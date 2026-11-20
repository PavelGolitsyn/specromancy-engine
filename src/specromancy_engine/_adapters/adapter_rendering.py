"""Deterministic harness rendering and expected manifest construction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from string import Template
from typing import TYPE_CHECKING, Any

from .adapter_contracts import (
    ADAPTER_COMMANDS, ADAPTER_SCHEMA_VERSION, GENERATOR_VERSION,
    MANIFEST_PATH, REGENERATION_COMMAND, AdapterCommand, AdapterError,
    COMMAND_PATHS, SKILL_CONSUMERS, INSTRUCTION_CONSUMERS, consumers_for_path, target_records,
)
from ..hashing import sha256_bytes, sha256_json

if TYPE_CHECKING:
    from .adapter_sources import AdapterSources, SourceInput


class _TemplateFields(Template):
    # Dollar signs are literal harness syntax, including $0 and $ARGUMENTS.
    delimiter = "%"


def render_release_template(source: SourceInput, **values: str) -> str:
    """Render a captured template once, preserving its original bytes for hashing."""
    try:
        template = _TemplateFields(source.content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise AdapterError("invalid UTF-8 in adapter release template", {"path": source.path}) from exc
    if not template.is_valid():
        raise AdapterError("invalid adapter template placeholder", {"path": source.path})
    required = set(template.get_identifiers())
    if required != values.keys():
        raise AdapterError("adapter template fields differ", {
            "path": source.path, "missing": sorted(required - values.keys()),
            "unknown": sorted(values.keys() - required),
        })
    rendered = template.substitute(values).replace("\r\n", "\n").replace("\r", "\n")
    return rendered.rstrip("\n") + "\n"


def render_release_launch(pipeline_id: str | None, launch: SourceInput, orchestrator: SourceInput) -> str:
    return render_release_template(
        launch, template_id=launch.path, title=pipeline_id or "Pipeline",
        skill_name=f"specromancy-{pipeline_id}" if pipeline_id else "pipeline",
        description=(f"Coordinate the {pipeline_id} pipeline when the user requests this workflow."
                     if pipeline_id else "Coordinate a registered Specromancy pipeline."),
        binding=(f"This invocation supplies `{pipeline_id}` as the pipeline ID for a new run."
                 if pipeline_id else "Use the registered pipeline ID supplied by the caller."),
        orchestrator_id=orchestrator.path,
        orchestration=render_release_template(orchestrator, pipeline_id=pipeline_id or "PIPELINE_ID"),
    )


def _harness_invocation(harness: str, command: AdapterCommand) -> str:
    if harness == "claude":
        arguments = {
            "init": '"$1" --pipeline "$0"',
            "resume": '"$0"',
            "status": '"$0"',
            "phase": '"$0" "$1"',
        }[command.name]
    elif harness == "opencode":
        arguments = {
            "init": '"$2" --pipeline "$1"',
            "resume": '"$1"',
            "status": '"$1"',
            "phase": '"$1" "$2"',
        }[command.name]
    else:
        arguments = "DESCRIPTION --pipeline PIPELINE_ID" if command.name == "init" else command.arguments
    return f"specromancy {command.cli_command} {arguments} --json"


def _command_follow(command: AdapterCommand) -> str:
    if command.name == "init":
        return (
            "Use the returned run ID and recorded next command. If the response contains "
            "an action packet, load its `skill.absolute_path` and follow that canonical "
            "procedure exactly."
        )
    if command.name == "status":
        return (
            "Report the persisted status and recorded next command. Do not infer run state "
            "from conversation history."
        )
    return (
        "If the response contains an action packet, load its `skill.absolute_path` and "
        "follow that canonical procedure exactly. Stop at any recorded pause, approval, "
        "block, validation failure, or terminal result."
    )


def render_workflow_sources(sources: AdapterSources) -> dict[str, bytes]:
    """Render the union of the selected harnesses' requirements from a single capture."""
    if not sources.harnesses:
        return {}
    assert sources.instructions is not None
    selected = set(sources.harnesses)
    templates = sources.templates
    envelope = templates["instructions.md"]
    files = {
        path: render_release_template(envelope, template_id=envelope.path,
                                      instructions=sources.instructions.content.decode("utf-8"))
        for path, consumers in INSTRUCTION_CONSUMERS.items() if selected.intersection(consumers)
    }

    launch, orchestrator = templates["launch.md"], templates["orchestrator.md"]
    skills = {"pipeline": render_release_launch(None, launch, orchestrator)}
    for pipeline in sources.pipelines:
        skills[f"specromancy-{pipeline.id}"] = render_release_launch(pipeline.id, launch, orchestrator)
    wrapper = templates["phase.md"]
    for skill in sources.skills:
        skills[skill.name] = render_release_template(
            wrapper, template_id=wrapper.path, validated_metadata=skill.frontmatter, skill_source=skill.source.path,
        )
    for directory, consumers in SKILL_CONSUMERS.items():
        if selected.isdisjoint(consumers):
            continue
        for name, content in skills.items():
            files[f"{directory}/{name}/SKILL.md"] = content

    for harness, pattern in COMMAND_PATHS.items():
        if harness not in selected:
            continue
        source = templates[f"command-{harness}.md"]
        for command in ADAPTER_COMMANDS:
            description = sources.command_help.get(command.cli_command, command.description)
            values = {
                "template_id": source.path,
                "description": json.dumps(description, ensure_ascii=False),
                "invocation": _harness_invocation(harness, command),
                "follow": _command_follow(command),
            }
            if harness != "opencode":
                values["arguments"] = command.arguments
            files[pattern.format(name=command.name)] = render_release_template(source, **values)
    return {path: files[path].encode("utf-8") for path in sorted(files)}


def workflow_manifest(bundle: AdapterSources, rendered: Mapping[str, bytes]) -> dict[str, Any]:
    selected = set(bundle.harnesses)
    generated = [{"path": path, "sha256": sha256_bytes(content),
                  "targets": sorted(selected.intersection(consumers_for_path(path)))}
                 for path, content in sorted(rendered.items())]
    sources = [source.record() for source in bundle.inputs]
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "generator": {
            "name": "specromancy",
            "version": GENERATOR_VERSION,
            "command": REGENERATION_COMMAND,
        },
        "canonical_source": {
            "sha256": sha256_json(sources),
            "inputs": sources,
        },
        "manifest": {
            "path": MANIFEST_PATH,
            "self_hash_omitted": True,
        },
        "targets": target_records(rendered, bundle.harnesses),
        "generated": generated,
    }
