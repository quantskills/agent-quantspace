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

Symbols
-------
Symbols are PandaData platform codes (``510300.SH``, ``RB2701.SHF``,
``RB_DOMINANT.SHF``) in both directions: inputs go to the SDK unchanged and
returned ``symbol`` columns are kept as PandaData returns them.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

_SymbolLike = str | list[str] | None
_StringLike = str | list[str] | None
_IntLike = int | list[int] | None

# Dedicated PandaData endpoints by asset class and price adjustment, as listed at
# https://www.pandaaiquant.com/docs/api. The older ``get_market_data`` and
# ``get_market_min_data`` are not documented there and futures requests through them
# fail with error 200103 even on accounts that hold the futures data permission.
DAILY_ENDPOINTS: dict[str, dict[str, str]] = {
    "stock": {
        "none": "get_stock_daily",
        "pre": "get_stock_daily_pre",
        "post": "get_stock_daily_post",
    },
    "index": {"none": "get_index_daily"},
    "future": {"none": "get_future_daily"},
}
MINUTE_ENDPOINTS: dict[str, dict[str, str]] = {
    "stock": {
        "none": "get_stock_min",
        "pre": "get_stock_min_pre",
        "post": "get_stock_min_post",
    },
    "index": {"none": "get_index_min"},
    "future": {"none": "get_future_min"},
    "fund": {"none": "get_fund_min"},
}
MINUTE_FREQUENCIES = ("1m", "5m", "15m", "60m")


def _endpoint(table: dict[str, dict[str, str]], asset: str, adjust: str, kind: str) -> str:
    if asset not in table:
        raise ValueError(f"PandaData has no {kind} bars for asset {asset!r}")
    methods = table[asset]
    if adjust not in methods:
        raise ValueError(f"{kind} {asset} bars support adjust in {sorted(methods)}, not {adjust!r}")
    return methods[adjust]


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


class PandaDataClient:
    """panda_data market data client.

    Parameters
    ----------
    username : str, optional
        panda_data account (``86`` + phone). Falls back to
        ``PANDA_DATA_USERNAME`` env var.
    password : str, optional
        Site password. Falls back to ``PANDA_DATA_PASSWORD`` env var.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
    ):
        _load_dotenv_if_present()
        self._username = username or os.environ.get("PANDA_DATA_USERNAME", "")
        self._password = password or os.environ.get("PANDA_DATA_PASSWORD", "")
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

    def _call(self, method_name: str, **kwargs: Any) -> pd.DataFrame:
        """Common call path: ensure auth, then invoke the SDK."""
        self._ensure_token()
        return getattr(self._sdk(), method_name)(**kwargs)

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
        adjust: str = "none",
    ) -> pd.DataFrame:
        """Fetch daily bars from the dedicated endpoint for ``type``.

        ``stock`` calls ``get_stock_daily`` (``adjust="pre"`` / ``"post"`` call
        ``get_stock_daily_pre`` / ``get_stock_daily_post``); ``index`` calls
        ``get_index_daily``; ``future`` calls ``get_future_daily``, which also
        returns ``settlement`` and ``pre_settlement``. Funds use
        :meth:`get_fund_daily`; HK and US stocks use :meth:`fetch_hk_daily` and
        :meth:`fetch_us_daily`.

        Parameters
        ----------
        symbol : str or list of str, optional
            PandaData code(s) such as ``600000.SH``, ``000300.SH`` or
            ``RB_DOMINANT.SHF``.
        start_date, end_date : str
            ``YYYYMMDD``; span capped at 5 years by PandaData.
        type : {"stock", "index", "future"}, default "stock"
        fields : list of str, optional
            Subset of response columns to keep. ``None`` returns all.
        indicator : str, optional
            Stock pool index code such as ``000300``; stock only.
        st : bool, default True
            Whether to include ST stocks; stock only.
        adjust : {"none", "pre", "post"}, default "none"
            Price adjustment; stock only.

        Returns
        -------
        pandas.DataFrame
            Native PandaData schema, including PandaData ``symbol`` codes.
        """
        method = _endpoint(DAILY_ENDPOINTS, type, adjust, "daily")
        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "fields": fields or [],
        }
        if type == "stock":
            kwargs.update(indicator=indicator or "", st=st)
        elif indicator or not st:
            raise ValueError("indicator and st apply only to stock daily bars")
        return self._call(method, **kwargs)

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
        adjust: str = "none",
    ) -> pd.DataFrame:
        """Fetch minute bars from the dedicated endpoint for ``symbol_type``.

        ``stock`` calls ``get_stock_min`` (``adjust="pre"`` / ``"post"`` call
        ``get_stock_min_pre`` / ``get_stock_min_post``); ``index`` calls
        ``get_index_min`` (1m only); ``future`` calls ``get_future_min``;
        ``fund`` (listed ETFs) calls ``get_fund_min``. ``frequency`` is one of
        ``1m``, ``5m``, ``15m``, ``60m``. PandaData caps the rows of one minute
        request and publishes minute bars once a day after the close, so they
        are not an intraday feed.
        """
        method = _endpoint(MINUTE_ENDPOINTS, symbol_type, adjust, "minute")
        if frequency not in MINUTE_FREQUENCIES:
            raise ValueError(f"frequency must be one of {MINUTE_FREQUENCIES}, not {frequency!r}")
        if symbol_type == "index" and frequency != "1m":
            raise ValueError("index minute bars support only 1m")
        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "fields": fields or [],
            "frequency": frequency,
        }
        if time_zone is not None:
            kwargs["time_zone"] = time_zone
        return self._call(method, **kwargs)

    def get_future_detail(
        self,
        symbol: _SymbolLike = None,
        *,
        fields: list[str] | None = None,
        exchange: str | None = None,
        date: str | None = None,
    ) -> pd.DataFrame:
        """Futures contract details via ``panda_data.get_future_detail``.

        Includes ``contract_multiplier``, ``trading_hours`` (bar-end times such
        as ``21:01-23:00,09:01-10:15,10:31-11:30,13:31-15:00``), ``market_tplus``
        and ``margin_rate``.
        """
        kwargs: dict[str, Any] = {"symbol": symbol or "", "fields": fields or []}
        if exchange:
            kwargs["exchange"] = exchange
        if date:
            kwargs["date"] = date
        return self._call("get_future_detail", **kwargs)

    def get_future_daily_post(
        self,
        start_date: str,
        end_date: str,
        *,
        underlying_symbol: _StringLike = None,
        method: str = "close_pcs",
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        """Backward-adjusted dominant-continuous futures daily bars.

        Calls ``panda_data.get_future_daily_post``. ``underlying_symbol`` is a
        product code such as ``"RB"`` or ``["RB", "IF"]``; rows come back as the
        dominant-continuous ``symbol`` (``RB_DOMINANT.SHF``) with the actual
        contract in ``dominant_id``. ``method`` is one of ``close_pcs``,
        ``close_os``, ``close_pcr``, ``close_or``.
        """
        return self._call(
            "get_future_daily_post",
            underlying_symbol=underlying_symbol or "",
            start_date=start_date,
            end_date=end_date,
            method=method,
            fields=fields or [],
        )

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
            symbol=symbol or [],
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
            symbol=symbol or [],
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    # ------------------------------------------------------------------
    # Listed funds and ETFs
    # ------------------------------------------------------------------

    def get_fund_detail(
        self,
        symbol: _SymbolLike = None,
        *,
        exchange: _StringLike = None,
        type: _StringLike = None,
        operation_mode: _StringLike = None,
        etf_lof_type: _StringLike = None,
        is_class_fund: _IntLike = None,
        index_fund_type: _StringLike = None,
        status: _StringLike = None,
        fund_status: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """Fund metadata via ``panda_data.get_fund_detail``.

        Use ``etf_lof_type="ETF"`` to discover listed ETFs. Both listed-fund
        symbols (for example ``510300.SH``) and off-exchange ``*.OF`` symbols
        are accepted.
        """
        return self._call(
            "get_fund_detail",
            symbol=symbol,
            exchange=exchange,
            type=type,
            operation_mode=operation_mode,
            etf_lof_type=etf_lof_type,
            is_class_fund=is_class_fund,
            index_fund_type=index_fund_type,
            status=status,
            fund_status=fund_status,
            fields=fields,
        )

    def get_fund_daily(
        self,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike = None,
        exchange: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """Unadjusted listed-fund daily bars, chunked to PandaData's 1-year cap."""
        return self._call_fund_daily_range(
            "get_fund_daily",
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    def get_fund_daily_pre(
        self,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike = None,
        exchange: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """Forward-adjusted listed-fund bars, chunked to PandaData's 1-year cap."""
        return self._call_fund_daily_range(
            "get_fund_daily_pre",
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    def get_fund_daily_post(
        self,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike = None,
        exchange: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """Backward-adjusted listed-fund bars, chunked to PandaData's 1-year cap."""
        return self._call_fund_daily_range(
            "get_fund_daily_post",
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    def get_fund_etf_cr_limits(
        self,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike = None,
        exchange: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """ETF creation/redemption limits via ``get_fund_etf_cr_limits``."""
        return self._call_fund_range(
            "get_fund_etf_cr_limits",
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    def get_fund_etf_cr_net(
        self,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike = None,
        exchange: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """ETF net creation/redemption data via ``get_fund_etf_cr_net``."""
        return self._call_fund_range(
            "get_fund_etf_cr_net",
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    def get_fund_etf_constituents(
        self,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike = None,
        exchange: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """ETF creation/redemption basket via ``get_fund_etf_constituents``."""
        return self._call_fund_range(
            "get_fund_etf_constituents",
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    def get_fund_etf_cr(
        self,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike = None,
        exchange: _StringLike = None,
        fields: _StringLike = None,
    ) -> pd.DataFrame:
        """ETF creation/redemption list via ``panda_data.get_fund_etf_cr``."""
        return self._call_fund_range(
            "get_fund_etf_cr",
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    def _call_fund_range(
        self,
        method_name: str,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike,
        exchange: _StringLike,
        fields: _StringLike,
    ) -> pd.DataFrame:
        """Call one PandaData fund endpoint with the shared date-range schema."""
        return self._call(
            method_name,
            start_date=start_date,
            end_date=end_date,
            symbol=symbol,
            exchange=exchange,
            fields=fields,
        )

    @staticmethod
    def _parse_yyyymmdd(value: str, *, name: str) -> date:
        """Validate and parse a PandaData ``YYYYMMDD`` date argument."""
        if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
            raise ValueError(f"{name} must be a YYYYMMDD string")
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError(f"{name} must be a valid YYYYMMDD date") from exc

    def _fund_daily_chunks(self, start_date: str, end_date: str) -> list[tuple[str, str]]:
        """Return contiguous fund-bar requests of at most 365 inclusive days."""
        start = self._parse_yyyymmdd(start_date, name="start_date")
        end = self._parse_yyyymmdd(end_date, name="end_date")
        if start > end:
            raise ValueError("start_date must be before or equal to end_date")

        chunks: list[tuple[str, str]] = []
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=364), end)
            chunks.append((current.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
            current = chunk_end + timedelta(days=1)
        return chunks

    def _call_fund_daily_range(
        self,
        method_name: str,
        start_date: str,
        end_date: str,
        *,
        symbol: _SymbolLike,
        exchange: _StringLike,
        fields: _StringLike,
    ) -> pd.DataFrame:
        """Fetch a fund daily endpoint in safe chunks and combine its raw frames."""
        chunks = self._fund_daily_chunks(start_date, end_date)
        frames: list[pd.DataFrame] = []
        for chunk_start, chunk_end in chunks:
            try:
                frames.append(
                    self._call_fund_range(
                        method_name,
                        chunk_start,
                        chunk_end,
                        symbol=symbol,
                        exchange=exchange,
                        fields=fields,
                    )
                )
            except Exception as exc:
                raise RuntimeError(
                    f"{method_name} failed for date range {chunk_start} to {chunk_end}"
                ) from exc

        if len(frames) == 1:
            return frames[0]
        return pd.concat(frames, ignore_index=True)

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
            symbol=symbol or "",
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
            symbol=symbol or "",
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
            symbol=symbol or "",
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
            index_symbol=index_symbol or "",
            stock_symbol=stock_symbol or "",
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
            stock_symbol=stock_symbol or None,
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
            stock_symbol=stock_symbol,
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
            concept_stock=concept_stock or None,
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
            Stock code(s) in PandaData format, such as ``600000.SH``.
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
            symbol=symbol or "",
            start_date=start_date,
            end_date=end_date,
            fields=fields or [],
        )

    def get_trade_cal(
        self, start_date: str, end_date: str, *, exchange: str = "SH"
    ) -> pd.DataFrame:
        """Trading calendar via ``panda_data.get_trade_cal`` (``YYYYMMDD`` bounds).

        One row per natural date: ``nature_date``, ``is_trade`` (1 = trading day),
        ``pretrade_date``, ``next_trade_date``. ``exchange`` is ``SH``, ``HK``, or ``US``.
        """
        return self._call(
            "get_trade_cal",
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
            is_trading_day=None,
            fields=[],
        )

    def __repr__(self) -> str:
        flag = "authed" if self._token_ready else "unauthed"
        return f"PandaDataClient(user={self._username or '<env>'!s}, {flag})"
