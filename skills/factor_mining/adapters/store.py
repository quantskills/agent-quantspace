"""ArtifactStorePort adapter backed by DataManager factor namespaces."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from skills.factor_mining.adapters.panel import ADAPTER_SCHEMA_VERSION
from skills.factor_mining.contracts import (
    SCHEMA_VERSION,
    ArtifactRef,
    EvidenceRef,
    FailureCode,
    ObjectRef,
    canonical_json,
    content_hash,
    to_plain_dict,
)
from skills.store.data_manager import DataManager

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class ArtifactStoreAdapterError(Exception):
    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PutIfAbsentResult:
    """Outcome of an append-only / create-if-absent write."""

    ref: ArtifactRef
    created: bool


def build_factor_cache_key(
    *,
    spec_hash: str,
    data_version: str,
    split_id: str,
    compute_fingerprint: str,
    adapter_schema_version: str = ADAPTER_SCHEMA_VERSION,
) -> str:
    """Stable cache key spanning spec/data/split/compute/adapter versions."""
    return content_hash(
        {
            "spec_hash": spec_hash,
            "data_version": data_version,
            "split_id": split_id,
            "compute_fingerprint": compute_fingerprint,
            "adapter_schema_version": adapter_schema_version,
        }
    )


def _safe_segment(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ArtifactStoreAdapterError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            f"invalid {label}",
        )
    if Path(value).is_absolute() or ".." in value.split("/") or "\\" in value or "/" in value:
        raise ArtifactStoreAdapterError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            f"path traversal rejected for {label}",
        )
    if not _SAFE_SEGMENT.match(value):
        raise ArtifactStoreAdapterError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            f"invalid {label}",
        )
    return value


class DataManagerArtifactStore:
    """Persist JSON research artifacts under ``data/factors/<namespace>/``."""

    def __init__(self, data_manager: DataManager) -> None:
        self._dm = data_manager

    def put(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = (),
    ) -> ArtifactRef:
        namespace = _safe_segment(namespace, label="namespace")
        kind = _safe_segment(kind, label="kind")
        artifact_id = _safe_segment(artifact_id, label="artifact_id")
        for ref in input_refs:
            ref_ns = getattr(ref, "namespace", None)
            if ref_ns != namespace:
                raise ArtifactStoreAdapterError(
                    FailureCode.INVALID_REFERENCE,
                    "input_refs namespace mismatch",
                )
        self._assert_namespace_contained(namespace)
        path = self._artifact_path(namespace, kind, artifact_id)
        self._assert_path_contained(path, namespace)
        tmp_path: Path | None = None
        fd: int | None = None
        try:
            body = {
                "kind": kind,
                "artifact_id": artifact_id,
                "namespace": namespace,
                "schema_version": SCHEMA_VERSION,
                "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
                "input_refs": [to_plain_dict(ref) for ref in input_refs],
                "payload": dict(payload),
                "meta": {},
            }
            digest = content_hash(body)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._assert_path_contained(path, namespace)
            self._assert_path_contained(path.parent, namespace)
            # Exclusive create in the validated directory; never open a
            # predictable caller-planted ``*.json.tmp`` symlink.
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{artifact_id}.",
                suffix=".json.tmp",
                dir=str(path.parent),
            )
            tmp_path = Path(tmp_name)
            if tmp_path.is_symlink() or not tmp_path.is_file():
                raise ArtifactStoreAdapterError(
                    FailureCode.ARTIFACT_PERSIST_FAILED,
                    "temporary artifact path is not a regular file",
                )
            self._assert_path_contained(tmp_path, namespace)
            payload_text = canonical_json(body)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                handle.write(payload_text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            tmp_path = None
            self._assert_path_contained(path, namespace)
            return ArtifactRef(
                kind=kind,
                artifact_id=artifact_id,
                namespace=namespace,
                content_hash=digest,
                uri=str(path.relative_to(self._dm.root)),
            )
        except ArtifactStoreAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "failed to persist artifact",
            ) from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def put_if_absent(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> PutIfAbsentResult:
        """Create-only write with crash-safe atomic publication.

        Complete content is written and fsynced to an anonymous temp file, then
        published via ``os.link`` onto the final path (true create-if-absent).
        Readers never observe partial final content. Identical races converge
        (``created=False``); divergent races raise ``DUPLICATE_LOGICAL_KEY``.
        Temp/orphan files are never authoritative.
        """
        namespace = _safe_segment(namespace, label="namespace")
        kind = _safe_segment(kind, label="kind")
        artifact_id = _safe_segment(artifact_id, label="artifact_id")
        for ref in input_refs:
            ref_ns = getattr(ref, "namespace", None)
            if ref_ns != namespace:
                raise ArtifactStoreAdapterError(
                    FailureCode.INVALID_REFERENCE,
                    "input_refs namespace mismatch",
                )
        self._assert_namespace_contained(namespace)
        path = self._artifact_path(namespace, kind, artifact_id)
        self._assert_path_contained(path, namespace)
        body = {
            "kind": kind,
            "artifact_id": artifact_id,
            "namespace": namespace,
            "schema_version": SCHEMA_VERSION,
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "input_refs": [to_plain_dict(ref) for ref in input_refs],
            "payload": dict(payload),
            "meta": dict(meta or {}),
        }
        digest = content_hash(body)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._assert_path_contained(path.parent, namespace)
        payload_text = canonical_json(body)

        # Fast path: final already published.
        if path.exists() and not path.is_symlink():
            return self._put_if_absent_existing(
                path=path,
                namespace=namespace,
                kind=kind,
                artifact_id=artifact_id,
                digest=digest,
            )

        tmp_path: Path | None = None
        fd: int | None = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{artifact_id}.",
                suffix=".json.tmp",
                dir=str(path.parent),
            )
            tmp_path = Path(tmp_name)
            if tmp_path.is_symlink() or not tmp_path.is_file():
                raise ArtifactStoreAdapterError(
                    FailureCode.ARTIFACT_PERSIST_FAILED,
                    "temporary artifact path is not a regular file",
                )
            self._assert_path_contained(tmp_path, namespace)
            # Test hook: crash before durable temp content is complete.
            self._crash_point("before_temp_write")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                handle.write(payload_text)
                handle.flush()
                os.fsync(handle.fileno())
            self._crash_point("after_temp_fsync")
            # Atomic publish: final path appears only with complete content.
            try:
                os.link(str(tmp_path), str(path))
            except FileExistsError:
                return self._put_if_absent_existing(
                    path=path,
                    namespace=namespace,
                    kind=kind,
                    artifact_id=artifact_id,
                    digest=digest,
                )
            self._crash_point("after_link")
            # Durability: directory entry for the new link must be fsynced before
            # success. Crash after link but before dir fsync still converges on
            # retry via FileExistsError → identical/divergent compare.
            dir_flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                dir_flags |= os.O_DIRECTORY
            dir_fd = os.open(str(path.parent), dir_flags)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            self._crash_point("after_dir_fsync")
        except ArtifactStoreAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "failed to persist append-only artifact",
            ) from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

        self._assert_path_contained(path, namespace)
        return PutIfAbsentResult(
            ref=ArtifactRef(
                kind=kind,
                artifact_id=artifact_id,
                namespace=namespace,
                content_hash=digest,
                uri=str(path.relative_to(self._dm.root)),
            ),
            created=True,
        )

    def _crash_point(self, name: str) -> None:
        """Optional test injection; production no-op unless hook is set."""
        hook = getattr(self, "_test_crash_hook", None)
        if callable(hook):
            hook(name)

    def _put_if_absent_existing(
        self,
        *,
        path: Path,
        namespace: str,
        kind: str,
        artifact_id: str,
        digest: str,
    ) -> PutIfAbsentResult:
        """Compare an already-published final path; never treat orphans as wins."""
        try:
            existing = self._read_body(path, namespace=namespace)
            existing_digest = content_hash(existing)
        except ArtifactStoreAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "existing append-only artifact is unreadable/corrupt",
            ) from exc
        if existing_digest == digest:
            return PutIfAbsentResult(
                ref=ArtifactRef(
                    kind=kind,
                    artifact_id=artifact_id,
                    namespace=namespace,
                    content_hash=existing_digest,
                    uri=str(path.relative_to(self._dm.root)),
                ),
                created=False,
            )
        raise ArtifactStoreAdapterError(
            FailureCode.DUPLICATE_LOGICAL_KEY,
            "append-only artifact exists with different content",
        )

    def _read_body(self, path: Path, *, namespace: str) -> dict[str, Any]:
        self._assert_path_contained(path, namespace)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "artifact body is not an object",
            )
        return {
            "kind": raw["kind"],
            "artifact_id": raw["artifact_id"],
            "namespace": raw["namespace"],
            "schema_version": raw["schema_version"],
            "adapter_schema_version": raw["adapter_schema_version"],
            "input_refs": raw.get("input_refs", []),
            "payload": raw["payload"],
            "meta": raw.get("meta", {}),
        }

    def get_envelope_by_identity(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        """Load full envelope by identity after verifying on-disk checksum."""
        namespace = _safe_segment(namespace, label="namespace")
        kind = _safe_segment(kind, label="kind")
        artifact_id = _safe_segment(artifact_id, label="artifact_id")
        self._assert_namespace_contained(namespace)
        path = self._artifact_path(namespace, kind, artifact_id)
        self._assert_path_contained(path, namespace)
        if not path.exists():
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact not found",
            )
        body = self._read_body(path, namespace=namespace)
        digest = content_hash(body)
        ref = ArtifactRef(
            kind=kind,
            artifact_id=artifact_id,
            namespace=namespace,
            content_hash=digest,
            schema_version=str(body.get("schema_version", SCHEMA_VERSION)),
            uri=str(path.relative_to(self._dm.root)),
        )
        return self.get_envelope(ref)

    def envelope_hash(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> str:
        """Predict content hash of a put_if_absent envelope without writing."""
        namespace = _safe_segment(namespace, label="namespace")
        kind = _safe_segment(kind, label="kind")
        artifact_id = _safe_segment(artifact_id, label="artifact_id")
        body = {
            "kind": kind,
            "artifact_id": artifact_id,
            "namespace": namespace,
            "schema_version": SCHEMA_VERSION,
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "input_refs": [to_plain_dict(ref) for ref in input_refs],
            "payload": dict(payload),
            "meta": dict(meta or {}),
        }
        return content_hash(body)

    def get(self, ref: ArtifactRef) -> Mapping[str, Any]:
        namespace = _safe_segment(ref.namespace, label="namespace")
        kind = _safe_segment(ref.kind, label="kind")
        artifact_id = _safe_segment(ref.artifact_id, label="artifact_id")
        self._assert_namespace_contained(namespace)
        path = self._artifact_path(namespace, kind, artifact_id)
        self._assert_path_contained(path, namespace)
        if not path.exists():
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact not found",
            )
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
            digest = content_hash(
                {
                    "kind": body["kind"],
                    "artifact_id": body["artifact_id"],
                    "namespace": body["namespace"],
                    "schema_version": body["schema_version"],
                    "adapter_schema_version": body["adapter_schema_version"],
                    "input_refs": body.get("input_refs", []),
                    "payload": body["payload"],
                    "meta": body.get("meta", {}),
                }
            )
        except ArtifactStoreAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "failed to load artifact",
            ) from exc
        if body.get("kind") != ref.kind:
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact kind mismatch",
            )
        if body.get("artifact_id") != ref.artifact_id:
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact_id mismatch",
            )
        if body.get("namespace") != ref.namespace:
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact namespace mismatch",
            )
        if body.get("schema_version") != ref.schema_version:
            raise ArtifactStoreAdapterError(
                FailureCode.SCHEMA_MISMATCH,
                "artifact schema_version mismatch",
            )
        if digest != ref.content_hash:
            raise ArtifactStoreAdapterError(
                FailureCode.HASH_MISMATCH,
                "artifact content_hash mismatch",
            )
        payload = body.get("payload")
        if not isinstance(payload, Mapping):
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "artifact payload missing",
            )
        return payload

    def get_envelope(self, ref: ArtifactRef) -> Mapping[str, Any]:
        """Return verified envelope including payload + meta (sealed capability)."""
        _ = self.get(ref)  # verify hash/identity
        path = self._artifact_path(ref.namespace, ref.kind, ref.artifact_id)
        body = self._read_body(path, namespace=ref.namespace)
        return body

    def get_by_identity(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
    ) -> Mapping[str, Any]:
        """Load payload by namespace/kind/id after verifying on-disk checksum.

        Unlike ``get(ArtifactRef)``, callers need not know the content hash in
        advance. Used for controller snapshot recovery and event replay.
        """
        namespace = _safe_segment(namespace, label="namespace")
        kind = _safe_segment(kind, label="kind")
        artifact_id = _safe_segment(artifact_id, label="artifact_id")
        self._assert_namespace_contained(namespace)
        path = self._artifact_path(namespace, kind, artifact_id)
        self._assert_path_contained(path, namespace)
        if not path.exists():
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact not found",
            )
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
            digest = content_hash(
                {
                    "kind": body["kind"],
                    "artifact_id": body["artifact_id"],
                    "namespace": body["namespace"],
                    "schema_version": body["schema_version"],
                    "adapter_schema_version": body["adapter_schema_version"],
                    "input_refs": body.get("input_refs", []),
                    "payload": body["payload"],
                    "meta": body.get("meta", {}),
                }
            )
        except ArtifactStoreAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "failed to load artifact",
            ) from exc
        if body.get("namespace") != namespace or body.get("kind") != kind:
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact identity mismatch",
            )
        if body.get("artifact_id") != artifact_id:
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_REFERENCE,
                "artifact_id mismatch",
            )
        # Re-validate via ArtifactRef.get semantics.
        ref = ArtifactRef(
            kind=kind,
            artifact_id=artifact_id,
            namespace=namespace,
            content_hash=digest,
            schema_version=str(body.get("schema_version", SCHEMA_VERSION)),
            uri=str(path.relative_to(self._dm.root)),
        )
        return self.get(ref)

    def get_unchecked(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
    ) -> Mapping[str, Any]:
        """Alias for ``get_by_identity`` (controller recovery hook)."""
        return self.get_by_identity(
            namespace=namespace, kind=kind, artifact_id=artifact_id
        )

    def list_artifact_ids(self, *, namespace: str, kind: str) -> list[str]:
        """List artifact ids under namespace/kind (no payload load)."""
        namespace = _safe_segment(namespace, label="namespace")
        kind = _safe_segment(kind, label="kind")
        self._assert_namespace_contained(namespace)
        directory = self._artifact_path(namespace, kind, "_").parent
        self._assert_path_contained(directory, namespace)
        if not directory.is_dir():
            return []
        ids: list[str] = []
        for path in directory.iterdir():
            if path.is_file() and path.suffix == ".json":
                ids.append(path.stem)
        return sorted(ids)

    def exists(self, ref: ArtifactRef) -> bool:
        try:
            self.get(ref)
            return True
        except ArtifactStoreAdapterError:
            return False

    def save_factor_pivot(
        self,
        *,
        namespace: str,
        cache_key: str,
        values: pd.Series,
    ) -> Path:
        """Persist a date×symbol wide pivot for explicit cache reuse."""
        namespace = _safe_segment(namespace, label="namespace")
        cache_key = _safe_segment(cache_key, label="cache_key")
        self._assert_namespace_contained(namespace)
        if not isinstance(values.index, pd.MultiIndex):
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_OUTPUT_TYPE,
                "factor pivot requires a MultiIndex Series",
            )
        names = list(values.index.names)
        if "symbol" not in names:
            raise ArtifactStoreAdapterError(
                FailureCode.INVALID_INDEX_SCHEMA,
                "factor pivot requires a symbol level",
            )
        working = values.copy()
        if None in names:
            working.index = working.index.set_names(
                ["symbol" if n == "symbol" else "eob" for n in names]
            )
        pivot = working.unstack("symbol").sort_index()
        filename = self._dm.factor_filename(
            "factor_mining_cache", {"cache_key": cache_key}
        )
        path = self._dm.root / "factors" / namespace / filename
        self._assert_path_contained(path, namespace)
        self._dm.save_factor(
            namespace=namespace,
            func_name="factor_mining_cache",
            params={"cache_key": cache_key},
            pivot_df=pivot,
        )
        self._assert_path_contained(path, namespace)
        return path

    def read_factor_pivot(self, *, namespace: str, cache_key: str) -> pd.DataFrame | None:
        namespace = _safe_segment(namespace, label="namespace")
        cache_key = _safe_segment(cache_key, label="cache_key")
        self._assert_namespace_contained(namespace)
        filename = self._dm.factor_filename(
            "factor_mining_cache", {"cache_key": cache_key}
        )
        path = self._dm.root / "factors" / namespace / filename
        self._assert_path_contained(path, namespace)
        return self._dm.read_factor(
            namespace=namespace,
            func_name="factor_mining_cache",
            params={"cache_key": cache_key},
        )

    def _artifact_path(self, namespace: str, kind: str, artifact_id: str) -> Path:
        return (
            self._dm.root
            / "factors"
            / namespace
            / "artifacts"
            / kind
            / f"{artifact_id}.json"
        )

    def _factors_root(self) -> Path:
        return (self._dm.root / "factors").resolve()

    def _assert_namespace_contained(self, namespace: str) -> None:
        """Reject namespace directories that symlink/resolve outside data/factors."""
        factors_root = self._factors_root()
        data_root = self._dm.root.resolve()
        try:
            factors_root.relative_to(data_root)
        except ValueError as exc:
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "factors root escaped data root",
            ) from exc
        ns_dir = self._dm.root / "factors" / namespace
        if ns_dir.exists() or ns_dir.is_symlink():
            resolved_ns = ns_dir.resolve()
            try:
                resolved_ns.relative_to(factors_root)
            except ValueError as exc:
                raise ArtifactStoreAdapterError(
                    FailureCode.ARTIFACT_PERSIST_FAILED,
                    "namespace escapes factors root",
                ) from exc

    def _assert_path_contained(self, path: Path, namespace: str) -> None:
        """Require logical and resolved targets to stay under data/factors."""
        self._assert_namespace_contained(namespace)
        factors_root = self._factors_root()
        logical_ns = self._dm.root / "factors" / namespace
        try:
            relative = path.relative_to(logical_ns)
        except ValueError as exc:
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "path is outside factors namespace",
            ) from exc
        # Walk only under the namespace so nested symlinks are caught without
        # incorrectly rejecting ordinary parents above data/factors.
        cursor = logical_ns
        for part in relative.parts:
            cursor = cursor / part
            if cursor.exists() or cursor.is_symlink():
                resolved_cursor = cursor.resolve()
                try:
                    resolved_cursor.relative_to(factors_root)
                except ValueError as exc:
                    raise ArtifactStoreAdapterError(
                        FailureCode.ARTIFACT_PERSIST_FAILED,
                        "resolved path escaped factors root",
                    ) from exc
        resolved = path.resolve()
        try:
            resolved.relative_to(factors_root)
        except ValueError as exc:
            raise ArtifactStoreAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "resolved path escaped factors root",
            ) from exc
        if logical_ns.exists() or logical_ns.is_symlink():
            resolved_ns = logical_ns.resolve()
            try:
                resolved.relative_to(resolved_ns)
            except ValueError as exc:
                raise ArtifactStoreAdapterError(
                    FailureCode.ARTIFACT_PERSIST_FAILED,
                    "resolved path escaped factors namespace",
                ) from exc
