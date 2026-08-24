"""Asserts for the parts of the API that are pure functions.

    python api/check.py

Routes need a server and a database; these do not, and they are where the bugs
were: a state dump that truncated away the very list the prompt tells the model to
obey, a rate limiter keyed on a header the caller writes, and a by-line that
published someone's email address.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OONTZ_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_check.db"))

import main  # noqa: E402


def check_state_text():
    """The verb list must survive; the patterns are what gets cut."""
    state = {
        "bpm": 150, "section": "drop",
        "tracks": {("t%d" % i): {"pat": "x" * 128, "gain": 1,
                                 "notes": ["a1"] * 64} for i in range(12)},
        "order": ["t%d" % i for i in range(12)],
        "commands": ["bpm", "gain", "sidechain", "compose"],
    }
    out = main._state_text(state)
    assert len(out) <= 4000, "state text is %d chars" % len(out)
    assert '"commands"' in out, "the verb list was truncated away - the prompt's rule cannot fire"
    assert '"order"' in out, "the arrangement was truncated away"
    assert "x" * 40 not in out, "a 128-step pattern went in whole"
    assert main._state_text({}) == "{}", "an empty state should not explode"
    assert main._state_text(None) == "{}", "a missing state should not explode"
    return "%d chars, verb list intact" % len(out)


def check_sessions():
    """A tampered or expired session must not unseal."""
    tok = main.sign({"uid": 7, "exp": main.time.time() + 60})
    assert main.unsign(tok)["uid"] == 7, "a fresh session did not round-trip"
    assert main.unsign(tok + "x") is None, "a tampered session unsealed"
    assert main.unsign("nonsense") is None, "garbage unsealed"
    old = main.sign({"uid": 7, "exp": main.time.time() - 1})
    assert main.unsign(old) is None, "an expired session unsealed"
    return "signed, tampered, expired"


def check_no_email_in_public():
    """Publishing must never expose an address nobody offered."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"),
               encoding="utf-8").read()
    assert 'email"].split("@")' not in src and "email'].split('@')" not in src, \
        "an email local-part is still being used as a public by-line"
    assert 'd["by"] = d["handle"] or "anon"' in src, "the gallery by-line is not anonymous"
    return "no addresses in public output"


def check_rate_limit_key():
    """X-Forwarded-For is written by the caller; only the last hop is the proxy's."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"),
               encoding="utf-8").read()
    assert 'split(",")[-1]' in src, "the rate limiter trusts a client-supplied hop"
    return "keyed on the proxy's hop"


def main_():
    checks = [check_state_text, check_sessions, check_no_email_in_public, check_rate_limit_key]
    bad = 0
    for fn in checks:
        try:
            print("  ok    %-22s %s" % (fn.__name__[6:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-22s %s" % (fn.__name__[6:], e))
    print("  api: %d passed, %d failed" % (len(checks) - bad, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.exit(main_())
    finally:
        try:
            os.remove(os.environ["OONTZ_DB"])
        except OSError:
            pass
