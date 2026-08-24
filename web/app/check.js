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

console.log("web checks pass  ·  write-through · pads · viz · touch · notes · roll · jumps · decks · theory (" + checked + " plans in window) · legible · " + OZ.KEYS.length + " keys listed");
