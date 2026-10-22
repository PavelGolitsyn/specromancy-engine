from __future__ import annotations

import ast
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests.source_export import ignore_development_outputs

import specromancy_engine
from tests.engine.contract.source_scan import runtime_sources


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FIXTURE = Path("tests/engine/fixtures/example-pipeline")


class ReleaseContractTests(unittest.TestCase):
    def assert_isolated_version(self, search_paths: list[Path], cwd: Path, expected: str) -> None:
        script = """
import sys
sys.path[:0] = sys.argv[1:]
import specromancy_engine
print(specromancy_engine.__version__)
"""
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", script, *map(str, search_paths)],
            cwd=cwd, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), expected)

    def test_checkout_version_wins_over_installed_and_working_directory_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "producer"
            source = checkout / "src"
            shutil.copytree(ROOT / "src/specromancy_engine", source / "specromancy_engine")
            (checkout / "pyproject.toml").write_text(
                '[project]\nname = "specromancy-engine"\nversion = "9.8.7"\n',
                encoding="utf-8",
            )
            consumer = root / "consumer"
            consumer.mkdir()
            (consumer / "pyproject.toml").write_text(
                '[project]\nname = "specromancy-engine"\nversion = "4.5.6"\n',
                encoding="utf-8",
            )
            # No installation, including when invoked from an unrelated project.
            self.assert_isolated_version([source], consumer, "9.8.7")
            metadata = root / "site-packages/specromancy_engine-1.2.3.dist-info"
            metadata.mkdir(parents=True)
            (metadata / "METADATA").write_text(
                "Metadata-Version: 2.4\nName: specromancy-engine\nVersion: 1.2.3\n",
                encoding="utf-8",
            )
            self.assert_isolated_version([metadata.parent, source], consumer, "9.8.7")

    def test_installed_version_uses_distribution_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Even a directory named src must not take another project's version.
            (root / "pyproject.toml").write_text(
                '[project]\nname = "consumer-project"\nversion = "4.5.6"\n',
                encoding="utf-8",
            )
            for directory in ("site-packages", "src"):
                with self.subTest(directory=directory):
                    installed = root / directory
                    shutil.copytree(ROOT / "src/specromancy_engine", installed / "specromancy_engine")
                    metadata = installed / "specromancy_engine-1.2.3.dist-info"
                    metadata.mkdir()
                    (metadata / "METADATA").write_text(
                        "Metadata-Version: 2.4\nName: specromancy-engine\nVersion: 1.2.3\n",
                        encoding="utf-8",
                    )
                    self.assert_isolated_version([installed], root, "1.2.3")

    def test_package_and_installed_metadata_agree(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        distribution = importlib.metadata.distribution("specromancy-engine")
        self.assertEqual(project["version"], specromancy_engine.__version__)
        self.assertEqual(distribution.version, specromancy_engine.__version__)
        self.assertEqual(distribution.metadata["Name"], project["name"])
        self.assertEqual(distribution.metadata["Requires-Python"], ">=3.11")
        self.assertEqual(distribution.metadata["License-Expression"], "MIT")
        self.assertEqual(project["dependencies"], [])
        self.assertEqual(distribution.requires or [], [])
        scripts = {
            entry.name: entry.value
            for entry in distribution.entry_points
            if entry.group == "console_scripts"
        }
        self.assertEqual(scripts, {"specromancy": "specromancy_engine.cli:main"})

    def test_fresh_source_export_runs_without_installation(self) -> None:
        self.assertGreaterEqual(sys.version_info, (3, 11))
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "specromancy"

            shutil.copytree(ROOT, checkout, ignore=ignore_development_outputs)
            subprocess.run(
                ["git", "-C", str(checkout), "init", "--quiet"],
                check=True,
                capture_output=True,
            )
            help_result = subprocess.run(
                [sys.executable, "-S", str(checkout / "bin" / "specromancy"), "--help"],
                cwd=checkout / "docs",
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            initialized = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(checkout / "bin" / "specromancy"),
                    "--json",
                    "--root",
                    str(checkout / WORKFLOW_FIXTURE),
                    "--pipeline",
                    "engine-example",
                    "init",
                    "Fresh source test",
                ],
                cwd=checkout,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(initialized.returncode, 8, initialized.stderr)
            self.assertEqual(json.loads(initialized.stdout)["action"]["phase"], "research")

    def test_runtime_package_imports_only_standard_library_modules(self) -> None:
        imported: set[str] = set()
        for path in runtime_sources(ROOT / "src" / "specromancy_engine"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".", 1)[0])
        non_standard = imported - sys.stdlib_module_names - {"specromancy_engine"}
        self.assertEqual(non_standard, set())

    def test_runtime_data_is_ignored_and_license_metadata_is_consistent(self) -> None:
        ignored = subprocess.run(
            ["git", "check-ignore", ".specromancy/runs/example/run.json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(ignored.returncode, 0)
        self.assertTrue((ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"))
        for path in sorted(
            (ROOT / WORKFLOW_FIXTURE / ".agents" / "skills").glob("*/SKILL.md")
        ):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn("\nlicense: MIT\n", path.read_text(encoding="utf-8"))

    def test_release_documents_cover_supported_contract_and_limitations(self) -> None:
        required = {
            "reference/architecture.md": ("Responsibility split", "Current limitations"),
            "reference/cli.md": ("Workflow commands", "exit codes"),
            "guides/authoring-pipelines.md": ("bounded loops", "active runs"),
            "guides/harnesses.md": ("Codex", "Claude Code", "GitHub Copilot", "OpenCode", "Hermes"),
        }
        for name, concepts in required.items():
            text = (ROOT / "docs" / name).read_text(encoding="utf-8")
            with self.subTest(path=name):
                for concept in concepts:
                    self.assertIn(concept.lower(), text.lower())


if __name__ == "__main__":
    unittest.main()
