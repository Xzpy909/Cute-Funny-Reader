"""Edited details: saved in the database (effective), the cover choice, and written into the files'
metadata.json on request (write_edits / write_metadata).

Part of the Library class (library.py: class Library(…, EditsMixin, …)) — methods and attributes unchanged; LIB_ROOT,
CONFIG_DIR and EMPTY_FOLDER_AFTER are read from library.py at call time (_L.…) so tests can swap them."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import zipfile

from pathlib import Path

from . import library as _L
from .library import build_metadata, info_yaml_extras, is_meta_file, is_video, log, split_tags


class EditsMixin:
    # ---- edited details: kept in the database until written into the files on request (write_edits)
    EDITABLE = ("author", "publisher", "genres", "tags", "summary", "year", "release", "direction")

    COVER_KEYS = ("coverPage", "seriesCover")

    @staticmethod
    def first_photo(b: dict) -> int:
        return next((i for i, n in enumerate(b.get("entries") or []) if not is_video(n)), -1)

    def file_cover_page(self, b: dict) -> int:
        """The cover page the file itself names (or its first photo)."""
        ents = b.get("entries") or []
        return ents.index(b["cover"]) if b.get("cover") in ents else self.first_photo(b)

    def effective(self, b: dict) -> dict:
        """The book as the reader shows it: the file's own details with the user's edits on top.
        Edits live in the database (instant, whatever the file's size) until written into the files on request
        (write_edits) — "unsaved" marks a book whose file could take them but doesn't hold them yet."""
        e = self.edits.get(b["id"])
        if not e:
            return b
        out = {**b, "edited": True, "unsaved": b.get("src") in self.WRITABLE}
        for k, v in e.items():
            if k == "direction":
                if v:
                    out["rtl"] = v == "rtl"
            elif k == "coverPage":
                ents = b.get("entries") or []
                i = v if isinstance(v, int) and v >= 0 else self.first_photo(b)
                if 0 <= i < len(ents) and not is_video(ents[i]):
                    out["cover"] = ents[i]
            elif k == "seriesCover":
                out["seriesCover"] = bool(v)
            else:
                out[k] = v
        return out

    def cover_tag(self, b: dict) -> str:
        """Part of a cover's cache key: changes when the chosen cover page does."""
        e = self.effective(b)
        ents = e.get("entries") or []
        return str(ents.index(e["cover"])) if e.get("cover") in ents else ""

    WRITABLE = ("cbz", "zip", "cb7", "folder")

    def _read_raw_meta(self, b: dict, kind: str) -> bytes | None:
        """Raw bytes of the book's metadata file of `kind` ("mj", "ci", "iy"), or None."""
        try:
            if b["src"] == "folder":
                f = next((p for p in (_L.LIB_ROOT / b["rel"]).iterdir() if p.is_file() and is_meta_file(p.name) == kind), None)
                return f.read_bytes() if f else None
            if b["src"] == "cb7":
                f = next((p for p in self._x7_dir(b).rglob("*") if p.is_file() and is_meta_file(p.name) == kind), None)
                return f.read_bytes() if f else None
            with zipfile.ZipFile(_L.LIB_ROOT / b["rel"]) as z:
                n = next((n for n in z.namelist() if is_meta_file(n) == kind), None)
                return z.read(n) if n else None
        except Exception:  # noqa: BLE001
            return None

    def _read_mj(self, b: dict) -> dict:
        raw = self._read_raw_meta(b, "mj")
        try:
            d = json.loads(raw.decode("utf-8-sig")) if raw else {}
        except Exception:  # noqa: BLE001
            return {}
        return d if isinstance(d, dict) else {}

    _KEEP = object()

    def write_metadata(self, b: dict, fields: dict, thumbnail=_KEEP, series_cover=_KEEP):
        """Write metadata.json into the book (archive or photo folder); ComicInfo.xml and info.yaml are dropped —
        their content is already carried over into metadata.json (info.yaml's source/id/event under "info").
        thumbnail: cover page index, None = back to the first photo · series_cover: this book is the series' cover."""
        path = _L.LIB_ROOT / b["rel"]
        doc = build_metadata(self.effective(b), self._read_mj(b), fields)
        iy = self._read_raw_meta(b, "iy")
        if iy and "info" not in doc and (extra := info_yaml_extras(iy)):
            doc["info"] = extra
        if thumbnail is not self._KEEP:
            if thumbnail is None:
                doc.pop("thumbnail", None)
            else:
                doc["thumbnail"] = int(thumbnail)
        elif b.get("cover") and b.get("entries") and b["entries"].index(b["cover"]) !=\
                next((i for i, n in enumerate(b["entries"]) if not is_video(n)), -1):
            doc.setdefault("thumbnail", b["entries"].index(b["cover"]))     # keep a chosen cover page
        if series_cover is not self._KEEP:
            if series_cover:
                doc["seriesCover"] = True
            else:
                doc.pop("seriesCover", None)
        data = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
        self._stale(path, path.parent)             # the file changes in place: re-read it at the next scan
        with self._busy:
            self._write_meta_file(b, path, data)

    def _swap_in(self, tmp: Path, path: Path, rel: str):
        """Replace `path` with `tmp`: our cached handles closed and kept closed, brief Windows locks retried."""
        for i in range(8):
            with self._zip_lock:
                self._close_under(rel)
                try:
                    os.replace(tmp, path)
                    return
                except PermissionError as e:
                    if i == 7:
                        raise OSError(e.errno, "the file is open somewhere (a viewer, Explorer, antivirus) — close it and try again") from e
            time.sleep(min(0.25 * (i + 1), 1.5))

    def _write_meta_file(self, b: dict, path: Path, data: bytes):
        with self._zip_lock:                       # drop cached handles of this archive
            self._close_under(b["rel"])
        if b["src"] == "folder":
            (path / "metadata.json").write_bytes(data)
            for f in path.iterdir():
                if is_meta_file(f.name) in ("ci", "iy"):
                    f.unlink()
        elif b["src"] == "cb7":
            import py7zr, tempfile
            src = self._x7_dir(b)
            tmp = path.with_name("." + path.name + ".tmp")
            with py7zr.SevenZipFile(tmp, "w") as z:
                for f in sorted(src.rglob("*")):
                    if f.is_file() and not is_meta_file(f.name):
                        z.write(f, f.relative_to(src).as_posix())
                with tempfile.TemporaryDirectory() as td:
                    mf = Path(td) / "metadata.json"; mf.write_bytes(data)
                    z.write(mf, "metadata.json")
            self._swap_in(tmp, path, b["rel"])
        else:
            tmp = path.with_name("." + path.name + ".tmp")
            try:
                with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w") as zout:
                    for info in zin.infolist():
                        if is_meta_file(info.filename):
                            continue
                        if info.is_dir():
                            zout.writestr(info, b"")
                            continue
                        with zin.open(info) as fi, zout.open(info, "w", force_zip64=info.file_size > 0x7FFFFFFF) as fo:
                            shutil.copyfileobj(fi, fo, 1 << 20)
                    zout.writestr("metadata.json", data, zipfile.ZIP_DEFLATED)
                self._swap_in(tmp, path, b["rel"])
            finally:
                tmp.unlink(missing_ok=True)

    def set_cover(self, sid: str, book_id: str | None, page: int | None):
        """Pick the series' cover: page `page` of book `book_id` (a photo, not a video) — or book_id None to go
        back to the default (first book, first photo). Kept in the database (see effective) — only where it differs
        from what the files say — until written into metadata.json ("thumbnail", "seriesCover") on request."""
        books = self.series_books(sid)
        if not books:
            raise KeyError(sid)
        target = None
        if book_id:
            target = next((x for x in books if x["id"] == book_id), None)
            if not target:
                raise ValueError("That book isn't in this series")
            if target.get("format") != "images" or target.get("src") not in self.WRITABLE:
                raise ValueError("This book can't hold a cover choice (only archives and photo sets can)")
            if page is None or not (0 <= page < len(target["entries"])) or is_video(target["entries"][page]):
                raise ValueError("Pick a photo page as the cover")
        for x in books:
            if x.get("src") not in self.WRITABLE or x.get("format") != "images":
                continue
            e = dict(self.edits.get(x["id"]) or {})
            flag = target is not None and x["id"] == target["id"] and len(books) > 1
            if flag == bool(x.get("seriesCover")):
                e.pop("seriesCover", None)
            else:
                e["seriesCover"] = flag
            want = page if target is not None and x["id"] == target["id"] else\
                self.first_photo(x) if book_id is None else None          # None: this book's page stays
            if want is not None:
                if want == self.file_cover_page(x):
                    e.pop("coverPage", None)
                else:
                    e["coverPage"] = want
            if e:
                self.edits.put(x["id"], e)
            else:
                self.edits.delete(x["id"])
        self.rev += 1

    def write_edits(self, sid: str) -> int:
        """Write the series' saved edits (details, tags, cover choice) into its files' metadata.json, then
        forget them — the files now say the same. Returns how many files were written."""
        books = self.series_books(sid)
        if not books:
            raise KeyError(sid)
        done, errors = 0, []
        for b in books:
            e = self.edits.get(b["id"])
            if not e or b.get("src") not in self.WRITABLE:
                continue
            fields = {k: v for k, v in e.items() if k in self.EDITABLE}
            thumb, flag = self._KEEP, self._KEEP
            if "coverPage" in e:
                i = e["coverPage"] if isinstance(e["coverPage"], int) and e["coverPage"] >= 0 else self.first_photo(b)
                thumb = None if i == self.first_photo(b) else i
            if "seriesCover" in e:
                flag = bool(e["seriesCover"])
            try:
                self.write_metadata(b, fields, thumbnail=thumb, series_cover=flag)
                self.edits.delete(b["id"])
                done += 1
            except Exception as ex:  # noqa: BLE001
                log.warning("could not write metadata into %s: %s", b["rel"], ex)
                errors.append(b["file"])
        if done:
            self.scan()
        if errors:
            raise OSError("Couldn’t write into: " + ", ".join(errors[:5]))
        return done

    def edit_series(self, sid: str, fields: dict, reset: bool = False) -> int:
        books = self.series_books(sid)
        if not books:
            raise KeyError(sid)
        fields = dict(fields or {})
        # series-wide tag edits arrive as a difference, applied to each chapter's own list — so a tag that only
        # some chapters carry survives an edit of the series' shared tags
        t_add = split_tags(", ".join(str(x) for x in (fields.pop("tagsAdd", None) or [])))
        t_rem = {t.lower() for t in split_tags(", ".join(str(x) for x in (fields.pop("tagsRemove", None) or [])))}
        t_base = split_tags(", ".join(str(x) for x in (fields.pop("tagsBase", None) or [])))   # the new series tags
        clean = {}
        for k, v in fields.items():
            if k not in self.EDITABLE:
                continue
            if k in ("genres", "tags"):
                v = split_tags(", ".join(str(x) for x in (v or [])))
            else:
                v = re.sub(r"\s+", " ", str(v or "")).strip() if k != "summary" else str(v or "").strip()[:4000]
            clean[k] = v
        if "direction" in clean and clean["direction"] not in ("rtl", "ltr"):
            clean["direction"] = ""
        for b in books:
            per = dict(clean)
            if (t_add or t_rem) and "tags" not in per:
                own = self.effective(b).get("tags") or []
                if not own and t_base:                  # an untagged chapter inherits the series' tags
                    per["tags"] = t_base
                else:
                    cur = [t for t in own if t.lower() not in t_rem]
                    have = {t.lower() for t in cur}
                    per["tags"] = cur + [t for t in t_add if t.lower() not in have]
            if reset:
                self.edits.delete(b["id"])
            elif per:                                   # into the database: instant, whatever the file's size —
                ov = {**self.edits.get(b["id"], {}), **per}     # written into the files on request (write_edits)
                if "direction" in per:
                    ov.pop("rtl", None)                 # (older edits kept the direction as "rtl")
                self.edits.put(b["id"], ov)
        self.rev += 1
        return len(books)
