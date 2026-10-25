"""One registry for execution, discovery, schemas, and command documentation."""

from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from importlib import import_module

from pydantic import BaseModel, TypeAdapter

from .models import CLIModel, CommandResult

# CLI Skill names use hyphens; their Python packages use underscores.
SKILLS = (
    "ingest",
    "store",
    "compute",
    "strategy",
    "backtest",
    "analyze",
    "ml",
    "factor-mining",
    "report",
)


def _embed_refs(node, prefix: str):
    if isinstance(node, dict):
        return {
            key: prefix + value.removeprefix("#/")
            if key == "$ref" and isinstance(value, str) and value.startswith("#/")
            else _embed_refs(value, prefix)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_embed_refs(value, prefix) for value in node]
    return node


@dataclass(frozen=True)
class Command:
    name: str
    input_model: type[CLIModel]
    output_model: type[BaseModel]
    handler: Callable[..., CommandResult]
    summary: str
    side_effects: tuple[str, ...] = ("read-only",)
    priority: str = "P1"
    positional: tuple[str, ...] = ()

    def json_file_schema(self, field: str) -> dict:
        model_field = self.input_model.model_fields.get(field)
        reference = (
            (model_field.json_schema_extra or {}).get("x-json-file-model") if model_field else None
        )
        if not isinstance(reference, str):
            raise ValueError(f"{field} is not a JSON file field of {self.name}")
        module_name, type_name = reference.split(":", 1)
        payload_type = getattr(import_module(module_name), type_name)
        schema = TypeAdapter(payload_type).json_schema()
        if (model_field.json_schema_extra or {}).get("x-json-file-strict"):
            if not is_dataclass(payload_type):
                raise TypeError(f"{reference} must be a dataclass for strict file schema")
            schema["required"] = [item.name for item in fields(payload_type)]
            schema["additionalProperties"] = False
        return schema

    def schemas(self) -> dict:
        input_schema = self.input_model.model_json_schema()
        for field, schema in input_schema.get("properties", {}).items():
            schema.pop("x-json-file-strict", None)
            if schema.pop("x-json-file-model", None):
                payload = self.json_file_schema(field)
                prefix = f"#/properties/{field}/x-json-file-schema/"
                schema["x-json-file-schema"] = _embed_refs(payload, prefix)
        return {
            "input": input_schema,
            "output": self.output_model.model_json_schema(),
        }

    def catalog_entry(self) -> dict:
        return {
            "command": self.name,
            "summary": self.summary,
            "side_effects": list(self.side_effects),
            "priority": self.priority,
        }


def get_commands(skill: str | None = None) -> dict[str, Command]:
    commands = {}
    for item in (skill,) if skill else SKILLS:
        module = import_module(f"skills.{item.replace('-', '_')}.cli")
        for command in module.COMMANDS:
            if command.name in commands:
                raise RuntimeError(f"Duplicate command: {command.name}")
            commands[command.name] = command
    return commands
