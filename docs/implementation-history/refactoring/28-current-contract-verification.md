# 28. Verify current fixtures, upgrades, and release gates

**Planned after Stage 27.** Make it possible to tell which contracts the
installed release supports by reading its docs and running its release gate.

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

- [ ] Run the shared stage gates and the source-export and consumer tests from
  a dedicated editable installation. Build the wheel and sdist from the final
  tree using the repository's pinned tooling. Follow the existing
  [distribution verification procedure](../../guides/distribution-verification.md)
  with the actual artifact paths on Python 3.11 and the development interpreter.
  Exercise the existing CI platform matrix.
- [ ] In both the direct wheel and sdist-rebuilt wheel, load the packaged
  schemas, run the shipped release-documentation example to completion, and
  compare generated adapters and manifests for the same selected harnesses.
  Exercise action and transition approval in a test-owned graph declaring both.
  Exercise obsolete-run refusal before recovery, graph rejection on init/resume,
  and obsolete adapter refusal before replacement or stale deletion. Compare
  files byte-for-byte on the rejection paths.
- [ ] Execute the upgrade examples and retain results. The new release's
  positive tests use current inputs. Historic specimens have identifiable
  provenance and explicit refusal assertions.
- [ ] Reconcile the index and active guides with the measured results. Every
  cross-release support claim found in the final audit points to a current
  public contract or to clearly dated historical evidence. Future maintainers
  can find the standing rule from the repository instructions and release guide.
