# Harness compatibility

Consumers author repository instructions, registered pipelines and phase procedures
under `workflow/`. List the selected harnesses in `workflow/adapters.toml`.
Generation supplies the union of their discovery and invocation files.

Generate adapters after changing any canonical source:

```text
specromancy adapters generate
```

CI and local verification can detect missing, modified, extra, or source-stale adapter output without writing files:

```text
specromancy adapters generate --check
```

The ownership record is `adapters/manifest.json`, schema version 2. Generator
version 4 records every selected consumer of a shared path in one ownership entry. Generation
uses normalized UTF-8 input, stable ordering and newlines, no timestamps or
absolute paths, and atomic per-file replacement with the manifest written last.
It is not a transaction across all generated files. A file may be removed as
stale only when the previous manifest owns it and its current hash still
matches. Unowned and edited stale files are preserved and reported as conflicts.
Generation restores current manifest-owned output even if edited; `--check`
reports those edits without writing. Preserve intentional edits before
regenerating and incorporate their intended changes into canonical sources.
During migration, first relocate hand-written instructions and phase skills.
Older manifests retain the ownership limits of their own versions.

All harnesses need the installed command on their process's `PATH`; terminal
activation does not update an already-running GUI harness. See
[Harness usage](../guides/harnesses.md) for environment setup. The packaged templates supply generic orchestration.
The test suite verifies generated Markdown and CLI argument handling. Live-host
discovery and invocation depend on each harness and its trust settings.

## Harness matrix

| Harness | Discovery | Invocation | Adapter mode |
| --- | --- | --- | --- |
| Codex | Reads `AGENTS.md` and `.agents/skills` directly | Use `$specromancy-<id>` for a new run or `$pipeline` with an explicit ID, or invoke the canonical phase skill named by an action packet | Native discovery of shared generated skills |
| Claude Code | Reads `.claude/CLAUDE.md`, `.claude/skills`, and `.claude/commands/specromancy` | Use the generated init, resume, status, or phase command | Generated mirrors and thin commands |
| GitHub Copilot | Reads `.github/copilot-instructions.md`, repository `.agents/skills`, and `.github/prompts` | Run a generated `specromancy-*` prompt | Generated instructions and thin prompts |
| OpenCode | Reads `AGENTS.md`, `.agents/skills`, and `.opencode/commands` | Run a generated `specromancy-*` command | Generated thin commands |
| Hermes | Reads `AGENTS.md` and project `.agents/skills` after trust is granted | Invoke a generated pipeline launch skill or the generic launch skill or phase wrapper | Native discovery of shared generated skills |

## Persisted-state workflow

Initialize a run with `specromancy init DESCRIPTION --pipeline ID --json` and retain its returned run ID. For an existing run, use `specromancy status RUN_ID --json` or `specromancy resume RUN_ID --json`. When the CLI emits an action packet, load the exact `skill.absolute_path` it records, honor its mutation policy, and execute its recorded final validation command. Conversation history is never run state.

## Hermes repository trust

Hermes requires project skills to be trusted before it will load them. From the repository, run:

```text
hermes skills trust
```

Review and accept the repository skills when prompted. Specromancy does not modify user-level Hermes configuration.

## Generated-file policy

Edit the registered workflow sources and regenerate. Codex and Hermes discover the
same generated `.agents/skills/` files. When both are selected, the manifest lists these paths for both
targets and records each file's hash once. Phase wrappers load the declared
canonical procedure, while generic and per-pipeline launch skills embed release
orchestration. See the [adapter contract](contracts.md#adapter-generation).
