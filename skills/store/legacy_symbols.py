"""Rename store files from the legacy ``<EXCHANGE>.<CODE>`` symbol format.

QuantSpace used to store PandaData data as ``SHSE.510300`` or ``SHFE.RB99``.
Stores now keep PandaData codes (``510300.SH``, ``RB_DOMINANT.SHF``). Parquet
files carry the symbol only in their file name, so renaming a file migrates it.
This module is the only place that knows the legacy format.

PandaData writes every futures contract with a four-digit year-month, Zhengzhou
included (``CF2509.CZC``), and refuses the exchange's own three-digit form
(``CF509.CZC``). Legacy Zhengzhou names in that three-digit form (``CZCE.CF509``)
carry no decade, so the migration takes the decade from the file's last bar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

MIGRATE_COMMAND = "uv run qs store migrate-symbols --write"

# Legacy exchange prefix -> PandaData exchange suffix.
_LEGACY_EXCHANGES = {
    "SHSE": "SH",
    "SZSE": "SZ",
    "SHFE": "SHF",
    "DCE": "DCE",
    "CZCE": "CZC",
    "CFFEX": "CFE",
    "INE": "INE",
    "GFEX": "GFE",
    "HKEX": "HK",
    "NASDAQ": "NB",
}
_FUTURES_EXCHANGES = {"SHFE", "DCE", "CZCE", "CFFEX", "INE", "GFEX"}
# Zhengzhou contract with a one-digit year and a two-digit month, such as CF509.
_CZCE_SHORT_CONTRACT = re.compile(r"([A-Za-z]{1,2})(\d)(0[1-9]|1[0-2])")
_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _short_czce_contract(symbol: str) -> re.Match[str] | None:
    prefix, _, code = symbol.partition(".")
    return _CZCE_SHORT_CONTRACT.fullmatch(code) if prefix == "CZCE" else None


def _czce_year(digit: str, as_of: date) -> str:
    """Two-digit year ending in ``digit`` within [as_of.year - 5, as_of.year + 4]."""
    decade = as_of.year - as_of.year % 10
    for year in (decade - 10 + int(digit), decade + int(digit), decade + 10 + int(digit)):
        if as_of.year - 5 <= year <= as_of.year + 4:
            return f"{year % 100:02d}"
    raise AssertionError("unreachable: one candidate always falls in the ten-year window")


def legacy_to_panda_data(symbol: str, *, as_of: date | None = None) -> str | None:
    """PandaData code for a legacy symbol, or None when ``symbol`` is not legacy.

    ``SHSE.510300`` -> ``510300.SH``; futures continuous ``SHFE.RB99`` ->
    ``RB_DOMINANT.SHF``; contracts such as ``SHFE.RB2601`` -> ``RB2601.SHF``.
    Zhengzhou's three-digit contracts get a four-digit year-month: ``CZCE.CF509``
    -> ``CF2509.CZC``. Their year is the one ending in that digit within five
    years before and four years after ``as_of``, a date the contract traded on
    (default: today in Asia/Shanghai).
    """
    prefix, dot, code = symbol.partition(".")
    if not dot or not code or prefix not in _LEGACY_EXCHANGES:
        return None
    if short := _short_czce_contract(symbol):
        product, digit, month = short.groups()
        year = _czce_year(digit, as_of or datetime.now(_TIMEZONE).date())
        code = f"{product}{year}{month}"
    elif prefix in _FUTURES_EXCHANGES and code.endswith("99") and len(code) > 2:
        code = f"{code[:-2]}_DOMINANT"
    return f"{code}.{_LEGACY_EXCHANGES[prefix]}"


def _last_bar_date(path: Path) -> date | None:
    """Date of the last bar in a store file, or None when it has no dated bars."""
    frame = pd.read_parquet(path)
    if "eob" in frame.columns:
        eob = pd.to_datetime(frame["eob"], errors="coerce")
    elif isinstance(frame.index, pd.DatetimeIndex):
        eob = frame.index
    else:
        return None
    latest = eob.max()
    return None if pd.isna(latest) else latest.date()


@dataclass(frozen=True)
class Rename:
    """One store file to rename.

    ``conflict`` when the target already exists or an earlier entry of the same
    plan renames another legacy file to it (``CZCE.CF2509`` and ``CZCE.CF509``).
    """

    source: Path
    target: Path
    conflict: bool


def _store_dirs(root: Path) -> list[Path]:
    market = root / "market"
    dirs = sorted(p for p in market.iterdir() if p.is_dir()) if market.is_dir() else []
    adj = root / "adj_factor"
    return dirs + ([adj] if adj.is_dir() else [])


def plan_symbol_migration(root: str | Path) -> list[Rename]:
    """Legacy-named Parquet files under ``market/*/`` and ``adj_factor/``.

    Three-digit Zhengzhou contracts take their decade from the file's last bar;
    a file without bars falls back to today's date.
    """
    plan = []
    for directory in _store_dirs(Path(root)):
        claimed: set[Path] = set()
        for path in sorted(directory.glob("*.parquet")):
            as_of = _last_bar_date(path) if _short_czce_contract(path.stem) else None
            new = legacy_to_panda_data(path.stem, as_of=as_of)
            if new is None:
                continue
            target = path.with_name(f"{new}.parquet")
            conflict = target.exists() or target.is_symlink() or target in claimed
            claimed.add(target)
            plan.append(Rename(path, target, conflict=conflict))
    return plan


def apply_symbol_migration(plan: list[Rename]) -> list[Rename]:
    """Rename every non-conflicting entry; return the entries renamed.

    A target that appeared after planning is never overwritten either.
    """
    done = []
    for item in plan:
        if item.conflict or item.target.exists() or item.target.is_symlink():
            continue
        item.source.rename(item.target)
        done.append(item)
    return done


def legacy_hint(directory: Path) -> str:
    """A migration hint when ``directory`` still holds legacy-named files."""
    if directory.is_dir() and any(
        legacy_to_panda_data(path.stem) for path in directory.glob("*.parquet")
    ):
        return (
            f" {directory} still has files named in the legacy format (such as SHSE.510300); "
            f"run `{MIGRATE_COMMAND}` to rename them to PandaData codes."
        )
    return ""
