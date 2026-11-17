"""✨ Optimize: convert the pages of books to AVIF in the background.

Every current browser shows AVIF directly and it is typically much smaller than JPEG / PNG at the same look.
Safety first — a book is never left half-done:
  1. the converted book is written next to the original under a temporary name,
  2. every converted page is decoded again and the page count compared,
  3. the original is copied to /config/originals (unless asked not to keep it) and only then swapped out.
The file keeps its name, so the book keeps its id, reading progress, favourites and chosen cover.
Undo puts the kept original back; kept originals are deleted after OPTIMIZE_KEEP_DAYS.

Jobs live in the database, so a restart continues where it stopped. One worker thread runs them, at low
priority, converting a couple of pages at a time so reading stays smooth.
"""
from __future__ import annotations

import io
import json
import os
import secrets
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

from . import library as L
from .store import Store

log = L.log
KEEP_DAYS = float(os.environ.get("OPTIMIZE_KEEP_DAYS", "14"))
THREADS = max(1, min(2, (os.cpu_count() or 2) - 1))       # pages converted at once
NEVER = (".gif", ".avif", ".svg")                           # GIF may be animated; AVIF is already the target
SUPPORTED_SRC = ("cbz", "zip", "folder")

# "Default" is built in and can't be deleted — the baseline to compare everything else with. Your own presets
# (made in the Optimize dialog) are kept in optimize-presets.json in the config folder.
DEFAULT_PRESET = {"id": "default", "name": "Default", "quality": 70, "speed": 6, "subsampling": "auto",
                  "grayscale": True, "builtin": True}
PRESET_KEYS = {"id", "name", "hint", "quality", "speed", "subsampling", "grayscale"}


class Cancelled(Exception):
    pass


def _low_priority():
    try:                                                   # Linux: this thread only, not the whole server
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except (AttributeError, OSError):
        pass


def _is_gray(im: Image.Image) -> bool:
    """A black-and-white page saved as colour (most scans): the channels agree everywhere."""
    import numpy as np
    small = im.convert("RGB").resize((96, 96), Image.BILINEAR)
    a = np.asarray(small, dtype=np.int16)
    spread = a.max(axis=2) - a.min(axis=2)
    return float(np.percentile(spread, 99.5)) <= 10


def encode_page(data: bytes, name: str, preset: dict, libtype: str, max_edge: int = 0) -> bytes | None:
    """One page as AVIF, or None when the original should stay (a video, an animation, already AVIF,
    or the AVIF would not be smaller)."""
    low = name.lower()
    if L.is_video(name) or low.endswith(NEVER):
        return None
    with Image.open(io.BytesIO(data)) as src:
        if getattr(src, "n_frames", 1) > 1:                # animated WebP / PNG: leave alone
            return None
        icc = src.info.get("icc_profile")
        im = ImageOps.exif_transpose(src)                  # bake in "rotate me": AVIF gets no EXIF
        alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if alpha else "RGB")
        resized = False
        if max_edge and max(im.size) > max_edge:
            im.thumbnail((max_edge, max_edge), Image.LANCZOS)
            resized = True
        sub = preset.get("subsampling") or "auto"
        if sub == "auto":                                  # line art keeps full colour detail; photos don't need it
            sub = "4:2:0" if libtype == "cosplay" else "4:4:4"
        if preset.get("grayscale", True) and not alpha and _is_gray(im):
            im, sub = im.convert("L"), "4:0:0"
        kw = {"quality": int(preset.get("quality", 70)), "speed": int(preset.get("speed", 6)), "subsampling": sub}
        if icc and im.mode != "L":
            kw["icc_profile"] = icc
        buf = io.BytesIO()
        im.save(buf, "AVIF", **kw)
    out = buf.getvalue()
    if len(out) >= len(data) and not resized:            # no gain: this page keeps its original
        return None
    return out


def _avif_name(name: str) -> str:
    stem, _ = os.path.splitext(name)
    return stem + ".avif"


def _verify(data: bytes):
    with Image.open(io.BytesIO(data)) as im:
        im.load()


class Optimizer:
    def __init__(self, lib):
        self.lib = lib
        self.jobs = Store(lib.db, "optimize_jobs")         # job id → job
        self.kept = Store(lib.db, "optimized")             # book id → what was done, and where the original is
        self.seen = Store(lib.db, "optimize_seen")         # book id → looked at by auto-optimize (once is enough)
        self.settings = Store(lib.db, "optimize_settings")  # "schedule" → night-only hours
        self.cv = threading.Condition()
        self.live: dict[str, dict] = {}                    # job id → progress of the book being converted
        self._ratio_cache: dict = {}
        self._last_cleanup = 0.0
        for jid, j in self.jobs.all().items():             # a restart: whatever was running continues
            if j.get("state") == "running":
                j["state"] = "queued"
                self.jobs.put(jid, j)

    # ---- presets
    @property
    def presets_file(self) -> Path:
        return L.CONFIG_DIR / "optimize-presets.json"

    def _own(self) -> list[dict]:
        """The presets made in the dialog (or written into the file by hand)."""
        try:
            raw = json.loads(self.presets_file.read_text("utf-8"))
        except FileNotFoundError:
            return []
        except Exception as e:  # noqa: BLE001
            log.warning("optimize-presets.json can't be read (%s) — only the Default preset is offered", e)
            return []
        items = raw.get("presets", raw) if isinstance(raw, dict) else raw
        out, seen = [], {DEFAULT_PRESET["id"]}
        for i, p in enumerate(items if isinstance(items, list) else []):
            if not isinstance(p, dict) or "quality" not in p:
                continue
            p = {k: v for k, v in p.items() if k in PRESET_KEYS}
            p.setdefault("id", f"preset{i + 1}"); p.setdefault("name", p["id"])
            if p["id"] in seen:
                continue
            seen.add(p["id"]); out.append(p)
        return out

    def presets(self) -> list[dict]:
        """Default first, then your own."""
        return [dict(DEFAULT_PRESET)] + self._own()

    def _save_own(self, items: list[dict]):
        f = self.presets_file
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps({"presets": items}, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, f)

    def add_preset(self, name: str, quality, speed) -> dict:
        name = " ".join(str(name or "").split())[:40]
        if not name:
            raise ValueError("Give the preset a name")
        try:
            q, sp = int(quality), int(speed)
        except (TypeError, ValueError):
            raise ValueError("Quality and speed must be numbers")
        if not 0 <= q <= 100 or not 0 <= sp <= 10:
            raise ValueError("Quality goes from 0 to 100, speed from 0 to 10")
        own = self._own()
        if any(p["name"].lower() == name.lower() for p in self.presets()):
            raise ValueError(f"There's already a preset called “{name}”")
        p = {"id": secrets.token_hex(4), "name": name, "quality": q, "speed": sp, "subsampling": "auto", "grayscale": True}
        self._save_own(own + [p])
        return p

    def delete_preset(self, pid: str):
        if pid == DEFAULT_PRESET["id"]:
            raise ValueError("The Default preset can't be deleted")
        own = self._own()
        if not any(p["id"] == pid for p in own):
            raise KeyError(pid)
        self._save_own([p for p in own if p["id"] != pid])

    def preset(self, pid: str) -> dict:
        p = next((p for p in self.presets() if p["id"] == pid), None)
        if not p:
            raise ValueError("Unknown preset")
        return p

    # ---- which books can be converted
    def why_not(self, b: dict) -> str | None:
        if b.get("format") != "images":
            return "not a picture book"
        if b.get("src") not in SUPPORTED_SRC:
            return "this archive type isn't supported yet (only .cbz, .zip and photo folders)"
        if (self.lib.trash.get(b["id"]) or {}).get("at"):
            return "in the trash"
        pages = [n for n in b.get("entries") or [] if not L.is_video(n) and not n.lower().endswith(NEVER)]
        if not pages:
            return "already AVIF" if any(n.lower().endswith(".avif") for n in b.get("entries") or []) else "no photos to convert"
        return None

    def libtype(self, b: dict) -> str:
        return (self.lib.get_library(b["library"]) or {}).get("type") or "comics"

    def size(self, b: dict) -> int:
        p = L.LIB_ROOT / b["rel"]
        try:
            if p.is_dir():
                return sum(f.stat().st_size for f in p.iterdir() if f.is_file())
            return p.stat().st_size
        except OSError:
            return 0

    # ---- one book
    def convert(self, b: dict, preset: dict, keep: bool, max_edge: int, progress=None, stop=None) -> dict:
        """Convert one book. Returns {"before", "after", "pages", "converted"}; raises Cancelled when stopped.
        Nothing in the library changes unless the whole book converted and checked out."""
        stop = stop or (lambda: False)
        progress = progress or (lambda done, total: None)
        why = self.why_not(b)
        if why:
            raise ValueError(why)
        ltype = self.libtype(b)
        if b["src"] == "folder":
            return self._convert_folder(b, preset, keep, max_edge, ltype, progress, stop)
        return self._convert_archive(b, preset, keep, max_edge, ltype, progress, stop)

    def _pages_parallel(self, items, work, progress, stop):
        """Run work(item) over items a few at a time, in order; stop between batches when asked."""
        out, total = [], len(items)
        with ThreadPoolExecutor(THREADS, initializer=_low_priority) as pool:
            for i in range(0, total, THREADS * 2):
                if stop():
                    raise Cancelled()
                out.extend(pool.map(work, items[i:i + THREADS * 2]))
                progress(min(i + THREADS * 2, total), total)
        return out

    def _backup_dir(self, b: dict) -> Path:
        d = L.CONFIG_DIR / "originals" / f"{b['id']}-{int(time.time())}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _convert_archive(self, b, preset, keep, max_edge, ltype, progress, stop) -> dict:
        src = L.LIB_ROOT / b["rel"]
        before = src.stat().st_size
        tmp = src.with_name(f".{src.name}.optimizing")
        converted = 0
        try:
            with zipfile.ZipFile(src) as zin:
                infos = zin.infolist()
                names = {i.filename.lower() for i in infos}
                media = [i for i in infos if not i.is_dir() and i.filename.lower().endswith(L.IMG_EXT)
                         and "__MACOSX" not in i.filename]

                lock = threading.Lock()                    # zipfile reads aren't thread-safe on one handle
                def locked(info):
                    with lock:
                        data = zin.read(info.filename)
                    target = _avif_name(info.filename)
                    if target.lower() in names and target.lower() != info.filename.lower():
                        return None
                    try:
                        return encode_page(data, info.filename, preset, ltype, max_edge)
                    except Exception as e:  # noqa: BLE001
                        log.warning("optimize %s: %s stays as it is (%s)", b["rel"], info.filename, e)
                        return None

                results = dict(zip((i.filename for i in media), self._pages_parallel(media, locked, progress, stop)))
                if stop():
                    raise Cancelled()
                with zipfile.ZipFile(tmp, "w", allowZip64=True) as zout:
                    for info in infos:
                        new = results.get(info.filename)
                        if new is not None:
                            zi = zipfile.ZipInfo(_avif_name(info.filename), date_time=info.date_time)
                            zi.compress_type = zipfile.ZIP_STORED      # AVIF is compressed already
                            zout.writestr(zi, new)
                            converted += 1
                        elif info.is_dir():
                            zout.writestr(info, b"")
                        else:
                            with zin.open(info) as fi, zout.open(info, "w", force_zip64=info.file_size > 0x7FFFFFFF) as fo:
                                shutil.copyfileobj(fi, fo, 1 << 20)
            # check: same number of pages, every converted page decodes
            with zipfile.ZipFile(tmp) as z:
                got = [n for n in z.namelist() if n.lower().endswith(L.MEDIA_EXT) and "__MACOSX" not in n]
                if len(got) != len([i for i in infos if i.filename.lower().endswith(L.MEDIA_EXT) and "__MACOSX" not in i.filename]):
                    raise RuntimeError("page count changed — not swapped in")
                for name, new in results.items():
                    if new is not None:
                        _verify(z.read(_avif_name(name)))
            after = tmp.stat().st_size
            if not converted or after >= before:
                tmp.unlink(missing_ok=True)
                return {"before": before, "after": before, "pages": len(media), "converted": 0}
            backup = None
            if keep:
                backup = self._backup_dir(b) / src.name
                shutil.copy2(src, backup)                  # /config is usually another drive: copy, not move
            with self.lib._busy:
                self.lib._stale(src, src.parent)
                self.lib._swap_in(tmp, src, b["rel"])
            self.kept.put(b["id"], {"kind": "archive", "backup": str(backup.relative_to(L.CONFIG_DIR)) if backup else None,
                                    "name": src.name, "at": int(time.time()), "before": before, "after": after,
                                    "preset": preset.get("id"), "pages": converted})
            self.lib.scan()
            return {"before": before, "after": after, "pages": len(media), "converted": converted}
        finally:
            tmp.unlink(missing_ok=True)

    def _convert_folder(self, b, preset, keep, max_edge, ltype, progress, stop) -> dict:
        folder = L.LIB_ROOT / b["rel"]
        files = [f for f in sorted(folder.iterdir()) if f.is_file() and f.name.lower().endswith(L.IMG_EXT)]
        before = self.size(b)
        names = {f.name.lower() for f in folder.iterdir()}

        def work(f: Path):
            target = _avif_name(f.name)
            if target.lower() in names and target.lower() != f.name.lower():
                return None
            try:
                return encode_page(f.read_bytes(), f.name, preset, ltype, max_edge)
            except Exception as e:  # noqa: BLE001
                log.warning("optimize %s: %s stays as it is (%s)", b["rel"], f.name, e)
                return None

        results = self._pages_parallel(files, work, progress, stop)
        todo = [(f, data) for f, data in zip(files, results) if data is not None]
        if not todo or stop():
            if stop():
                raise Cancelled()
            return {"before": before, "after": before, "pages": len(files), "converted": 0}
        parts = []
        try:
            for f, data in todo:                           # written under temporary names, then checked
                _verify(data)
                p = f.with_name(f".{_avif_name(f.name)}.part"); p.write_bytes(data); parts.append((f, p))
            backup = self._backup_dir(b) if keep else None
            if backup:
                for f, _ in parts:
                    shutil.copy2(f, backup / f.name)
            done, originals = [], []
            with self.lib._busy:
                for f, p in parts:
                    final = f.with_name(_avif_name(f.name))
                    os.replace(p, final)
                    try:
                        self.lib._retry(f.unlink)
                    except OSError:                         # locked on Windows: keep the original page instead
                        final.unlink(missing_ok=True)
                        continue
                    done.append(final.name); originals.append(f.name)
                self.lib._stale(folder)
        finally:
            for _, p in parts:
                p.unlink(missing_ok=True)
        after = self.size(b)
        self.kept.put(b["id"], {"kind": "folder", "backup": str(backup.relative_to(L.CONFIG_DIR)) if backup else None,
                                "written": done, "originals": originals, "at": int(time.time()),
                                "before": before, "after": after, "preset": preset.get("id"), "pages": len(done)})
        self.lib.scan()
        return {"before": before, "after": after, "pages": len(files), "converted": len(done)}

    # ---- undo / clean-up
    def can_undo(self, bid: str) -> bool:
        k = self.kept.get(bid)
        return bool(k and k.get("backup") and (L.CONFIG_DIR / k["backup"]).exists())

    def undo(self, bid: str):
        """Put the kept original back."""
        k, b = self.kept.get(bid), self.lib.get(bid)
        if not b:
            raise KeyError(bid)
        if not k or not k.get("backup") or not (L.CONFIG_DIR / k["backup"]).exists():
            raise ValueError("The original isn't kept any more")
        backup = L.CONFIG_DIR / k["backup"]
        here = L.LIB_ROOT / b["rel"]
        if k["kind"] == "archive":
            tmp = here.with_name(f".{here.name}.restoring")
            shutil.copy2(backup, tmp)
            with self.lib._busy:
                self.lib._stale(here, here.parent)
                self.lib._swap_in(tmp, here, b["rel"])
            shutil.rmtree(backup.parent, ignore_errors=True)
        else:
            with self.lib._busy:
                for n in k.get("originals") or []:
                    shutil.copy2(backup / n, here / n)
                for n in k.get("written") or []:
                    if n not in (k.get("originals") or []):
                        try:
                            self.lib._retry((here / n).unlink)
                        except FileNotFoundError:
                            pass
                self.lib._stale(here)
            shutil.rmtree(backup, ignore_errors=True)
        self.kept.delete(bid)
        self.lib.scan()

    def cleanup(self, now: float | None = None):
        """Kept originals older than KEEP_DAYS are deleted (the conversion stays)."""
        now = now or time.time()
        for bid, k in self.kept.all().items():
            if k.get("backup") and now - k.get("at", now) > KEEP_DAYS * 86400:
                p = L.CONFIG_DIR / k["backup"]
                shutil.rmtree(p.parent if k["kind"] == "archive" else p, ignore_errors=True)
                self.kept.put(bid, {**k, "backup": None})

    # ---- estimates and the compare view
    def sample_pages(self, books: list[dict], n: int = 4) -> list[tuple[dict, int]]:
        """A few pages spread over the selection (the biggest books first)."""
        cands = []
        for b in sorted(books, key=lambda b: -self.size(b))[:n]:
            pages = [i for i, e in enumerate(b.get("entries") or []) if not L.is_video(e) and not e.lower().endswith(NEVER)]
            if pages:
                cands.append((b, pages[len(pages) // 2]))
        i = 0
        while len(cands) < n and books:                    # few books: more pages of the first
            b = books[0]
            pages = [k for k, e in enumerate(b.get("entries") or []) if not L.is_video(e) and not e.lower().endswith(NEVER)]
            if not pages or i >= len(pages):
                break
            if (b, pages[i]) not in cands:
                cands.append((b, pages[i]))
            i += max(1, len(pages) // n)
        return cands[:n]

    def encode_sample(self, b: dict, n: int, preset: dict, max_edge: int) -> tuple[bytes, bytes]:
        """(original, avif) of one page — the avif cached, for the compare view."""
        name = b["entries"][n]
        f = L.CONFIG_DIR / "cache" / "compare" / f"{b['id']}-{b['mtime']}-{n}-{preset.get('quality')}-{preset.get('speed')}-{preset.get('subsampling')}-{max_edge}.avif"
        orig = self.lib.read(b, name)
        if f.exists():
            return orig, f.read_bytes()
        new = encode_page(orig, name, {**preset, "speed": max(int(preset.get("speed", 6)), 6)}, self.libtype(b), max_edge)
        new = new if new is not None else orig
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(new)
        return orig, new

    def estimate(self, books: list[dict], preset: dict, max_edge: int) -> dict:
        ok = [b for b in books if not self.why_not(b)]
        total = sum(self.size(b) for b in ok)
        key = (tuple(sorted(b["id"] + str(b["mtime"]) for b in ok)), preset.get("quality"), preset.get("speed"), preset.get("subsampling"), max_edge)
        if key not in self._ratio_cache:
            before = after = 0
            for b, n in self.sample_pages(ok):
                try:
                    o, a = self.encode_sample(b, n, preset, max_edge)
                except Exception:  # noqa: BLE001
                    continue
                before += len(o); after += min(len(a), len(o))
            self._ratio_cache[key] = after / before if before else 1.0
        ratio = self._ratio_cache[key]
        return {"books": len(ok), "skipped": len(books) - len(ok), "before": total, "after": int(total * ratio),
                "pages": sum(len(b.get("entries") or []) for b in ok)}

    # ---- the job queue
    def start(self, owner: str, books: list[dict], preset_id: str, keep: bool, max_edge: int, title: str, preset: dict | None = None) -> dict:
        preset = preset or self.preset(preset_id)
        ok = [b for b in books if not self.why_not(b)]
        if not ok:
            raise ValueError("Nothing here can be optimized: " + (self.why_not(books[0]) if books else "nothing selected"))
        jid = secrets.token_hex(5)
        job = {"id": jid, "owner": owner, "title": title, "preset": preset["id"], "presetName": preset.get("name"),
               "settings": {k: v for k, v in preset.items() if k != "builtin"},
               "keep": bool(keep), "maxEdge": int(max_edge or 0), "books": [b["id"] for b in ok],
               "done": [], "skipped": [], "failed": [], "state": "queued", "created": time.time(),
               "before": 0, "after": 0, "pagesTotal": sum(len(b.get("entries") or []) for b in ok), "pagesDone": 0}
        self.jobs.put(jid, job)
        with self.cv:
            self.cv.notify_all()
        return job

    # ---- night-only: jobs wait outside the chosen hours (unless started with "Run now")
    def schedule(self) -> dict:
        return {"on": False, "from": 1, "to": 7, "tz": "", "offset": 0, **(self.settings.get("schedule") or {})}

    def set_schedule(self, on, start, end, tz: str = "", offset: int = 0) -> dict:
        start, end = int(start), int(end)
        if not (0 <= start <= 23 and 0 <= end <= 23) or start == end:
            raise ValueError("Pick two different hours between 0 and 23")
        sch = {"on": bool(on), "from": start, "to": end, "tz": str(tz or "")[:60], "offset": int(offset or 0)}
        self.settings.put("schedule", sch)
        with self.cv:
            self.cv.notify_all()
        return sch

    def allowed(self, now: float | None = None) -> bool:
        sch = self.schedule()
        if not sch["on"]:
            return True
        now = now or time.time()
        try:                                               # the hours are meant in the owner's time zone
            from zoneinfo import ZoneInfo
            import datetime as _dt
            hour = _dt.datetime.fromtimestamp(now, ZoneInfo(sch["tz"])).hour
        except Exception:  # noqa: BLE001 — no zone data in the container: the offset the browser reported
            hour = int(((now + sch["offset"] * 60) % 86400) // 3600)
        a, b = sch["from"], sch["to"]
        return a <= hour < b if a < b else (hour >= a or hour < b)

    # ---- the Storage page
    def storage(self, owner: str) -> dict:
        libs, series = [], {}
        for l in self.lib.libraries:
            if l.get("owner") != owner:
                continue
            row = {"id": l["id"], "books": 0, "bytes": 0, "optimized": 0, "saved": 0, "convertible": 0, "convertibleBytes": 0}
            for b in self.lib.books.values():
                if b["library"] != l["id"]:
                    continue
                size = self.size(b)
                row["books"] += 1; row["bytes"] += size
                k = self.kept.get(b["id"])
                if k:
                    row["optimized"] += 1
                    row["saved"] += max(0, (k.get("before") or 0) - (k.get("after") or 0))
                elif not self.why_not(b):
                    row["convertible"] += 1; row["convertibleBytes"] += size
                    s = series.setdefault(b["seriesId"], {"id": b["seriesId"], "bytes": 0, "books": 0})
                    s["bytes"] += size; s["books"] += 1
            libs.append(row)
        mine = {l["id"] for l in libs}
        kept = [(bid, k) for bid, k in self.kept.all().items()
                if k.get("backup") and (self.lib.get(bid) or {}).get("library") in mine and (L.CONFIG_DIR / k["backup"]).exists()]
        return {"libraries": libs, "biggest": sorted(series.values(), key=lambda s: -s["bytes"])[:20],
                "kept": {"books": len(kept), "bytes": sum(k.get("before") or 0 for _, k in kept), "days": KEEP_DAYS},
                "schedule": self.schedule(), "allowed": self.allowed()}

    def drop_originals(self, owner: str) -> int:
        """Delete the kept originals of this account's books now (the conversions stay; Undo is gone)."""
        mine = {l["id"] for l in self.lib.libraries if l.get("owner") == owner}
        n = 0
        for bid, k in self.kept.all().items():
            if not k.get("backup") or (self.lib.get(bid) or {}).get("library") not in mine:
                continue
            p = L.CONFIG_DIR / k["backup"]
            shutil.rmtree(p.parent if k["kind"] == "archive" else p, ignore_errors=True)
            self.kept.put(bid, {**k, "backup": None})
            n += 1
        return n

    # ---- auto-optimize: libraries with a preset chosen convert whatever is added from then on
    def collect_auto(self, now: float | None = None) -> int:
        """Queue new books of libraries that have auto-optimize on. Each book is queued once (also when it
        turned out not to shrink), a moment after it arrived so a batch upload becomes one job."""
        now = now or time.time()
        queued = 0
        for l in self.lib.libraries:
            pid, since = l.get("autoOptimize"), l.get("autoSince") or 0
            if not pid:
                continue
            fresh = [b for b in self.lib.books.values()
                     if b["library"] == l["id"] and (b.get("added") or 0) >= since and now - (b.get("added") or 0) >= 20
                     and not self.seen.get(b["id"]) and not self.kept.get(b["id"])]
            for b in fresh:
                self.seen.put(b["id"], {"at": int(now)})
            fresh = [b for b in fresh if not self.why_not(b)]
            if not fresh:
                continue
            try:
                preset = self.preset(pid)
            except ValueError:                             # the chosen preset was deleted: the baseline
                preset = dict(DEFAULT_PRESET)
            owner = l.get("owner") or ""
            job = next((j for j in self.jobs.all().values() if j.get("auto") == l["id"] and j["state"] in ("queued", "running")), None)
            if job:                                        # more arrived while it runs: the same job grows
                job["books"] += [b["id"] for b in fresh if b["id"] not in job["books"]]
                job["pagesTotal"] += sum(len(b.get("entries") or []) for b in fresh)
                self.jobs.put(job["id"], job)
            else:
                for jid, j in self.jobs.all().items():     # one finished "new uploads" line per library is enough
                    if j.get("auto") == l["id"] and j["state"] == "done":
                        self.jobs.delete(jid)
                job = self.start(owner, fresh, preset["id"], True, 0, f"New in {l['name']}", preset=preset)
                job["auto"] = l["id"]
                self.jobs.put(job["id"], job)
            queued += len(fresh)
        return queued

    def list(self, owner: str) -> list[dict]:
        out = []
        for j in sorted(self.jobs.all().values(), key=lambda j: j["created"]):
            if j["owner"] != owner:
                continue
            live = self.live.get(j["id"]) or {}
            out.append({**{k: v for k, v in j.items() if k != "owner"}, "current": live or None,
                        "waiting": j["state"] in ("queued", "running") and not live and not j.get("now") and not self.allowed(),
                        "pagesDone": j["pagesDone"] + live.get("done", 0)})
        return out

    def control(self, owner: str, jid: str, action: str):
        j = self.jobs.get(jid)
        if not j or j["owner"] != owner:
            raise KeyError(jid)
        if action == "pause" and j["state"] in ("queued", "running"):
            j["state"] = "paused"
        elif action == "resume" and j["state"] == "paused":
            j["state"] = "queued"
        elif action == "cancel" and j["state"] in ("queued", "running", "paused"):
            j["state"] = "cancelled"; j["finished"] = time.time()
        elif action == "now" and j["state"] in ("queued", "running"):
            j["now"] = True                                # ignore the night-only hours for this job
        elif action == "dismiss" and j["state"] in ("done", "cancelled"):
            self.jobs.delete(jid)
            return
        else:
            return
        self.jobs.put(jid, j)
        with self.cv:
            self.cv.notify_all()

    def _next(self):
        jobs = sorted(self.jobs.all().values(), key=lambda j: j["created"])
        ok = self.allowed()
        return next((j for j in jobs if j["state"] in ("queued", "running") and (ok or j.get("now"))), None)

    def step(self) -> bool:
        """Run one book of the oldest waiting job. False when there's nothing to do."""
        job = self._next()
        if not job:
            return False
        jid = job["id"]
        job["state"] = "running"; job.setdefault("started", time.time())
        self.jobs.put(jid, job)
        left = [i for i in job["books"] if i not in job["done"]
                and i not in {s["id"] for s in job["skipped"]} and i not in {f["id"] for f in job["failed"]}]
        if not left:
            job["state"] = "done"; job["finished"] = time.time()
            self.jobs.put(jid, job)
            return True
        bid = left[0]
        b = self.lib.get(bid)
        stop = lambda: (self.jobs.get(jid) or {}).get("state") not in ("running",)
        if not b or self.why_not(b):
            job["skipped"].append({"id": bid, "why": "gone" if not b else self.why_not(b)})
            self.jobs.put(jid, job)
            return True
        self.live[jid] = {"id": bid, "label": f"{b['series']} · {b['label']}", "done": 0, "pages": len(b.get("entries") or [])}

        def progress(done, total):
            self.live[jid] = {**self.live[jid], "done": done, "pages": total}
        preset = job.get("settings") or {**DEFAULT_PRESET, "id": job["preset"]}
        try:
            r = self.convert(b, preset, job["keep"], job["maxEdge"], progress, stop)
            job = self.jobs.get(jid)
            job["done"].append(bid)
            job["before"] += r["before"]; job["after"] += r["after"]
            if not r["converted"]:
                job["skipped"].append({"id": bid, "why": "already as small as it gets"}); job["done"].remove(bid)
        except Cancelled:
            job = self.jobs.get(jid)                       # paused or cancelled: this book starts over later
        except Exception as e:  # noqa: BLE001
            log.warning("optimize %s failed: %s", b["rel"], e)
            job = self.jobs.get(jid)
            job["failed"].append({"id": bid, "why": str(e)[:200]})
        finally:
            self.live.pop(jid, None)
        job["pagesDone"] = sum(len((self.lib.get(i) or {}).get("entries") or []) for i in job["done"])
        self.jobs.put(jid, job)
        return True

    def loop(self):
        _low_priority()
        while True:
            try:
                self.collect_auto()
                worked = self.step()
                if time.time() - self._last_cleanup > 3600:
                    self._last_cleanup = time.time()
                    self.cleanup()
            except Exception as e:  # noqa: BLE001
                log.warning("optimizer: %s", e)
                worked = False
            if not worked:
                with self.cv:                              # (auto-optimize looks for new uploads more often)
                    self.cv.wait(8 if any(l.get("autoOptimize") for l in self.lib.libraries) else 30)
