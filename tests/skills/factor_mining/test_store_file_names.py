"""Artifact keys map to file names that are valid on every platform, legacy names still read."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from skills.factor_mining.adapters.store import (
    ArtifactStoreAdapterError,
    DataManagerArtifactStore,
    escape_file_name,
    unescape_file_name,
)
from skills.factor_mining.contracts import FailureCode
from skills.store.data_manager import DataManager

NS = "ns.demo"
KIND = "factor_values"
KEY = "exec-1:values"
FORBIDDEN = set('<>:"/\\|?*') | {chr(code) for code in range(32)}

# A legacy raw name contains ':', which cannot exist on a Windows file system.
needs_colon_names = pytest.mark.skipif(
    sys.platform == "win32", reason="legacy raw names with ':' cannot exist on Windows"
)


def _store(tmp_path: Path) -> DataManagerArtifactStore:
    return DataManagerArtifactStore(DataManager(data_root=str(tmp_path)))


def _kind_dir(tmp_path: Path, kind: str = KIND) -> Path:
    return tmp_path / "factors" / NS / "artifacts" / kind


def _files(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


# ---------------------------------------------------------------------------
# escaping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "plain-id_1.v2",
        "exec-1:values",
        "a%b",
        "a%3Ab",
        'a<b>c:d"e/f\\g|h?i*j',
        "ctrl\x00\x1f\x7fend",
        "trailing.",
        "trailing ",
        "dots..",
        "中文:键",
        "",
    ],
)
def test_escape_round_trips(value) -> None:
    assert unescape_file_name(escape_file_name(value)) == value


def test_escape_is_injective_for_percent_lookalikes() -> None:
    # A literal "%3A" must not collide with the escape of ":".
    assert escape_file_name(":") == "%3A"
    assert escape_file_name("%3A") == "%253A"
    assert escape_file_name(":") != escape_file_name("%3A")
    assert escape_file_name("a%") == "a%25"


def test_escaped_names_contain_no_forbidden_characters() -> None:
    nasty = "".join(sorted(FORBIDDEN)) + "%.x. "
    name = escape_file_name(nasty)
    assert not FORBIDDEN & set(name)
    assert not name.endswith((".", " "))


def test_names_that_need_no_escaping_are_unchanged() -> None:
    for value in ("run-1-00000001", "ns.demo", "controller_event", "a.b-c_d", "sha256-ab12"):
        assert escape_file_name(value) == value


def test_trailing_dot_and_space_are_escaped() -> None:
    assert escape_file_name("name.") == "name%2E"
    assert escape_file_name("name ") == "name%20"
    assert escape_file_name("na.me") == "na.me"


# ---------------------------------------------------------------------------
# adapter writes and reads
# ---------------------------------------------------------------------------


def test_put_writes_an_escaped_file_name(tmp_path) -> None:
    store = _store(tmp_path)
    ref = store.put(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 1})
    names = _files(_kind_dir(tmp_path))
    assert names == ["exec-1%3Avalues.json"]
    assert not FORBIDDEN & set(names[0])
    assert ref.uri == "factors/ns.demo/artifacts/factor_values/exec-1%3Avalues.json"
    assert store.get(ref) == {"v": 1}
    assert store.exists(ref)
    assert store.get_by_identity(namespace=NS, kind=KIND, artifact_id=KEY) == {"v": 1}
    assert store.get_envelope(ref)["artifact_id"] == KEY


def test_put_if_absent_writes_an_escaped_file_name_and_no_temp_leftovers(tmp_path) -> None:
    store = _store(tmp_path)
    result = store.put_if_absent(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 1})
    assert result.created
    assert _files(_kind_dir(tmp_path)) == ["exec-1%3Avalues.json"]
    again = store.put_if_absent(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 1})
    assert not again.created and again.ref == result.ref
    with pytest.raises(ArtifactStoreAdapterError) as excinfo:
        store.put_if_absent(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 2})
    assert excinfo.value.code is FailureCode.DUPLICATE_LOGICAL_KEY
    assert _files(_kind_dir(tmp_path)) == ["exec-1%3Avalues.json"]


def test_keys_that_differ_only_by_colon_stay_distinct(tmp_path) -> None:
    store = _store(tmp_path)
    keys = ["a:b", "a-b", "a.b", "a:b:c"]
    for index, key in enumerate(keys):
        store.put_if_absent(namespace=NS, kind=KIND, artifact_id=key, payload={"i": index})
    assert store.list_artifact_ids(namespace=NS, kind=KIND) == sorted(keys)
    for index, key in enumerate(keys):
        assert store.get_by_identity(namespace=NS, kind=KIND, artifact_id=key) == {"i": index}


def test_list_artifact_ids_decodes_escaped_names(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(namespace=NS, kind=KIND, artifact_id="exec-1:values", payload={})
    store.put(namespace=NS, kind=KIND, artifact_id="exec-1:mask", payload={})
    store.put(namespace=NS, kind=KIND, artifact_id="plain", payload={})
    assert store.list_artifact_ids(namespace=NS, kind=KIND) == [
        "exec-1:mask",
        "exec-1:values",
        "plain",
    ]


def test_colon_in_namespace_and_kind_is_escaped_too(tmp_path) -> None:
    store = _store(tmp_path)
    ref = store.put(namespace="ns:1", kind="kind:a", artifact_id="id:1", payload={"v": 1})
    assert ref.uri == "factors/ns%3A1/artifacts/kind%3Aa/id%3A1.json"
    assert store.get(ref) == {"v": 1}
    assert store.list_artifact_ids(namespace="ns:1", kind="kind:a") == ["id:1"]


# ---------------------------------------------------------------------------
# legacy raw names
# ---------------------------------------------------------------------------


def _move_to_legacy_name(directory: Path, escaped: str, raw: str) -> Path:
    legacy = directory / raw
    (directory / escaped).rename(legacy)
    return legacy


@needs_colon_names
def test_legacy_raw_named_artifact_is_read_through_the_adapter(tmp_path) -> None:
    store = _store(tmp_path)
    ref = store.put(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 1})
    directory = _kind_dir(tmp_path)
    _move_to_legacy_name(directory, "exec-1%3Avalues.json", "exec-1:values.json")
    assert _files(directory) == ["exec-1:values.json"]

    assert store.get(ref) == {"v": 1}
    assert store.exists(ref)
    assert store.get_by_identity(namespace=NS, kind=KIND, artifact_id=KEY) == {"v": 1}
    assert store.get_unchecked(namespace=NS, kind=KIND, artifact_id=KEY) == {"v": 1}
    assert store.get_envelope(ref)["payload"] == {"v": 1}
    assert store.get_envelope_by_identity(namespace=NS, kind=KIND, artifact_id=KEY)["payload"] == {
        "v": 1
    }
    assert store.list_artifact_ids(namespace=NS, kind=KIND) == [KEY]


@needs_colon_names
def test_put_if_absent_treats_a_legacy_file_as_existing(tmp_path) -> None:
    store = _store(tmp_path)
    store.put_if_absent(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 1})
    directory = _kind_dir(tmp_path)
    legacy = _move_to_legacy_name(directory, "exec-1%3Avalues.json", "exec-1:values.json")
    before = legacy.read_bytes()

    again = store.put_if_absent(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 1})
    assert not again.created
    assert again.ref.uri.endswith("exec-1:values.json")
    assert _files(directory) == ["exec-1:values.json"]  # no second copy
    assert legacy.read_bytes() == before

    with pytest.raises(ArtifactStoreAdapterError) as excinfo:
        store.put_if_absent(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 2})
    assert excinfo.value.code is FailureCode.DUPLICATE_LOGICAL_KEY
    assert _files(directory) == ["exec-1:values.json"]


@needs_colon_names
def test_listing_dedupes_a_key_present_under_both_names(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": 1})
    directory = _kind_dir(tmp_path)
    (directory / "exec-1:values.json").write_bytes(
        (directory / "exec-1%3Avalues.json").read_bytes()
    )
    assert store.list_artifact_ids(namespace=NS, kind=KIND) == [KEY]


@needs_colon_names
def test_escaped_file_wins_over_a_stale_legacy_file(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": "old"})
    directory = _kind_dir(tmp_path)
    _move_to_legacy_name(directory, "exec-1%3Avalues.json", "exec-1:values.json")
    ref = store.put(namespace=NS, kind=KIND, artifact_id=KEY, payload={"v": "new"})
    assert store.get(ref) == {"v": "new"}
    assert store.get_by_identity(namespace=NS, kind=KIND, artifact_id=KEY) == {"v": "new"}
    assert _files(directory) == ["exec-1%3Avalues.json", "exec-1:values.json"]


def test_missing_artifact_is_still_reported_missing(tmp_path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ArtifactStoreAdapterError) as excinfo:
        store.get_by_identity(namespace=NS, kind=KIND, artifact_id=KEY)
    assert excinfo.value.code is FailureCode.INVALID_REFERENCE
    assert store.list_artifact_ids(namespace=NS, kind=KIND) == []


# ---------------------------------------------------------------------------
# factor pivot cache
# ---------------------------------------------------------------------------


def _series() -> pd.Series:
    index = pd.MultiIndex.from_product(
        [["SHSE.510300", "SZSE.159915"], pd.date_range("2024-01-02", periods=3)],
        names=["symbol", "eob"],
    )
    return pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], index=index)


def test_factor_pivot_cache_key_is_escaped_and_round_trips(tmp_path) -> None:
    store = _store(tmp_path)
    path = store.save_factor_pivot(namespace=NS, cache_key="sha:abc", values=_series())
    assert path.name == "factor_mining_cache__sha%3Aabc.parquet" and path.is_file()
    assert not FORBIDDEN & set(path.name)
    pivot = store.read_factor_pivot(namespace=NS, cache_key="sha:abc")
    assert pivot is not None and list(pivot.columns) == ["SHSE.510300", "SZSE.159915"]
    assert store.read_factor_pivot(namespace=NS, cache_key="sha:other") is None


@needs_colon_names
def test_legacy_named_factor_pivot_is_still_read(tmp_path) -> None:
    store = _store(tmp_path)
    store.save_factor_pivot(namespace=NS, cache_key="sha:abc", values=_series())
    directory = tmp_path / "factors" / NS
    (directory / "factor_mining_cache__sha%3Aabc.parquet").rename(
        directory / "factor_mining_cache__sha:abc.parquet"
    )
    assert store.read_factor_pivot(namespace=NS, cache_key="sha:abc") is not None
