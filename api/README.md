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
| `POST /similar` | — | more like this unsaved song (inline doc), same scorer |
| `GET /charts` | — | most forked, most-shared patterns, tempo spread, busiest keys |
| `GET /songs/{id}/remixes` | — | the family tree: ancestors up, public flips down |
| `POST /rooms` · `WS /ws/room/{code}` | — | rooms: a relay that forwards music between members and never interprets it |
| `POST /ai/ask` | — | AI proxy; honours `X-Anthropic-Key` (used, never stored or logged) |

Run the tests with `python api/test_api.py` — they spawn a real uvicorn against a
temp database and walk the whole loop, magic link included.

## Changing a variable does not change the running process

Railway bakes a deployment's environment at build time, so a variable you edit
afterwards reaches the service **only when a new deployment is created**. Editing
one enqueues that deployment automatically — but if it does not run, the old
process keeps serving the old value indefinitely, and nothing in the dashboard
looks broken.

That cost an hour on 2026-08-29. `OONTZ_MAIL_FROM` was set to
`oontz <hello@oontz.sh>` the moment the sending domain verified. The variable read
back correctly. The API kept sending from `onboarding@resend.dev`, so Resend
returned 403 for every recipient except the account owner and no stranger could
finish a sign-up. The enqueued deployment had been `QUEUED` for over half an hour
and never started; every later commit deployed `SKIPPED`, because they only touched
`web/`, so nothing displaced it.

What does NOT fix it:

- **Restart.** `restart-service` re-runs the *existing* deployment with the
  environment it was created with. The container comes back healthy and wrong.
- **Redeploy.** Needs a build to copy, and the newest deployment being `SKIPPED`
  means there is no snapshot. Both the MCP and `railway redeploy` refuse.

What does: a commit that touches `api/`, which is what this file is. The service
only builds when its own root directory changes, so a `web/`-only push will never
pick up an API variable change.

**To confirm mail is actually live**, ask for a link with an address that is not
the Resend account owner's:

    POST /auth/request {"email": "someone-else@example.com"}

`{"sent": true}` with **no** `link` field means it reached a real inbox. A `link`
in the response means delivery failed and the API handed the link back instead —
that fallback is deliberate, and it is also why a broken sender can look like a
working one from the browser.
