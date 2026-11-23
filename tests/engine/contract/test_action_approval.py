import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from specromancy_engine.config import PipelineConfigError, load_pipeline
from specromancy_engine.engine import Engine
from specromancy_engine.errors import SpecromancyError
from tests.engine.support import MultiPipelineFixture


ACTION = "new-production-dependency"
TRANSITION = "material-scope-change"


class ActionApprovalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = MultiPipelineFixture()
        self.addCleanup(self.fixture.close)
        self.root = self.fixture.root
        self.path = self.root / "workflow/pipelines/alpha.toml"
        self.invocations = self.root / ".specromancy/invocations"
        self.allow_check = self.root / ".specromancy/pass"
        command = [sys.executable, "-c",
                   "from pathlib import Path\n"
                   "with Path('.specromancy/invocations').open('a') as log: log.write('check\\n')\n"
                   "raise SystemExit(0 if Path('.specromancy/pass').exists() else 5)"]
        self.source = self.path.read_text()
        self.source = self.source.replace("transition_approval_conditions = []\naction_approval_conditions = []",
            f'transition_approval_conditions = ["{TRANSITION}"]\n'
            f'action_approval_conditions = ["{ACTION}"]\ncommands = [{{ argv = {json.dumps(command)} }}]')
        self.source = self.source.replace('stop_conditions = []', 'stop_conditions = ["stopped"]')
        self.path.write_text(self.source)
        self.pipeline = load_pipeline(self.path, self.root)
        self.engine = Engine(self.pipeline)
        self.store = self.engine.store

    def cli(self, expected, *args, as_json=True):
        command = [sys.executable, "-m", "specromancy_engine", "--root", str(self.root)]
        result = subprocess.run(command + (["--json"] if as_json else []) + list(args),
                                capture_output=True, text=True, check=False)
        output = result.stdout or result.stderr
        self.assertEqual(result.returncode, expected, output)
        return json.loads(output) if as_json else output

    def start(self):
        run_id = self.engine.initialize("Record a result")["action"]["run_id"]
        self.engine.start_phase(run_id, "compose")
        return run_id

    def request(self, run_id, details="Install package A"):
        return self.engine.request_approval(run_id, reason=ACTION, details=details)

    def events(self, run_id):
        return [e["type"] for e in self.store.read_events(run_id)]

    def test_required_disjoint_lists_and_shorthand(self):
        for actions, transitions in (([], []), ([ACTION], []), ([], [TRANSITION]), ([ACTION], [TRANSITION])):
            with self.subTest(actions=actions, transitions=transitions):
                source = self.source.replace(f'["{ACTION}"]', json.dumps(actions))
                self.path.write_text(source.replace(f'["{TRANSITION}"]', json.dumps(transitions)))
                pipeline = load_pipeline(self.path, self.root)
                canonical = json.loads(pipeline.canonical_json)["phases"][0]
                self.assertEqual(canonical["action_approval_conditions"], actions)
                self.assertEqual(canonical["transition_approval_conditions"], transitions)
                self.assertNotIn("approval_conditions", canonical)
                self.engine = Engine(pipeline)
                run_id = self.start()
                self.cli(5, "request-approval", run_id, "--reason", "unknown")
                if actions and not transitions:
                    self.cli(2, "request-approval", run_id, "--details", "  ")
                    self.cli(2, "request-approval", run_id, "--details", "A", "--outcome", "done")
                    self.cli(7, "request-approval", run_id, "--details", "A")
                elif transitions and not actions:
                    self.store.write_visit_output(run_id, 1, "# Result\nEvidence.\n")
                    self.allow_check.touch()
                    self.cli(7, "request-approval", run_id)
                else:
                    self.cli(2, "request-approval", run_id)
        invalid = [self.source.replace(f'"{ACTION}"', f'"{TRANSITION}"')]
        for field in ("action_approval_conditions", "transition_approval_conditions"):
            invalid.append("\n".join(line for line in self.source.splitlines() if not line.startswith(field)))
        for source in invalid:
            self.path.write_text(source)
            with self.assertRaises(PipelineConfigError):
                load_pipeline(self.path, self.root)

    def test_cli_action_then_validation_and_transition(self):
        run_id = self.cli(8, "init", "--pipeline", "alpha", "Record a result")["action"]["run_id"]
        response = self.cli(8, "phase", run_id, "compose")
        self.assertEqual(response["schema_version"], 2)
        packet = response["action"]
        self.assertEqual(packet["schema_version"], 2)
        self.assertEqual(packet["action_approval_conditions"], [ACTION])
        self.assertEqual(packet["transition_approval_conditions"], [TRANSITION])
        output = Path(packet["output"]["absolute_path"])
        before = self.store.load(run_id)["visits"][0]
        request = ("request-approval", run_id, "--reason", ACTION, "--details", "Install A")
        pending = self.cli(7, *request)["approval"]
        self.assertEqual(pending["request_number"], 1)
        self.assertNotIn("artifact_sha256", pending)
        self.assertNotIn("outcome", pending)
        human = self.cli(7, *request, as_json=False)
        for expected in ("Install A", " ".join(pending["approve_command"]), " ".join(pending["decline_command"])):
            self.assertIn(expected, human)
        self.cli(2, "approve", run_id, "compose")
        action = self.cli(8, *pending["approve_command"][1:])["action"]
        self.assertEqual(action["visit_id"], packet["visit_id"])
        self.assertFalse(output.exists())
        self.assertFalse(self.invocations.exists())
        self.assertEqual(self.store.load(run_id)["visits"][0], before)
        self.assertEqual(self.events(run_id)[-2:], ["approval-requested", "approval-granted"])
        self.assertEqual(self.cli(0, "status", run_id)["status"]["next_command"],
                         ["specromancy", "phase", run_id, "compose"])
        self.assertEqual(self.cli(8, "phase", run_id, "compose")["action"], action)
        self.assertEqual(action["action_decisions"][0]["details"], "Install A")
        output.write_text("# Result\nEvidence.\n")
        self.cli(6, "validate", run_id, "compose")
        visit = self.store.load(run_id)["visits"][0]
        self.assertEqual(visit["command_results"][0]["exit_code"], 5)
        self.assertEqual(visit["status"], "active")
        self.assertEqual(self.invocations.read_text().splitlines(), ["check"])
        self.allow_check.touch()
        approval = self.cli(7, "request-approval", run_id, "--reason", TRANSITION)["approval"]
        self.assertEqual(approval["outcome"], "done")
        self.assertEqual(approval["artifact_sha256"], visit["validation_checks"][0]["sha256"])
        self.cli(0, *approval["approve_command"][1:])
        self.cli(0, *approval["approve_command"][1:])
        self.assertEqual(self.invocations.read_text().splitlines(), ["check"] * 3)
        self.assertEqual(self.events(run_id).count("visit-transitioned"), 1)

    def test_numbered_replay_decline_and_invalidation(self):
        run_id = self.start()
        def request(details, code):
            return self.cli(code, "request-approval", run_id, "--reason", ACTION, "--details", details)
        def decide(verb, number, code):
            return self.cli(code, verb, run_id, "compose", "--request", str(number))
        request("A", 7)
        decide("approve", 1, 8)
        request("B", 7)
        pending = self.store.load(run_id)
        request("B", 7)
        request("A", 5)
        decide("approve", 1, 5)
        self.cli(5, "request-approval", run_id, "--reason", TRANSITION)
        self.assertEqual(self.store.load(run_id), pending)
        decide("decline", 2, 8)
        decided = self.store.load(run_id)
        request("B", 8)
        decide("decline", 2, 8)
        decide("approve", 2, 5)
        request("A", 8)
        decide("approve", 1, 8)
        self.assertEqual(self.store.load(run_id), decided)
        request("B revised", 7)
        decide("approve", 3, 8)
        request("C", 7)
        self.path.write_text(self.source.replace("Record a result.", "Record the result."))
        decide("approve", 4, 7)
        stale = self.store.load(run_id)
        self.assertEqual(stale["status"], "active")
        self.assertEqual(stale["approvals"][-1]["status"], "stale")
        self.path.write_text(self.source)
        self.assertEqual(request("C", 7)["approval"]["request_number"], 5)
        action_events = [(e["type"], e["payload"]["request_number"]) for e in self.store.read_events(run_id)
                         if e["type"].startswith("approval-")]
        self.assertEqual(action_events, [
            ("approval-requested", 1), ("approval-granted", 1), ("approval-requested", 2),
            ("approval-declined", 2), ("approval-requested", 3), ("approval-granted", 3),
            ("approval-requested", 4), ("approval-invalidated", 4), ("approval-requested", 5),
        ])

    def test_action_permission_checks_inputs_provenance_and_original_baseline(self):
        run_id = self.start()
        directory = self.store.run_directory(run_id)
        protected = self.root / "protected"
        skill = self.pipeline.phases[0].skill_path
        request = directory / self.store.load(run_id)["request"]["path"]
        for stage in ("request", "grant"):
            if stage == "grant":
                self.request(run_id)
            snapshot = self.store.load(run_id)
            for path in (protected, request, skill):
                with self.subTest(stage=stage, path=path):
                    original = path.read_bytes() if path.exists() else None
                    path.write_text("changed")
                    with self.assertRaises(SpecromancyError):
                        if stage == "grant":
                            self.engine.approve(run_id, "compose", request_number=1)
                        else:
                            self.request(run_id)
                    self.assertEqual(self.store.load(run_id, verify_artifacts=False), snapshot)
                    if original is None:
                        path.unlink()
                    else:
                        path.write_bytes(original)

    def test_action_request_races_block_validation_and_transition_request(self):
        other = Engine(self.pipeline)
        for operation, write_method, event in (
            ("block", "mutate", "run-blocked"),
            ("pass", "transition_visit", "visit-transitioned"),
            ("fail", "record_validation_attempt", "validation-failed"),
            ("transition", "decide_approval", "approval-requested"),
        ):
            for first in ("operation", "action pending", "action granted"):
                with self.subTest(operation=operation, first=first):
                    run_id = self.start()
                    self.store.write_visit_output(run_id, 1, "# Result\nEvidence.\n")
                    if operation == "fail":
                        self.allow_check.unlink(missing_ok=True)
                    else:
                        self.allow_check.touch()
                    initial = self.events(run_id)

                    def compete(engine):
                        if operation == "block":
                            return engine.block(run_id, reason="stopped")
                        if operation == "transition":
                            return engine.request_approval(run_id, reason=TRANSITION)
                        return engine.validate(run_id)

                    if first == "operation":
                        original = self.store.decide_approval

                        def interleave(*args):
                            if operation == "fail":
                                with self.assertRaises(SpecromancyError) as failed:
                                    compete(other)
                                self.assertEqual(failed.exception.code, 6)
                            else:
                                compete(other)
                            return original(*args)

                        with patch.object(self.store, "decide_approval", side_effect=interleave):
                            if operation == "fail":
                                self.request(run_id)
                                visit = self.store.load(run_id)["visits"][0]
                                self.assertEqual(visit["command_results"][0]["exit_code"], 5)
                                self.assertEqual(self.events(run_id), initial + [event, "approval-requested"])
                                continue
                            with self.assertRaises(SpecromancyError) as conflict:
                                self.request(run_id)
                        self.assertEqual(conflict.exception.code, 5)
                        self.assertEqual(self.events(run_id), initial + [event])
                        continue

                    original = getattr(self.store, write_method)
                    winning_events = ["approval-requested"]
                    if first == "action granted":
                        winning_events.append("approval-granted")

                    def interleave(*args, **kwargs):
                        other.request_approval(run_id, reason=ACTION, details="A")
                        if first == "action granted":
                            other.approve(run_id, "compose", request_number=1)
                        return original(*args, **kwargs)

                    with patch.object(self.store, write_method, side_effect=interleave):
                        with self.assertRaises(SpecromancyError) as conflict:
                            compete(self.engine)
                    self.assertEqual(conflict.exception.code, 5)
                    self.assertEqual(self.events(run_id), initial + winning_events)
                    manifest = self.store.load(run_id)
                    self.assertEqual(manifest["revision"], len(initial + winning_events))
                    self.assertEqual(manifest["status"], "active" if first == "action granted" else "awaiting-approval")
                    self.assertEqual(manifest["visits"][0]["validation_checks"], [])

    def test_transition_seals_only_the_approved_output(self):
        run_id = self.start()
        self.store.write_visit_output(run_id, 1, "# Result\nOriginal.\n")
        self.allow_check.touch()
        self.engine.request_approval(run_id, reason=TRANSITION)
        transition = self.store.transition_visit

        def edit_after_validation(*args, **kwargs):
            self.store.write_visit_output(run_id, 1, "# Result\nReplacement.\n")
            return transition(*args, **kwargs)

        with patch.object(self.store, "transition_visit", side_effect=edit_after_validation):
            with self.assertRaises(SpecromancyError) as stale:
                self.engine.approve(run_id, "compose", request_number=1)
        self.assertEqual(stale.exception.diagnostic_code, "stale-approval")
        self.assertEqual(self.store.load(run_id)["approvals"][0]["status"], "stale")
        self.assertEqual(self.events(run_id)[-1], "approval-invalidated")
