"""Discover and validate factor-mining contracts from the shared CLI."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from skills.cli.io import check_output, import_function, load_panel, read_json, write_json
from skills.cli.models import CLIModel, CommandResult, PanelSource
from skills.cli.registry import Command


class TypesInput(CLIModel):
    pass


class TypeInput(CLIModel):
    type_name: str = Field(description="Exported factor-mining contract dataclass name.")


class TemplateInput(TypeInput):
    output: Path | None = Field(default=None, description="Optional plain contract JSON output.")
    overwrite: bool = Field(default=False, description="Replace an existing output file.")
    data_root: Path | None = Field(default=None, description="Optional output path guard root.")


class ValidateInput(TypeInput):
    file: Path | None = Field(
        default=None, description="JSON contract file; omit or use - for stdin."
    )
    fill_hash: bool = Field(
        default=False, description="Fill an absent content_hash using the domain constructor."
    )
    output: Path | None = Field(default=None, description="Optional validated JSON output path.")
    overwrite: bool = Field(default=False, description="Replace an existing output file.")
    data_root: Path | None = Field(default=None, description="Optional output path guard root.")


class CheckFunctionInput(PanelSource):
    function: str = Field(description="Importable factor callable as module:name.")
    params: dict[str, Any] = Field(
        default_factory=dict, description="JSON keyword arguments passed to the factor."
    )
    required_fields: list[str] = Field(
        default_factory=lambda: ["close", "volume"],
        description="Panel columns required by the factor.",
    )


class TypesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(description="Current factor-mining contract version.")
    types: list[str] = Field(description="Exported dataclass contract types.")


class SchemaOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type_name: str = Field(description="Selected contract type.")
    json_schema: dict[str, Any] = Field(description="Pydantic JSON Schema for the dataclass.")


class TemplateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type_name: str = Field(description="Selected contract type.")
    template: dict[str, Any] = Field(description="Fillable JSON skeleton.")


class ValidateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type_name: str = Field(description="Validated contract type.")
    value: dict[str, Any] = Field(description="Canonical validated contract payload.")
    content_hash: str | None = Field(description="Verified domain content hash where supported.")


class CheckFunctionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    function: str = Field(description="Validated callable reference.")
    rows: int = Field(description="Factor result row count.")
    checked_prefixes: int = Field(description="Number of prefix causality checks.")
    required_fields: list[str] = Field(description="Required input fields checked.")


def _type_names() -> list[str]:
    from skills.factor_mining import contracts

    return [
        name
        for name in contracts.__all__
        if isinstance(getattr(contracts, name, None), type)
        and is_dataclass(getattr(contracts, name))
    ]


def _contract_type(name: str) -> type:
    from skills.factor_mining import contracts

    if name not in _type_names():
        raise ValueError(f"Unknown factor-mining contract type: {name}")
    return getattr(contracts, name)


def _types(_: TypesInput) -> CommandResult:
    from skills.factor_mining.contracts import SCHEMA_VERSION

    return CommandResult(data=TypesOutput(schema_version=SCHEMA_VERSION, types=_type_names()))


def _schema(args: TypeInput) -> CommandResult:
    return CommandResult(
        data=SchemaOutput(
            type_name=args.type_name,
            json_schema=TypeAdapter(_contract_type(args.type_name)).json_schema(),
        )
    )


def _skeleton(schema: dict, defs: dict) -> Any:
    if "$ref" in schema:
        return _skeleton(defs[schema["$ref"].rsplit("/", 1)[-1]], defs)
    if "default" in schema:
        return schema["default"]
    if "anyOf" in schema:
        candidates = [item for item in schema["anyOf"] if item.get("type") != "null"]
        return _skeleton(candidates[0], defs) if candidates else None
    if schema.get("type") == "object":
        return {name: _skeleton(item, defs) for name, item in schema.get("properties", {}).items()}
    if schema.get("type") == "array":
        return []
    if "enum" in schema:
        return schema["enum"][0]
    return None


def _template(args: TemplateInput) -> CommandResult:
    schema = TypeAdapter(_contract_type(args.type_name)).json_schema()
    template = _skeleton(schema, schema.get("$defs", {}))
    artifacts = (
        [
            write_json(
                template,
                args.output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="template",
            )
        ]
        if args.output
        else []
    )
    return CommandResult(
        data=TemplateOutput(type_name=args.type_name, template=template), artifacts=artifacts
    )


def _validate(args: ValidateInput) -> CommandResult:
    from skills.factor_mining.contracts import rebuild_dataclass, to_plain_dict

    cls = _contract_type(args.type_name)
    payload = read_json(args.file or Path("-"))
    if not isinstance(payload, dict):
        raise ValueError("Contract JSON must be an object")
    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    if (
        not args.fill_hash
        and "content_hash" in {item.name for item in fields(cls)}
        and not payload.get("content_hash")
    ):
        raise ValueError("content_hash is absent; pass --fill-hash to calculate it")
    TypeAdapter(cls).validate_python(payload)
    value = rebuild_dataclass(cls, payload)
    if hasattr(value, "validate_hash"):
        value.validate_hash()
    plain = to_plain_dict(value)
    artifacts = (
        [
            write_json(
                plain,
                args.output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="contract",
            )
        ]
        if args.output
        else []
    )
    return CommandResult(
        data=ValidateOutput(
            type_name=args.type_name, value=plain, content_hash=plain.get("content_hash")
        ),
        artifacts=artifacts,
    )


def _check_function(args: CheckFunctionInput) -> CommandResult:
    import pandas as pd

    from skills.compute.wrappers import Factor

    panel = load_panel(args)
    missing = sorted(set(args.required_fields) - set(panel.columns))
    if missing:
        raise ValueError(f"Panel is missing required fields: {missing}")
    factor = Factor(import_function(args.function), **args.params)
    full = factor.calculate(panel, dropna=False)
    checked = 0
    for symbol in panel.index.get_level_values("symbol").unique():
        group = panel.xs(symbol, level="symbol", drop_level=True).sort_index()
        for k in sorted({max(1, len(group) // 3), max(1, 2 * len(group) // 3)}):
            if k >= len(group):
                continue
            prefix_panel = pd.concat({symbol: group.iloc[:k]}, names=["symbol", "eob"])
            prefix = factor.calculate(prefix_panel, dropna=False)
            expected = full.loc[prefix.index]
            try:
                pd.testing.assert_series_equal(
                    prefix, expected, check_names=False, check_exact=False, rtol=1e-12, atol=1e-12
                )
            except AssertionError as exc:
                raise ValueError(f"Factor is not prefix causal for {symbol} at {k} rows") from exc
            checked += 1
    return CommandResult(
        data=CheckFunctionOutput(
            function=args.function,
            rows=len(full),
            checked_prefixes=checked,
            required_fields=args.required_fields,
        )
    )


COMMANDS = [
    Command(
        "factor-mining.types",
        TypesInput,
        TypesOutput,
        _types,
        "List factor-mining contract types.",
        priority="P0",
    ),
    Command(
        "factor-mining.schema",
        TypeInput,
        SchemaOutput,
        _schema,
        "Show a contract JSON Schema.",
        priority="P0",
        positional=("type_name",),
    ),
    Command(
        "factor-mining.template",
        TemplateInput,
        TemplateOutput,
        _template,
        "Generate a fillable contract skeleton.",
        side_effects=("writes-output",),
        priority="P0",
        positional=("type_name",),
    ),
    Command(
        "factor-mining.validate",
        ValidateInput,
        ValidateOutput,
        _validate,
        "Validate a contract and its content hash.",
        side_effects=("read-only", "writes-output"),
        priority="P0",
        positional=("type_name",),
    ),
    Command(
        "factor-mining.check-function",
        CheckFunctionInput,
        CheckFunctionOutput,
        _check_function,
        "Check a factor function's required fields and prefix causality.",
    ),
]
