"""Synth bank - hard techno, acid, industrial. Extends VOICES, edits nothing.

Same contract as voices.py: pure, hashable args only, seeded off SEED, peak
<= 1.0, lru_cached. Stereo (n, 2) only where the sound genuinely has an image
(detuned stacks, wide pads) - everything else stays mono and lets core widen it.

Loud voices end in tanh(...) * k rather than a measured gain: tanh is bounded,
so peak <= k holds for every hz/dur/detune the caller throws at it.
"""
import functools
import numpy as np

from .contracts import SR, TAU, VOICES
from .voices import svf, env, saw, noise, note_hz

# ------------------------------------------------------------------ helpers
# Not filters or oscillators - those come from voices.py. Just two shapes that
# every voice below wants and neither of which is worth repeating six times.


def _phase(freq, n):
    """Running phase in turns (0..1), for pulse/PWM oscillators."""
    return np.cumsum(np.broadcast_to(np.asarray(freq, float), (n,))) / SR


def _atk(n, secs):
    """Linear attack ramp. Slow attacks are the whole point of pad/atmos."""
    return np.clip(np.arange(n) / SR / max(secs, 1e-6), 0.0, 1.0)


# ------------------------------------------------------------------- voices


@functools.lru_cache(maxsize=1024)
def v_sub(hz, dur, accent=False, click=0.5):
    """Sine bass. The click is a 1ms noise spit so it cuts through on small
    speakers that can't reproduce 40Hz at all."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    x = np.sin(TAU * hz * t) * env(n, dur * 0.55)
    x += noise(n, "sub") * np.exp(-t / 0.001) * click * 0.5
    drive = 1.6 if accent else 1.2                          # a little weight, not fuzz
    return np.tanh(x * drive) * 0.82


@functools.lru_cache(maxsize=1024)
def v_reese(hz, dur, accent=False, detune=0.012, cutoff=900.0, res=0.45):
    """Three saws beating. The channels get opposite detune signs, so the
    beating drifts in and out of phase between them - that is the width."""
    n = max(64, int(SR * dur))
    sides = []
    for s in (-1.0, 1.0):
        x = saw(hz, n) * 0.6
        x += saw(hz * (1 + detune * s), n)
        x += saw(hz * (1 - detune * s * 1.7), n) * 0.9      # 1.7 keeps it non-periodic
        x += saw(hz * 0.5, n) * 0.5                         # sub octave, glues the low end
        sides.append(svf(x / 3.0, cutoff, res, "lp"))
    e = env(n, dur * 0.8) * _atk(n, 0.004)
    g = 2.4 if accent else 1.7
    return np.stack([np.tanh(s * e * g) * 0.62 for s in sides], axis=1)


@functools.lru_cache(maxsize=512)
def v_hoover(hz, dur, accent=False, cutoff=5200.0, res=0.7):
    """Dominator. Saw stack + PWM square, filter falling across the whole note.
    The sweep is exponential because the ear hears the fall as linear."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    sides = []
    for s in (-1.0, 1.0):
        x = np.zeros(n)
        for det in (-0.008, 0.0, 0.011):                    # detuned saw stack
            x += saw(hz * (1 + det * s), n)
        x += saw(hz * 2.0 * (1 + 0.004 * s), n) * 0.5       # octave up, the "brass"
        w = 0.5 + 0.36 * np.sin(TAU * 5.5 * t + (0.0 if s < 0 else 1.1))
        x += np.where(_phase(hz, n) % 1.0 < w, 1.0, -1.0) * 0.8   # PWM, 5.5Hz
        fc = cutoff * (0.06 + 0.94 * np.exp(-t / (dur * 0.45)))   # the sweep down
        sides.append(svf(x / 4.3, fc, res, "lp"))
    e = env(n, dur * 0.9) * _atk(n, 0.008)
    g = 3.2 if accent else 2.3
    return np.stack([np.tanh(s * e * g) * 0.6 for s in sides], axis=1)


@functools.lru_cache(maxsize=1024)
def v_pluck(hz, dur, accent=False, cutoff=2400.0, res=0.8):
    """Short, resonant, gone. Cutoff tracks the amp envelope so the tail dulls
    as it dies - a static filter here sounds like a gate, not a pluck."""
    n = max(64, int(SR * dur))
    e = env(n, dur * 0.22)
    x = saw(hz, n) * 0.7 + np.sin(TAU * hz * np.arange(n) / SR) * 0.5
    x = svf(x, cutoff * (0.12 + 0.88 * e), res, "lp")
    return np.tanh(x * e * (2.2 if accent else 1.5)) * 0.55


@functools.lru_cache(maxsize=1024)
def v_lead(hz, dur, accent=False, cutoff=2800.0, res=0.62):
    """Saw + square, resonant lowpass with a short upward blip. Bright enough to
    survive a mix that is already full of distorted kick."""
    n = max(64, int(SR * dur))
    ph = _phase(hz, n)
    x = saw(hz, n) + saw(hz * 1.004, n) * 0.7               # slight detune, not a chorus
    x += np.where(ph % 1.0 < 0.5, 1.0, -1.0) * 0.45
    e = env(n, dur * 0.6)
    x = svf(x / 2.2, cutoff * (0.5 + 1.5 * env(n, dur * 0.12)), res, "lp")
    return np.tanh(x * e * (2.6 if accent else 1.9)) * 0.58


@functools.lru_cache(maxsize=512)
def v_screech(hz, dur, accent=False, cutoff=900.0, res=0.99):
    """303 at max resonance into hard drive. res ~1 makes the svf ring at fc,
    so the audible pitch is the SWEEP, not hz - hz just feeds it something to
    ring off. Distortion after the filter, like the real pedal chain."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    fc = cutoff * (1.0 + (14.0 if accent else 8.0) * env(n, dur * 0.35))
    x = svf(saw(hz, n), fc, res, "lp")
    x = np.tanh(x * 9.0)                                    # square it off
    x = svf(x, np.clip(fc * 1.5, 20, 16000), 0.5, "lp")     # tame the worst of the fizz
    return np.tanh(x * env(n, dur * 0.5) * 3.0) * 0.5


@functools.lru_cache(maxsize=256)
def v_pad(hz, dur, accent=False, cutoff=750.0, res=0.25):
    """Stacked saws, slow in, heavily lowpassed. Width comes from giving each
    channel its own detune spread and its own slow drift - identical channels
    with a delay would just comb-filter in mono."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    sides = []
    for s, dets in ((-1.0, (-0.007, 0.003, 0.009)), (1.0, (-0.010, -0.002, 0.006))):
        x = np.zeros(n)
        for semi in (0, 7, 12):                             # root, fifth, octave
            f = hz * 2 ** (semi / 12.0)
            for d in dets:
                drift = 1 + 0.0015 * np.sin(TAU * (0.11 + 0.03 * s) * t)
                x += saw(f * (1 + d) * drift, n)
        sides.append(svf(x / 9.0, cutoff, res, "lp"))
    e = _atk(n, dur * 0.4) * env(n, dur * 1.2)
    g = 3.4 if accent else 2.6                          # lowpass at 750Hz eats most of it
    return np.stack([np.tanh(x * e * g) * 0.42 for x in sides], axis=1)


@functools.lru_cache(maxsize=128)
def v_atmos(hz, dur, accent=False, res=0.9):
    """Filtered noise that wanders. Two uncorrelated noise sources and two
    different sweep rates - uncorrelated noise IS the widest thing there is.

    ponytail: two svf passes over a long buffer, ~0.4s of CPU per second of
    audio (voices.py's svf is a Python loop). lru_cache pays it once, but a
    4s atmos will drop the first bar it appears in. Vectorize svf if that bites.
    """
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    sides = []
    for i, rate in enumerate((0.07, 0.053)):                # prime-ish, never re-syncs
        fc = hz * (1.6 + 1.3 * np.sin(TAU * rate * t + i * 2.0))
        x = svf(noise(n, ("atmos", i, hz)), np.clip(fc, 40, 12000), res, "bp")
        sides.append(x * (1 + 0.3 * np.sin(TAU * (rate * 1.7) * t)))   # slow tremolo
    e = _atk(n, dur * 0.45) * env(n, dur * 1.5)
    g = 2.0 if accent else 1.4                          # it is background; stay under everything
    return np.stack([np.tanh(x * e * g) * 0.4 for x in sides], axis=1)


@functools.lru_cache(maxsize=1024)
def v_fm(hz, dur, accent=False, ratio=2.0, index=6.0):
    """2-op FM. ratio 1-2 growls, 3.5 and 7 go metallic/bell. The index decays
    faster than the amp, which is what makes it a strike and not a drone."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    mod = np.sin(TAU * hz * ratio * t) * index * env(n, dur * 0.2)
    x = np.sin(TAU * hz * t + mod) * env(n, dur * 0.55)
    return np.tanh(x * (1.9 if accent else 1.3)) * 0.68


@functools.lru_cache(maxsize=1024)
def v_chord(hz, dur, accent=False, quality="min", cutoff=2200.0, res=0.35):
    """v_stab with a chord table. Unknown quality falls back to minor rather
    than raising - a typo in a pattern should not stop the transport."""
    semis = CHORDS.get(quality, CHORDS["min"])
    n = max(64, int(SR * dur))
    x = np.zeros(n)
    for semi in semis:
        f = hz * 2 ** (semi / 12.0)
        for det in (-0.006, 0.0, 0.006):
            x += saw(f * (1 + det), n)
    x = svf(x / (3.0 * len(semis)), cutoff, res, "lp") * env(n, dur * 0.35)
    return np.tanh(x * (2.4 if accent else 1.8)) * 0.5


CHORDS = {"min": (0, 3, 7), "maj": (0, 4, 7), "min7": (0, 3, 7, 10),
          "sus4": (0, 5, 7), "dim": (0, 3, 6)}

@functools.lru_cache(maxsize=1024)
def v_bell(hz, dur, accent=False, ratio=3.53, shimmer=7.0):
    """Inharmonic FM bell. 3.53 is the classic clangorous ratio; a whisper of a
    second partial at 7.0 gives it air. The index dies fast - strike, then ring."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    idx = (9.0 if accent else 6.0) * np.exp(-t / (dur * 0.12))
    mod = np.sin(TAU * hz * ratio * t) * idx + np.sin(TAU * hz * shimmer * t) * idx * 0.15
    x = np.sin(TAU * hz * t + mod) * np.exp(-t / (dur * 0.45))
    return np.tanh(x * 1.2) * 0.6


@functools.lru_cache(maxsize=1024)
def v_donk(hz, dur, accent=False):
    """The donk: a sine an octave up that falls home through a resonant bandpass.
    Bouncy, rude, unmistakable. Nobody ever used one tastefully; do not start."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    sweep = hz * 2 * (2.0 ** (-t / max(dur * 0.18, 1e-3)))    # octave drop, fast
    ph = np.cumsum(np.maximum(sweep, hz * 2)) / SR
    x = np.sin(TAU * ph) * env(n, dur * 0.3)
    x = svf(x, float(hz * 4), 0.9, "bp")
    return np.tanh(x * (3.2 if accent else 2.2)) * 0.7


@functools.lru_cache(maxsize=1024)
def v_wob(hz, dur, accent=False, rate=3.0, cutoff=1400.0):
    """A reese with an LFO on its filter - the wob. The rate is in Hz, not synced;
    at bar lengths it lands near 8ths anyway, and drift is character here."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    x = saw(hz, n) + saw(hz * 1.01, n) + saw(hz * 0.5, n) * 0.6
    lfo = 0.5 - 0.5 * np.cos(TAU * rate * t)                  # starts closed, opens
    lo, hi = 180.0, cutoff * (1.6 if accent else 1.0)
    out = np.empty(n)
    step = 512                                                 # ponytail: block-wise svf, per-sample cutoff not needed
    for i in range(0, n, step):
        j = min(n, i + step)
        fc = lo + (hi - lo) * float(lfo[(i + j) // 2])
        out[i:j] = svf(x[i:j], fc, 0.7, "lp")
    return np.tanh(out * 0.8 * env(n, dur * 0.8)) * 0.62


@functools.lru_cache(maxsize=1024)
def v_air(hz, dur, accent=False):
    """Air: noise breathing through a narrow band four octaves up, with a faint
    root sine so it still belongs to the key. A texture, not a note."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    x = svf(noise(n, "air"), float(min(hz * 8, 12000)), 0.95, "bp") * 2.2
    x += np.sin(TAU * hz * 2 * t) * 0.12
    return np.tanh(x * _atk(n, dur * 0.4) * env(n, dur * 0.9)) * (0.5 if accent else 0.38)


VOICES.update({
    "sub": v_sub, "reese": v_reese, "hoover": v_hoover, "pluck": v_pluck,
    "lead": v_lead, "screech": v_screech, "pad": v_pad, "atmos": v_atmos,
    "fm": v_fm, "chord": v_chord,
    "bell": v_bell, "donk": v_donk, "wob": v_wob, "air": v_air,
})


# --------------------------------------------------------------------- demo

ALL = (v_sub, v_reese, v_hoover, v_pluck, v_lead, v_screech, v_pad, v_atmos,
       v_fm, v_chord)


def demo():
    """asserts + a level table. Run: python -m thud.synths"""
    a1, a2, a3 = note_hz("a1"), note_hz("a2"), note_hz("a3")
    cases = [
        ("sub", lambda: v_sub(a1, 0.5)),
        ("sub/acc", lambda: v_sub(a1, 0.5, True)),
        ("reese", lambda: v_reese(a1, 0.9)),
        ("reese/wide", lambda: v_reese(a1, 0.9, True, 0.03)),
        ("hoover", lambda: v_hoover(a2, 0.7)),
        ("pluck", lambda: v_pluck(a3, 0.25)),
        ("lead", lambda: v_lead(a3, 0.3, True)),
        ("screech", lambda: v_screech(a2, 0.4, True)),
        ("pad", lambda: v_pad(a2, 1.5)),
        ("atmos", lambda: v_atmos(400.0, 1.5)),
        ("fm/bass", lambda: v_fm(a1, 0.4, ratio=1.5)),
        ("fm/bell", lambda: v_fm(note_hz("a4"), 0.6, ratio=3.5, index=9.0)),
    ] + [("chord/" + q, (lambda q=q: v_chord(a2, 0.6, quality=q))) for q in CHORDS]

    print("  voice          peak    rms  shape")
    for name, f in cases:
        x = f()
        assert np.isfinite(x).all(), "%s has NaN/inf" % name
        p = float(np.max(np.abs(x)))
        assert p <= 1.0, "%s peaks at %.3f" % (name, p)
        assert p > 0.01, "%s is silent" % name
        print("  %-12s  %5.3f  %5.3f  %s"
              % (name, p, float(np.sqrt((x ** 2).mean())),
                 "stereo" if x.ndim == 2 else "mono"))

    # determinism: clear the caches, render again, demand byte-identical output.
    # Comparing two cached calls would only prove lru_cache works.
    first = {name: f() for name, f in cases}
    for v in ALL:
        v.cache_clear()
    for name, f in cases:
        assert np.array_equal(first[name], f()), "%s is not deterministic" % name

    def peak_hz(x):
        m = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        return float(np.fft.rfftfreq(len(x), 1 / SR)[int(np.argmax(m))])

    # sub is a sine: its spectral peak must actually be the note
    for nm in ("a1", "c2", "e2"):
        want = note_hz(nm)
        got = peak_hz(v_sub(want, 1.0))
        assert abs(got - want) / want < 0.03, "sub %s: %.2fHz want %.2f" % (nm, got, want)

    # stereo voices need two genuinely different channels, not a duplicated mono
    for name, x in (("reese", v_reese(a1, 0.9)), ("pad", v_pad(a2, 1.5)),
                    ("hoover", v_hoover(a2, 0.7)), ("atmos", v_atmos(400.0, 1.5))):
        assert x.ndim == 2 and x.shape[1] == 2, "%s is not stereo" % name
        d = np.abs(x[:, 0] - x[:, 1]).mean() / (np.abs(x).mean() + 1e-12)
        assert d > 0.05, "%s channels near-identical (diff %.4f)" % (name, d)

    # every chord tone is actually in the spectrum
    for q, semis in CHORDS.items():
        x = v_chord(a2, 1.0, quality=q)
        m = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        fr = np.fft.rfftfreq(len(x), 1 / SR)
        med = np.median(m)
        for semi in semis:
            f = a2 * 2 ** (semi / 12.0)
            band = (fr > f * 0.97) & (fr < f * 1.03)
            assert m[band].max() > 20 * med,                 "chord %s has no partial at %.1fHz" % (q, f)

    print("synths: %d voices pass  ·  peaks <= 1.0  ·  deterministic  ·  spectra ok"
          % len(ALL))


if __name__ == "__main__":
    demo()
