# Stage 19 — Build independent adapter capture and rendering

Status: **planned; not implemented**. Depends on Stages 16–18.
Category: adapter implementation, exercised on isolated workflow-only fixtures.

## Objective

Prepare the complete source-to-output path so adapters can be generated from a
release plus `workflow/`, with no source reads from harness output locations.
Keep the public generator on its existing path until the atomic repository
cutover in Stage 20; temporary implementation overlap ends there.

## Implementation

1. Replace the `AdapterSources.agents` concept with canonical repository
   instructions, declared workflow skill records, and packaged templates. Capture
   all content once per invocation and use that same snapshot for rendering and
   hashes. Preserve the render-only facade's documented input contract or record
   any intentional change explicitly; do not silently add output-file reads.
   Enforce Stage 16's declared-and-resolved workflow boundary on every repository
   source before its bytes are parsed/hashed, including registry/graphs and their
   indirect template/validator dependencies. The guard applies to render-only,
   generate, and check paths alike. Package resources and ownership/drift reads
   retain their separate rules; neither can bypass canonical source validation.
   Use Stage 18's shared guard before registry/graph reads. For facade calls
   receiving an already-loaded registry, validate its root/path and registration
   source locations before consuming it; document that a caller's earlier reads
   are outside this guarantee. Reuse the CLI's guarded registry snapshot without
   rereading it, preserving one capture for rendering and provenance.
   Public CLI bootstrap switches to the guarded loader in Stage 20, before its
   initial registry read, together with the public generator switch.
2. Validate registered graph declarations without legacy source resolution first.
   Require explicit workflow `skill_source` fields and report every needed
   migration clearly. Load validated pipelines and require frontmatter
   `name == skill`. Enforce one normalized declared source/resolved file per
   identifier and reject different identifiers aliasing one file, conflicting
   declarations, or reserved names before writing. Reuse of the same pair across
   phases is valid. Keep these repository-wide checks out of ordinary runtime
   graph loading. Deduplicate source reads/hashes only after identity checks;
   separately enumerate every required harness wrapper. Capture
   `workflow/instructions.md`; never inspect root `AGENTS.md` or `.agents` as
   canonical inputs, directly or through symlinks/dependency declarations.
3. Render root `AGENTS.md`, `.claude/CLAUDE.md`, and Copilot instructions
   independently from the same captured instruction body and packaged envelope.
   No output is rendered by reading another output. Add generated provenance
   headers identifying `workflow/instructions.md` and the release template.
4. Generate `.agents` and Claude phase skills as thin discovery wrappers from the
   same validated canonical metadata and packaged wrapper template. Include
   provenance and a repository-relative canonical source path, with an explicit
   instruction to load and follow that file using the supplied run context.
   Resolve that path from the consumer repository root, not the wrapper directory.
   Resolve supporting references relative to the canonical file, never the
   generated skill directory. When an action packet is available, its canonical
   skill path remains authoritative; a mismatch or missing canonical file must
   stop execution rather than fall back to copied/cached content. Do not copy
   phase procedure bodies or add phase-specific logic to wrappers. Generate the
   generic `pipeline` skill and per-pipeline `specromancy-<id>` launch skills
   separately from release orchestration templates.
5. Make each launch skill carry the packaged generic coordination instructions,
   including its bound pipeline ID. Remove the instruction to load
   `.agents/skills/pipeline/SKILL.md`. Command wrappers continue using the CLI and
   `action.skill.absolute_path`, which now points into `workflow/`. Thus Claude,
   Copilot, and OpenCode behavior does not depend on a `.agents` file being present.
6. Keep existing command names, argument quoting/position conventions, and
   deterministic sorted output paths. Use the existing CLI help metadata as the
   command contract; templates are presentation, not a competing command registry.
7. Construct manifest provenance from workflow inputs, validated configuration,
   dependencies, CLI metadata, package identity, and exact template bytes. Use
   logical package IDs without attempting `root / package_id`. Keep source order
   deterministic and shared sources unique. No generated path may appear in
   `canonical_source.inputs`.
   Continue hashing complete canonical skill files even though only metadata and
   paths enter phase wrappers. A body-only edit may leave wrappers unchanged
   while changing manifest provenance; do not treat that as missing generation.
8. Define each harness's required output set and render their union with all five
   targets enabled. Shared paths are generated and owned once, with every
   consuming target recorded accurately. Establish the schema below now;
   Stage 22 filters these same requirement sets without changing attribution.

## Shared requirements and manifest schema

Use these required surfaces, preserving the documented discovery entry points:

| Harness | Required surfaces |
| --- | --- |
| Codex | Root `AGENTS.md` and shared `.agents` orchestration, phase, and pipeline launch skills |
| Hermes | Root `AGENTS.md` and the same shared `.agents` skills |
| Claude | `.claude/CLAUDE.md`, `.claude/skills/`, and Specromancy command wrappers |
| Copilot | `.github/copilot-instructions.md`, Specromancy prompts, and shared `.agents` skills |
| OpenCode | Root `AGENTS.md`, shared `.agents` skills, and Specromancy command wrappers |

Generator version 3 writes adapter manifest schema 2. Retain the existing
top-level fields and source-record shape. Replace each generated record's singular
`target` with a sorted, unique, nonempty `targets` list of consuming harness IDs;
keep `path` and `sha256`. For example, root `AGENTS.md` has
`targets: ["codex", "hermes", "opencode"]`. Each path appears exactly once in
`generated`. Top-level `targets` records retain `name`, `mode`, `paths`, and
applicable `discovery_paths`; `paths` now lists every output that target requires,
including shared ones. Referencing a path from several targets is not duplicate
file ownership. Require both directions of attribution to agree, and validate
discovery paths against that target's requirements.

Version 3 records all five enabled targets. Stage 22 keeps this shape, recording
only explicitly selected targets and intersecting each output's consumers with
that selection; outputs with no consumers are omitted. Keep legacy single-target
records confined to their original manifest reader. This stage introduces the
shared requirement model, not user-selectable configuration or CLI flags.

## Ownership work

Replace current single-target path attribution with the shared requirement model;
extend `_is_managed_adapter_path`, drift discovery, and
preflight to support root `AGENTS.md` and exact `.agents/skills/<id>/SKILL.md`
outputs. Do not treat every file underneath `.agents` as owned. Unrelated skills
that are neither expected outputs nor manifest-owned stale outputs are ignored;
collisions at expected paths still fail. Apply the same rule consistently to
Claude skills. Output directories are not a canonical source inventory.

Preserve root containment, symlink checks, preflight-before-write behavior,
per-file atomic replacement, manifest-last publication, and hash-checked deletion
of stale owned outputs. Add explicit version-specific previous-manifest validation
before converting ownership records or computing overwrite/cleanup eligibility:

| Manifest identity | Ownership validation |
| --- | --- |
| Schema 1, generator `specromancy`, version 2 | Original v2 path allowlist and target mapping; `.agents` owns only `specromancy-*/SKILL.md`, never root `AGENTS.md` or ordinary phase/pipeline skills |
| Schema 2, generator `specromancy`, version 3 | Explicit new output allowlist and all-target shared attribution, including root instructions and generated phase/pipeline skills |
| Any additional supported historical version | Its own documented original restrictions, verified against preserved fixtures; no inheritance from the newest allowlist |
| Missing/malformed generator identity, unsupported name/version/schema combination | Controlled error before any writes or cleanup |

Validate record shape, normalized paths, duplicate/self-owned entries, target
attribution, and hashes under the manifest's original rules first. Only then
convert validated ownership into the internal representation used for migration.
Freeze the v2 rules independently of `_is_managed_adapter_path` and
`_target_for_path` changes; sharing a widened current allowlist would retroactively
grant ownership. Preserve valid v2 Claude and other harness paths exactly as the
old contract allowed them, rather than narrowing them based on new selection.

Even a matching file hash does not legitimize a v2 entry for root `AGENTS.md`,
`.agents/skills/pipeline/SKILL.md`, or `.agents/skills/compose/SKILL.md`. Reject the
whole manifest; do not drop illegal entries and continue. Validate it in check
mode too. Generator-version metadata describes format semantics, not authenticity
or ownership proof for an unlisted file; no manifest signing is introduced.
Document the existing recovery limits: multi-file generation is not a filesystem
transaction.

Keep the current contract for regeneration of modified owned files explicit;
this change must not silently broaden it. In particular, preserve conflict
protection for modified stale files and all unowned instruction/skill files.

## Intended files and tests

- Existing `_adapters/adapter_sources.py`, `adapter_rendering.py`,
  `adapter_contracts.py`, `adapter_ownership.py`, and their facade wiring only as
  required for testable preparation.
- Resource templates from Stage 17 and shared configuration precheck from 18.
- Guarded registry capture in `registry.py`; public `cli.py` bootstrap wiring
  remains part of Stage 20's coordinated switch.
- `tests/engine/unit/test_adapters.py`, `test_multi_pipeline_adapters.py`,
  `tests/engine/contract/test_adapter_drift.py`, `test_multi_pipeline.py`.

Required behavior cases:

| Case | Expected result |
| --- | --- |
| Only canonical workflow inputs exist | Render/write all expected outputs successfully |
| Generate twice and then check | Identical output/manifest bytes; check performs no writes |
| Remove generated `.agents` and root `AGENTS.md` in a disposable fixture | Check reports drift, generation reconstructs them; no missing-source error |
| Change only a generated file | Canonical source hash is unchanged; check reports output drift |
| Change instructions, skill, registry, CLI metadata, or a release template | Source hash changes and the appropriate outputs/manifest drift |
| Change only a canonical phase body with metadata/path unchanged | Wrapper bytes stay identical; manifest source hash changes and check reports drift |
| Two consumers use the same package from different install paths | Identical inputs produce identical relative output bytes/hashes |
| Frontmatter mismatch, different identifiers alias one file, same identifier with different sources, or reserved identifier | Controlled identity conflict before writes |
| Several phases share a skill and several harnesses need it | One captured source/hash; all distinct required wrapper paths exist |
| Root instructions and shared skills in schema 2 | One generated record per path; sorted consumers and target path lists agree with the requirement sets |
| Missing, duplicate, unknown, or inconsistent consumer attribution | Controlled manifest rejection before replacement or cleanup |
| Phase wrapper inspected/invoked through the supported test harness | Metadata and canonical load instruction present; no phase body copied; references anchored at canonical file |
| Missing canonical procedure after generation | Controlled source failure on check/regeneration; wrapper directs stopping instead of fallback |
| Skill/instructions/registry/graph/template/validator redirects into generated content | Declared/resolved-path rejection before dependency reads, even through parent symlinks or valid target content |
| Facade receives a pre-parsed registry whose source path redirects to generated content | Source guard rejects before using that registry or reading dependencies; no output mutation |
| Direct generated dependency or a dependency on an unselected harness output | Rejected independently of selection and file existence |
| Existing unowned `AGENTS.md` or expected skill | Generation fails and preserves all files, even if bytes match |
| Forged v2 entries claim root `AGENTS.md`, canonical phase skill, or generic pipeline skill | Generate/check reject the manifest using v2 rules; no overwrite or stale deletion, including with matching hashes |
| Forged v2 entry tested both as a desired new output and as stale | Neither replacement nor cleanup is authorized; preserve all file/manifest bytes |
| Missing/malformed/unsupported generator metadata or wrong version-specific target | Controlled rejection before writes; valid historical fixtures still migrate |
| Unrelated skill beside generated skills | Preserved; no false source dependency or ownership claim |
| Removed registration/skill | Only unchanged stale manifest-owned outputs are removed |
| Modified stale file, malicious manifest, unsafe output/source parent | Controlled error; no unrelated writes/deletes |

Run focused adapter suites, the full suite, existing checkout adapter check, and
`git diff --check` in the dedicated environment. The new generator contract must
also pass generate/check round trips inside the isolated fixtures.

## Exit criteria

- [ ] All required cases pass without hand-authored harness prerequisites.
- [ ] Capture → pure render → ownership remains the dependency direction.
- [ ] Templates, manifest inputs, shared requirements, and schema-2 attribution
  agree, with all targets enabled and each output owned once.
- [ ] Version-specific ownership validation precedes migration, and no canonical
  dependency can resolve through a generated path.
- [ ] Thin phase wrappers preserve canonical identity and relative-reference
  context; source deduplication does not suppress required outputs.
- [ ] Existing public generation remains usable until Stage 20 cutover.
- [ ] No framework, target-selection feature, unrelated CLI command, or workflow
  policy has been added to achieve the change.
