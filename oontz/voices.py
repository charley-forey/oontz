"""Voice bank - every voice is a pure, seeded, cacheable function.

CONTRACT (contracts.py): f(**hashable) -> np.ndarray, peak <= 1.0, deterministic
under SEED. No I/O, no global state, no randomness that isn't seeded.

Agents A1 (drums) and A2 (synths) extend this by adding entries to VOICES.
"""
import zlib
import functools
import numpy as np

from .contracts import SR, SEED, TAU, VOICES

# ---------------------------------------------------------------- primitives

def note_hz(name):
    """'a1' -> 55.0, 'f#2' -> 92.5. Scientific pitch, A4 = 440."""
    name = name.strip().lower()
    step = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}[name[0]]
    i = 1
    while i < len(name) and name[i] in "#b":
        step += 1 if name[i] == "#" else -1
        i += 1
    midi = (int(name[i:]) + 1) * 12 + step
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def rng(key):
    """Seeded generator. crc32 not hash() - hash() is salted per process."""
    return np.random.default_rng((SEED, zlib.crc32(repr(key).encode())))


def noise(n, key):
    """Deterministic white noise - same key, same samples, every run."""
    return rng(key).standard_normal(n)


def svf(x, fc, res=0.5, mode="lp"):
    """Trapezoidal (TPT) state-variable filter. fc is a scalar or per-sample array.

    TPT rather than the classic Chamberlin form because Chamberlin goes unstable
    above ~sr/6 and hats want an 8kHz highpass at 44.1k.

    ponytail: plain Python sample loop. Only ever runs over a single voice
    (<=0.5s) and the result is lru_cached, so it costs milliseconds once. If
    voices ever get long, vectorize or reach for scipy.signal.lfilter.
    """
    n = len(x)
    fc = np.clip(np.broadcast_to(np.asarray(fc, float), (n,)), 20.0, SR * 0.49)
    g = np.tan(np.pi * fc / SR)
    k = max(0.05, 2.0 - 2.0 * float(res))                   # damping; 0 = self-osc
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    s1 = s2 = 0.0
    out = np.empty(n)
    for i in range(n):
        v3 = x[i] - s2
        v1 = a1[i] * s1 + a2[i] * v3
        v2 = s2 + a2[i] * s1 + a3[i] * v3
        s1 = 2.0 * v1 - s1
        s2 = 2.0 * v2 - s2
        out[i] = v2 if mode == "lp" else (x[i] - k * v1 - v2 if mode == "hp" else v1)
    return out


def env(n, decay, shape=1.0):
    return np.exp(-np.arange(n) / SR / decay) ** shape


def saw(freq, n):
    """freq: scalar or per-sample array (for glides)."""
    f = np.broadcast_to(np.asarray(freq, float), (n,))
    return 2.0 * (np.cumsum(f) / SR % 1.0) - 1.0

# ------------------------------------------------------------------- voices
# Every voice is a pure function of its arguments -> float64 array at SR.
# lru_cache means a 16-step hat pattern synthesizes exactly one hat.


@functools.lru_cache(maxsize=512)
def v_kick(accent=False, tune=50.0, decay=0.42):
    n = int(SR * decay)
    t = np.arange(n) / SR
    f = tune + (tune * 2.4) * np.exp(-t / 0.013)          # 150 -> 50Hz in ~40ms
    x = np.sin(TAU * np.cumsum(f) / SR) * env(n, decay / 4.2)
    x += noise(n, "kick")[:n] * np.exp(-t / 0.0012) * 0.18  # click transient
    drive = 2.8 if accent else 2.0
    return np.tanh(x * drive) / np.tanh(drive) * 0.94      # saturation overshoots 1.0


@functools.lru_cache(maxsize=512)
def v_hat(accent=False, decay=0.03, fc=8000.0):
    n = int(SR * decay)
    x = svf(noise(n, ("hat", decay)), fc, 0.3, "hp")
    x = svf(x, fc, 0.3, "hp")                              # 2-pole, keeps it thin
    return x * env(n, decay / 3.5) * (0.55 if accent else 0.4)


@functools.lru_cache(maxsize=512)
def v_clap(accent=False):
    n = int(SR * 0.32)
    x = np.zeros(n)
    for k in range(3):                                     # 3 bursts, 10ms apart
        p = int(SR * 0.01 * k)
        b = noise(int(SR * 0.012), ("clap", k)) * env(int(SR * 0.012), 0.004)
        x[p:p + len(b)] += b
    x += noise(n, "clap-tail") * env(n, 0.055) * 0.5       # the room tail
    return svf(x, 1500.0, 0.72, "bp") * (0.9 if accent else 0.7)


@functools.lru_cache(maxsize=512)
def v_snare(accent=False):
    n = int(SR * 0.18)
    t = np.arange(n) / SR
    body = np.sin(TAU * 180 * t) * env(n, 0.03)
    snap = svf(noise(n, "snare"), 2200.0, 0.4, "hp") * env(n, 0.045)
    return (body * 0.5 + snap * 0.6) * (0.45 if accent else 0.34)


@functools.lru_cache(maxsize=512)
def v_perc(accent=False, tune=320.0):
    n = int(SR * 0.09)
    x = svf(noise(n, ("perc", tune)), tune, 0.9, "bp") * env(n, 0.02)
    return x * (1.8 if accent else 1.3)


@functools.lru_cache(maxsize=1024)
def v_bass303(hz, dur=0.2, accent=False, slide_from=0.0, cutoff=350.0, res=0.8):
    """Saw -> resonant lowpass with an envelope-swept cutoff. That's the 303."""
    n = max(64, int(SR * dur))
    t = np.arange(n) / SR
    f = np.full(n, hz)
    if slide_from:                                         # 60ms portamento
        g = min(n, int(SR * 0.06))
        f[:g] = np.geomspace(slide_from, hz, g)
    e = env(n, dur * 0.55)
    depth = 3.6 if accent else 1.9
    x = svf(saw(f, n), cutoff * (1.0 + depth * e), res, "lp")
    amp = env(n, dur * 0.7) * (1.0 if accent else 0.72)
    return np.tanh(x * amp * 1.6) * 0.5


@functools.lru_cache(maxsize=512)
def v_stab(hz, dur=0.4, accent=False, cutoff=2200.0, res=0.35):
    n = max(64, int(SR * dur))
    x = np.zeros(n)
    for semi in (0, 3, 7):                                 # minor triad
        f = hz * 2 ** (semi / 12.0)
        for det in (-0.006, 0.0, 0.006):                   # 3 detuned saws each
            x += saw(f * (1 + det), n)
    x = svf(x / 9.0, cutoff, res, "lp") * env(n, dur * 0.35)
    return x * (0.55 if accent else 0.4)


DRUMS = {"kick": v_kick, "hat": v_hat, "oh": v_hat, "clap": v_clap,
         "snare": v_snare, "perc": v_perc}
PITCHED = ("bass", "stab")


def voice(name, tr, accent, hz=0.0, dur=0.2, slide=0.0):
    """Render one hit, post-filtered by the track's filter if it has one."""
    if name == "bass":
        return v_bass303(hz, dur, accent, slide, tr["fc"] or 350.0, tr["res"])
    if name == "stab":
        return v_stab(hz, dur, accent, tr["fc"] or 2200.0, tr["res"])
    if name == "oh":
        x = v_hat(accent, 0.3, tr["tune"] or 8000.0)
    elif name == "hat":
        x = v_hat(accent, 0.03, tr["tune"] or 8000.0)
    elif name == "perc":
        x = v_perc(accent, tr["tune"] or 320.0)
    else:
        x = DRUMS[name](accent)
    if tr["filt"]:
        x = svf(x, tr["fc"], tr["res"], tr["filt"])
    return x

# Register into the shared registry from contracts.py. Adding a voice = adding an
# entry here; core.py never changes, so agents never collide.
VOICES.update({
    "kick": v_kick, "hat": v_hat, "oh": v_hat, "clap": v_clap,
    "snare": v_snare, "perc": v_perc, "bass": v_bass303, "stab": v_stab,
})
