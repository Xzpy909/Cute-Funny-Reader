'use strict';
/* Cute&Funny Reader — frontend, part 6 of 11: keyboard, buttons and the main click handling.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

/* ======================= EVENTS ======================= */
$$('[data-ico]').forEach(el => el.insertAdjacentHTML('afterbegin', ico(el.dataset.ico)));

document.addEventListener('click', e => {
  const t = e.target;
  const tpb = t.closest('[data-tagpop]');
  if (tpb) { e.preventDefault(); e.stopPropagation(); return openTagPop(tpb); }
  const tg = t.closest('[data-tag]');
  if (tg) { closeTagPop(); e.preventDefault(); e.stopPropagation(); S.q = tg.dataset.tag; $('#q').value = S.q; S.filter = 'all';
    const h = S.lib ? `#/library/${S.lib}` : '#/'; if (location.hash === h) { renderHome(); renderSidebar(); } else location.hash = h; return; }
  const mo = t.closest('[data-more]');
  if (mo) { e.preventDefault(); e.stopPropagation(); return openMenu(mo.dataset.more, mo); }
  const cc = t.closest('[data-collection]');
  if (cc && !S.sel) { location.hash = `#/collection/${cc.dataset.collection}`; return; }
  if (cc && S.sel) return appToast(`${cap(pl(Vhome().g))} can’t be selected — open one to select its ${pl(Vhome().s)}`);
  const lbk = t.closest('[data-libback]');
  if (lbk) { location.hash = `#/library/${lbk.dataset.libback}`; return; }
  const cbk = t.closest('[data-colback]');
  if (cbk) { location.hash = `#/collection/${cbk.dataset.colback}`; return; }
  const nc = t.closest('[data-newcol]');
  if (nc) return newCollection(nc, nc.dataset.newcol);
  const ss = t.closest('[data-sersettings]');
  if (ss) return openSeriesModal(S.seriesById[ss.dataset.sersettings]);
  const ns = t.closest('[data-newseries]');
  if (ns) return openSeriesModal(null, ns.dataset.newseries);
  if (t.closest('[data-select]')) return toggleSelect(!S.sel);
  if (t.closest('[data-selclose]')) return toggleSelect(false);
  if (t.closest('[data-selall]')) {
    const pool = selPool();
    S.sel = pool.every(id => S.sel.has(id)) ? new Set() : new Set(pool);
    return S.selMode === 'series' ? (renderHome(), renderSelbar()) : renderSeries(S.curSeries);
  }
  const sa = t.closest('[data-selact]');
  if (sa) {
    if (!S.sel?.size) return;
    if (sa.dataset.selact === 'read') {
      const books = selBooks(), done = !books.every(isDone);
      books.forEach(b => setDone(b, done));
      appToast(`Marked ${plural(books.length, 'item')} as ${done ? 'read' : 'unread'}`); S.sel = new Set(); renderSidebar();
      return S.selMode === 'series' ? (renderHome(), renderSelbar()) : renderSeries(S.curSeries);
    }
    if (S.selMode === 'series') return openSeriesBatchMenu([...S.sel], sa, sa.dataset.selact);
    return openBooksMenu([...S.sel], sa, sa.dataset.selact);
  }
  const vw = t.closest('[data-view]');
  if (vw) { saveSeriesPref(S.curSeries, { view: vw.dataset.view }); return renderSeries(S.curSeries); }
  if (t.closest('[data-sortflip]')) { const s = S.seriesById[S.curSeries]; saveSeriesPref(s.id, { sort: seriesSort(s) === 'desc' ? 'asc' : 'desc' }); return renderSeries(s.id); }
  if (S.sel) {
    const sc = S.selMode === 'series' && t.closest('#grid [data-series]');
    if (sc) { e.preventDefault(); const id = sc.dataset.series; S.sel.has(id) ? S.sel.delete(id) : S.sel.add(id); sc.classList.toggle('sel', S.sel.has(id)); sc._h = null; return renderSelbar(); }
    const so = S.selMode === 'books' && t.closest('.chgrid [data-open], .blist [data-open]');
    if (so) { e.preventDefault(); const id = so.dataset.open; S.sel.has(id) ? S.sel.delete(id) : S.sel.add(id); so.classList.toggle('sel', S.sel.has(id)); return renderSelbar(); }
  }
  const gone = !S.sel && t.closest('.card.trashed, .brow.trashed');
  if (gone) { e.preventDefault(); return openMenu(itemKey(gone), gone, isPhone() ? null : e); }
  const mark = t.closest('[data-mark]');
  if (mark) { const b = S.books[mark.dataset.mark]; setDone(b, !isDone(b)); renderSeries(b.seriesId); renderSidebar(); return; }
  const all = t.closest('[data-markall]');
  if (all) { const s = S.seriesById[all.dataset.markall]; const done = seriesInfo(s).unread > 0; s.books.forEach(b => setDone(b, done)); renderSeries(s.id); renderSidebar(); return; }
  const o = t.closest('[data-open]');
  if (o) return openBook(o.dataset.open, o.dataset.start != null ? +o.dataset.start : null);
  const se = t.closest('[data-series]');
  if (se) { if (se.dataset.single) return openBook(se.dataset.single); location.hash = `#/series/${se.dataset.series}`; return; }
  if (t.closest('[data-home]')) { location.hash = S.lib ? `#/library/${S.lib}` : '#/'; return; }
  if (t.closest('[data-addlib], #btnAddLib')) return openLibModal();
  const el = t.closest('[data-editlib]');
  if (el) return openLibModal(S.libById[el.dataset.editlib]);
  const pk = t.closest('[data-pick]');
  if (pk) { UP.pickTarget = pk.dataset.pick; UP.pickSeries = pk.dataset.pickseries || null; UP.pickCol = pk.dataset.pickcol || null; $('#filePick').click(); return; }
  if (t.closest('[data-upcancel]')) return cancelUploads();
  const ul = t.closest('[data-uplist]');
  if (ul) {                                          // the files whose path was too long: paths inside the dropped folder
    const text = (UP.longPaths || []).join('\r\n') + '\r\n';
    if (ul.dataset.uplist === 'copy') return navigator.clipboard.writeText(text).then(() => appToast('List copied — paste it anywhere (e.g. Notepad)'), () => appToast('Couldn’t copy — try Save list'));
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
    a.download = 'files-with-too-long-paths.txt'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    return;
  }
  if (t.closest('[data-upmin]') || (t.closest('#uploads.min .up-h') && !t.closest('[data-upclose], [data-upcancel]'))) {
    UP.min = !UP.min; local.set('cf-upmin', UP.min); UP.listAt = 0; renderUploads(); return;
  }
  if (t.closest('[data-upclose]')) { if (!UP.rows.some(r => r.state === 'queued' || r.state === 'up')) { UP.rows = []; UP.longPaths = []; } $('#uploads').classList.remove('on'); return; }
  if (t.closest('[data-closemodal]')) { $('#libModal').classList.remove('open'); return; }
  const f = t.closest('[data-filter]');
  if (f) { S.filter = f.dataset.filter; renderHome(); renderSidebar(); return; }
  const nav = t.closest('[data-nav]');
  if (nav?.dataset.nav === 'favs') { location.hash = '#/favs'; return; }
  if (nav?.dataset.nav === 'storage') { location.hash = '#/storage'; return; }
  const fl = t.closest('[data-favlist]');
  if (fl) { location.hash = `#/fav/${fl.dataset.favlist}`; return; }
  if (t.closest('[data-favback]')) { location.hash = '#/favs'; return; }
  const nf = t.closest('[data-newfav]');
  if (nf) return openPrompt(nf, { title: 'New favourites list', hint: 'Add series, sets or variants to it from their ⋯ menu.', placeholder: 'List name', button: 'Create',
    run: async name => { const f = await jsonFetch('POST', '/api/favorites', { name }); await refreshFavs(); location.hash = `#/fav/${f.id}`; } });
  if (nav) { S.lib = null; S.filter = nav.dataset.nav === 'home' ? 'all' : nav.dataset.nav; if (location.hash.length > 2) location.hash = '#/'; else { renderHome(); renderSidebar(); } return; }
  const lb = t.closest('[data-lib]');
  if (lb) { S.filter = 'all'; location.hash = location.hash === `#/library/${lb.dataset.lib}` ? '#/' : `#/library/${lb.dataset.lib}`; return; }
  const g = t.closest('[data-go]');
  if (g) return R.guided ? goTo(+g.dataset.go, { panel: 0 }) : goTo(+g.dataset.go);
  const ch = t.closest('#toc [data-ch]');
  if (ch) { $('#toc').classList.remove('open'); return loadChapter(+ch.dataset.ch); }
  const cg = t.closest('[data-chgo]');
  if (cg) return loadChapter(+cg.dataset.chgo);
  if (t.closest('[data-finish]')) return showEnd();
  const link = t.closest('#prose a[href="#"]');
  if (link) { e.preventDefault(); if (link.dataset.ch != null) loadChapter(+link.dataset.ch, { anchor: link.dataset.anchor }); else if (link.dataset.anchor) $('#prose').querySelector(`[id="${CSS.escape(link.dataset.anchor)}"]`)?.scrollIntoView({ behavior: 'smooth' }); return; }
  const pimg = t.closest('#prose img');
  if (pimg && !pimg.closest('h1,h2')) { $('#lightbox img').src = pimg.src; $('#lightbox').classList.add('open'); return; }
  const en = t.closest('[data-endnext]');
  if (en) { closeOverlays(); return openBook(en.dataset.endnext, 0); }
  if (t.closest('[data-endback]')) { closeOverlays(); return closeReader(); }
  if (t.closest('[data-endhome]')) { closeOverlays(); location.hash = '#/'; }
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
