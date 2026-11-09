// FINN's service worker: the app shell and the last answers from FINN's server, so the
// phone still opens to what FINN last showed when the network is gone.
//   - static assets (/_next/static, fonts, icons): cache first (their names are content-hashed)
//   - pages and API reads, including the POST /digest and /alerts reads: network first,
//     falling back to the last good copy, marked with an x-finn-offline header
const VERSION = "finn-v1";
const STATIC = `${VERSION}-static`;
const DATA = `${VERSION}-data`;
const API_READS = ["/digest", "/alerts", "/portfolio", "/research", "/results/", "/health"];

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) {
        if (!key.startsWith(VERSION)) await caches.delete(key);
      }
      await self.clients.claim();
    })(),
  );
});

const isStatic = (url) =>
  url.origin === self.location.origin &&
  (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/") || url.pathname.endsWith(".woff2"));

const isApiRead = (url, req) =>
  url.origin !== self.location.origin &&
  API_READS.some((p) => url.pathname === p || url.pathname.startsWith(p)) &&
  !url.pathname.endsWith("/build") && // live builds stream; never cache them
  (req.method === "GET" || (req.method === "POST" && (url.pathname === "/digest" || url.pathname === "/alerts")));

/** POST bodies become part of a synthetic GET key, since the Cache API stores GETs only. */
async function cacheKey(req) {
  if (req.method === "GET") return req.url;
  const body = await req.clone().text();
  return `${req.url}?finn-body=${encodeURIComponent(body)}`;
}

async function cacheFirst(req) {
  const hit = await caches.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) (await caches.open(STATIC)).put(req, res.clone());
  return res;
}

async function networkFirst(req, key) {
  const cache = await caches.open(DATA);
  try {
    const res = await fetch(req);
    if (res.ok) {
      const copy = res.clone();
      const headers = new Headers(copy.headers);
      headers.set("x-finn-saved", new Date().toISOString());
      await cache.put(key, new Response(await copy.blob(), { status: copy.status, headers }));
    }
    return res;
  } catch (err) {
    const hit = await cache.match(key);
    if (!hit) throw err;
    const headers = new Headers(hit.headers);
    headers.set("x-finn-offline", hit.headers.get("x-finn-saved") ?? "");
    return new Response(await hit.blob(), { status: 200, headers });
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (isStatic(url) && req.method === "GET") {
    event.respondWith(cacheFirst(req));
  } else if (req.mode === "navigate") {
    event.respondWith(networkFirst(req, req.url));
  } else if (isApiRead(url, req)) {
    event.respondWith(cacheKey(req).then((key) => networkFirst(req, key)));
  }
});
