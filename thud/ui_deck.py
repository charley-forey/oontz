"""DECK: the page you mix on.

A different instrument from STUDIO, so it looks different - two decks stacked
like real gear, waveforms you can see a whole track in, and a mixer you can read
at a glance. Every panel degrades internally and every module it draws from is
imported lazily, so this page renders whether or not deck/mixer/waveform landed.
"""
import numpy as np

from .contracts import PANELS, SR
from .layout import Panel
from .term import fit, vlen, DIM, OFF, INV
from . import theme as T


def _decks():
    try:
        from .deck import DECKS
        return DECKS
    except Exception:
        return None


def _mix():
    try:
        from .mixer import MIX
        return MIX
    except Exception:
        return None


def _mmss(sec):
    sec = max(0, int(sec))
    return "%d:%02d" % (sec // 60, sec % 60)


def _wave(buf, w, pos_frac, marks=(), h=1):
    """Overview waveform.

    Height comes from RMS and colour from peak. Peak alone pins almost every
    column to full on dance music and the arrangement disappears; RMS shows the
    intro and the break as the quiet passages they actually are.
    """
    if buf is None or len(buf) < 2 or w < 4:
        return [T.c("muted", "-" * w) for _ in range(h)]
    mono = buf[:, 0] if buf.ndim == 2 else buf
    n = len(mono)
    step = max(1, n // w)
    body = np.zeros(w)
    tops = np.zeros(w)
    for i in range(w):
        seg = mono[i * step:min(n, (i + 1) * step)]
        if len(seg):
            body[i] = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
            tops[i] = float(np.abs(seg).max())
    mx = body.max() or 1.0
    head = int(pos_frac * (w - 1))
    mark_cols = {int(m[0] / float(n) * (w - 1)): m[1] for m in marks} if marks else {}
    rows = []
    for r in range(h):
        line = []
        for i in range(w):
            lvl = body[i] / mx
            need = (h - r) / float(h)
            if lvl >= need:
                kind = "danger" if tops[i] > 0.85 else ("warn" if tops[i] > 0.5 else "accent")
                ch = T.c(kind, "#" if T._S["ascii"] else "█")
            elif lvl >= need - (0.5 / h):
                ch = T.c("accent", "▄")
            elif i in mark_cols and r == h - 1:
                ch = T.c("accent2", "|" if T._S["ascii"] else "│")
            else:
                ch = DIM + ("." if T._S["ascii"] else "·") + OFF
            if i == head:
                ch = INV + ch + OFF
            line.append(ch)
        rows.append("".join(line))
    return rows


def _deck_panel(which):
    def render(s, w, h):
        D = _decks()
        if D is None:
            return [fit(T.c("text_dim", "  deck engine not loaded"), w)] + [" " * w] * (h - 1)
        d = D.get(which)
        col = "accent" if which == "a" else "accent2"
        if d.loading:
            return [fit("  " + T.c(col, "DECK %s" % which.upper()) + "  " +
                        T.progress(d.progress, max(10, w - 24), "rendering"), w)] + \
                   [" " * w] * (h - 1)
        if d.n <= 1:
            return [fit("  " + T.c(col, "DECK %s" % which.upper()) +
                        T.c("text_dim", "   empty  ·  `load %s <song>`" % which), w)] + \
                   [" " * w] * (h - 1)
        pos = d.pos / float(max(1, d.n))
        head = [
            "  " + T.c(col, "DECK %s" % which.upper()) + "  " +
            T.c("text_bright", d.title[:24]) + "  " +
            T.c("text", "%.1f BPM" % d.effective_bpm()) +
            (T.c("warn", "  %+.2f%%" % ((d.rate - 1) * 100)) if abs(d.rate - 1) > 1e-4 else "") +
            T.c("text_dim", "  %s / %s" % (_mmss(d.pos / SR), _mmss(d.duration()))) +
            "  " + T.led(d.playing, "ok") +
            (T.c("accent", "  LOOP") if d.loop else "") +
            T.c("text_dim", "  %s" % d.section_at_pos()),
        ]
        wave_h = max(1, min(4, h - 2))
        body = _wave(d.buf, max(8, w - 4), pos, d.marks, wave_h)
        beat = d.beat_phase()
        foot = "  " + T.c("text_dim", "beat %d" % d.beat()) + "  " + \
               T.meter(beat, max(6, min(20, w - 30)), col) + \
               T.c("text_dim", "  cue %s" % _mmss(d.cue / SR))
        out = head + ["  " + b for b in body] + [foot]
        return [fit(l, w) for l in (out + [""] * h)[:h]]
    return render


def mixer_panel(s, w, h):
    M = _mix()
    if M is None:
        return [fit(T.c("text_dim", "  mixer not loaded"), w)] + [" " * w] * (h - 1)
    out = []
    for name in ("a", "b"):
        ch = M.ch[name]
        kills = "".join(T.c("danger" if v <= 0.01 else "text_dim", n)
                        for n, v in zip("LMH", ch.eq))
        out.append("  " + T.c("accent" if name == "a" else "accent2", name.upper()) +
                   " " + T.meter(ch.fader, max(6, min(18, w - 40)),
                                 "accent" if name == "a" else "accent2") +
                   "  eq " + kills +
                   "  " + T.gauge(ch.filter, max(9, min(22, w - 34)), "flt", -1.0, 1.0, True))
    if h > 2:
        out.append("  " + T.crossfader(M.xf, max(12, w - 16)) +
                   T.c("text_dim", "  %s" % M.curve))
    if h > 3:
        out.append("  " + T.c("text_dim", "master ") +
                   T.meter(min(1.0, M.rms * 3), max(8, min(30, w - 26)),
                           "danger" if M.peak > 0.97 else "ok", min(1.0, M.peak)) +
                   T.c("danger" if M.peak > 0.97 else "text_dim", "  %.2f" % M.peak))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


def beatmatch(s, w, h):
    D = _decks()
    if D is None or D.a.n <= 1 or D.b.n <= 1:
        return [fit(T.c("text_dim", "  load both decks to beatmatch"), w)] + [" " * w] * (h - 1)
    pa, pb = D.a.beat_phase(), D.b.beat_phase()
    drift = abs(pa - pb)
    drift = min(drift, 1.0 - drift)
    inner = max(10, w - 22)
    def strip(p, kind):
        i = int(p * (inner - 1))
        return "".join(T.c(kind, "█") if k == i else (DIM + "·" + OFF) for k in range(inner))
    lock = "ok" if drift < 0.02 else ("warn" if drift < 0.08 else "danger")
    out = ["  " + T.c("accent", "A ") + strip(pa, "accent"),
           "  " + T.c("accent2", "B ") + strip(pb, "accent2"),
           "  " + T.c(lock, "drift %.3f" % drift) +
           T.c("text_dim", "   ΔBPM %.2f" % (D.a.effective_bpm() - D.b.effective_bpm())) +
           T.c(lock, "   %s" % ("LOCKED" if drift < 0.02 else "adjust"))]
    return [fit(l, w) for l in (out + [""] * h)[:h]]


def browser(s, w, h):
    """The library, with a compatibility read against what is playing."""
    try:
        import glob, os
        from . import song as sm
    except Exception:
        return [" " * w] * h
    D = _decks()
    ref = None
    if D is not None:
        ref = D.a.song if D.a.n > 1 else (D.b.song if D.b.n > 1 else None)
    rows = [T.c("text_dim", "  %-18s %6s %6s %7s  %s" %
                ("song", "bpm", "key", "length", "match"))]
    try:
        from . import harmony as hm
    except Exception:
        hm = None
    for p in sorted(glob.glob("songs/*.song"))[:max(0, h - 1)]:
        try:
            sg = sm.Song.load(p)
        except Exception:
            continue
        cam = hm.camelot(sg.key, sg.scale) if hm else ""
        note = ""
        if ref is not None and hm is not None and sg.fingerprint() != ref.fingerprint():
            kd = hm.key_distance(sg.key, sg.scale, ref.key, ref.scale)
            bd = abs(sg.bpm - ref.bpm) / max(1.0, ref.bpm) * 100
            score = max(0.0, 1.0 - kd * 0.25 - min(1.0, bd / 8.0) * 0.5)
            kind = "ok" if score > 0.7 else ("warn" if score > 0.4 else "danger")
            note = T.c(kind, "%3d%%" % int(score * 100)) + \
                T.c("text_dim", "  %s, %+.0f BPM" % (
                    "same key" if kd == 0 else ("compatible" if kd <= 1 else "clashes"),
                    sg.bpm - ref.bpm))
        rows.append("  %-18s %6.1f %6s %7s  %s" % (
            os.path.basename(p)[:-5][:18], sg.bpm, cam or sg.key,
            _mmss(sg.seconds()), note))
    if len(rows) == 1:
        rows.append(T.c("text_dim", "  no .song files yet - `song save` one in STUDIO"))
    return [fit(l, w) for l in (rows + [""] * h)[:h]]


def master_bar(s, w, h):
    M = _mix()
    D = _decks()
    bits = [T.c("accent2", " DECK "), T.c("text_dim", "M switches back to STUDIO")]
    if M is not None:
        bits.append(T.c("danger" if M.peak > 0.97 else "text",
                        "master %.2f" % M.peak))
    if D is not None:
        bits.append(T.c("text_dim", "A %s / B %s" %
                        (D.a.title[:14] or "-", D.b.title[:14] or "-")))
    if s.recording:
        bits.append(T.c("danger", "REC %s" % _mmss(s.rec_secs)))
    return [fit(T.c("border", " · ").join(bits), w)]


def hint(s, w, h):
    txt = s.echo or s.hint or "load a <song> · load b <song> · deck b sync · xf 0.5"
    return [fit("  " + T.c("warn" if s.echo else "text_dim", "▸ ") +
                T.c("text" if s.echo else "text_dim", txt), w)]


PANELS_DECK = [
    Panel("master", master_bar, 40, 1, 200, 1, priority=100, region="top"),
    Panel("deck_a", _deck_panel("a"), 40, 3, 200, 7, priority=95, region="upper"),
    Panel("deck_b", _deck_panel("b"), 40, 3, 200, 7, priority=94, region="lower"),
    Panel("mixer", mixer_panel, 34, 2, 80, 5, priority=90, region="main"),
    Panel("beatmatch", beatmatch, 30, 3, 60, 4, priority=88, region="main"),
    Panel("browser", browser, 44, 3, 90, 12, priority=70, region="main", grow=True),
    Panel("hint", hint, 20, 1, 200, 1, priority=96, region="bottom"),
]

PANELS["deck"] = PANELS_DECK


def layout_for(s, w, h):
    from .layout import solve
    keep = {"master", "deck_a", "deck_b", "hint"}
    if h >= 20:
        keep.add("mixer")
    if w >= 70 and h >= 22:
        keep.add("beatmatch")
    if h >= 30 and w >= 90:
        keep.add("browser")
    return solve([p for p in PANELS_DECK if p.name in keep], w, h)
