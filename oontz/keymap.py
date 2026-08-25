"""One table. Every key declared once.

Dispatch, the legend bar, the ? overlay, the on-screen keyboard and the docs are
all generated from BINDINGS. A displayed key cannot disagree with what the key
does, because there is only one place either could come from - which is the exact
failure that makes a keyboard instrument unusable.

    Binding(mode, key, action, label, cat, help)

`action` is a callable taking no arguments, resolved lazily by name so this module
imports cleanly during core's own initialisation.
"""

# Categories drive colour, grouping and the on-screen keyboard legend.
CATS = {
    "transport": 51,   "track": 39,    "step": 226,   "sound": 149,
    "perform":  213,   "song":  215,   "deck":  81,   "mix":  203,
    "view":     141,   "system": 244,
}

MODES = ("studio", "deck")
STEP_KEYS = "qwertyuiasdfghjk"          # two rows of eight = the sixteen pads

# QWERTY geometry, for drawing a real keyboard on screen.
ROWS = ["`1234567890-=", "qwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"]
ROW_INDENT = [0, 1, 2, 3]


class Binding:
    __slots__ = ("mode", "key", "action", "label", "cat", "help", "hold")

    def __init__(self, mode, key, action, label, cat, help="", hold=False):
        self.mode, self.key, self.action = mode, key, action
        self.label, self.cat, self.help = label, cat, help
        self.hold = hold                 # engaged while held, released on let-go

    def __repr__(self):
        return "Binding(%s %r %s)" % (self.mode, self.key, self.label)


BINDINGS = []
_BY = {}                                 # (mode, key) -> Binding


def bind(mode, key, action, label, cat, help="", hold=False):
    """Declare a key. Later declarations replace earlier ones for the same slot."""
    b = Binding(mode, key, action, label, cat, help, hold)
    if (mode, key) in _BY:
        BINDINGS.remove(_BY[(mode, key)])
    BINDINGS.append(b)
    _BY[(mode, key)] = b
    return b


def bind_many(spec):
    for row in spec:
        bind(*row)


def lookup(mode, key):
    return _BY.get((mode, key)) or _BY.get(("*", key))


def for_mode(mode):
    return [b for b in BINDINGS if b.mode in (mode, "*")]


def by_cat(mode):
    out = {}
    for b in for_mode(mode):
        out.setdefault(b.cat, []).append(b)
    for v in out.values():
        v.sort(key=lambda b: b.key)
    return out


def duplicates():
    """Two bindings on one key in one mode. Should always be empty."""
    seen, dupes = {}, []
    for b in BINDINGS:
        k = (b.mode, b.key)
        if k in seen and seen[k] is not b:
            dupes.append(k)
        seen[k] = b
    return dupes


def key_label(mode, key):
    b = lookup(mode, key)
    return b.label if b else ""


def key_cat(mode, key):
    b = lookup(mode, key)
    if b:
        return b.cat
    if key in STEP_KEYS and mode == "studio":
        return "step"
    return ""


def pretty(key):
    """Human name for a key, for legends and the overlay."""
    return {" ": "spc", "\t": "tab", "\r": "ret", "\x1b": "esc", "\x08": "bksp",
            "\x1a": "^z", "\x19": "^y", "\x03": "^c"}.get(key, key)


def legend_items(mode, focus_kind=""):
    """The keys worth showing right now, most useful first.

    Context-sensitive: a pitched track shows cutoff, a drum track shows filter.
    The legend never invents a key - it only ever selects from BINDINGS.
    """
    order = {"studio": ["transport", "step", "track", "sound", "perform", "song", "view"],
             "deck":   ["deck", "mix", "transport", "perform", "view"]}.get(mode, [])
    cats = by_cat(mode)
    out = []
    for cat in order:
        for b in cats.get(cat, []):
            if b.help.startswith("!"):               # hidden from the legend
                continue
            label = b.label
            if focus_kind == "pitched" and "filter" in label:
                label = label.replace("filter", "cutoff")
            out.append((pretty(b.key), label, b.cat))
    return out


# ---------------------------------------------------------------------------
# THE TABLE. Every key oontz responds to is declared exactly once, right here.
# ui.on_key dispatches these; keyboard_view draws them; the legend and the ?
# overlay are generated from them. selftest asserts the table and the dispatcher
# agree in BOTH directions, so a displayed key cannot lie about what it does.
#
# `action` is a dotted name resolved lazily, because core is still initialising
# when this module is imported.

_ALL = "*"

bind_many([
    # transport
    (_ALL, " ", "core.toggle_play", "play / stop", "transport", "start and stop the transport"),
    (_ALL, "R", "core.REC.toggle", "record", "transport", "start or stop recording a take"),
    (_ALL, "M", "core.mode_toggle", "mode", "system", "switch between STUDIO and DECK"),
    (_ALL, ":", "ui.cmd_mode", "command", "system", "type a command"),
    (_ALL, "?", "ui.help_overlay", "all keys", "system", "show every key"),
    (_ALL, "", "ui.cancel", "cancel", "system", "!leave command mode"),
    (_ALL, "	", "ui.cycle_view", "view", "view", "cycle the visual panel"),
    (_ALL, "", "ui.quit", "quit", "system", "!leave oontz"),
    (_ALL, "", "core.ST.undo_one", "undo", "system", "step back"),
    (_ALL, "", "core.ST.redo_one", "redo", "system", "step forward"),

    # studio - tracks and steps
    ("studio", "1", "ui.focus_track", "focus track", "track", "focus tracks 1 to 8"),
    ("studio", "z", "ui.mute_focused", "mute", "track", "mute the focused track"),
    ("studio", "x", "ui.solo_focused", "solo", "track", "solo the focused track"),
    ("studio", "n", "ui.vary_focused", "vary", "track", "mutate the focused pattern"),
    ("studio", "q", "ui.toggle_step", "steps", "step",
     "qwertyui asdfghjk are the sixteen step pads"),

    # studio - sound
    ("studio", "[", "ui.sweep_down", "filter down", "sound", "sweep the cutoff down (hold)"),
    ("studio", "]", "ui.sweep_up", "filter up", "sound", "sweep the cutoff up (hold)"),
    ("studio", "{", "ui.res_down", "res -", "sound", "less resonance"),
    ("studio", "}", "ui.res_up", "res +", "sound", "more resonance"),
    ("studio", "-", "ui.bpm_down", "bpm -1", "sound", "slower by one"),
    ("studio", "=", "ui.bpm_up", "bpm +1", "sound", "faster by one"),
    ("studio", "_", "ui.bpm_down10", "bpm -10", "sound", "!slower by ten"),
    ("studio", "+", "ui.bpm_up10", "bpm +10", "sound", "!faster by ten"),
    ("studio", ",", "ui.swing_down", "swing -", "sound", "straighten the groove"),
    ("studio", ".", "ui.swing_up", "swing +", "sound", "shuffle the offbeats"),
    ("studio", "T", "ui.tap_tempo", "tap tempo", "sound", "tap four times to set the tempo"),
    ("studio", "A", "ui.ab_compare", "A/B", "sound", "compare two versions"),

    # studio - song
    ("studio", "<", "ui.prev_section", "prev section", "song", "jump to the previous section"),
    ("studio", ">", "ui.next_section", "next section", "song", "jump to the next section"),
    ("studio", "(", "ui.scrub_back", "back 8 bars", "song", "scrub eight bars back"),
    ("studio", ")", "ui.scrub_fwd", "fwd 8 bars", "song", "scrub eight bars forward"),
    ("studio", "L", "ui.loop_section", "loop section", "song", "loop the section you are on"),

    # performance - held keys
    ("studio", "/", "ui.perf_roll", "loop roll", "perform", "beat-repeat while held", True),
    ("studio", "v", "ui.perf_stutter", "stutter", "perform", "chop while held", True),
    ("studio", "\\", "ui.perf_spinback", "spinback", "perform", "turntable spin-down", True),
    ("studio", "`", "ui.perf_tapestop", "tape stop", "perform", "pitch falls to nothing", True),
    ("studio", "c", "ui.perf_reverse", "reverse", "perform", "play backwards while held", True),
    ("studio", "b", "ui.perf_brake", "brake", "perform", "momentary slow-down", True),

    # deck
    ("deck", "1", "ui.deck_focus", "focus deck", "deck", "1 selects deck A, 2 deck B"),
    ("deck", "s", "ui.deck_sync", "sync", "deck", "match this deck to the other"),
    ("deck", "c", "ui.deck_cue", "cue", "deck", "set the cue point"),
    ("deck", "l", "ui.deck_loop", "loop 4", "deck", "four-beat loop, snapped to the grid"),
    ("deck", "u", "ui.deck_unloop", "loop off", "deck", "leave the loop"),
    ("deck", "[", "ui.deck_filter_down", "filter", "mix", "sweep this deck's filter down"),
    ("deck", "]", "ui.deck_filter_up", "filter", "mix", "sweep this deck's filter up"),
    ("deck", ",", "ui.xf_left", "xfade A", "mix", "crossfade toward A"),
    ("deck", ".", "ui.xf_right", "xfade B", "mix", "crossfade toward B"),
    ("deck", "7", "ui.kill_low", "kill low", "mix", "cut the bass on this deck"),
    ("deck", "8", "ui.kill_mid", "kill mid", "mix", "cut the mids on this deck"),
    ("deck", "9", "ui.kill_high", "kill high", "mix", "cut the treble on this deck"),
    ("deck", "/", "ui.perf_roll", "loop roll", "perform", "beat-repeat while held", True),
])


# Keys the dispatcher handles as a GROUP rather than individually, so the
# one-key-one-binding table stays honest about them.
GROUPS = {
    "1": ("studio", "12345678", "focus track 1-8"),
    "q": ("studio", STEP_KEYS, "the sixteen step pads"),
}


def expand(mode, key):
    """A key that belongs to a declared group resolves to that group's binding."""
    for rep, (m, keys, _desc) in GROUPS.items():
        if key in keys and m in (mode, _ALL):
            return lookup(mode, rep)
    return lookup(mode, key)


def handled_keys(mode):
    """Every key the table says is live in this mode, groups expanded."""
    out = set()
    for b in for_mode(mode):
        grp = GROUPS.get(b.key)
        if grp and grp[0] in (mode, _ALL):
            out |= set(grp[1])
        else:
            out.add(b.key)
    return out
