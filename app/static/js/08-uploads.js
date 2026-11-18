'use strict';
/* Cute&Funny Reader — frontend, part 8 of 11: drag & drop, the review sheet, uploads.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

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
  if (!items.length) return appToast(unreadable.length ? `Your browser couldn’t read ${plural(unreadable.length, 'file')} — see the upload panel` : 'Couldn’t find any archives, images or videos in that drop');
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

/* ---------- what a drop becomes is planned on the server (app/uploadplan.py) — one set of naming rules ---------- */
const IMG_RE = /\.(jpe?g|png|webp|avif|gif|bmp|tiff?|jxl|heic|heif)$/i;
const natCmp = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
const META_RE = /^(metadata\.json|comicinfo\.xml)$/i;
// the plan for a drop: the server gets paths, sizes and the text of metadata.json / ComicInfo.xml; the jobs it
// returns point back into `usable` by index
async function planDrop(lid, usable, seriesId, colFolder) {
  const meta = {};
  await Promise.all(usable.map(async (it, i) => {
    if (META_RE.test(it.file.name) && it.file.size < 200_000) { try { meta[i] = await it.file.text(); } catch { /* unreadable: names stay */ } }
  }));
  const d = await jsonFetch('POST', `/api/libraries/${lid}/plan`, { items: usable.map(it => ({ path: it.path, size: it.file.size })), meta,
    series: seriesId || null, collection: colFolder || null, today: new Date().toISOString().slice(0, 10) });
  const f = i => usable[i].file;
  return d.jobs.map(j => j.kind === 'pack'
    ? { name: j.name, images: j.images.map(f), extras: j.extras.map(f), size: j.size, packed: true, series: j.series, collection: j.collection, folder: j.folder }
    : { f: f(j.file), name: j.name, size: j.size, series: j.series, collection: j.collection, folder: j.folder });
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
/* ---------- the review sheet: what a drop will create, before anything is sent ----------
   One sheet instead of stacked Yes / No dialogs. The plan comes from the server (planDrop); the choices —
   stray images next to archives, regular .zip / .rar / .7z archives — are toggles that re-plan at once.
   A drop with nothing to decide that only adds ready-made files goes straight in (no extra click).
   → Promise<{ jobs, strayNote, plainNote } | null> (null = cancelled) */
async function reviewDrop(lid, usable, seriesId, colFolder, ignored) {
  const cos = isCosplay(lid), packExt = cos ? '.zip' : '.cbz';
  const stray = new Set(strayImages(usable));
  // regular archives: probably a comic / set, converted on the server (Cosplay keeps a .zip as it is)
  const plain = new Set(usable.filter(it => PLAIN_ARCHIVE_RE.test(it.file.name) && !(cos && /\.zip$/i.test(it.file.name))));
  const opt = { stray: true, plain: true };
  const picked = () => usable.filter(it => (opt.stray || !stray.has(it)) && (opt.plain || !plain.has(it)));
  let jobs = await planDrop(lid, picked(), seriesId, colFolder);
  if (!stray.size && !plain.size && jobs.every(j => !j.packed && !j.folder && !j.collection)) return { jobs, strayNote: 0, plainNote: 0 };
  const v = V(lid), sName = seriesId && S.seriesById[seriesId]?.name;
  const dest = j => sName ? `→ ${sName}` : [j.collection && `🗂️ ${j.collection}`, j.folder].filter(Boolean).join(' / ')
    || (cos ? 'Sorted by the name' : `${cap(v.s)} from the file name`);
  const list = () => {
    const groups = new Map();
    for (const j of jobs) { const k = dest(j); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(j); }
    const total = jobs.reduce((n, j) => n + (j.size || 0), 0);
    return `<p class="hintline">${plural(jobs.length, 'file')} · ${fmtBytes(total)} → ${plural(groups.size, 'place')} in ${esc(libName(lid))}</p>
      <div class="revlist">${[...groups].map(([k, js]) => `<div class="revgrp"><b>${esc(k)}</b>${js.slice(0, 40).map(j =>
        `<div class="revrow"><span>${esc(j.name)}</span><small>${j.packed ? `${plural(j.images.length, j.images.every(f => VIDEO_RE.test(f.name)) ? 'video' : 'picture')} packed` : fmtBytes(j.size || 0)}</small></div>`).join('')}${js.length > 40 ? `<div class="revrow"><small>+ ${js.length - 40} more</small></div>` : ''}</div>`).join('')
        || '<p class="hintline">Nothing would be added.</p>'}</div>`;
  };
  const paths = set => [...set].slice(0, 4).map(it => `<code>${esc(it.path)}</code>`).join(' ') + (set.size > 4 ? ` <span>+${set.size - 4} more</span>` : '');
  return new Promise(res => {
    const o = document.createElement('div');
    o.className = 'overlay fixed open askmodal revmodal';
    o.innerHTML = `<div class="sheet libform" role="dialog" aria-modal="true"><h3>Add to ${esc(libName(lid))}</h3>
      <div class="revbody">${list()}</div>
      ${stray.size ? `<label class="optchk revopt"><input type="checkbox" data-rev="stray" checked><span>Keep <b>${plural(stray.size, 'image')}</b> lying next to archives — packed into a ${v.ch} of their own<span class="askfiles">${paths(stray)}</span></span></label>` : ''}
      ${plain.size ? `<label class="optchk revopt"><input type="checkbox" data-rev="plain" checked><span>Convert <b>${plural(plain.size, 'regular archive')}</b> to <code>${packExt}</code> (only pictures &amp; videos are kept)<span class="askfiles">${paths(plain)}</span></span></label>` : ''}
      ${ignored ? `<p class="hintline">${plural(ignored, 'other file')} ignored — not a book, picture or video.</p>` : ''}
      <div class="formerr" id="revErr"></div>
      <div class="mrow askrow"><button class="btn-ghost" data-revgo="0">Cancel</button><button class="btn-primary" data-revgo="1">Add</button></div></div>`;
    const go = o.querySelector('[data-revgo="1"]');
    const sync = () => { go.disabled = !jobs.length; go.textContent = jobs.length ? `Add ${plural(jobs.length, 'file')}` : 'Nothing to add'; };
    const done = v => { document.removeEventListener('keydown', key, true); o.remove();
      res(v ? { jobs, strayNote: opt.stray ? 0 : stray.size, plainNote: opt.plain ? 0 : plain.size } : null); };
    const key = e => { if (!e.isTrusted) return; if (e.key === 'Escape') { e.stopImmediatePropagation(); done(false); } else if (e.key === 'Enter' && !go.disabled) { e.preventDefault(); done(true); } };
    o.addEventListener('change', async e => {
      const k = e.target.dataset?.rev; if (!k) return;
      opt[k] = e.target.checked; go.disabled = true;
      try { jobs = await planDrop(lid, picked(), seriesId, colFolder); o.querySelector('.revbody').innerHTML = list(); o.querySelector('#revErr').textContent = ''; }
      catch (err) { o.querySelector('#revErr').textContent = err.message; }
      sync();
    });
    o.addEventListener('click', e => { const b = e.target.closest('[data-revgo]'); if (b && e.isTrusted && !b.disabled) done(b.dataset.revgo === '1'); });
    backdropCloses(o, () => done(false));
    document.addEventListener('keydown', key, true);
    document.body.appendChild(o); sync(); go.focus();
  });
}

async function uploadFiles(lid, input, seriesId = null, colFolder = null) {
  const items = input.map(x => x.file ? x : { file: x, path: x.webkitRelativePath || x.name });
  const usable = items.filter(it => BOOK_RE.test(it.file.name) || IMG_RE.test(it.file.name) || VIDEO_RE.test(it.file.name) || META_RE.test(it.file.name));
  let r;
  try { r = await reviewDrop(lid, usable, seriesId, colFolder, items.length - usable.length); }
  catch (err) { appToast(`Couldn’t plan this drop: ${err.message}`); return 0; }
  if (!r) return 0;                                   // cancelled in the review sheet
  const { jobs, strayNote, plainNote } = r;
  const ignored = items.length - usable.length;
  if (!jobs.length && (strayNote || plainNote)) { appToast('Nothing to add — you skipped everything in that drop'); return 0; }
  if (!jobs.length) { UP.rows.push({ f: { size: 0 }, name: `${plural(items.length, 'file')} skipped`, state: 'err', msg: 'No archives, images or videos', p: 1 }); return renderUploads(true); }
  const upBatch = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);   // groups this drop in the upload log
  const batch = jobs.map(j => ({ ...j, f: j.f || { size: j.size }, lib: lid, batch: upBatch, state: 'queued', msg: j.packed ? `${j.images.length} images → ${j.name.slice(j.name.lastIndexOf('.'))}` : 'Waiting', p: 0,
    where: j.series ? '' : [j.collection && `🗂️ ${j.collection}`, j.folder].filter(Boolean).join(' / ') }));
  if (ignored) batch.push({ f: { size: 0 }, name: `${plural(ignored, 'other file')} ignored`, state: 'skip', msg: 'Not a book, picture or video', p: 1 });
  if (plainNote) batch.push({ f: { size: 0 }, name: `${plural(plainNote, 'archive')} skipped`, state: 'skip', msg: 'Your choice', p: 1 });
  if (strayNote) batch.push({ f: { size: 0 }, name: `${plural(strayNote, 'stray image')} skipped`, state: 'skip', msg: 'Your choice', p: 1 });
  UP.rows.push(...batch); renderUploads(true);
  const queue = batch.filter(r => r.state === 'queued');
  const worker = async () => { let r; while ((r = queue.shift())) if (r.state === 'queued') await putFile(r); };
  await Promise.all([worker(), worker()]);
  logUploadBatch(upBatch, lid, batch, ignored, strayNote + plainNote);
  await api.post('/api/scan');
  setTimeout(load, 700); setTimeout(load, 2500);
  const added = batch.filter(r => r.state === 'ok').length;
  if (!UP.rows.some(r => r.state === 'err' || r.state === 'queued' || r.state === 'up')) {
    setTimeout(() => { if (!UP.rows.some(r => r.state === 'queued' || r.state === 'up' || r.state === 'err')) { UP.rows = []; $('#uploads').classList.remove('on'); } }, 6000);
  }
  return added;
}
// one request; resolves with { status, data } (status 0 = no answer). r.xhr lets Cancel abort it.
function xhrSend(r, method, url, body, onProgress) {
  return new Promise(res => {
    const x = new XMLHttpRequest();
    r.xhr = x;
    x.open(method, url);
    if (onProgress) x.upload.onprogress = e => { if (e.lengthComputable) onProgress(e.loaded); };
    x.onload = () => { r.xhr = null; let d = {}; try { d = JSON.parse(x.responseText); } catch {} res({ status: x.status, data: d }); };
    x.onerror = () => { r.xhr = null; res({ status: 0, data: {} }); };
    x.onabort = () => { r.xhr = null; res({ status: -1, data: {} }); };
    x.send(body);
  });
}
function placeQuery(r) {
  const q = new URLSearchParams({ name: r.name });
  if (r.series) q.set('series', r.series);
  if (r.collection) q.set('collection', r.collection);
  if (r.folder) q.set('folder', r.folder);
  if (r.batch) q.set('batch', r.batch);
  return q;
}
function uploadDone(r, status, d) {
  if (status > 0 && status < 300) { r.p = 1; r.path = d.path; r.state = d.skipped ? 'skip' : 'ok'; r.msg = d.skipped ? 'Already there' : d.converted ? `Converted to ${d.path.slice(d.path.lastIndexOf('.'))} ✓` : 'Added ✓'; }
  else { r.state = 'err'; r.p = 1; r.msg = d.detail || (status ? `Error ${status}` : 'Network error'); r.serverSaw = status > 0; }
  renderUploads();
}
// A folder of photos: the files go to the server one by one, straight into the .zip / .cbz it builds
// (nothing big is held in the browser's memory — sets with videos run to gigabytes).
async function putPack(r) {
  const files = [...r.images, ...(r.extras || [])];
  const pad = Math.max(3, String(r.images.length).length);
  const total = files.reduce((n, f) => n + f.size, 0) || 1;
  r.state = 'up'; r.msg = '0%'; renderUploads();
  const start = await xhrSend(r, 'POST', `/api/libraries/${r.lib}/packs`);
  if (r.cancel || start.status === -1) return markCancelled(r);
  if (start.status !== 200) return uploadDone(r, start.status, start.data);
  const pid = start.data.id;
  const drop = () => fetch(`/api/packs/${pid}`, { method: 'DELETE' }).catch(() => {});
  let sent = 0;
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const ext = (f.name.match(/\.[^.]+$/) || ['.jpg'])[0].toLowerCase();
    const name = i >= r.images.length ? f.name : String(i + 1).padStart(pad, '0') + ext;   // pages: stable reading order
    const up = await xhrSend(r, 'PUT', `/api/packs/${pid}/files?${new URLSearchParams({ name })}`, f,
      loaded => { r.p = .97 * (sent + loaded) / total; r.msg = `${Math.round(r.p / .97 * 100)}%`; renderUploads(); });
    if (r.cancel || up.status === -1) { drop(); return markCancelled(r); }
    if (up.status !== 200) { drop(); return uploadDone(r, up.status, up.data); }
    sent += f.size;
  }
  r.images = null; r.extras = null;
  r.msg = 'Finishing…'; r.p = .97; renderUploads();
  // past this point Cancel can't stop it (the set is being put in place): the row shows how it really ended
  const fin = await xhrSend({}, 'POST', `/api/packs/${pid}/finish?${placeQuery(r)}`);
  uploadDone(r, fin.status, fin.data);
}
async function putFile(r) {
  if (r.packed) return putPack(r);
  return new Promise(res => {
    const x = new XMLHttpRequest();
    r.xhr = x;
    x.onabort = () => { r.xhr = null; markCancelled(r); res(); };
    r.state = 'up'; r.msg = '0%';
    x.open('PUT', `/api/libraries/${r.lib}/files?${placeQuery(r)}`);
    x.upload.onprogress = e => { if (e.lengthComputable) { r.p = e.loaded / e.total; r.msg = Math.round(e.loaded / e.total * 100) + '%'; renderUploads(); } };
    x.onload = () => {
      let d = {}; try { d = JSON.parse(x.responseText); } catch {}
      uploadDone(r, x.status, d); res();
    };
    x.onerror = () => { r.state = 'err'; r.p = 1; r.msg = 'Network error'; renderUploads(); res(); };
    x.send(r.f); renderUploads();
  });
}
// End of a drop → one entry in config/logs/uploads-….log. The server saw every file that reached it;
// this adds what never did: files that failed in the browser (packing, network) and the cancelled ones.
function logUploadBatch(id, lid, rows, ignored, skipped) {
  const real = rows.filter(r => r.batch === id);
  const failed = real.filter(r => r.state === 'err' && !r.serverSaw).map(r => ({ name: r.name, why: r.msg }));
  const cancelled = real.filter(r => r.state === 'cancel').length;
  fetch(`/api/uploads/${id}/done`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lib: lid, failed, cancelled, ignored, skipped }) }).catch(() => {});
}
function markCancelled(r) { r.state = 'cancel'; r.msg = 'Cancelled'; r.p = 1; r.images = null; renderUploads(); }
// stop everything still waiting / packing / sending. Files that already finished stay in the library;
// a half-sent file is thrown away by the server (it only keeps uploads that arrived complete).
function cancelUploads() {
  let n = 0;
  for (const r of UP.rows) {
    if (r.state === 'queued') { markCancelled(r); n++; }
    else if (r.state === 'up') { r.cancel = true; n++; if (r.xhr) r.xhr.abort(); }   // (a set the server is already packing still finishes)
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
