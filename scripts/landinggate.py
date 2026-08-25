"""Drive the REAL landing server at /t/<id> in a browser. `python scripts/landinggate.py`.

browsergate covers web/app by serving that directory statically. Nothing covered
web/landing at all - not the share route, not server.py, not the page in a browser.
So `<script src="copy.js">` shipped, and because the share page is served at /t/<id>
that relative path resolved to /t/copy.js and 404'd on every share anyone opened.
The page loaded with no copy, and 43 green browser tests never saw it.

The assertion that would have caught it is "every same-origin response is 200", so
that is the first thing this checks. It runs the actual server.py with OONTZ_API
pointed at a stub, so it is hermetic: no live API, no network, same answers offline.

    python scripts/landinggate.py        # quiet unless it fails
    python scripts/landinggate.py -v     # print every line
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsergate import find_browser, free_port, show      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING = os.path.join(ROOT, "web", "landing")

RESULTS = []
DONE = threading.Event()
SEEN = []                                   # paths the page actually asked the API for

# One fixed song, so the gate says the same thing on every machine and offline.
SONG = {
    "format": "oontz-song-1", "name": "gate track", "bpm": 140, "key": "a", "scale": "minor",
    "order": ["intro", "drop"],
    "sections": {
        "intro": {"bars": 8, "role": "intro", "energy": 0.3,
                  "tracks": {"kick": {"voice": "kick", "pat": "x...x...x...x...", "gain": 1}},
                  "order": ["kick"]},
        "drop": {"bars": 8, "role": "drop", "energy": 0.9,
                 "tracks": {"kick": {"voice": "kick", "pat": "x...x...x...x...", "gain": 1},
                            "hat": {"voice": "hat", "pat": "..x...x...x...x.", "gain": 0.8}},
                 "order": ["kick", "hat"]},
    },
}
TRACK = {"id": "gatefake", "title": "gate track", "bpm": 140, "key": "a minor", "seconds": 27.4,
         "sections": 2, "public": True, "plays": 3, "by": "anon", "handle": None,
         "remix_of": None, "remixes": 0, "data": SONG}
PLAYLIST = {"id": "gatefake", "title": "gate list", "handle": "anon",
            "songs": [dict(TRACK, seconds=27.4)]}


class Stub(http.server.BaseHTTPRequestHandler):
    """The API, reduced to exactly what a share page asks for."""

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/probe":                        # what the page has asked us for so far
            return self._send({"seen": SEEN})
        SEEN.append(p)
        if p == "/health":
            return self._send({"ok": True, "mail": False, "ai": False})
        if p.startswith("/songs/"):
            return self._send(TRACK)
        if p.startswith("/p/"):
            return self._send(PLAYLIST)
        if p in ("/gallery",):
            return self._send({"songs": [TRACK], "sort": "new"})
        if p in ("/charts",):
            return self._send({"most_remixed": [], "top_patterns": [], "bpm": []})
        return self._send({"error": "no stub for " + p}, 404)

    def do_POST(self):
        SEEN.append(self.path.split("?", 1)[0])
        if self.path == "/report":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                msg = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                msg = {}
            if msg.get("done"):
                DONE.set()
            else:
                RESULTS.append(msg)
            return self._send({"ok": True})
        return self._send({"ok": True})

    def log_message(self, fmt, *a):
        pass


def main(argv):
    verbose = "-v" in argv
    budget = 120
    exe = find_browser()
    if not exe:
        print("landinggate: no Chrome or Edge found - skipping")
        return 0

    api_port, land_port = free_port(), free_port()
    stub = http.server.ThreadingHTTPServer(("127.0.0.1", api_port), Stub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()

    env = dict(os.environ, PORT=str(land_port),
               OONTZ_API="http://127.0.0.1:%d" % api_port,
               OONTZ_SITE_URL="http://127.0.0.1:%d" % land_port)
    server = subprocess.Popen([sys.executable, "server.py"], cwd=LANDING, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    base = "http://127.0.0.1:%d" % land_port
    for _ in range(50):                                  # bind before the browser looks
        try:
            urllib.request.urlopen(base + "/health", timeout=1).read()
            break
        except Exception:
            time.sleep(0.2)
    else:
        server.terminate(); stub.shutdown()
        print("  landinggate: server.py never came up on %s" % base)
        return 1

    profile = os.path.join(ROOT, ".landinggate-profile")
    proc = subprocess.Popen(
        [exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--mute-audio",
         "--autoplay-policy=no-user-gesture-required",
         "--user-data-dir=" + profile,
         "%s/test.html?api=%d" % (base, api_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    seen = 0
    try:
        t0 = time.time()
        while time.time() - t0 < budget and not DONE.is_set():
            while len(RESULTS) > seen:
                r = RESULTS[seen]; seen += 1
                if verbose or not r.get("ok"):
                    show(r)
            time.sleep(0.2)
    finally:
        proc.terminate()
        server.terminate()
        stub.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    while len(RESULTS) > seen:
        r = RESULTS[seen]; seen += 1
        if verbose or not r.get("ok"):
            show(r)

    fails = [r for r in RESULTS if not r.get("ok")]
    if not DONE.is_set():
        last = RESULTS[-1].get("name") if RESULTS else "nothing"
        print("  landinggate: did not finish in %ds (last test: %s)" % (budget, last))
        return 1
    print("  landinggate: %d passed, %d failed" % (len(RESULTS) - len(fails), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
