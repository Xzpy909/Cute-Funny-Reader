# Background jobs

One system for everything that runs longer than a click: ✨ Optimize, big moves / deletes / renames, scans,
the trash mover and JPEG XL / HEIC conversion. Every one of them shows up the same way — in the working pill
and in the Jobs panel — with real progress, and the ones that can be paused or cancelled can be.

## A job

| field | meaning |
|---|---|
| `id` | short random id |
| `kind` | what it does: `optimize`, `move`, `delete`, `rename`, `scan`, `trash`, `transcode`, … |
| `owner` | the account that started it; `null` for system jobs (scans, the trash mover, …) |
| `title` | what the person reads: "Moving 12 series to Comics" |
| `state` | `queued` → `running` → `done` / `failed` / `cancelled`; `paused` from queued or running |
| `done`, `total`, `unit` | progress: "12 of 340 files" (`total` may be unknown: `null`) |
| `label` | the item being worked on right now ("Starfall · Ch. 3") |
| `created`, `started`, `finished` | times (seconds) |
| `eta` | seconds left, from the speed so far (only once something is done) |
| `error` | why it failed |
| `canPause`, `canCancel` | what the buttons may offer for this kind |
| `system` | `true` for jobs nobody started (shown smaller, cleared by themselves) |

The work a job still has to do lives in `params` and `data` (both private to the server): `params` is what it
was started with, `data` is what the job saved so far (e.g. the ids already moved). That is what lets a job
continue after a pause or a restart.

## The registry

`app/jobs.py`, table `jobs` in `config/reader.db` (one row per job, like every other store).

- **Kinds are registered once** at start: `jobs.kind("move", run, lane="user", resumable=True, pause=True)`.
  `run(ctx)` does the work.
- **Lanes, not one queue.** Each lane has its own workers, so your own actions never wait behind a long
  Optimize run:
  - `user` — what someone just asked for (moves, deletes, renames): 2 workers
  - `optimize` — ✨ Optimize: 1 worker, low CPU priority, keeps its night-only hours
  - `system` — scans, the trash mover, JPEG XL / HEIC conversion: 1 worker
  Inside a lane: oldest first.
- **Restart:** a job that was running goes back to `queued` if its kind is `resumable` (it carries on from its
  `data`), otherwise it is marked `failed` ("Stopped by a restart"). Queued and paused jobs just stay.
- **Clean-up:** finished system jobs disappear after a minute; finished jobs of a person stay until dismissed
  (or 7 days).

## Inside a job: `ctx`

```python
def run(ctx):
    for i, sid in enumerate(ctx.params["ids"]):
        if sid in ctx.data.get("moved", []):
            continue                      # done before a pause / restart
        ctx.check()                       # raises when paused or cancelled
        ctx.progress(i, len(ctx.params["ids"]), label=name_of(sid))
        move(sid)
        ctx.save(moved=ctx.data.get("moved", []) + [sid])
```

- `ctx.check()` — the only place a job stops: between items, never halfway through one. Pause raises
  `Paused` (the job goes back to the lane when resumed and starts again with its `data`), cancel raises
  `Cancelled` (the job may tidy up in a `finally`).
- `ctx.progress(done, total=None, unit=None, label=None)` — the one progress callback. It updates memory at
  once and the database at most every 2 seconds (progress shouldn't cost a write per file).
- `ctx.save(**data)` — keeps what resuming needs, written at once.
- A return value is kept as `result` ("Saved 1.2 GB"); an exception fails the job with its message.

## Controls

`POST /api/jobs/{id}/{pause|resume|cancel|dismiss}` — for your own jobs (the admin may also control system
jobs). Pause and cancel only flip the state; the job notices at its next `ctx.check()`.

## Live updates: one stream

`GET /api/events` — Server-Sent Events. One connection per open tab carries:

- `job` — a job changed (sent at most ~4 times a second per job)
- `library` — the library changed (new `rev`), so the page reloads what it shows
- a comment every 15 s so proxies keep the connection open

You see your own jobs and system jobs. If the stream can't connect (some reverse proxies buffer it), the page
falls back to polling `GET /api/jobs` and `/api/status`.

## Order of the work (do.txt, Part 3)

3. this design · 4. the core (`app/jobs.py`, `/api/jobs`, `/api/events`, tests) · 5. ✨ Optimize moves onto it ·
6. big operations become jobs · 7. scans, trash mover, transcoding report as system jobs · 8. the frontend
reads one jobs store fed by the stream · 9. README.
