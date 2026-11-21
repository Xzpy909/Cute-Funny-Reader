'use strict';
/* Cute&Funny Reader — frontend, part 4 of 11: the series / set page and routing.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

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
        ${s.author || s.publisher ? `<div class="hero-meta">${[s.author && V(s.library).by(esc(s.author)), s.publisher && V(s.library).from(esc(s.publisher))].filter(Boolean).join(' · ')}</div>` : ''}
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
  const l = S.lib && S.libById[S.lib], b = $('#btnScope');
  const label = `Search in: ${l ? l.name : 'everything'}`;
  b.title = label; b.setAttribute('aria-label', label);
  b.style.setProperty('--c', l ? l.color : 'transparent');
  b.classList.toggle('lib', !!l);
  $('#scopeName').textContent = l ? (l.name.trim()[0] || '•').toUpperCase() : '';   // the library's initial on its colour
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
  S.inStorage = false; $('#viewStorage').classList.remove('on');
  S.inTrash = false; $('#viewTrash').classList.remove('on');
  if (view === 'storage') { renderStorage(); renderSidebar(); return; }
  if (view === 'trash') { renderTrash(); renderSidebar(); return; }
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

/* ---------- clicks handled here (the order is in CLICKS, js/06-events.js) ---------- */
function clickLibBack(lbk) { location.hash = `#/library/${lbk.dataset.libback}`; }
function clickColBack(cbk) { location.hash = `#/collection/${cbk.dataset.colback}`; }
function clickView(vw) { saveSeriesPref(S.curSeries, { view: vw.dataset.view }); return renderSeries(S.curSeries); }
function clickSortFlip() { const s = S.seriesById[S.curSeries]; saveSeriesPref(s.id, { sort: seriesSort(s) === 'desc' ? 'asc' : 'desc' }); return renderSeries(s.id); }
function clickSelectBook(so, e) { e.preventDefault(); const id = so.dataset.open; S.sel.has(id) ? S.sel.delete(id) : S.sel.add(id); so.classList.toggle('sel', S.sel.has(id)); return renderSelbar(); }
function clickMark(mark) { const b = S.books[mark.dataset.mark]; setDone(b, !isDone(b)); renderSeries(b.seriesId); renderSidebar(); }
function clickMarkAll(all) { const s = S.seriesById[all.dataset.markall]; const done = seriesInfo(s).unread > 0; s.books.forEach(b => setDone(b, done)); renderSeries(s.id); renderSidebar(); }
