"""The whole teaching layer: hint, legend, help, why, lesson, suggest, report.

Every function here is a pure function of a Snapshot (plus, for a couple of them,
a small extra argument). No I/O, no globals, nothing hidden. ui.py already calls
hint(s), legend(s, w) and help_page(s, w, h) with a try/except fallback, so those
three signatures are load-bearing - don't change them.

IMPORT SAFETY: core.py's own load_modules() imports this module *during* core's
own init, before core.echo/core.snapshot exist yet. ui.py's module level does
`from .core import ..., echo, ...`, which would blow up if reached at that point.
So this module must never `import ui` (or anything that imports ui) at module
level - only lazily, inside demo(), long after everything is loaded. STEP_KEYS is
therefore a local literal, checked against the real ui.STEP_KEYS in the self-test.
"""
import math
import collections
import dataclasses

from . import core
from .contracts import Snapshot, TrackView

STEP_KEYS = "qwertyuiasdfghjk"           # must equal ui.STEP_KEYS - checked in demo()

# ---------------------------------------------------------------------- hint

NO_HATS_BAR = 4          # bars of playing-with-no-hats before we say something
GOOD_BAR = 8              # bars of "it's going well" before we suggest recording
LOUD_RMS = 0.02           # rms above which a track counts as "audibly on"
PEAK_GOOD_LO = 0.05
PEAK_GOOD_HI = 0.95
PEAK_CLIP = 0.95


def _pitched(t):
    """Best guess at "this track plays notes", from Snapshot data alone.

    core.is_pitched() is the real answer but needs the internal voice registry -
    not visible from a TrackView. Notes being populated is the honest signal;
    the name fallback covers a freshly-loaded pitched track with no notes yet.
    """
    return bool(t.notes) or t.name in core.PITCHED


def hint(snapshot):
    """The one always-visible suggestion. None means "nothing useful to say"."""
    s = snapshot
    tracks = s.tracks
    if not tracks or not any(t.active for t in tracks):
        return "empty — press : then `open warehouse` to load a song (or `songs` to see all 5)"
    if not s.playing:
        return "press space to play"

    by = {t.name: t for t in tracks}
    hats_on = any(t.active for t in tracks if t.name in ("hat", "oh"))
    if not hats_on and s.bar >= NO_HATS_BAR:
        return "no hats yet — press 2 for the hat track, then q e t u to punch in a pattern"

    kick, bass = by.get("kick"), by.get("bass")
    if (kick and bass and kick.active and bass.active
            and kick.rms > LOUD_RMS and bass.rms > LOUD_RMS
            and bass.sc < 0.05 and bass.filt != "hp"):
        return ("kick and bass are colliding down low — try `sidechain bass 0.7` to duck "
                "the bass under each kick, or `filter bass hp 100` to clear the sub for it")

    if bass and bass.active and bass.sc < 0.05:
        return ("bass has no sidechain — try `sidechain bass 0.7`: it ducks the bass a "
                "touch on every kick hit so the two don't mush together down low")

    good = (not s.recording and s.bar >= GOOD_BAR
            and PEAK_GOOD_LO < s.peak < PEAK_GOOD_HI
            and sum(t.active for t in tracks) >= 3)
    if good:
        return "sounding good — press R to record a take"

    if s.recording:
        return "recording to %s — press R to stop" % s.rec_name

    if s.peak >= PEAK_CLIP:
        loud = max((t for t in tracks if t.active), key=lambda t: t.rms, default=None)
        name = loud.name if loud else tracks[s.focus % len(tracks)].name
        return "master is riding near clipping — try `gain %s 0.8`" % name

    return None

# -------------------------------------------------------------------- legend


def _pack(items, w, prefix="  "):
    """Greedily fit key/label pairs left to right, dropping from the end - never
    mid-word - when they don't fit. c()/vlen()/fit() come straight from term.py
    conventions; duplicated here rather than imported, since importing ui or
    term.c-users at module level is exactly the trap this file has to avoid."""
    from .term import c, vlen, fit
    sep = c(238, " · ")
    sep_w = vlen(sep)
    parts, used = [], vlen(prefix)
    for k, v in items:
        piece = c(117, k) + " " + c(245, v)
        add = vlen(piece) + (sep_w if parts else 0)
        if used + add > w:
            break
        parts.append(piece)
        used += add
    return fit(prefix + sep.join(parts), w)


def legend(snapshot, w):
    """The always-on key bar: only the keys that do something right now."""
    s = snapshot
    if s.mode == "cmd":
        return _pack([("Tab", "complete"), ("Enter", "run"), ("Esc", "cancel"),
                      ("?", "keys")], w)
    if not s.tracks:
        return _pack([(":", "open a song"), ("?", "all keys")], w)

    t = s.tracks[s.focus % len(s.tracks)]
    pitched = _pitched(t)
    hatlike = t.name in ("hat", "oh")
    sweep_label = "cutoff" if pitched else ("tone" if hatlike else "filter")

    items = [("1-8", "track"), (STEP_KEYS[:4] + "..", "steps"), ("spc", "play"),
             ("[ ]", sweep_label)]
    if hatlike:
        other = "oh" if t.name == "hat" else "hat"
        idx = next((i for i, tt in enumerate(s.tracks) if tt.name == other), None)
        if idx is not None:
            items.append((str(idx + 1), "open hat" if other == "oh" else "closed hat"))
    items.append(("z x", "mute solo"))
    items += [("{ }", "res"), ("n", "vary"), ("R", "rec"),
              (":", "notes  ~slide !accent" if pitched else "cmd"),
              ("?", "all keys")]
    return _pack(items, w)

# ---------------------------------------------------------------- help_page


def _key_rows():
    return [
        ("1-8", "focus a track"),
        (STEP_KEYS[:8] + " / " + STEP_KEYS[8:], "toggle steps 1-8 / 9-16 of the focused track"),
        ("space", "play / stop"),
        ("[ / ]", "cutoff or filter, down / up (hold to sweep)"),
        ("{ / }", "resonance down / up"),
        ("- / =", "bpm -1 / +1   (_ / + for -10 / +10)"),
        (", / .", "swing down / up"),
        ("z / x", "mute / solo the focused track"),
        ("n", "variation — nudge a couple of steps at random"),
        ("T", "tap tempo, tap it a few times"),
        ("R", "start / stop recording a take"),
        ("A", "A/B compare — store, then swap"),
        ("ctrl+z / ctrl+y", "undo / redo"),
        (":", "command mode — type any command below"),
        ("?", "this screen"),
    ]


def _cmd_rows():
    """Sourced from core.CMDS at call time, so this can never drift out of date."""
    return [("%s (%s)" % (name, alias or "-"), help)
            for name, (_fn, alias, help) in sorted(core.CMDS.items())]


def _pattern_rows():
    return [
        ("kick x...x...x...x...", "x = hit, X = accent, . = rest"),
        ("bass a1 . a1~ c2!", "~ = slide into the next note, ! = accent"),
        ("any length works", "5 steps against a 16-step kick is a polymeter, for free"),
    ]


def help_page(snapshot, w, h, page=0):
    """The full `?` overlay. Paginates and says so if it doesn't fit in h lines."""
    from .term import c, fit
    body = ["", "  " + c(51, "OONTZ — every key"), ""]
    for title, rows in (("PLAY", _key_rows()), ("COMMANDS", _cmd_rows()),
                        ("PATTERNS", _pattern_rows())):
        body.append("  " + c(226, title))
        for k, v in rows:
            body.append("    %s  %s" % (c(117, "%-20s" % k), c(245, v)))
        body.append("")
    body.append("  " + c(240, "any key closes this"))
    lines = [fit(l, w) for l in body]

    if len(lines) <= h:
        return lines[:h]
    per = max(1, h - 1)
    total = -(-len(lines) // per)                    # ceil
    page = max(0, min(page, total - 1))
    chunk = lines[page * per:(page + 1) * per]
    chunk.append(fit("  page %d/%d — press ? again for more" % (page + 1, total), w))
    return chunk[:h]

# --------------------------------------------------------------------- why

_WHY_ALIAS = {"sc": "sidechain", "hum": "humanize", "filt": "filter",
              "fc": "cutoff", "pat": "pattern", "res": "resonance"}

WHY = {
    "resonance": ("Resonance boosts the frequencies right at the cutoff before the filter "
                  "rolls them off. Low (0.2-0.4) just softens the edge. High (0.8+) makes the "
                  "filter ring at the cutoff - that ringing IS the acid squelch. Push it past "
                  "~0.9 on a lowpass and it starts to self-oscillate, almost singing on its own."),
    "cutoff": ("Cutoff is the frequency where the filter starts working. Raise it on a lowpass "
               "and the sound gets brighter, more top end let through; lower it and it gets "
               "darker, muffled. It's the one knob that turns a static pattern into a filter "
               "sweep - sweep it slowly and the whole room feels it build."),
    "lowpass": ("Lowpass lets the lows through and rolls off everything above the cutoff. It's "
                "the muffled-to-bright knob: closed cutoff sounds like it's behind a wall, open "
                "cutoff lets it breathe. The classic acid/techno filter."),
    "highpass": ("Highpass is the opposite: lets the highs through, cuts everything below the "
                 "cutoff. Use it to carve room out of a low end - `filter bass hp 100` removes "
                 "the mud below 100Hz so the kick has the sub to itself."),
    "bandpass": ("Bandpass only lets a narrow window of frequencies through, cutting above and "
                 "below. It's a telephone/radio effect - thin and focused. Good for a stab you "
                 "want to sit in one spot without fighting anything else."),
    "sidechain": ("Sidechain ducks a track's volume every time the kick hits, then lets it back "
                  "up before the next one. It's the pumping techno sound, and practically it's "
                  "how kick and bass share the same low end without turning to mud. "
                  "`sidechain bass 0.7` ducks bass by 70% on every kick."),
    "swing": ("Swing delays every other 16th step, so the groove limps instead of marching in a "
              "straight grid. 0% is dead straight (hard techno); 15-25% starts to feel like a "
              "shuffle; much higher gets drunk and lopsided fast."),
    "accent": ("An accent - capital X in a pattern, or ! after a note - hits louder and sharper "
               "than a normal step. It's how a flat 16 steps gets a pulse: ears lock onto the "
               "loud ones and the pattern starts to groove instead of just ticking."),
    "slide": ("A slide - ~ after a note - glides the pitch from the previous note into this one "
              "instead of jumping. It's the wet, vocal-ish glide in acid basslines; the 303 sound "
              "is basically slides plus resonance."),
    "humanize": ("Humanize adds small random timing jitter, in ms, to every hit, so the pattern "
                 "isn't robotically exact. A little (2-5ms) feels loose and human; a lot starts "
                 "to sound drunk. Zero is a machine - techno often wants the machine."),
    "gain": ("Gain is a track's volume, a plain multiplier. 1.0 is unity, lower turns it down, "
             "higher turns it up - but watch the master meter, pushing several tracks past 1.0 "
             "is how you clip."),
    "pan": ("Pan moves a track left/right in the stereo field. -1 is hard left, 0 centre, 1 hard "
            "right. Spreading tracks out gives everything room instead of piling up in the middle."),
    "decay": ("Decay is how fast a sound dies away after it's triggered. Short = tight and "
              "clicky (closed hats, techno kicks); long = washy and sustained (open hats, pads). "
              "The difference between a knock and a ring."),
    "tune": ("Tune sets a voice's pitch or tone centre. On a melodic track (bass/stab) it's the "
             "base note; on a noise-based track (hat/perc) it shifts the whole timbre brighter "
             "or darker."),
    "bpm": ("BPM is the tempo - beats per minute, one beat per quarter note. Techno usually "
            "lives 125-145; higher feels relentless, lower feels heavier and more spacious."),
    "euclidean": ("A euclidean rhythm spreads N hits as evenly as possible across a pattern's "
                  "steps - the same maths that makes clock gears mesh evenly. It's why 5 hits "
                  "against 16 steps still feels danceable instead of random: they're spaced as "
                  "evenly as 5 can go into 16."),
    "polymeter": ("Polymeter is two patterns of different lengths looping at the same time - a "
                  "5-step bassline against a 16-step kick, say. They only realign every 80 "
                  "steps, so the same two patterns keep sounding like new combinations. oontz "
                  "gives you this for free: just make a track's pattern a different length."),
    "headroom": ("Headroom is the gap between how loud you're playing and 0dB, where things "
                 "clip. Keep a few dB of it - mix a bit under full scale - so accents and "
                 "buildups have somewhere to go without distorting."),
    "clipping": ("Clipping is the signal trying to go louder than 0dB and getting flattened "
                 "instead - it sounds harsh and crackly. If the master meter is pinned red, turn "
                 "something down, usually the loudest track's gain, not everything at once."),
    "sub": "20-60Hz - sub bass. Felt more than heard on small speakers; kick and bass fundamentals live here. Too much and a mix sounds boomy on a real system.",
    "bass": "60-250Hz - low-mid weight and warmth, where basslines live. Together with sub, this is the band that turns to mud fastest when kick and bass overlap - what sidechain and highpass are for.",
    "low-mid": "250-800Hz - body and honk. Boxy or congested if this band gets crowded; clashing pads and stabs usually fight here.",
    "mid": "800-2500Hz - where most instruments and vocals sit, and where the ear is most sensitive. Small changes here are loud changes.",
    "presence": "2500-8000Hz - bite and attack, the band that cuts through a club system. Hats and claps live up here; too much gets harsh and fatiguing.",
    "air": "8000-20000Hz - shimmer and openness. Open hats and cymbal wash live here. Too little sounds shut in a box; too much sounds thin and hissy.",
    "filter": ("Filter shapes tone by cutting frequencies above (lowpass), below (highpass), or "
               "both sides of (bandpass) the cutoff. `filter bass lp 420 res 0.8` is a lowpass "
               "at 420Hz, fairly resonant."),
    "mute": "Mute silences a track completely without losing its pattern - flip it back on any time. Good for building a track up piece by piece.",
    "solo": "Solo silences every other track so you hear just this one. Good for checking a sound is clean before bringing it back into the mix.",
    "play": "Play/stop starts and stops the transport. oontz always keeps looping the current bar; play just starts the loop.",
    "stop": "Stops playback. The pattern is still there, ready to resume from the top of the bar.",
    "rec": "Starts or stops recording exactly what you hear to a .wav in takes/, plus a .oontz alongside it so the same session can be reloaded or handed to anyone.",
    "songs": "Lists the starter songbook in songs/ - ready-made templates to load and learn from or build on top of.",
    "open": "Loads a song by name from songs/ (or a full .oontz path), replacing the current session.",
    "save": "Writes the current session - tempo, patterns, every command that shaped it - to a .oontz file you can reload later or hand to someone.",
    "load": "Reads a .oontz file and replays its commands to rebuild that exact session.",
    "render": "Renders the current pattern offline to a .wav without needing to play it live - useful for quick exports.",
    "ab": "A/B stores the current session in a slot, then swaps it back on the next call - a quick way to compare two versions and pick the one that's actually better.",
    "undo": "Steps back one edit. Every pattern or parameter change is undoable, so mistakes are free.",
    "redo": "Steps forward again after an undo.",
    "gen": "Generates a starting pattern (acid/techno/minimal) so you're never starting from silence - a sketch to edit, not a final answer.",
    "variation": "Mutates a couple of steps in a pattern at random - a quick way to keep a loop moving without hand-editing every step.",
    "pattern": "A pattern is characters, any length: x = hit, X = accent (louder), . or - = rest. Any length works - a 5-step pattern against a 16-step kick is a polymeter for free.",
    "notes": "Notes are the pitches a melodic track (bass/stab) plays per step, e.g. `a1 . a1~ c2!` - note name, ~ to slide from the previous note, ! to accent.",
    "view": "View switches which panel fills the middle of the screen - pattern grid, spectrum, scope, whatever's registered. perform is always there.",
    "voice": "Voice points a track at a different sound engine - same pattern, same steps, different instrument underneath. `voice bass reese` swaps the 303 for a reese bass.",
    "track": "Track adds or removes a track - oontz isn't fixed at 8. `track add rumble sub` adds one called rumble playing the sub voice; `track del rumble` removes it.",
    "voices": "Lists every sound engine currently registered - everything you can point a track at with `voice`.",
    "fx": "Fx chains an effect onto a track (or `master` for the whole mix) - `fx bass drive amount 2.5` adds drive; `fx bass off` clears it. Stacks with the track's own filter, applied after it.",
    "fxlist": "Lists every effect currently registered - everything you can chain on with `fx`.",
}


def why(topic):
    """Explain a parameter, key or concept in sound terms. Never a gap for
    anything in core.new_track() or core.CMDS - checked in the self-test."""
    key = _WHY_ALIAS.get((topic or "").lower(), (topic or "").lower())
    if key in WHY:
        return WHY[key]
    return "no explanation yet for %r — try `?` for the key list, or ask about one of: %s" % (
        topic, ", ".join(sorted(WHY)))

# ------------------------------------------------------------------ lesson


def _track_pred(name, pred):
    def f(s):
        t = next((tt for tt in s.tracks if tt.name == name), None)
        return bool(t) and pred(t)
    return f


LESSON = [
    ("Make a kick",
     "Press `:` then type `kick x...x...x...x...` and hit Enter - four on the "
     "floor, the heartbeat of techno.",
     _track_pred("kick", lambda t: t.active)),
    ("Press play",
     "Press space. It loops until you stop it - there's nothing here to break.",
     lambda s: s.playing),
    ("Add hats",
     "Press `:` then type `hat ..x...x...x...x.` - hats fill the gaps between "
     "kicks and give the beat its lift.",
     _track_pred("hat", lambda t: t.active)),
    ("Punch a step by hand",
     "Press 2 to focus the hats, then press k - that's step 16, toggled straight "
     "from the keyboard, no typing required.",
     _track_pred("hat", lambda t: len(t.pat) >= 16 and t.pat[15] in "xX")),
    ("Add a bassline",
     "Press `:` then type `bass a1 . a1~ . c2 . a1 .` - a1 is a note, ~ slides "
     "into the next one.",
     _track_pred("bass", lambda t: t.active)),
    ("Sidechain it",
     "Press `:` then type `sidechain bass 0.7` - now the bass ducks out of the "
     "kick's way instead of fighting it.",
     _track_pred("bass", lambda t: t.sc >= 0.5)),
    ("Sweep a filter",
     "Focus the bass, then hold `]` - the cutoff rises and the bassline opens up. "
     "`[` brings it back down.",
     _track_pred("bass", lambda t: t.fc > 0.0)),
    ("Vary the pattern",
     "Press `n` - variation nudges a couple of steps at random. Keep pressing it "
     "until you like the result.",
     lambda s: "vary" in s.echo.lower() or "varied" in s.echo.lower()),
    ("Record a take",
     "Press `R` to start recording exactly what you hear.",
     lambda s: s.recording),
    ("Stop and admire it",
     "Press `R` again to stop. You just built a track from nothing: kick, hats, "
     "bass, a sidechain, a filter sweep, a variation, a take. Everything else in "
     "oontz is just more of this.",
     lambda s: (not s.recording) and bool(s.rec_name)),
]


def lesson(step):
    """(title, text, expected) for one 0-indexed step. expected: Snapshot -> bool."""
    return LESSON[step]


def lesson_check(step, snapshot):
    """True once the snapshot proves the step's action actually happened."""
    if not (0 <= step < len(LESSON)):
        return False
    return LESSON[step][2](snapshot)

# ----------------------------------------------------------------- suggest

_TRACK_CMDS = ("filter", "sidechain", "humanize", "gain", "pan", "tune")
_ALREADY = {
    "filter": lambda t: t.filt != "",
    "sidechain": lambda t: t.sc > 0.0,
    "humanize": lambda t: t.hum > 0.0,
    "gain": lambda t: t.gain != 1.0,
    "pan": lambda t: t.pan != 0.0,
    "tune": lambda t: False,      # ponytail: no clean "default" tune per track; always eligible
}


def suggest(snapshot, history):
    """Concrete commands worth running now, mined from past command strings.

    history: list[str] of previously-run command lines, oldest first - one per
    line the way ~/.oontz/history.jsonl stores them: {"ts": <float>, "cmd": "<line>"}
    per line, cmd already extracted before this is called. No file I/O happens
    here; the caller reads the jsonl and hands over the parsed cmd list.
    """
    if not history:
        return []
    names = {t.name for t in snapshot.tracks}

    def norm(h):
        p = h.split()
        if not p:
            return None
        return core.ALIAS.get(p[0].lower(), p[0].lower()), p[1:]

    played = collections.Counter()
    combo = collections.defaultdict(collections.Counter)
    bpms = collections.Counter()
    for h in history:
        r = norm(h)
        if not r:
            continue
        v, args = r
        if v in names:
            played[v] += 1
        elif v in _TRACK_CMDS and args and args[0] in names:
            combo[(v, args[0])][" ".join(args[1:])] += 1
        elif v == "bpm" and args:
            try:
                bpms[round(float(args[0]), 1)] += 1
            except ValueError:
                pass

    by = {t.name: t for t in snapshot.tracks}
    out = []
    for (verb, track), counts in sorted(combo.items()):
        n = played.get(track, 0)
        total = sum(counts.values())
        if n < 2 or total / n < 0.7:
            continue
        t = by.get(track)
        if not t or not t.active or _ALREADY[verb](t):
            continue
        best = counts.most_common(1)[0][0]
        cmd = ("%s %s %s" % (verb, track, best)).strip()
        out.append("%s   # you almost always %s %s (%d/%d times)" % (cmd, verb, track, total, n))

    if bpms:
        fav, cnt = bpms.most_common(1)[0]
        if cnt >= 2 and abs(snapshot.bpm - fav) >= 3:
            out.append("bpm %g   # you play at %g BPM most often (%d/%d sessions)" %
                       (fav, fav, cnt, len(history)))
    return out

# ------------------------------------------------------------------ report


def report(snapshot, history, elapsed):
    """Markdown session summary - what got built, how it sounds, how to redo it."""
    active = [t for t in snapshot.tracks if t.active]
    mins, secs = divmod(max(0, int(elapsed)), 60)
    L = []
    L.append("# %s — session report" % (snapshot.name or "untitled"))
    L.append("")
    L.append("**%g BPM**, swing %g%%, %d bar%s, %d:%02d elapsed." %
             (snapshot.bpm, snapshot.swing, snapshot.bar,
              "" if snapshot.bar == 1 else "s", mins, secs))
    L.append("")
    L.append("## what's playing")
    if active:
        for t in active:
            bits = ["`%s`" % t.pat]
            if _pitched(t) and t.notes:
                bits.append("notes `%s`" % " ".join(t.notes))
            if t.filt:
                bits.append("%s @ %gHz" % (t.filt, t.fc))
            if t.sc:
                bits.append("sidechained %.1f" % t.sc)
            if t.mute:
                bits.append("MUTED")
            if t.solo:
                bits.append("SOLO")
            L.append("- **%s** — %s" % (t.name, ", ".join(bits)))
    else:
        L.append("- nothing playing")
    L.append("")
    L.append("## balance")
    loud = sorted(active, key=lambda t: -t.rms)[:3]
    if loud:
        L.append(", ".join("%s (%.0f%%)" % (t.name, min(1.0, t.rms * 6) * 100)
                           for t in loud) + " carrying the mix.")
    else:
        L.append("nothing loud enough to call out.")
    db = -48.0 if snapshot.peak <= 0.004 else 20 * math.log10(snapshot.peak)
    verdict = ("clean, plenty of headroom" if db < -6 else
              "tight, keep an eye on it" if db < -1 else
              "riding the ceiling — pull something back")
    L.append("Master peak %.1f dB — %s." % (db, verdict))
    L.append("")
    L.append("## reproduce it")
    L.append("```")
    L.append("bpm %g" % snapshot.bpm)
    L.append("swing %g" % snapshot.swing)
    for h in history:
        L.append(h)
    L.append("```")
    return "\n".join(L)

# --------------------------------------------------------------------- demo


def _with_track(s, name, **kw):
    tracks = tuple(dataclasses.replace(t, **kw) if t.name == name else t for t in s.tracks)
    return dataclasses.replace(s, tracks=tracks)


def demo():
    import re
    import inspect
    from . import ui                      # safe here: only reached long after core is loaded

    print("=" * 70)
    print("oontz teach.py demo")
    print("=" * 70)

    # ---- build a family of realistic snapshots off the real engine ----
    core.do("open warehouse")
    stopped = core.snapshot()
    assert stopped.name == "warehouse.oontz"

    playing_good = dataclasses.replace(core.snapshot(), playing=True, bar=20, peak=0.3,
                                       recording=False)
    recording = dataclasses.replace(core.snapshot(), playing=True, bar=5, recording=True,
                                    rec_name="take_003.wav")
    clipping = dataclasses.replace(core.snapshot(), playing=True, bar=20, peak=0.99,
                                   recording=False)

    no_hats = dataclasses.replace(core.snapshot(), playing=True, bar=10, recording=False)
    no_hats = _with_track(no_hats, "hat", active=False)
    no_hats = _with_track(no_hats, "oh", active=False)

    bass_no_sc = dataclasses.replace(core.snapshot(), playing=True, bar=10, recording=False)
    bass_no_sc = _with_track(bass_no_sc, "kick", active=False)   # keep it out of collision
    bass_no_sc = _with_track(bass_no_sc, "bass", sc=0.0)

    collision = dataclasses.replace(core.snapshot(), playing=True, bar=10, recording=False)
    collision = _with_track(collision, "bass", sc=0.0)

    empty = Snapshot()

    # ---- 1. hint() covers every state, and fires the *right* one ----
    cases = {
        "empty": (empty, "open warehouse"),
        "stopped": (stopped, "press space"),
        "playing (sounding good)": (playing_good, "record"),
        "recording": (recording, "stop"),
        "clipping": (clipping, "clipping"),
        "no-hats": (no_hats, "hats"),
        "bass-without-sidechain": (bass_no_sc, "sidechain"),
    }
    print("\n-- hint() --")
    for label, (snap, must_contain) in cases.items():
        h = hint(snap)
        assert h is None or isinstance(h, str), (label, h)
        assert h is not None and must_contain in h.lower(), (label, h)
        print("  %-26s %s" % (label, h))
    h_collision = hint(collision)
    assert h_collision and "collid" in h_collision.lower(), h_collision
    print("  %-26s %s" % ("kick+bass collision", h_collision))

    # ---- every key a hint names is a key that really exists in ui.on_key ----
    src = inspect.getsource(ui.on_key)
    valid = set()
    for m in re.finditer(r'k == "((?:\\.|[^"\\])*)"', src):
        valid.add(m.group(1))
    for m in re.finditer(r'k in "((?:\\.|[^"\\])*)"', src):
        valid.update(m.group(1))
    if "k in STEP_KEYS" in src:
        valid.update(ui.STEP_KEYS)
    assert ui.STEP_KEYS == STEP_KEYS, "local STEP_KEYS drifted from ui.STEP_KEYS"
    mentioned = {" ", "2", "q", "e", "t", "u", "R", "["}
    missing = mentioned - valid
    assert not missing, "hint mentions keys ui.on_key doesn't have: %s" % missing
    print("  all mentioned keys verified against ui.on_key: %s" % sorted(mentioned))

    # ---- 2 & 3. legend() and help_page() are exact-width, help_page respects h ----
    print("\n-- legend() --")
    for w in (60, 80, 120, 200):
        for snap, label in ((stopped, "kick"), (dataclasses.replace(stopped, mode="cmd"), "cmd")):
            line = legend(snap, w)
            assert ui.vlen(line) == w, (w, label, ui.vlen(line))
        print("  w=%-3d %s" % (w, legend(stopped, w)))
    bass_focus = dataclasses.replace(stopped, focus=[t.name for t in stopped.tracks].index("bass"))
    print("  bass focus: %s" % legend(bass_focus, 100))
    hat_focus = dataclasses.replace(stopped, focus=[t.name for t in stopped.tracks].index("hat"))
    print("  hat  focus: %s" % legend(hat_focus, 100))

    print("\n-- help_page() --")
    for w in (60, 80, 120, 200):
        for h in (12, 24, 40):
            rows = help_page(stopped, w, h)
            assert len(rows) <= h, (w, h, len(rows))
            for r in rows:
                assert ui.vlen(r) == w, (w, h, r)
    small = help_page(stopped, 80, 10)
    assert any("page" in ui.ANSI.sub("", r) for r in small), "short page should say it paginated"
    print("  page 1/n at h=10:")
    for r in small:
        print("    " + ui.ANSI.sub("", r))

    # ---- 4. why() has zero gaps against the live core surface ----
    print("\n-- why() --")
    for k in core.new_track("kick"):
        assert why(k) and not why(k).startswith("no explanation"), "gap: new_track param %r" % k
    for k in core.CMDS:
        assert why(k) and not why(k).startswith("no explanation"), "gap: command %r" % k
    print("  res 0.9 lowpass: %s" % why("res"))
    print("  sidechain:       %s" % why("sidechain"))
    print("  euclidean:       %s" % why("euclidean"))

    # ---- 5. lesson / lesson_check ----
    print("\n-- lesson() --")
    title, text, _ = lesson(0)
    assert isinstance(title, str) and isinstance(text, str)
    assert not lesson_check(0, empty)
    made_kick = _with_track(dataclasses.replace(empty, tracks=stopped.tracks), "kick", active=True)
    assert lesson_check(0, made_kick)
    assert lesson_check(1, dataclasses.replace(empty, playing=True))
    assert not lesson_check(1, empty)
    assert lesson_check(len(LESSON) - 1, dataclasses.replace(empty, recording=False, rec_name="x.wav"))
    assert not lesson_check(999, empty)
    for i in range(len(LESSON)):
        t, tx, exp = lesson(i)
        print("  %2d. %-24s %s" % (i + 1, t, tx[:60] + ("…" if len(tx) > 60 else "")))

    # ---- 6. suggest() - every command it returns actually parses ----
    print("\n-- suggest() --")
    history = (["kick x...x...x...x...", "bass a1 . a1~ . c2 . a1 .",
               "sidechain bass 0.7", "bpm 140"] * 3 +
              ["bass a1 . a1~ . c2 . a1 .", "sidechain bass 0.7", "bpm 140"])
    fresh = dataclasses.replace(core.snapshot(), bpm=132.0)
    fresh = _with_track(fresh, "bass", sc=0.0, active=True)
    sugg = suggest(fresh, history)
    assert sugg, "expected at least one suggestion from a clear habit"
    for cmd in sugg:
        out = do_line = core.do(cmd)
        assert not (isinstance(out, str) and out.startswith("?")), (cmd, out)
        print("  " + cmd)
    assert suggest(fresh, []) == []

    # ---- 7. report() ----
    print("\n-- report() --")
    rpt = report(core.snapshot(), ["kick x...x...x...x...", "sidechain bass 0.7"], 137.0)
    assert rpt.startswith("# ") and "## reproduce it" in rpt
    print(rpt)

    print("\n" + "=" * 70)
    print("teach.py: all checks pass")
    print("=" * 70)


if __name__ == "__main__":
    demo()
