# thud

A terminal techno instrument. You play it with the keyboard, watch it on one
static page, and record the take. Everything is synthesized — no samples.

```
python -m thud            # the instrument
python -m thud test       # the checks
```

```
:open warehouse           # load a starter song   (:songs lists all 15)
space                     # play
1-8                       # focus a track
qwertyui asdfghjk         # the 16 step buttons
[ ]                       # sweep the filter      (hold to sweep)
/                         # loop roll             (hold)
\                         # spinback
Tab                       # cycle spectrum / scope / meters / freq / stereo
R                         # record a take
?                         # every key
```

## The idea

Text patterns are the interface. `kick x...x...x...x...` is greppable, diffable
and committable, and a whole session saves as a `.thud` file that is just the
commands you ran — so a song is something you can read, diff and commit.

Patterns can be any length, so a 5-step hat against a 16-step kick gives you
polymeter for free. `x` is a hit, `X` an accent, `.` a rest. Pitched tracks take
notes instead: `bass a1 . a1~ c2!` where `~` slides and `!` accents.

## How it works

Two mechanisms, kept strictly apart, and between them they cover everything:

**Render-ahead.** A worker thread keeps bar N+1 rendered while bar N plays, so
the audio callback only ever slices an array — no locks, no queue, no allocation.
Automation, arrangement, scene changes and generative variation all happen there.
A render that overruns reuses the current bar and counts a visible drop rather
than glitching. Measured: ~0.2s to render a 1.8s bar.

**Pointer math.** Live effects don't re-render anything — they read that same
buffer differently. A loop roll re-reads the last 1/16th, a spinback advances the
read pointer at a decaying rate, reverse walks backwards. Instant, and authentic
because that is physically what a turntable does.

## Layout

    thud/contracts.py   frozen seams: Snapshot, the registries, the audio conventions
    thud/core.py        state, sequencer, scheduler, engine, recording, undo, commands
    thud/ui.py          the static page: keys, views, diff renderer
    thud/term.py        shared terminal primitives every view uses
    thud/voices.py      the original voice bank
    thud/drums.py       hard techno drums: kick_hard, kick_dist, rumble, ride, toms
    thud/synths.py      sub, reese, hoover, pluck, lead, screech, pad, atmos, fm
    thud/fx.py          drive, fold, bitcrush, delay, reverb, chorus, phaser, eq3
    thud/dj.py          roll, stutter, spinback, tapestop, reverse, brake, scratch
    thud/arrange.py     scenes, automation ramps, build/drop/break, song timeline, sets
    thud/gen.py         euclidean rhythms, scale-aware melody, 10 style packs
    thud/viz_*.py       spectrum, braille scope, meters, frequency occupancy, goniometer
    thud/teach.py       context hints, the key legend, why(), the guided lesson
    thud/ai.py          asks the local `claude` CLI for command suggestions
    songs/              the songbook, one commented .thud per style

`contracts.py` is the seam. Modules register voices, effects, views and commands
into shared dicts, so adding a sound is adding a dict entry and `core.py` never
changes. Missing modules are skipped — the instrument runs with any subset of
them present. Two modules claiming the same name is detected and reported rather
than silently resolved by import order.

## Recording

`R` taps the master inside the audio callback, so a take is exactly what you
heard, performance effects and all. Each one writes `takes/take_NNN.wav` plus the
`.thud` that reproduces it. Recording starts with a 1kHz blip and one white frame
— an audio and visual sync point for lining a screen capture up with clean audio.

Because the engine is deterministic, `render take.wav` re-renders the same
performance offline with no realtime constraint. Record the screen, render the
audio, mux the two.
