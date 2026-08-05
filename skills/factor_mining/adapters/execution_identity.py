"""Execution envelope identity for FactorExecutionResult (Phase 02 coherent).

``FactorExecutionResult.fingerprint`` / ``execution_content_hash`` is the
envelope identity hash of the execution result. It is **not** the raw formula
fingerprint alone. The compiled-formula identity lives in the first-class
``callable_fingerprint`` field.
"""

from __future__ import annotations

from typing import Any

from skills.factor_mining.contracts import (
    ArtifactRef,
    FactorExecutionResult,
    IndexSchema,
    ObjectRef,
    Provenance,
    content_hash,
)


def _ref_payload(ref: ObjectRef | ArtifactRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    if isinstance(ref, ObjectRef):
        return {
            "kind": "object",
            "object_type": ref.object_type,
            "object_id": ref.object_id,
            "namespace": ref.namespace,
            "schema_version": ref.schema_version,
            "content_hash": ref.content_hash,
        }
    return {
        "kind": "artifact",
        "artifact_kind": ref.kind,
        "artifact_id": ref.artifact_id,
        "namespace": ref.namespace,
        "schema_version": ref.schema_version,
        "content_hash": ref.content_hash,
        "uri": ref.uri,
    }


def _schema_payload(schema: IndexSchema) -> dict[str, Any]:
    return {
        "names": list(schema.names),
        "symbol_level": schema.symbol_level,
        "datetime_level": schema.datetime_level,
        "level_order": list(schema.level_order),
        "timezone": schema.timezone,
        "sorted": bool(schema.sorted),
    }


def _provenance_payload(prov: Provenance) -> dict[str, Any]:
    return {
        "producer": prov.producer,
        "data_version": prov.data_version,
        "code_version": prov.code_version,
        "experiment_version": prov.experiment_version,
        "namespace": prov.namespace,
        "input_refs": [_ref_payload(r) for r in prov.input_refs],
    }


def execution_envelope_payload(
    *,
    request_id: str,
    experiment_id: str,
    execution_id: str,
    brief_ref: ObjectRef,
    factor_ref: ObjectRef,
    values_ref: ArtifactRef | None,
    valid_mask_ref: ArtifactRef | None,
    index_schema: IndexSchema,
    provenance: Provenance,
    callable_fingerprint: str,
    data_version: str,
    split_id: str,
    values_content_hash: str | None,
    valid_mask_content_hash: str | None,
    warnings: tuple[str, ...] = (),
    failure_code: str | None = None,
) -> dict[str, Any]:
    """Canonical payload hashed into FactorExecutionResult.fingerprint."""
    return {
        "request_id": request_id,
        "experiment_id": experiment_id,
        "execution_id": execution_id,
        "brief_ref": _ref_payload(brief_ref),
        "factor_ref": _ref_payload(factor_ref),
        "values_ref": _ref_payload(values_ref),
        "valid_mask_ref": _ref_payload(valid_mask_ref),
        "index_schema": _schema_payload(index_schema),
        "provenance": _provenance_payload(provenance),
        "callable_fingerprint": callable_fingerprint,
        "data_version": data_version,
        "split_id": split_id,
        "values_content_hash": values_content_hash,
        "valid_mask_content_hash": valid_mask_content_hash,
        "warnings": list(warnings),
        "failure_code": failure_code,
    }


def execution_envelope_identity_from_parts(
    *,
    request_id: str,
    experiment_id: str,
    execution_id: str,
    brief_ref: ObjectRef,
    factor_ref: ObjectRef,
    values_ref: ArtifactRef | None,
    valid_mask_ref: ArtifactRef | None,
    index_schema: IndexSchema,
    provenance: Provenance,
    callable_fingerprint: str,
    data_version: str,
    split_id: str,
    values_content_hash: str | None,
    valid_mask_content_hash: str | None,
    warnings: tuple[str, ...] = (),
    failure_code: str | None = None,
) -> str:
    return content_hash(
        execution_envelope_payload(
            request_id=request_id,
            experiment_id=experiment_id,
            execution_id=execution_id,
            brief_ref=brief_ref,
            factor_ref=factor_ref,
            values_ref=values_ref,
            valid_mask_ref=valid_mask_ref,
            index_schema=index_schema,
            provenance=provenance,
            callable_fingerprint=callable_fingerprint,
            data_version=data_version,
            split_id=split_id,
            values_content_hash=values_content_hash,
            valid_mask_content_hash=valid_mask_content_hash,
            warnings=warnings,
            failure_code=failure_code,
        )
    )


def execution_envelope_identity(result: FactorExecutionResult) -> str:
    """Recompute envelope identity from a FactorExecutionResult."""
    failure_code = None if result.failure is None else result.failure.code.value
    return execution_envelope_identity_from_parts(
        request_id=result.request_id,
        experiment_id=result.experiment_id,
        execution_id=result.execution_id,
        brief_ref=result.brief_ref,
        factor_ref=result.factor_ref,
        values_ref=result.values_ref,
        valid_mask_ref=result.valid_mask_ref,
        index_schema=result.index_schema,
        provenance=result.provenance,
        callable_fingerprint=result.callable_fingerprint,
        data_version=result.data_version,
        split_id=result.split_id,
        values_content_hash=result.values_content_hash,
        valid_mask_content_hash=result.valid_mask_content_hash,
        warnings=tuple(result.warnings),
        failure_code=failure_code,
    )


def callable_fingerprint_from_execution(result: FactorExecutionResult) -> str:
    return str(result.callable_fingerprint)


__all__ = [
    "execution_envelope_identity",
    "execution_envelope_identity_from_parts",
    "execution_envelope_payload",
    "callable_fingerprint_from_execution",
]
