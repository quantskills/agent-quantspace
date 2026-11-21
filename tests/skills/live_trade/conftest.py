"""Fixtures that keep live-trade tests off real webhooks and the repository .env."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlsplit

import pandas as pd
import pytest

WECOM = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=00000000-1111-2222-3333-444444444444"
FEISHU = "https://open.feishu.cn/open-apis/bot/v2/hook/00000000-1111-2222-3333-555555555555"
SLACK = "https://hooks.slack.com/services/T0000000/B0000000/XXXXXXXXXXXXXXXXXXXXXXXX"
DISCORD = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123"
DINGTALK = "https://oapi.dingtalk.com/robot/send?access_token=0000000000000000000000000000000000000000000000000000000000000000"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """No repository .env, no inherited webhook URLs, and no PandaAI CLI override."""
    monkeypatch.chdir(tmp_path)
    from skills.live_trade import NOTIFY_ENV

    for variable in NOTIFY_ENV.values():
        monkeypatch.setenv(variable, "")
    monkeypatch.delenv("PANDA_LIVE_CLI", raising=False)


def _response(request, status_code: int, content: bytes):
    import requests
    from requests.structures import CaseInsensitiveDict

    response = requests.Response()
    response.status_code = status_code
    response._content = content
    response.headers = CaseInsensitiveDict({"Content-Type": "application/json"})
    response.encoding = "utf-8"
    response.url = request.url
    response.request = request
    return response


@pytest.fixture
def http(monkeypatch):
    """Answer every requests call at the transport layer; nothing reaches the network.

    Hosts added to ``failing`` answer HTTP 500. Hosts added to ``rejecting`` answer HTTP 200
    with a nonzero error code in the body, the way WeCom, Feishu, and DingTalk refuse messages.
    """
    pytest.importorskip("apprise")
    from requests.adapters import HTTPAdapter

    state = SimpleNamespace(sent=[], failing=set(), rejecting=set())

    def send(self, request, *args, **kwargs):
        host = urlsplit(request.url).hostname
        body = request.body.decode() if isinstance(request.body, bytes) else request.body
        state.sent.append({"host": host, "url": request.url, "body": body})
        if host in state.failing:
            return _response(request, 500, b'{"errcode": 500, "errmsg": "server error"}')
        if host == "open.feishu.cn" and host in state.rejecting:
            return _response(request, 200, b'{"code": 19001, "msg": "access token invalid"}')
        if host in state.rejecting:
            return _response(request, 200, b'{"errcode": 93000, "errmsg": "invalid webhook"}')
        if host == "hooks.slack.com":
            return _response(request, 200, b"ok")
        return _response(request, 200, b'{"errcode": 0, "code": 0, "StatusCode": 0}')

    monkeypatch.setattr(HTTPAdapter, "send", send)
    return state


@pytest.fixture
def weights():
    index = pd.DatetimeIndex(["2026-11-17", "2026-11-18", "2026-11-19"], name="eob")
    return pd.DataFrame(
        {
            "510300.SH": [0.5, 0.5, 0.35],
            "159915.SZ": [0.5, 0.25, 0.0],
            "RB2601.SHF": [0.0, 0.25, float("nan")],
            "M2605.DCE": [0.0, 0.0, -0.4],
        },
        index=index,
    )


@pytest.fixture
def prices(weights):
    return pd.DataFrame(
        {
            "510300.SH": [4.0, 4.05, 4.123],
            "159915.SZ": [2.0, 2.01, 2.02],
            "RB2601.SHF": [3500.0, 3510.0, 3520.0],
            "M2605.DCE": [2800.0, 2810.0, 2820.0],
        },
        index=weights.index,
    )
