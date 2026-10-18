# Stage 01 — Contract and native baseline

Status: planned. Depends on: none. Risk: low; characterization and decisions.

## Outcome

Establish the exact Windows support boundary and a reproducible failure list
before modifying the runtime. Preserve a clean Unix baseline and identify which
failures are engine defects, tooling assumptions, or platform-specific assertions.

## Intended files

- This directory's `evidence/01-contract-and-baseline.md` (new during execution).
- `tests/engine/unit/` and `tests/engine/contract/`: small reproductions used by
  the later stages; do not merge unconditionally failing tests into existing CI.
- Inspect `.github/workflows/tests.yml`, `tools/requirements-build.txt`,
  `tools/verify_distribution.py`, and `tools/distribution_smoke.py`.
- Inspect `hashing.py`, `artifacts.py`, `locking.py`, `git.py`, `commands.py`,
  `_runs/run_persistence.py`, `_adapters/adapter_ownership.py`, and the tests
  mapped in the [plan overview](README.md).

## Instructions

1. Record the implementation starting revision and existing local changes.
   Preserve unrelated work. Use disposable repositories for all probes; do not
   initialize a test run or change Git configuration in the producer checkout.
2. Provision CPython 3.11.15 and 3.14.4 through the existing pinned uv route.
   First verify the uv 0.11.27 catalog supplies native Windows x64 builds of both
   exact patches. Log the managed interpreter paths, not just `python --version`.
   If unavailable, record a deliberate provisioning/pin update with its upstream
   source and run the existing platforms again; do not substitute a different
   patch only on Windows or silently use runner Python.
3. Create a dedicated environment per interpreter, provision
   `tools/requirements-build.txt`, and install the checkout editable. For Windows,
   use `.venv\Scripts\python.exe` directly and add `.venv\Scripts` to the process
   `PATH`. Activation and execution-policy changes must not be prerequisites.
4. Run the current full suite and both installed/module entry-point help commands
   on native Windows. Attempt the current distribution verifier and record its
   explicit POSIX-only rejection separately from runtime failures. Run the full
   supported-platform suite and adapter checks as comparison evidence.
5. Make a failure table with test name, traceback/diagnostic, minimal reproduction,
   responsible file, intended stage, and expected correction. Do not group all
   failures under a single “Windows unsupported” entry. Reproduce at least:
   directory syncing during initialization, direct checkout-launcher invocation,
   mode-bit assertions, compatibility-fixture differences, and verifier paths.
6. Probe capabilities in temporary directories: regular file replacement; an open
   destination that blocks replacement; exclusive lock contention; symlink and
   junction creation; case-insensitive name collisions; Unicode paths; and paths
   containing spaces. Record the Windows image, volume type, Git settings, and
   whether the process is elevated. Hosted Windows runners run as administrator,
   so their capability result alone does not establish non-admin behavior.
7. Record the decisions below before starting the implementation stages. Keep
   the default decisions unless a native reproduction demonstrates a conflict;
   explain any change in the evidence and dependent stage instructions.

## Decisions to record

| Topic | Planned decision |
| --- | --- |
| Durability | Keep file flush/fsync, close-before-replace, and the current recovery protocol. Preserve POSIX directory fsync; explicitly omit unsupported directory syncing on Windows. Do not promise power-loss equivalence. |
| Paths | Stored relative paths remain POSIX syntax. Native Windows path constraints are checked before access; preserve valid existing POSIX configurations. Explicit CLI roots are native filesystem paths. |
| Locks | Retain exclusive lock files and manual stale-lock remediation. Test actual process contention. |
| Permissions | Keep POSIX mode assertions on POSIX; Windows inherits filesystem permissions. Do not equate `chmod(0600)` with a Windows ACL. |
| Commands | Preserve argument lists and `shell=False`. Native Python/executable invocation is the verified baseline. Human Windows validation commands target PowerShell 7. |
| Compatibility | Preserve original captures. Native mode differences need explicit Windows expectations and same-host replay; active cross-OS run migration is not promised. |
| Symlinks | No privilege requirement for ordinary use. Privileged link tests are distinct from core tests, with mandatory link coverage on a capable CI runner. |
| Versioning | No schema change, namespace change, new workflow policy, or automatic package-version bump. |

## Verification

Use the common commands from the overview after editable installation. For a
native baseline, the following PowerShell setup assumes the pinned uv executable
is already provisioned; repeat in a separate environment for the second version:

```powershell
$testPythonVersion = '3.11.15'
uv python install --no-bin $testPythonVersion
if ($LASTEXITCODE -ne 0) { throw 'Python provisioning failed' }
$testPython = (uv python find --managed-python $testPythonVersion).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Managed Python lookup failed' }
& $testPython -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed' }
$env:PATH = (Join-Path $PWD '.venv\Scripts') + [IO.Path]::PathSeparator + $env:PATH
python -m pip install -r tools/requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Build tooling installation failed' }
python -m pip install --no-index --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'Editable installation failed' }
python -m unittest discover
```

At this baseline stage, retain the nonzero discovery result and full output;
do not present this snippet as a passing Windows test command yet. A local
Windows machine or a temporary diagnostic CI branch can provide the evidence.
Stage 06 specifies the final required workflow; an early diagnostic run must
not be mistaken for the finished CI gate.

## Exit criteria and handoff

- Baseline results are recorded for both selected Windows interpreters, with
  supported-platform regression evidence and no unexplained environment fallback.
- Every observed failure has an owner stage and reproduction. Distinguish
  suspected issues discovered by inspection from demonstrated native failures.
- The durability, path, fixture, shell, and permission decisions are explicit.
- No runtime behavior or generated adapter bytes change in this stage.

If native execution is unavailable, finish the static inventory and mark this
stage's native evidence incomplete. Do not replace it with an `os.name` mock.
Continue code investigation, but do not claim the native baseline or support gate
is complete.
