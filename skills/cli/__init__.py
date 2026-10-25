"""Model-driven Skill command line interface; stdout is one JSON envelope."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timezone
from importlib import metadata, util
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import CliSettingsSource, SettingsError

from .io import json_safe, read_json
from .models import CLIError, CLIModel, CommandResult
from .registry import SKILLS, get_commands

MAX_STDOUT_BYTES = 25_000  # A conservative upper bound of 25k tokenizer bytes/tokens.
SUMMARY_SAMPLE = 3  # Items kept from a summarized list or dict.
SUMMARY_TEXT = 200  # Characters kept from a summarized string.
# Optional dependency profile -> module whose presence `qs version` reports.
EXTRAS = {
    "analyze": "seaborn",
    "ml": "pycaret",
    "report": "jinja2",
    "query": "duckdb",
    "ts": "tsfresh",
    "panda_data": "panda_data",
}


class CatalogInput(CLIModel):
    skill: str | None = Field(None, description="Filter by CLI Skill name.")
    format: Literal["json", "markdown"] = Field(
        "json", description="Catalog representation inside the JSON envelope."
    )


class SchemaInput(CLIModel):
    command: str = Field(description="Dotted command name, for example backtest.run.")
    part: Literal["input", "output", "both"] = Field("both", description="Schema part to return.")
    file_field: str | None = Field(None, description="Return a JSON file field's payload schema.")


class DocsInput(CLIModel):
    skill: str | None = Field(
        None, description="Render only this Skill; defaults to all supported Skills."
    )
    check: bool = Field(False, description="Check generated sections without writing files.")


def _source(model, argv, name):
    source = CliSettingsSource(
        model,
        cli_prog_name="qs " + name.replace(".", " "),
        cli_kebab_case=True,
        cli_implicit_flags=True,
        cli_exit_on_error=False,
        cli_enforce_required=False,
        cli_parse_args=False,
    )
    return source(args=argv)()


def _parse(model, argv, name, positional=()):
    # Transport switches are separate from domain inputs; domain flags come entirely from models.
    argv = list(argv)
    base = {}
    transport = {"preview": 5, "log_level": "WARNING"}
    if "--input-json" in argv:
        index = argv.index("--input-json")
        if index + 1 == len(argv):
            raise ValueError("--input-json needs a path or -")
        base = read_json(argv[index + 1])
        if not isinstance(base, dict):
            raise ValueError("--input-json requires a JSON object")
        del argv[index : index + 2]
    for key in transport:
        if key in base:
            transport[key] = base.pop(key)
        switch = "--" + key.replace("_", "-")
        if switch in argv:
            index = argv.index(switch)
            if index + 1 == len(argv):
                raise ValueError(f"{switch} needs a value")
            transport[key] = argv[index + 1]
            del argv[index : index + 2]
    try:
        transport["preview"] = int(transport["preview"])
    except (TypeError, ValueError) as exc:
        raise ValueError("--preview must be an integer from 0 to 100") from exc
    if not 0 <= transport["preview"] <= 100:
        raise ValueError("--preview must be an integer from 0 to 100")
    for field in positional:
        if argv and not argv[0].startswith("-"):
            base[field] = argv.pop(0)
    parameters = {}
    while "-p" in argv:
        index = argv.index("-p")
        if index + 1 == len(argv) or "=" not in argv[index + 1]:
            raise ValueError("-p requires key=value")
        key, value = argv[index + 1].split("=", 1)
        if not key:
            raise ValueError("-p requires a nonempty key")
        try:
            parameters[key] = json.loads(value)
        except json.JSONDecodeError:
            parameters[key] = value
        del argv[index : index + 2]
    flags = _source(model, argv, name)
    base.update(flags)
    if parameters:
        if "params" not in model.model_fields:
            raise ValueError("This command does not accept -p")
        base["params"] = {**base.get("params", {}), **parameters}
    args = model.model_validate(base)
    args._transport_preview = transport["preview"]
    args._transport_log_level = str(transport["log_level"])
    return args


def schema_template(schema, root=None, seen=()):
    """A fillable skeleton, not a fabricated valid research contract."""
    root = root or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        if reference in seen:
            return None
        node = root
        for token in reference.removeprefix("#/").split("/"):
            node = node[token]
        return schema_template(node, root, (*seen, reference))
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for alternatives in ("anyOf", "oneOf"):
        if alternatives in schema:
            choices = [s for s in schema[alternatives] if s.get("type") != "null"]
            return schema_template(choices[0], root, seen) if choices else None
    kind = schema.get("type")
    if kind == "object":
        return {
            key: schema_template(value, root, seen)
            for key, value in schema.get("properties", {}).items()
        }
    if kind == "array":
        return []
    if kind == "boolean":
        return False
    if kind in ("integer", "number"):
        return schema.get("minimum", 0)
    if kind == "string":
        return ""
    return None


def _root(argv):
    name = argv[0]
    if name == "version":
        _parse(CLIModel, argv[1:], "version")
        from skills.factor_mining.contracts import SCHEMA_VERSION

        return CommandResult(
            data={
                "version": metadata.version("quantspace"),
                "factor_mining_schema_version": SCHEMA_VERSION,
                "extras": {
                    key: util.find_spec(module) is not None for key, module in EXTRAS.items()
                },
            }
        )
    with redirect_stdout(sys.stderr):
        commands = get_commands()
    if name == "catalog":
        args = _parse(CatalogInput, argv[1:], name)
        if args.skill and args.skill not in SKILLS:
            raise ValueError(f"Unknown Skill: {args.skill}")
        entries = [
            cmd.catalog_entry()
            for cmd in commands.values()
            if not args.skill or cmd.name.split(".")[0] == args.skill
        ]
        if args.format == "markdown":
            content = "| Command | Summary | Side effects | Priority |\n|---|---|---|---|\n"
            content += "\n".join(
                f"| {e['command']} | {e['summary']} | {', '.join(e['side_effects'])} | {e['priority']} |"
                for e in entries
            )
            return CommandResult(data={"markdown": content})
        return CommandResult(data={"commands": entries})
    if name == "schema":
        args = _parse(SchemaInput, argv[1:], name, ("command",))
        if args.command not in commands:
            raise ValueError(f"Unknown command: {args.command}")
        schemas = commands[args.command].schemas()
        if args.file_field:
            return CommandResult(data=commands[args.command].json_file_schema(args.file_field))
        return CommandResult(data=schemas if args.part == "both" else schemas[args.part])
    if name == "docs" and len(argv) > 1 and argv[1] == "render":
        from .docs import render_docs

        args = _parse(DocsInput, argv[2:], "docs.render")
        if args.skill and args.skill not in SKILLS:
            raise ValueError(f"Unknown Skill: {args.skill}")
        return render_docs(commands, skill=args.skill, check=args.check)
    raise ValueError(f"Unknown command: {' '.join(argv)}")


def _resolve(argv, commands):
    for count in range(min(4, len(argv)), 0, -1):
        key = ".".join(argv[:count])
        if key in commands:
            return commands[key], argv[count:]
    raise ValueError(f"Unknown command: {' '.join(argv)}")


def _failure(name, exc):
    hint = f"Run `uv run qs {name.replace('.', ' ')} --help` for parameters."
    if isinstance(exc, CLIError):
        code, status, details = exc.code, exc.exit_code, exc.details
        hint = exc.hint or hint
    elif isinstance(exc, ValidationError):
        code, status = "INVALID_INPUT", 2
        details = exc.errors(include_context=False, include_url=False, include_input=False)
    elif isinstance(exc, FileNotFoundError):
        code, status, details = "NOT_FOUND", 3, []
    elif isinstance(exc, ImportError):
        code, status, details = "MISSING_DEPENDENCY", 3, []
        hint = (
            "Install the command extra with uv sync --extra analyze|ml|report|query|ts|panda_data."
        )
    elif isinstance(exc, TimeoutError):
        code, status, details = "TIMEOUT", 124, []
    elif isinstance(exc, (ValueError, SettingsError, KeyError, TypeError)):
        code, status, details = "INVALID_INPUT", 2, []
    elif isinstance(exc, ConnectionError):
        code, status, details = "UPSTREAM_ERROR", 4, []
    else:
        code, status, details = "INTERNAL", 1, []
    return status, {
        "ok": False,
        "command": name,
        "error": {
            "code": code,
            "message": f"{exc.error_count()} validation errors"
            if isinstance(exc, ValidationError)
            else str(exc),
            "details": details,
            "hint": hint,
        },
    }


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _is_summary(node):
    return isinstance(node, dict) and node.keys() == {"summarized", "count", "sample"}


def _slots(node, path):
    """Yield (path, parent, key) for every descendant of node, without entering summaries."""
    is_list = isinstance(node, list)
    children = enumerate(node) if is_list else node.items() if isinstance(node, dict) else ()
    for key, child in children:
        child_path = f"{path}[{key}]" if is_list else f"{path}.{key}"
        yield child_path, node, key
        if not _is_summary(child):
            yield from _slots(child, child_path)


def _describe(node):
    if isinstance(node, str):
        return f"{len(node)} chars"
    return f"{len(node)} {'items' if isinstance(node, list) else 'keys'}"


def _summarized(node):
    """Return the smaller stand-in for node, or None when it cannot shrink further."""
    if _is_summary(node):
        return {**node, "sample": type(node["sample"])()} if node["sample"] else None
    if isinstance(node, list) and len(node) > SUMMARY_SAMPLE:
        return {"summarized": True, "count": len(node), "sample": node[:SUMMARY_SAMPLE]}
    if isinstance(node, dict) and len(node) > SUMMARY_SAMPLE:
        sample = dict(list(node.items())[:SUMMARY_SAMPLE])
        return {"summarized": True, "count": len(node), "sample": sample}
    # A shortened string is SUMMARY_TEXT + 1 characters long, so it never shrinks again.
    if isinstance(node, str) and len(node) > SUMMARY_TEXT + 1:
        return node[:SUMMARY_TEXT] + "…"
    return None


def _write_full_envelope(envelope):
    directory = Path(tempfile.gettempdir()) / "qs-output"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = directory / f"{stamp}-{envelope['command']}-{os.getpid()}.json"
    # Indented so grep and sed can read the file line by line.
    path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8"
    )
    return path


def _summarize(envelope, full_path):
    """Shrink the largest nodes of data and artifacts in place until the envelope fits stdout."""
    notes = []
    while True:
        summarized = ", ".join(notes)
        warning = (
            f"Output exceeded the stdout budget; the full envelope is at {full_path}."
            + (f" Summarized: {summarized}." if notes else "")
            + " Read it selectively (jq, grep, sed -n); do not read it whole."
        )
        result = {
            **envelope,
            "artifacts": [
                *envelope.get("artifacts", []),
                {"name": "full_output", "path": str(full_path), "format": "json"},
            ],
            "warnings": [*envelope.get("warnings", []), warning],
        }
        # Artifacts keep their name, path and format; only their column lists can grow large.
        slots = [
            (f"artifacts[{index}].columns", artifact, "columns")
            for index, artifact in enumerate(envelope.get("artifacts", []))
            if "columns" in artifact
        ]
        candidates = [
            (_size(parent[key]), path, parent, key, replacement)
            for path, parent, key in [*_slots(envelope.get("data"), "data"), *slots]
            if (replacement := _summarized(parent[key])) is not None
        ]
        if not candidates or _size(result) <= MAX_STDOUT_BYTES:
            return result
        _, path, parent, key, replacement = max(candidates, key=lambda item: item[0])
        if not _is_summary(parent[key]):
            notes.append(f"{path} ({_describe(parent[key])})")
        parent[key] = replacement


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # A command must never open plot windows; Skill code that calls plt.show() stays headless.
    os.environ.setdefault("MPLBACKEND", "Agg")
    if not argv or argv == ["--help"] or argv == ["-h"]:
        print(
            "Usage: qs <skill> <command> [options]\n\nSkills: "
            + ", ".join(SKILLS)
            + "\nDiscovery: catalog | schema <skill.command> | docs render | version\n"
            + "Transport: --input-json FILE|- (flags override JSON), --preview N, --log-level LEVEL, --print-template [JSON_FIELD]; -p key=value"
        )
        return 0
    name = ".".join(argv[:2]) if len(argv) > 1 and not argv[1].startswith("-") else argv[0]
    try:
        if argv[0] in ("catalog", "schema", "docs", "version"):
            result = _root(argv)
        else:
            with redirect_stdout(sys.stderr):
                commands = get_commands(argv[0] if argv[0] in SKILLS else None)
            # Intermediate group help is discovery; exact command help is model-generated.
            if argv[-1] in ("--help", "-h") and ".".join(argv[:-1]) not in commands:
                prefix = ".".join(argv[:-1])
                matches = [cmd for key, cmd in commands.items() if key.startswith(prefix + ".")]
                if not matches:
                    raise ValueError(f"Unknown command group: {prefix}")
                print("\n".join(f"{cmd.name.replace('.', ' ')}: {cmd.summary}" for cmd in matches))
                return 0
            command, flags = _resolve(argv, commands)
            name = command.name

            def selected_file_field(switch):
                index = flags.index(switch)
                if index + 1 < len(flags) and not flags[index + 1].startswith("-"):
                    if len(flags) != index + 2:
                        raise ValueError(f"{switch} accepts one JSON file field")
                    return flags[index + 1]
                if len(flags) != index + 1:
                    raise ValueError(f"{switch} accepts one JSON file field")
                return None

            if "--print-template" in flags:
                field = selected_file_field("--print-template")
                template_schema = (
                    command.json_file_schema(field)
                    if field
                    else command.input_model.model_json_schema()
                )
                template = schema_template(template_schema)
                if field and template_schema.get("type") == "array" and not template:
                    template = [schema_template(template_schema["items"], template_schema)]
                result = CommandResult(data=template)
            else:
                args = _parse(command.input_model, flags, name, command.positional)
                level = getattr(logging, args.log_level.upper(), None)
                if not isinstance(level, int):
                    raise ValueError("Unknown log level")
                logging.basicConfig(stream=sys.stderr, level=level)
                with redirect_stdout(sys.stderr):
                    result = command.handler(args)
                # Validate before publishing stdout, so output contract failures cannot look successful.
                try:
                    data = command.output_model.model_validate(result.data).model_dump()
                except ValidationError as exc:
                    raise CLIError(
                        "INTERNAL",
                        "Command output did not match its schema",
                        1,
                        details=exc.errors(
                            include_input=False, include_context=False, include_url=False
                        ),
                    ) from exc
                result.data = data
        status = result.exit_code
        envelope = {
            "ok": status == 0,
            "command": name,
            "data": result.data,
            "artifacts": [a.model_dump() for a in result.artifacts],
            "warnings": result.warnings,
        }
        if status:
            envelope["error"] = {
                "code": {
                    2: "INVALID_INPUT",
                    3: "NOT_FOUND",
                    4: "UPSTREAM_ERROR",
                    124: "TIMEOUT",
                }.get(status, "CHECK_FAILED"),
                "message": "Command completed with failed checks",
                "details": [],
                "hint": "Inspect data and warnings for failed checks.",
            }
    except SystemExit as exc:
        # argparse uses SystemExit(0) for help. Parsing errors use SettingsError instead.
        if exc.code == 0:
            if "command" in locals() and name == command.name:
                print(
                    "\nDiscovery: qs schema <skill.command> [--part input|output|both] [--file-field FIELD]; --print-template [FIELD] selects a template.\nTransport: --input-json FILE|-, --preview N, --log-level LEVEL; flags override matching JSON keys."
                )
            return 0
        status, envelope = _failure(name, ValueError("Invalid command parameters"))
    except Exception as exc:
        status, envelope = _failure(name, exc)
    safe = json_safe(envelope)
    payload = json.dumps(safe, ensure_ascii=False, allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_STDOUT_BYTES:
        safe = _summarize(safe, _write_full_envelope(safe))
        payload = json.dumps(safe, ensure_ascii=False, allow_nan=False)
    print(payload)
    return status
