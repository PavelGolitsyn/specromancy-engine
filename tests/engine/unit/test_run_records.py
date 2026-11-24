from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from specromancy_engine._runs import run_records
from specromancy_engine import run_store
from specromancy_engine._runs import run_validation
from specromancy_engine._engine.approvals import approved_record, pending_approval
from specromancy_engine.status import build_status, next_command
from tests.engine.contract.current_contract_support import RUN_ID, read_record


def manifest_at(state: str = "active") -> dict:
    return json.loads(read_record("states.json")[state]["run.json"])


class RecordValidationTests(unittest.TestCase):
    def test_invalid_status_shapes_raise_corruption_without_mutation(self) -> None:
        for path, message in ((("status",), "manifest status is invalid"),
                              (("visits", 0, "status"), "visit identity or status is invalid")):
            for invalid in (None, False, True, 0, 1, 1.5, "unknown", [], {}):
                with self.subTest(path=path, invalid=invalid):
                    value = manifest_at()
                    target = value
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = invalid
                    original = copy.deepcopy(value)
                    with self.assertRaises(run_store.RunCorruptionError) as raised:
                        run_validation.validate_manifest(value, RUN_ID)
                    self.assertEqual(str(raised.exception), message)
                    self.assertEqual(raised.exception.code, 12)
                    self.assertEqual(raised.exception.details,
                                     {"error_code": "corrupt-run", "run_id": RUN_ID})
                    self.assertEqual(value, original)

    def test_current_records_validate_without_mutation(self) -> None:
        for state, files in read_record("states.json").items():
            with self.subTest(state=state):
                manifest = json.loads(files["run.json"])
                original = copy.deepcopy(manifest)
                run_validation.validate_manifest(manifest, RUN_ID)
                self.assertEqual(manifest, original)
                for line in files["events.jsonl"].splitlines():
                    event = json.loads(line)
                    original_event = copy.deepcopy(event)
                    run_validation.validate_event(event, RUN_ID)
                    self.assertEqual(event, original_event)

    def test_required_and_extra_keys_are_rejected_at_closed_boundaries(self) -> None:
        paths = ((), ("pipeline",), ("git",), ("request",), ("visits", 0),
                 ("visits", 0, "inputs", 0), ("visits", 0, "output"),
                 ("visits", 0, "skill"))
        for path in paths:
            original = manifest_at()
            record = original
            for key in path:
                record = record[key]
            for missing in [*record, None]:
                value = copy.deepcopy(original)
                target = value
                for key in path:
                    target = target[key]
                if missing is None:
                    target["extra"] = None
                else:
                    del target[missing]
                with self.subTest(path=path, missing=missing):
                    with self.assertRaises(run_store.RunCorruptionError) as raised:
                        run_validation.validate_manifest(value, RUN_ID)
                    self.assertEqual(raised.exception.diagnostic_code, "corrupt-run")

    def test_invalid_records_keep_diagnostics(self) -> None:
        cases = [
            (("run_id",), "20261340T999999Z-01020304", "manifest run ID is invalid"),
            (("pipeline", "sha256"), "bad", "pipeline provenance is invalid"),
            (("request", "path"), "../request.md", "persisted path is unsafe"),
            (("request", "path"), "/absolute", "persisted path is unsafe"),
            (("request", "path"), "C:/drive", "persisted path is unsafe"),
            (("request", "path"), "a//b", "persisted path is unsafe"),
            (("request", "path"), "a/./b", "persisted path is unsafe"),
            (("request", "path"), "a\\b", "persisted path is unsafe"),
            (("request", "path"), None, "persisted path is invalid"),
            (("current_visit",), 2, "current visit is invalid"),
            (("visits", 0, "ordinal"), 2, "visit identity or status is invalid"),
            (("visits", 0, "attempt"), 2, "visit attempt is not ordered"),
            (("visits", 0, "output", "sha256"), "0" * 64, "artifact hash must be null until sealed"),
            (("visits", 0, "started_at"), None, "started visit lacks a start timestamp"),
            (("visits", 0, "skill", "sha256"), "bad", "provenance hash is invalid"),
            (("visits", 0, "template"), {}, "provenance record is invalid"),
            (("created_at",), "not-a-dateZ", "timestamp is invalid"),
            (("updated_at",), "2026-10-04T00:00:00+00:00", "timestamp is invalid"),
            (("approvals",), [None], "approvals must be an ordered object list"),
        ]
        for path, invalid, message in cases:
            value = manifest_at()
            target = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = invalid
            with self.subTest(path=path, invalid=invalid):
                with self.assertRaises(run_store.RunCorruptionError) as raised:
                    run_validation.validate_manifest(value, RUN_ID)
                self.assertEqual(str(raised.exception), message)
                self.assertEqual(raised.exception.details, {"error_code": "corrupt-run", "run_id": RUN_ID})
        completed = manifest_at("completed")
        completed["visits"][-1]["completed_at"] = None
        with self.assertRaisesRegex(run_store.RunCorruptionError, "completion timestamp"):
            run_validation.validate_manifest(completed, RUN_ID)
        completed["visits"][-1]["output"]["sha256"] = None
        with self.assertRaisesRegex(run_store.RunCorruptionError, "artifact hash is invalid"):
            run_validation.validate_manifest(completed, RUN_ID)

    def test_event_fields_identity_and_hash_are_checked(self) -> None:
        event = json.loads(read_record("states.json")["active"]["events.jsonl"].splitlines()[-1])
        invalid_fields = {"run_id": "20261004T000000Z-01020304", "sequence": 0,
                          "manifest_revision": 0, "manifest_hash": "bad",
                          "payload": [], "visit_number": 0, "type": "Bad_type",
                          "schema_version": True, "timestamp": "badZ"}
        cases = []
        for key in event:
            value = dict(event)
            del value[key]
            cases.append(value)
        cases.append({**event, "extra": None})
        cases.extend({**event, key: value} for key, value in invalid_fields.items())
        for value in cases:
            with self.subTest(value=value), self.assertRaises(run_store.RunCorruptionError) as raised:
                run_validation.validate_event(value, RUN_ID)
            self.assertEqual(raised.exception.diagnostic_code, "corrupt-run")

    def test_integer_tokens_required_for_all_counters_and_versions(self):
        # JSON Schema considers 2.0 integral and booleans distinct from numbers.
        # The wire format additionally requires integer tokens, even for 2e0.
        value = manifest_at("awaiting-approval")
        event = json.loads(read_record("states.json")["active"]["events.jsonl"].splitlines()[-1])
        for record, validator, paths in (
            (value, run_validation.validate_manifest,
             [("schema_version",), ("revision",), ("current_visit",), ("pipeline", "version"),
              ("visits", 0, "ordinal"), ("visits", 0, "attempt"), ("approvals", 0, "visit_number")]),
            (event, run_validation.validate_event,
             [("schema_version",), ("sequence",), ("manifest_revision",), ("visit_number",)]),
        ):
            for path in paths:
                for token in ("true", "false", "1.0", "2e0", "0", "null"):
                    with self.subTest(path=path, token=token):
                        if token == "null" and path in (("current_visit",), ("visit_number",)):
                            continue
                        candidate = copy.deepcopy(record)
                        parent = candidate
                        for key in path[:-1]:
                            parent = parent[key]
                        parent[path[-1]] = json.loads(token)
                        with self.assertRaises(run_store.RunCorruptionError):
                            validator(candidate, RUN_ID)

    def test_invalid_nested_manifest_fields(self):
        cases = [(("pipeline", "id"), ""), (("visits", 0, "phase_id"), " "),
                 (("visits", 0, "inputs", 0, "reference"), ""),
                 (("visits", 0, "mutation_policy"), {"invalid": True}),
                 (("visits", 0, "chosen_outcome"), []), (("visits", 0, "transition_target"), 7),
                 (("terminal_result",), float("nan"))]
        for path, invalid in cases:
            with self.subTest(path=path):
                value = manifest_at()
                parent = value
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = invalid
                with self.assertRaises(run_store.RunCorruptionError):
                    run_validation.validate_manifest(value, RUN_ID)

    def test_approval_variants_and_state_bindings(self):
        value = manifest_at("awaiting-approval")
        transition = value["approvals"][0]
        action = {k: v for k, v in transition.items() if k not in ("outcome", "artifact_sha256")}
        action.update(kind="action")
        for record in (action, transition):
            run_validation.validate_manifest({**value, "approvals": [record]}, RUN_ID)
            bad = [{k: v for k, v in record.items() if k != missing} for missing in record]
            updates = [{"extra": True}, {"phase_id": "other"}, {"run_id": "other"},
                       {"pipeline_sha256": "0" * 64}, {"visit_number": 19}, {"reason": ""},
                       {"requested_at": 10}, {"actor": "user"}, {"decision": "approved"},
                       {"decided_at": record["requested_at"]}, {"status": "approved"},
                       {"status": "stale", "decision": "approved", "actor": "system",
                        "decided_at": record["requested_at"]}]
            if record["kind"] == "transition":
                updates += [{"details": []}, {"outcome": ""}, {"artifact_sha256": "bad"},
                            {"status": "declined", "decision": "declined", "actor": "user",
                             "decided_at": record["requested_at"]}]
            else:
                updates += [{"details": "  "}, {"artifact_sha256": "0" * 64}, {"outcome": "done"}]
            bad.extend({**record, **change} for change in updates)
            for candidate in bad:
                with self.subTest(candidate=candidate), self.assertRaises(run_store.RunCorruptionError):
                    run_validation.validate_manifest({**value, "approvals": [candidate]}, RUN_ID)
        with self.assertRaisesRegex(run_store.RunCorruptionError, "multiple pending approvals"):
            run_validation.validate_manifest({**value, "approvals": [action, transition]}, RUN_ID)

    def test_open_metadata_is_accepted_without_mutation(self) -> None:
        cases = [
            (("visits", 0, "validation_checks"), [None, 42]),
            (("visits", 0, "command_results"), ["unstructured"]),
            (("git",), {"base": [], "head": 42}),
            (("visits", 0, "mutation_baseline"), {"files": []}),
            (("visits", 0, "mutation_result"), [None, 42]),
            (("visits", 0, "deviations"), [None, "unstructured"]),
            (("status",), "completed"),  # Current visit remains active.
            (("terminal_result",), ["unstructured"]),
            (("block_reason",), ["unstructured"]),
        ]
        for path, accepted in cases:
            with self.subTest(path=path):
                value = manifest_at()
                target = value
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = accepted
                original = copy.deepcopy(value)
                run_validation.validate_manifest(value, RUN_ID)
                self.assertEqual(value, original)

    def test_record_field_vocabulary_matches_schema_without_inserting_defaults(self) -> None:
        from pathlib import Path
        schemas = Path(run_store.__file__).parent / "schemas"
        run = json.loads((schemas / "run.schema.json").read_text())
        event = json.loads((schemas / "event.schema.json").read_text())
        for record, schema in (
            (run_records.RunRecord, run), (run_records.EventRecord, event),
            (run_records.VisitRecord, run["$defs"]["visit"]),
            (run_records.ArtifactRecord, run["$defs"]["outputArtifact"]),
            (run_records.InputArtifactRecord, run["$defs"]["inputArtifact"]),
        ):
            self.assertEqual(record.__required_keys__, set(schema["required"]))
            self.assertEqual(record(), {})
        common = set(run["$defs"]["approval"]["required"])
        self.assertEqual(run_records.ActionApproval.__required_keys__, common)
        self.assertEqual(run_records.TransitionApproval.__required_keys__, common | {"artifact_sha256", "outcome"})


class RunIdentityTests(unittest.TestCase):
    def test_utc_formatting_and_random_source_injection(self) -> None:
        for value in (datetime(2026, 10, 4, 12, 30, 1, 123456),
                      datetime(2026, 10, 4, 14, 30, 1, 123456,
                               tzinfo=timezone(timedelta(hours=2)))):
            self.assertEqual(run_store.format_timestamp(value), "2026-10-04T12:30:01.123456Z")
            calls = []
            def random_source(size):
                calls.append(size)
                return bytes.fromhex("01020304")
            self.assertEqual(run_store.generate_run_id(clock=lambda: value, random_source=random_source),
                             "20261004T123001Z-01020304")
            self.assertEqual(calls, [4])
            self.assertEqual(run_store.generate_run_id(clock=lambda: value, random_source=lambda: "01020304"),
                             "20261004T123001Z-01020304")
        def broken(size):
            raise TypeError("source failed")
        with self.assertRaisesRegex(TypeError, "source failed"):
            run_store.generate_run_id(random_source=broken)


class SelectionOutcomeTests(unittest.TestCase):
    def test_status_tolerates_absent_current_and_keeps_completed_current(self) -> None:
        value = manifest_at()
        for ordinal in (None, 999):
            value["current_visit"] = ordinal
            status = build_status(value, None)
            self.assertIsNone(status["current"])
            self.assertIsNone(status["next_command"])
            self.assertIsNone(run_records.current_visit(value))
        with self.assertRaises(run_store.RunStoreError) as raised:
            run_records.visit_by_number(value, 999)
        self.assertEqual(raised.exception.diagnostic_code, "visit-not-found")
        value = manifest_at("completed")
        self.assertEqual(build_status(value, None)["current"]["status"], "completed")
        self.assertEqual(run_records.current_visit(value)["status"], "completed")

    def test_approval_status_is_global_but_next_command_and_engine_are_per_visit(self) -> None:
        value = manifest_at("paused")
        current = value["current_visit"]
        approved = value["approvals"][0]
        pending = manifest_at("awaiting-approval")["approvals"][0]
        here = {**pending, "visit_number": current, "phase_id": value["visits"][-1]["phase_id"]}
        value.update(status="awaiting-approval", approvals=[approved, here, pending])
        run_validation.validate_manifest(value, RUN_ID)
        self.assertEqual(build_status(value, None)["pending_approval"]["request_number"], 3)
        self.assertIs(pending_approval(value, current), here)
        self.assertIs(approved_record(value, approved["visit_number"]), approved)
        self.assertEqual(next_command(value)[-2:], ["--request", "2"])
        value["approvals"].remove(here)
        self.assertEqual(next_command(value)[1], "request-approval")
        self.assertIsNone(pending_approval(value, current))


if __name__ == "__main__":
    unittest.main()
