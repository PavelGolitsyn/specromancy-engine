"""Generic, deterministic state-machine execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._engine import responses
from ._engine.approval_service import ApprovalService
from ._engine.approvals import approved_record
from ._engine.command_decisions import (
    declared_reason, illegal_transition, select_outcome,
)
from .artifacts import ArtifactError, verify_manifest_artifacts
from ._config.config_models import PhaseConfig, PipelineConfig
from ._config.skill_sources import check_workflow_paths
from ._engine.engine_errors import EngineError
from .errors import UsageError
from .exit_codes import ExitCode
from .git import GitError, capture_repository_snapshot
from ._engine.provenance import observe_provenance, pipeline_identity, pipeline_matches, require_provenance
from .run_store import RunStore
from ._runs.run_identity import format_timestamp, utc_now
from ._runs.run_records import (
    RunRecord, VisitRecord, current_visit, require_visit_revision,
)
from ._engine.validation_service import ValidationResult, perform_validation


class Engine:
    """Advance runs using only configured outcomes and persisted state."""

    def __init__(
        self,
        pipeline: PipelineConfig,
        store: RunStore | None = None,
        *,
        command_fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.store = store or RunStore(pipeline.repository_root)
        self._command_fault_injector = command_fault_injector

    def initialize(self, description: str) -> dict[str, Any]:
        if not description.strip():
            raise UsageError("DESCRIPTION must not be empty")
        try:
            git = capture_repository_snapshot(
                self.pipeline.repository_root,
                allow_non_git=self.pipeline.allow_non_git,
            )
        except GitError as exc:
            raise EngineError(
                ExitCode.INVALID_PIPELINE,
                exc.message,
                exc.diagnostic_code,
                **exc.details,
            ) from exc
        manifest = self.store.create(
            self.pipeline,
            description,
            git_base=git,
            git_head=git,
        )
        visit = self.store.prepare_visit(
            manifest["run_id"], self.pipeline, self.pipeline.start
        )
        manifest = self.store.load(manifest["run_id"])
        return responses.action_response(
            self.pipeline,
            manifest,
            visit,
            f"run {manifest['run_id']} initialized; agent action is required",
        )

    def start_phase(self, run_id: str, phase_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "paused":
            return responses.paused_response(
                self.pipeline, manifest, "run is paused; resume it first"
            )
        visit = current_visit(manifest)
        if visit is None or visit["phase_id"] != phase_id:
            expected = visit["phase_id"] if visit is not None else None
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"cannot start phase {phase_id!r}; expected {expected!r}",
                "unexpected-phase",
                requested=phase_id,
                expected=expected,
                status=manifest["status"],
            )
        if visit["status"] == "pending":
            try:
                baseline = capture_repository_snapshot(
                    self.pipeline.repository_root,
                    allow_non_git=self.pipeline.allow_non_git,
                )
            except GitError as exc:
                raise EngineError(
                    ExitCode.VALIDATION_FAILED,
                    exc.message,
                    exc.diagnostic_code,
                    **exc.details,
                ) from exc
            visit = self.store.activate_visit(
                run_id,
                self.pipeline,
                visit["ordinal"],
                mutation_baseline=baseline,
            )
            manifest = self.store.load(run_id)
        elif visit["status"] != "active":
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"phase {phase_id!r} cannot start from {visit['status']}",
                "illegal-visit-status",
                phase=phase_id,
                status=visit["status"],
            )
        return responses.action_response(
            self.pipeline,
            manifest, visit, f"phase {phase_id} is active; agent action is required"
        )

    def validate(
        self,
        run_id: str,
        phase_id: str | None = None,
        *,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "completed":
            return responses.status_response(
                self.pipeline, manifest, "run is already completed"
            )
        if manifest["status"] == "paused":
            return responses.paused_response(
                self.pipeline, manifest, "run is paused; resume it first"
            )
        visit = current_visit(manifest)
        if visit is None:
            raise illegal_transition("run has no current visit", manifest)
        if visit["status"] == "pending":
            previous = manifest["visits"][-2] if len(manifest["visits"]) > 1 else None
            if previous is not None and previous["status"] == "completed" and (
                phase_id is None or phase_id == previous["phase_id"]
            ):
                return responses.action_response(
                    self.pipeline,
                    manifest,
                    visit,
                    "validation was already recorded; the next phase requires agent action",
                )
            raise illegal_transition(
                f"phase {visit['phase_id']!r} must be started before validation",
                manifest,
                expected_phase=visit["phase_id"],
            )
        if visit["status"] != "active":
            raise illegal_transition(
                f"visit cannot be validated from {visit['status']}", manifest
            )
        self._require_phase(visit, phase_id)
        phase = self.pipeline.phase(visit["phase_id"])
        selected = select_outcome(phase, outcome)
        transition = next(item for item in phase.transitions if item.outcome == selected)
        evidence = self._perform_validation(manifest, visit, phase)
        updated = self.store.transition_visit(
            run_id,
            self.pipeline,
            visit["ordinal"],
            expected_revision=manifest["revision"],
            outcome=selected,
            transition_target=transition.target,
            terminal_result={
                "outcome": selected,
                "phase": phase.id,
                "visit_number": visit["ordinal"],
            },
            validation_checks=evidence.checks,
            mutation_result=evidence.mutation_result,
            command_results=evidence.command_results,
        )
        return responses.after_transition(self.pipeline, updated, selected)

    def request_approval(
        self,
        run_id: str,
        *,
        reason: str | None,
        details: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load(run_id)
        return self._approval_service().request_approval(
            manifest, reason=reason, details=details, outcome=outcome
        )

    def approve(self, run_id: str, phase_id: str, *, request_number: int | None = None) -> dict[str, Any]:
        check_workflow_paths(self.pipeline)
        return self._approval_service().decide(run_id, phase_id, request_number, "approved")

    def decline(self, run_id: str, phase_id: str, *, request_number: int) -> dict[str, Any]:
        check_workflow_paths(self.pipeline)
        return self._approval_service().decide(run_id, phase_id, request_number, "declined")

    def block(
        self,
        run_id: str,
        *,
        reason: str | None,
        details: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "blocked":
            recorded = manifest["block_reason"] or {}
            if reason is not None and reason != recorded.get("reason"):
                raise illegal_transition(
                    "run is already blocked for a different reason", manifest
                )
            if details is not None and details != recorded.get("details"):
                raise illegal_transition(
                    "run is already blocked with different details", manifest
                )
            return responses.blocked_response(
                self.pipeline, manifest, "run is already blocked"
            )
        visit = current_visit(manifest)
        if visit is None or visit["status"] != "active":
            raise illegal_transition("only an active visit can be blocked", manifest)
        phase = self.pipeline.phase(visit["phase_id"])
        chosen_reason = declared_reason(reason, phase.stop_conditions, "stop")
        block = {
            "phase_id": phase.id,
            "visit_number": visit["ordinal"],
            "reason": chosen_reason,
            "details": details,
            "recorded_at": format_timestamp(utc_now()),
        }

        def change(value: RunRecord) -> None:
            require_visit_revision(value, manifest["revision"], visit["ordinal"], "active")
            current = current_visit(value)
            assert current is not None
            current["status"] = "blocked"
            value["status"] = "blocked"
            value["block_reason"] = block

        manifest = self.store.mutate(
            run_id,
            "run-blocked",
            change,
            visit_number=visit["ordinal"],
            payload={"reason": chosen_reason, "details": details},
        )
        return responses.blocked_response(self.pipeline, manifest, "run is blocked")

    def status(self, run_id: str) -> dict[str, Any]:
        check_workflow_paths(self.pipeline)
        manifest = self.store.load(run_id, verify_artifacts=False)
        warnings: list[dict[str, Any]] = []
        if not pipeline_matches(self.pipeline, manifest):
            warnings.append(
                {
                    "code": "pipeline-drift",
                    "message": "pipeline configuration differs from the run provenance",
                }
            )
        try:
            verify_manifest_artifacts(manifest, self.store.run_directory(run_id))
        except ArtifactError as exc:
            warnings.append(
                {
                    "code": exc.diagnostic_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            )
        warnings.extend(observe_provenance(self.pipeline, manifest))
        return responses.status_response(
            self.pipeline, manifest, "run status", warnings=warnings
        )

    def resume(self, run_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "paused":
            manifest = self.store.resume_paused(run_id, self.pipeline)
        return responses.response_for_state(self.pipeline, manifest, "run resumed")

    def run(self, run_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        visit = current_visit(manifest)
        if manifest["status"] == "awaiting-approval" and visit is not None:
            approved = approved_record(manifest, visit["ordinal"])
            if approved is not None:
                return self._approval_service().advance_approved(manifest, visit, approved)
        if visit is not None and visit["status"] == "pending":
            return self.start_phase(run_id, visit["phase_id"])
        return responses.response_for_state(
            self.pipeline, manifest, "run reached a boundary"
        )

    def _approval_service(self) -> ApprovalService:
        # Resolve validation and the engine clock at their original call sites,
        # including hooks replaced after a grant has committed.
        return ApprovalService(
            self.pipeline,
            self.store,
            validate=lambda manifest, visit, phase: self._perform_validation(
                manifest, visit, phase
            ),
            timestamp=lambda: format_timestamp(utc_now()),
        )

    def _load(self, run_id: str) -> RunRecord:
        check_workflow_paths(self.pipeline)
        manifest = self.store.load(run_id)
        if not pipeline_matches(self.pipeline, manifest):
            raise EngineError(
                ExitCode.INVALID_PIPELINE,
                "pipeline configuration changed after the run was created",
                "pipeline-hash-mismatch",
                expected=manifest["pipeline"],
                actual=pipeline_identity(self.pipeline),
            )
        require_provenance(self.pipeline, manifest)
        return manifest

    def _perform_validation(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        phase: PhaseConfig,
    ) -> ValidationResult:
        # Keep this orchestration seam for overlapping-attempt fault injection.
        result = perform_validation(
            self.pipeline,
            self.store.run_directory(manifest["run_id"]),
            visit,
            phase,
            command_fault_injector=self._command_fault_injector,
        )
        if result.failure is not None:
            self.store.record_validation_attempt(
                manifest["run_id"],
                visit["ordinal"],
                expected_revision=manifest["revision"],
                expected_status=visit["status"],
                validation_checks=result.checks,
                command_results=result.command_results,
                mutation_result=result.mutation_result,
                diagnostic={"error_code": result.failure.diagnostic_code},
            )
            raise result.failure from result.cause
        return result

    @staticmethod
    def _require_phase(visit: VisitRecord, requested: str | None) -> None:
        if requested is not None and requested != visit["phase_id"]:
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"requested phase {requested!r}; expected {visit['phase_id']!r}",
                "unexpected-phase",
                requested=requested,
                expected=visit["phase_id"],
            )
