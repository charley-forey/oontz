#!/usr/bin/env python3
"""Shim so `python thud.py` still works. The instrument lives in thud/."""
from thud.__main__ import main

if __name__ == "__main__":
    main()
