import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


# 再次定义函数：计算最大回撤
def maxdrawdown(arr):
    """
    输入：净值序列
    输出：最大回撤
    """
    # 最大回撤结束点
    i = np.argmax((np.maximum.accumulate(arr) - arr) / np.maximum.accumulate(arr))
    # 开始点
    j = np.argmax(arr[:i])  # start of period
    # 输出回撤值
    return 1 - arr[i] / arr[j]


# 设置函数：计算净值曲线的绩效指标
def get_Performance_analysis(T, year_day=252):
    """
    输入：净值序列 和基准净值序列

    输出：绩效指标
    """

    # 新高日期数 #突破能力
    max_T = 0
    # 循环净值
    for s in range(2, len(T)):
        # 节点划分
        l_prefix = T[:s]
        # 判断当前节点为最大值
        if l_prefix[-1] > l_prefix[:-1].max():
            # 新高日数+1
            max_T += 1

    # 净值新高天数占比
    max_day_rate = max_T / (len(T) - 1)
    max_day_rate = round(max_day_rate * 100, 2)

    # 获取最终净值
    net_values = round(T[-1], 4)
    # 计算算术年化收益率
    year_ret_mean = T.pct_change().dropna().mean() * year_day
    year_ret_mean = round(year_ret_mean * 100, 2)

    # 计算几何年化收益率
    year_ret_sqrt = net_values ** (year_day / len(T)) - 1
    year_ret_sqrt = round(year_ret_sqrt * 100, 2)

    # 计算年化波动率
    volitiy = T.pct_change().dropna().std() * np.sqrt(year_day)
    volitiy = round(volitiy * 100, 2)

    # 计算夏普，无风险收益率记3%
    Sharpe = (year_ret_sqrt - 0.03) / volitiy
    Sharpe = round(Sharpe, 2)

    # 计算最大回撤
    downlow = maxdrawdown(T)
    downlow = round(downlow * 100, 2)

    # 输出
    return [net_values, year_ret_sqrt, downlow, Sharpe, volitiy, max_day_rate]


# 数据清洗函数 -----------------------------------------------------------
# MAD:中位数去极值
def filter_extreme_MAD(series, n):
    median = series.median()
    new_median = ((series - median).abs()).median()
    return series.clip(median - n * new_median, median + n * new_median)


def winsorize_std(series, n=3):
    mean, std = series.mean(), series.std()
    return series.clip(mean - std * n, mean + std * n)


def winsorize_percentile(series, left=0.025, right=0.975):
    lv, rv = np.percentile(series, [left * 100, right * 100])
    return series.clip(lv, rv)


# 单因子检测函数 -----------------------------------------------------------


def IC_stat(df: pd.DataFrame, rank_IC: bool = True, n=1):
    """
    :param df: columns 为 ['close', 'fac_val'], multi-index 为 ['eob', 'symbol']
    :param rank_IC: 是否为秩相关 -> bool
    :param n: 调仓日 -> int
    """
    index_names = set(df.index.names)
    if not {"eob", "symbol"}.issubset(index_names):
        raise ValueError(f"df.index must contain 'eob' and 'symbol'. Found: {df.index.names}")

    if "close" not in df.columns or "fac_val" not in df.columns:
        raise ValueError(f"df must contain 'close' and 'fac_val' columns. Found: {df.columns}")

    # 提取收盘价和因子值，转换为 unstack 格式（日期为index，标的为columns）
    close_unstack = df["close"].unstack(level="symbol")
    factor_unstack = df["fac_val"].unstack(level="symbol")

    future_return = close_unstack.pct_change(n).shift(-n)

    merged = pd.concat(
        [future_return.stack().rename("future_return"), factor_unstack.stack().rename("factor")],
        axis=1,
    ).dropna()

    # 6. 向量化计算IC (替代逐日 for 循环)
    if rank_IC:
        # Spearman = Pearson on ranks
        ranked = merged.groupby(level="eob").rank()
        ret_vals, fac_vals = ranked["future_return"], ranked["factor"]
    else:
        ret_vals, fac_vals = merged["future_return"], merged["factor"]

    # 用分量公式计算 Pearson 相关系数 (完全向量化，无循环)
    product = ret_vals * fac_vals
    _combined = pd.DataFrame({"ret": ret_vals, "fac": fac_vals, "product": product})
    _grp = _combined.groupby(level="eob")
    n_count = _grp["ret"].count()
    mean_ret = _grp["ret"].mean()
    mean_fac = _grp["fac"].mean()
    std_ret = _grp["ret"].std()
    std_fac = _grp["fac"].std()
    mean_rf = _grp["product"].mean()

    # corr = n/(n-1) * (E[xy] - E[x]E[y]) / (std_x * std_y)
    ic_values = (n_count / (n_count - 1)) * (mean_rf - mean_ret * mean_fac) / (std_ret * std_fac)
    ic_series = ic_values[n_count >= 2].dropna()
    ic_series.name = "IC"

    if len(ic_series) == 0:
        raise ValueError("No valid IC values calculated. Check data alignment and n parameter.")

    # 7. 计算统计指标
    t_stat, p_value = stats.ttest_1samp(ic_series.dropna(), 0)

    ic_mean = ic_series.mean()
    ic_std = ic_series.std()
    ic_ir = ic_mean / ic_std if ic_std != 0 else np.nan

    # 最近一年（约240个交易日）的IR
    ic_mean_last_1y = ic_series[-240:].mean()
    ic_last_1y = ic_series[-240:] if len(ic_series) >= 240 else ic_series
    ic_ir_last_1y = ic_last_1y.mean() / ic_last_1y.std() if ic_last_1y.std() != 0 else np.nan

    # 构建统计字典
    ic_stat_dict = {
        "IC_mean": round(ic_mean, 4),
        "IC_std": round(ic_std, 4),
        "IC_IR": round(ic_ir, 4),
        "IC_mean_last_1y": round(ic_mean_last_1y, 4),
        "IC_IR_LAST_1Y": round(ic_ir_last_1y, 4),
        "IC_>0": round((ic_series > 0).sum() / len(ic_series), 4),
        "IC_ABS_>2%": round((ic_series.abs() > 0.02).sum() / len(ic_series), 4),
        "t_stat": round(t_stat, 4),
        "p_value": round(p_value, 4),
        "IC_count": len(ic_series),
    }

    # 绘制累计IC图
    # plt.figure(figsize=(12, 6))
    # ic_series.cumsum().plot(title='Cum IC', grid=True, linewidth=1.5)
    # plt.xlabel('Date')
    # plt.ylabel('Cum IC')
    # plt.axhline(y=0, color='r', linestyle='--', linewidth=1, alpha=0.5)
    # plt.tight_layout()
    # plt.show()

    return ic_stat_dict, ic_series


def group_stat(df, n, g, verbose: bool = False):
    """
    :param df: 因子值 -> unstack
    :param n: 调仓周期（每 n 个交易日按调仓日因子重新分组）-> int
    :param g: 分组数量 -> int
    :return group_return: 各分组逐日收益率（周期内按调仓日成员等权，日度再平衡）-> dataframe
    :return turnover_ratio: 各分组日调仓日换手率 -> dataframe

    优化版本：使用向量化操作和索引映射，避免重复的列表推导和isin操作
    """
    # 1. 验证输入
    index_names = set(df.index.names)
    if not {"eob", "symbol"}.issubset(index_names):
        raise ValueError(f"df.index must contain 'eob' and 'symbol'. Found: {df.index.names}")

    if "close" not in df.columns or "fac_val" not in df.columns:
        raise ValueError(f"df must contain 'close' and 'fac_val' columns. Found: {df.columns}")

    # 2. 提取数据并计算未来收益率
    close_unstack = df["close"].unstack(level="symbol")
    factor_unstack = df["fac_val"].unstack(level="symbol")

    # 分层收益用逐日前瞻收益（t -> t+1）；n 只决定调仓频率。
    # 若用 pct_change(n)，周期内 n 行都会带着重叠的 n 日收益，连乘时被重复累计 n 次。
    future_return = close_unstack.pct_change().shift(-1)

    # 3. 合并数据
    merged = (
        pd.concat(
            [
                future_return.stack().rename("future_return"),
                factor_unstack.stack().rename("factor"),
            ],
            axis=1,
        )
        .dropna()
        .reset_index()
    )
    merged.columns = ["eob", "symbol", "future_return", "factor"]

    # 4. 获取调仓日期列表
    dates = sorted(merged["eob"].unique())
    rebalance_dates = dates[::n]  # 每n天调仓一次

    # 5. 预先构建日期索引映射 + symbol编码（关键优化）
    merged["eob_idx"] = pd.Categorical(merged["eob"], categories=dates, ordered=True).codes
    merged["symbol_code"] = pd.Categorical(merged["symbol"]).codes

    date_to_idx = {d: i for i, d in enumerate(dates)}
    rebalance_indices = [date_to_idx[d] for d in rebalance_dates]

    # 6. 预先排序，让后续操作更高效
    merged = merged.sort_values(["eob_idx", "symbol_code"]).reset_index(drop=True)

    # 7. 将symbol转为numpy数组，加速isin操作
    symbol_array = merged["symbol"].values
    eob_idx_array = merged["eob_idx"].values
    future_return_array = merged["future_return"].values
    eob_array = merged["eob"].values

    # 8. 计算各分组收益率和换手率
    group_return_list = []
    turnover_ratio_list = []
    prev_groups = {}  # 记录上一期的分组

    for i, rebalance_date in enumerate(rebalance_dates):
        # 获取调仓日的因子值（使用索引查找而非布尔索引）
        rebalance_idx = rebalance_indices[i]
        rebalance_mask = eob_idx_array == rebalance_idx
        rebalance_data = merged[rebalance_mask].copy()

        if len(rebalance_data) < g:
            continue

        # 按因子值分组（使用argsort加速）
        factor_values = rebalance_data["factor"].values
        sorted_indices = np.argsort(factor_values)
        n_symbols = len(sorted_indices)

        # 使用numpy分组，避免pd.qcut的开销
        try:
            group_ids = np.zeros(n_symbols, dtype=int)
            symbols_per_group = n_symbols // g
            for gid in range(g):
                start_idx = gid * symbols_per_group
                if gid == g - 1:  # 最后一组包含剩余所有
                    end_idx = n_symbols
                else:
                    end_idx = (gid + 1) * symbols_per_group
                group_ids[sorted_indices[start_idx:end_idx]] = gid + 1
        except Exception:
            # 如果有重复值导致分组失败，回退到pd.qcut
            rebalance_data = rebalance_data.sort_values("factor")
            rebalance_data["group"] = (
                pd.qcut(rebalance_data["factor"], g, labels=False, duplicates="drop") + 1
            )
            group_ids = rebalance_data["group"].values

        # 记录当前分组（向量化操作）
        current_groups = {}
        symbols_array = rebalance_data["symbol"].values
        for group_id in range(1, g + 1):
            current_groups[group_id] = set(symbols_array[group_ids == group_id])

        # 计算换手率（与上一期对比）
        if i > 0 and prev_groups:
            turnover_temp = {}
            for group_id in range(1, g + 1):
                prev_set = prev_groups.get(group_id, set())
                curr_set = current_groups.get(group_id, set())
                if len(prev_set) > 0:
                    turnover = len(prev_set.symmetric_difference(curr_set)) / len(prev_set)
                else:
                    turnover = 0
                turnover_temp[f"G{group_id}"] = turnover
            turnover_temp["eob"] = rebalance_date
            turnover_ratio_list.append(turnover_temp)

        prev_groups = current_groups

        # 使用索引范围代替列表推导和isin（关键优化）
        if i < len(rebalance_dates) - 1:
            next_rebalance_idx = rebalance_indices[i + 1]
            period_mask = (eob_idx_array >= rebalance_idx) & (eob_idx_array < next_rebalance_idx)
        else:
            period_mask = eob_idx_array >= rebalance_idx

        # 提取区间数据
        period_eob = eob_array[period_mask]
        period_symbol = symbol_array[period_mask]
        period_return = future_return_array[period_mask]

        # 计算各分组的平均收益率（向量化 + numpy加速）
        group_return_temp = {}
        unique_dates = np.unique(period_eob)

        for group_id in range(1, g + 1):
            group_symbols = current_groups[group_id]
            # 使用numpy的isin，比pandas快
            symbol_mask = np.isin(period_symbol, list(group_symbols))

            if symbol_mask.sum() > 0:
                # 按日期分组计算平均收益（向量化）
                group_eob = period_eob[symbol_mask]
                group_ret = period_return[symbol_mask]

                # 使用bincount加速分组求和
                date_to_code = {d: idx for idx, d in enumerate(unique_dates)}
                date_codes = np.array([date_to_code[d] for d in group_eob])

                counts = np.bincount(date_codes, minlength=len(unique_dates))
                sums = np.bincount(date_codes, weights=group_ret, minlength=len(unique_dates))

                means = np.divide(sums, counts, where=counts > 0, out=np.zeros_like(sums))

                group_return_temp[f"G{group_id}"] = pd.Series(means, index=unique_dates)

        if group_return_temp:
            group_return_list.append(pd.DataFrame(group_return_temp))

        if verbose:
            print(f"\r当前：{i + 1} / 总量：{len(rebalance_dates)}", end="")

    if verbose:
        print()

    # 9. 合并结果
    if group_return_list:
        group_return = pd.concat(group_return_list, axis=0)
    else:
        group_return = pd.DataFrame()

    if turnover_ratio_list:
        turnover_ratio = pd.DataFrame(turnover_ratio_list).set_index("eob")
        turnover_ratio = turnover_ratio.reindex(group_return.index, fill_value=0)
    else:
        turnover_ratio = pd.DataFrame()

    return group_return, turnover_ratio


def full_stat(
    df: pd.DataFrame,
    n: int = 1,
    g: int = 5,
    rank_IC: bool = True,
    verbose: bool = False,
    plot: bool = True,
):
    """
    完整的因子检测统计，包括IC分析和分层回测

    :param df: columns 为 ['close', 'fac_val'], multi-index 为 ['eob', 'symbol']
    :param n: 调仓周期 -> int
    :param g: 分组数量 -> int
    :param rank_IC: 是否使用秩相关 -> bool
    :param plot: 是否绘图+打印摘要；批量评测时传 False 走静默路径
    :return: IC统计字典, IC序列, 分组收益率, 换手率
    """
    ic_stat_dict, ic_series = IC_stat(df, rank_IC=rank_IC, n=n)

    group_return, turnover = group_stat(df, n=n, g=g, verbose=verbose)

    if not plot:
        return ic_stat_dict, ic_series, group_return, turnover

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # 图1: 累计IC曲线（重复显示，方便对比）
    ax1 = axes[0, 0]
    ic_series.cumsum().plot(
        ax=ax1, title="Cumulative IC", grid=True, linewidth=1.5, color="steelblue"
    )
    ax1.axhline(y=0, color="r", linestyle="--", linewidth=1, alpha=0.5)
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Cumulative IC")

    # 图2: 分层效应检验
    ax2 = axes[0, 1]
    group_return_with_benchmark = group_return.copy()
    group_return_with_benchmark["Benchmark"] = group_return.mean(axis=1)
    group_return_cumprod = (group_return_with_benchmark + 1).cumprod()
    group_return_cumprod.plot(ax=ax2, title="Layered Effect Test", linewidth=1.5)
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Cumulative Return")
    ax2.legend(loc="best")
    ax2.grid(True, alpha=0.3)

    # 图3: 多空效应检验
    ax3 = axes[1, 0]
    group_return_cumprod_for_tbd = (group_return + 1).cumprod()
    benchmark = group_return_cumprod_for_tbd.mean(axis=1)

    Down_Benchmark = -(group_return_cumprod_for_tbd["G1"] - benchmark)
    Top_Benchmark = group_return_cumprod_for_tbd[f"G{g}"] - benchmark
    Top_Down = Top_Benchmark + Down_Benchmark

    TBD = pd.concat([Down_Benchmark, Top_Benchmark, Top_Down], axis=1)
    TBD.columns = ["Down_Benchmark", "Top_Benchmark", "Top_Down"]
    TBD.plot(ax=ax3, title="Long-Short Effect Test", linewidth=1.5)
    ax3.set_xlabel("Date")
    ax3.set_ylabel("Excess Return vs Benchmark")
    ax3.legend(loc="best")
    ax3.grid(True, alpha=0.3)

    # 图4: 分组换手率
    ax4 = axes[1, 1]
    if not turnover.empty:
        turnover.plot(ax=ax4, title="Group Turnover Ratio", linewidth=1.5, markersize=3)
        ax4.set_xlabel("Date")
        ax4.set_ylabel("Turnover Ratio")
        ax4.legend(loc="best")
        ax4.grid(True, alpha=0.3)
        # 显示平均换手率
        turnover_mean = turnover.mean()
        mean_text = "\n".join([f"{k}: {v:.4f}" for k, v in turnover_mean.items()])
        ax4.text(
            0.02,
            0.98,
            f"Mean Turnover:\n{mean_text}",
            transform=ax4.transAxes,
            verticalalignment="top",
            fontsize=9,
            bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5},
        )

    plt.tight_layout()
    plt.show()

    # 打印统计摘要
    print("\n" + "=" * 60)
    print("IC Statistics Summary:")
    print("=" * 60)
    for key, value in ic_stat_dict.items():
        if key != "IC_series":
            print(f"{key}: {value}")

    print("\n" + "=" * 60)
    print("Group Return Summary (Final Cumulative Return):")
    print("=" * 60)
    if not group_return.empty:
        final_returns = (group_return + 1).cumprod().iloc[-1]
        for col in final_returns.index:
            print(f"{col}: {final_returns[col]:.4f}")

    print("\n" + "=" * 60)
    print("Mean Turnover Ratio:")
    print("=" * 60)
    if not turnover.empty:
        print(turnover.mean())

    return ic_stat_dict, ic_series, group_return, turnover
