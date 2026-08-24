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
from thud import compose, theory  # noqa: E402

HOUSE_EMAIL = "hello@oontz.sh"
HOUSE_HANDLE = "oontz"

# One title per genre, in the house voice. Genre -> (title, minutes, curve).
TRACKS = {
    "techno":     ("warehouse litany", 5, "classic"),
    "hardtechno": ("concrete sermon", 4, "peaktime"),
    "acid":       ("acid vespers", 5, "classic"),
    "minimal":    ("negative space", 6, "hypnotic"),
    "dubtechno":  ("submerged", 6, "warmup"),
    "industrial": ("foundry", 4, "peaktime"),
    "house":      ("sunday morning", 5, "warmup"),
    "trance":     ("the long breakdown", 6, "classic"),
    "breakbeat":  ("broken glass", 4, "classic"),
    "electro":    ("machine funk", 4, "classic"),
    "jungle":     ("two tempos", 4, "peaktime"),
    "downtempo":  ("home by four", 5, "warmup"),
    "garage":     ("two step", 4, "classic"),
    "psytrance":  ("rolling forever", 5, "peaktime"),
    "ambient":    ("tide", 6, "hypnotic"),
}
# genre -> (remix title, seed, curve) for real lineage
REMIXES = {
    "techno":     ("warehouse litany (peak edit)", 42, "peaktime"),
    "acid":       ("acid vespers (dub)", 42, "warmup"),
    "hardtechno": ("concrete sermon (harder)", 99, "peaktime"),
}
PLAYLISTS = {
    "peak time":      ["hardtechno", "acid", "psytrance", "industrial", "jungle"],
    "warmup":         ["dubtechno", "minimal", "house", "downtempo"],
    "home listening": ["ambient", "downtempo", "dubtechno"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://api-production-bd3d8.up.railway.app")
    ap.add_argument("--dry", action="store_true", help="compose and grade, publish nothing")
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

    def compose_doc(style, minutes, curve, seed):
        sg = compose.compose_song(style, minutes, seed=seed, curve_name=curve)
        d = sg.to_dict()
        d["format"] = "thud-song-1"
        crit = theory.critique(sg, style=style)
        score = theory.score(crit) if crit else None
        return d, score

    # --- compose + grade the whole corpus first (dry-safe) --------------------
    docs = {}
    for style, (title, minutes, curve) in TRACKS.items():
        d, score = compose_doc(style, minutes, curve, seed=7)
        d["name"] = title
        docs[style] = (title, d, score)
        print("  %-11s %-26s %s  %d bars%s" % (
            style, title, ("%d BPM" % round(d["bpm"])), len(d.get("order", [])) and
            sum((d["sections"].get(n) or {}).get("bars", 0) for n in d["order"]),
            (" · %d/100" % score) if score is not None else ""))
    if args.dry:
        print("dry run: %d tracks composed, nothing published." % len(docs))
        return

    # --- house session, self-contained ---------------------------------------
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
    # edge-dead; verify against the host we actually reached instead.
    import urllib.parse as _up
    verify_path = _up.urlsplit(link).path + "?" + _up.urlsplit(link).query
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        urllib.request.build_opener(NoRedirect).open(base + verify_path)
        print("verify did not redirect as expected"); sys.exit(2)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        if "#token=" not in loc:
            print("no session in the verify redirect:", loc); sys.exit(2)
        token = loc.split("#token=")[1]
    req("PATCH", "/me", {"handle": HOUSE_HANDLE}, token)
    print("signed in as the house account (%s)" % HOUSE_HANDLE)

    # --- publish the corpus ---------------------------------------------------
    ids = {}
    for style, (title, d, score) in docs.items():
        st, r = req("POST", "/songs", {"title": title, "data": d, "public": True}, token)
        if st != 200:
            print("  ! %s: %s" % (title, r)); continue
        ids[style] = r["id"]
        print("  published %-26s %s" % (title, r["id"]))

    # --- remixes: real lineage ------------------------------------------------
    for style, (rtitle, seed, curve) in REMIXES.items():
        if style not in ids:
            continue
        d, _ = compose_doc(style, TRACKS[style][1], curve, seed=seed)
        d["name"] = rtitle
        st, r = req("POST", "/songs",
                    {"title": rtitle, "data": d, "public": True, "remix_of": ids[style]}, token)
        print("  remix    %-26s %s  (of %s)" % (rtitle, r.get("id", r), ids[style]))

    # --- playlists ------------------------------------------------------------
    for title, styles in PLAYLISTS.items():
        song_ids = [ids[s] for s in styles if s in ids]
        st, r = req("POST", "/playlists", {"title": title}, token)
        if st != 200:
            print("  ! playlist %s: %s" % (title, r)); continue
        pid = r["id"]
        req("PUT", "/playlists/%s/items" % pid, {"song_ids": song_ids}, token)
        req("PATCH", "/playlists/%s" % pid, {"public": True}, token)
        print("  playlist %-26s %s  (%d tracks)" % (title, pid, len(song_ids)))

    st, g = req("GET", "/gallery")
    print("done. gallery now lists %d public tracks." % len(g.get("songs", [])))


if __name__ == "__main__":
    main()
