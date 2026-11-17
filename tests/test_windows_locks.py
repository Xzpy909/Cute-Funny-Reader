"""On Windows hosts a folder can't be renamed (and a file can't be replaced) while a file inside is open.
Linux doesn't mind, so these tests make rename / replace behave like Windows: they fail while this process
holds a handle under the path. The app's own handles (the reader's cache, the background worker measuring
a fresh upload) must never be what blocks Edit details."""
import os
import threading
import time
from pathlib import Path

import pytest

from app import library as L
from conftest import jpeg, make_cbz


def _open_under(p: Path) -> bool:
    p = str(p.resolve())
    for fd in os.listdir("/proc/self/fd"):
        try:
            t = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        if t == p or t.startswith(p + "/"):
            return True
    return False


@pytest.fixture
def windows(monkeypatch):
    real_rename, real_replace = Path.rename, os.replace

    def rename(self, target):
        if _open_under(self):
            raise PermissionError(13, "The process cannot access the file because it is being used")
        return real_rename(self, target)

    def replace(src, dst):
        if Path(dst).exists() and _open_under(Path(dst)):
            raise PermissionError(13, "The process cannot access the file because it is being used")
        return real_replace(src, dst)

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(os, "replace", replace)


def _book(lib, pages=4):
    l = lib.create_library("Manga", "Manga", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    make_cbz(root / "Images 2026-11-16" / "Images 2026-11-16.cbz", {f"{i:03}.jpg": jpeg() for i in range(pages)})
    lib.scan()
    return next(iter(lib.books.values())), root


def test_rename_after_reading_pages(lib, windows):
    b, root = _book(lib)
    lib.read(b, b["entries"][0])                         # the reader has the archive open (cached handle)
    assert _open_under(root / "Images 2026-11-16")
    lib.edit_series(b["seriesId"], {"author": "someone"})  # saved in the database …
    assert lib.write_edits(b["seriesId"]) == 1             # … then written into the archive (a rewrite)
    lib.read(lib.books[b["id"]], b["entries"][1])
    new = lib.rename_series(b["seriesId"], "test raw manga")
    assert (root / "test raw manga" / "Images 2026-11-16.cbz").exists()
    assert lib.series_books(new)[0]["author"] == "someone"


def test_rename_waits_for_the_background_worker(lib, windows):
    b, root = _book(lib)
    b.pop("dims", None)
    started, slow = threading.Event(), L.Library._dims

    def measuring(self, book, save):                     # a big fresh upload being measured
        started.set(); time.sleep(0.6)
        return slow(self, book, save)

    import zipfile
    def held(self, book, save):                          # keep the archive open the whole time, like a big set
        with zipfile.ZipFile(L.LIB_ROOT / book["rel"]):
            return measuring(self, book, save)

    L.Library._dims, orig = held, L.Library._dims
    try:
        t = threading.Thread(target=lib.dims, args=(b,), kwargs={"save": False}); t.start()
        started.wait(2)
        lib.rename_series(b["seriesId"], "test raw manga")   # waits for the measuring, then renames
        t.join()
    finally:
        L.Library._dims = orig
    assert (root / "test raw manga" / "Images 2026-11-16.cbz").exists()


def test_a_brief_lock_by_windows_is_waited_out(lib, monkeypatch):
    b, root = _book(lib)
    real, n = Path.rename, {"fails": 0}

    def flaky(self, target):                             # antivirus checks the freshly written file
        if n["fails"] < 3:
            n["fails"] += 1
            raise PermissionError(13, "in use")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    lib.rename_series(b["seriesId"], "test raw manga")
    assert (root / "test raw manga").is_dir() and n["fails"] == 3


def test_something_else_keeping_it_open_gives_a_clear_message(lib, monkeypatch):
    b, root = _book(lib)
    real = Path.rename
    monkeypatch.setattr(Path, "rename", lambda self, t: (_ for _ in ()).throw(PermissionError(13, "in use")))
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    with pytest.raises(OSError, match="open somewhere"):
        lib.rename_series(b["seriesId"], "test raw manga")
    monkeypatch.setattr(Path, "rename", real)
    assert (root / "Images 2026-11-16" / "Images 2026-11-16.cbz").exists()   # left where it was
