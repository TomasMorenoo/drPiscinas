self.addEventListener('install', (e) => {
    console.log('[Service Worker] Instalado');
});

self.addEventListener('fetch', (e) => {
    // No cacheamos nada para que tu sistema siempre muestre los datos reales y frescos de la base de datos
    e.respondWith(fetch(e.request));
});