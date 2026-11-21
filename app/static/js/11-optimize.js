'use strict';
/* Cute&Funny Reader — frontend, part 11 of 11: ✨ Optimize, the jobs panel, ✨ Storage.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

/* ======================= ✨ OPTIMIZE (AVIF) ======================= */
// The ⋯ / right-click menu opens a dialog: pick a preset (each with an estimated size), optionally compare one
// page before / after, start. The server converts in the background; the Jobs panel shows progress.
const fmtBytes = n => n >= 1e9 ? `${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e8 ? 0 : 1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
const pctLess = (a, b) => b ? `−${Math.max(0, Math.round((1 - a / b) * 100))}%` : '';
function optSel(t) {
  if (M.kind === 'series') return { sel: { series: [t.id] }, books: t.books, title: t.name };
  if (M.kind === 'multiseries') return { sel: { series: [...t.ids] }, books: t.ids.flatMap(id => S.seriesById[id]?.books || []), title: t.label };
  if (M.kind === 'books') return { sel: { books: [...t.ids] }, books: t.ids.map(id => S.books[id]).filter(Boolean), title: t.label };
  if (M.kind === 'collection') return { sel: { collections: [t.id] }, books: t.inside.flatMap(x => x.books), title: t.name };
  return { sel: { books: [t.id] }, books: [t], title: `${t.series} · ${t.label}` };
}
function optItems(t) {
  const o = optSel(t);
  if (!o.books.some(b => b.format === 'images')) return '';
  return `<button data-mact="optimize">${ico('spark', 17)} Optimize…</button>`
    + (o.books.some(b => b.canUndo) ? `<button data-mact="unoptimize">${ico('refresh', 17)} Undo optimize</button>` : '');
}
const OPT = { cur: null, jobs: [], min: false, pollT: 0, seen: {} };
async function openOptimize(o) {
  let m = $('#optModal');
  if (!m) {
    m = document.createElement('div'); m.id = 'optModal'; m.className = 'overlay fixed';
    document.body.append(m);
    backdropCloses(m, closeOptimize);
    m.addEventListener('click', optClick);
    m.addEventListener('change', optChange);
    m.addEventListener('submit', e => { if (e.target.id === 'optNewForm') { e.preventDefault(); savePreset(); } });
  }
  const lib = o.books[0]?.library, cos = isCosplay(lib);
  OPT.cur = { ...o, lib, cos, preset: null, shrink: false, maxEdge: 4000, adding: false, keep: true, est: {}, gen: (OPT.cur?.gen || 0) + 1 };
  m.innerHTML = `<div class="sheet libform optsheet"><h3>✨ Optimize ${escWrap(o.title)}</h3><p class="hintline">Loading…</p></div>`;
  m.classList.add('open');
  let p;
  try { p = await api.get('/api/optimize/presets'); } catch (e) { m.querySelector('.hintline').textContent = 'Couldn’t load the presets.'; return; }
  Object.assign(OPT.cur, { presets: p.presets, keepDays: p.keepDays, preset: p.presets[0]?.id });
  drawOptimize();
  estimateAll();
}
function closeOptimize() { $('#optModal')?.classList.remove('open'); if (OPT.cur) OPT.cur.gen++; }
const optEdge = () => OPT.cur.shrink ? Math.max(800, +OPT.cur.maxEdge || 4000) : 0;
// the built-in Lossless preset only matters for lossless (RAW: PNG / BMP / TIFF) books — shown once the first
// estimate says the selection has some; presets you made yourself are always shown
const optShown = () => { const c = OPT.cur, raw = Object.values(c.est).some(e => e?.raw); return c.presets.filter(p => p.id !== 'lossless' || raw); };
const presetDesc = p => p.mode === 'lossless'
  ? 'Lossless WebP · pixel-exact · only PNG / BMP / TIFF pages'
  : `Quality ${p.quality} · speed ${p.speed}${p.subsampling && p.subsampling !== 'auto' ? ` · colour ${p.subsampling}` : ''}${p.grayscale === false ? ' · no B&amp;W detection' : ''}${p.id === 'default' ? ' · the baseline' : ''}${p.hint ? ` · ${esc(p.hint)}` : ''}`;
function drawOptimize() {
  const c = OPT.cur, m = $('#optModal'), any = Object.values(c.est)[0];
  const head = any ? `${plural(any.books, V(c.lib).b)} · ${any.pages.toLocaleString()} pages · ${fmtBytes(any.before)}` : `${plural(c.books.length, V(c.lib).b)}`;
  const why = any && Object.entries(any.why || {}).map(([w, n]) => `${plural(n, V(c.lib).b)} skipped — ${esc(w)}`).join('<br>');
  m.querySelector('.sheet').innerHTML = `<h3>✨ Optimize ${escWrap(c.title)}</h3>
    <p class="hintline" id="optHead">${head}</p>
    <div class="optlist" role="radiogroup" aria-label="Preset">${optShown().map(p => `<label class="optrow">
      <input type="radio" name="optPreset" value="${esc(p.id)}" ${p.id === c.preset ? 'checked' : ''}>
      <span class="on"><b>${esc(p.name)}</b><small>${presetDesc(p)}</small></span>
      <span class="est" data-est="${esc(p.id)}">${estText(c.est[p.id])}</span>
      ${p.builtin ? '<span></span>' : `<button type="button" class="optdel" data-delpreset="${esc(p.id)}" title="Delete this preset" aria-label="Delete preset ${esc(p.name)}">×</button>`}</label>`).join('')}</div>
    ${c.adding ? `<form class="optnew" id="optNewForm">
        <input type="text" id="optNewName" placeholder="Preset name" maxlength="40" aria-label="Preset name" autocomplete="off" required>
        <label>Quality <input type="number" id="optNewQ" min="0" max="100" value="${c.newQ ?? 70}" required ${c.newMode === 'lossless' ? 'disabled' : ''}></label>
        <label>Speed <input type="number" id="optNewS" min="0" max="10" value="${c.newS ?? 6}" required ${c.newMode === 'lossless' ? 'disabled' : ''}></label>
        <button type="submit" class="btn-sm pri">Save</button><button type="button" class="btn-sm" data-opt="cancelnew">Cancel</button>
        <small>Quality 0–100: higher looks better and is bigger. Speed 0–10: lower makes smaller files but converts slower.</small>
        <details class="optadv" ${c.advOpen ? 'open' : ''}><summary>Advanced</summary>
          <label>Format <select id="optNewMode">
            <option value="avif" ${c.newMode !== 'lossless' ? 'selected' : ''}>AVIF — much smaller, looks the same</option>
            <option value="lossless" ${c.newMode === 'lossless' ? 'selected' : ''}>Lossless WebP — pixel-exact (PNG / BMP / TIFF pages only)</option></select></label>
          <label>Colour <select id="optNewSub" ${c.newMode === 'lossless' ? 'disabled' : ''}>
            ${[['auto', 'Auto (4:4:4)'], ['4:4:4', '4:4:4 — full colour detail'], ['4:2:0', '4:2:0 — smaller, softer colour edges']].map(([v, t]) => `<option value="${v}" ${(c.newSub || 'auto') === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
          <label class="optchk"><input type="checkbox" id="optNewGray" ${c.newGray !== false ? 'checked' : ''} ${c.newMode === 'lossless' ? 'disabled' : ''}> Save black-and-white pages as grayscale (smaller)</label>
          <small>Max size: “Shrink huge photos” below.</small>
        </details>
        <div class="formerr" id="optNewErr"></div></form>`
      : '<button type="button" class="optadd" data-opt="newpreset">+ New preset</button>'}
    <label class="optchk"><input type="checkbox" id="optShrink" ${c.shrink ? 'checked' : ''}> Shrink huge photos to
      <input type="number" id="optEdge" min="800" max="16000" step="100" value="${c.maxEdge}" aria-label="Longest side in pixels"> px on the long edge</label>
    <label class="optchk"><input type="checkbox" id="optKeep" ${c.keep ? 'checked' : ''}> Keep originals for ${plural(c.keepDays, 'day')} — undo from the menu any time</label>
    ${any?.raw && c.presets.find(p => p.id === c.preset)?.mode !== 'lossless' ? `<p class="optnote warn">${plural(any.raw, V(c.lib).b)} ${any.raw === 1 ? 'is' : 'are'} lossless (RAW). ${any.raw === 1 ? 'It' : 'They'} won’t be lossless any more — pick <b>Lossless</b> to keep every pixel.</p>` : ''}
    ${why ? `<p class="optnote">${why}</p>` : ''}
    <div class="formerr" id="optErr"></div>
    <div class="formfoot"><button type="button" class="btn-ghost" data-opt="compare" ${any?.books ? '' : 'disabled'}>Compare pages…</button><div class="grow"></div>
      <button type="button" class="btn-ghost" data-opt="cancel">Cancel</button>
      <button type="button" class="btn-primary" data-opt="start" ${any && !any.books ? 'disabled' : ''}>${ico('spark', 16)} Optimize</button></div>`;
}
const estText = e => !e ? '<i>estimating…</i>' : e.error ? '—' : `~${fmtBytes(e.after)} <small>${pctLess(e.after, e.before)}</small>`;
async function estimateAll() {
  const c = OPT.cur, gen = c.gen, edge = optEdge();
  for (const p of c.presets) {
    if (c.est[p.id] || !optShown().includes(p)) continue;
    let e;
    try { e = await jsonFetch('POST', '/api/optimize/estimate', { ...c.sel, preset: p.id, maxEdge: edge }); }
    catch (err) { e = { error: err.message }; }
    if (gen !== OPT.cur.gen || edge !== optEdge()) return;          // closed, or the size changed meanwhile
    const first = !Object.values(c.est).some(x => x && !x.error);
    c.est[p.id] = e;
    if (first && !e.error) { drawOptimize(); if (e.raw) return estimateAll(); }   // header, warnings, buttons — and RAW shows Lossless
    else { const el = $(`#optModal [data-est="${CSS.escape(p.id)}"]`); if (el) el.innerHTML = estText(e); }
  }
}
function optChange(e) {
  const c = OPT.cur; if (!c) return;
  if (e.target.name === 'optPreset') { c.preset = e.target.value; return drawOptimize(); }   // (the RAW warning depends on it)
  if (['optNewMode', 'optNewSub', 'optNewGray', 'optNewQ', 'optNewS', 'optNewName'].includes(e.target.id)) {
    const name = $('#optNewName').value;
    Object.assign(c, { newMode: $('#optNewMode').value, newSub: $('#optNewSub').value, newGray: $('#optNewGray').checked,
      newQ: +$('#optNewQ').value, newS: +$('#optNewS').value, advOpen: true });
    if (e.target.id === 'optNewMode') { drawOptimize(); $('#optNewName').value = name; }   // lossless greys out what doesn't apply
    return;
  }
  if (e.target.id === 'optKeep') { c.keep = e.target.checked; return; }
  if (e.target.id === 'optShrink' || e.target.id === 'optEdge') {
    c.shrink = $('#optShrink').checked; c.maxEdge = +$('#optEdge').value || 4000;
    c.est = {}; c.gen++;
    $$('#optModal [data-est]').forEach(el => { el.innerHTML = estText(null); });
    estimateAll();
  }
}
async function savePreset() {
  const c = OPT.cur, err = $('#optNewErr');
  c.newQ = +$('#optNewQ').value; c.newS = +$('#optNewS').value;
  try {
    c.newMode = $('#optNewMode').value; c.newSub = $('#optNewSub').value; c.newGray = $('#optNewGray').checked;
    const p = await jsonFetch('POST', '/api/optimize/presets', { name: $('#optNewName').value, quality: c.newQ, speed: c.newS,
      mode: c.newMode, subsampling: c.newSub, grayscale: c.newGray });
    c.presets = [...c.presets, p]; c.preset = p.id; c.adding = false;
  } catch (e) { err.textContent = e.message; return; }
  drawOptimize(); estimateAll();
}
async function deletePreset(btn) {
  const c = OPT.cur, id = btn.dataset.delpreset;
  if (!btn.classList.contains('armed')) {                         // deleting takes a second click
    btn.classList.add('armed'); btn.textContent = 'Delete?';
    return setTimeout(() => { if (btn.isConnected) { btn.classList.remove('armed'); btn.textContent = '×'; } }, 3500);
  }
  try { await jsonFetch('DELETE', `/api/optimize/presets/${encodeURIComponent(id)}`); }
  catch (e) { $('#optErr').textContent = e.message; return; }
  c.presets = c.presets.filter(p => p.id !== id); delete c.est[id];
  if (c.preset === id) c.preset = c.presets[0]?.id;
  drawOptimize();
}
async function optClick(e) {
  const del = e.target.closest('[data-delpreset]');
  if (del) { e.preventDefault(); return deletePreset(del); }      // (inside the row's label: don't select it)
  const a = e.target.closest('[data-opt]')?.dataset.opt; if (!a) return;
  const c = OPT.cur;
  if (a === 'cancel') return closeOptimize();
  if (a === 'compare') return openCompare();
  if (a === 'newpreset') { c.adding = true; drawOptimize(); return $('#optNewName')?.focus(); }
  if (a === 'cancelnew') { c.adding = false; return drawOptimize(); }
  if (a === 'start') {
    const btn = e.target.closest('button'); btn.disabled = true;
    try {
      await jsonFetch('POST', '/api/optimize', { ...c.sel, preset: c.preset, keep: c.keep, maxEdge: optEdge(), title: c.title });
    } catch (err) { btn.disabled = false; $('#optErr').textContent = err.message; return; }
    closeOptimize(); S.sel = null; OPT.min = false;
    appToast('✨ Optimizing in the background'); pollJobs();
  }
}

/* ---- the Jobs panel (bottom right, above the uploads panel) ---- */
// refreshed when an Optimize job changes (the live stream, js/13-live.js) or after a button here
async function pollJobs(d) {
  if (!S.me) return;
  if (!d) { try { d = await api.get('/api/jobs'); } catch { return; } }
  d = { jobs: d.jobs.filter(j => j.kind === 'optimize') };         // (the other kinds: the working pill)
  OPT.jobs = d.jobs;
  let changed = false;                                             // a book finished: refresh the library (AVIF pills)
  for (const j of d.jobs) {
    const n = j.done.length + j.failed.length + j.skipped.length;
    if (OPT.seen[j.id] !== undefined && OPT.seen[j.id] !== n) changed = true;
    OPT.seen[j.id] = n;
  }
  if (changed) load();
  renderJobs();
  if (changed && S.inStorage) renderStorage();
}
function jobLine(j) {
  const n = j.books.length, fin = j.done.length + j.skipped.length + j.failed.length;
  const saved = j.before ? ` · saved ${fmtBytes(j.before - j.after)} (${pctLess(j.after, j.before)})` : '';
  const extra = [j.skipped.length && `${j.skipped.length} skipped`, j.failed.length && `${j.failed.length} failed`].filter(Boolean).join(' · ');
  if (j.state === 'done') return `Done${saved}${extra ? ' · ' + extra : ''}`;
  if (j.state === 'cancelled') return `Cancelled after ${fin} of ${n}${saved}`;
  if (j.state === 'paused') return `Paused · ${fin} of ${n}${saved}`;
  if (j.waiting) return `Waits for the night hours · ${fin} of ${n}${saved}`;
  if (j.state === 'queued' && !fin) return 'Waiting…';
  return `${Math.min(fin + 1, n)} of ${n}${j.current ? ` · ${j.current.label}` : ''}${saved}${extra ? ' · ' + extra : ''}`;
}
function renderJobs() {
  let box = $('#jobs');
  if (!box) {
    box = document.createElement('div'); box.id = 'jobs'; box.className = 'glass';
    document.body.append(box);
    box.addEventListener('click', jobsClick);
    new ResizeObserver(placeJobs).observe($('#uploads'));
  }
  const jobs = OPT.jobs, active = jobs.filter(j => j.state === 'queued' || j.state === 'running' || j.state === 'paused');
  if (!jobs.length) { box.classList.remove('on'); return; }
  const pages = active.reduce((n, j) => n + j.pagesTotal, 0), done = active.reduce((n, j) => n + j.pagesDone, 0);
  const pct = pages ? Math.round(done / pages * 100) : 100;
  box.classList.add('on'); box.classList.toggle('min', OPT.min);
  box.innerHTML = `<div class="up-h"><b>${ico('spark', 15)} ${active.length ? `Optimizing ${plural(active.length, 'job')}` : 'Optimize finished'}</b>
      ${OPT.min && active.length ? `<span class="pct">${pct}%</span>` : ''}<div class="bar" ${active.length ? '' : 'hidden'}><i style="width:${pct}%"></i></div>
      <button data-jmin title="${OPT.min ? 'Show jobs' : 'Minimise'}">${OPT.min ? '▴' : '▾'}</button>${active.length ? '' : '<button data-jclose title="Close">×</button>'}</div>
    <div class="up-list">${jobs.map(j => {
      const p = j.pagesTotal ? Math.round(j.pagesDone / j.pagesTotal * 100) : 0, live = j.state === 'queued' || j.state === 'running';
      const fails = j.failed.map(f => S.books[f.id] ? `${S.books[f.id].series} · ${S.books[f.id].label}: ${f.why}` : f.why).join('\n');
      return `<div class="up-row job ${j.state}" data-job="${j.id}"><span class="n" title="${esc(j.title)}">${esc(j.title || 'Optimize')}<small class="w">${esc(j.presetName || j.preset)}</small></span>
        <span class="s">${j.state === 'running' || j.state === 'queued' ? `${p}%` : ''}</span>
        <div class="bar"><i style="width:${j.state === 'done' ? 100 : p}%"></i></div>
        <div class="jmeta" ${fails ? `title="${esc(fails)}"` : ''}>${esc(jobLine(j))}</div>
        <div class="jacts">${j.waiting ? '<button class="btn-sm" data-jact="now">Run now</button>' : ''}${live ? '<button class="btn-sm" data-jact="pause">Pause</button>' : j.state === 'paused' ? '<button class="btn-sm" data-jact="resume">Resume</button>' : ''}
          ${live || j.state === 'paused' ? '<button class="btn-sm" data-jact="cancel">Cancel</button>' : '<button class="btn-sm" data-jact="dismiss">Dismiss</button>'}</div></div>`;
    }).join('')}</div>`;
  placeJobs();
}
function placeJobs() {
  const box = $('#jobs'), up = $('#uploads'); if (!box) return;
  box.style.bottom = up.classList.contains('on') && !isPhone() ? `${up.offsetHeight + 30}px` : '';
}
async function jobsClick(e) {
  if (e.target.closest('[data-jmin]') || (OPT.min && e.target.closest('.up-h') && !e.target.closest('[data-jclose]'))) { OPT.min = !OPT.min; return renderJobs(); }
  if (e.target.closest('[data-jclose]')) {
    for (const j of OPT.jobs) await jsonFetch('POST', `/api/jobs/${j.id}/dismiss`).catch(() => {});
    return pollJobs();
  }
  const b = e.target.closest('[data-jact]'); if (!b) return;
  b.disabled = true;
  try { await jsonFetch('POST', `/api/jobs/${b.closest('[data-job]').dataset.job}/${b.dataset.jact}`); } catch (err) { appToast(err.message); }
  pollJobs();
}

/* ---- full-screen before / after: any page of the selection, fit / 100% / 200%, drag to move around ---- */
// Both pictures are drawn at the original's size, so a shrunken AVIF is shown scaled up — exactly what you'd see.
// 100% = one pixel of the original on one pixel of the screen.
const CMP = { list: [], i: 0, zoom: 'fit', split: 50, x: 0, y: 0, s: 1, key: '', drag: null };
function openCompare() {
  const c = OPT.cur;
  CMP.list = c.books.filter(b => b.format === 'images')
    .flatMap(b => Array.from({ length: b.pages }, (_, n) => n).filter(n => !(b.videos || []).includes(n)).map(n => [b.id, n]));
  if (!CMP.list.length) return;
  const s = Object.values(c.est).find(x => x?.sample)?.sample;
  CMP.i = Math.max(0, s ? CMP.list.findIndex(([b, n]) => b === s.book && n === s.page) : 0);
  CMP.zoom = 'fit'; CMP.split = 50;
  let o = $('#optCompare');
  if (!o) {
    o = document.createElement('div'); o.id = 'optCompare'; o.className = 'cmpfull';
    document.body.append(o);
    o.addEventListener('click', cmpClick);
    o.addEventListener('change', e => { if (e.target.id === 'cmpBook') cmpGo(CMP.list.findIndex(([b]) => b === e.target.value)); });
    o.addEventListener('pointerdown', cmpDown);
    o.addEventListener('dblclick', e => { if (e.target.closest('.cmpstage') && !e.target.closest('.cmpknob')) cmpZoom(CMP.zoom === 'fit' ? '1' : 'fit', e); });
    o.addEventListener('wheel', e => {                                   // the wheel scrolls a zoomed page
      if (CMP.zoom === 'fit' || !e.target.closest('.cmpstage')) return;
      e.preventDefault(); CMP.x -= e.shiftKey ? e.deltaY : e.deltaX; CMP.y -= e.shiftKey ? 0 : e.deltaY; cmpLayout();
    }, { passive: false });
    document.addEventListener('keydown', e => {
      if (!$('#optCompare.open')) return;
      if (e.key === 'Escape') { e.stopImmediatePropagation(); e.preventDefault(); return closeCompare(); }
      if (e.target.matches?.('select, input')) return;
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); cmpGo(CMP.i + 1); }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); cmpGo(CMP.i - 1); }
      else if (e.key === 'z') cmpZoom(CMP.zoom === 'fit' ? '1' : 'fit');
    }, true);
    addEventListener('resize', () => { if ($('#optCompare.open')) cmpLayout(); });
  }
  const books = [...new Set(CMP.list.map(([b]) => b))];
  o.innerHTML = `<div class="cmpbar">
      <div class="cmpp" role="radiogroup" aria-label="Preset">${c.presets.map(p => `<button type="button" role="radio" data-cpreset="${esc(p.id)}">${esc(p.name)}</button>`).join('')}</div>
      <div class="cmpnav"><button type="button" class="ib" data-cnav="-1" aria-label="Previous page">${ico('chevL', 18)}</button>
        <span class="cmppos"></span><button type="button" class="ib" data-cnav="1" aria-label="Next page">${ico('chevR', 18)}</button>
        ${books.length > 1 ? `<select id="cmpBook" aria-label="${cap(V(c.lib).b)}">${books.map(id => { const b = S.books[id]; return `<option value="${id}">${esc(b ? `${b.series} · ${b.label}` : id)}</option>`; }).join('')}</select>` : ''}</div>
      <div class="cmpz" role="group" aria-label="Zoom">${[['fit', 'Fit'], ['1', '100%'], ['2', '200%']].map(([z, t]) => `<button type="button" data-czoom="${z}">${t}</button>`).join('')}</div>
      <button type="button" class="btn-primary" data-cclose>Done</button></div>
    <div class="cmpstage"><div class="lay a"><img alt="Original" draggable="false"></div><div class="lay b"><img alt="AVIF" draggable="false"></div>
      <span class="lab l"></span><span class="lab r"></span><span class="cmpmsg"></span>
      <button type="button" class="cmpknob" aria-label="Move the before / after divider (arrow keys)"><i></i></button></div>
    <p class="cmphint">Drag the divider to compare · ${'double-click or Z'} zooms to 100% · drag to move around · ← → other pages</p>`;
  o.querySelector('.cmpknob').addEventListener('keydown', e => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); CMP.split = clamp(CMP.split + (e.key === 'ArrowLeft' ? -5 : 5), 0, 100); cmpLayout(); }
  });
  o.classList.add('open');
  cmpLoad();
}
function closeCompare() { $('#optCompare')?.classList.remove('open'); CMP.key = ''; }
function cmpGo(i) {
  if (i < 0 || i >= CMP.list.length || i === CMP.i) return;
  CMP.i = i; cmpLoad();
}
async function cmpLoad() {
  const o = $('#optCompare'), c = OPT.cur, [bid, n] = CMP.list[CMP.i], b = S.books[bid];
  const preset = c.presets.find(p => p.id === c.preset), edge = optEdge();
  const key = `${bid}-${n}-${c.preset}-${edge}`; CMP.key = key;
  o.querySelectorAll('[data-cpreset]').forEach(x => x.setAttribute('aria-checked', x.dataset.cpreset === c.preset));
  o.querySelectorAll('[data-czoom]').forEach(x => x.classList.toggle('on', x.dataset.czoom === CMP.zoom));
  const pagesOf = CMP.list.filter(([x]) => x === bid).length, nth = CMP.list.slice(0, CMP.i + 1).filter(([x]) => x === bid).length;
  o.querySelector('.cmppos').textContent = `${o.querySelector('#cmpBook') ? '' : `${b.series} · ${b.label} · `}page ${nth} of ${pagesOf}`;
  if (o.querySelector('#cmpBook')) o.querySelector('#cmpBook').value = bid;
  o.querySelector('[data-cnav="-1"]').disabled = CMP.i === 0;
  o.querySelector('[data-cnav="1"]').disabled = CMP.i === CMP.list.length - 1;
  const A = o.querySelector('.lay.a img'), B = o.querySelector('.lay.b img'), msg = o.querySelector('.cmpmsg');
  const lr = o.querySelector('.lab.r'), ll = o.querySelector('.lab.l');
  B.style.visibility = 'hidden'; lr.textContent = `${preset?.name || ''} · working…`; ll.textContent = 'Original'; msg.textContent = '';
  const origLoaded = new Promise(res => { A.onload = res; A.onerror = res; });
  A.src = URLS.page(b, n);                                       // the original file, untouched
  try {
    const r = await fetch(`/api/books/${bid}/pages/${n}/optimized?preset=${encodeURIComponent(c.preset)}&max=${edge}`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'error');
    const before = +r.headers.get('X-Before'), after = +r.headers.get('X-After'), blob = await r.blob();
    await origLoaded;
    if (CMP.key !== key) return;
    const url = URL.createObjectURL(blob);
    await new Promise(res => { B.onload = res; B.onerror = res; B.src = url; });
    URL.revokeObjectURL(url);
    if (CMP.key !== key) return;
    ll.textContent = `Original · ${fmtBytes(before)} · ${A.naturalWidth}×${A.naturalHeight}`;
    lr.textContent = after === before ? `${preset?.name} · kept as it is (AVIF wouldn’t be smaller)`
      : `${preset?.name} · ${fmtBytes(after)} (${pctLess(after, before)}) · ${B.naturalWidth}×${B.naturalHeight}`;
    B.style.visibility = '';
  } catch (e) { if (CMP.key === key) { await origLoaded; lr.textContent = `${preset?.name} · couldn’t convert this page`; msg.textContent = e.message !== 'error' ? e.message : ''; } }
  if (CMP.key === key) cmpLayout(true);
}
function cmpLayout(newPage) {
  const o = $('#optCompare'), st = o.querySelector('.cmpstage'), A = o.querySelector('.lay.a img');
  const vw = st.clientWidth, vh = st.clientHeight, nw = A.naturalWidth || 1, nh = A.naturalHeight || 1;
  const s = CMP.zoom === 'fit' ? Math.min(vw / nw, vh / nh) : +CMP.zoom / (devicePixelRatio || 1);
  const W = nw * s, H = nh * s;
  if (newPage) { CMP.x = (vw - W) / 2; CMP.y = H > vh ? 0 : (vh - H) / 2; }   // a new page: centred, from its top
  CMP.x = W <= vw ? (vw - W) / 2 : clamp(CMP.x, vw - W, 0);
  CMP.y = H <= vh ? (vh - H) / 2 : clamp(CMP.y, vh - H, 0);
  CMP.s = s;
  for (const img of o.querySelectorAll('.lay img')) {
    img.style.width = `${W}px`; img.style.height = `${H}px`; img.style.transform = `translate(${CMP.x}px, ${CMP.y}px)`;
  }
  st.style.setProperty('--split', `${CMP.split}%`);
  st.classList.toggle('zoomed', CMP.zoom !== 'fit');
  st.classList.toggle('pixels', CMP.zoom === '2');                // 200%: real pixels, not smoothed over
  o.querySelectorAll('[data-czoom]').forEach(x => x.classList.toggle('on', x.dataset.czoom === CMP.zoom));
}
function cmpZoom(z, e) {
  const st = $('#optCompare .cmpstage'), r = st.getBoundingClientRect();
  const px = e ? e.clientX - r.left : st.clientWidth / 2, py = e ? e.clientY - r.top : st.clientHeight / 2;
  const u = (px - CMP.x) / CMP.s, v = (py - CMP.y) / CMP.s;          // the image point under the cursor stays put
  CMP.zoom = z;
  const s = z === 'fit' ? 0 : +z / (devicePixelRatio || 1);
  if (s) { CMP.x = px - u * s; CMP.y = py - v * s; }
  cmpLayout();
}
function cmpDown(e) {
  const st = e.target.closest('.cmpstage'); if (!st || e.button !== 0) return;
  const knob = e.target.closest('.cmpknob'), r = st.getBoundingClientRect();
  const mode = knob || CMP.zoom === 'fit' ? 'split' : 'pan';      // fit: dragging anywhere moves the divider
  CMP.drag = { mode, sx: e.clientX, sy: e.clientY, x: CMP.x, y: CMP.y };
  st.setPointerCapture(e.pointerId);
  const move = ev => {
    if (CMP.drag.mode === 'split') CMP.split = clamp((ev.clientX - r.left) / r.width * 100, 0, 100);
    else { CMP.x = CMP.drag.x + ev.clientX - CMP.drag.sx; CMP.y = CMP.drag.y + ev.clientY - CMP.drag.sy; }
    cmpLayout();
  };
  if (mode === 'split') move(e);
  const up = () => { st.removeEventListener('pointermove', move); st.removeEventListener('pointerup', up); st.removeEventListener('pointercancel', up); CMP.drag = null; };
  st.addEventListener('pointermove', move); st.addEventListener('pointerup', up); st.addEventListener('pointercancel', up);
  e.preventDefault();
}
function cmpClick(e) {
  if (e.target.closest('[data-cclose]')) return closeCompare();
  const nav = e.target.closest('[data-cnav]'); if (nav) return cmpGo(CMP.i + +nav.dataset.cnav);
  const z = e.target.closest('[data-czoom]'); if (z) return cmpZoom(z.dataset.czoom);
  const p = e.target.closest('[data-cpreset]');
  if (p) {                                                        // the preset chosen here is the one the dialog uses
    OPT.cur.preset = p.dataset.cpreset;
    const r = $(`#optModal input[name=optPreset][value="${CSS.escape(p.dataset.cpreset)}"]`); if (r) r.checked = true;
    cmpLoad();
  }
}

/* ======================= ✨ STORAGE ======================= */
// How big each library is, what ✨ Optimize already saved and what it could still convert; the biggest
// unconverted series; the kept originals; and the night-only hours for the optimizer.
const hh = h => `${String(h).padStart(2, '0')}:00`;
async function renderStorage() {
  $('#viewHome').classList.remove('on'); $('#viewSeries').classList.remove('on'); $('#viewFavs').classList.remove('on'); $('#viewTrash').classList.remove('on');
  const v = $('#viewStorage'); v.classList.add('on'); S.inStorage = true;
  if (!v.dataset.ready) {
    v.dataset.ready = 1;
    v.innerHTML = '<div class="shelf-h"><div><h2>✨ Storage</h2><p class="sub">Measuring…</p></div></div>';
    v.addEventListener('click', storageClick);
    v.addEventListener('change', storageChange);
  }
  let st;
  try { st = await api.get('/api/storage'); } catch { v.querySelector('.sub').textContent = 'Couldn’t measure the libraries.'; return; }
  if (!S.inStorage) return;
  S.storage = st;
  const total = st.libraries.reduce((n, l) => n + l.bytes, 0), saved = st.libraries.reduce((n, l) => n + l.saved, 0);
  const left = st.libraries.reduce((n, l) => n + l.convertibleBytes, 0), max = Math.max(1, ...st.libraries.map(l => l.bytes));
  const sch = st.schedule, hours = sel => Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${h === sel ? 'selected' : ''}>${hh(h)}</option>`).join('');
  const big = st.biggest.map(x => ({ ...x, s: S.seriesById[x.id] })).filter(x => x.s);
  v.innerHTML = `<div class="shelf-h"><div><h2>✨ Storage</h2>
      <p class="sub">${fmtBytes(total)} in ${plural(st.libraries.length, 'library').replace('librarys', 'libraries')}${saved ? ` · ${fmtBytes(saved)} saved so far` : ''}${left ? ` · ${fmtBytes(left)} not optimized yet` : ''}</p></div></div>
    <div class="stlibs">${st.libraries.map(r => { const l = S.libById[r.id]; if (!l) return ''; return `<div class="stlib">
        <div class="stname"><i style="background:${esc(l.color)}"></i><b>${esc(l.name)}</b><small>${plural(r.books, 'file')} · ${fmtBytes(r.bytes)}</small></div>
        <div class="stbar" style="width:${Math.max(6, r.bytes / max * 100)}%" role="img" aria-label="${fmtBytes(r.convertibleBytes)} of ${fmtBytes(r.bytes)} could still be converted">
          <i class="todo" style="width:${r.bytes ? r.convertibleBytes / r.bytes * 100 : 0}%"></i></div>
        <div class="stmeta">${r.optimized ? `${plural(r.optimized, 'file')} optimized${r.saved ? ` · saved ${fmtBytes(r.saved)}` : ''} · ` : ''}${r.convertible ? `${fmtBytes(r.convertibleBytes)} in ${plural(r.convertible, 'file')} could still be converted` : 'nothing left to convert'}</div>
        <button type="button" class="btn-sm" data-stlib="${r.id}" ${r.convertible ? '' : 'disabled'}>${ico('spark', 15)} Optimize…</button></div>`; }).join('') || '<p class="hintline">No libraries yet.</p>'}</div>
    <div class="shelf-h slim"><div><h2>Biggest, not optimized yet</h2></div>
      <div class="shelf-actions">${big.length > 1 ? `<button type="button" class="btn-sm pri" data-stall>${ico('spark', 15)} Optimize the ${big.length} biggest…</button>` : ''}</div></div>
    <div class="stbig">${big.map(x => `<div class="strow"><button type="button" class="stopen" data-series="${x.id}">${esc(x.s.name)}</button>
        <small>${esc(libName(x.s.library))} · ${plural(x.books, V(x.s.library).b)}</small><b>${fmtBytes(x.bytes)}</b>
        <button type="button" class="btn-sm" data-stseries="${x.id}">Optimize…</button></div>`).join('') || '<p class="hintline">Everything that can be converted already is.</p>'}</div>
    <div class="shelf-h slim"><div><h2>Kept originals</h2></div></div>
    <div class="stbox">${st.kept.books
      ? `<span>${plural(st.kept.books, 'original')} kept for Undo · about ${fmtBytes(st.kept.bytes)} in the config folder · each is deleted ${plural(st.kept.days, 'day')} after its conversion.</span>
         <button type="button" class="btn-sm" data-stdrop>Delete them now</button>`
      : `<span>None. Originals are kept for ${plural(st.kept.days, 'day')} after a conversion, so it can be undone.</span>`}</div>
    <div class="shelf-h slim"><div><h2>Trash</h2></div></div>
    <div class="stbox">${S.status?.trash?.count
      ? `<span>${plural(S.status.trash.count, 'item')} in the trash · ${fmtBytes(S.status.trash.bytes)} that can be freed.</span>
         <button type="button" class="btn-sm" data-sttrash>Open trash</button><button type="button" class="btn-sm" data-stempty>Empty trash</button>`
      : '<span>The trash is empty.</span>'}</div>
    <div class="shelf-h slim"><div><h2>When to optimize</h2></div></div>
    <div class="stbox"><label class="optchk"><input type="checkbox" id="stNight" ${sch.on ? 'checked' : ''}> Only between
        <select id="stFrom" aria-label="From">${hours(sch.from)}</select> and <select id="stTo" aria-label="Until">${hours(sch.to)}</select></label>
      <span class="hintline" id="stNote">${sch.on ? (st.allowed ? 'Inside the hours right now — jobs run.' : 'Outside the hours right now — jobs wait (each has a “Run now” button).') : 'Jobs run whenever they are started.'}</span></div>`;
}
function storageClick(e) {
  const t = e.target;
  const sl = t.closest('[data-stlib]'); if (sl) return optimizeLibrary(sl.dataset.stlib);
  const ss = t.closest('[data-stseries]');
  if (ss) { const s = S.seriesById[ss.dataset.stseries]; return s && openOptimize({ sel: { series: [s.id] }, books: s.books, title: s.name }); }
  if (t.closest('[data-stall]')) {
    const list = S.storage.biggest.map(x => S.seriesById[x.id]).filter(Boolean);
    return openOptimize({ sel: { series: list.map(s => s.id) }, books: list.flatMap(s => s.books), title: `the ${list.length} biggest` });
  }
  const op = t.closest('.stopen'); if (op) { location.hash = `#/series/${op.dataset.series}`; return; }
  if (t.closest('[data-sttrash]')) { location.hash = '#/trash'; return; }
  const em = t.closest('[data-stempty]');
  if (em) {
    if (!em.classList.contains('armed')) {
      em.classList.add('armed', 'danger'); em.textContent = `Free ${fmtBytes(S.status.trash.bytes)} — can’t be undone`;
      return setTimeout(() => { if (em.isConnected) { em.classList.remove('armed', 'danger'); em.textContent = 'Empty trash'; } }, 4000);
    }
    em.disabled = true;
    jsonFetch('POST', '/api/trash/purge', { all: true }).then(() => { appToast(`Trash emptied — ${fmtBytes(S.status.trash.bytes)} freed`); return load(); }).then(renderStorage).catch(err => appToast(err.message));
    return;
  }
  const dr = t.closest('[data-stdrop]');
  if (dr) {
    if (!dr.classList.contains('armed')) {                         // can't be undone: a second click
      dr.classList.add('armed', 'danger'); dr.textContent = 'Delete — Undo won’t be possible';
      return setTimeout(() => { if (dr.isConnected) { dr.classList.remove('armed', 'danger'); dr.textContent = 'Delete them now'; } }, 4000);
    }
    dr.disabled = true;
    jsonFetch('POST', '/api/optimize/originals/clear').then(r => { appToast(`${plural(r.deleted, 'original')} deleted`); return load(); }).then(renderStorage).catch(err => appToast(err.message));
  }
}
async function storageChange(e) {
  if (!['stNight', 'stFrom', 'stTo'].includes(e.target.id)) return;
  try {
    await jsonFetch('PUT', '/api/optimize/schedule', { on: $('#stNight').checked, from: +$('#stFrom').value, to: +$('#stTo').value,
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone || '', offset: -new Date().getTimezoneOffset() });
  } catch (err) { appToast(err.message); }
  renderStorage(); pollJobs();
}

/* ---------- clicks handled here (the order is in CLICKS, js/06-events.js) ---------- */
function clickStorageNav() { location.hash = '#/storage'; }
