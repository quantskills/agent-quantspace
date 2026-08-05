"""Crash-safe put_if_absent atomicity for DataManagerArtifactStore (P1-A)."""

from __future__ import annotations

import multiprocessing as mp
import os
import threading
from pathlib import Path

import pytest

from skills.factor_mining.adapters.store import (
    ArtifactStoreAdapterError,
    DataManagerArtifactStore,
)
from skills.factor_mining.contracts import FailureCode
from skills.store.data_manager import DataManager

NS = "ns.demo"


def _store(tmp_path: Path) -> DataManagerArtifactStore:
    dm = DataManager(data_root=str(tmp_path))
    return DataManagerArtifactStore(dm)


def _final_artifact_path(
    data_root: Path, *, namespace: str, kind: str, artifact_id: str
) -> Path:
    """Test-scoped path helper matching DataManagerArtifactStore layout (not a private API)."""
    return (
        data_root
        / "factors"
        / namespace
        / "artifacts"
        / kind
        / f"{artifact_id}.json"
    )


def test_put_if_absent_crash_before_temp_write_leaves_no_final(tmp_path) -> None:
    store = _store(tmp_path)
    hits: list[str] = []

    def hook(name: str) -> None:
        hits.append(name)
        if name == "before_temp_write":
            raise RuntimeError("injected crash before temp write")

    store._test_crash_hook = hook  # type: ignore[attr-defined]
    with pytest.raises(ArtifactStoreAdapterError) as excinfo:
        store.put_if_absent(
            namespace=NS,
            kind="controller_event",
            artifact_id="run-1-00000001",
            payload={"sequence": 1},
        )
    assert excinfo.value.code is FailureCode.ARTIFACT_PERSIST_FAILED
    assert "before_temp_write" in hits
    assert "run-1-00000001" not in store.list_artifact_ids(
        namespace=NS, kind="controller_event"
    )
    final = _final_artifact_path(
        Path(tmp_path),
        namespace=NS,
        kind="controller_event",
        artifact_id="run-1-00000001",
    )
    assert not final.exists()


def test_put_if_absent_crash_after_temp_fsync_before_link_no_final(tmp_path) -> None:
    store = _store(tmp_path)

    def hook(name: str) -> None:
        if name == "after_temp_fsync":
            raise RuntimeError("injected crash after fsync")

    store._test_crash_hook = hook  # type: ignore[attr-defined]
    with pytest.raises(ArtifactStoreAdapterError):
        store.put_if_absent(
            namespace=NS,
            kind="controller_event",
            artifact_id="run-1-00000001",
            payload={"sequence": 1, "body": "x"},
        )
    assert "run-1-00000001" not in store.list_artifact_ids(
        namespace=NS, kind="controller_event"
    )
    final = _final_artifact_path(
        Path(tmp_path),
        namespace=NS,
        kind="controller_event",
        artifact_id="run-1-00000001",
    )
    assert not final.exists()
    leftovers = (
        list(final.parent.glob(".run-1-00000001.*.json.tmp"))
        if final.parent.exists()
        else []
    )
    assert leftovers == []


def test_put_if_absent_concurrent_identical_converges(tmp_path) -> None:
    store = _store(tmp_path)
    barrier = threading.Barrier(8)
    results: list = []
    errors: list = []

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            out = store.put_if_absent(
                namespace=NS,
                kind="controller_object",
                artifact_id="ResearchBrief-brief-1",
                payload={
                    "object_type": "ResearchBrief",
                    "object_id": "brief-1",
                    "body": {"k": 1},
                },
            )
            results.append(out)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    assert len(results) == 8
    created = [r for r in results if r.created]
    not_created = [r for r in results if not r.created]
    assert len(created) == 1
    assert len(not_created) == 7
    hashes = {r.ref.content_hash for r in results}
    assert len(hashes) == 1
    # Public read confirms durable publish.
    assert store.get(created[0].ref)["body"]["k"] == 1


def test_put_if_absent_concurrent_divergent_raises(tmp_path) -> None:
    store = _store(tmp_path)
    first = store.put_if_absent(
        namespace=NS,
        kind="controller_object",
        artifact_id="PoolDecision-pd-1",
        payload={"v": 1},
    )
    assert first.created is True
    with pytest.raises(ArtifactStoreAdapterError) as excinfo:
        store.put_if_absent(
            namespace=NS,
            kind="controller_object",
            artifact_id="PoolDecision-pd-1",
            payload={"v": 2},
        )
    assert excinfo.value.code is FailureCode.DUPLICATE_LOGICAL_KEY


def test_listed_event_corrupt_file_fail_closed_via_public_get(tmp_path) -> None:
    """P1-C: corrupt on-disk listed event → load_run_event_payloads RECOVERY_REQUIRED."""
    from skills.factor_mining.event_chain import EventChainError, load_run_event_payloads

    store = _store(tmp_path)
    put = store.put_if_absent(
        namespace=NS,
        kind="controller_event",
        artifact_id="run-corrupt-00000001",
        payload={"sequence": 1, "run_id": "run-corrupt", "namespace": NS},
    )
    assert put.created is True
    assert "run-corrupt-00000001" in store.list_artifact_ids(
        namespace=NS, kind="controller_event"
    )
    path = _final_artifact_path(
        Path(tmp_path),
        namespace=NS,
        kind="controller_event",
        artifact_id="run-corrupt-00000001",
    )
    assert path.is_file()
    # Deliberate on-disk corruption through test-scoped path helper (not private store maps).
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(EventChainError) as excinfo:
        load_run_event_payloads(store, namespace=NS, run_id="run-corrupt")
    assert excinfo.value.failure.code is FailureCode.RECOVERY_REQUIRED
    assert "unreadable" in excinfo.value.failure.message


def test_put_if_absent_directory_fsync_invoked_after_link(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    hits: list[str] = []
    fsynced_fds: list[int] = []

    def hook(name: str) -> None:
        hits.append(name)

    real_fsync = os.fsync

    def tracking_fsync(fd: int) -> None:
        fsynced_fds.append(fd)
        return real_fsync(fd)

    store._test_crash_hook = hook  # type: ignore[attr-defined]
    monkeypatch.setattr(os, "fsync", tracking_fsync)
    result = store.put_if_absent(
        namespace=NS,
        kind="controller_event",
        artifact_id="run-fsync-00000001",
        payload={"sequence": 1},
    )
    assert result.created is True
    assert "after_link" in hits
    assert "after_dir_fsync" in hits
    # At least temp-file fsync + directory fsync.
    assert len(fsynced_fds) >= 2


def _mp_identical_worker(data_root: str, queue) -> None:
    store = DataManagerArtifactStore(DataManager(data_root=data_root))
    try:
        out = store.put_if_absent(
            namespace=NS,
            kind="controller_object",
            artifact_id="ResearchBrief-mp-1",
            payload={"object_type": "ResearchBrief", "object_id": "mp-1", "body": {"k": 1}},
        )
        queue.put(("ok", out.created, out.ref.content_hash))
    except Exception as exc:  # noqa: BLE001
        queue.put(("err", type(exc).__name__, str(exc)))


def _mp_divergent_worker(data_root: str, payload_v: int, queue) -> None:
    store = DataManagerArtifactStore(DataManager(data_root=data_root))
    try:
        out = store.put_if_absent(
            namespace=NS,
            kind="controller_object",
            artifact_id="PoolDecision-mp-1",
            payload={"v": payload_v},
        )
        queue.put(("ok", out.created, payload_v))
    except ArtifactStoreAdapterError as exc:
        queue.put(("dup", exc.code.value, payload_v))
    except Exception as exc:  # noqa: BLE001
        queue.put(("err", type(exc).__name__, str(exc)))


def test_put_if_absent_multiprocessing_identical_converges(tmp_path) -> None:
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    procs = [
        ctx.Process(target=_mp_identical_worker, args=(str(tmp_path), queue))
        for _ in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0
    rows = [queue.get(timeout=5) for _ in procs]
    assert all(row[0] == "ok" for row in rows)
    created = [row for row in rows if row[1] is True]
    not_created = [row for row in rows if row[1] is False]
    assert len(created) == 1
    assert len(not_created) == 3
    assert len({row[2] for row in rows}) == 1


def test_put_if_absent_multiprocessing_divergent_one_winner(tmp_path) -> None:
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    procs = [
        ctx.Process(target=_mp_divergent_worker, args=(str(tmp_path), v, queue))
        for v in (1, 2, 3, 4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0
    rows = [queue.get(timeout=5) for _ in procs]
    wins = [row for row in rows if row[0] == "ok"]
    dups = [row for row in rows if row[0] == "dup"]
    assert len(wins) == 1
    assert len(dups) == 3
    assert all(row[1] == FailureCode.DUPLICATE_LOGICAL_KEY.value for row in dups)
