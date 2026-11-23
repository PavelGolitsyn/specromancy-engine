"""Stored record vocabulary and side-effect-free selectors.

Selectors borrow records from their argument; they neither copy nor mutate.
RunStore remains responsible for defensive copies at its public boundaries.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from ..exit_codes import ExitCode
from .run_errors import RunStoreError


RUN_SCHEMA_VERSION = 2
EVENT_SCHEMA_VERSION = 2
EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RUN_STATUSES = frozenset(
    {"active", "awaiting-agent", "awaiting-approval", "paused", "completed", "failed", "blocked"}
)
VISIT_STATUSES = frozenset(
    {"pending", "active", "awaiting-approval", "completed", "failed", "blocked"}
)


class ArtifactRecord(TypedDict):
    path: str
    sha256: str | None


class SealedArtifactRecord(TypedDict):
    path: str
    sha256: str


class InputArtifactRecord(SealedArtifactRecord):
    reference: str


class PipelineRecord(SealedArtifactRecord):
    id: str
    version: int


class GitRecord(TypedDict):
    base: Any
    head: Any


class ApprovalBinding(TypedDict):
    run_id: str
    phase_id: str
    visit_number: int
    reason: str
    pipeline_sha256: str
    status: Literal["pending", "approved", "declined", "stale"]
    decision: Literal["approved", "declined", "invalidated"] | None
    actor: Literal["user", "system"] | None
    requested_at: str
    decided_at: str | None


class ActionApproval(ApprovalBinding):
    kind: Literal["action"]
    details: str


class TransitionApproval(ApprovalBinding):
    kind: Literal["transition"]
    details: str | None
    artifact_sha256: str
    outcome: str


ApprovalRecord = ActionApproval | TransitionApproval


class VisitRecord(TypedDict):
    phase_id: str
    ordinal: int
    attempt: int
    status: str
    inputs: list[InputArtifactRecord]
    output: ArtifactRecord
    mutation_policy: str
    mutation_baseline: Any
    mutation_result: Any
    validation_checks: list[Any]
    command_results: list[Any]
    chosen_outcome: str | None
    transition_target: str | None
    skill: SealedArtifactRecord
    template: SealedArtifactRecord | None
    started_at: str | None
    completed_at: str | None
    deviations: list[Any]


class RunRecord(TypedDict):
    schema_version: int
    revision: int
    run_id: str
    pipeline: PipelineRecord
    status: str
    current_visit: int | None
    request: SealedArtifactRecord
    git: GitRecord
    created_at: str
    updated_at: str
    visits: list[VisitRecord]
    approvals: list[ApprovalRecord]
    terminal_result: Any
    block_reason: Any


class EventRecord(TypedDict):
    schema_version: int
    sequence: int
    timestamp: str
    run_id: str
    visit_number: int | None
    type: str
    payload: dict[str, Any]
    manifest_revision: int
    manifest_hash: str


def current_visit(manifest: RunRecord) -> VisitRecord | None:
    """Find the current ordinal, including completed visits; tolerate no match."""

    ordinal = manifest["current_visit"]
    if ordinal is None:
        return None
    return next(
        (visit for visit in manifest["visits"] if visit["ordinal"] == ordinal),
        None,
    )


def latest_approval(
    manifest: RunRecord, status: str, *, visit_number: int | None = None
) -> ApprovalRecord | None:
    """Find the last matching approval; omitted visit means any visit."""

    return next(
        (
            approval
            for approval in reversed(manifest["approvals"])
            if (visit_number is None or approval.get("visit_number") == visit_number)
            and approval.get("status") == status
        ),
        None,
    )


def visit_by_number(manifest: RunRecord, visit_number: int) -> VisitRecord:
    for visit in manifest["visits"]:
        if visit["ordinal"] == visit_number:
            return visit
    raise RunStoreError(
        f"visit not found: {visit_number}",
        diagnostic_code="visit-not-found",
        details={"visit_number": visit_number},
        code=ExitCode.NOT_FOUND,
    )


def require_visit_revision(manifest: RunRecord, revision: int, ordinal: int, status: str) -> None:
    visit = current_visit(manifest)
    if (manifest["revision"] != revision or manifest["status"] != status
            or visit is None or visit["ordinal"] != ordinal or visit["status"] != status):
        raise RunStoreError(
            "visit changed before the command could be applied",
            diagnostic_code="visit-state-changed", code=ExitCode.ILLEGAL_TRANSITION,
            details={"visit_number": ordinal, "expected_revision": revision,
                     "revision": manifest["revision"]},
        )
