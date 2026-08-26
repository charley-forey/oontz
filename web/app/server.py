"""Static server for the oontz landing terminal.

Vercel is the intended host, but this keeps the site deployable anywhere that can
run Python, which is what got it live the day the Vercel free tier ran out of
deployments. No dependencies.
"""
import os
import re
import http.server
import socketserver

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8080"))
SITE_URL = os.environ.get("OONTZ_SITE_URL", "https://oontz.music").rstrip("/")
SONG_Q = re.compile(r"(?:^|&)song=([A-Za-z0-9_-]{1,40})(?:&|$)")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map,
                          **{".webmanifest": "application/manifest+json"})
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def send_header(self, key, value):
        self.__dict__.setdefault("_sent", {})[key.lower()] = str(value)
        super().send_header(key, value)

    def end_headers(self):
        sent = self.__dict__.pop("_sent", {})        # handlers are reused per request
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Permissions-Policy",
                         "geolocation=(), camera=(), microphone=()")
        # frame-ancestors, not X-Frame-Options: DENY - browsergate drives this page
        # inside an iframe, and DENY would fail the gate rather than an attacker.
        # ponytail: no script-src/connect-src here. pyodide needs unsafe-eval and
        # jsdelivr, gtag is third-party, and the API has a hardcoded failover host -
        # a script-src that covers all three protects nothing. Tighten it the day
        # gtag goes and pyodide is vendored; the escaping in esc() is what actually
        # closes the injection path.
        self.send_header("Content-Security-Policy",
                         "object-src 'none'; base-uri 'self'; "
                         "frame-ancestors 'self'; form-action 'self'")
        # One blanket max-age=60 sat on 220KB of JS that only changes on a deploy,
        # so every visitor re-downloaded the whole instrument once a minute - and it
        # capped Railway's CDN at 60s too, since the edge honours the origin's
        # max-age over its own TTL. stale-while-revalidate is the fix: browser and
        # edge both serve the cached copy INSTANTLY and refresh behind the reader,
        # so a stale asset survives exactly one load. The shell stays no-cache
        # because it names the asset URLs, and skew between the two is what a stale
        # instrument actually looks like.
        if "cache-control" not in sent:              # a handler may set its own
            html = sent.get("content-type", "").startswith("text/html")
            self.send_header("Cache-Control", "no-cache" if html else
                             "public, max-age=60, stale-while-revalidate=86400")
        super().end_headers()

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        path, _, query = self.path.partition("?")
        # ?song=<id> is the instrument, which carries no social tags and cannot ever
        # preview. The share page does. Every such link already pasted anywhere in the
        # world starts working the moment this redirect exists; the app's own deep link
        # is #song=<id>, which is a fragment and never reaches here.
        m = SONG_Q.search(query) if path == "/" else None
        if m:
            self.send_response(302)
            self.send_header("Location", "%s/t/%s" % (SITE_URL, m.group(1)))
            self.end_headers()
            return
        if path == "/" or ("." not in os.path.basename(path) and not path.endswith("/")):
            self.path = "/index.html"          # single page, any route
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass                                    # Railway captures stdout; keep it quiet


import sys
if sys.argv[1:] == ["check"]:
    assert SONG_Q.search("song=abc123").group(1) == "abc123", "plain"
    assert SONG_Q.search("x=1&song=a-b_C").group(1) == "a-b_C", "after another param"
    assert SONG_Q.search("song=abc&z=1").group(1) == "abc", "before another param"
    assert not SONG_Q.search("songs=abc"), "must not match a different param"
    assert not SONG_Q.search("song=<script>"), "id charset is bounded"
    print("app server.py: ?song= redirects to %s/t/<id>" % SITE_URL)
    sys.exit(0)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print("landing on :%d" % PORT, flush=True)
    httpd.serve_forever()
