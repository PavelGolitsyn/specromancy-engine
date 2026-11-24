# Repository instructions

- Support Python 3.11 and newer. The engine has no third-party runtime dependencies.
- Install the checkout in a dedicated environment with `python -m pip install -e .` before testing.
- Run the full suite with `python -m unittest discover`.
- Author repository instructions, registered graphs, templates and phase procedures under `workflow/`. Generate root `AGENTS.md` and harness discovery files with `specromancy adapters generate`. The generic engine lives under `src/specromancy_engine/` and must not contain workflow-specific phase names or policies. Harness adapters are generated files recorded in `adapters/manifest.json` and must contain no unique workflow logic.
- Keep the engine generic: phase names belong in pipeline configuration, never in engine code.
- Treat run artifacts as immutable visit outputs, mechanically enforce read-only phases, and invalidate approval when an approved artifact changes. Every state change must be atomic, validated, and reflected in both `run.json` and `events.jsonl`; runtime correctness must not depend on chat history.
- The CLI owns only `.specromancy/runs/<run-id>/`, manifest-recorded adapter paths, and temporary files adjacent to a manifest during atomic replacement. It must never delete, reset, stage, or commit repository work.
- Any pre-1.0 release, including a patch, may change a public contract. Maintain one current representation per surface. Apply this rule to inherited behavior as well as new changes. Retire superseded readers, writers, compatibility-only aliases, migration paths, and tests that require obsolete formats to succeed.
- For an incompatible change to a stored format or explicitly versioned CLI output, advance its own version and update its schema, producers, readers, and fixtures together. Test refusal before side effects wherever a reader exists. Document unversioned API and command changes and update their callers and tests.
- A change is done when the public contract and consumer upgrade steps are documented, fixtures demonstrate the current behavior, focused and full tests pass, generated files are reproducible, and the diff contains only related changes.
