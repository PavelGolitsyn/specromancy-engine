# Stage 21 — Verify installed generation and close out

Status: **complete, verified 2026-11-20**. Depends on Stages 16–20.
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

- [x] All canonical repository policy and phase procedures are under `workflow/`.
- [x] All generic harness/orchestration templates ship in the engine release.
- [x] Every supported generated file, including root `AGENTS.md` and `.agents`
  skills, is reproducible and recorded in the manifest.
- [x] The generator requires neither `.agents` nor root `AGENTS.md` to exist.
- [x] Generated outputs never enter source hashes or new runtime skill identities.
- [x] All captured repository sources, including indirect dependencies, pass the
  declared/resolved workflow boundary; package/ownership reads remain distinct.
- [x] Historical manifest versions retain their original ownership restrictions,
  with forged new-path claims rejected before any writes or cleanup.
- [x] Canonical skill names/paths are unambiguous, complete procedure bytes remain
  hashed, and thin wrappers neither copy phase bodies nor lose required outputs.
- [x] Unowned files and modified stale outputs are protected; cleanup stays within
  validated manifest ownership and never invokes repository Git mutations.
- [x] Python 3.11+, no third-party runtime dependencies, and generic engine policy
  boundaries are preserved.
- [x] Public configuration, CLI/action, ownership, migration, and packaging
  contracts are documented; focused/full and installed-distribution gates pass.
- [x] Old artifacts/events and approved-output invalidation retain their existing
  integrity guarantees; no runtime correctness depends on chat history.
- [x] Temporary old adapter code is removed; unrelated refactors are absent.

Close out only when these checks have evidence. If a defect is outside this
scope, record its reproducer and follow-up separately instead of expanding this
change into a storage, configuration-framework, or harness-platform rewrite.

## Execution record

Verified from base revision `ce5fa8a` on macOS 26.6.2 arm64. Each interpreter
had a dedicated editable installation and two further clean wheel environments.
All counts below are from this run. All four installed consumer suites passed
with zero skips, as did both focused and full top-level suites.

| CPython | Focused | Full discovery | Direct wheel | Wheel rebuilt from sdist |
| --- | ---: | ---: | ---: | ---: |
| 3.11.15 | 43 | 367 | 93 | 93 |
| 3.14.4 | 43 | 367 | 93 | 93 |

Both installed entry points worked outside the checkout. Each installation
verified 65 runtime files, including the seven adapter templates. The example
produced a byte-identical schema-2 manifest and 23 verified output files for
five targets from 16 canonical inputs. The producer's own manifest covers 27
outputs. Both the installed and checkout launchers passed check mode on both
interpreters. The final whitespace check passed.

| Artifact or identity | SHA-256 |
| --- | --- |
| Direct wheel | `573dc64f04e00c68067e2908fe1fe289f26e9f44241106f54b424633cdee79d1` |
| Source archive | `23c68d51ba05a4c8a1fa6a027fbc49f063da41d24e5dde157d16149174e4b643` |
| Rebuilt wheel, both runs | `6512e852738048026cb63eeac240cafad5ec1f3739a1b2428125751dbe087b69` |
| Example manifest, including trailing newline | `b00e0e4826c0de5952dc45d4b33680d1a327b47d967b56f23d1080acb521cb08` |
| Example canonical source | `9ad8471d31ce07f285be5804f20d478a342a528a521c2ae5084013502f361d53` |

### Changes and coverage

- `tools/verify_distribution.py` copies the ten authored example files by name,
  checks for producer and installation paths in generated bytes, compares the
  two installed manifests and logs the common input and output hashes.
  `tools/distribution_smoke.py` checks actual on-disk hashes, input identities
  and target attribution. Making the installed phase template unavailable in
  the disposable environment produced exit 11 and an unchanged consumer tree.
- `tests/packaging/test_distribution.py` checks that local generated files stay
  out of the consumer bundle. `test_consumer_roots.py` removes root instructions
  and shared skills, verifies read-only drift reporting, then executes rendered
  Claude, Copilot and OpenCode commands against the installed CLI. Generation
  restores every output hash and the original manifest bytes. A separate case
  relocates unowned instructions and a procedure before retrying generation.
- `tests/packaging/test_release_documentation.py` checks a matching-hash forged
  v2 claim through both CLI modes and completes an upgrade from the frozen valid
  v2 fixture. A body-only edit in a disposable copy of the example changes the
  source hash while preserving wrapper bytes. Both wrappers identify the same
  procedure as the action packet, and its relative link resolves to the draft
  template. The example also starts a draft in a fresh workflow-only consumer.
- The installed gate includes the existing multi-pipeline CLI contract. It
  rejects both valid and malformed redirected registry TOML before parsing,
  preserves the tree, and exercises valid runs alongside invalid registrations.
  The full suite covers indirect dependency redirects, shared skill reads,
  modified stale outputs, legacy provenance, recovery and approval invalidation.
- The audit of active guides, references, workflow and engine source found the
  runtime compatibility lookup for an omitted `skill_source` in
  `_config/config_phase_parser.py`. The generator reads workflow declarations
  and package resources. Its harness-path reads serve ownership and drift
  checks. The changed documentation comprises the distribution verification
  guide, this execution record and the refactoring index.

### Commands and retained evidence

The following commands use the actual build-tool cache, environments, artifacts
and log names for this run. Existing pinned tool wheels allowed offline installs.
The verifier writes a text log. Its temporary rebuild and installation trees
are removed on exit.

```sh
work=/private/tmp/specromancy-verification-21.zZbxLs
tools=/private/tmp/specromancy-stage21.56Kjbp/build-tools
/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3.11 -m venv "$work/v311"
python3.14 -m venv "$work/v314"
for v in 311 314; do
  "$work/v$v/bin/python" -m pip install --no-index --find-links "$tools" -r tools/requirements-build.txt
  "$work/v$v/bin/python" -m pip install --no-index --no-build-isolation -e .
done > "$work/install.log"

for v in 311 314; do
  (
    . "$work/v$v/bin/activate"
    python -m unittest tests.packaging.test_distribution tests.packaging.test_consumer_roots tests.packaging.test_release_documentation tests.engine.contract.test_multi_pipeline > "$work/focused$v.log" 2>&1
    python -m unittest discover > "$work/full$v.log" 2>&1
  )
done

"$work/v314/bin/python" -m build --wheel --sdist --no-isolation --outdir "$work/artifacts" > "$work/build.log" 2>&1
for v in 311 314; do
  (
    . "$work/v$v/bin/activate"
    python tools/verify_distribution.py \
      --wheel "$work/artifacts/specromancy_engine-0.1.3-py3-none-any.whl" \
      --sdist "$work/artifacts/specromancy_engine-0.1.3.tar.gz" \
      --log "$work/distribution$v.log"
    specromancy adapters generate --check
    python bin/specromancy adapters generate --check
  )
done
git diff --check
```

The wheel and sdist were built after the distribution guide edit. The local
logs record the unpacked runtime inventories, build tools, tests and per-file
hashes. Live harness UIs, Linux and Windows were outside this execution.
Persistent harness selection remains in Stage 22.
