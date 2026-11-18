"""Baseline candidates for the 18 asset-class ETFs, built from public indicators.

Nineteen candidates from three generator families. Each row is
``(factor_id, direction, indicator, params, required_fields, window, warmup, hypothesis)``;
the indicator is a function of ``skills.compute.indicators``.
"""

from __future__ import annotations

from typing import Any

INDICATOR_MODULE = "skills.compute.indicators"

_TREND_MOMENTUM = (
    ("trend-roc-20-v1", "long_high", "roc", {"period": 20}, ("close",), 20, 20,
     "过去一个月的相对强势在ETF横截面中会延续至随后20个交易日。"),
    ("trend-roc-60-v1", "long_high", "roc", {"period": 60}, ("close",), 60, 60,
     "过去约一季的跨ETF相对收益反映中期资金配置趋势。"),
    ("trend-mom-skip-63-5-v1", "long_high", "mom_skip", {"skip": 5, "total": 63}, ("close",), 63, 63,
     "剔除最近一周噪声后的三个月相对动量。"),
    ("trend-mom-skip-126-21-v1", "long_high", "mom_skip", {"skip": 21, "total": 126}, ("close",), 126, 126,
     "剔除最近一月后的半年相对动量。"),
    ("trend-ma-deviation-50-v1", "long_high", "ma", {"period": 50}, ("close",), 50, 50,
     "价格相对50日均线的标准化偏离反映趋势位置。"),
    ("trend-ma-cross-10-50-v1", "long_high", "ma_cross", {"short": 10, "long": 50}, ("close",), 50, 50,
     "10日与50日均线差值刻画多尺度趋势。"),
    ("trend-bias-momentum-60-20-v1", "long_high", "bias_momentum", {"ma_period": 60, "momentum_day": 20}, ("close",), 60, 79,
     "60日均线乖离率的20日趋势刻画趋势扩张。"),
    ("trend-score-60-v1", "long_high", "trend_score", {"period": 60}, ("close",), 60, 60,
     "60日对数价格斜率乘拟合优度刻画趋势质量。"),
    ("trend-score-skip-126-21-v1", "long_high", "trend_score_v2_skip", {"period": 126, "skip": 21}, ("close",), 126, 126,
     "剔除最近一月的半年趋势质量。"),
)  # fmt: skip

_MEAN_REVERSION_PRICE_STRUCTURE = (
    ("mrps-daily-return-1d-v1", "long_low", "daily_return", {}, ("close",), 1, 1,
     "单日相对大跌的ETF在未来20日更可能反弹。"),
    ("mrps-roc-5d-v1", "long_low", "roc", {"period": 5}, ("close",), 5, 5,
     "5日相对收益的极端偏离会均值回归。"),
    ("mrps-ma-deviation-20d-v1", "long_low", "ma", {"period": 20}, ("close",), 20, 20,
     "价格相对20日均线的偏离会回归。"),
    ("mrps-ma-cross-stretch-5x20-v1", "long_low", "ma_cross", {"short": 5, "long": 20}, ("close",), 20, 20,
     "5日与20日均线的极端张口会收敛。"),
    ("mrps-cci-20d-v1", "long_low", "cci", {"period": 20}, ("high", "low", "close"), 20, 20,
     "极端CCI刻画超买超卖后的反转。"),
    ("mrps-slowkdj-14-3-3-v1", "long_high", "slowkdj", {"k_period": 14, "k_smooth": 3, "d_smooth": 3, "standardize_window": 60}, ("high", "low", "close"), 60, 30,
     "慢速KDJ的超卖结构预示反转。"),
    ("mrps-williams-r-14d-v1", "long_low", "williams_r", {"period": 14, "standardize_window": 60}, ("high", "low", "close"), 60, 26,
     "Williams %R的区间极值会回归。"),
)  # fmt: skip

_VOLUME_LIQUIDITY = (
    ("volliq-orb-relvol-05-v1", "long_high", "orb_relvol", {"period": 5}, ("volume",), 5, 0,
     "5日相对成交量刻画参与度冲击。"),
    ("volliq-orb-relvol-20-v1", "long_high", "orb_relvol", {"period": 20}, ("volume",), 20, 0,
     "20日相对成交量刻画量能确认。"),
    ("volliq-orb-relvol-60-v1", "long_high", "orb_relvol", {"period": 60}, ("volume",), 60, 0,
     "60日相对成交量刻画长期量能异常。"),
)  # fmt: skip


def _candidates(family: str, rows: tuple[tuple[Any, ...], ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "factor_id": factor_id,
            "family": family,
            "hypothesis": hypothesis,
            "expected_direction": direction,
            "required_fields": required_fields,
            "module": INDICATOR_MODULE,
            "name": indicator,
            "params": params,
            "window": window,
            "lag": 0,
            "warmup": warmup,
            "missing_policy": "keep_nan",
            "availability_rule": "Only point-in-time bars through close[t]; keep missing values as NaN.",
            "output_dtype": "float64",
            "index_restore_policy": "restore_original_names_and_order",
            "applicable_regimes": ("cross_sectional_etf_rotation",),
            "known_relations": (family,),
            "falsification_tests": (
                "Train and validation Rank-IC direction must agree.",
                "Prefix recompute must reproduce values without future bars.",
            ),
        }
        for factor_id, direction, indicator, params, required_fields, window, warmup, hypothesis in rows
    )


CANDIDATES = (
    *_candidates("trend_momentum", _TREND_MOMENTUM),
    *_candidates("mean_reversion_price_structure", _MEAN_REVERSION_PRICE_STRUCTURE),
    *_candidates("volume_liquidity", _VOLUME_LIQUIDITY),
)
