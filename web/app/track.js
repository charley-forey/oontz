/* Interaction telemetry. `OONTZ_TRACK(name, props)` from anywhere; the rest is
 * automatic. Both sites load this file — web/landing/engine/track.js is a
 * byte-identical copy, enforced by web/landing/check.js.
 *
 * Rules this file lives by, in order:
 *   1. It never throws and never blocks. Every entry point is wrapped; a broken
 *      tracker must not be able to break the instrument.
 *   2. Opt-out is checked BEFORE anything is queued — DNT, or oontz_notrack in
 *      localStorage. Opted out, nothing is collected, nothing is timed, and no
 *      listener does any work.
 *   3. Pointer movement is bucketed into a 12x8 grid at 4 Hz and shipped once
 *      every 10s. Cells, never pixels. That throttle is what keeps the table
 *      from being 95% mouse coordinates.
 *
 * The wire is POST {API}/e — one batch, <= 50 events, always answered 200.
 * The pure halves (name validation, sid rotation, the queue cap, the opt-out
 * predicate) are exported for node so web/app/check.js can test them.
 */
(function () {
"use strict";

var IDLE_MS = 30 * 60 * 1000;   /* a sid older than this much quiet is a new session */
var MAX_BATCH = 50;             /* the server's cap; take() must agree with it */
var FLUSH_AT = 20, FLUSH_MS = 5000, HEARTBEAT_MS = 15000, POINTER_MS = 10000;
var QMAX = 500;                 /* offline ceiling — a dead network must not eat the tab */

/* -- the pure half, tested in node ---------------------------------------- */
function valid(n){ return typeof n === "string" && /^[a-z][a-z0-9_]{0,39}$/.test(n); }

/* A session is the same session until 30 minutes of silence. Rotating on a wall
   clock instead would cut a 45-minute jam in half; rotating never would fuse
   this morning and tonight into one. */
function stale(lastMs, nowMs){ return !lastMs || (nowMs - lastMs) > IDLE_MS; }

function optedOut(nav, store, win){
  try {
    var d = (nav && (nav.doNotTrack || nav.msDoNotTrack)) || (win && win.doNotTrack);
    if (d === "1" || d === 1 || d === "yes") return true;
    return !!(store && store.getItem("oontz_notrack"));
  } catch (e) { return false; }
}

var Q = [];
function push(q, name, props, off, t){
  if (off || !valid(name) || q.length >= QMAX) return q.length;
  q.push({n: name, t: t || Date.now() / 1000, p: props || {}});
  return q.length;
}
function take(q){ return q.splice(0, MAX_BATCH); }

if (typeof module !== "undefined" && module.exports)
  module.exports = {valid: valid, stale: stale, optedOut: optedOut, push: push, take: take,
                    Q: Q, IDLE_MS: IDLE_MS, MAX_BATCH: MAX_BATCH};

if (typeof document === "undefined") return;   /* node stops here: no DOM to wire */

/* -- identity ------------------------------------------------------------- */
var OFF = optedOut(navigator, window.localStorage, window);
function rnd(){ return (Date.now().toString(36) + Math.random().toString(36).slice(2, 10)); }
var DID = "", SID = "";
try {
  DID = localStorage.getItem("oontz_did") || "";
  if (!DID && !OFF) { DID = rnd(); localStorage.setItem("oontz_did", DID); }
  SID = sessionStorage.getItem("oontz_sid") || "";
  if (stale(parseFloat(sessionStorage.getItem("oontz_sid_at")), Date.now())) SID = "";
  if (!SID) SID = rnd();
} catch (e) { SID = SID || rnd(); }

function touch(){
  try { sessionStorage.setItem("oontz_sid", SID); sessionStorage.setItem("oontz_sid_at", String(Date.now())); } catch (e) {}
}
if (!OFF) touch();

var SITE = window.OONTZ_SITE || (/oontz\.music$/.test(location.hostname) ? "music" : "app");

/* -- transport ------------------------------------------------------------ */
function body(evs){
  return JSON.stringify({sid: SID.slice(0, 64), did: (DID || null) && DID.slice(0, 64), site: SITE,
    path: String(location.pathname || "").slice(0, 300),
    ref: String(document.referrer || "").slice(0, 300), events: evs});
}
function flush(beacon){
  if (OFF || !Q.length) return;
  var url = (window.API || "https://api.oontz.sh") + "/e";
  var evs = take(Q), b = body(evs);
  try {
    /* sendBeacon cannot carry headers, so unload rows land anonymous — that is
       the trade for them landing at all. Everything else goes by fetch, which
       carries the token, and keepalive so a flush started mid-navigation finishes. */
    if (beacon && navigator.sendBeacon) { navigator.sendBeacon(url, new Blob([b], {type: "text/plain"})); return; }
    var h = {"content-type": "application/json"};
    var tk = localStorage.getItem("oontz_token"); if (tk) h.authorization = "Bearer " + tk;
    fetch(url, {method: "POST", headers: h, body: b, keepalive: true}).catch(function (){});
  } catch (e) {}
}

function track(name, props){
  try {
    if (OFF) return;
    if (push(Q, name, props) >= FLUSH_AT) flush(false);
    touch();
  } catch (e) {}
}
window.OONTZ_TRACK = track;

if (OFF) return;   /* opted out: not one listener, not one timer */

/* -- auto-capture --------------------------------------------------------- */
setInterval(function (){ flush(false); }, FLUSH_MS);

document.addEventListener("click", function (e){
  try {
    var el = e.target; if (!el || !el.tagName) return;
    track("click", {id: (el.id || "").slice(0, 40), tag: el.tagName.toLowerCase(),
      txt: (el.textContent || "").trim().slice(0, 40)});
  } catch (err) {}
}, true);

var DEPTH = 0;
addEventListener("scroll", function (){
  try {
    var h = document.documentElement.scrollHeight - innerHeight;
    var d = h > 0 ? Math.round((pageYOffset / h) * 100 / 25) * 25 : 100;
    if (d > DEPTH) { DEPTH = d; track("scroll", {depth: d}); }
  } catch (e) {}
}, {passive: true});

var VIS_MS = 0, VIS_AT = document.hidden ? 0 : Date.now();
setInterval(function (){
  if (document.hidden) return;
  VIS_MS += Date.now() - VIS_AT; VIS_AT = Date.now();
  track("heartbeat", {visible_ms: VIS_MS});
}, HEARTBEAT_MS);

addEventListener("error", function (e){
  try { track("js_error", {msg: String(e.message || "").slice(0, 200),
    src: String(e.filename || "").slice(0, 120), line: e.lineno || 0}); } catch (err) {}
});
addEventListener("unhandledrejection", function (e){
  try { track("js_reject", {msg: String((e.reason && e.reason.message) || e.reason || "").slice(0, 200)}); } catch (err) {}
});

/* -- pointer, 4 Hz into a 12x8 grid --------------------------------------- */
var PN = 0, PAT = 0, PDWELL = 0, CELLS = {};
addEventListener("pointermove", function (e){
  try {
    var now = Date.now(); if (now - PAT < 250) return;
    if (PAT && now - PAT < 2000) PDWELL += now - PAT;
    PAT = now; PN++;
    var c = Math.min(11, Math.max(0, Math.floor(e.clientX / innerWidth * 12)));
    var r = Math.min(7, Math.max(0, Math.floor(e.clientY / innerHeight * 8)));
    var k = r * 12 + c; CELLS[k] = (CELLS[k] || 0) + 1;
  } catch (err) {}
}, {passive: true});
setInterval(function (){
  if (!PN) return;
  var g = []; for (var k in CELLS) g.push([+k, CELLS[k]]);
  track("pointer", {n: PN, dwell_ms: PDWELL, grid: g.slice(0, 96)});
  PN = 0; PDWELL = 0; CELLS = {};
}, POINTER_MS);

/* -- session edges -------------------------------------------------------- */
var utm = (location.search.match(/[?&]utm_source=([^&]*)/) || [])[1] || "";
track("session_start", {});
track("boot", {vw: innerWidth, vh: innerHeight, dpr: window.devicePixelRatio || 1,
  lang: (navigator.language || "").slice(0, 12),
  tz: (function (){ try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return ""; } })(),
  mobile: /Mobi|Android|iPhone|iPad/.test(navigator.userAgent) ? 1 : 0,
  pwa: (matchMedia && matchMedia("(display-mode: standalone)").matches) ? 1 : 0,
  referrer: String(document.referrer || "").slice(0, 200), utm: decodeURIComponent(utm).slice(0, 60)});

function bye(){
  try {
    if (!document.hidden) { VIS_MS += Date.now() - VIS_AT; VIS_AT = Date.now(); }
    push(Q, "session_end", {visible_ms: VIS_MS});
    flush(true);
  } catch (e) {}
}
addEventListener("pagehide", bye);
document.addEventListener("visibilitychange", function (){
  if (document.hidden) bye(); else VIS_AT = Date.now();
});
})();
