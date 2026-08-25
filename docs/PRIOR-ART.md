# Prior art — what oontz takes, and what it politely declines

Five projects prove pieces of the "music as text" idea. None of them owns the thing
oontz is for: **a complete, portable, readable source format for an entire modern
song.** This document is the audit: what each project got right, what we absorb,
what we skip, and — kept honest — what oontz already had before reading any of them.

## The scoreboard

| Project | Take | Skip | Status in oontz |
|---|---|---|---|
| [Strudel](https://strudel.cc) | parser→AST discipline, browser-first runtime, modular outputs | its live-coding syntax | AST/IR: **already had** (`.song` is the IR). Outputs: WebAudio ✅ WAV ✅ **MIDI shipped this cycle** OSC later |
| [TidalCycles](https://tidalcycles.org) | the *ideas* of mini-notation: rests, repeats, probability, grouping | the Haskell, the cleverness | rests **already had** (`.`); `* N` repeat and `?` probability **shipped this cycle**; `[xx..]` subdivision later |
| [Sonic Pi](https://sonic-pi.net) | make the first sound in seconds; joy as a requirement | being a programming language | **already had**: browser, one command, no install, no account |
| [SuperCollider](https://supercollider.github.io) | language ≠ audio engine | its scale and UGen surface | **already had, stronger**: two full runtimes (Python + WebAudio) held identical by a 360-arrangement parity gate and golden renders |
| [ABC notation](https://abcnotation.com) | a versioned formal spec that outlives any app | its syntax (wrong genre) | **already had**: `format: "oontz-song-1"`, [OONTZ-FORMAT.md](OONTZ-FORMAT.md) |

## The one-line verdicts

**Strudel** is the closest cousin — a modular browser pattern system. Its lesson is
architecture: text parses to structure, structure feeds interchangeable outputs.
oontz's structure is the `.song` document; its outputs now include MIDI. We do NOT
adopt its package split yet: there are no external consumers, and carving
`@oontz/core` out before someone needs it is scaffolding for later's sake. The
trigger to split is written in ROADMAP: the first external consumer.

**TidalCycles** proves a small notation can be deeply expressive. But Tidal optimizes
for live-coders; oontz optimizes for *musicians, readers, and AI agents*. Every
notation extension must pass the house test: **someone who has never programmed can
guess what it does.** `x... *4` passes. `x?` passes ("that hit... maybe"). Nested
polymetric alternation does not, and stays out.

**Sonic Pi**'s philosophy — simple enough for beginners, powerful enough for serious
work, playful throughout — is already the copy voice and the ten-second demo. Its
live-loop *performance* culture is a feature for us, not the product: the product is
the song as source.

**SuperCollider** teaches separation of concerns at scale. oontz keeps the lesson
and skips the scale: patterns + notes + voices + arrangement + automation + fx is
the complete v1 surface. The goal is not every possible sound; it is the best
representation of a song.

**ABC** proves a plain-text music format can outlive every application around it —
decades, thousands of tools, one spec. That discipline (versioned spec, canonical
format, independent implementations) is exactly the `oontz-song-1` posture.

## What none of them solve — the oontz thesis

A complete modern song as canonical text: human + AI editable, versionable,
diffable, searchable, forkable with provenance, rendered identically by independent
runtimes. That stack exists here today (`source`/`load`/`diff`, remix lineage,
structural search, rooms) and is the moat. See PLAN.md "Source code for music."

## Decisions taken this cycle

1. **Pattern language v2** (both engines, spec'd): `* N` repeat sugar and `?`
   probability hits — deterministic per bar, so the determinism guarantee holds.
2. **MIDI output**: `export midi` — a song leaves for any DAW as a standard file.
3. Recorded as Later, with triggers: `[xx..]` subdivision, OSC output, the
   `@oontz/*` package split, desktop MIDI export (the evolution loop's queued item).
