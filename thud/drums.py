"""Hard-techno drum bank. Same contract as voices.py: pure, seeded, cacheable.

The 909 bank in voices.py is the clean one. This is the warehouse one - longer
kicks, more saturation, and the rumble tail that glues one beat to the next.
"""
import functools
import numpy as np

from .contracts import SR, TAU, VOICES
from .voices import svf, env, noise


@functools.lru_cache(maxsize=512)
def v_kick_hard(accent=False, tune=48.0, decay=0.62):
    """909 pushed: 180->48Hz in ~20ms, long body, tanh into the rails."""
    n = int(SR * decay)
    t = np.arange(n) / SR
    f = tune + tune * 2.75 * np.exp(-t / 0.02)             # 180 -> 48Hz
    x = np.sin(TAU * np.cumsum(f) / SR) * env(n, decay / 3.0)
    x += noise(n, ("kickhard", tune)) * np.exp(-t / 0.0015) * 0.22  # beater click
    drive = 5.0 if accent else 3.6
    return np.tanh(x * drive) / np.tanh(drive) * 0.95


@functools.lru_cache(maxsize=512)
def v_kick_dist(accent=False, tune=48.0, decay=0.62, fold=1.7):
    """Wavefold then hard-clip. Folding adds odd harmonics without the mud a
    higher tanh drive would leave in the 100-300Hz band."""
    x = v_kick_hard(accent, tune, decay)
    y = np.sin(TAU * 0.25 * np.clip(x * fold, -2.0, 2.0))  # fold, not just clip
    y = svf(y, 3000.0, 0.3, "lp")                          # tame the fizz the fold made
    return np.clip(y * (1.35 if accent else 1.1), -0.8, 0.8)


@functools.lru_cache(maxsize=256)
def v_rumble(accent=False, tune=44.0, decay=1.25):
    """The signature: kick into a short diffuse feedback tail, pitched down.

    Three short taps (prime-ish so they never line up into a pitched comb),
    lowpassed each pass so the tail loses air as it smears into the next beat.
    """
    n = int(SR * decay)
    x = np.zeros(n)
    k = v_kick_hard(accent, tune, 0.5)
    x[:len(k)] = k
    tail = x.copy()
    for _ in range(5):
        nxt = np.zeros(n)
        for ms, g in ((0.037, 0.50), (0.053, 0.31), (0.071, 0.20)):
            d = int(SR * ms)
            nxt[d:] += tail[:n - d] * g
        tail = svf(nxt, 170.0, 0.4, "lp")
        x += tail
    i = np.arange(n) * 0.8                                 # replay slow = pitched down
    x = np.interp(i, np.arange(n), x)
    return np.tanh(x * 1.4) * (0.95 if accent else 0.85)


@functools.lru_cache(maxsize=512)
def v_rim(accent=False, hz=1700.0):
    n = int(SR * 0.02)
    t = np.arange(n) / SR
    x = np.sin(TAU * hz * t) * env(n, 0.0035)
    x += noise(n, ("rim", hz)) * env(n, 0.0012) * 0.6      # the stick, not the shell
    return svf(x, hz, 0.8, "bp") * (0.38 if accent else 0.26)   # bp res adds ~7dB


@functools.lru_cache(maxsize=256)
def v_ride(accent=False, decay=1.2, tune=1150.0):
    n = int(SR * decay)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for j, r in enumerate((1.0, 1.62, 2.41, 3.17, 4.32, 5.71)):  # inharmonic = metal
        x += np.sin(TAU * tune * r * t) * env(n, decay / (2.2 + j * 0.4)) / (1 + j)
    x += noise(n, "ride") * env(n, decay / 6.0) * 0.35     # the strike, not the bell
    x = svf(svf(x, 2600.0, 0.4, "hp"), 12000.0, 0.3, "lp")
    return x * (0.55 if accent else 0.4)


@functools.lru_cache(maxsize=256)
def v_crash(accent=False, decay=2.0):
    """Stereo: the two sides get decorrelated noise, which is what makes a crash
    feel wide instead of like a mono hiss in the middle."""
    n = int(SR * decay)
    t = np.arange(n) / SR
    body = np.zeros(n)
    for j, r in enumerate((1.0, 1.47, 2.09, 2.83, 3.91, 5.13, 6.77)):
        body += np.sin(TAU * 620 * r * t) * env(n, decay / (3.0 + j * 0.5)) / (2 + j)
    out = np.empty((n, 2))
    for ch, key in enumerate(("crashL", "crashR")):
        h = svf(noise(n, key), 4000.0, 0.3, "hp") * env(n, decay / 2.6)
        out[:, ch] = svf(h + body * 0.55, 14000.0, 0.3, "lp")
    return np.tanh(out * 1.2) * (0.7 if accent else 0.52)


@functools.lru_cache(maxsize=512)
def v_tom(accent=False, tune=160.0, decay=0.35):
    n = int(SR * decay)
    t = np.arange(n) / SR
    f = tune * (1.0 + 0.75 * np.exp(-t / 0.05))            # drop of a fifth-ish
    x = np.sin(TAU * np.cumsum(f) / SR) * env(n, decay / 2.5)
    x += noise(n, ("tom", tune)) * np.exp(-t / 0.002) * 0.12
    return np.tanh(x * (2.2 if accent else 1.5)) * 0.8


@functools.lru_cache(maxsize=512)
def v_metal(accent=False, tune=210.0, decay=0.45, ratio=1.734):
    """FM with a non-integer ratio - integer ratios sound like a bell, this
    sounds like something falling over in a factory."""
    n = int(SR * decay)
    t = np.arange(n) / SR
    idx = (11.0 if accent else 7.0) * env(n, decay / 5.0)  # index env = the clang
    x = np.sin(TAU * tune * t + idx * np.sin(TAU * tune * ratio * t))
    x *= env(n, decay / 3.0)
    x = svf(x, 900.0, 0.5, "hp")
    return np.tanh(x * 1.6) * (0.7 if accent else 0.52)


@functools.lru_cache(maxsize=512)
def v_noise_hit(accent=False, cutoff=2000.0, decay=0.07, res=0.85):
    n = int(SR * decay)
    x = svf(noise(n, ("nhit", cutoff)), cutoff, res, "bp") * env(n, decay / 3.0)
    return np.tanh(x * (3.2 if accent else 2.2)) * 0.7


@functools.lru_cache(maxsize=64)
def v_riser(accent=False, dur=4.0, lo=250.0, hi=11000.0):
    """Bandpass sweeping up with a rising amplitude ramp - the ramp is what makes
    it read as tension rather than as a filter demo.

    ponytail: svf's per-sample loop means a 4s sweep costs ~1s to render once.
    lru_cache eats that on the first bar; vectorize only if a live build stalls.
    """
    n = int(SR * dur)
    fc = np.geomspace(lo, hi, n)
    x = svf(noise(n, ("riser", dur)), fc, 0.9, "bp")
    x *= np.linspace(0.05, 1.0, n) ** 2                    # squared: stays out of the way
    return np.tanh(x * (2.6 if accent else 1.9)) * 0.65


@functools.lru_cache(maxsize=64)
def v_downlifter(accent=False, dur=2.0, hi=9000.0, lo=120.0):
    n = int(SR * dur)
    fc = np.geomspace(hi, lo, n)
    x = svf(noise(n, ("down", dur)), fc, 0.9, "bp")
    x *= np.linspace(1.0, 0.02, n) ** 1.5                  # fall away into the drop
    return np.tanh(x * (3.0 if accent else 2.2)) * 0.65


VOICES.update({
    "kick_hard": v_kick_hard, "kick_dist": v_kick_dist, "rumble": v_rumble,
    "rim": v_rim, "ride": v_ride, "crash": v_crash, "tom": v_tom,
    "metal": v_metal, "noise_hit": v_noise_hit, "riser": v_riser,
    "downlifter": v_downlifter,
})


def demo():
    """asserts only - the levels get eyeballed, the physics gets checked."""
    def mono(x):
        return x.mean(axis=1) if x.ndim == 2 else x

    def peak_hz(x):
        x = mono(x)
        m = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        return np.fft.rfftfreq(len(x), 1 / SR)[int(np.argmax(m))]

    def centroid(x):
        m = np.abs(np.fft.rfft(mono(x)))
        return float((m * np.fft.rfftfreq(len(m) * 2 - 2, 1 / SR)).sum() / m.sum())

    calls = [("kick_hard", (), {}), ("kick_dist", (), {}), ("rumble", (), {}),
             ("rim", (), {}), ("ride", (), {}), ("crash", (), {}),
             ("tom", (), {"tune": 90.0}), ("tom", (), {"tune": 380.0}),
             ("metal", (), {}), ("noise_hit", (), {}), ("riser", (), {"dur": 4.0}),
             ("downlifter", (), {"dur": 2.0})]
    for name, a, kw in calls:
        f = VOICES[name]
        x = f(*a, **kw)
        pk, rms = float(np.max(np.abs(x))), float(np.sqrt(np.mean(mono(x) ** 2)))
        assert pk <= 1.0, "%s peaks at %.3f" % (name, pk)
        f.cache_clear()
        assert np.array_equal(x, f(*a, **kw)), "%s is not deterministic" % name
        print("  %-11s %6.2fs  peak %.3f  rms %.3f  centroid %6.0fHz"
              % (name, len(x) / SR, pk, rms, centroid(x)))

    for name in ("kick_hard", "kick_dist"):
        hz = peak_hz(VOICES[name]())
        assert 40 <= hz <= 90, "%s fundamental %.1fHz, want 40-90" % (name, hz)

    r = mono(v_rumble())
    m = np.abs(np.fft.rfft(r)) ** 2
    lowfrac = m[np.fft.rfftfreq(len(r), 1 / SR) < 200].sum() / m.sum()
    assert lowfrac > 0.6, "rumble only %.0f%% below 200Hz" % (lowfrac * 100)
    live = np.flatnonzero(np.abs(r) > 0.01 * np.max(np.abs(r)))[-1] / SR
    assert live > 0.8, "rumble dies at %.2fs, want >0.8" % live

    for name in ("ride", "crash"):
        cen = centroid(VOICES[name]())
        assert cen > 3000, "%s centroid %.0fHz, want >3k" % (name, cen)

    return "drums ok: %d voices, rumble %.0f%% sub-200Hz for %.2fs" % (
        len(calls), lowfrac * 100, live)


if __name__ == "__main__":
    print(demo())
