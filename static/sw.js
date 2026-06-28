const CACHE_NAME = 'genmon-v3';
const SHELL_ASSETS = [
  '/',
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
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // API calls and dynamic content: network only, never cache
  if (url.pathname.startsWith('/cmd/') || url.pathname.startsWith('/api/')) {
    return;
  }

  // Cache-first with background refresh (stale-while-revalidate) for static
  // assets: serve the cached copy immediately so a flaky/slow network fetch can
  // never leave the page unstyled, while still updating the cache in the
  // background for the next load.
  event.respondWith(
    caches.match(event.request).then(cached => {
      const networkFetch = fetch(event.request).then(response => {
        if (response && response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);
      return cached || networkFetch;
    })
  );
});
