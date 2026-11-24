# 25. Identify current CLI output and remove obsolete API shims

**Completed after Stage 24.** Earlier releases emitted two approval shapes
under one version. Stage 25 gives the envelope, action packet and status
object independent version-2 tags.

## Work

1. Advance the action packet, status object and successful/actionable envelope
   to version 2 in [actions.py](../../../src/specromancy_engine/actions.py),
   [status.py](../../../src/specromancy_engine/status.py) and
   [responses.py](../../../src/specromancy_engine/_engine/responses.py).
   Cover the separate success-envelope producer in
   [adapters.py](../../../src/specromancy_engine/adapters.py). Use a common
   envelope version wherever that envelope is emitted. Document the distinct
   version locations and keep error responses on their documented contract.
2. Project the validated Stage 24 approval variants into JSON and human output.
   For a pending action, display its number, exact details, and grant/decline
   commands. For a pending transition, include outcome and artifact binding.
   Remove fallbacks for malformed or kindless records now rejected at load.
   Exercise both CLI entry points and independent Python consumers, including
   callers that inspect the nested version before interpreting an action.
3. Trace the names in [config.py](../../../src/specromancy_engine/config.py),
   other public facades and the [compatibility tests](https://github.com/PavelGolitsyn/specromancy-engine/blob/31f2866/tests/engine/contract/test_compatibility.py)
   to current docs and callers. Remove private re-exports such as parser
   helpers and delegates whose only caller enforces an old internal API.
   Migrate actual internal callers to the defining module or canonical
   method first. For duplicate public names such as `load_config` and
   `load_pipeline`, record the supported spelling, update examples/imports
   and document any removal in the same change. Retain distinct current
   capabilities, including dynamic phase commands, the documented transition
   approval shorthand, package entry points and public exception handling.
4. Update the CLI, import-surface and architecture references. Capture complete
   current response expectations from deterministic test-owned scenarios and
   review the changed keys, versions, ordering and argv. Remove comparisons
   that impose a previous spelling or shape on current output.

## Acceptance

- [x] Fresh CLI processes produce the documented envelope and nested versions
  for init, phase, approval, status, resume, block, completion and adapter
  commands. Error routing and exit codes match the CLI reference.
- [x] An action consumer sees both approval lists and the decided action after
  restart. Transition-only fields and decline commands appear on the appropriate
  variants. Human-rendered commands execute against the same test run.
- [x] The public imports in the reference work from an installed package.
  A repository search finds no active callers of retired compatibility names.
  Update private architecture assertions to cover real boundaries.

Run CLI and engine unit tests, action approval and CLI contract tests, and
the public import and consumer-root tests alongside the shared stage gates.

## Execution record

The runtime and adapter generator share the envelope version in
`contracts.RESPONSE_SCHEMA_VERSION`. Each action and status builder stamps
its own payload. Request and status output use the same approval projection.
The transition display includes the outcome and the validated artifact digest.
Action decisions include the original details and their positions in the run's
approval history.

The deterministic response fixture covers both pending kinds, two decisions
reloaded in order, pause, resume, block, completion, and adapter generation
and check. The installed consumer suite executes the human-rendered grant
and decline argv from the run's worktree, then reopens the visit with the
Python API. The diagnostic fixture checks the unversioned error shape and
the actionable stale-approval diagnostic on stdout.

The [Python upgrade table](../../reference/contracts.md#python-import-surface)
maps retired names to their supported spellings. The import-boundary test now
loads the shared constants and the two projection modules independently and
checks that they do not initialize orchestration or persistence. A source
search found no Python callers of the retired aliases or private delegates.

### Verification

The checkout was installed in its dedicated environment using
`python -m pip install --no-build-isolation -e .`. Verification ran on macOS
arm64 with the following results.

| Check | Result |
| --- | --- |
| CLI, engine, configuration, record and transition-store units plus compatibility, architecture, orchestration, CLI, action approval and consumer-root contracts | 146 passed on Python 3.14.4 with the editable install and 146 passed on Python 3.11.15 with the installed wheel. |
| `python -m unittest discover` | 388 passed on Python 3.14.4. |
| Offline distribution verification | The direct wheel and the wheel rebuilt from the sdist each passed 101 installed tests on Python 3.14.4. They produced identical adapter manifests. |
| Adapter reproducibility and patch whitespace | `specromancy adapters generate --check`, the checkout launcher check, and `git diff --check` passed. |
