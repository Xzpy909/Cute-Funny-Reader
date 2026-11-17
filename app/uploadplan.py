"""Upload planning: what a drop of files and folders becomes. The browser sends the dropped paths (and the
text of any metadata.json / ComicInfo.xml in them), the server answers with the plan, and the browser only
carries it out. The naming rules live here and in library.py only — the browser used to keep its own copy
(seriesStem) and the two drifted ("Name Ch.1" was read differently).

Comics / manga:
   folder of images                    → a series with one chapter (packed into <folder>.cbz)
   folder whose subfolders are images  → a series, one chapter per subfolder
   folder of numbered chapters         → a series (folder name = series name)
   folder of unrelated archives        → a collection, each archive its own series
   folder of series folders            → a collection containing those series
   image folders side by side "Name 1", "Name 2" → one series "Name", a chapter each

Cosplay (Cosplayer → Set → Variant, docs/NAMING.md): every set in a drop — a folder of photos (± videos) or an
archive — is one *unit*, placed by cosplay_plan. A dropped folder of sets names the cosplayer when the set
names don't; a folder holding only archives is one set with each archive a variant. Photo units are packed
into <name>.zip, video-only units stay folders of videos.

A plan is a list of jobs:
   {"kind": "file", "file": i, "name": …, + place}       upload dropped item i as it is
   {"kind": "pack", "name": "….cbz", "images": [i…], "extras": [i…], + place}   pack these into one archive
   place: series (an existing series id) | collection (a folder name) + folder (the series / set folder)
"""
from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from . import library as L

IMG_RE = re.compile(r"\.(jpe?g|png|webp|avif|gif|bmp|tiff?|jxl|heic|heif)$", re.I)
VIDEO_RE = re.compile(r"\.(mp4|webm|mkv|mov|m4v)$", re.I)
BOOK_RE = re.compile(r"\.(cbz|zip|cb7|cbr|epub|rar|7z)$", re.I)
META_RE = re.compile(r"^(metadata\.json|comicinfo\.xml)$", re.I)


def nat_key(s: str):
    """Natural, case- and accent-blind order ("Ch 2" before "Ch 10")."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode() or s
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.casefold()) for t in re.split(r"(\d+)", s) if t]


def safe_name(v: str) -> str:
    return L.safe_component(v)[:150] or "Untitled"


def stem(name: str, is_file: bool = True) -> tuple[float | None, str]:
    """(number, text before it) — the server's own chapter-number rules (library.parse_number). Folders have
    no extension: "Name Ch.1" keeps its ".1"."""
    s = Path(name).stem if is_file else name
    _, num, before = L.parse_number(s)
    return num, before


def read_meta(name: str, text: str) -> dict:
    """{title, series} from the text of a metadata.json / ComicInfo.xml (unreadable → {})."""
    try:
        if name.lower().endswith(".json"):
            d = json.loads(text.lstrip("﻿"))
            return {"title": d["title"].strip()} if isinstance(d, dict) and isinstance(d.get("title"), str) else {"title": ""}
        root = ET.fromstring(text.encode("utf-8"))
        tag = lambda t: ((root.find(t).text or "").strip() if root.find(t) is not None else "")
        series, num = tag("Series"), tag("Number")
        return {"title": tag("Title") or (f"{series} {num}" if series and num else ""), "series": series}
    except Exception:  # noqa: BLE001
        return {}


class Node:
    def __init__(self, name: str):
        self.name, self.dirs, self.files = name, {}, []     # files: indices into the drop


class Planner:
    def __init__(self, items: list[dict], meta: dict | None = None, today: str = ""):
        self.items = items                                 # [{"path": "a/b/001.jpg", "size": n}, …]
        self.meta = {int(i): read_meta(self.fname(int(i)), t) for i, t in (meta or {}).items()
                     if str(i).isdigit() and 0 <= int(i) < len(items) and isinstance(t, str)}
        self.today = today or "today"
        self.root = Node("")
        for i, it in enumerate(items):
            parts = [p for p in str(it.get("path") or "").split("/") if p]
            node = self.root
            for p in parts[:-1]:
                node = node.dirs.setdefault(p, Node(p))
            node.files.append(i)

    # ---- the drop
    def fname(self, i: int) -> str:
        return str(self.items[i].get("path") or "").rstrip("/").rsplit("/", 1)[-1]

    def size(self, i: int) -> int:
        return int(self.items[i].get("size") or 0)

    def sort(self, idx: list[int]) -> list[int]:
        return sorted(idx, key=lambda i: nat_key(self.fname(i)))

    def has_images(self, n: Node) -> bool:
        return any(IMG_RE.search(self.fname(i)) for i in n.files)

    def archives_in(self, n: Node) -> list[int]:
        imgs = self.has_images(n)
        return self.sort([i for i in n.files if BOOK_RE.search(self.fname(i)) or (not imgs and VIDEO_RE.search(self.fname(i)))])

    def images_in(self, n: Node) -> list[int]:
        """A folder holding images packs ALL its media (videos between photos stay in order)."""
        if not self.has_images(n):
            return []
        return self.sort([i for i in n.files if IMG_RE.search(self.fname(i)) or VIDEO_RE.search(self.fname(i))])

    def media_in(self, n: Node) -> list[int]:
        return self.sort([i for i in n.files if IMG_RE.search(self.fname(i)) or VIDEO_RE.search(self.fname(i))])

    def books_in(self, n: Node) -> list[int]:
        return self.sort([i for i in n.files if BOOK_RE.search(self.fname(i))])

    def meta_in(self, n: Node) -> list[int]:
        return [i for i in n.files if META_RE.match(self.fname(i))]

    def is_image_folder(self, n: Node) -> bool:
        return bool(self.images_in(n)) and not self.archives_in(n) and not n.dirs

    def folder_meta(self, n: Node) -> dict:
        out = {}
        for i in self.meta_in(n):                          # metadata.json wins over ComicInfo.xml
            m = self.meta.get(i, {})
            if self.fname(i).lower().endswith(".json"):
                if m.get("title"):
                    out["title"] = m["title"]
            else:
                out["title"] = out.get("title") or m.get("title")
                out["series"] = m.get("series")
        return out

    def title_of(self, n: Node) -> str:                    # the packed file
        return L.tidy(self.folder_meta(n).get("title") or "") or n.name

    def series_of(self, n: Node) -> str:                   # its folder
        m = self.folder_meta(n)
        return L.tidy(m.get("series") or m.get("title") or "") or n.name

    def related_archives(self, files: list[int]) -> bool:
        """Archives of one series: numbered the same way ("Name 01", "Name 02"; a plain "Name" is part 1)."""
        if len(files) < 2:
            return True
        parsed = [stem(self.fname(i)) for i in files]
        keys = {L.tidy(b).lower() for n, b in parsed if n is not None}
        loose = [b for n, b in parsed if n is None]
        return len(keys) == 1 and (not loose or (len(loose) == 1 and L.tidy(loose[0]).lower() in keys))

    def stem_groups(self, dirs: list[Node]) -> tuple[list[dict], list[Node]]:
        """Sibling folders "Name 1", "Name 2" / "Name Ch.1", "Name Ch.2" (+ a plain "Name" = part 1) belong together."""
        def key(d):
            n, b = stem(d.name, False)
            name = L.tidy(b)
            return name.lower(), name, n
        groups: dict[str, dict] = {}
        for d in dirs:
            k, name, n = key(d)
            if n is not None and k:
                groups.setdefault(k, {"name": name, "dirs": []})["dirs"].append(d)
        for d in dirs:
            k, _, n = key(d)
            if n is None and k in groups:
                groups[k]["dirs"].insert(0, d)
        out = [g for g in groups.values() if len(g["dirs"]) >= 2]
        for g in out:
            lead, nums = g["dirs"][0], g["dirs"][1:]
            if key(lead)[2] is None:
                g["dirs"] = [lead] + sorted(nums, key=lambda x: key(x)[2])
            else:
                g["dirs"] = sorted(g["dirs"], key=lambda x: key(x)[2])
        used = {id(d) for g in out for d in g["dirs"]}
        return out, [d for d in dirs if id(d) not in used]

    # ---- jobs
    @staticmethod
    def _place(**kw) -> dict:
        return {k: v for k, v in kw.items() if v}

    def _file(self, jobs, i, place):
        jobs.append({"kind": "file", "file": i, "name": self.fname(i), "size": self.size(i), **place})

    def _pack(self, jobs, name, images, place, extras=(), ext=".cbz"):
        jobs.append({"kind": "pack", "name": safe_name(name) + ext, "images": list(images), "extras": list(extras),
                     "size": sum(self.size(i) for i in images), **place})

    def comics(self, series: str | None = None, col: str | None = None) -> list[dict]:
        jobs: list[dict] = []
        root = self.root
        top = self._place(series=series, collection=col)
        for i in self.archives_in(root):
            self._file(jobs, i, top)
        if self.images_in(root):
            m = self.folder_meta(root)
            nm = L.tidy(m.get("title") or "") or (f"Chapter {self.today}" if series else f"Images {self.today}")
            place = top if series else {**top, "folder": safe_name(L.tidy(m.get("series") or "") or nm)}
            self._pack(jobs, nm, self.images_in(root), place, self.meta_in(root))

        def plan_folder(d: Node, c_series: str | None, c_col: str | None):
            subs = list(d.dirs.values())
            img_subs = sorted([x for x in subs if self.is_image_folder(x)], key=lambda x: nat_key(x.name))
            other = [x for x in subs if x not in img_subs]
            arcs, imgs = self.archives_in(d), self.images_in(d)
            as_col = not c_series and not c_col and (bool(other) or (len(arcs) > 1 and not self.related_archives(arcs)
                                                                   and not imgs and not img_subs))
            sp = {"series": c_series} if c_series else self._place(collection=c_col, folder=safe_name(self.series_of(d)))
            if as_col:
                for i in arcs:
                    self._file(jobs, i, {"collection": d.name})               # loose = one series each
                if imgs:
                    self._pack(jobs, self.title_of(d), imgs, {"collection": d.name, "folder": safe_name(self.series_of(d))}, self.meta_in(d))
                groups, rest = self.stem_groups(img_subs)                     # "Name 1", "Name 2" → series "Name"
                for g in groups:
                    for x in g["dirs"]:
                        self._pack(jobs, self.title_of(x), self.images_in(x), {"collection": d.name, "folder": safe_name(g["name"])}, self.meta_in(x))
                for x in rest:
                    self._pack(jobs, self.title_of(x), self.images_in(x), {"collection": d.name, "folder": safe_name(self.series_of(x))}, self.meta_in(x))
                for x in other:
                    plan_folder(x, None, d.name)
                return
            if imgs:
                self._pack(jobs, self.title_of(d), imgs, sp, self.meta_in(d))      # the folder itself is a chapter
            for x in img_subs:
                self._pack(jobs, self.title_of(x), self.images_in(x), sp, self.meta_in(x))   # each image subfolder is a chapter
            for i in arcs:
                self._file(jobs, i, sp)
            for x in other:
                plan_folder(x, c_series, c_col)

        dirs = list(root.dirs.values())
        groups, _ = ([], dirs) if series else self.stem_groups([d for d in dirs if self.is_image_folder(d)])
        for g in groups:
            for x in g["dirs"]:
                self._pack(jobs, self.title_of(x), self.images_in(x), self._place(collection=col, folder=safe_name(g["name"])), self.meta_in(x))
        grouped = {id(x) for g in groups for x in g["dirs"]}
        for d in dirs:
            if id(d) not in grouped:
                plan_folder(d, series, col)
        return jobs

    def cosplay_units(self) -> list[dict]:
        units, root = [], self.root
        stamp = f"Set {self.today}"
        if self.media_in(root):
            units.append({"name": L.tidy(self.folder_meta(root).get("title") or "") or stamp, "media": self.media_in(root), "extras": self.meta_in(root)})
        for i in self.books_in(root):
            units.append({"name": Path(self.fname(i)).stem, "file": i})

        def walk(d: Node, parent: str | None):
            if not d.dirs:
                if self.media_in(d):
                    units.append({"name": self.title_of(d), "media": self.media_in(d), "parent": parent, "extras": self.meta_in(d)})
                for i in self.books_in(d):                 # a folder of archives = one set, archives = its variants
                    units.append({"name": Path(self.fname(i)).stem, "file": i, "parent": parent,
                                  "setHint": None if self.media_in(d) else d.name})
                return
            if self.media_in(d):
                units.append({"name": self.title_of(d), "media": self.media_in(d), "parent": parent, "extras": self.meta_in(d)})
            for i in self.books_in(d):
                units.append({"name": Path(self.fname(i)).stem, "file": i, "parent": d.name})
            for x in sorted(d.dirs.values(), key=lambda x: nat_key(x.name)):
                walk(x, d.name)

        for d in sorted(root.dirs.values(), key=lambda x: nat_key(x.name)):
            walk(d, None)
        return units

    def cosplay(self, lib_root: Path, series: str | None = None, col: str | None = None) -> list[dict]:
        units = self.cosplay_units()
        plans = {} if series else L.cosplay_plan(lib_root, list(dict.fromkeys(u["name"] for u in units)))
        jobs: list[dict] = []
        for u in units:
            p = plans.get(u["name"], {})
            place = {"series": series} if series else \
                self._place(collection=col or p.get("cosplayer") or u.get("parent"), folder=safe_name(u.get("setHint") or p.get("set") or u["name"]))
            if "file" in u:
                self._file(jobs, u["file"], place)
            elif any(IMG_RE.search(self.fname(i)) for i in u["media"]):   # photos (± videos in their place) → <name>.zip
                self._pack(jobs, u["name"], u["media"], place, u.get("extras") or [], ".zip")
            else:                                          # video-only variant → its own folder of videos
                sub = safe_name(u["name"])
                for i in u["media"]:
                    self._file(jobs, i, {**place, "folder": f"{place['folder']}/{sub}" if place.get("folder") else sub})
        return jobs


def plan(lib: dict, items: list[dict], meta: dict | None = None, series: str | None = None,
         collection: str | None = None, today: str = "") -> list[dict]:
    """The plan for one drop into library `lib` (see the module docstring)."""
    p = Planner(items, meta, today)
    if lib.get("type") == "cosplay":
        return p.cosplay(L.LIB_ROOT / lib["path"], series, collection)
    return p.comics(series, collection)
