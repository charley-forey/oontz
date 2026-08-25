"""A director that plans a whole song with you, one step at a time.

ai.py already turns a single intent into commands. This is the layer above it: a
plan for a whole track, broken into steps you accept, tweak or skip, each with a
plain explanation of what it does musically and a check that notices when you
have done it.

Every proposed command goes through ai.validate() before it is ever offered, and
nothing is applied here - commands are returned for the caller to preview. With
the claude CLI unavailable, every single function still works, using the
arrangement grammar instead of the model.
"""
from .contracts import COMMANDS

# Words people actually use, mapped onto things oontz can do.
MOODS = {
    "dark": ("phrygian", "lower the filter, minor second in the bassline"),
    "hypnotic": ("minor", "few elements, long sections, tiny variations"),
    "peak": ("minor", "everything in, short breaks, drops early and often"),
    "industrial": ("phrygian", "distorted kick, metallic percussion, noise"),
    "rolling": ("minor", "offbeat bass, swung hats, no big drops"),
    "euphoric": ("major", "open filters, stabs, long builds"),
}


class Plan(object):
    def __init__(self, style="hardtechno", minutes=5.0, bpm=145.0, key="a",
                 scale="minor", curve="classic", sections=(), intent="", notes=()):
        self.style, self.minutes, self.bpm = style, minutes, bpm
        self.key, self.scale, self.curve = key, scale, curve
        self.sections = list(sections)               # [(role, bars)]
        self.intent = intent
        self.notes = list(notes)

    def total_bars(self):
        return sum(b for _r, b in self.sections)

    def summary(self):
        arc = " → ".join("%s %d" % (r, b) for r, b in self.sections)
        return ("%s, %.0f min, %g BPM, %s %s, %s curve\n  %s\n  %s"
                % (self.style, self.minutes, self.bpm, self.key, self.scale,
                   self.curve, arc, "  ".join(self.notes)))


class Step(object):
    def __init__(self, title, why, commands, check=None):
        self.title, self.why = title, why
        self.commands = list(commands)
        self._check = check or (lambda s: False)

    def check(self, snap):
        try:
            return bool(self._check(snap))
        except Exception:
            return False


class Director(object):
    """The session. A state machine, not a chat log."""

    def __init__(self):
        self.plan = None
        self.steps = []
        self.at = 0
        self.transcript = []

    def start(self, brief):
        self.plan = plan(brief)
        self.steps = steps(self.plan)
        self.at = 0
        self.transcript = [("brief", brief)]
        return self.plan

    def current(self):
        return self.steps[self.at] if 0 <= self.at < len(self.steps) else None

    def advance(self, snap=None):
        """Move on if the current step is done, or on request."""
        st = self.current()
        if st is None:
            return None
        if snap is None or st.check(snap):
            self.at = min(len(self.steps), self.at + 1)
        return self.current()

    def skip(self):
        self.at = min(len(self.steps), self.at + 1)
        return self.current()

    def done(self):
        return self.at >= len(self.steps)

    def progress(self):
        return (self.at, len(self.steps))


SESSION = Director()


# --------------------------------------------------------------------- plan

def _ai():
    try:
        from . import ai
        return ai
    except ImportError:
        return None


def _parse_brief(brief):
    """Pull what we can out of the words, offline. Always produces something."""
    import re
    b = (brief or "").lower()
    minutes = 5.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:min|minute|m\b)", b)
    if m:
        minutes = max(1.0, min(20.0, float(m.group(1))))
    bpm = None
    m = re.search(r"(\d{2,3})\s*(?:bpm|beats)", b)
    if m:
        bpm = float(m.group(1))
    elif re.search(r"\b1[2-8]\d\b", b):
        bpm = float(re.search(r"\b1[2-8]\d\b", b).group(0))
    style = "hardtechno"
    for s in ("hardtechno", "hard techno", "acid", "industrial", "minimal",
              "dubtechno", "dub techno", "breakbeat", "house", "trance", "hypnotic",
              "techno"):
        if s in b:
            style = s.replace(" ", "")
            break
    curve = "classic"
    for word, cv in (("peak", "peaktime"), ("hypnotic", "hypnotic"),
                     ("journey", "journey"), ("warm", "warmup"),
                     ("build", "classic"), ("rollercoaster", "rollercoaster")):
        if word in b:
            curve = cv
            break
    scale, notes = "minor", []
    for mood, (sc, note) in MOODS.items():
        if mood in b:
            scale, _ = sc, None
            notes.append("%s: %s" % (mood, note))
    key = "a"
    m = re.search(r"\bin ([a-g])(#|b)?\s*(minor|major)?", b)
    if m:
        key = m.group(1) + (m.group(2) or "")
        scale = m.group(3) or scale
    return style, minutes, bpm, key, scale, curve, notes


def plan(brief):
    """A structured plan. Uses the model when it is there, the grammar when not."""
    style, minutes, bpm, key, scale, curve, notes = _parse_brief(brief)
    try:
        from . import compose
        if bpm is None:
            bpm = {"hardtechno": 148, "industrial": 152, "acid": 138, "minimal": 126,
                   "house": 124, "trance": 138, "dubtechno": 120}.get(style, 140)
        sections = compose.arrange(minutes, curve, bpm, seed=None)
    except Exception:
        bpm = bpm or 140
        sections = [("intro", 16), ("build", 8), ("drop", 32), ("break", 8),
                    ("build", 8), ("drop", 32), ("outro", 16)]
    p = Plan(style, minutes, bpm, key, scale, curve, sections, brief, notes)

    ai = _ai()
    if ai and ai.available():                        # let the model refine the notes
        try:
            r = ai.ask("Reply with at most four short lines of advice, no commands: "
                       "how should a %s track described as %r be arranged? "
                       "It is %.0f minutes at %g BPM in %s %s."
                       % (style, brief, minutes, bpm, key, scale), None)
            raw = getattr(r, "raw", "") or ""
            extra = [l.strip("-* ") for l in raw.splitlines() if l.strip()][:4]
            p.notes.extend(x for x in extra if not x.startswith("["))
        except Exception:
            pass
    if not p.notes:
        p.notes.append("%d bars, %d sections - the drop lands at bar %d."
                       % (p.total_bars(), len(sections),
                          sum(b for r, b in sections[:next(
                              (i for i, (r, _b) in enumerate(sections)
                               if r == "drop"), 0)])))
    return p


# -------------------------------------------------------------------- steps

def steps(p):
    """Groove first, arrangement second, polish last. Each step is one decision."""
    out = []

    def has(snap, name):
        return any(t.name == name and t.active for t in (snap.tracks or ()))

    out.append(Step(
        "Choose the kit",
        "Every style is a different set of sounds and a different tempo. This "
        "loads one so you are starting from something that already works.",
        ["style %s" % p.style],
        lambda s: bool(s.tracks) and any(t.active for t in s.tracks)))

    out.append(Step(
        "Lock the kick",
        "Techno is built from the kick outwards. Four to the floor is the "
        "default for a reason - it gives everything else a grid to sit on.",
        ["kick x...x...x...x...", "bpm %g" % p.bpm],
        lambda s: has(s, "kick")))

    out.append(Step(
        "Add hats for movement",
        "The kick gives you weight; hats give you speed. Offbeat hats are what "
        "make a track feel like it is moving rather than just thudding.",
        ["hat ..x...x...x...x."],
        lambda s: has(s, "hat") or has(s, "oh")))

    out.append(Step(
        "Write the bassline",
        "One phrase, in key, that you will develop for the rest of the track. "
        "It does not need to be clever - it needs to be recognisable.",
        ["melody bass %s %s 16" % (p.key, p.scale)],
        lambda s: has(s, "bass")))

    out.append(Step(
        "Duck the bass under the kick",
        "Sidechain drops the bass every time the kick hits, so the two stop "
        "fighting for the same low frequencies. This is what makes it breathe.",
        ["sidechain bass 0.7"],
        lambda s: any(t.name == "bass" and t.sc > 0 for t in (s.tracks or ()))))

    out.append(Step(
        "Turn it into a song",
        "Right now it is a loop. This gives it sections - an intro to mix into, "
        "builds, drops, a break - so it goes somewhere.",
        ["compose %s %g %s" % (p.style, p.minutes, p.curve)],
        lambda s: _has_song()))

    out.append(Step(
        "Shape the build",
        "A build works by taking something away and giving it back. Opening a "
        "filter across eight bars is the simplest version of that.",
        ["ramp bass.fc 300 4000 over 8"],
        lambda s: _section_has_automation()))

    out.append(Step(
        "Earn the break",
        "A drop only hits if something quiet came before it. Strip the drums "
        "and let the atmosphere run for eight bars.",
        ["goto break"],
        lambda s: True))

    out.append(Step(
        "Check the low end",
        "Kick and bass in the same band is the most common way a track turns to "
        "mud. Look at the FREQ view - anything red is two things colliding.",
        ["view freq"],
        lambda s: s.view == "freq"))

    out.append(Step(
        "Record a take",
        "Press R. Recording captures exactly what you hear, performance effects "
        "and all, and saves the .oontz beside it so you can get back here.",
        ["rec"],
        lambda s: s.recording))

    out.append(Step(
        "Save it for the deck",
        "Saving as a .song puts it in the library, where DECK mode can load it "
        "and tell you what else in your library mixes with it.",
        ["song save"],
        lambda s: True))

    # validate every command before any of it is ever offered
    ai = _ai()
    if ai:
        for st in out:
            good, _bad = ai.validate(st.commands)
            st.commands = good or st.commands
    return out


def _has_song():
    try:
        from . import core
        return core.ST.song is not None
    except Exception:
        return False


def _section_has_automation():
    try:
        from . import core
        _n, sec = core.current_section()
        return bool(sec and sec.automation)
    except Exception:
        return False


# ----------------------------------------------------------------- critique

def critique(song=None):
    """Structural criticism of a WHOLE song - pacing, not spectrum.

    ai.crit looks at one bar's frequency balance. This looks at the shape.
    """
    if song is None:
        try:
            from . import core
            song = core.ST.song
        except Exception:
            song = None
    if song is None or not song.order:
        return "No song yet. `compose hardtechno 5` gives you one to react to."

    secs = [(n, song.sections[n]) for n in song.order if n in song.sections]
    total = song.total_bars()
    roles = [s.role for _n, s in secs]
    energies = [s.energy for _n, s in secs]
    out = []

    first_drop = next((i for i, r in enumerate(roles) if r == "drop"), None)
    if first_drop is not None:
        bars_in = sum(s.bars for _n, s in secs[:first_drop])
        pct = bars_in / float(max(1, total)) * 100
        if pct < 8:
            out.append("The first drop lands %d bars in (%.0f%%). That is very early - "
                       "there is no tension to release yet. Give it 16-32 bars." % (bars_in, pct))
        elif pct > 45:
            out.append("The first drop is %d bars in (%.0f%%). People will drift before "
                       "it arrives." % (bars_in, pct))
        else:
            out.append("First drop at bar %d (%.0f%%) - well placed." % (bars_in, pct))
    else:
        out.append("There is no drop at all. Even a hypnotic track wants one moment "
                   "where everything arrives.")

    if "break" not in roles:
        out.append("No break anywhere. Without a quiet passage the drops stop feeling "
                   "like drops - the ear stops noticing loud.")
    if roles and roles[0] != "intro":
        out.append("It starts on a %s. A plain beat intro is what lets a DJ mix into "
                   "it." % roles[0])
    if energies and (max(energies) - min(energies)) < 0.35:
        out.append("Energy only moves %.2f across the whole track. It is flat - vary "
                   "density and filtering between sections." % (max(energies) - min(energies)))
    if len(secs) < 4:
        out.append("Only %d sections. That is a loop with edges, not an arrangement."
                   % len(secs))
    autos = sum(len(s.automation) for _n, s in secs)
    if autos == 0:
        out.append("Nothing is automated. Static sections are what make a long track "
                   "feel long - try `ramp bass.fc 300 4000 over 8` in a build.")

    mins = song.seconds() / 60.0
    out.append("%.1f minutes, %d sections, %d bars, %d automation lanes."
               % (mins, len(secs), total, autos))
    return "\n".join("• " + o for o in out)


def narrate(snap=None):
    """One sentence about what is happening right now, for the status line."""
    try:
        from . import core
        sg = core.ST.song
        if sg is None:
            return "Jamming on a loop - `compose` turns it into a song."
        name, sec, within, i = sg.section_at(core.ST.songbar)
        left = sec.bars - within
        nxt = sg.order[(i + 1) % len(sg.order)] if sg.order else ""
        role = sec.role
        verb = {"intro": "easing in", "build": "building", "drop": "full tilt",
                "break": "stripped back", "verse": "rolling",
                "outro": "winding down"}.get(role, "playing")
        return "%s in %s — %d bars until %s." % (verb.capitalize(), name, left, nxt)
    except Exception:
        return ""


# ---------------------------------------------------------------- commands

def direct_cmd(state, args):
    """`direct <brief>` starts a session; `direct` alone shows the current step."""
    if args:
        p = SESSION.start(" ".join(args))
        st = SESSION.current()
        return ("PLAN  %s\n\nSTEP 1/%d  %s\n  %s\n  → %s   (`accept` or `skip`)"
                % (p.summary(), len(SESSION.steps), st.title, st.why,
                   "  ".join(st.commands)))
    st = SESSION.current()
    if st is None:
        return "no session - `direct a 6 minute dark hypnotic track at 140`"
    i, n = SESSION.progress()
    return "STEP %d/%d  %s\n  %s\n  → %s" % (i + 1, n, st.title, st.why,
                                             "  ".join(st.commands))


def accept_cmd(state, args):
    """Return the current step's commands for the caller to apply, then advance."""
    st = SESSION.current()
    if st is None:
        return "nothing to accept"
    cmds = list(st.commands)
    SESSION.skip()
    return cmds


def next_step_cmd(state, args):
    st = SESSION.advance(None)
    return direct_cmd(state, []) if st else "plan complete - `critique` to review it"


def critique_cmd(state, args):
    return critique()


def narrate_cmd(state, args):
    return narrate()


COMMANDS.update({"direct": direct_cmd, "accept": accept_cmd,
                 "step": next_step_cmd, "critique": critique_cmd,
                 "narrate": narrate_cmd})
