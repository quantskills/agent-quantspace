"""A-share trigger-time cost mapping for overlay backtests."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Baseline calibration is from SZSE.002460 minute-level slippage profile.
COST_LAYERS: dict[str, int] = {
    "tight": 16,
    "base": 21,
    "wide": 30,
    "worst": 46,
    "stress": 66,
}


@dataclass(frozen=True)
class CostBoundary:
    start: str
    end: str
    layer: str


TIME_BOUNDARIES: tuple[CostBoundary, ...] = (
    CostBoundary("09:30", "09:45", "worst"),
    CostBoundary("09:45", "14:30", "wide"),
    CostBoundary("14:30", "14:45", "base"),
    CostBoundary("14:45", "15:00", "tight"),
)


def _is_in_cn_session(ts: pd.Timestamp) -> bool:
    hm = ts.strftime("%H:%M")
    in_am = "09:30" <= hm <= "11:30"
    in_pm = "13:00" <= hm <= "15:00"
    return in_am or in_pm


def cost_layer_for_trigger_time(ts: pd.Timestamp) -> str:
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    if not _is_in_cn_session(ts):
        raise ValueError(f"trigger time outside CN session: {ts}")
    hm = ts.strftime("%H:%M")
    for b in TIME_BOUNDARIES:
        if b.start <= hm < b.end or (hm == "15:00" and b.layer == "tight"):
            return b.layer
    return "base"


def cost_bp_for_trigger_time(ts: pd.Timestamp) -> int:
    return COST_LAYERS[cost_layer_for_trigger_time(ts)]


def single_T_pnl_bp(sell_price: float, buyback_price: float, cost_bp: float) -> tuple[float, float]:
    if sell_price <= 0 or buyback_price <= 0:
        raise ValueError("sell_price and buyback_price must be positive")
    gross_bp = (sell_price - buyback_price) / sell_price * 10000.0
    net_bp = gross_bp - float(cost_bp)
    return gross_bp, net_bp
