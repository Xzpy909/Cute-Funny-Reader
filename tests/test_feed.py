"""/api/library?since=… only sends what changed since the browser last asked."""
import importlib
import secrets

from fastapi.testclient import TestClient

from conftest import jpeg, make_cbz


def test_library_feed(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    assert c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)}).status_code == 200
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    root = M.LIB_ROOT / l["path"]
    for s in ("Starfall", "Moonforge"):
        for i in (1, 2):
            make_cbz(root / s / f"{s} {i:02}.cbz", {"001.jpg": jpeg()})
    M.lib.scan()

    first = c.get("/api/library").json()
    assert first["full"] and len(first["books"]) == 4
    q = lambda r: f"/api/library?since={r['seq']}&epoch={r['epoch']}"

    same = c.get(q(first)).json()
    assert not same["full"] and same["books"] == [] and same["removed"] == [] and same["seq"] == first["seq"]

    starfall = next(b for b in first["books"] if b["series"] == "Starfall")
    assert c.patch(f"/api/series/{starfall['seriesId']}", json={"name": "Starfall Deluxe"}).status_code == 200
    after = c.get(q(first)).json()
    assert not after["full"] and after["removed"] == []
    assert sorted(b["series"] for b in after["books"]) == ["Starfall Deluxe", "Starfall Deluxe"]      # only the renamed set

    gone = next(b for b in first["books"] if b["series"] == "Moonforge")
    assert c.delete(f"/api/books/{gone['id']}").status_code == 200                      # → marked for the trash
    t = c.get(q(after)).json()
    assert t["removed"] == [] and [(b["id"], bool(b["trashed"])) for b in t["books"]] == [(gone["id"], True)]
    assert c.post("/api/trash/restore", json={"ids": [gone["id"]]}).json()["restored"] == 1
    assert [b["trashed"] for b in c.get(q(t)).json()["books"]] == [None]
    c.delete(f"/api/books/{gone['id']}")
    assert c.post("/api/trash/purge", json={"ids": [gone["id"]]}).json()["deleted"] == 1   # "Delete forever"
    d = c.get(q(after)).json()
    assert d["removed"] == [gone["id"]] and d["books"] == []
    assert c.get(q(first)).json()["removed"] == [gone["id"]]                                  # an older tab catches up too

    c.put(f"/api/progress/{starfall['id']}", json={"page": 0, "frac": .5})                       # progress isn't library data
    assert c.get(q(d)).json()["books"] == []

    assert c.get(f"/api/library?since={d['seq']}&epoch=someoneelse").json()["full"]           # server restarted
    assert c.get(f"/api/library?since={d['seq'] + 50}&epoch={d['epoch']}").json()["full"]     # nonsense number
