'use strict';
/* Cute&Funny Reader — frontend, part 3 of 11: Home and library pages: rows, grids, cards.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

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
        <p class="blurb">${esc((s.summary || `${countLabel(s)} in your ${libName(s.library)} library${s.author ? ' · ' + V(s.library).by(s.author) : ''}.`).slice(0, 260))}</p>
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
  // adding files: the top bar's Add · new collection & library settings: right-click the library
  $('#libActions').innerHTML = (S.series.length ? `<button class="btn-sm ${selOn ? 'pri' : ''}" data-select>${selOn ? 'Done selecting' : '☑ Select files'}</button>` : '')
    + (col ? `<button class="btn-sm" data-more="collection:${col.id}">⋯ Collection</button>` : '');

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
    hits.length ? `${plural(hits.length, 'single ' + Vh.ch)} by tag` : ''].filter(Boolean).join(' · ');
  const weekAgo = Date.now() / 1000 - 7 * 86400;
  // front cover live; the ones behind it come as one picture drawn by the server (much cheaper to scroll).
  // Generated placeholder art can't be drawn there — such stacks stay as before.
  const stackCovers = covers => {
    if (!covers.length) return '<div class="stk s0 emptycol">🗂️</div>';
    const back = covers.slice(1).map(coverBook);
    if (back.length && back.every(b => b.hasCover && b.format !== 'video'))
      return `<div class="stk s0">${seriesCover(covers[0], 200)}</div><img class="stkback" src="/api/stack?books=${back.map(b => b.id).join(',')}&v=${back.map(b => `${b.mtime}.${b.coverPage ?? ''}`).join('-')}" alt="" loading="lazy" draggable="false">`;
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
    const bubble = unread && !one ? `<span class="ubub" title="${plural(unread, V(s.library).ch)} not started yet"><i></i><b>${unread > 99 ? '99+' : unread}</b> new</span>` : '';
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

/* ---------- clicks handled here (the order is in CLICKS, js/06-events.js) ---------- */
function clickTagPop(tpb, e) { e.preventDefault(); e.stopPropagation(); return openTagPop(tpb); }
function clickTag(tg, e) {
  closeTagPop(); e.preventDefault(); e.stopPropagation(); S.q = tg.dataset.tag; $('#q').value = S.q; S.filter = 'all';
  const h = S.lib ? `#/library/${S.lib}` : '#/'; if (location.hash === h) { renderHome(); renderSidebar(); } else location.hash = h;
}
function clickCollection(cc) {
  if (!S.sel) { location.hash = `#/collection/${cc.dataset.collection}`; return; }
  return appToast(`${cap(pl(Vhome().g))} can’t be selected — open one to select its ${pl(Vhome().s)}`);
}
function clickSelAll() {
  const pool = selPool();
  S.sel = pool.every(id => S.sel.has(id)) ? new Set() : new Set(pool);
  return S.selMode === 'series' ? (renderHome(), renderSelbar()) : renderSeries(S.curSeries);
}
function clickSelAct(sa) {
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
function clickSelectSeries(sc, e) { e.preventDefault(); const id = sc.dataset.series; S.sel.has(id) ? S.sel.delete(id) : S.sel.add(id); sc.classList.toggle('sel', S.sel.has(id)); sc._h = null; return renderSelbar(); }
function clickOpen(o) { return openBook(o.dataset.open, o.dataset.start != null ? +o.dataset.start : null); }
function clickSeries(se) { if (se.dataset.single) return openBook(se.dataset.single); location.hash = `#/series/${se.dataset.series}`; }
