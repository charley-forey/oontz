"""The API gate. `python api/test_api.py`.

Spawns uvicorn on a free port with a throwaway sqlite file and walks the whole
account flow over plain urllib: request a link, read the token out of the `links`
table (mail is not configured here), verify, save, publish, handle, playlist,
share URL, takes, and the bring-your-own-key path of the AI proxy. No framework:
each assert names what broke.
"""
import os
import sys
import json
import time
import socket
import shutil
import sqlite3
import tempfile
import subprocess
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="oontz-test-")
DB = os.path.join(TMP, "t.db")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


ADMIN_KEY = "test-admin-key"
PORT = free_port()
BASE = "http://127.0.0.1:%d" % PORT


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPEN = urllib.request.build_opener(NoRedirect).open


def call(method, path, body=None, token=None, headers=None):
    """(status, json). Never raises on an HTTP status; that is what we assert on."""
    data = json.dumps(body).encode() if body is not None else None
    h = {"content-type": "application/json"}
    if token:
        h["authorization"] = "Bearer " + token
    h.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with OPEN(req, timeout=45) as r:
            raw = r.read()
            try:                                  # not every 200 is JSON: /auth/verify is a page
                return r.status, json.loads(raw or b"{}"), dict(r.headers)
            except ValueError:
                return r.status, {"raw": raw.decode(errors="replace")}, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            j = json.loads(raw or b"{}")
        except ValueError:
            j = {"raw": raw.decode(errors="replace")}
        return e.code, j, dict(e.headers)


def post_form(path, fields):
    """The one form post in the API: signing in. `call` only speaks JSON."""
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers={"content-type": "application/x-www-form-urlencoded"})
    try:
        with OPEN(req, timeout=45) as r:
            return r.status, {}, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}"), dict(e.headers)
        except ValueError:
            return e.code, {"raw": raw.decode(errors="replace")}, dict(e.headers)


def sign_in(email):
    st, j, _ = call("POST", "/auth/request", {"email": email})
    assert st == 200 and j["sent"] is False and "link" in j, ("request link", st, j)
    with sqlite3.connect(DB) as c:
        tok = c.execute("SELECT token FROM links WHERE email=?", (email,)).fetchone()[0]
    # A GET must only ASK. Mail scanners fetch every link in an email, so if this
    # ever hands back a session again, every scanned sign-in link is a stolen one.
    st, j, h = call("GET", "/auth/verify?token=" + tok)
    assert st == 200, ("verify page", st, j)
    body = j.get("raw", "")
    assert "#token=" not in body and "<form" in body and tok in body, ("verify page leaked or lost the token", body[:200])
    assert not (h.get("Location") or h.get("location")), ("a GET must not redirect into a session", h)
    st, j, h = post_form("/auth/verify", {"token": tok})
    loc = h.get("Location") or h.get("location") or ""
    assert st == 303 and "#token=" in loc, ("verify", st, j, h)
    return loc.split("#token=")[1]


def main():
    env = dict(os.environ, OONTZ_DB=DB, OONTZ_API_URL=BASE, OONTZ_SITE_URL="https://oontz.music",
               ANTHROPIC_API_KEY="", RESEND_API_KEY="", RAILWAY_ENVIRONMENT="",
               OONTZ_ADMIN_KEY=ADMIN_KEY)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                             "--port", str(PORT), "--log-level", "warning"], cwd=HERE, env=env)
    try:
        for _ in range(100):
            try:
                st, j, _ = call("GET", "/health")
                if st == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.2)
        else:
            raise SystemExit("uvicorn never came up on %s" % BASE)
        assert j == {"ok": True, "mail": False, "ai": False}, j

        # -- sign in: link -> sqlite -> verify -> session ---------------------------
        tok = sign_in("one@example.com")
        st, me, _ = call("GET", "/me", token=tok)
        assert st == 200 and me["email"] == "one@example.com" and me["handle"] is None, me
        assert call("GET", "/me")[0] == 401, "no token must be 401"

        # -- save, read, publish ------------------------------------------------------
        song = {"name": "t", "bpm": 140, "key": "a", "scale": "minor", "order": ["intro", "drop"],
                "sections": {"intro": {"bars": 16}, "drop": {"bars": 32}}}
        st, s, _ = call("POST", "/songs", {"title": "t", "data": song}, token=tok)
        assert st == 200 and s["id"] and s["public"] is False, s
        sid = s["id"]
        # a private song has nothing to share; the link goes back to the instrument
        assert s["url"].endswith("/?song=" + sid), s
        # a PUBLIC save must hand back the share page, not the bare app - /t/ is the
        # only URL that carries a card, and this returning ?song= is why every link
        # the UI ever gave anyone previewed as nothing
        st, pub, _ = call("POST", "/songs", {"title": "public one", "data": song,
                                             "public": True}, token=tok)
        assert st == 200 and pub["url"] == "https://oontz.music/t/" + pub["id"], pub
        # Identity is the id, never the title. Everyone's first track is called
        # "untitled" and everyone's second one is too; when title WAS identity, the
        # second save silently replaced the first - under links already handed out.
        st, t1, _ = call("POST", "/songs", {"title": "warehouse", "data": song}, token=tok)
        st, t2, _ = call("POST", "/songs", {"title": "warehouse", "data": song}, token=tok)
        assert t1["id"] != t2["id"], ("a namesake overwrote an earlier track", t1, t2)
        # ...but re-saving the SAME song edits it in place, which is what the id is for
        st, t3, _ = call("POST", "/songs", {"title": "warehouse mk2", "data": song,
                                            "id": t1["id"]}, token=tok)
        assert t3["id"] == t1["id"], ("an explicit id minted a twin", t1, t3)
        assert call("GET", "/songs/" + t1["id"], token=tok)[1]["title"] == "warehouse mk2"
        # someone else's id is not an edit permit
        assert call("POST", "/songs", {"title": "hijack", "data": song,
                                       "id": t1["id"]})[1]["id"] != t1["id"], "anon edited an owned song"
        assert call("GET", "/songs/" + sid)[0] == 403, "private song must be 403 to strangers"
        st, g, _ = call("GET", "/songs/" + sid, token=tok)
        assert st == 200 and g["bpm"] == 140 and g["sections"] == 2 and g["seconds"] == round(48 * 240 / 140, 1), g
        st, p, _ = call("POST", "/songs/%s/publish" % sid, token=tok)
        assert st == 200 and p["public"] is True and p["url"].endswith("/t/" + sid), p

        # -- handle -------------------------------------------------------------------
        assert call("PATCH", "/me", {"handle": "x"}, token=tok)[0] == 400, "2 chars must fail"
        assert call("PATCH", "/me", {"handle": "Has Space"}, token=tok)[0] == 400, "space must fail"
        st, h, _ = call("PATCH", "/me", {"handle": " DJ_Test "}, token=tok)
        assert st == 200 and h["handle"] == "dj_test", h
        assert call("GET", "/me", token=tok)[1]["handle"] == "dj_test"
        tok2 = sign_in("two@example.com")
        assert call("PATCH", "/me", {"handle": "dj_test"}, token=tok2)[0] == 409, "handles are unique"
        st, gal, _ = call("GET", "/gallery")
        assert st == 200 and gal["songs"][0]["id"] == sid and gal["songs"][0]["handle"] == "dj_test" \
            and gal["songs"][0]["by"] == "dj_test", gal

        # -- playlists ----------------------------------------------------------------
        st, pl, _ = call("POST", "/playlists", {"title": "warmup"}, token=tok)
        assert st == 200 and pl["id"] and pl["public"] is False, pl
        pid = pl["id"]
        st, j, _ = call("PUT", "/playlists/%s/items" % pid, {"song_ids": [sid, "nope"]}, token=tok)
        assert st == 400, ("unknown song must be refused", st, j)
        st, j, _ = call("PUT", "/playlists/%s/items" % pid, {"song_ids": [sid]}, token=tok)
        assert st == 200 and j["count"] == 1, j
        assert call("PUT", "/playlists/%s/items" % pid, {"song_ids": []}, token=tok2)[0] == 404, \
            "someone else's playlist must be 404"
        assert call("GET", "/p/" + pid)[0] == 404, "private playlist must be invisible at /p"
        assert call("GET", "/playlists/" + pid)[0] == 403, "private playlist must be 403 to strangers"
        assert call("GET", "/playlists/" + pid, token=tok)[1]["songs"][0]["id"] == sid
        st, j, _ = call("PATCH", "/playlists/" + pid, {"public": True}, token=tok)
        assert st == 200 and j["public"] is True and j["url"] == "https://oontz.music/p/" + pid, j
        st, share, _ = call("GET", "/p/" + pid)
        assert st == 200 and share["title"] == "warmup" and share["handle"] == "dj_test", share
        assert [k for k in ("id", "title", "handle", "created", "songs") if k not in share] == []
        s0 = share["songs"][0]
        assert s0["id"] == sid and s0["handle"] == "dj_test" and s0["bpm"] == 140 and "public" not in s0, s0
        st, pub, _ = call("GET", "/playlists/public?limit_n=40")
        assert st == 200 and pub["playlists"][0]["id"] == pid and pub["playlists"][0]["n"] == 1, pub
        st, mine, _ = call("GET", "/playlists", token=tok)
        assert st == 200 and [p["id"] for p in mine["playlists"]] == [pid], mine
        # a stranger can put a public song in their own playlist, but not a private one
        st, s2, _ = call("POST", "/songs", {"title": "secret", "data": song}, token=tok2)
        st, pl2, _ = call("POST", "/playlists", {"title": "theirs"}, token=tok2)
        assert call("PUT", "/playlists/%s/items" % pl2["id"], {"song_ids": [sid]}, token=tok2)[0] == 200
        assert call("PUT", "/playlists/%s/items" % pid, {"song_ids": [s2["id"]]}, token=tok)[0] == 400, \
            "a private song of someone else's must be refused"
        assert call("DELETE", "/playlists/" + pl2["id"], token=tok2)[0] == 200
        assert call("GET", "/playlists/" + pl2["id"], token=tok2)[0] == 404

        # -- anonymous sharing: a link without an account ------------------------------
        st, a1, _ = call("POST", "/songs", {"title": "anon track", "data": song, "public": True})
        assert st == 200 and a1["id"] and a1["url"] == "https://oontz.music/t/" + a1["id"], a1
        assert a1.get("claim"), "an anonymous save must return a claim token"
        st, ag, _ = call("GET", "/songs/" + a1["id"])
        assert st == 200 and ag["by"] == "anon", ag
        # it must be visible everywhere, not just the gallery - a half-done job here
        # reads to the sharer as their track silently vanishing
        st, gal, _ = call("GET", "/gallery")
        assert any(x["id"] == a1["id"] for x in gal["songs"]), "anon track missing from gallery"
        st, sr, _ = call("GET", "/search?q=anon")
        assert any(x["id"] == a1["id"] for x in sr["songs"]), "anon track missing from search"
        # two anonymous saves of the SAME title must be two songs. They share one uid,
        # so honouring same-title-updates would let anyone overwrite a stranger's track.
        st, a2, _ = call("POST", "/songs", {"title": "anon track", "data": song, "public": True})
        assert st == 200 and a2["id"] != a1["id"], (a1, a2)
        # pydantic rejects past 120; between that and 60 the server truncates, so a
        # gallery row cannot be filled with someone's essay
        assert call("POST", "/songs", {"title": "z" * 200, "data": song})[0] == 422, "120 cap"
        st, a3, _ = call("POST", "/songs", {"title": "z" * 100, "data": song, "public": True})
        assert st == 200 and len(a3["title"]) == 60, a3

        # -- claiming ------------------------------------------------------------------
        st, cl, _ = call("POST", "/songs/claim", {"claims": [a1["claim"], "bogus"]}, token=tok)
        assert st == 200 and cl["claimed"] == 1, cl
        st, mine, _ = call("GET", "/songs", token=tok)
        assert any(x["id"] == a1["id"] for x in mine["songs"]), "claimed song is not mine"
        st, again, _ = call("POST", "/songs/claim", {"claims": [a1["claim"]]}, token=tok)
        assert again["claimed"] == 0, "a claim token must not be replayable"

        # -- plays: reading is not hearing ---------------------------------------------
        st, p0, _ = call("GET", "/songs/" + a2["id"])
        st, p1, _ = call("GET", "/songs/" + a2["id"])
        assert p1["plays"] == p0["plays"], ("a read incremented plays", p0, p1)
        call("POST", "/songs/%s/play" % a2["id"])
        st, p2, _ = call("GET", "/songs/" + a2["id"])
        assert p2["plays"] == p0["plays"] + 1, ("play did not count", p0, p2)

        # -- takes --------------------------------------------------------------------
        log = "# oontz session\nbpm 140\nkick x...x...x...x...\nbass a1 . a1~ c2\n"
        st, t, _ = call("POST", "/takes", {"song_id": sid, "name": "first", "data": log}, token=tok)
        assert st == 200 and t["id"], t
        st, j, _ = call("POST", "/takes", {"name": "huge", "data": "x" * (64 * 1024 + 1)}, token=tok)
        assert st == 413, ("64 KB cap", st, j)
        st, j, _ = call("GET", "/takes", token=tok)
        assert st == 200 and len(j["takes"]) == 1 and j["takes"][0]["bytes"] == len(log), j
        st, j, _ = call("GET", "/takes/" + t["id"], token=tok)
        assert st == 200 and j["data"] == log and j["song_id"] == sid, j
        assert call("GET", "/takes/" + t["id"], token=tok2)[0] == 404, "takes are private"
        assert call("DELETE", "/takes/" + t["id"], token=tok)[0] == 200
        assert call("GET", "/takes/" + t["id"], token=tok)[0] == 404

        # -- bring your own key -------------------------------------------------------
        NOKEY = "not configured"
        st, j, _ = call("POST", "/ai/ask", {"prompt": "darker"})
        assert st == 503 and NOKEY in j["error"], ("server has no key", st, j)
        st, j, _ = call("POST", "/ai/ask", {"prompt": "darker"}, headers={"X-Anthropic-Key": "nope"})
        assert st == 503, "a header that is not sk-ant- is ignored"
        st, j, _ = call("POST", "/ai/ask", {"prompt": "darker"},
                        headers={"X-Anthropic-Key": "sk-ant-not-a-real-key"})
        assert st != 503 and NOKEY not in j.get("error", ""), ("BYO key must reach upstream", st, j)
        assert 400 <= st < 600, ("a bogus key fails upstream, it does not succeed", st, j)

        # -- remix lineage ------------------------------------------------------------
        st, ra, _ = call("POST", "/songs", {"title": "original", "data": song, "public": True}, token=tok)
        assert st == 200, ra
        st, rb, _ = call("POST", "/songs", {"title": "the flip", "data": song,
                                            "public": True, "remix_of": ra["id"]}, token=tok)
        assert st == 200, rb
        st, gb, _ = call("GET", "/songs/" + rb["id"])
        assert st == 200 and gb["remix_of"] and gb["remix_of"]["id"] == ra["id"], ("lineage lost", gb)
        st, ga, _ = call("GET", "/songs/" + ra["id"])
        assert st == 200 and ga["remixes"] == 1, ("the original should count its remixes", ga)
        st, bad, _ = call("POST", "/songs", {"title": "x", "data": song, "remix_of": "nope404"}, token=tok)
        assert st == 400, ("remix_of accepted a ghost", st, bad)

        # -- structural search --------------------------------------------------------
        songp = dict(song, name="patterned",
                     sections={"intro": {"bars": 16, "role": "intro",
                                         "tracks": {"kick": {"voice": "kick", "pat": "x...x...x...x..."}}},
                               "drop": {"bars": 32, "role": "drop",
                                        "tracks": {"kick": {"voice": "kick", "pat": "x...x...x...x..."},
                                                   "hat": {"voice": "hat", "pat": "..x...x...x...x."}}}})
        st, sp, _ = call("POST", "/songs", {"title": "patterned", "data": songp, "public": True}, token=tok)
        assert st == 200, sp
        st, sr, _ = call("GET", "/search?pat=" + "x...x...x...x...")
        assert st == 200 and sr["songs"] and sr["songs"][0]["hit"], ("pattern search missed", sr)
        st, sr2, _ = call("GET", "/search?pat=zzzz")
        assert st == 200 and sr2["songs"] == [], "a pattern nobody plays matches nothing"
        st, sr3, _ = call("GET", "/search?bpm=137-143")
        assert st == 200 and all(137 <= x["bpm"] <= 143 for x in sr3["songs"]), sr3
        st, sim, _ = call("GET", "/similar/" + ra["id"])
        assert st == 200 and sim["songs"] and sim["songs"][0]["why"], ("similar found nothing", sim)
        st, tree, _ = call("GET", "/songs/%s/remixes" % ra["id"])
        assert st == 200 and any(k["id"] == rb["id"] for k in tree["remixes"]), ("tree misses the flip", tree)
        st, tree2, _ = call("GET", "/songs/%s/remixes" % rb["id"])
        assert st == 200 and tree2["ancestors"] and tree2["ancestors"][0]["id"] == ra["id"], ("no ancestor", tree2)

        # -- charts + inline similar --------------------------------------------------
        st, ch, _ = call("GET", "/charts")
        assert st == 200 and "top_patterns" in ch and "bpm" in ch, ("charts shape", ch)
        assert any(mr["id"] == ra["id"] for mr in ch["most_remixed"]), ("charts miss the remixed one", ch)
        st, si, _ = call("POST", "/similar", {"data": songp})
        assert st == 200 and si["songs"] and si["songs"][0]["why"], ("inline similar found nothing", si)

        # -- telemetry: a batch in, rows out ------------------------------------------
        batch = {"sid": "sess-1", "did": "dev-1", "site": "app", "path": "/", "ref": "",
                 "events": [{"n": "prompt_submit", "t": 1.5, "p": {"text": "kick harder",
                                                                   "oontz_key": "sk-ant-nope"}},
                            {"n": "BAD NAME", "t": 2.0, "p": {}}]}
        est, ej, _ = call("POST", "/e", batch, headers={"X-Forwarded-For": "9.9.9.9, 1.2.3.4"})
        assert est == 200 and ej == {"ok": 1}, ("ingest must always say ok", est, ej)
        with sqlite3.connect(DB) as c:
            rows = c.execute("SELECT ts,cts,sid,did,site,name,props,path,ip,ua FROM events "
                             "WHERE sid='sess-1'").fetchall()
        assert len(rows) == 1, ("one good event, one bad name, got %d rows" % len(rows), rows)
        r = rows[0]
        assert r[0] > time.time() - 60 and r[1] == 1.5, ("server ts / client cts", r)
        assert r[2] == "sess-1" and r[3] == "dev-1" and r[4] == "app" and r[5] == "prompt_submit", r
        assert "kick harder" in r[6] and "sk-ant" not in r[6] and "oontz_key" not in r[6], r[6]
        assert r[8] == "1.2.3.4", ("the ip must be the proxy's last hop", r[8])
        # garbage must never be a 4xx: a client would retry the poison batch forever
        for bad in ("not json", '{"events":[{"n":"x"}]}'):
            req = urllib.request.Request(BASE + "/e", data=bad.encode(), method="POST",
                                         headers={"content-type": "application/json"})
            with OPEN(req, timeout=10) as rr:
                assert json.loads(rr.read()) == {"ok": 1}, bad
        # the server logs its own events too, so a prompt survives an ad-blocked client
        with sqlite3.connect(DB) as c:
            n = c.execute("SELECT COUNT(*) FROM events WHERE site='api' AND name='play_server'").fetchone()[0]
            na = c.execute("SELECT COUNT(*) FROM events WHERE name='ai_prompt'").fetchone()[0]
        assert n >= 1, "count_play logged no server-side event"
        assert na >= 1, "ai_ask logged no prompt"

        # -- the analysis surface: guarded, filtered, aggregated -----------------------
        assert call("GET", "/admin/summary")[0] == 404, "the admin surface answered with no key"
        assert call("GET", "/admin/summary", headers={"X-Admin-Key": "wrong"})[0] == 404, \
            "a wrong admin key must 404, not 401 - a 401 confirms there is a door"
        AK = {"X-Admin-Key": ADMIN_KEY}
        st, sm, _ = call("GET", "/admin/summary?window=30", headers=AK)
        assert st == 200 and sm["window_days"] == 30, ("summary", st, sm)
        assert any(p["text"] == "kick harder" for p in sm["top_prompts"]), sm["top_prompts"]
        assert {f["stage"] for f in sm["funnel"]} == {"land", "command", "explore", "audio",
                                                      "save", "signin", "publish"}, sm["funnel"]
        assert dict((f["stage"], f["sessions"]) for f in sm["funnel"])["command"] >= 1, sm["funnel"]
        assert any(e["name"] == "api_error" for e in sm["recent_errors"]), sm["recent_errors"]
        assert call("GET", "/admin/summary?window=99999", headers=AK)[1]["window_days"] == 365, \
            "the window is not clamped"
        st, ev, _ = call("GET", "/admin/events?name=prompt_submit&sid=sess-1&limit=5000",
                         headers=AK)
        assert st == 200 and len(ev["events"]) == 1, ("filtered rows", ev)
        assert ev["events"][0]["sid"] == "sess-1" and ev["events"][0]["ip"] == "1.2.3.4", ev
        assert call("GET", "/admin/events?name=prompt_submit'--", headers=AK)[0] == 200, \
            "a quote in a filter must be data, not SQL"

        # -- rooms: the relay forwards music between members --------------------------
        import asyncio
        async def room_relay():
            import websockets
            st_r, room, _ = call("POST", "/rooms")
            assert st_r == 200 and len(room["code"]) == 6, room
            wsu = "ws://127.0.0.1:%d/ws/room/%s" % (PORT, room["code"])
            async with websockets.connect(wsu) as a, websockets.connect(wsu) as b:
                await a.send(json.dumps({"t": "hello", "handle": "left"}))
                await b.send(json.dumps({"t": "hello", "handle": "right"}))
                await asyncio.sleep(0.1)
                # drain the hellos each side relayed to the other
                for sock in (a, b):
                    try:
                        await asyncio.wait_for(sock.recv(), 0.5)
                    except asyncio.TimeoutError:
                        pass
                await a.send(json.dumps({"t": "cmd", "line": "kick x...x...x...x..."}))
                got = json.loads(await asyncio.wait_for(b.recv(), 2))
                assert got["t"] == "cmd" and got["line"].startswith("kick") and got["from"] == "left", got
                await b.send(json.dumps({"t": "sync?"}))
                got2 = json.loads(await asyncio.wait_for(a.recv(), 2))
                assert got2["t"] == "sync?" and got2["from"] == "right", got2
        asyncio.run(room_relay())

        print("api checks pass  ·  link -> sqlite -> verify · save · publish · handle · "
              "playlist · /p/{id} · takes · remix · search/similar/tree/charts · rooms · admin summary/events · BYO key (upstream said %s)" % st)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
