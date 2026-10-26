"""Small stdlib compatibility helpers for Python 3.7+.

Do not monkey-patch pathlib globally. Keep compatibility work isolated so the
same Core and UI run on Python 3.7 and on supported newer versions.
"""
from __future__ import annotations

from pathlib import Path


def unlink_missing_ok(path: Path) -> None:
    """Equivalent to Path.unlink(missing_ok=True), which was added in 3.8."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass
