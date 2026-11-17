"""The library page's collections / empty series come from a cache that follows folder changes."""
import os

from app import library as L
from conftest import jpeg, make_cbz


def test_folder_info_is_cached_and_refreshed(lib):
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    make_cbz(root / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})
    lib.scan()
    cols, empty = lib.folder_info()
    assert cols == [] and empty == []
    assert lib.folder_info() is lib.folder_info()                       # served from the cache
    lib.create_series(l["id"], "Paper Kites")                           # made in the app
    assert [e["series"] for e in lib.folder_info()[1]] == ["Paper Kites"]
    (root / "Inkwell").mkdir(); (root / "Inkwell" / L.COL_MARK).touch()     # made in Explorer …
    lib.scan()                                                          # … seen at the next scan
    assert [c["name"] for c in lib.folder_info()[0]] == ["Inkwell"]
    os.rmdir(root / "Paper Kites"); lib.scan()
    assert lib.folder_info()[1] == []
