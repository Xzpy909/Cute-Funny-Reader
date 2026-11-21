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
from .library import COL_MARK, JUNK_FILES, TRASH_DELAY, TRASH_DIR, TRASH_KEEP, log, safe_component


class TrashMixin:
    # ---- Trash
    # "Delete" doesn't delete: the book is marked (instant — it leaves the library views at once, and Undo /
    # Restore puts it back). After TRASH_DELAY the worker moves its file into <account>/.trash, where it stays
    # for the keep time (an app setting; TRASH_KEEP_DAYS is the default; 0 = never deleted by itself) before it is
    # really deleted. Reading progress and edits are kept until then, so a restore is complete.
    KEEP_CHOICES = (7, 14, 30, 90, 0)

    def trash_keep_days(self) -> int:
        """How long the trash keeps things, in days — 0: until it's emptied by hand."""
        v = self.settings.get("trashKeepDays")
        return int(v) if isinstance(v, int) and v in self.KEEP_CHOICES else TRASH_KEEP // 86400

    def set_trash_keep_days(self, days: int) -> int:
        if days not in self.KEEP_CHOICES:
            raise ValueError("Keep the trash for 7, 14, 30 or 90 days — or until it's emptied (0)")
        self.settings.put("trashKeepDays", days)
        return days

    def _days_left(self, deleted: float, now: float) -> int | None:
        keep = self.trash_keep_days()
        return None if not keep else max(0, int((deleted + keep * 86400 - now) // 86400) + 1)

    def trash_items(self, owner: str | None, libraries: set) -> list[dict]:
        """Everything in someone's trash, newest first — items still being moved out (marked) and items already in
        .trash (bin) alike: what it was, where it was, how big, and how long it stays."""
        now = time.time()
        out = []
        for bid, m in self.trash.all().items():
            b = self.books.get(bid)
            if not b or b["library"] not in libraries:
                continue
            lib = self.get_library(b["library"]) or {}
            out.append({"key": "b:" + bid, "kind": "marked", "id": bid, "series": b["series"], "label": b["label"],
                        "title": b.get("title"), "collection": b.get("collection"), "library": b["library"],
                        "libraryName": lib.get("name"), "libraryExists": True, "format": b.get("format"),
                        "pages": b.get("pages"), "size": b.get("size") or 0, "deleted": m["at"],
                        "daysLeft": self._days_left(m["at"], now)})
        for tid, e in self.bin.all().items():
            if e.get("owner") != owner:
                continue
            lib = self.get_library(e["library"])
            out.append({"key": "t:" + tid, "kind": "bin", "tid": tid, "id": e["id"], "series": e["series"],
                        "label": e["label"], "title": e.get("title"), "collection": e.get("collection"),
                        "library": e["library"], "libraryName": (lib or {}).get("name") or e.get("libraryName"),
                        "libraryExists": bool(lib and (_L.LIB_ROOT / lib["path"]).is_dir()), "format": e.get("format"),
                        "pages": e.get("pages"), "size": e.get("size") or 0, "deleted": e.get("marked") or e["binned"],
                        "daysLeft": self._days_left(e.get("marked") or e["binned"], now)})
        return sorted(out, key=lambda x: -x["deleted"])
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
            elif self.trash_keep_days() and now - (e.get("marked") or e["binned"]) > self.trash_keep_days() * 86400:
                self.purge_bin([tid])
        return moved

    def bin_items(self, owner: str | None) -> list[dict]:
        now = time.time()
        return sorted(({**e, "tid": tid, "daysLeft": self._days_left(e.get("marked") or e["binned"], now)}
                       for tid, e in self.bin.all().items() if e.get("owner") == owner), key=lambda e: -e["binned"])

    def bin_cover(self, tid: str) -> bytes | None:
        e = self.bin.get(tid)
        f = _L.LIB_ROOT / e["root"] / tid / "_cover" if e else None
        return f.read_bytes() if f and f.is_file() else None

    def restore_bin(self, tids: list[str], into: str | None = None) -> int:
        """Put trash items back where they were: a missing folder is recreated (a collection gets its marker back),
        a taken name gets a free one ("Name (2)"). An item whose library is gone needs `into` — another library's
        id — and lands there in the same collection / series folders; without it a LookupError names the items."""
        orphans = []
        for tid in tids:
            e = self.bin.get(tid)
            if e:
                lib = self.get_library(e["library"])
                if not lib or not (_L.LIB_ROOT / lib["path"]).is_dir():
                    orphans.append(tid)
        target = self.get_library(into) if into else None
        if orphans and not (target and (_L.LIB_ROOT / target["path"]).is_dir()):
            raise LookupError(orphans)
        n = 0
        for tid in tids:
            e = self.bin.get(tid)
            if not e:
                continue
            lib = target if tid in orphans else self.get_library(e["library"])
            base = _L.LIB_ROOT / lib["path"]
            if tid not in orphans and e["rel"].startswith(lib["path"] + "/"):
                dest = _L.LIB_ROOT / e["rel"]                    # where it was
            else:                                                # another library / the library's folder was renamed
                parts = [safe_component(x) for x in (e.get("collection"), e.get("series")) if x and safe_component(x)]
                dest = base.joinpath(*parts, e["name"])
            col = base / safe_component(e["collection"]) if e.get("collection") and safe_component(e["collection"]) else None
            col_new = bool(col) and not col.exists()
            dest = self._unique(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if col_new and col in dest.parents:
                (col / COL_MARK).touch()                         # recreated: still a collection, not a series folder
            src = _L.LIB_ROOT / e["root"] / tid / e["name"]
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
