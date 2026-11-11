# Stage 18 — Resolve canonical procedures from workflow files

Status: **planned; not implemented**. Depends on Stages 16–17.
Category: additive configuration and runtime resource support.

## Objective

Allow configuration validation, initialization, phase actions, validation, and
resume to work using canonical workflow files before adapters are generated.
Generated discovery files must never become runtime resource identities for new
workflows.

## Configuration contract

```toml
[[phases]]
id = "compose"
skill = "compose"
skill_source = "workflow/skills/compose/SKILL.md"
# Existing inputs, outputs, validator, mutation policy, and transitions follow.
```

`skill_source` is an additive optional phase field in pipeline schema 1. It is a
repository-relative POSIX path to a regular canonical file under `workflow/`.
Extend existing path normalization with the declared-and-resolved workflow
boundary from [Stage 16](16-generated-harness-contract.md#canonical-source-path-boundary);
the current repository-only containment check is insufficient. Reject absolute
paths, traversal, invalid types, missing files, and symlink escapes, including
escapes that remain inside the repository. Reject a symlinked `workflow/` root;
resolve descendant symlinks only within the actual workflow directory. Do not
derive the skill source base from the graph directory or process working
directory. Keep `skill` as the identifier; no arbitrary path is accepted in it.

For phases declaring `skill_source`, validate portable canonical frontmatter and
require `name == skill`. Reuse the same restricted metadata reader for adapter
capture; do not add a general YAML dependency. Runtime loading validates metadata
and identifier/source bindings within the selected graph only. Adapter generation
enforces the same bindings across all registered pipelines: one identifier maps
to one normalized declared source path/resolved file, and two identifiers cannot
alias one file. Repeated uses of the same identifier/source pair are allowed.
Validate identity before deduplicating reads, and never rewrite metadata to hide
a mismatch. Do not load unrelated graphs to validate, initialize, or continue a
selected pipeline; preserve the existing runtime isolation contract.

When the field is present, include its normalized declared value in the canonical
phase document and resolve `PhaseConfig.skill_path` to it. When absent, omit the
new key from canonical serialization and retain the exact legacy runtime
resolution and hashes. This narrow compatibility branch exists to read and run
old graphs; new documentation, fixtures, and adapter generation use explicit
workflow sources. Never choose a source based on whether `.agents` happens to
exist, and never fall back when a declared workflow source is missing.

Adapter generation will reject legacy graph registrations with an actionable
`skill_source` migration diagnostic before attempting legacy skill reads. This
precheck must use shared configuration validation or a small shared declaration
reader, not a second general TOML parser. Supporting old runtime graphs does not
make `.agents` a source for the new adapter generator.

Apply the workflow source boundary to every input captured by that generation
path, not just skills: validate registry/graph paths before parsing, then validate
artifact-template and validator paths before their bytes are loaded. For new
runtime phases with `skill_source`, enforce the same boundary on their declared
skill, template, and validator resources before a run mutation. Retain existing
graph-relative bases for template/validator declarations; constrain their final
locations. Do not globally tighten the legacy runtime branch or refresh old
compatibility captures to accommodate these new rules.

Prepare an adapter-specific guarded entry point in `registry.py` using the
shared source-path guard before opening/parsing the registry. Retain declared
registration paths long enough to validate both declared and resolved locations
before graph reads. The existing CLI calls `load_registry` before adapter dispatch;
Stage 20 must select this guarded entry point before that read. Runtime commands
keep the existing registry loader and lazy selected-graph behavior. Stage 19's
new capture path applies the same source guard to an already-loaded registry's
root/path and registration locations before consuming it or reading dependencies.
Reuse the guarded CLI registry snapshot without rereading it; a direct caller's
earlier reads are outside the facade's guarantee. Do not trust a pre-parsed object
as proof of safe source paths or add a second TOML parser.

## Implementation and intended files

1. Extend `config_models.py`, `config_phase_parser.py`, and
   `config_serialization.py` within `src/specromancy_engine/_config/`. Preserve
   facade imports and existing construction compatibility where tested. Store the
   declared source separately from the resolved `Path`.
2. Update `schemas/pipeline.schema.json` and documented schema/public contracts.
   Verify the schema and actual parser agree about accepted fields and paths.
   Add the small shared source-path guard alongside existing field/path helpers;
   use it from registry/graph capture and dependency reads as well as skill
   resolution. Keep generic legacy path helpers available for legacy runtime use.
   Prepare the guarded adapter registry entry point in `registry.py`; include
   `cli.py` bootstrap wiring in Stage 20's public cutover rather than changing
   legacy CLI behavior during this preparatory stage.
3. Trace `visit_preparation.collect_resources`, `actions.py`, and
   `_engine/provenance.py`. They should already consume resolved paths and sealed
   records; change them only if evidence shows a hardcoded location. Do not rename
   the public `action.skill` field or add generated resources to a visit record.
4. Add workflow-only test fixture builders to `tests/engine/support.py` and
   relevant unit/contract supports, leaving frozen legacy captures intact.
5. Add tests in `tests/engine/unit/test_config.py`, `test_registry.py`, and
   `test_run_store.py`; `tests/engine/contract/test_compatibility.py` and
   `test_multi_pipeline.py`; and `tests/packaging/test_consumer_roots.py`. Adapt
   only the fixtures needed by these new cases; broad shipped-workflow migration
   belongs to Stage 20.

## Provenance and old-run policy

- Unchanged legacy graphs retain their canonical bytes, hashes, resource paths,
  action envelope, and continuation behavior while their original files remain.
- Adding `skill_source` deliberately changes pipeline identity. Do not silently
  resume an old run against the new graph, rewrite `run.json`/`events.jsonl`, move
  immutable artifacts, or accept a generated wrapper as the original resource.
- To preserve unfinished old runs during migration, keep their original graph
  and original source bytes available at the saved paths in a retained checkout.
  Finish them before regenerating overlapping canonical `.agents` paths, or use
  a separately retained checkout and a new graph/path for new runs. Replacing a
  canonical skill with a generated wrapper changes its recorded bytes and meaning.
- Canonical procedure edits must remain visible to prepared-visit provenance
  checks. Existing output-edit approval invalidation and state/event transitions
  remain unchanged. Editing or regenerating a discovery wrapper must not change
  the canonical skill hash of a new run.

## Verification

```sh
python -m unittest tests.engine.unit.test_config tests.engine.unit.test_registry tests.engine.unit.test_run_store tests.engine.contract.test_compatibility tests.engine.contract.test_multi_pipeline tests.packaging.test_consumer_roots
python -m unittest discover
specromancy adapters generate --check
git diff --check
```

Use the dedicated editable environment. Test a repository with only `workflow/`
inputs and required application files: no root `AGENTS.md`, `.agents`, `.claude`,
`.github` prompts, `.opencode`, or adapter manifest. Validate/init/start a visit,
inspect its canonical action path, complete/resume it, and exercise a changed
canonical procedure. Test legacy hashes against existing captures, not newly
recorded expectations. Include a missing declared source even when a same-named
generated skill exists, to prove there is no fallback.

Add explicit source/identity cases, asserting controlled failure before mutation:

| Case | Expected result |
| --- | --- |
| Workflow skill/instructions symlink to `.agents` or root `AGENTS.md` | Rejected despite repository containment |
| Parent-directory symlink or symlinked `workflow/` redirects sources into a harness directory | Rejected; resolving the boundary itself must not authorize the escape |
| Artifact template or validator directly references a generated path, or links to one | Rejected before dependency reads, even if the file is valid Markdown/JSON |
| Registry/graph path links to generated content | Guarded adapter loader rejects before parsing, including malformed target content; legacy runtime rules remain separate |
| Source points to an unselected harness output | Same rejection as for a selected harness |
| Safe graph-relative template and descendant symlink staying within workflow | Accepted under the documented path rules |
| `skill = "compose"` but frontmatter `name: review` | Identity diagnostic; no silent renaming |
| Two identifiers alias one source; one identifier names distinct sources | Rejected within the selected graph at runtime and across registered graphs during generation |
| Pipeline A is valid; unrelated registered B has invalid TOML, missing skill content, or a conflicting skill binding | A still validates, initializes, and resumes; registry-wide generation rejects B or the conflict |
| Several phases reuse the same identifier/source | Accepted; each needed harness output remains planned |

Exercise adapter-only cases through the shared capture path in Stage 19 as it
becomes available. Keep old unmodified graph/hash/runtime cases passing separately.

## Exit criteria

- [ ] New workflows execute without generation or harness directories.
- [ ] Old unmodified graphs retain compatibility and new source declarations
  deliberately change identity.
- [ ] Unsafe/missing sources fail before any run mutation.
- [ ] Adapter registry reads are guarded before parsing; ordinary runtime loading
  remains lazy and independent of unrelated graph content.
- [ ] New resource sources cannot resolve into generated locations, and canonical
  metadata matches declared skill identity without affecting legacy acceptance.
- [ ] Prepared provenance, read-only enforcement, approvals, and immutable
  artifacts retain their existing contracts.
- [ ] Focused/full tests and the still-current checkout adapter check pass.
