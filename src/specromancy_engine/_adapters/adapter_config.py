"""User-owned, adapter-only selection and its canonical manifest input."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .adapter_contracts import HARNESS_MODES
from .._config.config_errors import PipelineConfigError
from .._config.config_fields import FieldContext
from ..hashing import canonical_json_bytes

SELECTION_KIND = "adapter-selection"
SELECTION_PATH = "workflow/adapters.toml"


def selection_bytes(harnesses: tuple[str, ...]) -> bytes:
    return canonical_json_bytes({"schema_version": 1, "harnesses": sorted(harnesses)})


def load_selection(root: Path) -> tuple[str, ...]:
    context = FieldContext(root / SELECTION_PATH, root)
    guidance = (f"choose from {', '.join(sorted(HARNESS_MODES))} in {SELECTION_PATH}, for example:\n"
                'schema_version = 1\nharnesses = ["claude"]')
    try:
        source = context.workflow_path(SELECTION_PATH, "adapters")
    except PipelineConfigError as exc:
        if exc.diagnostic_code != "missing-file":
            raise
        context.fail("missing-file", f"adapter generation requires {SELECTION_PATH}. {guidance}",
                     field="adapters", remediation=guidance)
    try:
        with source.open("rb") as stream:
            raw = tomllib.load(stream)
    except (ValueError, OSError) as exc:
        context.fail("invalid-adapter-config", f"cannot read {SELECTION_PATH}: {exc}",
                     field="adapters", remediation=guidance)
    context.check_unknown(raw, {"schema_version", "harnesses"})
    if context.require_integer(raw.get("schema_version"), "schema_version") != 1:
        context.fail("unsupported-schema-version", "adapter schema_version must be 1",
                     field="schema_version", remediation=guidance)
    harnesses = context.string_list(raw.get("harnesses"), "harnesses")
    unknown = sorted(set(harnesses) - HARNESS_MODES.keys())
    if unknown:
        context.fail("unknown-harness", "unknown adapter harness", field="harnesses",
                     value=unknown, remediation=guidance)
    return tuple(sorted(harnesses))
