"""Coordinate approval requests, grants, invalidation, and continuation.

The caller supplies a strictly loaded manifest for requests. Grants deliberately
load persisted state here before checking bindings, so drift can be audited.
Validation collects evidence and records expected failures through an explicit
collaborator; successful evidence is committed with the request or transition.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import responses
from .approvals import (
    ApprovalDecision, action_decision, approval_integrity_errors, approved_for_phase, approved_record,
    build_approval_record, conflict, grant_decision, invalidate_decision,
    pending_approval, request_decision, require_binding, stale_error,
)
from ..artifacts import ArtifactError, artifact_record, verify_manifest_artifacts
from .command_decisions import declared_reason, illegal_transition, select_outcome
from .._config.config_models import PhaseConfig, PipelineConfig
from .engine_errors import EngineError
from ..errors import UsageError
from ..git import GitError
from ..exit_codes import ExitCode
from .provenance import require_provenance
from .._runs.run_records import ApprovalRecord, RunRecord, VisitRecord, current_visit
from .._runs.record_fields import positive_integer
from ..run_store import RunStore
from .validation_service import ValidationResult, check_visit_mutation


class ApprovalService:
    """Own approval ordering with explicit validation and timestamp seams."""

    def __init__(
        self,
        pipeline: PipelineConfig,
        store: RunStore,
        *,
        validate: Callable[[RunRecord, VisitRecord, PhaseConfig], ValidationResult],
        timestamp: Callable[[], str],
    ) -> None:
        self.pipeline = pipeline
        self.store = store
        self._perform_validation = validate
        self._timestamp = timestamp

    def invalidate_approval(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        approval: ApprovalRecord,
        mismatches: list[str],
    ) -> None:
        decided_at = self._timestamp()

        self.store.decide_approval(
            manifest["run_id"],
            lambda value: invalidate_decision(
                value, approval, decided_at=decided_at, mismatches=mismatches,
                request_number=manifest["approvals"].index(approval) + 1,
            ),
        )

    def advance_approved(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        approval: ApprovalRecord,
    ) -> dict[str, Any]:
        require_binding(manifest, approval)
        if self.pipeline.config_hash != approval["pipeline_sha256"]:
            self.require_integrity(manifest, visit, approval)
        transition = next((
            item for item in self.pipeline.phase(visit["phase_id"]).transitions
            if item.outcome == approval["outcome"]
        ), None)
        decision = self.store.decide_approval(
            manifest["run_id"], lambda value: grant_decision(
                value, approval, transition_target=transition.target if transition else None,
                decided_at=None, request_number=manifest["approvals"].index(approval) + 1,
            ),
        )
        manifest, approval = decision.manifest, decision.approval
        if decision.disposition == "completed":
            return responses.response_for_state(
                self.pipeline, manifest, "approval was already recorded"
            )
        visit = current_visit(manifest)
        self.require_integrity(manifest, visit, approval)
        if transition is None:
            raise conflict(approval)
        phase = self.pipeline.phase(visit["phase_id"])
        evidence = self._perform_validation(manifest, visit, phase)
        updated = self.store.transition_visit(
            manifest["run_id"],
            self.pipeline,
            visit["ordinal"],
            expected_revision=manifest["revision"], expected_status="awaiting-approval",
            approval=approval,
            outcome=approval["outcome"],
            transition_target=transition.target,
            terminal_result={
                "outcome": approval["outcome"],
                "phase": phase.id,
                "visit_number": visit["ordinal"],
                "approval_reason": approval["reason"],
            },
            validation_checks=evidence.checks,
            mutation_result=evidence.mutation_result,
            command_results=evidence.command_results,
        )
        return responses.after_transition(self.pipeline, updated, approval["outcome"])

    def request_approval(
        self,
        manifest: RunRecord,
        *,
        reason: str | None,
        details: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        run_id = manifest["run_id"]
        visit = current_visit(manifest)
        if visit is None or visit["status"] not in {"active", "awaiting-approval"}:
            raise illegal_transition("only an active visit can request approval", manifest)
        phase = self.pipeline.phase(visit["phase_id"])
        reasons = phase.transition_approval_conditions + phase.action_approval_conditions
        chosen_reason = declared_reason(reason, reasons, "approval")
        pending = pending_approval(manifest, visit["ordinal"])
        if pending is not None:
            require_binding(manifest, pending)
            if pending["reason"] != chosen_reason or pending["details"] != details:
                raise conflict(pending)

        is_action = chosen_reason in phase.action_approval_conditions
        evidence = ValidationResult([], [], None)
        selected_outcome = output_hash = None
        if is_action:
            if not details or not details.strip():
                raise UsageError("an action approval requires nonblank --details")
            if outcome is not None:
                raise UsageError("an action approval cannot select --outcome")
        else:
            selected_outcome = select_outcome(phase, outcome)
            if pending:
                try:
                    output_hash = self.artifact_hash(manifest, visit)
                except EngineError as exc:
                    raise conflict(pending) from exc
                if selected_outcome != pending["outcome"] or output_hash != pending["artifact_sha256"]:
                    raise conflict(pending)
            else:
                approved = approved_record(manifest, visit["ordinal"])
                if approved is not None:
                    return self.advance_approved(manifest, visit, approved)
                evidence = self._perform_validation(manifest, visit, phase)
                output_hash = evidence.checks[0]["sha256"]

        approval = build_approval_record(
            run_id=run_id, phase_id=phase.id, visit_number=visit["ordinal"],
            reason=chosen_reason, details=details, kind="action" if is_action else "transition",
            artifact_sha256=output_hash, pipeline_sha256=self.pipeline.config_hash,
            outcome=selected_outcome, requested_at=self._timestamp(),
        )

        def request(value: RunRecord) -> ApprovalDecision:
            decision = request_decision(
                value, approval, validation_checks=evidence.checks,
                mutation_result=evidence.mutation_result, command_results=evidence.command_results,
                expected_revision=manifest["revision"],
            )
            if pending is not None and decision.event_type:
                raise conflict(pending)
            if is_action and decision.event_type:
                self.check_action_permission(value, visit, phase)
            elif decision.event_type and self.artifact_hash(value, visit) != output_hash:
                raise conflict(approval)
            return decision

        decision = self.store.decide_approval(run_id, request)
        if decision.disposition == "decided":
            return self.action_result(decision)
        return responses.approval_response(
            self.pipeline, decision.manifest, decision.approval,
            "approval is required" if decision.disposition == "requested"
            else "approval is already pending",
        )

    def action_result(self, decision: ApprovalDecision) -> dict[str, Any]:
        number = decision.manifest["approvals"].index(decision.approval) + 1
        return responses.response_for_state(
            self.pipeline, decision.manifest, f"action {number} was {decision.approval['status']}",
        )

    def check_action_permission(
        self, manifest: RunRecord, visit: VisitRecord, phase: PhaseConfig,
    ) -> None:
        verify_manifest_artifacts(manifest, self.store.run_directory(manifest["run_id"]))
        require_provenance(self.pipeline, manifest)
        try:
            check_visit_mutation(self.pipeline, visit, phase)
        except GitError as exc:
            raise EngineError(
                ExitCode.VALIDATION_FAILED, exc.message, exc.diagnostic_code, **exc.details,
            ) from exc

    def decide(
        self, run_id: str, phase_id: str, request_number: int | None, status: str,
    ) -> dict[str, Any]:
        # Load the saved graph binding first so a stale request can be audited.
        manifest = self.store.load(run_id)
        visit = current_visit(manifest)
        pending = pending_approval(manifest, visit["ordinal"]) if visit else None
        if request_number is not None:
            if not positive_integer(request_number) or request_number > len(manifest["approvals"]):
                raise illegal_transition("approval request number does not exist", manifest)
            approval = manifest["approvals"][request_number - 1]
            if approval.get("phase_id") != phase_id or (pending and pending is not approval):
                raise conflict(approval)
        elif pending is not None and pending["phase_id"] == phase_id:
            approval = pending
            if approval.get("kind") == "action":
                raise UsageError("an action decision requires --request N")
        elif pending is not None or status == "declined":
            raise illegal_transition("phase has no matching pending approval", manifest)
        elif visit and visit["phase_id"] == phase_id and visit["status"] == "awaiting-approval":
            approved = approved_record(manifest, visit["ordinal"])
            if approved is None:
                raise illegal_transition("visit has no pending approval request", manifest)
            return self.advance_approved(manifest, visit, approved)
        else:
            return self.idempotent_approval_result(manifest, phase_id)

        bound_visit = require_binding(manifest, approval)
        is_action = approval.get("kind") == "action"
        if not is_action and status == "declined":
            raise illegal_transition("only an action approval can be declined", manifest)
        if is_action and (bound_visit is not visit or approval["status"] not in ("pending", status)):
            raise conflict(approval)
        if approval["status"] == "stale":
            raise conflict(approval)
        self.require_integrity(manifest, bound_visit, approval)

        decided_at = self._timestamp()
        if is_action:
            assert request_number is not None

            def decide_action(value: RunRecord) -> ApprovalDecision:
                result = action_decision(
                    value, approval, request_number, status=status, decided_at=decided_at,
                )
                if status == "approved" and result.event_type:
                    self.check_action_permission(value, bound_visit, self.pipeline.phase(phase_id))
                return result

            decision = self.store.decide_approval(run_id, decide_action)
            return self.action_result(decision)

        require_provenance(self.pipeline, manifest)
        transition = next((
            item for item in self.pipeline.phase(phase_id).transitions
            if item.outcome == approval["outcome"]
        ), None)
        if transition is None:
            raise conflict(approval)
        decision = self.store.decide_approval(
            run_id, lambda value: grant_decision(
                value, approval, decided_at=decided_at, transition_target=transition.target,
                request_number=request_number,
            ),
        )
        if decision.disposition == "completed":
            return responses.response_for_state(
                self.pipeline, decision.manifest, "approval was already recorded"
            )
        return self.advance_approved(
            decision.manifest, current_visit(decision.manifest), decision.approval,
        )

    def require_integrity(
        self, manifest: RunRecord, visit: VisitRecord, approval: ApprovalRecord,
    ) -> None:
        current_hash = ""
        if approval.get("kind") != "action":
            try:
                current_hash = self.artifact_hash(manifest, visit)
            except EngineError:
                pass
        mismatches = approval_integrity_errors(
            approval, artifact_sha256=current_hash, pipeline_sha256=self.pipeline.config_hash,
        )
        if mismatches:
            self.invalidate_approval(manifest, visit, approval, mismatches)
            raise stale_error(approval, mismatches)

    def artifact_hash(
        self, manifest: RunRecord, visit: VisitRecord
    ) -> str:
        try:
            return artifact_record(
                self.store.run_directory(manifest["run_id"]),
                visit["output"]["path"],
            )["sha256"]
        except (ArtifactError, OSError) as exc:
            details = dict(getattr(exc, "details", None) or {"error": str(exc)})
            details.pop("error_code", None)
            raise EngineError(
                ExitCode.VALIDATION_FAILED,
                "output artifact is missing or unreadable",
                "invalid-output",
                **details,
            ) from exc

    def idempotent_approval_result(
        self, manifest: RunRecord, phase_id: str
    ) -> dict[str, Any]:
        approved = approved_for_phase(manifest, phase_id)
        if approved is None:
            raise illegal_transition(
                f"phase {phase_id!r} has no pending approval", manifest
            )
        return responses.response_for_state(
            self.pipeline, manifest, "approval was already recorded"
        )
