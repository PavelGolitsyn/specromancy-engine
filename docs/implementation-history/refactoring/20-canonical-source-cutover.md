# Stage 20 — Migrate canonical sources and switch generation

Status: **planned; not implemented**. Depends on Stages 16–19.
Category: coordinated behavior change and repository migration.

## Objective

Switch the public generator and this repository's workflow together. At the end,
all active authoring instructions point to `workflow/`; every supported harness
surface, including root `AGENTS.md`, is reproducible and manifest-owned.

## Migration sequence

1. Inventory the working tree, existing generated ownership, local modifications,
   and active-run constraints. Preserve unrelated user work. Retain unfinished
   old runs with their original checkout/source bytes as described in Stage 18;
   do not move their artifacts or rewrite their provenance.
2. Move repository policy from root `AGENTS.md` into
   `workflow/instructions.md`. Replace the old canonical-location rule with the
   new source/output ownership rule while preserving Python support, environment
   setup, tests, genericity, state safety, and CLI ownership constraints.
3. Move hand-authored phase procedures into `workflow/skills/<id>/SKILL.md`;
   update their actual relative references and the pipeline's `skill_source`
   declarations. The generic pipeline procedure now comes from the release
   template. Do not keep a separately editable copy under `workflow/` or `.agents`.
   Verify every canonical frontmatter name matches `skill`, and that repeated
   registrations agree on its source. Audit all captured inputs, including
   registry/graphs, artifact templates, and validators, against Stage 16's
   declared/resolved workflow boundary. Relocate out-of-bound example/fixture
   dependencies explicitly; do not use symlinks to retain generated prerequisites.
4. Migrate `examples/release-documentation/` to the same authoring layout and
   update its walkthrough. Prefer a source-only example: include instructions,
   workflows, and phase skills, then let consumers generate harness outputs.
   Update `MANIFEST.in` and `tools/verify_distribution.py` accordingly.
5. Switch `generate_adapters`/`render_adapters` to the new capture and renderer;
   set generator version 3 and adapter manifest schema 2, using Stage 19's shared
   requirement sets and consumer attribution. Delete superseded inline templates
   and source discovery code. Retain only the documented runtime legacy resolver,
   not a legacy adapter fallback or a permanent old-generation flag.
   In `cli.py`, route adapter commands through the guarded registry loader before
   the initial registry read. Runtime commands retain the existing loader and
   lazy selected-graph validation. A check inside adapter capture alone is too
   late for CLI bootstrap; use the shared guard at both entry points.
6. In this reviewed repository migration, relocate the former **unowned**
   canonical root instruction and skill files before invoking generation. This
   is an explicit source edit by the implementer, not deletion/adoption performed
   by the engine CLI. Never use `--force`, broad directory removal, reset, or
   fabricated manifest ownership to make generation pass.
   Validate any previous manifest under its own schema/generator-version path
   and target rules before migration. Invalid v2 claims to newly generated root
   instructions or phase skills must fail, even when their hashes match.
7. Generate with `specromancy adapters generate`, inspect the complete generated
   diff and manifest, then run check mode. Root `AGENTS.md` and former canonical
   `.agents` skill paths must now carry provenance headers and appear exactly
   once in the manifest. Keep foreign files in harness directories untouched.
   Inspect phase outputs as thin discovery wrappers: metadata, provenance, and
   canonical load instructions only. Generic launch orchestration remains
   embedded. Confirm source-read deduplication has not omitted any harness's
   wrapper or changed the canonical skill identity.
8. Convert ordinary fixtures/builders and shipped-configuration tests to workflow
   sources. Preserve explicitly labeled legacy compatibility fixtures/captures;
   old generated captures remain historical evidence, while new expected output
   captures identify generator version 3 and its intentional contract changes.

## Concrete file groups

- `workflow/instructions.md`, `workflow/skills/*/SKILL.md`,
  `workflow/pipelines/implementation.toml`, `workflow/README.md`.
- Root `AGENTS.md`, `.agents/skills/*/SKILL.md`, `.claude/`, supported `.github/`
  prompt/instruction files, `.opencode/commands/`, and `adapters/manifest.json`.
  Only the generator writes the new harness content.
- `examples/release-documentation/`, package inclusion lists, distribution tools.
- `src/specromancy_engine/cli.py`, `registry.py`, and focused CLI/registry tests
  for guarded adapter bootstrap and preserved runtime graph isolation.
- `tests/engine/support.py`, contract/unit supports and ordinary fixtures;
  `tests/engine/unit/test_skills.py`, architecture/adapter/replacement/default
  pipeline contracts; `tests/shipped_configuration/`; packaging consumer,
  release-documentation, source-export and README tests.
- `README.md`, `workflow/README.md`, `docs/guides/installation.md`,
  `authoring-pipelines.md`, `harnesses.md`, `distribution-verification.md`,
  `docs/reference/architecture.md`, `contracts.md`, `cli.md`,
  `harness-compatibility.md`, and `tests/README.md` where affected.

## Documentation contract

Explain that installation supplies templates but creates no repository files.
Users supply `workflow/instructions.md`, registered graphs with `skill_source`,
canonical phase procedures, and declared artifacts/validators. They then run the
existing generator. Edits go to workflow files; regeneration updates all harness
surfaces. A root `AGENTS.md` is an output, never a prerequisite.

Document the declared/resolved workflow source boundary, including indirect
dependencies and symlink restrictions. Explain `frontmatter.name == skill` and
per-identifier source uniqueness. Phase wrappers load the canonical procedure;
supporting references are relative to that source file. A procedure-body edit
may change only manifest provenance, while a metadata/path edit can also change
wrapper bytes. This does not remove the regeneration/check requirement.
Describe source-path validation for direct adapter facade callers, schema-2 shared
attribution, and adapter-wide identity checks separately from runtime validation
of the selected graph.

For existing consumers, document preservation/relocation of hand-written files
and active runs, predictable unowned-file conflicts, and the changed source
hashes. No instruction may tell users to hand-edit generated skills or manually
copy a generic orchestrator into `.agents`. Describe legacy graphs as runtime
compatibility, not the current authoring model. Historical plans remain historical;
do not mass-rewrite their old evidence or claims into current behavior.

Document shared discovery versus ownership accurately for Codex and Hermes.
Retain existing harness scope and invocation assumptions; do not claim live-host
compatibility was verified merely because Markdown and CLI tests pass. Refresh
external harness requirements only if implementation actually changes them.

## Verification and exit criteria

After reinstalling the edited checkout in the dedicated environment:

```sh
python -m unittest tests.engine.unit.test_adapters tests.engine.unit.test_multi_pipeline_adapters tests.engine.unit.test_cli tests.engine.unit.test_registry tests.engine.contract.test_multi_pipeline tests.engine.contract.test_adapter_drift tests.engine.contract.test_architecture
python -m unittest discover -s tests/shipped_configuration -t .
python -m unittest discover -s tests/packaging -t .
python -m unittest discover
specromancy adapters generate --check
python bin/specromancy adapters generate --check
git diff --check
```

Inspect scoped references with `rg` across active docs, source, tests, workflow,
and generated files. Categorize `.agents`/`AGENTS.md` mentions as generated-output
documentation, explicit legacy coverage, or a defect; a blanket zero-match rule
would incorrectly ban legitimate outputs and preserved history.

Through the public CLI, exercise both generate and check with a registry symlink
to generated content, using valid and malformed TOML targets. Require the source
boundary diagnostic before parsing either target and no filesystem mutation.
Repeat runtime validation/init/resume of valid pipeline A while registered B has
invalid graph content, missing skill content, or a conflicting binding; generation
must reject the invalid registry-wide inputs while A remains independently usable.

- [ ] No active canonical skills/prompts/instructions remain in harness locations.
- [ ] No public adapter path reads root `AGENTS.md` or `.agents` as sources.
- [ ] Source aliases/dependencies cannot bypass that separation, old manifests
  retain their original ownership limits, and phase wrappers preserve identity.
- [ ] Generated files contain no unique workflow policy and are reproducible.
- [ ] Example setup needs only release resources and authored workflow sources.
- [ ] Full tests pass, including old-run compatibility and new generator cases.
- [ ] Only intended source migration, generated changes, tests, and docs changed.

Rollback is a reviewed source/release change using preserved originals. Do not
rewrite run history, blindly downgrade a generated manifest, or delete foreign
files. Keep the code switch and source migration in one reviewable integration
stage so intermediate released revisions never require both source layouts.
