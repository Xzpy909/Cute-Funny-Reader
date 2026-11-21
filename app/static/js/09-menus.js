'use strict';
/* Cute&Funny Reader — frontend, part 9 of 11: favourites, the ⋯ menu, series settings, prompts.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

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
// a short message at the bottom; `action` ({ label, run }) adds one button — e.g. Undo — and keeps it up longer
function appToast(msg, action = null) {
  const t = $('#apptoast'); t.textContent = msg; t.classList.toggle('act', !!action);
  if (action) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = action.label;
    b.onclick = () => { t.classList.remove('show'); action.run(); };
    t.append(' · ', b);
  }
  t.classList.add('show'); clearTimeout(appToastT); appToastT = setTimeout(() => t.classList.remove('show'), action ? 7000 : 2600);
}
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
function newCollection(anchor, lid) {
  return openPrompt(anchor, { title: `New ${V(lid).g}`, hint: `A folder that groups ${pl(V(lid).s)} inside ${libName(lid)}.`, placeholder: 'e.g. Isekai, Favourites, 2026 releases', button: 'Create',
    run: async name => { const r = await jsonFetch('POST', `/api/libraries/${lid}/collections`, { name }); history.pushState(null, '', `#/collection/${r.id}`); appToast(`Created ${name}`); await load(); } });
}
// a library in the sidebar: right-click / long-press
function renderLibraryMenu() {
  const l = S.libById[M.id]; if (!l) return closeMenu();
  const m = $('#menu');
  m.innerHTML = `<div class="mhead"><b>${esc(l.name)}</b><small>${esc(plural(l.series || 0, V(l.id).s))} · ${esc(plural(l.books || 0, 'file'))}</small></div>
    <button data-libmenu="newcol">${ico('plus', 17)} New ${esc(V(l.id).g)}…</button>
    ${l.books ? `<button data-libmenu="optimize">${ico('spark', 17)} Optimize library…</button>` : ''}
    <button data-libmenu="settings">${ico('sliders', 17)} Library settings</button>`;
  m.classList.add('on'); $('#menuShade').classList.add('on'); placeMenu();
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-libmenu]'); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const l = S.libById[M.id], anchor = M.anchor;
  if (l && b.dataset.libmenu === 'newcol') return newCollection(anchor, l.id);
  closeMenu();
  if (l && b.dataset.libmenu === 'optimize') return optimizeLibrary(l.id);
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
      ${optItems(t)}
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
      + (isS && !onSeriesPage() ? `<button data-mact="open">${ico('book', 17)} Open ${v.s}</button>` : '') + favOpts + optItems(t) + `
      <div class="msep"></div>
      <button class="danger" data-mact="${isS && t.empty ? 'del' : t.multi || t.multiSeries ? 'del' : 'trash'}">${ico('trash', 17)} ${isS && t.empty ? `Delete ${what}` : 'Move to trash'}</button>`;
    if (isS ? seriesTrashed(t) : !t.multi && !t.multiSeries && t.trashed) body = `<p class="mnote">In the trash. It leaves the library in a few minutes and can be restored for 30 days.</p><button data-mact="restore">${ico('refresh', 17)} Restore</button><div class="msep"></div><button class="danger" data-mact="purge">${ico('trash', 17)} Delete forever</button>`;
  } else if (view === 'purge') {
    body = `<p class="mnote">Delete <b>forever</b>? The files are removed from disk right now, with their reading progress. This can’t be undone.</p><div class="mrow"><button class="btn-sm" data-mact="main">Cancel</button><button class="btn-sm danger-solid" data-mact="confirmpurge">${ico('trash', 15)} Delete forever</button></div>`;
  } else if (view === 'col') {
    const libId = t.library, cur = isS ? t.collectionId : null;
    const cols = S.collections.filter(c => c.library === libId && c.id !== cur);
    body = back + (cur || t.multiSeries ? `<button data-tocol=""><i class="dot" style="background:var(--mute)"></i>No ${v.g} — ${esc(libName(libId))} root</button>` : '')
      + cols.map(c => `<button data-tocol="${c.id}">🗂️ ${esc(c.name)}<span class="chev">${plural((S.byCol[c.id] || []).length, v.s)}</span></button>`).join('')
      + `<div class="msep"></div><button data-mact="newcolmove">+ New ${v.g}…</button>`;
  } else if (view === 'lib') {
    const libs = t.multiSeries ? S.libraries : S.libraries.filter(l => l.id !== t.library);
    body = back + (libs.length ? libs.map(l => `<button data-tolib="${l.id}"><i class="dot" style="background:${esc(l.color)}"></i>${esc(l.name)}<span class="chev">${plural(l.series || 0, V(l.id).s)}</span></button>`).join('')
      : `<p class="mnote">This is your only library.</p><button data-mact="newlib">+ Create another library</button>`);
  } else if (view === 'series') {
    body = back + `<input class="msearch" id="mSearch" placeholder="Search ${pl(v.s)}…" autocomplete="off"><div class="mlist" id="mList">${seriesChoices('')}</div>`
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
async function runOp(method, url, body, okMsg, undo = null) {
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
  closeMenu(); appToast(okMsg, undo);
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
  if (a === 'optimize') { const o = optSel(t); closeMenu(); return openOptimize(o); }
  if (a === 'unoptimize') return runOp('POST', '/api/optimize/undo', optSel(t).sel, 'Originals restored');
  if (a === 'rename') {
    const isCol = M.kind === 'collection', id = M.id, anchor = M.anchor;
    return openPrompt(anchor, { title: `Rename ${isCol ? V(t.library).g : V(t.library).s}`, hint: 'Renames the folder on disk · reading progress is kept', value: t.name, button: 'Rename',
      run: async name => {
        if (name === t.name) return;
        const d = await jsonFetch('PATCH', isCol ? `/api/collections/${id}` : `/api/series/${id}`, { name });
        const nid = isCol ? d.id : d.seriesId;
        if (!isCol) moveSeriesPref(id, nid);
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
    // what went to the trash can come straight back: Undo in the toast
    const undoOf = ids => ({ label: 'Undo', run: async () => {
      try { await jsonFetch('POST', '/api/trash/restore', { ids }); appToast('Restored'); } catch (err) { appToast(err.message); }
      load(); } });
    if (M.kind === 'books') return runOp('POST', '/api/books/delete', { ids: M.ids }, `${plural(M.ids.length, 'item')} moved to Trash`, undoOf(M.ids));
    if (M.kind === 'multiseries') return runOp('POST', '/api/series/delete', { ids: M.ids }, `${plural(M.ids.length, V(S.seriesById[M.ids[0]]?.library).s)} moved to Trash`,
      undoOf(M.ids.flatMap(id => (S.seriesById[id]?.books || []).map(b => b.id))));
    const empty = M.kind === 'series' && t.empty;
    const ids = M.kind === 'series' ? t.books.map(b => b.id) : [M.id];
    return runOp('DELETE', M.kind === 'series' ? `/api/series/${M.id}` : `/api/books/${M.id}`, null, empty ? `Deleted ${t.name}` : 'Moved to Trash', empty ? null : undoOf(ids));
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
      if (s && d.seriesId !== s.id) moveSeriesPref(s.id, d.seriesId);
      sid = d.seriesId;
    }
    const patch = { view: smodal.view, sort: smodal.sort };
    if (smodal.dir === 'lib') { patch.rtl = undefined; } else patch.rtl = smodal.dir === 'rtl';
    saveSeriesPref(sid, patch);                       // (rtl: undefined = back to the library's direction)
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
  if (!r.ok) { const e = new Error(d.detail || `Error ${r.status}`); if ('setup' in d) e.setup = d.setup; e.data = d; throw e; }
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

/* ---------- clicks handled here (the order is in CLICKS, js/06-events.js) ---------- */
function clickMore(mo, e) { e.preventDefault(); e.stopPropagation(); return openMenu(mo.dataset.more, mo); }
function clickNewCol(nc) { return newCollection(nc, nc.dataset.newcol); }
function clickSerSettings(ss) { return openSeriesModal(S.seriesById[ss.dataset.sersettings]); }
function clickNewSeries(ns) { return openSeriesModal(null, ns.dataset.newseries); }
function clickFavsNav() { location.hash = '#/favs'; }
function clickFavList(fl) { location.hash = `#/fav/${fl.dataset.favlist}`; }
function clickFavBack() { location.hash = '#/favs'; }
function clickNewFav(nf) {
  return openPrompt(nf, { title: 'New favourites list', hint: 'Add series, sets or variants to it from their ⋯ menu.', placeholder: 'List name', button: 'Create',
    run: async name => { const f = await jsonFetch('POST', '/api/favorites', { name }); await refreshFavs(); location.hash = `#/fav/${f.id}`; } });
}
