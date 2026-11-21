"""Cute&Funny Reader — FastAPI server."""
from __future__ import annotations

import logging
import os
import posixpath
import shutil
import json
import re
import secrets
import threading
import time
import uuid as _uuid
import zipfile
import zlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import ClientDisconnect

import asyncio
import contextvars
import mimetypes

from fastapi.responses import JSONResponse

from .auth import COOKIE, SESSION_DAYS, Accounts
from .store import Db, Store
from .library import COL_MARK, CONFIG_DIR, LIB_ROOT, safe_component, MEDIA_EXT, REPACK_EXT, REPACK_KIND, VIDEO_EXT, Library, is_avif, is_heic, is_jxl, is_rar, needs_transcode, is_raw, is_video, repack_to_cbz

__version__ = "1.7.3"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cfreader")

lib = Library()
from .optimize import Optimizer  # noqa: E402
from .uploadlog import UploadLog, damage_detail  # noqa: E402
from .jobs import Jobs  # noqa: E402
from .events import Hub  # noqa: E402
opt = Optimizer(lib)
jobs = Jobs(lib.db)                    # every background job (docs/JOBS.md)
hub = Hub(jobs.visible)                # the live stream: GET /api/events
jobs.listeners.append(hub.publish)
accounts = Accounts(CONFIG_DIR)
uplog = UploadLog(CONFIG_DIR / "logs")
favs = Store(Db.at(CONFIG_DIR / "reader.db"), "favorites", CONFIG_DIR / "favorites.json")      # {account id: [list, …]} — references only, never files
lib.accounts = accounts
_user: contextvars.ContextVar[dict | None] = contextvars.ContextVar("user", default=None)
STATIC = Path(__file__).parent / "static"
# fingerprint of the front-end files: busts browser caches (js/….js?v=…, app.css?v=…) and lets open tabs notice
# a rebuild. The frontend is in parts (static/js/*.js), all listed in index.html.
import hashlib as _hashlib
_front_seen: tuple = (None, "", "")


def _front_files() -> list[Path]:
    return [STATIC / "index.html", STATIC / "app.css", *sorted((STATIC / "js").glob("*.js"))]


def front() -> tuple[str, str]:
    """(build fingerprint, index.html) — recomputed when a front-end file changes on disk, so dev mode
    (./app mounted into the container) shows edits on refresh; costs a stat() per file otherwise."""
    global _front_seen
    files = _front_files()
    stamp = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    if stamp != _front_seen[0]:
        build = _hashlib.sha1(b"".join(f.read_bytes() for f in files)).hexdigest()[:10]
        index = re.sub(r'src="(js/[^"?]+\.js)"', rf'src="\1?v={build}"', (STATIC / "index.html").read_text("utf-8"))
        index = index.replace("app.css", f"app.css?v={build}").replace("<head>", f'<head><meta name="cf-build" content="{build}">', 1)
        _front_seen = (stamp, build, index)
    return _front_seen[1], _front_seen[2]


CACHE = "public, max-age=604800"


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=lib.watch_loop, name="scanner", daemon=True).start()
    threading.Thread(target=lib.prep_loop, name="prepare", daemon=True).start()
    threading.Thread(target=opt.loop, name="optimize", daemon=True).start()
    jobs.start_workers()
    threading.Thread(target=_watch_rev, name="events", daemon=True).start()
    yield
    jobs.stop()


def _watch_rev():
    """Tell every open tab when the library changed (a scan found something, an edit was saved)."""
    last = lib.rev
    while True:
        time.sleep(0.5)
        if lib.rev != last:
            last = lib.rev
            hub.publish({"type": "library", "rev": last})


app = FastAPI(title="Cute&Funny Reader", version=__version__, lifespan=lifespan)

PUBLIC_FIELDS = ("id", "seriesId", "series", "library", "label", "title", "number", "kind", "format",
                 "src", "pages", "author", "publisher", "summary", "rtl", "added", "mtime", "file", "size",
                 "collection", "collectionId", "genres", "tags", "release", "year", "isManga", "videos")


def public(b: dict) -> dict:
    b = lib.effective(b)
    out = {k: b.get(k) for k in PUBLIC_FIELDS}
    out["edited"] = bool(b.get("edited"))
    out["unsaved"] = bool(b.get("unsaved"))                        # edits the file could hold but doesn't yet
    out["trashed"] = (lib.trash.get(b["id"]) or {}).get("at")       # marked for the trash (still in place)
    out["hasCover"] = lib.has_cover(b)
    out["seriesCover"] = bool(b.get("seriesCover"))
    out["coverPage"] = b["entries"].index(b["cover"]) if b.get("format") == "images" and b.get("cover") in (b.get("entries") or []) else None
    out["raw"] = is_raw(b)
    out["jxl"] = is_jxl(b)
    out["heic"] = is_heic(b)
    out["transcode"] = needs_transcode(b)
    out["avif"] = is_avif(b)
    out["optimized"] = bool(opt.kept.get(b["id"]))                  # converted by ✨ Optimize
    out["canUndo"] = opt.can_undo(b["id"])                           # … and its original is still kept
    return out


def me() -> dict:
    u = _user.get()
    if not u:
        raise HTTPException(401, "Please sign in")
    return u


def mine() -> set:
    return lib.owned(me()["id"])


def own_lib(lid: str | None) -> dict | None:
    """A library of the signed-in account (404 for anything else — other accounts' data doesn't exist)."""
    if lid is None:
        return None
    l = lib.get_library(lid)
    if not l or l.get("owner") != me()["id"]:
        raise HTTPException(404, "library not found")
    return l


def book_or_404(bid: str) -> dict:
    b = lib.get(bid)
    if not b or b["library"] not in mine():
        raise HTTPException(404, "book not found")
    return b


def own_series(sid: str | None) -> str | None:
    if not sid:
        return sid
    books = lib.series_books(sid)
    lid = books[0]["library"] if books else next((x["library"] for x in lib.empty_series() if x["seriesId"] == sid), None)
    if lid not in mine():
        raise HTTPException(404, "series not found")
    return sid


def own_collection(cid: str | None) -> str | None:
    if not cid:
        return cid
    try:
        l, _ = lib.find_collection(cid)
    except KeyError:
        raise HTTPException(404, "collection not found")
    if l.get("owner") != me()["id"]:
        raise HTTPException(404, "collection not found")
    return cid


def cached(request: Request, etag: str, data: bytes, mime: str) -> Response:
    etag = f'"{etag}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": CACHE})
    return Response(content=data, media_type=mime, headers={"ETag": etag, "Cache-Control": CACHE})


# ------------------------------------------------------------------ library
@app.get("/api/status")
def status():
    if lib.discover() + lib.drop_missing():
        _scan_soon()
    ids = mine()
    books = [b for b in lib.books.values() if b["library"] in ids]
    trash = lib.trash_items(me()["id"], ids)
    return {**lib.status(), "books": len(books), "series": len({b["seriesId"] for b in books}),
            "libraries": len(ids), "version": __version__, "build": front()[0],
            "trash": {"count": len(trash), "bytes": sum(x["size"] for x in trash)}}


def _file_op(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except KeyError:
        raise HTTPException(404, "not found — try rescanning")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except OSError as e:
        msg = str(e.strerror or e)
        if "try again" in msg:                     # an open file on the host, not a read-only mount
            raise HTTPException(409, f"Couldn’t finish: {msg[0].upper() + msg[1:]}.")
        raise HTTPException(400, f"File operation failed ({msg}). Is /data writable?")
    return {"ok": True}


@app.post("/api/books/{bid}/move")
def move_book(bid: str, body: dict = Body(...)):
    book_or_404(bid); own_lib(body.get("library")); own_series(body.get("seriesId"))
    return _file_op(lib.move_book, bid, library=body.get("library"), series_id=body.get("seriesId"), new_series=body.get("newSeries"))


@app.delete("/api/books/{bid}")
def delete_book(bid: str):
    b = book_or_404(bid)
    return _file_op(lib.trash_books, [b])                  # to the trash (see Library.trash_books)


@app.post("/api/series/{sid}/move")
def move_series(sid: str, body: dict = Body(...)):
    if not body.get("library") and not body.get("into") and body.get("collection") is None:
        raise HTTPException(400, "Choose a library or a series")
    own_series(sid); own_lib(body.get("library")); own_series(body.get("into")); own_collection(body.get("collection"))
    return _file_op(lib.move_series, sid, library=body.get("library"), into=body.get("into"), collection=body.get("collection"))


@app.delete("/api/series/{sid}")
def delete_series(sid: str):
    own_series(sid)
    books = lib.series_books(sid)
    if not books:
        try:
            removed = lib.delete_empty_series(sid)
        except OSError as e:
            raise HTTPException(400, f"Couldn't remove the folder ({e.strerror or e})")
        if removed:
            return {"ok": True}
        raise HTTPException(404, "series not found")
    return _file_op(lib.trash_books, books)


@app.post("/api/series/delete")
def delete_series_many(body: dict = Body(...)):
    ids = [i for i in body.get("ids", []) if isinstance(i, str)]
    if not ids:
        raise HTTPException(400, "Nothing selected")
    for i in ids:
        own_series(i)
    out = {}
    _file_op(lambda: out.update(deleted=lib.delete_series_many(ids)))
    return {"ok": True, **out}


@app.post("/api/libraries/{lid}/collections")
def create_collection(lid: str, body: dict = Body(...)):
    own_lib(lid)
    out = {}
    _file_op(lambda: out.update(lib.create_collection(lid, body.get("name", ""))))
    return out


@app.patch("/api/collections/{cid}")
def rename_collection(cid: str, body: dict = Body(...)):
    own_collection(cid)
    out = {}
    _file_op(lambda: out.update(id=lib.rename_collection(cid, body.get("name", ""))))
    return out


@app.post("/api/collections/{cid}/ungroup")
def ungroup_collection(cid: str):
    own_collection(cid)
    return _file_op(lib.ungroup_collection, cid)


@app.delete("/api/collections/{cid}")
def delete_collection(cid: str):
    own_collection(cid)
    return _file_op(lib.delete_collection, cid)


@app.post("/api/libraries/{lid}/series")
def create_series(lid: str, body: dict = Body(...)):
    own_lib(lid)
    out = {}
    _file_op(lambda: out.update(lib.create_series(lid, body.get("name", ""))))
    return out


@app.patch("/api/series/{sid}/details")
def edit_series_details(sid: str, body: dict = Body(...)):
    own_series(sid)
    try:
        n = lib.edit_series(sid, body.get("fields") or {}, bool(body.get("reset")))
    except KeyError:
        raise HTTPException(404, "series not found")
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"books": n}


@app.post("/api/series/{sid}/write")
async def write_series_edits(sid: str):
    """Write the saved details / tags / cover choice into the series' files (metadata.json) — on request,
    because it rewrites each archive (minutes for a set of several GB)."""
    own_series(sid)
    try:
        n = await asyncio.to_thread(lib.write_edits, sid)
    except KeyError:
        raise HTTPException(404, "series not found")
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"files": n}


@app.put("/api/series/{sid}/cover")
def set_series_cover(sid: str, body: dict = Body(...)):
    """{book, page} → that photo is the series' cover · {book: null} → back to the default."""
    own_series(sid)
    try:
        page = body.get("page")
        lib.set_cover(sid, body.get("book") or None, int(page) if page is not None else None)
    except KeyError:
        raise HTTPException(404, "series not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


@app.patch("/api/series/{sid}")
def rename_series(sid: str, body: dict = Body(...)):
    own_series(sid)
    out = {}
    _file_op(lambda: out.update(seriesId=lib.rename_series(sid, body.get("name", ""))))
    return out


@app.post("/api/books/move")
def move_books(body: dict = Body(...)):
    ids = [i for i in body.get("ids", []) if isinstance(i, str)]
    if not ids:
        raise HTTPException(400, "Nothing selected")
    for i in ids:
        book_or_404(i)
    own_lib(body.get("library")); own_series(body.get("seriesId"))
    return _file_op(lib.move_books, ids, library=body.get("library"), series_id=body.get("seriesId"), new_series=body.get("newSeries"))


@app.post("/api/books/delete")
def delete_books(body: dict = Body(...)):
    books = [book_or_404(i) for i in body.get("ids", []) if lib.get(i)]
    if not books:
        raise HTTPException(400, "Nothing selected")
    return _file_op(lib.trash_books, books)


# ---- Trash
@app.get("/api/trash")
def trash_list():
    """Everything in your trash — items still being moved out and items already in .trash alike — with totals and
    how long it's kept."""
    from .library import TRASH_DELAY
    items = lib.trash_items(me()["id"], mine())
    return {"items": items, "count": len(items), "bytes": sum(x["size"] for x in items),
            "keepDays": lib.trash_keep_days(), "keepChoices": list(lib.KEEP_CHOICES), "delay": TRASH_DELAY,
            "canChange": bool(me().get("admin"))}


@app.put("/api/trash/settings")
def trash_settings(body: dict = Body(...)):
    """How long the trash keeps things (days; 0 = until emptied) — one setting for the whole reader."""
    admin()
    try:
        return {"keepDays": lib.set_trash_keep_days(int(body.get("keepDays")))}
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e) if isinstance(e, ValueError) and "Keep" in str(e) else "keepDays must be a number")


@app.get("/api/trash/{tid}/cover")
def trash_cover(tid: str):
    e = lib.bin.get(tid)
    data = lib.bin_cover(tid) if e and e.get("owner") == me()["id"] else None
    if not data:
        raise HTTPException(404)
    return Response(data, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


def _my_trash(body: dict) -> tuple[list[dict], list[str]]:
    """(marked books, bin ids) of yours that a request names — `all`: everything in your trash."""
    items = lib.trash_items(me()["id"], mine())
    if body.get("all"):
        marked = [x["id"] for x in items if x["kind"] == "marked"]
        tids = [x["tid"] for x in items if x["kind"] == "bin"]
    else:
        keys = {x["key"] for x in items}
        marked = [i for i in body.get("ids", []) if "b:" + i in keys]
        tids = [t for t in body.get("bin", []) if "t:" + t in keys]
    return [b for b in (lib.get(i) for i in marked) if b], tids


@app.post("/api/trash/restore")
def trash_restore(body: dict = Body(...)):
    """ids: books still being moved out · bin: items already in .trash · all: everything · into: the library for
    items whose own library is gone (without it: 409 with needLibrary = those items)."""
    books, tids = _my_trash(body)
    out = {"restored": lib.untrash([b["id"] for b in books])}
    into = body.get("into") or None
    if into and into not in mine():
        raise HTTPException(404, "library not found")
    try:
        _file_op(lambda: out.update(restored=out["restored"] + lib.restore_bin(tids, into)))
    except LookupError as e:
        return JSONResponse({"detail": "Their library is gone — choose a library to restore them into", "needLibrary": e.args[0],
                             "restored": out["restored"]}, status_code=409)
    return {"ok": True, **out}


@app.post("/api/trash/purge")
def trash_purge(body: dict = Body(...)):
    """Delete for good: books still being moved out (ids), items in .trash (bin), or everything (all)."""
    books, tids = _my_trash(body)
    out = {"deleted": 0}
    if books:
        _file_op(lib.delete_books, books)
        lib.trash.delete_many([b["id"] for b in books])
        out["deleted"] += len(books)
    _file_op(lambda: out.update(deleted=out["deleted"] + lib.purge_bin(tids)))
    return {"ok": True, **out}


@app.post("/api/scan")
def scan():
    if not lib.scanning:                           # the button means "check everything", not just changed folders
        threading.Thread(target=lib.scan, kwargs={"deep": True}, daemon=True).start()
    return {"started": True}


class _Feed:
    """What changed since a browser last asked. Every book's public form is compared with the one handed out
    before; a book that differs gets the next sequence number. A browser sends the number it has and receives
    only the books changed (or removed) after it — instead of the whole library after every action."""
    KEEP_GONE = 20000

    def __init__(self):
        self.lock = threading.Lock()
        self.epoch = secrets.token_hex(4)          # new on every server start: a restart means "send everything"
        self.seq = 0
        self.pub: dict[str, tuple[dict, int]] = {}
        self.gone: list[tuple[int, str]] = []
        self.floor = 0                             # removals older than this were forgotten

    def refresh(self) -> int:
        with self.lock:
            cur = {b["id"]: public(b) for b in list(lib.books.values())}
            nxt = self.seq + 1
            changed = False
            for bid, p in cur.items():
                old = self.pub.get(bid)
                if old is None or old[0] != p:
                    self.pub[bid] = (p, nxt); changed = True
            for bid in [bid for bid in self.pub if bid not in cur]:
                del self.pub[bid]; self.gone.append((nxt, bid)); changed = True
            if changed:
                self.seq = nxt
            if len(self.gone) > self.KEEP_GONE:
                drop = len(self.gone) - self.KEEP_GONE // 2
                self.floor = self.gone[drop - 1][0]; self.gone = self.gone[drop:]
            return self.seq

    def since(self, ids: set, epoch: str | None, seq: int | None) -> dict:
        self.refresh()
        with self.lock:
            full = epoch != self.epoch or seq is None or seq < self.floor or seq > self.seq
            if full:
                books = [p for p, _ in self.pub.values() if p["library"] in ids]
                removed = []
            else:
                hit = [p for p, n in self.pub.values() if n > seq]
                books = [p for p in hit if p["library"] in ids]
                removed = [bid for n, bid in self.gone if n > seq] + [p["id"] for p in hit if p["library"] not in ids]
            return {"epoch": self.epoch, "seq": self.seq, "full": full, "books": books, "removed": removed}

    def counts(self, ids: set) -> dict:
        with self.lock:
            out: dict[str, list] = {}
            for p, _ in self.pub.values():
                if p["library"] in ids:
                    c = out.setdefault(p["library"], [set(), 0]); c[0].add(p["seriesId"]); c[1] += 1
            return out


feed = _Feed()


@app.get("/api/library")
def library(request: Request, since: int | None = None, epoch: str | None = None):
    """The signed-in account's library. With ?since=<seq>&epoch=<epoch> from an earlier answer: only the books
    changed or removed after that ("full": false). Libraries, collections and empty series always come whole."""
    if lib.discover() + lib.drop_missing():
        _scan_soon()
    ids = mine()
    out = feed.since(ids, epoch, since)
    counts = feed.counts(ids)
    out["libraries"] = [{**l, "series": len(counts.get(l["id"], [(), 0])[0]), "books": counts.get(l["id"], [(), 0])[1]}
                        for l in lib.libraries if l["id"] in ids]
    cols, empty = lib.folder_info()
    out["emptySeries"] = [e for e in empty if e["library"] in ids]
    out["collections"] = [c for c in cols if c["library"] in ids]
    return _json_gz(request, out)


def _json_gz(request: Request, data) -> Response:
    """Big JSON, compressed when the browser accepts it (the library list is ~1.8 MB for 3000 books → ~10× smaller)."""
    import gzip, json as _json
    body = _json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if "gzip" in request.headers.get("accept-encoding", "") and len(body) > 2048:
        return Response(gzip.compress(body, 5), media_type="application/json", headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(body, media_type="application/json")


# ------------------------------------------------------------------ libraries
def _scan_soon():
    if not lib.scanning:
        threading.Thread(target=lib.scan, daemon=True).start()


@app.get("/api/folders")
def folders():
    return {"root": str(LIB_ROOT / me()["folder"]), "folders": lib.folders(me()["folder"])}


@app.post("/api/libraries")
def create_library(body: dict = Body(...)):
    try:
        l = lib.create_library(body.get("name", ""), body.get("path"), body.get("rtl", False), body.get("color", ""), body.get("type"), owner=me())
    except ValueError as e:
        raise HTTPException(400, str(e))
    _scan_soon()
    return l


@app.patch("/api/libraries/{lid}")
def update_library(lid: str, body: dict = Body(...)):
    own_lib(lid)
    try:
        return lib.update_library(lid, body)
    except KeyError:
        raise HTTPException(404, "library not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/libraries/{lid}")
def delete_library(lid: str, files: bool = False):
    own_lib(lid)
    out = {}
    _file_op(lambda: out.update(folder=lib.delete_library(lid, delete_files=files)))
    return {"ok": True, **out}


def free_name(dest: Path) -> Path:
    """`dest`, or "Name (2).ext", "Name (3).ext"… — the first that isn't taken. Only a trailing "(number)"
    is replaced; a "(Subtitle)" is part of the name."""
    stem, i = re.sub(r" \(\d+\)$", "", dest.stem), 2
    while dest.exists():
        dest = dest.with_name(f"{stem} ({i}){dest.suffix}")
        i += 1
    return dest


def damaged_entry(path) -> tuple[str, str] | None:
    """(name, why) for the first file inside a zip that can't be read back as stored (None = all good).
    Every byte is read once — an upload that arrived damaged, or was damaged before, is caught here
    instead of when someone opens the book."""
    try:
        with zipfile.ZipFile(path) as z:
            for i in z.infolist():
                try:
                    with z.open(i) as f:
                        while f.read(1 << 20):
                            pass
                except zipfile.BadZipFile as e:
                    if "CRC" in str(e):
                        return i.filename, "fails its checksum (its bytes changed)"
                    return i.filename, "can't be found where the archive's index says it is " \
                                       "(the archive was written wrongly — e.g. a zip over 4 GB without ZIP64)"
                except (EOFError, zlib.error) as e:
                    return i.filename, f"can't be unpacked ({e or 'cut off'})"
    except zipfile.BadZipFile as e:
        return "", str(e)
    except Exception:  # noqa: BLE001 — encrypted / unusual archives: not ours to judge
        return None
    return None


def damaged_message(bad: tuple[str, str]) -> str:
    name, why = bad
    what = f"“{Path(name).name}” inside {why}" if name else why
    return f"This archive is damaged: {what}. Check the original file (try unpacking it) and upload it again."


@app.put("/api/libraries/{lid}/files")
async def upload(lid: str, name: str, request: Request, series: str | None = None,
                 collection: str | None = None, folder: str | None = None, batch: str | None = None):
    """Stores one file and notes how it went in the upload log (config/logs/)."""
    return await _logged(lid, name, request, batch, _upload(lid, name, request, series, collection, folder),
                         announced=int(request.headers.get("content-length") or 0))


async def _logged(lid: str, name: str, request: Request, batch: str | None, work, announced: int = 0):
    """Runs one upload (`work`) and writes its outcome to the upload log."""
    request.state.received, request.state.detail, request.state.lib_name = 0, "", lid
    note = dict(lib="", user="", name=name)
    try:
        note["user"] = me()["email"]
    except HTTPException:
        work.close()
        raise                                      # not signed in: nothing to log
    def done(state, why=""):
        note["lib"] = request.state.lib_name
        uplog.record(batch, state=state, why=why, detail=request.state.detail,
                     sent=request.state.received, announced=announced, **note)
    try:
        out = await work
    except HTTPException as e:
        done("err", str(e.detail))
        raise
    except ClientDisconnect:
        done("cancel")
        raise
    except Exception as e:  # noqa: BLE001
        done("err", f"server error: {type(e).__name__}: {e}")
        raise
    done("skip" if out.get("skipped") else "ok")
    return out


@app.post("/api/uploads/{batch}/done")
def upload_batch_done(batch: str, body: dict = Body(default={})):
    """End of one drop: writes its entry to the upload log. The body carries what the server never saw."""
    l = None
    try:
        l = own_lib(body.get("lib")) if body.get("lib") else None
    except HTTPException:
        pass
    uplog.finish(batch, body, lib=(l or {}).get("name", ""), user=me()["email"])
    return {"ok": True}


# ---- Folders packed on the server -----------------------------------------------------------------------------
# A dropped folder of photos becomes one .zip (Cosplay) / .cbz. The browser used to build that archive itself,
# holding every photo in memory (a set with large videos needed gigabytes) — now it only sends the files:
#   POST   /api/libraries/{lid}/packs            → {id}
#   PUT    /api/packs/{id}/files?name=001.jpg    one file at a time, in page order, written straight into the zip
#   POST   /api/packs/{id}/finish?name=…&series=…   the zip is closed and stored like an upload
#   DELETE /api/packs/{id}                       cancelled
# The zip being built lives in <account>/.packs/ — on the library's own drive, hidden from scans like .trash —
# so finishing *moves* it into place. Every byte is written once: with Docker Desktop's shared folders, staging
# the files first and copying them into a zip afterwards took minutes for a 4 GB set.
# Left-overs older than a day are removed when the next pack starts.
PACK_DIR = ".packs"
PACK_TTL = 86400
PACK_ID = re.compile(r"^[a-f0-9]{16}$")
PACK_META = {"metadata.json", "comicinfo.xml", "info.yaml", "info.yml"}
_pack_locks: dict[str, asyncio.Lock] = {}


def _packs_root() -> Path:
    return LIB_ROOT / me()["folder"] / PACK_DIR


def _pack(pid: str) -> tuple[Path, dict]:
    """(the zip being built, its meta) for one of *this account's* packs — 404 otherwise."""
    root = _packs_root()
    try:
        meta = json.loads((root / f"{pid}.json").read_text("utf-8")) if PACK_ID.match(pid) else None
    except (OSError, ValueError):
        meta = None
    if not meta or meta.get("owner") != me()["id"]:
        raise HTTPException(404, "pack not found — it may have expired; drop the folder again")
    return root / f"{pid}.zip", meta


def _pack_drop(zp: Path):
    zp.unlink(missing_ok=True)
    zp.with_suffix(".json").unlink(missing_ok=True)
    _pack_locks.pop(zp.stem, None)


def _sweep_packs(root: Path):
    try:
        for f in root.iterdir():
            if f.stat().st_mtime < time.time() - PACK_TTL:
                f.unlink(missing_ok=True)
    except OSError:
        pass


@app.post("/api/libraries/{lid}/packs")
def pack_start(lid: str):
    own_lib(lid)
    root = _packs_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(400, f"Can't write to the library folder ({e.strerror}). Is /data mounted read-only?")
    _sweep_packs(root)
    pid = secrets.token_hex(8)
    zipfile.ZipFile(root / f"{pid}.zip", "w").close()          # an empty archive to add to
    (root / f"{pid}.json").write_text(json.dumps({"owner": me()["id"], "lib": lid, "started": time.time()}), "utf-8")
    return {"id": pid}


@app.put("/api/packs/{pid}/files")
async def pack_file(pid: str, name: str, request: Request):
    zp, _ = _pack(pid)
    n = safe_component(posixpath.basename(name.replace("\\", "/")))
    if not n or not (n.lower().endswith(MEDIA_EXT) or n.lower() in PACK_META):
        raise HTTPException(400, "Only pictures, videos and metadata files can go into a set")
    async with _pack_locks.setdefault(pid, asyncio.Lock()):    # one file at a time into the same zip
        z = zipfile.ZipFile(zp, "a", zipfile.ZIP_STORED, allowZip64=True)
        try:
            if n in z.namelist():
                raise HTTPException(409, f"“{n}” is already in this set")
            info = zipfile.ZipInfo(n, date_time=time.localtime()[:6])
            info.compress_type = zipfile.ZIP_STORED            # photos / videos don't shrink: stored as they are
            with z.open(info, "w", force_zip64=True) as w:     # size unknown up front: room for 4 GB+ files
                async for chunk in request.stream():
                    w.write(chunk)
        except HTTPException:
            z.close()
            raise
        except BaseException:                                  # cut off mid-file: this set can't be finished
            z.close()
            _pack_drop(zp)
            raise
        z.close()
    return {"ok": True}


@app.post("/api/libraries/{lid}/plan")
def upload_plan(lid: str, body: dict = Body(...)):
    """What a drop becomes (app/uploadplan.py): the browser sends the dropped paths and sizes — plus the text of
    any metadata.json / ComicInfo.xml — and carries out the jobs it gets back."""
    from .uploadplan import plan
    l = own_lib(lid)
    series = body.get("series") or None
    own_series(series)
    items = [{"path": str(it.get("path") or ""), "size": int(it.get("size") or 0)}
             for it in (body.get("items") or [])[:50000] if isinstance(it, dict)]
    meta = {k: v[:200_000] for k, v in (body.get("meta") or {}).items() if isinstance(v, str)}
    return {"jobs": plan(l, items, meta, series, body.get("collection") or None, str(body.get("today") or "")[:10])}


@app.post("/api/packs/{pid}/finish")
async def pack_finish(pid: str, name: str, request: Request, series: str | None = None,
                      collection: str | None = None, folder: str | None = None, batch: str | None = None):
    zp, meta = _pack(pid)
    try:
        with zipfile.ZipFile(zp) as z:
            media = any(n.lower().endswith(MEDIA_EXT) for n in z.namelist())
    except (OSError, zipfile.BadZipFile):
        media = False
    if not media:
        _pack_drop(zp)
        raise HTTPException(400, "Nothing arrived to pack — no pictures or videos")

    async def fill(tmp: Path):
        request.state.received = zp.stat().st_size
        await asyncio.to_thread(shutil.move, zp, tmp)          # same drive: a rename, not a copy

    try:
        return await _logged(meta["lib"], name, request, batch,
                             _upload(meta["lib"], name, request, series, collection, folder, fill=fill))
    finally:
        _pack_drop(zp)


@app.delete("/api/packs/{pid}")
def pack_cancel(pid: str):
    _pack_drop(_pack(pid)[0])
    return {"ok": True}


async def _upload(lid: str, name: str, request: Request, series: str | None,
                  collection: str | None, folder: str | None, fill=None):
    """Stores one uploaded file. `fill(tmp)` writes the bytes instead of the request body — used for
    folders packed here on the server (their size is only known once packed; they are built from pictures
    this server just checked, so the full re-read for damage is skipped)."""
    l = own_lib(lid)
    request.state.lib_name = l.get("name") or lid
    own_series(series)   # `collection` is a folder NAME inside this (already owned) library, not a collection id
    try:
        col_dir = LIB_ROOT / l["path"] / safe_component(collection) if collection and safe_component(collection) else None
        col_new = bool(col_dir) and not col_dir.exists()
        dest = lib.upload_target(l, name, series, collection, folder)
        made = [p for p in [dest.parent, *dest.parent.parents] if not p.exists() and LIB_ROOT in p.parents]   # new folders, deepest first
        dest.parent.mkdir(parents=True, exist_ok=True)
    except KeyError:
        raise HTTPException(404, "series not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except OSError as e:
        raise HTTPException(400, f"Can't write to the library folder ({e.strerror}). Is /data mounted read-only?")
    size = int(request.headers.get("content-length") or 0)
    cosplay = l.get("type") == "cosplay"
    keep = ".zip" if cosplay else ".cbz"           # what other archives become: Cosplay sets are plain .zip
    repack = dest.suffix.lower() if dest.name.lower().endswith(REPACK_EXT) else None
    plain_zip = dest.suffix.lower() == ".zip"      # a regular .zip is already a .cbz inside — checked first
    if repack or plain_zip:                        # .cb7 / .7z / .cbr / .rar → .cbz (Cosplay: .zip); .zip → .cbz outside Cosplay
        dest = dest.with_suffix(keep)
        if dest.exists():
            return {"skipped": True, "path": dest.relative_to(LIB_ROOT).as_posix()}
    if cosplay and dest.suffix.lower() in (".zip", ".cbz"):
        twin = dest.with_suffix(".cbz" if dest.suffix.lower() == ".zip" else ".zip")
        if twin.exists() and size and twin.stat().st_size == size:   # the same set uploaded before as .cbz
            return {"skipped": True, "path": twin.relative_to(LIB_ROOT).as_posix()}
    same_as = [dest] + ([twin] if cosplay and dest.suffix.lower() in (".zip", ".cbz") else [])  # a pack may repeat one
    if dest.exists():
        if size and dest.stat().st_size == size:
            return {"skipped": True, "path": dest.relative_to(LIB_ROOT).as_posix()}
        dest = free_name(dest)
    # Each upload writes to a temporary file of its own. (Two files with the same name uploaded at the same
    # moment used to share one — their contents got mixed into a single damaged archive.)
    tmp = dest.with_name(f".{dest.name}.{_uuid.uuid4().hex[:8]}.part")
    taken_at_start = dest.exists()
    try:
        if fill:
            await fill(tmp)
            n = tmp.stat().st_size
            for o in same_as:                      # the same folder dropped before: already there
                if o.exists() and o.stat().st_size == n:
                    return {"skipped": True, "path": o.relative_to(LIB_ROOT).as_posix()}
        else:
            with open(tmp, "wb") as f:
                async for chunk in request.stream():
                    f.write(chunk)
                    request.state.received += len(chunk)
        low = dest.name.lower()
        kind = REPACK_KIND.get(repack or "")
        if kind == "cb7":
            import py7zr
            if not py7zr.is_7zfile(tmp):
                raise HTTPException(400, f"That file isn't a valid {repack} (7-Zip) archive")
        elif kind == "cbr":
            if not is_rar(tmp):
                raise HTTPException(400, f"That file isn't a valid {repack} (RAR) archive")
        if plain_zip:
            if not zipfile.is_zipfile(tmp):
                raise HTTPException(400, "That file isn't a valid .zip archive")
            with zipfile.ZipFile(tmp) as z:
                if not any(n.lower().endswith(MEDIA_EXT) and "__MACOSX" not in n for n in z.namelist()):
                    raise HTTPException(400, "There are no images or videos inside that .zip")
            bad = None if fill else await asyncio.to_thread(damaged_entry, tmp)
            if bad:
                request.state.detail = await asyncio.to_thread(damage_detail, tmp, bad[0])
                raise HTTPException(400, damaged_message(bad))
            if not taken_at_start: dest = free_name(dest)      # a same-named upload finished meanwhile
            os.replace(tmp, dest)
            return {"skipped": False, "converted": not cosplay, "path": dest.relative_to(LIB_ROOT).as_posix()}
        if repack:
            if not taken_at_start: dest = free_name(dest)
            try:
                await asyncio.to_thread(repack_to_cbz, tmp, dest, kind)
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception as e:  # noqa: BLE001
                raise HTTPException(400, f"Couldn't convert that {repack} to {keep}: {e}")
            return {"skipped": False, "converted": True, "path": dest.relative_to(LIB_ROOT).as_posix()}
        elif low.endswith(VIDEO_EXT):
            pass                                   # the browser checks playability
        elif not zipfile.is_zipfile(tmp):
            raise HTTPException(400, "That file isn't a valid .cbz / .epub archive")
        else:
            bad = None if fill else await asyncio.to_thread(damaged_entry, tmp)
            if bad:
                request.state.detail = await asyncio.to_thread(damage_detail, tmp, bad[0])
                raise HTTPException(400, damaged_message(bad))
        if not taken_at_start: dest = free_name(dest)          # a same-named upload finished meanwhile
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()
        if not dest.exists():                      # cancelled / failed: don't leave the folders it made behind
            for p in made:
                try:
                    p.rmdir()                      # only succeeds while empty (another upload may have filled it)
                except OSError:
                    break
            if col_new and col_dir.is_dir() and [p.name for p in col_dir.iterdir()] == [COL_MARK]:
                (col_dir / COL_MARK).unlink(missing_ok=True)   # a collection this upload started, still empty
                try:
                    col_dir.rmdir()
                except OSError:
                    pass
    return {"skipped": False, "path": dest.relative_to(LIB_ROOT).as_posix()}


@app.get("/api/books/{bid}")
def book(bid: str):
    b = book_or_404(bid)
    out = public(b)
    if b["format"] in ("images", "video"):
        out["dims"] = lib.dims(b)
        out["videos"] = [0] if b["format"] == "video" else b.get("videos") or []
    else:
        out["chapters"] = [{"title": c.get("title")} for c in b["chapters"]]
    return out


def ranged(request: Request, path, start: int, length: int, mime: str):
    """Serve a byte slice of a file with HTTP Range support (video seeking)."""
    first, last = 0, length - 1
    rng = request.headers.get("range", "")
    status = 200
    if rng.startswith("bytes="):
        a, _, z = rng[6:].split(",")[0].partition("-")
        try:
            if a:
                first, last = int(a), (int(z) if z else length - 1)
            elif z:
                first, last = max(0, length - int(z)), length - 1
        except ValueError:
            pass
        last = min(last, length - 1)
        if first > last:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{length}"})
        status = 206

    def gen():
        with open(path, "rb") as f:
            f.seek(start + first)
            left = last - first + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                left -= len(chunk)
                yield chunk

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(last - first + 1), "Cache-Control": "public, max-age=3600"}
    if status == 206:
        headers["Content-Range"] = f"bytes {first}-{last}/{length}"
    return StreamingResponse(gen(), status_code=status, media_type=mime, headers=headers)


@app.get("/api/books/{bid}/pages/{n}")
def page(bid: str, n: int, request: Request, max: int | None = None):
    """A page. `max` (long edge in device pixels) asks for a copy no bigger than the screen."""
    b = book_or_404(bid)
    if b["format"] not in ("images", "video") or not 0 <= n < len(b["entries"]):
        raise HTTPException(404)
    name = b["entries"][n]
    if b["format"] == "video" or is_video(name):
        path, start, length = lib.media_span(b, n)
        return ranged(request, path, start, length, mimetypes.guess_type(name)[0] or "video/mp4")
    if max:
        lib.display_hint = min(lib.DISPLAY_SIZES, key=lambda x: abs(x - max))   # the worker prepares this size
        try:
            small = lib.display_page(b, n, max)
        except Exception as e:  # noqa: BLE001 — a copy that can't be made just means: send the original
            log.warning("display copy of %s page %d failed: %s", b["rel"], n, e)
            small = None
        if small:
            return cached(request, f"{bid}-{b['mtime']}-{n}-m{max}", *small)
    data, mime = lib.page(b, n)
    return cached(request, f"{bid}-{b['mtime']}-{n}", data, mime)


# ---- ✨ Optimize (AVIF)
def _selected(body: dict) -> list[dict]:
    """{books: [...], series: [...], collections: [...]} → the signed-in account's books in it."""
    out, seen = [], set()
    def add(b):
        if b["id"] not in seen:
            seen.add(b["id"]); out.append(b)
    for bid in body.get("books") or []:
        add(book_or_404(bid))
    for sid in body.get("series") or []:
        own_series(sid)
        for b in sorted(lib.series_books(sid), key=lambda b: (b.get("number") is None, b.get("number") or 0, b["file"])):
            add(b)
    for lid in body.get("libraries") or []:
        own_lib(lid)
        for b in sorted((b for b in lib.books.values() if b["library"] == lid and not (lib.trash.get(b["id"]) or {}).get("at")),
                        key=lambda b: b["rel"]):
            add(b)
    for cid in body.get("collections") or []:
        own_collection(cid)
        try:
            _, folder = lib.find_collection(cid)
        except KeyError:
            raise HTTPException(404, "collection not found")
        pre = folder.relative_to(LIB_ROOT).as_posix() + "/"
        for b in sorted((b for b in lib.books.values() if b["rel"].startswith(pre)), key=lambda b: b["rel"]):
            add(b)
    if not out:
        raise HTTPException(400, "Nothing selected")
    return out


@app.get("/api/libraries/{lid}/storage")
def library_storage(lid: str):
    """How big the library is and how much of it ✨ Optimize could still convert."""
    own_lib(lid)
    books = [b for b in lib.books.values() if b["library"] == lid]
    out = {"books": len(books), "bytes": 0, "optimized": 0, "saved": 0, "convertible": 0, "convertibleBytes": 0}
    for b in books:
        size = opt.size(b)
        out["bytes"] += size
        k = opt.kept.get(b["id"])
        if k:
            out["optimized"] += 1
            out["saved"] += max(0, (k.get("before") or 0) - (k.get("after") or 0))
        elif not opt.why_not(b):
            out["convertible"] += 1
            out["convertibleBytes"] += size
    return out


@app.get("/api/optimize/presets")
def optimize_presets():
    from .optimize import KEEP_DAYS
    return {"presets": opt.presets(), "keepDays": KEEP_DAYS}


@app.post("/api/optimize/presets")
def optimize_preset_add(body: dict = Body(...)):
    me()
    try:
        return opt.add_preset(body.get("name"), body.get("quality"), body.get("speed"), body.get("subsampling") or "auto",
                              body.get("grayscale", True) is not False, body.get("mode") or "avif")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/optimize/presets/{pid}")
def optimize_preset_delete(pid: str):
    me()
    try:
        opt.delete_preset(pid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "preset not found")
    return {"ok": True}


@app.post("/api/optimize/estimate")
def optimize_estimate(body: dict = Body(...)):
    books = _selected(body)
    try:
        preset = opt.preset(body.get("preset") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    e = opt.estimate(books, preset, int(body.get("maxEdge") or 0))
    reasons = {}
    for b in books:
        why = opt.why_not(b)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
    raw = sum(1 for b in books if is_raw(b) and not opt.why_not(b))
    sample = next(((b, n) for b, n in opt.sample_pages([b for b in books if not opt.why_not(b)], 1)), None)
    return {**e, "why": reasons, "raw": raw,
            "sample": {"book": sample[0]["id"], "page": sample[1]} if sample else None}


@app.get("/api/books/{bid}/pages/{n}/optimized")
def optimize_compare(bid: str, n: int, request: Request, preset: str, max: int = 0):
    """One page as the chosen preset would make it — for the before / after view."""
    b = book_or_404(bid)
    if b.get("format") != "images" or not 0 <= n < len(b["entries"]):
        raise HTTPException(404)
    try:
        orig, new = opt.encode_sample(b, n, opt.preset(preset), max)
    except ValueError as e:
        raise HTTPException(400, str(e))
    p = opt.preset(preset)
    mime = ("image/webp" if p.get("mode") == "lossless" else "image/avif") if new != orig else mimetypes.guess_type(b["entries"][n])[0] or "image/jpeg"
    r = cached(request, f"opt-{bid}-{b['mtime']}-{n}-{preset}-{max}", new, mime)
    r.headers["X-Before"], r.headers["X-After"] = str(len(orig)), str(len(new))
    r.headers["Access-Control-Expose-Headers"] = "X-Before, X-After"
    return r


@app.post("/api/optimize")
def optimize_start(body: dict = Body(...)):
    books = _selected(body)
    try:
        return opt.start(me()["id"], books, body.get("preset") or "", bool(body.get("keep", True)),
                         int(body.get("maxEdge") or 0), str(body.get("title") or "")[:200])
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/optimize/undo")
def optimize_undo(body: dict = Body(...)):
    books = [b for b in _selected(body) if opt.can_undo(b["id"])]
    if not books:
        raise HTTPException(400, "There's no kept original to go back to")
    failed = []
    for b in books:
        try:
            opt.undo(b["id"])
        except (OSError, ValueError, KeyError) as e:
            failed.append(f"{b['file']}: {e}")
    if failed:
        raise HTTPException(409, "Couldn’t restore: " + "; ".join(failed[:3]))
    return {"restored": len(books)}


@app.get("/api/storage")
def storage():
    return opt.storage(me()["id"])


@app.put("/api/optimize/schedule")
def optimize_schedule(body: dict = Body(...)):
    me()
    try:
        return opt.set_schedule(body.get("on"), body.get("from", 1), body.get("to", 7), body.get("tz") or "", body.get("offset") or 0)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/optimize/originals/clear")
def optimize_originals_clear():
    return {"deleted": opt.drop_originals(me()["id"])}


@app.get("/api/jobs")
def jobs_list():
    """Every job you can see: ✨ Optimize runs (until they move onto the job system) and the rest."""
    return {"jobs": [{**j, "kind": "optimize"} for j in opt.list(me()["id"])] + jobs.list(me())}


@app.post("/api/jobs/{jid}/{action}")
def jobs_control(jid: str, action: str):
    if action not in ("pause", "resume", "cancel", "dismiss", "now"):
        raise HTTPException(400, "Unknown action")
    try:
        if jid in jobs.mem:
            if action == "now":
                raise HTTPException(400, "Unknown action")
            jobs.control(jid, action, me())
        else:
            opt.control(me()["id"], jid, action)
    except KeyError:
        raise HTTPException(404, "job not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.get("/api/events")
async def events(request: Request):
    """The live stream (Server-Sent Events): job progress and "the library changed", one connection per tab."""
    user = me()
    hello = {"type": "hello", "rev": lib.rev, "jobs": jobs.list(user)}
    return StreamingResponse(hub.stream(user, hello, request.is_disconnected), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/books/{bid}/transcode")
def transcode_start(bid: str):
    """JPEG XL / HEIC book: start converting its pages to PNG (cached). Poll GET for progress."""
    return lib.transcode_start(book_or_404(bid))


@app.get("/api/books/{bid}/transcode")
def transcode_status(bid: str):
    return lib.transcode_status(book_or_404(bid))


@app.get("/api/books/{bid}/thumbs/{n}")
def thumb(bid: str, n: int, request: Request, w: int = 200):
    b = book_or_404(bid)
    if b["format"] != "images" or not 0 <= n < len(b["entries"]):
        raise HTTPException(404)
    try:
        data = lib.thumb(b, n, w)
    except KeyError:
        raise HTTPException(404, "no thumbnail for videos")
    return cached(request, f"{bid}-{b['mtime']}-{n}-t{w}", data, "image/webp")


@app.get("/api/books/{bid}/cover")
def cover(bid: str, request: Request, w: int = 480):
    b = book_or_404(bid)
    data = lib.cover(b, w)
    if not data:
        raise HTTPException(404, "no cover")
    return cached(request, f"{bid}-{b['mtime']}-{lib.cover_tag(b)}-c{w}", data, "image/webp")


@app.get("/api/stack")
def stack(request: Request, books: str):
    """The two back covers of a collection card, drawn once (see Library.stack_back). books=id1,id2"""
    bs = [book_or_404(i) for i in books.split(",")[:2] if i]
    if not bs:
        raise HTTPException(404)
    data = lib.stack_back(bs)
    if not data:
        raise HTTPException(404, "no covers")
    return cached(request, "-".join(f"{b['id']}-{b['mtime']}-{lib.cover_tag(b)}" for b in bs) + "-stack", data, "image/webp")


@app.get("/api/books/{bid}/panels/{n}")
def panels(bid: str, n: int, rtl: bool = False):
    b = book_or_404(bid)
    if b["format"] != "images" or not 0 <= n < len(b["entries"]) or is_video(b["entries"][n]):
        raise HTTPException(404)
    return {"panels": lib.panels(b, n, rtl)}


@app.get("/api/books/{bid}/chapters/{i}")
def chapter(bid: str, i: int):
    b = book_or_404(bid)
    if b["format"] != "epub" or not 0 <= i < len(b["chapters"]):
        raise HTTPException(404)
    return lib.chapter(b, i)


@app.get("/api/books/{bid}/res/{path:path}")
def resource(bid: str, path: str, request: Request):
    b = book_or_404(bid)
    try:
        data, mime = lib.resource(b, path)
    except KeyError:
        raise HTTPException(404)
    return cached(request, f"{bid}-{b['mtime']}-{path}", data, mime)


# ------------------------------------------------------------------ favourites
# Named lists of references: whole series (comics / manga / novels) or single sets (Cosplay). Nothing is copied:
# an item is {kind, id, hint}. The hint (file names / size) finds the item again when its id changed —
# a series renamed or moved, a set moved to another collection, in the app or on disk.
def _lib_type(lid: str) -> str:
    return (lib.get_library(lid) or {}).get("type") or "comics"


def _fav_hint(kind: str, iid: str) -> dict:
    if kind == "book":
        b = lib.get(iid)
        return {"file": b["file"], "size": b["size"]} if b else {}
    return {"files": sorted({b["file"] for b in lib.series_books(iid)})[:60]}


def _fav_check(kind: str, iid: str):
    """The item exists, belongs to the signed-in account and is the right kind for its library."""
    if kind == "series":
        own_series(iid)
        books = lib.series_books(iid)
        if not books:
            raise HTTPException(400, "That series is empty")
    elif kind == "book":
        b = book_or_404(iid)
        if _lib_type(b["library"]) != "cosplay":
            raise HTTPException(400, "Favourite the whole series instead of a single chapter")
        # Cosplay: a whole set or a single variant — both are fine
    else:
        raise HTTPException(400, "Unknown item kind")


def _fav_heal(items: list) -> bool:
    """Re-attach items whose id no longer exists, using their hint. Returns True when something changed."""
    owned = mine()
    books = [b for b in lib.books.values() if b["library"] in owned]
    series_files: dict[str, set] = {}
    for b in books:
        series_files.setdefault(b["seriesId"], set()).add(b["file"])
    changed = False
    for it in items:
        h = it.get("hint") or {}
        if it["kind"] == "book" and not lib.get(it["id"]) and h.get("file"):
            m = next((b for b in books if b["file"] == h["file"] and b["size"] == h.get("size")), None)
            if m and _lib_type(m["library"]) == "cosplay":
                it["id"], changed = m["id"], True
        elif it["kind"] == "series" and it["id"] not in series_files and h.get("files"):
            want = set(h["files"])
            best = max(series_files.items(), key=lambda kv: len(kv[1] & want), default=(None, set()))
            if best[0] and len(best[1] & want) >= max(1, len(want) // 2):
                it["id"], it["hint"], changed = best[0], {"files": sorted(best[1])[:60]}, True
    return changed


def _my_favs() -> list:
    return [dict(x, items=list(x.get("items", []))) for x in favs.all().get(me()["id"], [])]


def _save_favs(lists: list):
    favs.put(me()["id"], lists)


def _fav_or_404(lists: list, fid: str) -> dict:
    f = next((x for x in lists if x["id"] == fid), None)
    if not f:
        raise HTTPException(404, "favourites list not found")
    return f


# ---- per-series view settings: reading direction, layout, order, reader mode, fit — per account, on the server,
# so they follow you from one device to the next (they used to live in each browser's localStorage)
series_prefs = Store(Db.at(CONFIG_DIR / "reader.db"), "series_prefs")      # {account id: {series id: {key: value}}}
SERIES_PREF_KEYS = {"rtl": bool, "view": str, "sort": str, "mode": str, "fit": str}


def _clean_pref(p) -> dict:
    if not isinstance(p, dict):
        return {}
    return {k: v for k, v in p.items() if k in SERIES_PREF_KEYS and isinstance(v, SERIES_PREF_KEYS[k])
            and (not isinstance(v, str) or 0 < len(v) <= 20)}


@app.get("/api/prefs/series")
def get_series_prefs():
    return series_prefs.get(me()["id"]) or {}


@app.put("/api/prefs/series")
def put_series_prefs(body: dict = Body(...)):
    """{series id: {key: value} | null}: each named series' settings replaced as a whole (null / {} = forgotten).
    (Settings of a series that's gone stay behind — a few bytes, and a drive that's only unplugged comes back.)"""
    uid = me()["id"]
    cur = dict(series_prefs.get(uid) or {})
    for sid, p in list(body.items())[:2000]:
        p = _clean_pref(p)
        if p and sid and len(sid) <= 64:
            cur[sid] = p
        else:
            cur.pop(sid, None)
    series_prefs.put(uid, cur)
    return cur


@app.get("/api/favorites")
def favorites():
    lists = _my_favs()
    healed = False
    if lib.books:                                  # never "heal" against an empty index (first scan running)
        for f in lists:
            healed = _fav_heal(f["items"]) or healed
    if healed:
        _save_favs(lists)
    return [{"id": f["id"], "name": f["name"], "created": f.get("created"),
             "items": [{"kind": i["kind"], "id": i["id"], "added": i.get("added")} for i in f["items"]]} for f in lists]


@app.post("/api/favorites")
def favorites_create(body: dict = Body(...)):
    name = " ".join(str(body.get("name") or "").split())[:80]
    if not name:
        raise HTTPException(400, "Give the list a name")
    lists = _my_favs()
    if any(x["name"].lower() == name.lower() for x in lists):
        raise HTTPException(400, f"You already have a list called {name}")
    f = {"id": _uuid.uuid4().hex[:12], "name": name, "created": int(time.time()), "items": []}
    _save_favs(lists + [f])
    return {"id": f["id"], "name": name, "created": f["created"], "items": []}


@app.patch("/api/favorites/{fid}")
def favorites_rename(fid: str, body: dict = Body(...)):
    name = " ".join(str(body.get("name") or "").split())[:80]
    if not name:
        raise HTTPException(400, "Give the list a name")
    lists = _my_favs()
    if any(x["name"].lower() == name.lower() and x["id"] != fid for x in lists):
        raise HTTPException(400, f"You already have a list called {name}")
    _fav_or_404(lists, fid)["name"] = name
    _save_favs(lists)
    return {"ok": True}


@app.delete("/api/favorites/{fid}")
def favorites_delete(fid: str):
    """Deletes the list only — the series and sets in it stay where they are."""
    lists = _my_favs()
    _fav_or_404(lists, fid)
    _save_favs([x for x in lists if x["id"] != fid])
    return {"ok": True}


@app.post("/api/favorites/{fid}/items")
def favorites_add(fid: str, body: dict = Body(...)):
    kind, iid = str(body.get("kind") or ""), str(body.get("id") or "")
    _fav_check(kind, iid)
    lists = _my_favs()
    f = _fav_or_404(lists, fid)
    if not any(i["kind"] == kind and i["id"] == iid for i in f["items"]):
        f["items"].append({"kind": kind, "id": iid, "added": int(time.time()), "hint": _fav_hint(kind, iid)})
        _save_favs(lists)
    return {"ok": True}


@app.delete("/api/favorites/{fid}/items/{kind}/{iid}")
def favorites_remove(fid: str, kind: str, iid: str):
    lists = _my_favs()
    f = _fav_or_404(lists, fid)
    f["items"] = [i for i in f["items"] if not (i["kind"] == kind and i["id"] == iid)]
    _save_favs(lists)
    return {"ok": True}


# ------------------------------------------------------------------ progress
@app.get("/api/progress")
def progress_all():
    ids = mine()
    return {k: v for k, v in lib.progress.all().items() if (b := lib.books.get(k)) and b["library"] in ids}


@app.put("/api/progress/{bid}")
def progress_put(bid: str, body: dict = Body(...)):
    book_or_404(bid)
    allowed = {k: body[k] for k in ("page", "chapter", "scroll", "frac", "done", "updated", "seen") if k in body}
    if (old := lib.progress.get(bid)) and old.get("seen"):
        allowed["seen"] = True                     # once opened / read, never "new" again
    lib.progress.put(bid, allowed)
    return allowed


@app.delete("/api/progress/{bid}")
def progress_delete(bid: str):
    book_or_404(bid)
    lib.progress.delete(bid)
    return {"ok": True}


# ------------------------------------------------------------------ accounts
def _with_session(a: dict, payload: dict, request: Request) -> JSONResponse:
    r = JSONResponse(payload)
    r.set_cookie(COOKIE, accounts.token(a), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                 secure=request.url.scheme == "https", path="/")
    return r


@app.get("/api/auth/state")
def auth_state(request: Request):
    a = accounts.from_token(request.cookies.get(COOKIE))
    return {"setup": not accounts.items, "user": accounts.public(a) if a else None, "version": __version__}


@app.post("/api/auth/setup")
def auth_setup(request: Request, body: dict = Body(...)):
    with accounts.lock:
        if accounts.items:
            return JSONResponse({"detail": "The first account already exists — sign in instead", "setup": False}, status_code=409)
        try:
            a = accounts.create(body.get("email", ""), body.get("password", ""), admin=True)
        except ValueError as e:
            raise HTTPException(400, str(e))
    lib.claim_orphans(a)
    lib.discover()
    _scan_soon()
    return _with_session(a, {"user": accounts.public(a)}, request)


@app.post("/api/auth/login")
async def auth_login(request: Request, body: dict = Body(...)):
    if not accounts.items:                       # nothing to sign in to yet: the page should show first-run setup
        return JSONResponse({"detail": "No account exists yet — create the first one", "setup": True}, status_code=409)
    a = await asyncio.to_thread(accounts.verify, body.get("email", ""), body.get("password", ""))
    if not a:
        await asyncio.sleep(0.8)
        raise HTTPException(401, "Wrong e-mail or password")
    return _with_session(a, {"user": accounts.public(a)}, request)


@app.post("/api/auth/logout")
def auth_logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE, path="/")
    return r


@app.post("/api/auth/password")
def auth_password(request: Request, body: dict = Body(...)):
    u = accounts.from_token(request.cookies.get(COOKIE))
    if not u:
        raise HTTPException(401, "Please sign in")
    if not accounts.verify(u["email"], body.get("current", "")):
        raise HTTPException(400, "Your current password isn't right")
    try:
        accounts.set_password(u["id"], body.get("password", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _with_session(accounts.get(u["id"]), {"ok": True}, request)   # stay signed in here; other devices are signed out


def admin() -> dict:
    u = me()
    if not u.get("admin"):
        raise HTTPException(403, "Only the admin can manage accounts")
    return u


@app.get("/api/accounts")
def accounts_list():
    admin()
    out = []
    for a in accounts.items:
        libs = lib.owned(a["id"])
        out.append({**accounts.public(a), "libraries": len(libs), "books": sum(1 for b in lib.books.values() if b["library"] in libs)})
    return {"accounts": out}


@app.post("/api/accounts")
def accounts_create(body: dict = Body(...)):
    admin()
    try:
        a = accounts.create(body.get("email", ""), body.get("password", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    (LIB_ROOT / a["folder"]).mkdir(parents=True, exist_ok=True)
    return accounts.public(a)


@app.delete("/api/accounts/{uid}")
def accounts_delete(uid: str, files: bool = False):
    admin()
    try:
        a = accounts.delete(uid)
    except KeyError:
        raise HTTPException(404, "account not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    lib.forget_owner(a["id"], a["folder"], files)
    favs.delete(a["id"])
    return {"ok": True}


@app.post("/api/accounts/{uid}/admin")
def accounts_make_admin(uid: str):
    u = admin()
    try:
        accounts.transfer_admin(u["id"], uid)
    except KeyError:
        raise HTTPException(404, "account not found")
    return {"ok": True}


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/auth/"):
        a = accounts.from_token(request.cookies.get(COOKIE))
        if not a:
            return JSONResponse({"detail": "Please sign in"}, status_code=401)
        token = _user.set(a)
        try:
            return await call_next(request)
        finally:
            _user.reset(token)
    return await call_next(request)


# Always serve the current UI: index.html is never cached, and it references
# js/*.js / app.css with ?v=<version> so a rebuilt container can't run stale code.
@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def index():
    return Response(front()[1], media_type="text/html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.middleware("http")
async def no_stale_assets(request: Request, call_next):
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
