"""STUDIO: the page you build a song on.

Panels declare their size and priority; layout.solve decides what fits. Every
render is pure - f(snapshot, w, h) -> list[str] of exactly w visible columns -
and every one degrades internally, because the solver may hand it 40 columns or
180.

The headline panel is `arrangement`. A page that only ever showed one bar is why
this felt like a loop; showing the whole song is the fix.
"""
from .contracts import PANELS
from .layout import Panel
from .term import fit, vlen, ANSI, COL, DIM, OFF, INV
from . import theme as T

ROLE_COL = {"intro": "muted", "build": "warn", "drop": "danger", "break": "accent",
            "verse": "ok", "fill": "accent2", "outro": "muted", "loop": "accent"}
STEP_KEYS = "qwertyuiasdfghjk"


def _song(s):
    """The Song being edited, or None. Snapshot has no song field, so ask core."""
    try:
        from . import core
        return core.ST.song
    except Exception:
        return None


def _mmss(sec):
    return "%d:%02d" % (int(sec) // 60, int(sec) % 60)


# ---------------------------------------------------------------- transport

def transport(s, w, h):
    sg = _song(s)
    left = [T.c("accent", " STUDIO "), T.c("text_bright", s.name)]
    if sg is not None:
        pos = 0
        try:
            from . import core
            pos = core.ST.songbar
        except Exception:
            pass
        left.append(T.c("text", "bar %d/%d" % (pos + 1, max(1, sg.total_bars()))))
        cur, _sec, within, _i = sg.section_at(pos)
        left.append(T.c("accent2", "%s %d/%d" % (cur, within + 1, _sec.bars if _sec else 0)))
        left.append(T.c("text_dim", "%s %s" % (sg.key, sg.scale)))
        left.append(T.c("text_dim", _mmss(sg.seconds())))
    left.append(T.c("text", "%g BPM" % s.bpm))
    if s.swing:
        left.append(T.c("text_dim", "swing %g%%" % s.swing))
    if s.recording:
        left.append(T.c("danger", "REC %s" % _mmss(s.rec_secs)))
    if s.drops:
        left.append(T.c("warn", "drops %d" % s.drops))
    line = T.c("border", " · ").join(left)
    return [fit(line, w)]


# -------------------------------------------------------------- arrangement

def arrangement(s, w, h):
    """The whole song as proportional blocks, with the playhead inside it."""
    sg = _song(s)
    if sg is None or not sg.order:
        body = [T.c("text_dim", "  no song  ·  `song new <name>` or `compose hardtechno 5`")]
        return [fit(l, w) for l in (body + [""] * h)[:h]]
    try:
        from . import core
        bar = core.ST.songbar
    except Exception:
        bar = 0

    total = max(1, sg.total_bars())
    inner = max(8, w - 2)
    cells, edges, acc = [], [], 0
    for n in sg.order:
        sec = sg.sections[n]
        span = max(1, int(round(sec.bars * inner / float(total))))
        edges.append((acc, span, n, sec))
        acc += span
    if acc < inner and edges:                      # give rounding slack to the last
        a, sp, n, sec = edges[-1]
        edges[-1] = (a, sp + inner - acc, n, sec)

    cur_name, _sec, _within, _i = sg.section_at(bar)
    row, labels = [], [" "] * inner
    head_col = int(bar / float(total) * inner)
    for start, span, n, sec in edges:
        kind = ROLE_COL.get(sec.role, "text")
        glyph = "█" if sec.energy > 0.8 else ("▓" if sec.energy > 0.5 else "▒")
        for k in range(span):
            i = start + k
            if i >= inner:
                break
            cell = T.c(kind, glyph)
            if i == head_col:
                cell = INV + cell + OFF
            row.append(cell)
        lab = n[:max(0, span - 1)]
        for j, ch in enumerate(lab):
            if start + j < inner:
                labels[start + j] = ch
    row += [" "] * (inner - len(row))

    out = [" " + "".join(row)]
    out.append(" " + "".join(T.c("text_bright" if cur_name and
                                 "".join(labels).find(cur_name) <= i <
                                 "".join(labels).find(cur_name) + len(cur_name)
                                 else "text_dim", ch)
                            for i, ch in enumerate(labels)))
    if h >= 3:                                     # energy curve under the blocks
        es = []
        for start, span, n, sec in edges:
            es += [sec.energy] * span
        out.append(" " + T.sparkline(es or [0], inner, "accent2"))
    if h >= 4:
        cur = sg.sections.get(cur_name)
        if cur:
            _n, _s, within, _i2 = sg.section_at(bar)
            out.append("  " + T.c("text_bright", cur_name) +
                       T.c("text_dim", "  %s  bar %d/%d  energy %.2f  %d automation" %
                           (cur.role, within + 1, cur.bars, cur.energy, len(cur.automation))))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


# --------------------------------------------------------------------- pads

def pads(s, w, h):
    """The focused track's 16 steps as hardware pads, with their keys on them."""
    if not s.tracks:
        return [fit("", w) for _ in range(h)]
    t = s.tracks[min(s.focus, len(s.tracks) - 1)]
    pat = (t.pat + "." * 16)[:16]
    cols = 8 if w >= 8 * 7 else 4
    rows = 16 // cols
    pw = max(3, min(9, (w - 2) // cols))
    ph = 2 if h >= rows * 2 else 1
    out = [fit("  " + T.c(t.name, t.name) + T.c("text_dim", "  %s  %s" %
               (t.voice if hasattr(t, "voice") else "", "accent = bright")), w)] if h > rows * ph else []
    for r in range(rows):
        strip = [[], []]
        for k in range(cols):
            i = r * cols + k
            ch = pat[i]
            cell = T.pad(STEP_KEYS[i], ch not in ".-", ch.isupper(),
                         i == s.step and s.playing, pw, ph)
            strip[0].append(cell[0])
            if ph > 1:
                strip[1].append(cell[1])
        out.append(" " + "".join(strip[0]))
        if ph > 1:
            out.append(" " + "".join(strip[1]))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


# ------------------------------------------------------------------- tracks

def tracks(s, w, h):
    out = []
    for i, t in enumerate(s.tracks):
        if len(out) >= h:
            break
        focused = i == s.focus
        name = ("%s%d %-8s" % ("▸" if focused else " ", i + 1, t.name[:8]))
        tag = T.c("text_bright" if focused else t.name, name)
        steps = []
        for j, ch in enumerate(t.pat[:32]):
            g = "·" if ch in ".-" else "█"
            cell = (DIM + g + OFF) if ch in ".-" else T.c(
                "text_bright" if ch.isupper() else t.name, g)
            if j == s.step and s.playing:
                cell = INV + cell + OFF
            steps.append(cell)
        mw = max(4, min(12, w - 60))
        extras = []
        if t.mute:
            extras.append(T.c("danger", "M"))
        if t.solo:
            extras.append(T.c("warn", "S"))
        if t.filt:
            extras.append(T.c("text_dim", "%s%d" % (t.filt[:1], t.fc)))
        if t.sc:
            extras.append(T.c("text_dim", "sc%.1f" % t.sc))
        out.append("%s %s  %s %s" % (tag, "".join(steps),
                                     T.meter(min(1.0, t.rms * 5), mw,
                                             t.name if t.active else "muted"),
                                     " ".join(extras)))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


# ----------------------------------------------------------------- sections

def sections(s, w, h):
    sg = _song(s)
    if sg is None:
        return [fit(T.c("text_dim", "  jam mode - no sections"), w)] + [" " * w] * (h - 1)
    try:
        from . import core
        cur, _sec, _wi, _i = sg.section_at(core.ST.songbar)
    except Exception:
        cur = None
    out = []
    for n in sg.order[:h]:
        sec = sg.sections[n]
        mark = "▸" if n == cur else " "
        out.append("%s %s %s %s %s" % (
            T.c("accent" if n == cur else "text_dim", mark),
            T.c("text_bright" if n == cur else "text", "%-10s" % n[:10]),
            T.c(ROLE_COL.get(sec.role, "text"), "%-6s" % sec.role[:6]),
            T.c("text_dim", "%3db" % sec.bars),
            T.meter(sec.energy, max(4, min(16, w - 32)),
                    ROLE_COL.get(sec.role, "accent"))))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


# --------------------------------------------------------------- automation

def automation(s, w, h):
    sg = _song(s)
    if sg is None:
        return [" " * w for _ in range(h)]
    try:
        from . import core
        _n, sec, _wi, _i = sg.section_at(core.ST.songbar)
    except Exception:
        sec = None
    if sec is None or not sec.automation:
        return [fit(T.c("text_dim", "  no automation in this section"), w)] + \
               [" " * w] * (h - 1)
    from . import song as sm
    out = []
    for a in sec.automation[:h]:
        target, lo, hi = a[0], float(a[1]), float(a[2])
        start = int(a[3]) if len(a) > 3 else 0
        length = int(a[4]) if len(a) > 4 and a[4] else sec.bars - start
        cname = a[5] if len(a) > 5 else "linear"
        fn = sm.CURVES.get(cname, sm.CURVES["linear"])
        gw = max(6, w - 26)
        vals = [fn(k / float(max(1, length - 1))) for k in range(min(length, gw))]
        out.append("%s %s %s" % (
            T.c("accent2", "%-12s" % target[:12]),
            T.c("text_dim", "%5g→%-5g" % (lo, hi)),
            T.sparkline(vals or [0], gw, "accent2")))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


# --------------------------------------------------------------------- hint

def hint(s, w, h):
    txt = s.echo or s.hint
    kind = "warn" if s.echo else "text_dim"
    return [fit("  " + T.c(kind, "▸ ") + T.c("text" if s.echo else "text_dim", txt), w)]


PANELS_STUDIO = [
    Panel("transport", transport, 40, 1, 200, 1, priority=100, region="top"),
    Panel("arrangement", arrangement, 40, 2, 200, 4, priority=92, region="upper"),
    Panel("tracks", tracks, 46, 3, 78, 11, priority=84, region="main", grow=True),
    Panel("pads", pads, 34, 3, 62, 9, priority=80, region="main"),
    Panel("sections", sections, 30, 2, 54, 12, priority=60, region="lower", grow=True),
    Panel("automation", automation, 34, 2, 70, 5, priority=50, region="lower"),
    Panel("hint", hint, 20, 1, 200, 1, priority=96, region="bottom"),
]

PANELS["studio"] = PANELS_STUDIO


def layout_for(s, w, h):
    """Offer panels the size can afford; the solver does the rest."""
    from .layout import solve, breakpoint_for
    keep = {"transport", "hint"}
    if h >= 20:
        keep.add("arrangement")
    if w >= 46 and h >= 12:
        keep.add("tracks")
    if w >= 86 and h >= 18:                 # tracks and pads side by side
        keep.add("pads")
    elif w < 86 and h >= 12:
        keep.add("pads")
    if h >= 26:
        keep.add("sections")
    if h >= 34 and w >= 110:
        keep.add("automation")
    return solve([p for p in PANELS_STUDIO if p.name in keep], w, h)
