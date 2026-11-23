"""PandaAI client CLI wrapper: JSON envelope, accounts, capabilities, contract codes."""

from __future__ import annotations

import json
import stat
import sys

import pytest

from skills.live_trade import (
    PandaCliError,
    capability_problems,
    list_accounts,
    require_actual_contract,
    run_cli,
    version_problem,
)

# Shaped like the client's real output (CLI 0.1.11); codes and names are made up.
ACCOUNTS = [
    {
        "realAccountId": 1,
        "accountCode": "100001",
        "accountName": "simnow_demo",
        "brokerId": "9999",
        "companyName": "SimNow",
        "accountMode": "DIRECT_CLI",
        "runningAssetUnitCount": 0,
        "cliRuntimeStateKnown": True,
        "cliEligible": True,
        "cliUnavailableReason": "",
    },
    {
        "realAccountId": 2,
        "accountCode": "200002",
        "accountName": "real_demo",
        "brokerId": "0274",
        "companyName": "示例期货",
        "accountMode": "PARTITIONED",
        "runningAssetUnitCount": 0,
        "cliRuntimeStateKnown": True,
        "cliEligible": False,
        "cliUnavailableReason": "该账号尚未开启 CLI 模式，请在客户端的账号管理中开启后再使用。",
    },
]
CAPABILITIES = {"contract": {"supported": True}, "batchLimitTimeCondition": "GFD"}


def fake_cli(tmp_path, responses):
    """An executable that prints ``responses[<first arg>]`` and records its environment."""
    script = tmp_path / "panda-live-trading"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"responses = json.loads({json.dumps(json.dumps(responses))})\n"
        "command = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if command == '--version':\n"
        "    print('0.1.11'); sys.exit(0)\n"
        "if command == 'env':\n"
        "    keys = ('PANDA_LIVE_ACTOR', 'PANDA_LIVE_ACTOR_ID', 'PANDA_LIVE_TRACE_ID',\n"
        "            'PANDA_LIVE_UPDATE_CHECK', 'ELECTRON_RUN_AS_NODE')\n"
        "    print(json.dumps({'ok': True, 'data': {k: os.environ.get(k) for k in keys}}))\n"
        "    sys.exit(0)\n"
        "answer = responses.get(command)\n"
        "ok = isinstance(answer, dict) and bool(answer.get('ok'))\n"
        "# Like the client's CLI, a failed command prints its envelope on stderr.\n"
        "stream = sys.stderr if isinstance(answer, dict) and not ok else sys.stdout\n"
        "print(answer if isinstance(answer, str) else json.dumps(answer), file=stream)\n"
        "sys.exit(0 if ok else 1)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [str(script)]


@pytest.fixture
def cli(tmp_path):
    return fake_cli(
        tmp_path,
        {
            "accounts": {"ok": True, "data": ACCOUNTS},
            "capabilities": {"ok": True, "data": CAPABILITIES},
            "connection": {"ok": False, "error": {"code": 1, "message": "该账号尚未开启 CLI 模式"}},
            "broken": "not json",
        },
    )


def test_run_cli_returns_data_and_marks_calls_for_the_audit_trail(cli):
    assert run_cli(cli, "capabilities") == CAPABILITIES
    # The client's update reminders stay on; the launcher runs on the client's runtime.
    assert run_cli(cli, "env", env={"PANDA_LIVE_TRACE_ID": "rb-1"}) == {
        "PANDA_LIVE_ACTOR": "AI",
        "PANDA_LIVE_ACTOR_ID": "quantspace-live-trade",
        "PANDA_LIVE_TRACE_ID": "rb-1",
        "PANDA_LIVE_UPDATE_CHECK": None,
        "ELECTRON_RUN_AS_NODE": "1",
    }


def test_the_client_launcher_is_found_before_path(tmp_path, monkeypatch):
    import skills.live_trade.panda_cli as module

    runtime, launcher = tmp_path / "PandaAI", tmp_path / "bundled-launcher.mjs"
    monkeypatch.delenv(module.CLI_ENV, raising=False)
    monkeypatch.setattr(module, "CLIENT_RUNTIME", runtime)
    monkeypatch.setattr(module, "BUNDLED_CLI", launcher)
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    assert module.discover_cli() is None
    runtime.write_text(""), launcher.write_text("")
    assert module.discover_cli() == [str(runtime), str(launcher)]


def test_run_cli_raises_the_cli_error(cli):
    with pytest.raises(PandaCliError, match="尚未开启 CLI 模式") as caught:
        run_cli(cli, "connection")
    assert caught.value.code == 1
    with pytest.raises(PandaCliError, match="printed no JSON"):
        run_cli(cli, "broken")


def test_accounts_report_simnow_and_cli_eligibility(cli):
    simnow, real = list_accounts(cli)
    assert (simnow.account_id, simnow.is_simnow, simnow.cli_eligible) == (1, True, True)
    assert (real.account_id, real.is_simnow, real.cli_eligible) == (2, False, False)
    assert "CLI 模式" in real.unavailable_reason


def test_capabilities_and_version_checks():
    assert capability_problems(CAPABILITIES) == []
    assert len(capability_problems({"batchLimitTimeCondition": "IOC"})) == 2
    assert version_problem("0.1.11") is None
    assert version_problem("0.2.0") is None
    assert "older than 0.1.11" in version_problem("0.1.9")
    assert "cannot read" in version_problem("dev")


def test_actual_contracts_pass_unchanged_and_continuous_symbols_are_refused():
    assert require_actual_contract("RB2601.SHF") == "RB2601.SHF"
    assert require_actual_contract("SA2701.CZC") == "SA2701.CZC"
    with pytest.raises(ValueError, match="continuous"):
        require_actual_contract("RB_DOMINANT.SHF")
    with pytest.raises(ValueError, match="not a futures"):
        require_actual_contract("510300.SH")
