from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from skills.live_trade import (
    TargetSnapshot,
    build_signal,
    channel_name,
    format_signal,
    load_notify_urls,
    normalize_webhook_url,
    platform_of,
    send_notifications,
    size_targets,
)
from tests.skills.live_trade.conftest import DINGTALK, DISCORD, FEISHU, SLACK, WECOM


def test_each_im_has_its_own_variable():
    environ = {
        "QS_NOTIFY_DISCORD": DISCORD,
        "QS_NOTIFY_SLACK": SLACK,
        "QS_NOTIFY_WECOM": WECOM,
        "QS_NOTIFY_FEISHU": FEISHU,
        "QS_NOTIFY_DINGTALK": DINGTALK,
    }
    assert load_notify_urls(environ) == [WECOM, FEISHU, DINGTALK, SLACK, DISCORD]
    assert load_notify_urls({}) == []


def test_one_variable_may_hold_several_groups_without_duplicates():
    second = WECOM.replace("4444", "9999")
    environ = {"QS_NOTIFY_WECOM": f"{WECOM}, {second}\n{WECOM}"}
    assert load_notify_urls(environ) == [WECOM, second]


def test_url_in_the_wrong_variable_is_refused_without_echoing_it():
    with pytest.raises(ValueError, match="QS_NOTIFY_FEISHU holds a slack URL") as error:
        load_notify_urls({"QS_NOTIFY_FEISHU": SLACK})
    assert SLACK not in str(error.value)


def test_urls_come_from_environment(monkeypatch):
    monkeypatch.setenv("QS_NOTIFY_WECOM", WECOM)
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    assert load_notify_urls() == [WECOM, FEISHU]


def test_dotenv_supplies_urls_when_environment_lacks_them(tmp_path, monkeypatch):
    monkeypatch.delenv("QS_NOTIFY_SLACK")
    (tmp_path / ".env").write_text(f"QS_NOTIFY_SLACK={SLACK}\n", encoding="utf-8")
    assert load_notify_urls() == [SLACK]


def test_copied_im_urls_are_rewritten_for_apprise():
    assert normalize_webhook_url(FEISHU) == "feishu://00000000-1111-2222-3333-555555555555"
    assert normalize_webhook_url(DINGTALK) == "dingtalk://" + "0" * 64
    assert normalize_webhook_url(DISCORD).endswith("?avatar=no")
    assert normalize_webhook_url(DISCORD + "?avatar=yes").endswith("?avatar=yes")
    assert normalize_webhook_url(WECOM) == WECOM


def test_channel_names_identify_platforms_without_secrets():
    names = [channel_name(url) for url in (WECOM, FEISHU, DINGTALK, SLACK, DISCORD)]
    assert [name.split("-")[0] for name in names] == [
        "wecom",
        "feishu",
        "dingtalk",
        "slack",
        "discord",
    ]
    assert all("0000" not in name and "XXXX" not in name for name in names)
    assert platform_of("wecombot://abc") == "wecom"
    assert channel_name(FEISHU) == channel_name(normalize_webhook_url(FEISHU))


def test_message_lists_changes_prices_and_units(weights, prices):
    signal = build_signal(
        TargetSnapshot.from_frames(weights, "etf_rotation", prices=prices), {"159915.SZ": 0.5}
    )
    sized = {
        item.symbol: item
        for item in size_targets(
            {change.symbol: change.target for change in signal.changes},
            1_000_000,
            signal.prices,
            multipliers={"M2605.DCE": 10},
        )
    }
    title, body = format_signal(signal, sized)
    assert "QuantSpace" in title and "etf_rotation" in title
    assert "信号时间：2026-11-19" in body
    assert "- 510300.SH：0.00% → 35.00%（+35.00%），参考价 4.123，目标 84800 股" in body
    assert "- M2605.DCE：0.00% → -40.00%（-40.00%），参考价 2820，目标 -14 手" in body
    assert "- 159915.SZ：50.00% → 0.00%（-50.00%）" in body
    assert f"信号编号：{signal.signal_id}" in body


def test_empty_signal_says_there_is_no_rebalance(weights):
    snapshot = TargetSnapshot.from_frames(weights, "demo")
    _, body = format_signal(build_signal(snapshot, snapshot.weights))
    assert "无调仓" in body


def test_each_platform_gets_its_own_payload(http):
    results = send_notifications(
        "QuantSpace 调仓信号 | demo", "- 510300.SH", [WECOM, FEISHU, SLACK, DISCORD, DINGTALK]
    )
    assert [result.ok for result in results] == [True] * 5
    hosts = [item["host"] for item in http.sent]
    assert hosts == [
        "qyapi.weixin.qq.com",
        "open.feishu.cn",
        "hooks.slack.com",
        "discord.com",
        "oapi.dingtalk.com",
    ]
    wecom, feishu = (json.loads(item["body"]) for item in http.sent[:2])
    assert wecom["msgtype"] == "text" and "510300.SH" in wecom["text"]["content"]
    assert feishu["msg_type"] == "text" and "QuantSpace" in feishu["content"]["text"]
    assert "avatar_url" not in json.loads(http.sent[3]["body"])


def test_failed_channel_reports_redacted_detail(http):
    http.failing.add("qyapi.weixin.qq.com")
    (result,) = send_notifications("QuantSpace", "body", [WECOM])
    assert not result.ok
    assert result.channel.startswith("wecom-")
    assert "00000000-1111" not in result.detail


@pytest.mark.parametrize("url", [WECOM, FEISHU, DINGTALK])
def test_http_200_with_error_code_is_a_failure(http, url):
    http.rejecting.add(urlsplit(url).hostname)
    (result,) = send_notifications("QuantSpace", "body", [url])
    assert not result.ok
    assert "HTTP 200: error code" in result.detail
    assert "00000000" not in result.detail


def test_scheme_urls_post_to_the_platform_endpoint(http):
    token = "a" * 64
    results = send_notifications(
        "QuantSpace", "body", ["wecombot://k-123", f"dingtalk://SECabc@{token}"]
    )
    assert [result.ok for result in results] == [True, True]
    wecom, dingtalk = (item["url"] for item in http.sent)
    assert wecom == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=k-123"
    query = parse_qs(urlsplit(dingtalk).query)
    assert query["access_token"] == [token]
    assert query["timestamp"] and query["sign"]
    assert "SECabc" not in dingtalk
