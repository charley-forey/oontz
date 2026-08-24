# thud

A terminal techno studio and DJ system. You write songs with the keyboard, watch
them on one page that fits any terminal, and mix the ones you keep. Everything is
synthesized — no samples.

```
python -m thud            # the instrument
python -m thud test       # the checks
```

Two modes, switched with `M`.

**STUDIO** — build a song.

```
:compose hardtechno 5     # a whole 5-minute track, arranged
:song info                # what it is
space                     # play
< >                       # jump section        ( ) scrub eight bars
1-8                       # focus a track       L  loop this section
qwertyui asdfghjk         # the 16 step pads
[ ]                       # sweep the filter    (hold)
/                         # loop roll (hold)    \  spinback
:sec add drop 32          # grow the arrangement
:song render out.wav      # the whole song, offline
R                         # record a take
?                         # every key
```

**DECK** — mix what you made.

```
:dload a warehouse        # render a song onto deck A
:dload b acidtrip
:deck b sync              # beat-exact, no detection involved
:deck a loop 8
:eq b low 0               # kill the incoming bass
:xf 0.5                   # crossfade
:transition blend 16
```

## Songs are timelines

A song is sections in an order, and the engine asks it one question:

    song.state_at(bar) -> the track state for that absolute bar

Scrubbing is setting an index. Rendering is asking for every bar in turn.
Automation interpolates inside the answer. Because it is pure, an offline render
is what you heard, to the sample — and a DJ deck is just that render, finished.

`:compose` walks an energy curve through an arrangement grammar and develops one
motif across the whole track, so the drop's bassline is recognisably the intro's.

## The idea

**Oontz is source code for music.** An MP3 tells you what happened; an oontz
file tells you how — and renders to the same audio every time. The full spec:
[`docs/OONTZ-FORMAT.md`](docs/OONTZ-FORMAT.md).

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
    thud/song.py        Song/Section, state_at, automation, offline render
    thud/layout.py      panels declare size and priority; a solver fits them
    thud/theme.py       palette, chrome, widgets - one visual system
    thud/harmony.py     scales, chords, the Camelot wheel, motifs
    thud/compose.py     energy curves, arrangement grammar, whole songs
    thud/deck.py        pre-rendered decks, exact beat grids, sync, cue, loop
    thud/mixer.py       channel strips, EQ kills, crossfader, transitions
    thud/ui_studio.py   the STUDIO page      thud/ui_deck.py  the DECK page
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
