# 01. Support action approval within a visit

A user should be able to approve adding a dependency before the application or its tests exist. Granting that permission should return the agent to implementation. Today, requesting approval runs completion checks, and granting it attempts the phase transition. [Approval service](../../../src/specromancy_engine/_engine/approval_service.py)

## Behavior

Add one optional phase setting, `approval_mode = "action"`. Set it on the shipped `implement` phase for its existing approval reasons. The default, `"transition"`, preserves the artifact approval used by `plan`. [Implementation workflow](../../../workflow/pipelines/implementation.toml)

| Action-mode command | Result |
| --- | --- |
| `request-approval` | Require a declared reason and nonblank action details. Reject an explicit `--outcome`. Record the request and enter `awaiting-approval` (7). The visit output can be absent. |
| `approve RUN_ID PHASE --request N` | Grant that action and restore the same visit to `active` in one commit. Return its action packet (8). Request and grant both skip output validation and phase commands. |
| `decline RUN_ID PHASE --request N` | Record the user’s refusal and restore the same visit to `active` in one commit (8). The agent can continue within the approved scope or submit corrected details as a new request. The original decision remains visible after restart. |
| `validate` | Once the work is ready, check the output, run the configured commands, and enforce the original mutation policy. A failed check leaves the visit active. Success takes the configured transition. |

A visit has at most one pending request. An exact retry returns that record (7). A different request or a decision targeting another record returns a conflict (5). Neither retry writes an event. On an active visit, repeating a granted or declined request or its decision returns the recorded result without an event. An opposite decision on the same record conflicts.

## Implementation

1. Extend the phase parser, model and schema. Serialize only the nondefault mode into the canonical graph so existing graph hashes remain valid. Treat approval records without a mode as transition approvals. Existing runs require their original graph and prepared workflow resources. Start a new run to use the revised workflow. [Canonical configuration](../../../src/specromancy_engine/_config/config_serialization.py)
2. Reuse the approval list and its locked decision path. Bind an action to the run, visit, phase, pipeline hash, reason and exact details. Omit the phase output hash and transition outcome from an action request. Look up the current visit’s pending request first. Preserve provenance, sealed-input and mutation-policy checks at request and grant, along with the original mutation baseline and completion evidence. Restrict transition recovery to transition approvals. [Approval decisions](../../../src/specromancy_engine/_engine/approvals.py)
3. Use the record’s one-based position in the append-only approval list as `N`. Display the details and exact decision commands in text and JSON. Resolve `N` and verify its binding under lock. Include `request_number: N` in every action-mode request, grant, decline and invalidation event, with full details in the approval record. If pipeline drift invalidates a pending action request, mark it stale and return the visit to active in the same commit. After the original graph is restored, the agent can request fresh consent. [Run store](../../../src/specromancy_engine/run_store.py)
4. Run validation commands outside the lock. Before writing either a successful transition (`transition_visit`) or failed evidence (`record_validation_attempt`), check the observed revision, current visit and active state under lock for action mode. Discard an overtaken result without changing the manifest or audit log, even if a grant has already restored the visit to active. Apply the same precondition inside the `block` mutation. The locked request path must also reject a visit that was blocked or advanced first. [Validation writes](../../../src/specromancy_engine/run_store.py) · [Block](../../../src/specromancy_engine/engine.py)
5. After a grant or decline, point `status.next_command` to `phase RUN_ID PHASE`. Include the visit’s action decisions and details in its action packet. Update the implementation procedure to honor those decisions and validate after doing the work. Document the CLI and persistence contracts, then regenerate adapters. [Status](../../../src/specromancy_engine/status.py) · [Action packet](../../../src/specromancy_engine/actions.py) · [Procedure](../../../workflow/skills/implement/SKILL.md)

## Acceptance

- In a test-owned CLI fixture, start with no output and a required command that records invocations and exits 5. Request and grant permission to add `cellular-automata`. Verify zero invocations, one request event, one grant event, and the same visit. Restart, follow the next command, and recover the exact grant.
- Write a valid output and validate. Verify the command now runs, its failure is recorded (CLI exit 6), and the visit stays active. Make the check pass and verify exactly one transition.
- Grant A, then request B with the same reason and different details. Retry B, request A again, and replay A’s grant. B stays pending. Decline B, restart, submit corrected details and grant the new request. Check each event’s request number against the approval record. Separately, invalidate a pending request through pipeline drift, restore the original graph, and request the same action again. Expect a fresh request number.
- Exercise both commit orders for `block` versus request and for passing or failing validation versus request. Assert the manifest and event log reflect commit order. A block or transition that wins prevents a request on the old active state. A failed validation that wins leaves the visit eligible for a request. A request that wins prevents an earlier block or validation attempt from committing, even after a grant restores the same visit to active.
- Verify that sealed-input drift and read-only violations prevent permission, and that legacy transition approvals retain their hash, grant and recovery behavior.
- In a dedicated environment, install with `python -m pip install -e .`. Run focused approval and recovery tests, `python -m unittest discover`, and `specromancy adapters generate --check`.
