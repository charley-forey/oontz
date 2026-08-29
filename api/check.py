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


class _Req:
    """Enough of a Request for client_ip: headers and a peer."""
    def __init__(self, headers, peer="10.0.0.1"):
        self.headers = headers
        self.client = type("C", (), {"host": peer})()


def check_rate_limit_key():
    """X-Forwarded-For is written by the CALLER. If the bucket key comes from it,
    every limit in main.py is bypassed by rotating one header - so assert the
    behaviour, not the source line that happens to implement it."""
    ip = main.client_ip
    assert ip(_Req({"x-real-ip": "9.9.9.9", "x-forwarded-for": "1.2.3.4"})) == "9.9.9.9", \
        "a client-supplied X-Forwarded-For beat the edge's X-Real-IP"
    a = ip(_Req({"x-real-ip": "9.9.9.9", "x-forwarded-for": "1.1.1.1"}))
    b = ip(_Req({"x-real-ip": "9.9.9.9", "x-forwarded-for": "2.2.2.2"}))
    assert a == b, "rotating X-Forwarded-For bought a fresh rate-limit bucket"
    assert ip(_Req({}, peer="10.0.0.7")) == "10.0.0.7", "no header, no peer fallback"
    assert ip(None) == "?", "client_ip must survive no request at all"
    return "keyed on X-Real-IP, XFF ignored"


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


def check_admin_guard():
    """No key configured means no admin surface at all - and a wrong key must
    look exactly like no surface, or the 401 itself is the leak."""
    old = main.ADMIN_KEY
    try:
        main.ADMIN_KEY = ""
        assert not main.admin_ok("anything"), "the admin surface opened with no key set"
        main.ADMIN_KEY = "s3cret"
        assert main.admin_ok("s3cret"), "the right key was refused"
        assert not main.admin_ok("s3cre"), "a prefix opened the door"
        assert not main.admin_ok(""), "an empty header opened the door"
        assert not main.admin_ok(None), "a missing header opened the door"
    finally:
        main.ADMIN_KEY = old
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"),
               encoding="utf-8").read()
    assert "compare_digest(str(supplied" in src, "the admin key is compared with =="
    assert main.clamp(9999, 1, 365, 30) == 365 and main.clamp(0, 1, 365, 30) == 1, \
        "the window is not clamped - a summary would full-scan an unbounded table"
    assert main.clamp("nope", 1, 1000, 200) == 200 and main.clamp(None, 1, 1000, 200) == 200
    assert main.clamp(float("nan"), 1, 1000, 200) == 200, "NaN slipped past the clamp"
    assert main.clamp("50", 1, 1000, 200) == 50, "a numeric string was thrown away"
    return "404 posture, constant-time compare, clamped window"


def check_admin_summary():
    """The aggregates, against a seeded table. Three sessions on two devices,
    one of which fails its command."""
    now = main.time.time()
    with main.closing(main.db()) as c:
        c.execute("DELETE FROM events")
        for sid, did in (("a", "d1"), ("b", "d1"), ("c", "d2")):
            names = [("boot", None),
                     ("prompt_submit", {"text": "kick harder", "verb": "kick"}),
                     ("cmd_result", {"verb": "kick", "ok": sid != "c"}),
                     ("play", {"song_id": "x"}),
                     ("api_error", {"status": 500})]
            if sid == "a":       # exactly one session types a SECOND thing
                names.append(("prompt_submit", {"text": "hat faster", "verb": "hat"}))
                names.append(("feedback", {"text": "the decks are great", "chars": 19}))
                # and exactly one changes a pattern, then hands it to someone -
                # the two stages that are the actual game
                names.append(("edit", {"verb": "kick", "how": "tap"}))
                names.append(("share_mint", {"kind": "server", "anon": 1}))
            rows = main.clean_batch({"sid": sid, "did": did, "site": "app", "path": "/",
                                     "events": [{"n": n, "t": now, "p": p} for n, p in names]},
                                    now, "1.2.3.4", "ua")
            c.executemany(main.EV_INSERT, rows)
        c.commit()
    old = main.ADMIN_KEY
    try:
        main.ADMIN_KEY = ""
        try:
            main.admin_summary(window=30, x_admin_key="k")
            raise AssertionError("the summary answered with OONTZ_ADMIN_KEY unset")
        except main.HTTPException as e:
            assert e.status_code == 404, "an unset admin key leaked a %d" % e.status_code
        main.ADMIN_KEY = "k"
        s = main.admin_summary(window=30, x_admin_key="k")
        ev = main.admin_events(name="prompt_submit", x_admin_key="k")["events"]
    finally:
        main.ADMIN_KEY = old
    assert s["totals"]["sessions"] == 3 and s["totals"]["devices"] == 2, s["totals"]
    assert s["top_prompts"][0] == {"text": "kick harder", "n": 3, "sessions": 3}, s["top_prompts"]
    assert s["totals"]["events"] == 19, s["totals"]
    assert [f["text"] for f in s["feedback"]] == ["the decks are great"], s["feedback"]
    verbs = {r["verb"]: r for r in s["commands"]}
    assert verbs["kick"]["n"] == 3 and verbs["kick"]["errors"] == 1 \
        and verbs["kick"]["error_rate"] == 0.333, verbs
    stages = {f["stage"]: f["sessions"] for f in s["funnel"]}
    assert stages == {"land": 3, "command": 3, "explore": 1, "audio": 3, "edited": 1,
                      "shared": 1, "save": 0, "signin": 0, "publish": 0}, stages
    # the tier is what stops a future reader treating signin as the goal again
    tiers = {f["stage"]: f["tier"] for f in s["funnel"]}
    assert tiers["edited"] == "activation" and tiers["shared"] == "activation", tiers
    assert tiers["signin"] == "account" and tiers["save"] == "account", tiers
    assert tiers["explore"] == "activation", tiers
    # explore counts SESSIONS that typed twice, not prompts - three prompts across
    # one session would read as three explorers if this ever went back to COUNT(*).
    assert [f["stage"] for f in s["funnel"]][:3] == ["land", "command", "explore"], s["funnel"]
    pct = {f["stage"]: f["pct"] for f in s["funnel"]}
    assert pct["land"] == 100.0 and pct["explore"] == 33.3 and pct["audio"] == 100.0, pct
    assert s["top_ips"][0]["ip"] == "1.2.3.4" and s["top_ips"][0]["n"] == 19, s["top_ips"]
    assert len(s["recent_errors"]) == 3, s["recent_errors"]
    assert s["median_session_sec"] is not None, "no session length was measured"
    assert len(ev) == 4 and ev[0]["name"] == "prompt_submit", ev   # 3 sessions, one typed twice
    return "3 sessions, 2 devices, 1 explorer, 1 editor, 1 sharer, tiered funnel"


def main_():
    checks = [check_state_text, check_sessions, check_no_email_in_public, check_rate_limit_key,
              check_clean_batch, check_admin_guard, check_admin_summary]
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
