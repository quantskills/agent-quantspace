"""Tests for the ``qs report`` command adapters."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skills.cli import main
from skills.cli.io import json_safe
from skills.report import charts
from skills.report.research_report import (
    ReportFigure,
    ReportTable,
    ResearchReport,
    list_research_studies,
    write_research_bundle,
    write_research_catalog,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def run(capsys, *argv):
    capsys.readouterr()
    code = main(["report", *argv])
    return code, json.loads(capsys.readouterr().out)


def assert_error(code, body, name, status):
    assert code == status, body
    assert body["ok"] is False
    assert body["error"]["code"] == name, body


@pytest.fixture(autouse=True)
def isolated_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "data_root"))
    monkeypatch.setenv("QUANTSPACE_REPORTS_ROOT", str(tmp_path / "env_reports"))


# ---------------------------------------------------------------------------
# chart
# ---------------------------------------------------------------------------


def returns_table(periods=80, seed=1):
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-01", periods=periods, name="eob")
    return pd.DataFrame({"return": rng.normal(0.0005, 0.01, periods)}, index=index)


def surface_summary(seed=2):
    rng = np.random.default_rng(seed)
    rows = [
        {
            "factor": factor,
            "segment": "full",
            "horizon": horizon,
            "lag": lag,
            "ic_mean": rng.normal(0, 0.02),
        }
        for factor in ("mom", "rev")
        for horizon in (1, 5, 10, 20)
        for lag in (0, 1, 2)
    ]
    return pd.DataFrame(rows)


def assert_png(path: Path):
    data = path.read_bytes()
    assert data.startswith(PNG_SIGNATURE) and len(data) > 1000
    return data


def test_chart_equity_curve_equals_plot_equity_curve(capsys, tmp_path):
    frame = returns_table()
    table = tmp_path / "returns.parquet"
    frame.to_parquet(table)
    output = tmp_path / "out" / "equity.png"
    code, body = run(
        capsys, "chart", "--kind", "equity-curve", "--table", str(table), "--title", "My curve",
        "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    png = assert_png(output)
    assert png == charts.plot_equity_curve(frame["return"], title="My curve")
    assert body["data"] == {
        "kind": "equity-curve",
        "function": "charts.plot_equity_curve",
        "bytes": len(png),
    }
    assert body["artifacts"][0]["name"] == "chart"
    assert body["artifacts"][0]["path"] == str(output.resolve())


def test_chart_equity_curve_custom_column_and_csv(capsys, tmp_path):
    frame = returns_table().rename(columns={"return": "pnl"})
    table = tmp_path / "pnl.csv"
    frame.reset_index().to_csv(table, index=False)
    output = tmp_path / "pnl.png"
    code, body = run(
        capsys, "chart", "--kind", "equity-curve", "--table", str(table), "--column", "pnl",
        "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    assert_png(output)
    code, body = run(
        capsys, "chart", "--kind", "equity-curve", "--table", str(table),
        "--output", str(tmp_path / "other.png"),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)  # the default column "return" is absent


def test_chart_backtest_performance(capsys, tmp_path):
    returns = returns_table()["return"]
    equity = (1 + returns).cumprod()
    frame = pd.DataFrame(
        {"return": returns, "equity": equity, "drawdown": equity / equity.cummax() - 1}
    )
    table = tmp_path / "backtest.parquet"
    frame.to_parquet(table)
    output = tmp_path / "backtest.png"
    code, body = run(
        capsys, "chart", "--kind", "backtest-performance", "--table", str(table),
        "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    assert assert_png(output) == charts.plot_backtest_performance(pd.read_parquet(table))
    assert body["data"]["function"] == "charts.plot_backtest_performance"


def test_chart_factor_ranking_params_reach_the_chart_function(capsys, tmp_path):
    ranking = pd.DataFrame(
        {
            "indicator": list("abcd"),
            "IC_IR": [0.5, -0.3, 0.1, 0.05],
            "IC_mean": [0.02, -0.01, 0.0, 0.0],
        }
    )
    table = tmp_path / "ranking.csv"
    ranking.to_csv(table, index=False)
    output = tmp_path / "ranking.png"
    code, body = run(
        capsys, "chart", "--kind", "factor-ranking", "--table", str(table), "--output", str(output),
        "--params", '{"top_n": 2, "value_col": "IC_mean"}', "--title", "Top",
    )  # fmt: skip
    assert code == 0, body
    assert assert_png(output) == charts.plot_factor_ranking(
        ranking, value_col="IC_mean", top_n=2, title="Top"
    )
    # A chart keyword that the function does not know is an input error, not a crash.
    code, body = run(
        capsys, "chart", "--kind", "factor-ranking", "--table", str(table),
        "--output", str(tmp_path / "bad.png"), "-p", "colour=red",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert not (tmp_path / "bad.png").exists()


def test_chart_ic_heatmap(capsys, tmp_path):
    rng = np.random.default_rng(3)
    ic = pd.DataFrame(
        rng.normal(0, 0.05, (3, 4)), index=["f1", "f2", "f3"], columns=["p1", "p5", "p10", "p20"]
    )
    table = tmp_path / "ic.parquet"
    ic.to_parquet(table)
    output = tmp_path / "ic.png"
    code, body = run(
        capsys, "chart", "--kind", "ic-heatmap", "--table", str(table), "--output", str(output),
        "-p", "annotate=true",
    )  # fmt: skip
    assert code == 0, body
    assert assert_png(output) == charts.plot_ic_heatmap(ic, annotate=True)


def test_chart_horizon_and_lagged_ic_from_an_ic_surface_summary(capsys, tmp_path):
    summary = surface_summary()
    table = tmp_path / "summary.parquet"
    summary.to_parquet(table)
    horizon = tmp_path / "horizon.png"
    code, body = run(
        capsys, "chart", "--kind", "horizon-ic", "--table", str(table), "--output", str(horizon),
        "--params", '{"factors": ["mom", "rev"]}',
    )  # fmt: skip
    assert code == 0, body
    assert assert_png(horizon) == charts.plot_horizon_ic(summary, factors=["mom", "rev"])
    lagged = tmp_path / "lagged.png"
    code, body = run(
        capsys, "chart", "--kind", "lagged-ic", "--table", str(table), "--output", str(lagged),
        "--params", '{"factors": ["mom"]}', "--title", "Decay",
    )  # fmt: skip
    assert code == 0, body
    assert assert_png(lagged) == charts.plot_lagged_ic(summary, factors=["mom"], title="Decay")
    # factors is a required keyword of both charts.
    code, body = run(
        capsys, "chart", "--kind", "horizon-ic", "--table", str(table),
        "--output", str(tmp_path / "missing_factors.png"),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)


def tidy_factor_weights(periods=30):
    index = pd.bdate_range("2024-01-01", periods=periods, name="eob")
    return pd.DataFrame(
        [
            {"eob": day, "method": "max_icir", "factor": factor, "weight": 0.5}
            for day in index
            for factor in ("a", "b")
        ]
    )


@pytest.mark.parametrize("suffix", ["parquet", "csv"])
def test_chart_factor_weight_history(capsys, tmp_path, suffix):
    weights = tidy_factor_weights()
    table = tmp_path / f"weights.{suffix}"
    if suffix == "csv":
        weights.to_csv(table, index=False)
    else:
        weights.to_parquet(table)
    output = tmp_path / "weights.png"
    code, body = run(
        capsys, "chart", "--kind", "factor-weight-history", "--table", str(table),
        "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    assert assert_png(output) == charts.plot_factor_weight_history(weights)


@pytest.mark.parametrize("method", [None, "rolling_ic"])
def test_chart_factor_weight_history_from_wide_combine_weights(capsys, tmp_path, method):
    # strategy combine writes one method's weights as a wide eob x factor table.
    wide = pd.DataFrame(
        {"a": [None, 0.4, 0.6, 0.5], "b": [None, 0.6, 0.4, 0.5]},
        index=pd.bdate_range("2024-01-01", periods=4, name="eob"),
    )
    table = tmp_path / "factor_weights.parquet"
    wide.to_parquet(table)
    output = tmp_path / "weights.png"
    code, body = run(
        capsys, "chart", "--kind", "factor-weight-history", "--table", str(table),
        *(["-p", f"method={method}"] if method else []), "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    # The tidy records run_lesson06_multifactor builds before plotting.
    records = wide.stack().rename("weight").dropna().reset_index()
    records.columns = ["eob", "factor", "weight"]
    records.insert(0, "method", method or "max_icir")
    kwargs = {"method": method} if method else {}
    assert assert_png(output) == charts.plot_factor_weight_history(records, **kwargs)


def test_chart_input_errors_and_conflicts(capsys, tmp_path):
    table = tmp_path / "returns.parquet"
    returns_table().to_parquet(table)
    output = tmp_path / "equity.png"
    base = ["chart", "--kind", "equity-curve", "--table", str(table)]
    code, body = run(capsys, *base, "--output", str(tmp_path / "equity.jpg"))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "chart", "--kind", "pie", "--table", str(table), "--output", str(output)
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "chart", "--kind", "equity-curve", "--table", str(tmp_path / "missing.parquet"),
        "--output", str(output),
    )  # fmt: skip
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, *base)  # output is required
    assert_error(code, body, "INVALID_INPUT", 2)
    assert not output.exists()
    output.write_bytes(b"keep me")
    code, body = run(capsys, *base, "--output", str(output))
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_bytes() == b"keep me"
    code, body = run(capsys, *base, "--output", str(output), "--overwrite")
    assert code == 0, body
    assert_png(output)


# ---------------------------------------------------------------------------
# bundle, list, catalog
# ---------------------------------------------------------------------------


@pytest.fixture
def evidence(tmp_path):
    """A chart PNG and a small CSV table for a study."""
    frame = returns_table(periods=60)
    table = tmp_path / "returns.parquet"
    frame.to_parquet(table)
    chart = tmp_path / "equity.png"
    code = main(
        ["report", "chart", "--kind", "equity-curve", "--table", str(table), "--output", str(chart)]
    )
    assert code == 0
    params = tmp_path / "params.csv"
    pd.DataFrame({"window": [10, 20], "sharpe": [0.5, 0.7]}).to_csv(params, index=False)
    return chart, params


def study_payload(chart, params, **overrides):
    payload = {
        "namespace": "demo",
        "slug": "momentum",
        "title": "Momentum study",
        "question": "Does 20-day momentum predict next-week ETF returns?",
        "universe": ["SHSE.510300", "SHSE.510500"],
        "frequency": "1d",
        "sample_start": "2020-01-01",
        "sample_end": "2023-12-31",
        "hypothesis": "Momentum persists after costs.",
        "method_notes": ["Signal is lagged one bar."],
        "execution": {"trade_at": "close", "signal_lag": 1},
        "metrics": {"sharpe": 1.2, "max_drawdown": -0.1},
        "metrics_source": "BacktestResult.metrics",
        "figures": [{"name": "equity", "caption": "Equity curve", "source_path": str(chart)}],
        "tables": [
            {"name": "params", "caption": "Parameters", "path": str(params)},
            {
                "name": "robustness_grid",
                "caption": "Robustness",
                "html": "<table><tr><td>robust-cell</td></tr></table>",
            },
        ],
        "caveats": ["Small sample."],
        "next_steps": ["Test a longer window."],
        "reproduce_command": "uv run qs backtest run ...",
        "tags": ["momentum"],
    }
    payload.update(overrides)
    return payload


def write_payload(tmp_path, payload, name="study.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


def direct_report(payload):
    return ResearchReport(
        **{key: value for key, value in payload.items() if key not in {"figures", "tables"}},
        in_sample_end=None,
        out_of_sample_start=None,
        visibility="private",
        figures=[
            ReportFigure(
                name=item["name"], caption=item["caption"], source_path=item["source_path"]
            )
            for item in payload["figures"]
        ],
        tables=[
            ReportTable(
                name=item["name"],
                caption=item["caption"],
                frame=pd.read_csv(item["path"]) if "path" in item else None,
                html=item.get("html"),
            )
            for item in payload["tables"]
        ],
    )


def test_bundle_equals_write_research_bundle_and_inlines_the_chart(capsys, tmp_path, evidence):
    chart, params = evidence
    payload = study_payload(chart, params)
    root = tmp_path / "reports"
    code, body = run(
        capsys, "bundle", "--input-json", str(write_payload(tmp_path, payload)),
        "--reports-root", str(root),
    )  # fmt: skip
    assert code == 0, body
    study = root / "demo" / "momentum"
    assert body["data"] == {
        "study_dir": str(study.resolve()),
        "files": ["artifacts/metrics.csv", "index.html", "params.json"],
        "catalog": None,
    }
    assert body["artifacts"] == [
        {
            "name": "study",
            "path": str(study.resolve()),
            "format": "directory",
            "rows": None,
            "columns": [],
        }
    ]
    # The same study written directly is byte-identical.
    direct_root = tmp_path / "direct"
    direct_dir = write_research_bundle(direct_report(payload), reports_root=direct_root)
    for name in body["data"]["files"]:
        ours, theirs = (study / name).read_text(), (direct_dir / name).read_text()
        # pandas Styler gives every rendered table a random id.
        assert re.sub(r"T_[0-9a-f]{5}", "T_x", ours) == re.sub(r"T_[0-9a-f]{5}", "T_x", theirs), (
            name
        )
    html = (study / "index.html").read_text(encoding="utf-8")
    encoded = base64.b64encode(chart.read_bytes()).decode("ascii")
    assert f"data:image/png;base64,{encoded}" in html
    assert "robust-cell" in html and payload["question"] in html
    params_json = json.loads((study / "params.json").read_text())
    assert params_json["metrics"] == payload["metrics"] and params_json["visibility"] == "private"
    assert list(pd.read_csv(study / "artifacts" / "metrics.csv")["metric"]) == [
        "sharpe",
        "max_drawdown",
    ]


def test_bundle_flags_override_json_and_the_catalog_option_writes_the_catalog(
    capsys, tmp_path, evidence
):
    chart, params = evidence
    path = write_payload(tmp_path, study_payload(chart, params))
    root = tmp_path / "reports"
    code, body = run(
        capsys, "bundle", "--input-json", str(path), "--reports-root", str(root),
        "--slug", "renamed", "--visibility", "public_example", "--kind", "dashboard",
        "--domain", "etf", "--as-of", "2024-01-31", "--catalog",
    )  # fmt: skip
    assert code == 0, body
    study = root / "demo" / "renamed"
    assert body["data"]["study_dir"] == str(study.resolve())
    meta = json.loads((study / "params.json").read_text())
    assert (meta["visibility"], meta["kind"], meta["domain"], meta["as_of"]) == (
        "public_example",
        "dashboard",
        "etf",
        "2024-01-31",
    )
    assert body["data"]["catalog"] == str((root / "catalog.html").resolve())
    assert (root / "catalog.json").exists()
    assert [item["name"] for item in body["artifacts"]] == ["study", "catalog"]
    catalog = json.loads((root / "catalog.json").read_text())
    assert [(item["namespace"], item["slug"]) for item in catalog] == [("demo", "renamed")]


def test_bundle_uses_the_environment_reports_root_by_default(capsys, tmp_path, evidence):
    chart, params = evidence
    path = write_payload(tmp_path, study_payload(chart, params))
    code, body = run(capsys, "bundle", "--input-json", str(path))
    assert code == 0, body
    assert (
        Path(body["data"]["study_dir"])
        == (tmp_path / "env_reports" / "demo" / "momentum").resolve()
    )
    assert (tmp_path / "env_reports" / "demo" / "momentum" / "index.html").exists()


def test_bundle_refuses_an_existing_study_without_overwrite(capsys, tmp_path, evidence):
    chart, params = evidence
    payload = study_payload(chart, params)
    root = tmp_path / "reports"
    argv = ["bundle", "--reports-root", str(root)]
    path = write_payload(tmp_path, payload)
    code, body = run(capsys, *argv, "--input-json", str(path))
    assert code == 0, body
    study = root / "demo" / "momentum"
    before = {name: (study / name).read_bytes() for name in ("index.html", "params.json")}
    changed = write_payload(tmp_path, {**payload, "title": "Changed title"}, "changed.json")
    code, body = run(capsys, *argv, "--input-json", str(changed))
    assert_error(code, body, "CONFLICT", 2)
    assert body["error"]["details"] == ["index.html", "params.json"]
    assert {name: (study / name).read_bytes() for name in before} == before
    code, body = run(capsys, *argv, "--input-json", str(changed), "--overwrite")
    assert code == 0, body
    assert (study / "index.html").read_bytes() != before["index.html"]
    assert json.loads((study / "params.json").read_text())["title"] == "Changed title"


def test_bundle_without_figures_tables_or_metrics(capsys, tmp_path):
    payload = study_payload(None, None, figures=[], tables=[], metrics={}, universe=["SHSE.510300"])
    root = tmp_path / "reports"
    code, body = run(
        capsys, "bundle", "--input-json", str(write_payload(tmp_path, payload)),
        "--reports-root", str(root),
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["files"] == ["index.html", "params.json"]


@pytest.mark.parametrize(
    ("overrides", "status", "code_name"),
    [
        ({"namespace": "../escape"}, 2, "INVALID_INPUT"),
        ({"slug": "a/b"}, 2, "INVALID_INPUT"),
        ({"visibility": "world"}, 2, "INVALID_INPUT"),
        ({"kind": "poster"}, 2, "INVALID_INPUT"),
        ({"question": "  "}, 2, "INVALID_INPUT"),
        ({"metrics_source": ""}, 2, "INVALID_INPUT"),
        ({"unknown_field": 1}, 2, "INVALID_INPUT"),
        ({"tables": [{"name": "t", "caption": "c"}]}, 2, "INVALID_INPUT"),
        (
            {"tables": [{"name": "t", "caption": "c", "path": "x.csv", "html": "<p></p>"}]},
            2,
            "INVALID_INPUT",
        ),
    ],
)
def test_bundle_rejects_invalid_payloads_without_writing(
    capsys, tmp_path, evidence, overrides, status, code_name
):
    chart, params = evidence
    root = tmp_path / "reports"
    path = write_payload(tmp_path, study_payload(chart, params, **overrides))
    code, body = run(capsys, "bundle", "--input-json", str(path), "--reports-root", str(root))
    assert_error(code, body, code_name, status)
    assert not root.exists() or not list(root.rglob("*.html"))


def test_bundle_missing_inputs(capsys, tmp_path, evidence):
    chart, params = evidence
    root = tmp_path / "reports"
    payload = study_payload(chart, params)
    figure = {"name": "equity", "caption": "c", "source_path": str(tmp_path / "missing.png")}
    code, body = run(
        capsys, "bundle", "--input-json",
        str(write_payload(tmp_path, {**payload, "figures": [figure]}, "figure.json")),
        "--reports-root", str(root),
    )  # fmt: skip
    # Missing figure files are NOT_FOUND, like missing table files.
    assert_error(code, body, "NOT_FOUND", 3)
    assert body["error"]["details"] == [figure["source_path"]]
    table = {"name": "t", "caption": "c", "path": str(tmp_path / "missing.csv")}
    code, body = run(
        capsys, "bundle", "--input-json",
        str(write_payload(tmp_path, {**payload, "tables": [table]}, "table.json")),
        "--reports-root", str(root),
    )  # fmt: skip
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "bundle", "--input-json", str(tmp_path / "nothing.json"))
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "bundle", "--reports-root", str(root))  # required fields missing
    assert_error(code, body, "INVALID_INPUT", 2)
    assert not root.exists() or not list(root.rglob("*.html"))


def test_list_equals_list_research_studies(capsys, tmp_path, evidence):
    chart, params = evidence
    root = tmp_path / "reports"
    for namespace, slug in (("beta", "two"), ("alpha", "one"), ("alpha", "three")):
        payload = study_payload(chart, params, namespace=namespace, slug=slug)
        code, body = run(
            capsys, "bundle", "--input-json", str(write_payload(tmp_path, payload)),
            "--reports-root", str(root),
        )  # fmt: skip
        assert code == 0, body
    # A directory without index.html is not a study.
    stray = root / "gamma" / "draft"
    stray.mkdir(parents=True)
    (stray / "params.json").write_text("{}")
    expected = list_research_studies(root)
    code, body = run(capsys, "list", "--reports-root", str(root))
    assert code == 0, body
    assert body["data"] == {
        "reports_root": str(root.resolve()),
        "count": 3,
        "studies": json_safe(expected),
    }
    assert [(item["namespace"], item["slug"]) for item in body["data"]["studies"]] == [
        ("alpha", "one"),
        ("alpha", "three"),
        ("beta", "two"),
    ]
    assert body["data"]["studies"][0]["index_html"] == "alpha/one/index.html"
    code, body = run(capsys, "list", "--reports-root", str(root), "--namespace", "alpha")
    assert code == 0 and body["data"]["count"] == 2
    assert {item["namespace"] for item in body["data"]["studies"]} == {"alpha"}
    code, body = run(capsys, "list", "--reports-root", str(root), "--namespace", "none")
    assert code == 0 and body["data"] == {
        "reports_root": str(root.resolve()),
        "count": 0,
        "studies": [],
    }


def test_list_of_a_missing_root_is_empty_and_creates_nothing(capsys, tmp_path):
    root = tmp_path / "nowhere"
    code, body = run(capsys, "list", "--reports-root", str(root))
    assert code == 0 and body["data"]["count"] == 0
    assert not root.exists()
    code, body = run(capsys, "list")  # the environment root, also absent
    assert code == 0 and body["data"]["reports_root"] == str((tmp_path / "env_reports").resolve())
    assert not (tmp_path / "env_reports").exists()


def test_catalog_equals_write_research_catalog(capsys, tmp_path, evidence):
    chart, params = evidence
    root = tmp_path / "reports"
    payload = study_payload(chart, params)
    code, _ = run(
        capsys, "bundle", "--input-json", str(write_payload(tmp_path, payload)),
        "--reports-root", str(root),
    )  # fmt: skip
    assert code == 0
    code, body = run(capsys, "catalog", "--reports-root", str(root))
    assert code == 0, body
    assert body["data"] == {"catalog": str((root / "catalog.html").resolve()), "count": 1}
    assert [(item["name"], item["format"]) for item in body["artifacts"]] == [
        ("catalog", "html"),
        ("catalog_json", "json"),
    ]
    assert body["artifacts"][1]["path"] == str((root / "catalog.json").resolve())
    produced = {name: (root / name).read_bytes() for name in ("catalog.html", "catalog.json")}
    write_research_catalog(root)  # rewriting through the library changes nothing
    assert {name: (root / name).read_bytes() for name in produced} == produced
    records = json.loads(produced["catalog.json"])
    assert [(item["namespace"], item["slug"]) for item in records] == [("demo", "momentum")]
    assert records[0]["sharpe"] == 1.2 and records[0]["max_drawdown"] == -0.1
    assert "Momentum study" in produced["catalog.html"].decode("utf-8")


def test_catalog_of_an_empty_root_writes_an_empty_catalog(capsys, tmp_path):
    root = tmp_path / "reports"
    code, body = run(capsys, "catalog", "--reports-root", str(root))
    assert code == 0, body
    assert body["data"]["count"] == 0
    assert json.loads((root / "catalog.json").read_text()) == []
