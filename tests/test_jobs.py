"""The job system (docs/JOBS.md): registry, lanes of workers, pause / cancel / resume, restarts, the API and the
live stream."""
import asyncio
import importlib
import json
import secrets
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.events import Hub, sse
from app.jobs import Jobs
from app.store import Db


def _jobs(tmp_path):
    return Jobs(Db.at(tmp_path / "reader.db"))


def _counting(gate=None):
    """A job that moves `n` items one by one, saving what's done (so it can resume)."""
    seen = []

    def run(ctx):
        n = ctx.params["n"]
        for i in range(n):
            if i in ctx.data.get("done", []):
                continue
            ctx.check()
            if gate:
                gate(i)
            seen.append(i)
            ctx.progress(i + 1, n, "files", label=f"file {i}")
            ctx.save(done=ctx.data.get("done", []) + [i])
        return f"moved {n}"
    return run, seen


def test_a_job_runs_and_reports(tmp_path):
    J = _jobs(tmp_path)
    run, seen = _counting()
    J.kind("move", run)
    events = []
    J.listeners.append(events.append)
    j = J.submit("move", "u1", "Moving 3 files", {"n": 3})
    assert j["state"] == "queued" and "params" not in j and "owner" not in j
    done = J.run_now(j["id"])
    assert seen == [0, 1, 2]
    assert done["state"] == "done" and done["done"] == done["total"] == 3 and done["result"] == "moved 3"
    assert done["unit"] == "files" and done["label"] is None and done["finished"]
    assert events[0]["job"]["state"] == "queued" and events[-1]["job"]["state"] == "done"
    assert [x["title"] for x in J.list({"id": "u1"})] == ["Moving 3 files"]
    assert J.list({"id": "u2"}) == []                       # someone else's


def test_failures_keep_the_message(tmp_path):
    J = _jobs(tmp_path)
    J.kind("bad", lambda ctx: 1 / 0)
    j = J.submit("bad", "u1", "x")
    assert J.run_now(j["id"])["state"] == "failed"
    assert "division" in J.get(j["id"])["error"]


def test_pause_then_resume_carries_on(tmp_path):
    J = _jobs(tmp_path)
    holder = {}

    def gate(i):
        if i == 2:
            J.control(holder["id"], "pause")              # someone presses Pause during the third file
    run, seen = _counting(gate)
    J.kind("move", run)
    holder["id"] = jid = J.submit("move", "u1", "Moving", {"n": 5})["id"]
    with pytest.raises(ValueError):
        J.control(jid, "resume")                          # nothing to resume yet
    J.run_now(jid)                                        # the pause is noticed at the next check
    assert J.get(jid)["state"] == "paused" and seen == [0, 1, 2]
    J.control(jid, "resume")
    assert J.get(jid)["state"] == "queued"
    holder["id"] = None
    J.kinds["move"].run, seen2 = _counting()
    J.run_now(jid)
    assert seen2 == [3, 4] and J.get(jid)["state"] == "done"


def test_cancel_stops_at_the_next_item(tmp_path):
    J = _jobs(tmp_path)
    holder = {}
    run, seen = _counting(lambda i: i == 1 and J.control(holder["id"], "cancel"))
    J.kind("move", run)
    holder["id"] = jid = J.submit("move", "u1", "Moving", {"n": 5})["id"]
    J.run_now(jid)
    assert J.get(jid)["state"] == "cancelled" and seen == [0, 1]
    J.control(jid, "dismiss")
    assert J.get(jid) is None


def test_only_the_owner_or_the_admin_controls(tmp_path):
    J = _jobs(tmp_path)
    J.kind("move", _counting()[0])
    J.kind("scan", _counting()[0], lane="system", pause=False)
    mine = J.submit("move", "u1", "x", {"n": 1})["id"]
    sysj = J.submit("scan", None, "Scanning", {"n": 1})["id"]
    with pytest.raises(KeyError):
        J.control(mine, "pause", {"id": "u2"})
    with pytest.raises(KeyError):
        J.control(sysj, "cancel", {"id": "u1"})          # system jobs: the admin only
    J.control(sysj, "cancel", {"id": "u1", "admin": True})
    with pytest.raises(ValueError):
        J.control(sysj, "pause", {"id": "u1", "admin": True})   # can't pause a cancelled one (nor a scan)
    assert {x["id"] for x in J.list({"id": "u1"})} == {mine, sysj}   # system jobs are everyone's to see


def test_restart_resumes_or_fails(tmp_path):
    J = _jobs(tmp_path)
    J.kind("move", _counting()[0], resumable=True)
    J.kind("rename", _counting()[0])
    a = J.submit("move", "u1", "a", {"n": 3})["id"]
    b = J.submit("rename", "u1", "b", {"n": 3})["id"]
    c = J.submit("rename", "u1", "c", {"n": 3})["id"]
    for jid in (a, b):                                    # the server stops while these two run
        J.mem[jid]["state"] = "running"; J._write(J.mem[jid])
    J.mem[a]["data"] = {"done": [0]}; J._write(J.mem[a])
    Db._open.clear()

    J2 = _jobs(tmp_path)
    run, seen = _counting()
    J2.kind("move", run, resumable=True)
    J2.kind("rename", _counting()[0])
    assert J2.get(a)["state"] == "queued"
    assert J2.get(b)["state"] == "failed" and J2.get(b)["error"] == "Stopped by a restart"
    assert J2.get(c)["state"] == "queued"                 # never started: just waits
    J2.run_now(a)
    assert seen == [1, 2]                                 # carried on where it stopped


def test_lanes_keep_your_actions_moving(tmp_path):
    """A long Optimize run in its lane doesn't hold up a move."""
    J = _jobs(tmp_path)
    release = threading.Event()

    def slow(ctx):
        release.wait(10)
    J.kind("optimize", slow, lane="optimize")
    J.kind("move", _counting()[0])
    J.start_workers()
    try:
        o = J.submit("optimize", "u1", "Optimize", {})["id"]
        end = time.time() + 5
        while J.get(o)["state"] != "running" and time.time() < end:   # the optimize lane is busy…
            time.sleep(0.01)
        m = J.submit("move", "u1", "Move", {"n": 2})["id"]                 # …and a move still goes through
        assert J.wait(m, 5)["state"] == "done"
        assert J.get(o)["state"] == "running"
        release.set()
        assert J.wait(o, 5)["state"] == "done"
    finally:
        release.set(); J.stop()


def test_ready_holds_a_job_back(tmp_path):
    J = _jobs(tmp_path)
    ok = {"v": False}
    J.kind("optimize", _counting()[0], lane="optimize", ready=lambda j: ok["v"])
    jid = J.submit("optimize", "u1", "x", {"n": 1})["id"]
    assert J._next("optimize") is None
    ok["v"] = True
    assert J._next("optimize")["id"] == jid


def test_eta_and_tidy(tmp_path):
    J = _jobs(tmp_path)
    J.kind("scan", _counting()[0], lane="system")
    j = {"state": "running", "started": 100.0, "done": 10, "total": 40}
    assert Jobs.eta(j, now=120.0) == 60                   # 10 in 20 s → 30 more in 60 s
    jid = J.submit("scan", None, "Scanning", {"n": 1})["id"]
    J.run_now(jid)
    J.tidy(time.time() + 30)
    assert J.get(jid)
    J.tidy(time.time() + 120)                             # finished system jobs clear themselves
    assert J.get(jid) is None


def test_progress_is_throttled(tmp_path):
    J = _jobs(tmp_path)
    events = []
    J.listeners.append(events.append)

    def run(ctx):
        for i in range(500):
            ctx.progress(i + 1, 500)
    J.kind("many", run)
    J.run_now(J.submit("many", "u1", "x")["id"])
    assert len(events) < 20 and events[-1]["job"]["done"] == 500


def test_the_stream_sends_only_what_you_may_see():
    hub = Hub(lambda ev, user: ev.get("owner") in (None, user["id"]))

    async def go():
        out = []
        gone = asyncio.Event()

        async def disconnected():
            return gone.is_set()
        gen = hub.stream({"id": "u1"}, {"type": "hello"}, disconnected)
        out.append(await gen.__anext__())                 # retry
        out.append(await gen.__anext__())                 # hello
        await asyncio.sleep(0)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, hub.publish, {"type": "x", "owner": "u2"})
        await loop.run_in_executor(None, hub.publish, {"type": "x", "owner": "u1"})
        out.append(await asyncio.wait_for(gen.__anext__(), 2))
        assert hub.count == 1
        await gen.aclose()
        assert hub.count == 0
        return out
    out = asyncio.run(go())
    assert out[0].startswith("retry:") and json.loads(out[1][6:]) == {"type": "hello"}
    assert json.loads(out[2][6:]) == {"type": "x", "owner": "u1"}
    assert "ownerId" not in sse({"type": "job", "job": {"id": "a", "ownerId": "u1"}})


def test_api_lists_and_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "d")); monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "d").mkdir(); (tmp_path / "c").mkdir()
    import app.library, app.main
    importlib.reload(app.library); M = importlib.reload(app.main)
    c = TestClient(M.app)
    c.post("/api/auth/setup", json={"email": "test@example.invalid", "password": secrets.token_urlsafe(12)})
    run, seen = _counting()
    M.jobs.kind("move", run)
    uid = M.accounts.by_email("test@example.invalid")["id"]
    jid = M.jobs.submit("move", uid, "Moving 2", {"n": 2})["id"]
    other = M.jobs.submit("move", "someone-else", "Not yours", {"n": 2})["id"]
    js = c.get("/api/jobs").json()["jobs"]
    assert [j["title"] for j in js] == ["Moving 2"] and js[0]["kind"] == "move"
    assert c.post(f"/api/jobs/{other}/cancel").status_code == 404
    assert c.post(f"/api/jobs/{jid}/resume").status_code == 409
    assert c.post(f"/api/jobs/{jid}/pause").json() == {"ok": True}
    assert c.get("/api/jobs").json()["jobs"][0]["state"] == "paused"
    assert c.post(f"/api/jobs/{jid}/cancel").json() == {"ok": True}
    assert c.post(f"/api/jobs/{jid}/dismiss").json() == {"ok": True}
    assert c.get("/api/jobs").json()["jobs"] == []
    assert c.post("/api/jobs/nope/cancel").status_code == 404


def test_closing_ends_every_stream():
    """`docker stop` must not wait for open tabs: closing the hub ends their streams."""
    hub = Hub()

    async def go():
        async def never():
            return False
        gen = hub.stream({"id": "u1"}, {"type": "hello"}, never)
        await gen.__anext__(); await gen.__anext__()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, hub.close)
        try:
            await asyncio.wait_for(gen.__anext__(), 2)
        except StopAsyncIteration:
            return True
        return False
    assert asyncio.run(go()) and hub.count == 0
