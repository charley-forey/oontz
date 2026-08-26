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


def check_clean_batch():
    """The ingest caps and the redaction. Everything here is what the client cannot
    be trusted to have done itself."""
    B = lambda **kw: dict({"sid": "s1", "site": "app"}, **kw)          # noqa: E731
    ev = lambda n, p=None: {"n": n, "t": 1.0, "p": p}                  # noqa: E731

    rows = main.clean_batch(B(events=[ev("click") for _ in range(60)]), 100.0)
    assert len(rows) == 50, "a 60-event batch became %d rows" % len(rows)
    assert rows[0][0] == 100.0, "the server clock is not stamped"

    rows = main.clean_batch(B(events=[ev("boot", {"note": "my key is sk-ant-abc123 ok",
                                                  "nest": [{"deep": "sk-ant-xyz"}]})]), 1.0)
    assert "sk-ant-" not in rows[0][7], "an Anthropic key reached the table: %s" % rows[0][7]

    rows = main.clean_batch(B(events=[ev("boot", {"email": "a@b.c", "API_TOKEN": "x",
                                                  "ok": 1})]), 1.0)
    props = rows[0][7]
    assert "a@b.c" not in props and "API_TOKEN" not in props and '"ok":1' in props, props

    rows = main.clean_batch(B(events=[ev("boot", {"text": "z" * 4096})]), 1.0)
    assert len(rows) == 1, "an oversized prop dropped the event instead of truncating it"
    assert len(rows[0][7].encode()) <= 2048, "props are %d bytes" % len(rows[0][7].encode())

    rows = main.clean_batch(B(events=[ev("Click Me"), ev("9lives"), ev("x" * 41), ev("ok_1")]), 1.0)
    assert [r[6] for r in rows] == ["ok_1"], "a bad event name got through: %s" % [r[6] for r in rows]

    assert main.clean_batch({"site": "app", "events": [ev("click")]}, 1.0) == [], \
        "a batch with no sid was accepted - sid is NOT NULL"
    assert main.clean_batch(B(site="hax", events=[ev("click")]), 1.0)[0][5] == "app", \
        "an unknown site was stored verbatim"
    assert main.clean_batch("not a batch", 1.0) == [] and main.clean_batch(None, 1.0) == []
    return "50-cap, sk-ant stripped, secrets dropped, 2KB truncate"


def main_():
    checks = [check_state_text, check_sessions, check_no_email_in_public, check_rate_limit_key,
              check_clean_batch]
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
