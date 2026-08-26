"""Dump the events table as NDJSON, one event per line, for offline analysis.

The API's /admin/summary answers the questions we already know we have. This is
for the ones we don't: it hands the raw rows to HNIP (or jq, or a notebook) with
`props` already parsed back into an object, so nothing downstream has to know
that SQLite stored it as text.

    python scripts/analytics.py --db /data/oontz.db
    python scripts/analytics.py --since 1756080000 --name prompt_submit -o day.ndjson

Read-only, stdlib only, and safe to run against the live file: SQLite in WAL
mode lets a reader in while the API is writing.
"""
import argparse
import json
import os
import sqlite3
import sys
import time

COLS = "id,ts,cts,sid,did,user_id,site,name,props,path,ref,ip,ua"


def rows(db, since=0.0, name="", sid="", limit=0):
    sql = "SELECT %s FROM events WHERE ts>=?" % COLS
    args = [float(since or 0)]
    if name:                                     # parameterised: a filter is data
        sql += " AND name=?"
        args.append(name)
    if sid:
        sql += " AND sid=?"
        args.append(sid)
    sql += " ORDER BY ts, id"
    if limit:
        sql += " LIMIT ?"
        args.append(int(limit))
    c = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    c.row_factory = sqlite3.Row
    try:
        for r in c.execute(sql, args):
            d = dict(r)
            try:
                d["props"] = json.loads(d["props"]) if d["props"] else None
            except ValueError:
                pass                             # a truncated 2KB prop is still worth having
            yield d
    finally:
        c.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=os.environ.get("OONTZ_DB", "/data/oontz.db"))
    p.add_argument("--since", type=float, default=0.0,
                   help="epoch seconds, or negative for 'this many days back'")
    p.add_argument("--name", default="", help="only this event name")
    p.add_argument("--sid", default="", help="only this session")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("-o", "--out", default="", help="file to write (default stdout)")
    a = p.parse_args(argv)
    if not os.path.exists(a.db):
        p.error("no database at %s" % a.db)
    since = time.time() + a.since * 86400 if a.since < 0 else a.since
    out = open(a.out, "w", encoding="utf-8", newline="\n") if a.out else sys.stdout
    n = 0
    try:
        for d in rows(a.db, since, a.name, a.sid, a.limit):
            out.write(json.dumps(d, default=str) + "\n")
            n += 1
    finally:
        if a.out:
            out.close()
            print("%d events -> %s" % (n, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
