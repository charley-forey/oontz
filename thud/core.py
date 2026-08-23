"""State, sequencer, audio engine, recording, undo, and the command table.

The audio callback slices a pre-rendered bar and does nothing else. Editing
re-renders off-thread and swaps the array in on the next bar boundary.
"""
import os
import sys
import copy
import inspect
import time
import wave
import random
import threading
import functools
import collections
import numpy as np
import sounddevice as sd

from .contracts import (SR, SEED, Snapshot, TrackView, VOICES, FX, COMMANDS,
                        BAR_HOOKS, load_modules)
from . import song as songmod
from .voices import svf, note_hz, rng, v_hat, v_perc, v_bass303, v_stab

TRACK_ORDER = ["kick", "hat", "oh", "clap", "snare", "perc", "bass", "stab"]
PITCHED = ("bass", "stab")
DEFAULT_TUNE = {"hat": 8000.0, "oh": 8000.0, "perc": 320.0}
SCOPE_N = 4096


def new_track(name, voice_name=None):
    return {"voice": voice_name or name, "pat": "." * 16, "notes": [], "gain": 1.0,
            "pan": 0.0, "sc": 0.0, "hum": 0.0, "filt": None, "fc": 0.0, "res": 0.6,
            "tune": DEFAULT_TUNE.get(name, 0.0), "mute": False, "solo": False,
            "fx": []}                                   # [[name, {params}], ...]


def is_pitched(tr):
    """A track is pitched if its voice asks for a frequency. Works for any voice."""
    fn = VOICES.get(tr["voice"])
    return bool(fn) and bool({"hz", "freq"} & _params_of(fn))


def stereo(x):
    """Widen a mono voice to (n,2). Voices may return either shape."""
    x = np.asarray(x)
    return x if x.ndim == 2 else np.repeat(x[:, None], 2, axis=1)


class State:
    def __init__(self):
        self.bpm = 132.0
        self.swing = 0.0
        self.order = list(TRACK_ORDER)
        self.tracks = {n: new_track(n) for n in TRACK_ORDER}
        self.bar = np.zeros((self.n, 2), np.float32)
        self.pending = None
        self.next = None                             # bar N+1, rendered ahead
        self.pos = 0
        self.bars = 0
        self.drops = 0
        self.name = "untitled.thud"
        self.log = {}
        self.rms = {}
        self.bands = {}          # track -> per-band energy, measured not guessed
        self.focus = 0
        self.view = "perform"
        self.echo = ""
        self.echo_at = 0.0
        self.undo = collections.deque(maxlen=64)
        self.redo = collections.deque(maxlen=64)
        self.scope = np.zeros(SCOPE_N, np.float32)
        self.scope_lr = np.zeros((SCOPE_N, 2), np.float32)
        self.scope_i = 0
        self.blip = None
        self.blip_i = 0
        self.ab = [None, None]
        self.master_fx = []
        self.song = None                             # a Song, or None for jam mode
        self.songbar = 0                             # absolute bar in the song
        self.mode = "studio"                         # studio | deck
        self.section = None                          # name of the section playing
        self.edit_section = None                     # the section the editor actually holds
        self.follow = True                           # transport advances through the song
        self.loop_section = False

    @property
    def n(self):
        return round(SR * 240.0 / self.bpm)          # one 4/4 bar

    # -- undo ------------------------------------------------------------
    def mark(self):
        self.undo.append((self.bpm, self.swing, copy.deepcopy(self.tracks)))
        self.redo.clear()

    def _restore(self, snap):
        self.bpm, self.swing, self.tracks = snap[0], snap[1], snap[2]
        refresh()

    def undo_one(self):
        if not self.undo:
            return "nothing to undo"
        self.redo.append((self.bpm, self.swing, copy.deepcopy(self.tracks)))
        self._restore(self.undo.pop())
        return "undo"

    def redo_one(self):
        if not self.redo:
            return "nothing to redo"
        self.undo.append((self.bpm, self.swing, copy.deepcopy(self.tracks)))
        self._restore(self.redo.pop())
        return "redo"


ST = State()

# ---------------------------------------------------------------- sequencer


def hits(name, tr, n, swing):
    """Yield (step, sample_pos, accent) for every hit in the pattern."""
    pat = tr["pat"]
    L = len(pat) or 16
    step = n / L
    jit = rng(name).uniform(-1, 1, L) * tr["hum"] * SR / 1000.0
    for i, c in enumerate(pat):
        if c in ".-":
            continue
        p = i * step + (swing / 100.0 * step if i % 2 else 0.0) + jit[i]
        yield i, int(p) % n, c.isupper()


@functools.lru_cache(maxsize=256)
def _params_of(fn):
    """Which arguments this voice actually accepts. Cached; signatures are static."""
    try:
        return frozenset(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return frozenset(("accent",))


def voice(name, tr, accent, hz=0.0, dur=0.2, slide=0.0):
    """Render one hit.

    Voices declare what they want by parameter name and core supplies whatever the
    track has: a voice with a `tune` argument gets the track's tune, one with
    `cutoff` gets its filter frequency. That way a new voice from any module is
    playable without core knowing anything about it.
    """
    fn = VOICES.get(tr["voice"], VOICES.get(name))
    if fn is None:
        return np.zeros(1)
    want = _params_of(fn)
    kw = {}
    have = {"accent": accent, "hz": hz, "freq": hz, "dur": dur,
            "slide_from": slide, "slide": slide, "tune": tr["tune"],
            "cutoff": tr["fc"], "fc": tr["fc"], "res": tr["res"],
            "decay": tr.get("decay", 0.0)}
    for k, v in have.items():
        if k in want and v:            # falsy means "not set" - leave the voice default
            kw[k] = v
    if tr["voice"] == "oh" and "decay" in want and "decay" not in kw:
        kw["decay"] = 0.3              # open hat is the hat voice held longer
    x = fn(**kw)
    if tr["filt"] and not is_pitched(tr):
        x = svf(x, tr["fc"], tr["res"], tr["filt"])
    return x


def add_wrap(buf, v, pos):
    """Mix v into the (n,2) bar at pos. Tails wrap the loop point."""
    v = stereo(v)
    n, m = len(buf), len(v)
    if m > n:
        v, m = v[:n], n
    if pos + m <= n:
        buf[pos:pos + m] += v
    else:
        buf[pos:] += v[:n - pos]
        buf[:pos + m - n] += v[n - pos:]                 # tail wraps the loop


def duck_env(n, kick_positions):
    d = np.ones(n)
    if not kick_positions:
        return d
    t = np.arange(n)
    for p in kick_positions:
        d = np.minimum(d, 1.0 - np.exp(-((t - p) % n) / SR / 0.12))
    return d


def apply_fx(x, chain, bpm):
    """Run an effect chain over a buffer. A broken effect is skipped, not fatal."""
    for name, params in chain:
        fn = FX.get(name)
        if fn is None:
            continue
        try:
            kw = dict(params)
            if "bpm" in _params_of(fn):
                kw.setdefault("bpm", bpm)
            y = fn(x, **kw)
            if y is not None and np.shape(y)[0] == np.shape(x)[0]:
                x = y
        except Exception:
            pass
    return x


BANDS_HZ = [(20, 60), (60, 250), (250, 800), (800, 2500), (2500, 8000), (8000, 20000)]
_BAND_BINS = {}


def band_energy(buf, n=8192):
    """Real per-band energy for one track's bar.

    Sums to very nearly 1 - not exactly, because the top band stops at 20kHz and
    Nyquist is 22.05k, so a sliver of content sits outside every band.

    The frequency view used to guess this from a table of voice names, which was
    wrong the moment you pointed a track at a different voice or filtered it.
    One rfft over a slice is cheap enough to do per track per bar.
    """
    x = buf[:, 0] if getattr(buf, "ndim", 1) == 2 else buf
    if len(x) < 64:
        return [0.0] * len(BANDS_HZ)
    m = min(len(x), n)
    seg = np.asarray(x[:m], dtype=np.float64)
    if not seg.any():
        return [0.0] * len(BANDS_HZ)
    sp = np.abs(np.fft.rfft(seg * np.hanning(m)))
    key = m
    if key not in _BAND_BINS:
        f = np.fft.rfftfreq(m, 1.0 / SR)
        _BAND_BINS[key] = [(f >= lo) & (f < hi) for lo, hi in BANDS_HZ]
    tot = sp.sum() + 1e-12
    return [float(sp[mask].sum() / tot) for mask in _BAND_BINS[key]]


def render_state(d):
    """Render one bar from a resolved state dict (what Song.state_at returns).

    A tiny shim over render_bar so the song timeline and the live jam share one
    renderer - that is what keeps an offline render identical to what you heard.
    """
    tmp = State.__new__(State)
    tmp.bpm = d.get("bpm", ST.bpm)
    tmp.swing = d.get("swing", ST.swing)
    tmp.tracks = d.get("tracks", {})
    tmp.order = d.get("order", list(tmp.tracks))
    tmp.master_fx = d.get("master_fx", [])
    tmp.rms, tmp.bands = {}, {}
    out = render_bar(tmp)
    ST.rms, ST.bands = tmp.rms, tmp.bands                                  # meters follow what is playing
    return out


def render_bar(st=None):
    st = st or ST
    n = st.n
    mix = np.zeros((n, 2))
    soloed = [k for k, t in st.tracks.items() if t["solo"]]
    kicks = [p for _, p, _ in hits("kick", st.tracks["kick"], n, st.swing)]
    duck = duck_env(n, kicks)
    for name in st.order:
        tr = st.tracks.get(name)
        if tr is None:                               # order/tracks desync: skip it
            continue
        st.rms[name] = 0.0
        if not tr["pat"].strip(".-"):
            continue
        if tr["mute"] or (soloed and name not in soloed):
            continue
        buf = np.zeros((n, 2))
        L = len(tr["pat"])
        dur = round(n / L / SR, 3)
        prev = 0.0
        for i, p, acc in hits(name, tr, n, st.swing):
            hz = slide = 0.0
            if is_pitched(tr):
                tok = tr["notes"][i] if i < len(tr["notes"]) else "."
                hz = note_hz(tok.rstrip("~!"))
                slide = prev if tok.rstrip("!").endswith("~") else 0.0
                prev = hz
            add_wrap(buf, voice(name, tr, acc, hz, dur, slide), p)
        if tr["sc"] and name != "kick":
            buf *= (1.0 - tr["sc"] * (1.0 - duck))[:, None]
        p = max(-1.0, min(1.0, tr["pan"]))          # equal-power pan
        buf *= tr["gain"] * np.array([np.cos((p + 1) * np.pi / 4),
                                      np.sin((p + 1) * np.pi / 4)]) * 1.41421356
        if tr["fx"]:
            buf = stereo(apply_fx(buf, tr["fx"], st.bpm))
        st.rms[name] = float(np.sqrt((buf ** 2).mean()))
        st.bands[name] = band_energy(buf)
        mix += buf
    if st.master_fx:
        mix = stereo(apply_fx(mix, st.master_fx, st.bpm))
    return (np.tanh(mix * 1.1) * 0.95).astype(np.float32)    # soft limiter


_batch = False
_want = threading.Event()
_sched = None


def refresh():
    """A live edit. Takes effect at the next bar line, or immediately when stopped."""
    if _batch:
        return
    bar = render_bar()
    if playing():
        ST.pending = bar
        ST.next = None                               # the lookahead is now stale
        _want.set()
    else:
        ST.bar, ST.pos = bar, 0


def _schedule():
    """Keep bar N+1 rendered, so automation and arrangement can change every bar.

    Runs off the audio thread. Cold render is ~0.2s against a 1.8s bar, so there is
    room; if a render ever overruns, the callback reuses the current bar and counts
    a drop rather than glitching.

    ponytail: BAR_HOOKS commands mutate ST from this thread. State is small dicts and
    the GIL makes each write atomic; add a lock if hooks ever grow beyond parameter
    changes.
    """
    while True:
        _want.wait()
        _want.clear()
        if not playing():
            continue
        try:
            if ST.song is not None and ST.follow:
                nxt = ST.songbar + 1
                if ST.loop_section and ST.song.sections:
                    _n, sec, within, _i = ST.song.section_at(ST.songbar)
                    if sec and within + 1 >= sec.bars:
                        nxt = ST.songbar - within     # back to the top of this section
                ST.next = render_state(ST.song.state_at(nxt))
            else:
                idx = ST.bars + 1
                for hook in BAR_HOOKS:               # arrange.py drives automation here
                    for line in hook(idx) or ():
                        do(line, log=False)
                ST.next = render_bar()
        except Exception:
            ST.next = None                           # never let a bad hook kill the clock

# ------------------------------------------------------------------- engine

_stream = None


def playing():
    return _stream is not None and _stream.active


def playhead():
    """ST.pos as a plain sample index. Decaying dj effects park (ptr, elapsed) there."""
    p = ST.pos
    return float(p[0] if isinstance(p, tuple) else p)


PERF = {"fn": None, "params": {}}                    # live performance effect, from dj.py


def perform(fn=None, **params):
    """Engage a live effect (dj.py function) or, with no args, release it."""
    if fn is None and PERF["fn"] is not None:
        ST.pos = int(playhead()) % max(1, len(ST.bar))    # hand a clean index back
    PERF["fn"], PERF["params"] = fn, params


def _tap(seg, frames):
    """Feed the visual ring and the recorder. Called from the audio thread."""
    mono = seg.mean(axis=1)
    j = ST.scope_i
    k = min(frames, SCOPE_N - j)
    ST.scope[j:j + k] = mono[:k]
    ST.scope_lr[j:j + k] = seg[:k]
    if k < frames:
        ST.scope[:frames - k] = mono[k:]
        ST.scope_lr[:frames - k] = seg[k:]
    ST.scope_i = (j + frames) % SCOPE_N
    if REC.on:
        REC.q.append(seg.copy())                     # ponytail: deque append is atomic in
                                                     # CPython and this is a 2KB copy. Use a
                                                     # preallocated ring if takes run for hours.


def _deck_audio(out, frames):
    """DECK mode: two rendered songs through the mixer. Returns True if handled."""
    try:
        from . import deck, mixer
    except ImportError:
        return False
    d = deck.DECKS
    seg = mixer.MIX.process(d.a.read(frames), d.b.read(frames))
    if len(seg) != frames:
        return False
    out[:] = seg
    _tap(seg, frames)
    return True


def _callback(out, frames, _t, _status):
    if ST.mode == "deck":
        if _deck_audio(out, frames):
            return
    b, i = ST.bar, ST.pos
    n = len(b)
    if PERF["fn"] is not None:                       # live FX: pointer math, no re-render
        try:
            seg, ST.pos = PERF["fn"](b, i, frames, **PERF["params"])
            out[:] = seg
            _tap(seg, frames)
            return
        except Exception:
            PERF["fn"] = None                        # a broken effect must not kill audio
    i = int(i[0] if isinstance(i, tuple) else i) % n
    end = i + frames
    seg = b[i:end] if end <= n else np.concatenate((b[i:], b[:end - n]))

    if ST.blip is not None:                              # video/audio sync mark
        bl = ST.blip
        k = min(frames, len(bl) - ST.blip_i)
        seg = seg.copy()
        seg[:k] += bl[ST.blip_i:ST.blip_i + k, None]
        ST.blip_i += k
        if ST.blip_i >= len(bl):
            ST.blip = None

    out[:] = seg
    ST.pos = end % n
    _tap(seg, frames)
    if end >= n:                                     # bar boundary
        ST.bars += 1
        if ST.song is not None and ST.follow:
            total = ST.song.total_bars() or 1
            if ST.loop_section:
                _nm, sec, within, _ix = ST.song.section_at(ST.songbar)
                ST.songbar = (ST.songbar - within if sec and within + 1 >= sec.bars
                              else ST.songbar + 1)
            else:
                ST.songbar = (ST.songbar + 1) % total
        nxt = ST.pending if ST.pending is not None else ST.next
        if nxt is not None:
            ST.bar, ST.pending, ST.next, ST.pos = nxt, None, None, 0
        else:
            ST.drops += 1                            # render overran; reuse this bar
        _want.set()


def play():
    global _stream, _sched
    if _sched is None:
        _sched = threading.Thread(target=_schedule, daemon=True)
        _sched.start()
    if _stream is None:
        _stream = sd.OutputStream(samplerate=SR, channels=2, dtype="float32",
                                  blocksize=512, callback=_callback)
    if not _stream.active:
        ST.bar, ST.pos, ST.bars, ST.drops = render_bar(), 0, 0, 0
        ST.next = None
        _stream.start()
        _want.set()


def stop():
    if playing():
        _stream.stop()


def toggle_play():
    stop() if playing() else play()
    return "playing" if playing() else "stopped"

# ---------------------------------------------------------------- recording


class Recorder:
    """Taps the master in the callback. Captures exactly what was heard."""

    def __init__(self):
        self.on = False
        self.q = collections.deque()
        self.path = ""
        self.t0 = 0.0
        self.frames = 0
        self._w = None
        self._th = None

    def start(self):
        os.makedirs("takes", exist_ok=True)
        i = 1
        while os.path.exists("takes/take_%03d.wav" % i):
            i += 1
        self.path = "takes/take_%03d.wav" % i
        self._w = wave.open(self.path, "wb")
        self._w.setnchannels(2)
        self._w.setsampwidth(2)
        self._w.setframerate(SR)
        self.q.clear()
        self.frames = 0
        self.t0 = time.time()
        self.on = True
        self._th = threading.Thread(target=self._drain, daemon=True)
        self._th.start()
        t = np.arange(int(SR * 0.05)) / SR                # 1kHz sync blip
        ST.blip = (np.sin(2 * np.pi * 1000 * t) * np.exp(-t / 0.012) * 0.5).astype(np.float32)
        ST.blip_i = 0
        return self.path

    def _drain(self):
        while self.on or self.q:
            if self.q:
                b = self.q.popleft()
                self.frames += len(b)
                self._w.writeframes((np.clip(b, -1, 1) * 32767).astype("<i2").tobytes())
            else:
                time.sleep(0.02)
        self._w.close()

    def stop(self):
        self.on = False
        if self._th:
            self._th.join(timeout=2)
        base = self.path[:-4]
        save(base + ".thud")
        ST.name = os.path.basename(self.path)
        return "%s  %.1fs" % (self.path, self.frames / SR)

    def toggle(self):
        return "REC " + (self.stop() if self.on else self.start())

    @property
    def secs(self):
        return (time.time() - self.t0) if self.on else 0.0


REC = Recorder()

# ---------------------------------------------------------------------- dsl


def set_pattern(name, pat):
    if not pat or any(c not in "xX.-" for c in pat):
        raise ValueError("pattern uses x X . - only")
    ST.tracks[name]["pat"] = pat


def set_notes(name, toks):
    for t in toks:
        if t not in (".", "-"):
            note_hz(t.rstrip("~!"))                       # validate now, not in audio
    ST.tracks[name]["notes"] = list(toks)
    ST.tracks[name]["pat"] = "".join(
        "." if t in (".", "-") else ("X" if t.endswith("!") else "x") for t in toks)


def track_arg(a):
    if a in ST.tracks:
        return ST.tracks[a]
    raise ValueError("no track %r" % a)


def _filter(a):
    tr = track_arg(a[0])
    tr["filt"] = None if a[1] == "off" else a[1]
    if a[1] != "off":
        tr["fc"] = float(a[2])
        if "res" in a:
            tr["res"] = float(a[a.index("res") + 1])


def _render(a):
    bars = int(a[a.index("--bars") + 1]) if "--bars" in a else 8
    data = np.tile(render_bar(), (bars, 1))
    with wave.open(a[0], "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
    return "rendered %s  %d bars  %.1fs" % (a[0], bars, len(data) / SR)


def _num(v):
    try:
        return float(v)
    except ValueError:
        return {"true": True, "false": False, "on": True, "off": False}.get(v.lower(), v)


def _fx_cmd(a):
    """`fx bass drive amount 2.5` · `fx bass drive off` · `fx bass off` · target `master`."""
    chain = ST.master_fx if a[0] == "master" else track_arg(a[0])["fx"]
    if len(a) < 2 or a[1] == "off":
        chain.clear()
        return None
    name = a[1]
    if name not in FX:
        return "no effect %r  (try `fxlist`)" % name
    if len(a) > 2 and a[2] == "off":
        chain[:] = [e for e in chain if e[0] != name]
        return None
    params = {a[i]: _num(a[i + 1]) for i in range(2, len(a) - 1, 2)}
    for e in chain:
        if e[0] == name:                                 # update in place, keep the order
            e[1].update(params)
            return None
    chain.append([name, params])
    return None


# ------------------------------------------------------------------- song

SONGDIR = "songs"


def current_section():
    """The section under the playhead - what a live edit should target."""
    if ST.song is None:
        return None, None
    name, sec, _within, _i = ST.song.section_at(ST.songbar)
    return name, sec


def _sync_section():
    """Push the live track state back into the section being edited.

    Only writes when the editor is actually holding THAT section. Without this
    guard, assigning ST.song without loading a section first silently overwrites
    it with whatever unrelated state the editor happened to contain - which
    rendered a composed intro as pure silence before it was caught.
    """
    name, sec = current_section()
    if sec is not None and ST.edit_section == name:
        sec.tracks = copy.deepcopy(ST.tracks)
        sec.order = list(ST.order)
        sec.master_fx = copy.deepcopy(ST.master_fx)


def _load_section(bar):
    """Pull a section's state into the live editor."""
    if ST.song is None:
        return
    d = ST.song.state_at(bar)
    ST.tracks = d["tracks"] or ST.tracks
    ST.order = d["order"] or ST.order
    ST.master_fx = d["master_fx"]
    ST.bpm, ST.swing = d["bpm"], d["swing"]
    ST.section = ST.edit_section = d["section"]
    ST.focus = min(ST.focus, max(0, len(ST.order) - 1))


def _song_cmd(a):
    """song new|info|save|load|render|bars|key"""
    sub = a[0] if a else "info"
    if sub == "new":
        name = a[1] if len(a) > 1 else "untitled"
        ST.song = songmod.from_state(name, ST.tracks, ST.order, ST.bpm, ST.swing,
                                     ST.master_fx, bars=16, role="loop")
        ST.songbar, ST.section, ST.edit_section = 0, name, name
        return "new song %r - one section, `sec add drop 16` to grow it" % name
    if ST.song is None:
        return "no song loaded  (`song new <name>`, or `compose <style>`)"
    sg = ST.song
    if sub == "info":
        secs = "  ".join("%s:%d" % (n, sg.sections[n].bars) for n in sg.order)
        return "%s  %g BPM  %s %s  %d bars  %s  |  %s" % (
            sg.name, sg.bpm, sg.key, sg.scale, sg.total_bars(),
            _mmss(sg.seconds()), secs)
    if sub == "save":
        os.makedirs(SONGDIR, exist_ok=True)
        _sync_section()
        p = a[1] if len(a) > 1 else "%s/%s.song" % (SONGDIR, sg.name)
        return "saved " + sg.save(p if p.endswith(".song") else p + ".song")
    if sub == "load":
        p = a[1]
        p = p if p.endswith(".song") else "%s/%s.song" % (SONGDIR, p)
        ST.song = songmod.Song.load(p)
        ST.songbar = 0
        _load_section(0)
        refresh()
        return "loaded %s - %d bars, %s" % (ST.song.name, ST.song.total_bars(),
                                            _mmss(ST.song.seconds()))
    if sub == "render":
        p = a[1] if len(a) > 1 else "%s.wav" % sg.name
        return render_song(p)
    if sub == "key" and len(a) > 2:
        sg.key, sg.scale = a[1], a[2]
        return None
    return "song new|info|save|load|render|key"


def _sec_cmd(a):
    """sec add|copy|del|len|goto|role|list - editing the arrangement itself."""
    if ST.song is None:
        return "no song  (`song new <name>` first)"
    sg, sub = ST.song, (a[0] if a else "list")
    if sub == "list":
        cur = ST.section
        return "  ".join(("[%s:%d]" if n == cur else "%s:%d") % (n, sg.sections[n].bars)
                         for n in sg.order)
    if sub == "add":
        name = a[1]
        bars = int(a[2]) if len(a) > 2 else 16
        _sync_section()
        base = sg.sections.get(ST.section)
        sec = base.copy(name) if base else songmod.Section(name, bars)
        sec.bars, sec.role = bars, name.rstrip("0123456789")
        sec.energy = songmod.ROLES.get(sec.role, 0.5)
        sg.sections[name] = sec
        sg.order.append(name)
        return "added %s (%d bars) - now %d bars total" % (name, bars, sg.total_bars())
    if sub == "copy":
        src, dst = a[1], a[2]
        sg.sections[dst] = sg.sections[src].copy(dst)
        sg.order.append(dst)
        return "copied %s -> %s" % (src, dst)
    if sub in ("del", "rm"):
        n = a[1]
        sg.order = [x for x in sg.order if x != n]
        sg.sections.pop(n, None)
        return "removed " + n
    if sub == "len":
        sg.sections[a[1] if len(a) > 2 else ST.section].bars = int(a[-1])
        return None
    if sub == "goto":
        return _goto_cmd([a[1]])
    if sub == "role":
        sec = sg.sections[ST.section]
        sec.role = a[1]
        sec.energy = songmod.ROLES.get(a[1], sec.energy)
        return None
    if sub == "order":
        sg.order = list(a[1:])
        return "order: " + " ".join(sg.order)
    return "sec add|copy|del|len|goto|role|order|list"


def _goto_cmd(a):
    """goto <bar|section> - scrub anywhere, instantly."""
    if ST.song is None:
        return "no song"
    t = a[0] if a else "0"
    if t in ST.song.sections:
        bar, _sec = ST.song.bar_span(ST.song.order.index(t))
    else:
        try:
            bar = int(t)
        except ValueError:
            return "goto <bar number|section name>"
    _sync_section()
    ST.songbar = max(0, bar) % max(1, ST.song.total_bars())
    _load_section(ST.songbar)
    refresh()
    return "bar %d  ·  %s" % (ST.songbar, ST.section)


def _mmss(sec):
    return "%d:%02d" % (int(sec) // 60, int(sec) % 60)


def set_song(sg, bar=0):
    """Attach a Song and point the editor at it. Use this rather than assigning
    ST.song directly, so the editor never clobbers a section it does not hold."""
    ST.song = sg
    ST.songbar = bar
    ST.edit_section = None
    _load_section(bar)
    refresh()
    return sg


def render_song(path, on_progress=None):
    """The whole song, offline, at full quality. Deterministic."""
    if ST.song is None:
        return "no song to render"
    _sync_section()
    data = songmod.render(ST.song, render_state, on_progress=on_progress)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
    return "rendered %s  %d bars  %s" % (path, ST.song.total_bars(),
                                         _mmss(len(data) / SR))


def _mode_cmd(a):
    """Switch instruments. STUDIO builds songs, DECK mixes them."""
    m = (a[0] if a else ("deck" if ST.mode == "studio" else "studio")).lower()
    if m not in ("studio", "deck"):
        return "mode studio|deck"
    ST.mode = m
    return "mode: %s" % m.upper()


def _voice_cmd(a):
    """`voice bass reese` - point a track at any registered voice."""
    tr = track_arg(a[0])
    if a[1] not in VOICES:
        return "no voice %r  (try `voices`)" % a[1]
    tr["voice"] = a[1]
    return None


def _track_cmd(a):
    """`track add rumble [voice]` / `track del rumble`. Tracks are not fixed at 8."""
    if a[0] == "add":
        name = a[1]
        if name in ST.tracks:
            return "track %s already exists" % name
        v = a[2] if len(a) > 2 else name
        if v not in VOICES:
            return "no voice %r  (try `voices`)" % v
        ST.tracks[name] = new_track(name, v)
        ST.order.append(name)
        return None
    if a[0] in ("del", "rm"):
        if a[1] not in ST.tracks or a[1] in TRACK_ORDER:
            return "can only remove tracks you added"
        del ST.tracks[a[1]]
        ST.order.remove(a[1])
        ST.focus = min(ST.focus, len(ST.order) - 1)
        return None
    return "track add <name> [voice] | track del <name>"


def _voices_cmd(a):
    return "  ".join(sorted(VOICES))


def _songs(a):
    """The starter songbook. Templates to learn from and build on."""
    import glob
    out = []
    for f in sorted(glob.glob("songs/*.thud")):
        first = open(f, encoding="utf-8").readline().lstrip("# ").strip()
        out.append("%-14s %s" % (os.path.basename(f)[:-5], first))
    return "  ·  ".join(out) if out else "no songs/ directory"


def _open(a):
    n = a[0] if a else ""
    p = n if n.endswith(".thud") else "songs/%s.thud" % n
    if not os.path.exists(p):
        return "no song %r — try `songs`" % n
    ST.tracks = {t: new_track(t) for t in TRACK_ORDER}
    ST.order = list(TRACK_ORDER)
    ST.log.clear()
    return load(p)


def _ab(a):
    """Two full state slots. A/B what you can't hear the difference on."""
    slot = 0 if (a and a[0].lower() == "a") else 1
    cur = (ST.bpm, ST.swing, copy.deepcopy(ST.tracks))
    if ST.ab[slot] is None:
        ST.ab[slot] = cur
        return "stored in %s" % "AB"[slot]
    ST.ab[slot], other = cur, ST.ab[slot]
    ST.mark()
    ST.bpm, ST.swing, ST.tracks = other
    refresh()
    return "recalled %s" % "AB"[slot]


# name -> (handler, short alias, one-line help). Both forms always work.
CMDS = {
    "bpm":       (lambda a: setattr(ST, "bpm", float(a[0])), "t", "set tempo"),
    "swing":     (lambda a: setattr(ST, "swing", max(0.0, min(50.0, float(a[0])))), "sw", "shuffle odd 16ths"),
    "gain":      (lambda a: track_arg(a[0]).__setitem__("gain", float(a[1])), "g", "track level"),
    "pan":       (lambda a: track_arg(a[0]).__setitem__("pan", float(a[1])), "pn", "-1 left .. 1 right"),
    "tune":      (lambda a: track_arg(a[0]).__setitem__("tune", float(a[1])), "tn", "voice pitch/tone"),
    "filter":    (_filter, "f", "lp|hp|bp FC [res R] | off"),
    "sidechain": (lambda a: track_arg(a[0]).__setitem__("sc", float(a[1])), "sc", "duck against kick"),
    "humanize":  (lambda a: track_arg(a[0]).__setitem__("hum", float(a[1])), "hz", "timing jitter, ms"),
    "mute":      (lambda a: track_arg(a[0]).__setitem__("mute", not track_arg(a[0])["mute"]), "m", "toggle mute"),
    "solo":      (lambda a: track_arg(a[0]).__setitem__("solo", not track_arg(a[0])["solo"]), "so", "toggle solo"),
    "play":      (lambda a: toggle_play(), "p", "start/stop"),
    "stop":      (lambda a: stop(), None, "stop"),
    "rec":       (lambda a: REC.toggle(), "rc", "record a take"),
    "mode":      (lambda a: _mode_cmd(a), "md", "studio | deck"),
    "view":      (lambda a: setattr(ST, "view", a[0]) or ("view " + a[0]), "vw", "switch panel"),
    "song":      (_song_cmd, "sg", "new|info|save|load|render|key"),
    "sec":       (_sec_cmd, "se", "add|copy|del|len|goto|role|order|list"),
    "goto":      (_goto_cmd, "gt", "scrub to a bar or section"),
    "loopsec":   (lambda a: setattr(ST, "loop_section", not ST.loop_section)
                  or ("loop section: %s" % ("on" if ST.loop_section else "off")), "lp", "loop this section"),
    "voice":     (_voice_cmd, "vc", "point a track at a voice"),
    "track":     (_track_cmd, "tk", "add <name> [voice] | del <name>"),
    "voices":    (_voices_cmd, None, "list every registered voice"),
    "fx":        (_fx_cmd, "x", "fx <track|master> <effect> [k v ..] | off"),
    "fxlist":    (lambda a: "  ".join(sorted(FX)), None, "list every registered effect"),
    "songs":     (_songs, "ls", "list the starter songbook"),
    "open":      (_open, "o", "load a song by name"),
    "save":      (lambda a: save(a[0]), "s", "write .thud"),
    "load":      (lambda a: load(a[0]), "l", "read .thud"),
    "render":    (_render, "rn", "offline wav"),
    "ab":        (_ab, None, "A/B compare slots"),
    "undo":      (lambda a: ST.undo_one(), "u", "step back"),
    "redo":      (lambda a: ST.redo_one(), None, "step forward"),
    "gen":       (lambda a: generate("gen", a), None, "acid|techno|minimal"),
    "variation": (lambda a: generate("variation", a), "v", "mutate a pattern"),
}
NO_LOG = {"play", "stop", "rec", "save", "load", "render", "undo", "redo",
          "ab", "songs", "open", "view", "voices", "fxlist",
          "song", "sec", "goto", "loopsec", "mode"}
# How a command is keyed in the session log, which is what a .thud file is. One entry
# per thing that can be independently set, so a later edit replaces the earlier one.
KEYED = {"gain", "pan", "tune", "filter", "sidechain", "humanize", "mute", "solo", "voice"}
KEYED2 = {"fx", "track"}                                 # keyed by two arguments
ALIAS = {a: n for n, (_, a, _) in CMDS.items() if a}
ALIAS.update({"k": "kick", "h": "hat", "b": "bass", "c": "clap", "st": "stab",
              "sn": "snare", "pc": "perc"})


def complete(text):
    """Longest common prefix of matching command names, for Tab."""
    if not text or " " in text:
        return ""
    pool = sorted(set(list(CMDS) + list(ST.tracks) + list(VOICES) + list(ALIAS)))
    hits_ = [c for c in pool if c.startswith(text)]
    if not hits_:
        return ""
    out = hits_[0]
    for h in hits_[1:]:
        while not h.startswith(out):
            out = out[:-1]
    return out[len(text):]


def do(line, log=True):
    """Parse and apply one command. Returns a string to print, or None."""
    parts = line.split()
    if not parts or parts[0].startswith("#"):
        return None
    verb, args = parts[0].lower(), parts[1:]
    verb = ALIAS.get(verb, verb)

    if log and verb not in NO_LOG:
        ST.mark()

    if verb in ST.tracks:
        if is_pitched(ST.tracks[verb]):
            set_notes(verb, args)
        else:
            set_pattern(verb, args[0])
    elif verb in CMDS:
        try:
            out = CMDS[verb][0](args)
        except (IndexError, ValueError, KeyError, TypeError) as e:
            # A typo at the prompt must never raise. Show what the verb wants.
            return "? %s %s   (%s)" % (verb, CMDS[verb][2],
                                       str(e) or type(e).__name__)
        if verb in NO_LOG:
            return out
        if out:
            return out
    elif verb in COMMANDS and verb not in CMDS:
        try:
            out = COMMANDS[verb](ST, args)
        except (IndexError, ValueError, KeyError, TypeError) as e:
            return "? %s   (%s)" % (verb, str(e) or type(e).__name__)
        if isinstance(out, (list, tuple)):               # expanded to primitives
            bad = []
            for cmd in out:
                r = do(cmd, log=False)
                if isinstance(r, str) and r.startswith("?"):
                    bad.append(cmd)
            if log:
                ST.log[(verb,) + tuple(args)] = line.strip()
                refresh()
            return "%s: %d command(s) did not parse" % (verb, len(bad)) if bad else None
        return out
    else:
        return "? %s   (: then Tab to complete, or ? for keys)" % parts[0]

    if log:
        if verb in KEYED2:
            key = (verb,) + tuple(args[:2])
        elif verb in KEYED:
            key = (verb, args[0])
        else:
            key = verb
        ST.log[key] = line.strip()
        refresh()
    return None

# ------------------------------------------------------------ save / load


def save(path):
    ST.name = os.path.basename(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# thud session\n")
        f.write("bpm %g\nswing %g\n" % (ST.bpm, ST.swing))
        for k, v in ST.log.items():
            if (k[0] if isinstance(k, tuple) else k) not in ("bpm", "swing"):
                f.write(v + "\n")
    return "saved %s (%d commands)" % (path, len(ST.log))


def load(path):
    global _batch
    _batch = True
    try:
        for line in open(path, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                do(line)
    finally:
        _batch = False
    ST.name = os.path.basename(path)
    refresh()
    return "loaded " + path

# ------------------------------------------------------------- generative

SCALE = [0, 2, 3, 5, 7, 10]
NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]


def generate(verb, args):
    """Writes the *result* as a plain command, so .thud files stay literal."""
    r = random.Random()
    if verb == "variation":
        name = args[0] if args else ST.order[ST.focus]
        pat = list(ST.tracks[name]["pat"])
        for _ in range(2):
            i = r.randrange(len(pat))
            pat[i] = "." if pat[i] != "." else r.choice("xxX")
        return do("%s %s" % (name, "".join(pat)))
    kind = args[0] if args else "techno"
    if kind == "acid":
        base = NAMES.index(r.choice(["a", "c", "d", "f"]))
        toks = []
        for _ in range(16):
            if r.random() < 0.28:
                toks.append(".")
                continue
            semi = base + r.choice(SCALE + [12, 12, 0, 0])
            t = NAMES[semi % 12] + str(1 + semi // 12)
            toks.append(t + ("~" if r.random() < 0.25 else "") + ("!" if r.random() < 0.3 else ""))
        do("bass " + " ".join(toks))
        return "acid line"
    if kind == "minimal":
        for c in ("kick x...x...x...x...", "hat ..x...x...x...x.",
                  "clap ....x.......x...", "sidechain bass 0.6"):
            do(c)
        return "minimal"
    for c in ("kick X...x...X...x..x", "hat ..x...x...x.x.x.", "oh ......x.......x.",
              "clap ....x.......x...",
              "bass a1! . a1~ . c2 . a1 . g1! . a1~ . c2 . d2 .",
              "sidechain bass 0.7", "sidechain stab 0.5"):
        do(c)
    return "techno"

# -------------------------------------------------------------- snapshot


MODULES, MODULE_ERRORS = load_modules()

# A module verb that shadows a core verb is unreachable, and the module has no way
# to know. Surface it rather than letting the user hit a confusing error.
SHADOWED = sorted(set(COMMANDS) & set(CMDS))


def _wire_bar_hooks():
    """Any module exposing automation_at/commands_at_bar gets called once per bar."""
    for m in MODULES:
        mod = sys.modules["%s.%s" % (__package__, m)]
        fns = [getattr(mod, n, None) for n in ("automation_at", "commands_at_bar")]
        fns = [f for f in fns if callable(f)]
        if fns:
            BAR_HOOKS.append(lambda i, fns=fns: [c for f in fns for c in (f(i) or ())])


_wire_bar_hooks()


def snapshot(**over):
    """Immutable view of the world for one frame. Views only ever read this."""
    soloed = any(t["solo"] for t in ST.tracks.values())
    tv = []
    for name in ST.order:
        t = ST.tracks.get(name)
        if t is None:
            continue
        tv.append(TrackView(
            name=name, pat=t["pat"], notes=tuple(t["notes"]), gain=t["gain"],
            pan=t["pan"], sc=t["sc"], filt=t["filt"] or "", fc=t["fc"], res=t["res"],
            tune=t["tune"], hum=t["hum"], mute=t["mute"], solo=t["solo"],
            rms=ST.rms.get(name, 0.0), bands=tuple(ST.bands.get(name, ())),
            active=bool(t["pat"].strip(".-")) and not t["mute"] and (t["solo"] or not soloed)))
    n = ST.n
    scope = np.concatenate((ST.scope[ST.scope_i:], ST.scope[:ST.scope_i]))
    scope_lr = np.concatenate((ST.scope_lr[ST.scope_i:], ST.scope_lr[:ST.scope_i]))
    return Snapshot(
        bpm=ST.bpm, swing=ST.swing, bar=ST.bars,
        step=int(playhead() / n * 16) if playing() else -1,
        playing=playing(), name=ST.name, tracks=tuple(tv), focus=ST.focus,
        view=ST.view, echo=ST.echo if time.time() - ST.echo_at < 1.2 else "",
        recording=REC.on, rec_secs=REC.secs, rec_name=os.path.basename(REC.path),
        scope=scope, scope_lr=scope_lr, peak=float(np.abs(scope).max()), drops=ST.drops, **over)


def echo(msg):
    ST.echo, ST.echo_at = msg, time.time()
