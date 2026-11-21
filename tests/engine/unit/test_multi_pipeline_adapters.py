from __future__ import annotations

import json
import shutil
from importlib.resources import files
from pathlib import Path
import unittest
from unittest.mock import patch

from specromancy_engine.adapters import (
    MANIFEST_PATH, AdapterError, generate_adapters, render_adapters,
)
from specromancy_engine._adapters import adapter_sources
from specromancy_engine.config import PipelineConfigError
from specromancy_engine.hashing import sha256_bytes
from specromancy_engine._adapters.adapter_rendering import render_workflow_sources, workflow_manifest
from specromancy_engine._adapters.adapter_sources import capture_workflow_sources
from specromancy_engine.cli import adapter_command_metadata
from specromancy_engine.registry import load_adapter_registry, load_registry
from tests.engine.support import MultiPipelineFixture, select_harnesses, write_workflow_skill


class MultiPipelineAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MultiPipelineFixture()
        self.root = self.fixture.root

    def tearDown(self) -> None:
        self.fixture.close()

    def generate(self, *, check: bool = False) -> dict:
        registry = load_registry(self.root)
        phases = sorted({phase for graph in registry.load_all() for phase in graph.phase_ids})
        return generate_adapters(self.root, registry, adapter_command_metadata(phases), check=check)

    def snapshot(self) -> dict[str, bytes]:
        manifest = self.root / "adapters/manifest.json"
        entries = json.loads(manifest.read_text())["generated"]
        return {entry["path"]: (self.root / entry["path"]).read_bytes() for entry in entries} | {"adapters/manifest.json": manifest.read_bytes()}

    def test_registered_launch_skills_are_discoverable_and_do_not_hash_themselves(self) -> None:
        self.generate()
        first = self.snapshot()
        manifest = json.loads(first["adapters/manifest.json"])
        sources = manifest["canonical_source"]["inputs"]
        self.assertEqual(sum(item["kind"] == "validated-pipeline" for item in sources), 2)
        self.assertEqual(sum(item["kind"] == "pipeline-dependency" for item in sources), 1)
        self.assertFalse(any("skills/specromancy-" in item["path"] for item in sources))
        self.assertTrue(any(item["kind"] == "validated-registry" for item in sources))
        for pipeline_id in ("alpha", "beta"):
            relative = f".agents/skills/specromancy-{pipeline_id}/SKILL.md"
            text = first[relative].decode()
            self.assertIn(f"`specromancy init DESCRIPTION --pipeline {pipeline_id} --json`", text)
            self.assertNotIn("bin/specromancy", text)
            self.assertIn("specromancy resume RUN_ID --json", text)
            self.assertEqual(first[f".claude/skills/specromancy-{pipeline_id}/SKILL.md"], first[relative])
        native = {item["name"]: item for item in manifest["targets"] if item["mode"] == "native"}
        self.assertEqual(native["codex"]["discovery_paths"], native["hermes"]["discovery_paths"])
        self.assertEqual(native["codex"]["discovery_paths"], [
            f".agents/skills/{name}/SKILL.md" for name in ("compose", "pipeline", "specromancy-alpha", "specromancy-beta")
        ])
        self.fixture.register("beta", "alpha")
        self.generate()
        self.assertEqual(self.snapshot(), first)
        self.generate(check=True)

    def test_render_and_hash_share_captured_bytes_after_sources_change(self) -> None:
        registry = load_registry(self.root)
        sources = capture_workflow_sources(self.root, registry, None)
        rendered = render_workflow_sources(sources)
        manifest = workflow_manifest(sources, rendered)
        for relative in (
            "workflow/instructions.md", "workflow/skills/compose/SKILL.md",
            "workflow/templates/shared.md", "workflow/pipelines/beta.toml",
        ):
            path = self.root / relative
            path.write_bytes(path.read_bytes() + b"\n# A later source edit\n")
        self.assertEqual(render_workflow_sources(sources), rendered)
        self.assertEqual(workflow_manifest(sources, rendered), manifest)
        fresh = capture_workflow_sources(self.root, registry, None)
        self.assertNotEqual(workflow_manifest(fresh, render_workflow_sources(fresh)), manifest)

    def test_renamed_registration_replaces_only_its_owned_launch_skills(self) -> None:
        self.generate()
        self.fixture.add_pipeline("renamed", "inspect")
        self.fixture.register("alpha", "renamed")
        result = self.generate()
        self.assertEqual(set(result["adapters"]["removed"]), {
            f"{directory}/specromancy-beta/SKILL.md"
            for directory in (".agents/skills", ".claude/skills")
        })
        for directory in (".agents/skills", ".claude/skills"):
            self.assertTrue((self.root / directory / "specromancy-renamed/SKILL.md").is_file())
        self.generate(check=True)

    def test_registration_add_and_remove_updates_only_owned_launch_skills(self) -> None:
        self.generate()
        self.fixture.add_pipeline("gamma", "compose")
        self.fixture.register("alpha", "beta", "gamma")
        self.generate()
        self.assertTrue((self.root / ".agents/skills/specromancy-gamma/SKILL.md").is_file())
        canonical = self.root / "workflow/skills/compose/SKILL.md"
        before = canonical.read_bytes()
        self.fixture.register("alpha")
        result = self.generate()
        self.assertEqual(set(result["adapters"]["removed"]), {
            f"{directory}/specromancy-{pipeline_id}/SKILL.md"
            for directory in (".agents/skills", ".claude/skills") for pipeline_id in ("beta", "gamma")
        })
        self.assertEqual(canonical.read_bytes(), before)
        self.generate(check=True)

    def test_source_changes_and_launch_skill_drift_are_read_only_in_check_mode(self) -> None:
        for relative in ("workflow/pipelines/beta.toml", "workflow/templates/shared.md", ".agents/skills/specromancy-alpha/SKILL.md"):
            with self.subTest(path=relative):
                self.generate()
                target = self.root / relative
                before = self.snapshot()
                source = target.read_bytes()
                changed_source = source.replace(b"\nversion = 1", b"\nversion = 2") if target.suffix == ".toml" else source + b"\nChanged content.\n"
                target.write_bytes(changed_source)
                changed = self.snapshot()
                with self.assertRaises(AdapterError):
                    self.generate(check=True)
                self.assertEqual(self.snapshot(), changed)
                target.write_bytes(source)
                self.assertEqual(self.snapshot(), before)

    def test_unowned_and_modified_stale_native_skills_are_preserved(self) -> None:
        native = self.root / ".agents/skills/specromancy-beta/SKILL.md"
        native.parent.mkdir(parents=True)
        native.write_text("User owned\n")
        with self.assertRaises(AdapterError) as caught:
            self.generate()
        self.assertIn(native.relative_to(self.root).as_posix(), caught.exception.details["unowned"])
        self.assertEqual(native.read_text(), "User owned\n")
        native.unlink()
        self.generate()
        native.write_text("User edited\n")
        self.fixture.register("alpha")
        manifest = (self.root / "adapters/manifest.json").read_bytes()
        with self.assertRaises(AdapterError) as caught:
            self.generate()
        self.assertIn(native.relative_to(self.root).as_posix(), caught.exception.details["stale_modified"])
        self.assertEqual(native.read_text(), "User edited\n")
        self.assertEqual((self.root / "adapters/manifest.json").read_bytes(), manifest)

    def test_manifest_cannot_claim_a_canonical_skill(self) -> None:
        self.generate()
        path = self.root / "adapters/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["generated"][0]["path"] = "workflow/skills/compose/SKILL.md"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(AdapterError):
            self.generate()
        self.assertTrue((self.root / "workflow/skills/compose/SKILL.md").is_file())

    def test_native_launch_skill_parent_symlink_is_rejected(self) -> None:
        skill = self.root / ".agents/skills/specromancy-alpha"
        skill.parent.mkdir(parents=True)
        skill.symlink_to(self.root / "workflow/skills/compose", target_is_directory=True)
        before = (self.root / "workflow/skills/compose/SKILL.md").read_bytes()
        with self.assertRaises(AdapterError):
            self.generate()
        self.assertEqual((self.root / "workflow/skills/compose/SKILL.md").read_bytes(), before)


class WorkflowAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MultiPipelineFixture()
        self.addCleanup(self.fixture.close)
        self.root = self.fixture.root
        self.skill = self.root / "workflow/skills/compose/SKILL.md"
        self.graph = self.root / "workflow/pipelines/beta.toml"

    def generate(self, *, check=False, metadata=None):
        return generate_adapters(self.root, load_adapter_registry(self.root), metadata, check=check)

    def manifest(self):
        return json.loads((self.root / MANIFEST_PATH).read_bytes())

    def test_capture_once_and_render_all_required_surfaces(self) -> None:
        registry = load_adapter_registry(self.root)
        schema = self.root / "workflow/templates/schema.json"
        schema.write_text('{"type":"object"}')
        for registration in registry.pipelines:
            path = registration.path
            path.write_text(path.read_text().replace('validator = "markdown"', 'validator = "json"\n'
                                                     'validator_path = "../templates/schema.json"')
                            .replace('required_headings = ["Result"]', 'required_headings = []'))
        # Registry parsing belongs to the caller. Guard its location again, but
        # use the same snapshot even if its on-disk contents subsequently change.
        registry.path.write_text("[broken")
        read = Path.read_bytes
        with patch.object(Path, "read_bytes", autospec=True, side_effect=read) as reader:
            captured = capture_workflow_sources(self.root, registry, None)
            calls = [call.args[0] for call in reader.call_args_list]
            for source in (self.skill, schema, self.root / "workflow/templates/shared.md",
                           self.root / "workflow/instructions.md"):
                self.assertEqual(calls.count(source), 1)
        self.skill.unlink()
        schema.unlink()
        rendered = render_workflow_sources(captured)
        manifest = workflow_manifest(captured, rendered)
        self.assertEqual(list(rendered), sorted(rendered))
        self.assertEqual((manifest["schema_version"], manifest["generator"]["version"]), (2, 4))
        inputs = [entry["path"] for entry in manifest["canonical_source"]["inputs"]]
        self.assertEqual(inputs, sorted(set(inputs)))
        self.assertTrue(set(inputs).isdisjoint(rendered))
        self.assertTrue(all(s.startswith(("workflow/", "@")) for s in inputs))
        shared = {f".agents/skills/{name}/SKILL.md" for name in
                  ("compose", "pipeline", "specromancy-alpha", "specromancy-beta")}
        native = {"AGENTS.md"} | shared
        names = ("init", "phase", "status", "resume")
        required = {
            "codex": native, "hermes": native,
            "opencode": native | {f".opencode/commands/specromancy-{n}.md" for n in names},
            "copilot": shared | {".github/copilot-instructions.md"} |
                       {f".github/prompts/specromancy-{n}.prompt.md" for n in names},
            "claude": {s.replace(".agents/", ".claude/") for s in shared} | {".claude/CLAUDE.md"} |
                      {f".claude/commands/specromancy/{n}.md" for n in names},
        }
        self.assertEqual(set(rendered), set.union(*required.values()))
        self.assertEqual([r["path"] for r in manifest["generated"]], list(rendered))
        for entry in manifest["generated"]:
            path = entry["path"]
            self.assertEqual(entry["targets"], sorted(t for t, paths in required.items() if path in paths))
            self.assertEqual(entry["sha256"], sha256_bytes(rendered[path]))
        for target in manifest["targets"]:
            self.assertEqual(target["paths"], sorted(required[target["name"]]))
            if target["mode"] == "native":
                self.assertEqual(target["discovery_paths"], sorted(shared))
        for name in ("alpha", "beta"):
            launch = rendered[f".claude/skills/specromancy-{name}/SKILL.md"]
            self.assertIn(f"init DESCRIPTION --pipeline {name} --json".encode(), launch)
            self.assertIn(b"resume RUN_ID --json", launch)
            self.assertNotIn(b".agents/", launch)

    def test_render_only_validates_locations_and_skips_template_bytes(self) -> None:
        registry = load_adapter_registry(self.root)
        path = self.root / "workflow/templates/shared.md"
        read = Path.read_bytes

        def read_without_template(candidate):
            self.assertNotEqual(candidate, path)
            return read(candidate)

        with patch.object(Path, "read_bytes", read_without_template):
            files = render_adapters(self.root, registry, adapter_command_metadata())
        self.assertIn("AGENTS.md", files)
        self.assertFalse((self.root / MANIFEST_PATH).exists())

    def test_rebuild_drift_and_normalization(self) -> None:
        result = self.generate()
        first = self.manifest()
        digest = first["canonical_source"]["sha256"]
        self.assertEqual(digest, result["adapters"]["canonical_source_sha256"])
        self.generate()
        snapshot = {p: (self.root / p).read_bytes() for p in [*result["adapters"]["paths"], MANIFEST_PATH]}
        with patch("tempfile.mkstemp", side_effect=AssertionError("check wrote files")):
            self.generate(check=True)
        shutil.rmtree(self.root / ".agents")
        (self.root / "AGENTS.md").unlink()
        with self.assertRaises(AdapterError) as caught:
            self.generate(check=True)
        self.assertIn("AGENTS.md", caught.exception.details["missing"])
        self.generate()
        self.assertEqual(snapshot, {p: (self.root / p).read_bytes() for p in snapshot})
        output = self.root / ".claude/skills/compose/SKILL.md"
        output.write_bytes(b"edited")
        with self.assertRaises(AdapterError) as caught:
            self.generate(check=True)
        self.assertEqual(caught.exception.details["modified"], [output.relative_to(self.root).as_posix()])
        self.assertEqual(self.generate()["adapters"]["canonical_source_sha256"], digest)
        self.skill.write_bytes(self.skill.read_bytes().replace(b"\n", b"\r\n") + b"\r\n")
        self.generate(check=True)
        self.skill.write_bytes(self.skill.read_bytes() + b"Body edit\n")
        with self.assertRaises(AdapterError) as caught:
            self.generate(check=True)
        self.assertEqual(caught.exception.details["modified"], [MANIFEST_PATH])
        self.assertNotEqual(self.generate()["adapters"]["canonical_source_sha256"], digest)
        self.assertEqual(self.manifest()["generated"], first["generated"])
        self.skill.unlink()
        for check in (True, False):
            with self.assertRaises(PipelineConfigError) as caught:
                self.generate(check=check)
            self.assertEqual(caught.exception.diagnostic_code, "missing-file")

    def test_release_content_metadata_and_workflow_changes_reach_hash_and_render(self) -> None:
        baseline = self.generate()["adapters"]["canonical_source_sha256"]
        package = files("specromancy_engine").joinpath("resources", "adapters")
        clone = self.root / "installed-copy"
        shutil.copytree(package, clone / "resources/adapters")
        with patch.object(adapter_sources, "files", return_value=clone):
            self.generate(check=True)
            template = clone / "resources/adapters/instructions.md"
            template.write_bytes(template.read_bytes() + b"Release edit.\n")
            with self.assertRaises(AdapterError) as drift:
                self.generate(check=True)
            self.assertIn("AGENTS.md", drift.exception.details["modified"])
            self.assertNotEqual(self.generate()["adapters"]["canonical_source_sha256"], baseline)
        metadata = adapter_command_metadata()
        next(c for c in metadata["commands"] if c["name"] == "resume")["help"] = "Continue the saved run."
        self.assertNotEqual(self.generate(metadata=metadata)["adapters"]["canonical_source_sha256"], baseline)
        self.assertIn(b"Continue the saved run.", (self.root / ".claude/commands/specromancy/resume.md").read_bytes())
        instructions = self.root / "workflow/instructions.md"
        instructions.write_text("A new canonical rule.\n")
        self.assertNotEqual(self.generate()["adapters"]["canonical_source_sha256"], baseline)
        for path in ("AGENTS.md", ".claude/CLAUDE.md", ".github/copilot-instructions.md"):
            self.assertIn(instructions.read_bytes(), (self.root / path).read_bytes())
        before = self.manifest()["canonical_source"]["sha256"]
        self.fixture.register("alpha")
        self.assertNotEqual(self.generate()["adapters"]["canonical_source_sha256"], before)

    def test_guarded_source_paths_across_render_generate_and_check(self) -> None:
        registry = load_adapter_registry(self.root)
        select_harnesses(self.root, "claude")
        options = [
            lambda: render_adapters(self.root, registry, adapter_command_metadata()),
            lambda: generate_adapters(self.root, registry),
            lambda: generate_adapters(self.root, registry, check=True),
        ]
        foreign = self.root / ".opencode/commands/specromancy-phase.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("invalid TOML, schema, and skill frontmatter")
        validator = self.root / "workflow/schema.json"
        validator.write_text("{}")
        self.graph.write_text(self.graph.read_text().replace('validator = "markdown"',
                             'validator = "json"\nvalidator_path = "../schema.json"')
                             .replace('required_headings = ["Result"]', 'required_headings = []'))
        for path in (registry.path, self.graph, self.skill, self.root / "workflow/instructions.md",
                     self.root / "workflow/templates/shared.md", validator):
            content = path.read_bytes()
            path.unlink()
            path.symlink_to(foreign)
            for run in options:
                with self.subTest(path=path, run=run), self.assertRaises(PipelineConfigError) as caught:
                    run()
                self.assertEqual(caught.exception.diagnostic_code, "unsafe-path")
            path.unlink()
            path.write_bytes(content)
        self.graph.write_text(self.graph.read_text().replace("../schema.json", "../../.github/prompts/absent.md"))
        for run in options:
            with self.assertRaises(PipelineConfigError) as caught:
                run()
            self.assertEqual(caught.exception.diagnostic_code, "unsafe-path")
        self.assertFalse((self.root / MANIFEST_PATH).exists())

    def test_selection_guard_precedes_parsing_and_opt_out(self):
        registry = load_adapter_registry(self.root)
        selection = self.root / "workflow/adapters.toml"
        select_harnesses(self.root)
        empty = selection.read_bytes()
        selection.unlink()
        for relative in ("AGENTS.md", ".claude/CLAUDE.md", MANIFEST_PATH):
            target = self.root / relative
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(empty)
            selection.symlink_to(target)
            for check in (False, True):
                with self.subTest(path=relative), self.assertRaises(PipelineConfigError) as caught:
                    generate_adapters(self.root, registry, check=check)
                self.assertEqual(caught.exception.diagnostic_code, "unsafe-path")
                self.assertEqual(target.read_bytes(), empty)
            selection.unlink()
        workflow = self.root / "workflow"
        destination = self.root / ".claude/workflow"
        workflow.rename(destination)
        (destination / "adapters.toml").write_bytes(empty)
        workflow.symlink_to(destination, target_is_directory=True)
        with self.assertRaises(PipelineConfigError) as caught:
            generate_adapters(self.root, registry)
        self.assertEqual(caught.exception.diagnostic_code, "unsafe-path")

    def test_identity_conflicts_and_legacy_migrations_precede_publication(self) -> None:
        original = self.graph.read_text()
        alias = self.root / "workflow/alias.md"
        alias.symlink_to(self.skill)
        source = self.skill.relative_to(self.root).as_posix()
        alternate = write_workflow_skill(self.root, "other")
        for name, path, diagnostic in (
            ("compose", "workflow/alias.md", "conflicting-skill-source"),
            ("alternate", "workflow/alias.md", "conflicting-skill-source"),
            ("alternate", alternate.relative_to(self.root).as_posix(), "skill-name-mismatch"),
            ("specromancy-alpha", alternate.relative_to(self.root).as_posix(), "reserved-skill"),
            ("pipeline", alternate.relative_to(self.root).as_posix(), "reserved-skill"),
        ):
            with self.subTest(name=name, path=path):
                self.graph.write_text(original.replace('skill = "compose"', f'skill = "{name}"').replace(source, path))
                with self.assertRaises(PipelineConfigError) as caught:
                    self.generate()
                self.assertEqual(caught.exception.diagnostic_code, diagnostic)
        self.graph.write_text(original)
        for path in self.graph.parent.glob("*.toml"):
            path.write_text(path.read_text().replace(f'skill_source = "{source}"\n', ""))
        with self.assertRaises(PipelineConfigError) as caught:
            self.generate()
        self.assertEqual(caught.exception.details["value"], {"alpha": ["compose"], "beta": ["inspect"]})
        self.assertFalse((self.root / MANIFEST_PATH).exists())
