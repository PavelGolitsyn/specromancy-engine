# Specromancy Engine public contracts

## Changing a contract before 1.0

Any 0.x release, including a patch, may change a public contract. Each release
supports one current representation per surface. An older producer's data is
usable if it satisfies that contract. Apply the rule to inherited behavior too.
Retire superseded readers, writers, compatibility-only aliases, migration
paths, and tests that require obsolete inputs to succeed.

Classify a change from the documented reader and writer behavior. Removing a
required field, narrowing previously supported input, or changing what a stored
value authorizes is incompatible. For example, a change to which files an
ownership record permits the generator to replace requires a version change
even if its keys stay the same. An additive change can keep its version when
existing conforming inputs and outputs still meet the documented contract.

Advance each affected stored format or explicitly versioned CLI output
independently, including nested objects and their envelopes when both change.
Update the schema where published, readers, writers, current fixtures and
consumer instructions together. Readers must reject an unsupported version
before recovery or writes. Test the version and shape at the emission point
for output-only contracts. For unversioned Python APIs and CLI commands,
document the changed names or behavior and update callers, examples and tests.
Package releases, project-owned graph revisions and artifact validator schemas
have independent versions.

The sections below describe the current implementation. The
[Stage 23 inventory](../implementation-history/refactoring/23-pre-1-contract-policy.md)
records inherited exceptions and the stages responsible for retiring them.

## Python import surface

Import `Engine`, `RunStore`, `ExitCode`, `PipelineConfig`, `PipelineRegistry`,
`PipelineRegistration`, `load_pipeline`, `load_registry`, `generate_run_id`,
and `validate_run_id` from `specromancy_engine`. The package also exports
`EngineError`, `PipelineConfigError`, `RunCorruptionError`, and `RunNotFoundError`.
Catching these classes handles exceptions raised through the corresponding
`engine`, `config`, and `run_store` modules.

Use `specromancy_engine.config` for the loader, `require_pipeline_hash` and the
configuration records (`PipelineConfig`, `PhaseConfig`, `TransitionConfig`,
`ValidatorConfig`, and `ValidationCommand`). Use `schema_validation` for schema
loading and validation, `adapters` for generation and rendering, and `cli` for
in-process command invocation.

When upgrading Python callers, replace the following retired spellings.

| Previous API | Current API |
| --- | --- |
| `config.load_config`, `load_pipeline(..., root=...)` | `load_pipeline(path, repository_root=...)`. The root can also be positional or discovered from Git. |
| `PhaseConfig.validation_commands` | `PhaseConfig.commands` |
| `PipelineConfig.hash`, `config.hash_pipeline(pipeline)`, `config.canonicalize_pipeline(pipeline)` | `pipeline.config_hash` for the SHA-256, `pipeline.canonical_json` for its input text |
| `hashing.hash_bytes/text/json/file` | `hashing.sha256_bytes`, `sha256_text`, `sha256_json`, `sha256_file` |
| `artifacts.resolve_artifact_reference`, `artifacts.verify_artifacts` | `resolve_input_reference`, `verify_manifest_artifacts` in `artifacts` |
| `git.snapshot_repository`, `engine.capture_git_metadata` | `git.capture_repository_snapshot`. Select the required fields from the snapshot. |
| Module-level `run_store.new_run_id`, `CorruptRunError` | `generate_run_id`, `RunCorruptionError`. The instance method `RunStore.new_run_id()` uses the store's injected clock and random source. |
| `RunStore.create_run`, `load_run`, `create_visit`, `update` | `create`, `load`, `start_visit`, `mutate`, respectively |
| `engine.RESPONSE_SCHEMA_VERSION`, `config.RESERVED_COMMANDS` | `contracts.RESPONSE_SCHEMA_VERSION`, `contracts.RESERVED_COMMANDS` |

Replace imports of `config.SUPPORTED_SCHEMA_VERSION`, `IDENTIFIER_PATTERN`,
`MUTATION_POLICIES`, and `VALIDATOR_TYPES` with the version, pattern and enums
in the published pipeline schema. Schema-subset constants live in
`schema_validation`. Import artifact path and reference helpers from
`artifacts`, and path resolution and SHA-256 helpers from `hashing`.
Use `load_pipeline` for full graph and resource validation. The config
facade no longer exports parser constants, private helpers or a loader class.
The source tree lives under `src/specromancy_engine/`; its four JSON schemas are
packaged under `specromancy_engine/schemas/` in the installed distribution.

The `_config`, `_runs`, `_engine`, `_adapters`, and `_cli` subpackages are private
implementation details, not supported import contracts. Use the public facades
for configuration records, errors, loading, execution, and run storage.

The distribution is named `specromancy-engine`, requires
Python 3.11 or newer, and has no third-party runtime dependencies. It installs
the `specromancy = specromancy_engine.cli:main` console entry point. Module
invocation is `python -m specromancy_engine`.

`project.version` in [`pyproject.toml`](../../pyproject.toml) is the single version
source. `specromancy_engine.__version__` reads it when imported from the producer's
`src/` checkout or source export, including editable installations. Other
installations read their distribution version through `importlib.metadata`.
Version lookup is independent of the working directory. A checkout's version
takes precedence over installed metadata; reinstall after a version bump to
refresh editable-install metadata. Missing installed metadata raises
`importlib.metadata.PackageNotFoundError` when no producer checkout is available.

Action packets emit `final_validation_command` as an argv starting with
`["specromancy"]`. Execute it with the installed console script on `PATH`;
source-export users can put the checkout's `bin/` on `PATH`. Consumer-configured
validation commands execute the argv declared in their pipeline.

## Installed resources and consumer roots

Installation supplies the engine and release templates and creates no consumer
repository files. Author repository instructions, graphs, phase skills and
their referenced resources under `workflow/`, then generate harness outputs.
The source distribution includes the [consumer example](../../examples/release-documentation/README.md).

The installed engine has no implicit pipeline or producer-checkout fallback.
CLI discovery starts at the working directory and walks upward to a `.git`
directory or worktree marker file. An explicit `--root PATH` overrides discovery,
including from an unrelated directory, and must name an existing directory.
Without a Git marker, pass `--root`; initialization additionally requires
`allow_non_git = true` in the selected graph to permit a non-Git project.
`workflow/pipelines.toml` remains mandatory and initialization requires an
explicit registered ID. Existing runs load the saved project-relative pipeline
path and ID, even if the registry now registers that ID at another path.

Each root owns its registry, graphs, skills, templates, validator schemas, and
`.specromancy/runs/`. Graph and resource resolution is scoped to that root on
each load; identical pipeline IDs in different projects do not share state.
Skills resolve from the root; templates and validator schemas resolve from the
graph's directory. All three use the workflow containment rules below.
No installed command
requires writes to the package, the producer checkout, or home-directory
configuration. Python bytecode caching can be disabled independently with
`PYTHONDONTWRITEBYTECODE=1` when testing a read-only installation.

The four published schemas are `pipeline.schema.json` (graph),
`pipelines.schema.json` (registry), `run.schema.json` (manifest), and
`event.schema.json` (event). Read them using Python 3.11-compatible resource APIs:

```python
import json
from importlib.resources import files

schema = json.loads(
    files("specromancy_engine").joinpath("schemas", "run.schema.json")
    .read_text(encoding="utf-8")
)
```

These published JSON Schema documents describe engine formats for external
tools; the runtime's loaders and record validators enforce those contracts.
They are separate from `schema_validation.load_json_schema(path)`, which loads
a **project-owned** artifact validator using the limited subset documented
below. Published schemas use keywords outside that subset and must not be
passed to its loader as an availability check. No schema subset is expanded by
packaging. When an external tool needs a filesystem path to a package resource,
use `importlib.resources.as_file(resource)` only for the duration of its context;
never persist the temporary path in run records.

The release also ships seven UTF-8 Markdown templates under
`specromancy_engine/resources/adapters/`. These supply the repository
instruction envelope, phase discovery wrapper, orchestration procedure,
pipeline launch skill, and Claude, Copilot, and OpenCode command wrappers.
The phase wrapper points to its canonical workflow file and resolves support
references from that file's directory. The launch skill embeds the entire
orchestration procedure together with the registered pipeline ID.

Internal capture reads these templates from the installed package and identifies
each by a logical ID such as `@package/specromancy_engine/resources/adapters/launch.md`.
It preserves the exact bytes for SHA-256 hashing and captures the package
version under `@package/specromancy_engine/version`. Both identifiers are
independent of the install location. Rendering substitutes named fields once
and emits LF text with one trailing newline. Braces and dollar signs in
consumer Markdown and command arguments remain literal.

For Python embedding, use the existing public facades and explicit consumer
roots; see the [executable examples](../guides/authoring-pipelines.md#embed-the-installed-engine).

## Vocabulary

- **Pipeline:** a versioned directed graph of phases.
- **Phase:** a configured unit of agent work with declared inputs, output, mutation policy, validation, and transitions.
- **Visit:** one execution attempt of a phase. Loops may cause a phase to have multiple visits.
- **Artifact:** a file produced or consumed by a visit.
- **Outcome:** a configured result such as `validated`, `changes-requested`, or `blocked`.
- **Gate:** a mechanical condition that prevents transition, including approval.
- **Run:** one execution of a pipeline for a user request.
- **Action packet:** the fully resolved instructions emitted by the CLI for the current visit.
- **Adapter:** generated harness-native instructions or a command wrapper containing no canonical workflow logic.

## Command surface

The reserved commands are:

```text
init DESCRIPTION --pipeline ID
phase RUN_ID PHASE
<dynamic-phase> RUN_ID
validate RUN_ID [PHASE] [--outcome OUTCOME]
approve RUN_ID PHASE [--request N]
decline RUN_ID PHASE --request N
request-approval RUN_ID [--reason CODE] [--details TEXT] [--outcome OUTCOME]
block RUN_ID [--reason CODE] [--details TEXT]
status RUN_ID
resume RUN_ID
run RUN_ID
adapters generate [--check]
```

Workflow commands accept `--root PATH`, `--pipeline ID`, `--json`, and `--quiet`. Built-in commands are resolved before dynamic phase aliases; pipeline phase names must avoid reserved commands.

`--reason` may be omitted only when the current phase declares exactly one
approval reason across both lists, or one stop reason for `block`. `validate --outcome` is required when a phase has
multiple non-blocking outcomes and is rejected when there is only one.

The installed `specromancy` command, diagnostic `python -m specromancy_engine`
invocation, and optional checkout-only `bin/specromancy` launcher share the same
package entry point. Generated instructions use `specromancy`; the harness
process must inherit its environment on `PATH`. Activating a terminal does not
update an already-running GUI harness. The repository root is found by walking
upward to a `.git` directory or worktree marker. `--root` supplies an explicit
root for fixtures and non-Git directories. Status `next_command` argv relies on
the consumer cwd (or an added `--root`); action `final_validation_command` argv
already carries the absolute consumer root.

### Adapter generation

Generation and check require the user-owned `workflow/adapters.toml`, guarded
before parsing by the same declared/resolved workflow boundary as graph inputs.
Its only keys are integer `schema_version = 1` and `harnesses`, an array of
unique supported identifiers. Missing configuration reports the supported names
and an example. Both commands are non-interactive and reject `--pipeline`.
For nonempty selection generation validates every registration. With an empty
selection it checks prior ownership and reconciles to zero generated files.
Generator version 4 writes schema 2 and carries the generator name `specromancy`.
`--check` compares expected output and ownership without writing. It reports
drift when the generated tree or manifest differs.

The Python `cli.adapter_command_metadata` facade shares explicit descriptions
with parser construction and returns the same sorted command metadata without
inspecting argparse internals. `adapters.render_adapters(root, registry, metadata)`
retains its render-only contract. `adapters.generate_adapters` still accepts
explicit metadata; when omitted, metadata is derived from that invocation's
validated graphs. Generation reuses captured source text and bytes for rendering
and source hashes, without a cross-invocation cache. Adapter constants and
`AdapterError` remain available from `specromancy_engine.adapters`.

For selected outputs, generation and rendering use a registry snapshot and capture
`workflow/instructions.md`, every registered graph, and its explicitly declared
workflow procedures and dependencies. Both facades check the registry root,
registry path, and registration locations before consuming the snapshot. A caller that
needs this guarantee from the first registry read uses
`load_adapter_registry(root)`. Earlier reads made by the caller are outside
the capture guarantee. Adapter CLI commands use that loader before parsing TOML.
Render-only validates the same locations and graph definitions, including
validator schemas. Reading artifact-template contents
for hashing and inspecting ownership or drift are generation/check operations.

Instructions and complete canonical procedures use UTF-8, LF, and one trailing
newline for adapter provenance. The manifest also hashes validated configuration,
dependency bytes, CLI metadata for command wrappers, package version, and exact
bytes of required release templates. The canonical selection input identifies
`workflow/adapters.toml` and hashes canonical JSON containing `schema_version`
and the sorted `harnesses` array. TOML comments and list order do not affect it.
For an empty selection this is the only manifest input.
A procedure-body edit can change only the manifest. Metadata and path edits can
also change phase wrapper bytes. Regenerate and check after either kind of edit.
Phase wrappers retain the validated frontmatter and load the declared procedure from the consumer root.
An action packet identifies the authoritative file. A missing file or a mismatch
stops the visit. Relative references inside the procedure use its own directory.

In generator v4 each output has one `path`, one `sha256`, and a sorted
`targets` list of its selected consumers. Each selected target lists all its required paths. Root `AGENTS.md`
serves Codex, Hermes, and OpenCode. Shared `.agents/skills` serve those three
and Copilot. Claude has its own instructions, skills, and commands. Copilot
also requires its instructions and prompts, and OpenCode its commands. Codex
and Hermes list the shared skills in `discovery_paths`. Each launch embeds the
coordination procedure with the registered pipeline ID.

Generation and check validate the previous manifest's generator identity and
ownership records. Schema 1 generators 1 and 2 use their original single-target
mapping. Under `.agents` they own only recorded `skills/specromancy-*/SKILL.md`
outputs. Their Claude mirrors retain the original `.claude/skills/*/SKILL.md`
grammar. Generator 3 requires the original all-target mapping. Generator 4
validates attribution against its recorded selection. Both schema-2 versions
check the consuming targets in both directions. Unrelated
skills beside expected outputs are ignored. An existing expected file requires
valid prior ownership even when its bytes match. Regeneration restores edited
current outputs and removes stale owned outputs only while their recorded hashes
match.

## Pipeline registry and selection

`workflow/pipelines.toml` is mandatory for workflow and adapter commands:

```toml
schema_version = 1

[[pipelines]]
id = "implementation"
path = "pipelines/implementation.toml"
```

At least one registration is required. Only `schema_version` and `pipelines`
are accepted at the top level; each registration contains only `id` and `path`.
IDs use lowercase kebab-case, match the graph's ID, and are unique. Resolved
paths are unique TOML files under `workflow/pipelines/`, relative to `workflow/`.
Segments use letters, numbers, underscores or hyphens. Unsafe, escaping,
missing and duplicate paths are rejected with `INVALID_PIPELINE` diagnostics.
The registry format is published in `src/specromancy_engine/schemas/pipelines.schema.json`;
filesystem containment and cross-file identity are additionally validated by
the loader. `load_registry(root)` returns immutable registrations; `load(id)`
validates the selected graph and `load_all()` validates every registration.
`load_pipeline(path, root)` remains a low-level explicit-path API with no default.

Initialization requires `--pipeline ID`, even for a single registration. Paths
and unknown IDs cannot initialize a run. Existing-run commands select the graph
from validated persisted provenance; an optional ID must match the run. Paths
are not accepted as selectors. Packets omit the selector in their validation command.
Pipeline edits still enforce provenance and approval invalidation. Removing a
registration disables initialization but retains existing-run access while the
original files exist. Registry ordering and unrelated graph edits do not alter
another pipeline's run. Every workflow command requires a valid registry;
help remains available without one.

### Workflow-owned procedures (pipeline schema 3)

Each phase declares `skill_source = "workflow/skills/compose/SKILL.md"` alongside
`skill = "compose"`. The identifier remains lowercase kebab-case. The source
is a repository-relative POSIX file path with no parent segments. The parser
normalizes redundant separators and current-directory segments, stores this
declared path as `PhaseConfig.skill_source`, and includes it in canonical JSON.
Callers constructing `PhaseConfig` directly must supply the `skill_source` keyword.
`PhaseConfig.skill_path` holds the resolved regular file. Both the declared
location and the symlink target of each procedure, output template, and validator
must be inside a non-symlinked `workflow/` directory. Templates and validators
retain their graph-relative bases, including safe `../templates/` references.

Each skill has portable UTF-8 frontmatter with a matching `name` and a
nonempty `description`. See [authoring pipelines](../guides/authoring-pipelines.md#skills-and-templates)
for the supported fields. Each identifier binds to one normalized declaration
and one resolved file. A file can serve multiple phases under the same identifier.
Runtime validation checks the selected graph. The guarded adapter preparation
path checks bindings across the registry and requires explicit sources in every phase.
`registry.load_adapter_registry(root)` validates source locations before parsing
the registry. Its `load_adapter_pipelines(root)` method rechecks the supplied
registry and registration paths before loading graphs and reuses the parsed registry.

Graph schema 3 requires `skill_source`, `transition_approval_conditions`, and
`action_approval_conditions` on every phase. The loader checks `schema_version`
before it interprets graph fields. A missing source declaration in schema 3
reports `missing-skill-source` with the pipeline, phase and field. The registry
and harness-selection documents each use their own schema version 1.

The graph author controls the positive integer `version`. A run saves the graph
ID, path, author revision, and SHA-256 of the canonical configuration, including
its schema version and normalized procedure declarations. A semantic graph edit
changes the hash even at the same revision. Finish runs created under a retired
graph schema with the producing engine and original resources, or initialize
a separate run under schema 3.

Prepared visits seal the raw bytes at the resolved procedure path and return
that path and digest in `action.skill`. A missing declared source is an error,
even when a same-named discovery file exists. A retained Python configuration
rechecks its resource locations before run operations. If a descendant symlink
in the same graph comes to identify a different workflow file for a prepared
procedure or template, continuation with the reloaded graph reports
`provenance-path-mismatch` before reading the old recorded location.

## Filesystem ownership

The CLI may create or replace files only in:

- `.specromancy/runs/<run-id>/`;
- generated adapter paths recorded in `adapters/manifest.json`;
- explicit temporary files adjacent to a manifest during atomic replacement.

The CLI never deletes, resets, stages, or commits repository work. Cleanup is limited to generated paths owned by the previous adapter manifest.

`adapters/manifest.json` is the schema-versioned ownership boundary. It records
the generator version and regeneration command, canonical source records and
aggregate hash, every generated adapter path and content hash, and generated or
native mode for every selected harness. Native Codex and Hermes targets
record shared skill `discovery_paths`. Each generated file has a single
ownership record listing all selected consuming targets. The manifest omits its own hash to
avoid self-reference and contains no timestamps or absolute paths.

Generation preflights ownership conflicts before writing, rechecks stale owned
file hashes before removal, replaces each output atomically, and writes the
manifest last. An interruption between replacements can leave some new outputs
alongside the previous manifest. Preserve any user edits and resolve unowned
collisions before retrying. Check mode validates previous ownership, compares
expected bytes, and creates no temporary output files. Both modes ignore foreign
files exclusive to unselected harnesses, including names in reserved command
directories. Previously owned files that lose their last consumer remain subject
to stale-file checks. Resolve modified stale files before retrying.
Selection and generation preserve pipeline and skill identities and do not write
run records, approvals, or visit artifacts. Repository mutation checks still see
edits to configuration and generated paths under the active visit's baseline.

## Configuration and state handling

Run and event schema versions are independent of the package version. Keep
`.specromancy/` at its existing location. Never rewrite `run.json`, `events.jsonl`,
artifact hashes, or completed outputs to bypass validation or force compatibility.
Status inspection can recover an interrupted commit and append a recovery event;
it is not guaranteed to leave every run byte-identical.

Graph and artifact drift can invalidate approval. Prepared skill/template drift
produces provenance warnings and prevents continuation. Editing an approved output
before advancement marks the approval stale and requires a fresh decision.
Finish active runs with their producing engine and recorded resources, or
initialize a separate run when adopting the new graph.

Configuration and adapter changes are separate from installing the engine.
Preserve project instructions and the adapter manifest, and follow the ownership
rules when regenerating. Forward replay of historical development fixtures does
not establish downgrade safety after new state writes. A package downgrade does
not undo configuration or renderer changes.

## Run persistence

Run IDs use a UTC timestamp and eight lowercase hexadecimal characters, for
example `20260922T142501Z-a1b2c3d4`. Only IDs matching that form may be used to
address `.specromancy/runs/`.

The `specromancy_engine.run_store` module exposes `RunStoreError`,
`RunNotFoundError`, and `RunCorruptionError` for storage failures. Run and
event records each use schema version 2. `RunStore` returns ordinary, defensively copied
dictionaries; record annotations neither construct defaults nor validate
external data. Generation accepts injected clocks and zero-argument or sized
random sources, and timestamp formatting remains UTC with microseconds and `Z`.

`run.json` is the validated current snapshot. Each mutation increments its
`revision`, atomically replaces the file, and appends an `events.jsonl` record
that contains the revision and canonical manifest hash. If interruption occurs
after replacement but before the event append, the next load appends a
`recovery` event. A malformed manifest, a malformed event, a non-contiguous
event sequence, or any other manifest/event disagreement is corrupt state and
is not repaired heuristically.

### Stored versions and fields

All reads validate the manifest and every event under the run lock before
reconciliation. An unsupported positive integer version raises `RunStoreError`
with exit code 12 and diagnostic `unsupported-schema-version`. Its details
include `run_id`, `surface` (run or event), `observed_version`, and
`expected_version`. Finish an older run with its producing engine and the
original graph, skills, templates, and validators. To adopt the new engine,
start a separate run. Preserve the archived log with its manifest and artifacts.

Missing or malformed version tags and malformed current records raise
`RunCorruptionError` (`corrupt-run`, exit 12). For example, an invalid run
status reports `manifest status is invalid`. An invalid visit status reports
`visit identity or status is invalid`. A one-event gap permits recovery only
after these checks pass.

Versions, counters and ordinals require positive JSON integer tokens. A
decimal point or exponent is invalid even when the number is mathematically
integral. JSON Schema treats `2.0` as equal to `2` and as an integer. Consumers
must also check token types when decoding. Booleans are a distinct JSON type,
including in Python callers where `True == 1`. Timestamps are UTC calendar
date-times ending in `Z`, with optional fractional seconds.

Pipeline and phase identifiers, input references, and non-null visit outcomes
and targets must contain non-whitespace text. Each visit records a mutation
policy of `read-only`, `repository-write`, or `allowlist`. The loader checks
ordinal and per-phase attempt ordering, current-visit bounds, start/completion
timestamps for started/completed visits, and output sealing. Run status and
visit status can differ. For example, low-level completion seals a visit
without advancing the run, and a paused run can point to a pending successor.

Git base/head, mutation baseline/result, terminal result, block reason and
the entries in the validation-check, command-result and deviation arrays can
hold arbitrary finite JSON. These fields support low-level store operations
and historical evidence. Engine gates collect and check the evidence needed
for the requested operation.

### Durable operations and visit preparation

The internal `run_persistence` component owns serialization, reconciliation,
and commits. `RunStore` retains repository/run path ownership checks and artifact
verification, and collects evidence for the pure internal `visit_transitions`
decisions. Those decisions return copied state and event payloads (or an explicit
no-op); they do not read files or clocks, assign revisions, or acquire locks.
One lock spans manifest/event loading, the
change, validation, replacement, and append; internal commit helpers do not
reacquire it. Idempotent activation, transition, and resume returns do not add
a revision or event. The general `mutate` API always commits a valid proposal,
even if its callback leaves the record unchanged. Custom event types accept
object payloads containing arbitrary finite JSON. The store validates and
serializes the candidate audit event before it replaces the manifest. A
rejected candidate therefore preserves the previous revision and log.

Visit preparation resolves symbolic inputs and hashes skill/template provenance
immediately, including for a pending successor at a paused edge. Activation
records the start timestamp and mutation baseline without refreshing those
records. A graph transition seals the current output and prepares its successor
in one commit; a reached limit records a blocked visit without sealing its output
or creating a successor. Resume releases a paused checkpoint while leaving the
successor pending. The low-level `start_visit` and `complete_visit` methods retain
their separate semantics: start appends an active visit, and completion seals a
visit without advancing the run. Completion rejects an already completed visit;
transition accepts an exact outcome/target retry without another commit.

`read_pipeline(run_id)` returns a detached copy of the saved pipeline record.
It checks manifest and log consistency and permits a one-revision gap without
repairing it. The CLI uses this lookup to select and validate the saved graph
before a command's normal load can recover. Both `load(recover=False)` and
`read_events(recover=False)` require a synchronized manifest and log.
`load(verify_artifacts=False)` skips artifact verification independently and
still permits recovery by default. Normal loads, including those invoked by
`status`, may append the allowed recovery event; recovery precedes artifact
verification, so an artifact error may be reported after that append.

Creation first makes the run directory and request artifact, then commits
revision 1. Engine initialization prepares its first visit in a separate commit.
Interruption can therefore leave a directory/request without a manifest or a
created run without a visit. These operations are not one transaction, and the
store does not automatically clean up partially initialized runs.

Each run uses an exclusive `.lock` file containing the owner PID and acquisition
time. Locks are never expired based on age alone. After verifying that its owner
is no longer running, a stale lock must be removed manually.

Artifact paths in manifests are normalized relative paths. Symbolic inputs are
resolved once, when a visit is prepared (or created active by `start_visit`), to
literal paths and SHA-256 hashes. Activating a pending visit does not resolve
them again. Request artifacts and completed visit outputs are immutable; hash drift is a corrupt
state diagnostic rather than an instruction to rewrite either the file or its
record.

## Exit codes and output

| Code | Name | Meaning |
| ---: | --- | --- |
| 0 | `SUCCESS` | Command completed successfully |
| 2 | `USAGE_ERROR` | CLI usage error |
| 3 | `INVALID_PIPELINE` | Invalid pipeline configuration |
| 4 | `NOT_FOUND` | Run or artifact not found |
| 5 | `ILLEGAL_TRANSITION` | Illegal state transition |
| 6 | `VALIDATION_FAILED` | Validation failed |
| 7 | `APPROVAL_REQUIRED` | Approval required |
| 8 | `AGENT_ACTION_REQUIRED` | Agent action required |
| 9 | `RUN_BLOCKED` | Run blocked or stopped |
| 10 | `LOCK_HELD` | Concurrent run lock held |
| 11 | `ADAPTER_DRIFT` | Adapter drift detected |
| 12 | `INTERNAL_ERROR` | Internal or corrupt-state error |
| 13 | `RUN_PAUSED` | Run paused at a configured checkpoint |

Successful and actionable command results use stdout. With `--json`, the
outer object has `schema_version: 2`, `kind`, `code`, and `message`.
Dispatch on that version and kind first. For `action`, check
`action.schema_version` before consuming the packet. For `status` and
`approval`, check `status.schema_version` before using the status projection.
Both nested versions are 2. The `adapters` result uses the common outer
version for generation and check.

Diagnostics carry `code`, `message`, and optional `details` without a version
or kind. They use stderr, except actionable diagnostics such as
`stale-approval` (7), which use stdout.

Upgrade harnesses that consumed version 1 by reading the two kind-specific
approval lists and the current visit's `action_decisions` in request order.
Pending approvals in `approval` and `status.pending_approval` carry the stored
record, its one-based `request_number`, and a numbered `approve_command`.
Only actions carry `decline_command`. Only transitions carry `outcome` and
`artifact_sha256`. Status uses null for an absent pending approval.

An action packet uses schema version 2 and contains stable keys for `run_id`,
`visit_id`, `visit_attempt`, `visit_status`, `phase`, `skill`, `inputs`,
`output`, `template`, `mutation`, `completion_criteria`, `validation`,
`action_approval_conditions`, `transition_approval_conditions`, `action_decisions`,
`stop_conditions`, `outcomes`, and
`final_validation_command`. Literal artifact records retain repository- or
run-relative paths and add `absolute_path` for direct harness use.

## Validation and safety

Pipelines require a real Git worktree by default. A pipeline intended for a
non-Git fixture or repository must explicitly set `allow_non_git = true`.
Repository snapshots include every tracked and non-ignored untracked path and
record file content, mode, and symlink target without following symlinks.
`.git/` and CLI-owned `.specromancy/` storage are excluded.

Markdown validators require configured headings exactly once by default;
`heading_occurrence = "at-least-once"` relaxes duplicate handling. JSON
validators may reference a schema file and support only `type`, `required`,
`properties`, `items`, `enum`, `pattern`, and `additionalProperties`.
Unsupported schema keywords make the pipeline invalid at load time.

Validation commands are trusted repository configuration and execute from the
repository root with the user's permissions. They are argument arrays, never
shell strings. Full stdout and stderr remain in ignored run storage; manifests
contain byte-limited summaries with values from secret-like environment
variables redacted. The environment itself is never persisted.

Validation checks the output artifact first, runs commands sequentially, and
then checks the repository mutation policy. A required command failure stops
the command sequence; an optional failure does not. Mutation enforcement still
runs after command execution and its failure takes precedence over a required
command failure. An expected validation failure records one attempt with the
available artifact, command, and mutation evidence before returning its error;
the visit remains retriable.

## Approval consistency

The ordered `approvals` array gives each request a one-based number. Every
record stores `kind` as `action` or `transition`. Both kinds bind the run, visit, phase, pipeline hash, reason,
exact details, and request timestamp. A transition also binds the validated
artifact hash and outcome. The stored phase must match the referenced visit
ordinal in that run, and the pipeline digest must match its saved provenance.
A visit can have one pending request across both kinds. The array position
identifies a request even when a clock repeats a timestamp.

Pending records have null `decision`, `actor`, and `decided_at`. A user grant
records `approved` for both status and decision, actor `user`, and a decision
timestamp. An action decline uses `declined` for status and decision. A stale
request records decision `invalidated`, actor `system`, and a decision timestamp.
A transition's details may be text or null.

Action requests require nonblank details and preserve the visit's original
mutation baseline and completion evidence. Request and grant check sealed
inputs, procedure provenance, and mutation policy. They can run before the
output exists. Grant and decline record the user's decision and restore the
same visit to active in one revision. Action events carry `payload.request_number`
for `approval-requested`, `approval-granted`, `approval-declined`, and
`approval-invalidated`. A pending action with a changed graph becomes stale
and returns the visit to active. Restoring the graph permits a fresh request.

Approval events require a positive `visit_number`. Each payload includes
`kind`. The table lists its remaining fields. Every action payload also
requires the positive one-based `request_number`.

| Event | Action | Transition |
| --- | --- | --- |
| `approval-requested` | `reason` | `reason`, `outcome` |
| `approval-granted` | `actor: "user"` | `actor: "user"`, `phase_id` |
| `approval-declined` | `actor: "user"` | Unsupported |
| `approval-invalidated` | `mismatches: ["pipeline"]` | Nonempty `mismatches` containing `artifact`, `pipeline`, or both in that order |

Under the run lock, a pending request takes priority over a replay. An exact
pending request returns exit 7. A different request or a decision aimed at
another record conflicts (5). On the active visit, an exact decided action or
matching decision returns the recorded result (8). An opposite decision
conflicts. Replays and conflicts leave the revision and event log intact.

Transition approval and advancement remain separate durable operations.
A caller supplying `approval` to `RunStore.transition_visit` must supply the
stored transition grant for that visit and outcome and its configured target.
After an interruption, only a granted transition can resume advancement.
Revalidation failure records evidence and retains the grant. A matching
continuation of a completed transition leaves the successor untouched.

Validation commands execute outside the lock. A validation result, transition
request, or block observed on an active visit may commit only at the observed
revision with the same active visit. This also excludes observations from before
an intervening action grant or decline. A failed validation that commits first
leaves the visit eligible for an action request.

A stale observation invalidates only its exact eligible pending or granted
request, adding one `approval-invalidated` revision/event before returning
`stale-approval` (7). Mismatch labels remain ordered: `artifact`, then `pipeline`.
An in-flight duplicate invalidation of that same request returns `stale-approval`
without another event, provided no replacement or visit change has occurred.

An overtaken decision whose request is absent, replaced, ambiguous, missing
identity fields, associated with the wrong run/visit, or completed with a different
outcome/target fails with `EngineError`, `ILLEGAL_TRANSITION` (5), diagnostic
`approval-state-changed`, and message `approval state changed before the command
could be applied`. Details contain `error_code`, `run_id`, observed `phase`, and
observed `visit_number`. The conflict creates no revision/event and preserves the
winner.

Lock contention still returns `LOCK_HELD` (10) without implicit retries. General
`RunStore.mutate` still commits an unchanged callback; only explicit decision
no-ops skip commits. Approval decisions use the existing persistence protocol:
interruption after manifest replacement but before event append is repaired on
load with one `recovery` event at the same revision, without synthesizing the
missing approval event.
External artifact edits are not made atomic with validation by this lock.

The [integration evidence](../implementation-history/refactoring/15-follow-on-integration.md#intentional-behavior-corrections)
maps approval overlap outcomes and malformed-status diagnostics to their tests.
