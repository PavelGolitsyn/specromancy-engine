# Specromancy Engine

Specromancy Engine is a dependency-free Python 3.11+ framework for portable,
artifact-based agent workflows. A declarative pipeline and canonical skills
define the work; a small CLI validates transitions and persists recoverable run
state independently of any harness conversation.

Version 0.1.1 targets Linux and macOS. The release verification matrix covers
Ubuntu 24.04 and macOS 15 with Python 3.11.15 and 3.14.4. Windows is unverified
and is not claimed as supported in this release.

## Use the engine in another project

Install version `0.1.1` from PyPI into your project's Python environment:

```sh
python -m pip install specromancy-engine==0.1.1
specromancy --help
```

Follow the [installation guide][installation] to create an isolated
environment, add the engine to an existing Python project's dependencies, or
install a local wheel. The
[release-documentation consumer][consumer-example]
provides an executable two-phase example.

Your project explicitly supplies its registry, graphs, templates, instructions,
and skills. The engine emits actions and verifies agent output; it does not
launch an LLM, provide credentials, generate prose, or publish results.

## Contributor quickstart

From a Git checkout, create a dedicated development environment and install
the package in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
bin/specromancy init "describe the requested change" --pipeline implementation
bin/specromancy status RUN_ID
bin/specromancy resume RUN_ID
python -m unittest discover
bin/specromancy adapters generate --check
```

`init` returns the run ID and next action. Follow the emitted action packet and
use its exact output path, skill, mutation policy, and final validation command.
Runtime data is written only under ignored `.specromancy/runs/` storage.

The `specromancy-engine` version `0.1.1` package provides the `specromancy` console
command and `python -m specromancy_engine`. The checkout wrappers
`bin/specromancy` and `adapters/generate.py` also work without installation as
producer-checkout conveniences. Consumers install the dependency; they do not
copy engine source or launchers into their projects.
Python consumers import `specromancy_engine`. Run and event formats use schema
version 1. See the [public contracts][contracts] for supported
interfaces, persistence, and ownership rules.

## Customize the workflow

Register pipelines in `workflow/pipelines.toml` and keep their graphs under
`workflow/pipelines/`. Every new run requires `--pipeline ID`; there is no default.
Adapters generate a `specromancy-<id>` launch skill for each registration.
The editable graphs and shared artifact templates live in [`workflow/`][workflow-directory].
These top-level resources configure this repository's own development workflow;
they are not automatically installed consumer defaults.
Phase procedures live in [`.agents/skills/`][skills-directory] for native harness
discovery, and repository-wide agent constraints live in [`AGENTS.md`][agent-instructions].
The Python package under `src/specromancy_engine/` is the generic engine, not a workflow
customization surface. Start with the
[`workflow/README.md`][workflow-guide] customization map.

## Documentation

- [Documentation and repository map][documentation]
- [Consumer installation][installation]
- [Distribution verification and CI][distribution-verification]
- [Publishing a release][releasing]
- [Architecture][architecture]
- [CLI reference][cli]
- [Pipeline authoring][pipeline-authoring]
- [Harness usage][harnesses]
- [Public contracts][contracts]
- [Historical plans and refactoring records][history]

The engine intentionally does not launch harnesses, migrate active runs between
pipeline versions, provide remote storage or distributed locking, authenticate
approvers, or implement parallel graph joins. See the architecture document for
the complete limitations and safety boundary.

[installation]: docs/guides/installation.md
[consumer-example]: examples/release-documentation/README.md
[contracts]: docs/reference/contracts.md
[workflow-directory]: workflow/
[skills-directory]: .agents/skills/
[agent-instructions]: AGENTS.md
[workflow-guide]: workflow/README.md
[documentation]: docs/README.md
[distribution-verification]: docs/guides/distribution-verification.md
[releasing]: docs/guides/releasing.md
[architecture]: docs/reference/architecture.md
[cli]: docs/reference/cli.md
[pipeline-authoring]: docs/guides/authoring-pipelines.md
[harnesses]: docs/guides/harnesses.md
[history]: docs/implementation-history/README.md
