"""Files and folders: upload targets, collections and empty series, renames, moves, merges, deletes,
Windows-lock retries, the Cosplay tidy and the empty-folder clean-up.

Part of the Library class (library.py: class Library(…, FilesMixin, …)) — methods and attributes unchanged; LIB_ROOT,
CONFIG_DIR and EMPTY_FOLDER_AFTER are read from library.py at call time (_L.…) so tests can swap them."""
from __future__ import annotations

import os
import posixpath
import shutil
import time

from pathlib import Path

from . import library as _L
from .jobs import step as job_step
from .library import BOOK_EXT, COL_MARK, JUNK_FILES, MEDIA_EXT, REPACK_EXT, SQUARE, VIDEO_EXT, _remove, collection_key, cosplay_name, joins_existing, log, parse_number, safe_component, safe_rel, same_case, series_key, sibling_works, strip_brackets, tidy, variant_groups


class FilesMixin:
    # ---- uploads
    def upload_target(self, lib: dict, filename: str, series_id: str | None = None,
                      collection: str | None = None, folder: str | None = None) -> Path:
        name = safe_component(posixpath.basename(filename.replace("\\", "/")))
        if name.lower().endswith(VIDEO_EXT):
            if lib.get("type") != "cosplay":
                raise ValueError("Videos can only be added to a Cosplay library")
        elif not name.lower().endswith(BOOK_EXT + REPACK_EXT):
            raise ValueError("Only .cbz, .cb7, .cbr, .epub and .zip / .rar / .7z archives can be added")
        # `folder` may be nested ("Collection/Set 2") — Cosplay video-only sets live in their own folder
        sub = safe_rel(folder) if folder and folder.strip(" ./\\") else ""
        if series_id:
            d = self.series_folder(series_id, create=False)
            return (d / sub / name) if sub else d / name
        base = _L.LIB_ROOT / lib["path"]
        if collection:
            base = base / same_case(base, safe_component(collection))
            base.mkdir(parents=True, exist_ok=True)
            (base / COL_MARK).touch()
        if sub:
            first, _, more = sub.partition("/")
            sub = same_case(base, first) + (f"/{more}" if more else "")
            return base / sub / name
        if collection:
            return base / name             # loose in a collection = its own series
        kind, number, before = parse_number(Path(name).stem)
        series = safe_component(tidy(before)) if number is not None else ""
        if not series:                             # "Name.cbz" next to an existing "Name/" (its Part 2, 3…)
            guess = safe_component(tidy(strip_brackets(Path(name).stem)))
            if guess and (_L.LIB_ROOT / lib["path"] / guess).is_dir():
                series = guess
        folder = _L.LIB_ROOT / lib["path"]
        if series:
            folder = folder / series
        return folder / name

    # ---- moving & deleting (operates on the files in /data)
    def _lib_path(self, lid: str) -> str:
        l = self.get_library(lid)
        if not l:
            raise ValueError("Unknown library")
        return l["path"]

    def series_books(self, sid: str) -> list[dict]:
        return [b for b in self.books.values() if b["seriesId"] == sid]

    def _series_dir(self, books: list[dict]) -> Path | None:
        for b in books:
            if b.get("sdir"):
                return _L.LIB_ROOT / b["sdir"]
        return None

    def _base(self, b: dict) -> Path:
        return _L.LIB_ROOT / (b.get("base") or self._lib_path(b["library"]))

    def _collection_folders(self, lib: dict) -> set:
        root = _L.LIB_ROOT / lib["path"]
        if not root.is_dir():
            return set()
        return {d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".") and (d / COL_MARK).exists()}

    def _collections_from_disk(self) -> list[dict]:
        out = []
        for l in self.libraries:
            for name in sorted(self._collection_folders(l), key=str.lower):
                d = _L.LIB_ROOT / l["path"] / name
                out.append({"id": self.groups.id_for("collection", collection_key(l["id"], name)), "name": name, "folder": name,
                            "library": l["id"], "added": int(d.stat().st_mtime)})
        return out

    def find_collection(self, cid: str) -> tuple[dict, Path]:
        for l in self.libraries:
            for name in self._collection_folders(l):
                if self.groups.id_for("collection", collection_key(l["id"], name)) == cid:
                    return l, _L.LIB_ROOT / l["path"] / name
        raise KeyError(cid)

    # ---- collections & empty series ("folder info")
    # Finding these means looking at every folder of every library. The scan already has every folder's
    # listing in memory (see _ls), so it works them out for free; the answer is kept with the index, so even
    # the first request after a restart needs no disk access. (On a Windows folder shared into Docker, asking
    # the disk took ~7 s for 2,300 series — on every start.)
    def folder_info(self) -> tuple[list, list]:
        info = self._folder_info
        if info is None:                             # nothing remembered yet (very first start): ask the disk
            info = self._folder_info = (self._collections_from_disk(), self._empty_series_from_disk())
        return info

    def forget_folders(self):
        """The app made or removed a folder: a scan (which only re-reads changed folders) refreshes the info."""
        self.scan()

    def collections(self) -> list[dict]:
        return self.folder_info()[0]

    def empty_series(self) -> list[dict]:
        return self.folder_info()[1]

    def _folders_from_scan(self, found: dict, cols_by_lib: dict) -> tuple[list, list]:
        memo, used = self._ls_memo, {b.get("seriesKey") or b["seriesId"] for b in found.values()}
        media = BOOK_EXT + MEDIA_EXT

        def has_media(d: str) -> bool:               # (iterative walk over the remembered listings)
            stack = [d]
            while stack:
                cur = stack.pop()
                got = memo.get(cur)
                if not got:
                    continue
                if any(posixpath.splitext(f)[1].lower() in media for f in got[1]):
                    return True
                stack.extend(os.path.join(cur, x) for x in got[0])
            return False
        secs = lambda d: int((memo.get(d) or (0, 0, 0, 0))[3] / 1e9)
        cols_out, empty_out = [], []
        for l in self.libraries:
            root = str(_L.LIB_ROOT / l["path"])
            top = memo.get(root)
            if not top:
                continue
            cols = cols_by_lib.get(l["id"], set())
            for name in sorted(cols, key=str.lower):
                cols_out.append({"id": self.groups.id_for("collection", collection_key(l["id"], name)), "name": name,
                                 "folder": name, "library": l["id"], "added": secs(os.path.join(root, name))})
            cands = [(None, d) for d in top[0] if d not in cols]
            for c in cols:
                cands += [(c, d) for d in (memo.get(os.path.join(root, c)) or ((),))[0]]
            for col, d in sorted(cands, key=lambda x: x[1].lower()):
                name = tidy(SQUARE.sub("", d)) or d
                key = series_key(l["id"], col, name)
                path = os.path.join(root, col, d) if col else os.path.join(root, d)
                if key in used or has_media(path):
                    continue
                empty_out.append({"seriesId": self.groups.id_for("series", key), "series": name, "library": l["id"],
                                  "folder": (col + "/" if col else "") + d, "collection": col,
                                  "collectionId": self.groups.id_for("collection", collection_key(l["id"], col)) if col else None,
                                  "added": secs(path)})
        return cols_out, empty_out

    def _empty_series_from_disk(self) -> list[dict]:
        """Series folders (also inside collections) that don't contain any books yet."""
        used = {b.get("seriesKey") or b["seriesId"] for b in self.books.values()}
        out = []
        for l in self.libraries:
            root = _L.LIB_ROOT / l["path"]
            if not root.is_dir():
                continue
            cols = self._collection_folders(l)
            cands = [(None, d) for d in root.iterdir() if d.is_dir() and d.name not in cols]
            for c in cols:
                cands += [(c, d) for d in (root / c).iterdir() if d.is_dir()]
            for col, d in sorted(cands, key=lambda x: x[1].name.lower()):
                if d.name.startswith("."):
                    continue
                name = tidy(SQUARE.sub("", d.name)) or d.name
                key = series_key(l["id"], col, name)
                if key in used or any(f.suffix.lower() in BOOK_EXT + MEDIA_EXT for f in d.rglob("*")):
                    continue
                out.append({"seriesId": self.groups.id_for("series", key), "series": name, "library": l["id"],
                            "folder": (col + "/" if col else "") + d.name, "collection": col,
                            "collectionId": self.groups.id_for("collection", collection_key(l["id"], col)) if col else None,
                            "added": int(d.stat().st_mtime)})
        return out

    def _release(self, folder: Path):
        """Close cached archive handles under `folder` — an open file inside blocks a rename on Windows hosts."""
        pre = folder.relative_to(_L.LIB_ROOT).as_posix() + "/"
        with self._zip_lock:
            for k in [k for k in self._zips if k[0].startswith(pre)]:
                try:
                    self._zips.pop(k).close()
                except Exception:  # noqa: BLE001
                    pass

    def _forget(self, bid: str):
        """The app deleted a book: drop everything kept about it."""
        self.progress.delete(bid); self.edits.delete(bid); self.ids.forget(bid)

    def _moved(self, old_rel: str, new_rel: str):
        """The app moved/renamed a file or folder: its books keep their ids (and so their progress, edits,
        favourites, covers and date added — nothing needs carrying over any more)."""
        self.ids.moved(old_rel, new_rel)
        for b in self.books.values():                 # until the rescan, point the index at the new place
            if b["rel"] == old_rel or b["rel"].startswith(old_rel + "/"):
                b["rel"] = new_rel + b["rel"][len(old_rel):]

    # ---- collections
    def _close_under(self, rel_prefix: str):
        """Close the reader's cached handles on archives under a folder (call with _zip_lock held)."""
        for k in [k for k in self._zips if k[0] == rel_prefix or k[0].startswith(rel_prefix + "/")]:
            try:
                self._zips.pop(k).close()
            except Exception:  # noqa: BLE001
                pass

    LOCKED = "a file inside is open somewhere (a viewer, Explorer, antivirus) — close it and try again"

    def _rename_dir(self, src: Path, dest: Path, tries: int = 8):
        """Rename a folder in two steps (so case-only renames work on Windows hosts) — and if the second step
        fails, put it back: otherwise it would stay under its hidden temporary name and vanish from the app.
        On Windows hosts a folder can't be renamed while any file inside is open. The app's own handles are
        closed first and kept closed (the background worker waits, page requests wait for the lock), and a
        brief lock by Windows itself (antivirus checking a freshly written file, Explorer's preview) is
        waited out with a few retries. Raises a readable error when something else keeps a file open."""
        tmp = src.with_name(f".{src.name}.renaming")
        rel = src.relative_to(_L.LIB_ROOT).as_posix()

        def attempt(a: Path, b: Path):
            for i in range(tries):
                with self._zip_lock:                   # nothing can reopen a cached handle in between
                    self._close_under(rel)
                    try:
                        a.rename(b)
                        return
                    except PermissionError:
                        if i == tries - 1:
                            raise
                time.sleep(min(0.25 * (i + 1), 1.5))   # ≈ 6 s in all

        with self._busy:                               # the background worker isn't reading inside meanwhile
            try:
                attempt(src, tmp)
            except PermissionError as e:
                log.warning("rename %s: still locked after retries (%s)", rel, e)
                raise OSError(e.errno, self.LOCKED) from e
            try:
                attempt(tmp, dest)
            except OSError as e:
                try:
                    tmp.rename(src)
                except OSError:
                    log.error("rename failed and couldn't be undone — the folder is at %s", tmp)
                if isinstance(e, PermissionError):
                    raise OSError(e.errno, self.LOCKED) from e
                raise

    def _migrate_prefix(self, old_rel: str, new_rel: str):
        """A folder moved/renamed: its books keep their ids."""
        self._moved(old_rel, new_rel)

    def create_collection(self, lid: str, name: str) -> dict:
        folder = safe_component((name or "").strip())
        if not folder:
            raise ValueError("Give the collection a name")
        root = _L.LIB_ROOT / self._lib_path(lid)
        d = root / folder
        if d.exists():
            raise ValueError(f"A folder called “{folder}” already exists in this library")
        d.mkdir(parents=True)
        (d / COL_MARK).touch()
        self.scan()
        return {"id": self.groups.id_for("collection", collection_key(lid, folder)), "name": folder, "library": lid}

    def rename_collection(self, cid: str, name: str) -> str:
        l, src = self.find_collection(cid)
        folder = safe_component((name or "").strip())
        if not folder:
            raise ValueError("Give the collection a name")
        dest = src.parent / folder
        if dest.exists() and dest.resolve() != src.resolve():
            raise ValueError(f"A folder called “{folder}” already exists in this library")
        if dest != src:
            self._release(src)
            self._rename_dir(src, dest)             # progress moves only once the folder really moved
            self._migrate_prefix(src.relative_to(_L.LIB_ROOT).as_posix(), dest.relative_to(_L.LIB_ROOT).as_posix())
            self.groups.rename("collection", collection_key(l["id"], src.name), collection_key(l["id"], folder))
        self.scan()
        return cid                                  # the id stays — only the name changed

    def ungroup_collection(self, cid: str):
        """Move every series out of the collection into the library root, then drop the folder."""
        l, src = self.find_collection(cid)
        root = _L.LIB_ROOT / l["path"]
        for item in sorted(src.iterdir()):
            if item.name == COL_MARK:
                continue
            dest = self._unique(root / item.name)
            shutil.move(str(item), str(dest))
            self._moved(item.relative_to(_L.LIB_ROOT).as_posix(), dest.relative_to(_L.LIB_ROOT).as_posix())
        shutil.rmtree(src, ignore_errors=True)
        self.scan()

    def delete_collection(self, cid: str):
        """Its books go to the trash (the folder follows once they've been moved out); an empty one goes at once."""
        _, src = self.find_collection(cid)
        prefix = src.relative_to(_L.LIB_ROOT).as_posix() + "/"
        books = [b for b in self.books.values() if b["rel"].startswith(prefix)]
        if books:
            self.trash_books(books)
            return
        shutil.rmtree(src)
        self.scan()

    def series_folder(self, sid: str, create: bool = True) -> Path:
        """Directory that holds a series' files. Loose series (files at the library root)
        are given their own folder when create=True; otherwise the library root is returned."""
        books = self.series_books(sid)
        if books:
            d = self._series_dir(books)
            if d is not None:
                return d
            root = self._base(books[0])
            if not create:
                return root
            return self._target_dir(books)
        e = next((x for x in self.empty_series() if x["seriesId"] == sid), None)
        if not e:
            raise KeyError(sid)
        return _L.LIB_ROOT / self._lib_path(e["library"]) / e["folder"]

    def create_series(self, lid: str, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the series a name")
        root = _L.LIB_ROOT / self._lib_path(lid)
        folder = safe_component(name)
        if not folder:
            raise ValueError("That name can't be used as a folder name")
        key = series_key(lid, None, tidy(SQUARE.sub("", folder)) or folder)
        if any(b.get("seriesKey") == key for b in self.books.values()) or (root / folder).exists():
            raise ValueError(f"A series called “{name}” already exists here")
        (root / folder).mkdir(parents=True)
        self.forget_folders()
        return {"seriesId": self.groups.id_for("series", key), "library": lid, "series": name}

    def rename_series(self, sid: str, name: str) -> str:
        name = (name or "").strip()
        folder = safe_component(name)
        if not folder:
            raise ValueError("Give the series a name")
        books = self.series_books(sid)
        empty = None if books else next((x for x in self.empty_series() if x["seriesId"] == sid), None)
        if not books and not empty:
            raise KeyError(sid)
        lid = books[0]["library"] if books else empty["library"]
        col = books[0].get("collection") if books else empty["collection"]
        base = self._base(books[0]) if books else _L.LIB_ROOT / self._lib_path(lid) / (col or "")
        dest = base / folder
        src = self.series_folder(sid, create=False) if books else self.series_folder(sid)
        loose = books and self._series_dir(books) is None
        new_key = series_key(lid, col, tidy(SQUARE.sub("", folder)) or folder)
        merging = dest.exists() and dest.resolve() != src.resolve()
        if not merging:                             # a plain rename: the id moves to the new name
            old_key = books[0].get("seriesKey") if books else series_key(lid, col, empty["series"])
            self.groups.rename("series", old_key, new_key)
        if loose or merging:
            for b in books:                         # loose files, or merging into an existing folder
                self._move_file(b, dest)
            dest.mkdir(parents=True, exist_ok=True)
            if not books:
                self._prune(src)
        elif dest != src:
            self._release(src)
            self._rename_dir(src, dest)
            self._moved(src.relative_to(_L.LIB_ROOT).as_posix(), dest.relative_to(_L.LIB_ROOT).as_posix())
        self.scan()
        return self.groups.id_for("series", new_key)

    def move_books(self, ids: list[str], library: str | None = None, series_id: str | None = None, new_series: str | None = None):
        books = [self._book(i) for i in ids]
        if series_id:
            d = self.series_folder(series_id)
            for b in books:
                self._move_file(b, d)
        else:
            for b in books:
                name = (new_series or b["series"]).strip()
                if not name:
                    raise ValueError("Series name can't be empty")
                base = _L.LIB_ROOT / self._lib_path(library) if library and library != b["library"] else self._base(b)
                self._move_file(b, base / safe_component(name))
        self.scan()

    def delete_empty_series(self, sid: str) -> bool:
        e = next((x for x in self.empty_series() if x["seriesId"] == sid), None)
        if not e:
            return False
        shutil.rmtree(_L.LIB_ROOT / self._lib_path(e["library"]) / e["folder"])
        self.forget_folders()
        return True

    def _target_dir(self, target_books: list[dict]) -> Path:
        """Folder of an existing series; loose single-file series get a folder first."""
        d = self._series_dir(target_books)
        if d is None:
            d = self._base(target_books[0]) / safe_component(target_books[0]["series"])
            for x in target_books:
                self._move_file(x, d)
        return d

    @staticmethod
    def _unique(dest: Path) -> Path:
        i, cand = 2, dest
        while cand.exists():
            cand = dest.with_name(f"{dest.stem} ({i}){dest.suffix}")
            i += 1
        return cand

    def _prune(self, folder: Path):
        """Remove now-empty series folders (never a library root or /data itself)."""
        stop = {(_L.LIB_ROOT / l["path"]).resolve() for l in self.libraries} | {_L.LIB_ROOT.resolve()}
        if self.accounts:
            stop |= {(_L.LIB_ROOT / a["folder"]).resolve() for a in self.accounts.items}
        f = folder
        while f.resolve() not in stop and _L.LIB_ROOT.resolve() in f.resolve().parents:
            try:
                f.rmdir()
            except OSError:
                break
            f = f.parent

    def _release_file(self, rel: str):
        """Close the reader's cached handle on this archive — an open file can't be moved / deleted on Windows hosts."""
        with self._zip_lock:
            for k in [k for k in self._zips if k[0] == rel]:
                try:
                    self._zips.pop(k).close()
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _retry(fn, *args, tries: int = 6):
        """Windows hosts report a file as locked for a moment (thumbnailer, antivirus, Explorer preview): retry."""
        for i in range(tries):
            try:
                return fn(*args)
            except PermissionError:
                if i == tries - 1:
                    raise
                time.sleep(0.25 * (i + 1))

    def _move_file(self, b: dict, dest_dir: Path):
        src = _L.LIB_ROOT / b["rel"]
        if not src.exists():
            return
        dest_dir.mkdir(parents=True, exist_ok=True)
        if (dest_dir / src.name).resolve() == src.resolve():
            return
        dest = self._unique(dest_dir / src.name)
        self._release_file(b["rel"])
        self._retry(shutil.move, str(src), str(dest))
        self._moved(b["rel"], dest.relative_to(_L.LIB_ROOT).as_posix())
        self._prune(src.parent)
        job_step(src.name)                         # one more file for the job running this (if any)

    def _book(self, bid: str) -> dict:
        b = self.books.get(bid)
        if not b:
            raise KeyError(bid)
        return b

    def move_book(self, bid: str, library: str | None = None, series_id: str | None = None, new_series: str | None = None):
        self.move_books([bid], library, series_id, new_series)

    def move_series(self, sid: str, library: str | None = None, into: str | None = None, collection: str | None = None):
        if collection is not None:          # "" = library root of the series' library
            books = self.series_books(sid)
            lid = books[0]["library"] if books else next((x["library"] for x in self.empty_series() if x["seriesId"] == sid), None)
            if not lid:
                raise KeyError(sid)
            target = self.find_collection(collection)[1] if collection else _L.LIB_ROOT / self._lib_path(lid)
            if books:
                src = self._series_dir(books)
                d = target / src.name if src else target      # a loose file / photo-set folder stays loose
                if not src:                                    # loose series: join a same-named series folder there
                    same = target / safe_component(books[0]["series"])
                    if same.is_dir() and same != target:
                        d = same
                failed = []
                for b in books:                                # every chapter is tried — one locked file doesn't
                    try:                                       # leave the series split down the middle
                        self._move_file(b, d)
                    except OSError as e:
                        log.warning("couldn't move %s: %s", b["rel"], e)
                        failed.append(b["file"])
                if failed:
                    self.scan()
                    raise OSError(13, f"{len(failed)} of {len(books)} files couldn’t be moved ({', '.join(failed[:3])}"
                                      f"{'…' if len(failed) > 3 else ''}) — a file is open somewhere; close it and try again")
            else:
                e = next(x for x in self.empty_series() if x["seriesId"] == sid)
                srcd = _L.LIB_ROOT / self._lib_path(lid) / e["folder"]
                shutil.move(str(srcd), str(self._unique(target / srcd.name)))
            self.scan()
            return
        books = self.series_books(sid)
        if not books:
            e = next((x for x in self.empty_series() if x["seriesId"] == sid), None)
            if not e:
                raise KeyError(sid)
            src = _L.LIB_ROOT / self._lib_path(e["library"]) / e["folder"]
            if into:
                shutil.rmtree(src)             # nothing to merge — just drop the empty folder
            elif library and library != e["library"]:
                dest = _L.LIB_ROOT / self._lib_path(library) / Path(e["folder"]).name
                if dest.exists():
                    shutil.rmtree(src)
                else:
                    shutil.move(str(src), str(dest))
            return
        if into:
            if into == sid:
                return
            d = self.series_folder(into)
        else:
            src = self._series_dir(books)
            d = _L.LIB_ROOT / self._lib_path(library) / src.name if src else _L.LIB_ROOT / self._lib_path(library)
        failed = []
        for b in books:                                # try every chapter, report the ones that didn't move
            try:
                self._move_file(b, d)
            except OSError as e:
                log.warning("couldn't move %s: %s", b["rel"], e)
                failed.append(b["file"])
        self.scan()
        if failed:
            raise OSError(13, f"{len(failed)} of {len(books)} files couldn’t be moved ({', '.join(failed[:3])}"
                              f"{'…' if len(failed) > 3 else ''}) — a file is open somewhere; close it and try again")

    def delete_series_many(self, sids: list[str]) -> int:
        """Several series: their books go to the trash; empty ones are removed at once."""
        want = set(sids)
        books = [b for b in self.books.values() if b["seriesId"] in want]
        self.trash_books(books)
        removed, gone = len({b["seriesId"] for b in books}), 0
        for e in self.empty_series():
            if e["seriesId"] in want:
                shutil.rmtree(_L.LIB_ROOT / self._lib_path(e["library"]) / e["folder"], ignore_errors=True)
                gone += 1
        if gone:
            self.scan()
        return removed + gone

    def delete_books(self, books: list[dict]):
        for b in books:
            src = _L.LIB_ROOT / b["rel"]
            self._release_file(b["rel"])
            self._retry(_remove, src, b)
            self._forget(b["id"])
            self._prune(src.parent)
            job_step(src.name)
        self.scan()

    # ---- Empty folders
    def remove_empty_folders(self) -> int:
        """Folders with nothing in them (but marker / system files) that have been that way for
        EMPTY_FOLDER_AFTER are removed — leftovers of moves and deletes, emptied collections. Works from the
        folder listings the scan just made: no extra disk reads. Library folders themselves are never removed."""
        memo, now, removed = self._ls_memo, time.time_ns(), 0
        roots = {str(_L.LIB_ROOT / l["path"]) for l in self.libraries}
        empty: dict[str, bool] = {}

        def is_empty(d: str) -> bool:
            if d not in empty:
                got = memo.get(d)
                empty[d] = bool(got) and all(f.lower() in JUNK_FILES for f in got[1])\
                    and all(is_empty(os.path.join(d, x)) for x in got[0])\
                    and now - got[3] > _L.EMPTY_FOLDER_AFTER * 1_000_000_000
            return empty[d]
        for d in sorted(memo, key=len, reverse=True):               # deepest first
            if d in roots or not any(d.startswith(r + os.sep) for r in roots) or not is_empty(d):
                continue
            try:
                for f in memo[d][1]:
                    os.unlink(os.path.join(d, f))
                os.rmdir(d)
                removed += 1
            except OSError:
                pass
        if removed:
            log.info("removed %d empty folder(s)", removed)
        return removed

    # ---- Cosplay tidy (runs after every scan, like Immich's / Jellyfin's background jobs)
    def _cosplay_units(self, lib: dict) -> dict:
        """What sits at each level of a Cosplay library: {container dir: [(entry path, name, is_set_folder)]}.
        A set folder holds books; any other entry is one book (an archive, a video or a photo folder)."""
        root = _L.LIB_ROOT / lib["path"]
        units: dict[Path, dict[Path, tuple]] = {}
        for b in self.books.values():
            if b["library"] != lib["id"] or b.get("format") == "epub":
                continue
            src = _L.LIB_ROOT / b["rel"]
            container = root / b["collection"] if b.get("collection") else root
            if b.get("sdir"):
                entry = _L.LIB_ROOT / b["sdir"]
                if entry.parent != container:          # deeper than <Set>/<file> — not ours to rearrange
                    continue
                units.setdefault(container, {})[entry] = (entry.name, True)
            else:
                stem = src.name if b.get("src") == "folder" else src.stem
                units.setdefault(container, {})[src] = (stem, False)
        return {c: [(e, n, s) for e, (n, s) in u.items()] for c, u in units.items()}

    def _mark_cosplayers(self, lib: dict) -> int:
        """Hand-copied <Cosplayer>/<Set>/<files> (no marker yet): a top folder holding only set folders is a cosplayer."""
        root, n = _L.LIB_ROOT / lib["path"], 0
        by_dir: dict[str, list[int]] = {}
        for b in self.books.values():
            if b["library"] == lib["id"] and not b.get("collection") and b.get("sdir"):
                inner = b["rel"][len(lib["path"]) + 1:].split("/")
                by_dir.setdefault(inner[0], []).append(len(inner))
        for d, depths in by_dir.items():
            if min(depths) >= 3 and not (root / d / COL_MARK).exists():
                try:
                    (root / d / COL_MARK).touch(); n += 1
                except OSError as e:
                    log.warning("couldn't mark %s as a cosplayer: %s", d, e)
        return n

    def _move_entry(self, src: Path, dest: Path):
        """Move a file/folder, keeping reading progress and edits of every book inside it."""
        old_rel, new_rel = src.relative_to(_L.LIB_ROOT).as_posix(), dest.relative_to(_L.LIB_ROOT).as_posix()
        dest.parent.mkdir(parents=True, exist_ok=True)
        (self._release if src.is_dir() else self._release_file)(src if src.is_dir() else old_rel)
        self._retry(shutil.move, str(src), str(dest))
        self._moved(old_rel, new_rel)

    def tidy_cosplay(self) -> int:
        """Cosplay libraries end up as <Cosplayer>/<Set>/<variant files>, whatever way the files came in:
          · a set at the top whose name credits a cosplayer moves into that cosplayer's folder;
          · siblings sharing a base name ("… Bonus", "… Normal") become variants of one set;
          · a later variant joins a set that already exists.
        Files are only ever moved — never renamed, re-packed or deleted. Returns how many things moved."""
        moved = 0
        for lib in [l for l in self.libraries if l.get("type") == "cosplay"]:
            root = _L.LIB_ROOT / lib["path"]
            if not root.is_dir():
                continue
            moved += self._mark_cosplayers(lib)
            for container, units in self._cosplay_units(lib).items():
                groups: dict[str, list] = {}
                for entry, name, is_set in units:
                    if container == root:
                        cos = cosplay_name(name)["cosplayer"]
                        cos_dir = root / same_case(root, safe_component(cos)) if cos else root
                    else:
                        cos_dir = container
                    groups.setdefault(str(cos_dir), []).append((entry, name, is_set))
                for cos_dir, items in groups.items():
                    cos_dir = Path(cos_dir)
                    got = self._ls(str(cos_dir))               # from the scan that just ran: no extra listing
                    existing = {n.lower(): n for n in (got[0] if got else [])}
                    works = sibling_works([n for _, n, _ in items])
                    found = variant_groups(works)
                    for i, (entry, name, is_set) in enumerate(items):
                        if entry.as_posix() in self._tidy_failed:
                            continue
                        base = joins_existing(works[i], existing)
                        if i in found:
                            set_name = found[i][0]                              # a variant among its siblings
                        elif base and base.lower() != entry.name.lower():
                            set_name = base                                     # a later variant of an existing set
                        elif container == cos_dir:
                            continue                                            # a lone set already in place: leave it
                        else:
                            set_name = works[i]                                 # a lone set moving into its cosplayer
                        set_dir = cos_dir / existing.get(set_name.lower(), safe_component(set_name))
                        if entry == set_dir or (not is_set and entry.parent == set_dir):
                            continue
                        if is_set and set_dir.exists():
                            rel = entry.relative_to(_L.LIB_ROOT).as_posix()
                            if sum(1 for b in self.books.values() if b.get("sdir") == rel) > 1:
                                continue                                        # never pour a multi-book set into another
                        if not entry.exists():                 # (checked only for the few that need moving)
                            continue
                        try:
                            if cos_dir != root and not (cos_dir / COL_MARK).exists():
                                cos_dir.mkdir(parents=True, exist_ok=True); (cos_dir / COL_MARK).touch()
                            if is_set and not set_dir.exists():
                                self._move_entry(entry, set_dir)          # the whole set folder, extras included
                            elif is_set:
                                for child in sorted(entry.iterdir()):
                                    self._move_entry(child, self._unique(set_dir / child.name))
                                self._prune(entry)
                            else:
                                self._move_entry(entry, self._unique(set_dir / entry.name))
                            existing[set_dir.name.lower()] = set_dir.name
                            moved += 1
                            log.info("tidy: %s → %s", entry.relative_to(root).as_posix(), set_dir.relative_to(root).as_posix())
                        except OSError as e:
                            self._tidy_failed.add(entry.as_posix())   # don't retry every scan; a restart tries again
                            log.warning("tidy: couldn't move %s: %s", entry.name, e)
        return moved
