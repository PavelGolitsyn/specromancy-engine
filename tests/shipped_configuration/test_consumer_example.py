"""Check the source-only consumer example and its portable procedures."""

from pathlib import Path
import unittest

from tests.shipped_configuration.test_skills import ALLOWED_FRONTMATTER, parse_frontmatter


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/release-documentation"


class ConsumerExampleSourcesTests(unittest.TestCase):
    def test_example_ships_only_authored_sources(self) -> None:
        for relative in ("AGENTS.md", ".agents", ".claude", ".github", ".opencode", "adapters"):
            self.assertFalse((EXAMPLE / relative).exists(), relative)
        self.assertTrue((EXAMPLE / "workflow/instructions.md").is_file())

    def test_example_skills_have_portable_frontmatter(self) -> None:
        skills = sorted((EXAMPLE / "workflow/skills").glob("*/SKILL.md"))
        self.assertEqual(len(skills), 2)
        for path in skills:
            with self.subTest(skill=path.parent.name):
                fields, metadata = parse_frontmatter(path)
                self.assertEqual(set(fields), ALLOWED_FRONTMATTER)
                self.assertEqual(fields["name"], path.parent.name)
                self.assertTrue(metadata)
                self.assertNotIn("bin/specromancy", path.read_text())
