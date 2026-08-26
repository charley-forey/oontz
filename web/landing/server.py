"""Static server for the oontz landing terminal. No dependencies.

Also the share layer: /t/<song id> and /p/<playlist id> serve index.html with the
track's title, BPM, key and length in the OG tags (so a pasted link previews) and
a boot hook so the page starts playing it. The API base is read from index.html —
that `const API` line is the only place it lives.

Railway builds this service from web/landing alone, so the engine is served from
./engine (a copy of web/app/oontz.js; check.js keeps it identical). In the repo,
where ../app exists, /engine/ is served from there directly.
"""
import functools
import os
import re
import time
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

with open(os.path.join(ROOT, "language.html"), encoding="utf-8") as f:
    LANGUAGE = f.read()          # the research article, served whole at /language

# Every social tag must be an ABSOLUTE url; crawlers do not resolve relative ones.
SITE_URL = os.environ.get("OONTZ_SITE_URL", "https://oontz.music").rstrip("/")

import png                                       # the stdlib card renderer

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


def _meta(page, kind, name, value):
    """Rewrite one <meta> in place. kind is 'property' (og:*) or 'name' (twitter:*)."""
    pat = r'(%s="%s" content=")[^"]*' % (kind, re.escape(name))
    return re.sub(pat, lambda m: m.group(1) + html.escape(value, quote=True), page, count=1)


def inject(page, title, desc, cmd, og=None, url=None, alt=None, meta=None, watch=False):
    """index.html with its title and social tags replaced, and a command run at boot.

    One table, not a regex per tag. The old shape had a hand-written substitution for
    each of three tags and appended og:image only when a caller passed one - which is
    exactly how twitter:*, og:url and the whole playlist card came to be missing for
    months. Every tag now exists in the HTML and is rewritten here, so adding one is a
    row and forgetting one is impossible.
    """
    page = re.sub(r"<title>.*?</title>",
                  lambda m: "<title>%s — oontz</title>" % html.escape(title, quote=True),
                  page, count=1)
    img = og or (SITE_URL + "/og/brand.png")
    for kind, name, val in (("property", "og:title", title),
                            ("name", "twitter:title", title),
                            ("property", "og:description", desc),
                            ("name", "twitter:description", desc),
                            ("property", "og:url", url or (SITE_URL + "/")),
                            ("property", "og:image", img),
                            ("name", "twitter:image", img),
                            ("property", "og:image:alt", alt or "oontz")):
        page = _meta(page, kind, name, val)
    # the receiver shows what it is before the API answers a second time
    boot = "window.OONTZ_BOOT=%s;window.OONTZ_WATCH=%s;window.OONTZ_META=%s" % (
        json.dumps(cmd), "true" if watch else "false", json.dumps(meta or {}))
    return page.replace("</head>", "<script>%s</script></head>" % boot, 1)


def share(kind, sid, watch=False):
    """Fail open: if the API is slow or the id is unknown, the plain page."""
    try:
        if kind == "t":
            j = fetch("/songs/" + sid)
            desc = "%d bpm · %s · %s · by %s" % (round(j["bpm"]), j["key"], mmss(j["seconds"]), j["by"])
            return inject(INDEX, str(j["title"]), desc, "play " + sid,
                          og=SITE_URL + "/og/" + sid + ".png",
                          url=SITE_URL + "/t/" + sid,
                          alt="%s — %s" % (j["title"], desc),
                          meta={"title": str(j["title"]), "sub": desc, "id": sid},
                          watch=watch)
        # A playlist used to fall through to a call with no og= at all, so a shared
        # playlist had no card and no twitter tags. It gets both now.
        j = fetch("/p/" + sid)
        desc = "%d tracks · %s · by %s" % (len(j["songs"]), mmss(sum(s.get("seconds") or 0 for s in j["songs"])),
                                           j.get("handle") or "someone")
        return inject(INDEX, str(j["title"]), desc, "playlist " + sid,
                      og=SITE_URL + "/og/p/" + sid + ".png",
                      url=SITE_URL + "/p/" + sid,
                      alt="%s — %s" % (j["title"], desc),
                      meta={"title": str(j["title"]), "sub": desc, "id": sid})
    except Exception:
        return INDEX


def _card_data(sid):
    """What the card says, pulled from the song itself. Fail open to the brand card.

    This is the extraction the SVG card always did - the first section that has a
    kick, preferring the drop - kept verbatim. Only the pixels changed.
    """
    title, sub = "oontz", "source code for music"
    kick, hat = "x...x...x...x...", "..x...x...x...x."
    try:
        j = fetch("/songs/" + sid)
        title = str(j["title"])[:40]
        sub = "%d bpm · %s · %s · by %s" % (round(j["bpm"]), j["key"], mmss(j["seconds"]), j["by"])
        secs = j.get("data", {}).get("sections", {})
        for n in j.get("data", {}).get("order", []):
            tr = (secs.get(n) or {}).get("tracks", {})
            if tr.get("kick", {}).get("pat"):
                kick = tr["kick"]["pat"]
                hat = (tr.get("hat") or {}).get("pat") or hat
                if (secs.get(n) or {}).get("role") == "drop":
                    break
    except Exception:
        pass
    return title, sub, kick, hat


def _playlist_card_data(pid):
    """A playlist's card borrows the drums of its first track."""
    title, sub = "oontz", "a playlist"
    kick, hat = "x...x...x...x...", "..x...x...x...x."
    try:
        j = fetch("/p/" + pid)
        title = str(j["title"])[:40]
        sub = "%d tracks · %s · by %s" % (
            len(j["songs"]), mmss(sum(s.get("seconds") or 0 for s in j["songs"])),
            j.get("handle") or "someone")
        if j["songs"]:
            _t, _s, kick, hat = _card_data(j["songs"][0]["id"])
    except Exception:
        pass
    return title, sub, kick, hat


@functools.lru_cache(maxsize=256)
def og_png(sid, kind="t", _bucket=0):
    """The share card as a PNG. _bucket expires the cache without a timer."""
    data = _playlist_card_data(sid) if kind == "p" else _card_data(sid)
    return png.card(*data)


def card_png(sid, kind="t"):
    return og_png(sid, kind, int(time.time() // 600))     # 10-minute TTL


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
        # An .svg card is what shipped before, and crawlers cache hard. Send anyone
        # holding the old address to the one their renderer can actually read.
        oldm = re.match(r"^/og/(?:p/)?([A-Za-z0-9_-]{1,40})\.svg$", path)
        if oldm:
            self.send_response(301)
            self.send_header("Location", path[:-4] + ".png")
            self.end_headers(); return
        ogm = re.match(r"^/og/(p/)?([A-Za-z0-9_-]{1,40})\.png$", path)
        if ogm:
            kind = "p" if ogm.group(1) else "t"
            body = card_png(ogm.group(2), kind)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers(); self.wfile.write(body); return
        m = SHARE_RE.match(path)
        if m:
            return self.send_html(share(*m.groups(), watch=("watch=1" in query)))
        # The article is its own document, not the terminal booted into a command:
        # it is meant to be linked, read, cited and printed, so it carries its own
        # <head> and social tags and inject() does not touch it.
        if path.strip("/") == "language":
            return self.send_html(LANGUAGE)
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
    assert png.demo(), "png self-check"
    card = card_png("nope")                      # a dead id must still make a card
    assert card[1:4] == b"PNG" and len(card) > 1000, "og card renders"
    # every social tag has to exist in the page AND come out absolute, or the
    # crawler ignores it - the two failures this card spent months behind
    for tag in ('property="og:url"', 'property="og:image"', 'name="twitter:image"',
                'name="twitter:title"', 'name="twitter:card"', 'property="og:type"',
                'property="og:image:alt"', 'property="og:site_name"'):
        assert out.count(tag) == 1, ("exactly one " + tag, out.count(tag))
    for m in re.findall(r'(?:og:image|og:url|twitter:image)" content="([^"]*)', out):
        assert m.startswith("https://"), ("relative social url", m)
    assert '/og/brand.png' in inject(INDEX, "t", "d", "x"), "a plain page keeps the brand card"
    wout = inject(INDEX, "t", "d", "play x", watch=True)
    assert "window.OONTZ_WATCH=true" in wout, "watch flag set"
    assert SHARE_RE.match("/t/abc-1") and not SHARE_RE.match("/t/a/b") and not SHARE_RE.match("/t/<x>"), "share ids"
    # /language is a standalone document: it must bring its own head, and every
    # anchor it points at must exist, or a 21,000-word article has dead contents.
    assert LANGUAGE.count("<title>") == 1 and 'property="og:url" content="https://' in LANGUAGE, "article head"
    _all = re.findall(r'id="([^"]+)"', LANGUAGE)
    _ids = set(_all)
    _dead = sorted(set(re.findall(r'href="#([^"]+)"', LANGUAGE)) - _ids)
    assert not _dead, ("dead anchors in language.html", _dead)
    # An <svg> marker id="a3" and the appendix anchor #a3 are the same id, and the
    # contents rail then tracks a <marker> in a <defs> block. Duplicates, not just
    # missing ones.
    _dupe = sorted(i for i in _ids if _all.count(i) > 1)
    assert not _dupe, ("duplicate ids in language.html", _dupe)
    print("server.py: inject escapes, boot hook set, share ids validated")
    sys.exit(0)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print("landing on :%d  api %s" % (PORT, API), flush=True)
    httpd.serve_forever()
