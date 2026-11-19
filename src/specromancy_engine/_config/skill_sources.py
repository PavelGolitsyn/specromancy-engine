"""Portable procedure metadata and identifier bindings for workflow sources."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config_fields import FieldContext
from .config_models import PhaseConfig, PipelineConfig


_NON_STRING_SCALAR = re.compile(
    r"(?:null|~|true|false|[-+]?(?:0x[0-9a-f]+|0o[0-7]+|\.inf|\.nan|"
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?))", re.IGNORECASE
)


def _scalar(value: str) -> str:
    """Read a single-line string in the portable frontmatter subset."""
    if value.startswith('"'):
        value = json.loads(value)
    elif value.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')*'", value):
            raise ValueError("invalid single-quoted string")
        value = value[1:-1].replace("''", "'")
    elif (_NON_STRING_SCALAR.fullmatch(value)
          or re.search(r"^(?:[][{},|>!&*#@%`]|[-?:](?:\s|$))|:(?:\s|$)|\s#", value)):
        raise ValueError("quote the value as a single-line string")
    if not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("expected a nonempty single-line string")
    return value


def parse_skill_frontmatter(text: str) -> dict[str, str | dict[str, str]]:
    """Read only portable scalar fields and one flat metadata mapping."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("expected frontmatter between two --- lines")
    try:
        closing = lines.index("---", 1)
    except ValueError:
        raise ValueError("missing frontmatter closing delimiter") from None
    fields: dict[str, str | dict[str, str]] = {}
    metadata: dict[str, str] = {}
    in_metadata = False
    for line in lines[1:closing]:
        if not line.strip():
            continue
        nested = line.startswith("  ")
        key, colon, value = (line[2:] if nested else line).partition(":")
        if (not colon or not re.fullmatch(r"[A-Za-z0-9_.-]+", key)
                or (value and not value.startswith(" "))):
            raise ValueError("expected a key and a single-line value")
        if nested:
            if not in_metadata or key in metadata:
                raise ValueError(f"unexpected or duplicate nested key {key!r}")
            metadata[key] = _scalar(value.strip())
            continue
        if key not in {"name", "description", "license", "compatibility", "metadata"} or key in fields:
            raise ValueError(f"unsupported or duplicate frontmatter key {key!r}")
        in_metadata = key == "metadata"
        if in_metadata:
            if value.strip():
                raise ValueError("metadata must contain indented key/value pairs")
            fields[key] = metadata
        else:
            fields[key] = _scalar(value.strip())
    if not {"name", "description"} <= fields.keys():
        raise ValueError("name and description are required")
    if "metadata" in fields and not metadata:
        raise ValueError("metadata must contain at least one key/value pair")
    return fields


class SkillBindings:
    """One normalized declaration and one resolved file per skill identifier."""

    def __init__(self) -> None:
        self.by_name: dict[str, tuple[str | None, Path]] = {}
        self.by_path: dict[Path, str] = {}
        self.checked: set[Path] = set()

    def _bind(self, context: FieldContext, phase: PhaseConfig) -> None:
        binding = (phase.skill_source, phase.skill_path)
        if (self.by_name.setdefault(phase.skill, binding) != binding
                or self.by_path.setdefault(phase.skill_path, phase.skill) != phase.skill):
            context.fail(
                "conflicting-skill-source", f"conflicting source binding for skill {phase.skill!r}",
                field="skill_source", phase=phase.id, value=phase.skill_source,
                remediation="use one declared source per identifier and one identifier per file",
            )

    def validate_graph(self, context: FieldContext, phases: tuple[PhaseConfig, ...]) -> None:
        if not any(phase.skill_source is not None for phase in phases):
            return
        for phase in phases:
            self._bind(context, phase)
        for phase in phases:
            if phase.skill_source is not None and phase.skill_path not in self.checked:
                _validate_skill_metadata(context, phase)
                self.checked.add(phase.skill_path)


def _validate_skill_metadata(context: FieldContext, phase: PhaseConfig) -> None:
    if phase.skill == "pipeline" or phase.skill.startswith("specromancy-"):
        context.fail(
            "reserved-skill", f"skill identifier {phase.skill!r} is reserved",
            field="skill", phase=phase.id, value=phase.skill,
            remediation="choose an identifier outside the generated launch and orchestration names",
        )
    try:
        fields = parse_skill_frontmatter(phase.skill_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        context.fail(
            "invalid-skill-frontmatter", f"cannot read portable frontmatter at {phase.skill_source}: {exc}",
            field="skill_source", phase=phase.id, value=phase.skill_source,
            remediation="provide a UTF-8 skill with portable name and description fields",
        )
    if fields["name"] != phase.skill:
        context.fail(
            "skill-name-mismatch", f"frontmatter name {fields['name']!r} differs from skill {phase.skill!r}",
            field="skill_source", phase=phase.id, value=phase.skill_source,
            remediation="make the skill identifier and canonical frontmatter name agree",
        )


def check_workflow_paths(pipeline: PipelineConfig) -> None:
    """An embedding caller may retain the parsed graph across filesystem changes."""
    context = FieldContext(pipeline.path, pipeline.repository_root)
    for phase in pipeline.phases:
        if phase.skill_source is None:
            continue
        resources = (
            ("skill_source", phase.skill_source, phase.skill_path),
            ("output_template", phase.output_template, phase.output_template_path),
            ("validator_path", phase.validator.declared_path, phase.validator.resolved_path),
        )
        for field, declared, original in resources:
            if declared is None:
                continue
            dependency = field != "skill_source"
            resolved = context.workflow_path(
                declared, field, phase=phase.id, allow_parent=dependency,
                base=pipeline.path.parent if dependency else pipeline.repository_root,
            )
            if resolved != original:
                context.fail(
                    "workflow-source-changed", f"{field} now resolves to a different workflow file",
                    field=field, phase=phase.id, value=declared,
                    remediation="restore the original workflow file or load the new configuration",
                )
