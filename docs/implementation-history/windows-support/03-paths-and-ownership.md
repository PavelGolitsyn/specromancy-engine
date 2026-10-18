# Stage 03 — Paths and filesystem ownership

Status: planned. Depends on: 02. Risk: high; containment and overwrite prevention.

## Outcome

Keep persisted paths portable while preventing native Windows names, aliases,
and directory junctions from bypassing configuration or write-ownership rules.
Ordinary Windows roots with spaces and Unicode must work without relaxing
read-only policies or adapter collision protection.

## Intended files

- `src/specromancy_engine/hashing.py`: normalized relative syntax and resolution.
- `_config/config_fields.py`, `_config/config_phase_parser.py`, `registry.py`:
  declared paths, output patterns, and duplicate registrations.
- `artifacts.py`, `run_store.py`, `_runs/visit_preparation.py`: artifact/run
  containment and physical output collisions.
- `_adapters/adapter_ownership.py`: preflight, manifest ownership, safe writes,
  stale owned-file cleanup, and managed-path discovery.
- Small shared filesystem helpers from Stage 02 where a genuinely common
  primitive is needed; do not add a second competing path policy.
- Focused tests in `test_config.py`, `test_registry.py`, `test_run_store.py`,
  `test_visit_transition_store.py`, `test_adapters.py`, and
  `test_multi_pipeline_adapters.py`; new path unit tests as needed.
- `docs/reference/contracts.md`, `docs/guides/authoring-pipelines.md`.

## Instructions

1. Separate three concepts explicitly:
   - Serialized repository/run-relative paths use the existing forward-slash
     syntax and keep their canonical spelling in hashes and records.
   - User-supplied CLI roots and OS calls use native `Path` objects.
   - Filesystem identity determines whether destinations alias or escape an
     authorized root. String normalization alone cannot establish ownership.
2. Preserve existing grammar differences. Artifact/manifest relative paths reject
   parent traversal. Configuration resource references can use `..` when their
   resolved target stays inside the consumer root. Mutation allowlists contain
   glob syntax and must not be validated as literal filenames. Prefer
   `PurePosixPath` for serialized syntax without changing accepted Unix forms
   incidentally during this work.
3. Before native Windows access, reject components that cannot represent an
   ordinary file safely: reserved device names including extension variants,
   colon/alternate-data-stream syntax, trailing spaces/dots, forbidden characters,
   and control characters. Apply checks to rendered outputs, manifest-owned
   adapter paths, resource paths, and registry paths, not only `--root`.
   Check materialized filenames, not every logical phase/pipeline ID: a safe
   prefix can make a generated filename valid even when an ID alone is reserved.
4. Keep absolute, drive-relative, rooted, UNC, and device namespace forms out of
   serialized relative fields. Explicit roots are a different API: native drive
   paths are supported, while network roots remain outside the verified storage
   guarantee. Do not strip prefixes, punctuation, or case to “repair” unsafe input.
5. Keep host-specific restrictions at native access boundaries so existing valid
   POSIX-only filenames do not acquire an undocumented global ban. Pure component
   checks can accept a platform argument for unit tests; native integration still
   runs on Windows. Do not rely on APIs added after Python 3.11.
6. Audit symlink and junction behavior. Resolve the explicitly chosen repository
   root once, then enforce existing policies on descendants. Configuration
   resources retain permitted in-root links but reject escapes. Run storage and
   generated adapter destinations reject redirected paths according to their
   stricter ownership rules, including Windows junctions and unsafe reparse
   points, before writing or deleting anything.
7. Implement junction detection compatible with Python 3.11, using documented
   `lstat` reparse attributes/tags where necessary; do not require newer
   `Path.is_junction`. Recheck after creating parent directories as the current
   artifact writer does. Do not claim this closes every concurrent directory-swap
   race; preserve the existing concurrency boundary and document discovered gaps.
8. Detect destination aliases before mutation. Cover duplicate registry targets,
   artifact paths that differ only by case, and adapter ownership/canonical-skill
   collisions through differently cased parents. Use native path identity and
   `samefile` for existing targets where appropriate, with explicit handling for
   missing targets. Never lowercase stored paths or broaden allowlist matching.
9. Preflight the entire adapter generation before writing or cleaning stale
   outputs. A forged manifest, alias, or junction must not let the CLI overwrite
   a canonical skill or remove an unowned file. Preserve check mode as read-only.
10. Surface invalid paths through the existing configuration/artifact/adapter/run
    error families and CLI codes. Catch path-resolution errors at the correct
    boundary so Windows errors produce useful diagnostics, not raw tracebacks.
    Do not add a schema version just to carry a platform-specific error detail.

Microsoft documents the relevant naming and namespace rules in
[Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).
Python 3.11 exposes Windows reparse metadata through
[stat](https://docs.python.org/3.11/library/stat.html).

## Required test matrix

| Input/scenario | Required result |
| --- | --- |
| Consumer root with spaces, an apostrophe, and Unicode | Initialize, write output, validate, and generate adapters successfully |
| `C:relative`, `C:/absolute`, backslash-rooted, UNC/device forms in relative fields | Controlled rejection before filesystem mutation |
| `artifacts/result.md:stream`, `NUL.txt`, `con`, `COM1.log`, trailing dot/space | Windows rejection without creating an alias or stream |
| Ordinary POSIX filename invalid on Windows | Existing POSIX behavior preserved; Windows failure explicit |
| Legitimate `../templates/result.md` within consumer root | Still accepted; escape beyond the root rejected |
| Glob such as `docs/**` | Still treated as a mutation pattern, not a literal filename |
| Symlink/junction parent points outside run or adapter root | No write or cleanup outside the authorized location |
| Junction/case alias points at an in-root canonical skill | No ownership takeover or overwrite |
| Registry/output/adapter destinations alias on Windows | Duplicate or collision detected before mutation |
| Case-sensitive POSIX filesystem with genuinely distinct paths | Do not impose Windows identity semantics globally |
| Adapter generation fails preflight | Exact repository snapshot unchanged, including unowned files |

Link tests must probe the specific capability. Separate unavailable symlink
creation from junction coverage and ordinary path tests. CI must exercise the
link-capable cases on a real Windows runner; a catch-all platform skip is not
an acceptable ownership test. Teardown may remove only test-owned links and
fixtures and must never recursively follow a junction into its target.

## Verification

```sh
python -m unittest tests.engine.unit.test_config tests.engine.unit.test_registry
python -m unittest tests.engine.unit.test_run_store tests.engine.unit.test_visit_transition_store
python -m unittest tests.engine.unit.test_adapters tests.engine.unit.test_multi_pipeline_adapters
python -m unittest tests.engine.contract.test_safety tests.packaging.test_consumer_roots
```

Also run new path tests and the common full verification commands. Record native
Windows failures still assigned to invocation/fixture work in Stage 04. Unix
compatibility records and generated bytes must still match their prior baseline.

## Exit criteria and handoff

- Windows name/alias/link regressions pass with no out-of-scope writes or deletes.
- Valid native roots work; serialized paths and hash inputs remain unchanged.
- Existing Unix path acceptance, configuration diagnostics, and ownership tests
  remain green except for any separately documented, justified safety correction.
- No special phase name, workflow fork, or generated adapter hand edit is added.

If an alias cannot be classified safely, reject that operation with a diagnostic;
do not compensate by renaming, deleting, or adopting the existing target.
