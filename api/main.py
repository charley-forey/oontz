"""oontz API — accounts, song storage, the public gallery, and an AI proxy.

Deliberately small. The instrument runs entirely in the browser, so no audio ever
reaches this service. A song is a few KB of JSON, which is why hosting a gallery
of them costs almost nothing.

Auth is email plus a magic link. No passwords to leak, no OAuth to maintain, and
you can use the whole instrument without an account at all — one only buys you
storage and publishing.
"""
import os
import re
import json
import time
import hmac
import base64
import sqlite3
import hashlib
import secrets
import urllib.request
from contextlib import closing

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

DB = os.environ.get("OONTZ_DB", "/data/oontz.db")
SECRET = os.environ.get("OONTZ_SECRET", "dev-only-not-a-secret")
if SECRET == "dev-only-not-a-secret" and os.environ.get("RAILWAY_ENVIRONMENT"):
    raise SystemExit("OONTZ_SECRET is unset: every session would be forgeable. Refusing to start.")
APP_URL = os.environ.get("OONTZ_APP_URL", "https://oontz.sh")
SITE_URL = os.environ.get("OONTZ_SITE_URL", "https://oontz.music")
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
MAIL_FROM = os.environ.get("OONTZ_MAIL_FROM", "oontz <hello@oontz.sh>")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# thud/theory.py exported: the same rules the desktop AI and the grader use.
THEORY = {}
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "theory.json"),
              encoding="utf-8") as _f:
        THEORY = json.load(_f)
except (OSError, ValueError):
    pass

MAX_SONG_BYTES = 512 * 1024          # a .song is a few KB; this is generous
LINK_TTL = 900                       # magic links die in 15 minutes
SESSION_TTL = 60 * 60 * 24 * 90

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="oontz", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[APP_URL, SITE_URL, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ storage

def db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with closing(db()) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
          handle TEXT, created REAL NOT NULL, verified REAL);
        CREATE TABLE IF NOT EXISTS songs(
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL,
          data TEXT NOT NULL, bpm REAL, kkey TEXT, seconds REAL, sections INTEGER,
          public INTEGER DEFAULT 0, plays INTEGER DEFAULT 0,
          created REAL NOT NULL, updated REAL NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE INDEX IF NOT EXISTS songs_user ON songs(user_id);
        CREATE INDEX IF NOT EXISTS songs_public ON songs(public, updated DESC);
        CREATE TABLE IF NOT EXISTS links(
          token TEXT PRIMARY KEY, email TEXT NOT NULL, created REAL NOT NULL);
        """)
        c.commit()


init()


# --------------------------------------------------------------------- auth

def sign(payload):
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return "%s.%s" % (body, sig)


def unsign(token):
    try:
        body, sig = str(token).split(".", 1)
    except ValueError:
        return None
    want = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, want):
        return None
    try:
        pad = "=" * (-len(body) % 4)
        d = json.loads(base64.urlsafe_b64decode(body + pad))
    except Exception:
        return None
    if d.get("exp", 0) < time.time():
        return None
    return d


def current_user(authorization: str = Header(default="")):
    tok = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    d = unsign(tok)
    if not d or "uid" not in d:
        raise HTTPException(401, "sign in first")
    with closing(db()) as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (d["uid"],)).fetchone()
    if not row:
        raise HTTPException(401, "unknown account")
    return dict(row)


def optional_user(authorization: str = Header(default="")):
    try:
        return current_user(authorization)
    except HTTPException:
        return None


LAST_MAIL_ERROR = {"why": ""}


def send_mail(to, subject, text, html=None):
    """Resend if configured. Without a key the link comes back in the response,
    which keeps the whole flow testable before email is wired up.

    Failures are RECORDED, not swallowed. A silent false here looked exactly like
    'no key configured' and cost a diagnosis round-trip.
    """
    LAST_MAIL_ERROR["why"] = ""
    if not RESEND_KEY:
        LAST_MAIL_ERROR["why"] = "no RESEND_API_KEY"
        return False
    body = json.dumps({"from": MAIL_FROM, "to": [to], "subject": subject,
                       "text": text, "html": html or text}).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=body,
        headers={"Authorization": "Bearer " + RESEND_KEY,
                 "Content-Type": "application/json",
                 # Without an explicit UA, urllib sends "Python-urllib/3.x" and
                 # Cloudflare in front of the API answers 1010 (banned browser
                 # signature). The failure looked like a rejected key.
                 "User-Agent": "oontz/1.0 (+https://oontz.sh)",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        try:
            LAST_MAIL_ERROR["why"] = e.read().decode()[:300]
        except Exception:
            LAST_MAIL_ERROR["why"] = "HTTP %s" % e.code
        return False
    except Exception as e:
        LAST_MAIL_ERROR["why"] = "%s: %s" % (type(e).__name__, e)
        return False


# -------------------------------------------------------------------- models

class EmailIn(BaseModel):
    email: str = Field(max_length=254)


class SongIn(BaseModel):
    title: str = Field(default="untitled", max_length=120)
    data: dict
    public: bool = False


# --------------------------------------------------------------------- rate

_HITS = {}


def limit(request: Request, bucket, per_min=30):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
        (request.client.host if request.client else "?")
    now = time.time()
    key = (ip, bucket)
    hits = [t for t in _HITS.get(key, []) if now - t < 60]
    if len(hits) >= per_min:
        raise HTTPException(429, "slow down")
    hits.append(now)
    _HITS[key] = hits
    if len(_HITS) > 20000:                       # cheap sweep so this cannot grow
        for k, v in list(_HITS.items()):
            if not [t for t in v if now - t < 60]:
                _HITS.pop(k, None)


# ------------------------------------------------------------------- routes

@app.get("/health")
def health():
    """Public: the Railway healthcheck hits this. Diagnostics are in the logs, not here."""
    with closing(db()) as c:
        c.execute("SELECT 1")
    return {"ok": True, "mail": bool(RESEND_KEY), "ai": bool(ANTHROPIC_KEY)}


@app.post("/auth/request")
def auth_request(body: EmailIn, request: Request):
    limit(request, "auth", 6)
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "that does not look like an email address")
    token = secrets.token_urlsafe(32)
    with closing(db()) as c:
        c.execute("DELETE FROM links WHERE created < ?", (time.time() - LINK_TTL,))
        c.execute("INSERT INTO links(token,email,created) VALUES(?,?,?)",
                  (token, email, time.time()))
        c.commit()
    link = "%s/auth/verify?token=%s" % (os.environ.get("OONTZ_API_URL", ""), token)
    sent = send_mail(email, "your oontz sign-in link",
                     "Open this to sign in. It expires in 15 minutes.\n\n" + link)
    out = {"sent": sent, "email": email}
    if not sent:                                 # hand the link back, and say why
        out["link"] = link
        out["why"] = LAST_MAIL_ERROR["why"] or "unknown"
        out["note"] = ("email could not be sent, so here is the link directly"
                       if RESEND_KEY else
                       "email is not configured on this deployment; use this link")
    return out


@app.get("/auth/verify")
def auth_verify(token: str, request: Request):
    limit(request, "verify", 20)                 # 256-bit tokens, but no free guessing either
    with closing(db()) as c:
        row = c.execute("SELECT * FROM links WHERE token=?", (token,)).fetchone()
        if not row or time.time() - row["created"] > LINK_TTL:
            raise HTTPException(400, "that link has expired — ask for another")
        email = row["email"]
        c.execute("DELETE FROM links WHERE token=?", (token,))
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not u:
            c.execute("INSERT INTO users(email,created,verified) VALUES(?,?,?)",
                      (email, time.time(), time.time()))
            uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
        else:
            uid = u["id"]
            c.execute("UPDATE users SET verified=? WHERE id=?", (time.time(), uid))
        c.commit()
    session = sign({"uid": uid, "exp": time.time() + SESSION_TTL})
    return RedirectResponse("%s/#token=%s" % (APP_URL, session), status_code=302)


@app.get("/me")
def me(user=Depends(current_user)):
    with closing(db()) as c:
        n = c.execute("SELECT COUNT(*) n FROM songs WHERE user_id=?",
                      (user["id"],)).fetchone()["n"]
    return {"email": user["email"], "handle": user["handle"], "songs": n}


def _meta(data):
    """Pull the display fields out of a .song document, defensively."""
    try:
        secs = data.get("sections") or {}
        order = data.get("order") or []
        bpm = float(data.get("bpm") or 0)
        bars = sum(int(secs.get(n, {}).get("bars") or 0) for n in order)
        seconds = bars * 240.0 / bpm if bpm > 0 else 0.0
        return bpm, "%s %s" % (data.get("key", ""), data.get("scale", "")), \
            round(seconds, 1), len(order)
    except Exception:
        return 0.0, "", 0.0, 0


@app.post("/songs")
def save_song(body: SongIn, request: Request, user=Depends(current_user)):
    limit(request, "save", 60)
    blob = json.dumps(body.data, separators=(",", ":"))
    if len(blob.encode()) > MAX_SONG_BYTES:
        raise HTTPException(413, "that song is unusually large")
    sid = hashlib.sha1(("%s%s%s" % (user["id"], body.title, time.time()))
                       .encode()).hexdigest()[:12]
    bpm, kkey, seconds, nsec = _meta(body.data)
    now = time.time()
    with closing(db()) as c:
        row = c.execute("SELECT id FROM songs WHERE user_id=? AND title=?",
                        (user["id"], body.title)).fetchone()
        if row:                                  # same title from the same user updates
            sid = row["id"]
            c.execute("""UPDATE songs SET data=?,bpm=?,kkey=?,seconds=?,sections=?,
                         public=?,updated=? WHERE id=?""",
                      (blob, bpm, kkey, seconds, nsec, int(body.public), now, sid))
        else:
            c.execute("""INSERT INTO songs(id,user_id,title,data,bpm,kkey,seconds,
                         sections,public,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                      (sid, user["id"], body.title, blob, bpm, kkey, seconds, nsec,
                       int(body.public), now, now))
        c.commit()
    return {"id": sid, "title": body.title, "public": body.public,
            "url": "%s/#s=%s" % (APP_URL, sid)}


@app.get("/songs")
def my_songs(user=Depends(current_user)):
    with closing(db()) as c:
        rows = c.execute("""SELECT id,title,bpm,kkey,seconds,sections,public,plays,updated
                            FROM songs WHERE user_id=? ORDER BY updated DESC""",
                         (user["id"],)).fetchall()
    return {"songs": [dict(r) for r in rows]}


@app.get("/songs/{sid}")
def get_song(sid: str, request: Request, user=Depends(optional_user)):
    limit(request, "get", 120)
    with closing(db()) as c:
        row = c.execute("SELECT * FROM songs WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "no such song")
        if not row["public"] and (not user or user["id"] != row["user_id"]):
            raise HTTPException(403, "that song is private")
        c.execute("UPDATE songs SET plays=plays+1 WHERE id=?", (sid,))
        c.commit()
        author = c.execute("SELECT handle,email FROM users WHERE id=?",
                           (row["user_id"],)).fetchone()
    who = (author["handle"] or (author["email"].split("@")[0] + "@…")) if author else "?"
    return {"id": row["id"], "title": row["title"], "bpm": row["bpm"],
            "key": row["kkey"], "seconds": row["seconds"], "sections": row["sections"],
            "public": bool(row["public"]), "plays": row["plays"] + 1, "by": who,
            "data": json.loads(row["data"])}


@app.delete("/songs/{sid}")
def delete_song(sid: str, user=Depends(current_user)):
    with closing(db()) as c:
        r = c.execute("DELETE FROM songs WHERE id=? AND user_id=?", (sid, user["id"]))
        c.commit()
    if not r.rowcount:
        raise HTTPException(404, "no such song of yours")
    return {"deleted": sid}


@app.post("/songs/{sid}/publish")
def publish(sid: str, user=Depends(current_user)):
    with closing(db()) as c:
        row = c.execute("SELECT public FROM songs WHERE id=? AND user_id=?",
                        (sid, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "no such song of yours")
        nxt = 0 if row["public"] else 1
        c.execute("UPDATE songs SET public=?,updated=? WHERE id=?",
                  (nxt, time.time(), sid))
        c.commit()
    return {"id": sid, "public": bool(nxt),
            "url": "%s/#s=%s" % (SITE_URL, sid) if nxt else None}


@app.get("/gallery")
def gallery(sort: str = "new", limit_n: int = 40, request: Request = None):
    limit_n = max(1, min(100, limit_n))
    order = {"new": "updated DESC", "played": "plays DESC",
             "long": "seconds DESC"}.get(sort, "updated DESC")
    with closing(db()) as c:
        rows = c.execute("""SELECT s.id,s.title,s.bpm,s.kkey,s.seconds,s.sections,
                            s.plays,s.updated,u.handle,u.email
                            FROM songs s JOIN users u ON u.id=s.user_id
                            WHERE s.public=1 ORDER BY %s LIMIT ?""" % order,
                         (limit_n,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["by"] = d.pop("handle") or (d.pop("email").split("@")[0] + "@…")
        d.pop("email", None)
        out.append(d)
    return {"songs": out, "sort": sort}


class AskIn(BaseModel):
    prompt: str = Field(max_length=2000)
    state: dict = Field(default_factory=dict)


@app.post("/ai/ask")
def ai_ask(body: AskIn, request: Request):
    """Proxy so no API key ever reaches the browser. Returns command lines only."""
    limit(request, "ai", 12)
    if not ANTHROPIC_KEY:
        raise HTTPException(503, "the AI helper is not configured on this deployment")
    system = (
        "You control 'oontz', a terminal techno instrument. Reply with ONLY bare "
        "command lines, one per line, no prose, no markdown, no backticks.\n"
        "Patterns: x=hit X=accent .=rest, any length (5 steps against 16 is "
        "polymeter). Notes: a1 f#2, ~ slides, ! accents.\n"
        "Commands: kick|hat|oh|clap|snare|perc <pattern>; bass|stab <notes>; "
        "bpm N; swing N; gain <track> N; pan <track> -1..1; filter <track> "
        "lp|hp|bp <hz> [res R]; sidechain <track> 0..1; voice <track> <voice>; "
        "track add <name> [voice]; fx <track|master> <effect> [k v]; "
        "style <name>; melody <track> <root> <scale> <len>; euc <track> k n; "
        "compose <style> <minutes> <curve>; ramp <track>.<param> <lo> <hi> over <bars>.\n"
        "If the state lists `commands`, use only verbs from that list - the client "
        "rejects anything else. Prefer few, decisive lines.\n"
        + ("What makes a track work - decide with it, and it is what `grade` checks:\n"
           + THEORY["prompt"] + "\n" if THEORY.get("prompt") else "")
        + "Current state:\n" + json.dumps(body.state)[:4000])
    payload = json.dumps({
        "model": "claude-sonnet-5",
        "max_tokens": 700,
        "system": system,
        "messages": [{"role": "user", "content": body.prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        raise HTTPException(502, "the AI helper is unreachable right now (%s)" % type(e).__name__)
    text = "".join(b.get("text", "") for b in data.get("content", []))
    lines = [l.strip() for l in text.splitlines() if l.strip()
             and not l.strip().startswith(("#", "`"))]
    return {"commands": lines[:24], "raw": text}


@app.exception_handler(HTTPException)
def http_err(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
