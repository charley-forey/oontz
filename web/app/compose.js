/* Arrangement, in the browser. The port of thud/compose.py + thud/theory.py.
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

/* The theory is not copied here. theory.js is generated from thud/theory.py and
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
  var s = seed >>> 0 || 1;
  return function(){ s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
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

function energyFor(role, pos){
  if(role === "drop") return Math.min(1, 0.84 + 0.16 * pos);
  if(role === "break") return Math.max(0.05, 0.2 - 0.05 * pos);
  var base = {intro:0.15, build:0.55, verse:0.5, outro:0.2}[role] || 0.5;
  return Math.min(1, base + 0.2 * pos);
}

var STYLE_TRACKS = {
  hardtechno: {kick:"X...X...X...X..X", hat:"x.x.x.x.x.x.x.x.", oh:"....x.......x...",
               clap:"....X.......X...", perc:"..x..x..x..x..x."},
  techno:     {kick:"x...x...x...x...", hat:"..x...x...x...x.", clap:"....x.......x...",
               perc:"..........x....."},
  acid:       {kick:"x...x...x...x...", hat:"..x...x...x...x.", clap:"....x.......x..."},
  industrial: {kick:"X..xX...X..xX...", hat:"x.xxx.xxx.xxx.xx", snare:"........x.......",
               perc:"x..x..x..x..x..x"},
  minimal:    {kick:"x...x...x...x...", hat:"..x...x...x...x.", perc:"...........x...."},
  dubtechno:  {kick:"x...x...x...x...", hat:"..x...x...x...x."},
  house:      {kick:"x...x...x...x...", hat:"..x...x...x...x.", clap:"....x.......x..."},
  trance:     {kick:"x...x...x...x...", hat:"..x...x...x...x.", oh:"..x...x...x...x."}
};

function compose(style, minutes, curveName, seed){
  style = GENRES[style] ? style : "hardtechno";
  var G = GENRES[style];
  var rand = rng(seed || Math.floor(Math.random() * 1e9));
  var curve = TEMPLATES[curveName] ? curveName : "classic";
  var root = ["a","c","d","f","g"][Math.floor(rand() * 5)];
  var scale = G.key;
  var bpm = G.bpm;
  var m = motif(rand, ["static","arch","rising","zigzag"][Math.floor(rand() * 4)], 8);

  var plan = arrange(minutes, curve, bpm, G.drop);
  var seen = {}, order = [], sections = {};

  plan.forEach(function(p, i){
    seen[p.role] = (seen[p.role] || 0) + 1;
    var name = seen[p.role] === 1 ? p.role : p.role + seen[p.role];
    var pos = i / Math.max(1, plan.length - 1);
    var energy = energyFor(p.role, pos);
    var tracks = {}, ord = [];

    var base = STYLE_TRACKS[style] || STYLE_TRACKS.techno;
    Object.keys(base).forEach(function(k){
      tracks[k] = {voice: k, pat: base[k], gain: 1, sc: 0};
      ord.push(k);
    });

    /* the motif, developed for this section's energy */
    var mm = m;
    if(energy < 0.4) mm = thin(m, rand, 0.6);
    else if(energy > 0.85) mm = densify(m, rand, 0.4);
    var notes = motifTokens(mm, root, scale, 1);
    tracks.bass = {voice: "bass", notes: notes, gain: 1, sc: 0.7, fc: 350,
                   pat: notes.map(function(t){ return t === "." ? "." : (t.indexOf("!") > 0 ? "X" : "x"); }).join("")};
    ord.push("bass");

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
      tracks.pad = {voice: "pad", pat: "x...............",
                    notes: [degToken(root, scale, 0, 2)].concat(Array(15).fill(".")),
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
          meta: {style: style, curve: curve, generated: true}};
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
                   GENRES: GENRES, TEMPLATES: TEMPLATES, degToken: degToken};
})(typeof window !== "undefined" ? window : globalThis);
