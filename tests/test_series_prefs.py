"""Per-series view settings (reading direction, layout, order, reader mode, fit) live per account on the server,
so they follow you from one device to the next."""
import importlib
import secrets

from fastapi.testclient import TestClient


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "d")); monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "d").mkdir(); (tmp_path / "c").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    pw = secrets.token_urlsafe(12)
    c = TestClient(M.app)
    assert c.post("/api/auth/setup", json={"email": "first@example.invalid", "password": pw}).status_code == 200
    return M, c, pw


def test_saved_and_read_back_and_only_known_settings(tmp_path, monkeypatch):
    M, c, _ = _app(tmp_path, monkeypatch)
    assert c.get("/api/prefs/series").json() == {}
    r = c.put("/api/prefs/series", json={"s1": {"rtl": True, "view": "cards", "sort": "desc", "mode": "webtoon", "fit": "width"},
                                         "s2": {"view": "list", "colour": "pink", "rtl": "yes", "fit": "x" * 50}})
    assert r.json() == {"s1": {"rtl": True, "view": "cards", "sort": "desc", "mode": "webtoon", "fit": "width"},
                        "s2": {"view": "list"}}                          # unknown keys / wrong types / long values dropped
    c.put("/api/prefs/series", json={"s2": {"sort": "asc"}})            # a series' settings are replaced as a whole
    c.put("/api/prefs/series", json={"s1": None})                       # null forgets
    assert c.get("/api/prefs/series").json() == {"s2": {"sort": "asc"}}


def test_another_device_sees_them_another_account_doesnt(tmp_path, monkeypatch):
    M, c, pw = _app(tmp_path, monkeypatch)
    c.put("/api/prefs/series", json={"s1": {"rtl": True}})
    phone = TestClient(M.app)                                           # the same account, signed in elsewhere
    phone.post("/api/auth/login", json={"email": "first@example.invalid", "password": pw})
    assert phone.get("/api/prefs/series").json() == {"s1": {"rtl": True}}
    pw2 = secrets.token_urlsafe(12)
    assert c.post("/api/accounts", json={"email": "second@example.invalid", "password": pw2}).status_code == 200
    other = TestClient(M.app)
    other.post("/api/auth/login", json={"email": "second@example.invalid", "password": pw2})
    assert other.get("/api/prefs/series").json() == {}
    assert TestClient(M.app).get("/api/prefs/series").status_code == 401  # signed out: nothing
