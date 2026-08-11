"""mean_reversion_price_structure_generator 角色产出的 NEW 因子候选.

遵循 skills.compute.wrappers.Factor 契约：
- 输入: 单 symbol DataFrame，索引名为 eob 的 DatetimeIndex，列含 OHLCV
- 输出: float64 Series，索引与输入完全相同且顺序一致，NaN 用于 warm-up

所有因子均为 mean-reversion / price-structure 族全新假设，不复用
indicators.py / factors.py 已存在的因子（roc/ma/mean_reversion/bollinger/
williams_r/rsi/cci/supertrend/donchian 等）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# =============================================================================
# 工具
# =============================================================================


def _safe_divide(numer: np.ndarray, denom: np.ndarray, fill: float = np.nan) -> np.ndarray:
    """安全除法：denom 为 0 或 NaN 时返回 fill。"""
    out = np.full_like(numer, fill, dtype=np.float64)
    mask = (denom != 0) & np.isfinite(denom) & np.isfinite(numer)
    out[mask] = numer[mask] / denom[mask]
    return out


def _rolling_apply(arr: np.ndarray, window: int, func) -> np.ndarray:
    """对 1D 数组做滚动窗口应用（仅用于无向量化替代时）。

    返回长度 == len(arr)，前 window-1 位为 NaN。
    """
    n = len(arr)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return out
    for i in range(window - 1, n):
        out[i] = func(arr[i - window + 1 : i + 1])
    return out


def _sliding_view(arr: np.ndarray, window: int) -> np.ndarray:
    """返回 sliding_window_view，长度不足时返回空 (n-window+1, window)。"""
    if len(arr) < window:
        return np.empty((0, window), dtype=np.float64)
    return np.lib.stride_tricks.sliding_window_view(arr, window_shape=window)


# =============================================================================
# 因子定义
# =============================================================================


def mr_quantile_deviation(group: pd.DataFrame, period: int = 60, q: float = 0.5) -> pd.Series:
    """价格分位数偏离反转因子。

    经济假设：价格相对近期分位点的偏离具有均值回归性。当价格远高于
    滚动窗口分位数（如中位数）时，后续倾向于回落；远低于时倾向于反弹。
    本因子用 (close - rolling_quantile) / (rolling_max - rolling_min) 衡量
    偏离方向，正值偏大→看空（取负），形成反转信号。

    与现有 mean_reversion（基于 z-score）不同：分位数偏离对厚尾更稳健，
    不受极端值放大影响。
    """
    close = group["close"].astype(float)
    idx = group.index

    if len(close) < period:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    vals = close.values
    out = np.full(len(vals), np.nan, dtype=np.float64)

    for i in range(period - 1, len(vals)):
        window = vals[i - period + 1 : i + 1]
        q_val = np.quantile(window, q)
        w_max = np.max(window)
        w_min = np.min(window)
        spread = w_max - w_min
        if spread > 0:
            out[i] = (vals[i] - q_val) / spread

    # 反转方向：偏离越大→因子值越负（看空），偏离越小（负偏离）→因子值越正（看多）
    return pd.Series(-out, index=idx, dtype=np.float64)


def mr_return_autocorr(group: pd.DataFrame, period: int = 20, lag: int = 5) -> pd.Series:
    """收益序列自相关反转因子。

    经济假设：日收益率的短期自相关反映市场惯性。当近期收益序列呈现
    强正自相关（趋势惯性过强）时，后续倾向于反转；强负自相关（震荡）
    时倾向延续小幅震荡。本因子用滚动窗口内收益与其 lag 期的皮尔逊
    相关作为信号，正自相关过高→看空（取负）。

    与现有 momentum / roc 因子不同：自相关系数度量的是收益序列的时间
    结构，而非收益本身的方向。
    """
    close = group["close"].astype(float)
    idx = group.index

    if len(close) < period + lag:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    rets = np.diff(np.log(close.values))
    rets = np.concatenate([[np.nan], rets])

    out = np.full(len(close), np.nan, dtype=np.float64)
    n = len(rets)

    # 滚动窗口 [i-period+1, i]，对照窗口整体前移 lag 期
    for i in range(period + lag - 1, n):
        r0 = rets[i - period + 1 : i + 1]                  # 当前窗口，长度 period
        r_lag = rets[i - period + 1 - lag : i + 1 - lag]   # 滞后窗口，长度 period
        if len(r0) != period or len(r_lag) != period:
            continue
        mask = np.isfinite(r0) & np.isfinite(r_lag)
        if mask.sum() < period // 2:
            continue
        r0_v = r0[mask]
        r_lag_v = r_lag[mask]
        s0 = r0_v.std()
        s1 = r_lag_v.std()
        if s0 > 1e-10 and s1 > 1e-10:
            corr = np.corrcoef(r0_v, r_lag_v)[0, 1]
            if np.isfinite(corr):
                out[i] = corr

    # 正自相关过高→看空（取负）；负自相关→看多（取正）
    return pd.Series(-out, index=idx, dtype=np.float64)


def mr_hilbert_phase(group: pd.DataFrame, period: int = 20) -> pd.Series:
    """Hilbert 变换相位反转因子。

    经济假设：价格序列可视为含周期成分的信号。Hilbert 变换给出
    解析信号（analytic signal）的瞬时相位。当瞬时相位处于顶部
    （接近 π）→ 短期顶部反转看空；处于底部（接近 -π/2 或 0）→ 看多。
    本因子用 sin(phase) 作为反转信号，相位越接近波峰→因子越负。

    与所有现有因子不同：这是信号处理视角的价格结构因子，捕获周期
    性均值回归的相位结构。
    """
    close = group["close"].astype(float)
    idx = group.index

    if len(close) < period + 4:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    vals = close.values
    # 去趋势：减去滚动均值
    out = np.full(len(vals), np.nan, dtype=np.float64)
    n = len(vals)

    for i in range(period + 3, n):
        window = vals[i - period + 1 : i + 1]
        t = np.arange(period, dtype=np.float64)
        # 线性去趋势
        coef = np.polyfit(t, window, 1)
        detrended = window - np.polyval(coef, t)
        # 简化 Hilbert 变换：4 点差分近似 (Hilbert 变换的离散 FIR)
        # H[x][n] ≈ x[n-2] - x[n+2]  (近似，端点用 0 填充)
        h = np.zeros(period, dtype=np.float64)
        h[2:-2] = detrended[:-4] - detrended[4:]
        # 解析信号: z = detrended + j*h
        # 瞬时相位 = arctan2(h, detrended)
        phase = np.arctan2(h, detrended)
        # 取最近一个点的相位
        out[i] = phase[-1]

    # sin(phase): 波峰附近 sin=1→看空(取负)；波谷 sin=-1→看多(取正)
    signal = -np.sin(out)
    return pd.Series(signal, index=idx, dtype=np.float64)


def mr_fractal_dim(group: pd.DataFrame, period: int = 30) -> pd.Series:
    """价格分形维度反转因子。

    经济假设：价格序列的分形维度（Higuchi 维度）反映其复杂度/随机性。
    分形维度接近 2（高度随机/震荡）→ 均值回归性强，趋势倾向反转；
    接近 1（强趋势）→ 趋势延续。本因子用 (dim - 1.5) 作为信号，
    维度高→震荡→看多反转；维度低→趋势→减弱反转信号。

    与现有 er (效率系数) 不同：分形维度是拓扑度量，对非线性结构更敏感。
    """
    close = group["close"].astype(float)
    idx = group.index

    if len(close) < period * 2:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    vals = close.values
    n = len(vals)
    out = np.full(n, np.nan, dtype=np.float64)

    # Higuchi 分形维度
    k_max = min(5, period // 4)

    for i in range(period * 2 - 1, n):
        window = vals[i - period + 1 : i + 1]
        L = []
        for k in range(1, k_max + 1):
            Lk = 0.0
            for m in range(k):
                idx_arr = np.arange(m, len(window), k)
                if len(idx_arr) < 2:
                    continue
                diff = np.abs(np.diff(window[idx_arr]))
                # Higuchi 标准归一化: Lmk = (len(window)-1)/(k * (len(idx_arr)-1)) * diff.sum()
                Lmk = diff.sum() * (len(window) - 1) / (k * (len(idx_arr) - 1))
                Lk += Lmk
            L.append((k, Lk / k))
        # log-log 拟合: dim = -slope(log(k), log(Lk))
        logs = [(np.log(k), np.log(lk)) for k, lk in L if lk > 0 and np.isfinite(lk)]
        if len(logs) >= 2:
            xs = np.array([p[0] for p in logs])
            ys = np.array([p[1] for p in logs])
            coef = np.polyfit(xs, ys, 1)
            dim = -coef[0]
            # Higuchi 维度理论范围 [1, 2]；放宽到 [0.5, 2.5] 容忍估计噪声
            if 0.5 < dim < 2.5:
                out[i] = dim

    # 维度高→均值回归性强→正信号；维度低→趋势→负信号
    signal = out - 1.5
    return pd.Series(signal, index=idx, dtype=np.float64)


def mr_tail_extreme(group: pd.DataFrame, period: int = 60, k: float = 2.0) -> pd.Series:
    """对数收益厚尾极值反转因子。

    经济假设：当近期收益位于滚动窗口分布的厚尾极值区（超过 k 倍滚动
    std），市场过度反应，后续倾向于反转。本因子用收益相对滚动 std
    的偏离（带符号）取反作为信号。极端正收益→看空；极端负收益→看多。

    与现有 bollinger_reversal（基于价格带位置）不同：本因子直接度量
    收益分布的厚尾极端性，并显式建模尾部反转。
    """
    close = group["close"].astype(float)
    idx = group.index

    if len(close) < period + 1:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    log_ret = np.diff(np.log(close.values), prepend=np.nan)
    out = np.full(len(close), np.nan, dtype=np.float64)
    n = len(log_ret)

    for i in range(period, n):
        window = log_ret[i - period + 1 : i + 1]
        mask = np.isfinite(window)
        if mask.sum() < period // 2:
            continue
        w = window[mask]
        mu = w.mean()
        sigma = w.std()
        if sigma < 1e-10:
            continue
        z = (log_ret[i] - mu) / sigma
        # 仅在 |z| > k 时触发反转，否则温和
        if abs(z) > k:
            out[i] = -np.sign(z) * (abs(z) - k)
        else:
            out[i] = -z * 0.3  # 温和反转偏向

    return pd.Series(out, index=idx, dtype=np.float64)


def mr_price_volume_divergence(
    group: pd.DataFrame, period: int = 20
) -> pd.Series:
    """价格-成交量背离结构反转因子。

    经济假设：价格创新高但成交量未创新高（量价背离）→ 上涨乏力，
    倾向反转下跌；反之价格创新低但成交量未创新低→下跌乏力，倾向
    反弹。本因子用 (price_rank - volume_rank) 作为背离信号，正值→
    价格强于量→看空；负值→价格弱于量→看多。

    与现有 ma_vol_ratio（量比）不同：背离因子度量价格与量在窗口
    内的相对分位结构，而非量本身的均值比率。
    """
    close = group["close"].astype(float)
    volume = group["volume"].astype(float)
    idx = group.index

    if len(close) < period:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    p_vals = close.values
    v_vals = volume.values
    out = np.full(len(close), np.nan, dtype=np.float64)
    n = len(close)

    for i in range(period - 1, n):
        p_w = p_vals[i - period + 1 : i + 1]
        v_w = v_vals[i - period + 1 : i + 1]
        p_rank = (p_w <= p_vals[i]).sum() / period
        v_rank = (v_w <= v_vals[i]).sum() / period
        out[i] = p_rank - v_rank

    # 价格排名高于量排名 → 看空（取负）
    return pd.Series(-out, index=idx, dtype=np.float64)


def mr_vwap_deviation(group: pd.DataFrame, period: int = 20) -> pd.Series:
    """价格相对 VWAP 偏离回归因子。

    经济假设：滚动 VWAP（成交量加权平均价）反映机构成本基准。价格
    大幅高于 VWAP → 获利盘抛压，倾向回落；大幅低于 → 抄底盘介入，
    倾向反弹。本因子用 (close - rolling_vwap) / rolling_vwap 作为
    偏离度，取负作为反转信号。

    与现有 mean_reversion（基于简单均线 z-score）不同：VWAP 偏离
    度量成交成本结构，对机构行为更敏感。
    """
    close = group["close"].astype(float)
    volume = group["volume"].astype(float)
    idx = group.index

    if len(close) < period:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    c_vals = close.values
    v_vals = volume.values
    out = np.full(len(close), np.nan, dtype=np.float64)
    n = len(close)

    for i in range(period - 1, n):
        c_w = c_vals[i - period + 1 : i + 1]
        v_w = v_vals[i - period + 1 : i + 1]
        total_v = v_w.sum()
        if total_v <= 0:
            continue
        vwap = (c_w * v_w).sum() / total_v
        if vwap > 0:
            out[i] = (c_vals[i] - vwap) / vwap

    # 偏离越大→反转越强（取负）
    return pd.Series(-out, index=idx, dtype=np.float64)


# =============================================================================
# CANDIDATES 元数据
# =============================================================================

CANDIDATES = [
    {
        "factor_id": "mr_quantile_dev_60",
        "family": "mean_reversion",
        "hypothesis": "价格相对滚动分位点的偏离具有均值回归性，厚尾稳健",
        "direction": "negative",
        "func_name": "mr_quantile_deviation",
        "params": {"period": 60, "q": 0.5},
    },
    {
        "factor_id": "mr_ret_autocorr_20_5",
        "family": "mean_reversion",
        "hypothesis": "收益序列正自相关过强预示趋势惯性耗尽→反转",
        "direction": "negative",
        "func_name": "mr_return_autocorr",
        "params": {"period": 20, "lag": 5},
    },
    {
        "factor_id": "mr_hilbert_phase_20",
        "family": "mean_reversion",
        "hypothesis": "价格解析信号瞬时相位处于波峰→顶部反转",
        "direction": "negative",
        "func_name": "mr_hilbert_phase",
        "params": {"period": 20},
    },
    {
        "factor_id": "mr_fractal_dim_30",
        "family": "mean_reversion",
        "hypothesis": "价格分形维度高（震荡态）→均值回归性强；低（趋势态）→减弱反转",
        "direction": "positive",
        "func_name": "mr_fractal_dim",
        "params": {"period": 30},
    },
    {
        "factor_id": "mr_tail_extreme_60",
        "family": "mean_reversion",
        "hypothesis": "对数收益位于滚动分布厚尾极值区→过度反应反转",
        "direction": "negative",
        "func_name": "mr_tail_extreme",
        "params": {"period": 60, "k": 2.0},
    },
    {
        "factor_id": "mr_pv_divergence_20",
        "family": "mean_reversion",
        "hypothesis": "价格创新高但量未创新高的背离→上涨乏力反转",
        "direction": "negative",
        "func_name": "mr_price_volume_divergence",
        "params": {"period": 20},
    },
    {
        "factor_id": "mr_vwap_dev_20",
        "family": "mean_reversion",
        "hypothesis": "价格相对滚动VWAP偏离过大→向机构成本基准回归",
        "direction": "negative",
        "func_name": "mr_vwap_deviation",
        "params": {"period": 20},
    },
]
