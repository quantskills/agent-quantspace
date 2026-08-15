"""Jinja2 + matplotlib → HTML (and optionally PDF) report renderer.

Templates live alongside this file in ``templates/``. Charts are passed in as
PNG ``bytes`` and base64-encoded inline so reports are single-file artifacts.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from skills.store.workspace import resolve_workspace_paths

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_OUTPUT_DIR = resolve_workspace_paths().reports_root


def png_to_data_uri(png: bytes | None) -> str:
    """Encode PNG bytes as an ``<img src="..."/>``-ready data URI.

    Returns an empty string when ``png`` is falsy so templates can use
    ``{{ chart or '' }}`` without an extra conditional.
    """
    if not png:
        return ""
    b64 = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"


def relative_catalog_href(from_dir: str | Path, reports_root: str | Path) -> str:
    """POSIX href from ``from_dir`` to ``reports_root/catalog.html``.

    Study pages live at ``<namespace>/<slug>/``, so this is typically
    ``../../catalog.html``. Dashboard files saved at the reports root get
    ``catalog.html``. Windows backslashes are never used in the href.
    """
    catalog = Path(reports_root) / "catalog.html"
    relative = os.path.relpath(os.fspath(catalog), start=os.fspath(from_dir))
    return Path(relative).as_posix()


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
            loader=FileSystemLoader(os.fspath(self.template_dir)),
            autoescape=select_autoescape(["html"]),
        )
        self.env.filters["png_data_uri"] = png_to_data_uri

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a template file (with or without ``.html`` suffix) to HTML."""
        if not template_name.endswith(".html"):
            template_name = f"{template_name}.html"
        template = self.env.get_template(template_name)
        payload = {"catalog_href": "catalog.html", **context}
        return template.render(**payload)

    def save(self, html: str, output_path: str | Path) -> Path:
        """Write HTML to ``output_path``.

        Relative paths resolve against ``self.output_dir``. Parent directories
        are created automatically.
        """
        path = Path(output_path)
        if not path.is_absolute():
            path = self.output_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8", newline="\n")
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
        HTML(string=html).write_pdf(os.fspath(path))
        return path
