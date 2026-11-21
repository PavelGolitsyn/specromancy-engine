"""Copied into a runtime-free bundle and executed by a fresh wheel environment."""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import unittest
from importlib.resources import files


def verify_generation(bundle: Path, console: Path, installed: Path, expected: dict) -> None:
    from tests.packaging.test_consumer_roots import snapshot

    root = bundle / "examples/release-documentation"
    before = snapshot(root)
    for name in ("AGENTS.md", ".agents", ".claude", ".github", ".opencode", "adapters"):
        assert name not in before, name

    argv = [str(console), "--root", str(root), "--json", "adapters", "generate"]
    # This environment belongs only to this wheel smoke run.
    template = "specromancy_engine/resources/adapters/phase.md"
    path = installed / template
    hidden = path.with_suffix(".unavailable")
    path.rename(hidden)
    try:
        result = subprocess.run(argv, capture_output=True, text=True)
        assert result.returncode == 11, (result.stdout, result.stderr)
        assert json.loads(result.stderr or result.stdout)["details"]["path"] == "@package/" + template
        assert snapshot(root) == before, "missing release template changed consumer"
    finally:
        hidden.rename(path)

    # The example selects Claude and OpenCode. A missing Copilot template
    # cannot prevent generation or enter either installation's source hash.
    unused = installed / "specromancy_engine/resources/adapters/command-copilot.md"
    unused.rename(unused.with_suffix(".unavailable"))
    try:
        subprocess.run(argv, check=True, capture_output=True)
    finally:
        unused.with_suffix(".unavailable").rename(unused)
    subprocess.run([sys.executable, "-I", "-m", "specromancy_engine", *argv[1:], "--check"],
                   check=True, capture_output=True)
    manifest = json.loads((root / "adapters/manifest.json").read_bytes())
    inputs = manifest["canonical_source"]["inputs"]
    identities = {entry["path"] for entry in inputs}
    assert len(identities) == len(inputs)
    template_hashes = {"@package/" + name: digest for name, digest in expected["template_hashes"].items()
                       if name != unused.relative_to(installed).as_posix()}
    assert {e["path"]: e["sha256"] for e in inputs if e["kind"] == "release-template"} == template_hashes
    workflow = {p for p in before if p.startswith("workflow/") and (root / p).is_file()}
    assert identities == workflow | template_hashes.keys() | {
        "@cli-help-metadata", "@package/specromancy_engine/version",
    }

    after = snapshot(root)
    outputs = {e["path"]: e["sha256"] for e in manifest["generated"]}
    assert len(outputs) == len(manifest["generated"])
    assert {p for p in after.keys() - before if (root / p).is_file()} == outputs.keys() | {"adapters/manifest.json"}
    assert all(after[p] == original for p, original in before.items())
    targets = {t["name"]: t["paths"] for t in manifest["targets"]}
    assert targets.keys() == {"claude", "opencode"}
    assert "AGENTS.md" in targets["opencode"]
    assert ".agents/skills/specromancy-release-documentation/SKILL.md" in targets["opencode"]
    assert all(p.startswith(".claude/") for p in targets["claude"])
    assert all(not p.startswith(".github/") for p in outputs)
    assert {p for paths in targets.values() for p in paths} == outputs.keys()
    for entry in manifest["generated"]:
        name = entry["path"]
        assert after[name][1] == entry["sha256"], name
        assert entry["targets"] == sorted(t for t, paths in targets.items() if name in paths), name


def main() -> int:
    bundle = Path(__file__).resolve().parent
    expected = json.loads((bundle / "expected.json").read_text())
    installed = Path(sysconfig.get_path("purelib")).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), installed
    package = importlib.import_module("specromancy_engine")
    assert Path(package.__file__).resolve().is_relative_to(installed), package.__file__
    assert package.__version__ == expected["version"]
    assert importlib.metadata.version("specromancy-engine") == expected["version"]
    assert importlib.util.find_spec("specromancy") is None, "stale legacy import namespace"
    for relative in expected["runtime"]:
        if relative.endswith(".py"):
            name = relative[:-3].replace("/", ".").removesuffix(".__init__")
            module = importlib.import_module(name)
            assert Path(module.__file__).resolve() == installed / relative, module.__file__
        else:
            resource = files(package).joinpath(relative.split("/", 1)[1])
            if relative in expected["template_hashes"]:
                assert hashlib.sha256(resource.read_bytes()).hexdigest() == expected["template_hashes"][relative]
            else:
                assert json.loads(resource.read_text(encoding="utf-8"))["$schema"]
    console = Path(sys.executable).with_name("specromancy")
    help_text = []
    for command in ([sys.executable, "-I", "-m", "specromancy_engine"], [str(console)]):
        result = subprocess.run([*command, "--help"], check=True, capture_output=True, text=True)
        assert "request-approval" in result.stdout
        help_text.append(result.stdout)
    assert help_text[0] == help_text[1]
    print(f"Installed origin: {package.__file__}", flush=True)
    print(f"Verified {len(expected['runtime'])} runtime files and both entry points", flush=True)
    # Only test code/fixtures are exposed. This directory has no engine source,
    # launcher, editable metadata, or producer configuration.
    sys.path.insert(0, str(bundle))
    suite = unittest.defaultTestLoader.loadTestsFromNames(expected["tests"])
    assert suite.countTestCases() > 0
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        return 1
    verify_generation(bundle, console, installed, expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
