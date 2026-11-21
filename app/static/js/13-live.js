'use strict';
/* ======================= LIVE: one jobs store, fed by the server's event stream =======================
   GET /api/events (Server-Sent Events) sends every job change and "the library changed". Everything that shows
   background work reads this one store: the working pill (moves, deletes, scans, the trash mover), the Jobs
   panel (✨ Optimize) and the reader's JPEG XL / HEIC conversion. If the stream can't connect (some reverse
   proxies hold it back), the same store is filled by polling instead. Design: docs/JOBS.md. */
const LIVE = { jobs: new Map(), es: null, ok: false, failures: 0, pollT: null, subs: new Set(), libT: null, stale: false, optT: null };
const FINISHED = ['done', 'failed', 'cancelled'];

function liveStart() {
  liveStop();
  if (!S.me) return;
  if (!window.EventSource) return livePoll();
  const es = LIVE.es = new EventSource('/api/events');
  const giveUp = setTimeout(() => { if (!LIVE.ok) { liveStop(); livePoll(); } }, 10000);   // never opened: poll instead
  es.onopen = () => { LIVE.ok = true; LIVE.failures = 0; clearTimeout(LIVE.pollT); clearTimeout(giveUp); };
  es.onmessage = e => { let ev; try { ev = JSON.parse(e.data); } catch { return; } liveEvent(ev); };
  es.onerror = () => {
    LIVE.ok = false;
    if (++LIVE.failures >= 3) { liveStop(); livePoll(); }     // keeps failing: poll (and try the stream again later)
    else refreshStatus();                                     // the server may be away: that shows the "Reconnecting…" screen
  };
}
function liveStop() {
  if (LIVE.es) { LIVE.es.close(); LIVE.es = null; }
  LIVE.ok = false; clearTimeout(LIVE.pollT);
}
// the fallback: the same store, filled every few seconds (faster while something runs); the stream is tried again
async function livePoll() {
  clearTimeout(LIVE.pollT);
  if (!S.me) return;
  try { const d = await api.get('/api/jobs'); liveEvent({ type: 'hello', jobs: d.jobs }); pollJobs(d); } catch {}
  const busy = [...LIVE.jobs.values()].some(j => !FINISHED.includes(j.state) && !j.waiting);
  LIVE.pollT = setTimeout(() => (++LIVE.failures % 10 === 0 ? liveStart() : livePoll()), busy ? 1500 : 6000);
}

function liveEvent(ev) {
  if (ev.type === 'hello') {
    LIVE.jobs = new Map(ev.jobs.map(j => [j.id, j]));
    if (ev.rev != null && S.status && ev.rev !== S.status.rev) liveLibrary();
    liveChanged(null);
  } else if (ev.type === 'job') {
    const j = ev.job;
    if (j.gone) LIVE.jobs.delete(j.id); else LIVE.jobs.set(j.id, { ...LIVE.jobs.get(j.id), ...j });
    liveChanged(LIVE.jobs.get(j.id) || j);
  } else if (ev.type === 'library') liveLibrary();
}
// the library changed on the server: reload what the page shows (soon, and not while you're busy with it)
function liveLibrary() {
  clearTimeout(LIVE.libT);
  LIVE.libT = setTimeout(() => {
    if (document.hidden || document.body.classList.contains('reading') || S.sel || $('.overlay.open, #menu.on')) { LIVE.stale = true; return; }
    LIVE.stale = false; refreshStatus();
  }, 400);
}
function liveChanged(j) {
  for (const fn of LIVE.subs) { try { fn(j); } catch (e) { console.error(e); } }
  liveBackground();
  if (LIVE.ok && (!j || j.kind === 'optimize')) { clearTimeout(LIVE.optT); LIVE.optT = setTimeout(() => pollJobs(), 1000); }   // the Jobs panel (its own shape)
}
const liveOn = fn => { LIVE.subs.add(fn); return () => LIVE.subs.delete(fn); };
// the next change of a job that `want(job)` picks — or null after `ms`
function liveNext(want, ms) {
  return new Promise(resolve => {
    const t = setTimeout(() => { off(); resolve(null); }, ms);
    const off = liveOn(j => { if (j && want(j)) { clearTimeout(t); off(); resolve(j); } });
  });
}

// wait for a job to finish; `each(job)` on every change. Resolves with the last state seen.
function liveWait(id, each = () => {}) {
  return new Promise(resolve => {
    let last = LIVE.jobs.get(id) || { id, state: 'queued' }, t = null;
    const fin = j => { off(); clearTimeout(t); resolve(j); };
    const off = liveOn(j => {
      if (j && j.id !== id) return;
      const cur = LIVE.jobs.get(id);
      if (!cur) return fin(last);                            // dismissed meanwhile
      last = cur; each(cur);
      if (FINISHED.includes(cur.state)) fin(cur);
    });
    if (FINISHED.includes(last.state)) return fin(last);
    each(last);
    // a stream that's down, or an update lost on the way: look at the job itself now and then
    const check = async () => {
      try {
        const r = await _fetch(`/api/jobs/${id}`);
        if (r.status === 404) return fin(last);
        if (r.ok) { const j = await r.json(); LIVE.jobs.set(id, j); liveChanged(j); if (FINISHED.includes(j.state)) return; }
      } catch {}
      t = setTimeout(check, LIVE.ok ? 5000 : 700);
    };
    t = setTimeout(check, LIVE.ok ? 5000 : 700);
  });
}

// work nobody is waiting for right now (a scan, the trash mover, someone's long move in another tab) shows in
// the working pill while nothing in the foreground does
function liveBackground() {
  const reading = document.body.classList.contains('reading');
  const bg = [...LIVE.jobs.values()].find(j => j.state === 'running' && j.kind !== 'optimize' && j.id !== WORK.job?.id
    && !(reading && j.kind === 'transcode'));
  WORK.bg = bg || null;
  const el = workEl();
  if (WORK.n === 0) {
    if (bg && !el.classList.contains('on')) { WORK.label = bg.title; WORK.start = performance.now(); el.classList.add('on'); }
    else if (!bg && el.classList.contains('on') && !WORK.job) el.classList.remove('on');
    if (bg) WORK.label = bg.title;
  }
  workPaint();
}
