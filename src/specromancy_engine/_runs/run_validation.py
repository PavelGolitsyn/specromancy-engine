"""Validate current persisted records before reconciliation or publication."""

from __future__ import annotations

from typing import Any

from ..hashing import SHA256_PATTERN, canonical_json_bytes, normalize_relative_path
from .record_fields import nonblank, positive_integer, validate_approval, validate_timestamp
from .run_errors import RunCorruptionError, RunStoreError
from .run_identity import is_valid_run_id
from .run_records import (
    EVENT_SCHEMA_VERSION, EVENT_TYPE_PATTERN, RUN_SCHEMA_VERSION,
    RUN_STATUSES, VISIT_STATUSES, EventRecord, RunRecord, VisitRecord,
)


def validate_version(record: dict, surface: str, expected: int, run_id: str) -> None:
    version = record.get("schema_version")
    if not positive_integer(version):
        raise RunCorruptionError(f"{surface} schema_version must be a positive integer", run_id=run_id)
    if version != expected:
        raise RunStoreError(
            f"unsupported {surface} schema version {version}, expected {expected}. "
            "Use the engine that produced the run or start a new run.",
            diagnostic_code="unsupported-schema-version",
            details={"run_id": run_id, "surface": surface,
                     "observed_version": version, "expected_version": expected},
        )


def record_bytes(value: dict, surface: str, run_id: str) -> bytes:
    try:
        return canonical_json_bytes(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise RunCorruptionError(f"{surface} is not JSON serializable: {exc}", run_id=run_id) from exc


def validate_manifest(value: dict[str, Any], run_id: str) -> None:
    validate_version(value, "run", RUN_SCHEMA_VERSION, run_id)
    if value.keys() != RunRecord.__required_keys__:
        invalid_manifest(run_id, "manifest fields do not match the schema")
    if not positive_integer(value["revision"]):
        invalid_manifest(run_id, "manifest revision must be positive")
    if value["run_id"] != run_id or not is_valid_run_id(value["run_id"]):
        invalid_manifest(run_id, "manifest run ID is invalid")
    if not isinstance(value["status"], str) or value["status"] not in RUN_STATUSES:
        invalid_manifest(run_id, "manifest status is invalid")
    validate_timestamp(value["created_at"], run_id)
    validate_timestamp(value["updated_at"], run_id)
    pipeline = value["pipeline"]
    if not isinstance(pipeline, dict) or set(pipeline) != {
        "id",
        "version",
        "path",
        "sha256",
    }:
        invalid_manifest(run_id, "pipeline record is invalid")
    if (
        not nonblank(pipeline["id"])
        or not positive_integer(pipeline["version"])
        or not isinstance(pipeline["sha256"], str)
        or not SHA256_PATTERN.fullmatch(pipeline["sha256"])
    ):
        invalid_manifest(run_id, "pipeline provenance is invalid")
    validate_path(pipeline["path"], run_id)
    validate_artifact_record(value["request"], run_id, hash_required=True)
    if not isinstance(value["git"], dict) or set(value["git"]) != {"base", "head"}:
        invalid_manifest(run_id, "git metadata is invalid")
    if not isinstance(value["visits"], list):
        invalid_manifest(run_id, "visits must be a list")
    attempts: dict[str, int] = {}
    for expected_ordinal, visit in enumerate(value["visits"], 1):
        if not isinstance(visit, dict):
            invalid_manifest(run_id, "visit record must be an object")
        validate_visit(visit, run_id, expected_ordinal)
        phase_id = visit["phase_id"]
        attempts[phase_id] = attempts.get(phase_id, 0) + 1
        if visit["attempt"] != attempts[phase_id]:
            invalid_manifest(run_id, "visit attempt is not ordered")
    current = value["current_visit"]
    if current is not None and (
        not positive_integer(current) or current > len(value["visits"])
    ):
        invalid_manifest(run_id, "current visit is invalid")
    if not isinstance(value["approvals"], list) or not all(
        isinstance(item, dict) for item in value["approvals"]
    ):
        invalid_manifest(run_id, "approvals must be an ordered object list")
    pending_visits = set()
    for approval in value["approvals"]:
        validate_approval(approval, value)
        if approval["status"] == "pending":
            ordinal = approval["visit_number"]
            if ordinal in pending_visits:
                invalid_manifest(run_id, "visit has multiple pending approvals")
            pending_visits.add(ordinal)
    record_bytes(value, "manifest", run_id)


def validate_visit(
    visit: dict[str, Any], run_id: str, expected_ordinal: int
) -> None:
    if visit.keys() != VisitRecord.__required_keys__:
        invalid_manifest(run_id, "visit fields do not match the schema")
    if (
        not nonblank(visit["phase_id"])
        or not positive_integer(visit["ordinal"])
        or visit["ordinal"] != expected_ordinal
        or not positive_integer(visit["attempt"])
        or not isinstance(visit["status"], str)
        or visit["status"] not in VISIT_STATUSES
    ):
        invalid_manifest(run_id, "visit identity or status is invalid")
    if visit["mutation_policy"] not in ("read-only", "repository-write", "allowlist"):
        invalid_manifest(run_id, "visit mutation policy is invalid")
    for name in ("chosen_outcome", "transition_target"):
        if visit[name] is not None and not nonblank(visit[name]):
            invalid_manifest(run_id, f"visit {name} must be null or a nonblank string")
    if not isinstance(visit["inputs"], list):
        invalid_manifest(run_id, "visit inputs must be a list")
    for record in visit["inputs"]:
        validate_artifact_record(record, run_id, hash_required=True, reference=True)
    validate_artifact_record(
        visit["output"], run_id, hash_required=visit["status"] == "completed"
    )
    if visit["status"] != "completed" and visit["output"]["sha256"] is not None:
        invalid_manifest(run_id, "mutable visit output cannot have a sealed hash")
    for name in ("validation_checks", "command_results", "deviations"):
        if not isinstance(visit[name], list):
            invalid_manifest(run_id, f"visit {name} must be a list")
    if not isinstance(visit["skill"], dict):
        invalid_manifest(run_id, "visit skill provenance is invalid")
    validate_provenance(visit["skill"], run_id)
    if visit["template"] is not None:
        if not isinstance(visit["template"], dict):
            invalid_manifest(run_id, "visit template provenance is invalid")
        validate_provenance(visit["template"], run_id)
    if visit["started_at"] is not None:
        validate_timestamp(visit["started_at"], run_id)
    if visit["status"] != "pending" and visit["started_at"] is None:
        invalid_manifest(run_id, "started visit lacks a start timestamp")
    if visit["completed_at"] is not None:
        validate_timestamp(visit["completed_at"], run_id)
    if visit["status"] == "completed" and visit["completed_at"] is None:
        invalid_manifest(run_id, "completed visit lacks a completion timestamp")


def validate_artifact_record(
    value: Any,
    run_id: str,
    *,
    hash_required: bool,
    reference: bool = False,
) -> None:
    fields = {"path", "sha256", "reference"} if reference else {"path", "sha256"}
    if not isinstance(value, dict) or set(value) != fields:
        invalid_manifest(run_id, "artifact record is invalid")
    validate_path(value["path"], run_id)
    digest = value["sha256"]
    if hash_required and (
        not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest)
    ):
        invalid_manifest(run_id, "artifact hash is invalid")
    if not hash_required and digest is not None:
        invalid_manifest(run_id, "artifact hash must be null until sealed")
    if reference and not nonblank(value["reference"]):
        invalid_manifest(run_id, "artifact reference is invalid")


def validate_provenance(value: dict[str, Any], run_id: str) -> None:
    if set(value) != {"path", "sha256"}:
        invalid_manifest(run_id, "provenance record is invalid")
    validate_path(value["path"], run_id)
    if not isinstance(value["sha256"], str) or not SHA256_PATTERN.fullmatch(
        value["sha256"]
    ):
        invalid_manifest(run_id, "provenance hash is invalid")


def validate_event(event: dict[str, Any], run_id: str) -> None:
    serialize_event(event, run_id)


def serialize_event(event: dict[str, Any], run_id: str) -> bytes:
    validate_version(event, "event", EVENT_SCHEMA_VERSION, run_id)
    if event.keys() != EventRecord.__required_keys__:
        raise RunCorruptionError("event fields do not match the schema", run_id=run_id)
    if (
        event["run_id"] != run_id
        or not is_valid_run_id(run_id)
        or not positive_integer(event["sequence"])
        or not positive_integer(event["manifest_revision"])
        or not isinstance(event["type"], str)
        or not EVENT_TYPE_PATTERN.fullmatch(event["type"])
        or not isinstance(event["payload"], dict)
        or not isinstance(event["manifest_hash"], str)
        or not SHA256_PATTERN.fullmatch(event["manifest_hash"])
    ):
        raise RunCorruptionError("event record is invalid", run_id=run_id)
    visit_number = event["visit_number"]
    if visit_number is not None and not positive_integer(visit_number):
        raise RunCorruptionError("event visit number is invalid", run_id=run_id)
    validate_timestamp(event["timestamp"], run_id)
    if event["type"] in ("approval-requested", "approval-granted", "approval-declined",
                         "approval-invalidated"):
        if visit_number is None:
            raise RunCorruptionError("approval event requires a visit number", run_id=run_id)
        validate_approval_payload(event["type"], event["payload"], run_id)
    return record_bytes(event, "event", run_id) + b"\n"


def validate_approval_payload(event_type: str, payload: dict, run_id: str) -> None:
    kind = payload.get("kind")
    if kind not in ("action", "transition"):
        raise RunCorruptionError("approval event kind is invalid", run_id=run_id)
    fields = {"kind"}
    if kind == "action":
        fields.add("request_number")
        if not positive_integer(payload.get("request_number")):
            raise RunCorruptionError("action event requires a positive request number", run_id=run_id)
    if event_type == "approval-requested":
        fields.add("reason")
        valid = nonblank(payload.get("reason"))
        if kind == "transition":
            fields.add("outcome")
            valid = valid and nonblank(payload.get("outcome"))
    elif event_type == "approval-invalidated":
        fields.add("mismatches")
        allowed = (["pipeline"],) if kind == "action" else (
            ["artifact"], ["pipeline"], ["artifact", "pipeline"],
        )
        valid = payload.get("mismatches") in allowed
    else:
        fields.add("actor")
        valid = payload.get("actor") == "user"
        if kind == "transition":
            fields.add("phase_id")
            valid = valid and event_type == "approval-granted" and nonblank(payload.get("phase_id"))
    if not valid or payload.keys() != fields:
        raise RunCorruptionError(f"invalid {kind} {event_type} payload", run_id=run_id)


def validate_path(value: Any, run_id: str) -> None:
    if not isinstance(value, str):
        raise RunCorruptionError("persisted path is invalid", run_id=run_id)
    try:
        normalize_relative_path(value)
    except ValueError as exc:
        raise RunCorruptionError("persisted path is unsafe", run_id=run_id) from exc


def invalid_manifest(run_id: str, message: str) -> None:
    raise RunCorruptionError(message, run_id=run_id)
