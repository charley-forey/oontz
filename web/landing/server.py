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
API = re.search(r'(?:const|var) API = "([^"]+)"', INDEX).group(1)
if os.environ.get("OONTZ_API"):                  # a local run pointed at a local API
    INDEX = INDEX.replace(API, os.environ["OONTZ_API"])
    API = os.environ["OONTZ_API"]

SHARE_RE = re.compile(r"^/(t|p)/([A-Za-z0-9_-]{1,40})$")


def mmss(seconds):
    return "%d:%02d" % divmod(int(seconds or 0), 60)


API_FALLBACK = "https://api-production-68c09.up.railway.app"

def fetch(path):
    """The custom API domain can be edge-dead; fall back to the railway.app host
    so server-rendered share cards keep working when it is."""
    for host in (API, API_FALLBACK):
        try:
            with urllib.request.urlopen(host + path, timeout=2) as r:
                return json.load(r)
        except Exception:
            continue
    raise RuntimeError("no API host answered")


def inject(page, title, desc, cmd, og=None, watch=False):
    """index.html with its title and OG tags replaced, and a command run at boot."""
    t, d = html.escape(title, quote=True), html.escape(desc, quote=True)
    page = re.sub(r"<title>.*?</title>", lambda m: "<title>%s — oontz</title>" % t, page, count=1)
    page = re.sub(r'(property="og:title" content=")[^"]*', lambda m: m.group(1) + t, page, count=1)
    page = re.sub(r'(property="og:description" content=")[^"]*', lambda m: m.group(1) + d, page, count=1)
    if og:
        page = page.replace("</head>", '<meta property="og:image" content="%s">'
                            '<meta name="twitter:card" content="summary_large_image"></head>'
                            % html.escape(og, quote=True), 1)
    boot = "window.OONTZ_BOOT=%s;window.OONTZ_WATCH=%s" % (json.dumps(cmd), "true" if watch else "false")
    return page.replace("</head>", "<script>%s</script></head>" % boot, 1)


def share(kind, sid, watch=False):
    """Fail open: if the API is slow or the id is unknown, the plain page."""
    try:
        if kind == "t":
            j = fetch("/songs/" + sid)
            desc = "%d bpm · %s · %s · by %s" % (round(j["bpm"]), j["key"], mmss(j["seconds"]), j["by"])
            return inject(INDEX, str(j["title"]), desc, "play " + sid,
                          og="/og/" + sid + ".svg", watch=watch)
        else:
            j = fetch("/p/" + sid)
            desc = "%d tracks · %s · by %s" % (len(j["songs"]), mmss(sum(s.get("seconds") or 0 for s in j["songs"])),
                                               j.get("handle") or "someone")
            cmd = "playlist " + sid
        return inject(INDEX, str(j["title"]), desc, cmd)
    except Exception:
        return INDEX


def og_svg(sid):
    """A share card drawn FROM the song: title, the numbers, and the real kick
    and hat patterns as a 16-step strip. Fail open to a plain brand card."""
    W, H = 1200, 630
    title, sub, kick, hat = "oontz", "source code for music", "x...x...x...x...", "..x...x...x...x."
    try:
        j = fetch("/songs/" + sid)
        title = str(j["title"])[:40]
        sub = "%d bpm · %s · %s · by %s" % (round(j["bpm"]), j["key"], mmss(j["seconds"]), j["by"])
        secs = j.get("data", {}).get("sections", {})
        order = j.get("data", {}).get("order", [])
        for n in order:
            tr = (secs.get(n) or {}).get("tracks", {})
            if tr.get("kick", {}).get("pat"):
                kick = tr["kick"]["pat"]
                hat = (tr.get("hat") or {}).get("pat") or hat
                if (secs.get(n) or {}).get("role") == "drop":
                    break
    except Exception:
        pass

    def strip(pat, y, color):
        cells = []
        for i in range(16):
            ch = pat[i % len(pat)] if pat else "."
            on = ch not in (".", "-")
            x = 80 + i * 66
            fill = color if on else "#1b232b"
            cells.append('<rect x="%d" y="%d" width="52" height="52" rx="8" fill="%s"/>' % (x, y, fill))
        return "".join(cells)

    e = lambda s: html.escape(str(s), quote=True)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H) +
        '<rect width="%d" height="%d" fill="#07090b"/>' % (W, H) +
        '<text x="80" y="150" font-family="ui-monospace,Menlo,Consolas,monospace" font-size="88" '
        'font-weight="700" fill="#f4f9fc">%s</text>' % e(title) +
        '<text x="80" y="210" font-family="ui-monospace,Menlo,Consolas,monospace" font-size="34" '
        'fill="#46545f">%s</text>' % e(sub) +
        '<text x="80" y="330" font-family="ui-monospace,monospace" font-size="30" fill="#ff3b3b">kick</text>' +
        strip(kick, 300, "#ff3b3b") +
        '<text x="80" y="430" font-family="ui-monospace,monospace" font-size="30" fill="#22e0d0">hat</text>' +
        strip(hat, 400, "#22e0d0") +
        '<text x="80" y="560" font-family="ui-monospace,monospace" font-size="30" fill="#46545f">'
        'the whole song is this readable. oontz.sh</text>' +
        '</svg>')
    return svg.encode("utf-8")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map,
                          **{".webmanifest": "application/manifest+json"})
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
        path, _, query = self.path.partition("?")
        if path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        ogm = re.match(r"^/og/([A-Za-z0-9_-]{1,40})\.svg$", path)
        if ogm:
            body = og_svg(ogm.group(1))
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers(); self.wfile.write(body); return
        m = SHARE_RE.match(path)
        if m:
            return self.send_html(share(*m.groups(), watch=("watch=1" in query)))
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
    assert 'window.OONTZ_BOOT="play x1"' in out, "boot hook"
    card = og_svg("nope")
    assert card.startswith(b"<svg") and b"oontz" in card, "og card renders"
    wout = inject(INDEX, "t", "d", "play x", watch=True)
    assert "window.OONTZ_WATCH=true" in wout, "watch flag set"
    assert SHARE_RE.match("/t/abc-1") and not SHARE_RE.match("/t/a/b") and not SHARE_RE.match("/t/<x>"), "share ids"
    print("server.py: inject escapes, boot hook set, share ids validated")
    sys.exit(0)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print("landing on :%d  api %s" % (PORT, API), flush=True)
    httpd.serve_forever()
