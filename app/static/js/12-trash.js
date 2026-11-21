/* ======================= TRASH (its own page: #/trash) =======================
   Everything deleted, as one shelf: books still waiting to be moved (marked) and books already in the
   account's .trash folder (bin). Restore or delete forever, one by one or a selection; Empty trash. */
const TR = { items: [], sel: new Set(), group: 'library', data: null };

function clickTrashNav() { location.hash = '#/trash'; }

async function renderTrash() {
  ['#viewHome', '#viewSeries', '#viewFavs', '#viewStorage'].forEach(s => $(s)?.classList.remove('on'));
  const v = $('#viewTrash'); v.classList.add('on'); S.inTrash = true;
  if (!v.dataset.ready) {
    v.dataset.ready = 1;
    v.innerHTML = '<div class="shelf-h"><div><h2>🗑 Trash</h2><p class="sub">Loading…</p></div></div>';
    v.addEventListener('click', trashClick); v.addEventListener('change', trashChange);
  }
  let d;
  try { d = await api.get('/api/trash'); } catch { v.querySelector('.sub').textContent = 'Couldn’t open the trash.'; return; }
  if (!S.inTrash) return;
  TR.data = d; TR.items = d.items;
  const have = new Set(d.items.map(x => x.key)); TR.sel = new Set([...TR.sel].filter(k => have.has(k)));
  drawTrash();
}

const trashKeepText = k => k ? `kept ${plural(k, 'day')}, then deleted for good` : 'kept until you empty it';
const trashWhere = x => [x.libraryName || 'a library that’s gone', x.collection, x.series].filter(Boolean).join(' / ');
const trashDay = t => { const d = new Date(t * 1000), n = new Date(); const days = Math.floor((new Date(n.toDateString()) - new Date(d.toDateString())) / 864e5);
  return days === 0 ? 'Today' : days === 1 ? 'Yesterday' : d.toLocaleDateString(undefined, { weekday: days < 7 ? 'long' : undefined, day: 'numeric', month: 'long', year: d.getFullYear() === n.getFullYear() ? undefined : 'numeric' }); };

function trashCard(x, k) {
  const b = x.kind === 'marked' ? S.books[x.id] : null;
  const cover = b ? coverImg(b, 320) : `<img src="/api/trash/${encodeURIComponent(x.tid)}/cover" alt="" loading="lazy" draggable="false" onerror="this.dataset.failed=1">`;
  const left = x.daysLeft == null ? '' : x.daysLeft <= 0 ? 'goes today' : `${plural(x.daysLeft, 'day')} left`;
  return `<div class="card tcard ${TR.sel.has(x.key) ? 'sel' : ''}" role="button" tabindex="0" data-tkey="${esc(x.key)}" style="--d:${Math.min(k, 20) * 30}ms" aria-pressed="${TR.sel.has(x.key)}">
    <div class="cover">${cover}${left ? `<span class="badge tleft ${x.daysLeft <= 1 ? 'soon' : ''}">${left}</span>` : ''}<span class="check">✓</span></div>
    <div class="ct" title="${esc(x.title || x.label)}">${esc(x.label || x.title)}</div>
    <div class="cm" title="Was in: ${esc(trashWhere(x))}">Was in: ${esc(trashWhere(x))}</div>
    <div class="cm">${fmtBytes(x.size || 0)} · deleted ${ago(x.deleted * 1000)}</div>
    <div class="tbtns"><button type="button" class="btn-sm" data-trestore="${esc(x.key)}">Restore</button>
      <button type="button" class="btn-sm" data-tpurge="${esc(x.key)}">Delete forever</button></div>
  </div>`;
}

function drawTrash() {
  const v = $('#viewTrash'), d = TR.data, items = TR.items;
  const keep = d.canChange
    ? `<label class="tkeep">Keep for <select id="trKeep">${d.keepChoices.map(c => `<option value="${c}" ${c === d.keepDays ? 'selected' : ''}>${c ? plural(c, 'day') : 'until emptied'}</option>`).join('')}</select></label>`
    : '';
  const groups = new Map();
  for (const x of items) {
    const g = TR.group === 'day' ? trashDay(x.deleted) : (x.libraryName || 'Library that’s gone');
    (groups.get(g) || groups.set(g, []).get(g)).push(x);
  }
  let k = 0;
  const n = TR.sel.size, selBytes = items.filter(x => TR.sel.has(x.key)).reduce((s, x) => s + (x.size || 0), 0);
  v.innerHTML = `<div class="shelf-h"><div><h2>🗑 Trash</h2>
      <p class="sub">${items.length ? `${plural(items.length, 'item')} · ${fmtBytes(d.bytes)} · ${trashKeepText(d.keepDays)}` : `Empty. Deleted things wait here — ${trashKeepText(d.keepDays)}.`}</p></div>
    <div class="shelf-actions">${keep}${items.length ? `
      <div class="seg" role="group" aria-label="Group by"><button type="button" data-tgroup="library" class="${TR.group === 'library' ? 'on' : ''}">By library</button><button type="button" data-tgroup="day" class="${TR.group === 'day' ? 'on' : ''}">By day</button></div>
      <button type="button" class="btn-sm" data-tselall>${n === items.length ? 'Clear selection' : 'Select all'}</button>
      <button type="button" class="btn-sm danger-soft" data-tempty>${ico('trash', 15)} Empty trash</button>` : ''}</div></div>
    ${n ? `<div class="tselbar glass"><b>${plural(n, 'item')} selected</b><small>${fmtBytes(selBytes)}</small>
      <button type="button" class="btn-sm pri" data-tselrestore>Restore</button>
      <button type="button" class="btn-sm" data-tselpurge>Delete forever</button>
      <button type="button" class="btn-sm" data-tselclear>Clear</button></div>` : ''}
    ${[...groups].map(([g, list]) => `<div class="shelf-h slim"><div><h2>${esc(g)}</h2><p class="sub">${plural(list.length, 'item')} · ${fmtBytes(list.reduce((s, x) => s + (x.size || 0), 0))}</p></div></div>
      <div class="grid tgrid">${list.map(x => trashCard(x, k++)).join('')}</div>`).join('')}`;
}

// split keys into what the server wants: marked book ids and bin tids
function trashBody(keys) {
  const ids = [], bin = [];
  for (const key of keys) (key.startsWith('b:') ? ids.push(key.slice(2)) : bin.push(key.slice(2)));
  return { ids, bin };
}

async function trashRestore(keys, into = null) {
  try {
    const r = await jsonFetch('POST', '/api/trash/restore', { ...trashBody(keys), ...(into ? { into } : {}) });
    appToast(`${plural(r.restored ?? keys.length, 'item')} restored`);
  } catch (err) {
    if (err.data?.needLibrary) {                    // the rest came back; these need a library to go to
      if (err.data.restored) appToast(`${plural(err.data.restored, 'item')} restored`);
      await load(); if (S.inTrash) await renderTrash();
      return trashPickLibrary(keys, err.data);
    }
    appToast(err.message);
  }
  keys.forEach(k => TR.sel.delete(k)); await load(); if (S.inTrash) renderTrash();
}

// the library they came from is gone: choose where they go
function trashPickLibrary(keys, info) {
  const v = $('#viewTrash'), libs = S.libraries;
  if (!libs.length) return appToast('There’s no library to restore into — add one first');
  v.querySelector('.tpick')?.remove();
  v.insertAdjacentHTML('afterbegin', `<div class="tpick glass"><b>${esc(info.detail || 'Their library is gone')}</b>
    <select id="trInto">${libs.map(l => `<option value="${l.id}">${esc(l.name)}</option>`).join('')}</select>
    <button type="button" class="btn-sm pri" data-tinto>Restore here</button><button type="button" class="btn-sm" data-tintocancel>Cancel</button></div>`);
  const left = new Set(TR.items.map(x => x.key));   // what's still here (the others went back already)
  TR.pending = keys.filter(k => left.has(k));
}

async function trashPurge(keys, all = false) {
  try {
    const r = await jsonFetch('POST', '/api/trash/purge', all ? { all: true } : trashBody(keys));
    appToast(all ? `Trash emptied — ${fmtBytes(TR.data.bytes)} freed` : `${plural(r.deleted ?? keys.length, 'item')} deleted forever`);
  } catch (err) { appToast(err.message); }
  TR.sel.clear(); await load(); if (S.inTrash) renderTrash();
}

// a second click before anything is gone for good
function armed(btn, text, then) {
  if (btn.classList.contains('armed')) { btn.disabled = true; return then(); }
  const was = btn.innerHTML; btn.classList.add('armed', 'danger'); btn.textContent = text;
  setTimeout(() => { if (btn.isConnected && !btn.disabled) { btn.classList.remove('armed', 'danger'); btn.innerHTML = was; } }, 4000);
}

function trashClick(e) {
  const t = e.target; e.stopPropagation();
  const r = t.closest('[data-trestore]'); if (r) return trashRestore([r.dataset.trestore]);
  const p = t.closest('[data-tpurge]'); if (p) return armed(p, 'Gone for good — sure?', () => trashPurge([p.dataset.tpurge]));
  const g = t.closest('[data-tgroup]'); if (g) { TR.group = g.dataset.tgroup; return drawTrash(); }
  if (t.closest('[data-tselall]')) { TR.sel = TR.sel.size === TR.items.length ? new Set() : new Set(TR.items.map(x => x.key)); return drawTrash(); }
  if (t.closest('[data-tselclear]')) { TR.sel.clear(); return drawTrash(); }
  if (t.closest('[data-tselrestore]')) return trashRestore([...TR.sel]);
  const sp = t.closest('[data-tselpurge]'); if (sp) return armed(sp, `Delete ${plural(TR.sel.size, 'item')} forever?`, () => trashPurge([...TR.sel]));
  const em = t.closest('[data-tempty]'); if (em) return armed(em, `Free ${fmtBytes(TR.data.bytes)} — can’t be undone`, () => trashPurge([], true));
  if (t.closest('[data-tinto]')) { const into = $('#trInto').value; $('.tpick')?.remove(); return trashRestore(TR.pending || [], into); }
  if (t.closest('[data-tintocancel]')) return $('.tpick')?.remove();
  const c = t.closest('[data-tkey]');
  if (c && !t.closest('button, select')) { const k = c.dataset.tkey; TR.sel.has(k) ? TR.sel.delete(k) : TR.sel.add(k); drawTrash(); }
}

async function trashChange(e) {
  if (e.target.id !== 'trKeep') return;
  try { await jsonFetch('PUT', '/api/trash/settings', { keepDays: +e.target.value }); appToast('Saved'); } catch (err) { appToast(err.message); }
  renderTrash();
}
