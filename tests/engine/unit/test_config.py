from __future__ import annotations

import json
import re
import tempfile
import textwrap
import unittest
from importlib.resources import files
from dataclasses import FrozenInstanceError
from pathlib import Path

from specromancy_engine.config import (
    PipelineConfigError,
    load_pipeline,
    require_pipeline_hash,
)
from specromancy_engine.exit_codes import ExitCode
from tests.engine.support import MultiPipelineFixture, write_workflow_skill


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "engine" / "fixtures"
WORKFLOW_FIXTURE = FIXTURES / "example-pipeline"


PHASE = """
[[phases]]
id = "compose"
skill = "compose"
skill_source = "workflow/skills/compose/SKILL.md"
inputs = ["request"]
output_name = "{visit:03}-result.md"
mutation = "read-only"
completion_criteria = ["Write the result."]
validator = "file"
approval_conditions = []
stop_conditions = []
max_visits = 1

[[phases.transitions]]
outcome = "done"
"""


def document(phase: str = PHASE, **changes: str) -> str:
    values = {
        "schema_version": "1",
        "id": '"fixture"',
        "version": "1",
        "start": '"compose"',
        "terminal_outcomes": '["done"]',
        "artifact_pattern": '"artifacts/{visit:03}-{phase}.md"',
    }
    values.update(changes)
    return textwrap.dedent(
        f"""
        schema_version = {values['schema_version']}
        id = {values['id']}
        version = {values['version']}
        start = {values['start']}
        terminal_outcomes = {values['terminal_outcomes']}
        artifact_pattern = {values['artifact_pattern']}
        {phase}
        """
    )


class PipelineFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        skill = self.root / "workflow" / "skills" / "compose" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: compose\ndescription: Test.\n---\n", encoding="utf-8")
        templates = self.root / "workflow/config" / "templates"
        templates.mkdir(parents=True)
        (templates / "result.md").write_text("# Result\n", encoding="utf-8")
        self.path = self.root / "workflow/config" / "pipeline.toml"

    def close(self) -> None:
        self.temporary.cleanup()

    def write(self, content: str, name: str = "pipeline.toml") -> Path:
        path = self.path.with_name(name)
        path.write_text(content, encoding="utf-8")
        return path


class WorkflowSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MultiPipelineFixture()
        self.addCleanup(self.fixture.close)
        self.root = self.fixture.root
        self.graph = self.root / "workflow/pipelines/alpha.toml"
        self.graph_text = self.graph.read_text()
        self.source = "workflow/skills/compose/SKILL.md"
        self.skill = self.root / self.source

    def load(self, graph: str):
        self.graph.write_text(graph, encoding="utf-8")
        return load_pipeline(self.graph, self.root)

    def assert_failure(self, graph: str, diagnostic: str, field: str) -> None:
        with self.assertRaises(PipelineConfigError) as caught:
            self.load(graph)
        self.assertEqual(caught.exception.diagnostic_code, diagnostic)
        self.assertEqual(caught.exception.details["field"], field)

    def test_declared_source_syntax_agrees_with_published_schema(self) -> None:
        schema = json.loads(files("specromancy_engine").joinpath("schemas", "pipeline.schema.json").read_text())
        phase = schema["$defs"]["phase"]
        rule = phase["properties"]["skill_source"]
        self.assertEqual(rule["type"], "string")
        self.assertNotIn("skill_source", phase["required"])
        for spelling in (self.source, "./workflow//skills/./compose/SKILL.md"):
            with self.subTest(spelling=spelling):
                self.assertRegex(spelling, rule["pattern"])
                pipeline = self.load(self.graph_text.replace(self.source, spelling))
                self.assertEqual(pipeline.phases[0].skill_path, self.skill)
                self.assertEqual(pipeline.phases[0].skill_source, self.source)
                self.assertEqual(json.loads(pipeline.canonical_json)["phases"][0]["skill_source"], self.source)
        for spelling in ("/" + self.source, ".agents/skills/compose/SKILL.md",
                         "workflow/../" + self.source, "workflow//skills/..//SKILL.md",
                         "workflow/skills/*/SKILL.md", r"workflow\skills", "C:/workflow/skill.md"):
            with self.subTest(spelling=spelling):
                self.assertIsNone(re.fullmatch(rule["pattern"], spelling))
                graph = self.graph_text.replace(json.dumps(self.source), json.dumps(spelling))
                self.assert_failure(graph, "unsafe-path", "skill_source")
        self.assert_failure(self.graph_text.replace(json.dumps(self.source), "42"),
                            "invalid-field-type", "skill_source")

    def test_safe_descendant_link_and_graph_relative_dependency(self) -> None:
        self.skill.rename(self.skill.with_suffix(".canonical"))
        self.skill.symlink_to(self.skill.with_suffix(".canonical"))
        phase = self.load(self.graph_text).phases[0]
        self.assertEqual(phase.skill_source, self.source)
        self.assertEqual(phase.skill_path, self.skill.resolve())
        self.assertEqual(phase.output_template_path, self.root / "workflow/templates/shared.md")

    def test_runtime_resource_lookup_rejects_a_symlinked_workflow_root(self) -> None:
        workflow = self.root / "workflow"
        workflow.rename(self.root / ".claude")
        workflow.symlink_to(self.root / ".claude", target_is_directory=True)
        self.assert_failure(self.graph_text, "unsafe-path", "skill_source")

    def test_portable_strings_and_flat_metadata(self) -> None:
        self.skill.write_text(
            "---\nname: 'compose'\ndescription: \"Use when editing: record evidence.\"\n"
            "compatibility: Specromancy pipeline schema version 1.\nlicense: MIT\n"
            "metadata:\n  role: phase\n  revision: '2'\n---\n", encoding="utf-8"
        )
        self.assertEqual(self.load(self.graph_text).phases[0].skill_path, self.skill)

    def test_outside_declared_or_resolved_dependencies_fail_before_parsing(self) -> None:
        outside = self.root / ".opencode/generated"
        outside.parent.mkdir()
        outside.write_bytes(b"malformed JSON and frontmatter")
        link = self.root / "workflow/link"
        link.symlink_to(outside)
        outside_alias = outside.with_name("alias")
        outside_alias.symlink_to(self.skill)
        for ref in ("../../.opencode/generated", "../../.opencode/alias", "../link"):
            for field in ("output_template", "validator_path"):
                with self.subTest(ref=ref, field=field):
                    if field == "validator_path":
                        graph = self.graph_text.replace('validator = "markdown"',
                                                        f'validator = {{type = "json", schema = "{ref}"}}')
                        graph = graph.replace('required_headings = ["Result"]', '')
                    else:
                        graph = self.graph_text.replace("../templates/shared.md", ref)
                    self.assert_failure(graph, "unsafe-path", field)
        self.assert_failure(self.graph_text.replace(self.source, "workflow/link"), "unsafe-path", "skill_source")
        parent = self.root / "workflow/linked"
        parent.symlink_to(outside.parent, target_is_directory=True)
        self.assert_failure(self.graph_text.replace(self.source, "workflow/linked/generated"),
                            "unsafe-path", "skill_source")

    def test_metadata_errors_are_controlled_and_identify_the_source(self) -> None:
        for header in ("no header", "---\nname: compose", "---\nname: compose\n---",
                       "---\nname: compose\ndescription:  \n---",
                       "---\nname: compose\nname: compose\ndescription: Test\n---",
                       "---\nname: compose\ndescription: [a, b]\n---",
                       "---\nname: compose\ndescription: false\n---",
                       "---\nname: compose\ndescription: Test\nmodel: fixture\n---",
                       "---\nname: compose\ndescription: Test\nmetadata:\n  role:\n---"):
            with self.subTest(header=header):
                self.skill.write_text(header)
                self.assert_failure(self.graph_text, "invalid-skill-frontmatter", "skill_source")
        self.skill.write_bytes(b"\xff")
        self.assert_failure(self.graph_text, "invalid-skill-frontmatter", "skill_source")
        self.skill.write_text("---\nname: other\ndescription: Test\n---")
        self.assert_failure(self.graph_text, "skill-name-mismatch", "skill_source")
        for name in ("pipeline", "specromancy-alpha"):
            self.assert_failure(self.graph_text.replace('skill = "compose"', f'skill = "{name}"'),
                                "reserved-skill", "skill")

    def test_graph_binding_is_checked_before_reusing_procedure_metadata(self) -> None:
        first = self.graph_text.replace('outcome = "done"', 'outcome = "next"\ntarget = "finish"')
        second = self.graph_text[self.graph_text.index("[[phases]]"):].replace('id = "compose"', 'id = "finish"')
        self.assertEqual(self.load(first + second).phase_ids, ("compose", "finish"))
        other = "workflow/other.md"
        write_workflow_skill(self.root, source=other)
        self.assert_failure(first + second.replace(self.source, other), "conflicting-skill-source", "skill_source")
        alias = self.root / "workflow/alias.md"
        alias.symlink_to(self.skill)
        for name in ("compose", "other"):
            graph = second.replace(self.source, "workflow/alias.md").replace('skill = "compose"', f'skill = "{name}"')
            self.assert_failure(first + graph, "conflicting-skill-source", "skill_source")


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def assert_error(self, content: str, diagnostic: str) -> PipelineConfigError:
        path = self.fixture.write(content)
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(path)
        error = raised.exception
        self.assertEqual(error.code, ExitCode.INVALID_PIPELINE)
        self.assertEqual(error.details["error_code"], diagnostic)
        self.assertEqual(error.details["path"], str(path.resolve()))
        self.assertIn("remediation", error.details)
        return error

    def test_file_fixture_loads_as_immutable_domain_objects(self) -> None:
        pipeline = load_pipeline(
            WORKFLOW_FIXTURE / "workflow/pipelines/engine-example.toml", WORKFLOW_FIXTURE
        )
        self.assertEqual(pipeline.start, "research")
        self.assertEqual(pipeline.phase_ids, ("research", "plan", "implement", "review"))
        self.assertRegex(pipeline.config_hash, r"^[0-9a-f]{64}$")
        self.assertTrue(pipeline.phase("research").skill_path.is_file())
        with self.assertRaises(FrozenInstanceError):
            pipeline.version = 2  # type: ignore[misc]

    def test_table_driven_valid_fixtures_include_unrelated_phase_names(self) -> None:
        for name, expected in (
            ("config-valid-minimal", ("compose",)),
            ("config-valid-branch", ("inspect", "transform", "verify")),
            ("config-valid-loop", ("transform", "verify")),
        ):
            with self.subTest(name=name):
                fixture = FIXTURES / name
                loaded = load_pipeline(fixture / "workflow/pipeline.toml", fixture)
                self.assertEqual(loaded.phase_ids, expected)

    def test_duplicate_phase_is_rejected(self) -> None:
        duplicate = PHASE + PHASE.replace('id = "compose"', 'id = "compose"')
        self.assert_error(document(duplicate), "duplicate-phase")

    def test_malformed_toml_is_rejected_with_a_stable_diagnostic(self) -> None:
        path = self.fixture.write("schema_version = [\n")
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(path)
        self.assertEqual(raised.exception.code, ExitCode.INVALID_PIPELINE)
        self.assertEqual(raised.exception.diagnostic_code, "invalid-toml")
        self.assertNotIn("traceback", raised.exception.as_dict())

    def test_missing_start_is_rejected(self) -> None:
        self.assert_error(document(start='"missing"'), "missing-start-phase")

    def test_unreachable_phase_is_rejected(self) -> None:
        orphan = PHASE.replace('id = "compose"', 'id = "orphan"').replace(
            'skill = "compose"', 'skill = "compose"'
        )
        self.assert_error(document(PHASE + orphan), "unreachable-phase")

    def test_unknown_transition_target_is_rejected(self) -> None:
        phase = PHASE.replace('outcome = "done"', 'outcome = "next"\ntarget = "missing"')
        self.assert_error(document(phase), "unknown-transition-target")

    def test_duplicate_outcome_is_rejected(self) -> None:
        phase = PHASE + '\n[[phases.transitions]]\noutcome = "done"\n'
        self.assert_error(document(phase), "duplicate-outcome")

    def test_unbounded_cycle_is_rejected(self) -> None:
        cyclic = PHASE.replace('outcome = "done"', 'outcome = "again"\ntarget = "compose"')
        cyclic = cyclic.replace("max_visits = 1\n", "")
        self.assert_error(document(cyclic), "unbounded-cycle")

    def test_parallel_unbounded_edge_does_not_borrow_another_outcomes_bound(self) -> None:
        cyclic = PHASE.replace(
            'outcome = "done"',
            'outcome = "bounded"\ntarget = "compose"\nmax_traversals = 1'
            '\n[[phases.transitions]]\noutcome = "unbounded"\ntarget = "compose"',
        ).replace("max_visits = 1\n", "")
        self.assert_error(document(cyclic), "unbounded-cycle")

    def test_bounds_must_be_positive(self) -> None:
        changed = PHASE.replace("max_visits = 1", "max_visits = 0")
        self.assert_error(document(changed), "invalid-bound")

    def test_transition_pause_is_optional_boolean_and_hash_compatible(self) -> None:
        without_pause = load_pipeline(self.fixture.write(document(), "without.toml"))
        explicit_false = PHASE.replace(
            'outcome = "done"', 'outcome = "done"\npause = false'
        )
        with_false = load_pipeline(
            self.fixture.write(document(explicit_false), "false.toml")
        )
        self.assertFalse(without_pause.phase("compose").transitions[0].pause)
        self.assertFalse(with_false.phase("compose").transitions[0].pause)
        self.assertEqual(without_pause.config_hash, with_false.config_hash)

        paused = PHASE.replace(
            'outcome = "done"',
            'outcome = "again"\ntarget = "compose"\npause = true',
        )
        with_pause = load_pipeline(
            self.fixture.write(document(paused), "pause.toml")
        )
        self.assertTrue(with_pause.phase("compose").transitions[0].pause)
        self.assertNotEqual(without_pause.config_hash, with_pause.config_hash)

    def test_transition_pause_rejects_invalid_type_and_terminal_outcome(self) -> None:
        invalid_type = PHASE.replace(
            'outcome = "done"',
            'outcome = "again"\ntarget = "compose"\npause = "yes"',
        )
        self.assert_error(document(invalid_type), "invalid-field-type")
        terminal = PHASE.replace(
            'outcome = "done"', 'outcome = "done"\npause = true'
        )
        self.assert_error(document(terminal), "terminal-transition-pause")

    def test_published_pipeline_schema_declares_transition_pause(self) -> None:
        schema = json.loads(files("specromancy_engine").joinpath("schemas", "pipeline.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            schema["$defs"]["transition"]["properties"]["pause"],
            {"type": "boolean"},
        )

    def test_reserved_phase_id_is_rejected(self) -> None:
        phase = PHASE.replace('id = "compose"', 'id = "status"')
        self.assert_error(document(phase, start='"status"'), "reserved-phase-id")

    def test_invalid_mutation_policy_is_rejected(self) -> None:
        phase = PHASE.replace('mutation = "read-only"', 'mutation = "sometimes"')
        self.assert_error(document(phase), "invalid-mutation-policy")

    def test_non_finite_command_timeout_is_rejected(self) -> None:
        phase = PHASE.replace(
            "[[phases.transitions]]",
            '[[phases.commands]]\nargv = ["check"]\n'
            "timeout_seconds = nan\n\n[[phases.transitions]]",
        )
        self.assert_error(document(phase), "invalid-command-timeout")

    def test_allowlist_policy_requires_patterns(self) -> None:
        phase = PHASE.replace('mutation = "read-only"', 'mutation = "allowlist"')
        self.assert_error(document(phase), "empty-field")

    def test_missing_skill_and_template_are_rejected(self) -> None:
        self.assert_error(
            document(PHASE.replace("workflow/skills/compose/", "workflow/skills/missing/")),
            "missing-file",
        )
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "templates/missing.md"',
        )
        self.assert_error(document(phase), "missing-file")

    def test_legacy_skill_resolution_and_hash_do_not_depend_on_procedure_bytes(self) -> None:
        legacy = self.fixture.root / ".agents/skills/compose/SKILL.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes((self.fixture.root / "workflow/skills/compose/SKILL.md").read_bytes())
        path = self.fixture.write(document().replace('skill_source = "workflow/skills/compose/SKILL.md"\n', ""))
        first = load_pipeline(path)
        skill = self.fixture.root / ".agents/skills/compose/SKILL.md"
        self.assertEqual(first.phase("compose").skill_path, skill.resolve())
        self.assertNotIn("skill_source", json.loads(first.canonical_json)["phases"][0])
        skill.write_bytes(skill.read_bytes() + b"\nUpdated procedure.\n")
        self.assertEqual(load_pipeline(path).canonical_json, first.canonical_json)
        self.assertEqual(load_pipeline(path).config_hash, first.config_hash)
        skill.unlink()
        with self.assertRaises(PipelineConfigError) as caught:
            load_pipeline(path)
        self.assertEqual(caught.exception.diagnostic_code, "missing-file")
        self.assertEqual(caught.exception.details["field"], "skill")
        self.assertEqual(caught.exception.details["value"], ".agents/skills/compose/SKILL.md")

    def test_unsafe_template_and_output_paths_are_rejected(self) -> None:
        (self.fixture.root / "outside.md").write_text("# Safe parent\n", encoding="utf-8")
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "../../../outside.md"',
        )
        self.assert_error(document(phase), "unsafe-path")
        unsafe_output = PHASE.replace(
            'output_name = "{visit:03}-result.md"', 'output_name = "../result.md"'
        )
        self.assert_error(
            document(unsafe_output),
            "unsafe-output-path",
        )

    def test_template_parent_segments_may_stay_inside_repository(self) -> None:
        template = self.fixture.root / "workflow/shared.md"
        template.write_text("# Shared\n", encoding="utf-8")
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "../shared.md"',
        )
        loaded = load_pipeline(self.fixture.write(document(phase)))
        self.assertEqual(loaded.phase("compose").output_template_path, template.resolve())

    def test_template_symlink_cannot_escape_repository(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "target.md"
            target.write_text("# Outside\n", encoding="utf-8")
            link = self.fixture.root / "workflow/config" / "templates" / "link.md"
            link.symlink_to(target)
            phase = PHASE.replace(
                'output_name = "{visit:03}-result.md"',
                'output_name = "{visit:03}-result.md"\n'
                'output_template = "templates/link.md"',
            )
            self.assert_error(document(phase), "unsafe-path")

    def test_input_must_have_a_possible_producer(self) -> None:
        phase = PHASE.replace('inputs = ["request"]', 'inputs = ["latest:compose"]')
        self.assert_error(document(phase), "unavailable-input")

    def test_input_producer_must_dominate_all_incoming_routes(self) -> None:
        phase = textwrap.dedent(
            """
            [[phases]]
            id = "compose"
            skill = "compose"
            skill_source = "workflow/skills/compose/SKILL.md"
            inputs = ["request"]
            output_name = "compose.md"
            mutation = "read-only"
            completion_criteria = ["Choose a route."]
            validator = "file"
            approval_conditions = []
            stop_conditions = []
            max_visits = 1
            [[phases.transitions]]
            outcome = "direct"
            target = "consume"
            [[phases.transitions]]
            outcome = "indirect"
            target = "produce"

            [[phases]]
            id = "produce"
            skill = "compose"
            skill_source = "workflow/skills/compose/SKILL.md"
            inputs = ["request"]
            output_name = "produce.md"
            mutation = "read-only"
            completion_criteria = ["Produce."]
            validator = "file"
            approval_conditions = []
            stop_conditions = []
            max_visits = 1
            [[phases.transitions]]
            outcome = "next"
            target = "consume"

            [[phases]]
            id = "consume"
            skill = "compose"
            skill_source = "workflow/skills/compose/SKILL.md"
            inputs = ["latest:produce"]
            output_name = "consume.md"
            mutation = "read-only"
            completion_criteria = ["Consume."]
            validator = "file"
            approval_conditions = []
            stop_conditions = []
            max_visits = 1
            [[phases.transitions]]
            outcome = "done"
            """
        )
        self.assert_error(document(phase), "unavailable-input")

    def test_visit_input_must_be_available_before_consumer(self) -> None:
        phase = PHASE.replace('inputs = ["request"]', 'inputs = ["visit:1"]')
        self.assert_error(document(phase), "unavailable-input")

    def test_terminal_outcome_cannot_also_be_a_phase(self) -> None:
        phase = PHASE.replace('id = "compose"', 'id = "done"')
        self.assert_error(document(phase, start='"done"'), "terminal-outcome-phase")

    def test_diagnostic_serializes_without_traceback_data(self) -> None:
        error = self.assert_error(document(schema_version="2"), "unsupported-schema-version")
        payload = error.as_dict()
        self.assertEqual(payload["code"], ExitCode.INVALID_PIPELINE)
        json.dumps(payload)
        self.assertNotIn("traceback", payload)

    def test_hash_is_stable_across_toml_key_order(self) -> None:
        first = self.fixture.write(document(), "first.toml")
        reordered_phase = PHASE.replace(
            'id = "compose"\nskill = "compose"',
            'skill = "compose"\nid = "compose"',
        )
        reordered = self.fixture.write(
            textwrap.dedent(
                f"""
                artifact_pattern = "artifacts/{{visit:03}}-{{phase}}.md"
                terminal_outcomes = ["done"]
                start = "compose"
                version = 1
                id = "fixture"
                schema_version = 1
                {reordered_phase}
                """
            ),
            "second.toml",
        )
        self.assertEqual(load_pipeline(first).config_hash, load_pipeline(reordered).config_hash)

    def test_hash_changes_after_semantic_edit_and_drift_is_actionable(self) -> None:
        first = load_pipeline(self.fixture.write(document(), "first.toml"))
        changed_phase = PHASE.replace(
            "Write the result.", "Write a reviewed result."
        )
        changed = load_pipeline(
            self.fixture.write(document(changed_phase), "changed.toml")
        )
        self.assertNotEqual(first.config_hash, changed.config_hash)
        with self.assertRaises(PipelineConfigError) as raised:
            require_pipeline_hash(changed, first.config_hash)
        self.assertEqual(raised.exception.diagnostic_code, "pipeline-hash-mismatch")

    def test_declared_and_resolved_paths_are_retained(self) -> None:
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "templates/result.md"',
        )
        loaded = load_pipeline(self.fixture.write(document(phase)))
        configured = loaded.phase("compose")
        self.assertEqual(configured.output_template, "templates/result.md")
        self.assertEqual(
            configured.output_template_path,
            (self.fixture.root / "workflow/config" / "templates" / "result.md").resolve(),
        )

    def test_unsupported_json_schema_keyword_is_rejected_at_load(self) -> None:
        schema = self.fixture.root / "workflow/config" / "result.schema.json"
        schema.write_text('{"type":"string","minLength":1}', encoding="utf-8")
        phase = PHASE.replace(
            'validator = "file"',
            'validator = { type = "json", schema = "result.schema.json" }',
        )
        self.assert_error(document(phase), "unsupported-json-schema")

    def test_root_alias_discovery_and_failure_precedence_are_preserved(self) -> None:
        path = self.fixture.write(document())
        root = self.fixture.root
        expected = load_pipeline(path)
        self.assertEqual(load_pipeline(path, root), expected)
        self.assertEqual(load_pipeline(path, root=root), expected)
        with self.assertRaisesRegex(TypeError, "pass repository_root or root, not both"):
            load_pipeline(path, root, root=root)
        missing = path.with_name("missing.toml")
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(missing, root, root=root)
        self.assertEqual(raised.exception.diagnostic_code, "pipeline-not-found")
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(path, missing)
        self.assertEqual(raised.exception.diagnostic_code, "invalid-repository-root")
        self.assertEqual(raised.exception.details["value"], str(missing.resolve()))
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(path, root / "workflow/skills")
        self.assertEqual(raised.exception.diagnostic_code, "pipeline-outside-repository")
        (root / ".git").rmdir()
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(path)
        self.assertEqual(raised.exception.diagnostic_code, "repository-root-not-found")
        self.assertNotIn("value", raised.exception.details)
        self.assertEqual(load_pipeline(path, root=root), expected)

    def test_missing_diagnostic_values_remain_distinct_from_explicit_null(self) -> None:
        options = {"path": self.fixture.path, "remediation": "Correct the value."}
        omitted = PipelineConfigError("example", "Example", **options)
        explicit = PipelineConfigError("example", "Example", value=None, **options)
        self.assertNotIn("value", omitted.as_dict()["details"])
        self.assertIsNone(explicit.as_dict()["details"]["value"])
        unknown = self.assert_error("extra = true\n" + document(), "unknown-field")
        self.assertEqual(unknown.details["field"], "extra")
        self.assertIs(unknown.details["value"], True)

    def test_multiple_invalid_fields_preserve_the_first_complete_diagnostic(self) -> None:
        cases = [
            ("a_extra = true\n" + document(),
             "z_extra = false\na_extra = true\n" + document(schema_version="false"),
             "unknown-field", "a_extra"),
            (document(schema_version="false"),
             document(schema_version="false", id="42"), "invalid-field-type", "schema_version"),
            (document(PHASE.replace('id = "compose"', 'id = "Bad"')),
             document(PHASE.replace('id = "compose"', 'id = "Bad"\nextra = true')),
             "invalid-identifier", "id"),
            (document(PHASE.replace("workflow/skills/compose/", "workflow/skills/missing/")),
             document(PHASE.replace("workflow/skills/compose/", "workflow/skills/missing/")
                      .replace('inputs = ["request"]', 'inputs = false')),
             "missing-file", "skill_source"),
            (document(PHASE.replace('validator = "file"', 'validator = "unknown"')),
             document(PHASE.replace('validator = "file"', 'validator = "unknown"\ncommands = false')),
             "invalid-validator", "validator"),
            (document(PHASE.replace('validator = "file"', 'validator = "file"\ncommands = false')),
             document(PHASE.replace('validator = "file"', 'validator = "file"\ncommands = false')
                      .replace('outcome = "done"', 'outcome = false')),
             "invalid-field-type", "commands"),
        ]
        for single, multiple, diagnostic, field in cases:
            with self.subTest(field=field):
                expected = self.assert_error(single, diagnostic)
                self.assertEqual(expected.details["field"], field)
                actual = self.assert_error(multiple, diagnostic)
                self.assertEqual(actual.as_dict(), expected.as_dict())

    def test_schema_paths_and_dependencies_are_resolved_on_every_load(self) -> None:
        schema = self.fixture.root / "workflow/shared.schema.json"
        schema.write_text('{"type":"string"}', encoding="utf-8")
        phase = PHASE.replace(
            'validator = "file"',
            'validator = { type = "json", schema = "../shared.schema.json" }',
        )
        path = self.fixture.write(document(phase))
        first = load_pipeline(path)
        self.assertEqual(first.phases[0].validator.resolved_path, schema.resolve())
        schema.write_text('{"type":"integer"}', encoding="utf-8")
        second = load_pipeline(path)
        self.assertEqual(second.phases[0].validator.json_schema, {"type": "integer"})
        self.assertEqual(first.config_hash, second.config_hash)
        schema.write_text('{"minLength":1}', encoding="utf-8")
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(path)
        self.assertEqual(raised.exception.diagnostic_code, "unsupported-json-schema")
        self.assertEqual(raised.exception.details["field"], "validator_path")
        self.assertEqual(raised.exception.details["value"], "../shared.schema.json")
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "schema.json"
            external.write_text('{}', encoding="utf-8")
            schema.unlink()
            schema.symlink_to(external)
            with self.assertRaises(PipelineConfigError) as raised:
                load_pipeline(path)
            self.assertEqual(raised.exception.diagnostic_code, "unsafe-path")


if __name__ == "__main__":
    unittest.main()
