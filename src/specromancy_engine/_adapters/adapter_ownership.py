"""Manifest ownership, drift checks, preflight, and per-file atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .adapter_config import SELECTION_KIND, SELECTION_PATH, selection_bytes
from .adapter_contracts import (
    ADAPTER_SCHEMA_VERSION, COMMAND_PATHS, HARNESS_MODES, MANIFEST_PATH, AdapterError,
    consumers_for_path, generator_identity, target_records,
)
from ..hashing import SHA256_PATTERN, normalize_relative_path, sha256_bytes, sha256_json


def write_adapters(
    root: Path, rendered: Mapping[str, bytes], manifest_bytes: bytes, harnesses: tuple[str, ...],
    owned: Mapping[str, str],
) -> tuple[str, ...]:
    """Preflight ownership, replace outputs, recheck stale hashes, then write manifest."""

    conflicts, stale = _preflight_generation(root, rendered, owned, harnesses)
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


def _read_ownership(root: Path) -> dict[str, str]:
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
    return _owned_paths(value)


def _owned_paths(manifest: Any) -> dict[str, str]:
    generator = manifest.get("generator") if isinstance(manifest, dict) else None
    if not isinstance(generator, dict):
        raise AdapterError("invalid adapter manifest generator", {"path": MANIFEST_PATH})
    schema, version = manifest.get("schema_version"), generator.get("version")
    if (type(schema) is not int or schema != ADAPTER_SCHEMA_VERSION
            or type(version) is not int or generator != generator_identity()):
        raise AdapterError("unsupported adapter manifest generator identity",
                           {"schema_version": schema, "generator": generator})
    harnesses = _recorded_selection(manifest)
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
        consumers = sorted(set(harnesses).intersection(consumers_for_path(normalized)))
        if not consumers:
            raise AdapterError("adapter manifest contains a path outside generated adapter locations",
                               {"path": normalized})
        if set(item) != {"path", "sha256", "targets"} or item.get("targets") != consumers:
            raise AdapterError("adapter manifest target does not match its generated path", {"path": normalized})
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise AdapterError(
                "adapter manifest contains an invalid content hash",
                {"path": normalized, "sha256": digest},
            )
        owned[normalized] = digest
    if manifest["targets"] != target_records(owned, harnesses):
        raise AdapterError("adapter manifest target paths or discovery paths disagree", {"path": MANIFEST_PATH})
    return owned


def _recorded_selection(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    records = manifest.get("targets")
    if not isinstance(records, list):
        raise AdapterError("invalid adapter manifest targets", {"path": MANIFEST_PATH})
    names = []
    for record in records:
        name = record.get("name") if isinstance(record, dict) else None
        if not isinstance(name, str) or name not in HARNESS_MODES or name in names:
            raise AdapterError("invalid adapter manifest target", {"name": name})
        names.append(name)
    harnesses = tuple(sorted(names))
    source = manifest.get("canonical_source")
    inputs = source.get("inputs") if isinstance(source, dict) else None
    selection = {"kind": SELECTION_KIND, "path": SELECTION_PATH,
                 "sha256": sha256_bytes(selection_bytes(harnesses))}
    if not isinstance(inputs, list):
        raise AdapterError("adapter manifest has no canonical inputs", {"path": MANIFEST_PATH})
    recorded = [item for item in inputs if isinstance(item, dict)
                and (item.get("path") == SELECTION_PATH or item.get("kind") == SELECTION_KIND)]
    if recorded != [selection] or (not harnesses and inputs != recorded):
        raise AdapterError("adapter manifest targets disagree with selection input", {"path": SELECTION_PATH})
    try:
        digest = sha256_json(inputs)
    except ValueError as exc:
        raise AdapterError("invalid adapter manifest canonical inputs", {"path": MANIFEST_PATH}) from exc
    if source.get("sha256") != digest:
        raise AdapterError("adapter manifest canonical input hash disagrees", {"path": MANIFEST_PATH})
    return harnesses


def _preflight_generation(
    root: Path,
    rendered: Mapping[str, bytes],
    owned: Mapping[str, str],
    harnesses: tuple[str, ...],
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

    unexpected = sorted(_managed_paths(root, harnesses) - expected - set(owned))
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
    root: Path, rendered: Mapping[str, bytes], manifest_bytes: bytes, harnesses: tuple[str, ...],
    owned: Mapping[str, str],
) -> dict[str, Any]:
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
    unexpected = _managed_paths(root, harnesses) - set(rendered)
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


def _managed_paths(root: Path, harnesses: tuple[str, ...]) -> set[str]:
    # All selected instruction files are already checked as exact destinations.
    # Only the selected command namespaces reserve additional wildcard paths.
    paths: set[str] = set()
    for harness in harnesses:
        if harness not in COMMAND_PATHS:
            continue
        glob = root / COMMAND_PATHS[harness].format(name="*")
        directory, pattern = glob.parent, glob.name
        if _unsafe_directory(root, directory) or not directory.is_dir():
            continue
        for candidate in directory.glob(pattern):
            if candidate.is_symlink() or candidate.is_file():
                paths.add(candidate.relative_to(root).as_posix())
    return paths


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
