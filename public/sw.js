// App-shell cache only. Stock, reservations and everything else under /api/
// is live data -- serving it from a cache would show a customer a "held"
// item that already sold, so those requests are never intercepted here.
// Bump this whenever the shell (HTML/CSS/JS) changes. The fetch handler is
// stale-while-revalidate, so without a new name an already-installed app
// serves the previous version once more before picking the update up; a new
// name makes install fetch a fresh shell and activate drop the old one.
const CACHE = 'showcase-v6';

const SHELL = [
  '/',
  '/css/app.css',
  '/js/app.js',
  '/js/api.js',
  '/js/state.js',
  '/js/ui.js',
  '/js/views/customer.js',
  '/js/views/store.js',
  '/images/stage.jpg',
  '/images/offline.png',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only ever cache same-origin GETs. Live API calls and anything cross-origin
  // pass straight through to the network, untouched.
  if (request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) {
    return;
  }

  // Stale-while-revalidate: an already-cached shell answers instantly (this
  // is what makes the app open like a native one on a flaky connection), and
  // every fetch quietly refreshes the cache behind it so updates still land.
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(request);
      const network = fetch(request)
        .then((response) => {
          if (response && response.ok) cache.put(request, response.clone());
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
