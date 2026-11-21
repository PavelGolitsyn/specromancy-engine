# 01. Support action approval within a visit

A user should be able to approve adding a dependency before the application or its tests exist, then approve a completed artifact later in the same visit. Today, requesting approval runs completion checks, and granting it attempts the phase transition. [Approval service](../../../src/specromancy_engine/_engine/approval_service.py)

## Phase configuration

Replace the phase’s single `approval_conditions` list with two required lists of reason codes. Either or both may be empty. This phase accepts one reason of each kind.

```toml
transition_approval_conditions = ["material-scope-change"]
action_approval_conditions = ["new-production-dependency"]
```

The reason determines what the user is approving. Reject a reason declared in both lists of the same phase. Keep the existing CLI shorthand that allows `--reason` to be omitted when the phase declares exactly one reason in total. With two empty lists, the phase accepts no approval requests.

In the shipped workflow, move the existing `plan` reason to `transition_approval_conditions` and the existing `implement` reasons to `action_approval_conditions`. Set every remaining list to `[]`. [Implementation workflow](../../../workflow/pipelines/implementation.toml)

## Behavior

| Command | Result |
| --- | --- |
| `request-approval` with an action reason | Require nonblank action details and reject an explicit `--outcome`. Record the request and enter `awaiting-approval` (7). The output can be absent. |
| `approve RUN_ID PHASE --request N` for an action | Grant the specified action and restore the same visit to `active` in one commit. Return its action packet (8). Both request and grant skip output validation and phase commands. |
| `decline RUN_ID PHASE --request N` for an action | Record the refusal and restore the same visit to `active` in one commit (8). The agent can continue within scope or submit corrected details as a new request. |
| `request-approval` with a transition reason | Use the existing outcome selection and completion checks. Bind the request to the validated output hash and outcome. Granting it rechecks the artifact and follows the selected transition. |
| `validate` | Check the output, run configured commands, and enforce the original mutation policy. A failed check leaves the visit active. Success follows the configured transition. |

A visit has at most one pending request across both lists. An exact retry returns that record (7). A different request or a decision targeting another record conflicts (5). Neither retry writes an event. On an active visit, repeating a decided action request or its decision returns the recorded result without an event. An opposite decision on the same record conflicts.

## Implementation

1. Version the pipeline schema. Require both lists in the new parser and schema, expose them in the phase model and action packet, and include both in the canonical graph even when empty. Reject previous pipeline schema versions and the superseded `approval_conditions` field. Start a new run for a migrated graph. [Canonical configuration](../../../src/specromancy_engine/_config/config_serialization.py)
2. Reuse the append-only approval list and its locked decision path. Record the approval kind on each request and require it when applying a decision. Look up the visit’s pending request before replaying a decision. Bind an action to the run, visit, phase, pipeline hash, reason and exact details. Only transition records bind an output hash and outcome or qualify for transition recovery. Preserve provenance, sealed-input and mutation-policy checks at action request and grant, along with the visit’s original mutation baseline and completion evidence. [Approval decisions](../../../src/specromancy_engine/_engine/approvals.py)
3. Use the record’s one-based position as `N`. Display the details and exact decision commands in text and JSON. Resolve `N` and verify its binding under lock. Include `request_number: N` in each action request, grant, decline and invalidation event. If pipeline drift invalidates a pending action, mark it stale and restore the visit to active in one commit. Restoring the original graph allows a fresh request. [Run store](../../../src/specromancy_engine/run_store.py)
4. Run validation commands outside the lock. Before committing a validation result, transition approval request or block observed on an active visit, verify its revision, visit and active state under lock. Discard an overtaken result even if an intervening action decision has restored the visit to active. The locked action request must likewise reject a visit that was blocked or advanced first. [Validation writes](../../../src/specromancy_engine/run_store.py) · [Block](../../../src/specromancy_engine/engine.py)
5. After an action decision, point `status.next_command` to `phase RUN_ID PHASE`. Include the visit’s action decisions and details in its action packet. Update the implementation procedure to honor those decisions and validate after doing the work. Document the configuration, CLI and persistence contracts, then regenerate adapters. [Status](../../../src/specromancy_engine/status.py) · [Action packet](../../../src/specromancy_engine/actions.py) · [Procedure](../../../workflow/skills/implement/SKILL.md)

## Acceptance

- Load phases with either list empty, both empty and both populated. Reject each missing list and overlapping reasons. Verify an undeclared reason fails and the single-reason shorthand works across the two lists.
- In a CLI fixture using the example above, start with no output and a required command that records invocations and exits 5. Request and grant permission to add a dependency. Verify zero invocations, one request event, one grant event and the same active visit. Restart and recover the exact grant from the action packet.
- In that visit, write a valid output and validate. Verify the command runs, its failure is recorded (CLI exit 6), and the visit stays active. Make the check pass and request transition approval for `material-scope-change`. Verify the request binds the output hash and outcome, waits for a separate grant and then advances exactly once.
- Grant action A, then request B with the same reason and different details. Retry B, request A again, replay A’s grant and try a transition request. B stays pending. Decline B, restart, submit corrected details and grant the new request. Check event request numbers against their records. Invalidate a pending action through pipeline drift, restore the original graph, and verify a fresh request number for the same action.
- Exercise both commit orders for an action request racing a block, a passing or failing validation, or a transition approval request. Verify the manifest and event log reflect commit order. A failed validation that commits first leaves the visit eligible for a request. An action request that commits first invalidates earlier observations even after its grant restores the visit to active.
- Verify sealed-input drift and read-only violations prevent action permission. Verify a previous-schema graph is rejected on initialization and resume. Exercise transition approval, artifact invalidation and recovery on a current-schema run.
- In a dedicated environment, install with `python -m pip install -e .`. Run focused approval and recovery tests, `python -m unittest discover`, and `specromancy adapters generate --check`.
