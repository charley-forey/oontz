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

console.log("web checks pass  ·  write-through · pads · notes · roll · jumps · " + OZ.KEYS.length + " keys listed");
