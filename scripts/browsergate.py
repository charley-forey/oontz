"""Run web/app/test.html in a real headless browser and report.

check.js covers the pure half. This covers everything that needs a DOM or an
AudioContext - decks, the offline renders, the ear, the keyboard, the palette -
by driving the actual index.html in an iframe.

    python scripts/browsergate.py            # quiet unless it fails
    python scripts/browsergate.py -v         # print every line

Exit 0 only if the page prints OONTZ-GATE PASS.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import http.server
import functools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "app")

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def serve(port):
    """The app must come off http, not file:// - modules and fetch need an origin."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=APP)
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main(argv):
    verbose = "-v" in argv or "--verbose" in argv
    exe = find_browser()
    if not exe:
        print("browsergate: no Chrome or Edge found - skipping")
        return 0

    port = free_port()
    httpd = serve(port)
    try:
        out = subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--mute-audio",
             "--autoplay-policy=no-user-gesture-required",
             "--virtual-time-budget=900000", "--dump-dom",
             "http://127.0.0.1:%d/test.html" % port],
            capture_output=True, text=True, timeout=420, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print("browsergate: the browser did not finish in 420s")
        return 1
    finally:
        httpd.shutdown()

    dom = out.stdout or ""
    # The DOM comes back as one line of HTML; recover the rows.
    rows = re.findall(r'<div class="(ok|fail|note)">(.*?)</div>', dom, re.S)
    text = [re.sub(r"<[^>]+>", "", r[1]).replace("&lt;", "<").replace("&amp;", "&").strip()
            for r in rows]
    verdict = [t for t in text if t.startswith("OONTZ-GATE")]

    fails = [t for t in text if t.startswith("FAIL")]
    if verbose or fails or not verdict:
        for t in text:
            if t:
                print("  " + t)
    if not verdict:
        print("browsergate: the page never reported a verdict")
        if not verbose:
            print((out.stderr or "")[-600:])
        return 1
    print("  " + verdict[0])
    return 0 if "PASS" in verdict[0] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
