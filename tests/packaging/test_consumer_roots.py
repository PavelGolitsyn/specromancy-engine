"""Self-contained smoke suite: copy this file outside the checkout to test a wheel.

No producer fixtures, build tools, downloads, or source-path injection are used.
Run with the installed environment's Python; subprocesses use its console script.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

from specromancy_engine import Engine, EngineError, ExitCode, RunStore, load_pipeline, load_registry
from specromancy_engine._adapters.adapter_sources import capture_release_inputs
from specromancy_engine.cli import main
from specromancy_engine.schema_validation import load_json_schema


SCHEMAS = {"event.schema.json", "run.schema.json", "pipeline.schema.json", "pipelines.schema.json"}


def snapshot(root: Path, *, exclude_runs: bool = False) -> dict:
    """Capture content, modes, and links, including Git metadata and empty dirs."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if exclude_runs and (relative in {".specromancy", ".specromancy/runs"}
                             or relative.startswith(".specromancy/runs/")):
            continue
        mode = path.lstat().st_mode
        content = (os.readlink(path) if path.is_symlink() else
                   hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
        result[relative] = (mode, content)
    return result


def write_consumer(root: Path, phase: str, *, allow_non_git: bool = False) -> None:
    skill = "workflow/skills/compose/SKILL.md"
    source_field = f'skill_source = "{skill}"\n'
    resources = {
        "workflow/adapters.toml": 'schema_version = 1\nharnesses = ["claude", "codex", "copilot", "hermes", "opencode"]\n',
        "workflow/instructions.md": "# Consumer instructions\n",
        "workflow/pipelines.toml": 'schema_version = 1\n[[pipelines]]\nid = "shared"\npath = "pipelines/flow.toml"\n',
        "workflow/pipelines/flow.toml": (
            f'schema_version = 3\nid = "shared"\nversion = 1\nstart = "{phase}"\n'
            'terminal_outcomes = ["done"]\nartifact_pattern = "artifacts/{visit:03}-{phase}.json"\n'
            f'allow_non_git = {str(allow_non_git).lower()}\n'
            f'[[phases]]\nid = "{phase}"\nskill = "compose"\n{source_field}inputs = ["request"]\n'
            'output_name = "result.json"\noutput_template = "../templates/result.json"\n'
            'mutation = "read-only"\ncompletion_criteria = ["Record the consumer result."]\n'
            'validator = {type = "json", path = "../schemas/result.json"}\n'
            'transition_approval_conditions = []\naction_approval_conditions = []\nstop_conditions = []\n'
            '[[phases.transitions]]\noutcome = "done"\n'
        ),
        skill: f"---\nname: compose\ndescription: Record {phase}.\n---\nUse {phase} resources.\n",
        "workflow/templates/result.json": json.dumps({"consumer": phase}) + "\n",
        "workflow/schemas/result.json": json.dumps({
            "type": "object", "required": ["consumer"],
            "properties": {"consumer": {"enum": [phase]}}, "additionalProperties": False,
        }),
        "request.md": f"Request for {phase}\n",
    }
    for name, content in resources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (root / "nested/deeper").mkdir(parents=True, exist_ok=True)


class ConsumerRootTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.outside = self.base / "unrelated"
        self.outside.mkdir()
        self.home = self.base / "empty-home"
        self.home.mkdir()
        self.env = os.environ.copy()
        for name in tuple(self.env):
            if name.startswith("PYTHON") or name.startswith("GIT_"):
                self.env.pop(name)
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        XDG_CONFIG_HOME=str(self.home), PYTHONNOUSERSITE="1",
                        PYTHONDONTWRITEBYTECODE="1", GIT_CONFIG_NOSYSTEM="1")
        self.console = Path(sys.executable).parent / ("specromancy.exe" if os.name == "nt" else "specromancy")
        self.assertTrue(self.console.is_file(), "install the checkout or wheel before testing")
        git = shutil.which("git")
        self.assertIsNotNone(git)
        # Only the environment's scripts and Git's directory; no producer bin/.
        self.env["PATH"] = os.pathsep.join((str(self.console.parent), str(Path(git).parent)))
        self.first, self.second = self.base / "amber", self.base / "blue"
        self.first.mkdir()
        self.git("init", "--quiet", str(self.first))
        self.git("-C", str(self.first), "-c", "user.name=Consumer Test",
                 "-c", "user.email=consumer@example.invalid", "-c", "commit.gpgsign=false",
                 "commit", "--quiet", "--allow-empty", "-m", "Test worktree seed")
        self.git("-C", str(self.first), "worktree", "add", "--quiet", "--detach", str(self.second))
        write_consumer(self.first, "amber")
        write_consumer(self.second, "blue")

    def git(self, *args: str) -> None:
        result = subprocess.run(["git", *args], cwd=self.outside, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def command(self, cwd: Path, *args: str, expected: int = 0, module: bool = False) -> dict:
        argv = [sys.executable, "-m", "specromancy_engine"] if module else [str(self.console)]
        result = subprocess.run([*argv, "--json", *args], cwd=cwd, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        if expected in {0, 7, 8, 9, 13}:
            self.assertEqual(result.stderr, "")
            response = json.loads(result.stdout)
            self.assertEqual(response["code"], expected)
            if expected == 7 and response.get("details", {}).get("error_code") == "stale-approval":
                self.assertEqual(set(response), {"code", "message", "details"})
                return response
            self.assertEqual(response["schema_version"], 2)
            if response["kind"] in {"status", "approval"}:
                self.assertEqual(response["status"]["schema_version"], 2)
            elif response["kind"] == "action":
                self.assertEqual(response["action"]["schema_version"], 2)
            return response
        self.assertEqual(result.stdout, "")
        return json.loads(result.stderr)

    def assert_action(self, action: dict, root: Path, phase: str) -> None:
        self.assertEqual(action["phase"], phase)
        self.assertEqual(Path(action["skill"]["absolute_path"]), root / "workflow/skills/compose/SKILL.md")
        self.assertIn(f"Use {phase} resources.", Path(action["skill"]["absolute_path"]).read_text())
        self.assertEqual(Path(action["template"]["absolute_path"]), root / "workflow/templates/result.json")
        self.assertEqual(json.loads(Path(action["template"]["absolute_path"]).read_text()), {"consumer": phase})
        self.assertEqual(Path(action["inputs"][0]["absolute_path"]).read_text(), f"Request for {phase}\n")
        run_root = root / ".specromancy/runs" / action["run_id"]
        self.assertTrue(Path(action["output"]["absolute_path"]).is_relative_to(run_root))
        self.assertEqual(action["final_validation_command"][:3], ["specromancy", "--root", str(root)])

    def test_installed_cli_uses_explicit_workflow_resources_from_an_unrelated_directory(self) -> None:
        root = self.base / "workflow-only"
        write_consumer(root, "publish", allow_non_git=True)
        (root / "workflow/adapters.toml").unlink()
        self.assertEqual(load_registry(root).load("shared").start, "publish")
        before = snapshot(root)
        for args in ((), ("--check",)):
            error = self.command(self.outside, "--root", str(root), "adapters", "generate", *args, expected=3)
            self.assertIn("workflow/adapters.toml", error["message"])
            self.assertIn('harnesses = ["claude"]', error["message"])
            self.assertEqual(snapshot(root), before)
        (root / "workflow/templates/result.json").write_text('{"consumer": "pending"}\n')
        prefix = ("--root", str(root))
        action = self.command(self.outside, *prefix, "init", "Publish", "--pipeline", "shared", expected=8)["action"]
        self.assertEqual(Path(action["skill"]["absolute_path"]), root / "workflow/skills/compose/SKILL.md")
        run = action["run_id"]
        self.command(self.outside, *prefix, "phase", run, "publish", expected=8)
        Path(action["output"]["absolute_path"]).write_text('{"consumer": "publish"}\n')
        self.command(self.outside, *prefix, "validate", run)
        final = self.command(self.outside, *prefix, "resume", run)
        self.assertEqual(final["status"]["terminal_result"]["outcome"], "done")
        self.assertEqual({path.name for path in root.iterdir()}, {"workflow", "request.md", ".specromancy", "nested"})

    def test_cli_discovers_both_git_markers_and_keeps_consumers_isolated(self) -> None:
        self.assertTrue((self.first / ".git").is_dir())
        self.assertTrue((self.second / ".git").is_file())
        before = snapshot(self.base, exclude_runs=False)
        # Exclude only each consumer's run storage when comparing all other files.
        protected = [snapshot(root, exclude_runs=True) for root in (self.first, self.second)]
        actions = []
        for root, phase in ((self.first, "amber"), (self.second, "blue")):
            for cwd in (root, root / "nested/deeper"):
                action = self.command(cwd, "init", "--description-file", "request.md",
                                      "--pipeline", "shared", expected=8)["action"]
                self.assert_action(action, root, phase)
                actions.append((root, phase, action))
        for root, phase, action in reversed(actions):
            run_id = action["run_id"]
            status = self.command(self.outside, "--root", str(root), "status", run_id, module=True)["status"]
            self.assertEqual(status["pipeline"]["id"], "shared")
            self.command(root / "nested/deeper", phase, run_id, expected=8)
            Path(action["output"]["absolute_path"]).write_text(json.dumps({"consumer": phase}), encoding="utf-8")
            result = subprocess.run(action["final_validation_command"], cwd=self.outside,
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            completed = self.command(root, "status", run_id)["status"]
            self.assertEqual(completed["terminal_result"]["outcome"], "done")
            other = self.second if root == self.first else self.first
            self.command(self.outside, "--root", str(other), "status", run_id, expected=ExitCode.NOT_FOUND)
        for root, original in zip((self.first, self.second), protected):
            self.assertEqual(snapshot(root, exclude_runs=True), original)
        self.assertEqual(snapshot(self.home), {})
        self.assertEqual(snapshot(self.outside), {})
        after = snapshot(self.base)
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertTrue(all(key.split("/")[0] in {"amber", "blue"} and
                            (key.endswith("/.specromancy") or "/.specromancy/runs" in key)
                            for key in after.keys() - before.keys()))

    def test_public_api_and_in_process_cli_do_not_cache_same_pipeline_id(self) -> None:
        registries = [load_registry(root) for root in (self.first, self.second)]
        pipelines = [registry.load("shared") for registry in registries]
        self.assertNotEqual(pipelines[0].config_hash, pipelines[1].config_hash)
        protected = [snapshot(root, exclude_runs=True) for root in (self.first, self.second)]
        runs = []
        for pipeline in pipelines:
            root, phase = pipeline.repository_root, pipeline.start
            self.assertEqual(load_pipeline(pipeline.path, repository_root=root), pipeline)
            schema = load_json_schema(pipeline.phase(phase).validator.resolved_path)
            self.assertEqual(schema["properties"]["consumer"]["enum"], [phase])
            engine = Engine(pipeline, RunStore(root))
            action = engine.initialize((root / "request.md").read_text())["action"]
            self.assert_action(action, root, phase)
            runs.append((engine, action))
        # Interleave retained registry/engine objects and repeated CLI calls in one process.
        for registry, (engine, action) in reversed(list(zip(registries, runs))):
            root, phase, run_id = engine.pipeline.repository_root, engine.pipeline.start, action["run_id"]
            self.assertEqual(registry.load("shared").start, phase)
            stdout, stderr = io.StringIO(), io.StringIO()
            code = main(["--root", str(root), "--json", "status", run_id], stdout=stdout, stderr=stderr)
            self.assertEqual(code, 0, stderr.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())["status"]["pipeline"]["sha256"], engine.pipeline.config_hash)
            engine.start_phase(run_id, phase)
            output = Path(action["output"]["absolute_path"])
            output.write_text(json.dumps({"consumer": "wrong-project"}), encoding="utf-8")
            with self.assertRaises(EngineError) as raised:
                engine.validate(run_id, phase)
            self.assertEqual(raised.exception.code, ExitCode.VALIDATION_FAILED)
            output.write_text(json.dumps({"consumer": phase}), encoding="utf-8")
            self.assertEqual(engine.validate(run_id, phase)["code"], 0)
            stored = RunStore(root).load(run_id)
            self.assertEqual(stored["pipeline"]["path"], "workflow/pipelines/flow.toml")
            self.assertEqual(stored["pipeline"]["sha256"], engine.pipeline.config_hash)
            restored = Engine(load_pipeline(root / stored["pipeline"]["path"], repository_root=root), RunStore(root))
            self.assertEqual(restored.status(run_id)["status"]["terminal_result"]["outcome"], "done")
        for root, original in zip((self.first, self.second), protected):
            self.assertEqual(snapshot(root, exclude_runs=True), original)

    def test_explicit_non_git_roots_and_failure_diagnostics(self) -> None:
        root = self.base / "non-git"
        write_consumer(root, "standalone", allow_non_git=True)
        before = snapshot(self.base)
        for cwd in (self.outside, root, root / "nested/deeper"):
            payload = self.command(cwd, "init", "Request", "--pipeline", "shared", expected=2)
            self.assertEqual(payload["message"], "could not find a repository root; pass --root PATH")
        for path, suffix in ((self.base / "absent", "does not exist"), (root / "request.md", "is not a directory")):
            payload = self.command(self.first, "--root", str(path), "init", "Request", "--pipeline", "shared", expected=2)
            self.assertIn(suffix, payload["message"])
            self.assertEqual(payload["details"]["root"], str(path))
        payload = self.command(self.outside, "--root", str(root), "init", "Request", expected=2)
        self.assertEqual(payload["message"], "init requires --pipeline ID; there is no default pipeline")
        self.assertEqual(snapshot(self.base), before)
        action = self.command(self.outside, "--root", str(root), "init", "--description-file", "request.md",
                              "--pipeline", "shared", expected=8)["action"]
        self.assert_action(action, root, "standalone")
        denied = self.base / "git-required"
        write_consumer(denied, "denied")
        payload = self.command(self.outside, "--root", str(denied), "init", "Request", "--pipeline", "shared", expected=ExitCode.INVALID_PIPELINE)
        self.assertEqual(payload["details"]["error_code"], "git-worktree-required")
        self.assertFalse((denied / ".specromancy").exists())

    def test_saved_provenance_survives_registry_retargeting_but_registry_is_mandatory(self) -> None:
        action = self.command(self.first, "init", "Request", "--pipeline", "shared", expected=8)["action"]
        root, run_id = self.first, action["run_id"]
        registry = root / "workflow/pipelines.toml"
        # Change only test-owned config; existing runs must use their saved path.
        other = root / "workflow/pipelines/other.toml"
        other.write_bytes((root / "workflow/pipelines/flow.toml").read_bytes().replace(b'"amber"', b'"other"'))
        registry.write_text(registry.read_text().replace("flow.toml", "other.toml"))
        resumed = self.command(self.outside, "--root", str(root), "resume", run_id, expected=8)["action"]
        self.assertEqual(resumed["phase"], "amber")
        fresh = self.command(root, "init", "New request", "--pipeline", "shared", expected=8)["action"]
        self.assertEqual(fresh["phase"], "other")
        self.command(root, "--pipeline", "wrong", "status", run_id, expected=2)
        registry.unlink()
        before = snapshot(self.base)
        for args in (("status", run_id), ("init", "Request", "--pipeline", "shared")):
            payload = self.command(root, *args, expected=ExitCode.INVALID_PIPELINE)
            self.assertEqual(payload["details"]["error_code"], "invalid-registry")
            self.assertEqual(payload["details"]["path"], str(registry))
        self.assertEqual(snapshot(self.base), before)


    def test_selection_preserves_run_bytes_and_respects_active_mutation_policy(self) -> None:
        for root, phase, policy in ((self.first, "amber", "read-only"), (self.second, "blue", "allowlist")):
            with self.subTest(policy=policy):
                graph = root / "workflow/pipelines/flow.toml"
                config = root / "workflow/adapters.toml"
                source = graph.read_text().replace('transition_approval_conditions = []', 'transition_approval_conditions = ["accept"]')
                if policy == "allowlist":
                    source = source.replace('mutation = "read-only"', 'mutation = "allowlist"\nallowlist = ["workflow/adapters.toml"]')
                graph.write_text(source)
                self.command(root, "adapters", "generate")
                self.git("-C", str(root), "add", "workflow", "AGENTS.md", "adapters", ".agents", ".claude", ".opencode", ".github")
                pipeline = load_registry(root).load("shared")
                skill = pipeline.phase(phase).skill_path
                skill_hash = hashlib.sha256(skill.read_bytes()).digest()
                run = self.command(root, "init", "Check policy", "--pipeline", "shared", expected=8)["action"]["run_id"]
                action = self.command(root, "phase", run, phase, expected=8)["action"]
                Path(action["output"]["absolute_path"]).write_text(json.dumps({"consumer": phase}))
                if policy == "read-only":
                    self.command(root, "request-approval", run, "--reason", "accept", expected=7)

                run_root = root / ".specromancy/runs" / run
                before = snapshot(run_root)
                config.write_text('schema_version = 1\nharnesses = ["claude"]\n')
                self.command(root, "adapters", "generate")
                self.assertEqual(snapshot(run_root), before)
                self.assertEqual(load_registry(root).load("shared").canonical_json, pipeline.canonical_json)
                self.assertEqual(hashlib.sha256(skill.read_bytes()).digest(), skill_hash)
                command = "approve" if policy == "read-only" else "validate"
                refused = self.command(root, command, run, phase, expected=6)
                self.assertEqual(refused["details"]["error_code"], "mutation-policy-violation")
                violations = RunStore(root).load(run)["visits"][0]["mutation_result"]["violations"]
                self.assertIn("AGENTS.md", violations)
                self.assertEqual("workflow/adapters.toml" in violations, policy == "read-only")

    def prepare_adapters(self) -> dict:
        root = self.first
        self.assertFalse((root / "bin/specromancy").exists())
        self.assertFalse((root / "src").exists())
        self.command(root, "adapters", "generate")
        before = snapshot(root)
        self.command(root, "adapters", "generate")
        self.command(root / "nested/deeper", "adapters", "generate", "--check")
        self.assertEqual(snapshot(root), before)
        manifest = json.loads((root / "adapters/manifest.json").read_text())
        self.assertEqual(manifest["generator"], {
            "name": "specromancy", "version": 4, "command": "specromancy adapters generate",
        })
        self.assertEqual(manifest["schema_version"], 2)
        for entry in manifest["generated"]:
            content = (root / entry["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), entry["sha256"])
        mirror = (root / ".claude/skills/pipeline/SKILL.md").read_text()
        self.assertIn("specromancy resume RUN_ID --json", mirror)
        return manifest

    def run_rendered(self, argv: list[str], *, cwd: Path, expected: int = 8) -> dict:
        self.assertEqual(argv[0], "specromancy")
        result = subprocess.run(argv, cwd=cwd, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertFalse(result.stderr, result.stderr)
        return json.loads(result.stdout)

    def test_consumer_executes_every_wrapper_and_launch_skill(self) -> None:
        manifest = self.prepare_adapters()
        root = self.first
        manifest_path = root / "adapters/manifest.json"
        original_manifest = manifest_path.read_bytes()
        shutil.rmtree(root / ".agents")
        (root / "AGENTS.md").unlink()
        missing = {entry["path"] for entry in manifest["generated"]
                   if entry["path"] == "AGENTS.md" or entry["path"].startswith(".agents/")}
        before = snapshot(root)
        drift = self.command(root, "adapters", "generate", "--check", expected=ExitCode.ADAPTER_DRIFT)
        self.assertEqual(set(drift["details"]["missing"]), missing)
        self.assertEqual(snapshot(root), before)
        description = 'A request with spaces, "quotes", $HOME, $(echo never), and café'
        conventions = {
            "claude": (".claude/commands/specromancy/{name}.md", {
                "init": '"$1" --pipeline "$0"', "status": '"$0"',
                "resume": '"$0"', "phase": '"$0" "$1"',
            }),
            "opencode": (".opencode/commands/specromancy-{name}.md", {
                "init": '"$2" --pipeline "$1"', "status": '"$1"',
                "resume": '"$1"', "phase": '"$1" "$2"',
            }),
            "copilot": (".github/prompts/specromancy-{name}.prompt.md", {
                "init": "DESCRIPTION --pipeline PIPELINE_ID", "status": "RUN_ID",
                "resume": "RUN_ID", "phase": "RUN_ID PHASE",
            }),
        }
        wrappers = {entry["path"] for entry in manifest["generated"]
                    if "commands/" in entry["path"] or entry["path"].endswith(".prompt.md")}
        self.assertEqual(wrappers, {pattern.format(name=name)
                                   for pattern, commands in conventions.values() for name in commands})
        for harness, (pattern, commands) in conventions.items():
            run_id = None
            for name in ("init", "status", "resume", "phase"):
                with self.subTest(harness=harness, command=name):
                    text = (root / pattern.format(name=name)).read_text()
                    self.assertNotIn("bin/specromancy", text)
                    invocations = re.findall(r"`(specromancy (?:init|phase|status|resume) [^`]+)`", text)
                    self.assertEqual(invocations, [f"specromancy {name} {commands[name]} --json"])
                    values = (["shared", description] if name == "init" else
                              [run_id, "amber"] if name == "phase" else [run_id])
                    tokens = shlex.split(invocations[0])
                    if harness == "copilot":
                        placeholders = dict(zip(("PIPELINE_ID", "DESCRIPTION") if name == "init" else
                                                ("RUN_ID", "PHASE"), values))
                    else:
                        start = 0 if harness == "claude" else 1
                        placeholders = {f"${index}": value for index, value in enumerate(values, start)}
                    argv = [placeholders.get(token, token) for token in tokens]
                    arguments = ([description, "--pipeline", "shared"] if name == "init" else values)
                    self.assertEqual(argv, ["specromancy", name, *arguments, "--json"])
                    result = self.run_rendered(argv, cwd=root / "nested/deeper",
                                               expected=0 if name == "status" else 8)
                    if name == "init":
                        action = result["action"]
                        run_id = action["run_id"]
                        self.assertIn(description, Path(action["inputs"][0]["absolute_path"]).read_text())
                    if name in ("init", "resume", "phase"):
                        source = Path(result["action"]["skill"]["absolute_path"])
                        self.assertEqual(source, root / "workflow/skills/compose/SKILL.md")
                        self.assertIn("Use amber resources.", source.read_text())
            # Status argv uses cwd; validation argv independently carries the root.
            status = self.command(root, "status", run_id)["status"]
            self.assertEqual(status["next_command"], ["specromancy", "validate", run_id, "amber"])
            Path(action["output"]["absolute_path"]).write_text('{"consumer":"amber"}\n')
            self.run_rendered([*status["next_command"], "--json"], cwd=root / "nested/deeper", expected=0)

        self.command(root, "adapters", "generate")
        self.command(root, "adapters", "generate", "--check")
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        for entry in manifest["generated"]:
            self.assertEqual(hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])

        launches = [entry["path"] for entry in manifest["generated"]
                    if entry["path"].endswith("skills/specromancy-shared/SKILL.md")]
        self.assertEqual(set(launches), {".agents/skills/specromancy-shared/SKILL.md",
                                        ".claude/skills/specromancy-shared/SKILL.md"})
        for relative in launches:
            with self.subTest(launch=relative):
                text = (root / relative).read_text()
                invocations = re.findall(r"`(specromancy init [^`]+)`", text)
                self.assertEqual(invocations, ["specromancy init DESCRIPTION --pipeline shared --json"])
                argv = [description if token == "DESCRIPTION" else token for token in shlex.split(invocations[0])]
                action = self.run_rendered(argv, cwd=root)["action"]
                self.assertEqual(action["phase"], "amber")
                self.assertEqual(action["final_validation_command"][:3], ["specromancy", "--root", str(root)])
                self.assertIn(description, Path(action["inputs"][0]["absolute_path"]).read_text())
                status = self.command(root, "status", action["run_id"])["status"]
                self.assertEqual(status["next_command"], ["specromancy", "phase", action["run_id"], "amber"])
                self.run_rendered([*status["next_command"], "--json"], cwd=root)
                Path(action["output"]["absolute_path"]).write_text('{"consumer":"amber"}\n')
                result = subprocess.run(action["final_validation_command"], cwd=self.outside,
                                        env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_consumer_executes_rendered_decisions_and_resumes_through_python(self) -> None:
        root = self.first
        graph = root / "workflow/pipelines/flow.toml"
        graph.write_text(graph.read_text().replace(
            "action_approval_conditions = []", 'action_approval_conditions = ["change"]'
        ).replace(
            "transition_approval_conditions = []", 'transition_approval_conditions = ["accept"]'
        ).replace("stop_conditions = []", 'stop_conditions = ["unavailable"]'))

        def human(*args: str, expected: int) -> str:
            result = subprocess.run([str(self.console), *args], cwd=root, env=self.env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")
            return result.stdout

        run = self.command(root, "init", "Review changes", "--pipeline", "shared", expected=8)["action"]["run_id"]
        self.command(root, "amber", run, module=True, expected=8)
        for number, verb in enumerate(("decline", "approve"), 1):
            details = f'  Change "{number}" in café.  '
            args = ("request-approval", run, "--reason", "change", "--details", details)
            response = self.command(root, *args, module=True, expected=7)
            approval = response["approval"]
            self.assertEqual(response["status"]["pending_approval"], approval)
            self.assertEqual(approval["request_number"], number)
            self.assertEqual(approval["details"], details)
            display = human(*args, expected=7)
            self.assertIn(f"Details: {details}\n", display)
            self.assertIn(f"Request {number}: change\n", display)
            line = next(line for line in display.splitlines() if line.startswith(verb.capitalize() + ": "))
            argv = shlex.split(line.split(": ", 1)[1])
            self.assertEqual(argv, approval[verb + "_command"])
            self.run_rendered([*argv, "--json"], cwd=root, expected=8)

        # An embedding opens the CLI-created run and checks each version before using its fields.
        engine = Engine(load_pipeline(graph, repository_root=root), RunStore(root))
        resumed = engine.resume(run)
        self.assertEqual(resumed["schema_version"], 2)
        packet = resumed["action"]
        self.assertEqual(packet["schema_version"], 2)
        self.assertEqual(packet["action_approval_conditions"], ["change"])
        self.assertEqual(packet["transition_approval_conditions"], ["accept"])
        self.assertEqual([(item["request_number"], item["decision"]) for item in packet["action_decisions"]],
                         [(1, "declined"), (2, "approved")])
        Path(packet["output"]["absolute_path"]).write_text('{"consumer":"amber"}\n')
        pending = self.command(root, "request-approval", run, "--reason", "accept", expected=7)["approval"]
        display = human("status", run, expected=0)
        self.assertIn("Outcome: done\n", display)
        self.assertIn(f"Artifact SHA-256: {pending['artifact_sha256']}\n", display)
        self.assertNotIn("Decline:", display)
        self.assertNotIn("decline_command", pending)
        argv = shlex.split(next(line.removeprefix("Approve: ") for line in display.splitlines()
                                if line.startswith("Approve: ")))
        self.assertEqual(argv, pending["approve_command"])
        completed = self.run_rendered([*argv, "--json"], cwd=root, expected=0)
        self.assertEqual(completed["status"]["status"], "completed")
        self.command(root, "resume", run, module=True)

        blocked = self.command(root, "init", "Missing input", "--pipeline", "shared", expected=8)["action"]
        self.command(root, "phase", blocked["run_id"], "amber", expected=8)
        result = self.command(root, "block", blocked["run_id"], "--reason", "unavailable", module=True, expected=9)
        self.assertEqual(result["status"]["status"], "blocked")

    def test_adapter_generation_protects_existing_project_owned_instructions(self) -> None:
        root = self.first
        (root / "AGENTS.md").write_text("# Consumer instructions\n")
        wrapper = root / ".agents/skills/compose/SKILL.md"
        wrapper.parent.mkdir(parents=True)
        source = root / "workflow/skills/compose/SKILL.md"
        wrapper.write_bytes(source.read_bytes() + b"Additional consumer procedure.\n")
        before = snapshot(root)
        result = self.command(root, "adapters", "generate", expected=ExitCode.ADAPTER_DRIFT)
        self.assertEqual(result["details"]["unowned"], [".agents/skills/compose/SKILL.md", "AGENTS.md"])
        self.assertEqual(snapshot(root), before)
        # Relocate the consumer's originals to their declared workflow locations.
        wrapper.replace(source)
        (root / "AGENTS.md").replace(root / "workflow/instructions.md")
        self.command(root, "adapters", "generate")
        self.command(root, "adapters", "generate", "--check")
        self.assertIn("Additional consumer procedure.", source.read_text())
        self.assertIn("# Consumer instructions", (root / "AGENTS.md").read_text())


class PackageResourceTests(unittest.TestCase):
    def test_release_inputs_are_available_outside_a_producer_or_consumer_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, chdir(temporary):
            captured = capture_release_inputs()
            identity, *templates = captured
            self.assertEqual(identity.path, "@package/specromancy_engine/version")
            self.assertEqual(identity.content.decode(), version("specromancy-engine"))
            resources = files("specromancy_engine").joinpath("resources", "adapters")
            self.assertEqual({source.path for source in templates}, {
                "@package/specromancy_engine/resources/adapters/" + entry.name
                for entry in resources.iterdir() if entry.is_file()
            })
            for source in templates:
                self.assertEqual(source.content, resources.joinpath(source.path.rsplit("/", 1)[1]).read_bytes())

            # Consumer files at lookalike paths cannot override any release input.
            for name in ("AGENTS.md", ".agents/skills/pipeline/SKILL.md",
                         "resources/adapters/launch.md", templates[0].path):
                path = Path(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("consumer override")
            self.assertEqual(capture_release_inputs(), captured)

    def test_all_four_published_schemas_are_readable_json(self) -> None:
        resources = files("specromancy_engine").joinpath("schemas")
        self.assertEqual({item.name for item in resources.iterdir() if item.name.endswith(".json")}, SCHEMAS)
        for name in sorted(SCHEMAS):
            with self.subTest(name=name):
                schema = json.loads(files("specromancy_engine").joinpath("schemas", name).read_text(encoding="utf-8"))
                self.assertIsInstance(schema, dict)
                self.assertEqual(schema["type"], "object")
                self.assertIn("$schema", schema)


if __name__ == "__main__":
    unittest.main()
