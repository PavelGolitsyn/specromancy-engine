#!/usr/bin/env python3
"""Offline distribution gate. Invoke from a checkout with prebuilt, exact artifacts.

Only stdlib imports here. Build tooling is provisioned separately; the rebuilding
subprocess checks all backend requirements before an offline, non-isolated build.
"""
from __future__ import annotations

import argparse
import configparser
import email.policy
import hashlib
import importlib.metadata
import json
import os
import platform
import runpy
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser

ROOT = Path(__file__).resolve().parents[1]
build_metadata = runpy.run_path(str(ROOT / "build_readme.py"))["build_metadata"]
SCHEMAS = {f"specromancy_engine/schemas/{name}.schema.json"
           for name in ("event", "run", "pipeline", "pipelines")}
ADAPTER_TEMPLATES = {f"specromancy_engine/resources/adapters/{name}.md" for name in (
    "command-claude", "command-copilot", "command-opencode", "instructions",
    "launch", "orchestrator", "phase",
)}
EXAMPLE = Path("examples/release-documentation")
EXAMPLE_FILES = (
    ".gitignore", "README.md", "sample-changes.md", "workflow/instructions.md",
    "workflow/adapters.toml", "workflow/pipelines.toml", "workflow/pipelines/release-documentation.toml",
    "workflow/skills/draft-release-notes/SKILL.md", "workflow/skills/review-release-notes/SKILL.md",
    "workflow/templates/release-notes.md", "workflow/templates/review.md",
)
TEST_MODULES = (
    "tests.packaging.test_consumer_roots",
    "tests.packaging.test_release_documentation",
    "tests.engine.contract.test_action_approval",
    "tests.engine.contract.test_current_contract",
    "tests.engine.contract.test_engine_orchestration",
    "tests.engine.contract.test_multi_pipeline",
    "tests.engine.contract.test_safety",
    "tests.engine.contract.test_recovery",
    "tests.engine.contract.test_adapter_drift",
    "tests.engine.unit.test_adapters",
    "tests.engine.unit.test_registry",
    "tests.engine.unit.test_run_records",
    "tests.engine.unit.test_multi_pipeline_adapters",
)


class VerificationError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def inventory(root: Path) -> dict[str, bytes]:
    package = root / "src/specromancy_engine"
    result = {p.relative_to(root / "src").as_posix(): p.read_bytes()
              for p in package.rglob("*.py")}
    require("specromancy_engine/__init__.py" in result, "runtime source inventory is missing")
    for name in sorted(SCHEMAS | ADAPTER_TEMPLATES):
        path = root / "src" / name
        require(path.is_file(), f"required package resource is missing: {name}")
        result[name] = path.read_bytes()
    return result


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and not any(
        part in {"..", "."} or ":" in part or "\\" in part for part in name.split("/")
    ) and all(name.split("/"))


def inspect_wheel(wheel: Path, root: Path) -> dict:
    require(wheel.is_file() and wheel.suffix == ".whl", f"wheel is missing or invalid: {wheel}")
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    expected = inventory(root)
    version = project["version"]
    info = f"specromancy_engine-{version}.dist-info"
    metadata_files = {f"{info}/{name}" for name in (
        "METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD", "licenses/LICENSE",
    )}
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "wheel contains duplicate members")
        require(all(safe_name(n) for n in names), "wheel contains unsafe paths")
        require(all(not stat.S_ISLNK(i.external_attr >> 16) for i in archive.infolist()),
                "wheel contains symlinks")
        missing = set(expected) | metadata_files
        require(set(names) == missing,
                f"wheel contents mismatch; missing={sorted(missing - set(names))}; "
                f"unexpected={sorted(set(names) - missing)}")
        for name, content in expected.items():
            require(archive.read(name) == content, f"wheel runtime differs from source: {name}")
        metadata = BytesParser(policy=email.policy.default).parsebytes(archive.read(f"{info}/METADATA"))
        for key, value in {"Name": "specromancy-engine", "Version": version,
                           "Requires-Python": ">=3.11", "License-Expression": "MIT",
                           "Description-Content-Type": "text/markdown"}.items():
            require(metadata[key] == value, f"wheel metadata {key}: expected {value!r}, got {metadata[key]!r}")
        require(not metadata.get_all("Requires-Dist"), "wheel declares runtime dependencies")
        description = build_metadata(root)
        require(metadata.get_payload().strip() == description["long_description"].strip(),
                "wheel README description differs")
        require(set(metadata.get_all("Project-URL", [])) == {
            f"{label}, {url}" for label, url in description["project_urls"].items()
        }, "wheel project URLs differ")
        require(archive.read(f"{info}/licenses/LICENSE") == (root / "LICENSE").read_bytes(),
                "wheel license differs")
        entry = configparser.ConfigParser()
        entry.read_string(archive.read(f"{info}/entry_points.txt").decode())
        require(entry.sections() == ["console_scripts"] and dict(entry["console_scripts"]) == {
            "specromancy": "specromancy_engine.cli:main"}, "wheel console entry points differ")
    return {"version": version, "runtime": sorted(expected), "sha256": digest(wheel),
            "template_hashes": {n: hashlib.sha256(expected[n]).hexdigest()
                                for n in sorted(ADAPTER_TEMPLATES)}}


def sdist_sources(root: Path) -> set[str]:
    names = {"pyproject.toml", "MANIFEST.in", "README.md", "LICENSE", "docs/README.md",
             "setup.py", "build_readme.py"}
    names.update("src/" + n for n in inventory(root))
    names.update((EXAMPLE / name).as_posix() for name in EXAMPLE_FILES)
    for directory in ("docs/guides", "docs/reference"):
        names.update(p.relative_to(root).as_posix() for p in (root / directory).rglob("*.md")
                     if p.is_file())
    return names


def extract_sdist(sdist: Path, destination: Path, root: Path) -> Path:
    require(sdist.is_file(), f"sdist is missing: {sdist}")
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    prefix = f"specromancy_engine-{version}"
    expected = sdist_sources(root)
    generated = {"PKG-INFO", "setup.cfg"}
    generated.update(f"src/specromancy_engine.egg-info/{n}" for n in (
        "PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt", "top_level.txt",
    ))
    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        require(len(names) == len(set(names)), "sdist contains duplicate members")
        require(all(safe_name(n) for n in names), "sdist contains unsafe paths")
        require(all(m.isfile() or m.isdir() for m in members), "sdist contains links or special files")
        require(all(n == prefix or n.startswith(prefix + "/") for n in names),
                "sdist has an unexpected root")
        files = {m.name[len(prefix) + 1:]: m for m in members if m.isfile()}
        require(set(files) == expected | generated,
                f"sdist contents mismatch; missing={sorted((expected | generated) - set(files))}; "
                f"unexpected={sorted(set(files) - expected - generated)}")
        for name in expected:
            require(archive.extractfile(files[name]).read() == (root / name).read_bytes(),
                    f"sdist source differs: {name}")
        # Explicit regular-file extraction works on 3.11 too; never follow links,
        # apply archived permissions, or delegate path handling to extractall.
        for name, member in files.items():
            target = destination / prefix / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    return destination / prefix


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTHON", "GIT_", "PIP_", "SPECROMANCY_"))}
    git = shutil.which("git")
    require(git is not None, "required executable is missing: git")
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PIP_NO_INDEX="1",
               PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    env["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), str(Path(git).parent), os.defpath))
    return env


def copy_bundle(destination: Path, consumer_source: Path) -> None:
    files = {m.replace(".", "/") + ".py" for m in TEST_MODULES}
    files.update({"tests/engine/support.py", "tests/engine/contract/current_contract_support.py",
                  "tests/engine/contract/support.py"})
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
        parent = target.parent
        while parent != destination:
            (parent / "__init__.py").touch()
            parent = parent.parent
    for fixture in ("current-contract/source", "example-pipeline"):
        shutil.copytree(ROOT / "tests/engine/fixtures" / fixture,
                        destination / "tests/engine/fixtures" / fixture)
    fixtures = Path("tests/engine/fixtures")
    for directory, names in (
        ("current-contract", ("canonical.json", "diagnostics.json", "ownership.json",
                              "responses.json", "states.json")),
        ("refused-contracts", ("runs-v1.json", "ownership-generator-1.json", "ownership-generator-2.json",
                               "ownership-generator-3.json", "ownership-generator-4.json")),
    ):
        target = destination / fixtures / directory
        target.mkdir(exist_ok=True)
        for name in names:
            shutil.copyfile(ROOT / fixtures / directory / name, target / name)
    for name in EXAMPLE_FILES:
        target = destination / EXAMPLE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(consumer_source / EXAMPLE / name, target)
    (destination / "docs/guides").mkdir(parents=True)
    shutil.copyfile(consumer_source / "docs/guides/installation.md", destination / "docs/guides/installation.md")
    shutil.copyfile(ROOT / "tools/distribution_smoke.py", destination / "distribution_smoke.py")


class Verifier:
    def __init__(self, log):
        self.log = log
        self.env = environment()

    def say(self, message: str) -> None:
        print(message, flush=True)
        self.log.write(message + "\n")
        self.log.flush()

    def run(self, command: list[str], cwd: Path, env=None) -> None:
        self.say("RUN " + json.dumps(command))
        result = subprocess.run(command, cwd=cwd, env=env or self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.log.write(result.stdout)
        self.log.flush()
        require(result.returncode == 0, f"command failed (exit {result.returncode}); see log: {command}")

    def consumer(self, wheel: Path, base: Path, source: Path, expected: dict) -> bytes:
        base.mkdir()
        venv = base / "venv"
        self.run([sys.executable, "-I", "-m", "venv", str(venv)], base)
        python = venv / "bin/python"
        self.run([str(python), "-I", "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)], base)
        bundle = base / "runner"
        copy_bundle(bundle, source)
        (bundle / "expected.json").write_text(json.dumps({**expected, "tests": TEST_MODULES}))
        env = self.env | {"PATH": str(python.parent) + os.pathsep + self.env["PATH"],
                          "SPECROMANCY_CONSUMER_BUNDLE": str(bundle)}
        self.run([str(python), "-I", "-B", str(bundle / "distribution_smoke.py")], base, env)
        root = bundle / EXAMPLE
        manifest = (root / "adapters/manifest.json").read_bytes()
        for path in ["adapters/manifest.json", *(e["path"] for e in json.loads(manifest)["generated"])]:
            data = (root / path).read_bytes()
            for location in (ROOT, source, base):
                require(os.fsencode(location) not in data, f"host path in generated file: {path}")
        self.say(f"PASS isolated consumer: {wheel.name}")
        return manifest

    def verify(self, wheel: Path, sdist: Path) -> None:
        require(sys.version_info >= (3, 11), "Python >=3.11 is required")
        require(os.name == "posix", "distribution verification currently covers POSIX; Windows is unverified")
        self.say(f"Interpreter: {sys.executable}; {sys.version}; platform={platform.platform()}")
        expected = inspect_wheel(wheel, ROOT)
        self.say("Runtime inventory: " + json.dumps(expected["runtime"]))
        self.say(f"Wheel: {wheel} sha256={expected['sha256']}")
        require(sdist.is_file(), f"sdist is missing: {sdist}")
        self.say(f"Sdist: {sdist} sha256={digest(sdist)}")
        for line in (ROOT / "tools/requirements-build.txt").read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            name, version = line.split("==")
            try:
                actual = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                actual = "missing"
            require(actual == version, f"required build tool {name}=={version}; found {actual}; "
                    "provision tools/requirements-build.txt before verification")
            self.say(f"Build tool: {name}=={actual}")
        with tempfile.TemporaryDirectory(prefix="specromancy-distribution-") as temporary:
            base = Path(temporary).resolve()
            require(not base.is_relative_to(ROOT), "TMPDIR must be outside the producer checkout")
            source = extract_sdist(sdist, base / "source", ROOT)
            self.run([sys.executable, "-I", "-c",
                      "import build,sys; b=build.ProjectBuilder(sys.argv[1]); "
                      "missing=b.check_dependencies('wheel'); "
                      "sys.exit('Missing declared build requirements: '+repr(missing) if missing else 0)",
                      str(source)], base)
            output = base / "rebuilt"
            self.run([sys.executable, "-I", "-m", "build", "--wheel", "--no-isolation",
                      "--outdir", str(output), str(source)], base)
            wheels = list(output.glob("*.whl"))
            require(len(wheels) == 1, "sdist rebuild must produce exactly one wheel")
            rebuilt = inspect_wheel(wheels[0], ROOT)
            self.say(f"Rebuilt wheel: sha256={rebuilt['sha256']}")
            direct_manifest = self.consumer(wheel, base / "direct", ROOT, expected)
            rebuilt_manifest = self.consumer(wheels[0], base / "from-sdist", source, rebuilt)
            require(direct_manifest == rebuilt_manifest, "installed wheels generated different manifests")
            self.say("Verified identical manifest, inputs and output hashes: " + direct_manifest.decode().strip())
        self.say("PASS distribution verification (direct wheel and sdist-rebuilt wheel)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--log", type=Path, help="new log file; default: a persistent temporary file")
    args = parser.parse_args()
    if args.log:
        log = args.log.open("x", encoding="utf-8")
        log_path = args.log.resolve()
    else:
        fd, name = tempfile.mkstemp(prefix="specromancy-distribution-", suffix=".log")
        log = os.fdopen(fd, "w", encoding="utf-8")
        log_path = Path(name)
    print(f"Verification log (retained on success or failure): {log_path}", flush=True)
    with log:
        try:
            Verifier(log).verify(args.wheel.resolve(), args.sdist.resolve())
        except (VerificationError, OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
            message = f"FAIL distribution verification: {error}"
            print(message, file=sys.stderr)
            log.write(message + "\n")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
