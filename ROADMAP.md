# thud roadmap

The backlog an evolution cycle works from. Each item is small enough to finish,
test and commit in one pass. Cycles pick the highest item that is `open`, do it,
prove it, push it, then append what they learned.

**The gate: nothing merges unless `python -m thud test` and `python -m thud.qa`
both pass.** An unattended loop that can push broken audio to main is worse than
no loop.

---

## Now

- [x] **Per-track spectra** — done. `core.band_energy` measures each track's real band
      energy from its own bar buffer and puts it on the Snapshot as `TrackView.bands`.
- [x] **Automation recording** — done. `autorec` arms, move a control, `autorec` writes
      the gesture into the section as a ramp, fitting the curve (linear/exp/log/ease)
      to the shape you made, not just the endpoints.
- [ ] **Transition scheduler** — `mixer.plan_transition` returns bar-stamped steps but
      `transition` applies them all at once. Drive them from the deck's beat grid.
- [ ] **Deck performance FX** — `dj.py` effects are wired for STUDIO only. Route them
      through a deck's read pointer so a roll works while mixing.
- [ ] **Stem export** — `stems take_003/` writing one WAV per track. render_bar
      already computes per-track buffers; keep them instead of summing.
- [ ] **MIDI export** — patterns to a .mid file so a track can leave for a DAW.

## Next

- [ ] **Reference matching** — analyse a WAV you like, show where your spectrum differs.
- [ ] **Freeze a track** to audio so an expensive voice stops re-rendering.
- [ ] **Vectorise `svf`** — the per-sample loop is 99ms per pass on a full bar. It is
      the single biggest cost in a cold render.
- [ ] **More voices** — 909 snare variants, dub chords, granular pads, vocal-ish formants.
- [ ] **Groove templates from real records** — swing/velocity curves, not just a swing %.
- [ ] **Live-code mode** — type a pattern and hear it on the next bar without Enter.
- [ ] **Undo across song edits** — undo covers tracks; extend it to section edits.
- [ ] **Cue-point hot keys in DECK** — 8 hot cues exist in `deck.py`, unbound.

## Later

- [ ] **A second output device** for cue/PFL, so you can pre-listen like real gear.
- [ ] **Video export** — render the page to frames alongside the audio.
- [ ] **Move the frontends to Vercel** — decided 2026-08-23 to stay on Railway because
      it was already live; revisit if the Railway bill for two static sites matters.
- [ ] **Collaborative sets** — two thud instances sharing a clock.
- [ ] **Rust port of the voice bank** for a much faster cold render.

---

## Known limits, stated plainly

- Nobody has listened to this on speakers. Every check is spectral or structural.
- The interactive TUI has never run in a real terminal in this session; `build()`
  is verified but the alt-screen loop and key-repeat timing are not.
- `HOLD_MS = 450` in `ui.py` is tuned to a guess about OS key-repeat delay.
- `arrange.py`'s `song` and `variation` verbs are shadowed by core's and unreachable.
- v2 `.thud` files have no duration, so `library.autobuild` under-fills with them.

## Web

The web gate is `node web/app/check.js`, and a web cycle is not done until Railway
reports SUCCESS and the live file contains the change.

- [x] **oontz.music live** — landing terminal, makes techno in the page, on Railway.
- [x] **API live** — auth, song storage, gallery, AI proxy. Verified end to end.
- [x] **oontz.sh shipped** — WebAudio voice bank, the song model and the composer all
      ported. `go` makes a whole arranged song in the browser.
- [x] **Keyboard-as-controller in the browser** — Esc leaves the prompt; pads, focus,
      mute/solo, master filter sweep, loop roll (a step-index freeze), spinback and
      tape stop (a DelayNode read at a rate curve), section jumps. `?` prints the table.
- [x] **Record in the browser** — `R` / `rec` captures the master via MediaRecorder;
      `rec screen` muxes a screen capture with it. Exactly what you heard.
- [x] **`ask` in the browser** — proposes command lines, empty Enter runs them, `undo`
      takes them back. Needs `ANTHROPIC_API_KEY` on the api service to answer.
- [ ] **Deck mode in the browser** — `OZ.render(song)` via OfflineAudioContext, two
      AudioBufferSourceNodes, playbackRate sync, 3-band EQ, crossfader. `export` (WAV)
      falls out of the same render. The `decks` copy is still a promise until this lands.
- [ ] **DNS** — the three custom domains are attached on Railway; the records are not
      set yet. Until they are, only the `*.up.railway.app` URLs work and `oontz.sh` has
      no reachable URL at all (Railway will not add a service domain beside a custom one).
- [x] **Gallery on oontz.music** — reads the live `/gallery`.
- [ ] **Play a gallery track in the landing page** — oontz.js can already interpret a
      .song; wire the browser engine to a fetched track.
- [x] **RESEND_API_KEY wired** — email sends. Two bugs on the way: the failure was
      swallowed (looked like "no key"), and the real cause was Cloudflare 1010
      blocking urllib's default User-Agent.
- [x] **Persistent volume** — 1GB at /data. Before it, every redeploy wiped all
      accounts and songs.
- [ ] **ANTHROPIC_API_KEY** — still needed. The key pasted for it was a duplicate of
      the Resend key (`re_…`); Anthropic keys start with `sk-ant-`.
- [ ] **Verify a sending domain in Resend** so mail comes from oontz.sh rather than
      onboarding@resend.dev, which only delivers to the account owner.

## Copy

- [x] **oontz.music voice** — dry, self-aware, story-shaped. In `copy.js`, apart from
      the machinery, because copy changes far more often than code.
- [x] **oontz.sh voice** — written, with the rules it follows stated in the file so it
      stays consistent: a joke must carry information, punch at the software and never
      the user, deadpan beats zany.

## Next, web-first (the order the loop should take them)

1. Deck mode in the browser (above).
2. **One theory, three consumers** — `theory.py` exports `web/app/theory.json`;
   `compose.py` and `compose.js` drop their private tables and read it; the AI prompt
   gets `theory.brief()`; a check that both composers make the same shape for one seed.
3. Make `copy.js` honest: any claim a cycle did not deliver gets cut, not softened.
4. **Reference matching from music you own** — analyse a WAV (band energy, onset
   BPM, chroma key) and compare to theory. The Rekordbox library on this machine is
   the legal corpus; not the internet.

## Known risk: the two composers can drift

`thud/compose.py` and `web/app/compose.js` implement the same arrangement logic
independently. The JS one now solves the drop window directly; the Python one still
nudges and carries the same 14%-drop-in-techno fault the grader caught. Port the fix
back, then add a check that both produce the same shape for the same seed.

## Cycle log

Append one line per completed cycle: what changed, what it measured, what it learned.

- 2026-08-23 — cycle 5: the browser does what its copy says, minus decks. setTrack
  write-through (stateAt() was wiping every live edit at the next bar - the `kick
  x...` command had this bug from day one), a lookahead clock, a master filter and a
  DelayNode for spinback/tape stop, 16 keys, MediaRecorder capture, `ask` + `undo`,
  section-aware visuals, localStorage restore. 311 lines of inline script, 37 asserts
  in check.js. Learned that a DelayNode is a ring buffer with a read head, so dj.py's
  pointer math ports to the browser as a delay-time curve: d(t) = t - ∫r.
- 2026-08-23 — cycle 4: automation recording, plus what the gate turned up on the way.
  The fuzzer had been writing `save nan` and `render 999999` into the repo root (and
  `save ../etc/passwd` outside it) - 16 files were tracked. Fixed at the command layer
  with one `outpath()` guard; QA points it at a scratch dir. The fuzzer also spent ten
  minutes per run inside the `claude` CLI because `ask <junk>` is a real model call -
  `THUD_OFFLINE=1` now makes `ai.available()` say no. And `do()` only guarded command
  typos, not track verbs or missing files: 58 escaped exceptions in 600 fuzzed lines.
  One outer guard, 0 escaped. Learned that a gate that has never finished is not a gate.

- 2026-08-23 — cycle 3: the browser composer. The grader immediately convicted the
  generator - theory says techno drops at 20-40%, the generator dropped at 14% and
  scored itself 68/100. Two fixes failed first: nudging fought itself (grow the intro,
  the length goes out; trim the length, the drop leaves the window), and proportional
  scaling broke phrase alignment on rounding. Solving it directly works - decide the
  pre-drop bar count up front, because that IS what the window specifies. 144 songs
  across 8 styles x 6 curves x 3 durations, 0 failures, mean score 82.6. Learned that
  the grader is worth more than the generator: it found a real fault I would have
  shipped without noticing.
- 2026-08-23 — cycle 2: theory.py. Eight genres, per-element frequency roles, and
  arrangement/mixing/DJ rules as checkable claims with reasons. A composed track
  grades 92/100; the same track broken into two drops with a 12-bar section grades
  0/100 and says why. The point is that generation can now be graded rather than
  trusted. Learned that the QA gate is worth its runtime: it caught a genuine
  out-of-bounds crash in dj.scratch that 10,000 earlier calls had missed.
- 2026-08-23 — cycle 1: per-track band energy is measured from each track's own bar
  buffer rather than guessed from a voice-name table. Measured on `industrial`: kick
  96% in sub+bass, hat 85% in presence+air. Learned that the guess was wrong the
  moment a track was repointed at a different voice, which the FREQ view could never
  have shown.
- 2026-08-23 — v3 shipped: song timeline, layout solver, keymap table, compose,
  deck, mixer, two pages, copilot. 20 modules. Deck browser went 7 fps → 58 fps
  after caching the library index.
