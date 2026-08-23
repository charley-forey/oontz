"""Effect bank - every effect is a pure function of a buffer and its params.

CONTRACT (contracts.py): f(x, **params) -> ndarray, same shape in as out, mono
(n,) or stereo (n,2), input never mutated, peak <= 1.0, deterministic. Adding an
effect = adding an entry to FX at the bottom; core.py never changes.

House note on filtering: voices.svf is a per-sample Python loop - fine for a
0.3s hat, 99ms per pass on an 80k-sample bar. Effects run on whole bars and eq3
runs off the live kill keys, so the filtering here is either FFT-domain (eq3,
phaser) or a 2-tap FIR inside a feedback path (delay, reverb). Same maths, ~50x
cheaper.
"""
import functools

import numpy as np

from .contracts import SR, TAU, FX

_HOP = 256                    # ~5.8ms: the grid for every envelope follower here


def _cap(y):
    """Last line of defence for the peak <= 1.0 rule - the wav writer wraps."""
    return np.clip(y, -1.0, 1.0)


def _damp(v, d):
    """2-tap FIR lowpass for a feedback path.

    An IIR one-pole would need per-sample state; this compounds once per repeat,
    which is exactly what makes echoes and reverb tails get darker, and it can
    never self-oscillate.
    """
    if not d:
        return v
    return (1.0 - d) * v + d * np.concatenate((v[:1], v[:-1]))


def _fb(x, d, fb, damp=0.0):
    """Feedback comb: y[i] = x[i] + fb*lp(y[i-d]).

    Walked one delay-length at a time, so it is n/d numpy ops instead of n
    Python iterations - block k only ever depends on block k-1, which is
    already final.
    """
    y = np.array(x, float)
    for i in range(d, len(y), d):
        j = min(i + d, len(y))
        y[i:j] += fb * _damp(y[i - d:j - d], damp)
    return y


def _allpass(x, d, g):
    """Schroeder allpass, same block walk as _fb."""
    y = -g * np.asarray(x, float)
    if d < len(y):
        y[d:] += x[:-d]
    for i in range(d, len(y), d):
        j = min(i + d, len(y))
        y[i:j] += g * y[i - d:j - d]
    return y


def _benv(m, atk, rel):
    """Peak envelope on the _HOP grid with attack/release ballistics.

    ponytail: block ballistics, not per-sample. A sample-accurate follower is
    80k Python iterations a bar; this is ~300, and 6ms of grid is inaudible on
    a compressor or a gate. Go per-sample only for a true peak limiter.
    """
    n = len(m)
    nb = -(-n // _HOP)
    pad = np.zeros(nb * _HOP)
    pad[:n] = m
    pk = pad.reshape(nb, _HOP).max(1)
    ca = np.exp(-_HOP / SR / max(atk, 1e-5))
    cr = np.exp(-_HOP / SR / max(rel, 1e-5))
    e = np.empty(nb)
    s = 0.0
    for i, v in enumerate(pk):
        c = ca if v > s else cr
        s = v + c * (s - v)
        e[i] = s
    return e


def _mono(y):
    """Detector signal: stereo-linked, so a gain ride never wobbles the image."""
    return np.abs(y).max(1) if y.ndim == 2 else np.abs(y)


def _up(g, n, ndim):
    """Block gains -> per-sample gain, ready to broadcast. interp is the ramp."""
    v = np.interp(np.arange(n), np.arange(len(g)) * _HOP, g)
    return v[:, None] if ndim == 2 else v

# ------------------------------------------------------------------ distortion


def drive(x, amount=0.5):
    """tanh saturation, peak-compensated so it dirties instead of just louder.

    amount=0 is a true bypass: tanh(kx)/tanh(k) -> x as k -> 0.
    """
    k = max(1e-3, float(amount) * 4.0)
    return _cap(np.tanh(np.asarray(x, float) * k) / np.tanh(k))


def fold(x, amount=2.0):
    """Wavefolder. Reflects past 1.0 instead of flattening, so it keeps adding
    harmonics as you push it - the industrial cousin of drive."""
    y = np.asarray(x, float) * max(float(amount), 0.0)
    return _cap(np.abs((y - 1.0) % 4.0 - 2.0) - 1.0)      # triangle fold


def bitcrush(x, bits=8, rate=8000.0):
    """Bit depth + sample rate, the two halves of a crusher. rate is a
    sample-and-hold, not a resample: the aliasing is the point."""
    y = np.asarray(x, float)
    q = 2.0 ** max(1, int(bits) - 1)
    y = np.round(y * q) / q
    step = max(1, int(round(SR / max(float(rate), 1.0))))
    return _cap(y[np.arange(len(y)) // step * step])       # works on (n,) and (n,2)

# ----------------------------------------------------------------------- time


def delay(x, beats=0.75, bpm=132.0, feedback=0.4, mix=0.3, damp=0.3, pingpong=False):
    """Tempo-synced echo. beats=0.75 is the dotted 1/8 every techno record uses."""
    y = np.array(x, float)
    d = max(1, int(SR * 60.0 / max(float(bpm), 1e-3) * float(beats)))
    fb = min(abs(float(feedback)), 0.95)                   # >=1 would never decay
    if y.ndim == 2 and pingpong:
        w = np.array(y)
        for i in range(d, len(w), d):                      # cross-coupled taps
            j = min(i + d, len(w))
            v = _damp(w[i - d:j - d], damp)
            w[i:j, 0] += fb * v[:, 1]
            w[i:j, 1] += fb * v[:, 0]
    else:
        w = _fb(y, d, fb, damp)
    return _cap(y * (1.0 - mix) + (w - y) * mix)           # w - y is the wet only


def _tank(m, size, damp, spread):
    """4 parallel combs -> 2 series allpasses. Freeverb delay times, scaled.

    Comb feedback tops out at 0.96, so the tail always decays - that is the
    whole stability argument.
    """
    s = 0.6 + 1.4 * min(max(float(size), 0.0), 1.0)
    g = 0.72 + 0.24 * min(max(float(size), 0.0), 1.0)
    w = np.zeros(len(m))
    for d in (1557, 1617, 1491, 1422):
        w += _fb(m, max(1, int(d * s) + spread), g, damp) - m
    w /= 4.0
    for d in (225, 556):
        w = _allpass(w, max(1, int(d * s) + spread), 0.5)
    return w


def reverb(x, size=0.6, damp=0.4, mix=0.25):
    """Schroeder tank, run per channel with a small delay spread for width."""
    y = np.array(x, float)
    if y.ndim == 2:
        w = np.stack([_tank(y[:, 0], size, damp, 0),
                      _tank(y[:, 1], size, damp, 23)], 1)  # freeverb stereospread
    else:
        w = _tank(y, size, damp, 0)
    return _cap(y * (1.0 - mix) + w * mix)


def chorus(x, rate=0.6, depth=0.004, base=0.012, mix=0.4):
    """Modulated short delay. Stereo gets the LFO in quadrature - that is the
    spread; mono just gets the wobble."""
    y = np.array(x, float)
    n = len(y)
    idx = np.arange(n, dtype=float)
    t = idx / SR

    def tap(m, ph):                                        # fractional delay
        d = (base + depth * np.sin(TAU * rate * t + ph)) * SR
        return np.interp(idx - d, idx, m, left=0.0)

    if y.ndim == 2:
        w = np.stack([tap(y[:, 0], 0.0), tap(y[:, 1], np.pi / 2)], 1)
    else:
        w = tap(y, 0.0)
    return _cap(y * (1.0 - mix) + w * mix)


def phaser(x, rate=0.4, stages=4, mix=0.5, fmin=200.0, fmax=1600.0):
    """Cascaded first-order allpass swept by an LFO, applied per block in the
    frequency domain.

    WHY not a sample loop: the coefficient only has to track a 0.4Hz LFO, so it
    is constant across a 2048-sample block. One rfft per block beats 320k Python
    iterations a bar and the notches land in the same place. The notches come
    from summing with the dry - an allpass alone is flat.
    """
    y = np.array(x, float)
    n = len(y)
    N = 2048
    hop = N // 2
    win = np.hanning(N + 1)[:N]                            # periodic: 50% OLA sums to 1
    z = np.exp(-1j * TAU * np.arange(N // 2 + 1) / N)
    sh = (-1,) + (1,) * (y.ndim - 1)
    pad = np.zeros((n + 3 * N,) + y.shape[1:])
    pad[hop:hop + n] = y            # lead-in block, so every real sample is
    out = np.zeros_like(pad)        # covered by two windows and OLA sums to 1
    for i in range(0, n + hop, hop):
        fc = fmin * (fmax / fmin) ** (0.5 + 0.5 * np.sin(TAU * rate * (i + hop) / SR))
        g = np.tan(np.pi * fc / SR)
        a = (1.0 - g) / (1.0 + g)
        H = ((z - a) / (1.0 - a * z)) ** int(stages)       # -pi/2 of phase at fc
        blk = np.fft.rfft(pad[i:i + N] * win.reshape(sh), axis=0)
        out[i:i + N] += np.fft.irfft(blk * H.reshape(sh), N, axis=0)
    return _cap(y * (1.0 - mix) + out[hop:hop + n] * mix)

# ------------------------------------------------------------------- spectral


def width(x, amount=1.4):
    """Mid/side widener. 0.0 collapses to mono, 1.0 is untouched, >1 is wider.
    Mono in is mono out - there is no side to widen."""
    y = np.array(x, float)
    if y.ndim == 1:
        return _cap(y)
    m = (y[:, 0] + y[:, 1]) * 0.5
    s = (y[:, 0] - y[:, 1]) * 0.5 * float(amount)
    return _cap(np.stack([m + s, m - s], 1))


def _band(f, hz, oct_=1.0):
    """Raised-cosine crossover in log freq: 0 below, 1 above, smooth between."""
    u = np.clip(np.log2(np.maximum(f, 1e-6) / hz) / (2.0 * oct_) + 0.5, 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(np.pi * u)


@functools.lru_cache(maxsize=8)
def _bands(n, lo_hz, hi_hz):
    """Padded FFT length + both crossover curves, cached - they only change
    when the bpm does.

    The length matters: numpy falls back to Bluestein on large prime factors,
    and a bar is an ugly number (80182 = 2*47*853 -> 146ms). Rounding up to the
    next 5-smooth length costs 1% more samples and runs in 11ms.
    """
    N = max(int(n), 2)
    while True:
        r = N
        for p in (2, 3, 5):
            while r % p == 0:
                r //= p
        if r == 1:
            break
        N += 1
    f = np.fft.rfftfreq(N, 1.0 / SR)
    return N, _band(f, lo_hz), _band(f, hi_hz)


def eq3(x, low=1.0, mid=1.0, high=1.0, lo_hz=200.0, hi_hz=2000.0):
    """DJ three-band: 0.0 is a full kill, 1.0 unity. What the kill keys drive.

    One rfft for the whole buffer instead of three svf passes (99ms each, per
    channel). The crossovers are complementary, so all-unity is bit-flat and it
    early-outs anyway; a kill is an exact zero, with no filter ringing to hear.
    """
    y = np.asarray(x, float)
    if low == mid == high == 1.0:
        return y.copy()
    n = len(y)
    N, a, b = _bands(n, lo_hz, hi_hz)
    g = low * (1.0 - a) + mid * a * (1.0 - b) + high * b   # the three sum to 1
    w = np.fft.irfft(np.fft.rfft(y.T, N) * g, N).T         # .T so channels are
    return _cap(w[:n])                                     # the contiguous axis

# ------------------------------------------------------------------- dynamics


def comp(x, threshold=0.3, ratio=4.0, attack=0.005, release=0.12, makeup=1.0):
    """Feed-forward compressor, stereo-linked."""
    y = np.array(x, float)
    e = _benv(_mono(y), attack, release)
    over = np.maximum(e, 1e-9) / max(float(threshold), 1e-6)
    g = np.where(over > 1.0, over ** (1.0 / max(float(ratio), 1e-3) - 1.0), 1.0)
    return _cap(y * _up(g, len(y), y.ndim) * makeup)


def limiter(x, ceiling=0.95, release=0.05):
    """Brickwall, no lookahead: a fast gain ride, then a hard clip that
    guarantees the ceiling even on the transient the block grid stepped over."""
    c = abs(float(ceiling))
    y = np.array(x, float)
    e = _benv(_mono(y), 0.0005, release)
    g = np.minimum(1.0, c / np.maximum(e, 1e-9))
    return np.clip(y * _up(g, len(y), y.ndim), -c, c)


def gate(x, threshold=0.1, attack=0.002, release=0.05, floor=0.0):
    """Noise gate - the pad chopper. The interp between block gains is the ramp,
    which is why it does not click."""
    y = np.array(x, float)
    e = _benv(_mono(y), attack, release)
    g = np.where(e >= float(threshold), 1.0, float(floor))
    return _cap(y * _up(g, len(y), y.ndim))


FX.update({
    "drive": drive, "fold": fold, "bitcrush": bitcrush,
    "delay": delay, "reverb": reverb, "chorus": chorus, "phaser": phaser,
    "width": width, "eq3": eq3,
    "comp": comp, "limiter": limiter, "gate": gate,
})

# ---------------------------------------------------------------------- check


def _rms(v):
    return float(np.sqrt(np.mean(np.square(v))))


def demo():
    """One runnable check. asserts only - no framework. Run: python -m thud.fx"""
    n = 8192
    t = np.arange(n) / SR
    mono = np.sin(TAU * 220 * t) * np.exp(-t / 0.05) * 0.7
    st = np.stack([mono, np.roll(mono, 37) * 0.8], 1)

    # -- the contract, for every effect, in both shapes -------------------
    for name, f in sorted(FX.items()):
        for x in (mono, st):
            keep = x.copy()
            y = f(x)
            assert y.shape == x.shape, "%s: %s -> %s" % (name, x.shape, y.shape)
            assert np.array_equal(x, keep), name + " mutated its input"
            assert np.isfinite(y).all(), name + " made NaN/inf"
            assert np.abs(y).max() <= 1.0 + 1e-9, "%s peak %.3f" % (name, np.abs(y).max())
            assert np.array_equal(y, f(x)), name + " is not deterministic"
    assert delay(st, pingpong=True).shape == st.shape
    assert np.array_equal(delay(mono, pingpong=True), delay(mono)), "pingpong mono differs"

    # -- limiter never breaks the ceiling ---------------------------------
    pk = float(np.abs(limiter(st * 10.0, ceiling=0.9)).max())
    assert pk <= 0.9 + 1e-12, pk

    # -- width: 0 collapses, 1.5 spreads ----------------------------------
    d0 = float(np.abs(st[:, 0] - st[:, 1]).mean())
    w0 = width(st, 0.0)
    assert np.array_equal(w0[:, 0], w0[:, 1]), "width(x,0) is not mono"
    w2 = width(st, 1.5)
    d2 = float(np.abs(w2[:, 0] - w2[:, 1]).mean())
    assert d2 > d0, (d0, d2)

    # -- eq3 kills --------------------------------------------------------
    m = SR                                        # 1s: 50Hz and 10k are exact bins
    tt = np.arange(m) / SR
    lo = np.sin(TAU * 50 * tt) * 0.5
    hi = np.sin(TAU * 10000 * tt) * 0.5
    lo_db = 20 * np.log10(_rms(eq3(lo, low=0.0)) / _rms(lo))
    hi_db = 20 * np.log10(_rms(eq3(hi, high=0.0)) / _rms(hi))
    assert lo_db < -20.0, lo_db
    assert hi_db < -20.0, hi_db
    assert np.allclose(eq3(st, 1.0, 1.0, 1.0), st), "unity eq3 is not flat"

    # -- phaser: the OLA reconstructs, and the cascade really notches ------
    assert np.abs(phaser(mono, stages=0, mix=1.0) - mono).max() < 1e-9, "phaser OLA leaks"
    imp = np.zeros(8192)
    imp[1024] = 0.5                                        # flat spectrum = |H|
    h = np.abs(np.fft.rfft(phaser(imp, rate=0.0))) / 0.5
    fz = np.fft.rfftfreq(8192, 1.0 / SR)
    notch = 20 * np.log10(h[(fz > 100) & (fz < 6000)].min())
    assert notch < -20.0, notch

    # -- delay and reverb decay -------------------------------------------
    m = SR * 2
    burst = np.zeros(m)
    burst[:2000] = np.sin(TAU * 300 * np.arange(2000) / SR) * 0.8
    tails = {}
    for name, y in (("delay", delay(burst, feedback=0.5, mix=0.5)),
                    ("reverb", reverb(burst, mix=0.6))):
        tail = y[m // 10:]                                 # skip past the dry burst
        k = len(tail) // 10
        assert _rms(tail[:k]) > _rms(tail[-k:]) * 2.0, name + " does not decay"
        tails[name] = 20 * np.log10((_rms(tail[-k:]) + 1e-12) / (_rms(tail[:k]) + 1e-12))

    print("fx: %d effects pass  ·  eq3 kill low %.0fdB / high %.0fdB"
          "  ·  limiter peak %.3f  ·  phaser notch %.0fdB"
          "  ·  delay tail %.0fdB  ·  reverb tail %.0fdB  ·  width %.3f -> %.3f"
          % (len(FX), lo_db, hi_db, pk, notch, tails["delay"], tails["reverb"], d0, d2))


if __name__ == "__main__":
    demo()
