/* The web gate. `node web/app/check.js`. No framework: each assert names what
 * broke. Covers the pure half of the engine - the song model, the key table, the
 * roll arithmetic, write-through - because that is what node can see. */
"use strict";
require("./oontz.js");
var OZ = globalThis.oontz;
var A = require("assert");

function song(){
  return {name: "t", bpm: 140, key: "a", scale: "minor", order: ["intro", "drop"],
    sections: {
      intro: {bars: 8, role: "intro", energy: 0.3, tracks: {kick: {voice: "kick", pat: "x...x...x...x...", gain: 1}}, order: ["kick"]},
      drop:  {bars: 8, role: "drop", energy: 1.0, order: ["kick", "bass"],
              tracks: {kick: {voice: "kick", pat: "x...x...x...x...", gain: 1},
                       bass: {voice: "bass", pat: "x.x.x.x.x.x.x.x.", gain: 1,
                              notes: "a1 . a1 . c2 . a1 . a1 . a1 . g1 . a1 .".split(" ")}}}
    }};
}

var E = new OZ.Engine();
var sg = song();
E.loadSong(sg);

/* -- write-through: a live edit survives stateAt() rebuilding the bar ------ */
E.setTrack("kick", {pat: "x.x.x.x.x.x.x.x."});
A.strictEqual(OZ.stateAt(sg, 0).tracks.kick.pat, "x.x.x.x.x.x.x.x.", "setTrack did not reach the section");
A.strictEqual(OZ.stateAt(sg, 9).tracks.kick.pat, "x...x...x...x...", "edit leaked out of its section");
E.setTrack("hat", {pat: "..x...x...x...x."});
A.ok(sg.sections.intro.order.indexOf("hat") >= 0 && E.order.indexOf("hat") >= 0, "a new track must join both orders");

/* -- pads cycle . -> x -> X -> . on the focused track ---------------------- */
E.focus = "kick";
A.strictEqual(E.key("w", true), "kick xxx.x.x.x.x.x.x.", "pad w should set step 2");
A.strictEqual(E.key("w", true), "kick xXx.x.x.x.x.x.x.", "pad w again should accent");
A.strictEqual(E.key("w", true), "kick x.x.x.x.x.x.x.x.", "pad w a third time should clear");
A.strictEqual(E.key("2", true), "focus hat", "2 focuses the second track");
A.strictEqual(E.key("q", true), "hat x.x...x...x...x.", "pads follow focus");

/* -- a click on the rack takes the same path as the pad key ---------------- */
E.focus = "kick";
var before = E.tracks.kick.pat;
var viaClick = E.toggleStep("kick", 1);
A.strictEqual(viaClick, "kick " + E.tracks.kick.pat, "toggleStep reports what it did");
A.notStrictEqual(E.tracks.kick.pat, before, "a click must change the pattern");
A.strictEqual(OZ.stateAt(sg, 0).tracks.kick.pat, E.tracks.kick.pat, "a click writes through to the song");
E.key("w", true); E.key("w", true);            // cycle back to where it started

/* -- a pitched track keeps notes aligned to hits --------------------------- */
E.jump(8);                                   // into the drop, where bass lives
A.strictEqual(E.songbar, 8);
E.focus = "bass";
E.key("w", true);                             // step 2 was a rest
A.strictEqual(E.tracks.bass.notes[1], "a1", "a new hit borrows the first real note");
E.key("w", true);
A.strictEqual(E.tracks.bass.notes[1], "a1!", "an accented hit accents the note");
E.key("w", true);
A.strictEqual(E.tracks.bass.notes[1], ".", "clearing the hit clears the note");
A.strictEqual(sg.sections.drop.tracks.bass.notes[1], ".", "notes write through too");

/* -- mute / solo ---------------------------------------------------------- */
A.strictEqual(E.key("z", true), "bass muted");
A.strictEqual(E.key("z", true), "bass on");
A.strictEqual(E.key("x", true), "solo bass");
A.strictEqual(E.tracks.kick.mute, true, "solo mutes the others");
A.strictEqual(E.tracks.bass.mute, false, "solo keeps the focused track");
E.key("x", true);
A.strictEqual(E.tracks.kick.mute, false, "solo off restores");

/* -- the roll freezes the index, the step count keeps running -------------- */
E.roll = null; E.step = 37;                   // sounding index 4 (step 36)
A.strictEqual(E._index(37), 5);
E.key("/", true);
A.deepStrictEqual(E.roll, {i: 4, step: 37, len: 1});
for(var s = 37; s < 45; s++) A.strictEqual(E._index(s), 4, "held roll repeats the frozen 16th");
A.strictEqual(E.key("/", false), "roll off");
A.strictEqual(E._index(45), 13, "release lands where the track would have been");

/* -- section jumps -------------------------------------------------------- */
E.jump(0);
A.strictEqual(E.key(">", true), "-> drop");
A.strictEqual(E.songbar, 8);
A.strictEqual(E.key("<", true), "-> intro");
A.strictEqual(E.songbar, 0);
A.strictEqual(E.key("<", true), "-> drop", "previous from the first section wraps");
A.strictEqual(E.songbar, 8);

/* -- tempo / swing clamp -------------------------------------------------- */
E.setBpm(999); A.strictEqual(E.bpm, 220);
E.key("=", true); A.strictEqual(E.bpm, 220, "tempo clamps at 220");
A.strictEqual(sg.bpm, 220, "tempo keys write to the song");
E.swing = 58; E.key(".", true); E.key(".", true); A.strictEqual(E.swing, 60);

/* -- keys the engine does not own are left alone --------------------------- */
A.strictEqual(E.key("F5", true), null);
A.strictEqual(E.key("[", true), "filter 18868 Hz", "the sweep works without an AudioContext");

/* -- the table the ? key prints covers every key the engine handles -------- */
var listed = OZ.KEYS.map(function(kv){ return kv[0]; }).join(" ");
["space", "1-8", "z / x", "[ ]", "/", "\\", "`", "- =", ", .", "< >", "R", "?"].forEach(function(k){
  A.ok(listed.indexOf(k) >= 0, "KEYS table is missing " + k);
});

/* -- decks: the grid is exact, sync holds phase, the crossfader is equal power - */
var sg2 = song(); sg2.bpm = 128; sg2.sections.drop.bpm = 128; sg2.sections.intro.bpm = 128;
var gA = OZ.gridFor(sg), gB = OZ.gridFor(sg2);
A.strictEqual(gA.grid.length, 16 * 4, "4 beats per bar on the grid");
A.ok(Math.abs(gA.grid[4] - 240 / 220) < 1e-9, "beat 4 is one bar in, at the song's bpm (220 after the clamp test)");
A.deepStrictEqual(gA.marks.map(function(m){ return m[1]; }), ["intro", "drop"], "a mark at every section start");
A.ok(Math.abs(gA.seconds - 16 * 240 / 220) < 1e-9, "duration is the walked bar total");

var fakeE = {ctx: {currentTime: 10}, start: function(){ return this.ctx; }, master: {}};
var dA = new OZ.Deck(fakeE, "a"), dB = new OZ.Deck(fakeE, "b");
dA.r = Object.assign({buf: null, name: "a"}, gA); dB.r = Object.assign({buf: null, name: "b"}, gB);
dA.pos0 = 3.31;                                   // somewhere mid-beat, stopped
dB.pos0 = 7.0;
dB.syncTo(dA);
A.ok(Math.abs(dB.bpm() - dA.bpm()) < 1e-9, "sync matches tempo: " + dB.bpm() + " vs " + dA.bpm());
A.ok(Math.abs(dB.beatPhase() - dA.beatPhase()) < 1e-6, "sync matches beat phase: " + dB.beatPhase() + " vs " + dA.beatPhase());
dA.anchor = 10; dA.playing = true; dA.rate = 1;   // A is playing at rate 1 from t=10
A.ok(Math.abs(dA.posAt(12.5) - (3.31 + 2.5)) < 1e-9, "position is anchor arithmetic");
dA.setRate(1.25);                                 // re-anchors at now (10)
A.ok(Math.abs(dA.posAt(11) - (3.31 + 1.25)) < 1e-9, "a rate change re-anchors so position stays continuous");
dA.loop = [gA.grid[8], gA.grid[12]];              // a 4-beat loop
var L = gA.grid[12] - gA.grid[8];
A.ok(Math.abs(dA.posAt(10 + (gA.grid[8] - 3.31) / 1.25 + L * 1.7 / 1.25) - (gA.grid[8] + L * 0.7)) < 1e-6, "a loop wraps the read position");
var g = OZ.xfGains(0);
A.ok(Math.abs(g[0] * g[0] + g[1] * g[1] - 1) < 1e-9 && Math.abs(g[0] - g[1]) < 1e-9, "centre of the crossfader is equal power");
A.deepStrictEqual(OZ.xfGains(-1).map(Math.round), [1, 0], "hard left is all A");
A.deepStrictEqual(OZ.xfGains(1).map(Math.round), [0, 1], "hard right is all B");

/* -- one theory: the composer's tables come from theory.js, and it obeys them --- */
require("./theory.js"); require("./compose.js");
var T = globalThis.OONTZ_THEORY, CO = globalThis.OONTZ_COMPOSE;
A.ok(T && T.genres && T.arrangement && T.templates, "theory.js exports the corpus");
A.strictEqual(CO.GENRES.techno.bpm, T.genres.techno.sweet, "composer bpm is theory's sweet spot");
A.strictEqual(CO.TEMPLATES, T.templates, "composer templates are theory's, not a copy");
var checked = 0;
Object.keys(T.genres).forEach(function(style){ var gnr = T.genres[style];
  Object.keys(T.templates).forEach(function(curve){
    var plan = CO.arrange(5, curve, gnr.sweet, gnr.drop_at), total = 0, pre = 0, seen = false;
    plan.forEach(function(p){ total += p.bars; if(p.role === "drop") seen = true; if(!seen) pre += p.bars;
      A.ok(p.bars % 8 === 0 && p.bars >= 8, style + "/" + curve + ": " + p.role + " is " + p.bars + " bars"); });
    var at = pre / total;
    A.ok(at >= gnr.drop_at[0] - 0.04 && at <= gnr.drop_at[1] + 0.04,
      style + "/" + curve + " drops at " + Math.round(at * 100) + "%, window " + gnr.drop_at);
    checked++; }); });

/* -- viz: the pure half of the canvas ------------------------------------- */
require("./viz.js");
var V = globalThis.OONTZ_VIZ;
A.strictEqual(V.parseParam("symmetry", "5.4"), 5, "symmetry rounds to a mirror count");
A.strictEqual(V.parseParam("intensity", "99"), 2, "intensity clamps");
A.strictEqual(V.parseParam("decay", "junk"), null, "junk is not a param value");
A.strictEqual(V.parseParam("palette", "acid"), "acid", "palette accepts a theme");
A.strictEqual(V.parseParam("palette", "beige"), null, "beige is not a vibe");
A.deepStrictEqual(V.mix(["#000000", "#ffffff"], 0), [0, 0, 0], "mix t=0 is the first colour");
A.deepStrictEqual(V.mix(["#000000", "#ffffff"], 0.25), [128, 128, 128], "mix walks the palette");
var ph = V.clockPhase(8, 1.0, 1.0, 150, 0);       /* next 16th is now: playhead sits on step 8 */
A.ok(Math.abs(ph.beat - 2) < 1e-9 && ph.beatIndex === 2 && ph.beatPhase < 1e-9, "clockPhase: step 8 at 150bpm is beat 2");
ph = V.clockPhase(8, 1.1, 1.0, 150, 0);           /* scheduled 100ms ahead: the ear is behind the clock */
A.ok(ph.beat < 2, "clockPhase walks the lookahead back");
var spec = new Uint8Array(128); spec.fill(255, 1, 4);   /* energy only in the lowest bins */
var b = V.bands(spec, 43);                               /* ~43Hz per bin, like fftSize 1024 at 44.1k */
A.ok(b.sub > 0.8 && b.high === 0, "bands: sub-only spectrum reads as sub-only");
var vsg = song();
var up = V.upcoming(vsg, 7.5, 0.5);
A.ok(up.section === "intro" && up.next === "drop" && Math.abs(up.left) < 1e-9, "upcoming sees the drop coming");
A.ok(V.upcoming(vsg, 9, 0).energy === 1, "the drop carries its energy");

/* -- touch deck: the tables a phone plays from ----------------------------- */
require("./touch.js");
var TD = globalThis.OONTZ_TOUCH;
A.strictEqual(TD.PADS.join(""), "qwertyuiasdfghjk", "the 16 pads are the 16 pad keys");
A.strictEqual(TD.TRACKS.join(""), "12345678", "track buttons are the focus keys");
TD.ROW_MAIN.concat(TD.ROW_FX).forEach(function(k){
  A.ok(typeof k[0] === "string" && k[0].length === 1 && k[1], "every button is one real key with a label: " + k);
});
A.ok(TD.ROW_FX.filter(function(k){ return k[2]; }).length === 3, "exactly [ ] / are hold keys");

/* -- the page must stay readable: this bug shipped once ---------------------
   The scanlines and the vignette used to sit ABOVE the text, multiplying 30%
   black through every glyph and dropping 80% black over the HUD and prompt.
   And .dim carries most of the prose, so its contrast is not decoration. */
var fs = require("fs"), path = require("path");
var html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
function blockFor(sel){
  var i = html.indexOf(sel + "{");
  A.ok(i >= 0, "no CSS rule for " + sel);
  return html.slice(i, html.indexOf("}", i));
}
function zOf(sel){
  var b = blockFor(sel), k = b.indexOf("z-index:");
  A.ok(k >= 0, "no z-index for " + sel);
  return parseInt(b.slice(k + 8), 10);
}
var zWrap = zOf("#wrap");
["#scan", "#vig", "#bg", "#viz"].forEach(function(sel){
  A.ok(zOf(sel) < zWrap, sel + " (z " + zOf(sel) + ") must sit UNDER the text (z " + zWrap + ")");
});
A.ok(blockFor("#wrap").indexOf("text-shadow:var(--halo)") >= 0,
  "the text needs its halo to survive the visuals");

function lum(hex){
  var c = [1, 3, 5].map(function(i){ return parseInt(hex.substr(i, 2), 16) / 255; })
    .map(function(v){ return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a, b){ var l1 = lum(a), l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); }
function tok(name){
  var i = html.indexOf("--" + name + ":");
  A.ok(i >= 0, "token --" + name + " not found");
  return html.substr(html.indexOf("#", i), 7);
}
var bg = tok("bg");
[["fg", 7], ["dim", 4.5], ["bright", 7], ["accent", 4.5], ["accent2", 4.5], ["ok", 4.5], ["warn", 4.5], ["hot", 4.5]]
  .forEach(function(p){
    var r = ratio(tok(p[0]), bg);
    A.ok(r >= p[1], "--" + p[0] + " " + tok(p[0]) + " on " + bg + " is " + r.toFixed(1) +
      ":1, needs " + p[1] + ":1");
  });

/* the live grid belongs in the static rack, never in the scrolling log */
A.ok(/RACK\.innerHTML = h;/.test(html), "the grid must render into the rack");
/* only tail() may pin the log to the bottom; draw() used to do it every 16th note */
A.strictEqual(html.split("OUT.scrollTop = OUT.scrollHeight").length - 1, 1,
  "exactly one place may jump the log to the bottom, and it is tail()");

/* -- voices: the six former aliases now have their own circuits ------------- */
["hoover", "lead", "pluck", "fm", "screech", "chord"].forEach(function(v){
  A.ok(typeof OZ.VOICES[v] === "function" && OZ.VOICES[v] !== OZ.VOICES.stab && OZ.VOICES[v] !== OZ.VOICES.bass,
    v + " deserves its own circuit, not an alias");
});

/* -- a pitched track survives an edit in a later bar -------------------------
   toggleStep padded the notes lane to 16 while a pattern can be 128 long, so
   editing bar 2+ wrote past the end and left holes that silenced the track. */
var pe = new OZ.Engine();
var psong = song();
psong.sections.drop.tracks.bass.pat = new Array(9).join("x.x.x.x.x.x.x.x.");  // 8 bars
psong.sections.drop.bars = 8;
pe.loadSong(psong); pe.jump(8); pe.songbar = 10;                 // three bars into the drop
pe.focus = "bass";
pe.toggleStep("bass", 2);
var bt = pe.tracks.bass;
A.strictEqual(bt.notes.length, bt.pat.length, "the notes lane must match the pattern length");
A.ok(bt.notes.every(function(x){ return typeof x === "string"; }), "a hole was left in the notes lane");
A.strictEqual(bt.notes.indexOf(undefined), -1, "undefined in the notes lane silences the track");

/* -- the page must not run what a stranger published -------------------------
   A track name comes out of published JSON and lands in innerHTML; everything
   else in draw() was escaped and these two were not. And the model proposes
   music, never account actions - the server prompt claims the client refuses,
   so the client has to actually refuse. */
var drawFn = html.slice(html.indexOf("function draw()"), html.indexOf("psychedelic bg"));
A.strictEqual(drawFn.split("data-t=").length - 1, 2, "expected two data-t sites in draw()");
drawFn.split("data-t=").slice(1).forEach(function(chunk, i){
  A.ok(chunk.indexOf("esc(n)") === 1 || chunk.slice(0, 12).indexOf("esc(n)") >= 0,
    "data-t site " + (i + 1) + " does not escape the track name: " + chunk.slice(0, 30));
});
A.ok(html.indexOf("ps.filter(musical).forEach(run)") >= 0,
  "AI output must be filtered before it runs");

var mlist = html.slice(html.indexOf("var MUSICAL ="), html.indexOf("function musical("));
["publish", "login", "key", "handle", "playlist", "take", "rec", "export", "clear", "undo", "dload"]
  .forEach(function(v){
    A.ok(mlist.indexOf(v) < 0, "the AI allowlist must not contain " + v);
  });
["bpm", "gain", "sidechain", "compose", "grade"].forEach(function(v){
  A.ok(mlist.indexOf(v) >= 0, "the AI allowlist should contain " + v); });

/* -- the ear: a spectrum, and what it concludes ---------------------------- */
require("./ear.js");
var EAR = globalThis.OONTZ_EAR;
var SR = 44100;
function sine(hz, n){ var x = new Float32Array(n);
  for(var i = 0; i < n; i++) x[i] = Math.sin(2 * Math.PI * hz * i / SR); return x; }

var lo = EAR.bandEnergy(sine(50, 8192), SR), hi = EAR.bandEnergy(sine(12000, 8192), SR);
A.ok(lo[0] > 0.95, "a 50Hz tone must read as sub, got " + lo[0].toFixed(3));
A.ok(hi[5] > 0.95, "a 12kHz tone must read as air, got " + hi[5].toFixed(3));
A.ok(Math.abs(lo.reduce(function(a, b){ return a + b; }, 0) - 1) < 0.02, "bands should sum to ~1");
A.strictEqual(EAR.bandEnergy(new Float32Array(8192), SR)[0], 0, "silence has no energy anywhere");

/* A hit that is not on the downbeat must still be measured. One 8192-sample
   window covers 0.19s of a 1.6s bar, so measuring one window heard only step 0
   and reported every offbeat track as silent. */
var late = new Float32Array(SR);                 // one second, a 12kHz burst at 0.7s
var burst = sine(12000, 4096);
for(var b2 = 0; b2 < burst.length; b2++) late[Math.floor(SR * 0.7) + b2] = burst[b2];
var lateBands = EAR.bandEnergy(late, SR);
A.ok(lateBands[5] > 0.9, "a burst at 0.7s must be heard, got air=" + lateBands[5].toFixed(3));

/* mid/side: the same signal in both ears has no side energy; opposite is all side */
var t1 = sine(50, 8192), t2 = new Float32Array(t1.length);
for(var q = 0; q < t1.length; q++) t2[q] = -t1[q];
A.ok(EAR.lowMidSide(t1, t1, SR, 120).ratio < 0.01, "identical channels are mono");
A.ok(EAR.lowMidSide(t1, t2, SR, 120).ratio > 10, "inverted channels are all side");

/* the band a role owns, derived from theory's own numbers */
A.strictEqual(EAR.ownerOf("bass"), "kick", "the kick owns 60-250Hz, so a bass there is the guest");
A.strictEqual(EAR.ownerOf("air"), "hat", "the hat owns the air band");

/* fixWorst picks the worst thing and makes one real move */
function fakeSong(){
  return {name: "x", bpm: 140, order: ["drop"], sections: {drop: {bars: 8, role: "drop", energy: 1,
    order: ["kick", "bass", "hat"],
    tracks: {kick: {voice: "kick", pat: "x...x...x...x...", gain: 1},
             bass: {voice: "bass", pat: "x.x.x.x.x.x.x.x.", gain: 1, sc: 0, pan: 0.6},
             hat:  {voice: "hat",  pat: "..x...x...x...x.", gain: 1}}}}};
}
function meas(over){
  var m = {section: "drop", bar: 0, order: ["kick", "bass", "hat"],
    tracks: {kick: [0.5, 0.45, 0.03, 0.01, 0.01, 0], bass: [0.1, 0.6, 0.2, 0.05, 0.03, 0.02],
             hat: [0, 0.01, 0.02, 0.05, 0.2, 0.7]},
    master: {peak: 0.5, peakDb: -6, rms: 0.2, bands: [0.3, 0.3, 0.2, 0.1, 0.05, 0.05],
             low: {mid: 1, side: 0.01, ratio: 0.01}}};
  if(over) Object.keys(over).forEach(function(k){ m[k] = over[k]; });
  return m;
}

/* clipping outranks everything */
var sg3 = fakeSong();
var did = EAR.fixWorst(sg3, meas({master: {peak: 1.1, peakDb: 0.8, rms: 0.4,
  bands: [0.3, 0.3, 0.2, 0.1, 0.05, 0.05], low: {mid: 1, side: 0.01, ratio: 0.01}}}));
A.ok(/dB/.test(did), "a clipped master must be pulled down first: " + did);
A.ok(sg3.sections.drop.tracks.kick.gain < 1, "the pull must actually change gains");

/* then a wide low end gets centred */
var sg4 = fakeSong();
did = EAR.fixWorst(sg4, meas({master: {peak: 0.5, peakDb: -6, rms: 0.2,
  bands: [0.3, 0.3, 0.2, 0.1, 0.05, 0.05], low: {mid: 1, side: 0.5, ratio: 0.5}}}));
A.ok(/centred/.test(did), "a wide low end must be centred: " + did);
A.strictEqual(sg4.sections.drop.tracks.bass.pan, 0, "the offending track is panned back to centre");

/* the kick never gives way: if it is one of the pair, the other one moves */
var sg7 = fakeSong();
var km = meas();
km.share = EAR.shares({kick: [50, 45, 40, 0, 0, 0], bass: [10, 40, 45, 0, 0, 0],
                       hat: [0, 0, 0, 0, 0, 10]}, km.order);
did = EAR.fixWorst(sg7, km);
A.ok(did && !/^kick /.test(did), "the kick must never be the one trimmed: " + did);

/* two tracks merely present in a band is not masking; jointly owning it is */
var mild = meas();
mild.share = EAR.shares({kick: [50, 40, 30, 0, 0, 0], bass: [10, 30, 32, 0, 0, 0],
                         hat: [0, 0, 30, 0, 0, 10]}, mild.order);   // three-way split
A.ok(!EAR.critiqueMix(mild).some(function(c){ return c[0] === "bad" && /living in low-mid/.test(c[1]); }),
  "a three-way split in one band is a mix, not a fault");

/* then kick vs bass in the same band is a sidechain problem, not a level one */
var sg5 = fakeSong();
var m5 = meas();
m5.share = EAR.shares({kick: [50, 45, 5, 2, 1, 1], bass: [10, 45, 20, 5, 3, 2],
                       hat: [0, 1, 2, 5, 20, 70]}, m5.order);
did = EAR.fixWorst(sg5, m5);
A.ok(/sidechain/.test(did) && /bass/.test(did), "kick and bass in one band want ducking: " + did);
A.strictEqual(sg5.sections.drop.tracks.bass.sc, 0.8, "the guest gets ducked");

/* and it must eventually run out of things to say */
var sg6 = fakeSong();
sg6.sections.drop.tracks.bass.sc = 0.8; sg6.sections.drop.tracks.bass.pan = 0;
var clean = meas();
clean.share = EAR.shares({kick: [90, 70, 5, 2, 1, 1], bass: [5, 20, 60, 20, 2, 1],
                          hat: [0, 1, 2, 5, 25, 80]}, clean.order);   // one owner per band
A.strictEqual(EAR.fixWorst(sg6, clean), null, "a clean mix has nothing left to fix");

/* share: who actually owns the band, which is what masking means */
var sh = EAR.shares({a: [10, 0, 0, 0, 0, 0], b: [30, 0, 0, 0, 0, 0]}, ["a", "b"]);
A.ok(Math.abs(sh.a[0] - 0.25) < 1e-9 && Math.abs(sh.b[0] - 0.75) < 1e-9, "shares split the band by contribution");
A.strictEqual(EAR.shares({a: [0, 0, 0, 0, 0, 0]}, ["a"]).a[0], 0, "an empty band has no owner");

/* a ducked rumble sharing the low end with the kick is hard techno, not a fault */
var rum = meas();
rum.order = ["kick", "rumble"];
rum.tracks = {kick: [0.5, 0.4, 0.05, 0.03, 0.01, 0.01], rumble: [0.55, 0.4, 0.03, 0.01, 0, 0]};
rum.params = {kick: {gain: 1}, rumble: {gain: 0.5, sc: 0.8}};
rum.share = EAR.shares({kick: [45, 40, 5, 3, 1, 1], rumble: [55, 40, 3, 1, 0, 0]}, rum.order);
var rc = EAR.critiqueMix(rum);
A.ok(rc.some(function(c){ return c[0] === "good" && /that smear is the genre/.test(c[1]); }),
  "a ducked rumble must be allowed to share the low end: " + JSON.stringify(rc));
rum.params.rumble.sc = 0;                        // not ducked: now it really is eating the kick
A.ok(EAR.critiqueMix(rum).some(function(c){ return c[0] === "bad" && /living in/.test(c[1]); }),
  "an undicked rumble is still a fault");

/* the critique says what it measured, with the number */
var cm = meas();
cm.share = EAR.shares({kick: [50, 45, 5, 2, 1, 1], bass: [10, 45, 20, 5, 3, 2],
                       hat: [0, 1, 2, 5, 20, 70]}, cm.order);
var crit = EAR.critiqueMix(cm);
A.ok(crit.some(function(c){ return c[0] === "bad" && /kick and bass/.test(c[1]); }),
  "the conflict must be reported: " + JSON.stringify(crit));
A.ok(crit.every(function(c){ return ["good", "warn", "bad"].indexOf(c[0]) >= 0; }), "levels are good/warn/bad");
A.ok(EAR.critiqueMix(meas()).some(function(c){ return /-6.00 dBFS/.test(c[1]); }), "headroom is quoted");

/* -- midi: the note map a controller plays from ----------------------------- */
require("./midi.js");
var MD = globalThis.OONTZ_MIDI;
A.strictEqual(MD.keyForNote(36), "q", "note 36 is step 1");
A.strictEqual(MD.keyForNote(51), "k", "note 51 is step 16");
A.strictEqual(MD.keyForNote(52), "<", "note 52 walks a section back");
A.strictEqual(MD.keyForNote(35), null, "below the pads is nobody's key");
A.ok(MD.FILTER_CCS[74] && MD.FILTER_CCS[1], "cutoff and modwheel both sweep the filter");

var fs2 = require("fs"), path2 = require("path");
/* -- pwa: the shell the service worker promises must exist ------------------ */
var man = JSON.parse(fs2.readFileSync(path2.join(__dirname, "manifest.webmanifest"), "utf8"));
A.ok(man.icons.length && man.display === "standalone", "manifest is installable");
var sw = fs2.readFileSync(path2.join(__dirname, "sw.js"), "utf8");
(sw.match(/"\/[a-z.]+"/g) || []).forEach(function(q){
  var f = q.slice(2, -1); if(!f) return;
  A.ok(fs2.existsSync(path2.join(__dirname, f)), "sw.js precaches " + f + " but it does not exist");
});

/* -- new circuits and the auto canvas --------------------------------------- */
["bell", "donk", "wob", "air"].forEach(function(v){
  A.ok(typeof OZ.VOICES[v] === "function", v + " is missing from the browser bank");
});
A.ok(V.MODES.terrain, "terrain mode exists");
A.strictEqual(V.autoFor("drop"), "tunnel", "a drop blows out");
A.strictEqual(V.autoFor("break"), "particles", "a break drifts");
A.strictEqual(V.autoFor("nosuchrole"), "tunnel", "unknown roles still draw");

/* -- layout: the stage is one block, the deck folds -------------------------- */
var page = fs2.readFileSync(path2.join(__dirname, "index.html"), "utf8");
A.ok(page.indexOf('id="rack"') < page.indexOf('id="out"'), "the rack belongs to the stage, above the log");
A.ok(page.indexOf("sugPick") >= 0 && page.indexOf("#sug") >= 0, "the command dropdown exists and is pickable");
var touchSrc = fs2.readFileSync(path2.join(__dirname, "touch.js"), "utf8");
A.ok(touchSrc.indexOf("oontz_deck") >= 0 && touchSrc.indexOf(".shut") >= 0, "the deck must fold and remember");

/* -- the theme workshop and the cinema -------------------------------------- */
A.ok(V.MODES.stars && V.MODES.kaleido, "stars and kaleido exist");
A.ok(Object.keys(V.THEMES).length >= 12, "a dozen palettes minimum, got " + Object.keys(V.THEMES).length);
A.strictEqual(V.make("ACID!!", ["#ff0000", "#00ff00"]), null, "built-ins cannot be overwritten");
A.strictEqual(V.make("x", ["#nope", "#alsono"]), null, "junk hex is refused");
var made = V.make("teste2e", ["#ff0044", "#00ffcc", "#4400ff"]);
A.ok(made && V.THEMES.teste2e && made.colors.length === 3, "a custom theme registers");
A.ok(V.unmake("teste2e") && !V.THEMES.teste2e, "and can be deleted");
A.ok(/^#[0-9a-f]{6}$/.test(V.hslHex(200, 0.9, 0.55)), "hslHex emits hex");

/* -- songDiff: the demo that sells the format ------------------------------- */
var d1 = song(), d2 = JSON.parse(JSON.stringify(d1));
d2.bpm = 132; d2.sections.drop.tracks.kick.pat = "x..xx...x...x...";
d2.sections.break2 = {bars: 8, role: "break", tracks: {}, order: []};
d2.order.push("break2");
var dd = OZ.songDiff(d1, d2);
A.ok(dd.indexOf("bpm 140 \u2192 132") >= 0, "diff sees the bpm: " + dd);
A.ok(dd.some(function(l){ return l.indexOf("drop/kick:") === 0; }), "diff sees the pattern");
A.ok(dd.some(function(l){ return l.indexOf("+ section break2") === 0; }), "diff sees the new section");
A.deepStrictEqual(OZ.songDiff(d1, JSON.parse(JSON.stringify(d1))), ["identical, note for note"], "no-change is said plainly");

/* -- rooms: what broadcasts is exactly what is musical ------------------------ */
var pageSrc = fs2.readFileSync(path2.join(__dirname, "index.html"), "utf8");
A.ok(pageSrc.indexOf("function roomWire") >= 0 && pageSrc.indexOf("ws/room/") >= 0, "the room client exists");
A.ok(pageSrc.indexOf("ROOM.remote = true") >= 0, "remote commands must not re-broadcast");

console.log("web checks pass  ·  write-through · pads · viz · touch · midi · voices+4 · viz-auto · themes · stage · pwa · notes · roll · jumps · decks · diff · rooms · theory (" + checked + " plans in window) · legible · ear · " + OZ.KEYS.length + " keys listed");
