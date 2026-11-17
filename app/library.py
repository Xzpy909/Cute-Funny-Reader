"""Library scanning, indexing and archive access for Cute&Funny Reader."""
from __future__ import annotations

import html
import io
import json
import logging
import mimetypes
import os
import posixpath
import random
import re
import shutil
import threading
import time
import struct
import subprocess
import zipfile
import hashlib
import uuid
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path
from urllib.parse import unquote, quote

from PIL import Image, ImageOps

from .store import Db, Identities, Names, Store
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
from .panels import detect_panels

log = logging.getLogger("cfreader")

LIB_ROOT = Path(os.environ.get("LIBRARY_DIR", "/data"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/config"))
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL", "600"))
TRASH_DIR = ".trash"                                                    # inside each account's folder (hidden from scans)
TRASH_DELAY = int(os.environ.get("TRASH_DELAY", "600"))                 # seconds a trashed item stays in place (undo)
TRASH_KEEP = int(os.environ.get("TRASH_KEEP_DAYS", "30")) * 86400       # then this long in the trash before it's deleted
EMPTY_FOLDER_AFTER = int(os.environ.get("EMPTY_FOLDER_HOURS", "24")) * 3600   # empty folders are removed after this
JUNK_FILES = {".collection", "thumbs.db", "desktop.ini", ".ds_store"}

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".tif", ".tiff", ".jxl", ".heic", ".heif")
# no browser but Safari shows these: transcoded to PNG before reading, cached for a while
JXL_EXT = (".jxl",)
HEIC_EXT = (".heic", ".heif")
TRANSCODE_EXT = JXL_EXT + HEIC_EXT
JXL_TTL = float(os.environ.get("JXL_CACHE_DAYS", "7")) * 86400     # converted pages unused this long are dropped
LOSSLESS_EXT = (".png", ".bmp", ".tif", ".tiff")     # → the RAW pill
BROWSER_UNSAFE = (".tif", ".tiff")                  # only Safari shows TIFF: served as PNG (still lossless)
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v")
BOOK_EXT = (".cbz", ".zip", ".cb7", ".epub")
MEDIA_EXT = IMG_EXT + VIDEO_EXT


def is_video(name: str) -> bool:
    return name.lower().endswith(VIDEO_EXT)
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


# ----------------------------------------------------------------- helpers
def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def make_id(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:12]


# innermost [..] / (..) / {..} with no other bracket inside — applied until nothing is left, so nested
# groups like "[Circle (Artist)]" go as a whole (a flat [^\])}]* stopped at the inner ")" and left "]")
BRACKET_GROUP = re.compile(r"\s*(?:\[[^\[\](){}]*\]|\([^\[\](){}]*\)|\{[^\[\](){}]*\})")


def strip_brackets(s: str, repl: str = "") -> str:
    while True:
        t = BRACKET_GROUP.sub(repl, s)
        if t == s:
            return t
        s = t
SQUARE = re.compile(r"\s*\[[^\]]*\]")
NUM = re.compile(
    r"(?:^|[\s_\-.])(c|ch|chap|chapter|part|pt|ep|episode|v|vol|volume|#)\.?\s*(\d+(?:\.\d+)?)(?=$|[\s_\-.])",
    re.I,
)


def tidy(s: str) -> str:
    return re.sub(r"[\s_]+", " ", s).strip(" -_.")


def parse_number(stem: str):
    """-> (kind, number, text_before_number) from a filename stem."""
    s = strip_brackets(stem, " ")
    m = None
    for m in NUM.finditer(s):
        pass
    if m:
        kind = "volume" if m.group(1).lower().startswith("v") else "chapter"
        return kind, float(m.group(2)), s[: m.start()]
    t = re.search(r"\s(\d{1,4}(?:\.\d+)?)\s*$", s)
    if t:
        return None, float(t.group(1)), s[: t.start()]
    return None, None, s


def fmt_num(n):
    if n is None:
        return ""
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_component(name: str) -> str:
    """Make a single path component safe on Linux *and* Windows hosts."""
    return UNSAFE.sub("_", name).strip(" .")[:180]


def safe_rel(path: str) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("Folder can't contain '..'")
    parts = [safe_component(p) for p in parts]
    if not parts or not all(parts):
        raise ValueError("Please enter a folder name")
    return "/".join(parts)


def guess_type(name: str) -> str:
    n = name.lower()
    return "cosplay" if "cosplay" in n else "manga" if ("manga" in n or "漫画" in n) else "comics"


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


# ----------------------------------------------------------------- parsing
def parse_comicinfo(data: bytes) -> dict:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {}

    def g(tag):
        el = root.find(tag)
        return (el.text or "").strip() if el is not None and el.text else ""

    out = {k.lower(): g(k) for k in ("Title", "Series", "Number", "Volume", "Summary", "Writer", "Publisher", "Manga",
                                     "Year", "Genre", "Tags", "Format", "Count", "PageCount", "Characters", "LanguageISO")}
    return {k: v for k, v in out.items() if v}


def parse_metadata_json(data: bytes) -> dict:
    """metadata.json (gallery-downloader style) -> the same keys parse_comicinfo returns.
    type -> genre, artists -> writer, groups -> publisher, tags[{tag, female, male}] -> "tag ♀" / "tag ♂" / "tag"."""
    try:
        d = json.loads(data.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(d, dict):
        return {}
    def names(v):
        return [str(x).strip() for x in (v or []) if isinstance(x, (str, int)) and str(x).strip()] if isinstance(v, list) else []
    tags = []
    for t in d.get("tags") or []:
        if isinstance(t, str):
            tags.append(t.strip()); continue
        if not isinstance(t, dict) or not str(t.get("tag", "")).strip():
            continue
        name = str(t["tag"]).strip()
        f, m = bool(t.get("female")), bool(t.get("male"))
        if f:
            tags.append(f"{name} ♀")
        if m:
            tags.append(f"{name} ♂")
        if not f and not m:
            tags.append(name)
    tags += names(d.get("parodys"))
    genres = names(d.get("genres"))            # our extension: the full list (type = the first one)
    out = {
        "title": str(d.get("title") or "").strip(),
        "genre": ", ".join(genres) if genres else str(d.get("type") or "").strip(),
        "summary": str(d.get("summary") or "").strip(),
        "format": str(d.get("release") or "").strip(),
        "number": str(d.get("number") if d.get("number") is not None else "").strip(),
        "direction": str(d.get("direction") or "").strip().lower(),
        "writer": ", ".join(names(d.get("artists"))),
        "publisher": ", ".join(names(d.get("groups"))),
        "tags": ", ".join(tags),
        "year": str(d.get("year") or "").strip() or (str(d.get("date") or "")[:4] if re.match(r"\d{4}", str(d.get("date") or "")) else ""),
        "language": str(d.get("language") or "").strip(),
        "thumbnail": str(d["thumbnail"]) if isinstance(d.get("thumbnail"), int) and not isinstance(d.get("thumbnail"), bool) else "",
        "seriescover": "1" if d.get("seriesCover") is True else "",
    }
    out = {k: v for k, v in out.items() if v}
    if str(d.get("series") or "").strip():
        out["series"] = str(d["series"]).strip()
    elif out.get("title"):
        out["series"] = out["title"]          # standalone galleries: the title names the series
    return out


def merge_meta(ci: dict, mj: dict) -> dict:
    """metadata.json wins (it's what the editor writes); ComicInfo.xml fills the gaps; tags/genres are combined."""
    out = dict(ci); out.update(mj)
    for k in ("tags", "genre"):
        if ci.get(k) and mj.get(k):
            out[k] = mj[k] + ", " + ci[k]
    return out


def tags_to_json(tags: list[str]) -> list[dict]:
    """["cute ♀", "glasses ♀", "glasses ♂", "full color"] -> [{tag, female, male}, ...] (♀/♂ of one tag merged)"""
    out: dict[str, dict] = {}
    for t in tags:
        name = re.sub(r"\s*[♀♂]\s*$", "", t).strip()
        if not name:
            continue
        e = out.setdefault(name.lower(), {"tag": name, "female": 0, "male": 0})
        if t.rstrip().endswith("♀"):
            e["female"] = 1
        elif t.rstrip().endswith("♂"):
            e["male"] = 1
    return list(out.values())


def build_metadata(b: dict, existing: dict, fields: dict) -> dict:
    """The metadata.json written into a book: the existing file's extra keys are kept,
    everything the app knows about the book is carried over (incl. what came from ComicInfo.xml),
    and the edited fields go on top."""
    cur = {k: b.get(k) for k in ("author", "publisher", "genres", "tags", "summary", "year", "release")}
    cur["direction"] = "rtl" if b.get("rtl") is True else "ltr" if b.get("rtl") is False else ""
    cur.update(fields)
    doc = dict(existing)
    split = lambda v: [x.strip() for x in re.split(r"\s*[,;]\s*", v or "") if x.strip()]
    if b.get("title") and not doc.get("title"):
        doc["title"] = b["title"]
    if b.get("number") is not None and "number" not in doc:
        n = b["number"]; doc["number"] = int(n) if float(n).is_integer() else n
    genres = list(cur.get("genres") or [])
    doc["type"] = genres[0] if genres else ""
    doc["genres"] = genres
    doc["artists"] = split(cur.get("author"))
    doc["groups"] = split(cur.get("publisher"))
    doc["tags"] = tags_to_json(cur.get("tags") or [])
    for k in ("summary", "year", "release", "direction"):
        if cur.get(k):
            doc[k] = cur[k]
        else:
            doc.pop(k, None)
    return doc


META_FILES = {"comicinfo.xml": "ci", "metadata.json": "mj", "info.yaml": "iy", "info.yml": "iy"}


def is_meta_file(n: str) -> str | None:
    return META_FILES.get(posixpath.basename(n).lower())


def read_meta(files: dict) -> dict:
    """files: {"ci": ComicInfo.xml, "iy": info.yaml, "mj": metadata.json} (bytes, any may be missing).
    Layered weakest → strongest: ComicInfo.xml < info.yaml < metadata.json (what the editor writes)."""
    out = parse_comicinfo(files["ci"]) if files.get("ci") else {}
    for layer in (parse_info_yaml(files["iy"]) if files.get("iy") else {},
                  parse_metadata_json(files["mj"]) if files.get("mj") else {}):
        if layer:
            out = merge_meta(out, layer)
    return out


def _yaml_load(data: bytes):
    try:
        import yaml
    except ImportError:                           # PyYAML missing → ignore info.yaml rather than crash a scan
        log.warning("info.yaml found but PyYAML isn't installed — skipping it")
        return None
    try:
        return yaml.safe_load(data.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001 — broken YAML is just "no metadata"
        return None


INFO_EXTRA = ("Id", "IdSource", "Source", "URL", "Event", "Circle", "Parody")   # kept in metadata.json after an edit


def parse_info_yaml(data: bytes) -> dict:
    """info.yaml (gallery-downloader style) -> the same keys parse_comicinfo returns.
       Title → title (+ series)   Description → summary   Artist[] → writer   Circle + Publisher → publisher
       Tags[] (+ Parody, Event) → tags   Released (unix time or date) → year   Thumbnail / ThumbnailIndex → cover page (0-based)
       Empty keys and unknown ones (Magazine, Pages…) are skipped"""
    d = _yaml_load(data)
    if not isinstance(d, dict):
        return {}
    d = {str(k).strip().lower(): v for k, v in d.items()}
    def txt(v):
        return "" if v is None or isinstance(v, (dict, list)) else str(v).strip()
    def many(v):
        if isinstance(v, (str, int, float)):
            v = [v]
        return [str(x).strip() for x in (v or []) if isinstance(x, (str, int, float)) and str(x).strip()] if isinstance(v, list) else []
    tags = []
    for t in many(d.get("tags")):
        ns, _, name = t.partition(":")            # "female:glasses" → "glasses ♀" (the app's own tag style)
        tags.append(f"{name.strip()} ♀" if ns.lower() == "female" and name.strip()
                    else f"{name.strip()} ♂" if ns.lower() == "male" and name.strip() else t)
    tags += [p for p in many(d.get("parody")) if p.lower() not in ("original", "original work")]
    tags += many(d.get("event"))
    year = ""
    rel = d.get("released")
    if isinstance(rel, (int, float)) and rel > 0:
        year = str(time.gmtime(rel / 1000 if rel > 1e11 else rel).tm_year)    # seconds (or milliseconds)
    elif hasattr(rel, "year"):                    # YAML turned "2019-08-10" into a date
        year = str(rel.year)
    elif re.match(r"\d{4}", txt(rel)):
        year = txt(rel)[:4]
    out = {
        "title": txt(d.get("title")),
        "summary": txt(d.get("description")),
        "writer": ", ".join(many(d.get("artist")) or many(d.get("artists"))),
        "publisher": ", ".join(dict.fromkeys(many(d.get("circle")) + many(d.get("publisher")))),
        "tags": ", ".join(tags),
        "year": year,
        "language": txt(d.get("language")),
    }
    out = {k: v for k, v in out.items() if v}
    if out.get("title"):
        out["series"] = out["title"]               # standalone galleries: the title names the series
    th = d.get("thumbnail", d.get("thumbnailindex"))     # both spellings exist in the wild
    if isinstance(th, int) and not isinstance(th, bool) and th >= 0:
        out["thumbnail"] = str(th)
    return out


def info_yaml_extras(data: bytes) -> dict:
    """The info.yaml fields the app has no column for (source link, gallery id…) — carried into metadata.json."""
    d = _yaml_load(data)
    if not isinstance(d, dict):
        return {}
    keep = {k.lower(): k for k in INFO_EXTRA}
    out = {}
    for k, v in d.items():
        if isinstance(v, list):                    # "Parody:\n  - " → [None] → nothing
            v = [x for x in v if x not in (None, "")]
        if str(k).lower() in keep and v not in (None, "", []):
            out[keep[str(k).lower()]] = v
    return out


def split_tags(v: str) -> list[str]:
    seen, out = set(), []
    for t in re.split(r"[,;|\n]+", v or ""):
        t = re.sub(r"\s+", " ", t).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:80]


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


# "[Circle (Artist)] Title.cbz" / "[Artist] Title.cbz", optionally after event tags: "(C90) [Circle (Artist)] …"
NAME_CREDIT = re.compile(r"^\s*(?:\([^()]*\)\s*)*\[([^\[\]]+)\]")
CIRCLE_ARTIST = re.compile(r"^(.+?)\s*\(([^()]+)\)\s*$")
NOT_A_CREDIT = {  # leading [tags] that aren't people
    "english", "eng", "en", "japanese", "jp", "jpn", "raw", "raws", "chinese", "cn", "korean", "kr", "spanish",
    "french", "german", "russian", "portuguese", "italian", "digital", "decensored", "uncensored", "censored",
    "colorized", "colourized", "color", "colour", "full color", "translated", "textless", "hd", "hq", "lq",
    "complete", "completed", "ongoing", "oneshot", "one shot", "sample", "preview", "anthology", "various",
    "unknown", "n/a", "dl版", "中国翻訳", "無修正", "中国語", "english translated", "fan edition", "webtoon",
}


def credits_from_name(stem: str, numbered: bool) -> tuple[str, str]:
    """-> (artist, circle) from a leading [..] in a file/folder name, or ("", "").
    Numbered chapters/volumes ("[Group] Series Ch.05") usually carry a scanlation group there, so for those
    only the unambiguous "[Circle (Artist)]" form counts."""
    m = NAME_CREDIT.match(stem)
    if not m:
        return "", ""
    inner = re.sub(r"\s+", " ", m.group(1)).strip()
    ca = CIRCLE_ARTIST.match(inner)
    circle, artist = (ca.group(1).strip(), ca.group(2).strip()) if ca else ("", inner)
    if numbered and not ca:
        return "", ""
    junk = lambda v: (not v or v.lower() in NOT_A_CREDIT
                      or re.fullmatch(r"[\d\s._\-/]+|c\d{2,3}|\d{3,4}[pk]|v\d+|\d+x\d+", v, re.I) is not None)
    if junk(artist):
        return "", ""
    return artist, "" if junk(circle) else circle


def clean_title_credits(meta: dict, stem: str, numbered: bool) -> dict:
    """Metadata titles often repeat the credit: "Title: [Circle (Artist)] Work (C99) [English]".
    When the leading [..] names the book's author or circle (from the metadata, or from the file name), the
    title — and the series name taken from it — are cleaned like file names are: credit and brackets go.
    No author known yet + the unambiguous "[Circle (Artist)]" form → that becomes the author / circle too."""
    split = lambda v: {x.strip().lower() for x in re.split(r"\s*[,;&]\s*", v or "") if x.strip()}
    fa, fc = credits_from_name(stem, numbered)
    known = split(meta.get("writer")) | split(meta.get("publisher")) | split(fa) | split(fc)
    out = dict(meta)
    for key in ("title", "series"):
        v = out.get(key) or ""
        a, c = credits_from_name(v, False)                 # leading [..] that looks like a credit at all
        if not a:
            continue
        sure_a, sure_c = credits_from_name(v, True)        # only the "[Circle (Artist)]" form
        if (split(a) | split(c)) & known or (sure_a and not out.get("writer") and not fa):
            if sure_a and not out.get("writer") and not fa:
                out["writer"] = sure_a
                if sure_c and not out.get("publisher"):
                    out["publisher"] = sure_c
                known |= split(sure_a) | split(sure_c)
            elif sure_c and not out.get("publisher") and split(sure_a) & known:
                out["publisher"] = sure_c              # author matched: keep the circle the title names
            cleaned = tidy(strip_brackets(v))
            if cleaned:
                out[key] = cleaned
    return out


# ---- Cosplay names: Cosplayer → Set → Variant, with the circle as metadata
#   "[Dreva(Solene)]My Lucky Bunny Bonus"                     circle Dreva · cosplayer Solene · "My Lucky Bunny Bonus"
#   "[DREVA] Bluma - Equinox Lark (Dream Chronicle) Normal Ver" circle DREVA · cosplayer Bluma · "Equinox Lark Normal Ver"
# Whether the end of a name is a *variant* can't be told from one name alone — only when the same cosplayer
# has sibling sets whose names start the same way: the part that differs is the variant (variant_groups).
VARIANT_WORD = re.compile(
    r"^(?:normal|bonus|special|extra|ex|ver\.?|version|nsfw|sfw|lite|full|uncensored|censored|original|alt|another"
    r"|plus|\+|part|vol\.?|photos?|videos?|[a-z]|[a-z0-9+]{1,3}[_-]?ver(?:sion)?\.?|[a-z]{1,2}\+|v?\d+(?:\.\d+)?|[ivx]{1,4})$", re.I)


def cosplay_name(stem: str) -> dict:
    """-> {circle, cosplayer, work} from a Cosplay file / folder name."""
    circle = cosplayer = ""
    rest = stem
    m = NAME_CREDIT.match(stem)
    if m:
        inner = re.sub(r"\s+", " ", m.group(1)).strip()
        ca = CIRCLE_ARTIST.match(inner)
        circle, cosplayer = (ca.group(1).strip(), ca.group(2).strip()) if ca else (inner, "")
        rest = stem[m.end():]
    if circle.lower() in NOT_A_CREDIT:
        circle = ""
    rest = tidy(strip_brackets(rest))
    if not cosplayer and " - " in rest:                    # "Cosplayer - Work"
        cosplayer, rest = (x.strip() for x in rest.split(" - ", 1))
    return {"circle": circle, "cosplayer": cosplayer, "work": rest}


def split_variant(work: str) -> tuple[str, str]:
    """-> (set, variant): up to 3 trailing variant words split off ("My Lucky Bunny", "Bonus").
    (work, "") when the end of the name doesn't look like a variant."""
    words = work.split()
    k = 0
    while k < min(3, len(words) - 1) and VARIANT_WORD.match(words[-1 - k]):
        k += 1
    return (" ".join(words[:-k]), " ".join(words[-k:])) if k else (work, "")


MAX_VARIANT = 3     # a variant is at most this many words …
MAX_FREE = 2        # … and at most this many when they aren't the usual variant words
SEPARATOR = re.compile(r"^[\W_]+$")


def _tail(words: list[str]) -> list[str]:
    """The part after the shared start, without loose separators ("- Normal" → "Normal")."""
    return [w for w in words if not SEPARATOR.match(w) or w == "+"]


def _usual(tail: list[str]) -> bool:
    return bool(tail) and len(tail) <= MAX_VARIANT and all(VARIANT_WORD.match(w) for w in tail)


def _variant_pair(k: int, mine: list[str], other: list[str]) -> bool:
    """Two names share their first k words; `mine` / `other` are what follows. Is that a set with variants?
    The difference is the variant — but "Arc Fleet HMS Siren" and "Arc Fleet USS St. Lucas" are two sets,
    so a free-form difference needs more in common than one written with the usual words:
      · usual variant words ("Normal", "S ver", "SP-version", "Bonus")   → any shared start
      · anything else, up to 2 words                                    → 3 shared words, or 2 when the
        other name is the bare set name or carries a usual variant word."""
    def ok(t, o):
        if not t or _usual(t):
            return True
        return len(t) <= MAX_FREE and (k >= 3 or (k >= 2 and (not o or _usual(o))))
    return (bool(mine) or bool(other)) and ok(mine, other) and ok(other, mine)


def variant_groups(works: list[str]) -> dict[int, tuple[str, str]]:
    """Sibling works of one cosplayer → {index: (set, variant)}. When names start the same way, the shared
    start is the set and the part that differs is the variant —
        "Circuit Hunter Mika Normal" + "Circuit Hunter Mika SP-version" → set "Circuit Hunter Mika".
    Each name takes the longest start it shares with a sibling (a sibling may be exactly that start, with no
    variant part). Names that share too little are left out: they stay whole sets (see _variant_pair)."""
    words = [w.split() for w in works]
    low = [[x.lower() for x in w] for w in words]
    base_of: dict[int, int] = {}
    for i, w in enumerate(low):
        for k in range(len(w), 0, -1):
            if any(j != i and o[:k] == w[:k] and _variant_pair(k, _tail(w[k:]), _tail(o[k:]))
                   for j, o in enumerate(low)):
                base_of[i] = k
                break
    groups: dict[tuple, list[int]] = {}
    for i, k in base_of.items():
        groups.setdefault(tuple(low[i][:k]), []).append(i)
    out = {}
    for ids in groups.values():
        if len(ids) < 2:
            continue
        k = base_of[ids[0]]
        base = " ".join(words[min(ids, key=lambda i: len(words[i]))][:k])     # one spelling for the whole set
        for i in ids:
            out[i] = (base, " ".join(_tail(words[i][k:])))
    return out


def sibling_works(names: list[str]) -> list[str]:
    """The work title of each sibling name. "Title - Normal" next to "Title" is that title's variant, not a
    set called "Normal" by a cosplayer called "Title"."""
    parsed = [cosplay_name(n) for n in names]
    whole = {tidy(strip_brackets(n)).lower() for n in names}
    out = []
    for n, p in zip(names, parsed):
        m = NAME_CREDIT.match(n)
        dashed = not m and " - " in n and p["cosplayer"]
        out.append(tidy(strip_brackets(n)) if dashed and p["cosplayer"].lower() in whole else p["work"])
    return out


def joins_existing(work: str, existing) -> str:
    """The set (a folder that is already there) this name is a further variant of, or ""."""
    words = work.split()
    for k in range(len(words) - 1, 0, -1):
        base = " ".join(words[:k])
        tail = _tail([x.lower() for x in words[k:]])
        if tail and base.lower() in existing and _variant_pair(k, tail, []):
            return base
    return ""


def same_case(parent: Path, name: str) -> str:
    """An existing child folder spelled differently ("DREVA" / "Dreva") is reused instead of making a twin."""
    try:
        low = name.lower()
        return next((p.name for p in parent.iterdir() if p.is_dir() and p.name.lower() == low), name)
    except OSError:
        return name


def cosplay_plan(root: Path, names: list[str]) -> dict[str, dict]:
    """Where uploaded Cosplay sets go: {name: {cosplayer, set}}. The name itself becomes the variant.
    Variants are found among the uploaded siblings of the same cosplayer, and an upload also joins a set
    that already exists for that cosplayer (e.g. the 4th variant of "My Lucky Bunny", weeks later)."""
    parsed = {n: cosplay_name(n) for n in names}
    by_cos: dict[str, list[str]] = {}
    for n, p in parsed.items():
        by_cos.setdefault(p["cosplayer"].lower(), []).append(n)
    out = {}
    for group in by_cos.values():
        cos = parsed[group[0]]["cosplayer"]
        cos_dir = same_case(root, safe_component(cos)) if cos else ""
        here = root / cos_dir if cos_dir else root
        try:
            existing = {p.name.lower(): p.name for p in here.iterdir() if p.is_dir() and not p.name.startswith(".")}
        except OSError:
            existing = {}
        found = variant_groups([parsed[n]["work"] for n in group])
        for i, n in enumerate(group):
            work = parsed[n]["work"]
            if i in found:
                set_name = found[i][0]
            else:
                set_name = joins_existing(work, existing) or work
            set_name = existing.get(set_name.lower(), set_name)
            out[n] = {"cosplayer": cos_dir, "set": set_name}
    return out


def name_credits(b: dict, cosplay: bool = False):
    """No author in the metadata → take it from the name. Re-applied every scan (cheap); flagged so a
    later metadata author always wins and a renamed file is re-read. Cosplay: author = cosplayer,
    publisher = circle."""
    if b.get("author") and not b.get("nameCredit"):
        return
    stem = b["file"] if b.get("src") == "folder" else posixpath.splitext(b["file"])[0]
    if cosplay:
        p = cosplay_name(stem)
        artist, circle = p["cosplayer"], p["circle"]
    else:
        artist, circle = credits_from_name(stem, b.get("kind") in ("chapter", "volume"))
    if b.get("nameCredit"):                          # undo the last guess before making a new one
        b["author"] = ""
        if b.pop("namePub", None):
            b["publisher"] = ""
    b.pop("nameCredit", None)
    if artist or (cosplay and circle):
        b["nameCredit"] = True
        if artist:
            b["author"] = artist
        if circle and not b.get("publisher"):
            b["publisher"], b["namePub"] = circle, True


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
class Library:
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
        self._jxl_jobs: dict[str, dict] = {}
        self._jxl_touched: dict[str, float] = {}
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
        base = LIB_ROOT / lib["path"]
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
            if guess and (LIB_ROOT / lib["path"] / guess).is_dir():
                series = guess
        folder = LIB_ROOT / lib["path"]
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
                return LIB_ROOT / b["sdir"]
        return None

    def _base(self, b: dict) -> Path:
        return LIB_ROOT / (b.get("base") or self._lib_path(b["library"]))

    def _collection_folders(self, lib: dict) -> set:
        root = LIB_ROOT / lib["path"]
        if not root.is_dir():
            return set()
        return {d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".") and (d / COL_MARK).exists()}

    def _collections_from_disk(self) -> list[dict]:
        out = []
        for l in self.libraries:
            for name in sorted(self._collection_folders(l), key=str.lower):
                d = LIB_ROOT / l["path"] / name
                out.append({"id": self.groups.id_for("collection", collection_key(l["id"], name)), "name": name, "folder": name,
                            "library": l["id"], "added": int(d.stat().st_mtime)})
        return out

    def find_collection(self, cid: str) -> tuple[dict, Path]:
        for l in self.libraries:
            for name in self._collection_folders(l):
                if self.groups.id_for("collection", collection_key(l["id"], name)) == cid:
                    return l, LIB_ROOT / l["path"] / name
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
            root = str(LIB_ROOT / l["path"])
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
            root = LIB_ROOT / l["path"]
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

    # ---- edited details (stored in /config, files are never rewritten)
    EDITABLE = ("author", "publisher", "genres", "tags", "summary", "year", "release", "direction")

    def _release(self, folder: Path):
        """Close cached archive handles under `folder` — an open file inside blocks a rename on Windows hosts."""
        pre = folder.relative_to(LIB_ROOT).as_posix() + "/"
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

    def effective(self, b: dict) -> dict:
        e = self.edits.get(b["id"])
        return {**b, **e, "edited": True} if e else b

    WRITABLE = ("cbz", "zip", "cb7", "folder")

    def _read_raw_meta(self, b: dict, kind: str) -> bytes | None:
        """Raw bytes of the book's metadata file of `kind` ("mj", "ci", "iy"), or None."""
        try:
            if b["src"] == "folder":
                f = next((p for p in (LIB_ROOT / b["rel"]).iterdir() if p.is_file() and is_meta_file(p.name) == kind), None)
                return f.read_bytes() if f else None
            if b["src"] == "cb7":
                f = next((p for p in self._x7_dir(b).rglob("*") if p.is_file() and is_meta_file(p.name) == kind), None)
                return f.read_bytes() if f else None
            with zipfile.ZipFile(LIB_ROOT / b["rel"]) as z:
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
        path = LIB_ROOT / b["rel"]
        doc = build_metadata(self.effective(b), self._read_mj(b), fields)
        iy = self._read_raw_meta(b, "iy")
        if iy and "info" not in doc and (extra := info_yaml_extras(iy)):
            doc["info"] = extra
        if thumbnail is not self._KEEP:
            if thumbnail is None:
                doc.pop("thumbnail", None)
            else:
                doc["thumbnail"] = int(thumbnail)
        elif b.get("cover") and b.get("entries") and b["entries"].index(b["cover"]) != \
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
        back to the default (first book, first photo). Stored in metadata.json: "thumbnail" (page) on that book,
        "seriesCover": true when it isn't the series' first book. Only books whose flags change are rewritten."""
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
        errors = []
        for x in books:
            want_flag = target is not None and x["id"] == target["id"] and len(books) > 1
            want_thumb = page if target is not None and x["id"] == target["id"] else self._KEEP
            if book_id is None and x.get("format") == "images":
                want_thumb = None                      # reset: every book back to its first photo
            if bool(x.get("seriesCover")) == want_flag and want_thumb is self._KEEP:
                continue                               # nothing changes in this file
            if x.get("src") not in self.WRITABLE:
                continue
            try:
                self.write_metadata(x, {}, thumbnail=want_thumb, series_cover=want_flag)
            except Exception as e:  # noqa: BLE001
                log.warning("could not write the cover choice into %s: %s", x["rel"], e)
                errors.append(x["file"])
        self.scan()
        if errors:
            raise OSError("Couldn’t write into: " + ", ".join(errors[:5]))

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
        errors = []
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
            elif per and b.get("src") in self.WRITABLE:
                try:
                    self.write_metadata(b, per)         # into the file itself
                    self.edits.delete(b["id"])          # (older app-side edits are now inside the file)
                except Exception as e:  # noqa: BLE001
                    log.warning("could not write metadata into %s: %s", b["rel"], e)
                    errors.append(b["file"])
            elif per:                                   # standalone videos / EPUBs: kept app-side
                ov = {**self.edits.get(b["id"], {}), **per}
                if "direction" in ov:
                    d = ov.pop("direction")
                    if d: ov["rtl"] = d == "rtl"
                    else: ov.pop("rtl", None)
                self.edits.put(b["id"], ov)
        self.scan()
        if errors:
            raise OSError("Couldn’t write into: " + ", ".join(errors[:5]))
        return len(books)

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
        rel = src.relative_to(LIB_ROOT).as_posix()

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
        root = LIB_ROOT / self._lib_path(lid)
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
            self._migrate_prefix(src.relative_to(LIB_ROOT).as_posix(), dest.relative_to(LIB_ROOT).as_posix())
            self.groups.rename("collection", collection_key(l["id"], src.name), collection_key(l["id"], folder))
        self.scan()
        return cid                                  # the id stays — only the name changed

    def ungroup_collection(self, cid: str):
        """Move every series out of the collection into the library root, then drop the folder."""
        l, src = self.find_collection(cid)
        root = LIB_ROOT / l["path"]
        for item in sorted(src.iterdir()):
            if item.name == COL_MARK:
                continue
            dest = self._unique(root / item.name)
            shutil.move(str(item), str(dest))
            self._moved(item.relative_to(LIB_ROOT).as_posix(), dest.relative_to(LIB_ROOT).as_posix())
        shutil.rmtree(src, ignore_errors=True)
        self.scan()

    def delete_collection(self, cid: str):
        """Its books go to the trash (the folder follows once they've been moved out); an empty one goes at once."""
        _, src = self.find_collection(cid)
        prefix = src.relative_to(LIB_ROOT).as_posix() + "/"
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
        return LIB_ROOT / self._lib_path(e["library"]) / e["folder"]

    def create_series(self, lid: str, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the series a name")
        root = LIB_ROOT / self._lib_path(lid)
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
        base = self._base(books[0]) if books else LIB_ROOT / self._lib_path(lid) / (col or "")
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
            self._moved(src.relative_to(LIB_ROOT).as_posix(), dest.relative_to(LIB_ROOT).as_posix())
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
                base = LIB_ROOT / self._lib_path(library) if library and library != b["library"] else self._base(b)
                self._move_file(b, base / safe_component(name))
        self.scan()

    def delete_empty_series(self, sid: str) -> bool:
        e = next((x for x in self.empty_series() if x["seriesId"] == sid), None)
        if not e:
            return False
        shutil.rmtree(LIB_ROOT / self._lib_path(e["library"]) / e["folder"])
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
        stop = {(LIB_ROOT / l["path"]).resolve() for l in self.libraries} | {LIB_ROOT.resolve()}
        if self.accounts:
            stop |= {(LIB_ROOT / a["folder"]).resolve() for a in self.accounts.items}
        f = folder
        while f.resolve() not in stop and LIB_ROOT.resolve() in f.resolve().parents:
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
        src = LIB_ROOT / b["rel"]
        if not src.exists():
            return
        dest_dir.mkdir(parents=True, exist_ok=True)
        if (dest_dir / src.name).resolve() == src.resolve():
            return
        dest = self._unique(dest_dir / src.name)
        self._release_file(b["rel"])
        self._retry(shutil.move, str(src), str(dest))
        self._moved(b["rel"], dest.relative_to(LIB_ROOT).as_posix())
        self._prune(src.parent)

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
            target = self.find_collection(collection)[1] if collection else LIB_ROOT / self._lib_path(lid)
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
                srcd = LIB_ROOT / self._lib_path(lid) / e["folder"]
                shutil.move(str(srcd), str(self._unique(target / srcd.name)))
            self.scan()
            return
        books = self.series_books(sid)
        if not books:
            e = next((x for x in self.empty_series() if x["seriesId"] == sid), None)
            if not e:
                raise KeyError(sid)
            src = LIB_ROOT / self._lib_path(e["library"]) / e["folder"]
            if into:
                shutil.rmtree(src)             # nothing to merge — just drop the empty folder
            elif library and library != e["library"]:
                dest = LIB_ROOT / self._lib_path(library) / Path(e["folder"]).name
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
            d = LIB_ROOT / self._lib_path(library) / src.name if src else LIB_ROOT / self._lib_path(library)
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
                shutil.rmtree(LIB_ROOT / self._lib_path(e["library"]) / e["folder"], ignore_errors=True)
                gone += 1
        if gone:
            self.scan()
        return removed + gone

    def delete_books(self, books: list[dict]):
        for b in books:
            src = LIB_ROOT / b["rel"]
            self._release_file(b["rel"])
            self._retry(_remove, src, b)
            self._forget(b["id"])
            self._prune(src.parent)
        self.scan()

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
        return LIB_ROOT / top / TRASH_DIR if top else LIB_ROOT / TRASH_DIR

    def _prune_junk(self, folder: Path):
        """Like _prune, but a folder holding only marker / system files (.collection, Thumbs.db…) counts as empty."""
        stop = {(LIB_ROOT / l["path"]).resolve() for l in self.libraries} | {LIB_ROOT.resolve()}
        if self.accounts:
            stop |= {(LIB_ROOT / a["folder"]).resolve() for a in self.accounts.items}
        f = folder
        while f.resolve() not in stop and LIB_ROOT.resolve() in f.resolve().parents:
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
        src = LIB_ROOT / b["rel"]
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
        self.bin.put(tid, {"id": b["id"], "rel": b["rel"], "name": src.name, "root": root.relative_to(LIB_ROOT).as_posix(),
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
            d = LIB_ROOT / e["root"] / tid
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
        f = LIB_ROOT / e["root"] / tid / "_cover" if e else None
        return f.read_bytes() if f and f.is_file() else None

    def restore_bin(self, tids: list[str]) -> int:
        n = 0
        for tid in tids:
            e = self.bin.get(tid)
            if not e:
                continue
            lib = self.get_library(e["library"])
            if not lib or not (LIB_ROOT / lib["path"]).is_dir():
                raise ValueError(f"“{e.get('libraryName') or 'Its library'}” no longer exists — create it again to restore this")
            src = LIB_ROOT / e["root"] / tid / e["name"]
            dest = self._unique(LIB_ROOT / e["rel"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._retry(shutil.move, str(src), str(dest))
            shutil.rmtree(LIB_ROOT / e["root"] / tid, ignore_errors=True)
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
            shutil.rmtree(LIB_ROOT / e["root"] / tid, ignore_errors=True)
            self.bin.delete(tid)
            if e["id"] not in self.books:                        # (not if a restored copy is back under this id)
                self._forget(e["id"])
            n += 1
        return n

    # ---- Empty folders
    def remove_empty_folders(self) -> int:
        """Folders with nothing in them (but marker / system files) that have been that way for
        EMPTY_FOLDER_AFTER are removed — leftovers of moves and deletes, emptied collections. Works from the
        folder listings the scan just made: no extra disk reads. Library folders themselves are never removed."""
        memo, now, removed = self._ls_memo, time.time_ns(), 0
        roots = {str(LIB_ROOT / l["path"]) for l in self.libraries}
        empty: dict[str, bool] = {}

        def is_empty(d: str) -> bool:
            if d not in empty:
                got = memo.get(d)
                empty[d] = bool(got) and all(f.lower() in JUNK_FILES for f in got[1]) \
                    and all(is_empty(os.path.join(d, x)) for x in got[0]) \
                    and now - got[3] > EMPTY_FOLDER_AFTER * 1_000_000_000
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
        root = LIB_ROOT / lib["path"]
        units: dict[Path, dict[Path, tuple]] = {}
        for b in self.books.values():
            if b["library"] != lib["id"] or b.get("format") == "epub":
                continue
            src = LIB_ROOT / b["rel"]
            container = root / b["collection"] if b.get("collection") else root
            if b.get("sdir"):
                entry = LIB_ROOT / b["sdir"]
                if entry.parent != container:          # deeper than <Set>/<file> — not ours to rearrange
                    continue
                units.setdefault(container, {})[entry] = (entry.name, True)
            else:
                stem = src.name if b.get("src") == "folder" else src.stem
                units.setdefault(container, {})[src] = (stem, False)
        return {c: [(e, n, s) for e, (n, s) in u.items()] for c, u in units.items()}

    def _mark_cosplayers(self, lib: dict) -> int:
        """Hand-copied <Cosplayer>/<Set>/<files> (no marker yet): a top folder holding only set folders is a cosplayer."""
        root, n = LIB_ROOT / lib["path"], 0
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
        old_rel, new_rel = src.relative_to(LIB_ROOT).as_posix(), dest.relative_to(LIB_ROOT).as_posix()
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
            root = LIB_ROOT / lib["path"]
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
                            rel = entry.relative_to(LIB_ROOT).as_posix()
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
            if LIB_ROOT.stat().st_mtime_ns != self._root_m:
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
            if self.libraries and not LIB_ROOT.exists():
                raise FileNotFoundError(f"{LIB_ROOT} does not exist — mount a folder there")
            # deepest library paths first, so nested libraries claim their own files
            for lib in sorted(list(self.libraries), key=lambda l: -l["path"].count("/")):
                root = LIB_ROOT / lib["path"]
                if not root.is_dir():
                    continue
                top = self._ls(str(root), deep)
                cols = {d for d in (top[0] if top else [])
                        if COL_MARK in ((self._ls(os.path.join(str(root), d), deep) or ((), ()))[1])}
                col_keys |= {collection_key(lib["id"], c) for c in cols}
                cols_by_lib[lib["id"]] = cols
                # plain string paths below: pathlib arithmetic per file was most of an unchanged scan's time
                root_s, base_n = str(root), len(str(LIB_ROOT)) + 1
                for dirpath, dirnames, filenames, fresh in self._walk(root, deep):
                    dir_list.append(dirpath)
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
                    self._root_m = LIB_ROOT.stat().st_mtime_ns
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
            return None
        finally:
            self.scanning = False

    # ---- cache clean-up
    # Every cache entry is named "<book id>-<mtime>…" (thumbs, video frames, panels, extracted .cb7s,
    # unpacked videos). After a scan, entries whose key isn't a live book belong to a file that was
    # deleted, moved/renamed (new id) or changed (new mtime) — they can never be hit again.
    CACHE_KEY = re.compile(r"^([0-9a-f]{12}-\d+)")
    CACHE_GRACE = 600                                  # leave anything touched in the last 10 min alone

    def sweep_cache(self) -> dict:
        if not LIB_ROOT.is_dir() or not any(LIB_ROOT.iterdir()):
            return {}                                  # /data not mounted → don't mistake that for "all deleted"
        with self.lock:
            live = {f"{b['id']}-{b['mtime']}" for b in self.books.values()}
            live_rel = {(b["rel"], b["mtime"]) for b in self.books.values()}
        cache = CONFIG_DIR / "cache"
        cutoff = time.time() - self.CACHE_GRACE
        removed, freed = 0, 0
        def size_of(p: Path) -> int:
            if p.is_dir():
                return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            return p.stat().st_size
        def drop(p: Path):
            nonlocal removed, freed
            try:
                if p.stat().st_mtime > cutoff:
                    return
                n = size_of(p)
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                removed, freed = removed + 1, freed + n
            except FileNotFoundError:
                pass
            except OSError as e:
                log.debug("couldn't remove %s: %s", p, e)
        for sub in ("thumbs", "panels", "media", "cb7", "jxl", "pages"):
            d = cache / sub
            if not d.is_dir():
                continue
            for p in d.iterdir():
                m = self.CACHE_KEY.match(p.name)
                if m and m.group(1) not in live:
                    drop(p)
                elif m and sub == "jxl" and p.is_dir():   # JPEG XL → PNG is temporary: unused for a while → rebuilt on open
                    job = self._jxl_jobs.get(p.name.split("-")[0], {})
                    try:
                        idle = time.time() - p.stat().st_mtime > JXL_TTL
                    except OSError:
                        idle = False
                    if idle and job.get("state") != "running":
                        drop(p)
                        self._jxl_jobs.pop(p.name.split("-")[0], None)
        repack = cache / "repack"                      # left-overs of a .cb7/.cbr conversion that crashed
        if repack.is_dir():
            for p in repack.iterdir():
                if p.stat().st_mtime < time.time() - 86400:
                    drop(p)
        with self._zip_lock:                           # open handles to archives that are gone
            for k in [k for k in self._zips if k not in live_rel]:
                try:
                    self._zips.pop(k).close()
                except Exception:  # noqa: BLE001
                    pass
        if removed:
            log.info("cache sweep: removed %d stale entr%s (%.1f MB)", removed, "y" if removed == 1 else "ies", freed / 1e6)
        return {"removed": removed, "freed": freed}

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
        rel = d.relative_to(LIB_ROOT).as_posix()
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
                "scanning": self.scanning, "error": self.scan_error, "root": str(LIB_ROOT),
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

    # ---- archive access
    def get(self, bid: str) -> dict | None:
        return self.books.get(bid)

    def _x7_dir(self, b: dict) -> Path:
        """.cb7 (solid 7z) can't be read entry-by-entry cheaply: extract once into the cache."""
        d = CONFIG_DIR / "cache" / "cb7" / f"{b['id']}-{b['mtime']}"
        if d.is_dir():
            return d
        import py7zr
        with self._x7_lock:
            if not d.is_dir():
                tmp = d.with_name(d.name + ".tmp")
                shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True)
                # some packers add a "." folder entry (or other odd paths) that py7zr refuses to extract:
                # pick the real files only
                with py7zr.SevenZipFile(LIB_ROOT / b["rel"]) as z:
                    targets = [f.filename for f in z.list() if not f.is_directory and _safe_member(f.filename)]
                with py7zr.SevenZipFile(LIB_ROOT / b["rel"]) as z:
                    z.extract(path=tmp, targets=targets)
                tmp.rename(d)
        return d

    def media_span(self, b: dict, n: int):
        """(file path, start offset, length) of page n on disk — lets videos stream with Range
        requests straight out of uncompressed (STORED) zip entries without extracting them."""
        if b["format"] == "video":
            p = LIB_ROOT / b["rel"]
            return p, 0, p.stat().st_size
        name = b["entries"][n]
        if b.get("src") in ("cb7", "folder"):
            p = (self._x7_dir(b) if b["src"] == "cb7" else LIB_ROOT / b["rel"]) / name
            return p, 0, p.stat().st_size
        path = LIB_ROOT / b["rel"]
        with self._zip_lock:
            z = self._zips.get((b["rel"], b["mtime"])) or zipfile.ZipFile(path)
            self._zips[(b["rel"], b["mtime"])] = z
            info = z.getinfo(name)
        if info.compress_type == zipfile.ZIP_STORED:
            with open(path, "rb") as f:
                f.seek(info.header_offset)
                hdr = f.read(30)
            fnlen, exlen = struct.unpack("<HH", hdr[26:30])
            return path, info.header_offset + 30 + fnlen + exlen, info.file_size
        # compressed video inside a zip: extract once to the cache
        c = CONFIG_DIR / "cache" / "media" / f"{b['id']}-{b['mtime']}-{n}{Path(name).suffix.lower()}"
        if not c.exists():
            c.parent.mkdir(parents=True, exist_ok=True)
            c.write_bytes(self.read(b, name))
        return c, 0, c.stat().st_size

    def read(self, b: dict, name: str) -> bytes:
        if b.get("src") == "folder":
            return (LIB_ROOT / b["rel"] / name).read_bytes()
        if b.get("src") == "cb7":
            return (self._x7_dir(b) / name).read_bytes()
        if b["format"] == "video":
            return (LIB_ROOT / b["rel"]).read_bytes()
        key = (b["rel"], b["mtime"])
        with self._zip_lock:
            z = self._zips.pop(key, None) or zipfile.ZipFile(LIB_ROOT / b["rel"])
            self._zips[key] = z
            while len(self._zips) > 12:
                _, old = self._zips.popitem(last=False)
                old.close()
            try:
                return z.read(name)
            except zipfile.BadZipFile as e:
                # The page's checksum doesn't match (the archive was damaged before or while it was copied).
                # Most pictures still show — maybe with a glitch — so hand over what is there instead of
                # refusing the whole book.
                if "CRC" not in str(e):
                    raise
                log.warning("damaged page in %s: %s fails its checksum — shown as it is", b["rel"], name)
                with z.open(name) as fp:
                    fp._expected_crc = None            # zipfile's own switch for "don't verify"
                    return fp.read()

    def names(self, b: dict) -> set:
        if b.get("src") == "folder":
            return set(b["entries"])
        if b.get("src") == "cb7":
            d = self._x7_dir(b)
            return {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()}
        key = (b["rel"], b["mtime"])
        with self._zip_lock:
            z = self._zips.get(key) or zipfile.ZipFile(LIB_ROOT / b["rel"])
            self._zips[key] = z
            return set(z.namelist())

    # ---- JPEG XL / HEIC → PNG (cached per book version in cache/jxl; dropped with the book or after JXL_TTL idle)
    def _jxl_dir(self, b: dict) -> Path:
        return CONFIG_DIR / "cache" / "jxl" / f"{b['id']}-{b['mtime']}"

    def _jxl_touch(self, d: Path):
        """Mark a book's converted pages as used (at most once a minute) — the sweep drops ones idle > JXL_TTL."""
        now = time.time()
        if now - self._jxl_touched.get(d.name, 0) > 60 and d.is_dir():
            self._jxl_touched[d.name] = now
            try:
                os.utime(d)
            except OSError:
                pass

    def transcoded_page(self, b: dict, n: int) -> bytes:
        f = self._jxl_dir(b) / f"{n}.png"
        if f.exists():
            self._jxl_touch(f.parent)
            return f.read_bytes()
        missing = self._decoder_missing([b["entries"][n]])
        if missing:
            raise ValueError(missing)
        with Image.open(io.BytesIO(self.read(b, b["entries"][n]))) as im:
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            buf = io.BytesIO(); im.save(buf, "PNG", compress_level=1)       # fast; it's a cache
        data = buf.getvalue()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f".{f.name}.{threading.get_ident()}.tmp")
        tmp.write_bytes(data); tmp.replace(f)
        return data

    @staticmethod
    def _decoder_missing(names: list) -> str:
        if not JXL_OK and any(n.lower().endswith(JXL_EXT) for n in names):
            return "JPEG XL support isn't installed (pillow-jxl-plugin) — rebuild the image"
        if not HEIC_OK and any(n.lower().endswith(HEIC_EXT) for n in names):
            return "HEIC support isn't installed (pillow-heif) — rebuild the image"
        return ""

    def transcode_status(self, b: dict) -> dict:
        todo = [i for i, n in enumerate(b["entries"]) if n.lower().endswith(TRANSCODE_EXT)]
        d = self._jxl_dir(b)
        done = sum((d / f"{i}.png").exists() for i in todo) if d.is_dir() else 0
        job = self._jxl_jobs.get(b["id"])
        state = "done" if done >= len(todo) else (job or {}).get("state", "idle")
        return {"total": len(todo), "done": done, "state": state, "error": (job or {}).get("error")}

    def transcode_start(self, b: dict) -> dict:
        """Transcode every JPEG XL page of the book in the background (a few at a time); poll transcode_status."""
        st = self.transcode_status(b)
        self._jxl_touch(self._jxl_dir(b))
        if st["state"] in ("done", "running"):
            return st
        missing = self._decoder_missing(b["entries"])
        if missing:
            return {**st, "state": "error", "error": missing}
        job = self._jxl_jobs[b["id"]] = {"state": "running", "error": None}
        todo = [i for i, n in enumerate(b["entries"]) if n.lower().endswith(TRANSCODE_EXT)]

        def run():
            from concurrent.futures import ThreadPoolExecutor
            try:
                with ThreadPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) - 1))) as ex:
                    list(ex.map(lambda i: self.transcoded_page(b, i), todo))
                job["state"] = "done"
            except Exception as e:  # noqa: BLE001
                log.warning("transcode of %s failed: %s", b["rel"], e)
                job.update(state="error", error=str(e))
        threading.Thread(target=run, name=f"jxl-{b['id']}", daemon=True).start()
        return {**st, "state": "running"}

    # ---- screen-sized page copies
    # A 50-megapixel camera photo shown on a 1440p screen makes the browser decode ~12× more pixels than it
    # can display (≈150 ms+ and ~200 MB per page), so page turns stall. The reader asks for pages no
    # bigger than its screen (`max`, long edge in device pixels, one of DISPLAY_SIZES); the server sends a
    # cached copy at that size. Originals stay untouched and are still used for zoom / magnifier.
    DISPLAY_SIZES = (1280, 1920, 2560, 3840)
    _NO_COPY = LOSSLESS_EXT + (".gif",)               # RAW pages stay lossless; GIFs may be animated

    def display_page(self, b: dict, n: int, max_edge: int) -> tuple[bytes, str] | None:
        """(bytes, mime) of page n scaled to fit max_edge, or None when the original is the right answer
        (small enough already, lossless, animated, or not a picture)."""
        name = b["entries"][n]
        if b.get("format") != "images" or is_video(name) or name.lower().endswith(self._NO_COPY):
            return None
        max_edge = min(self.DISPLAY_SIZES, key=lambda x: abs(x - max_edge))
        dims = b.get("dims") or []
        # A long strip (webtoon page) is read at full width and scrolled, so only its *width* is compared with
        # the screen — fitting its length into the screen would shrink it to an unreadable sliver.
        strip = lambda w, h: h >= 2 * w
        edge = lambda w, h: w if strip(w, h) else max(w, h)
        if n < len(dims) and edge(*dims[n]) <= max_edge * 1.15:
            return None                                # already about screen size — nothing to gain
        tag = "w" if n < len(dims) and strip(*dims[n]) else ""
        f = CONFIG_DIR / "cache" / "pages" / f"{b['id']}-{b['mtime']}-{n}-{max_edge}{tag}"
        for ext, mime in ((".jpg", "image/jpeg"), (".webp", "image/webp")):
            if (f.with_suffix(ext)).exists():
                return (f.with_suffix(ext)).read_bytes(), mime
        if f.with_suffix(".orig").exists():
            return None                                # measured before: the original is small enough
        data, _ = self.page(b, n)                      # (JPEG XL / HEIC arrive here already as PNG)
        with Image.open(io.BytesIO(data)) as im:
            if edge(*im.size) <= max_edge * 1.15 or (strip(*im.size) and not tag):
                f.parent.mkdir(parents=True, exist_ok=True); f.with_suffix(".orig").touch()
                return None
            box = (max_edge, 65000) if tag else (max_edge, max_edge)      # (65 535 px is JPEG's limit)
            im.draft("RGB", box)                       # JPEG: decode at 1/2, 1/4… size — the fast part
            im = ImageOps.exif_transpose(im)           # bake in "rotate me": the copy has no EXIF
            alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
            im = im.convert("RGBA" if alpha else "RGB")
            im.thumbnail(box, Image.LANCZOS)
            buf = io.BytesIO()
            if alpha:
                im.save(buf, "WEBP", quality=90, method=3); ext, mime = ".webp", "image/webp"
            else:
                im.save(buf, "JPEG", quality=90, subsampling=0 if b.get("isManga") else 2); ext, mime = ".jpg", "image/jpeg"
        out = buf.getvalue()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f".{f.name}.{threading.get_ident()}.tmp")
        tmp.write_bytes(out); tmp.replace(f.with_suffix(ext))
        return out, mime

    def page(self, b: dict, n: int):
        name = b["entries"][n]
        if name.lower().endswith(TRANSCODE_EXT):        # JPEG XL / HEIC → PNG (cached)
            return self.transcoded_page(b, n), "image/png"
        data = self.read(b, name)
        if name.lower().endswith(BROWSER_UNSAFE):     # TIFF → PNG: lossless, and every browser can show it
            with Image.open(io.BytesIO(data)) as im:
                im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") or "A" in im.getbands() else "RGB")
                buf = io.BytesIO(); im.save(buf, "PNG", compress_level=3)
            return buf.getvalue(), "image/png"
        return data, mimetypes.guess_type(name)[0] or "application/octet-stream"

    def dims(self, b: dict, save: bool = True):
        if b.get("dims") and len(b["dims"]) == len(b["entries"]):
            return b["dims"]
        # Only each picture's *header* is read (a few KB), never the whole page: Pillow learns the size there
        # without decoding. (Reading every page in full made the first open of big photo sets crawl.)
        with self._busy:
            return self._dims(b, save)

    def _dims(self, b: dict, save: bool):
        out = []
        zf = None
        if b["format"] != "video" and b.get("src") not in ("folder", "cb7"):
            zf = zipfile.ZipFile(LIB_ROOT / b["rel"])           # .cbz / .zip / image .epub
        base = (LIB_ROOT / b["rel"]) if b.get("src") == "folder" else self._x7_dir(b) if b.get("src") == "cb7" else None
        try:
            for name in b["entries"]:
                if b["format"] == "video" or is_video(name):
                    out.append([1920, 1080])
                    continue
                try:
                    with (zf.open(name) if zf else open(base / name, "rb")) as f, Image.open(f) as im:
                        w, h = im.size
                        try:                                      # phone photos stored sideways + "rotate me"
                            if im.getexif().get(0x0112) in (5, 6, 7, 8):    # tag: browsers show them upright
                                w, h = h, w
                        except Exception:  # noqa: BLE001
                            pass
                        out.append([w, h])
                except Exception:  # noqa: BLE001
                    out.append([1000, 1500])
        finally:
            if zf:
                zf.close()
        b["dims"] = out
        if save:
            self._save_index()
        return out

    def _thumb_from_bytes(self, data: bytes, w: int) -> bytes:
        with Image.open(io.BytesIO(data)) as im:
            im.draft("RGB", (w * 2, w * 6))
            im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
            im.thumbnail((w, w * 8), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=82, method=4)
            return buf.getvalue()

    def thumb(self, b: dict, n: int, w: int) -> bytes:
        if b["format"] == "video" or is_video(b["entries"][n]):
            raise KeyError("video")                       # the UI shows a ▶ tile / first frame instead
        w = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
        f = self.thumb_dir / f"{b['id']}-{b['mtime']}-{n}-{w}.webp"
        if f.exists():
            return f.read_bytes()
        data = self._thumb_from_bytes(self.read(b, b["entries"][n]), w)
        f.write_bytes(data)
        return data

    # ---- video covers: a frame grabbed with ffmpeg, cached once, then sized like any photo
    FFMPEG = shutil.which("ffmpeg")
    FFPROBE = shutil.which("ffprobe")
    _ff_slots = threading.BoundedSemaphore(2)          # a grid full of videos mustn't spawn 50 ffmpegs

    @staticmethod
    def _video_only(b: dict) -> bool:
        return b["format"] == "video" or (b["format"] == "images" and bool(b.get("entries"))
                                           and all(is_video(n) for n in b["entries"]))

    def has_cover(self, b: dict) -> bool:
        if self._video_only(b):
            return bool(self.FFMPEG)                   # photo-less set / standalone video → frame from the video
        if b["format"] == "images":
            return any(not is_video(n) for n in b.get("entries", []))
        return bool(b.get("cover"))

    def _video_frame(self, b: dict, n: int) -> bytes | None:
        f = self.thumb_dir / f"{b['id']}-{b['mtime']}-{n}-frame.jpg"
        if f.exists():
            return f.read_bytes() or None              # empty file = ffmpeg failed before, don't retry
        if not self.FFMPEG:
            return None
        path, start, length = self.media_span(b, n)
        # a video STORED inside a .cbz is read in place via ffmpeg's subfile protocol
        src = str(path) if not start else f"subfile,,start,{start},end,{start + length},,:{path}"
        def grab(at: float) -> bytes:
            # seek a bit in (skips black fades / logo cards), then `thumbnail` picks the most typical frame
            cmd = [self.FFMPEG, "-v", "error", "-nostdin", "-ss", f"{at:.2f}", "-i", src, "-an", "-sn",
                   "-vf", "thumbnail=40,scale='min(1280,iw)':-2", "-frames:v", "1",
                   "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "pipe:1"]
            try:
                return subprocess.run(cmd, capture_output=True, timeout=45).stdout
            except (OSError, subprocess.TimeoutExpired):
                return b""
        with self._ff_slots:
            if f.exists():
                return f.read_bytes() or None
            dur = 0.0
            if self.FFPROBE:
                try:
                    dur = float(subprocess.run([self.FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                                "-of", "default=nw=1:nk=1", src],
                                               capture_output=True, text=True, timeout=20).stdout.strip() or 0)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass
            data = (grab(min(dur * 0.1, 15.0)) if dur > 1 else b"") or grab(0)   # short clip / bad seek → start
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        if not data:
            log.warning("couldn't grab a cover frame from %s", b["rel"])
        return data or None

    # A collection card shows its first covers as a little stack. Drawing the two tilted, dimmed, shadowed
    # back covers live costs the browser a lot when there are hundreds of cards (choppy scrolling), so the
    # server draws them once into one transparent picture; only the front cover stays a live <img>.
    # Geometry matches the old CSS: the picture spans 140% × 130% of the card, centred on it.
    STACK_W = 240                                    # back-cover width inside the picture (px)
    STACK_SHEETS = ((7, -4, 4, .94, .7), (-7, -5, -5, .9, .5))   # dx%, dy%, degrees, scale, brightness

    def stack_back(self, books: list[dict]) -> bytes | None:
        from PIL import ImageDraw, ImageEnhance, ImageFilter
        books = books[:2]
        key = "-".join(f"{b['id']}-{b['mtime']}" for b in books)
        f = self.thumb_dir / f"{key}-stack-{self.STACK_W}.webp"
        if f.exists():
            return f.read_bytes()
        W = self.STACK_W; H = W * 3 // 2; k = W / 168      # the CSS was tuned on ~168 px wide cards
        cw, ch = round(W * 1.4), round(H * 1.3)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        r = round(10 * k)
        mask = Image.new("L", (W, H), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), r, fill=255)
        for b, (dx, dy, deg, sc, bright) in reversed(list(zip(books, self.STACK_SHEETS))):   # back-most first
            data = self.cover(b, 320)
            if not data:
                continue
            with Image.open(io.BytesIO(data)) as im:
                im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)    # object-fit: cover
            im = ImageEnhance.Brightness(im).enhance(bright)
            sheet = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sheet.paste(im, (0, 0), mask)
            ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))                     # the faint 1px edge
            ImageDraw.Draw(ring).rounded_rectangle((0, 0, W - 1, H - 1), r, outline=(255, 255, 255, 15), width=max(1, round(k)))
            sheet = Image.alpha_composite(sheet, ring)
            # soft shadow: 0 14px 30px -14px rgba(0,0,0,.9)
            pad = round(40 * k)
            sh = Image.new("RGBA", (W + 2 * pad, H + 2 * pad), (0, 0, 0, 0))
            spread = round(14 * k); off = round(14 * k)
            ImageDraw.Draw(sh).rounded_rectangle((pad + spread, pad + spread + off, pad + W - spread, pad + H - spread + off), r, fill=(0, 0, 0, 230))
            sh = sh.filter(ImageFilter.GaussianBlur(15 * k))
            sh.alpha_composite(sheet, (pad, pad))
            sh = sh.resize((round(sh.width * sc), round(sh.height * sc)), Image.LANCZOS)
            sh = sh.rotate(-deg, resample=Image.BICUBIC, expand=True)           # CSS rotate is clockwise
            cx, cy = cw / 2 + dx / 100 * W, ch / 2 + dy / 100 * H
            canvas.alpha_composite(sh, (round(cx - sh.width / 2), round(cy - sh.height / 2)))
        buf = io.BytesIO(); canvas.save(buf, "WEBP", quality=88, method=4)
        out = buf.getvalue()
        f.write_bytes(out)
        return out

    def cover(self, b: dict, w: int) -> bytes | None:
        if self._video_only(b):
            w = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
            f = self.thumb_dir / f"{b['id']}-{b['mtime']}-vcover-{w}.webp"
            if f.exists():
                return f.read_bytes()
            frame = self._video_frame(b, 0)
            if not frame:
                return None
            data = self._thumb_from_bytes(frame, w)
            f.write_bytes(data)
            return data
        if b["format"] == "images":
            first = b["entries"].index(b["cover"]) if b.get("cover") in b["entries"] else \
                next((i for i, n in enumerate(b["entries"]) if not is_video(n)), None)
            return None if first is None else self.thumb(b, first, w)
        if not b.get("cover"):
            return None
        w = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
        f = self.thumb_dir / f"{b['id']}-{b['mtime']}-cover-{w}.webp"
        if f.exists():
            return f.read_bytes()
        data = self._thumb_from_bytes(self.read(b, b["cover"]), w)
        f.write_bytes(data)
        return data

    def panels(self, b: dict, n: int, rtl: bool):
        f = self.panel_dir / f"{b['id']}-{b['mtime']}-{n}-{int(rtl)}.json"
        if f.exists():
            return json.loads(f.read_text())
        with Image.open(io.BytesIO(self.read(b, b["entries"][n]))) as im:
            boxes = detect_panels(im, rtl)
        f.write_text(json.dumps(boxes))
        return boxes

    # ---- EPUB text
    def chapter(self, b: dict, i: int) -> dict:
        ch = b["chapters"][i]
        spine_index = {c["href"]: k for k, c in enumerate(b["chapters"])}
        names = self.names(b)

        def res_url(path):
            return f"/api/books/{b['id']}/res/{quote(path)}?v={b['mtime']}"

        def img_size(path):
            if path not in names:
                return None
            try:
                with Image.open(io.BytesIO(self.read(b, path))) as im:
                    return im.size
            except Exception:
                return None

        html_out = epubmod.render_chapter(self.read(b, ch["href"]), ch["href"], spine_index, res_url, img_size)
        return {"index": i, "title": ch.get("title"), "html": html_out}

    def resource(self, b: dict, path: str):
        path = posixpath.normpath(unquote(path)).lstrip("/")
        mime = mimetypes.guess_type(path)[0] or ""
        if not (mime.startswith("image/") or mime.startswith("font/")):
            raise KeyError(path)
        return self.read(b, path), mime
