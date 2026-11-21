# 26. Require workflow-owned sources in pipeline schema 3

**Planned after Stage 25.** Schema 2 rejects the former approval list but
still lets runtime phases find procedures in generated `.agents/skills`.
Omitting `skill_source` also changes the containment boundary for templates
and validators. Nonempty adapter generation already requires an explicit source.

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

- [ ] Graph versions 1, 2 and a future version fail through `init`, existing-run
  graph selection and graph loading for a selected adapter. Verify the CLI
  error without creating a run or changing an existing run/event pair.
- [ ] A version-3 graph missing `skill_source` fails even if a matching
  discovery wrapper exists. A valid graph runs in a consumer containing only
  authored inputs. Action packets name and hash the canonical file.
- [ ] A procedure, template or validator redirected outside `workflow/`
  is rejected on the applicable load and prepared-visit paths. Registry-wide
  adapter validation still catches conflicting bindings. An unrelated invalid
  graph does not prevent runtime loading of a valid selection.
- [ ] Registry and harness-selection version 1 keep passing their independent
  positive and unsupported-version tests. The updated example, current
  lifecycle snapshots and generated wrappers all use the new graph contract.

Run config and registry unit tests, replacement/multi-pipeline and provenance
contracts, shipped-configuration discovery, and consumer example tests.
