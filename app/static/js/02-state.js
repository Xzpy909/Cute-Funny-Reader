'use strict';
/* Cute&Funny Reader — frontend, part 2 of 11: app state, loading the library, the sidebar.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

/* ======================= STATE ======================= */
const S = {
  libraries: [], books: {}, series: [], seriesById: {}, progress: {}, status: null,
  lib: null, filter: 'all', q: '', sort: local.get('cf-sort', 'recent'), loaded: false,
};
// per-series view settings (rtl, view, sort, mode, fit): kept per account on the server so they follow you to
// other devices; this is the working copy (also used offline) — synced at start and when the tab comes back
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
const prefQ = new Set(); let prefT;
function pushSeriesPrefs() {                          // changes go up shortly after they're made, a few at once
  clearTimeout(prefT);
  prefT = setTimeout(() => {
    if (!S.me || !prefQ.size) return;
    const body = Object.fromEntries([...prefQ].map(id => [id, seriesPrefs[id] || null])); prefQ.clear();
    jsonFetch('PUT', '/api/prefs/series', body).catch(() => Object.keys(body).forEach(id => prefQ.add(id)));   // retried with the next change
  }, 400);
}
// patch: { key: value } — undefined / null forgets that key (back to the default)
const saveSeriesPref = (sid, patch) => {
  const p = { ...seriesPrefs[sid], ...patch };
  for (const k of Object.keys(p)) if (p[k] == null) delete p[k];
  if (Object.keys(p).length) seriesPrefs[sid] = p; else delete seriesPrefs[sid];
  local.set('cf-series', seriesPrefs); prefQ.add(sid); pushSeriesPrefs();
};
// a series got a new id (renamed / merged): its settings go with it
const moveSeriesPref = (from, to) => {
  if (!seriesPrefs[from] || from === to) return;
  seriesPrefs[to] = seriesPrefs[from]; delete seriesPrefs[from];
  local.set('cf-series', seriesPrefs); prefQ.add(from); prefQ.add(to); pushSeriesPrefs();
};
let prefSynced = 0;
async function syncSeriesPrefs() {
  if (!S.me || prefQ.size) return;                    // (changes still on their way up: next time)
  let srv; try { srv = await api.get('/api/prefs/series'); } catch { return; }   // offline: the working copy stays
  // settings this browser kept from before they lived on the server go up once — to the first account that signs in
  // here; after that the working copy is always some account's server copy, never something to hand to another
  if (!local.get('cf-series-synced', false)) {
    const up = Object.fromEntries(Object.entries(seriesPrefs).filter(([id]) => !srv[id]));
    if (Object.keys(up).length) { try { srv = await jsonFetch('PUT', '/api/prefs/series', up); } catch { return; } }
    local.set('cf-series-synced', true);
  }
  prefSynced = Date.now();
  const before = JSON.stringify(seriesPrefs);
  for (const k of Object.keys(seriesPrefs)) delete seriesPrefs[k];
  Object.assign(seriesPrefs, srv); local.set('cf-series', seriesPrefs);
  if (S.loaded && JSON.stringify(seriesPrefs) !== before && !location.hash.startsWith('#/read')) route();   // (never under an open book)
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() - prefSynced > 30000) syncSeriesPrefs(); });

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
  for (const b of Object.values(S.books)) if (!isTrashed(b)) (by[b.library] ||= []).push(b);
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
    if (isTrashed(b)) continue;                     // in the trash: only on the Trash page (until it's restored)
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
    if (first) liveStart();                       // background jobs and "library changed", live (js/13-live.js)
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
  const tr = S.status?.trash; $('#nTrash').textContent = tr?.count || '';
  $('#mainNav [data-nav="trash"]').title = tr?.count ? `${plural(tr.count, 'item')} · ${fmtBytes(tr.bytes)}` : 'The trash is empty';
  $('#libNav').innerHTML = S.libraries.map(l =>
    `<button data-lib="${l.id}" class="${S.lib === l.id ? 'on' : ''}"><span class="dot" style="background:${esc(l.color)}"></span>${esc(l.name)} <span class="count">${l.series || ''}</span></button>`).join('');
  $$('#mainNav button').forEach(b => b.classList.toggle('on', S.inTrash ? b.dataset.nav === 'trash' : S.inStorage ? b.dataset.nav === 'storage' : S.inFavs ? b.dataset.nav === 'favs' : !S.lib && b.dataset.nav === (S.filter === 'all' ? 'home' : S.filter)));
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

/* ---------- clicks handled here (the order is in CLICKS, js/06-events.js) ---------- */
function clickHome() { location.hash = S.lib ? `#/library/${S.lib}` : '#/'; }
function clickFilter(f) { S.filter = f.dataset.filter; renderHome(); renderSidebar(); }
function clickNav(nav) { S.lib = null; S.filter = nav.dataset.nav === 'home' ? 'all' : nav.dataset.nav; if (location.hash.length > 2) location.hash = '#/'; else { renderHome(); renderSidebar(); } }
function clickLib(lb) { S.filter = 'all'; location.hash = location.hash === `#/library/${lb.dataset.lib}` ? '#/' : `#/library/${lb.dataset.lib}`; }
