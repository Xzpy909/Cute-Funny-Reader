"""Real clicks in a real browser, against a real server — what the server-side tests can't see.
(Both "cards don't open" bugs lived here.) Skipped when Playwright / Chrome aren't installed."""
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path

import pytest

from conftest import jpeg
from test_epub_open import CH1, CONTAINER, OPF

pw_api = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parent.parent
EMAIL = "test@example.invalid"


def cbz(path: Path, pages: int = 3):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for i in range(pages):
            z.writestr(f"{i + 1:03}.jpg", jpeg(300, 450, ["red", "blue", "green"][i % 3]))


def epub(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip"); z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", OPF); z.writestr("OEBPS/ch1.xhtml", CH1)


def serve(tmp: Path, build, books: int):
    """Start a real server on an empty folder, let `build(call, data_dir)` fill it, wait for the scan."""
    (tmp / "data").mkdir(); (tmp / "config").mkdir()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "LIBRARY_DIR": str(tmp / "data"), "CONFIG_DIR": str(tmp / "config")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
                            cwd=ROOT, env=env)
    base, password = f"http://127.0.0.1:{port}", secrets.token_urlsafe(12)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(method, url, body=None):
        r = urllib.request.Request(base + url, method=method, headers={"Content-Type": "application/json"},
                                   data=json.dumps(body).encode() if body is not None else None)
        return json.loads(opener.open(r, timeout=10).read() or b"null")
    try:
        for _ in range(100):
            try:
                call("GET", "/api/auth/state"); break
            except OSError:
                time.sleep(.1)
        call("POST", "/api/auth/setup", {"email": EMAIL, "password": password})
        build(call, tmp / "data")
        call("POST", "/api/scan")
        for _ in range(300):
            st = call("GET", "/api/status")
            if st["books"] == books and not st["scanning"]:
                break
            time.sleep(.1)
        assert st["books"] == books, st
        yield base, password
    finally:
        proc.terminate(); proc.wait(5)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    def build(call, data):
        comics = call("POST", "/api/libraries", {"name": "Comics", "type": "comics", "color": "#fff"})
        cos = call("POST", "/api/libraries", {"name": "Cos", "type": "cosplay", "color": "#fff"})
        c, k = data / comics["path"], data / cos["path"]
        cbz(c / "Starfall" / "Starfall 01.cbz"); cbz(c / "Starfall" / "Starfall 02.cbz")
        epub(c / "Test Novel" / "Test Novel v01.epub"); epub(c / "Test Novel" / "Test Novel v02.epub")
        for n in ("Maid", "Beach"):
            cbz(k / "Mirelle" / n / f"{n}.cbz")
        (k / "Mirelle" / ".collection").touch()
    yield from serve(tmp_path_factory.mktemp("browser"), build, 6)


@pytest.fixture(scope="module")
def big_server(tmp_path_factory):
    def build(call, data):
        lib = call("POST", "/api/libraries", {"name": "Big", "type": "comics", "color": "#fff"})
        for i in range(240):                                   # every 7th title is long enough to wrap: uneven rows
            name = f"Series {i:03}" + (" with a much longer title that wraps onto more lines" if i % 7 == 0 else "")
            cbz(data / lib["path"] / name / f"{name} 01.cbz", 1); cbz(data / lib["path"] / name / f"{name} 02.cbz", 1)
    yield from serve(tmp_path_factory.mktemp("big"), build, 480)


@pytest.fixture(scope="module")
def browser():
    with pw_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            exe = os.environ.get("CHROME") or shutil.which("google-chrome") or shutil.which("chromium")
            if not exe:
                pytest.skip("no Chrome / Chromium to drive")
            b = p.chromium.launch(executable_path=exe)
        yield b
        b.close()


def open_page(server, browser, library=None):
    base, password = server
    ctx = browser.new_context(viewport={"width": 1100, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/")
    pg.evaluate("""async ([email, password]) => { await fetch('/api/auth/login', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email, password})}); }""", [EMAIL, password])
    pg.goto(base + "/#/"); pg.reload()
    try:
        pg.wait_for_selector("#rows .card", timeout=8000)                  # Home: rows
        if library:                                                        # most tests work on a library's shelf
            pg.locator(".side [data-lib]", has_text=library).click()
            pg.wait_for_selector("#grid .card", timeout=8000)
    except Exception:
        raise AssertionError(f"no cards: errors={errors} state={pg.evaluate('[!document.getElementById(`auth`).hidden, document.body.innerText.slice(0, 400)]')}")
    yield pg
    assert not errors, errors
    ctx.close()


@pytest.fixture
def page(server, browser):
    yield from open_page(server, browser, "Comics")


@pytest.fixture
def home_page(server, browser):
    yield from open_page(server, browser)


@pytest.fixture
def big_page(big_server, browser):
    yield from open_page(big_server, browser, "Big")


BOOK = "#viewSeries .chgrid [data-open], #viewSeries .blist [data-open]"     # cards or list rows


def click(pg, selector, text=None):
    """A real mouse click in the middle of the cover — where a person clicks (lands on the <img>, not the card)."""
    loc = pg.locator(selector, has_text=text).first if text else pg.locator(selector).first
    loc.wait_for()
    loc.scroll_into_view_if_needed()
    cover = loc.locator(".cover")
    box = (cover.first if cover.count() else loc).bounding_box()
    pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def hash_is(pg, prefix):
    pg.wait_for_function("p => location.hash.startsWith(p)", arg=prefix, timeout=5000)


def test_series_card_opens_its_page_then_a_book(page):
    click(page, "#grid .card[data-series]", "Starfall")
    hash_is(page, "#/series/")
    click(page, BOOK)
    hash_is(page, "#/read/")
    page.wait_for_function("document.querySelector('#spread img.pg')?.naturalWidth > 0")


def test_collection_card_opens_and_its_single_set_opens_the_reader(page):
    page.locator(".side [data-lib]", has_text="Cos").click()
    click(page, "#grid .card[data-collection]", "Mirelle")
    hash_is(page, "#/collection/")
    click(page, "#grid .card[data-series]")
    hash_is(page, "#/read/")


def test_half_visible_card_still_opens(page):
    top = page.locator("#grid .card[data-series]", has_text="Starfall").first.bounding_box()["y"]
    page.set_viewport_size({"width": 1100, "height": int(top + 90)})       # only the top of the card shows
    box = page.locator("#grid .card[data-series]", has_text="Starfall").first.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, top + 50)
    hash_is(page, "#/series/")


def test_cards_open_right_after_scrolling(page):
    page.mouse.move(600, 500); page.mouse.wheel(0, 200); page.mouse.wheel(0, -200)
    page.wait_for_timeout(700)
    click(page, "#grid .card[data-series]", "Starfall")
    hash_is(page, "#/series/")


def test_epub_opens_and_shows_text(page):
    click(page, "#grid .card[data-series]", "Test Novel")
    hash_is(page, "#/series/")
    click(page, BOOK)
    hash_is(page, "#/read/")
    page.wait_for_function("document.getElementById('prose')?.textContent.includes('Hello from the first chapter.')")


def test_reader_keys_turn_pages_and_escape_closes(page):
    click(page, "#grid .card[data-series]", "Starfall")
    hash_is(page, "#/series/")
    click(page, BOOK)
    page.wait_for_function("document.querySelector('#spread img.pg')?.naturalWidth > 0")
    first = page.evaluate("document.querySelector('#spread img.pg').src")
    page.keyboard.press("ArrowRight")
    page.wait_for_function("s => document.querySelector('#spread img.pg')?.src !== s", arg=first)
    page.keyboard.press("Escape")
    hash_is(page, "#/series/")


def test_mark_read_from_the_menu(page):
    click(page, "#grid .card[data-series]", "Starfall")
    hash_is(page, "#/series/")
    page.locator(BOOK).first.click(button="right")                       # right-click opens the item menu
    page.locator("#menu [data-mact='read']").click()
    page.wait_for_function("/READ\\b|Finished/.test(document.querySelector('#viewSeries').innerText)")
    page.locator(BOOK).first.click(button="right")
    assert "unread" in page.locator("#menu [data-mact='read']").inner_text().lower()


def test_a_change_only_touches_its_own_card(page):
    """Redrawing the shelf after a change keeps every other card (and the scroll position) as it is."""
    page.evaluate("document.querySelectorAll('#grid .card').forEach((c, i) => c.__mark = i)")
    page.locator("#grid .card[data-series]", has_text="Starfall").first.click(button="right")
    page.locator("#menu [data-mact='sread']").click()                       # mark the whole series read
    page.wait_for_function("[...document.querySelectorAll('#grid .card[data-series]')].some(c => /Starfall/.test(c.innerText) && c.__mark === undefined)")
    kept = page.evaluate("[...document.querySelectorAll('#grid .card')].filter(c => c.__mark !== undefined).length")
    total = page.evaluate("document.querySelectorAll('#grid .card').length")
    assert kept == total - 1                                                 # only Starfall's card was re-made

    page.evaluate("document.querySelectorAll('#grid .card').forEach((c, i) => c.__mark = i)")
    page.evaluate("load()")                                                  # a refresh with nothing new
    page.wait_for_timeout(600)
    assert page.evaluate("[...document.querySelectorAll('#grid .card')].every(c => c.__mark !== undefined)")


def test_patching_handles_reorder_insert_and_remove(page):
    out = page.evaluate("""() => {
        const grid = document.getElementById('grid'), key = c => c.dataset.collection || c.dataset.series || c.dataset.open;
        const cards = () => [...grid.querySelectorAll(':scope > .card')];
        const html = cards().map(c => c.outerHTML), before = cards();
        const extra = html[0].replace(/data-(collection|series|open)="[^"]*"/, 'data-series="brand-new"');
        const want = [html[1], extra, html[0]];                    // 1 moved first, a new card, 0 last
        fillGrid(grid, want);
        return { keys: cards().map(key), expect: [key(before[1]), 'brand-new', key(before[0])], reused: key(cards()[0]) === key(before[1]) };
    }""")
    assert out["keys"] == out["expect"] and out["reused"]


def test_too_long_paths_are_listed_with_where_they_are(page):
    """Files Windows won't hand to the browser: each one is named with its folder, and the list can be copied."""
    page.evaluate("""() => {
        dropFailures.push({ path: '/Manga/Doujins 2011/(C80) [Circle Name] A Very Long Title.cbz', err: new Error('x') },
                          { path: '/Manga/Some Long Manga 2.cbz', err: new Error('x') });
        const unreadable = dropFailures.splice(0);
        const where = x => x.path.split('/').filter(Boolean).slice(0, -1).join(' › ');
        UP.rows.push(...unreadable.map(x => ({ f: { size: 0 }, name: x.path.split('/').filter(Boolean).pop(), state: 'err', p: 1,
          msg: 'Path too long', where: where(x) ? 'in ' + where(x) : '', inside: x.path.replace(/^\\//, '') })));
        UP.longPaths = unreadable.map(x => x.path.replace(/^\\//, '').replaceAll('/', '\\\\'));
        UP.rows.push({ f: { size: 0 }, state: 'skip', msg: '', p: 1, notice: true, name: '2 files Windows wouldn’t let the browser open' });
        renderUploads(true);
    }""")
    page.wait_for_selector("#uploads .up-row.notice [data-uplist='save']")
    if os.environ.get("SHOT"): page.locator("#uploads").screenshot(path=os.environ["SHOT"])
    text = page.inner_text("#uploads .up-list")
    assert "in Manga › Doujins 2011" in text and "Path too long" in text
    with page.expect_download() as d:
        page.click("#uploads [data-uplist='save']")
    saved = open(d.value.path(), encoding="utf-8").read()
    assert "Manga\\Doujins 2011\\(C80) [Circle Name] A Very Long Title.cbz" in saved and "Manga\\Some Long Manga 2.cbz" in saved


def test_dialogs_fit_short_screens_and_remove_asks_once(page):
    page.set_viewport_size({"width": 1100, "height": 560})               # a short laptop screen
    page.evaluate("openLibModal(S.libraries[0])")
    page.wait_for_selector("#libForm #btnRemoveLib")
    fits = page.evaluate("""() => { const r = document.getElementById('libForm').getBoundingClientRect();
        const save = [...document.querySelectorAll('#libForm .formfoot button')].pop().getBoundingClientRect();
        return [r.top >= 0, r.bottom <= innerHeight, save.bottom <= innerHeight] }""")
    assert fits == [True, True, True]                                   # the dialog and its buttons are on screen
    if os.environ.get("SHOT"): page.screenshot(path=os.environ["SHOT"] + "-1.png")
    page.click("#libForm #btnRemoveLib")
    page.wait_for_selector("#libForm .rmbox [data-rmgo]")
    if os.environ.get("SHOT"): page.wait_for_timeout(500); page.screenshot(path=os.environ["SHOT"] + "-2.png")
    visible = page.evaluate("[...document.querySelectorAll('#libForm button')].filter(b => b.offsetParent && /Remove library/.test(b.textContent)).length")
    assert visible == 1                                                  # one "Remove library", not two
    page.click("#libForm [data-rmcancel]")
    assert page.is_visible("#libForm #btnRemoveLib")                     # cancelled: the normal buttons are back


def test_big_shelf_keeps_only_nearby_cards_on_the_page(big_page):
    pg = big_page
    count = lambda: pg.evaluate("document.querySelectorAll('#grid > .card').length")
    shown = lambda: pg.evaluate("""() => { const m = document.getElementById('main').getBoundingClientRect();
        return [...document.querySelectorAll('#grid > .card')].filter(c => { const r = c.getBoundingClientRect(); return r.bottom > m.top && r.top < m.bottom; }).length }""")
    scroll = lambda y: (pg.evaluate("y => { const m = document.getElementById('main'); m.style.scrollBehavior = 'auto'; m.scrollTop = y; }", y), pg.wait_for_timeout(600))
    assert pg.evaluate("S.series.length") == 240
    assert 20 <= count() <= 80                                           # not 240
    full = pg.evaluate("document.getElementById('main').scrollHeight")
    assert full > 240 / 6 * 250                                          # the scrollbar still spans the whole shelf

    scroll(full / 2); assert count() <= 80 and shown() >= 6             # the middle: cards there, the rest gone
    scroll(10 ** 7)                                                      # the very end
    assert count() <= 80 and shown() >= 3
    titles = pg.evaluate("[...document.querySelectorAll('#grid > .card .ct')].map(e => e.innerText)")
    last = pg.evaluate("S.seriesById[VG.keys.at(-1).split(':')[1]].name")
    assert any(last in t.replace("\n", "") for t in titles)             # the last series is really there
    assert pg.evaluate("document.getElementById('grid').getBoundingClientRect().bottom <= document.getElementById('main').getBoundingClientRect().bottom + 200")

    scroll(0); assert shown() >= 3                                       # and back at the top (the banner takes most of it)
    assert pg.evaluate("VG.start") == 0 and pg.evaluate("VG.top.hidden")


def test_big_shelf_click_after_scrolling_and_back_keeps_your_place(big_page):
    pg = big_page
    pg.evaluate("() => { const m = document.getElementById('main'); m.style.scrollBehavior = 'auto'; m.scrollTop = 6000; }")
    pg.wait_for_timeout(300)
    box = pg.evaluate("""() => { const m = document.getElementById('main').getBoundingClientRect();
        const c = [...document.querySelectorAll('#grid > .card')].find(c => c.getBoundingClientRect().top > m.top + 40);
        const r = c.querySelector('.cover').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2, c.dataset.series]; }""")
    pg.mouse.click(box[0], box[1])
    hash_is(pg, "#/series/" + box[2])
    pg.go_back()
    pg.wait_for_function("document.getElementById('viewHome').classList.contains('on')")
    pg.wait_for_timeout(400)
    assert abs(pg.evaluate("document.getElementById('main').scrollTop") - 6000) < 300      # where you were
    assert pg.evaluate("k => !!document.querySelector(`#grid > .card[data-series='${k}']`)", box[2])


def test_fade_in_is_dropped_once_played(page):
    page.wait_for_timeout(1500)
    left = page.evaluate("document.getAnimations().filter(a => a.animationName === 'rise').length")
    assert left == 0


def test_cards_have_no_dots_and_open_their_menu_by_right_click_or_long_press(page):
    assert page.locator("#grid .card .more, #grid .card [data-more]").count() == 0
    page.locator("#grid .card[data-series]", has_text="Starfall").first.click(button="right")
    page.wait_for_selector("#menu.on [data-mact='rename']")
    page.keyboard.press("Escape"); page.mouse.click(5, 5)
    page.wait_for_function("!document.getElementById('menu').classList.contains('on')")
    # a long press on a touch screen
    box = page.locator("#grid .card[data-series]", has_text="Starfall").first.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 3
    page.evaluate("""([x, y]) => { const el = document.elementFromPoint(x, y);
        el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerType: 'touch', clientX: x, clientY: y })); }""", [x, y])
    page.wait_for_selector("#menu.on [data-mact='rename']", timeout=2000)


def test_library_menu_and_settings_button(page):
    assert page.locator("#btnLibSettings, #btnFx").count() == 0
    page.locator(".side [data-lib]").first.click(button="right")
    page.locator("#menu [data-libmenu='settings']").click()
    page.wait_for_selector("#libModal.open #libForm h3:has-text('Library settings')")
    page.click("#libForm [data-cancel], #libForm .btn-ghost")
    page.click("#btnSettings")
    page.wait_for_selector("#fxPanel.open :text('Smoothness')")


def test_add_library_opens_at_once_even_if_the_folder_list_is_slow(page):
    held = []
    page.route("**/api/folders", lambda route: held.append(route))          # the folder list never answers…
    page.click("#btnAddLib")
    page.wait_for_selector("#libModal.open #libName", timeout=1500)          # …the dialog is there anyway
    box = page.locator("#btnAddLib").bounding_box()                          # an impatient second click, same spot
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(200)
    assert page.locator("#libModal.open").count() == 1                       # still open (and only one)
    for r in held:
        r.fulfill(json={"root": "/data/test", "folders": [{"path": "Old Stuff", "books": 12, "used": False}, {"path": "Comics", "books": 0, "used": True}]})
    page.wait_for_selector("#libSuggest [data-usefolder='Old Stuff']")       # suggestions drop in when they arrive
    assert page.locator("#libSuggest [data-usefolder='Comics']").count() == 0


def test_trash_marks_the_card_and_a_click_restores_it(page):
    starfall = "#grid .card[data-series]:has-text('Starfall')"
    page.locator(starfall).first.click(button="right")
    page.locator("#menu [data-mact='trash']").click()
    page.wait_for_selector(starfall + ".trashed")                               # greyed out, still there
    click(page, starfall)                                                       # a click doesn't open it…
    page.wait_for_selector("#menu.on [data-mact='restore']")                # …it offers to restore
    assert location_hash(page).startswith("#/library/")                     # still on the shelf
    page.keyboard.press("Escape"); page.mouse.click(5, 5)

    page.click("#acctBtn"); page.click("#menu [data-acct='trash']")         # the Trash dialog lists it
    page.wait_for_selector("#trashModal.open .trow")
    assert page.locator("#trashModal .trow").count() == 2                   # Starfall's two books
    page.locator("#trashModal .trow [data-tact='restore']").first.click()
    page.wait_for_function("document.querySelectorAll('#trashModal .trow').length === 1")
    page.locator("#trashModal .trow [data-tact='purge']").first.click()     # deleting for good needs a second click
    assert page.locator("#trashModal .trow").count() == 1
    page.locator("#trashModal .trow [data-tact='restore']").first.click()
    page.wait_for_selector("#trashModal .empty")
    page.click("#trashModal [data-tclose]")
    assert page.locator(starfall + ".trashed").count() == 0


def location_hash(page):
    return page.evaluate("location.hash")


def test_new_is_only_the_latest_upload_of_a_library(page):
    news = lambda: page.evaluate("S.series.filter(s => s.books.some(isNew)).map(s => s.name).sort()")
    page.evaluate("S.progress = {}; buildSeries()")                          # (whatever earlier tests read)
    assert news() == ["Beach", "Maid", "Starfall", "Test Novel"]                 # one scan = one batch: all new
    page.evaluate("""() => { const b = S.series.find(s => s.name === 'Starfall').books[0];
        b.added += 2 * 3600; buildSeries(); renderHome(); }""")              # Starfall 01 arrives two hours later
    assert news() == ["Beach", "Maid", "Starfall"]                               # Test Novel (same library) is now just unread
    assert page.evaluate("S.series.find(s => s.name === 'Starfall').books.filter(isNew).length") == 1
    assert page.evaluate("S.series.find(s => s.name === 'Test Novel').books.every(isUnstarted)")


def test_home_shows_rows_instead_of_one_shelf(home_page):
    pg = home_page
    titles = pg.evaluate("[...document.querySelectorAll('#rows .hrow h2')].map(e => e.textContent)")
    assert "Recently added" in titles and titles.index("Recently added") < len(titles)
    assert not pg.is_visible("#grid") and not pg.is_visible("#chips")
    added = pg.locator("#rows .hrow", has_text="Recently added").locator(".card").count()
    assert added == pg.evaluate("S.series.filter(s => s.books.length && !seriesTrashed(s)).length") >= 3   # sets inside collections too
    click(pg, "#rows .card[data-series]", "Starfall")                            # cards work like on the shelf
    hash_is(pg, "#/series/")
    click(pg, BOOK); hash_is(pg, "#/read/")
    pg.wait_for_function("document.querySelector('#spread img.pg')?.naturalWidth > 0")
    pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(700)
    pg.keyboard.press("Escape"); hash_is(pg, "#/series/")
    pg.locator(".side [data-nav='home']").click()
    pg.wait_for_function("[...document.querySelectorAll('#rows .hrow h2')].some(e => e.textContent === 'Recently read')")
    pg.locator("#rows .hrow", has_text="Recently read").locator("[data-nav='reading']").click()   # "See all" → the full list
    pg.wait_for_selector("#grid .card")
    assert not pg.is_visible("#rows")


def test_cosplay_photo_folders_are_packed_as_zip(page):
    names = page.evaluate("""() => {
      const f = n => new File(['x'], n, { type: 'image/jpeg' });
      const items = ['001.jpg', '002.jpg'].map(n => ({ path: '/Circuit Hunter Mika Normal/' + n, file: f(n) }));
      return { cos: planCosplay(items, {}, {}).map(j => j.name), com: planUploads(items, {}).map(j => j.name) };
    }""")
    assert names["cos"] == ["Circuit Hunter Mika Normal.zip"]
    assert names["com"] == ["Circuit Hunter Mika Normal.cbz"]       # comics libraries keep .cbz


def test_top_bar_scope_and_add(home_page):
    pg = home_page
    assert pg.inner_text("#scopeName") == "Everything"
    assert pg.evaluate("getComputedStyle(document.getElementById('topBar')).backdropFilter").startswith("blur")
    pg.click("#btnScope")
    pg.locator("#topMenu [data-scope]", has_text="Comics").click()
    pg.wait_for_function("location.hash.startsWith('#/library/') && document.getElementById('scopeName').textContent === 'Comics'")
    assert pg.evaluate("document.activeElement.id") == "q"
    pg.click("#btnScope"); pg.locator("#topMenu [data-scope='']").click()
    pg.wait_for_function("!location.hash.startsWith('#/library/')")
    pg.click("#btnTopAdd")                                   # Home with several libraries: asks which one
    assert pg.locator("#topMenu.open [data-addto]").count() >= 2
    pg.keyboard.press("Escape")
    assert not pg.locator("#topMenu.open").count()
    # at every width the buttons stay beside the search, never on top of it
    for w in (1500, 1250, 1100, 1000, 900, 861, 860, 700, 420):
        pg.set_viewport_size({"width": w, "height": 700})
        gap = pg.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
          const a = r('.top .search'), add = r('#btnTopAdd'), gear = r('#btnSettings'), k = r('#btnScope');
          return [add.left - a.right, innerWidth - gear.right, k.right <= a.right, a.width]; }""")
        assert gap[0] >= 8 and gap[1] >= 0 and gap[2] and gap[3] >= 200, (w, gap)
    pg.set_viewport_size({"width": 1400, "height": 760})


def test_optimize_from_the_menu_then_undo(server, browser):
    for pg in open_page(server, browser, "Cos"):
        cos = "#grid .card[data-collection]"
        pg.locator(cos, has_text="Mirelle").first.click(button="right")
        pg.locator("#menu [data-mact=optimize]").click()
        pg.wait_for_selector("#optModal.open .optrow")
        assert "placeholder" in pg.inner_text("#optModal .optnote").lower()
        pg.wait_for_function("document.querySelector('#optModal .est') && !/estimating/.test(document.querySelector('#optModal .est').textContent)")
        assert "2 variants" in pg.inner_text("#optHead") and "−" in pg.inner_text("#optModal .est")
        pg.click("#optModal [data-opt=compare]")
        pg.wait_for_selector("#optCmp img.b:not([hidden])")
        pg.wait_for_function("/AVIF · \\d/.test(document.querySelector('#optCmp .lab.r').textContent)")
        pg.click("#optModal [data-opt=start]")
        pg.wait_for_selector("#jobs.on")
        pg.wait_for_function("OPT.jobs.length && OPT.jobs[0].state === 'done'", timeout=30000)
        pg.wait_for_function("(() => { const bs = Object.values(S.books).filter(b => isCosplay(b.library)); return bs.length === 2 && bs.every(b => b.avif && b.canUndo); })()", timeout=15000)
        assert "Done" in pg.inner_text("#jobs")
        pg.locator(cos, has_text="Mirelle").first.click()
        pg.wait_for_selector("#grid .card .avifpill")
        pg.go_back(); pg.wait_for_selector(cos)
        pg.locator(cos, has_text="Mirelle").first.click(button="right")
        pg.locator("#menu [data-mact=unoptimize]").click()
        pg.wait_for_function("(() => { const bs = Object.values(S.books).filter(b => isCosplay(b.library)); return bs.length === 2 && bs.every(b => !b.avif && !b.canUndo); })()", timeout=15000)
        pg.click("#jobs [data-jact=dismiss]")
        pg.wait_for_selector("#jobs", state="hidden")


def test_zz_nothing_went_missing(home_page):
    names = home_page.evaluate("S.series.map(s => s.name + ':' + s.books.length + (seriesTrashed(s) ? ':trashed' : '')).sort()")
    assert names == ["Beach:1", "Maid:1", "Starfall:2", "Test Novel:2"], names
