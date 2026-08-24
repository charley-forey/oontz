# oontz api

Accounts, song storage, the public gallery, and an AI proxy. No audio ever passes
through here — the instrument runs entirely in the visitor's browser.

    uvicorn main:app --reload

## Environment

| var | what it does |
|---|---|
| `OONTZ_DB` | sqlite path. On Railway point it at a volume, e.g. `/data/oontz.db` |
| `OONTZ_SECRET` | session signing key. Set it, or sessions are forgeable |
| `OONTZ_APP_URL` | where the instrument lives, e.g. `https://oontz.sh` |
| `OONTZ_SITE_URL` | the landing site, e.g. `https://oontz.music` |
| `OONTZ_API_URL` | this service's public URL, used to build magic links |
| `RESEND_API_KEY` | optional. Without it, sign-in links come back in the response |
| `ANTHROPIC_API_KEY` | optional. Without it `/ai/ask` returns 503 and the app falls back |

Everything except the first two is optional; the service starts and works without them.

## Endpoints

| method · path | auth | what |
|---|---|---|
| `POST /auth/request` · `GET /auth/verify` | — | magic-link sign-in |
| `GET /me` · `PATCH /me {handle}` | ✓ | who you are; one-word handle shown on the gallery |
| `POST/GET/DELETE /songs…` · `POST /songs/{id}/publish` | ✓ | songs; publish puts one in the gallery |
| `GET /gallery` | — | public songs |
| `POST/GET/DELETE /takes…` | ✓ | takes: the command log as text (≤64KB), never audio |
| `POST/GET/PATCH/DELETE /playlists…` · `PUT /playlists/{id}/items` | ✓ | ordered song lists; `public` makes them shareable |
| `GET /playlists/public` · `GET /p/{id}` | — | what the landing page reads |
| `GET /search?pat=&track=&bpm=&key=` | — | find tracks by the music itself: exact pattern, BPM window, key |
| `GET /similar/{id}` | — | more like this one, scored on structure, reasons included |
| `GET /songs/{id}/remixes` | — | the family tree: ancestors up, public flips down |
| `POST /ai/ask` | — | AI proxy; honours `X-Anthropic-Key` (used, never stored or logged) |

Run the tests with `python api/test_api.py` — they spawn a real uvicorn against a
temp database and walk the whole loop, magic link included.
