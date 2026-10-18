# Stage 04 — Invocation, Git, and portable tests

Status: planned. Depends on: 03. Risk: medium/high; command contracts and fixtures.

## Outcome

Make the full suite pass on native Windows while preserving meaningful Unix
coverage. Verify installed/module/source invocation, exact argument handling,
read-only enforcement, byte integrity, and usable PowerShell instructions.

## Intended files

- `src/specromancy_engine/actions.py`, `commands.py`, `git.py`, and `cli.py` only
  where native reproductions require changes.
- `bin/specromancy` only if needed; its existing Python body is already usable
  through an explicit interpreter. Do not add a parallel `.bat` implementation.
- `.gitattributes` (new): deliberate LF policy for repository-owned text.
- `tests/engine/contract/test_launcher.py`, `test_release.py`, `test_cli.py`,
  `test_safety.py`, `test_compatibility.py`, and `compatibility_support.py`.
- `tests/engine/unit/test_git.py`, `test_run_persistence.py`, relevant command
  and CLI tests; `tests/packaging/test_consumer_roots.py` and
  `test_release_documentation.py`.
- Existing fixture writers under `tests/engine/` and shipped-configuration tests
  where they assume host newline, encoding, permissions, or shebang execution.
- `tests/README.md`, the compatibility-fixture README, and current CLI/contracts
  documentation for intentional platform differences.

## Instructions: launch and command behavior

1. Locate installed scripts through the active interpreter's scripts directory;
   use `specromancy.exe` on Windows. Verify both console and module entry points
   from an unrelated working directory, a nested consumer directory, and paths
   containing spaces/Unicode. Check the selected interpreter and import origin.
2. Exercise `python -S bin/specromancy` and `python -S adapters/generate.py` in
   fresh source exports on every OS. Retain a distinct POSIX direct-shebang test.
   Do not make Windows depend on file associations, `python3` aliases, Bash, or a
   producer launcher on the consumer's `PATH`.
3. Preserve `final_validation_command` as the existing JSON argv list and keep
   validation execution as `subprocess.run(list(argv), shell=False, ...)`.
   Use `sys.executable` in test-owned Python commands. Do not convert argv into
   shell strings or implicitly translate configured `python3` into another tool.
4. Define Windows human-readable `Validate:` output as PowerShell 7 syntax.
   Use a narrow formatter: the call operator for the executable and literal
   single-quoted arguments with embedded apostrophes doubled. Keep POSIX
   `shlex.join` output unchanged. Document the selected shell; do not use
   `subprocess.list2cmdline` as if it were a PowerShell quoting function.
5. Test rendered commands by executing them through native `pwsh -NoProfile`
   against a test-owned executable/argument recorder, including spaces,
   apostrophes, `$`, `&`, parentheses, empty arguments, and backslashes. Also
   execute a real rendered validation command. Template-token parsing with
   `shlex.split` alone does not prove Windows shell behavior.
6. Preserve required/optional failures, timeout behavior, output byte limits,
   redaction, and command-output paths. Test native child processes for success,
   nonzero exit, missing executable, timeout, and raw stdout/stderr capture.
   Keep process-tree termination improvements outside this change unless an
   observed Windows blocker requires a separately specified correction.
7. Document that Windows can dispatch `.bat`/`.cmd` through its command processor
   even with `shell=False`. Do not add automatic shell wrapping or claim those
   scripts have the same literal-argument semantics as native executables. The
   verified baseline uses Python/native executables; pipeline authors own any
   explicit shell invocation. See [Python subprocess](https://docs.python.org/3.11/library/subprocess.html#security-considerations).

## Instructions: bytes, Git, and permissions

1. Add scoped `.gitattributes` rules for tracked source/configuration/docs,
   extensionless launchers, generated text, and compatibility fixtures so a
   Windows checkout retains intended LF bytes. Keep binary files unaffected.
   Do not run a blanket renormalization or change user Git configuration.
   Verify attributes with Git and a fresh temporary checkout using
   `core.autocrlf=true`; setting autocrlf false after checkout is insufficient.
   See [Git attributes](https://git-scm.com/docs/gitattributes).
2. Make fixture writes deterministic with explicit UTF-8 and `newline='\n'` or
   byte writes when their hashes/expected bytes matter. Restore frozen file
   contents as exact UTF-8 bytes. Do not normalize real runtime input or mask
   CRLF edits when checking approval or immutable-artifact hashes.
3. Audit default `read_text`/`write_text` and `subprocess(..., text=True)` calls.
   Specify encoding where the data format defines it. Exercise Unicode requests,
   roots, branch names, diagnostics, and redirected output on Python 3.11 without
   assuming global UTF-8 mode. Preserve the CLI's existing ASCII-escaped JSON
   contract and caller-supplied text streams. If human output needs a fallback,
   implement it only at the stream boundary and test it explicitly.
4. Preserve byte-based Git file enumeration and content hashing. Handle Git's
   UTF-8 paths without the Windows locale corrupting names, and keep native
   filesystem paths out of serialized snapshot keys. Retain HEAD/branch/index
   observations and detection of already-dirty file changes.
5. Keep snapshot modes as native observations; do not replace all Windows modes
   with a fabricated POSIX value. Split executable-bit assertions from the
   combined content/rename test. Windows tests must cover an observable read-only
   attribute change where applicable and always cover content, additions,
   deletions, renames, staged changes, HEAD changes, and branch changes.
6. Preserve POSIX `0600` permission assertions in persistence tests. Windows
   checks assert the actual creation/write/lock behavior and documented inherited
   permissions, not a pretend ACL guarantee. Test fixture cleanup may restore
   its own read-only attributes; runtime code must not repair user permissions.
7. Make temporary Git repositories independent of user/global identity, newline,
   signing, and hook settings without modifying any external Git config. Keep
   deliberate CRLF and case tests separate from deterministic baseline fixtures.

## Compatibility-fixture policy

The current `states.json` includes mode observations and their resulting hashes;
`chmod(0644)` cannot establish identical native Windows observations. Handle this
explicitly, not by deleting mode fields or ignoring hashes in comparisons:

1. Keep every original fixture unchanged and retain exact POSIX lifecycle replay.
   Run host-independent canonical/schema/adapter comparisons on every platform.
2. Add separately named, reviewed Windows state expectations for the same
   deterministic scenario. Document each allowed difference: native mode values
   and the manifest/event hashes that necessarily depend on them. Content bytes,
   revision/sequence order, approval bindings, and outcomes must remain identical.
3. Validate the relationship between fixture sets structurally and verify each
   expected hash chain independently. Tests must load fixed expected records,
   never regenerate expected results from the implementation under test.
4. Normalize only known machine-specific response fields such as absolute roots
   and interpreter locations. Handle their native separators deliberately; never
   blanket-replace backslashes in arbitrary strings, stored paths, or hashes.
5. On Windows, verify original records can still be read and the historical
   one-revision gap recovered without rewriting their snapshots. Continue the
   native Windows lifecycle against its matching expectations. Do not silently
   promise approval/read-only continuity for a POSIX run moved to Windows.
6. Exercise the Windows records and actual native snapshot behavior on both
   target interpreters. Document capture commands and review the diff before
   accepting a Windows fixture; a broad fixture refresh is not acceptable.

## Test coverage and skip policy

Run launcher/CLI tests, Git snapshot tests, compatibility tests, engine safety and
orchestration tests, and consumer tests, followed by full discovery. Suggested
focused commands:

```sh
python -m unittest tests.engine.contract.test_launcher tests.engine.contract.test_release tests.engine.contract.test_cli
python -m unittest tests.engine.unit.test_git tests.engine.unit.test_run_persistence
python -m unittest tests.engine.contract.test_compatibility tests.engine.contract.test_safety tests.engine.contract.test_engine_orchestration
python -m unittest tests.packaging.test_consumer_roots tests.packaging.test_release_documentation
```

New command/rendering/path tests must be included too. No test should download
tools or invoke an interactive shell profile. Keep support helpers small and
record their transitive imports for the copied distribution bundle in Stage 05.

Use platform-specific assertions within tests where semantics differ. Only tests
requiring an unavailable filesystem privilege/capability may skip locally, with
an explicit reason. Required CI must provision and execute the native safety
coverage. Preserve the distribution smoke runner's existing failure on skipped
installed-consumer tests; do not weaken it to accommodate a test organization issue.

## Exit criteria and handoff

- Full discovery passes on native Windows with both target interpreters; existing
  Linux/macOS coverage remains green. No unexplained skips or fixture changes.
- Byte hashes still detect LF-to-CRLF approval drift, and read-only enforcement
  still catches dirty content and Git metadata changes.
- Installed, module, source-export, and actual PowerShell command tests pass.
- Adapter check mode remains deterministic and all generated changes, if any,
  come from canonical inputs and the generator.
- Remaining Windows work concerns distribution orchestration/CI/docs, not known
  runtime or core-test failures.
