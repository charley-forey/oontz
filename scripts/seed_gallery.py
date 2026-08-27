"""Seed the live gallery so both sites demonstrate themselves.

One house account, one grader-approved track per genre, three remixes for real
family trees, and three public playlists. Deterministic under fixed seeds, so a
re-run publishes the same corpus (same title from the same user updates in place).

Auth is self-contained: `/auth/request` hands the sign-in link back in the
response whenever mail can't be delivered — and Resend (onboarding@resend.dev)
refuses any address that isn't the account owner — so a house email verifies
without a human clicking anything. If a deploy ever DOES mail the link, the
script says so and stops rather than guessing.

    python scripts/seed_gallery.py [--api https://api-...] [--dry]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
from oontz import compose, theory  # noqa: E402

HOUSE_EMAIL = "hello@oontz.sh"
HOUSE_HANDLE = "oontz"

# One track per line: (style, title, minutes, curve). Two per genre, because a
# gallery with exactly one of everything reads as a feature grid, not a record
# shelf - the second one exists to be a different mood in the same room.
# Titles are written, not generated. The MUSIC is searched: every line below is
# composed at each seed in SEEDS and only the highest-scoring take is published,
# so what lands in the gallery is the best of five, not the first of one.
TRACKS = [
    ("techno",     "warehouse litany",      5, "classic"),
    ("techno",     "steel and tape",        6, "hypnotic"),
    ("hardtechno", "concrete sermon",       4, "peaktime"),
    ("hardtechno", "no encore",             4, "classic"),
    ("acid",       "acid vespers",          5, "classic"),
    ("acid",       "303 confession",        5, "peaktime"),
    ("minimal",    "negative space",        6, "hypnotic"),
    ("minimal",    "one room",              6, "warmup"),
    ("dubtechno",  "submerged",             6, "warmup"),
    ("dubtechno",  "chlorine",              7, "hypnotic"),
    ("industrial", "foundry",               4, "peaktime"),
    ("industrial", "shift change",          5, "classic"),
    ("house",      "sunday morning",        5, "warmup"),
    ("house",      "the second wind",       5, "classic"),
    ("trance",     "the long breakdown",    6, "classic"),
    ("trance",     "the last train home",   6, "hypnotic"),
    ("breakbeat",  "broken glass",          4, "classic"),
    ("breakbeat",  "cheap thrills",         4, "peaktime"),
    ("electro",    "machine funk",          4, "classic"),
    ("electro",    "cold solder",           4, "warmup"),
    ("jungle",     "two tempos",            4, "peaktime"),
    ("jungle",     "pirate radio",          4, "classic"),
    ("downtempo",  "home by four",          5, "warmup"),
    ("downtempo",  "the kitchen at six",    5, "hypnotic"),
    ("garage",     "two step",              4, "classic"),
    ("garage",     "corner shop",           4, "warmup"),
    ("psytrance",  "rolling forever",       5, "peaktime"),
    ("psytrance",  "the long way up",       6, "classic"),
    ("ambient",    "tide",                  6, "hypnotic"),
    ("ambient",    "low pressure",          7, "warmup"),
]
SEEDS = (7, 42, 99, 137, 256)     # the search space; deterministic, so a re-run agrees

# title -> (remix title, seed, curve) for real lineage
REMIXES = {
    "warehouse litany": ("warehouse litany (peak edit)", 42, "peaktime"),
    "acid vespers":     ("acid vespers (dub)",           42, "warmup"),
    "concrete sermon":  ("concrete sermon (harder)",     99, "peaktime"),
    "machine funk":     ("machine funk (electro dub)",   137, "warmup"),
}
PLAYLISTS = {
    "peak time":      ["concrete sermon", "303 confession", "rolling forever",
                       "foundry", "two tempos", "no encore"],
    "warmup":         ["submerged", "one room", "sunday morning", "home by four",
                       "cold solder", "corner shop"],
    "home listening": ["tide", "low pressure", "the kitchen at six", "chlorine",
                       "the last train home"],
}


def compose_doc(style, minutes, curve, seed):
    sg = compose.compose_song(style, minutes, seed=seed, curve_name=curve)
    d = sg.to_dict()
    d["format"] = "oontz-song-1"
    crit = theory.critique(sg, style=style)
    score = theory.score(crit) if crit else None
    return d, score


def best_doc(style, minutes, curve, seeds=SEEDS):
    """Compose the same brief at every seed and keep the take the grader likes best.

    One seed is a coin flip - the corpus used to be whatever seed 7 happened to
    produce. Searching costs seconds and is the only taste I can actually apply
    without ears, so it is the taste that gets applied.
    """
    best = None
    for seed in seeds:
        d, score = compose_doc(style, minutes, curve, seed)
        if best is None or (score or 0) > (best[1] or 0):
            best = (d, score, seed)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://api.oontz.sh")
    ap.add_argument("--dry", action="store_true", help="compose and grade, publish nothing")
    ap.add_argument("--token", help="use this session token instead of self-auth")
    args = ap.parse_args()
    base = args.api.rstrip("/")

    def req(method, path, body=None, token=None):
        r = urllib.request.Request(
            base + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"content-type": "application/json",
                     **({"authorization": "Bearer " + token} if token else {})})
        try:
            with urllib.request.urlopen(r, timeout=30) as f:
                return f.status, json.load(f)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.load(e)
            except Exception:
                return e.code, {"error": e.reason}

    # --- compose + grade the whole corpus first (dry-safe) --------------------
    docs, worst = [], (999, "")
    for style, title, minutes, curve in TRACKS:
        d, score, seed = best_doc(style, minutes, curve)
        d["name"] = title
        docs.append((title, d, score, style))
        bars = sum((d["sections"].get(n) or {}).get("bars", 0) for n in d.get("order", []))
        print("  %-11s %-24s %3d BPM  %3d bars  seed %-4d%s" % (
            style, title, round(d["bpm"]), bars, seed,
            ("  %d/100" % score) if score is not None else ""))
        if score is not None and score < worst[0]:
            worst = (score, title)
    print("  %d tracks, worst score %d (%s)" % (len(docs), worst[0], worst[1]))
    if args.dry:
        print("dry run: nothing published.")
        return

    # --- house session --------------------------------------------------------
    if args.token:
        token = args.token
        req("PATCH", "/me", {"handle": HOUSE_HANDLE}, token)
        print("using the provided session token")
        _publish(req, docs, token); return

    req("POST", "/auth/request", {"email": HOUSE_EMAIL})
    st, j = req("POST", "/auth/request", {"email": HOUSE_EMAIL})
    link = j.get("link")
    if not link:
        print("The API mailed the sign-in link instead of returning it, so this "
              "script can't complete auth on its own.\nCheck %s for a link to "
              "%s, then paste its ?token=... below is not wired — rerun once mail "
              "is off, or seed from a signed-in browser." % (HOUSE_EMAIL, HOUSE_EMAIL))
        sys.exit(2)

    # The link is built from OONTZ_API_URL (the custom domain), which may be
    # edge-dead; verify against the host we actually reached instead. And verify
    # is two steps now - a GET only shows a form, because mail scanners were
    # burning the token before the human clicked - so POST the token like a browser.
    import urllib.parse as _up
    token_q = _up.parse_qs(_up.urlsplit(link).query).get("token", [""])[0]
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    r = urllib.request.Request(base + "/auth/verify", method="POST",
                               data=_up.urlencode({"token": token_q}).encode(),
                               headers={"content-type": "application/x-www-form-urlencoded"})
    try:
        urllib.request.build_opener(NoRedirect).open(r)
        print("verify did not redirect as expected"); sys.exit(2)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        if "#token=" not in loc:
            print("no session in the verify redirect:", loc); sys.exit(2)
        token = loc.split("#token=")[1]
    req("PATCH", "/me", {"handle": HOUSE_HANDLE}, token)
    print("signed in as the house account (%s)" % HOUSE_HANDLE)
    _publish(req, docs, token)


def _publish(req, docs, token):
    """Publish the corpus, updating in place rather than minting twins.

    Identity is the song id now, not the title (a title collision used to
    silently overwrite the earlier track). So a re-run has to look up what it
    published last time and hand the id back, or every run doubles the gallery.
    """
    st, mine = req("GET", "/songs", None, token)
    known = {r["title"]: r["id"] for r in (mine or {}).get("songs", [])} if st == 200 else {}
    if known:
        print("  %d tracks already on this account - re-running updates them in place" % len(known))

    ids = {}
    for title, d, score, style in docs:
        body = {"title": title, "data": d, "public": True}
        if title in known:
            body["id"] = known[title]
        st, r = req("POST", "/songs", body, token)
        if st != 200:
            print("  ! %s: %s" % (title, r)); continue
        ids[title] = r["id"]
        print("  %-9s %-24s %s" % ("updated" if title in known else "published", title, r["id"]))

    # --- remixes: real lineage ------------------------------------------------
    src = {t: (style, mins) for style, t, mins, _c in TRACKS}
    for parent, (rtitle, seed, curve) in REMIXES.items():
        if parent not in ids or parent not in src:
            continue
        style, minutes = src[parent]
        d, _score = compose_doc(style, minutes, curve, seed=seed)
        d["name"] = rtitle
        body = {"title": rtitle, "data": d, "public": True, "remix_of": ids[parent]}
        if rtitle in known:
            body["id"] = known[rtitle]
        st, r = req("POST", "/songs", body, token)
        ids[rtitle] = r.get("id")
        print("  remix     %-24s %s  (of %s)" % (rtitle, r.get("id", r), ids[parent]))

    # --- playlists ------------------------------------------------------------
    st, pls = req("GET", "/playlists", None, token)
    have = {p["title"]: p["id"] for p in (pls or {}).get("playlists", [])} if st == 200 else {}
    for title, titles in PLAYLISTS.items():
        song_ids = [ids[t] for t in titles if ids.get(t)]
        pid = have.get(title)
        if not pid:
            st, r = req("POST", "/playlists", {"title": title}, token)
            if st != 200:
                print("  ! playlist %s: %s" % (title, r)); continue
            pid = r["id"]
        req("PUT", "/playlists/%s/items" % pid, {"song_ids": song_ids}, token)
        req("PATCH", "/playlists/%s" % pid, {"public": True}, token)
        print("  playlist  %-24s %s  (%d tracks)" % (title, pid, len(song_ids)))

    st, g = req("GET", "/gallery")
    print("done. gallery now lists %d public tracks." % len(g.get("songs", [])))


if __name__ == "__main__":
    main()
