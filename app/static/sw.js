self.addEventListener('install', (e) => {
    console.log('[Dr. Piscinas] Service Worker Instalado');
});

self.addEventListener('fetch', (e) => {});

self.addEventListener('push', (e) => {
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

self.addEventListener('notificationclick', (e) => {
    e.notification.close();
    e.waitUntil(clients.openWindow('/'));
});
