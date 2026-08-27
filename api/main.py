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
import functools
import threading
import urllib.request
from contextlib import closing

from fastapi import (FastAPI, HTTPException, Depends, Header, Request, Form,
                     WebSocket, WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
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

# oontz/theory.py exported: the same rules the desktop AI and the grader use.
THEORY = {}
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "theory.json"),
              encoding="utf-8") as _f:
        THEORY = json.load(_f)
except (OSError, ValueError):
    pass

MAX_SONG_BYTES = 512 * 1024          # a .song is a few KB; this is generous
# Anonymous shares. ANON_UID owns them until somebody claims them; it is a real row so
# the NOT NULL user_id and its foreign key both still hold, and no migration is needed.
ANON_UID = 0
# The escape hatch. Flip this to 0 and anonymous shares become reachable-by-link but
# unlisted (public=2), which every gallery/search/charts query filters out - a spam
# wave can be contained with an env var instead of a deploy.
ANON_PUBLIC = os.environ.get("OONTZ_ANON_PUBLIC", "1") == "1"
MAX_TAKE_BYTES = 64 * 1024           # a take is the command log, not audio
LINK_TTL = 900                       # magic links die in 15 minutes
SESSION_TTL = 60 * 60 * 24 * 90

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HANDLE_RE = re.compile(r"^[a-z0-9_]{3,24}$")

app = FastAPI(title="oontz", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[APP_URL, SITE_URL, "http://localhost:3000", "http://localhost:5173"],
    # NOT every *.up.railway.app - that is any Railway user's deployment. Ours.
    allow_origin_regex=r"https://(130v5d2f|g1p1gota|6nb6dlqp|api-production-68c09)\.up\.railway\.app"
                       r"|http://localhost:\d+",
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


EVENT_DAYS = float(os.environ.get("OONTZ_EVENT_DAYS", "180"))


def prune_events():
    """Retention, enforced by deletion rather than by a promise in a privacy page.
    # ponytail: SQLite single-writer + a 5GB volume; pointer samples are the volume
    # driver. Move events to Postgres if inserts exceed ~1M/day or WAL contention
    # shows up in /health latency.
    """
    try:
        with closing(db()) as c:
            c.execute("DELETE FROM events WHERE ts < ?", (time.time() - EVENT_DAYS * 86400,))
            c.commit()
    except sqlite3.Error:
        pass                                     # retention must never break a request


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
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY,
          ts REAL NOT NULL,            -- server clock, authoritative
          cts REAL,                    -- client clock, for ordering within a batch
          sid TEXT NOT NULL,           -- session id (sessionStorage, 30-min idle rotation)
          did TEXT,                    -- device id (localStorage, survives sessions)
          user_id INTEGER,             -- NULL when signed out
          site TEXT NOT NULL,          -- 'app' | 'music' | 'api'
          name TEXT NOT NULL,
          props TEXT,                  -- JSON, <= 2KB
          path TEXT, ref TEXT,         -- location.pathname, document.referrer
          ip TEXT, ua TEXT);
        CREATE INDEX IF NOT EXISTS events_ts   ON events(ts DESC);
        CREATE INDEX IF NOT EXISTS events_sid  ON events(sid, ts);
        CREATE INDEX IF NOT EXISTS events_name ON events(name, ts DESC);
        CREATE INDEX IF NOT EXISTS events_user ON events(user_id, ts DESC);
        """)
        try:                                     # lineage arrived after the table did
            c.execute("ALTER TABLE songs ADD COLUMN remix_of TEXT")
        except sqlite3.OperationalError:
            pass
        try:                                     # so did anonymous sharing
            c.execute("ALTER TABLE songs ADD COLUMN claim TEXT")
        except sqlite3.OperationalError:
            pass
        # The owner of every unclaimed share. A row, not a NULL: songs.user_id is
        # NOT NULL with a foreign key, and SQLite cannot drop either in place.
        c.execute("INSERT OR IGNORE INTO users(id,email,created) VALUES(?,?,?)",
                  (ANON_UID, "anon@oontz.invalid", time.time()))
        c.commit()
    prune_events()


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
    # Which song this IS, when re-sharing one you already own. Identity used to be
    # the title, which meant two tracks called "warehouse" were one track, and the
    # second share silently replaced the first - including under links already
    # handed out. Omit it and you get a new song, which is the safe default.
    id: str | None = Field(default=None, max_length=32)


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


def client_ip(request: Request):
    # X-Real-IP, which Railway's edge SETS - never X-Forwarded-For, which the
    # caller can send. Reading XFF made every limit below a formality: rotate the
    # header, get a fresh bucket. There is no hop count you can trust from in here.
    if not request:
        return "?"
    return request.headers.get("x-real-ip", "").strip() or \
        (request.client.host if request.client else "?")


def limit(request: Request, bucket, per_min=30):
    ip = client_ip(request)
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


MAIL_COOLDOWN = 60                               # seconds, per email address
AI_DAY_MAX = int(os.environ.get("OONTZ_AI_DAY_MAX", "500"))
_AI_DAY = ["", 0]


def ai_budget_ok():
    """The shared key is one bill, and a per-IP limit does nothing about a botnet.
    A bring-your-own key spends the caller's money, so only the shared key counts.
    # ponytail: in-process counter, resets on deploy; a DB row if this ever runs
    # more than one replica."""
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if _AI_DAY[0] != day:
        _AI_DAY[:] = [day, 0]
    if _AI_DAY[1] >= AI_DAY_MAX:
        return False
    _AI_DAY[1] += 1
    return True


# -------------------------------------------------------------- telemetry
# Every interaction on both sites lands in one table. The client is untrusted and
# often ad-blocked, so the caps, the redaction and the important events all live
# on this side.

EV_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
EV_SECRET_KEY_RE = re.compile(r"key|token|auth|secret|password|email")
EV_ANTHROPIC_RE = re.compile(r"sk-ant-\S+")
EV_SITES = ("app", "music", "api")
MAX_EVENTS = 50
MAX_PROP_BYTES = 2 * 1024
MAX_BATCH_BYTES = 128 * 1024
_EV_INSERTS = [0]


def _redact(v):
    """The user's own Anthropic key lives in localStorage; it must never land here."""
    if isinstance(v, str):
        return EV_ANTHROPIC_RE.sub("[redacted]", v)
    if isinstance(v, dict):
        return {k: _redact(x) for k, x in v.items()
                if not EV_SECRET_KEY_RE.search(str(k).lower())}
    if isinstance(v, list):
        return [_redact(x) for x in v]
    return v


def clean_batch(body, now, ip="", ua="", user_id=None):
    """A batch of client events -> rows for executemany. Pure: no db, no request.

    Caps rather than refusals. A 4xx would make a client retry a poison batch
    forever, so an event that cannot be trusted is dropped and the rest go in.
    """
    if not isinstance(body, dict):
        return []
    sid = str(body.get("sid") or "")[:64]
    if not sid:                                  # no session, no row: sid is NOT NULL
        return []
    did = str(body.get("did") or "")[:64] or None
    site = body.get("site") if body.get("site") in EV_SITES else "app"
    path = str(body.get("path") or "")[:300] or None
    ref = str(body.get("ref") or "")[:300] or None
    rows = []
    for e in (body.get("events") or [])[:MAX_EVENTS]:
        if not isinstance(e, dict):
            continue
        name = str(e.get("n") or "")
        if not EV_NAME_RE.match(name):
            continue
        props = None
        if e.get("p") not in (None, {}):
            props = json.dumps(_redact(e["p"]), separators=(",", ":"), default=str)
            if len(props.encode()) > MAX_PROP_BYTES:   # truncated, never dropped
                props = props.encode()[:MAX_PROP_BYTES].decode("utf-8", "ignore")
        try:
            cts = float(e["t"]) if e.get("t") is not None else None
        except (TypeError, ValueError):
            cts = None
        rows.append((now, cts, sid, did, user_id, site, name, props, path, ref, ip, ua))
    return rows


EV_INSERT = """INSERT INTO events(ts,cts,sid,did,user_id,site,name,props,path,ref,ip,ua)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"""


def log_event(name, props, request=None, user_id=None, sid=None):
    """One server-side row, so a prompt survives an ad-blocked client.

    Never raises: telemetry losing a row is nothing, telemetry breaking a request
    is an outage.
    """
    try:
        rows = clean_batch({"sid": sid or "server", "site": "api",
                            "path": request.url.path if request else None,
                            "events": [{"n": name, "p": props}]},
                           time.time(), client_ip(request),
                           (request.headers.get("user-agent", "")[:300] if request else ""),
                           user_id)
        if not rows:
            return
        with closing(db()) as c:
            c.execute(EV_INSERT, rows[0])
            c.commit()
    except Exception:
        pass


@app.post("/e")
async def ingest(request: Request, user=Depends(optional_user)):
    """Batch ingest. Always {"ok":1} - a 4xx here only buys a retry loop."""
    limit(request, "e", 60)                      # 60 x 50 events is already plenty
    try:
        if int(request.headers.get("content-length") or 0) > MAX_BATCH_BYTES:
            return {"ok": 1}
        raw = await request.body()
        if len(raw) > MAX_BATCH_BYTES:
            return {"ok": 1}
        rows = clean_batch(json.loads(raw), time.time(), client_ip(request),
                           request.headers.get("user-agent", "")[:300],
                           user["id"] if user else None)
    except Exception:
        return {"ok": 1}
    if rows:
        with closing(db()) as c:
            c.executemany(EV_INSERT, rows)
            c.commit()
        _EV_INSERTS[0] += len(rows)
        if _EV_INSERTS[0] >= 1000:               # retention, paid for in small change
            _EV_INSERTS[0] = 0
            prune_events()
    return {"ok": 1}


# ---------------------------------------------------------------- analysis
# The read side of the events table: one JSON summary for a human, raw rows for
# HNIP. Aggregates are plain SQL - SQLite has json_extract, so props never has to
# be parsed in Python here.

ADMIN_KEY = os.environ.get("OONTZ_ADMIN_KEY", "")

# stage -> the event names that count as having reached it
FUNNEL = [("land", ("boot", "session_start")),
          ("command", ("prompt_submit",)),
          ("audio", ("play", "play_server")),
          ("save", ("song_save",)),
          ("signin", ("signin_request", "signin_done")),
          ("publish", ("song_publish",))]
OUTCOMES = ("cmd_result", "ai_result", "ai_accept", "ai_reject", "ai_undo")


def clamp(v, lo, hi, default):
    """Query params are whatever the caller typed. A summary that full-scans an
    unbounded table is a self-inflicted outage."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v != v:                                   # NaN compares false against everything
        return default
    return int(max(lo, min(hi, v)))


def admin_ok(supplied):
    """Unset key means the surface does not exist at all - hence 404 everywhere
    below, never 401: a 401 would confirm there is something here to guess at."""
    if not ADMIN_KEY:
        return False
    return hmac.compare_digest(str(supplied or ""), ADMIN_KEY)


def _guard(key):
    if not admin_ok(key):
        raise HTTPException(404, "Not Found")


def _in(c, names, since, expr="COUNT(DISTINCT sid)"):
    q = "SELECT %s FROM events WHERE ts>=? AND name IN (%s)" % (
        expr, ",".join("?" * len(names)))       # placeholders, never the values
    return c.execute(q, (since,) + tuple(names)).fetchone()[0]


@app.get("/admin/events")
def admin_events(since: float = 0, name: str = "", sid: str = "",
                 limit: int = 200, x_admin_key: str = Header(default="")):
    """Raw rows, newest first. `since` is epoch seconds."""
    _guard(x_admin_key)
    sql = "SELECT * FROM events WHERE ts>=?"
    args = [float(since or 0)]
    if name:
        sql += " AND name=?"
        args.append(name[:40])
    if sid:
        sql += " AND sid=?"
        args.append(sid[:64])
    sql += " ORDER BY ts DESC, id DESC LIMIT ?"
    args.append(clamp(limit, 1, 1000, 200))
    with closing(db()) as c:
        rows = c.execute(sql, args).fetchall()
    return {"events": [dict(r) for r in rows]}


@app.get("/admin/summary")
def admin_summary(window: int = 30, x_admin_key: str = Header(default="")):
    """Everything the plan asked the table to answer, as one JSON document."""
    _guard(x_admin_key)
    days = clamp(window, 1, 365, 30)
    since = time.time() - days * 86400
    with closing(db()) as c:
        q = lambda sql, a=(): [dict(r) for r in c.execute(sql, (since,) + a).fetchall()]  # noqa: E731
        totals = c.execute("""SELECT COUNT(*) events, COUNT(DISTINCT sid) sessions,
                              COUNT(DISTINCT did) devices, COUNT(DISTINCT user_id) users
                              FROM events WHERE ts>=?""", (since,)).fetchone()
        top_prompts = q("""SELECT json_extract(props,'$.text') text, COUNT(*) n,
                           COUNT(DISTINCT sid) sessions FROM events
                           WHERE ts>=? AND name='prompt_submit'
                             AND json_extract(props,'$.text') IS NOT NULL
                           GROUP BY text ORDER BY n DESC, text LIMIT 50""")
        outcomes = q("""SELECT name, json_extract(props,'$.ok') ok, COUNT(*) n
                        FROM events WHERE ts>=? AND name IN (%s)
                        GROUP BY name, ok ORDER BY n DESC"""
                     % ",".join("?" * len(OUTCOMES)), OUTCOMES)
        dau = q("""SELECT date(ts,'unixepoch') day, COUNT(*) events,
                   COUNT(DISTINCT sid) sessions, COUNT(DISTINCT did) devices
                   FROM events WHERE ts>=? GROUP BY day ORDER BY day DESC LIMIT 90""")
        wau = q("""SELECT strftime('%Y-W%W',ts,'unixepoch') week, COUNT(DISTINCT sid) sessions,
                   COUNT(DISTINCT did) devices FROM events WHERE ts>=?
                   GROUP BY week ORDER BY week DESC LIMIT 26""")
        per_device = q("""SELECT did, COUNT(DISTINCT sid) sessions FROM events
                          WHERE ts>=? AND did IS NOT NULL
                          GROUP BY did ORDER BY sessions DESC LIMIT 50""")
        # SQLite has no median; the middle row of the ordered durations is one.
        n_sess = c.execute("""SELECT COUNT(*) FROM (SELECT sid FROM events WHERE ts>=?
                              GROUP BY sid HAVING COUNT(*)>1)""", (since,)).fetchone()[0]
        median = c.execute("""SELECT max(ts)-min(ts) d FROM events WHERE ts>=?
                              GROUP BY sid HAVING COUNT(*)>1
                              ORDER BY d LIMIT 1 OFFSET ?""",
                           (since, n_sess // 2)).fetchone() if n_sess else None
        commands = q("""SELECT json_extract(props,'$.verb') verb, COUNT(*) n,
                        SUM(CASE WHEN json_extract(props,'$.ok') IN (0,'false') THEN 1 ELSE 0 END) errors
                        FROM events WHERE ts>=? AND name='cmd_result'
                        GROUP BY verb ORDER BY n DESC LIMIT 50""")
        funnel = [{"stage": s, "sessions": _in(c, names, since)} for s, names in FUNNEL]
        # "did they type a SECOND thing" is the only stage the name list cannot
        # express - it is not a new event, it is the same event happening twice in
        # one session. It is also the stage that matters most: one command is
        # curiosity, two is the product working.
        repeat = c.execute("""SELECT COUNT(*) FROM (SELECT sid FROM events
                              WHERE ts>=? AND name='prompt_submit'
                              GROUP BY sid HAVING COUNT(*)>1)""", (since,)).fetchone()[0]
        funnel.insert(2, {"stage": "explore", "sessions": repeat})
        top_ips = q("""SELECT ip, COUNT(*) n, COUNT(DISTINCT sid) sessions
                       FROM events WHERE ts>=? AND ip IS NOT NULL AND ip!=''
                       GROUP BY ip ORDER BY n DESC LIMIT 50""")
        errors = q("""SELECT id,ts,sid,site,name,props,path FROM events
                      WHERE ts>=? AND name IN ('error','api_error')
                      ORDER BY ts DESC LIMIT 50""")
    for r in commands:
        r["error_rate"] = round((r["errors"] or 0) / r["n"], 3) if r["n"] else 0.0
    # Counts do not show a drop-off; shares of the people who arrived do. Only
    # "of everyone who landed" is quoted - the stages are not nested (reaching
    # `audio` does not require `explore`), so a step-over-step ratio would read as
    # 300% conversion and mean nothing.
    landed = funnel[0]["sessions"] if funnel else 0
    for r in funnel:
        r["pct"] = round(100.0 * r["sessions"] / landed, 1) if landed else None
    return {"window_days": days, "since": since, "totals": dict(totals),
            "top_prompts": top_prompts, "prompt_outcomes": outcomes,
            "dau": dau, "wau": wau, "sessions_per_device": per_device,
            "median_session_sec": round(median["d"], 1) if median else None,
            "commands": commands, "funnel": funnel, "top_ips": top_ips,
            "recent_errors": errors}


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
        # Per-IP alone let anyone mail a stranger six times a minute from every
        # address they had. The cooldown is per EMAIL - and the response must not
        # change shape for it, or this becomes an account-existence oracle.
        recent = c.execute("SELECT 1 FROM links WHERE email=? AND created > ?",
                           (email, time.time() - MAIL_COOLDOWN)).fetchone()
        if recent:
            return {"sent": True, "email": email}
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


# secrets.token_urlsafe's alphabet, and nothing else, ever reaches the page below.
LINK_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

VERIFY_PAGE = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content=noindex>
<title>sign in to oontz</title>
<style>
 body{background:#0b0b0c;color:#e8e8ea;font:16px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
      display:grid;place-items:center;min-height:100vh;margin:0;padding:24px}
 main{max-width:30rem;text-align:center}
 h1{font-size:1.4rem;letter-spacing:.02em;margin:0 0 .6rem}
 p{color:#9a9aa2;margin:0 0 1.6rem}
 button{font:inherit;background:#e8e8ea;color:#0b0b0c;border:0;border-radius:.4rem;
        padding:.7rem 1.6rem;cursor:pointer}
 button:hover{background:#fff}
</style>
<main>
 <h1>&#9658; sign in to oontz</h1>
 <p>One click and you are in. This link is good for 15 minutes.</p>
 <form method=post action="/auth/verify">
  <input type=hidden name=token value="%s">
  <button type=submit autofocus>sign me in</button>
 </form>
</main>"""


@app.get("/auth/verify")
def auth_verify_page(token: str = ""):
    """A GET only ASKS. Corporate mail scanners, link previewers and antivirus
    proxies fetch every URL in an email before the human sees it - and a GET that
    consumed the token meant the SCANNER signed in (and had a session handed to it
    in a redirect) while the human got "that link has expired". Nothing automated
    submits a form, so the token is spent by the POST below and only by it."""
    if not LINK_TOKEN_RE.match(token or ""):
        raise HTTPException(400, "that is not a sign-in link")
    return HTMLResponse(VERIFY_PAGE % token)     # the regex above is what makes this safe


@app.post("/auth/verify")
def auth_verify(request: Request, token: str = Form(default="")):
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
    return RedirectResponse("%s/#token=%s" % (APP_URL, session), status_code=303)  # POST -> GET


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
def save_song(body: SongIn, request: Request, user=Depends(optional_user)):
    """Save a song. Signed in it is yours; signed out it is still shareable.

    Sharing used to require an account, which meant the path to a link ran: type an
    email, leave for your inbox, come back, publish. Almost nobody finishes that, and
    a share nobody completes is a share that never happens. Anonymous saves get a real
    id and a real link, and a claim token so they can be adopted later.
    """
    uid = user["id"] if user else ANON_UID
    limit(request, "save" if user else "anon", 60 if user else 6)
    blob = json.dumps(body.data, separators=(",", ":"))
    if len(blob.encode()) > MAX_SONG_BYTES:
        raise HTTPException(413, "that song is unusually large")
    title = (body.title or "untitled")[:60]      # the client caps this; the server must too
    sid = hashlib.sha1(("%s%s%s" % (uid, title, time.time()))
                       .encode()).hexdigest()[:12]
    claim = None if user else secrets.token_urlsafe(16)
    public = int(body.public) if (user or ANON_PUBLIC) else 2   # 2 = reachable by link, unlisted
    bpm, kkey, seconds, nsec = _meta(body.data)
    now = time.time()
    with closing(db()) as c:
        if body.remix_of:                        # credit must point at a real, hearable track
            src = c.execute("SELECT public,user_id FROM songs WHERE id=?",
                            (body.remix_of,)).fetchone()
            if not src or (not src["public"] and src["user_id"] != uid):
                raise HTTPException(400, "remix_of must name a public track (or one of yours)")
        # An explicit id updates that song - but ONLY for a real account. Anonymous
        # saves all share one uid and their id is public in the share link, so
        # honouring it there would let anyone who has the link overwrite the track.
        row = c.execute("SELECT id FROM songs WHERE id=? AND user_id=?",
                        (body.id, uid)).fetchone() if (user and body.id) else None
        if row:                                  # the same song, saved again
            sid = row["id"]
            c.execute("""UPDATE songs SET title=?,data=?,bpm=?,kkey=?,seconds=?,sections=?,
                         public=?,remix_of=?,updated=? WHERE id=?""",
                      (title, blob, bpm, kkey, seconds, nsec, public, body.remix_of, now, sid))
        else:
            c.execute("""INSERT INTO songs(id,user_id,title,data,bpm,kkey,seconds,
                         sections,public,remix_of,claim,created,updated)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (sid, uid, title, blob, bpm, kkey, seconds, nsec,
                       public, body.remix_of, claim, now, now))
        c.commit()
    # A public song's shareable address is the SHARE page, not the instrument.
    # /t/<id> is the only URL that carries a card and boots the track; ?song= is
    # the bare app with no meta tags at all, so every link handed out from here
    # previewed as nothing anywhere. A private song has nothing to share yet, so
    # it keeps the working link back into the instrument.
    out = {"id": sid, "title": title, "public": bool(public),
           "url": ("%s/t/%s" % (SITE_URL, sid)) if public
                  else ("%s/?song=%s" % (APP_URL, sid))}
    if claim:
        out["claim"] = claim                     # the browser keeps this to adopt it later
    return out


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
        # Reading a song is not hearing it. This counted every fetch, and the share
        # page fetches twice per crawler hit (once for the tags, once for the card) -
        # so a single link preview logged two plays and the charts were ranking
        # crawler traffic. POST /songs/{id}/play is the honest counter; it fires when
        # a listener's own gesture actually starts the audio.
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
            "public": bool(row["public"]), "plays": row["plays"], "by": who,
            "data": json.loads(row["data"])}


@app.delete("/songs/{sid}")
def delete_song(sid: str, user=Depends(current_user)):
    with closing(db()) as c:
        r = c.execute("DELETE FROM songs WHERE id=? AND user_id=?", (sid, user["id"]))
        c.commit()
    if not r.rowcount:
        raise HTTPException(404, "no such song of yours")
    return {"deleted": sid}


@app.post("/songs/{sid}/play")
def count_play(sid: str, request: Request):
    """One play, when a human actually heard it. Fire-and-forget from the client."""
    limit(request, "play", 30)
    with closing(db()) as c:
        c.execute("UPDATE songs SET plays=plays+1 WHERE id=? AND public!=0", (sid,))
        c.commit()
    log_event("play_server", {"song_id": sid}, request)
    return {"ok": True}
# ponytail: one IP can inflate a count 30/min; add a per-song cooldown if a chart
# ever decides anything that matters.


class ClaimIn(BaseModel):
    claims: list[str] = Field(default_factory=list, max_length=50)


@app.post("/songs/claim")
def claim_songs(body: ClaimIn, request: Request, user=Depends(current_user)):
    """Adopt the tracks this browser shared before it had an account.

    The token is the proof - it was returned once, to the browser that made the
    track, and it is cleared on adoption so a leaked one cannot be replayed.
    """
    limit(request, "claim", 10)
    got = 0
    with closing(db()) as c:
        for tok in body.claims[:50]:
            if not tok:
                continue
            got += c.execute("UPDATE songs SET user_id=?, claim=NULL "
                             "WHERE claim=? AND user_id=?",
                             (user["id"], tok, ANON_UID)).rowcount
        c.commit()
    return {"claimed": got}
# ponytail: claim is a full scan; index it when songs pass ~100k rows.


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
    """What the source graph knows: only possible because songs are text."""
    limit(request, "get", 60)
    with _CHARTS_LOCK:                           # see the lock, below
        return _charts(int(time.time() // 60))   # same TTL trick as the OG cards


# The cache alone still let every concurrent request past a cold bucket compute
# the same full scan: 32 at once measured p95 4.2s against p50 0.12s. One lock
# means one of them does the work and the rest get the answer.
_CHARTS_LOCK = threading.Lock()


@functools.lru_cache(maxsize=2)
def _charts(_bucket):
    """A full scan that parses every public song, so it must not run per request.
    ponytail: full scan behind a 60s cache; an index when the gallery outgrows a
    few thousand tracks."""
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
                if not p.replace(".", "").replace("-", ""):
                    continue                      # all-rest is not a pattern anyone means
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
    limit(request, "get", 60)
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
# A take is the .oontz command log of a session: text, a few KB, re-rendered by
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
def my_takes(request: Request, user=Depends(current_user)):
    limit(request, "take", 60)
    with closing(db()) as c:
        rows = c.execute("""SELECT id,song_id,name,length(data) bytes,created
                            FROM takes WHERE user_id=? ORDER BY created DESC""",
                         (user["id"],)).fetchall()
    return {"takes": [dict(r) for r in rows]}


@app.get("/takes/{tid}")
def get_take(tid: str, request: Request, user=Depends(current_user)):
    limit(request, "take", 60)
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
def public_playlists(limit_n: int = 40, request: Request = None):
    limit(request, "get", 60)
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
def set_items(pid: str, body: ItemsIn, request: Request, user=Depends(current_user)):
    """Replaces the ordered list. Every song must be yours or public."""
    limit(request, "playlist", 30)
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
    t0 = time.time()
    log_event("ai_prompt", {"prompt": body.prompt, "source": "api",
                            "state_bytes": len(json.dumps(body.state or {}))}, request)
    own = x_anthropic_key.strip()
    key = own if own.startswith("sk-ant-") else ANTHROPIC_KEY
    if key and not own and not ai_budget_ok():
        log_event("ai_result", {"ms": 0, "n_commands": 0, "ok": False,
                                "error": "budget"}, request)
        raise HTTPException(503, "the AI helper is resting for today - `key sk-ant-...` "
                                 "with your own to keep going")
    if not key:
        log_event("ai_result", {"ms": 0, "n_commands": 0, "ok": False,
                                "error": "not configured"}, request)
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
        log_event("ai_result", {"ms": int((time.time() - t0) * 1000), "n_commands": 0,
                                "ok": False, "error": type(e).__name__}, request)
        raise HTTPException(502, "the AI helper is unreachable right now (%s)" % type(e).__name__)
    text = "".join(b.get("text", "") for b in data.get("content", []))
    lines = [l.strip() for l in text.splitlines() if l.strip()
             and not l.strip().startswith(("#", "`"))]
    why = next((l.strip().lstrip("#").strip() for l in text.splitlines()
                if l.strip().startswith("#")), "")
    out = {"commands": lines[:24], "why": why[:120], "raw": text}
    log_event("ai_result", {"ms": int((time.time() - t0) * 1000),
                            "n_commands": len(out["commands"]), "ok": True, "error": ""}, request)
    return out


# ---------------------------------------------------------------- rooms
# A room is a chatroom whose messages happen to be music: the relay forwards
# JSON between members and never interprets it. The engine is deterministic and
# command-driven, so relaying command strings IS real-time collaboration.
# ponytail: in-memory, single instance - rooms die on redeploy, which is fine
# for a jam; persistence and shared-clock playback are the v2 upgrade path.

ROOMS: dict = {}                                 # code -> list[(WebSocket, handle)]
ROOM_CAP = 8
ROOM_MSG_MAX = 128 * 1024                         # a .song is 15-40KB; leave headroom


@app.post("/rooms")
def room_new(request: Request):
    limit(request, "room", 12)
    code = "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(6))
    ROOMS.setdefault(code, [])
    return {"code": code}


async def _room_send(ws, text):
    try:
        await ws.send_text(text)
    except Exception:
        pass                                     # a dead member is removed on its own recv


@app.websocket("/ws/room/{code}")
async def room_ws(ws: WebSocket, code: str):
    code = code.upper()[:6]
    # setdefault here meant every made-up code MINTED a room, so dialling random
    # codes grew the dict forever. A socket joins rooms; POST /rooms makes them.
    members = ROOMS.get(code)
    if members is None or len(members) >= ROOM_CAP:
        await ws.close(code=1008)
        return
    try:
        limit(ws, "room", 30)                    # ws has .headers and .client too
    except HTTPException:
        await ws.close(code=1008)
        return
    await ws.accept()
    me = [ws, "someone"]
    members.append(me)
    try:
        while True:
            text = await ws.receive_text()
            if len(text) > ROOM_MSG_MAX:
                continue                          # drop the message, keep the member
            try:
                msg = json.loads(text)
            except ValueError:
                continue
            if msg.get("t") == "hello":
                me[1] = str(msg.get("handle") or "someone")[:24]
            msg["from"] = me[1]
            out = json.dumps(msg)
            for other in list(members):
                if other[0] is not ws:
                    await _room_send(other[0], out)
    except WebSocketDisconnect:
        pass
    finally:
        if me in members:
            members.remove(me)
        for other in list(members):
            await _room_send(other[0], json.dumps({"t": "bye", "from": me[1]}))
        if not members:
            ROOMS.pop(code, None)


@app.exception_handler(HTTPException)
def http_err(request, exc):
    log_event("api_error", {"path": str(request.url.path), "status": exc.status_code,
                            "detail": str(exc.detail)[:200]}, request)
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
