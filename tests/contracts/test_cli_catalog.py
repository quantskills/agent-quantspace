"""Every registered qs command is discoverable, fully described and closed to unknown keys."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from skills.cli import schema_template
from skills.cli.registry import SKILLS, get_commands
from tests.fixtures.console import UTF8_TEXT, qs_script, utf8_env

ROOT = Path(__file__).resolve().parents[2]
SIDE_EFFECTS = {"read-only", "writes-output", "writes-store", "network", "remote-exec"}
COMMANDS = get_commands()


def _undescribed(schema, path="", defs=None):
    """Paths of object properties that lack a description, following $defs."""
    defs = schema.get("$defs", {}) if defs is None else defs
    missing = []
    for name, info in schema.get("properties", {}).items():
        if not isinstance(info, dict):
            continue
        if not info.get("description") and "$ref" not in info:
            missing.append(f"{path}.{name}")
        for key in ("items", "additionalProperties"):
            if isinstance(info.get(key), dict):
                missing += _undescribed(info[key], f"{path}.{name}[]", defs)
        for option in info.get("anyOf", []):
            missing += _undescribed(option, f"{path}.{name}", defs)
    for name, definition in (schema.get("$defs") or {}).items():
        missing += _undescribed(definition, f"{path}#{name}", defs)
    return missing


def test_every_skill_has_an_adapter_with_commands():
    for skill in SKILLS:
        assert (ROOT / "skills" / skill.replace("-", "_") / "cli.py").is_file(), skill
        assert any(name.split(".")[0] == skill for name in COMMANDS), skill


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_command_contract(name):
    command = COMMANDS[name]
    assert name.split(".")[0] in SKILLS
    assert command.summary.strip()
    assert set(command.side_effects) <= SIDE_EFFECTS
    assert command.priority in {"P0", "P1", "P2"}
    schemas = command.schemas()
    for part in ("input", "output"):
        schema = schemas[part]
        assert schema.get("additionalProperties") is False, f"{name} {part}"
        assert _undescribed(schema) == [], f"{name} {part}"
    for field in command.positional:
        assert field in command.input_model.model_fields
    template = schema_template(command.input_model.model_json_schema())
    fields = command.input_model.model_fields
    assert set(template) == {info.alias or field for field, info in fields.items()}
    for field, info in command.input_model.model_fields.items():
        if (info.json_schema_extra or {}).get("x-json-file-model"):
            assert isinstance(command.json_file_schema(field), dict)


@pytest.mark.parametrize(
    "name", sorted(name for name, cmd in COMMANDS.items() if "writes-store" in cmd.side_effects)
)
def test_store_writers_need_an_explicit_write_flag(name):
    field = COMMANDS[name].input_model.model_fields.get("write")
    assert field is not None and field.default is False


def test_no_command_takes_credentials_as_flags():
    for name, command in COMMANDS.items():
        for field in command.input_model.model_fields:
            assert not any(word in field for word in ("password", "token", "secret")), name


def test_every_flag_is_a_long_option_that_parses_as_documented():
    for name, command in COMMANDS.items():
        for field, info in command.input_model.model_fields.items():
            # One-letter fields become -x flags, while the reference documents --x.
            assert len(info.alias or field) > 1, (name, field)
            # argparse treats every --no-* spelling of a boolean flag as False.
            if info.annotation is bool:
                assert not field.startswith("no_"), (name, field)


def _qs():
    script = qs_script()
    if script is None:
        pytest.skip("qs console script is not installed in this environment")
    return script


def test_console_script_runs_from_a_subdirectory(tmp_path):
    result = subprocess.run(
        [str(_qs()), "version"],
        cwd=ROOT / "tests",
        env=utf8_env(),
        capture_output=True,
        **UTF8_TEXT,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True and envelope["command"] == "version"


def test_module_entry_point_matches_console_script():
    result = subprocess.run(
        [sys.executable, "-m", "skills", "catalog", "--skill", "store"],
        cwd=ROOT,
        env=utf8_env(),
        capture_output=True,
        **UTF8_TEXT,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    commands = {entry["command"] for entry in json.loads(result.stdout)["data"]["commands"]}
    assert commands == {name for name in COMMANDS if name.startswith("store.")}


def test_stdout_is_exactly_one_json_document_even_when_code_prints(tmp_path):
    result = subprocess.run(
        [str(_qs()), "schema", "store.read", "--part", "output"],
        cwd=tmp_path,
        env=utf8_env(),
        capture_output=True,
        **UTF8_TEXT,
        timeout=120,
    )
    assert result.returncode == 0
    assert result.stdout.count("\n") == 1
    json.loads(result.stdout)
