# oontz — web architecture

## The constraint that decides everything

oontz is Python + numpy + sounddevice + a terminal. **None of that runs in a browser.**
Three ways out, and only one of them is a playable instrument:

| approach | latency | cost at scale | verdict |
|---|---|---|---|
| Render server-side, stream audio | 200ms+ round trip | CPU per listener, per second | Dead. You cannot play an instrument through it, and "free" is impossible. |
| Pyodide (numpy in WASM) | 10MB+ download, GC pauses in the audio path | free | Dead for live audio. Fine for offline render. |
| **Port the DSP to WebAudio / AudioWorklet** | sub-10ms, native | **free — it runs on the visitor's machine** | This one. |

So: **oontz.sh is a client-side instrument.** The server never touches audio.

## What ports and what gets rewritten

The Python codebase splits cleanly, which is lucky and not an accident — it is what
came out of keeping the seams pure.

**Ports almost mechanically** (pure logic, no numpy, no I/O):
- `song.py` — Song/Section/state_at/automation. The whole timeline model.
- `layout.py` — the panel solver.
- `keymap.py` — the key table.
- `harmony.py` — scales, chords, Camelot, motifs.
- `compose.py` — arrangement grammar, energy curves.
- `library.py` — compatibility scoring.
- `theme.py`, `waveform.py`, `ui_studio.py`, `ui_deck.py` — string-building, all pure.

**Gets rewritten in JS** (the numpy DSP):
- `voices.py`, `drums.py`, `synths.py` — oscillators and envelopes. Straightforward:
  these are formulas, not libraries.
- `fx.py` — filters, delay, reverb. WebAudio has BiquadFilter, DelayNode and
  ConvolverNode natively, which replaces most of it.
- `core.render_bar` — becomes an AudioWorklet that renders a bar into a buffer.

The architecture survives intact: pre-render a bar, the worklet slices it, live FX
are pointer math. That was always the right shape for a browser too.

## The property that makes the whole product work

**A song is text.** A `.song` file is a few KB of JSON. The engine is deterministic.

That means the gallery stores SONGS, not audio:
- Sharing a track costs kilobytes, not megabytes.
- Hosting is effectively free — no object storage, no bandwidth bill, no transcoding.
- Anyone who opens a shared track gets the *source*: they can hear it, open the
  arrangement, take it apart, and remix it.
- Every track on the site is a playable, editable instrument preset.

You share the recipe, not the cake. Nothing else in music software works this way.

## Services

```
oontz.music   Vercel, static      the CLI landing page + public gallery
oontz.sh      Vercel, static      the instrument (WebAudio, all client-side)
api.oontz.sh  Railway             accounts, song storage, gallery, AI proxy
```

The API is small on purpose: email verify, save/load songs, publish/browse, and one
proxied AI endpoint so no key ever reaches the browser. No audio anywhere in it.

## Auth, kept minimal

Email + a magic link. No passwords, no OAuth providers, no sessions to leak.
You can use the whole instrument with no account at all — an account only buys you
storage and publishing. Local work lives in `localStorage` until you want it kept.
