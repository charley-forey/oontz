"""The harness that drives the whole app and tries to break it.

Every module tests itself. Nothing tested them together, and integration is where
this breaks. Checks skip gracefully when a module is absent, so this is useful at
any point in the build.

    python -m oontz.qa            everything
    python -m oontz.qa --quick    the fast subset
    python -m oontz.qa --bless    update the golden render hashes
"""
import os
import sys
import time
import json
import random
import hashlib
import numpy as np

RESULTS = []
GOLDEN = os.path.join("tests", "golden.json")


def check(name, fn, quick=True):
    t0 = time.time()
    try:
        detail = fn()
        RESULTS.append((name, "pass", detail or "", time.time() - t0))
    except SkipCheck as s:
        RESULTS.append((name, "skip", str(s), time.time() - t0))
    except AssertionError as e:
        RESULTS.append((name, "FAIL", str(e) or "assertion", time.time() - t0))
    except Exception as e:
        RESULTS.append((name, "FAIL", "%s: %s" % (type(e).__name__, e), time.time() - t0))


class SkipCheck(Exception):
    pass


def _mod(name):
    try:
        return __import__("oontz." + name, fromlist=["x"])
    except ImportError:
        raise SkipCheck("%s not present" % name)


# ------------------------------------------------------------- 1. registries

def c_registries():
    from oontz import core
    from oontz.contracts import COLLISIONS
    assert not COLLISIONS, "registry collisions: %s" % (COLLISIONS,)
    assert not core.MODULE_ERRORS, "modules failed to import: %s" % (core.MODULE_ERRORS,)
    return "%d modules, no collisions, no import errors" % len(core.MODULES)


def c_voices():
    from oontz.contracts import VOICES
    from oontz import core
    bad = []
    for name, fn in VOICES.items():
        try:
            x = core.stereo(fn())
        except TypeError:
            try:
                x = core.stereo(fn(hz=110.0, dur=0.2))
            except Exception as e:
                bad.append("%s: %s" % (name, e))
                continue
        except Exception as e:
            bad.append("%s: %s" % (name, e))
            continue
        if x.ndim != 2 or x.shape[1] != 2:
            bad.append("%s: shape %s" % (name, x.shape))
        elif not np.isfinite(x).all():
            bad.append("%s: non-finite" % name)
        elif np.abs(x).max() > 1.0:
            bad.append("%s: peaks %.2f" % (name, np.abs(x).max()))
    assert not bad, "; ".join(bad[:5])
    return "%d voices all legal shape, finite, <=0dBFS" % len(VOICES)


def c_fx():
    from oontz.contracts import FX
    bad = []
    mono = (np.sin(np.linspace(0, 200, 4096)) * 0.4).astype(np.float32)
    st = np.stack([mono, mono * 0.9], axis=1)
    for name, fn in FX.items():
        for sig in (mono, st):
            before = sig.copy()
            try:
                y = fn(sig)
            except TypeError:
                continue                             # perform FX take (bar,pos,frames)
            except Exception as e:
                bad.append("%s: %s" % (name, e))
                break
            if y is None:
                continue
            y = np.asarray(y)
            if y.shape != sig.shape:
                bad.append("%s: %s -> %s" % (name, sig.shape, y.shape))
            if not np.array_equal(before, sig):
                bad.append("%s mutated its input" % name)
            if not np.isfinite(y).all():
                bad.append("%s: non-finite" % name)
    assert not bad, "; ".join(sorted(set(bad))[:5])
    return "%d effects: shape preserved, input untouched, finite" % len(FX)


def c_views():
    from oontz.contracts import VIEWS
    from oontz import core, ui
    snap = core.snapshot()
    bad = []
    for name, fn in VIEWS.items():
        for w, h in ((60, 4), (100, 8), (200, 12)):
            try:
                for line in fn(snap, w, h):
                    if ui.vlen(line) != w:
                        bad.append("%s at %d: %d cols" % (name, w, ui.vlen(line)))
                        break
            except Exception as e:
                bad.append("%s: %s" % (name, e))
                break
    assert not bad, "; ".join(bad[:4])
    return "%d views exact-width at 3 sizes" % len(VIEWS)


def c_keymap():
    km = _mod("keymap")
    assert not km.duplicates(), "duplicate bindings: %s" % (km.duplicates(),)
    for b in km.BINDINGS:
        assert b.label and b.cat in km.CATS, "bad binding %r" % (b,)
    return "%d bindings, %d studio keys, no duplicates" % (
        len(km.BINDINGS), len(km.handled_keys("studio")))


# --------------------------------------------------------- 2. command fuzzer

FUZZ_ARGS = ["", "0", "-1", "1e9", "-1e9", "nan", "inf", "0.5", "999999",
             "kick", "nosuchtrack", "x...x...", "!!!!", "a1", "zz9", "../etc/passwd",
             "a b c", "éèê", "-", "--", "1 2 3 4 5 6 7 8"]


def c_fuzz(n=2500):
    from oontz import core
    from oontz.contracts import COMMANDS
    import tempfile
    r = random.Random(20240823)
    verbs = list(core.CMDS) + list(COMMANDS) + list(core.ST.tracks)
    crashes = []
    core.OUTDIR = tempfile.mkdtemp(prefix="oontz-fuzz-")   # fuzzed `save`/`render` land here, not in the repo
    for _ in range(n):
        v = r.choice(verbs)
        args = [r.choice(FUZZ_ARGS) for _ in range(r.randrange(0, 4))]
        line = (v + " " + " ".join(args)).strip()
        try:
            core.do(line, log=False)
        except SystemExit:
            pass
        except Exception as e:
            crashes.append("%r -> %s: %s" % (line, type(e).__name__, e))
    assert not crashes, "%d uncaught: %s" % (len(crashes), crashes[:3])
    # and the state must still be usable afterwards
    core.do("open warehouse")
    bar = core.render_bar()
    assert np.isfinite(bar).all() and np.abs(bar).max() <= 1.0, "fuzzing corrupted state"
    return "%d random command lines, 0 uncaught exceptions, state still renders" % n


# ---------------------------------------------------------- 3. song invariants

def c_song():
    from oontz import core, song as sm
    cp = _mod("compose")
    sg = cp.compose_song("hardtechno", 2.0, seed=42)
    total = sg.total_bars()
    for b in range(total):
        st = sg.state_at(b)
        assert st["tracks"] is not None and st["bpm"] > 0, "state_at broke at bar %d" % b
    # boundaries exact
    acc = 0
    for n in sg.order:
        name, _sec, within, _i = sg.section_at(acc)
        assert name == n and within == 0, "boundary wrong at bar %d" % acc
        acc += sg.sections[n].bars
    # automation endpoints exact
    for n in sg.order:
        for a in sg.sections[n].automation:
            tgt, lo, hi = a[0], float(a[1]), float(a[2])
            start = int(a[3]) if len(a) > 3 else 0
            bars = sg.sections[n].bars
            start = max(0, min(start, bars - 1))
            length = int(a[4]) if len(a) > 4 and a[4] else (bars - start)
            length = max(1, min(length, bars - start))   # same clamp as song.py
            base, _s = sg.bar_span(sg.order.index(n))
            s0 = sg.state_at(base + start)
            s1 = sg.state_at(base + start + length - 1)
            for st, want in ((s0, lo), (s1, hi)):
                if "." in tgt:
                    tn, pm = tgt.split(".", 1)
                    got = st["tracks"].get(tn, {}).get(pm)
                else:
                    got = st.get(tgt)
                if got is not None:
                    assert abs(got - want) < 1e-6, \
                        "%s endpoint %.3f, want %.3f" % (tgt, got, want)
    # deterministic render, exact length
    a = sm.render(sg, core.render_state)
    b = sm.render(sg, core.render_state)
    assert np.array_equal(a, b), "render not deterministic"
    exp = sum(round(44100 * 240.0 / (sg.sections[n].bpm or sg.bpm))
              * sg.sections[n].bars for n in sg.order)
    assert len(a) == exp, "length %d, expected %d" % (len(a), exp)
    return "%d bars: boundaries exact, automation endpoints exact, render byte-identical" % total


def c_scrub():
    """A bar rendered from a scrub must equal that bar of the full render."""
    from oontz import core, song as sm
    cp = _mod("compose")
    sg = cp.compose_song("acid", 1.0, seed=7)
    full = sm.render(sg, core.render_state)
    n = round(44100 * 240.0 / sg.bpm)
    for b in (0, 3, sg.total_bars() // 2, sg.total_bars() - 1):
        one = core.render_state(sg.state_at(b))
        assert np.array_equal(one, full[b * n:(b + 1) * n]), "scrub mismatch at bar %d" % b
    return "scrubbed bars match the offline render sample-for-sample"


# --------------------------------------------------------------- 4. layout

def c_layout():
    from oontz import core, ui
    from oontz.contracts import PANELS
    from oontz.layout import solve, compose as lcompose
    snap = core.snapshot()
    tested = 0
    for mode in ("studio", "deck"):
        panels = PANELS.get(mode) or []
        if not panels:
            continue
        for w in (80, 100, 120, 160, 200, 240):
            for h in (24, 30, 40, 50, 60):
                placed = solve(panels, w, h)
                screen = lcompose(placed, snap, w, h)
                assert len(screen) == h, "%s %dx%d: %d rows" % (mode, w, h, len(screen))
                for row in screen:
                    assert ui.vlen(row) == w, \
                        "%s %dx%d: row is %d cols" % (mode, w, h, ui.vlen(row))
                for p in placed:
                    assert p.w >= p.panel.min_w and p.h >= p.panel.min_h, \
                        "%s under minimum at %dx%d" % (p.panel.name, w, h)
                # no overlap
                for i, p in enumerate(placed):
                    for q in placed[i + 1:]:
                        if not (p.x + p.w <= q.x or q.x + q.w <= p.x or
                                p.y + p.h <= q.y or q.y + q.h <= p.y):
                            raise AssertionError("%s overlaps %s at %dx%d" %
                                                 (p.panel.name, q.panel.name, w, h))
                assert lcompose(solve(panels, w, h), snap, w, h) == screen, "not stable"
                tested += 1
    assert tested, "no panels registered"
    return "%d size/mode combinations: exact width, no overlap, above minimums, stable" % tested


# ----------------------------------------------------------------- 5. soak

def c_soak(minutes=2.0):
    """Drive the callback by hand, so no audio hardware is needed."""
    from oontz import core
    cp = _mod("compose")
    core.set_song(cp.compose_song("hardtechno", 1.0, seed=5))
    core.ST.bar = core.render_bar()
    core.ST.pos, core.ST.bars, core.ST.drops = 0, 0, 0
    r = random.Random(7)
    worst, frames_done, blocks = 0.0, 0, 0
    target = int(44100 * 60 * minutes)
    while frames_done < target:
        f = r.choice([37, 64, 128, 256, 511, 512, 1024])
        out = np.zeros((f, 2), np.float32)
        t0 = time.time()
        core._callback(out, f, None, None)
        dt = time.time() - t0
        worst = max(worst, dt / (f / 44100.0))
        assert np.isfinite(out).all(), "non-finite audio in the callback"
        assert np.abs(out).max() <= 1.001, "callback output exceeded 0dBFS"
        frames_done += f
        blocks += 1
        if blocks % 400 == 0:                        # edits while it runs
            core.do(r.choice(["kick x...x...x...x...", "hat ..x...x...x...x.",
                              "bpm 146", "swing 8"]), log=False)
        if blocks % 900 == 0 and core.ST.song is not None:
            core.do("goto %d" % r.randrange(0, max(1, core.ST.song.total_bars())))
    return ("%.0f min simulated, %d blocks, worst callback %.1f%% of its budget, %d drops"
            % (minutes, blocks, worst * 100, core.ST.drops))


def c_perf_fx():
    """Every dj effect, driven hard, must stay in bounds."""
    dj = _mod("dj")
    from oontz import core
    bar = core.render_bar()
    r = random.Random(3)
    for name, fn in dj.PERFORM.items():
        pos = 0.0
        for _ in range(400):
            f = r.choice([64, 128, 512])
            try:
                seg, pos = fn(bar, pos, f)
            except TypeError:
                break
            assert np.shape(seg) == (f, 2), "%s returned %s" % (name, np.shape(seg))
            assert np.isfinite(seg).all(), "%s produced non-finite" % name
            p = pos[0] if isinstance(pos, tuple) else pos
            assert 0 <= p < len(bar), "%s left the buffer: %s" % (name, p)
    return "%d performance effects stayed in bounds over 400 calls each" % len(dj.PERFORM)


# --------------------------------------------------------- 6. golden renders

def c_golden(bless=False):
    import glob
    from oontz import core, song as sm
    hashes = {}
    for p in sorted(glob.glob("songs/*.oontz"))[:8]:
        core.do("open " + os.path.splitext(os.path.basename(p))[0])
        h = hashlib.sha1(core.render_bar().tobytes()).hexdigest()[:16]
        hashes[os.path.basename(p)] = h
    for p in sorted(glob.glob("songs/*.song"))[:4]:
        sg = sm.Song.load(p)
        h = hashlib.sha1(sm.render(sg, core.render_state).tobytes()).hexdigest()[:16]
        hashes[os.path.basename(p)] = h
    os.makedirs("tests", exist_ok=True)
    if bless or not os.path.exists(GOLDEN):
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=1, sort_keys=True)
        return "blessed %d golden renders" % len(hashes)
    with open(GOLDEN, encoding="utf-8") as f:
        old = json.load(f)
    drift = [k for k in hashes if k in old and old[k] != hashes[k]]
    assert not drift, ("sound changed for: %s  (run --bless if intended)"
                       % ", ".join(drift))
    return "%d golden renders unchanged (%d new)" % (
        len(hashes) - len([k for k in hashes if k not in old]),
        len([k for k in hashes if k not in old]))


# ----------------------------------------------------- 3. the two composers

def c_composers_agree():
    """oontz/compose.py and web/app/compose.js implement one algorithm. Prove it."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        raise SkipCheck("node not on PATH")
    from oontz import compose, theory
    cases, want = [], []
    for style, g in theory.GENRES.items():
        for curve in theory.TEMPLATES:
            for minutes in (2.0, 3.5, 5.0, 8.0):
                cases.append([curve, minutes, g["sweet"], g["drop_at"][0], g["drop_at"][1]])
                want.append([list(x) for x in compose.arrange(minutes, curve, g["sweet"], None, g["drop_at"])])
    r = subprocess.run([node, os.path.join("web", "app", "plan.js")], input=json.dumps(cases),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-300:]
    got = json.loads(r.stdout)
    bad = [(c, w, g) for c, w, g in zip(cases, want, got) if w != g]
    assert not bad, "%d of %d plans differ, first: %s\n  py %s\n  js %s" % (
        len(bad), len(cases), bad[0][0], bad[0][1], bad[0][2])
    return "%d arrangements identical in python and js" % len(cases)


# ------------------------------------------------------------------ report

def report():
    w = max(len(n) for n, _s, _d, _t in RESULTS) + 2
    print()
    print("  %-*s %-5s %8s  %s" % (w, "check", "", "time", "detail"))
    print("  " + "-" * (w + 60))
    for name, status, detail, dt in RESULTS:
        mark = {"pass": "ok", "skip": "--", "FAIL": "FAIL"}[status]
        print("  %-*s %-5s %7.2fs  %s" % (w, name, mark, dt, detail[:110]))
    p = sum(1 for _n, s, _d, _t in RESULTS if s == "pass")
    f = sum(1 for _n, s, _d, _t in RESULTS if s == "FAIL")
    sk = sum(1 for _n, s, _d, _t in RESULTS if s == "skip")
    total = sum(t for _n, _s, _d, t in RESULTS)
    print()
    print("  %d passed, %d failed, %d skipped in %.1fs" % (p, f, sk, total))
    return f == 0


def main(argv=()):
    os.environ.setdefault("OONTZ_OFFLINE", "1")   # 600 fuzzed `ask`s once spent 10 minutes in the claude CLI
    quick = "--quick" in argv
    bless = "--bless" in argv
    check("registries", c_registries)
    check("voices", c_voices)
    check("effects", c_fx)
    check("views", c_views)
    check("keymap", c_keymap)
    check("layout sweep", c_layout)
    check("command fuzzer", lambda: c_fuzz(600 if quick else 2500))
    check("song invariants", c_song)
    check("scrub == render", c_scrub)
    check("performance fx", c_perf_fx)
    check("audio soak", lambda: c_soak(0.5 if quick else 2.0))
    check("golden renders", lambda: c_golden(bless))
    check("composers agree", c_composers_agree)
    ok = report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
