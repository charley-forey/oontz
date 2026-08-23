"""Generative techno: Euclidean rhythms, scale-aware melodies, groove templates,
and full style packs.

Every function here is a COMMANDS entry: f(state, args) -> list[str]. It never
touches `state` - it only reads it for context (an existing note to reuse, the
focused track) - and returns plain thud command strings. That is what keeps
generated music honest: run the strings through core.do() and you get exactly
what a human typing them would get, so it undoes and saves like anything else.

Owns: this file, and new songs/*.thud. Nothing else.
"""
import random

# Redefined rather than imported from core: two tuples of static data, and
# importing core here would make gen<->core a circular import at module load
# time (core.load_modules() imports gen while core itself is still being
# built). Not worth the coupling for two constants that never change.
TRACK_ORDER = ["kick", "hat", "oh", "clap", "snare", "perc", "bass", "stab"]
PITCHED = ("bass", "stab")
BASE_OCT = {"bass": 1, "stab": 2}
NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]

# ---------------------------------------------------------------- euclidean


def euclid(k, n, rotate=0):
    """Bjorklund: spread k hits as evenly as possible over n steps.

    e(4,16) -> four-on-the-floor, e(3,8) -> tresillo, e(7,16) -> a classic hat.
    The standard recursive algorithm (Toussaint): repeatedly fold the smaller
    remainder group into the larger one until what's left is 0 or 1 groups.
    """
    if n <= 0:
        return ""
    k = max(0, min(k, n))
    if k == 0:
        bits = [0] * n
    elif k == n:
        bits = [1] * n
    else:
        counts, remainders = [], [k]
        divisor = n - k
        lvl = 0
        while True:
            counts.append(divisor // remainders[lvl])
            remainders.append(divisor % remainders[lvl])
            divisor = remainders[lvl]
            lvl += 1
            if remainders[lvl] <= 1:
                break
        counts.append(divisor)
        bits = []

        def build(level):
            if level == -1:
                bits.append(0)
            elif level == -2:
                bits.append(1)
            else:
                for _ in range(counts[level]):
                    build(level - 1)
                if remainders[level] != 0:
                    build(level - 2)

        build(lvl)
        i = bits.index(1)                       # canonical form starts on a hit
        bits = bits[i:] + bits[:i]
    if rotate:
        r = rotate % n
        bits = bits[r:] + bits[:r]
    return "".join("x" if b else "." for b in bits)


def _default_root(state, track):
    """Reuse whatever note is already on the track, else a sane default."""
    for t in state.tracks[track].get("notes") or ():
        if t not in (".", "-"):
            return t.rstrip("~!")
    return "a%d" % BASE_OCT.get(track, 2)


def _pattern_or_notes(track, pat, state, accent_char="X"):
    """A euclid/density bit-string, rendered as the right kind of command:
    a bare pattern for drums, note tokens (reusing the track's root) for
    bass/stab - pitched tracks don't take a plain x./X. pattern."""
    if track not in PITCHED:
        return "%s %s" % (track, pat)
    root = _default_root(state, track)
    toks = [(root + "!" if c == accent_char else root) if c != "." else "."
            for c in pat]
    return "%s %s" % (track, " ".join(toks))


def euc_cmd(state, args):
    """`euc <track> <k> <n> [rot <r>]` -> one pattern (or notes) command."""
    track, k, n = args[0], int(args[1]), int(args[2])
    rot = int(args[args.index("rot") + 1]) if "rot" in args else 0
    return [_pattern_or_notes(track, euclid(k, n, rot), state)]

# ------------------------------------------------------------------- melody

# Interval sets, semitones above the root, within one octave.
SCALES = {
    "major":         (0, 2, 4, 5, 7, 9, 11),
    "minor":         (0, 2, 3, 5, 7, 8, 10),
    "dorian":        (0, 2, 3, 5, 7, 9, 10),
    "phrygian":      (0, 1, 3, 5, 7, 8, 10),      # the dark techno one
    "harmonicminor": (0, 2, 3, 5, 7, 8, 11),
    "pentatonic":    (0, 3, 5, 7, 10),            # minor pentatonic
}
SCALE_ALIAS = {"harmonic-minor": "harmonicminor", "harmonic_minor": "harmonicminor",
               "hminor": "harmonicminor", "minor-pentatonic": "pentatonic",
               "aeolian": "minor"}


def _root_pc(name):
    """Note letter (+ optional #/b) -> pitch class 0..11. No octave needed."""
    name = name.strip().lower()
    step = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}[name[0]]
    for ch in name[1:]:
        step += 1 if ch == "#" else (-1 if ch == "b" else 0)
    return step % 12


def _note(pc, octave):
    return NAMES[pc % 12] + str(max(0, min(8, octave)))


def melody_tokens(track, root, scale, length, note_p=0.78, rng_=None):
    """A scale-aware line: mostly stepwise, root-weighted, the odd octave
    jump, rests, slides, accents. Root-weighting is what makes it read as a
    bassline rather than a random walk - real basslines keep coming home.
    """
    rng_ = rng_ or random.Random()
    ivals = SCALES[SCALE_ALIAS.get(scale, scale)]
    rpc = _root_pc(root)
    oct0 = BASE_OCT.get(track, 2)
    deg, oc = 0, oct0
    toks = []
    for i in range(length):
        if rng_.random() > note_p:
            toks.append(".")
            continue
        if rng_.random() < 0.15:                 # pulled back to the root
            deg, oc = 0, oct0
        elif rng_.random() < 0.12:                # octave jump, same degree
            oc += rng_.choice((-1, 1))
        else:                                      # stepwise motion, mostly
            deg += rng_.choice((-2, -1, -1, 1, 1, 2))
            while deg < 0:
                deg += len(ivals)
                oc -= 1
            while deg >= len(ivals):
                deg -= len(ivals)
                oc += 1
        oc = max(0, min(6, oc))
        semi = rpc + ivals[deg]
        note = _note(semi % 12, oc + semi // 12)
        slide = bool(toks) and toks[-1] != "." and rng_.random() < 0.18
        accent = rng_.random() < (0.4 if i % 4 == 0 else 0.15)   # weight downbeats
        toks.append(note + ("~" if slide else "") + ("!" if accent else ""))
    if toks and toks[0] == ".":                   # ground bar one - it's a bassline
        toks[0] = _note(rpc, oct0) + "!"
    return toks


def melody_cmd(state, args):
    """`melody <track> <root> <scale> [length]` -> one notes command."""
    track, root, scale = args[0], args[1], args[2]
    length = int(args[3]) if len(args) > 3 else 16
    return ["%s %s" % (track, " ".join(melody_tokens(track, root, scale, length)))]

# ------------------------------------------------------------------- groove

# name -> (swing %, humanize ms). Swing shuffles odd 16ths; humanize jitters
# every hit independently - together they're what separates a loop from a
# take.
GROOVES = {
    "straight":  (0.0, 0.0),
    "swung-16":  (20.0, 4.0),     # classic swung 16ths - house, most techno
    "shuffle":   (33.0, 6.0),     # near-triplet, breaks and swung acid
    "hypnotic":  (8.0, 10.0),     # barely swung but loose - the Robert Hood pocket
    "rolling":   (14.0, 5.0),     # a push, not a shuffle - dub/industrial rumble
}


def groove_cmd(state, args):
    name = args[0] if args else "straight"
    sw, hum = GROOVES.get(name, GROOVES["straight"])
    return ["swing %g" % sw] + ["humanize %s %g" % (t, hum) for t in TRACK_ORDER]

# -------------------------------------------------------------- variation

# density and fillpat work on any track by falling back to euclid: k = how
# many hits, spread evenly. It's the same operator as a live "thin this out" /
# "roll a fill" - just a different k.


def density_cmd(state, args):
    """`density <track> <0..1>` -> thin/thicken toward that fraction of hits."""
    track, amount = args[0], max(0.0, min(1.0, float(args[1])))
    n = len(state.tracks[track]["pat"]) or 16
    k = round(n * amount)
    if track == "kick":
        k = max(1, k)                            # a kick with zero hits isn't a kick
    return [_pattern_or_notes(track, euclid(k, n), state)]


def variation_cmd(state, args):
    """`variation <track> [amount]` -> nudge some hits, never the kick's
    downbeat. amount is the fraction of steps eligible to flip (default 0.2).
    """
    track = args[0] if args else TRACK_ORDER[state.focus]
    amount = float(args[1]) if len(args) > 1 else 0.2
    pat = list(state.tracks[track]["pat"] or "." * 16)
    n = len(pat)
    idxs = list(range(n))
    if track == "kick" and 0 in idxs:
        idxs.remove(0)                           # protect the downbeat
    rng_ = random.Random()
    rng_.shuffle(idxs)
    for i in idxs[:max(1, round(n * amount))]:
        if pat[i] in ".-":
            pat[i] = rng_.choice("xxX")
        else:
            pat[i] = rng_.choice([".", "x", "X"])
    new_pat = "".join(pat)
    if track not in PITCHED:
        return ["%s %s" % (track, new_pat)]
    notes = list(state.tracks[track]["notes"]) or ["."] * n
    root = _default_root(state, track)
    toks = []
    for i, c in enumerate(new_pat):
        old = notes[i] if i < len(notes) else "."
        if c == ".":
            toks.append(".")
        elif old not in (".", "-"):                # keep the pitch, just re-flag it
            toks.append(old.rstrip("~!") + ("!" if c == "X" else ""))
        else:
            toks.append(root + ("!" if c == "X" else ""))
    return ["%s %s" % (track, " ".join(toks))]


def fill_cmd(state, args):
    """`fillpat <track>` -> a denser one-off variant that rolls into the last
    steps. Registered as "fillpat", not "fill" - arrange.py's section macro
    (build/drop/break/riser family) owns that verb in the timeline sense."""
    track = args[0] if args else TRACK_ORDER[state.focus]
    n = len(state.tracks[track]["pat"]) or 16
    bits = list(euclid(max(1, round(n * 0.75)), n))
    for i in range(max(0, n - 2), n):             # the roll: accent the last two
        bits[i] = "X" if bits[i] != "." else "X"
    return [_pattern_or_notes(track, "".join(bits), state)]

# --------------------------------------------------------------- style packs
#
# A style is DATA: tempo, groove, and per-track euclid/pat/melody + filter/
# sidechain defaults. style_cmd() is the only code; everything musical below
# is just numbers, so the taste lives in one place and is easy to audit.
#
# Track spec keys: euclid=(k,n[,rot]) | pat="literal" | melody=(root,scale[,len]),
# plus optional accent (bool, capitalizes euclid hits), density (melody note
# probability), filt=(mode,fc[,res]), tune, sc, gain, pan.

STYLES = {
    "techno": {
        "bpm": 132, "groove": "swung-16",
        "tracks": {
            "kick": {"euclid": (4, 16)},
            "hat":  {"euclid": (11, 16, 1), "filt": ("hp", 8500)},
            "oh":   {"euclid": (2, 16, 4), "gain": 0.6},
            "clap": {"pat": "....x.......x..."},
            "bass": {"melody": ("a", "minor", 16), "filt": ("lp", 420, 0.8), "sc": 0.7},
        },
    },
    "hardtechno": {
        "bpm": 150, "groove": "straight",
        "tracks": {
            "kick": {"euclid": (4, 16), "accent": True},
            "hat":  {"euclid": (7, 16), "filt": ("hp", 9500)},
            "perc": {"euclid": (5, 16), "tune": 500},
            "clap": {"euclid": (2, 16, 2), "accent": True},
            "bass": {"melody": ("a", "harmonicminor", 8), "filt": ("lp", 260, 0.9), "sc": 0.85},
        },
    },
    "acid": {
        "bpm": 134, "groove": "swung-16",
        "tracks": {
            "kick": {"euclid": (4, 16)},
            "hat":  {"euclid": (6, 16)},
            "clap": {"pat": "....x.......x..."},
            "bass": {"melody": ("a", "phrygian", 16), "filt": ("lp", 340, 0.94), "sc": 0.7},
        },
    },
    "industrial": {
        "bpm": 140, "groove": "rolling",
        "tracks": {
            "kick":  {"euclid": (5, 16), "accent": True},
            "hat":   {"euclid": (9, 16), "filt": ("hp", 11000), "tune": 11000},
            "perc":  {"euclid": (7, 16), "tune": 210},
            "snare": {"pat": "........x......."},
            "bass":  {"melody": ("e", "phrygian", 16), "filt": ("lp", 300, 0.92), "sc": 0.8},
        },
    },
    "minimal": {
        "bpm": 122, "groove": "hypnotic",
        "tracks": {
            "kick": {"euclid": (4, 16)},
            "hat":  {"euclid": (3, 16)},
            "perc": {"euclid": (2, 16), "tune": 780},
            "stab": {"melody": ("a", "pentatonic", 16), "density": 0.35,
                     "filt": ("lp", 1600, 0.5), "sc": 0.5},
        },
    },
    "dubtechno": {
        "bpm": 118, "groove": "rolling",
        "tracks": {
            "kick": {"euclid": (4, 16)},
            "hat":  {"euclid": (4, 16, 2), "filt": ("hp", 7000), "gain": 0.5},
            "stab": {"melody": ("a", "dorian", 16), "density": 0.3,
                     "filt": ("lp", 900, 0.3), "sc": 0.5},
        },
    },
    "breakbeat": {
        "bpm": 136, "groove": "shuffle",
        "tracks": {
            "kick":  {"euclid": (5, 16, 1)},
            "snare": {"pat": "....x...x.x....."},
            "hat":   {"euclid": (10, 16)},
            "perc":  {"euclid": (6, 16, 3), "tune": 400},
            "bass":  {"melody": ("a", "minor", 16), "filt": ("lp", 500, 0.6), "sc": 0.6},
        },
    },
    "house": {
        "bpm": 124, "groove": "swung-16",
        "tracks": {
            "kick": {"euclid": (4, 16)},
            "hat":  {"euclid": (8, 16, 1), "tune": 9000},
            "oh":   {"euclid": (4, 16, 2), "gain": 0.7},
            "clap": {"pat": "....x.......x..."},
            "bass": {"melody": ("a", "dorian", 16), "filt": ("lp", 700, 0.5), "sc": 0.5},
        },
    },
    "trance": {
        "bpm": 138, "groove": "straight",
        "tracks": {
            "kick": {"euclid": (4, 16)},
            "hat":  {"euclid": (12, 16, 1), "filt": ("hp", 8000)},
            "bass": {"melody": ("a", "minor", 16), "density": 0.9,
                     "filt": ("lp", 1200, 0.3), "sc": 0.4},
            "stab": {"melody": ("c", "major", 16), "density": 0.25,
                     "filt": ("lp", 3000, 0.2), "sc": 0.3},
        },
    },
    "hypnotic": {
        "bpm": 128, "groove": "hypnotic",
        "tracks": {
            "kick": {"euclid": (4, 16)},
            "perc": {"euclid": (5, 16, 2), "tune": 350},
            "hat":  {"euclid": (3, 16), "gain": 0.5},
            "bass": {"melody": ("a", "minor", 16), "density": 0.4,
                     "filt": ("lp", 500, 0.7), "sc": 0.6},
        },
    },
}


def _track_cmds(track, spec):
    cmds = []
    if "euclid" in spec:
        k, n, *rest = spec["euclid"]
        pat = euclid(k, n, rest[0] if rest else 0)
        if spec.get("accent"):
            pat = pat.replace("x", "X")
        cmds.append(_pattern_or_notes(track, pat, _SPEC_STATE))
    elif "pat" in spec:
        cmds.append("%s %s" % (track, spec["pat"]))
    elif "melody" in spec:
        root, scale, *rest = spec["melody"]
        length = rest[0] if rest else 16
        toks = melody_tokens(track, root, scale, length, spec.get("density", 0.78))
        cmds.append("%s %s" % (track, " ".join(toks)))
    if "filt" in spec:
        mode, fc, *r = spec["filt"]
        cmds.append("filter %s %s %g%s" % (track, mode, fc, (" res %g" % r[0]) if r else ""))
    if "tune" in spec:
        cmds.append("tune %s %g" % (track, spec["tune"]))
    if "sc" in spec:
        cmds.append("sidechain %s %g" % (track, spec["sc"]))
    if "gain" in spec:
        cmds.append("gain %s %g" % (track, spec["gain"]))
    if "pan" in spec:
        cmds.append("pan %s %g" % (track, spec["pan"]))
    return cmds


class _RootStub:
    """A stand-in `state` for style building: euclid hits on bass/stab in a
    style spec always start from the track's octave-default root (styles
    hand pitched tracks a real `melody` spec instead), so there is never a
    prior note to reuse - this just satisfies _pattern_or_notes' lookup."""
    tracks = {t: {"notes": ()} for t in TRACK_ORDER}


_SPEC_STATE = _RootStub()


def _style_cmds(spec):
    cmds = ["bpm %g" % spec["bpm"]] + groove_cmd(None, [spec.get("groove", "straight")])
    for track in TRACK_ORDER:
        if track in spec["tracks"]:
            cmds += _track_cmds(track, spec["tracks"][track])
    return cmds


def style_cmd(state, args):
    """`style <name>` -> the full command list that reconfigures the instrument.
    No name, or a name that isn't one of ours: list what's available rather
    than erroring - `style` on its own is the first thing a new user types."""
    name = args[0] if args else ""
    if name not in STYLES:
        return "styles: %s  (style <name> to load one)" % " ".join(sorted(STYLES))
    return _style_cmds(STYLES[name])


REGISTERED = {
    "euc": euc_cmd, "melody": melody_cmd, "groove": groove_cmd,
    "style": style_cmd, "density": density_cmd, "variation": variation_cmd,
    "fillpat": fill_cmd,          # not "fill" - arrange.py owns that verb
}
from .contracts import COMMANDS
COMMANDS.update(REGISTERED)

# ---------------------------------------------------------------------- demo

SONGS = {
    # filename (no collision with the starter songbook) -> (style, description)
    "concrete":       ("techno", "poured, driving techno - the euclidean default"),
    "sledgehammer":   ("hardtechno", "150bpm, accented four-on-the-floor, no mercy"),
    "acidrain":       ("acid", "phrygian 303 line, filter wide open"),
    "foundry":        ("industrial", "syncopated kick, metallic hats, dark bass"),
    "negativespace":  ("minimal", "sparse pentatonic stabs, mostly silence"),
    "subterranean":   ("dubtechno", "118bpm, dorian chord stabs, deep and slow"),
    "brokenglass":    ("breakbeat", "syncopated kick/snare, shuffled groove"),
    "basement":       ("house", "124bpm, warm dorian bassline, offbeat hats"),
    "horizon":        ("trance", "rolling 16th bass under a sustained major stab"),
    "tunnel":         ("hypnotic", "one loop, slowly mutating - the Hood pocket"),
}


def demo():
    import os
    import numpy as np
    from . import core
    from .voices import note_hz
    from .contracts import COLLISIONS

    # -- registry: we don't own "fill" (arrange.py's section macro does) ----
    assert "fill" not in REGISTERED and "fillpat" in REGISTERED, REGISTERED
    assert COLLISIONS == [], COLLISIONS

    # -- style: no name, or a bad one, is a listing, not an error -----------
    for bad in ([], ["nope"]):
        out = style_cmd(core.ST, bad)
        assert isinstance(out, str) and not out.startswith("?"), out
        for name in STYLES:
            assert name in out, (bad, out)

    # -- euclid: exact known results, then a full sweep ---------------------
    assert euclid(4, 16) == "x...x...x...x...", euclid(4, 16)
    assert euclid(3, 8) == "x..x..x.", euclid(3, 8)
    assert euclid(5, 8) == "x.xx.xx.", euclid(5, 8)          # canonical Bjorklund E(5,8)
    for n in range(1, 33):
        for k in range(0, n + 1):
            p = euclid(k, n)
            assert p.count("x") == k and len(p) == n, (k, n, p)

    # -- melody: every token parses, every pitch class is in-scale ----------
    for scale, ivals in SCALES.items():
        toks = melody_tokens("bass", "a", scale, 32, note_p=0.9, rng_=random.Random(scale))
        pcs = {(_root_pc("a") + i) % 12 for i in ivals}
        for t in toks:
            if t == ".":
                continue
            bare = t.rstrip("~!")
            note_hz(bare)                                    # raises if unparseable
            pc = NAMES.index(bare.rstrip("0123456789"))
            assert pc in pcs, (scale, t, pcs)

    # -- integration: every COMMANDS function's output must be real thud ----
    def apply_fresh(cmds):
        core.ST.tracks = {t: core.new_track(t) for t in core.TRACK_ORDER}
        core.ST.log.clear()
        for c in cmds:
            out = core.do(c)
            assert not (isinstance(out, str) and out.startswith("?")), (c, out)
        return core.render_bar()

    apply_fresh(euc_cmd(core.ST, ["kick", "5", "16"]))
    apply_fresh(euc_cmd(core.ST, ["hat", "7", "16", "rot", "2"]))
    apply_fresh(melody_cmd(core.ST, ["bass", "a", "minor", "16"]))
    apply_fresh(groove_cmd(core.ST, ["hypnotic"]))
    apply_fresh(["kick x...x...x...x...", "hat ..x...x...x...x."])
    apply_fresh(density_cmd(core.ST, ["hat", "0.5"]))
    apply_fresh(["kick x...x...x...x..."] + variation_cmd(core.ST, ["kick", "0.3"]))
    apply_fresh(["hat ..x...x...x...x."] + fill_cmd(core.ST, ["hat"]))

    results = {}
    for name, spec in STYLES.items():
        bar = apply_fresh(_style_cmds(spec))
        rms = float(np.sqrt((bar ** 2).mean()))
        peak = float(np.abs(bar).max())
        active = sorted(t for t in core.TRACK_ORDER if core.ST.tracks[t]["pat"].strip(".-"))
        assert rms > 0.01, "%s: rms %.4f too quiet" % (name, rms)
        assert peak <= 1.0, "%s: peak %.3f clips" % (name, peak)
        results[name] = (spec["bpm"], rms, peak, active, bar)

    names = list(results)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ba, bb = results[a][4], results[b][4]
            same = ba.shape == bb.shape and np.array_equal(ba, bb)
            assert not same, "%s and %s render identically" % (a, b)

    # -- write and verify the songbook ---------------------------------------
    os.makedirs("songs", exist_ok=True)
    for fname, (style, desc) in SONGS.items():
        path = "songs/%s.thud" % fname
        cmds = _style_cmds(STYLES[style])
        with open(path, "w", encoding="utf-8") as f:
            f.write("# %s - %s\n" % (fname, desc))
            f.write("\n".join(cmds) + "\n")
        core.do("open %s" % fname)
        bar = core.render_bar()
        rms = float(np.sqrt((bar ** 2).mean()))
        assert rms > 0.01, "%s: song too quiet after load" % fname

    return results


if __name__ == "__main__":
    # `python -m thud.gen` executes this file under the name "__main__"; it is
    # never given the name "thud.gen" in sys.modules. demo() below imports
    # core, whose load_modules() then imports "thud.gen" for real - a second,
    # separate execution of everything above, registering a second set of
    # (behaviorally identical but not identical-by-id) functions and tripping
    # the collision detector against ourselves. Alias the module we're already
    # running under its real name so that import is a no-op.
    import sys
    sys.modules.setdefault("thud.gen", sys.modules[__name__])
    results = demo()
    print("gen.py: all checks pass\n")
    for name, (bpm, rms, peak, active, _bar) in sorted(results.items()):
        print("  %-11s %5.0fbpm  rms %.3f  peak %.3f  tracks: %s" %
              (name, bpm, rms, peak, " ".join(active)))
    print("\nsongbook: %s" % " ".join(sorted(SONGS)))
