"""What a minute-level live strategy declares: instruments, bar interval, warm-up, timing."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .clock import INTRADAY_MINUTES
from .contracts import is_futures_symbol
from .ledger import validate_strategy_id

Asset = Literal["stock", "fund", "future"]


class Instrument(BaseModel):
    """One traded symbol in PandaData code; futures may be continuous (``RB_DOMINANT.SHF``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str = Field(description="PandaData code such as 000001.SZ, 510300.SH, RB2701.SHF.")
    asset: Asset = Field(description="stock, fund (listed ETF or LOF) or future.")

    @model_validator(mode="after")
    def _matches_code(self) -> Instrument:
        if (self.asset == "future") != is_futures_symbol(self.symbol):
            raise ValueError(f"{self.symbol} is not a {self.asset} code")
        return self

    @property
    def continuous(self) -> bool:
        return self.asset == "future" and "_" in self.symbol.partition(".")[0]


class LiveSpec(BaseModel):
    """A minute-level live strategy.

    History comes from PandaData and today's bars from AKShare (Sina). ``warmup_bars`` is
    how many bars the strategy needs to compute the newest target; the live store keeps
    that many plus ``spare_days`` trading days. A bar is used ``bar_delay_seconds`` after it
    ends, because Sina keeps revising a bar for some seconds after it closes, and is given up
    ``deadline_seconds`` after it ends. The deadline defaults to one bar plus the delay, the
    moment the next bar becomes ready, so a late bar never holds up the next one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    strategy_id: str
    frequency: Literal["1m", "5m", "15m", "30m", "60m"]
    instruments: tuple[Instrument, ...] = Field(min_length=1)
    warmup_bars: int = Field(ge=1)
    adjust: Literal["none", "post"] = Field(
        "post", description="Price series for signals of stocks and funds; futures never adjust."
    )
    bar_delay_seconds: int = Field(40, ge=0, le=600)
    deadline_seconds: int | None = Field(None, gt=0)
    spare_days: int = Field(2, ge=0, le=20)
    intraday_source: Literal["akshare"] = "akshare"

    @field_validator("strategy_id")
    @classmethod
    def _strategy(cls, value: str) -> str:
        return validate_strategy_id(value)

    @model_validator(mode="after")
    def _one_session_family(self) -> LiveSpec:
        symbols = [item.symbol for item in self.instruments]
        if len(symbols) != len(set(symbols)):
            raise ValueError("each symbol may appear once")
        families = {item.asset == "future" for item in self.instruments}
        if len(families) > 1:
            raise ValueError("a minute strategy trades either futures or stocks and funds")
        if self.deadline <= self.bar_delay_seconds:
            raise ValueError("deadline_seconds must be greater than bar_delay_seconds")
        return self

    @property
    def deadline(self) -> int:
        return self.deadline_seconds or self.bar_seconds + self.bar_delay_seconds

    @property
    def bar_seconds(self) -> int:
        return INTRADAY_MINUTES[self.frequency] * 60

    @property
    def symbols(self) -> list[str]:
        return [item.symbol for item in self.instruments]

    @property
    def futures(self) -> bool:
        return self.instruments[0].asset == "future"


__all__ = ["Asset", "Instrument", "LiveSpec"]
