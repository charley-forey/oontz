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
if os.environ.get("RAILWAY_ENVIRONMENT") and not os.environ.get("OONTZ_API_URL"):
    raise SystemExit("OONTZ_API_URL is unset: every magic link would be a relative URL.")
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
MAX_TAKE_BYTES = 64 * 1024           # a take is the command log, not audio
LINK_TTL = 900                       # magic links die in 15 minutes
SESSION_TTL = 60 * 60 * 24 * 90

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HANDLE_RE = re.compile(r"^[a-z0-9_]{3,24}$")

app = FastAPI(title="oontz", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[APP_URL, SITE_URL, "http://localhost:3000", "http://localhost:5173"],
    allow_origin_regex=r"https://[a-z0-9-]+\.up\.railway\.app",   # the hostnames that work when a custom domain does not
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
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
        CREATE UNIQUE INDEX IF NOT EXISTS users_handle ON users(handle);
        CREATE TABLE IF NOT EXISTS takes(
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, song_id TEXT,
          name TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE INDEX IF NOT EXISTS takes_user ON takes(user_id);
        CREATE TABLE IF NOT EXISTS playlists(
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL,
          public INTEGER DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE INDEX IF NOT EXISTS playlists_user ON playlists(user_id);
        CREATE TABLE IF NOT EXISTS playlist_items(
          playlist_id TEXT NOT NULL, pos INTEGER NOT NULL, song_id TEXT NOT NULL,
          PRIMARY KEY(playlist_id, pos));
        """)
        try:                                     # lineage arrived after the table did
            c.execute("ALTER TABLE songs ADD COLUMN remix_of TEXT")
        except sqlite3.OperationalError:
            pass
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
    remix_of: str | None = Field(default=None, max_length=32)


class MeIn(BaseModel):
    handle: str = Field(max_length=64)


class TakeIn(BaseModel):
    song_id: str | None = Field(default=None, max_length=32)
    name: str = Field(default="take", max_length=120)
    data: str


class PlaylistIn(BaseModel):
    title: str = Field(default="untitled", max_length=120)


class PlaylistPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    public: bool | None = None


class ItemsIn(BaseModel):
    song_ids: list[str] = Field(max_length=200)


# --------------------------------------------------------------------- rate

_HITS = {}


def limit(request: Request, bucket, per_min=30):
    # the LAST hop, not the first: the proxy appends, and everything before it
    # is whatever the caller decided to send
    ip = request.headers.get("x-forwarded-for", "").split(",")[-1].strip() or \
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


@app.patch("/me")
def set_handle(body: MeIn, request: Request, user=Depends(current_user)):
    limit(request, "handle", 10)
    h = body.handle.strip().lower()
    if not HANDLE_RE.match(h):
        raise HTTPException(400, "a handle is one word, 3-24 of a-z 0-9 _")
    with closing(db()) as c:
        try:
            c.execute("UPDATE users SET handle=? WHERE id=?", (h, user["id"]))
            c.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "someone already has that handle")
    return {"handle": h}


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
        if body.remix_of:                        # credit must point at a real, hearable track
            src = c.execute("SELECT public,user_id FROM songs WHERE id=?",
                            (body.remix_of,)).fetchone()
            if not src or (not src["public"] and src["user_id"] != user["id"]):
                raise HTTPException(400, "remix_of must name a public track (or one of yours)")
        row = c.execute("SELECT id FROM songs WHERE user_id=? AND title=?",
                        (user["id"], body.title)).fetchone()
        if row:                                  # same title from the same user updates
            sid = row["id"]
            c.execute("""UPDATE songs SET data=?,bpm=?,kkey=?,seconds=?,sections=?,
                         public=?,remix_of=?,updated=? WHERE id=?""",
                      (blob, bpm, kkey, seconds, nsec, int(body.public), body.remix_of, now, sid))
        else:
            c.execute("""INSERT INTO songs(id,user_id,title,data,bpm,kkey,seconds,
                         sections,public,remix_of,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (sid, user["id"], body.title, blob, bpm, kkey, seconds, nsec,
                       int(body.public), body.remix_of, now, now))
        c.commit()
    return {"id": sid, "title": body.title, "public": body.public,
            "url": "%s/?song=%s" % (APP_URL, sid)}


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
    who = (author["handle"] if author and author["handle"] else "anon")
    with closing(db()) as c:
        parent = c.execute("""SELECT s.id,s.title,u.handle FROM songs s
                              JOIN users u ON u.id=s.user_id WHERE s.id=?""",
                           (row["remix_of"],)).fetchone() if row["remix_of"] else None
        n_remixes = c.execute("SELECT COUNT(*) n FROM songs WHERE remix_of=? AND public=1",
                              (row["id"],)).fetchone()["n"]
    return {"id": row["id"], "title": row["title"], "bpm": row["bpm"],
            "remix_of": dict(parent) if parent else None, "remixes": n_remixes,
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
            "url": "%s/t/%s" % (SITE_URL, sid) if nxt else None}


# ------------------------------------------------- structural search
# Only possible because songs are source: these read the music, not metadata.
# ponytail: full scan of public songs per query - an index when the gallery
# outgrows a few thousand tracks.

def _struct(data):
    """The searchable skeleton of a .song document."""
    secs = data.get("sections") or {}
    order = data.get("order") or []
    roles = [((secs.get(n) or {}).get("role") or "") for n in order]
    pats = set()
    for n in order:
        for t, tr in (((secs.get(n) or {}).get("tracks")) or {}).items():
            p = (tr or {}).get("pat")
            if p:
                pats.add((t, p))
    return {"roles": roles, "pats": pats}


def _similarity(a, b):
    """0..1 with human reasons. Structure weighs most: a track IS its shape."""
    import difflib
    sa, sb = _struct(a), _struct(b)
    why, score = [], 0.0
    d = abs((a.get("bpm") or 0) - (b.get("bpm") or 0))
    if d <= 6:
        score += 0.25
        why.append("within %g BPM" % d)
    if a.get("key") and (a.get("key"), a.get("scale")) == (b.get("key"), b.get("scale")):
        score += 0.2
        why.append("same key")
    r = difflib.SequenceMatcher(None, sa["roles"], sb["roles"]).ratio()
    score += 0.35 * r
    if r > 0.7:
        why.append("same shape")
    shared = sa["pats"] & sb["pats"]
    if shared:
        score += min(0.2, 0.05 * len(shared))
        why.append("shares %d pattern%s" % (len(shared), "" if len(shared) == 1 else "s"))
    return round(score, 3), why


def _public_songs(c):
    return c.execute("""SELECT s.id,s.title,s.bpm,s.kkey,s.seconds,s.plays,s.data,
                        s.remix_of,u.handle FROM songs s JOIN users u ON u.id=s.user_id
                        WHERE s.public=1""").fetchall()


@app.get("/search")
def search(pat: str = "", track: str = "", bpm: str = "", key: str = "",
           limit_n: int = 20, request: Request = None):
    """Find public tracks by what they ARE: an exact pattern (optionally on one
    track), a BPM window ("140-150" or "142" meaning +-3), a key."""
    limit(request, "get", 120)
    lo = hi = None
    if bpm:
        try:
            parts = bpm.split("-")
            lo, hi = (float(parts[0]), float(parts[1])) if len(parts) == 2 else \
                     (float(parts[0]) - 3, float(parts[0]) + 3)
        except ValueError:
            raise HTTPException(400, "bpm looks like 140-150, or 142 meaning give-or-take 3")
    out = []
    with closing(db()) as c:
        for r in _public_songs(c):
            if lo is not None and not (lo <= (r["bpm"] or 0) <= hi):
                continue
            if key and (r["kkey"] or "").lower() != key.lower():
                continue
            hit = None
            if pat:
                try:
                    data = json.loads(r["data"])
                except ValueError:
                    continue
                for n in (data.get("order") or []):
                    for t, tr in ((((data.get("sections") or {}).get(n) or {}).get("tracks")) or {}).items():
                        if track and t != track:
                            continue
                        if (tr or {}).get("pat") == pat:
                            hit = "%s/%s" % (n, t)
                            break
                    if hit:
                        break
                if not hit:
                    continue
            out.append({"id": r["id"], "title": r["title"], "bpm": r["bpm"],
                        "kkey": r["kkey"], "seconds": r["seconds"], "plays": r["plays"],
                        "handle": r["handle"], "hit": hit})
            if len(out) >= max(1, min(50, limit_n)):
                break
    return {"songs": out}


@app.get("/similar/{sid}")
def similar(sid: str, limit_n: int = 10, request: Request = None):
    """More like this one - scored on structure, with the reasons said aloud."""
    limit(request, "get", 60)
    with closing(db()) as c:
        row = c.execute("SELECT data,public FROM songs WHERE id=?", (sid,)).fetchone()
        if not row or not row["public"]:
            raise HTTPException(404, "no such public song")
        target = json.loads(row["data"])
        scored = []
        for r in _public_songs(c):
            if r["id"] == sid:
                continue
            try:
                score, why = _similarity(target, json.loads(r["data"]))
            except ValueError:
                continue
            if score > 0.15:
                scored.append({"id": r["id"], "title": r["title"], "bpm": r["bpm"],
                               "kkey": r["kkey"], "handle": r["handle"],
                               "score": score, "why": why})
        scored.sort(key=lambda x: -x["score"])
    return {"songs": scored[:max(1, min(25, limit_n))]}


@app.get("/songs/{sid}/remixes")
def remix_tree(sid: str, request: Request = None):
    """The family tree: ancestors walked up, public children listed."""
    limit(request, "get", 60)
    with closing(db()) as c:
        row = c.execute("SELECT id,remix_of,public FROM songs WHERE id=?", (sid,)).fetchone()
        if not row or not row["public"]:
            raise HTTPException(404, "no such public song")
        ancestors, cur, hops = [], row["remix_of"], 0
        while cur and hops < 10:
            p = c.execute("""SELECT s.id,s.title,s.remix_of,s.public,u.handle FROM songs s
                             JOIN users u ON u.id=s.user_id WHERE s.id=?""", (cur,)).fetchone()
            if not p or not p["public"]:
                break
            ancestors.append({"id": p["id"], "title": p["title"], "handle": p["handle"]})
            cur, hops = p["remix_of"], hops + 1
        kids = c.execute("""SELECT s.id,s.title,u.handle,
                            (SELECT COUNT(*) FROM songs g WHERE g.remix_of=s.id AND g.public=1) n
                            FROM songs s JOIN users u ON u.id=s.user_id
                            WHERE s.remix_of=? AND s.public=1 ORDER BY s.updated DESC""",
                         (sid,)).fetchall()
    return {"id": sid, "ancestors": ancestors,
            "remixes": [dict(k) for k in kids]}


@app.get("/charts")
def charts(request: Request = None):
    """What the source graph knows: only possible because songs are text.
    ponytail: full scan; an index when the gallery outgrows a few thousand."""
    limit(request, "get", 60)
    from collections import Counter
    most_remixed, pat_count, pat_ex, bpm_bucket, key_count = [], Counter(), {}, Counter(), Counter()
    with closing(db()) as c:
        for r in _public_songs(c):
            if r["kkey"]:
                key_count[r["kkey"]] += 1
            if r["bpm"]:
                bpm_bucket[int(r["bpm"] // 10) * 10] += 1
            n = c.execute("SELECT COUNT(*) n FROM songs WHERE remix_of=? AND public=1",
                          (r["id"],)).fetchone()["n"]
            if n:
                most_remixed.append({"id": r["id"], "title": r["title"],
                                     "handle": r["handle"], "remixes": n})
            try:
                data = json.loads(r["data"])
            except ValueError:
                continue
            for _t, p in _struct(data)["pats"]:
                pat_count[p] += 1
                pat_ex.setdefault(p, {"id": r["id"], "title": r["title"]})
    most_remixed.sort(key=lambda x: -x["remixes"])
    top_pats = [{"pat": p, "count": n, "example": pat_ex[p]}
                for p, n in pat_count.most_common(8) if n > 1]
    return {"most_remixed": most_remixed[:10],
            "top_patterns": top_pats,
            "bpm": sorted(([b, n] for b, n in bpm_bucket.items())),
            "keys": key_count.most_common(8)}


class SimilarIn(BaseModel):
    data: dict


@app.post("/similar")
def similar_inline(body: SimilarIn, request: Request = None):
    """More like THIS unsaved song - the create-side of discovery."""
    limit(request, "get", 60)
    scored = []
    with closing(db()) as c:
        for r in _public_songs(c):
            try:
                score, why = _similarity(body.data, json.loads(r["data"]))
            except ValueError:
                continue
            if score > 0.15:
                scored.append({"id": r["id"], "title": r["title"], "bpm": r["bpm"],
                               "kkey": r["kkey"], "handle": r["handle"],
                               "score": score, "why": why})
    scored.sort(key=lambda x: -x["score"])
    return {"songs": scored[:10]}


@app.get("/gallery")
def gallery(sort: str = "new", limit_n: int = 40, request: Request = None):
    limit_n = max(1, min(100, limit_n))
    order = {"new": "updated DESC", "played": "plays DESC",
             "long": "seconds DESC"}.get(sort, "updated DESC")
    with closing(db()) as c:
        rows = c.execute("""SELECT s.id,s.title,s.bpm,s.kkey,s.seconds,s.sections,
                            s.plays,s.updated,s.remix_of,u.handle,u.email
                            FROM songs s JOIN users u ON u.id=s.user_id
                            WHERE s.public=1 ORDER BY %s LIMIT ?""" % order,
                         (limit_n,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("email", None)
        d["by"] = d["handle"] or "anon"        # never publish an address nobody offered
        d.pop("email", None)
        out.append(d)
    return {"songs": out, "sort": sort}


# -------------------------------------------------------------------- takes
# A take is the .thud command log of a session: text, a few KB, re-rendered by
# the deterministic engine wherever it is played. Never audio.

def _nid():
    return secrets.token_hex(6)


@app.post("/takes")
def save_take(body: TakeIn, request: Request, user=Depends(current_user)):
    limit(request, "take", 60)
    if len(body.data.encode()) > MAX_TAKE_BYTES:
        raise HTTPException(413, "a take is a command log; that one is too big to be one")
    tid = _nid()
    with closing(db()) as c:
        c.execute("INSERT INTO takes(id,user_id,song_id,name,data,created) VALUES(?,?,?,?,?,?)",
                  (tid, user["id"], body.song_id, body.name, body.data, time.time()))
        c.commit()
    return {"id": tid, "name": body.name, "song_id": body.song_id}


@app.get("/takes")
def my_takes(user=Depends(current_user)):
    with closing(db()) as c:
        rows = c.execute("""SELECT id,song_id,name,length(data) bytes,created
                            FROM takes WHERE user_id=? ORDER BY created DESC""",
                         (user["id"],)).fetchall()
    return {"takes": [dict(r) for r in rows]}


@app.get("/takes/{tid}")
def get_take(tid: str, user=Depends(current_user)):
    with closing(db()) as c:
        row = c.execute("SELECT * FROM takes WHERE id=? AND user_id=?",
                        (tid, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "no such take of yours")
    return dict(row)


@app.delete("/takes/{tid}")
def delete_take(tid: str, user=Depends(current_user)):
    with closing(db()) as c:
        r = c.execute("DELETE FROM takes WHERE id=? AND user_id=?", (tid, user["id"]))
        c.commit()
    if not r.rowcount:
        raise HTTPException(404, "no such take of yours")
    return {"deleted": tid}


# ---------------------------------------------------------------- playlists

def _playlist(c, pid):
    row = c.execute("""SELECT p.*, u.handle FROM playlists p JOIN users u ON u.id=p.user_id
                       WHERE p.id=?""", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "no such playlist")
    return row


def _playlist_songs(c, pid):
    rows = c.execute("""SELECT s.id,s.title,s.bpm,s.kkey,s.seconds,s.sections,s.plays,
                        s.public,u.handle FROM playlist_items i
                        JOIN songs s ON s.id=i.song_id JOIN users u ON u.id=s.user_id
                        WHERE i.playlist_id=? ORDER BY i.pos""", (pid,)).fetchall()
    return [dict(r) for r in rows]


@app.post("/playlists")
def new_playlist(body: PlaylistIn, request: Request, user=Depends(current_user)):
    limit(request, "playlist", 30)
    pid, now = _nid(), time.time()
    with closing(db()) as c:
        c.execute("INSERT INTO playlists(id,user_id,title,public,created,updated) VALUES(?,?,?,0,?,?)",
                  (pid, user["id"], body.title, now, now))
        c.commit()
    return {"id": pid, "title": body.title, "public": False}


@app.get("/playlists/public")
def public_playlists(limit_n: int = 40):
    limit_n = max(1, min(100, limit_n))
    with closing(db()) as c:
        rows = c.execute("""SELECT p.id,p.title,p.created,p.updated,u.handle,
                            (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist_id=p.id) n
                            FROM playlists p JOIN users u ON u.id=p.user_id
                            WHERE p.public=1 ORDER BY p.updated DESC LIMIT ?""",
                         (limit_n,)).fetchall()
    return {"playlists": [dict(r) for r in rows]}


@app.get("/playlists")
def my_playlists(user=Depends(current_user)):
    with closing(db()) as c:
        rows = c.execute("""SELECT p.id,p.title,p.public,p.created,p.updated,
                            (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist_id=p.id) n
                            FROM playlists p WHERE p.user_id=? ORDER BY p.updated DESC""",
                         (user["id"],)).fetchall()
    return {"playlists": [dict(r) for r in rows]}


@app.get("/playlists/{pid}")
def get_playlist(pid: str, user=Depends(optional_user)):
    with closing(db()) as c:
        row = _playlist(c, pid)
        if not row["public"] and (not user or user["id"] != row["user_id"]):
            raise HTTPException(403, "that playlist is private")
        songs = _playlist_songs(c, pid)
    return {"id": row["id"], "title": row["title"], "public": bool(row["public"]),
            "handle": row["handle"], "created": row["created"], "updated": row["updated"],
            "songs": songs}


@app.patch("/playlists/{pid}")
def patch_playlist(pid: str, body: PlaylistPatch, user=Depends(current_user)):
    with closing(db()) as c:
        row = c.execute("SELECT * FROM playlists WHERE id=? AND user_id=?",
                        (pid, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "no such playlist of yours")
        title = body.title if body.title is not None else row["title"]
        public = int(body.public) if body.public is not None else row["public"]
        c.execute("UPDATE playlists SET title=?,public=?,updated=? WHERE id=?",
                  (title, public, time.time(), pid))
        c.commit()
    return {"id": pid, "title": title, "public": bool(public),
            "url": "%s/p/%s" % (SITE_URL, pid) if public else None}


@app.delete("/playlists/{pid}")
def delete_playlist(pid: str, user=Depends(current_user)):
    with closing(db()) as c:
        r = c.execute("DELETE FROM playlists WHERE id=? AND user_id=?", (pid, user["id"]))
        if r.rowcount:
            c.execute("DELETE FROM playlist_items WHERE playlist_id=?", (pid,))
        c.commit()
    if not r.rowcount:
        raise HTTPException(404, "no such playlist of yours")
    return {"deleted": pid}


@app.put("/playlists/{pid}/items")
def set_items(pid: str, body: ItemsIn, user=Depends(current_user)):
    """Replaces the ordered list. Every song must be yours or public."""
    with closing(db()) as c:
        row = c.execute("SELECT id FROM playlists WHERE id=? AND user_id=?",
                        (pid, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "no such playlist of yours")
        for sid in body.song_ids:
            s = c.execute("SELECT public,user_id FROM songs WHERE id=?", (sid,)).fetchone()
            if not s or (not s["public"] and s["user_id"] != user["id"]):
                raise HTTPException(400, "song %s is not yours and not public" % sid)
        c.execute("DELETE FROM playlist_items WHERE playlist_id=?", (pid,))
        c.executemany("INSERT INTO playlist_items(playlist_id,pos,song_id) VALUES(?,?,?)",
                      [(pid, i, sid) for i, sid in enumerate(body.song_ids)])
        c.execute("UPDATE playlists SET updated=? WHERE id=?", (time.time(), pid))
        c.commit()
    return {"id": pid, "count": len(body.song_ids)}


@app.get("/p/{pid}")
def public_playlist(pid: str, request: Request):
    """The share URL's data. Public playlists only; 404 keeps private ones invisible.
    A song that went private after it was added is left out, not leaked."""
    limit(request, "get", 120)
    with closing(db()) as c:
        row = _playlist(c, pid)
        if not row["public"]:
            raise HTTPException(404, "no such playlist")
        songs = [s for s in _playlist_songs(c, pid) if s["public"]]
    for s in songs:
        s.pop("public", None)
    return {"id": row["id"], "title": row["title"], "handle": row["handle"],
            "created": row["created"], "songs": songs}


class AskIn(BaseModel):
    prompt: str = Field(max_length=2000)
    state: dict = Field(default_factory=dict)


def _state_text(state, cap=4000):
    """The verb list and the arrangement first, the patterns last and trimmed.

    Truncating the raw dump put `tracks` first - and one track's pattern is 128
    characters now - so the verb list at the end was always the part that got cut,
    which is precisely the part the system prompt tells the model to obey.
    """
    state = dict(state or {})
    tracks = state.pop("tracks", None)
    head = json.dumps(state)
    if isinstance(tracks, dict):
        thin = {}
        for name, tr in list(tracks.items())[:16]:
            if not isinstance(tr, dict):
                continue
            keep = {k: tr[k] for k in ("pat", "gain", "sc", "fc", "pan") if k in tr}
            pat = keep.get("pat")
            if isinstance(pat, str) and len(pat) > 32:      # one bar is enough to reason about
                keep["pat"] = pat[:16] + "…"
            if isinstance(tr.get("notes"), list):
                keep["notes"] = " ".join(str(x) for x in tr["notes"][:16])
            thin[str(name)[:24]] = keep
        head = head[:-1] + ', "tracks": ' + json.dumps(thin) + "}" if head.endswith("}") else head
    return head[:cap]


@app.post("/ai/ask")
def ai_ask(body: AskIn, request: Request, x_anthropic_key: str = Header(default="")):
    """Proxy so the shared API key never reaches the browser. Returns command lines only.

    Bring your own key: an `X-Anthropic-Key` header wins over the server key. It is
    used for this one request and never logged or stored.
    """
    limit(request, "ai", 12)
    own = x_anthropic_key.strip()
    key = own if own.startswith("sk-ant-") else ANTHROPIC_KEY
    if not key:
        raise HTTPException(503, "the AI helper is not configured on this deployment")
    system = (
        "You control 'oontz', a terminal techno instrument. Reply with ONLY bare "
        "command lines, one per line, no prose, no markdown, no backticks.\n"
        "Patterns: x=hit X=accent .=rest, any length (5 steps against 16 is "
        "polymeter). Notes: a1 f#2, ~ slides, ! accents.\n"
        "Commands: kick|hat|oh|clap|snare|perc <pattern>; bass|stab <notes>; "
        "bpm 60-220; swing 0-60; gain <track> 0-1.2 (a LINEAR multiplier, never dB - "
        "-6 would silence the track); pan <track> -1..1; filter <track> "
        "lp|hp|bp <hz> [res R]; sidechain <track> 0..1; voice <track> <voice>; "
        "track add <name> [voice]; fx <track|master> <effect> [k v]; "
        "style <name>; melody <track> <root> <scale> <len>; euc <track> k n; "
        "compose <style> <minutes> <curve>; ramp <track>.<param> <lo> <hi> over <bars>.\n"
        "You may end with ONE line starting with '# ': six words or fewer on why. "
        "If the state lists `commands`, use only verbs from that list - the client "
        "rejects anything else. Prefer few, decisive lines. Every note token is a "
        "real note (a1, f#2) or a rest (.); ~ and ! are suffixes ON a note, "
        "never tokens of their own.\n"
        + ("What makes a track work - decide with it, and it is what `grade` checks:\n"
           + THEORY["prompt"] + "\n" if THEORY.get("prompt") else "")
        + "Current state:\n" + _state_text(body.state))
    payload = json.dumps({
        "model": "claude-sonnet-5",
        "max_tokens": 700,
        "system": system,
        "messages": [{"role": "user", "content": body.prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        raise HTTPException(502, "the AI helper is unreachable right now (%s)" % type(e).__name__)
    text = "".join(b.get("text", "") for b in data.get("content", []))
    lines = [l.strip() for l in text.splitlines() if l.strip()
             and not l.strip().startswith(("#", "`"))]
    why = next((l.strip().lstrip("#").strip() for l in text.splitlines()
                if l.strip().startswith("#")), "")
    return {"commands": lines[:24], "why": why[:120], "raw": text}


@app.exception_handler(HTTPException)
def http_err(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
