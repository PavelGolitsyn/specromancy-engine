# 28. Verify current fixtures, upgrades, and release gates

**Executed locally on 2026-11-24.** The current reference and installed release
gate cover the contracts below. The hosted CI matrix remains pending.

## Work

1. Consolidate the current lifecycle, graph identity, diagnostics, CLI responses,
   and generated ownership expectations under clearly named current-contract
   fixtures. Update [test discovery and documentation](../../../tests/README.md),
   fixture helpers, imports, and the explicit module and fixture lists in
   [verify_distribution.py](../../../tools/verify_distribution.py). Use direct,
   deterministic expected records for the current formats. Eliminate golden
   tests that transform old expected bytes, compare two obsolete captures, or
   pin private delegates. Preserve current same-format replay, crash recovery,
   integrity, ownership and canonicalization coverage.
2. Keep the smallest authentic old specimens needed to test refusal, with origin,
   version and expected diagnostic. Use a disposable copy for each test. Retire
   redundant historical captures from the active suite and distribution test
   bundle. If historical evidence links to a retired file, retain the evidence
   separately or link to the file at its recorded revision. Keep original
   measurements, hashes and release records intact.
3. Extend the existing contract tests to compare writer version tags, schema
   constants, packaged schema declarations where available, and independent
   expected records for each versioned surface. Include supported, previous
   incompatible, future and malformed versions on read paths. For output-only
   schemas, assert the version and shape at the public entry points. Verify
   that current records with invalid nested values produce controlled errors.
   Reviewers classify compatibility from the actual change and prior contract.
   A test that compares two constants cannot detect an omitted version bump.
4. Update [installation](../../guides/installation.md), authoring, harness,
   architecture, CLI and [distribution guidance](../../guides/distribution-verification.md)
   wherever they still promise old schemas or migration. Give two executable
   upgrade examples in disposable consumers. Finish an old run with its pinned
   engine, original graph, skills, templates and validators. Start a separate
   run with the new engine, current authored inputs and freshly generated
   adapters. Use an already installed prior release or a locally built prior
   artifact for the historical demonstration. The ongoing release gate needs
   only the current candidate and the negative fixtures.
5. Verify the [release checklist](../../guides/releasing.md) and generated
   contributor instructions cover any future 0.x release, including patch
   updates. Review the Stage 23 inventory against the final diff. Record the
   actual format versions, deliberate API removals, retained current features
   and end-user upgrade steps in the current reference. Close this plan with
   the tested revision, environment, commands, pass/skip counts and artifact
   hashes.

## Verification and acceptance

- [x] Run the shared stage gates and the source-export and consumer tests from
  a dedicated editable installation. Build the wheel and sdist from the final
  tree using the repository's pinned tooling. Follow the existing
  [distribution verification procedure](../../guides/distribution-verification.md)
  with the actual artifact paths on Python 3.11 and the development interpreter.
- [ ] Exercise the existing CI platform matrix. The requested local-only scope
  excludes pushing these changes to GitHub Actions.
- [x] In both the direct wheel and sdist-rebuilt wheel, load the packaged
  schemas, run the shipped release-documentation example to completion, and
  compare generated adapters and manifests for the same selected harnesses.
  Exercise action and transition approval in a test-owned graph declaring both.
  Exercise obsolete-run refusal before recovery, graph rejection on init/resume,
  and obsolete adapter refusal before replacement or stale deletion. Compare
  files byte-for-byte on the rejection paths.
- [x] Execute the upgrade examples and retain results. The new release's
  positive tests use current inputs. Historic specimens have identifiable
  provenance and explicit refusal assertions.
- [x] Reconcile the index and active guides with the measured results. Every
  cross-release support claim found in the final audit points to a current
  public contract or to clearly dated historical evidence. Future maintainers
  can find the standing rule from the repository instructions and release guide.

## Execution record

Tested the Stage 28 working tree based on
`e218dffdc983b92c8754eb1a3e1efac5bd9560a9`. Compared the Stage 23 inventory
with release `v0.1.3` (`d0bd655`), development baseline `f265780` and the
candidate. Stages 24–27 changed the run/event and output contracts to 2, the
graph to 3, and ownership to 3/generator 5. Registry and selection remain at
1. Stage 28 changes the tests, distribution verifier and documentation. The
candidate package version is 0.1.4.

The [current version table and API replacements](../../reference/contracts.md#current-format-versions)
give the consumer action for each surface. The installed suite exercises both
approval kinds on one graph, immutable outputs, read-only enforcement, raw
procedure hashes, current-state continuation, crash recovery and owned-path
cleanup. The release checklist and generated instructions for the root, Claude
and Copilot all include patch releases in the pre-1.0 rule.

The [current fixtures](../../../tests/engine/fixtures/current-contract/README.md)
retain the deterministic Stage 27 expectations. The [refusal specimens](../../../tests/engine/fixtures/refused-contracts/README.md)
retain two original run states and one manifest plus one matching command per
retired generator. Compared every retained file's contents with its Git
revision and checked each command against the original ownership digest.
Only current expectations and the five refusal JSON files accompany the
test-owned workflows in the installed test bundle.

### Local release gates

Host was macOS 26.7.3 arm64 with Git 2.54.0. The development interpreter was
framework CPython 3.14.4, and the minimum interpreter was uv-managed CPython
3.11.15. Each had its own editable environment with its `bin` first on
`PATH`. Both used build 1.6.1, setuptools 84.0.0, packaging 26.3 and
pyproject-hooks 1.3.3. The existing CI workflow targets Ubuntu 24.04 and
macOS 15 on both Python versions. No hosted run was requested after the
decision to keep this working tree local.

| Gate | CPython 3.11.15 | CPython 3.14.4 |
| --- | --- | --- |
| Focused contracts, source export and consumers | Included in full suite | 105 passed |
| Full discovery | 390 passed | 390 passed |
| Installed CLI and checkout launcher adapter checks | Both up to date | Both up to date |
| Direct wheel, isolated installed tests | 161 passed | 161 passed |
| Sdist-rebuilt wheel, isolated installed tests | 161 passed | 161 passed |

All reported suites had zero skips. In each installation the two-phase
release-documentation example completed. Generated Claude and OpenCode
adapters matched the recorded hashes for all 18 outputs. The complete manifest
was byte-identical across installations (SHA-256
`37723934ab4c234f0c00e530b16d33bfa86e2ea51fc02a57ee0af33830afcd8f`).

Commands below use the actual local artifact directory. The 3.11 environment
was `/private/tmp/specromancy-stage28.9SjFDK/py311`, and 3.14 used the
checkout's `.venv`. Provisioned the four pinned tools before installing editable.
Built the candidate once with 3.14 and verified that same pair with both.

```sh
python -m pip install --no-index --no-build-isolation -e .
python -m unittest tests.engine.contract.test_current_contract tests.engine.contract.test_recovery \
  tests.engine.contract.test_multi_pipeline tests.engine.contract.test_adapter_drift \
  tests.engine.unit.test_registry tests.engine.unit.test_run_records \
  tests.engine.contract.test_action_approval tests.engine.contract.test_release \
  tests.packaging.test_release_documentation tests.packaging.test_consumer_roots
python -m unittest discover
specromancy adapters generate --check
bin/specromancy adapters generate --check
artifacts=/private/tmp/specromancy-stage28.9SjFDK/final
python -m build --wheel --sdist --no-isolation --outdir "$artifacts"
python tools/verify_distribution.py \
  --wheel "$artifacts/specromancy_engine-0.1.4-py3-none-any.whl" \
  --sdist "$artifacts/specromancy_engine-0.1.4.tar.gz"
git diff --check
```

| Artifact | SHA-256 |
| --- | --- |
| Direct candidate wheel | `384fcc755df58cbe5afaccc9d410ccaa3f877ec8ac45a18b019b1dd3c38d2674` |
| Candidate sdist | `1d760525d9f9c3c1d555bda2d2712bac13d69550b418c7edb06d9f4a7ab7c648` |
| Sdist-rebuilt wheel in the recorded final verification, both interpreters | `59a825a3a3bb7c3e001f8f6d48fc4a683cc8d9cc6a65e114ed1d707e40594ab6` |
| Locally built 0.1.3 wheel used in the upgrade example | `038ece62e70c62a88f9bec7b8eaa17c3d7e9a5b4d4617e742e3a2840c211fb8c` |

### Consumer upgrades

Executed both shell blocks in the [installation guide](../../guides/installation.md#exercise-an-upgrade-in-disposable-consumers)
with the direct candidate wheel. The 0.1.3 wheel resumed run
`20261124T123342Z-3867c84a` in a second process and completed both visits with
outcome `approved`. Its schema-1 log contained six events. All 11 files from
the tagged consumer, including procedures, templates and graph validators,
retained their original contents.

The 0.1.4 wheel generated and checked 18 files from current authored inputs in
a separate project. Run `20261124T123345Z-69cd48ee` persisted its first pending
draft visit with run and event schema 2. Both consumers' last event revisions
matched their manifests. The ongoing verification command takes only the
candidate wheel and sdist.
