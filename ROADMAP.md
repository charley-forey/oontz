# oontz roadmap

The backlog an evolution cycle works from. Each item is small enough to finish,
test and commit in one pass. Cycles pick the highest item that is `open`, do it,
prove it, push it, then append what they learned.

**The gate: nothing merges unless `python -m oontz test` and `python -m oontz.qa`
both pass.** An unattended loop that can push broken audio to main is worse than
no loop.

---

## ⏸ PAUSED — 2026-08-26

**The evolution loop is paused. Do not start a cycle.** If you are the `evolve`
skill, stop here and say so.

Why: the funnel says 36 sessions landed, 7 typed a command, 0 saved, 0 signed in,
0 published. Every open item below is a feature. None of them is why nobody is
using oontz. The work is launch work — blockers, a seeded gallery, distribution —
and it is tracked outside this file until it ships.

Delete this section to resume.

### Launch punchlist (2026-08-26)

- [x] **Song identity is the id, not the title** — everyone's first track is called
      `untitled` and so is their second; a same-title save used to replace the earlier
      song under links already handed out. `POST /songs` takes an optional `id` now.
- [x] **A sign-in link survives a mail scanner** — `GET /auth/verify` shows a form,
      `POST` spends the token. A scanner that prefetched the GET was signing in *and*
      being handed the session in the redirect; the human got "that link has expired".
- [x] **The funnel has an `explore` stage and percentages** — sessions that typed a
      SECOND command. One command is curiosity, two is the product working.
- [x] **The gallery is 30 tracks, best-of-five** — `scripts/seed_gallery.py` composes
      every brief at five seeds and publishes only what the grader likes best.
- [ ] **Verify the oontz.sh sending domain** — DNS is DONE: all three records are in
      at Namecheap and resolve byte-identically to what Resend expects. MX and SPF read
      `verified`; **DKIM is the last one** and SES allows itself 72h for it. Read status
      with `python scripts/mailcheck.py` and NOT `--verify`, which restarts the check and
      resets verified records to pending. Until DKIM lands, mail only reaches the account
      owner, so no stranger can finish a sign-up.
- [x] **Open oontz.sh on a phone** — done, and it found a real bug. Both canvas
      loops repainted at 60fps whether or not anything was playing; idle now drifts at
      ~13fps and the user confirms the phone is responsive again. `scripts/perfprobe.py`
      is how it was found. index.html's 127KB inline script also moved to app.js so
      every script defers and the terminal shell paints before the JS runs.
- [x] **A `feedback <text>` command** — done. Fires `ev('feedback')` through the
      existing `POST /e`, and `/admin/summary` carries a `feedback` list so reading it
      needs no SQL. Typing anything already landed in `prompt_submit`; what this adds
      is a findable name and an answer back, which is the half that makes someone
      bother saying anything.

### The first ten seconds (2026-08-27)

- [x] **A first-time visitor arrives holding a track** — was: a blinking prompt, five
      verbs to read, and no song loaded at all, which is why `go` and `what` were the
      most-typed things. Now `starterSong()` (the README's warehouse, hardcoded so it
      costs nothing on the boot path) loads on arrival, every pattern is in the rack,
      `armPlay` makes hearing it one tap, and the ask is one character back on a line
      already on screen. The grader is suppressed for that one load: it marks
      ARRANGEMENTS and scores a 16-bar loop 12/100, which is a bad five seconds and
      not even the question.
- [x] **A sentence gets an answer instead of `how: no`** — anything ending in `?`, or
      three-plus prose words, routes to `CMDS.ask`; greetings get a greeting. The AI
      ladder existed and was invisible unless you already knew the word `ask`.
- [ ] **Behavioural first-run test in `test.html`** — the gate asserts on source plus a
      truth table for `looksLikeProse`; the flow itself was verified by driving a real
      headless page. Belongs in browsergate proper once test.html is free.

### Resolved: the fader red (2026-08-26 → 27)

- [x] **browsergate: "a fader moves a real AudioParam"** — CONFIRMED 2026-08-27, and
      it was never a mixer bug. `--mute-audio` never renders a quantum, so
      `AudioParam.value` is frozen at its construction value while `currentTime`
      advances normally — a correctly wired fader is simply unobservable through
      `.value` in the gate. Verified by hand in Chrome with a live audio thread by the
      mobile-deck session: level 0.25 → `fader.gain` 0.25, low kill → `lo.gain` −40 dB,
      crossfader hard right → deck A gain 0. The test now spies `setTargetAtTime` and
      asserts WHICH param each control writes and what it asks for, which needs no
      audio thread at all. **Do not re-add `gain.value` reads.** browsergate is 68/68.

      Worth keeping as a hit rather than a scar: the instinct that solved this was
      "suspect the harness before the code" — the same instinct that stopped a phone
      perf fix being built on `--disable-gpu` software rasterisation the same day.

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

## Later — the source-code-for-music layers (see PLAN.md thesis, docs/OONTZ-FORMAT.md)

- [ ] **Mini-notation subdivision** — `[xx..]` inside a step (32nds); the next
      pattern-language rung after `*N` and `?` proved the path. Both engines + spec.
- [ ] **OSC output** — the third output after WAV and MIDI; events to external
      systems. Only when someone asks.
- [ ] **@oontz/* package split** — carve core/parser/outputs into packages the day
      the FIRST external consumer appears, not before.
- [ ] **Structural search** — the gallery filters on bpm/key because the fields are
      real; extend the API to match patterns and section shapes ("every public track
      using this exact kick pattern", "drop structure like this one").
- [ ] **Module registry ("npm for sounds")** — publish reusable musical behavior, not
      sample packs: a generative bassline with parameters, a genre template, a viz
      theme. The format is small enough that a module is a JSON document.
- [ ] **PR-style collaboration** — propose a change to someone's public track as a
      structural diff they can hear, review line by line, and merge with credit.
- [ ] **Adaptive runtime** — music as logic: expose the engine so a game/app can bind
      energy, tempo and sections to its own state. A 15 KB file defining hours of music.
- [ ] **Provenance graph UI** — the remix family tree, walkable: who forked what,
      which bassline is the most forked in techno.
- [x] **Edit-history corpus** — takes, jam/produce accept-vs-undo already generate
      (state, instruction, exact transformation, verdict) tuples. The privacy call was
      made on 2026-08-25 and it went the other way: collection is **opt-out**, on by
      default, with the raw IP kept. It is written down (`privacy`, section 4), DNT is
      honoured, and `notrack` switches it off. The `events` table holds the tuples.

## Later

- [ ] **A second output device** for cue/PFL, so you can pre-listen like real gear.
- [ ] **Video export** — render the page to frames alongside the audio.
- [ ] **Move the frontends to Vercel** — decided 2026-08-23 to stay on Railway because
      it was already live; revisit if the Railway bill for two static sites matters.
- [ ] **Collaborative sets** — two oontz instances sharing a clock.
- [ ] **Rust port of the voice bank** for a much faster cold render.

---

## Known limits, stated plainly

- Nobody has listened to this on speakers. Every check is spectral or structural.
- The interactive TUI has never run in a real terminal in this session; `build()`
  is verified but the alt-screen loop and key-repeat timing are not.
- `HOLD_MS = 450` in `ui.py` is tuned to a guess about OS key-repeat delay.
- `arrange.py`'s `song` and `variation` verbs are shadowed by core's and unreachable.
- v2 `.oontz` files have no duration, so `library.autobuild` under-fills with them.

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
- [x] **Pyodide spike: GO** -- the real oontz runs in Chrome at median 185ms/bar
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
- [ ] **oontz.music 503s at Railway's edge — churn did not fix it (2026-08-24 ~15:20 UTC).**
      Removed and re-added the domain: re-verified in seconds (the TXT token is
      unchanged, so Namecheap needed nothing), new CNAME target `5j4213fn.up.railway.app`
      (69.46.46.58; old `6nb6dlqp` was 69.46.46.89). Symptom identical after: port 80
      answers 503 FROM THE EDGE, 443 resets during handshake, pinned to either edge IP,
      while the railway.app hostname serves 200 and control plane says VALID cert. This
      is Railway's edge, not DNS. Two ways out: (a) a Railway support ticket, or (b) move
      oontz.music's nameservers to Cloudflare and proxy a CNAME at the apex (SSL mode
      Full, not Strict) so Cloudflare terminates TLS and Railway's edge cert stops
      mattering. Either way, update the Namecheap ALIAS to `5j4213fn.up.railway.app` —
      the old target hostname may stop resolving eventually.
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

Done 2026-08-24/25 (cycles on the `enhance` branch): every genre has its own
Euclidean kit and groove, the seeded rng no longer correlates with its seed, the
break walks a chord progression, `sec` edits the arrangement, `undo` covers your
edits, a local library, `export stems`, and `eargate.js` guards all of it.

- [ ] **The nine missing voice circuits** — `downlifter` is aliased to `riser`, so a
      fall renders as a rise, which is simply wrong. `tom`, `metal`, `rim`, `ride`,
      `crash` all collapse onto `perc`, a 90ms bandpassed click, so four different
      names are the same sound. `drums.py` has each in about nine lines.
- [ ] **Publishing the same title overwrites the earlier song** — the API upserts on
      `(user_id, title)`. `name` now exists so a user *can* avoid it, but the API
      should key on the song id the client holds.
- [ ] **Magic links die to email link-scanners** — `/auth/verify` is a GET that
      deletes the row on first hit, so a prefetch burns it. Let it work twice inside
      its 15 minutes.
- [ ] **An expired session is never cleared** — boot still says "signed in" after 90
      days. Drop the token on a 401.
- [ ] **`playlist` subcommands crash on a missing argument** (`account.js:96/103`).
- [ ] **`renderSong` blocks the main thread** — ~22k voice calls built synchronously,
      so the tab freezes on `dload`/`export` and the progress percentage never paints.
- [ ] **Reference matching** — analyse a WAV you own and show where yours differs.
      `ear.js` already has the FFT and the band grid; the Rekordbox library on this
      machine is the corpus.
- [ ] **Grade more than the loudest section** — a break with a pad masks differently.
- [ ] **Micro-timing on the desktop** — `theory.GROOVES` drives the browser engine;
      `core.hits()` still applies a single swing percentage. This also blocks any
      Pyodide migration from being a pure win.

### Known: newly-registered-domain filtering

`oontz.sh` and `oontz.music` are blocked by some corporate and guest networks under
the "newly-registered-domain" category — a full day was spent chasing this as a
Railway edge fault before reading the 503's body, which said so plainly. The
category typically ages out in 30-90 days. Check from outside such a network
(`https://r.jina.ai/https://oontz.sh/` works) before concluding anything is broken.

## One theory (was: the two composers can drift)

`oontz/theory.py` is the only source. `python -m oontz theory export` writes
`web/app/theory.js` (the browser composer derives its tables from it) and
`api/theory.json` (the AI proxy appends its `prompt` to the system prompt). The
desktop AI reads `theory.prompt_text()` directly. The selftest fails if an export is
stale; `qa` runs 192 arrangements through both composers and requires identical plans.

- 2026-08-24 -- cycle 8: the Pyodide spike, and its number. The real oontz package
  -- all 25 modules, numpy DSP, the composer, ui.build() -- imports and runs in
  Chrome via Pyodide: `compose hardtechno 3` composed 112 bars in-page, and a full
  1600ms bar renders in **min 124 / median 185 / max 212 ms** (native: ~94ms).
  The go/no-go line in PLAN.md was 1200ms, so this is a **GO** with 8x headroom:
  oontz.sh can be the actual software. Load cost: ~5s pyodide + numpy, 178KB
  oontz.zip, 660ms unpack+import. What it took: sounddevice behind a guard, the
  POSIX tty/termios imports behind another (Pyodide has neither), oontz/web.py as
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

- 2026-08-24 -- cycle 12: sounds and sights, both sites. Four voices join BOTH
  engines in the same commit -- bell (inharmonic FM, 3.53), donk (an octave-up
  sine falling home through a resonant band), wob (a reese with an LFO on its
  filter) and air (noise breathing through a narrow band) -- python renders
  sanity-checked (air clipped at 1.72 until tanh), browser twins instantiated
  live. The canvas learns `viz auto`: the section picks the mode (builds run,
  drops blow out, breaks drift) and a new `terrain` mode draws a wireframe
  landscape the bass builds. Landscape phones get a 16-wide deck row and a
  shorter rack. And oontz.music catches up to the .sh look: the SAME viz.js
  (engine-copy gate now guards both files) starts in auto the moment a gallery
  track plays, plus a manifest and icon so the gallery installs. Verified live
  on both pages; landing engine playing with viz auto attached.

- 2026-08-24 -- cycle 13: the stage becomes one thing, the deck folds, and four
  more genres. The rack moved up under the HUD - song map and instrument rows are
  one stationary stage, the conversation scrolls beneath it, and the touch deck
  folds to a one-line "pads" handle (remembered per device) so the log gets the
  room back. Style packs can now point a track at any circuit ("voice" in the
  spec), and garage (two-step shuffle), psytrance (the rolling bass IS the track),
  jungle (two tempos, both grooving) and downtempo (bell stabs, air hats, sub
  bass at 95) join theory + gen - 15 genres, 360 arrangements identical across
  both composers, 90 plans in their windows. Caught on the way: gen has its own
  scale aliases (pentatonic, not pentatonic_min) and a pack that names an unknown
  scale silently falls back to defaults - the tempo told on it.

- 2026-08-24 -- the edge outage spread (~16:20 UTC): ALL THREE custom domains
  (oontz.sh, api.oontz.sh, oontz.music) now TLS-reset at Railway's edge while both
  railway.app hostnames serve 200. status.railway.com says fully operational, so
  this needs a support ticket (or Cloudflare in front of all three). Mitigations
  shipped: the app service now has a permanent fallback URL
  **app-production-ca85.up.railway.app** (created by briefly removing and re-adding
  the oontz.sh domain - new CNAME target `l08sxgk0.up.railway.app`, verify TXT
  unchanged), and both pages probe the API at boot and fall back to
  api-production-bd3d8.up.railway.app within 4s if the custom domain is dead.
  Namecheap updates when convenient: ALIAS @ oontz.music -> 5j4213fn, ALIAS @
  oontz.sh -> l08sxgk0 (both TXT records stay as they are).

- 2026-08-24 -- cycle 14: the cinema and the theme workshop. `watch` fades every
  scrap of chrome away - full screen, cursor hidden, nothing but the canvas; the
  keys still play the instrument and Esc or a tap brings the terminal back (on
  the landing page too). Themes stop being a fixed menu: `theme make <name>
  <#hex...>` builds one (2-6 colors, junk hex refused, built-ins protected),
  `theme random` rolls hue-spaced palettes until one sticks, `theme del` cleans
  up, and a custom look is EMBEDDED in song.viz so a published track carries its
  own palette to viewers who never made it. Nine new built-ins (ultraviolet,
  lava, oilslick, vapor, matrix, blacklight, neonnoir, aurora...) and two new
  modes: `stars` (rushing exactly as fast as the music says) and `kaleido` (a
  breathing mandala the symmetry folds). Verified visually - and learned that
  getComputedStyle lies under the dark-mode extension: when CSS seems impossible,
  screenshot the truth.

- 2026-08-24 -- cycle 15: the thesis, named and shipped. Oontz is source code for
  music - the essay's claims audited honestly (most were already true here), the
  format specified in docs/OONTZ-FORMAT.md (.oontz command log + oontz-song-1 JSON,
  determinism guaranteed by the gates), PLAN.md carries the three layers (format ->
  ecosystem -> intelligence) with a real-vs-future table, and the Later backlog
  gains structural search, the module registry, PR-style collab, the adaptive
  runtime, the provenance graph and the (opt-in-first) edit corpus. In the
  instrument: `source` / `source save` (a .oontz download) / `source copy`,
  `load <paste>` round-trips a song, and `diff` says what changed in human lines -
  bpm, bars, patterns - against the last snapshot, a take, or any gallery track.
  publish stamps format: oontz-song-1. oontz.music gains `spec`: the story in
  sixty seconds, hello world included. Verified end to end in the browser: source
  -> compose something else -> load restored the exact song, and diff named the
  bpm and kick changes.

- 2026-08-24 -- cycle 16: structural search, the ecosystem layer's first rung.
  Because songs are source, the API can read the music instead of the metadata:
  `GET /search` matches an exact pattern (optionally per track) plus BPM window
  and key; `GET /similar/{id}` scores structural likeness (bpm distance, key,
  role-sequence shape, shared patterns) and says WHY - "within 1 BPM, same key,
  same shape, shares 2 patterns"; `GET /songs/{id}/remixes` walks the family
  tree both directions. oontz.music grew `gallery pat x...x...x...x...`,
  `gallery like <id>` and `tree <id>`, every result a tap-to-play row. Full
  scan per query, ponytail-marked, an index when the gallery outgrows it.
  Verified against a seeded api: the accented kick variant was correctly NOT
  a match for the plain pattern - the search reads accents because the music
  does. Also checked the ticked search box off the thesis table in PLAN.md.

- 2026-08-24 -- cycle 17: filled the world, charted it, made shares cinematic.
  scripts/seed_gallery.py published a house corpus - 15 genres, 3 remixes, 3
  playlists - so the live gallery finally demonstrates search/similar/tree/mix
  instead of being empty. Charts arrived (only the source graph can): /charts
  (most forked, most-shared patterns, tempo spread, busiest keys) with a `charts`
  command on oontz.music, and POST /similar powering a `similar` command on
  oontz.sh (what public tracks does mine resemble). And /t/<id> shares got
  cinematic: server-generated OG cards drawn FROM the song (title, numbers, the
  real kick/hat as a 16-step strip) via /og/<id>.svg, and ?watch=1 opens the link
  as a light show after one tap. The landing server learned an API fallback so
  server-rendered cards survive the custom-domain edge outage. Verified: OG card
  shows warehouse litany's real drums, watch flow enters fullscreen on tap.

- 2026-08-24 -- cycle 18: the database stops evaporating. Root cause of the
  vanishing gallery: OONTZ_DB=/data/oontz.db but NO volume was mounted there, so
  every redeploy wiped all songs, accounts and playlists. Created a 5GB volume at
  /data on the api service; re-seeded the corpus (18 tracks, 3 remixes, 3
  playlists) and PROVED it survives a redeploy - the gallery read 18 tracks after
  the very push that used to empty it. Charts skip the all-rest pattern (not a
  pattern anyone means), duplicate playlists from the double seed were cleaned,
  and the seed script gained a --token path for when Resend's delivery to the
  house address is too flaky for self-auth.

- 2026-08-24 -- cycle 19: rooms. A room is a chatroom whose messages happen to be
  music: because every musical action is a command string through one run(), live
  collaboration is relaying strings - POST /rooms mints a code, WS /ws/room/{code}
  forwards JSON between members and never interprets it (in-memory, dies on
  redeploy, ponytail-marked). `room new` / `room <code>` / who / leave; local
  musical commands broadcast (the musical() filter), incoming ones run echoed as
  ◂ handle, joiners inherit the room's track, presence sits in the HUD, and the
  AI's jam turns broadcast like anyone else's because they go through run() too.
  Verified with two real Chrome tabs: alice's kick landed in bob's session, bob's
  hat came back into alice's rack, HUD read room · 2 on both sides. Found the
  hard way: a .song is 15-40KB and the relay's 16KB cap CLOSED the sender - the
  retry then double-counted presence. 128KB cap, oversize dropped not executed.

- 2026-08-24 -- cycle 20: oontz.music wears the same glass. The landing adopts the
  instrument's design language - unified tokens, the --plate panels with blur on a
  new live status strip and the prompt bar - and becomes a guided journey: the menu
  is grouped LISTEN / UNDERSTAND / MAKE (every row a tap target), `tour` walks demo
  -> the one-character moment -> the spec story -> the live gallery -> charts ->
  the invite (Enter advances, anything else wanders off politely), first visitors
  get one nudge, and the strip fills with live numbers (track count, most-shared
  pattern, most-forked track) once the API answers. Also: local dev ports joined
  the CORS regex - the strip's 'Failed to fetch' on localhost was CORS, not code,
  and the production fallback origins were already allowed by the loop's earlier
  fix. Reminder recorded again: oontz.music THE DOMAIN cannot render any version
  until Railway's edge is fixed; the railway.app URL is the truth.

- 2026-08-24 -- cycle 21: the film lifts and the bar earns trust. The landing's CRT
  overlays sat ABOVE the text (z2 over z1) - the app fixed that stack long ago and
  the landing never got it - so every character rendered through a 0.75 vignette;
  text now sits at z4 like the app's. The status strip stops racing the API probe
  (it awaits it), its fetches get 4s timeouts, segments look pressable (underline +
  hover), and a skeleton keeps the bar honest while loading. Biggest catch: every
  link to https://oontz.sh - including the strip's flagship 'open the real one' -
  pointed at the edge-dead domain; an APP fallback probe now heals those links at
  click time to the address that works, and heals back automatically once Railway
  fixes their edge. Tokens finished matching the app exactly; returning visitors
  (and reduced-motion) skip the typewriter and boot instantly.

- 2026-08-24 -- cycle 22: the strip fits, the accent breathes, the eggs hatch.
  #hud stops amputating on phones: horizontally swipeable (hidden scrollbar, a
  fade-right mask that hints at more), low-priority segments hide under 560px,
  and it fades in as it populates. The accent becomes a living thing - viz.js
  drifts --accent ±24° around teal on a 45s sine, BOTH sites breathe because
  both load the file, playback energy quickens the breath, reduced-motion stills
  it. While a track plays, the strip grows a ♪ now-playing chip that is also the
  stop button. And the terminal grew eggs in the house voice: `oontz` chants
  itself over a kick-only loop, `sudo` meets the groove authorities, the Konami
  code finds the rave (blacklight + kaleido + a ten-second hot-pink flare), and
  five clicks on the logo spinback, obviously. Everything verified in-browser;
  focus-visible outlines joined for keyboard users.

- 2026-08-24 -- cycle 23: prior art absorbed, on the record. docs/PRIOR-ART.md
  audits Strudel, Tidal, Sonic Pi, SuperCollider and ABC - what oontz takes, what
  it declines, and (kept honest) what it already had: the .song doc IS the AST/IR,
  two gate-held runtimes ARE the language/engine split, oontz-song-1 IS the
  versioned spec. Two decisions implemented, both engines, both gated: the pattern
  language grows `?` (a maybe-step: 70% per bar, decided by the SAME hash in
  Python and JS, so determinism holds - scrub==render and the goldens passed
  untouched) and `x... *4` repeat sugar (entry-time, capped 64); and `export midi`
  ships the first non-audio output - a standard .mid with drums on channel 10,
  pitched tracks on their own channels, byte-asserted in the gate. The offline
  render's identical-state cache learned that ?-bars are never identical.

- 2026-08-24 -- cycle 24: two paper cuts and a sweep. The rack misaligned because
  track names were padded with SPACES inside normal-whitespace HTML - browsers
  collapse the runs, so every row shifted by its name length; the fix is a real
  CSS column (.trk inline-block, 9ch, ellipsis) and the padEnd is gone. Verified
  by measurement: kick, hat, bass and a ten-character downlifter all start their
  cells at the same pixel. And on oontz.music the visuals now follow the
  transport: stopTrack turns the canvas off (and exits watch if stranded),
  playTrack re-arms auto, and `watch` with nothing playing says so instead of
  showing a still frame. Verified: stop leaves the center pixels black, replay
  brings the show back. Sweep note: pre-volume track ids died with the old
  database - the seeded corpus ids are the live ones.

- 2026-08-24 -- cycle 25: watch stops fighting the keyboard. Typing `watch`
  leaves the input focused, so the virtual keyboard was still up when fullscreen
  engaged - the canvas measured a keyboard-shrunk viewport and everything landed
  off-center when it collapsed. watch() now blurs the active element FIRST,
  scrolls home, and re-measures the canvas in staggered kicks (250/700/1400ms)
  because fullscreen and the keyboard settle at different times on different
  phones; fullscreenchange and visualViewport resizes also re-measure, so the
  canvas can never stay stale. Verified by sabotage: with the input focused and
  the canvas forced to 300x200, watch blurred the input and restored the canvas
  to the exact full viewport.

- 2026-08-24 -- cycle 26: arrival shows the title, and the prompt earns its keys
  on both sites. Boot auto-scroll was tucking the banner under the stationary
  plates whenever the log was shorter than the boot text (always, on phones) -
  both pages now scroll home when boot finishes, and normal bottom-following
  resumes on the first command. The landing prompt reaches parity with the
  instrument's: the autosuggest dropdown (same combobox rules), up-arrow history
  (50 entries, draft preserved), and smart paste - a /t/ share link pasted into
  the prompt becomes `play <id>`; on the instrument, pasted .oontz JSON becomes
  `load <source>` with the hint saying why. Coarse pointers get a ▶ run chip in
  the bar on both pages (enterkeyhint=go for mobile keyboards too). Verified:
  scrollTop 0 with the banner fully below the strip, `ga` -> gallery dropdown
  fill, history recall, both paste rewrites.

## Cycle log

### Cycle 27 — the interaction round (2026-08-24)
Drag-to-paint the rack (pointer sweep, first cell sets the brush; click still
toggles), dropdown argument hints (`viz k` → kaleido; theme/gallery/room…),
screen wake lock while playing or watching, did-you-mean typo forgiveness
(edit distance 1, 2 for long verbs) on both prompts, `tilt` — lean the phone
to sweep the filter, shake for a spinback (behind a permission tap; needs a
real-device pass). Eggs: `boots and cats` (the beat is the pronunciation),
`dance`, `bpm 420`, `credits`. Verified by synthetic pointer painting +
prompt drives in Chrome; gates grew paint/tilt asserts.

Append one line per completed cycle: what changed, what it measured, what it learned.

- 2026-08-25 — interaction telemetry. One `events` table, one `POST /e` batch ingest
  (50 events a batch, 2KB a prop, always 200), 183 lines of `track.js` on both sites
  behind the `ev()` hook that already existed, ~14 chokepoint events, and
  `/admin/summary` + `/admin/events` + `scripts/analytics.py` to read it back. Four
  server-side events too, so a blocked client still leaves the prompt text. Retention
  180 days; opt-out is DNT or `notrack`; the privacy notice now lists every one of the
  six things collected instead of only the AI prompts. Learned that the honest privacy
  copy is the hard half: `nkeys` matched the `key` redaction rule and the server was
  silently deleting a legitimate prop, which is exactly the class of bug a policy
  written from a template would never have caught.

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
  `OONTZ_OFFLINE=1` now makes `ai.available()` say no. And `do()` only guarded command
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
