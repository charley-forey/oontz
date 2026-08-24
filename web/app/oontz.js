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
  this.focus = null;           // the track the pads edit
  this.roll = null;            // {i, step, len} while a loop roll is held
  this.fc = 20000;             // the master filter, swept by [ and ]
  this.stepNow = 0;            // the step that is sounding right now (for the grid)
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
  /* master -> filter -> delay line -> out -> comp -> analyser. The filter is the
     [ ] sweep. The delay line sits at 0 and is only ever moved by rateFx: a
     DelayNode is a ring buffer with a read head, which is what a spinback needs. */
  this.filter = c.createBiquadFilter(); this.filter.type = "lowpass";
  this.filter.frequency.value = this.fc; this.filter.Q.value = 0.7;
  this.fx = c.createDelay(4); this.fx.delayTime.value = 0;
  this.out = c.createGain();
  this.master.connect(this.filter); this.filter.connect(this.fx); this.fx.connect(this.out);
  this.out.connect(comp); comp.connect(this.analyser);
  this.analyser.connect(c.destination);
  return c;
};

/* Read the delay line at speed r(t): a rate is a delay d(t) = t - integral(r), so a
   negative rate reads backwards. Same idea as dj.py moving a pointer, on a node
   the browser already has. After `dur` the head snaps back to live. */
Engine.prototype.rateFx = function(rate, dur){
  var c = this.ctx; if(!c || !this.fx) return;
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

/* -- the keyboard as a controller ---------------------------------------- */
/* The same table as thud/keymap.py, minus what a browser cannot do. Returns a
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

Engine.prototype.key = function(k, down){
  var self = this, foc = this.focus && this.tracks[this.focus] ? this.focus : this.order[0];
  var tr = foc && this.tracks[foc];
  if(!down){ if(k === "/" && this.roll){ this.roll = null; return "roll off"; } return null; }
  if(k === " "){ if(this.playing) this.stop(); else this.play(); return this.playing ? "play" : "stop"; }
  if(/^[1-8]$/.test(k)){ var n = this.order[+k - 1]; if(!n) return "no track " + k; this.focus = n; return "focus " + n; }
  var pi = PADS.indexOf(k);
  if(pi >= 0){
    if(!tr) return "no track to edit";
    var pat = (tr.pat || "").padEnd(16, ".").slice(0, 16).split("");   // ponytail: pads see 16 steps; polymeter stays a typed thing
    var ch = pat[pi], nx = ch === "." || ch === "-" ? "x" : (ch === "x" ? "X" : ".");
    pat[pi] = nx;
    var patch = {pat: pat.join("")};
    if(tr.notes){                              // a pitched track keeps its notes aligned to its hits
      var notes = tr.notes.slice(0, 16); while(notes.length < 16) notes.push(".");
      var rest = function(x){ return x === "." || x === "-"; };
      if(nx === ".") notes[pi] = ".";
      else { if(rest(notes[pi])) notes[pi] = (notes.filter(function(x){ return !rest(x); })[0] || "a1").replace(/[~!]+$/, "");
             notes[pi] = notes[pi].replace("!", "") + (nx === "X" ? "!" : ""); }
      patch.notes = notes;
    }
    this.setTrack(foc, patch); this.focus = foc;
    return foc + " " + patch.pat;
  }
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
  stateAt: stateAt, sectionAt: sectionAt, totalBars: totalBars, SR: SR
};
})(typeof window !== "undefined" ? window : globalThis);
