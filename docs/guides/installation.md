# Install the engine in a consumer project

Python 3.11 or newer is required. The distribution **specromancy-engine** provides
the **specromancy_engine** Python package and **specromancy** executable, with no
third-party runtime dependencies. Installation supplies the generic engine and
four published schemas. Your project supplies its workflow configuration,
instructions, and skills; these are not installed defaults. Installing the
engine does not create a workflow or launch an LLM.

## Install from PyPI

From your consumer project root, create and activate a dedicated environment,
then install from PyPI:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install specromancy-engine
specromancy --help
python -m specromancy_engine --help
```

Keep `.venv/` ignored. Ensure the harness inherits this environment's `PATH`;
activating a terminal does not update an already-running GUI process. See
[Harness usage](harnesses.md) for command environments and generated adapters.
Before starting a run, [supply your consumer configuration and skills](#supply-consumer-configuration-explicitly).

## Obtain a local wheel

For local builds or installation without PyPI, a maintainer can build from a
producer checkout in a dedicated build environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tools/requirements-build.txt
python -m build --sdist --wheel --no-isolation --outdir dist
```

The separately provisioned toolchain includes the pinned build backend declared
in `pyproject.toml`; these are build dependencies, not engine runtime dependencies. The result is
`dist/specromancy_engine-<version>-py3-none-any.whl`, where `<version>` comes from
`project.version` in `pyproject.toml`. Transfer that wheel to the
consumer. The consumer needs no engine source or editable install. The
[distribution verification guide](distribution-verification.md) documents the
repeatable wheel and sdist gates and links their executed evidence.
Verify the wheel hash against its build evidence before installation. `bin/specromancy` and
`adapters/generate.py` are producer-checkout conveniences; do not copy them or
the engine source into each consumer project.

## Install a local wheel

From the consumer project root (which may be a non-Python project), substitute
the actual wheel path and version in the command below:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --no-deps "/absolute/path/to/specromancy_engine-<version>-py3-none-any.whl"
specromancy --help
python -m specromancy_engine --help
```

Keep `.venv/` ignored. Ensure the harness inherits this environment's `PATH`;
activating a terminal does not update an already-running GUI process. See
[Harness usage](harnesses.md) for command environments and generated adapters.

## Python project dependency

In an existing Python project's `pyproject.toml`, merge this entry into its
existing dependency list; preserve its other metadata and dependencies.
Replace `<version>` with the published release you intend to pin:

```toml
[project]
dependencies = ["specromancy-engine==<version>"]
```

Install your project and resolve the engine dependency from PyPI:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Alternatively, make a local wheel available when installing the project:

```sh
python -m pip install --find-links /absolute/path/to/wheels .
```

Pip uses its configured package indexes by default; `--find-links` adds the local
wheel directory as another source. Use `--no-index` only if the engine, your
project's other dependencies, and its build backend are all supplied locally.
Do not add the engine's source directory to `PYTHONPATH`.

With the release-documentation example configured, this runnable API example
initializes a separate run, reads persisted status, and starts the emitted phase:

<!-- public-api: tested with the release-documentation consumer -->
```python
from pathlib import Path
from specromancy_engine import Engine, RunStore, load_registry

root = Path.cwd().resolve()  # Run from the explicitly selected consumer root.
pipeline = load_registry(root).load("release-documentation")
store = RunStore(root)
engine = Engine(pipeline, store)
response = engine.initialize((root / "sample-changes.md").read_text(encoding="utf-8"))
run_id = response["action"]["run_id"]
status = engine.status(run_id)
manifest = store.load(run_id)
action = engine.start_phase(run_id, response["action"]["phase"])["action"]
assert action["mutation"]["policy"] == "read-only"
print(action["output"]["absolute_path"])
# An agent writes the designated output using action's inputs and skill.
# Then: response = engine.validate(run_id, action["phase"])
```

The API returns actionable response dictionaries; `EngineError` reports expected
failures. It does not call an LLM or author the output. For an existing run, use
the recorded pipeline path, as shown in [Pipeline authoring](authoring-pipelines.md#embed-the-installed-engine).
The [consumer walkthrough](../../examples/release-documentation/README.md)
executes both phases through completion using the CLI and a deterministic agent.

## Supply consumer configuration explicitly

Copy the complete [release-documentation example](../../examples/release-documentation/README.md)
into a new directory, including `.gitignore`, or author
the following resources in your existing project:

| Resource | Your responsibility |
| --- | --- |
| `workflow/adapters.toml` | Save the harnesses this project uses before generating or checking adapters |
| `workflow/instructions.md` | Preserve and merge the repository instructions here |
| `workflow/pipelines.toml` | Merge an explicit unique registration; there is no default |
| `workflow/pipelines/<id>.toml` | Own phases, policies, outcomes, and input selectors |
| `workflow/templates/` | Supply every template referenced by your graph |
| Referenced validator schemas | Place graph-relative dependencies under `workflow/` |
| `workflow/skills/<skill>/SKILL.md` | Declare each procedure with `skill_source` and match its frontmatter name to `skill` |
| `.gitignore` | Ignore `.specromancy/`, local environments, and development outputs |

Use a real Git repository for this example. Specify `--root /absolute/consumer`
when invoking from elsewhere, especially while inspecting an example inside a
producer checkout: otherwise Git discovery can select the producer. A non-Git
consumer needs both explicit `--root` and graph `allow_non_git = true`.

The engine has no implicit scaffolding step. Installing it never silently
overwrites `AGENTS.md`, skills, a registry, or harness files. After reviewing
your configuration, explicitly run `specromancy adapters generate` and
`specromancy adapters generate --check`. Generate before starting a read-only
phase because adapter generation changes repository files. Keep the manifest
with its generated files. Resolve conflicts using the
[documented ownership model](harnesses.md#ownership-and-conflicts), preserving
existing instructions before regeneration. Do not manufacture ownership by
editing the manifest.

The package supplies the harness templates and generic orchestrator. The example
selects Claude and OpenCode. Edit its `workflow/adapters.toml` for your project,
or set `harnesses = []` for CLI-only use. Runs and pipeline configuration
validation work without this file. Adapter generation and check require it.

## Upgrade an existing consumer

Pipeline graphs use schema 3. Run manifests and events each use schema 2.
Finish older runs with their producing engine and original workflow resources,
or initialize a separate run after upgrading. Move procedures and dependencies
under `workflow/`, declare each phase's `skill_source` and both approval lists,
and convert validators and commands to tables. The registry and harness
selection keep their independent schema version 1. See the
[graph upgrade instructions](authoring-pipelines.md#regeneration-and-active-runs).

### Rebuild adapters from a previous ownership format

Generation and check accept ownership manifest schema 3 with generator 5.
Both return adapter drift (11) for earlier identities, including when the
desired harness list is empty. Upgrade in a fresh directory.

1. Preserve the original project, including its manifest, generated files,
   local edits and run data. Use the producing engine's check in that tree
   to identify edits you want to keep.
2. Copy the authored workflow into a clean destination. Merge hand-written
   instructions into `workflow/instructions.md` and custom procedures into
   `workflow/skills/`. Update relative references, graph source declarations,
   templates and validators. Leave the old manifest and generated outputs in
   the original tree.
3. Set `workflow/adapters.toml` to the desired harness list. In the clean
   directory, run `specromancy adapters generate`, then
   `specromancy adapters generate --check`.
4. Compare the new manifest's paths and file contents with the preserved tree.
   Review additions, removals, edits and collisions with project files. Adopt
   the reviewed outputs and their manifest together, then run check in the
   adopted tree.

Deleting the old manifest alone leaves occupied output paths unowned, even if
their bytes match. Editing version fields or hashes cannot establish ownership.

### Exercise an upgrade in disposable consumers

Run these examples from the producer checkout with its pinned build environment
active. Set `CANDIDATE_WHEEL` to the absolute path of the wheel you built.
Both examples use the same shell and create their projects and environments
under a new temporary directory.

**Finish a run with its producing release.** The local tag supplies the
0.1.3 source, example graph, procedures, templates and validator declarations.
The first process starts a run. A second process resumes it from disk with the
same installed wheel and original inputs.

```sh
set -e
producer=$PWD
demo=$(mktemp -d)
mkdir "$demo/prior"
git archive --output="$demo/prior.tar" v0.1.3
tar -xf "$demo/prior.tar" -C "$demo/prior"
python -m build --wheel --no-isolation --outdir "$demo/wheels" "$demo/prior"
python -m venv "$demo/old-env"
"$demo/old-env/bin/python" -m pip install --no-index --no-deps \
  "$demo/wheels/specromancy_engine-0.1.3-py3-none-any.whl"
cp -R "$demo/prior/examples/release-documentation" "$demo/old-project"
git init --quiet "$demo/old-project"
(
  cd "$demo/old-project"
  . "$demo/old-env/bin/activate"
  specromancy adapters generate
  python - > "$demo/old-id" <<'PY'
from pathlib import Path
from specromancy_engine import Engine, load_registry

engine = Engine(load_registry(Path.cwd()).load("release-documentation"))
print(engine.initialize(Path("sample-changes.md").read_text())["action"]["run_id"])
PY
  python - "$(cat "$demo/old-id")" <<'PY'
import sys
from pathlib import Path
from specromancy_engine import Engine, load_registry

run_id = sys.argv[1]
engine = Engine(load_registry(Path.cwd()).load("release-documentation"))
for phase, output in (
    ("draft-release-notes",
     "## Summary\nReport export and retry fixes.\n## Changes\nAdded CSV export.\n"
     "## Upgrade Notes\nRename report_timeout to report_timeout_seconds.\n"),
    ("review-release-notes",
     "## Verdict\nApproved.\n## Findings\nClaims match the sample.\n"
     "## Verification\nChecked the CSV change and setting rename.\n"),
):
    assert engine.resume(run_id)["action"]["phase"] == phase
    action = engine.start_phase(run_id, phase)["action"]
    Path(action["output"]["absolute_path"]).write_text(output, encoding="utf-8")
    engine.validate(run_id, phase)
status = engine.status(run_id)["status"]
assert status["status"] == "completed"
print(run_id, status["terminal_result"]["outcome"])
PY
)
```

**Start a separate run with current inputs.** The current example supplies
the converted authored files. Generate adapters before starting its first
visit. The two projects and their run directories remain independently usable.

```sh
python -m venv "$demo/new-env"
"$demo/new-env/bin/python" -m pip install --no-index --no-deps "${CANDIDATE_WHEEL:?set the absolute candidate wheel path}"
cp -R "$producer/examples/release-documentation" "$demo/new-project"
git init --quiet "$demo/new-project"
(
  cd "$demo/new-project"
  . "$demo/new-env/bin/activate"
  specromancy adapters generate
  specromancy adapters generate --check
  python - <<'PY'
from pathlib import Path
from specromancy_engine import Engine, RunStore, load_registry

root = Path.cwd()
store = RunStore(root)
engine = Engine(load_registry(root).load("release-documentation"), store)
action = engine.initialize((root / "sample-changes.md").read_text())["action"]
run_id = action["run_id"]
assert store.load(run_id)["schema_version"] == 2
print(run_id, action["phase"], action["visit_status"])
PY
)
```

## Contributor environment

Contributors editing engine source use a dedicated editable installation from
the producer checkout, separate from the consumer routes above:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover
specromancy adapters generate --check
```

Editable tests alone do not prove a wheel works in another project. See the
[test guide](../../tests/README.md) for independent consumer verification and
the [public contracts](../reference/contracts.md) for supported interfaces and state handling.
