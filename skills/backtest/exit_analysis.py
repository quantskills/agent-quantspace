"""
Exit Factor Evaluation Module

Evaluate the effectiveness of exit (filter) factors using:
1. Portfolio-level A/B comparison (baseline vs variant with exit filter)
2. Event-level analysis (forward returns at trigger points)

Reference: jq_ss/etf/exit_factor_evaluation.md

Usage:
    from skills.backtest.exit_analysis import evaluate_exit_factor, plot_exit_evaluation

    result = evaluate_exit_factor(
        data, factor_configs,
        exit_filter={'func': F.rsi, 'kwargs': {'period': 14},
                     'name': 'rsi<75', 'condition': lambda x: x < 75},
    )
    plot_exit_evaluation(result)
"""

import io
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from strategies.cross_sectional.modular_backtester import ModularBacktester

# ======================================================================
# Core evaluation function
# ======================================================================


def evaluate_exit_factor(
    data: pd.DataFrame,
    factor_configs: list,
    exit_filter: dict,
    *,
    top_pct: float = 0.2,
    commission: float = 0.0002,
    slippage_bp: float,
    signal_lag: int = 1,
    start_date: str = None,
    end_date: str = None,
    baseline_exits: list = None,
    forward_windows: list = None,
    exposure_policy: str = "keep_cash",
) -> dict:
    """
    Evaluate a single exit factor by comparing baseline vs variant backtests
    and analyzing forward returns at trigger points.

    Parameters
    ----------
    data : pd.DataFrame
        MultiIndex (symbol, eob) with OHLCV columns.
    factor_configs : list
        Entry factor configurations (held constant).
    exit_filter : dict
        The exit factor to evaluate.
        Format: {'func': callable, 'kwargs': dict, 'name': str, 'condition': callable}
    top_pct, commission, slippage_bp, signal_lag, start_date, end_date :
        ModularBacktester parameters.
    baseline_exits : list, optional
        Existing exit filters for baseline. Default: no exit filters.
    forward_windows : list, optional
        Forward return horizons in days. Default: [1, 3, 5, 10].
    exposure_policy : str, optional
        Exposure policy for exit filters: 'keep_cash', 'renormalize', 'allocate_defensive'
        Default: 'keep_cash'

    Returns
    -------
    dict with keys:
        'name'              : str
        'ab_comparison'     : dict with 'baseline', 'variant', 'delta' metrics
        'trigger_stats'     : dict with hit_count, hit_rate, exposure stats
        'event_analysis'    : dict[horizon] -> forward return stats
        'baseline_result_df': pd.DataFrame
        'variant_result_df' : pd.DataFrame
        'trigger_mask'      : pd.DataFrame (bool, date x symbol)
    """
    if forward_windows is None:
        forward_windows = [1, 3, 5, 10]
    if baseline_exits is None:
        baseline_exits = []

    name = exit_filter.get("name", exit_filter["func"].__name__)

    # --- Run baseline ---
    bt_base = _run_backtest_silent(
        data,
        factor_configs,
        baseline_exits,
        top_pct,
        commission,
        slippage_bp,
        signal_lag,
        start_date,
        end_date,
        exposure_policy=exposure_policy,
    )

    # --- Run variant (baseline + this exit filter) ---
    variant_exits = list(baseline_exits) + [exit_filter]
    bt_var = _run_backtest_silent(
        data,
        factor_configs,
        variant_exits,
        top_pct,
        commission,
        slippage_bp,
        signal_lag,
        start_date,
        end_date,
        exposure_policy=exposure_policy,
    )

    # --- A/B comparison ---
    ab = _compute_ab_comparison(bt_base.metrics, bt_var.metrics)

    # --- Trigger mask ---
    trigger_mask = _compute_trigger_mask(bt_base.weights_df, bt_var.weights_df)

    # --- Trigger stats ---
    trigger_stats = _compute_trigger_stats(trigger_mask, bt_base.weights_df, bt_var.weights_df)

    # --- Event-level forward returns ---
    close_pivot = data["close"].unstack(level="symbol")
    event_analysis = _compute_forward_returns(close_pivot, trigger_mask, forward_windows)

    return {
        "name": name,
        "ab_comparison": ab,
        "trigger_stats": trigger_stats,
        "event_analysis": event_analysis,
        "baseline_result_df": bt_base.result_df,
        "variant_result_df": bt_var.result_df,
        "trigger_mask": trigger_mask,
    }


# ======================================================================
# Internal helpers
# ======================================================================


def _run_backtest_silent(
    data,
    factor_configs,
    exit_filters,
    top_pct,
    commission,
    slippage_bp,
    signal_lag,
    start_date,
    end_date,
    exposure_policy="keep_cash",
) -> ModularBacktester:
    """Run a ModularBacktester with stdout suppressed."""
    bt = ModularBacktester(
        data=data,
        factor_configs=factor_configs,
        exit_filters=exit_filters,
        top_pct=top_pct,
        commission=commission,
        slippage_bp=slippage_bp,
        signal_lag=signal_lag,
        start_date=start_date,
        end_date=end_date,
        exposure_policy=exposure_policy,
    )
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        bt.run()
    finally:
        sys.stdout = old_stdout
    return bt


def _compute_ab_comparison(base_m: dict, var_m: dict) -> dict:
    """Compute A/B metrics comparison."""
    keys = [
        "total_return",
        "ann_return",
        "max_drawdown",
        "sharpe_ratio",
        "calmar_ratio",
        "sortino_ratio",
        "ann_volatility",
        "avg_daily_turnover",
        "total_transaction_cost",
    ]
    baseline = {k: base_m.get(k, 0) for k in keys}
    variant = {k: var_m.get(k, 0) for k in keys}
    delta = {k: variant[k] - baseline[k] for k in keys}
    return {"baseline": baseline, "variant": variant, "delta": delta}


def _compute_trigger_mask(base_weights: pd.DataFrame, var_weights: pd.DataFrame) -> pd.DataFrame:
    """
    Identify trigger points: baseline has position but variant filtered it out.
    Returns bool DataFrame (date x symbol).
    """
    common_idx = base_weights.index.intersection(var_weights.index)
    common_cols = base_weights.columns.intersection(var_weights.columns)
    bw = base_weights.loc[common_idx, common_cols]
    vw = var_weights.loc[common_idx, common_cols]
    return (bw > 0) & (vw == 0)


def _compute_trigger_stats(
    trigger_mask: pd.DataFrame, base_weights: pd.DataFrame, var_weights: pd.DataFrame
) -> dict:
    """Compute trigger frequency and exposure impact."""
    # Total baseline holding points
    common_idx = trigger_mask.index
    common_cols = trigger_mask.columns
    bw = base_weights.loc[common_idx, common_cols]

    baseline_hold_count = (bw > 0).sum().sum()
    hit_count = trigger_mask.sum().sum()
    hit_rate = hit_count / baseline_hold_count if baseline_hold_count > 0 else 0

    # Exposure = daily sum of weights
    vw = var_weights.reindex(index=common_idx, columns=common_cols).fillna(0)
    daily_exposure = vw.sum(axis=1)

    return {
        "hit_count": int(hit_count),
        "hit_rate": float(hit_rate),
        "exposure_mean": float(daily_exposure.mean()),
        "exposure_std": float(daily_exposure.std()),
        "low_exposure_days_pct": float((daily_exposure < 0.6).mean()),
    }


def _compute_forward_returns(
    close_pivot: pd.DataFrame, trigger_mask: pd.DataFrame, windows: list
) -> dict:
    """
    For each trigger point (date, symbol), compute forward h-day returns.
    """
    daily_ret = close_pivot.pct_change(fill_method=None)
    common_idx = trigger_mask.index.intersection(daily_ret.index)
    common_cols = trigger_mask.columns.intersection(daily_ret.columns)
    mask = trigger_mask.loc[common_idx, common_cols]
    ret = daily_ret.loc[common_idx, common_cols]

    result = {}
    for h in windows:
        # 向量化：未来 h 天累计收益 = shift(-1) 到 shift(-h) 之和
        fwd_ret = sum(ret.shift(-lag).fillna(0) for lag in range(1, h + 1))

        # Extract triggered points
        triggered_fwd = fwd_ret[mask]
        vals = triggered_fwd.stack().dropna()

        if len(vals) == 0:
            result[h] = {
                "mean": np.nan,
                "p10": np.nan,
                "p50": np.nan,
                "p90": np.nan,
                "big_loss_prob_2pct": np.nan,
                "big_loss_prob_4pct": np.nan,
                "big_gain_prob_2pct": np.nan,
                "count": 0,
            }
        else:
            result[h] = {
                "mean": float(vals.mean()),
                "p10": float(vals.quantile(0.1)),
                "p50": float(vals.quantile(0.5)),
                "p90": float(vals.quantile(0.9)),
                "big_loss_prob_2pct": float((vals < -0.02).mean()),
                "big_loss_prob_4pct": float((vals < -0.04).mean()),
                "big_gain_prob_2pct": float((vals > 0.02).mean()),
                "count": len(vals),
            }
    return result


# ======================================================================
# Visualization
# ======================================================================


def plot_exit_evaluation(eval_result: dict, figsize=(16, 10)):
    """
    Visualize exit factor evaluation:
    - Top-left: cumulative return comparison (baseline vs variant)
    - Top-right: drawdown comparison
    - Bottom-left: daily exposure of variant
    - Bottom-right: forward return box plot at trigger points
    """
    name = eval_result["name"]
    base_df = eval_result["baseline_result_df"]
    var_df = eval_result["variant_result_df"]
    event = eval_result["event_analysis"]
    trigger = eval_result["trigger_stats"]
    ab = eval_result["ab_comparison"]  # noqa: F841 — reserved for future use

    fig, axes = plt.subplots(2, 2, figsize=figsize)
    fig.suptitle(f"Exit Factor: {name}", fontsize=14, fontweight="bold")

    # --- Top-left: cumulative return ---
    ax = axes[0, 0]
    ax.plot(base_df.index, base_df["cum_return"], label="Baseline", alpha=0.8)
    ax.plot(var_df.index, var_df["cum_return"], label=f"+ {name}", alpha=0.8)
    ax.set_title("Cumulative Return")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- Top-right: drawdown ---
    ax = axes[0, 1]
    ax.fill_between(base_df.index, base_df["drawdown"], 0, alpha=0.3, label="Baseline DD")
    ax.fill_between(var_df.index, var_df["drawdown"], 0, alpha=0.3, label=f"+ {name} DD")
    ax.set_title("Drawdown")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- Bottom-left: exposure ---
    ax = axes[1, 0]
    # Reconstruct variant daily exposure from var weights
    # (we stored trigger_mask which has the right index)
    # Actually let's just use the A/B metrics
    ax.text(
        0.5,
        0.5,
        f"Exposure Mean: {trigger['exposure_mean']:.3f}\n"
        f"Exposure Std:  {trigger['exposure_std']:.3f}\n"
        f"Low Exp Days:  {trigger['low_exposure_days_pct'] * 100:.1f}%\n"
        f"\nHit Count: {trigger['hit_count']}\n"
        f"Hit Rate:  {trigger['hit_rate'] * 100:.2f}%",
        transform=ax.transAxes,
        fontsize=11,
        verticalalignment="center",
        horizontalalignment="center",
        fontfamily="monospace",
        bbox={"boxstyle": "round", "facecolor": "lightyellow", "alpha": 0.8},
    )
    ax.set_title("Trigger & Exposure Stats")
    ax.set_xticks([])
    ax.set_yticks([])

    # --- Bottom-right: forward return distribution ---
    ax = axes[1, 1]
    horizons = sorted(event.keys())
    box_data = []
    box_labels = []
    for h in horizons:
        ev = event[h]
        if ev["count"] > 0:
            box_data.append([ev["p10"], ev["p50"], ev["mean"], ev["p90"]])
            box_labels.append(f"{h}d\n(n={ev['count']})")

    if box_data:
        x = range(len(box_data))
        means = [d[2] for d in box_data]
        p10s = [d[0] for d in box_data]
        p90s = [d[3] for d in box_data]
        p50s = [d[1] for d in box_data]

        ax.bar(
            x, means, color=["red" if m < 0 else "green" for m in means], alpha=0.6, label="Mean"
        )
        ax.scatter(x, p10s, marker="v", color="darkred", s=50, zorder=5, label="P10")
        ax.scatter(x, p50s, marker="o", color="black", s=30, zorder=5, label="P50")
        ax.scatter(x, p90s, marker="^", color="darkgreen", s=50, zorder=5, label="P90")
        ax.set_xticks(x)
        ax.set_xticklabels(box_labels)
        ax.axhline(y=0, color="black", linewidth=0.5)
        ax.legend(fontsize=7)
    ax.set_title("Forward Return at Trigger Points")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


def print_ab_comparison(eval_result: dict):
    """Print A/B comparison table."""
    name = eval_result["name"]
    ab = eval_result["ab_comparison"]

    print(f"\n{'=' * 70}")
    print(f"  Exit Factor A/B: {name}")
    print(f"{'=' * 70}")
    print(f"  {'Metric':<25s} {'Baseline':>10s} {'Variant':>10s} {'Delta':>10s}")
    print(f"  {'-' * 55}")

    fmt_map = {
        "total_return": ("Total Return", "{:+.2%}", "{:+.2%}", "{:+.2%}"),
        "ann_return": ("Ann Return", "{:+.2%}", "{:+.2%}", "{:+.2%}"),
        "max_drawdown": ("Max Drawdown", "{:.2%}", "{:.2%}", "{:+.2%}"),
        "sharpe_ratio": ("Sharpe", "{:.2f}", "{:.2f}", "{:+.2f}"),
        "calmar_ratio": ("Calmar", "{:.2f}", "{:.2f}", "{:+.2f}"),
        "sortino_ratio": ("Sortino", "{:.2f}", "{:.2f}", "{:+.2f}"),
        "ann_volatility": ("Ann Volatility", "{:.2%}", "{:.2%}", "{:+.2%}"),
        "avg_daily_turnover": ("Avg Turnover", "{:.2%}", "{:.2%}", "{:+.2%}"),
        "total_transaction_cost": ("Total Cost", "{:.4%}", "{:.4%}", "{:+.4%}"),
    }

    for key, (label, f_b, f_v, f_d) in fmt_map.items():
        b = ab["baseline"].get(key, 0)
        v = ab["variant"].get(key, 0)
        d = ab["delta"].get(key, 0)
        print(f"  {label:<25s} {f_b.format(b):>10s} {f_v.format(v):>10s} {f_d.format(d):>10s}")

    ts = eval_result["trigger_stats"]
    print(f"\n  Trigger: {ts['hit_count']} hits ({ts['hit_rate'] * 100:.1f}% of positions)")
    print(
        f"  Exposure: mean={ts['exposure_mean']:.3f}  std={ts['exposure_std']:.3f}"
        f"  low(<0.6)={ts['low_exposure_days_pct'] * 100:.1f}%"
    )
    print(f"{'=' * 70}")


def print_event_analysis(eval_result: dict):
    """Print forward return analysis at trigger points."""
    name = eval_result["name"]
    event = eval_result["event_analysis"]

    print(f"\n  Forward Returns at Trigger Points ({name}):")
    print(
        f"  {'Horizon':<8s} {'Count':>6s} {'Mean':>8s} {'P10':>8s} {'P50':>8s}"
        f" {'P90':>8s} {'Loss>2%':>8s} {'Loss>4%':>8s} {'Gain>2%':>8s}"
    )
    print(f"  {'-' * 72}")

    for h in sorted(event.keys()):
        ev = event[h]
        if ev["count"] == 0:
            print(f"  {h}d       {'N/A':>6s}")
            continue
        print(
            f"  {h}d      {ev['count']:>6d} {ev['mean']:>+8.3%} {ev['p10']:>+8.3%}"
            f" {ev['p50']:>+8.3%} {ev['p90']:>+8.3%}"
            f" {ev['big_loss_prob_2pct']:>8.1%} {ev['big_loss_prob_4pct']:>8.1%}"
            f" {ev['big_gain_prob_2pct']:>8.1%}"
        )


def summarize_exit_factors(results: list) -> pd.DataFrame:
    """
    Build a summary DataFrame comparing multiple exit factors.

    Parameters
    ----------
    results : list of dict
        List of evaluate_exit_factor() outputs.

    Returns
    -------
    pd.DataFrame
        One row per exit factor, key metrics as columns.
    """
    rows = []
    for r in results:
        ab = r["ab_comparison"]
        ts = r["trigger_stats"]
        ev = r["event_analysis"]
        fwd1 = ev.get(1, {})
        fwd5 = ev.get(5, {})

        rows.append(
            {
                "name": r["name"],
                "dAnnReturn": ab["delta"]["ann_return"],
                "dMaxDD": ab["delta"]["max_drawdown"],
                "dSharpe": ab["delta"]["sharpe_ratio"],
                "dCalmar": ab["delta"]["calmar_ratio"],
                "dSortino": ab["delta"]["sortino_ratio"],
                "dTurnover": ab["delta"]["avg_daily_turnover"],
                "hit_rate": ts["hit_rate"],
                "exposure_mean": ts["exposure_mean"],
                "fwd1d_mean": fwd1.get("mean", np.nan),
                "fwd5d_mean": fwd5.get("mean", np.nan),
                "fwd1d_loss4pct": fwd1.get("big_loss_prob_4pct", np.nan),
            }
        )

    return pd.DataFrame(rows).set_index("name")
