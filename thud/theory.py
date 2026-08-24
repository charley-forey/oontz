"""What makes a techno track work — as data the agent can reason over.

`harmony.py` knows notes. This knows RECORDS: how long an intro runs before a DJ
can mix out of it, where the drop belongs, which frequency band each element owns,
why a hat on the offbeat feels faster than one on the beat.

Every rule here is a checkable claim with a stated reason, not taste. `critique()`
runs a track against all of them and returns what is wrong and what to do about it,
so a generated song can be judged the same way a human would judge it — and so the
generator can be graded rather than trusted.

Sources are the conventions of the genre: 4/4 at 120-150, 8/16/32-bar phrasing,
sidechained low end, mix-friendly intros and outros. Where a number is a judgement
call rather than a convention it says so.
"""

import os
import json

from .contracts import COMMANDS

# ---------------------------------------------------------------- the corpus

GENRES = {
    "techno": {
        "bpm": (125, 145), "sweet": 132,
        "key": "minor", "phrase": 16,
        "intro_bars": (16, 32), "outro_bars": (16, 32),
        "drop_at": (0.20, 0.40),          # fraction of the track
        "swing": (0, 8),
        "note": "Hypnotic and mechanical. Repetition is the point; change one "
                "element at a time and let it ride."},
    "hardtechno": {
        "bpm": (145, 165), "sweet": 150,
        "key": "minor", "phrase": 16,
        "intro_bars": (16, 32), "outro_bars": (16, 32),
        "drop_at": (0.12, 0.30),
        "swing": (0, 4),
        "note": "Distorted kick carries the track. Rumble tails fill the gaps "
                "between kicks - that smear IS the genre."},
    "acid": {
        "bpm": (130, 145), "sweet": 138,
        "key": "minor", "phrase": 16,
        "intro_bars": (8, 16), "outro_bars": (16, 32),
        "drop_at": (0.15, 0.35),
        "swing": (0, 10),
        "note": "The 303 is the lead, the hook and the arrangement. Move the "
                "filter, not the notes."},
    "minimal": {
        "bpm": (120, 130), "sweet": 126,
        "key": "minor", "phrase": 32,
        "intro_bars": (32, 64), "outro_bars": (32, 64),
        "drop_at": (0.30, 0.55),
        "swing": (8, 20),
        "note": "Space is an instrument. What you leave out is the composition."},
    "dubtechno": {
        "bpm": (118, 128), "sweet": 122,
        "key": "minor", "phrase": 32,
        "intro_bars": (32, 64), "outro_bars": (32, 64),
        "drop_at": (0.35, 0.6),
        "swing": (0, 12),
        "note": "Chords through long delays. Nothing arrives suddenly."},
    "industrial": {
        "bpm": (140, 160), "sweet": 150,
        "key": "phrygian", "phrase": 16,
        "intro_bars": (8, 16), "outro_bars": (8, 24),
        "drop_at": (0.10, 0.28),
        "swing": (0, 3),
        "note": "Metallic percussion and noise. Ugly on purpose, tight anyway."},
    "house": {
        "bpm": (118, 128), "sweet": 124,
        "key": "minor", "phrase": 16,
        "intro_bars": (16, 32), "outro_bars": (16, 32),
        "drop_at": (0.20, 0.40),
        "swing": (8, 25),
        "note": "Swing is the whole feel. Straight house is broken house."},
    "trance": {
        "bpm": (132, 142), "sweet": 138,
        "key": "minor", "phrase": 32,
        "intro_bars": (32, 64), "outro_bars": (32, 64),
        "drop_at": (0.45, 0.65),
        "swing": (0, 4),
        "note": "The breakdown is the song. Everything before it is setup."},
    "breakbeat": {
        "bpm": (130, 145), "sweet": 136,
        "key": "minor", "phrase": 16,
        "intro_bars": (8, 16), "outro_bars": (16, 32),
        "drop_at": (0.15, 0.35),
        "swing": (20, 40),
        "note": "The break IS the hook. Keep the kick off the grid and let the "
                "snare drag - straight sixteenths would kill it."},
    "electro": {
        "bpm": (125, 138), "sweet": 130,
        "key": "minor", "phrase": 16,
        "intro_bars": (16, 32), "outro_bars": (16, 32),
        "drop_at": (0.20, 0.40),
        "swing": (0, 6),
        "note": "Machine funk: syncopated kick under a straight hat. The bassline "
                "talks; everything else answers it."},
    "ambient": {
        "bpm": (100, 120), "sweet": 110,
        "key": "minor", "phrase": 32,
        "intro_bars": (32, 64), "outro_bars": (32, 64),
        "drop_at": (0.40, 0.65),
        "swing": (0, 10),
        "note": "A drop here is a tide, not a cliff. Chords carry the track and "
                "the drums are weather."},
}

# Real dance tracks have known shapes. Walking a grammar produced technically
# legal nonsense - a "drop" at 0.24 energy - so the shape is explicit per curve
# and energy modulates WITHIN it rather than choosing the roles.
TEMPLATES = {
    "classic":       ["intro", "build", "drop", "break", "build", "drop", "outro"],
    "peaktime":      ["intro", "build", "drop", "drop", "break", "build", "drop", "outro"],
    "hypnotic":      ["intro", "verse", "build", "drop", "verse", "drop", "outro"],
    "journey":       ["intro", "build", "drop", "break", "verse", "build", "drop",
                      "break", "drop", "outro"],
    "warmup":        ["intro", "verse", "build", "verse", "drop", "outro"],
    "rollercoaster": ["intro", "build", "drop", "break", "build", "drop", "break",
                      "build", "drop", "outro"],
}

# Bars a role wants. Dance music is phrased in powers of two, and a build is
# usually half its drop.
ROLE_BARS = {"intro": 16, "build": 8, "drop": 32, "break": 8, "verse": 16,
             "fill": 4, "outro": 16}

# The measurement grid. core.band_energy reports energy per entry, and
# band_conflicts names them; the browser reads the same list out of theory.js so a
# band means one thing in both languages.
BANDS_HZ = [("sub", 20, 60), ("bass", 60, 250), ("low-mid", 250, 800),
            ("mid", 800, 2500), ("presence", 2500, 8000), ("air", 8000, 20000)]

# Which band an element owns. Two things fighting for one band is the most common
# way a mix turns to mud, and it is the thing you cannot hear until it is fixed.
FREQ_ROLES = {
    "kick":   {"band": "sub+bass", "hz": (40, 90),
               "note": "Owns 40-90Hz. Nothing else lives there."},
    "rumble": {"band": "sub", "hz": (30, 120),
               "note": "Sits under the kick and fills the gap between hits. "
                       "Sidechain it or it eats the kick."},
    "sub":    {"band": "sub", "hz": (30, 80),
               "note": "Conflicts with the kick by definition. Sidechain hard or "
                       "write it to play in the kick's gaps."},
    "bass":   {"band": "bass+lowmid", "hz": (60, 400),
               "note": "Sits above the kick. Highpass at ~60Hz to stay out of it."},
    "stab":   {"band": "mid", "hz": (300, 3000), "note": "Mid-range hook."},
    "clap":   {"band": "lowmid+mid", "hz": (1000, 3000),
               "note": "1-2kHz is where a clap reads as a clap."},
    "snare":  {"band": "mid", "hz": (180, 4000), "note": "Body at 180, snap at 2k."},
    "hat":    {"band": "air", "hz": (8000, 16000),
               "note": "Above 8k. Below that it fights the mids."},
    "oh":     {"band": "presence+air", "hz": (6000, 14000),
               "note": "Longer than a closed hat, so it masks more. Use sparingly."},
    "perc":   {"band": "mid+presence", "hz": (300, 6000),
               "note": "The band with the most room in most techno tracks."},
    "pad":    {"band": "lowmid+mid", "hz": (200, 4000),
               "note": "Wide and long, so it masks everything. Duck it or filter it."},
    "atmos":  {"band": "presence+air", "hz": (2000, 16000), "note": "Texture, not content."},
}

# Rhythm facts, each with the reason it is true.
RHYTHM = {
    "four_floor": {"pattern": "x...x...x...x...",
                   "why": "A kick on every beat gives every other element a grid. "
                          "It is the reason techno is danceable at any tempo."},
    "offbeat_hat": {"pattern": "..x...x...x...x.",
                    "why": "A hat between kicks doubles the perceived tempo without "
                           "changing the BPM. This is why house feels faster than it is."},
    "clap_on_3": {"pattern": "....x.......x...",
                  "why": "Backbeat on beats 2 and 4. Borrowed from rock and it still "
                         "works, because the ear expects it."},
    "offbeat_bass": {"pattern": ".x.x.x.x.x.x.x.x",
                     "why": "Bass in the kick's gaps means no sidechain is needed - "
                            "they never collide in the first place."},
    "rolling_16ths": {"pattern": "xxxxxxxxxxxxxxxx",
                      "why": "Constant 16ths on a closed hat is momentum with no "
                             "information. Vary the accents or it is wallpaper."},
    "tresillo": {"pattern": "x..x..x.",
                 "why": "3-3-2. The most common syncopation on earth, and it makes "
                        "a straight 4/4 groove immediately."},
}

# Groove is a CURVE, not a percentage.
#
# A swing number moves every offbeat by the same amount and leaves every hit the
# same loudness, which is why a machine pattern sounds like a machine. Real feel is
# two curves over the sixteen: how hard each step is hit, and how far off the grid
# it sits. The downbeat is loudest and dead on; the rest is the genre.
#
# push_ms is milliseconds: negative is early (urgent), positive is late (behind the
# beat). These are small on purpose - past about 15ms it stops being feel and starts
# being a timing error.
GROOVES = {
    "straight": {
        "accent": [1.00, .58, .76, .58, .92, .58, .76, .62,
                   .96, .58, .76, .58, .90, .62, .78, .70],
        "push_ms": [0] * 16,
        "why": "Dead on the grid. The accent curve alone gives it shape, which is "
               "what techno wants - the machine is the point."},
    "pushed": {
        "accent": [1.00, .55, .80, .55, .95, .55, .80, .60,
                   1.00, .55, .80, .55, .93, .60, .82, .74],
        "push_ms": [0, -4, -2, -4, 0, -4, -2, -4, 0, -4, -2, -4, 0, -4, -2, -5],
        "why": "Everything but the downbeat lands fractionally early. Reads as "
               "urgency, and it is why hard techno feels faster than its BPM."},
    "swung": {
        "accent": [1.00, .52, .74, .60, .88, .52, .74, .64,
                   .94, .52, .74, .60, .86, .64, .78, .72],
        "push_ms": [0, 11, 0, 9, 0, 11, 0, 9, 0, 11, 0, 9, 0, 11, 0, 8],
        "why": "The offbeat sixteenth arrives late. This is the shuffle house is "
               "built on, and straight house is broken house."},
    "laid": {
        "accent": [1.00, .54, .70, .54, .84, .54, .70, .58,
                   .90, .54, .70, .54, .82, .58, .72, .66],
        "push_ms": [0, 5, 3, 5, 1, 5, 3, 5, 0, 5, 3, 5, 1, 5, 3, 6],
        "why": "Behind the beat. Dub and the deeper end sit here; it feels heavier "
               "without being slower."},
}

# Which feel each genre is built on.
GENRE_GROOVE = {"techno": "straight", "hardtechno": "pushed", "acid": "straight",
                "minimal": "swung", "dubtechno": "laid", "industrial": "pushed",
                "house": "swung", "trance": "straight"}

# Arrangement rules. `check` returns None when the rule passes, else what is wrong.
ARRANGEMENT = [
    {"id": "dj_intro",
     "rule": "Start with 16-32 bars of beat before anything melodic.",
     "why": "A DJ needs a plain section to mix into. A track that starts on the "
            "drop is unmixable and gets skipped."},
    {"id": "phrase_multiple",
     "rule": "Every section is a multiple of 8 bars, usually 16 or 32.",
     "why": "Dancers and DJs both count in 8s. A 12-bar section lands wrong and "
            "no one can tell you why."},
    {"id": "drop_placement",
     "rule": "The first drop belongs 20-40% into the track.",
     "why": "Earlier and there is no tension to release. Later and the floor drifts."},
    {"id": "break_earns_drop",
     "rule": "A drop needs a quieter section before it.",
     "why": "Loudness is relative. Without contrast the ear stops registering loud."},
    {"id": "one_change",
     "rule": "Change one element per 8 or 16 bars, not three.",
     "why": "Techno is about noticing a single change. Three at once reads as chaos."},
    {"id": "energy_moves",
     "rule": "Peak energy minus minimum energy should exceed 0.4.",
     "why": "A flat track is a long loop. The shape is the composition."},
    {"id": "outro_mixable",
     "rule": "End with 16-32 bars of thinning beat.",
     "why": "Same reason as the intro, in reverse: the next DJ needs somewhere to go."},
    {"id": "motif_returns",
     "rule": "The main motif should appear in at least three sections.",
     "why": "Repetition is what makes a track memorable. A new idea every section "
            "is eight loops, not a song."},
]

MIXING = [
    {"id": "sidechain_bass",
     "rule": "Duck the bass 6dB or more against the kick.",
     "why": "They occupy the same band. Ducking is what lets both be loud."},
    {"id": "hp_the_bass",
     "rule": "Highpass anything that is not the kick above ~60Hz.",
     "why": "Sub energy from three sources sums to mud and eats all the headroom."},
    {"id": "one_per_band",
     "rule": "One element owns each band at any moment.",
     "why": "Masking is inaudible as a problem and obvious as a result."},
    {"id": "headroom",
     "rule": "Master peak at or below -0.5dBFS.",
     "why": "Clipping on a limiter is distortion you cannot undo later."},
    {"id": "mono_bass",
     "rule": "Keep everything below ~120Hz centred.",
     "why": "Wide bass cancels on a mono club system - the one place it must not."},
]

DJ = [
    {"id": "phrase_align",
     "rule": "Start a blend on a phrase boundary, not a bar boundary.",
     "why": "Phrases are 16 or 32 bars. Landing mid-phrase makes both tracks feel wrong."},
    {"id": "bass_swap",
     "rule": "Never run two basslines at once. Swap the lows at the midpoint.",
     "why": "Two sub sources double the energy in the one band with no headroom."},
    {"id": "key_distance",
     "rule": "Mix within one step on the Camelot wheel.",
     "why": "Two keys a tritone apart beat against each other audibly."},
    {"id": "energy_direction",
     "rule": "Mix into equal or higher energy across a set.",
     "why": "A set is one arrangement at a larger scale. The same rules apply."},
    {"id": "tempo_stretch",
     "rule": "Keep tempo changes under about 6%.",
     "why": "Past that, drums start to sound obviously time-stretched."},
]


def genre(name):
    return GENRES.get(str(name).lower().replace(" ", ""), GENRES["techno"])


def brief(name):
    """A short, honest description of what the genre demands. For the copilot."""
    g = genre(name)
    return ("%s: %d-%d BPM (sweet spot %d), %s key, %d-bar phrases, first drop "
            "%d-%d%% in. %s" % (name, g["bpm"][0], g["bpm"][1], g["sweet"],
                                g["key"], g["phrase"],
                                int(g["drop_at"][0] * 100), int(g["drop_at"][1] * 100),
                                g["note"]))


def prompt_text():
    """The corpus as a few hundred words a model can hold: every genre's brief and
    every rule with its reason. The desktop `ask` and the web one get this same
    text, so there is one theory and two readers rather than two theories."""
    lines = ["GENRES:"] + ["  " + brief(n) for n in GENRES]
    for title, rules in (("ARRANGEMENT", ARRANGEMENT), ("MIXING", MIXING), ("DJ", DJ)):
        lines.append(title + ":")
        lines += ["  %s (%s)" % (r["rule"], r["why"]) for r in rules]
    lines.append("BANDS:")
    lines += ["  %s %d-%dHz: %s" % (k, v["hz"][0], v["hz"][1], v["note"])
              for k, v in FREQ_ROLES.items()]
    return "\n".join(lines)


def _why_table():
    """teach.WHY - what a parameter does, in sound terms. Imported lazily because
    teach imports core and core imports this module; at export time everything is
    loaded, so there is no cycle to trip over."""
    try:
        from . import teach
        return dict(teach.WHY)
    except Exception:
        return {}


def as_dict():
    return {"why": _why_table(),
            "genres": GENRES, "freq_roles": FREQ_ROLES, "rhythm": RHYTHM,
            "arrangement": ARRANGEMENT, "mixing": MIXING, "dj": DJ,
            "templates": TEMPLATES, "role_bars": ROLE_BARS,
            "bands_hz": [list(b) for b in BANDS_HZ],
            "grooves": GROOVES, "genre_groove": GENRE_GROOVE}


def export_files():
    """The generated files, keyed by path from the repo root. This module is the
    only source; the browser composer and the API read these, never their own copy.
    `python -m thud theory export` writes them and the selftest fails if they are stale."""
    data = json.dumps(as_dict(), indent=1, sort_keys=True)
    head = "/* generated from thud/theory.py by `python -m thud theory export` - do not edit */\n"
    return {
        "web/app/theory.js": head + '(typeof window !== "undefined" ? window : globalThis)'
                             '.OONTZ_THEORY = ' + data + ";\n",
        "api/theory.json": json.dumps(dict(as_dict(), prompt=prompt_text()),
                                      indent=1, sort_keys=True) + "\n",
    }


ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def export():
    for rel, text in export_files().items():
        with open(os.path.join(ROOT, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return "wrote " + ", ".join(export_files())


def stale():
    """Which exported files no longer match this module."""
    out = []
    for rel, want in export_files().items():
        p = os.path.join(ROOT, rel)
        try:
            with open(p, encoding="utf-8") as f:
                got = f.read()
        except OSError:
            got = None
        if got != want:
            out.append(rel)
    return out


def band_conflicts(bands_by_track, threshold=0.30):
    """Which tracks are fighting for the same band, from MEASURED band energy.

    bands_by_track: {name: [sub, bass, lowmid, mid, presence, air]} as
    core.band_energy produces. Returns [(band, [tracks])].
    """
    names = ["sub", "bass", "low-mid", "mid", "presence", "air"]
    out = []
    for i, band in enumerate(names):
        loud = [t for t, b in bands_by_track.items()
                if b and len(b) > i and b[i] >= threshold]
        if len(loud) > 1:
            out.append((band, sorted(loud)))
    return out


def critique(song, bands_by_track=None, style=None):
    """Run a Song against every rule. Returns [(severity, id, message)].

    severity: "bad" (fix this), "warn" (consider), "good" (it passes).
    This is what lets a generated track be GRADED rather than trusted.
    """
    out = []
    if song is None or not getattr(song, "order", None):
        return [("bad", "no_song", "There is no song to judge yet.")]

    secs = [(n, song.sections[n]) for n in song.order if n in song.sections]
    if not secs:
        return [("bad", "no_sections", "The arrangement is empty.")]
    total = sum(s.bars for _n, s in secs)
    roles = [s.role for _n, s in secs]
    energies = [s.energy for _n, s in secs]
    g = genre(style or (song.meta or {}).get("style") or "techno")

    # tempo
    lo, hi = g["bpm"]
    if not (lo <= song.bpm <= hi):
        out.append(("warn", "bpm",
                    "%.0f BPM sits outside the %d-%d range that defines this style. "
                    "Intentional is fine; accidental is not." % (song.bpm, lo, hi)))
    else:
        out.append(("good", "bpm", "%.0f BPM is right in the pocket." % song.bpm))

    # phrasing
    odd = [n for n, s in secs if s.bars % 8]
    if odd:
        out.append(("bad", "phrase_multiple",
                    "These sections are not multiples of 8 bars: %s. Dancers and "
                    "DJs both count in 8s." % ", ".join(odd)))
    else:
        out.append(("good", "phrase_multiple", "Every section is phrase-aligned."))

    # intro
    first = secs[0]
    if first[1].role != "intro":
        out.append(("bad", "dj_intro",
                    "The track opens on a %s. A DJ has nothing to mix into."
                    % first[1].role))
    elif first[1].bars < g["intro_bars"][0]:
        out.append(("warn", "dj_intro",
                    "The intro is %d bars; %d-%d is what a DJ needs."
                    % (first[1].bars, g["intro_bars"][0], g["intro_bars"][1])))
    else:
        out.append(("good", "dj_intro", "%d-bar intro - mixable." % first[1].bars))

    # drop placement
    di = next((i for i, r in enumerate(roles) if r == "drop"), None)
    if di is None:
        out.append(("bad", "drop_placement",
                    "There is no drop. Even a hypnotic track wants one arrival."))
    else:
        at = sum(s.bars for _n, s in secs[:di]) / float(max(1, total))
        p0, p1 = g["drop_at"]
        if at < p0:
            out.append(("bad", "drop_placement",
                        "The drop lands %.0f%% in. Before %.0f%% there is no tension "
                        "built to release." % (at * 100, p0 * 100)))
        elif at > p1:
            out.append(("warn", "drop_placement",
                        "The drop lands %.0f%% in. Past %.0f%% the floor drifts."
                        % (at * 100, p1 * 100)))
        else:
            out.append(("good", "drop_placement",
                        "Drop at %.0f%% - well placed for this style." % (at * 100)))

    # a drop needs a break before it
    if "break" not in roles and di is not None:
        out.append(("warn", "break_earns_drop",
                    "No break anywhere. Loudness is relative - without a quiet "
                    "passage the drops stop reading as drops."))
    elif "break" in roles:
        out.append(("good", "break_earns_drop", "There is contrast before the drops."))

    # energy range
    spread = (max(energies) - min(energies)) if energies else 0
    if spread < 0.4:
        out.append(("bad", "energy_moves",
                    "Energy only moves %.2f across the track. That is a long loop, "
                    "not an arrangement." % spread))
    else:
        out.append(("good", "energy_moves", "Energy spans %.2f." % spread))

    # outro
    if secs[-1][1].role != "outro":
        out.append(("warn", "outro_mixable",
                    "It ends on a %s. The next DJ has nowhere to go."
                    % secs[-1][1].role))
    else:
        out.append(("good", "outro_mixable", "Mixable outro."))

    # length
    mins = song.seconds() / 60.0
    if mins < 3:
        out.append(("warn", "length",
                    "%.1f minutes is short for a DJ tool. 5-7 is the useful range."
                    % mins))

    # frequency conflicts, from measurement when it is available
    if bands_by_track:
        for band, tracks in band_conflicts(bands_by_track):
            out.append(("warn", "one_per_band",
                        "%s are all loud in the %s band. Pick one to own it and "
                        "filter or duck the others." % (" and ".join(tracks), band)))
    return out


def score(crit):
    """0-100 from a critique. Something to optimise against and to track over time."""
    if not crit:
        return 0
    weights = {"bad": -12, "warn": -4, "good": 6}
    raw = sum(weights.get(sev, 0) for sev, _i, _m in crit)
    return max(0, min(100, 50 + raw))


def advice(crit, n=3):
    """The n most important things to fix, worst first."""
    order = {"bad": 0, "warn": 1, "good": 2}
    ranked = sorted(crit, key=lambda c: order.get(c[0], 3))
    return [m for sev, _i, m in ranked if sev != "good"][:n]


def report(song, bands_by_track=None, style=None):
    """A readable verdict. What the copilot shows and what the generator is graded on."""
    crit = critique(song, bands_by_track, style)
    s = score(crit)
    lines = ["%s — %d/100" % (getattr(song, "name", "untitled"), s), ""]
    for sev, _id, msg in crit:
        lines.append({"bad": "  ✗ ", "warn": "  ! ", "good": "  ✓ "}[sev] + msg)
    tips = advice(crit)
    if tips:
        lines += ["", "  Fix first:"] + ["   - " + t for t in tips]
    return "\n".join(lines)


NEWLINE = chr(10)


# ---------------------------------------------------------------- commands

def _bands_now():
    try:
        from . import core
        return {t: core.ST.bands.get(t) for t in core.ST.order
                if core.ST.rms.get(t, 0) > 0}
    except Exception:
        return None


def grade_cmd(state, args):
    """`grade` - run the whole track against the rules and score it 0-100."""
    from . import core
    return report(core.ST.song, _bands_now(),
                  args[0] if args else (core.ST.song.meta.get("style")
                                        if core.ST.song else None))


def theory_cmd(state, args):
    """`theory <genre>` - what this style actually demands."""
    if not args:
        return "  ".join(sorted(GENRES))
    return brief(args[0])


def rules_cmd(state, args):
    """`rules arrangement|mixing|dj|rhythm|freq` - the reference itself."""
    which = (args[0] if args else "arrangement").lower()
    if which.startswith("arr"):
        return NEWLINE.join("- %s  (%s)" % (r["rule"], r["why"]) for r in ARRANGEMENT)
    if which.startswith("mix"):
        return NEWLINE.join("- %s  (%s)" % (r["rule"], r["why"]) for r in MIXING)
    if which.startswith("dj"):
        return NEWLINE.join("- %s  (%s)" % (r["rule"], r["why"]) for r in DJ)
    if which.startswith("rhy"):
        return NEWLINE.join("- %-18s %s" + NEWLINE + "    %s" % (k, v["pattern"], v["why"])
                          for k, v in RHYTHM.items())
    if which.startswith("fre"):
        return NEWLINE.join("- %-8s %-14s %s" % (k, v["band"], v["note"])
                          for k, v in FREQ_ROLES.items())
    return "rules arrangement|mixing|dj|rhythm|freq"


COMMANDS.update({"grade": grade_cmd, "theory": theory_cmd, "rules": rules_cmd})
