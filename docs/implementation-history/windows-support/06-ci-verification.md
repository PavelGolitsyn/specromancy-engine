# Stage 06 — Required CI coverage

Status: planned. Depends on: 05. Risk: medium; false-green and provisioning risks.

## Outcome

Make native Windows support a continuously enforced contract. Every pull request
and push runs the complete existing verification on Windows and retains the
Linux/macOS gates. Windows must not be a smoke-only or allowed-failure job.

## Intended files

- `.github/workflows/tests.yml`.
- `tools/requirements-build.txt` only for a reviewed provisioning correction.
- A small CI helper only if repeated path/build orchestration genuinely warrants
  it; prefer existing tools and short OS-specific steps over a new framework.
- Native integration tests from stages 02–05 and their explicit capability gate.
- `docs/guides/distribution-verification.md`, `tests/README.md`, and stage evidence.

## Required matrix

Retain the existing exact patches unless Stage 01 established a documented
cross-platform provisioning update:

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-24.04, macos-15, windows-2025]
    python: ['3.11.15', '3.14.4']
runs-on: ${{ matrix.os }}
```

This is **six required verification jobs**. Keep `push`, `pull_request`, and
`workflow_dispatch`, `permissions: contents: read`, and checkout credentials
disabled. Give jobs stable names including the OS and Python version. Do not
use `windows-latest`, remove an existing combination, or add `continue-on-error`.
GitHub documents the runner labels in its
[hosted-runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

## Instructions: provisioning and shells

1. Retain commit-pinned checkout and setup-uv actions and the reviewed uv version.
   If a pin must change, resolve it from the upstream repository at implementation
   time, record the SHA/version, and test every matrix entry. Do not invent action
   hashes in this plan or switch away from managed CPython silently.
2. Use explicit Bash provisioning for Linux/macOS and explicit `pwsh` provisioning
   for Windows. Resolve `uv python find --managed-python` for the requested exact
   version, create the venv, install pinned build tools, and install the checkout
   editable before testing. Do not depend on activated shell state persisting
   between workflow steps.
3. Add `.venv/bin` or `.venv\Scripts` to `GITHUB_PATH` using the correct shell and
   encoding. For Windows, for example:

   ```powershell
   $scripts = Join-Path $env:GITHUB_WORKSPACE '.venv\Scripts'
   $scripts | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
   & (Join-Path $scripts 'python.exe') --version
   if ($LASTEXITCODE -ne 0) { throw 'Dedicated interpreter failed' }
   ```

   Subsequent steps must print `sys.executable`, `sys.prefix`, platform/architecture,
   Git version, and build-tool versions. Verify these match the matrix; do not
   print complete environments or secrets.
4. Treat every native program's exit code as authoritative. In multi-command
   PowerShell steps, check `$LASTEXITCODE` immediately after each invocation or
   use a tested helper that raises on failure. `$ErrorActionPreference = 'Stop'`
   alone is not sufficient for all native-command failures. Avoid pipelines that
   replace the tested command's exit status with a successful log-printing command.
5. Use `$env:RUNNER_TEMP` on PowerShell and `$RUNNER_TEMP` on Bash, or build paths
   inside Python with `os.environ`. Quote each path. Do not reuse the current
   Bash `$RUNNER_TEMP` expansion in an implicit Windows PowerShell step.
   GitHub's [workflow shell reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
   defines the shell invocation behavior; make the workflow explicit.

## Required work in every matrix job

| Order | Gate | Failure condition |
| --- | --- | --- |
| 1 | Selected interpreter, Git, build tools, editable install | Missing/wrong tool or fallback interpreter |
| 2 | `python -m unittest discover` | Any failing core test; unexpected loss of coverage |
| 3 | `specromancy adapters generate --check` | Generated drift or canonical source inconsistency |
| 4 | `python bin/specromancy adapters generate --check` | Source launcher/import failure or drift |
| 5 | Fresh `python -m build --sdist --wheel --no-isolation` | Build failure or missing exact artifacts |
| 6 | `tools/verify_distribution.py` on both exact artifact paths | Archive failure, isolation failure, failed/skipped consumer test, rebuild failure |
| 7 | Final whitespace/generated-file/worktree checks | Verification unexpectedly changes tracked files |

Retain direct `bin/specromancy` shebang verification on POSIX in addition to the
portable source invocation. Use separate steps or explicit native-exit checks
for both adapter invocations so one cannot mask the other.

Build into a fresh job-owned path under the runner temporary directory. Pass
exact wheel/sdist filenames, and a new persistent verifier-log path. The verifier
must still rebuild offline and run both isolated consumer suites; a Windows wheel
install followed only by `--help` is not sufficient.

## Additional Windows checks

Run these on native Windows, at minimum in one target-interpreter job unless a
stage requires both. They may be included in full discovery if already covered;
do not rerun expensive suites just to create more check names.

- Actual PowerShell-rendered argv and an end-to-end validation command.
- A consumer root and artifact directory containing spaces and Unicode.
- Lock contention and replace/recovery tests using real Windows handles/processes.
- Junction and symlink ownership tests. Probe capability and require coverage
  on the designated runner; fail that job if the expected capability is absent.
  A local capability skip must not silently turn the CI safety check green.
- A fresh test-owned checkout with `core.autocrlf=true` verifies `.gitattributes`,
  canonical byte expectations, and adapter check mode. Do not renormalize or
  change the producer checkout as part of this test.
- Python 3.11 execution without relying on global UTF-8 mode, covering Unicode
  JSON/files/paths and the documented human-output behavior.

The hosted Windows image's privileges are not a product prerequisite. Preserve
an ordinary-user smoke result in Stage 07; do not make all user instructions
require Administrator or Developer Mode to accommodate link tests.

## Failure evidence and gate validation

1. Run a log-display step with `if: always()` in the correct native shell. Missing
   verifier logs after early provisioning failures should be reported as “not
   created”; the failed provisioning step must remain visible and failing.
2. Retain verifier and test logs as workflow artifacts with a newly verified,
   commit-pinned upload action. Use unique names per OS/interpreter and a bounded
   retention period such as 14 days. Upload only job-owned verification evidence,
   never whole workspaces, environments, or unrelated run directories.
3. Keep test counts/skips and image/interpreter details visible in the job summary
   or logs. The installed smoke runner must continue to reject skipped tests.
4. Deliberately inject a failing test, a missing wheel, and a native command failure
   before a succeeding command in a disposable diagnostic branch/workflow run.
   Confirm each makes the job red and preserves useful output. Remove diagnostic
   faults before final verification; retain links/results in stage evidence.
5. Run the final workflow on the actual implementation revision and record all
   six successful jobs plus artifact links. Workflow YAML inspection alone is
   not CI verification. If branch protection is managed separately, report the
   stable check names to configure; do not claim required repository rules were
   changed unless that separate change was authorized and performed.

## Exit criteria and handoff

- All six jobs pass full discovery, adapter checks, and both installed-artifact
  verifications on one identified revision.
- Windows execution is native, uses the pinned managed interpreter, and does not
  rely on Bash/WSL to hide invocation or path problems.
- Negative-gate rehearsals fail as expected, and success/failure evidence remains
  accessible after temporary consumer directories are cleaned up.
- No publishing credentials, package publication, or new runtime dependencies.

If Windows CI is still red, fix the responsible stage and rerun it. Do not merge
an allowed-failure job and label the platform supported.
