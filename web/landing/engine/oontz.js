/* oontz browser engine — the WebAudio port of the oontz voice bank and sequencer.
 *
 * This file is the foundation for oontz.sh, not throwaway landing-page code. The
 * Python engine's design ports directly: voices are pure functions of their
 * parameters, a song is sections in an order, and state_at(bar) answers what the
 * music is at any point. Only the DSP is rewritten, because numpy does not run
 * in a browser and WebAudio gives us filters and convolution natively.
 *
 * No dependencies. Nothing is sampled.
 */
(function (global) {
"use strict";

var SR = 44100;
var A4 = 440;
var NAMES = ["c","c#","d","d#","e","f","f#","g","g#","a","a#","b"];
var FLATS = {db:"c#", eb:"d#", gb:"f#", ab:"g#", bb:"a#"};

/* 'a1' -> 55.0, 'f#2' -> 92.5. Scientific pitch, same as the Python. */
function noteHz(name){
  var n = String(name).trim().toLowerCase().replace(/[~!]+$/,"");
  var m = n.match(/^([a-g])([#b]?)(-?\d+)$/);
  if(!m) return 0;
  var base = m[1] + (m[2]||"");
  base = FLATS[base] || base;
  var i = NAMES.indexOf(base);
  if(i < 0) return 0;
  var midi = (parseInt(m[3],10) + 1) * 12 + i;
  return A4 * Math.pow(2, (midi - 69) / 12);
}

/* ---------------------------------------------------------------- engine */

function Engine(){
  this.ctx = null; this.master = null; this.analyser = null;
  this.limiter = null; this.bus = {};
  this.onbar = null; this.onstep = null;
  this.playing = false; this.step = 0; this.bar = 0;
  this.bpm = 138; this.swing = 0;
  this.tracks = {};            // name -> {voice, pat, notes, gain, pan, sc, fc, res}
  this.order = [];
  this.song = null;            // {bpm, key, scale, order, sections}
  this.songbar = 0;
  this.focus = null;           // the track the pads edit
  this.roll = null;            // {i, step, len} while a loop roll is held
  this.fc = 20000;             // the master filter, swept by [ and ]
  this.groove = null;          // {accent[16], push_ms[16]} - see theory.GROOVES
  this.stepNow = 0;            // the step that is sounding right now (for the grid)
  this._timer = null; this._next = 0;
}

/* The master chain, built once and used by the live engine and both offline
   renders - if they differed, the ear would be measuring something nobody hears.
 *
 * It enforces the rules theory.py already states rather than trusting them:
 *   - everything below 120Hz is summed to mono, because wide bass cancels on the
 *     one system it must not, which is a mono club rig;
 *   - a real limiter after the glue compressor, because the generator was
 *     shipping tracks that peaked at +2.8 dBFS.
 * Returns the node everything plays into. */
function buildMaster(c, dest){
  var inp = c.createGain(); inp.gain.value = 0.85;
  var glue = c.createDynamicsCompressor();
  glue.threshold.value = -8; glue.ratio.value = 14;
  glue.attack.value = 0.002; glue.release.value = 0.10;

  var lp = c.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 120; lp.Q.value = 0.7;
  var hp = c.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 120; hp.Q.value = 0.7;
  var mono = c.createGain();                       // explicit 1 channel = a downmix
  mono.channelCount = 1; mono.channelCountMode = "explicit"; mono.channelInterpretation = "speakers";
  var sum = c.createGain();

  var lim = c.createDynamicsCompressor();
  lim.threshold.value = -2; lim.ratio.value = 20; lim.knee.value = 0;
  lim.attack.value = 0.001; lim.release.value = 0.05;
  /* A DynamicsCompressor has no lookahead, so a fast transient still slips past
     the threshold - measured 0.00 dBFS with the limiter in. The trim is what
     actually guarantees the 0.5dB theory asks for. */
  var trim = c.createGain(); trim.gain.value = 0.85;

  inp.connect(glue);
  glue.connect(lp); glue.connect(hp);
  lp.connect(mono); mono.connect(sum); hp.connect(sum);
  sum.connect(lim); lim.connect(trim); trim.connect(dest);
  return inp;
}

/* Only what owns the low end is allowed to keep it: theory says highpass anything
   that is not the kick above ~60Hz, because three sub sources sum to mud. */
function keepsLows(name){
  var T = global.OONTZ_THEORY, r = T && T.freq_roles && T.freq_roles[name];
  return r ? r.hz[0] < 60 : false;
}

Engine.prototype.start = function(){
  if(this.ctx) { if(this.ctx.state === "suspended") this.ctx.resume(); return this.ctx; }
  var C = global.AudioContext || global.webkitAudioContext;
  var c = this.ctx = new C();
  this.analyser = c.createAnalyser();
  this.analyser.fftSize = 2048; this.analyser.smoothingTimeConstant = 0.75;
  /* master -> filter -> delay line -> out -> comp -> analyser. The filter is the
     [ ] sweep. The delay line sits at 0 and is only ever moved by rateFx: a
     DelayNode is a ring buffer with a read head, which is what a spinback needs. */
  this.filter = c.createBiquadFilter(); this.filter.type = "lowpass";
  this.filter.frequency.value = this.fc; this.filter.Q.value = 0.7;
  this.fx = c.createDelay(4); this.fx.delayTime.value = 0;
  this.out = c.createGain();
  var head = buildMaster(c, this.analyser);        // glue, mono lows, limiter
  this.master = c.createGain(); this.master.gain.value = 1;
  this.master.connect(this.filter); this.filter.connect(this.fx); this.fx.connect(this.out);
  this.out.connect(head);
  this.analyser.connect(c.destination);
  return c;
};

/* Read the delay line at speed r(t): a rate is a delay d(t) = t - integral(r), so a
   negative rate reads backwards. Same idea as dj.py moving a pointer, on a node
   the browser already has. After `dur` the head snaps back to live. */
Engine.prototype.rateFx = function(rate, dur){
  var c = this.ctx; if(!c || !this.fx) return;
  /* Value curves may not overlap - scheduling a second one inside a live one
     throws, and the throw escapes the keydown handler, so holding the key broke
     preventDefault and the redraw too. One guard, since every caller repeats. */
  if(this._fxUntil > c.currentTime) return;
  this._fxUntil = c.currentTime + dur + 0.05;
  var n = Math.ceil(dur * 1000), d = new Float32Array(n + 1), acc = 0, dt = dur / n;
  for(var k = 0; k <= n; k++){ d[k] = Math.max(0, Math.min(3.9, k * dt - acc)); acc += rate(k * dt) * dt; }
  var t0 = c.currentTime + 0.01, p = this.fx.delayTime, g = this.out.gain;
  p.cancelScheduledValues(t0); p.setValueCurveAtTime(d, t0, dur);
  p.setValueAtTime(0, t0 + dur + 0.002);
  g.setValueAtTime(1, t0 + dur - 0.006); g.linearRampToValueAtTime(0.0001, t0 + dur);
  g.setValueAtTime(1, t0 + dur + 0.012);   // a 6ms dip hides the click when the head snaps back
};

Engine.prototype.spectrum = function(){
  if(!this.analyser) return null;
  var a = new Uint8Array(this.analyser.frequencyBinCount);
  this.analyser.getByteFrequencyData(a); return a;
};

Engine.prototype.wave = function(){
  if(!this.analyser) return null;
  var a = new Uint8Array(this.analyser.fftSize);
  this.analyser.getByteTimeDomainData(a); return a;
};

/* -- primitives ---------------------------------------------------------- */

function envTo(g, t, a, d, peak){
  g.gain.setValueAtTime(0.0001, t);
  g.gain.linearRampToValueAtTime(peak, t + a);
  g.gain.exponentialRampToValueAtTime(0.0001, t + a + d);
}

var _curves = {};
function satCurve(k){
  if(_curves[k]) return _curves[k];
  var n = 1024, c = new Float32Array(n), th = Math.tanh(k);
  for(var i = 0; i < n; i++){ var x = i * 2 / n - 1; c[i] = Math.tanh(k * x) / th; }
  return (_curves[k] = c);
}

var _noiseBuf = null;
function noiseBuffer(ctx){
  if(_noiseBuf && _noiseBuf.sampleRate === ctx.sampleRate) return _noiseBuf;
  var n = Math.floor(ctx.sampleRate * 2);
  var b = ctx.createBuffer(1, n, ctx.sampleRate), d = b.getChannelData(0);
  /* seeded, so a render is repeatable like the Python one */
  var s = 1312;
  for(var i = 0; i < n; i++){ s = (s * 1103515245 + 12345) & 0x7fffffff; d[i] = (s / 0x3fffffff) - 1; }
  return (_noiseBuf = b);
}
function noiseSrc(ctx, dur){
  var s = ctx.createBufferSource();
  s.buffer = noiseBuffer(ctx);
  s.loop = true;
  s.playbackRate.value = 1;
  return s;
}

/* -- voices -------------------------------------------------------------- */
/* Each returns nothing; it schedules itself. Parameters mirror the Python. */

var VOICES = {};

VOICES.kick = function(e, t, o){
  var c = e.ctx, osc = c.createOscillator(), g = c.createGain(), s = c.createWaveShaper();
  var tune = o.tune || 50, acc = o.accent;
  osc.frequency.setValueAtTime(tune * 3.0, t);
  osc.frequency.exponentialRampToValueAtTime(tune, t + 0.045);
  envTo(g, t, 0.002, acc ? 0.46 : 0.36, acc ? 1.0 : 0.86);
  s.curve = satCurve(acc ? 3.2 : 2.2);
  osc.connect(s); s.connect(g); g.connect(o.dest);
  osc.start(t); osc.stop(t + 0.7);
  var cl = noiseSrc(c), cg = c.createGain(), cf = c.createBiquadFilter();
  cf.type = "highpass"; cf.frequency.value = 1200;
  envTo(cg, t, 0.0005, 0.006, 0.22);
  cl.connect(cf); cf.connect(cg); cg.connect(o.dest);
  cl.start(t); cl.stop(t + 0.05);
};

VOICES.kick_hard = function(e, t, o){
  var oo = Object.assign({}, o, {tune: (o.tune || 48), accent: true});
  VOICES.kick(e, t, oo);
  var c = e.ctx, s = noiseSrc(c), f = c.createBiquadFilter(), g = c.createGain();
  f.type = "bandpass"; f.frequency.value = 220; f.Q.value = 1.2;
  envTo(g, t, 0.001, 0.10, 0.30);
  s.connect(f); f.connect(g); g.connect(o.dest); s.start(t); s.stop(t + 0.2);
};

VOICES.rumble = function(e, t, o){
  var c = e.ctx, osc = c.createOscillator(), g = c.createGain(), lp = c.createBiquadFilter();
  osc.frequency.setValueAtTime(70, t);
  osc.frequency.exponentialRampToValueAtTime(38, t + 0.5);
  lp.type = "lowpass"; lp.frequency.value = 170; lp.Q.value = 0.7;
  envTo(g, t, 0.01, 1.0, 0.42);
  osc.connect(lp); lp.connect(g); g.connect(o.dest);
  osc.start(t); osc.stop(t + 1.3);
};

VOICES.hat = function(e, t, o){
  var c = e.ctx, s = noiseSrc(c), f = c.createBiquadFilter(), g = c.createGain();
  var dur = o.open ? 0.30 : 0.045;
  f.type = "highpass"; f.frequency.value = o.tune || 8200; f.Q.value = 0.8;
  envTo(g, t, 0.001, dur, o.accent ? 0.42 : 0.30);
  s.connect(f); f.connect(g); g.connect(o.dest);
  s.start(t); s.stop(t + dur + 0.1);
};
VOICES.oh = function(e, t, o){ VOICES.hat(e, t, Object.assign({}, o, {open: true})); };

VOICES.clap = function(e, t, o){
  var c = e.ctx, k;
  for(k = 0; k < 3; k++){
    var s = noiseSrc(c), f = c.createBiquadFilter(), g = c.createGain();
    f.type = "bandpass"; f.frequency.value = 1500; f.Q.value = 1.1;
    envTo(g, t + k * 0.011, 0.001, 0.028, 0.46);
    s.connect(f); f.connect(g); g.connect(o.dest);
    s.start(t + k * 0.011); s.stop(t + k * 0.011 + 0.07);
  }
  var s2 = noiseSrc(c), f2 = c.createBiquadFilter(), g2 = c.createGain();
  f2.type = "bandpass"; f2.frequency.value = 1400; f2.Q.value = 0.8;
  envTo(g2, t, 0.002, 0.13, 0.28);
  s2.connect(f2); f2.connect(g2); g2.connect(o.dest);
  s2.start(t); s2.stop(t + 0.3);
};

VOICES.snare = function(e, t, o){
  var c = e.ctx, osc = c.createOscillator(), g = c.createGain();
  osc.frequency.setValueAtTime(180, t);
  envTo(g, t, 0.001, 0.06, 0.22);
  osc.connect(g); g.connect(o.dest); osc.start(t); osc.stop(t + 0.2);
  var s = noiseSrc(c), f = c.createBiquadFilter(), ng = c.createGain();
  f.type = "highpass"; f.frequency.value = 2000;
  envTo(ng, t, 0.001, 0.09, 0.26);
  s.connect(f); f.connect(ng); ng.connect(o.dest); s.start(t); s.stop(t + 0.25);
};

VOICES.perc = function(e, t, o){
  var c = e.ctx, s = noiseSrc(c), f = c.createBiquadFilter(), g = c.createGain();
  f.type = "bandpass"; f.frequency.value = o.tune || 320; f.Q.value = 6;
  envTo(g, t, 0.001, 0.05, 0.34);
  s.connect(f); f.connect(g); g.connect(o.dest); s.start(t); s.stop(t + 0.15);
};

VOICES.bass = function(e, t, o){
  var c = e.ctx, osc = c.createOscillator(), f = c.createBiquadFilter(), g = c.createGain();
  var hz = o.hz || 55, dur = o.dur || 0.2, fc = o.fc || 350;
  osc.type = "sawtooth";
  if(o.slide){ osc.frequency.setValueAtTime(o.slide, t);
               osc.frequency.exponentialRampToValueAtTime(hz, t + 0.06); }
  else osc.frequency.setValueAtTime(hz, t);
  f.type = "lowpass"; f.Q.value = 4 + (o.res || 0.8) * 14;
  var top = Math.min(16000, fc * (o.accent ? 4.6 : 2.9));
  f.frequency.setValueAtTime(top, t);
  f.frequency.exponentialRampToValueAtTime(Math.max(60, fc), t + dur * 0.8);
  envTo(g, t, 0.004, dur * 0.85, o.accent ? 0.34 : 0.26);
  var s = c.createWaveShaper(); s.curve = satCurve(1.6);
  osc.connect(f); f.connect(s); s.connect(g); g.connect(o.dest);
  osc.start(t); osc.stop(t + dur + 0.06);
};
VOICES.sub = function(e, t, o){
  var c = e.ctx, osc = c.createOscillator(), g = c.createGain();
  osc.frequency.setValueAtTime(o.hz || 55, t);
  envTo(g, t, 0.006, (o.dur || 0.25) * 0.9, 0.34);
  osc.connect(g); g.connect(o.dest); osc.start(t); osc.stop(t + (o.dur || 0.25) + 0.05);
};

VOICES.stab = function(e, t, o){
  var c = e.ctx, hz = o.hz || 220, dur = o.dur || 0.3;
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.frequency.value = o.fc || 2200; f.Q.value = 1;
  envTo(g, t, 0.004, dur * 0.5, 0.16);
  f.connect(g); g.connect(o.dest);
  [0, 3, 7].forEach(function(semi){
    [-0.006, 0, 0.006].forEach(function(det){
      var osc = c.createOscillator(); osc.type = "sawtooth";
      osc.frequency.value = hz * Math.pow(2, semi / 12) * (1 + det);
      osc.connect(f); osc.start(t); osc.stop(t + dur + 0.05);
    });
  });
};
VOICES.pad = function(e, t, o){
  var c = e.ctx, hz = o.hz || 110, dur = o.dur || 1.2;
  var ivals = o.ivals || [0, 7, 12];             // root+fifth+octave: works over major or minor
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.frequency.value = o.fc || 800;
  g.gain.setValueAtTime(0.0001, t);
  g.gain.linearRampToValueAtTime(0.11, t + dur * 0.4);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  f.connect(g); g.connect(o.dest);
  ivals.forEach(function(semi){
    [-0.004, 0.004].forEach(function(det){
      var osc = c.createOscillator(); osc.type = "sawtooth";
      osc.frequency.value = hz * Math.pow(2, semi / 12) * (1 + det);
      osc.connect(f); osc.start(t); osc.stop(t + dur + 0.1);
    });
  });
};
VOICES.atmos = function(e, t, o){
  var c = e.ctx, s = noiseSrc(c), f = c.createBiquadFilter(), g = c.createGain();
  var dur = o.dur || 1.5;
  f.type = "bandpass"; f.Q.value = 2.5;
  f.frequency.setValueAtTime(400, t);
  f.frequency.linearRampToValueAtTime(1800, t + dur);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.linearRampToValueAtTime(0.10, t + dur * 0.5);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  s.connect(f); f.connect(g); g.connect(o.dest); s.start(t); s.stop(t + dur + 0.1);
};
VOICES.riser = function(e, t, o){
  var c = e.ctx, s = noiseSrc(c), f = c.createBiquadFilter(), g = c.createGain();
  var dur = o.dur || 2.0;
  f.type = "bandpass"; f.Q.value = 3;
  f.frequency.setValueAtTime(300, t);
  f.frequency.exponentialRampToValueAtTime(9000, t + dur);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.linearRampToValueAtTime(0.22, t + dur);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.05);
  s.connect(f); f.connect(g); g.connect(o.dest); s.start(t); s.stop(t + dur + 0.1);
};
/* aliases so a .song made in the desktop tool finds something sensible */
VOICES.hoover = function(e, t, o){              /* the rave chord: detuned saws swooping up into place */
  var c = e.ctx, hz = o.hz || 220, dur = o.dur || 0.4;
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.Q.value = 4;
  f.frequency.setValueAtTime(o.fc || 900, t);
  f.frequency.exponentialRampToValueAtTime(Math.min(16000, (o.fc || 900) * 4), t + dur * 0.5);
  envTo(g, t, 0.01, dur * 0.8, 0.14);
  f.connect(g); g.connect(o.dest);
  [-12, 0, 0, 0, 7].forEach(function(semi, i){
    var osc = c.createOscillator(); osc.type = "sawtooth";
    var target = hz * Math.pow(2, semi / 12) * (1 + (i - 2) * 0.008);
    osc.frequency.setValueAtTime(target * 0.66, t);          /* the swoop IS the hoover */
    osc.frequency.exponentialRampToValueAtTime(target, t + 0.09);
    osc.connect(f); osc.start(t); osc.stop(t + dur + 0.05);
  });
};

VOICES.lead = function(e, t, o){                /* square + saw an octave apart, bright and quick */
  var c = e.ctx, hz = o.hz || 440, dur = o.dur || 0.22;
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.frequency.value = o.fc || 4200; f.Q.value = 1.2;
  envTo(g, t, 0.003, dur * 0.6, 0.15);
  f.connect(g); g.connect(o.dest);
  [["square", 1], ["sawtooth", 2]].forEach(function(v){
    var osc = c.createOscillator(); osc.type = v[0]; osc.frequency.value = hz * v[1];
    osc.connect(f); osc.start(t); osc.stop(t + dur + 0.05);
  });
};

VOICES.pluck = function(e, t, o){               /* a saw with its filter snapped shut: the snap is the note */
  var c = e.ctx, hz = o.hz || 330, dur = o.dur || 0.18;
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.Q.value = 6;
  f.frequency.setValueAtTime(o.accent ? 6000 : 3800, t);
  f.frequency.exponentialRampToValueAtTime(260, t + 0.09);
  envTo(g, t, 0.002, dur, 0.17);
  var osc = c.createOscillator(); osc.type = "sawtooth"; osc.frequency.value = hz;
  osc.connect(f); f.connect(g); g.connect(o.dest); osc.start(t); osc.stop(t + dur + 0.05);
};

VOICES.fm = function(e, t, o){                  /* two operators; the index rides the envelope, bright to sine */
  var c = e.ctx, hz = o.hz || 220, dur = o.dur || 0.3;
  var car = c.createOscillator(), mod = c.createOscillator(), mg = c.createGain(), g = c.createGain();
  car.frequency.value = hz; mod.frequency.value = hz * 2;
  mg.gain.setValueAtTime(hz * (o.accent ? 5 : 2.5), t);
  mg.gain.exponentialRampToValueAtTime(hz * 0.2, t + dur);
  mod.connect(mg); mg.connect(car.frequency);
  envTo(g, t, 0.004, dur * 0.7, 0.18);
  car.connect(g); g.connect(o.dest);
  car.start(t); mod.start(t); car.stop(t + dur + 0.05); mod.stop(t + dur + 0.05);
};

VOICES.screech = function(e, t, o){             /* a saw fighting a resonance it cannot win */
  var c = e.ctx, hz = o.hz || 440, dur = o.dur || 0.25;
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "bandpass"; f.Q.value = 14;
  f.frequency.setValueAtTime(hz * 3, t);
  f.frequency.exponentialRampToValueAtTime(hz * (o.accent ? 9 : 5), t + dur * 0.6);
  envTo(g, t, 0.004, dur * 0.8, 0.2);
  var osc = c.createOscillator(); osc.type = "sawtooth"; osc.frequency.value = hz;
  osc.connect(f); f.connect(g); g.connect(o.dest); osc.start(t); osc.stop(t + dur + 0.05);
};

VOICES.chord = function(e, t, o){               /* stab's warmer cousin: minor7 voicing, longer, darker */
  var c = e.ctx, hz = o.hz || 220, dur = o.dur || 0.45;
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.frequency.value = o.fc || 1500; f.Q.value = 0.8;
  envTo(g, t, 0.008, dur * 0.85, 0.12);
  f.connect(g); g.connect(o.dest);
  (o.ivals || [0, 3, 7, 10]).forEach(function(semi){
    var osc = c.createOscillator(); osc.type = "sawtooth";
    osc.frequency.value = hz * Math.pow(2, semi / 12);
    osc.connect(f); osc.start(t); osc.stop(t + dur + 0.05);
  });
};

VOICES.bell = function(e, t, o){            /* inharmonic FM: strike, then ring */
  var c = e.ctx, hz = o.hz || 440, dur = o.dur || 0.6;
  var car = c.createOscillator(), mod = c.createOscillator(), mg = c.createGain(), g = c.createGain();
  car.frequency.value = hz; mod.frequency.value = hz * 3.53;
  mg.gain.setValueAtTime(hz * (o.accent ? 9 : 6), t);
  mg.gain.exponentialRampToValueAtTime(hz * 0.05, t + dur * 0.4);
  mod.connect(mg); mg.connect(car.frequency);
  envTo(g, t, 0.002, dur, 0.14);
  car.connect(g); g.connect(o.dest);
  car.start(t); mod.start(t); car.stop(t + dur + 0.05); mod.stop(t + dur + 0.05);
};

VOICES.donk = function(e, t, o){            /* an octave-up sine falling home through a resonant band */
  var c = e.ctx, hz = o.hz || 220, dur = o.dur || 0.22;
  var osc = c.createOscillator(), f = c.createBiquadFilter(), g = c.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(hz * 4, t);
  osc.frequency.exponentialRampToValueAtTime(hz * 2, t + dur * 0.18);
  f.type = "bandpass"; f.frequency.value = hz * 4; f.Q.value = 8;
  envTo(g, t, 0.002, dur * 0.6, o.accent ? 0.26 : 0.2);
  osc.connect(f); f.connect(g); g.connect(o.dest);
  osc.start(t); osc.stop(t + dur + 0.05);
};

VOICES.wob = function(e, t, o){             /* a reese with an LFO on its filter: the wob */
  var c = e.ctx, hz = o.hz || 55, dur = o.dur || 0.5;
  var f = c.createBiquadFilter(), g = c.createGain(), lfo = c.createOscillator(), lg = c.createGain();
  f.type = "lowpass"; f.Q.value = 6;
  f.frequency.value = 700;
  lfo.frequency.value = 3; lg.gain.value = (o.accent ? 900 : 550);
  lfo.connect(lg); lg.connect(f.frequency);
  envTo(g, t, 0.01, dur * 0.85, 0.16);
  f.connect(g); g.connect(o.dest);
  [1, 1.01, 0.5].forEach(function(m, i){
    var osc = c.createOscillator(); osc.type = "sawtooth"; osc.frequency.value = hz * m;
    osc.connect(f); osc.start(t); osc.stop(t + dur + 0.05);
  });
  lfo.start(t); lfo.stop(t + dur + 0.05);
};

VOICES.air = function(e, t, o){             /* noise breathing through a narrow band, four octaves up */
  var c = e.ctx, hz = o.hz || 220, dur = o.dur || 0.8;
  var n = Math.max(1, Math.floor(c.sampleRate * dur)), buf = c.createBuffer(1, n, c.sampleRate);
  var d = buf.getChannelData(0);
  for(var i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
  var src = c.createBufferSource(); src.buffer = buf;
  var f = c.createBiquadFilter(), g = c.createGain(), root = c.createOscillator(), rg = c.createGain();
  f.type = "bandpass"; f.frequency.value = Math.min(hz * 8, 12000); f.Q.value = 12;
  envTo(g, t, dur * 0.35, dur * 0.6, 0.12);
  root.frequency.value = hz * 2; rg.gain.value = 0.03;
  src.connect(f); f.connect(g); root.connect(rg); rg.connect(g); g.connect(o.dest);
  src.start(t); root.start(t); root.stop(t + dur + 0.05);
};

VOICES.kick_dist = VOICES.kick_hard; VOICES.reese = VOICES.bass;
VOICES.ride = VOICES.oh; VOICES.crash = VOICES.oh; VOICES.metal = VOICES.perc;
VOICES.rim = VOICES.perc; VOICES.noise_hit = VOICES.perc; VOICES.tom = VOICES.perc;
VOICES.downlifter = VOICES.riser; VOICES.growl = VOICES.bass;

Engine.prototype.voiceFor = function(name){
  return VOICES[name] || VOICES.perc;
};

/* Which character of a pattern sounds at step `i` of bar `bar`.
 *
 * A pattern of 16 or fewer steps is a bar and repeats every bar, so a 5-step hat
 * against a 16-step kick still gives polymeter. A pattern that is a whole number
 * of bars long (32, 64, 128) SPANS those bars instead of repeating inside one -
 * which is what lets a phrase carry a fill in its last bar, and is the difference
 * between a loop and a track.
 *
 * (The desktop engine spreads any pattern across a single bar instead; the two
 * have always differed here, and the browser is the instrument people use.) */
function patIndex(pat, bar, i){
  var L = pat.length || 16;
  if(L > 16 && L % 16 === 0) return ((bar % (L / 16)) * 16 + i) % L;
  return i % L;
}

/* -- the song model, ported ---------------------------------------------- */

function totalBars(song){
  if(!song) return 0;
  var n = 0;
  (song.order || []).forEach(function(k){
    var s = song.sections && song.sections[k]; if(s) n += (s.bars | 0);
  });
  return n;
}

function sectionAt(song, bar){
  var total = totalBars(song);
  if(!total) return null;
  bar = ((bar % total) + total) % total;
  var acc = 0;
  for(var i = 0; i < song.order.length; i++){
    var name = song.order[i], s = song.sections[name];
    if(!s) continue;
    if(bar < acc + s.bars) return {name: name, sec: s, within: bar - acc, index: i};
    acc += s.bars;
  }
  return null;
}

var CURVES = {
  linear: function(t){ return t; },
  exp:    function(t){ return t * t; },
  log:    function(t){ return Math.sqrt(t); },
  ease:   function(t){ return t * t * (3 - 2 * t); },
  step:   function(t){ return t < 1 ? 0 : 1; }
};

/* The one question. Pure, same as the Python. */
function stateAt(song, bar){
  var at = sectionAt(song, bar);
  if(!at) return null;
  var sec = at.sec;
  var st = {
    tracks: JSON.parse(JSON.stringify(sec.tracks || {})),
    order: (sec.order || Object.keys(sec.tracks || {})).slice(),
    bpm: sec.bpm || song.bpm || 138,
    swing: (sec.swing == null ? (song.swing || 0) : sec.swing),
    section: at.name, within: at.within, bars: sec.bars, role: sec.role
  };
  (sec.automation || []).forEach(function(a){
    var target = a[0], lo = +a[1], hi = +a[2];
    var start = Math.max(0, Math.min(a[3] | 0, sec.bars - 1));
    var len = (a[4] ? (a[4] | 0) : (sec.bars - start));
    len = Math.max(1, Math.min(len, sec.bars - start));
    var curve = CURVES[a[5]] || CURVES.linear;
    if(at.within < start) return;
    var t = len <= 1 ? 1 : Math.min(1, (at.within - start) / (len - 1));
    var v = lo + (hi - lo) * curve(t);
    if(target.indexOf(".") > 0){
      var p = target.split("."), tr = st.tracks[p[0]];
      if(tr) tr[p[1]] = v;
    } else st[target] = v;
  });
  return st;
}

/* -- the clock ----------------------------------------------------------- */

function grooveOf(song){
  var T = global.OONTZ_THEORY;
  if(!T || !T.grooves) return null;
  var name = (song && song.groove) ||
             (T.genre_groove && T.genre_groove[(song && song.meta && song.meta.style) || ""]) || null;
  return name ? T.grooves[name] || null : null;
}

Engine.prototype.loadSong = function(song){
  this.song = song; this.songbar = 0; this.groove = grooveOf(song);
  var st = stateAt(song, 0);
  if(st){ this.tracks = st.tracks; this.order = st.order; this.bpm = st.bpm; this.swing = st.swing; }
  return this;
};

/* Every live edit goes through here. It writes to the playing tracks AND to the
   section under the playhead, because stateAt() rebuilds the tracks every bar and
   would otherwise wipe the edit before you heard it twice. Scoped to the section
   on purpose: a hat you add in the drop should not leak into the break. */
Engine.prototype.setTrack = function(name, patch){
  var tr = this.tracks[name] || (this.tracks[name] = {voice: name, pat: "", gain: 1});
  Object.assign(tr, patch);
  if(this.order.indexOf(name) < 0) this.order.push(name);
  var at = this.song && sectionAt(this.song, this.songbar);
  if(at){ var sec = at.sec; sec.tracks = sec.tracks || {};
    sec.tracks[name] = Object.assign(sec.tracks[name] || {voice: name, pat: "", gain: 1}, patch);
    if(sec.order && sec.order.indexOf(name) < 0) sec.order.push(name); }
  return tr;
};
Engine.prototype.setPattern = function(name, pat){ return this.setTrack(name, {pat: pat}); };

/* Which 16th sounds at a given step. A held roll freezes the index while the step
   count keeps running, so releasing lands where the track would have been. */
Engine.prototype._index = function(step){
  var r = this.roll;
  return r ? (r.i + ((step - r.step) % r.len + r.len) % r.len) % 16 : ((step % 16) + 16) % 16;
};

Engine.prototype.jump = function(bar){
  var total = totalBars(this.song); if(!total) return;
  this.songbar = ((bar % total) + total) % total;
  var st = stateAt(this.song, this.songbar);
  if(st){ this.tracks = st.tracks; this.order = st.order; this.setBpm(st.bpm); this.swing = st.swing; }
  this.step = 0;               // the bar restarts on its first step and does not advance
  if(this.onbar) this.onbar(this.songbar, st);
};

/* One 16th of one bar: schedule every hit into `dest` on context `c`. Pure in
   the sense that matters - it reads only its arguments - so the live clock and
   an OfflineAudioContext render share it. */
/* The `?` maybe-step: a 70% chance decided per (track, bar, step) with the
   exact hash the Python engine uses - both players make identical decisions,
   and the same source renders the same audio every time. */
function maybe(name, bar, i){
  var s = name + "|" + (bar|0) + "|" + (i|0), h = 0;
  for(var k = 0; k < s.length; k++) h = ((h * 31) + s.charCodeAt(k)) >>> 0;
  h = (h ^ (h >>> 15)) >>> 0;
  return (h % 1000) < 700;
}

/* `x... *4` is sugar for the pattern written four times. Capped at 64 steps. */
function expandPat(args){
  var pat = args[0] || "";
  if(args.length > 1 && /^\*\d+$/.test(args[1])){
    var n = Math.max(1, Math.min(Math.floor(64 / Math.max(1, pat.length)), parseInt(args[1].slice(1), 10)));
    pat = new Array(n + 1).join(pat);
  }
  return pat;
}

Engine.prototype._hits = function(c, dest, t, i, tracks, order, bpm, swing, bar){
  var self = this;
  bar = bar | 0;
  var kickHit = false;
  var kt = tracks.kick;
  if(kt && kt.pat){ var ki = patIndex(kt.pat, bar, i), kc = kt.pat[ki];
    if(kc && kc !== "." && kc !== "-" && (kc !== "?" || maybe("kick", bar, ki))) kickHit = true; }
  var e = {ctx: c};
  order.forEach(function(name){
    var tr = tracks[name];
    if(!tr || !tr.pat) return;
    var idx = patIndex(tr.pat, bar, i);
    var ch = tr.pat[idx];
    if(!ch || ch === "." || ch === "-") return;
    if(ch === "?" && !maybe(name, bar, idx)) return;
    if(tr.mute) return;
    var gain = (tr.gain == null ? 1 : tr.gain);
    /* Velocity: the accent curve is what stops sixteen identical hits sounding
       like sixteen identical hits. A written accent (X) overrides it upward. */
    var gr = self.groove;
    if(gr && gr.accent && ch !== "X" && ch !== "O")
      gain *= gr.accent[i % gr.accent.length];
    if(gain <= 0.001) return;
    /* sidechain: duck everything but the kick when the kick lands */
    var duck = (kickHit && tr.sc && name !== "kick") ? (1 - tr.sc * 0.85) : 1;
    var g = c.createGain(); g.gain.value = Math.min(1.2, gain * duck);
    var pan = tr.pan || 0, out = g, tailIn = g;
    if(!keepsLows(name)){                          // highpass everything but the low-end owners
      var hpf = c.createBiquadFilter();
      hpf.type = "highpass"; hpf.frequency.value = 60; hpf.Q.value = 0.7;
      g.connect(hpf); tailIn = hpf;
    }
    if(c.createStereoPanner && pan && dest.numberOfInputs){
      var p = c.createStereoPanner(); p.pan.value = Math.max(-1, Math.min(1, pan));
      tailIn.connect(p); p.connect(dest);
    } else tailIn.connect(dest);
    var opts = {dest: out, accent: ch === "X" || ch === "O", tune: tr.tune,
                fc: tr.fc, res: tr.res, dur: 60 / bpm / 2};
    if(tr.notes && tr.notes.length){
      var tok = tr.notes[idx % tr.notes.length];
      if(!tok || tok === "." || tok === "-") return;
      opts.hz = noteHz(tok);
      if(String(tok).indexOf("~") >= 0) opts.slide = opts.hz * 0.75;
      if(String(tok).indexOf("!") >= 0) opts.accent = true;
      if(!opts.hz) return;
    }
    var sw = (i % 2 && swing) ? (swing / 100) * (60 / bpm / 4) : 0;
    /* Micro-timing: milliseconds off the grid, per step. Small on purpose - past
       about 15ms it stops being feel and starts being a mistake. */
    if(gr && gr.push_ms) sw += gr.push_ms[i % gr.push_ms.length] / 1000;
    try { self.voiceFor(tr.voice || name)(e, Math.max(0, t + sw), opts); } catch(err){}
  });
};

Engine.prototype._tick = function(t){
  var c = this.start(), self = this;
  if(t == null) t = c.currentTime + 0.05;
  var raw = this.step % 16, i = this._index(this.step);

  if(this.song && raw === 0 && this.step > 0){
    this.songbar++;
    var st = stateAt(this.song, this.songbar);
    if(st){ this.tracks = st.tracks; this.order = st.order;
            if(st.bpm && Math.abs(st.bpm - this.bpm) > 0.01) this.setBpm(st.bpm); }
    if(this.onbar) this.onbar(this.songbar, st);
  }

  this._hits(c, this.master, t, i, this.tracks, this.order, this.bpm, this.swing, this.songbar);

  if(this.onstep){ var wait = Math.max(0, (t - c.currentTime) * 1000);   // the grid moves when the sound does
    setTimeout(function(){ self.stepNow = i; if(self.onstep) self.onstep(i, self.tracks, self.order); }, wait); }
  this.step++;
};

/* The standard lookahead clock: a 25ms timer keeps the next 100ms scheduled on the
   audio clock, so timer jitter never reaches the audio. */
Engine.prototype._sched = function(){
  var now = this.ctx.currentTime;
  while(this._next < now + 0.1){ this._tick(this._next); this._next += 60 / this.bpm / 4; }
};

Engine.prototype.setBpm = function(v){
  this.bpm = Math.max(60, Math.min(220, v));
};

Engine.prototype.play = function(){
  if(this.playing) return; var c = this.start();
  this.playing = true; this.step = 0; this._next = c.currentTime + 0.05;
  var self = this;
  this._timer = setInterval(function(){ self._sched(); }, 25);
  this._sched();
};

/* -- decks ----------------------------------------------------------------- */

/* Every beat and every section start, in seconds. We composed it, so this is
   exact - no beat detection. Same walk as song.py's beat_grid(). */
function gridFor(song){
  var grid = [], marks = [], t = 0, total = totalBars(song);
  for(var bar = 0; bar < total; bar++){
    var st = stateAt(song, bar), spb = 60 / (st.bpm || song.bpm || 138);
    if(st.within === 0) marks.push([t, st.section]);
    for(var b = 0; b < 4; b++) grid.push(t + b * spb);
    t += 4 * spb;
  }
  return {grid: grid, marks: marks, seconds: t, bpm: song.bpm || 138};
}

/* What changed between two songs, as human lines - the diff that sells the
   format. Pure; both sides are .song documents. */
function songDiff(a, b){
  var out = [];
  if(!a || !b) return ["nothing to compare"];
  ["bpm", "swing", "key", "scale"].forEach(function(k){
    if(String(a[k] == null ? "" : a[k]) !== String(b[k] == null ? "" : b[k]))
      out.push(k + " " + a[k] + " \u2192 " + b[k]);
  });
  var an = a.order || [], bn = b.order || [];
  bn.forEach(function(n){ if(an.indexOf(n) < 0){ var sb = (b.sections || {})[n] || {};
    out.push("+ section " + n + " (" + (sb.bars || 0) + " bars, " + (sb.role || "?") + ")"); } });
  an.forEach(function(n){ if(bn.indexOf(n) < 0) out.push("- section " + n); });
  bn.forEach(function(n){
    if(an.indexOf(n) < 0) return;
    var sa = (a.sections || {})[n] || {}, sb = (b.sections || {})[n] || {};
    if((sa.bars | 0) !== (sb.bars | 0)) out.push(n + ": " + sa.bars + " \u2192 " + sb.bars + " bars");
    var ta = sa.tracks || {}, tb = sb.tracks || {};
    Object.keys(tb).forEach(function(t){
      if(!ta[t]) return out.push(n + ": + " + t + " (" + (tb[t].voice || t) + ")");
      var x = ta[t], y = tb[t];
      if((x.pat || "") !== (y.pat || "")) out.push(n + "/" + t + ": " + (x.pat || "\u00b7") + " \u2192 " + (y.pat || "\u00b7"));
      if(String(x.notes || "") !== String(y.notes || "")) out.push(n + "/" + t + ": notes changed");
      if((x.voice || t) !== (y.voice || t)) out.push(n + "/" + t + ": voice " + (x.voice || t) + " \u2192 " + (y.voice || t));
      var gx = x.gain == null ? 1 : x.gain, gy = y.gain == null ? 1 : y.gain;
      if(gx !== gy) out.push(n + "/" + t + ": gain " + gx + " \u2192 " + gy);
    });
    Object.keys(ta).forEach(function(t){ if(!tb[t]) out.push(n + ": - " + t); });
  });
  return out.length ? out : ["identical, note for note"];
}

/* The song as a standard MIDI file - the first non-audio output. Drums land on
   channel 10 with GM notes; each pitched track gets its own channel. 16 steps a
   bar at 24 ticks a step (96 PPQ). Deterministic: `?` steps use maybe(). */
var GM_DRUM = {kick: 36, kick_hard: 36, kick_dist: 36, hat: 42, oh: 46, clap: 39,
               snare: 38, perc: 37, rumble: 41, ride: 51, rim: 37, tom: 45, crash: 49};
function songToMidi(song){
  var PPQ = 96, STEP = PPQ / 4, total = totalBars(song);
  var drums = [], melo = {};                     /* name -> events */
  for(var b = 0; b < total; b++){
    var st = stateAt(song, b);
    (st.order || []).forEach(function(name){
      var tr = st.tracks[name];
      if(!tr || !tr.pat || tr.mute) return;
      var L = tr.pat.length || 16;
      for(var i = 0; i < 16; i++){
        var idx = ((b * 16 + i) % L + L) % L;    /* the polymeter walk patIndex does */
        var ch = tr.pat[idx];
        if(!ch || ch === "." || ch === "-") continue;
        if(ch === "?" && !maybe(name, b, idx)) continue;
        var tick = (b * 16 + i) * STEP;
        var vel = ch === "X" || ch === "O" ? 112 : 88;
        var noteTok = tr.notes && tr.notes[idx];
        if(noteTok && noteTok !== "." && noteTok !== "-"){
          var hz = noteHz(String(noteTok).replace(/[~!]/g, ""));
          if(hz > 0){
            var note = Math.max(0, Math.min(127, Math.round(69 + 12 * Math.log2(hz / 440))));
            (melo[name] = melo[name] || []).push({tick: tick, note: note, vel: vel, dur: STEP});
            continue;
          }
        }
        drums.push({tick: tick, note: GM_DRUM[tr.voice || name] || GM_DRUM[name] || 37, vel: vel, dur: STEP / 2});
      }
    });
  }
  function vlq(n){ var b = [n & 0x7f]; while((n >>= 7)) b.unshift((n & 0x7f) | 0x80); return b; }
  function trackBytes(events, chan, tempoMeta){
    var out = [], last = 0;
    if(tempoMeta){ var us = Math.round(60000000 / (song.bpm || 120));
      out = out.concat([0, 0xFF, 0x51, 0x03, (us >> 16) & 255, (us >> 8) & 255, us & 255]); }
    var seq = [];
    events.forEach(function(e){
      seq.push({t: e.tick, on: 1, n: e.note, v: e.vel});
      seq.push({t: e.tick + e.dur, on: 0, n: e.note, v: 0});
    });
    seq.sort(function(a, b2){ return a.t - b2.t || b2.on - a.on; });
    seq.forEach(function(e){
      out = out.concat(vlq(e.t - last)); last = e.t;
      out.push((e.on ? 0x90 : 0x80) | chan, e.n, e.v);
    });
    out = out.concat([0, 0xFF, 0x2F, 0x00]);
    var head = [0x4D, 0x54, 0x72, 0x6B,
                (out.length >> 24) & 255, (out.length >> 16) & 255, (out.length >> 8) & 255, out.length & 255];
    return head.concat(out);
  }
  var names = Object.keys(melo);
  var ntrks = 1 + (names.length ? names.length : 0) + (drums.length ? 1 : 0);
  var bytes = [0x4D, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 1, 0, ntrks, 0, PPQ];
  bytes = bytes.concat(trackBytes([], 0, true));            /* tempo track */
  if(drums.length) bytes = bytes.concat(trackBytes(drums, 9));
  names.forEach(function(n, i2){ bytes = bytes.concat(trackBytes(melo[n], i2 % 8 < 9 ? i2 % 8 : 0)); });
  return new Uint8Array(bytes);
}

/* The whole song, offline, through the same _hits the live clock uses. Mono:
   ponytail: nothing sets pan yet and two 5-minute stereo decks are 200MB. */
function renderSong(song, onProgress, opts){
  var g0 = gridFor(song), total = totalBars(song);
  var C = global.OfflineAudioContext || global.webkitOfflineAudioContext;
  var off = new C(1, Math.ceil((g0.seconds + 1.5) * SR), SR);
  /* `raw` skips the master chain: a deck plays through the LIVE one, and mastering
     the same audio twice glue-compresses and limits it twice, which pumps. */
  var g;
  if(opts && opts.raw){ g = off.createGain(); g.gain.value = 0.85; g.connect(off.destination); }
  else g = buildMaster(off, off.destination);
  var fake = new Engine(); fake.ctx = off; fake.groove = grooveOf(song);
  var t = 0;
  for(var bar = 0; bar < total; bar++){
    var st = stateAt(song, bar), spb = 60 / (st.bpm || g0.bpm);
    for(var i = 0; i < 16; i++) fake._hits(off, g, t + i * spb / 4, i, st.tracks, st.order, st.bpm || g0.bpm, st.swing || 0, bar);
    t += 4 * spb;
    if(onProgress && bar % 16 === 0) onProgress(bar / total);
  }
  return off.startRendering().then(function(buf){
    return {buf: buf, grid: g0.grid, marks: g0.marks, seconds: g0.seconds, bpm: g0.bpm, name: song.name};
  });
}

/* A slice of the song, rendered offline. `only` mutes everything but one track
   WITHOUT removing it from the state, so the kick still ducks what it ducks and
   what you measure is the track as it sits in the mix, not in isolation. */
function renderSlice(song, opts){
  opts = opts || {};
  var bar0 = opts.bar | 0, nBars = Math.max(1, opts.bars || 1), only = opts.only;
  var C = global.OfflineAudioContext || global.webkitOfflineAudioContext;
  var dur = 0, b;
  for(b = 0; b < nBars; b++){
    var s0 = stateAt(song, bar0 + b);
    dur += 4 * 60 / ((s0 && s0.bpm) || song.bpm || 138);
  }
  var off = new C(opts.channels || 2, Math.ceil((dur + 1.2) * SR), SR);
  var g = buildMaster(off, off.destination);
  var fake = new Engine(); fake.ctx = off; fake.groove = grooveOf(song);
  var t = 0;
  for(b = 0; b < nBars; b++){
    var st = stateAt(song, bar0 + b); if(!st) break;
    var spb = 60 / (st.bpm || song.bpm || 138);
    var order = only ? (st.order.indexOf(only) >= 0 ? [only] : []) : st.order;
    for(var i = 0; i < 16; i++)
      fake._hits(off, g, t + i * spb / 4, i, st.tracks, order, st.bpm || song.bpm || 138, st.swing || 0, bar0 + b);
    t += 4 * spb;
  }
  return off.startRendering();
}

/* Every track of one bar, each on its own channel, in a SINGLE render.
 *
 * The ear used to call renderSlice once per track: eight tracks meant eight
 * OfflineAudioContexts per measurement, and `improve` runs six measurements, so a
 * single command opened fifty-odd contexts. Browsers stop handing them out long
 * before that - the tab simply stalls with renders that never resolve.
 *
 * One context, one ChannelMerger, one channel per track. Raw on purpose: a solo'd
 * track pushed through a limiter tuned for the whole mix is not what that track
 * sounds like in the mix.
 */
function renderTracks(song, opts){
  opts = opts || {};
  var bar = opts.bar | 0, st = stateAt(song, bar);
  if(!st) return Promise.reject(new Error("nothing to render"));
  var names = (opts.names || st.order).filter(function(n){
    var tr = st.tracks[n];
    return tr && tr.pat && !tr.mute && tr.pat.replace(/[.\-]/g, "").length;
  }).slice(0, 32);                               // a ChannelMerger tops out at 32
  if(!names.length) return Promise.resolve({names: [], buf: null});

  var spb = 60 / (st.bpm || song.bpm || 138), dur = 4 * spb;
  var C = global.OfflineAudioContext || global.webkitOfflineAudioContext;
  var off = new C(names.length, Math.ceil((dur + 1.2) * SR), SR);
  var merger = off.createChannelMerger(names.length);
  merger.connect(off.destination);

  var fake = new Engine(); fake.ctx = off; fake.groove = grooveOf(song);
  names.forEach(function(n, ch){
    var bus = off.createGain(); bus.gain.value = 1;
    bus.connect(merger, 0, ch);
    for(var i = 0; i < 16; i++)
      fake._hits(off, bus, i * spb / 4, i, st.tracks, [n], st.bpm || song.bpm || 138, st.swing || 0, bar);
  });
  return off.startRendering().then(function(buf){ return {names: names, buf: buf}; });
}

/* A deck is a rendered song, a read position, and a rate. AudioBufferSourceNodes
   have no readable playhead, so position is anchor arithmetic and every seek
   makes a new source. Rate is native and sample-exact: that is the sync. */
function Deck(engine, name){
  this.e = engine; this.name = name; this.r = null;
  this.src = null; this.rate = 1; this.pos0 = 0; this.anchor = null;
  this.loop = null; this.playing = false; this.nodes = null; this.kill = {low: 0, mid: 0, high: 0};
}
Deck.prototype._chain = function(){
  if(this.nodes) return this.nodes;
  var c = this.e.start(), lo = c.createBiquadFilter(), mid = c.createBiquadFilter(), hi = c.createBiquadFilter();
  lo.type = "lowshelf"; lo.frequency.value = 200;
  mid.type = "peaking"; mid.frequency.value = 1000; mid.Q.value = 0.7;
  hi.type = "highshelf"; hi.frequency.value = 4000;
  var gain = c.createGain();
  /* start where the crossfader actually is, or the HUD says 71%/71% while both
     decks run at unity into the limiter */
  gain.gain.value = xfGains(this.e._decks ? this.e._decks.xf : 0)[this.name === "a" ? 0 : 1];
  lo.connect(mid); mid.connect(hi); hi.connect(gain); gain.connect(this.e.master);
  return (this.nodes = {lo: lo, mid: mid, hi: hi, gain: gain});
};
Deck.prototype.load = function(r){ this.stop(); this.r = r; this.pos0 = 0; this.loop = null; return this; };
Deck.prototype.posAt = function(t){
  var p = this.anchor == null ? this.pos0 : this.pos0 + (t - this.anchor) * this.rate;
  if(this.loop && p >= this.loop[1]){ var L = this.loop[1] - this.loop[0]; p = this.loop[0] + ((p - this.loop[0]) % L); }
  return p;
};
Deck.prototype.pos = function(){ return this.posAt(this.e.ctx ? this.e.ctx.currentTime : 0); };
Deck.prototype.play = function(at, when){
  if(!this.r) return; var c = this.e.start(), n = this._chain();
  if(when == null) when = c.currentTime + 0.02;
  var from = at == null ? this.posAt(when) : at;
  this._kill();
  from = Math.max(0, Math.min(this.r.seconds - 0.01, from));
  var s = c.createBufferSource(); s.buffer = this.r.buf; s.playbackRate.value = this.rate;
  if(this.loop){ s.loop = true; s.loopStart = this.loop[0]; s.loopEnd = this.loop[1]; }
  s.connect(n.lo); s.start(when, from);
  this.src = s; this.pos0 = from; this.anchor = when; this.playing = true;
  var self = this;
  s.onended = function(){ if(self.src === s){ self.pos0 = self.r.seconds; self.anchor = null; self.src = null; self.playing = false; } };
};
Deck.prototype._kill = function(){ if(this.src){ var s = this.src; this.src = null; s.onended = null; try{ s.stop(); }catch(e){} } };
Deck.prototype.stop = function(){ this.pos0 = this.pos(); this.anchor = null; this._kill(); this.playing = false; };
Deck.prototype.setRate = function(r){
  var now = this.e.ctx ? this.e.ctx.currentTime : 0;
  this.pos0 = this.posAt(now); this.anchor = this.playing ? now : null;   // re-anchor, or the arithmetic drifts
  this.rate = Math.max(0.5, Math.min(2, r));
  if(this.src) this.src.playbackRate.setValueAtTime(this.rate, now);
};
Deck.prototype.bpm = function(){ return this.r ? this.r.bpm * this.rate : 0; };
Deck.prototype.beatAt = function(p){
  var g = this.r.grid, lo = 0, hi = g.length - 1;
  while(lo < hi){ var mid = (lo + hi + 1) >> 1; if(g[mid] <= p) lo = mid; else hi = mid - 1; }
  return lo;
};
Deck.prototype.beat = function(){ return this.beatAt(this.pos()); };
Deck.prototype.phaseAt = function(t){
  var p = this.posAt(t), g = this.r.grid, i = this.beatAt(p);
  var a = g[i], b = i + 1 < g.length ? g[i + 1] : a + 60 / this.r.bpm;
  return b <= a ? 0 : Math.max(0, Math.min(1, (p - a) / (b - a)));
};
Deck.prototype.beatPhase = function(){ return this.phaseAt(this.e.ctx ? this.e.ctx.currentTime : 0); };
/* Match tempo, then put this deck's read head at the same phase of ITS beat as
   the other deck is through its own - evaluated at one shared instant `when`,
   so the two sources start in lock rather than a scheduling delay apart. */
Deck.prototype.syncTo = function(o){
  if(!o.r || !this.r) return;
  var now = this.e.ctx ? this.e.ctx.currentTime : 0, when = now + 0.05;
  this.setRate(o.bpm() / this.r.bpm);
  var p = this.posAt(when), g = this.r.grid, i = this.beatAt(p);
  var a = g[i], b = i + 1 < g.length ? g[i + 1] : a + 60 / this.r.bpm;
  var target = a + o.phaseAt(when) * (b - a);
  this.loop = null;                              // syncing can land outside the loop
  if(this.playing) this.play(target, when); else this.pos0 = target;
};
Deck.prototype.loopBeats = function(n){
  if(!this.r) return;
  var now = this.e.ctx ? this.e.ctx.currentTime : 0;
  this.pos0 = this.posAt(now); if(this.playing) this.anchor = now;
  if(!n){ this.loop = null; if(this.src) this.src.loop = false; return; }
  var g = this.r.grid, i = this.beatAt(this.pos0), a = g[i], b = g[Math.min(g.length - 1, i + n)];
  if(b <= a) return;
  this.loop = [a, b];
  if(this.src){ this.src.loopStart = a; this.src.loopEnd = b; this.src.loop = true; }
};
Deck.prototype.eq = function(band, v){
  var n = this._chain(), node = {low: n.lo, mid: n.mid, high: n.hi}[band]; if(!node) return null;
  v = Math.max(0, Math.min(2, v));
  node.gain.setTargetAtTime(v <= 0.001 ? -40 : 20 * Math.log10(v), this.e.ctx.currentTime, 0.01);
  return v;
};
Deck.prototype.seekMark = function(dir){
  if(!this.r) return null;
  var m = this.r.marks; if(!m || !m.length) return null;
  this.loop = null;                              // an explicit seek leaves the loop
  var p = this.pos(), k = 0;
  for(var i = 0; i < m.length; i++) if(m[i][0] <= p + 0.01) k = i;
  k = Math.max(0, Math.min(m.length - 1, k + dir));
  if(this.playing) this.play(m[k][0]); else this.pos0 = m[k][0];
  return m[k][1];
};

/* Equal power, same as mixer.py: the long blend keeps the loudness flat. */
function xfGains(p){ var t = (Math.max(-1, Math.min(1, p)) + 1) / 2;
  return [Math.cos(t * Math.PI / 2), Math.sin(t * Math.PI / 2)]; }

Engine.prototype.decks = function(){
  if(!this._decks) this._decks = {a: new Deck(this, "a"), b: new Deck(this, "b"), xf: 0};
  return this._decks;
};
Engine.prototype.crossfade = function(p){
  var d = this.decks(), g = xfGains(p); d.xf = p;
  var ca = d.a._chain(), cb = d.b._chain();      // these create the context
  var now = this.ctx ? this.ctx.currentTime : 0;
  ca.gain.gain.setTargetAtTime(g[0], now, 0.01);
  cb.gain.gain.setTargetAtTime(g[1], now, 0.01);
  return g;
};

/* 16-bit PCM WAV from an AudioBuffer: the `export` command. */
function wavBlob(buf){
  var ch = buf.numberOfChannels, n = buf.length, out = new DataView(new ArrayBuffer(44 + n * ch * 2));
  var w = function(o, str){ for(var i = 0; i < str.length; i++) out.setUint8(o + i, str.charCodeAt(i)); };
  w(0, "RIFF"); out.setUint32(4, 36 + n * ch * 2, true); w(8, "WAVE"); w(12, "fmt ");
  out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, ch, true);
  out.setUint32(24, buf.sampleRate, true); out.setUint32(28, buf.sampleRate * ch * 2, true);
  out.setUint16(32, ch * 2, true); out.setUint16(34, 16, true); w(36, "data"); out.setUint32(40, n * ch * 2, true);
  var o = 44, data = [];
  for(var c = 0; c < ch; c++) data.push(buf.getChannelData(c));
  for(var i = 0; i < n; i++) for(c = 0; c < ch; c++){
    var v = Math.max(-1, Math.min(1, data[c][i]));
    out.setInt16(o, v < 0 ? v * 32768 : v * 32767, true); o += 2; }
  return new Blob([out], {type: "audio/wav"});
}

/* -- a song, in a link ---------------------------------------------------- */
/* The whole point of the format, taken literally: a song is text, text compresses,
 * and a compressed song fits in a URL. A 4-bar loop is ~300 characters and a full
 * five-minute arrangement ~1400 - so a track can travel with no account, no upload
 * and no database, in a message. The payload rides in the FRAGMENT, which browsers
 * never send to a server: nothing to store, nothing to moderate, nothing to leak.
 *
 * The cost is that a fragment is invisible to crawlers, so a link like this can
 * never show a preview card. That is exactly why both mechanisms exist - `share`
 * for a short link that previews, `link` for one that depends on nobody. */
function b64u(bytes){
  var s = "";
  for(var i = 0; i < bytes.length; i += 8192)    /* apply() dies on a big array */
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function unb64u(s){
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while(s.length % 4) s += "=";
  var bin = atob(s), out = new Uint8Array(bin.length);
  for(var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/* One leading byte names the encoding, so an old link keeps working when a better
   one arrives, and a browser without CompressionStream still produces something. */
async function packSong(sg){
  var json = JSON.stringify(sg);
  if(typeof CompressionStream === "undefined")
    return "r" + b64u(new TextEncoder().encode(json));
  var cs = new CompressionStream("deflate-raw");
  var buf = await new Response(new Blob([json]).stream().pipeThrough(cs)).arrayBuffer();
  return "z" + b64u(new Uint8Array(buf));
}

async function unpackSong(s){
  var kind = s[0], bytes = unb64u(s.slice(1));
  var json;
  if(kind === "z"){
    var ds = new DecompressionStream("deflate-raw");
    json = await new Response(new Blob([bytes]).stream().pipeThrough(ds)).text();
  } else if(kind === "r"){
    json = new TextDecoder().decode(bytes);
  } else throw new Error("unknown link format");
  var sg = JSON.parse(json);
  if(!sg || !sg.order || !sg.sections) throw new Error("not a song");
  return sg;
}

/* -- the keyboard as a controller ---------------------------------------- */
/* The same table as oontz/keymap.py, minus what a browser cannot do. Returns a
   short message when a key was handled, null when it was not. Pure enough to run
   in node with no AudioContext: only the sweep and the rate effects need one. */

var PADS = "qwertyuiasdfghjk";
var KEYS = [
  ["space", "play / stop"], ["1-8", "focus a track"],
  ["q w e r t y u i", "steps 1-8 of the focused track  . -> x -> X"],
  ["a s d f g h j k", "steps 9-16"], ["z / x", "mute / solo the focused track"],
  ["[ ]  (hold)", "sweep the master filter"], ["/  (hold)", "loop roll"],
  ["\\", "spinback"], ["`", "tape stop"], ["- =", "tempo"], [", .", "swing"],
  ["< >", "previous / next section"], ["R", "record what you hear"],
  ["Esc", "leave the prompt and play the keys"], [":", "back to the prompt"], ["?", "this table"]
];

/* One step, cycled . -> x -> X -> . The pads, a click on the rack and a phone tap
   all land here, so the rules about keeping notes aligned live in one place. */
/* setStep: paint-friendly - force a step to a state instead of cycling it. */
Engine.prototype.setStep = function(name, i, on){
  var tr = this.tracks[name];
  if(!tr) return null;
  var pat = (tr.pat || "").padEnd(16, ".").split("");
  i = patIndex(pat.join(""), this.songbar, i);
  var ch = pat[i], want = on ? (ch === "X" ? "X" : "x") : ".";
  if(ch === want) return null;
  pat[i] = want;
  this.setTrack(name, {pat: pat.join("")});
  return name + " " + pat.join("");
};

Engine.prototype.toggleStep = function(name, i){
  var tr = this.tracks[name];
  if(!tr) return "no track to edit";
  var pat = (tr.pat || "").padEnd(16, ".").split("");
  i = patIndex(pat.join(""), this.songbar, i);       // the bar you are hearing is the bar you edit
  var ch = pat[i], nx = ch === "." || ch === "-" ? "x" : (ch === "x" ? "X" : ".");
  pat[i] = nx;
  var patch = {pat: pat.join("")};
  if(tr.notes){                                // a pitched track keeps its notes aligned to its hits
    /* pad to the PATTERN, not to 16: editing bar 2 of a 128-step pattern used to
       write past the end of a 16-long notes array, leaving holes that silenced
       the track wherever they landed */
    var notes = tr.notes.slice(0, pat.length);
    while(notes.length < pat.length) notes.push(".");
    var rest = function(x){ return x === "." || x === "-"; };
    if(nx === ".") notes[i] = ".";
    else { if(rest(notes[i])) notes[i] = (notes.filter(function(x){ return !rest(x); })[0] || "a1").replace(/[~!]+$/, "");
           notes[i] = notes[i].replace("!", "") + (nx === "X" ? "!" : ""); }
    patch.notes = notes;
  }
  this.setTrack(name, patch); this.focus = name;
  return name + " " + patch.pat;
};

Engine.prototype.key = function(k, down){
  var self = this, foc = this.focus && this.tracks[this.focus] ? this.focus : this.order[0];
  var tr = foc && this.tracks[foc];
  if(!down){ if(k === "/" && this.roll){ this.roll = null; return "roll off"; } return null; }
  if(k === " "){ if(this.playing) this.stop(); else this.play(); return this.playing ? "play" : "stop"; }
  if(/^[1-8]$/.test(k)){ var n = this.order[+k - 1]; if(!n) return "no track " + k; this.focus = n; return "focus " + n; }
  var pi = PADS.indexOf(k);
  if(pi >= 0) return this.toggleStep(foc, pi);
  if(k === "z"){ if(!tr) return null; this.setTrack(foc, {mute: !tr.mute}); return foc + (tr.mute ? " muted" : " on"); }
  if(k === "x"){ if(!tr) return null; var solo = !this._solo; this._solo = solo;
    this.order.forEach(function(nm){ self.setTrack(nm, {mute: solo && nm !== foc}); });
    return solo ? "solo " + foc : "solo off"; }
  if(k === "-" || k === "="){ this.setBpm(this.bpm + (k === "-" ? -1 : 1)); if(this.song) this.song.bpm = this.bpm; return this.bpm + " BPM"; }
  if(k === "," || k === "."){ this.swing = Math.max(0, Math.min(60, this.swing + (k === "," ? -2 : 2))); return "swing " + this.swing; }
  if(k === "<" || k === ">"){ if(!this.song) return "no song"; var at = sectionAt(this.song, this.songbar); if(!at) return null;
    var start = this.songbar - at.within;
    if(k === ">") this.jump(start + at.sec.bars);
    else { var pb = at.within > 0 ? start : start - 1, pa = sectionAt(this.song, pb);
           this.jump(pa ? pb - pa.within : pb); }        // to the START of the previous section
    var a2 = sectionAt(this.song, this.songbar); return "-> " + (a2 ? a2.name : ""); }
  if(k === "/"){ if(!this.roll) this.roll = {i: this._index(this.step - 1), step: this.step, len: 1}; return "roll"; }
  if(k === "[" || k === "]"){
    this.fc = Math.max(80, Math.min(20000, this.fc * (k === "[" ? 1 / 1.06 : 1.06)));
    if(this.filter) this.filter.frequency.setTargetAtTime(this.fc, this.ctx.currentTime, 0.02);
    return "filter " + Math.round(this.fc) + " Hz"; }
  if(k === "\\"){ this.rateFx(function(t){ return -1.5 * Math.exp(-t / 0.35); }, 1.2); return "spinback"; }
  if(k === "`"){ this.rateFx(function(t){ return Math.exp(-t / 0.6); }, 1.5); return "tape stop"; }
  return null;
};

Engine.prototype.stop = function(){
  this.playing = false;
  if(this._timer) clearInterval(this._timer);
  this._timer = null;
};

global.oontz = {
  Engine: Engine, VOICES: VOICES, noteHz: noteHz, KEYS: KEYS, PADS: PADS,
  Deck: Deck, gridFor: gridFor, renderSong: renderSong, renderSlice: renderSlice,
  songDiff: songDiff, songToMidi: songToMidi, maybe: maybe, expandPat: expandPat,
  patIndex: patIndex, grooveOf: grooveOf, buildMaster: buildMaster, keepsLows: keepsLows,
  renderTracks: renderTracks,
  xfGains: xfGains, wavBlob: wavBlob, packSong: packSong, unpackSong: unpackSong,
  stateAt: stateAt, sectionAt: sectionAt, totalBars: totalBars, SR: SR
};
})(typeof window !== "undefined" ? window : globalThis);
