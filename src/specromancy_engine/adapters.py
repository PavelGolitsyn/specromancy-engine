"""Deterministic, safely owned adapters for supported agent harnesses."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ._adapters.adapter_contracts import (
    ADAPTER_COMMANDS, ADAPTER_SCHEMA_VERSION, GENERATOR_VERSION, HARNESS_MODES,
    MANIFEST_PATH, REGENERATION_COMMAND, AdapterCommand, AdapterError,
)
from ._adapters.adapter_ownership import _compare, _has_drift, write_adapters
from ._adapters.adapter_rendering import render_workflow_sources, workflow_manifest
from ._adapters.adapter_sources import capture_workflow_sources
from .contracts import RESPONSE_SCHEMA_VERSION
from .exit_codes import ExitCode
from .hashing import canonical_json_bytes
from .registry import PipelineRegistry, load_adapter_registry


def generate_adapters(
    repository_root: Path,
    registry: PipelineRegistry,
    command_metadata: Mapping[str, Any] | None = None,
    *,
    check: bool = False,
) -> dict[str, Any]:
    """Generate adapters or compare the worktree to deterministic output.

    Omitted metadata is derived from the graphs captured for this invocation.
    Command wrappers include explicit caller-supplied metadata in their source hash.
    """

    return _generate_adapters(repository_root.resolve(strict=True), registry, command_metadata, check=check)


def _generate_adapters(
    root: Path, registry: PipelineRegistry | Callable[[Path], PipelineRegistry] = load_adapter_registry,
    command_metadata: Mapping[str, Any] | None = None, *, check: bool,
) -> dict[str, Any]:
    sources = capture_workflow_sources(root, registry, command_metadata)
    rendered = render_workflow_sources(sources)
    manifest = workflow_manifest(sources, rendered)
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"

    if check:
        drift = _compare(root, rendered, manifest_bytes, sources.harnesses)
        if _has_drift(drift):
            raise AdapterError("generated adapter drift detected", drift)
        return _result(
            "generated adapters are up to date",
            checked=True,
            paths=tuple(rendered),
            canonical_source_sha256=manifest["canonical_source"]["sha256"],
        )

    removed = write_adapters(root, rendered, manifest_bytes, sources.harnesses)
    return _result(
        f"generated {len(rendered)} harness adapter files",
        checked=False,
        paths=tuple(rendered),
        canonical_source_sha256=manifest["canonical_source"]["sha256"],
        removed=removed,
    )


def render_adapters(
    repository_root: Path,
    registry: PipelineRegistry,
    command_metadata: Mapping[str, Any],
) -> dict[str, bytes]:
    """Render the selected adapter files in stable path order."""

    root = repository_root.resolve(strict=True)
    sources = capture_workflow_sources(
        root, registry, command_metadata, include_manifest_inputs=False
    )
    return render_workflow_sources(sources)


def _result(
    message: str,
    *,
    checked: bool,
    paths: tuple[str, ...],
    canonical_source_sha256: str,
    removed: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "kind": "adapters",
        "code": int(ExitCode.SUCCESS),
        "message": message,
        "adapters": {
            "checked": checked,
            "manifest": MANIFEST_PATH,
            "canonical_source_sha256": canonical_source_sha256,
            "paths": list(paths),
            "removed": list(removed),
        },
    }
