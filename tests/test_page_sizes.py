"""Page sizes (used to lay out the reader) must be right without reading whole pages."""
from conftest import jpeg, make_cbz


def _book(lib, name):
    return next(b for b in lib.books.values() if b["file"] == name)


def test_sizes_from_archive(lib):
    make_cbz(lib_root(lib) / "Comics" / "Work.cbz",
             {"01.jpg": jpeg(600, 900), "02.jpg": jpeg(1200, 800), "03.mp4": b"\0" * 10})
    lib.create_library("Comics", "Comics", False, "#fff", "comics"); lib.scan()
    assert lib.dims(_book(lib, "Work.cbz")) == [[600, 900], [1200, 800], [1920, 1080]]


def test_sizes_from_photo_folder(lib):
    d = lib_root(lib) / "Cos" / "Coll" / "Set A"; d.mkdir(parents=True)
    (d / "01.jpg").write_bytes(jpeg(400, 600)); (d / "02.jpg").write_bytes(jpeg(800, 500))
    lib.create_library("Cos", "Cos", False, "#fff", "cosplay"); lib.scan()
    assert lib.dims(_book(lib, "Set A")) == [[400, 600], [800, 500]]


def test_sideways_phone_photo_is_measured_upright(lib):
    # stored 1200×800 with "rotate 90°" (6) → browsers show it 800 wide × 1200 tall
    make_cbz(lib_root(lib) / "Comics" / "Phone.cbz", {"01.jpg": jpeg(1200, 800, orientation=6), "02.jpg": jpeg(1200, 800)})
    lib.create_library("Comics", "Comics", False, "#fff", "comics"); lib.scan()
    assert lib.dims(_book(lib, "Phone.cbz")) == [[800, 1200], [1200, 800]]


def test_unreadable_page_gets_a_fallback(lib):
    make_cbz(lib_root(lib) / "Comics" / "Broken.cbz", {"01.jpg": jpeg(), "02.jpg": b"not an image"})
    lib.create_library("Comics", "Comics", False, "#fff", "comics"); lib.scan()
    assert lib.dims(_book(lib, "Broken.cbz"))[1] == [1000, 1500]


def lib_root(lib):
    from app import library as L
    return L.LIB_ROOT
