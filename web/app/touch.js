/* The touch deck. A phone has no qwertyui, so the instrument grows buttons —
 * and every button just dispatches the KeyboardEvent the desktop key would
 * have sent, so the whole keyboard path (mode branching, echo, draw) is reused
 * verbatim and this file teaches the page nothing new about music.
 *
 * Coarse pointers only; a laptop never sees it. Hold keys ([ ] /) repeat while
 * pressed, exactly like OS key-repeat. Pure tables exported for check.js.
 */
(function (g) {
"use strict";

/* what the deck shows, top to bottom: [key, label, hold?] */
var ROW_MAIN = [[" ", "▶ ▮"], ["<", "‹ sec"], [">", "sec ›"], ["z", "mute"], ["x", "solo"], ["M", "deck"], ["R", "rec"], ["\\", "spin"]];
var ROW_FX   = [["[", "filt ▼", 1], ["]", "filt ▲", 1], ["/", "roll", 1], ["`", "tape"], ["-", "bpm −"], ["=", "bpm +"], [",", "sw −"], [".", "sw +"]];
var PADS     = "qwertyuiasdfghjk".split("");           /* steps 1..16 of the focused track */
var TRACKS   = "12345678".split("");
var HOLD_MS  = 90;

var TOUCH = { ROW_MAIN: ROW_MAIN, ROW_FX: ROW_FX, PADS: PADS, TRACKS: TRACKS };
g.OONTZ_TOUCH = TOUCH;
if (typeof document === "undefined") return;           /* node: tables only, for the gate */
if (!matchMedia("(pointer: coarse)").matches) return;  /* a mouse never needs this */

function send(type, key, repeat) {
  var IN = document.getElementById("in");
  if (document.activeElement === IN) IN.blur();        /* pads must not type letters */
  dispatchEvent(new KeyboardEvent(type, { key: key, repeat: !!repeat, bubbles: true }));
}

var css = document.createElement("style");
css.textContent =
  "#touch{display:grid;grid-template-columns:repeat(8,1fr);gap:5px;padding:8px 0 2px;user-select:none;-webkit-user-select:none}" +
  "#touch button{font:inherit;font-size:12px;color:var(--fg);background:rgba(255,255,255,.04);" +
    "border:1px solid var(--line);border-radius:6px;padding:9px 0;touch-action:manipulation;min-height:40px}" +
  "#touch button:active,#touch button.held{background:var(--accent);color:var(--bg);border-color:var(--accent)}" +
  "#touch .pad{color:var(--accent)} #touch .trk{opacity:.75;min-height:32px;padding:5px 0}" +
  "@media (orientation: landscape){#touch{grid-template-columns:repeat(16,1fr);gap:4px;padding:4px 0 0}" +
    "#touch button{min-height:30px;padding:4px 0;font-size:11px}#rack{max-height:22vh}}";
document.head.appendChild(css);

var deck = document.createElement("div");
deck.id = "touch";
function btn(key, label, opts) {
  var b = document.createElement("button");
  b.textContent = label;
  b.dataset.key = key;
  if (opts) b.className = opts;
  return b;
}
ROW_MAIN.forEach(function (k) { deck.appendChild(btn(k[0], k[1])); });
PADS.forEach(function (k, i) { deck.appendChild(btn(k, String(i + 1), "pad")); });
TRACKS.forEach(function (k) { deck.appendChild(btn(k, "trk " + k, "trk")); });
ROW_FX.forEach(function (k) { var b = btn(k[0], k[1]); if (k[2]) b.dataset.hold = "1"; deck.appendChild(b); });

var bar = document.getElementById("bar");
bar.parentNode.insertBefore(deck, bar);

var timer = 0;
deck.addEventListener("touchstart", function (e) {
  var b = e.target.closest("button"); if (!b) return;
  e.preventDefault();                                   /* no ghost click, no zoom, no focus */
  b.classList.add("held");
  send("keydown", b.dataset.key);
  if (b.dataset.hold) timer = setInterval(function () { send("keydown", b.dataset.key, true); }, HOLD_MS);
}, { passive: false });
function up(e) {
  var b = e.target.closest && e.target.closest("button"); if (!b) return;
  b.classList.remove("held");
  if (timer) { clearInterval(timer); timer = 0; }
  send("keyup", b.dataset.key);
}
deck.addEventListener("touchend", up);
deck.addEventListener("touchcancel", up);
/* a desktop with a touchscreen sends clicks too; honour them once */
deck.addEventListener("click", function (e) {
  var b = e.target.closest("button"); if (!b || e.detail === 0) return;
  if (!("ontouchstart" in window)) { send("keydown", b.dataset.key); send("keyup", b.dataset.key); }
});
})(typeof window !== "undefined" ? window : globalThis);
