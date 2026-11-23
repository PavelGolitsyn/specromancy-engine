"""Per-invocation capture of validated adapter sources and their hash inputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .adapter_config import SELECTION_PATH, load_selection, selection_bytes
from .adapter_contracts import ADAPTER_COMMANDS, COMMAND_PATHS, AdapterError
from .._config.config_fields import FieldContext
from .._cli.cli_commands import adapter_command_metadata
from .._version import get_version
from ..hashing import canonical_json_bytes, sha256_bytes

if TYPE_CHECKING:
    from .._config.config_models import PipelineConfig
    from ..registry import PipelineRegistry


@dataclass(frozen=True, slots=True)
class SourceInput:
    kind: str
    path: str
    content: bytes

    def record(self) -> dict[str, str]:
        return {"kind": self.kind, "path": self.path, "sha256": sha256_bytes(self.content)}


COMMON_TEMPLATES = ("instructions.md", "launch.md", "orchestrator.md", "phase.md")
TEMPLATE_NAMES = (*COMMON_TEMPLATES, *(f"command-{name}.md" for name in COMMAND_PATHS))


def load_release_template(name: str) -> SourceInput:
    if name not in TEMPLATE_NAMES:
        raise AdapterError("unknown adapter release template", {"name": name})
    source_id = f"@package/specromancy_engine/resources/adapters/{name}"
    try:
        content = files("specromancy_engine").joinpath("resources", "adapters", name).read_bytes()
    except OSError as exc:
        raise AdapterError("cannot read adapter release template", {"path": source_id}) from exc
    return SourceInput("release-template", source_id, content)


def capture_release_inputs(names: Sequence[str] = TEMPLATE_NAMES) -> tuple[SourceInput, ...]:
    version = SourceInput("package-version", "@package/specromancy_engine/version",
                          get_version().encode("utf-8"))
    return (version, *(load_release_template(name) for name in names))


def _known_cli_commands(metadata: Mapping[str, Any]) -> set[str]:
    commands = metadata.get("commands")
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)):
        raise AdapterError("invalid CLI help metadata", {"field": "commands"})
    known: set[str] = set()
    for item in commands:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            known.add(item["name"])
    return known


def _command_metadata(
    pipelines: tuple[PipelineConfig, ...], command_metadata: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if command_metadata is None:
        phases = sorted({phase for pipeline in pipelines for phase in pipeline.phase_ids})
        command_metadata = adapter_command_metadata(phases)
    cli_commands = _known_cli_commands(command_metadata)
    for command in ADAPTER_COMMANDS:
        if command.cli_command not in cli_commands:
            raise AdapterError(
                "adapter command is absent from CLI metadata",
                {"command": command.cli_command},
            )

    return command_metadata


@dataclass(frozen=True, slots=True)
class WorkflowSkill:
    name: str
    source: SourceInput
    frontmatter: str


@dataclass(frozen=True, slots=True)
class AdapterSources:
    harnesses: tuple[str, ...]
    pipelines: tuple[PipelineConfig, ...]
    instructions: SourceInput | None
    skills: tuple[WorkflowSkill, ...]
    templates: Mapping[str, SourceInput]
    command_help: Mapping[str, str]
    inputs: tuple[SourceInput, ...]


def capture_workflow_sources(
    root: Path, registry: PipelineRegistry | Callable[[Path], PipelineRegistry], command_metadata: Mapping[str, Any] | None,
    *, include_manifest_inputs: bool = True,
) -> AdapterSources:
    """Validate a registry snapshot and capture workflow inputs for the selected harnesses.

    A caller's reads before supplying the registry are outside this guarantee.
    Render-only still validates graphs but skips bytes needed only for provenance.
    """
    harnesses = load_selection(root)
    selection = SourceInput("adapter-selection", SELECTION_PATH, selection_bytes(harnesses))
    if callable(registry):
        registry = registry(root)
    if not harnesses:
        return AdapterSources(harnesses=(), pipelines=(), instructions=None, skills=(),
                              templates={}, command_help={}, inputs=(selection,))
    context = FieldContext(registry.path, root)

    @cache
    def read(path: Path) -> bytes:
        # Declarations have their own guards. Recheck the resolved file on its
        # first read, including validator reads performed inside graph parsing.
        label = path.relative_to(root).as_posix()
        checked = context.workflow_path(label, "adapter-source")
        if checked != path:
            raise AdapterError("workflow source location changed during capture", {"path": label})
        return checked.read_bytes()

    pipelines = registry.load_adapter_pipelines(root, read_bytes=read)
    label = "workflow/instructions.md"
    instructions = _workflow_text(
        "repository-instructions", label, context.workflow_path(label, "instructions"), read,
    )
    skills: dict[str, WorkflowSkill] = {}
    dependencies: set[Path] = set()
    for pipeline in pipelines:
        for phase in pipeline.phases:
            if phase.skill not in skills:
                source = _workflow_text("canonical-skill", phase.skill_source, phase.skill_path, read)
                lines = source.content.decode("utf-8").splitlines()
                frontmatter = "\n".join(lines[1:lines.index("---", 1)])
                skills[phase.skill] = WorkflowSkill(phase.skill, source, frontmatter)
            for path in (phase.output_template_path, phase.validator.resolved_path):
                if path is not None:
                    dependencies.add(path)

    command_templates = [f"command-{name}.md" for name in harnesses if name in COMMAND_PATHS]
    metadata = _command_metadata(pipelines, command_metadata) if command_templates else {}
    command_help = {entry["name"]: entry["help"] for entry in metadata.get("commands", ())
                    if isinstance(entry, Mapping) and isinstance(entry.get("name"), str)
                    and isinstance(entry.get("help"), str)}
    release = capture_release_inputs((*COMMON_TEMPLATES, *command_templates))
    templates = {
        source.path.rsplit("/", 1)[-1]: source for source in release if source.kind == "release-template"
    }
    inputs = []
    if include_manifest_inputs:
        inputs = [
            selection, instructions,
            *release,
            SourceInput("validated-registry", registry.path.relative_to(root).as_posix(),
                        registry.canonical_json.encode("utf-8")),
        ]
        if metadata:
            inputs.append(SourceInput("cli-help-metadata", "@cli-help-metadata", canonical_json_bytes(metadata)))
        inputs.extend(skill.source for skill in skills.values())
        for pipeline in pipelines:
            inputs.append(SourceInput(
                "validated-pipeline", pipeline.path.relative_to(root).as_posix(), pipeline.canonical_json.encode("utf-8"),
            ))
        for path in sorted(dependencies):
            label = path.relative_to(root).as_posix()
            try:
                inputs.append(SourceInput("pipeline-dependency", label, read(path)))
            except OSError as exc:
                raise AdapterError("cannot read pipeline dependency", {"path": label}) from exc
    return AdapterSources(
        harnesses, pipelines, instructions, tuple(skills[name] for name in sorted(skills)),
        templates, command_help, tuple(sorted(inputs, key=lambda source: source.path)),
    )


def _workflow_text(kind: str, label: str, path: Path, read: Callable[[Path], bytes]) -> SourceInput:
    try:
        text = read(path).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError) as exc:
        raise AdapterError("cannot read canonical adapter source", {"path": label}) from exc
    return SourceInput(kind, label, (text.rstrip("\n") + "\n").encode("utf-8"))
