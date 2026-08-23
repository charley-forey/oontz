"""Waveforms you can see a whole track in.

Height comes from RMS and colour from spectral content, which is how DJ software
makes a drop visible at a glance. Peak-per-column alone pins dance music to full
and the arrangement disappears.

analyse() does the expensive part once per load; the drawing functions take the
result, so a 30fps page never re-runs an FFT.
"""
import numpy as np

from .contracts import SR
from .term import fit, DIM, OFF, INV, BRAILLE
from . import theme as T

# dot -> bit for a braille cell, 2 wide by 4 tall
DOTS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]


def analyse(samples, columns):
    """(rms, peak, tilt) per column. tilt is -1 bass-heavy .. +1 treble-heavy."""
    if samples is None or len(samples) < 2 or columns < 1:
        z = np.zeros(max(1, columns))
        return z, z.copy(), z.copy()
    mono = samples[:, 0] if getattr(samples, "ndim", 1) == 2 else samples
    mono = np.asarray(mono, dtype=np.float64)
    n = len(mono)
    edges = np.linspace(0, n, columns + 1).astype(int)
    rms = np.zeros(columns)
    peak = np.zeros(columns)
    tilt = np.zeros(columns)
    for i in range(columns):
        seg = mono[edges[i]:max(edges[i] + 1, edges[i + 1])]
        if not len(seg):
            continue
        rms[i] = float(np.sqrt(np.mean(seg ** 2)))
        peak[i] = float(np.abs(seg).max())
        m = min(len(seg), 2048)
        if m >= 64:                                  # cheap two-band tilt
            sp = np.abs(np.fft.rfft(seg[:m] * np.hanning(m)))
            f = np.fft.rfftfreq(m, 1.0 / SR)
            lo = sp[f < 300].sum()
            hi = sp[f > 3000].sum()
            tot = lo + hi + 1e-12
            tilt[i] = (hi - lo) / tot
    return rms, peak, tilt


def _kind(tilt_v, peak_v):
    if peak_v > 0.9:
        return "danger"
    if tilt_v < -0.35:
        return "danger"                              # bass-heavy reads warm
    if tilt_v > 0.35:
        return "accent"                              # treble reads cold
    return "warn"


def overview(samples, w, h=3, pos=0.0, marks=(), cues=(), cache=None):
    """The whole track in one strip. `cache` is an analyse() result to reuse."""
    if w < 4 or h < 1:
        return [""] * max(0, h)
    if samples is None or len(samples) < 2:
        return [fit(T.c("muted", "-" * w), w) for _ in range(h)]
    rms, peak, tilt = cache if cache is not None else analyse(samples, w)
    mx = rms.max() or 1.0
    n = len(samples)
    head = int(max(0.0, min(1.0, pos)) * (w - 1))
    mark_at = {}
    for m in marks or ():
        try:
            mark_at[int(m[0] / float(n) * (w - 1))] = str(m[1])
        except Exception:
            pass
    cue_at = {int(c / float(n) * (w - 1)) for c in (cues or ()) if c is not None}
    rows = []
    for r in range(h):
        line = []
        need = (h - r) / float(h)
        for i in range(w):
            lvl = rms[i] / mx
            if lvl >= need:
                ch = T.c(_kind(tilt[i], peak[i]), "█")
            elif lvl >= need - 0.5 / h:
                ch = T.c(_kind(tilt[i], peak[i]), "▄")
            elif i in cue_at:
                ch = T.c("ok", "▏")
            elif i in mark_at and r == h - 1:
                ch = T.c("accent2", "│")
            else:
                ch = DIM + "·" + OFF
            if i == head:
                ch = INV + ch + OFF
            line.append(ch)
        rows.append("".join(line))
    return [fit(r, w) for r in rows]


def detail(samples, w, h, pos_samples, grid=(), zoom_beats=8, bpm=132.0):
    """The zoomed view around the playhead, with the beat grid drawn exactly."""
    if w < 8 or h < 1 or samples is None or len(samples) < 2:
        return [fit(T.c("muted", "-" * max(0, w)), w) for _ in range(max(0, h))]
    span = int(SR * 60.0 / max(1.0, bpm) * zoom_beats)
    a = int(max(0, pos_samples - span // 2))
    b = int(min(len(samples), a + span))
    seg = samples[a:b]
    rms, peak, tilt = analyse(seg, w)
    mx = rms.max() or 1.0
    gcols = set()
    downs = set()
    for i, g in enumerate(grid or ()):
        if a <= g < b:
            col = int((g - a) / float(max(1, b - a)) * (w - 1))
            gcols.add(col)
            if i % 4 == 0:
                downs.add(col)
    mid = w // 2
    rows = []
    for r in range(h):
        need = (h - r) / float(h)
        line = []
        for i in range(w):
            lvl = rms[i] / mx
            if i == mid:
                line.append(T.c("text_bright", "┃"))
            elif lvl >= need:
                line.append(T.c(_kind(tilt[i], peak[i]), "█"))
            elif i in downs:
                line.append(T.c("accent2", "┃"))
            elif i in gcols:
                line.append(DIM + "│" + OFF)
            else:
                line.append(DIM + " " + OFF)
        rows.append("".join(line))
    return [fit(r, w) for r in rows]


def align(grid_a, pos_a, grid_b, pos_b, w, bpm_a=132.0, bpm_b=132.0):
    """How the two decks' beats line up right now. Aligned must LOOK aligned."""
    if w < 12:
        return [fit("", w)] * 2
    def phase(grid, pos, bpm):
        if not grid:
            return 0.0
        i = int(np.searchsorted(np.asarray(grid), pos, side="right") - 1)
        i = max(0, min(len(grid) - 1, i))
        s = grid[i]
        e = grid[i + 1] if i + 1 < len(grid) else s + SR * 60.0 / max(1.0, bpm)
        return 0.0 if e <= s else max(0.0, min(1.0, (pos - s) / float(e - s)))
    pa, pb = phase(grid_a, pos_a, bpm_a), phase(grid_b, pos_b, bpm_b)
    inner = w - 4
    def strip(p, kind):
        i = int(p * (inner - 1))
        return "".join(T.c(kind, "█") if k == i else (DIM + "·" + OFF)
                       for k in range(inner))
    return [fit("  " + T.c("accent", "A") + " " + strip(pa, "accent"), w),
            fit("  " + T.c("accent2", "B") + " " + strip(pb, "accent2"), w)]


def minimap(energy_curve, w, pos_frac=0.0):
    """The arrangement as a shape: from Song.energy_curve()."""
    if not energy_curve or w < 4:
        return fit("", w)
    total = sum(max(1, b) for _n, _e, b in energy_curve) or 1
    cells, acc = [], 0
    for name, energy, bars in energy_curve:
        span = max(1, int(round(bars / float(total) * w)))
        glyph = "█" if energy > 0.8 else ("▓" if energy > 0.5 else "▒")
        kind = "danger" if energy > 0.8 else ("warn" if energy > 0.5 else "muted")
        cells += [T.c(kind, glyph)] * span
        acc += span
    cells = cells[:w] + [DIM + "·" + OFF] * max(0, w - len(cells))
    head = int(max(0.0, min(1.0, pos_frac)) * (w - 1))
    if 0 <= head < len(cells):
        cells[head] = INV + cells[head] + OFF
    return fit("".join(cells), w)


def time_ruler(duration, w, pos=0.0):
    """A time axis with tick spacing that suits the length."""
    if w < 8 or duration <= 0:
        return fit("", w)
    for step in (15, 30, 60, 120, 300):
        if duration / step <= w / 8.0:
            break
    line = [" "] * w
    t = 0.0
    while t <= duration:
        col = int(t / duration * (w - 1))
        label = "%d:%02d" % (int(t) // 60, int(t) % 60)
        for j, c in enumerate(label):
            if col + j < w:
                line[col + j] = c
        t += step
    out = "".join(line)
    head = int(max(0.0, min(1.0, pos)) * (w - 1))
    return fit(T.c("text_dim", out[:head]) + T.c("accent", out[head:head + 1]) +
               T.c("text_dim", out[head + 1:]), w)


def braille(samples, w, h):
    """A braille trace, for the close-up scope. 2x4 dots per cell."""
    if w < 2 or h < 1 or samples is None or len(samples) < 2:
        return [fit("", w) for _ in range(max(0, h))]
    mono = samples[:, 0] if getattr(samples, "ndim", 1) == 2 else samples
    xs = np.linspace(0, len(mono) - 1, w * 2).astype(int)
    vals = np.asarray(mono)[xs]
    mx = max(1e-9, float(np.abs(vals).max()))
    ys = ((1.0 - vals / mx) * 0.5 * (h * 4 - 1)).astype(int)
    grid = [[0] * w for _ in range(h)]
    for i in range(len(xs)):
        cx, dx = divmod(i, 2)
        cy, dy = divmod(int(ys[i]), 4)
        if 0 <= cy < h and 0 <= cx < w:
            grid[cy][cx] |= DOTS[dy][dx]
    return [fit("".join(T.c("accent", chr(BRAILLE + b)) if b else " " for b in row), w)
            for row in grid]
