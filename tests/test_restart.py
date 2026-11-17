"""After a restart, nothing has to be re-read from disk for the library page — and the first scan only
checks folders, it doesn't list them again."""
import os
import time

from app import library as L
from conftest import jpeg, make_cbz


def test_restart_needs_no_folder_listing(lib, monkeypatch):
    lib.RACY_NS = 0
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    for s in ("Starfall", "Moonforge"):
        make_cbz(root / s / f"{s} 01.cbz", {"001.jpg": jpeg()})
    (root / "Inkwell").mkdir(); (root / "Inkwell" / L.COL_MARK).touch()
    make_cbz(root / "Inkwell" / "Paper Kites" / "Paper Kites 01.cbz", {"001.jpg": jpeg()})
    (root / "Empty One").mkdir(); (root / "Inkwell" / "Empty Two").mkdir()
    (root / "Notes Only").mkdir(); (root / "Notes Only" / "readme.txt").write_text("x")
    time.sleep(0.03)
    lib.scan()
    cols, empty = lib.folder_info()
    assert [c["name"] for c in cols] == ["Inkwell"]
    assert sorted((e["series"], e["collection"]) for e in empty) == [("Empty One", None), ("Empty Two", "Inkwell"), ("Notes Only", None)]
    assert (cols, empty) == (lib._collections_from_disk(), lib._empty_series_from_disk())   # same answer as asking the disk
    books = dict(lib.books)

    calls = {"n": 0}
    real_scandir = os.scandir

    def counting(path=".", *a, **k):                           # listings inside the library (not /config's cache)
        if str(path).startswith(str(root)):
            calls["n"] += 1
        return real_scandir(path, *a, **k)
    monkeypatch.setattr(os, "scandir", counting)
    again = L.Library()                                        # "restart": a new Library on the same config
    again.RACY_NS = 0
    assert again.folder_info() == (cols, empty)                # straight from the saved index
    assert calls["n"] == 0
    again.scan()                                               # first scan after the restart
    assert calls["n"] == 0                                     # folders were only checked, not listed again
    assert {b["rel"] for b in again.books.values()} == {b["rel"] for b in books.values()}
    assert again.folder_info() == (cols, empty)

    make_cbz(root / "Empty One" / "Empty One 01.cbz", {"001.jpg": jpeg()})     # changed while running: picked up
    again.scan()
    assert "Empty One" not in [e["series"] for e in again.folder_info()[1]]
    assert len(again.books) == 4


def test_marking_an_empty_folder_as_collection_is_noticed(lib):
    lib.RACY_NS = 0
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    (root / "Shelf").mkdir()
    lib.scan()
    assert [e["series"] for e in lib.folder_info()[1]] == ["Shelf"]
    time.sleep(0.03); (root / "Shelf" / L.COL_MARK).touch()
    lib.scan()
    assert [c["name"] for c in lib.folder_info()[0]] == ["Shelf"] and lib.folder_info()[1] == []


def test_folder_suggestions_dont_walk_existing_libraries(lib, monkeypatch):
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    base = l["path"].split("/")[0] if "/" in l["path"] else ""
    free = (L.LIB_ROOT / base / "Loose Folder"); free.mkdir(parents=True)
    make_cbz(free / "a.cbz", {"001.jpg": jpeg()})
    walked = []
    real = os.walk
    monkeypatch.setattr(os, "walk", lambda top, *a, **k: (walked.append(str(top)), real(top, *a, **k))[1])
    out = {f["path"]: f for f in lib.folders(base)}
    assert out["Loose Folder"]["books"] == 1 and not out["Loose Folder"]["used"]
    assert out[root.name]["used"] and str(root) not in walked            # the existing library wasn't walked
