"""Ask Resend where the oontz.sh sending domain has got to.

    python scripts/mailcheck.py [--verify]

Reads RESEND_API_KEY from the environment, or from the linked Railway service.
See docs/runbook-mail.md for what the records are and why this blocks signups.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

DOMAIN_ID = "232d4a96-5ad4-4e67-9778-c5c667138e94"


def key():
    k = os.environ.get("RESEND_API_KEY")
    if k:
        return k
    # The key lives on the Railway service, not in this repo, and never should.
    try:
        out = subprocess.run(["railway", "variables", "--service", "api", "--json"],
                             capture_output=True, text=True, shell=True, timeout=60).stdout
        return json.loads(out).get("RESEND_API_KEY")
    except Exception:
        return None


def call(path, k, method="GET"):
    # Resend sits behind Cloudflare, which answers urllib's default agent with 1010.
    r = urllib.request.Request("https://api.resend.com" + path, method=method,
                               headers={"authorization": "Bearer " + k,
                                        "user-agent": "oontz-mailcheck/1"})
    try:
        with urllib.request.urlopen(r, timeout=30) as f:
            return json.load(f)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(errors="replace"), "status": e.code}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="ask Resend to re-check the records now")
    a = ap.parse_args()
    k = key()
    if not k:
        print("no RESEND_API_KEY (set it, or `railway link` this project)"); sys.exit(2)
    if a.verify:
        call("/domains/%s/verify" % DOMAIN_ID, k, "POST")
    d = call("/domains/" + DOMAIN_ID, k)
    if d.get("error"):
        print(d["error"]); sys.exit(2)
    print("%s  %s" % (d.get("name"), (d.get("status") or "?").upper()))
    for r in d.get("records") or []:
        print("  %-4s %-20s %-12s %s" % (r.get("type"), r.get("name"), r.get("status"),
                                         (r.get("value") or "")[:56]))
    if d.get("status") == "verified":
        print('\nready. now: railway variables --service api '
              '--set "OONTZ_MAIL_FROM=oontz <hello@oontz.sh>"')
    else:
        print("\nnot yet. add the records in docs/runbook-mail.md, then rerun with --verify")


if __name__ == "__main__":
    main()
