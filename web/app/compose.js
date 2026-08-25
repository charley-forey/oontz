/* Arrangement, in the browser. The port of oontz/compose.py + oontz/theory.py.
 *
 * A song is a walk along a shape. Section content follows its ROLE - an intro is
 * thin because it is an intro - and ONE motif is developed across the whole
 * track, which is the difference between a song and eight unrelated loops.
 *
 * The theory half grades what comes out, so generation can be argued with
 * instead of trusted.
 */
(function (g) {
"use strict";

var NAMES = ["c","c#","d","d#","e","f","f#","g","g#","a","a#","b"];
var SCALES = {
  minor:    [0,2,3,5,7,8,10],
  phrygian: [0,1,3,5,7,8,10],
  dorian:   [0,2,3,5,7,9,10],
  major:    [0,2,4,5,7,9,11],
  harmonic: [0,2,3,5,7,8,11]
};

/* The theory is not copied here. theory.js is generated from oontz/theory.py and
   must load first; what the composer needs is derived from it. */
var T = g.OONTZ_THEORY;
if(!T) throw new Error("theory.js must load before compose.js");
var GENRES = {};
Object.keys(T.genres).forEach(function(k){
  var t = T.genres[k];
  GENRES[k] = {bpm: t.sweet, key: t.key, drop: t.drop_at, phrase: t.phrase,
               swing: Math.round((t.swing[0] + t.swing[1]) / 2), note: t.note};
});
var TEMPLATES = T.templates, ROLE_BARS = T.role_bars;

function rng(seed){
  var s = (seed >>> 0) || 1;
  /* Mix the seed before the first draw. A bare LCG's first output is very nearly
     a linear function of its seed - 1 through 6 gave 0.2364, 0.2368, 0.2372,
     0.2376, 0.2380, 0.2384 - so every decision made early in a compose (the
     curve, the first motif note, the first hat rotation) came out the same
     whatever seed you passed. This is why "generate another one" gave you the
     same track. splitmix32 finish, then the same LCG. */
  s = (s ^ 0x9e3779b9) >>> 0;
  s = Math.imul(s ^ (s >>> 16), 0x21f0aaad) >>> 0;
  s = Math.imul(s ^ (s >>> 15), 0x735a2d97) >>> 0;
  s = (s ^ (s >>> 15)) >>> 0;
  return function(){ s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
}

function degToken(root, scale, deg, oct){
  var steps = SCALES[scale] || SCALES.minor;
  var base = NAMES.indexOf(root);
  var semi = base + steps[((deg % steps.length) + steps.length) % steps.length]
             + 12 * Math.floor(deg / steps.length);
  return NAMES[((semi % 12) + 12) % 12] + (oct + Math.floor(semi / 12));
}

/* A motif is scale DEGREES, so transposing can never leave the key. */
var CONTOURS = {
  static: [0,0,2,0,0,0,2,0], arch: [0,2,4,6,7,6,4,2],
  rising: [0,1,2,3,4,5,6,7], zigzag: [0,4,1,5,2,6,3,7]
};
function motif(rand, contour, len){
  var shape = CONTOURS[contour] || CONTOURS.static, out = [];
  for(var i = 0; i < len; i++){
    if(i > 0 && rand() < 0.25){ out.push(null); continue; }
    var d = shape[i % shape.length] + (rand() < 0.35 ? (rand() < 0.5 ? -1 : 1) : 0);
    out.push({deg: Math.max(0, d), accent: rand() < 0.3, slide: rand() < 0.2});
  }
  return out;
}
function motifTokens(m, root, scale, oct){
  return m.map(function(e){
    if(!e) return ".";
    return degToken(root, scale, e.deg, oct) + (e.slide ? "~" : "") + (e.accent ? "!" : "");
  });
}
function thin(m, rand, amount){
  return m.map(function(e, i){ return (i === 0 || rand() > amount) ? e : null; });
}
function densify(m, rand, amount){
  var last = 0;
  return m.map(function(e){
    if(e){ last = e.deg; return e; }
    return rand() < amount ? {deg: last, accent: false, slide: rand() < 0.3} : null;
  });
}

/* Distribute `bars` across `roles` in proportion to what each role wants, every
   section a multiple of 8 and never below 8. Phrasing is not negotiable, so the
   rounding remainder goes to the biggest section rather than being smeared. */
function share(roles, bars){
  if(!roles.length) return [];
  var want = roles.map(function(r){ return ROLE_BARS[r] || 16; });
  var tot = want.reduce(function(a, b){ return a + b; }, 0);
  var out = want.map(function(wv){
    return Math.max(8, Math.round(bars * wv / tot / 8) * 8); });
  var guard = 0;
  while(out.reduce(function(a, b){ return a + b; }, 0) > bars && guard++ < 200){
    var i = out.indexOf(Math.max.apply(null, out));
    if(out[i] <= 8) break;
    out[i] -= 8;
  }
  guard = 0;
  while(out.reduce(function(a, b){ return a + b; }, 0) < bars - 4 && guard++ < 200){
    var j = out.indexOf(Math.max.apply(null, out));
    out[j] += 8;
  }
  return out;
}

/* Solve the arrangement rather than nudging it.
 *
 * Nudging fought itself: growing the intro to reach the drop window pushed the
 * length out, and trimming the length dragged the drop back out of the window.
 * Instead, decide up front how many bars belong BEFORE the drop - that is what
 * the genre's window actually specifies - and share the rest out after it.
 */
function arrange(minutes, curve, bpm, dropWindow){
  var barsTotal = Math.max(32, Math.round(minutes * 60 / (240 / bpm) / 8) * 8);
  var tpl = (TEMPLATES[curve] || TEMPLATES.classic).slice();
  var minBars = tpl.length * 8;
  while(minBars > barsTotal && tpl.length > 4){ tpl.splice(1, 1); minBars -= 8; }
  while(minBars < barsTotal - 64 && tpl.length < 22){
    tpl = tpl.slice(0, -1).concat(tpl.slice(1, -1).slice(-4), [tpl[tpl.length - 1]]);
    minBars = tpl.length * 8;
  }

  var mid = dropWindow ? (dropWindow[0] + dropWindow[1]) / 2 : 0.3;

  /* A long template has a lot of post-drop sections, and each one needs at least
     8 bars. For a genre whose drop belongs late, those minimums can eat the
     pre-drop budget and drag the drop forward out of its window. When that
     happens the template is simply too long for this duration - drop a section
     rather than compromise the shape. */
  for(var attempt = 0; attempt < 12; attempt++){
    var di = tpl.indexOf("drop");
    if(di < 0) break;
    var minPost = (tpl.length - di) * 8;
    var minPre = di * 8;
    var pre = Math.max(minPre, Math.round(barsTotal * mid / 8) * 8);
    if(pre + minPost <= barsTotal) break;            // it fits, go
    if(tpl.length <= 5) break;                       // any shorter is not a song
    var cut = -1;                                    // drop a repeated later section
    for(var k = tpl.length - 2; k > di; k--){
      if(tpl[k] !== "outro"){ cut = k; break; }
    }
    if(cut < 0) break;
    tpl.splice(cut, 1);
  }

  var di = tpl.indexOf("drop");
  if(di < 0){
    var flat = share(tpl, barsTotal);
    return tpl.map(function(r, i){ return {role: r, bars: flat[i]}; });
  }
  var pre = Math.max(di * 8, Math.round(barsTotal * mid / 8) * 8);
  var post = Math.max((tpl.length - di) * 8, barsTotal - pre);
  if(pre + post > barsTotal + 8) pre = Math.max(di * 8, barsTotal - post);

  var preBars = share(tpl.slice(0, di), pre);
  var postBars = share(tpl.slice(di), post);
  return tpl.map(function(r, i){
    return {role: r, bars: i < di ? preBars[i] : postBars[i - di]}; });
}

/* Tracks that may carry a fill. Not the kick - moving it moves the floor - and
   not anything pitched, whose notes lane would have to move with it. */
var FILLABLE = ["perc", "snare", "clap", "oh", "hat"];

/* Repeat `pat` for `bars` bars and vary the last one. A fill is a roll into the
   downbeat that is coming, so it lands in the final beat and accents its last hit. */
function fillBar(pat, name, rand, energy){
  var b = pat.padEnd(16, ".").slice(0, 16).split("");
  var from = name === "hat" ? 8 : 12;              // hats roll for half a bar, drums for a beat
  for(var i = from; i < 16; i++){
    var dense = name === "hat" ? true : (i >= 12);
    b[i] = dense || rand() < 0.4 + 0.4 * energy ? (i === 15 ? "X" : "x") : b[i];
  }
  return b.join("");
}
function phrase(pat, bars, name, rand, energy){
  var base = pat.padEnd(16, ".").slice(0, 16), out = "";
  for(var b = 0; b < bars; b++) out += (b === bars - 1) ? fillBar(base, name, rand, energy) : base;
  return out;
}

/* ------------------------------------------------------------- harmony
   Neither engine had ever played a chord progression: the break pad played the
   tonic and held it for the whole section. harmony.py has had six progressions
   and eleven chord shapes since v3, called from nowhere. This walks one.

   One chord per bar, as a phrase-length pattern - the same machinery the drum
   fills use - so the pad moves and comes home. */
function progressionOf(style, rand){
  var H = T.harmony || {}, P = H.progressions || {};
  var name = (T.genre_progression || {})[style] || "i_VII";
  var prog = P[name] || P.static_i || [[0, "min"]];
  return {name: name, steps: prog};
}

/* A note token `semi` semitones above the root, in `oct`. */
function shift(root, scale, semi, oct){
  var i = NAMES.indexOf(root);
  if(i < 0) i = 0;
  var n = (i + semi) % 12, up = Math.floor((i + semi) / 12);
  return NAMES[n] + (oct + up);
}

/* A chord track: one chord a bar, walking the progression across `bars`. Returns
   {pat, notes, ivals} - `ivals` is the chord shape, so the voice stops assuming
   minor-seventh whatever the harmony is doing. */
function chordTrack(root, prog, bars, oct){
  var H = T.harmony || {}, shapes = H.chords || {};
  var pat = "", notes = [];
  /* One track carries one voicing, so a progression that mixes major and minor
     gets the quality-neutral one - root, fifth, octave. Taking the first chord's
     shape and using it for all of them put a minor third over every major chord
     in the andalusian, which is the one interval that had to be right. */
  var qualities = {};
  prog.steps.forEach(function(st){ qualities[st[1]] = 1; });
  var only = Object.keys(qualities);
  var ivals = only.length === 1 ? (shapes[only[0]] || [0, 7, 12]) : [0, 7, 12];
  for(var b = 0; b < bars; b++){
    var step = prog.steps[b % prog.steps.length];
    var semi = step[0];
    pat += "x...............";
    notes.push(shift(root, null, semi, oct));
    for(var k = 1; k < 16; k++) notes.push(".");
  }
  return {pat: pat, notes: notes, ivals: ivals, chords: prog.steps.length};
}

function energyFor(role, pos){
  if(role === "drop") return Math.min(1, 0.84 + 0.16 * pos);
  if(role === "break") return Math.max(0.05, 0.2 - 0.05 * pos);
  var base = {intro:0.15, build:0.55, verse:0.5, outro:0.2}[role] || 0.5;
  return Math.min(1, base + 0.2 * pos);
}

/* Bjorklund: spread k hits as evenly as possible over n steps. e(4,16) is
   four-on-the-floor, e(3,8) is the tresillo, e(7,16) is a classic hat.
   Ported from oontz/gen.py so a genre's rhythms are one definition, not two. */
function euclid(k, n, rotate){
  n = n | 0; if(n <= 0) return "";
  k = Math.max(0, Math.min(k | 0, n));
  var bits, i;
  if(k === 0){ bits = []; for(i = 0; i < n; i++) bits.push(0); }
  else if(k === n){ bits = []; for(i = 0; i < n; i++) bits.push(1); }
  else {
    var counts = [], rem = [k], divisor = n - k, lvl = 0;
    while(true){
      counts.push(Math.floor(divisor / rem[lvl]));
      rem.push(divisor % rem[lvl]);
      divisor = rem[lvl];
      lvl++;
      if(rem[lvl] <= 1) break;
    }
    counts.push(divisor);
    var build = function(l){
      var out = [];
      if(l === -1) out.push(0);
      else if(l === -2) out.push(1);
      else {
        for(var j = 0; j < counts[l]; j++) out = out.concat(build(l - 1));
        if(rem[l] !== 0) out = out.concat(build(l - 2));
      }
      return out;
    };
    bits = build(lvl);
    var first = bits.indexOf(1);
    if(first > 0) bits = bits.slice(first).concat(bits.slice(0, first));
  }
  var r = ((rotate | 0) % n + n) % n;
  if(r) bits = bits.slice(n - r).concat(bits.slice(0, n - r));
  return bits.map(function(b){ return b ? "x" : "."; }).join("");
}

/* A genre's kit, resolved to patterns. Every one of the fifteen genres has its
   own; seven of them used to fall through to the techno kit, which is how jungle
   ended up four-on-the-floor at 168 BPM and garage ended up straight. */
function kitFor(style, rand){
  var kit = (T.kits || {})[style] || (T.kits || {}).techno;
  if(!kit) return {drums: {}, pitched: {}};
  var drums = {}, pitched = {};
  Object.keys(kit.tracks).forEach(function(name){
    var spec = kit.tracks[name], t = {voice: spec.voice || name, gain: 1, sc: 0};
    if(spec.gain != null) t.gain = spec.gain;
    if(spec.sc != null) t.sc = spec.sc;
    if(spec.tune != null) t.tune = spec.tune;
    if(spec.filt){ t.filt = spec.filt[0]; t.fc = spec.filt[1];
                   if(spec.filt[2] != null) t.res = spec.filt[2];
                   /* A noise voice takes its brightness from `tune` - the hat's
                      highpass IS its tune - so a kit that says hp 8500 has to
                      land there or it does nothing at all. */
                   if(spec.filt[0] === "hp" && spec.tune == null && !spec.melody) t.tune = spec.filt[1]; }
    if(spec.melody){ t.scale = spec.melody[1]; t.density = spec.density;
                     pitched[name] = t; return; }
    var pat = spec.pat;
    if(!pat && spec.euclid){
      /* rotate by a seeded step so two seeds do not share a hat */
      var rot = (spec.euclid[2] || 0) + (rand && name !== "kick" ? Math.floor(rand() * 4) : 0);
      pat = euclid(spec.euclid[0], spec.euclid[1], rot);
    }
    if(!pat) return;
    if(spec.accent) pat = pat.replace(/x/g, function(c, i){ return i % 4 === 0 ? "X" : c; });
    t.pat = pat;
    drums[name] = t;
  });
  return {drums: drums, pitched: pitched, bpm: kit.bpm};
}

function compose(style, minutes, curveName, seed){
  style = GENRES[style] ? style : "hardtechno";
  var G = GENRES[style];
  var rand = rng(seed || Math.floor(Math.random() * 1e9));
  /* No curve named? Pick one from the seed. `go` used to be hardtechno/classic
     every single time, so every generated track had the same shape. arrange()
     itself stays deterministic - the Python and JS arrangers are held to
     identical output by qa, and a seeded jitter inside it would break that. */
  var curve = TEMPLATES[curveName] ? curveName
            : Object.keys(TEMPLATES)[Math.floor(rand() * Object.keys(TEMPLATES).length)];
  var root = ["a","c","d","f","g"][Math.floor(rand() * 5)];
  var scale = G.key;
  var bpm = ((T.kits || {})[style] || {}).bpm || G.bpm;
  var m = motif(rand, ["static","arch","rising","zigzag"][Math.floor(rand() * 4)], 8);

  var prog = progressionOf(style, rand);
  var plan = arrange(minutes, curve, bpm, G.drop);
  var seen = {}, order = [], sections = {};

  plan.forEach(function(p, i){
    seen[p.role] = (seen[p.role] || 0) + 1;
    var name = seen[p.role] === 1 ? p.role : p.role + seen[p.role];
    var pos = i / Math.max(1, plan.length - 1);
    var energy = energyFor(p.role, pos);
    var tracks = {}, ord = [];

    var kit = kitFor(style, rand);
    Object.keys(kit.drums).forEach(function(k){
      var d = kit.drums[k], t = {voice: d.voice, pat: d.pat, gain: d.gain, sc: d.sc};
      if(d.tune != null) t.tune = d.tune;
      if(d.filt){ t.filt = d.filt; t.fc = d.fc; if(d.res != null) t.res = d.res; }
      tracks[k] = t; ord.push(k);
    });

    /* the motif, developed for this section's energy */
    var mm = m;
    if(energy < 0.4) mm = thin(m, rand, 0.6);
    else if(energy > 0.85) mm = densify(m, rand, 0.4);

    /* Every pitched track the kit asks for - a bass, and for the genres that want
       one a stab or chord - each on the same motif so the track has an identity. */
    var pitchNames = Object.keys(kit.pitched);
    if(!pitchNames.length) pitchNames = ["bass"];
    /* Whatever the kit's lowest pitched voice is, it is keyed `bass` - the role
       code below and the mixing rules both reach for that name. Aliasing it to a
       second key instead made the same voice render twice. */
    var hasBass = pitchNames.indexOf("bass") >= 0;
    pitchNames.forEach(function(pn, pi){
      var key = (!hasBass && pi === 0) ? "bass" : pn;
      var spec = kit.pitched[pn] || {};
      var mv = pi === 0 ? mm : thin(mm, rand, 0.55);          // the stab is sparser than the bass
      var sc2 = spec.scale && SCALES[spec.scale] ? spec.scale : scale;
      var notes = motifTokens(mv, root, sc2, pi === 0 ? 1 : 2);
      var t = {voice: spec.voice || pn, notes: notes,
               gain: spec.gain == null ? 1 : spec.gain,
               sc: spec.sc == null ? 0.7 : spec.sc,
               fc: spec.fc == null ? 350 : spec.fc,
               pat: notes.map(function(x){ return x === "." ? "." : (x.indexOf("!") > 0 ? "X" : "x"); }).join("")};
      if(spec.res != null) t.res = spec.res;
      tracks[key] = t; ord.push(key);
    });

    var auto = [];
    function silence(){ [].forEach.call(arguments, function(k){
      if(tracks[k]) tracks[k].pat = tracks[k].pat.replace(/[xXoO]/g, "."); }); }

    if(p.role === "intro"){
      silence("clap","snare","oh","perc");
      tracks.bass.pat = tracks.bass.pat.replace(/[xX]/g, ".");
      tracks.kick.gain = 0.5; if(tracks.hat) tracks.hat.gain = 0.35;
      auto.push(["kick.gain", 0.3, 0.95, 0, p.bars, "linear"]);
      auto.push(["hat.gain", 0.15, 0.7, 0, p.bars, "linear"]);
    } else if(p.role === "build"){
      if(tracks.hat) tracks.hat.pat = "xxxxxxxxxxxxxxxx";
      tracks.bass.fc = 300;
      auto.push(["bass.fc", 260, 4200, 0, p.bars, "exp"]);
      /* everything tightens into the drop: the clap gets louder and the kick harder */
      if(tracks.clap) auto.push(["clap.gain", 0.6, 1.0, 0, p.bars, "exp"]);
      auto.push(["kick.gain", 0.9, 1.0, 0, p.bars, "linear"]);
      tracks.riser = {voice: "riser", pat: "x...............", gain: 0.5};
      ord.push("riser");
      auto.push(["riser.gain", 0.2, 0.9, 0, p.bars, "exp"]);
    } else if(p.role === "drop"){
      tracks.bass.fc = 1200; tracks.bass.sc = 0.8;
      /* a drop opens rather than arriving flat, and the hats lift across it */
      auto.push(["bass.fc", 700, 1600, 0, Math.min(8, p.bars), "log"]);
      if(tracks.hat) auto.push(["hat.gain", 0.55, 0.85, 0, p.bars, "linear"]);
      if(energy > 0.85){
        tracks.rumble = {voice: "rumble", pat: "x...............", gain: 0.5, sc: 0};
        ord.push("rumble");
      }
      if(!tracks.oh){ tracks.oh = {voice: "oh", pat: "......x.......x.", gain: 0.6, sc: 0.5};
                      ord.push("oh"); }
    } else if(p.role === "break"){
      silence("kick","clap","snare","perc","oh");
      /* the pad walks the genre's progression instead of sitting on the tonic */
      var pbars = Math.max(1, Math.min(8, p.bars));
      var ch = chordTrack(root, prog, pbars, 2);
      tracks.pad = {voice: "pad", pat: ch.pat, notes: ch.notes, ivals: ch.ivals,
                    gain: 0.5, sc: 0};
      ord.push("pad");
      tracks.bass.gain = 0.4; tracks.bass.fc = 220;
      auto.push(["bass.fc", 180, 900, 0, p.bars, "linear"]);
      /* the pad swells and the room opens as the break runs out */
      auto.push(["pad.gain", 0.25, 0.7, 0, p.bars, "ease"]);
      auto.push(["pad.fc", 400, 2600, 0, p.bars, "linear"]);
    } else if(p.role === "outro"){
      silence("clap","perc");
      tracks.bass.pat = tracks.bass.pat.replace(/[xX]/g, ".");
      auto.push(["kick.gain", 0.95, 0.3, Math.floor(p.bars / 2), p.bars, "exp"]);
    }

    /* density follows energy, so a repeat is never a photocopy */
    if(tracks.hat && p.role !== "break" && p.role !== "intro"){
      var pat = tracks.hat.pat.split("");
      for(var q = 0; q < pat.length; q++){
        if(pat[q] === "." && rand() < (0.25 + 0.6 * energy) - 0.3) pat[q] = "x";
      }
      tracks.hat.pat = pat.join("");
    }

    /* The last bar of the phrase is not the same as the other seven. This is the
       single biggest difference between a loop and a track: the ear counts in
       eights and expects to be told where the boundary is. */
    if(p.bars >= 8 && p.role !== "break"){
      FILLABLE.forEach(function(n){
        var t = tracks[n];
        if(!t || !t.pat || t.notes) return;
        if(!t.pat.replace(/[.\-]/g, "").length) return;   // silenced here: a fill would resurrect it
        t.pat = phrase(t.pat, 8, n, rand, energy);
      });
    }

    sections[name] = {name: name, bars: p.bars, role: p.role, energy: energy,
                      tracks: tracks, order: ord, automation: auto};
    order.push(name);
  });

  return {name: style + "-" + curve, bpm: bpm, swing: G.swing, key: root,
          groove: (T.genre_groove || {})[style] || "straight",
          scale: scale, order: order, sections: sections,
          meta: {style: style, curve: curve, generated: true, progression: prog.name}};
}

/* ---------------------------------------------------------------- theory */

function critique(song){
  if(!song || !song.order || !song.order.length)
    return [["bad", "There is no song to judge yet."]];
  var secs = song.order.map(function(n){ return song.sections[n]; }).filter(Boolean);
  var total = secs.reduce(function(a, s){ return a + s.bars; }, 0);
  var roles = secs.map(function(s){ return s.role; });
  var energies = secs.map(function(s){ return s.energy; });
  var G = GENRES[(song.meta || {}).style] || GENRES.techno;
  var out = [];

  var odd = secs.filter(function(s){ return s.bars % 8; }).map(function(s){ return s.name; });
  if(odd.length) out.push(["bad", "Not multiples of 8 bars: " + odd.join(", ") +
    ". Dancers and DJs both count in eights."]);
  else out.push(["good", "Every section is phrase-aligned."]);

  if(roles[0] !== "intro") out.push(["bad", "It opens on a " + roles[0] +
    ". A DJ has nothing to mix into."]);
  else out.push(["good", secs[0].bars + "-bar intro - mixable."]);

  var di = roles.indexOf("drop");
  if(di < 0) out.push(["bad", "There is no drop at all."]);
  else {
    var at = secs.slice(0, di).reduce(function(a, s){ return a + s.bars; }, 0) / Math.max(1, total);
    if(at < G.drop[0]) out.push(["bad", "The drop lands " + Math.round(at * 100) +
      "% in. Before " + Math.round(G.drop[0] * 100) + "% there is no tension built to release."]);
    else if(at > G.drop[1]) out.push(["warn", "The drop lands " + Math.round(at * 100) +
      "% in. The floor drifts before it arrives."]);
    else out.push(["good", "Drop at " + Math.round(at * 100) + "% - well placed."]);
  }

  if(roles.indexOf("break") < 0)
    out.push(["warn", "No break. Loudness is relative - without a quiet passage the drops stop reading as drops."]);
  else out.push(["good", "There is contrast before the drops."]);

  var spread = Math.max.apply(null, energies) - Math.min.apply(null, energies);
  if(spread < 0.4) out.push(["bad", "Energy only moves " + spread.toFixed(2) +
    ". That is a long loop, not an arrangement."]);
  else out.push(["good", "Energy spans " + spread.toFixed(2) + "."]);

  if(roles[roles.length - 1] !== "outro")
    out.push(["warn", "It ends on a " + roles[roles.length - 1] + ". The next DJ has nowhere to go."]);
  else out.push(["good", "Mixable outro."]);
  return out;
}

function score(crit){
  var wgt = {bad: -12, warn: -4, good: 6};
  return Math.max(0, Math.min(100, 50 + crit.reduce(function(a, c){
    return a + (wgt[c[0]] || 0); }, 0)));
}

g.OONTZ_COMPOSE = {compose: compose, critique: critique, score: score, arrange: arrange,
                   euclid: euclid, kitFor: kitFor, chordTrack: chordTrack, progressionOf: progressionOf,
                   GENRES: GENRES, TEMPLATES: TEMPLATES, degToken: degToken};
})(typeof window !== "undefined" ? window : globalThis);
