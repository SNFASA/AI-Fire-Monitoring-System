// Name your cache and give it a version number
const CACHE_NAME = 'fire-monitor-v1';

// Hardcode the URLs of the files you want to save offline
const STATIC_ASSETS = [
    '/',
    '/manifest.json',
    '/static/bootstrap/css/bootstrap.min.css',
    '/static/bootstrap/js/bootstrap.bundle.min.js'
    // Add paths to your logos, custom CSS, or offline fallback pages here
];

// 1. INSTALL EVENT: Triggered the first time the user visits the site
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Service Worker: Caching App Shell');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// 2. ACTIVATE EVENT: Triggered when a new version of the SW takes over
self.addEventListener('activate', (event) => {
    // Delete old caches if the CACHE_NAME version changes
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cache) => {
                    if (cache !== CACHE_NAME) {
                        console.log('Service Worker: Clearing Old Cache');
                        return caches.delete(cache);
                    }
                })
            );
        })
    );
});

// 3. FETCH EVENT: Intercepts all network requests from the app
self.addEventListener('fetch', (event) => {
    // Ignore WebSocket connections (your live firefighter alerts)
    if (event.request.url.startsWith('ws://') || event.request.url.startsWith('wss://')) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then((networkResponse) => {
                // If the internet works, return the fresh data
                return networkResponse;
            })
            .catch(() => {
                // If the internet is down, try to serve the file from the cache
                return caches.match(event.request);
            })
    );
});
