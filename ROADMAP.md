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
- [x] **Deck mode in the browser** — `M`. `renderSong()` walks `stateAt` through an
      OfflineAudioContext using the same `_hits` the live clock uses; a deck is that
      buffer, a read position and a rate. `playbackRate` is the sync, `loopStart/End`
      is the beat loop, three biquads are the kills, two gains are the crossfader.
      `export` writes the same render as a WAV.
- [x] **Pyodide spike: GO** -- the real thud runs in Chrome at median 185ms/bar
      against a 1200ms threshold. See cycle 8 and PLAN.md; web/app/py/ is the proof.
- [x] **DNS** — live 2026-08-24. Namecheap: apex ALIAS `@` → `g1p1gota.up.railway.app`
      (oontz.sh), CNAME `api` → `130v5d2f.up.railway.app`, the two `_railway-verify` TXT
      records, and `www` redirecting to https://oontz.sh. oontz.music's apex ALIAS →
      `6nb6dlqp.up.railway.app`. Read a target with
      `railway domain status <domain> --service <name> --json` — the MCP does not return them.
- [x] **ANTHROPIC_API_KEY set** — `/health` reports `ai:true` and `/ai/ask` returns
      command lines. The first live answer said `gain hat -6`, reaching for dB against a
      0-1.2 linear multiplier, which would have silenced the track: the prompt states
      units and ranges now.
- [ ] **oontz.music 503s at Railway's edge** — since ~11:30 UTC 2026-08-24. HTTP 503,
      HTTPS handshake reset, while `landing-production-74c4.up.railway.app` serves the
      same deployment fine and oontz.sh/api.oontz.sh are unaffected. DNS resolves to the
      right target (69.46.46.89 = `6nb6dlqp`), Railway reports the domain ACTIVE with a
      VALID cert, and `domain certificate retry` refuses for that reason. Decided to wait
      rather than remove/re-add the domain, because re-adding can return a different CNAME
      target and would need the Namecheap ALIAS changed. Re-check; if it persists, that is
      the fix, or a support ticket.
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

Open findings from the 2026-08-24 audits that are written down rather than fixed:

- [ ] **Publishing the same title overwrites the earlier song** — `api/main.py`
      upserts on `(user_id, title)`, and `compose` names songs by style, so two
      `hardtechno` tracks collide and any share link already pasted starts playing
      different music. Key on the song id the client holds.
- [ ] **Magic links die to email link-scanners** — `/auth/verify` is a GET that
      deletes the row on first hit, so Outlook/Gmail prefetch burns it and the real
      click says "expired". Let a link work twice inside its 15 minutes.
- [ ] **An expired session is never cleared** — after 90 days boot still says
      "signed in" and every account command fails. Drop the token on a 401.
- [ ] **`playlist` subcommands crash on a missing argument** — `playlist public`
      with no id reads `.songs` off a listing response.
- [ ] **The landing page sends `limit` where the API takes `limit_n`** — silently
      ignored, so the public playlist list is always 40.
- [ ] **`renderSong` blocks the main thread** — ~22k voice calls and 10^5 nodes are
      built synchronously before rendering starts, so the tab freezes for seconds on
      `dload`/`export` and the progress percentage can never paint.
- [ ] **Reference matching** — analyse a WAV you own and show where yours differs.
      `ear.js` already has the FFT and the band grid.
- [ ] **`improve` should reach past levels** — it moves gain, pan and sidechain.
      Per-track filters and swapping a voice are what a person reaches for when two
      elements are simply the same sound twice.
- [ ] **Grade more than the loudest section** — a break with a pad masks differently.
- [ ] **Micro-timing on the desktop** — `theory.GROOVES` drives the browser engine;
      `core.hits()` still applies a single swing percentage.

## One theory (was: the two composers can drift)

`thud/theory.py` is the only source. `python -m thud theory export` writes
`web/app/theory.js` (the browser composer derives its tables from it) and
`api/theory.json` (the AI proxy appends its `prompt` to the system prompt). The
desktop AI reads `theory.prompt_text()` directly. The selftest fails if an export is
stale; `qa` runs 192 arrangements through both composers and requires identical plans.

- 2026-08-24 -- cycle 8: the Pyodide spike, and its number. The real thud package
  -- all 25 modules, numpy DSP, the composer, ui.build() -- imports and runs in
  Chrome via Pyodide: `compose hardtechno 3` composed 112 bars in-page, and a full
  1600ms bar renders in **min 124 / median 185 / max 212 ms** (native: ~94ms).
  The go/no-go line in PLAN.md was 1200ms, so this is a **GO** with 8x headroom:
  oontz.sh can be the actual software. Load cost: ~5s pyodide + numpy, 178KB
  thud.zip, 660ms unpack+import. What it took: sounddevice behind a guard, the
  POSIX tty/termios imports behind another (Pyodide has neither), thud/web.py as
  the JS-facing seam (do/render_bar/page/key), and JS driving the render-ahead
  loop instead of a thread. web/app/py/ is the proof page. Next cycle: wire the
  worklet transport end to end and start retiring the JS engine per PLAN.md.

- 2026-08-24 -- cycle 9: the phone pass. Every command printed on either page is
  now a tap target (one delegated click handler; tapping `grade` in help runs it),
  gallery and playlist rows tap to play, and oontz.sh grows a touch deck on coarse
  pointers only -- 40 buttons (transport, sections, 16 pads, 8 track selects, hold
  keys for filter/roll) that each dispatch the KeyboardEvent the desktop key would
  have sent, so the entire keyboard path is reused and the deck knows nothing about
  music. Phone taps no longer summon the keyboard unless they land on the input
  bar, and inputs are 16px under coarse pointers so iOS stops zooming the page on
  focus. Verified in Chrome by driving the synthetic path: space toggled the
  transport, a pad edited the live pattern, trk 2 moved focus, taps ran commands
  on both pages. Learned that the landing server caches index.html at import and
  the page caches for 60s -- two layers that can both serve you the past while
  you debug the present.

- 2026-08-24 -- cycle 10: jam, and six voices earn their circuits. `jam on 8` makes
  the AI a bandmate: every N bars it makes exactly one small move through the same
  /ai/ask path, out loud in the log, snapshot first, `undo` vetoes -- a duet with
  the machine, not autocomplete. And the six voice aliases (hoover, lead, pluck,
  fm, screech, chord) are now real WebAudio circuits: the hoover swoops, the pluck
  snaps its filter, fm rides a real modulation index. `sounds` lists the bank.
  Verified in Chrome: a stubbed jam turn fired on the bar boundary, applied
  `swing 18`, and undo reverted it; all six voices rendered without error while a
  song played. Learned that a hidden tab can be silently DISCARDED by Chrome, not
  just throttled -- state you proved one call ago may be a fresh boot now.

- 2026-08-24 -- cycle 11: the seven, greenlit and shipped in order. (1) /py/ is
  reachable (`real` on oontz.sh) and verified: a typed :compose built 112 bars and
  render_bar streamed stereo through the worker; the SPA rewrite ate /py/?query and
  was fixed. (2) breakbeat, electro and ambient join theory.py with style packs --
  264 arrangements identical cross-language, and the qa fuzzer caught 'compose -1
  inf' overflowing (minutes clamp now). (3) jam has ears: the grade rides each turn,
  `jam style <mood>` leans it, and the model answers with a six-word '# why' the
  page prints. (4) mix <playlist>: deck b renders ahead, syncs 16 bars out, an eased
  crossfade walks over, the freed deck loads the next track -- blend, handover and
  preload verified with faked positions. (5) WebMIDI by the touch.js trick: notes
  dispatch the KeyboardEvents the keys would have sent; pads 36-51 are steps, the
  sustain pedal is play. (6) A manifest, a grid-bar icon and a network-first service
  worker: oontz.sh installs and serves offline. (7) remix <id> + automatic lineage:
  the API validates credit, counts flips both directions, the landing page says so.
  Learned twice over that a shared checkout means anchors drift under your feet:
  add only the files you touched, and re-read before you patch.

## Cycle log

Append one line per completed cycle: what changed, what it measured, what it learned.

- 2026-08-24 — cycles 9-12: the ear, the track, and the interface. `grade` renders
  the loudest section once per track and measures it, so every mixing rule in
  theory.py is now checked rather than claimed; `improve` fixes the worst violation
  and re-measures until the score stops rising. Then the generator learned to write
  a track: fills in the last bar of every phrase, groove as a velocity curve plus a
  micro-timing curve per genre, automation across builds and breaks, and a master
  chain that highpasses at 60, sums the sub to mono and limits. Hardtechno grades
  82/100 out of the box (was 52) and improve takes it to 100 in three rounds.
  Learned that a measurement is a design decision: reading masking off each track's
  own normalised spectrum meant turning a track down could never clear a conflict,
  and measuring one 8192-sample window meant every offbeat track read as silence.
  Both were found by reading what the tool said and not believing it.
- 2026-08-24 — cycle 7: one theory. TEMPLATES/ROLE_BARS moved into theory.py; the
  Python arranger is now the JS solve line for line (decide the pre-drop bars up
  front, share the rest); the 14%-drop fault the grader caught in cycle 3 is gone on
  the desktop too. theory.py exports theory.js + theory.json; compose.js derives its
  GENRES from theory.js instead of carrying truncated rewrites; both `ask`s get the
  same 4.4KB corpus. Checks: 48 genre×curve plans drop inside their window in both
  languages, 192 plans identical across Python and node, export staleness fails the
  selftest. Learned that Math.round and Python round() disagree on halves - a
  cross-language equality check finds the kind of drift a per-language test never will.
- 2026-08-24 — cycle 6: DECK mode in the browser. 725 lines of engine now. The port
  was honest about one thing deck.py never had to think about: an
  AudioBufferSourceNode has no playhead, so position is anchor arithmetic and every
  rate change re-anchors first or the maths drifts. Sync evaluates both decks at one
  shared future instant and starts the new source there, so the two sources begin in
  lock rather than a scheduling delay apart. 14 more asserts: grid exact, sync holds
  phase to 1e-6, loop wraps, crossfader equal power. Learned that the offline render
  is the cheap part - the same 40-line `_hits` serves the live clock, the decks and
  `export`, which is what keeping the step body pure bought.
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
