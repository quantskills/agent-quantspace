"""Factor screening and parameter sweep commands over the research templates."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skills.cli.io import (
    check_output,
    data_manager,
    factor_function,
    json_safe,
    load_panel,
    read_panel,
    write_frame,
)
from skills.cli.models import CLIModel, CommandResult, PanelSource
from skills.cli.registry import Command

WRITE_HELP = (
    "Persist each indicator's IC, group returns and turnover under "
    "data/factor_test/<namespace>/ (persist=True); otherwise the store is not touched."
)


@contextmanager
def _store_root(data_root):
    """Point the research templates' own DataManager() at the command's data root."""
    if data_root is None:
        yield
        return
    previous = os.environ.get("QUANTSPACE_DATA_ROOT")
    os.environ["QUANTSPACE_DATA_ROOT"] = str(data_manager(data_root).root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("QUANTSPACE_DATA_ROOT", None)
        else:
            os.environ["QUANTSPACE_DATA_ROOT"] = previous


def _namespace(value: str) -> str:
    if not value or value in {".", ".."} or any(char in value for char in "/\\\0"):
        raise ValueError(f"Invalid artifact namespace: {value!r}")
    return value


def _factor_test_files(data_root, namespaces):
    """Snapshot data/factor_test/<namespace>/ files; the templates log persist failures."""
    root = data_manager(data_root).root / "factor_test"
    files = {}
    for namespace in namespaces:
        for path in (root / namespace).rglob("*"):
            if path.is_file():
                stat = path.stat()
                files[path] = (stat.st_mtime_ns, stat.st_size)
    return files


class RankingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Ranking rows.")
    persisted: bool = Field(
        description="Whether factor-test files under data/factor_test/<namespace>/ were "
        "created or updated."
    )
    ranking: list[dict[str, Any]] = Field(
        description="First ranking rows by |IC_IR| (indicator, factor_id, IC_mean, IC_IR, ...)."
    )


def _ranking_result(frame, args, persisted) -> CommandResult:
    warnings = []
    if frame.empty:
        warnings.append(
            "No indicator produced a ranking row; skipped or failed indicators are logged on "
            "stderr."
        )
    elif args.write and not persisted:
        warnings.append(
            "--write was given but no factor-test file was written; persist failures are "
            "logged on stderr."
        )
    artifacts = []
    if args.output:
        artifacts.append(
            write_frame(
                frame,
                args.output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="ranking",
            )
        )
    return CommandResult(
        data=RankingOutput(
            rows=len(frame),
            persisted=persisted,
            ranking=json_safe(frame.head(args.preview).to_dict(orient="records")),
        ),
        artifacts=artifacts,
        warnings=warnings,
    )


class ScreenInput(PanelSource):
    namespace: str = Field(description="Artifact namespace under data/factor_test.")
    horizon: int = Field(default=5, gt=0, description="Holding period n for the IC.")
    groups: int = Field(default=5, ge=2, description="Number of groups g for group_stat.")
    top_k: int = Field(default=0, ge=0, description="Keep the top_k by |IC_IR|; 0 keeps all.")
    indicators: list[str] = Field(
        default_factory=list, description="Indicator subset; empty screens every indicator."
    )
    write: bool = Field(default=False, description=WRITE_HELP)
    output: Path | None = Field(default=None, description="Optional full ranking table.")
    overwrite: bool = Field(default=False, description="Replace an existing ranking file.")


def screen(args: ScreenInput) -> CommandResult:
    from skills.research.factor_screening import screen_all_indicators

    namespace = _namespace(args.namespace)
    panel = load_panel(args)
    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    before = _factor_test_files(args.data_root, [namespace])
    with _store_root(args.data_root):
        ranking = screen_all_indicators(
            namespace=namespace,
            n=args.horizon,
            g=args.groups,
            top_k=args.top_k,
            indicator_names=args.indicators or None,
            persist=args.write,
            data=panel,
        )
    persisted = _factor_test_files(args.data_root, [namespace]) != before
    return _ranking_result(ranking, args, persisted=persisted)


class BatchInput(CLIModel):
    panels: dict[str, Path] = Field(
        description="Panel files by artifact namespace, e.g. etf=etf_panel.parquet."
    )
    n_list: list[int] = Field(
        default_factory=lambda: [1, 5, 20], description="Holding periods screened per namespace."
    )
    groups: int = Field(default=5, ge=2, description="Number of groups g for group_stat.")
    indicators: list[str] = Field(
        default_factory=list, description="Indicator subset; empty screens every indicator."
    )
    write: bool = Field(default=False, description=WRITE_HELP)
    data_root: Path | None = Field(
        None, description="Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/."
    )
    output: Path | None = Field(default=None, description="Optional combined ranking table.")
    overwrite: bool = Field(default=False, description="Replace an existing ranking file.")

    @model_validator(mode="after")
    def check_panels(self):
        if not self.panels:
            raise ValueError("panels cannot be empty")
        for name in self.panels:
            _namespace(name)
        if any(value <= 0 for value in self.n_list):
            raise ValueError("n_list must be positive")
        return self


def batch_screen(args: BatchInput) -> CommandResult:
    from skills.research.factor_screening import batch_evaluate

    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    panels = {name: read_panel(path) for name, path in args.panels.items()}
    before = _factor_test_files(args.data_root, list(panels))
    with _store_root(args.data_root):
        ranking = batch_evaluate(
            namespaces=list(panels),
            n_list=args.n_list,
            g=args.groups,
            indicator_names=args.indicators or None,
            persist=args.write,
            data_by_namespace=panels,
        )
    persisted = _factor_test_files(args.data_root, list(panels)) != before
    return _ranking_result(ranking, args, persisted=persisted)


class SweepInput(PanelSource):
    indicator: str | None = Field(default=None, description="Public skills.compute indicator name.")
    function: str | None = Field(
        default=None, description="Importable module:name factor callable."
    )
    call: Literal["per-symbol", "panel"] = Field(
        default="per-symbol",
        description="per-symbol: Factor(func, **kwargs).calculate(panel, dropna=False); "
        "panel: func(panel, **kwargs) as param_sweep calls it.",
    )
    param_name: str = Field(description="Parameter to sweep.")
    param_range: list[Any] = Field(
        description="Values swept, in order; flag values are JSON-decoded, so 20 is an integer."
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="Other keyword arguments held fixed (base_kwargs)."
    )
    horizon: int = Field(default=5, gt=0, description="Holding period n for the IC.")

    @field_validator("param_range", mode="before")
    @classmethod
    def decode_values(cls, values):
        if not isinstance(values, list):
            return values
        decoded = []
        for value in values:
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            decoded.append(value)
        return decoded

    @model_validator(mode="after")
    def check_inputs(self):
        if bool(self.indicator) == bool(self.function):
            raise ValueError("Exactly one of indicator or function is required")
        if not self.param_range:
            raise ValueError("param_range cannot be empty")
        return self


class SweepOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[dict[str, Any]] = Field(
        description="param_value, IC_mean, IC_std, IC_IR and t_stat per swept value."
    )
    failed: list[Any] = Field(description="Swept values that produced no row.")


def param_sweep(args: SweepInput) -> CommandResult:
    from skills.research.param_sensitivity import param_sweep as sweep

    func = factor_function(args.indicator, args.function)
    if args.call == "per-symbol":
        from skills.compute.wrappers import Factor

        def factor(panel, **kwargs):
            return Factor(func, **kwargs).calculate(panel, dropna=False)

    else:
        factor = func
    result = sweep(
        factor,
        args.param_name,
        args.param_range,
        n=args.horizon,
        base_kwargs=args.params,
        data=load_panel(args),
    )
    done = list(result["param_value"]) if "param_value" in result else []
    failed = [value for value in args.param_range if value not in done]
    warnings = [f"param_sweep produced no row for: {failed}"] if failed else []
    return CommandResult(
        data=SweepOutput(rows=json_safe(result.to_dict(orient="records")), failed=failed),
        warnings=warnings,
    )


COMMANDS = [
    Command(
        "research.screen",
        ScreenInput,
        RankingOutput,
        screen,
        "Screen indicators on a panel and rank them by |IC_IR|.",
        side_effects=("writes-store",),
    ),
    Command(
        "research.batch-screen",
        BatchInput,
        RankingOutput,
        batch_screen,
        "Screen indicators across namespace panels and holding periods.",
        side_effects=("writes-store",),
        priority="P2",
    ),
    Command(
        "research.param-sweep",
        SweepInput,
        SweepOutput,
        param_sweep,
        "Sweep one factor parameter and report IC statistics per value.",
    ),
]
