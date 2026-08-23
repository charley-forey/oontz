# thud

A terminal techno instrument. Text patterns are the interface.

```
python -m thud            # the instrument
python -m thud test       # the checks
```

```
:open warehouse           # load a starter song
space                     # play
1-8                       # focus a track
qwertyui asdfghjk         # the 16 step buttons
[ ]                       # sweep the filter
R                         # record a take
?                         # every key
```

Everything is synthesized — no samples. Every session saves to a readable, diffable
`.thud` file that is just the commands you ran, so a song is something you can grep,
diff, and commit.

## How it works

The audio callback slices a pre-rendered bar and does nothing else — no locks, no
queue, no allocation. Editing a pattern re-renders off-thread and swaps the array in
on the next bar boundary. Live performance FX are pointer math on that same buffer.

`thud/contracts.py` is the frozen seam: modules register voices, FX, views and
commands into shared dicts, so adding a sound is adding a dict entry and `core.py`
never changes.

## Layout

    thud/contracts.py   frozen seams and registries
    thud/core.py        state, sequencer, engine, recording, undo, commands
    thud/ui.py          the static page: keys, views, diff renderer
    thud/voices.py      the voice bank
    songs/              starter songbook, one commented .thud per style
