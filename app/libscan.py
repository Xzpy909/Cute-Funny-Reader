"""Scanning: walking the library folders, reading what changed, the index, the watch loop and the
background preparation of new books.

Part of the Library class (library.py: class Library(…, ScanMixin, …)) — methods and attributes unchanged; LIB_ROOT,
CONFIG_DIR and EMPTY_FOLDER_AFTER are read from library.py at call time (_L.…) so tests can swap them."""
from __future__ import annotations

import os
import time

from pathlib import Path

from . import library as _L
from .library import BOOK_EXT, COL_MARK, IMG_EXT, SCAN_INTERVAL, VIDEO_EXT, collection_key, is_meta_file, is_video, log, make_id, media_sort, needs_transcode, parse_book, place_book


class ScanMixin:
    # ---- scanning
    def scan(self, deep: bool = False):
        """Bring the index in line with the disk. Normally only folders whose modification time changed are
        listed again (see _ls); deep=True re-lists every folder and re-checks every file (the periodic safety
        net, and the "Rescan library" button)."""
        with self._scan_lock:
            changed = self._scan(deep)
            try:
                # tidying only has something to do when the books changed (or on the full check)
                if (changed or deep) and self.tidy_cosplay():
                    self._scan()
                if (deep or time.time() - self._emptied > 600) and self._scanned:
                    self._emptied = time.time()
                    if self.remove_empty_folders():
                        self._scan()
            except Exception as e:  # noqa: BLE001 — tidying must never break scanning
                log.warning("cosplay tidy failed: %s", e)

    # ---- folder listings, remembered between scans
    # Listing a folder and checking each file in it is the slow part of a scan — very slow on a Windows/macOS
    # folder shared into Docker. A folder's modification time changes whenever something in it is added,
    # removed or renamed, so an unchanged time means the remembered listing (and the books made from it) still
    # holds: one stat() per folder instead of a listing plus a stat() per file.
    RACY_NS = 3_000_000_000      # a folder changed this recently may change again within the same clock tick

    def _ls(self, d: str, deep: bool = False) -> tuple[list, list, bool, int] | None:
        """(sub-folders, files, fresh, mtime) of a folder — fresh=False: unchanged since the last scan. None: gone."""
        hit = self._ls_memo.get(d)
        if hit is not None:
            return hit
        try:
            m = os.stat(d).st_mtime_ns
        except OSError:
            self._dircache.pop(d, None)
            return None
        c = self._dircache.get(d)
        if c and c[0] == m and not deep:
            out = (c[1], c[2], False, m)
        else:
            dirs, files = [], []
            try:
                with os.scandir(d) as it:
                    for e in it:
                        try:
                            (dirs if e.is_dir() else files).append(e.name)
                        except OSError:
                            files.append(e.name)
            except OSError:
                self._dircache.pop(d, None)
                return None
            dirs = sorted(x for x in dirs if not x.startswith("."))
            if time.time_ns() - m > self.RACY_NS:
                self._dircache[d] = (m, dirs, files)
            else:
                self._dircache.pop(d, None); self._racy = True       # look again next time
            out = (dirs, files, True, m)
        self._ls_memo[d] = out
        return out

    def _walk(self, root: Path, deep: bool):
        """os.walk(root), top-down and sorted, hidden folders skipped — through the remembered listings."""
        stack = [str(root)]
        while stack:
            d = stack.pop()
            got = self._ls(d, deep)
            if got is None:
                continue
            yield d, got[0], got[1], got[2]
            stack.extend(os.path.join(d, x) for x in reversed(got[0]))

    def _stale(self, *paths: Path):
        """The app changed a file in place (which doesn't touch its folder's modification time): look again."""
        for p in paths:
            self._dircache.pop(str(p), None)

    def changed_on_disk(self) -> bool:
        """Has any known folder changed since the last scan? One stat() per folder, no listings."""
        if not self._dircache and not self._scanned:
            return True
        try:
            if _L.LIB_ROOT.stat().st_mtime_ns != self._root_m:
                return True
        except OSError:
            return True
        for d, c in list(self._dircache.items()):
            try:
                if os.stat(d).st_mtime_ns != c[0]:
                    return True
            except OSError:
                return True
        return False

    def _scan(self, deep: bool = False):
        if self.scanning:
            return None
        self.scanning = True
        t0 = time.time()
        self._ls_memo, self._racy = {}, False
        # a scan that takes a while shows as a job: "Scanning · 1,200 of 3,400 files" (the total: last scan's count)
        tracker = self.track("scan", "Checking everything" if deep else "Scanning", unit="files",
                             total=len(self.books) or None)
        tracker.__enter__()
        try:
            by_rel = {b["rel"]: b for b in self.books.values()}
            first_run = not by_rel
            found: dict[str, dict] = {}
            changed_dirs = False
            col_keys: set[str] = set()
            dir_list: list[str] = []
            cols_by_lib: dict[str, set] = {}
            # which series / collection every book was in — taken now, because the walk below re-places
            # (mutates) the very same book dicts
            before = {bid: (b.get("seriesId"), b.get("collectionId")) for bid, b in self.books.items()}
            self.discover()
            self.drop_missing()
            if self.libraries and not _L.LIB_ROOT.exists():
                raise FileNotFoundError(f"{_L.LIB_ROOT} does not exist — mount a folder there")
            # deepest library paths first, so nested libraries claim their own files
            for lib in sorted(list(self.libraries), key=lambda l: -l["path"].count("/")):
                root = _L.LIB_ROOT / lib["path"]
                if not root.is_dir():
                    continue
                top = self._ls(str(root), deep)
                cols = {d for d in (top[0] if top else [])
                        if COL_MARK in ((self._ls(os.path.join(str(root), d), deep) or ((), ()))[1])}
                col_keys |= {collection_key(lib["id"], c) for c in cols}
                cols_by_lib[lib["id"]] = cols
                # plain string paths below: pathlib arithmetic per file was most of an unchanged scan's time
                root_s, base_n = str(root), len(str(_L.LIB_ROOT)) + 1
                for dirpath, dirnames, filenames, fresh in self._walk(root, deep):
                    dir_list.append(dirpath)
                    tracker.progress(len(found), label=lib["name"])
                    in_root = dirpath[len(root_s) + 1:].replace(os.sep, "/")       # "" at the library's top
                    cosplay = lib.get("type") == "cosplay"
                    vis = [f for f in filenames if not f.startswith(".")]
                    imgs = [f for f in vis if f.lower().endswith(IMG_EXT)]
                    vids = [f for f in vis if f.lower().endswith(VIDEO_EXT)] if cosplay else []
                    absorbed = set()
                    # Cosplay: a folder of only videos *inside a collection* (<lib>/<Collection>/<Set>/) is one set too.
                    # Videos lying loose in a collection folder stay one set each.
                    depth = tuple(in_root.split("/")) if in_root else ()
                    depth = depth[1:] if depth and depth[0] in cols else depth
                    video_set = (cosplay and vids and not imgs and not dirnames and len(depth) >= 2
                                 and not any(f.lower().endswith(BOOK_EXT) for f in vis))
                    # a folder with photos directly in it (and no archives) is one book — a photo set / chapter.
                    # A lone cover.jpg next to chapter subfolders is just artwork, not a set.
                    if video_set or (imgs and in_root and not any(f.lower().endswith(BOOK_EXT) for f in vis)
                            and (len(imgs) >= 2 or not dirnames)):
                        media = media_sort(imgs + vids)
                        absorbed = set(media)
                        self._scan_set(Path(dirpath), media, root, lib, cols, by_rel, found, first_run, fresh)
                    for fn in filenames:
                        if fn in absorbed:
                            continue
                        low = fn.lower()
                        if fn.startswith(".") or not (low.endswith(BOOK_EXT) or (low.endswith(VIDEO_EXT) and lib.get("type") == "cosplay")):
                            continue
                        rel = (dirpath[base_n:] + os.sep + fn).replace(os.sep, "/")
                        if make_id(rel) in found:
                            continue
                        inner = in_root + "/" + fn if in_root else fn
                        old = by_rel.get(rel)
                        if old and not fresh and old["library"] == lib["id"]:      # folder untouched → file untouched
                            place_book(old, lib["id"], lib["path"], inner, cols, lib.get("type") == "cosplay")
                            found[make_id(rel)] = old
                            continue
                        path = Path(dirpath) / fn
                        try:
                            st = path.stat()
                        except OSError:
                            continue
                        if (old and old["size"] == st.st_size
                                and old["mtime"] == int(st.st_mtime) and old["library"] == lib["id"]):
                            place_book(old, lib["id"], lib["path"], inner, cols, lib.get("type") == "cosplay")
                            found[make_id(rel)] = old           # keyed by path for now — ids are settled below
                            continue
                        try:
                            b = parse_book(path, rel, inner, lib["id"], st)
                        except Exception as e:  # noqa: BLE001
                            log.warning("skipping %s: %s", rel, e)
                            continue
                        b["added"] = old["added"] if old else (int(st.st_mtime) if first_run else int(time.time()))
                        place_book(b, lib["id"], lib["path"], inner, cols, lib.get("type") == "cosplay")
                        found[make_id(rel)] = b
            found = self.ids.resolve(found, make_id, int(time.time()))   # permanent ids (moves keep theirs)
            self._settle_names(found, col_keys, before)
            self._imply_first(found)
            with self.lock:
                self.books = found
                self.last_scan = time.time()
                # (ids survive renames now, so names and labels are part of "did anything change")
                sig = hash(tuple(sorted((b["id"], b["seriesId"], b.get("collectionId") or "", b["mtime"], b["size"],
                                         b["series"], b.get("collection") or "", b["label"]) for b in found.values())))
                changed = sig != self._sig
                if changed:
                    self._sig, self.rev = sig, self.rev + 1
                dsig = hash((tuple(dir_list), tuple(sorted((k, tuple(sorted(v))) for k, v in cols_by_lib.items()))))
                if changed or dsig != self._dir_sig or self._folder_info is None:   # folders added / removed / renamed
                    self._dir_sig, self._folder_info = dsig, self._folders_from_scan(found, cols_by_lib)
                    changed_dirs = True
                self.scan_error = None
                for d in [d for d in self._dircache if d not in self._ls_memo]:
                    del self._dircache[d]                  # folders that are gone
                self._scanned = True
                try:
                    self._root_m = _L.LIB_ROOT.stat().st_mtime_ns
                except OSError:
                    self._root_m = None
            # the index is only a start-up cache: rewrite it when something changed (or on the first scan
            # after a start, which may have fixed up old entries) — not every 30 s for nothing
            if changed or changed_dirs or not self._saved_once:
                self._save_index(); self._saved_once = True
            log.info("scan complete: %d books in %.1fs", len(found), time.time() - t0)
            self.queue_prep()
            if deep or time.time() - self._swept > 600:    # the cache clean-up lists the whole cache: not every scan
                self._swept = time.time()
                try:
                    self.sweep_cache()
                except Exception as e:  # noqa: BLE001 — a failed clean-up must never fail the scan
                    log.warning("cache sweep failed: %s", e)
            return changed
        except Exception as e:  # noqa: BLE001
            self.scan_error = str(e)
            log.error("scan failed: %s", e)
            self._dircache.clear()                         # don't trust remembered listings after a failure
            tracker.__exit__(RuntimeError, RuntimeError(f"Scan failed: {e}"), None)
            tracker = None
            return None
        finally:
            self.scanning = False
            if tracker:
                if tracker.total and tracker.done > tracker.total:
                    tracker.total = tracker.done
                tracker.__exit__(None, None, None)

    def _settle_names(self, found: dict, col_keys: set, before: dict):
        """Swap each book's natural series / collection key for the permanent id (see store.Names)."""
        now = int(time.time())
        for slot, (kind, key_f, id_f, keep) in enumerate((("series", "seriesKey", "seriesId", set()),
                                                          ("collection", "collectionKey", "collectionId", col_keys))):
            present: dict[str, list] = {}
            for b in found.values():
                if b.get(key_f):
                    present.setdefault(b[key_f], []).append(b["id"])
            old = {bid: v[slot] for bid, v in before.items() if v[slot]}
            ids = self.groups.resolve(kind, present, old, now, keep)
            for b in found.values():
                if b.get(key_f):
                    b[id_f] = ids[b[key_f]]

    def _imply_first(self, found: dict):
        """"Name.cbz" + "Name - Part 2.cbz" (+ "Name - Part 3.cbz"…) → the unnumbered one is chapter 1.
        Only when it is the series' *only* unnumbered book and number 1 is still free; re-decided every scan
        (marked impliedFirst) so it's undone when the siblings go. Not in Cosplay libraries (sets, not chapters)."""
        groups: dict[str, list] = {}
        for b in found.values():
            if b.pop("impliedFirst", None):            # undo last scan's guess, decide afresh
                b.update(number=None, kind=b.pop("kindOrig", None), label=b.pop("labelOrig", b["label"]),
                         title=b.pop("titleOrig", ""))
            groups.setdefault(b["seriesId"], []).append(b)
        cosplay = {l["id"] for l in self.libraries if l.get("type") == "cosplay"}
        for books in groups.values():
            if books[0]["library"] in cosplay or len(books) < 2:
                continue
            loose = [b for b in books if b["number"] is None]
            nums = [b["number"] for b in books if b["number"] is not None]
            if len(loose) != 1 or not nums or min(nums) <= 1 or loose[0].get("format") == "epub":
                continue
            b = loose[0]
            kinds = {x["kind"] for x in books if x["number"] is not None}
            kind = kinds.pop() if len(kinds) == 1 else "chapter"
            b.update(impliedFirst=True, kindOrig=b["kind"], labelOrig=b["label"], titleOrig=b.get("title", ""),
                     number=1.0, kind=kind, label=f"{'Vol.' if kind == 'volume' else 'Chapter'} 1",
                     title=b.get("title") or (b["label"] if b["label"].lower() != b["series"].lower() else ""))

    def _scan_set(self, d: Path, media: list[str], root: Path, lib: dict, cols: set, by_rel: dict, found: dict,
                  first_run: bool, fresh: bool = True):
        rel = d.relative_to(_L.LIB_ROOT).as_posix()
        if make_id(rel) in found:
            return
        inner = d.relative_to(root).as_posix()
        old = by_rel.get(rel)
        if old and not fresh and old["library"] == lib["id"] and old.get("entries") == media:   # folder untouched
            place_book(old, lib["id"], lib["path"], inner, cols, lib.get("type") == "cosplay")
            found[make_id(rel)] = old
            return
        size, mtime = 0, 0.0
        metas = [f.name for f in d.iterdir() if is_meta_file(f.name)] if d.is_dir() else []
        for n in media + metas:                     # metadata files count too: an edit must trigger a re-read
            try:
                st = (d / n).stat()
            except OSError:
                return
            size += st.st_size
            mtime = max(mtime, st.st_mtime)
        sig = type("St", (), {"st_size": size, "st_mtime": mtime})()
        old = by_rel.get(rel)
        if (old and old["size"] == size and old["mtime"] == int(mtime)
                and old["library"] == lib["id"] and old.get("entries") == media):
            place_book(old, lib["id"], lib["path"], inner, cols, lib.get("type") == "cosplay")
            found[make_id(rel)] = old
            return
        try:
            b = parse_book(d, rel, inner, lib["id"], sig, media=media)
        except Exception as e:  # noqa: BLE001
            log.warning("skipping %s: %s", rel, e)
            return
        b["added"] = old["added"] if old else (int(mtime) if first_run else int(time.time()))
        place_book(b, lib["id"], lib["path"], inner, cols, lib.get("type") == "cosplay")
        found[make_id(rel)] = b

    def watch_loop(self):
        """Every few seconds: has a folder changed (also from Explorer / Finder on the host)? Then scan — which
        only re-reads the changed folders. Every SCAN_INTERVAL a deep scan re-checks everything."""
        last_deep = time.time()
        while True:
            try:
                if self.trash_tick():
                    self.scan()
                deep = time.time() - last_deep > max(30, SCAN_INTERVAL)
                if deep or self._racy or not self._scanned or self.changed_on_disk():
                    self.scan(deep=deep)
                    if deep:
                        last_deep = time.time()
            except Exception as e:  # noqa: BLE001
                log.warning("watcher: %s", e)
            time.sleep(4)

    def status(self):
        with self.lock:
            series = {b["seriesId"] for b in self.books.values()}
            return {
                "books": len(self.books), "series": len(series), "libraries": len(self.libraries),
                "lastScan": self.last_scan, "rev": self.rev,
                "scanning": self.scanning, "error": self.scan_error, "root": str(_L.LIB_ROOT),
                "preparing": len(self._prep_queue) + (1 if self._prep_busy else 0),
            }

    # ---- background preparation
    # The slow first-open work (measuring every page, the card cover, screen-sized copies of the first
    # pages) is done by a worker as soon as a scan finds a new book — so opening it later is instant.
    # A book you open yourself never waits for the worker: the reader does what it needs right away.
    @staticmethod
    def needs_prep(b: dict) -> bool:
        return b.get("format") == "images" and not (b.get("dims") and len(b["dims"]) == len(b.get("entries") or []))

    def queue_prep(self):
        with self.lock:
            todo = sorted((b for b in self.books.values() if self.needs_prep(b)), key=lambda b: -(b.get("added") or 0))
        with self._prep:
            for b in todo:
                self._prep_queue[b["id"]] = True
            if todo:
                self._prep.notify()

    def prepare(self, b: dict):
        """Everything a first open would otherwise wait for. Safe to repeat: each step is cached."""
        self.dims(b, save=False)
        try:
            self.cover(b, 320)
        except Exception as e:  # noqa: BLE001
            log.debug("cover for %s: %s", b["rel"], e)
        if not needs_transcode(b):                     # JPEG XL / HEIC books have their own conversion step
            pages = [n for n, name in enumerate(b["entries"]) if not is_video(name)][:2]
            for n in pages:
                try:
                    self.display_page(b, n, self.display_hint)
                except Exception as e:  # noqa: BLE001
                    log.debug("display copy %s #%d: %s", b["rel"], n, e)

    def prep_loop(self):
        done, last_save = 0, time.time()
        while True:
            with self._prep:
                while not self._prep_queue:
                    if done:                           # queue drained: save what was measured
                        self._save_index(); done = 0
                    self._prep.wait()
                bid, _ = self._prep_queue.popitem(last=False)
                self._prep_busy = True
            try:
                b = self.books.get(bid)
                if b and self.needs_prep(b):
                    with self._busy:
                        self.prepare(b)
                    done += 1
                    if done >= 10 or time.time() - last_save > 30:
                        self._save_index(); done, last_save = 0, time.time()
            except Exception as e:  # noqa: BLE001 — one bad file must not stop the worker
                log.warning("preparing %s failed: %s", bid, e)
            finally:
                self._prep_busy = False
            time.sleep(0.02)                           # leave room for the reader's own requests
