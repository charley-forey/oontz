---
name: evolve
description: Run one oontz evolution cycle - pick the top open roadmap item, implement it, prove it, push it, and append what was learned. Use when the user says "evolve", "improve oontz", "next cycle", or runs /loop over this project.
---

# One evolution cycle

You are improving `oontz` at C:\Users\charl\desktop\oontz. Do ONE cycle, completely,
then stop. Do not start a second cycle in the same run.

## The cycle

1. **Read `ROADMAP.md`.** If it carries a `## ⏸ PAUSED` section, STOP: run no
   cycle, change nothing, and report that the loop is paused and why. Otherwise
   take the topmost unchecked item under "Now". If "Now" is
   empty, promote the best two items from "Next" into "Now" and take the first.
   **Idea intake:** whenever you promote, also re-read `IDEAS.md` and the cycle log
   and append ONE new item to "Next" with a one-line reason - a gap between what
   IDEAS.md asks for and what the code does. That is how the roadmap grows on its own.

2. **Read the code it touches** before writing anything. `oontz/contracts.py` is the
   frozen seam; modules register into shared dicts and nothing edits `core.py`
   except deliberately.

3. **Implement it.** House style: terse, comments explain WHY. No new dependencies
   (numpy and sounddevice only). Match the surrounding code.

4. **Prove it.** Both must pass, and you must run them:
   - `python -m oontz test`
   - `python -m oontz.qa --quick`
   Add at least one assert that would FAIL if your change regressed. A change with
   no check is not finished.

   **Web items** (`web/app`, `web/landing`, `api/`) have their own gates, run in
   addition:
   - `node web/app/check.js` - the pure half: song model, keys, FFT, theory, and
     the guards that keep published JSON out of innerHTML.
   - `python scripts/browsergate.py` - the real half. Drives the actual index.html
     in headless Edge and asserts on the cold start, the composer, the ear,
     improve, export's WAV header, both decks, the keyboard, the palette and the
     scrollback. Takes about four minutes. Anything touching the browser runtime
     is NOT proven until this passes; it is what caught measure() exhausting the
     browser's OfflineAudioContexts and spinback throwing on key repeat.
   - `python api/check.py` when `api/` changed.

   After the push, poll `mcp__railway__get-status` until the service reports
   SUCCESS, then fetch the live URL and confirm the change is in the served file.
   A web cycle is not done until the deploy is green.

5. **THE GATE.** If either suite fails, fix it or revert your change. Never commit
   red. A loop that pushes broken audio to main is worse than no loop.

6. **Commit and push to main.** Message: what changed, what it measured, why.
   End with the Co-Authored-By and Claude-Session trailers used in the log.

7. **Update `ROADMAP.md`**: tick the item, and append ONE line to the cycle log
   saying what changed, what it measured, and what you learned. If the work
   revealed new work, add those items — that is how the roadmap grows.

## Rules

- One item per cycle. Finishing one thing beats starting three.
- Report honestly. If you could not do it, say so and why, and leave it unticked.
- Numbers, not adjectives. "58 fps, was 7" not "much faster".
- You cannot hear audio and cannot drive the interactive TUI. Verify structurally
  and say what you could not verify.
- If an item turns out to be a bad idea, say so, strike it from the roadmap with a
  one-line reason, and take the next one instead.
