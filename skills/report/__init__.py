"""Report skill: Jinja2-rendered HTML reports and matplotlib PNG charts."""

from skills.report import charts
from skills.report.renderer import ReportRenderer
from skills.report.research_report import (
    ReportFigure,
    ReportTable,
    ResearchReport,
    list_research_studies,
    write_research_bundle,
    write_research_catalog,
)
from skills.report.strategy_markdown import (
    StrategyReport,
    write_strategy_index,
    write_strategy_report,
)

__all__ = [
    "ReportFigure",
    "ReportRenderer",
    "ReportTable",
    "ResearchReport",
    "StrategyReport",
    "charts",
    "list_research_studies",
    "write_research_bundle",
    "write_research_catalog",
    "write_strategy_index",
    "write_strategy_report",
]
