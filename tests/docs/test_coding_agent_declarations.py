from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_AGENTS = (
    "Codex",
    "Claude Code",
    "Cursor",
    "CodeBuddy",
    "Qoder",
    "TRAE",
    "OpenCode",
    "OpenClaw",
    "Kimi Code",
)


def _platforms_from_agents_md(text: str) -> list[str]:
    match = re.search(r"platforms:\s*\[([^\]]+)\]", text)
    assert match is not None
    return [item.strip().strip("'\"") for item in match.group(1).split(",")]


def test_readme_agents_platform_declarations_are_aligned() -> None:
    readme_zh = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    for name in EXPECTED_AGENTS:
        assert name in readme_zh or (
            name == "Codex" and "ChatGPT Codex" in readme_zh
        ), name
        assert name in readme_en or (
            name == "Codex" and "ChatGPT Codex" in readme_en
        ), name
        assert name in agents or name.lower().replace(" ", "-") in agents.lower(), name

    platforms = _platforms_from_agents_md(agents)
    assert platforms == [
        "codex",
        "claude-code",
        "cursor",
        "codebuddy",
        "qoder",
        "trae",
        "opencode",
        "openclaw",
        "kimi-code",
    ]

    assert "factor_mining" in readme_zh
    assert "factor_mining" in readme_en
    assert "factor_mining" in agents
    assert "capability discovery" in agents.lower() or "能力发现" in agents
