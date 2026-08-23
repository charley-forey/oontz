"""Terminal primitives shared by every view. Agents import from here, not ui.

A view returns a list of strings, each EXACTLY w visible columns wide (colour
codes don't count). fit() is how you guarantee that.
"""
import re

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
OFF = "\x1b[0m"
DIM = "\x1b[38;5;240m"
INV = "\x1b[7m"
BOLD = "\x1b[1m"

# Per-track colours, so every view agrees on what "bass" looks like.
COL = {"kick": 203, "hat": 80, "oh": 80, "clap": 213, "snare": 215,
       "perc": 149, "bass": 39, "stab": 141}

# Frequency bands, low to high: (label, lo_hz, hi_hz, colour).
BANDS = [("sub", 20, 60, 196), ("bass", 60, 250, 203), ("low-mid", 250, 800, 215),
         ("mid", 800, 2500, 149), ("presence", 2500, 8000, 80), ("air", 8000, 20000, 141)]

BLOCKS = " ▁▂▃▄▅▆▇█"          # 0..8 eighths, for meters and spectra
BRAILLE = 0x2800               # + bitmask; 2x4 dots per cell


def c(n, s):
    """Colour s with 256-colour index n."""
    return "\x1b[38;5;%dm%s%s" % (n, s, OFF)


def vlen(s):
    """Visible width, ignoring colour codes."""
    return len(ANSI.sub("", s))


def fit(s, w):
    """Pad or truncate to exactly w visible columns."""
    n = vlen(s)
    return s + " " * (w - n) if n <= w else ANSI.sub("", s)[:w]


def bar(frac, w, col, track=None):
    """A horizontal meter, w cells wide, frac in 0..1."""
    frac = 0.0 if frac != frac else max(0.0, min(1.0, frac))
    n = int(frac * w)
    return c(col, "█" * n) + DIM + "░" * (w - n) + OFF


def band_of(hz):
    for name, lo, hi, col in BANDS:
        if lo <= hz < hi:
            return name, col
    return "air", 141
