"""Turn "a six minute peak-time track" into an actual arrangement.

A song is a walk along an energy curve. Sections get their content FROM THEIR
ROLE - an intro is thin because it is an intro, a break drops the drums because
that is what a break is - and one motif is developed across all of them so the
drop's bassline is recognisably the intro's, not a fresh roll of the dice.

That last part is the difference between a song and eight unrelated loops.
"""
import copy
import math
import random

from .contracts import COMMANDS, VOICES
from . import song as sm
from . import harmony as hm
from . import theory
from .theory import TEMPLATES, ROLE_BARS

# Energy curves. Each is a shape in 0..1 that the arrangement walks along.
CURVES = {
    "classic":      "a steady climb to one big drop, then a wind-down",
    "peaktime":     "straight in hard, sustained, brief break, higher drop",
    "hypnotic":     "slow monotonic rise, barely any release - the long stare",
    "journey":      "two drops with a deep break between them",
    "warmup":       "low and gradual, never fully lets go - opening set",
    "rollercoaster": "several peaks, each higher, short breaks between",
}

# The shapes (TEMPLATES) and the bars a role wants (ROLE_BARS) live in theory.py,
# the one place the browser composer also reads them from.


def _energy_for(role, position, shape):
    """A drop is always a drop. The curve decides only HOW hard, and later drops
    sit higher than earlier ones so the track goes somewhere."""
    base = {"intro": 0.15, "build": 0.55, "drop": 0.95, "break": 0.2,
            "verse": 0.5, "fill": 0.7, "outro": 0.2}.get(role, 0.5)
    if role == "drop":
        return min(1.0, 0.84 + 0.16 * position * shape)
    if role == "break":
        return max(0.05, base - 0.05 * position)
    return max(0.05, min(1.0, base + 0.2 * position * shape))


def _jsround(x):
    """Math.round: halves go up. Python's round() goes to even, and the browser
    composer must produce the same plan for the same inputs."""
    return int(math.floor(x + 0.5))


def _share(roles, bars):
    """Distribute `bars` across `roles` in proportion to what each wants, every
    section a multiple of 8 and never below 8. Phrasing is not negotiable, so the
    rounding remainder goes to the biggest section rather than being smeared."""
    if not roles:
        return []
    want = [ROLE_BARS.get(r, 16) for r in roles]
    tot = float(sum(want))
    out = [max(8, _jsround(bars * w / tot / 8.0) * 8) for w in want]
    guard = 0
    while sum(out) > bars and guard < 200:
        guard += 1
        i = out.index(max(out))
        if out[i] <= 8:
            break
        out[i] -= 8
    guard = 0
    while sum(out) < bars - 4 and guard < 200:
        guard += 1
        out[out.index(max(out))] += 8
    return out


def arrange(minutes=5.0, curve_name="classic", bpm=140.0, seed=None, drop_window=None):
    """[(role, bars)] whose total lands near `minutes`, with the first drop inside
    the genre's window.

    Solved rather than nudged. Nudging fought itself: growing the intro to reach
    the window pushed the length out, and trimming the length dragged the drop
    back out of the window. Decide up front how many bars belong BEFORE the drop -
    that is what the window specifies - and share the rest out after it. This is
    the browser composer's algorithm, line for line; qa checks they agree.
    """
    bars_total = max(32, _jsround(minutes * 60.0 / (240.0 / bpm) / 8.0) * 8)
    tpl = list(TEMPLATES.get(curve_name, TEMPLATES["classic"]))
    min_bars = len(tpl) * 8
    while min_bars > bars_total and len(tpl) > 4:
        del tpl[1]
        min_bars -= 8
    while min_bars < bars_total - 64 and len(tpl) < 22:
        tpl = tpl[:-1] + tpl[1:-1][-4:] + [tpl[-1]]
        min_bars = len(tpl) * 8

    mid = (drop_window[0] + drop_window[1]) / 2.0 if drop_window else 0.3

    # A long template has many post-drop sections, each needing 8 bars. For a
    # genre whose drop belongs late those minimums can eat the pre-drop budget and
    # drag the drop forward out of its window - then the template is too long for
    # this duration. Drop a repeated later section rather than compromise the shape.
    for _ in range(12):
        if "drop" not in tpl:
            break
        di = tpl.index("drop")
        pre = max(di * 8, _jsround(bars_total * mid / 8.0) * 8)
        if pre + (len(tpl) - di) * 8 <= bars_total:
            break
        if len(tpl) <= 5:
            break
        cut = -1
        for k in range(len(tpl) - 2, di, -1):
            if tpl[k] != "outro":
                cut = k
                break
        if cut < 0:
            break
        del tpl[cut]

    if "drop" not in tpl:
        return list(zip(tpl, _share(tpl, bars_total)))
    di = tpl.index("drop")
    pre = max(di * 8, _jsround(bars_total * mid / 8.0) * 8)
    post = max((len(tpl) - di) * 8, bars_total - pre)
    if pre + post > bars_total + 8:
        pre = max(di * 8, bars_total - post)
    pre_bars, post_bars = _share(tpl[:di], pre), _share(tpl[di:], post)
    return [(r, pre_bars[i] if i < di else post_bars[i - di]) for i, r in enumerate(tpl)]


def _uniq(plan):
    """intro, build, drop, drop2, break, drop3 ... - names you can type."""
    seen, out = {}, []
    for role, bars in plan:
        seen[role] = seen.get(role, 0) + 1
        out.append((role if seen[role] == 1 else "%s%d" % (role, seen[role]), role, bars))
    return out


def _voice(*names):
    """First registered voice from the candidates - never assume a module landed."""
    for n in names:
        if n in VOICES:
            return n
    return None


def compose_song(style="hardtechno", minutes=5.0, key=None, seed=None,
                 curve_name="classic", bpm=None):
    """Build a whole Song. Deterministic under seed."""
    from . import core
    r = random.Random(seed)
    key = key or r.choice(["a", "c", "d", "f", "g"])
    scale = r.choice(["minor", "minor", "minor", "phrygian"])

    # 1. base groove from the style pack, applied to a scratch state
    base = core.State()
    saved, core.ST = core.ST, base
    try:
        try:
            from . import gen
            for line in gen.style_cmd(base, [style]) or ():
                core.do(line, log=False)
        except Exception:
            for line in ("kick x...x...x...x...", "hat ..x...x...x...x.",
                         "clap ....x.......x..."):
                core.do(line, log=False)
    finally:
        core.ST = saved
    bpm = bpm or base.bpm

    # 2. one motif, developed across the whole song. This is the song's identity.
    motif = hm.motif_generate(r.randrange(1 << 30), 8,
                              r.choice(["static", "arch", "rising", "zigzag"]))

    plan = arrange(minutes, curve_name, bpm, seed, theory.genre(style)["drop_at"])
    named = _uniq(plan)
    shape = {"hypnotic": 1.0, "warmup": 0.4, "peaktime": 0.6}.get(curve_name, 0.8)
    energies = [_energy_for(role, i / float(max(1, len(named) - 1)), shape)
                for i, (_n, role, _b) in enumerate(named)]

    sections, order = {}, []
    for i, ((name, role, bars), energy) in enumerate(zip(named, energies)):
        sec = _section(name, role, bars, energy, base, motif, key, scale, bpm, r, i)
        sections[name] = sec
        order.append(name)

    sg = sm.Song(name="%s-%s" % (style, curve_name), bpm=bpm, swing=base.swing,
                 key=key, scale=scale, sections=sections, order=order,
                 meta={"style": style, "curve": curve_name, "seed": seed,
                       "generated": True})
    return sg


def _section(name, role, bars, energy, base, motif, key, scale, bpm, r, index):
    """Content follows the role. This is where a section becomes what it is."""
    tracks = copy.deepcopy(base.tracks)
    order = list(base.order)
    auto = []

    # the motif, developed for this section's energy
    m = motif
    if energy < 0.4:
        m = hm.thin(motif, 0.6)
    elif energy > 0.85:
        m = hm.densify(motif, 0.4)
    if index and r.random() < 0.35:
        m = hm.transpose(m, r.choice([-2, 2, 3]))
    if "bass" in tracks:
        tracks["bass"]["notes"] = hm.motif_to_tokens(m, key, scale, 1).split()
        tracks["bass"]["pat"] = "".join(
            "." if t == "." else ("X" if t.endswith("!") else "x")
            for t in tracks["bass"]["notes"])

    def silence(*names):
        for n in names:
            if n in tracks:
                tracks[n]["pat"] = "." * len(tracks[n]["pat"])

    def add(track, voice, pat, notes=None, **kw):
        if voice is None:
            return
        tr = tracks.setdefault(track, base.tracks.get(track) or _new(track))
        tr = copy.deepcopy(tr)
        tr.update({"voice": voice, "pat": pat})
        if notes:
            tr["notes"] = notes
        tr.update(kw)
        tracks[track] = tr
        if track not in order:
            order.append(track)

    def _new(t):
        from . import core
        return core.new_track(t)

    if role == "intro":
        silence("clap", "snare", "stab", "oh")
        if "bass" in tracks:
            silence("bass")
        if "hat" in tracks:
            tracks["hat"]["gain"] = 0.35
        if "perc" in tracks:
            tracks["perc"]["gain"] = 0.4
        if "kick" in tracks:
            tracks["kick"]["gain"] = 0.5         # an intro a DJ can mix into
        auto.append(sm.ramp("kick.gain", 0.3, 0.95, 0, bars, "linear"))
        auto.append(sm.ramp("hat.gain", 0.15, 0.7, 0, bars, "linear"))

    elif role == "build":
        silence("break")
        if "hat" in tracks:
            tracks["hat"]["pat"] = "x" * 16
        if "bass" in tracks:
            tracks["bass"]["fc"] = 300.0
        auto.append(sm.ramp("bass.fc", 260, 4200, 0, bars, "exp"))
        auto.append(sm.ramp("hat.gain", 0.6, 1.0, 0, bars, "linear"))
        rise = _voice("riser", "atmos", "noise_hit")
        if rise:
            add("riser", rise, "x" + "." * 15, gain=0.5)
            auto.append(sm.ramp("riser.gain", 0.2, 0.9, 0, bars, "exp"))
        sn = _voice("snare", "clap")
        if sn and bars >= 8:                          # the roll into the drop
            add("roll", sn, "." * (len(tracks.get("kick", {}).get("pat", "x" * 16)) - 4)
                + "x.xx", gain=0.5)

    elif role in ("drop", "peak"):
        if "bass" in tracks:
            tracks["bass"]["fc"] = 1200.0
            tracks["bass"]["sc"] = 0.8
        rum = _voice("rumble")
        if rum and energy > 0.8:
            add("rumble", rum, "x" + "." * 15, gain=0.55, sc=0.0)
        oh = _voice("oh")
        if oh:
            add("oh", oh, "......x.......x.", gain=0.7, sc=0.5)

    elif role == "break":
        silence("kick", "clap", "snare", "perc", "oh")
        pad = _voice("pad", "atmos", "stab")
        if pad:
            add("pad", pad, "x" + "." * 15,
                notes=[hm.degree_token(key, scale, 0, 2)] + ["."] * 15,
                gain=0.5, sc=0.0)
        if "bass" in tracks:
            tracks["bass"]["gain"] = 0.4
            tracks["bass"]["fc"] = 220.0
        auto.append(sm.ramp("bass.fc", 180, 900, 0, bars, "linear"))

    elif role == "outro":
        silence("stab", "clap", "bass")
        auto.append(sm.ramp("kick.fc", 12000, 500, max(0, bars // 2), bars, "exp"))
        for t in tracks.values():
            t["gain"] = t.get("gain", 1.0) * 0.8

    else:                                            # verse / fill
        if "bass" in tracks:
            tracks["bass"]["fc"] = 600.0

    # per-section density follows energy, so a repeat is never a photocopy
    if "hat" in tracks and role not in ("break", "intro"):
        pat = list(tracks["hat"]["pat"])
        want = 0.25 + 0.6 * energy
        for i in range(len(pat)):
            if pat[i] in ".-" and r.random() < (want - 0.3):
                pat[i] = "x"
        tracks["hat"]["pat"] = "".join(pat)

    sec = sm.Section(name, bars, tracks, order,
                     copy.deepcopy(base.master_fx), None, None, auto, role, energy)
    return sec


# ---------------------------------------------------------------- commands

def compose_cmd(state, args):
    """`compose <style> [minutes] [curve]` - builds a whole Song.

    SANCTIONED EXCEPTION to the return-commands rule: a Song is not expressible
    as a command string, so this assigns core.ST.song directly and returns a
    status line. Reported to the orchestrator rather than worked around.
    """
    from . import core
    import math
    style = args[0] if args else "hardtechno"
    try:                                     # 'compose x inf' / 'compose x nan' are keyboards, not requests
        minutes = float(args[1]) if len(args) > 1 else 5.0
    except ValueError:
        minutes = 5.0
    if not math.isfinite(minutes):
        minutes = 5.0
    minutes = min(20.0, max(0.5, minutes))
    cname = args[2] if len(args) > 2 else "classic"
    core.set_song(compose_song(style, minutes, curve_name=cname))
    sg = core.ST.song
    return "%s  %d sections  %d bars  %s  %s %s  |  %s" % (
        sg.name, len(sg.order), sg.total_bars(),
        "%d:%02d" % (int(sg.seconds()) // 60, int(sg.seconds()) % 60),
        sg.key, sg.scale, " ".join(sg.order))


def curves_cmd(state, args):
    return "  ".join("%s: %s" % (k, v) for k, v in CURVES.items())


COMMANDS.update({"compose": compose_cmd, "curves": curves_cmd})
