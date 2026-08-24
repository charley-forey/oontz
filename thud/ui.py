"""The static page: one full screen, never scrolls, 30fps, diff-rendered.

No curses. Alt-screen buffer + ANSI + raw single-key reads, all stdlib. Only
lines that changed are rewritten, so the page doesn't flicker under screen
capture.
"""
import os
import sys
import time
import math
import dataclasses
import numpy as np

from . import core
from .core import ST, do, echo, complete, CMDS, TRACK_ORDER, REC
from .contracts import VIEWS

if os.name == "nt":
    import msvcrt
else:
    try:
        import tty
        import termios
        import select
    except ImportError:                # the browser: no terminal to put in raw mode.
        tty = termios = select = None  # build()/on_key() still work; run() cannot.

from .term import ANSI, COL, DIM, OFF, INV, c, vlen, fit

STEP_KEYS = "qwertyuiasdfghjk"          # two rows of 8 = the 16 buttons

# ------------------------------------------------------------------- keys


def read_key():
    """One keypress, or None. Never blocks."""
    if os.name == "nt":
        if not msvcrt.kbhit():
            return None
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            b = ord(msvcrt.getwch())
            return "<F%d>" % (b - 58) if 59 <= b <= 68 else None   # F1-F10
        return ch
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None

# ------------------------------------------------------------- page pieces


def header(s, w):
    rec = c(196, " ⏺ REC %02d:%02d " % (s.rec_secs // 60, s.rec_secs % 60)) if s.recording else ""
    bits = [c(51, " THUD "), c(250, "%g BPM" % s.bpm), c(250, "bar %d" % s.bar),
            c(244, "swing %g%%" % s.swing), rec, c(244, s.name)]
    line = c(238, "┌─") + c(238, "─").join(b for b in bits if b)
    return fit(line + " " + c(238, "─" * w), w)


def master_bar(s, w):
    """RMS fill with a peak tick, on the same dB scale as the meters view.

    Peak alone sits near 0dBFS almost all the time, which is why the old bar read
    as permanently full; RMS is what tells you how loud it actually is.
    """
    rms = float(np.sqrt(np.mean(np.square(s.scope)))) if len(s.scope) else 0.0
    try:
        from .viz_scope import _db, _frac_from_db
        rdb, pdb = _db(rms), _db(s.peak)
        rf, pf = _frac_from_db(rdb), _frac_from_db(pdb)
    except Exception:                                    # viz_scope absent
        rdb, pdb = _fallback_db(rms), _fallback_db(s.peak)
        rf, pf = max(0.0, (rdb + 60) / 60), max(0.0, (pdb + 60) / 60)
    bw = w - 30
    n = int(rf * bw)
    tick = min(bw - 1, int(pf * bw))
    col = 196 if pdb > -0.5 else (214 if pdb > -6 else 78)
    cells = [c(col, "█")] * n + [DIM + "░" + OFF] * (bw - n)
    if 0 <= tick < bw:
        cells[tick] = c(231, "▏")                        # peak-hold tick
    clip = c(196, " CLIP") if pdb > -0.1 else "     "
    return fit("  " + c(244, "master ") + "".join(cells) +
               c(250, " %+5.1f dB" % rdb) + clip, w)


def _fallback_db(x):
    return -60.0 if x <= 0.001 else max(-60.0, 20 * math.log10(x))


def track_row(t, i, s, w):
    col = COL.get(t.name, 250)
    sel = "▸" if i == s.focus else " "
    tag = "%s%d %-7s" % (sel, i + 1, t.name[:7])
    tag = c(231 if i == s.focus else col, tag)
    cells = []
    for j, ch in enumerate(t.pat):
        glyph = "·" if ch in ".-" else ("▒" if ch == "?" else "█")
        g = DIM + glyph + OFF if ch in ".-" else c(231 if ch.isupper() else col, glyph)
        if j == s.step and s.playing:
            g = INV + g + OFF
        cells.append(g + ("  " if j % 4 == 3 else " "))
    meter_w = 10
    lvl = int(min(1.0, t.rms * 6) * meter_w)
    meter = c(col if t.active else 240, "█" * lvl) + DIM + "░" * (meter_w - lvl) + OFF
    extra = []
    if t.mute:
        extra.append(c(196, "MUTE"))
    if t.solo:
        extra.append(c(226, "SOLO"))
    if t.filt:
        extra.append(c(244, "%s %d" % (t.filt, t.fc)))
    if t.sc:
        extra.append(c(244, "sc %.1f" % t.sc))
    return fit("%s %s %s %s" % (tag, "".join(cells), meter, " ".join(extra)), w)


def legend(s, w):
    """Generated from the key table, so a shown key always does what it says."""
    try:
        from . import keyboard_view as kv
        return fit(kv.legend_bar(s, w), w)
    except Exception:
        pass
    try:
        from . import teach
        return fit(teach.legend(s, w), w)
    except Exception:
        pass
    t = s.tracks[s.focus]
    if s.mode == "cmd":
        items = [("Tab", "complete"), ("Enter", "run"), ("Esc", "back"), ("?", "keys")]
    else:
        items = [("1-8", "track"), (STEP_KEYS[:4] + "..", "steps"), ("spc", "play"),
                 ("[ ]", "cutoff" if core.is_pitched(ST.tracks[t.name]) else "filter"),
                 ("z x", "mute solo"), ("/", "roll"), ("\\", "spin"), ("R", "rec"),
                 (":", "cmd"), ("?", "all keys")]
    return fit("  " + c(238, " · ").join(c(117, k) + " " + c(245, v) for k, v in items), w)


def status(s, w):
    if s.echo:
        return fit("  " + c(226, "▸ ") + c(253, s.echo), w)
    return fit("  " + c(240, "▸ ") + c(244, s.hint), w)


def cmdline(s, w):
    if s.mode != "cmd":
        return fit("  " + DIM + "press : for commands" + OFF, w)
    return fit("  " + c(51, ":") + c(255, s.cmdline) + DIM + s.complete + OFF + INV + " " + OFF, w)


HELP = [
    ("PLAY", [("1-8", "focus track"), ("space", "play / stop"),
              ("qwertyui asdfghjk", "toggle the 16 steps of the focused track"),
              ("[ ]", "filter cutoff down / up  (hold to sweep)"),
              ("{ }", "resonance down / up"), ("- =", "bpm -1 / +1"),
              ("_ +", "bpm -10 / +10"), (", .", "swing down / up"),
              ("z / x", "mute / solo focused track"), ("n", "variation on focused track"),
              ("T", "tap tempo"), ("R", "start / stop recording"),
              ("ctrl+z / ctrl+y", "undo / redo"), ("A", "A/B compare"),
              ("Tab", "cycle view"), ("?", "this screen"), (":", "command mode")]),
    ("COMMANDS", [("%s  (%s)" % (n, a or "-"), h) for n, (_, a, h) in sorted(CMDS.items())]),
    ("PATTERNS", [("kick x...x...x...x...", "x = hit, X = accent, . = rest"),
                  ("bass a1 . a1~ c2!", "~ = slide into note, ! = accent"),
                  ("any length", "5 steps against 16 = polymeter, for free")]),
]


def help_page(w, h):
    out = ["", "  " + c(51, "THUD — every key"), ""]
    for title, rows in HELP:
        out.append("  " + c(226, title))
        for k, v in rows:
            out.append("    %s  %s" % (c(117, "%-20s" % k), c(245, v)))
        out.append("")
    out.append("  " + c(240, "any key to close"))
    return [fit(l, w) for l in out[:h]]

# ------------------------------------------------------------------ frame


def rule(w):
    return fit(c(238, "├" + "─" * (w - 2) + "┤"), w)


def views():
    """perform (the grid alone) plus whatever view modules have registered."""
    return ["perform"] + sorted(VIEWS)


def panel(s, w, h):
    """The middle region: whichever view is selected, or empty space."""
    if h <= 0:
        return []
    fn = VIEWS.get(s.view)
    if fn is None:
        return [" " * w] * h
    try:
        lines = list(fn(s, w, h))[:h]
    except Exception as e:                           # a broken view must not kill the page
        lines = [fit("  " + c(196, "view %r: %s: %s" % (s.view, type(e).__name__, e)), w)]
    return lines + [" " * w] * (h - len(lines))


def build(s, w, h):
    """The page. Uses the v3 panel system when it is present, else the v2 page."""
    if s.overlay == "help":
        return overlay_page(s, w, h)
    page = _panel_page(s, w, h)
    if page is not None:
        return page
    head = [header(s, w), master_bar(s, w), rule(w)]
    head += [track_row(t, i, s, w) for i, t in enumerate(s.tracks)]
    head.append(rule(w))
    tail = [rule(w), legend(s, w), status(s, w), cmdline(s, w)]
    rows = head + panel(s, w, h - len(head) - len(tail)) + tail
    return rows[:h] if len(rows) >= h else rows + [" " * w] * (h - len(rows))


def _panel_page(s, w, h):
    """Solve and compose the registered panels for the current mode.

    Returns None if the mode's panels are not available, so the instrument still
    runs with any subset of the v3 modules present.
    """
    try:
        from .contracts import PANELS
        from .layout import compose as lcompose
        mode = getattr(ST, "mode", "studio")
        if not PANELS.get(mode):
            return None
        if mode == "deck":
            from . import ui_deck as mod
        else:
            from . import ui_studio as mod
        placed = mod.layout_for(s, w, h)
        if not placed:
            return None
        return lcompose(placed, s, w, h)
    except Exception:
        return None                                  # never lose the page to a panel bug


def overlay_page(s, w, h):
    """keyboard_view generates this from the key table, so it cannot drift."""
    try:
        from . import keyboard_view as kv
        return [fit(l, w) for l in kv.cheatsheet(s, w, h, _overlay_page[0])][:h]
    except Exception:
        pass
    try:
        from . import teach
        return [fit(l, w) for l in teach.help_page(s, w, h)][:h]
    except Exception:
        return help_page(w, h)


# ------------------------------------------------------------------- input

# Hold-to-perform. The OS waits ~300ms before it starts repeating a held key, so the
# release window has to outlast that gap or the effect stutters out mid-hold.
# ponytail: 450ms suits this keyboard; it is the one number worth tuning by feel.
HOLD_MS = 450
PERF_KEYS = {"/": ("roll", {"length_beats": 0.25}), "?": ("roll", {"length_beats": 0.0625}),
             "v": ("stutter", {}), "\\": ("spinback", {}), "`": ("tapestop", {}),
             "c": ("reverse", {}), "b": ("brake", {})}
_held = {"key": None, "t": 0.0}

_cmd = {"buf": "", "on": False}
_overlay = [""]
_overlay_page = [0]
_taps = []


def sweep(t, mult):
    tr = ST.tracks[t.name]
    if core.is_pitched(tr):
        tr["fc"] = max(40.0, min(18000.0, (tr["fc"] or 350.0) * mult))
        core.autorec_touch("%s.fc" % t.name, tr["fc"])
        core.refresh()
        return echo("%s cutoff %d Hz" % (t.name, tr["fc"]))
    if not tr["filt"]:
        tr["filt"] = "lp"
        tr["fc"] = tr["fc"] or 8000.0
    tr["fc"] = max(40.0, min(18000.0, tr["fc"] * mult))
    core.autorec_touch("%s.fc" % t.name, tr["fc"])
    core.refresh()
    echo("%s %s %d Hz" % (t.name, tr["filt"], tr["fc"]))


def bump(attr, d, lo, hi, fmt):
    setattr(ST, attr, max(lo, min(hi, getattr(ST, attr) + d)))
    core.autorec_touch(attr, getattr(ST, attr))
    core.refresh()
    echo(fmt % getattr(ST, attr))


def hold_tick():
    """Release a performance effect once its key stops repeating."""
    if _held["key"] and (time.time() - _held["t"]) * 1000 > HOLD_MS:
        _held["key"] = None
        core.perform()
        echo("released")


def perf_key(k):
    """Engage a dj.py effect for as long as the key is held. Returns True if handled."""
    if k not in PERF_KEYS or not core.playing():
        return False
    try:
        from . import dj
    except ImportError:
        return False
    name, params = PERF_KEYS[k]
    fn = dj.PERFORM.get(name)
    if fn is None:
        return False
    if _held["key"] != k:
        core.perform(fn, bpm=ST.bpm, **params) if "bpm" in core._params_of(fn) else core.perform(fn, **params)
        echo(name)
    _held["key"], _held["t"] = k, time.time()
    return True


def on_key(k, s):
    """Returns False to quit."""
    if _overlay[0]:
        if k == "?":                                 # page through a long cheatsheet
            _overlay_page[0] += 1
        else:
            _overlay[0], _overlay_page[0] = "", 0
        return True

    if _cmd["on"]:
        if k in ("\r", "\n"):
            line, _cmd["buf"], _cmd["on"] = _cmd["buf"], "", False
            if line.strip() in ("q", "quit", "exit"):
                return False
            try:
                out = do(line)
                echo(out or line)
            except Exception as e:
                echo("%s: %s" % (type(e).__name__, e))
        elif k == "\x1b":
            _cmd["buf"], _cmd["on"] = "", False
        elif k == "\t":
            _cmd["buf"] += complete(_cmd["buf"])
        elif k in ("\x08", "\x7f"):
            _cmd["buf"] = _cmd["buf"][:-1]
        elif k >= " ":
            _cmd["buf"] += k
        return True

    if perf_key(k):
        return True

    t = s.tracks[min(ST.focus, len(s.tracks) - 1)]
    tr = ST.tracks[t.name]

    if k == ":":
        _cmd["on"], _cmd["buf"] = True, ""
    elif k == "?":
        _overlay[0] = "help"
    elif k == "\x03":
        return False
    elif k in "12345678":
        ST.focus = int(k) - 1
        ST.focus = min(ST.focus, len(ST.order) - 1)
        echo("focus %s" % ST.order[ST.focus])
    elif k in STEP_KEYS and ST.focus < len(ST.order):
        i = STEP_KEYS.index(k)
        pat = list(tr["pat"].ljust(16, ".")[:16])
        pat[i] = {".": "x", "x": "X", "X": "."}[pat[i] if pat[i] in ".xX" else "."]
        ST.mark()
        tr["pat"] = "".join(pat)
        if core.is_pitched(tr):                          # keep notes aligned
            notes = (list(tr["notes"]) + ["."] * 16)[:16]
            notes[i] = "." if pat[i] == "." else (notes[i] if notes[i] != "." else "a1")
            if pat[i] == "X" and not notes[i].endswith("!"):
                notes[i] += "!"
            if pat[i] == "x":
                notes[i] = notes[i].rstrip("!")
            tr["notes"] = notes
        ST.log[t.name] = "%s %s" % (t.name, " ".join(tr["notes"])) if t.name in core.PITCHED \
            else "%s %s" % (t.name, tr["pat"])
        core.refresh()
        echo("%s step %d %s" % (t.name, i + 1, pat[i]))
    elif k == " ":
        echo(core.toggle_play())
    elif k == "[":
        sweep(t, 1 / 1.06)
    elif k == "]":
        sweep(t, 1.06)
    elif k == "{":
        tr["res"] = max(0.0, tr["res"] - 0.05)
        core.autorec_touch("%s.res" % t.name, tr["res"]); core.refresh(); echo("%s res %.2f" % (t.name, tr["res"]))
    elif k == "}":
        tr["res"] = min(0.98, tr["res"] + 0.05)
        core.autorec_touch("%s.res" % t.name, tr["res"]); core.refresh(); echo("%s res %.2f" % (t.name, tr["res"]))
    elif k == "-":
        bump("bpm", -1, 60, 220, "%g BPM")
    elif k == "=":
        bump("bpm", 1, 60, 220, "%g BPM")
    elif k == "_":
        bump("bpm", -10, 60, 220, "%g BPM")
    elif k == "+":
        bump("bpm", 10, 60, 220, "%g BPM")
    elif k == ",":
        bump("swing", -2, 0, 50, "swing %g%%")
    elif k == ".":
        bump("swing", 2, 0, 50, "swing %g%%")
    elif k == "z":
        ST.mark(); tr["mute"] = not tr["mute"]; core.refresh()
        echo("%s %s" % (t.name, "muted" if tr["mute"] else "unmuted"))
    elif k == "x":
        ST.mark(); tr["solo"] = not tr["solo"]; core.refresh()
        echo("%s %s" % (t.name, "solo" if tr["solo"] else "unsolo"))
    elif k == "n":
        echo(do("variation %s" % t.name) or "varied %s" % t.name)
    elif k == "T":
        now = time.time()
        _taps.append(now)
        while len(_taps) > 4 or (len(_taps) > 1 and now - _taps[0] > 3):
            _taps.pop(0)
        if len(_taps) > 1:
            ST.bpm = round(60.0 / ((_taps[-1] - _taps[0]) / (len(_taps) - 1)), 1)
            core.refresh()
        echo("tap %g BPM" % ST.bpm)
    elif k == "R":
        echo(REC.toggle())
    elif k == "A":
        echo(do("ab a") or "")
    elif k == "\x1a":
        echo(ST.undo_one())
    elif k == "\x19":
        echo(ST.redo_one())
    elif k == "\t":
        echo("view: perform")
    return True

# -------------------------------------------------------------------- loop


def hint(s):
    """teach.py owns this when present; these are the fallbacks."""
    try:
        from . import teach
        h = teach.hint(s)
        return h if h is not None else ""
    except Exception:
        pass
    if not any(t.active for t in s.tracks):
        return "empty — press : then `open warehouse` (or `songs` to see all 5)"
    if not s.playing:
        return "press space to play"
    if not any(t.active for t in s.tracks if t.name in ("hat", "oh")):
        return "no hats — press 2, then q e t u"
    if not s.recording:
        return "press R to record a take"
    return "recording to %s — press R to stop" % s.rec_name


def run():
    if os.name == "nt":
        os.system("")
    old = None
    if os.name != "nt":
        old = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")       # alt screen, hide cursor
    prev, flashed = [], False
    try:
        while True:
            w, h = shutil_size()
            k = read_key()
            hold_tick()
            s0 = core.snapshot(mode="cmd" if _cmd["on"] else "play",
                               cmdline=_cmd["buf"], complete=complete(_cmd["buf"]),
                               overlay=_overlay[0])
            if k is not None and not on_key(k, s0):
                break
            s = core.snapshot(mode="cmd" if _cmd["on"] else "play",
                              cmdline=_cmd["buf"], complete=complete(_cmd["buf"]),
                              overlay=_overlay[0])
            s = dataclasses.replace(s, hint=hint(s))
            if ST.blip is not None and not flashed:       # one white frame = sync mark
                sys.stdout.write("\x1b[?5h")
                flashed = True
            elif flashed and ST.blip is None:
                sys.stdout.write("\x1b[?5l")
                flashed = False
            rows = build(s, w, h)
            if len(prev) != len(rows):
                prev = [None] * len(rows)
                sys.stdout.write("\x1b[2J")
            for y, line in enumerate(rows):
                if prev[y] != line:
                    sys.stdout.write("\x1b[%d;1H\x1b[K%s" % (y + 1, line))
                    prev[y] = line
            sys.stdout.flush()
            time.sleep(1 / 30.0)
    except KeyboardInterrupt:
        pass
    finally:
        core.stop()
        if REC.on:
            REC.stop()
        sys.stdout.write("\x1b[?5l\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if old:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)


def shutil_size():
    try:
        s = os.get_terminal_size()
        return max(60, s.columns), max(16, s.lines)
    except OSError:
        return 100, 30
