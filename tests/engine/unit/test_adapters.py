from __future__ import annotations

import io
import json
import tempfile
import textwrap
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from specromancy_engine._adapters import adapter_ownership
from specromancy_engine._adapters import adapter_sources
from specromancy_engine._adapters.adapter_rendering import render_release_launch, render_release_template
from specromancy_engine._adapters.adapter_sources import load_release_template
from specromancy_engine.adapters import (
    MANIFEST_PATH,
    AdapterError,
    generate_adapters,
    render_adapters,
)
from specromancy_engine.cli import adapter_command_metadata, main
from specromancy_engine.config import load_pipeline
from specromancy_engine.registry import PipelineRegistry, load_registry
from specromancy_engine.exit_codes import ExitCode
from specromancy_engine.hashing import sha256_bytes


class ReleaseTemplateTests(unittest.TestCase):
    def test_release_inputs_omit_producer_phase_names_and_harness_source_paths(self) -> None:
        for source in adapter_sources.capture_release_inputs():
            with self.subTest(source=source.path):
                self.assertNotRegex(source.content, rb"\b(research|plan|implement|review)\b")
                self.assertNotIn(b".agents/skills/", source.content)

    def test_only_allowlisted_resource_names_reach_package_lookup(self) -> None:
        with patch.object(adapter_sources, "files") as lookup:
            for name in ("AGENTS.md", ".agents/skills/pipeline/SKILL.md", "../launch.md",
                         "/tmp/launch.md", "resources/adapters/launch.md", "extra.md"):
                with self.subTest(name=name), self.assertRaisesRegex(AdapterError, "unknown"):
                    load_release_template(name)
            lookup.assert_not_called()

    def test_missing_and_unreadable_resources_report_logical_id(self) -> None:
        with patch.object(adapter_sources, "files") as lookup:
            read = lookup.return_value.joinpath.return_value.read_bytes
            for error in (FileNotFoundError(), PermissionError()):
                read.side_effect = error
                with self.subTest(error=error), self.assertRaises(AdapterError) as caught:
                    load_release_template("launch.md")
                self.assertEqual(caught.exception.details, {
                    "path": "@package/specromancy_engine/resources/adapters/launch.md",
                })

    def test_hash_uses_raw_bytes_while_render_normalizes_and_substitutes_once(self) -> None:
        packaged = load_release_template("instructions.md")
        raw = packaged.content.replace(b"\n", b"\r\n") + b"\r\n"
        with patch.object(adapter_sources, "files") as lookup:
            lookup.return_value.joinpath.return_value.read_bytes.return_value = raw
            source = load_release_template("instructions.md")
        body = "Keep {phase}, %{instructions}, 50%, $0, $1, $2, and $ARGUMENTS.\r\n\r\n"
        self.assertEqual(source.record()["sha256"], sha256_bytes(raw))
        self.assertNotEqual(source.record(), packaged.record())
        rendered = render_release_template(source, template_id=source.path, instructions=body)
        self.assertEqual(rendered, render_release_template(
            packaged, template_id=packaged.path, instructions=body,
        ))
        self.assertTrue(rendered.endswith("\n\n" + body.rstrip("\r\n") + "\n"))

    def test_missing_unknown_and_malformed_template_fields_are_controlled(self) -> None:
        source = load_release_template("instructions.md")
        with self.assertRaises(AdapterError) as caught:
            render_release_template(source, template_id=source.path, typo="unused")
        self.assertEqual(caught.exception.details, {
            "path": source.path, "missing": ["instructions"], "unknown": ["typo"],
        })
        for content in (b"%{unclosed", b"\xff"):
            with self.subTest(content=content), self.assertRaises(AdapterError) as caught:
                render_release_template(replace(source, content=content))
            self.assertEqual(caught.exception.details["path"], source.path)

    def test_phase_wrapper_exposes_only_metadata_and_canonical_reference(self) -> None:
        phase = load_release_template("phase.md")
        path = "workflow/skills/compose/SKILL.md"
        metadata = "name: compose\ndescription: Compose the result."
        wrapper = render_release_template(phase, template_id=phase.path,
                                          skill_source=path, validated_metadata=metadata)
        self.assertIn(metadata + "\n---\n", wrapper)
        self.assertIn(f"Load `{path}` from the consumer repository root", wrapper)
        self.assertIn("directory containing the canonical file", wrapper)
        self.assertIn(phase.path, wrapper)
        with self.assertRaises(AdapterError) as caught:
            render_release_template(phase, template_id=phase.path, skill_source=path,
                                    validated_metadata=metadata, body="private phase procedure")
        self.assertEqual(caught.exception.details["unknown"], ["body"])

    def test_launch_embeds_the_whole_orchestrator_and_bound_identity(self) -> None:
        orchestrator = load_release_template("orchestrator.md")
        launch = render_release_launch("example", load_release_template("launch.md"), orchestrator)
        self.assertIn(render_release_template(orchestrator, pipeline_id="example"), launch)
        self.assertIn("specromancy init DESCRIPTION --pipeline example --json", launch)
        self.assertIn("specromancy status RUN_ID --json", launch)
        self.assertIn("pause, approval, block, validation failure,", launch)
        self.assertIn("specromancy resume RUN_ID --json", launch)
        self.assertNotIn(".agents/", launch)

    def test_command_variants_preserve_the_supplied_invocation(self) -> None:
        for harness, invocation in (
            ("claude", 'specromancy init "$1" --pipeline "$0" --json'),
            ("copilot", "specromancy init DESCRIPTION --pipeline PIPELINE_ID --json"),
            ("opencode", 'specromancy init "$2" --pipeline "$1" --json'),
        ):
            with self.subTest(harness=harness):
                source = load_release_template(f"command-{harness}.md")
                values = {"description": "Start a run.", "follow": "Retain $ARGUMENTS.",
                          "invocation": invocation, "template_id": source.path}
                if harness != "opencode":
                    values["arguments"] = "PIPELINE_ID DESCRIPTION"
                wrapper = render_release_template(source, **values)
                self.assertIn(f"`{invocation}`", wrapper)
                self.assertIn("Retain $ARGUMENTS.", wrapper)
                self.assertEqual("argument-hint:" in wrapper, harness != "opencode")
                self.assertEqual("agent: agent" in wrapper, harness == "copilot")


class AdapterFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        (self.root / "AGENTS.md").write_text(
            "# Repository instructions\n\n- Keep workflow logic canonical.\n",
            encoding="utf-8",
        )
        self.write_skill("compose")
        self.write_skill("pipeline")
        self.pipeline_path = self.root / "workflow/pipelines/adapter-fixture.toml"
        self.pipeline_path.parent.mkdir(parents=True)
        (self.root / "workflow/pipelines.toml").write_text(
            'schema_version = 1\n[[pipelines]]\nid = "adapter-fixture"\npath = "pipelines/adapter-fixture.toml"\n', encoding="utf-8"
        )
        self.pipeline_path.write_text(
            textwrap.dedent(
                """
                schema_version = 1
                id = "adapter-fixture"
                version = 1
                start = "compose"
                terminal_outcomes = ["done"]
                artifact_pattern = "artifacts/{visit:03}-{phase}.md"
                allow_non_git = true
                [[phases]]
                id = "compose"
                skill = "compose"
                inputs = ["request"]
                output_name = "{visit:03}-result.md"
                mutation = "read-only"
                completion_criteria = ["Write a result."]
                validator = "file"
                approval_conditions = []
                stop_conditions = []
                max_visits = 1
                [[phases.transitions]]
                outcome = "done"
                """
            ).lstrip(),
            encoding="utf-8",
        )

    def close(self) -> None:
        self.temporary.cleanup()

    def write_skill(self, name: str) -> Path:
        path = self.root / ".agents" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            textwrap.dedent(
                f"""
                ---
                name: {name}
                description: Use when the fixture needs {name}.
                license: MIT
                compatibility: Specromancy pipeline schema version 1.
                metadata:
                  role: phase
                ---

                # {name.title()}

                Follow the emitted action packet.
                """
            ).lstrip(),
            encoding="utf-8",
        )
        return path

    def pipeline(self):
        return load_pipeline(self.pipeline_path, self.root)

    def generate(self, *, check: bool = False):
        pipeline = self.pipeline()
        return generate_adapters(
            self.root,
            load_registry(self.root),
            adapter_command_metadata(pipeline.phase_ids),
            check=check,
        )

    def snapshot(self) -> dict[str, bytes]:
        manifest_path = self.root / MANIFEST_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        paths = [entry["path"] for entry in manifest["generated"]]
        paths.append(MANIFEST_PATH)
        return {path: (self.root / path).read_bytes() for path in paths}


class AdapterGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = AdapterFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_two_generations_are_byte_identical(self) -> None:
        self.fixture.generate()
        first = self.fixture.snapshot()
        self.fixture.generate()
        self.assertEqual(self.fixture.snapshot(), first)
        self.fixture.generate(check=True)

    def test_adapter_text_normalization_preserves_outputs_and_source_hashes(self) -> None:
        self.fixture.generate()
        expected = self.fixture.snapshot()
        paths = [self.fixture.root / "AGENTS.md",
                 self.fixture.root / ".agents/skills/compose/SKILL.md",
                 self.fixture.root / ".agents/skills/pipeline/SKILL.md"]
        originals = {path: path.read_bytes().rstrip(b"\n") for path in paths}
        for newline, trailing in ((b"\r\n", 3), (b"\r", 2), (b"\n", 0)):
            with self.subTest(newline=newline, trailing=trailing):
                for path, content in originals.items():
                    path.write_bytes(content.replace(b"\n", newline) + newline * trailing)
                self.fixture.generate(check=True)
                self.fixture.generate()
                self.assertEqual(self.fixture.snapshot(), expected)

    def test_missing_root_instructions_are_a_controlled_source_error(self) -> None:
        # Legacy source requirement; Stage 20 replaces it with workflow/instructions.md.
        (self.fixture.root / "AGENTS.md").unlink()
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.message, "cannot read canonical adapter source")
        self.assertEqual(caught.exception.details["path"], "AGENTS.md")
        self.assertFalse((self.fixture.root / MANIFEST_PATH).exists())

    def test_cli_captures_graphs_and_canonical_text_once_per_invocation(self) -> None:
        original_load = PipelineRegistry.load_all
        original_text = adapter_sources._normalized_text
        for _ in range(2):
            with (
                patch.object(PipelineRegistry, "load_all", autospec=True, side_effect=original_load) as graphs,
                patch.object(adapter_sources, "_normalized_text", wraps=original_text) as texts,
            ):
                output, errors = io.StringIO(), io.StringIO()
                code = main(
                    ["--root", str(self.fixture.root), "--json", "adapters", "generate"],
                    stdout=output, stderr=errors,
                )
                self.assertEqual(code, ExitCode.SUCCESS, errors.getvalue())
                self.assertEqual(graphs.call_count, 1)
                self.assertEqual(
                    [call.args[1] for call in texts.call_args_list],
                    ["AGENTS.md", ".agents/skills/compose/SKILL.md", ".agents/skills/pipeline/SKILL.md"],
                )

    def test_check_creates_no_temporary_files_and_preserves_tree_metadata(self) -> None:
        self.fixture.generate()

        def snapshot():
            return {
                path.relative_to(self.fixture.root).as_posix():
                    (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.fixture.root.rglob("*") if path.is_file()
            }

        before = snapshot()
        with patch.object(adapter_ownership.tempfile, "mkstemp", side_effect=AssertionError("write")):
            self.fixture.generate(check=True)
        self.assertEqual(snapshot(), before)

    def test_stale_file_changed_after_preflight_is_not_deleted(self) -> None:
        extra = self.fixture.write_skill("extra")
        self.fixture.generate()
        extra.unlink()
        stale = self.fixture.root / ".claude/skills/extra/SKILL.md"
        manifest = (self.fixture.root / MANIFEST_PATH).read_bytes()
        (self.fixture.root / "AGENTS.md").write_text("New instructions\n")
        original_write = adapter_ownership._atomic_write

        def overlapping_write(root, relative, content):
            stale.write_text("Concurrent edit\n")
            original_write(root, relative, content)

        with patch.object(adapter_ownership, "_atomic_write", side_effect=overlapping_write):
            with self.assertRaises(AdapterError) as caught:
                self.fixture.generate()
        self.assertEqual(caught.exception.message, "stale generated adapter changed during generation")
        self.assertEqual(stale.read_text(), "Concurrent edit\n")
        self.assertEqual((self.fixture.root / MANIFEST_PATH).read_bytes(), manifest)

    def test_public_render_facade_preserves_source_diagnostics(self) -> None:
        registry = load_registry(self.fixture.root)
        metadata = adapter_command_metadata(["compose"])
        path = self.fixture.root / ".agents/skills/pipeline/SKILL.md"
        path.unlink()
        with self.assertRaises(AdapterError) as caught:
            render_adapters(self.fixture.root, registry, metadata)
        self.assertEqual(caught.exception.message, "canonical pipeline orchestrator skill is missing")
        self.assertEqual(caught.exception.details, {"path": ".agents/skills/pipeline/SKILL.md"})

    def test_check_detects_changes_without_writing_generated_output(self) -> None:
        cases = ("modified", "missing", "unexpected", "canonical", "no-manifest")
        for case in cases:
            with self.subTest(case=case):
                fixture = AdapterFixture()
                try:
                    fixture.generate()
                    before = fixture.snapshot()
                    if case == "modified":
                        path = fixture.root / ".claude" / "CLAUDE.md"
                        path.write_text("changed\n", encoding="utf-8")
                    elif case == "missing":
                        (fixture.root / ".opencode" / "commands" / "specromancy-status.md").unlink()
                    elif case == "unexpected":
                        path = fixture.root / ".opencode" / "commands" / "specromancy-extra.md"
                        path.write_text("extra\n", encoding="utf-8")
                    elif case == "no-manifest":
                        (fixture.root / MANIFEST_PATH).unlink()
                    else:
                        with (fixture.root / "AGENTS.md").open("a", encoding="utf-8") as stream:
                            stream.write("- A new canonical rule.\n")
                    changed_before_check = {
                        path: (fixture.root / path).read_bytes()
                        for path in before
                        if (fixture.root / path).is_file()
                    }
                    with patch.object(adapter_ownership.tempfile, "mkstemp", side_effect=AssertionError("write")), self.assertRaises(AdapterError) as caught:
                        fixture.generate(check=True)
                    self.assertEqual(caught.exception.code, ExitCode.ADAPTER_DRIFT)
                    changed_after_check = {
                        path: (fixture.root / path).read_bytes()
                        for path in changed_before_check
                    }
                    self.assertEqual(changed_after_check, changed_before_check)
                    if case == "no-manifest":
                        self.assertFalse((fixture.root / MANIFEST_PATH).exists())
                finally:
                    fixture.close()

    def test_check_without_any_outputs_does_not_create_files(self) -> None:
        before = {path.relative_to(self.fixture.root): path.read_bytes()
                  for path in self.fixture.root.rglob("*") if path.is_file()}
        with patch.object(adapter_ownership.tempfile, "mkstemp", side_effect=AssertionError("write")), self.assertRaises(AdapterError):
            self.fixture.generate(check=True)
        self.assertEqual({path.relative_to(self.fixture.root): path.read_bytes()
                          for path in self.fixture.root.rglob("*") if path.is_file()}, before)

    def test_generation_restores_edited_current_owned_output(self) -> None:
        self.fixture.generate()
        original = self.fixture.snapshot()
        path = self.fixture.root / ".claude/CLAUDE.md"
        path.write_text("User edit\n")
        before = self.fixture.snapshot()
        with self.assertRaises(AdapterError):
            self.fixture.generate(check=True)
        self.assertEqual(self.fixture.snapshot(), before)
        self.fixture.generate()
        self.assertEqual(self.fixture.snapshot(), original)

    def test_generation_never_overwrites_an_unowned_destination(self) -> None:
        path = self.fixture.root / ".claude" / "CLAUDE.md"
        path.parent.mkdir(parents=True)
        path.write_text("user owned\n", encoding="utf-8")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.details["unowned"], [".claude/CLAUDE.md"])
        self.assertEqual(path.read_text(encoding="utf-8"), "user owned\n")
        self.assertFalse((self.fixture.root / MANIFEST_PATH).exists())

    def test_identical_unowned_output_is_not_adopted(self) -> None:
        relative = ".claude/CLAUDE.md"
        expected = render_adapters(
            self.fixture.root, load_registry(self.fixture.root),
            adapter_command_metadata(["compose"]),
        )[relative]
        path = self.fixture.root / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(expected)
        with patch.object(adapter_ownership, "_atomic_write", side_effect=AssertionError("write")):
            with self.assertRaises(AdapterError) as caught:
                self.fixture.generate()
        self.assertEqual(caught.exception.details["unowned"], [relative])
        self.assertEqual(path.read_bytes(), expected)
        self.assertFalse((self.fixture.root / MANIFEST_PATH).exists())

    def test_v2_manifest_cannot_claim_root_instructions_or_canonical_skills(self) -> None:
        self.fixture.generate()
        manifest_path = self.fixture.root / MANIFEST_PATH
        original = manifest_path.read_bytes()
        for relative in ("AGENTS.md", ".agents/skills/pipeline/SKILL.md",
                         ".agents/skills/compose/SKILL.md"):
            with self.subTest(path=relative):
                source = self.fixture.root / relative
                content = source.read_bytes()
                manifest = json.loads(original)
                manifest["generated"].append({
                    "path": relative, "sha256": sha256_bytes(content), "target": "codex",
                })
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                before = self.fixture.snapshot()
                for check in (False, True):
                    with patch.object(adapter_ownership, "_atomic_write", side_effect=AssertionError("write")):
                        with self.assertRaises(AdapterError) as caught:
                            self.fixture.generate(check=check)
                    if check:
                        # v2 check compares bytes; Stage 19 adds ownership validation here.
                        self.assertEqual(caught.exception.message, "generated adapter drift detected")
                    else:
                        self.assertIn("outside generated adapter locations", caught.exception.message)
                    self.assertEqual(self.fixture.snapshot(), before)
                    self.assertEqual(source.read_bytes(), content)

    def test_stale_unchanged_file_is_removed(self) -> None:
        extra = self.fixture.write_skill("extra")
        self.fixture.generate()
        generated = self.fixture.root / ".claude" / "skills" / "extra" / "SKILL.md"
        self.assertTrue(generated.is_file())
        extra.unlink()
        result = self.fixture.generate()
        self.assertFalse(generated.exists())
        self.assertEqual(result["adapters"]["removed"], [".claude/skills/extra/SKILL.md"])

    def test_stale_modified_file_is_preserved_with_an_error(self) -> None:
        extra = self.fixture.write_skill("extra")
        self.fixture.generate()
        generated = self.fixture.root / ".claude" / "skills" / "extra" / "SKILL.md"
        generated.write_text("user change\n", encoding="utf-8")
        extra.unlink()
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(
            caught.exception.details["stale_modified"],
            [".claude/skills/extra/SKILL.md"],
        )
        self.assertEqual(generated.read_text(encoding="utf-8"), "user change\n")

    def test_manifest_records_targets_relative_paths_and_content_hashes(self) -> None:
        self.fixture.generate()
        manifest = json.loads(
            (self.fixture.root / MANIFEST_PATH).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["generator"], {
            "name": "specromancy", "version": 2,
            "command": "specromancy adapters generate",
        })
        modes = {entry["name"]: entry["mode"] for entry in manifest["targets"]}
        self.assertEqual(
            modes,
            {
                "claude": "generated",
                "codex": "native",
                "copilot": "generated",
                "hermes": "native",
                "opencode": "generated",
            },
        )
        for target in manifest["targets"]:
            if target["mode"] == "native":
                self.assertEqual(target["discovery_paths"], [".agents/skills/specromancy-adapter-fixture/SKILL.md"])
        for entry in manifest["generated"]:
            path = entry["path"]
            self.assertFalse(Path(path).is_absolute())
            self.assertNotIn("..", Path(path).parts)
            self.assertEqual(
                entry["sha256"], sha256_bytes((self.fixture.root / path).read_bytes())
            )

    def test_tampered_manifest_cannot_claim_an_unrelated_path(self) -> None:
        self.fixture.generate()
        unrelated = self.fixture.root / "README.md"
        unrelated.write_text("keep me\n", encoding="utf-8")
        manifest_path = self.fixture.root / MANIFEST_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["generated"].append(
            {
                "path": "README.md",
                "sha256": sha256_bytes(unrelated.read_bytes()),
                "target": "claude",
            }
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertIn("outside generated adapter locations", caught.exception.message)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me\n")

    def test_unmanaged_skill_support_file_does_not_count_as_drift(self) -> None:
        self.fixture.generate()
        support = self.fixture.root / ".claude" / "skills" / "compose" / "notes.md"
        support.write_text("user support file\n", encoding="utf-8")
        self.fixture.generate(check=True)

    def test_cli_check_reports_json_drift_and_writes_nothing(self) -> None:
        common = [
            "--root",
            str(self.fixture.root),
            "--json",
            "adapters",
            "generate",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        self.assertEqual(main(common, stdout=stdout, stderr=stderr), ExitCode.SUCCESS)
        changed = self.fixture.root / ".github" / "copilot-instructions.md"
        changed.write_text("changed\n", encoding="utf-8")
        before = changed.read_bytes()
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main([*common, "--check"], stdout=stdout, stderr=stderr)
        self.assertEqual(code, ExitCode.ADAPTER_DRIFT)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertIn(".github/copilot-instructions.md", payload["details"]["modified"])
        self.assertEqual(changed.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
