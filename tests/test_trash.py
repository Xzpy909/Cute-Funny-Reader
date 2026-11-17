"""Deleting moves things to the trash: marked first (instant, undoable), moved out after a delay, deleted
for good much later — and restorable with reading progress until then."""
import time

from app import library as L
from conftest import jpeg, make_cbz


def shelf(lib):
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    for i in (1, 2):
        make_cbz(root / "Starfall" / f"Starfall {i:02}.cbz", {"001.jpg": jpeg()})
    make_cbz(root / "Moonforge" / "Moonforge 01.cbz", {"001.jpg": jpeg()})
    lib.scan()
    return l, root


def book(lib, name):
    return next(b for b in lib.books.values() if b["file"] == name)


def test_marking_is_instant_and_undoable(lib):
    _, root = shelf(lib)
    b = book(lib, "Starfall 01.cbz")
    lib.trash_books([b])
    assert lib.trash.get(b["id"]) and (root / "Starfall" / "Starfall 01.cbz").exists()      # nothing moved yet
    assert not lib.trash_tick()                                                    # not due yet
    lib.untrash([b["id"]])
    assert lib.trash.get(b["id"]) is None and not lib.trash_tick(time.time() + 10 ** 6)


def test_due_items_move_to_the_trash_folder_and_come_back_with_progress(lib):
    _, root = shelf(lib)
    b = book(lib, "Moonforge 01.cbz"); bid = b["id"]
    lib.progress.put(bid, {"page": 0, "frac": .5, "seen": True})
    lib.trash_books([b])
    assert lib.trash_tick(time.time() + L.TRASH_DELAY + 1)                         # the worker moves it
    lib.scan()
    assert bid not in lib.books and not (root / "Moonforge").exists()               # gone, its folder too
    (item,) = lib.bin_items(None)
    assert item["series"] == "Moonforge" and item["daysLeft"] >= 29
    assert (L.LIB_ROOT / L.TRASH_DIR / item["tid"] / "Moonforge 01.cbz").exists()
    assert lib.bin_cover(item["tid"])                                               # a cover for the trash list
    assert lib.progress.get(bid)                                                    # kept while it's in the trash

    assert lib.restore_bin([item["tid"]]) == 1
    back = book(lib, "Moonforge 01.cbz")
    assert back["id"] == bid and back["series"] == "Moonforge"
    assert lib.progress.get(bid)["frac"] == .5 and lib.bin_items(None) == []
    assert not (L.LIB_ROOT / L.TRASH_DIR / item["tid"]).exists()


def test_trash_is_emptied_after_the_keep_time_or_by_hand(lib):
    shelf(lib)
    a, b = book(lib, "Starfall 01.cbz"), book(lib, "Starfall 02.cbz")
    lib.progress.put(a["id"], {"page": 0})
    lib.trash_books([a, b])
    lib.trash_tick(time.time() + L.TRASH_DELAY + 1); lib.scan()
    items = lib.bin_items(None)
    assert len(items) == 2
    first = next(i for i in items if i["id"] == a["id"])
    assert lib.purge_bin([first["tid"]]) == 1                                       # "Delete forever"
    assert lib.progress.get(a["id"]) is None and len(lib.bin_items(None)) == 1
    lib.trash_tick(time.time() + L.TRASH_KEEP + 3600)                               # a month later
    assert lib.bin_items(None) == [] and not any((L.LIB_ROOT / L.TRASH_DIR).iterdir())


def test_trashing_a_collection_takes_its_folder_along(lib):
    l = lib.create_library("Cos", "Cos", False, "#fff", "cosplay")
    root = L.LIB_ROOT / l["path"]
    for n in ("Maid", "Beach"):
        make_cbz(root / "Mirelle" / n / f"{n}.cbz", {"001.jpg": jpeg()})
    (root / "Mirelle" / L.COL_MARK).touch()
    lib.scan()
    cid = lib.collections()[0]["id"]
    lib.delete_collection(cid)
    assert len(lib.trash.all()) == 2 and (root / "Mirelle").exists()                  # marked, still there
    lib.trash_tick(time.time() + L.TRASH_DELAY + 1); lib.scan()
    assert not (root / "Mirelle").exists() and lib.collections() == []                # the emptied collection went too
    assert len(lib.bin_items(None)) == 2


def test_empty_folders_are_removed_after_a_while(lib, monkeypatch):
    lib.RACY_NS = 0
    _, root = shelf(lib)
    (root / "Old Empty" / "Inner").mkdir(parents=True)
    (root / "Old Shelf").mkdir(); (root / "Old Shelf" / L.COL_MARK).touch(); (root / "Old Shelf" / "Thumbs.db").write_text("x")
    (root / "Notes").mkdir(); (root / "Notes" / "readme.txt").write_text("keep me")
    time.sleep(0.03); lib.scan(deep=True)
    assert (root / "Old Empty").exists()                                            # too fresh to remove
    monkeypatch.setattr(L, "EMPTY_FOLDER_AFTER", 0)
    lib.scan(deep=True)
    assert not (root / "Old Empty").exists() and not (root / "Old Shelf").exists()
    assert (root / "Notes" / "readme.txt").exists() and (root / "Starfall").exists() and root.exists()
    assert lib.folder_info() == ([], [{**e} for e in lib.folder_info()[1] if e["series"] == "Notes"])
