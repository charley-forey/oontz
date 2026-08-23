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
- [ ] **Automation recording** — sweep a filter by hand while playing and have the
      gesture captured as a `ramp` you can replay. The engine already stores
      automation; this is the capture path.
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

- [x] **oontz.music live** — landing terminal, makes techno in the page, on Railway.
- [x] **API live** — auth, song storage, gallery, AI proxy. Verified end to end.
- [x] **oontz.sh shipped** — WebAudio voice bank, the song model and the composer all
      ported. `go` makes a whole arranged song in the browser.
- [ ] **Deck mode in the browser** — the DJ half is desktop-only so far.
- [ ] **Keyboard-as-controller in the browser** — step pads, held-key filter sweeps,
      loop rolls. The web app is command-driven only right now.
- [x] **Gallery on oontz.music** — reads the live `/gallery`.
- [ ] **Play a gallery track in the landing page** — oontz.js can already interpret a
      .song; wire the browser engine to a fetched track.
- [ ] **Move the landing page to Vercel** when the free-tier deploy cap resets.
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

## Known risk: the two composers can drift

`thud/compose.py` and `web/app/compose.js` implement the same arrangement logic
independently. The JS one now solves the drop window directly; the Python one still
nudges and carries the same 14%-drop-in-techno fault the grader caught. Port the fix
back, then add a check that both produce the same shape for the same seed.

## Cycle log

Append one line per completed cycle: what changed, what it measured, what it learned.

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
