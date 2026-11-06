const CACHE_STATIC = 'drp-static-v2';
const CACHE_PAGES  = 'drp-pages-v2';

const STATIC_ASSETS = [
  '/static/offline-visits.js',
  '/static/DRPiscinas2.png',
  '/static/manifest.json',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const staticCache = await caches.open(CACHE_STATIC);
    await staticCache.addAll(STATIC_ASSETS).catch(() => {});
    self.skipWaiting();
  })());
});

// ── Activate ──────────────────────────────────────────────────────────────────
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

  // CDN y assets estáticos → cache-first
  if (url.hostname.includes('jsdelivr') || url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(r => {
        if (r.ok) caches.open(CACHE_STATIC).then(c => c.put(e.request, r.clone()));
        return r;
      }))
    );
    return;
  }

  // Íconos de Bootstrap (font CDN) → cache-first
  if (url.hostname.includes('bootstrapcdn') || url.pathname.includes('/font/')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(r => {
        if (r.ok) caches.open(CACHE_STATIC).then(c => c.put(e.request, r.clone()));
        return r;
      }))
    );
    return;
  }

  // Páginas HTML → network-first, guardar en cache, fallback a cache
  if (e.request.mode === 'navigate' || e.request.headers.get('Accept')?.includes('text/html')) {
    e.respondWith(
      fetch(e.request, { credentials: 'include' }).then(r => {
        if (r.ok) {
          caches.open(CACHE_PAGES).then(c => c.put(e.request, r.clone()));
        }
        return r;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
});

// ── Message handler (cache on demand) ────────────────────────────────────────
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'CACHE_PAGE') {
    caches.open(CACHE_PAGES).then(c =>
      fetch(e.data.url, { credentials: 'include' })
        .then(r => { if (r.ok) c.put(e.data.url, r); })
        .catch(() => {})
    );
  }
});

// ── Push notifications ────────────────────────────────────────────────────────
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
