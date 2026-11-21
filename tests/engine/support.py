"""Test-owned multi-pipeline configuration, independent of shipped workflows."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def select_harnesses(root: Path, *names: str) -> None:
    (root / "workflow/adapters.toml").write_text(
        f"schema_version = 1\nharnesses = {json.dumps(names)}\n", encoding="utf-8",
    )


def write_workflow_skill(root: Path, name: str = "compose", source: str | None = None) -> Path:
    path = root / (source or f"workflow/skills/{name}/SKILL.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: Record evidence.\n---\nFollow the action packet.\n",
                    encoding="utf-8")
    return path


class MultiPipelineFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True, capture_output=True)
        write_workflow_skill(self.root)
        select_harnesses(self.root, "claude", "codex", "copilot", "hermes", "opencode")
        (self.root / "workflow/instructions.md").write_text("# Repository instructions\n", encoding="utf-8")
        template = self.root / "workflow/templates/shared.md"
        template.parent.mkdir(parents=True)
        template.write_text("# Result\n## Result\nRecord evidence.\n", encoding="utf-8")
        self.add_pipeline("alpha", "compose")
        self.add_pipeline("beta", "inspect")
        self.register("alpha", "beta")

    def close(self) -> None:
        self.temporary.cleanup()

    def add_pipeline(self, pipeline_id: str, phase: str) -> Path:
        path = self.root / "workflow/pipelines" / f"{pipeline_id}.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f'schema_version = 2\nid = "{pipeline_id}"\nversion = 1\nstart = "{phase}"\n'
            'terminal_outcomes = ["done"]\nartifact_pattern = "artifacts/{visit:03}-{phase}.md"\n'
            f'[[phases]]\nid = "{phase}"\n'
            'skill = "compose"\nskill_source = "workflow/skills/compose/SKILL.md"\n'
            'inputs = ["request"]\noutput_name = "result.md"\n'
            'output_template = "../templates/shared.md"\nmutation = "read-only"\n'
            'completion_criteria = ["Record a result."]\nvalidator = "markdown"\n'
            'required_headings = ["Result"]\ntransition_approval_conditions = []\naction_approval_conditions = []\nstop_conditions = []\n'
            '[[phases.transitions]]\noutcome = "done"\n', encoding="utf-8",
        )
        return path

    def register(self, *ids: str) -> None:
        (self.root / "workflow/pipelines.toml").write_text(
            "schema_version = 1\n" + "".join(
                f'\n[[pipelines]]\nid = "{pipeline_id}"\npath = "pipelines/{pipeline_id}.toml"\n'
                for pipeline_id in ids
            ), encoding="utf-8",
        )
