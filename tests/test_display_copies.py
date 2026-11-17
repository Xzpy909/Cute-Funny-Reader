"""Screen-sized page copies: big photos shrink to the screen, everything else is served as the original."""
import io

from PIL import Image

from app import library as L
from conftest import jpeg, make_cbz


def _png(w, h):
    buf = io.BytesIO(); Image.new("RGB", (w, h), "blue").save(buf, "PNG"); return buf.getvalue()


def _gif(w, h):
    buf = io.BytesIO(); Image.new("P", (w, h)).save(buf, "GIF"); return buf.getvalue()


def _setup(lib, pages, ltype="cosplay"):
    make_cbz(L.LIB_ROOT / "Lib" / "Set.cbz", pages)
    lib.create_library("Lib", "Lib", False, "#fff", ltype); lib.scan()
    b = next(iter(lib.books.values())); lib.dims(b)
    return b


def test_big_photo_is_scaled_to_the_screen(lib):
    b = _setup(lib, {"01.jpg": jpeg(5760, 8640)})
    data, mime = lib.display_page(b, 0, 2560)
    with Image.open(io.BytesIO(data)) as im:
        assert mime == "image/jpeg" and max(im.size) == 2560 and im.size == (1707, 2560)


def test_copy_is_cached(lib):
    b = _setup(lib, {"01.jpg": jpeg(5760, 8640)})
    first = lib.display_page(b, 0, 2560)
    assert list((L.CONFIG_DIR / "cache" / "pages").iterdir())
    assert lib.display_page(b, 0, 2560) == first


def test_sideways_phone_photo_copy_is_upright(lib):
    b = _setup(lib, {"01.jpg": jpeg(6000, 4000, orientation=6)})      # stored landscape, shown portrait
    data, _ = lib.display_page(b, 0, 1920)
    with Image.open(io.BytesIO(data)) as im:
        assert im.size == (1280, 1920)


def test_small_lossless_and_animated_pages_stay_original(lib):
    b = _setup(lib, {"01.jpg": jpeg(1200, 1800), "02.png": _png(6000, 9000), "03.gif": _gif(4000, 6000)})
    assert lib.display_page(b, 0, 2560) is None      # already about screen size
    assert lib.display_page(b, 1, 2560) is None      # RAW / lossless stays lossless
    assert lib.display_page(b, 2, 2560) is None      # GIFs may be animated


def test_odd_sizes_snap_to_a_few_cache_sizes(lib):
    b = _setup(lib, {"01.jpg": jpeg(5760, 8640)})
    data, _ = lib.display_page(b, 0, 2380)            # e.g. a phone: 915 px × 2.6
    with Image.open(io.BytesIO(data)) as im:
        assert max(im.size) == 2560


def test_cache_sweep_removes_copies_of_deleted_books(lib):
    b = _setup(lib, {"01.jpg": jpeg(5760, 8640)})
    lib.display_page(b, 0, 2560)
    (L.LIB_ROOT / "Lib" / "Set.cbz").unlink()
    lib.CACHE_GRACE = 0; lib.scan(deep=True)     # the clean-up runs on deep scans (and every 10 minutes)
    assert not list((L.CONFIG_DIR / "cache" / "pages").iterdir())


def test_long_strips_are_never_squeezed_into_the_screen(lib):
    # a webtoon page: read at full width and scrolled — its length has nothing to do with the screen
    b = _setup(lib, {"01.jpg": jpeg(800, 20000), "02.jpg": jpeg(4000, 30000)}, "comics")
    assert lib.display_page(b, 0, 2560) is None                # narrower than the screen: the original
    data, _ = lib.display_page(b, 1, 1920)                     # wider than the screen: only its width is fitted
    with Image.open(io.BytesIO(data)) as im:
        assert im.size == (1920, 14400)
    b.pop("dims")                                              # not measured yet: decided from the file itself
    assert lib.display_page(b, 0, 1280) is None


def test_a_cover_that_is_only_a_small_copy_of_page_one_is_not_a_page(lib):
    # downloaders add cover.webp = shrunken first page; for a strip it's a blurry sliver shown as page 1
    make_cbz(L.LIB_ROOT / "Lib" / "Toon" / "Ch.0000.cbz", {"cover.jpg": jpeg(99, 1600), "1.jpg": jpeg(720, 11521)})
    make_cbz(L.LIB_ROOT / "Lib" / "Toon" / "Ch.0001.cbz", {"cover.jpg": jpeg(1120, 1600), "01.jpg": jpeg(1400, 2000), "02.jpg": jpeg(720, 5070)})
    make_cbz(L.LIB_ROOT / "Lib" / "Real" / "Vol 1.cbz", {"cover.jpg": jpeg(1000, 1500, "blue"), "01.jpg": jpeg(1400, 2000)})   # other shape
    make_cbz(L.LIB_ROOT / "Lib" / "Same" / "Vol 1.cbz", {"cover.jpg": jpeg(1400, 2000, "blue"), "01.jpg": jpeg(1400, 2000)})   # full size
    lib.create_library("Lib", "Lib", False, "#fff", "comics"); lib.scan()
    pages = {b["rel"].split("/", 1)[1]: b["entries"] for b in lib.books.values()}
    assert pages["Toon/Ch.0000.cbz"] == ["1.jpg"]
    assert pages["Toon/Ch.0001.cbz"] == ["01.jpg", "02.jpg"]
    assert pages["Real/Vol 1.cbz"] == ["cover.jpg", "01.jpg"]
    assert pages["Same/Vol 1.cbz"] == ["cover.jpg", "01.jpg"]
