"""What a drop becomes is planned on the server (app/uploadplan.py). upload_plan_golden.json holds 23 drops —
comics and Cosplay, with metadata files, numbered folders, collections, videos — and the plans the browser's own
planner made for them before planning moved here: the server must keep making exactly those."""
import importlib
import json
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

GOLDEN = json.loads((Path(__file__).parent / "upload_plan_golden.json").read_text("utf-8"))


@pytest.mark.parametrize("case", GOLDEN, ids=[c["drop"] for c in GOLDEN])
def test_same_plan_as_before(case, lib):
    from app import uploadplan as U, library as L
    kind = "cosplay" if case.get("cosplay") else "comics"
    got = U.plan({"type": kind, "path": ""}, case["items"], case.get("meta"), case.get("series"), case.get("collection"), "2026-01-01")
    assert [{k: v for k, v in j.items() if k != "size"} for j in got] == case["plan"]


def test_chapter_numbers_follow_the_server_rules():
    """The browser's copy of the number parser is gone: "Name Ch.1" folders are read like file names are."""
    from app import uploadplan as U
    assert U.stem("Starfall Ch.1", is_file=False) == (1.0, "Starfall")
    assert U.stem("Starfall Ch.1.cbz") == (1.0, "Starfall")
    assert U.stem("[Moonforge (Mirelle)] Starfall - Ch. 03 [English].cbz")[0] == 3.0


def test_the_plan_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "d")); monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "d").mkdir(); (tmp_path / "c").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)})
    l = c.post("/api/libraries", json={"name": "Cos", "type": "cosplay", "color": "#fff"}).json()
    r = c.post(f"/api/libraries/{l['id']}/plan", json={
        "items": [{"path": "[Lumen Studio] Mirelle - Starfall Bunny - Bonus/001.jpg", "size": 10},
                  {"path": "[Lumen Studio] Mirelle - Starfall Bunny - Bonus/002.mov", "size": 20}], "today": "2026-01-01"})
    assert r.status_code == 200
    assert r.json()["jobs"] == [{"kind": "pack", "name": "[Lumen Studio] Mirelle - Starfall Bunny - Bonus.zip", "images": [0, 1],
                                 "extras": [], "size": 30, "collection": "Mirelle", "folder": "Starfall Bunny"}]
    assert c.post("/api/libraries/nope/plan", json={"items": []}).status_code == 404
    assert c.post(f"/api/libraries/{l['id']}/plan", json={"items": [], "series": "nope"}).status_code == 404
