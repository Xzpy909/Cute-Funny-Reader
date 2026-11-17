"""An EPUB can be opened and its text read (regression: a new attribute once hid Library.names)."""
import zipfile

from app import library as L

CONTAINER = """<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
OPF = """<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test Novel</dc:title><dc:identifier id="id">x</dc:identifier></metadata>
<manifest><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>"""
CH1 = """<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body><h1>Chapter One</h1><p>Hello from the first chapter.</p></body></html>"""


def test_epub_chapter_opens(lib):
    l = lib.create_library("Novels", "Novels", False, "#fff", "comics")
    path = L.LIB_ROOT / l["path"] / "Test Novel" / "Test Novel v01.epub"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", OPF)
        z.writestr("OEBPS/ch1.xhtml", CH1)
    lib.scan()
    b = next(iter(lib.books.values()))
    assert b["format"] == "epub"
    out = lib.chapter(b, 0)
    assert "Hello from the first chapter." in out["html"]
