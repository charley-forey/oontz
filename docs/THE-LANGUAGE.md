# The Song Is the Source

**The research article: https://oontz.music/language**

The complete reasoning behind this class of language — history, theory,
semantics, architecture, metaphors, economics, failure modes, and a conformance
checklist precise enough to build a rival implementation from. ~21,000 words.
It lives as a page rather than as markdown because it is meant to be read,
linked and cited; this file is its outline and its map.

Source: [`web/landing/language.html`](../web/landing/language.html), served at
`/language` by `web/landing/server.py`. Its internal anchors are gate-checked
(`python web/landing/server.py check`).

---

## What it is for

Software got version control, code review, forks, diffs, and a culture of
reading each other's work. Music got the WAV file. That asymmetry is a
consequence of the artifact each field exchanges: programmers exchange
*source*, musicians exchange *renders*.

The article argues that a narrow, achievable class of language — **a
declarative, deterministic, whole-song source format with independent
runtimes** — closes the gap, and that the design space has been repeatedly
half-explored for sixty-five years without anyone landing in the middle of it.
oontz is the existence proof; the article is the reasoning, written down so the
next language does not start from scratch.

## Outline

**Part I — The problem** (§1–4)
1. The artifact gap · why a project file is not a source format
2. Six thousand years of text · notation as compression against an assumed
   decoder; ABC, MML, trackers
3. The computer-music lineage · Music-N, MIDI, SuperCollider, ChucK, Tidal,
   Sonic Pi, Strudel, ORCA, bytebeat — what each proved and what each costs
4. The hole in the middle · the empty quadrant, and the thesis

**Part II — The theory** (§5–11) — *the part that transfers to a language
sharing none of our syntax*
5. Nine laws, and what they forbid
6. A song is a pure function · `state_at(bar)`; snapshots, not diffs;
   referential transparency
7. Models of musical time · event list vs. cycle vs. clock vs. timeline; where
   the seam goes
8. Determinism and the human · why a seeded PRNG fails, and hashing coordinates
   instead
9. Notation as interface · iconicity, the guessability test, polymeter for free
10. Totality and failing open · fail open ≠ fail silent; clamp at the assignment
11. Metaphors and analogies · HTML, recipe/cake, seed, build artifact, chess
    notation, knitting patterns, DNA — and two metaphors to avoid

**Part III — The architecture** (§12–18)
12. The layer cake · why the IR is the load-bearing layer
13. One bar ahead · the scheduler, and what bar-quantized editing costs
14. Voices that ask · extension by parameter name
15. Effects and the duck · make the genre's signature move a primitive
16. Two runtimes, one theory · the 360-arrangement parity gate
17. Generation over the IR · arrangement as grammar; where a model fits
18. The proof obligations · the four gates, and golden renders as a cultural
    device

**Part IV — The consequences** (§19–25)
19. Version control for music · diff, blame, bisect, PR — and merge, unsolved
20. The economics of kilobytes · why sustainable free is an architecture
21. Searching the music itself · the corpus as a research instrument
22. Why machines read this well · five structural reasons
23. Teaching and reading · the ten-second rule, defended
24. Preservation · rot rates, and what a preservation-grade format requires
25. Access

**Part V — Build your own** (§26–29) — *the payload*
26. Twelve decisions, with when the other answer is right
27. A conformance checklist
28. Ten anti-patterns
29. Open problems · semantic merge, structural diff, perceptual equality,
    sub-bar structure, microtiming, similarity search, notation for timbre, a
    package registry, formal semantics, localization

**Part VI — Appendices** (A–F)
- A. Grammar (EBNF)
- B. The document schema
- C. The determinism hash, in both languages
- D. Glossary
- E. Bibliography
- F. Reuse and citation

## The nine laws, in short

1. **The source is the song** — audio is a build artifact.
2. **Determinism is non-negotiable** — same text, same sound, any machine, any
   year.
3. **Legibility beats expressiveness** — every extension passes the
   guessability test.
4. **The whole song or nothing** — a loop is not a song.
5. **One source, many runtimes** — two implementations, gated for parity, or
   you have a save file.
6. **No hidden state** — if a knob matters, it is written down.
7. **Ten seconds to the first sound** — this kills whole architectures.
8. **Fail open, never fail silent** — keep playing, say what happened.
9. **Text is the API** — every capability reads the same document.

## Related

- [OONTZ-FORMAT.md](OONTZ-FORMAT.md) — the format specification
- [PRIOR-ART.md](PRIOR-ART.md) — the audit: what was taken from each system,
  and what was declined
- [ARCHITECTURE-WEB.md](../ARCHITECTURE-WEB.md) — the browser constraint that
  decides everything

## Citing it

```
The Song Is the Source: Notes Toward an Audio Programming Language.
oontz, 2026. https://oontz.music/language
```

Fork it, argue with it, publish a correction. The most useful outcome is a
better language that cites this one as the thing it improved on.
