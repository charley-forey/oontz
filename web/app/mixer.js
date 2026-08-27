/* DECK: the page you mix on.
 *
 * A different instrument from STUDIO, so it looks different - two decks stacked like
 * real gear, waveforms you can see a whole track in, and a mixer you can read at a
 * glance. That is `oontz/ui_deck.py`'s shape, which is a finished design; this is
 * that layout in a browser.
 *
 * It owns no audio. Every control here drives something the engine already had:
 * Deck.eq, Deck.filter, Deck.fader, Deck.setRate, Deck.syncTo, Deck.loopBeats,
 * Deck.jumpBeats, Deck.jumpHot, Engine.crossfade. The only reason this file exists
 * is that none of it was reachable without typing.
 *
 * Structure follows touch.js: inject a stylesheet, build the DOM once, mount inside
 * #wrap so viz.js's watch-mode hide list still covers it, and bail before touching
 * the document so check.js can import the tables under node.
 */
(function (g) {
"use strict";

/* Faders are <input type=range>. Native gets keyboard, touch and a screen reader for
   free, and a rotary knob would buy nothing a range does not. */
var EQ_BANDS = ["low", "mid", "high"];
var LOOPS = [1, 2, 4, 8, 16];
var JUMPS = [-8, -4, -1, 1, 4, 8];

/* grid-template-areas per breakpoint. Deck panels are minmax(0,1fr) everywhere or
   the canvases refuse to shrink and push the prompt off the screen. */
var AREAS = {
  desktop: '"wavea master waveb" "decka mixer deckb" "browse browse browse"',
  portrait: '"wavea" "decka" "mixer" "deckb" "waveb" "browse"',
  landscape: '"wavea waveb" "decka deckb" "mixer mixer"'
};

g.OONTZ_MIXER = {AREAS: AREAS, EQ_BANDS: EQ_BANDS, LOOPS: LOOPS, JUMPS: JUMPS};

if (typeof document === "undefined") return;      /* node gets the tables only */

var CSS = [
"#mixer{display:none;flex:1;min-height:0;grid-gap:5px;gap:5px;margin-top:5px}",
"body.deck #mixer{display:grid}",
/* #out is the only scroller in #wrap and also flex:1 - two of those fight, and the
   canvases win by pushing the prompt off the bottom. In deck mode the log steps aside. */
"body.deck #out,body.deck #tail,body.deck #hint{display:none}",
/* The palette is the way back to the terminal from a full-screen deck. Its output
   goes to #out, which deck mode hides - so while it is open, the log takes the room
   back and the mixer steps aside, or every command you type looks like it did nothing. */
"body.deck.palout #mixer{display:none}",
"body.deck.palout #out{display:flex}",
"body.deck #wrap{max-width:none;padding:8px}",
"body.deck #touch{display:none}",
"#mixer .pane{background:var(--plate);border:1px solid var(--line);border-radius:5px;",
  "backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);padding:6px 8px;min-width:0;min-height:0}",
"#mixer .wave{grid-area:wavea;position:relative;min-height:54px}",
"#mixer .wave.b{grid-area:waveb}",
"#mixer canvas{display:block;width:100%;height:100%;min-height:48px;border-radius:3px;touch-action:none;cursor:pointer}",
"#mixer .deck{grid-area:decka;display:flex;flex-direction:column;gap:4px;overflow:auto;scrollbar-width:thin}",
"#mixer .deck.b{grid-area:deckb}",
"#mixer .mix{grid-area:mixer;display:flex;flex-direction:column;gap:4px;align-items:stretch;overflow:auto;scrollbar-width:thin}",
"#mixer .master{grid-area:master;display:flex;align-items:center;gap:10px;flex-wrap:wrap}",
"#mixer .browse{grid-area:browse;overflow:auto;min-height:0}",
/* rows of controls */
"#mixer .row{display:flex;align-items:center;gap:3px;flex-wrap:wrap}",
"#mixer .ttl{display:flex;align-items:baseline;gap:8px;min-width:0}",
"#mixer .nm{color:var(--bright);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:22ch}",
"#mixer .num{color:var(--dim);font-size:.85em;white-space:nowrap}",
"#mixer .tag{color:var(--accent)} #mixer .deck.b .tag{color:var(--accent2)}",
/* buttons: same vocabulary as .chip, sized for a thumb */
"#mixer button{font:inherit;font-size:.78em;line-height:1;color:var(--dim);background:rgba(255,255,255,.04);",
  "border:1px solid var(--line);border-radius:5px;padding:6px 7px;min-height:32px;min-width:32px;",
  "cursor:pointer;touch-action:manipulation}",
"#mixer button:hover{color:var(--bright);border-color:var(--accent)}",
"#mixer button.on{background:var(--accent);border-color:var(--accent);color:var(--bg)}",
"#mixer .deck.b button.on{background:var(--accent2);border-color:var(--accent2)}",
"#mixer button.hot.set{color:var(--accent);border-color:var(--accent)}",
"#mixer .deck.b button.hot.set{color:var(--accent2);border-color:var(--accent2)}",
"#mixer button:disabled{opacity:.35;cursor:default}",
/* ranges: horizontal by default, vertical where there is height to use */
"#mixer input[type=range]{-webkit-appearance:none;appearance:none;background:transparent;margin:0;",
  "width:100%;min-width:44px;height:22px;touch-action:none}",
"#mixer input[type=range]::-webkit-slider-runnable-track{height:4px;border-radius:2px;background:var(--line)}",
"#mixer input[type=range]::-moz-range-track{height:4px;border-radius:2px;background:var(--line)}",
"#mixer input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;margin-top:-6px;",
  "border-radius:50%;background:var(--accent);border:1px solid var(--bg)}",
"#mixer input[type=range]::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--accent);border:1px solid var(--bg)}",
"#mixer .b input[type=range]::-webkit-slider-thumb{background:var(--accent2)}",
"#mixer .b input[type=range]::-moz-range-thumb{background:var(--accent2)}",
"#mixer .lab{color:var(--dim);font-size:.72em;min-width:2.8em}",
"#mixer .strip{display:flex;gap:8px;align-items:stretch}",
"#mixer .ch{flex:1 1 0;min-width:0;display:flex;flex-direction:column;gap:2px}",
/* A range is width:100%, which in a narrow channel wraps it under its own label
   and doubles the height of the whole strip. Beside the label, not under it. */
"#mixer .ch .row{flex-wrap:nowrap}",
"#mixer .row input[type=range]{flex:1 1 50px;width:auto;min-width:50px}",
"#mixer .trow{flex-wrap:nowrap}",
"#mixer .xf{display:flex;align-items:center;gap:6px}",
"#mixer .xf input{flex:1}",
"#mixer .drift{font-size:.8em;color:var(--dim)}",
/* the browser */
"#mixer .src{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:5px}",
"#mixer .item{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid rgba(36,49,61,.5)}",
"#mixer .item .t{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
"#mixer .item .m{color:var(--dim);font-size:.8em;white-space:nowrap}",
"#mixer .empty{color:var(--dim);padding:6px 0}",
/* Desktop is the only new breakpoint; 640px and the landscape query already exist. */
/* A wave row must be told its height. Left on `auto` the canvas takes whatever it
   likes, the deck row collapses to nothing and its controls spill over the browser.
   Phone portrait scrolls the whole panel instead of trying to fit; on a big screen
   everything fits at once and each pane scrolls on its own. */
"#mixer{grid-template-areas:" + AREAS.portrait + ";grid-template-columns:minmax(0,1fr);",
  "grid-template-rows:minmax(44px,12vh) auto auto auto minmax(44px,12vh) auto;overflow-y:auto}",
"@media (min-width:900px){#mixer{grid-template-areas:" + AREAS.desktop + ";",
  "grid-template-columns:minmax(0,1fr) minmax(220px,300px) minmax(0,1fr);",
  "grid-template-rows:minmax(52px,14vh) minmax(0,1fr) minmax(0,15vh);overflow:hidden}",
  "#mixer .wave{min-height:52px}}",
"@media (max-height:520px) and (orientation:landscape){#mixer{grid-template-areas:" + AREAS.landscape + ";",
  "grid-template-columns:minmax(0,1fr) minmax(0,1fr);",
  "grid-template-rows:minmax(38px,22vh) minmax(0,1fr) auto;gap:4px;overflow:hidden}",
  "#mixer .browse{display:none}#mixer .wave{min-height:38px}",
  "#mixer button{min-height:30px;padding:5px 6px}}"
].join("");

var EL = null, DECKS = {}, RAF = 0, PEAKS = {}, SRC = "mine", LIST = [], BUSY = false;

function el(tag, cls, txt){
  var d = document.createElement(tag);
  if(cls) d.className = cls;
  if(txt != null) d.textContent = txt;
  return d;
}
function mmss(s){ s = Math.max(0, Math.round(s || 0)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
function E(){ return g.E; }
function deck(n){ return E().decks()[n]; }

/* ---- one deck's controls ------------------------------------------------- */

function buildDeck(name){
  var wrapC = el("div", "pane wave" + (name === "b" ? " b" : ""));
  var cv = el("canvas"); wrapC.appendChild(cv);

  var p = el("div", "pane deck" + (name === "b" ? " b" : ""));
  var ttl = el("div", "ttl");
  var tag = el("span", "tag", name.toUpperCase());
  var nm = el("span", "nm", "empty");
  var num = el("span", "num", "");
  ttl.appendChild(tag); ttl.appendChild(nm); ttl.appendChild(num);

  var transport = el("div", "row");
  function btn(label, title, fn){
    var b = el("button", null, label); b.title = title || label;
    b.addEventListener("click", function(e){ e.preventDefault(); fn(b); paint(); });
    return b;
  }
  var play = btn("▶", "play / pause", function(){
    var d = deck(name); if(!d.r) return;
    if(d.playing) d.stop(); else d.play();
  });
  var cue = btn("cue", "back to the start", function(){ var d = deck(name); if(!d.r) return; d.stop(); d.pos0 = 0; });
  var sync = btn("sync", "match the other deck's tempo and phase", function(){
    var d = deck(name), o = deck(name === "a" ? "b" : "a");
    if(d.r && o.r) d.syncTo(o);
  });
  transport.appendChild(play); transport.appendChild(cue); transport.appendChild(sync);

  /* beat jump */
  var jumps = el("div", "row");
  jumps.appendChild(el("span", "lab", "jump"));
  JUMPS.forEach(function(n){
    jumps.appendChild(btn((n > 0 ? "+" : "") + n, n + " beats", function(){
      var d = deck(name); if(d.r) d.jumpBeats(n);
    }));
  });

  /* loop */
  var loops = el("div", "row");
  loops.appendChild(el("span", "lab", "loop"));
  var loopBtns = {};
  LOOPS.forEach(function(n){
    var b = btn(String(n), n + "-beat loop", function(){
      var d = deck(name); if(!d.r) return;
      var on = d.loop && d.loopN === n;
      d.loopBeats(on ? 0 : n); d.loopN = on ? 0 : n;
    });
    loopBtns[n] = b; loops.appendChild(b);
  });

  /* hot cues, seeded from the section marks so they mean something on load */
  var hots = el("div", "row");
  hots.appendChild(el("span", "lab", "cues"));
  var hotBtns = [];
  for(var i = 0; i < 8; i++) (function(i){
    var b = el("button", "hot", String(i + 1));
    b.title = "tap to jump, hold to set";
    var held = 0;
    b.addEventListener("pointerdown", function(){ held = setTimeout(function(){
      held = 0; var d = deck(name); if(d.r){ d.setHot(i); paint(); } }, 500); });
    b.addEventListener("pointerup", function(e){
      e.preventDefault();
      if(held){ clearTimeout(held); held = 0; var d = deck(name);
        if(d.r){ if(d.hot && d.hot[i] != null) d.jumpHot(i); else d.setHot(i); paint(); } }
    });
    b.addEventListener("pointercancel", function(){ if(held){ clearTimeout(held); held = 0; } });
    hotBtns.push(b); hots.appendChild(b);
  })(i);

  /* tempo */
  var tempo = el("div", "row trow");
  tempo.appendChild(el("span", "lab", "tempo"));
  var rate = el("input"); rate.type = "range"; rate.min = "0.92"; rate.max = "1.08"; rate.step = "0.0005"; rate.value = "1";
  rate.setAttribute("aria-label", "deck " + name + " tempo");
  rate.addEventListener("input", function(){ var d = deck(name); if(d.r) d.setRate(parseFloat(rate.value)); paint(); });
  var reset = btn("0", "back to the track's own tempo", function(){
    var d = deck(name); d.setRate(1); rate.value = "1";
  });
  tempo.appendChild(rate); tempo.appendChild(reset);

  p.appendChild(ttl); p.appendChild(transport); p.appendChild(jumps);
  p.appendChild(loops); p.appendChild(hots); p.appendChild(tempo);

  DECKS[name] = {pane: p, wave: wrapC, cv: cv, nm: nm, num: num, play: play,
                 loopBtns: loopBtns, hotBtns: hotBtns, rate: rate};
  return [wrapC, p];
}

/* ---- the mixer strip ----------------------------------------------------- */

function buildMix(){
  var p = el("div", "pane mix");
  var strip = el("div", "strip");
  ["a", "b"].forEach(function(name){
    var ch = el("div", "ch" + (name === "b" ? " b" : ""));
    ch.appendChild(el("div", "lab", name.toUpperCase()));
    EQ_BANDS.forEach(function(band){
      var r = el("div", "row");
      r.appendChild(el("span", "lab", band));
      var s = el("input"); s.type = "range"; s.min = "0"; s.max = "2"; s.step = "0.01"; s.value = "1";
      s.setAttribute("aria-label", "deck " + name + " " + band);
      s.addEventListener("input", function(){
        var d = deck(name), v = parseFloat(s.value);
        d.eq(band, v); d.kill[band] = v <= 0.001;
      });
      /* double-tap a band to kill it and back, the way a kill switch works */
      s.addEventListener("dblclick", function(){
        var d = deck(name), killed = parseFloat(s.value) <= 0.001;
        s.value = killed ? "1" : "0"; d.eq(band, killed ? 1 : 0); d.kill[band] = !killed;
      });
      r.appendChild(s); ch.appendChild(r);
    });
    var fr = el("div", "row");
    fr.appendChild(el("span", "lab", "filter"));
    var f = el("input"); f.type = "range"; f.min = "-1"; f.max = "1"; f.step = "0.01"; f.value = "0";
    f.setAttribute("aria-label", "deck " + name + " filter");
    f.addEventListener("input", function(){ deck(name).filter(parseFloat(f.value)); });
    f.addEventListener("dblclick", function(){ f.value = "0"; deck(name).filter(0); });
    fr.appendChild(f); ch.appendChild(fr);

    var lr = el("div", "row");
    lr.appendChild(el("span", "lab", "level"));
    var lv = el("input"); lv.type = "range"; lv.min = "0"; lv.max = "1"; lv.step = "0.01"; lv.value = "1";
    lv.setAttribute("aria-label", "deck " + name + " level");
    lv.addEventListener("input", function(){ deck(name).fader(parseFloat(lv.value)); });
    lr.appendChild(lv); ch.appendChild(lr);
    strip.appendChild(ch);
  });

  var xf = el("div", "xf");
  xf.appendChild(el("span", "lab", "A"));
  var x = el("input"); x.type = "range"; x.min = "-1"; x.max = "1"; x.step = "0.01"; x.value = "0";
  x.setAttribute("aria-label", "crossfader");
  x.addEventListener("input", function(){ E().crossfade(parseFloat(x.value)); paint(); });
  xf.appendChild(x); xf.appendChild(el("span", "lab", "B"));

  p.appendChild(strip); p.appendChild(xf);
  DECKS._mix = {pane: p, xf: x};
  return p;
}

/* ---- the browser --------------------------------------------------------- */

var SOURCES = [
  {id: "mine", label: "mine"},
  {id: "gallery", label: "gallery"},
  {id: "styles", label: "styles"},
  {id: "sets", label: "sets"}
];

function buildBrowse(){
  var p = el("div", "pane browse");
  var tabs = el("div", "src");
  SOURCES.forEach(function(s){
    var b = el("button", null, s.label);
    b.addEventListener("click", function(){ SRC = s.id; refreshList(); });
    b.dataset.src = s.id;
    tabs.appendChild(b);
  });
  var list = el("div", "list");
  p.appendChild(tabs); p.appendChild(list);
  DECKS._browse = {pane: p, tabs: tabs, list: list};
  return p;
}

/* Every load builds an argv for CMDS.dload / CMDS.mix. No second load path to
   debug, and it inherits the render lane and the error messages for free. */
function loadOnto(name, argv){
  if(BUSY) return;
  BUSY = true; refreshList();
  var run = argv[0] === "mix" ? g.CMDS.mix(argv.slice(1)) : g.CMDS.dload([name].concat(argv));
  Promise.resolve(run).catch(function(){}).then(function(){ BUSY = false; paint(); refreshList(); });
}

function row(title, meta, onA, onB){
  var it = el("div", "item");
  var t = el("span", "t", title);
  var m = el("span", "m", meta || "");
  var a = el("button", null, "→A"), b = el("button", null, "→B");
  a.disabled = b.disabled = BUSY;
  a.addEventListener("click", function(){ onA(); });
  b.addEventListener("click", function(){ onB(); });
  it.appendChild(t); it.appendChild(m); it.appendChild(a); it.appendChild(b);
  return it;
}

function refreshList(){
  var B = DECKS._browse; if(!B) return;
  Array.prototype.forEach.call(B.tabs.children, function(b){
    b.classList.toggle("on", b.dataset.src === SRC);
  });
  B.list.innerHTML = "";
  if(BUSY){ B.list.appendChild(el("div", "empty", "rendering…")); return; }

  if(SRC === "styles"){
    var genres = Object.keys((g.CO && g.CO.GENRES) || {});
    if(!genres.length) return B.list.appendChild(el("div", "empty", "no styles"));
    genres.forEach(function(k){
      B.list.appendChild(row(k, "composed fresh",
        function(){ loadOnto("a", [k]); }, function(){ loadOnto("b", [k]); }));
    });
    return;
  }
  if(SRC === "mine"){
    if(g.song) B.list.appendChild(row(g.song.name || "this track", "what you are working on",
      function(){ loadOnto("a", ["this"]); }, function(){ loadOnto("b", ["this"]); }));
    else B.list.appendChild(el("div", "empty", "nothing open — `go` in the studio makes one"));
    return;
  }
  if(SRC === "gallery"){
    if(!LIST.length){
      var note = el("div", "empty", "loading…");
      B.list.appendChild(note);
      /* CMDS.gallery fills GAL, which is exactly what `dload <n>` indexes into */
      Promise.resolve(g.CMDS.gallery([])).catch(function(){}).then(function(){
        LIST = (g.GAL || []).slice();
        if(SRC === "gallery") refreshList();
      });
      return;
    }
    LIST.forEach(function(it, i){
      B.list.appendChild(row(it.title || it.id,
        (it.bpm ? Math.round(it.bpm) + " BPM " : "") + (it.kkey || ""),
        function(){ loadOnto("a", [String(i + 1)]); }, function(){ loadOnto("b", [String(i + 1)]); }));
    });
    return;
  }
  /* sets: the auto-DJ already exists, so this is a button for it */
  B.list.appendChild(el("div", "empty", "a playlist mixes itself across both decks"));
  var it = el("div", "item");
  var inp = el("input"); inp.type = "text"; inp.placeholder = "playlist id";
  inp.style.cssText = "flex:1;min-width:0;font:inherit;font-size:.9em;color:var(--fg);background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:5px;padding:6px";
  var go = el("button", null, "mix");
  go.addEventListener("click", function(){ if(inp.value.trim()) loadOnto("a", ["mix", inp.value.trim()]); });
  it.appendChild(inp); it.appendChild(go);
  B.list.appendChild(it);
}

/* ---- waveforms ----------------------------------------------------------- */

/* Peaks are computed once per load and cached on the render itself. Redoing this
   every frame is what makes a waveform stutter. */
function peaksFor(r, w){
  /* `ready` is in the key because a streaming load hands over the same track with
     more of it rendered; the peaks have to be recut when the audio grows. */
  var key = w + "@" + r.seconds + "@" + (r.ready == null ? r.seconds : r.ready);
  if(r._peaks && r._peaks.key === key) return r._peaks;
  var d = r.buf.getChannelData(0), n = Math.max(1, w), step = Math.floor(d.length / n) || 1;
  var mins = new Float32Array(n), maxs = new Float32Array(n);
  for(var i = 0; i < n; i++){
    var lo = 1, hi = -1, s = i * step, e = Math.min(d.length, s + step);
    for(var k = s; k < e; k += 2){ var v = d[k]; if(v < lo) lo = v; if(v > hi) hi = v; }
    mins[i] = lo; maxs[i] = hi;
  }
  PEAKS.built = (PEAKS.built || 0) + 1;                 /* the gate counts these */
  return (r._peaks = {key: key, mins: mins, maxs: maxs, n: n});
}

function drawWave(name){
  var D = DECKS[name], d = deck(name), cv = D.cv;
  var dpr = Math.min(g.devicePixelRatio || 1, 1.5);        /* same cap as viz.js */
  var w = cv.clientWidth, h = cv.clientHeight;
  if(!w || !h) return;
  if(cv.width !== Math.floor(w * dpr) || cv.height !== Math.floor(h * dpr)){
    cv.width = Math.floor(w * dpr); cv.height = Math.floor(h * dpr);
  }
  var x = cv.getContext("2d"), W = cv.width, H = cv.height;
  var css = getComputedStyle(document.documentElement);
  var accent = css.getPropertyValue(name === "a" ? "--accent" : "--accent2").trim() || "#3ff0e0";
  var line = css.getPropertyValue("--line").trim() || "#24313d";
  var dim = css.getPropertyValue("--dim").trim() || "#93a4b3";
  x.clearRect(0, 0, W, H);
  if(!d.r){
    x.fillStyle = dim; x.font = (12 * dpr) + "px ui-monospace,monospace";
    x.fillText("empty — load a track below", 8 * dpr, H / 2);
    return;
  }
  var p = peaksFor(d.r, Math.floor(W));
  var mid = H / 2;
  x.fillStyle = line;
  for(var i = 0; i < p.n; i++){
    var y0 = mid - p.maxs[i] * mid, y1 = mid - p.mins[i] * mid;
    x.fillRect(i, y0, 1, Math.max(1, y1 - y0));
  }
  /* the played part, in the deck's colour */
  var frac = Math.max(0, Math.min(1, d.pos() / d.r.seconds));
  var px = Math.floor(p.n * frac);
  x.fillStyle = accent;
  for(var j = 0; j < px; j++){
    var a0 = mid - p.maxs[j] * mid, a1 = mid - p.mins[j] * mid;
    x.fillRect(j, a0, 1, Math.max(1, a1 - a0));
  }
  /* section marks, then hot cues, then the head */
  var m = d.r.marks || [];
  x.fillStyle = dim;
  for(var k = 0; k < m.length; k++){
    var mx = Math.floor(W * (m[k][0] / d.r.seconds));
    x.fillRect(mx, 0, Math.max(1, dpr), H * 0.22);
  }
  if(d.hot) for(var q = 0; q < d.hot.length; q++){
    if(d.hot[q] == null) continue;
    x.fillStyle = accent;
    var hx = Math.floor(W * (d.hot[q] / d.r.seconds));
    x.fillRect(hx, H * 0.78, Math.max(1, dpr), H * 0.22);
  }
  if(d.loop){
    x.fillStyle = "rgba(255,194,71,.20)";
    var l0 = Math.floor(W * (d.loop[0] / d.r.seconds)), l1 = Math.floor(W * (d.loop[1] / d.r.seconds));
    x.fillRect(l0, 0, Math.max(2, l1 - l0), H);
  }
  /* What has not been rendered yet, said out loud rather than drawn as silence. */
  var ready = d.readySec ? d.readySec() : d.r.seconds;
  if(ready < d.r.seconds - 0.05){
    var rx = Math.floor(W * (ready / d.r.seconds));
    x.fillStyle = "rgba(7,9,11,.55)";
    x.fillRect(rx, 0, W - rx, H);
    x.fillStyle = dim;
    x.fillRect(rx, 0, Math.max(1, dpr), H);
  }
  x.fillStyle = "#fff";
  x.fillRect(Math.floor(W * frac), 0, Math.max(1, dpr), H);
}

/* Scrub. The one real pointer-drag here; the ranges handle themselves. */
function wireScrub(name){
  var D = DECKS[name], cv = D.cv;
  function seek(e){
    var d = deck(name); if(!d.r) return;
    var r = cv.getBoundingClientRect();
    var f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    var at = f * d.r.seconds;
    d.loop = null;
    if(d.playing) d.play(at); else d.pos0 = at;
  }
  cv.addEventListener("pointerdown", function(e){
    e.preventDefault(); seek(e);
    try{ cv.setPointerCapture(e.pointerId); }catch(err){}
    cv.dataset.drag = "1";
  });
  cv.addEventListener("pointermove", function(e){ if(cv.dataset.drag) seek(e); });
  g.addEventListener("pointerup", function(){ delete cv.dataset.drag; });
}

/* ---- painting ------------------------------------------------------------ */

function paint(){
  if(!EL || !document.body.classList.contains("deck")) return;
  ["a", "b"].forEach(function(name){
    var D = DECKS[name], d = deck(name);
    D.nm.textContent = d.r ? String(d.r.name || "untitled") : "empty";
    D.num.textContent = d.r
      ? d.bpm().toFixed(1) + " BPM" + (Math.abs(d.rate - 1) > 1e-4 ? "  " + (d.rate > 1 ? "+" : "") + ((d.rate - 1) * 100).toFixed(1) + "%" : "") +
        "  " + mmss(d.pos()) + " / " + mmss(d.r.seconds)
      : "";
    D.play.textContent = d.playing ? "❚❚" : "▶";
    D.play.classList.toggle("on", !!d.playing);
    LOOPS.forEach(function(n){ D.loopBtns[n].classList.toggle("on", !!(d.loop && d.loopN === n)); });
    D.hotBtns.forEach(function(b, i){ b.classList.toggle("set", !!(d.hot && d.hot[i] != null)); });
    drawWave(name);
  });
  var M = DECKS._mix, D0 = E().decks();
  if(M){
    if(document.activeElement !== M.xf) M.xf.value = String(D0.xf);
  }
  var MB = DECKS._master;
  if(MB){
    var a = D0.a, b = D0.b;
    if(a.r && b.r){
      var dr = Math.abs(a.beatPhase() - b.beatPhase());
      dr = Math.min(dr, 1 - dr);
      MB.drift.textContent = "ΔBPM " + (a.bpm() - b.bpm()).toFixed(2) +
        "   drift " + dr.toFixed(3) + (dr < 0.02 ? "   LOCKED" : "");
    } else MB.drift.textContent = "load both decks to beatmatch";
  }
}

function frame(){ if(!document.body.classList.contains("deck")){ RAF = 0; return; } paint(); RAF = requestAnimationFrame(frame); }

/* ---- mount --------------------------------------------------------------- */

function build(){
  if(EL) return EL;
  var st = document.createElement("style"); st.textContent = CSS;
  document.head.appendChild(st);

  EL = el("div"); EL.id = "mixer";
  var master = el("div", "pane master");
  master.appendChild(el("span", "tag", "DECK"));
  var drift = el("span", "drift", "");           /* the beatmatch readout, where there is room for it */
  master.appendChild(drift);
  /* Deck mode hides #touch, so on a phone the backslash spinback - the one flourish
     the copy actually sells - had no route at all. Same call the key makes. */
  var spin = el("button", null, "↺ spin");
  spin.setAttribute("aria-label", "spinback");
  spin.addEventListener("click", function(){ E().key("\\", true); });
  master.appendChild(spin);
  DECKS._master = {pane: master, drift: drift};

  var A = buildDeck("a"), B = buildDeck("b");
  EL.appendChild(master);
  EL.appendChild(A[0]); EL.appendChild(A[1]);
  EL.appendChild(buildMix());
  EL.appendChild(B[0]); EL.appendChild(B[1]);
  EL.appendChild(buildBrowse());

  /* Inside #wrap, above the log: viz.js's watch-mode rule hides #wrap and #touch by
     name, so anything that must disappear in watch mode has to live in one of them. */
  var out = document.getElementById("out");
  out.parentNode.insertBefore(EL, out);
  wireScrub("a"); wireScrub("b");
  refreshList();
  return EL;
}

g.OONTZ_MIXER.show = function(){
  /* One load can land a new mixer.js on top of an engine an old service worker
     still had cached. Rather than throw on the first control you touch, say so and
     leave DECK's text HUD and its keys working - they need nothing from this file. */
  var d0 = deck("a");
  if(typeof d0.filter !== "function" || typeof d0.fader !== "function"){
    if(typeof g.line === "function") g.line("the mixer needs a newer engine than this tab has cached — reload once", "w");
    return;
  }
  build();
  refreshList();
  if(!RAF) RAF = requestAnimationFrame(frame);
  paint();
};
g.OONTZ_MIXER.hide = function(){
  if(RAF){ cancelAnimationFrame(RAF); RAF = 0; }
};
g.OONTZ_MIXER.paint = paint;
g.OONTZ_MIXER.peaksBuilt = function(){ return PEAKS.built || 0; };

})(typeof window !== "undefined" ? window : globalThis);
