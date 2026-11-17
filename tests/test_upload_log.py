"""Upload log (config/logs/uploads-YYYY-MM.log): one short entry per drop — files that went in fine are only
counted, every failure is written out with its reason, and a damaged archive says what exactly is wrong."""
import importlib
import io
import secrets
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


def _cbz(damaged=False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("001.jpg", jpeg(400, 600)); z.writestr("002.jpg", jpeg())
    data = bytearray(buf.getvalue())
    if damaged:                                  # change a byte in the middle of the first page: same size, wrong checksum
        data[2000] ^= 0xFF
    return bytes(data)


def _log(tmp_path) -> str:
    logs = list((tmp_path / "config" / "logs").glob("uploads-*.log"))
    assert len(logs) == 1
    return logs[0].read_text("utf-8")


def test_one_entry_per_drop_with_the_failure_explained(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Moonforge", "type": "comics", "color": "#fff"}).json()
    put = lambda name, data: c.put(f"/api/libraries/{l['id']}/files", params={"name": name, "batch": "drop1"}, content=data)
    assert put("Starfall 01.cbz", _cbz()).status_code == 200
    assert put("Starfall 02.cbz", _cbz()).status_code == 200
    assert put("Starfall 01.cbz", _cbz()).json()["skipped"]                 # already there: still "without problems"
    r = put("Starfall 03.cbz", _cbz(damaged=True))
    assert r.status_code == 400 and "001.jpg" in r.json()["detail"]
    assert not (tmp_path / "config" / "logs").exists()                     # nothing written until the drop ends

    c.post("/api/uploads/drop1/done", json={"lib": l["id"], "cancelled": 1, "ignored": 2, "skipped": 0,
                                            "failed": [{"name": "Starfall 04.cbz", "why": "Network error"}]})
    text = _log(tmp_path)
    assert "library “Moonforge”" in text and "test@example.invalid" in text
    assert "3 out of 6 uploaded without problems (1 already there) · 2 failed · 1 cancelled" in text
    assert "2 ignored" in text
    assert "✗ Starfall 03.cbz: This archive is damaged" in text
    assert "same size — the bytes themselves differ" in text               # traced: corrupted, not cut off
    assert "ARRIVED INCOMPLETE" not in text
    assert "✗ Starfall 04.cbz: Network error (in the browser" in text
    assert "Starfall 01.cbz" not in text and "Starfall 02.cbz" not in text  # fine files are only counted


def test_drop_without_problems_is_one_short_line(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Moonforge", "type": "comics", "color": "#fff"}).json()
    for i in range(3):
        c.put(f"/api/libraries/{l['id']}/files", params={"name": f"Starfall {i}.cbz", "batch": "ok1"}, content=_cbz())
    c.post("/api/uploads/ok1/done", json={"lib": l["id"]})
    lines = [x for x in _log(tmp_path).splitlines() if x.strip()]
    assert len(lines) == 2 and lines[1].strip() == "3 out of 3 uploaded without problems"


def test_drop_never_finished_is_still_written(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Moonforge", "type": "comics", "color": "#fff"}).json()
    c.put(f"/api/libraries/{l['id']}/files", params={"name": "Starfall.cbz", "batch": "lost"}, content=_cbz())
    M.uplog.batches["lost"]["seen"] -= 3600                                # quiet for an hour: tab was closed
    M.uplog.flush_stale()
    assert "never reported the end" in _log(tmp_path)


def test_misplaced_entries_are_not_called_a_checksum_error(tmp_path, monkeypatch):
    """What the old in-browser packer made of sets over 4 GB: the index points every file to the wrong place.
    That's a broken archive, not changed bytes — the message and the log say so."""
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Mirelle", "type": "cosplay", "color": "#fff"}).json()
    data = bytearray(_cbz())
    end = data.rindex(b"PK\x05\x06")
    at = int.from_bytes(data[end + 16:end + 20], "little")
    data[end + 16:end + 20] = (at - 16).to_bytes(4, "little")             # index start off by 16 → every entry shifted
    r = c.put(f"/api/libraries/{l['id']}/files", params={"name": "Moonforge Set.zip", "batch": "b"}, content=bytes(data))
    assert r.status_code == 400
    msg = r.json()["detail"]
    assert "001.jpg" in msg and "index" in msg and "checksum" not in msg
    c.post("/api/uploads/b/done", json={"lib": l["id"]})
    assert "ZIP64" in _log(tmp_path)
