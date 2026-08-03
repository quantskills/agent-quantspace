"""Workspace path resolution shared by data, report, and runtime entrypoints."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def find_workspace_root(start: str | Path | None = None) -> Path:
    """Find the QuantSpace workspace without mutating the filesystem."""
    configured = os.getenv("QUANTSPACE_WORKSPACE_ROOT")
    if configured:
        return _resolved(configured)

    current = _resolved(start or Path.cwd())
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "skills").is_dir():
            return candidate

    # Development fallback for direct imports from an uninstalled source tree.
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class WorkspacePaths:
    workspace_root: Path
    data_root: Path
    reports_root: Path


def resolve_workspace_paths(
    *,
    workspace_root: str | Path | None = None,
    data_root: str | Path | None = None,
    reports_root: str | Path | None = None,
) -> WorkspacePaths:
    """Resolve workspace-owned paths with explicit values and env vars first."""
    root = _resolved(workspace_root) if workspace_root else find_workspace_root()
    data = _resolved(data_root or os.getenv("QUANTSPACE_DATA_ROOT") or root / "data")
    reports = _resolved(reports_root or os.getenv("QUANTSPACE_REPORTS_ROOT") or root / "reports")
    return WorkspacePaths(workspace_root=root, data_root=data, reports_root=reports)


__all__ = ["WorkspacePaths", "find_workspace_root", "resolve_workspace_paths"]
