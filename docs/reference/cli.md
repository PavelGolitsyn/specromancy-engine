# CLI reference

Install the engine wheel using the [consumer installation guide](../guides/installation.md)
and use `specromancy` or `python -m specromancy_engine` from the consumer repository.
Python 3.11 or newer is required; the runtime has no third-party dependencies.
Contributors use `python -m pip install -e .` in a dedicated environment; the
optional `bin/specromancy` wrapper also runs directly from a producer checkout.

Global options may appear before or after a subcommand:

```text
--root PATH       explicit repository root
--pipeline ID     registered pipeline ID (required for init)
--json            emit exactly one JSON object
--quiet           suppress successful human-readable output
```

`--root` is required when no `.git` directory or worktree marker can be
discovered. `workflow/pipelines.toml` is mandatory and contains at least one
registration pointing to a TOML graph under `workflow/pipelines/`. There is no
default pipeline. See [Workflow customization](../../workflow/README.md).

## Workflow commands

```bash
specromancy init "describe the requested change" --pipeline implementation
specromancy status RUN_ID
specromancy resume RUN_ID
specromancy phase RUN_ID PHASE
specromancy validate RUN_ID PHASE
```

- `init DESCRIPTION --pipeline ID` creates a run, immutable request artifact, and pending
  first visit. `--description-file PATH` reads the request from UTF-8 input.
  Relative description-file paths resolve from the selected consumer root.
  This copies request content; it does not introduce arbitrary file selectors
  for phase inputs. See the [complete walkthrough](../../examples/release-documentation/README.md).
- `status RUN_ID` reports current persisted state, warnings, and the next command
  without advancing the workflow. Loading may append a recovery event for an
  interrupted manifest commit, as described in the persistence contract.
- `resume RUN_ID` reconstructs the next boundary from disk. For a paused run it
  atomically releases the checkpoint and returns the pending successor action;
  otherwise it returns the current boundary without a new transition. Loading
  may recover the same permitted audit gap. It does not depend on the process
  or conversation that created the run.
- `phase RUN_ID PHASE` starts or resumes only the recorded current phase and
  emits its action packet. Each configured phase also has a dynamic alias, such
  as `specromancy research RUN_ID` when the run's graph declares that phase.
- `validate RUN_ID [PHASE] [--outcome OUTCOME]` validates the output, configured
  commands, and repository mutation policy before recording a transition.
  `--outcome` is required when more than one non-blocking outcome is possible.
  Omit it when there is only one successful outcome. Use `block` with a declared
  stop reason for blocking; `--outcome blocked` is not a validation route.
- `run RUN_ID` performs deterministic CLI work until the next agent, pause,
  approval, block, failure, or terminal boundary. It never launches a harness.

Existing-run commands select the original graph from validated persisted ID,
path, version and hash. An optional `--pipeline ID` must agree with that run.
Paths are not accepted as selectors. Action packets validate using the run ID
without a selector.

Removing a registration prevents new runs while existing runs can still use
their original files. The CLI checks the saved graph’s schema before recovery.
Finish a run that uses graph schema 1 or 2 with its producing engine and original
resources, or initialize a separate run under schema 3. Existing-run commands
load only the saved graph.

## Approval and stop commands

```bash
specromancy request-approval RUN_ID --reason REASON --details TEXT
specromancy approve RUN_ID PHASE --request N
specromancy decline RUN_ID PHASE --request N
specromancy block RUN_ID --reason REASON --details TEXT
```

The phase must declare the requested reason. You can omit `--reason` when the
two approval lists contain one reason in total. For an action, give the exact
proposed change in nonblank `--details` and omit `--outcome`. The request
returns exit 7 and shows its number and decision commands. A grant or decline
returns exit 8 with the same active visit's action packet. Run the packet's
final validation command after completing the work.

A transition request validates the output and commands and binds the output hash
and selected outcome. Supply `--outcome` for multiple successful outcomes.
Granting the request rechecks the binding, validates again, and follows the
saved transition. The unnumbered `approve RUN_ID PHASE` form remains available
for transition approvals. `decline` applies only to actions.

Run and visit state, exact details, and request number identify the decision.
An exact pending retry returns the same record. A competing request, a decision
for a different record while one is pending, or a reversed decision returns
exit 5 without changing state. After a decision, `phase RUN_ID PHASE` shows
the visit's recorded action decisions. `block` records a declared stop reason.
Lock contention remains exit code 10 without automatic retries. Full binding,
retry, and audit rules are in the [approval consistency contract](contracts.md#approval-consistency).

## Adapter commands

```bash
specromancy adapters generate
specromancy adapters generate --check
```

Both commands require `workflow/adapters.toml` with `schema_version = 1` and
a `harnesses` array. A missing or invalid choice returns configuration error 3.
An empty array reconciles to zero harness files. For a nonempty selection,
generation reads `workflow/instructions.md`, the registry and every registered
graph, including declared phase procedures, templates and validators. Both
commands guard the registry location before parsing it. Use explicit `skill_source`
declarations and consistent skill bindings across registrations. Runtime commands
validate the selected graph independently. Generation rejects `--pipeline`.

The selected harnesses determine which instruction files, wrappers, and launch
skills are required. The generator-v4, schema-2 manifest records each output
once with its selected consumers. `--check` reports missing, modified, unexpected or source-stale files
without writing. See [Adapter generation](contracts.md#adapter-generation).

## JSON and exit codes

With `--json`, the CLI emits one object. Successful and actionable envelopes
on stdout carry `schema_version: 2`, `kind`, `code`, and `message`.

| Envelope kind | Payload and version to check |
| --- | --- |
| `action` | Check `action.schema_version == 2` before reading the phase, approval lists, decided actions, or validation argv. |
| `approval` | Check `status.schema_version == 2`. A pending request appears in both `approval` and `status.pending_approval`. |
| `status` | Check `status.schema_version == 2` for read-only, paused, blocked, and completed runs. |
| `adapters` | Generation and check use the outer version. The `adapters` payload contains the manifest path, source hash, generated paths, removed paths, and check flag. |

For a pending request, inspect `kind` and the one-based `request_number`.
An action includes its exact `details` and both `approve_command` and
`decline_command`. A transition includes `outcome`, `artifact_sha256`,
nullable `details`, and `approve_command`. Run decision argv from the
consumer worktree or supply its `--root`. Human approval and status output
show the same decision commands and bindings.

Diagnostics use the unversioned object with `code`, `message`, and optional
`details`. A stable diagnostic identifier appears in `details.error_code`.
Errors use stderr, including lock contention (10). The actionable
`stale-approval` diagnostic (7) uses stdout and also has the unversioned shape.

| Code | Meaning |
| ---: | --- |
| 0 | success |
| 2 | CLI usage error |
| 3 | invalid or changed pipeline |
| 4 | run or artifact not found |
| 5 | illegal transition |
| 6 | artifact, command, or mutation validation failed |
| 7 | approval required |
| 8 | agent action required |
| 9 | run blocked |
| 10 | run lock held |
| 11 | generated adapter drift |
| 12 | internal or corrupt-state error |
| 13 | run paused at a configured checkpoint |

Exit codes 7–9 and 13 identify workflow boundaries.
In particular, init and phase start normally return 8. Automation using `set -e`
must capture and handle that code before continuing with the emitted action.
Status returns 0 for a readable state; inspect its status and terminal result
instead of treating that return code alone as workflow completion.
Full public contracts are recorded in [contracts.md](contracts.md).

Malformed run or visit statuses, including JSON arrays and objects, return
`corrupt-run` (12), with `manifest status is invalid` or
`visit identity or status is invalid`. These failures occur before audit recovery
and leave persisted files unchanged. See the [stored field contract](contracts.md#stored-versions-and-fields).
