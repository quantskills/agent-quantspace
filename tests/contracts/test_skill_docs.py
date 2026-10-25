"""Generated qs command references in SKILL.md stay in sync with the registered models."""

from __future__ import annotations

from pathlib import Path

from skills.cli.docs import BEGIN, END, render_docs
from skills.cli.registry import SKILLS, get_commands

ROOT = Path(__file__).resolve().parents[2]


def test_generated_command_references_have_no_drift():
    result = render_docs(get_commands(), check=True)
    assert result.data["changed"] == [], "run `uv run qs docs render`"
    assert result.exit_code == 0


def test_every_skill_document_has_exactly_one_generated_block():
    for skill in SKILLS:
        text = (ROOT / "skills" / skill.replace("-", "_") / "SKILL.md").read_text(encoding="utf-8")
        assert text.count(BEGIN) == 1 and text.count(END) == 1, skill
        assert text.index(BEGIN) < text.index(END), skill


def test_agents_document_points_agents_to_the_cli():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "uv run qs catalog" in text
    assert "uv run qs docs render" in text
