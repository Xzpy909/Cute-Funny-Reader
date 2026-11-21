"""Background jobs: one registry, lanes of workers, pause / cancel, live progress (design: docs/JOBS.md).

    jobs = Jobs(db)
    jobs.kind("move", run_move, lane="user", resumable=True)
    jobs.start_workers()
    job = jobs.submit("move", owner="u1", title="Moving 12 series", params={...})

`run(ctx)` does the work; it calls ctx.check() between items, ctx.progress() as it goes and ctx.save() for
whatever resuming needs. Every change is announced to `listeners` (the /api/events stream).
"""
from __future__ import annotations

import contextvars
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .store import Db, Store

log = logging.getLogger("cfreader")

LANES = {"user": 2, "optimize": 1, "system": 1}          # workers per lane: your own actions never wait behind Optimize
ACTIVE = ("queued", "running", "paused")
FINISHED = ("done", "failed", "cancelled")
SYSTEM_KEEP = 60                                         # finished system jobs disappear after this long
KEEP = 7 * 86400                                         # finished jobs of a person: until dismissed, at most this long
SAVE_EVERY = 2.0                                         # progress reaches the database at most this often
NOTIFY_EVERY = 0.25                                      # … and the live stream at most this often (per job)
PRIVATE = ("params", "data", "owner", "memory")
current: contextvars.ContextVar["Ctx | None"] = contextvars.ContextVar("job", default=None)   # the job this thread runs


def step(label: str | None = None, n: int = 1):
    """Called by code deep inside an operation (e.g. after each file moved): counts one item for the job this
    thread is running, if any, and stops there when the job was cancelled. Outside a job: nothing."""
    ctx = current.get()
    if ctx is not None:
        ctx.count += n
        ctx.progress(ctx.count, label=label)
        ctx.check()


class Paused(Exception):
    """Raised by ctx.check() when the job was paused: it goes back to its lane, `data` kept."""


class Cancelled(Exception):
    """Raised by ctx.check() when the job was cancelled."""


@dataclass
class Kind:
    name: str
    run: Callable
    lane: str = "user"
    resumable: bool = False          # after a restart: carry on (True) or fail (False)
    pause: bool = True               # may be paused
    cancel: bool = True              # may be cancelled
    ready: Callable | None = None    # ready(job) → may it run now? (e.g. Optimize's night-only hours)
    low: bool = False                # run its worker at low CPU priority


@dataclass
class Ctx:
    """What a running job sees."""
    jobs: "Jobs"
    id: str
    params: dict
    data: dict = field(default_factory=dict)
    count: int = 0                   # items counted with jobs.step()

    def check(self):
        state = self.jobs._state(self.id)
        if state == "paused":
            raise Paused()
        if state == "cancelled":
            raise Cancelled()

    def progress(self, done, total=None, unit=None, label=None):
        self.jobs._progress(self.id, done, total, unit, label)

    def save(self, **data):
        self.data.update(data)
        self.jobs._save_data(self.id, self.data)


class Tracker:
    """Work that runs in its own loop (a scan, the trash mover, a JPEG XL conversion) reported as a job. The job
    appears only once the work has taken `after` seconds — the many quick scans never show — and lives in memory
    only (nothing to resume after a restart).

        with jobs.track("scan", "Scanning", unit="files", total=3400) as t:
            for …: t.progress(n, label=…)
    """

    def __init__(self, reg: "Jobs | None", kind: str, title: str, owner: str | None, unit: str, total, after: float,
                 ref: str | None = None):
        self.reg, self.kind, self.title, self.owner, self.unit, self.ref = reg, kind, title, owner, unit, ref
        self.total, self.after, self.t0 = total, after, time.time()
        self.done, self.label, self.id = 0, None, None

    def progress(self, done=None, total=None, label=None, n: int = 0):
        self.done = self.done + n if done is None else done
        if total is not None:
            self.total = total
        if label is not None:
            self.label = label
        if self.reg is None:
            return
        if self.id is None:
            if time.time() - self.t0 < self.after:
                return
            self.id = self.reg._track_open(self)
        self.reg._progress(self.id, self.done, self.total, None, self.label)

    def __enter__(self):
        if self.reg is not None and self.after <= 0:
            self.id = self.reg._track_open(self)
        return self

    def __exit__(self, et, e, tb):
        if self.reg is not None and self.id is not None:
            self.reg._track_close(self.id, None if et is None else (str(e)[:300] or et.__name__))
        return False


class Jobs:
    def __init__(self, db: Db):
        self.store = Store(db, "jobs")
        self.kinds: dict[str, Kind] = {}
        self.listeners: list[Callable[[dict], None]] = []     # called with every event (from any thread)
        self.lock = threading.RLock()
        self.cv = threading.Condition(self.lock)
        self.mem: dict[str, dict] = {}                         # live copy of every job (the store lags by ≤ SAVE_EVERY)
        self._saved: dict[str, float] = {}
        self._told: dict[str, float] = {}
        self._threads: list[threading.Thread] = []
        self._stop = False
        self.running = False                                   # workers started (else: run_now on the caller's thread)
        for jid, j in self.store.all().items():
            self.mem[jid] = j

    # ---- set-up
    def kind(self, name: str, run: Callable, **opts) -> Kind:
        k = Kind(name, run, **opts)
        if k.lane not in LANES:
            raise ValueError(f"unknown lane {k.lane}")
        self.kinds[name] = k
        self._restarted(k)
        return k

    def _restarted(self, k: Kind):
        """Jobs of this kind that were running when the server stopped."""
        for j in list(self.mem.values()):
            if j["kind"] == k.name and j["state"] == "running":
                if k.resumable:
                    j["state"] = "queued"
                else:
                    j.update(state="failed", error="Stopped by a restart", finished=time.time())
                self._write(j)

    def start_workers(self, lanes: dict | None = None):
        self.running = True
        for lane, n in (lanes or LANES).items():
            for i in range(n):
                t = threading.Thread(target=self._worker, args=(lane,), name=f"jobs-{lane}-{i}", daemon=True)
                t.start()
                self._threads.append(t)

    def stop(self):
        with self.cv:
            self._stop = True
            self.running = False
            self.cv.notify_all()

    # ---- starting and controlling
    def submit(self, kind: str, owner: str | None, title: str, params: dict | None = None,
               total: int | None = None, unit: str = "items") -> dict:
        k = self.kinds[kind]
        now = time.time()
        j = {"id": secrets.token_hex(5), "kind": kind, "owner": owner, "system": owner is None, "title": title,
             "state": "queued", "done": 0, "total": total, "unit": unit, "label": None, "created": now,
             "started": None, "finished": None, "error": None, "result": None, "stopping": None,
             "canPause": k.pause, "canCancel": k.cancel, "params": params or {}, "data": {}}
        with self.cv:
            self.mem[j["id"]] = j
            self._write(j)
            self.cv.notify_all()
        self._tell(j, force=True)
        return self.public(j)

    def control(self, jid: str, action: str, user: dict | None = None):
        """pause / resume / cancel / dismiss. KeyError: no such job (or not yours); ValueError: not now."""
        with self.cv:
            j = self.mem.get(jid)
            if not j or not self._may(j, user):
                raise KeyError(jid)
            st = j["state"]
            # a running job keeps running until it notices (at its next check): until then it is "stopping"
            if action == "pause" and st == "running" and j["canPause"] and not j.get("stopping"):
                j["stopping"] = "pause"
            elif action == "pause" and st == "queued" and j["canPause"]:
                j["state"] = "paused"
            elif action == "resume" and st == "running" and j.get("stopping") == "pause":
                j["stopping"] = None
            elif action == "resume" and st == "paused":
                j["state"] = "queued"
            elif action == "cancel" and st == "running" and j["canCancel"]:
                j["stopping"] = "cancel"
            elif action == "cancel" and st in ("queued", "paused") and j["canCancel"]:
                j["state"] = "cancelled"
                j["finished"] = time.time()
            elif action == "dismiss" and st in FINISHED:
                self.mem.pop(jid, None)
                self.store.delete(jid)
                self._tell({"id": jid, "gone": True, "ownerId": j["owner"]}, force=True)
                return
            else:
                raise ValueError(f"can't {action} a {st} job")
            self._write(j)
            self.cv.notify_all()
        self._tell(j, force=True)

    @staticmethod
    def _may(j: dict, user: dict | None) -> bool:
        if user is None:
            return True                                      # the server itself
        return j["owner"] == user["id"] or (j["owner"] is None and bool(user.get("admin")))

    # ---- reading
    @staticmethod
    def public(j: dict) -> dict:
        out = {k: v for k, v in j.items() if k not in PRIVATE}
        out["eta"] = Jobs.eta(j)
        return out

    @staticmethod
    def eta(j: dict, now: float | None = None) -> int | None:
        if j["state"] != "running" or not j.get("started") or not j.get("total") or not j.get("done"):
            return None
        spent = (now or time.time()) - j["started"]
        return max(0, round(spent / j["done"] * (j["total"] - j["done"])))

    def list(self, user: dict | None = None) -> list[dict]:
        """Your jobs and the system's, oldest first."""
        self.tidy()
        with self.lock:
            js = [j for j in self.mem.values() if user is None or j["owner"] in (None, user["id"])]
            return [self.public(j) for j in sorted(js, key=lambda j: j["created"])]

    def get(self, jid: str) -> dict | None:
        with self.lock:
            j = self.mem.get(jid)
            return self.public(j) if j else None

    def visible(self, event: dict, user: dict) -> bool:
        """May this account see this event? (job events: own and system jobs)"""
        if event.get("type") != "job":
            return True
        with self.lock:
            j = self.mem.get(event["job"]["id"])
        owner = j["owner"] if j else event["job"].get("ownerId")
        return owner in (None, user["id"])

    def tidy(self, now: float | None = None):
        now = now or time.time()
        with self.lock:
            for j in list(self.mem.values()):
                if j["state"] in FINISHED and j.get("finished"):
                    if now - j["finished"] > (SYSTEM_KEEP if j["system"] or j.get("memory") else KEEP):
                        self.mem.pop(j["id"], None)
                        self.store.delete(j["id"])

    # ---- running
    def _next(self, lane: str) -> dict | None:
        for j in sorted(self.mem.values(), key=lambda j: j["created"]):
            k = self.kinds.get(j["kind"])
            if j["state"] == "queued" and k and k.lane == lane and (not k.ready or k.ready(j)):
                return j
        return None

    def _worker(self, lane: str):
        if any(k.low for k in self.kinds.values() if k.lane == lane):
            _low_priority()
        while True:
            with self.cv:
                if self._stop:
                    return
                j = self._next(lane)
                if not j:
                    self.cv.wait(5)                          # also re-checks `ready` (night-only hours) now and then
                    continue
                j["state"] = "running"
                j["started"] = j["started"] or time.time()
                self._write(j)
            self._tell(j, force=True)
            self.run_one(j)

    def run_one(self, j: dict):
        """Run one job until it's done, paused, cancelled or failed (workers call this; tests may too)."""
        k = self.kinds[j["kind"]]
        ctx = Ctx(self, j["id"], j["params"], j.get("data") or {})
        state, error, result = "done", None, None
        token = current.set(ctx)
        try:
            result = k.run(ctx)
        except Paused:
            state = "paused"
        except Cancelled:
            state = "cancelled"
        except Exception as e:  # noqa: BLE001
            log.warning("job %s (%s) failed: %s", j["id"], j["kind"], e)
            state, error = "failed", str(e)[:300] or e.__class__.__name__
        finally:
            current.reset(token)
        with self.cv:
            cur = self.mem.get(j["id"])
            if not cur:
                return
            if state == "paused" and cur.get("stopping") == "cancel":
                state = "cancelled"
            cur["state"] = state
            cur["stopping"] = None
            cur["error"] = error
            if result is not None:
                cur["result"] = result
            if state == "done" and cur.get("total"):
                cur["done"] = cur["total"]
            if state in FINISHED:
                cur["finished"] = time.time()
                cur["label"] = None
            self._write(cur)
            self.cv.notify_all()
        self._tell(cur, force=True)

    def run_now(self, jid: str):
        """Run a queued job on the calling thread (tests, or work that should happen right here)."""
        with self.cv:
            j = self.mem[jid]
            j["state"] = "running"
            j["started"] = j["started"] or time.time()
            self._write(j)
        self.run_one(j)
        return self.get(jid)

    def wait(self, jid: str, timeout: float = 30) -> dict | None:
        end = time.time() + timeout
        with self.cv:
            while True:
                j = self.mem.get(jid)
                if not j or j["state"] in FINISHED or j["state"] == "paused":
                    return self.public(j) if j else None
                left = end - time.time()
                if left <= 0:
                    return self.public(j)
                self.cv.wait(min(left, 0.5))

    # ---- tracked work (see Tracker)
    def track(self, kind: str, title: str, owner: str | None = None, unit: str = "items", total=None,
              after: float = 1.0, ref: str | None = None) -> Tracker:
        return Tracker(self, kind, title, owner, unit, total, after, ref)

    def _track_open(self, t: Tracker) -> str:
        now = time.time()
        j = {"id": secrets.token_hex(5), "kind": t.kind, "owner": t.owner, "system": t.owner is None, "title": t.title,
             "state": "running", "done": t.done, "total": t.total, "unit": t.unit, "label": t.label, "created": t.t0,
             "started": t.t0, "finished": None, "error": None, "result": None, "stopping": None,
             "canPause": False, "canCancel": False, "params": {}, "data": {}, "memory": True, "ref": t.ref}
        with self.cv:
            self.mem[j["id"]] = j
        self._tell(j, force=True)
        return j["id"]

    def _track_close(self, jid: str, error: str | None):
        with self.cv:
            j = self.mem.get(jid)
            if not j:
                return
            j.update(state="failed" if error else "done", error=error, finished=time.time(), label=None)
            if not error and j.get("total"):
                j["done"] = j["total"]
            self.cv.notify_all()
        self._tell(j, force=True)

    # ---- what a job calls (through ctx)
    def _state(self, jid: str) -> str | None:
        with self.lock:
            j = self.mem.get(jid)
            if not j:
                return "cancelled"
            return {"pause": "paused", "cancel": "cancelled"}.get(j.get("stopping"), j["state"])

    def _progress(self, jid, done, total, unit, label):
        with self.lock:
            j = self.mem.get(jid)
            if not j:
                return
            j["done"] = done
            if total is not None:
                j["total"] = total
            if unit:
                j["unit"] = unit
            if label is not None:
                j["label"] = label
            if time.time() - self._saved.get(jid, 0) >= SAVE_EVERY:
                self._write(j)
        self._tell(j)

    def _save_data(self, jid, data):
        with self.lock:
            j = self.mem.get(jid)
            if j:
                j["data"] = dict(data)
                self._write(j)

    # ---- storage and events
    def _write(self, j: dict):
        self._saved[j["id"]] = time.time()
        if not j.get("memory"):                                # tracked work isn't kept across restarts
            self.store.put(j["id"], j)

    def _tell(self, j: dict, force: bool = False):
        now = time.time()
        if not force and now - self._told.get(j["id"], 0) < NOTIFY_EVERY:
            return
        self._told[j["id"]] = now
        if j.get("gone"):
            ev = {"type": "job", "job": j}
        else:
            ev = {"type": "job", "job": {**self.public(j), "ownerId": j["owner"]}}
        self.emit(ev)

    def emit(self, event: dict):
        for fn in list(self.listeners):
            try:
                fn(event)
            except Exception as e:  # noqa: BLE001
                log.debug("job listener: %s", e)


def _low_priority():
    """Background work shouldn't make reading slower (Linux: per thread)."""
    try:
        import os
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except Exception:  # noqa: BLE001
        pass
