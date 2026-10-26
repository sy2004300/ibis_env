#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convenient entry point: python start_ibis_ui.py [--check|--workspace PATH]."""
from __future__ import print_function

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

if sys.version_info < (3, 7):
    print("IBIS Automation requires Python 3.7 or later.", file=sys.stderr)
    raise SystemExit(2)

try:
    import tkinter
except ImportError as exc:
    print("Cannot load Tkinter GUI: %s" % exc, file=sys.stderr)
    print("Select a Python environment with _tkinter, or use ibis_auto CLI.", file=sys.stderr)
    raise SystemExit(2)

try:
    import openpyxl
except ImportError as exc:
    print("Cannot import openpyxl: %s" % exc, file=sys.stderr)
    print("For Python 3.7 install: python -m pip install 'openpyxl==3.0.10'.", file=sys.stderr)
    raise SystemExit(2)

from ibis_ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
