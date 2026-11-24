# Engine contract records

The lifecycle records use the current pipeline schema and a test-owned graph in
`source/`. They cover configuration identity, CLI responses and recovery.
The all-target adapter inputs come from `AdapterFixture` in the adapter unit tests.

| Record | Contract |
| --- | --- |
| `canonical.json` | Exact canonical strings and SHA-256 for omitted pause, explicit false, and true; non-ASCII criteria and omitted optional defaults |
| `responses.json` | Complete version-2 action, approval, status and adapter envelopes, including both pending request kinds and ordered action decisions after restart |
| `diagnostics.json` | Exact configuration locations, remediation, error values, CLI exit codes and stdout/stderr routing; outcome-before-output and artifact-before-pipeline mismatch ordering |
| `states.json` | Schema-2 state name → relative run filename → exact UTF-8 contents, including complete `run.json`, `events.jsonl`, request and output artifacts |
| `ownership.json` | Current all-target outputs, exact UTF-8 and SHA-256 including the schema-3 ownership manifest |

`states.json` includes pending, active, awaiting approval, approved before
advancement, paused, completed, a recoverable manifest/event gap, and its
recovered counterpart. The examples were produced through `Engine` and
`RunStore` APIs in temporary repositories. The approved example stops at the
`after-event-append` fault hook during approval; the recoverable example stops
at `after-manifest-replace` during activation. No history was fabricated by
editing manifests or events. Replay copies these original bytes into a fresh
temporary run directory and loads them through the current API.

The store clock and random source are injected. Engine approval/block timestamps
use its existing `utc_now` reference, patched to the same fixed instant because
the engine currently has no injectable clock. Fixture file modes are explicitly
0644, so content/mode snapshots remain meaningful on different umasks.
Only absolute temporary roots and the current Python executable are replaced
with `<ROOT>` / `<PYTHON>` in response and diagnostic records. Persisted bytes,
hashes, timestamps, revisions, event types, outcomes and list order are never
normalized. No command durations occur in these snapshots; command behavior
remains covered by the existing safety tests and the added mutation-order test.

Run the comparison and replay gate with:

```sh
python3 -m unittest tests.engine.contract.test_current_contract
```

Tests never rewrite these records. `capture_canonical`, `capture_lifecycle`, and
`capture_diagnostics` in `tests.engine.contract.current_contract_support` expose
the capture scenarios for inspection. A deliberate contract change must review
both the scenario and the expected record; do not refresh records merely to make
an extraction pass. Adapter generation must also stay in `AdapterFixture`'s
temporary repository.

The ownership comparison fixes the package-version input at 0.1.4. The installed
gate separately exercises the actual candidate version. See the [refusal
specimens](../refused-contracts/README.md) for earlier formats.
