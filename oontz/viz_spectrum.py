"""spectrum & freq views. Pure f(Snapshot, w, h) -> list[str], per contracts.py.

spectrum : a live analyser - Hann-windowed rFFT of the scope, grouped into
           log-spaced bins, drawn as dB-scale vertical bars.
freq     : the "why is my mix muddy" view - one row per active track, columns
           = term.BANDS, shaded by an approximate per-voice band profile,
           with same-band collisions between tracks highlighted in red.
"""
import numpy as np

from .contracts import SR
from . import term
from .term import fit, c, vlen, COL, BANDS, BLOCKS

# ------------------------------------------------------------- fft plumbing

FMIN, FMAX = 30.0, 16000.0
NBINS = 56                                       # ~48-64 log bins, per spec

_EDGES = np.geomspace(FMIN, FMAX, NBINS + 1)
_CENTERS = np.sqrt(_EDGES[:-1] * _EDGES[1:])     # geometric-mean centre freq per bin


def _band_levels_db(scope):
    """Hann-windowed rFFT of scope -> NBINS dB values (floor -60, ceiling 0).

    Pure: same scope in, same dB out, every time. Used by both spectrum_view
    and the self-test (test asserts against this directly, not the rendered
    ANSI, so the bin-mapping check isn't parsing colour codes).
    """
    x = np.asarray(scope, dtype=np.float64)
    if x.size == 0:
        x = np.zeros(4096)
    win = np.hanning(x.size)
    mag = np.abs(np.fft.rfft(x * win))
    norm = (win.sum() / 2.0) or 1.0              # coherent gain: full-scale sine -> mag ~= 1
    mag = mag / norm
    freqs = np.fft.rfftfreq(x.size, 1 / SR)
    levels = np.empty(NBINS)
    for i in range(NBINS):
        lo, hi = _EDGES[i], _EDGES[i + 1]
        idx = np.where((freqs >= lo) & (freqs < hi))[0]
        if idx.size == 0:                        # bin narrower than freq resolution (low end)
            idx = [int(np.argmin(np.abs(freqs - _CENTERS[i])))]
        levels[i] = mag[idx].max()
    return np.clip(20 * np.log10(np.maximum(levels, 1e-6)), -60.0, 0.0)


def _stretch(vals, w):
    """Resample an NBINS-length array to exactly w columns (nearest-neighbour)."""
    idx = (np.arange(w) * len(vals)) // w
    return vals[idx]


def _axis_row(col_hz, w):
    """Band labels positioned under the columns they actually cover."""
    chars = [" "] * w
    for name, lo, hi, col in BANDS:
        idx = [j for j in range(w) if lo <= col_hz[j] < hi]
        if len(idx) < 2:
            continue
        span = idx[-1] - idx[0] + 1
        label = name[:span]
        start = idx[0] + max(0, (span - len(label)) // 2)
        for k, ch in enumerate(label):
            if 0 <= start + k < w:
                chars[start + k] = ch
    return "".join(ch if ch == " " else c(term.band_of(col_hz[j])[1], ch)
                   for j, ch in enumerate(chars))

# ----------------------------------------------------------------- spectrum

# ponytail: the ONE deliberate impurity in this file. A decaying peak-hold
# cap needs to remember last frame's height; that can't be pure. Scope is
# kept tiny (one array, reset whenever the terminal width changes) and every
# other function/view here is a plain f(x) -> y.
_HOLD = {"w": 0, "eighths": None}


def spectrum_view(s, w, h):
    db = _band_levels_db(s.scope)                       # NBINS values, -60..0 dB
    frac = np.clip((db + 60.0) / 60.0, 0.0, 1.0)
    col_hz = _stretch(_CENTERS, w)
    col_frac = _stretch(frac, w)

    axis_rows = 1 if h > 1 else 0
    rows_n = max(1, h - axis_rows)
    total = rows_n * 8
    heights = np.round(col_frac * total).astype(int)

    if _HOLD["w"] != w or _HOLD["eighths"] is None or len(_HOLD["eighths"]) != w:
        _HOLD["eighths"], _HOLD["w"] = heights.astype(float), w
    else:
        _HOLD["eighths"] = np.maximum(heights.astype(float), _HOLD["eighths"] - 2)
    hold = np.clip(_HOLD["eighths"], 0, total).astype(int)

    lines = []
    for r in range(rows_n):
        base = (rows_n - 1 - r) * 8
        out = []
        for j in range(w):
            fill = min(8, max(0, heights[j] - base))
            hl = hold[j] - base
            if fill == 0 and 0 < hl <= 8:
                out.append(c(231, "-"))                  # peak-hold cap
            elif fill == 0:
                out.append(" ")
            else:
                out.append(c(term.band_of(col_hz[j])[1], BLOCKS[fill]))
        lines.append(fit("".join(out), w))
    if axis_rows:
        lines.append(fit(_axis_row(col_hz, w), w))
    return lines[:h]

# --------------------------------------------------------------------- freq

# Approximate per-voice band weight (0..1), across term.BANDS. This is a
# guess from how each voice is synthesised (drums.py/voices.py), NOT a
# measured per-track spectrum - Snapshot has no per-track audio to analyse.
# Replace with real per-track FFTs if/when that lands in the contract.
PROFILE = {
    "kick":  {"sub": .5, "bass": .9, "low-mid": .2},
    "hat":   {"mid": .1, "presence": .5, "air": .9},
    "oh":    {"low-mid": .1, "mid": .3, "presence": .6, "air": .7},
    "clap":  {"low-mid": .2, "mid": .5, "presence": .7, "air": .3},
    "snare": {"bass": .1, "low-mid": .4, "mid": .6, "presence": .4},
    "perc":  {"low-mid": .2, "mid": .5, "presence": .4},
    "bass":  {"sub": .4, "bass": .9, "low-mid": .3},
    "stab":  {"low-mid": .3, "mid": .7, "presence": .4, "air": .1},
}
_RMS_GAIN = 6.0                # rms rarely nears 1.0; scale so cells actually light up
_COLLIDE_AT = 0.35             # both tracks need at least this much energy to count as a clash

LEGEND_DESC = [
    "weight you feel", "kick body and bassline", "boxiness, where mixes turn to mud",
    "punch of mid elements", "clarity and attack, claps and snares live here",
    "air and shimmer, hats and cymbals",
]


def freq_view(s, w, h):
    active = [t for t in s.tracks if t.active]
    legend = "  " + " . ".join("%s %d-%d %s" % (b[0], b[1], b[2], d)
                                for b, d in zip(BANDS, LEGEND_DESC))
    legend_line = fit(c(240, legend), w)

    if not active:
        return [fit(c(240, "  no active tracks"), w), legend_line][:h]

    label_w = max(len(t.name) for t in active) + 1
    cell_w = max(3, (w - label_w) // len(BANDS))

    levels = {t.name: [min(1.0, PROFILE.get(t.name, {}).get(b[0], 0.0) * t.rms * _RMS_GAIN)
                        for b in BANDS] for t in active}
    collide = [sum(1 for t in active if levels[t.name][i] > _COLLIDE_AT) >= 2
               for i in range(len(BANDS))]

    lines = [fit("  " + c(244, "%-*s" % (label_w, "band"))
                  + "".join(c(b[3], "%-*s" % (cell_w, b[0])) for b in BANDS), w)]
    for t in active:
        cells = []
        for i, b in enumerate(BANDS):
            lvl = levels[t.name][i]
            red = collide[i] and lvl > _COLLIDE_AT
            glyph = BLOCKS[int(round(lvl * 8))] * cell_w
            cells.append(c(196 if red else b[3], glyph))
        row = "  " + c(COL.get(t.name, 250), "%-*s" % (label_w, t.name)) + "".join(cells)
        lines.append(fit(row, w))

    lines = lines[:max(0, h - 1)]
    lines.append(legend_line)
    return lines[:h]

# ------------------------------------------------------------------- demo

from .contracts import Snapshot, TrackView    # noqa: E402  (test-only imports, kept local to demo)


def demo():
    n = 4096
    t = np.arange(n) / SR
    lo_sine = np.sin(2 * np.pi * 50 * t)
    noise = np.random.default_rng(0).uniform(-1, 1, n)
    hi_sine = np.sin(2 * np.pi * 10000 * t)

    # -- bin mapping isn't inverted or off by a decade -------------------
    db_lo, db_noise, db_hi = (_band_levels_db(tuple(x)) for x in (lo_sine, noise, hi_sine))
    peak_lo_hz = _CENTERS[int(np.argmax(db_lo))]
    peak_hi_hz = _CENTERS[int(np.argmax(db_hi))]
    assert peak_lo_hz < 100, "50Hz sine peaked at %.0fHz - bin mapping is off" % peak_lo_hz
    assert peak_hi_hz > 5000, "10kHz sine peaked at %.0fHz - bin mapping is off" % peak_hi_hz
    assert (db_noise > -50).sum() > NBINS * 0.6, "white noise landed narrow, expected broadband"

    # -- exact width/height contract, every combo, active AND silent -----
    tracks = (
        TrackView(name="kick", pat="x...x...x...x...", rms=0.30, active=True),
        TrackView(name="hat", pat="..x...x...x...x.", rms=0.15, active=True),
        TrackView(name="bass", pat="x...x...x...x...", rms=0.25, active=True),
    )
    snap = Snapshot(tracks=tracks, scope=tuple(lo_sine), playing=True)
    empty = Snapshot()                            # all defaults: no tracks, no scope, silent

    for view in (spectrum_view, freq_view):
        for w in (60, 80, 120, 200):
            for h in (6, 10, 20):
                for sn in (snap, empty):
                    lines = view(sn, w, h)
                    assert len(lines) <= h, (view.__name__, w, h, len(lines))
                    for ln in lines:
                        assert vlen(ln) == w, (view.__name__, w, h, vlen(ln), ln)

    print(c(51, "-- spectrum --"))
    for ln in spectrum_view(snap, 100, 16):
        print(ln)
    print(c(51, "\n-- freq --"))
    for ln in freq_view(snap, 100, 10):
        print(ln)
    print(c(78, "\nviz_spectrum: all checks pass  ·  50Hz->%.0fHz  10kHz->%.0fHz  noise bins lit %d/%d"
            % (peak_lo_hz, peak_hi_hz, int((db_noise > -50).sum()), NBINS)))


if __name__ == "__main__":
    demo()

# ---------------------------------------------------------------- register
from .contracts import VIEWS                      # noqa: E402
VIEWS.update({"spectrum": spectrum_view, "freq": freq_view})
