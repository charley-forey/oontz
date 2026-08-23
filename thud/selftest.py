"""One runnable check. asserts only - no framework, no fixtures.

Covers the M1 surface: voices, sequencer, DSL, undo, aliases, completion, the
page renderer, and the recorder. Run: python -m thud test
"""
import os
import time
import wave
import numpy as np

from .contracts import SR, Snapshot, VOICES as VOICES_, FX
from . import core, ui
from .core import ST, State, do, render_bar, hits, new_track
from .voices import (v_kick, v_hat, v_clap, v_snare, v_perc, v_bass303, v_stab,
                     note_hz)


def selftest():
    st = State()

    # -- sequencer -------------------------------------------------------
    st.tracks["kick"]["pat"] = "x..X"
    h = list(hits("kick", st.tracks["kick"], 1000, 0))
    assert [(i, a) for i, _, a in h] == [(0, False), (3, True)], h
    assert [p for _, p, _ in h] == [0, 750], h
    sw = [p for _, p, _ in hits("hat", {**new_track("hat"), "pat": "xxxx"}, 1000, 25)]
    assert sw == [0, 312, 500, 812], sw

    st.tracks["kick"]["pat"] = "x...x...x...x..."
    a, b = render_bar(st), render_bar(st)
    assert len(a) == round(SR * 240 / st.bpm) == st.n, len(a)
    assert np.array_equal(a, b), "render is not deterministic"

    # -- spectra ---------------------------------------------------------
    def peak_hz(x):
        m = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        return np.fft.rfftfreq(len(x), 1 / SR)[int(np.argmax(m))]

    def centroid(x):
        m = np.abs(np.fft.rfft(x))
        return float((m * np.fft.rfftfreq(len(x), 1 / SR)).sum() / m.sum())

    k = peak_hz(v_kick())
    assert 40 <= k <= 90, "kick fundamental at %.1fHz, want 40-90" % k
    cen = centroid(v_hat())
    assert cen > 8000, "hat centroid %.0fHz, want >8k" % cen
    assert centroid(v_clap()) > 900, "clap too dull"
    assert peak_hz(v_bass303(note_hz("a1"), 0.2)) < 200, "303 not bassy"

    from .core import stereo
    assert stereo(np.zeros(10)).shape == (10, 2), "mono widening broken"
    assert stereo(np.zeros((10, 2))).shape == (10, 2), "stereo passthrough broken"
    assert a.shape == (st.n, 2), "bar is not stereo: %s" % (a.shape,)

    for nm, v in (("kick", v_kick()), ("hat", v_hat()), ("clap", v_clap()),
                  ("snare", v_snare()), ("perc", v_perc()),
                  ("bass", v_bass303(55.0, 0.2)), ("stab", v_stab(220.0, 0.4))):
        assert np.max(np.abs(v)) <= 1.0, "%s peaks at %.2f" % (nm, np.max(np.abs(v)))
    assert np.max(np.abs(a)) <= 1.0, "master clips"

    # -- sidechain -------------------------------------------------------
    st.tracks["bass"].update(notes=["a1"] * 4, pat="xxxx")
    st.tracks["kick"].update(pat="x...", gain=0.0)
    dry = render_bar(st)
    st.tracks["bass"]["sc"] = 0.7
    wet = render_bar(st)
    w = slice(int(SR * 0.005), int(SR * 0.025))
    dry, wet = dry.mean(axis=1), wet.mean(axis=1)
    db = 20 * np.log10(np.sqrt((wet[w] ** 2).mean()) / np.sqrt((dry[w] ** 2).mean()))
    assert db <= -6.0, "sidechain only ducks %.1fdB, want >=6" % -db

    # -- mute / solo -----------------------------------------------------
    st.tracks["kick"]["gain"] = 1.0
    st.tracks["kick"]["mute"] = True
    render_bar(st)
    assert st.rms["kick"] == 0.0, "mute did not silence kick"
    st.tracks["kick"]["mute"] = False
    st.tracks["bass"]["solo"] = True
    render_bar(st)
    assert st.rms["kick"] == 0.0, "solo did not silence kick"
    assert st.rms["bass"] > 0.0, "solo silenced the soloed track"

    st.tracks["bass"]["pan"] = -1.0      # bass is still soloed, so it is the whole mix
    pl = render_bar(st)
    assert np.abs(pl[:, 0]).sum() > 8 * np.abs(pl[:, 1]).sum(), "hard-left pan leaks right"
    st.tracks["bass"]["pan"] = 0.0
    st.tracks["bass"]["solo"] = False

    # -- notes -----------------------------------------------------------
    assert abs(note_hz("a1") - 55.0) < 0.01
    assert abs(note_hz("c2") - 65.406) < 0.01
    assert abs(note_hz("f#2") - 92.499) < 0.01

    # -- dsl, aliases, completion ---------------------------------------
    do("bpm 140")
    assert ST.bpm == 140.0
    do("t 132")                                   # alias for bpm
    assert ST.bpm == 132.0
    do("k x...x...x...x...")                      # alias for kick
    assert ST.tracks["kick"]["pat"] == "x...x...x...x..."
    assert do("nonsense").startswith("?")
    assert core.complete("sid") == "echain"
    assert core.complete("zzz") == ""

    # -- undo / redo -----------------------------------------------------
    before = ST.tracks["kick"]["pat"]
    do("kick X...............")
    assert ST.tracks["kick"]["pat"] == "X..............."
    ST.undo_one()
    assert ST.tracks["kick"]["pat"] == before, "undo did not restore"
    ST.redo_one()
    assert ST.tracks["kick"]["pat"] == "X..............."
    ST.undo_one()

    # -- save / load round-trip -----------------------------------------
    do("gen techno")
    do("sidechain bass 0.7")
    do("pan hat -0.4")
    if "sub" in VOICES_:                      # a pitched voice takes notes, not a pattern
        do("track add sub2 sub")
        do("sub2 a1 . . . a1 . . .")
    else:
        do("track add extra kick")
        do("extra x.......")
    if FX:
        do("fx bass %s" % (sorted(FX)[0]))
    p = "_selftest_%d.thud" % os.getpid()   # unique: tests run concurrently
    do("save " + p)
    want = render_bar()
    ST.tracks = {n: new_track(n) for n in core.TRACK_ORDER}
    ST.order = list(core.TRACK_ORDER)
    ST.master_fx = []
    do("load " + p)
    got = render_bar()
    assert np.array_equal(want, got), "save/load did not round-trip"
    os.remove(p)

    # -- fx chains, and everything survives a save --------------------
    if FX:
        eff = "drive" if "drive" in FX else sorted(FX)[0]
        assert do("fx bass %s" % eff) is None, "fx command failed"
        assert do("fx master %s" % eff) is None
        assert do("fx bass nosucheffect").startswith("no effect")
        assert ST.tracks["bass"]["fx"] and ST.master_fx, "fx chain not stored"
        dirty = render_bar()
        assert np.max(np.abs(dirty)) <= 1.0, "fx chain clips the master"
        assert not np.isnan(dirty).any(), "fx chain produced NaN"
        do("fx bass off")
        do("fx master off")
        assert not ST.tracks["bass"]["fx"] and not ST.master_fx, "fx off did not clear"

    # -- page renders, every line fits exactly ---------------------------
    snap = core.snapshot(mode="play", hint="x", cmdline="", complete="")
    for W, H in ((80, 24), (120, 40), (60, 16)):
        rows = ui.build(snap, W, H)
        assert len(rows) == H, "page is %d rows, want %d" % (len(rows), H)
        for r in rows:
            assert ui.vlen(r) == W, "row is %d cols, want %d: %r" % (ui.vlen(r), W, r[:40])
        hp = ui.build(core.snapshot(overlay="help"), W, H)
        assert any("every key" in ui.ANSI.sub("", r) for r in hp), "help overlay empty"

    # -- a long track name must not break row alignment ----------------
    do("track add verylongname kick")
    do("verylongname x...............")
    for W in (80, 120):
        for r in ui.build(core.snapshot(), W, 24):
            assert ui.vlen(r) == W, "long track name broke the grid at w=%d" % W
    do("track del verylongname")

    # -- keys drive state ------------------------------------------------
    ST.focus = 0
    ui.on_key("2", snap)
    assert ST.focus == 1, "digit key did not move focus"
    pat0 = ST.tracks["hat"]["pat"]
    ui.on_key("q", core.snapshot())
    assert ST.tracks["hat"]["pat"] != pat0, "step key did not toggle a step"
    assert ST.tracks["hat"]["pat"][0] in "xX"
    fc0 = ST.tracks["hat"]["fc"] or 8000.0
    ui.on_key("]", core.snapshot())
    assert ST.tracks["hat"]["fc"] > fc0, "] did not raise cutoff"
    bpm0 = ST.bpm
    ui.on_key("=", core.snapshot())
    assert ST.bpm == bpm0 + 1
    ui.on_key("z", core.snapshot())
    assert ST.tracks["hat"]["mute"] is True
    ui.on_key("z", core.snapshot())

    # -- dynamic tracks and voice assignment ----------------------------
    from .contracts import VOICES
    n0 = len(ST.order)
    assert do("track add rumbletest rumble") is None, "track add failed"
    assert ST.order[-1] == "rumbletest" and len(ST.order) == n0 + 1
    do("rumbletest x...............")
    render_bar()
    assert ST.rms["rumbletest"] > 0.0, "added track made no sound"
    assert do("track add x nosuchvoice").startswith("no voice")
    assert do("voice rumbletest nosuchvoice").startswith("no voice")
    assert do("track del kick").startswith("can only"), "removed a builtin track"
    do("track del rumbletest")
    assert "rumbletest" not in ST.tracks and len(ST.order) == n0
    if "reese" in VOICES:                        # pitched-ness follows the voice
        do("track add reesetest reese")
        assert core.is_pitched(ST.tracks["reesetest"]), "reese track is not pitched"
        do("reesetest a1 . c2 .")
        assert ST.tracks["reesetest"]["pat"] == "x.x."
        do("track del reesetest")
    assert not core.is_pitched(ST.tracks["kick"]), "kick should not be pitched"
    assert core.is_pitched(ST.tracks["bass"]), "bass should be pitched"

    # -- recorder writes a real wav of the right length ------------------
    core.REC.start()
    blk = np.zeros((512, 2), np.float32)
    for _ in range(20):
        core.REC.q.append(blk.copy())
    time.sleep(0.4)
    core.REC.stop()
    with wave.open(core.REC.path) as f:
        assert f.getnchannels() == 2, "take is not stereo"
        assert f.getnframes() == 20 * 512, "recorded %d frames, want %d" % (f.getnframes(), 20 * 512)
        assert f.getframerate() == SR
    assert os.path.exists(core.REC.path[:-4] + ".thud"), "take did not save its .thud"
    for f in (core.REC.path, core.REC.path[:-4] + ".thud"):
        for _ in range(20):                      # the writer thread may still hold the
            try:                                 # handle for a moment on Windows
                os.remove(f)
                break
            except PermissionError:
                time.sleep(0.05)
    try:
        os.rmdir("takes")
    except OSError:
        pass

    return ("all checks pass  ·  kick %.0fHz  ·  hat centroid %.0fHz  ·  duck %.1fdB"
            "  ·  page + keys + undo + rec ok" % (k, cen, -db))
