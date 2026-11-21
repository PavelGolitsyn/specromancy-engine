# 23. Apply the current-contract rule throughout 0.x

**Planned.** Establish the rule in the places contributors use to author,
review, and release a change. The review at `f265780` found that a real earlier
approval passed manifest validation and failed decision binding. It also found
four accepted adapter manifest identities. Both behaviors passed the full suite.

## Work

1. Put the release rule and definition of done in [workflow/instructions.md](../../../workflow/instructions.md).
   Any pre-1.0 release may change a public contract. Implement one current
   representation per surface. Retire superseded readers, writers, aliases
   kept solely for compatibility, migration paths, and positive old-format tests.
   Regenerate manifest-owned instructions with the installed CLI.
2. In the [public contracts](../../reference/contracts.md), state how to classify
   a change. Removing a required field, tightening previously supported input,
   or changing what a stored value authorizes is incompatible. Version the
   affected format and update fixtures together. Apply the same convention to
   explicitly versioned CLI output. An additive change that preserves the
   documented reader/writer contract can keep its version. Document changes to
   unversioned Python APIs and CLI commands and update their callers and tests.
3. Update the [release checklist](../../guides/releasing.md). Review the diff
   against the last released contract and the current development baseline.
   For each affected surface, record the old and new version or why the format
   remains compatible, the fixture proving current behavior, and what a consumer
   must do. Keep the package version in `pyproject.toml` independent of each
   format version. Applying the rule retrospectively changes current code,
   tests, and guidance. Published packages and tags are historical evidence.
4. Audit active code, examples, docs, tests, generated-file sources, and
   distribution gates for earlier compatibility decisions. Use the completed
   stages and release diffs to locate them. Classify each as a current feature,
   a compatibility-only path to remove, a refusal case, or historical evidence.
   Record each disposition and its owning stage here at execution. Include the
   pending [Windows plan](../windows-support/README.md), which still targets
   version-1 formats. Point its prospective gates at the current contracts when
   updating active guidance.

## Format decisions for this cleanup

| Surface | Baseline → planned | Reason and owner |
| --- | --- | --- |
| Run manifest | 1 → 2 | Stored approvals require a kind and different binding fields. Stage 24 |
| Event log | 1 → 2 | Approval payload semantics are part of the audit contract. Stage 24 |
| Action packet | 1 → 2 | One approval list became two and decisions can be replayed. Stage 25 |
| Status and successful/actionable CLI envelope | 1 → 2 each | Both directly expose pending approvals, including actions without an artifact or outcome. Stage 25 |
| Pipeline graph | 2 → 3 | Every phase must declare its workflow procedure. Stage 26 |
| Generated ownership manifest | 2 → 3, generator 4 → 5 | Selection evidence determines which paths the recorded targets can own. Stage 27 |
| Pipeline registry and adapter selection TOML | 1 → 1 each | Their structures already express the current contract. Exercise both version guards. |
| Project validators, workflow graph revision, package version | Separate authorities | A consumer owns its artifact schemas and graph revision. The release process owns the package version. |

## Acceptance

- [ ] Authored instructions, regenerated harness instructions, contract reference,
  and release checklist give the same rule for past and future pre-1.0 changes.
- [ ] Each active compatibility promise has a disposition, including parser
  alternatives, public facade aliases, persisted formats and fixture consumers.
  Historical execution records remain identifiable by their original revision.
- [ ] Review can trace every planned incompatible change to its version,
  fixtures, refusal behavior where a reader exists, and consumer instructions.
  Verify instruction propagation with the shipped-configuration adapter tests.
