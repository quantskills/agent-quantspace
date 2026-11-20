"""Rename store files from the legacy ``<EXCHANGE>.<CODE>`` symbol format.

QuantSpace used to store PandaData data as ``SHSE.510300`` or ``SHFE.RB99``.
Stores now keep PandaData codes (``510300.SH``, ``RB_DOMINANT.SHF``). Parquet
files carry the symbol only in their file name, so renaming a file migrates it.
This module is the only place that knows the legacy format.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def legacy_to_panda_data(symbol: str) -> str | None:
    """PandaData code for a legacy symbol, or None when ``symbol`` is not legacy.

    ``SHSE.510300`` -> ``510300.SH``; futures continuous ``SHFE.RB99`` ->
    ``RB_DOMINANT.SHF``; contracts such as ``SHFE.RB2601`` -> ``RB2601.SHF``.
    """
    prefix, dot, code = symbol.partition(".")
    if not dot or not code or prefix not in _LEGACY_EXCHANGES:
        return None
    if prefix in _FUTURES_EXCHANGES and code.endswith("99") and len(code) > 2:
        code = f"{code[:-2]}_DOMINANT"
    return f"{code}.{_LEGACY_EXCHANGES[prefix]}"


@dataclass(frozen=True)
class Rename:
    """One store file to rename; ``conflict`` when the target already exists."""

    source: Path
    target: Path
    conflict: bool


def _store_dirs(root: Path) -> list[Path]:
    market = root / "market"
    dirs = sorted(p for p in market.iterdir() if p.is_dir()) if market.is_dir() else []
    adj = root / "adj_factor"
    return dirs + ([adj] if adj.is_dir() else [])


def plan_symbol_migration(root: str | Path) -> list[Rename]:
    """Legacy-named Parquet files under ``market/*/`` and ``adj_factor/``."""
    plan = []
    for directory in _store_dirs(Path(root)):
        for path in sorted(directory.glob("*.parquet")):
            new = legacy_to_panda_data(path.stem)
            if new is None:
                continue
            target = path.with_name(f"{new}.parquet")
            plan.append(Rename(path, target, conflict=target.exists() or target.is_symlink()))
    return plan


def apply_symbol_migration(plan: list[Rename]) -> list[Rename]:
    """Rename every non-conflicting entry; return the entries renamed."""
    done = []
    for item in plan:
        if item.conflict or item.target.exists():
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
