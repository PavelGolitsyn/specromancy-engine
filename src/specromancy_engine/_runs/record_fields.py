"""Shared field and approval binding checks for stored state and decisions."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, TypeGuard

from ..hashing import SHA256_PATTERN
from .run_errors import RunCorruptionError
from .run_records import ActionApproval, TransitionApproval, VisitRecord


TIMESTAMP_PATTERN = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z"


def positive_integer(value: Any) -> bool:
    return type(value) is int and value >= 1


def nonblank(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def validate_timestamp(value: Any, run_id: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(TIMESTAMP_PATTERN, value):
        raise RunCorruptionError("timestamp is invalid", run_id=run_id)
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise RunCorruptionError("timestamp is invalid", run_id=run_id) from exc


def validate_approval(record: dict, manifest: dict) -> VisitRecord:
    run_id = manifest["run_id"]
    kind = record.get("kind")
    variant = ActionApproval if kind == "action" else TransitionApproval
    if kind not in ("action", "transition") or record.keys() != variant.__required_keys__:
        raise RunCorruptionError("approval fields do not match its kind", run_id=run_id)

    number = record["visit_number"]
    if (record["run_id"] != run_id or not positive_integer(number)
            or number > len(manifest["visits"])
            or record["pipeline_sha256"] != manifest["pipeline"]["sha256"]):
        raise RunCorruptionError("approval binding is invalid", run_id=run_id)
    visit = manifest["visits"][number - 1]
    if (visit["ordinal"] != number or record["phase_id"] != visit["phase_id"]
            or not nonblank(record["reason"])):
        raise RunCorruptionError("approval phase or reason is invalid", run_id=run_id)
    if kind == "action":
        if not nonblank(record["details"]):
            raise RunCorruptionError("action approval requires nonblank details", run_id=run_id)
    elif (record["details"] is not None and not isinstance(record["details"], str)
          or not nonblank(record["outcome"]) or not isinstance(record["artifact_sha256"], str)
          or not SHA256_PATTERN.fullmatch(record["artifact_sha256"])):
        raise RunCorruptionError("transition approval details, outcome or digest is invalid", run_id=run_id)

    validate_timestamp(record["requested_at"], run_id)
    status = record["status"]
    if status == "pending":
        decision, actor = None, None
        if record["decided_at"] is not None:
            raise RunCorruptionError("pending approval has a decision timestamp", run_id=run_id)
    else:
        if status == "approved" or (status == "declined" and kind == "action"):
            decision, actor = status, "user"
        elif status == "stale":
            decision, actor = "invalidated", "system"
        else:
            raise RunCorruptionError("approval status is invalid", run_id=run_id)
        validate_timestamp(record["decided_at"], run_id)
    if (record["decision"], record["actor"]) != (decision, actor):
        raise RunCorruptionError("approval decision or actor disagrees with its status", run_id=run_id)
    return visit
