# oontz — goal and plan

Written 2026-08-24. The single source for *where this is going*; ROADMAP.md stays
the per-cycle backlog and log.

## The goal, in one sentence

**oontz.music** tells people who we are and what we do. **oontz.sh** *is* the
software — the same instrument you get from `python -m oontz`, running in the
browser for anyone, free, with an account only if you want to keep things.

## The two sites, and what each is for

| site | job | never does |
|---|---|---|
| `oontz.music` | the story, a 30-second demo in the page, the public gallery, playlists people shared, "open the real one" | the full instrument |
| `oontz.sh` | the instrument: **CREATE** (studio, you + the AI) and **MIX** (decks, your playlists, transitions), sign-in, record, save, publish | marketing copy |
| `api.oontz.sh` | accounts, songs, takes, playlists, gallery, AI proxy | audio |

## The decision that matters: one engine, not two

There are two composers today: `oontz/` (Python, the real one, 20 modules) and
`web/app/oontz.js` (a 725-line JS port). ROADMAP already calls the drift between
them a risk and built `theory.py → theory.js` to contain it. That is a treatment,
not a cure.

The honest way to put "the actual software" at oontz.sh is **Pyodide**: run the
real `oontz` package in the visitor's browser (numpy in WASM), the terminal page
drawn from `ui.build()` exactly as on the desktop, audio through an AudioWorklet.
ARCHITECTURE-WEB.md rejected Pyodide because of "GC pauses in the audio path" —
but oontz's audio path never runs Python per sample. It renders bar N+1 while bar N
plays (`core.render_bar`) and the callback only slices a buffer. That design is
what makes it viable: Python renders in a Web Worker, the worklet slices.

Why not stream audio from a server? Latency kills an instrument and every listener
costs CPU per second — "free for everyone" is impossible that way. The browser is
the only place it is free.

**Phase 0 is a spike with a number attached.** If a full bar renders in under
~1.2 s in Pyodide on a normal laptop (native is 0.2 s for a 1.8 s bar), we switch
oontz.sh to the real engine and delete the JS port. If not, the JS port stays and
we vectorise `svf` first (already on the roadmap, it is 99 ms of that 200 ms). The
landing page keeps its 80-line toy either way — it is a demo, not the product.

What the spike needs from `oontz/`: `sounddevice` import made optional, a
JS-callable surface (`do(cmd)`, `render_bar()`, `snapshot()`, `ui.build()`), and
the render-ahead scheduler driven from JS instead of a thread. Small changes at
the seams `contracts.py` already draws.

## Phases

### 0. Truth (this week)
- [x] Banners spelled "oontz" / "oontz.sh" (the block font drew the *t* as an *n*).
- [ ] DNS at Namecheap (records in the session notes; owner: Charley). Then point
      both pages' `API` constant and `OONTZ_API_URL` at `https://api.oontz.sh`.
- [ ] Resend sending domain for `oontz.sh` so magic links reach people who are
      not the account owner. Until then sign-in does not work for the public.
- [ ] `ANTHROPIC_API_KEY` on the api service (a real one — the last one was the
      Resend key).
- [ ] Pyodide spike, go/no-go number recorded in ROADMAP.

### 1. Accounts that buy something
Email + magic link exists. Add what a signed-in user actually gets:
- **Takes.** `R` records; a signed-in `save` stores the *take* — the `.oontz`
  command log, a few KB — not the WAV. The engine is deterministic, so a take
  re-renders identically anywhere. Storage stays free.
- **Playlists.** Ordered lists of songs (yours or public ones), `public` flag,
  a share URL `oontz.music/p/<id>`.
- **Bring your own key.** `key sk-ant-…` links an Anthropic key for `ask`. It is
  kept in the browser and sent per request; the API prefers it over the shared
  key and never stores it. No secret at rest we could leak.
- **Handle.** One word, shown on the gallery and playlists.

### 2. The public page
- `oontz.music` gallery plays a track *in the page* (the engine is shared).
- Every track and playlist has its own URL with real OG tags, so a link pasted
  anywhere shows the title, BPM, key and a play button.
- Sort by new / plays / BPM / key; filter by style. Camelot-compatible
  "mixes well with" on every track — `library.py` already scores this.

### 3. CREATE — you and the AI
- Two-column page like the desktop STUDIO: pattern grid + the AI's proposals.
- `ask` proposes, empty Enter accepts, `undo` reverts (exists). Add **`jam`**: the
  AI takes a turn every N bars — a variation, a fill, a filter move — and says what
  it did, and you can veto with one key. A duet, not autocomplete.
- More styles: the theory corpus has 8 genres; add breaks, dub techno, trance,
  electro, ambient — each is a `theory.py` entry with roles + rules, and the grader
  checks the generator honours them.
- `critique` in the browser at parity with `theory.py` (19 claims, not 6).

### 4. MIX — a set from a playlist
- `mix <playlist>`: loads the deck queue. `mixer.plan_transition` already returns
  bar-stamped steps; drive them from the deck clock (roadmap: transition
  scheduler) so a blend actually happens over 16 bars instead of all at once.
- **Auto-set**: order by Camelot key + BPM distance (`library.py`), pick the
  transition type by energy delta (blend / cut / filter / echo-out), and `flow`
  plays the whole playlist as one continuous set you can take over at any moment.
- Hot cues, loops and the DJ effects routed through the deck read pointer
  (roadmap: deck performance FX).
- Record the set as a take, publish it as a *mix*.

### 5. Visuals that belong to the music
The clock is exact — we know every bar, beat and section boundary in advance, so
visuals can *anticipate* the drop instead of detecting it late.
- A canvas layer under the terminal text: spectrum, scope, goniometer (the
  desktop `viz_*` modules), plus generative modes — tunnels, feedback, particles —
  driven by beat phase, band energy per track, and section (intro / build / drop).
- **`viz <mode>`**, **`theme <name>`**, and a small parameter set (palette,
  intensity, decay, symmetry) users can save with a song. Themes are JSON; people
  can share them like songs.
- Everything reads the same `AnalyserNode` + clock interface, so the visual layer
  survives the engine swap.

### 6. The loop that keeps it improving
- Gate stays: `python -m oontz test` + `python -m oontz.qa` + `node web/app/check.js`,
  and a web cycle is done only when Railway reports SUCCESS and the live file has
  the change.
- Cycles pick the top open item here, do it, prove it, log it (ROADMAP "Cycle log").
- Every agent works on a branch in its own worktree; main only moves by a
  fast-forward after the gate passes.

## Source code for music — the thesis (added 2026-08-24)

Git made source code collaborative. Oontz makes music **executable, inspectable,
remixable, and machine-readable**. The closest analogy is not another live-coding
language; it is HTML: not a screenshot of the website, the source of it, rendered
by anything that speaks the format. The recording becomes a compiled artifact —
a PDF generated from the document. The spec lives in `docs/OONTZ-FORMAT.md`.

Three layers, in the order they compound:

1. **The format.** `.oontz` (command log) and `.song` (`format: "oontz-song-1"`
   JSON timeline) — tiny, deterministic, diffable, already real.
2. **The ecosystem.** Fork/remix with provenance (shipped), playlists and share
   pages (shipped), then: structural search, a module registry ("npm for
   sounds" — behavior, not sample packs), PR-style collaboration on songs.
3. **The intelligence layer.** AI that reads and edits the source and shows its
   diff (ask/jam/produce/dream — shipped), then: agents that aim at references,
   and the edit-history corpus (state → instruction → exact transformation →
   accepted or vetoed) that nothing else in music has.

What is true today vs. future (kept honest so the loop builds in order):

| Claim | Status |
|---|---|
| Song as tiny executable text, deterministic renders | shipped |
| AI edits source in the open; user vetoes | shipped (jam/produce/dream) |
| Provenance: remix lineage both directions | shipped |
| In-instrument structural diff, source export/import | shipped this cycle |
| Search by bpm/key/pattern/structure + similarity + family tree | shipped |
| Module registry, marketplace, PR merge UI | later |
| Adaptive/game runtime (music as logic reacting to state) | later |
| Deliberate edit-history dataset (RLHF-for-music) | shipped 2026-08-25; opt-out, IP kept, written down in `privacy` |

**Prior art:** the audit of Strudel/Tidal/Sonic Pi/SuperCollider/ABC — what we
absorb and what we decline — lives in `docs/PRIOR-ART.md`.

## The next level (added 2026-08-24)

The ladder of intelligence, each rung shipped on the one below:

1. **ask** — the AI proposes, you press Enter. *(shipped)*
2. **jam** — a bandmate: one move every N bars, graded ears, a mood, a six-word why. *(shipped)*
3. **produce** — a producer: the closed loop made watchable. grade → worst fault →
   fewest-commands fix → regrade; a round that makes it worse is reverted on the
   spot; two bad rounds and it stops while ahead; one `undo` takes back the pass. *(shipped)*
4. **dream** — prose in, arranged track out: the AI picks style, length and curve,
   then pushes the result toward the words. `dream driving acid at 3am`. *(shipped)*
5. **rooms** — two browsers, one track, live: musical commands relay through a
   websocket room; everyone hears their own render of the same evolving song;
   the AI's jam moves broadcast like anyone else's. *(shipped: shared state;
   shared clock is the v2.)*
6. Next up: **produce with reference** (the loop's reference-matching lands, and
   produce aims at a record you love, not just the rulebook); **rooms** (two
   browsers, one clock, jam together); **the /py/ default swap** once the real
   engine's transport is as polished as the port it replaces.

Design/UI direction, in one sentence each:
- The terminal is the identity; polish means fewer, better words and exact color
  discipline, not more chrome.
- Every capability must be reachable three ways: typed, tapped, and through the
  palette — no feature exists until all three know it.
- The stage (HUD + rack) never scrolls; the conversation always does.

## What would make it amazing

1. **The recipe, not the cake.** Every public track is its source. "Remix" is one
   command and the original author is credited automatically. No other music
   site can do this because everyone else stores audio.
2. **A duet with the machine.** `jam` — the AI plays *with* you on the beat grid,
   explains itself in one line, and you veto with one key.
3. **Sets that flow.** A playlist becomes a continuous DJ set with real key- and
   energy-aware transitions, and you can grab the crossfader mid-set.
4. **Visuals you own.** Beat-exact, section-aware, and yours — a theme is a file
   you can share, and a track can carry its own.
5. **Zero friction.** No install, no account to play, one command to a whole
   song, one to publish, one URL to share.

## Not doing (on purpose)
- Storing audio server-side. Takes are text; audio is rendered where it is played.
- Passwords / OAuth. Magic link is enough and leaks nothing.
- A second frontend host. Everything is on Railway; revisit if the bill matters.
- Storing users' AI keys. Browser-side only.
