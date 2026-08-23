"""A song is a timeline, not a loop.

The whole model is one pure question:

    song.state_at(bar) -> the resolved track state for that absolute bar

Everything falls out of it. Scrubbing is setting an index. Offline rendering is
asking for every bar in turn. Automation is interpolation inside the answer rather
than mutation of a global. A DJ deck is that render, finished, in a buffer.

Sections hold FULL SNAPSHOTS of track state, not diffs. Storage is trivial and it
matches how people think about a song - "the drop has more going on" - with no
spooky action between sections.
"""
import copy
import json
import math
import hashlib

from .contracts import SR

# Section roles. Energy is 0..1 and is what generation walks along a curve.
ROLES = {
    "intro":  0.25, "build": 0.60, "drop": 1.00, "break": 0.30,
    "verse":  0.55, "peak":  0.95, "outro": 0.20, "fill": 0.70, "loop": 0.7,
}

CURVES = {
    "linear": lambda t: t,
    "exp":    lambda t: t * t,
    "log":    lambda t: math.sqrt(t),
    "ease":   lambda t: t * t * (3 - 2 * t),
    "step":   lambda t: 0.0 if t < 1.0 else 1.0,
}


class Section:
    """One block of a song: a full snapshot of every track, held for N bars."""

    def __init__(self, name, bars=16, tracks=None, order=None, master_fx=None,
                 bpm=None, swing=None, automation=None, role=None, energy=None):
        self.name = name
        self.bars = int(bars)
        self.tracks = tracks or {}
        self.order = list(order or tracks or [])
        self.master_fx = master_fx or []
        self.bpm = bpm                      # None inherits the song
        self.swing = swing
        self.automation = list(automation or [])
        self.role = role or name.rstrip("0123456789")
        self.energy = ROLES.get(self.role, 0.5) if energy is None else float(energy)

    def copy(self, name=None):
        s = Section(name or self.name, self.bars, copy.deepcopy(self.tracks),
                    list(self.order), copy.deepcopy(self.master_fx), self.bpm,
                    self.swing, copy.deepcopy(self.automation), self.role, self.energy)
        return s

    def to_dict(self):
        return {"name": self.name, "bars": self.bars, "tracks": self.tracks,
                "order": self.order, "master_fx": self.master_fx, "bpm": self.bpm,
                "swing": self.swing, "automation": self.automation,
                "role": self.role, "energy": self.energy}

    @staticmethod
    def from_dict(d):
        return Section(**d)


class Song:
    """Sections in an order, with repeats. The order is the arrangement."""

    def __init__(self, name="untitled", bpm=132.0, swing=0.0, key="a", scale="minor",
                 sections=None, order=None, meta=None):
        self.name = name
        self.bpm = float(bpm)
        self.swing = float(swing)
        self.key = key
        self.scale = scale
        self.sections = sections or {}
        self.order = list(order or [])
        self.meta = meta or {}

    # -- shape -----------------------------------------------------------
    def total_bars(self):
        return sum(self.sections[n].bars for n in self.order if n in self.sections)

    def bar_span(self, index):
        """(start_bar, section) for the index-th entry in the arrangement."""
        b = 0
        for i, n in enumerate(self.order):
            sec = self.sections.get(n)
            if sec is None:
                continue
            if i == index:
                return b, sec
            b += sec.bars
        return b, None

    def section_at(self, bar):
        """(name, section, bar_within_section, index_in_order) for an absolute bar."""
        total = self.total_bars()
        if total <= 0:
            return None, None, 0, -1
        bar = int(bar) % total                       # songs loop; scrubbing wraps
        b = 0
        for i, n in enumerate(self.order):
            sec = self.sections.get(n)
            if sec is None:
                continue
            if bar < b + sec.bars:
                return n, sec, bar - b, i
            b += sec.bars
        n = self.order[-1]
        return n, self.sections[n], 0, len(self.order) - 1

    def seconds(self):
        s = 0.0
        for n in self.order:
            sec = self.sections.get(n)
            if sec:
                s += sec.bars * 240.0 / (sec.bpm or self.bpm)
        return s

    # -- the one question ------------------------------------------------
    def state_at(self, bar):
        """Resolved state for an absolute bar: tracks, order, bpm, swing, master_fx.

        Pure. Same song and bar always give the same answer, which is what makes
        the offline render byte-identical to what you heard.
        """
        name, sec, within, _ = self.section_at(bar)
        if sec is None:
            return {"tracks": {}, "order": [], "bpm": self.bpm,
                    "swing": self.swing, "master_fx": [], "section": None, "within": 0}
        st = {"tracks": copy.deepcopy(sec.tracks), "order": list(sec.order),
              "bpm": sec.bpm or self.bpm, "swing": self.swing if sec.swing is None else sec.swing,
              "master_fx": copy.deepcopy(sec.master_fx), "section": name, "within": within}
        for a in sec.automation:
            _apply_automation(st, a, within, sec.bars)
        return st

    def beat_grid(self):
        """Absolute sample index of every beat. We composed it, so this is exact -
        no beat detection, no guessing. Deck sync and quantised cues depend on it."""
        out, pos = [], 0.0
        for n in self.order:
            sec = self.sections.get(n)
            if sec is None:
                continue
            spb = SR * 60.0 / (sec.bpm or self.bpm)
            for b in range(sec.bars * 4):
                out.append(int(pos + b * spb))
            pos += sec.bars * 4 * spb
        return out

    def phrase_marks(self):
        """(sample, label) at every section start - where a DJ transition belongs."""
        out, pos = [], 0.0
        for n in self.order:
            sec = self.sections.get(n)
            if sec is None:
                continue
            out.append((int(pos), n))
            pos += sec.bars * 4 * SR * 60.0 / (sec.bpm or self.bpm)
        return out

    def energy_curve(self):
        return [(n, self.sections[n].energy, self.sections[n].bars)
                for n in self.order if n in self.sections]

    # -- persistence -----------------------------------------------------
    def to_dict(self):
        return {"format": "thud-song-1", "name": self.name, "bpm": self.bpm,
                "swing": self.swing, "key": self.key, "scale": self.scale,
                "order": self.order, "meta": self.meta,
                "sections": {k: v.to_dict() for k, v in self.sections.items()}}

    @staticmethod
    def from_dict(d):
        return Song(name=d.get("name", "untitled"), bpm=d.get("bpm", 132.0),
                    swing=d.get("swing", 0.0), key=d.get("key", "a"),
                    scale=d.get("scale", "minor"), order=d.get("order", []),
                    meta=d.get("meta", {}),
                    sections={k: Section.from_dict(v) for k, v in d.get("sections", {}).items()})

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1, sort_keys=True)
        return path

    @staticmethod
    def load(path):
        with open(path, encoding="utf-8") as f:
            return Song.from_dict(json.load(f))

    def fingerprint(self):
        """Content hash. The deck cache is keyed on this, so an unchanged song
        never re-renders and a changed one never serves a stale buffer."""
        blob = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha1(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- automation


def _apply_automation(st, a, within, bars):
    """One automation entry, resolved for the bar we are on.

    (target, lo, hi, start_bar, length_bars, curve) where target is 'bpm',
    'swing', or 'track.param' such as 'bass.fc'.
    """
    target, lo, hi = a[0], float(a[1]), float(a[2])
    start = max(0, min(int(a[3]) if len(a) > 3 else 0, max(0, bars - 1)))
    length = int(a[4]) if len(a) > 4 and a[4] else (bars - start)
    length = max(1, min(length, bars - start))   # clamp: a ramp cannot outlive
                                                 # its section, or its endpoint
                                                 # would land in the next one
    curve = CURVES.get(a[5] if len(a) > 5 else "linear", CURVES["linear"])

    if within < start:
        return
    t = 1.0 if length <= 1 else min(1.0, (within - start) / float(length - 1))
    val = lo + (hi - lo) * curve(t)

    if "." in target:
        tname, param = target.split(".", 1)
        tr = st["tracks"].get(tname)
        if tr is not None:
            tr[param] = val
    elif target in ("bpm", "swing"):
        st[target] = val


def ramp(target, lo, hi, start=0, length=None, curve="linear"):
    return [target, lo, hi, start, length, curve]


# ------------------------------------------------------------------ helpers


def from_state(name, tracks, order, bpm, swing, master_fx=None, bars=16, role="loop"):
    """Snapshot the live jam state into a one-section song. How a sketch becomes
    something you can arrange."""
    sec = Section(name, bars, copy.deepcopy(tracks), list(order),
                  copy.deepcopy(master_fx or []), role=role)
    return Song(name=name, bpm=bpm, swing=swing, sections={name: sec}, order=[name])


def render(song, render_bar_fn, bars=None, on_progress=None):
    """Render a whole song offline: ask for every bar, concatenate.

    render_bar_fn(state_dict) -> (n,2) float32. Identical consecutive states reuse
    the previous buffer, which is what makes a 16-bar repeated section cheap.
    """
    import numpy as np
    total = bars if bars is not None else song.total_bars()
    if total <= 0:
        return np.zeros((0, 2), np.float32)
    out, last_key, last_buf = [], None, None
    for b in range(total):
        st = song.state_at(b)
        key = _state_key(st)
        if key != last_key:
            last_buf = render_bar_fn(st)
            last_key = key
        out.append(last_buf)
        if on_progress and (b % 4 == 0 or b == total - 1):
            on_progress(b + 1, total)
    return np.concatenate(out, axis=0)


def _state_key(st):
    return json.dumps([st["tracks"], st["order"], st["bpm"], st["swing"],
                       st["master_fx"]], sort_keys=True, default=str)
