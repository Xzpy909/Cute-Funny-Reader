"""Pictures and caches: pages, display copies, thumbnails, covers, stacks, panels, .cb7 unpacking,
JPEG XL / HEIC conversion, video frames, and the cache sweep.

Part of the Library class (library.py: class Library(…, MediaMixin, …)) — methods and attributes unchanged; LIB_ROOT,
CONFIG_DIR and EMPTY_FOLDER_AFTER are read from library.py at call time (_L.…) so tests can swap them."""
from __future__ import annotations

import io
import json
import mimetypes
import os
import posixpath
import re
import shutil
import struct
import subprocess
import threading
import time
import zipfile

from pathlib import Path
from urllib.parse import quote, unquote

from PIL import Image, ImageOps

from . import library as _L
from . import epub as epubmod
from .panels import detect_panels
from .library import BROWSER_UNSAFE, HEIC_EXT, HEIC_OK, JXL_EXT, JXL_OK, LOSSLESS_EXT, THUMB_WIDTHS, TRANSCODE_EXT, TRANSCODE_TTL, _safe_member, is_video, log


class MediaMixin:
    # ---- cache clean-up
    # Every cache entry is named "<book id>-<mtime>…" (thumbs, video frames, panels, extracted .cb7s,
    # unpacked videos). After a scan, entries whose key isn't a live book belong to a file that was
    # deleted, moved/renamed (new id) or changed (new mtime) — they can never be hit again.
    CACHE_KEY = re.compile(r"^([0-9a-f]{12}-\d+)")

    CACHE_GRACE = 600                                  # leave anything touched in the last 10 min alone

    def sweep_cache(self) -> dict:
        if not _L.LIB_ROOT.is_dir() or not any(_L.LIB_ROOT.iterdir()):
            return {}                                  # /data not mounted → don't mistake that for "all deleted"
        with self.lock:
            live = {f"{b['id']}-{b['mtime']}" for b in self.books.values()}
            live_rel = {(b["rel"], b["mtime"]) for b in self.books.values()}
        cache = _L.CONFIG_DIR / "cache"
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
        for old in ("jxl", "packs"):                   # left-overs of older versions (cache/jxl → cache/transcoded;
            if (cache / old).is_dir():                 # uploads used to be staged in cache/packs)
                shutil.rmtree(cache / old, ignore_errors=True)
        for sub in ("thumbs", "panels", "media", "cb7", "transcoded", "pages"):
            d = cache / sub
            if not d.is_dir():
                continue
            for p in d.iterdir():
                m = self.CACHE_KEY.match(p.name)
                if m and m.group(1) not in live:
                    drop(p)
                elif m and sub == "transcoded" and p.is_dir():   # JPEG XL / HEIC → PNG is temporary: unused a while → rebuilt on open
                    job = self._transcode_jobs.get(p.name.split("-")[0], {})
                    try:
                        idle = time.time() - p.stat().st_mtime > TRANSCODE_TTL
                    except OSError:
                        idle = False
                    if idle and job.get("state") != "running":
                        drop(p)
                        self._transcode_jobs.pop(p.name.split("-")[0], None)
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

    def forget_extracted(self, b: dict):
        """Drop the extracted copy of a .cb7 that was replaced in place (its cache name holds the file's mtime in
        seconds — a swap within the same second would otherwise keep serving the old pages)."""
        for d in (_L.CONFIG_DIR / "cache" / "cb7").glob(f"{b['id']}-*"):
            shutil.rmtree(d, ignore_errors=True)

    def _x7_dir(self, b: dict) -> Path:
        """.cb7 (solid 7z) can't be read entry-by-entry cheaply: extract once into the cache."""
        d = _L.CONFIG_DIR / "cache" / "cb7" / f"{b['id']}-{b['mtime']}"
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
                with py7zr.SevenZipFile(_L.LIB_ROOT / b["rel"]) as z:
                    targets = [f.filename for f in z.list() if not f.is_directory and _safe_member(f.filename)]
                with py7zr.SevenZipFile(_L.LIB_ROOT / b["rel"]) as z:
                    z.extract(path=tmp, targets=targets)
                tmp.rename(d)
        return d

    def media_span(self, b: dict, n: int):
        """(file path, start offset, length) of page n on disk — lets videos stream with Range
        requests straight out of uncompressed (STORED) zip entries without extracting them."""
        if b["format"] == "video":
            p = _L.LIB_ROOT / b["rel"]
            return p, 0, p.stat().st_size
        name = b["entries"][n]
        if b.get("src") in ("cb7", "folder"):
            p = (self._x7_dir(b) if b["src"] == "cb7" else _L.LIB_ROOT / b["rel"]) / name
            return p, 0, p.stat().st_size
        path = _L.LIB_ROOT / b["rel"]
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
        c = _L.CONFIG_DIR / "cache" / "media" / f"{b['id']}-{b['mtime']}-{n}{Path(name).suffix.lower()}"
        if not c.exists():
            c.parent.mkdir(parents=True, exist_ok=True)
            c.write_bytes(self.read(b, name))
        return c, 0, c.stat().st_size

    def read(self, b: dict, name: str) -> bytes:
        if b.get("src") == "folder":
            return (_L.LIB_ROOT / b["rel"] / name).read_bytes()
        if b.get("src") == "cb7":
            return (self._x7_dir(b) / name).read_bytes()
        if b["format"] == "video":
            return (_L.LIB_ROOT / b["rel"]).read_bytes()
        key = (b["rel"], b["mtime"])
        with self._zip_lock:
            z = self._zips.pop(key, None) or zipfile.ZipFile(_L.LIB_ROOT / b["rel"])
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
            z = self._zips.get(key) or zipfile.ZipFile(_L.LIB_ROOT / b["rel"])
            self._zips[key] = z
            return set(z.namelist())

    # ---- JPEG XL / HEIC → PNG (cached per book version in cache/transcoded; dropped with the book or after TRANSCODE_TTL idle)
    def _transcode_dir(self, b: dict) -> Path:
        return _L.CONFIG_DIR / "cache" / "transcoded" / f"{b['id']}-{b['mtime']}"

    def _transcode_touch(self, d: Path):
        """Mark a book's converted pages as used (at most once a minute) — the sweep drops ones idle > TRANSCODE_TTL."""
        now = time.time()
        if now - self._transcode_touched.get(d.name, 0) > 60 and d.is_dir():
            self._transcode_touched[d.name] = now
            try:
                os.utime(d)
            except OSError:
                pass

    def transcoded_page(self, b: dict, n: int) -> bytes:
        f = self._transcode_dir(b) / f"{n}.png"
        if f.exists():
            self._transcode_touch(f.parent)
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
        d = self._transcode_dir(b)
        done = sum((d / f"{i}.png").exists() for i in todo) if d.is_dir() else 0
        job = self._transcode_jobs.get(b["id"])
        state = "done" if done >= len(todo) else (job or {}).get("state", "idle")
        return {"total": len(todo), "done": done, "state": state, "error": (job or {}).get("error")}

    def transcode_start(self, b: dict, owner: str | None = None) -> dict:
        """Transcode every JPEG XL page of the book in the background (a few at a time); poll transcode_status."""
        st = self.transcode_status(b)
        self._transcode_touch(self._transcode_dir(b))
        if st["state"] in ("done", "running"):
            return st
        missing = self._decoder_missing(b["entries"])
        if missing:
            return {**st, "state": "error", "error": missing}
        job = self._transcode_jobs[b["id"]] = {"state": "running", "error": None}
        todo = [i for i, n in enumerate(b["entries"]) if n.lower().endswith(TRANSCODE_EXT)]

        def run():
            from concurrent.futures import ThreadPoolExecutor
            kind = "HEIC" if any(n.lower().endswith(HEIC_EXT) for n in b["entries"]) else "JPEG XL"
            try:
                with self.track("transcode", f"Converting {b['series']} · {b['label']} ({kind})", owner, "pages",
                                len(todo), after=0, ref=b["id"]) as tracker, \
                        ThreadPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) - 1))) as ex:
                    for _ in ex.map(lambda i: self.transcoded_page(b, i), todo):
                        tracker.progress(n=1)
                job["state"] = "done"
            except Exception as e:  # noqa: BLE001
                log.warning("transcode of %s failed: %s", b["rel"], e)
                job.update(state="error", error=str(e))
        threading.Thread(target=run, name=f"transcode-{b['id']}", daemon=True).start()
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
        f = _L.CONFIG_DIR / "cache" / "pages" / f"{b['id']}-{b['mtime']}-{n}-{max_edge}{tag}"
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
            zf = zipfile.ZipFile(_L.LIB_ROOT / b["rel"])           # .cbz / .zip / image .epub
        base = (_L.LIB_ROOT / b["rel"]) if b.get("src") == "folder" else self._x7_dir(b) if b.get("src") == "cb7" else None
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
        video = b["format"] == "video" or is_video(b["entries"][n])
        w = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
        f = self.thumb_dir / f"{b['id']}-{b['mtime']}-{n}-{w}.webp"
        if f.exists():
            return f.read_bytes()
        if video:                                         # a frame from the video (ffmpeg), sized like a page
            frame = self._video_frame(b, n)
            if not frame:
                raise KeyError("video")                   # no ffmpeg / unreadable: the UI keeps its ▶ tile
            data = self._thumb_from_bytes(frame, w)
            f.write_bytes(data)
            return data
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
        key = "-".join(f"{b['id']}-{b['mtime']}" for b in books) + "-c" + ".".join(self.cover_tag(b) for b in books)
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
        b = self.effective(b)                          # a cover page chosen in the reader counts
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
            first = b["entries"].index(b["cover"]) if b.get("cover") in b["entries"] else\
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
