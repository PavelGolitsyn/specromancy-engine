# Windows support implementation plan

Status: **planned; implementation has not started**. Prepared on 2026-10-18
against `b587ac8cd195dcbf308b61e28ec5047323cc56f1`.

Add native Windows support to the existing engine, CLI, source launcher, and
distribution verification. Keep the implementation small, preserve the existing
Unix behavior, and prove the result with real Windows CI. This directory contains
execution instructions, not evidence that Windows is already supported.

## Scope and support target

| Surface | Planned contract |
| --- | --- |
| Runtime | CPython 3.11+, standard library only; no new runtime dependency |
| Native Windows | x64 Windows on local NTFS, with Git for Windows available for Git-backed pipelines |
| Automated Windows baseline | GitHub Actions `windows-2025`, Python 3.11.15 and 3.14.4, native processes and PowerShell 7 |
| Existing platforms | Retain `ubuntu-24.04` and `macos-15` on the same two interpreter versions |
| Installed invocation | `specromancy` / generated `specromancy.exe`, and `python -m specromancy_engine` |
| Checkout invocation | `python bin/specromancy` everywhere; retain direct shebang invocation on POSIX |
| Data formats | Existing version-1 schemas, canonical JSON, relative POSIX paths, hashes, and CLI exit codes |
| Filesystem semantics | Same-file replacement, exclusive run locks, immutable outputs, recovery, approval invalidation, and ownership enforcement |
| User documentation | Tested PowerShell installation, development, consumer, and verification instructions |

The first delivery does not promise network-share durability, cloud-synchronized
run storage, arbitrary Windows versions/architectures, native `cmd.exe` command
rendering, or long-path configurations that have not been exercised. WSL and Git
Bash are not substitutes for native Windows verification. A Server 2025 CI result
does not by itself verify Windows 11; record a separate Windows 11 smoke test
before making that specific desktop claim. Hosted agent-harness behavior remains
separate from generated adapter and command verification.

Moving an active run between operating systems is outside this change: repository
snapshots contain native mode observations. Preserve old records and their hash
integrity; do not rewrite them to simulate portability. Source/configuration and
distribution portability are in scope.

## Stage sequence

Execute sequentially, keeping each stage independently reviewable. The first
four stages remove runtime and test blockers; the fifth verifies real packages;
the sixth makes the complete verification mandatory in CI.

| Stage | Deliverable | Depends on |
| --- | --- | --- |
| [01 — Contract and native baseline](01-contract-and-baseline.md) | Reproductions, support decisions, Windows failure inventory | None |
| [02 — Persistence and locking](02-persistence-and-locking.md) | Portable file durability boundary without changing the commit protocol | 01 |
| [03 — Paths and filesystem ownership](03-paths-and-ownership.md) | Safe native path materialization, aliases, and junction handling | 02 |
| [04 — Invocation, Git, and portable tests](04-invocation-git-and-tests.md) | Native CLI/commands, reliable snapshots, deterministic fixtures, green full suite | 03 |
| [05 — Installed distribution verification](05-distribution-verification.md) | Direct wheel and sdist-rebuilt wheel pass outside the checkout on Windows | 04 |
| [06 — Required CI coverage](06-ci-verification.md) | Six full verification jobs, native shell smoke, retained failure evidence | 05 |
| [07 — Documentation and closeout](07-documentation-and-closeout.md) | Executable Windows guidance and evidence-backed support claim | 06 |

## Evidence from this planning pass

The checkout was clean before this work. The existing dedicated `.venv` uses
Python 3.14.4 on macOS 26.6.2 arm64. These commands were executed successfully:

```sh
.venv/bin/python -m pip install --no-index --no-build-isolation -e .
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m unittest discover
PATH="$PWD/.venv/bin:$PATH" .venv/bin/specromancy adapters generate --check
PATH="$PWD/.venv/bin:$PATH" bin/specromancy adapters generate --check
```

The full suite passed **283 tests in 47.738 seconds**, with no reported skips.
Both adapter checks reported that generated files were current. The editable
installation reused the already-provisioned pinned build backend. No Windows,
Linux, Python 3.11, or fresh distribution verification was executed in this
planning pass. Stage 01 must collect those implementation baselines.

| Inspected evidence | Consequence | Stage |
| --- | --- | --- |
| `artifacts._fsync_directory` and `RunPersistence._fsync_directory` open directories with `os.open(..., os.O_RDONLY)` | POSIX directory syncing is embedded in core writes | 02 |
| `RunLock` already uses exclusive creation, file syncing, close, and unlink | Verify native behavior; do not replace it with platform lock libraries | 02 |
| Path normalization rejects backslashes and drive prefixes but does not cover Windows reserved components | Separate stored path syntax from native path safety | 03 |
| Adapter ownership checks use `is_symlink()` and string-keyed path ownership | Audit junctions, case aliases, and preflight-before-write behavior | 03 |
| Launcher tests directly execute the extensionless `bin/specromancy` | Use interpreter invocation on Windows and preserve POSIX shebang coverage | 04 |
| Snapshot tests require executable-bit changes; persistence tests require mode `0600` | Separate genuine POSIX assertions from cross-platform correctness | 04 |
| Compatibility fixtures use `chmod(0644)`, text-mode writes, and POSIX path expectations | Preserve frozen fixtures while adding explicit native expectations | 04 |
| Human action rendering uses `shlex.join` | Add a defined PowerShell rendering contract without changing JSON argv | 04 |
| Verifier rejects `os.name != 'posix'`, assumes `bin/python`; smoke runner assumes unsuffixed console script | Port the complete installed-artifact gate | 05 |
| Installed `build==1.6.1` metadata requires `colorama` on Windows, absent from the build-tool pin file | Complete the reproducible build-only toolchain | 05 |
| CI has four Ubuntu/macOS jobs, Bash provisioning, `.venv/bin`, and Bash environment syntax | Add native Windows jobs and explicit per-platform shell handling | 06 |

## Design rules for every stage

1. Keep phase names and workflow policy in `workflow/` and canonical procedures
   in `.agents/skills/`. No Windows-specific workflow fork or adapter-only logic.
2. Prefer a few internal functions at existing filesystem/process boundaries.
   Do not introduce a platform service framework, change public imports, or
   reorganize the engine as part of this task.
3. Preserve atomic manifest replacement followed by event append under the run
   lock. A permitted one-revision gap recovers once. This is not a transaction
   across two files and must not be described as one.
4. Preserve byte hashes. LF/CRLF conversion of an approved output must still
   invalidate approval. Do not normalize consumer content to make tests pass.
5. Preserve CLI ownership: run directories, manifest-owned adapter files, and
   the existing permitted adjacent temporary files. Never add runtime Git
   mutation, permission repair, deletion of user files, or stale-lock expiry.
6. Preserve version-1 records and Unix behavior. Any deliberate Windows-only
   rejection or presentation difference must be documented and tested. Do not
   update original golden records to conceal a regression.
7. Use real native Windows processes. Mocks may exercise error branches but
   cannot establish Windows support. Never mark a broken core test as a
   platform skip or use `continue-on-error` to obtain a green support gate.
8. Only regenerate adapters when canonical inputs change. Verify the generated
   diff, update provenance through the generator, and run check mode again.

## Verification and evidence policy

Before tests, install the current checkout into a dedicated environment with
`python -m pip install -e .`. With the pinned tools already provisioned, the
existing offline equivalent is `python -m pip install --no-index
--no-build-isolation -e .`. Put that environment's scripts directory on `PATH`.

After each implementation stage run its focused checks, then:

```sh
python -m unittest discover
specromancy adapters generate --check
python bin/specromancy adapters generate --check
git diff --check
```

The existing supported-platform suite must remain green at every stage. During
01–03, run full Windows discovery and record the remaining known failures by
test name; those stages are not Windows-support completion gates. Stage 04
requires a green native full suite. Stage 05 adds a green Windows distribution
gate. Stage 06 requires all six CI combinations. Stage 07 must verify the final
documented tree again because documentation is included in the sdist.

At execution time add `evidence/NN-<stage>.md` under this directory. Record the
starting and tested revisions, changed files, actual commands, OS/image,
interpreter and Git versions, results/counts/skips, CI links, artifact hashes
where relevant, decisions/deviations, and remaining failures. Planned commands
are not test results. Mark a stage complete only after its exit criteria pass.

## External contracts informing the plan

These references were checked during planning; recheck provisioning availability
when implementing CI rather than silently changing a pinned interpreter.

- Python documents Windows virtual environments with a `Scripts` directory and
  interpreter invocation without activation: [Python 3.11 venv](https://docs.python.org/3.11/library/venv.html).
- File syncing is available on Windows, while `chmod` does not provide Unix mode
  semantics: [Python 3.11 os](https://docs.python.org/3.11/library/os.html).
- Windows names have reserved components, aliasing, and namespace rules:
  [Microsoft file naming](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).
- GitHub lists `windows-2025` as an x64 hosted runner:
  [hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
- uv's downloadable Python catalog is tied to the uv release:
  [uv Python versions](https://docs.astral.sh/uv/concepts/python-versions/).

Current behavior remains documented in [public contracts](../../reference/contracts.md)
and [distribution verification](../../guides/distribution-verification.md).
