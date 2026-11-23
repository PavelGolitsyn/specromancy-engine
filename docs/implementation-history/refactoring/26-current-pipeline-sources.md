# 26. Require workflow-owned sources in pipeline schema 3

**Executed on 2026-11-23 against `31f2866`.** Graph schema 3 requires an
authored procedure under `workflow/` for each phase. The shared loader applies
the same resource boundary to runtime execution and selected adapter generation.

## Work

1. Make `skill_source` required in the
   [pipeline schema](../../../src/specromancy_engine/schemas/pipeline.schema.json),
   field parser, configuration model and canonical document. Set the supported
   graph version to 3. Eliminate runtime discovery fallback and conditional
   resource boundaries in [the configuration package](../../../src/specromancy_engine/_config/).
   Delete the registry's separate missing-source migration pass once the common
   loader enforces the rule. Retain the adapter registry pre-read path guard,
   cross-graph binding checks, selected-graph runtime isolation and empty
   adapter selection semantics.
2. Check the version before interpreting fields specific to a retired schema.
   Diagnostics should identify an obsolete graph and explain how to author a
   current graph, including both approval lists and an explicit procedure.
   For a current graph with a missing source, report the pipeline, phase and
   missing field. Apply the same declared/resolved workflow containment and
   prepared-provenance checks to every phase. Audit alternate graph field
   spellings against the Stage 23 inventory and retire compatibility-only
   spellings in this version change.
3. Convert the [shipped workflow](../../../workflow/), the
   [consumer example](../../../examples/release-documentation/), engine
   fixtures and graphs constructed inside tests. Move hand-authored fixture
   procedures out of discovery locations. Update portable skill frontmatter
   and the [packaged launch template](../../../src/specromancy_engine/resources/adapters/launch.md).
   Update authoring instructions, graph hashes, persisted provenance and
   action/adapter fixtures. Regenerate checkout adapters from authored sources.
4. Replace old-run continuation guidance with same-engine completion or a new
   run under the new graph. Explain the difference between graph schema,
   author-controlled graph revision and the canonical hash saved by a run.

## Acceptance

- [x] Graph versions 1, 2 and a future version fail through `init`, existing-run
  graph selection and graph loading for a selected adapter. Verify the CLI
  error without creating a run or changing an existing run/event pair.
- [x] A version-3 graph missing `skill_source` fails even if a matching
  discovery wrapper exists. A valid graph runs in a consumer containing only
  authored inputs. Action packets name and hash the canonical file.
- [x] A procedure, template or validator redirected outside `workflow/`
  is rejected on the applicable load and prepared-visit paths. Registry-wide
  adapter validation still catches conflicting bindings. An unrelated invalid
  graph does not prevent runtime loading of a valid selection.
- [x] Registry and harness-selection version 1 keep passing their independent
  positive and unsupported-version tests. The updated example, current
  lifecycle snapshots and generated wrappers all use the new graph contract.

Run config and registry unit tests, replacement/multi-pipeline and provenance
contracts, shipped-configuration discovery, and consumer example tests.

## Execution record

The schema, parser and canonical graph require `skill_source`. Procedures are
repository-relative. Templates and JSON validator paths are graph-relative.
Both their declared locations and resolved files must stay under `workflow/`.
A retained configuration rechecks all three resource types before continuation.
Prepared visits bind procedure and template paths and hash their raw bytes.

The loader now accepts `allowlist`, command tables with `argv`, and a validator
table with `type` and its options. Refusal tests cover each retired spelling
from the Stage 23 inventory. The shipped graph, release-documentation example
and test graphs use the current forms. The lifecycle captures include the new
canonical hash and workflow procedure paths. The generator-4 fixture captures
the resulting wrappers and ownership manifest.

CLI tests exercise graph versions 1, 2 and 4 through initialization, selected
generation and check, and resume with an interrupted manifest/event pair.
The resume test compares the saved bytes after each refusal and verifies
exactly one recovery event after restoring the current graph.

### Verification

| Check | Result |
| --- | --- |
| Configuration, registry, adapter, replacement and multi-pipeline contracts, provenance, recovery and consumer example checks | 162 passed with the dedicated Python 3.14.4 editable installation. |
| Shipped-configuration discovery | 19 passed, including execution of the shipped validation commands. |
| Full `python -m unittest discover` | 390 passed on Python 3.14.4. |
| Installed wheel on Python 3.11.15 | 130 focused tests passed in a fresh environment. |
| Checkout adapter generation | Regenerated 27 files. The installed CLI and checkout launcher both reported up to date in check mode. |
| `git diff --check` | Passed. |
