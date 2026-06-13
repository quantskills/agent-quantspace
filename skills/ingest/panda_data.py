"""PandaData market data client.

Thin wrapper around the ``panda_data`` SDK. Fetch-only; no local persistence.
Callers decide whether to save returned DataFrames via
``skills.store.data_manager.DataManager``.

Prerequisites
-------------
- ``panda_data`` package installed (``uv sync --extra panda_data``).
- Environment variables ``PANDA_DATA_USERNAME`` and ``PANDA_DATA_PASSWORD``
  set in ``.env`` (account = 86 + phone number, password = panda_data site
  password).

Symbol Handling
---------------
By default (``auto_convert_symbols=True``) input symbols may be in either
QuantSpace format (``SHSE.510300``) or panda_data native format
(``510300.SH``); unknown prefixes pass through unchanged. For DataFrames
returned from panda_data, any ``symbol`` column is converted back to
QuantSpace format so downstream code (``DataManager``, factor pipelines)
sees a consistent namespace.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from skills.ingest.symbol_map import try_to_panda_data_symbol, try_to_quantspace_symbol

_SymbolLike = str | list[str] | None


def _load_dotenv_if_present(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from .env without overwriting environment."""
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_first(*names: str) -> str:
    """Return the first non-empty environment variable value."""
    for name in names:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


class PandaDataClient:
    """panda_data market data client.

    Parameters
    ----------
    username : str, optional
        panda_data account (``86`` + phone). Falls back to
        ``PANDA_DATA_USERNAME`` env var.
    password : str, optional
        Site password. Falls back to ``PANDA_DATA_PASSWORD`` env var.
    auto_convert_symbols : bool, default True
        If True, input symbols are best-effort converted to panda_data
        native format before the API call, and any ``symbol`` column in
        the returned DataFrame is converted back to QuantSpace format.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        auto_convert_symbols: bool = True,
    ):
        _load_dotenv_if_present()
        self._username = username or _env_first("PANDA_DATA_USERNAME", "PANDAAI_USERNAME")
        self._password = password or _env_first("PANDA_DATA_PASSWORD", "PANDAAI_PASSWORD")
        self.auto_convert_symbols = auto_convert_symbols
        self._token_ready = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sdk(self):
        """Import and return the ``panda_data`` module.

        Raised errors guide the user toward the correct install path.
        """
        try:
            import panda_data  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError(
                "panda_data is not installed. Run `uv sync --extra panda_data` "
                "or `pip install panda_data`."
            ) from e
        return panda_data

    def _ensure_token(self) -> None:
        """Authenticate with panda_data once per client instance."""
        if self._token_ready:
            return
        if not self._username or not self._password:
            raise RuntimeError(
                "PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD not set; see .env.example."
            )
        self._sdk().init_token(username=self._username, password=self._password)
        self._token_ready = True

    def _to_pd(self, symbol: _SymbolLike) -> _SymbolLike:
        """Convert input symbol(s) to panda_data native format if enabled."""
        if not self.auto_convert_symbols or symbol is None:
            return symbol
        if isinstance(symbol, str):
            return try_to_panda_data_symbol(symbol)
        if isinstance(symbol, Iterable):
            return [try_to_panda_data_symbol(s) for s in symbol]
        return symbol

    def _from_pd_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert the ``symbol`` column of a returned frame to QS format."""
        if not self.auto_convert_symbols or df is None or len(df) == 0:
            return df
        if isinstance(df, pd.DataFrame) and "symbol" in df.columns:
            df = df.copy()
            df["symbol"] = df["symbol"].map(try_to_quantspace_symbol)
        return df

    def _call(self, method_name: str, **kwargs: Any) -> pd.DataFrame:
        """Common call path: ensure auth, invoke SDK, post-process symbols."""
        self._ensure_token()
        fn = getattr(self._sdk(), method_name)
        result = fn(**kwargs)
        if isinstance(result, pd.DataFrame):
            return self._from_pd_frame(result)
        return result

    # ------------------------------------------------------------------
    # Market bars
    # ------------------------------------------------------------------

    def fetch_market_data(
        self,
        symbol: _SymbolLike,
        start_date: str,
        end_date: str,
        *,
        type: str = "stock",
        fields: list[str] | None = None,
        indicator: str | None = None,
        st: bool = True,
    ) -> pd.DataFrame:
        """Fetch daily bars via ``panda_data.get_market_data``.

        Parameters
        ----------
        symbol : str or list of str, optional
            Stock / index / future code(s). Accepts QuantSpace or panda_data
            native format when ``auto_convert_symbols`` is True.
        start_date, end_date : str
            ``YYYYMMDD``; span capped at 5 years by panda_data.
        type : {"stock", "index", "future"}, default "stock"
        fields : list of str, optional
            Subset of response columns to keep. ``None`` returns all.
        indicator : str, optional
            Stock pool index code (see panda_data docs); only relevant for
            ``type="stock"``.
        st : bool, default True
            Whether to include ST stocks (stock type only).

        Returns
        -------
        pandas.DataFrame
            Native panda_data schema; ``symbol`` column converted back to
            QuantSpace format when auto-convert is on.
        """
        return self._call(
            "get_market_data",
            symbol=self._to_pd(symbol),
            start_date=start_date,
            end_date=end_date,
            type=type,
            fields=fields or [],
            indicator=indicator or "",
            st=st,
        )

    def fetch_market_min_data(
        self,
        symbol: _SymbolLike,
        start_date: str,
        end_date: str,
        *,
        symbol_type: str = "stock",
        fields: list[str] | None = None,
        time_zone: tuple[str, str] | None = None,
        frequency: str = "1m",
    ) -> pd.DataFrame:
        """Fetch minute bars via ``panda_data.get_market_min_data``.

        See panda_data docs for per-frequency span limits. ``frequency`` is
        one of ``{"1m", "5m", "15m", "60m"}`` (index supports only 1m).
        """
        kwargs: dict[str, Any] = {
            "symbol": self._to_pd(symbol),
            "start_date": start_date,
            "end_date": end_date,
            "symbol_type": symbol_type,
            "fields": fields or [],
            "frequency": frequency,
        }
        if time_zone is not None:
            kwargs["time_zone"] = time_zone
        return self._call("get_market_min_data", **kwargs)

    def fetch_hk_daily(
        self,
        symbol: _SymbolLike,
        start_date: str,
        end_date: str,
        *,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch HK daily bars via ``panda_data.get_hk_daily``."""
        return self._call(
            "get_hk_daily",
            symbol=self._to_pd(symbol) if symbol else [],
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    def fetch_us_daily(
        self,
        symbol: _SymbolLike,
        start_date: str,
        end_date: str,
        *,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch US (NASDAQ basic) daily bars via ``panda_data.get_us_daily``."""
        return self._call(
            "get_us_daily",
            symbol=self._to_pd(symbol) if symbol else [],
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    # ------------------------------------------------------------------
    # Reference data (metadata)
    # ------------------------------------------------------------------

    def get_stock_detail(
        self,
        symbol: _SymbolLike = "",
        *,
        fields: list[str] | None = None,
        market: str = "cn",
        status: int | None = None,
    ) -> pd.DataFrame:
        """Stock basic info via ``panda_data.get_stock_detail``."""
        return self._call(
            "get_stock_detail",
            symbol=self._to_pd(symbol) if symbol else "",
            fields=fields or [""],
            market=market,
            status=status,
        )

    def get_index_detail(
        self,
        symbol: _SymbolLike = "",
        *,
        status: int | None = None,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Index basic info via ``panda_data.get_index_detail``."""
        return self._call(
            "get_index_detail",
            symbol=self._to_pd(symbol) if symbol else "",
            status=status,
            fields=fields or [],
        )

    def get_index_indicator(
        self,
        symbol: _SymbolLike = "",
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Index valuation indicators via ``panda_data.get_index_indicator``."""
        return self._call(
            "get_index_indicator",
            symbol=self._to_pd(symbol) if symbol else "",
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    def get_index_weights(
        self,
        start_date: str,
        end_date: str,
        *,
        index_symbol: _SymbolLike = "",
        stock_symbol: _SymbolLike = "",
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Index weights via ``panda_data.get_index_weights``.

        ``start_date`` / ``end_date`` are required by panda_data.
        """
        return self._call(
            "get_index_weights",
            index_symbol=self._to_pd(index_symbol) if index_symbol else "",
            stock_symbol=self._to_pd(stock_symbol) if stock_symbol else "",
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    def get_industry_detail(
        self,
        *,
        level: str | list[str] | None = None,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Industry taxonomy via ``panda_data.get_industry_detail``."""
        return self._call(
            "get_industry_detail",
            level=level,
            fields=fields or [],
        )

    def get_industry_constituents(
        self,
        *,
        industry_code: str | list[str] | None = None,
        stock_symbol: _SymbolLike = None,
        level: str | None = None,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Industry constituents via ``panda_data.get_industry_constituents``."""
        return self._call(
            "get_industry_constituents",
            industry_code=industry_code,
            stock_symbol=self._to_pd(stock_symbol) if stock_symbol else None,
            level=level,
            fields=fields or [],
        )

    def get_stock_industry(
        self,
        stock_symbol: str,
        *,
        level: str | None = None,
    ) -> pd.DataFrame:
        """Industry classification for one stock via ``panda_data.get_stock_industry``."""
        return self._call(
            "get_stock_industry",
            stock_symbol=self._to_pd(stock_symbol)
            if isinstance(stock_symbol, str)
            else stock_symbol,
            level=level,
        )

    def get_concept_list(
        self,
        *,
        concept: str | list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """Concept list via ``panda_data.get_concept_list``."""
        return self._call(
            "get_concept_list",
            concept=concept,
            start_date=start_date,
            end_date=end_date,
        )

    def get_concept_constituents(
        self,
        *,
        concept: str | list[str] | None = None,
        concept_stock: _SymbolLike = None,
        start_date: str | None = None,
        end_date: str | None = None,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Concept constituents via ``panda_data.get_concept_constituents``."""
        return self._call(
            "get_concept_constituents",
            concept=concept,
            concept_stock=self._to_pd(concept_stock) if concept_stock else None,
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    def get_adj_factor(
        self,
        symbol: _SymbolLike = "",
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Stock adjustment factors via ``panda_data.get_adj_factor``.

        Parameters
        ----------
        symbol : str or list of str, optional
            Stock code(s). Accepts QuantSpace or panda_data native format.
            Empty string queries all stocks in the range.
        start_date, end_date : str, optional
            ``YYYYMMDD``.
        fields : list of str, optional
            Subset of response columns to keep.

        Returns
        -------
        pandas.DataFrame
            One row per corporate-action event: ``symbol``, ``ex_date``,
            ``ex_cum_factor``, ``ex_factor``, ``ex_end_date``,
            ``announcement_date``.
        """
        return self._call(
            "get_adj_factor",
            symbol=self._to_pd(symbol) if symbol else "",
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    def __repr__(self) -> str:
        flag = "authed" if self._token_ready else "unauthed"
        return f"PandaDataClient(user={self._username or '<env>'!s}, {flag})"
