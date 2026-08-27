"""Measure where oontz.sh's main thread actually goes, in a real browser.

    python scripts/perfprobe.py [--throttle 6]

browsergate proves the app is CORRECT. This answers a different question: what is
it DOING between your keystroke and the screen. It loads the real index.html,
lets it settle, then samples for five seconds and reports, per animation loop,
how many milliseconds of the main thread it ate and how many frames it drew -
plus the long tasks that block input, which is what "delayed by a second" is.

--throttle applies CDP CPU throttling so a desktop can stand in for a phone. A
mid-range Android is roughly 4-6x slower than this machine, so 6 is the honest
default when the complaint came from a phone.

Numbers, not adjectives: it prints ms and fps and exits 0. It asserts nothing.
"""
import argparse
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
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "app")
RESULT = []
DONE = threading.Event()
NOPAINT = [False]

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# Injected into the real page. Wraps each animation entry point in a counter, runs
# the page untouched for SAMPLE_MS, and reports. Wrapping is the only honest way to
# attribute cost: a profiler timeline would need parsing, and self-timing each loop
# measures exactly the function the fix would change.
PROBE = r"""
(function(){
var SETTLE = 1500, SAMPLE = 5000;
var acc = {}, longTasks = [], nav = {};

function wrapRAF(){
  var orig = window.requestAnimationFrame;
  window.requestAnimationFrame = function(fn){
    return orig.call(window, function(t){
      var label = fn.name || "anon";
      var t0 = performance.now();
      try { return fn(t); }
      finally {
        var d = performance.now() - t0;
        var a = acc[label] || (acc[label] = {ms: 0, n: 0, max: 0});
        a.ms += d; a.n++; if(d > a.max) a.max = d;
      }
    });
  };
}

try {
  var po = new PerformanceObserver(function(l){
    l.getEntries().forEach(function(e){ if(e.duration >= 50) longTasks.push(Math.round(e.duration)); });
  });
  po.observe({entryTypes: ["longtask"]});
} catch(e){}

wrapRAF();

/* Long tasks say the thread is blocked but not by what. Timers are where a
   synchronous engine hides, so name and time every one of them too. */
function wrapTimer(which){
  var orig = window[which];
  window[which] = function(fn, ms){
    if(typeof fn !== "function") return orig.apply(window, arguments);
    var label = which + ":" + (fn.name || ("anon@" + String(ms)));
    var args = [].slice.call(arguments, 2);
    return orig.call(window, function(){
      var t0 = performance.now();
      try { return fn.apply(window, args); }
      finally {
        var d = performance.now() - t0;
        var a = acc[label] || (acc[label] = {ms: 0, n: 0, max: 0});
        a.ms += d; a.n++; if(d > a.max) a.max = d;
      }
    }, ms);
  };
}
wrapTimer("setTimeout"); wrapTimer("setInterval");

/* An `await`-driven loop hides from both wrappers above: the cost lands in the
   microtask drain, after the callback returns. Audio rendering is the only thing
   here big enough to cost 700ms, so count the contexts and the renders instead. */
window.__audio = {ctx: 0, render: 0, renderMs: 0, frames: 0};
["OfflineAudioContext", "webkitOfflineAudioContext"].forEach(function(k){
  var C = window[k]; if(!C) return;
  function Wrapped(a, b, c){
    window.__audio.ctx++;
    if(typeof b === "number") window.__audio.frames += b;
    var o = new C(a, b, c);
    var sr = o.startRendering;
    o.startRendering = function(){
      window.__audio.render++;
      var t0 = performance.now();
      return sr.apply(o, arguments).then(function(v){
        window.__audio.renderMs += performance.now() - t0; return v;
      });
    };
    return o;
  }
  Wrapped.prototype = C.prototype;
  window[k] = Wrapped;
});

/* A/B control. The JS in each frame measures a few ms while the FRAME costs
   hundreds, so the cost is downstream of the callback - raster, not script. Gut
   the 2D drawing calls and nothing else: same loops, same JS, no pixels. If the
   long tasks go with it, painting is the bill. */
if(window.__NOPAINT){
  var P = CanvasRenderingContext2D.prototype;
  ["fill", "stroke", "fillRect", "clearRect", "drawImage", "fillText", "strokeRect", "putImageData"]
    .forEach(function(m){ if(P[m]) P[m] = function(){}; });
}

setTimeout(function(){
  acc = {}; longTasks = [];            /* discard boot: we want the steady state */
  var t0 = performance.now();
  setTimeout(function(){
    var span = performance.now() - t0;
    try {
      var n = performance.getEntriesByType("navigation")[0];
      if(n) nav = {dom: Math.round(n.domContentLoadedEventEnd), load: Math.round(n.loadEventEnd),
                   ttfb: Math.round(n.responseStart)};
      /* The number that matters for "it loads slowly". defer still runs every script
         BEFORE domContentLoaded fires, so dCL cannot show the win; first paint is
         when the terminal shell actually appears on the glass. */
      performance.getEntriesByType("paint").forEach(function(e){
        if(e.name === "first-contentful-paint") nav.fcp = Math.round(e.startTime);
        if(e.name === "first-paint") nav.fp = Math.round(e.startTime);
      });
    } catch(e){}
    var rows = Object.keys(acc).map(function(k){
      var a = acc[k];
      return {name: k, ms: Math.round(a.ms), n: a.n, max: Math.round(a.max),
              fps: Math.round(a.n / (span / 1000)), pct: Math.round(a.ms / span * 100)};
    }).sort(function(x, y){ return y.ms - x.ms; });
    var busy = rows.reduce(function(s, r){ return s + r.ms; }, 0);
    fetch("/", {method: "POST", body: JSON.stringify({
      span: Math.round(span), rows: rows, busy: Math.round(busy),
      busyPct: Math.round(busy / span * 100), longTasks: longTasks, nav: nav,
      playing: !!(window.E && E.playing), scripts: document.scripts.length,
      audio: window.__audio,
      /* If this reads false the handset paths never ran and the numbers below are
         a desktop's, not a phone's. */
      small: matchMedia("(max-width: 820px), (pointer: coarse)").matches,
      vw: innerWidth, vh: innerHeight, dpr: devicePixelRatio,
      canvases: [].map.call(document.querySelectorAll("canvas"), function(c){
        return c.id + ":" + c.width + "x" + c.height; }).join(" ")
    })});
  }, SAMPLE);
}, SETTLE);
})();
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=APP, **kw)

    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        # Serve index.html with the probe appended. Everything else is the real file.
        if self.path.split("?")[0] in ("/", "/index.html"):
            html = open(os.path.join(APP, "index.html"), encoding="utf-8").read()
            # The probe MUST beat every app script to the timer registrations, or a
            # setInterval created once at boot is never wrapped and reads as 0ms.
            cut = html.index("<script")
            pre = "<script>window.__NOPAINT=%s;</script>" % ("true" if NOPAINT[0] else "false")
            html = html[:cut] + pre + "<script>" + PROBE + "</script>\n" + html[cut:]
            body = html.encode()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n).decode("utf-8", "replace")
        self.send_response(204)
        self.end_headers()
        try:
            RESULT.append(json.loads(body))
        except ValueError:
            pass
        DONE.set()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def find_browser():
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    for n in ("msedge", "chrome", "chromium"):
        p = shutil.which(n)
        if p:
            return p
    return None


def throttle(dev_port, rate):
    """CPU throttling is a CDP call, and CDP needs the target's websocket. Emulation
    .setCPUThrottlingRate is one message, so a raw socket beats a dependency."""
    import base64
    import struct
    for _ in range(50):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json" % dev_port, timeout=1) as f:
                tabs = json.load(f)
            ws = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if ws:
                url = ws[0]["webSocketDebuggerUrl"]
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        return False
    host, rest = url[len("ws://"):].split("/", 1)
    h, p = host.split(":")
    s = socket.create_connection((h, int(p)), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (rest, host, key)).encode())
    s.recv(4096)
    msg = json.dumps({"id": 1, "method": "Emulation.setCPUThrottlingRate",
                      "params": {"rate": rate}}).encode()
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(msg))
    frame = b"\x81"
    n = len(msg)
    if n < 126:
        frame += bytes([0x80 | n])
    else:
        frame += bytes([0x80 | 126]) + struct.pack(">H", n)
    s.sendall(frame + mask + masked)
    time.sleep(0.3)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--throttle", type=float, default=6.0,
                    help="CPU slowdown factor; 1 = this machine's speed, 6 ~ a mid Android")
    ap.add_argument("--gpu", action="store_true",
                    help="allow GPU raster; the default --disable-gpu makes ALL canvas "
                         "work software, which a real phone does not do")
    ap.add_argument("--nopaint", action="store_true",
                    help="neuter 2D canvas drawing: same JS, no pixels (an A/B control)")
    a = ap.parse_args()

    NOPAINT[0] = a.nopaint
    exe = find_browser()
    if not exe:
        print("perfprobe: no Chrome or Edge found")
        return 0

    port, dev = free_port(), free_port()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    profile = tempfile.mkdtemp(prefix="perfprobe-")
    proc = subprocess.Popen(
        [exe, "--headless=new", "--no-sandbox", "--mute-audio"] +
        ([] if a.gpu else ["--disable-gpu"]) + [
         "--autoplay-policy=no-user-gesture-required",
         "--remote-debugging-port=%d" % dev,
         "--window-size=390,844",             # a phone viewport, not a desktop one
         "--user-data-dir=" + profile,
         "http://127.0.0.1:%d/" % port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = throttle(dev, a.throttle) if a.throttle and a.throttle != 1 else True
    try:
        DONE.wait(60)
    finally:
        proc.terminate()
        httpd.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    if not RESULT:
        print("perfprobe: the page never reported (did it fail to boot?)")
        return 1
    r = RESULT[0]
    print("\noontz.sh main thread  ·  %dx CPU throttle%s  ·  390x844  ·  %d scripts  ·  playing=%s"
          % (a.throttle, "" if ok else " (NOT APPLIED)", r["scripts"], r["playing"]))
    n = r["nav"]
    print("boot: ttfb %sms  FIRST PAINT %sms  domContentLoaded %sms  load %sms"
          % (n.get("ttfb"), n.get("fcp", n.get("fp")), n.get("dom"), n.get("load")))
    print("\nsampled %dms  ·  animation work %dms (%d%% of the thread)"
          % (r["span"], r["busy"], r["busyPct"]))
    print("  %-22s %7s %6s %6s %8s" % ("loop", "ms", "frames", "fps", "worst"))
    for row in r["rows"]:
        print("  %-22s %7d %6d %6d %7dms" % (row["name"], row["ms"], row["n"], row["fps"], row["max"]))
    print("viewport %sx%s dpr %s  ·  handset paths active: %s  ·  canvases %s"
          % (r.get("vw"), r.get("vh"), r.get("dpr"), r.get("small"), r.get("canvases")))
    a2 = r.get("audio") or {}
    print("\noffline audio while idle: %s contexts, %s renders, %s frames, %sms in startRendering"
          % (a2.get("ctx"), a2.get("render"), a2.get("frames"), round(a2.get("renderMs") or 0)))
    lt = r["longTasks"]
    print("\nlong tasks (>=50ms, each one is input that waits): %d" % len(lt))
    if lt:
        print("  worst %dms  ·  total %dms  ·  %s" % (max(lt), sum(lt), sorted(lt, reverse=True)[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
