"""Repository-owned registrations for independently configured pipelines."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from ._config.config_errors import PipelineConfigError
from ._config.config_fields import FieldContext
from ._config.config_loader import IDENTIFIER_PATTERN, _Loader, load_pipeline, read_pipeline_document
from ._config.config_models import PipelineConfig
from ._config.skill_sources import SkillBindings


REGISTRY_PATH = "workflow/pipelines.toml"
PIPELINE_PATH_PATTERN = re.compile(r"^pipelines/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.toml$")


@dataclass(frozen=True, slots=True)
class PipelineRegistration:
    id: str
    path: Path
    declared_path: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineRegistry:
    path: Path
    repository_root: Path
    pipelines: tuple[PipelineRegistration, ...]

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "pipelines": [
                    {"id": item.id, "path": item.path.relative_to(self.path.parent).as_posix()}
                    for item in self.pipelines
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def load(self, pipeline_id: str) -> PipelineConfig:
        for registration in self.pipelines:
            if registration.id == pipeline_id:
                return self._check_id(registration, load_pipeline(registration.path, self.repository_root))
        raise PipelineConfigError(
            "unknown-pipeline",
            f"pipeline {pipeline_id!r} is not registered",
            path=self.path,
            field="pipelines.id",
            value=pipeline_id,
            remediation="choose a registered ID: " + ", ".join(item.id for item in self.pipelines),
        )

    def load_all(self) -> tuple[PipelineConfig, ...]:
        return tuple(self.load(item.id) for item in self.pipelines)

    def _check_id(self, item: PipelineRegistration, pipeline: PipelineConfig) -> PipelineConfig:
        if pipeline.id != item.id:
            raise PipelineConfigError(
                "pipeline-id-mismatch", "registered ID differs from pipeline ID",
                path=self.path, field="pipelines.id", value=item.id,
                remediation="make the registration and pipeline IDs agree",
            )
        return pipeline

    def load_adapter_pipelines(
        self, repository_root: Path, *, read_bytes: Callable[[Path], bytes] = Path.read_bytes,
    ) -> tuple[PipelineConfig, ...]:
        """Consume a registry snapshot after checking its sources, without reparsing it."""
        root = repository_root.resolve()
        context = FieldContext(self.path, root)
        if self.repository_root != root or self.path != root / REGISTRY_PATH:
            context.fail("unsafe-path", "registry does not belong to the adapter root",
                         field="registry", value=str(self.path),
                         remediation="load the workflow registry from the selected repository")
        context.workflow_path(REGISTRY_PATH, "registry")
        for item in self.pipelines:
            declared = item.declared_path
            if declared is None and item.path.is_relative_to(self.path.parent):
                declared = item.path.relative_to(self.path.parent).as_posix()
            if not isinstance(declared, str) or not PIPELINE_PATH_PATTERN.fullmatch(declared):
                context.fail("unsafe-pipeline-path", "invalid registered graph location",
                             field="pipelines.path", value=declared,
                             remediation="use a registered TOML file under workflow/pipelines/")
            resolved = context.workflow_path(declared, "pipelines.path", base=self.path.parent)
            if resolved != item.path or not resolved.is_relative_to(self.path.parent / "pipelines"):
                context.fail("unsafe-pipeline-path", "registered graph location has changed",
                             field="pipelines.path", value=declared,
                             remediation="restore the registered graph or reload the registry")
        documents = [(item, read_pipeline_document(item.path, read_bytes=read_bytes)) for item in self.pipelines]
        migrations = {}
        for item, raw in documents:
            phases = raw.get("phases")
            if isinstance(phases, list):
                missing = [phase.get("id") for phase in phases
                           if isinstance(phase, Mapping) and "skill_source" not in phase]
                if missing:
                    migrations[item.id] = missing
        if migrations:
            context.fail(
                "missing-skill-source", "adapter generation requires explicit skill_source declarations",
                field="skill_source", value=migrations,
                remediation="set skill_source to a workflow file for every listed pipeline and phase",
            )

        bindings = SkillBindings()
        pipelines = []
        for item, raw in documents:
            loader = _Loader(item.path, root, read_bytes=read_bytes)
            pipeline = self._check_id(item, loader.parse(raw, adapter_bindings=bindings))
            pipelines.append(pipeline)
        # Check all declarations for aliases before reading any skill body.
        for pipeline in pipelines:
            bindings.validate_metadata(FieldContext(pipeline.path, root, read_bytes=read_bytes), pipeline.phases)
        return tuple(pipelines)


def load_registry(repository_root: str | Path) -> PipelineRegistry:
    """Validate the mandatory registry without loading unrelated phase graphs."""
    return _load_registry(repository_root, workflow_only=False)


def load_adapter_registry(repository_root: str | Path) -> PipelineRegistry:
    """Guard registry and registration locations before adapter configuration reads."""
    return _load_registry(repository_root, workflow_only=True)


def _load_registry(repository_root: str | Path, *, workflow_only: bool) -> PipelineRegistry:
    root = Path(repository_root).expanduser().resolve()
    path = root / REGISTRY_PATH
    context = FieldContext(path, root)
    source = context.workflow_path(REGISTRY_PATH, "registry") if workflow_only else path

    def fail(code: str, message: str, field: str, value: object = None) -> NoReturn:
        raise PipelineConfigError(
            code,
            message,
            path=path,
            field=field,
            value=value,
            remediation="use schema_version = 1 and unique [[pipelines]] id/path entries under workflow/pipelines/",
        )

    try:
        if not path.resolve().is_relative_to(root):
            fail("unsafe-registry-path", "registry resolves outside the repository", "registry")
        with source.open("rb") as stream:
            raw = tomllib.load(stream)
    except (OSError, ValueError, RuntimeError) as exc:
        fail("invalid-registry", f"cannot load mandatory registry: {exc}", "registry")
    if set(raw) != {"schema_version", "pipelines"}:
        fail("invalid-registry-fields", "registry requires only schema_version and pipelines", "registry")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        fail("unsupported-schema-version", "registry schema_version must be 1", "schema_version", raw["schema_version"])
    entries = raw["pipelines"]
    if not isinstance(entries, list) or not entries:
        fail("empty-registry", "pipelines must be a nonempty array of tables", "pipelines")
    registrations: list[PipelineRegistration] = []
    ids: set[str] = set()
    paths: set[Path] = set()
    directory = root / "workflow" / "pipelines"
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "path"}:
            fail("invalid-registration", "registration requires only id and path", "pipelines", entry)
        pipeline_id = entry["id"]
        if not isinstance(pipeline_id, str) or not IDENTIFIER_PATTERN.fullmatch(pipeline_id):
            fail("invalid-identifier", "pipeline ID must be lowercase kebab-case", "pipelines.id", pipeline_id)
        if pipeline_id in ids:
            fail("duplicate-pipeline-id", "pipeline IDs must be unique", "pipelines.id", pipeline_id)
        declared = entry["path"]
        if not isinstance(declared, str):
            fail("unsafe-pipeline-path", "pipeline path must be a relative TOML path", "pipelines.path", declared)
        if not PIPELINE_PATH_PATTERN.fullmatch(declared):
            fail("unsafe-pipeline-path", "pipeline path must be under pipelines/", "pipelines.path", declared)
        try:
            resolved = (context.workflow_path(declared, "pipelines.path", base=path.parent)
                        if workflow_only else (path.parent / declared).resolve())
        except (OSError, ValueError, RuntimeError) as exc:
            fail("unsafe-pipeline-path", f"pipeline path cannot be resolved: {exc}", "pipelines.path", declared)
        if not resolved.is_relative_to(directory) or not resolved.is_relative_to(root):
            fail("unsafe-pipeline-path", "pipeline path escapes workflow/pipelines/", "pipelines.path", declared)
        if not resolved.is_file():
            fail("missing-pipeline", "registered pipeline file does not exist", "pipelines.path", declared)
        if resolved in paths:
            fail("duplicate-pipeline-path", "pipeline paths must be unique", "pipelines.path", declared)
        ids.add(pipeline_id)
        paths.add(resolved)
        registrations.append(PipelineRegistration(pipeline_id, resolved, declared))
    return PipelineRegistry(path, root, tuple(sorted(registrations, key=lambda item: item.id)))
