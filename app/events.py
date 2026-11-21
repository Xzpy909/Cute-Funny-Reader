"""The live stream (GET /api/events): one Server-Sent Events connection per open tab.

Anything on the server (a job thread, the library watcher) calls `hub.publish(event)`; each connected tab
gets the events its account may see. A tab that can't keep up loses old events, never blocks the server.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Callable

PING = 15                     # seconds between keep-alive comments (proxies drop quiet connections)
QUEUE = 500                   # events waiting per tab before the oldest are dropped


class Hub:
    def __init__(self, visible: Callable[[dict, dict], bool] = lambda ev, user: True):
        self.visible = visible
        self._subs: set = set()
        self._lock = threading.Lock()
        self.closed = False

    def publish(self, event: dict):
        """From any thread."""
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            if self.visible(event, sub.user):
                try:
                    sub.loop.call_soon_threadsafe(_put, sub.q, event)
                except RuntimeError:          # that tab's loop is gone
                    self._drop(sub)

    def close(self):
        """The server is stopping: end every stream (an open stream would hold up a graceful shutdown)."""
        self.closed = True
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            try:
                sub.loop.call_soon_threadsafe(_put, sub.q, None)
            except RuntimeError:
                pass

    def _drop(self, sub):
        with self._lock:
            self._subs.discard(sub)

    @property
    def count(self) -> int:
        return len(self._subs)

    async def stream(self, user: dict, hello: dict, disconnected: Callable):
        """The body of one SSE response: `hello` first, then events as they come."""
        q: asyncio.Queue = asyncio.Queue(QUEUE)
        sub = _Sub(asyncio.get_running_loop(), q, user)
        with self._lock:
            self._subs.add(sub)
        try:
            yield "retry: 3000\n\n"
            yield sse(hello)
            while not self.closed:
                try:
                    ev = await asyncio.wait_for(q.get(), PING)
                except asyncio.TimeoutError:
                    if await disconnected():
                        break
                    yield ": ping\n\n"
                    continue
                if ev is None:                    # closing
                    break
                yield sse(ev)
        finally:
            self._drop(sub)


class _Sub:
    __slots__ = ("loop", "q", "user")

    def __init__(self, loop, q, user):
        self.loop, self.q, self.user = loop, q, user


def _put(q: asyncio.Queue, event: dict):
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(event)


def sse(event: dict) -> str:
    if event.get("type") == "job":                        # who owns it is the server's business
        event = {**event, "job": {k: v for k, v in event["job"].items() if k != "ownerId"}}
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
