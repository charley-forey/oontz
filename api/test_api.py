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
            return r.status, json.loads(r.read() or b"{}"), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            j = json.loads(raw or b"{}")
        except ValueError:
            j = {"raw": raw.decode(errors="replace")}
        return e.code, j, dict(e.headers)


def sign_in(email):
    st, j, _ = call("POST", "/auth/request", {"email": email})
    assert st == 200 and j["sent"] is False and "link" in j, ("request link", st, j)
    with sqlite3.connect(DB) as c:
        tok = c.execute("SELECT token FROM links WHERE email=?", (email,)).fetchone()[0]
    st, j, h = call("GET", "/auth/verify?token=" + tok)
    loc = h.get("Location") or h.get("location") or ""
    assert st == 302 and "#token=" in loc, ("verify", st, j, h)
    return loc.split("#token=")[1]


def main():
    env = dict(os.environ, OONTZ_DB=DB, OONTZ_API_URL=BASE, OONTZ_SITE_URL="https://oontz.music",
               ANTHROPIC_API_KEY="", RESEND_API_KEY="", RAILWAY_ENVIRONMENT="")
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
        assert call("GET", "/songs/" + sid)[0] == 403, "private song must be 403 to strangers"
        st, g, _ = call("GET", "/songs/" + sid, token=tok)
        assert st == 200 and g["bpm"] == 140 and g["sections"] == 2 and g["seconds"] == round(48 * 240 / 140, 1), g
        st, p, _ = call("POST", "/songs/%s/publish" % sid, token=tok)
        assert st == 200 and p["public"] is True and p["url"].endswith("#s=" + sid), p

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

        # -- takes --------------------------------------------------------------------
        log = "# thud session\nbpm 140\nkick x...x...x...x...\nbass a1 . a1~ c2\n"
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

        print("api checks pass  ·  link -> sqlite -> verify · save · publish · handle · "
              "playlist · /p/{id} · takes · BYO key (upstream said %s)" % st)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
