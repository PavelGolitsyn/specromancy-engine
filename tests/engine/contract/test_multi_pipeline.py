from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from specromancy_engine.adapters import generate_adapters
from specromancy_engine.exit_codes import ExitCode
from specromancy_engine.registry import load_adapter_registry, load_registry
from tests.engine.support import MultiPipelineFixture, write_workflow_skill


ROOT = Path(__file__).resolve().parents[3]


class PipelineCLICase(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MultiPipelineFixture()
        self.root = self.fixture.root

    def tearDown(self) -> None:
        self.fixture.close()

    def command(self, *arguments: str) -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, "-m", "specromancy_engine", "--root", str(self.root), "--json", *arguments],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        return result.returncode, json.loads(result.stdout or result.stderr)

    def initialize(self, pipeline_id: str) -> dict:
        code, payload = self.command("init", "Record evidence", "--pipeline", pipeline_id)
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        return payload["action"]


class WorkflowOnlyContractTests(PipelineCLICase):
    def test_discovery_and_action_identify_the_same_canonical_procedure(self) -> None:
        source = self.root / "workflow/skills/compose/SKILL.md"
        source.write_text(source.read_text().replace("Follow the action packet.", "Read [notes](notes.md)."))
        source.with_name("notes.md").write_text("Canonical support file.")
        generate_adapters(self.root, load_adapter_registry(self.root))
        action = self.initialize("alpha")
        self.assertEqual(Path(action["skill"]["absolute_path"]), source)
        for harness in (".agents", ".claude"):
            wrapper = self.root / harness / "skills/compose/SKILL.md"
            text = wrapper.read_text()
            self.assertIn("name: compose", text)
            self.assertIn("description: Record evidence.", text)
            relative = source.relative_to(self.root).as_posix()
            self.assertIn(f"Load `{relative}` from the consumer repository root", text)
            self.assertIn("directory containing the canonical file", text)
            self.assertIn("skill.absolute_path", text)
            self.assertIn("Stop if the canonical file is missing", text)
            self.assertIn("packet identifies a different file", text)
            self.assertNotIn("notes.md", text)
            self.assertFalse(wrapper.with_name("notes.md").exists())
        shutil.rmtree(self.root / ".agents")
        code, payload = self.command("phase", action["run_id"], "compose")
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        canonical = Path(payload["action"]["skill"]["absolute_path"])
        self.assertIn("[notes](notes.md)", canonical.read_text())
        self.assertEqual(canonical.with_name("notes.md").read_text(), "Canonical support file.")

    def test_cli_guards_registry_before_reading_valid_or_malformed_generated_toml(self) -> None:
        registry = self.root / "workflow/pipelines.toml"
        valid = registry.read_bytes()
        target = self.root / "AGENTS.md"
        generate_adapters(self.root, load_adapter_registry(self.root))
        registry.unlink()
        registry.symlink_to(target)

        def snapshot():
            return {p: (p.lstat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                    for p in self.root.rglob("*")}

        for content in (valid, b"[invalid"):
            target.write_bytes(content)
            before = snapshot()
            for args in ((), ("--check",)):
                with self.subTest(content=content, args=args):
                    code, payload = self.command("adapters", "generate", *args)
                    self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
                    self.assertEqual(payload["details"]["error_code"], "unsafe-path")
                    self.assertEqual(payload["details"]["field"], "registry")
                    self.assertTrue(registry.is_symlink())
                    self.assertEqual(snapshot(), before)

    def test_selected_workflow_completes_independently_of_other_registrations(self) -> None:
        beta = self.root / "workflow/pipelines/beta.toml"
        graph = beta.read_text()
        source = "workflow/skills/compose/SKILL.md"
        write_workflow_skill(self.root, source="workflow/conflict.md")
        for document, error in (("invalid [", "invalid-toml"),
                                (graph.replace(source, "workflow/absent.md"), "missing-file"),
                                (graph.replace(source, "workflow/conflict.md"), "conflicting-skill-source")):
            with self.subTest(error=error):
                beta.write_text(document)
                self.assertEqual(load_registry(self.root).load("alpha").phases[0].skill_source, source)
                code, failure = self.command("adapters", "generate")
                self.assertEqual(code, ExitCode.INVALID_PIPELINE, failure)
                self.assertEqual(failure["details"]["error_code"], error)
                action = self.initialize("alpha")
                run = action["run_id"]
                self.assertEqual(action["skill"]["absolute_path"], str(self.root / source))
                code, active = self.command("phase", run, "compose")
                self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, active)
                Path(active["action"]["output"]["absolute_path"]).write_text("## Result\nEvidence.\n")
                code, payload = self.command("validate", run)
                self.assertEqual(code, ExitCode.SUCCESS, payload)
                code, payload = self.command("resume", run)
                self.assertEqual(code, ExitCode.SUCCESS, payload)
                self.assertEqual(payload["status"]["terminal_result"]["outcome"], "done")
        self.assertEqual({p.name for p in self.root.iterdir()}, {".git", "workflow", ".specromancy"})

    def test_unsupported_graph_versions_refuse_init_and_selected_generation(self) -> None:
        graph = self.root / "workflow/pipelines/alpha.toml"
        current = graph.read_text()
        for version in (1, 2, 4):
            obsolete = current.replace("schema_version = 3", f"schema_version = {version}")
            # Obsolete fields and a missing source must not mask the version error.
            graph.write_text(obsolete.replace("transition_approval_conditions", "approval_conditions")
                             .replace('skill_source = "workflow/skills/compose/SKILL.md"\n', ""))
            for args in (("init", "Record evidence", "--pipeline", "alpha"),
                         ("adapters", "generate"), ("adapters", "generate", "--check")):
                with self.subTest(version=version, command=args):
                    code, error = self.command(*args)
                    self.assertEqual(code, ExitCode.INVALID_PIPELINE, error)
                    details = error["details"]
                    self.assertEqual(details["error_code"], "unsupported-schema-version")
                    self.assertEqual(details["value"], version)
                    self.assertEqual(details["path"], str(graph))
                    for field in ("skill_source", "transition_approval_conditions", "action_approval_conditions"):
                        self.assertIn(field, details["remediation"])
                    self.assertEqual({p.name for p in self.root.iterdir()}, {".git", "workflow"})

    def test_missing_or_escaped_canonical_procedure_blocks_init_despite_wrapper(self) -> None:
        generate_adapters(self.root, load_adapter_registry(self.root))
        skill = self.root / "workflow/skills/compose/SKILL.md"
        skill.unlink()
        for target, diagnostic in ((None, "missing-file"), (self.root / "AGENTS.md", "unsafe-path"),
                                   (self.root / ".agents/skills/compose/SKILL.md", "unsafe-path")):
            with self.subTest(target=target):
                if target is not None:
                    skill.symlink_to(target)
                code, payload = self.command("init", "Record evidence", "--pipeline", "alpha")
                self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
                self.assertEqual(payload["details"]["error_code"], diagnostic)
                self.assertFalse((self.root / ".specromancy").exists())
                if target is not None:
                    skill.unlink()

    def test_retargeted_workflow_link_cannot_redirect_a_prepared_visit(self) -> None:
        skill = self.root / "workflow/skills/compose/SKILL.md"
        original = skill.with_name("original.md")
        skill.rename(original)
        skill.symlink_to(original)
        action = self.initialize("alpha")
        self.assertEqual(Path(action["skill"]["absolute_path"]), original)
        generate_adapters(self.root, load_adapter_registry(self.root))
        other = skill.with_name("other.md")
        other.write_bytes(original.read_bytes())
        skill.unlink()
        skill.symlink_to(other)
        # Even identical bytes at the old recorded location cannot make a
        # discovery wrapper the procedure for an existing visit.
        wrapper = self.root / ".agents/skills/compose/SKILL.md"
        wrapper.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(wrapper)
        directory = self.root / ".specromancy/runs" / action["run_id"]
        before = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        code, payload = self.command("resume", action["run_id"])
        self.assertEqual(code, ExitCode.INTERNAL_ERROR, payload)
        self.assertEqual(payload["details"]["error_code"], "provenance-path-mismatch")
        self.assertEqual({p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}, before)

    def test_only_canonical_procedure_edits_affect_prepared_skill_provenance(self) -> None:
        action = self.initialize("alpha")
        run = action["run_id"]
        directory = self.root / ".specromancy/runs" / run
        before = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        generate_adapters(self.root, load_adapter_registry(self.root))
        code, payload = self.command("resume", run)
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        self.assertEqual(payload["action"]["skill"], action["skill"])
        skill = Path(action["skill"]["absolute_path"])
        skill.write_bytes(skill.read_bytes() + b"Changed procedure.\n")
        code, payload = self.command("phase", run, "compose")
        self.assertEqual(code, ExitCode.INTERNAL_ERROR, payload)
        self.assertEqual(payload["details"]["error_code"], "provenance-hash-mismatch", payload)
        self.assertEqual({p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}, before)


class MultiPipelineContractTests(PipelineCLICase):
    def test_init_requires_registered_id_even_for_one_pipeline(self) -> None:
        for ids in (("alpha", "beta"), ("alpha",)):
            self.fixture.register(*ids)
            code, payload = self.command("init", "Record evidence")
            self.assertEqual(code, ExitCode.USAGE_ERROR, payload)
            self.assertIn("no default", payload["message"])
            for selector in ("absent", str(self.root / "workflow/pipelines/alpha.toml")):
                code, payload = self.command("--pipeline", selector, "init", "Record evidence")
                self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
            self.assertFalse((self.root / ".specromancy").exists())

    def test_fresh_processes_complete_two_graphs_using_recorded_selection(self) -> None:
        actions = [self.initialize("alpha"), self.initialize("beta")]
        for action, pipeline_id, phase in zip(actions, ("alpha", "beta"), ("compose", "inspect")):
            run_id = action["run_id"]
            self.assertNotIn("--pipeline", action["final_validation_command"])
            code, payload = self.command("status", run_id)
            self.assertEqual(code, ExitCode.SUCCESS, payload)
            self.assertEqual(payload["status"]["pipeline"]["id"], pipeline_id)
            code, payload = self.command(phase, run_id)
            self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
            self.assertEqual(payload["action"]["phase"], phase)
            Path(payload["action"]["output"]["absolute_path"]).write_text("## Result\nRecorded evidence.\n", encoding="utf-8")
            result = subprocess.run(payload["action"]["final_validation_command"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, ExitCode.SUCCESS, result.stderr)
            code, payload = self.command("resume", run_id)
            self.assertEqual(code, ExitCode.SUCCESS, payload)
            self.assertEqual(payload["status"]["terminal_result"]["outcome"], "done")

    def test_alias_and_selector_cannot_switch_a_runs_graph(self) -> None:
        run_id = self.initialize("alpha")["run_id"]
        for selector in (
            "beta", "absent", "workflow/pipelines/beta.toml",
            "workflow/pipelines/alpha.toml", str(self.root / "workflow/pipelines/alpha.toml"),
        ):
            code, payload = self.command("status", run_id, "--pipeline", selector)
            self.assertEqual(code, ExitCode.USAGE_ERROR, payload)
        code, payload = self.command("inspect", run_id)
        self.assertEqual(code, ExitCode.USAGE_ERROR, payload)
        code, payload = self.command("status", run_id, "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.SUCCESS, payload)
        code, payload = self.command("phase", run_id, "inspect")
        self.assertEqual(code, ExitCode.ILLEGAL_TRANSITION, payload)

    def test_unrelated_graph_edits_and_registry_reordering_preserve_run(self) -> None:
        run_id = self.initialize("alpha")["run_id"]
        self.fixture.register("beta", "alpha")
        (self.root / "workflow/pipelines/beta.toml").write_text("invalid [", encoding="utf-8")
        code, payload = self.command("resume", run_id)
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        path = self.root / "workflow/pipelines/alpha.toml"
        path.write_text(path.read_text().replace("\nversion = 1", "\nversion = 2"), encoding="utf-8")
        code, payload = self.command("status", run_id)
        self.assertEqual(code, ExitCode.SUCCESS, payload)
        self.assertIn("pipeline-drift", {item["code"] for item in payload["status"]["warnings"]})
        code, payload = self.command("resume", run_id)
        self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
        self.assertEqual(payload["details"]["error_code"], "pipeline-hash-mismatch")

    def test_removed_registration_disables_init_and_preserves_existing_run(self) -> None:
        run_id = self.initialize("alpha")["run_id"]
        self.fixture.register("beta")
        code, payload = self.command("init", "New request", "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
        code, payload = self.command("compose", run_id)
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        Path(payload["action"]["output"]["absolute_path"]).write_text("## Result\nEvidence.\n", encoding="utf-8")
        code, payload = self.command("validate", run_id)
        self.assertEqual(code, ExitCode.SUCCESS, payload)

    def test_common_option_positions_and_description_file(self) -> None:
        description = self.root / "request.md"
        description.write_text("A file request\n", encoding="utf-8")
        code, payload = self.command("--pipeline=beta", "init", "--description-file", "request.md")
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        request = Path(payload["action"]["inputs"][0]["absolute_path"])
        self.assertEqual(request.read_text(), "A file request\n")
        run_id = payload["action"]["run_id"]
        code, payload = self.command("--pipeline", "beta", "status", run_id)
        self.assertEqual(code, ExitCode.SUCCESS, payload)
        code, payload = self.command("init", "Inline", "--description-file", "request.md", "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.USAGE_ERROR, payload)

    def test_missing_registry_and_corrupt_or_missing_run_are_reported(self) -> None:
        code, payload = self.command("status", "20261003T000000Z-00000000")
        self.assertEqual(code, ExitCode.NOT_FOUND, payload)
        action = self.initialize("alpha")
        manifest = self.root / ".specromancy/runs" / action["run_id"] / "run.json"
        # Deliberately tamper only with test-owned state to exercise corruption.
        manifest.write_text("{}", encoding="utf-8")
        code, payload = self.command("status", action["run_id"])
        self.assertEqual(code, ExitCode.INTERNAL_ERROR, payload)
        (self.root / "workflow/pipelines.toml").unlink()
        code, payload = self.command("init", "Request", "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
        code, payload = self.command("--help")
        self.assertEqual(code, ExitCode.SUCCESS, payload)

    def test_overlapping_phase_names_keep_pipeline_provenance(self) -> None:
        self.fixture.add_pipeline("beta", "compose")
        for pipeline_id in ("alpha", "beta"):
            action = self.initialize(pipeline_id)
            code, payload = self.command("compose", action["run_id"])
            self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
            code, payload = self.command("status", action["run_id"])
            self.assertEqual(payload["status"]["pipeline"]["id"], pipeline_id)
