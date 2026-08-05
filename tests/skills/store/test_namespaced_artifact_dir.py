"""Minimal DataManager namespaced artifact directory helper."""

from __future__ import annotations

import pytest

from skills.store.data_manager import DataManager


def test_namespaced_artifact_dir_stays_under_factors(tmp_path) -> None:
    dm = DataManager(str(tmp_path))
    path = dm.namespaced_artifact_dir("ns.demo", "artifacts", "controller_event")
    assert path == tmp_path / "factors" / "ns.demo" / "artifacts" / "controller_event"
    assert path.is_dir()
    with pytest.raises(ValueError):
        dm.namespaced_artifact_dir("ns.demo", "..")
    with pytest.raises(ValueError):
        dm.namespaced_artifact_dir("ns.demo", "a/b")
