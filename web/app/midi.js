/* WebMIDI. Plug a controller in and it plays the same instrument the keyboard
 * does, because every note dispatches the KeyboardEvent the key would have
 * sent (touch.js taught us this trick). Nothing here knows any music.
 *
 * The map, chosen for the common cheap pad controller:
 *   notes 36-51   the 16 step pads (36 = step 1, GM drum-pad layout)
 *   note  52/53   previous / next section        note 54  mute   note 55  solo
 *   note  56      spinback                       note 57  tape stop
 *   CC 74 (or 1)  master filter: turning up taps ], down taps [
 *   CC 64 ≥64     transport (sustain pedal = play/stop, obviously)
 * Pure tables exported for check.js.
 */
(function (g) {
"use strict";

var PAD_BASE = 36;
var PADS = "qwertyuiasdfghjk".split("");
var NOTE_KEYS = {52: "<", 53: ">", 54: "z", 55: "x", 56: "\\", 57: "`"};
var FILTER_CCS = {74: 1, 1: 1};

var MIDI = { PAD_BASE: PAD_BASE, PADS: PADS, NOTE_KEYS: NOTE_KEYS, FILTER_CCS: FILTER_CCS,
             keyForNote: function (n) {
               if (n >= PAD_BASE && n < PAD_BASE + 16) return PADS[n - PAD_BASE];
               return NOTE_KEYS[n] || null;
             } };
g.OONTZ_MIDI = MIDI;
if (typeof navigator === "undefined") return;          /* node: tables only */

var access = null, last = {};                          /* last CC value per controller number */

function send(type, key) {
  var IN = document.getElementById("in");
  if (document.activeElement === IN) IN.blur();
  dispatchEvent(new KeyboardEvent(type, { key: key, bubbles: true }));
}
function tap(key) { send("keydown", key); send("keyup", key); }

function onMsg(e) {
  var d = e.data, st = d[0] & 0xf0;
  if (st === 0x90 && d[2] > 0) {                       /* note on */
    var k = MIDI.keyForNote(d[1]);
    if (k) tap(k);
  } else if (st === 0xb0) {                            /* control change */
    var cc = d[1], v = d[2];
    if (cc === 64) { if (v >= 64) tap(" "); return; }
    if (FILTER_CCS[cc]) {
      var was = last[cc] == null ? v : last[cc]; last[cc] = v;
      if (v > was) tap("]"); else if (v < was) tap("[");
    }
  }
}

function wire() {
  var names = [];
  access.inputs.forEach(function (inp) { inp.onmidimessage = onMsg; names.push(inp.name); });
  return names;
}

MIDI.connect = function (done) {
  if (!navigator.requestMIDIAccess) return done(null, "this browser has no WebMIDI (Chrome and Edge do)");
  if (access) return done(wire());
  navigator.requestMIDIAccess({ sysex: false }).then(function (a) {
    access = a;
    a.onstatechange = function () { wire(); };         /* hot-plug just works */
    done(wire());
  }, function () { done(null, "MIDI permission denied"); });
};
MIDI.off = function () {
  if (access) access.inputs.forEach(function (inp) { inp.onmidimessage = null; });
};
})(typeof window !== "undefined" ? window : globalThis);
