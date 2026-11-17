"""Sets/series and collections keep their id through renames and moves — in the app or in Explorer."""
import os
import shutil

from app import library as L
from conftest import jpeg, make_cbz


def setup(lib):
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    make_cbz(root / "Starfall" / "Starfall 02.cbz", {"001.jpg": jpeg(color="blue")})
    make_cbz(root / "Moonforge" / "Moonforge 01.cbz", {"001.jpg": jpeg(color="green")})
    lib.scan()
    return l, root


def sid(lib, file):
    return next(b["seriesId"] for b in lib.books.values() if b["file"] == file)


def test_first_start_keeps_todays_ids(lib):
    l, _ = setup(lib)
    assert sid(lib, "Starfall 01.cbz") == L.series_key(l["id"], None, "Starfall")


def test_rename_in_the_app_keeps_the_id(lib):
    _, _ = setup(lib)
    s = sid(lib, "Starfall 01.cbz")
    assert lib.rename_series(s, "Starfall Deluxe") == s
    assert {b["series"] for b in lib.series_books(s)} == {"Starfall Deluxe"}


def test_rename_in_explorer_keeps_the_id(lib):
    _, root = setup(lib)
    s = sid(lib, "Starfall 01.cbz")
    os.rename(root / "Starfall", root / "Starfall (2012)")
    lib.scan()
    assert sid(lib, "Starfall 01.cbz") == s
    assert len(lib.series_books(s)) == 2


def test_collections_keep_ids_and_their_series_too(lib):
    l, root = setup(lib)
    s = sid(lib, "Starfall 01.cbz")
    c = lib.create_collection(l["id"], "Inkwell Press")["id"]
    lib.move_series(s, collection=c)
    assert sid(lib, "Starfall 01.cbz") == s                         # moved into a collection
    assert lib.rename_collection(c, "Inkwell") == c
    assert sid(lib, "Starfall 01.cbz") == s                         # its collection renamed
    assert next(b for b in lib.books.values() if b["file"] == "Starfall 01.cbz")["collectionId"] == c
    assert [x["id"] for x in lib.collections()] == [c]


def test_empty_series_rename_keeps_the_id(lib):
    l, _ = setup(lib)
    s = lib.create_series(l["id"], "Paper Kites")["seriesId"]
    assert lib.rename_series(s, "Paper Kites Deluxe") == s
    assert [e["seriesId"] for e in lib.empty_series() if e["series"] == "Paper Kites Deluxe"] == [s]


def test_merge_keeps_the_target_and_split_gets_a_new_id(lib):
    _, _ = setup(lib)
    starfall, mon = sid(lib, "Starfall 01.cbz"), sid(lib, "Moonforge 01.cbz")
    one = next(b["id"] for b in lib.books.values() if b["file"] == "Starfall 02.cbz")
    lib.move_books([one], new_series="Starfall Extras")              # split one book off
    assert sid(lib, "Starfall 01.cbz") == starfall
    assert sid(lib, "Starfall 02.cbz") not in (starfall, mon)
    lib.move_series(mon, into=starfall)                               # merge Moonforge into Starfall
    assert sid(lib, "Moonforge 01.cbz") == starfall


def test_a_new_series_with_an_old_name_is_a_new_series(lib):
    l, root = setup(lib)
    s = sid(lib, "Starfall 01.cbz")
    lib.rename_series(s, "Starfall Deluxe")
    make_cbz(root / "Starfall" / "Other 01.cbz", {"001.jpg": jpeg(color="white")})
    lib.scan()
    assert sid(lib, "Other 01.cbz") != s
    assert sid(lib, "Starfall 01.cbz") == s
