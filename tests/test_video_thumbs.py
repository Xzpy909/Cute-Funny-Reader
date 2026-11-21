"""Videos in a photo set get a real thumbnail in the reader's strip: a frame taken with ffmpeg, sized like a
page thumbnail and cached; without ffmpeg (or an unreadable clip) the strip keeps its ▶ tile."""
import io
import shutil
import subprocess

import pytest
from PIL import Image

from app import library as L
from conftest import jpeg

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def _clip(path):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=2", "-pix_fmt", "yuv420p",
                    str(path)], check=True)


def _set(lib):
    d = L.LIB_ROOT / "Cos" / "Mirelle" / "Garden"
    d.mkdir(parents=True)
    (d / "001.jpg").write_bytes(jpeg()); (d / "002.jpg").write_bytes(jpeg())
    _clip(d / "003.mp4")
    lib.create_library("Cos", "Cos", False, "#fff", "cosplay"); lib.scan()
    return next(iter(lib.books.values()))


def test_a_video_page_gets_a_frame_as_thumbnail(lib):
    b = _set(lib)
    n = b["entries"].index("003.mp4")
    data = lib.thumb(b, n, 200)
    with Image.open(io.BytesIO(data)) as im:
        assert im.format == "WEBP" and im.width <= 200
        r, g, bl = im.convert("RGB").getpixel((im.width // 2, im.height // 2))
        assert bl > 150 and r < 80                                # the clip's blue
    assert lib.thumb(b, n, 200) == data                           # cached


def test_without_ffmpeg_the_strip_keeps_its_tile(lib, monkeypatch):
    b = _set(lib)
    monkeypatch.setattr(type(lib), "FFMPEG", None)
    with pytest.raises(KeyError):
        lib.thumb(b, b["entries"].index("003.mp4"), 200)
