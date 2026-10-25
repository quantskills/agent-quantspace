"""Transport contracts shared by Skill command adapters."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class CLIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    _transport_preview: int = PrivateAttr(default=5)
    _transport_log_level: str = PrivateAttr(default="WARNING")

    @property
    def preview(self) -> int:
        return self._transport_preview

    @property
    def log_level(self) -> str:
        return self._transport_log_level


class OutputOptions(CLIModel):
    output: Path | None = Field(
        None, description="Explicit output path outside managed store namespaces."
    )
    overwrite: bool = Field(False, description="Allow replacing an existing output artifact.")
    data_root: Path | None = Field(
        None, description="Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/."
    )


class PanelSource(CLIModel):
    panel: Path | None = Field(
        None, description="Parquet/CSV panel, mutually exclusive with symbols or symbols-file."
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="QuantSpace symbols such as SHSE.510300; repeat flag or comma-separate.",
    )
    symbols_file: Path | None = Field(
        None, description="Text lines or JSON list of QuantSpace symbols."
    )
    frequency: str = Field(
        "1d", description="Market store directory under data/market, for example 1d or 1d_adj."
    )
    data_root: Path | None = Field(
        None, description="Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/."
    )
    start: str | None = Field(None, description="Inclusive start date: YYYY-MM-DD or YYYYMMDD.")
    end: str | None = Field(None, description="Inclusive end date: YYYY-MM-DD or YYYYMMDD.")
    fields: list[str] = Field(default_factory=list, description="Optional panel field subset.")


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Artifact role.")
    path: str = Field(description="Absolute output path.")
    format: str = Field(description="File format.")
    rows: int | None = Field(None, description="Table row count, if applicable.")
    columns: list[str] = Field(default_factory=list, description="Table value columns.")


class CommandResult(BaseModel):
    data: Any = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    exit_code: int = 0


class CLIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        exit_code: int = 2,
        details: list | None = None,
        hint: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = details or []
        self.hint = hint
