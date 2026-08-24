/* The canvas under the terminal.
 *
 * Nothing here detects a beat. The engine's clock is exact - it placed every hit
 * on the audio timeline itself - so beat phase is arithmetic on the scheduler's
 * numbers, and the section list tells us what is coming: a build knows how far
 * along it is, the last bar before a drop knows it is the last bar. Energy per
 * band comes from the AnalyserNode on the master. Every mode is one function of
 * (ctx, frame, theme); add one by adding a key to MODES.
 *
 * Pure parts (parseParam, mix, clockPhase, bands, upcoming) run in node for check.js.
 */
(function (global) {
"use strict";

var THEMES = {
  acid:      {name: "acid",      colors: ["#1aff5c", "#a8ff00", "#00ff9c", "#0b3d1a"], bg: "#020604", glow: 0.7, intensity: 1,   decay: 0.15, symmetry: 4},
  warehouse: {name: "warehouse", colors: ["#e6e6e6", "#8a8a8a", "#ff3b3b", "#3a3a3a"], bg: "#050505", glow: 0.4, intensity: 0.9, decay: 0.25, symmetry: 1},
  sunset:    {name: "sunset",    colors: ["#ff4fa3", "#ff8a2a", "#ffd166", "#5b2a86"], bg: "#0b0611", glow: 0.8, intensity: 1,   decay: 0.12, symmetry: 2},
  mono:      {name: "mono",      colors: ["#c6d2dc", "#22e0d0", "#46545f", "#f4f9fc"], bg: "#07090b", glow: 0.3, intensity: 0.7, decay: 0.2,  symmetry: 1}
};
var PARAMS = {intensity: [0, 2], decay: [0, 1], symmetry: [1, 8]};
var ENERGY = {drop: 1, build: 0.6, break: 0.15, intro: 0.2, outro: 0.2};

/* -- pure ------------------------------------------------------------------ */

function parseParam(k, v){
  if(k === "palette" || k === "theme") return THEMES[v] ? v : null;
  var r = PARAMS[k]; if(!r) return null;
  var x = parseFloat(v); if(!isFinite(x)) return null;
  x = Math.max(r[0], Math.min(r[1], x));
  return k === "symmetry" ? Math.round(x) : Math.round(x * 100) / 100;
}

function hex(c){ var n = parseInt(c.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
/* The colour at t around the palette, t wraps: 0 is colors[0], 1 is colors[0] again. */
function mix(colors, t){
  var n = colors.length, x = (((t % 1) + 1) % 1) * n, i = Math.floor(x), f = x - i;
  var a = hex(colors[i % n]), b = hex(colors[(i + 1) % n]);
  return [Math.round(a[0] + (b[0] - a[0]) * f), Math.round(a[1] + (b[1] - a[1]) * f), Math.round(a[2] + (b[2] - a[2]) * f)];
}
function rgba(c, a){ return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + (a == null ? 1 : Math.max(0, Math.min(1, a))) + ")"; }

/* Where the playhead is, from the lookahead clock. `next` is the audio time of
   step `step` (the next 16th to be scheduled), so the 16th sounding at `now` is
   step - (next - now) / sixteenth. `songbar` belongs to the last scheduled step,
   which can be a bar ahead of the ear for up to 100ms; walk it back. */
function clockPhase(step, next, now, bpm, songbar){
  var s16 = 60 / bpm / 4, pos = Math.max(0, step - (next - now) / s16), beat = pos / 4;
  var last = Math.max(0, step - 1);
  return {pos: pos, beat: beat, beatIndex: Math.floor(beat), beatPhase: beat - Math.floor(beat),
          barPhase: (pos % 16) / 16, bar: (songbar | 0) - (Math.floor(last / 16) - Math.floor(pos / 16))};
}

/* Mean level per band, 0..1, from byte spectrum bins of `binHz` each. */
function bands(spec, binHz){
  var f = function(lo, hi){ var a = Math.max(1, Math.round(lo / binHz)), b = Math.min(spec.length, Math.round(hi / binHz)), s = 0;
    for(var i = a; i < b; i++) s += spec[i]; return b > a ? s / (b - a) / 255 : 0; };
  return {sub: f(20, 90), bass: f(90, 260), mid: f(260, 3000), high: f(3000, 11000)};
}

/* The clock knows the future: this section, how far through it we are (in bars,
   fractional), how many bars are left, and what comes next. */
function upcoming(song, bar, barPhase){
  var OZ = global.oontz, at = OZ.sectionAt(song, bar); if(!at) return null;
  var nx = OZ.sectionAt(song, bar - at.within + at.sec.bars), role = at.sec.role || "";
  return {section: at.name, role: role, within: at.within + barPhase, bars: at.sec.bars, left: at.sec.bars - at.within - barPhase,
          next: nx ? nx.sec.role || "" : "", energy: at.sec.energy == null ? (ENERGY[role] || 0.5) : at.sec.energy};
}

/* -- modes: (ctx, frame, theme). Called once per symmetry pass; mutate state on pass 0 only. -- */

var MODES = {};

MODES.spectrum = function(c, f, th){
  var sp = f.spectrum; if(!sp) return;
  var n = 48, w = f.W / 2 / n, mid = f.H / 2;
  for(var i = 0; i < n; i++){
    var lo = Math.floor(Math.pow(i / n, 2) * 400), hi = Math.floor(Math.pow((i + 1) / n, 2) * 400) + 1, s = 0;
    for(var k = lo; k < hi; k++) s += sp[k]; s /= (hi - lo) * 255;
    var h = s * s * mid * 0.9 * f.intensity * (1 + f.pulse * 0.2);
    c.fillStyle = rgba(mix(th.colors, i / n + f.t * 0.05), 0.3 + s * 0.6);
    c.fillRect(f.W / 2 + i * w, mid - h, w - 2, h * 2);
    c.fillRect(f.W / 2 - (i + 1) * w, mid - h, w - 2, h * 2);
  }
};

MODES.scope = function(c, f, th){
  var wv = f.wave; if(!wv) return;
  var n = wv.length, mid = f.H / 2, amp = f.H * 0.3 * f.intensity, i;
  c.lineWidth = 2; c.strokeStyle = rgba(mix(th.colors, f.beatPhase * 0.5 + f.t * 0.02), 0.8);
  c.beginPath();
  for(i = 0; i < n; i += 2){ var x = i / n * f.W, y = mid + wv[i] * amp; i ? c.lineTo(x, y) : c.moveTo(x, y); }
  c.stroke();
  /* a Lissajous of the signal against itself a few ms later: a mono goniometer */
  var R = Math.min(f.W, f.H) * (0.6 + f.bands.bass) * f.intensity, d = 48;
  c.lineWidth = 1.5; c.strokeStyle = rgba(mix(th.colors, 0.5 + f.beatPhase * 0.3), 0.6);
  c.beginPath();
  for(i = 0; i + d < n; i += 2){ var x2 = f.W / 2 + wv[i] * R, y2 = mid + wv[i + d] * R; i ? c.lineTo(x2, y2) : c.moveTo(x2, y2); }
  c.stroke();
};

MODES.tunnel = function(c, f, th){
  var N = 14, R = Math.hypot(f.W, f.H) * 0.55, i, k;
  var z = f.beat * (0.25 + f.rush * 0.5) + f.t * 0.05;           // rings advance per beat; a build runs
  for(k = 0; k < N; k++){
    var p = (((z + k / N) % 1) + 1) % 1, r = R * p * p * (1 + f.flash * 0.8);   // p^2 is perspective
    var a = p * (0.15 + f.energy * 0.25 + f.pulse * 0.35 + f.flash * 0.4) * f.intensity;
    c.beginPath();
    for(i = 0; i <= 64; i++){
      var t = i / 64 * Math.PI * 2, wob = 1 + Math.sin(t * (3 + k % 3) + f.t * 2) * (0.04 + f.bands.mid * 0.25) * f.intensity;
      var x = f.W / 2 + Math.cos(t) * r * wob, y = f.H / 2 + Math.sin(t) * r * wob;
      i ? c.lineTo(x, y) : c.moveTo(x, y);
    }
    c.closePath();
    c.strokeStyle = rgba(mix(th.colors, k / N + f.beat * 0.02), a);
    c.lineWidth = (1 + p * 6 + f.pulse * 4) * f.intensity; c.stroke();
  }
  if(f.flash > 0.01){ c.fillStyle = rgba(mix(th.colors, 0), f.flash * 0.5 * f.intensity); c.fillRect(0, 0, f.W, f.H); }
};

var P = [];                                    // particles live across frames
MODES.particles = function(c, f, th){
  var i, p;
  if(f.pass === 0){
    if(f.kick) for(i = 0; i < 40 * f.intensity; i++){ var a = Math.random() * Math.PI * 2, v = (2 + Math.random() * 6) * (1 + f.energy);
      P.push({x: f.W / 2, y: f.H / 2, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, c: Math.random()}); }
    var drift = f.bands.high * 3 * f.intensity;
    for(i = P.length - 1; i >= 0; i--){ p = P[i];
      p.vx += (Math.random() - 0.5) * drift; p.vy += (Math.random() - 0.5) * drift - 0.02;
      p.x += p.vx; p.y += p.vy; p.vx *= 0.985; p.vy *= 0.985; p.life -= 0.006 + f.bands.high * 0.01;
      if(p.life <= 0 || p.x < 0 || p.x > f.W || p.y < 0 || p.y > f.H){ P[i] = P[P.length - 1]; P.pop(); } }
    if(P.length > 900) P.splice(0, P.length - 900);   // ponytail: hard cap; a pool if it ever stutters
  }
  for(i = 0; i < P.length; i++){ p = P[i];
    c.fillStyle = rgba(mix(th.colors, p.c + f.t * 0.05), p.life * 0.9);
    var r = (1 + p.life * 3) * f.intensity; c.fillRect(p.x - r, p.y - r, r * 2, r * 2); }
};

MODES.feedback = function(c, f, th){
  if(f.pass === 0){                            // last frame, turned and zoomed, under this one
    c.save(); c.globalCompositeOperation = "source-over"; c.globalAlpha = 0.96;
    c.translate(f.W / 2, f.H / 2); c.rotate((0.006 + f.bands.bass * 0.02) * f.intensity);
    var z = 1.015 + f.pulse * 0.03; c.scale(z, z);
    c.drawImage(c.canvas, -f.W / 2, -f.H / 2, f.W, f.H); c.restore();
  }
  var sides = 3 + (f.beatIndex % 4), R = Math.min(f.W, f.H) * (0.08 + f.bands.bass * 0.25 + f.pulse * 0.1) * f.intensity;
  c.beginPath();
  for(var i = 0; i <= sides; i++){ var a = i / sides * Math.PI * 2 + f.t * 0.5 + f.beatPhase;
    var x = f.W / 2 + Math.cos(a) * R, y = f.H / 2 + Math.sin(a) * R; i ? c.lineTo(x, y) : c.moveTo(x, y); }
  c.strokeStyle = rgba(mix(th.colors, f.beat * 0.1), 0.7); c.lineWidth = 3 * f.intensity; c.stroke();
};

MODES.terrain = function(c, f, th){          /* a wireframe landscape the bass builds */
  var rows = 12, cols = 28, horizon = f.H * 0.42;
  if(f.pass !== 0) return;                    /* symmetry would just blur it */
  for(var r = 0; r < rows; r++){
    var z = r / rows, zz = (z + (f.beat * 0.12) % (1 / rows)) % 1;
    var y = horizon + (f.H - horizon) * zz * zz * 1.2;
    var amp = (f.bands.sub * 60 + f.bands.bass * 40 + f.pulse * 50) * (1 - zz) * f.intensity;
    c.beginPath();
    for(var q = 0; q <= cols; q++){
      var x = f.W * (q / cols), mid = Math.abs(q / cols - 0.5) * 2;
      var h = Math.sin(q * 1.7 + r * 2.3 + f.t * 1.5) * amp * (0.3 + f.bands.mid) * (1 - mid * 0.6);
      var yy = y - Math.max(0, h);
      q ? c.lineTo(x, yy) : c.moveTo(x, yy);
    }
    c.strokeStyle = rgba(mix(th.colors, zz + f.t * 0.03), (0.12 + (1 - zz) * 0.5) * f.intensity);
    c.lineWidth = 1 + (1 - zz) * 2; c.stroke();
  }
  if(f.flash > 0.01){ c.fillStyle = rgba(mix(th.colors, 0), f.flash * 0.4); c.fillRect(0, 0, f.W, f.H); }
};

/* viz auto: the section picks the mode. We composed the song; the canvas reads the score. */
var AUTO = {intro: "scope", build: "feedback", drop: "tunnel", "break": "particles",
            verse: "terrain", outro: "spectrum"};
function autoFor(role){ return AUTO[role] || "tunnel"; }

/* -- runtime --------------------------------------------------------------- */

var S = {mode: "tunnel", theme: "acid", intensity: 1, decay: 0.15, symmetry: 4};
var eng = null, cv = null, cx = null, W = 0, H = 0, raf = 0, reduce = false;
var last = 0, lastStep = -1, lastSection = null, pulse = 0, flash = 0, prevBeat = -1;

function size(){ var d = Math.min(devicePixelRatio || 1, 1.5);
  W = cv.width = Math.floor(innerWidth * d); H = cv.height = Math.floor(innerHeight * d);
  cv.style.width = innerWidth + "px"; cv.style.height = innerHeight + "px"; }

function frameFor(E, now){
  var f = {t: now, W: W, H: H, bpm: E.bpm, beat: 0, beatIndex: 0, beatPhase: 0, barPhase: 0, section: "", role: "",
           within: 0, bars: 8, left: 8, next: "", energy: 0.3, bands: {sub: 0, bass: 0, mid: 0, high: 0},
           wave: null, spectrum: null, playing: false, kick: false, intensity: S.intensity};
  var c = E.ctx, an = E.analyser;
  if(an){ f.spectrum = new Uint8Array(an.frequencyBinCount); an.getByteFrequencyData(f.spectrum);
          f.wave = new Float32Array(an.fftSize); an.getFloatTimeDomainData(f.wave);
          f.bands = bands(f.spectrum, c.sampleRate / an.fftSize); }
  var step = -1;
  if(E.playing && c){
    var ph = clockPhase(E.step, E._next, c.currentTime, E.bpm, E.songbar); Object.assign(f, ph); f.playing = true;
    if(E.song){ var u = upcoming(E.song, ph.bar, ph.barPhase); if(u) Object.assign(f, u); }
    step = Math.floor(ph.pos); var kt = E.tracks.kick, i = E._index(step), ch = kt && kt.pat && !kt.mute && kt.pat[i % kt.pat.length];
    f.kick = step !== lastStep && !!ch && ch !== "." && ch !== "-";
  } else if(E._decks){                          /* DECK mode: the rendered grid and its section marks */
    var d = [E._decks.a, E._decks.b].filter(function(x){ return x.playing && x.r; })[0];
    if(d){ var p = d.pos(), b = d.beatAt(p), m = d.r.marks, k = 0, j;
      f.beat = b + d.phaseAt(c.currentTime); f.beatIndex = b; f.beatPhase = f.beat - b; f.barPhase = (f.beat % 4) / 4;
      f.playing = true; f.bpm = d.bpm(); f.kick = b !== prevBeat; prevBeat = b;
      for(j = 0; j < m.length; j++) if(m[j][0] <= p + 0.01) k = j;
      if(m.length){ var spb = 240 / d.r.bpm, end = k + 1 < m.length ? m[k + 1][0] : d.r.seconds;
        f.section = m[k][1]; f.role = f.section.replace(/\d+$/, ""); f.within = (p - m[k][0]) / spb;
        f.bars = (end - m[k][0]) / spb; f.left = f.bars - f.within; f.energy = ENERGY[f.role] || 0.5;
        f.next = k + 1 < m.length ? m[k + 1][1].replace(/\d+$/, "") : ""; } }
  }
  lastStep = step;
  if(f.kick) pulse = 1;
  if(f.section !== lastSection){ if(f.role === "drop" && lastSection !== null) flash = 1; lastSection = f.section; }
  pulse *= 0.85; flash *= 0.92;
  f.pulse = pulse; f.flash = flash;
  /* anticipation: a build accelerates over its length, the last bar before a drop sprints */
  f.rush = Math.min(2, (f.role === "build" ? f.within / f.bars : 0) + (f.next === "drop" && f.left < 1 ? 1 - f.left : 0));
  return f;
}

function tick(now){
  raf = requestAnimationFrame(tick);
  if(now - last < 15) return; last = now;    // ~60fps cap on faster displays
  var th = THEMES[S.theme] || THEMES.acid, f = frameFor(eng, now / 1000);
  var mode = S.mode === "auto" ? autoFor(f.playing ? f.role : "intro") : S.mode;
  var draw = MODES[mode];
  if(!draw) return;
  cx.globalCompositeOperation = "source-over"; cx.globalAlpha = 1;
  cx.fillStyle = rgba(hex(th.bg), S.decay); cx.fillRect(0, 0, W, H);
  cx.globalCompositeOperation = "lighter";
  for(var k = 0; k < S.symmetry; k++){
    f.pass = k; cx.save();
    if(k){ cx.translate(W / 2, H / 2); cx.rotate(k * Math.PI * 2 / S.symmetry); if(k % 2) cx.scale(1, -1); cx.translate(-W / 2, -H / 2); }
    draw(cx, f, th); cx.restore();
  }
  cx.globalCompositeOperation = "source-over";
}

function run(){ if(cv && !raf && S.mode !== "off" && !document.hidden) raf = requestAnimationFrame(tick); }
function halt(){ if(raf) cancelAnimationFrame(raf); raf = 0; }

function persist(){
  var v = {mode: S.mode, theme: S.theme, intensity: S.intensity, decay: S.decay, symmetry: S.symmetry};
  try{ localStorage.setItem("oontz_viz", JSON.stringify(v)); }catch(e){}
  if(eng && eng.song) eng.song.viz = v;
}
function apply(v){                               // a stored/song look, validated field by field
  if(!v) return;
  if(v.mode === "off" || v.mode === "auto" || MODES[v.mode]) S.mode = v.mode;
  if(THEMES[v.theme]) S.theme = v.theme;
  Object.keys(PARAMS).forEach(function(k){ var x = parseParam(k, v[k]); if(x != null) S[k] = x; });
}

var VIZ = {
  THEMES: THEMES, MODES: MODES, autoFor: autoFor, parseParam: parseParam, mix: mix, clockPhase: clockPhase, bands: bands, upcoming: upcoming,
  status: function(){ return {mode: S.mode, theme: S.theme, intensity: S.intensity, decay: S.decay, symmetry: S.symmetry, reduced: reduce}; },
  start: function(E){
    eng = E; cv = document.getElementById("viz"); if(!cv) return; cx = cv.getContext("2d");
    reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if(reduce) S.mode = "off";
    try{ apply(JSON.parse(localStorage.getItem("oontz_viz"))); }catch(e){}
    size(); addEventListener("resize", size);
    document.addEventListener("visibilitychange", function(){ if(document.hidden) halt(); else run(); });
    run();
  },
  mode: function(m){
    if(m !== "off" && m !== "auto" && !MODES[m]) return false;
    S.mode = m; persist();
    if(m === "off"){ halt(); if(cx) cx.clearRect(0, 0, W, H); } else run();
    return true;
  },
  set: function(k, v){
    var x = parseParam(k, v); if(x == null) return null;
    S[k === "palette" ? "theme" : k] = x; persist(); return x;
  },
  theme: function(name){
    var th = THEMES[name]; if(!th) return null;
    S.theme = name; S.intensity = th.intensity; S.decay = th.decay; S.symmetry = th.symmetry; persist(); return th;
  },
  song: function(sg){                            // a song that carries its look gets it, unless the OS asked for calm
    if(!sg || !sg.viz) return; var m = S.mode; apply(sg.viz); if(reduce) S.mode = m;
    if(S.mode === "off") halt(); else run();
  }
};
global.OONTZ_VIZ = VIZ;
})(typeof window !== "undefined" ? window : globalThis);
