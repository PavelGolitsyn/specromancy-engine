# Stage 21 — Verify installed generation and close out

Status: **planned; not implemented**. Depends on Stages 16–20.
Category: integration, distribution verification, and documentation closeout.

## Objective

Prove the delivered release works in an unrelated consumer with no harness files,
and that its outputs remain reproducible, safe, and independent of one another.
The source checkout alone is insufficient evidence for release-owned templates.

This stage closes the canonical-source/all-harness baseline. The subsequent
[Stage 22](22-selective-harness-generation.md) adds persistent harness selection
and repeats the affected integration and distribution gates; completion here
does not establish that later feature's acceptance criteria.

## Verification matrix

| Scenario | Evidence required |
| --- | --- |
| Editable checkout, Python 3.11 and development Python | Focused and full tests, generated checks, recorded interpreter/version |
| Direct wheel installed outside source checkout | Templates are present; workflow-only consumer executes and generates |
| Wheel rebuilt from sdist, installed outside checkout | Same template bytes and same generated output/source hashes for equal inputs |
| Two different installation/consumer paths | No host absolute paths in manifest identities or generated content |
| Fresh consumer, no harness directories/root instructions | Configuration and runtime action work before generation; generation succeeds |
| Generated `.agents` and root `AGENTS.md` removed in disposable consumer | Check reports drift; regeneration reconstructs outputs with identical hashes |
| Claude/Copilot/OpenCode command surfaces used without `.agents` | Wrappers resolve CLI/actions and canonical workflow procedures; no generated cross-file prerequisite |
| Existing consumer with unowned root instructions/skills | Refusal preserves every file; documented migration resolves it explicitly |
| Upgrade from valid generator-v2 manifest | Existing owned files handled safely; newly claimed paths still require absence or actual ownership |
| Forged generator-v2 ownership of root instructions or ordinary `.agents` skills | Original v2 restrictions reject matching-hash claims before replacement or cleanup |
| Canonical source/dependency redirects through a generated path | Instructions, skills, registry/graphs, templates, and validators fail declared/resolved-boundary checks |
| Adapter CLI registry redirects to generated content containing valid or malformed TOML | Both generate and check reject at bootstrap before parsing target content; no output/manifest mutation |
| Valid pipeline A alongside an unrelated invalid or conflicting graph B | A validates, initializes, and resumes independently; registry-wide generation rejects B or the conflict |
| Schema-2 shared output attribution | Every path is owned once; consumer lists and target requirements agree, with all five targets enabled |
| Phase discovery wrapper and canonical supporting reference | Wrapper loads the named canonical procedure, contains no copied phase body, and anchors references at the source file |
| Reused canonical skill across phases/harnesses | Metadata name matches skill; source read/hash is deduplicated while required wrapper outputs remain complete |
| Canonical body-only edit after generation | Canonical source hash/manifest drift changes; wrapper bytes can remain identical |
| Legacy run and migrated new run | Legacy provenance preserved; new actions use workflow sources; no automatic state migration |

Use deterministic CLI/subprocess tests for wrappers and launch instructions, not
an assertion that live harness UIs were exercised. Record any actual host smoke
tests separately. This work does not add platforms or promise Windows support
beyond whatever the separately implemented platform plan has verified.

## Work sequence and intended files

1. Extend the existing `tools/verify_distribution.py` and
   `tools/distribution_smoke.py` consumer scenarios. Copy only the source-only
   example's required files. Assert the absence of `.agents` and root `AGENTS.md`
   before configuration/init/generation rather than deleting an accidentally
   copied prerequisite and masking setup coupling.
2. Install each distribution in its own clean environment and run from outside
   the producer checkout, with no `PYTHONPATH` or editable checkout leakage.
   Exercise the installed console entry point and `python -m specromancy_engine`.
3. Verify package resource inventories, generated manifest inputs, output path
   ownership, and content equality across direct/rebuilt wheels. Record artifact
   hashes. Include a missing-template failure with no partial output writes.
4. Add integration regressions in `tests/packaging/test_distribution.py`,
   `test_consumer_roots.py`, and `test_release_documentation.py`; reuse existing
   setup/process helpers. Avoid duplicating the entire adapter unit matrix here.
5. Run the full suite on Python 3.11 and the available development interpreter,
   each after a dedicated editable install. Run generated checks after the final
   documentation/source edits. Perform the installed-artifact gate after final
   package-included documentation edits as well.
6. Audit active docs and source direction: packaged generic templates + workflow
   sources → rendering → manifest-owned harness outputs. The only legacy source
   resolution is the explicit runtime compatibility branch from Stage 18.
   Exercise registry-symlink rejection before parsing through both generate and
   check, plus one forged-v2 ownership rejection through the installed CLI,
   not just editable unit tests. Assert no output/manifest mutation.
   Run generation/check for thin wrappers from the
   source-only example with a canonical relative supporting reference; distinguish
   verified path/content behavior from any unperformed live-agent invocation.
7. Record results, actual changed files, deviations, remaining limitations, and
   any distribution or live-harness gaps; update the refactoring index status.

## Commands

Within each dedicated environment, install before testing. Use the repository's
existing pinned build-tool setup for artifact creation, then run:

```sh
python -m pip install -e .
python -m unittest discover
specromancy adapters generate --check
python bin/specromancy adapters generate --check
git diff --check
```

The existing installed-artifact verifier interface is:

```sh
python tools/verify_distribution.py --wheel /absolute/path/to/built.whl --sdist /absolute/path/to/built.tar.gz --log /absolute/path/to/new-verification-log.json
```

Replace placeholders with actual newly built artifacts; record exact commands,
interpreter versions, test counts/skips, hashes, and log locations. The verifier's
current supported execution platforms remain the baseline. Do not report planned
commands or earlier historical test counts as fresh evidence.

## Final acceptance checklist

- [ ] All canonical repository policy and phase procedures are under `workflow/`.
- [ ] All generic harness/orchestration templates ship in the engine release.
- [ ] Every supported generated file, including root `AGENTS.md` and `.agents`
  skills, is reproducible and recorded in the manifest.
- [ ] The generator requires neither `.agents` nor root `AGENTS.md` to exist.
- [ ] Generated outputs never enter source hashes or new runtime skill identities.
- [ ] All captured repository sources, including indirect dependencies, pass the
  declared/resolved workflow boundary; package/ownership reads remain distinct.
- [ ] Historical manifest versions retain their original ownership restrictions,
  with forged new-path claims rejected before any writes or cleanup.
- [ ] Canonical skill names/paths are unambiguous, complete procedure bytes remain
  hashed, and thin wrappers neither copy phase bodies nor lose required outputs.
- [ ] Unowned files and modified stale outputs are protected; cleanup stays within
  validated manifest ownership and never invokes repository Git mutations.
- [ ] Python 3.11+, no third-party runtime dependencies, and generic engine policy
  boundaries are preserved.
- [ ] Public configuration, CLI/action, ownership, migration, and packaging
  contracts are documented; focused/full and installed-distribution gates pass.
- [ ] Old artifacts/events and approved-output invalidation retain their existing
  integrity guarantees; no runtime correctness depends on chat history.
- [ ] Temporary old adapter code is removed; unrelated refactors are absent.

Close out only when these checks have evidence. If a defect is outside this
scope, record its reproducer and follow-up separately instead of expanding this
change into a storage, configuration-framework, or harness-platform rewrite.
