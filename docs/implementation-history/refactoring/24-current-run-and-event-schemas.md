# 24. Version run approvals and audit events

**Planned after Stage 23.** In the earlier awaiting-approval fixture, the saved
record has no `kind`. The current loader accepts it and the decision path returns
`approval-state-changed`. A replay of the earlier recoverable fixture also showed
that CLI `resume` appended a recovery event before rejecting its graph.

## Work

1. Set the run and event versions independently to 2 in
   [run_records.py](../../../src/specromancy_engine/_runs/run_records.py).
   Update the [published schemas](../../../src/specromancy_engine/schemas/),
   [validators](../../../src/specromancy_engine/_runs/run_validation.py),
   and writers. Describe required common approval identity, phase/visit/run
   binding, request and decision states, actor, and timestamps. Define the
   action and transition variants. Actions require nonblank details.
   Transitions bind an artifact digest and outcome. Use the same field rules
   in validation, typing, and decision consumers.
2. Reconcile the [nested validation matrix](14-persisted-data-diagnostics.md#nested-validation-decision-matrix)
   against actual producers and the documented low-level store API. Reject
   boolean version/counter values, empty identifiers and references, invalid
   mutation policies, and malformed outcome/target types. Specify integer
   token handling and test it, including the distinction between JSON Schema's
   numeric equality and Python's boolean/integer equality. Record which fields
   intentionally hold arbitrary finite JSON. Preserve valid low-level operations,
   paused successors, interrupted grants, and custom metadata.
3. Define the payload alternatives for the engine's approval request, grant,
   decline, and invalidation events in the event schema and validator. Check
   positive request numbers for action events and transition-specific fields
   for transition events. Keep the documented custom event facility usable.
   Validate and serialize the candidate event before replacing the manifest in
   [commit_locked](../../../src/specromancy_engine/_runs/run_persistence.py).
   An invalid candidate must fail before publication. Preserve exactly-once
   recovery for an actual interruption between replacement and append.
4. Check schema identity on all persisted reads, including `read_events` and
   `load(recover=False)`. Reject an obsolete manifest or any obsolete event
   before reconciliation, recovery append or mutation. In
   [CLI pipeline selection](../../../src/specromancy_engine/_cli/pipeline_selection.py),
   read validated saved provenance without recovery, validate the selected
   graph, then use the normal locked load with recovery. A read-only provenance
   lookup must permit a valid one-event gap. Simply switching selection to
   `load(recover=False)` would prevent healthy interrupted runs from resuming.
5. Update the configuration/state and recovery contract, approval fixtures,
   snapshots, canonical manifest/event hashes, and direct API tests together.
   Give an unsupported-format diagnostic with the observed and expected
   versions and the option to use the engine that produced the run. Keep
   malformed current records distinguishable from obsolete versions.

## Acceptance

| Exercise | Required observation |
| --- | --- |
| Restore a real old approval and a recoverable old run in disposable directories | Store and CLI refuse the obsolete format. Manifest, event and artifact bytes match the pre-call snapshot. |
| Current manifest with an old event, a mixed-version log, or a well-formed future version | Reject before any append, including when the log is one revision behind. |
| Current run with a recoverable gap and an unsupported saved graph | CLI reports the graph error without appending. With its supported graph restored, recovery appends once. |
| Current-version malformed approval, boolean counter, or invalid event submitted through a writer | Controlled diagnostic, original bytes and revision preserved. |
| Action grant/decline, transition grant, stale invalidation, retries, overlaps, custom event, and valid interrupted commit | Verify bindings, idempotency, audit payload, hashes and exactly-once recovery from disk. |

Run the record, persistence and store unit tests and the action approval, CLI,
interruption, recovery and orchestration contract tests. Include the new
versioned inputs in installed-wheel verification in Stage 28.
