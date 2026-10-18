# Stage 05 — Installed distribution verification

Status: planned. Depends on: 04. Risk: medium; isolation and release guarantees.

## Outcome

Run the existing complete distribution gate on Windows: inspect the exact wheel
and sdist, safely extract and rebuild the sdist offline, then verify both wheels
in independent environments outside the producer checkout. Editable tests alone
must not establish Windows support.

## Intended files

- `tools/verify_distribution.py`: environment, interpreter paths, provisioning
  checks, archives, subprocess logging, and platform guard.
- `tools/distribution_smoke.py`: installed console executable, origins, copied
  suites, and encoding.
- `tools/requirements-build.txt`: complete pinned build-only toolchain.
- `tests/packaging/test_distribution.py`, `test_consumer_roots.py`, and
  `test_release_documentation.py`; the copied test helpers/fixtures from Stage 04.
- `docs/guides/distribution-verification.md`, `tests/README.md`.
- Inspect `pyproject.toml` and `MANIFEST.in`; change them only if a demonstrated
  packaging omission requires it, not merely to add an OS label.

## Instructions

1. Replace the verifier's POSIX-only rejection with verified native Windows
   handling. Create each consumer venv with the selected interpreter and locate
   its interpreter as `Scripts/python.exe` on Windows or `bin/python` on POSIX.
   Do not choose another `python` from the user's global `PATH`.
2. In the installed smoke runner, locate the console script using that venv's
   scripts directory and the Windows `.exe` suffix. Keep module and console help
   equivalence checks, package-origin checks, schema enumeration, empty runtime
   dependencies, and legacy-namespace absence.
3. Complete the build-tool pins. The inspected `build==1.6.1` metadata requires
   `colorama` when `os_name == 'nt'`; the current requirements file omits it.
   Select and verify a compatible exact version during implementation. Prefer an
   unconditional **build-only** pin in the existing simple `name==version` file,
   keeping its verifier parser and offline checks straightforward. This does not
   add an engine runtime requirement. Record why the toolchain changed and verify
   it on all three OSes.
4. Preserve the environment isolation boundary: clear inherited Python, Git,
   Pip, and Specromancy configuration; disable user sites, global/system Git
   config, and network package installation. Retain Windows process essentials
   such as `SystemRoot`, temporary-directory settings, and the environment needed
   to locate Git's own helpers. Do not replace the environment with a Unix-only
   minimal dictionary or expose its values in logs.
5. Construct `PATH` with `os.pathsep`, the selected environment, and verified Git
   locations. Preserve support for native Git worktree markers and two independent
   consumer roots. Do not add producer `src`, `bin`, or editable metadata to the
   copied test bundle or import path.
6. Make logging and control files explicitly encoded. Capture diagnostics without
   allowing a locale decode error to hide the subprocess's real failure. Python
   children that need UTF-8 can be given an explicit interpreter option; remember
   that `-I` ignores `PYTHON*` environment settings. Keep log files available after
   failure and close all handles before temporary directory cleanup on Windows.
7. Update `copy_bundle` for every new helper and native compatibility fixture
   imported by the selected tests. Keep an explicit test/fixture inventory and
   retain the direct-wheel and sdist-example distinction. A missing helper must
   fail clearly, not silently reduce the copied suite.
8. Preserve archive allowlists and byte comparisons against the current checkout.
   Extend negative archive tests for Windows alias forms: case collisions,
   device names, trailing dots/spaces, drive/UNC syntax, and alternate streams.
   Reject unsafe/duplicate destinations before any extraction. Preserve existing
   traversal/link/special-file rejection; do not delegate to unrestricted
   `extractall` or trust archive permission metadata.
9. Run each consumer in a fresh venv with exact-path
   `pip install --no-index --no-deps`, using isolated Python outside the checkout.
   Require successful tests with no skipped installed-consumer cases. Keep
   missing Git/build tools/artifacts as failures. The copied bundle must exercise
   lifecycle completion, approvals, recovery, read-only enforcement, adapters,
   immutable artifacts, and resource provenance on native Windows.
10. Add a real verification run from an artifact/output directory containing
    spaces and Unicode. Preserve the evidence log and artifact hashes. Use a new
    directory and log path for each run; do not glob stale versioned artifacts.

## Verification

Run focused archive and consumer tests, then the full suite and adapter checks:

```sh
python -m unittest tests.packaging.test_distribution tests.packaging.test_consumer_roots tests.packaging.test_release_documentation
python -m unittest tests.engine.contract.test_compatibility tests.engine.contract.test_engine_orchestration
```

Provision the pinned tools separately, build a fresh artifact set, and execute
the verifier on each target Windows interpreter. The platform-neutral commands
below use placeholders for newly selected absolute paths; substitute them as
single arguments, with native shell quoting:

```text
python -m build --sdist --wheel --no-isolation --outdir <NEW_ARTIFACT_DIRECTORY>
python tools/verify_distribution.py --wheel <EXACT_WHEEL_PATH> --sdist <EXACT_SDIST_PATH> --log <NEW_LOG_PATH>
```

The expected artifacts for the current version are
`specromancy_engine-0.1.0-py3-none-any.whl` and
`specromancy_engine-0.1.0.tar.gz`. Read the actual project version at execution
time; do not bump it or quietly select a different artifact to satisfy this plan.

Verify controlled failure for missing wheel, stale/wrong runtime bytes, missing
schemas, unsafe archive entries, missing tools, wrong pinned tool versions, and
an installed-consumer test failure. Tests should use synthetic archives or
subprocess seams for these negative cases; do not make unit tests fetch tools.

## Exit criteria and handoff

- Both Windows interpreters pass the full direct-wheel and sdist-rebuild gate.
- The same gate remains green on existing supported platforms after the shared
  verifier/toolchain changes.
- Logs identify exact Python/tool versions, artifact hashes, origins, runtime
  inventory, test counts, and both successful installed-consumer executions.
- No runtime dependencies, producer source leakage, archive-boundary expansion,
  skip-based success, or network fallback is introduced.
- A failure retains useful diagnostics and closes handles without hiding the
  original error behind a cleanup exception.

Do not remove an isolation check to make Windows pass. Correct the environment,
paths, copied bundle, or native runtime defect responsible for the failure.
