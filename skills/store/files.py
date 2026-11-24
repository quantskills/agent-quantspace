"""Whole-file replacement that readers never see half done, on macOS, Linux and Windows."""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

# Windows refuses to replace a file that another process (a reader, an antivirus scan) holds
# open; such holds last milliseconds, so a replace is retried for about two seconds.
REPLACE_RETRIES = 20
REPLACE_WAIT_SECONDS = 0.1


def replace_file(
    source: str | Path,
    target: str | Path,
    *,
    retries: int = REPLACE_RETRIES,
    wait: float = REPLACE_WAIT_SECONDS,
    sleep: Callable[[float], object] = time.sleep,
) -> None:
    """``os.replace``, retried while Windows reports the target as in use."""
    for attempt in range(retries + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == retries:
                raise
            sleep(wait)


def write_parquet_atomic(frame: pd.DataFrame, path: str | Path, **options) -> Path:
    """Write ``frame`` to a temporary file next to ``path``, then :func:`replace_file` it.

    A reader sees the old file or the new one, never a partial write; ``options`` go to
    ``DataFrame.to_parquet``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".parquet", dir=path.parent)
    os.close(fd)
    try:
        frame.to_parquet(temporary, **options)
        replace_file(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


__all__ = ["REPLACE_RETRIES", "REPLACE_WAIT_SECONDS", "replace_file", "write_parquet_atomic"]
