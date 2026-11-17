"""Collection cards: the two back covers come pre-drawn as one transparent picture."""
import io

from PIL import Image

from app import library as L
from conftest import jpeg, make_cbz


def test_stack_picture_is_drawn_once_and_cached(lib):
    l = lib.create_library("Cos", "Cos", False, "#fff", "cosplay")
    root = L.LIB_ROOT / l["path"]
    for n, color in (("Maid", "red"), ("Beach", "blue")):
        make_cbz(root / "Mirelle" / n / f"{n}.cbz", {"001.jpg": jpeg(400, 600, color)})
    (root / "Mirelle" / L.COL_MARK).touch()
    lib.scan()
    books = sorted(lib.books.values(), key=lambda b: b["file"])
    data = lib.stack_back(books)
    im = Image.open(io.BytesIO(data))
    W = lib.STACK_W
    assert im.format == "WEBP" and im.mode == "RGBA"
    assert im.size == (round(W * 1.4), round(W * 3 // 2 * 1.3))
    assert im.getpixel((2, 2))[3] == 0                         # corners see-through
    assert im.getpixel((im.width // 2, im.height // 2))[3] == 255   # covers in the middle
    assert lib.stack_back(books) == data                      # second time: from the cache
    assert len(list(lib.thumb_dir.glob("*-stack-*.webp"))) == 1
