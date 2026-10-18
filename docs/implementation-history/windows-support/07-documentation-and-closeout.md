# Stage 07 — Documentation and closeout

Status: planned. Depends on: 06. Risk: medium; accuracy of the support claim.

## Outcome

Document a reproducible native Windows workflow and close the change with
evidence for the final tree. Support statements must match actual runner,
interpreter, filesystem, shell, and user-permission coverage.

## Intended files

- `README.md`, `docs/guides/installation.md`, and
  `docs/guides/distribution-verification.md`.
- `docs/reference/cli.md`, `contracts.md`, `architecture.md`, and
  `harness-compatibility.md` where their guarantees or limitations need updates.
- `docs/guides/authoring-pipelines.md`, `docs/guides/harnesses.md`,
  `tests/README.md`, and `examples/release-documentation/README.md`.
- Canonical `.agents/skills/` or example skills only if invocation guidance
  needs correction; regenerate all affected manifest-owned adapters afterward.
- This plan's stage statuses, `evidence/07-documentation-and-closeout.md`, and
  `docs/implementation-history/README.md`.

## Instructions

1. Update the current “Windows is unverified” statement only after Stage 06 has
   real passing evidence. State the verified matrix explicitly; separate Python
   3.11+ metadata compatibility from the exact tested patches and OS versions.
   Preserve historical documents as historical results, including their prior
   Windows limitations.
2. Add PowerShell consumer and contributor instructions using native scripts
   paths. Prefer direct interpreter invocation so activation/execution policy is
   optional. Explain how to put the installed console command on the harness
   process's `PATH`; activating a terminal does not update an already-running GUI.
3. Keep Unix instructions intact and label shell-specific blocks. Document
   `specromancy`, `python -m specromancy_engine`, and `python bin/specromancy` in
   their appropriate installed/check-out contexts. Do not recommend direct
   extensionless shebang execution or a `python3` alias as a Windows prerequisite.
   Explain that the explicitly invoked source launcher works without installation,
   but generated action/harness commands still require the installed `specromancy`
   command on Windows. Merely adding the checkout's `bin` directory to Windows
   `PATH` does not provide that command.
4. Provide PowerShell equivalents for fresh artifact-directory creation, pinned
   provisioning, builds, exact-path verification, and retained logs. Avoid Bash
   heredocs, `source`, `mktemp`, and `$VAR` environment syntax in Windows blocks.
   Do not require a global execution-policy change or administrative privileges.
5. Explain relative forward-slash configuration paths versus native `--root`
   paths, reserved Windows names, LF byte integrity, and inherited permissions.
   Describe PowerShell human command rendering and the authoritative JSON argv
   contract. Explain configured batch/shell commands without implying they are
   automatically made portable by the engine.
6. Update durability/limitations precisely: file syncing and atomic replacement,
   manifest/event ordering and permitted recovery gap, manual stale-lock handling,
   no verified Windows directory-sync/power-loss equivalence, and no promised
   migration of an active mode-bound run between operating systems.
7. Keep generated adapter claims scoped to discovery files, deterministic bytes,
   and executed commands. Do not claim that every hosted/native agent product was
   tested on Windows just because the engine and adapter smoke suite passed.
8. Execute the Windows installation and consumer walkthrough as an ordinary user
   in an independent project. Use a root with spaces and Unicode. Verify init,
   status, phase action, output write, validation, approval/pause where configured,
   resume, and completion using a test-owned or documented example pipeline.
   Use the actual documented exit codes: action/approval/pause responses can be
   nonzero without being execution failures.
9. Verify the Python API example and the twelve generated wrapper invocations and
   two launch skills remain exercised by the existing packaging smoke suite.
   Add a focused executable-doc check for any new PowerShell walkthrough, without
   duplicating the engine's implementation in tests.
10. If claiming Windows 11 specifically, run the same ordinary-user smoke there
    and record edition/build, architecture, CPython, Git, PowerShell, filesystem,
    and outcomes. If no such host is available, retain the narrower verified
    Server 2025 CI statement and mark desktop evidence pending; do not invent it.

## Final verification

1. Install the final tree editable in the dedicated environments. Run focused
   documentation/consumer checks and the full suite:

   ```sh
   python -m unittest tests.packaging.test_release_documentation tests.shipped_configuration.test_consumer_example
   python -m unittest discover
   specromancy adapters generate --check
   python bin/specromancy adapters generate --check
   git diff --check
   ```

2. Build a fresh wheel and sdist from the final documented tree and run the
   distribution verifier. Documentation/example bytes are in the sdist, so an
   earlier artifact set is not sufficient after these edits.
3. Run all six CI jobs on the final revision. Compare counts and skip lists with
   Stage 01 and explain differences. Review original fixture hashes, any separately
   added Windows expectations, public signatures/schemas/CLI codes, and generated
   ownership/provenance. Confirm no unrelated files changed.
4. Review the completed changes against the repository instructions: standard
   library runtime, generic engine, canonical procedures, no unique adapter
   logic, immutable artifacts, mechanical read-only checks, stale-approval
   invalidation, validated atomic state changes with matching audit evidence,
   and unchanged repository-work ownership.
5. Record exact artifact paths/hashes, verifier logs, final CI links, native
   ordinary-user smoke evidence, remaining limitations, and any approved design
   deviations. Do not mark incomplete evidence as a passed test.

## Completion checklist

- [ ] All seven stage exit criteria satisfied and recorded.
- [ ] Native Windows full suite and direct/rebuilt-wheel gates pass on both
      selected Python versions; all existing platform jobs pass too.
- [ ] PowerShell instructions and independent consumer use are executed.
- [ ] Runtime errors preserve state and do not trigger permission repair,
      destination deletion, lock expiry, or repository cleanup.
- [ ] Original compatibility fixtures preserved; native differences explicit.
- [ ] Adapters are reproducible and have no handwritten platform logic.
- [ ] Current support statements match the available evidence and limitations.
- [ ] Final evidence identifies a single tested tree and fresh distributions.

Mark the overview and stage files complete only after these checks pass. Any
remaining work should be listed with its reproduction, impact, and verification
needed. Release publication and repository branch-protection changes are separate
operations; this plan ends with a reviewable, verified implementation.
