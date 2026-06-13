"""Report skill: Jinja2-rendered HTML reports and matplotlib PNG charts."""

from skills.report import charts
from skills.report.renderer import ReportRenderer
from skills.report.strategy_markdown import (
    StrategyReport,
    write_strategy_index,
    write_strategy_report,
)

__all__ = [
    "ReportRenderer",
    "StrategyReport",
    "charts",
    "write_strategy_index",
    "write_strategy_report",
]
