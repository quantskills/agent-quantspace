"""Portable helpers for tests that run child processes: the ``qs`` script and UTF-8 I/O.

Windows installs console scripts as ``Scripts\\qs.exe`` and decodes pipes with the locale
codec (GBK on Chinese Windows), so tests never assume ``bin/qs`` or ``text=True`` alone.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Keyword arguments for subprocess.run: decode the child's output as UTF-8 text.
UTF8_TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}


def qs_script() -> Path | None:
    """The ``qs`` console script installed next to the running interpreter, or ``None``."""
    directory = Path(sys.executable).parent
    for name in ("qs", "qs.exe"):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def utf8_env(base: dict | None = None, **extra: str) -> dict:
    """A child environment (default: this process's) that makes Python I/O use UTF-8."""
    return {
        **(os.environ if base is None else base),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        **extra,
    }
