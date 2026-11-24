"""Public pipeline configuration records, loader and drift diagnostic."""

from __future__ import annotations

from ._config.config_errors import PipelineConfigError
from ._config.config_loader import load_pipeline
from ._config.config_models import (
    PhaseConfig,
    PipelineConfig,
    TransitionConfig,
    ValidationCommand,
    ValidatorConfig,
)


def require_pipeline_hash(pipeline: PipelineConfig, expected_hash: str) -> None:
    """Reject configuration drift for a persisted in-progress run."""

    if pipeline.config_hash != expected_hash:
        raise PipelineConfigError(
            "pipeline-hash-mismatch",
            "pipeline configuration changed after the run was created",
            path=pipeline.path,
            field="config_hash",
            value={"expected": expected_hash, "actual": pipeline.config_hash},
            remediation="finish with the producing engine and original workflow resources or start a new run",
        )
