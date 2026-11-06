const CACHE_STATIC = 'drp-static-v1';
const CACHE_PAGES  = 'drp-pages-v1';

const PRECACHE_STATIC = [
  '/static/DRPiscinas2.png',
  '/static/manifest.json',
  '/static/offline-visits.js',
];

// ── Install: precache static assets ──────────────────────────────────────────
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_STATIC)
      .then(c => c.addAll(PRECACHE_STATIC))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: clean old caches ────────────────────────────────────────────────
self.addEventListener('activate', e => {
  const keep = [CACHE_STATIC, CACHE_PAGES];
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => !keep.includes(k)).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // CDN assets → cache-first (Bootstrap, icons)
  if (url.hostname.includes('jsdelivr') || url.hostname.includes('cdn.')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(r => {
        if (r.ok) caches.open(CACHE_STATIC).then(c => c.put(e.request, r.clone()));
        return r;
      }))
    );
    return;
  }

  // Local static files → cache-first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(r => {
        if (r.ok) caches.open(CACHE_STATIC).then(c => c.put(e.request, r.clone()));
        return r;
      }))
    );
    return;
  }

  // HTML pages → network-first, fallback to cache
  if (e.request.mode === 'navigate' || e.request.headers.get('Accept')?.includes('text/html')) {
    e.respondWith(
      fetch(e.request).then(r => {
        if (r.ok) caches.open(CACHE_PAGES).then(c => c.put(e.request, r.clone()));
        return r;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
});

// ── Push notifications (existing) ────────────────────────────────────────────
self.addEventListener('push', e => {
  let data = { title: 'Dr. Piscinas', body: 'Nueva novedad' };
  try { data = e.data.json(); } catch (_) {}
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/icon-192.png',
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow('/'));
});
