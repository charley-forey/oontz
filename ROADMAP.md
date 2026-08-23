# thud roadmap

The backlog an evolution cycle works from. Each item is small enough to finish,
test and commit in one pass. Cycles pick the highest item that is `open`, do it,
prove it, push it, then append what they learned.

**The gate: nothing merges unless `python -m thud test` and `python -m thud.qa`
both pass.** An unattended loop that can push broken audio to main is worse than
no loop.

---

## Now

- [ ] **Per-track spectra** — `freq` view approximates band energy from a voice-name
      table. Render tracks separately once per bar and use the real numbers.
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

## Cycle log

Append one line per completed cycle: what changed, what it measured, what it learned.

- 2026-08-23 — v3 shipped: song timeline, layout solver, keymap table, compose,
  deck, mixer, two pages, copilot. 20 modules. Deck browser went 7 fps → 58 fps
  after caching the library index.
