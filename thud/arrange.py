"""Song machinery: scenes, automation ramps, build/drop/break macros, a
section timeline, and sets. Owned entirely by this file - see the module
docstring at the bottom for the core.py hooks this still needs to actually
fire at bar boundaries; nothing here calls into core beyond reading ST.

THE RULE (from contracts.py): every COMMANDS function returns thud command
STRINGS - the same primitives a user could type (bpm, gain, filter, pattern
setters, ...) - never verbs of its own (scene/ramp/song/set/build/...) that
core.do() doesn't know yet. That's what lets `python -m thud.arrange` prove
every generated line actually parses against TODAY's core.do(), with zero
changes to core.py. Automations and macros register their own bookkeeping
in module-level dicts/lists here (SCENES, AUTOMATIONS, SONG, SETLIST) and
hand back only the primitive commands needed right now (an initial jump to
the ramp's start value, an immediate pattern change, ...); the rest of a
ramp's progression is delivered later, bar by bar, via automation_at().
"""
import os
from .contracts import COMMANDS
from . import core
from .core import TRACK_ORDER, PITCHED
from .term import fit, c, vlen, bar as term_bar

# ------------------------------------------------------------- automation

CURVES = {
    "linear": lambda t: t,
    # (k**t - 1)/(k-1): k=1 fixed so both ends land on exactly 0.0 and 1.0.
    "exp":    lambda t, k=8.0: (k ** t - 1) / (k - 1),
    "log":    lambda t, k=8.0: 1 - (k ** (1 - t) - 1) / (k - 1),   # exp mirrored
    "ease":   lambda t: t * t * (3 - 2 * t),                       # smoothstep
}

AUTOMATIONS = []   # list of {target, from, to, bars, curve, start}


def ramp_value(frm, to, bars, curve, t):
    if bars <= 1:                          # a 1-bar "ramp" is just a jump
        return to
    ratio = t / (bars - 1)                 # exactly 0.0 at t=0, exactly 1.0 at t=bars-1
    return frm + (to - frm) * CURVES[curve](ratio)


def _emit(tracks, target, v):
    """target -> the one primitive thud command that sets it to v now."""
    if target == "bpm":
        return "bpm %g" % v
    name, param = target.split(".", 1)
    tr = tracks[name]
    if param == "fc":
        return "filter %s %s %g res %g" % (name, tr["filt"] or "lp", v, tr["res"])
    if param == "res":
        return "filter %s %s %g res %g" % (name, tr["filt"] or "lp", tr["fc"] or 300.0, v)
    verb = {"gain": "gain", "pan": "pan", "tune": "tune",
            "sc": "sidechain", "hum": "humanize"}[param]
    return "%s %s %g" % (verb, name, v)


def _validate_target(tracks, target):
    if target == "bpm":
        return
    if "." not in target:
        raise ValueError("bad target %r (want track.param or bpm)" % target)
    name, param = target.split(".", 1)
    if name not in tracks:
        raise ValueError("no track %r" % name)
    if param not in ("gain", "pan", "tune", "sc", "hum", "fc", "res"):
        raise ValueError("no automatable param %r" % param)


def _ramp(cmds, tracks, target, frm, to, bars, curve, start):
    """Register an automation and append its start-value jump to cmds."""
    cmds.append(_emit(tracks, target, frm))
    AUTOMATIONS.append({"target": target, "from": frm, "to": to,
                         "bars": bars, "curve": curve, "start": start})


def automation_at(bar_index):
    """What to run AT this bar: every automation whose window covers it."""
    tracks = core.ST.tracks
    out = []
    for a in AUTOMATIONS:
        t = bar_index - a["start"]
        if 0 <= t < a["bars"]:
            out.append(_emit(tracks, a["target"], ramp_value(a["from"], a["to"], a["bars"], a["curve"], t)))
    return out


def ramp_cmd(state, args):
    """ramp bass.fc 300 4000 over 16 [curve exp]"""
    target = args[0]
    _validate_target(state.tracks, target)
    frm, to = float(args[1]), float(args[2])
    bars = int(args[args.index("over") + 1])
    curve = args[args.index("curve") + 1] if "curve" in args else "linear"
    if curve not in CURVES:
        raise ValueError("unknown curve %r, want %s" % (curve, "|".join(CURVES)))
    cmds = []
    _ramp(cmds, state.tracks, target, frm, to, bars, curve, state.bars)
    return cmds

# ------------------------------------------------------------------ scenes

# name -> list of primitive commands. A flat list (not a live diff) so that
# to_commands() can hand the whole thing back verbatim - see `scene define`.
SCENES = {}


def _capture(state):
    cmds = ["bpm %g" % state.bpm, "swing %g" % state.swing]
    for name in TRACK_ORDER:
        tr = state.tracks[name]
        if name in PITCHED:
            toks = tr["notes"] if tr["notes"] else ["."] * len(tr["pat"])
            cmds.append("%s %s" % (name, " ".join(toks)))
        else:
            cmds.append("%s %s" % (name, tr["pat"]))
        cmds.append("gain %s %g" % (name, tr["gain"]))
        cmds.append("pan %s %g" % (name, tr["pan"]))
        cmds.append("tune %s %g" % (name, tr["tune"]))
        cmds.append("sidechain %s %g" % (name, tr["sc"]))
        cmds.append("humanize %s %g" % (name, tr["hum"]))
        cmds.append("filter %s %s %g res %g" % (name, tr["filt"], tr["fc"], tr["res"])
                     if tr["filt"] else "filter %s off" % name)
        # ponytail: mute/solo are toggles in core (no absolute on/off), so
        # these only round-trip cleanly starting from a fresh/unmuted track.
        # A `mute NAME on|off` verb in core would remove this caveat.
        if tr["mute"]:
            cmds.append("mute %s" % name)
        if tr["solo"]:
            cmds.append("solo %s" % name)
    return cmds


def scene_cmd(state, args):
    if not args:
        return "scene save NAME | scene list | scene NAME"
    if args[0] == "save":
        SCENES[args[1]] = _capture(state)
        return "scene saved: %s (%d commands)" % (args[1], len(SCENES[args[1]]))
    if args[0] == "list":
        return "  ·  ".join(sorted(SCENES)) if SCENES else "no scenes"
    if args[0] == "define":            # internal form: what to_commands() writes
        name = args[1]
        SCENES[name] = [s.strip() for s in " ".join(args[2:]).split("|") if s.strip()]
        return "scene defined: %s" % name
    return scenes_to_commands(args[0])


def scenes_to_commands(name):
    return list(SCENES.get(name, []))

# --------------------------------------------------------------- macros

DEFAULT_BARS = {"build": 16, "drop": 1, "break": 8, "riser": 8, "fill": 1}


def build_cmd(state, args):
    """Filter opens, hats and snare thicken, loudness climbs into the drop."""
    bars = int(args[0]) if args else DEFAULT_BARS["build"]
    start, tr = state.bars, state.tracks
    cmds = ["hat " + "x" * 16, "snare " + "x" * 16]
    _ramp(cmds, tr, "bass.fc", tr["bass"]["fc"] or 300.0, 6000.0, bars, "exp", start)
    _ramp(cmds, tr, "hat.gain", tr["hat"]["gain"], 1.3, bars, "linear", start)
    _ramp(cmds, tr, "snare.gain", 0.15, 1.0, bars, "exp", start)
    return cmds


def drop_cmd(state, args):
    """Everything in: kick and bass centred and full, filters snap open."""
    bars = int(args[0]) if args else DEFAULT_BARS["drop"]
    start, tr = state.bars, state.tracks
    cmds = ["gain kick 1", "gain bass 1", "pan kick 0", "pan bass 0", "sidechain bass 0.65"]
    _ramp(cmds, tr, "bass.fc", tr["bass"]["fc"] or 300.0, 5000.0, max(1, bars), "exp", start)
    _ramp(cmds, tr, "kick.gain", tr["kick"]["gain"], 1.0, max(1, bars), "linear", start)
    return cmds


def break_cmd(state, args):
    """Drums out (kick/clap/snare silenced), hats thin, bass darkens."""
    bars = int(args[0]) if args else DEFAULT_BARS["break"]
    start, tr = state.bars, state.tracks
    cmds = ["kick " + "." * 16, "clap " + "." * 16, "snare " + "." * 16]
    _ramp(cmds, tr, "hat.gain", tr["hat"]["gain"], 0.3, bars, "linear", start)
    _ramp(cmds, tr, "bass.fc", tr["bass"]["fc"] or 4000.0, 250.0, bars, "log", start)
    return cmds


def riser_cmd(state, args):
    """Pitch/noise sweep up on perc, opening into the next section."""
    bars = int(args[0]) if args else DEFAULT_BARS["riser"]
    start, tr = state.bars, state.tracks
    cmds = ["perc " + "x" * 16]
    _ramp(cmds, tr, "perc.tune", tr["perc"]["tune"] or 300.0, 6000.0, bars, "exp", start)
    _ramp(cmds, tr, "perc.gain", tr["perc"]["gain"], 1.2, bars, "linear", start)
    return cmds


def fill_cmd(state, args):
    """A one-bar drum fill. bars is accepted for symmetry with the other
    macros, but a true multi-bar accelerating roll needs per-bar pattern
    changes the DSL can't express in a single returned command list -
    ponytail: fixed one-bar fill, upgrade if a real timeline needs more."""
    return ["snare xXxXxXxXxXxXxXxX", "perc x.x.x.x.x.x.x.x."]

# ------------------------------------------------------------- song timeline

SONG = []   # list of (name, bars)

_MACROS = {"build": build_cmd, "drop": drop_cmd, "break": break_cmd,
           "riser": riser_cmd, "fill": fill_cmd}


def song_cmd(state, args):
    """song intro 16, build 16, drop 32, break 8, drop 32"""
    global SONG
    if not args:
        return "song NAME bars, NAME bars, ..."
    sections = []
    for part in " ".join(args).split(","):
        toks = part.split()
        if toks:
            sections.append((toks[0], int(toks[1])))
    SONG = sections
    return "song set: %d sections, %d bars" % (len(SONG), total_bars())


def total_bars():
    return sum(bars for _, bars in SONG)


def _locate(bar):
    """(name, start, bars, bars_into, bars_left) for bar, clamped to the
    song's length. Chose CLAMP over wrap: an arrangement has a real end (a
    mixdown point); silently wrapping would replay a loop nobody asked for.
    Looping between arrangements is what `set` is for."""
    if not SONG:
        return None
    tot = total_bars()
    b = max(0, min(bar, tot - 1))
    acc = 0
    for name, bars in SONG:
        if b < acc + bars:
            return name, acc, bars, b - acc, bars - (b - acc) - 1
        acc += bars
    name, bars = SONG[-1]
    return name, tot - bars, bars, bars - 1, 0


def section_at(bar):
    loc = _locate(bar)
    if not loc:
        return "", 0, 0
    name, _start, _bars, into, left = loc
    return name, into, left


def _section_start_commands(name, bars):
    fn = _MACROS.get(name)
    if fn:
        return fn(core.ST, [str(bars)])
    if name in SCENES:
        return scenes_to_commands(name)
    return []


def commands_at_bar(bar):
    """What to run when the transport reaches bar: the macro/scene for
    whichever section starts exactly here, else nothing."""
    acc = 0
    for name, bars in SONG:
        if acc == bar:
            return _section_start_commands(name, bars)
        acc += bars
    return []


def timeline_str(bar, w):
    loc = _locate(bar)
    if not loc:
        return fit("no song", w)
    cur, start, bars, into, left = loc
    idx = acc = 0
    for i, (_name, bs) in enumerate(SONG):
        if acc == start:
            idx = i
            break
        acc += bs
    nxt = SONG[idx + 1][0] if idx + 1 < len(SONG) else None
    names = ["⟦%s⟧" % n.upper() if i == idx else n for i, (n, _) in enumerate(SONG)]
    crumbs = c(80, " ▸ ".join(names))
    frac = into / (bars - 1) if bars > 1 else 1.0
    meter = term_bar(frac, 12, 149)
    tail = "%d bars → %s" % (left, nxt or "end")
    return fit("%s   %s  %s" % (crumbs, meter, tail), w)

# ---------------------------------------------------------------------- sets

SETLIST = []   # list of (song_name, bars)


def _song_bpm(name):
    path = name if name.endswith(".thud") else "songs/%s.thud" % name
    try:
        for line in open(path, encoding="utf-8"):
            parts = line.split()
            if parts and parts[0] == "bpm":
                return float(parts[1])
    except OSError:
        pass
    return None


def _transition(state, i, bars):
    """Beatmatch into SETLIST[i]: ramp bpm to the target song's tempo, then
    hard-cut patterns on `open` and fade the new tracks in from silence.
    ponytail: thud is a single-deck engine - there is no second buffer to
    crossfade against, so this fakes it with a tempo ramp + fade-in rather
    than a real overlap. A second render buffer in core would fix that."""
    name, _bars = SETLIST[i]
    target_bpm = _song_bpm(name)
    cmds = []
    if target_bpm:
        _ramp(cmds, state.tracks, "bpm", state.bpm, target_bpm, bars, "linear", state.bars)
    cmds.append("open %s" % name)
    for tname in TRACK_ORDER:
        _ramp(cmds, state.tracks, "%s.gain" % tname, 0.0, 1.0, max(1, bars // 2), "ease", state.bars)
    return cmds


def set_cmd(state, args):
    if not args:
        return "set add NAME bars | set list | set go INDEX [bars]"
    if args[0] == "add":
        SETLIST.append((args[1], int(args[2])))
        return "set: added %s (%d bars), %d total" % (args[1], int(args[2]), len(SETLIST))
    if args[0] == "list":
        return "  ·  ".join("%s(%d)" % p for p in SETLIST) if SETLIST else "empty set"
    if args[0] == "go":
        return _transition(state, int(args[1]), int(args[2]) if len(args) > 2 else 8)
    raise ValueError("unknown set subcommand %r" % args[0])

# --------------------------------------------------------------- serialisation


def to_commands():
    """Everything this module knows, as plain lines a .thud file can hold.
    Needs the COMMANDS-dispatch hook below before load() can replay them;
    until then they're inert text, same as typing an unwired verb today."""
    out = []
    for name, cmds in SCENES.items():
        out.append("scene define %s %s" % (name, " | ".join(cmds)))
    for a in AUTOMATIONS:
        out.append("ramp %s %g %g over %d curve %s" %
                    (a["target"], a["from"], a["to"], a["bars"], a["curve"]))
    if SONG:
        out.append("song " + ", ".join("%s %d" % p for p in SONG))
    for name, bars in SETLIST:
        out.append("set add %s %d" % (name, bars))
    return out


COMMANDS.update({"scene": scene_cmd, "ramp": ramp_cmd, "build": build_cmd,
                 "drop": drop_cmd, "break": break_cmd, "riser": riser_cmd,
                 "fill": fill_cmd, "song": song_cmd, "set": set_cmd})

# --------------------------------------------------------------------- demo


def demo():
    import numpy as np

    # -- ramp math: exact endpoints, monotonic in between --------------
    lin = [ramp_value(300, 4000, 16, "linear", t) for t in range(16)]
    assert lin[0] == 300.0 and lin[15] == 4000.0, lin
    assert all(b >= a for a, b in zip(lin, lin[1:])), "linear ramp not monotonic"

    exp = [ramp_value(300, 4000, 16, "exp", t) for t in range(16)]
    assert exp[0] == 300.0 and exp[15] == 4000.0, exp
    assert all(b >= a for a, b in zip(exp, exp[1:])), "exp ramp not monotonic"

    for curve in CURVES:
        v = [ramp_value(10, 20, 8, curve, t) for t in range(8)]
        assert v[0] == 10.0 and v[7] == 20.0, (curve, v)

    # -- song timeline ----------------------------------------------------
    global SONG
    SONG = []
    song_cmd(core.ST, ["intro", "16,", "build", "16,", "drop", "32"])
    assert total_bars() == 64, total_bars()
    assert section_at(0)[0] == "intro", section_at(0)
    assert section_at(16)[0] == "build", section_at(16)
    assert section_at(63)[0] == "drop", section_at(63)
    name, into, left = section_at(64)             # clamps to the last bar of the song
    assert (name, into, left) == ("drop", 31, 0), section_at(64)

    # -- reset the engine to a known, fresh state for everything below ---
    core.ST.tracks = {t: core.new_track(t) for t in TRACK_ORDER}
    core.ST.bpm, core.ST.swing, core.ST.bars = 132.0, 6.0, 0
    core.ST.log.clear()
    core.do("kick X...x...X...x..x")
    core.do("hat ..x...x...x.x.x.")
    core.do("bass a1! . a1~ . c2 . a1 . g1! . a1~ . c2 . d2 .")
    core.do("filter bass lp 420 res 0.8")

    # -- every command string any function returns actually parses ------
    def check_all(cmds):
        for line in cmds:
            out = core.do(line, log=False)
            assert not (isinstance(out, str) and out.startswith("?")), \
                "did not parse: %r -> %r" % (line, out)

    SETLIST.append(("warehouse", 64))              # for `set go`, exercised below
    batches = [
        ramp_cmd(core.ST, ["bass.fc", "300", "4000", "over", "16", "curve", "exp"]),
        build_cmd(core.ST, ["8"]), drop_cmd(core.ST, ["1"]), break_cmd(core.ST, ["4"]),
        riser_cmd(core.ST, ["4"]), fill_cmd(core.ST, ["1"]),
        automation_at(0), automation_at(3), automation_at(15),
        [scene_cmd(core.ST, ["save", "check"])] and [],   # side effect only, not a cmd batch
        scenes_to_commands("check"),
        _transition(core.ST, 0, 4),
    ]
    for b in batches:
        check_all(b)
    song_cmd(core.ST, ["intro", "4,", "build", "4"])
    for bar in (0, 4):
        check_all(commands_at_bar(bar))

    # -- scenes round-trip exactly ---------------------------------------
    core.ST.tracks = {t: core.new_track(t) for t in TRACK_ORDER}
    core.do("kick x...x...x...x...")
    core.do("bass a1 . c2 . a1 . g1 . a1 . c2 . a1 . g1 .")
    core.do("gain bass 0.8")
    core.do("filter bass lp 900 res 0.7")
    scene_cmd(core.ST, ["save", "snap1"])
    before = core.render_bar()
    core.do("kick X...............")               # mutate away from the snapshot
    core.do("gain bass 0.2")
    core.do("filter bass hp 2000")
    assert not np.array_equal(before, core.render_bar()), "mutation had no effect (bad test)"
    for line in scenes_to_commands("snap1"):
        core.do(line)
    after = core.render_bar()
    assert np.array_equal(before, after), "scene replay is not byte-identical"

    # -- serialisation: to_commands() also all parses --------------------
    check_all([l for l in to_commands() if not l.startswith(("scene define", "ramp ", "song ", "set "))])

    # -- timeline_str is exactly w visible columns ------------------------
    for w in (20, 40, 80, 120):
        for bar in (0, 4, 7):
            s = timeline_str(bar, w)
            assert core.ui.vlen(s) == w, (w, bar, core.ui.vlen(s), s)

    return ("arrange ok  ·  ramps exact+monotonic  ·  song 64 bars  ·  %d parse checks"
            "  ·  scene round-trip byte-identical  ·  timeline widths exact"
            % sum(len(b) for b in batches))


if __name__ == "__main__":
    print(demo())
