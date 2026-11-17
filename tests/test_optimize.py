"""✨ Optimize: books converted to AVIF safely — same id and progress, checked before swapping in, undo-able."""
import io
import time
import zipfile

import numpy as np
import pytest
from PIL import Image, ImageFilter

from app import library as L
from app.optimize import Optimizer, encode_page
from conftest import make_cbz

P = {"id": "t", "name": "Test", "quality": 60, "speed": 8, "subsampling": "auto", "grayscale": True}


def photo(w=600, h=900, seed=1, q=95) -> bytes:
    """A photo-like JPEG (smooth noise): AVIF makes it much smaller."""
    rng = np.random.default_rng(seed)
    im = Image.fromarray(rng.normal(128, 50, (h // 4, w // 4, 3)).clip(0, 255).astype("uint8")).resize((w, h)).filter(ImageFilter.GaussianBlur(2))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=q); return buf.getvalue()


def gif() -> bytes:
    buf = io.BytesIO(); Image.new("P", (40, 40)).save(buf, "GIF"); return buf.getvalue()


def _book(lib, pages, ltype="comics", name="Starfall 01.cbz"):
    l = lib.create_library("Lib", "Lib", False, "#fff", ltype)
    make_cbz(L.LIB_ROOT / l["path"] / "Starfall" / name, pages)
    lib.scan()
    return next(iter(lib.books.values()))


def test_a_book_becomes_avif_and_keeps_its_id_progress_and_pages(lib):
    b = _book(lib, {"001.jpg": photo(seed=1), "002.jpg": photo(seed=2), "003.gif": gif(), "metadata.json": b'{"tags": ["x"]}'})
    lib.progress.put(b["id"], {"page": 1})
    before = (L.LIB_ROOT / b["rel"]).read_bytes()
    o = Optimizer(lib)
    r = o.convert(b, P, keep=True, max_edge=0)
    assert r["converted"] == 2 and r["after"] < r["before"]
    nb = lib.get(b["id"])
    assert nb["entries"] == ["001.avif", "002.avif", "003.gif"]          # same order, the GIF untouched
    assert lib.progress.get(b["id"]) == {"page": 1} and nb["tags"] == ["x"]
    with zipfile.ZipFile(L.LIB_ROOT / nb["rel"]) as z:
        Image.open(io.BytesIO(z.read("001.avif"))).load()
    assert o.can_undo(b["id"])
    o.undo(b["id"])
    assert (L.LIB_ROOT / b["rel"]).read_bytes() == before                 # exactly the original again
    assert lib.get(b["id"])["entries"] == ["001.jpg", "002.jpg", "003.gif"]
    assert not list((L.CONFIG_DIR / "originals").iterdir())


def test_without_keeping_there_is_nothing_to_undo(lib):
    b = _book(lib, {"001.jpg": photo()})
    o = Optimizer(lib)
    o.convert(b, P, keep=False, max_edge=0)
    assert not o.can_undo(b["id"])
    with pytest.raises(ValueError):
        o.undo(b["id"])


def test_pages_that_would_grow_stay_as_they_are(lib):
    tiny = io.BytesIO(); Image.new("RGB", (8, 8), "white").save(tiny, "WEBP", quality=20)     # ~40 bytes
    b = _book(lib, {"001.webp": tiny.getvalue()})
    r = Optimizer(lib).convert(b, P, keep=True, max_edge=0)
    assert r["converted"] == 0 and lib.get(b["id"])["entries"] == ["001.webp"]


def test_huge_photos_can_be_shrunk_and_bw_pages_stay_gray(lib):
    big = encode_page(photo(1200, 1800), "a.jpg", P, "cosplay", max_edge=800)
    with Image.open(io.BytesIO(big)) as im:
        assert max(im.size) == 800
    gray = io.BytesIO(); Image.fromarray(np.tile(np.linspace(0, 255, 600, dtype="uint8"), (900, 1))).convert("RGB").save(gray, "JPEG", quality=98)
    out = encode_page(gray.getvalue(), "g.jpg", P, "manga")
    with Image.open(io.BytesIO(out)) as im:
        a = np.asarray(im.convert("RGB"), dtype=int)
        assert (a.max(axis=2) - a.min(axis=2)).max() <= 2


def test_a_photo_folder_is_converted_in_place_and_undone(lib):
    l = lib.create_library("Cos", "Cos", False, "#fff", "cosplay")
    d = L.LIB_ROOT / l["path"] / "Mirelle" / "Garden"
    d.mkdir(parents=True)
    for i in range(3):
        (d / f"{i:02}.jpg").write_bytes(photo(seed=i))
    (d / "clip.mp4").write_bytes(b"\0" * 100)
    lib.scan()
    b = next(iter(lib.books.values()))
    o = Optimizer(lib)
    r = o.convert(b, P, keep=True, max_edge=0)
    assert r["converted"] == 3
    assert sorted(p.name for p in d.iterdir() if not p.name.startswith(".")) == ["00.avif", "01.avif", "02.avif", "clip.mp4"]
    o.undo(b["id"])
    assert sorted(p.name for p in d.iterdir() if not p.name.startswith(".")) == ["00.jpg", "01.jpg", "02.jpg", "clip.mp4"]
    assert (d / "01.jpg").read_bytes() == photo(seed=1)


def test_stopping_midway_leaves_the_book_untouched(lib):
    b = _book(lib, {f"{i:03}.jpg": photo(seed=i) for i in range(8)})
    before = (L.LIB_ROOT / b["rel"]).read_bytes()
    calls = {"n": 0}
    def stop():
        calls["n"] += 1
        return calls["n"] > 1
    from app.optimize import Cancelled
    with pytest.raises(Cancelled):
        Optimizer(lib).convert(b, P, keep=True, max_edge=0, stop=stop)
    assert (L.LIB_ROOT / b["rel"]).read_bytes() == before
    assert not [p for p in (L.LIB_ROOT / b["rel"]).parent.iterdir() if p.name.startswith(".")]


def test_queue_runs_pauses_resumes_and_survives_a_restart(lib, monkeypatch):
    l = lib.create_library("Lib", "Lib", False, "#fff", "comics")
    for n in ("Starfall 01", "Starfall 02", "Moonforge 01"):
        make_cbz(L.LIB_ROOT / l["path"] / n.split()[0] / f"{n}.cbz", {"001.jpg": photo(seed=len(n)), "002.jpg": photo(seed=3)})
    lib.scan()
    o = Optimizer(lib)
    monkeypatch.setattr(o, "presets", lambda: [P])
    j = o.start("me", list(lib.books.values()), "t", keep=True, max_edge=0, title="All")
    assert o.step()                                        # one book
    o.control("me", j["id"], "pause")
    o.step()                                               # paused: nothing happens
    assert len(o.jobs.get(j["id"])["done"]) == 1
    o.control("me", j["id"], "resume")
    o2 = Optimizer(lib)                                    # the server restarted
    monkeypatch.setattr(o2, "presets", lambda: [P])
    while o2.step():
        if o2.jobs.get(j["id"])["state"] == "done":
            break
    done = o2.jobs.get(j["id"])
    assert done["state"] == "done" and len(done["done"]) == 3 and done["after"] < done["before"]
    assert all(e.endswith(".avif") for b in lib.books.values() for e in b["entries"])
    assert o2.list("me")[0]["pagesDone"] == 6 and o2.list("someone-else") == []


def test_kept_originals_are_cleaned_up_after_the_keep_time(lib):
    b = _book(lib, {"001.jpg": photo()})
    o = Optimizer(lib)
    o.convert(b, P, keep=True, max_edge=0)
    o.cleanup(time.time() + 13 * 86400)
    assert o.can_undo(b["id"])
    o.cleanup(time.time() + 15 * 86400)
    assert not o.can_undo(b["id"]) and not list((L.CONFIG_DIR / "originals").iterdir())


def test_default_preset_and_own_presets(lib):
    b = _book(lib, {"001.jpg": photo(seed=1), "002.jpg": photo(seed=2)})
    o = Optimizer(lib)
    assert [(p["id"], p["quality"], p["speed"]) for p in o.presets()] == [("default", 70, 6)]
    mine = o.add_preset("Small", 40, 8)
    assert [p["name"] for p in o.presets()] == ["Default", "Small"]
    with pytest.raises(ValueError):
        o.add_preset("small", 50, 6)                       # same name
    with pytest.raises(ValueError):
        o.add_preset("Huge", 130, 6)                       # quality out of range
    with pytest.raises(ValueError):
        o.delete_preset("default")                         # the baseline stays
    e = o.estimate([b], o.preset(mine["id"]), 0)
    assert e["books"] == 1 and 0 < e["after"] < e["before"]
    j = o.start("me", [b], mine["id"], keep=True, max_edge=0, title="x")
    o.delete_preset(mine["id"])                            # deleted while queued: the job keeps its settings
    assert [p["id"] for p in o.presets()] == ["default"]
    while o.step():
        if o.jobs.get(j["id"])["state"] == "done":
            break
    assert o.jobs.get(j["id"])["settings"]["quality"] == 40 and lib.get(b["id"])["entries"] == ["001.avif", "002.avif"]


def test_the_api_end_to_end(tmp_path, monkeypatch):
    import importlib, secrets
    from fastapi.testclient import TestClient
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "data")); monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    import app.library, app.optimize, app.main
    importlib.reload(app.library); importlib.reload(app.optimize); M = importlib.reload(app.main)
    c = TestClient(M.app)
    c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)})
    l = c.post("/api/libraries", json={"name": "Comics", "type": "comics", "color": "#fff"}).json()
    root = M.LIB_ROOT / l["path"]
    for n in ("Starfall 01", "Starfall 02"):
        make_cbz(root / "Starfall" / f"{n}.cbz", {"001.jpg": photo(seed=len(n)), "002.jpg": photo(seed=5)})
    M.lib.scan()
    sid = next(iter(M.lib.books.values()))["seriesId"]
    pr = c.get("/api/optimize/presets").json()
    assert [p["id"] for p in pr["presets"]] == ["default"]
    mine = c.post("/api/optimize/presets", json={"name": "Lighter", "quality": 55, "speed": 7}).json()
    assert [p["name"] for p in c.get("/api/optimize/presets").json()["presets"]] == ["Default", "Lighter"]
    assert c.delete("/api/optimize/presets/default").status_code == 400
    assert c.delete(f"/api/optimize/presets/{mine['id']}").status_code == 200
    est = c.post("/api/optimize/estimate", json={"series": [sid], "preset": "default"}).json()
    assert est["books"] == 2 and est["after"] < est["before"] and est["sample"]
    cmp = c.get(f"/api/books/{est['sample']['book']}/pages/{est['sample']['page']}/optimized", params={"preset": "default"})
    assert cmp.headers["content-type"] == "image/avif" and int(cmp.headers["X-After"]) < int(cmp.headers["X-Before"])
    job = c.post("/api/optimize", json={"series": [sid], "preset": "default", "keep": True, "title": "Starfall"}).json()
    while M.opt.step():
        pass
    j = c.get("/api/jobs").json()["jobs"][0]
    assert j["id"] == job["id"] and j["state"] == "done" and len(j["done"]) == 2
    books = c.get("/api/library").json()["books"]
    assert all(b["avif"] and b["canUndo"] for b in books)
    assert c.post("/api/optimize/undo", json={"series": [sid]}).json() == {"restored": 2}
    assert not any(b["avif"] or b["canUndo"] for b in c.get("/api/library").json()["books"])
    assert c.post(f"/api/jobs/{job['id']}/dismiss").status_code == 200 and c.get("/api/jobs").json()["jobs"] == []


def test_new_uploads_are_optimized_by_themselves(lib):
    l = lib.create_library("Cos", "Cos", False, "#fff", "cosplay")
    root = L.LIB_ROOT / l["path"]
    make_cbz(root / "Mirelle" / "Garden" / "Old.cbz", {"001.jpg": photo(seed=1)})
    lib.scan()
    old = next(iter(lib.books.values()))
    o = Optimizer(lib)
    assert o.collect_auto() == 0                                   # off: nothing happens
    lib.update_library(l["id"], {"autoOptimize": "default"})
    lib.get_library(l["id"])["autoSince"] = int(time.time()) + 5   # (what was there before stays as it is)
    make_cbz(root / "Mirelle" / "Lake" / "New 1.cbz", {"001.jpg": photo(seed=2)})
    make_cbz(root / "Mirelle" / "Lake" / "New 2.cbz", {"001.jpg": photo(seed=3)})
    lib.scan()
    for b in lib.books.values():
        if b["id"] != old["id"]:
            b["added"] = int(time.time()) + 10
    assert o.collect_auto(time.time() + 15) == 0                   # just arrived: wait for the rest of the batch
    assert o.collect_auto(time.time() + 60) == 2
    assert o.collect_auto(time.time() + 61) == 0                   # each book once
    job = next(iter(o.jobs.all().values()))
    assert job["auto"] == l["id"] and job["title"] == "New in Cos" and job["keep"] and len(job["books"]) == 2
    while o.step():
        if o.jobs.get(job["id"])["state"] == "done":
            break
    by = {b["file"]: b for b in lib.books.values()}
    assert by["New 1.cbz"]["entries"] == ["001.avif"] and by["Old.cbz"]["entries"] == ["001.jpg"]
    lib.update_library(l["id"], {"autoOptimize": ""})
    assert "autoOptimize" not in lib.get_library(l["id"])


def test_heic_and_jxl_books_convert_too(lib):
    import pillow_heif, pillow_jxl  # noqa: F401
    im = Image.open(io.BytesIO(photo(400, 600)))
    h, j = io.BytesIO(), io.BytesIO()
    im.save(h, "HEIF", quality=95); im.save(j, "JXL", quality=95)
    b = _book(lib, {"001.heic": h.getvalue(), "002.jxl": j.getvalue()})
    assert L.needs_transcode(b)
    Optimizer(lib).convert(b, {**P, "quality": 40}, keep=True, max_edge=0)
    nb = lib.get(b["id"])
    assert nb["entries"] == ["001.avif", "002.avif"] and not L.needs_transcode(nb)   # opens without waiting now
