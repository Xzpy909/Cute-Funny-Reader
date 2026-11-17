"""EPUB parsing (OPF, spine, TOC) and chapter sanitising."""
from __future__ import annotations

import html
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
}
DROP = ["script", "style", "link", "meta", "iframe", "object", "embed", "form", "input",
        "button", "base", "title", "noscript", "audio", "video", "source", "head"]
IMG_RE = re.compile(r"<(?:img|image)\b[^>]*?\s(?:src|xlink:href|href)\s*=\s*[\"']([^\"']+)", re.I)
HEAD_RE = re.compile(r"(?is)<head.*?</head>")
TAG_RE = re.compile(r"<[^>]+>")
H_RE = re.compile(r"(?is)<h[1-3]\b[^>]*>(.*?)</h[1-3]>")


def resolve(base_href: str, ref: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_href), unquote(ref)))


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", s))).strip()


def read_toc(z: zipfile.ZipFile, items: dict, spine_el, ) -> dict:
    """Map spine href (no fragment) -> label, from EPUB3 nav or EPUB2 NCX."""
    toc: dict[str, str] = {}
    nav = next((it for it in items.values() if "nav" in it["props"].split()), None)
    if nav:
        try:
            soup = BeautifulSoup(z.read(nav["href"]), "html.parser")
            navs = soup.find_all("nav")
            el = next((n for n in navs if "toc" in (n.get("epub:type") or "")), navs[0] if navs else soup)
            for a in el.find_all("a", href=True):
                path = urlsplit(a["href"]).path
                if not path:
                    continue
                target = resolve(nav["href"], path)
                label = re.sub(r"\s+", " ", a.get_text(" ")).strip()
                if label and target not in toc:
                    toc[target] = label
        except Exception:
            pass
    if not toc:
        ncx_id = spine_el.get("toc")
        ncx = items.get(ncx_id) if ncx_id else next((it for it in items.values() if it["type"] == "application/x-dtbncx+xml"), None)
        if ncx:
            try:
                root = ET.fromstring(z.read(ncx["href"]))
                for np in root.iter(f"{{{NS['ncx']}}}navPoint"):
                    label = np.findtext("ncx:navLabel/ncx:text", default="", namespaces=NS).strip()
                    content = np.find("ncx:content", NS)
                    if content is None:
                        continue
                    target = resolve(ncx["href"], urlsplit(content.get("src", "")).path)
                    if label and target not in toc:
                        toc[target] = label
            except Exception:
                pass
    return toc


def parse_epub(path) -> dict:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        cont = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = cont.find(".//c:rootfile", NS).get("full-path")
        base = posixpath.dirname(opf_path)
        opf = ET.fromstring(z.read(opf_path))
        md = opf.find("opf:metadata", NS)

        def t(tag):
            return (md.findtext(tag, default="", namespaces=NS) or "").strip() if md is not None else ""

        meta = {"title": t("dc:title"), "writer": t("dc:creator"), "publisher": t("dc:publisher"),
                "summary": _text(t("dc:description"))}
        if md is not None:
            subj = [x.text.strip() for x in md.findall("dc:subject", NS) if x.text and x.text.strip()]
            if subj:
                meta["tags"] = ", ".join(subj)

        items = {}
        for it in opf.find("opf:manifest", NS):
            href = posixpath.normpath(posixpath.join(base, unquote(it.get("href", ""))))
            items[it.get("id")] = {"href": href, "type": it.get("media-type", ""), "props": it.get("properties", "")}

        cover = next((it["href"] for it in items.values() if "cover-image" in it["props"].split()), None)
        if not cover and md is not None:
            m = md.find("opf:meta[@name='cover']", NS)
            if m is not None:
                c = items.get(m.get("content"))
                if c and c["type"].startswith("image/"):
                    cover = c["href"]
                else:  # some tools put the file name instead of the id
                    cand = next((it["href"] for it in items.values()
                                 if posixpath.basename(it["href"]) == m.get("content")), None)
                    cover = cand

        spine_el = opf.find("opf:spine", NS)
        rtl = spine_el.get("page-progression-direction") == "rtl"
        spine = [items[i.get("idref")]["href"] for i in spine_el
                 if i.get("idref") in items and i.get("linear", "yes") != "no"
                 and items[i.get("idref")]["href"] in names]
        toc = read_toc(z, items, spine_el)

        chapters, pages, first_img = [], [], None
        for href in spine:
            doc = z.read(href).decode("utf-8", "replace")
            body = HEAD_RE.sub("", doc)
            imgs = IMG_RE.findall(body)
            words = len(_text(body).split())
            if imgs and first_img is None:
                first_img = resolve(href, imgs[0])
            if len(imgs) == 1 and words < 30:
                pages.append(resolve(href, imgs[0]))
            title = toc.get(href)
            if not title:
                h = H_RE.search(body)
                title = _text(h.group(1))[:90] if h and _text(h.group(1)) else None
            chapters.append({"href": href, "title": title})

        image_book = spine and len(pages) >= 0.9 * len(spine) and all(p in names for p in pages)
        if not cover or cover not in names:
            cover = first_img if first_img in names else None

    return {"meta": meta, "cover": cover, "rtl": rtl, "chapters": chapters,
            "pages": pages if image_book else None}


def render_chapter(raw: bytes, href: str, spine_index: dict, res_url, img_size) -> str:
    """Return a sanitised HTML fragment for one spine document."""
    soup = BeautifulSoup(raw, "html.parser")
    body = soup.body or soup
    for tag in body.find_all(DROP):
        tag.decompose()
    for t in body.find_all(True):
        for a in list(t.attrs):
            al = a.lower()
            if al.startswith("on") or al in ("style", "xmlns", "xml:lang"):
                del t.attrs[a]
        if t.name == "img":
            src = t.get("src", "")
            if src and not src.startswith(("http:", "https:", "data:")):
                path = resolve(href, src)
                t["src"] = res_url(path)
                size = img_size(path)
                if size:
                    t["width"], t["height"] = str(size[0]), str(size[1])
            t["loading"] = "lazy"
            t["decoding"] = "async"
        elif t.name == "image":
            for attr in ("xlink:href", "href"):
                v = t.get(attr)
                if v and not v.startswith(("http:", "https:", "data:")):
                    t[attr] = res_url(resolve(href, v))
        elif t.name == "a" and t.get("href"):
            h = t["href"]
            if h.startswith(("http://", "https://", "mailto:")):
                t["target"], t["rel"] = "_blank", "noopener noreferrer"
            else:
                parts = urlsplit(h)
                target = resolve(href, parts.path) if parts.path else href
                idx = spine_index.get(target)
                t["href"] = "#"
                if idx is not None:
                    t["data-ch"] = str(idx)
                if parts.fragment:
                    t["data-anchor"] = parts.fragment
    return "".join(str(c) for c in body.contents).strip()
