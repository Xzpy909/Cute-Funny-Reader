'use strict';
/* Cute&Funny Reader — frontend, part 7 of 11: first run, library settings, Edit details.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

/* ======================= WELCOME / LIBRARIES ======================= */
function renderWelcome() {
  $('#welcome').innerHTML = `<div class="welcome"><div class="welcome-card">
    <svg class="mascot" viewBox="0 0 200 200" aria-hidden="true">${critter(100, 128, 60, 48)}</svg>
    <h1>Add your <em>first</em> library</h1>
    <p>A library is a shelf for your comics, manga, light novels or Cosplay photo sets. Create one, then drag <code>.cbz</code> or <code>.epub</code> files — or whole folders — straight onto this window.</p>
    <button class="btn-primary" data-addlib>+ Add library</button>
    <div class="steps"><span><b>1</b>Create a library</span><span><b>2</b>Drop in your files</span><span><b>3</b>Start reading</span></div>
  </div></div>`;
}
const dropzoneHTML = lid => `<div class="dropzone"><div class="big">📚</div><h3>${esc(libName(lid))} is empty</h3>
  <p>Drag ${V(lid).dropWhat} — or whole folders — anywhere onto this window.<br>${V(lid).dropSorts}</p>
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
    ${edit ? `<div class="f libstore">✨ Optimize
      <span class="hintline" id="libStore">Measuring…</span>
      <div class="storerow"><button type="button" class="btn-sm" data-optlib="${edit.id}">${ico('spark', 15)} Optimize whole library…</button>
        <label for="libAuto">New uploads</label><select id="libAuto" disabled><option value="">stay as they are</option></select></div>
      <span class="hintline">“New uploads” converts whatever you add from now on to AVIF by itself, with the chosen preset. Originals are kept for Undo as usual.</span></div>` : ''}
    <div class="formerr" id="formErr"></div>
    <div class="formfoot">${edit ? '<button type="button" class="btn-danger" id="btnRemoveLib">Remove library</button>' : ''}<div class="grow"></div>
      <button type="button" class="btn-ghost" data-closemodal>Cancel</button><button type="submit" class="btn-primary">${edit ? 'Save' : 'Create library'}</button></div>`;
  syncModal();
  $('#libModal').classList.add('open');
  setTimeout(() => $('#libName').focus(), 60);
  if (edit) fillLibStore(edit);
}
async function fillLibStore(l) {
  const mine = () => modal?.edit?.id === l.id;
  api.get(`/api/libraries/${l.id}/storage`).then(st => {
    if (!mine() || !$('#libStore')) return;
    const parts = [fmtBytes(st.bytes)];
    if (st.optimized) parts.push(`${plural(st.optimized, V(l.id).b)} optimized${st.saved ? ` (saved ${fmtBytes(st.saved)})` : ''}`);
    parts.push(st.convertible ? `${plural(st.convertible, V(l.id).b)} · ${fmtBytes(st.convertibleBytes)} could still be converted` : 'nothing left to convert');
    $('#libStore').textContent = parts.join(' · ');
    $('#libForm [data-optlib]').disabled = !st.convertible;
  }).catch(() => { if (mine() && $('#libStore')) $('#libStore').textContent = ''; });
  api.get('/api/optimize/presets').then(p => {
    const sel = $('#libAuto'); if (!mine() || !sel) return;
    sel.innerHTML = '<option value="">stay as they are</option>' + p.presets.map(x => `<option value="${esc(x.id)}">→ AVIF · ${esc(x.name)}</option>`).join('');
    sel.value = p.presets.some(x => x.id === l.autoOptimize) ? l.autoOptimize : l.autoOptimize ? 'default' : '';
    sel.disabled = false;
  }).catch(() => {});
}
function optimizeLibrary(lid) {
  const l = S.libById[lid]; if (!l) return;
  openOptimize({ sel: { libraries: [lid] }, books: Object.values(S.books).filter(b => b.library === lid && !isTrashed(b)), title: l.name });
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
$('#libForm').addEventListener('click', e => {
  const b = e.target.closest('[data-optlib]'); if (!b) return;
  $('#libModal').classList.remove('open'); modal = null;
  optimizeLibrary(b.dataset.optlib);
});
$('#libForm').addEventListener('submit', async e => {
  e.preventDefault();
  const name = $('#libName').value.trim();
  if (!name) { $('#formErr').textContent = 'Give your library a name'; return $('#libName').focus(); }
  const body = { name, type: modal.type, rtl: modal.type === 'manga', color: modal.color };
  if (!modal.edit) body.path = $('#libPath').value.trim() || slug(name);
  if (modal.edit && $('#libAuto') && !$('#libAuto').disabled) body.autoOptimize = $('#libAuto').value;
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
  pollJobs();                                         // (auto-optimize may just have been switched on)
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
  const cos = isCosplay(s.library), edited = s.books.some(b => b.edited), unsaved = s.books.filter(b => b.unsaved).length;
  const f = $('#detForm');
  f.innerHTML = `
    <div class="dhead"><span class="dcover">${seriesCover(s, 160)}</span><div><h3>Edit details</h3><span class="hintline">${esc(libName(s.library))} · ${countLabel(s)}${edited ? ` · <b class="edtag" title="${unsaved ? 'Kept in the reader — not written into the files yet' : 'Kept in the reader (this kind of file can’t hold details)'}">edited</b>` : ''}</span>
      ${coverBooks(s).length ? '<button type="button" class="btn-sm editcover" data-editcover>🖼 Edit cover</button>' : ''}</div></div>
    <div class="f"><label for="dName">Name</label><input type="text" id="dName" maxlength="120" value="${esc(init.name)}"><span class="hintline">Renames the folder / file on disk · progress is kept</span></div>
    <div class="f2"><div class="f"><label for="dAuthor">${V(s.library).author}</label><input type="text" id="dAuthor" value="${esc(init.author)}" placeholder="${V(s.library).authorHint}"></div>
      <div class="f"><label for="dPub">${V(s.library).pub}</label><input type="text" id="dPub" value="${esc(init.publisher)}" placeholder="—"></div></div>
    <div class="f">Genres <span class="hintline">The first one is shown on the cover badge</span><div class="chipin" data-list="genres"></div></div>
    <div class="f">Tags <span class="hintline">Enter or comma adds · type <code>tag:f</code> / <code>tag:m</code> for tag ♀ / tag ♂</span><div class="chipin" data-list="tags"></div></div>
    <div class="f2"><div class="f"><label for="dRel">Release format</label><input type="text" id="dRel" value="${esc(init.release)}" placeholder="e.g. Web, Digital, Tankōbon"></div>
      <div class="f"><label for="dYear">Year</label><input type="text" id="dYear" inputmode="numeric" maxlength="4" value="${esc(init.year)}" placeholder="—"></div></div>
    <div class="f"><label for="dSum">Summary</label><textarea id="dSum" rows="4" placeholder="—">${esc(init.summary)}</textarea></div>
    ${cos ? '' : `<div class="f">Reading direction<div class="seg dseg"><button type="button" data-ddir="auto">Auto</button><button type="button" data-ddir="ltr">Left → right</button><button type="button" data-ddir="rtl">Right ← left</button></div></div>`}
    <span class="hintline">Saved in the reader at once. <b>Write into files</b> puts them into each file’s <code>metadata.json</code>${s.books.some(b => b.src === 'cbz' || b.src === 'cb7' || b.src === 'zip') ? ' (ComicInfo.xml is folded into it) — that rewrites each archive, so it takes a while for big ones' : ''}.</span>
    <div class="formerr" id="detErr"></div>
    <div class="formfoot">${edited ? '<button type="button" class="btn-ghost" id="detReset" title="Forget your edits and use what the files say">↺ Reset to file</button>' : ''}${unsaved ? `<button type="button" class="btn-ghost" id="detWrite" title="Put the saved details and cover choice into the files (metadata.json)">💾 Write into ${plural(unsaved, 'file')}</button>` : ''}<div class="grow"></div>
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
      <div class="cvfoot"><span class="hintline">Saved in the reader · <b>Write into files</b> in Edit details puts it into ${books.length > 1 ? 'that ' + unit + '’s' : 'the file’s'} <code>metadata.json</code></span><div class="grow"></div>
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
    const unsaved = ns ? ns.books.filter(x => x.unsaved).length : 0;   // the form stays as typed; only the button follows
    $('#detWrite')?.remove();
    if (unsaved && box) $('#detForm .formfoot .grow').insertAdjacentHTML('beforebegin',
      `<button type="button" class="btn-ghost" id="detWrite" title="Put the saved details and cover choice into the files (metadata.json)">💾 Write into ${plural(unsaved, 'file')}</button>`);
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
  if (e.target.closest('#detWrite')) {
    const b = e.target.closest('#detWrite'); b.disabled = true; b.textContent = 'Writing…';
    try { const d = await jsonFetch('POST', `/api/series/${DM.sid}/write`); appToast(`Written into ${plural(d.files, 'file')}`); b.remove(); }
    catch (err) { $('#detErr').textContent = err.message; b.disabled = false; b.textContent = '💾 Write into files'; }
    return load();                                    // (the form keeps whatever is typed in it)
  }
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
  if (Object.keys(fields).length) btn.textContent = 'Saving…';
  let sid = DM.sid;
  try {
    if (Object.keys(fields).length) await jsonFetch('PATCH', `/api/series/${sid}/details`, { fields });
    if (seriesPrefs[sid]?.rtl != null) saveSeriesPref(sid, { rtl: undefined });   // the file decides now
    if (v.name !== DM.init.name) {
      const d = await jsonFetch('PATCH', `/api/series/${sid}`, { name: v.name });
      moveSeriesPref(sid, d.seriesId);
      if (location.hash === `#/series/${sid}`) history.replaceState(null, '', `#/series/${d.seriesId}`);
      sid = d.seriesId;
    }
  } catch (err) { btn.disabled = false; btn.textContent = 'Save'; $('#detErr').textContent = err.message || 'Couldn’t save'; await load(); return; }
  btn.disabled = false;
  $('#detModal').classList.remove('open'); appToast('Details saved'); await load();
});
document.addEventListener('keydown', e => { if (e.isTrusted && e.key === 'Escape' && $('#detModal.open')) { e.stopImmediatePropagation(); $('#detModal').classList.remove('open'); } }, true);
