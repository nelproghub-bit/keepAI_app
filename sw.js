// KeepAI service worker for Progressive Web App (PWA)
const CACHE_NAME = 'keepai-pwa-__APP_VERSION__';

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
  './assets/css/onboarding-tour.css',
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
      fetch(req)
        .then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
          }
          return networkResponse;
        })
        .catch(() => {
          return caches.match(req).then(cached => {
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
