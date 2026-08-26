# Runbook: oontz is under attack

Nothing here is on by default. This is the order to do things in when the sites
are actually being flooded, and the one gotcha that will bite you if you guess.

## 0. Is it an attack?

Read the response **body**, not the status code. A `503` with a `P3P:` header and
"Category: newly-registered-domain" is a guest-WiFi filter, not traffic — see
`oontz-domain-filtering`. Check from outside your network before doing anything.

Real signal: `railway logs --service api` showing sustained requests, or
`/admin/summary`'s `top_ips` (needs `OONTZ_ADMIN_KEY` set — it is not, by
default, which is why `/admin/*` 404s).

## 1. Block the source, if it has one

Edge rules take effect in seconds and cost nothing:

```
Settings → Edge → Edge Rules → Edit as JSON
```

Add a rule matching `ipv4.src` `in` the offending CIDRs with action `block`,
priority above the scanner rules. Rules are per service and apply to every
domain on it.

## 2. Under Attack Mode, if it does not

```bash
railway waf under-attack enable --service app --duration 1h
railway waf under-attack enable --service landing --duration 1h
```

**The gotcha: browser-check clearance is scoped to the root domain.**

| site | api | clearance shared? |
|---|---|---|
| `oontz.sh` | `api.oontz.sh` | yes |
| `oontz.music` | `api.oontz.sh` | **no — different root domain** |

And the check is only shown to browser navigations (a `GET` whose `Accept`
includes `text/html`). Everything else is turned away outright.

So:

- Enabling it on `app` and `landing` is safe. Visitors pass once and continue.
- Enabling it on `api` blocks **all** API traffic, because API calls are never
  navigations. Only do that if the attack is hitting the API directly, and
  expect oontz.music's server-side `fetch()` (`web/landing/server.py:48`) to
  fail, so share cards fall back to the brand card and `/t/<id>` pages lose
  their per-track OG tags.

Turn it off as soon as the flood stops — every new visitor pays the check while
it is on.

## 3. Cut the expensive endpoints

If the cost is the problem rather than the load:

```bash
railway variables set OONTZ_AI_DAY_MAX=0 --service api    # shared AI key off
```

Bring-your-own-key requests keep working; `ai_budget_ok()` only counts the
shared key.

Anonymous publishing is already unlisted (`public=2`) unless
`OONTZ_ANON_PUBLIC` is set. Confirm it is unset before looking for a spam
problem in the gallery.

## 4. Afterwards

- CDN caching (`railway cdn enable --service app|landing`) means edge hits never
  reach the service, so the service logs and `scripts/analytics.py` undercount.
  `track.js` still sees every visitor.
- The rate limiter is in-process (`_HITS`, `api/main.py`). It resets on every
  deploy — redeploying during an incident clears every 429.
