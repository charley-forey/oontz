/* The service worker. Network first, always — a stale instrument is worse than a
 * slow one — and the cache is the parachute: everything ever fetched from this
 * origin serves offline, which is the whole app, because the engine is
 * client-side and the API was never load-bearing for making music. */
var V = "oontz-v3";        // v2: ?song= now redirects, so the cached "/" must go
var CORE = ["/", "/copy.js", "/legal.js", "/oontz.js", "/theory.js", "/compose.js",
            "/viz.js", "/account.js", "/touch.js", "/mixer.js", "/midi.js", "/track.js", "/icon.svg",
            "/manifest.webmanifest"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(V).then(function (c) { return c.addAll(CORE); })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== V; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request).then(function (r) {
      if (r.ok) { var cp = r.clone(); caches.open(V).then(function (c) { c.put(e.request, cp); }); }
      return r;
    }).catch(function () {
      return caches.match(e.request, { ignoreSearch: true }).then(function (m) {
        return m || caches.match("/");                 /* offline deep link: the app shell */
      });
    })
  );
});
