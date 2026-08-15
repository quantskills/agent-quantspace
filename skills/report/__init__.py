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

__all__ = [
    "ReportFigure",
    "ReportRenderer",
    "ReportTable",
    "ResearchReport",
    "charts",
    "list_research_studies",
    "write_research_bundle",
    "write_research_catalog",
]
