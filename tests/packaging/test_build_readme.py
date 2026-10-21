"""Contracts for build-only Markdown conversion; no Git or network required."""
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
helper = runpy.run_path(str(ROOT / "build_readme.py"))
render = helper["render_readme"]
metadata = helper["build_metadata"]
REPO = "https://github.com/example/project"


class BuildReadmeTests(unittest.TestCase):
    def test_reference_links_titles_fragments_and_directories(self):
        source = ('[Guide][guide] and [Workflow][workflow].\n'
                  '[guide]: ./docs/guide.md?view=1#install "Guide"\n'
                  '[workflow]: workflow/\n'
                  '[section]: #usage\n'
                  '[space]: <docs/my guide.md>\n')
        expected = ('[Guide][guide] and [Workflow][workflow].\n'
                    f'[guide]: {REPO}/blob/v1.2.3/docs/guide.md?view=1#install "Guide"\n'
                    f'[workflow]: {REPO}/tree/v1.2.3/workflow\n'
                    f'[section]: {REPO}/blob/v1.2.3/README.md#usage\n'
                    f'[space]: <{REPO}/blob/v1.2.3/docs/my%20guide.md>\n')
        self.assertEqual(render(source, REPO, "1.2.3"), expected)

    def test_image_references_use_raw_content(self):
        self.assertEqual(render('![Diagram][image-flow]\n[image-flow]: images/flow.png\n', REPO, "2.0.0"),
                         f'![Diagram][image-flow]\n[image-flow]: {REPO}/raw/v2.0.0/images/flow.png\n')

    def test_external_links_and_code_are_preserved(self):
        source = ('[Web](https://example.com/path) and `[example](local.md)`\n'
                  '[web]: https://example.com/path\n[mail]: mailto:hello@example.com\n'
                  '[cdn]: //example.com/image.png\n'
                  '````markdown\n[example]: local.md\n```\n[Link](local.md)\n````\n'
                  '~~~md\n[example]: local.md\n~~~\n'
                  '    [example]: local.md\n')
        self.assertEqual(render(source, REPO, "1.2.3"), source)

    def test_inline_local_links_fail_with_authoring_guidance(self):
        for source in ('[Guide](docs/guide.md)', '[Section](#usage)', '![Image](images/a.png)'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "reference definition"):
                render(source, REPO, "1.2.3")

    def test_parent_escape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "escapes the repository"):
            render('[bad]: ../outside.md\n', REPO, "1.2.3")

    def test_build_uses_only_readme_and_config_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                f'[project]\nversion = "9.8.7"\n[tool.specromancy-build]\nrepository = "{REPO}"\n')
            (root / "README.md").write_text('[Guide][guide]\n[guide]: omitted/guide.md\n')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = metadata(root)
            self.assertIn(f'{REPO}/blob/v9.8.7/omitted/guide.md', result['long_description'])
            self.assertEqual(result['project_urls']['Documentation'], f'{REPO}/blob/v9.8.7/docs/README.md')
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})


if __name__ == "__main__":
    unittest.main()
