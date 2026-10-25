"""The qs runner: one JSON envelope on stdout, model-driven parsing, safe file transport."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from enum import Enum
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import BaseModel, ConfigDict, Field

from skills.cli.models import CLIError, CLIModel, CommandResult
from skills.cli.registry import Command


def invoke(capsys, *args):
    from skills.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


class SampleOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


def install(monkeypatch, handler, input_model=CLIModel, output_model=SampleOutput, **options):
    import skills.cli as cli

    command = Command("sample.run", input_model, output_model, handler, "Sample", **options)
    monkeypatch.setattr(cli, "get_commands", lambda *_: {command.name: command})
    return command


# ---------------------------------------------------------------------------
# Envelope, discovery and argument parsing
# ---------------------------------------------------------------------------


def test_no_arguments_print_usage(capsys):
    from skills.cli import main

    assert main([]) == 0
    assert "Usage: qs <skill> <command>" in capsys.readouterr().out


def test_unknown_command_is_a_json_error(capsys):
    code, result = invoke(capsys, "not-a-skill")
    assert code == 2
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_group_help_lists_commands_and_unknown_group_fails(capsys):
    from skills.cli import main

    assert main(["compute", "indicators", "--help"]) == 0
    listing = capsys.readouterr().out
    assert "compute indicators list:" in listing
    assert "compute indicators show:" in listing
    code, result = invoke(capsys, "compute", "nothing", "--help")
    assert code == 2 and result["error"]["code"] == "INVALID_INPUT"


def test_command_help_is_model_generated(capsys):
    from skills.cli import main

    assert main(["backtest", "run", "--help"]) == 0
    text = capsys.readouterr().out
    assert "--slippage-bp" in text and "--weights" in text
    assert "qs schema" in text


def test_json_flags_and_parameter_override(monkeypatch, tmp_path, capsys):
    class Input(CLIModel):
        count: int = Field(description="Count")
        params: dict = Field(default_factory=dict, description="Parameters")
        enabled: bool = Field(False, description="Enabled")
        symbols: list[str] = Field(default_factory=list, description="Symbols")

    def handle(args):
        print("progress lines belong to stderr")
        return CommandResult(data=args.model_dump())

    install(monkeypatch, handle, Input)
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"count": 1, "params": {"x": 1, "y": "a"}, "enabled": True}))
    code, result = invoke(
        capsys,
        *["sample", "run", "--input-json", str(path), "--count", "3", "--no-enabled"],
        *["-p", "x=2", "-p", "z=text", "--symbols", "A,B", "--symbols", "C"],
    )
    assert code == 0, result
    assert result["data"] == {
        "count": 3,
        "params": {"x": 2, "y": "a", "z": "text"},
        "enabled": False,
        "symbols": ["A", "B", "C"],
    }
    code, result = invoke(capsys, "sample", "run", "--input-json", str(path), "--bogus", "1")
    assert code == 2 and result["error"]["code"] == "INVALID_INPUT"


def test_p_requires_a_params_field(monkeypatch, capsys):
    class Input(CLIModel):
        count: int = Field(1, description="Count")

    install(monkeypatch, lambda args: CommandResult(data={}), Input)
    code, result = invoke(capsys, "sample", "run", "-p", "x=1")
    assert code == 2 and "does not accept -p" in result["error"]["message"]
    code, result = invoke(capsys, "sample", "run", "-p", "novalue")
    assert code == 2 and "key=value" in result["error"]["message"]


def test_input_json_from_stdin_and_environment_is_not_an_input(monkeypatch, capsys):
    class Input(CLIModel):
        count: int = Field(description="Count")

    install(monkeypatch, lambda args: CommandResult(data={"count": args.count}), Input)
    monkeypatch.setenv("COUNT", "999")
    monkeypatch.setattr("sys.stdin", StringIO('{"count": 2}'))
    code, result = invoke(capsys, "sample", "run", "--input-json", "-")
    assert code == 0 and result["data"] == {"count": 2}
    monkeypatch.setattr("sys.stdin", StringIO("[1, 2]"))
    code, result = invoke(capsys, "sample", "run", "--input-json", "-")
    assert code == 2 and "JSON object" in result["error"]["message"]


def test_missing_required_field_reports_validation_details(monkeypatch, capsys):
    class Input(CLIModel):
        path: Path = Field(description="Required path")

    install(monkeypatch, lambda args: CommandResult(data={}), Input)
    code, result = invoke(capsys, "sample", "run")
    assert code == 2
    assert result["error"]["code"] == "INVALID_INPUT"
    assert result["error"]["details"][0]["loc"] == ["path"]


def test_schema_and_template_do_not_need_command_arguments(monkeypatch, capsys):
    class Input(CLIModel):
        path: Path = Field(description="Required path")
        count: int = Field(3, description="Count")

    install(monkeypatch, lambda args: CommandResult(data={}), Input)
    code, result = invoke(capsys, "sample", "run", "--print-template")
    assert code == 0 and result["data"] == {"path": "", "count": 3}


def test_transport_switches_preview_and_log_level(monkeypatch, capsys):
    install(monkeypatch, lambda args: CommandResult(data={"preview": args.preview}))
    code, result = invoke(capsys, "sample", "run", "--preview", "7")
    assert code == 0 and result["data"] == {"preview": 7}
    code, result = invoke(capsys, "sample", "run", "--preview", "101")
    assert code == 2 and "--preview" in result["error"]["message"]
    code, result = invoke(capsys, "sample", "run", "--log-level", "LOUD")
    assert code == 2 and "log level" in result["error"]["message"]


def test_output_that_breaks_its_schema_is_internal(monkeypatch, capsys):
    class Output(BaseModel):
        rows: int

    install(monkeypatch, lambda args: CommandResult(data={"oops": 1}), output_model=Output)
    code, result = invoke(capsys, "sample", "run")
    assert code == 1 and result["error"]["code"] == "INTERNAL"


@pytest.mark.parametrize(
    ("exc", "code", "status"),
    [
        (CLIError("CONFLICT", "exists"), "CONFLICT", 2),
        (FileNotFoundError("missing.parquet"), "NOT_FOUND", 3),
        (ImportError("No module named x"), "MISSING_DEPENDENCY", 3),
        (TimeoutError("slow"), "TIMEOUT", 124),
        (ValueError("bad"), "INVALID_INPUT", 2),
        (ConnectionError("down"), "UPSTREAM_ERROR", 4),
        (RuntimeError("bug"), "INTERNAL", 1),
    ],
)
def test_exceptions_map_to_error_codes(monkeypatch, capsys, exc, code, status):
    def handle(args):
        raise exc

    install(monkeypatch, handle)
    result_code, result = invoke(capsys, "sample", "run")
    assert result_code == status
    assert result["ok"] is False and result["error"]["code"] == code
    assert "data" not in result


@pytest.mark.parametrize(
    ("exit_code", "code"),
    [(1, "CHECK_FAILED"), (2, "INVALID_INPUT"), (3, "NOT_FOUND"), (124, "TIMEOUT")],
)
def test_nonzero_result_keeps_data_and_reports_failed_checks(monkeypatch, capsys, exit_code, code):
    install(monkeypatch, lambda args: CommandResult(data={"passed": False}, exit_code=exit_code))
    result_code, result = invoke(capsys, "sample", "run")
    assert result_code == exit_code
    assert result["ok"] is False and result["error"]["code"] == code
    assert result["data"] == {"passed": False}


def test_nonfinite_values_become_null(monkeypatch, capsys):
    install(monkeypatch, lambda args: CommandResult(data={"sharpe": float("nan"), "x": np.inf}))
    code, result = invoke(capsys, "sample", "run")
    assert code == 0 and result["data"] == {"sharpe": None, "x": None}


def test_oversized_output_spills_to_a_file(monkeypatch, tmp_path, capsys):
    import tempfile

    rows = [{"index": i, "text": "x" * 50} for i in range(2000)]
    install(monkeypatch, lambda args: CommandResult(data={"rows": rows}))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    code, result = invoke(capsys, "sample", "run")
    assert code == 0
    assert result["data"]["rows"]["summarized"] is True
    assert result["data"]["rows"]["count"] == 2000
    full = [item for item in result["artifacts"] if item["name"] == "full_output"]
    assert len(full) == 1 and Path(full[0]["path"]).parent == tmp_path / "qs-output"
    assert json.loads(Path(full[0]["path"]).read_text())["data"]["rows"] == rows
    assert any("stdout budget" in warning for warning in result["warnings"])


def test_entry_point_forces_headless_matplotlib(monkeypatch, capsys):
    from skills.cli import main

    monkeypatch.delenv("MPLBACKEND", raising=False)
    main([])
    capsys.readouterr()
    import os

    assert os.environ["MPLBACKEND"] == "Agg"
    monkeypatch.setenv("MPLBACKEND", "pdf")
    main([])
    assert os.environ["MPLBACKEND"] == "pdf"


def test_version_catalog_and_schema(capsys):
    from skills.cli.registry import SKILLS, get_commands

    code, result = invoke(capsys, "version")
    assert code == 0
    assert result["data"]["factor_mining_schema_version"]
    assert set(result["data"]["extras"]) == {"analyze", "ml", "report", "query", "ts", "panda_data"}
    code, result = invoke(capsys, "catalog")
    assert code == 0
    listed = {entry["command"] for entry in result["data"]["commands"]}
    assert listed == set(get_commands())
    assert {name.split(".")[0] for name in listed} == set(SKILLS)
    code, result = invoke(capsys, "catalog", "--skill", "store", "--format", "markdown")
    assert code == 0 and "| store.read |" in result["data"]["markdown"]
    code, result = invoke(capsys, "catalog", "--skill", "nope")
    assert code == 2
    code, result = invoke(capsys, "schema", "store.read", "--part", "input")
    assert code == 0 and result["data"]["additionalProperties"] is False
    code, result = invoke(capsys, "schema", "analyze.preflight", "--file-field", "spec_json")
    assert code == 0 and "factor_id" in result["data"]["properties"]
    code, result = invoke(capsys, "schema", "store.nothing")
    assert code == 2 and "Unknown command" in result["error"]["message"]


def test_skill_command_loads_only_its_adapter(monkeypatch, capsys):
    import skills.cli.registry as registry

    loaded = []
    original = registry.import_module

    def tracking(name):
        loaded.append(name)
        return original(name)

    monkeypatch.setattr(registry, "import_module", tracking)
    code, _ = invoke(capsys, "compute", "indicators", "list")
    assert code == 0
    assert [name for name in loaded if name.endswith(".cli")] == ["skills.compute.cli"]


# ---------------------------------------------------------------------------
# File transport
# ---------------------------------------------------------------------------


def test_command_store_never_creates_the_data_root(tmp_path):
    from skills.cli.io import data_manager

    store = data_manager(tmp_path / "absent")
    assert store.root == tmp_path / "absent"
    assert store.list_symbols("1d") == []
    assert not store.root.exists()


@pytest.mark.parametrize(
    "namespace",
    ["market", "adj_factor", "factors", "correlation", "backtest", "models"],
)
def test_outputs_never_target_managed_namespaces(tmp_path, namespace):
    from skills.cli.io import check_output

    root = tmp_path / "data"
    with pytest.raises(CLIError, match="managed store namespace"):
        check_output(root / namespace / "x.parquet", data_root=root)
    assert not root.exists()


def test_managed_guard_follows_symlinks_and_the_environment_root(tmp_path, monkeypatch):
    from skills.cli.io import check_output

    store = tmp_path / "store"
    (store / "market").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(store / "market", target_is_directory=True)
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(store))
    with pytest.raises(CLIError):
        check_output(alias / "new.parquet", data_root=tmp_path / "other")


def test_write_frame_refuses_overwrite_and_keeps_the_original(tmp_path):
    from skills.cli.io import write_frame

    frame = pd.DataFrame(
        {"a": [1.0, 2.0]}, index=pd.date_range("2024-01-01", periods=2, name="eob")
    )
    output = tmp_path / "out" / "a.parquet"
    artifact = write_frame(frame, output, name="table")
    assert artifact.model_dump() == {
        "name": "table",
        "path": str(output.resolve()),
        "format": "parquet",
        "rows": 2,
        "columns": ["a"],
    }
    with pytest.raises(CLIError, match="exists"):
        write_frame(frame * 10, output)
    pd.testing.assert_frame_equal(pd.read_parquet(output), frame, check_freq=False)
    write_frame(frame * 10, output, overwrite=True)
    assert pd.read_parquet(output)["a"].tolist() == [10.0, 20.0]
    csv = write_frame(frame, tmp_path / "a.csv")
    assert csv.format == "csv"
    assert (tmp_path / "a.csv").read_text().splitlines()[0] == "eob,a"
    with pytest.raises(ValueError, match="parquet or .csv"):
        write_frame(frame, tmp_path / "a.xlsx")
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == ["a.parquet"]


def test_write_json_bytes_and_lines(tmp_path):
    from skills.cli.io import write_bytes, write_json, write_lines

    artifact = write_json({"x": float("nan"), "when": date(2024, 1, 2)}, tmp_path / "a.json")
    assert json.loads((tmp_path / "a.json").read_text()) == {"x": None, "when": "2024-01-02"}
    assert artifact.format == "json"
    png = write_bytes(b"\x89PNG", tmp_path / "c.png", name="chart")
    assert (png.name, png.format) == ("chart", "png")
    assert (tmp_path / "c.png").read_bytes() == b"\x89PNG"
    with pytest.raises(CLIError):
        write_bytes(b"other", tmp_path / "c.png")
    lines = write_lines(["甲", "B"], tmp_path / "s.txt")
    assert (tmp_path / "s.txt").read_text(encoding="utf-8") == "甲\nB\n" and lines.rows == 2


def test_read_frame_parses_compact_dates_and_rejects_other_formats(tmp_path):
    from skills.cli.io import read_frame

    path = tmp_path / "dates.csv"
    path.write_text("eob,close\n20240101,10\n20240102,11\n")
    frame = read_frame(path)
    assert frame.index.equals(pd.DatetimeIndex(["2024-01-01", "2024-01-02"], name="eob"))
    with pytest.raises(ValueError, match="Parquet or CSV"):
        read_frame(tmp_path / "x.json")


def test_read_panel_accepts_long_and_multiindex_and_rejects_duplicates(tmp_path):
    from skills.cli.io import read_panel

    frame = pd.DataFrame(
        {"symbol": ["A", "A"], "eob": pd.date_range("2024-01-01", periods=2), "close": [1.0, 2.0]}
    )
    path = tmp_path / "p.parquet"
    frame.to_parquet(path)
    long = read_panel(path)
    assert long.index.names == ["symbol", "eob"]
    long.to_parquet(path)
    pd.testing.assert_frame_equal(read_panel(path), long)
    frame.loc[1, "eob"] = frame.loc[0, "eob"]
    frame.to_parquet(path)
    with pytest.raises(ValueError, match="duplicate"):
        read_panel(path)


def test_load_panel_filters_dates_fields_and_needs_one_source(tmp_path):
    from skills.cli.io import load_panel
    from skills.cli.models import PanelSource

    path = tmp_path / "p.parquet"
    pd.DataFrame(
        {
            "symbol": ["A"] * 3,
            "eob": pd.to_datetime(["2024-01-01 15:00", "2024-01-02 15:00", "2024-01-03 15:00"]),
            "close": [1.0, 2.0, 3.0],
            "volume": [1.0, 1.0, 1.0],
        }
    ).to_parquet(path)
    assert len(load_panel(PanelSource(panel=path, end="20240102"))) == 2
    assert len(load_panel(PanelSource(panel=path, start="2024-01-02"))) == 2
    assert list(load_panel(PanelSource(panel=path, fields=["close"])).columns) == ["close"]
    with pytest.raises(ValueError, match="Missing panel fields"):
        load_panel(PanelSource(panel=path, fields=["open"]))
    with pytest.raises(ValueError, match="exactly one"):
        load_panel(PanelSource(panel=path, symbols=["A"]))
    with pytest.raises(ValueError, match="empty"):
        load_panel(PanelSource(panel=path, start="2025-01-01"))
    with pytest.raises(ValueError, match="after end"):
        load_panel(PanelSource(panel=path, start="2024-01-03", end="2024-01-01"))


def test_load_panel_reads_the_store_without_creating_it(tmp_path):
    from skills.cli.io import load_panel
    from skills.cli.models import PanelSource
    from skills.store.data_manager import DataManager
    from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet

    root = tmp_path / "data"
    write_symbol_parquet(root, "SHSE.510300", make_ohlcv())
    panel = load_panel(PanelSource(symbols=["SHSE.510300"], data_root=root))
    assert sorted(path.name for path in root.rglob("*")) == ["1d", "SHSE.510300.parquet", "market"]
    expected = DataManager(data_root=str(root)).read_symbols(["SHSE.510300"], frequency="1d")
    pd.testing.assert_frame_equal(panel, expected)


def test_symbols_are_split_deduplicated_and_never_paths(tmp_path):
    from skills.cli.io import resolve_symbols, validate_symbol

    assert resolve_symbols(["A,B", "B", " C "]) == ["A", "B", "C"]
    listing = tmp_path / "symbols.json"
    listing.write_text('["X", "Y"]')
    assert resolve_symbols([], listing) == ["X", "Y"]
    with pytest.raises(ValueError, match="not both"):
        resolve_symbols(["A"], listing)
    for bad in ("", ".", "..", "a/b", "a\\b", "a\x00"):
        with pytest.raises(ValueError):
            validate_symbol(bad)


def test_json_safe_converts_scientific_values_and_refuses_tables():
    from skills.cli.io import json_safe

    class Color(Enum):
        RED = "red"

    @dataclass
    class Point:
        x: float

    value = {
        "np": np.float64(1.5),
        "int": np.int64(2),
        "nan": math.nan,
        "nat": pd.NaT,
        "enum": Color.RED,
        "point": Point(np.float32(0.5)),
        "path": Path("a/b"),
        "day": date(2024, 1, 1),
        "items": (1, {2}),
        "index": pd.Index([1, 2]),
    }
    assert json_safe(value) == {
        "np": 1.5,
        "int": 2,
        "nan": None,
        "nat": None,
        "enum": "red",
        "point": {"x": 0.5},
        "path": "a/b",
        "day": "2024-01-01",
        "items": [1, [2]],
        "index": [1, 2],
    }
    with pytest.raises(TypeError, match="artifacts"):
        json_safe({"table": pd.DataFrame({"a": [1]})})


def test_function_references_resolve_indicators_and_callables():
    from skills.cli.io import factor_function, import_function
    from skills.compute.indicators import discover_indicators

    assert factor_function(indicator="roc") is discover_indicators()["roc"]
    assert factor_function(function="skills.compute.indicators:roc") is discover_indicators()["roc"]
    with pytest.raises(CLIError, match="Unknown indicator"):
        factor_function(indicator="no_such_indicator")
    with pytest.raises(ValueError, match="module:name"):
        import_function("skills.compute.indicators.roc")
    with pytest.raises(ValueError, match="Not a callable"):
        import_function("skills.cli.io:MANAGED")
    with pytest.raises(CLIError, match="has no attribute no_such_name") as caught:
        import_function("skills.cli.io:no_such_name")
    assert caught.value.code == "INVALID_INPUT"
