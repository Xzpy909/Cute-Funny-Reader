"""While the server is away (starting, restarting after update.bat) the browser shows "starting…" — and carries
on by itself once the server answers. Real server, real browser; skipped without Playwright / Chrome."""
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from test_browser import EMAIL, ROOT, cbz

pw_api = pytest.importorskip("playwright.sync_api")


def test_starting_screen_while_the_server_is_away(tmp_path):
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "LIBRARY_DIR": str(tmp_path / "data"), "CONFIG_DIR": str(tmp_path / "config")}
    start = lambda: subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)
    base, password = f"http://127.0.0.1:{port}", secrets.token_urlsafe(12)

    def up():
        for _ in range(150):
            try:
                urllib.request.urlopen(base + "/api/auth/state", timeout=2); return
            except OSError:
                time.sleep(.1)
        raise AssertionError("server didn't start")
    proc = start(); up()
    with pw_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            exe = shutil.which("google-chrome") or shutil.which("chromium")
            if not exe:
                pytest.skip("no Chrome")
            b = p.chromium.launch(executable_path=exe)
        try:
            pg = b.new_page()
            pg.goto(base + "/")
            pg.evaluate("""async ([e, p]) => { await fetch('/api/auth/setup', {method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: e, password: p})}); }""", [EMAIL, password])
            pg.reload()
            pg.wait_for_function("navigator.serviceWorker.controller || (navigator.serviceWorker.ready.then(() => location.reload()), false)", timeout=15000)
            pg.wait_for_selector("#btnSettings")

            proc.terminate(); proc.wait(5)                          # the server goes away under an open page
            pg.evaluate("refreshStatus()")
            pg.wait_for_selector("#starting:not([hidden]) h1:has-text('Reconnecting')", timeout=5000)
            if os.environ.get("SHOT"): pg.wait_for_timeout(4500); pg.screenshot(path=os.environ["SHOT"] + "-1.png")

            pg.goto(base + "/")                                     # a fresh page load while it's down
            pg.wait_for_selector("text=The reader is starting", timeout=5000)
            if os.environ.get("SHOT"): pg.wait_for_timeout(3500); pg.screenshot(path=os.environ["SHOT"] + "-2.png")

            proc = start(); up()                                    # back: the page continues by itself
            pg.wait_for_selector("#btnSettings", timeout=15000)
            assert pg.locator("#auth").is_hidden()                  # still signed in
        finally:
            b.close()
            proc.terminate(); proc.wait(5)


def test_slow_first_load_says_the_library_is_coming(tmp_path):
    """Signed in, but the library takes a while to arrive: "Loading your library…" instead of an empty page."""
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "LIBRARY_DIR": str(tmp_path / "data"), "CONFIG_DIR": str(tmp_path / "config")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)
    base, password = f"http://127.0.0.1:{port}", secrets.token_urlsafe(12)
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(base + "/api/auth/state", timeout=2); break
            except OSError:
                time.sleep(.1)
        with pw_api.sync_playwright() as p:
            exe = shutil.which("google-chrome") or shutil.which("chromium")
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
            try:
                pg = b.new_page()
                pg.goto(base + "/")
                pg.evaluate("""async ([e, p]) => { await fetch('/api/auth/setup', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email: e, password: p})}); }""", [EMAIL, password])
                held = []
                pg.route("**/api/library*", lambda route: held.append(route))                     # the library is slow to come
                pg.reload()
                pg.wait_for_function("document.body.classList.contains('booting')", timeout=4000)
                pg.wait_for_function("getComputedStyle(document.querySelector('.app')).visibility === 'hidden'", timeout=3000)   # no empty skeleton
                pg.wait_for_selector("#starting:not([hidden]) h1:has-text('Loading your library')", timeout=4000)
                assert held
                for r in held: r.continue_()
                pg.unroute("**/api/library*")
                pg.wait_for_selector("#starting", state="hidden", timeout=10000)                   # …and gone once it's there
                assert pg.evaluate("S.loaded") and pg.locator(".app").is_visible()
            finally:
                b.close()
    finally:
        proc.terminate(); proc.wait(5)
