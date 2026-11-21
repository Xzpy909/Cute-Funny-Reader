"""The trash: items marked for it stay in place for TRASH_DELAY (undo), then move into <account>/.trash,
where they stay TRASH_KEEP before they're deleted.

Part of the Library class (library.py: class Library(…, TrashMixin, …)) — methods and attributes unchanged; LIB_ROOT,
CONFIG_DIR and EMPTY_FOLDER_AFTER are read from library.py at call time (_L.…) so tests can swap them."""
from __future__ import annotations

import shutil
import time
import uuid

from pathlib import Path

from . import library as _L
from .library import JUNK_FILES, TRASH_DELAY, TRASH_DIR, TRASH_KEEP, log


class TrashMixin:
    # ---- Trash
    # "Delete" doesn't delete: the book is marked (instant — the card greys out, and can be put back with one
    # click). After TRASH_DELAY the worker moves its file into <account>/.trash, where it stays TRASH_KEEP
    # before it is really deleted. Reading progress and edits are kept until then, so a restore is complete.
    def trash_books(self, books: list[dict]) -> int:
        now = int(time.time())
        new = {b["id"]: {"at": now} for b in books if not self.trash.get(b["id"])}
        self.trash.put_many(new)
        return len(new)

    def untrash(self, ids: list[str]) -> int:
        ids = [i for i in ids if self.trash.get(i)]
        self.trash.delete_many(ids)
        return len(ids)

    def _trash_root(self, b: dict) -> Path:
        lib = self.get_library(b["library"]) or {}
        top = lib.get("path", "").split("/")[0] if "/" in lib.get("path", "") else ""
        return _L.LIB_ROOT / top / TRASH_DIR if top else _L.LIB_ROOT / TRASH_DIR

    def _prune_junk(self, folder: Path):
        """Like _prune, but a folder holding only marker / system files (.collection, Thumbs.db…) counts as empty."""
        stop = {(_L.LIB_ROOT / l["path"]).resolve() for l in self.libraries} | {_L.LIB_ROOT.resolve()}
        if self.accounts:
            stop |= {(_L.LIB_ROOT / a["folder"]).resolve() for a in self.accounts.items}
        f = folder
        while f.resolve() not in stop and _L.LIB_ROOT.resolve() in f.resolve().parents:
            try:
                inside = list(f.iterdir())
                if any(p.is_dir() or p.name.lower() not in JUNK_FILES for p in inside):
                    break
                for p in inside:
                    p.unlink()
                f.rmdir()
            except OSError:
                break
            f = f.parent

    def _to_bin(self, b: dict, marked: int):
        src = _L.LIB_ROOT / b["rel"]
        lib = self.get_library(b["library"]) or {}
        root = self._trash_root(b)
        tid = uuid.uuid4().hex[:12]
        (root / tid).mkdir(parents=True)
        try:
            data = self.cover(b, 320)
            if data:
                (root / tid / "_cover").write_bytes(data)
        except Exception:  # noqa: BLE001 — a cover for the trash list is a nicety
            pass
        self._release_file(b["rel"])
        self._retry(shutil.move, str(src), str(root / tid / src.name))
        self.bin.put(tid, {"id": b["id"], "rel": b["rel"], "name": src.name, "root": root.relative_to(_L.LIB_ROOT).as_posix(),
                           "library": b["library"], "libraryName": lib.get("name"), "owner": lib.get("owner"),
                           "series": b["series"], "collection": b.get("collection"), "label": b["label"], "title": b.get("title"),
                           "format": b.get("format"), "pages": b.get("pages"), "size": b.get("size"),
                           "marked": marked, "binned": int(time.time())})
        self.trash.delete(b["id"])
        self._prune_junk(src.parent)

    def trash_tick(self, now: float | None = None) -> bool:
        """The trash worker (called every few seconds): move what's due into .trash, delete what's been there
        long enough, forget marks and entries whose files are gone. True if files moved (→ rescan)."""
        now = now or time.time()
        moved = False
        for bid, m in self.trash.all().items():
            b = self.books.get(bid)
            if b is None:
                if not self.scanning and self._scanned:
                    self.trash.delete(bid)                      # deleted some other way meanwhile
                continue
            if now - m["at"] < TRASH_DELAY:
                continue
            try:
                self._to_bin(b, m["at"]); moved = True
            except OSError as e:
                log.warning("trash: couldn't move %s (%s) — trying again later", b["rel"], e)
        for tid, e in self.bin.all().items():
            d = _L.LIB_ROOT / e["root"] / tid
            if not d.is_dir():
                self.bin.delete(tid)                            # emptied by hand, or its account was removed
            elif now - e["binned"] > TRASH_KEEP:
                self.purge_bin([tid])
        return moved

    def bin_items(self, owner: str | None) -> list[dict]:
        now = time.time()
        return sorted(({**e, "tid": tid, "daysLeft": max(0, int((e["binned"] + TRASH_KEEP - now) // 86400) + 1)}
                       for tid, e in self.bin.all().items() if e.get("owner") == owner), key=lambda e: -e["binned"])

    def bin_cover(self, tid: str) -> bytes | None:
        e = self.bin.get(tid)
        f = _L.LIB_ROOT / e["root"] / tid / "_cover" if e else None
        return f.read_bytes() if f and f.is_file() else None

    def restore_bin(self, tids: list[str]) -> int:
        n = 0
        for tid in tids:
            e = self.bin.get(tid)
            if not e:
                continue
            lib = self.get_library(e["library"])
            if not lib or not (_L.LIB_ROOT / lib["path"]).is_dir():
                raise ValueError(f"“{e.get('libraryName') or 'Its library'}” no longer exists — create it again to restore this")
            src = _L.LIB_ROOT / e["root"] / tid / e["name"]
            dest = self._unique(_L.LIB_ROOT / e["rel"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._retry(shutil.move, str(src), str(dest))
            shutil.rmtree(_L.LIB_ROOT / e["root"] / tid, ignore_errors=True)
            self.bin.delete(tid)
            n += 1
        if n:
            self.scan()
        return n

    def purge_bin(self, tids: list[str]) -> int:
        """Delete for good."""
        n = 0
        for tid in tids:
            e = self.bin.get(tid)
            if not e:
                continue
            shutil.rmtree(_L.LIB_ROOT / e["root"] / tid, ignore_errors=True)
            self.bin.delete(tid)
            if e["id"] not in self.books:                        # (not if a restored copy is back under this id)
                self._forget(e["id"])
            n += 1
        return n
