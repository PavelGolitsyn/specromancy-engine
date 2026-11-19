# Authoring pipelines

Start with the [release-documentation consumer](../../examples/release-documentation/README.md)
and [installation guide](installation.md). The example supplies a registry,
two read-only phases, canonical skills, templates, and a complete walkthrough.
The producer's implementation pipeline provides richer approval and repair
examples. Test-owned replacement fixtures independently verify replaceability;
they are not the consumer onboarding template.

Register each graph in mandatory `workflow/pipelines.toml`, with a unique ID
and a path under `workflow/pipelines/`. There is no default; use
`specromancy init DESCRIPTION --pipeline ID`. See
[Workflow customization](../../workflow/README.md) for add/edit/remove steps.

With the package installed in your environment, use `specromancy init DESCRIPTION
--pipeline ID` from the consumer root or a nested directory. Discovery recognizes
both `.git` directories and worktree marker files. From an unrelated directory,
use `specromancy --root /absolute/path/to/consumer init DESCRIPTION --pipeline ID`.
A non-Git consumer needs both `--root` and `allow_non_git = true` in its graph.
Installation supplies the engine and its four published schemas; author the
registry, graph, skills, templates, and validator schemas in the consumer project.
Nothing is implicitly loaded from the engine's source checkout or home directory.

Write repository-wide instructions in `workflow/instructions.md`. The generator
combines them with packaged harness templates, including the generic orchestrator.
See [Harness usage](harnesses.md) for the generator command and harness environment.

Pipeline files use TOML so Python 3.11 can load them without a dependency. A
pipeline declares schema version, identity, start phase, terminal outcomes,
artifact naming, Git policy, and an ordered `[[phases]]` array. Every phase
names a canonical skill, inputs, output, mutation policy, validator, gates, and
transitions.

## Add, delete, reorder, or replace phases

To add a phase:

1. Write the procedure in `workflow/skills/<name>/SKILL.md` with portable frontmatter.
2. Add any output template under `workflow/`.
3. Add `[[phases]]` with a unique lowercase identifier, the `skill` name and its `skill_source`.
4. route an existing transition to it and give it at least one transition;
5. make every symbolic input available on every incoming route;
6. Validate the graph and run its tests. The runtime can execute it before generating any adapters.

Delete a phase by removing all inbound transitions first, then its phase table,
skill, and unused template. Reordering table text alone does not change graph
behavior: change transition targets and, when necessary, `start`. The loader
rejects unreachable phases and unknown targets.

Replacing the whole workflow follows the same rules. The replacement fixture's
unrelated names and order are the contract test for this operation.

## Branches and bounded loops

Add one transition table per allowed outcome:

```toml
[[phases.transitions]]
outcome = "accepted"

[[phases.transitions]]
outcome = "rejected"
target = "transform"
max_traversals = 2
```

A transition without `target` must be listed in `terminal_outcomes`. A cycle
must be bounded by a positive `max_traversals` on the cyclic edge or a positive
`max_visits` on a phase that bounds the cycle. Limits count persisted visits or
edge traversals and block before creating an excess visit.

Set `pause = true` on a nonterminal transition to create a durable checkpoint:

```toml
[[phases.transitions]]
outcome = "validated"
target = "implement"
pause = true
```

The source visit completes and the target visit is prepared atomically, but the
run remains `paused` until `specromancy resume RUN_ID` releases it. Pauses are
independent from approvals and are rejected on terminal transitions. Omitting
`pause`, or setting it to `false`, preserves ordinary transition behavior and
the canonical hash of an otherwise unchanged version-1 pipeline.

## Skills and templates

Declare the skill identifier and its repository-relative procedure in each new phase:

```toml
[[phases]]
id = "inspect-changes"
skill = "inspect"
skill_source = "workflow/skills/inspect/SKILL.md"
# Add inputs, output, mutation policy, validator, gates and transitions here.
```

Start that UTF-8 Markdown file with portable frontmatter:

```markdown
---
name: inspect
description: Inspect the changes listed in the request.
---
```

`name` must equal `skill`. Several phases may reuse the same identifier and
source. Across registered graphs each identifier has one declared source and each resolved
file has one identifier. Resolve supporting references relative to the canonical
procedure file. Reserve `pipeline` and `specromancy-*` for orchestration and launch skills.
The reader accepts single-line string values for `name`, `description`, and
optional `license` and `compatibility`. Optional `metadata` holds a flat mapping
of string values indented two spaces. Quote values containing YAML punctuation
such as a colon followed by a space.

With `skill_source`, the procedure, template and validator files must all resolve
under the repository's actual `workflow/` directory. The directory itself must
not be a symlink. Descendant links can target files elsewhere inside it. Use
forward slashes and omit parent segments in `skill_source`. The CLI returns
the canonical procedure in `action.skill` and checks its bytes on continuation.

For an existing graph without `skill_source`, the runtime still loads
`.agents/skills/<skill>/SKILL.md`. Adapter generation requires explicit declarations in every registered graph. Adding the field changes the graph hash. Finish an
existing run with its original graph and procedure bytes, or retain its checkout
and start new runs in a separate checkout.

`output_template` is relative to the pipeline file. `../templates/result.md`
can reference shared `workflow/templates/`; multiple graphs may use the same
canonical skill or template.
The `.agents/skills/specromancy-*` namespace holds generated launch skills and
is not a phase-procedure customization surface. A Markdown validator can
declare `required_headings` and `heading_occurrence`; a JSON validator may use
the documented project-owned schema subset. Templates should contain every
required heading exactly once and meaningful placeholder content that a valid
artifact must replace.

JSON validator `path` (or `schema`) resolves relative to the pipeline file and
follows the same containment rule as the template. Legacy phases use the
consumer root as their resource boundary. The
`load_json_schema(path)` API still reads these project-owned files and rejects
unsupported keywords. The four published engine schemas are a separate package
resource contract, not artifact validators for that subset; see
[installed resources](../reference/contracts.md#installed-resources-and-consumer-roots).

## Embed the installed engine

Use an explicit absolute consumer root so the caller's working directory does
not select the project. Given a registered `shared` pipeline, this initializes a
run and reads its durable status through the public facades:

```python
from pathlib import Path
from specromancy_engine import Engine, RunStore, load_registry

root = Path("/absolute/path/to/consumer").resolve()
pipeline = load_registry(root).load("shared")
store = RunStore(root)
engine = Engine(pipeline, store)
response = engine.initialize("Record the consumer result.")
run_id = response["action"]["run_id"]
status = engine.status(run_id)
manifest = store.load(run_id)
```

`Engine(pipeline)` also constructs a store at `pipeline.repository_root` when
one is not supplied. For an existing run, load its recorded graph rather than
selecting today's registration, which might point somewhere else:

```python
from specromancy_engine import load_pipeline

saved = store.load(run_id, verify_artifacts=False)["pipeline"]
pipeline = load_pipeline(root / saved["path"], repository_root=root)
engine = Engine(pipeline, store)
status = engine.status(run_id)
```

The low-level `load_pipeline(path, repository_root=...)` API does not require a
registry. CLI commands continue to require one. Neither API executes a phase's
agent procedure: call `start_phase(run_id, phase_id)`, use its action packet to
produce the artifact, then call `validate(run_id, phase_id)`. Construct a
separate pipeline and store for each consumer; no new builder API is required.

## Approvals and stops

Declare stable kebab-case reason codes:

```toml
approval_conditions = ["external-side-effect", "material-scope-change"]
stop_conditions = ["insufficient-information"]
```

The phase skill explains when each code applies. It must call
`request-approval` or `block` rather than merely mentioning a concern in prose.
Changing or adding a reason changes the pipeline hash.

## Mutation policies

- `read-only` rejects every repository path change during the visit, including
  a second edit to a file that was dirty at visit start.
- `repository-write` records all changes but permits them.
- `allowlist` permits only paths matched by the phase's `allowlist` globs and
  rejects the rest.

CLI-owned `.specromancy/` files are outside repository mutation comparison.
Read-only phases may write their designated visit output there. Completed
outputs are immutable. In the release-documentation example the reviewed notes
stay in run storage; explicitly copying them into release docs is a user action
outside that lifecycle.
None of these policies grants permission to delete, reset, stage, or commit
work; repository instructions still apply.

## Validation commands

Commands are arrays, never shell strings:

```toml
[[phases.commands]]
argv = ["python", "-m", "unittest", "discover"]
timeout_seconds = 300
required = true
```

They run in order from the repository root. A required failure prevents phase
completion. Use explicit executables and arguments; shell operators, pipes, and
redirections are not interpreted.

## Regeneration and active runs

After changing `workflow/instructions.md`, a canonical skill, the registry, a pipeline or its
referenced templates/schemas, or CLI help
metadata, regenerate and check. A body edit can change only manifest provenance.
A frontmatter or source-path edit can also change the wrapper bytes. Run:

```bash
specromancy adapters generate
specromancy adapters generate --check
python -m unittest discover
```

A run stores its pipeline hash. Any pipeline change causes `resume`, `phase`,
and transition commands to reject that run with `pipeline-hash-mismatch`.
Approval records also become stale. The engine deliberately has no active-run
migration: finish the old run before editing its pipeline, restore the exact
old configuration to resume it, or initialize a new run under the new hash.
Never edit `run.json` to force compatibility.

Removing a registration disables new runs and removes unchanged generated
launch skills on regeneration. Keep original graph, skill, and template files
for active runs, which continue to resolve their persisted provenance. Removing
the files or moving the graph prevents continuation. Registry order and edits
to another graph do not change the selected run.
