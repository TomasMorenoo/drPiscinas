const CACHE_STATIC = 'drp-static-v4';
const CACHE_PAGES  = 'drp-pages-v4';

const STATIC_ASSETS = [
  '/static/offline-visits.js',
  '/static/DRPiscinas2.png',
  '/static/manifest.json',
  '/static/drpiscina-192.png',
  '/static/drpiscina-512.png',
  '/static/drpiscina-local-192.png',
  '/static/drpiscina-local-512.png',
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

  // Páginas HTML → network-first, guardar en cache, fallback inteligente a cache
  if (e.request.mode === 'navigate' || e.request.headers.get('Accept')?.includes('text/html')) {
    e.respondWith(
      fetch(e.request, { credentials: 'include' }).then(r => {
        if (r.ok) {
          caches.open(CACHE_PAGES).then(c => c.put(e.request, r.clone()));
        }
        return r;
      }).catch(async () => {
        const pagesCache = await caches.open(CACHE_PAGES);

        // 1. Match exacto
        let cached = await pagesCache.match(e.request, { ignoreSearch: true });
        if (cached) return cached;

        // 2. Probar con o sin barra final (/visits <-> /visits/)
        const reqUrl = new URL(e.request.url);
        const altPath = reqUrl.pathname.endsWith('/')
          ? reqUrl.pathname.slice(0, -1)
          : (reqUrl.pathname + '/');
        cached = await pagesCache.match(altPath, { ignoreSearch: true });
        if (cached) return cached;

        // 3. Fallback: si es algo de visitas, devolver /visits/ o /visits/create
        if (reqUrl.pathname.startsWith('/visits')) {
          cached = await pagesCache.match('/visits/', { ignoreSearch: true });
          if (cached) return cached;
          cached = await pagesCache.match('/visits', { ignoreSearch: true });
          if (cached) return cached;
          cached = await pagesCache.match('/visits/create', { ignoreSearch: true });
          if (cached) return cached;
        }

        // 4. Fallback final a home o cualquier cosa en cache
        return (await pagesCache.match('/', { ignoreSearch: true })) || (await caches.match(e.request));
      })
    );
    return;
  }
});

// ── Message handler ───────────────────────────────────────────────────────────
self.addEventListener('message', e => {
  if (!e.data) return;

  if (e.data.type === 'CACHE_PAGE') {
    caches.open(CACHE_PAGES).then(c =>
      fetch(e.data.url, { credentials: 'include' })
        .then(r => { if (r.ok) c.put(e.data.url, r); })
        .catch(() => {})
    );
  }

  if (e.data.type === 'CACHE_ALL') {
    caches.open(CACHE_PAGES).then(c => {
      e.data.urls.forEach(url => {
        fetch(url, { credentials: 'include' })
          .then(r => { if (r.ok) c.put(url, r); })
          .catch(() => {});
      });
    });
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
