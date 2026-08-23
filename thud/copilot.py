"""The copilot: the AI, present on the page rather than hidden behind a command.

Three lines, always visible:

    what is happening   narrated from the song, free, instant, always right
    what to try next    one concrete suggestion with the exact keys to press
    what it proposed    an AI answer waiting for you to accept or discard

The rule that makes it safe and makes it simple: the copilot NEVER changes
anything. It proposes commands, you press Enter. Everything it suggests is a
command you could have typed, so it lands in undo and in the .thud file like any
other edit, and you can always see exactly what it did.

It is useful with no model at all. Narration and most suggestions come from the
song itself; the model only handles open-ended intent.
"""
import time

from .contracts import PANELS, COMMANDS
from .layout import Panel
from .term import fit, DIM, OFF
from . import theme as T

# The pending proposal, waiting for Enter. One at a time, deliberately.
PENDING = {"commands": [], "why": "", "at": 0.0, "source": ""}
HISTORY = []                                     # (prompt, commands, applied)


def propose(commands, why="", source="ai"):
    PENDING.update({"commands": list(commands), "why": why,
                    "at": time.time(), "source": source})
    return PENDING


def clear():
    PENDING.update({"commands": [], "why": "", "at": 0.0, "source": ""})


def apply_pending():
    """The ONLY place the copilot's suggestions take effect, and only on Enter."""
    from . import core
    cmds = list(PENDING["commands"])
    if not cmds:
        return "nothing pending"
    bad = []
    for c in cmds:
        r = core.do(c)
        if isinstance(r, str) and r.startswith("?"):
            bad.append(c)
    HISTORY.append((PENDING.get("why", ""), cmds, True))
    clear()
    return "applied %d command%s%s" % (len(cmds), "" if len(cmds) == 1 else "s",
                                       "  (%d failed)" % len(bad) if bad else "")


# ------------------------------------------------------------------ advice

def _narrate():
    try:
        from . import director
        return director.narrate()
    except Exception:
        return ""


def advice(snap):
    """One concrete next move. Song-aware first, then mix, then teaching.

    Everything here is derived from state, so it costs nothing and is never wrong
    about what is currently loaded.
    """
    from . import core
    sg = core.ST.song
    tracks = {t.name: t for t in (snap.tracks or ())}
    live = [t for t in tracks.values() if t.active]

    if core.ST.mode == "deck":
        return _deck_advice(snap)

    if not live:
        return ("nothing playing yet", "press `:` then `compose hardtechno 5`"
                " for a whole track, or `open warehouse` for a starting point")
    if sg is None:
        return ("this is a loop, not a song",
                "press `:` then `compose %s 5` to give it an arrangement"
                % (core.ST.tracks.get("kick", {}).get("voice", "hardtechno")
                   and "hardtechno"))
    if not snap.playing:
        return ("song loaded, stopped", "press space")

    bass = tracks.get("bass")
    if bass is not None and bass.active and not bass.sc:
        return ("bass and kick are fighting for the low end",
                "press `:` then `sidechain bass 0.7` - it ducks the bass on every kick")
    if not any(t.name in ("hat", "oh") and t.active for t in live):
        return ("nothing above 8kHz", "press 2 then q e t u to put hats in")
    autos = 0
    try:
        _n, sec = core.current_section()
        autos = len(sec.automation) if sec else 0
    except Exception:
        pass
    if sg is not None and autos == 0:
        name, sec, _w, _i = sg.section_at(core.ST.songbar)
        if sec is not None and sec.role == "build":
            return ("this build is static",
                    "press `:` then `ramp bass.fc 300 4000 over %d` to open it up" % sec.bars)
    try:                                       # a measured rule beats a heuristic
        from . import theory
        if sg is not None:
            crit = theory.critique(sg, {t.name: t.bands for t in live if t.bands},
                                   (sg.meta or {}).get("style"))
            worst = [m for sev, _i, m in crit if sev == "bad"]
            if worst:
                return ("theory says: " + worst[0].split(".")[0].lower(),
                        "press `:` then `grade` for the full verdict")
    except Exception:
        pass
    if snap.peak > 0.98:
        return ("master is clipping", "press `:` then `gain kick 0.8`")
    if not snap.recording:
        return ("sounds like a take", "press R to record it")
    return ("recording", "press R again to stop, then `song save`")


def _deck_advice(snap):
    try:
        from .deck import DECKS
        from . import library as lib
    except ImportError:
        return ("deck mode", "`dload a <song>` to load a deck")
    a, b = DECKS.a, DECKS.b
    if a.n <= 1 and b.n <= 1:
        return ("both decks empty", "press `:` then `dload a <song>`  (`lib list` to see them)")
    if b.n <= 1:
        try:
            nxt = lib.suggest_next(lib.get(a.title), n=1)
            if nxt:
                s, e, why = nxt[0]
                return ("%s mixes with this at %d%% - %s" % (e["name"], int(s * 100), why[0]),
                        "press `:` then `dload b %s`" % e["name"])
        except Exception:
            pass
        return ("deck B is empty", "`dload b <song>`")
    if abs(a.effective_bpm() - b.effective_bpm()) > 0.05:
        return ("the decks are %.1f BPM apart" % abs(a.effective_bpm() - b.effective_bpm()),
                "press `:` then `deck b sync`")
    return ("decks are locked", "kill the incoming bass (`eq b low 0`), then `xf` across")


# ------------------------------------------------------------------- panel

def copilot_panel(s, w, h):
    what = _narrate()
    head, do_this = advice(s)
    rows = []
    if what:
        rows.append("  " + T.c("accent", "▸ ") + T.c("text", what))
    rows.append("  " + T.c("accent2", "▸ ") + T.c("text_dim", head + " — ") +
                T.c("text_bright", do_this))
    if PENDING["commands"]:
        rows.append("  " + T.c("warn", "▸ proposed  ") +
                    T.c("text_dim", PENDING.get("why", "")[:max(0, w - 30)]))
        for c in PENDING["commands"][:max(1, h - len(rows))]:
            rows.append("      " + T.c("ok", c))
        rows.append("  " + T.c("text_bright", "  Enter") + T.c("text_dim", " apply   ") +
                    T.c("text_bright", "Esc") + T.c("text_dim", " discard"))
    return [fit(l, w) for l in (rows + [""] * h)[:h]]


COPILOT_PANEL = Panel("copilot", copilot_panel, 40, 2, 200, 4,
                      priority=93, region="bottom")
for _m in ("studio", "deck"):
    PANELS.setdefault(_m, []).append(COPILOT_PANEL)


# ---------------------------------------------------------------- commands

def ask_cmd(state, args):
    """`ask make it darker` - proposes, never applies. Enter applies."""
    from . import core
    prompt = " ".join(args)
    if not prompt:
        return "ask <what you want>   e.g. `ask make it darker and half time`"
    try:
        from . import ai
    except ImportError:
        return "the AI bridge is not available - try `suggest` or `direct`"
    try:
        r = ai.ask(prompt, core.snapshot())
    except Exception as e:
        return "ask failed: %s" % e
    cmds = list(getattr(r, "commands", []) or [])
    rejected = list(getattr(r, "rejected", []) or [])
    if not cmds:
        return "nothing usable came back%s" % (
            "  (%d line(s) rejected)" % len(rejected) if rejected else "")
    propose(cmds, prompt, "ask")
    return "proposed %d command%s - Enter to apply, Esc to discard%s" % (
        len(cmds), "" if len(cmds) == 1 else "s",
        "  (%d rejected)" % len(rejected) if rejected else "")


def suggest_cmd(state, args):
    """Offline: one concrete move, derived from the state. Always works."""
    from . import core
    head, do_this = advice(core.snapshot())
    return "%s — %s" % (head, do_this)


def why_cmd(state, args):
    if not args:
        return "why <parameter or key>   e.g. `why res`"
    try:
        from . import teach
        return teach.why(args[0])
    except Exception:
        try:
            from . import keyboard_view as kv
            return kv.key_help(__import__("thud.core", fromlist=["x"]).ST.mode, args[0])
        except Exception:
            return "no explanation for %r yet" % args[0]


def apply_cmd(state, args):
    return apply_pending()


def discard_cmd(state, args):
    clear()
    return "discarded"


COMMANDS.update({"ask": ask_cmd, "suggest": suggest_cmd, "why": why_cmd,
                 "apply": apply_cmd, "discard": discard_cmd})
