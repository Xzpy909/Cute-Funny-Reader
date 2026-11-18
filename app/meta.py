"""Metadata inside books: ComicInfo.xml, metadata.json and info.yaml — read, merged, and written back
(build_metadata). Pure functions on bytes / dicts; library.py reads and writes the files."""
from __future__ import annotations

import json
import logging
import posixpath
import re
import time
import xml.etree.ElementTree as ET

log = logging.getLogger("cfreader")


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
