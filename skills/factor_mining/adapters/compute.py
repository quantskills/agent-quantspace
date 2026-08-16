"""Deterministic FactorExecutionPort adapter over compute + panel normalization."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from skills.compute.wrappers import Factor
from skills.factor_mining.adapters.execution_identity import (
    execution_envelope_identity_from_parts,
)
from skills.factor_mining.adapters.formula import (
    FORMULA_RESOLVER_VERSION,
    FormulaAdapterError,
    compile_formula,
)
from skills.factor_mining.adapters.panel import (
    ADAPTER_SCHEMA_VERSION,
    PanelAdapterError,
    normalize_panel,
    restore_series,
    valid_mask,
)
from skills.factor_mining.adapters.series_codec import (
    SeriesCodecError,
    series_content_hash,
    series_from_payload,
    series_to_payload,
)
from skills.factor_mining.adapters.store import ArtifactStoreAdapterError
from skills.factor_mining.contracts import (
    SCHEMA_VERSION,
    ArtifactRef,
    FactorComputeRequest,
    FactorExecutionResult,
    FactorSpec,
    FailureCode,
    FailureDetail,
    IndexSchema,
    ObjectRef,
    Provenance,
    Severity,
    content_hash,
)
from skills.factor_mining.ports import ArtifactStorePort

CODE_VERSION = (
    f"factor_mining.adapters.compute@{ADAPTER_SCHEMA_VERSION}"
    f"+resolver-{FORMULA_RESOLVER_VERSION}"
)

_SUPPORTED_MISSING_POLICY = "keep_nan"
_SUPPORTED_OUTPUT_DTYPE = "float64"
_SUPPORTED_INDEX_RESTORE_POLICY = "restore_original_names_and_order"


class FactorExecutionAdapterError(Exception):
    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fallback_schema() -> IndexSchema:
    return IndexSchema(
        names=("symbol", "eob"),
        symbol_level="symbol",
        datetime_level="eob",
        level_order=(0, 1),
        timezone="naive",
    )


def _schema_to_dict(schema: IndexSchema) -> dict[str, Any]:
    return {
        "names": list(schema.names),
        "symbol_level": schema.symbol_level,
        "datetime_level": schema.datetime_level,
        "level_order": list(schema.level_order),
        "timezone": schema.timezone,
        "sorted": schema.sorted,
    }


def _map_wrapper_error(exc: BaseException) -> FactorExecutionAdapterError:
    if isinstance(exc, TypeError):
        message = str(exc)
        lowered = message.lower()
        if "series" in lowered and "got" in lowered:
            return FactorExecutionAdapterError(
                FailureCode.INVALID_OUTPUT_TYPE,
                "factor function returned a non-Series value",
            )
        if "dtype" in lowered or "numeric" in lowered or "complex" in lowered or "boolean" in lowered:
            return FactorExecutionAdapterError(
                FailureCode.INVALID_OUTPUT_DTYPE,
                "factor function returned an invalid dtype",
            )
        return FactorExecutionAdapterError(
            FailureCode.INVALID_OUTPUT_TYPE,
            "factor function returned an invalid type",
        )
    if isinstance(exc, ValueError) and "index" in str(exc).lower():
        return FactorExecutionAdapterError(
            FailureCode.OUTPUT_INDEX_MISMATCH,
            "factor output index mismatch",
        )
    return FactorExecutionAdapterError(
        FailureCode.FACTOR_RUNTIME_FAILED,
        "factor runtime failed",
    )


def _apply_lag(values: pd.Series, lag: int) -> pd.Series:
    if lag == 0:
        return values
    symbols = list(dict.fromkeys(values.index.get_level_values("symbol")))
    pieces: list[pd.Series] = []
    for symbol in symbols:
        piece = values.xs(symbol, level="symbol", drop_level=True).shift(lag)
        pieces.append(piece)
    return pd.concat(pieces, keys=symbols, names=["symbol", "eob"])


def _refs_equal(left: ObjectRef, right: ObjectRef) -> bool:
    return (
        left.object_type == right.object_type
        and left.object_id == right.object_id
        and left.schema_version == right.schema_version
        and left.content_hash == right.content_hash
        and left.namespace == right.namespace
    )


class FactorExecutionAdapter:
    """Phase 02 deterministic implementation of ``FactorExecutionPort``.

    The adapter is explicitly configured with an ``ArtifactStorePort``. On
    success it persists values/mask through that store and returns real
    ``ArtifactRef`` handles. ``skills.compute.wrappers.Factor`` itself never
    writes artifacts.
    """

    def __init__(
        self,
        *,
        resolve_factor_spec: Callable[[ObjectRef], FactorSpec],
        resolve_panel: Callable[[FactorComputeRequest], object],
        artifact_store: ArtifactStorePort,
        producer: str = "factor_mining.adapters.compute",
    ) -> None:
        self._resolve_factor_spec = resolve_factor_spec
        self._resolve_panel = resolve_panel
        self._store = artifact_store
        self._producer = producer

    def execute(self, request: FactorComputeRequest) -> FactorExecutionResult:
        started = time.perf_counter()
        warnings: list[str] = []
        index_schema = _fallback_schema()
        fingerprint = content_hash(
            {
                "request_id": request.request_id,
                "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
                "formula_resolver_version": FORMULA_RESOLVER_VERSION,
            }
        )
        factor_ref = request.factor_ref
        try:
            self._validate_factor_ref(request.factor_ref)
            try:
                spec = self._resolve_factor_spec(request.factor_ref)
            except FactorExecutionAdapterError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise FactorExecutionAdapterError(
                    FailureCode.INVALID_REFERENCE,
                    "factor_ref could not be resolved",
                ) from exc
            self._validate_spec_identity(request, spec)

            panel = self._resolve_panel(request)
            if not isinstance(panel, pd.DataFrame):
                raise PanelAdapterError(
                    FailureCode.INVALID_PANEL_TYPE,
                    "panel must be a pandas DataFrame",
                )
            panel_snapshot = panel.copy(deep=True)
            normalized = normalize_panel(panel, required_fields=spec.required_fields)
            index_schema = normalized.index_schema
            if not panel_snapshot.equals(panel):
                raise FactorExecutionAdapterError(
                    FailureCode.INVALID_STATE,
                    "panel adapter mutated the caller panel",
                )

            func, fingerprint, bound_params = compile_formula(
                spec.formula,
                required_fields=spec.required_fields,
                adapter_schema_version=ADAPTER_SCHEMA_VERSION,
            )
            work = normalized.frame.loc[:, list(spec.required_fields)]
            factor = Factor(func)
            try:
                computed = factor.calculate(work, dropna=False)
                computed = _apply_lag(computed, spec.lag)
            except FactorExecutionAdapterError:
                raise
            except (TypeError, ValueError) as exc:
                raise _map_wrapper_error(exc) from exc
            except Exception as exc:  # noqa: BLE001
                raise FactorExecutionAdapterError(
                    FailureCode.FACTOR_RUNTIME_FAILED,
                    "factor runtime failed",
                ) from exc

            restored = restore_series(computed, normalized)
            mask = valid_mask(restored)
            if not panel_snapshot.equals(panel):
                raise FactorExecutionAdapterError(
                    FailureCode.INVALID_STATE,
                    "panel adapter mutated the caller panel",
                )
            if not restored.index.equals(panel.index):
                raise FactorExecutionAdapterError(
                    FailureCode.OUTPUT_INDEX_MISMATCH,
                    "restored values index does not match the caller panel index",
                )

            elapsed_ms = (time.perf_counter() - started) * 1000.0
            eob = normalized.frame.index.get_level_values("eob")
            output_schema = IndexSchema(
                names=tuple(restored.index.names),
                symbol_level="symbol",
                datetime_level=next(
                    (n for n in restored.index.names if n != "symbol"),
                    None,
                ),
                level_order=(
                    list(restored.index.names).index("symbol"),
                    1 - list(restored.index.names).index("symbol"),
                ),
                timezone=index_schema.timezone,
                sorted=bool(restored.index.is_monotonic_increasing),
            )
            metadata = {
                "experiment_id": request.experiment_id,
                "execution_id": request.execution_id,
                "factor_id": spec.factor_id,
                "factor_revision": spec.revision,
                "factor_content_hash": spec.content_hash,
                "lag": spec.lag,
                "warmup": spec.warmup,
                "missing_policy": spec.missing_policy,
                "output_dtype": spec.output_dtype,
                "index_restore_policy": spec.index_restore_policy,
                "data_version": request.data_version,
                "split_id": request.split_id,
                "callable_fingerprint": fingerprint,
                "bound_params": bound_params,
                "required_fields": list(spec.required_fields),
                "input_index_schema": _schema_to_dict(index_schema),
                "output_index_schema": _schema_to_dict(output_schema),
                "timezone": index_schema.timezone,
                "sort_policy": "lexicographic_symbol_eob",
                "duplicate_policy": "reject_duplicate_logical_keys",
                "conversion_policy": "to_datetime_reject_nat_and_collisions",
                "formula_resolver_version": FORMULA_RESOLVER_VERSION,
                "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
                "start": eob.min().isoformat() if len(eob) else "",
                "end": eob.max().isoformat() if len(eob) else "",
                "row_count": int(len(restored)),
                "elapsed_ms": elapsed_ms,
                "warnings": list(warnings),
            }
            values_ref = self._persist_series(
                request,
                kind="factor_values",
                artifact_id=f"{request.execution_id}:values",
                series=restored,
                metadata=metadata,
            )
            mask_ref = self._persist_series(
                request,
                kind="valid_mask",
                artifact_id=f"{request.execution_id}:mask",
                series=mask,
                metadata=metadata,
            )
            provenance = Provenance(
                producer=self._producer,
                data_version=request.data_version,
                code_version=CODE_VERSION,
                experiment_version=request.experiment_id,
                namespace=request.namespace,
                input_refs=(request.brief_ref, request.factor_ref),
            )
            values_hash = series_content_hash(restored)
            mask_hash = series_content_hash(mask)
            # Envelope identity authenticates FactorExecutionResult; callable
            # fingerprint is a first-class field (never smuggled via warnings).
            envelope_fp = execution_envelope_identity_from_parts(
                request_id=request.request_id,
                experiment_id=request.experiment_id,
                execution_id=request.execution_id,
                brief_ref=request.brief_ref,
                factor_ref=factor_ref,
                values_ref=values_ref,
                valid_mask_ref=mask_ref,
                index_schema=index_schema,
                provenance=provenance,
                callable_fingerprint=fingerprint,
                data_version=request.data_version,
                split_id=request.split_id,
                values_content_hash=values_hash,
                valid_mask_content_hash=mask_hash,
                warnings=tuple(warnings),
                failure_code=None,
            )
            return FactorExecutionResult(
                request_id=request.request_id,
                experiment_id=request.experiment_id,
                execution_id=request.execution_id,
                brief_ref=request.brief_ref,
                factor_ref=factor_ref,
                values_ref=values_ref,
                valid_mask_ref=mask_ref,
                index_schema=index_schema,
                provenance=provenance,
                fingerprint=envelope_fp,
                callable_fingerprint=fingerprint,
                data_version=request.data_version,
                split_id=request.split_id,
                values_content_hash=values_hash,
                valid_mask_content_hash=mask_hash,
                warnings=tuple(warnings),
            )
        except (
            PanelAdapterError,
            FormulaAdapterError,
            FactorExecutionAdapterError,
            SeriesCodecError,
            ArtifactStoreAdapterError,
        ) as exc:
            return self._failure_result(
                request=request,
                factor_ref=factor_ref,
                index_schema=index_schema,
                fingerprint=fingerprint,
                code=exc.code,
                message=exc.message,
                cause=exc,
            )
        except Exception as exc:  # noqa: BLE001
            return self._failure_result(
                request=request,
                factor_ref=factor_ref,
                index_schema=index_schema,
                fingerprint=fingerprint,
                code=FailureCode.FACTOR_RUNTIME_FAILED,
                message="factor runtime failed",
                cause=exc,
            )

    def _validate_factor_ref(self, factor_ref: ObjectRef) -> None:
        if factor_ref.object_type != "FactorSpec":
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_REFERENCE,
                "factor_ref.object_type must be FactorSpec",
            )
        if factor_ref.schema_version != SCHEMA_VERSION:
            raise FactorExecutionAdapterError(
                FailureCode.SCHEMA_MISMATCH,
                "factor_ref.schema_version mismatch",
            )

    def _validate_spec_identity(
        self, request: FactorComputeRequest, spec: FactorSpec
    ) -> None:
        try:
            spec.validate_hash()
        except ValueError as exc:
            raise FactorExecutionAdapterError(
                FailureCode.HASH_MISMATCH,
                "FactorSpec content_hash mismatch",
            ) from exc
        if spec.factor_id != request.factor_ref.object_id:
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_REFERENCE,
                "factor_ref.object_id does not match FactorSpec",
            )
        if spec.schema_version != request.factor_ref.schema_version:
            raise FactorExecutionAdapterError(
                FailureCode.SCHEMA_MISMATCH,
                "factor_ref.schema_version does not match FactorSpec",
            )
        if spec.provenance.namespace != request.factor_ref.namespace:
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_REFERENCE,
                "factor_ref.namespace does not match FactorSpec",
            )
        if spec.content_hash != request.factor_ref.content_hash:
            raise FactorExecutionAdapterError(
                FailureCode.HASH_MISMATCH,
                "factor_ref content_hash does not match FactorSpec",
            )
        if not _refs_equal(request.brief_ref, spec.brief_ref):
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_REFERENCE,
                "request.brief_ref does not match FactorSpec.brief_ref",
            )
        if request.data_version != spec.provenance.data_version:
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_REFERENCE,
                "request.data_version does not match FactorSpec provenance",
            )
        if spec.missing_policy != _SUPPORTED_MISSING_POLICY:
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_PARAMETERS,
                "unsupported missing_policy for Phase 02",
            )
        if spec.output_dtype != _SUPPORTED_OUTPUT_DTYPE:
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_OUTPUT_DTYPE,
                "unsupported output_dtype for Phase 02",
            )
        if spec.index_restore_policy != _SUPPORTED_INDEX_RESTORE_POLICY:
            raise FactorExecutionAdapterError(
                FailureCode.INVALID_PARAMETERS,
                "unsupported index_restore_policy for Phase 02",
            )

    def _persist_series(
        self,
        request: FactorComputeRequest,
        *,
        kind: str,
        artifact_id: str,
        series: pd.Series,
        metadata: Mapping[str, Any],
    ) -> ArtifactRef:
        try:
            payload = {
                "series": series_to_payload(series),
                "metadata": dict(metadata),
            }
            if request.sealed_execution:
                put = self._store.put_if_absent(
                    namespace=request.namespace,
                    kind=kind,
                    artifact_id=artifact_id,
                    payload=payload,
                    input_refs=(request.brief_ref, request.factor_ref),
                    meta={"sealed": True, "append_only": True},
                )
                return put.ref if hasattr(put, "ref") else put
            return self._store.put(
                namespace=request.namespace,
                kind=kind,
                artifact_id=artifact_id,
                payload=payload,
                input_refs=(request.brief_ref, request.factor_ref),
            )
        except (
            ArtifactStoreAdapterError,
            SeriesCodecError,
            FactorExecutionAdapterError,
        ):
            raise
        except Exception as exc:  # noqa: BLE001
            raise FactorExecutionAdapterError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "artifact persistence failed",
            ) from exc

    def _failure_result(
        self,
        *,
        request: FactorComputeRequest,
        factor_ref: ObjectRef,
        index_schema: IndexSchema,
        fingerprint: str,
        code: FailureCode,
        message: str,
        cause: BaseException | None,
    ) -> FactorExecutionResult:
        details: dict[str, Any] = {
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "formula_resolver_version": FORMULA_RESOLVER_VERSION,
        }
        if cause is not None:
            details["cause_type"] = type(cause).__name__
        provenance = Provenance(
            producer=self._producer,
            data_version=request.data_version,
            code_version=CODE_VERSION,
            experiment_version=request.experiment_id,
            namespace=request.namespace,
            input_refs=(request.brief_ref, request.factor_ref),
        )
        failure = FailureDetail(
            code=code,
            message=message,
            severity=Severity.HARD_FAIL,
            retryable=False,
            details=details,
        )
        envelope_fp = execution_envelope_identity_from_parts(
            request_id=request.request_id,
            experiment_id=request.experiment_id,
            execution_id=request.execution_id,
            brief_ref=request.brief_ref,
            factor_ref=factor_ref,
            values_ref=None,
            valid_mask_ref=None,
            index_schema=index_schema,
            provenance=provenance,
            callable_fingerprint=fingerprint or ("0" * 64),
            data_version=request.data_version,
            split_id=request.split_id,
            values_content_hash=None,
            valid_mask_content_hash=None,
            warnings=(),
            failure_code=code.value,
        )
        return FactorExecutionResult(
            request_id=request.request_id,
            experiment_id=request.experiment_id,
            execution_id=request.execution_id,
            brief_ref=request.brief_ref,
            factor_ref=factor_ref,
            values_ref=None,
            valid_mask_ref=None,
            index_schema=index_schema,
            provenance=provenance,
            fingerprint=envelope_fp,
            callable_fingerprint=fingerprint or ("0" * 64),
            data_version=request.data_version,
            split_id=request.split_id,
            values_content_hash=None,
            valid_mask_content_hash=None,
            warnings=(),
            failure=failure,
        )


def load_execution_series(store: ArtifactStorePort, ref: ArtifactRef) -> pd.Series:
    """Load a Series previously persisted by ``FactorExecutionAdapter``."""
    payload = store.get(ref)
    series_payload = payload.get("series")
    if not isinstance(series_payload, Mapping):
        raise FactorExecutionAdapterError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "artifact payload missing series encoding",
        )
    return series_from_payload(series_payload)
