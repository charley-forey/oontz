"""The visual system: one palette, one set of chrome, one set of widgets.

Every panel draws from here so the page reads as one designed product rather than
twelve programs sharing a terminal. Everything is pure and returns strings of an
exact visible width - the layout solver decides the size, panels never guess.
"""
from .term import ANSI, OFF, DIM, INV, COL, BLOCKS, fit, vlen
from .term import c as _c

SCHEMES = {
    # near-black ground, one cold accent, warm only where it means something
    "night": {"bg": 233, "surface": 235, "border": 238, "border_focus": 51,
              "text": 252, "text_dim": 243, "text_bright": 231, "accent": 51,
              "accent2": 213, "warn": 214, "danger": 196, "ok": 78, "muted": 240},
    # single-hue CRT. Distinctive on camera and kind to bad terminals.
    "amber": {"bg": 233, "surface": 234, "border": 94, "border_focus": 214,
              "text": 179, "text_dim": 136, "text_bright": 222, "accent": 214,
              "accent2": 208, "warn": 220, "danger": 196, "ok": 178, "muted": 94},
}
_S = {"name": "night", "ascii": False}

BOX = {
    "round":  "╭╮╰╯─│",
    "square": "┌┐└┘─│",
    "heavy":  "┏┓┗┛━┃",
    "double": "╔╗╚╝═║",
    "ascii":  "++++-|",
}


def set_scheme(name):
    if name in SCHEMES:
        _S["name"] = name
    return _S["name"]


def set_ascii(on=True):
    _S["ascii"] = bool(on)


def col(sem):
    """Semantic name -> 256-colour index. Track names resolve to their own colour."""
    if sem in COL:
        return COL[sem]
    return SCHEMES[_S["name"]].get(sem, 250)


def c(sem, text):
    """Colour by SEMANTIC name (or a raw 256 index). Panels never write raw codes."""
    return _c(sem if isinstance(sem, int) else col(sem), text)


paint = c


# ------------------------------------------------------------------ chrome

def _glyphs(style):
    return BOX["ascii" if _S["ascii"] else (style if style in BOX else "round")]


def box(title, w, h, focused=False, style="round", cat=None):
    """A bordered panel with its title set into the top edge."""
    if w < 4 or h < 2:
        return [" " * w for _ in range(max(0, h))]
    tl, tr, bl, br, hz, vt = _glyphs(style)
    bc = col("border_focus") if focused else col(cat or "border")
    t = (" %s " % title) if title else ""
    t = t[:max(0, w - 4)]
    top = tl + hz + t + hz * (w - 3 - len(t)) + tr
    lines = [c(bc, tl + hz) + c("text_bright" if focused else "text_dim", t) +
             c(bc, hz * (w - 3 - len(t)) + tr)]
    for _ in range(h - 2):
        lines.append(c(bc, vt) + " " * (w - 2) + c(bc, vt))
    if h > 1:
        lines.append(c(bc, bl + hz * (w - 2) + br))
    return lines


def frame(lines, title, w, h, focused=False, style="round", cat=None):
    """Wrap content INSIDE a box so a panel author only supplies content."""
    shell = box(title, w, h, focused, style, cat)
    if h < 3 or w < 4:
        return [fit(l, w) for l in (list(lines) + [""] * h)[:h]]
    tl, tr, bl, br, hz, vt = _glyphs(style)
    bc = col("border_focus") if focused else col(cat or "border")
    inner_w, inner_h = w - 4, h - 2
    out = [shell[0]]
    body = [fit(l, inner_w) for l in list(lines)[:inner_h]]
    body += [" " * inner_w] * (inner_h - len(body))
    for row in body:
        out.append(c(bc, vt) + " " + row + " " + c(bc, vt))
    out.append(shell[-1])
    return out


def hrule(w, label="", cat="border"):
    hz = "-" if _S["ascii"] else "─"
    if not label or w < len(label) + 6:
        return c(cat, hz * w)
    return c(cat, hz * 2) + " " + paint("text_dim", label) + " " + c(cat, hz * (w - 4 - len(label)))


def tab_bar(items, active, w):
    parts = []
    for it in items:
        parts.append((INV + c("accent", " %s " % it) + OFF) if it == active
                     else paint("text_dim", " %s " % it))
    return fit("".join(parts), w)


def badge(text, kind="accent"):
    return INV + c(kind, " %s " % text) + OFF


def led(on, kind="ok"):
    return c(kind if on else "muted", "●" if not _S["ascii"] else ("*" if on else "."))


# ----------------------------------------------------------------- widgets

def meter(value, w, kind="ok", peak=None):
    """Horizontal bar with an optional peak-hold tick."""
    if w <= 0:
        return ""
    v = 0.0 if value != value else max(0.0, min(1.0, value))
    n = int(v * w)
    cells = [c(kind, "█")] * n + [DIM + ("." if _S["ascii"] else "░") + OFF] * (w - n)
    if peak is not None and w:
        t = max(0, min(w - 1, int(max(0.0, min(1.0, peak)) * w)))
        cells[t] = c("text_bright", "▏" if not _S["ascii"] else "|")
    return "".join(cells)


def vmeter(value, h, kind="ok"):
    v = max(0.0, min(1.0, value or 0.0))
    lit = v * h
    out = []
    for row in range(h):
        rem = lit - (h - 1 - row)
        out.append(c(kind, BLOCKS[-1]) if rem >= 1 else
                   (c(kind, BLOCKS[max(0, int(rem * 8))]) if rem > 0 else DIM + " " + OFF))
    return out


def gauge(value, w, label="", lo=0.0, hi=1.0, bipolar=False):
    """A knob-like readout. Bipolar controls show a centre detent."""
    if w < 6:
        return fit(label[:w], w)
    span = max(1e-9, hi - lo)
    v = max(0.0, min(1.0, ((value if value == value else lo) - lo) / span))
    track_w = max(3, w - (len(label) + 1 if label else 0))
    pos = int(v * (track_w - 1))
    cells = []
    for i in range(track_w):
        if i == pos:
            cells.append(c("accent", "●"))
        elif bipolar and i == track_w // 2:
            cells.append(DIM + "┼" + OFF)
        else:
            cells.append(c("muted", "─" if not _S["ascii"] else "-"))
    g = "".join(cells)
    return fit((paint("text_dim", label) + " " + g) if label else g, w)


def crossfader(pos, w, label=""):
    """-1 .. +1 with a visible travel and a handle."""
    if w < 7:
        return fit("xf", w)
    track = w - 4
    p = max(-1.0, min(1.0, pos if pos == pos else 0.0))
    i = int((p + 1) / 2 * (track - 1))
    cells = []
    for k in range(track):
        if k == i:
            cells.append(c("text_bright", "█"))
        elif k == track // 2:
            cells.append(DIM + "┃" + OFF)
        else:
            cells.append(c("muted", "─"))
    return fit(paint("accent", "A ") + "".join(cells) + paint("accent2", " B"), w)


def pad(label, on=False, accent=False, active=False, w=4, h=2):
    """A drum pad. The step grid should look like hardware, not text."""
    if accent:
        fg, ch = "text_bright", "█"
    elif on:
        fg, ch = "accent", "▓"
    else:
        fg, ch = "muted", "·"
    body = ch * max(1, w - 2)
    top = (INV if active else "") + c(fg, " " + body + " ") + (OFF if active else "")
    rows = [top]
    if h > 1:
        rows.append(paint("text_dim", (" %s " % label)[:w].ljust(w)))
    while len(rows) < h:
        rows.append(" " * w)
    return [fit(r, w) for r in rows[:h]]


def sparkline(values, w, kind="accent"):
    if not values or w <= 0:
        return " " * max(0, w)
    out, mx = [], max(max(values), 1e-9)
    for i in range(w):                       # stretch, never clamp to the last value
        v = values[min(len(values) - 1, int(i * len(values) / float(w)))] / mx
        out.append(c(kind, BLOCKS[max(0, min(8, int(v * 8)))]))
    return "".join(out)


def progress(frac, w, label=""):
    if w < 4:
        return " " * w
    inner = w - (len(label) + 1 if label else 0)
    n = int(max(0.0, min(1.0, frac)) * inner)
    return fit((paint("text_dim", label) + " " if label else "") +
               c("ok", "█" * n) + DIM + "░" * (inner - n) + OFF, w)


def marquee(text, w, offset=0):
    if vlen(text) <= w:
        return fit(text, w)
    pad_ = "   "
    s = text + pad_
    o = offset % len(s)
    return fit((s + s)[o:o + w], w)


# -------------------------------------------------------------------- type

_DIGITS = {
    "0": ("███", "█ █", "███"), "1": ("  █", "  █", "  █"), "2": ("███", "███", "███"),
    "3": ("███", " ██", "███"), "4": ("█ █", "███", "  █"), "5": ("███", "██ ", "███"),
    "6": ("█  ", "███", "███"), "7": ("███", "  █", "  █"), "8": ("███", "███", "███"),
    "9": ("███", "███", "  █"), ".": ("   ", "   ", " █ "), ":": ("   ", " █ ", " █ "),
    " ": ("   ", "   ", "   "), "-": ("   ", "███", "   "),
}


def bignum(text, kind="text_bright"):
    """Three-row block digits. A DJ reads tempo at a glance; small text is wrong."""
    rows = ["", "", ""]
    for ch in str(text):
        g = _DIGITS.get(ch, _DIGITS[" "])
        for i in range(3):
            rows[i] += g[i] + " "
    return [c(kind, r.rstrip()) for r in rows]


def title(text, kind="accent"):
    return c(kind, " ".join(str(text).upper()))


# ------------------------------------------------------------------ motion

def pulse(t, speed=1.0):
    import math
    return 0.5 + 0.5 * math.sin(t * speed * 6.283185307)


def beat_flash(phase):
    """Chrome brightens on the downbeat. Subtle - a nudge, not a strobe."""
    p = 0.0 if phase != phase else (phase % 1.0)
    return "border_focus" if p < 0.12 else "border"


def vu_decay(prev, now, rate=0.25):
    return now if now >= prev else prev - (prev - now) * rate
