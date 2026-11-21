"""Scans, the trash mover and JPEG XL / HEIC conversion report as jobs — but only when they take a while, and
only in memory (a restart has nothing to resume)."""
import time

from app import library as L
from app.jobs import Jobs, Tracker
from app.store import Db
from conftest import jpeg, make_cbz


def test_quick_work_never_shows(tmp_path):
    J = Jobs(Db.at(tmp_path / "r.db"))
    with J.track("scan", "Scanning", unit="files", total=10, after=0.2) as t:
        t.progress(5)
    assert J.list() == []
    with J.track("scan", "Scanning", unit="files", total=10, after=0.05) as t:
        t.progress(5)
        time.sleep(0.06)
        t.progress(6, label="Comics")
        j = J.list()[0]
        assert j["state"] == "running" and j["done"] == 6 and j["label"] == "Comics" and j["system"]
        assert not j["canCancel"] and not j["canPause"]
    j = J.list()[0]
    assert j["state"] == "done" and j["done"] == 10
    assert J.store.all() == {}                                 # never written to the database
    J.tidy(time.time() + 120)
    assert J.list() == []


def test_failed_work_says_why(tmp_path):
    J = Jobs(Db.at(tmp_path / "r.db"))
    try:
        with J.track("transcode", "Converting", owner="u1", after=0):
            raise OSError("disk full")
    except OSError:
        pass
    j = J.list({"id": "u1"})[0]
    assert j["state"] == "failed" and "disk full" in j["error"] and not j["system"]


def _eager(J):
    J.track = lambda kind, title, owner=None, unit="items", total=None, after=1.0, ref=None: Tracker(J, kind, title, owner, unit, total, 0, ref)


def test_a_scan_and_the_trash_mover_report(lib):
    J = Jobs(lib.db)
    _eager(J)
    events = []
    J.listeners.append(events.append)
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    for i in range(1, 4):
        make_cbz(L.LIB_ROOT / l["path"] / "Starfall" / f"Starfall 0{i}.cbz", {"001.jpg": jpeg()})
    lib.scan()
    lib.jobs = J
    lib.scan(deep=True)
    scans = [e["job"] for e in events if e["job"]["kind"] == "scan"]
    assert scans and scans[-1]["state"] == "done" and scans[-1]["done"] == 3 and scans[-1]["title"] == "Checking everything"
    lib.trash_books([next(iter(lib.books.values()))])
    lib.trash_tick(time.time() + L.TRASH_DELAY + 1)
    tr = [e["job"] for e in events if e["job"]["kind"] == "trash"]
    assert tr[-1]["state"] == "done" and tr[-1]["done"] == tr[-1]["total"] == 1
