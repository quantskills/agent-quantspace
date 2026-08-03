from __future__ import annotations

from pathlib import Path

from skills.store.workspace import find_workspace_root, resolve_workspace_paths


def test_workspace_paths_honor_explicit_roots_without_creating_them(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    data = tmp_path / "external-data"
    reports = tmp_path / "external-reports"

    paths = resolve_workspace_paths(
        workspace_root=workspace,
        data_root=data,
        reports_root=reports,
    )

    assert paths.workspace_root == workspace.resolve()
    assert paths.data_root == data.resolve()
    assert paths.reports_root == reports.resolve()
    assert not workspace.exists()
    assert not data.exists()
    assert not reports.exists()


def test_find_workspace_root_walks_up_from_child(tmp_path: Path) -> None:
    root = tmp_path / "project"
    child = root / "nested" / "directory"
    (root / "skills").mkdir(parents=True)
    child.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    assert find_workspace_root(child) == root.resolve()
