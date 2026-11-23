"""Internal manifest/event durability protocol for already authorized run paths.

The run store owns path authorization and domain decisions. This component owns
serialization, event reconciliation, and ordered manifest replacement/event append.
Locked helpers never acquire a lock; their caller must hold the run lock.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from ..hashing import sha256_json
from ..locking import RunLock
from .run_errors import RunCorruptionError
from .run_records import EVENT_SCHEMA_VERSION, EventRecord, RunRecord
from . import run_validation


class RunPersistence:
    """Implement manifest and event IO without workflow or artifact policies."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        timestamp: Callable[[], str],
        fault: Callable[[str], None],
    ) -> None:
        self._clock = clock
        self._timestamp = timestamp
        self._fault = fault

    def lock(self, directory: Path) -> RunLock:
        """Return a lock for a path already authorized by the run store."""
        return RunLock(directory / ".lock", clock=self._clock)

    @contextmanager
    def locked(
        self, directory: Path, run_id: str, *, gap: Literal["recover", "inspect", "reject"] = "recover"
    ) -> Iterator[tuple[RunRecord, list[EventRecord]]]:
        """Hold one lock across loading, reconciliation, and the caller's changes.

        Returning from this context does not commit implicitly. The caller must
        explicitly advance a revision and commit a mutation, so idempotent returns
        and artifact-only writes do not emit extra revisions or events. Creation
        uses lock() separately because no manifest exists yet.
        """
        with self.lock(directory):
            manifest = self._read_manifest(directory, run_id)
            events = self._read_events(directory, run_id)
            if self._needs_recovery(events, manifest):
                if gap == "reject":
                    raise RunCorruptionError(
                        "manifest is newer than its final audit event; recovery is required",
                        run_id=run_id, details={"recoverable": True},
                    )
                if gap == "recover":
                    event = self._event(
                        manifest, sequence=len(events) + 1, event_type="recovery",
                        visit_number=manifest["current_visit"],
                        payload={"reason": "manifest-event-gap", "previous_sequence": len(events),
                                 "previous_manifest_revision": len(events)},
                    )
                    self._append_event(directory, run_id, run_validation.serialize_event(event, run_id))
                    events.append(event)
            yield manifest, events

    def advance_revision(self, manifest: RunRecord, previous_revision: int) -> None:
        """Stamp a mutation at the caller's established clock boundary."""
        manifest["revision"] = previous_revision + 1
        manifest["updated_at"] = self._timestamp()

    def _read_manifest(self, directory: Path, run_id: str) -> RunRecord:
        path = directory / "run.json"
        try:
            raw = path.read_text(encoding="utf-8")
            value = json.loads(raw)
        except (OSError, ValueError, RecursionError) as exc:
            raise RunCorruptionError(
                "run manifest is missing, unreadable, or malformed",
                run_id=run_id,
                details={"path": str(path), "error": str(exc)},
            ) from exc
        if not isinstance(value, dict):
            raise RunCorruptionError(
                "run manifest must be a JSON object", run_id=run_id
            )
        run_validation.validate_manifest(value, run_id)
        return value

    def _write_manifest_atomic(
        self, directory: Path, manifest: RunRecord
    ) -> None:
        target = directory / "run.json"
        self._fault("before-manifest-temporary-write")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=directory, prefix=".run.json.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    manifest,
                    stream,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    indent=2,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._fault("after-manifest-temporary-write")
            self._fault("before-manifest-replace")
            os.replace(temporary, target)
            self._fsync_directory(directory)
            self._fault("after-manifest-replace")
        finally:
            temporary.unlink(missing_ok=True)

    def _append_event(self, directory: Path, run_id: str, payload: bytes) -> None:
        path = directory / "events.jsonl"
        self._fault("before-event-append")
        try:
            with path.open("ab") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise RunCorruptionError(
                "could not append the run audit event",
                run_id=run_id,
                details={"path": str(path), "error": str(exc)},
            ) from exc
        self._fault("after-event-append")

    def _read_events(self, directory: Path, run_id: str) -> list[EventRecord]:
        path = directory / "events.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").split("\n")
            if lines[-1] == "":
                lines.pop()
        except (OSError, UnicodeError) as exc:
            raise RunCorruptionError(
                "run event log is missing or unreadable",
                run_id=run_id,
                details={"path": str(path), "error": str(exc)},
            ) from exc
        events: list[EventRecord] = []
        for index, line in enumerate(lines, 1):
            if not line:
                raise RunCorruptionError(
                    "run event log contains an empty record",
                    run_id=run_id,
                    details={"line": index},
                )
            try:
                event = json.loads(line)
            except (ValueError, RecursionError) as exc:
                raise RunCorruptionError(
                    "run event log contains malformed JSON",
                    run_id=run_id,
                    details={"line": index, "error": str(exc)},
                ) from exc
            if not isinstance(event, dict):
                raise RunCorruptionError(
                    "run event must be a JSON object",
                    run_id=run_id,
                    details={"line": index},
                )
            run_validation.validate_event(event, run_id)
            if event["sequence"] != index:
                raise RunCorruptionError(
                    "run event sequence is not contiguous",
                    run_id=run_id,
                    details={"line": index, "sequence": event["sequence"]},
                )
            if event["manifest_revision"] != index:
                raise RunCorruptionError(
                    "run event revisions are not contiguous",
                    run_id=run_id,
                    details={
                        "line": index,
                        "manifest_revision": event["manifest_revision"],
                    },
                )
            events.append(event)
        return events

    @staticmethod
    def _needs_recovery(events: list[EventRecord], manifest: RunRecord) -> bool:
        last_revision = events[-1]["manifest_revision"] if events else 0
        if last_revision == manifest["revision"] - 1:
            return True
        if (last_revision == manifest["revision"]
                and events[-1]["manifest_hash"] == sha256_json(manifest)):
            return False
        raise RunCorruptionError(
            "manifest and event log disagree in a way that cannot be recovered",
            run_id=manifest["run_id"],
            details={
                "manifest_revision": manifest["revision"],
                "last_event_revision": last_revision,
            },
        )

    def commit_locked(
        self,
        directory: Path,
        manifest: RunRecord,
        events: list[EventRecord],
        event_type: str,
        visit_number: int | None,
        payload: dict[str, Any],
    ) -> None:
        """Replace the manifest then append its event under the caller's lock.

        There is deliberately no lock acquisition or revision stamping here;
        creation commits revision 1, while mutations stamp at their existing
        clock boundary. A failure after replacement leaves the permitted gap.
        """
        run_id = directory.name
        run_validation.validate_manifest(manifest, run_id)
        event = self._event(
            manifest,
            sequence=len(events) + 1,
            event_type=event_type,
            visit_number=visit_number,
            payload=payload,
        )
        serialized = run_validation.serialize_event(event, run_id)
        self._write_manifest_atomic(directory, manifest)
        self._append_event(directory, run_id, serialized)

    def _event(
        self,
        manifest: RunRecord,
        *,
        sequence: int,
        event_type: str,
        visit_number: int | None,
        payload: dict[str, Any],
    ) -> EventRecord:
        return {
            "schema_version": EVENT_SCHEMA_VERSION,
            "sequence": sequence,
            "timestamp": self._timestamp(),
            "run_id": manifest["run_id"],
            "visit_number": visit_number,
            "type": event_type,
            "payload": payload,
            "manifest_revision": manifest["revision"],
            "manifest_hash": sha256_json(manifest),
        }

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
