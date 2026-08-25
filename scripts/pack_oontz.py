"""Zip oontz/ and songs/ for the browser: `python scripts/pack_oontz.py`.
The selftest fails when web/app/py/oontz.zip is stale."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from oontz import web                                   # noqa: E402

print(web.pack())
