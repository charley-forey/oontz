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
