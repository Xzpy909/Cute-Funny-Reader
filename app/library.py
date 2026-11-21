"""Library scanning, indexing and archive access for Cute&Funny Reader."""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import posixpath
import random
import shutil
import threading
import time
import zipfile
import uuid
from collections import OrderedDict
from pathlib import Path

from PIL import Image

from .store import Db, Identities, Names, Store
# split out of this file — imported back so every `library.X` / `from .library import X` keeps working
from .formats import IMG_EXT, JXL_EXT, HEIC_EXT, TRANSCODE_EXT, LOSSLESS_EXT, BROWSER_UNSAFE, VIDEO_EXT, BOOK_EXT, MEDIA_EXT, is_video  # noqa: F401
from .names import natural_key, make_id, BRACKET_GROUP, strip_brackets, SQUARE, NUM, tidy, parse_number, fmt_num, UNSAFE, safe_component, safe_rel, strip_tags, NAME_CREDIT, CIRCLE_ARTIST, NOT_A_CREDIT, credits_from_name, clean_title_credits, VARIANT_WORD, cosplay_name, split_variant, MAX_VARIANT, MAX_FREE, SEPARATOR, _tail, _usual, _variant_pair, variant_groups, sibling_works, joins_existing, same_case, set_of, cosplay_plan, name_credits, guess_type  # noqa: F401
from .meta import parse_comicinfo, parse_metadata_json, merge_meta, tags_to_json, build_metadata, META_FILES, is_meta_file, read_meta, _yaml_load, INFO_EXTRA, parse_info_yaml, info_yaml_extras, split_tags  # noqa: F401
try:                                    # JPEG XL decoding for Pillow (registers .jxl) — optional, see requirements.txt
    import pillow_jxl  # noqa: F401
    JXL_OK = True
except ImportError:  # pragma: no cover
    JXL_OK = False
try:                                    # HEIC / HEIF decoding for Pillow — optional, see requirements.txt
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except ImportError:  # pragma: no cover
    HEIC_OK = False

from . import epub as epubmod

log = logging.getLogger("cfreader")

LIB_ROOT = Path(os.environ.get("LIBRARY_DIR", "/data"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/config"))
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL", "600"))
TRASH_DIR = ".trash"                                                    # inside each account's folder (hidden from scans)
TRASH_DELAY = int(os.environ.get("TRASH_DELAY", "600"))                 # seconds a trashed item stays in place (undo)
TRASH_KEEP = int(os.environ.get("TRASH_KEEP_DAYS", "30")) * 86400       # then this long in the trash before it's deleted
EMPTY_FOLDER_AFTER = int(os.environ.get("EMPTY_FOLDER_HOURS", "24")) * 3600   # empty folders are removed after this
JUNK_FILES = {".collection", "thumbs.db", "desktop.ini", ".ds_store"}
# JPEG XL / HEIC pages converted to PNG for the browser: unused this long → dropped (rebuilt on the next open).
# TRANSCODE_CACHE_DAYS; the old name JXL_CACHE_DAYS still works.
TRANSCODE_TTL = float(os.environ.get("TRANSCODE_CACHE_DAYS") or os.environ.get("JXL_CACHE_DAYS") or "7") * 86400
INDEX_VERSION = 16   # bump whenever parsing rules change → everything is re-read once
THUMB_WIDTHS = (120, 200, 320, 480)
LIB_TYPES = ("comics", "manga", "cosplay")
UNSORTED = "Unsorted"
COL_MARK = ".collection"   # marker file: this folder is a collection of series, not a series


def series_key(lib: str, col: str | None, series: str) -> str:
    return make_id(lib, series.lower()) if not col else make_id(lib, col.lower(), series.lower())


def collection_key(lib: str, col: str) -> str:
    return make_id(lib, "col", col.lower())
PALETTE = ("#ff5c8a", "#ffd84d", "#5ee6c1", "#7aa8ff", "#b388ff", "#ff9f5a")

Image.MAX_IMAGE_PIXELS = 200_000_000  # tall webtoon strips are legitimately huge

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/webm", ".webm")


def media_sort(names: list[str]) -> list[str]:
    return sorted(names, key=lambda n: (not posixpath.basename(n).lower().startswith("cover."), natural_key(n)))


def _cover_is_preview(z: zipfile.ZipFile, names: list[str]) -> bool:
    """Some downloaders add a cover.* that is only a shrunken copy of the first page (for a long strip: a
    sliver 99 px wide). Shown as page 1 it is a blurry duplicate — so it is left out of the pages.
    A real cover (its own artwork: other proportions, or no smaller than the page) stays."""
    if len(names) < 2 or not posixpath.basename(names[0]).lower().startswith("cover.") or is_video(names[1]):
        return False
    try:
        sizes = []
        for n in names[:2]:
            with z.open(n) as f, Image.open(f) as im:       # only the header is read
                sizes.append(im.size)
        (cw, ch), (pw, ph) = sizes
        return cw * ch < pw * ph * 0.9 and abs(cw / ch - pw / ph) <= 0.03 * (pw / ph)
    except Exception:  # noqa: BLE001
        return False


def parse_cbz(path: Path):
    with zipfile.ZipFile(path) as z:
        names = [
            i.filename for i in z.infolist()
            if not i.is_dir()
            and i.filename.lower().endswith(MEDIA_EXT)
            and "__MACOSX" not in i.filename
            and not posixpath.basename(i.filename).startswith(".")
        ]
        names = media_sort(names)
        if _cover_is_preview(z, names):
            names = names[1:]
        found = {}
        for n in z.namelist():
            k = is_meta_file(n)
            if k and k not in found:
                found[k] = n
        meta = read_meta({k: z.read(n) for k, n in found.items()})
    return names, meta


REPACK_EXT = (".cb7", ".cbr", ".7z", ".rar")      # uploaded in these formats -> converted and stored as .cbz
REPACK_KIND = {".cb7": "cb7", ".7z": "cb7", ".cbr": "cbr", ".rar": "cbr"}


def is_rar(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(7).startswith(b"Rar!\x1a\x07")


def repack_to_cbz(src: Path, dest: Path, kind: str):
    """.cb7 / .cbr -> .cbz. Images and videos are stored as-is (they're compressed already), so pages open
    instantly and a later metadata edit is a quick rewrite. Only pages, videos and metadata files are kept."""
    import subprocess
    import tempfile
    work = CONFIG_DIR / "cache" / "repack"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as td:
        out = Path(td)
        if kind == "cb7":
            import py7zr
            with py7zr.SevenZipFile(src) as z:
                if z.needs_password():
                    raise ValueError("That 7-Zip archive is password-protected")
                targets = [f.filename for f in z.list() if not f.is_directory and _safe_member(f.filename)]
            with py7zr.SevenZipFile(src) as z:
                z.extract(path=out, targets=targets)
        else:
            tools = [["unar", "-q", "-f", "-D", "-o", str(out), str(src)],
                     ["bsdtar", "-x", "-f", str(src), "-C", str(out)]]
            for cmd in tools:
                if not shutil.which(cmd[0]):
                    continue
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL)
                if r.returncode == 0:
                    break
                log.warning("%s failed on %s: %s", cmd[0], src.name, (r.stderr or r.stdout).strip()[:300])
            else:
                raise ValueError("Couldn't unpack that RAR archive (is it password-protected or damaged?)")
        files = []
        for f in out.rglob("*"):
            rel = f.relative_to(out).as_posix()
            if not f.is_file() or any(p.startswith(".") or p == "__MACOSX" for p in rel.split("/")):
                continue
            if f.name.lower().endswith(MEDIA_EXT) or is_meta_file(f.name):
                files.append((rel, f))
        if not any(r.lower().endswith(MEDIA_EXT) for r, _ in files):
            raise ValueError("There are no images or videos inside that archive")
        files.sort(key=lambda x: natural_key(x[0]))
        part = dest.with_name(f".{dest.name}.part")
        try:
            with zipfile.ZipFile(part, "w", allowZip64=True) as z:
                for rel, f in files:
                    z.write(f, rel, zipfile.ZIP_DEFLATED if is_meta_file(rel) else zipfile.ZIP_STORED)
            os.replace(part, dest)
        finally:
            part.unlink(missing_ok=True)


def _safe_member(n: str) -> bool:
    p = n.replace("\\", "/")
    parts = p.split("/")
    return p not in ("", ".", "..") and not p.startswith("/") and ".." not in parts and ":" not in parts[0]


def parse_cb7(path: Path):
    import py7zr, tempfile
    with py7zr.SevenZipFile(path) as z:
        all_names = z.getnames()
    names = media_sort([n for n in all_names if n.lower().endswith(MEDIA_EXT)
                        and "__MACOSX" not in n and not posixpath.basename(n).startswith(".")])
    found = {}
    for n in all_names:
        k = is_meta_file(n)
        if k and k not in found:
            found[k] = n
    data = {}
    if found:
        with tempfile.TemporaryDirectory() as td:
            with py7zr.SevenZipFile(path) as z:
                z.extract(path=td, targets=list(found.values()))
            for k, n in found.items():
                try:
                    data[k] = (Path(td) / n).read_bytes()
                except OSError:
                    pass
    return names, read_meta(data)


def pick_cover(entries: list[str], meta: dict) -> str | None:
    """The cover page: info.yaml's Thumbnail (0-based) if it points at a photo, else the first photo."""
    try:
        i = int(meta.get("thumbnail", ""))
        if 0 <= i < len(entries) and not is_video(entries[i]):
            return entries[i]
    except ValueError:
        pass
    return next((n for n in entries if not is_video(n)), None)


def parse_book(path: Path, rel: str, inner: str, library: str, st, media: list[str] | None = None) -> dict:
    parts = inner.split("/")
    is_set = media is not None          # a plain folder of photos (+ videos) = one book
    stem = path.name if is_set else path.stem
    kind, number, before = parse_number(stem)
    in_folder = False   # placement (collection / series folder) is decided per scan in place_book()
    if number is not None and not tidy(before):
        series = UNSORTED   # e.g. "Ch.0012 (en) [group].cbz" with no series name: group them together
    else:
        series = tidy(before) or tidy(strip_brackets(stem))
    ext = "" if is_set else path.suffix.lower()

    b = {
        "id": make_id(rel), "rel": rel, "file": path.name, "library": library,
        "size": st.st_size, "mtime": int(st.st_mtime),
        "kind": kind, "number": number, "src": "folder" if is_set else ext[1:], "dims": None,
    }

    if is_set:
        data = {}
        try:
            for f in path.iterdir():
                k = is_meta_file(f.name)
                if k and f.is_file():
                    data[k] = f.read_bytes()
        except OSError:
            pass
        meta = clean_title_credits(read_meta(data), stem, kind in ("chapter", "volume"))
        b["seriesCover"] = bool(meta.get("seriescover"))
        first_img = pick_cover(media, meta)
        b.update(format="images", entries=media, chapters=[], pages=len(media), cover=first_img,
                 videos=[i for i, n in enumerate(media) if is_video(n)], rtl=None)
        title = meta.get("title", "")
        if meta.get("series") and number is None:
            series = meta["series"]
    elif ext in VIDEO_EXT:                     # a standalone video (Cosplay libraries)
        b.update(format="video", entries=[path.name], chapters=[], pages=1, cover=None, rtl=None)
        meta, title = {}, ""
    elif ext == ".epub":
        e = epubmod.parse_epub(path)
        meta = clean_title_credits(e["meta"], stem, kind in ("chapter", "volume"))
        if e["pages"]:  # fixed-layout image EPUB -> treat like a comic
            b.update(format="images", entries=e["pages"], chapters=[], pages=len(e["pages"]))
        else:
            b.update(format="epub", entries=[], chapters=e["chapters"], pages=len(e["chapters"]))
        b["cover"] = e["cover"]
        b["rtl"] = True if e["rtl"] else None
        title = ""
    else:
        names, meta = parse_cb7(path) if ext == ".cb7" else parse_cbz(path)
        meta = clean_title_credits(meta, stem, kind in ("chapter", "volume"))
        b["seriesCover"] = bool(meta.get("seriescover"))
        if not names:
            raise ValueError("archive has no images")
        first_img = pick_cover(names, meta)
        b.update(format="images", entries=names, chapters=[], pages=len(names), cover=first_img,
                 videos=[i for i, n in enumerate(names) if is_video(n)])
        b["rtl"] = True if meta.get("manga", "").lower() == "yesandrighttoleft" else None
        if number is None and meta.get("number"):
            try:
                number, kind = float(meta["number"]), "chapter"
            except ValueError:
                pass
        if not in_folder and meta.get("series") and series in (UNSORTED, tidy(strip_brackets(stem))):
            series = meta["series"]
        title = meta.get("title", "")
        if meta.get("manga", "").lower() in ("yes", "yesandrighttoleft"):
            b["isManga"] = True

    if meta.get("direction") in ("rtl", "ltr"):
        b["rtl"] = meta["direction"] == "rtl"
    if number is None and not title:
        title = meta.get("title", "") or tidy(strip_brackets(stem))
    label = (
        f"{'Vol.' if kind == 'volume' else 'Chapter'} {fmt_num(number)}" if number is not None
        else (title or tidy(strip_brackets(stem)))
    )
    if label == title:
        title = ""

    b.update(
        kind=kind, number=number, series=series or UNSORTED, looseSeries=series or UNSORTED,
        seriesId=make_id(library, (series or UNSORTED).lower()),
        label=label, title=title,
        author=meta.get("writer", ""), publisher=meta.get("publisher", ""),
        summary=strip_tags(meta.get("summary", ""))[:1200],
        genres=split_tags(meta.get("genre", "")), tags=split_tags(meta.get("tags", "")),
        release=meta.get("format", ""), year=meta.get("year", ""),
    )
    return b


def is_raw(b: dict) -> bool:
    """A book in a lossless format: (nearly) all its photos are PNG / BMP / TIFF. A cover.jpg alone doesn't spoil it."""
    if b.get("format") != "images":
        return False
    imgs = [n for n in b.get("entries") or [] if not is_video(n)]
    pages = [n for n in imgs if not posixpath.basename(n).lower().startswith("cover.")] or imgs
    return bool(pages) and sum(n.lower().endswith(LOSSLESS_EXT) for n in pages) >= 0.9 * len(pages)


def _mostly(b: dict, exts: tuple) -> bool:
    if b.get("format") != "images":
        return False
    imgs = [n for n in b.get("entries") or [] if not is_video(n)]
    return bool(imgs) and sum(n.lower().endswith(exts) for n in imgs) >= 0.9 * len(imgs)


def is_jxl(b: dict) -> bool:
    """A book whose photos are (nearly all) JPEG XL → the JPEG XL pill, and transcoding before the reader opens."""
    return _mostly(b, JXL_EXT)


def is_heic(b: dict) -> bool:
    """Same for HEIC / HEIF (phone photos) → the HEIC pill."""
    return _mostly(b, HEIC_EXT)


def is_avif(b: dict) -> bool:
    """A book whose photos are (nearly all) AVIF — optimized, or uploaded that way → the AVIF pill."""
    return _mostly(b, (".avif",))


def needs_transcode(b: dict) -> bool:
    return b.get("format") == "images" and any(n.lower().endswith(TRANSCODE_EXT) for n in b.get("entries") or [])


def place_book(b: dict, lib_id: str, lib_path: str, inner: str, cols: set, cosplay: bool = False):
    """Work out collection + series from where the file sits in the library:
       <lib>/<file>                       loose series (name from filename)
       <lib>/<Series>/<file>              series folder
       <lib>/<Collection>/<file>          loose series inside a collection
       <lib>/<Collection>/<Series>/<file> series folder inside a collection"""
    parts = inner.split("/")
    col = parts[0] if len(parts) >= 2 and parts[0] in cols else None
    if col:
        parts = parts[1:]
    base = lib_path + ("/" + col if col else "")
    if len(parts) >= 2:
        series, sdir = (tidy(SQUARE.sub("", parts[0])) or parts[0]), base + "/" + parts[0]
    else:
        series, sdir = b.get("looseSeries") or b["series"], None
    b.update(series=series, collection=col, base=base, sdir=sdir, library=lib_id,
             collectionId=collection_key(lib_id, col) if col else None,
             seriesId=series_key(lib_id, col, series))
    # natural keys (change on rename/move); the scan swaps the ids above for permanent ones (store.Names)
    b["seriesKey"], b["collectionKey"] = b["seriesId"], b["collectionId"]
    name_credits(b, cosplay)
    if cosplay and b.get("format") != "epub":
        work = cosplay_name(b["file"] if b.get("src") == "folder" else posixpath.splitext(b["file"])[0])["work"]
        rest = work[len(series):].strip(" -_.") if series and work.lower().startswith(series.lower()) else ""
        b["label"] = rest or work or b["label"]


def _remove(src: Path, b: dict):
    """Delete a book: the file, or for a photo-set folder its media (+ the folder once empty)."""
    if b.get("src") == "folder" and src.is_dir():
        for n in b.get("entries", []):
            (src / n).unlink(missing_ok=True)
        for extra in ("ComicInfo.xml", "metadata.json", "Thumbs.db", "desktop.ini", ".DS_Store"):
            (src / extra).unlink(missing_ok=True)
        try:
            src.rmdir()
        except OSError:
            pass
    else:
        src.unlink(missing_ok=True)


# ----------------------------------------------------------------- library
# the Library class is put together from its areas (one file each); they import what they need from here,
# so they're imported only now, after everything above is defined
from .libfiles import FilesMixin  # noqa: E402
from .libedits import EditsMixin  # noqa: E402
from .libtrash import TrashMixin  # noqa: E402
from .libscan import ScanMixin  # noqa: E402
from .libmedia import MediaMixin  # noqa: E402


class Library(FilesMixin, EditsMixin, TrashMixin, ScanMixin, MediaMixin):
    def __init__(self):
        self.lock = threading.RLock()
        self.books: dict[str, dict] = {}
        self.last_scan: float | None = None
        self.scanning = False
        self.rev = 0                                     # bumps whenever the scanned library changes
        self._sig = None
        self.scan_error: str | None = None
        self.thumb_dir = CONFIG_DIR / "cache" / "thumbs"
        self.panel_dir = CONFIG_DIR / "cache" / "panels"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.panel_dir.mkdir(parents=True, exist_ok=True)
        self.db = Db.at(CONFIG_DIR / "reader.db")
        self.progress = Store(self.db, "progress", CONFIG_DIR / "progress.json")
        self.edits = Store(self.db, "edits", CONFIG_DIR / "edits.json")      # user edits to metadata, per book id
        self.trash = Store(self.db, "trash")      # book id → {"at"}: marked for the trash, still in its place
        self.bin = Store(self.db, "bin")          # trash id → what was moved into .trash, and where it came from
        self.settings = Store(self.db, "settings")
        self.jobs = None                                 # the job registry (app/jobs.py), set by the server: long work shows there  # app-wide settings changed in the app (e.g. "trashKeepDays")
        self.ids = Identities(self.db)                                        # permanent book ids, whatever the path
        self.groups = Names(self.db)                                          # permanent series / collection ids
        try:
            self.libraries: list[dict] = json.loads((CONFIG_DIR / "libraries.json").read_text("utf-8"))
        except Exception:
            self.libraries = []
        for l in self.libraries:   # migrate pre-type libraries
            if "type" not in l:
                l["type"] = "manga" if l.get("rtl") else guess_type(l["name"])
        try:
            self.ignored: list[str] = json.loads((CONFIG_DIR / "ignored.json").read_text("utf-8"))
        except Exception:
            self.ignored = []
        self._scan_lock = threading.Lock()
        self._x7_lock = threading.Lock()
        self._zips: OrderedDict = OrderedDict()
        self._transcode_jobs: dict[str, dict] = {}
        self._transcode_touched: dict[str, float] = {}
        # background preparation (like Immich / Jellyfin jobs): books waiting to be prepared, newest first
        self._prep = threading.Condition()
        self._prep_queue: OrderedDict = OrderedDict()
        self._prep_busy = False
        self.display_hint = 2560                         # screen size the reader last asked for
        self._tidy_failed: set[str] = set()
        self._saved_once = False
        self._dircache: dict[str, tuple] = {}            # folder → (mtime, sub-folders, files) — see _ls
        self._ls_memo: dict[str, tuple] = {}
        self._racy, self._scanned, self._root_m, self._swept, self._emptied = False, False, None, 0.0, 0.0
        self._dir_sig, self._folder_info = None, None    # cached (collections, empty series) — see folder_info              # cosplay tidy: entries that couldn't move (file open)
        self._zip_lock = threading.Lock()
        # held while the background worker (or a page-size measurement) has a book open on its own handle:
        # a rename or rewrite waits for it — on Windows hosts an open file blocks both
        self._busy = threading.RLock()
        self._dirty = False
        self.accounts = None          # set by the server: auth.Accounts — each account owns /data/<folder>/<libraries>
        self._load_index()

    # ---- index persistence
    def _load_index(self):
        try:
            data = json.loads((CONFIG_DIR / "index.json").read_text("utf-8"))
            if data.get("version") == INDEX_VERSION:
                self.books = {b["id"]: b for b in data["books"]}
                self.last_scan = data.get("lastScan")
                if data.get("folders"):
                    self._folder_info = (data["folders"][0], data["folders"][1])
                # folder listings from before the restart: the first scan then only re-reads changed folders
                dirs = json.loads((CONFIG_DIR / "dirs.json").read_text("utf-8"))
                if dirs.get("root") == str(LIB_ROOT):
                    self._dircache = {d: (v[0], v[1], v[2]) for d, v in dirs["dirs"].items()}
        except Exception:
            pass

    def _save_index(self):
        with self.lock:
            payload = {"version": INDEX_VERSION, "lastScan": self.last_scan, "books": list(self.books.values()),
                       "folders": list(self._folder_info) if self._folder_info else None}
            dirs = {"root": str(LIB_ROOT), "dirs": dict(self._dircache)}
        tmp = CONFIG_DIR / "dirs.tmp"                # written first: listings without their books are harmless,
        tmp.write_text(json.dumps(dirs, ensure_ascii=False), "utf-8")      # books without listings just get re-read
        tmp.replace(CONFIG_DIR / "dirs.json")
        tmp = CONFIG_DIR / "index.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
        tmp.replace(CONFIG_DIR / "index.json")
        self._dirty = False

    # ---- libraries (user-created)
    def _save_libs(self):
        tmp = CONFIG_DIR / "libraries.tmp"
        tmp.write_text(json.dumps(self.libraries, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(CONFIG_DIR / "libraries.json")
        (CONFIG_DIR / "ignored.json").write_text(json.dumps(self.ignored, ensure_ascii=False), "utf-8")

    def discover(self) -> int:
        """Every folder inside an account's folder (/data/<account>/<folder>) becomes a library of that
        account (random colour, left-to-right), unless the account removed that library before."""
        if not LIB_ROOT.is_dir() or not self.accounts or not self.accounts.items:
            return 0
        used = {l["path"].lower() for l in self.libraries}
        ignored = {p.lower() for p in self.ignored}
        added = 0
        for acc in self.accounts.items:
            root = LIB_ROOT / acc["folder"]
            try:
                root.mkdir(parents=True, exist_ok=True)
                subs = sorted(root.iterdir(), key=lambda p: p.name.lower())
            except OSError:
                continue
            for d in subs:
                rel = f"{acc['folder']}/{d.name}"
                if not d.is_dir() or d.name.startswith(".") or rel.lower() in used or rel.lower() in ignored:
                    continue
                name, n = d.name, 2
                while any(l.get("owner") == acc["id"] and l["name"].lower() == name.lower() for l in self.libraries):
                    name, n = f"{d.name} {n}", n + 1
                with self.lock:
                    ltype = guess_type(d.name)
                    self.libraries.append({"id": uuid.uuid4().hex[:10], "name": name, "path": rel, "owner": acc["id"],
                                           "rtl": ltype == "manga", "type": ltype, "color": random.choice(PALETTE),
                                           "created": int(time.time()), "auto": True})
                used.add(rel.lower())
                added += 1
                log.info("discovered library folder %s", rel)
        if added:
            with self.lock:
                self._save_libs()
        return added

    def claim_orphans(self, acc: dict) -> int:
        """First account: everything that was in /data before accounts existed moves into its folder."""
        root = LIB_ROOT / acc["folder"]
        root.mkdir(parents=True, exist_ok=True)
        keep = self.accounts.folders() if self.accounts else {acc["folder"].lower()}
        moved = 0
        with self._scan_lock:
            for d in sorted(LIB_ROOT.iterdir(), key=lambda p: p.name.lower()):
                if not d.is_dir() or d.name.startswith(".") or d.name.lower() in keep:
                    continue
                dest = self._unique(root / d.name)
                self._migrate_prefix(d.name, f"{acc['folder']}/{dest.name}")
                shutil.move(str(d), str(dest))
                for l in self.libraries:
                    if l["path"].split("/")[0] == d.name:
                        l["path"] = f"{acc['folder']}/{dest.name}" + l["path"][len(d.name):]
                moved += 1
            with self.lock:
                for l in self.libraries:
                    if not l.get("owner"):
                        l["owner"] = acc["id"]
                self.ignored = []
                self._save_libs()
        if moved:
            log.info("moved %d existing folder(s) into %s", moved, root)
        return moved

    def owned(self, uid: str) -> set:
        return {l["id"] for l in self.libraries if l.get("owner") == uid}

    def forget_owner(self, uid: str, folder: str, delete_files: bool):
        """An account was deleted: drop its libraries (and optionally its folder)."""
        with self.lock:
            ids = self.owned(uid)
            for b in self.books.values():
                if b["library"] in ids:
                    self._forget(b["id"])
            self.libraries = [l for l in self.libraries if l["id"] not in ids]
            self.books = {k: b for k, b in self.books.items() if b["library"] not in ids}
            self._save_libs()
        self._save_index()
        root = LIB_ROOT / folder
        if delete_files and root.is_dir() and LIB_ROOT.resolve() in root.resolve().parents:
            shutil.rmtree(root)

    def drop_missing(self) -> int:
        """A library whose folder was deleted from disk disappears from the app.
        (Skipped when /data itself is missing or empty, e.g. a drive that isn't mounted.)"""
        if not LIB_ROOT.is_dir() or not any(LIB_ROOT.iterdir()):
            return 0
        owners = {a["id"] for a in self.accounts.items} if self.accounts else set()
        gone = [l for l in self.libraries if not (LIB_ROOT / l["path"]).is_dir() or (owners and l.get("owner") not in owners)]
        if not gone:
            return 0
        with self.lock:
            ids = {l["id"] for l in gone}
            self.libraries = [l for l in self.libraries if l["id"] not in ids]
            self.ignored = [p for p in self.ignored if p.lower() not in {l["path"].lower() for l in gone}]
            self.books = {k: b for k, b in self.books.items() if b["library"] not in ids}
            self._save_libs()
        log.info("removed %d librar(y/ies) whose folder no longer exists: %s", len(gone), ", ".join(l["name"] for l in gone))
        return len(gone)

    def track(self, kind: str, title: str, owner: str | None = None, unit: str = "items", total=None, after: float = 1.0):
        """Long work reported as a job (a scan, the trash mover, a conversion) — see jobs.Tracker."""
        from .jobs import Tracker
        return self.jobs.track(kind, title, owner, unit, total, after) if self.jobs else Tracker(None, kind, title, owner, unit, total, after)

    def get_library(self, lid: str) -> dict | None:
        return next((l for l in self.libraries if l["id"] == lid), None)

    def folders(self, base: str) -> list[dict]:
        used = {l["path"].lower() for l in self.libraries}
        out = []
        root = LIB_ROOT / base
        if root.is_dir():
            for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if d.is_dir() and not d.name.startswith("."):
                    rel = (f"{base}/{d.name}" if base else d.name).lower()
                    # Folders that are already libraries are never offered, so they aren't counted (counting
                    # walked every file of every library before the "Add library" dialog could open).
                    # A free folder is counted, but only up to a point: a rough number is all the hint needs.
                    n = 0
                    if rel not in used:
                        for _, _dirs, files in os.walk(d):
                            n += sum(1 for f in files if os.path.splitext(f)[1].lower() in BOOK_EXT)
                            if n >= 500:
                                break
                    out.append({"path": d.name, "books": n, "used": rel in used})
        return out

    def _validate(self, name: str, path: str, skip_id: str | None = None, owner: str | None = None):
        name = (name or "").strip()[:60]
        if not name:
            raise ValueError("Give your library a name")
        for l in self.libraries:
            if l["id"] == skip_id or l.get("owner") != owner:
                continue
            if l["name"].lower() == name.lower():
                raise ValueError(f"You already have a library called “{l['name']}”")
            if path is not None and l["path"].lower() == path.lower():
                raise ValueError(f"That folder is already used by “{l['name']}”")
        return name

    def create_library(self, name: str, path: str | None, rtl: bool, color: str, ltype: str | None = None,
                       owner: dict | None = None) -> dict:
        ltype = ltype if ltype in LIB_TYPES else ("manga" if rtl else "comics")
        path = safe_rel(path or name)
        if owner:
            path = f"{owner['folder']}/{path}"
        name = self._validate(name, path, owner=owner and owner["id"])
        try:
            (LIB_ROOT / path).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ValueError(f"Couldn't create /data/{path} ({e.strerror}). Is /data mounted read-only?")
        lib = {"id": uuid.uuid4().hex[:10], "name": name, "path": path, "owner": owner and owner["id"], "rtl": ltype == "manga", "type": ltype,
               "color": color or random.choice(PALETTE), "created": int(time.time())}
        with self.lock:
            self.libraries.append(lib)
            self.ignored = [p for p in self.ignored if p.lower() != path.lower()]
            self._save_libs()
        return lib

    def update_library(self, lid: str, patch: dict) -> dict:
        lib = self.get_library(lid)
        if not lib:
            raise KeyError(lid)
        renamed = False
        if "name" in patch:
            new_name = self._validate(patch["name"], None, skip_id=lid, owner=lib.get("owner"))
            folder = safe_component(new_name)
            src = LIB_ROOT / lib["path"]
            parent, cur = posixpath.split(lib["path"])
            new_path = f"{parent}/{folder}" if parent else folder
            # rename the folder too (library folders directly in the account folder only)
            if folder and lib["path"].count("/") <= (1 if lib.get("owner") else 0) and folder != cur:
                dest = LIB_ROOT / new_path
                if dest.exists() and dest.resolve() != src.resolve():
                    raise ValueError(f"A folder called “{folder}” already exists — pick another name")
                if src.is_dir():
                    self._release(src)
                    self._rename_dir(src, dest)      # progress moves only once the folder really moved
                    self._migrate_prefix(lib["path"], new_path)
                else:
                    dest.mkdir(parents=True, exist_ok=True)
                lib["path"] = new_path
                lib.pop("auto", None)
                renamed = True
            lib["name"] = new_name
        if patch.get("type") in LIB_TYPES:
            lib["type"] = patch["type"]
            lib["rtl"] = patch["type"] == "manga"
        elif "rtl" in patch:
            lib["rtl"] = bool(patch["rtl"])
            lib["type"] = "manga" if lib["rtl"] else ("cosplay" if lib.get("type") == "cosplay" else "comics")
        if patch.get("color"):
            lib["color"] = str(patch["color"])[:20]
        if "autoOptimize" in patch:                    # ✨ a preset id: new uploads are converted to AVIF by themselves
            if patch["autoOptimize"]:
                if lib.get("autoOptimize") is None:
                    lib["autoSince"] = int(time.time())  # only what arrives from now on
                lib["autoOptimize"] = str(patch["autoOptimize"])[:40]
            else:
                lib.pop("autoOptimize", None); lib.pop("autoSince", None)
        with self.lock:
            self._save_libs()
        if renamed:
            self.scan()
        return lib

    def delete_library(self, lid: str, delete_files: bool = False) -> str:
        """Remove a library. Its folder is deleted when it's empty (or when delete_files=True);
        otherwise the folder is kept and ignored by auto-discovery. Returns removed|kept|missing."""
        lib = self.get_library(lid)
        state = "missing"
        if lib:
            root = LIB_ROOT / lib["path"]
            if root.is_dir() and LIB_ROOT.resolve() in root.resolve().parents:
                has_files = any(p.is_file() for p in root.rglob("*"))
                if delete_files or not has_files:
                    if delete_files:
                        for b in self.books.values():
                            if b["library"] == lid:
                                self._forget(b["id"])
                    shutil.rmtree(root)
                    self._prune(root.parent)
                    state = "removed"
                else:
                    state = "kept"
        with self.lock:
            if lib and state == "kept" and lib["path"].lower() not in (p.lower() for p in self.ignored):
                self.ignored.append(lib["path"])  # don't auto-rediscover a library the user removed
            if lib and state != "kept":
                self.ignored = [p for p in self.ignored if p.lower() != lib["path"].lower()]
            self.libraries = [l for l in self.libraries if l["id"] != lid]
            self.books = {k: b for k, b in self.books.items() if b["library"] != lid}
            self._save_libs()
        self._save_index()
        return state


    # ---- archive access
    def get(self, bid: str) -> dict | None:
        return self.books.get(bid)


