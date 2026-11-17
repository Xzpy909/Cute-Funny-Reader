'use strict';
/* Cute&Funny Reader — frontend */

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
  comics:  { s: 'series',     b: 'book', ch: 'chapter', g: 'collection', G_BADGE: 'COLLECTION' },
  cosplay: { s: 'set',        b: 'variant', ch: 'variant', g: 'cosplayer', G_BADGE: 'COSPLAYER' },   // circle → metadata
};
const V = lid => VOCAB[lid && isCosplay(lid) ? 'cosplay' : 'comics'];
// "all libraries" views: Cosplay words only when every library is a Cosplay one
const Vhome = () => S.lib ? V(S.lib) : (S.libraries.length && S.libraries.every(l => isCosplay(l.id)) ? VOCAB.cosplay : VOCAB.comics);

const ICONS = {
  chevL: '<path d="M15 18l-6-6 6-6"/>', chevD: '<path d="M6 9l6 6 6-6"/>', upload: '<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>', chevR: '<path d="M9 18l6-6-6-6"/>',
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
    if (url.endsWith('/details')) return `Saving details into ${plural(S.seriesById?.[id]?.books.length || 1, 'file')}…`;
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
    if (method === 'GET' || !url.startsWith('/api/') || url.startsWith('/api/progress') || url.startsWith('/api/auth') || init.keepalive) return guard(_fetch(input, init), url);
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
  cover: (b, w = 480) => `/api/books/${b.id}/cover?w=${w}&v=${b.mtime}`,
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

/* ======================= STATE ======================= */
const S = {
  libraries: [], books: {}, series: [], seriesById: {}, progress: {}, status: null,
  lib: null, filter: 'all', q: '', sort: local.get('cf-sort', 'recent'), loaded: false,
};
const seriesPrefs = local.get('cf-series', {});
const libOf = id => S.libById?.[id];
const libName = id => libOf(id)?.name || 'Library';
const libType = id => libOf(id)?.type || (libOf(id)?.rtl ? 'manga' : 'comics');
const isCosplay = id => libType(id) === 'cosplay';
const libRtl = b => isCosplay(b.library) ? false : (seriesPrefs[b.seriesId]?.rtl ?? (b.rtl ?? libType(b.library) === 'manga'));
const seriesView = s => seriesPrefs[s.id]?.view || (isCosplay(s.library) ? 'cards' : 'list');   // sets are photos — a cover grid suits them
const seriesSort = s => seriesPrefs[s.id]?.sort || 'asc';
// Soft "blurred cover" backgrounds, baked into a tiny image: no live CSS blur / filter and no extra layers.
// (A filter:blur layer behind the hero made Chrome draw tile seams, and — being its own GPU layer under a
// rounded clip — sometimes stack it *over* the hero's content until something repainted.)
// The picture is shrunk once to 96×144 px on a canvas, softly blurred there (three box-blur passes ≈ a gaussian)
// and given a whisper of grain against banding. (It used to be shrunk to 16×24 and left to the browser to stretch:
// that tiny grid showed through as boxy, star-shaped patches — very visible behind black-and-white manga.)
// Saturation and transparency are baked in too, and `overlay` (a CSS gradient) is layered on top in the same background.
const HERO_GRAD = 'linear-gradient(100deg,rgba(12,11,16,.35),rgba(12,11,16,.82) 55%,rgba(12,11,16,.92))';
const SHERO_GRAD = 'linear-gradient(100deg,rgba(12,11,16,.4),rgba(12,11,16,.9) 60%)';
const blurCache = new Map();
function blurBg(el, url, o = {}) {
  if (!el) return;
  const paint = data => { el.style.backgroundImage = [o.overlay, data && `url("${data}")`].filter(Boolean).join(', '); };
  if (!url) { delete el.dataset.bgsrc; paint(null); return; }
  const key = `${url}|${o.sat || 1}|${o.alpha ?? 1}`;
  el.dataset.bgsrc = key;
  const done = blurCache.get(key);
  if (done) return paint(done);
  if (o.overlay) paint(null);                         // gradient right away, the picture when it's ready
  const img = new Image();
  img.onload = () => {
    try {
      const W = 96, H = 144;
      const c = document.createElement('canvas'); c.width = W; c.height = H;
      const x = c.getContext('2d', { willReadFrequently: true }); x.imageSmoothingQuality = 'high';
      if ((o.alpha ?? 1) < 1) { x.fillStyle = '#0c0b10'; x.fillRect(0, 0, W, H); x.globalAlpha = o.alpha; }
      if (o.sat) x.filter = `saturate(${o.sat})`;     // ignored where canvas filters aren't supported — harmless
      const r = Math.max(W / img.naturalWidth, H / img.naturalHeight), w = img.naturalWidth * r, h = img.naturalHeight * r;
      x.drawImage(img, (W - w) / 2, (H - h) / 2, w, h);
      const px = x.getImageData(0, 0, W, H);
      softBlur(px.data, W, H, 13);
      for (let i = 0; i < px.data.length; i += 4) {     // ±1.5 grain: no visible noise, no banding in dark gradients
        const n = (Math.random() - .5) * 3;
        px.data[i] += n; px.data[i + 1] += n; px.data[i + 2] += n;
      }
      x.putImageData(px, 0, 0);
      const data = c.toDataURL('image/webp', .92);     // (browsers without WebP encoding hand back a PNG)
      if (blurCache.size > 200) blurCache.delete(blurCache.keys().next().value);
      blurCache.set(key, data);
      if (el.dataset.bgsrc === key) paint(data);       // still the same background?
    } catch { if (el.dataset.bgsrc === key) paint(null); }
  };
  img.src = url;
}
// Gaussian-ish blur of RGBA pixels in place: three box blurs, each horizontal then vertical, edges clamped.
function softBlur(d, w, h, radius) {
  const tmp = new Float32Array(d.length), src = new Float32Array(d);
  const box = (from, to, len, stride, count, step, r) => {
    for (let k = 0; k < count; k++) {
      const base = k * step;
      for (let c = 0; c < 4; c++) {
        let acc = 0;
        const at = i => from[base + Math.min(len - 1, Math.max(0, i)) * stride + c];
        for (let i = -r; i <= r; i++) acc += at(i);
        for (let i = 0; i < len; i++) {
          to[base + i * stride + c] = acc / (2 * r + 1);
          acc += at(i + r + 1) - at(i - r);
        }
      }
    }
  };
  const r = Math.max(1, Math.round(radius / 1.73));   // three passes of radius r ≈ one gaussian of radius·
  for (let pass = 0; pass < 3; pass++) {
    box(src, tmp, w, 4, h, w * 4, r);                  // along rows
    box(tmp, src, h, w * 4, w, 4, r);                  // along columns
  }
  for (let i = 0; i < d.length; i++) d[i] = src[i];
}
const fmtPills = x => (x.raw ? '<span class="rawpill" title="Lossless images (PNG / BMP / TIFF)">RAW</span>' : '')
  + (x.jxl ? '<span class="rawpill" title="JPEG XL — converted to PNG when you open it">JPEG XL</span>' : '')
  + (x.heic ? '<span class="rawpill" title="HEIC / HEIF — converted to PNG when you open it">HEIC</span>' : '');
const coverBook = s => s.books.find(b => b.seriesCover) || s.books[0];
const seriesCover = (s, w) => s.books.length ? coverImg(coverBook(s), w) : `<img src="${placeholderCover({ id: s.id, series: s.name })}" alt="" draggable="false">`;
const saveSeriesPref = (sid, patch) => { seriesPrefs[sid] = { ...seriesPrefs[sid], ...patch }; local.set('cf-series', seriesPrefs); };

const prog = b => S.progress[b.id];
const isDone = b => !!prog(b)?.done;
const bookFrac = b => { const p = prog(b); return !p ? 0 : p.done ? 1 : clamp(p.frac ?? 0, 0, 1); };
const inProgress = b => !isDone(b) && bookFrac(b) > 0;
// "unread" = not started: still on the first page (or first section of a novel), never finished
const isUnstarted = b => { const p = prog(b); return !p || (!p.done && (p.page ?? 0) < 1 && (p.chapter ?? 0) < 1 && !(p.scroll > .02)); };
const unstartedCount = s => s.books.filter(isUnstarted).length;
// "new" = never opened. Something you read and then marked unread is unread, but not new again
// (its progress keeps a `seen` note) — no NEW badge, no yellow frame, still in the Unread filter.
// …and only from the library's latest upload: once something newer arrives, older unopened things are
// simply unread. S.newBatch (see latestBatches) holds the ids of each library's most recent batch.
const isNew = b => isUnstarted(b) && !prog(b)?.seen && S.newBatch.has(b.id);
// A batch = everything added without a pause of more than 30 minutes, counted back from the newest book.
S.newBatch = new Set();
const BATCH_GAP = 30 * 60;
function latestBatches() {
  const by = {};
  for (const b of Object.values(S.books)) (by[b.library] ||= []).push(b);
  const out = new Set();
  for (const list of Object.values(by)) {
    list.sort((a, b) => (b.added || 0) - (a.added || 0));
    for (let i = 0; i < list.length; i++) {
      if (i && (list[i - 1].added || 0) - (list[i].added || 0) > BATCH_GAP) break;
      out.add(list[i].id);
    }
  }
  return out;
}
// in the trash, but not moved out of the library yet (the server does that a few minutes later)
const isTrashed = b => !!b.trashed;
const seriesTrashed = s => s.books.length > 0 && s.books.every(isTrashed);
const newCount = s => s.books.filter(isNew).length;
// chapter / set cards: label + frame + glow — reading → white, new (a Cosplay set nobody opened) → yellow,
// finished → plain. Reading wins over new, so a set opened on page 1 isn't both.
const bookGlow = (b, cos) => isDone(b) ? '' : inProgress(b) ? 'g-reading' : cos && isNew(b) ? 'g-new' : '';
const statusBadge = (b, glow) => isDone(b) ? '<span class="badge done">READ</span>'
  : glow === 'g-reading' ? '<span class="badge reading">READING</span>' : glow === 'g-new' ? '<span class="badge new">NEW</span>' : '';
const kindOrder = b => b.kind === 'volume' ? 0 : b.kind === 'chapter' ? 2 : 1;

function buildSeries() {
  S.newBatch = latestBatches();
  const map = {};
  for (const b of Object.values(S.books)) {
    (map[b.seriesId] ||= { id: b.seriesId, name: b.series, library: b.library, books: [] }).books.push(b);
  }
  for (const e of S.empty || []) {
    if (!map[e.seriesId] && S.libById[e.library]) map[e.seriesId] = { id: e.seriesId, name: e.series, library: e.library, books: [], empty: true, added: e.added, collectionId: e.collectionId };
  }
  for (const s of Object.values(map)) {
    if (!s.books.length) { Object.assign(s, { author: '', summary: '', novel: false, genres: [], tags: [] }); continue; }
    s.collectionId = s.books[0].collectionId || null;
    s.books.sort((a, b) => kindOrder(a) - kindOrder(b) || (a.number ?? 1e9) - (b.number ?? 1e9) || a.file.localeCompare(b.file, undefined, { numeric: true }));
    s.author = s.books.find(b => b.author)?.author || '';
    s.publisher = s.books.find(b => b.publisher)?.publisher || '';
    s.raw = s.books.every(b => b.raw);                 // every book lossless (PNG/BMP/TIFF) → RAW pill
    s.jxl = s.books.every(b => b.jxl);                 // every book JPEG XL → JPEG XL pill
    s.heic = s.books.every(b => b.heic);               // every book HEIC / HEIF → HEIC pill
    const uniq = arr => [...new Map(arr.map(t => [t.toLowerCase(), t])).values()];
    s.genres = uniq(s.books.flatMap(b => b.genres || []));
    // series tags = what every *tagged* chapter has (untagged chapters = "no info", they don't veto anything);
    // a tag only some tagged chapters carry stays on those chapters — search finds them one by one.
    // One tagged chapter → its tags are the series' tags.
    const tagged = s.books.filter(b => b.tags?.length);
    const tagSets = tagged.map(b => new Set(b.tags.map(t => t.toLowerCase())));
    s.tags = tagged.length ? uniq(tagged[0].tags.filter(t => tagSets.every(set => set.has(t.toLowerCase())))) : [];
    s.summary = s.books.find(b => b.summary)?.summary || '';
    s.added = Math.max(...s.books.map(b => b.added || 0));
    s.novel = s.books.every(b => b.format === 'epub');
  }
  S.series = Object.values(map);
  S.byCol = {};                                     // collection id → its series (looked up per card, per menu)
  for (const x of S.series) if (x.collectionId) (S.byCol[x.collectionId] ||= []).push(x);
  S.seriesById = map;
}
function seriesInfo(s) {
  if (!s.books.length) return { read: 0, unread: 0, frac: 0, lastRead: 0, reading: false };
  const read = s.books.filter(isDone).length;
  const partial = s.books.reduce((n, b) => n + (isDone(b) ? 0 : bookFrac(b)), 0);
  const lastRead = Math.max(0, ...s.books.map(b => prog(b)?.updated || 0));
  return { read, unread: s.books.length - read, frac: (read + partial) / s.books.length, lastRead, reading: s.books.some(inProgress) || (read > 0 && read < s.books.length) };
}
const nextUp = s => s.books.find(inProgress) || s.books.find(b => !isDone(b)) || s.books[0];
function countLabel(s) {
  if (!s.books.length) return `Empty ${V(s.library).s}`;
  if (isCosplay(s.library)) return plural(s.books.length, V(s.library).b);
  const k = s.books.map(b => b.kind);
  if (k.every(x => x === 'volume')) return plural(s.books.length, 'volume');
  if (k.every(x => x === 'chapter')) return plural(s.books.length, 'chapter');
  return plural(s.books.length, 'book');
}
const progressText = b => {
  const p = prog(b);
  if (!p || (!p.done && !p.frac)) return b.format === 'video' ? 'Video' : b.format === 'epub' ? `${b.pages} sections` : `${b.pages} ${isCosplay(b.library) ? 'photos' : 'pages'}`;
  if (p.done) return 'Finished';
  return b.format === 'epub' ? `${Math.round(p.frac * 100)}% through` : `Page ${(p.page ?? 0) + 1} of ${b.pages}`;
};

/* ======================= LOAD ======================= */
let pollT;
// The server was rebuilt while this tab stayed open → it's still running the old code. Offer a reload
// (never forced: you may be mid-chapter or mid-upload).
const MY_BUILD = document.querySelector('meta[name="cf-build"]')?.content || '';
function checkBuild(st) {
  if (!MY_BUILD || !st?.build || st.build === MY_BUILD || $('#newbuild')) return;
  const el = document.createElement('div');
  el.id = 'newbuild'; el.className = 'glass'; el.setAttribute('role', 'status');
  el.innerHTML = `<span>✨ <b>New version</b> of the reader is installed</span><button class="btn-sm pri" data-reloadapp>Reload</button><button class="nbx" data-nbclose aria-label="Later">×</button>`;
  el.addEventListener('click', e => {
    if (e.target.closest('[data-reloadapp]')) { flushProgress?.(); location.reload(); }
    else if (e.target.closest('[data-nbclose]')) el.remove();
  });
  document.body.appendChild(el);
}
// Pages come screen-sized: the long edge of the screen in device pixels, snapped to the same few sizes as
// the server's cache (a 50 MP photo on a 1440p screen otherwise costs ~150 ms+ to decode, every page turn).
const DISPLAY_SIZES = [1280, 1920, 2560, 3840];
const displayMax = () => { const want = Math.max(screen.width, screen.height, innerWidth, innerHeight) * (devicePixelRatio || 1);
  return DISPLAY_SIZES.find(x => x >= want * 0.95) || DISPLAY_SIZES.at(-1); };
// Look-ahead: decode the next few pages (and the one before) now, and keep them, so a page turn shows a
// picture the browser has already decoded instead of starting from scratch.
function prefetchAround(ids) {
  const want = new Set(), lo = Math.min(...ids), hi = Math.max(...ids);
  for (let i = hi + 1; i <= hi + 4; i++) want.add(i);
  want.add(lo - 1);
  for (const i of [...R.pre.keys()]) if (!want.has(i) && !ids.includes(i)) R.pre.delete(i);
  for (const i of want) {
    const p = R.pages[i]; if (!p || p.video || R.pre.has(i)) continue;
    const im = new Image(); im.decoding = 'async'; im.src = R.guided || R.mode === 'webtoon' ? p.full : p.src;
    im.decode?.().catch(() => {});
    R.pre.set(i, im);
  }
}
// Loading: the page-flip animation (fades in after ¼ s, so quick loads never flash it)
const readerLoader = (text = '') => `<div class="rload" aria-live="polite"><span class="wbook"><i></i><i></i><i></i></span>${text ? `<small>${esc(text)}</small>` : ''}</div>`;
// A page appears — picture, shadow and blurred backdrop together — only once it's decoded. Until then the
// loader shows instead of an empty shadow over a blurred background. Already-decoded pages (look-ahead)
// skip all of this and show at once.
function revealWhenReady(sp, ambientSrc) {
  const imgs = [...sp.querySelectorAll('img.pg')];
  if (imgs.every(im => im.complete && im.naturalWidth)) { setAmbient(ambientSrc); return; }
  sp.classList.add('waiting');
  stage.insertAdjacentHTML('beforeend', readerLoader());
  Promise.all(imgs.map(im => (im.decode ? im.decode() : Promise.resolve()).catch(() => {}))).then(() => {
    if (!sp.isConnected) return;                    // turned the page meanwhile
    sp.classList.remove('waiting');
    stage.querySelector('.rload')?.remove();
    setAmbient(ambientSrc);
  });
}
// Zoom / magnifier want every pixel: swap in the original once it's decoded (no flash in between).
function useFullRes(sp) {
  sp?.querySelectorAll('img.pg').forEach(img => {
    const p = R.pages[+img.dataset.i]; if (!p || img.dataset.full || p.full === p.src) return;
    img.dataset.full = '1';
    const hi = new Image(); hi.src = p.full;
    (hi.decode ? hi.decode() : Promise.resolve()).then(() => { if (img.isConnected) img.src = p.full; }).catch(() => {});
  });
}
const nextFrame = () => new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
async function load() {
  if (!S.me) return;                    // signed out: nothing to load (and no polling behind the sign-in screen)
  // right after a change (delete / rename / move…) the refresh is the slow, page-blocking part: keep the pill up
  const stop = WORK.n > 0 || $('#working.on') ? workStart('Updating your library…') : null;
  const first = !S.loaded;
  if (first) libraryLoading(true);            // no library on screen yet: say it's coming, if it takes a moment
  try {
    // after the first load, the server only sends the books that changed since (see _Feed in main.py)
    const since = S.loaded && S.feed ? `?since=${S.feed.seq}&epoch=${S.feed.epoch}` : '';
    const limit = first ? 20000 : 0;            // a first load that hangs (Docker can hold requests while a container starts)
    const [lib, progress, status, favs] = await Promise.all([api.get('/api/library' + since, limit), api.get('/api/progress', limit), api.get('/api/status', limit),
      api.get('/api/favorites').catch(() => S.favs || [])]);
    if (stop) { workPaint(); await nextFrame(); }   // let the pill paint before the page freezes to re-render
    setFavs(favs);
    S.libraries = lib.libraries; S.libById = Object.fromEntries(lib.libraries.map(l => [l.id, l]));
    if (S.lib && !S.libById[S.lib]) S.lib = null;
    if (lib.full || !S.loaded) S.books = Object.fromEntries(lib.books.map(b => [b.id, b]));
    else if (lib.epoch !== S.feed?.epoch || lib.seq >= S.feed.seq) {      // (an answer older than what we have: skip)
      for (const id of lib.removed) delete S.books[id]; for (const b of lib.books) S.books[b.id] = b; }
    if (lib.full || lib.epoch !== S.feed?.epoch || lib.seq >= S.feed.seq) S.feed = { epoch: lib.epoch, seq: lib.seq };
    S.empty = lib.emptySeries || [];
    S.collections = lib.collections || []; S.colById = Object.fromEntries(S.collections.map(c => [c.id, c]));
    if (S.col && !S.colById[S.col]) S.col = null;
    S.progress = progress; S.status = status; S.loaded = true; checkBuild(status);
    buildSeries();
    renderSidebar();
    route();
    clearTimeout(pollT);
    if (status.scanning) pollT = setTimeout(load, 2500);
  } catch (e) {
    if (e instanceof TypeError || e.name === 'TimeoutError') serverGone(true);    // no answer (failed / hung): the server is away
    else { $('#hero').innerHTML = `<div class="empty" style="grid-column:1/-1">Couldn’t load the library (${esc(e.message)}). Retrying…</div>`; pollT = setTimeout(load, 4000); }
  } finally {
    if (stop) { await nextFrame(); stop(); }      // stop once the new page is on screen
    if (first) libraryLoading(false);
  }
}
async function refreshStatus() {
  if (!S.me) return;
  try {
    const prev = S.status?.rev;
    S.status = await api.get('/api/status'); renderServer(); checkBuild(S.status);
    if (S.status.rev !== prev || S.status.libraries !== S.libraries.length || S.status.books !== Object.keys(S.books).length) load();
  } catch (e) { if (e instanceof TypeError) serverGone(true); }
}

/* ======================= SIDEBAR ======================= */
const sideOpen = on => document.querySelector('.app').classList.toggle('side-open', on);
$('#btnSide').onclick = () => sideOpen(true);
$('#sideShade').onclick = () => sideOpen(false);
$('.side').addEventListener('click', e => { if (e.target.closest('[data-lib], [data-nav]')) setTimeout(() => sideOpen(false), 120); });
function renderSidebar() {
  const sInfo = S.series.map(s => [s, seriesInfo(s)]);
  $('#nReading').textContent = sInfo.filter(([, i]) => i.reading).length || '';
  $('#nUnread').textContent = sInfo.filter(([, i]) => i.read === 0 && i.frac === 0).length || '';
  $('#nDone').textContent = sInfo.filter(([, i]) => i.unread === 0).length || '';
  $('#nFavs').textContent = S.favs.reduce((n, f) => n + favItems(f).length, 0) || '';
  $('#libNav').innerHTML = S.libraries.map(l =>
    `<button data-lib="${l.id}" class="${S.lib === l.id ? 'on' : ''}"><span class="dot" style="background:${esc(l.color)}"></span>${esc(l.name)} <span class="count">${l.series || ''}</span></button>`).join('');
  $$('#mainNav button').forEach(b => b.classList.toggle('on', S.inFavs ? b.dataset.nav === 'favs' : !S.lib && b.dataset.nav === (S.filter === 'all' ? 'home' : S.filter)));
  renderServer();
}
function renderServer() {
  const st = S.status; if (!st) return;
  $('#srvState').textContent = st.error ? 'Library error' : st.scanning ? 'Scanning…'
    : st.preparing ? `Preparing ${plural(st.preparing, Vhome().b)}…` : 'Server online';
  $('#server .dot').style.background = st.error ? 'var(--pop)' : '';
  $('#srvBooks').textContent = st.error ? st.error : `${plural(st.series, 'series')} · ${plural(st.books, 'book')}`;
  $('#srvScan').textContent = `last scan ${ago(st.lastScan)} · v${st.version}`;
  $('#btnRescan').disabled = st.scanning;
  $('#btnRescan svg').classList.toggle('spin', !!st.scanning);
}

/* ======================= HOME ======================= */
const FILTERS = [['all', 'All'], ['reading', 'Reading'], ['unread', 'Unread'], ['done', 'Finished'], ['comics', 'Comics'], ['novels', 'Novels']];
function renderHome() {
  if (!$('#viewHome').classList.contains('on')) VG.back = true;       // coming back from another page
  $('#viewHome').classList.add('on'); $('#viewSeries').classList.remove('on');
  const noLibs = !S.libraries.length;
  $('#welcome').classList.toggle('on', noLibs);
  $('#homeBody').style.display = noLibs ? 'none' : '';
  if (noLibs) return renderWelcome();
  const hr = new Date().getHours();
  $('#greet').textContent = (hr < 5 ? 'Up late' : hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening') + ' — pick up where you left off';

  const col = S.col && S.colById[S.col];
  $('#greet').style.display = $('#hero').style.display = col ? 'none' : '';
  const st = S.status;
  $('#banner').innerHTML = st?.scanning && !S.series.length
    ? `<div class="banner"><div class="loader" style="width:20px;height:20px;border-width:3px;margin:0"></div>Scanning your library for the first time…</div>`
    : st?.error ? `<div class="banner">⚠ ${esc(st.error)}</div>` : '';

  // hero: most recently read, unfinished book
  const recent = Object.entries(S.progress)
    .filter(([id, p]) => S.books[id] && !S.books[id].trashed && !p.done && p.frac > 0 && (!S.lib || S.books[id].library === S.lib))
    .sort((a, b) => (b[1].updated || 0) - (a[1].updated || 0)).map(([id]) => S.books[id]);
  const fresh = S.series.filter(x => x.books.length && !seriesTrashed(x) && (!S.lib || x.library === S.lib)).sort((a, b) => b.added - a.added);
  const hb = recent[0] || (fresh[0] && nextUp(fresh[0]));
  $('#hero').classList.toggle('bare', !hb);
  $('#chips').style.display = hb ? '' : 'none';
  if (!hb) {
    blurBg($('#hero'), '');                          // bare hero (drop zone): no backdrop
    $('#hero').innerHTML = dropzoneHTML(S.lib || S.libraries[0].id);
  } else {
    const s = S.seriesById[hb.seriesId], started = !!prog(hb);
    const others = recent.filter(b => b.seriesId !== hb.seriesId).filter((b, i, a) => a.findIndex(x => x.seriesId === b.seriesId) === i).slice(0, 4);
    const side = others.length ? others : fresh.filter(x => x.id !== s.id).slice(0, 4).map(nextUp);
    $('#hero').innerHTML = `
      
      <button class="hero-cover" data-open="${hb.id}" aria-label="Open">${coverImg(hb, 480)}</button>
      <div class="hero-info">
        <div class="eyebrow">${started ? 'Continue reading' : 'Start something new'}</div>
        <h1 class="${s.name.length > 60 ? 'xl' : s.name.length > 32 ? 'l' : ''}">${escWrap(s.name)}</h1>
        <div class="hero-meta">${escWrap(hb.label)}${hb.title ? ' · ' + escWrap(hb.title) : ''} · ${progressText(hb)}</div>
        <div class="bar"><i style="width:${Math.round(bookFrac(hb) * 100)}%"></i></div>
        <p class="blurb">${esc((s.summary || `${countLabel(s)} in your ${libName(s.library)} library${s.author ? ' · by ' + s.author : ''}.`).slice(0, 260))}</p>
        <div class="actions">
          <button class="btn-primary" data-open="${hb.id}">${ico('play')} ${started ? 'Resume' : 'Start reading'}</button>
          ${s.books.length > 1 ? `<button class="btn-ghost" data-series="${s.id}">${ico('book', 17)} Series</button>` : ''}
        </div>
      </div>
      <div class="upnext">
        <div class="eyebrow">${others.length ? 'Also in progress' : 'Recently added'}</div>
        ${side.map(b => `<button class="mini" data-open="${b.id}">${coverImg(b, 120)}<div><b>${escWrap(b.series)}</b><small>${escWrap(b.label)} · ${progressText(b)}</small><div class="bar"><i style="width:${Math.round(bookFrac(b) * 100)}%"></i></div></div></button>`).join('')}
      </div>`;
    blurBg($('#hero'), hb.hasCover ? URLS.cover(hb, 120) : '', { sat: 1.5, alpha: .55, overlay: HERO_GRAD });
  }

  // shelf
  $('#chips').innerHTML = FILTERS.map(([k, t]) => `<button class="chip ${k === S.filter ? 'on' : ''}" data-filter="${k}">${t}</button>`).join('');
  if (col) $('#chips').style.display = '';
  $('#sort').value = S.sort;
  $('#colCrumb').innerHTML = col ? `<button class="crumb" data-libback="${col.library}">${ico('chevL', 16)} ${esc(libName(col.library))}</button>` : '';
  $('#shelfTitle').innerHTML = col ? `<span class="colicon">🗂️</span>${esc(col.name)}` : esc(S.lib ? libName(S.lib) : 'Your shelf');
  const pickTarget = col ? col.library : S.lib || (S.libraries.length === 1 ? S.libraries[0].id : '');
  const selOn = S.sel && S.selMode === 'series';
  $('#viewHome').classList.toggle('selecting', !!selOn);
  $('#libActions').innerHTML = (pickTarget ? `<button class="btn-sm pri" data-pick="${pickTarget}" ${col ? `data-pickcol="${esc(col.folder)}"` : ''}>+ Add files</button>` : '')
    + (S.series.length ? `<button class="btn-sm ${selOn ? 'pri' : ''}" data-select>${selOn ? 'Done selecting' : '☑ Select files'}</button>` : '')
    + (col ? `<button class="btn-sm" data-more="collection:${col.id}">⋯ Collection</button>`
      : pickTarget ? `<button class="btn-sm" data-newcol="${pickTarget}">+ New ${V(pickTarget).g}</button>` : '')
    + (S.lib && !col ? `<button class="btn-sm" data-editlib="${S.lib}">${ico('sliders', 15)} Edit library</button>` : '');

  const q = normQ(S.q);
  const flat = !!q || S.filter !== 'all';          // searching/filtering looks inside collections too
  const hits = [];                                // chapters found by a tag the rest of their series doesn't have
  const bookOk = (b, s) => S.filter === 'reading' ? inProgress(b) : S.filter === 'unread' ? isUnstarted(b) : S.filter === 'done' ? isDone(b)
    : S.filter === 'comics' ? !s.novel : S.filter === 'novels' ? s.novel : true;
  let list = S.series.map(s => [s, seriesInfo(s)]).filter(([s, i]) => {
    if (S.lib && s.library !== S.lib) return false;
    if (col ? s.collectionId !== col.id : (!flat && s.collectionId)) return false;
    if (q && ![s.name, s.author, s.publisher, libName(s.library), S.colById[s.collectionId]?.name, ...(s.genres || []), ...(s.tags || [])].map(normQ).join(' ').includes(q)) {
      const found = s.books.filter(b => (b.tags || []).some(t => normQ(t).includes(q)));
      if (!found.length) return false;
      if (found.length < s.books.filter(b => b.tags?.length).length) { hits.push(...found.filter(b => bookOk(b, s))); return false; }
      // every tagged chapter matches (maybe through different tags) → it's the series that matches
    }
    if (S.filter === 'reading' && !i.reading) return false;
    if (S.filter === 'unread' && (i.read > 0 || i.frac > 0)) return false;
    if (S.filter === 'done' && i.unread > 0) return false;
    if (S.filter === 'comics' && s.novel) return false;
    if (S.filter === 'novels' && !s.novel) return false;
    return true;
  });
  if (S.sort === 'title') list.sort((a, b) => a[0].name.localeCompare(b[0].name));
  else if (S.sort === 'added') list.sort((a, b) => b[0].added - a[0].added);
  else list.sort((a, b) => b[1].lastRead - a[1].lastRead || b[0].added - a[0].added);
  const cols = col || flat ? [] : S.collections.filter(c => !S.lib || c.library === S.lib).sort((a, b) => a.name.localeCompare(b.name));

  S.visibleSeries = list.map(([x]) => x.id);
  const Vh = col ? V(col.library) : Vhome();
  $('#stats').textContent = [cols.length ? plural(cols.length, Vh.g) : '', plural(list.length, Vh.s), plural(list.reduce((n, [s]) => n + s.books.length, 0), Vh.b),
    hits.length ? `${plural(hits.length, 'single chapter')} by tag` : ''].filter(Boolean).join(' · ');
  const weekAgo = Date.now() / 1000 - 7 * 86400;
  // front cover live; the ones behind it come as one picture drawn by the server (much cheaper to scroll).
  // Generated placeholder art can't be drawn there — such stacks stay as before.
  const stackCovers = covers => {
    if (!covers.length) return '<div class="stk s0 emptycol">🗂️</div>';
    const back = covers.slice(1).map(coverBook);
    if (back.length && back.every(b => b.hasCover && b.format !== 'video'))
      return `<div class="stk s0">${seriesCover(covers[0], 200)}</div><img class="stkback" src="/api/stack?books=${back.map(b => b.id).join(',')}&v=${back.map(b => b.mtime).join('-')}" alt="" loading="lazy" draggable="false">`;
    return covers.map((x, j) => `<div class="stk s${j}">${seriesCover(x, 200)}</div>`).join('');
  };
  const colCards = cols.map((c, k) => {
    const inside = S.byCol[c.id] || [];
    const covers = inside.filter(x => x.books.length).slice(0, 3);
    const read = inside.reduce((n, x) => n + seriesInfo(x).frac, 0) / (inside.length || 1);
    const unreadSeries = inside.filter(x => x.books.length && newCount(x) > 0).length;
    return `<button class="card colcard ${inside.length && inside.every(seriesTrashed) ? 'trashed' : unreadSeries ? 'unread' : ''}" data-collection="${c.id}" style="--d:${Math.min(k, 20) * 30}ms">
      <div class="cover stack">${stackCovers(covers)}
        <span class="badge fmt">${V(c.library).G_BADGE}</span>${unreadSeries ? `<span class="ubub" title="${plural(unreadSeries, V(c.library).s)} with unread ${pl(V(c.library).ch)}"><i></i><b>${unreadSeries > 99 ? '99+' : unreadSeries}</b> new</span>` : ''}</div>
      <div class="pbar"><i style="width:${Math.round(read * 100)}%"></i></div>
      <div class="ct">${escWrap(c.name)}</div>
      <div class="cm">${inside.length ? plural(inside.length, V(c.library).s) : `Empty ${V(c.library).g}`}</div>
    </button>`;
  });
  const seriesCard = ([s, i], k) => {
    const b0 = s.books[0];
    const badge = i.unread === 0 && s.books.length ? '<span class="badge done">READ</span>'
      : i.frac === 0 && newCount(s) ? '<span class="badge new">NEW</span>' : '';   // from the library's latest upload, never opened
    // ComicInfo <Genre> is the type of release (Manga, Doujinshi, Manhwa…): it names the badge
    const fmt = !b0 ? '' : s.genres?.length ? s.genres[0].toUpperCase().slice(0, 18) : s.novel ? 'NOVEL' : s.books.every(x => x.format === 'video') ? '▶ VIDEO' : s.books.some(x => x.videos?.length) ? '▶ + PHOTOS' : libRtl(b0) ? 'RTL' : '';
    const one = s.books.length === 1;
    const unread = s.books.length ? newCount(s) : 0;
    const bubble = unread && !one ? `<span class="ubub" title="${plural(unread, 'chapter')} not started yet"><i></i><b>${unread > 99 ? '99+' : unread}</b> new</span>` : '';
    return `<button class="card ${seriesTrashed(s) ? 'trashed' : unread ? 'unread' : ''} ${selOn && S.sel.has(s.id) ? 'sel' : ''}" data-series="${s.id}" ${one ? `data-single="${b0.id}"` : ''} style="--d:${Math.min(k + cols.length, 20) * 30}ms">
      <div class="cover">${seriesCover(s, 320)}${s.empty ? '<span class="badge fmt">EMPTY</span>' : badge}${fmt ? `<span class="badge fmt">${fmt}</span>` : ''}${s.raw || s.jxl || s.heic || bubble ? `<div class="blc">${bubble}${fmtPills(s)}</div>` : ''}<span class="check">✓</span></div>
      <div class="pbar"><i style="width:${Math.round(i.frac * 100)}%"></i></div>
      <div class="ct" ${one && b0.title && normQ(b0.title) !== normQ(s.name) ? `title="${esc(b0.title)}"` : ''}>${esc(s.name)}</div>
      <div class="cm">${one ? progressText(b0) : countLabel(s)}${s.author ? ` · <span class="au">${esc(s.author)}</span>` : ''}${!one && i.unread && i.unread < s.books.length ? ` · ${i.unread} unread` : ''}${flat && s.collectionId ? ` · 🗂️ ${esc(S.colById[s.collectionId]?.name || '')}` : ''}</div>${cardTags(s)}
    </button>`;
  };
  // Home (all libraries, no filter, no search): rows instead of one long shelf
  const rowsMode = !S.lib && !col && !flat && !selOn;
  $('#homeBody').classList.toggle('rowsmode', rowsMode);
  if (rowsMode) { VG.cards = null; $('#grid').textContent = ''; return renderRows(seriesCard); }
  const seriesCards = list.map(seriesCard);
  const hitCards = hits.map((b, k) => hitCard(b, k + seriesCards.length));
  const cards = [...colCards, ...seriesCards, ...hitCards];
  if (cards.length) return fillGrid($('#grid'), cards);
  VG.cards = null;
  $('#grid').innerHTML = col ? `<div class="dropzone"><div class="big">🗂️</div><h3>${esc(col.name)} is empty</h3>
        <p>Drop <b>.cbz</b>/<b>.epub</b> files or whole folders onto this window to add ${pl(V(col.library).s)} to this ${V(col.library).g},<br>or move existing ${pl(V(col.library).s)} here with their <b>⋯</b> menu.</p>
        <button class="btn-primary" data-pick="${col.library}" data-pickcol="${esc(col.folder)}">Choose files</button></div>`
    : !hb && !S.series.some(x => !S.lib || x.library === S.lib) ? '' : `<div class="empty">Nothing matches — try another filter or search.</div>`;
}

// Home: a few rows to pick from. Each is a strip you scroll sideways (wheel on a touchpad, swipe, or the ‹ ›
// buttons); "See all" opens the matching full list. The full shelves live in the libraries.
const ROW_CARDS = 18;
function dayShuffle(list) {                    // a different order every day, the same all day (no reshuffle on redraw)
  const day = Math.floor(Date.now() / 86400000);
  const h = id => { let x = day; for (let i = 0; i < id.length; i++) x = (x * 31 + id.charCodeAt(i)) >>> 0; return x; };
  return list.map(x => [h(x[0].id), x]).sort((a, b) => a[0] - b[0]).map(x => x[1]);
}
function renderRows(seriesCard) {
  const all = S.series.filter(s => s.books.length && !seriesTrashed(s)).map(s => [s, seriesInfo(s)]);
  const rows = [
    ['Recently read', 'Pick up where you left off', 'reading', all.filter(([, i]) => i.lastRead > 0 && i.unread > 0).sort((a, b) => b[1].lastRead - a[1].lastRead)],
    ['Recently added', 'The newest arrivals', null, [...all].sort((a, b) => b[0].added - a[0].added)],
    ['Discover', 'Not started yet — a new mix every day', 'unread', dayShuffle(all.filter(([, i]) => i.read === 0 && i.frac === 0))],
    ['Finished', 'Read again', 'done', all.filter(([, i]) => i.unread === 0).sort((a, b) => b[1].lastRead - a[1].lastRead)],
  ].filter(r => r[3].length);
  const html = rows.map(([title, sub, nav, list]) => `<section class="hrow">
      <div class="shelf-h slim"><div><h2>${title}</h2><p>${sub}${list.length > ROW_CARDS ? ` · ${list.length}` : ''}</p></div>
        <div class="shelf-actions"><button class="ib hnav" data-hscroll="-1" aria-label="Scroll left">‹</button><button class="ib hnav" data-hscroll="1" aria-label="Scroll right">›</button>
          ${nav ? `<button class="btn-sm" data-nav="${nav}">See all</button>` : ''}</div></div>
      <div class="hstrip">${list.slice(0, ROW_CARDS).map(seriesCard).join('')}</div></section>`).join('');
  const el = $('#rows');
  if (el._html !== html) { el._html = html; el.innerHTML = html; }       // unchanged → leave it (no flicker, keeps scroll)
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-hscroll]'); if (!b) return;
  const strip = b.closest('.hrow').querySelector('.hstrip');
  strip.scrollBy({ left: +b.dataset.hscroll * strip.clientWidth * .85, behavior: 'smooth' });
});

// Drawing the shelf: only the cards near the screen exist on the page.
// A library with 2000+ cards scrolled at under 20 frames a second however few effects were on — the browser has
// to account for every card on every frame. So the grid holds about VG_CARDS cards: the rows on screen plus a
// few above and below. Blank spacers above and below stand in for the rest, so the scrollbar still spans the
// whole library; scrolling adds rows ahead and drops them behind.
//  · Row heights differ (titles wrap), so each row is measured when it's drawn; rows not drawn yet count as average.
//  · A redraw after a change keeps the cards whose HTML didn't change (each remembers the HTML it was made from).
const VG_CARDS = 60;
const VG = { el: null, cards: null, keys: null, start: 0, end: 0, cols: 0, rowH: [], avg: 0, top: null, bot: null, lastTop: null, back: false };
// card titles: a name without spaces (Some.Dotted.Name, some_name) may wrap after its dots / underscores
const escWrap = t => esc(t).replace(/([._])(?=[^\s._])/g, '$1<wbr>');
const cardKey = html => { const m = /data-(collection|series|open|favlist)="([^"]*)"/.exec(html.slice(0, html.indexOf('>') + 1)); return m ? m[1] + ':' + m[2] : null; };
const cardNorm = html => html.replace(/--d:\d+ms/, '');          // (the fade-in delay depends on position only)
const cardTpl = document.createElement('template');
function fillGrid(el, cards) {
  const keys = cards.map(cardKey), main = $('#main');
  if (!(keys.every(Boolean) && new Set(keys).size === keys.length)) { VG.cards = null; el.innerHTML = cards.join(''); return; }   // (never expected)
  const view = gridView(), same = VG.el === el && !!VG.cards && el.dataset.gridview === view && VG.top?.parentNode === el;
  el.dataset.gridview = view;                 // (not "view": data-view is the cards/list switch on series pages)
  if (!same) {
    el.textContent = '';
    VG.top = document.createElement('div'); VG.bot = document.createElement('div');
    VG.top.className = VG.bot.className = 'vspace'; VG.top.hidden = VG.bot.hidden = true;
    el.append(VG.top, VG.bot);
    VG.rowH = []; VG.avg = 0; VG.start = VG.end = 0;
  }
  Object.assign(VG, { el, cards, keys });
  if (same && VG.back && VG.lastTop != null) {     // back on the shelf after a series page: where you were
    main.style.scrollBehavior = 'auto'; main.scrollTop = VG.lastTop; main.style.scrollBehavior = '';
  }
  VG.back = false;
  vgRender(true, !same);
}
// Put the right rows on the page. force: redraw even if the rows on the page still cover the screen.
function vgRender(force, intro) {
  const { el, cards, keys } = VG;
  if (!el || !cards || !el.isConnected || VG.top?.parentNode !== el) return;
  const cs = getComputedStyle(el), tracks = cs.gridTemplateColumns;
  if (!tracks || tracks === 'none' || !el.offsetParent) return;               // the shelf isn't showing
  const cols = tracks.split(' ').length, gap = parseFloat(cs.rowGap) || 0, main = $('#main');
  if (cols !== VG.cols) { VG.cols = cols; VG.rowH = []; VG.avg = 0; force = true; }
  const rows = Math.ceil(cards.length / cols), h = r => VG.rowH[r] || VG.avg || 400;
  const offset = r => { let y = 0; for (let i = 0; i < r; i++) y += h(i); return y; };
  const y = main.scrollTop - (el.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop), vh = main.clientHeight;
  let r0 = 0, acc = 0; while (r0 < rows - 1 && acc + h(r0) <= y) acc += h(r0++);       // first row on screen
  let r1 = r0; while (r1 < rows && acc < y + vh) acc += h(r1++);                       // one past the last
  if (!force && (r0 - 1 >= VG.start || VG.start === 0) && (r1 + 1 <= VG.end || VG.end >= rows)) return;
  const want = Math.max(Math.ceil(VG_CARDS / cols), r1 - r0 + 4);
  let start = Math.max(0, r0 - Math.floor((want - (r1 - r0)) / 2));
  const end = Math.min(rows, start + want); start = Math.max(0, end - want);
  const spacers = () => {
    const t = start ? offset(start) - gap : 0, b = end < rows ? offset(rows) - offset(end) - gap : 0;
    VG.top.hidden = t <= 0; VG.top.style.height = Math.max(0, t) + 'px';
    VG.bot.hidden = b <= 0; VG.bot.style.height = Math.max(0, b) + 'px';
  };
  const before = offset(r0) - offset(start);                                          // rows above the screen, as assumed
  spacers();
  // the cards of rows start…end, keeping the ones already there
  const from = start * cols, to = Math.min(cards.length, end * cols), want_k = new Set(keys.slice(from, to)), old = new Map();
  for (const c of [...el.children]) {
    if (c === VG.top || c === VG.bot) continue;
    if (c._k && want_k.has(c._k) && !old.has(c._k)) old.set(c._k, c); else c.remove();
  }
  let ref = VG.top.nextElementSibling;
  for (let i = from; i < to; i++) {
    const k = keys[i], norm = cardNorm(cards[i]);
    let node = old.get(k);
    if (!node || node._h !== norm) {
      cardTpl.innerHTML = cards[i];
      const n = cardTpl.content.firstElementChild; n._k = k; n._h = norm;
      if (node || !intro) n.style.animation = 'none';      // fade in only when a view opens, not while scrolling
      if (node) {
        if (node.classList.contains('onscreen')) n.classList.add('onscreen');
        if (ref === node) ref = n;
        node.replaceWith(n);
      }
      node = n;
    }
    if (node === ref) ref = ref.nextElementSibling; else el.insertBefore(node, ref);
  }
  VG.start = start; VG.end = end;
  // measure the rows now on the page (offsetTop: unaffected by hover lifts and fade-ins)
  const kids = []; for (let c = VG.top.nextElementSibling; c && c !== VG.bot; c = c.nextElementSibling) kids.push(c);
  const hadAvg = VG.avg;
  for (let r = start; r < end; r++) {
    const first = kids[(r - start) * cols], next = kids[(r - start + 1) * cols];
    if (!first) break;
    if (next) VG.rowH[r] = next.offsetTop - first.offsetTop;
    else { let bottom = 0; for (let j = (r - start) * cols; j < kids.length; j++) bottom = Math.max(bottom, kids[j].offsetTop + kids[j].offsetHeight); VG.rowH[r] = bottom - first.offsetTop + gap; }
  }
  if (!hadAvg) { let sum = 0, n = 0; for (let r = start; r < end; r++) if (VG.rowH[r]) { sum += VG.rowH[r]; n++; } if (n) VG.avg = sum / n; spacers(); }
  // rows above the screen turned out taller/shorter than assumed: browsers without scroll anchoring (Safari) would jump
  const drift = offset(r0) - offset(start) - before;
  if (drift && hadAvg && !CSS.supports('overflow-anchor', 'auto')) { main.style.scrollBehavior = 'auto'; main.scrollTop += drift; main.style.scrollBehavior = ''; }
}
{ const main = $('#main'); let queued = false;
  main.addEventListener('scroll', () => {
    if (VG.cards && VG.el?.offsetParent) VG.lastTop = main.scrollTop;
    if (queued) return; queued = true;
    requestAnimationFrame(() => { queued = false; vgRender(false); });
  }, { passive: true });
  new ResizeObserver(() => vgRender(true)).observe(main);
}
// Once a card's fade-in has played, drop it: finished animations still cost the browser on every frame.
document.addEventListener('animationend', e => { if (e.animationName === 'rise' && e.target.classList?.contains('card')) e.target.style.animation = 'none'; });
const gridView = () => [location.hash, S.lib, S.col, S.filter, S.q, S.sort].join('|');

// a single chapter / set in search results (found by a tag only it has) — its series is named underneath
function hitCard(b, k) {
  const s = S.seriesById[b.seriesId], cos = isCosplay(b.library);
  const glow = bookGlow(b, cos);
  return `<button class="card ch hit ${isDone(b) ? 'done' : ''} ${b.trashed ? 'trashed' : glow}" data-open="${b.id}" style="--d:${Math.min(k, 20) * 30}ms">
    <div class="cover">${coverImg(b, 320)}${statusBadge(b, glow)}<span class="badge fmt">${cos ? V(b.library).b.toUpperCase() : b.kind === 'volume' ? 'VOLUME' : 'CHAPTER'}</span>${b.raw || b.jxl || b.heic ? `<div class="blc">${fmtPills(b)}</div>` : ''}</div>
    <div class="pbar"><i style="width:${Math.round(bookFrac(b) * 100)}%"></i></div>
    <div class="ct">${escWrap(s && s.books.length > 1 ? b.label + (b.title ? ' · ' + b.title : '') : b.title || b.label)}</div>
    <div class="cm">in ${esc(s?.name || b.series)}</div>
  </button>`;
}

/* ======================= SERIES PAGE ======================= */
// ♀ / ♂ disambiguate tags (metadata.json); searching ignores them, so "cute ♀" also finds a plain "cute"
const normQ = v => String(v || '').replace(/[♀♂]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
const tagHue = t => [...normQ(t)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
const allTagsOf = s => [...(s.genres || []).slice(1), ...(s.tags || [])];
function cardTags(s) {
  const all = allTagsOf(s);
  if (!all.length) return '';
  return `<div class="ctags"><span class="tagbtn" role="button" tabindex="0" data-tagpop="${s.id}" title="Show tags">
    <span class="tdots">${all.slice(0, 4).map(t => `<i style="--h:${tagHue(t)}"></i>`).join('')}</span>${plural(all.length, 'tag')}<span class="car">▾</span></span></div>`;
}
/* tag bubble: unrolls under the card's Tags button with every genre + tag as coloured chips */
function closeTagPop() { const p = $('#tagpop'); if (!p) return; p.remove(); $$('.tagbtn.open').forEach(b => b.classList.remove('open')); }
function openTagPop(btn) {
  const s = S.seriesById[btn.dataset.tagpop]; if (!s) return;
  const was = btn.classList.contains('open');
  closeTagPop(); if (was) return;
  btn.classList.add('open');
  const pop = document.createElement('div');
  pop.id = 'tagpop'; pop.className = 'tagpop';
  pop.innerHTML = `<div class="tp-h">${esc(s.name)}</div><div class="tp-b">${allTagsOf(s).map((t, i) =>
    `<span class="ctag ${i < Math.max(0, (s.genres || []).length - 1) ? 'genre' : ''} ${/♀/.test(t) ? 'fem' : /♂/.test(t) ? 'male' : ''}" role="button" data-tag="${esc(t)}" style="--h:${tagHue(t)};--i:${i}">${esc(t)}</span>`).join('')}</div>`;
  document.body.append(pop);
  const r = btn.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
  const left = clamp(r.left + r.width / 2 - w / 2, 10, innerWidth - w - 10);
  const below = r.bottom + 10 + h < innerHeight - 10;
  Object.assign(pop.style, { left: left + 'px', top: (below ? r.bottom + 10 : r.top - 10 - h) + 'px' });
  pop.style.setProperty('--ax', clamp(r.left + r.width / 2 - left, 18, w - 18) + 'px');
  pop.classList.add(below ? 'down' : 'up');
  requestAnimationFrame(() => pop.classList.add('on'));
}
document.addEventListener('pointerdown', e => { if ($('#tagpop') && !e.target.closest('#tagpop, [data-tagpop]')) closeTagPop(); });
window.addEventListener('hashchange', closeTagPop);
document.addEventListener('scroll', e => { if (!e.target.closest?.('#tagpop')) closeTagPop(); }, true);
window.addEventListener('resize', closeTagPop);
document.addEventListener('keydown', e => { if (e.isTrusted && e.key === 'Escape' && $('#tagpop')) { e.stopImmediatePropagation(); closeTagPop(); } }, true);
function tagChips(genres = [], tags = [], max = 16, release = '') {
  if (!genres.length && !tags.length && !release) return '';
  const shown = tags.slice(0, Math.max(0, max - genres.length));
  return `<div class="tagrow">${release ? `<span class="tag rel">${esc(release)}</span>` : ''}${genres.map(g => `<button class="tag g" data-tag="${esc(g)}">${esc(g)}</button>`).join('')}${shown.map(t => `<button class="tag" data-tag="${esc(t)}">#${esc(t)}</button>`).join('')}${tags.length > shown.length ? `<span class="tag more">+${tags.length - shown.length}</span>` : ''}</div>`;
}
function chapterCard(b, k) {
  const sel = S.sel?.has(b.id);
  const glow = bookGlow(b, isCosplay(b.library));
  const badge = statusBadge(b, glow) + (b.release ? `<span class="badge fmt">${esc(b.release.toUpperCase())}</span>` : b.format === 'video' ? '<span class="badge fmt">▶ VIDEO</span>' : '');
  return `<button class="card ch ${isDone(b) ? 'done' : ''} ${b.trashed ? 'trashed' : glow} ${sel ? 'sel' : ''}" data-open="${b.id}" style="--d:${Math.min(k, 24) * 22}ms">
    <div class="cover">${coverImg(b, 320)}${badge}<span class="check">✓</span></div>
    <div class="pbar"><i style="width:${Math.round(bookFrac(b) * 100)}%"></i></div>
    <div class="ct">${escWrap(b.label)}</div>
    <div class="cm">${esc(b.title || progressText(b))}</div>
  </button>`;
}
function chapterRow(b, k) {
  return `<div class="brow ${isDone(b) ? 'done' : ''} ${b.trashed ? 'trashed' : ''} ${S.sel?.has(b.id) ? 'sel' : ''}" data-open="${b.id}" role="button" tabindex="0" style="--d:${Math.min(k, 30) * 20}ms">
    ${coverImg(b, 120)}
    <div style="min-width:0"><b>${esc(b.label)}</b>${isCosplay(b.library) && isNew(b) ? '<span class="newpill">NEW</span>' : ''}<span class="bt">${esc(b.title || `${b.format === 'video' ? 'Video' : b.src.toUpperCase()} · ${(b.size / 1048576).toFixed(1)} MB`)}</span>${tagChips(b.genres, b.tags, 4, b.release)}</div>
    <span class="bp">${progressText(b)}</span>
    <div class="bar"><i style="width:${Math.round(bookFrac(b) * 100)}%"></i></div>
    <button class="mark" data-mark="${b.id}">${isDone(b) ? 'Mark unread' : 'Mark read'}</button>
    
  </div>`;
}
function renderSeries(sid) {
  const s = S.seriesById[sid];
  if (!s) { location.hash = S.lib ? `#/library/${S.lib}` : '#/'; return; }
  if (S.curSeries !== sid || S.selMode !== 'books') S.sel = null;
  S.curSeries = sid;
  $('#viewHome').classList.remove('on');
  const v = $('#viewSeries'); v.classList.add('on');
  v.classList.toggle('selecting', !!S.sel);
  const sc = s.collectionId && S.colById[s.collectionId];
  const crumb = sc ? `<button class="crumb" data-colback="${sc.id}">${ico('chevL', 16)} 🗂️ ${esc(sc.name)}</button>`
    : `<button class="crumb" data-libback="${s.library}">${ico('chevL', 16)} ${esc(libName(s.library))}</button>`;
  const eyebrow = `${esc(libName(s.library))}${s.novel ? ' · Light novel' : isCosplay(s.library) ? ' · Cosplay' : ''}`;
  if (!s.books.length) {
    v.innerHTML = `${crumb}
      <section class="shero"><div class="hero-cover" style="transform:rotate(-2deg)">${seriesCover(s, 480)}</div>
        <div class="hero-info"><div class="eyebrow">${eyebrow}</div><h1 class="${s.name.length > 60 ? 'xl' : ''}">${escWrap(s.name)}</h1>
          <div class="hero-meta">Empty ${V(s.library).s} · /data/${esc(libOf(s.library)?.path || '')}/…</div>
          <div class="actions"><button class="btn-primary" data-pick="${s.library}" data-pickseries="${s.id}">+ Add files</button>
          <button class="btn-ghost" data-more="series:${s.id}" aria-label="More options">⋯</button></div></div></section>
      <div class="dropzone" style="margin-top:26px"><div class="big">🗂️</div><h3>Drop ${pl(V(s.library).ch)} here</h3>
        <p>Drag <b>.cbz</b>, <b>.zip</b> or <b>.epub</b> files onto this window — they’ll go straight into <b>${esc(s.name)}</b>.<br>Or move ${pl(V(s.library).ch)} here from other ${pl(V(s.library).s)} with their <b>⋯</b> menu.</p></div>`;
    $('#main').scrollTop = 0; return;
  }
  const i = seriesInfo(s), nb = nextUp(s), b0 = s.books[0];
  const cta = i.unread === 0 ? 'Read again' : inProgress(nb) ? `Continue ${nb.label}` : `Start ${nb.label}`;
  const books = seriesSort(s) === 'desc' ? [...s.books].reverse() : s.books;
  const view = seriesView(s);
  const unit = (isCosplay(s.library) ? V(s.library).b : b0.kind === 'volume' ? 'volume' : b0.kind === 'chapter' ? 'chapter' : 'book') + (s.books.length === 1 ? '' : 's');
  v.innerHTML = `${crumb}
    <section class="shero">
      
      <button class="hero-cover" data-open="${nb.id}">${coverImg(coverBook(s), 480)}</button>
      <div class="hero-info">
        <div class="eyebrow">${eyebrow}</div>
        <h1 class="${s.name.length > 60 ? 'xl' : ''}">${escWrap(s.name)}</h1>
        ${s.author || s.publisher ? `<div class="hero-meta">${[s.author && 'by ' + esc(s.author), s.publisher && esc(s.publisher)].filter(Boolean).join(' · ')}</div>` : ''}
        ${tagChips(s.genres, s.tags, 16)}
        ${s.summary ? `<p class="blurb">${esc(s.summary.slice(0, 420))}</p>` : ''}
        <div class="stats"><div><b>${s.books.length}</b>${unit}</div><div><b>${i.read}</b>finished</div><div><b>${Math.round(i.frac * 100)}%</b>complete</div></div>
        <div class="actions">
          <button class="btn-primary" data-open="${i.unread === 0 ? b0.id : nb.id}"${i.unread === 0 ? ' data-start="0"' : ''}>${ico('play')} ${esc(cta)}</button>
          <button class="btn-ghost" data-markall="${s.id}">${i.unread === 0 ? 'Mark all unread' : 'Mark all read'}</button>
          <button class="btn-ghost" data-more="series:${s.id}" aria-label="More options">⋯</button>
        </div>
      </div>
    </section>
    <div class="shelf-h slim">
      <div><h2>${s.books.length} ${unit}</h2></div>
      <div class="shelf-actions">
        <button class="btn-sm ${S.sel ? 'pri' : ''}" data-select>${S.sel ? 'Done selecting' : '☑ Select files'}</button>
        <button class="btn-sm" data-pick="${s.library}" data-pickseries="${s.id}">+ Add files</button>
        <button class="btn-sm" data-sortflip title="Sort order">${seriesSort(s) === 'desc' ? '↓ Newest first' : '↑ Oldest first'}</button>
        <div class="seg vseg"><button data-view="cards" class="${view === 'cards' ? 'on' : ''}" title="Cards">${ico('grid', 15)}</button><button data-view="list" class="${view === 'list' ? 'on' : ''}" title="List">${ico('toc', 15)}</button></div>
      </div>
    </div>
    ${view === 'list' ? `<div class="blist">${books.map(chapterRow).join('')}</div>` : `<div class="grid chgrid">${books.map(chapterCard).join('')}</div>`}`;
  { const cb = coverBook(s); blurBg(v.querySelector('.shero'), cb.hasCover ? URLS.cover(cb, 120) : '', { sat: 1.5, alpha: .55, overlay: SHERO_GRAD }); }
  renderSelbar();
}

/* ---------- multi-select (series page) ---------- */
function selPool() {
  if (S.selMode === 'series') return S.visibleSeries || [];
  return S.seriesById[S.curSeries]?.books.map(b => b.id) || [];
}
const selBooks = () => S.selMode === 'series' ? [...S.sel].flatMap(id => S.seriesById[id]?.books || []) : [...S.sel].map(id => S.books[id]).filter(Boolean);
function renderSelbar() {
  const bar = $('#selbar');
  document.body.classList.toggle('has-selbar', !!S.sel);
  if (!S.sel) { bar.classList.remove('on'); return; }
  const n = S.sel.size, ser = S.selMode === 'series', pool = selPool();
  const all = pool.length && pool.every(id => S.sel.has(id));
  const vv = ser ? Vhome() : V(S.seriesById[S.curSeries]?.library);
  const allRead = n && selBooks().every(isDone);
  bar.innerHTML = `<b>${n ? `${plural(n, ser ? vv.s : 'item')} selected` : `Tap ${pl(ser ? vv.s : vv.ch)} to select`}</b>
    <button class="btn-sm ${all ? '' : 'pri'}" data-selall>${all ? '☐ Select none' : `☑ Select all (${pool.length})`}</button>
    <span class="grow"></span>
    <button class="btn-sm" data-selact="series" ${n ? '' : 'disabled'}>${ico('stack', 15)} ${ser ? `Merge into ${vv.s}` : `Move to ${vv.s}`}</button>
    ${ser ? `<button class="btn-sm" data-selact="col" ${n ? '' : 'disabled'}>${ico('folder', 15)} Move to ${vv.g}</button>` : ''}
    <button class="btn-sm" data-selact="lib" ${n ? '' : 'disabled'}>${ico('move', 15)} Move to library</button>
    <button class="btn-sm" data-selact="read" ${n ? '' : 'disabled'}>${ico('check', 15)} ${allRead ? 'Mark unread' : 'Mark read'}</button>
    <button class="btn-sm danger" data-selact="del" ${n ? '' : 'disabled'}>${ico('trash', 15)} Delete</button>
    <button class="btn-sm" data-selclose title="Done (Esc)">✕</button>`;
  bar.classList.add('on');
}
function toggleSelect(on) {
  S.selMode = location.hash.startsWith('#/series/') ? 'books' : 'series';
  S.sel = on ? new Set() : null;
  S.selHash = location.hash;
  if (S.selMode === 'books') renderSeries(S.curSeries); else { renderHome(); renderSelbar(); }
}

function setDone(b, done) {
  if (done) {
    const rec = { seen: true, done: true, frac: 1, page: b.pages - 1, chapter: b.pages - 1, scroll: 1, updated: Date.now() };
    S.progress[b.id] = rec; api.put(`/api/progress/${b.id}`, rec);
  } else if (prog(b)) {                              // back to unread — but remembered as seen, so not NEW again
    const rec = { seen: true };
    S.progress[b.id] = rec; api.put(`/api/progress/${b.id}`, rec);
  }
}

/* ======================= ROUTING ======================= */
const onSeriesPage = () => location.hash.startsWith('#/series/') && !document.body.classList.contains('reading');
/* ---------- top bar: search scope + Add ----------
   Scope = where the search looks: everything, or one library (the same as opening that library).
   Add = upload into wherever you are: this series, this collection, this library — on Home, pick a library. */
function updateTopButton() {
  const l = S.lib && S.libById[S.lib];
  $('#scopeName').textContent = l ? l.name : 'Everything';
  $('#btnScope').style.setProperty('--c', l ? l.color : 'transparent');
  $('#btnScope').classList.toggle('lib', !!l);
}
function addTarget() {
  const s = onSeriesPage() && S.seriesById[S.curSeries];
  if (s) return { lid: s.library, series: s.id };
  if (S.col && S.colById[S.col]) return { lid: S.colById[S.col].library, col: S.colById[S.col].folder };
  if (S.lib) return { lid: S.lib };
  if (S.libraries.length === 1) return { lid: S.libraries[0].id };
  return null;
}
function topMenu(anchor, html) {
  const m = $('#topMenu');
  if (m.classList.contains('open') && m._for === anchor) return closeTopMenu();
  m.innerHTML = html; m._for = anchor;
  const r = anchor.getBoundingClientRect();
  m.style.top = `${r.bottom + 8}px`;
  m.style.left = `${Math.max(8, Math.min(r.left, innerWidth - 268))}px`;
  m.classList.add('open');
}
function closeTopMenu() { $('#topMenu').classList.remove('open'); }
const libItems = (attr, cur) => S.libraries.map(l => `<button type="button" role="menuitem" ${attr}="${l.id}" class="${cur === l.id ? 'on' : ''}"><i style="background:${esc(l.color)}"></i>${esc(l.name)}<small>${plural(l.books, 'book')}</small></button>`).join('');
$('#btnScope').addEventListener('click', e => {
  e.preventDefault(); e.stopPropagation();          // inside the search's <label>: don't focus the field
  topMenu(e.currentTarget, `<div class="tm-h">Search in</div>
    <button type="button" role="menuitem" data-scope="" class="${S.lib ? '' : 'on'}"><i class="all"></i>Everything<small>all libraries</small></button>${libItems('data-scope', S.lib)}`);
});
$('#btnTopAdd').addEventListener('click', e => {
  e.stopPropagation();
  const t = addTarget();
  if (t) { closeTopMenu(); UP.pickTarget = t.lid; UP.pickSeries = t.series || null; UP.pickCol = t.col || null; return $('#filePick').click(); }
  if (!S.libraries.length) return openLibModal();
  topMenu(e.currentTarget, `<div class="tm-h">Add files to</div>${libItems('data-addto')}
    <div class="tm-foot">Tip: you can also drag files anywhere onto this window.</div>`);
});
$('#topMenu').addEventListener('click', e => {
  const sc = e.target.closest('[data-scope]');
  if (sc) {
    closeTopMenu();
    location.hash = sc.dataset.scope ? `#/library/${sc.dataset.scope}` : '#/';
    return $('#q').focus();
  }
  const ad = e.target.closest('[data-addto]');
  if (ad) { closeTopMenu(); UP.pickTarget = ad.dataset.addto; UP.pickSeries = UP.pickCol = null; $('#filePick').click(); }
});
document.addEventListener('pointerdown', e => { if (!e.target.closest('#topMenu, #btnScope, #btnTopAdd')) closeTopMenu(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#topMenu').classList.contains('open')) { e.stopImmediatePropagation(); closeTopMenu(); } }, true);
window.addEventListener('resize', closeTopMenu);
document.getElementById('main')?.addEventListener('scroll', () => {
  closeTopMenu();
  $('#topBar').classList.toggle('stuck', $('#main').scrollTop > 4);
}, { passive: true });
function route() {
  if (!S.loaded) return;
  updateTopButton();
  if (S.sel && location.hash !== S.selHash) S.sel = null;
  if (!location.hash.startsWith('#/series/')) { S.curSeries = null; }
  renderSelbar();
  const h = location.hash.slice(1) || '/';
  const [, view, id, extra] = h.split('/');
  if (view === 'read' && S.books[id]) {
    if (R.book?.id !== id || !document.body.classList.contains('reading')) openReader(id, extra != null && extra !== '' ? +extra : null);
    return;
  }
  if (document.body.classList.contains('reading')) shutReader();
  S.inFavs = false; S.favCur = null; $('#viewFavs').classList.remove('on');
  if (view === 'favs' || view === 'fav') { renderFavs(view === 'fav' ? id : null); renderSidebar(); return; }
  if (view !== 'collection') S.col = null;
  if (view === 'series') renderSeries(id);
  else if (view === 'collection' && S.colById[id]) { S.col = id; S.lib = S.colById[id].library; renderHome(); }
  else if (view === 'library' && S.libById[id]) { S.lib = id; renderHome(); }
  else { S.lib = null; renderHome(); }
  renderSidebar(); updateTopButton();
}
window.addEventListener('hashchange', route);
const openBook = (id, start) => { location.hash = `#/read/${id}${start != null ? '/' + start : ''}`; };

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
  document.body.classList.remove('reading');
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
  if (nc) return openPrompt(nc, { title: `New ${V(nc.dataset.newcol).g}`, hint: `A folder that groups ${pl(V(nc.dataset.newcol).s)} inside ${libName(nc.dataset.newcol)}.`, placeholder: 'e.g. Isekai, Favourites, 2026 releases', button: 'Create',
    run: async name => { const r = await jsonFetch('POST', `/api/libraries/${nc.dataset.newcol}/collections`, { name }); history.pushState(null, '', `#/collection/${r.id}`); appToast(`Created ${name}`); await load(); } });
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

/* ======================= WELCOME / LIBRARIES ======================= */
function renderWelcome() {
  $('#welcome').innerHTML = `<div class="welcome"><div class="welcome-card">
    <svg class="mascot" viewBox="0 0 200 200" aria-hidden="true">${critter(100, 128, 60, 48)}</svg>
    <h1>Add your <em>first</em> library</h1>
    <p>A library is a shelf for your comics, manga or light novels. Create one, then drag <code>.cbz</code> or <code>.epub</code> files — or whole folders — straight onto this window.</p>
    <button class="btn-primary" data-addlib>+ Add library</button>
    <div class="steps"><span><b>1</b>Create a library</span><span><b>2</b>Drop in your files</span><span><b>3</b>Start reading</span></div>
  </div></div>`;
}
const dropzoneHTML = lid => `<div class="dropzone"><div class="big">📚</div><h3>${esc(libName(lid))} is empty</h3>
  <p>Drag <b>.cbz</b>, <b>.zip</b> or <b>.epub</b> files — or whole folders — anywhere onto this window.<br>Chapters are sorted into series folders automatically.</p>
  <button class="btn-primary" data-pick="${lid}">Choose files</button></div>`;

const SWATCHES = ['#ff5c8a', '#ffd84d', '#5ee6c1', '#7aa8ff', '#b388ff', '#ff9f5a'];
let modal = null;
const slug = v => v.replace(/[<>:"/\\|?*\x00-\x1f]/g, '').trim();
function openLibModal(edit = null, pendingFiles = null) {
  // The dialog opens at once; folders that could be used arrive a moment later (asking for them first made the
  // button feel dead on big libraries — and a second, impatient click opened the dialog twice).
  if (!edit) api.get('/api/folders').then(r => {
    const free = r.folders.filter(f => !f.used), box = $('#libSuggest');
    if (!box || !free.length || !modal || modal.edit) return;
    box.innerHTML = `<span class="hintline">Or use a folder that's already there:</span><div class="suggest">${free.map(x =>
      `<button type="button" data-usefolder="${esc(x.path)}">${esc(x.path)}${x.books ? ` · ${x.books >= 500 ? '500+' : x.books}` : ''}</button>`).join('')}</div>`;
  }).catch(() => {});
  modal = { edit, pendingFiles, pathTouched: false, armed: false, color: edit?.color || SWATCHES[S.libraries.length % SWATCHES.length], type: edit ? libType(edit.id) : 'comics' };
  const f = $('#libForm'); f.classList.remove('confirming');      // (a remove left half-confirmed on another library)
  f.innerHTML = `
    <h3>${edit ? 'Library settings' : S.libraries.length ? 'New library' : 'Create your first library'}</h3>
    ${edit ? `<div class="libtabs">${S.libraries.map(l => `<button type="button" data-switchlib="${l.id}" class="${l.id === edit.id ? 'on' : ''}"><i style="background:${esc(l.color)}"></i>${esc(l.name)}</button>`).join('')}<button type="button" data-newlib>+ New</button></div>` : ''}
    ${pendingFiles ? `<div class="banner" style="margin:0">📦 ${plural(pendingFiles.length, 'file')} will be added once the library is created.</div>` : ''}
    <div class="f"><label for="libName">Name</label><input type="text" id="libName" name="name" maxlength="60" placeholder="e.g. Manga, Comics, Light Novels" value="${esc(edit?.name || '')}"></div>
    ${edit ? `<div class="f">Folder<span class="hintline"><code>/data/${esc(edit.path)}</code> · ${plural(edit.books || 0, 'book')}${edit.auto ? ' · found automatically' : ''}</span></div>` : `
    <div class="f"><label for="libPath">Folder</label><div class="pathbox"><span>/data/${esc(S.me?.folder || "")}/</span><input type="text" id="libPath" name="path" placeholder="Manga"></div>
      <span class="hintline">Created for you if it doesn't exist — files you drop in are saved here.</span>
      <div id="libSuggest"></div>
    </div>`}
    <div class="f">Library type<div class="dirpick three">
      <button type="button" data-ltype="comics"><b>📖 Comics</b><small>Left → right · webtoons, novels</small></button>
      <button type="button" data-ltype="manga"><b>🎌 Manga</b><small>Right ← left reading</small></button>
      <button type="button" data-ltype="cosplay"><b>📸 Cosplay</b><small>Cosplayers → sets → variants · L → R</small></button></div></div>
    <div class="f">Colour<div class="swatches">${SWATCHES.map(c => `<button type="button" data-swatch="${c}" style="--c:${c}" aria-label="Colour ${c}"></button>`).join('')}</div></div>
    <div class="formerr" id="formErr"></div>
    <div class="formfoot">${edit ? '<button type="button" class="btn-danger" id="btnRemoveLib">Remove library</button>' : ''}<div class="grow"></div>
      <button type="button" class="btn-ghost" data-closemodal>Cancel</button><button type="submit" class="btn-primary">${edit ? 'Save' : 'Create library'}</button></div>`;
  syncModal();
  $('#libModal').classList.add('open');
  setTimeout(() => $('#libName').focus(), 60);
}
function syncModal() {
  $$('#libForm [data-ltype]').forEach(b => b.classList.toggle('on', b.dataset.ltype === modal.type));
  $$('#libForm [data-swatch]').forEach(b => b.classList.toggle('on', b.dataset.swatch === modal.color));
}
$('#libForm').addEventListener('input', e => {
  if (e.target.id === 'libPath') modal.pathTouched = true;
  if (e.target.id === 'libName' && !modal.edit && !modal.pathTouched) {
    $('#libPath').value = slug(e.target.value);
    if (!modal.dirTouched) { modal.type = /cosplay|photo/i.test(e.target.value) ? 'cosplay' : /manga|漫画/i.test(e.target.value) ? 'manga' : 'comics'; syncModal(); }
  }
  if (e.target.id !== 'rmFiles') $('#formErr').textContent = '';
});
$('#libForm').addEventListener('click', async e => {
  const sl = e.target.closest('[data-switchlib]');
  if (sl) return openLibModal(S.libById[sl.dataset.switchlib]);
  if (e.target.closest('[data-newlib]')) return openLibModal();
  const d = e.target.closest('[data-ltype]');
  if (d) { modal.type = d.dataset.ltype; modal.dirTouched = true; return syncModal(); }
  const sw = e.target.closest('[data-swatch]');
  if (sw) { modal.color = sw.dataset.swatch; return syncModal(); }
  const uf = e.target.closest('[data-usefolder]');
  if (uf) { $('#libPath').value = uf.dataset.usefolder; modal.pathTouched = true; if (!$('#libName').value) $('#libName').value = uf.dataset.usefolder; return; }
  const rm = e.target.closest('#btnRemoveLib');
  if (rm) {
    const l = modal.edit, n = l.books || 0;
    $('#formErr').innerHTML = `<div class="rmbox">
      <b>Remove “${esc(l.name)}”?</b>
      ${n ? `<label class="rmcheck"><input type="checkbox" id="rmFiles"><span>Also delete <code>/data/${esc(l.path)}</code> and its ${plural(n, 'file')} from disk</span></label>
        <span class="hintline">Leave unticked to keep the files — the folder then won’t be re-added automatically.</span>`
        : `<span class="hintline">Its empty folder <code>/data/${esc(l.path)}</code> will be removed too.</span>`}
      <div class="formfoot"><div class="grow"></div><button type="button" class="btn-ghost" data-rmcancel>Cancel</button><button type="button" class="btn-danger arm" data-rmgo>Remove library</button></div></div>`;
    $('#libForm').classList.add('confirming');
    $('#formErr .rmbox').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return;
  }
  if (e.target.closest('[data-rmcancel]')) { $('#formErr').innerHTML = ''; $('#libForm').classList.remove('confirming'); return; }
  if (e.target.closest('[data-rmgo]')) {
    const id = modal.edit.id, files = !!$('#rmFiles')?.checked;
    const r = await fetch(`/api/libraries/${id}${files ? '?files=true' : ''}`, { method: 'DELETE' }).catch(() => null);
    const d = r ? await r.json().catch(() => ({})) : {};
    if (!r?.ok) { $('#formErr').textContent = d.detail || 'Couldn’t remove the library'; return; }
    $('#libModal').classList.remove('open'); modal = null;
    appToast(d.folder === 'removed' ? 'Library and folder removed' : 'Library removed · files kept on disk');
    location.hash = '#/'; await load();
  }
});
$('#libForm').addEventListener('submit', async e => {
  e.preventDefault();
  const name = $('#libName').value.trim();
  if (!name) { $('#formErr').textContent = 'Give your library a name'; return $('#libName').focus(); }
  const body = { name, type: modal.type, rtl: modal.type === 'manga', color: modal.color };
  if (!modal.edit) body.path = $('#libPath').value.trim() || slug(name);
  const btn = e.target.querySelector('[type=submit]'); btn.disabled = true;
  const r = await fetch(modal.edit ? `/api/libraries/${modal.edit.id}` : '/api/libraries', {
    method: modal.edit ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).catch(() => null);
  btn.disabled = false;
  const d = r ? await r.json().catch(() => ({})) : {};
  if (!r || !r.ok) { $('#formErr').textContent = d.detail || 'Couldn’t reach the server'; return; }
  const pending = modal.pendingFiles, wasEdit = !!modal.edit;
  $('#libModal').classList.remove('open'); modal = null;
  if (!wasEdit) location.hash = `#/library/${d.id}`;
  await load();
  if (pending?.length) uploadFiles(d.id, pending);
});
/* ======================= EDIT DETAILS (series / set metadata) ======================= */
let DM = null;
function openDetails(sid) {
  const s = S.seriesById[sid]; if (!s || !s.books.length) return;
  const first = k => s.books.find(b => b[k])?.[k] || '';
  const init = { name: s.name, author: first('author'), publisher: first('publisher'), summary: first('summary'),
    year: String(first('year') || ''), release: first('release'), genres: [...(s.genres || [])], tags: [...(s.tags || [])] };
  const r0 = seriesPrefs[sid]?.rtl ?? s.books[0].rtl;
  init.direction = r0 == null ? '' : r0 ? 'rtl' : 'ltr';
  DM = { sid, s, init, genres: [...init.genres], tags: [...init.tags], dir: init.direction || 'auto' };
  const cos = isCosplay(s.library), edited = s.books.some(b => b.edited);
  const f = $('#detForm');
  f.innerHTML = `
    <div class="dhead"><span class="dcover">${seriesCover(s, 160)}</span><div><h3>Edit details</h3><span class="hintline">${esc(libName(s.library))} · ${countLabel(s)}${edited ? ' · <b class="edtag">edited</b>' : ''}</span>
      ${coverBooks(s).length ? '<button type="button" class="btn-sm editcover" data-editcover>🖼 Edit cover</button>' : ''}</div></div>
    <div class="f"><label for="dName">Name</label><input type="text" id="dName" maxlength="120" value="${esc(init.name)}"><span class="hintline">Renames the folder / file on disk · progress is kept</span></div>
    <div class="f2"><div class="f"><label for="dAuthor">Author</label><input type="text" id="dAuthor" value="${esc(init.author)}" placeholder="Writer / artist"></div>
      <div class="f"><label for="dPub">Publisher / group</label><input type="text" id="dPub" value="${esc(init.publisher)}" placeholder="—"></div></div>
    <div class="f">Genres <span class="hintline">The first one is shown on the cover badge</span><div class="chipin" data-list="genres"></div></div>
    <div class="f">Tags <span class="hintline">Enter or comma adds · type <code>tag:f</code> / <code>tag:m</code> for tag ♀ / tag ♂</span><div class="chipin" data-list="tags"></div></div>
    <div class="f2"><div class="f"><label for="dRel">Release format</label><input type="text" id="dRel" value="${esc(init.release)}" placeholder="e.g. Web, Digital, Tankōbon"></div>
      <div class="f"><label for="dYear">Year</label><input type="text" id="dYear" inputmode="numeric" maxlength="4" value="${esc(init.year)}" placeholder="—"></div></div>
    <div class="f"><label for="dSum">Summary</label><textarea id="dSum" rows="4" placeholder="—">${esc(init.summary)}</textarea></div>
    ${cos ? '' : `<div class="f">Reading direction<div class="seg dseg"><button type="button" data-ddir="auto">Auto</button><button type="button" data-ddir="ltr">Left → right</button><button type="button" data-ddir="rtl">Right ← left</button></div></div>`}
    <span class="hintline">Saved into each file as <code>metadata.json</code>${s.books.some(b => b.src === 'cbz' || b.src === 'cb7' || b.src === 'zip') ? ' (ComicInfo.xml is folded into it)' : ''}.</span>
    <div class="formerr" id="detErr"></div>
    <div class="formfoot">${edited ? '<button type="button" class="btn-ghost" id="detReset" title="Forget your edits and use what the files say">↺ Reset to file</button>' : ''}<div class="grow"></div>
      <button type="button" class="btn-ghost" data-closedet>Cancel</button><button type="submit" class="btn-primary">Save</button></div>`;
  renderChipLists(); syncDetDir();
  $('#detModal').classList.add('open');
  setTimeout(() => !isPhone() && $('#dAuthor').focus(), 60);
}
/* ---------- cover picker: every photo of a book in rows & columns; the choice goes into metadata.json ---------- */
// books that can carry a cover choice: archives / photo sets with at least one photo
const coverBooks = s => s.books.filter(b => b.format === 'images' && ['cbz', 'zip', 'cb7', 'folder'].includes(b.src) && b.pages > (b.videos?.length || 0));
function openCoverPicker(sid) {
  const s = S.seriesById[sid]; if (!s) return;
  const books = coverBooks(s); if (!books.length) return;
  const cur = coverBook(s);
  let book = books.includes(cur) ? cur : books[0];
  const o = document.createElement('div');
  o.className = 'overlay fixed open cvmodal';
  const unit = V(s.library).ch;
  const paint = () => {
    const vids = new Set(book.videos || []);
    const chosen = book.id === cur.id ? (cur.coverPage ?? 0) : -1;
    o.innerHTML = `<div class="sheet cvsheet" role="dialog" aria-modal="true">
      <div class="cvhead"><h3>Choose a cover</h3><button type="button" class="ib" data-cvclose aria-label="Close">×</button></div>
      ${books.length > 1 ? `<label class="cvbook">From ${unit}
        <select id="cvBook">${books.map(b => `<option value="${b.id}" ${b.id === book.id ? 'selected' : ''}>${esc(b.label)}${b.title ? ' · ' + esc(b.title) : ''}${b.id === cur.id ? '  ★ current cover' : ''}</option>`).join('')}</select></label>` : ''}
      <div class="cvgrid">${Array.from({ length: book.pages }, (_, i) => vids.has(i)
        ? `<div class="cvtile vid" title="Videos can't be covers"><span>▶</span><i>${i + 1}</i></div>`
        : `<button type="button" class="cvtile ${i === chosen ? 'on' : ''}" data-cvpage="${i}" title="Page ${i + 1}"><img loading="lazy" src="${URLS.thumb(book, i, 200)}" alt=""><i>${i + 1}</i></button>`).join('')}</div>
      <div class="cvfoot"><span class="hintline">Saved into ${books.length > 1 ? 'that ' + unit + '’s' : 'the file’s'} <code>metadata.json</code></span><div class="grow"></div>
        <button type="button" class="btn-ghost" data-cvreset>↺ Default cover</button><button type="button" class="btn-ghost" data-cvclose>Cancel</button></div></div>`;
    o.querySelector('#cvBook')?.addEventListener('change', e => { book = books.find(b => b.id === e.target.value) || book; paint(); });
  };
  const close = () => { document.removeEventListener('keydown', key, true); o.remove(); };
  const key = e => { if (e.isTrusted && e.key === 'Escape') { e.stopImmediatePropagation(); close(); } };
  const save = async body => {
    try { await jsonFetch('PUT', `/api/series/${sid}/cover`, body); } catch (err) { appToast(err.message); return; }
    close(); appToast(body.book ? 'Cover changed' : 'Back to the default cover');
    await load();
    const ns = S.seriesById[sid]; const box = $('#detForm .dcover');
    if (ns && box) box.innerHTML = seriesCover(ns, 160);
  };
  o.addEventListener('click', e => {
    if (e.target.closest('[data-cvclose]')) return close();
    if (e.target.closest('[data-cvreset]')) return save({ book: null });
    const t = e.target.closest('[data-cvpage]'); if (t) save({ book: book.id, page: +t.dataset.cvpage });
  });
  document.addEventListener('keydown', key, true);
  backdropCloses(o, close);
  paint(); document.body.appendChild(o);
  o.querySelector('.cvtile.on')?.scrollIntoView({ block: 'center' });
}
function renderChipLists() {
  $$('#detForm .chipin').forEach(box => {
    const k = box.dataset.list, list = DM[k];
    box.innerHTML = list.map((t, i) => `<span class="ctag ${k === 'genres' && i === 0 ? 'genre' : ''}" style="--h:${tagHue(t)}">${esc(t)}<button type="button" data-rmchip="${k}:${i}" aria-label="Remove">×</button></span>`).join('')
      + `<input type="text" class="chipadd" data-addto="${k}" placeholder="${list.length ? 'Add…' : k === 'genres' ? 'e.g. Manga, Doujinshi' : 'e.g. cute, comedy, glasses ♀'}">`;
  });
}
function syncDetDir() { $$('#detForm [data-ddir]').forEach(b => b.classList.toggle('on', b.dataset.ddir === DM.dir)); }
function addChips(k, raw) {
  const have = new Set(DM[k].map(x => x.toLowerCase()));
  raw.split(/[,;\n]+/).map(x => x.replace(/\s+/g, ' ').trim())
    .map(x => k === 'tags' ? x.replace(/\s*:\s*f(emale)?$/i, ' ♀').replace(/\s*:\s*m(ale)?$/i, ' ♂') : x).filter(Boolean).forEach(x => { if (!have.has(x.toLowerCase())) { have.add(x.toLowerCase()); DM[k].push(x); } });
  renderChipLists(); $(`#detForm [data-addto="${k}"]`).focus();
}
$('#detForm').addEventListener('keydown', e => {
  const inp = e.target.closest('[data-addto]'); if (!inp) return;
  const k = inp.dataset.addto;
  if ((e.key === 'Enter' || e.key === ',') && inp.value.trim()) { e.preventDefault(); addChips(k, inp.value); }
  else if (e.key === 'Enter') e.preventDefault();
  else if (e.key === 'Backspace' && !inp.value && DM[k].length) { DM[k].pop(); renderChipLists(); $(`#detForm [data-addto="${k}"]`).focus(); }
});
$('#detForm').addEventListener('focusout', e => { const inp = e.target.closest?.('[data-addto]'); if (inp && inp.value.trim()) addChips(inp.dataset.addto, inp.value); });
$('#detForm').addEventListener('paste', e => { const inp = e.target.closest('[data-addto]'); if (!inp) return; const t = e.clipboardData.getData('text'); if (/[,;\n]/.test(t)) { e.preventDefault(); addChips(inp.dataset.addto, t); } });
$('#detForm').addEventListener('click', async e => {
  const rm = e.target.closest('[data-rmchip]');
  if (rm) { const [k, i] = rm.dataset.rmchip.split(':'); DM[k].splice(+i, 1); return renderChipLists(); }
  if (e.target.closest('.chipin') && !e.target.closest('input')) return e.target.closest('.chipin').querySelector('input').focus();
  const dd = e.target.closest('[data-ddir]'); if (dd) { DM.dir = dd.dataset.ddir; return syncDetDir(); }
  if (e.target.closest('[data-closedet]')) return $('#detModal').classList.remove('open');
  if (e.target.closest('[data-editcover]')) return openCoverPicker(DM.sid);
  if (e.target.closest('#detReset')) {
    try { await jsonFetch('PATCH', `/api/series/${DM.sid}/details`, { reset: true }); } catch (err) { $('#detErr').textContent = err.message; return; }
    $('#detModal').classList.remove('open'); appToast('Details reset to what the files say'); return load();
  }
});
$('#detForm').addEventListener('submit', async e => {
  e.preventDefault();
  const v = { name: $('#dName').value.trim(), author: $('#dAuthor').value.trim(), publisher: $('#dPub').value.trim(), release: $('#dRel').value.trim(),
    year: $('#dYear').value.trim(), summary: $('#dSum').value.trim(), genres: DM.genres, tags: DM.tags };
  if (!v.name) { $('#detErr').textContent = `The ${V(DM.s.library).s} needs a name`; return $('#dName').focus(); }
  if (v.year && !/^\d{4}$/.test(v.year)) { $('#detErr').textContent = 'Year should be four digits'; return $('#dYear').focus(); }
  const same = (a, b) => Array.isArray(a) ? a.join('\u0001') === b.join('\u0001') : a === b;
  v.direction = DM.dir === 'auto' ? '' : DM.dir;
  const fields = {};
  for (const k of ['author', 'publisher', 'release', 'year', 'summary', 'genres', 'direction']) if (!same(v[k], DM.init[k])) fields[k] = v[k];
  // tags here are the ones *every* chapter shares: send the difference so chapter-only tags survive
  const low = a => new Set(a.map(t => t.toLowerCase()));
  const was = low(DM.init.tags), now = low(v.tags);
  const tagsAdd = v.tags.filter(t => !was.has(t.toLowerCase())), tagsRemove = DM.init.tags.filter(t => !now.has(t.toLowerCase()));
  if (tagsAdd.length) fields.tagsAdd = tagsAdd;
  if (tagsRemove.length) fields.tagsRemove = tagsRemove;
  if (tagsAdd.length || tagsRemove.length) fields.tagsBase = v.tags;   // what untagged chapters inherit
  const btn = e.target.querySelector('[type=submit]'); btn.disabled = true;
  const n = DM.s.books.length;
  if (Object.keys(fields).length) btn.textContent = n > 1 ? `Saving into ${n} files…` : 'Saving…';
  let sid = DM.sid;
  try {
    if (Object.keys(fields).length) await jsonFetch('PATCH', `/api/series/${sid}/details`, { fields });
    if (seriesPrefs[sid]?.rtl != null) saveSeriesPref(sid, { rtl: undefined });   // the file decides now
    if (v.name !== DM.init.name) {
      const d = await jsonFetch('PATCH', `/api/series/${sid}`, { name: v.name });
      if (seriesPrefs[sid]) { seriesPrefs[d.seriesId] = seriesPrefs[sid]; delete seriesPrefs[sid]; local.set('cf-series', seriesPrefs); }
      if (location.hash === `#/series/${sid}`) history.replaceState(null, '', `#/series/${d.seriesId}`);
      sid = d.seriesId;
    }
  } catch (err) { btn.disabled = false; btn.textContent = 'Save'; $('#detErr').textContent = err.message || 'Couldn’t save'; await load(); return; }
  btn.disabled = false;
  $('#detModal').classList.remove('open'); appToast('Details saved'); await load();
});
document.addEventListener('keydown', e => { if (e.isTrusted && e.key === 'Escape' && $('#detModal.open')) { e.stopImmediatePropagation(); $('#detModal').classList.remove('open'); } }, true);


/* ======================= DRAG & DROP + UPLOADS ======================= */
const BOOK_RE = /\.(cbz|zip|cb7|cbr|epub|rar|7z)$/i;
const PLAIN_ARCHIVE_RE = /\.(zip|rar|7z)$/i;          // regular archives: converted to .cbz on upload — if you say so
const VIDEO_RE = /\.(mp4|webm|mkv|mov|m4v)$/i;
const UP = { rows: [], pickTarget: null, min: local.get('cf-upmin', false) };
let dragDepth = 0, internalDrag = false;
document.addEventListener('dragstart', () => { internalDrag = true; });
document.addEventListener('dragend', () => { internalDrag = false; });
const hasFiles = e => [...(e.dataTransfer?.types || [])].includes('Files');
const reading = () => document.body.classList.contains('reading');
function showDrop() {
  const d = $('#drop');
  if (d.classList.contains('on')) return;
  const libs = S.libraries;
  const cur = onSeriesPage() && S.seriesById[S.curSeries];
  if (cur) {
    $('#dropTitle').textContent = `Add to ${cur.name}`;
    $('#dropSub').textContent = `Files go straight into this ${V(cur.library).s} in ${libName(cur.library)}`;
    $('#dropTiles').innerHTML = '';
  } else if (S.col && S.colById[S.col]) {
    const c = S.colById[S.col];
    $('#dropTitle').textContent = `Add to 🗂️ ${c.name}`;
    $('#dropSub').textContent = `Files become ${pl(V(c.library).s)} in this ${V(c.library).g} · folders of images are packed into ${isCosplay(c.library) ? '.zip' : '.cbz'}`;
    $('#dropTiles').innerHTML = '';
  } else if (!libs.length) {
    $('#dropTitle').textContent = 'Drop to start your first library';
    $('#dropSub').textContent = 'We’ll ask for a name, then add these files to it.';
    $('#dropTiles').innerHTML = '';
  } else {
    const order = S.lib ? [S.libById[S.lib], ...libs.filter(l => l.id !== S.lib)] : libs;
    $('#dropTitle').textContent = libs.length === 1 ? `Add to ${libs[0].name}` : 'Drop onto a library';
    $('#dropSub').textContent = `.cbz, .cb7, .cbr, .epub or folders of images — they’re sorted into ${pl(Vhome().s)} & ${pl(Vhome().g)}`;
    $('#dropTiles').innerHTML = libs.length > 1 ? order.map((l, i) => `<div data-droplib="${l.id}" style="--c:${esc(l.color)}" class="${i === 0 ? 'hot' : ''}"><i></i>${esc(l.name)}<small>${plural(l.books, 'book')}</small></div>`).join('') : '';
  }
  d.classList.add('on');
}
function hideDrop() { $('#drop').classList.remove('on'); dragDepth = 0; }
window.addEventListener('dragenter', e => { if (!hasFiles(e) || reading() || internalDrag) return; e.preventDefault(); dragDepth++; showDrop(); });
window.addEventListener('dragover', e => {
  if (!hasFiles(e) || internalDrag) return;
  e.preventDefault();
  if (reading()) { e.dataTransfer.dropEffect = 'none'; return; }
  e.dataTransfer.dropEffect = 'copy';
  const t = e.target.closest?.('[data-droplib]');
  if (t) $$('#dropTiles [data-droplib]').forEach(x => x.classList.toggle('hot', x === t));
});
window.addEventListener('dragleave', e => { if (!hasFiles(e)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) hideDrop(); });
window.addEventListener('drop', async e => {
  if (!hasFiles(e) || internalDrag) return;
  e.preventDefault();
  if (reading()) return;
  const target = $('#dropTiles .hot')?.dataset.droplib;
  const filesP = collectFiles(e.dataTransfer);   // must start synchronously, before any await
  hideDrop();
  const slow = setTimeout(() => appToast('Reading dropped folder…'), 350);
  let items = [];
  try { items = await filesP; } catch (err) { console.warn('drop failed', err); }
  clearTimeout(slow);
  const unreadable = dropFailures.filter(x => BOOK_RE.test(x.path) || IMG_RE.test(x.path) || VIDEO_RE.test(x.path) || x.path.endsWith('/'));
  if (unreadable.length) {
    // say exactly where each one is (inside the dropped folder), so nobody has to hunt through 1000 files
    const where = x => x.path.split('/').filter(Boolean).slice(0, -1).join(' › ');
    UP.rows.push(...unreadable.map(x => ({ f: { size: 0 }, name: x.path.split('/').filter(Boolean).pop(), state: 'err', p: 1,
      msg: 'Path too long', where: where(x) ? 'in ' + where(x) : '', inside: x.path.replace(/^\//, '') })));
    UP.longPaths = [...(UP.longPaths || []), ...unreadable.map(x => x.path.replace(/^\//, '').replace(/\/$/, '').replaceAll('/', '\\'))];
    UP.rows.push({ f: { size: 0 }, state: 'skip', msg: '', p: 1, notice: true,
      name: `${plural(unreadable.length, 'file')} Windows wouldn’t let the browser open: the full path is over 260 characters. Shorten the name or move the folder closer to the drive (e.g. D:\\Manga), then drop just these again.` });
    renderUploads(true);
  }
  if (!items.length) return appToast(unreadable.length ? `Your browser couldn’t read ${plural(unreadable.length, 'file')} — see the upload panel` : 'Couldn’t find any comics or images in that drop');
  if (!S.libraries.length) return openLibModal(null, items);
  const cur = onSeriesPage() && S.seriesById[S.curSeries];
  if (cur) return uploadFiles(cur.library, items, cur.id);
  const col = S.col && S.colById[S.col];
  if (col) return uploadFiles(col.library, items, null, col.folder);
  uploadFiles(target || S.lib || S.libraries[0].id, items);
});
function collectFiles(dt) {
  dropFailures.length = 0;
  // Grab everything synchronously — DataTransfer is emptied once the event returns.
  const items = [...(dt.items || [])].filter(i => i.kind === 'file');
  const entries = items.map(i => { try { return i.webkitGetAsEntry?.() || null; } catch { return null; } });
  const handles = items.map(i => { try { return i.getAsFileSystemHandle ? i.getAsFileSystemHandle().catch(() => null) : null; } catch { return null; } });
  const plain = [...(dt.files || [])];
  return (async () => {
    const out = [];
    for (const en of entries) { if (en) { try { await walkEntry(en, out); } catch (err) { console.warn('entry walk failed', err); } } }
    if (out.length) return out;
    for (const hp of handles) {                     // File System Access API fallback
      const h = hp && await hp;
      if (h) { try { await walkHandle(h, out, ''); } catch (err) { console.warn('handle walk failed', err); } }
    }
    if (out.length) { dropFailures.length = 0; return out; }   // the fallback could read them after all
    return plain.filter(f => BOOK_RE.test(f.name) || IMG_RE.test(f.name) || VIDEO_RE.test(f.name)).map(f => ({ file: f, path: f.name }));
  })();
}
const dropFailures = [];
async function walkEntry(entry, out) {
  if (entry.isFile) {
    const f = await new Promise((res, rej) => entry.file(res, rej)).catch(err => { dropFailures.push({ path: entry.fullPath, err }); return null; });
    if (f) out.push({ file: f, path: entry.fullPath.replace(/^\/+/, '') });
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    for (;;) {
      let batch;
      try { batch = await new Promise((res, rej) => reader.readEntries(res, rej)); }
      catch (err) { dropFailures.push({ path: entry.fullPath + '/', err }); break; }
      if (!batch.length) break;
      for (const en of batch) await walkEntry(en, out);
    }
  }
}
async function walkHandle(h, out, prefix) {
  if (h.kind === 'file') { out.push({ file: await h.getFile(), path: prefix + h.name }); return; }
  for await (const child of h.values()) await walkHandle(child, out, prefix + h.name + '/');
}
$('#filePick').addEventListener('change', e => {
  const files = [...e.target.files]; e.target.value = '';
  if (files.length && UP.pickTarget) uploadFiles(UP.pickTarget, files, UP.pickSeries, UP.pickCol);
});

/* ---------- folder planner: decide what each dropped folder becomes ----------
   folder of images                    → a series with one chapter (packed into <folder>.cbz)
   folder whose subfolders are images  → a series, one chapter per subfolder
   folder of numbered chapters         → a series (folder name = series name)
   folder of unrelated archives        → a collection, each archive its own series
   folder of series folders            → a collection containing those series            */
const IMG_RE = /\.(jpe?g|png|webp|avif|gif|bmp|tiff?|jxl|heic|heif)$/i;
const natCmp = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
const tidyName = v => v.replace(/[\s_]+/g, ' ').replace(/^[\s\-_.]+|[\s\-_.]+$/g, '');
const safeName = v => v.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/^[\s.]+|[\s.]+$/g, '').slice(0, 150) || 'Untitled';
function seriesStem(name, isFile = true) {
  let s = isFile ? name.replace(/\.[^.]+$/, '') : name, u;   // folders have no extension: "Name Ch.1" keeps its ".1"
  while ((u = s.replace(/\s*(?:\[[^\[\](){}]*\]|\([^\[\](){}]*\)|\{[^\[\](){}]*\})/g, ' ')) !== s) s = u;   // innermost first: nested groups go whole
  const re = /(?:^|[\s_\-.])(c|ch|chap|chapter|part|pt|ep|episode|v|vol|volume|#)\.?\s*(\d+(?:\.\d+)?)(?=$|[\s_\-.])/ig;
  let m, last = null;
  while ((m = re.exec(s))) last = m;
  if (last) return { num: +last[2], before: s.slice(0, last.index) };
  const t = s.match(/\s(\d{1,4}(?:\.\d+)?)\s*$/);
  return t ? { num: +t[1], before: s.slice(0, t.index) } : { num: null, before: s };
}
function relatedArchives(files) {
  if (files.length < 2) return true;
  const parsed = files.map(f => seriesStem(f.name));
  const keys = new Set(parsed.filter(p => p.num != null).map(p => tidyName(p.before).toLowerCase()));
  const loose = parsed.filter(p => p.num == null);   // "Name.cbz" beside "Name - Part 2.cbz" is part 1 of the same series
  return keys.size === 1 && (loose.length === 0 || (loose.length === 1 && keys.has(tidyName(loose[0].before).toLowerCase())));
}
function fileTree(items) {
  const root = { name: '', dirs: {}, files: [] };
  for (const it of items) {
    const parts = it.path.split('/').filter(Boolean);
    let node = root;
    for (const p of parts.slice(0, -1)) node = node.dirs[p] ||= { name: p, dirs: {}, files: [] };
    node.files.push(it.file);
  }
  return root;
}
// a folder holding images packs ALL its media (videos between photos stay in order); videos alone stay separate files
const hasImages = n => n.files.some(f => IMG_RE.test(f.name));
const archivesIn = n => n.files.filter(f => BOOK_RE.test(f.name) || (!hasImages(n) && VIDEO_RE.test(f.name))).sort((a, b) => natCmp(a.name, b.name));
const imagesIn = n => hasImages(n) ? n.files.filter(f => IMG_RE.test(f.name) || VIDEO_RE.test(f.name)).sort((a, b) => natCmp(a.name, b.name)) : [];
const isImageFolder = n => imagesIn(n).length && !archivesIn(n).length && !Object.keys(n.dirs).length;
// sibling folders "Name 1", "Name 2" / "Name Ch.1", "Name Ch.2" (+ a plain "Name" = part 1) belong together:
// → { groups: [{ name: 'Name', dirs: [...] }], rest: [folders that stand alone] }
function stemGroups(dirs) {
  const keyOf = d => { const p = seriesStem(d.name, false), name = tidyName(p.before); return { key: name.toLowerCase(), name, num: p.num }; };
  const groups = new Map();
  for (const d of dirs) { const k = keyOf(d); if (k.num != null && k.key) { if (!groups.has(k.key)) groups.set(k.key, { name: k.name, dirs: [] }); groups.get(k.key).dirs.push(d); } }
  for (const d of dirs) { const k = keyOf(d); if (k.num == null && groups.has(k.key)) groups.get(k.key).dirs.unshift(d); }
  const out = [...groups.values()].filter(g => g.dirs.length >= 2);
  out.forEach(g => { const [lead, ...nums] = g.dirs; const plain = keyOf(lead).num == null;
    g.dirs = plain ? [lead, ...nums.sort((a, b) => keyOf(a).num - keyOf(b).num)] : g.dirs.sort((a, b) => keyOf(a).num - keyOf(b).num); });
  const used = new Set(out.flatMap(g => g.dirs));
  return { groups: out, rest: dirs.filter(d => !used.has(d)) };
}
function planUploads(items, ctx) {
  const jobs = [], root = fileTree(items);
  const fileJob = (f, place) => jobs.push({ f, name: f.name, size: f.size, ...place });
  const packJob = (name, images, place) => jobs.push({ name: safeName(name) + '.cbz', images, size: images.reduce((n, f) => n + f.size, 0), packed: true, ...place });
  const top = { series: ctx.seriesId || undefined, collection: ctx.colFolder || undefined };
  archivesIn(root).forEach(f => fileJob(f, top));
  if (imagesIn(root).length) {
    const nm = ctx.seriesId ? `Chapter ${new Date().toISOString().slice(0, 10)}` : `Images ${new Date().toISOString().slice(0, 10)}`;
    packJob(nm, imagesIn(root), ctx.seriesId ? top : { ...top, folder: nm });
  }
  const planFolder = (d, c) => {
    const subs = Object.values(d.dirs);
    const imgSubs = subs.filter(isImageFolder).sort((a, b) => natCmp(a.name, b.name));
    const otherSubs = subs.filter(x => !imgSubs.includes(x));
    const arcs = archivesIn(d), imgs = imagesIn(d);
    const asCollection = !c.seriesId && !c.colFolder && (otherSubs.length > 0 || (arcs.length > 1 && !relatedArchives(arcs) && !imgs.length && !imgSubs.length));
    const seriesPlace = c.seriesId ? { series: c.seriesId } : { collection: c.colFolder || undefined, folder: d.name };
    if (asCollection) {
      arcs.forEach(f => fileJob(f, { collection: d.name }));                      // loose = one series each
      if (imgs.length) packJob(d.name, imgs, { collection: d.name, folder: d.name });
      const sg = stemGroups(imgSubs);                                             // "Name 1", "Name 2" → series "Name"
      sg.groups.forEach(g => g.dirs.forEach(x => packJob(x.name, imagesIn(x), { collection: d.name, folder: safeName(g.name) })));
      sg.rest.forEach(x => packJob(x.name, imagesIn(x), { collection: d.name, folder: x.name }));
      otherSubs.forEach(x => planFolder(x, { colFolder: d.name }));
      return;
    }
    if (imgs.length) packJob(d.name, imgs, seriesPlace);                          // the folder itself is a chapter
    imgSubs.forEach(x => packJob(x.name, imagesIn(x), seriesPlace));              // each image subfolder is a chapter
    arcs.forEach(f => fileJob(f, seriesPlace));
    otherSubs.forEach(x => planFolder(x, c));
  };
  // image folders dropped side by side: "Name 1", "Name 2"… → one series "Name", a chapter each
  const tg = ctx.seriesId ? { groups: [], rest: [] } : stemGroups(Object.values(root.dirs).filter(isImageFolder));
  tg.groups.forEach(g => g.dirs.forEach(x => packJob(x.name, imagesIn(x), { collection: ctx.colFolder || undefined, folder: safeName(g.name) })));
  const grouped = new Set(tg.groups.flatMap(g => g.dirs));
  Object.values(root.dirs).filter(d => !grouped.has(d)).forEach(d => planFolder(d, ctx));
  return jobs;
}

/* ---------- Cosplay planner: Cosplayer → Set → Variant ----------
   Every set in a drop — a folder of photos (± videos) or an archive — is one *unit*; it becomes a variant.
   The server says which cosplayer and set each unit belongs to (POST …/cosplay-plan), so the naming rules
   live in one place (app/library.py: cosplay_name / variant_groups):
     "[Dreva(Solene)]My Lucky Bunny Bonus / Normal / S_version"  →  Solene / My Lucky Bunny / 3 variants
   A dropped folder of sets ("Solene/…") names the cosplayer when the set names don't; a folder holding only
   archives is one set with each archive a variant. Dropped onto a set page: everything joins that set.
   The circle (Dreva) stays in the names → shown as publisher. Photo units are packed into <name>.zip,
   video-only units stay folders of videos. */
const mediaIn = n => n.files.filter(f => IMG_RE.test(f.name) || VIDEO_RE.test(f.name)).sort((a, b) => natCmp(a.name, b.name));
const booksIn = n => n.files.filter(f => BOOK_RE.test(f.name)).sort((a, b) => natCmp(a.name, b.name));
const isLeaf = n => !Object.keys(n.dirs).length;
const stemOf = f => f.name.replace(/\.[^.]+$/, '');
function cosplayUnits(root) {
  const units = [];
  const stamp = `Set ${new Date().toISOString().slice(0, 10)}`;
  if (mediaIn(root).length) units.push({ name: stamp, media: mediaIn(root) });
  booksIn(root).forEach(f => units.push({ name: stemOf(f), file: f }));
  const walk = (d, parent) => {
    if (isLeaf(d)) {
      if (mediaIn(d).length) units.push({ name: d.name, media: mediaIn(d), parent });
      const arcs = booksIn(d);                         // a folder of archives = one set, archives = its variants
      arcs.forEach(f => units.push({ name: stemOf(f), file: f, parent, setHint: mediaIn(d).length ? null : d.name }));
      return;
    }
    if (mediaIn(d).length) units.push({ name: d.name, media: mediaIn(d), parent });
    booksIn(d).forEach(f => units.push({ name: stemOf(f), file: f, parent: d.name }));
    Object.values(d.dirs).sort((a, b) => natCmp(a.name, b.name)).forEach(x => walk(x, d.name));
  };
  Object.values(root.dirs).sort((a, b) => natCmp(a.name, b.name)).forEach(d => walk(d, null));
  return units;
}
function planCosplay(items, ctx, plans = {}) {
  const jobs = [];
  for (const u of cosplayUnits(fileTree(items))) {
    const p = plans[u.name] || {};
    const place = ctx.seriesId ? { series: ctx.seriesId }
      : { collection: ctx.colFolder || p.cosplayer || u.parent || undefined, folder: safeName(u.setHint || p.set || u.name) };
    if (u.file) { jobs.push({ f: u.file, name: u.file.name, size: u.file.size, ...place }); continue; }
    if (u.media.some(f => IMG_RE.test(f.name))) {     // photos (± videos in their place) → <name>.zip
      jobs.push({ name: safeName(u.name) + '.zip', images: u.media, size: u.media.reduce((n, f) => n + f.size, 0), packed: true, ...place });
    } else {                                          // video-only variant → its own folder of videos
      const sub = safeName(u.name);
      u.media.forEach(f => jobs.push({ f, name: f.name, size: f.size, ...place, folder: place.folder ? `${place.folder}/${sub}` : sub }));
    }
  }
  return jobs;
}

// images in a folder (or the top of the drop) that also holds .cbz/.epub/… archives
function strayImages(items) {
  const byDir = new Map();
  for (const it of items) {
    const dir = it.path.includes('/') ? it.path.slice(0, it.path.lastIndexOf('/')) : '';
    if (!byDir.has(dir)) byDir.set(dir, []);
    byDir.get(dir).push(it);
  }
  const out = [];
  for (const list of byDir.values())
    if (list.some(it => BOOK_RE.test(it.file.name))) out.push(...list.filter(it => IMG_RE.test(it.file.name)));
  return out;
}
// small Yes / No dialog → Promise<boolean>. Esc or clicking outside = No.
function askDialog({ title, body, yes = 'Yes', no = 'No' }) {
  return new Promise(res => {
    const o = document.createElement('div');
    o.className = 'overlay fixed open askmodal';
    o.innerHTML = `<div class="sheet libform" role="dialog" aria-modal="true"><h3>${esc(title)}</h3><div class="askbody">${body}</div>
      <div class="mrow askrow"><button class="btn-ghost" data-ask="0">${esc(no)}</button><button class="btn-primary" data-ask="1">${esc(yes)}</button></div></div>`;
    const done = v => { document.removeEventListener('keydown', key, true); o.remove(); res(v); };
    const key = e => { if (!e.isTrusted) return; if (e.key === 'Escape') { e.stopImmediatePropagation(); done(false); } else if (e.key === 'Enter') { e.preventDefault(); done(true); } };
    o.addEventListener('click', e => { const b = e.target.closest('[data-ask]'); if (b && e.isTrusted) done(b.dataset.ask === '1'); });
    backdropCloses(o, () => done(false));
    document.addEventListener('keydown', key, true);
    document.body.appendChild(o);
    o.querySelector('[data-ask="1"]').focus();
  });
}

/* ---------- tiny ZIP writer (STORE) so image folders become .cbz in the browser ---------- */
const CRC_T = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(buf) { let c = 0xFFFFFFFF; for (let i = 0; i < buf.length; i++) c = CRC_T[(c ^ buf[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
async function makeCbz(images, onStep) {
  const enc = new TextEncoder(), parts = [], central = [];
  let offset = 0;
  const pad = String(images.length).length;
  for (let i = 0; i < images.length; i++) {
    const f = images[i];
    const data = new Uint8Array(await f.arrayBuffer());
    const crc = crc32(data);
    const ext = (f.name.match(/\.[^.]+$/) || ['.jpg'])[0].toLowerCase();
    const name = enc.encode(String(i + 1).padStart(Math.max(3, pad), '0') + ext);   // stable reading order
    const lh = new DataView(new ArrayBuffer(30));
    lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true);
    lh.setUint16(12, 0x21, true); lh.setUint32(14, crc, true); lh.setUint32(18, data.length, true);
    lh.setUint32(22, data.length, true); lh.setUint16(26, name.length, true);
    const ch = new DataView(new ArrayBuffer(46));
    ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true);
    ch.setUint16(14, 0x21, true); ch.setUint32(16, crc, true); ch.setUint32(20, data.length, true); ch.setUint32(24, data.length, true);
    ch.setUint16(28, name.length, true); ch.setUint32(42, offset, true);
    parts.push(lh, name, f); central.push(ch, name);
    offset += 30 + name.length + data.length;
    onStep?.(i + 1, images.length);
  }
  const cdSize = central.reduce((n, p) => n + p.byteLength, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, images.length, true); end.setUint16(10, images.length, true);
  end.setUint32(12, cdSize, true); end.setUint32(16, offset, true);
  return new Blob([...parts, ...central, end], { type: 'application/zip' });
}

async function uploadFiles(lid, input, seriesId = null, colFolder = null) {
  const items = input.map(x => x.file ? x : { file: x, path: x.webkitRelativePath || x.name });
  let usable = items.filter(it => BOOK_RE.test(it.file.name) || IMG_RE.test(it.file.name) || VIDEO_RE.test(it.file.name));
  // images lying next to archives (posters, covers, scans of the box…) would be packed into a chapter / set of
  // their own — ask first. A drop of *only* images is a photo set / chapter on purpose: no question then.
  const stray = strayImages(usable);
  let strayNote = 0;
  if (stray.length) {
    const keep = await askDialog({
      title: 'Stray images found',
      body: `<p><b>${plural(stray.length, 'image')}</b> ${stray.length === 1 ? 'sits' : 'sit'} next to comic archives in this drop:</p>
        <p class="askfiles">${stray.slice(0, 6).map(it => `<code>${esc(it.path)}</code>`).join(' ')}${stray.length > 6 ? ` <span>+${stray.length - 6} more</span>` : ''}</p>
        <p class="hintline"><b>Keep</b> packs them into a ${V(lid).ch} of their own · <b>Skip</b> adds only the archives.</p>`,
      yes: 'Keep them', no: 'Skip them' });
    if (!keep) { const drop = new Set(stray); usable = usable.filter(it => !drop.has(it)); strayNote = stray.length; }
  }
  // regular .zip / .rar / .7z: probably a comic, but ask — they're converted to .cbz on the server
  // (Cosplay keeps a .zip as it is — it's the usual format there; .rar / .7z still become .zip after asking)
  const plain = usable.filter(it => PLAIN_ARCHIVE_RE.test(it.file.name) && !(isCosplay(lid) && /\.zip$/i.test(it.file.name)));
  const packExt = isCosplay(lid) ? '.zip' : '.cbz';
  let plainNote = 0;
  if (plain.length) {
    const exts = [...new Set(plain.map(it => it.file.name.split('.').pop().toLowerCase()))].map(x => '.' + x).join(' / ');
    const conv = await askDialog({
      title: plain.length === 1 ? 'Archive found' : 'Archives found',
      body: `<p><b>${plural(plain.length, 'regular archive')}</b> (${esc(exts)}) in this drop:</p>
        <p class="askfiles">${plain.slice(0, 6).map(it => `<code>${esc(it.path)}</code>`).join(' ')}${plain.length > 6 ? ` <span>+${plain.length - 6} more</span>` : ''}</p>
        <p class="hintline"><b>Convert</b> turns each into a <code>${packExt}</code> ${isCosplay(lid) ? 'set' : 'comic'} (only its pictures &amp; videos are kept) · <b>Skip</b> leaves ${plain.length === 1 ? 'it' : 'them'} out.</p>`,
      yes: `Convert to ${packExt}`, no: 'Skip' });
    if (!conv) { const drop = new Set(plain); usable = usable.filter(it => !drop.has(it)); plainNote = plain.length; }
  }
  const ignored = items.length - usable.length - strayNote - plainNote;
  let jobs;
  if (isCosplay(lid)) {                               // ask the server how the set names split, then plan
    let plans = {};
    if (!seriesId) {
      const names = [...new Set(cosplayUnits(fileTree(usable)).map(u => u.name))];
      try { plans = (await jsonFetch('POST', `/api/libraries/${lid}/cosplay-plan`, { names })).plans || {}; } catch {}
    }
    jobs = planCosplay(usable, { seriesId, colFolder }, plans);
  } else jobs = planUploads(usable, { seriesId, colFolder });
  if (!jobs.length && (strayNote || plainNote)) { appToast('Nothing to add — you skipped everything in that drop'); return 0; }
  if (!jobs.length) { UP.rows.push({ f: { size: 0 }, name: `${plural(items.length, 'file')} skipped`, state: 'err', msg: 'No comics, images or videos', p: 1 }); return renderUploads(true); }
  const batch = jobs.map(j => ({ ...j, f: j.f || { size: j.size }, lib: lid, state: 'queued', msg: j.packed ? `${j.images.length} images → ${j.name.slice(j.name.lastIndexOf('.'))}` : 'Waiting', p: 0,
    where: j.series ? '' : [j.collection && `🗂️ ${j.collection}`, j.folder].filter(Boolean).join(' / ') }));
  if (ignored) batch.push({ f: { size: 0 }, name: `${plural(ignored, 'other file')} ignored`, state: 'skip', msg: 'Not a comic', p: 1 });
  if (plainNote) batch.push({ f: { size: 0 }, name: `${plural(plainNote, 'archive')} skipped`, state: 'skip', msg: 'Your choice', p: 1 });
  if (strayNote) batch.push({ f: { size: 0 }, name: `${plural(strayNote, 'stray image')} skipped`, state: 'skip', msg: 'Your choice', p: 1 });
  UP.rows.push(...batch); renderUploads(true);
  const queue = batch.filter(r => r.state === 'queued');
  const worker = async () => { let r; while ((r = queue.shift())) if (r.state === 'queued') await putFile(r); };
  await Promise.all([worker(), worker()]);
  await api.post('/api/scan');
  setTimeout(load, 700); setTimeout(load, 2500);
  const added = batch.filter(r => r.state === 'ok').length;
  if (!UP.rows.some(r => r.state === 'err' || r.state === 'queued' || r.state === 'up')) {
    setTimeout(() => { if (!UP.rows.some(r => r.state === 'queued' || r.state === 'up' || r.state === 'err')) { UP.rows = []; $('#uploads').classList.remove('on'); } }, 6000);
  }
  return added;
}
async function putFile(r) {
  if (r.packed && !(r.f instanceof Blob)) {
    r.state = 'up'; r.msg = 'Packing…'; renderUploads();
    try { r.f = await makeCbz(r.images, (i, n) => { if (r.cancel) throw new Error('cancelled'); r.msg = `Packing ${i}/${n}`; r.p = i / n * .3; renderUploads(); }); }
    catch (err) { if (r.cancel) return markCancelled(r); r.state = 'err'; r.p = 1; r.msg = 'Couldn’t read images'; renderUploads(); return; }
    if (r.cancel) return markCancelled(r);
    r.images = null;
  }
  return new Promise(res => {
    const x = new XMLHttpRequest();
    r.xhr = x;
    x.onabort = () => { r.xhr = null; markCancelled(r); res(); };
    r.state = 'up'; r.msg = '0%';
    const q = new URLSearchParams({ name: r.name });
    if (r.series) q.set('series', r.series);
    if (r.collection) q.set('collection', r.collection);
    if (r.folder) q.set('folder', r.folder);
    x.open('PUT', `/api/libraries/${r.lib}/files?${q}`);
    const base = r.packed ? .3 : 0;
    x.upload.onprogress = e => { if (e.lengthComputable) { r.p = base + (1 - base) * e.loaded / e.total; r.msg = Math.round(e.loaded / e.total * 100) + '%'; renderUploads(); } };
    x.onload = () => {
      let d = {}; try { d = JSON.parse(x.responseText); } catch {}
      if (x.status < 300) { r.p = 1; r.state = d.skipped ? 'skip' : 'ok'; r.msg = d.skipped ? 'Already there' : d.converted ? `Converted to ${d.path.slice(d.path.lastIndexOf('.'))} ✓` : 'Added ✓'; }
      else { r.state = 'err'; r.p = 1; r.msg = d.detail || `Error ${x.status}`; }
      renderUploads(); res();
    };
    x.onerror = () => { r.state = 'err'; r.p = 1; r.msg = 'Network error'; renderUploads(); res(); };
    x.send(r.f); renderUploads();
  });
}
function markCancelled(r) { r.state = 'cancel'; r.msg = 'Cancelled'; r.p = 1; r.images = null; renderUploads(); }
// stop everything still waiting / packing / sending. Files that already finished stay in the library;
// a half-sent file is thrown away by the server (it only keeps uploads that arrived complete).
function cancelUploads() {
  let n = 0;
  for (const r of UP.rows) {
    if (r.state === 'queued') { markCancelled(r); n++; }
    else if (r.state === 'up') { r.cancel = true; n++; if (r.xhr) r.xhr.abort(); }   // packing rows stop at the next image
  }
  if (n) appToast(`Cancelled ${plural(n, 'upload')}`);
}
let upRaf;
// The header (title, bar, buttons) is built once and only *updated*, so its buttons stay the same elements and
// clicks land even mid-upload. The list is the heavy part: redrawn at most ~3×/s, never while minimised,
// and capped to the rows worth seeing (uploading, failed, then newest).
const UP_LIST_MAX = 150, UP_LIST_EVERY = 350;
function upShell() {
  const box = $('#uploads');
  if (!box.querySelector('.up-h')) {
    box.innerHTML = `<div class="up-h"><b class="up-t"></b><span class="pct"></span><div class="bar"><i></i></div>
      <button class="upcancel" data-upcancel title="Stop the uploads that haven’t finished">Cancel</button>
      <button data-upmin></button><button data-upclose title="Close">×</button></div><div class="up-list"></div>`;
    UP.listAt = 0;
  }
  return box;
}
function renderUploads(show) {
  if (show) $('#uploads').classList.add('on');
  cancelAnimationFrame(upRaf);
  upRaf = requestAnimationFrame(() => {
    const box = upShell(), rows = UP.rows;
    let active = 0, ok = 0, err = 0, cut = 0, total = 0, sent = 0;
    for (const r of rows) {
      if (r.state === 'queued' || r.state === 'up') active++; else if (r.state === 'ok') ok++; else if (r.state === 'err') err++; else if (r.state === 'cancel') cut++;
      const n = r.f.size || 0; total += n; sent += n * r.p;
    }
    const pct = Math.round(sent / (total || 1) * 100);
    box.classList.toggle('min', UP.min);
    const h = box.querySelector('.up-h');
    h.querySelector('.up-t').textContent = active ? `Adding ${plural(active, 'file')}…` : `${plural(ok, 'file')} added${err ? ` · ${err} failed` : ''}${cut ? ` · ${cut} cancelled` : ''}`;
    const pc = h.querySelector('.pct'); pc.textContent = `${pct}%`; pc.hidden = !(UP.min && active);
    const bar = h.querySelector('.bar'); bar.hidden = !(active || UP.min); bar.firstChild.style.width = `${active ? pct : 100}%`;
    h.querySelector('[data-upcancel]').hidden = !active;
    const mb = h.querySelector('[data-upmin]'); mb.textContent = UP.min ? '▴' : '▾'; mb.title = UP.min ? 'Show files' : 'Minimise';
    if (UP.min) return;                              // list hidden: don't spend time on it
    const now = performance.now();
    if (active && now - (UP.listAt || 0) < UP_LIST_EVERY) {   // too soon: come back for the last update
      clearTimeout(UP.listT); UP.listT = setTimeout(() => renderUploads(), UP_LIST_EVERY);
      return;
    }
    UP.listAt = now;
    const rank = r => r.notice ? 0 : r.state === 'up' ? 1 : r.state === 'err' ? 2 : 3;
    const shown = rows.map((r, i) => [r, i]).sort((x, y) => rank(x[0]) - rank(y[0]) || y[1] - x[1]).slice(0, UP_LIST_MAX).map(x => x[0]);
    box.querySelector('.up-list').innerHTML = shown.map(r => r.notice ? `<div class="up-row notice">${esc(r.name)}
        <div class="up-acts"><button class="btn-sm" data-uplist="copy">Copy list</button><button class="btn-sm" data-uplist="save">Save list…</button></div></div>`
      : `<div class="up-row ${{ ok: 'ok', err: 'err', skip: 'skip', cancel: 'skip' }[r.state] || ''}">
        <span class="n" title="${esc(r.inside || r.name)}">${esc(r.name)}${r.where ? `<small class="w">${r.inside ? '' : '→ '}${esc(r.where)}</small>` : ''}</span><span class="s">${esc(r.msg)}</span>
        <div class="bar"><i style="width:${Math.round(r.p * 100)}%"></i></div></div>`).join('')
      + (rows.length > shown.length ? `<div class="up-more">+ ${plural(rows.length - shown.length, 'more file')}</div>` : '');
  });
}

/* ======================= FAVOURITES ======================= */
// Lists of references kept on the server (/config/favorites.json) — nothing is copied on disk.
// Comics / manga / novels: whole series. Cosplay: single sets (books), never a whole collection.
S.favs = []; S.favById = {};
function setFavs(list) { S.favs = list || []; S.favById = Object.fromEntries(S.favs.map(f => [f.id, f])); }
async function refreshFavs() {
  try { setFavs(await api.get('/api/favorites')); } catch {}
  renderSidebar();
  if (S.inFavs) renderFavs(S.favCur);
}
// what the open ⋯ menu would favourite: ['series', id] or ['book', id] — or null when it can't be favourited
function favKey(t) {
  if (M.kind === 'series') {
    if (t.empty || !t.books?.length) return null;
    return ['series', t.id];                                        // a series / a Cosplay set
  }
  if (M.kind === 'book') return isCosplay(t.library) ? ['book', t.id] : null;   // one Cosplay variant
  return null;
}
const inFav = (f, fk) => !!f && !!fk && f.items.some(i => i.kind === fk[0] && i.id === fk[1]);
const favItems = f => f.items.map(i => i.kind === 'series' ? (S.seriesById[i.id]?.books.length ? { kind: 'series', s: S.seriesById[i.id] } : null)
  : S.books[i.id] ? { kind: 'book', b: S.books[i.id] } : null).filter(Boolean);
function favCount(f) {
  const live = favItems(f), ns = live.filter(x => x.kind === 'series').length, nb = live.length - ns;
  return [ns && plural(ns, 'series / set'), nb && plural(nb, 'variant')].filter(Boolean).join(' · ') || 'Empty list';
}
function favSeriesCard(s, k) {
  const i = seriesInfo(s), one = s.books.length === 1;
  return `<button class="card ${seriesTrashed(s) ? 'trashed' : newCount(s) && !one ? 'unread' : ''}" data-series="${s.id}" ${one ? `data-single="${s.books[0].id}"` : ''} style="--d:${Math.min(k, 20) * 30}ms">
    <div class="cover">${seriesCover(s, 320)}${i.unread === 0 ? '<span class="badge done">READ</span>' : ''}${s.raw || s.jxl || s.heic ? `<div class="blc">${fmtPills(s)}</div>` : ''}</div>
    <div class="pbar"><i style="width:${Math.round(i.frac * 100)}%"></i></div>
    <div class="ct">${escWrap(s.name)}</div>
    <div class="cm">${one ? progressText(s.books[0]) : countLabel(s)} · ${esc(libName(s.library))}</div>
  </button>`;
}
function favSetCard(b, k) {
  const glow = bookGlow(b, true);                                   // favourited sets: always Cosplay
  return `<button class="card ch ${isDone(b) ? 'done' : ''} ${b.trashed ? 'trashed' : glow}" data-open="${b.id}" style="--d:${Math.min(k, 20) * 30}ms">
    <div class="cover">${coverImg(b, 320)}${statusBadge(b, glow)}${b.format === 'video' ? '<span class="badge fmt">▶ VIDEO</span>' : ''}${b.raw || b.jxl || b.heic ? `<div class="blc">${fmtPills(b)}</div>` : ''}</div>
    <div class="pbar"><i style="width:${Math.round(bookFrac(b) * 100)}%"></i></div>
    <div class="ct">${escWrap(b.label)}</div>
    <div class="cm">📸 ${esc(S.seriesById[b.seriesId]?.name || b.series)}</div>
  </button>`;
}
function renderFavs(fid) {
  $('#viewHome').classList.remove('on'); $('#viewSeries').classList.remove('on');
  const v = $('#viewFavs'); v.classList.add('on');
  S.inFavs = true; S.favCur = fid || null;
  if (!fid) {
    const cards = S.favs.map((f, k) => {
      const covers = favItems(f).slice(0, 3).map(x => x.kind === 'series' ? seriesCover(x.s, 200) : coverImg(x.b, 200));
      return `<button class="card colcard favcard" data-favlist="${f.id}" style="--d:${Math.min(k, 20) * 30}ms">
        <div class="cover stack">${covers.length ? covers.map((c, j) => `<div class="stk s${j}">${c}</div>`).join('') : `<div class="stk s0 emptycol">${ico('heart', 54)}</div>`}
          <span class="badge fmt">♥ FAVOURITES</span></div>
        <div class="ct">${escWrap(f.name)}</div><div class="cm">${favCount(f)}</div></button>`;
    });
    v.innerHTML = `<div class="shelf-h"><div><h2 class="favtitle">${ico('heartF', 26)} Favourites</h2><p>${S.favs.length ? plural(S.favs.length, 'list') : 'Your own lists — nothing on disk is copied or moved'}</p></div>
        <div class="shelf-actions"><button class="btn-sm pri" data-newfav>+ New list</button></div></div>
      ${S.favs.length ? `<div class="grid">${cards.join('')}</div>`
        : `<div class="empty">${ico('heart', 40)}<p><b>No favourites yet.</b><br>Make a list here, or open the <b>⋯</b> menu of a series (or of a Cosplay set or variant) and choose <b>Add to Favourites</b>.</p></div>`}`;
  } else {
    const f = S.favById[fid];
    if (!f) { location.hash = '#/favs'; return; }
    const live = favItems(f), missing = f.items.length - live.length;
    v.innerHTML = `<button class="crumb" data-favback>${ico('chevL', 16)} ${ico('heart', 15)} Favourites</button>
      <div class="shelf-h"><div><h2 class="favtitle">${ico('heartF', 26)} ${esc(f.name)}</h2><p>${favCount(f)}</p></div>
        <div class="shelf-actions"><button class="btn-sm" data-more="favlist:${f.id}">⋯ List</button></div></div>
      ${missing ? `<p class="favmiss">${plural(missing, 'item')} can’t be found right now — deleted, or its library is offline. ${missing === 1 ? 'It reappears' : 'They reappear'} here if the files come back.</p>` : ''}
      ${live.length ? `<div class="grid">${live.map((x, k) => x.kind === 'series' ? favSeriesCard(x.s, k) : favSetCard(x.b, k)).join('')}</div>`
        : `<div class="empty">${ico('heart', 40)}<p><b>This list is empty.</b><br>Open the <b>⋯</b> menu of a series — or of a Cosplay set or variant — and choose <b>Add to Favourites</b>.</p></div>`}`;
  }
  $('#main').scrollTop = 0;
}
function renderFavListMenu(view, t, err = '') {
  const back = `<button data-mact="main">${ico('chevL', 17)} Back</button><div class="msep"></div>`;
  const body = view === 'del'
    ? `<p class="mnote">Delete the list <b>${esc(t.name)}</b>?<br>Only the list goes — everything in it stays exactly where it is.</p>
       <div class="mrow"><button class="btn-sm" data-mact="main">Cancel</button><button class="btn-sm danger-solid" data-mact="confirmdel">${ico('trash', 15)} Delete list</button></div>`
    : `${location.hash === `#/fav/${t.id}` ? '' : `<button data-mact="open">${ico('heart', 17)} Open list</button>`}
       <button data-mact="rename">${ico('sliders', 17)} Rename…</button><div class="msep"></div>
       <button class="danger" data-mact="del">${ico('trash', 17)} Delete list</button>`;
  const m = $('#menu');
  m.innerHTML = `<div class="mhead"><b>♥ ${esc(t.name)}</b><small>${favCount(t)}</small></div>${view === 'del' ? '' : ''}${body}${err ? `<div class="merr">${esc(err)}</div>` : ''}`;
  m.classList.add('on'); m.classList.remove('busy'); $('#menuShade').classList.add('on');
  placeMenu();
}

/* ======================= ITEM MENU (⋯ · long-press · right-click) ======================= */
const M = { kind: null, id: null };
let appToastT;
function appToast(msg) { const t = $('#apptoast'); t.textContent = msg; t.classList.add('show'); clearTimeout(appToastT); appToastT = setTimeout(() => t.classList.remove('show'), 2600); }
const menuTarget = () => {
  if (M.kind === 'favlist') { const f = S.favById[M.id]; return f ? { ...f, isFavList: true } : null; }
  if (M.kind === 'series') return S.seriesById[M.id];
  if (M.kind === 'collection') {
    const c = S.colById[M.id]; if (!c) return null;
    const inside = S.byCol[c.id] || [];
    return { ...c, isCol: true, inside, files: inside.reduce((n, x) => n + x.books.length, 0) };
  }
  if (M.kind === 'multiseries') {
    const list = M.ids.map(id => S.seriesById[id]).filter(Boolean); if (!list.length) return null;
    return { multi: true, multiSeries: true, ids: M.ids, label: `${plural(list.length, V(list[0].library).s)} selected`, title: '', series: list.map(x => x.name).slice(0, 2).join(', ') + (list.length > 2 ? '…' : ''),
      seriesId: null, library: list[0].library, kind: 'series', files: list.reduce((n, x) => n + x.books.length, 0) };
  }
  if (M.kind === 'books') {
    const first = S.books[M.ids[0]]; if (!first) return null;
    return { multi: true, ids: M.ids, label: `${plural(M.ids.length, 'item')} selected`, title: '', series: first.series, seriesId: first.seriesId, library: first.library, kind: 'chapter' };
  }
  return S.books[M.id];
};
// a library in the sidebar: right-click / long-press
function renderLibraryMenu() {
  const l = S.libById[M.id]; if (!l) return closeMenu();
  const m = $('#menu');
  m.innerHTML = `<div class="mhead"><b>${esc(l.name)}</b><small>${esc(plural(l.series || 0, V(l.id).s))} · ${esc(plural(l.books || 0, 'file'))}</small></div>
    <button data-libmenu="settings">${ico('sliders', 17)} Library settings</button>`;
  m.classList.add('on'); $('#menuShade').classList.add('on'); placeMenu();
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-libmenu]'); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const l = S.libById[M.id]; closeMenu();
  if (l) openLibModal(l);
}, true);
function openSeriesBatchMenu(ids, anchor, view = 'main') {
  Object.assign(M, { kind: 'multiseries', ids, id: null, anchor, ev: null });
  renderMenu(view);
}
function openBooksMenu(ids, anchor, view = 'main') {
  Object.assign(M, { kind: 'books', ids, id: null, anchor, ev: null });
  renderMenu(view === 'del' ? 'del' : view);
}
const isPhone = () => matchMedia('(max-width: 860px)').matches;

function openMenu(key, anchor, ev) {
  const [kind, id] = key.split(':');
  Object.assign(M, { kind, id, anchor, ev });
  $$('.more.on').forEach(x => x.classList.remove('on'));
  anchor?.querySelector?.('.more')?.classList.add('on');
  if (anchor?.classList?.contains('more')) anchor.classList.add('on');
  renderMenu('main');
}
function closeMenu() {
  $('#menu').classList.remove('on', 'busy'); $('#menuShade').classList.remove('on');
  $$('.more.on').forEach(x => x.classList.remove('on'));
  M.kind = null;
}
function placeMenu() {
  const m = $('#menu');
  if (isPhone()) { m.style.left = m.style.top = ''; return; }
  if (!M.ev && M.anchor && !M.anchor.isConnected) return;   // the page re-rendered under the menu: stay where it is
  const r = M.ev ? { left: M.ev.clientX, right: M.ev.clientX, top: M.ev.clientY, bottom: M.ev.clientY } : M.anchor.getBoundingClientRect();
  const w = m.offsetWidth, h = m.offsetHeight;
  const left = clamp(M.ev ? r.left : r.right - w, 10, innerWidth - w - 10);
  let top = r.bottom + 6;
  if (top + h > innerHeight - 10) top = Math.max(10, r.top - h - 6);
  m.style.left = left + 'px'; m.style.top = top + 'px';
}
function seriesChoices(q) {
  const t = menuTarget(), lib = t.library, self = M.kind === 'series' ? t.id : t.multi ? null : t.seriesId;
  q = q.trim().toLowerCase();
  const skip = new Set(t.multiSeries ? t.ids : [self]);
  return S.series.filter(x => !skip.has(x.id) && (!q || x.name.toLowerCase().includes(q)))
    .sort((a, b) => (b.library === lib) - (a.library === lib) || a.name.localeCompare(b.name)).slice(0, 80)
    .map(x => `<button data-toseries="${x.id}">${seriesCover(x, 120)}<span><b>${esc(x.name)}</b><small>${esc(libName(x.library))} · ${countLabel(x)}</small></span></button>`).join('')
    || `<p class="mnote">No other ${pl(V(lib).s)} match.</p>`;
}
function renderCollectionMenu(view, t, err) {
  const back = `<button data-mact="main">${ico('chevL', 17)} Back</button><div class="msep"></div>`;
  let body = '';
  const v = V(t.library);
  if (view === 'main') body = `<button data-mact="open">${ico('book', 17)} Open ${v.g}</button>
      <button data-mact="rename">${ico('sliders', 17)} Rename…</button>
      <button data-mact="ungroup" ${t.inside.length ? '' : 'disabled'}>${ico('move', 17)} Ungroup — keep ${pl(v.s)} in ${esc(libName(t.library))}</button>
      <div class="msep"></div><button class="danger" data-mact="del">${ico('trash', 17)} ${t.files ? 'Move to trash' : `Delete ${v.g}`}</button>`;
  else if (view === 'purge') body = `<p class="mnote">Delete <b>forever</b>? The files are removed from disk right now, with their reading progress. This can’t be undone.</p><div class="mrow"><button class="btn-sm" data-mact="main">Cancel</button><button class="btn-sm danger-solid" data-mact="confirmpurge">${ico('trash', 15)} Delete forever</button></div>`;
  else if (view === 'del') body = `<p class="mnote">${t.files ? 'Move' : 'Delete'} <b>${esc(t.name)}</b>${t.files ? ' to the trash' : ''}?<br>${t.files ? `${plural(t.inside.length, v.s)} (${plural(t.files, 'file')}) leave the library in a few minutes and can be restored for 30 days. Use <b>Ungroup</b> instead to keep them.` : 'It’s empty — only the folder is removed.'}</p>
      <div class="mrow"><button class="btn-sm" data-mact="main">Cancel</button><button class="btn-sm danger-solid" data-mact="confirmdel">${ico('trash', 15)} ${t.files ? 'Move to trash' : 'Delete'}</button></div>`;
  if (view === 'main' && t.inside.length && t.inside.every(seriesTrashed))
    body = `<p class="mnote">In the trash. It leaves the library in a few minutes and can be restored for 30 days.</p><button data-mact="restore">${ico('refresh', 17)} Restore</button><div class="msep"></div><button class="danger" data-mact="purge">${ico('trash', 17)} Delete forever</button>`;
  const m = $('#menu');
  m.innerHTML = `<div class="mhead"><b>🗂️ ${esc(t.name)}</b><small>${t.inside.length ? plural(t.inside.length, v.s) : 'Empty'} · ${esc(libName(t.library))}</small></div>${view === 'main' ? '' : ''}${body}${err ? `<div class="merr">${esc(err)}</div>` : ''}`;
  m.classList.add('on'); m.classList.remove('busy'); $('#menuShade').classList.add('on'); placeMenu();
}
function renderMenu(view, err = '') {
  if (M.kind === 'library') return renderLibraryMenu();
  const t = menuTarget(); if (!t) return closeMenu();
  if (t.isCol) return renderCollectionMenu(view, t, err);
  if (t.isFavList) return renderFavListMenu(view, t, err);
  const isS = M.kind === 'series';
  const fk = favKey(t), cur = S.favCur && S.favById[S.favCur];
  const favOpts = !fk ? '' : `<button data-mact="fav">${ico('heart', 17)} Add to Favourites <span class="chev">›</span></button>`
    + (cur && inFav(cur, fk) ? `<button data-mact="favremove">${ico('heartF', 17)} Remove from ${esc(cur.name)}</button>` : '');
  const v = V(t.library);
  const what = isS ? v.s : t.multiSeries ? plural(t.ids.length, v.s) : t.multi ? plural(t.ids.length, 'item') : isCosplay(t.library) ? v.b : t.kind === 'volume' ? 'volume' : t.kind === 'chapter' ? 'chapter' : 'book';
  const back = `<button data-mact="main">${ico('chevL', 17)} Back</button><div class="msep"></div>`;
  let body = '';
  if (view === 'main') {
    const editOpt = isS && !t.empty ? `<button data-mact="details">${ico('edit', 17)} Edit details…</button>` : '';
    const colOpt = (isS || t.multiSeries) ? `${editOpt}<button data-mact="col">${ico('folder', 17)} Move to ${v.g} <span class="chev">›</span></button>` : '';
    body = (isS && t.empty ? `<button data-mact="rename">${ico('sliders', 17)} Rename…</button>${colOpt}` : `${colOpt}<button data-mact="lib">${ico('move', 17)} Move to library <span class="chev">›</span></button>
      <button data-mact="series">${ico('stack', 17)} ${isS || t.multiSeries ? `Merge into ${v.s}` : `Move to ${v.s}`} <span class="chev">›</span></button>
      ${isS ? `<button data-mact="rename">${ico('sliders', 17)} Rename…</button><button data-mact="sread">${ico('check', 17)} ${t.books.every(isDone) ? 'Mark as unread' : 'Mark as read'}</button>` : t.multi ? '' : `<button data-mact="read">${ico('check', 17)} ${isDone(t) ? 'Mark as unread' : 'Mark as read'}</button>`}`)
      + (isS && !onSeriesPage() ? `<button data-mact="open">${ico('book', 17)} Open series</button>` : '') + favOpts + `
      <div class="msep"></div>
      <button class="danger" data-mact="${isS && t.empty ? 'del' : t.multi || t.multiSeries ? 'del' : 'trash'}">${ico('trash', 17)} ${isS && t.empty ? `Delete ${what}` : 'Move to trash'}</button>`;
    if (isS ? seriesTrashed(t) : !t.multi && !t.multiSeries && t.trashed) body = `<p class="mnote">In the trash. It leaves the library in a few minutes and can be restored for 30 days.</p><button data-mact="restore">${ico('refresh', 17)} Restore</button><div class="msep"></div><button class="danger" data-mact="purge">${ico('trash', 17)} Delete forever</button>`;
  } else if (view === 'purge') {
    body = `<p class="mnote">Delete <b>forever</b>? The files are removed from disk right now, with their reading progress. This can’t be undone.</p><div class="mrow"><button class="btn-sm" data-mact="main">Cancel</button><button class="btn-sm danger-solid" data-mact="confirmpurge">${ico('trash', 15)} Delete forever</button></div>`;
  } else if (view === 'col') {
    const libId = t.library, cur = isS ? t.collectionId : null;
    const cols = S.collections.filter(c => c.library === libId && c.id !== cur);
    body = back + (cur || t.multiSeries ? `<button data-tocol=""><i class="dot" style="background:var(--mute)"></i>No ${v.g} — ${esc(libName(libId))} root</button>` : '')
      + cols.map(c => `<button data-tocol="${c.id}">🗂️ ${esc(c.name)}<span class="chev">${plural((S.byCol[c.id] || []).length, 'series')}</span></button>`).join('')
      + `<div class="msep"></div><button data-mact="newcolmove">+ New ${v.g}…</button>`;
  } else if (view === 'lib') {
    const libs = t.multiSeries ? S.libraries : S.libraries.filter(l => l.id !== t.library);
    body = back + (libs.length ? libs.map(l => `<button data-tolib="${l.id}"><i class="dot" style="background:${esc(l.color)}"></i>${esc(l.name)}<span class="chev">${plural(l.series || 0, 'series')}</span></button>`).join('')
      : `<p class="mnote">This is your only library.</p><button data-mact="newlib">+ Create another library</button>`);
  } else if (view === 'series') {
    body = back + `<input class="msearch" id="mSearch" placeholder="Search series…" autocomplete="off"><div class="mlist" id="mList">${seriesChoices('')}</div>`
      + (isS || t.multiSeries ? '' : `<div class="msep"></div><button data-mact="newseries">+ New ${v.s}…</button>`);
  } else if (view === 'newseries') {
    body = back + `<p class="mnote" style="padding-bottom:6px">Create a new ${v.s} in <b>${esc(libName(t.library))}</b>:</p>
      <form id="mNewForm"><input class="msearch" id="mNewName" value="${esc(t.series)}" autocomplete="off"><button class="btn-sm pri" type="submit">Move</button></form>`;
  } else if (view === 'fav') {
    body = back + (S.favs.length ? S.favs.map(f => { const on = inFav(f, fk);
      return `<button data-favtoggle="${f.id}" class="favopt ${on ? 'on' : ''}">${ico(on ? 'heartF' : 'heart', 17)}${esc(f.name)}<span class="chev">${on ? 'added' : favItems(f).length || ''}</span></button>`; }).join('')
      : '<p class="mnote">No favourites lists yet — make the first one:</p>')
      + `<div class="msep"></div><button data-mact="newfav">+ New list…</button>`;
  } else if (view === 'del') {
    const n = isS ? t.books.length : t.multiSeries ? t.files : t.multi ? t.ids.length : 1;
    body = `<p class="mnote">${n ? 'Move' : 'Delete'} <b>${esc(isS ? t.name : t.multiSeries ? plural(t.ids.length, v.s) : t.multi ? `${plural(n, 'item')} from ${t.series}` : `${t.series} · ${t.label}`)}</b>?<br>${n ? `${n === 1 ? 'It goes' : 'They go'} to the trash: out of the library in a few minutes, restorable for 30 days.` : 'This removes the empty series folder.'}</p>
      <div class="mrow"><button class="btn-sm" data-mact="main">Cancel</button><button class="btn-sm danger-solid" data-mact="confirmdel">${ico('trash', 15)} ${n ? 'Move to trash' : 'Delete'}</button></div>`;
  }
  const m = $('#menu');
  m.innerHTML = `<div class="mhead"><b>${esc(isS ? t.name : t.label + (t.title ? ' · ' + t.title : ''))}</b><small>${esc(isS ? `${countLabel(t)} · ${libName(t.library)}` : t.series)}</small></div>${body}${err ? `<div class="merr">${esc(err)}</div>` : ''}`;
  m.classList.add('on'); m.classList.remove('busy');
  $('#menuShade').classList.add('on');
  placeMenu();
  if (view === 'series') {
    const inp = $('#mSearch');
    inp.addEventListener('input', () => { $('#mList').innerHTML = seriesChoices(inp.value); });
    if (!isPhone()) inp.focus();
  }
  if (view === 'newseries') {
    const inp = $('#mNewName'); inp.focus(); inp.select();
    $('#mNewForm').addEventListener('submit', ev => { ev.preventDefault(); if (inp.value.trim()) runMove({ newSeries: inp.value.trim(), library: t.library }, `Moved to “${inp.value.trim()}”`); });
  }
}
async function runOp(method, url, body, okMsg) {
  const m = $('#menu'); m.classList.add('busy');
  let r = null, d = {};
  try {
    r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    d = await r.json().catch(() => ({}));
  } catch {}
  if (!r || !r.ok) { m.classList.remove('busy'); return renderMenu('main', d.detail || 'Something went wrong'); }
  const sid = M.kind === 'series' ? M.id : M.kind === 'books' ? null : S.books[M.id]?.seriesId;
  const wasOnSeries = sid && location.hash.startsWith('#/series/') && location.hash.includes(sid) && M.kind === 'series';
  if (M.kind === 'books' || M.kind === 'multiseries') S.sel = null;
  closeMenu(); appToast(okMsg);
  if (wasOnSeries) location.hash = S.lib ? `#/library/${S.lib}` : '#/';
  await load();
}
async function runSeriesBatch(method, bodyFor, okMsg) {
  const m = $('#menu'); m.classList.add('busy');
  const ids = [...M.ids]; let failed = 0, err = '';
  const vb = V(S.seriesById[ids[0]]?.library);
  const stop = workStart(method === 'DELETE' ? `Deleting ${plural(ids.length, vb.s)}…` : `Moving ${plural(ids.length, vb.s)}…`);
  for (const [k, id] of ids.entries()) {
    WORK.sub = `${k + 1} / ${ids.length}`;
    const body = bodyFor ? bodyFor(id) : undefined;
    if (body === null) continue;            // nothing to do for this one (e.g. already in that library)
    const r = await fetch(method === 'DELETE' ? `/api/series/${id}` : `/api/series/${id}/move`, {
      method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }).catch(() => null);
    if (!r?.ok) { failed++; err = (await r?.json().catch(() => ({})))?.detail || err; }
  }
  stop();
  S.sel = null; closeMenu();
  appToast(failed ? `${okMsg} — ${failed} failed${err ? `: ${err}` : ''}` : okMsg);
  await load();
}
const runMove = (body, msg) => M.kind === 'multiseries'
  ? runSeriesBatch('POST', id => body.into ? (id === body.into ? null : { into: body.into }) : (S.seriesById[id]?.library === body.library ? null : { library: body.library }), msg)
  : M.kind === 'books' ? runOp('POST', '/api/books/move', { ...body, ids: M.ids }, msg)
  : runOp('POST', M.kind === 'series' ? `/api/series/${M.id}/move` : `/api/books/${M.id}/move`, body, msg);

$('#menu').addEventListener('click', e => {
  const t = menuTarget(); if (!t) return;
  const a = e.target.closest('[data-mact]')?.dataset.mact;
  if (M.kind === 'favlist') {
    if (a === 'open') { closeMenu(); location.hash = `#/fav/${t.id}`; return; }
    if (a === 'rename') return openPrompt(M.anchor, { title: 'Rename list', value: t.name, button: 'Rename',
      run: async name => { if (name !== t.name) { await jsonFetch('PATCH', `/api/favorites/${t.id}`, { name }); await refreshFavs(); appToast(`Renamed to ${name}`); } } });
    if (a === 'confirmdel') return jsonFetch('DELETE', `/api/favorites/${t.id}`).then(async () => {
      closeMenu(); appToast(`Deleted ${t.name}`); await refreshFavs(); if (location.hash === `#/fav/${t.id}`) location.hash = '#/favs'; })
      .catch(err => renderFavListMenu('main', t, err.message));
    if (a) return renderFavListMenu(a, t);
    return;
  }
  const fk = favKey(t);
  if (fk && a === 'newfav') {
    const label = M.kind === 'series' ? t.name : t.label;
    return openPrompt(M.anchor, { title: 'New favourites list', hint: `${label} goes into it.`, placeholder: 'List name', button: 'Create & add',
      run: async name => { const f = await jsonFetch('POST', '/api/favorites', { name }); await jsonFetch('POST', `/api/favorites/${f.id}/items`, { kind: fk[0], id: fk[1] });
        await refreshFavs(); appToast(`♥ Added to ${name}`); } });
  }
  if (fk && a === 'favremove') {
    const f = S.favById[S.favCur];
    return jsonFetch('DELETE', `/api/favorites/${f.id}/items/${fk[0]}/${fk[1]}`).then(async () => { closeMenu(); appToast(`Removed from ${f.name}`); await refreshFavs(); })
      .catch(err => renderMenu('main', err.message));
  }
  const ftg = e.target.closest('[data-favtoggle]');
  if (fk && ftg) {
    const f = S.favById[ftg.dataset.favtoggle], on = inFav(f, fk);
    $('#menu').classList.add('busy');
    return jsonFetch(on ? 'DELETE' : 'POST', on ? `/api/favorites/${f.id}/items/${fk[0]}/${fk[1]}` : `/api/favorites/${f.id}/items`, on ? undefined : { kind: fk[0], id: fk[1] })
      .then(async () => { await refreshFavs(); appToast(on ? `Removed from ${f.name}` : `♥ Added to ${f.name}`); renderMenu('fav'); })
      .catch(err => renderMenu('fav', err.message));
  }
  if (a === 'read') { setDone(t, !isDone(t)); closeMenu(); return route(); }
  if (a === 'sread') { const done = !t.books.every(isDone); t.books.forEach(b => setDone(b, done)); closeMenu(); renderSidebar(); return route(); }
  if (a === 'open') { closeMenu(); location.hash = `#/series/${t.id}`; return; }
  if (a === 'newlib') { closeMenu(); return openLibModal(); }
  if (a === 'details') { closeMenu(); return openDetails(t.id); }
  if (a === 'rename') {
    const isCol = M.kind === 'collection', id = M.id, anchor = M.anchor;
    return openPrompt(anchor, { title: `Rename ${isCol ? V(t.library).g : V(t.library).s}`, hint: 'Renames the folder on disk · reading progress is kept', value: t.name, button: 'Rename',
      run: async name => {
        if (name === t.name) return;
        const d = await jsonFetch('PATCH', isCol ? `/api/collections/${id}` : `/api/series/${id}`, { name });
        const nid = isCol ? d.id : d.seriesId;
        if (!isCol && seriesPrefs[id]) { seriesPrefs[nid] = seriesPrefs[id]; delete seriesPrefs[id]; local.set('cf-series', seriesPrefs); }
        const page = isCol ? `#/collection/${id}` : `#/series/${id}`;
        if (location.hash === page) history.replaceState(null, '', isCol ? `#/collection/${nid}` : `#/series/${nid}`);
        appToast(`Renamed to ${name}`); await load();
      } });
  }
  if (M.kind === 'collection') {
    if (a === 'open') { closeMenu(); location.hash = `#/collection/${t.id}`; return; }
    if (a === 'ungroup') return runOp('POST', `/api/collections/${t.id}/ungroup`, null, `Ungrouped ${t.name}`).then(() => { if (location.hash === `#/collection/${t.id}`) location.hash = `#/library/${t.library}`; });
    if (a === 'confirmdel') return runOp('DELETE', `/api/collections/${t.id}`, null, t.files ? `Moved ${t.name} to trash` : `Deleted ${t.name}`).then(() => { if (location.hash === `#/collection/${t.id}`) location.hash = `#/library/${t.library}`; });
    if (a === 'restore' || a === 'confirmpurge') return runOp('POST', a === 'restore' ? '/api/trash/restore' : '/api/trash/purge', { ids: t.inside.flatMap(x => x.books.map(b => b.id)) }, a === 'restore' ? 'Restored' : 'Deleted forever');
  }
  if (a === 'newcolmove') {
    const kind = M.kind, ids = M.ids, id = M.id, lib = t.library, anchor = M.anchor;
    return openPrompt(anchor, { title: `New ${V(lib).g}`, hint: `Created in ${libName(lib)}, then the ${pl(V(lib).s)} move into it.`, placeholder: `${cap(V(lib).g)} name`, button: 'Create & move',
      run: async name => {
        const c = await jsonFetch('POST', `/api/libraries/${lib}/collections`, { name });
        for (const sid of kind === 'multiseries' ? ids : [id]) await jsonFetch('POST', `/api/series/${sid}/move`, { collection: c.id });
        S.sel = null; appToast(`Moved to ${name}`); await load();
      } });
  }
  if (a === 'confirmdel' || a === 'trash') {
    if (M.kind === 'books') return runOp('POST', '/api/books/delete', { ids: M.ids }, `${plural(M.ids.length, 'item')} moved to trash`);
    if (M.kind === 'multiseries') return runOp('POST', '/api/series/delete', { ids: M.ids }, `${plural(M.ids.length, 'series')} moved to trash`);
    const empty = M.kind === 'series' && t.empty;
    return runOp('DELETE', M.kind === 'series' ? `/api/series/${M.id}` : `/api/books/${M.id}`, null, empty ? `Deleted ${t.name}` : `Moved to trash — click it to restore`);
  }
  if (a === 'restore' || a === 'confirmpurge') {
    const ids = M.kind === 'series' ? t.books.map(b => b.id) : [M.id];
    return runOp('POST', a === 'restore' ? '/api/trash/restore' : '/api/trash/purge', { ids }, a === 'restore' ? 'Restored' : 'Deleted forever');
  }
  if (a) return renderMenu(a);
  const tc = e.target.closest('[data-tocol]');
  if (tc) {
    const cid = tc.dataset.tocol, msg = cid ? `Moved to ${S.colById[cid]?.name}` : `Moved out of the ${V(t.library).g}`;
    if (M.kind === 'multiseries') return runSeriesBatch('POST', () => ({ collection: cid }), msg);
    return runOp('POST', `/api/series/${M.id}/move`, { collection: cid }, msg);
  }
  const tl = e.target.closest('[data-tolib]');
  if (tl) return runMove({ library: tl.dataset.tolib }, `Moved to ${libName(tl.dataset.tolib)}`);
  const ts = e.target.closest('[data-toseries]');
  if (ts) { const into = S.seriesById[ts.dataset.toseries]; const merge = M.kind === 'series' || M.kind === 'multiseries'; return runMove(merge ? { into: into.id } : { seriesId: into.id }, `${merge ? 'Merged into' : 'Moved to'} ${into.name}`); }
});
$('#menuShade').addEventListener('click', e => { if (e.isTrusted) closeMenu(); });
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || !e.isTrusted) return;
  if (M.kind) { closeMenu(); e.stopImmediatePropagation(); }
  else if ($('#serModal.open')) { $('#serModal').classList.remove('open'); e.stopImmediatePropagation(); }
  else if (S.sel && !reading()) { toggleSelect(false); e.stopImmediatePropagation(); }
}, true);
window.addEventListener('resize', () => { if (M.kind) placeMenu(); });
$('#main').addEventListener('scroll', () => { if (M.kind && !M.ev) placeMenu(); }, { passive: true });

// long-press (touch) and right-click (mouse) open the same menu
const itemKey = el => el.dataset.lib ? `library:${el.dataset.lib}` : el.dataset.favlist ? `favlist:${el.dataset.favlist}` : el.dataset.collection ? `collection:${el.dataset.collection}` : el.dataset.series ? `series:${el.dataset.series}` : `book:${el.dataset.open}`;
let lp = null, lpFired = false;
document.addEventListener('pointerdown', e => {
  lpFired = false;
  if (e.pointerType !== 'touch' || reading()) return;
  const el = e.target.closest('.card[data-series], .card[data-open], .card[data-collection], .card[data-favlist], .brow[data-open], .side [data-lib]');
  if (!el || (S.sel && !el.dataset.lib) || e.target.closest('[data-more], .mark, .hero-cover')) return;
  lp = { x: e.clientX, y: e.clientY, t: setTimeout(() => { lpFired = true; lp = null; navigator.vibrate?.(12); openMenu(itemKey(el), el); }, 480) };
});
document.addEventListener('pointermove', e => { if (lp && Math.hypot(e.clientX - lp.x, e.clientY - lp.y) > 10) { clearTimeout(lp.t); lp = null; } });
['pointerup', 'pointercancel'].forEach(t => document.addEventListener(t, () => { if (lp) { clearTimeout(lp.t); lp = null; } }));
document.addEventListener('click', e => { if (lpFired) { lpFired = false; e.preventDefault(); e.stopPropagation(); } }, true);
document.addEventListener('contextmenu', e => {
  const el = e.target.closest('.card[data-series], .card[data-open], .card[data-collection], .card[data-favlist], .brow[data-open], .side [data-lib]');
  if (!el || reading() || (S.sel && !el.dataset.lib)) return;
  e.preventDefault();
  if (M.kind && lpFired) return;               // already opened by long-press
  openMenu(itemKey(el), el, isPhone() ? null : e);
});

/* ======================= SERIES SETTINGS / NEW SERIES ======================= */
let smodal = null;
function openSeriesModal(s, newInLib = null) {
  if (!s && !newInLib) return;
  const lid = s ? s.library : newInLib;
  const cos = isCosplay(lid), novel = s?.novel;
  const pref = s ? (seriesPrefs[s.id] || {}) : {};
  smodal = { s, lid, view: s ? seriesView(s) : (cos ? 'cards' : 'list'), sort: pref.sort || 'asc', dir: pref.rtl == null ? 'lib' : pref.rtl ? 'rtl' : 'ltr', armed: false };
  const f = $('#serForm');
  f.innerHTML = `
    <h3>${s ? `${cap(V(lid).s)} settings` : `New ${V(lid).s}`}</h3>
    <div class="f"><label for="serName">Name</label><input type="text" id="serName" maxlength="150" value="${esc(s?.name || '')}" placeholder="e.g. Starfall" autocomplete="off">
      <span class="hintline">${s ? `Renames the folder on disk${s.books.length && !s.empty ? ' · reading progress is kept' : ''}.` : `Creates a folder in <code>/data/${esc(libOf(lid)?.path || '')}</code> — drop chapters into it or move them here with ⋯.`}</span></div>
    <div class="f">${cap(V(lid).ch)} layout<div class="dirpick">
      <button type="button" data-sview="cards"><b>▦ Cards</b><small>Cover grid, like the library</small></button>
      <button type="button" data-sview="list"><b>☰ List</b><small>Compact rows with progress</small></button></div></div>
    <div class="f">Order<div class="dirpick">
      <button type="button" data-ssort="asc"><b>↑ Oldest first</b><small>${cos ? 'First variant' : 'Chapter 1'} at the top</small></button>
      <button type="button" data-ssort="desc"><b>↓ Newest first</b><small>Latest ${V(lid).ch} at the top</small></button></div></div>
    ${cos || novel ? '' : `<div class="f">Reading direction<div class="dirpick three">
      <button type="button" data-sdir="lib"><b>Library default</b><small>${libType(lid) === 'manga' ? 'Right ← left' : 'Left → right'}</small></button>
      <button type="button" data-sdir="ltr"><b>Left → right</b><small>Comics, webtoons</small></button>
      <button type="button" data-sdir="rtl"><b>Right ← left</b><small>Manga</small></button></div></div>`}
    <div class="formerr" id="serErr"></div>
    <div class="formfoot">${s ? '<button type="button" class="btn-danger" id="btnDelSeries">Delete ${V(lid).s}</button>' : ''}<div class="grow"></div>
      <button type="button" class="btn-ghost" data-closeser>Cancel</button><button type="submit" class="btn-primary">${s ? 'Save' : `Create ${V(lid).s}`}</button></div>`;
  syncSerModal();
  $('#serModal').classList.add('open');
  setTimeout(() => { const i = $('#serName'); i.focus(); if (!s) i.select(); }, 60);
}
function syncSerModal() {
  $$('#serForm [data-sview]').forEach(b => b.classList.toggle('on', b.dataset.sview === smodal.view));
  $$('#serForm [data-ssort]').forEach(b => b.classList.toggle('on', b.dataset.ssort === smodal.sort));
  $$('#serForm [data-sdir]').forEach(b => b.classList.toggle('on', b.dataset.sdir === smodal.dir));
}
$('#serForm').addEventListener('click', async e => {
  const v = e.target.closest('[data-sview]'); if (v) { smodal.view = v.dataset.sview; return syncSerModal(); }
  const o = e.target.closest('[data-ssort]'); if (o) { smodal.sort = o.dataset.ssort; return syncSerModal(); }
  const d = e.target.closest('[data-sdir]'); if (d) { smodal.dir = d.dataset.sdir; return syncSerModal(); }
  if (e.target.closest('[data-closeser]')) return $('#serModal').classList.remove('open');
  const del = e.target.closest('#btnDelSeries');
  if (del) {
    const s = smodal.s;
    if (!smodal.armed) { smodal.armed = true; del.classList.add('arm'); del.textContent = s.books.length ? `Delete ${plural(s.books.length, 'file')}?` : 'Click again to delete'; return; }
    const r = await fetch(`/api/series/${s.id}`, { method: 'DELETE' }).catch(() => null);
    if (!r?.ok) { $('#serErr').textContent = (await r?.json().catch(() => ({})))?.detail || 'Couldn’t delete'; return; }
    $('#serModal').classList.remove('open'); appToast(`Deleted ${s.name}`);
    location.hash = S.lib ? `#/library/${S.lib}` : '#/'; await load();
  }
});
$('#serForm').addEventListener('submit', async e => {
  e.preventDefault();
  const name = $('#serName').value.trim();
  if (!name) { $('#serErr').textContent = `Give the ${V(smodal.lid).s} a name`; return; }
  const { s, lid } = smodal, btn = e.target.querySelector('[type=submit]');
  let sid = s?.id;
  btn.disabled = true;
  try {
    if (!s || name !== s.name) {
      const r = await fetch(s ? `/api/series/${s.id}` : `/api/libraries/${lid}/series`, {
        method: s ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { $('#serErr').textContent = d.detail || 'Something went wrong'; return; }
      if (s && d.seriesId !== s.id) { seriesPrefs[d.seriesId] = { ...seriesPrefs[s.id] }; delete seriesPrefs[s.id]; }
      sid = d.seriesId;
    }
    const patch = { view: smodal.view, sort: smodal.sort };
    if (smodal.dir === 'lib') { patch.rtl = undefined; } else patch.rtl = smodal.dir === 'rtl';
    saveSeriesPref(sid, patch);
    if (smodal.dir === 'lib') { delete seriesPrefs[sid].rtl; local.set('cf-series', seriesPrefs); }
    $('#serModal').classList.remove('open');
    appToast(s ? `${cap(V(smodal.lid).s)} updated` : `Created ${name}`);
    if (location.hash !== `#/series/${sid}`) history[s ? 'replaceState' : 'pushState'](null, '', `#/series/${sid}`);
    await load();
  } finally { btn.disabled = false; }
});
// (#serModal is an .overlay: its backdrop is handled with the others)

/* ======================= PROMPT + COLLECTION MENU ======================= */
async function jsonFetch(method, url, body) {
  const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(d.detail || `Error ${r.status}`); if ('setup' in d) e.setup = d.setup; throw e; }
  return d;
}
function openPrompt(anchor, o) {
  Object.assign(M, { kind: 'prompt', id: null, ids: null, anchor, ev: null, prompt: o });
  const m = $('#menu');
  m.innerHTML = `<div class="mhead"><b>${esc(o.title)}</b>${o.hint ? `<small>${esc(o.hint)}</small>` : ''}</div>
    <form id="mPrompt"><input class="msearch" id="mPromptIn" value="${esc(o.value || '')}" placeholder="${esc(o.placeholder || '')}" autocomplete="off"><button class="btn-sm pri" type="submit">${esc(o.button || 'OK')}</button></form><div class="merr" id="mPromptErr"></div>`;
  m.classList.add('on'); m.classList.remove('busy'); $('#menuShade').classList.add('on'); placeMenu();
  const inp = $('#mPromptIn'); inp.focus(); inp.select();
  $('#mPrompt').addEventListener('submit', async ev => {
    ev.preventDefault();
    const v = inp.value.trim(); if (!v) return;
    m.classList.add('busy');
    try { await o.run(v); closeMenu(); } catch (err) { m.classList.remove('busy'); $('#mPromptErr').textContent = err.message; }
  });
}

/* ======================= VIDEO PLAYER (pages that are videos) ======================= */
const fmtTime = t => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, sec = t % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(sec).padStart(2, '0'); };
function renderVideo(i, dir = 0) {
  const p = R.pages[i];
  stage.className = `stage mode-${R.mode} vmode`;
  stage.style.cursor = '';
  const anim = prefs.anim && dir ? ((dir > 0) !== R.rtl ? 'turn-next' : 'turn-prev') : '';
  stage.innerHTML = `<div class="spread vidwrap ${anim}" id="spread">
      <video id="vid" class="vid" src="${p.src}" data-i="${i}" playsinline preload="auto"></video>
      <button class="vbig" id="vbig" aria-label="Play / pause">${ico('play', 38)}</button></div>`;
  stage.scrollTop = 0;
  const v = $('#vid'), big = $('#vbig'), seek = $('#vseek');
  v.volume = prefs.vol ?? 1; v.muted = !!prefs.muted;
  seek.value = 0; seek.style.setProperty('--p', '0%'); $('#vcur').textContent = '0:00'; $('#vdur').textContent = '–:––';
  const sync = () => { big.classList.toggle('show', v.paused || v.ended); big.innerHTML = ico(v.ended ? 'refresh' : 'play', 38); };
  v.addEventListener('play', sync); v.addEventListener('pause', sync);
  v.addEventListener('ended', () => { sync(); wake(); if (i >= R.pages.length - 1 && R.book) saveProgress({ done: true }); });
  v.addEventListener('loadedmetadata', () => { if ($('#vid') === v) $('#vdur').textContent = fmtTime(v.duration); });
  v.addEventListener('timeupdate', () => {
    if ($('#vid') !== v) return;
    if (!seek.matches(':active')) { seek.value = v.duration ? v.currentTime / v.duration * 1000 : 0; seek.style.setProperty('--p', seek.value / 10 + '%'); }
    $('#vcur').textContent = fmtTime(v.currentTime);
  });
  v.addEventListener('volumechange', () => { prefs.vol = v.volume; prefs.muted = v.muted; local.set('cf-prefs', prefs); syncVol(); });
  v.addEventListener('error', () => toast('Your browser can’t play this video format'));
  big.addEventListener('click', e => { e.stopPropagation(); toggleVid(); });
  syncVol(); sync();
  v.play().catch(() => sync());                // autoplay may be blocked until the first tap
  setAmbient(R.pages.slice(0, i).reverse().find(x => x.thumb)?.thumb || R.pages.find(x => x.thumb)?.thumb);
}
function syncVol() {
  const v = $('#vid'); if (!v) return;
  const val = Math.round((v.muted ? 0 : v.volume) * 100);
  $('#vvolbtn').innerHTML = ico(val === 0 ? 'volx' : 'vol');
  $('#vvolr').value = val; $('#vvolv').textContent = val; $('#vvolr').style.setProperty('--p', val + '%');
}
function toggleVid() { const v = $('#vid'); if (!v) return; if (v.paused || v.ended) v.play().catch(() => {}); else v.pause(); }
function setVol(vol, muted, quiet) {
  const v = $('#vid'); if (!v) return;
  if (vol != null) v.volume = vol;
  if (muted != null) v.muted = muted; else if (vol > 0) v.muted = false;
  if (!quiet) toast(v.muted || v.volume === 0 ? 'Muted' : `Volume ${Math.round(v.volume * 100)}%`);
}
$('#vseek').addEventListener('input', e => { const v = $('#vid'), t = e.target; if (v?.duration) v.currentTime = t.value / 1000 * v.duration; t.style.setProperty('--p', t.value / 10 + '%'); });
$('#vvolr').addEventListener('input', e => setVol(e.target.value / 100, +e.target.value === 0, true));
$('#vvolbtn').addEventListener('click', () => $('#vvol').classList.toggle('open'));
document.addEventListener('pointerdown', e => { if (!e.target.closest('.vvolwrap')) $('#vvol').classList.remove('open'); });

/* ======================= ACCOUNTS ======================= */
// signed out while the app was open: ask the server which screen is right (first-run setup or sign-in).
// Never replaces an auth screen that is already showing — that would wipe what's being typed.
let authChecking = false;
if ('serviceWorker' in navigator && isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
async function authLost() {
  if (!$('#auth').hidden || authChecking) return;
  authChecking = true;
  try { const st = await (await _fetch('/api/auth/state')).json(); if (!st.user) showAuth(st.setup); }
  catch {} finally { authChecking = false; }
}
/* ---- "Starting up…": shown whenever the server can't be reached (container starting, restarting after
   update.bat, briefly offline). It checks every 2 s and carries on by itself — to sign-in or the library. */
let waitingT = null, waitingSince = 0;
function startingEl() {
  let el = document.getElementById('starting');
  if (!el) {
    el = document.createElement('div'); el.id = 'starting'; el.setAttribute('role', 'status');
    el.innerHTML = `<div class="startcard"><svg class="mascot" viewBox="0 0 200 200" aria-hidden="true">${critter(100, 128, 60, 48)}</svg>
      <h1></h1><p>This page continues by itself as soon as it’s ready — no need to refresh.</p>
      <div class="startbar"><i></i></div><small class="startt"></small></div>`;
    document.body.append(el);
  }
  return el;
}
// the server answers, but the library hasn't arrived yet (right after a start it can take a while on a
// Docker folder share): say so, instead of an empty page
let loadingT = null;
function libraryLoading(on) {
  clearTimeout(loadingT);
  document.body.classList.toggle('booting', on);       // no empty page skeleton while the library is on its way
  if (on) {
    loadingT = setTimeout(() => {
      if (waitingT) return;
      const el = startingEl(); waitingSince = Date.now();
      el.querySelector('h1').textContent = 'Loading your library…'; el.hidden = false; el.dataset.mode = 'loading';
      const tick = () => { if (el.dataset.mode !== 'loading' || el.hidden) return;
        const secs = Math.round((Date.now() - waitingSince) / 1000); el.querySelector('.startt').textContent = secs >= 3 ? `Waiting ${secs} s` : ''; loadingT = setTimeout(tick, 1000); };
      tick();
    }, 350);
  } else {
    const el = document.getElementById('starting');
    if (el && el.dataset.mode === 'loading') { el.hidden = true; el.dataset.mode = ''; }
  }
}
function serverGone(reconnect) {
  if (waitingT) return;
  libraryLoading(false);
  waitingSince = Date.now();
  const el = startingEl(); el.dataset.mode = 'waiting';
  el.querySelector('h1').textContent = reconnect ? 'Reconnecting…' : 'The reader is starting…';
  el.hidden = false; document.body.classList.add('waiting');
  const tick = async () => {
    const secs = Math.round((Date.now() - waitingSince) / 1000);
    el.querySelector('.startt').textContent = secs >= 3 ? `Waiting ${secs} s${secs > 90 ? ' — is Docker Desktop running?' : ''}` : '';
    let ok = false;
    try { ok = (await _fetch('/api/auth/state', { cache: 'no-store', signal: AbortSignal.timeout(5000) })).ok; } catch {}
    if (!ok) { waitingT = setTimeout(tick, 2000); return; }
    waitingT = null; el.hidden = true; el.dataset.mode = ''; document.body.classList.remove('waiting');
    if (await stale()) return location.reload();          // the server came back with newer app files
    boot();
  };
  waitingT = setTimeout(tick, 1200);
}
async function stale() {
  try { const st = await (await _fetch('/api/status', { cache: 'no-store' })).json(); return st.build && st.build !== document.querySelector('meta[name=cf-build]')?.content; }
  catch { return false; }
}
async function boot() {
  let st;
  try { st = await (await _fetch('/api/auth/state', { cache: 'no-store', signal: AbortSignal.timeout(6000) })).json(); }
  catch { return serverGone(false); }
  if (!st.user) return showAuth(st.setup);
  S.me = st.user; $('#auth').hidden = true; document.body.classList.remove('authing');
  renderAcct(); load();
}
function showAuth(setup) {
  if (!$('#auth').hidden && $('#auth').dataset.mode === (setup ? 'setup' : 'login')) return;
  clearTimeout(pollT); S.me = null; S.loaded = false;
  document.body.classList.add('authing');
  const a = $('#auth'); a.hidden = false; a.dataset.mode = setup ? 'setup' : 'login';
  a.innerHTML = `<form class="authcard" id="authForm" method="post" action="/" autocomplete="on">
      <svg class="mascot" viewBox="0 0 200 200" aria-hidden="true">${critter(100, 128, 60, 48)}</svg>
      <h1>${setup ? 'Welcome! Create your account' : 'Welcome back'}</h1>
      <p>${setup ? 'This first account is the <b>admin</b>: it gets its own library folder and can add accounts for others. Anything already in your data folder moves into it.' : 'Sign in to open your libraries.'}</p>
      <label class="af"><span>E-mail</span><input type="email" name="email" id="aEmail" autocomplete="username" required autofocus></label>
      <label class="af"><span>Password</span><input type="password" name="password" id="aPw" autocomplete="${setup ? 'new-password' : 'current-password'}" minlength="8" required></label>
      ${setup ? '<label class="af"><span>Repeat password</span><input type="password" id="aPw2" autocomplete="new-password" minlength="8" required></label>' : ''}
      <div class="formerr" id="authErr"></div>
      <button class="btn-primary big" type="submit">${setup ? 'Create account' : 'Sign in'}</button>
      ${setup ? '<small class="hintline">At least 8 characters — your password manager can save these.</small>' : ''}
    </form>`;
  $('#authForm').addEventListener('submit', async e => {
    e.preventDefault();
    const email = $('#aEmail').value.trim(), password = $('#aPw').value;
    if (setup && password !== $('#aPw2').value) { $('#authErr').textContent = 'The passwords don’t match'; return $('#aPw2').focus(); }
    const btn = e.target.querySelector('[type=submit]'); btn.disabled = true; $('#authErr').textContent = '';
    try {
      await jsonFetch('POST', setup ? '/api/auth/setup' : '/api/auth/login', { email, password });
      // tell the browser / password manager the sign-in succeeded so it offers to save it
      if (window.PasswordCredential) { try { await navigator.credentials.store(new PasswordCredential({ id: email, password })); } catch {} }
      a.hidden = true; a.innerHTML = ''; boot();
    } catch (err) {
      btn.disabled = false;
      if (err instanceof TypeError) { $('#authErr').textContent = ''; return serverGone(true); }   // server away: wait, then try again
      $('#authErr').textContent = err.message;
      if (err.setup != null && err.setup !== setup) { a.dataset.mode = ''; showAuth(err.setup); $('#aEmail').value = email; }
    }
  });
  setTimeout(() => $('#aEmail')?.focus(), 50);
}
function renderAcct() {
  const u = S.me; if (!u) return;
  $('#acct').innerHTML = `<button class="acctbtn" id="acctBtn" title="Account">
      <span class="av" style="--h:${tagHue(u.email)}">${esc(u.email[0].toUpperCase())}</span>
      <span class="who"><b>${esc(u.email)}</b><small>${u.admin ? 'Admin' : 'Account'}</small></span><span class="car">⋯</span></button>`;
}
$('#acct').addEventListener('click', e => {
  const b = e.target.closest('#acctBtn'); if (!b) return;
  Object.assign(M, { kind: 'acct', id: null, ids: null, anchor: b, ev: null });
  const m = $('#menu');
  m.innerHTML = `<div class="mhead"><b>${esc(S.me.email)}</b><small>${S.me.admin ? 'Admin' : 'Account'} · /data/${esc(S.me.folder)}</small></div>
    ${S.me.admin ? `<button data-acct="manage">${ico('users', 17)} Manage accounts…</button>` : ''}
    <button data-acct="pw">${ico('key', 17)} Change password…</button>
    <button data-acct="trash">${ico('trash', 17)} Trash</button>
    <div class="msep"></div><button data-acct="out" class="danger">${ico('logout', 17)} Sign out</button>`;
  m.classList.add('on'); m.classList.remove('busy'); $('#menuShade').classList.add('on'); placeMenu();
});
$('#menu').addEventListener('click', async e => {
  const a = e.target.closest('[data-acct]')?.dataset.acct; if (!a) return;
  closeMenu();
  if (a === 'out') { await _fetch('/api/auth/logout', { method: 'POST' }); location.hash = '#/'; return showAuth(false); }
  if (a === 'pw') return openPw();
  if (a === 'manage') return openAccounts();
  if (a === 'trash') return openTrash();
});

/* ======================= TRASH (account menu → Trash) ======================= */
// Two kinds of rows: books marked for the trash that are still in the library for a few minutes, and items
// already moved out (kept ~30 days, then deleted for good by the server).
async function openTrash() {
  let o = $('#trashModal');
  if (!o) {
    o = document.createElement('div'); o.id = 'trashModal'; o.className = 'overlay fixed';
    document.body.append(o);
    backdropCloses(o, () => o.classList.remove('open'));
    o.addEventListener('click', async e => {
      if (e.target.closest('[data-tclose]')) return o.classList.remove('open');
      const b = e.target.closest('[data-tact]'); if (!b) return;
      const act = b.dataset.tact, body = b.dataset.all ? (act === 'purge' ? { all: true, ids: b.dataset.ids.split(',').filter(Boolean) } : null)
        : b.dataset.tid ? { bin: [b.dataset.tid] } : { ids: [b.dataset.bid] };
      if (act === 'purge' && !b.classList.contains('armed')) {          // deleting for good takes a second click
        b.classList.add('armed'); b.textContent = b.dataset.all ? 'Really delete everything?' : 'Really delete?';
        return setTimeout(() => { if (b.isConnected) { b.classList.remove('armed'); b.textContent = b.dataset.all ? 'Empty trash' : 'Delete forever'; } }, 4000);
      }
      b.disabled = true;
      try { await jsonFetch('POST', `/api/trash/${act}`, body); appToast(act === 'restore' ? 'Restored' : 'Deleted forever'); }
      catch (err) { appToast(err.message); }
      await load(); drawTrash();
    });
  }
  o.innerHTML = '<div class="sheet libform trashsheet"><h3>Trash</h3><p class="hintline">Loading…</p></div>';
  o.classList.add('open');
  drawTrash();
}
async function drawTrash() {
  const o = $('#trashModal'); if (!o?.classList.contains('open')) return;
  let d; try { d = await api.get('/api/trash'); } catch { return; }
  const marked = Object.values(S.books).filter(isTrashed).sort((a, b) => b.trashed - a.trashed);
  const mins = Math.max(1, Math.round(d.delay / 60));
  const row = (img, title, sub, attr) => `<div class="trow">${img}<div class="tinfo"><b>${escWrap(title)}</b><small>${sub}</small></div>
      <button type="button" class="btn-sm" data-tact="restore" ${attr}>Restore</button><button type="button" class="btn-sm tdel" data-tact="purge" ${attr}>Delete forever</button></div>`;
  const name = (series, label, title) => series + (label && label !== series ? ' · ' + label : '') + (title ? ' · ' + title : '');
  const rows = marked.map(b => row(coverImg(b, 120), name(b.series, b.label, b.title), `${esc(libName(b.library))} · leaves the library within ${mins} min`, `data-bid="${b.id}"`))
    .concat(d.items.map(x => row(`<img src="/api/trash/${x.tid}/cover" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`, name(x.series, x.label, x.title),
      `${esc(x.libraryName || 'Library removed')} · deleted for good in ${plural(x.daysLeft, 'day')}`, `data-tid="${x.tid}"`)));
  o.querySelector('.sheet').innerHTML = `<h3>Trash</h3>
    <p class="hintline">Deleted items wait here for ${d.keepDays} days, then they’re removed from disk for good. Restoring brings back reading progress too.</p>
    <div class="tlist">${rows.join('') || '<div class="empty">The trash is empty.</div>'}</div>
    <div class="formfoot">${rows.length ? `<button type="button" class="btn-danger" data-tact="purge" data-all="1" data-ids="${marked.map(b => b.id).join(',')}">Empty trash</button>` : ''}<div class="grow"></div>
      <button type="button" class="btn-ghost" data-tclose>Close</button></div>`;
}
function openPw() {
  $('#pwForm').innerHTML = `<h3>Change password</h3>
    <input type="email" autocomplete="username" value="${esc(S.me.email)}" hidden readonly>
    <div class="f"><label for="pwCur">Current password</label><input type="password" id="pwCur" autocomplete="current-password" required></div>
    <div class="f"><label for="pwNew">New password</label><input type="password" id="pwNew" autocomplete="new-password" minlength="8" required></div>
    <div class="f"><label for="pwNew2">Repeat new password</label><input type="password" id="pwNew2" autocomplete="new-password" minlength="8" required></div>
    <span class="hintline">Other devices signed in to this account will be signed out.</span>
    <div class="formerr" id="pwErr"></div>
    <div class="formfoot"><div class="grow"></div><button type="button" class="btn-ghost" data-closepw>Cancel</button><button type="submit" class="btn-primary">Change password</button></div>`;
  $('#pwModal').classList.add('open'); setTimeout(() => $('#pwCur').focus(), 60);
}
$('#pwForm').addEventListener('click', e => { if (e.target.closest('[data-closepw]')) $('#pwModal').classList.remove('open'); });
$('#pwForm').addEventListener('submit', async e => {
  e.preventDefault();
  if ($('#pwNew').value !== $('#pwNew2').value) { $('#pwErr').textContent = 'The new passwords don’t match'; return; }
  try { await jsonFetch('POST', '/api/auth/password', { current: $('#pwCur').value, password: $('#pwNew').value }); }
  catch (err) { $('#pwErr').textContent = err.message; return; }
  if (window.PasswordCredential) { try { await navigator.credentials.store(new PasswordCredential({ id: S.me.email, password: $('#pwNew').value })); } catch {} }
  $('#pwModal').classList.remove('open'); appToast('Password changed');
});
async function openAccounts() {
  let list;
  try { list = (await jsonFetch('GET', '/api/accounts')).accounts; } catch (err) { return appToast(err.message); }
  $('#accBox').innerHTML = `<h3>Accounts</h3>
    <span class="hintline">Every account has its own libraries in its own folder of <code>/data</code> and can't see anyone else's.</span>
    <div class="acclist">${list.map(a => `<div class="accrow">
        <span class="av" style="--h:${tagHue(a.email)}">${esc(a.email[0].toUpperCase())}</span>
        <span class="who"><b>${esc(a.email)}${a.id === S.me.id ? ' <i>(you)</i>' : ''}</b><small>/data/${esc(a.folder)} · ${a.libraries} ${a.libraries === 1 ? 'library' : 'libraries'} · ${plural(a.books, 'book')}</small></span>
        ${a.admin ? '<span class="badge-admin">ADMIN</span>' : `<button class="btn-sm" data-mkadmin="${a.id}" title="Hand the admin role to this account">Make admin</button>
          <button class="btn-sm danger" data-delacc="${a.id}" title="Delete account">${ico('trash', 15)}</button>`}
      </div>`).join('')}</div>
    <form class="addacc" id="addAcc" autocomplete="off">
      <div class="label">Add an account</div>
      <div class="f2"><input type="email" id="naEmail" placeholder="E-mail" autocomplete="off" required>
        <div class="pwgen"><input type="text" id="naPw" placeholder="Password (8+ characters)" autocomplete="new-password" minlength="8" required><button type="button" class="btn-sm" id="naGen" title="Generate a password">🎲</button></div></div>
      <div class="formerr" id="accErr"></div>
      <div class="formfoot"><div class="grow"></div><button type="button" class="btn-ghost" data-closeacc>Close</button><button type="submit" class="btn-primary">Add account</button></div>
    </form>`;
  $('#accModal').classList.add('open');
}
$('#accBox').addEventListener('click', async e => {
  if (e.target.closest('[data-closeacc]')) return $('#accModal').classList.remove('open');
  if (e.target.closest('#naGen')) {
    const c = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789', r = crypto.getRandomValues(new Uint32Array(16));
    $('#naPw').value = [...r].map(x => c[x % c.length]).join(''); $('#naPw').select(); return;
  }
  const mk = e.target.closest('[data-mkadmin]');
  if (mk) {
    const who = mk.closest('.accrow').querySelector('b').textContent;
    if (!confirm(`Hand the admin role to ${who}?\n\nYou'll keep your account and libraries, but only ${who} will be able to manage accounts.`)) return;
    try { await jsonFetch('POST', `/api/accounts/${mk.dataset.mkadmin}/admin`); } catch (err) { return ($('#accErr').textContent = err.message); }
    S.me.admin = false; renderAcct(); $('#accModal').classList.remove('open'); return appToast(`${who} is the admin now`);
  }
  const del = e.target.closest('[data-delacc]');
  if (del) {
    const row = del.closest('.accrow'), who = row.querySelector('b').textContent;
    if (row.querySelector('.delconf')) return;
    row.insertAdjacentHTML('afterend', `<div class="delconf"><label><input type="checkbox" id="delFiles"> Also delete this account's files</label>
      <span class="grow"></span><button class="btn-sm" data-nodel>Keep</button><button class="btn-sm danger" data-yesdel="${del.dataset.delacc}">Delete ${esc(who)}</button></div>`);
    return;
  }
  if (e.target.closest('[data-nodel]')) return e.target.closest('.delconf').remove();
  const yes = e.target.closest('[data-yesdel]');
  if (yes) {
    try { await jsonFetch('DELETE', `/api/accounts/${yes.dataset.yesdel}?files=${$('#delFiles').checked}`); } catch (err) { return ($('#accErr').textContent = err.message); }
    appToast('Account deleted'); return openAccounts();
  }
});
$('#accBox').addEventListener('submit', async e => {
  e.preventDefault();
  const email = $('#naEmail').value.trim(), pw = $('#naPw').value;
  try { await jsonFetch('POST', '/api/accounts', { email, password: pw }); } catch (err) { return ($('#accErr').textContent = err.message); }
  try { await navigator.clipboard.writeText(`${email}\n${pw}`); appToast('Account added — e-mail and password copied'); } catch { appToast('Account added'); }
  openAccounts();
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || !e.isTrusted) return;
  for (const id of ['#pwModal', '#accModal']) if ($(id).classList.contains('open')) { e.stopImmediatePropagation(); $(id).classList.remove('open'); }
}, true);

boot();
