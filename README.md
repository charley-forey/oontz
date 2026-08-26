# 🔊 oontz

**Source code for music.** A terminal techno studio, a DJ booth, an AI bandmate,
and a file format — where a whole five-minute track is a few kilobytes of text
you can read, grep, diff, fork and commit.

```
python -m oontz
```

```
kick x...x...x...x...
```

Press play. That is four on the floor. Change one character and the song
changes. That is the entire idea, and everything below is the consequence of
taking it seriously. 🥁

---

## 📖 Table of contents

- [The 60-second version](#-the-60-second-version)
- [Why this exists](#-why-this-exists)
- [Who it's for](#-who-its-for)
- [Where it runs](#-where-it-runs)
- [Install & first run](#-install--first-run)
- [STUDIO — build a song](#-studio--build-a-song)
- [DECK — mix what you made](#-deck--mix-what-you-made)
- [The pattern language](#-the-pattern-language)
- [The AI ladder: ask → jam → produce → dream](#-the-ai-ladder-ask--jam--produce--dream)
- [The file formats](#-the-file-formats)
- [How it actually works](#️-how-it-actually-works)
- [The sound bank](#-the-sound-bank)
- [Visuals](#-visuals)
- [Every module, explained](#-every-module-explained)
- [The browser build](#-the-browser-build)
- [The API](#-the-api)
- [Recording & video](#-recording--video)
- [Testing: the four gates](#-testing-the-four-gates)
- [Contributing](#-contributing)
- [Deliberately not doing](#-deliberately-not-doing)
- [FAQ](#-faq)

---

## ⚡ The 60-second version

| | |
|---|---|
| **What** | A techno instrument, DJ system and music file format that lives in a terminal |
| **Who** | Anyone who can type. Producers, live coders, DJs, programmers who miss trackers, people who want to make a banger at 2am without opening a DAW |
| **When** | Right now — `python -m oontz`, no install ceremony, no account, no login wall |
| **Where** | Your terminal, or [**oontz.sh**](https://oontz.sh) in any browser, free |
| **Why** | Because an MP3 tells you *what happened*. An oontz file tells you *how* — and renders to the same audio, every time, on any machine 🎯 |
| **How** | Text patterns → a deterministic renderer → one bar rendered ahead of the one you're hearing |

Everything is **synthesized from scratch**. There is not a single sample in this
repository. The kick is math. The hat is math. The screech that ruins your
neighbours' evening is also math.

---

## 🤔 Why this exists

Software got version control, code review, package registries, forks, diffs,
issues, and a culture of reading each other's work. Music got… a WAV file. 😐

You cannot diff two mixes. You cannot fork someone's bassline. You cannot grep a
record for "every track that goes into a breakdown at bar 64." You cannot open a
song and *see how it was made*, because the thing that was shared with you was
the cake, not the recipe.

**oontz shares the recipe.**

The closest honest analogy is not another live-coding language — it is **HTML**.
A web page isn't a screenshot of a web page. It is source, rendered by anything
that speaks the format. oontz does that for a techno track:

```
songs/warehouse.oontz  —  10 lines, 232 bytes, renders to a full driving techno loop
```

```
# warehouse - driving techno, the default starting point
bpm 132
swing 6
kick X...x...X...x..x
hat  ..x...x...x.x.x.
oh   ......x.......x.
clap ....x.......x...
bass a1! . a1~ . c2 . a1 . g1! . a1~ . c2 . d2 .
filter bass lp 420 res 0.8
sidechain bass 0.7
```

That is a *song*. Not a description of a song. Commit it. Diff it. Someone opens
a pull request that changes line 5 and now the hats swing. This is completely
normal for code and completely impossible for music, and that gap is the whole
project. 🚀

The full argument and spec: [`docs/OONTZ-FORMAT.md`](docs/OONTZ-FORMAT.md).
The honest audit of Tidal / Strudel / Sonic Pi / SuperCollider / ABC notation —
what we borrow and what we refuse — is in [`docs/PRIOR-ART.md`](docs/PRIOR-ART.md).

📚 **The whole reasoning, at length** — history, theory, semantics,
architecture, metaphors, economics, and a conformance checklist you can build
your own language from: [**The Song Is the Source**](https://oontz.music/language)
(~21,000 words). Outline: [`docs/THE-LANGUAGE.md`](docs/THE-LANGUAGE.md).

---

## 👥 Who it's for

- 🎹 **Producers** who are faster at typing than at dragging rectangles.
- 🖥️ **Terminal people** who want the one app they never have to leave.
- 🎧 **DJs** who want to mix tracks they made ten seconds ago, beat-exact, with
  no beat detection involved because the engine already knows where every beat is.
- 🧑‍💻 **Programmers** who miss trackers, or who want to see what happens when you
  apply source-control thinking to a kick drum.
- 🤖 **People who want to argue with an AI about their arrangement** and win.
- 🎓 **Learners** — `why` explains what you just did and why it works, and the
  built-in theory corpus covers 15 genres with real rules, not vibes.

You need **zero** music theory to start. Type `:compose hardtechno 5` and you have
a five-minute arranged track. You need zero install to start either — the browser
build is the same instrument.

---

## 🌍 Where it runs

| Where | What you get | Cost |
|---|---|---|
| **Your terminal** — `python -m oontz` | The full instrument. 36 modules, 33 voices, 21 effects, two DJ decks, the AI, offline render | free |
| [**oontz.sh**](https://oontz.sh) | The same instrument in any browser, WebAudio, installable as a PWA, no account needed | free |
| [**oontz.music**](https://oontz.music) | The story, a demo that plays in the page, the public gallery, shared playlists | free |
| [**api.oontz.sh**](https://api.oontz.sh/health) | Accounts, song storage, gallery, search, playlists, AI proxy, live rooms | free |
| [**oontz.sh/py/**](https://oontz.sh/py/) | 🧪 The *real Python engine* running in your browser via Pyodide + numpy in WASM | free, experimental |

All three sites run on Railway, auto-deploying from `main`. The server **never
touches audio** — every note you hear is rendered on your own machine. That is
why it can be free for everyone: a gallery of songs is a gallery of a few
kilobytes each, not a bandwidth bill. 💸

---

## 🛠️ Install & first run

```bash
git clone https://github.com/charley-forey/oontz.git
cd oontz
pip install numpy sounddevice        # that is the entire dependency list
python -m oontz
```

`numpy` does the DSP. `sounddevice` opens your speakers. Nothing else is
required — no DAW, no VST, no sample pack, no audio interface.

```bash
python -m oontz                  # the instrument
python -m oontz songs/warehouse.oontz   # open straight into a song
python -m oontz test             # the self-check (~9 s)
python -m oontz.qa               # the deep QA suite
python -m oontz.qa --quick       # 13 checks, ~30 s
python -m oontz theory export    # regenerate theory.js / theory.json
```

**Don't want to install anything?** Go to [oontz.sh](https://oontz.sh). Same
instrument, WebAudio instead of numpy. 🌐

### Your first sixty seconds

```
:compose hardtechno 5      # a whole 5-minute track, arranged, with a real energy curve
space                      # play it
:song info                 # what it actually is — sections, key, BPM, energy
>                          # jump to the next section
1                          # focus track 1
[ [ [                      # sweep the filter down (hold it)
/                          # loop roll (hold)
R                          # record a take
?                          # every key on one page
```

---

## 🎛️ STUDIO — build a song

Press `M` to switch modes. STUDIO is where a song gets made.

### The keys

**Everywhere, both modes:**

| key | does |
|---|---|
| `space` | play / stop |
| `M` | switch STUDIO ⇄ DECK |
| `R` | record a take |
| `:` | command line |
| `Tab` | cycle visualiser |
| `?` | every key, one page |
| `Ctrl-Z` / `Ctrl-Y` | undo / redo |
| `Esc` | cancel |
| `Ctrl-C` | quit |

**STUDIO:**

| key | does |
|---|---|
| `1`–`8` | focus a track |
| `qwertyuiasdfghjk` | the 16 step pads — toggle steps on the focused track |
| `z` / `x` | mute / solo |
| `n` | generate a variation of this track |
| `[` `]` | sweep the filter (hold) · `{` `}` resonance |
| `-` `=` | BPM ∓1 · `_` `+` BPM ∓10 · `T` tap tempo |
| `,` `.` | swing down / up |
| `A` | A/B compare — flip between two versions of the state |
| `<` `>` | previous / next section |
| `(` `)` | scrub back / forward eight bars |
| `L` | loop this section |
| `/` | loop roll (hold) — re-reads the last 1/16th |
| `v` | stutter · `\` spinback · `` ` `` tape stop · `c` reverse · `b` brake |

### The commands

Everything typed after `:`. **45 high-level commands** on top of **35 core verbs**:

```
:compose hardtechno 5       whole track, arranged, energy curve and all
:styles                     16 style packs to compose from
:song info                  sections, bars, key, BPM, energy curve
:song render out.wav        the entire song, offline, faster than realtime
:sec add drop 32            grow the arrangement
:scene save / :scene recall  snapshot the whole mixer state
:euc kick 5 16              euclidean rhythm — 5 hits spread over 16 steps
:melody / :motif            scale-aware melodic generation
:build 16 / :drop / :break  arrangement moves as automation ramps
:ramp filter 400 4000 16    automate anything over N bars
:grade                      the AI grades your arrangement against genre rules
:crit                       19 specific claims about what is wrong
:why                        why does what you just did work?
:lib                        the songbook, with Camelot-compatible neighbours
:theory hardtechno          the rules for a genre, in plain language
```

### Songs are timelines ⏱️

A song is **sections in an order**, and the engine asks it exactly one question:

```python
song.state_at(bar) -> the track state for that absolute bar
```

That's it. Scrubbing is setting an index. Rendering is asking for every bar in
turn. Automation interpolates *inside* the answer. Because the function is pure,
an offline render is byte-identical to what you heard live — and a DJ deck is
just that render, finished. 🎯

`:compose` walks an **energy curve** through an **arrangement grammar** and
develops **one motif** across the whole track — so the drop's bassline is
recognisably the intro's, the way a real track works.

---

## 🎚️ DECK — mix what you made

Press `M`. Now you have two decks and a crossfader.

```
:dload a warehouse          render a song onto deck A
:dload b acidtrip           and another onto deck B
:deck b sync                beat-exact — no beat detection, the engine knows
:deck a loop 8              loop 8 bars
:eq b low 0                 kill the incoming bass
:xf 0.5                     crossfade
:transition blend 16        a real 16-bar blend, bar-stamped
```

| key | does |
|---|---|
| `1` `2` | focus deck |
| `s` | sync · `c` cue · `l` loop 4 · `u` loop off |
| `[` `]` | filter |
| `,` `.` | crossfade toward A / B |
| `7` `8` `9` | kill low / mid / high |
| `/` | loop roll |

**Why sync is exact, not approximate:** every other DJ tool has to *detect* the
beat grid from audio, and it gets it wrong. oontz rendered the audio from a
score, so it already knows where every beat, bar and section boundary is. Sync
is arithmetic, not analysis. 🎯

`library.py` scores **Camelot-wheel compatibility** and BPM distance between
every pair of songs, so "what mixes well with this" is a query, not a guess.

---

## 🔤 The pattern language

Text is the interface. That is not an aesthetic choice — it is what makes a song
greppable, diffable and committable.

### Drums

```
kick x...x...x...x...
hat  ..x...x...x.x.x.
clap ....x.......x...
```

| token | means |
|---|---|
| `x` | a hit |
| `X` | an accent (louder) |
| `.` | a rest |

### Pitched tracks

```
bass a1! . a1~ c2 . g1 . d2~
```

| token | means |
|---|---|
| `a1` | note A, octave 1 |
| `~` | slide into the next note (303-style glide) |
| `!` | accent |
| `.` | rest |

### 🌀 Polymeter, for free

Patterns can be **any length**. Put a 5-step hat against a 16-step kick and they
only realign every 80 steps — so the same two patterns keep sounding like new
combinations for a minute and a half. No feature was added for this. It falls
out of not hardcoding the bar length.

```
kick x...x...x...x...      16 steps
hat  ..x.x                  5 steps  →  realigns every 80
```

### Everything else is a command

```
bpm 138                     tempo
swing 6                     swing, in percent
filter bass lp 420 res 0.8  a filter on a track
sidechain bass 0.7          duck this track under the kick
fx bass drive 0.4           any of 21 effects on any track
track add rumble sub        oontz is not fixed at 8 tracks
```

---

## 🤖 The AI ladder: ask → jam → produce → dream

Four rungs, each built on the one below. All four are **shipped and working**.
The AI never touches audio — it writes *commands*, the same ones you could type,
so every suggestion lands in the undo stack and in the `.oontz` file like
anything else. You can always see exactly what it did, and always take it back
with one key. ✋

### 1️⃣ `ask` — it proposes, you press Enter

```
:ask make the bassline nastier
```

It replies with command lines. Empty Enter accepts, `undo` reverts. Every
suggestion is **validated against the real command table before it is even
shown to you** — a hallucinated verb never reaches the screen.

### 2️⃣ `jam` — a bandmate, not autocomplete

The AI takes a turn every N bars — a variation, a fill, a filter move — tells you
what it did in six words, and you veto with one key. It has graded ears and a
mood. It is playing *with* you on the beat grid. 🎸

### 3️⃣ `produce` — the closed loop, made watchable

```
grade → find the worst fault → fix it in the fewest commands → grade again
```

A round that makes the track *worse* is reverted on the spot. Two bad rounds and
it stops while it's ahead. One `undo` takes back the whole pass. You watch the
score move. 📈

### 4️⃣ `dream` — prose in, arranged track out

```
:dream driving acid at 3am
```

It picks the style, the length and the energy curve, composes the track, then
pushes the result toward your words. ✨

### The grader is not a vibe

`theory.py` holds a real corpus: **15 genres** (acid, ambient, breakbeat,
downtempo, dubtechno, electro, garage, hardtechno, house, industrial, jungle,
minimal, psytrance, techno, trance), each with roles and rules. `:grade` scores
your arrangement against them. `:crit` makes 19 specific claims about what is
wrong. The same rules are exported to `theory.js` and `theory.json`, so the
desktop AI, the browser AI and the API all argue from **one source of truth**.

**Bring your own key:** `key sk-ant-…` links your own Anthropic key. It stays in
your browser and is sent per request. The API prefers it and never stores it —
there is no secret at rest for anyone to leak. 🔐

---

## 📄 The file formats

Two representations of the same thing, the way a program exists as source and as
an AST. Both are plain text. Both are executable.

### `.oontz` — the command log (canonical source)

The exact commands that make the instrument produce the song, one per line.
Comments start with `#`. This is what you'd type; it is also what a recording
saves alongside the WAV, and it is what git diffs beautifully.

```
# warehouse - driving techno
bpm 132
kick X...x...X...x..x
bass a1! . a1~ . c2 . a1 .
```

### `.song` — the timeline (`format: "oontz-song-1"`)

JSON. Sections, order, per-track state, automation curves. A few KB for a
five-minute track. This is what the gallery stores and what a share link
carries.

```json
{
  "format": "oontz-song-1",
  "name": "warehouse",
  "bpm": 132,
  "key": "a", "scale": "minor",
  "order": ["intro", "build", "drop", "break", "drop", "outro"],
  "sections": { "...": "..." }
}
```

> 📜 **Compatibility:** files written before the rename say `format:
> "thud-song-1"`. Readers still accept it. Nothing you saved has stopped working.

### Determinism is the load-bearing property 🏗️

The same file renders to the same samples on the Python engine, the JavaScript
port and the Pyodide build. That is checked in CI: `golden renders` hashes twelve
songs sample-for-sample, and `composers agree` verifies **360 arrangements** are
identical in Python and JavaScript. If the two engines ever drift, the build
fails. This is the only reason a song can be a few KB and still be *the song*.

---

## ⚙️ How it actually works

Two mechanisms, kept strictly apart. Between them they cover everything. 🧠

### 🔮 Render-ahead

A worker thread keeps **bar N+1 rendered while bar N plays**, so the audio
callback only ever *slices an array* — no locks, no queue, no allocation on the
audio thread. Automation, arrangement, scene changes and generative variation
all happen in the worker where they're allowed to take their time.

Measured: **~0.2 s to render a 1.8 s bar**. Nine times realtime, one bar ahead.

A render that overruns reuses the current bar and counts a **visible drop**
rather than glitching. You can see the engine sweat.

### 👉 Pointer math

Live effects **don't re-render anything** — they read that same buffer
differently.

- **Loop roll** re-reads the last 1/16th
- **Spinback** advances the read pointer at a decaying rate
- **Reverse** walks backwards
- **Tape stop** decays the rate to zero
- **Scratch** oscillates it

Instant, zero-allocation, and *authentic* — because that is physically what a
turntable does to a record. 💿

### 🧩 The contract seam

`contracts.py` is the frozen boundary. Modules **register** voices, effects,
views and commands into shared dicts:

```python
VOICES["screech"] = ...      # adding a sound is adding a dict entry
FX["bitcrush"] = ...         # core.py never changes
COMMANDS["compose"] = ...
VIEWS["spectrum"] = ...
```

Consequences that matter:

- ✅ **Missing modules are skipped.** The instrument runs with any subset present.
- ✅ **Two modules claiming the same name is detected and reported**, not silently
  resolved by import order.
- ✅ **A `COMMANDS` function returns command strings, never mutated state** — which
  is exactly why every AI suggestion, every generated fill and every arrangement
  move lands in undo and in the `.oontz` file like something you typed.

---

## 🔊 The sound bank

**33 voices**, every one synthesized, no samples:

| family | voices |
|---|---|
| 🥁 **Kicks** | `kick` `kick_hard` `kick_dist` |
| 🎩 **Hats & cymbals** | `hat` `oh` `ride` `crash` |
| 👏 **Percussion** | `clap` `snare` `rim` `tom` `perc` `metal` `noise_hit` |
| 🎸 **Bass** | `bass` `sub` `reese` `wob` `donk` |
| 🎹 **Leads & synths** | `lead` `pluck` `stab` `hoover` `screech` `chord` `fm` `bell` |
| 🌫️ **Texture** | `pad` `atmos` `air` `rumble` `riser` `downlifter` |

**21 effects** — 12 processors and 9 performance effects:

| | |
|---|---|
| 🎛️ **Processors** | `drive` `fold` `bitcrush` `delay` `reverb` `chorus` `phaser` `eq3` `comp` `limiter` `gate` `width` |
| 🎪 **Performance** | `roll` `stutter` `spinback` `tapestop` `reverse` `brake` `scratch` `gate_pattern` `crossfade` |

**16 style packs** for `:compose`: acid, ambient, breakbeat, downtempo, dubtechno,
electro, garage, hardtechno, house, hypnotic, industrial, jungle, minimal,
psytrance, techno, trance.

**5 visualisers** in the terminal: `spectrum` `scope` `meters` `freq` `stereo` —
FFT spectrum, braille oscilloscope, level meters, frequency-occupancy map and a
goniometer, all drawn in text.

---

## 🌈 Visuals

The clock is **exact**. Every bar, beat and section boundary is known *in
advance* — so the visuals can **anticipate the drop** instead of detecting it
late. Nothing else in visualiser-land gets to do this.

**8 modes:** `spectrum` `scope` `tunnel` `particles` `kaleido` `feedback` `stars`
`terrain`

**12 themes:** acid · warehouse · sunset · mono · ultraviolet · lava · oilslick ·
vapor · matrix · neonnoir · blacklight · aurora 🎨

Each theme is a small JSON object — palette, glow, intensity, decay, symmetry —
so **you can make your own and share it like a song**. `theme make` builds one,
`theme del` removes it, and customs never overwrite the built-ins.

Text sits *over* the moving graphics, so every glyph carries its own dark halo.
That is what keeps the terminal readable without hiding the art behind a slab.

---

## 📚 Every module, explained

**12,400+ lines of Python across 36 modules.** Every one has a single job.

### Foundation

| module | job |
|---|---|
| `oontz/contracts.py` | 🔒 The frozen seam: `Snapshot`, the four registries, audio conventions, `VERSION`. Change this only deliberately. |
| `oontz/core.py` | ❤️ State, sequencer, scheduler, audio engine, recording, undo, the 35 core commands. |
| `oontz/term.py` | Shared terminal primitives every view uses. |
| `oontz/theme.py` | Palette, chrome, widgets — one visual system, two schemes (`night`, `amber`). |
| `oontz/layout.py` | Panels declare size and priority; a solver fits them to *your* terminal. |

### Sound

| module | job |
|---|---|
| `oontz/voices.py` | The original voice bank. |
| `oontz/drums.py` | Hard techno drums: `kick_hard`, `kick_dist`, `rumble`, `ride`, toms. |
| `oontz/synths.py` | `sub`, `reese`, `hoover`, `pluck`, `lead`, `screech`, `pad`, `atmos`, `fm`. |
| `oontz/fx.py` | Drive, fold, bitcrush, delay, reverb, chorus, phaser, 3-band EQ. |
| `oontz/dj.py` | The performance effects — roll, stutter, spinback, tapestop, reverse, brake, scratch. All pointer math. |
| `oontz/mixer.py` | Channel strips, EQ kills, crossfader, bar-stamped transitions. |

### Composition

| module | job |
|---|---|
| `oontz/song.py` | `Song` / `Section`, `state_at`, automation, offline render. The timeline model. |
| `oontz/arrange.py` | Scenes, automation ramps, build / drop / break, song timeline, sets. |
| `oontz/compose.py` | Energy curves, the arrangement grammar, whole songs from one word. |
| `oontz/gen.py` | Euclidean rhythms, scale-aware melody, the style packs. |
| `oontz/harmony.py` | Scales, chords, the Camelot wheel, motif development. |
| `oontz/theory.py` | The 15-genre corpus: roles, rules, the grader. Exported to JS and JSON. |
| `oontz/library.py` | The songbook — scans `songs/`, scores key and BPM compatibility. |
| `oontz/deck.py` | Pre-rendered decks, exact beat grids, sync, cue, loop. |

### Interface

| module | job |
|---|---|
| `oontz/ui.py` | The static page: keys, views, the diff renderer. |
| `oontz/ui_studio.py` | The STUDIO page. |
| `oontz/ui_deck.py` | The DECK page. |
| `oontz/keymap.py` | 🔑 **The table.** Every key oontz responds to is declared exactly once, right here. 51 bindings, 60 studio keys, no duplicates — and that's a test. |
| `oontz/keyboard_view.py` | The on-screen keyboard legend. |
| `oontz/viz_spectrum.py` | FFT spectrum, meters, frequency occupancy. |
| `oontz/viz_scope.py` | Braille oscilloscope, goniometer. |
| `oontz/waveform.py` | Waveform drawing. |
| `oontz/teach.py` | Context hints, the key legend, `why()`, the guided lesson. |

### Intelligence

| module | job |
|---|---|
| `oontz/ai.py` | ask / jam / produce / dream. Validates every suggestion against the real command table before showing it. |
| `oontz/copilot.py` | The suggestion surface — proposals land as commands you could have typed. |
| `oontz/director.py` | The words people actually use, mapped onto things oontz can do. |

### Quality

| module | job |
|---|---|
| `oontz/selftest.py` | `python -m oontz test` — the fast gate. |
| `oontz/qa.py` | 13 deep checks: golden renders, fuzzing, soak, layout sweep, composer agreement. |
| `oontz/web.py` | Packs `oontz/` + `songs/` into the browser bundle. |

### Everything else

```
songs/            the songbook — one commented .oontz per style, plus .song timelines
tests/golden.json 12 render hashes. If the sound changes, this fails.
docs/             the format spec, the prior-art audit, the research article
scripts/          pack_oontz.py, browsergate.py, seed_gallery.py
web/app/          oontz.sh — the instrument in the browser
web/landing/      oontz.music — the story and the gallery
api/              accounts, storage, gallery, search, playlists, AI proxy, rooms
```

---

## 🌐 The browser build

`web/app/` is **oontz.sh**: the same instrument, WebAudio instead of numpy, all
client-side. ~6,500 lines.

| file | job |
|---|---|
| `oontz.js` | The engine — the WebAudio port of the voice bank and sequencer |
| `compose.js` | The port of `compose.py` + arrangement |
| `theory.js` | 🤖 **Generated** from `theory.py` by `python -m oontz theory export` — never edited by hand |
| `viz.js` | The 8 visual modes and 12 themes |
| `ear.js` | In-browser analysis — the grader's ears |
| `eargate.js` | 👂 An automated listener over generated music: `node web/app/eargate.js` |
| `touch.js` | Paint drums with a finger 👆 |
| `midi.js` | WebMIDI in |
| `account.js` | Sign-in, save, publish |
| `plan.js` | Transition planning |
| `sw.js` + `manifest.webmanifest` | 📱 PWA — installs to your home screen, works offline |
| `check.js` | The pure-logic gate: song model, keys, FFT, theory, XSS and allowlist guards |

**Every capability is reachable three ways** — typed, tapped, and through the
command palette. A feature does not exist until all three know about it.

### 🧪 `/py/` — the real Python engine, in your browser

`web/app/py/` runs the **actual `oontz` package** through Pyodide: numpy compiled
to WASM, rendering in a Web Worker, an AudioWorklet slicing the buffer.

This works *because* of the render-ahead design. oontz never runs Python per
sample — it renders bar N+1 while bar N plays, and the callback only slices. So
Python being slow-ish and garbage-collected doesn't matter: it isn't in the audio
path. Measured at **185 ms a bar** in the browser. 🤯

Long term this deletes the JS port and leaves **one engine**. Today it's a spike
you can go play with.

---

## 🔌 The API

`api/main.py` — FastAPI, SQLite, ~1,350 lines. **Deliberately small.** No audio
ever reaches it, because a song is text and the render happens in your browser.

```
GET    /health                    is it up, and does it have an AI key
POST   /auth/request              email a magic link
GET    /auth/verify               redeem it
GET    /me                        who am I     PATCH /me   set your handle
POST   /songs                     save a song (a few KB of JSON)
GET    /songs                     your songs   GET /songs/{id}   one song
POST   /songs/{id}/publish        put it in the gallery
GET    /songs/{id}/remixes        🌳 the family tree, both directions
GET    /gallery                   what's public
GET    /search                    by BPM, key, pattern, structure
GET    /similar/{id}              Camelot + energy + structure similarity
POST   /similar                   similarity for a song you haven't saved
GET    /charts                    what's being played
POST   /takes                     store a take — the .oontz log, not the WAV
GET/POST/PATCH/DELETE /playlists  ordered lists, public or private
PUT    /playlists/{id}/items      reorder
GET    /p/{id}                    the public share page, with real OG tags
POST   /ai/ask                    the AI proxy
POST   /rooms + WS /ws/room/{code} 🎪 live rooms — two browsers, one track
```

### 🔐 Auth, kept minimal

Email plus a magic link. **No passwords to leak, no OAuth to maintain.** You can
use the entire instrument with no account at all — an account only buys you
storage and publishing. Local work lives in `localStorage` until you want it kept.

The service **refuses to start** in production if `OONTZ_SECRET` is unset (every
session would be forgeable) or `OONTZ_API_URL` is unset (every magic link would
be a relative URL). Better a loud crash than a quiet vulnerability. 💥

---

## 🎥 Recording & video

`R` taps the master **inside the audio callback**, so a take is exactly what you
heard — performance effects, drops, the lot. Each one writes:

```
takes/take_NNN.wav      the audio
takes/take_NNN.oontz    the commands that reproduce it
```

Recording starts with a **1 kHz blip and one white frame** — an audio *and*
visual sync point, so you can line a screen capture up with clean audio to the
frame. 🎬

Because the engine is deterministic, `render take.wav` re-renders the same
performance offline with no realtime constraint. **Record the screen, render the
audio, mux the two.** The video is the messy live capture; the audio is perfect.

---

## ✅ Testing: the gates

Nothing merges unless all of these pass. Run from the repo root.

| gate | covers | time |
|---|---|---|
| `python -m oontz test` | the desktop engine end to end | ~9 s |
| `python -m oontz.qa --quick` | 13 checks incl. golden renders and "composers agree" | ~30 s |
| `node web/app/check.js` | the browser's *pure* half: song model, keys, FFT, theory, XSS guards | instant |
| `python scripts/browsergate.py` | the browser's *real* half — drives `index.html` in headless Edge | ~4 min |
| `python scripts/landinggate.py` | oontz.music: runs the real `server.py` at `/t/<id>`, every asset 200, the card, one-tap audio | ~20 s |
| `python api/check.py` | when `api/` changed | instant |

### What the QA suite actually checks

```
registries        25 modules, no collisions, no import errors
voices            33 voices, legal shape, finite, ≤ 0 dBFS
effects           21 effects: shape preserved, input untouched, finite
views             5 views exact-width at 3 terminal sizes
keymap            51 bindings, 60 studio keys, no duplicates
layout sweep      60 size/mode combinations: exact width, no overlap, stable
command fuzzer    600 random command lines, 0 uncaught exceptions
song invariants   72 bars: boundaries exact, automation exact, render byte-identical
scrub == render   scrubbed bars match the offline render sample-for-sample
performance fx    9 performance effects stayed in bounds over 400 calls each
audio soak        3758 blocks, worst callback % of budget, 0 drops
golden renders    12 songs hashed sample-for-sample — if the sound changed, this fails
composers agree   360 arrangements identical in Python and JavaScript
```

### 🕵️ Why `browsergate.py` exists

Everything needing a DOM or an AudioContext used to be verified **by eyeballing
screenshots**. That is how `kick x...x...x...x...` shipped broken on a cold page,
how every offbeat track measured as silence, and how `measure()` shipped opening
one `OfflineAudioContext` per track — the browser stops handing them out, so the
whole thing simply stalled.

Now it drives the real page in an iframe and reports each result back over HTTP
*as it runs*, so a hang **names the test that hung**. 🎯

### After you edit

```bash
python scripts/pack_oontz.py     # after editing any oontz/ module — the selftest fails on a stale bundle
python -m oontz theory export    # after editing oontz/theory.py — regenerates theory.js and theory.json
python -m oontz.qa --bless       # only when a sound change is intentional
```

---

## 🤝 Contributing

The architecture is built so that **adding things doesn't require changing
`core.py`**.

**Adding a voice:** write a function, put it in `VOICES`. Done. It's now on the
command line, in the AI's vocabulary, in the browser's completion list, and in
the test suite.

**Adding an effect:** same, into `FX`. The QA suite will immediately check that
it preserves buffer shape, doesn't mutate its input, and stays finite.

**Adding a command:** put it in `COMMANDS`. It must return command strings, not
mutated state — that is what makes it undoable and loggable for free.

**Adding a genre:** one entry in `theory.py` with roles and rules. The grader
enforces it, `theory export` pushes it to the browser and the API.

**The rules:**

1. 📏 **`contracts.py` changes are deliberate and versioned.** Everything else is
   free to move.
2. 🎯 **Non-trivial logic leaves one runnable check behind.** An `assert`-based
   `demo()` in the module, or an entry in `qa.py`. No frameworks, no fixtures.
3. 🔊 **If a sound change is intentional, bless it.** `python -m oontz.qa --bless`
   and say so in the commit. Never bless to make red go away.
4. 🚦 **All four gates, every time.**

`ROADMAP.md` is the backlog and the cycle log. `PLAN.md` is where this is
going and why. Read both before proposing something large.

---

## 🚫 Deliberately not doing

Being clear about the *no* is how the *yes* stays sharp.

- ❌ **Storing audio server-side.** Takes are text; audio is rendered where it is
  played. This is what makes the whole thing free.
- ❌ **Streaming rendered audio from a server.** 200 ms round trip kills an
  instrument, and CPU-per-listener-per-second kills "free."
- ❌ **Passwords or OAuth.** A magic link is enough and leaks nothing.
- ❌ **Storing users' AI keys.** Browser-side only. No secret at rest.
- ❌ **Samples.** Everything is synthesized. A song stays kilobytes.
- ❌ **More chrome.** The terminal *is* the identity. Polish means fewer, better
  words and exact colour discipline, not more boxes.

---

## ❓ FAQ

**Do I need to know music theory?**
No. Type `:compose hardtechno 5` and you have a track. Then type `:why` and it
tells you what it did and why it works. 🎓

**Do I need an audio interface / a DAW / plugins?**
No. `pip install numpy sounddevice` is the entire dependency list. Or open
[oontz.sh](https://oontz.sh) and install nothing at all.

**Can I use it on my phone?**
Yes — oontz.sh is a PWA. Install it to your home screen. You can paint drums with
a finger, and it keeps the screen awake while you play. 📱

**Is the AI required?**
No. It is one module out of 36 and the instrument runs perfectly without it. Set
`OONTZ_OFFLINE=1` and it will politely say it's unavailable. The gates set this
so a fuzzed `ask` never calls a model.

**Why does a song sound identical everywhere?**
Because determinism is enforced by a test. Twelve songs are hashed sample-for-
sample and 360 arrangements are compared between the Python and JavaScript
engines on every run. Drift fails the build.

**What happened to "thud"?**
That was the old name. It is now oontz, top to bottom — the package, the file
extension, the format string, the sites. Old `.thud` files and
`format: "thud-song-1"` documents are still readable. 👋

**Is it actually good techno?**
Open `songs/`, run `python -m oontz songs/warehouse.oontz`, press space, and
decide for yourself. That's a 232-byte file. 🔊

---

<div align="center">

**🔊 oontz** · v3.0

[oontz.sh](https://oontz.sh) — make it · [oontz.music](https://oontz.music) — hear it ·
[the format](docs/OONTZ-FORMAT.md) — read it ·
[the article](https://oontz.music/language) — study it

*You share the recipe, not the cake.* 🍰

</div>
