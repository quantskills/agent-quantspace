"""Default-suite guard: every non-network command has a smoke step or a stated skip reason.

No local data is needed; the smoke sources are read as text.
"""

from __future__ import annotations

from skills.cli.registry import get_commands
from tests.smoke.coverage import ROOT_COMMANDS, SKIPPED, invoked_commands


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


def test_root_commands_are_smoked() -> None:
    covered = invoked_commands(non_network_commands() | set(ROOT_COMMANDS))
    assert set(ROOT_COMMANDS) <= covered
