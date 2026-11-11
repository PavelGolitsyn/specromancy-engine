# Stage 16 — Define the generated-harness contract

Status: **planned; not implemented**. Prepared 2026-11-11 against
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

- [ ] The source/output boundary, additive field, normalization, and compatibility
  policy are documented and backed by an inventory.
- [ ] No stage requires generated output as an upstream source.
- [ ] Resolved source boundaries, skill identity, thin wrappers, and versioned
  ownership restrictions are explicit, with regression cases assigned below.
- [ ] Baseline focused/full tests and existing adapter check pass.
- [ ] No runtime, workflow, generated file, or user run is changed by this stage.

Record implementation results in this document before marking it complete.
