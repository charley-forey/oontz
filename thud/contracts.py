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

Views and display state
    A view is a pure function of (Snapshot, w, h). The one sanctioned exception is
    DISPLAY state - peak-hold decay, a clip latch, a scroll offset - which by
    definition cannot come from a single frame. Keep it module-local, keep it
    small, reset it when the width changes, and never let it affect audio or leak
    to another module. Two view agents hit this independently; this is the ruling.

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
    scope: tuple = ()              # recent MONO samples for the oscilloscope
    scope_lr: tuple = ()           # the same window as (n,2) stereo, for goniometers
    spectrum: tuple = ()           # magnitude bins, already log-spaced
    peak: float = 0.0
    drops: int = 0                 # bars the scheduler failed to render in time
    overlay: str = ""              # "help" etc; suppresses the normal page


VOICES = {}
FX = {}
VIEWS = {}
COMMANDS = {}

# Called by the scheduler once per bar, before rendering bar N. Each hook gets the
# bar index and returns command strings to apply for that bar. This is how
# arrange.py drives automation without touching core.
BAR_HOOKS = []

# (key, first_owner, module_that_overwrote_it). Two modules claiming one name is a
# real bug - surfaced rather than silently resolved by import order.
COLLISIONS = []

# Optional modules. Missing ones are skipped, so the instrument runs with any
# subset of them present.
OPTIONAL = ("drums", "synths", "fx", "viz_spectrum", "viz_scope",
            "arrange", "dj", "gen", "teach", "ai")


def load_modules(pkg=__name__.rsplit(".", 1)[0]):
    """Import every optional module so it can fill the registries above."""
    import importlib
    loaded, failed = [], {}
    owner = {}                                    # registry key -> module that claimed it
    for m in OPTIONAL:
        before = {id(r): dict(r) for r in (VOICES, FX, VIEWS, COMMANDS)}
        try:
            importlib.import_module("%s.%s" % (pkg, m))
            loaded.append(m)
            for r in (VOICES, FX, VIEWS, COMMANDS):
                for k in r:
                    if k not in before[id(r)]:
                        owner[k] = m
                    elif before[id(r)][k] is not r[k]:
                        COLLISIONS.append((k, owner.get(k, "?"), m))
        except ImportError:
            pass                                  # not written yet, that is fine
        except Exception as e:                    # written but broken: say so, keep going
            failed[m] = "%s: %s" % (type(e).__name__, e)
    return loaded, failed
