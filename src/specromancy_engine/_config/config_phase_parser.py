"""Parse phases and their validation, command, transition, and artifact contracts."""

from __future__ import annotations

import math
import string
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config_fields import FieldContext, IDENTIFIER_PATTERN, _safe_declared_path
from .config_models import PhaseConfig, TransitionConfig, ValidationCommand, ValidatorConfig
from ..contracts import RESERVED_COMMANDS
from ..schema_validation import SchemaDefinitionError, load_json_schema


MUTATION_POLICIES = frozenset({"read-only", "repository-write", "allowlist"})
VALIDATOR_TYPES = frozenset({"markdown", "json", "file"})


def parse_phase(context: FieldContext, value: Any, pipeline_id: str) -> PhaseConfig:
    raw = context.require_mapping(value, "phases")
    phase_id = context.require_identifier(raw.get("id"), "id")
    allowed = {
        "id",
        "skill",
        "skill_source",
        "inputs",
        "output_name",
        "output_template",
        "mutation",
        "allowlist",
        "completion_criteria",
        "validator",
        "commands",
        "transition_approval_conditions",
        "action_approval_conditions",
        "stop_conditions",
        "transitions",
        "max_visits",
    }
    context.check_unknown(raw, allowed, phase=phase_id)
    if phase_id in RESERVED_COMMANDS:
        context.fail(
            "reserved-phase-id",
            f"phase id {phase_id!r} shadows a reserved CLI command",
            phase=phase_id,
            field="id",
            value=phase_id,
            remediation="choose a phase id that is not a CLI command",
        )
    skill = context.require_identifier(raw.get("skill"), "skill", phase=phase_id)
    if "skill_source" not in raw:
        context.fail(
            "missing-skill-source", f"pipeline {pipeline_id!r} phase {phase_id!r} requires skill_source",
            phase=phase_id, field="skill_source",
            remediation="declare skill_source as the repository-relative path to a procedure under workflow/",
        )
    declared = context.require_string(raw["skill_source"], "skill_source", phase=phase_id)
    skill_path = context.workflow_path(declared, "skill_source", phase=phase_id)
    skill_source = Path(declared).as_posix()
    inputs = context.string_list(raw.get("inputs"), "inputs", phase=phase_id)
    _validate_inputs(inputs, phase_id, context.fail)
    output_name = context.require_string(
        raw.get("output_name"), "output_name", phase=phase_id
    )
    _validate_output_pattern(
        output_name, "output_name", context.fail, phase=phase_id
    )
    output_template_raw = raw.get("output_template")
    output_template: str | None = None
    output_template_path: Path | None = None
    if output_template_raw is not None:
        output_template = context.require_string(
            output_template_raw, "output_template", phase=phase_id
        )
        output_template_path = context.phase_dependency(
            output_template, "output_template", phase=phase_id,
        )
    mutation = context.require_string(raw.get("mutation"), "mutation", phase=phase_id)
    if mutation not in MUTATION_POLICIES:
        context.fail(
            "invalid-mutation-policy",
            f"phase {phase_id!r} uses unsupported mutation policy {mutation!r}",
            phase=phase_id,
            field="mutation",
            value=mutation,
            remediation=f"choose one of {', '.join(sorted(MUTATION_POLICIES))}",
        )
    allowlist = context.string_list(
        raw.get("allowlist", []), "allowlist", phase=phase_id, allow_empty=mutation != "allowlist"
    )
    for pattern in allowlist:
        if not _safe_declared_path(pattern, allow_glob=True):
            context.fail(
                "unsafe-path",
                f"allowlist pattern escapes the repository: {pattern!r}",
                phase=phase_id,
                field="allowlist",
                value=pattern,
                remediation="use repository-relative glob patterns without parent segments",
            )
    if mutation != "allowlist" and allowlist:
        context.fail(
            "unexpected-allowlist",
            f"mutation policy {mutation!r} cannot declare an allowlist",
            phase=phase_id,
            field="allowlist",
            value=allowlist,
            remediation="remove allowlist or use mutation = 'allowlist'",
        )
    completion_criteria = context.string_list(
        raw.get("completion_criteria"),
        "completion_criteria",
        phase=phase_id,
        allow_empty=False,
    )
    validator = parse_validator(context, raw.get("validator"), phase_id)
    commands = parse_commands(context, raw, phase_id)
    transition_reasons = context.string_list(
        raw.get("transition_approval_conditions"), "transition_approval_conditions",
        phase=phase_id, identifiers=True,
    )
    action_reasons = context.string_list(
        raw.get("action_approval_conditions"), "action_approval_conditions",
        phase=phase_id, identifiers=True,
    )
    overlap = sorted(set(action_reasons).intersection(transition_reasons))
    if overlap:
        context.fail(
            "conflicting-fields", "approval reasons must have a single kind",
            phase=phase_id, field="action_approval_conditions", value=overlap,
            remediation="declare each reason in only one approval list",
        )
    stop_conditions = context.string_list(
        raw.get("stop_conditions"),
        "stop_conditions",
        phase=phase_id,
        identifiers=True,
    )
    transitions_raw = raw.get("transitions")
    if not isinstance(transitions_raw, list):
        context.fail(
            "invalid-field-type",
            "transitions must be an array of tables",
            phase=phase_id,
            field="transitions",
            value=transitions_raw,
            remediation="declare one or more [[phases.transitions]] tables",
        )
    transitions = tuple(
        parse_transition(context, item, phase_id) for item in transitions_raw
    )
    max_visits = None
    if "max_visits" in raw:
        max_visits = context.require_integer(
            raw["max_visits"], "max_visits", phase=phase_id, minimum=1
        )
    return PhaseConfig(
        id=phase_id,
        skill=skill,
        skill_source=skill_source,
        skill_path=skill_path,
        inputs=inputs,
        output_name=output_name,
        output_template=output_template,
        output_template_path=output_template_path,
        mutation=mutation,
        allowlist=allowlist,
        completion_criteria=completion_criteria,
        validator=validator,
        commands=commands,
        transition_approval_conditions=transition_reasons,
        action_approval_conditions=action_reasons,
        stop_conditions=stop_conditions,
        transitions=transitions,
        max_visits=max_visits,
    )


def parse_validator(
    context: FieldContext, value: Any, phase_id: str
) -> ValidatorConfig:
    raw = context.require_mapping(value, "validator", phase=phase_id)
    context.check_unknown(raw, {"type", "required_headings", "heading_occurrence", "path"}, phase=phase_id)
    validator_type = context.require_string(raw.get("type"), "validator.type", phase=phase_id)
    if validator_type not in VALIDATOR_TYPES:
        context.fail(
            "invalid-validator",
            f"phase {phase_id!r} uses unsupported validator {validator_type!r}",
            phase=phase_id,
            field="validator",
            value=validator_type,
            remediation=f"choose one of {', '.join(sorted(VALIDATOR_TYPES))}",
        )
    required_headings = context.string_list(
        raw.get("required_headings", []),
        "required_headings",
        phase=phase_id,
    )
    if validator_type != "markdown" and required_headings:
        context.fail(
            "invalid-validator-rule",
            "required_headings is supported only by the markdown validator",
            phase=phase_id,
            field="required_headings",
            value=required_headings,
            remediation="remove the headings or set validator.type to 'markdown'",
        )
    heading_occurrence = context.require_string(
        raw.get("heading_occurrence", "exactly-once"), "heading_occurrence", phase=phase_id
    )
    if heading_occurrence not in {"exactly-once", "at-least-once"}:
        context.fail(
            "invalid-heading-occurrence",
            "heading_occurrence must be exactly-once or at-least-once",
            phase=phase_id,
            field="heading_occurrence",
            value=heading_occurrence,
            remediation="choose exactly-once or at-least-once",
        )
    if validator_type != "markdown" and heading_occurrence != "exactly-once":
        context.fail(
            "invalid-validator-rule",
            "heading_occurrence is supported only by the markdown validator",
            phase=phase_id,
            field="heading_occurrence",
            value=heading_occurrence,
            remediation="remove the setting or set validator.type to 'markdown'",
        )
    declared_path: str | None = None
    resolved_path: Path | None = None
    json_schema: Mapping[str, Any] | None = None
    if "path" in raw:
        declared_path = context.require_string(
            raw["path"], "validator.path", phase=phase_id
        )
        resolved_path = context.phase_dependency(
            declared_path, "validator.path", phase=phase_id,
        )
        if validator_type != "json":
            context.fail(
                "invalid-validator-rule",
                "a validator schema path is supported only by the JSON validator",
                phase=phase_id,
                field="validator.path",
                value=declared_path,
                remediation="remove the path or set validator.type to 'json'",
            )
        try:
            json_schema = load_json_schema(resolved_path, read_bytes=context.read_bytes)
        except SchemaDefinitionError as exc:
            context.fail(
                "unsupported-json-schema",
                f"invalid JSON validator schema at {exc.location}: {exc}",
                phase=phase_id,
                field="validator.path",
                value=declared_path,
                remediation="use only type, required, properties, items, enum, pattern, and additionalProperties",
            )
    return ValidatorConfig(
        type=validator_type,
        required_headings=required_headings,
        heading_occurrence=heading_occurrence,
        declared_path=declared_path,
        resolved_path=resolved_path,
        json_schema=json_schema,
    )


def parse_commands(
    context: FieldContext, raw: Mapping[str, Any], phase_id: str
) -> tuple[ValidationCommand, ...]:
    values = raw.get("commands", [])
    if not isinstance(values, list):
        context.fail(
            "invalid-field-type",
            "commands must be an array of command tables",
            phase=phase_id,
            field="commands",
            value=values,
            remediation="use command tables with an argv string array",
        )
    commands: list[ValidationCommand] = []
    for value in values:
        command_raw = context.require_mapping(value, "commands", phase=phase_id)
        context.check_unknown(
            command_raw, {"argv", "timeout_seconds", "required"}, phase=phase_id
        )
        argv = context.string_list(
            command_raw.get("argv"), "commands.argv", phase=phase_id, allow_empty=False
        )
        timeout_raw = command_raw.get("timeout_seconds", 300)
        if (
            not isinstance(timeout_raw, (int, float))
            or isinstance(timeout_raw, bool)
            or not math.isfinite(timeout_raw)
            or timeout_raw <= 0
        ):
            context.fail(
                "invalid-command-timeout",
                "command timeout_seconds must be positive",
                phase=phase_id,
                field="commands.timeout_seconds",
                value=timeout_raw,
                remediation="set a positive timeout in seconds",
            )
        required = command_raw.get("required", True)
        if not isinstance(required, bool):
            context.fail(
                "invalid-field-type",
                "commands.required must be a boolean",
                phase=phase_id,
                field="commands.required",
                value=required,
                remediation="use true or false",
            )
        commands.append(
            ValidationCommand(argv, float(timeout_raw), required)
        )
    return tuple(commands)


def parse_transition(context: FieldContext, value: Any, phase_id: str) -> TransitionConfig:
    raw = context.require_mapping(value, "transitions", phase=phase_id)
    context.check_unknown(
        raw, {"outcome", "target", "max_traversals", "pause"}, phase=phase_id
    )
    outcome = context.require_identifier(
        raw.get("outcome"), "transitions.outcome", phase=phase_id
    )
    target = None
    if "target" in raw:
        target = context.require_identifier(
            raw["target"], "transitions.target", phase=phase_id
        )
    max_traversals = None
    if "max_traversals" in raw:
        max_traversals = context.require_integer(
            raw["max_traversals"],
            "transitions.max_traversals",
            phase=phase_id,
            minimum=1,
        )
    pause = raw.get("pause", False)
    if not isinstance(pause, bool):
        context.fail(
            "invalid-field-type",
            "transitions.pause must be a boolean",
            phase=phase_id,
            field="transitions.pause",
            value=pause,
            remediation="use true or false",
        )
    return TransitionConfig(outcome, target, max_traversals, pause)


def _validate_output_pattern(
    pattern: str,
    field: str,
    fail: Any,
    *,
    phase: str | None = None,
    output_name: str = "output.md",
) -> None:
    allowed_fields = {"visit", "phase", "output_name"}
    try:
        parsed = tuple(string.Formatter().parse(pattern))
        for _, name, _, conversion in parsed:
            if name is not None and name not in allowed_fields:
                raise ValueError(f"unknown placeholder {name!r}")
            if conversion:
                raise ValueError("conversions are not supported")
        rendered = pattern.format(visit=1, phase=phase or "phase", output_name=output_name)
    except (KeyError, IndexError, ValueError) as exc:
        fail(
            "invalid-output-pattern",
            f"{field} is not a valid output pattern: {exc}",
            phase=phase,
            field=field,
            value=pattern,
            remediation="use only {visit}, {phase}, and {output_name} placeholders",
        )
    if not _safe_declared_path(rendered):
        fail(
            "unsafe-output-path",
            f"{field} can resolve outside a run directory",
            phase=phase,
            field=field,
            value=pattern,
            remediation="use a relative output path without parent segments",
        )


def _validate_inputs(inputs: tuple[str, ...], phase: str, fail: Any) -> None:
    for reference in inputs:
        if reference == "request":
            continue
        if reference.startswith("latest:"):
            producer = reference.removeprefix("latest:")
            if IDENTIFIER_PATTERN.fullmatch(producer):
                continue
        if reference.startswith("visit:"):
            ordinal = reference.removeprefix("visit:")
            if ordinal.isascii() and ordinal.isdigit() and int(ordinal) >= 1:
                continue
        fail(
            "invalid-input-reference",
            f"phase {phase!r} has invalid input reference {reference!r}",
            phase=phase,
            field="inputs",
            value=reference,
            remediation="use request, latest:<phase>, or visit:<positive-number>",
        )
