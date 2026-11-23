# 24. Version run approvals and audit events

**Implemented on 2026-11-22 from `1d4fb1c`.** Before this change, the loader
accepted a version-1 approval without `kind` and the decision path returned
`approval-state-changed`. CLI `resume` also appended a recovery event before
rejecting an unsupported saved graph.

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

## Execution record

The run and event writers emit independent version-2 tags. A reserved approval
event carries an explicit `kind` so that an action with a missing request number
cannot be interpreted as a transition invalidation. The store prepares the
complete UTF-8 event before manifest replacement. A crash after replacement
still leaves a single recoverable gap. CLI selection inspects that gap under
lock and the command reconciles it after loading the selected graph.

### Stage 14 matrix disposition

| Field or operation | Version-2 behavior |
| --- | --- |
| Approvals | Closed action and transition records share run, visit, phase, pipeline and reason bindings. The one-based array position identifies the request. Status determines decision, actor and decision time. Each visit permits one pending request. An interrupted transition grant can remain approved while the visit awaits advancement. |
| Numeric identity | Versions, revisions, counters, ordinals and action event request numbers require positive integer tokens. Booleans, fractions and exponent forms fail. A positive unsupported schema version identifies its surface and both version numbers. |
| Visits | Require nonblank identifiers and input references, a declared mutation policy, and text or null outcomes/targets. Preserve ordered visits and attempts, sealed outputs, and the low-level distinction between completing a visit and advancing the run. A paused successor may be pending. Timestamp checks validate the UTC calendar value without requiring clocks to advance between operations. |
| Open metadata | Git base/head, mutation baseline/result, terminal result and block reason accept finite JSON. Check, command and deviation arrays retain arbitrary finite JSON entries. The store preserves these values for inspection. Engine validation gathers fresh evidence. |
| Events | Request, grant, decline and invalidation payloads have kind-specific fields. Other event names accept finite JSON objects. The store validates every event on reload and checks sequence, revision and final manifest hash before deciding whether recovery is possible. |

The negative fixtures preserve the original file contents of the awaiting-approval
and recoverable runs in `v0.1.3:tests/engine/fixtures/refactoring-compatibility/states.json`.
All eight current snapshots were captured again through the deterministic
lifecycle. Restoration tests compare manifest, audit and artifact bytes before
and after refusal, and replay current snapshots through interruption and recovery.
The installed test bundle includes both fixture generations, the recovery tests
and the action approval contract tests for Stage 28.

Consumer upgrade steps and the reserved event payloads are documented in the
[public contract](../../reference/contracts.md#run-persistence).

### Verification

The checkout was installed in its dedicated environment with
`python -m pip install --no-build-isolation -e .`. The final source checks
used the activated environment on macOS arm64.

| Check | Result |
| --- | --- |
| Record, persistence, store and visit-transition unit tests plus action approval, CLI, interruption, recovery, orchestration and compatibility contract tests | 106 passed on Python 3.14.4. The same 106 passed against the installed wheel on Python 3.11.15. |
| `python -m unittest discover` | 389 passed on Python 3.14.4. |
| Draft 2020-12 schema check | Both published schemas passed metaschema validation. All eight lifecycle snapshots and their 34 event records validated, along with action decision variants. Checked boolean rejection and integral-float equality separately. |
| `python -m build --sdist --wheel --no-isolation` and `python tools/verify_distribution.py` | Both installs passed offline on Python 3.14.4, with 102 tests each for the direct wheel and the wheel rebuilt from the source archive. |
| `specromancy adapters generate --check` and `git diff --check` | Passed. |

The distribution check covers the Stage 24 fixtures on this host. The complete
release and platform matrix belongs to Stage 28.
