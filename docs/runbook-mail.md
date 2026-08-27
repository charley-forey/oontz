# Sending domain: oontz.sh

Until this is done, `send_mail` goes out from `onboarding@resend.dev`, and Resend
refuses every recipient except the account owner. That means **nobody but you can
create an account** — the magic link is generated, the API reports `sent: false`,
and the stranger who typed their email gets nothing. It is the single hardest
blocker on having users at all.

The domain is already registered in Resend as `oontz.sh`
(id `232d4a96-5ad4-4e67-9778-c5c667138e94`, region `us-east-1`, status
`not_started` until the records below resolve). Nothing sends from it yet, and
deleting it in the Resend dashboard undoes this completely.

## 1. Add three records at Namecheap

Advanced DNS → oontz.sh → Add New Record. Namecheap appends the domain itself, so
the Host column is exactly what is written here — no trailing `.oontz.sh`.

| Type | Host | Value | Priority | TTL |
|---|---|---|---|---|
| TXT | `resend._domainkey` | `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDW3eDcsBY1jO7sXAAXLmc9W5a0bbGogw5W6bCA8fEPfgJ+aGbZoo5kx1c1NxJpCnLKszxaZ6RrMAKZdfnAN6WO0fbV3zoES1pFvRsfhGLkDcHjYapa19pJ1nX8+M6ypEYE8up4/EVZeZi8apYc4D+71M6/F9niKht8pt9K1GsK5wIDAQAB` | — | Automatic |
| MX | `send` | `feedback-smtp.us-east-1.amazonses.com` | `10` | Automatic |
| TXT | `send` | `v=spf1 include:amazonses.com ~all` | — | Automatic |

All three sit on subdomains, so **none of them touches the apex ALIAS that points
oontz.sh at Railway**. The website is unaffected.

The DKIM value is one line with no spaces. Namecheap sometimes wraps it in the
input box; that is display only. If it rejects the length, paste without any
surrounding quotes.

## 2. Verify

    python scripts/mailcheck.py

It asks Resend to re-check and prints the per-record status. Namecheap usually
resolves inside 30 minutes; Resend re-checks on its own for 72 hours.

## 3. Switch the from address

Only once status reads `verified` — flipping it earlier breaks the mail that does
work today:

    railway variables --service api --set "OONTZ_MAIL_FROM=oontz <hello@oontz.sh>"

Railway redeploys the service. Then confirm end to end from a browser that is not
signed in, with an address that is not yours:

    login someone-else@example.com

`{"sent": true}` and no `link` field in the response means it went to a real
inbox. While mail is broken the API hands the link back in the response instead,
which is how `scripts/seed_gallery.py` signs itself in — that path stops working
once this is verified, and the script says so rather than guessing.
