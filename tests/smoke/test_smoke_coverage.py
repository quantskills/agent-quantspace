"""Default-suite guard: every non-network command has a smoke step or a stated skip reason.

No local data is needed; the smoke sources are read as text.
"""

from __future__ import annotations

from skills.cli.registry import get_commands
from tests.smoke.coverage import (
    OPTIONAL_DEPENDENCY,
    RESEARCH_SCRIPTS,
    ROOT_COMMANDS,
    SKIPPED,
    invoked_commands,
)
from tests.smoke.runner import REPO_ROOT


def non_network_commands() -> set[str]:
    return {
        name for name, command in get_commands().items() if "network" not in command.side_effects
    }


def test_every_non_network_command_is_smoked_or_skipped_with_a_reason() -> None:
    expected = non_network_commands()
    covered = invoked_commands(expected | set(ROOT_COMMANDS))
    uncovered = expected - covered - set(SKIPPED)
    assert not uncovered, (
        f"add smoke steps to tests/smoke or a SKIPPED reason for: {sorted(uncovered)}"
    )
    assert not set(SKIPPED) - expected, "SKIPPED names commands that are not non-network commands"
    assert not set(SKIPPED) & covered, "a command is both smoked and listed as skipped"
    assert all(reason.strip() for reason in SKIPPED.values())


def test_optional_dependency_commands_keep_a_smoke_step() -> None:
    """A step that skips when its dependency is missing must still exist in the sources."""
    expected = non_network_commands()
    covered = invoked_commands(expected | set(ROOT_COMMANDS))
    assert set(OPTIONAL_DEPENDENCY) <= expected, "OPTIONAL_DEPENDENCY names unknown commands"
    assert set(OPTIONAL_DEPENDENCY) <= covered, "an optional-dependency command has no smoke step"
    assert not set(OPTIONAL_DEPENDENCY) & set(SKIPPED), (
        "a command is listed as skipped and optional"
    )
    assert all(module and reason.strip() for module, reason in OPTIONAL_DEPENDENCY.values())


def test_root_commands_are_smoked() -> None:
    covered = invoked_commands(non_network_commands() | set(ROOT_COMMANDS))
    assert set(ROOT_COMMANDS) <= covered


def test_research_scripts_named_by_the_smoke_tests_exist() -> None:
    for label, module in RESEARCH_SCRIPTS.items():
        assert (REPO_ROOT / (module.replace(".", "/") + ".py")).is_file(), (label, module)
