'use strict';
/* Cute&Funny Reader — frontend, part 6 of 11: keyboard, buttons and the main click handling.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

/* ======================= EVENTS ======================= */
$$('[data-ico]').forEach(el => el.insertAdjacentHTML('afterbegin', ico(el.dataset.ico)));

// Clicks anywhere on the page: one listener, one table. Each row is [selector, handler(el, e, t), when(el, t)?]:
// rows are tried top to bottom, `el` is the clicked element's closest match, and the first row that matches
// (and whose `when` agrees) handles the click. ORDER MATTERS: tag chips and ⋯ buttons sit inside cards, so they
// come before the cards; selection mode comes before opening. The handlers live with their area:
// 02-state (sidebar), 03-home, 04-series, 05-reader, 07-libraries, 08-uploads, 09-menus, 11-optimize.
let CLICKS;
const clickTable = () => CLICKS ||= [      // built at the first click — every part has loaded by then
  ['[data-tagpop]', clickTagPop],
  ['[data-tag]', clickTag],
  ['[data-more]', clickMore],
  ['[data-collection]', clickCollection],
  ['[data-libback]', clickLibBack],
  ['[data-colback]', clickColBack],
  ['[data-newcol]', clickNewCol],
  ['[data-sersettings]', clickSerSettings],
  ['[data-newseries]', clickNewSeries],
  ['[data-select]', () => toggleSelect(!S.sel)],
  ['[data-selclose]', () => toggleSelect(false)],
  ['[data-selall]', clickSelAll],
  ['[data-selact]', clickSelAct],
  ['[data-view]', clickView],
  ['[data-sortflip]', clickSortFlip],
  ['#grid [data-series]', clickSelectSeries, () => S.sel && S.selMode === 'series'],                    // selecting:
  ['.chgrid [data-open], .blist [data-open]', clickSelectBook, () => S.sel && S.selMode === 'books'],  // toggle, don't open
  ['.card.trashed, .brow.trashed', clickTrashed, () => !S.sel],
  ['[data-mark]', clickMark],
  ['[data-markall]', clickMarkAll],
  ['[data-open]', clickOpen],
  ['[data-series]', clickSeries],
  ['[data-home]', clickHome],
  ['[data-addlib], #btnAddLib', () => openLibModal()],
  ['[data-editlib]', clickEditLib],
  ['[data-pick]', clickPick],
  ['[data-upcancel]', () => cancelUploads()],
  ['[data-uplist]', clickUpList],
  ['[data-upmin]', clickUpMin],
  ['#uploads.min .up-h', clickUpMin, (el, t) => !t.closest('[data-upclose], [data-upcancel]')],
  ['[data-upclose]', clickUpClose],
  ['[data-closemodal]', clickCloseLibModal],
  ['[data-filter]', clickFilter],
  ['[data-nav]', clickFavsNav, el => el.dataset.nav === 'favs'],
  ['[data-nav]', clickStorageNav, el => el.dataset.nav === 'storage'],
  ['[data-favlist]', clickFavList],
  ['[data-favback]', clickFavBack],
  ['[data-newfav]', clickNewFav],
  ['[data-nav]', clickNav],
  ['[data-lib]', clickLib],
  ['[data-go]', clickGo],
  ['#toc [data-ch]', clickTocChapter],
  ['[data-chgo]', clickChapterGo],
  ['[data-finish]', () => showEnd()],
  ['#prose a[href="#"]', clickProseLink],
  ['#prose img', clickProseImage, el => !el.closest('h1,h2')],
  ['[data-endnext]', clickEndNext],
  ['[data-endback]', clickEndBack],
  ['[data-endhome]', clickEndHome],
];
document.addEventListener('click', e => {
  const t = e.target;
  for (const [sel, run, when] of clickTable()) {
    const el = t.closest(sel);
    if (el && (!when || when(el, t))) return run(el, e, t);
  }
});
document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.brow')) { e.preventDefault(); e.target.click(); }
});
$('#q').addEventListener('input', e => { S.q = e.target.value; if (location.hash.startsWith('#/series')) location.hash = S.lib ? `#/library/${S.lib}` : '#/'; else renderHome(); });
$('#sort').addEventListener('change', e => { S.sort = e.target.value; local.set('cf-sort', S.sort); renderHome(); });
$('#btnRescan').onclick = async () => { await api.post('/api/scan'); S.status = { ...S.status, scanning: true }; renderServer(); clearTimeout(pollT); pollT = setTimeout(load, 1500); };

$('#btnBack').onclick = closeReader;
$$('#modeSeg button').forEach(b => b.onclick = () => setMode(b.dataset.mode));
$('#btnGuided').onclick = toggleGuided;
$('#btnFit').onclick = toggleFit;
$('#btnDir').onclick = toggleDir;
$('#btnZoom').onclick = () => toggleZoom();
$('#btnFS').onclick = toggleFS;
$('#btnHelp').onclick = () => $('#help').classList.toggle('open');
$('#btnSettings').onclick = () => { $('#toc').classList.remove('open'); $('#settings').classList.toggle('open'); };
$('#btnToc').onclick = () => { $('#settings').classList.remove('open'); $('#toc').classList.toggle('open'); $('#toc .on')?.scrollIntoView({ block: 'center' }); };
function centreFilm(smooth) {
  const film = $('#film'), b = film.querySelector(`[data-go="${R.idx}"]`);
  if (!b) return;
  const fr = film.getBoundingClientRect(), br = b.getBoundingClientRect();
  film.scrollTo({ left: film.scrollLeft + (br.left + br.width / 2) - (fr.left + fr.width / 2), behavior: smooth ? 'smooth' : 'auto' });
}
$('#btnFilm').onclick = () => {
  const open = $('#bottom').classList.toggle('film-open'); $('#btnFilm').classList.toggle('on', open);
  updateChrome();
  if (open) { centreFilm(false); requestAnimationFrame(() => centreFilm(false)); setTimeout(() => centreFilm(false), 420); }
};
$('#btnPrev').onclick = () => step(R.kind === 'images' && R.rtl ? 1 : -1);
$('#btnNext').onclick = () => step(R.kind === 'images' && R.rtl ? -1 : 1);
$$('#bgSeg button').forEach(b => b.onclick = () => { prefs.bg = b.dataset.bg; applyPrefs(); });
$$('#fontSeg button').forEach(b => b.onclick = () => { prefs.font = b.dataset.font; applyPrefs(); });
$$('#widthSeg button').forEach(b => b.onclick = () => { prefs.width = b.dataset.w; applyPrefs(); });
$$('#lhSeg button').forEach(b => b.onclick = () => { prefs.lh = b.dataset.lh; applyPrefs(); });
$('#fsDown').onclick = () => setFont(-1);
$('#fsUp').onclick = () => setFont(1);
$('#swAmbient').onclick = () => { prefs.ambient = !prefs.ambient; applyPrefs(); };
$('#swAnim').onclick = () => { prefs.anim = !prefs.anim; applyPrefs(); };
$$('.overlay').forEach(o => o.id === 'lightbox'
  ? o.addEventListener('click', e => { if (e.isTrusted) o.classList.remove('open'); })
  : backdropCloses(o, () => o.classList.remove('open')));
document.addEventListener('pointerdown', e => {
  if (!e.target.closest('#settings, #btnSettings')) $('#settings').classList.remove('open');
  if (!e.target.closest('#toc, #btnToc')) $('#toc').classList.remove('open');
});

/* scrubber + peek */
const slider = $('#slider'), peek = $('#peek');
slider.addEventListener('input', () => {
  if (R.kind === 'text') return loadChapter(+slider.value);
  goTo(+slider.value, { dir: Math.sign(+slider.value - R.idx), panel: R.guided ? 0 : undefined });
});
slider.addEventListener('pointermove', e => {
  const r = slider.getBoundingClientRect();
  let f = clamp((e.clientX - r.left) / r.width, 0, 1);
  if (R.kind === 'images' && R.rtl) f = 1 - f;
  const n = R.kind === 'text' ? R.chapters.length : R.pages.length;
  const i = Math.round(f * (n - 1));
  const img = peek.querySelector('img');
  if (R.kind === 'text') { img.style.display = 'none'; peek.querySelector('span').textContent = R.chapters[i]?.title || `Section ${i + 1}`; peek.style.width = '200px'; }
  else if (R.pages[i].video) { img.style.display = 'none'; peek.querySelector('span').textContent = `▶ Video · ${i + 1}`; peek.style.width = '120px'; }
  else { const p = R.pages[i], a = clamp(p.w / p.h, .42, 1.9); img.style.display = ''; img.src = p.thumb; img.style.setProperty('--ar', a); peek.querySelector('span').textContent = `Page ${i + 1}`; peek.style.width = a > 1 ? '180px' : ''; }
  peek.style.left = (e.clientX - $('#slwrap').getBoundingClientRect().left) + 'px';
  peek.classList.add('show');
});
slider.addEventListener('pointerleave', () => peek.classList.remove('show'));

/* stage gestures */
let drag = null, suppressClick = false, wheelLock = 0, wheelT;
let lastPT = 'mouse', lastTap = 0, tapT;
stage.addEventListener('pointerdown', e => { lastPT = e.pointerType; }, true);
stage.addEventListener('pointerdown', e => {
  if (R.kind === 'text' || R.mode === 'webtoon' || e.button !== 0) return;
  drag = { x: e.clientX, y: e.clientY, px: R.px, py: R.py, moved: false };
});
window.addEventListener('pointermove', e => {
  if (e.pointerType === 'mouse' && document.body.classList.contains('reading')) wake();
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (Math.hypot(dx, dy) > 6) drag.moved = true;
  if (R.zoom > 1 && !R.guided && drag.moved) {
    R.px = drag.px + dx; R.py = drag.py + dy;
    $('#spread')?.classList.add('dragging'); applyTransform();
  }
});
window.addEventListener('pointerup', e => {
  if (!drag) return;
  const d = drag; drag = null;
  $('#spread')?.classList.remove('dragging');
  if (!d.moved) return;
  suppressClick = true; setTimeout(() => suppressClick = false, 0);
  if (R.zoom === 1) {
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) step(((dx < 0) !== R.rtl) ? 1 : -1);
  }
});
stage.addEventListener('click', e => {
  if (suppressClick || e.target.closest('a, .chnav, #prose img, .vbig')) return;
  if (lastPT !== 'mouse') return touchTap(e);
  if (R.kind === 'text') { if (!getSelection().toString()) toggleUI(); return; }
  if (R.mode === 'webtoon') return toggleUI();
  if (R.zoom > 1) return;
  const f = e.clientX / innerWidth;
  if (f < .3) step(R.rtl ? 1 : -1);
  else if (f > .7) step(R.rtl ? -1 : 1);
  else if ($('#vid')) toggleVid();
  else toggleUI();
});
// Touch: edge taps turn pages, a single centre tap shows / hides the controls,
// a double tap zooms (on a video: play / pause). Swipes never wake the controls.
function touchTap(e) {
  const f = e.clientX / innerWidth, flow = R.kind === 'text' || R.mode === 'webtoon';
  if (!flow && R.zoom <= 1 && (f < .3 || f > .7)) return step((f < .3) !== R.rtl ? -1 : 1);
  if (flow) return toggleUI();
  const now = Date.now(), x = e.clientX, y = e.clientY;
  clearTimeout(tapT);
  if (now - lastTap < 300) { lastTap = 0; return $('#vid') ? toggleVid() : toggleZoom(x, y); }
  lastTap = now;
  tapT = setTimeout(toggleUI, 300);                  // wait: it might become a double tap
}
stage.addEventListener('dblclick', e => {
  if (lastPT !== 'mouse') return;
  const f = e.clientX / innerWidth;
  if ($('#vid')) { if (f >= .3 && f <= .7) toggleFS(); return; }
  if (R.kind === 'images' && R.mode !== 'webtoon' && f >= .3 && f <= .7) toggleZoom(e.clientX, e.clientY);
});
stage.addEventListener('wheel', e => {
  if (R.kind === 'text' || R.mode === 'webtoon') return;
  const brief = () => { const sp = $('#spread'); sp?.classList.add('dragging'); clearTimeout(wheelT); wheelT = setTimeout(() => sp?.classList.remove('dragging'), 140); };
  if (e.ctrlKey) { e.preventDefault(); brief(); return zoomAt(e.clientX, e.clientY, R.zoom * Math.exp(-e.deltaY * .01)); }
  if (R.zoom > 1) { e.preventDefault(); R.px -= e.deltaX; R.py -= e.deltaY; brief(); applyTransform(); return; }
  if (R.fit === 'height' || R.guided) {
    e.preventDefault();
    const now = Date.now();
    if (now - wheelLock < 380 || Math.abs(e.deltaY) < 8) return;
    wheelLock = now; step(e.deltaY > 0 ? 1 : -1);
  }
}, { passive: false });

/* magnifier */
const loupe = $('#loupe'); let loupeOn = false;
stage.addEventListener('mousemove', e => {
  const img = e.target.closest?.('img.pg');
  if (!(loupeOn || e.shiftKey) || !img) { loupe.style.display = 'none'; return; }
  const r = img.getBoundingClientRect(), Z = 2.6, half = 120;
  const fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
  const bw = r.width * Z, bh = r.height * Z;
  Object.assign(loupe.style, {
    display: 'block', left: e.clientX + 'px', top: e.clientY + 'px',
    backgroundImage: `url("${R.pages[+img.dataset.i]?.full || img.src}")`, backgroundSize: `${bw}px ${bh}px`,
    backgroundPosition: `${-(fx * bw - half)}px ${-(fy * bh - half)}px`, backgroundColor: '#fff',
  });
});
stage.addEventListener('mouseleave', () => loupe.style.display = 'none');

/* keyboard */
document.addEventListener('keydown', e => {
  if (!e.isTrusted) return;                         // fake keys from extensions don't drive the app
  const typing = e.target.matches('input:not([type=range]), textarea, select');
  if (!document.body.classList.contains('reading')) {
    if ((e.key === '/' || (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey))) && !typing) { e.preventDefault(); $('#q').focus(); }
    if (e.key === 'Escape' && $('#libModal.open')) { $('#libModal').classList.remove('open'); return; }
    if (e.key === 'Escape') { if (typing) e.target.blur(); else if (location.hash.startsWith('#/series')) location.hash = '#/'; }
    return;
  }
  if (e.key === 'Shift') { loupeOn = R.kind === 'images'; return; }
  if (e.metaKey || e.ctrlKey || e.altKey || typing) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const text = R.kind === 'text';
  const v = !text && R.mode !== 'webtoon' && $('#vid');
  if (v && !$('.overlay.open')) {
    const vk = { ' ': () => toggleVid(), k: () => toggleVid(), m: () => setVol(null, !v.muted),
      ArrowUp: () => setVol(Math.min(1, v.volume + .1), false), ArrowDown: () => setVol(Math.max(0, v.volume - .1)),
      j: () => { v.currentTime = Math.max(0, v.currentTime - 10); }, l: () => { v.currentTime = Math.min(v.duration || 0, v.currentTime + 10); } }[k];
    if (vk) { e.preventDefault(); wake(); return vk(); }
  }
  const fwd = () => step(1), back = () => step(-1);
  const map = {
    ArrowRight: () => !text && R.rtl ? back() : fwd(), ArrowLeft: () => !text && R.rtl ? fwd() : back(),
    d: () => !text && R.rtl ? back() : fwd(), a: () => !text && R.rtl ? fwd() : back(),
    PageDown: () => text ? pageScroll(1) : fwd(), PageUp: () => text ? pageScroll(-1) : back(),
    ' ': () => text ? pageScroll(e.shiftKey ? -1 : 1) : R.mode === 'webtoon' ? stage.scrollBy({ top: innerHeight * .85 * (e.shiftKey ? -1 : 1), behavior: 'smooth' }) : (e.shiftKey ? back() : fwd()),
    ArrowDown: () => text || R.mode === 'webtoon' ? stage.scrollBy({ top: 220, behavior: 'smooth' }) : fwd(),
    ArrowUp: () => text || R.mode === 'webtoon' ? stage.scrollBy({ top: -220, behavior: 'smooth' }) : back(),
    Home: () => text ? stage.scrollTo({ top: 0 }) : goTo(0, { panel: R.guided ? 0 : undefined }),
    End: () => text ? stage.scrollTo({ top: stage.scrollHeight }) : goTo(R.pages.length - 1, { panel: R.guided ? 0 : undefined }),
    '1': () => setMode('single'), '2': () => setMode('spread'), '3': () => setMode('webtoon'),
    g: toggleGuided, w: toggleFit, r: toggleDir, f: toggleFS, z: () => toggleZoom(),
    t: () => !text && $('#btnFilm').click(), c: () => text && $('#btnToc').click(), h: toggleUI,
    '+': () => setFont(1), '=': () => setFont(1), '-': () => setFont(-1),
    '?': () => $('#help').classList.toggle('open'),
    Escape: () => {
      if ($('.overlay.open')) return closeOverlays();
      if ($('#settings.open, #toc.open')) { $('#settings').classList.remove('open'); $('#toc').classList.remove('open'); return; }
      if (R.zoom > 1) return zoomAt(innerWidth / 2, innerHeight / 2, 1);
      if (R.guided) return toggleGuided();
      closeReader();
    },
  };
  const fn = map[k];
  // turning / scrolling pages never brings the hidden controls back — only the other shortcuts do
  const quiet = k === 'h' || ['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'a', 'd', 'PageDown', 'PageUp', ' ', 'Home', 'End'].includes(k);
  if (fn) { e.preventDefault(); if (!quiet) wake(); fn(); }
});
document.addEventListener('keyup', e => { if (e.key === 'Shift') { loupeOn = false; loupe.style.display = 'none'; } });
window.addEventListener('resize', () => { if (document.body.classList.contains('reading') && R.kind === 'images') applyTransform(); });
setInterval(() => { if (!document.hidden && !document.body.classList.contains('reading') && !S.sel && !$('.overlay.open, #menu.on')) refreshStatus(); }, 8000);
