"""Live performance FX - pointer math over the pre-rendered bar, not synthesis.

CENTRAL IDEA (see core.py's docstring and _callback): thud renders ONE BAR into a
(n,2) array and the audio callback only ever slices it. So a "live" effect here
never re-renders - it is POINTER MATH over that existing buffer: where to read
from, how fast, which direction. A loop roll re-reads the last window. A spinback
advances the read pointer at a decaying rate. Reverse walks backwards. That's why
they're instant (no render latency) and why they sound like the real hardware - a
spinback IS just the turntable's read head slowing down, nothing more.

CONTRACT: every effect is f(bar, pos, frames, **params) -> (samples, new_pos).
  bar     the (n,2) rendered bar. Read-only - never mutated.
  pos     whatever this same effect returned last call. On the very first call it
          is a bare number (ST.pos, ordinary playback position) - every effect
          below bootstraps cleanly from that (see _bootstrap).
  frames  the block size core asks for.
Returns exactly `frames` stereo samples and a `pos` to hand back next call.
Pure, no blocking, no I/O, no global state - and no per-call allocation bigger than
O(frames). See STATE NOTE at the bottom for the one place this gets interesting.

Two registries, same functions:
  FX       (contracts.py, frozen) - typed there as f(x, **params) -> ndarray, the
           shape fx.py's buffer effects use. Ours are a different shape entirely,
           f(bar, pos, frames, **params) -> (seg, pos), but the brief wants these
           discoverable alongside every other agent's FX entries too, so they're
           added there as well. Don't call them expecting the fx.py contract.
  PERFORM  (this module) - the dict core._callback actually drives, through
           core.PERF["fn"] / core.perform(fn, **params). This is the real one.
"""
import numpy as np
from .contracts import SR, FX

SMOOTH_MS = 5                                    # click-guard width, every entry/exit


def _fade_n(ms=SMOOTH_MS):
    return max(1, int(SR * ms / 1000))


def _lerp_read(bar, p):
    """Linear-interpolated read at fractional sample position(s) p, any shape."""
    n = len(bar)
    p = np.mod(p, n)
    i0 = np.floor(p).astype(np.int64)
    i1 = (i0 + 1) % n
    frac = (p - i0)[:, None]
    return bar[i0] * (1 - frac) + bar[i1] * frac


def smooth_edge(dry, wet, ms=SMOOTH_MS):
    """Equal-power crossfade `dry` into `wet` over `ms` - same-length (k,2) arrays.

    This is the SMOOTH_MS helper: it exists to be called at the two moments a
    click can actually happen - the block where an effect ENGAGES (dry tail
    crossfaded into wet head) and the block where it RELEASES (wet tail into dry
    head). Effects do NOT call this on themselves every block - that would put an
    11ms tremolo on every callback for as long as the effect runs. It's used once
    per transition, by whoever owns the transition (core, or demo() below).
    """
    k = len(dry)
    t = np.linspace(0, np.pi / 2, k, endpoint=False)[:, None]
    return dry * np.cos(t) + wet * np.sin(t)


def _soft_gate(mask, F):
    """Smear a 0/1 gate array's edges over F samples. Box filter - cheap, plenty."""
    if F <= 1 or len(mask) < F:            # np.convolve('same') pads UP to kernel
        return mask                        # length otherwise - wrong for short blocks
    return np.convolve(mask, np.ones(F) / F, mode="same")


def _seam_blend(bar, start, L, F):
    """F-sample crossfade of a loop window's tail into its own head, so looping
    [start, start+L) forever has no seam regardless of what the audio is doing
    there. Cost is O(F), not O(L) - it's recomputed each call but F is tiny
    (~220 samples) and constant, independent of how long the roll window is.
    """
    n = len(bar)
    head = bar[(start + np.arange(F)) % n]
    tail = bar[(start + L - F + np.arange(F)) % n]
    t = np.linspace(0, np.pi / 2, F, endpoint=False)[:, None]
    return tail * np.cos(t) + head * np.sin(t)


def _bootstrap(pos):
    """Rate effects need a bit more state than a read pointer - elapsed time since
    engage, so the decay curve is continuous across calls. They carry it as
    (ptr, elapsed) and thread it through `pos`. The first call after an effect
    engages still hands in a bare number (ordinary ST.pos) - this turns that into
    (ptr, 0.0) once, and passes an existing tuple through unchanged after that.
    """
    return pos if isinstance(pos, tuple) else (float(pos), 0.0)


# ---------------------------------------------------------------- pointer-math FX

def roll(bar, pos, frames, length_beats=0.25, bpm=132.0):
    """Beat-repeat: lock onto the L-sample grid cell `pos` falls in, loop it.

    Stateless by construction - "which window" is recomputed from pos alone every
    call (floor to the L-sample grid), so call 1 and call 500 of the same roll
    agree without anything but pos carrying over.
    """
    n = len(bar)
    F = _fade_n()
    L = int(np.clip(round(length_beats * 60.0 / bpm * SR), 2 * F, n))
    p = int(round(pos)) % n
    start = (p // L) * L
    off = p - start
    idx_w = (off + np.arange(frames)) % L            # offset within the window
    idx = (start + idx_w) % n
    out = bar[idx].copy()                             # copy: seam rows get overwritten below
    seam = idx_w < F
    if seam.any():
        out[seam] = _seam_blend(bar, start, L, F)[idx_w[seam]]
    new_pos = start + (off + frames) % L
    return out.astype(bar.dtype, copy=False), float(new_pos)


def stutter(bar, pos, frames, div=0.125, bpm=132.0, duty=0.6):
    """Beat-repeat's chopped cousin. Same locked window as roll, but gated: it
    plays the first `duty` of the window and cuts to silence for the rest, so it
    chops rather than loops. The silence conveniently covers the window seam.
    """
    n = len(bar)
    F = _fade_n()
    L = int(np.clip(round(div * 60.0 / bpm * SR), 2 * F, n))
    p = int(round(pos)) % n
    start = (p // L) * L
    off = p - start
    idx_w = (off + np.arange(frames)) % L
    idx = (start + idx_w) % n
    on_len = max(2 * F, int(L * duty))
    gate = _soft_gate((idx_w < on_len).astype(float), F)
    new_pos = start + (off + frames) % L
    return (bar[idx] * gate[:, None]).astype(bar.dtype, copy=False), float(new_pos)


def reverse(bar, pos, frames):
    """Play backwards from pos. Same rate as forward, opposite direction."""
    n = len(bar)
    p = int(round(pos)) % n
    idx = (p - np.arange(frames)) % n
    return bar[idx].copy(), float((p - frames) % n)


def _resample_walk(bar, ptr, elapsed, frames, rate_fn):
    """Shared engine for the decaying-rate effects. rate_fn(t_seconds) gives the
    playback rate for each sample of this call (1 = normal forward, -1 = normal
    backward, 0 = stopped); integrating it gives the fractional read position,
    which needs linear interpolation since it's off the sample grid.
    """
    n = len(bar)
    t = (elapsed + np.arange(frames)) / SR
    rate = rate_fn(t)
    p = ptr + np.concatenate(([0.0], np.cumsum(rate)[:-1]))   # pos *before* each step
    seg = _lerp_read(bar, p)
    new_ptr = float(np.mod(p[-1] + rate[-1], n)) if frames else float(ptr)
    return seg, new_ptr, elapsed + frames


def spinback(bar, pos, frames, speed=1.5, decay=0.35):
    """Turntable spin-down: pointer runs backwards, rate decaying to 0."""
    ptr, elapsed = _bootstrap(pos)
    seg, new_ptr, new_el = _resample_walk(bar, ptr, elapsed, frames,
                                           lambda t: -speed * np.exp(-t / decay))
    return seg.astype(bar.dtype, copy=False), (new_ptr, new_el)


def tapestop(bar, pos, frames, decay=0.6):
    """Forwards, rate decaying 1 -> 0. Pitch falls to nothing."""
    ptr, elapsed = _bootstrap(pos)
    seg, new_ptr, new_el = _resample_walk(bar, ptr, elapsed, frames,
                                           lambda t: np.exp(-t / decay))
    return seg.astype(bar.dtype, copy=False), (new_ptr, new_el)


def brake(bar, pos, frames, amount=0.5):
    """A momentary dip in speed that recovers - tension before a drop. Forward
    only: rate starts at (1-amount) the instant it engages and climbs back to 1.
    """
    ptr, elapsed = _bootstrap(pos)
    tau = 0.1 + 0.4 * amount
    seg, new_ptr, new_el = _resample_walk(bar, ptr, elapsed, frames,
                                           lambda t: 1.0 - amount * np.exp(-t / tau))
    return seg.astype(bar.dtype, copy=False), (new_ptr, new_el)


def scratch(bar, pos, frames, lfo_hz=2.0, depth=0.25, bpm=132.0):
    """Baby scratch: pointer oscillates around a fixed centre (set once, at
    engage). `depth` is a beat fraction - same units as roll's length_beats.
    """
    center, elapsed = _bootstrap(pos)
    t = (elapsed + np.arange(frames)) / SR
    amp = depth * 60.0 / bpm * SR
    p = center + amp * np.sin(2 * np.pi * lfo_hz * t)
    seg = _lerp_read(bar, p)
    return seg.astype(bar.dtype, copy=False), (center, elapsed + frames)


def gate_pattern(bar, pos, frames, pattern="x.x.x.x.x.x.x.x.", bpm=132.0):
    """Trance-gate: chop with a 16-step on/off string. Reads forward normally -
    only amplitude is gated - so this is the one effect here that needs no
    resampling at all.
    """
    n = len(bar)
    F = _fade_n()
    p = int(round(pos)) % n
    idx = (p + np.arange(frames)) % n
    step = max(1, round(60.0 / bpm / 4 * SR))          # one 16th note
    steps = (idx // step) % len(pattern)
    on = np.array([pattern[s] not in ".-" for s in steps], dtype=float)
    gate = _soft_gate(on, F)
    return (bar[idx] * gate[:, None]).astype(bar.dtype, copy=False), float((p + frames) % n)


def crossfade(bar, pos, frames, bar_b=None, x=0.5):
    """Equal-power blend of `bar` (=bar_a) and `bar_b` at the same read position.

    Signature is (bar, pos, frames, bar_b, x) rather than the brief's literal
    (bar_a, bar_b, pos, frames, x) so it drops straight into the uniform
    (bar, pos, frames, **params) calling convention every other effect here uses -
    bar_b just rides along in **params.
    """
    n = len(bar)
    p = int(round(pos)) % n
    idx = (p + np.arange(frames)) % n
    a, b = bar[idx], bar_b[idx % len(bar_b)]
    ga, gb = np.cos(x * np.pi / 2), np.sin(x * np.pi / 2)
    return (a * ga + b * gb).astype(bar.dtype, copy=False), float((p + frames) % n)


# --------------------------------------------------------------------- registries

PERFORM = {"roll": roll, "stutter": stutter, "reverse": reverse, "spinback": spinback,
           "tapestop": tapestop, "brake": brake, "scratch": scratch,
           "gate_pattern": gate_pattern, "crossfade": crossfade}


def apply(name, bar, pos, frames, **params):
    """Call an effect by name - core drives PERFORM directly via core.PERF["fn"];
    this is for anything that wants to look one up (tests, a command console)."""
    return PERFORM[name](bar, pos, frames, **params)


FX.update(PERFORM)          # discoverability alongside every other agent's FX entries

# STATE NOTE - the hook this needs in core, precisely, described but not added here:
#
# core._callback (core.py ~L282-292) already does exactly the right thing for the
# five position-is-a-number effects (roll, stutter, reverse, gate_pattern,
# crossfade):
#     seg, ST.pos = PERF["fn"](b, i, frames, **PERF["params"])
# ST.pos round-trips as a plain float/int, and nothing else in core.py minds.
#
# spinback, tapestop, brake and scratch need one more number of state (elapsed
# time since engage) to make their decay curve continuous across calls, and the
# only place to carry it, given this hook, is inside the returned `pos` itself -
# so those four return a (ptr, elapsed) tuple instead of a bare number. They
# bootstrap cleanly FROM a bare number on the first call (see _bootstrap), so
# engaging one needs no change on core's side. The gap is on the read side:
# core.snapshot() does `int(ST.pos / n * 16) if playing() else -1` - that line
# will raise once ST.pos is a tuple, i.e. the instant a rate effect is engaged.
# Two ways to close it, either is a one-line change and neither is mine to make:
#   (a) guard that line - `... if playing() and not isinstance(ST.pos, tuple) else -1`
#   (b) give PERF a state slot separate from ST.pos, e.g.
#       seg, ST.pos, PERF["state"] = PERF["fn"](b, i, frames, state=PERF["state"], **PERF["params"])
#       and have the four rate effects take/return `state` instead of overloading pos.
# (a) is the smaller diff; (b) is cleaner if a second stateful effect ever needs it.

# ------------------------------------------------------------------------- demo


def demo():
    n = round(SR * 240.0 / 132.0)                        # one bar at 132bpm, like State.n
    F = _fade_n()

    # Amplitude 0.6, not 0.95: several checks below equal-power-sum two readings
    # of the same signal (roll/stutter's own seam blend, smooth_edge at every
    # entry/exit). Equal-power trades headroom for constant energy - at x=0.5,
    # two same-signed full-scale samples sum past 1.0 by design (cos+sin peaks at
    # sqrt2/2 each, sqrt2 together). 0.6 leaves exactly that headroom so the
    # peak<=1.0 check is honest instead of just avoiding the scenario.
    AMP = 0.6
    ramp = np.linspace(0, AMP, n, dtype=np.float32)
    bar_ramp = np.stack([ramp, -ramp], axis=1)            # channels differ -> catches ch-swap bugs
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * 400.0 * t) * AMP).astype(np.float32)
    bar_tone = np.stack([tone, tone], axis=1)

    peaks = []

    def check_frame(seg, pos, frames):
        assert seg.shape == (frames, 2), seg.shape
        assert np.isfinite(seg).all(), "NaN/inf in output"
        peaks.append(float(np.abs(seg).max()))

    # -- every effect: exact frame count, every call, several block sizes -------
    kwset = {"roll": dict(length_beats=0.25, bpm=132.0),
              "stutter": dict(div=0.125, bpm=132.0),
              "reverse": dict(),
              "spinback": dict(speed=1.5, decay=0.35),
              "tapestop": dict(decay=0.5),
              "brake": dict(amount=0.5),
              "scratch": dict(lfo_hz=3.0, depth=0.08, bpm=132.0),
              "gate_pattern": dict(pattern="x.x.x.x.x.x.x.x.", bpm=132.0),
              "crossfade": dict(bar_b=bar_tone, x=0.5)}
    bars = {name: (bar_tone if name in ("spinback", "tapestop") else bar_ramp)
            for name in kwset}
    for name, kw in kwset.items():
        b = bars[name]
        pos = n // 3
        for frames in (1, 64, 512, 4000):
            seg, pos = apply(name, b, pos, frames, **kw)
            check_frame(seg, pos, frames)

    # -- 10000-call crash-in-production walk: pos never leaves [0, n) ----------
    # One shared walk cycling randomly through every effect - the point is
    # thousands of successive, unpredictable frame counts feeding pos back into
    # itself, exactly what a live take does to whichever effect is engaged.
    rng = np.random.default_rng(1312)
    live_pos = {name: n // 5 for name in kwset}
    names = list(kwset)
    for _ in range(10000):
        name = names[rng.integers(len(names))]
        frames = int(rng.integers(1, 3000))
        seg, pos = apply(name, bars[name], live_pos[name], frames, **kwset[name])
        assert seg.shape == (frames, 2)
        p = pos[0] if isinstance(pos, tuple) else pos
        assert 0 <= p < n, (name, p, "position escaped [0, n)")
        live_pos[name] = pos

    # -- roll actually repeats -------------------------------------------------
    L = int(round(0.25 * 60.0 / 132.0 * SR))
    start = 8 * L                                          # land exactly on a grid line
    w1, p1 = roll(bar_ramp, start, L, length_beats=0.25, bpm=132.0)
    w2, p2 = roll(bar_ramp, p1, L, length_beats=0.25, bpm=132.0)
    assert p1 == start and p2 == start, (p1, p2)
    assert np.array_equal(w1, w2), "roll window did not repeat identically"

    # -- reverse is the time-reverse of the forward read -----------------------
    p, fr = 20000, 3000
    fwd = bar_ramp[p - fr + 1:p + 1]
    rev, _ = reverse(bar_ramp, p, fr)
    assert np.array_equal(rev, fwd[::-1]), "reverse is not the forward read, reversed"

    # -- spinback / tapestop: rate -> 0, pitch (zero-crossing rate) falls ------
    def zcr(x):
        return float((np.diff(np.sign(x)) != 0).sum()) / len(x)

    for fn, kw, sign in ((spinback, dict(speed=2.0, decay=0.05), -1),
                         (tapestop, dict(decay=0.05), 1)):
        pos, rates = n // 2, []
        block = 2000
        for _ in range(6):
            seg, pos = fn(bar_tone, pos, block, **kw)
            rates.append(zcr(seg.mean(axis=1)))
        assert rates[0] > rates[-1] * 3, ("%s did not slow down" % fn.__name__, rates)
        assert rates[-1] < 0.02, ("%s never reached near-zero rate" % fn.__name__, rates)
        elapsed = pos[1]
        final_rate = sign * kw.get("speed", 1.0) * np.exp(-elapsed / kw["decay"])
        assert abs(final_rate) < 1e-3, "rate did not decay to ~0"

    # -- crossfade: x=0 is bar_a, x=1 is bar_b, x=0.5 matches the formula -------
    p0, fr0 = 5000, 1000
    a0, _ = crossfade(bar_ramp, p0, fr0, bar_b=bar_tone, x=0.0)
    assert np.array_equal(a0, bar_ramp[p0:p0 + fr0]), "x=0 is not bar_a"
    b1, _ = crossfade(bar_ramp, p0, fr0, bar_b=bar_tone, x=1.0)
    assert np.allclose(b1, bar_tone[p0:p0 + fr0], atol=1e-6), "x=1 is not bar_b"
    half, _ = crossfade(bar_ramp, p0, fr0, bar_b=bar_tone, x=0.5)
    want = bar_ramp[p0:p0 + fr0] * np.cos(np.pi / 4) + bar_tone[p0:p0 + fr0] * np.sin(np.pi / 4)
    assert np.allclose(half, want), "x=0.5 does not match the equal-power formula"

    # -- no clicks: entry and exit boundary of every effect ---------------------
    def worst_delta(seq):
        return float(np.abs(np.diff(seq, axis=0)).max())

    click_max = 0.0
    for name, kw in kwset.items():
        b = bars[name]
        engage = n // 4
        dry_would_have = b[engage:engage + F]                          # what kept playing without the fx
        wet_head, mid_pos = apply(name, b, engage, F, **kw)
        blended_in = smooth_edge(dry_would_have, wet_head)
        seq_in = np.concatenate([b[engage - 1:engage], blended_in])
        click_max = max(click_max, worst_delta(seq_in))

        pos, prev_last = mid_pos, wet_head[-1]
        for _ in range(4):                                             # run it a while, then release
            seg, pos = apply(name, b, pos, F, **kw)
            prev_last = seg[-1]                    # true last sample before the release block
        # wet_next is the block the effect is producing AT the moment of release; dry
        # resumes from wherever that block's own pointer ends up, not where it began -
        # for the rate effects the pointer is still moving fast right up to release.
        wet_next, pos_after = apply(name, b, pos, F, **kw)
        p_end = pos_after[0] if isinstance(pos_after, tuple) else pos_after
        resume = int(round(p_end)) % len(b)
        dry_resume = b[resume:resume + F] if resume + F <= len(b) else b[:F]
        blended_out = smooth_edge(wet_next, dry_resume)   # wet dominant at start, dry by the end
        seq_out = np.concatenate([prev_last[None], blended_out])
        click_max = max(click_max, worst_delta(seq_out))

    assert click_max < 0.05, "click at an effect boundary: max delta %.4f" % click_max

    # -- global sanity: peak, finiteness, already asserted per-call above -------
    assert max(peaks) <= 1.0, "an effect exceeded 0dBFS: peak %.4f" % max(peaks)

    return ("dj: all checks pass  ·  %d effects  ·  10000-call walk clean  ·  "
            "max boundary delta %.4f  ·  peak %.3f" % (len(kwset), click_max, max(peaks)))


if __name__ == "__main__":
    print(demo())
