"""qs live-trade commands: preview by default, deliver once per channel, never guess sizes."""

from __future__ import annotations

import json

import pytest

from tests.skills.live_trade.conftest import FEISHU, SLACK, WECOM


def invoke(capsys, *args):
    from skills.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def files(tmp_path, weights, prices):
    paths = {"weights": tmp_path / "weights.parquet", "prices": tmp_path / "prices.parquet"}
    weights.to_parquet(paths["weights"])
    prices.to_parquet(paths["prices"])
    paths["multipliers"] = tmp_path / "multipliers.json"
    paths["multipliers"].write_text(json.dumps({"M2605.DCE": 10}), encoding="utf-8")
    return paths


def notify(capsys, files, tmp_path, *extra):
    return invoke(
        capsys,
        "live-trade",
        "notify",
        "--weights",
        str(files["weights"]),
        "--strategy-id",
        "demo",
        "--data-root",
        str(tmp_path / "data"),
        *extra,
    )


def test_preview_formats_signal_without_network_or_ledger(capsys, files, tmp_path, monkeypatch):
    monkeypatch.setenv("QS_NOTIFY_WECOM", WECOM)
    monkeypatch.setenv("QS_NOTIFY_SLACK", SLACK)
    code, result = notify(capsys, files, tmp_path)
    assert code == 0, result
    data = result["data"]
    assert data["status"] == "preview"
    assert [item["symbol"] for item in data["changes"]] == ["510300.SH", "M2605.DCE"]
    assert [name.split("-")[0] for name in data["channels"]] == ["wecom", "slack"]
    assert data["deliveries"] == []
    assert not (tmp_path / "data" / "live").exists()


def test_the_envelope_is_utf8_on_a_gbk_pipe(files, tmp_path):
    """A Windows pipe defaults to GBK; agents read stdout as UTF-8, as JSON should be."""
    import os
    import subprocess
    import sys

    program = "import sys; from skills.cli import main; sys.exit(main(sys.argv[1:]))"
    completed = subprocess.run(
        [sys.executable, "-c", program, "live-trade", "notify", "--weights", str(files["weights"])]
        + ["--strategy-id", "demo", "--data-root", str(tmp_path / "data")],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "gbk"},
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.decode("utf-8"))
    assert result["data"]["title"] == "QuantSpace 调仓信号 | demo"


def test_send_delivers_once_then_reports_unchanged(capsys, files, tmp_path, monkeypatch, http):
    monkeypatch.setenv("QS_NOTIFY_WECOM", WECOM)
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 0, result
    assert result["data"]["status"] == "sent"
    assert len(http.sent) == 2

    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 0
    assert result["data"]["status"] == "unchanged"
    assert len(http.sent) == 2


def test_failed_channel_is_retried_alone(capsys, files, tmp_path, monkeypatch, http):
    monkeypatch.setenv("QS_NOTIFY_WECOM", WECOM)
    monkeypatch.setenv("QS_NOTIFY_SLACK", SLACK)
    http.failing.add("hooks.slack.com")
    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 4
    assert result["data"]["status"] == "partial"
    assert result["error"]["code"] == "UPSTREAM_ERROR"
    first_id = result["data"]["signal_id"]

    http.failing.clear()
    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 0, result
    assert result["data"]["status"] == "sent"
    assert result["data"]["signal_id"] == first_id
    assert [item["host"] for item in http.sent] == [
        "qyapi.weixin.qq.com",
        "hooks.slack.com",
        "hooks.slack.com",
    ]
    skipped = [item for item in result["data"]["deliveries"] if item["skipped"]]
    assert [item["channel"].split("-")[0] for item in skipped] == ["wecom"]


def test_rejected_message_is_not_recorded_as_delivered(capsys, files, tmp_path, monkeypatch, http):
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    http.rejecting.add("open.feishu.cn")
    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 4
    assert result["data"]["status"] == "failed"
    assert "error code 19001" in result["data"]["deliveries"][0]["detail"]

    http.rejecting.clear()
    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 0, result
    assert result["data"]["status"] == "sent"
    assert len(http.sent) == 2


def test_send_without_channels_fails_before_any_write(capsys, files, tmp_path):
    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 2
    assert result["error"]["code"] == "CONFIG_MISSING"
    assert not (tmp_path / "data" / "live").exists()


def test_capital_sizes_units_and_needs_prices(capsys, files, tmp_path):
    code, result = notify(capsys, files, tmp_path, "--capital", "1000000")
    assert code == 2
    assert "--prices" in result["error"]["message"]

    code, result = notify(
        capsys,
        files,
        tmp_path,
        "--capital",
        "1000000",
        "--prices",
        str(files["prices"]),
        "--multipliers",
        str(files["multipliers"]),
    )
    assert code == 0, result
    units = {item["symbol"]: item["units"] for item in result["data"]["changes"]}
    assert units == {"M2605.DCE": -14, "510300.SH": 84800}


def test_futures_without_multiplier_are_refused(capsys, files, tmp_path):
    code, result = notify(
        capsys, files, tmp_path, "--capital", "1000000", "--prices", str(files["prices"])
    )
    assert code == 2
    assert "M2605.DCE" in result["error"]["message"]


def test_output_file_holds_the_signal(capsys, files, tmp_path):
    out = tmp_path / "signal.json"
    code, result = notify(capsys, files, tmp_path, "--output", str(out))
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["signal_id"] == result["data"]["signal_id"]


def test_doctor_reports_channels_and_panda_cli(capsys, tmp_path, monkeypatch, http):
    from tests.skills.live_trade.test_panda_cli import ACCOUNTS, CAPABILITIES, fake_cli

    cli = fake_cli(
        tmp_path,
        {
            "accounts": {"ok": True, "data": ACCOUNTS},
            "capabilities": {"ok": True, "data": CAPABILITIES},
        },
    )
    monkeypatch.setenv("PANDA_LIVE_CLI", cli[0])
    monkeypatch.setenv("QS_NOTIFY_WECOM", WECOM)
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)

    code, result = invoke(capsys, "live-trade", "doctor", "--send-test")
    assert code == 0, result
    data = result["data"]
    assert data["notify_ready"] is True
    assert [(item["platform"], item["variable"]) for item in data["channels"]] == [
        ("wecom", "QS_NOTIFY_WECOM"),
        ("feishu", "QS_NOTIFY_FEISHU"),
    ]
    assert all(item["ok"] for item in data["test_deliveries"])
    panda = data["panda_cli"]
    assert (panda["found"], panda["command"], panda["version"]) == (True, cli, "0.1.11")
    assert (panda["error"], panda["problems"]) == (None, [])
    assert [
        (item["account_id"], item["simnow"], item["cli_eligible"]) for item in panda["accounts"]
    ] == [
        (1, True, True),
        (2, False, False),
    ]


def test_doctor_warns_when_no_account_is_cli_eligible(capsys, tmp_path, monkeypatch):
    from tests.skills.live_trade.test_panda_cli import ACCOUNTS, fake_cli

    cli = fake_cli(
        tmp_path,
        {
            "accounts": {"ok": True, "data": ACCOUNTS[1:]},
            "capabilities": {"ok": True, "data": {"contract": {"supported": True}}},
        },
    )
    monkeypatch.setenv("PANDA_LIVE_CLI", cli[0])
    monkeypatch.setenv("QS_NOTIFY_SLACK", SLACK)
    code, result = invoke(capsys, "live-trade", "doctor")
    assert code == 0, result
    assert result["data"]["panda_cli"]["problems"] == ["batch plans do not freeze GFD limit orders"]
    assert any("No PandaAI account" in warning for warning in result["warnings"])


def test_doctor_warns_when_the_client_is_closed(capsys, tmp_path, monkeypatch):
    from tests.skills.live_trade.test_panda_cli import fake_cli

    closed = {"ok": False, "error": {"code": "INTERNAL", "message": "fetch failed"}}
    cli = fake_cli(tmp_path, {"accounts": closed, "capabilities": closed})
    monkeypatch.setenv("PANDA_LIVE_CLI", cli[0])
    monkeypatch.setenv("QS_NOTIFY_SLACK", SLACK)
    code, result = invoke(capsys, "live-trade", "doctor")
    assert code == 0, result
    assert result["data"]["panda_cli"]["error"].startswith("fetch failed")
    assert any("先打开客户端并登录" in warning for warning in result["warnings"])


def test_doctor_reports_whether_an_account_can_trade_automatically(capsys, tmp_path, monkeypatch):
    from tests.skills.live_trade.test_panda_cli import ACCOUNTS, CAPABILITIES, fake_cli

    connected = {"connected": True, "cli_ready": True, "connection_status": "CONNECTED"}
    cli = fake_cli(
        tmp_path,
        {
            "accounts": {"ok": True, "data": ACCOUNTS},
            "capabilities": {"ok": True, "data": CAPABILITIES},
            "connection": {"ok": True, "data": {"connection": connected}},
        },
    )
    monkeypatch.setenv("PANDA_LIVE_CLI", cli[0])
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    data_root = tmp_path / "data"

    def doctor(*extra):
        return invoke(capsys, "live-trade", "doctor", "--data-root", str(data_root), *extra)

    code, result = doctor("--account", "100001", "--strategy-id", "rb_demo")
    assert code == 0, result
    auto = result["data"]["auto_trade"]
    assert (auto["name"], auto["simnow"], auto["ready"], auto["reasons"]) == (
        "simnow_demo（100001）",
        True,
        True,
        [],
    )

    stop = data_root / "live" / "rb_demo" / "STOP"
    stop.parent.mkdir(parents=True)
    stop.write_text("", encoding="utf-8")
    code, result = doctor("--account", "100001", "--strategy-id", "rb_demo")
    assert code == 1 and result["data"]["auto_trade"]["ready"] is False
    assert "紧急停止文件" in result["data"]["auto_trade"]["reasons"][0]

    code, result = doctor("--account", "200002")
    auto = result["data"]["auto_trade"]
    assert code == 1 and (auto["simnow"], auto["ready"]) == (False, False)
    assert "不是 SimNow 账号" in auto["reasons"][0]
    assert any("cannot trade automatically" in warning for warning in result["warnings"])

    code, result = doctor()
    assert code == 0 and result["data"]["auto_trade"] is None


def test_doctor_says_a_dropped_counter_is_reconnected_before_orders(capsys, tmp_path, monkeypatch):
    from tests.skills.live_trade.test_panda_cli import ACCOUNTS, CAPABILITIES, fake_cli

    dropped = {"connected": False, "cli_ready": False, "connection_status": "FAILED"}
    cli = fake_cli(
        tmp_path,
        {
            "accounts": {"ok": True, "data": ACCOUNTS},
            "capabilities": {"ok": True, "data": CAPABILITIES},
            "connection": {"ok": True, "data": {"connection": dropped}},
        },
    )
    monkeypatch.setenv("PANDA_LIVE_CLI", cli[0])
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)

    code, result = invoke(
        capsys, "live-trade", "doctor", "--data-root", str(tmp_path), "--account", "100001"
    )

    auto = result["data"]["auto_trade"]
    assert code == 1 and auto["ready"] is False
    assert auto["reasons"] == ["柜台未就绪（FAILED）（下一次下单前会先自动重连）"]


def test_doctor_without_channels_is_not_ready(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("PANDA_LIVE_CLI", str(tmp_path / "missing"))
    code, result = invoke(capsys, "live-trade", "doctor")
    assert code == 1
    assert result["data"]["notify_ready"] is False
    assert result["data"]["panda_cli"]["found"] is False


def test_misplaced_webhook_fails_before_sending(capsys, files, tmp_path, monkeypatch, http):
    monkeypatch.setenv("QS_NOTIFY_FEISHU", SLACK)
    code, result = notify(capsys, files, tmp_path, "--write")
    assert code == 2
    assert "QS_NOTIFY_FEISHU holds a slack URL" in result["error"]["message"]
    assert SLACK not in json.dumps(result)
    assert http.sent == []
