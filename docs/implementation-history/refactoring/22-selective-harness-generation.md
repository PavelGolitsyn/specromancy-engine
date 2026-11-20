# Stage 22 — Generate only selected harnesses

Status: **complete, verified 2026-11-20**. Depends on completed Stages 16–21.
Category: explicit project configuration, output selection, and safe migration.

## Objective

Let users choose the harnesses they use once, persist that choice under
`workflow/`, and generate only the required files. An assisting agent can ask
during setup; subsequent generation and checking must be deterministic and
non-interactive. Selection leaves pipeline identity and canonical skill hashes
unchanged and generation does not directly mutate run state. Configuration and
generated-file edits remain subject to ordinary repository mutation checks.

This is a follow-on feature after the all-harness implementation and distribution
baseline in Stage 21. It does not reopen the canonical-source migration. Earlier
stages establish shared requirements and manifest attribution with all targets
enabled. This stage adds persisted selection and filtering of those requirements,
then repeats the affected integration gates before final completion.

## User configuration and setup contract

```toml
# workflow/adapters.toml
schema_version = 1
harnesses = ["claude", "opencode"]
```

1. Supported identifiers are the existing `claude`, `codex`, `copilot`, `hermes`,
   and `opencode` targets. Do not add harnesses as part of selection.
2. Require `workflow/adapters.toml` for `adapters generate` and `--check` once
   this stage is enabled. If missing, return a controlled configuration diagnostic
   with the supported identifiers and a minimal example, before any output writes.
   Do not silently default to all harnesses, guess from installed applications,
   inspect existing output directories, or infer the choice from chat history.
3. Validate schema version, allowed keys, list/string types, known identifiers,
   and duplicates. Reject malformed input before writes or stale-file cleanup.
   Treat ordering as insignificant and canonicalize the selected set by sorting.
   Use `tomllib` and existing error/path conventions, with no new dependency.
   Before parsing, apply Stage 16's declared/resolved workflow source guard to
   `workflow/adapters.toml`, including its parent directories. A symlink to root
   `AGENTS.md`, a harness file, or the adapter manifest is invalid even if its
   contents are valid TOML. Empty selection does not bypass this guard.
4. Allow `harnesses = []` as explicit opt-out. Generation then reconciles to no
   harness outputs, retaining the manifest and removing only eligible unchanged
   owned files. Missing configuration is never equivalent to an empty selection.
5. During agent-assisted setup, ask which harnesses to support if the user has
   not supplied a choice. Save the answer in the workflow file through the normal
   authoring process. Reuse an existing valid choice without asking again. The
   engine CLI itself does not prompt, create, or edit user-owned configuration.
6. Keep existing CLI commands and public adapter facade signatures. Do not add
   per-invocation selection flags, an interactive wizard, auto-detection, or a
   second source of selection precedence.
7. Workflow configuration validation and run commands remain usable without this
   adapter-only file. Adding/changing it must not change pipeline canonical bytes,
   canonical skill hashes, or persisted run/event schemas. Generation must not
   directly modify `run.json`, `events.jsonl`, approval records, or run artifacts.
   Repository snapshots still observe configuration and generated-file edits:
   changes during a read-only visit, or outside an allowlist, must continue to
   fail validation and can prevent approval. Do not exempt adapter paths, refresh
   visit baselines, or suppress approval checks to claim run independence.

## Required-output contract

Reuse Stage 19's explicit per-harness requirement sets and render the selected
union. Shared files are emitted once. Retain the discovery/entry points
documented by Stage 21; selection must not accidentally remove a supported launch
skill or require another harness to be selected.

| Selected harness | Required surfaces from the Stage 21 contract |
| --- | --- |
| Codex | Root `AGENTS.md` and shared `.agents` orchestration, phase, and pipeline launch skills |
| Hermes | Root `AGENTS.md` and the same shared `.agents` skills |
| Claude | `.claude/CLAUDE.md`, `.claude/skills/`, and Specromancy command wrappers |
| Copilot | `.github/copilot-instructions.md`, Specromancy prompts, and shared `.agents` skills for the documented skill entry points |
| OpenCode | Root `AGENTS.md`, shared `.agents` skills for the documented skill entry points, and Specromancy command wrappers |

Confirm this restatement matches Stage 19's verified mapping; reuse that mapping
in code rather than defining a second one. A shared
`.agents` output does not imply that Codex is selected. Claude alone must produce
no `.agents` files or root `AGENTS.md`. OpenCode or Copilot can require shared
outputs without depending on pre-existing copies of those outputs.

Every selected surface still derives directly from packaged templates and
canonical `workflow/` inputs. Retain the no-output-as-source rule: no read of root
`AGENTS.md`, `.agents`, or another generated adapter is needed to render selected
outputs. An unselected harness's unrelated files must not block generation or
appear as unexpected drift merely because they use a recognized harness path.

Retain the thin phase-wrapper contract from Stage 19: validated metadata,
provenance, and canonical load instructions, without copied procedure bodies.
Validate `frontmatter.name == skill` and the unique identifier/source binding
before deduplicating reads. Required outputs are the union of harness needs,
not the number of unique source reads. Canonical body bytes remain hashed even
when they do not alter wrapper bytes.

The source-path exclusion covers all harness output locations regardless of the
selected set. Selecting only Claude must not authorize a skill, template,
validator, or configuration symlink into an unselected harness's output. Ignore
unselected foreign files as output drift, but reject their use as canonical inputs.

## Manifest, ownership, and drift contract

- Include the validated normalized selection as a canonical source input with a
  stable `workflow/adapters.toml` identity. List reordering and TOML comments do
  not change canonical hashes; a changed selected set does.
- Record the selected targets and their required/discovery paths explicitly.
  Store each generated path/hash once even when several selected harnesses use
  it. Shared-path attribution must not falsely list an unselected harness as an
  enabled target. Keep ownership validation strict when making this change.
- Keep Stage 19's adapter manifest schema 2 and set generator version 4 for
  selective behavior. Top-level `targets` lists only selected harnesses; each
  generated record's `targets` is the sorted nonempty intersection of its
  required consumers and the selection. Empty selection yields empty `targets`
  and `generated` lists. No shared-attribution redesign or additional selection
  field is needed: the canonical configuration input records the choice.
  Validate version 3 with its original all-target rules before migration;
  version 4 validates attribution against its recorded selected target set.
- Read valid manifests produced by Stage 21 and earlier supported migration
  versions. Selection is authoritative for desired outputs; a previous validated
  manifest is authoritative only for existing ownership, never for the new choice.
  Validate schema/generator identity, paths, target mapping, and hashes under each
  version's original rules before migration or applying new shared attribution.
  In particular, retain v2's prohibition on root `AGENTS.md` and ordinary
  `.agents` phase/pipeline ownership. Unknown/malformed combinations fail before
  writes; do not accept a forged old entry because a new version allows its path.
- Compute stale outputs as `previous owned paths - newly required paths`.
  Preserve a shared output while any selected harness still requires it. Delete
  only unchanged, regular, safely located, previously owned stale files.
- Modified stale files cause a controlled conflict before any writes/deletions.
  Existing unowned files at newly required paths also cause a conflict, even if
  their bytes match. No force option, directory deletion, automatic adoption, or
  Git mutation is introduced.
- `--check` validates the same configuration, reports missing/modified required
  outputs and stale previously owned outputs, and writes nothing. Ignoring
  unselected foreign files must not hide previously owned stale files.
- Empty selection still reads/validates the previous manifest and performs safe
  ownership reconciliation. It need not load unused templates, instructions, or
  pipeline skill sources merely to remove eligible old outputs.
- Preserve preflight-before-write, per-file atomic replacement, and manifest-last
  publication. Do not claim whole-directory transactional generation.

## Work sequence and intended files

1. Record the completed Stage 21 baseline, schema-2 shared attribution,
   requirement sets, and safety tests. Preserve that shape while defining the
   version-4 selection rules and validating version-3 ownership before migration.
2. Add a small adapter configuration loader beside
   `src/specromancy_engine/_adapters/adapter_sources.py`, or within it if the logic
   stays cohesive. Keep selection out of pipeline parsing and run orchestration.
3. Pass validated selection through source capture into pure rendering and
   expected-manifest construction. Capture/hash only resources used by the
   selected outputs, alongside existing dependencies applicable to those outputs.
   Guard every captured repository path before reads, including indirect
   dependencies. Selection filters outputs/resources, never source-safety rules
   or the per-version restrictions on existing manifest ownership.
   Do not render every target and discard unwanted files after filesystem writes.
4. Update `adapter_contracts.py`, `adapter_rendering.py`, `adapter_ownership.py`,
   and the facade only as needed to filter existing shared requirements, record
   selected targets, detect stale ownership, and read historical manifests safely.
5. Add explicit `workflow/adapters.toml` files to this repository, examples, and
   ordinary generation fixtures. Preserve all five targets for this repository's
   verification baseline; this keeps supported-target coverage without treating
   all targets as a default for consumers. Make the example's chosen list explicit
   and editable. Do not manufacture selections for external consumer projects.
6. Update `workflow/README.md`, installation/authoring/harness guides, CLI and
   ownership contracts, and example documentation. Explain the initial choice,
   non-interactive repeat runs, shared files, empty selection, missing-config
   diagnostic, and cleanup conflicts when deselecting a harness. Explain that
   selection/regeneration during a run can violate its ordinary mutation policy;
   unchanged pipeline identity does not imply unchanged validation evidence.
7. Update package/example allowlists and `tools/verify_distribution.py` as needed
   for the new TOML source. Extend installed-consumer scenarios in
   `tools/distribution_smoke.py` and packaging tests. Preserve the source-only
   example and runtime wheel's separation from producer configuration.
8. Regenerate owned checkout adapters, review the selection/provenance diff, and
   run all gates below. Mark Stage 22 complete only with fresh integration evidence.

## Focused test matrix

Use `tests/engine/unit/test_adapters.py`, `test_multi_pipeline_adapters.py`,
`tests/engine/contract/test_adapter_drift.py`, shipped-configuration adapter
tests, and packaging consumer tests. Test behavior rather than private call counts.

| Case | Expected observation |
| --- | --- |
| Each supported harness alone | Exactly its required union, valid entry points, no unselected exclusive outputs |
| Claude only, with no harness files initially | Generation/check succeed without creating root `AGENTS.md` or `.agents` |
| Codex + Hermes, then deselect one | Shared files remain, recorded once; only selection metadata changes where appropriate |
| Claude + OpenCode | Both required sets work; shared outputs have accurate selected consumers |
| Reorder selection and change comments | Identical canonical selection hash, rendered bytes, and manifest |
| Repeat generation/check | Deterministic results; check writes nothing |
| Missing/malformed config, unknown or duplicate name | Controlled diagnostic and no filesystem changes |
| Selection file or parent directory redirects into generated content | Rejected before TOML parsing, including when content declares an empty selection |
| Selected harness has a source/template/validator pointing into an unselected harness output | Rejected by the same declared/resolved source boundary |
| Shared phase source used by multiple selected harnesses | One canonical read/hash, matching skill/frontmatter identity, every required thin wrapper emitted |
| Canonical phase body changes without metadata/path changes | Manifest provenance changes; thin wrapper bytes may stay identical |
| Select a new harness with an unowned colliding file | Entire preflight fails without modifying prior outputs |
| Deselect a harness with unchanged owned exclusive outputs | Only those stale outputs are removed |
| Deselect a harness with a modified stale output | Conflict before mutation; user edits preserved |
| Unselected foreign harness files | Preserved and ignored by generation/check |
| Empty selection with no prior outputs | Manifest records opt-out; no harness directories/files are created |
| Empty selection after prior generation | Safe owned cleanup; foreign files/directories and run artifacts preserved |
| Previous schema-2/version-3 all-target manifest | Explicit config controls migration; original all-target attribution is validated before applying the subset, without changing schema |
| Forged v2 claim to root instructions or a phase/pipeline skill, including with empty selection | Original v2 rules reject it before overwrite or stale deletion, even with a matching hash |
| Unsupported generator/schema combination or version-specific target mismatch | Controlled rejection; no cleanup or migration using current-version rules |
| Change selection and regenerate during an existing run, before any further run command | Pipeline identity and canonical skill hashes unchanged; run/event bytes, approval records, and artifacts untouched by generation |
| Change tracked selection/configuration or generated files after a read-only visit starts | Subsequent validation/approval enforces the original mutation baseline and rejects the changes |
| Regenerate outside an active visit's mutation allowlist | Ordinary mutation-policy failure; no adapter-path exemption or baseline refresh |
| Direct and sdist-rebuilt wheels outside checkout | Same selected outputs and canonical hashes; no producer or generated-source dependency |

Cover unsafe paths/symlinks, malformed manifests, and interrupted replacement
through the existing ownership/fault tests, extending them only where selection
creates a new branch. Test output deletion/reconstruction in disposable consumers.

## Verification and acceptance

Install the checkout in a dedicated environment before testing, as in Stage 16.
Run on Python 3.11 and the available development interpreter:

```sh
python -m pip install -e .
python -m unittest tests.engine.unit.test_adapters tests.engine.unit.test_multi_pipeline_adapters tests.engine.contract.test_adapter_drift tests.packaging.test_consumer_roots
python -m unittest discover
specromancy adapters generate --check
python bin/specromancy adapters generate --check
git diff --check
```

Repeat Stage 21's direct-wheel and sdist-rebuilt-wheel verification with explicit
selections after final package-included documentation changes. Record actual
versions, commands, counts/skips, artifact hashes, and migration evidence.

- [x] Selection is explicit, persisted under `workflow/`, validated, and reused.
- [x] Only the union required by selected harnesses is generated; shared ownership
  is unambiguous and unselected foreign content does not trigger drift.
- [x] Missing configuration does not trigger defaults, prompts, writes, or cleanup.
- [x] Deselecting targets protects edits and preserves still-needed shared files.
- [x] Generation works without pre-existing `.agents` or root `AGENTS.md`.
- [x] Selection does not weaken source-path exclusion or historical ownership
  limits; metadata identity and thin-wrapper completeness remain enforced.
- [x] Selection preserves pipeline identity and canonical skill hashes; generation
  does not directly mutate run/event records, approvals, or artifacts.
- [x] Configuration and generated-file changes remain visible to ordinary
  mutation-policy and approval checks during active runs.
- [x] Public contracts, migration guidance, full tests, and installed-distribution
  checks pass without new runtime dependencies or unrelated changes.

Rollback requires reviewing the configuration/manifest and release together.
Do not blindly run an older all-target generator against a selective manifest or
discard user edits to restore the previous output set.

## Execution record

Verified from base revision `7c990e6` on macOS 26.6.2 arm64 with dedicated
editable installations of `specromancy-engine 0.1.3`. The initial checkout
manifest used schema 2, generator 3, five targets and 27 owned files. Generation
with the explicit five-target selection retained all 27 content hashes and all
target records. The manifest now uses generator 4 and adds the canonical
`workflow/adapters.toml` input. Both CLI launchers passed check mode on each
interpreter. The final whitespace check passed.

| CPython | Focused tests | Full discovery | Installed direct wheel | Installed rebuilt wheel |
| --- | ---: | ---: | ---: | ---: |
| 3.11.15 | 70 | 375 | 94 | 94 |
| 3.14.4 | 70 | 375 | 94 | 94 |

All listed suites passed with zero skips. The isolated verifier checked 66
installed runtime files and both entry points. Each of the four installations
produced the same 18 files and manifest from the example's 16 canonical inputs.
The example selects Claude and OpenCode. Removing the installed Copilot template
permitted generation and restoring it produced a clean check. Removing the
required phase template failed before any consumer writes.

| Artifact or identity | SHA-256 |
| --- | --- |
| Direct wheel | `923f0315446781c9659fceec99ece97ff79a6d9aa1586ca73c0de379c8bfbfbc` |
| Sdist | `d5da4031abf46f755c5c5b7869a610a88b0d37b4177f845307e6385173e77b38` |
| Wheel rebuilt from sdist, both interpreters | `442fcf1a048d6ab8b518dfaa32676efc430969eb782455025be173424543d12c` |
| Example manifest including trailing newline | `a1bbb0c8c601b58d9465585b7d93f55fca056d35435a68fd0b52c289491ce015` |
| Example canonical source | `68422739c772a23b7f544455b82faf8c336f491c95d130ab979b180a2cf2d095` |
| Checkout manifest including trailing newline | `866f96aba679e8a0edf52c1a4fb73646ff54e61e91c9a3b1b0338c091f67e4ef` |

### Migration and run evidence

- Each harness passed alone against the Stage 21 requirements. Claude started
  without root instructions or shared skills. Deselecting Codex kept all files
  needed by Hermes. Reordering the choice and adding a comment passed check
  without writes and reproduced the manifest bytes on regeneration.
- A frozen v3 manifest migrated to Hermes alone. Substituting Hermes-only
  attribution into the v3 input failed before mutation. Frozen v1 and v2
  manifests migrated under their own rules. Forged v2 claims to root
  instructions or ordinary shared skills failed even with an empty selection.
- Opt-out reconciled unchanged owned files while preserving directories and
  foreign files. Modified stale files and unowned collisions blocked the entire
  preflight. Source redirects into unselected outputs failed in render,
  generation and check. The selection file and its parent passed the workflow
  source guard before TOML parsing.
- In disposable Git worktrees, changing selection and generating during an
  active visit preserved the pipeline canonical bytes, skill hash, and every
  file in the run directory, including pending approval evidence. Subsequent
  approval of a read-only visit failed the mutation check. In an allowlist
  visit, permitting edits to the selection file still left generated changes
  outside the allowlist. Runtime code and stored schemas required no changes.

### Commands and retained logs

The build used the local pinned wheels for build 1.6.1, setuptools 84.0.0,
packaging 26.3 and pyproject-hooks 1.3.3. The following commands identify the
environments, artifacts and logs from this verification.

```sh
work=/private/tmp/specromancy-stage22.pCtquC
cache=/private/tmp/specromancy-stage21.56Kjbp/build-tools
/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3.11 -m venv "$work/v311"
python3.14 -m venv "$work/v314"
for v in 311 314; do
  "$work/v$v/bin/python" -m pip install --no-index --find-links "$cache" -r tools/requirements-build.txt
  "$work/v$v/bin/python" -m pip install --no-index --no-build-isolation -e .
done > "$work/install.log"

"$work/v314/bin/specromancy" adapters generate
"$work/v314/bin/python" -m build --wheel --sdist --no-isolation --outdir "$work/artifacts" > "$work/build.log" 2>&1
for v in 311 314; do
  (
    . "$work/v$v/bin/activate"
    python -m unittest tests.engine.unit.test_adapters tests.engine.unit.test_multi_pipeline_adapters tests.engine.contract.test_adapter_drift tests.packaging.test_consumer_roots > "$work/focused$v.log" 2>&1
    python -m unittest discover > "$work/full$v.log" 2>&1
    specromancy adapters generate --check
    python bin/specromancy adapters generate --check
    python tools/verify_distribution.py \
      --wheel "$work/artifacts/specromancy_engine-0.1.3-py3-none-any.whl" \
      --sdist "$work/artifacts/specromancy_engine-0.1.3.tar.gz" \
      --log "$work/distribution$v.log"
  )
done
git diff --check
```

Verification covered generated entry points and CLI invocation on macOS.
Live harness UIs and other operating systems were outside this run.
