/* The audio side of the spike: a queue of pre-rendered bars, sliced 128 frames
 * at a time. Python never runs here — this is the same shape as the native
 * callback, which only ever copies out of ST.bar. Underrun plays silence and
 * counts, exactly like the desktop's drop counter. */
class BarPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bars = [];            // Float32Array, interleaved stereo
    this.pos = 0;              // frame index into bars[0]
    this.on = false;
    this.drops = 0;
    this.port.onmessage = (e) => {
      const m = e.data;
      if (m.t === "bar") this.bars.push(m.buf);
      else if (m.t === "start") this.on = true;
      else if (m.t === "stop") { this.on = false; this.bars = []; this.pos = 0; }
    };
  }
  process(_in, out) {
    const L = out[0][0], R = out[0][1] || out[0][0], n = L.length;
    if (!this.on || !this.bars.length) {
      if (this.on) { this.drops++; this.port.postMessage({ t: "drop", n: this.drops }); }
      return true;
    }
    let bar = this.bars[0], p = this.pos;
    for (let i = 0; i < n; i++) {
      if (p * 2 >= bar.length) {                      // bar boundary
        this.bars.shift(); this.pos = p = 0;
        this.port.postMessage({ t: "need", queued: this.bars.length });
        if (!this.bars.length) { this.drops++; break; }
        bar = this.bars[0];
      }
      L[i] = bar[p * 2]; R[i] = bar[p * 2 + 1]; p++;
    }
    this.pos = p;
    return true;
  }
}
registerProcessor("bar-player", BarPlayer);
