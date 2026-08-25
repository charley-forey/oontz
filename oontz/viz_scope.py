"""Scope, meters, and goniometer views. Pure f(Snapshot, w, h) -> list[str].

Three registrations: "scope" (braille oscilloscope), "meters" (mixer strip
with proper dB and peak-hold), "stereo" (Lissajous/correlation display).

Braille packs 2x4 dots per terminal cell, so a w x h view has 2w x 4h dots of
real resolution - far sharper than block glyphs. All three views share one
braille canvas (_set_dot / _render_canvas) so scope and stereo look and
behave identically.

Contract friction: peak-hold ("falls slowly") and the CLIP latch both need
memory across frames, but a view is `f(Snapshot, w, h) -> list[str]` with no
history field on Snapshot for it. There's no way to do a real decaying hold
from a single immutable snapshot, so _METER_STATE below is a small module-
level cache, scoped to this file only, no I/O, nothing shared with core/ui.
That's a deliberate, contained exception to "no global state" - flagging it
rather than silently doing it. If that rule is meant to be absolute, the fix
is to drop decay and show an instantaneous peak instead.
"""
import math
import re
import numpy as np

from .contracts import Snapshot, TrackView, VIEWS
from .term import ANSI, COL, DIM, OFF, BLOCKS, BRAILLE, c, fit, vlen

# dot position (col 0-1, row 0-3) -> bit, per the braille cell layout
DOT_BIT = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08,
           (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80}

# ------------------------------------------------------------- shared canvas


def _set_dot(bits, amp, dx, dy, level, w, h):
    """Light one dot at (dx, dy) in dot-space (0..2w-1, 0..4h-1)."""
    if dx < 0 or dx >= 2 * w or dy < 0 or dy >= 4 * h:
        return
    cx, cy, sx, sy = dx // 2, dy // 4, dx % 2, dy % 4
    bits[cy][cx] |= DOT_BIT[(sx, sy)]
    a = abs(level)
    if a > amp[cy][cx]:
        amp[cy][cx] = a


def _amp_db(a):
    return 20.0 * math.log10(a) if a > 1e-6 else -120.0


def _level_color(db):
    """Same thresholds as ui.py's master bar: healthy / hot / clipping."""
    return 196 if db > -1 else (214 if db > -6 else 78)


def _render_canvas(bits, amp, w, h):
    lines = []
    for cy in range(h):
        row = []
        for cx in range(w):
            b = bits[cy][cx]
            if b:
                row.append(c(_level_color(_amp_db(amp[cy][cx])), chr(BRAILLE | b)))
            else:
                row.append(" ")
        lines.append(fit("".join(row), w))
    return lines

# ------------------------------------------------------------------- scope


def _to_array(scope):
    return np.asarray(scope, dtype=np.float64) if len(scope) else np.zeros(0)


def _mono_trace(scope):
    """scope is mono (n,) today; downmix if a (n,2) buffer ever lands."""
    arr = _to_array(scope)
    return arr.mean(axis=1) if arr.ndim == 2 else arr


def scope_view(s, w, h):
    w, h = max(1, w), max(1, h)
    trace = _mono_trace(s.scope)
    nx = 2 * w
    if trace.size == 0:
        y = np.zeros(nx)
    elif trace.size == 1:
        y = np.full(nx, trace[0])
    else:
        idx = np.linspace(0, trace.size - 1, nx)
        y = np.interp(idx, np.arange(trace.size), trace)
    y = np.clip(y, -1.0, 1.0)
    ny = 4 * h
    dot_y = np.round((1.0 - y) * 0.5 * (ny - 1)).astype(int)

    bits = [[0] * w for _ in range(h)]
    amp = [[0.0] * w for _ in range(h)]
    _set_dot(bits, amp, 0, int(dot_y[0]), y[0], w, h)
    for x in range(1, nx):
        lo, hi = sorted((int(dot_y[x - 1]), int(dot_y[x])))
        level = max(abs(y[x - 1]), abs(y[x]))
        for dy in range(lo, hi + 1):                  # vertical run = continuous trace
            _set_dot(bits, amp, x, dy, level, w, h)
    return _render_canvas(bits, amp, w, h)

# ------------------------------------------------------------------ meters

_METER_STATE = {"hold": {}, "clip_until": 0.0}         # see module docstring
_HOLD_FALL_DB_S = 20.0                                  # peak-hold fall rate


def _db(x):
    return 20.0 * math.log10(x) if x > 1e-3 else -60.0


def _frac_from_db(db, floor=-60.0):
    """A proper -60..0dB linear-in-dB scale, not the compressed one in ui.py."""
    return max(0.0, min(1.0, (db - floor) / -floor))


def _update_hold(key, db, now):
    lvl, t0 = _METER_STATE["hold"].get(key, (-60.0, now))
    decayed = lvl - (now - t0) * _HOLD_FALL_DB_S
    lvl = max(db, decayed)
    _METER_STATE["hold"][key] = (lvl, now)
    return lvl


def _update_clip(peak, now):
    if peak >= 1.0:
        _METER_STATE["clip_until"] = now + 1.0
    return now < _METER_STATE["clip_until"]


def _pan_widget(pan):
    n = 7
    pos = int(round((max(-1.0, min(1.0, pan)) + 1.0) / 2.0 * (n - 1)))
    cells = ["─"] * n                              # ─
    cells[pos] = "●"                                # ●
    return "L" + "".join(cells) + "R"


def _bar_with_hold(frac, hold_frac, barw, col):
    """Solid fill + one eighth-block for the fractional edge (BLOCKS), plus
    a bright peak-hold tick wherever the (slowly falling) hold level sits."""
    frac = max(0.0, min(1.0, frac))
    exact = frac * barw
    n = int(exact)
    sub = BLOCKS[int(round((exact - n) * 8))] if n < barw else ""
    hn = min(barw - 1, int(round(max(0.0, min(1.0, hold_frac)) * barw)))
    out = []
    for i in range(barw):
        if i == hn:
            out.append(c(255, "▏"))                 # ▏ peak-hold tick
        elif i < n:
            out.append(c(col, "█"))                 # █
        elif i == n and sub:
            out.append(c(col, sub))
        else:
            out.append(DIM + "░" + OFF)             # ░
    return "".join(out)


def _meter_row(t, w, now):
    col = COL.get(t.name, 250)
    db = _db(t.rms)
    hold_db = _update_hold(t.name, db, now)
    barw = max(6, w - 34)
    bar = _bar_with_hold(_frac_from_db(db), _frac_from_db(hold_db), barw, col if t.active else 240)
    tag = c(231 if t.active else 240, "%-5s" % t.name[:5])
    flags = (c(196, "M") if t.mute else " ") + (c(226, "S") if t.solo else " ")
    pan = c(244, _pan_widget(t.pan))
    dbtxt = c(_level_color(db), "%+5.1f dB" % db)
    return fit("  %s %s %s %s %s" % (tag, bar, dbtxt, pan, flags), w)


def _master_row(s, w, now):
    db = _db(s.peak)
    hold_db = _update_hold("__master__", db, now)
    barw = max(6, w - 30)
    bar = _bar_with_hold(_frac_from_db(db), _frac_from_db(hold_db), barw, _level_color(db))
    clip = c(196, "CLIP") if _update_clip(s.peak, now) else DIM + "    " + OFF
    dbtxt = c(_level_color(db), "%+5.1f dB" % db)
    return fit("  %s %s %s %s" % (c(255, "MASTER"), bar, dbtxt, clip), w)


def meters_view(s, w, h):
    import time
    w, h = max(1, w), max(1, h)
    now = time.time()
    rows = [_meter_row(t, w, now) for t in s.tracks] + [_master_row(s, w, now)]
    return rows[:h]

# ------------------------------------------------------------------ stereo


def _stereo_lr(s):
    """Prefer the real (n,2) scope_lr; fall back to mono scope (L=R, a
    degenerate vertical line) when scope_lr is absent - e.g. a snapshot
    built before playback ever fills the ring buffer."""
    lr = _to_array(s.scope_lr)
    if lr.ndim == 2 and lr.shape[1] == 2 and lr.shape[0]:
        return lr[:, 0], lr[:, 1], True
    mono = _mono_trace(s.scope)
    return mono, mono, False


def _correlation(L, R):
    if L.size == 0:
        return 1.0
    num = float(np.dot(L, R))
    den = float(np.sqrt(np.dot(L, L) * np.dot(R, R)))
    return 1.0 if den < 1e-9 else max(-1.0, min(1.0, num / den))


def stereo_view(s, w, h):
    w, h = max(1, w), max(1, h)
    show_corr = h >= 2
    ph = max(1, h - 1) if show_corr else h
    L, R, stereo_src = _stereo_lr(s)

    bits = [[0] * w for _ in range(ph)]
    amp = [[0.0] * w for _ in range(ph)]
    if L.size:
        cap = min(L.size, 3000)
        idx = np.linspace(0, L.size - 1, cap).astype(int)
        Ls, Rs = L[idx], R[idx]
        mid = np.clip((Ls + Rs) * 0.5, -1.0, 1.0)      # vertical axis: mono content
        side = np.clip((Ls - Rs) * 0.5, -1.0, 1.0)     # horizontal axis: stereo width
        dx = np.round((side + 1.0) * 0.5 * (2 * w - 1)).astype(int)
        dy = np.round((1.0 - mid) * 0.5 * (4 * ph - 1)).astype(int)
        lvl = np.maximum(np.abs(Ls), np.abs(Rs))
        for i in range(cap):
            _set_dot(bits, amp, int(dx[i]), int(dy[i]), float(lvl[i]), w, ph)

    lines = _render_canvas(bits, amp, w, ph)
    if show_corr:
        corr = _correlation(L, R)
        col = 78 if corr > 0.5 else (214 if corr > -0.5 else 196)
        label = "  " + c(51, "correlation") + " " + c(col, "%+.2f" % corr)
        if not stereo_src:                             # no scope_lr yet - say so, don't pretend
            label += DIM + "  (mono scope)" + OFF
        lines.append(fit(label, w))
    return lines[:h]


VIEWS.update({"scope": scope_view, "meters": meters_view, "stereo": stereo_view})

# --------------------------------------------------------------------- demo


def _dot_rows_used(lines):
    """Decode rendered braille back to the set of dot-rows lit, for tests."""
    rows = set()
    for cy, line in enumerate(lines):
        for ch in ANSI.sub("", line):
            bits = ord(ch) - BRAILLE
            if 0 < bits <= 0xFF:
                for (sx, sy), bit in DOT_BIT.items():
                    if bits & bit:
                        rows.add(cy * 4 + sy)
    return rows


def _dot_cols_used(lines):
    """Same decode as _dot_rows_used but for columns, to check trace width."""
    cols = set()
    for line in lines:
        for cx, ch in enumerate(ANSI.sub("", line)):
            bits = ord(ch) - BRAILLE
            if 0 < bits <= 0xFF:
                for (sx, sy), bit in DOT_BIT.items():
                    if bits & bit:
                        cols.add(cx * 2 + sx)
    return cols


def demo():
    n = 2000
    t = np.arange(n) / 44100.0
    sine = 0.9 * np.sin(2 * math.pi * 220 * t)
    snap = Snapshot(scope=tuple(sine.tolist()), peak=0.9, playing=True, bpm=132, step=0,
                     tracks=(TrackView(name="kick", pat="", rms=0.5, active=True),))

    # 1) a real sine must actually oscillate across the plot, not go flat/clipped
    w, h = 100, 20
    used = _dot_rows_used(scope_view(snap, w, h))
    assert len(used) >= 0.5 * 4 * h, "sine scope only lit %d/%d dot rows" % (len(used), 4 * h)

    # 2) silence -> a tight flat line at centre, no crash
    silent = Snapshot(scope=tuple([0.0] * 500), peak=0.0)
    used0 = _dot_rows_used(scope_view(silent, w, h))
    centre = (4 * h) // 2
    assert used0 and max(used0) - min(used0) <= 2 and abs(min(used0) - centre) <= 2, \
        "silent scope should be a flat centre line, got rows %r" % used0

    # 3) exact width, bounded height, for every size the page can be
    for W in (60, 80, 120, 200):
        for H in (4, 8, 16):
            for view in (scope_view, meters_view, stereo_view):
                out = view(snap, W, H)
                assert len(out) <= H, "%s: %d lines, want <=%d" % (view.__name__, len(out), H)
                for ln in out:
                    assert vlen(ln) == W, "%s: line is %d cols not %d: %r" % (
                        view.__name__, vlen(ln), W, ANSI.sub("", ln)[:40])

    # 4) dB readout: 0.5 amplitude should read ~-6dB (within 1dB)
    tv = TrackView(name="bass", pat="", rms=0.5, active=True)
    out4 = meters_view(Snapshot(tracks=(tv,), peak=0.5), 100, 8)
    m = re.search(r"([+-]\d+\.\d)\s*dB", ANSI.sub("", out4[0]))
    assert m, "no dB readout in meter row: %r" % out4[0]
    assert abs(float(m.group(1)) - (-6.0)) < 1.0, "0.5 amplitude read %s, want ~-6dB" % m.group(1)

    # 5) stereo_view must actually be wired to scope_lr, not silently mono:
    #    a genuinely mono signal reads +1.00 and draws a vertical line...
    mono_lines = stereo_view(snap, w, h)
    mono_cols = _dot_cols_used(mono_lines)
    mono_corr = _correlation(*_stereo_lr(snap)[:2])
    assert mono_cols and max(mono_cols) - min(mono_cols) <= 1, \
        "mono input should draw a vertical line, spread cols %r" % mono_cols
    assert abs(mono_corr - 1.0) < 0.01, "mono input should read +1.00, got %.2f" % mono_corr

    # ...a decorrelated stereo signal must NOT: it should spread horizontally
    # and read well below +1.00.
    Lc = 0.6 * np.sin(np.linspace(0, 90, 4096))
    Rc = np.roll(Lc, 40)
    stereo_snap = Snapshot(scope_lr=tuple(map(tuple, np.stack([Lc, Rc], axis=1))),
                            scope=tuple(((Lc + Rc) / 2).tolist()), peak=0.6)
    st_lines = stereo_view(stereo_snap, w, h)
    st_cols = _dot_cols_used(st_lines)
    st_corr = _correlation(*_stereo_lr(stereo_snap)[:2])
    assert max(st_cols) - min(st_cols) > w // 4, \
        "decorrelated stereo should spread across the goniometer, spread cols %r" % st_cols
    assert st_corr < 0.9, "decorrelated stereo should read well below +1.00, got %.2f" % st_corr
    print("\nmono correlation: %+.2f   decorrelated correlation: %+.2f" % (mono_corr, st_corr))

    print("\n-- scope --")
    for l in scope_view(snap, 100, 16):
        print(l)

    print("\n-- meters --")
    demo_tracks = (
        TrackView(name="kick", pat="", rms=0.62, active=True),
        TrackView(name="hat", pat="", rms=0.15, active=True, pan=0.6),
        TrackView(name="bass", pat="", rms=0.35, active=True, mute=True),
        TrackView(name="clap", pat="", rms=0.05, active=False, solo=True),
    )
    for l in meters_view(Snapshot(tracks=demo_tracks, peak=0.97), 100, 8):
        print(l)

    print("\n-- stereo (mono fallback) --")
    for l in stereo_view(snap, 60, 16):
        print(l)

    print("\n-- stereo (real scope_lr, decorrelated) --")
    for l in stereo_view(stereo_snap, 60, 16):
        print(l)

    print("\nviz_scope: all checks pass")


if __name__ == "__main__":
    demo()
