"""The naming baseline (docs/NAMING.md): file names the reader must always understand.
Cases marked xfail are part of the baseline but not handled yet — fixing the parser turns them into failures
of the xfail itself (strict), so the mark has to come off and the case stays guarded from then on."""
import importlib
import io
import secrets
import zipfile

import pytest
from fastapi.testclient import TestClient

from conftest import jpeg

GAP = pytest.mark.xfail(strict=True, reason="baseline not handled yet")


# ---- Cosplay: [Photographer / Publisher] Cosplayer - Set - Variant.zip -------------------------------------

@pytest.mark.parametrize("name, circle, cosplayer, set_", [
    ("[Lumen Studio] Mirelle - Starfall Bunny", "Lumen Studio", "Mirelle", "Starfall Bunny"),
    ("Mirelle - Starfall Bunny", "", "Mirelle", "Starfall Bunny"),
])
def test_cosplay_without_variant(name, circle, cosplayer, set_, lib, tmp_path):
    from app import library as L
    assert L.cosplay_name(name) == {"circle": circle, "cosplayer": cosplayer, "work": set_}
    assert L.cosplay_plan(L.LIB_ROOT, [name])[name] == {"cosplayer": cosplayer, "set": set_}


@pytest.mark.parametrize("name, circle", [
    pytest.param("[Lumen Studio] Mirelle - Starfall Bunny - Bonus", "Lumen Studio", marks=GAP),
    pytest.param("Mirelle - Starfall Bunny - Bonus", "", marks=GAP),
])
def test_cosplay_with_variant(name, circle, lib):
    """` - Variant` at the end: the set is what comes before it — never "Starfall Bunny -"."""
    from app import library as L
    assert L.cosplay_name(name)["circle"] == circle
    assert L.cosplay_plan(L.LIB_ROOT, [name])[name] == {"cosplayer": "Mirelle", "set": "Starfall Bunny"}


# ---- Manga: (Event) [Circle (Author)] Series - Ch. XX [Language].cbz ---------------------------------------

def _scan(tmp_path, monkeypatch, name):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)})
    l = c.post("/api/libraries", json={"name": "Manga", "type": "manga", "color": "#fff"}).json()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("001.jpg", jpeg())
    folder = tmp_path / "data" / l["path"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(buf.getvalue())
    M.lib.scan()
    (b,) = M.lib.books.values()
    return b


@pytest.mark.parametrize("name, number, author, publisher", [
    ("(C105) [Moonforge (Mirelle)] Starfall Academy - Ch. 03 [English].cbz", 3, "Mirelle", "Moonforge"),
    ("[Moonforge (Mirelle)] Starfall Academy - Ch. 01.cbz", 1, "Mirelle", "Moonforge"),
    pytest.param("[Mirelle] - Starfall Academy - Ch. 01.cbz", 1, "Mirelle", "", marks=GAP),
])
def test_manga(name, number, author, publisher, tmp_path, monkeypatch):
    b = _scan(tmp_path, monkeypatch, name)
    assert b["series"] == "Starfall Academy"
    assert b.get("number") == number and b.get("kind") == "chapter"
    assert (b.get("author") or "") == author
    assert (b.get("publisher") or "") == publisher
