"""Fast archive contract tests; no builds, venvs, downloads, or installs."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
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

    def test_runtime_dependency_and_consumer_files_are_rejected(self):
        with self.assertRaisesRegex(verifier.VerificationError, "runtime dependencies"):
            verifier.inspect_wheel(self.wheel(dependency=True), ROOT)
        for name in ("workflow/pipelines.toml", "tests/fixture.py", ".agents/skills/a/SKILL.md",
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

    def test_sdist_preserves_hidden_example_skills_and_rejects_missing_files(self):
        skill = "examples/release-documentation/.agents/skills/pipeline/SKILL.md"
        source = verifier.extract_sdist(self.sdist(), self.root / "extract", ROOT)
        self.assertEqual((source / skill).read_bytes(), (ROOT / skill).read_bytes())
        with self.assertRaisesRegex(verifier.VerificationError, "missing=.*SKILL.md"):
            verifier.extract_sdist(self.sdist(omit={skill}), self.root / "bad", ROOT)

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
