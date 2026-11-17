"""Shared test setup: every test gets its own empty library + config folder, so nothing touches real data."""
import io
import zipfile

import pytest
from PIL import Image

from app import library as L


@pytest.fixture
def lib(tmp_path, monkeypatch):
    data, config = tmp_path / "data", tmp_path / "config"
    data.mkdir(); config.mkdir()
    monkeypatch.setattr(L, "LIB_ROOT", data)
    monkeypatch.setattr(L, "CONFIG_DIR", config)
    return L.Library()


def jpeg(w=60, h=90, color="red", orientation=None) -> bytes:
    """A small JPEG; `orientation` adds an EXIF rotate-me tag like phone cameras write."""
    buf = io.BytesIO()
    im = Image.new("RGB", (w, h), color)
    if orientation:
        exif = Image.Exif(); exif[0x0112] = orientation
        im.save(buf, "JPEG", exif=exif.tobytes())
    else:
        im.save(buf, "JPEG")
    return buf.getvalue()


def make_cbz(path, pages: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in pages.items():
            z.writestr(name, data)
