/* oontz browser engine — the WebAudio port of the thud voice bank and sequencer.
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
  this._timer = null; this._next = 0;
}

Engine.prototype.start = function(){
  if(this.ctx) { if(this.ctx.state === "suspended") this.ctx.resume(); return this.ctx; }
  var C = global.AudioContext || global.webkitAudioContext;
  var c = this.ctx = new C();
  this.master = c.createGain(); this.master.gain.value = 0.85;
  var comp = c.createDynamicsCompressor();
  comp.threshold.value = -8; comp.ratio.value = 14;
  comp.attack.value = 0.002; comp.release.value = 0.10;
  this.analyser = c.createAnalyser();
  this.analyser.fftSize = 2048; this.analyser.smoothingTimeConstant = 0.75;
  this.master.connect(comp); comp.connect(this.analyser);
  this.analyser.connect(c.destination);
  return c;
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
  var g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.frequency.value = o.fc || 800;
  g.gain.setValueAtTime(0.0001, t);
  g.gain.linearRampToValueAtTime(0.11, t + dur * 0.4);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  f.connect(g); g.connect(o.dest);
  [0, 7, 12].forEach(function(semi){
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
VOICES.kick_dist = VOICES.kick_hard; VOICES.reese = VOICES.bass;
VOICES.hoover = VOICES.stab; VOICES.lead = VOICES.stab; VOICES.pluck = VOICES.stab;
VOICES.screech = VOICES.bass; VOICES.chord = VOICES.stab; VOICES.fm = VOICES.stab;
VOICES.ride = VOICES.oh; VOICES.crash = VOICES.oh; VOICES.metal = VOICES.perc;
VOICES.rim = VOICES.perc; VOICES.noise_hit = VOICES.perc; VOICES.tom = VOICES.perc;
VOICES.downlifter = VOICES.riser; VOICES.growl = VOICES.bass;

Engine.prototype.voiceFor = function(name){
  return VOICES[name] || VOICES.perc;
};

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

Engine.prototype.loadSong = function(song){
  this.song = song; this.songbar = 0;
  var st = stateAt(song, 0);
  if(st){ this.tracks = st.tracks; this.order = st.order; this.bpm = st.bpm; this.swing = st.swing; }
  return this;
};

Engine.prototype.setPattern = function(name, pat){
  if(!this.tracks[name]) this.tracks[name] = {voice: name, pat: pat, gain: 1};
  else this.tracks[name].pat = pat;
  if(this.order.indexOf(name) < 0) this.order.push(name);
};

Engine.prototype._tick = function(){
  var c = this.start(), t = c.currentTime + 0.05;
  var i = this.step % 16, self = this;

  if(this.song && i === 0 && this.step > 0){
    this.songbar++;
    var st = stateAt(this.song, this.songbar);
    if(st){ this.tracks = st.tracks; this.order = st.order;
            if(st.bpm && Math.abs(st.bpm - this.bpm) > 0.01) this.setBpm(st.bpm); }
    if(this.onbar) this.onbar(this.songbar, st);
  }

  var kickHit = false;
  var kt = this.tracks.kick;
  if(kt && kt.pat && kt.pat[i % kt.pat.length] && kt.pat[i % kt.pat.length] !== ".") kickHit = true;

  this.order.forEach(function(name){
    var tr = self.tracks[name];
    if(!tr || !tr.pat) return;
    var L = tr.pat.length || 16;
    var ch = tr.pat[i % L];
    if(!ch || ch === "." || ch === "-") return;
    if(tr.mute) return;
    var gain = (tr.gain == null ? 1 : tr.gain);
    if(gain <= 0.001) return;
    /* sidechain: duck everything but the kick when the kick lands */
    var duck = (kickHit && tr.sc && name !== "kick") ? (1 - tr.sc * 0.85) : 1;
    var g = c.createGain(); g.gain.value = Math.min(1.2, gain * duck);
    var pan = tr.pan || 0, dest = g;
    if(c.createStereoPanner && pan){
      var p = c.createStereoPanner(); p.pan.value = Math.max(-1, Math.min(1, pan));
      g.connect(p); p.connect(self.master); dest = g;
    } else g.connect(self.master);
    var opts = {dest: dest, accent: ch === "X" || ch === "O", tune: tr.tune,
                fc: tr.fc, res: tr.res, dur: 60 / self.bpm / 2};
    if(tr.notes && tr.notes.length){
      var tok = tr.notes[i % tr.notes.length];
      if(!tok || tok === "." || tok === "-") return;
      opts.hz = noteHz(tok);
      if(String(tok).indexOf("~") >= 0) opts.slide = opts.hz * 0.75;
      if(String(tok).indexOf("!") >= 0) opts.accent = true;
      if(!opts.hz) return;
    }
    var swing = (i % 2 && self.swing) ? (self.swing / 100) * (60 / self.bpm / 4) : 0;
    try { self.voiceFor(tr.voice || name)(self, t + swing, opts); } catch(err){}
  });

  if(this.onstep) this.onstep(i, this.tracks, this.order);
  this.step++;
};

Engine.prototype.setBpm = function(v){
  this.bpm = Math.max(60, Math.min(220, v));
  if(this.playing){ clearInterval(this._timer);
    var self = this;
    this._timer = setInterval(function(){ self._tick(); }, 60 / this.bpm / 4 * 1000); }
};

Engine.prototype.play = function(){
  if(this.playing) return; this.start();
  this.playing = true; this.step = 0;
  var self = this;
  this._timer = setInterval(function(){ self._tick(); }, 60 / this.bpm / 4 * 1000);
  this._tick();
};

Engine.prototype.stop = function(){
  this.playing = false;
  if(this._timer) clearInterval(this._timer);
  this._timer = null;
};

global.oontz = {
  Engine: Engine, VOICES: VOICES, noteHz: noteHz,
  stateAt: stateAt, sectionAt: sectionAt, totalBars: totalBars, SR: SR
};
})(window);
