"""A book keeps its id — and so its progress, edits and date added — when it moves or is renamed."""
import os
import shutil

from app import library as L
from conftest import jpeg, make_cbz


def comics(lib):
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    return L.LIB_ROOT / l["path"]


def by_file(lib, name):
    return next(b for b in lib.books.values() if b["file"] == name)


def test_first_start_keeps_todays_ids(lib):
    root = comics(lib)
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    lib.scan()
    b = by_file(lib, "Starfall 01.cbz")
    assert b["id"] == L.make_id(b["rel"])                     # same id the old version gave it


def test_moved_in_explorer_keeps_id_progress_and_date(lib):
    root = comics(lib)
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    lib.scan()
    b = by_file(lib, "Starfall 01.cbz"); bid, added = b["id"], b["added"]
    lib.progress.put(bid, {"page": 0, "frac": .5, "seen": True})
    (root / "Starfall Deluxe").mkdir()
    shutil.move(str(root / "Starfall" / "Starfall 01.cbz"), str(root / "Starfall Deluxe" / "Starfall 01.cbz"))   # not via the app
    lib.scan()
    b = by_file(lib, "Starfall 01.cbz")
    assert b["series"] == "Starfall Deluxe"
    assert (b["id"], b["added"]) == (bid, added)
    assert lib.progress.get(bid)["frac"] == .5


def test_renamed_in_explorer_keeps_id(lib):
    root = comics(lib)
    make_cbz(root / "Starfall" / "starfall_1.cbz", {"001.jpg": jpeg()})
    lib.scan(); bid = by_file(lib, "starfall_1.cbz")["id"]
    os.rename(root / "Starfall" / "starfall_1.cbz", root / "Starfall" / "Starfall 01.cbz")
    lib.scan()
    assert by_file(lib, "Starfall 01.cbz")["id"] == bid


def test_moved_by_the_app_keeps_id(lib):
    root = comics(lib)
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    lib.scan(); b = by_file(lib, "Starfall 01.cbz"); bid = b["id"]
    lib.rename_series(b["seriesId"], "Starfall Vol 1")
    assert by_file(lib, "Starfall 01.cbz")["id"] == bid


def test_a_new_file_at_an_old_path_is_a_new_book(lib):
    root = comics(lib)
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    lib.scan(); old = by_file(lib, "Starfall 01.cbz")["id"]
    (root / "Old").mkdir()
    shutil.move(str(root / "Starfall" / "Starfall 01.cbz"), str(root / "Old" / "Starfall 01.cbz"))
    lib.scan()
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg(color="blue"), "002.jpg": jpeg()})   # different file, old path
    lib.scan()
    ids = {b["rel"].split("/", 1)[1]: b["id"] for b in lib.books.values()}
    assert ids["Old/Starfall 01.cbz"] == old
    assert ids["Starfall/Starfall 01.cbz"] != old


def test_a_briefly_missing_folder_comes_back_with_its_ids(lib):
    root = comics(lib)
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    lib.scan(); bid = by_file(lib, "Starfall 01.cbz")["id"]
    os.rename(root / "Starfall", root.parent / "Starfall-away")       # e.g. a drive that wasn't mounted yet
    lib.scan()
    assert not lib.books
    os.rename(root.parent / "Starfall-away", root / "Starfall")
    lib.scan()
    assert by_file(lib, "Starfall 01.cbz")["id"] == bid


def test_deleting_forgets_the_book(lib):
    root = comics(lib)
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    lib.scan(); b = by_file(lib, "Starfall 01.cbz")
    lib.progress.put(b["id"], {"page": 1})
    lib.delete_books([b])
    assert lib.progress.get(b["id"]) is None
    assert b["rel"] not in lib.ids.rows()
