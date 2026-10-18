# Stage 02 — Persistence and locking

Status: planned. Depends on: 01. Risk: high; durable state and error ordering.

## Outcome

Allow native Windows initialization and state mutation while preserving manifest
replacement, event reconciliation, lock ownership, and immutable artifacts.
Avoid a persistence rewrite: the current ordered protocol is already tested.

## Intended files

- `src/specromancy_engine/artifacts.py`.
- `src/specromancy_engine/_runs/run_persistence.py`.
- A small internal `src/specromancy_engine/_filesystem.py` for shared filesystem
  primitives, if needed; no policy, phase names, or public API exports.
- `src/specromancy_engine/locking.py` only for demonstrated native defects.
- Inspect `_adapters/adapter_ownership.py`; its writer already closes its binary
  temporary file before replacement and has no directory-fsync call.
- `tests/engine/unit/test_run_persistence.py`, `test_run_store.py`,
  `test_visit_transition_store.py`; `tests/engine/contract/test_interruptions.py`,
  `test_recovery.py`, `test_engine_orchestration.py`.
- New focused filesystem/lock tests where existing files do not cover the seam.
- `docs/reference/contracts.md` and `docs/reference/architecture.md` for the
  precise durability guarantee, without claiming completed Windows support yet.

## Instructions

1. Introduce one narrow directory-sync operation used by artifacts and run
   persistence. On POSIX retain directory open, fsync, and close with failures
   propagated. On Windows select an explicit documented unsupported operation
   branch before attempting the POSIX directory open. Do not catch arbitrary
   `OSError` and report success on every platform.
2. Keep each writer's authorization, serialization, temporary-file placement,
   cleanup, and fault-injection ordering in its existing owner. Retain existing
   compatibility methods/seams where tests rely on them. Share the directory
   operation, not a generalized transaction or writer framework.
3. Maintain the exact write sequence: create a unique adjacent temporary file;
   write all bytes; flush and file-fsync; close the handle; replace with
   `os.replace`; perform the platform's directory-sync operation; then append and
   sync the audit event. Artifacts retain their existing no-overwrite checks.
4. Preserve JSON serialization and LF bytes. `run.json` already specifies
   `newline='\n'`, events are written as bytes, and artifacts preserve bytes.
   Add assertions around those boundaries rather than converting read data.
5. Exercise Windows replacement failures using a real blocking open handle.
   A failure before replacement must leave the old manifest and event log
   intact; a failure after replacement must leave the existing one-revision
   recovery case. Do not delete the destination first, clear read-only attributes,
   retry arbitrary permission errors, or fall back to copy-overwrite.
6. Keep retry behavior simple: fail through the established controlled error
   path. Add a bounded sharing-violation retry only if native evidence establishes
   a need, with explicit error-code selection and fault-order tests. Never retry
   an event append blindly, since it may already have reached the file.
7. Keep `RunLock` exclusive creation and its PID/time diagnostic record. Add
   independent-process contention and release tests using subprocesses and a
   synchronization handshake, not sleeps. Verify owner-file cleanup on exceptions,
   descriptor closure before unlink, retry after release, and stale-lock refusal.
   Killing a holder may leave a lock; recovery remains manual, never age-based.
8. Keep historical partial-initialization behavior: an interrupted creation can
   leave owned request/run files for diagnosis. Do not add repository cleanup,
   rollback deletion, or a new recovery policy while making writes portable.

Python's file-sync and permission interfaces differ from Unix on Windows; the
implementation must describe the guarantee it actually provides.
See [Python 3.11 os](https://docs.python.org/3.11/library/os.html).

## Required checks

| Scenario | Required result |
| --- | --- |
| Normal create/mutate | Valid manifest, contiguous event sequence, matching final hash |
| Before temporary write / after write / before replace | Previous committed bytes remain intact; owned temporary files cleaned |
| After replace / before event append | Exactly one recovery event on reload; second reload is a no-op |
| After event append | No duplicate audit event or revision on restart |
| File flush/fsync/replace errors | Failure is visible; no false successful transition |
| POSIX directory-sync error | Still propagates; Windows handling does not hide it |
| Completed artifact overwrite or edit | Overwrite refused or integrity failure reported through existing contracts |
| Two processes competing for one run | Only one lock holder; loser makes no mutation |
| Repeated load/approve after interruption | Existing idempotency and approval continuation behavior retained |

Run focused suites after editable installation:

```sh
python -m unittest tests.engine.unit.test_run_persistence tests.engine.unit.test_run_store tests.engine.unit.test_visit_transition_store
python -m unittest tests.engine.contract.test_interruptions tests.engine.contract.test_recovery tests.engine.contract.test_engine_orchestration
```

Run new primitive tests and the common full verification commands as well.
Partition only POSIX permission assertions that obstruct these focused tests;
do not skip the fault/recovery tests themselves. Stage 04 completes the broader
test-portability audit. Preserve native Windows traceback evidence for failures
assigned to stages 03–04.

## Exit criteria and handoff

- Real Windows create, mutate, failure, restart, and contention checks pass on
  both target interpreters; remaining full-suite failures are classified.
- POSIX fault hooks, exact stored bytes, event ordering, and compatibility tests
  remain unchanged and green.
- Documentation distinguishes atomic replacement and process-interruption
  recovery from an unverified Windows power-loss durability guarantee.
- No new runtime dependency, platform lock implementation, schema change, or
  CLI-owned cleanup scope is introduced.

If a correction breaks recovery ordering, split the extraction from the native
behavior change and restore the existing sequence before proceeding. Repair the
code, never existing consumer runs or expected fixture hashes.
