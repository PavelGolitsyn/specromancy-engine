from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy_engine.cli import main
from specromancy_engine.config import load_pipeline
from specromancy_engine.run_store import RunStore, RunStoreError
from tests.engine.contract.compatibility_support import CompatibilityFixture, RUN_ID as CAPTURED_ID, read_record


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "20260925T120000Z-a1b2c3d4"


class VersionedRecoveryTests(unittest.TestCase):
    def restore(self, files):
        fixture = CompatibilityFixture(pause=True)
        self.addCleanup(fixture.close)
        fixture.restore(files)
        return fixture

    def snapshot(self, fixture):
        directory = fixture.store.run_directory(CAPTURED_ID)
        return {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}

    def cli(self, fixture, command, *args):
        out, err = io.StringIO(), io.StringIO()
        code = main(["--root", str(fixture.root), "--json", command, CAPTURED_ID, *args],
                    stdout=out, stderr=err)
        return code, json.loads(err.getvalue() or out.getvalue())

    def assert_refused(self, fixture, surface, version, command, *args):
        before = self.snapshot(fixture)
        store = fixture.store
        details = {"error_code": "unsupported-schema-version", "surface": surface,
                   "observed_version": version, "expected_version": 2, "run_id": CAPTURED_ID}
        for operation in (
            lambda: store.load(CAPTURED_ID), lambda: store.load(CAPTURED_ID, recover=False),
            lambda: store.read_events(CAPTURED_ID), lambda: store.read_events(CAPTURED_ID, recover=False),
            lambda: store.read_pipeline(CAPTURED_ID), lambda: store.block(CAPTURED_ID, "test"),
        ):
            with self.assertRaises(RunStoreError) as caught:
                operation()
            self.assertEqual(caught.exception.details, details)
            self.assertEqual(self.snapshot(fixture), before)
        code, response = self.cli(fixture, command, *args)
        self.assertEqual(code, 12)
        self.assertEqual(response["details"], details)
        self.assertIn("engine that produced the run", response["message"])
        self.assertEqual(self.snapshot(fixture), before)

    def test_original_approval_and_interrupted_v1_runs_are_refused_before_writes(self):
        old = read_record("states-v1.json")
        approval = json.loads(old["awaiting-approval"]["run.json"])["approvals"][0]
        self.assertNotIn("kind", approval)
        self.assert_refused(self.restore(old["awaiting-approval"]), "run", 1, "approve", "compose")
        self.assert_refused(self.restore(old["recoverable"]), "run", 1, "resume")

    def test_old_mixed_and_future_versions_are_refused_even_with_recoverable_gap(self):
        current = read_record("states.json")
        old_log = read_record("states-v1.json")["recoverable"]["events.jsonl"]
        for state in ("active", "recoverable"):
            files = current[state]
            lines = files["events.jsonl"].splitlines(keepends=True)
            for version, log in ((1, old_log), (1, old_log.splitlines(keepends=True)[0] + "".join(lines[1:])),
                                 (3, lines[0].replace('"schema_version":2', '"schema_version":3') + "".join(lines[1:]))):
                with self.subTest(state=state, log=log):
                    fixture = self.restore({**files, "events.jsonl": log})
                    self.assert_refused(fixture, "event", version, "resume")
        files = current["recoverable"]
        future = json.loads(files["run.json"])
        future["schema_version"] = 3
        self.assert_refused(self.restore({**files, "run.json": json.dumps(future)}), "run", 3, "resume")

    def test_cli_loads_saved_graph_before_recovering_once(self):
        fixture = self.restore(read_record("states.json")["recoverable"])
        before = self.snapshot(fixture)
        graph = fixture.path.read_text()
        fixture.path.write_text(graph.replace("schema_version = 2", "schema_version = 99"))
        code, error = self.cli(fixture, "resume")
        self.assertEqual(code, 3)
        self.assertEqual(error["details"]["error_code"], "unsupported-schema-version")
        self.assertEqual(error["details"]["value"], 99)
        self.assertEqual(self.snapshot(fixture), before)
        fixture.path.write_text(graph)
        self.assertEqual(self.cli(fixture, "resume")[0], 8)
        events = fixture.store.read_events(CAPTURED_ID, recover=False)
        self.assertEqual(events[-1]["type"], "recovery")
        self.assertEqual(sum(e["type"] == "recovery" for e in events), 1)
        recovered = self.snapshot(fixture)
        self.assertEqual(recovered[Path("run.json")], before[Path("run.json")])
        self.assertEqual(self.cli(fixture, "resume")[0], 8)
        self.assertEqual(self.snapshot(fixture), recovered)


class RecoveryContractTests(unittest.TestCase):
    def test_fresh_process_reconstructs_a_run_using_only_disk_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            skill = root / "workflow" / "skills" / "compose" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: compose\ndescription: Fixture.\n---\n", encoding="utf-8"
            )
            pipeline_path = root / "workflow/pipeline.toml"
            pipeline_path.write_text(
                textwrap.dedent(
                    """
                    schema_version = 2
                    id = "recovery"
                    version = 1
                    start = "compose"
                    terminal_outcomes = ["done"]
                    artifact_pattern = "artifacts/{visit:03}-{phase}.md"
                    allow_non_git = true
                    [[phases]]
                    id = "compose"
                    skill = "compose"
                    skill_source = "workflow/skills/compose/SKILL.md"
                    inputs = ["request"]
                    output_name = "{visit:03}-result.md"
                    mutation = "read-only"
                    completion_criteria = ["Write."]
                    validator = "file"
                    transition_approval_conditions = []
                    action_approval_conditions = []
                    stop_conditions = []
                    max_visits = 1
                    [[phases.transitions]]
                    outcome = "done"
                    """
                ),
                encoding="utf-8",
            )
            pipeline = load_pipeline(pipeline_path, root)
            store = RunStore(root)
            store.create(pipeline, "recover me", run_id=RUN_ID)
            visit = store.start_visit(RUN_ID, pipeline, "compose")
            store.write_visit_output(RUN_ID, visit["ordinal"], "result\n")
            store.complete_visit(RUN_ID, visit["ordinal"], outcome="done")

            program = (
                "import json,sys; "
                "from specromancy_engine.run_store import RunStore; "
                "print(json.dumps(RunStore(sys.argv[1]).load(sys.argv[2]), sort_keys=True))"
            )
            result = subprocess.run(
                [sys.executable, "-c", program, str(root), RUN_ID],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["run_id"], RUN_ID)
            self.assertEqual(manifest["visits"][0]["status"], "completed")
            self.assertEqual(manifest["visits"][0]["output"]["sha256"], visit_hash(store))


def visit_hash(store: RunStore) -> str:
    return store.load(RUN_ID)["visits"][0]["output"]["sha256"]


if __name__ == "__main__":
    unittest.main()
