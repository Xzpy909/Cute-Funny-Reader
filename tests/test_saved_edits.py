"""Details, tags and the cover choice are saved in the database — instantly, whatever the file's size — and
written into the files' metadata.json only on request ("Write into files")."""
import json
import zipfile

from app import library as L
from conftest import jpeg, make_cbz


def _series(lib, n_books=2, pages=3):
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"] / "Starfall"
    for i in range(1, n_books + 1):
        make_cbz(root / f"Starfall {i:02}.cbz", {f"{p:03}.jpg": jpeg(color=("red", "blue", "green")[p % 3]) for p in range(pages)})
    lib.scan()
    books = sorted(lib.books.values(), key=lambda b: b["number"])
    return books, root


def _meta(path) -> dict:
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("metadata.json")) if "metadata.json" in z.namelist() else {}


def test_edits_are_saved_without_touching_the_files(lib):
    books, root = _series(lib)
    before = {p: p.stat().st_mtime_ns for p in root.iterdir()}
    lib.edit_series(books[0]["seriesId"], {"author": "Mirelle", "tagsAdd": ["cute"], "tagsBase": ["cute"], "direction": "rtl"})
    assert {p: p.stat().st_mtime_ns for p in root.iterdir()} == before          # no file was rewritten
    for b in books:
        e = lib.effective(lib.books[b["id"]])
        assert e["author"] == "Mirelle" and e["tags"] == ["cute"] and e["rtl"] is True
        assert e["edited"] and e["unsaved"]


def test_cover_choice_is_saved_without_touching_the_files(lib):
    books, root = _series(lib)
    sid = books[0]["seriesId"]
    before = {p: p.stat().st_mtime_ns for p in root.iterdir()}
    lib.set_cover(sid, books[1]["id"], 2)
    assert {p: p.stat().st_mtime_ns for p in root.iterdir()} == before
    second = lib.effective(lib.books[books[1]["id"]])
    assert second["seriesCover"] and second["cover"] == second["entries"][2]
    assert lib.cover_tag(lib.books[books[1]["id"]]) == "2"
    assert not lib.edits.get(books[0]["id"])                 # the first book already matches its file: nothing kept
    lib.set_cover(sid, None, None)                           # back to the default: nothing left to remember
    assert not lib.edits.get(books[1]["id"])


def test_cover_image_follows_the_saved_choice(lib):
    books, root = _series(lib, n_books=1)
    b = lib.books[books[0]["id"]]
    first = lib.cover(b, 200)
    lib.set_cover(b["seriesId"], b["id"], 1)
    assert lib.cover(b, 200) != first                        # page 2 (blue) instead of page 1 (red)
    assert lib.cover(b, 200) == lib.thumb(b, 1, 200)


def test_write_into_files_then_forget(lib):
    books, root = _series(lib)
    sid = books[0]["seriesId"]
    lib.edit_series(sid, {"author": "Mirelle", "summary": "A short one."})
    lib.set_cover(sid, books[1]["id"], 1)
    assert lib.write_edits(sid) == 2
    m1, m2 = _meta(root / "Starfall 01.cbz"), _meta(root / "Starfall 02.cbz")
    assert m1["artists"] == ["Mirelle"] and m1["summary"] == "A short one." and "seriesCover" not in m1
    assert m2["artists"] == ["Mirelle"] and m2["thumbnail"] == 1 and m2["seriesCover"] is True
    assert not lib.edits.get(books[0]["id"]) and not lib.edits.get(books[1]["id"])
    after = lib.effective(lib.books[books[1]["id"]])        # read back from the file at the rescan
    assert after["author"] == "Mirelle" and after["seriesCover"] and after["cover"] == after["entries"][1]
    assert not after.get("unsaved")
    assert lib.write_edits(sid) == 0                         # nothing left to write


def test_reset_forgets_saved_edits(lib):
    books, root = _series(lib, n_books=1)
    sid = books[0]["seriesId"]
    lib.edit_series(sid, {"author": "Mirelle"})
    lib.edit_series(sid, {}, reset=True)
    assert not lib.edits.get(books[0]["id"]) and not lib.effective(lib.books[books[0]["id"]]).get("author")


def test_through_the_api(tmp_path, monkeypatch):
    import importlib, secrets
    from fastapi.testclient import TestClient
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "d")); monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "d").mkdir(); (tmp_path / "c").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)})
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    make_cbz(tmp_path / "d" / l["path"] / "Starfall" / "Starfall 01.cbz", {"001.jpg": jpeg(), "002.jpg": jpeg(color="blue")})
    M.lib.scan()
    (b,) = M.lib.books.values()
    rev = M.lib.rev
    assert c.patch(f"/api/series/{b['seriesId']}/details", json={"fields": {"author": "Mirelle"}}).status_code == 200
    assert M.lib.rev > rev                                   # other tabs / devices notice the change
    assert c.put(f"/api/series/{b['seriesId']}/cover", json={"book": b["id"], "page": 1}).status_code == 200
    got = c.get(f"/api/books/{b['id']}").json()
    assert got["author"] == "Mirelle" and got["unsaved"] and got["coverPage"] == 1
    assert c.post(f"/api/series/{b['seriesId']}/write").json() == {"files": 1}
    got = c.get(f"/api/books/{b['id']}").json()
    assert got["author"] == "Mirelle" and not got["unsaved"] and got["coverPage"] == 1
