"""Decks: a song rendered to a buffer, and a read pointer over it.

Loading a song renders it fully, once, cached to disk under its fingerprint.
After that every DJ move - seek, loop, sync, scratch - is arithmetic on a read
pointer. No re-render, so no underrun risk in the middle of a mix and no CPU
cliff when both decks hit a dense section at once.

The decisive advantage: we composed this music, so song.beat_grid() is the exact
sample index of every beat. Real DJ software runs beat detection and gets it
approximately right. Sync, cues and loops here are sample-exact.
"""
import os
import time
import threading
import numpy as np

from .contracts import SR, COMMANDS

CACHE = ".oontzcache"
CACHE_MAX = 40                                   # files; oldest evicted first


def _cache_path(fp):
    return os.path.join(CACHE, "%s.npy" % fp)


def _evict():
    try:
        files = [(os.path.getmtime(os.path.join(CACHE, f)), f)
                 for f in os.listdir(CACHE) if f.endswith(".npy")]
    except OSError:
        return
    for _t, f in sorted(files)[:-CACHE_MAX]:
        try:
            os.remove(os.path.join(CACHE, f))
        except OSError:
            pass


class Deck:
    """One deck. read() is the only thing the audio thread calls."""

    def __init__(self, name="a"):
        self.name = name
        self.song = None
        self.buf = np.zeros((1, 2), np.float32)
        self.grid = [0]                          # sample index of every beat
        self.marks = []                          # (sample, section name)
        self.bpm = 132.0
        self.pos = 0.0                           # fractional: rate can be non-integer
        self.rate = 1.0
        self.playing = False
        self.cue = 0
        self.hotcues = [None] * 8
        self.loop = None                         # (start, end) in samples
        self.gain = 1.0
        self.progress = 1.0
        self.loading = False
        self.title = ""

    # -- loading ---------------------------------------------------------
    def load(self, song, render_fn=None, background=True):
        """Render the song to a buffer. Cached on the song's fingerprint."""
        from . import core
        from . import song as sm
        render_fn = render_fn or core.render_state
        self.song = song
        self.title = song.name
        self.bpm = song.bpm
        self.grid = song.beat_grid() or [0]
        self.marks = song.phrase_marks()
        self.loading, self.progress = True, 0.0

        def work():
            fp = song.fingerprint()
            path = _cache_path(fp)
            if os.path.exists(path):
                try:
                    self.buf = np.load(path)
                    self.progress, self.loading = 1.0, False
                    return
                except Exception:
                    pass                          # a corrupt cache just re-renders
            data = sm.render(song, render_fn,
                             on_progress=lambda b, t: setattr(self, "progress", b / float(t)))
            self.buf = np.ascontiguousarray(data.astype(np.float32))
            os.makedirs(CACHE, exist_ok=True)
            try:
                np.save(path, self.buf)
                _evict()
            except Exception:
                pass
            self.progress, self.loading = 1.0, False

        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()
        return self

    def wait(self, timeout=120):
        t0 = time.time()
        while self.loading and time.time() - t0 < timeout:
            time.sleep(0.02)
        return not self.loading

    # -- shape -----------------------------------------------------------
    @property
    def n(self):
        return len(self.buf)

    def duration(self):
        return self.n / float(SR)

    def beat(self):
        """Which beat the playhead is on."""
        p = self.pos
        lo, hi = 0, len(self.grid) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.grid[mid] <= p:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def beat_phase(self):
        """0..1 through the current beat. Two decks in sync hold this together."""
        i = self.beat()
        a = self.grid[i]
        b = self.grid[i + 1] if i + 1 < len(self.grid) else a + SR * 60.0 / self.bpm
        return 0.0 if b <= a else max(0.0, min(1.0, (self.pos - a) / float(b - a)))

    def section_at_pos(self):
        cur = ""
        for smp, name in self.marks:
            if smp <= self.pos:
                cur = name
            else:
                break
        return cur

    # -- transport -------------------------------------------------------
    def play(self):
        self.playing = True

    def pause(self):
        self.playing = False

    def toggle(self):
        self.playing = not self.playing
        return self.playing

    def seek(self, sample):
        self.pos = float(max(0, min(self.n - 1, sample)))

    def seek_beat(self, i):
        if self.grid:
            self.seek(self.grid[max(0, min(len(self.grid) - 1, int(i)))])

    def seek_phrase(self, i):
        if self.marks:
            self.seek(self.marks[max(0, min(len(self.marks) - 1, int(i)))][0])

    def quantise(self, sample=None):
        """Nearest beat to a sample. Exact, because the grid is exact."""
        p = self.pos if sample is None else sample
        if not self.grid:
            return int(p)
        i = min(range(len(self.grid)), key=lambda k: abs(self.grid[k] - p))
        return self.grid[i]

    def set_cue(self, sample=None):
        self.cue = self.quantise(sample)
        return self.cue

    def to_cue(self):
        self.seek(self.cue)

    def set_hotcue(self, i):
        if 0 <= i < 8:
            self.hotcues[i] = self.quantise()
        return self.hotcues[i]

    def jump_hotcue(self, i):
        if 0 <= i < 8 and self.hotcues[i] is not None:
            self.seek(self.hotcues[i])
            return True
        return False

    def beat_loop(self, beats):
        """Loop `beats` beats from the current beat, snapped to the grid."""
        i = self.beat()
        j = min(len(self.grid) - 1, i + int(beats))
        if j <= i:
            self.loop = None
            return None
        self.loop = (self.grid[i], self.grid[j])
        return self.loop

    def loop_exit(self):
        self.loop = None

    # -- pitch and sync --------------------------------------------------
    def set_rate(self, r):
        self.rate = max(0.5, min(2.0, float(r)))

    def effective_bpm(self):
        return self.bpm * self.rate

    def sync_to(self, other, align_phase=True):
        """Match tempo, then line the downbeats up. Both grids are exact."""
        if not other or other.bpm <= 0 or self.bpm <= 0:
            return self.rate
        self.set_rate(other.effective_bpm() / self.bpm)
        if align_phase and self.grid and other.grid:
            i = self.beat()
            target = other.beat_phase()
            a = self.grid[i]
            b = self.grid[i + 1] if i + 1 < len(self.grid) else a + SR * 60.0 / self.bpm
            self.pos = a + target * (b - a)
        return self.rate

    def nudge(self, amount):
        self.pos = max(0.0, min(self.n - 1.0, self.pos + amount * SR * 0.01))

    # -- audio -----------------------------------------------------------
    def read(self, frames):
        """Exactly `frames` stereo samples. Never raises, never leaves the buffer."""
        out = np.zeros((frames, 2), np.float32)
        if self.n <= 1 or not self.playing:
            return out
        idx = self.pos + np.arange(frames, dtype=np.float64) * self.rate
        if self.loop:
            a, b = self.loop
            span = max(1.0, b - a)
            idx = a + np.mod(idx - a, span)
        else:
            idx = np.mod(idx, self.n)
        i0 = idx.astype(np.int64)
        frac = (idx - i0)[:, None]
        i1 = (i0 + 1) % self.n
        out[:] = self.buf[i0] * (1.0 - frac) + self.buf[i1] * frac
        nxt = self.pos + frames * self.rate
        if self.loop:
            a, b = self.loop
            self.pos = a + ((nxt - a) % max(1.0, b - a))
        else:
            self.pos = nxt % self.n
        return out * self.gain


class Decks:
    """Two decks and a summed output for the mixer."""

    def __init__(self):
        self.a = Deck("a")
        self.b = Deck("b")

    def get(self, name):
        return self.a if str(name).lower() in ("a", "1") else self.b

    def mix(self, frames):
        return self.a.read(frames) + self.b.read(frames)

    def levels(self):
        return {"a": float(np.abs(self.a.buf).max() if self.a.n > 1 else 0.0),
                "b": float(np.abs(self.b.buf).max() if self.b.n > 1 else 0.0)}


DECKS = Decks()


# ---------------------------------------------------------------- commands

def _load_cmd(state, args):
    """`dload a warehouse` - render a song onto a deck.

    Not `load`: core already owns that verb for .oontz session files.
    """
    from . import core
    from . import song as sm
    if len(args) < 2:
        return "dload <a|b> <song name>"
    d = DECKS.get(args[0])
    name = args[1]
    path = name if name.endswith(".song") else "songs/%s.song" % name
    if os.path.exists(path):
        sg = sm.Song.load(path)
    elif core.ST.song is not None and name in ("this", "current"):
        sg = core.ST.song
    else:
        return "no song %r  (`song save` it first, or `lib list`)" % name
    d.load(sg)
    return "deck %s loading %s (%d bars)" % (d.name.upper(), sg.name, sg.total_bars())


def _deck_cmd(state, args):
    """`deck a play|cue|sync|loop 4|hotcue 1|rate 1.02`"""
    if not args:
        return "  ".join("%s: %s %s %s" % (
            k.upper(), (DECKS.get(k).title or "-"),
            "%.1f BPM" % DECKS.get(k).effective_bpm(),
            "playing" if DECKS.get(k).playing else "stopped") for k in ("a", "b"))
    d = DECKS.get(args[0])
    sub = args[1] if len(args) > 1 else "info"
    if sub == "play":
        return "deck %s %s" % (d.name.upper(), "playing" if d.toggle() else "paused")
    if sub == "cue":
        d.set_cue()
        return "cue at beat %d" % d.beat()
    if sub == "sync":
        other = DECKS.b if d is DECKS.a else DECKS.a
        return "rate %.4f (%.1f BPM)" % (d.sync_to(other), d.effective_bpm())
    if sub == "loop":
        n = int(args[2]) if len(args) > 2 else 4
        return "loop %d beats" % n if d.beat_loop(n) else "loop off"
    if sub == "unloop":
        d.loop_exit()
        return "loop off"
    if sub == "hotcue":
        i = int(args[2]) - 1 if len(args) > 2 else 0
        return "hotcue %d %s" % (i + 1, "jumped" if d.jump_hotcue(i) else
                                 "set at %d" % (d.set_hotcue(i) or 0))
    if sub == "rate":
        return "rate %.4f" % d.set_rate(float(args[2])) if len(args) > 2 else "rate %.4f" % d.rate
    if sub == "goto":
        d.seek_phrase(int(args[2])) if len(args) > 2 else d.to_cue()
        return "at %s" % d.section_at_pos()
    return "deck <a|b> play|cue|sync|loop N|unloop|hotcue N|rate R|goto N"


COMMANDS.update({"dload": _load_cmd, "deck": _deck_cmd})
