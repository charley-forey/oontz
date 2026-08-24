"""Static server for the oontz landing terminal. No dependencies.

Also the share layer: /t/<song id> and /p/<playlist id> serve index.html with the
track's title, BPM, key and length in the OG tags (so a pasted link previews) and
a boot hook so the page starts playing it. The API base is read from index.html —
that `const API` line is the only place it lives.

Railway builds this service from web/landing alone, so the engine is served from
./engine (a copy of web/app/oontz.js; check.js keeps it identical). In the repo,
where ../app exists, /engine/ is served from there directly.
"""
import os
import re
import sys
import json
import html
import urllib.request
import http.server
import socketserver

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, "..", "app")
PORT = int(os.environ.get("PORT", "8080"))

with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
    INDEX = f.read()
API = re.search(r'const API = "([^"]+)"', INDEX).group(1)
if os.environ.get("OONTZ_API"):                  # a local run pointed at a local API
    INDEX = INDEX.replace(API, os.environ["OONTZ_API"])
    API = os.environ["OONTZ_API"]

SHARE_RE = re.compile(r"^/(t|p)/([A-Za-z0-9_-]{1,40})$")


def mmss(seconds):
    return "%d:%02d" % divmod(int(seconds or 0), 60)


def fetch(path):
    with urllib.request.urlopen(API + path, timeout=2) as r:
        return json.load(r)


def inject(page, title, desc, cmd):
    """index.html with its title and OG tags replaced, and a command run at boot."""
    t, d = html.escape(title, quote=True), html.escape(desc, quote=True)
    page = re.sub(r"<title>.*?</title>", lambda m: "<title>%s — oontz</title>" % t, page, count=1)
    page = re.sub(r'(property="og:title" content=")[^"]*', lambda m: m.group(1) + t, page, count=1)
    page = re.sub(r'(property="og:description" content=")[^"]*', lambda m: m.group(1) + d, page, count=1)
    return page.replace("</head>", "<script>window.OONTZ_BOOT=%s</script></head>" % json.dumps(cmd), 1)


def share(kind, sid):
    """Fail open: if the API is slow or the id is unknown, the plain page."""
    try:
        if kind == "t":
            j = fetch("/songs/" + sid)
            desc = "%d bpm · %s · %s · by %s" % (round(j["bpm"]), j["key"], mmss(j["seconds"]), j["by"])
            cmd = "play " + sid
        else:
            j = fetch("/p/" + sid)
            desc = "%d tracks · %s · by %s" % (len(j["songs"]), mmss(sum(s.get("seconds") or 0 for s in j["songs"])),
                                               j.get("handle") or "someone")
            cmd = "playlist " + sid
        return inject(INDEX, str(j["title"]), desc, cmd)
    except Exception:
        return INDEX


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "public, max-age=60")
        super().end_headers()

    def translate_path(self, path):
        # The committed engine/ copy first. Only a repo checkout (where the copy
        # might be mid-edit) falls through to ../app -- on Railway the deploy
        # root is literally /app, so ROOT/../app is ROOT itself and lies.
        p = super().translate_path(path)
        if path.startswith("/engine/") and not os.path.isfile(p) and os.path.isdir(APP):
            return os.path.join(APP, os.path.basename(p))
        return p

    def send_html(self, body):
        body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        m = SHARE_RE.match(path)
        if m:
            return self.send_html(share(*m.groups()))
        if path == "/" or "." not in os.path.basename(path):
            return self.send_html(INDEX)            # single page, any route
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass                                    # Railway captures stdout; keep it quiet


if sys.argv[1:] == ["check"]:
    out = inject(INDEX, 'a <b> "q"', "140 bpm · <i>", "play x1")
    assert '<title>a &lt;b&gt; &quot;q&quot; — oontz</title>' in out, "title not escaped"
    assert 'property="og:title" content="a &lt;b&gt; &quot;q&quot;"' in out, "og:title"
    assert 'property="og:description" content="140 bpm · &lt;i&gt;"' in out, "og:description"
    assert 'window.OONTZ_BOOT="play x1"</script></head>' in out, "boot hook"
    assert SHARE_RE.match("/t/abc-1") and not SHARE_RE.match("/t/a/b") and not SHARE_RE.match("/t/<x>"), "share ids"
    print("server.py: inject escapes, boot hook set, share ids validated")
    sys.exit(0)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print("landing on :%d  api %s" % (PORT, API), flush=True)
    httpd.serve_forever()
