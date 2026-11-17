"""Background preparation: new books get measured, a cover and screen-sized first pages before anyone opens them."""
import threading
import time

from app import library as L
from conftest import jpeg, make_cbz


def _scan_with(lib, files, ltype="cosplay"):
    for rel, pages in files.items():
        make_cbz(L.LIB_ROOT / "Lib" / rel, pages)
    lib.create_library("Lib", "Lib", False, "#fff", ltype)
    lib.scan()


def test_scan_queues_new_books_newest_first(lib):
    _scan_with(lib, {"A.cbz": {"01.jpg": jpeg()}, "B.cbz": {"01.jpg": jpeg()}})
    assert lib.status()["preparing"] == 2


def test_prepare_does_the_first_open_work(lib):
    _scan_with(lib, {"Set.cbz": {"01.jpg": jpeg(5760, 8640), "02.jpg": jpeg(5760, 8640), "03.jpg": jpeg(5760, 8640)}})
    b = next(iter(lib.books.values()))
    assert lib.needs_prep(b)
    lib.prepare(b)
    assert not lib.needs_prep(b) and b["dims"][0] == [5760, 8640]
    copies = {p.name.rsplit("-", 1)[0] for p in (L.CONFIG_DIR / "cache" / "pages").glob("*.jpg")}
    assert len(copies) == 2                                    # the first two pages, not all of them
    assert any((L.CONFIG_DIR / "cache" / "thumbs").iterdir())  # card cover


def test_worker_drains_the_queue_and_saves(lib):
    _scan_with(lib, {f"S{i}.cbz": {"01.jpg": jpeg(), "02.jpg": jpeg()} for i in range(5)})
    threading.Thread(target=lib.prep_loop, daemon=True).start()
    for _ in range(100):
        if lib.status()["preparing"] == 0:
            break
        time.sleep(0.05)
    assert lib.status()["preparing"] == 0
    assert all(not lib.needs_prep(b) for b in lib.books.values())
    time.sleep(0.1)
    fresh = L.Library()                                         # what was measured survives a restart
    assert all(b.get("dims") for b in fresh.books.values())


def test_novels_and_videos_are_not_queued(lib):
    (L.LIB_ROOT / "Lib").mkdir(parents=True)
    (L.LIB_ROOT / "Lib" / "clip.mp4").write_bytes(b"\0" * 10)
    lib.create_library("Lib", "Lib", False, "#fff", "cosplay"); lib.scan()
    assert lib.status()["preparing"] == 0
