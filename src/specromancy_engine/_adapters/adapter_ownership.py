"""Manifest ownership, drift checks, preflight, and per-file atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .adapter_contracts import (
    HARNESS_MODES, MANIFEST_PATH, REGENERATION_COMMAND, AdapterError, consumers_for_path,
    target_records,
)
from ..hashing import SHA256_PATTERN, normalize_relative_path, sha256_bytes


def write_adapters(
    root: Path, rendered: Mapping[str, bytes], manifest_bytes: bytes, *, workflow: bool = False,
) -> tuple[str, ...]:
    """Preflight ownership, replace outputs, recheck stale hashes, then write manifest."""

    owned = _read_ownership(root, workflow=workflow)
    conflicts, stale = _preflight_generation(root, rendered, owned, workflow=workflow)
    if conflicts:
        raise AdapterError(
            "adapter generation stopped to protect unowned or modified files",
            conflicts,
        )

    for path, content in rendered.items():
        target = _target(root, path)
        if _unsafe_existing_path(root, target) is None and target.is_file():
            try:
                if target.read_bytes() == content:
                    continue
            except OSError as exc:
                raise AdapterError(
                    "cannot read generated adapter destination",
                    {"path": path, "error": str(exc)},
                ) from exc
        _atomic_write(root, path, content)

    for path, expected_hash in stale:
        target = _target(root, path)
        if _unsafe_existing_path(root, target) is not None:
            raise AdapterError(
                "stale generated adapter changed during generation",
                {"stale_modified": [path]},
            )
        if not target.exists():
            continue
        current = sha256_bytes(target.read_bytes())
        if current != expected_hash:
            raise AdapterError(
                "stale generated adapter changed during generation",
                {"stale_modified": [path]},
            )
        target.unlink()

    _atomic_write(root, MANIFEST_PATH, manifest_bytes)
    return tuple(path for path, _ in stale)


def _read_ownership(root: Path, *, workflow: bool) -> dict[str, str]:
    path = _target(root, MANIFEST_PATH)
    problem = _unsafe_existing_path(root, path)
    if problem:
        raise AdapterError("adapter manifest destination is unsafe", {"path": MANIFEST_PATH, "reason": problem})
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(
            "adapter manifest is unreadable or invalid",
            {"path": MANIFEST_PATH, "error": str(exc)},
        ) from exc
    return _owned_paths(value, workflow=workflow)


def _owned_paths(manifest: Any, *, workflow: bool) -> dict[str, str]:
    generator = manifest.get("generator") if isinstance(manifest, dict) else None
    if not isinstance(generator, dict):
        raise AdapterError("invalid adapter manifest generator", {"path": MANIFEST_PATH})
    schema, version = manifest.get("schema_version"), generator.get("version")
    identities = [(1, 1), (1, 2)]
    if workflow:
        identities.append((2, 3))
    command = "bin/specromancy adapters generate" if version == 1 else REGENERATION_COMMAND
    if (type(schema) is not int or type(version) is not int or (schema, version) not in identities
            or generator.get("name") != "specromancy" or generator.get("command") != command):
        raise AdapterError("unsupported adapter manifest generator identity",
                           {"schema_version": schema, "generator": generator})
    generated = manifest.get("generated")
    if not isinstance(generated, list):
        raise AdapterError("adapter manifest has no generated path list", {"path": MANIFEST_PATH})
    owned: dict[str, str] = {}
    for item in generated:
        if not isinstance(item, Mapping):
            raise AdapterError(
                "adapter manifest has an invalid generated entry",
                {"path": MANIFEST_PATH},
            )
        path = item.get("path")
        digest = item.get("sha256")
        try:
            normalized = normalize_relative_path(path)
        except (TypeError, ValueError) as exc:
            raise AdapterError(
                "adapter manifest contains an unsafe path",
                {"path": path, "error": str(exc)},
            ) from exc
        if normalized == MANIFEST_PATH or normalized in owned:
            raise AdapterError(
                "adapter manifest contains a duplicate or self-owned path",
                {"path": normalized},
            )
        if any(ord(c) < 32 for c in normalized):
            raise AdapterError("adapter manifest contains an unsafe path", {"path": normalized})
        if schema == 1:
            target = _legacy_target(normalized)
            allowed = target is not None
            attribution = set(item) == {"path", "sha256", "target"} and item.get("target") == target
        else:
            consumers = consumers_for_path(normalized)
            allowed = bool(consumers)
            attribution = set(item) == {"path", "sha256", "targets"} and item.get("targets") == list(consumers)
        if not allowed:
            raise AdapterError("adapter manifest contains a path outside generated adapter locations",
                               {"path": normalized})
        if not attribution:
            raise AdapterError("adapter manifest target does not match its generated path", {"path": normalized})
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise AdapterError(
                "adapter manifest contains an invalid content hash",
                {"path": normalized, "sha256": digest},
            )
        owned[normalized] = digest
    expected = target_records(owned) if schema == 2 else _legacy_target_records(owned)
    if manifest.get("targets") != expected:
        raise AdapterError("adapter manifest target paths or discovery paths disagree", {"path": MANIFEST_PATH})
    return owned


def _legacy_target_records(owned: Mapping[str, str]) -> list[dict[str, Any]]:
    discovery = sorted(path for path in owned if path.startswith(".agents/"))
    records = []
    for name, mode in sorted(HARNESS_MODES.items()):
        record = {"name": name, "mode": mode,
                  "paths": sorted(path for path in owned if _legacy_target(path) == name)}
        if mode == "native":
            record["discovery_paths"] = discovery
        records.append(record)
    return records


def _preflight_generation(
    root: Path,
    rendered: Mapping[str, bytes],
    owned: Mapping[str, str], *, workflow: bool,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    expected = set(rendered)
    conflicts: dict[str, Any] = {}
    unowned = []
    unsafe = []
    for path in sorted(expected):
        target = _target(root, path)
        problem = _unsafe_existing_path(root, target)
        if problem is not None:
            unsafe.append({"path": path, "reason": problem})
        elif (target.exists() or target.is_symlink()) and path not in owned:
            unowned.append(path)

    unexpected = sorted(_managed_paths(root, workflow=workflow) - expected - set(owned))
    if unexpected:
        unowned.extend(path for path in unexpected if path not in unowned)

    stale: list[tuple[str, str]] = []
    stale_modified = []
    for path in sorted(set(owned) - expected):
        target = _target(root, path)
        problem = _unsafe_existing_path(root, target)
        if problem is not None:
            stale_modified.append(path)
            continue
        if not target.exists():
            continue
        try:
            current_hash = sha256_bytes(target.read_bytes())
        except OSError:
            stale_modified.append(path)
            continue
        if current_hash == owned[path]:
            stale.append((path, owned[path]))
        else:
            stale_modified.append(path)

    if unowned:
        conflicts["unowned"] = sorted(unowned)
    if unsafe:
        conflicts["unsafe"] = unsafe
    if stale_modified:
        conflicts["stale_modified"] = stale_modified
    return conflicts, stale


def _compare(
    root: Path, rendered: Mapping[str, bytes], manifest_bytes: bytes, *, workflow: bool = False,
) -> dict[str, Any]:
    owned = _read_ownership(root, workflow=workflow)
    missing = []
    modified = []
    for path, expected in (*rendered.items(), (MANIFEST_PATH, manifest_bytes)):
        target = _target(root, path)
        if _unsafe_existing_path(root, target) is not None:
            modified.append(path)
            continue
        if not target.exists():
            missing.append(path)
            continue
        try:
            actual = target.read_bytes()
        except OSError:
            modified.append(path)
            continue
        if actual != expected:
            modified.append(path)
    unexpected = _managed_paths(root, workflow=workflow) - set(rendered)
    for path in owned.keys() - rendered.keys():
        target = _target(root, path)
        if _unsafe_existing_path(root, target) or target.exists():
            unexpected.add(path)
    return {
        "missing": sorted(missing),
        "modified": sorted(modified),
        "unexpected": sorted(unexpected),
    }


def _has_drift(drift: Mapping[str, Any]) -> bool:
    return any(bool(value) for value in drift.values())


def _managed_paths(root: Path, *, workflow: bool) -> set[str]:
    paths: set[str] = set()
    singles = (".claude/CLAUDE.md", ".github/copilot-instructions.md")
    if workflow:
        singles += ("AGENTS.md",)
    for path in singles:
        target = root / path
        if target.exists() or target.is_symlink():
            paths.add(path)
    scans = (
        (root / ".claude" / "commands" / "specromancy", "*.md"),
        (root / ".github" / "prompts", "specromancy-*.prompt.md"),
        (root / ".opencode" / "commands", "specromancy-*.md"),
    )
    if not workflow:
        scans += (
            (root / ".agents" / "skills", "specromancy-*/SKILL.md"),
            (root / ".claude" / "skills", "*/SKILL.md"),
        )
    for directory, pattern in scans:
        if _unsafe_directory(root, directory) or not directory.is_dir():
            continue
        for candidate in directory.glob(pattern):
            if candidate.is_symlink() or candidate.is_file():
                paths.add(candidate.relative_to(root).as_posix())
    return paths


def _legacy_target(path: str) -> str | None:
    """Original v1/v2 ownership grammar, including their wider Claude skill names."""
    parts = path.split("/")
    if path == ".claude/CLAUDE.md":
        return "claude"
    if path == ".github/copilot-instructions.md":
        return "copilot"
    if len(parts) == 4 and parts[3] == "SKILL.md":
        if parts[:2] == [".agents", "skills"] and parts[2].startswith("specromancy-"):
            return "codex"
        if parts[:2] == [".claude", "skills"]:
            return "claude"
    if len(parts) == 4 and parts[:3] == [".claude", "commands", "specromancy"] and parts[3].endswith(".md"):
        return "claude"
    if len(parts) == 3 and parts[2].startswith("specromancy-"):
        if parts[:2] == [".github", "prompts"] and parts[2].endswith(".prompt.md"):
            return "copilot"
        if parts[:2] == [".opencode", "commands"] and parts[2].endswith(".md"):
            return "opencode"
    return None


def _unsafe_directory(root: Path, directory: Path) -> str | None:
    current = root
    for part in directory.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            return "parent-is-symlink"
        if current.exists() and not current.is_dir():
            return "parent-is-not-directory"
    return None


def _unsafe_existing_path(root: Path, target: Path) -> str | None:
    problem = _unsafe_directory(root, target.parent)
    if problem:
        return problem
    if target.is_symlink():
        return "target-is-symlink"
    if target.exists() and not target.is_file():
        return "target-is-not-file"
    return None


def _target(root: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    return root / normalized


def _atomic_write(root: Path, relative: str, content: bytes) -> None:
    target = _target(root, relative)
    problem = _unsafe_existing_path(root, target)
    if problem is not None:
        raise AdapterError(
            "generated adapter destination is unsafe",
            {"path": relative, "reason": problem},
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
