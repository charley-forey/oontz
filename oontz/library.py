"""The library: what you made, and what mixes with what.

An index cached on file mtime, so the deck browser can ask it every frame without
re-parsing anything. Compatibility scores always come with reasons, because the
point is to teach you why two tracks work, not just to rank them.
"""
import os
import json
import glob
import time

from .contracts import COMMANDS, ANALYSERS

DIR = "songs"
INDEX = os.path.join(DIR, "library.json")
PLAYLISTS = os.path.join(DIR, "playlists.json")

_CACHE = {"at": 0.0, "entries": {}}
CACHE_TTL = 2.0                                  # seconds; the browser polls hard


def _hm():
    try:
        from . import harmony
        return harmony
    except ImportError:
        return None


def _read_song(path):
    from . import song as sm
    sg = sm.Song.load(path)
    hm = _hm()
    energies = [e for _n, e, _b in sg.energy_curve()] or [0.5]
    return {"name": sg.name or os.path.splitext(os.path.basename(path))[0], "path": path,
            "format": "song", "bpm": round(sg.bpm, 2), "key": sg.key,
            "scale": sg.scale, "camelot": hm.camelot(sg.key, sg.scale) if hm else "",
            "seconds": round(sg.seconds(), 1), "bars": sg.total_bars(),
            "sections": len(sg.order), "peak_energy": round(max(energies), 2),
            "mean_energy": round(sum(energies) / len(energies), 2),
            "mtime": os.path.getmtime(path), "fingerprint": sg.fingerprint()}


def _read_oontz(path):
    """A v2 command-log session. Cheap to parse - just read the header lines."""
    bpm, name = 132.0, os.path.splitext(os.path.basename(path))[0]
    try:
        for line in open(path, encoding="utf-8"):
            if line.startswith("bpm "):
                bpm = float(line.split()[1])
                break
    except Exception:
        pass
    return {"name": name, "path": path, "format": "oontz", "bpm": round(bpm, 2),
            "key": "a", "scale": "minor", "camelot": "8A", "seconds": 0.0,
            "bars": 0, "sections": 1, "peak_energy": 0.7, "mean_energy": 0.7,
            "mtime": os.path.getmtime(path), "fingerprint": ""}


def scan(force=False):
    """Index songs/. Keeps user data (rating, tags) across rescans."""
    if not force and time.time() - _CACHE["at"] < CACHE_TTL and _CACHE["entries"]:
        return _CACHE["entries"]
    old = _CACHE["entries"] or _load_index()
    out = {}
    for path in sorted(glob.glob(os.path.join(DIR, "*.song")) +
                       glob.glob(os.path.join(DIR, "*.oontz"))):
        key = os.path.basename(path)
        prev = old.get(key)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if prev and abs(prev.get("mtime", -1) - mtime) < 1e-6:
            out[key] = prev                      # unchanged: keep it, ratings and all
            continue
        try:
            e = _read_song(path) if path.endswith(".song") else _read_oontz(path)
        except Exception as exc:
            e = {"name": key, "path": path, "format": "broken", "bpm": 0.0,
                 "key": "", "scale": "", "camelot": "", "seconds": 0.0, "bars": 0,
                 "sections": 0, "peak_energy": 0.0, "mean_energy": 0.0,
                 "mtime": mtime, "fingerprint": "", "error": str(exc)}
        if prev:                                 # user data survives a re-read
            for k in ("rating", "tags", "plays"):
                if k in prev:
                    e[k] = prev[k]
        e.setdefault("rating", 0)
        e.setdefault("tags", [])
        e.setdefault("plays", 0)
        out[key] = e
    _CACHE["entries"], _CACHE["at"] = out, time.time()
    _save_index(out)
    return out


def _load_index():
    try:
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_index(entries):
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(INDEX, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=1, sort_keys=True)
    except Exception:
        pass


def all_songs():
    return sorted(scan().values(), key=lambda e: e["name"].lower())


def get(name):
    for e in scan().values():
        if e["name"] == name or os.path.splitext(os.path.basename(e["path"]))[0] == name:
            return e
    return None


def search(query=""):
    """Text plus filters: `bpm:130-140 key:8A tag:peak rating:>3 dark`"""
    entries = all_songs()
    words = []
    for tok in str(query).split():
        if ":" not in tok:
            words.append(tok.lower())
            continue
        field, _s, val = tok.partition(":")
        field = field.lower()
        if field == "bpm" and "-" in val:
            lo, _d, hi = val.partition("-")
            try:
                entries = [e for e in entries if float(lo) <= e["bpm"] <= float(hi)]
            except ValueError:
                pass
        elif field == "bpm":
            try:
                entries = [e for e in entries if abs(e["bpm"] - float(val)) < 1.0]
            except ValueError:
                pass
        elif field == "key":
            v = val.upper()
            entries = [e for e in entries
                       if e["camelot"].upper() == v or e["key"].lower() == val.lower()]
        elif field == "tag":
            entries = [e for e in entries if val.lower() in
                       [t.lower() for t in e.get("tags", [])]]
        elif field == "rating":
            try:
                if val.startswith(">"):
                    entries = [e for e in entries if e.get("rating", 0) > float(val[1:])]
                elif val.startswith("<"):
                    entries = [e for e in entries if e.get("rating", 0) < float(val[1:])]
                else:
                    entries = [e for e in entries if e.get("rating", 0) == float(val)]
            except ValueError:
                pass
    for wd in words:
        entries = [e for e in entries if wd in e["name"].lower()
                   or wd in " ".join(e.get("tags", [])).lower()]
    return entries


# ------------------------------------------------------------ compatibility

def compatibility(a, b):
    """(score 0..1, reasons). Always returns at least one reason."""
    if not a or not b:
        return 0.0, ["one of them is missing"]
    reasons = []
    hm = _hm()
    if hm and a.get("key") and b.get("key"):
        kd = hm.key_distance(a["key"], a.get("scale", "minor"),
                             b["key"], b.get("scale", "minor"))
        if kd == 0:
            reasons.append("same key (%s)" % (a.get("camelot") or a["key"]))
        elif kd <= 1:
            reasons.append("neighbouring keys, %s to %s" %
                           (a.get("camelot"), b.get("camelot")))
        else:
            reasons.append("keys clash (%s vs %s)" % (a.get("camelot"), b.get("camelot")))
    else:
        kd = 2.0
        reasons.append("key unknown, treated as neutral")

    ref = max(1.0, a.get("bpm") or 1.0)
    pct = abs((b.get("bpm") or 0) - ref) / ref * 100.0
    if pct < 3:
        reasons.append("%.1f BPM apart, easy" % abs((b.get("bpm") or 0) - ref))
    elif pct < 6:
        reasons.append("%.0f%% tempo stretch, workable" % pct)
    else:
        reasons.append("%.0f%% tempo gap, a stretch" % pct)

    de = (b.get("peak_energy", 0.5) - a.get("peak_energy", 0.5))
    if de >= 0.05:
        reasons.append("energy rises")
    elif de <= -0.2:
        reasons.append("energy drops sharply")
    else:
        reasons.append("energy holds")

    score = 1.0
    score -= min(1.0, kd * 0.22)
    score -= min(0.5, pct / 12.0)
    score -= 0.15 if de <= -0.2 else 0.0
    return max(0.0, min(1.0, score)), reasons


def suggest_next(current, pool=None, n=5):
    pool = pool if pool is not None else all_songs()
    cur = current if isinstance(current, dict) else get(current)
    out = []
    for e in pool:
        if cur and e["path"] == cur["path"]:
            continue
        s, why = compatibility(cur, e)
        out.append((s, e, why))
    out.sort(key=lambda x: -x[0])
    return out[:n]


def best_order(entries):
    """A set that rises then resolves. Greedy nearest-compatible; good enough."""
    items = list(entries)
    if not items:
        return []
    items.sort(key=lambda e: e.get("mean_energy", 0.5))
    out = [items.pop(0)]
    while items:
        s, e, _w = max(((compatibility(out[-1], x)[0], x, None) for x in items),
                       key=lambda t: t[0])
        out.append(e)
        items.remove(e)
    return out


# ----------------------------------------------------------------- playlists

def _load_pl():
    try:
        with open(PLAYLISTS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_pl(d):
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(PLAYLISTS, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, sort_keys=True)
    except Exception:
        pass


def playlists():
    return _load_pl()


def pl_new(name):
    d = _load_pl()
    d.setdefault(name, [])
    _save_pl(d)
    return d[name]


def pl_add(name, song):
    d = _load_pl()
    d.setdefault(name, []).append(song)
    _save_pl(d)
    return d[name]


def pl_remove(name, song):
    d = _load_pl()
    d[name] = [s for s in d.get(name, []) if s != song]
    _save_pl(d)
    return d[name]


def pl_duration(name, overlap_bars=16):
    d = _load_pl().get(name, [])
    total = 0.0
    for s in d:
        e = get(s)
        if e:
            total += e["seconds"]
    total -= max(0, len(d) - 1) * (overlap_bars * 2.0)   # rough overlap allowance
    return max(0.0, total)


def autobuild(minutes=30, style=None, name="auto"):
    """Fill a duration with a sensible energy arc."""
    pool = [e for e in all_songs() if e["seconds"] > 10 and e["format"] == "song"]
    if style:
        pool = [e for e in pool if style.lower() in e["name"].lower()
                or style.lower() in " ".join(e.get("tags", [])).lower()] or pool
    ordered = best_order(pool)
    out, total = [], 0.0
    for e in ordered:
        if total >= minutes * 60:
            break
        out.append(e["name"])
        total += e["seconds"] - 32.0
    d = _load_pl()
    d[name] = out
    _save_pl(d)
    return out, total


def export(name, path=None):
    """A readable cue sheet: order, keys, BPMs, transitions, total time."""
    d = _load_pl().get(name, [])
    path = path or os.path.join(DIR, "%s.md" % name)
    lines = ["# %s" % name, "",
             "| # | track | bpm | key | length | into the next |",
             "|---|---|---|---|---|---|"]
    prev = None
    for i, s in enumerate(d, 1):
        e = get(s) or {}
        note = ""
        if prev is not None:
            sc, why = compatibility(prev, e)
            note = "%d%% — %s" % (int(sc * 100), "; ".join(why))
        lines.append("| %d | %s | %.1f | %s | %s | %s |" % (
            i, e.get("name", s), e.get("bpm", 0), e.get("camelot") or e.get("key", ""),
            "%d:%02d" % (int(e.get("seconds", 0)) // 60, int(e.get("seconds", 0)) % 60),
            note))
        prev = e
    total = pl_duration(name)
    lines += ["", "Total about %d:%02d." % (int(total) // 60, int(total) % 60)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------- commands

def _fmt(e):
    return "%-16s %6.1f %-4s %5s  e%.2f %s" % (
        e["name"][:16], e["bpm"], e.get("camelot") or e.get("key", ""),
        "%d:%02d" % (int(e["seconds"]) // 60, int(e["seconds"]) % 60),
        e.get("peak_energy", 0), "".join("*" for _ in range(int(e.get("rating", 0)))))


def lib_cmd(state, args):
    sub = args[0] if args else "list"
    if sub == "scan":
        e = scan(force=True)
        return "indexed %d songs" % len(e)
    if sub == "list":
        es = all_songs()
        return "  ·  ".join(_fmt(e) for e in es[:12]) if es else "songs/ is empty"
    if sub == "search":
        es = search(" ".join(args[1:]))
        return "%d match: %s" % (len(es), "  ·  ".join(e["name"] for e in es[:10]))
    if sub == "info":
        e = get(args[1]) if len(args) > 1 else None
        return _fmt(e) if e else "no such song"
    if sub == "rate" and len(args) > 2:
        e = get(args[1])
        if not e:
            return "no such song"
        e["rating"] = max(0, min(5, int(float(args[2]))))
        _save_index(_CACHE["entries"])
        return None
    if sub == "tag" and len(args) > 2:
        e = get(args[1])
        if not e:
            return "no such song"
        e.setdefault("tags", []).extend(args[2:])
        e["tags"] = sorted(set(e["tags"]))
        _save_index(_CACHE["entries"])
        return None
    return "lib scan|list|search <q>|info <name>|rate <name> 0-5|tag <name> <tags>"


def pl_cmd(state, args):
    sub = args[0] if args else "list"
    if sub == "list":
        d = playlists()
        if len(args) > 1:
            return "  ".join(d.get(args[1], [])) or "empty"
        return "  ".join("%s(%d)" % (k, len(v)) for k, v in d.items()) or "no playlists"
    if sub == "new" and len(args) > 1:
        pl_new(args[1])
        return None
    if sub == "add" and len(args) > 2:
        pl_add(args[1], args[2])
        return None
    if sub in ("rm", "remove") and len(args) > 2:
        pl_remove(args[1], args[2])
        return None
    if sub == "autobuild":
        mins = float(args[1]) if len(args) > 1 else 30
        got, total = autobuild(mins)
        return "%d tracks, about %d:%02d" % (len(got), int(total) // 60, int(total) % 60)
    if sub == "export" and len(args) > 1:
        return "wrote " + export(args[1])
    return "pl list|new <n>|add <n> <song>|rm <n> <song>|autobuild <min>|export <n>"


def next_cmd(state, args):
    """What should I play after this?"""
    cur = get(args[0]) if args else None
    if cur is None:
        try:
            from .deck import DECKS
            d = DECKS.a if DECKS.a.n > 1 else DECKS.b
            cur = get(d.title)
        except Exception:
            pass
    if cur is None:
        return "next <song>  (or load a deck first)"
    out = suggest_next(cur, n=4)
    if not out:
        return "nothing else in the library yet"
    return "  ·  ".join("%s %d%% (%s)" % (e["name"], int(s * 100), why[0])
                        for s, e, why in out)


def analyse_library(song):
    return {"library": len(scan())}


COMMANDS.update({"lib": lib_cmd, "pl": pl_cmd, "next": next_cmd})
ANALYSERS.update({"library": analyse_library})
