"""The JS-facing surface for the browser build (Pyodide).

No thread and no stream: the worker calls render_bar() whenever its ring buffer
has room, and that one call does what the scheduler thread and the bar boundary
of the audio callback do natively - render ahead, count the bar, take the next.
The page is the same ui.build() the terminal draws; JS turns the SGR codes into
spans. `python scripts/pack_thud.py` zips this package for the browser to fetch.
"""
import io
import os
import zipfile
import dataclasses

from . import core, ui
from .core import ST
from .contracts import VERSION

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ZIP = "web/app/py/thud.zip"


def boot():
    core.refresh()
    return "thud %s  %d modules" % (VERSION, len(core.MODULES))


def do(cmd):
    return core.do(cmd) or ""


def render_bar():
    """float32 interleaved stereo of the current bar, then advance to the next one."""
    out = ST.bar.tobytes()
    core._tap(ST.bar[:core.SCOPE_N], min(len(ST.bar), core.SCOPE_N))   # scope + meters
    core.render_next()
    core.bar_done()
    return out


def _snap(step=-1):
    s = core.snapshot(mode="cmd" if ui._cmd["on"] else "play", cmdline=ui._cmd["buf"],
                      complete=core.complete(ui._cmd["buf"]), overlay=ui._overlay[0])
    return dataclasses.replace(s, playing=step >= 0, step=int(step))


def page(cols, rows, step=-1):
    """The terminal page as ANSI text. `step` is the JS playhead's 16th, -1 when stopped."""
    s = _snap(step)
    s = dataclasses.replace(s, hint=ui.hint(s))
    return "\n".join(ui.build(s, int(cols), int(rows)))


def key(ch):
    """One keypress. Space is the transport, which JS owns; everything else is ui's."""
    if ch == " " and not ui._cmd["on"]:
        return "toggle"
    ui.on_key(ch, _snap())
    return ST.echo

# ------------------------------------------------------------- the package zip


def _members():
    for d, exts in (("thud", (".py",)), ("songs", (".thud", ".song"))):
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            if f.endswith(exts):
                yield d + "/" + f


def _read(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        return f.read().replace(b"\r\n", b"\n")          # same bytes on every checkout


def pack():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in _members():
            z.writestr(zipfile.ZipInfo(rel, (1980, 1, 1, 0, 0, 0)), _read(rel), zipfile.ZIP_DEFLATED)
    with open(os.path.join(ROOT, ZIP), "wb") as f:
        f.write(buf.getvalue())
    return "wrote %s  %d files  %dKB" % (ZIP, len(list(_members())), len(buf.getvalue()) // 1024)


def stale():
    """Which zip members no longer match the source. Empty means fresh."""
    try:
        with zipfile.ZipFile(os.path.join(ROOT, ZIP)) as z:
            got = {i.filename: z.read(i) for i in z.infolist()}
    except (OSError, zipfile.BadZipFile):
        return [ZIP]
    want = {rel: _read(rel) for rel in _members()}
    return sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
