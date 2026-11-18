"""Name rules: chapter numbers, brackets, safe file names, credits in a name ("[Circle (Artist)]"), and
the Cosplay rules Cosplayer → Set → Variant (docs/NAMING.md). No files are touched here — library.py does that."""
from __future__ import annotations

import hashlib
import html
import posixpath
import re
from pathlib import Path


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
    dashed = re.match(r"\s*-\s", stem[m.end():]) is not None   # "[Author] - Series - Ch. 01" (docs/NAMING.md)
    if numbered and not ca and not dashed:
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


def set_of(work: str) -> str:
    """The set in a Cosplay work title: "Starfall Bunny - Bonus" → "Starfall Bunny" (the variant is after the dash)."""
    head, sep, tail = work.rpartition(" - ")
    return tidy(head) if sep and tidy(head) and tidy(tail) else work


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
        # "Cosplayer - Set - Variant" (docs/NAMING.md): a second " - " marks the variant outright
        works = [set_of(parsed[n]["work"]) for n in group]
        found = variant_groups(works)
        for i, n in enumerate(group):
            work = works[i]
            if i in found:
                set_name = tidy(found[i][0]) or found[i][0]
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
