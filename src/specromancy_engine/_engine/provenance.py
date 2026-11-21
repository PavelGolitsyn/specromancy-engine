"""Observe pipeline and prepared resource identity without choosing a policy."""

from __future__ import annotations

from typing import Any

from .engine_errors import EngineError
from ..exit_codes import ExitCode
from .._config.config_models import PipelineConfig
from ..hashing import relative_path, sha256_file
from .._runs.run_records import RunRecord


def observe_provenance(
    pipeline: PipelineConfig, manifest: RunRecord
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    workflow_phases = {p.id: p for p in pipeline.phases if p.skill_source is not None}
    for visit in manifest["visits"]:
        phase = workflow_phases.get(visit["phase_id"])
        for kind in ("skill", "template"):
            record = visit[kind]
            if record is None:
                continue
            path = pipeline.repository_root / record["path"]
            if phase is not None:
                current = phase.skill_path if kind == "skill" else phase.output_template_path
                if current != path:
                    warnings.append({
                        "code": "provenance-path-mismatch",
                        "message": f"visit {visit['ordinal']} {kind} resolves to a different file",
                        "details": {"path": record["path"]},
                    })
                    continue
            try:
                actual = sha256_file(path)
            except OSError as exc:
                warnings.append(
                    {
                        "code": "provenance-missing",
                        "message": f"visit {visit['ordinal']} {kind} provenance is missing",
                        "details": {"path": record["path"], "error": str(exc)},
                    }
                )
                continue
            if actual != record["sha256"]:
                warnings.append(
                    {
                        "code": "provenance-hash-mismatch",
                        "message": f"visit {visit['ordinal']} {kind} changed after preparation",
                        "details": {
                            "path": record["path"],
                            "expected": record["sha256"],
                            "actual": actual,
                        },
                    }
                )
    return warnings


def require_provenance(pipeline: PipelineConfig, manifest: RunRecord) -> None:
    warnings = observe_provenance(pipeline, manifest)
    if warnings:
        warning = warnings[0]
        raise EngineError(
            ExitCode.INTERNAL_ERROR, warning["message"], warning["code"],
            **warning.get("details", {}),
        )


def pipeline_matches(pipeline: PipelineConfig, manifest: RunRecord) -> bool:
    return manifest["pipeline"] == pipeline_identity(pipeline)


def pipeline_identity(pipeline: PipelineConfig) -> dict[str, Any]:
    return {
        "id": pipeline.id,
        "version": pipeline.version,
        "path": relative_path(pipeline.path, pipeline.repository_root),
        "sha256": pipeline.config_hash,
    }
