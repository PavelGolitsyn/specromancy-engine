# Stage 16 — Define the generated-harness contract

Status: **complete**. Executed 2026-11-11 against
`b1e64d4efd7b4147a6d0afdaf2d615c36701f43e` with an initially clean working tree.
Design and characterization only; the new generator remains future work.
Prepared 2026-11-11 against
`d0bd655120dfd6eb2bdbc7e61fc12ae45e46f82b`.
Prerequisite: completed stages 01–15. Category: design and characterization.

## Objective

Make harness directories and root `AGENTS.md` generated presentation surfaces.
Users author workflow policy under `workflow/`; an installed engine release
provides canonical, generic adapter and orchestration templates. Neither adapter
source discovery nor new workflow execution may need generated files to exist.

“No skills or prompts in `.agents`” means no **hand-authored canonical inputs**
there. Generated discovery skills remain allowed, just like generated Claude and
OpenCode files. Root `AGENTS.md` likewise remains a supported generated output,
never an input or an installation prerequisite. Keep `.claude/CLAUDE.md` at its
existing location; this work does not add a second root Claude instructions file.

## Inspected evidence

| Current file / behavior | Required change |
| --- | --- |
| `_adapters/adapter_sources.py` requires root `AGENTS.md`, scans `.agents/skills`, and requires the `pipeline` skill | Capture only declared workflow sources, release resources, registry/configuration, and CLI metadata |
| `_config/config_phase_parser.py` resolves every `skill` to `.agents/skills/<id>/SKILL.md` | Allow explicit canonical workflow source paths without depending on generation |
| `_adapters/adapter_rendering.py` embeds templates and launches through `.agents/skills/pipeline/SKILL.md` | Use packaged templates and self-contained orchestration content in each harness launch surface |
| `_adapters/adapter_ownership.py` owns only `specromancy-*` skills under `.agents`, does not own root `AGENTS.md`, and uses one path allowlist without checking generator version | Validate old manifests under their original ownership rules before admitting the new output paths |
| `config_fields.existing_path` checks resolved repository containment only | Enforce the canonical workflow boundary for every new adapter source, including indirect dependencies |
| `cli.main` loads the registry before adapter dispatch | Guard adapter registry reads at CLI bootstrap, before parsing, without tightening ordinary runtime loading |
| `pyproject.toml` packages only schema JSON as data | Ship generic templates in both wheel and sdist |
| `MANIFEST.in`, distribution verification, fixtures, and current guides describe canonical hidden skills | Migrate the example, active documentation, packaging checks, and ordinary fixtures together |
| Visits persist resource paths and hashes; pipeline identity uses canonical configuration | Preserve old bytes; moving a source is a provenance/configuration change, not a transparent rename |

Paths in this table are relative to `src/specromancy_engine/` unless named as
repository-level files. Recheck them at implementation time.

## Target source and output layout

```text
src/specromancy_engine/resources/adapters/  # release-owned generic templates
workflow/
  instructions.md                          # user-owned repository instructions
  skills/<skill-id>/SKILL.md               # user-owned portable phase procedures
  pipelines.toml                          # existing registry
  pipelines/*.toml                        # graphs, with explicit skill_source
  templates/*.md                          # existing artifact templates

AGENTS.md                                 # generated repository instructions
.agents/skills/*/SKILL.md                  # generated discovery surfaces only
.claude/CLAUDE.md                         # generated repository instructions
.claude/skills/*/SKILL.md                   # generated discovery surfaces only
.claude/commands/specromancy/*.md          # generated wrappers
.github/copilot-instructions.md           # generated repository instructions
.github/prompts/specromancy-*.prompt.md    # generated wrappers
.opencode/commands/specromancy-*.md        # generated wrappers
adapters/manifest.json                    # generated ownership/provenance record
```

The packaged resources contain generic instruction envelopes, orchestration,
launch/command templates, and thin phase-discovery wrappers. They contain no
shipped phase names, transition order, repository testing policy, or approval policy. The
current generic `pipeline` procedure moves into these resources; workflow-specific
phase procedures move into `workflow/skills/`. Do not copy the producer's workflow
into every installed consumer or add automatic project scaffolding.

## Decisions for all following stages

1. Use the fixed source `workflow/instructions.md`. Missing/unreadable content
   produces a controlled source error; do not fall back to root `AGENTS.md`.
   Do not add a settings file solely to customize this one path.
2. Retain `skill = "compose"` as the portable skill/discovery identifier. Add
   optional `skill_source = "workflow/skills/compose/SKILL.md"`, interpreted
   relative to the repository root, explicitly restricted to `workflow/`.
   Require it for every phase used by the new adapter generator. See Stage 18
   for legacy runtime compatibility and canonical serialization.
3. Require canonical frontmatter `name == skill`. During adapter generation,
   each skill identifier across all registered pipelines maps to exactly one
   normalized declared source path, resolving to one canonical file. Repeated
   phases may reuse the same pair;
   different identifiers may not reference the same resolved file, and alternate
   path spellings do not create additional identities. Do not silently rename
   frontmatter or use the parent directory name as identity. Reserve `pipeline`
   and `specromancy-*` for generated orchestration/launch skills. Validate these
   bindings before deduplicating reads/hashes; render every required harness
   wrapper independently of source-read deduplication. Do not scan arbitrary
   directories or import unrelated installed skills.
   Ordinary runtime loading validates the selected graph's metadata and bindings
   only; repository-wide collision checks belong to adapter generation. Preserve
   lazy graph loading so an unrelated invalid graph cannot block a valid run.
4. Keep workflow skill files portable Markdown with the existing supported
   frontmatter. Generate phase skills as thin wrappers containing validated
   discovery metadata, provenance, and an explicit instruction to load the
   canonical workflow file. Do not copy phase procedure bodies into outputs.
   Resolve supporting references relative to that canonical file, never the
   wrapper. Keep generic orchestration embedded in each pipeline launch skill
   for harness independence. Migration must audit existing relative references.
5. Retain current CLI commands, public adapter facade signatures, output envelope,
   manifest path, and run/event schemas. Plan generator version 3 with adapter
   manifest schema 2, recording each output once with its consuming targets as
   specified in Stage 19. Establish shared requirements in that stage with all
   targets enabled; Stage 22 adds selection without redesigning attribution.
   Package IDs such as `@package/specromancy_engine/resources/adapters/launch.md`
   are provenance labels, never repository filesystem paths.
6. Every generated byte must derive from captured canonical inputs and deterministic
   rendering. Hash the actual release template bytes and release identity, user
   instruction/skill bytes under the documented normalization rule, validated
   registry/graphs, existing dependencies, and CLI metadata. Never hash generated
   `AGENTS.md`, generated `.agents` content, mtimes, or installation paths.
7. Preserve existing normalization intentionally: adapter text uses UTF-8 and LF
   with one trailing newline; runtime visit provenance still hashes raw canonical
   file bytes. Do not normalize approved artifacts or conflate these two contracts.
8. Protect unowned existing files, including a root `AGENTS.md` identical to the
   expected output. No automatic adoption, force-overwrite, migration command,
   directory deletion, or recursive ownership of `.agents` is introduced.
9. Validate previous manifests by supported schema, generator name, and generator
   version before granting ownership. Each supported combination retains its
   own path and target restrictions; a widened new-version allowlist must never
   apply to old entries. Reject unsupported/malformed combinations before any
   writes or cleanup. Stage 19 specifies migration and forged-entry regressions.

## Canonical source path boundary

For new adapter generation, every captured **repository filesystem source** must
have both a normalized declared location and a resolved regular-file location
under the repository's actual `workflow/` directory. This includes instructions,
skills, registry, registered graphs, artifact templates, validator files, and
Stage 22's adapter configuration. Preserve each field's documented relative base
when computing the declared location; graph-relative `../templates/...` remains
valid when it stays inside `workflow/`. Reject escapes before reading/parsing or
hashing a source, including indirect dependencies loaded during graph validation.

For adapter CLI commands, apply the guard before the initial registry load, not
only inside adapter capture: the current CLI parses the registry before dispatch.
Use the same source guard in the new capture path. Public facade calls supplied
an already-loaded registry validate its root/path and registration source
locations before consuming its contents or reading dependencies; a caller's
earlier reads are outside that facade's guarantee. Reuse the guarded CLI registry
snapshot without reading/parsing it again. Keep ordinary runtime registry
loading and selected-graph validation on their existing compatibility path.
Prepare this guarded entry point in Stage 18 and switch public CLI dispatch in
Stage 20 alongside the generator; no preparatory stage changes legacy behavior.

Resolve the repository root first. Do not establish the source boundary by
following a symlink at `workflow/` to an arbitrary repository directory: reject
a symlinked workflow root. For descendant file/directory symlinks, require the
final target to remain inside that canonical workflow directory. Check both
declared and resolved locations against generated locations as well: root
`AGENTS.md`, harness output paths/directories, `adapters/manifest.json`, and
expected/previously validated owned outputs cannot be canonical inputs. Apply
this exclusion independently of selected harnesses, including absent outputs;
selection must not make another harness's output eligible as a source.

Use one small shared path-validation boundary, with source-labelled diagnostics,
instead of scattered checks for `.agents`. Repository containment alone is not
sufficient. Legacy runtime loading retains its explicitly separate compatibility
rules; it must never be a fallback used by new adapter source capture.

Package templates are a separate source class, read only from allowlisted
release resources through `importlib.resources`, never resolved as consumer
repository paths or overridden from harness directories. Derived CLI metadata
is not a filesystem source. Previous manifests and existing outputs may be read
for ownership/drift checks under their own rules; those observations never enter
canonical source hashes. These distinctions avoid banning the output inspection
needed for safe regeneration.

Thin wrappers do not remove canonical procedure content from provenance. Hash
the captured complete canonical file under the documented normalization rule;
a body-only edit may change only the manifest while wrapper bytes stay identical.
Keep content digests in the manifest, not embedded in phase-wrapper headers;
wrapper provenance identifies source paths and release templates. Runtime visits
continue hashing the raw canonical file bytes.

## Work sequence and intended files

1. Record the starting revision/status and inventory all canonical/generated
   files, references, manifest ownership, and active-run migration constraints.
2. Add focused characterization to `tests/engine/unit/test_adapters.py`,
   `test_config.py`, and `tests/engine/contract/test_compatibility.py` only where
   current coverage is missing. Preserve historical compatibility captures.
3. Specify fixture cases for absent output directories, mismatched frontmatter,
   identity aliases, direct/symlinked output dependencies, forged old manifest
   entries, ownership collisions, release-template drift, and old runs.
   Add passing behavior tests with the implementing stages; do not leave the
   baseline suite deliberately red or blanket-skip new acceptance cases.
4. Record the expected changes to source hashes, generated bytes, action skill
   paths, and missing-source diagnostics. All other contracts remain unchanged.
5. Align overlapping Windows-plan work at execution time, without importing its
   platform expansion into this refactor. Its older canonical-location statement
   is superseded by this plan for this workstream.

## Verification and exit criteria

Install the checkout in a dedicated environment before testing:

```sh
python -m pip install -e .
python -m unittest tests.engine.unit.test_adapters tests.engine.unit.test_config tests.engine.contract.test_compatibility
python -m unittest discover
specromancy adapters generate --check
git diff --check
```

Use that environment's interpreter and scripts on `PATH`; an existing provisioned
environment may use `--no-index --no-build-isolation` when it has the pinned build
backend. Record the actual command. This planning pass did not run these tests.

- [x] The source/output boundary, additive field, normalization, and compatibility
  policy are documented and backed by an inventory.
- [x] No stage requires generated output as an upstream source.
- [x] Resolved source boundaries, skill identity, thin wrappers, and versioned
  ownership restrictions are explicit, with regression cases assigned below.
- [x] Baseline focused/full tests and existing adapter check pass.
- [x] No runtime, workflow, generated file, or user run is changed by this stage.

## Execution inventory

Rechecked the inspected-evidence table against the execution revision. Its
source-discovery, configuration, CLI bootstrap, packaging, and ownership
observations still apply. Stage 16 changes only this record, the plan index, and
the three specified test modules. No public runtime contract changes yet.

### Canonical files and generated ownership

| Current input or surface | Inventory and migration destination |
| --- | --- |
| Root `AGENTS.md` | User-owned instructions, currently read and hashed by capture; move policy to `workflow/instructions.md` in Stage 20, then generate the root envelope |
| `workflow/pipelines.toml` | One registration, `implementation`, pointing to `pipelines/implementation.toml`; retain registry-relative graph paths |
| `workflow/pipelines/implementation.toml` | Four phases using `research`, `plan`, `implement`, `review`; add explicit repository-relative `skill_source` declarations in Stage 20 |
| `.agents/skills/{research,plan,implement,review}/SKILL.md` | Four canonical phase procedures; relocate to corresponding `workflow/skills/<id>/SKILL.md` in Stage 20 |
| `.agents/skills/pipeline/SKILL.md` | Generic canonical orchestration, required by current capture; package generic content in Stage 17, retire repository source at Stage 20 |
| `workflow/templates/{implementation,plan,research,review}.md` | Four graph-referenced artifact templates, captured as raw dependency bytes today; remain canonical workflow inputs |
| `workflow/templates/request.md` and `workflow/README.md` | Workflow support/documentation, not captured adapter inputs; no new arbitrary directory scanning |
| `_adapters/adapter_rendering.py` | Inline instruction, command, launch, provenance, and skill-mirroring content; release resources replace the generic templates in Stages 17–19 |
| CLI metadata | Derived command definitions, not a repository filesystem source; retain deterministic capture |
| `adapters/generate.py` | Compatibility launcher, not canonical policy or a manifest-owned generated output |

The checked-in manifest uses schema **1**, generator **specromancy v2**, and
canonical-source digest
`74710ca101bc40c7757e56037e287638d366eba03976365c6a272b04a7e04027`.
Its 13 inputs are instructions, registry, graph, four template dependencies,
five canonical skills, and CLI metadata. Release template bytes/identity are not
currently independent hash inputs. Normalization applies to instruction/skill
text; registry/graph hashes use canonical JSON; dependencies use raw bytes.

It owns **21 output files**, plus the separately written manifest:

| Target attribution in v2 | Exact output families | Count |
| --- | --- | --- |
| Codex | `.agents/skills/specromancy-implementation/SKILL.md` | 1 |
| Claude | `.claude/CLAUDE.md`; `.claude/commands/specromancy/{init,phase,resume,status}.md`; `.claude/skills/{implement,pipeline,plan,research,review,specromancy-implementation}/SKILL.md` | 11 |
| Copilot | `.github/copilot-instructions.md`; `.github/prompts/specromancy-{init,phase,resume,status}.prompt.md` | 5 |
| OpenCode | `.opencode/commands/specromancy-{init,phase,resume,status}.md` | 4 |

Codex and Hermes are recorded as native targets, both discovering the shared
launch skill; Hermes owns no separate output. Root `AGENTS.md` and ordinary
`.agents` skills are unowned. The current ownership reader validates schema,
paths, target mapping, duplicates, and hashes, but **does not validate generator
identity/version**. Current check mode compares expected bytes without running
that ownership reader. Stage 19 must validate both modes before granting any
new output authority. Preserve v1 compatibility captures and document any
additional supported historical combination under its original restrictions.

### References, fixtures, and packaging

- Current launch skills explicitly load `.agents/skills/pipeline/SKILL.md`;
  Claude phase mirrors copy full canonical bodies. Stages 19–20 replace these
  dependencies with embedded generic orchestration and thin canonical-file
  references. No new source reader may consume a generated wrapper.
- Audited the five producer procedures and three release-documentation example
  procedures: no Markdown relative support links or `../` references need
  rebasing. Procedures use action-packet resource paths and commands from the
  consumer root. The generic orchestrator references `workflow/pipelines.toml`
  from that root. Graph template references such as `../templates/research.md`
  and the example's `../templates/release-notes.md` remain graph-relative.
  Stage 19 still needs an explicit relative-support-file fixture to prove that
  thin wrappers preserve the canonical file's reference base.
- The consumer example owns `AGENTS.md`, its registry/graph, two artifact
  templates, and `.agents` skills `pipeline`, `draft-release-notes`, and
  `review-release-notes`. Migrate these together in Stage 20. `MANIFEST.in` and
  `tools/verify_distribution.py` explicitly list those hidden skill paths;
  `tools/distribution_smoke.py` and `tests/packaging/test_distribution.py` verify
  the packaged consumer. Package data currently includes only schema JSON.
- Ordinary on-disk fixtures to migrate in Stage 20: `config-valid-minimal`,
  `config-valid-branch`, `config-valid-loop`, `example-pipeline`, and
  `replacement-pipeline` under `tests/engine/fixtures/`. Phase IDs can differ
  from skill IDs (for example `inspect` uses `research`); preserve that distinction
  and validate metadata against `skill` during migration rather than inferring
  identities from phase IDs or directory names. Temporary fixture builders in unit/contract
  tests and `tests/engine/support.py` need the same audit. Keep deliberate legacy
  cases separate.
- Preserve `tests/engine/fixtures/refactoring-compatibility/` byte-for-byte,
  including source files, v1/v2 adapter captures, canonical JSON, responses,
  diagnostics, and stored run/event snapshots. New expectations belong in
  separate cases, never regenerated historical records.
- Active documentation to update with cutover: `README.md`, `docs/README.md`,
  `workflow/README.md`, `tests/README.md`, the consumer example README,
  guides `installation`, `authoring-pipelines`, `harnesses`, and
  `distribution-verification`, and references `architecture`, `contracts`,
  `harness-compatibility`, and `cli`. Leave current usage guidance accurate until
  Stage 20; this design record describes the future contract.

### Existing-run constraint

Read the local run files directly without invoking recovery or other mutating
CLI commands. Run `20261029T211240Z-41c13687` has schema 1, revision 2, status
`awaiting-agent`, current visit 1 (`research`, pending), and no approvals. Its
saved graph is `workflow/pipelines/implementation.toml` with hash
`83f485004e10fa7ef664e982f146a793a5fcf7f43e7fcf0fb67eb3f807a93d13`.
The pending visit seals `.agents/skills/research/SKILL.md` with hash
`e074c668eac368f16f2ea004a8034a76a4b00f13e4c62d0dfa81f7801bb6431d`
and `workflow/templates/research.md` with hash
`a8706ba65d53b85a35a54a186099ab5a40aa847162226cbd4069ff7f3aeb5f88`.

This is a concrete Stage 20 migration constraint, even though the visit has not
started. Replacing the skill with a wrapper or adding `skill_source` to its graph
cannot transparently continue that run. Recheck at cutover: finish it under the
original files or retain an original checkout for continuation before replacing
overlapping paths. Do not infer permission to finish it from this stage request,
rewrite provenance, or move its immutable request artifact. All three local run
files remain unchanged in this stage.

The Windows plan is still marked planned in its index and all seven stages;
there is no completed implementation to merge here. Its repository-only path
boundary and canonical hidden-skill statement remain legacy runtime guidance.
For the new adapter path, this workstream's stricter workflow boundary takes
precedence. Coordinate shared path helpers, package allowlists, and invocation
tests when either workstream advances; no native Windows support is claimed.

## Regression allocation and intentional changes

These are future acceptance cases, not skipped or failing baseline tests. Use
temporary repositories with sentinel source/output bytes and assert rejection
before source reads or mutations at the boundary concerned.

| Fixture case | Required assertion and implementing stage |
| --- | --- |
| Only canonical workflow inputs; no harness directories/root instructions/manifest | Runtime validate/init/phase/resume succeeds (18); generation/check and deleted-output rebuild succeed (19–21) |
| Missing/unreadable `workflow/instructions.md` or declared skill, with a same-named generated file present | Controlled source-labelled error, no fallback or writes (18–20) |
| Frontmatter mismatch, missing/invalid supported metadata, reserved `pipeline` or `specromancy-*` identifier | Controlled identity error; never silently rename metadata (18–19) |
| Repeated identical binding; one ID with distinct sources; two IDs aliasing one file; alternate declared spellings and descendant symlinks | Accept reuse; reject ambiguous identity before read/hash deduplication; render every required wrapper (18–19) |
| Valid selected graph plus unrelated invalid graph or cross-graph collision | Selected runtime stays lazy/usable; repository-wide generation fails (18–20) |
| Instructions, skill, registry, graph, template, validator directly or indirectly point at root instructions, harness files, manifest, or owned outputs | Check declared and resolved locations before parse/hash, including malformed target content and absent generated locations; apply to unselected targets too (18–20, 22) |
| Symlinked workflow root; descendant file/parent symlink outside workflow but inside repository; safe descendant symlink and `../templates` within workflow | Reject root/escape, accept safe descendants and graph-relative resources (18–19) |
| CLI registry symlink versus already-loaded public facade registry | Guard before initial CLI parse; validate facade root/path/registration locations; reuse one CLI snapshot (18 preparation, 19 capture, 20 dispatch) |
| Canonical skill referencing adjacent support file; body-only skill edit | Wrapper directs loading canonical file with its reference base; full body remains hashed even when wrapper bytes stay identical (19) |
| Forged v2 manifest claims root instructions, pipeline skill, or phase skill with matching hashes | Reject as desired output and as stale output before replacement/deletion; validate old target restrictions in generate and check (19) |
| Missing/malformed/unknown generator/schema combinations and wrong target attribution | Controlled failure before writes; valid v2 and explicitly supported historical manifests migrate under original rules (19) |
| Unowned root/skill output identical to expected; unrelated skill/support file; modified stale owned output | No adoption, recursive ownership, or collateral deletion; stale removal requires recorded hash (19–20) |
| Release-template edit, version change, separate install path, CRLF/trailing newlines | Capture actual package bytes/identity; deterministic normalized text; installation location excluded (17, 19, 21) |
| Legacy run with unchanged sources, moved source, edited body, or normalized line endings | Preserve historical replay and raw-byte drift checks; additive source field changes graph identity; never rewrite old records (18, 20–21) |
| Selected harness subsets and shared surfaces | Schema-2 consumer unions, no duplicate ownership; source exclusions independent of selection; configuration/output edits still visible to mutation checks (22) |

Expected deltas are limited to adapter source hashes/input labels, generated
bytes/paths and ownership attribution, explicit-source pipeline identity and
`action.skill` paths, and missing/unsafe-source diagnostics for the new path.
Release resources add `@package/...` provenance labels without filesystem
resolution in consumer repositories. Phase-wrapper headers identify source paths
and templates, not content digests. Adapter instruction/skill text remains UTF-8,
LF, one trailing newline; runtime provenance and approved artifacts keep raw
bytes. CLI commands/envelopes, public adapter signatures, run/event schemas,
legacy graph hashes without the new field, mutation enforcement, and approval
invalidation retain their contracts.

Stages 17–19 intentionally retain the existing public generator while preparing
the independent path; this temporary sequencing does not make generated outputs
inputs to the new design. Stage 20 switches capture and migrates sources together.

## Characterization and verification results

Added six focused tests without changing fixtures or runtime:

- Adapter text normalization across CRLF, CR, and missing/extra final newlines
  preserves generated bytes and manifest hashes.
- Missing legacy root instructions produce the controlled source error.
- An identical unowned output is rejected without adoption or writes.
- Matching-hash v2 manifest claims on root instructions and canonical skills
  cannot authorize writes; check reports drift and preserves files.
- Legacy skill lookup and diagnostics retain the hidden path; editing procedure
  content leaves canonical graph bytes/hash unchanged and omits `skill_source`.
- Visit/action provenance hashes raw CRLF skill bytes; a normalization-only edit
  blocks activation without rewriting stored run/events.

Existing tests already cover missing orchestration, deterministic generation,
no-write drift checks, stale-file races, source diagnostics, repository escapes,
graph-relative dependencies, sequential old-run replay/recovery, and historical
adapter bytes. The first focused run exposed two test assumptions: the render
facade requires CLI metadata, and check mode reports byte drift rather than
ownership diagnostics. Corrected the tests to characterize the public behavior;
the stronger check-mode validation remains explicitly assigned to Stage 19.

Verification used the existing dedicated `.venv` with Python 3.14.4 on macOS
(Darwin arm64). Actual
commands (the PATH prefix selects that environment's interpreter and scripts):

```sh
.venv/bin/python -m pip install --no-index --no-build-isolation -e .
PATH="$PWD/.venv/bin:$PATH" python -m unittest tests.engine.unit.test_adapters tests.engine.unit.test_config tests.engine.contract.test_compatibility
PATH="$PWD/.venv/bin:$PATH" python -m unittest discover
PATH="$PWD/.venv/bin:$PATH" specromancy adapters generate --check
git diff --check
```

Editable installation succeeded using the provisioned pinned backend. Final
focused tests: **68 passed** in 0.589 seconds. Full suite: **322 passed** in
49.387 seconds, with no reported skips. Adapter check: **generated adapters are
up to date**. `git diff --check` passed. A SHA-256 comparison against the
pre-edit inventory found all 54 protected files unchanged: root instructions,
workflow, harness surfaces, adapters, local run files, and historical compatibility
captures. The final diff contains only the two plan documents and three test
modules listed above. No adapter generation was
performed in the checkout. Python 3.11, other operating systems, and distribution
builds were not rerun for this characterization stage; their acceptance remains
with the implementing stages.
