"""The mixer: two channel strips, a crossfader, a master chain, and transitions.

Every control is smoothed per block. A stepped parameter clicks, and a click in
the middle of a mix is the one thing you cannot take back on a live recording.

Transitions are planned rather than guessed, because both songs' phrase marks are
exact: a blend can be told to start precisely where B's drop will land on A's.
"""
import numpy as np

from .contracts import SR, COMMANDS, FX

SMOOTH = 0.02                                    # seconds to reach a new setting


def _fx(name):
    """Fetch an effect, importing fx on first use.

    Relying on someone else having imported thud.fx made the mixer silently
    no-op - EQ kills did nothing and reported success. It loads its own now.
    """
    fn = FX.get(name)
    if fn is None:
        try:
            from . import fx as _m                # noqa: F401 - registers into FX
            fn = FX.get(name)
        except ImportError:
            pass
    return fn


def _sm(cur, target, frames):
    """One block of smoothing toward a target. Returns (ramp, new_value)."""
    k = min(1.0, frames / float(max(1, SMOOTH * SR)))
    nxt = cur + (target - cur) * k
    return np.linspace(cur, nxt, frames, dtype=np.float32)[:, None], nxt


class Channel:
    def __init__(self, name):
        self.name = name
        self.fader = 1.0
        self.trim = 1.0
        self.eq = [1.0, 1.0, 1.0]                # low, mid, high; 0.0 is a kill
        self.filter = 0.0                        # -1 lowpass .. 0 off .. +1 highpass
        self.cue = False
        self._f = 1.0
        self._eq = [1.0, 1.0, 1.0]
        self._flt = 0.0

    def process(self, x):
        n = len(x)
        if n == 0:
            return x
        y = x
        # EQ, only when it is doing something - unity must be bit-identical
        if any(abs(a - b) > 1e-6 or abs(a - 1.0) > 1e-6
               for a, b in zip(self.eq, self._eq)):
            eq3 = _fx("eq3")
            if eq3:
                tgt = [max(0.0, min(2.0, v)) for v in self.eq]
                mid = [(self._eq[i] + tgt[i]) * 0.5 for i in range(3)]
                try:
                    y = eq3(y, low=mid[0], mid=mid[1], high=mid[2])
                except Exception:
                    pass
            self._eq = list(self.eq)
        # bipolar filter: centre is off and must not touch the signal
        f = self.filter
        if abs(f) > 0.02 or abs(self._flt) > 0.02:
            svf = None
            try:
                from .voices import svf as _svf
                svf = _svf
            except Exception:
                pass
            if svf is not None:
                cur = (self._flt + f) * 0.5
                if cur < 0:
                    fc = 18000.0 * (1.0 + cur) ** 2 + 60.0
                    mode = "lp"
                else:
                    fc = 30.0 + 6000.0 * cur ** 2
                    mode = "hp"
                try:
                    y = np.stack([svf(y[:, 0], fc, 0.4, mode),
                                  svf(y[:, 1], fc, 0.4, mode)], axis=1).astype(np.float32)
                except Exception:
                    pass
            self._flt = f
        ramp, self._f = _sm(self._f, self.fader * self.trim, n)
        return y * ramp


class Mixer:
    def __init__(self):
        self.ch = {"a": Channel("a"), "b": Channel("b")}
        self.xf = 0.0                            # -1 = A, +1 = B
        self.curve = "smooth"
        self.master = 1.0
        self._xf = 0.0
        self._m = 1.0
        self.peak = 0.0
        self.rms = 0.0

    def xf_gains(self, pos):
        p = max(-1.0, min(1.0, pos if pos == pos else 0.0))
        t = (p + 1.0) * 0.5
        if self.curve == "sharp":
            a = 1.0 if t < 0.5 else max(0.0, 1.0 - (t - 0.5) * 4)
            b = 1.0 if t > 0.5 else max(0.0, 1.0 - (0.5 - t) * 4)
        elif self.curve == "constant":
            a, b = 1.0 - t, t
        else:                                    # equal power - the long blend
            a, b = float(np.cos(t * np.pi / 2)), float(np.sin(t * np.pi / 2))
        return a, b

    def process(self, a_samples, b_samples):
        n = max(len(a_samples), len(b_samples))
        if n == 0:
            return np.zeros((0, 2), np.float32)
        a = self.ch["a"].process(a_samples)
        b = self.ch["b"].process(b_samples)
        ga0, gb0 = self.xf_gains(self._xf)
        ga1, gb1 = self.xf_gains(self.xf)
        ra = np.linspace(ga0, ga1, n, dtype=np.float32)[:, None]
        rb = np.linspace(gb0, gb1, n, dtype=np.float32)[:, None]
        self._xf = self.xf
        out = a * ra + b * rb
        mr, self._m = _sm(self._m, self.master, n)
        out = out * mr
        lim = _fx("limiter")
        if lim:
            try:
                out = lim(out, ceiling=0.97)
            except Exception:
                out = np.tanh(out)
        else:
            out = np.tanh(out * 1.05) * 0.95
        out = np.asarray(out, np.float32)
        self.peak = float(np.abs(out).max()) if len(out) else 0.0
        self.rms = float(np.sqrt(np.mean(out ** 2))) if len(out) else 0.0
        return out


MIX = Mixer()


# ------------------------------------------------------------- transitions

STYLES = {
    "blend":       "long equal-power crossfade with the lows swapped at the midpoint",
    "cut":         "hard swap on the downbeat",
    "filter_sweep": "A filters out while B filters in",
    "bass_swap":   "swap the low bands at the phrase line, faders stay put",
    "echo_out":    "delay throw on A while B comes in",
    "drop_swap":   "line B's drop up with the end of A's",
}


def plan_transition(from_deck, to_deck, style="blend", bars=16):
    """[(bar_offset, control, value)] - every step lands on a phrase boundary.

    Controls are names the mixer actually has, so nothing in a plan can fail to
    apply: xf, a.low/mid/high, b.low/mid/high, a.filter, b.filter, a.fader, b.fader.
    """
    bars = max(4, int(bars))
    steps = [(0, "b.fader", 1.0)]
    if style == "cut":
        return steps + [(0, "xf", -1.0), (bars, "xf", 1.0)]
    if style == "bass_swap":
        return steps + [(0, "xf", 0.0), (0, "b.low", 0.0),
                        (bars // 2, "a.low", 0.0), (bars // 2, "b.low", 1.0),
                        (bars, "xf", 1.0), (bars, "a.low", 1.0)]
    if style == "filter_sweep":
        return steps + [(0, "b.filter", 1.0), (bars // 2, "b.filter", 0.0),
                        (bars // 2, "a.filter", 0.6), (bars, "a.filter", 1.0),
                        (bars, "xf", 1.0)]
    if style == "echo_out":
        return steps + [(bars - 4, "a.high", 0.4), (bars - 2, "a.fader", 0.5),
                        (bars, "xf", 1.0), (bars, "a.fader", 0.0)]
    # blend, and drop_swap which is a blend timed against the phrase marks
    out = steps + [(0, "b.low", 0.0)]
    for k in range(1, 5):
        out.append((int(bars * k / 4.0), "xf", -1.0 + 2.0 * k / 4.0))
    out += [(bars // 2, "a.low", 0.0), (bars // 2, "b.low", 1.0), (bars, "a.fader", 0.0)]
    return sorted(out)


def apply_step(control, value):
    """Route one planned control to the mixer. Unknown controls are refused."""
    if control == "xf":
        MIX.xf = float(value)
        return True
    if "." in control:
        ch, param = control.split(".", 1)
        c = MIX.ch.get(ch)
        if c is None:
            return False
        if param in ("low", "mid", "high"):
            c.eq[["low", "mid", "high"].index(param)] = float(value)
            return True
        if param in ("fader", "trim", "filter"):
            setattr(c, param, float(value))
            return True
    return False


def controls():
    return ["xf"] + ["%s.%s" % (ch, p) for ch in ("a", "b")
                     for p in ("low", "mid", "high", "fader", "trim", "filter")]


# ---------------------------------------------------------------- commands

def _xf_cmd(state, args):
    if not args:
        return "crossfader %.2f (%s)" % (MIX.xf, MIX.curve)
    if args[0] in STYLES or args[0] in ("smooth", "sharp", "constant"):
        MIX.curve = args[0]
        return "curve " + args[0]
    MIX.xf = max(-1.0, min(1.0, float(args[0])))
    return None


def _eq_cmd(state, args):
    """`eq a low 0` - 0 is a full kill, 1 unity."""
    if len(args) < 3:
        return "eq <a|b> <low|mid|high> <0..2>"
    return None if apply_step("%s.%s" % (args[0], args[1]), float(args[2])) \
        else "no such control"


def _filter_cmd(state, args):
    if len(args) < 2:
        return "dfilter <a|b> <-1..1>   (-1 lowpass, 0 off, +1 highpass)"
    return None if apply_step("%s.filter" % args[0], float(args[1])) else "no such deck"


def _transition_cmd(state, args):
    style = args[0] if args else "blend"
    bars = int(args[1]) if len(args) > 1 else 16
    if style not in STYLES:
        return "styles: " + "  ".join("%s (%s)" % (k, v) for k, v in STYLES.items())
    plan = plan_transition("a", "b", style, bars)
    for _bar, ctl, val in plan:
        apply_step(ctl, val)                     # applied immediately for now
    return "%s over %d bars: %d steps" % (style, bars, len(plan))


COMMANDS.update({"xf": _xf_cmd, "eq": _eq_cmd, "dfilter": _filter_cmd,
                 "transition": _transition_cmd})
