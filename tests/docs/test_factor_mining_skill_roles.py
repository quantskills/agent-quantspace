from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/factor_mining/SKILL.md"

REQUIRED_FIELDS = (
    "role_id",
    "purpose",
    "spawn_when",
    "do_not_spawn_when",
    "task_template",
    "required_inputs",
    "allowed_tools",
    "forbidden_actions",
    "output_contract",
    "stop_conditions",
    "handoff_to",
)

def _parse_roles(text: str) -> list[dict[str, str]]:
    blocks = re.findall(
        r"### Role:.*?\n\n```text\n(.*?)```",
        text,
        flags=re.DOTALL,
    )
    roles: list[dict[str, str]] = []
    for block in blocks:
        role: dict[str, str] = {}
        current_key: str | None = None
        current_lines: list[str] = []
        for line in block.splitlines():
            if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
                key, _, value = line.partition(":")
                key = key.strip()
                if key in REQUIRED_FIELDS:
                    if current_key is not None:
                        role[current_key] = "\n".join(current_lines).strip()
                    current_key = key
                    current_lines = [value.strip()] if value.strip() else []
                    if value.strip() == "|":
                        current_lines = []
                    continue
            if current_key is not None:
                current_lines.append(line.rstrip())
        if current_key is not None:
            role[current_key] = "\n".join(current_lines).strip()
        roles.append(role)
    return roles


def test_skill_defines_exactly_eight_unique_roles() -> None:
    roles = _parse_roles(SKILL.read_text(encoding="utf-8"))
    assert len(roles) == 8
    role_ids = [role["role_id"] for role in roles]
    assert len(set(role_ids)) == 8
    assert Counter(role["output_contract"] for role in roles) == {
        "ResearchDecision": 1,
        "FactorSpec": 4,
        "ReviewReport": 2,
        "PoolDecision": 1,
    }
    for role in roles:
        for field in REQUIRED_FIELDS:
            assert field in role and role[field], f"missing {field} in {role.get('role_id')}"
        assert "Goal:" in role["task_template"]
        assert "Forbidden:" in role["task_template"] or "Forbidden" in role["forbidden_actions"]
        assert role["output_contract"]


def test_skill_capability_modes_are_platform_agnostic() -> None:
    text = SKILL.read_text(encoding="utf-8")
    lower = text.lower()
    assert "native sub-agent" in lower
    assert "equivalent isolated" in lower or "等价隔离" in text
    assert "sequential" in lower or "single-agent" in lower or "降级" in text

    # Vendor SDK wiring / runtime platform branches are forbidden.
    # Documenting the prohibition (e.g. "do not encode ... if platform") is allowed.
    assert "openai sdk" not in lower
    assert "anthropic sdk" not in lower
    assert "cursor sdk" not in lower
    assert "from openai" not in lower
    assert "from anthropic" not in lower
    assert not re.search(r"\bif\s+platform\s*(==|in)\b", text)
    assert "product_whitelist" not in lower
    assert "PLATFORM_WHITELIST" not in text


def test_skill_phase05_protocol_requires_equivalent_auditable_modes() -> None:
    text = SKILL.read_text(encoding="utf-8")
    lower = text.lower()
    assert "stable" in lower or "稳定" in text
    assert "budget lease" in lower or "预算租约" in text
    assert "recursively spawn" in lower or "递归派生" in text
    assert re.search(r"at most two\s+(?:debate\s+)?rounds", lower) or "最多两轮" in text
    assert "at most one revision" in lower or "最多一次修订" in text


def test_skill_phase05_debate_protocol_preserves_hard_failure_and_full_rerun() -> None:
    text = SKILL.read_text(encoding="utf-8")
    lower = text.lower()
    assert "do not debate a hard" in lower
    assert "high-value conflict" in lower
    assert "claim → evidence → objection → falsification test → response → decision" in lower
    assert re.search(
        r"full preflight\s*→\s*compute\s*→\s*evaluate\s*→\s*independent-review",
        lower,
    )
