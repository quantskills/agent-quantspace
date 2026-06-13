"""Jinja2 + matplotlib → HTML (and optionally PDF) report renderer.

Templates live alongside this file in ``templates/``. Charts are passed in as
PNG ``bytes`` and base64-encoded inline so reports are single-file artifacts.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "reports"


def png_to_data_uri(png: bytes | None) -> str:
    """Encode PNG bytes as an ``<img src="..."/>``-ready data URI.

    Returns an empty string when ``png`` is falsy so templates can use
    ``{{ chart or '' }}`` without an extra conditional.
    """
    if not png:
        return ""
    b64 = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"


class ReportRenderer:
    """Render Jinja2 templates into HTML and save to ``reports/``.

    Parameters
    ----------
    template_dir : Path or str, optional
        Override the default template directory. Useful for tests that load
        templates from a temporary directory.
    output_dir : Path or str, optional
        Override the default output directory.
    """

    def __init__(
        self,
        template_dir: Path | str | None = None,
        output_dir: Path | str | None = None,
    ) -> None:
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
        except ImportError as exc:  # pragma: no cover — jinja2 is required
            raise ImportError(
                "ReportRenderer requires jinja2 — install with `uv pip install jinja2`"
            ) from exc

        self.template_dir = Path(template_dir) if template_dir else TEMPLATE_DIR
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html"]),
        )
        self.env.filters["png_data_uri"] = png_to_data_uri

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a template file (with or without ``.html`` suffix) to HTML."""
        if not template_name.endswith(".html"):
            template_name = f"{template_name}.html"
        template = self.env.get_template(template_name)
        return template.render(**context)

    def save(self, html: str, output_path: str | Path) -> Path:
        """Write HTML to ``output_path``.

        Relative paths resolve against ``self.output_dir``. Parent directories
        are created automatically.
        """
        path = Path(output_path)
        if not path.is_absolute():
            path = self.output_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path

    def to_pdf(self, html: str, output_path: str | Path) -> Path:
        """Convert HTML to PDF via ``weasyprint`` (optional dependency)."""
        try:
            from weasyprint import HTML
        except ImportError as exc:  # pragma: no cover — optional dep
            raise ImportError(
                "to_pdf() requires weasyprint — install with `uv pip install weasyprint`"
            ) from exc

        path = Path(output_path)
        if not path.is_absolute():
            path = self.output_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=html).write_pdf(str(path))
        return path
