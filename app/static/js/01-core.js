'use strict';
/* Cute&Funny Reader — frontend, part 1 of 11: helpers, the API wrapper, placeholder art, smooth scrolling and the ⚡ switches.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

/* ======================= UTILS ======================= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const local = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
const ago = t => {
  if (!t) return 'never';
  const s = Date.now() / 1000 - t;
  return s < 60 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
};
const plural = (n, w) => `${n} ${w}${n === 1 || w.endsWith('s') ? '' : 's'}`;
const pl = w => w.endsWith('s') ? w : w + 's';                    // plural without a number: "sets", "series"
const cap = w => w.charAt(0).toUpperCase() + w.slice(1);
// What things are called, per library type — the only place these words live.
//   s: a group of books   b: one book   ch: what you page through   g: a folder of groups (🗂️)
const VOCAB = {
  comics:  { s: 'series',     b: 'book', ch: 'chapter', g: 'collection', G_BADGE: 'COLLECTION',
             author: 'Author', authorHint: 'Writer / artist', pub: 'Publisher / group', by: a => 'by ' + a, from: p => p,
             dropWhat: '<b>.cbz</b>, <b>.zip</b> or <b>.epub</b> files', dropSorts: 'Chapters are sorted into series folders automatically.' },
  cosplay: { s: 'set',        b: 'variant', ch: 'variant', g: 'cosplayer', G_BADGE: 'COSPLAYER',   // circle → metadata
             author: 'Cosplayer', authorHint: 'Who is in the photos', pub: 'Photographer / publisher', by: a => a, from: p => '📷 ' + p,
             dropWhat: '<b>.zip</b> sets, photo folders or videos', dropSorts: 'Sets are sorted into cosplayer and set folders automatically.' },
};
const V = lid => VOCAB[lid && isCosplay(lid) ? 'cosplay' : 'comics'];
// "all libraries" views: Cosplay words only when every library is a Cosplay one
const Vhome = () => S.lib ? V(S.lib) : (S.libraries.length && S.libraries.every(l => isCosplay(l.id)) ? VOCAB.cosplay : VOCAB.comics);

const ICONS = {
  chevL: '<path d="M15 18l-6-6 6-6"/>', chevR: '<path d="M9 18l6-6-6-6"/>', chevD: '<path d="M6 9l6 6 6-6"/>', plus: '<path d="M12 5v14M5 12h14"/>', spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>', upload: '<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>', chevR: '<path d="M9 18l6-6-6-6"/>',
  home: '<path d="M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  book: '<path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2z"/><path d="M4 19V5M8 7h7"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  guided: '<path d="M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3"/><rect x="8.5" y="8.5" width="7" height="7" rx="1"/>',
  fitH: '<path d="M12 3v18M8 7l4-4 4 4M8 17l4 4 4-4"/>', fitW: '<path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h10"/>',
  film: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 5v14M16 5v14"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 114 2c-.9.6-1.5 1.1-1.5 2.2M12 17h.01"/>',
  zoom: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5M11 8v6M8 11h6"/>',
  toc: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/>',
  play: '<path d="M8 5v14l11-7z" fill="currentColor"/>',
  pause: '<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" stroke="none"/>',
  skipb: '<path d="M18 6v12L9 12z" fill="currentColor"/><path d="M6 6v12"/>',
  skipf: '<path d="M6 6v12l9-6z" fill="currentColor"/><path d="M18 6v12"/>',
  vol: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z" fill="currentColor"/><path d="M15.5 9a4 4 0 010 6M18 6.5a7.5 7.5 0 010 11"/>',
  volx: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z" fill="currentColor"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0113 0M16 4.5a3.5 3.5 0 010 7M18 14a6 6 0 013.5 6"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M14 9l2 2"/>',
  logout: '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V4h6v3"/>',
  move: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  stack: '<rect x="4" y="4" width="10" height="13" rx="1.5"/><path d="M8 20h10a2 2 0 002-2V8"/>',
  heart: '<path d="M12 20.5s-7.5-4.6-7.5-10.4A4.1 4.1 0 0112 7.6a4.1 4.1 0 017.5 2.5c0 5.8-7.5 10.4-7.5 10.4z"/>',
  heartF: '<path d="M12 20.5s-7.5-4.6-7.5-10.4A4.1 4.1 0 0112 7.6a4.1 4.1 0 017.5 2.5c0 5.8-7.5 10.4-7.5 10.4z" fill="currentColor"/>',
};
// Dialogs close only for REAL input. Browser extensions (password managers like Bitwarden, autofill…)
// send fake key / mouse events to drive their own popups — e.g. an Escape — and those used to close
// the dialog you were typing in. Real events are marked isTrusted by the browser; fakes are not.
// A backdrop also needs both the press and the release on itself (dragging out of a field doesn't count).
// And not in the first half second: the second click of an impatient double-click lands on the backdrop of
// the dialog the first click just opened — that used to close it again at once.
function backdropCloses(el, close) {
  let down = false, shown = 0;
  new MutationObserver(() => { if (el.classList.contains('open') || el.classList.contains('on')) shown ||= performance.now(); else shown = 0; })
    .observe(el, { attributes: true, attributeFilter: ['class'] });
  el.addEventListener('pointerdown', e => { down = e.isTrusted && e.target === el && performance.now() - shown > 500; });
  el.addEventListener('click', e => { if (down && e.isTrusted && e.target === el) close(e); down = false; });
}
const ico = (n, s = 19) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ''}</svg>`;

/* ======================= API ======================= */
/* ---------- "working…" pill: any change sent to the server that takes a moment (deleting / renaming / moving
   hundreds of series…) shows what's happening and for how long, so a long operation never looks frozen ---------- */
const WORK = { n: 0, label: '', start: 0, showT: null, hideT: null, tick: null, sub: '' };
function workEl() {
  let el = $('#working');
  if (!el) {
    el = document.createElement('div'); el.id = 'working'; el.className = 'glass'; el.setAttribute('role', 'status');
    el.innerHTML = '<span class="wbook"><i></i><i></i><i></i></span><div><b></b><small></small></div>';
    document.body.appendChild(el);
  }
  return el;
}
function workPaint() {
  const el = workEl(), secs = Math.floor((performance.now() - WORK.start) / 1000);
  el.querySelector('b').textContent = WORK.label;
  el.querySelector('small').textContent = [WORK.sub, secs >= 2 ? `${secs} s` : '', secs >= 8 ? 'big folders take a while — it’s still going' : ''].filter(Boolean).join(' · ');
}
// start(label) → stop(); nested / back-to-back operations share one pill (no flicker between them)
function workStart(label) {
  WORK.label = label; clearTimeout(WORK.hideT);
  if (WORK.n++ === 0 && !$('#working.on')) {
    // on at once: the 350 ms "don't flash for quick jobs" delay lives in CSS (transition-delay), so it still
    // plays when the page is busy re-rendering hundreds of cards and timers can't fire
    WORK.start = performance.now(); WORK.sub = '';
    workPaint(); workEl().classList.add('on');
    clearInterval(WORK.tick); WORK.tick = setInterval(workPaint, 1000);
  } else workPaint();
  let done = false;
  return () => {
    if (done) return; done = true;
    if (--WORK.n > 0) return;
    WORK.hideT = setTimeout(() => { clearInterval(WORK.tick); $('#working')?.classList.remove('on'); WORK.sub = ''; }, 250);
  };
}
function workLabel(method, url, body) {
  const id = url.split('?')[0].split('/')[3] || '', n = body?.ids?.length;
  const sName = S.seriesById?.[id]?.name, colN = S.colById?.[id] ? (S.byCol[id] || []).length : 0;
  const vc = V(S.colById?.[id]?.library), vs = V(S.seriesById?.[id]?.library || S.seriesById?.[body?.ids?.[0]]?.library);
  if (url.startsWith('/api/series/delete')) return `Deleting ${plural(n || 0, vs.s)}…`;
  if (url.startsWith('/api/books/delete')) return `Deleting ${plural(n || 0, 'item')}…`;
  if (url.startsWith('/api/books/move')) return `Moving ${plural(n || 1, 'item')}…`;
  if (url.startsWith('/api/collections/')) {
    if (url.endsWith('/ungroup')) return `Ungrouping ${plural(colN, vc.s)}…`;
    if (method === 'DELETE') return `Deleting ${vc.g} · ${plural(colN, vc.s)}…`;
    return `Renaming ${vc.g} · ${plural(colN, vc.s)}…`;
  }
  if (url.startsWith('/api/series/')) {
    if (url.endsWith('/details')) return 'Saving details…';
    if (url.endsWith('/write')) return `Writing details into ${plural(S.seriesById?.[id]?.books.filter(b => b.unsaved).length || 1, 'file')}…`;
    if (url.endsWith('/move')) return `Moving ${sName || vs.s}…`;
    if (method === 'DELETE') return `Deleting ${sName || vs.s}…`;
    return `Renaming ${sName || vs.s}…`;
  }
  if (url.startsWith('/api/books/')) return method === 'DELETE' ? 'Deleting…' : 'Moving…';
  if (url.startsWith('/api/libraries')) return method === 'DELETE' ? 'Removing library…' : url.includes('/collections') ? 'Creating collection…' : 'Saving library…';
  if (url.startsWith('/api/scan')) return 'Rescanning library…';
  if (url.startsWith('/api/favorites')) return 'Saving favourites…';
  return 'Working…';
}
const _fetch = window.fetch.bind(window);   // the browser's own fetch (used directly by the sign-in checks)
{ // The one place every request passes through:
  //  · a 401 from the API (signed out / session expired) brings up the sign-in screen;
  //  · every non-GET API call shows the working pill (reading progress & sign-in excluded: frequent / instant).
  const guard = (p, url) => p.then(r => { if (r.status === 401 && url.includes('/api/') && !url.includes('/api/auth/')) authLost(); return r; });
  window.fetch = (input, init = {}) => {
    const method = (init.method || 'GET').toUpperCase(), url = typeof input === 'string' ? input : input?.url || '';
    if (method === 'GET' || !url.startsWith('/api/') || url.startsWith('/api/progress') || url.startsWith('/api/auth') || url.startsWith('/api/optimize/estimate') || url.startsWith('/api/jobs') || init.keepalive) return guard(_fetch(input, init), url);
    let body = null; try { body = typeof init.body === 'string' ? JSON.parse(init.body) : null; } catch {}
    const stop = workStart(workLabel(method, url, body));
    return guard(_fetch(input, init), url).finally(stop);
  };
}
const api = {
  async get(u, ms) { const r = await fetch(u, ms ? { signal: AbortSignal.timeout(ms) } : undefined); if (!r.ok) throw new Error(`${r.status} ${u}`); return r.json(); },
  put(u, body) { return fetch(u, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), keepalive: true }).catch(() => {}); },
  del(u) { return fetch(u, { method: 'DELETE' }).catch(() => {}); },
  post(u) { return fetch(u, { method: 'POST' }).then(r => r.json()).catch(() => ({})); },
};
const URLS = {
  cover: (b, w = 480) => `/api/books/${b.id}/cover?w=${w}&v=${b.mtime}-${b.coverPage ?? ''}`,   // a new cover choice = a new address
  page: (b, n) => `/api/books/${b.id}/pages/${n}?v=${b.mtime}`,
  thumb: (b, n, w = 200) => `/api/books/${b.id}/thumbs/${n}?w=${w}&v=${b.mtime}`,
};

/* ======================= PLACEHOLDER ART (books without a cover) ======================= */
function rngFrom(seed) { let a = seed >>> 0; return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function hashStr(s) { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
const hsl = (h, s, l) => `hsl(${((h % 360) + 360) % 360} ${s}% ${l}%)`;
const xml = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function critter(cx, cy, r, hue) {
  const INK = '#15131a', body = hsl(hue, 72, 72), sw = r * .07;
  const eye = s => `<circle cx="${cx + s * r * .32}" cy="${cy - r * .12}" r="${r * .21}" fill="#fff" stroke="${INK}" stroke-width="${sw * .8}"/><circle cx="${cx + s * r * .32}" cy="${cy - r * .1}" r="${r * .11}" fill="${INK}"/>`;
  return `${[-1, 1].map(s => `<ellipse cx="${cx + s * r * .5}" cy="${cy - r * .95}" rx="${r * .19}" ry="${r * .46}" fill="${body}" stroke="${INK}" stroke-width="${sw}" transform="rotate(${s * 14} ${cx + s * r * .5} ${cy - r * .95})"/>`).join('')}
  <ellipse cx="${cx}" cy="${cy}" rx="${r}" ry="${r * .9}" fill="${body}" stroke="${INK}" stroke-width="${sw}"/>${eye(-1)}${eye(1)}
  <ellipse cx="${cx - r * .6}" cy="${cy + r * .18}" rx="${r * .14}" ry="${r * .08}" fill="#ff8fb0"/><ellipse cx="${cx + r * .6}" cy="${cy + r * .18}" rx="${r * .14}" ry="${r * .08}" fill="#ff8fb0"/>
  <path d="M${cx - r * .2} ${cy + r * .2} Q${cx} ${cy + r * .45} ${cx + r * .2} ${cy + r * .2}" fill="none" stroke="${INK}" stroke-width="${sw}" stroke-linecap="round"/>`;
}
const placeholderCache = {};
function placeholderCover(b) {
  if (placeholderCache[b.id]) return placeholderCache[b.id];
  const hue = hashStr(b.series) % 360;
  const words = b.series.toUpperCase().split(' '), lines = [];
  for (const w of words) { const l = lines[lines.length - 1]; if (l && (l + ' ' + w).length <= 13) lines[lines.length - 1] = l + ' ' + w; else lines.push(w); }
  const title = lines.slice(0, 3).map((l, i) => `<text x="300" y="${110 + i * 64}" text-anchor="middle" font-family="Impact,'Arial Black',sans-serif" font-size="58" fill="#fff" stroke="#15131a" stroke-width="9" paint-order="stroke">${xml(l)}</text>`).join('');
  let rays = '';
  for (let j = 0; j < 18; j++) { const a0 = j * Math.PI / 9, a1 = a0 + Math.PI / 18; rays += `<polygon points="300,600 ${300 + 1100 * Math.cos(a0)},${600 + 1100 * Math.sin(a0)} ${300 + 1100 * Math.cos(a1)},${600 + 1100 * Math.sin(a1)}" fill="#fff" opacity=".16"/>`; }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 900"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${hsl(hue, 80, 62)}"/><stop offset="1" stop-color="${hsl(hue + 45, 85, 46)}"/></linearGradient></defs>
    <rect width="600" height="900" fill="url(#g)"/>${rays}<ellipse cx="300" cy="930" rx="420" ry="190" fill="${hsl(hue + 150, 50, 55)}" stroke="#15131a" stroke-width="6"/>
    ${critter(300, 620, 160, hue + 170)}${title}
    <rect x="12" y="12" width="576" height="876" fill="none" stroke="#15131a" stroke-width="8"/></svg>`;
  return (placeholderCache[b.id] = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg));
}
const coverSrc = (b, w) => b.hasCover ? URLS.cover(b, w) : placeholderCover(b);
// any cover <img> that fails falls back to generated art
document.addEventListener('error', e => {
  const img = e.target;
  if (img.tagName === 'IMG' && img.dataset.book && !img.dataset.failed) {
    img.dataset.failed = '1';
    const b = S.books[img.dataset.book]; if (b) img.src = placeholderCover(b);
  }
}, true);
const coverImg = (b, w = 320, extra = '') => b.format === 'video'
  ? `<video class="vcover" src="${URLS.page(b, 0)}#t=1" preload="metadata" muted playsinline data-book="${b.id}" ${extra}></video>`
  : `<img src="${coverSrc(b, w)}" data-book="${b.id}" alt="" loading="lazy" draggable="false" ${extra}>`;

/* ======================= SMOOTH SCROLLING ======================= */
// A library with hundreds of "N new" pills scrolled at ~7 fps: every pill pulsed forever (on screen or not),
// and each pulse made the browser redo the frosted blur behind it. Now only pills on screen pulse, and they
// pause while the page is being scrolled.
(() => {
  const main = document.getElementById('main'); if (!main) return;
  const io = new IntersectionObserver(es => { for (const e of es) e.target.classList.toggle('onscreen', e.isIntersecting); },
    { root: main, rootMargin: '150px 0px' });
  let queued = false;
  new MutationObserver(() => {                        // after each render: watch the new cards (and drop the old)
    if (queued) return; queued = true;
    requestAnimationFrame(() => { queued = false; io.disconnect(); main.querySelectorAll('.card').forEach(c => io.observe(c)); });
  }).observe(main, { childList: true, subtree: true });
  // "scrolling" = the person is scrolling (wheel, touchpad, finger): hover effects and pulses pause meanwhile.
  // Only those start it — not scrolls the browser makes itself (e.g. bringing a half-visible card into view
  // when it's clicked: that once swallowed the click) — and any press ends it at once.
  let t, user = 0;
  const intent = () => { user = performance.now(); };
  main.addEventListener('wheel', intent, { passive: true });
  main.addEventListener('touchmove', intent, { passive: true });
  const stop = () => { clearTimeout(t); main.classList.remove('scrolling'); };
  main.addEventListener('pointerdown', stop, { capture: true });
  main.addEventListener('scroll', () => {
    if (performance.now() - user > 600) return;          // (smooth scrolling glides on after the last wheel turn)
    if (!main.classList.contains('scrolling')) { main.classList.add('scrolling'); FX.measure(); }
    clearTimeout(t); t = setTimeout(stop, 160);
  }, { passive: true });
})();

/* ======================= SMOOTHNESS SWITCHES (⚡ in the top bar) ======================= */
// Each switch turns one effect off (all on = the normal look), remembered in this browser. The meter shows the
// frame rate while the page scrolls: 60 (or your screen's rate) is perfectly smooth.
const FX = (() => {
  const ITEMS = [
    ['pulse-off', 'Pulsing dot', 'on the “N new” pills (on-screen ones only)'],
    ['keep-pulse', 'Pause pulse while scrolling', 'dots hold still while the page moves', true],
    ['pillglass-off', 'Frosted “new” pills', 'blur behind the pill'],
    ['glass-off', 'Frosted badges', 'blur behind small labels'],
    ['glow-off', 'Glow & frames', 'yellow NEW / white READING'],
    ['shadow-off', 'Card shadows', 'soft shadow under every cover (glow too)'],
    ['stack-off', 'Stacked covers', 'covers behind a collection’s front cover'],
    ['intro-off', 'Cards fade in', 'animation when a page opens'],
    ['hover-off', 'Hover lift & shine', 'when the mouse is over a card'],
    ['topglass-off', 'See-through top bar', 'blur behind the search bar while scrolling'],
  ];   // [class, label, hint, inverted?] — the switch shows "on" while the effect is on
  // tablets / phones: the frosted pills & badges were the expensive part there — off by default (switchable)
  let off = new Set(local.get('cf-fx', null) ?? (matchMedia('(pointer: coarse)').matches ? ['pillglass-off', 'glass-off'] : []));
  const apply = () => { for (const [k] of ITEMS) document.body.classList.toggle('fx-' + k, off.has(k)); };
  apply();
  let panel, stats = null;
  const paint = () => {
    if (!panel) return;
    panel.querySelectorAll('[data-fx]').forEach(b => b.classList.toggle('on', !off.has(b.dataset.fx)));
    $('#fxFps').innerHTML = stats ? `${stats.live ? 'Scrolling' : 'Last scroll'}: <b>${stats.fps} fps</b> · slowest frames ${stats.p95} ms`
      : 'Scroll the library to measure';
  };
  function open() {
    if (!panel) {
      panel = document.createElement('div'); panel.id = 'fxPanel';
      panel.innerHTML = `<div class="pop-h">Settings <button class="x" aria-label="Close">✕</button></div>
        <div class="fx-sec">Smoothness <small>turn effects off to see what makes scrolling smoothest</small></div>
        <div id="fxFps"></div>
        ${ITEMS.map(([k, label, hint]) => `<div class="row"><span>${label}<small>${hint}</small></span><button class="switch" data-fx="${k}" aria-label="${label}"></button></div>`).join('')}
        <button class="reset">Turn everything back on</button>`;
      panel.addEventListener('click', e => {
        const sw = e.target.closest('[data-fx]');
        if (sw) { off.has(sw.dataset.fx) ? off.delete(sw.dataset.fx) : off.add(sw.dataset.fx); }
        else if (e.target.closest('.reset')) off = new Set();
        else if (e.target.closest('.x')) return panel.classList.remove('open');
        else return;
        local.set('cf-fx', [...off]); apply(); paint();
      });
      document.body.append(panel);
    }
    panel.classList.toggle('open'); paint();
  }
  // frame-rate meter: runs only while the page scrolls and the panel is open
  let running = false;
  function measure() {
    if (running || !panel?.classList.contains('open')) return;
    running = true;
    const main = document.getElementById('main'), t = []; let last = performance.now(), shown = last;
    const f = now => {
      t.push(now - last); last = now;
      const done = !main.classList.contains('scrolling');
      if (now - shown > 250 || done) {
        shown = now;
        const s = t.slice(1).sort((a, b) => a - b);
        if (s.length > 3) stats = { live: !done, fps: Math.round(1000 / (s.reduce((a, b) => a + b, 0) / s.length)), p95: Math.round(s[Math.floor(s.length * .95)]) };
        paint();
      }
      if (done) { running = false; return; }
      requestAnimationFrame(f);
    };
    requestAnimationFrame(f);
  }
  return { open, measure };
})();
document.getElementById('btnSettings')?.addEventListener('click', () => FX.open());
