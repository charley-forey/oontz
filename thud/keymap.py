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
