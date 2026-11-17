"""A scan only re-reads folders whose modification time changed; everything else is replayed from memory."""
import os
import time

import pytest

from app import library as L
from conftest import jpeg, make_cbz


@pytest.fixture
def shelf(lib, monkeypatch):
    lib.RACY_NS = 0                                    # tests don't wait out the "changed just now" guard
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    for s in ("Starfall", "Moonforge"):
        for i in (1, 2):
            make_cbz(root / s / f"{s} {i:02}.cbz", {"001.jpg": jpeg()})
    lib.scan()
    calls = {"scandir": 0, "stat": 0}
    real_scandir, real_stat = os.scandir, os.stat
    monkeypatch.setattr(os, "scandir", lambda *a, **k: (calls.__setitem__("scandir", calls["scandir"] + 1), real_scandir(*a, **k))[1])
    monkeypatch.setattr(os, "stat", lambda *a, **k: (calls.__setitem__("stat", calls["stat"] + 1), real_stat(*a, **k))[1])
    return lib, root, calls


def tick():
    time.sleep(0.03)                                   # so the folder's modification time really differs


def test_unchanged_rescan_lists_nothing(shelf):
    lib, root, calls = shelf
    before = dict(lib.books)
    calls.update(scandir=0, stat=0)
    lib.scan()
    assert calls["scandir"] <= 1                       # (only the accounts' top folder, for new libraries)
    assert lib.books == before
    assert not lib.changed_on_disk()


def test_only_the_changed_folder_is_listed(shelf):
    lib, root, calls = shelf
    tick(); make_cbz(root / "Starfall" / "Starfall 03.cbz", {"001.jpg": jpeg()})      # dropped in with Explorer
    assert lib.changed_on_disk()
    calls.update(scandir=0, stat=0)
    lib.scan()
    assert calls["scandir"] <= 2                       # Starfall — not Moonforge
    assert sorted(b["file"] for b in lib.books.values() if b["series"] == "Starfall") == ["Starfall 01.cbz", "Starfall 02.cbz", "Starfall 03.cbz"]


def test_removed_and_renamed_outside_the_app(shelf):
    lib, root, _ = shelf
    tick(); os.remove(root / "Starfall" / "Starfall 02.cbz"); os.rename(root / "Moonforge", root / "Moonforge Deluxe")
    lib.scan()
    assert sorted((b["series"], b["file"]) for b in lib.books.values()) == [
        ("Moonforge Deluxe", "Moonforge 01.cbz"), ("Moonforge Deluxe", "Moonforge 02.cbz"), ("Starfall", "Starfall 01.cbz")]
    assert all(d.startswith(str(root)) and os.path.isdir(d) for d in lib._dircache)   # gone folders are forgotten


def test_file_rewritten_in_place_is_found_by_a_deep_scan(shelf):
    lib, root, _ = shelf
    f = root / "Starfall" / "Starfall 01.cbz"
    folder_time = os.stat(root / "Starfall").st_mtime_ns
    make_cbz(f, {"001.jpg": jpeg(), "002.jpg": jpeg(color="blue")})          # same name, new content
    os.utime(root / "Starfall", ns=(folder_time, folder_time))                    # …and the folder looks untouched
    lib.scan()
    assert next(b for b in lib.books.values() if b["file"] == "Starfall 01.cbz")["pages"] == 1
    lib.scan(deep=True)
    assert next(b for b in lib.books.values() if b["file"] == "Starfall 01.cbz")["pages"] == 2


def test_an_edit_made_in_the_app_is_re_read(shelf):
    lib, root, _ = shelf
    b = next(b for b in lib.books.values() if b["file"] == "Starfall 01.cbz")
    folder_time = os.stat(root / "Starfall").st_mtime_ns
    lib.write_metadata(b, {"tags": ["space opera"]})
    os.utime(root / "Starfall", ns=(folder_time, folder_time))                    # even if the folder's time didn't move
    lib.scan()
    assert "space opera" in next(b for b in lib.books.values() if b["file"] == "Starfall 01.cbz")["tags"]
