#!/usr/bin/env python3
"""Release orchestration checks; not installed as part of the engine.

Network operations are read-only. Uploads belong to the Trusted Publishing action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import venv

REGISTRIES = {"testpypi": "https://test.pypi.org", "pypi": "https://pypi.org"}


class ReleaseError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


def filenames(version: str) -> tuple[str, str]:
    require(re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version)
            is not None, "Release version must be a final MAJOR.MINOR.PATCH version")
    return (f"specromancy_engine-{version}-py3-none-any.whl",
            f"specromancy_engine-{version}.tar.gz")


def prepare(root: Path, commit: str, default_commit: str) -> dict[str, str]:
    for value in (commit, default_commit):
        require(re.fullmatch(r"[0-9a-f]{40}", value) is not None,
                "Supply a full, lowercase 40-character commit SHA")

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    require(git("rev-parse", f"{commit}^{{commit}}") == commit,
            "Release input must identify a commit, not a tag object")
    require(subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                            commit, default_commit], check=False).returncode == 0,
            "Release commit must belong to the selected default-branch history")
    project = tomllib.loads(git("show", f"{commit}:pyproject.toml"))["project"]
    require(project["name"] == "specromancy-engine", "Unexpected distribution name")
    version = project["version"]
    wheel, sdist = filenames(version)
    tag = f"refs/tags/v{version}"
    exists = subprocess.run(["git", "-C", str(root), "show-ref", "--verify", "--quiet", tag],
                            check=False).returncode == 0
    if exists:
        require(git("rev-parse", f"{tag}^{{commit}}") == commit,
                f"Existing v{version} tag points to a different commit")
    return {"commit": commit, "version": version, "wheel": wheel, "sdist": sdist}


def check_files(directory: Path, version: str, hashes: tuple[str, str]) -> dict[str, str]:
    names = filenames(version)
    require(directory.is_dir(), "Distribution directory is missing")
    require({p.name for p in directory.iterdir()} == set(names),
            "Distribution directory must contain exactly the selected wheel and sdist")
    expected = dict(zip(names, hashes))
    for name, digest in expected.items():
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "Invalid expected SHA-256")
        path = directory / name
        require(path.is_file() and not path.is_symlink(), f"Not a regular artifact: {name}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                f"Artifact hash mismatch: {name}")
    return expected


def inspect_registry(data: dict, expected: dict[str, str], allow_missing: bool) -> bool:
    """Reject conflicts immediately; return False only for not-yet-visible files."""
    found = set()
    for entry in data["urls"]:
        name = entry["filename"]
        require(name in expected and name not in found, f"Unexpected registry file: {name}")
        require(not entry.get("yanked", False), f"Registry file is yanked: {name}")
        require(entry["digests"]["sha256"] == expected[name],
                f"Registry already contains different bytes: {name}; do not overwrite a release")
        found.add(name)
    return allow_missing or found == set(expected)


def check_registry(registry: str, version: str, expected: dict[str, str], *,
                   allow_missing: bool = False, attempts: int = 12) -> None:
    url = f"{REGISTRIES[registry]}/pypi/specromancy-engine/{version}/json"
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            if inspect_registry(data, expected, allow_missing):
                return
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_missing:
                return
            if exc.code != 404 and exc.code != 429 and exc.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
        if attempt + 1 < attempts:
            print(f"Waiting for {registry} artifact metadata ({attempt + 1}/{attempts})", flush=True)
            time.sleep(10)
    raise ReleaseError(f"Could not verify both published files on {registry}")


def smoke(registry: str, version: str, wheel_hash: str) -> None:
    """Download from the selected index, enforce the built hash, install in isolation."""
    with tempfile.TemporaryDirectory(prefix="specromancy-registry-smoke-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / "bin/python"
        requirements = root / "requirements.txt"
        requirements.write_text(f"specromancy-engine=={version} --hash=sha256:{wheel_hash}\n")
        downloads = root / "downloads"
        downloads.mkdir()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("PYTHON", "PIP_"))}
        env["PIP_CONFIG_FILE"] = os.devnull
        download = [str(python), "-I", "-m", "pip", "download", "--no-cache-dir",
                    "--index-url", f"{REGISTRIES[registry]}/simple/", "--no-deps",
                    "--only-binary=:all:", "--require-hashes", "-r", str(requirements),
                    "--dest", str(downloads)]
        for attempt in range(12):
            result = subprocess.run(download, cwd=root, env=env, check=False)
            if result.returncode == 0:
                break
            if attempt == 11:
                raise ReleaseError(f"Could not download the verified wheel from {registry}")
            time.sleep(10)
        wheel, _ = filenames(version)
        subprocess.run([str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps",
                        str(downloads / wheel)], cwd=root, env=env, check=True)
        subprocess.run([str(python), "-I", "-c",
                        "import sys; from importlib.metadata import version; "
                        "import specromancy_engine; "
                        "assert version('specromancy-engine') == sys.argv[1]; "
                        "assert specromancy_engine.__version__ == sys.argv[1]", version],
                       cwd=root, env=env, check=True)
        subprocess.run([str(environment / "bin/specromancy"), "--help"],
                       cwd=root, env=env, check=True)
        subprocess.run([str(python), "-I", "-m", "specromancy_engine", "--help"],
                       cwd=root, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--root", type=Path, default=Path.cwd())
    prepare_parser.add_argument("--commit", required=True)
    prepare_parser.add_argument("--default-commit", required=True)
    for command in ("check", "registry", "smoke"):
        check = commands.add_parser(command)
        check.add_argument("--directory", type=Path, required=True)
        check.add_argument("--version", required=True)
        check.add_argument("--wheel-sha256", required=True)
        check.add_argument("--sdist-sha256", required=True)
        if command != "check":
            check.add_argument("--registry", choices=REGISTRIES, required=True)
        if command == "registry":
            check.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        outputs = prepare(args.root, args.commit, args.default_commit)
        for key, value in outputs.items():
            print(f"{key}={value}")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.writelines(f"{key}={value}\n" for key, value in outputs.items())
        return
    expected = check_files(args.directory, args.version, (args.wheel_sha256, args.sdist_sha256))
    if args.command != "check":
        check_registry(args.registry, args.version, expected,
                       allow_missing=getattr(args, "allow_missing", False))
    if args.command == "smoke":
        smoke(args.registry, args.version, args.wheel_sha256)


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Release check failed: {exc}")
