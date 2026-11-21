"""Fast archive contract tests; no builds, venvs, downloads, or installs."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import shutil
import tarfile
import tempfile
import tomllib
import unittest
import zipfile

from tests.source_export import ignore_development_outputs

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_distribution", ROOT / "tools/verify_distribution.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class DistributionContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
        self.prefix = f"specromancy_engine-{self.version}"
        self.info = f"{self.prefix}.dist-info"

    def wheel(self, *, omit=(), extra=None, dependency=False):
        description = verifier.build_metadata(ROOT)
        members = verifier.inventory(ROOT)
        members.update({f"{self.info}/{name}": content for name, content in {
            "METADATA": (f"Metadata-Version: 2.4\nName: specromancy-engine\nVersion: {self.version}\n"
                         "Requires-Python: >=3.11\nLicense-Expression: MIT\n"
                         "Description-Content-Type: text/markdown\n"
                         + "".join(f"Project-URL: {label}, {url}\n" for label, url
                                   in description["project_urls"].items())
                         + ("Requires-Dist: unwanted\n" if dependency else "")
                         + "\n" + description["long_description"]).encode(),
            "WHEEL": b"Wheel-Version: 1.0\n", "RECORD": b"", "top_level.txt": b"specromancy_engine\n",
            "entry_points.txt": b"[console_scripts]\nspecromancy = specromancy_engine.cli:main\n",
            "licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
        }.items()})
        members.update(extra or {})
        path = self.root / "fixture.whl"
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in members.items():
                if name not in omit:
                    archive.writestr(name, content)
        return path

    def test_complete_wheel_inventory_and_metadata(self):
        result = verifier.inspect_wheel(self.wheel(), ROOT)
        self.assertEqual(result["version"], self.version)
        self.assertEqual(set(result["runtime"]), set(verifier.inventory(ROOT)))

    def test_missing_schema_and_old_namespace_are_clear_failures(self):
        schema = "specromancy_engine/schemas/run.schema.json"
        with self.assertRaisesRegex(verifier.VerificationError, "missing=.*run.schema.json"):
            verifier.inspect_wheel(self.wheel(omit={schema}), ROOT)
        with self.assertRaisesRegex(verifier.VerificationError, "unexpected=.*specromancy/__init__.py"):
            verifier.inspect_wheel(self.wheel(extra={"specromancy/__init__.py": b""}), ROOT)

    def test_release_templates_are_required_byte_for_byte_in_both_archives(self):
        launch = "specromancy_engine/resources/adapters/launch.md"
        with self.assertRaisesRegex(verifier.VerificationError, "missing=.*launch.md"):
            verifier.inspect_wheel(self.wheel(omit={launch}), ROOT)
        with self.assertRaisesRegex(verifier.VerificationError, "wheel runtime differs.*launch.md"):
            verifier.inspect_wheel(self.wheel(extra={launch: b"changed"}), ROOT)
        with self.assertRaisesRegex(verifier.VerificationError, "missing=.*launch.md"):
            verifier.extract_sdist(self.sdist(omit={"src/" + launch}), self.root / "bad", ROOT)

    def test_runtime_dependency_and_consumer_files_are_rejected(self):
        with self.assertRaisesRegex(verifier.VerificationError, "runtime dependencies"):
            verifier.inspect_wheel(self.wheel(dependency=True), ROOT)
        for name in ("workflow/pipelines.toml", "workflow/adapters.toml", "tests/fixture.py", ".agents/skills/a/SKILL.md",
                     "AGENTS.md", "specromancy_engine/resources/adapters/producer-policy.md",
                     "bin/specromancy", "specromancy_engine/__pycache__/cli.pyc",
                     "game-of-life/README.md", ".specromancy/runs/run.json"):
            with self.subTest(name=name), self.assertRaisesRegex(verifier.VerificationError, "unexpected="):
                verifier.inspect_wheel(self.wheel(extra={name: b"unexpected"}), ROOT)

    def test_missing_artifacts_fail_instead_of_skip(self):
        with self.assertRaisesRegex(verifier.VerificationError, "wheel is missing"):
            verifier.inspect_wheel(self.root / "missing.whl", ROOT)
        with self.assertRaisesRegex(verifier.VerificationError, "sdist is missing"):
            verifier.extract_sdist(self.root / "missing.tar.gz", self.root / "extract", ROOT)

    def test_unconverted_description_and_stale_project_urls_are_rejected(self):
        wheel = self.wheel()
        with zipfile.ZipFile(wheel) as archive:
            metadata = archive.read(f"{self.info}/METADATA").decode()
        bad_description = metadata.split("\n\n", 1)[0] + "\n\n" + (ROOT / "README.md").read_text()
        documentation_url = verifier.build_metadata(ROOT)["project_urls"]["Documentation"]
        header = f"Project-URL: Documentation, {documentation_url}"
        self.assertIn(header, metadata)
        stale_urls = metadata.replace(header, "Project-URL: Documentation, https://example.invalid/stale", 1)
        for content, error in ((bad_description, "README description differs"),
                               (stale_urls, "project URLs differ")):
            self.assertNotEqual(content, metadata, "The negative fixture must change the metadata")
            with self.subTest(error=error), self.assertRaisesRegex(verifier.VerificationError, error):
                verifier.inspect_wheel(self.wheel(extra={f"{self.info}/METADATA": content.encode()}), ROOT)

    def sdist(self, *, omit=(), special=None):
        members = {name: (ROOT / name).read_bytes() for name in verifier.sdist_sources(ROOT)}
        members.update({name: b"" for name in ("PKG-INFO", "setup.cfg")})
        members.update({f"src/specromancy_engine.egg-info/{name}": b"" for name in (
            "PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt", "top_level.txt")})
        path = self.root / "fixture.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name, content in members.items():
                if name in omit:
                    continue
                member = tarfile.TarInfo(self.prefix + "/" + name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            if special:
                archive.addfile(special)
        return path

    def test_sdist_preserves_canonical_example_skills_and_rejects_missing_files(self):
        skill = "examples/release-documentation/workflow/skills/draft-release-notes/SKILL.md"
        source = verifier.extract_sdist(self.sdist(), self.root / "extract", ROOT)
        self.assertEqual((source / skill).read_bytes(), (ROOT / skill).read_bytes())
        for name in (skill, "examples/release-documentation/workflow/adapters.toml"):
            with self.subTest(name=name), self.assertRaisesRegex(verifier.VerificationError, "missing=.*" + name):
                verifier.extract_sdist(self.sdist(omit={name}), self.root / "bad", ROOT)

    def test_consumer_bundle_copies_only_the_source_example_inputs(self):
        source = self.root / "source"
        shutil.copytree(ROOT / verifier.EXAMPLE, source / verifier.EXAMPLE)
        guide = Path("docs/guides/installation.md")
        (source / guide.parent).mkdir(parents=True)
        shutil.copyfile(ROOT / guide, source / guide)
        for name in ("AGENTS.md", ".agents/skills/foreign/SKILL.md", "adapters/manifest.json"):
            foreign = source / verifier.EXAMPLE / name
            foreign.parent.mkdir(parents=True, exist_ok=True)
            foreign.write_text("local generation")
        runner = self.root / "runner"
        verifier.copy_bundle(runner, source)
        example = runner / verifier.EXAMPLE
        self.assertEqual({p.relative_to(example).as_posix() for p in example.rglob("*") if p.is_file()},
                         set(verifier.EXAMPLE_FILES))
        for name in verifier.EXAMPLE_FILES:
            self.assertEqual((example / name).read_bytes(), (source / verifier.EXAMPLE / name).read_bytes())

    def test_sdist_rejects_traversal_links_and_duplicate_members_before_writing(self):
        for name, kind in (("../escaped", tarfile.REGTYPE),
                           (f"{self.prefix}/link", tarfile.SYMTYPE),
                           (f"{self.prefix}/link", tarfile.LNKTYPE),
                           (f"{self.prefix}/README.md", tarfile.REGTYPE)):
            with self.subTest(name=name, kind=kind):
                special = tarfile.TarInfo(name)
                special.type = kind
                special.linkname = "../../escape"
                destination = self.root / "unsafe"
                with self.assertRaises(verifier.VerificationError):
                    verifier.extract_sdist(self.sdist(special=special), destination, ROOT)
                self.assertFalse(destination.exists())

    def test_source_export_excludes_arbitrarily_named_venvs_preserving_evidence(self):
        for name in ("custom-environment", ".venv311"):
            (self.root / name).mkdir()
            (self.root / name / "pyvenv.cfg").touch()
        names = ["custom-environment", ".venv311", "build", "dist", "old.egg-info", "old.dist-info",
                 "workflow", ".agents", "docs", "tests", "adapters", "game-of-life"]
        ignored = ignore_development_outputs(str(self.root), names)
        self.assertEqual(ignored, set(names[:6]))


if __name__ == "__main__":
    unittest.main()
