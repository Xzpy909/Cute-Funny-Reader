"""Big file operations as jobs: quick ones answer as before, long ones answer 202 with the job, which reports
real progress (files done / total, ETA, the current file) and can be cancelled between files."""
import importlib
import secrets
import shutil
import time

from fastapi.testclient import TestClient

from conftest import jpeg, make_cbz


def _app(tmp_path, monkeypatch, slow=0.0):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "d")); monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "d").mkdir(); (tmp_path / "c").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)})
    a = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    b = c.post("/api/libraries", json={"name": "Shelf", "type": "comics", "color": "#fff"}).json()
    for i in range(1, 5):
        make_cbz(tmp_path / "d" / a["path"] / "Starfall" / f"Starfall 0{i}.cbz", {"001.jpg": jpeg()})
    M.lib.scan()
    if slow:
        import app.libfiles as F
        real = shutil.move
        monkeypatch.setattr(F.shutil, "move", lambda *x: (time.sleep(slow), real(*x))[1])
    return M, c, a, b


def _follow(c, jid, timeout=20):
    end = time.time() + timeout
    seen = []
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        seen.append(j)
        if j["state"] in ("done", "failed", "cancelled"):
            return j, seen
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def test_quick_moves_answer_as_before(tmp_path, monkeypatch):
    M, c, a, b = _app(tmp_path, monkeypatch)
    ids = [x["id"] for x in M.lib.books.values()]
    assert c.post("/api/books/move", json={"ids": ids[:1], "library": b["id"]}).json() == {"ok": True}
    assert c.post("/api/books/move", json={"ids": ids[1:2], "newSeries": "  "}).status_code == 400   # errors too
    assert c.get("/api/jobs").json()["jobs"] == []                                             # nothing left behind


def test_a_long_move_is_a_job_with_progress(tmp_path, monkeypatch):
    M, c, a, b = _app(tmp_path, monkeypatch, slow=0.25)
    M.QUICK = 0.05
    M.jobs.start_workers({"user": 1})
    try:
        sid = next(iter(M.lib.books.values()))["seriesId"]
        r = c.post(f"/api/series/{sid}/move", json={"library": b["id"]})
        assert r.status_code == 202
        job = r.json()["job"]
        assert job["kind"] == "files" and job["title"] == "Moving Starfall" and job["total"] == 4 and job["unit"] == "files"
        done, seen = _follow(c, job["id"])
        assert done["state"] == "done" and done["done"] == 4
        assert any(0 < j["done"] < 4 and j["label"] and j["label"].startswith("Starfall") for j in seen)
        assert any(j["eta"] is not None for j in seen)
        assert {x["library"] for x in M.lib.books.values()} == {b["id"]}
        assert c.post(f"/api/jobs/{job['id']}/dismiss").json() == {"ok": True}
    finally:
        M.jobs.stop()


def test_cancel_stops_between_files(tmp_path, monkeypatch):
    M, c, a, b = _app(tmp_path, monkeypatch, slow=0.3)
    M.QUICK = 0.05
    M.jobs.start_workers({"user": 1})
    try:
        ids = sorted(M.lib.books, key=lambda i: M.lib.books[i]["file"])
        job = c.post("/api/books/move", json={"ids": ids, "library": b["id"]}).json()["job"]
        while c.get(f"/api/jobs/{job['id']}").json()["done"] < 1:
            time.sleep(0.02)
        assert c.post(f"/api/jobs/{job['id']}/cancel").json() == {"ok": True}
        done, _ = _follow(c, job["id"])
        assert done["state"] == "cancelled" and 1 <= done["done"] < 4
        moved = [x for x in M.lib.books.values() if x["library"] == b["id"]]
        assert 1 <= len(moved) < 4 and len(M.lib.books) == 4                # the library shows what's where
    finally:
        M.jobs.stop()
