"""Send rebalance signals to IM webhooks (WeCom, Feishu, DingTalk, Slack, Discord).

WeCom, Feishu, and DingTalk answer HTTP 200 even when they reject a message and put the
error code in the JSON body. Apprise only checks the HTTP status for them, so these three
are posted directly and judged by their error code; Slack and Discord go through Apprise.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import time
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from .contracts import DeliveryResult, Signal, is_futures_symbol
from .sizing import SizedTarget

# One environment variable per IM; each may hold several webhook URLs separated by commas.
NOTIFY_ENV = {
    "wecom": "QS_NOTIFY_WECOM",
    "feishu": "QS_NOTIFY_FEISHU",
    "dingtalk": "QS_NOTIFY_DINGTALK",
    "slack": "QS_NOTIFY_SLACK",
    "discord": "QS_NOTIFY_DISCORD",
}
# Feishu and DingTalk bots show these URLs; Apprise only understands feishu:// and dingtalk://.
_FEISHU_NATIVE = re.compile(
    r"^https://open\.feishu\.cn/open-apis/bot/v2/hook/(?P<token>[A-Za-z0-9_-]+)/?$"
)
_DINGTALK_NATIVE = re.compile(
    r"^https://oapi\.dingtalk\.com/robot/send\?access_token=(?P<token>[A-Za-z0-9]+)$"
)
_PLATFORMS = (
    ("wecom", ("wecombot", "qyapi.weixin.qq.com")),
    ("feishu", ("feishu", "open.feishu.cn")),
    ("dingtalk", ("dingtalk", "oapi.dingtalk.com")),
    ("slack", ("slack", "hooks.slack.com")),
    ("discord", ("discord", "discord.com", "discordapp.com")),
)
DETAIL_LIMIT = 300
TIMEOUT_SECONDS = 10
# Bots that report rejections inside an HTTP 200 body.
_DIRECT_ENDPOINTS = {
    "wecom": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={token}",
    "feishu": "https://open.feishu.cn/open-apis/bot/v2/hook/{token}",
    "dingtalk": "https://oapi.dingtalk.com/robot/send?access_token={token}",
}


def load_notify_urls(environ: Mapping[str, str] | None = None) -> list[str]:
    """Webhook URLs from the per-IM variables in ``NOTIFY_ENV``.

    Without ``environ`` the process environment is read, with ``.env`` filling unset
    variables. A variable may hold several URLs separated by commas, spaces, or newlines.
    A URL of another platform than its variable raises ``ValueError`` before anything is sent.
    """
    if environ is None:
        from skills.ingest.panda_data import _load_dotenv_if_present

        _load_dotenv_if_present()
        environ = os.environ
    urls, problems = [], []
    for platform, variable in NOTIFY_ENV.items():
        for url in re.split(r"[\s,]+", environ.get(variable, "")):
            if not url:
                continue
            found = platform_of(url)
            if found != platform:
                problems.append(f"{variable} holds a {found} URL, expected {platform}")
            urls.append(url)
    if problems:
        raise ValueError("Webhook URL in the wrong variable: " + "; ".join(problems))
    return list(dict.fromkeys(urls))


def normalize_webhook_url(url: str) -> str:
    """Rewrite copied IM webhook URLs into forms Apprise sends correctly."""
    url = url.strip()
    feishu = _FEISHU_NATIVE.match(url)
    if feishu:
        return f"feishu://{feishu['token']}"
    dingtalk = _DINGTALK_NATIVE.match(url)
    if dingtalk:
        return f"dingtalk://{dingtalk['token']}"
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme == "discord" or host in ("discord.com", "discordapp.com"):
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        # Apprise otherwise posts with its own avatar image.
        query.setdefault("avatar", "no")
        return urlunsplit(parts._replace(query=urlencode(query)))
    return url


def platform_of(url: str) -> str:
    parts = urlsplit(normalize_webhook_url(url))
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
    for name, markers in _PLATFORMS:
        if scheme in markers or host in markers:
            return name
    return scheme or "unknown"


def channel_name(url: str) -> str:
    """A stable label that never reveals the webhook secret: ``<platform>-<hash8>``."""
    digest = hashlib.sha256(normalize_webhook_url(url).encode("utf-8")).hexdigest()[:8]
    return f"{platform_of(url)}-{digest}"


def _unit_label(symbol: str) -> str:
    return "手" if is_futures_symbol(symbol) else "股"


def format_signal(
    signal: Signal, sized: Mapping[str, SizedTarget] | None = None
) -> tuple[str, str]:
    """Plain-text title and body that read the same in every IM.

    The title always contains ``QuantSpace`` so Feishu bots can use keyword security.
    """
    title = f"QuantSpace 调仓信号 | {signal.strategy_id}"
    lines = [f"信号时间：{signal.as_of}"]
    for change in signal.changes:
        line = (
            f"- {change.symbol}：{change.previous:.2%} → {change.target:.2%}（{change.delta:+.2%}）"
        )
        price = signal.prices.get(change.symbol)
        if price is not None:
            line += f"，参考价 {price:g}"
        if sized and change.symbol in sized:
            line += f"，目标 {sized[change.symbol].units} {_unit_label(change.symbol)}"
        lines.append(line)
    if signal.is_empty:
        lines.append("目标与上次已推送的一致，无调仓。")
    lines.append(f"信号编号：{signal.signal_id}")
    return title, "\n".join(lines)


def _redacted(text: str, url: str) -> str:
    for secret in {url, normalize_webhook_url(url)}:
        text = text.replace(secret, "<webhook>")
    return text.strip()[:DETAIL_LIMIT]


def _direct_target(url: str) -> tuple[str, str, str | None]:
    """Platform, HTTPS endpoint, and DingTalk signing secret for a WeCom, Feishu, or DingTalk URL."""
    url = url.strip()
    platform = platform_of(url)
    parts = urlsplit(url)
    if parts.scheme in ("http", "https"):
        return platform, url, None
    # wecombot://key, feishu://token, dingtalk://[secret@]token; netloc keeps the case.
    secret, _, token = parts.netloc.rpartition("@")
    token = token or parts.path.strip("/")
    return platform, _DIRECT_ENDPOINTS[platform].format(token=token), secret or None


def _signed(endpoint: str, secret: str | None) -> str:
    if not secret:
        return endpoint
    timestamp = str(round(time.time() * 1000))
    digest = hmac.new(
        secret.encode("utf-8"), f"{timestamp}\n{secret}".encode(), hashlib.sha256
    ).digest()
    sign = quote(base64.b64encode(digest), safe="")
    return f"{endpoint}&timestamp={timestamp}&sign={sign}"


def _post_direct(url: str, text: str) -> tuple[bool, str]:
    """POST a plain-text message and judge it by the platform's error code, not just HTTP 200."""
    import requests

    platform, endpoint, secret = _direct_target(url)
    if platform == "feishu":
        payload = {"msg_type": "text", "content": {"text": text}}
    else:
        payload = {"msgtype": "text", "text": {"content": text}}
    try:
        response = requests.post(_signed(endpoint, secret), json=payload, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # The exception text may carry the endpoint built from a wecombot:// style URL.
        return False, f"{type(exc).__name__}: {exc}".replace(endpoint, "<webhook>")
    try:
        answer = response.json()
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        return False, f"HTTP {response.status_code}: response is not JSON"
    code = answer.get("errcode", answer.get("code"))
    if response.status_code == 200 and code == 0:
        return True, ""
    message = answer.get("errmsg", answer.get("msg", ""))
    return False, f"HTTP {response.status_code}: error code {code} {message}"


def _post_apprise(url: str, title: str, body: str) -> tuple[bool, str]:
    import apprise

    notifier = apprise.Apprise()
    if not notifier.add(normalize_webhook_url(url)):
        return False, "Apprise does not recognize this URL"
    with apprise.LogCapture(level=logging.WARNING) as captured:
        ok = bool(notifier.notify(title=title, body=body, body_format=apprise.NotifyFormat.TEXT))
        return ok, "" if ok else captured.getvalue()


def send_notifications(title: str, body: str, urls: Sequence[str]) -> list[DeliveryResult]:
    """Send one message to each URL separately and report each channel's outcome.

    A channel counts as delivered only when the platform accepts the message: for WeCom,
    Feishu, and DingTalk that means error code 0 in the response body. Raises ImportError
    when ``requests`` or the optional ``apprise`` package is missing.
    """
    results = []
    for url in urls:
        if platform_of(url) in _DIRECT_ENDPOINTS:
            ok, detail = _post_direct(url, f"{title}\n{body}")
        else:
            ok, detail = _post_apprise(url, title, body)
        results.append(DeliveryResult(channel_name(url), ok, _redacted(detail, url)))
    return results


__all__ = [
    "NOTIFY_ENV",
    "channel_name",
    "format_signal",
    "load_notify_urls",
    "normalize_webhook_url",
    "platform_of",
    "send_notifications",
]
