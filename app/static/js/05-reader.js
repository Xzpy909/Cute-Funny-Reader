'use strict';
/* Cute&Funny Reader — frontend, part 5 of 11: the readers (images, EPUB), their prefs, idle / toast.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

/* ======================= READER (shared) ======================= */
const reader = $('#reader'), stage = $('#stage');
const prefs = Object.assign({ bg: 'ink', ambient: true, anim: true, fs: 19, font: 'serif', width: '40em', lh: '1.75' }, local.get('cf-prefs', {}));
const R = {
  pre: new Map(),                                  // look-ahead: decoded upcoming pages
  book: null, kind: 'images', pages: [], idx: 0, mode: 'single', fit: 'height', rtl: false, guided: false, panel: 0,
  zoom: 1, px: 0, py: 0, panelReq: {}, panelData: {}, chapters: [], ch: 0, scroll: 0, chCache: {}, token: 0,
};
let observer = null;

async function openReader(id, start) {
  const b = S.books[id];
  reader.dataset.libtype = b.format === 'epub' ? 'novel' : libType(b.library);
  const token = ++R.token;
  R.book = b;
  reader.dataset.kind = b.format === 'epub' ? 'text' : 'images';
  document.body.classList.add('reading');
  closeOverlays(); $('#settings').classList.remove('open'); $('#toc').classList.remove('open');
  stage.className = 'stage'; stage.innerHTML = readerLoader('Opening…');
  $('#rTitle').textContent = b.series; $('#rSub').textContent = b.label + (b.title ? ' · ' + b.title : '');
  // picture books: no blurred backdrop until the first page is actually on screen (see revealWhenReady)
  blurBg($('#ambient'), b.format === 'epub' && b.hasCover ? URLS.cover(b, 120) : '', { sat: 1.8 });
  applyPrefs(); wake();
  if (b.transcode && !(await jxlGate(b, token))) return;
  let d;
  try { d = await api.get(`/api/books/${id}`); }
  catch (e) { stage.innerHTML = `<div class="empty" style="margin:auto">Couldn't open this book (${esc(e.message)})</div>`; return; }
  if (token !== R.token) return;
  if (b.format === 'epub') openText(b, d, start); else openImages(b, d, start);
  if (b.transcode) suggestAvif(b);
}
// A HEIC / JPEG XL book had to be transcoded before it opened: offer to convert it for good.
function suggestAvif(b) {
  $('#avifHint')?.remove();
  const s = S.seriesById[b.seriesId], no = local.get('cf-avif-no', []);
  if (!s || no.includes(b.seriesId) || OPT.jobs.some(j => j.books.includes(b.id) && j.state !== 'done' && j.state !== 'cancelled')) return;
  const todo = s.books.filter(x => x.transcode), what = b.heic ? 'HEIC' : b.jxl ? 'JPEG XL' : 'a format browsers can’t show';
  const h = document.createElement('div'); h.id = 'avifHint'; h.setAttribute('role', 'status');
  h.innerHTML = `<span>This ${V(b.library).b} is ${what}, so it has to be converted every time the cache runs out. <b>Optimize to AVIF</b> and it opens instantly.</span>
    <button type="button" class="btn-sm pri" data-avif="go">${ico('spark', 14)} Optimize${todo.length > 1 ? ` all ${todo.length}` : ''}…</button>
    <button type="button" class="btn-sm" data-avif="no">Not now</button>`;
  h.addEventListener('click', e => {
    const a = e.target.closest('[data-avif]')?.dataset.avif; if (!a) return;
    h.remove();
    if (a === 'no') return local.set('cf-avif-no', [...no, b.seriesId].slice(-500));
    openOptimize({ sel: { books: todo.map(x => x.id) }, books: todo, title: s.name });
  });
  reader.append(h);
  setTimeout(() => h.remove(), 20000);
}
// JPEG XL / HEIC: browsers (bar Safari) can't show them, so the server converts the pages to PNG first —
// once, then cached (dropped after JXL_CACHE_DAYS without reading)
async function jxlGate(b, token) {
  const what = b.heic ? 'HEIC' : b.jxl ? 'JPEG XL' : 'pages';
  const paint = st => {
    const pct = st.total ? Math.round(st.done / st.total * 100) : 0;
    stage.innerHTML = `<div class="xcode"><span class="wbook"><i></i><i></i><i></i></span><b>Transcoding ${what}</b>
      <small>${st.done} / ${plural(st.total, 'page')} → PNG · only the first time</small><div class="bar"><i style="width:${pct}%"></i></div></div>`;
  };
  let st;
  try { st = await (await fetch(`/api/books/${b.id}/transcode`, { method: 'POST' })).json(); } catch { st = null; }
  while (st && st.state === 'running' && token === R.token) {
    paint(st);
    await new Promise(r => setTimeout(r, 400));
    try { st = await api.get(`/api/books/${b.id}/transcode`); } catch { st = null; }
  }
  if (token !== R.token) return false;               // the reader was closed / another book opened meanwhile
  if (!st || st.state === 'error') {
    stage.innerHTML = `<div class="empty" style="margin:auto">Couldn’t convert this ${what} book${st?.error ? ` (${esc(st.error)})` : ''}.</div>`;
    return false;
  }
  return true;
}
function shutReader() {
  document.body.classList.remove('reading'); $('#avifHint')?.remove();
  flushProgress();
  closeOverlays(); $('#settings').classList.remove('open'); $('#toc').classList.remove('open');
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  if (observer) { observer.disconnect(); observer = null; }
  R.token++; R.book = null; R.pre = new Map();      // let go of decoded look-ahead pages
  stage.innerHTML = '';
}
const backFrom = sid => {
  const s = S.seriesById[sid];
  if (s && s.books.length === 1) return s.collectionId && S.colById[s.collectionId] ? `#/collection/${s.collectionId}` : `#/library/${s.library}`;
  return `#/series/${sid || ''}`;
};
const closeReader = () => { location.hash = backFrom(R.book?.seriesId); };

/* progress (debounced to server) */
let saveT, pending = null;
function saveProgress(extra = {}) {
  const b = R.book; if (!b) return;
  let rec;
  if (R.kind === 'images') {
    const n = R.pages.length;
    const lastVisible = R.mode === 'spread' ? Math.max(...currentSpread()) : R.idx;
    rec = { seen: true, page: R.idx, frac: (lastVisible + 1) / n, done: !!extra.done || lastVisible >= n - 1, updated: Date.now() };
  } else {
    const n = R.chapters.length;
    rec = { seen: true, chapter: R.ch, scroll: +R.scroll.toFixed(4), frac: (R.ch + R.scroll) / n, done: !!extra.done || (R.ch === n - 1 && R.scroll > .97), updated: Date.now() };
  }
  S.progress[b.id] = rec;
  pending = [b.id, rec];
  clearTimeout(saveT); saveT = setTimeout(flushProgress, 700);
}
function flushProgress() { clearTimeout(saveT); if (pending) { api.put(`/api/progress/${pending[0]}`, pending[1]); pending = null; } }
window.addEventListener('pagehide', flushProgress);

function nextBook() {
  const s = S.seriesById[R.book.seriesId];
  const i = s.books.findIndex(b => b.id === R.book.id);
  return s.books[i + 1] || null;
}
function showEnd() {
  saveProgress({ done: true }); flushProgress();
  const next = nextBook(), s = S.seriesById[R.book.seriesId];
  $('#endInner').innerHTML = next ? `${coverImg(next, 320)}
    <div><div class="eyebrow">Finished ${esc(R.book.label)} 🎉</div>
    <h3>Up next: ${esc(next.label)}</h3><p>${esc(next.title || s.name)}</p>
    <div class="actions"><button class="btn-primary" data-endnext="${next.id}">${ico('play')} Read next</button><button class="btn-ghost" data-endback>${s.books.length === 1 ? 'Back' : `Back to ${V(s.library).s}`}</button></div></div>`
    : `${coverImg(R.book, 320)}<div><div class="eyebrow">All caught up 🎉</div><h3>${esc(s.name)}</h3><p>That's the latest ${R.book.kind || 'book'} in your library. New ones will show up after the next scan.</p>
    <div class="actions"><button class="btn-primary" data-endback>${s.books.length === 1 ? 'Back' : `Back to ${V(s.library).s}`}</button><button class="btn-ghost" data-endhome>Library</button></div></div>`;
  $('#endcard').classList.add('open');
}
function closeOverlays() { $$('.overlay.open').forEach(o => o.classList.remove('open')); }

/* ======================= IMAGE READER ======================= */
function openImages(b, d, start) {
  R.kind = 'images';
  reader.dataset.libtype = libType(b.library);
  const vids = new Set(d.videos || []);
  const fit = b.raw ? '' : `&max=${displayMax()}`;    // RAW books: always the lossless original
  R.pages = d.dims.map(([w, h], i) => ({ src: URLS.page(b, i) + (vids.has(i) ? '' : fit), full: URLS.page(b, i),
    thumb: vids.has(i) ? null : URLS.thumb(b, i, 200), w, h, video: vids.has(i) }));
  R.pre = new Map();
  R.panelReq = {}; R.panelData = {};
  const sp = seriesPrefs[b.seriesId] || {};
  R.rtl = libRtl(b);
  const ratios = R.pages.map(p => p.h / p.w).sort((a, b) => a - b);
  const tall = ratios[Math.floor(ratios.length / 2)] > 2.2;
  R.mode = sp.mode ?? (tall ? 'webtoon' : 'single');
  R.fit = sp.fit ?? 'height';
  R.guided = false; R.zoom = 1; R.px = R.py = 0;
  const p = prog(b);
  R.idx = clamp(start ?? (p && !p.done ? p.page ?? 0 : 0), 0, R.pages.length - 1);
  const ar = p => p.video ? '16/9' : clamp(p.w / p.h, .42, 1.9).toFixed(3);
  $('#film').innerHTML = R.pages.map((p, i) => `<button data-go="${i}" style="--ar:${ar(p)}">${p.video ? '<div class="vth">▶</div>' : `<img src="${p.thumb}" alt="" loading="lazy">`}<span>${i + 1}</span></button>`).join('');
  $('#film').dir = R.rtl ? 'rtl' : 'ltr';
  render();
  saveProgress();
  if (!local.get('cf-tipped', false)) { local.set('cf-tipped', true); setTimeout(() => toast('Press ? for shortcuts'), 500); }
  else if (R.rtl) setTimeout(() => toast('Right-to-left · press R to switch'), 400);
  if (isCosplay(b.library) && R.mode === 'single' && !seriesPrefs[b.seriesId]?.fit) R.fit = 'height';
}

const isWide = i => R.pages[i] && (R.pages[i].video || R.pages[i].w > R.pages[i].h * 1.1);
function spreads() {
  const n = R.pages.length, out = [[0]];
  let i = 1;
  while (i < n) {
    if (isWide(i)) { out.push([i]); i++; continue; }
    if (i + 1 < n && !isWide(i + 1)) { out.push([i, i + 1]); i += 2; } else { out.push([i]); i++; }
  }
  return out;
}
const currentSpread = () => R.mode === 'spread' ? (spreads().find(s => s.includes(R.idx)) || [R.idx]) : [R.idx];

function render(dir = 0) {
  if (observer) { observer.disconnect(); observer = null; }
  if (R.kind === 'text') return;
  if (R.mode === 'webtoon') renderStrip(); else renderPages(dir);
  updateChrome();
}

function renderPages(dir = 0) {
  const vi = currentSpread().find(i => R.pages[i]?.video);
  if (vi != null) return renderVideo(vi, dir);
  stage.className = `stage fit-${R.fit} mode-${R.mode}${R.guided ? ' is-guided' : ''}`;
  stage.style.cursor = '';
  const ids = currentSpread();
  const order = R.rtl ? [...ids].reverse() : ids;
  const anim = prefs.anim && dir ? ((dir > 0) !== R.rtl ? 'turn-next' : 'turn-prev') : '';
  stage.innerHTML = `<div class="spread ${anim}" id="spread">${order.map(i =>
    `<div class="page"><img class="pg" src="${R.guided ? R.pages[i].full : R.pages[i].src}" data-i="${i}" width="${R.pages[i].w}" height="${R.pages[i].h}" style="--ar:${(R.pages[i].h / R.pages[i].w) || 1.5}" alt="Page ${i + 1}" draggable="false">${R.guided ? '<div class="spot"></div>' : ''}</div>`).join('')}</div>`;
  stage.scrollTop = 0;
  const img = $('#spread img');
  if (img.complete) applyTransform(); else img.addEventListener('load', applyTransform, { once: true });
  applyTransform();
  revealWhenReady($('#spread'), R.pages[R.idx].thumb);
  prefetchAround(ids);
  if (R.guided) {
    const i = R.idx;
    ensurePanels(i).then(() => {
      if (R.idx !== i || !R.guided) return;
      if (R.panel === 'last') R.panel = panelsOf(i).length - 1;
      R.panel = clamp(R.panel, 0, panelsOf(i).length - 1);
      applyTransform(); updateChrome();
    });
    ensurePanels(i + 1);
  }
}

function renderStrip() {
  stage.className = 'stage mode-webtoon';
  stage.innerHTML = `<div class="strip">${R.pages.map((p, i) => p.video
    ? `<video class="pg vstrip" src="${p.src}" data-i="${i}" controls playsinline preload="metadata"></video>`
    : `<img class="pg" src="${p.full}" data-i="${i}" data-full="1" width="${p.w}" height="${p.h}" alt="Page ${i + 1}" loading="lazy" draggable="false">`).join('')}</div>`;   // scroll mode: always the original file — strips are read at full width
  const target = stage.querySelector(`[data-i="${R.idx}"]`);
  requestAnimationFrame(() => { stage.scrollTop = target.offsetTop; });
  observer = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) {
      R.idx = +e.target.dataset.i; updateChrome(); saveProgress(); setAmbient(R.pages[R.idx].thumb);
    }
  }, { root: stage, rootMargin: '-50% 0px -50% 0px', threshold: 0 });
  $$('.strip .pg').forEach(el => observer.observe(el));
  setAmbient(R.pages[R.idx].thumb);
}

/* guided panels */
function ensurePanels(i) {
  if (i < 0 || i >= R.pages.length) return Promise.resolve();
  return (R.panelReq[i] ||= api.get(`/api/books/${R.book.id}/panels/${i}?rtl=${R.rtl ? 1 : 0}`)
    .then(r => { R.panelData[i] = r.panels; })
    .catch(() => { R.panelData[i] = [{ x: 0, y: 0, w: 1, h: 1 }]; }));
}
const panelsOf = i => R.panelData[i] || [{ x: 0, y: 0, w: 1, h: 1 }];

function applyTransform() {
  const sp = $('#spread'); if (!sp) return;
  if (R.guided && R.mode === 'single') {
    const img = sp.querySelector('img'), w = img.offsetWidth, h = img.offsetHeight;
    if (!w || !h) return;
    const ps = panelsOf(R.idx), p = ps[clamp(R.panel === 'last' ? ps.length - 1 : R.panel, 0, ps.length - 1)];
    const s = Math.min(innerWidth * .94 / (p.w * w), innerHeight * .86 / (p.h * h));
    const dx = (p.x + p.w / 2 - .5) * w, dy = (p.y + p.h / 2 - .5) * h;
    sp.style.transform = `scale(${s}) translate(${-dx}px, ${-dy}px)`;
    sp.classList.toggle('zoomed', s > 1.05);
    const spot = sp.querySelector('.spot');
    if (spot) Object.assign(spot.style, { left: p.x * 100 + '%', top: p.y * 100 + '%', width: p.w * 100 + '%', height: p.h * 100 + '%' });
  } else {
    sp.style.transform = `translate(${R.px}px, ${R.py}px) scale(${R.zoom})`;
    sp.classList.toggle('zoomed', R.zoom > 1);
  }
}

function seqOf(b) {
  const s = S.seriesById[b.seriesId];
  return S.series.filter(x => x.library === b.library && (x.collectionId || null) === (s?.collectionId || null) && x.books.length)
    .sort((a, c) => natCmp(a.name, c.name)).flatMap(x => x.books);
}
function neighbour(dir) { const seq = seqOf(R.book), i = seq.findIndex(x => x.id === R.book.id); return i < 0 ? null : seq[i + dir] || null; }
function atEnd() {
  if (isCosplay(R.book.library)) {
    const n = neighbour(1);
    if (n) { saveProgress({ done: true }); flushProgress(); return openBook(n.id, 0); }
  }
  showEnd();
}
function atStart() {
  if (isCosplay(R.book.library)) { const p = neighbour(-1); if (p) return openBook(p.id, Math.max(0, p.pages - 1)); }
  toast('This is the first page');
}
function step(dir) {
  if (R.kind === 'text') return stepText(dir);
  if (dir < 0 && R.idx <= 0 && (!R.guided || R.panel === 0)) return atStart();
  if (R.mode === 'webtoon') {
    if (dir > 0 && R.idx >= R.pages.length - 1) return atEnd();
    return goTo(R.idx + dir);
  }
  if (R.guided) {
    const n = panelsOf(R.idx).length, cur = R.panel === 'last' ? n - 1 : R.panel, np = cur + dir;
    if (np >= 0 && np < n) { R.panel = np; applyTransform(); updateChrome(); return; }
    if (dir > 0) return R.idx < R.pages.length - 1 ? goTo(R.idx + 1, { dir, panel: 0 }) : atEnd();
    if (R.idx > 0) goTo(R.idx - 1, { dir, panel: 'last' });
    return;
  }
  if (R.mode === 'spread') {
    const sp = spreads(), k = sp.findIndex(s => s.includes(R.idx)), nk = k + dir;
    if (nk >= sp.length) return atEnd();
    if (nk >= 0) goTo(sp[nk][0], { dir });
    return;
  }
  if (dir > 0 && R.idx >= R.pages.length - 1) return atEnd();
  goTo(R.idx + dir, { dir });
}

function goTo(i, o = {}) {
  if (R.kind === 'text') return loadChapter(i);
  i = clamp(i, 0, R.pages.length - 1);
  const dir = o.dir ?? Math.sign(i - R.idx);
  if (i === R.idx && o.panel == null && !o.force) return;
  R.idx = i; R.zoom = 1; R.px = R.py = 0;
  if (R.guided) R.panel = o.panel ?? 0;
  if (R.mode === 'webtoon') {
    const t = stage.querySelector(`[data-i="${i}"]`);
    if (t) stage.scrollTo({ top: t.offsetTop, behavior: o.instant ? 'auto' : 'smooth' });
    updateChrome();
  } else { renderPages(dir); updateChrome(); }
  saveProgress();
}

function updateChrome() {
  const sl = $('#slider'), pc = $('#panelChip');
  if (R.kind === 'text') {
    const n = R.chapters.length;
    $('#bottom').classList.remove('vbar');
    $('#pageLabel').textContent = `${R.ch + 1} / ${n}`;
    sl.max = n - 1; sl.value = R.ch; sl.dir = 'ltr';
    sl.style.setProperty('--p', (n > 1 ? R.ch / (n - 1) * 100 : 100) + '%');
    pc.classList.add('show'); pc.textContent = `${Math.round(R.scroll * 100)}%`;
    $('#rSub').textContent = `${R.book.label} · ${R.chapters[R.ch]?.title || `Section ${R.ch + 1}`}`;
    $$('#toc button').forEach(b => b.classList.toggle('on', +b.dataset.ch === R.ch));
    return;
  }
  const n = R.pages.length;
  $('#bottom').classList.toggle('vbar', R.mode !== 'webtoon' && currentSpread().some(i => R.pages[i]?.video));
  let label = `${R.idx + 1}`;
  if (R.mode === 'spread') { const s = currentSpread(); label = s.length > 1 ? `${s[0] + 1}–${s[1] + 1}` : `${s[0] + 1}`; }
  $('#pageLabel').textContent = `${label} / ${n}`;
  sl.max = n - 1; sl.value = R.idx; sl.dir = R.rtl ? 'rtl' : 'ltr';
  sl.style.setProperty('--p', (n > 1 ? R.idx / (n - 1) * 100 : 100) + '%');
  $$('#modeSeg button').forEach(b => b.classList.toggle('on', b.dataset.mode === R.mode));
  const gb = $('#btnGuided'); gb.classList.toggle('on', R.guided); gb.disabled = R.mode === 'webtoon';
  const fb = $('#btnFit'); fb.innerHTML = ico(R.fit === 'height' ? 'fitH' : 'fitW'); fb.disabled = R.mode === 'webtoon' || R.guided;
  $('#btnZoom').disabled = R.mode === 'webtoon';
  $('#btnDir').textContent = R.rtl ? 'RTL' : 'LTR';
  $('#btnDir').classList.toggle('on', R.rtl);
  pc.classList.toggle('show', R.guided);
  if (R.guided) { const ps = panelsOf(R.idx); pc.textContent = `Panel ${(R.panel === 'last' ? ps.length - 1 : R.panel) + 1} / ${ps.length}`; }
  const vis = currentSpread();
  $$('#film button').forEach((b, i) => b.classList.toggle('on', vis.includes(i)));
  if ($('#bottom').classList.contains('film-open')) centreFilm(true);
}

function setMode(m) {
  if (R.kind === 'text' || m === R.mode) return;
  R.mode = m; R.zoom = 1; R.px = R.py = 0;
  if (m !== 'single') R.guided = false;
  saveSeriesPref(R.book.seriesId, { mode: m });
  render(); toast({ single: 'Single page', spread: 'Two-page spread', webtoon: 'Vertical scroll' }[m]);
}
function toggleGuided() {
  if (R.kind === 'text' || isCosplay(R.book.library)) return;
  if (R.mode === 'webtoon') return toast('Guided view works in Single & Spread');
  R.guided = !R.guided;
  if (R.guided) { R.mode = 'single'; R.panel = 0; R.zoom = 1; R.px = R.py = 0; }
  render(); toast(R.guided ? 'Guided view — arrows step through panels' : 'Guided view off');
}
function toggleFit() {
  if (R.kind === 'text' || R.mode === 'webtoon' || R.guided) return;
  R.fit = R.fit === 'height' ? 'width' : 'height'; R.zoom = 1; R.px = R.py = 0;
  saveSeriesPref(R.book.seriesId, { fit: R.fit });
  render(); toast(R.fit === 'height' ? 'Fit to height' : 'Fit to width');
}
function toggleDir() {
  if (R.kind === 'text' || isCosplay(R.book.library)) return;
  R.rtl = !R.rtl; R.panelReq = {}; R.panelData = {};
  saveSeriesPref(R.book.seriesId, { rtl: R.rtl });
  $('#film').dir = R.rtl ? 'rtl' : 'ltr';
  render(); toast(R.rtl ? 'Right-to-left' : 'Left-to-right');
}
function toggleFS() {
  if (document.fullscreenElement) return document.exitFullscreen().catch(() => {});
  const p = document.documentElement.requestFullscreen?.();
  if (p) p.catch(() => toast('Fullscreen isn’t available here'));
}
function zoomAt(cx, cy, z) {
  if (R.kind === 'text' || R.mode === 'webtoon' || $('#vid')) return;
  if (R.guided) { R.guided = false; render(); }
  const sp = $('#spread'); if (!sp) return;
  z = clamp(z, 1, 5);
  const r = sp.getBoundingClientRect();
  const ux = r.left + r.width / 2 - R.px, uy = r.top + r.height / 2 - R.py;
  const sx = cx - ux, sy = cy - uy;
  const c0x = (sx - R.px) / R.zoom, c0y = (sy - R.py) / R.zoom;
  R.px = sx - z * c0x; R.py = sy - z * c0y; R.zoom = z;
  if (z <= 1.01) { R.zoom = 1; R.px = R.py = 0; }
  stage.style.cursor = R.zoom > 1 ? 'grab' : '';
  if (R.zoom > 1) useFullRes(sp);
  applyTransform();
}
const toggleZoom = (cx = innerWidth / 2, cy = innerHeight / 2) => R.zoom > 1 ? zoomAt(cx, cy, 1) : zoomAt(cx, cy, 2.4);
const setAmbient = src => { if (src) blurBg($('#ambient'), src, { sat: 1.8 }); };

/* ======================= TEXT (EPUB) READER ======================= */
function openText(b, d, start) {
  R.kind = 'text';
  R.chapters = d.chapters; R.chCache = {};
  const p = prog(b), resume = start == null && p && !p.done;
  R.ch = clamp(start ?? (resume ? p.chapter ?? 0 : 0), 0, R.chapters.length - 1);
  R.scroll = resume ? p.scroll || 0 : 0;
  stage.className = 'stage mode-text';
  stage.innerHTML = `<div class="prose-wrap"><article class="prose" id="prose"></article><nav class="chnav" id="chnav"></nav></div>`;
  $('#toc').innerHTML = `<div class="pop-h" style="padding:6px 10px 10px">Contents</div>` + R.chapters.map((c, i) =>
    `<button data-ch="${i}" class="${c.title ? '' : 'dim'}"><span>${i + 1}</span>${esc(c.title || 'Untitled section')}</button>`).join('');
  loadChapter(R.ch, { scroll: R.scroll });
}
const fetchChapter = i => (R.chCache[i] ||= api.get(`/api/books/${R.book.id}/chapters/${i}`).catch(e => { delete R.chCache[i]; throw e; }));

async function loadChapter(i, o = {}) {
  i = clamp(i, 0, R.chapters.length - 1);
  const token = R.token, prose = $('#prose');
  if (!prose) return;
  R.ch = i; R.scroll = o.scroll || 0;
  prose.classList.add('loading');
  let data;
  try { data = await fetchChapter(i); } catch (e) { prose.innerHTML = `<p>Couldn't load this section (${esc(e.message)}).</p>`; prose.classList.remove('loading'); return; }
  if (token !== R.token || R.ch !== i) return;
  prose.innerHTML = data.html || '<p style="opacity:.5;text-align:center">(empty section)</p>';
  prose.classList.remove('loading');
  const prev = R.chapters[i - 1], next = R.chapters[i + 1];
  $('#chnav').innerHTML = `${prev ? `<button data-chgo="${i - 1}"><small>Previous</small>${esc(prev.title || `Section ${i}`)}</button>` : '<span style="flex:1"></span>'}
    ${next ? `<button class="nx" data-chgo="${i + 1}"><small>Next</small>${esc(next.title || `Section ${i + 2}`)} →</button>` : `<button class="nx" data-finish><small>The end</small>Finish book ✓</button>`}`;
  requestAnimationFrame(() => {
    if (o.anchor) {
      const el = prose.querySelector(`[id="${CSS.escape(o.anchor)}"]`);
      if (el) { el.scrollIntoView(); return; }
    }
    const max = stage.scrollHeight - stage.clientHeight;
    stage.scrollTop = o.end ? max : (o.scroll || 0) * max;
  });
  updateChrome(); saveProgress();
  if (next) fetchChapter(i + 1).catch(() => {});
}
function stepText(dir) {
  if (dir > 0 && R.ch >= R.chapters.length - 1) return showEnd();
  if (R.ch + dir >= 0) loadChapter(R.ch + dir);
}
function pageScroll(dir) {
  const max = stage.scrollHeight - stage.clientHeight;
  if (dir > 0 && stage.scrollTop >= max - 4) return stepText(1);
  if (dir < 0 && stage.scrollTop <= 4) { if (R.ch > 0) loadChapter(R.ch - 1, { end: true }); return; }
  stage.scrollBy({ top: dir * stage.clientHeight * .88, behavior: 'smooth' });
}
stage.addEventListener('scroll', () => {
  if (R.kind !== 'text' || !$('#prose')) return;
  const max = stage.scrollHeight - stage.clientHeight;
  R.scroll = max > 0 ? clamp(stage.scrollTop / max, 0, 1) : 1;
  $('#panelChip').textContent = `${Math.round(R.scroll * 100)}%`;
  saveProgress();
}, { passive: true });

/* ======================= PREFS ======================= */
function applyPrefs() {
  reader.dataset.bg = prefs.bg;
  reader.classList.toggle('no-ambient', !prefs.ambient || R.book?.format === 'epub');
  reader.style.setProperty('--fs', prefs.fs + 'px');
  reader.style.setProperty('--lh', prefs.lh);
  reader.style.setProperty('--measure', prefs.width);
  reader.style.setProperty('--rfont', prefs.font === 'sans' ? 'var(--body)' : '"Literata", Georgia, serif');
  $$('#bgSeg button').forEach(b => b.classList.toggle('on', b.dataset.bg === prefs.bg));
  $$('#fontSeg button').forEach(b => b.classList.toggle('on', b.dataset.font === prefs.font));
  $$('#widthSeg button').forEach(b => b.classList.toggle('on', b.dataset.w === prefs.width));
  $$('#lhSeg button').forEach(b => b.classList.toggle('on', b.dataset.lh === prefs.lh));
  $('#fsVal').textContent = prefs.fs + 'px';
  $('#swAmbient').classList.toggle('on', prefs.ambient);
  $('#swAnim').classList.toggle('on', prefs.anim);
  local.set('cf-prefs', prefs);
}
function setFont(delta) {
  if (R.kind !== 'text') return;
  const keep = R.scroll;
  prefs.fs = clamp(prefs.fs + delta, 14, 30); applyPrefs();
  requestAnimationFrame(() => { stage.scrollTop = keep * (stage.scrollHeight - stage.clientHeight); });
  toast(`Text size ${prefs.fs}px`);
}

/* ======================= UI idle / toast ======================= */
let idleT, toastT;
function wake() {
  reader.classList.remove('idle'); clearTimeout(idleT);
  idleT = setTimeout(() => {
    if ($('#settings.open, #toc.open, .chrome:hover, .overlay.open')) return wake();
    reader.classList.add('idle');
  }, R.kind === 'text' ? 3500 : 2600);
}
function toggleUI() { if (reader.classList.toggle('idle')) clearTimeout(idleT); else wake(); }
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 1600); }

/* ---------- clicks handled here (the order is in CLICKS, js/06-events.js) ---------- */
function clickGo(g) { return R.guided ? goTo(+g.dataset.go, { panel: 0 }) : goTo(+g.dataset.go); }
function clickTocChapter(ch) { $('#toc').classList.remove('open'); return loadChapter(+ch.dataset.ch); }
function clickChapterGo(cg) { return loadChapter(+cg.dataset.chgo); }
function clickProseLink(link, e) { e.preventDefault(); if (link.dataset.ch != null) loadChapter(+link.dataset.ch, { anchor: link.dataset.anchor }); else if (link.dataset.anchor) $('#prose').querySelector(`[id="${CSS.escape(link.dataset.anchor)}"]`)?.scrollIntoView({ behavior: 'smooth' }); }
function clickProseImage(pimg) { $('#lightbox img').src = pimg.src; $('#lightbox').classList.add('open'); }
function clickEndNext(en) { closeOverlays(); return openBook(en.dataset.endnext, 0); }
function clickEndBack() { closeOverlays(); return closeReader(); }
function clickEndHome() { closeOverlays(); location.hash = '#/'; }
