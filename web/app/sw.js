/* The service worker. Network first, always — a stale instrument is worse than a
 * slow one — and the cache is the parachute: everything ever fetched from this
 * origin serves offline, which is the whole app, because the engine is
 * client-side and the API was never load-bearing for making music. */
var V = "oontz-v5";        // v2: ?song= now redirects, so the cached "/" must go; v4: mixer.js joined CORE; v5: app.js split out of index.html
var CORE = ["/", "/app.js", "/copy.js", "/legal.js", "/oontz.js", "/theory.js", "/compose.js",
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
  /* `no-cache` means revalidate, not "do not cache" - it sends the conditional
     request and takes a 304. Without it this "network first" was a lie: the origin
     serves `max-age=60, stale-while-revalidate=86400`, so the plain fetch below was
     answered by the HTTP cache with a copy up to a day old, and then this worker
     wrote that stale copy into its own cache and served it again. A visitor ended up
     running a NEW mixer.js against an OLD engine, which is worse than either. */
  e.respondWith(
    fetch(new Request(e.request, {cache: "no-cache"})).then(function (r) {
      if (r.ok) { var cp = r.clone(); caches.open(V).then(function (c) { c.put(e.request, cp); }); }
      return r;
    }).catch(function () {
      return caches.match(e.request, { ignoreSearch: true }).then(function (m) {
        return m || caches.match("/");                 /* offline deep link: the app shell */
      });
    })
  );
});
