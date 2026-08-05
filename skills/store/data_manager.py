"""
Quant Research Data Manager

Core concepts:
  - Single-symbol market data stored as individual Parquet files
  - Explicit symbol lists are loaded as MultiIndex panels
  - Derived artifacts are stored under caller-provided namespace strings

Usage:
    from skills.store.data_manager import DataManager
    dm = DataManager()
    dm.import_combined_csv('E:/datasets/ETF_1d/etf_rotation_daily.csv')
    data = dm.read_symbols(['SHSE.510300', 'SHSE.510500'], frequency='1d')
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from skills.store.workspace import resolve_workspace_paths

# ======================================================================
# Base path resolution
# ======================================================================


def _get_data_root() -> Path:
    """Return the data root directory for the workspace."""
    return resolve_workspace_paths().data_root


# ======================================================================
# OHLCV validation
# ======================================================================


@dataclass
class DataQualityReport:
    """Structured result of OHLCV validation checks."""

    passed: bool
    n_rows: int
    nan_count: int
    inf_count: int
    negative_price_count: int
    negative_volume_count: int
    high_lt_low_count: int
    non_monotonic_index: bool
    details: dict = field(default_factory=dict)

    def summary(self) -> str:
        """Return a human-readable summary of validation results."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"Data quality: {status} (n_rows={self.n_rows})",
            f"  NaN (numeric): {self.nan_count}, Inf (float): {self.inf_count}",
            f"  Negative price cells: {self.negative_price_count}, negative volume: {self.negative_volume_count}",
            f"  high < low: {self.high_lt_low_count}, non-monotonic index: {self.non_monotonic_index}",
        ]
        if self.details:
            lines.append(f"  details: {self.details}")
        return "\n".join(lines)


def validate_ohlcv(df: pd.DataFrame) -> DataQualityReport:
    """
    Validate an OHLCV DataFrame (index ``eob``, columns include OHLCV).

    Read-only: reports issues only; does not modify ``df``.
    Uses vectorized pandas/numpy operations for large panels.
    """
    n_rows = len(df)
    idx = df.index
    non_monotonic_index = not idx.is_monotonic_increasing

    numeric = df.select_dtypes(include=[np.number])
    nan_count = int(numeric.isna().sum().sum()) if numeric.shape[1] else 0

    float_numeric = numeric.select_dtypes(include=[np.floating])
    if float_numeric.shape[1]:
        inf_count = int(np.isinf(float_numeric.to_numpy(copy=False)).sum())
    else:
        inf_count = 0

    price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
    if price_cols:
        negative_price_count = int((df[price_cols] < 0).sum().sum())
    else:
        negative_price_count = 0

    if "volume" in df.columns:
        negative_volume_count = int((df["volume"] < 0).sum())
    else:
        negative_volume_count = 0

    if "high" in df.columns and "low" in df.columns:
        high_lt_low_count = int((df["high"] < df["low"]).sum())
    else:
        high_lt_low_count = 0

    passed = (
        nan_count == 0
        and inf_count == 0
        and negative_price_count == 0
        and negative_volume_count == 0
        and high_lt_low_count == 0
        and not non_monotonic_index
    )

    details = {
        "numeric_columns": list(numeric.columns),
        "price_columns_checked": price_cols,
        "volume_checked": "volume" in df.columns,
        "high_low_checked": "high" in df.columns and "low" in df.columns,
    }

    return DataQualityReport(
        passed=passed,
        n_rows=n_rows,
        nan_count=nan_count,
        inf_count=inf_count,
        negative_price_count=negative_price_count,
        negative_volume_count=negative_volume_count,
        high_lt_low_count=high_lt_low_count,
        non_monotonic_index=non_monotonic_index,
        details=details,
    )


# ======================================================================
# DataManager
# ======================================================================


class DataManager:
    """
    Central data manager for the quant research system.

    All paths are relative to the data root directory.
    Market data, factors, tests, and backtests are Parquet files.

    Usage:
        dm = DataManager()
        data = dm.read_symbols(['SHSE.510300', 'SHSE.510500'], frequency='1d')
    """

    def __init__(self, data_root: str = None):
        self.root = Path(data_root) if data_root else _get_data_root()
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _ensure_dirs(self):
        """Create top-level directories if missing."""
        for d in [
            "market/1d",
            "market/1m",
            "market/5m",
            "factors",
            "factor_test",
            "correlation",
            "backtest",
            "export",
            "models",
        ]:
            (self.root / d).mkdir(parents=True, exist_ok=True)

    # ==================================================================
    # 1. Market Data — single symbol IO
    # ==================================================================

    def read_symbol(self, symbol: str, frequency: str = "1d") -> pd.DataFrame:
        """Read a single symbol's OHLCV data. Index: eob."""
        path = self.root / "market" / frequency / f"{symbol}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"{path}")
        return pd.read_parquet(path)

    def read_symbols(self, symbols: list[str], frequency: str = "1d") -> pd.DataFrame:
        """Read explicit symbols into a standard MultiIndex panel.

        Returns a DataFrame indexed by ``(symbol, eob)``. Missing files are
        reported together so research scripts fail with one actionable error.
        """
        frames = []
        missing = []
        for symbol in symbols:
            try:
                bars = self.read_symbol(symbol, frequency=frequency).copy()
            except FileNotFoundError:
                missing.append(symbol)
                continue
            bars.index = pd.to_datetime(bars.index)
            bars.index.name = "eob"
            bars["symbol"] = symbol
            frames.append(bars.reset_index().set_index(["symbol", "eob"]))
        if missing:
            raise FileNotFoundError(
                f"Missing {frequency} Parquet files for symbols: {missing}. "
                f"Expected files under {self.root / 'market' / frequency}."
            )
        if not frames:
            raise ValueError("symbols cannot be empty.")
        return pd.concat(frames).sort_index()

    def save_symbol(
        self, symbol: str, df: pd.DataFrame, frequency: str = "1d", source: str = "unknown"
    ):
        """
        Save a single symbol's OHLCV DataFrame to Parquet.
        df must have eob as index and OHLCV columns.
        """
        out_dir = self.root / "market" / frequency
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{symbol}.parquet"
        df.to_parquet(path)

    def import_symbol_csv(
        self, csv_path: str, symbol: str, frequency: str = "1d", time_col: str = "eob"
    ):
        """Import a single-symbol CSV -> Parquet."""
        df = pd.read_csv(csv_path)
        df[time_col] = (
            pd.to_datetime(df[time_col], utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.tz_localize(None)
        )
        df = df.set_index(time_col).sort_index()
        df.index.name = "eob"
        cols = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in cols if c in df.columns]]
        self.save_symbol(symbol, df, frequency, source="csv_import")

    def import_combined_csv(
        self,
        csv_path: str,
        frequency: str = "1d",
        symbol_col: str = "symbol",
        time_col: str = "eob",
    ) -> list[str]:
        """
        Import a combined multi-symbol CSV -> split into individual Parquet.
        Returns list of symbols imported.
        """
        print(f"Reading {csv_path} ...")
        df = pd.read_csv(csv_path)
        df[time_col] = (
            pd.to_datetime(df[time_col], utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.tz_localize(None)
        )

        symbols = sorted(df[symbol_col].unique())
        print(f"Found {len(symbols)} symbols, splitting ...")

        out_dir = self.root / "market" / frequency
        out_dir.mkdir(parents=True, exist_ok=True)

        cols = ["open", "high", "low", "close", "volume"]
        keep_cols = [c for c in cols if c in df.columns]

        for sym in symbols:
            sym_df = df[df[symbol_col] == sym].copy()
            sym_df = sym_df.set_index(time_col).sort_index()
            sym_df.index.name = "eob"
            sym_df = sym_df[keep_cols]
            path = out_dir / f"{sym}.parquet"
            sym_df.to_parquet(path)

        print(f"Imported {len(symbols)} symbols to {out_dir}")
        return symbols

    def list_symbols(self, frequency: str = "1d") -> list[str]:
        """List all available symbols for a frequency."""
        market_dir = self.root / "market" / frequency
        if not market_dir.exists():
            return []
        return sorted(p.stem for p in market_dir.glob("*.parquet"))

    # ==================================================================
    # 1b. Adjustment Factors (event-based, one row per ex-date)
    # ==================================================================

    def _adj_factor_dir(self) -> Path:
        return self.root / "adj_factor"

    def save_adj_factor(self, symbol: str, df: pd.DataFrame, source: str = "unknown"):
        """Save per-symbol adjustment factor events.

        df should carry one row per corporate-action event with an ``ex_date``
        index (DatetimeIndex) and columns such as ``ex_cum_factor``,
        ``ex_factor``, ``ex_end_date``, ``announcement_date``.
        """
        out_dir = self._adj_factor_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_dir / f"{symbol}.parquet")

    def read_adj_factor(self, symbol: str) -> pd.DataFrame:
        """Read per-symbol adjustment factor events."""
        path = self._adj_factor_dir() / f"{symbol}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"{path}")
        return pd.read_parquet(path)

    def list_adj_factors(self) -> list[str]:
        """List symbols with saved adjustment-factor data."""
        d = self._adj_factor_dir()
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.parquet"))

    def list_models(self, namespace: str) -> list[dict]:
        """List saved ML models for a namespace (from ``metadata.json``), newest first."""
        namespace_dir = self.root / "models" / namespace
        if not namespace_dir.is_dir():
            return []
        metas = []
        for sub in namespace_dir.iterdir():
            if not sub.is_dir():
                continue
            meta_path = sub / "metadata.json"
            if meta_path.is_file():
                with open(meta_path, encoding="utf-8") as f:
                    metas.append(json.load(f))
        metas.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return metas

    def read_model_metadata(self, namespace: str, model_id: str) -> dict:
        """Read ``metadata.json`` for one saved model."""
        path = self.root / "models" / namespace / model_id / "metadata.json"
        if not path.exists():
            raise FileNotFoundError(f"{path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # ==================================================================
    # 2. Factor Data (scoped to artifact namespace)
    # ==================================================================

    @staticmethod
    def factor_filename(func_name: str, params: dict | None = None) -> str:
        """Public stable factor cache filename under ``data/factors/<namespace>/``."""
        params = params or {}
        param_str = "_".join(str(v) for v in params.values()) if params else "default"
        return f"{func_name}__{param_str}.parquet"

    @staticmethod
    def _factor_filename(func_name: str, params: dict) -> str:
        return DataManager.factor_filename(func_name, params)

    @staticmethod
    def _factor_id(func_name: str, params: dict) -> str:
        param_str = "_".join(str(v) for v in params.values()) if params else "default"
        return f"{func_name}__{param_str}"

    def read_factor(
        self, namespace: str, func_name: str, params: dict = None
    ) -> pd.DataFrame | None:
        """Read cached factor pivot for a namespace. Returns None on cache miss."""
        params = params or {}
        filename = self._factor_filename(func_name, params)
        path = self.root / "factors" / namespace / filename
        if not path.exists():
            return None
        return pd.read_parquet(path)

    def save_factor(self, namespace: str, func_name: str, params: dict, pivot_df: pd.DataFrame):
        """Save a factor pivot (date x symbol) for a namespace.

        Callers that need stable cache addressing should put a content-addressed
        key inside ``params`` (for example ``cache_key`` from factor_mining).
        """
        params = params or {}
        out_dir = self.root / "factors" / namespace
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = self._factor_filename(func_name, params)
        pivot_df.to_parquet(out_dir / filename)

    def factor_namespace_dir(self, namespace: str) -> Path:
        """Return ``data/factors/<namespace>/``, creating it if needed."""
        path = self.root / "factors" / namespace
        path.mkdir(parents=True, exist_ok=True)
        return path

    def namespaced_artifact_dir(self, namespace: str, *parts: str) -> Path:
        """Return ``data/factors/<namespace>/<parts...>/``, creating it if needed.

        Generic helper for namespaced research artifacts (controller events,
        snapshots, JSON payloads). Does not invent a second catalog — paths stay
        under the existing factors root.
        """
        path = self.factor_namespace_dir(namespace)
        for part in parts:
            if not part or "/" in part or "\\" in part or part in {".", ".."}:
                raise ValueError(f"invalid artifact path segment: {part!r}")
            path = path / part
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ==================================================================
    # 4. Factor Test Results (scoped to namespace)
    # ==================================================================

    def save_factor_test(
        self,
        namespace: str,
        factor_id: str,
        n: int,
        g: int,
        ic_stat: dict,
        ic_series: pd.Series,
        group_return: pd.DataFrame,
        turnover: pd.DataFrame = None,
    ):
        """Save single factor test results for a namespace."""
        base = self.root / "factor_test" / namespace
        (base / "ic").mkdir(parents=True, exist_ok=True)
        (base / "group_return").mkdir(parents=True, exist_ok=True)

        ic_series.to_frame("ic").to_parquet(base / "ic" / f"{factor_id}__n{n}.parquet")
        group_return.to_parquet(base / "group_return" / f"{factor_id}__n{n}_g{g}.parquet")

        if turnover is not None:
            (base / "turnover").mkdir(parents=True, exist_ok=True)
            turnover.to_parquet(base / "turnover" / f"{factor_id}__n{n}_g{g}.parquet")

        self._append_factor_test_summary(namespace, factor_id, n, g, ic_stat, group_return)

    def _append_factor_test_summary(
        self,
        namespace: str,
        factor_id: str,
        n: int,
        g: int,
        ic_stat: dict,
        group_return: pd.DataFrame,
    ):
        """Append or update a row in the namespace's summary.parquet."""
        summary_path = self.root / "factor_test" / namespace / "summary.parquet"

        cum_returns = (1 + group_return).prod() - 1
        top_col = group_return.columns[-1]
        bot_col = group_return.columns[0]

        row = {
            "factor_id": factor_id,
            "n": n,
            "g": g,
            "IC_mean": ic_stat.get("IC_mean"),
            "IC_std": ic_stat.get("IC_std"),
            "IC_IR": ic_stat.get("IC_IR"),
            "IC_mean_last_1y": ic_stat.get("IC_mean_last_1y"),
            "IC_IR_LAST_1Y": ic_stat.get("IC_IR_LAST_1Y"),
            "IC_positive_ratio": ic_stat.get("IC_>0"),
            "IC_abs_gt_2pct": ic_stat.get("IC_ABS_>2%"),
            "t_stat": ic_stat.get("t_stat"),
            "p_value": ic_stat.get("p_value"),
            "IC_count": ic_stat.get("IC_count"),
            "top_group_cum_return": cum_returns.get(top_col),
            "bottom_group_cum_return": cum_returns.get(bot_col),
            "long_short_return": cum_returns.get(top_col, 0) - cum_returns.get(bot_col, 0),
            "tested_at": pd.Timestamp.now(),
        }
        new_row = pd.DataFrame([row])

        if summary_path.exists():
            existing = pd.read_parquet(summary_path)
            mask = ~(
                (existing["factor_id"] == factor_id) & (existing["n"] == n) & (existing["g"] == g)
            )
            existing = existing[mask]
            summary = pd.concat([existing, new_row], ignore_index=True)
        else:
            summary = new_row

        summary.to_parquet(summary_path, index=False)

    def read_factor_test_summary(self, namespace: str) -> pd.DataFrame:
        """Read the factor test summary for a namespace."""
        path = self.root / "factor_test" / namespace / "summary.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def read_ic_series(self, namespace: str, factor_id: str, n: int = 1) -> pd.Series:
        """Read IC time series for a factor in a namespace."""
        path = self.root / "factor_test" / namespace / "ic" / f"{factor_id}__n{n}.parquet"
        return pd.read_parquet(path)["ic"]

    def read_group_return(
        self, namespace: str, factor_id: str, n: int = 1, g: int = 5
    ) -> pd.DataFrame:
        """Read group return for a factor in a namespace."""
        path = (
            self.root
            / "factor_test"
            / namespace
            / "group_return"
            / f"{factor_id}__n{n}_g{g}.parquet"
        )
        return pd.read_parquet(path)

    # ==================================================================
    # 5. Factor Correlation (scoped to namespace)
    # ==================================================================

    def save_factor_correlation(
        self,
        namespace: str,
        pearson_df: pd.DataFrame = None,
        spearman_df: pd.DataFrame = None,
        date_min=None,
        date_max=None,
    ):
        """Save factor correlation matrices for a namespace."""
        out_dir = self.root / "correlation" / namespace
        out_dir.mkdir(parents=True, exist_ok=True)
        if pearson_df is not None:
            pearson_df.to_parquet(out_dir / "pearson.parquet")
        if spearman_df is not None:
            spearman_df.to_parquet(out_dir / "spearman.parquet")

    def read_factor_correlation(self, namespace: str, rank: bool = True) -> pd.DataFrame:
        """Read factor correlation matrix. rank=True for Spearman."""
        fname = "spearman.parquet" if rank else "pearson.parquet"
        path = self.root / "correlation" / namespace / fname
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    # ==================================================================
    # 6. Backtest Results (scoped to namespace)
    # ==================================================================

    def save_backtest_run(
        self,
        namespace: str,
        result_df: pd.DataFrame,
        weights_df: pd.DataFrame,
        metrics: dict,
        factor_configs: list = None,
        exit_filters: list = None,
        description: str = "",
        **extra_params,
    ) -> str:
        """
        Save a backtest run (scoped to namespace). Returns run_id.

        Parameters
        ----------
        namespace : str
        result_df : DataFrame with daily PnL (from Backtester.result_df)
        weights_df : DataFrame with daily weights (from Backtester.weights_df)
        metrics : dict with performance metrics (from Backtester.metrics)
        factor_configs : original factor config list (for logging)
        exit_filters : original exit filter list (for logging)
        description : free text
        **extra_params : top_pct, commission, slippage, delay etc.
        """
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.root / "backtest" / namespace
        (base / "runs").mkdir(parents=True, exist_ok=True)
        (base / "weights").mkdir(parents=True, exist_ok=True)

        result_df.to_parquet(base / "runs" / f"run_{run_id}.parquet")
        weights_df.to_parquet(base / "weights" / f"run_{run_id}.parquet")

        def _serialize_configs(configs):
            if configs is None:
                return "[]"
            out = []
            for c in configs:
                item = {
                    "name": c.get("name", c["func"].__name__),
                    "func": c["func"].__name__,
                    "kwargs": c.get("kwargs", {}),
                }
                out.append(item)
            return json.dumps(out)

        config_json = _serialize_configs(factor_configs)
        filter_json = _serialize_configs(exit_filters)

        self._append_backtest_summary(
            namespace, run_id, description, config_json, filter_json, metrics, extra_params
        )

        print(f"Backtest run saved: {namespace}/{run_id}")
        return run_id

    def _append_backtest_summary(
        self, namespace, run_id, description, config_json, filter_json, metrics, extra_params
    ):
        """Append to namespace's backtest summary.parquet."""
        summary_path = self.root / "backtest" / namespace / "summary.parquet"

        row = {
            "run_id": run_id,
            "description": description,
            "factor_config_json": config_json,
            "exit_filter_json": filter_json,
            "top_pct": extra_params.get("top_pct"),
            "commission": extra_params.get("commission"),
            "slippage": extra_params.get("slippage"),
            "delay": extra_params.get("delay"),
            "start_date": extra_params.get("start_date"),
            "end_date": extra_params.get("end_date"),
            "total_return": metrics.get("total_return"),
            "ann_return": metrics.get("ann_return"),
            "max_drawdown": metrics.get("max_drawdown"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "calmar_ratio": metrics.get("calmar_ratio"),
            "sortino_ratio": metrics.get("sortino_ratio"),
            "ann_volatility": metrics.get("ann_volatility"),
            "avg_daily_turnover": metrics.get("avg_daily_turnover"),
            "total_transaction_cost": metrics.get("total_transaction_cost"),
            "n_factors": extra_params.get("n_factors"),
            "n_exit_filters": extra_params.get("n_exit_filters"),
            "created_at": pd.Timestamp.now(),
        }
        new_row = pd.DataFrame([row])

        if summary_path.exists():
            existing = pd.read_parquet(summary_path)
            summary = pd.concat([existing, new_row], ignore_index=True)
        else:
            summary = new_row

        summary.to_parquet(summary_path, index=False)

    def read_backtest_summary(self, namespace: str) -> pd.DataFrame:
        """Read backtest summary for a namespace."""
        path = self.root / "backtest" / namespace / "summary.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def read_backtest_run(self, namespace: str, run_id: str) -> pd.DataFrame:
        """Read daily PnL for a specific backtest run."""
        path = self.root / "backtest" / namespace / "runs" / f"run_{run_id}.parquet"
        return pd.read_parquet(path)

    def read_backtest_weights(self, namespace: str, run_id: str) -> pd.DataFrame:
        """Read daily weights for a specific backtest run."""
        path = self.root / "backtest" / namespace / "weights" / f"run_{run_id}.parquet"
        return pd.read_parquet(path)

    # ==================================================================
    # 7. Freshness & Cache Management
    # ==================================================================

    def invalidate_namespace_cache(self, namespace: str):
        """Delete all cached factors/tests for a namespace (after inputs change)."""
        import shutil

        for sub in ["factors", "factor_test", "correlation"]:
            d = self.root / sub / namespace
            if d.exists():
                shutil.rmtree(d)
                print(f"  Removed {d}")
        print(f'Artifact cache invalidated for namespace "{namespace}"')

    # ==================================================================
    # 8. DuckDB Query Engine (lazy import, in-memory, no persistent file)
    # ==================================================================

    def query(self, sql: str, params: list = None) -> pd.DataFrame:
        """Run SQL over Parquet files using DuckDB as query engine.

        DuckDB is imported lazily — install via ``pip install duckdb`` or
        ``uv add --optional query``.  Each call creates a fresh in-memory
        connection (no persistent .duckdb file).

        The placeholder ``{data}`` in *sql* is replaced with the data root
        path, so you can write::

            dm.query(\"\"\"
                SELECT * FROM read_parquet('{data}/market/1d/*.parquet',
                                           filename=true, union_by_name=true)
                WHERE close > 100
            \"\"\")

        For cross-namespace factor screening::

            dm.query(\"\"\"
                SELECT *
                FROM read_parquet('{data}/factor_test/*/summary.parquet',
                                  filename=true, union_by_name=true)
                WHERE abs(IC_IR) > 0.3
                ORDER BY abs(IC_IR) DESC
            \"\"\")

        Parameters
        ----------
        sql : str
            SQL statement. ``{data}`` is replaced with ``self.root``.
        params : list, optional
            Positional parameters bound as ``$1, $2, ...`` in the SQL.

        Returns
        -------
        pd.DataFrame
        """
        try:
            import duckdb
        except ImportError as e:
            raise ImportError(
                "duckdb is required for query(). "
                "Install it with: uv add duckdb  (or: pip install duckdb)"
            ) from e

        resolved_sql = sql.replace("{data}", str(self.root))
        con = duckdb.connect()
        try:
            if params:
                return con.execute(resolved_sql, params).df()
            return con.sql(resolved_sql).df()
        finally:
            con.close()

    def query_market(self, sql_where: str = "", frequency: str = "1d") -> pd.DataFrame:
        """Convenience wrapper: query market Parquet files.

        Example::

            dm.query_market("WHERE symbol = 'SHSE.510300' AND eob >= '2024-01-01'")
            dm.query_market("", frequency="1m")

        The underlying glob is ``market/{frequency}/*.parquet`` with
        ``filename=true`` so a ``filename`` column is available for
        extracting the symbol from the file path.
        """
        glob = f"{self.root}/market/{frequency}/*.parquet"
        sql = f"""
            SELECT * FROM read_parquet('{glob}',
                                       filename=true, union_by_name=true)
            {sql_where}
        """
        return self.query(sql)

    def query_factor_tests(self, sql_where: str = "") -> pd.DataFrame:
        """Convenience wrapper: query all factor test summaries across namespaces.

        A ``filename`` column is included so you can extract the namespace.
        Example::

            dm.query_factor_tests("WHERE abs(IC_IR) > 0.3 ORDER BY abs(IC_IR) DESC")
        """
        glob = f"{self.root}/factor_test/*/summary.parquet"
        sql = f"""
            SELECT * FROM read_parquet('{glob}',
                                       filename=true, union_by_name=true)
            {sql_where}
        """
        return self.query(sql)

    def query_backtests(self, sql_where: str = "") -> pd.DataFrame:
        """Convenience wrapper: query all backtest summaries across namespaces.

        Example::

            dm.query_backtests("WHERE sharpe_ratio > 1.0 ORDER BY sharpe_ratio DESC")
        """
        glob = f"{self.root}/backtest/*/summary.parquet"
        sql = f"""
            SELECT * FROM read_parquet('{glob}',
                                       filename=true, union_by_name=true)
            {sql_where}
        """
        return self.query(sql)

    # ==================================================================
    # 9. Analytical Queries (pandas fallback, no DuckDB required)
    # ==================================================================

    def find_best_factors(self, namespace: str, min_ir: float = 0.3) -> pd.DataFrame:
        """Find factors with |IC_IR| > min_ir in a namespace."""
        summary = self.read_factor_test_summary(namespace)
        if summary.empty or "IC_IR" not in summary.columns:
            return pd.DataFrame(
                columns=["factor_id", "IC_mean", "IC_IR", "t_stat", "long_short_return"]
            )
        mask = summary["IC_IR"].abs() > min_ir
        result = summary.loc[
            mask, ["factor_id", "IC_mean", "IC_IR", "t_stat", "long_short_return"]
        ].copy()
        result = result.sort_values("IC_IR", key=lambda x: x.abs(), ascending=False)
        return result.reset_index(drop=True)

    def compare_factor_across_namespaces(self, factor_id: str) -> pd.DataFrame:
        """Compare a factor's performance across all namespaces."""
        ft_dir = self.root / "factor_test"
        if not ft_dir.exists():
            return pd.DataFrame(
                columns=["namespace", "IC_mean", "IC_IR", "t_stat", "long_short_return"]
            )
        rows = []
        for namespace_dir in sorted(ft_dir.iterdir()):
            if not namespace_dir.is_dir():
                continue
            summary_path = namespace_dir / "summary.parquet"
            if not summary_path.exists():
                continue
            summary = pd.read_parquet(summary_path)
            match = summary[summary["factor_id"] == factor_id]
            for _, r in match.iterrows():
                rows.append(
                    {
                        "namespace": namespace_dir.name,
                        "IC_mean": r.get("IC_mean"),
                        "IC_IR": r.get("IC_IR"),
                        "t_stat": r.get("t_stat"),
                        "long_short_return": r.get("long_short_return"),
                    }
                )
        result = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(
                columns=["namespace", "IC_mean", "IC_IR", "t_stat", "long_short_return"]
            )
        )
        return result.sort_values("IC_IR", key=lambda x: x.abs(), ascending=False).reset_index(
            drop=True
        )

    # ==================================================================
    # 10. Info / Status
    # ==================================================================

    def info(self):
        """Print a summary of the data store."""
        print(f"Data root: {self.root}")

        for freq in ["1d", "5m", "1m"]:
            syms = self.list_symbols(freq)
            if syms:
                print(f"  market/{freq}: {len(syms)} symbols")

        for sub in ["factors", "factor_test", "backtest"]:
            d = self.root / sub
            if d.exists():
                namespace_dirs = [p for p in d.iterdir() if p.is_dir()]
                if namespace_dirs:
                    print(f"  {sub}/:")
                    for namespace_dir in namespace_dirs:
                        n_files = len(list(namespace_dir.rglob("*.parquet")))
                        print(f"    {namespace_dir.name}: {n_files} files")
