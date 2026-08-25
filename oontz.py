#!/usr/bin/env python3
"""Shim so `python oontz.py` still works. The instrument lives in oontz/."""
from oontz.__main__ import main

if __name__ == "__main__":
    main()
