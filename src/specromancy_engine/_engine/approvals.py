"""Pure approval selectors, integrity checks, and detached state changes.

Callers supply timestamps and observations; decisions run against locked state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .engine_errors import EngineError
from ..exit_codes import ExitCode
from .._runs.run_records import ApprovalRecord, RunRecord, VisitRecord, current_visit, latest_approval


def build_approval_record(
    *,
    run_id: str,
    phase_id: str,
    visit_number: int,
    reason: str,
    details: str | None,
    kind: str = "transition",
    artifact_sha256: str | None = None,
    pipeline_sha256: str,
    outcome: str | None = None,
    requested_at: str,
) -> ApprovalRecord:
    record: ApprovalRecord = {
        "run_id": run_id,
        "phase_id": phase_id,
        "visit_number": visit_number,
        "reason": reason,
        "details": details,
        "kind": kind,
        "pipeline_sha256": pipeline_sha256,
        "status": "pending",
        "decision": None,
        "actor": None,
        "requested_at": requested_at,
        "decided_at": None,
    }
    if kind == "transition":
        if artifact_sha256 is None or outcome is None:
            raise ValueError("transition approval needs an artifact hash and outcome")
        record.update(artifact_sha256=artifact_sha256, outcome=outcome)
    return record


def approval_integrity_errors(
    approval: ApprovalRecord, *, artifact_sha256: str, pipeline_sha256: str
) -> list[str]:
    """Return stable mismatch labels for an approval's bound inputs."""

    errors: list[str] = []
    if approval.get("kind") != "action" and approval.get("artifact_sha256") != artifact_sha256:
        errors.append("artifact")
    if approval.get("pipeline_sha256") != pipeline_sha256:
        errors.append("pipeline")
    return errors


def pending_approval(manifest: RunRecord, visit_number: int) -> ApprovalRecord | None:
    return latest_approval(manifest, "pending", visit_number=visit_number)


def approved_record(manifest: RunRecord, visit_number: int) -> ApprovalRecord | None:
    return next((a for a in reversed(manifest["approvals"])
                 if a.get("visit_number") == visit_number and a.get("status") == "approved"
                 and a.get("kind") == "transition"), None)


def approved_for_phase(manifest: RunRecord, phase_id: str) -> ApprovalRecord | None:
    return next(
        (
            item
            for item in reversed(manifest["approvals"])
            if item.get("phase_id") == phase_id and item.get("status") == "approved"
            and item.get("kind") == "transition"
        ),
        None,
    )


def requested_state(
    manifest: RunRecord,
    approval: ApprovalRecord,
    *,
    validation_checks: list[dict[str, Any]],
    command_results: list[dict[str, Any]],
    mutation_result: dict[str, Any] | None,
) -> RunRecord:
    """Return a detached pending state using already collected evidence."""

    updated = copy.deepcopy(manifest)
    current = current_visit(updated)
    assert current is not None
    current["status"] = "awaiting-approval"
    if approval.get("kind") != "action":
        current["validation_checks"] = copy.deepcopy(validation_checks)
        current["mutation_result"] = copy.deepcopy(mutation_result)
        current["command_results"] = copy.deepcopy(command_results)
    updated["status"] = "awaiting-approval"
    updated["approvals"].append(copy.deepcopy(approval))
    return updated


COMMON_FIELDS = (
    "run_id", "visit_number", "phase_id", "reason", "details", "requested_at",
    "pipeline_sha256",
)
IDENTITY_FIELDS = COMMON_FIELDS + ("outcome", "artifact_sha256")


@dataclass
class ApprovalDecision:
    """A detached approval result; absent event means no durable change."""

    manifest: RunRecord
    approval: ApprovalRecord
    disposition: str
    event_type: str | None = None
    visit_number: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def stale_error(approval: ApprovalRecord, mismatches: list[str]) -> EngineError:
    return EngineError(
        ExitCode.APPROVAL_REQUIRED, "approval request is stale because its artifact or pipeline changed",
        "stale-approval", phase=approval["phase_id"], visit_number=approval["visit_number"],
        mismatches=mismatches,
    )


def conflict(observed: ApprovalRecord) -> EngineError:
    return EngineError(
        ExitCode.ILLEGAL_TRANSITION,
        "approval state changed before the command could be applied",
        "approval-state-changed",
        run_id=observed.get("run_id"), phase=observed.get("phase_id"),
        visit_number=observed.get("visit_number"),
    )


def require_binding(manifest: RunRecord, observed: ApprovalRecord) -> VisitRecord:
    """Reject incomplete identities or a mismatched containing run/visit."""

    kind = observed.get("kind")
    fields = COMMON_FIELDS if kind == "action" else IDENTITY_FIELDS
    if (kind not in {"transition", "action"} or any(key not in observed for key in fields)
            or manifest["pipeline"]["sha256"] != observed["pipeline_sha256"]):
        raise conflict(observed)
    visits = [v for v in manifest["visits"]
              if v["ordinal"] == observed["visit_number"]]
    if (manifest["run_id"] != observed["run_id"] or len(visits) != 1
            or visits[0]["phase_id"] != observed["phase_id"]):
        raise conflict(observed)
    if kind == "action" and (
        not isinstance(observed["details"], str) or not observed["details"].strip()
        or "artifact_sha256" in observed or "outcome" in observed
    ):
        raise conflict(observed)
    return visits[0]


def _matches(
    record: ApprovalRecord, observed: ApprovalRecord, *, creation: bool = False,
) -> bool:
    if record.get("kind") != observed.get("kind"):
        return False
    fields = COMMON_FIELDS if observed.get("kind") == "action" else IDENTITY_FIELDS
    return all(key in record and record[key] == observed[key]
               for key in fields if not (creation and key == "requested_at"))


def _eligible(
    manifest: RunRecord, visit: VisitRecord, *, creation: bool = False,
) -> bool:
    statuses = ("active", "awaiting-approval") if creation else ("awaiting-approval",)
    return (
        manifest["current_visit"] == visit["ordinal"]
        and manifest["status"] == visit["status"]
        and visit["status"] in statuses
    )


def request_decision(
    manifest: RunRecord, approval: ApprovalRecord, *,
    validation_checks: list[dict[str, Any]], command_results: list[dict[str, Any]],
    mutation_result: dict[str, Any] | None, expected_revision: int | None = None,
) -> ApprovalDecision:
    """Resolve pending requests before considering a replay or a new request."""

    visit = require_binding(manifest, approval)
    if not _eligible(manifest, visit, creation=True):
        raise conflict(approval)
    pending = pending_approval(manifest, visit["ordinal"])
    if pending is not None:
        if not _matches(pending, approval, creation=True):
            raise conflict(approval)
        return ApprovalDecision(manifest, pending, "pending")

    is_action = approval.get("kind") == "action"
    if is_action:
        if visit["status"] != "active":
            raise conflict(approval)
        for record in reversed(manifest["approvals"]):
            if (_matches(record, approval, creation=True)
                    and record.get("status") in {"approved", "declined"}):
                return ApprovalDecision(manifest, record, "decided")
    elif (approved_record(manifest, visit["ordinal"]) is not None
          or expected_revision is not None and manifest["revision"] != expected_revision):
        raise conflict(approval)

    updated = requested_state(
        manifest, approval, validation_checks=validation_checks,
        command_results=command_results, mutation_result=mutation_result,
    )
    payload = {"reason": approval["reason"]}
    if is_action:
        payload["request_number"] = len(updated["approvals"])
    else:
        payload["outcome"] = approval["outcome"]
    return ApprovalDecision(
        updated, updated["approvals"][-1], "requested", "approval-requested",
        visit["ordinal"], payload,
    )


def _identified(
    manifest: RunRecord, observed: ApprovalRecord, request_number: int | None = None,
) -> tuple[VisitRecord, ApprovalRecord]:
    visit = require_binding(manifest, observed)
    pending = latest_approval(manifest, "pending", visit_number=manifest["current_visit"])
    records = manifest["approvals"]
    if request_number is None:
        matches = [a for a in records if _matches(a, observed)]
        if len(matches) != 1:
            raise conflict(observed)
        record = matches[0]
    else:
        if not 1 <= request_number <= len(records):
            raise conflict(observed)
        record = records[request_number - 1]
        if not _matches(record, observed):
            raise conflict(observed)
    if pending is not None and record is not pending:
        raise conflict(observed)
    return visit, record


def action_decision(
    manifest: RunRecord, observed: ApprovalRecord, request_number: int, *,
    status: str, decided_at: str,
) -> ApprovalDecision:
    updated = copy.deepcopy(manifest)
    visit, record = _identified(updated, observed, request_number)
    if updated["current_visit"] != visit["ordinal"] or record.get("kind") != "action":
        raise conflict(observed)
    if record["status"] == status and updated["status"] == visit["status"] == "active":
        return ApprovalDecision(updated, record, "decided")
    if record["status"] != "pending" or not _eligible(updated, visit):
        raise conflict(observed)
    record.update(status=status, decision=status, actor="user", decided_at=decided_at)
    updated["status"] = visit["status"] = "active"
    event = "approval-granted" if status == "approved" else "approval-declined"
    return ApprovalDecision(updated, record, "decided", event, visit["ordinal"],
                            {"request_number": request_number, "actor": "user"})


def grant_decision(
    manifest: RunRecord, observed: ApprovalRecord, *,
    transition_target: str | None, decided_at: str | None, request_number: int | None = None,
) -> ApprovalDecision:
    """Grant exactly the observed request; None permits only existing grants."""

    updated = copy.deepcopy(manifest)
    visit, record = _identified(updated, observed, request_number)
    if record.get("kind") == "action":
        raise conflict(observed)
    if record.get("status") == "approved" and visit["status"] == "completed":
        if (visit["chosen_outcome"] != record["outcome"]
                or visit["transition_target"] != transition_target):
            raise conflict(observed)
        return ApprovalDecision(updated, copy.deepcopy(record), "completed")
    if not _eligible(updated, visit):
        raise conflict(observed)
    if record.get("status") == "approved":
        return ApprovalDecision(updated, copy.deepcopy(record), "granted")
    if record.get("status") != "pending" or decided_at is None:
        raise conflict(observed)
    record.update(status="approved", decision="approved", actor="user", decided_at=decided_at)
    return ApprovalDecision(
        updated, copy.deepcopy(record), "granted", "approval-granted",
        visit["ordinal"], {"phase_id": visit["phase_id"], "actor": "user"},
    )


def invalidate_decision(
    manifest: RunRecord, observed: ApprovalRecord, *, decided_at: str,
    mismatches: list[str], request_number: int | None = None,
) -> ApprovalDecision:
    """Invalidate only the eligible observed request, including stale retries."""

    updated = copy.deepcopy(manifest)
    visit, record = _identified(updated, observed, request_number)
    if record.get("status") == "stale" and record.get("decision") == "invalidated":
        later = updated["approvals"][updated["approvals"].index(record) + 1:]
        if (_eligible(updated, visit, creation=True)
                and not any(a.get("visit_number") == visit["ordinal"] for a in later)):
            return ApprovalDecision(updated, copy.deepcopy(record), "stale")
        raise conflict(observed)
    if not _eligible(updated, visit):
        raise conflict(observed)
    if record.get("status") not in ("pending", "approved"):
        raise conflict(observed)
    record.update(status="stale", decision="invalidated", actor="system", decided_at=decided_at)
    payload = {"mismatches": list(mismatches)}
    if record.get("kind") == "action":
        updated["status"] = visit["status"] = "active"
        payload["request_number"] = updated["approvals"].index(record) + 1
    return ApprovalDecision(
        updated, copy.deepcopy(record), "stale", "approval-invalidated",
        visit["ordinal"], payload,
    )
