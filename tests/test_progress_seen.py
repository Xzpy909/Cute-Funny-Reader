"""Read → marked unread → it's unread, but never "new" again."""
import importlib
import secrets

from fastapi.testclient import TestClient

from conftest import jpeg, make_cbz


def test_seen_survives_later_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    assert c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)}).status_code == 200
    l = c.post("/api/libraries", json={"name": "Cos", "type": "cosplay", "color": "#fff"}).json()
    make_cbz(M.LIB_ROOT / l["path"] / "Set" / "a.cbz", {"001.jpg": jpeg(), "002.jpg": jpeg()})
    M.lib.scan()
    bid = next(iter(M.lib.books))

    c.put(f"/api/progress/{bid}", json={"seen": True, "done": True, "frac": 1})     # read it
    c.put(f"/api/progress/{bid}", json={"seen": True})                              # mark unread
    assert c.get("/api/progress").json()[bid] == {"seen": True}
    c.put(f"/api/progress/{bid}", json={"page": 0, "frac": 0.5})                     # an older tab saves without the note
    assert c.get("/api/progress").json()[bid]["seen"] is True
