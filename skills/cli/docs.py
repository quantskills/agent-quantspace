"""Generated command references, derived exclusively from registered models."""

from pathlib import Path

from .models import CommandResult, OutputOptions, PanelSource
from .registry import SKILLS

BEGIN = "<!-- BEGIN GENERATED: qs commands -->"
END = "<!-- END GENERATED: qs commands -->"


GROUPS = (("PanelSource", PanelSource), ("OutputOptions", OutputOptions))


def _field_type(info):
    if "enum" in info:
        return "|".join(map(str, info["enum"]))
    if "const" in info:
        return str(info["const"])
    if "anyOf" in info or "oneOf" in info:
        alternatives = info.get("anyOf", info.get("oneOf", []))
        optional = any(item.get("type") == "null" for item in alternatives)
        rendered = []
        for item in alternatives:
            if item.get("type") != "null":
                value = _field_type(item)
                if value not in rendered:
                    rendered.append(value)
        value = "|".join(rendered) or "any"
        return value + ("?" if optional else "")
    if "$ref" in info:
        return info["$ref"].rsplit("/", 1)[-1]
    kind = info.get("type", "any")
    if kind == "array":
        return f"list[{_field_type(info.get('items', {}))}]"
    if kind == "string" and info.get("format") == "path":
        return "path"
    return {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "object": "object",
        "null": "null",
    }.get(kind, str(kind))


def _default(info, *, required):
    if required:
        return "required"
    if "default" not in info:
        return "factory"
    value = info["default"]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _option_row(field, info, *, required):
    description = info.get("description", "").replace("|", "\\|").replace("\n", " ")
    field_type = _field_type(info).replace("|", "\\|")
    return (
        f"| `--{field.replace('_', '-')}` | `{field_type}` / `{_default(info, required=required)}` | "
        f"{description} |"
    )


def _shared_fields(command, group_model):
    if not issubclass(command.input_model, group_model):
        return set()
    command_schema = command.schemas()["input"]
    group_schema = group_model.model_json_schema()
    inherited = set()
    for field, info in group_schema.get("properties", {}).items():
        if command_schema.get("properties", {}).get(field) == info:
            command_required = field in command_schema.get("required", [])
            group_required = field in group_schema.get("required", [])
            if command_required == group_required:
                inherited.add(field)
    return inherited


def command_reference(commands, skill):
    selected = [command for command in commands.values() if command.name.split(".")[0] == skill]
    lines = [
        BEGIN,
        "",
        "Transport: `--input-json FILE|-`, `--preview N`, and `--log-level LEVEL`; flags override JSON. Use `--print-template [FIELD]` for fillable templates.",
        "",
    ]
    used_groups = []
    for name, model in GROUPS:
        if any(_shared_fields(command, model) for command in selected):
            used_groups.append((name, model))
    if used_groups:
        lines += ["### Shared parameter groups", ""]
        for name, model in used_groups:
            schema = model.model_json_schema()
            lines += [
                f"#### `{name}`",
                "",
                "| Option | Type / default | Description |",
                "|---|---|---|",
            ]
            required = set(schema.get("required", []))
            for field, info in schema.get("properties", {}).items():
                lines.append(_option_row(field, info, required=field in required))
            lines.append("")
    for command in selected:
        invocation = "uv run qs " + command.name.replace(".", " ")
        inherited = set()
        group_names = []
        for name, model in used_groups:
            fields = _shared_fields(command, model)
            if fields:
                inherited.update(fields)
                group_names.append(name)
        lines += [
            f"### `{invocation}`",
            "",
            command.summary,
            "",
            f"Priority: {command.priority}. Side effects: {', '.join(command.side_effects)}.",
            "",
        ]
        if command.positional:
            lines += [
                "Positional: " + ", ".join(f"`{name}`" for name in command.positional) + ".",
                "",
            ]
        if group_names:
            lines += [
                "Shared parameters: " + ", ".join(f"`{name}`" for name in group_names) + ".",
                "",
            ]
        lines += [
            "| Option | Type / default | Description |",
            "|---|---|---|",
        ]
        schema = command.schemas()["input"]
        required = set(schema.get("required", []))
        for field, info in schema.get("properties", {}).items():
            if field in inherited:
                continue
            lines.append(_option_row(field, info, required=field in required))
            if "x-json-file-schema" in info:
                lines.append(
                    f"| ↳ JSON payload | `qs schema {command.name} --file-field {field}` | "
                    f"Generate a fillable file with `{invocation} --print-template {field}`. |"
                )
        lines += [
            "",
            "Output data fields: "
            + ", ".join(f"`{key}`" for key in command.output_model.model_fields)
            + ".",
            "",
            f"Inspect schemas: `uv run qs schema {command.name}` (add `--part input|output` or `--file-field FIELD`).",
            "",
        ]
    return "\n".join([*lines, END])


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
