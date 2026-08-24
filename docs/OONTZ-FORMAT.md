# The oontz format — source code for music

An MP3 tells you *what happened*. An oontz file tells you *how*.

A complete modern electronic track — arrangement, patterns, notes, automation,
sound design, even its visuals — fits in a few kilobytes of readable text that
renders to the same audio every time, on any machine. Not a description of the
song. The song.

That makes music **inspectable, diffable, forkable, searchable, versionable,
and machine-readable** — the properties source code has had since forever and
recordings have never had.

## Hello world

```
kick x...x...x...x...
```

Press play. Four on the floor.

```
kick x...x...x...x..x
```

Press play again. One character changed; the song changed. That is the whole
idea.

## One song, two representations

The same song exists in two forms, the way a program exists as source and as
an AST. Both are plain text. Both are executable.

### `.thud` — the command log (canonical source)

The exact commands that make the instrument produce the song, one per line.
Comments start with `#`. This is what you'd type; it is also what a take
records and what git diffs beautifully.

```
# acidburn - 303 led, the filter is the song
bpm 138
swing 4
kick x...x...x...x...
hat ..x...x...x...x.
clap ....x.......x...
bass a1! c2 a1~ e2 a1 c2! a1~ g1 a1! c2 d2~ a1 c2 a1! g1~ a1
filter bass lp 340 res 0.94
sidechain bass 0.7
```

Pattern language: `x` hit · `X` accent · `.` rest · `-` tie. Patterns may be
any length — a 5-step hat against a 16-step kick is polymeter, free. Pitched
tracks take note tokens (`a1`, `f#2`); `~` slides into the note, `!` accents
it. Real examples live in [`songs/`](../songs/).

### `.song` — the compiled timeline (JSON)

What the composer emits and the players consume: the whole arrangement as
data. Field-for-field, from `thud/song.py` (`format: "thud-song-1"`):

```jsonc
{
  "format": "thud-song-1",
  "name": "warehouse", "bpm": 138, "swing": 8,
  "key": "a", "scale": "minor",
  "order": ["intro", "build", "drop", "break", "drop2", "outro"],
  "sections": {
    "drop": {
      "bars": 32, "role": "drop", "energy": 1.0,
      "order": ["kick", "hat", "bass"],
      "tracks": {
        "bass": { "voice": "reese", "pat": "x.x.x.x.x.x.x.x.",
                  "notes": ["a1", ".", "a1", "c2"], "gain": 1.0,
                  "filt": "lp", "fc": 340, "res": 0.94,
                  "sc": 0.7, "pan": 0, "tune": 0, "fx": [] }
      },
      "automation": [], "master_fx": []
    }
  },
  "meta":     { "style": "hardtechno", "curve": "classic" },
  "viz":      { "theme": "acid", "mode": "auto" },
  "remix_of": "a1b2c3d4e5f6"
}
```

- `viz` — a song can carry its own look; a custom palette embeds whole, so a
  published track brings its colors to people who never made them.
- `remix_of` — provenance travels in the source; the API keeps the family tree.
- A full five-minute composed track is ~15–40 KB. Small enough to live in a
  git repo, a chat message, an API response, or an AI's context window.

## The determinism guarantee

The engine is a pure function of the source: `state_at(bar)` answers what any
bar sounds like, offline render equals live playback sample-for-sample, and
the QA gate keeps golden renders byte-identical across changes. Two engines —
the Python original (`thud/`) and the browser port (`web/app/oontz.js`) —
derive their music theory from one file and are held to identical output by a
360-arrangement cross-language gate.

Because rendering is deterministic, **storing audio is unnecessary**: a take
is the text that reproduces it, a "recording" is a compiled artifact the way a
PDF is compiled from a document.

## What this makes possible (and what already works)

- **Diff a song** like code: `bpm: 128 → 132`, kick pattern changed in the
  drop, break grew 8 bars. (`diff` in the instrument; git for the files.)
- **Fork with credit**: `remix <id>` opens any public track as source;
  publishing carries `remix_of` automatically.
- **AI as collaborator, not oracle**: `ask`, `jam`, `produce` and `dream` all
  read this structure and answer in command lines you watch apply — editable
  source, never a black-box render.
- **Search the music itself**: the gallery filters on real fields (bpm, key)
  because the fields are real; pattern-level search is a straight extension.
- **Move it anywhere**: `source` prints the song; `source save` downloads it;
  `load` accepts a pasted one. No project files, no stems, no 400 MB.

## Versioning

`format: "thud-song-1"` names this schema. Readers should accept unknown
extra fields (forward compatibility) and refuse unknown formats loudly.
