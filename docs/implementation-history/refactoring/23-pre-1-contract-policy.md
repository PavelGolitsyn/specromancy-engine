# 23. Apply the current-contract rule throughout 0.x

**Executed on 2026-11-22 against `c83e437`.** The policy applies when
contributors author, review, and release a change. The review at `f265780` found that a real earlier
approval passed manifest validation and failed decision binding. It also found
four accepted adapter manifest identities. Both behaviors passed the full suite.

## Work

1. Put the release rule and definition of done in [workflow/instructions.md](../../../workflow/instructions.md).
   Any pre-1.0 release may change a public contract. Implement one current
   representation per surface. Retire superseded readers, writers, aliases
   kept solely for compatibility, migration paths, and positive old-format tests.
   Regenerate manifest-owned instructions with the installed CLI.
2. In the [public contracts](../../reference/contracts.md), state how to classify
   a change. Removing a required field, tightening previously supported input,
   or changing what a stored value authorizes is incompatible. Version the
   affected format and update fixtures together. Apply the same convention to
   explicitly versioned CLI output. An additive change that preserves the
   documented reader/writer contract can keep its version. Document changes to
   unversioned Python APIs and CLI commands and update their callers and tests.
3. Update the [release checklist](../../guides/releasing.md). Review the diff
   against the last released contract and the current development baseline.
   For each affected surface, record the old and new version or why the format
   remains compatible, the fixture proving current behavior, and what a consumer
   must do. Keep the package version in `pyproject.toml` independent of each
   format version. Applying the rule retrospectively changes current code,
   tests, and guidance. Published packages and tags are historical evidence.
4. Audit active code, examples, docs, tests, generated-file sources, and
   distribution gates for earlier compatibility decisions. Use the completed
   stages and release diffs to locate them. Classify each as a current feature,
   a compatibility-only path to remove, a refusal case, or historical evidence.
   Record each disposition and its owning stage here at execution. Include the
   pending [Windows plan](../windows-support/README.md), which still targets
   version-1 formats. Point its prospective gates at the current contracts when
   updating active guidance.

## Format decisions for this cleanup

| Surface | Baseline → planned | Reason and owner |
| --- | --- | --- |
| Run manifest | 1 → 2 | Stored approvals require a kind and different binding fields. Stage 24 |
| Event log | 1 → 2 | Approval payload semantics are part of the audit contract. Stage 24 |
| Action packet | 1 → 2 | One approval list became two and decisions can be replayed. Stage 25 |
| Status and successful/actionable CLI envelope | 1 → 2 each | Both directly expose pending approvals, including actions without an artifact or outcome. Stage 25 |
| Pipeline graph | 2 → 3 | Every phase must declare its workflow procedure. Stage 26 |
| Generated ownership manifest | 2 → 3, generator 4 → 5 | Selection evidence determines which paths the recorded targets can own. Stage 27 |
| Pipeline registry and adapter selection TOML | 1 → 1 each | Their structures already express the current contract. Exercise both version guards. |
| Project validators, workflow graph revision, package version | Separate authorities | A consumer owns its artifact schemas and graph revision. The release process owns the package version. |

## Acceptance

- [x] Authored instructions, regenerated harness instructions, contract reference,
  and release checklist give the same rule for past and future pre-1.0 changes.
- [x] Each active compatibility promise has a disposition, including parser
  alternatives, public facade aliases, persisted formats and fixture consumers.
  Historical execution records remain identifiable by their original revision.
- [x] Review can trace every planned incompatible change to its version,
  fixtures, refusal behavior where a reader exists, and consumer instructions.
  Verify instruction propagation with the shipped-configuration adapter tests.

## Execution inventory

Compared release tag `v0.1.3` (`d0bd655`) with development revision
`f265780`. From that revision to the starting checkout, only the plan changed.
The release shipped graph schema 1 and wrote ownership schema 1/generator 2. Stages
18–22 changed procedure sources and ownership. Commit `2e5451a` introduced
graph schema 2 and action approvals while keeping the run, event, action,
status and response versions at 1. The package at the development baseline
reports 0.1.4. The version decisions above start from that development baseline.

### Persisted data and CLI consumers

| Surface and owner | Disposition and fixture | Consumer action at cutover |
| --- | --- | --- |
| Run manifest 1 → 2 ([24](24-current-run-and-event-schemas.md)) | **Refuse.** Use the kindless awaiting-approval and recoverable specimens in `v0.1.3:tests/engine/fixtures/refactoring-compatibility/states.json`. Replace permissive nested validation from [Stage 14](14-persisted-data-diagnostics.md#nested-validation-decision-matrix) with the current action/transition bindings. Test both variants, decisions and interrupted grants. | Finish the run with its producing engine and original workflow resources, or start a separate run. Store and CLI must reject an obsolete manifest before any recovery or mutation. |
| Event log 1 → 2 (24) | **Refuse.** The same specimen contains the actual log bytes. Test an old event in a current log, including a one-revision gap. Keep current custom events, finite JSON metadata and exactly-once recovery as positive store fixtures. | Read archived logs with the matching engine. Check every event version before reconciliation or append, including read-only provenance lookup. |
| Action packet 1 → 2 ([25](25-cli-and-python-contracts.md)) | **Replace.** In `responses-current.json` and `test_action_approval.py`, capture both approval lists and decided actions after restart. Retire the single-list expectation. | Harnesses check the nested packet version before interpreting the lists or replayed decision. |
| Status 1 → 2 and successful/actionable envelope 1 → 2 (25) | **Replace.** Capture both pending variants, request numbers and decision commands in lifecycle and CLI fixtures. Check the outer version on adapter responses too. Keep error routing and exit-code fixtures in `diagnostics.json`. | Dispatch on envelope and nested status versions. Use action details for actions and artifact/outcome binding for transitions. These are emitted formats. Exercise both CLI entry points and an independent consumer. |
| Graph 2 → 3 ([26](26-current-pipeline-sources.md)) | **Remove** implicit `.agents/skills` lookup, the wider dependency boundary and the registry's missing-source migration pass. Use `canonical.json`, test-owned graphs, the shipped workflow and release-documentation example for current identities. **Refuse** graphs 1, 2 and future versions at init, resume and selected generation before side effects. | Declare both approval lists and each `skill_source`. Put authored procedures and dependencies under `workflow/`. Preserve original inputs for unfinished runs. |
| Ownership 2/4 → 3/5 ([27](27-current-adapter-ownership.md)) | **Remove** the single-target and inferred all-target readers. **Refuse** (schema, generator) pairs (1,1), (1,2), (2,3), (2,4), mixed and unknown identities. Use `adapters.json`, `adapters-generator-v2.json`, `adapters-generator-v3.json` and a baseline v4 manifest. Snapshot destinations across check and generate, including empty selection. | Preserve the existing tree. Generate from current authored inputs in a fresh directory and review paths and bytes before adoption. Prior hashes or hand-edited versions cannot authorize replacement or stale-file deletion. |

### Authored inputs, APIs and verification

| Evidence | Disposition and owner |
| --- | --- |
| Phase parser, published pipeline schema, canonical serializer and authoring examples | **Remove duplicate authoring forms in 26.** Use `allowlist` and `commands` in place of `mutation_allowlist` and `validation_commands`. Use command tables with `argv` for bare argv arrays. Use a validator table with `type`, `path`, `required_headings` and `heading_occurrence` as applicable. Convert string validators, phase-level validator options (including `validator_path`), and nested `schema`. Convert shipped, example, and test-created graphs together and test rejection of the retired forms. |
| Graph defaults and version authorities | **Keep in 26.** Omitted or false `pause` denotes the same current default. Preserve deterministic canonicalization and raw skill-byte hashing. Registry and harness-selection TOML each stay at schema 1 and need independent accepted and unsupported-version fixtures. Consumers keep those declarations. The graph author's `version`, the graph hash, project artifact validator schemas and the distribution version have distinct purposes. |
| [Stage 01's facade inventory](01-compatibility-baseline.md), `test_compatibility.py`, architecture assertions | **Remove duplicate spellings in 25.** Use `load_pipeline(..., repository_root=...)` for `load_config` and the `root=` synonym, `commands` for the model's `validation_commands`, and `config_hash` for `hash`. Use `sha256_*` for `hash_{bytes,text,json,file}`, `resolve_input_reference` for `resolve_artifact_reference`, `verify_manifest_artifacts` for `verify_artifacts`, and `capture_repository_snapshot` for `snapshot_repository`. Update callers of the old `capture_git_metadata` projection to consume the fields they need. |
| Store, engine and config facades | **Remove compatibility-only paths in 25.** Use module-level `generate_run_id` and `RunCorruptionError` for `new_run_id` and `CorruptRunError`. Use store methods `create`, `load`, `start_visit`, `mutate` for `create_run`, `load_run`, `create_visit`, `update`. Keep the instance method `RunStore.new_run_id()` with its injected sources. Migrate callers of private parser re-exports, `_Loader.parse_*` delegates, engine version re-export and private engine/store delegates to their owners. Exercise public operations and exception identity. |
| CLI and Python embedding guides, installed consumer tests | **Keep in 25.** Dynamic phase commands, transition approval without a request number when permitted, explicit and discovered roots, console/module entry points and the checkout launcher serve current callers. Preserve public facades for configuration, execution, schema loading and exception handling, store injection and recovery controls, render-only adapters and explicit metadata. Keep checkout/installed version lookup and the absence of the former `specromancy` import namespace in distribution smoke tests (28). |
| Generated-file sources, examples and active guides | **Update in 26/27.** Change schema declarations in workflow/example skill frontmatter and the packaged launch template when the graph changes. Regenerate wrappers and ownership evidence together. Replace fallback and upgrade-success guidance in the contract, CLI, architecture, authoring, installation and harness references with the corresponding stage's consumer steps. Keep registry path guards, shared target attribution, collision protection and manifest-last writes. |
| Lifecycle and adapter fixture consumers, `tools/verify_distribution.py` and `tools/distribution_smoke.py` | **Replace in [28](28-current-contract-verification.md).** The copied module list, fixture directory, helpers, tests README and distribution guide carry the old replay/upgrade gate into both wheels. Compare current captures directly. Retire transformations of generator-v3 text and v1/v2 golden comparisons. Bundle minimal authentic refusal specimens and verify current lifecycle, recovery and ownership through both installations. |
| Published tags, completed stage results, `responses.json` and previous captures | **Historical evidence (23/28).** The fixture README identifies `7f8aafa` as the runtime that produced the original adapter capture. The released copy is at `v0.1.3:tests/engine/fixtures/refactoring-compatibility/adapters.json`. Cite the revision containing each specimen when retiring it from the active suite. |
| [Pending Windows plan](../windows-support/README.md) prepared at `b587ac8` | **Retargeted in 23.** Its prospective Windows checks use the tested revision's formats. Use current records for successful same-host replay and one-event recovery, obsolete specimens for byte-preserving refusal, and current ownership for both wheel installations. The earlier POSIX measurements retain their recorded revision. |

## Verification

Tested the Stage 23 working tree based on `c83e437` on macOS 26.7.3 arm64,
Python 3.14.4. Installed the checkout in its dedicated environment with
`python -m pip install --no-index --no-build-isolation -e .` using the
already provisioned build backend.

| Check | Result |
| --- | --- |
| `specromancy adapters generate` | Generated 27 outputs. Compared with the starting manifest, only the authored instruction input and the three instruction output hashes changed among the input and output records. |
| `python -m unittest tests.shipped_configuration.test_adapters` | 6 passed, including comparison of the authored instructions with root, Claude and Copilot outputs. |
| `python -m unittest discover` | 382 passed, zero skips. |
| `specromancy adapters generate --check` and `bin/specromancy adapters generate --check` | Both reported up to date. |
| `git diff --check` | Passed. |
