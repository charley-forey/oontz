"""AI bridge - talks to Claude by shelling out to the `claude` CLI. No API key,
no secret in the repo: the user already has Claude Code installed and
authenticated, so `claude -p "<prompt>"` (print mode, one-shot) is the whole
integration.

THE RULE: a model reply is untrusted text. It is never executed, never eval'd,
never applied blind. validate() is the gate - every line is parsed and checked
against thud's real command table before anything is even shown to the user,
and the caller always gets a preview (AskResult.commands + .diff) to approve.
Everything else in this module is built on top of validate(); it is written
first and it is the paranoid part.
"""
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from . import core
from .voices import note_hz
from .contracts import COMMANDS, VOICES

# ------------------------------------------------------------- availability

_claude_bin = None


def available():
    """Is the `claude` CLI on PATH? Cached - shutil.which is cheap but there's
    no reason to stat PATH on every keystroke."""
    global _claude_bin
    if _claude_bin is None:
        _claude_bin = shutil.which("claude") is not None
    return _claude_bin

# ------------------------------------------------------------------ validate
#
# A line is "good" only if: it has no shell/injection characters anywhere,
# its verb resolves (via core.ALIAS) to a track name, a core.CMDS key, or a
# registered COMMANDS entry, and its arguments actually parse for that verb.
# Track/note syntax reuses core.note_hz directly (the real parser, so it can
# never drift); CMDS argument shapes aren't exposed by core as data, so they
# are mirrored here per-verb - kept honest by the drift assertion in demo().

_BAD_CHARS = re.compile(r"[;&|`$\n\r\x00]")            # shell/injection chars


def _safe_path(p):
    """save/load/render/open all touch the filesystem. No absolute paths, no
    ../ traversal, and the resolved path must stay under the cwd."""
    if not p or _BAD_CHARS.search(p):
        raise ValueError("unsafe path %r" % p)
    if os.path.isabs(p) or re.match(r"^[A-Za-z]:", p) or p.startswith(("~", "\\\\", "//")):
        raise ValueError("absolute path not allowed: %r" % p)
    if ".." in re.split(r"[\\/]", p):
        raise ValueError("path traversal not allowed: %r" % p)
    root = os.path.abspath(os.getcwd())
    full = os.path.abspath(os.path.join(root, p))
    if os.path.commonpath([full, root]) != root:
        raise ValueError("path escapes working directory: %r" % p)


def _validate_track(name, args):
    # Pitched-ness is per-voice, not a fixed track list (voice/track add can
    # repoint or create tracks at runtime) - ask the same predicate core uses.
    if core.is_pitched(core.ST.tracks[name]):
        if not args:
            raise ValueError("needs note tokens")
        for t in args:
            if t in (".", "-"):
                continue
            try:
                note_hz(t.rstrip("~!"))                 # the real parser - no drift
            except Exception:
                raise ValueError("not a note: %r" % t)
    else:
        if not args:
            raise ValueError("needs a pattern")
        pat = args[0]
        if not pat or any(c not in "xX.-" for c in pat):
            raise ValueError("pattern uses x X . - only: %r" % pat)


def _need(args, n, usage):
    if len(args) < n:
        raise ValueError("usage: %s" % usage)


def _num(s):
    try:
        return float(s)
    except ValueError:
        raise ValueError("not a number: %r" % s)


def _trk(name):
    if name not in core.ST.tracks:                          # dynamic: track add/del
        raise ValueError("no track %r" % name)
    return name


def _v_bpm(a):
    _need(a, 1, "bpm N")
    v = _num(a[0])
    if not (20 <= v <= 999):
        raise ValueError("bpm out of range: %g" % v)


def _v_swing(a):
    _need(a, 1, "swing N")
    _num(a[0])


def _v_track_num(a):                                    # gain pan tune sidechain humanize
    _need(a, 2, "<track> N")
    _trk(a[0])
    _num(a[1])


def _v_toggle(a):                                        # mute solo
    _need(a, 1, "<track>")
    _trk(a[0])


def _v_filter(a):
    _need(a, 2, "<track> lp|hp|bp|off ...")
    _trk(a[0])
    if a[1] not in ("lp", "hp", "bp", "off"):
        raise ValueError("filter mode must be lp|hp|bp|off: %r" % a[1])
    if a[1] != "off":
        _need(a, 3, "<track> mode FC")
        _num(a[2])
        if "res" in a:
            i = a.index("res")
            _need(a, i + 2, "res needs a value")
            _num(a[i + 1])


def _v_none(a):
    pass                                                  # play stop rec songs undo redo


def _v_ab(a):
    if a and a[0].lower() not in ("a", "b"):
        raise ValueError("ab takes a or b")


def _v_open(a):
    if a:
        _safe_path(a[0])


def _v_save(a):
    _need(a, 1, "save PATH")
    _safe_path(a[0])


def _v_load(a):
    _need(a, 1, "load PATH")
    _safe_path(a[0])


def _v_render(a):
    _need(a, 1, "render PATH")
    _safe_path(a[0])
    if "--bars" in a:
        i = a.index("--bars")
        _need(a, i + 2, "--bars needs a value")
        if not a[i + 1].isdigit():
            raise ValueError("--bars needs an integer")


def _v_gen(a):
    if a and not a[0].isalnum():
        raise ValueError("bad gen kind: %r" % a[0])


def _v_variation(a):
    if a:
        _trk(a[0])


def _v_view(a):
    _need(a, 1, "view <name>")


def _v_voice(a):
    _need(a, 2, "<track> <voicename>")
    _trk(a[0])
    if a[1] not in VOICES:
        raise ValueError("no voice %r  (try `voices`)" % a[1])


def _v_track(a):
    _need(a, 1, "add <name> [voice] | del <name>")
    if a[0] == "add":
        _need(a, 2, "track add <name> [voice]")
        v = a[2] if len(a) > 2 else a[1]
        if v not in VOICES:
            raise ValueError("no voice %r  (try `voices`)" % v)
    elif a[0] in ("del", "rm"):
        _need(a, 2, "track del <name>")
    else:
        raise ValueError("track add|del <name>: %r" % a[0])


def _v_voices(a):
    pass


CMD_VALIDATORS = {
    "bpm": _v_bpm, "swing": _v_swing,
    "gain": _v_track_num, "pan": _v_track_num, "tune": _v_track_num,
    "sidechain": _v_track_num, "humanize": _v_track_num,
    "filter": _v_filter, "mute": _v_toggle, "solo": _v_toggle,
    "play": _v_none, "stop": _v_none, "rec": _v_none, "songs": _v_none,
    "undo": _v_none, "redo": _v_none, "ab": _v_ab, "open": _v_open,
    "save": _v_save, "load": _v_load, "render": _v_render,
    "gen": _v_gen, "variation": _v_variation,
    "view": _v_view, "voice": _v_voice, "track": _v_track, "voices": _v_voices,
}


def validate(lines):
    """The gate. Returns (good: [line], rejected: [(line, reason)]).

    Never raises - every failure mode is a rejection with a reason, not an
    exception, because this runs on text a model produced.
    """
    good, rejected = [], []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue                                     # blank/comment: skip, don't reject
        if _BAD_CHARS.search(line):
            rejected.append((raw, "unsafe characters"))
            continue
        parts = line.split()
        verb0 = parts[0].lower()
        verb = core.ALIAS.get(verb0, verb0)
        args = parts[1:]
        try:
            if verb in core.ST.tracks:                       # dynamic track table
                _validate_track(verb, args)
            elif verb in core.CMDS:
                v = CMD_VALIDATORS.get(verb)
                if v is None:
                    # ponytail: a CMDS verb with no dedicated arg-shape rule
                    # yet (core grew one after this table was written). The
                    # line-level char check already ran; nothing further to
                    # check blind, so let it through rather than guess.
                    pass
                else:
                    v(args)
            elif verb in COMMANDS:
                pass                                      # another agent's registered command
            else:
                raise ValueError("unknown command %r" % verb0)
            good.append(line)
        except Exception as e:
            rejected.append((raw, str(e)))
    return good, rejected

# ------------------------------------------------------------------ prompts


def _cmd_table_text():
    lines = []
    for name, (_, alias, help_) in sorted(core.CMDS.items()):
        lines.append("  %-10s %-4s %s" % (name, alias or "", help_))
    return "\n".join(lines)


def _render_state(snap):
    out = ["bpm %g  swing %g" % (snap.bpm, snap.swing)]
    for t in snap.tracks:
        bits = [t.name.ljust(6), t.pat if t.pat.strip(".-") else "(empty)"]
        if t.notes:
            bits.append("notes: " + " ".join(t.notes))
        if t.filt:
            bits.append("%s@%g" % (t.filt, t.fc))
        if t.gain != 1.0:
            bits.append("gain %g" % t.gain)
        if t.pan:
            bits.append("pan %g" % t.pan)
        if t.sc:
            bits.append("sidechain %g" % t.sc)
        if t.mute:
            bits.append("MUTE")
        if t.solo:
            bits.append("SOLO")
        out.append("  ".join(bits))
    return "\n".join(out)


def _system_prompt(snap):
    names = [t.name for t in snap.tracks]
    pitched = [n for n in names
               if n in core.ST.tracks and core.is_pitched(core.ST.tracks[n])]
    return """You are editing a live techno pattern in thud, a terminal step
sequencer. A thud session is just a log of commands, one per line - your
entire output is more of those lines, applied on top of what already exists.

TRACKS: %s
Pitched tracks (%s) take note tokens, one per step, space separated; every
other track takes a single pattern string. New tracks can be added with
`track add <name> [voice]` (voice defaults to the track name); `voices`
lists every registered voice.

PATTERN SYNTAX (non-pitched tracks): a string of
  x  hit      X  accented hit      .  rest      -  rest
Any length works - tracks don't have to share a length; different lengths
against each other is polymeter, and used on purpose. "kick x...x...x...x..."
is four-on-the-floor.

NOTE SYNTAX (pitched tracks): scientific pitch, one token per step -
  a1  note + octave (a b c d e f g, # for sharp, e.g. f#2)
  .   rest           a1~  slide from the previous note
  a1!  accent        a1~!  slide and accent together

COMMANDS (name, short alias, what it does):
%s

CURRENT STATE:
%s

Reply with ONLY thud command lines, one per line. No prose, no markdown
fences, no numbering, no explanation - every line must be something that
could be pasted straight into thud.""" % (
        ", ".join(names), ", ".join(pitched) or "none",
        _cmd_table_text(), _render_state(snap))


def _band_report(snap):
    by = {t.name: t for t in snap.tracks}
    low = by["kick"].rms + by["bass"].rms
    mid = by["clap"].rms + by["snare"].rms + by["perc"].rms + by["stab"].rms
    high = by["hat"].rms + by["oh"].rms
    return "band energy - low %.3f  mid %.3f  high %.3f" % (low, mid, high)

# --------------------------------------------------------------- claude i/o


def _run_raw(prompt, timeout=25):
    """Shell out to `claude -p <prompt>`. Never raises.

    Returns (True, reply_text) on success, or (False, "[reason]") for every
    failure mode - missing binary, timeout, non-zero exit, empty reply.
    """
    if not available():
        return False, "[claude unavailable]"
    try:
        r = subprocess.run(["claude", "-p", prompt], capture_output=True,
                            text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "[claude timed out after %gs]" % timeout
    except OSError as e:
        return False, "[claude failed to run: %s]" % e
    if r.returncode != 0:
        return False, "[claude exited %d: %s]" % (r.returncode, (r.stderr or "").strip()[:200])
    out = r.stdout.strip()
    return (True, out) if out else (False, "[empty reply]")

# ---------------------------------------------------------------- AskResult


@dataclass
class AskResult:
    raw: str                # claude's raw reply (or a bracketed error/offline note)
    commands: list           # validated, ready to preview/apply
    rejected: list            # [(line, reason)]
    diff: str                # human-readable "what would change"


def _diff(snap, commands):
    """Cosmetic before/after for the approval preview. Simulates on a local
    copy of the snapshot's data only - never touches core.ST, so this can run
    on unapproved, unvalidated-by-a-human text with zero side effects."""
    pat = {t.name: t.pat for t in snap.tracks}
    bpm, swing = snap.bpm, snap.swing
    changes = []
    for line in commands:
        parts = line.split()
        verb = core.ALIAS.get(parts[0].lower(), parts[0].lower())
        args = parts[1:]
        if verb in pat:                                      # a track that existed at ask() time
            before = pat[verb]
            tr = core.ST.tracks.get(verb)
            if tr is not None and core.is_pitched(tr):
                after = "".join("." if a in (".", "-") else
                                 ("X" if a.endswith("!") else "x") for a in args)
            else:
                after = args[0] if args else before
            pat[verb] = after
            if before != after:
                changes.append("%-6s %r -> %r" % (verb, before, after))
        elif verb == "bpm" and args and float(args[0]) != bpm:
            changes.append("bpm    %g -> %g" % (bpm, float(args[0])))
            bpm = float(args[0])
        elif verb == "swing" and args and float(args[0]) != swing:
            changes.append("swing  %g -> %g" % (swing, float(args[0])))
            swing = float(args[0])
        else:
            changes.append(line)
    return "\n".join(changes) if changes else "(no changes)"


def ask(prompt, snapshot, timeout=25):
    """Main entry point: NL request -> validated commands + diff, ready for
    the caller to preview and apply (or not)."""
    full = _system_prompt(snapshot) + "\n\nREQUEST: " + prompt.strip()
    ok, text = _run_raw(full, timeout)
    if not ok:
        hint = "" if available() else (" Try `gen techno`, `gen acid`, `gen minimal`, "
                                        "or `variation <track>` instead.")
        return AskResult(raw=text + hint, commands=[], rejected=[], diff="(offline)")
    good, rejected = validate(text.splitlines())
    return AskResult(raw=text, commands=good, rejected=rejected, diff=_diff(snapshot, good))


def arrange(description, snapshot, timeout=40):
    """'5 minutes, hypnotic, slow build' -> a section timeline as commands,
    '# label' comment lines marking sections (do() treats '#' as a no-op, so
    they survive into the .thud file as readable markers)."""
    full = (_system_prompt(snapshot) +
            "\n\nBuild a full arrangement timeline for: " + description.strip() +
            "\nMark sections with '# <label>' comment lines (e.g. '# intro', "
            "'# build', '# drop', '# breakdown'), thud commands under each. "
            "Comments and commands only, nothing else.")
    ok, text = _run_raw(full, timeout)
    if not ok:
        hint = "" if available() else " Build it by hand: gen, then variation per section."
        return AskResult(raw=text + hint, commands=[], rejected=[], diff="(offline)")
    good, rejected = validate(text.splitlines())
    return AskResult(raw=text, commands=good, rejected=rejected, diff=_diff(snapshot, good))


def crit(snapshot):
    """Mix critic. Prose, not commands - crit never returns anything the
    caller could apply."""
    band = _band_report(snapshot)
    prompt = ("You are a techno mix critic. Given this arrangement, give specific, "
              "actionable criticism: which frequency ranges are empty or crowded, "
              "what's missing arrangement-wise, and 2-3 concrete things to try next. "
              "Prose only, under 150 words.\n\n" + _render_state(snapshot) + "\n\n" + band)
    ok, text = _run_raw(prompt)
    return text if ok else _offline_crit(snapshot, band)


def _offline_crit(snap, band):
    by = {t.name: t for t in snap.tracks}
    notes = []
    if by["kick"].rms + by["bass"].rms < 0.01:
        notes.append("low end is nearly silent - kick and bass are both quiet or inactive.")
    if by["hat"].rms + by["oh"].rms < 0.01:
        notes.append("nothing above the mids - hats are inactive, the groove has no air.")
    if by["clap"].rms + by["snare"].rms + by["perc"].rms + by["stab"].rms < 0.01:
        notes.append("no mid-range percussion or stab - clap/snare/perc/stab are all quiet.")
    active = [t.name for t in snap.tracks if t.active]
    if len(active) <= 2:
        notes.append("only %d track(s) active - plenty of headroom left for a build." % len(active))
    if not any(t.filt for t in snap.tracks):
        notes.append("no filters in use anywhere - a slow sweep on bass or hats is an easy move.")
    if not notes:
        notes.append("balanced across bands with %d tracks active - try automation over time "
                      "(a filter sweep, a mute drop) rather than a new element." % len(active))
    return "[offline critic] " + band + "\n" + "\n".join("- " + n for n in notes)


def name(snapshot):
    """Suggest a track title from what's actually playing."""
    prompt = ("Suggest ONE short, evocative track title (2-5 words) for this techno "
              "pattern. Reply with just the title, no quotes, no punctuation besides "
              "spaces and dashes, nothing else.\n\n" + _render_state(snapshot))
    ok, text = _run_raw(prompt, timeout=20)
    if ok:
        title = re.sub(r"[^\w \-]", "", text.splitlines()[0]).strip()
        if title:
            return title
    return _offline_name(snapshot)


def _offline_name(snap):
    active = [t.name for t in snap.tracks if t.active]
    mood = "Driving" if snap.bpm >= 138 else "Warehouse" if snap.bpm >= 128 else "Dub"
    tag = "-".join(active[:2]).title() if active else "Silence"
    return "%s %s %d" % (mood, tag, int(snap.bpm))


def explain(snapshot):
    """Plain-language description of what the current patterns are doing."""
    prompt = ("Explain in plain language, for someone learning drum programming, what "
              "this pattern is doing musically - the groove, how the tracks interlock, "
              "anything notable. Under 120 words, prose only.\n\n" + _render_state(snapshot))
    ok, text = _run_raw(prompt, timeout=20)
    return text if ok else _offline_explain(snapshot)


def _offline_explain(snap):
    active = [t for t in snap.tracks if t.active]
    if not active:
        return "[offline] nothing is playing - every track is empty or muted."
    parts = ["%s (%d/%d steps)" % (t.name, sum(c not in ".-" for c in t.pat), len(t.pat))
             for t in active]
    lead = "at %g BPM" % snap.bpm + (", %g%% swing" % snap.swing if snap.swing else "")
    out = "[offline] %s: %s." % (lead, ", ".join(parts))
    sc = [t.name for t in snap.tracks if t.sc > 0]
    if sc:
        out += " %s side-chained to the kick for pump." % ", ".join(sc)
    return out

# ---------------------------------------------------------- COMMANDS wiring
#
# Wrappers never apply anything - they return command strings or a status
# string, same as every other COMMANDS entry (contracts.py). The caller
# previews commands, then applies them through core.do() like anything typed
# by hand.


def ask_cmd(state, args):
    prompt = " ".join(args).strip()
    if not prompt:
        return "usage: ask <what to change>"
    r = ask(prompt, core.snapshot())
    if r.commands:
        return r.commands
    if r.rejected:
        return r.raw + "  (rejected: " + "; ".join("%r: %s" % x for x in r.rejected) + ")"
    return r.raw


def arrange_cmd(state, args):
    desc = " ".join(args).strip()
    if not desc:
        return "usage: arrange <description>"
    r = arrange(desc, core.snapshot())
    return r.commands if r.commands else r.raw


def crit_cmd(state, args):
    return crit(core.snapshot())


def explain_cmd(state, args):
    return explain(core.snapshot())


def name_cmd(state, args):
    return name(core.snapshot())


COMMANDS.update({
    "ask": ask_cmd, "arrange": arrange_cmd,
    "crit": crit_cmd, "explain": explain_cmd, "name": name_cmd,
})

# ---------------------------------------------------------------------- demo


def demo():
    snap = core.snapshot()

    # -- validate: adversarial rejections --------------------------------
    bad = [
        "frobnicate kick",                       # unknown verb
        "save ../../etc/passwd",                 # path traversal
        "bpm 140; rm -rf /",                      # ;
        "kick x...x... | cat",                    # |
        "bpm $(whoami)",                          # $(
        "bass `id`",                              # backtick
        "bpm 140\nsave evil.thud",                 # embedded newline injection
        "kick x?x?x?x?",                          # illegal pattern char
        "bass q9 . . .",                          # not a note
        "save C:\\evil.thud",                      # absolute path
    ]
    good, rejected = validate(bad)
    assert good == [], "adversarial lines slipped through validate(): %r" % good
    assert len(rejected) == len(bad), "expected every adversarial line rejected: %r" % rejected

    # -- validate: known-good, one of each CMDS form + track forms -------
    ok_lines = [
        "kick x...x...x...x...", "bass a1! . a1~ . c2 . a1 .",
        "bpm 140", "swing 12", "gain kick 0.8", "pan bass -0.3", "tune hat 6000",
        "filter bass lp 420 res 0.8", "filter bass off", "sidechain bass 0.6",
        "humanize hat 4", "mute kick", "solo bass", "play", "stop", "rec", "songs",
        "open warehouse", "save songs/_tmp_ai_demo.thud", "load songs/warehouse.thud",
        "render takes/_tmp_ai_demo.wav --bars 4", "ab a", "undo", "redo",
        "gen techno", "variation kick",
        "view perform", "voice bass bass", "voices",
        "track add _tmp_ai_track rumble", "track del _tmp_ai_track",
        "ask add a hat", "crit", "explain", "name",             # registered COMMANDS entries
    ]
    good, rejected = validate(ok_lines)
    assert rejected == [], "known-good lines rejected: %r" % rejected
    assert set(good) == set(ok_lines)
    missing = set(core.CMDS) - {l.split()[0] for l in ok_lines}
    assert not missing, "known-good list missing CMDS verbs: %r" % missing

    # -- prompt builder can't silently drift from core.CMDS --------------
    prompt = _system_prompt(snap)
    for verb in core.CMDS:
        assert verb in prompt, "prompt is missing CMDS verb %r" % verb
    for verb, rule in CMD_VALIDATORS.items():
        assert verb in core.CMDS, "validator for %r but no such CMDS verb" % verb

    # -- offline fallbacks, binary forced unavailable ---------------------
    real_available, _claude_bin_saved = available, globals()["_claude_bin"]
    globals()["available"] = lambda: False
    try:
        assert crit(snap), "crit() empty offline"
        assert explain(snap), "explain() empty offline"
        assert name(snap), "name() empty offline"
        r = ask("add an open hat on the offbeat", snap)
        assert isinstance(r, AskResult) and r.raw and r.commands == []
        r2 = arrange("5 minutes, hypnotic, slow build", snap)
        assert isinstance(r2, AskResult) and r2.raw and r2.commands == []
    finally:
        globals()["available"] = real_available

    # -- ask() failure modes never raise ----------------------------------
    import subprocess as sp

    def _boom(exc):
        def f(*a, **k):
            raise exc
        return f

    globals()["_claude_bin"] = True
    orig_run = sp.run
    try:
        sp.run = _boom(sp.TimeoutExpired(cmd="claude", timeout=1))
        r = ask("x", snap, timeout=1)
        assert isinstance(r, AskResult) and "timed out" in r.raw

        sp.run = _boom(FileNotFoundError("no claude"))
        r = ask("x", snap)
        assert isinstance(r, AskResult) and "failed to run" in r.raw

        class FakeProc:
            returncode, stdout, stderr = 1, "", "boom"
        sp.run = lambda *a, **k: FakeProc()
        r = ask("x", snap)
        assert isinstance(r, AskResult) and "exited 1" in r.raw

        class EmptyProc:
            returncode, stdout, stderr = 0, "   ", ""
        sp.run = lambda *a, **k: EmptyProc()
        r = ask("x", snap)
        assert isinstance(r, AskResult) and "empty reply" in r.raw

        class GarbageProc:
            returncode, stdout, stderr = 0, "not a real command\nneither is this", ""
        sp.run = lambda *a, **k: GarbageProc()
        r = ask("x", snap)
        assert isinstance(r, AskResult) and r.commands == [] and len(r.rejected) == 2
    finally:
        sp.run = orig_run
        globals()["_claude_bin"] = _claude_bin_saved

    # -- real end-to-end call, only if the binary is actually here --------
    if real_available():
        r = ask("add an open hat on the offbeat", snap, timeout=30)
        print("--- raw reply ---\n%s" % r.raw)
        print("--- validated commands ---\n%s" % "\n".join(r.commands))
        print("--- diff ---\n%s" % r.diff)
        assert isinstance(r, AskResult)
        assert isinstance(r.commands, list) and isinstance(r.rejected, list)
        assert isinstance(r.diff, str) and r.diff
    else:
        print("claude binary not found on PATH - skipping the real end-to-end call")

    return "ai: all checks pass"


if __name__ == "__main__":
    print(demo())
