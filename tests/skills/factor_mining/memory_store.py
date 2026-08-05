"""In-memory ArtifactStorePort with real put_if_absent CAS for Phase 04 tests."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from skills.factor_mining.adapters.store import PutIfAbsentResult
from skills.factor_mining.contracts import (
    SCHEMA_VERSION,
    ArtifactRef,
    EvidenceRef,
    FailureCode,
    ObjectRef,
    content_hash,
    to_plain_dict,
)


class InMemoryArtifactStoreError(Exception):
    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.put_calls = 0
        self.put_if_absent_calls = 0
        self.fail_kind: str | None = None
        self.fail_put_if_absent_kind: str | None = None

    def _body(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple,
        meta: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "artifact_id": artifact_id,
            "namespace": namespace,
            "schema_version": SCHEMA_VERSION,
            "adapter_schema_version": "test",
            "input_refs": [to_plain_dict(ref) for ref in input_refs],
            "payload": dict(payload),
            "meta": dict(meta or {}),
        }

    def put(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> ArtifactRef:
        if self.fail_kind == kind:
            raise RuntimeError(f"injected failure for kind={kind}")
        with self._lock:
            body = self._body(
                namespace=namespace,
                kind=kind,
                artifact_id=artifact_id,
                payload=payload,
                input_refs=input_refs,
                meta=meta,
            )
            digest = content_hash(body)
            self._items[(namespace, kind, artifact_id)] = body
            self.put_calls += 1
            return ArtifactRef(
                kind=kind,
                artifact_id=artifact_id,
                namespace=namespace,
                content_hash=digest,
            )

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
        if self.fail_put_if_absent_kind == kind or self.fail_kind == kind:
            raise RuntimeError(f"injected failure for kind={kind}")
        with self._lock:
            self.put_if_absent_calls += 1
            key = (namespace, kind, artifact_id)
            body = self._body(
                namespace=namespace,
                kind=kind,
                artifact_id=artifact_id,
                payload=payload,
                input_refs=input_refs,
                meta=meta,
            )
            digest = content_hash(body)
            existing = self._items.get(key)
            if existing is not None:
                existing_digest = content_hash(existing)
                if existing_digest == digest:
                    return PutIfAbsentResult(
                        ref=ArtifactRef(
                            kind=kind,
                            artifact_id=artifact_id,
                            namespace=namespace,
                            content_hash=existing_digest,
                        ),
                        created=False,
                    )
                raise InMemoryArtifactStoreError(
                    FailureCode.DUPLICATE_LOGICAL_KEY,
                    "append-only artifact exists with different content",
                )
            self._items[key] = body
            return PutIfAbsentResult(
                ref=ArtifactRef(
                    kind=kind,
                    artifact_id=artifact_id,
                    namespace=namespace,
                    content_hash=digest,
                ),
                created=True,
            )

    def get(self, ref: ArtifactRef) -> Mapping[str, Any]:
        with self._lock:
            body = self._items.get((ref.namespace, ref.kind, ref.artifact_id))
            if body is None:
                raise KeyError("missing")
            digest = content_hash(body)
            if digest != ref.content_hash:
                raise ValueError("hash mismatch")
            return body["payload"]

    def get_envelope(self, ref: ArtifactRef) -> Mapping[str, Any]:
        with self._lock:
            body = self._items.get((ref.namespace, ref.kind, ref.artifact_id))
            if body is None:
                raise KeyError("missing")
            digest = content_hash(body)
            if digest != ref.content_hash:
                raise ValueError("hash mismatch")
            return dict(body)

    def exists(self, ref: ArtifactRef) -> bool:
        try:
            self.get(ref)
            return True
        except Exception:  # noqa: BLE001
            return False

    def get_unchecked(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        with self._lock:
            body = self._items[(namespace, kind, artifact_id)]
            return body["payload"]

    def get_by_identity(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        with self._lock:
            body = self._items[(namespace, kind, artifact_id)]
            digest = content_hash(body)
            ref = ArtifactRef(
                kind=kind,
                artifact_id=artifact_id,
                namespace=namespace,
                content_hash=digest,
            )
        return self.get(ref)

    def get_envelope_by_identity(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        """Load full envelope (payload+meta) by identity after verifying checksum."""
        with self._lock:
            body = self._items.get((namespace, kind, artifact_id))
            if body is None:
                raise KeyError("missing")
            digest = content_hash(body)
            ref = ArtifactRef(
                kind=kind,
                artifact_id=artifact_id,
                namespace=namespace,
                content_hash=digest,
            )
        return self.get_envelope(ref)

    def list_artifact_ids(self, *, namespace: str, kind: str) -> list[str]:
        with self._lock:
            return sorted(
                aid
                for (ns, k, aid) in self._items
                if ns == namespace and k == kind
            )

    def envelope_hash(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple = (),
        meta: Mapping[str, Any] | None = None,
    ) -> str:
        body = self._body(
            namespace=namespace,
            kind=kind,
            artifact_id=artifact_id,
            payload=payload,
            input_refs=input_refs,
            meta=meta,
        )
        return content_hash(body)

    def tamper(self, *, namespace: str, kind: str, artifact_id: str) -> None:
        with self._lock:
            body = self._items[(namespace, kind, artifact_id)]
            payload = dict(body["payload"])
            payload["tampered"] = True
            body["payload"] = payload


class UnreadableListedArtifactStore:
    """Public ArtifactStorePort wrapper that keeps ids listed but fails get_by_identity.

    Used to exercise fail-closed listed-but-unreadable event loading without
    mutating private backing maps of the inner store.
    """

    def __init__(self, inner: InMemoryArtifactStore) -> None:
        self._inner = inner
        self._unreadable: set[tuple[str, str, str]] = set()

    def mark_unreadable(self, *, namespace: str, kind: str, artifact_id: str) -> None:
        self._unreadable.add((namespace, kind, artifact_id))

    def list_artifact_ids(self, *, namespace: str, kind: str) -> list[str]:
        return self._inner.list_artifact_ids(namespace=namespace, kind=kind)

    def get_by_identity(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        if (namespace, kind, artifact_id) in self._unreadable:
            raise OSError("injected unreadable listed artifact")
        return self._inner.get_by_identity(
            namespace=namespace, kind=kind, artifact_id=artifact_id
        )

    def get(self, ref: ArtifactRef) -> Mapping[str, Any]:
        key = (ref.namespace, ref.kind, ref.artifact_id)
        if key in self._unreadable:
            raise OSError("injected unreadable listed artifact")
        return self._inner.get(ref)

    def get_envelope(self, ref: ArtifactRef) -> Mapping[str, Any]:
        return self._inner.get_envelope(ref)

    def get_envelope_by_identity(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        if (namespace, kind, artifact_id) in self._unreadable:
            raise OSError("injected unreadable listed artifact")
        return self._inner.get_envelope_by_identity(
            namespace=namespace, kind=kind, artifact_id=artifact_id
        )

    def exists(self, ref: ArtifactRef) -> bool:
        return self._inner.exists(ref)

    def put(self, **kwargs):  # type: ignore[no-untyped-def]
        return self._inner.put(**kwargs)

    def put_if_absent(self, **kwargs):  # type: ignore[no-untyped-def]
        return self._inner.put_if_absent(**kwargs)

    def envelope_hash(self, **kwargs):  # type: ignore[no-untyped-def]
        return self._inner.envelope_hash(**kwargs)

    def get_unchecked(self, **kwargs):  # type: ignore[no-untyped-def]
        return self._inner.get_unchecked(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
