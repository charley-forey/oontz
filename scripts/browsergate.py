"""Run web/app/test.html in a real headless browser and report.

check.js covers the pure half. This covers everything that needs a DOM or an
AudioContext - decks, the offline renders, the ear, the keyboard, the palette -
by driving the actual index.html in an iframe.

The page reports each result back over HTTP as it runs, so a hang still tells you
which test hung. Chrome's --virtual-time-budget fast-forwards timers, which makes
an in-page timeout fire long before the real render it is guarding has finished -
so this runs in real time and the runner holds the clock.

    python scripts/browsergate.py            # quiet unless it fails
    python scripts/browsergate.py -v         # print every line

Exit 0 only if every test passed.
"""
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "app")

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

RESULTS = []
DONE = threading.Event()


def find_browser():
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=APP, **kw)

    def log_message(self, *a, **k):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n).decode("utf-8", "replace")
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            msg = json.loads(body)
        except ValueError:
            return
        if msg.get("done"):
            DONE.set()
        else:
            RESULTS.append(msg)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def show(r):
    print("  %-4s  %s%s" % ("ok" if r.get("ok") else "FAIL",
                            r.get("name", "?"),
                            ("   " + r["detail"]) if r.get("detail") else ""))


def main(argv):
    verbose = "-v" in argv or "--verbose" in argv
    budget = 600
    exe = find_browser()
    if not exe:
        print("browsergate: no Chrome or Edge found - skipping")
        return 0

    port = free_port()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    # The port was already per-run; the profile was not. Two sessions running the
    # gate at once shared one ROOT/.browsergate-profile, and whichever finished
    # first rmtree'd it out from under the other. mkdtemp is per-process by
    # construction, so concurrent gates no longer see each other at all.
    profile = tempfile.mkdtemp(prefix="browsergate-")
    proc = subprocess.Popen(
        [exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--mute-audio",
         "--autoplay-policy=no-user-gesture-required",
         "--user-data-dir=" + profile,
         "http://127.0.0.1:%d/test.html" % port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    seen = 0
    try:
        t0 = time.time()
        while time.time() - t0 < budget and not DONE.is_set():
            while len(RESULTS) > seen:
                r = RESULTS[seen]
                seen += 1
                if verbose or not r.get("ok"):
                    show(r)
            time.sleep(0.2)
    finally:
        proc.terminate()
        httpd.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    while len(RESULTS) > seen:
        r = RESULTS[seen]
        seen += 1
        if verbose or not r.get("ok"):
            show(r)

    fails = [r for r in RESULTS if not r.get("ok")]
    if not DONE.is_set():
        last = RESULTS[-1].get("name") if RESULTS else "nothing"
        print("  browsergate: did not finish in %ds (last test: %s)" % (budget, last))
        return 1
    print("  browsergate: %d passed, %d failed" % (len(RESULTS) - len(fails), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
