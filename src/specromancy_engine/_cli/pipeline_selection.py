"""Select registered initialization graphs or an existing run's saved provenance."""

from __future__ import annotations

import argparse
from pathlib import Path

from .._config.config_loader import load_pipeline
from .._config.config_models import PipelineConfig
from ..errors import UsageError
from ..registry import PipelineRegistry
from ..run_store import RunStore


def selected_pipeline(
    arguments: argparse.Namespace, root: Path, registry: PipelineRegistry
) -> PipelineConfig:
    selector = getattr(arguments, "pipeline", None)
    if arguments.command == "init":
        if selector is None:
            raise UsageError("init requires --pipeline ID; there is no default pipeline")
        return registry.load(selector)

    saved = RunStore(root).read_pipeline(arguments.run_id)
    path = root / saved["path"]
    if selector is not None and selector != saved["id"]:
        raise UsageError("--pipeline must match the run's recorded pipeline ID")
    return load_pipeline(path, root)
