'use strict';
/* Cute&Funny Reader — frontend, part 10 of 11: the video player, accounts, the trash.
   The parts are plain scripts sharing one global scope, loaded in file-name order (index.html). */

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
  renderAcct(); load(); syncSeriesPrefs();
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
    <div class="msep"></div><button data-acct="out" class="danger">${ico('logout', 17)} Sign out</button>`;
  m.classList.add('on'); m.classList.remove('busy'); $('#menuShade').classList.add('on'); placeMenu();
});
$('#menu').addEventListener('click', async e => {
  const a = e.target.closest('[data-acct]')?.dataset.acct; if (!a) return;
  closeMenu();
  if (a === 'out') { await _fetch('/api/auth/logout', { method: 'POST' }); location.hash = '#/'; return showAuth(false); }
  if (a === 'pw') return openPw();
  if (a === 'manage') return openAccounts();
});
