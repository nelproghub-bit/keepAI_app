// KeepAI service worker for Progressive Web App (PWA)
const CACHE_NAME = 'keepai-pwa-navy-teal-__APP_VERSION__';

const STATIC_ASSETS = [
  './',
  './index.html',
  './student_login.html',
  './student_dashboard.html',
  './admin_dashboard.html',
  './admin-manifest.json',
  './admin_panel.html',
  './manifest.json',
  './icons/favicon-32.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-192.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png',
  './assets/css/responsive-layouts.css',
  './assets/css/landing.css',
  './assets/css/brand-theme.css',
  './assets/css/design-system.css',
  './assets/css/onboarding-tour.css',
  './assets/js/landing.js',
  './assets/js/push-notifications.js',
  './assets/js/onboarding-tour.js',
  './assets/images/keepai-logo.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(err => {
        console.warn('[KeepAI PWA Service Worker] Partial cache during install:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('push', event => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    console.error('[KeepAI Push] Could not parse notification payload:', error);
  }

  const title = typeof payload.title === 'string' && payload.title
    ? payload.title
    : 'KeepAI notification';
  const options = {
    body: typeof payload.body === 'string' ? payload.body : 'You have a new KeepAI announcement.',
    icon: './icons/icon-192.png',
    badge: './icons/icon-192.png',
    tag: typeof payload.tag === 'string' ? payload.tag : 'keepai-notification',
    data: { url: typeof payload.url === 'string' ? payload.url : './student_dashboard.html' }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const requestedUrl = new URL(
    event.notification.data?.url || './student_dashboard.html?showNotifications=1',
    self.location.origin
  );
  const targetUrl = requestedUrl.origin === self.location.origin
    ? requestedUrl.href
    : new URL('./student_dashboard.html?showNotifications=1', self.location.origin).href;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (const client of windowClients) {
        if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
          return client.navigate(targetUrl).then(() => client.focus());
        }
      }
      return clients.openWindow(targetUrl);
    })
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // Never cache backend API calls, runtime config, or non-GET requests
  if (
    url.pathname.includes('/api/')
    || url.pathname.endsWith('/assets/js/config.js')
    || req.method !== 'GET'
  ) {
    return;
  }

  // Navigation requests (HTML pages): Network-first with cache fallback
  if (req.mode === 'navigate' || req.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(req, { cache: 'no-cache' })
        .then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
          }
          return networkResponse;
        })
        .catch(() => {
          return caches.match(req, { ignoreSearch: true }).then(cached => {
            if (cached) return cached;
            return caches.match('./student_login.html') || caches.match('./student_dashboard.html');
          });
        })
    );
    return;
  }

  // Static assets (CSS, JS, Fonts, Images): Cache-first with network fallback
  event.respondWith(
    caches.match(req).then(cachedResponse => {
      if (cachedResponse) {
        // Fetch in background to update cache for next time
        fetch(req).then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then(cache => cache.put(req, networkResponse));
          }
        }).catch(() => {});
        return cachedResponse;
      }

      return fetch(req).then(networkResponse => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
        }
        return networkResponse;
      }).catch(err => {
        return new Response('', { status: 408, statusText: 'Offline' });
      });
    })
  );
});
