"""A picture of your keyboard, drawn from the key table.

Both the dispatcher and this drawing read keymap.BINDINGS, so what you see on a
key is what that key does - it is not possible for them to disagree. A key with
no binding in the current mode renders dim and unlabelled.

Three sizes: the full board, a compact two-row form, and a category summary that
still tells you what exists when there is almost no room at all.
"""
from .contracts import PANELS
from .layout import Panel
from .term import fit, vlen, DIM, OFF, INV
from . import theme as T
from . import keymap as K


def _mode(s):
    return getattr(s, "mode", None) if getattr(s, "mode", "") in K.MODES else \
        (__import__("thud.core", fromlist=["x"]).ST.mode if True else "studio")


def _cur_mode(s):
    try:
        from . import core
        return core.ST.mode
    except Exception:
        return "studio"


def _held(s):
    return set(getattr(s, "held", ()) or ())


def _cell(mode, key, held, wide=3):
    """One key cap. Colour says what family it belongs to; bright means bound."""
    b = K.expand(mode, key)
    label = key.upper() if key.isalpha() else key
    if b is None:
        return DIM + (" %s " % label)[:wide].ljust(wide) + OFF
    kind = K.CATS.get(b.cat, 250)
    txt = (" %s " % label)[:wide].ljust(wide)
    if key in held:
        return INV + T.c(kind, txt) + OFF
    return T.c(kind, txt)


def keyboard_panel(s, w, h):
    """The board. Full at w>=90, compact at w>=60, a summary below that."""
    mode = _cur_mode(s)
    held = _held(s)
    if w < 60 or h < 3:
        return _summary(mode, w, h)
    rows = K.ROWS if w >= 90 else K.ROWS[1:3]
    out = [fit("  " + T.c("text_dim", "%s keys" % mode.upper()) + "   " +
               T.c("text_dim", "lit = bound  ·  inverse = held"), w)]
    for i, row in enumerate(rows):
        indent = "  " + " " * (K.ROW_INDENT[K.ROWS.index(row)] * 2)
        caps = [_cell(mode, ch, held) for ch in row]
        out.append(fit(indent + "".join(caps), w))
    # the sixteen pads are a bank, so show them as one
    if h > len(out) + 2 and mode == "studio":
        pads = "".join(_cell(mode, ch, held) for ch in K.STEP_KEYS)
        out.append(fit("  " + T.c("text_dim", "pads ") + pads, w))
    out.append(_legend_colours(w))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


def _legend_colours(w):
    parts = []
    for cat, col in K.CATS.items():
        parts.append(T.c(col, "■") + T.c("text_dim", " " + cat))
    return fit("  " + "  ".join(parts), w)


def _summary(mode, w, h):
    """Too narrow to draw a board - say what families of keys exist."""
    cats = K.by_cat(mode)
    out = []
    for cat, bs in sorted(cats.items()):
        keys = " ".join(K.pretty(b.key) for b in bs[:6])
        out.append("  " + T.c(K.CATS.get(cat, 250), "%-9s" % cat) +
                   T.c("text_dim", keys))
    return [fit(l, w) for l in (out + [""] * h)[:h]]


def legend_bar(s, w):
    """The always-on line. Drops whole items when space runs out, never mid-word."""
    mode = _cur_mode(s)
    kind = ""
    try:
        from . import core
        t = s.tracks[min(s.focus, len(s.tracks) - 1)] if s.tracks else None
        if t is not None and core.is_pitched(core.ST.tracks.get(t.name, {})):
            kind = "pitched"
    except Exception:
        pass
    items = K.legend_items(mode, kind)
    out, used = [], 2
    for key, label, cat in items:
        piece = T.c(K.CATS.get(cat, 250), key) + " " + T.c("text_dim", label)
        cost = len(key) + len(label) + 4
        if used + cost > w:
            break
        out.append(piece)
        used += cost
    return fit("  " + T.c("border", " · ").join(out), w)


def cheatsheet(s, w, h, page=0):
    """The ? overlay: every binding in this mode, grouped, paginated if needed."""
    mode = _cur_mode(s)
    cats = K.by_cat(mode)
    order = ["transport", "track", "step", "sound", "song", "perform",
             "deck", "mix", "view", "system"]
    lines = ["", "  " + T.c("accent", "THUD — %s keys" % mode.upper()), ""]
    for cat in order:
        bs = cats.get(cat)
        if not bs:
            continue
        lines.append("  " + T.c(K.CATS.get(cat, 250), cat.upper()))
        for b in bs:
            note = b.help[1:] if b.help.startswith("!") else b.help
            lines.append("    %s  %s  %s" % (
                T.c("text_bright", "%-10s" % K.pretty(b.key)),
                T.c("text", "%-16s" % b.label),
                T.c("text_dim", note + ("  (hold)" if b.hold else ""))))
        lines.append("")
    # commands, read live so they cannot drift
    try:
        from . import core
        lines.append("  " + T.c("accent2", "COMMANDS") + T.c("text_dim", "  (press : first)"))
        for n, (_fn, alias, hlp) in sorted(core.CMDS.items()):
            lines.append("    %s  %s  %s" % (
                T.c("text_bright", "%-10s" % n),
                T.c("text_dim", "%-6s" % (alias or "")),
                T.c("text_dim", hlp)))
    except Exception:
        pass

    body = max(1, h - 2)
    pages = max(1, (len(lines) + body - 1) // body)
    page = max(0, min(pages - 1, int(page)))
    chunk = lines[page * body:(page + 1) * body]
    foot = T.c("text_dim", "  page %d/%d   any key closes%s" %
               (page + 1, pages, "   ? again for more" if pages > 1 else ""))
    return [fit(l, w) for l in (chunk + [""] * body)[:body]] + [fit(foot, w)]


def key_help(mode, key):
    b = K.expand(mode, key)
    if b is None:
        return "%r does nothing in %s mode" % (key, mode)
    note = b.help[1:] if b.help.startswith("!") else b.help
    return "%s  —  %s. %s%s" % (K.pretty(b.key), b.label, note,
                                     " Hold it." if b.hold else "")


def printable_map(mode="studio"):
    """The keymap as markdown, so docs are generated from the same table."""
    out = ["# thud keys — %s" % mode.upper(), ""]
    for cat, bs in sorted(K.by_cat(mode).items()):
        out.append("## %s" % cat)
        out.append("")
        out.append("| key | does | |")
        out.append("|---|---|---|")
        for b in bs:
            note = b.help[1:] if b.help.startswith("!") else b.help
            out.append("| `%s` | %s | %s%s |" % (K.pretty(b.key), b.label, note,
                                                 " (hold)" if b.hold else ""))
        out.append("")
    return "\n".join(out)


KEYBOARD_PANEL = Panel("keyboard", keyboard_panel, 40, 3, 120, 7,
                       priority=35, region="lower")
for _m in K.MODES:
    PANELS.setdefault(_m, []).append(KEYBOARD_PANEL)
