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

from . import core
from .core import ST, do, echo, complete, CMDS, TRACK_ORDER, REC

if os.name == "nt":
    import msvcrt
else:
    import tty
    import termios
    import select

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
    db = -48.0 if s.peak <= 0.004 else 20 * math.log10(s.peak)
    n = int(max(0.0, min(1.0, (db + 48) / 48)) * (w - 26))
    col = 196 if db > -1 else (214 if db > -6 else 78)
    bar = c(col, "█" * n) + DIM + "░" * (w - 26 - n) + OFF
    return fit("  " + c(244, "master ") + bar + c(250, " %+5.1f dB" % db), w)


def track_row(t, i, s, w):
    col = COL.get(t.name, 250)
    sel = "▸" if i == s.focus else " "
    tag = "%s%d %-5s" % (sel, i + 1, t.name)
    tag = c(231 if i == s.focus else col, tag)
    cells = []
    for j, ch in enumerate(t.pat):
        glyph = "·" if ch in ".-" else "█"
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
    """Context-sensitive: only the keys that do something right now."""
    t = s.tracks[s.focus]
    if s.mode == "cmd":
        items = [("Tab", "complete"), ("Enter", "run"), ("Esc", "back"), ("?", "keys")]
    else:
        items = [("1-8", "track"), (STEP_KEYS[:4] + "..", "steps"), ("spc", "play"),
                 ("[ ]", "cutoff" if t.name in core.PITCHED else "filter"),
                 ("z x", "mute solo"), ("n", "vary"), ("R", "rec"),
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


def build(s, w, h):
    if s.overlay == "help":
        return help_page(w, h)
    rows = [header(s, w), master_bar(s, w), fit(c(238, "├" + "─" * (w - 2) + "┤"), w)]
    for i, t in enumerate(s.tracks):
        rows.append(track_row(t, i, s, w))
    while len(rows) < h - 4:
        rows.append(" " * w)
    rows = rows[:h - 4]
    rows.append(fit(c(238, "├" + "─" * (w - 2) + "┤"), w))
    rows.append(legend(s, w))
    rows.append(status(s, w))
    rows.append(cmdline(s, w))
    return rows[:h]

# ------------------------------------------------------------------- input

_cmd = {"buf": "", "on": False}
_overlay = [""]
_taps = []


def sweep(t, mult):
    tr = ST.tracks[t.name]
    if t.name in core.PITCHED:
        tr["fc"] = max(40.0, min(18000.0, (tr["fc"] or 350.0) * mult))
        core.refresh()
        return echo("%s cutoff %d Hz" % (t.name, tr["fc"]))
    if not tr["filt"]:
        tr["filt"] = "lp"
        tr["fc"] = tr["fc"] or 8000.0
    tr["fc"] = max(40.0, min(18000.0, tr["fc"] * mult))
    core.refresh()
    echo("%s %s %d Hz" % (t.name, tr["filt"], tr["fc"]))


def bump(attr, d, lo, hi, fmt):
    setattr(ST, attr, max(lo, min(hi, getattr(ST, attr) + d)))
    core.refresh()
    echo(fmt % getattr(ST, attr))


def on_key(k, s):
    """Returns False to quit."""
    if _overlay[0]:
        _overlay[0] = ""
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

    t = s.tracks[ST.focus]
    tr = ST.tracks[t.name]

    if k == ":":
        _cmd["on"], _cmd["buf"] = True, ""
    elif k == "?":
        _overlay[0] = "help"
    elif k == "\x03":
        return False
    elif k in "12345678":
        ST.focus = int(k) - 1
        echo("focus %s" % TRACK_ORDER[ST.focus])
    elif k in STEP_KEYS:
        i = STEP_KEYS.index(k)
        pat = list(tr["pat"].ljust(16, ".")[:16])
        pat[i] = {".": "x", "x": "X", "X": "."}[pat[i] if pat[i] in ".xX" else "."]
        ST.mark()
        tr["pat"] = "".join(pat)
        if t.name in core.PITCHED:                       # keep notes aligned
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
        tr["res"] = max(0.0, tr["res"] - 0.05); core.refresh(); echo("%s res %.2f" % (t.name, tr["res"]))
    elif k == "}":
        tr["res"] = min(0.98, tr["res"] + 0.05); core.refresh(); echo("%s res %.2f" % (t.name, tr["res"]))
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
    """Minimal M1 teaching line. teach.py (A9) replaces this wholesale."""
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
