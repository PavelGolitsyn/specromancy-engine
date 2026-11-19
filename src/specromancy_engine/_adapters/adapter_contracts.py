"""Shared adapter contracts, re-exported by the public adapters facade."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .._config.config_fields import IDENTIFIER_PATTERN
from ..errors import SpecromancyError
from ..exit_codes import ExitCode


ADAPTER_SCHEMA_VERSION = 1
GENERATOR_VERSION = 2
MANIFEST_PATH = "adapters/manifest.json"
REGENERATION_COMMAND = "specromancy adapters generate"


@dataclass(frozen=True, slots=True)
class AdapterCommand:
    """A thin harness command that delegates to the stable CLI."""

    name: str
    cli_command: str
    arguments: str
    description: str


ADAPTER_COMMANDS = (
    AdapterCommand(
        "init",
        "init",
        "PIPELINE_ID DESCRIPTION",
        "Initialize a Specromancy run and return its recorded next action.",
    ),
    AdapterCommand(
        "resume",
        "resume",
        "RUN_ID",
        "Resume a Specromancy run from persisted state.",
    ),
    AdapterCommand(
        "status",
        "status",
        "RUN_ID",
        "Read a Specromancy run's persisted status and next command.",
    ),
    AdapterCommand(
        "phase",
        "phase",
        "RUN_ID PHASE",
        "Start or resume the named current phase and return its action packet.",
    ),
)

HARNESS_MODES = {
    "claude": "generated",
    "codex": "native",
    "copilot": "generated",
    "hermes": "native",
    "opencode": "generated",
}


class AdapterError(SpecromancyError):
    """Report adapter drift or an ownership conflict without unsafe writes."""

    def __init__(self, message: str, details: Mapping[str, Any]) -> None:
        super().__init__(ExitCode.ADAPTER_DRIFT, message, details)


def _target_for_path(path: str) -> str:
    if path.startswith(".agents/"):
        return "codex"
    if path.startswith(".claude/"):
        return "claude"
    if path.startswith(".github/"):
        return "copilot"
    if path.startswith(".opencode/"):
        return "opencode"
    raise AdapterError("generated path has no target harness", {"path": path})


# Generator v3 requirements. A path's consumers are independent of which other
# outputs happen to exist in a checkout.
WORKFLOW_SCHEMA_VERSION = 2
WORKFLOW_GENERATOR_VERSION = 3
INSTRUCTION_CONSUMERS = {
    "AGENTS.md": ("codex", "hermes", "opencode"),
    ".claude/CLAUDE.md": ("claude",),
    ".github/copilot-instructions.md": ("copilot",),
}
SKILL_CONSUMERS = {
    ".agents/skills": ("codex", "copilot", "hermes", "opencode"),
    ".claude/skills": ("claude",),
}
COMMAND_PATHS = {
    "claude": ".claude/commands/specromancy/{name}.md",
    "copilot": ".github/prompts/specromancy-{name}.prompt.md",
    "opencode": ".opencode/commands/specromancy-{name}.md",
}
_COMMAND_CONSUMERS = {
    pattern.format(name=command.name): (harness,)
    for harness, pattern in COMMAND_PATHS.items() for command in ADAPTER_COMMANDS
}


def consumers_for_path(path: str) -> tuple[str, ...]:
    if path in INSTRUCTION_CONSUMERS:
        return INSTRUCTION_CONSUMERS[path]
    if path in _COMMAND_CONSUMERS:
        return _COMMAND_CONSUMERS[path]
    parts = path.split("/")
    if len(parts) == 4 and parts[3] == "SKILL.md" and IDENTIFIER_PATTERN.fullmatch(parts[2]):
        return SKILL_CONSUMERS.get("/".join(parts[:2]), ())
    return ()


def target_records(paths: Iterable[str]) -> list[dict[str, Any]]:
    targets = []
    paths = sorted(paths)
    for name, mode in sorted(HARNESS_MODES.items()):
        required = [path for path in paths if name in consumers_for_path(path)]
        record = {"name": name, "mode": mode, "paths": required}
        if mode == "native":
            record["discovery_paths"] = [path for path in required if path.startswith(".agents/")]
        targets.append(record)
    return targets
