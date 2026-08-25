"""Responsive layout: panels declare what they need, a solver decides what fits.

Row arithmetic is why terminal UIs break when you resize them. Here nothing
computes its own position. A panel says how small it can get, how big it would
like to be, and how much it matters; the solver drops the least important things
that cannot fit and hands everyone else a rectangle.

    Panel(name, render, min_w, min_h, want_w, want_h, priority, grow, region)
    solve(panels, w, h) -> [Placed(panel, x, y, w, h)]

A panel's render is f(snapshot, w, h) -> list[str], each line exactly w visible
columns - the same contract views already use. Panels also degrade INTERNALLY:
the solver tells a waveform it has 40 columns or 180, and it draws the same song
either way.
"""
from .term import fit, vlen

# Breakpoints. Each is a design, not a squeeze.
BREAKPOINTS = [(0, "xs"), (100, "s"), (140, "m"), (200, "l"), (240, "xl")]

# region -> where it sits. Rows stack top to bottom; a row splits horizontally.
REGIONS = ("top", "upper", "main", "lower", "bottom")
ROW_ORDER = {r: i for i, r in enumerate(REGIONS)}


class Panel:
    def __init__(self, name, render, min_w=20, min_h=1, want_w=0, want_h=0,
                 priority=50, grow=False, region="main", title=""):
        self.name = name
        self.render = render
        self.min_w, self.min_h = min_w, min_h
        self.want_w = want_w or min_w
        self.want_h = want_h or min_h
        self.priority = priority          # higher survives when space runs out
        self.grow = grow                  # absorbs leftover rows
        self.region = region
        self.title = title

    def __repr__(self):
        return "Panel(%s p%d %s)" % (self.name, self.priority, self.region)


class Placed:
    __slots__ = ("panel", "x", "y", "w", "h")

    def __init__(self, panel, x, y, w, h):
        self.panel, self.x, self.y, self.w, self.h = panel, x, y, w, h

    def __repr__(self):
        return "Placed(%s %dx%d at %d,%d)" % (self.panel.name, self.w, self.h, self.x, self.y)


def breakpoint_for(w, h):
    name = "xs"
    for lo, n in BREAKPOINTS:
        if w >= lo:
            name = n
    if h < 24:                            # a short terminal is a small one
        name = "xs"
    elif h < 30 and name in ("m", "l", "xl"):
        name = "s"
    elif h < 40 and name in ("l", "xl"):
        name = "m"
    return name


def solve(panels, w, h):
    """Place what fits, drop what does not, hand out the slack.

    Panels are grouped into rows by region. A row's height is the tallest want_h
    of its members, then rows compete for the terminal's height by priority.
    Within a row, widths are shared in proportion to want_w, never below min_w.
    """
    rows = {}
    for p in panels:
        rows.setdefault(p.region, []).append(p)
    ordered = sorted(rows.items(), key=lambda kv: ROW_ORDER.get(kv[0], 99))

    # 1. within each row, keep only the panels whose min_w can coexist
    kept = []
    for region, members in ordered:
        members = sorted(members, key=lambda p: -p.priority)
        fitting, used = [], 0
        for p in members:
            if used + p.min_w + (1 if fitting else 0) <= w:
                fitting.append(p)
                used += p.min_w + (1 if len(fitting) > 1 else 0)
        if fitting:
            kept.append((region, fitting, max(p.min_h for p in fitting),
                         max(p.want_h for p in fitting),
                         max(p.priority for p in fitting)))

    # 2. rows compete for height; least important row is dropped first
    while kept and sum(r[2] for r in kept) > h:
        worst = min(range(len(kept)), key=lambda i: kept[i][4])
        kept.pop(worst)
    if not kept:
        return []

    heights = [r[2] for r in kept]
    slack = h - sum(heights)
    for i, r in enumerate(kept):                  # grow toward want_h
        if slack <= 0:
            break
        take = min(slack, max(0, r[3] - heights[i]))
        heights[i] += take
        slack -= take
    growers = [i for i, r in enumerate(kept) if any(p.grow for p in r[1])]
    if slack > 0 and growers:                     # give the rest to grow panels
        share, extra = divmod(slack, len(growers))
        for j, i in enumerate(growers):
            heights[i] += share + (1 if j < extra else 0)
    elif slack > 0:
        heights[-1] += slack

    # 3. lay out
    placed, y = [], 0
    for (region, members, _minh, _wanth, _pri), rh in zip(kept, heights):
        members = sorted(members, key=lambda p: (-p.priority, p.name))
        widths = _share_width(members, w)
        x = 0
        for p, pw in zip(members, widths):
            placed.append(Placed(p, x, y, pw, rh))
            x += pw
        y += rh
    return placed


def _share_width(members, w):
    """min_w to everyone, then the rest in proportion to want_w."""
    n = len(members)
    widths = [p.min_w for p in members]
    left = w - sum(widths)
    if left <= 0:
        return _trim_to(widths, w)
    demand = [max(0, p.want_w - p.min_w) for p in members]
    total = sum(demand)
    if total > 0:
        for i in range(n):
            take = min(left, int(round(left * demand[i] / float(total))))
            widths[i] += take
    short = w - sum(widths)
    if short:                                     # rounding remainder to the widest
        widths[max(range(n), key=lambda i: widths[i])] += short
    return widths


def _trim_to(widths, w):
    while sum(widths) > w and any(x > 1 for x in widths):
        i = max(range(len(widths)), key=lambda i: widths[i])
        widths[i] -= 1
    return widths


def compose(placed, snapshot, w, h, fill=" "):
    """Render every placed panel into one screen of exactly h lines x w columns.

    A panel that raises, or returns the wrong shape, gets an inline error in its
    own rectangle. One bad panel must never take the page down mid-performance.
    """
    screen = [[fill] * w for _ in range(h)]
    for pl in placed:
        try:
            lines = pl.panel.render(snapshot, pl.w, pl.h)
            lines = [fit(l, pl.w) for l in list(lines)[:pl.h]]
        except Exception as e:
            lines = [fit("  %s: %s" % (pl.panel.name, e), pl.w)]
        lines += [" " * pl.w] * (pl.h - len(lines))
        for dy, line in enumerate(lines):
            y = pl.y + dy
            if 0 <= y < h:
                _blit(screen[y], line, pl.x, pl.w)
    return ["".join(row) for row in screen]


def _blit(row, line, x, width):
    """Write a coloured string into a cell row without disturbing its neighbours.

    Cells hold whole escape-sequence-plus-glyph chunks, so the row joins back to a
    string whose VISIBLE width is still exactly w.
    """
    cells, buf, seen = [], "", 0
    i = 0
    while i < len(line) and seen < width:
        if line[i] == "\x1b":                      # keep an escape with its glyph
            j = i
            while j < len(line) and line[j] not in "mK":
                j += 1
            buf += line[i:j + 1]
            i = j + 1
            continue
        cells.append(buf + line[i])
        buf = ""
        seen += 1
        i += 1
    if buf and cells:
        cells[-1] += buf
    for k, cell in enumerate(cells):
        if 0 <= x + k < len(row):
            row[x + k] = cell
    for k in range(len(cells), width):
        if 0 <= x + k < len(row):
            row[x + k] = " "


def describe(placed, w, h):
    """One line per placed panel. Used by the layout sweep test and by `:layout`."""
    bp = breakpoint_for(w, h)
    out = ["%dx%d  breakpoint %s  %d panels" % (w, h, bp, len(placed))]
    for pl in sorted(placed, key=lambda p: (p.y, p.x)):
        out.append("  %-16s %3d,%-3d %3dx%-3d" % (pl.panel.name, pl.x, pl.y, pl.w, pl.h))
    return out
