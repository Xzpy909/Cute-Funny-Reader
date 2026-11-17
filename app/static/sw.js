// Cute&Funny Reader — service worker.
// One job: when the browser can't load the page at all (the server is starting, or restarting after
// update.bat), show a "starting" page instead of the browser's own error, and carry on by itself once the
// server answers. Nothing is cached; every other request goes straight to the network as usual.
// (Browsers only allow this on localhost or https — on a plain-http LAN address it simply isn't installed.)
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

const PAGE = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Starting… · Cute&amp;Funny Reader</title><meta name="color-scheme" content="dark">
<style>
  html,body{height:100%;margin:0}
  body{display:grid;place-items:center;background:radial-gradient(120% 90% at 50% 0%,rgba(255,92,138,.16),transparent 60%),#0c0b10;color:#f3f0f7;
    font:500 15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;text-align:center;padding:24px}
  .c{max-width:420px;display:grid;gap:12px;justify-items:center}
  .dot{width:64px;height:64px;border-radius:50%;background:#ff5c8a;box-shadow:0 0 0 0 rgba(255,92,138,.6);animation:p 1.6s infinite}
  @keyframes p{70%{box-shadow:0 0 0 18px rgba(255,92,138,0)}100%{box-shadow:0 0 0 0 rgba(255,92,138,0)}}
  h1{font-size:24px;margin:10px 0 0;letter-spacing:-.02em}
  p{margin:0;color:#a7a2b5}
  .bar{width:220px;height:4px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:6px}
  .bar i{display:block;width:40%;height:100%;border-radius:99px;background:#ffd84d;animation:s 1.4s ease-in-out infinite}
  @keyframes s{0%{transform:translateX(-100%)}100%{transform:translateX(250%)}}
  small{color:#7d7890;min-height:1.5em}
</style></head><body><div class="c"><div class="dot"></div><h1>The reader is starting…</h1>
<p>This page continues by itself as soon as it’s ready — no need to refresh.</p><div class="bar"><i></i></div><small id="t"></small></div>
<script>
  const t0 = Date.now();
  async function check() {
    const s = Math.round((Date.now() - t0) / 1000);
    document.getElementById('t').textContent = s >= 3 ? 'Waiting ' + s + ' s' + (s > 90 ? ' — is Docker Desktop running?' : '') : '';
    try { if ((await fetch('/api/auth/state', { cache: 'no-store' })).ok) return location.reload(); } catch (e) {}
    setTimeout(check, 2000);
  }
  setTimeout(check, 1500);
</script></body></html>`;

self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(fetch(e.request).catch(() => new Response(PAGE, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } })));
});
