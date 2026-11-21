"""The trash as its own page: one list of everything deleted (still being moved out, or already in .trash), with
size, days left and where it was; a keep time set in the app; restoring that copes with missing folders, taken
names and removed libraries; emptying that takes everything."""
import importlib
import secrets
import time

from fastapi.testclient import TestClient

from conftest import jpeg, make_cbz


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "d")); monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "d").mkdir(); (tmp_path / "c").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)})
    return M, c


def _shelf(M, c, tmp_path, name="Comics"):
    l = c.post("/api/libraries", json={"name": name, "type": "comics", "color": "#fff"}).json()
    root = tmp_path / "d" / l["path"]
    make_cbz(root / "Shelf" / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg()})        # in the collection "Shelf"
    (root / "Shelf" / ".collection").touch()
    make_cbz(root / "Moonforge" / "Moonforge 01.cbz", {"001.jpg": jpeg(), "002.jpg": jpeg()})
    M.lib.scan()
    return l, root


def _bin(M, b):                                             # what the trash worker does once the delay is over
    M.lib.trash_tick(time.time() + 10 ** 5)
    M.lib.scan()


def test_one_list_with_size_days_and_origin(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l, root = _shelf(M, c, tmp_path)
    star, moon = sorted(M.lib.books.values(), key=lambda b: b["series"], reverse=True)
    assert c.post("/api/books/delete", json={"ids": [star["id"]]}).status_code == 200
    _bin(M, star)                                           # Starfall: already in .trash
    c.post("/api/books/delete", json={"ids": [moon["id"]]})  # Moonforge: still being moved out
    d = c.get("/api/trash").json()
    assert [x["series"] for x in d["items"]] == ["Moonforge", "Starfall"]       # newest first
    assert [x["kind"] for x in d["items"]] == ["marked", "bin"]
    assert d["count"] == 2 and d["bytes"] == sum(x["size"] for x in d["items"]) > 0
    assert all(x["daysLeft"] == d["keepDays"] for x in d["items"]) and d["keepDays"] == 30
    assert d["items"][1]["collection"] == "Shelf" and d["items"][1]["libraryName"] == "Comics"
    assert c.get("/api/status").json()["trash"] == {"count": 2, "bytes": d["bytes"]}


def test_keep_time_is_an_app_setting(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l, root = _shelf(M, c, tmp_path)
    b = next(iter(M.lib.books.values()))
    c.post("/api/books/delete", json={"ids": [b["id"]]}); _bin(M, b)
    assert c.put("/api/trash/settings", json={"keepDays": 45}).status_code == 400
    assert c.put("/api/trash/settings", json={"keepDays": 0}).json() == {"keepDays": 0}        # until emptied
    assert c.get("/api/trash").json()["items"][0]["daysLeft"] is None
    M.lib.trash_tick(time.time() + 400 * 86400)
    assert c.get("/api/trash").json()["count"] == 1                                         # still there
    c.put("/api/trash/settings", json={"keepDays": 7})
    M.lib.trash_tick(time.time() + 8 * 86400)
    assert c.get("/api/trash").json()["count"] == 0                                         # gone after 7 days


def test_restore_recreates_folders_and_the_collection(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l, root = _shelf(M, c, tmp_path)
    star = next(b for b in M.lib.books.values() if b["series"] == "Starfall")
    c.post("/api/books/delete", json={"ids": [star["id"]]}); _bin(M, star)
    assert not (root / "Shelf").exists()                                                     # emptied → cleaned up
    tid = c.get("/api/trash").json()["items"][0]["tid"]
    assert c.post("/api/trash/restore", json={"bin": [tid]}).json()["restored"] == 1
    assert (root / "Shelf" / "Starfall" / "Starfall 01.cbz").exists()
    assert (root / "Shelf" / ".collection").exists()                                         # still a collection
    assert next(b for b in M.lib.books.values() if b["series"] == "Starfall")["collection"] == "Shelf"


def test_restore_when_the_library_is_gone(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l, root = _shelf(M, c, tmp_path)
    other = c.post("/api/libraries", json={"name": "Other", "type": "comics", "color": "#fff"}).json()
    star = next(b for b in M.lib.books.values() if b["series"] == "Starfall")
    c.post("/api/books/delete", json={"ids": [star["id"]]}); _bin(M, star)
    c.delete(f"/api/libraries/{l['id']}")
    item = c.get("/api/trash").json()["items"][0]
    assert item["libraryExists"] is False
    r = c.post("/api/trash/restore", json={"bin": [item["tid"]]})
    assert r.status_code == 409 and r.json()["needLibrary"] == [item["tid"]]
    r = c.post("/api/trash/restore", json={"bin": [item["tid"]], "into": other["id"]})
    assert r.json()["restored"] == 1
    assert (tmp_path / "d" / other["path"] / "Shelf" / "Starfall" / "Starfall 01.cbz").exists()


def test_empty_trash_takes_everything(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l, root = _shelf(M, c, tmp_path)
    star, moon = sorted(M.lib.books.values(), key=lambda b: b["series"], reverse=True)
    c.post("/api/books/delete", json={"ids": [star["id"]]}); _bin(M, star)
    c.post("/api/books/delete", json={"ids": [moon["id"]]})                 # still being moved out
    assert c.post("/api/trash/purge", json={"all": True}).json()["deleted"] == 2
    M.lib.scan()
    assert c.get("/api/trash").json()["count"] == 0 and not M.lib.books
    assert not (root / "Moonforge" / "Moonforge 01.cbz").exists()
