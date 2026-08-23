"""Music theory: scales, chords, the Camelot wheel, and motifs.

Pure functions, no I/O. Everything that reasons about pitch goes through here, so
a generated bassline and a DJ key-match are using the same idea of what a key is.

Motifs are why a generated song has identity: the drop's bassline is the intro's,
transposed and densified, not a fresh roll of the dice.
"""
import functools

from .contracts import ANALYSERS

NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]
FLATS = {"db": "c#", "eb": "d#", "gb": "f#", "ab": "g#", "bb": "a#"}

SCALES = {
    "major":            [0, 2, 4, 5, 7, 9, 11],
    "minor":            [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor":   [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor":    [0, 2, 3, 5, 7, 9, 11],
    "dorian":           [0, 2, 3, 5, 7, 9, 10],
    "phrygian":         [0, 1, 3, 5, 7, 8, 10],     # the dark techno one
    "lydian":           [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":       [0, 2, 4, 5, 7, 9, 10],
    "locrian":          [0, 1, 3, 5, 6, 8, 10],
    "pentatonic_min":   [0, 3, 5, 7, 10],
    "pentatonic_maj":   [0, 2, 4, 7, 9],
    "blues":            [0, 3, 5, 6, 7, 10],
    "whole_tone":       [0, 2, 4, 6, 8, 10],
}

CHORDS = {
    "min": [0, 3, 7], "maj": [0, 4, 7], "dim": [0, 3, 6], "aug": [0, 4, 8],
    "sus2": [0, 2, 7], "sus4": [0, 5, 7], "min7": [0, 3, 7, 10],
    "maj7": [0, 4, 7, 11], "dom7": [0, 4, 7, 10], "min9": [0, 3, 7, 10, 14],
    "add9": [0, 4, 7, 14],
}

# Progressions that actually suit techno. static_i is the honest default: one
# chord for eight minutes is a genre, not a shortcut.
PROGRESSIONS = {
    "static_i":   [(0, "min")],
    "i_VI_III_VII": [(0, "min"), (8, "maj"), (3, "maj"), (10, "maj")],
    "i_iv_v":     [(0, "min"), (5, "min"), (7, "min")],
    "andalusian": [(0, "min"), (10, "maj"), (8, "maj"), (7, "maj")],
    "i_v":        [(0, "min"), (7, "min")],
    "i_VII":      [(0, "min"), (10, "maj")],
}


def pc(name):
    """Pitch class 0-11 from a note name, ignoring octave."""
    n = str(name).strip().lower().rstrip("0123456789")
    n = FLATS.get(n, n)
    if n not in NAMES:
        raise ValueError("bad note %r" % name)
    return NAMES.index(n)


def token(semi, octave=1):
    """Semitone offset -> a thud note token. Octave carries over automatically."""
    return NAMES[semi % 12] + str(octave + semi // 12)


def scale_notes(root, scale="minor", octave=1, count=8):
    """Ascending scale tones as thud note tokens, wrapping octaves as it climbs."""
    steps = SCALES.get(scale, SCALES["minor"])
    base = pc(root)
    return [token(base + steps[i % len(steps)] + 12 * (i // len(steps)), octave)
            for i in range(count)]


def degree_token(root, scale, degree, octave=1):
    steps = SCALES.get(scale, SCALES["minor"])
    return token(pc(root) + steps[degree % len(steps)] + 12 * (degree // len(steps)), octave)


def in_scale(note, root, scale="minor"):
    steps = SCALES.get(scale, SCALES["minor"])
    return (pc(note) - pc(root)) % 12 in steps


def snap(note, root, scale="minor"):
    """Nearest in-scale pitch class. Generation uses this so nothing lands wrong."""
    steps = SCALES.get(scale, SCALES["minor"])
    off = (pc(note) - pc(root)) % 12
    best = min(steps, key=lambda s: min(abs(s - off), 12 - abs(s - off)))
    return NAMES[(pc(root) + best) % 12]


def chord(root, quality="min", octave=2, inversion=0):
    iv = CHORDS.get(quality, CHORDS["min"])
    notes = [token(pc(root) + i, octave) for i in iv]
    for _ in range(inversion):
        notes = notes[1:] + [token(pc(notes[0]) + 12, octave + 1)]
    return notes


def progression(key, scale="minor", name="static_i", octave=2):
    """[(root_token, quality)] for a named progression in a key."""
    return [(token(pc(key) + off, octave), q)
            for off, q in PROGRESSIONS.get(name, PROGRESSIONS["static_i"])]


# --------------------------------------------------------------- camelot
# The wheel DJs use: same number mixes, +/-1 mixes, A<->B (relative) mixes.
# 8A is A minor, 8B is C major, and the wheel walks in fifths from there.

def _wheel():
    m, M = {}, {}
    minor_root, major_root = pc("a"), pc("c")
    for i in range(12):
        code = "%dA" % (((i + 7) % 12) + 1)
        m[(minor_root + i * 7) % 12] = code
        M[(major_root + i * 7) % 12] = "%dB" % (((i + 7) % 12) + 1)
    return m, M


_MINOR_CODES, _MAJOR_CODES = _wheel()
_CODE_TO_KEY = {v: (k, "minor") for k, v in _MINOR_CODES.items()}
_CODE_TO_KEY.update({v: (k, "major") for k, v in _MAJOR_CODES.items()})


def camelot(key, scale="minor"):
    """'a','minor' -> '8A'. Anything not clearly major is treated as minor."""
    table = _MAJOR_CODES if str(scale).startswith("maj") else _MINOR_CODES
    return table.get(pc(key), "")


def from_camelot(code):
    k, s = _CODE_TO_KEY.get(code.upper(), (pc("a"), "minor"))
    return NAMES[k], s


def camelot_neighbours(code):
    """The four codes that mix: itself, +1, -1, and its relative."""
    code = code.upper()
    if not code or code[-1] not in "AB":
        return []
    n, letter = int(code[:-1]), code[-1]
    other = "B" if letter == "A" else "A"
    return ["%d%s" % (n, letter), "%d%s" % (n % 12 + 1, letter),
            "%d%s" % ((n - 2) % 12 + 1, letter), "%d%s" % (n, other)]


def key_distance(k1, s1, k2, s2):
    """0 identical, 1 a neighbour on the wheel, rising for worse. Symmetric."""
    c1, c2 = camelot(k1, s1), camelot(k2, s2)
    if not c1 or not c2:
        return 2.0                                   # unknown: neutral, not hostile
    if c1 == c2:
        return 0.0
    if c2 in camelot_neighbours(c1):
        return 1.0
    n1, n2 = int(c1[:-1]), int(c2[:-1])
    step = min((n1 - n2) % 12, (n2 - n1) % 12)
    return 1.0 + step * 0.5 + (0.5 if c1[-1] != c2[-1] else 0.0)


# ----------------------------------------------------------------- motifs
# A motif is [(degree, steps, accent, slide)]. Degrees are scale degrees, so a
# transposition can never leave the key.

CONTOURS = {
    "rising":  [0, 1, 2, 3, 4, 5, 6, 7],
    "falling": [7, 6, 5, 4, 3, 2, 1, 0],
    "arch":    [0, 2, 4, 6, 7, 6, 4, 2],
    "static":  [0, 0, 2, 0, 0, 0, 2, 0],
    "zigzag":  [0, 4, 1, 5, 2, 6, 3, 7],
}


def motif_generate(seed, length=8, contour="static", rest_chance=0.25):
    """Deterministic under seed. Stepwise-biased so it sounds written, not random."""
    import random
    r = random.Random(seed)
    shape = CONTOURS.get(contour, CONTOURS["static"])
    out = []
    for i in range(length):
        if i > 0 and r.random() < rest_chance:
            out.append((None, 1, False, False))
            continue
        deg = shape[i % len(shape)] + (r.choice([-1, 0, 0, 0, 1]) if r.random() < 0.4 else 0)
        out.append((max(0, deg), 1, r.random() < 0.3, r.random() < 0.2))
    return out


def transpose(m, degrees):
    return [(None if d is None else d + degrees, s, a, sl) for d, s, a, sl in m]


def invert(m):
    notes = [d for d, _, _, _ in m if d is not None]
    if not notes:
        return list(m)
    piv = notes[0]
    return [(None if d is None else 2 * piv - d, s, a, sl) for d, s, a, sl in m]


def retrograde(m):
    return list(reversed(m))


def octave_shift(m, n):
    return transpose(m, n * 7)                       # 7 scale degrees = an octave


def thin(m, amount=0.5):
    """Remove notes without touching the first - the downbeat has to survive."""
    import random
    r = random.Random(len(m) * 7 + int(amount * 100))
    out = []
    for i, ev in enumerate(m):
        out.append(ev if i == 0 or r.random() > amount else (None, ev[1], False, False))
    return out


def densify(m, amount=0.5):
    """Fill rests with neighbours of the surrounding notes."""
    import random
    r = random.Random(len(m) * 13 + int(amount * 100))
    last = next((d for d, _, _, _ in m if d is not None), 0)
    out = []
    for d, s, a, sl in m:
        if d is None and r.random() < amount:
            out.append((last + r.choice([-1, 0, 1]), s, False, r.random() < 0.3))
        else:
            if d is not None:
                last = d
            out.append((d, s, a, sl))
    return out


def accent_shift(m):
    return [(d, s, (not a) if d is not None and i % 4 == 0 else a, sl)
            for i, (d, s, a, sl) in enumerate(m)]


def motif_to_tokens(m, root, scale="minor", octave=1):
    """A motif as a thud note-command argument string: 'a1! . c2~ d2 . a1 ...'"""
    out = []
    for d, _s, accent, slide in m:
        if d is None:
            out.append(".")
            continue
        t = degree_token(root, scale, d, octave)
        out.append(t + ("~" if slide else "") + ("!" if accent else ""))
    return " ".join(out)


# ---------------------------------------------------------------- rhythm

def density(pattern):
    return sum(1 for c in pattern if c not in ".-") / float(len(pattern) or 1)


def syncopation(pattern):
    """How much of the pattern lands off the strong beats."""
    hits = [i for i, c in enumerate(pattern) if c not in ".-"]
    if not hits:
        return 0.0
    return sum(1 for i in hits if i % 4 != 0) / float(len(hits))


def complementary(pattern):
    """A pattern that fills the gaps - how you layer perc against a kick."""
    return "".join("." if c not in ".-" else ("x" if i % 2 else ".")
                   for i, c in enumerate(pattern))


# -------------------------------------------------------------- analysers

def analyse_key(song):
    return {"key": song.key, "scale": song.scale,
            "camelot": camelot(song.key, song.scale)}


def analyse_harmony(song):
    d = analyse_key(song)
    d["neighbours"] = camelot_neighbours(d["camelot"])
    d["scale_notes"] = scale_notes(song.key, song.scale, 2, 8)
    return d


ANALYSERS.update({"key": analyse_key, "harmony": analyse_harmony})
