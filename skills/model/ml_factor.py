"""
ML因子排序引擎

利用PyCaret集成XGBoost/随机森林模型，将多因子信号压缩为单一ML排序因子。
对 Backtester 模块的扩展 (Open/Closed Principle: 对扩展开放，对修改关闭)。

核心流程:
1. 多因子 → 特征矩阵 (date, symbol, features)
2. PyCaret 训练 (fold_strategy='timeseries' k-fold CV)
3. 预测值 → 截面 rank (0~1)
4. rank pivot 包装为 Backtester 兼容的因子函数

训练模式:
- fixed: 固定窗口, 前 train_ratio 训练, 后面测试
- rolling: 累积训练 (expanding), 每 retrain_freq 天累积所有历史数据重训练

用法:
    from skills.model.ml_factor import MLFactorEngine, make_precomputed_factor
    from skills.compute import indicators as I

    engine = MLFactorEngine(
        data=multiindex_df,
        factor_configs=[
            {'func': I.trend_score_v2, 'kwargs': {'period': 24}, 'name': 'trend'},
            {'func': I.cci, 'kwargs': {'period': 48}, 'name': 'cci'},
        ],
        model_type='xgboost',
        train_mode='rolling',
    )
    rank_pivot = engine.generate()
    ml_factor_func = make_precomputed_factor(rank_pivot, name='ml_rank')
"""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ---------------------------------------------------------------------------
# PyCaret lazy import (avoid slow startup when module is just imported)
# ---------------------------------------------------------------------------


def _get_pycaret_regression():
    from pycaret.regression import RegressionExperiment

    return RegressionExperiment


# ---------------------------------------------------------------------------
# Helper: 将预计算 pivot 包装为 Backtester 兼容因子函数
# ---------------------------------------------------------------------------


def make_precomputed_factor(pivot_df: pd.DataFrame, name: str = "ml_prediction"):
    """
    将预计算的 pivot (date × symbol) 包装为 Backtester 兼容的因子函数。

    Backtester 内部调用:
        data.groupby(level='symbol', group_keys=False).apply(func)
    每个 group 是 MultiIndex (symbol, eob) 的 DataFrame (同一 symbol)。
    本函数返回的闭包会从 pivot 中提取对应 symbol 列返回。

    Parameters
    ----------
    pivot_df : pd.DataFrame
        索引为日期, 列为 symbol, 值为因子数值 (此处为 rank 0~1)
    name : str
        函数名 (用于 Backtester 因子缓存 key)
    """

    def _factor(group_df, **kwargs):
        symbol = group_df.index.get_level_values("symbol")[0]
        eob_idx = group_df.index.get_level_values("eob")
        if symbol in pivot_df.columns:
            values = pivot_df[symbol].reindex(eob_idx).values
            return pd.Series(values, index=group_df.index)
        return pd.Series(np.nan, index=group_df.index)

    _factor.__name__ = name
    return _factor


# ---------------------------------------------------------------------------
# MLFactorEngine
# ---------------------------------------------------------------------------


class MLFactorEngine:
    """
    ML因子排序引擎

    Parameters
    ----------
    data : pd.DataFrame
        MultiIndex (symbol, eob) DataFrame, 列包含 open/high/low/close/volume
    factor_configs : list of dict
        因子配置列表, 格式同 Backtester:
        [{'func': callable, 'kwargs': dict, 'name': str}, ...]
    model_type : str
        PyCaret 模型标识: 'xgboost' | 'rf' (随机森林)
    target_forward : int
        前瞻 N 期收益作为训练标签 (默认 1)
    train_mode : str
        'fixed' (固定窗口) | 'rolling' (expanding窗口, 累积所有历史)
    train_ratio : float
        fixed 模式的训练集时间占比 (默认 0.7)
    train_window : int
        rolling 模式的初始训练窗口 (交易日, 默认 120).
        采用 expanding 策略: 首次用前 train_window 天训练,
        之后每次重训练累积所有历史数据 (不丢弃旧数据).
    retrain_freq : int
        rolling 模式的重训练间隔 (交易日, 默认 20)
    n_folds : int
        PyCaret k-fold CV 折数 (默认 5)
    pycaret_kwargs : dict, optional
        额外传给 PyCaret setup() 的参数
    """

    def __init__(
        self,
        data,
        factor_configs,
        model_type="xgboost",
        target_forward=1,
        train_mode="rolling",
        train_ratio=0.7,
        train_window=120,
        retrain_freq=20,
        n_folds=5,
        pycaret_kwargs=None,
    ):
        self.data = data
        self.factor_configs = factor_configs
        self.model_type = model_type
        self.target_forward = target_forward
        self.train_mode = train_mode
        self.train_ratio = train_ratio
        self.train_window = train_window
        self.retrain_freq = retrain_freq
        self.n_folds = n_folds
        self.pycaret_kwargs = pycaret_kwargs or {}

        # 因子名列表
        self.feature_names = [c.get("name", c["func"].__name__) for c in factor_configs]

        # ---- 结果属性 (generate() 后填充) ----
        self.prediction_rank_pivot = None  # 截面 rank pivot (date × symbol)
        self.eval_df = None  # 逐日 IC, 列: eob, ic, period_type
        self.cv_metrics_list = []  # per-window PyCaret CV 指标
        self.holdout_metrics_list = []  # per-window PyCaret holdout 指标
        self.models = []  # 训练得到的模型对象
        self.feature_importance_df = None  # 因子重要性
        self.oos_start_date = None  # 样本外起始日期

        # 内部缓存
        self._feature_df = None
        self._dates = None

    # ------------------------------------------------------------------
    # Step 1: 特征矩阵构建
    # ------------------------------------------------------------------

    def _build_feature_matrix(self):
        """构建 flat panel: (date, symbol, f1, ..., fN, forward_return)"""
        print("   构建特征矩阵...")

        # 计算每个因子的 pivot
        factor_pivots = {}
        for config in self.factor_configs:
            func = config["func"]
            kwargs = config.get("kwargs", {})
            name = config.get("name", func.__name__)
            print(f"     计算因子: {name}")
            series = self.data.groupby(level="symbol", group_keys=False).apply(
                lambda g, _f=func, _k=kwargs: _f(g, **_k)
            )
            pivot = series.unstack(level="symbol")
            factor_pivots[name] = pivot

        # Stack 为 flat panel
        panels = {}
        for name, pivot in factor_pivots.items():
            panels[name] = pivot.stack()
        feature_df = pd.DataFrame(panels)

        # forward return → 截面 rank 作为标签
        # 先算原始前瞻收益, 再按每个截面日期做 rank(pct=True)
        close_pivot = self.data["close"].unstack(level="symbol")
        forward_ret = close_pivot.shift(-self.target_forward) / close_pivot - 1
        forward_ret_rank = forward_ret.rank(axis=1, pct=True)  # 每行(日期)内排序
        feature_df["forward_return"] = forward_ret.stack()  # 保留原始收益(用于IC计算)
        feature_df["forward_rank"] = forward_ret_rank.stack()  # rank标签(用于模型训练)

        # Reset index
        feature_df = feature_df.reset_index()
        feature_df.columns = (
            ["eob", "symbol"] + self.feature_names + ["forward_return", "forward_rank"]
        )

        # 确保 eob 是 Timestamp
        feature_df["eob"] = pd.to_datetime(feature_df["eob"])

        # 按时间排序 (PyCaret timeseries CV 依赖行顺序)
        feature_df = feature_df.sort_values("eob").reset_index(drop=True)

        # Drop NaN
        n_before = len(feature_df)
        feature_df = feature_df.dropna().reset_index(drop=True)
        n_after = len(feature_df)

        dates = sorted(feature_df["eob"].unique())
        dates = [pd.Timestamp(d) for d in dates]  # 确保是 Timestamp
        n_symbols = feature_df["symbol"].nunique()
        print(f"   特征矩阵: {n_after} 行 (删除 {n_before - n_after} NaN)")
        print(
            f"   日期: {dates[0].strftime('%Y-%m-%d')} ~ "
            f"{dates[-1].strftime('%Y-%m-%d')}, {len(dates)} 天, {n_symbols} 只标的"
        )

        self._feature_df = feature_df
        self._dates = dates

    # ------------------------------------------------------------------
    # Step 2: 截面 rank & IC 计算
    # ------------------------------------------------------------------

    def _compute_cross_sectional_rank(self, pred_df):
        """对每个截面日期, 将 prediction_label → rank (pct=True, 0~1)"""
        result = pred_df[["eob", "symbol"]].copy()
        result["rank"] = pred_df.groupby("eob")["prediction_label"].rank(pct=True)
        return result

    def _compute_ic_series(self, pred_df):
        """逐日 Rank IC (Spearman): rank_corr(prediction_label, forward_return)"""

        def _ic(group):
            p = group["prediction_label"]
            a = group["forward_return"]
            mask = p.notna() & a.notna()
            g = group[mask]
            if len(g) < 3:
                return np.nan
            ic, _ = spearmanr(g["prediction_label"], g["forward_return"])
            return ic

        ic_series = pred_df.groupby("eob").apply(_ic)
        return pd.DataFrame({"eob": ic_series.index, "ic": ic_series.values})

    # ------------------------------------------------------------------
    # Step 3a: 固定窗口训练
    # ------------------------------------------------------------------

    def _train_predict_fixed(self):
        """固定窗口: 前 train_ratio 训练, 后面测试"""
        print(f"\n[训练模式: 固定窗口] train_ratio={self.train_ratio}")

        df = self._feature_df
        dates = self._dates
        split_idx = int(len(dates) * self.train_ratio)
        split_date = dates[split_idx]
        self.oos_start_date = split_date

        train_df = df[df["eob"] < split_date].copy().reset_index(drop=True)
        test_df = df[df["eob"] >= split_date].copy().reset_index(drop=True)

        print(
            f"   训练集: {len(train_df)} 行, "
            f"{dates[0].strftime('%Y-%m-%d')} ~ {split_date.strftime('%Y-%m-%d')}"
        )
        print(
            f"   测试集: {len(test_df)} 行, "
            f"{split_date.strftime('%Y-%m-%d')} ~ {dates[-1].strftime('%Y-%m-%d')}"
        )

        # PyCaret setup
        RegressionExperiment = _get_pycaret_regression()
        exp = RegressionExperiment()

        setup_kwargs = {
            "data": train_df,
            "test_data": test_df,
            "target": "forward_rank",
            "index": False,
            "fold_strategy": "timeseries",
            "fold": self.n_folds,
            "data_split_shuffle": False,
            "normalize": True,
            "numeric_imputation": "mean",
            "ignore_features": ["eob", "symbol", "forward_return"],
            "session_id": 42,
            "verbose": False,
            "html": False,
        }
        setup_kwargs.update(self.pycaret_kwargs)
        exp.setup(**setup_kwargs)

        # 训练 (k-fold CV)
        print(f"   训练 {self.model_type} (timeseries {self.n_folds}-fold CV)...")
        model = exp.create_model(self.model_type, verbose=False)
        cv_metrics = exp.pull()
        self.cv_metrics_list.append(cv_metrics)
        self.models.append(model)

        mean_row = cv_metrics.loc["Mean"]
        print(
            f"   CV (in-sample):  MAE={mean_row['MAE']:.4f}  "
            f"MSE={mean_row['MSE']:.4f}  R2={mean_row['R2']:.4f}"
        )

        # Holdout 指标
        exp.predict_model(model, verbose=False)
        holdout_metrics = exp.pull()
        self.holdout_metrics_list.append(holdout_metrics)
        print(
            f"   Holdout (OOS):   MAE={holdout_metrics['MAE'].iloc[0]:.4f}  "
            f"MSE={holdout_metrics['MSE'].iloc[0]:.4f}  "
            f"R2={holdout_metrics['R2'].iloc[0]:.4f}"
        )

        # 在 train / test 上分别预测
        train_pred = exp.predict_model(model, data=train_df, verbose=False)
        test_pred = exp.predict_model(model, data=test_df, verbose=False)

        # 截面 rank
        train_rank = self._compute_cross_sectional_rank(train_pred)
        test_rank = self._compute_cross_sectional_rank(test_pred)
        all_rank = pd.concat([train_rank, test_rank], ignore_index=True)
        self.prediction_rank_pivot = all_rank.pivot(index="eob", columns="symbol", values="rank")

        # IC
        train_ic = self._compute_ic_series(train_pred)
        train_ic["period_type"] = "in_sample"
        test_ic = self._compute_ic_series(test_pred)
        test_ic["period_type"] = "out_of_sample"
        self.eval_df = pd.concat([train_ic, test_ic], ignore_index=True)

        # Feature importance
        self._extract_feature_importance()

    # ------------------------------------------------------------------
    # Step 3b: 累积训练 (expanding)
    # ------------------------------------------------------------------

    def _train_predict_rolling(self):
        """Expanding 窗口: 初始用前 train_window 天, 之后每 retrain_freq 天
        累积所有历史数据重训练 (不丢弃旧数据)."""
        print(
            f"\n[训练模式: expanding] "
            f"init_window={self.train_window}, retrain_freq={self.retrain_freq}"
        )

        df = self._feature_df
        dates = self._dates

        # 重训练时间点: 从 train_window 开始, 每 retrain_freq 天重训练一次
        retrain_indices = list(range(self.train_window, len(dates), self.retrain_freq))
        if not retrain_indices:
            raise ValueError(
                f"train_window={self.train_window} >= 数据天数={len(dates)}, 无法创建训练窗口"
            )

        self.oos_start_date = dates[retrain_indices[0]]
        print(f"   共 {len(retrain_indices)} 个训练窗口")
        print(f"   样本外起始: {self.oos_start_date.strftime('%Y-%m-%d')}")

        all_rank_records = []
        all_ic_records = []
        RegressionExperiment = _get_pycaret_regression()

        for i, retrain_idx in enumerate(retrain_indices):
            # Expanding: 训练数据从第0天开始, 到当前重训练点
            train_end = retrain_idx
            predict_end = min(retrain_idx + self.retrain_freq, len(dates))

            train_dates = dates[0:train_end]  # 累积所有历史
            predict_dates = dates[train_end:predict_end]

            if not predict_dates:
                break

            train_data = df[df["eob"].isin(train_dates)].copy().reset_index(drop=True)
            predict_data = df[df["eob"].isin(predict_dates)].copy().reset_index(drop=True)

            if len(train_data) < 20 or len(predict_data) < 1:
                continue

            pct = (i + 1) / len(retrain_indices) * 100
            print(
                f"\r   窗口 {i + 1}/{len(retrain_indices)} ({pct:.0f}%) "
                f"train: {train_dates[0].strftime('%m/%d')}~"
                f"{train_dates[-1].strftime('%m/%d')} "
                f"({len(train_dates)}d) -> "
                f"pred: {predict_dates[0].strftime('%m/%d')}~"
                f"{predict_dates[-1].strftime('%m/%d')}",
                end="",
            )

            # PyCaret
            exp = RegressionExperiment()
            n_folds = min(self.n_folds, max(2, len(train_dates) // 10))
            setup_kwargs = {
                "data": train_data,
                "test_data": predict_data,
                "target": "forward_rank",
                "index": False,
                "fold_strategy": "timeseries",
                "fold": n_folds,
                "data_split_shuffle": False,
                "normalize": True,
                "numeric_imputation": "mean",
                "ignore_features": ["eob", "symbol", "forward_return"],
                "session_id": 42 + i,
                "verbose": False,
                "html": False,
            }
            setup_kwargs.update(self.pycaret_kwargs)

            try:
                exp.setup(**setup_kwargs)
                model = exp.create_model(self.model_type, verbose=False)
                cv_metrics = exp.pull()
                self.cv_metrics_list.append(cv_metrics)
                self.models.append(model)

                # Holdout
                exp.predict_model(model, verbose=False)
                holdout_metrics = exp.pull()
                self.holdout_metrics_list.append(holdout_metrics)

                # Predictions → rank & IC
                train_pred = exp.predict_model(model, data=train_data, verbose=False)
                predict_pred = exp.predict_model(model, data=predict_data, verbose=False)

                # Rank (collect OOS for pivot, IS for IC only)
                predict_rank = self._compute_cross_sectional_rank(predict_pred)
                all_rank_records.append(predict_rank)

                # IC
                train_ic = self._compute_ic_series(train_pred)
                train_ic["period_type"] = "in_sample"
                predict_ic = self._compute_ic_series(predict_pred)
                predict_ic["period_type"] = "out_of_sample"
                all_ic_records.extend([train_ic, predict_ic])

            except Exception as e:
                print(f"\n   [WARN] 窗口 {i + 1} 失败: {e}")
                continue

        print()  # newline after progress

        # 合并结果
        if all_rank_records:
            all_rank_df = pd.concat(all_rank_records, ignore_index=True)
            all_rank_df = all_rank_df.drop_duplicates(subset=["eob", "symbol"], keep="last")
            self.prediction_rank_pivot = all_rank_df.pivot(
                index="eob", columns="symbol", values="rank"
            )

        if all_ic_records:
            self.eval_df = pd.concat(all_ic_records, ignore_index=True)
            self.eval_df = self.eval_df.drop_duplicates(subset=["eob", "period_type"], keep="last")

        # Feature importance (多窗口平均)
        self._extract_feature_importance()

        # 汇总打印
        if self.cv_metrics_list:
            cv_means = pd.concat([m.loc[["Mean"]] for m in self.cv_metrics_list])
            ho_all = pd.concat(self.holdout_metrics_list)
            print(f"\n   === 汇总 ({len(self.cv_metrics_list)} 窗口) ===")
            print(
                f"   CV (IS avg):  MAE={cv_means['MAE'].mean():.4f}  "
                f"MSE={cv_means['MSE'].mean():.4f}  "
                f"R2={cv_means['R2'].mean():.4f}"
            )
            print(
                f"   Holdout (OOS): MAE={ho_all['MAE'].mean():.4f}  "
                f"MSE={ho_all['MSE'].mean():.4f}  "
                f"R2={ho_all['R2'].mean():.4f}"
            )

    # ------------------------------------------------------------------
    # Feature importance
    # ------------------------------------------------------------------

    def _extract_feature_importance(self):
        """从模型中提取 feature_importances_ (XGBoost / RF 原生支持)"""
        importances = []
        for model in self.models:
            if hasattr(model, "feature_importances_"):
                importances.append(model.feature_importances_)

        if importances:
            avg_imp = np.mean(importances, axis=0)
            self.feature_importance_df = (
                pd.DataFrame(
                    {
                        "feature": self.feature_names,
                        "importance": avg_imp,
                    }
                )
                .sort_values("importance", ascending=False)
                .reset_index(drop=True)
            )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def generate(self) -> pd.DataFrame:
        """
        运行完整 ML 流程, 返回截面 rank pivot。

        Returns
        -------
        pd.DataFrame
            rank pivot (date × symbol), 值域 [0, 1]
        """
        print("=" * 60)
        print(f"MLFactorEngine: {self.model_type} | mode={self.train_mode}")
        print("=" * 60)

        # Step 1
        print("\n[Step 1] 构建特征矩阵")
        self._build_feature_matrix()

        # Step 2
        print("\n[Step 2] 模型训练与预测")
        if self.train_mode == "fixed":
            self._train_predict_fixed()
        elif self.train_mode == "rolling":
            self._train_predict_rolling()
        else:
            raise ValueError(f"Unknown train_mode: {self.train_mode}")

        print("\nMLFactorEngine 完成!")
        return self.prediction_rank_pivot

    # ------------------------------------------------------------------
    # 评估接口
    # ------------------------------------------------------------------

    def get_feature_importance(self) -> pd.DataFrame:
        """返回因子重要性 DataFrame (feature, importance)"""
        if self.feature_importance_df is None:
            raise ValueError("请先调用 generate()")
        return self.feature_importance_df

    def get_eval_summary(self) -> dict:
        """
        返回评估摘要字典, 包含:
        - in_sample / out_of_sample: IC 统计
        - cv_metrics_mean: PyCaret CV 指标均值
        - holdout_metrics_mean: PyCaret holdout 指标均值
        """
        if self.eval_df is None:
            raise ValueError("请先调用 generate()")

        summary = {}
        for period_type in ["in_sample", "out_of_sample"]:
            subset = self.eval_df[self.eval_df["period_type"] == period_type]
            if len(subset) > 0:
                ic_vals = subset["ic"].dropna()
                summary[period_type] = {
                    "ic_mean": ic_vals.mean(),
                    "ic_std": ic_vals.std(),
                    "ir": (ic_vals.mean() / ic_vals.std() if ic_vals.std() > 0 else 0),
                    "positive_ic_ratio": (ic_vals > 0).mean(),
                    "n_dates": len(ic_vals),
                }

        if self.cv_metrics_list:
            cv_means = pd.concat([m.loc[["Mean"]] for m in self.cv_metrics_list])
            summary["cv_metrics_mean"] = cv_means.mean().to_dict()

        if self.holdout_metrics_list:
            ho_all = pd.concat(self.holdout_metrics_list)
            summary["holdout_metrics_mean"] = ho_all.mean().to_dict()

        return summary
