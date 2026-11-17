"""Upload log — /config/logs/uploads-YYYY-MM.log, one short entry per drop.

Files that went in fine are only counted ("42 out of 43 uploaded without problems"); every file that
didn't gets a line of its own with the reason, so a failure can be traced after the toast is gone.

The browser marks every upload of one drop with the same batch id and reports the end of the drop
(plus what only it knows: cancelled files, network errors, files skipped on purpose). A drop whose end
never arrives (tab closed mid-way) is written anyway once it has been quiet for STALE seconds.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

log = logging.getLogger("cfreader.uploads")
STALE = 30 * 60
BATCH_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def size_text(n: int | None) -> str:
    if not n:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def damage_detail(path, entry: str) -> str:
    """What exactly is wrong with one entry of a zip — read again only when the upload is refused anyway.
    Same size but another checksum = bytes changed; unpacking that stops early = cut-off / scrambled data."""
    try:
        with zipfile.ZipFile(path) as z:
            if entry not in z.namelist():
                return ""
            i = z.getinfo(entry)
            crc = n = 0
            with z.open(i) as f:
                f._expected_crc = None            # read to the end without the check raising, then compare ourselves
                try:
                    while chunk := f.read(1 << 20):
                        crc = zlib.crc32(chunk, crc)
                        n += len(chunk)
                except Exception as e:  # noqa: BLE001
                    return f"unpacking stopped after {n:,} of {i.file_size:,} bytes ({e})"
            if n != i.file_size:
                return f"unpacks to {n:,} bytes, the archive says {i.file_size:,}"
            return f"stored checksum {i.CRC:08x}, content gives {crc:08x} ({i.file_size:,} bytes, same size — the bytes themselves differ)"
    except Exception as e:  # noqa: BLE001
        return f"couldn't inspect it ({e})"


class UploadLog:
    def __init__(self, folder: Path):
        self.folder = folder
        self.batches: dict[str, dict] = {}
        self.lock = threading.Lock()

    # ---- recording -------------------------------------------------------------------------------
    def record(self, batch: str | None, *, lib: str, user: str, name: str, state: str,
               sent: int = 0, announced: int = 0, why: str = "", detail: str = ""):
        """One file's outcome. state: ok | skip (already there) | err | cancel."""
        f = {"name": name, "state": state, "sent": sent, "announced": announced, "why": why, "detail": detail}
        if state == "err":
            log.warning("upload failed: %s → %s: %s %s", name, lib, why, detail)
        if not batch or not BATCH_RE.match(batch):     # a lone upload (API, old page): an entry of its own
            self._write({"lib": lib, "user": user, "start": time.time(), "files": [f]}, {})
            return
        now = time.time()
        with self.lock:
            b = self.batches.setdefault(batch, {"lib": lib, "user": user, "start": now, "files": []})
            b["seen"] = now
            b["files"].append(f)
        self.flush_stale()

    def finish(self, batch: str, client: dict | None = None, *, lib: str = "", user: str = ""):
        """The browser says the drop is over; `client` holds what never reached the server."""
        if not BATCH_RE.match(batch or ""):
            return
        with self.lock:
            b = self.batches.pop(batch, None)
        client = client or {}
        if b is None:                                   # nothing reached the server (all cancelled / offline…)
            if not any(client.get(k) for k in ("failed", "cancelled", "ignored", "skipped")):
                return
            b = {"lib": lib, "user": user, "start": time.time(), "files": []}
        self._write(b, client)
        self.flush_stale()

    def flush_stale(self):
        cut = time.time() - STALE
        with self.lock:
            old = [k for k, b in self.batches.items() if b.get("seen", b["start"]) < cut]
            gone = [self.batches.pop(k) for k in old]
        for b in gone:
            self._write(b, {"unfinished": True})

    # ---- writing ---------------------------------------------------------------------------------
    @staticmethod
    def entry(b: dict, client: dict) -> str:
        files = b["files"]
        ok = sum(f["state"] == "ok" for f in files)
        there = sum(f["state"] == "skip" for f in files)
        server_err = [f for f in files if f["state"] == "err"]
        client_err = [f for f in client.get("failed") or [] if isinstance(f, dict)][:500]
        cancelled = sum(f["state"] == "cancel" for f in files)
        cancelled = max(cancelled, int(client.get("cancelled") or 0))
        failed = len(server_err) + len(client_err)
        total = ok + there + failed + cancelled
        when = datetime.fromtimestamp(b["start"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        head = f"{when} · library “{b['lib']}”" + (f" · {b['user']}" if b.get("user") else "")
        good = ok + there
        line = f"  {good} out of {total} uploaded without problems" if total else "  nothing was uploaded"
        if there:
            line += f" ({there} already there)"
        if failed:
            line += f" · {failed} failed"
        if cancelled:
            line += f" · {cancelled} cancelled"
        out = [head, line]
        extra = [f"{n} {what}" for n, what in ((int(client.get("ignored") or 0), "ignored (not comics / images / videos)"),
                                                  (int(client.get("skipped") or 0), "skipped by your choice")) if n]
        if extra:
            out.append("  " + " · ".join(extra))
        for f in server_err:
            got = f" · received {size_text(f['sent'])}" + (f" of {size_text(f['announced'])}" if f["announced"] else "")
            if f["announced"] and f["sent"] < f["announced"]:
                got += " — ARRIVED INCOMPLETE"
            out.append(f"  ✗ {f['name']}: {f['why']}{got}")
            if f.get("detail"):
                out.append(f"      {f['detail']}")
        for f in client_err:
            out.append(f"  ✗ {str(f.get('name', '?'))[:300]}: {str(f.get('why', '?'))[:500]} (in the browser — never reached the server)")
        if client.get("unfinished"):
            out.append("  (the page never reported the end of this drop — closed or reloaded mid-way?)")
        return "\n".join(out) + "\n\n"

    def _write(self, b: dict, client: dict):
        text = self.entry(b, client)
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / f"uploads-{datetime.now():%Y-%m}.log"
            with self.lock, open(path, "a", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as e:
            log.warning("couldn't write the upload log: %s", e)
