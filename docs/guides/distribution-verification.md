# Verify a distribution before release

Use a Git checkout with Python 3.11 or newer and Git on `PATH`. The minimum
verification interpreter is 3.11.15; the development interpreter is 3.14.4.
CI is configured for Ubuntu 24.04 and macOS 15 on both interpreters. Windows is
unverified and is not claimed as supported. Other Python 3.11+ versions satisfy the package metadata but are not individually verified here.

## Provision and build

Use [uv 0.11.27](https://github.com/astral-sh/uv/releases/tag/0.11.27) to provision
the same managed CPython builds as CI, then create a dedicated environment.
Repeat with `TEST_PYTHON_VERSION=3.14.4` in a separate environment. Provisioning
downloads the interpreter and build tools; tests and the verifier never download
them. The pinned backend in `pyproject.toml` and the
complete frontend/backend toolchain in `tools/requirements-build.txt` must agree.

```sh
TEST_PYTHON_VERSION=3.11.15
uv python install --no-bin "$TEST_PYTHON_VERSION"
test_python="$(uv python find --managed-python "$TEST_PYTHON_VERSION")"
"$test_python" -m venv .venv
. .venv/bin/activate
python -m pip install -r tools/requirements-build.txt
python -m pip install --no-index --no-build-isolation -e .
python -m unittest discover
specromancy adapters generate --check
bin/specromancy adapters generate --check
```

Activation puts the selected interpreter first on `PATH` for shebang tests.
Managed-only interpreter selection avoids silently using a different Python
distribution preinstalled on a runner. The exact patch versions are preserved
across operating systems; verify their managed builds exist for every target
architecture when updating the matrix or uv pin.
For an offline setup, provision the pinned tool wheels separately, then add
`--no-index --find-links /absolute/build-tools` to the tooling installation.
The runtime has no third-party requirements.

Choose a new output directory for each build and keep its exact artifact paths:

```sh
ARTIFACT_DIR="$(mktemp -d /tmp/specromancy-artifacts.XXXXXX)"
python -m build --sdist --wheel --no-isolation --outdir "$ARTIFACT_DIR"
python tools/verify_distribution.py \
  --wheel "$ARTIFACT_DIR/specromancy_engine-0.1.1-py3-none-any.whl" \
  --sdist "$ARTIFACT_DIR/specromancy_engine-0.1.1.tar.gz"
```

`python -m build` is the build frontend. Specifying both `--sdist --wheel`
builds each directly from the checkout; the verifier independently rebuilds the
source archive. `--no-isolation` is appropriate here because the declared build
requirements were explicitly provisioned. The verifier checks the pinned tools
and asks the frontend to check all declared wheel build requirements before its
own offline, non-isolated rebuild. Do not pass a glob that can select stale
versions. After changing included files, build a fresh artifact set; the gate
compares archives with the current checkout and deliberately rejects stale ones.

## README build metadata

`README.md` is the single source for the repository README and PyPI description.
`setup.py` calls the build-only, standard-library `build_readme.py` helper through
the normal setuptools build hooks. `python -m build` and editable installs derive
the description and project URLs automatically; no separate generation command
or generated README file is needed. The source README is never modified.

Use Markdown reference links for local README destinations:

```markdown
[Installation][installation]
[Workflow][workflow]
![Diagram][image-diagram]

[installation]: docs/guides/installation.md
[workflow]: workflow/
[image-diagram]: images/diagram.png
```

Definitions must be on a single line outside code blocks. Directory destinations
must end in `/`; image reference labels must start with `image-`. Files use GitHub
`blob/v<version>/`, directories use `tree/v<version>/`, and images use
`raw/v<version>/`. Fragment-only references point to the tagged README. Titles,
query strings, and fragments are preserved; angle brackets support paths with
spaces. External URLs and fenced or indented code blocks are left unchanged.
Local inline links are rejected with authoring guidance; inline external links
are allowed. These conventions apply only to the root README.

The version comes from `[project].version`, and the repository URL comes from
`[tool.specromancy-build].repository` in `pyproject.toml`. The helper also derives
Homepage, Documentation, and Issues metadata. It needs neither Git nor network
access, and does not inspect linked paths: some targets intentionally exist only
in the full repository. Both helper files are included in the sdist so a rebuild
produces the same description, while neither is included in the installed wheel.
The release workflow creates or verifies the matching tag after verification
and before uploading, as described in [the release guide](releasing.md).
The converter does not check remote availability.

## Verifier contract

`tools/verify_distribution.py --wheel PATH --sdist PATH [--log NEW_PATH]` is a
standard-library orchestration script. Missing artifacts, schemas, Git, or build
tooling are failures, never skips. It exits 0 only when both installed artifacts
pass. The optional log path must not exist; otherwise a persistent temporary log
is created. The printed log path survives both success and failure, including
subprocess output, test counts, interpreter details, artifact hashes, and runtime
inventory. Work directories and temporary venvs are removed when verification
finishes. Keep the original artifact set and the log for release review.

The verifier inspects exact wheel paths, runtime bytes, and metadata, including
version, Python requirement, license, generated README and project URLs, entry
point, and empty runtime dependencies. It enumerates every runtime module and all four schemas. Wheel
contents are limited to `specromancy_engine` source/schema data and normal
`.dist-info` metadata. Tests, producer/consumer configurations, skills, wrappers,
run data, caches, environments, and unrelated projects fail the archive boundary.

`MANIFEST.in` defines a deliberate sdist allowlist: build metadata and README
helpers, runtime source and schemas, README, license, the complete release-documentation example
(including hidden skills and ignore rules), and current guides and reference
documentation. Setuptools adds normal sdist metadata. Tests, historical documents,
producer workflows, generated adapters, and developer tools are not included.
The sdist is a consumer/build artifact, not a full developer checkout. Some
repository-oriented documentation links require the Git checkout. Run the
verifier from the checkout; extracted sdists prove rebuilding and consumer use.

Before extraction, the gate rejects path traversal, duplicate members, symlinks,
hardlinks, special files, unexpected roots, and missing/unexpected files. It
extracts only checked regular files into its fresh temporary tree. It builds a
wheel there without a source-checkout import fallback or network installation.

Each wheel gets its own fresh venv and exact-path `pip install --no-index
--no-deps`. The runner uses `python -I -B`, clears inherited Python/Git/Pip
configuration, disables user sites, and runs outside the producer checkout. It
checks every imported module's installed origin, version agreement, missing
legacy namespace, schemas, and both CLI entry points before exposing only the
copied test bundle to imports. The rebuilt wheel uses the **sdist's** example and
installation guide in its consumer tests.

The copied suite covers explicit/discovered consumer roots, two-project
isolation, custom pipeline completion, public API calls, immutable outputs,
read-only enforcement, and adapter invocation. Original compatibility records
are replayed without refreshing their expected bytes or hashes, including old
approvals and exactly-once recovery. Adapter tests verify upgrades from original
owned files, collision protection, and repeated generation with identical bytes.
There is no claim that archive bytes are reproducible across timestamps or hosts;
the gate checks contents and metadata instead.

The installed suite also runs the engine orchestration contracts: pending and
granted approval invalidation, interrupted approval continuation, and skill and
template provenance enforcement. These distinguish an engine-only installation
change from editing a consumer's configuration or approved artifact.

## CI and evidence

[The workflow](../../.github/workflows/tests.yml) uses commit-pinned actions,
read-only repository permission, dedicated environments, and the same commands
on both interpreters/platforms. It prints the retained verifier log even on
failure. There are no publishing credentials, release steps, or artifact uploads.
The separate, manually triggered [release workflow](releasing.md) builds one
candidate artifact set, runs these gates across the same matrix, and publishes
the verified files to TestPyPI and PyPI using Trusted Publishing. It retains
the packages and verifier logs as Actions artifacts. The ordinary test workflow
does not publish.
The pinned `astral-sh/setup-uv` action installs uv 0.11.27; uv provisions CPython
on every matrix entry. This avoids relying on GitHub's separate `setup-python`
catalog, which does not supply macOS Python 3.11.15. Environment creation,
editable installation, tests, and builds continue to use standard Python/pip
commands. uv is a provisioning tool, not a runtime or package build dependency.
The pins were checked against upstream references at implementation time; review
and update them and the build-tool pins deliberately together with verification.

Historical build results and provisioning decisions are retained in
[implementation history](../implementation-history/README.md). Those artifact
hashes and test results describe their original development builds; verify a
fresh artifact set for the current checkout using the commands above.
