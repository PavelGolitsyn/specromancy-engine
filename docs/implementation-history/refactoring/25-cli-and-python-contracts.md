# 25. Identify current CLI output and remove obsolete API shims

**Planned after Stage 24.** A harness reading action packet version 1 can
currently see either `approval_conditions` or two kind-specific lists. The
outer approval response and `status.pending_approval` also expose two shapes
under their original versions.

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
   other public facades and the [compatibility tests](../../../tests/engine/contract/test_compatibility.py)
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

- [ ] Fresh CLI processes produce the documented envelope and nested versions
  for init, phase, approval, status, resume, block, completion and adapter
  commands. Error routing and exit codes match the CLI reference.
- [ ] An action consumer sees both approval lists and the decided action after
  restart. Transition-only fields and decline commands appear on the appropriate
  variants. Human-rendered commands execute against the same test run.
- [ ] The public imports in the reference work from an installed package.
  A repository search finds no active callers of retired compatibility names.
  Update private architecture assertions to cover real boundaries.

Run CLI and engine unit tests, action approval and CLI contract tests, and
the public import and consumer-root tests alongside the shared stage gates.
