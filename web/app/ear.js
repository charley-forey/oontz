/* ear.js - the browser listens to what it made.
 *
 * `grade` could only ever read the ARRANGEMENT: section lengths, where the drop
 * sits, whether the energy moves. Every mixing rule in theory.py - kick owns
 * 40-90Hz, hat above 8k, one element per band, -0.5dBFS of headroom, nothing
 * wide below 120Hz - was an unenforced claim, because nothing measured the sound.
 *
 * It can now, because the engine renders offline: render the loudest section, one
 * pass per track, take the spectrum of each, and run the rules against numbers.
 * "your sub and your kick are both sitting at 55Hz" is a thing it can prove.
 *
 * The maths here is pure and runs in node; only measure() needs a browser.
 */
(function (g) {
"use strict";

var OZ = g.oontz, T = g.OONTZ_THEORY;
if(!OZ) throw new Error("oontz.js must load before ear.js");

/* ------------------------------------------------------------------- fft */
/* Iterative radix-2, in place. ~30 lines beats a dependency for one transform. */
function fft(re, im){
  var n = re.length, i, j, k, len, t;
  for(i = 1, j = 0; i < n; i++){
    var bit = n >> 1;
    for(; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if(i < j){ t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for(len = 2; len <= n; len <<= 1){
    var ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang), half = len >> 1;
    for(i = 0; i < n; i += len){
      var cr = 1, ci = 0;
      for(k = 0; k < half; k++){
        var pr = re[i + k + half] * cr - im[i + k + half] * ci;
        var pi = re[i + k + half] * ci + im[i + k + half] * cr;
        var ur = re[i + k], ui = im[i + k];
        re[i + k] = ur + pr; im[i + k] = ui + pi;
        re[i + k + half] = ur - pr; im[i + k + half] = ui - pi;
        var ncr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = ncr;
      }
    }
  }
}

function pow2below(n){ var p = 1; while(p * 2 <= n) p *= 2; return p; }

/* Average magnitude spectrum over the WHOLE signal: Hann windows of `n`, hopping
   by half, averaged (Welch).

   One window is not enough and the difference is not subtle. A bar at 150 BPM is
   1.6s; one 8192-sample window is 0.19s of it. Measuring a single window meant
   every track whose first hit was not on the downbeat - the offbeat hat, the clap
   on 2 and 4, every perc - measured as pure silence, and `improve` would have
   balanced a mix it had only heard the first sixteenth of. */
function spectrum(x, n){
  n = pow2below(Math.min(x.length, n || 8192));
  if(n < 64) return null;
  var half = n >> 1, mag = new Float64Array(half), win = new Float64Array(n), i, k;
  for(i = 0; i < n; i++) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1));
  var hop = half, frames = 0;
  for(var off = 0; off + n <= x.length || frames === 0; off += hop){
    var re = new Float64Array(n), im = new Float64Array(n);
    for(i = 0; i < n; i++) re[i] = (x[off + i] || 0) * win[i];
    fft(re, im);
    for(k = 0; k < half; k++) mag[k] += Math.sqrt(re[k] * re[k] + im[k] * im[k]);
    frames++;
    if(off + n + hop > x.length) break;
  }
  for(k = 0; k < half; k++) mag[k] /= frames;
  return {mag: mag, n: n, frames: frames};
}

function bandsHz(){ return (T && T.bands_hz) ||
  [["sub",20,60],["bass",60,250],["low-mid",250,800],["mid",800,2500],["presence",2500,8000],["air",8000,20000]]; }

/* Fraction of energy in each band. Sums to nearly 1 - the top band stops at 20k
   and Nyquist is 22.05k, so a sliver always sits outside every band. */
function bandEnergy(x, sr){
  var sp = spectrum(x), B = bandsHz();
  if(!sp) return B.map(function(){ return 0; });
  var binHz = (sr || 44100) / sp.n, tot = 0, i;
  for(i = 0; i < sp.mag.length; i++) tot += sp.mag[i];
  if(tot <= 0) return B.map(function(){ return 0; });
  return B.map(function(b){
    var lo = Math.ceil(b[1] / binHz), hi = Math.min(sp.mag.length, Math.ceil(b[2] / binHz)), s = 0;
    for(var k = Math.max(0, lo); k < hi; k++) s += sp.mag[k];
    return s / tot;
  });
}

/* The same sums, NOT normalised. Two questions need two measures: "where does
   this track sit" is about its own distribution, but "who is masking whom" is
   about how much of the band each track actually contributes. Normalised numbers
   cannot answer the second - a quiet bright hat still reads as 70% air, so
   turning it down never clears the conflict, and improve trims forever. */
function bandAbs(x, sr){
  var sp = spectrum(x), B = bandsHz();
  if(!sp) return B.map(function(){ return 0; });
  var binHz = (sr || 44100) / sp.n;
  return B.map(function(b){
    var lo = Math.max(0, Math.ceil(b[1] / binHz)), hi = Math.min(sp.mag.length, Math.ceil(b[2] / binHz)), sum = 0;
    for(var k = lo; k < hi; k++) sum += sp.mag[k];
    return sum;
  });
}

/* Each track's share of each band, across the tracks that are playing. This is
   what masking actually means, and it moves when you change a level. */
function shares(abs, order){
  var B = bandsHz(), out = {};
  order.forEach(function(n){ out[n] = B.map(function(){ return 0; }); });
  B.forEach(function(_b, i){
    var tot = 0;
    order.forEach(function(n){ tot += (abs[n] || [])[i] || 0; });
    if(tot <= 0) return;
    order.forEach(function(n){ out[n][i] = ((abs[n] || [])[i] || 0) / tot; });
  });
  return out;
}

/* Energy below `hz`, for mid and side. Wide bass cancels on a mono club rig, so
   what matters is how much of the low end is in the side channel at all. */
function lowMidSide(L, R, sr, hz){
  var n = L.length;
  if(n < 64) return {mid: 0, side: 0, ratio: 0};
  var mid = new Float32Array(n), side = new Float32Array(n), i;
  for(i = 0; i < n; i++){ mid[i] = (L[i] + R[i]) / 2; side[i] = (L[i] - R[i]) / 2; }
  function under(x){
    var sp = spectrum(x); if(!sp) return 0;
    var binHz = sr / sp.n, hi = Math.min(sp.mag.length, Math.ceil(hz / binHz)), s = 0;
    for(var k = 1; k < hi; k++) s += sp.mag[k];
    return s;
  }
  var m = under(mid), sd = under(side);
  /* If mid is empty and side is not, the channels are out of phase and the low end
     vanishes entirely in mono - the worst case, not the best. Guarding with 0 here
     would have reported it as perfectly centred. */
  var ratio = m > 1e-9 ? sd / m : (sd > 1e-9 ? 999 : 0);
  return {mid: m, side: sd, ratio: ratio};
}

function db(x){ return 20 * Math.log10(Math.max(1e-9, x)); }

function peakOf(buf){
  var p = 0;
  for(var c = 0; c < buf.numberOfChannels; c++){
    var d = buf.getChannelData(c);
    for(var i = 0; i < d.length; i++){ var a = d[i] < 0 ? -d[i] : d[i]; if(a > p) p = a; }
  }
  return p;
}
function rmsOf(buf){
  var d = buf.getChannelData(0), s = 0;
  for(var i = 0; i < d.length; i++) s += d[i] * d[i];
  return Math.sqrt(s / Math.max(1, d.length));
}

/* --------------------------------------------------------------- measure */
/* The loudest section is the one worth judging: it is where everything plays at
   once, which is where a mix falls apart. */
function loudestSection(song){
  var best = null;
  (song.order || []).forEach(function(name, i){
    var sec = song.sections[name]; if(!sec) return;
    var e = sec.energy == null ? 0.5 : sec.energy;
    if(!best || e > best.energy) best = {name: name, energy: e, index: i};
  });
  return best;
}
function barOfSection(song, name){
  var bar = 0;
  for(var i = 0; i < song.order.length; i++){
    var s = song.sections[song.order[i]];
    if(song.order[i] === name) return bar + Math.min(1, (s.bars | 0) - 1);   // one bar in, past any ramp start
    bar += s ? (s.bars | 0) : 0;
  }
  return 0;
}

/* Render one bar of one section, optionally only one track sounding. The other
   tracks stay in the state dict so the kick still ducks what it should. */
function measure(song, opts){
  opts = opts || {};
  var sec = opts.section || (loudestSection(song) || {}).name;
  var bar = barOfSection(song, sec);
  var st = OZ.stateAt(song, bar);
  if(!st) return Promise.reject(new Error("nothing to measure"));
  /* Two renders, not one per track: the whole mix through the master chain (which
     is what the headroom and mono rules judge), and every track at once on its own
     channel (which is what the masking rules need). */
  return Promise.all([
    OZ.renderTracks(song, {bar: bar}),
    OZ.renderSlice(song, {bar: bar, bars: 1, channels: 2})
  ]).then(function(both){
    var per = both[0], master = both[1], sr = master.sampleRate;
    var names = per.names, tracks = {}, abs = {};
    names.forEach(function(n, i){
      var ch = per.buf.getChannelData(i);
      tracks[n] = bandEnergy(ch, sr);
      abs[n] = bandAbs(ch, sr);
    });
    var L = master.getChannelData(0);
    var R = master.numberOfChannels > 1 ? master.getChannelData(1) : L;
    return {section: sec, bar: bar, tracks: tracks, abs: abs, share: shares(abs, names),
            order: names, params: st.tracks,
            master: {peak: peakOf(master), peakDb: db(peakOf(master)), rms: rmsOf(master),
                     bands: bandEnergy(L, sr), low: lowMidSide(L, R, sr, 120)}};
  });
}

/* theory.FREQ_ROLES on rumble: "Sits under the kick and fills the gap between
   hits. Sidechain it or it eats the kick." So a kick and a rumble in the same low
   band is the genre working, NOT a fault - as long as the rumble is ducked. Without
   this the grader fights hard techno for being hard techno. */
function duckedUnderKick(m, loud){
  if(loud.length !== 2 || loud.indexOf("kick") < 0) return false;
  var other = loud.filter(function(n){ return n !== "kick"; })[0];
  if(other !== "rumble" && other !== "sub") return false;
  var p = (m.params || {})[other];
  return !!(p && p.sc >= 0.5);
}

/* -------------------------------------------------------------- critique */
/* Same shape as the arrangement critique: [level, text]. Every line carries the
   number it is judging, because "muddy" is an opinion and 0.42 is not. */
/* Older measurements carry no shares; fall back so a saved one still grades. */
function sh(m){ return m.share || m.tracks; }

/* Masking is two elements JOINTLY OWNING a band, not merely both being present.
   Six bands are broad: three tracks in the mids is normal and splits 33% each.
   The pair has to both be big AND account for most of the band before it is a
   fault - clap at 38% and bass at 32% of the mids is a mix; a hat at 32% and an
   open hat at 52% is the same sound twice. */
var PAIR_EACH = 0.30, PAIR_TOGETHER = 0.75;

function pairIn(m, i){
  var S = sh(m);
  var top = m.order.filter(function(n){ return (S[n] || [])[i] >= PAIR_EACH; })
    .sort(function(a, b){ return S[b][i] - S[a][i]; });
  if(top.length < 2) return null;
  var pair = top.slice(0, 2);
  if(S[pair[0]][i] + S[pair[1]][i] < PAIR_TOGETHER) return null;
  return pair;
}

function critiqueMix(m){
  var out = [], B = bandsHz(), names = B.map(function(b){ return b[0]; });
  var roles = (T && T.freq_roles) || {};

  /* headroom */
  if(m.master.peakDb > -0.5)
    out.push(["bad", "Master peaks at " + m.master.peakDb.toFixed(2) +
      " dBFS. Clipping a limiter is distortion you cannot undo later - leave 0.5dB."]);
  else
    out.push(["good", "Peaks at " + m.master.peakDb.toFixed(2) + " dBFS - headroom is there."]);

  /* wide bass */
  var r = m.master.low.ratio;
  if(r > 0.08) out.push(["bad", "Below 120Hz, " + Math.round(r * 100) +
    "% of the energy is in the side channel. Wide bass cancels on a mono club rig."]);
  else out.push(["good", "Low end is centred (" + Math.round(r * 100) + "% side under 120Hz)."]);

  /* one element per band */
  var conflicts = [];
  names.forEach(function(band, i){
    var loud = pairIn(m, i);
    if(loud){
      if(duckedUnderKick(m, loud)){
        out.push(["good", loud.join(" and ") + " share " + band +
          ", and the " + loud.filter(function(n){ return n !== "kick"; })[0] +
          " is ducked under the kick - that smear is the genre, not a fault."]);
        return;
      }
      conflicts.push([band, loud]);
    }
  });
  conflicts.forEach(function(c){
    var i = names.indexOf(c[0]);
    out.push(["bad", c[1].join(" and ") + " are both living in " + c[0] +
      " (" + c[1].map(function(n){ return n + " " + Math.round(sh(m)[n][i] * 100) + "% of the band"; }).join(", ") +
      "). Masking is inaudible as a problem and obvious as a result."]);
  });
  if(!conflicts.length) out.push(["good", "No two elements are fighting for the same band."]);

  /* nothing but the kick belongs in the sub */
  m.order.forEach(function(n){
    if(n === "kick" || n === "rumble" || n === "sub") return;
    var sub = (m.tracks[n] || [])[0] || 0;
    if(sub > 0.25) out.push(["warn", n + " puts " + Math.round(sub * 100) +
      "% of itself under 60Hz. Highpass anything that is not the kick - three sub sources sum to mud."]);
  });

  /* does each element sit where theory says it should? */
  m.order.forEach(function(n){
    var role = roles[n]; if(!role) return;
    var b = m.tracks[n] || [], want = [], i;
    for(i = 0; i < B.length; i++) if(B[i][2] > role.hz[0] && B[i][1] < role.hz[1]) want.push(i);
    if(!want.length) return;
    var got = want.reduce(function(a, i2){ return a + (b[i2] || 0); }, 0);
    /* 0.4, not 0.5: a hard kick puts a real share of itself in the click, and a
       clap has a tail. Below 40% it is genuinely in the wrong place. */
    if(got < 0.4) out.push(["warn", n + " has only " + Math.round(got * 100) + "% of its energy in " +
      role.band + " (" + role.hz[0] + "-" + role.hz[1] + "Hz). " + role.note]);
    else out.push(["good", n + " sits where it should: " + Math.round(got * 100) + "% in " + role.band + "."]);
  });

  return out;
}

/* A compact per-track band table - the FREQ view, in the browser. */
function table(m){
  var B = bandsHz(), rows = [], BLOCK = " ▁▂▃▄▅▆▇█";
  rows.push("        " + B.map(function(b){ return pad(b[0], 9); }).join(""));
  m.order.forEach(function(n){
    rows.push(pad(n, 8) + (m.tracks[n] || []).map(function(v){
      var k = Math.max(0, Math.min(8, Math.round(v * 8)));
      return pad(BLOCK[k] + " " + Math.round(v * 100) + "%", 9); }).join(""));
  });
  return rows;
}
function pad(s, n){ s = String(s); while(s.length < n) s += " "; return s.slice(0, n); }

/* ------------------------------------------------------------- fix one thing */
/* The worst violation, and the smallest real move that answers it. Pure: it takes
   a song and a measurement and edits the measured section, so it is testable
   without a browser and every change can be printed as a sentence.

   The levers are the ones the engine actually honours - gain, pan, sidechain -
   because a fix you cannot hear is not a fix. */
function ownerOf(band){
  /* theory.FREQ_ROLES on the kick: "Owns 40-90Hz. Nothing else lives there." It is
     the one element that never ducks, so down there it is the owner by fiat -
     geometry alone hands the band to whichever role happens to be narrowest. */
  if(band === "sub" || band === "bass") return "kick";
  var roles = (T && T.freq_roles) || {}, B = bandsHz(), i = B.map(function(b){ return b[0]; }).indexOf(band);
  if(i < 0) return null;
  var lo = B[i][1], hi = B[i][2], best = null;
  Object.keys(roles).forEach(function(n){
    var r = roles[n];
    var overlap = Math.min(hi, r.hz[1]) - Math.max(lo, r.hz[0]);
    if(overlap <= 0) return;
    var frac = overlap / (r.hz[1] - r.hz[0]);       // whose declared home is most inside this band
    if(!best || frac > best.frac) best = {name: n, frac: frac};
  });
  return best && best.name;
}

function fixWorst(song, m){
  var sec = song.sections[m.section]; if(!sec || !sec.tracks) return null;
  var B = bandsHz(), names = B.map(function(b){ return b[0]; }), SH = sh(m);
  function tr(n){ return sec.tracks[n]; }
  function setg(n, mult, why){
    var t = tr(n); if(!t) return null;
    var was = t.gain == null ? 1 : t.gain;
    t.gain = Math.max(0.05, Math.min(1.2, was * mult));
    return n + " gain " + was.toFixed(2) + " → " + t.gain.toFixed(2) + " · " + why;
  }

  /* 1. headroom: nothing else can be judged past a clipped master */
  if(m.master.peakDb > -0.5){
    /* Aim at -2, not at the -0.5 limit. The master compressor is not linear, so
       pulling the inputs by exactly the overshoot lands you back on the threshold:
       measured 2.89 dBFS, pulled 3.89 dB, came back at -0.49 and still failed. */
    var mult = Math.pow(10, (-2.0 - m.master.peakDb) / 20);
    var touched = 0;
    m.order.forEach(function(n){ var t = tr(n); if(!t) return;
      t.gain = Math.max(0.05, (t.gain == null ? 1 : t.gain) * mult); touched++; });
    return "pulled all " + touched + " tracks by " + (20 * Math.log10(mult)).toFixed(1) +
      " dB · master was " + m.master.peakDb.toFixed(2) + " dBFS, and a limiter cannot undo clipping";
  }

  /* 2. wide low end: centre whatever is loud below 250Hz */
  if(m.master.low.ratio > 0.08){
    var moved = [];
    m.order.forEach(function(n){
      var b = m.tracks[n] || [];
      if(((b[0] || 0) + (b[1] || 0)) > 0.4 && tr(n) && tr(n).pan){ tr(n).pan = 0; moved.push(n); }
    });
    if(moved.length) return "centred " + moved.join(", ") +
      " · " + Math.round(m.master.low.ratio * 100) + "% of the sub was in the side channel, which cancels in mono";
  }

  /* 3. two elements in one band: the one whose home it is keeps it */
  for(var i = 0; i < names.length; i++){
    var loud = pairIn(m, i);
    if(!loud) continue;
    if(duckedUnderKick(m, loud)) continue;        // the genre, already handled correctly
    var owner = ownerOf(names[i]);
    /* The kick is never the one that moves. Everything else in a mix is arranged
       around it, so if the kick is the "guest" here, the other one gives way. */
    var guest = loud.filter(function(n){ return n !== owner && n !== "kick"; })[0];
    if(!guest) continue;
    /* a bass fighting the kick is a sidechain problem before it is a level problem */
    if(names[i] === "bass" || names[i] === "sub"){
      var t = tr(guest);
      if(t && (t.sc == null || t.sc < 0.7)){
        var was = t.sc == null ? 0 : t.sc;
        t.sc = 0.8;
        return guest + " sidechain " + was.toFixed(2) + " → 0.80 · it and " +
          (owner || loud.join(" and ")) + " both own " + names[i] +
          ", and ducking is what lets both be loud";
      }
    }
    /* Trim by what it would take to drop the share under the threshold, not by a
       flat 3dB: a share only moves when the level does, and a fixed step can trim
       forever without ever clearing the fault. Capped so it converges instead of
       nuking the track in one go. */
    var have = SH[guest][i], want = PAIR_EACH - 0.02;
    var need = (want * (1 - have)) / Math.max(1e-6, have * (1 - want));
    var r = setg(guest, Math.max(0.5, Math.min(0.95, need)),
      "it holds " + Math.round(have * 100) + "% of " + names[i] + ", which " +
      (owner || "another track") + " owns");
    if(r) return r;
  }

  /* 4. sub leakage: only the kick belongs under 60Hz */
  for(var k = 0; k < m.order.length; k++){
    var n2 = m.order[k];
    if(n2 === "kick" || n2 === "rumble" || n2 === "sub") continue;
    if(((m.tracks[n2] || [])[0] || 0) > 0.25){
      var t2 = tr(n2);
      if(t2 && (t2.sc == null || t2.sc < 0.7)){
        t2.sc = 0.8;
        return n2 + " sidechain → 0.80 · " + Math.round(m.tracks[n2][0] * 100) +
          "% of it sits under 60Hz, on top of the kick";
      }
      var r2 = setg(n2, Math.pow(10, -3 / 20), Math.round(m.tracks[n2][0] * 100) + "% of it is under 60Hz");
      if(r2) return r2;
    }
  }
  return null;
}

g.OONTZ_EAR = {fft: fft, fixWorst: fixWorst, ownerOf: ownerOf, duckedUnderKick: duckedUnderKick,
               bandAbs: bandAbs, shares: shares, spectrum: spectrum, bandEnergy: bandEnergy, lowMidSide: lowMidSide,
               measure: measure, critiqueMix: critiqueMix, table: table, db: db,
               loudestSection: loudestSection, barOfSection: barOfSection};
})(typeof window !== "undefined" ? window : globalThis);
