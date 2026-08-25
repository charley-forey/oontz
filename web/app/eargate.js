/* eargate.js — the first automated listener over generated music.
 *
 *     node web/app/eargate.js
 *
 * Every other gate in this repo is structural. `golden renders` hashes twelve
 * frozen hand-authored files and cannot tell better from worse (--bless erases
 * either); `composers agree` compares section lengths; check.js asserts on the
 * song model and the FFT. None of them would notice if the generator started
 * producing worse music, and for a while it was: seven of the fifteen genres fell
 * through to the techno kit, so jungle was four-on-the-floor at 168 BPM, and the
 * seeded rng's first draw was so nearly a linear function of its seed that every
 * early decision came out identical whatever seed you passed.
 *
 * So this one asks three questions of the composer's actual output:
 *   1. is a genre distinguishable from the other fourteen?
 *   2. is a seed distinguishable from another seed?
 *   3. does what it writes obey the theory it is graded by?
 *
 * It runs in node - ear.js's maths is pure - so it needs no browser. What it
 * cannot do is render (no OfflineAudioContext here); browsergate covers that.
 */
"use strict";
require("./oontz.js");
require("./theory.js");
require("./compose.js");
require("./ear.js");

var OZ = globalThis.oontz, CO = globalThis.OONTZ_COMPOSE, T = globalThis.OONTZ_THEORY;
var A = require("assert");

var FAIL = 0, PASS = 0;
function t(name, fn){
  try { var d = fn(); PASS++; console.log("  ok    " + name + (d ? "   " + d : "")); }
  catch (e) { FAIL++; console.log("  FAIL  " + name + "   " + (e && e.message || e)); }
}

var GENRES = Object.keys(T.genres).sort();
var SEEDS = [1, 2, 3, 7, 42, 99, 500, 999];

/* One representative section per song: the loudest, where everything plays. */
function drop(sg){
  var best = null;
  sg.order.forEach(function(n){
    var s = sg.sections[n];
    if (!best || s.energy > sg.sections[best].energy) best = n;
  });
  return sg.sections[best];
}
function sig(sg){
  var d = drop(sg);
  return {
    bpm: sg.bpm, groove: sg.groove, key: sg.key,
    kick: (d.tracks.kick && d.tracks.kick.pat.slice(0, 16)) || "",
    voices: Object.keys(d.tracks).map(function(k){ return d.tracks[k].voice; }).sort().join(","),
    shape: sg.order.map(function(n){ return sg.sections[n].role; }).join(">")
  };
}
function patterns(sg){
  var out = {};
  sg.order.forEach(function(n){
    var s = sg.sections[n];
    Object.keys(s.tracks).forEach(function(k){ out[n + "." + k] = s.tracks[k].pat || ""; });
  });
  return out;
}

/* ---------------------------------------------- 1. a genre must mean something */

t("every genre has its own kit", function(){
  var missing = GENRES.filter(function(g){ return !(T.kits || {})[g]; });
  A.ok(!missing.length, "no kit for: " + missing.join(", "));
  return GENRES.length + " genres, " + Object.keys(T.kits).length + " kits";
});

t("every genre has a groove", function(){
  var missing = GENRES.filter(function(g){ return !T.genre_groove[g]; });
  A.ok(!missing.length, "no groove for: " + missing.join(", "));
  var bad = GENRES.filter(function(g){ return !T.grooves[T.genre_groove[g]]; });
  A.ok(!bad.length, "groove names that do not exist: " + bad.join(", "));
});

t("genres are distinguishable from each other", function(){
  var kicks = {}, tempos = {}, voices = {};
  GENRES.forEach(function(g){
    var s = sig(CO.compose(g, 3, "classic", 7));
    (kicks[s.kick] = kicks[s.kick] || []).push(g);
    tempos[s.bpm] = 1;
    voices[s.voices] = 1;
  });
  /* Four-on-the-floor is correct for a lot of techno, so identical kicks are not
     a failure by themselves - but the whole roster sharing one is. */
  var biggest = Object.keys(kicks).sort(function(a, b){ return kicks[b].length - kicks[a].length; })[0];
  A.ok(kicks[biggest].length <= 8,
    "too many genres share one kick (" + kicks[biggest].length + "): " + kicks[biggest].join(", "));
  A.ok(Object.keys(tempos).length >= 10, "only " + Object.keys(tempos).length + " distinct tempos");
  A.ok(Object.keys(voices).length >= 8, "only " + Object.keys(voices).length + " distinct voice sets");
  return Object.keys(kicks).length + " kicks, " + Object.keys(tempos).length +
    " tempos, " + Object.keys(voices).length + " voice sets";
});

t("a genre sounds like what theory says it is", function(){
  GENRES.forEach(function(g){
    var sg = CO.compose(g, 3, "classic", 7), gen = T.genres[g];
    A.ok(sg.bpm >= gen.bpm[0] - 2 && sg.bpm <= gen.bpm[1] + 2,
      g + " composed at " + sg.bpm + " BPM, outside its " + gen.bpm.join("-") + " range");
    A.strictEqual(sg.groove, T.genre_groove[g], g + " did not use its own groove");
  });
  return "tempo and feel match theory for all " + GENRES.length;
});

t("garage does not sound straight", function(){
  /* theory.py's own note: "the kick skips beat three and the shuffle is the
     groove. If it sounds straight, it is wrong." It was straight. */
  var sg = CO.compose("garage", 3, "classic", 7), d = drop(sg);
  A.strictEqual(sg.groove, "swung", "garage is not swung");
  var kick = d.tracks.kick.pat.slice(0, 16);
  A.strictEqual(kick[8], ".", "the garage kick is on beat three: " + kick);
  return kick;
});

t("jungle is not four-on-the-floor", function(){
  var sg = CO.compose("jungle", 3, "classic", 7), d = drop(sg);
  var kick = d.tracks.kick.pat.slice(0, 16);
  A.notStrictEqual(kick, "x...x...x...x...", "jungle at " + sg.bpm + " BPM is four-on-the-floor");
  return kick + " at " + sg.bpm;
});

/* ------------------------------------------------- 2. a seed must mean something */

t("seeds change more than the key", function(){
  var a = CO.compose("hardtechno", 3, "classic", 1);
  var b = CO.compose("hardtechno", 3, "classic", 999);
  var pa = patterns(a), pb = patterns(b);
  var keys = Object.keys(pa), differ = keys.filter(function(k){ return pb[k] !== pa[k]; });
  A.ok(differ.length >= keys.length * 0.2,
    "only " + differ.length + " of " + keys.length + " patterns differ between seeds");
  return differ.length + "/" + keys.length + " patterns differ";
});

t("seeds reach different shapes and keys", function(){
  var shapes = {}, keys = {};
  SEEDS.forEach(function(s){
    var sg = CO.compose("hardtechno", 3, null, s);
    shapes[sg.order.map(function(n){ return sg.sections[n].role; }).join(">")] = 1;
    keys[sg.key] = 1;
  });
  A.ok(Object.keys(shapes).length >= 3,
    "only " + Object.keys(shapes).length + " distinct arrangements over " + SEEDS.length + " seeds");
  A.ok(Object.keys(keys).length >= 3, "only " + Object.keys(keys).length + " distinct keys");
  return Object.keys(shapes).length + " shapes, " + Object.keys(keys).length + " keys";
});

t("the seeded rng does not correlate with its seed", function(){
  /* The old LCG's first draw was 0.2364, 0.2368, 0.2372 for seeds 1, 2, 3. */
  var firsts = [1, 2, 3, 4, 5, 6, 7, 8].map(function(s){
    return CO.compose("techno", 2, null, s).key;
  });
  var spread = {}; firsts.forEach(function(k){ spread[k] = 1; });
  A.ok(Object.keys(spread).length >= 3,
    "eight seeds produced " + Object.keys(spread).length + " keys - the rng is correlated with its seed");
  return firsts.join(" ");
});

t("an explicit curve is still honoured", function(){
  Object.keys(T.templates).forEach(function(c){
    A.strictEqual(CO.compose("techno", 3, c, 5).meta.curve, c, c + " was ignored");
  });
  return Object.keys(T.templates).length + " curves";
});

/* --------------------------------------- 3. what it writes must obey the theory */

t("every generated song passes its own arrangement grader", function(){
  var worst = 100, worstAt = "";
  GENRES.forEach(function(g){
    SEEDS.slice(0, 4).forEach(function(s){
      var sg = CO.compose(g, 4, null, s);
      var sc = CO.score(CO.critique(sg));
      if (sc < worst) { worst = sc; worstAt = g + "/" + s; }
      var bad = CO.critique(sg).filter(function(c){ return c[0] === "bad"; });
      A.ok(!bad.length, g + " seed " + s + ": " + (bad[0] && bad[0][1]));
    });
  });
  return GENRES.length * 4 + " songs, worst score " + worst + " (" + worstAt + ")";
});

t("sections stay phrase-aligned", function(){
  GENRES.forEach(function(g){
    var sg = CO.compose(g, 5, null, 3);
    sg.order.forEach(function(n){
      var s = sg.sections[n];
      A.strictEqual(s.bars % 8, 0, g + "/" + n + " is " + s.bars + " bars");
    });
  });
});

t("patterns are legal and phrase-length", function(){
  GENRES.forEach(function(g){
    var sg = CO.compose(g, 3, null, 11);
    sg.order.forEach(function(n){
      var s = sg.sections[n];
      Object.keys(s.tracks).forEach(function(k){
        var p = s.tracks[k].pat || "";
        A.ok(/^[xXoO.\-]*$/.test(p), g + "/" + n + "/" + k + " has an illegal pattern: " + p);
        A.ok(p.length <= 16 || p.length % 16 === 0,
          g + "/" + n + "/" + k + " is " + p.length + " steps - not a whole number of bars");
        var tr = s.tracks[k];
        if (tr.notes) A.strictEqual(tr.notes.length, p.length,
          g + "/" + n + "/" + k + ": " + tr.notes.length + " notes for " + p.length + " steps");
      });
    });
  });
});

t("the voices it reaches are real circuits", function(){
  var used = {};
  GENRES.forEach(function(g){
    SEEDS.slice(0, 3).forEach(function(s){
      var sg = CO.compose(g, 3, null, s);
      sg.order.forEach(function(n){
        Object.keys(sg.sections[n].tracks).forEach(function(k){
          used[sg.sections[n].tracks[k].voice] = 1;
        });
      });
    });
  });
  var names = Object.keys(used).sort();
  names.forEach(function(v){ A.ok(OZ.VOICES[v], "the composer emits '" + v + "', which is not a voice"); });
  A.ok(names.length >= 14, "the composer only reaches " + names.length + " voices: " + names.join(","));
  return names.length + " voices: " + names.join(" ");
});

/* ------------------------------------------------------- harmony that moves */

t("the break plays a progression, not one held chord", function(){
  var moved = 0, checked = 0;
  GENRES.forEach(function(g){
    var sg = CO.compose(g, 4, "classic", 7), brk = null;
    sg.order.forEach(function(n){ if(sg.sections[n].role === "break" && !brk) brk = sg.sections[n]; });
    if(!brk || !brk.tracks.pad) return;
    checked++;
    var roots = brk.tracks.pad.notes.filter(function(x){ return x !== "."; });
    A.ok(roots.length >= 2, g + ": the pad plays " + roots.length + " chord(s)");
    var uniq = {}; roots.forEach(function(r){ uniq[r] = 1; });
    if(Object.keys(uniq).length > 1) moved++;
    A.ok(T.harmony.progressions[sg.meta.progression], g + " names an unknown progression");
  });
  A.ok(checked >= 8, "only " + checked + " genres have a break with a pad");
  /* static_i is a legitimate choice for the hypnotic genres, so not all move. */
  A.ok(moved >= checked / 2, "only " + moved + " of " + checked + " breaks actually change chord");
  return moved + " of " + checked + " breaks move";
});

t("a voicing never puts a minor third over a major chord", function(){
  GENRES.forEach(function(g){
    var sg = CO.compose(g, 4, "classic", 7), brk = null;
    sg.order.forEach(function(n){ if(sg.sections[n].role === "break" && !brk) brk = sg.sections[n]; });
    if(!brk || !brk.tracks.pad) return;
    var prog = T.harmony.progressions[sg.meta.progression];
    var qualities = {}; prog.forEach(function(st){ qualities[st[1]] = 1; });
    var ivals = brk.tracks.pad.ivals || [];
    if(Object.keys(qualities).length > 1)
      A.ok(ivals.indexOf(3) < 0 && ivals.indexOf(4) < 0,
        g + " voices a mixed progression with a third: [" + ivals + "]");
  });
  return "mixed progressions stay quality-neutral";
});

console.log(FAIL ? "  eargate FAILED (" + FAIL + ")" : "  eargate pass  ·  " + PASS + " checks");
process.exit(FAIL ? 1 : 0);
