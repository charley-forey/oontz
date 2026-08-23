"""FROZEN. The seams between core and every agent module.

Change these only through the orchestrator, versioned. Everything else in thud
is allowed to churn; this file is what lets ten agents work at once without a
merge queue.

THE RULE: agents add entries to the registries below. No agent edits core.py.
Integration is a dict entry, so there is nothing to conflict.

Audio conventions
    SR = 44100, peak <= 1.0 at every stage, float32 or float64.
    The bar and the master bus are STEREO, shape (n, 2).
    A voice may return mono (n,) or stereo (n, 2) - core.stereo() widens mono, so
    write mono unless the voice genuinely has a stereo image (detuned stacks,
    wide hats, ping-pong delays).
    Every voice is pure, seeded off SEED, and safe to lru_cache: hashable args
    only, no ndarray parameters.

Registries
    VOICES   : dict[str, f(**hashable) -> ndarray]        drums.py synths.py
    FX       : dict[str, f(x, **params) -> ndarray]       fx.py
    VIEWS    : dict[str, f(Snapshot, w, h) -> list[str]]  viz_*.py
    COMMANDS : dict[str, f(state, args) -> list[str]]     arrange.py dj.py gen.py
    hint(Snapshot) -> str | None                          teach.py
    ask(prompt, Snapshot) -> list[str]                    ai.py

A COMMANDS function returns thud command strings, never mutated state. That is
what keeps generative and AI code honest: everything they do is expressible as
something you could have typed, so it lands in the undo stack and the .thud file
like any other edit.
"""
from dataclasses import dataclass, field

SR = 44100
SEED = 1312
TAU = 6.283185307179586
CHANNELS = 2

VERSION = "2.0-M1"


@dataclass(frozen=True)
class TrackView:
    """One track, as the UI sees it. Read-only by construction."""
    name: str
    pat: str
    notes: tuple = ()
    gain: float = 1.0
    pan: float = 0.0
    sc: float = 0.0
    filt: str = ""
    fc: float = 0.0
    res: float = 0.6
    tune: float = 0.0
    hum: float = 0.0
    mute: bool = False
    solo: bool = False
    rms: float = 0.0               # of the current bar, per track
    active: bool = False


@dataclass(frozen=True)
class Snapshot:
    """Everything a view needs for one frame. Handed to pure render functions.

    Nobody mutates this. core builds a new one per frame; views only read.
    """
    bpm: float = 132.0
    swing: float = 0.0
    bar: int = 0
    step: int = -1                 # -1 when stopped
    playing: bool = False
    name: str = "untitled.thud"
    tracks: tuple = ()             # tuple[TrackView, ...]
    focus: int = 0                 # index into tracks
    mode: str = "play"             # play | cmd
    view: str = "perform"
    cmdline: str = ""
    complete: str = ""             # ghost text for tab-completion
    echo: str = ""                 # "kick lp 1200 -> 980", cleared after ~1s
    hint: str = ""
    recording: bool = False
    rec_secs: float = 0.0
    rec_name: str = ""
    flash: bool = False            # one white frame, the video sync mark
    scope: tuple = ()              # recent samples for the oscilloscope
    spectrum: tuple = ()           # magnitude bins, already log-spaced
    peak: float = 0.0
    drops: int = 0                 # bars the scheduler failed to render in time
    overlay: str = ""              # "help" etc; suppresses the normal page


VOICES = {}
FX = {}
VIEWS = {}
COMMANDS = {}
