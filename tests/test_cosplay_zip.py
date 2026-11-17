"""Cosplay libraries keep sets as plain .zip: packed photo folders arrive as .zip, other archives become .zip,
and .cbz (old sets, or uploaded as .cbz) is still read and accepted. Comics libraries keep .cbz."""
import importlib
import io
import secrets
import zipfile

from fastapi.testclient import TestClient

from conftest import jpeg


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("001.jpg", jpeg()); z.writestr("002.jpg", jpeg())
    return buf.getvalue()


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    assert c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)}).status_code == 200
    return M, c


def test_cosplay_keeps_zip_and_accepts_cbz(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Cos", "type": "cosplay", "color": "#fff"}).json()
    up = lambda name, **kw: c.put(f"/api/libraries/{l['id']}/files", params={"name": name, **kw}, content=_zip()).json()

    r = up("Circuit Hunter Mika Normal.zip", collection="Sela", folder="Circuit Hunter Mika")
    assert r["path"].endswith("Sela/Circuit Hunter Mika/Circuit Hunter Mika Normal.zip") and not r["converted"]
    r = up("Circuit Hunter Mika SP-version.cbz", collection="Sela", folder="Circuit Hunter Mika")
    assert r["path"].endswith("Circuit Hunter Mika SP-version.cbz")                 # .cbz stays .cbz
    # the same set again, packed as .zip this time: recognised, not added twice
    assert up("Circuit Hunter Mika SP-version.zip", collection="Sela", folder="Circuit Hunter Mika")["skipped"]
    M.lib.scan()
    books = sorted(b["file"] for b in M.lib.books.values())
    assert books == ["Circuit Hunter Mika Normal.zip", "Circuit Hunter Mika SP-version.cbz"]
    assert {b["series"] for b in M.lib.books.values()} == {"Circuit Hunter Mika"}
    assert all(b["pages"] == 2 for b in M.lib.books.values())


def test_comics_still_turn_zip_into_cbz(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    r = c.put(f"/api/libraries/{l['id']}/files", params={"name": "Starfall 01.zip"}, content=_zip()).json()
    assert r["path"].endswith("Starfall 01.cbz") and r["converted"]


def _damaged() -> bytes:
    """A stored zip whose page was changed after packing: same size, wrong checksum."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("001.jpg", jpeg(400, 600)); z.writestr("002.jpg", jpeg())
    raw = bytearray(buf.getvalue())
    at = raw.index(b"\xff\xd9") - 3                    # a byte near the end of the first picture
    raw[at] ^= 0x55
    return bytes(raw)


def test_damaged_upload_is_refused_and_names_keep_their_subtitle(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    put = lambda name, data: c.put(f"/api/libraries/{l['id']}/files", params={"name": name}, content=data)
    r = put("The Princess (But Can't Hide Her Crown).cbz", _damaged())
    assert r.status_code == 400 and "damaged" in r.json()["detail"] and "001.jpg" in r.json()["detail"]
    assert put("The Princess (But Can't Hide Her Crown).cbz", _zip()).status_code == 200
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("001.jpg", jpeg(80, 120))
    r = put("The Princess (But Can't Hide Her Crown).cbz", buf.getvalue()).json()     # same name, other content
    assert r["path"].endswith("The Princess (But Can't Hide Her Crown) (2).cbz")


def test_a_damaged_book_already_in_the_library_still_opens(tmp_path, monkeypatch):
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    root = M.LIB_ROOT / l["path"]
    (root / "Old").mkdir(parents=True); (root / "Old" / "Old 01.cbz").write_bytes(_damaged())
    M.lib.scan()
    b = next(iter(M.lib.books.values()))
    assert c.get(f"/api/books/{b['id']}/pages/0").status_code == 200       # shown as it is
    assert c.get(f"/api/books/{b['id']}/pages/1").status_code == 200


def test_two_same_named_uploads_at_once_dont_mix(tmp_path, monkeypatch):
    # the cause of the three damaged books: both uploads wrote into one temporary file
    import threading, time
    M, c = _app(tmp_path, monkeypatch)
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()

    def book(color, n):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            z.writestr("page.jpg", jpeg(300 + n * 40, 400, color))
        return buf.getvalue()
    a, b, first = book("red", 1), book("blue", 4), book("green", 2)
    url = f"/api/libraries/{l['id']}/files"
    assert c.put(url, params={"name": "Same Name (Sub).cbz"}, content=first).status_code == 200

    def slow(data):                                      # arrives in pieces, so the two overlap
        for i in range(0, len(data), 400):
            yield data[i:i + 400]
            time.sleep(0.01)

    codes = []
    def send(d):
        with TestClient(M.app, cookies=c.cookies) as tc:
            codes.append(tc.put(url, params={"name": "Same Name (Sub).cbz"}, data=slow(d)).status_code)
    ts = [threading.Thread(target=send, args=(d,)) for d in (a, b)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert codes == [200, 200]
    root = M.LIB_ROOT / l["path"]
    files = sorted(p.name for p in root.rglob("*.cbz"))
    assert files == ["Same Name (Sub) (2).cbz", "Same Name (Sub) (3).cbz", "Same Name (Sub).cbz"]
    got = {p.read_bytes() for p in root.rglob("*.cbz")}
    assert got == {a, b, first}                          # each arrived whole, none mixed
    assert not list(root.rglob("*.part"))
