// Offline support: the app itself is cached on first visit, and every chapter
// you open is cached too, so your study Bible keeps working without internet.
const VERSION = "margin-v1";
const SHELL = [
  "./", "index.html", "styles.css", "manifest.webmanifest",
  "js/app.js", "js/bible.js", "js/books.js", "js/ink.js", "js/storage.js",
  "icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png",
];
const BIBLE_HOSTS = ["bolls.life", "api.getbible.net"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (BIBLE_HOSTS.includes(url.hostname)) {
    // Scripture text never changes: cache first.
    e.respondWith(caches.open(VERSION).then(async (c) => {
      const hit = await c.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok) c.put(req, res.clone());
      return res;
    }));
    return;
  }

  if (url.origin === location.origin) {
    // App files: serve from cache instantly, refresh in the background.
    e.respondWith(caches.open(VERSION).then(async (c) => {
      const hit = await c.match(req, { ignoreSearch: true });
      const net = fetch(req).then((res) => { if (res.ok) c.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || net;
    }));
  }
});
