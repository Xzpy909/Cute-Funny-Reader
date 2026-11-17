"""Dropped photo folders are packed on the server: the browser sends the files one by one into a staging
folder, the server builds the .zip / .cbz (ZIP64 when needed) and stores it like any upload."""
import importlib
import os
import secrets
import time
import zipfile

from fastapi.testclient import TestClient

from conftest import jpeg


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    assert c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)}).status_code == 200
    return M, c


def _pack(c, lid, files: dict, **place):
    pid = c.post(f"/api/libraries/{lid}/packs").json()["id"]
    for name, data in files.items():
        assert c.put(f"/api/packs/{pid}/files", params={"name": name}, content=data).status_code == 200
    return pid, c.post(f"/api/packs/{pid}/finish", params=place)


def test_cosplay_folder_becomes_a_zip_in_page_order(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Cos", "type": "cosplay", "color": "#fff"}).json()
    pid, r = _pack(c, l["id"], {"002.jpg": jpeg(color="blue"), "001.jpg": jpeg(), "003.mov": b"\0" * 2048,
                                "metadata.json": b'{"title": "Starfall Bunny"}'},
                   name="Starfall Bunny.zip", collection="Mirelle", folder="Starfall Bunny", batch="d1")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["path"].endswith("Mirelle/Starfall Bunny/Starfall Bunny.zip") and not d["skipped"]
    with zipfile.ZipFile(tmp_path / "data" / d["path"]) as z:
        assert z.namelist() == ["001.jpg", "002.jpg", "003.mov", "metadata.json"]
        assert z.testzip() is None
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
    assert not (tmp_path / "config" / "cache" / "packs" / pid).exists()      # staging folder cleaned up
    M.lib.scan()
    (b,) = M.lib.books.values()
    assert b["pages"] >= 2


def test_same_folder_again_is_already_there(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    pages = {"001.jpg": jpeg(), "002.jpg": jpeg(color="blue")}
    assert not _pack(c, l["id"], pages, name="Starfall 01.cbz")[1].json()["skipped"]
    again = _pack(c, l["id"], pages, name="Starfall 01.cbz")[1].json()
    assert again["skipped"] and again["path"].endswith("Starfall 01.cbz")
    other = _pack(c, l["id"], {"001.jpg": jpeg(color="green")}, name="Starfall 01.cbz")[1].json()
    assert not other["skipped"] and other["path"].endswith("Starfall 01 (2).cbz")   # different content: both kept


def test_only_media_and_metadata_are_accepted(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Cos", "type": "cosplay", "color": "#fff"}).json()
    pid = c.post(f"/api/libraries/{l['id']}/packs").json()["id"]
    for bad in ("pack.json", "run.sh", "../../evil.jpg.exe"):
        assert c.put(f"/api/packs/{pid}/files", params={"name": bad}, content=b"x").status_code == 400
    c.put(f"/api/packs/{pid}/files", params={"name": "../001.jpg"}, content=jpeg())     # path parts are dropped
    assert (tmp_path / "config" / "cache" / "packs" / pid / "001.jpg").exists()
    assert c.post(f"/api/packs/nothex/finish", params={"name": "x.zip"}).status_code == 404


def test_empty_pack_is_refused_and_logged(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Cos", "type": "cosplay", "color": "#fff"}).json()
    pid, r = _pack(c, l["id"], {"metadata.json": b"{}"}, name="Empty.zip")
    assert r.status_code == 400


def test_failed_pack_is_in_the_upload_log(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    pid, r = _pack(c, l["id"], {"001.jpg": jpeg()}, name="Starfall.cbz", series="no-such-series", batch="b2")
    assert r.status_code == 404
    c.post("/api/uploads/b2/done", json={"lib": l["id"]})
    text = next((tmp_path / "config" / "logs").glob("*.log")).read_text("utf-8")
    assert "✗ Starfall.cbz: series not found" in text


def test_another_account_cant_use_a_pack_and_old_ones_are_swept(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Cos", "type": "cosplay", "color": "#fff"}).json()
    pid = c.post(f"/api/libraries/{l['id']}/packs").json()["id"]
    d = tmp_path / "config" / "cache" / "packs" / pid
    meta = d / "pack.json"
    import json
    m = json.loads(meta.read_text()); m["owner"] = "someone-else"; meta.write_text(json.dumps(m))
    assert c.put(f"/api/packs/{pid}/files", params={"name": "001.jpg"}, content=jpeg()).status_code == 404
    old = time.time() - 2 * 86400
    os.utime(d, (old, old))
    c.post(f"/api/libraries/{l['id']}/packs")                                 # starting a new pack sweeps
    assert not d.exists()
