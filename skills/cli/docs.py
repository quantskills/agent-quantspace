"""Generated command lists, derived exclusively from registered commands.

A ``SKILL.md`` carries one row per command. Options, defaults, and field schemas are not written
to disk: ``--help`` and ``qs schema`` read them from the registered models.
"""

from pathlib import Path

from .models import CommandResult
from .registry import SKILLS

BEGIN = "<!-- BEGIN GENERATED: qs commands -->"
END = "<!-- END GENERATED: qs commands -->"


def command_reference(commands, skill):
    selected = [command for command in commands.values() if command.name.split(".")[0] == skill]
    lines = [
        BEGIN,
        "",
        "Before using a command, run it with `--help` to see its options and defaults. "
        "`uv run qs schema <skill>.<command>` shows its input and output fields; add "
        "`--file-field FIELD` for the structure of an option that takes a JSON file.",
        "",
        "| Command | What it does | Side effects |",
        "|---|---|---|",
    ]
    for command in selected:
        summary = command.summary.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `uv run qs {command.name.replace('.', ' ')}` | {summary} | "
            f"{', '.join(command.side_effects)} |"
        )
    return "\n".join([*lines, "", END])


def render_docs(commands, *, skill=None, check=False):
    root = Path(__file__).resolve().parents[1]
    changed = []
    for item in (skill,) if skill else SKILLS:
        path = root / item.replace("-", "_") / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        generated = command_reference(commands, item)
        if BEGIN in content and END in content:
            before, rest = content.split(BEGIN, 1)
            _, after = rest.split(END, 1)
            updated = before + generated + after
        else:
            updated = content.rstrip() + "\n\n## CLI command reference\n\n" + generated + "\n"
        if updated != content:
            changed.append(str(path))
            if not check:
                path.write_text(updated, encoding="utf-8")
    return CommandResult(
        data={"checked": check, "changed": changed}, exit_code=1 if check and changed else 0
    )
