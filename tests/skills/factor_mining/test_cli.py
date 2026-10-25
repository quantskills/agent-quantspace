"""Tests for the ``qs factor-mining`` command adapters."""

from __future__ import annotations

import io
import json
import sys
import types
from dataclasses import is_dataclass

import numpy as np
import pandas as pd
import pytest
from pydantic import TypeAdapter

from skills.cli import main
from skills.compute.wrappers import Factor
from skills.factor_mining import contracts
from skills.factor_mining.contracts import SCHEMA_VERSION, to_plain_dict
from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet
from tests.skills.factor_mining.builders import make_brief, make_factor_spec


def run(capsys, *argv):
    capsys.readouterr()
    code = main(["factor-mining", *argv])
    return code, json.loads(capsys.readouterr().out)


def assert_error(code, body, name, status):
    assert code == status, body
    assert body["ok"] is False
    assert body["error"]["code"] == name, body


@pytest.fixture(autouse=True)
def isolated_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "data_root"))
    monkeypatch.setenv("QUANTSPACE_REPORTS_ROOT", str(tmp_path / "reports_root"))


def contract_types() -> list[str]:
    return [
        name
        for name in contracts.__all__
        if isinstance(getattr(contracts, name, None), type)
        and is_dataclass(getattr(contracts, name))
    ]


# ---------------------------------------------------------------------------
# types, schema, template
# ---------------------------------------------------------------------------


def test_types_lists_the_exported_dataclass_contracts(capsys):
    code, body = run(capsys, "types")
    assert code == 0 and body["ok"], body
    assert body["data"]["schema_version"] == SCHEMA_VERSION
    assert body["data"]["types"] == contract_types()
    assert {"FactorSpec", "ResearchBrief", "EvaluationReport", "SplitWindow"} <= set(
        body["data"]["types"]
    )
    # Enums and helper functions are not contract types.
    assert "Severity" not in body["data"]["types"]
    assert "content_hash" not in body["data"]["types"]


@pytest.mark.parametrize("type_name", ["FactorSpec", "ResearchBrief", "SplitWindow", "ObjectRef"])
def test_schema_equals_the_dataclass_json_schema(capsys, type_name):
    code, body = run(capsys, "schema", type_name)
    assert code == 0, body
    assert body["data"]["type_name"] == type_name
    assert body["data"]["json_schema"] == TypeAdapter(getattr(contracts, type_name)).json_schema()


def test_schema_and_template_reject_unknown_types(capsys):
    for command in ("schema", "template", "validate"):
        code, body = run(capsys, command, "NotAContract")
        assert_error(code, body, "INVALID_INPUT", 2)
        assert "NotAContract" in body["error"]["message"] or command == "validate"
    code, body = run(capsys, "schema", "Severity")  # an enum, not a dataclass contract
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "schema")
    assert_error(code, body, "INVALID_INPUT", 2)


def test_template_is_a_fillable_skeleton_of_the_schema(capsys, tmp_path):
    schema = TypeAdapter(contracts.FactorSpec).json_schema()
    code, body = run(capsys, "template", "FactorSpec")
    assert code == 0, body
    template = body["data"]["template"]
    assert body["data"]["type_name"] == "FactorSpec" and body["artifacts"] == []
    assert set(template) == set(schema["properties"])
    assert template["revision"] == schema["properties"]["revision"].get("default")
    assert template["required_fields"] == []
    assert isinstance(template["brief_ref"], dict)


def test_template_writes_plain_json_and_guards_overwrites(capsys, tmp_path):
    output = tmp_path / "out" / "spec_template.json"
    code, body = run(capsys, "template", "SplitWindow", "--output", str(output))
    assert code == 0, body
    assert json.loads(output.read_text()) == body["data"]["template"]
    assert body["artifacts"] == [
        {
            "name": "template",
            "path": str(output.resolve()),
            "format": "json",
            "rows": None,
            "columns": [],
        }
    ]
    output.write_text("keep me")
    code, body = run(capsys, "template", "SplitWindow", "--output", str(output))
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_text() == "keep me"
    code, body = run(capsys, "template", "SplitWindow", "--output", str(output), "--overwrite")
    assert code == 0, body
    assert output.read_text() != "keep me"
    managed = tmp_path / "root" / "market" / "1d" / "t.json"
    code, body = run(
        capsys, "template", "SplitWindow", "--output", str(managed),
        "--data-root", str(tmp_path / "root"),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert not managed.exists()


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def spec_payload():
    spec = make_factor_spec()
    return spec, to_plain_dict(spec)


def write_json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


def test_validate_returns_the_canonical_payload_and_verified_hash(capsys, tmp_path):
    spec, payload = spec_payload()
    path = write_json(tmp_path, "spec.json", payload)
    out = tmp_path / "validated.json"
    code, body = run(capsys, "validate", "FactorSpec", "--file", str(path), "--output", str(out))
    assert code == 0, body
    assert body["data"] == {
        "type_name": "FactorSpec",
        "value": payload,
        "content_hash": spec.content_hash,
    }
    assert json.loads(out.read_text()) == payload
    assert body["artifacts"][0]["name"] == "contract"
    brief = make_brief()
    brief_path = write_json(tmp_path, "brief.json", to_plain_dict(brief))
    code, body = run(capsys, "validate", "ResearchBrief", "--file", str(brief_path))
    assert code == 0 and body["data"]["content_hash"] == brief.content_hash


def test_validate_reads_stdin_when_the_file_is_omitted_or_dash(capsys, monkeypatch):
    spec, payload = spec_payload()
    for argv in (["validate", "FactorSpec"], ["validate", "FactorSpec", "--file", "-"]):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        code, body = run(capsys, *argv)
        assert code == 0, body
        assert body["data"]["content_hash"] == spec.content_hash


def test_validate_types_without_a_hash_report_none(capsys, tmp_path):
    window = make_brief().train
    path = write_json(tmp_path, "window.json", to_plain_dict(window))
    code, body = run(capsys, "validate", "SplitWindow", "--file", str(path))
    assert code == 0, body
    assert body["data"]["content_hash"] is None
    assert body["data"]["value"] == to_plain_dict(window)


def test_validate_needs_fill_hash_for_an_absent_hash(capsys, tmp_path):
    spec, payload = spec_payload()
    payload.pop("content_hash")
    path = write_json(tmp_path, "nohash.json", payload)
    code, body = run(capsys, "validate", "FactorSpec", "--file", str(path))
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "--fill-hash" in body["error"]["message"]
    code, body = run(capsys, "validate", "FactorSpec", "--file", str(path), "--fill-hash")
    assert code == 0, body
    assert body["data"]["content_hash"] == spec.content_hash
    assert body["data"]["value"]["content_hash"] == spec.content_hash


def test_validate_rejects_a_forged_hash_even_with_fill_hash(capsys, tmp_path):
    _, payload = spec_payload()
    payload["content_hash"] = "0" * 64
    path = write_json(tmp_path, "forged.json", payload)
    out = tmp_path / "validated.json"
    for extra in ([], ["--fill-hash"]):
        code, body = run(
            capsys, "validate", "FactorSpec", "--file", str(path), "--output", str(out), *extra
        )
        assert_error(code, body, "INVALID_INPUT", 2)
    assert not out.exists()


def test_validate_input_errors_and_output_conflict(capsys, tmp_path):
    spec, payload = spec_payload()
    path = write_json(tmp_path, "spec.json", payload)
    code, body = run(capsys, "validate", "FactorSpec", "--file", str(tmp_path / "missing.json"))
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(
        capsys, "validate", "FactorSpec", "--file", str(write_json(tmp_path, "list.json", [1]))
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    incomplete = dict(payload)
    incomplete.pop("family")
    code, body = run(
        capsys,
        "validate",
        "FactorSpec",
        "--file",
        str(write_json(tmp_path, "bad.json", incomplete)),
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    out = tmp_path / "validated.json"
    out.write_text("keep me")
    code, body = run(capsys, "validate", "FactorSpec", "--file", str(path), "--output", str(out))
    assert_error(code, body, "CONFLICT", 2)
    assert out.read_text() == "keep me"
    code, body = run(
        capsys, "validate", "FactorSpec", "--file", str(path), "--output", str(out), "--overwrite"
    )
    assert code == 0 and json.loads(out.read_text()) == payload


# ---------------------------------------------------------------------------
# check-function
# ---------------------------------------------------------------------------


def momentum(frame, period=5):
    return frame["close"].pct_change(period)


def look_ahead(frame, period=5):
    # Divides by a full-sample statistic, so a shorter history changes earlier values.
    return frame["close"] / frame["close"].mean() - 1.0


def needs_volume(frame):
    return frame["volume"].rolling(3).mean()


@pytest.fixture
def factor_module(monkeypatch):
    module = types.ModuleType("fake_factor_module")
    for function in (momentum, look_ahead, needs_volume):
        setattr(module, function.__name__, function)
    monkeypatch.setitem(sys.modules, "fake_factor_module", module)
    return module


def random_panel(symbols=("S0", "S1", "S2"), periods=90, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for symbol in symbols:
        prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, periods)))
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


@pytest.fixture
def panel_file(tmp_path):
    panel = random_panel()
    path = tmp_path / "panel.parquet"
    panel.to_parquet(path)
    return panel, path


def test_check_function_accepts_a_causal_factor(capsys, panel_file, factor_module):
    panel, path = panel_file
    expected = Factor(momentum, period=7).calculate(panel, dropna=False)
    code, body = run(
        capsys, "check-function", "--panel", str(path),
        "--function", "fake_factor_module:momentum", "--params", '{"period": 7}',
    )  # fmt: skip
    assert code == 0, body
    # Two distinct prefix lengths (a third and two thirds of 90 bars) per symbol.
    assert body["data"] == {
        "function": "fake_factor_module:momentum",
        "rows": len(expected),
        "checked_prefixes": 3 * 2,
        "required_fields": ["close", "volume"],
    }


def test_check_function_on_a_real_indicator_and_the_store(capsys, tmp_path, factor_module):
    root = tmp_path / "root"
    panel = random_panel(("S0", "S1"), periods=60)
    for symbol in ("S0", "S1"):
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"))
    from skills.compute.indicators import roc

    expected = Factor(roc, period=3).calculate(panel, dropna=False)
    code, body = run(
        capsys, "check-function", "--symbols", "S0,S1", "--data-root", str(root),
        "--function", "skills.compute.indicators:roc", "--params", '{"period": 3}',
        "--required-fields", "close",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["rows"] == len(expected) == 120
    assert body["data"]["checked_prefixes"] == 4
    assert body["data"]["required_fields"] == ["close"]


def test_check_function_rejects_a_look_ahead_factor(capsys, panel_file, factor_module):
    _, path = panel_file
    code, body = run(
        capsys,
        "check-function",
        "--panel",
        str(path),
        "--function",
        "fake_factor_module:look_ahead",
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "not prefix causal" in body["error"]["message"]


def test_check_function_input_errors(capsys, tmp_path, panel_file, factor_module):
    panel, path = panel_file
    function = "fake_factor_module:momentum"
    code, body = run(capsys, "check-function", "--function", function)
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "check-function", "--panel", str(path), "--symbols", "S0", "--function", function
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "check-function", "--panel", str(path), "--function", function,
        "--required-fields", "close,vwap",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "vwap" in body["error"]["message"]
    code, body = run(
        capsys,
        "check-function",
        "--panel",
        str(tmp_path / "missing.parquet"),
        "--function",
        function,
    )
    assert_error(code, body, "NOT_FOUND", 3)
    no_volume = tmp_path / "no_volume.parquet"
    panel.drop(columns=["volume"]).to_parquet(no_volume)
    code, body = run(
        capsys, "check-function", "--panel", str(no_volume), "--function",
        "fake_factor_module:needs_volume",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "check-function", "--panel", str(path))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "check-function", "--panel", str(path), "--function", "no-colon-reference"
    )
    assert_error(code, body, "INVALID_INPUT", 2)
