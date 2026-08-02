const CACHE_NAME = 'genmon-v4';
// Core assets kept for offline use only. Navigation/HTML is intentionally NOT
// listed here so login/auth pages are never served stale from the cache.
const SHELL_ASSETS = [
  '/css/genmon.css',
  '/js/genmon.js',
  '/js/addon-icons.js',
  '/favicon.ico',
  '/icons/icon-192x192.png',
  '/icons/icon-512x512.png',
  '/manifest.webmanifest'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  // Never intercept navigations/documents: HTML must always come from the
  // network so login and auth state are never served stale from the cache.
  if (req.mode === 'navigate' || req.destination === 'document') return;

  const url = new URL(req.url);
  // API calls and dynamic content: network only, never cache.
  if (url.pathname.startsWith('/cmd/') || url.pathname.startsWith('/api/')) return;

  // Network-first for static assets: always try a fresh copy, and fall back to
  // the cache only when the network is unavailable (offline resilience).
  event.respondWith(
    fetch(req).then(response => {
      if (response && response.ok) {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
      }
      return response;
    }).catch(() => caches.match(req))
  );
});
