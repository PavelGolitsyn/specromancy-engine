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

Run manifests and audit events each use schema version 2. To continue a
version-1 run, keep its producing engine, original graph and recorded resource
bytes together. Initialize a separate run when adopting the new engine.
Adding `skill_source` changes the graph hash. Replacing the old procedure with a
wrapper changes the prepared visit's recorded skill hash.

When upgrading from an all-target manifest, first save the desired harness list.
Selecting all five preserves the previous output set. A smaller selection retires
unchanged owned files that the project no longer needs.

Before generation, move hand-written root instructions to
`workflow/instructions.md` and phase procedures into `workflow/skills/`.
Update relative references, add the source declarations, and bring referenced
templates and validators inside `workflow/`. Preserve any custom instructions
from the former generic launch skill in the authored workflow before relocating
that file. Keep the previous adapter manifest. The generator validates it using
its original ownership rules and reports conflicts at occupied unowned paths,
even if their contents match. Review the resulting manifest and run check mode.

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
