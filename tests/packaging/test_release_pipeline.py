"""Release safety checks, using temporary Git repositories and mocked registries."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_tool", ROOT / "tools/release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleasePipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "distributions"
        self.directory.mkdir()
        self.names = release.filenames("0.1.1")
        self.hashes = tuple(hashlib.sha256(name.encode()).hexdigest() for name in self.names)
        self.expected = dict(zip(self.names, self.hashes))
        for name in self.names:
            (self.directory / name).write_text(name)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def repository(self):
        self.git("init", "--quiet")
        self.git("config", "user.email", "release-test@example.invalid")
        self.git("config", "user.name", "Release test")
        project = self.root / "pyproject.toml"
        project.write_text('[project]\nname = "specromancy-engine"\nversion = "0.1.1"\n')
        self.git("add", "pyproject.toml")
        self.git("commit", "--quiet", "-m", "release candidate")
        return self.git("rev-parse", "HEAD")

    def test_resolve_commit_reads_selected_metadata_not_working_tree(self):
        commit = self.repository()
        self.git("tag", "v0.1.0")
        (self.root / "pyproject.toml").write_text("broken working tree")
        result = release.prepare(self.root, commit, commit)
        self.assertEqual(result, {"commit": commit, "version": "0.1.1",
                                 "wheel": self.names[0], "sdist": self.names[1]})
        self.assertEqual((self.root / "pyproject.toml").read_text(), "broken working tree")

    def test_rejects_mutable_refs_and_shell_or_output_injection(self):
        for value in ("main", "v0.1.0", "1234abc", "a" * 40 + "\nversion=9.9.9", "$(id)"):
            with self.subTest(value=value), self.assertRaisesRegex(release.ReleaseError, "full"):
                release.prepare(self.root, value, "a" * 40)

    def test_rejects_commit_outside_selected_default_branch_history(self):
        base = self.repository()
        self.git("tag", "v0.1.0")
        self.git("commit", "--allow-empty", "--quiet", "-m", "not merged into selected default")
        other = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(release.ReleaseError, "default-branch history"):
            release.prepare(self.root, other, base)
        self.assertEqual(release.prepare(self.root, base, other)["commit"], base)

    def test_accepts_matching_annotated_tag_and_rejects_conflicting_tag(self):
        commit = self.repository()
        self.git("tag", "-a", "v0.1.0", "-m", "release")
        release.prepare(self.root, commit, commit)
        self.git("commit", "--allow-empty", "--quiet", "-m", "another candidate")
        other = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(release.ReleaseError, "tag points to a different commit"):
            release.prepare(self.root, other, other)

    def test_prepare_allows_missing_tag_without_creating_it(self):
        commit = self.repository()
        self.assertEqual(release.prepare(self.root, commit, commit)["commit"], commit)
        self.assertEqual(self.git("tag", "--list"), "")

    def test_rejects_wrong_project_and_nonfinal_version(self):
        self.repository()
        for name, version in (("another-project", "0.1.1"), ("specromancy-engine", "0.1.0rc1")):
            (self.root / "pyproject.toml").write_text(
                f'[project]\nname = "{name}"\nversion = "{version}"\n')
            self.git("add", "pyproject.toml")
            self.git("commit", "--quiet", "-m", "invalid release metadata")
            commit = self.git("rev-parse", "HEAD")
            with self.assertRaises(release.ReleaseError):
                release.prepare(self.root, commit, commit)

    def test_artifacts_require_exact_files_and_hashes(self):
        self.assertEqual(release.check_files(self.directory, "0.1.1", self.hashes), self.expected)
        (self.directory / "stale.whl").write_text("stale")
        with self.assertRaisesRegex(release.ReleaseError, "exactly"):
            release.check_files(self.directory, "0.1.1", self.hashes)
        (self.directory / "stale.whl").unlink()
        (self.directory / self.names[0]).write_text("tampered")
        with self.assertRaisesRegex(release.ReleaseError, "hash mismatch"):
            release.check_files(self.directory, "0.1.1", self.hashes)

    def test_rejects_missing_or_symlink_artifact(self):
        wheel = self.directory / self.names[0]
        wheel.unlink()
        with self.assertRaisesRegex(release.ReleaseError, "exactly"):
            release.check_files(self.directory, "0.1.1", self.hashes)
        target = self.root / "target"
        target.write_text(self.names[0])
        wheel.symlink_to(target)
        with self.assertRaisesRegex(release.ReleaseError, "regular artifact"):
            release.check_files(self.directory, "0.1.1", self.hashes)

    def registry(self):
        return {"urls": [{"filename": name, "digests": {"sha256": digest}, "yanked": False}
                         for name, digest in self.expected.items()]}

    def test_retry_accepts_only_identical_existing_files(self):
        data = self.registry()
        self.assertTrue(release.inspect_registry(data, self.expected, True))
        self.assertTrue(release.inspect_registry(data, self.expected, False))
        data["urls"].pop()
        self.assertTrue(release.inspect_registry(data, self.expected, True))
        self.assertFalse(release.inspect_registry(data, self.expected, False))
        data["urls"][0]["digests"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(release.ReleaseError, "different bytes"):
            release.inspect_registry(data, self.expected, True)

    def test_yanked_unexpected_and_duplicate_registry_files_fail(self):
        for kind in ("yanked", "unexpected", "duplicate"):
            data = self.registry()
            if kind == "yanked":
                data["urls"][0]["yanked"] = True
            elif kind == "unexpected":
                data["urls"][0]["filename"] = "another.whl"
            else:
                data["urls"].append(data["urls"][0])
            with self.subTest(kind=kind), self.assertRaises(release.ReleaseError):
                release.inspect_registry(data, self.expected, True)

    def test_registry_waits_for_propagation_but_does_not_retry_conflicts(self):
        absent = urllib.error.HTTPError("https://test.pypi.org", 404, "not found", {}, None)
        self.addCleanup(absent.close)
        found = io.BytesIO(json.dumps(self.registry()).encode())
        with patch.object(release.urllib.request, "urlopen", side_effect=[absent, found]) as request:
            with patch.object(release.time, "sleep") as sleep:
                release.check_registry("testpypi", "0.1.1", self.expected, attempts=2)
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(10)
        conflicting = self.registry()
        conflicting["urls"][0]["digests"]["sha256"] = "0" * 64
        with patch.object(release.urllib.request, "urlopen",
                          return_value=io.BytesIO(json.dumps(conflicting).encode())) as request:
            with self.assertRaisesRegex(release.ReleaseError, "different bytes"):
                release.check_registry("pypi", "0.1.1", self.expected)
        request.assert_called_once()

    def test_missing_registry_release_allowed_only_before_upload(self):
        absent = urllib.error.HTTPError("https://test.pypi.org", 404, "not found", {}, None)
        self.addCleanup(absent.close)
        with patch.object(release.urllib.request, "urlopen", side_effect=absent):
            release.check_registry("testpypi", "0.1.1", self.expected, allow_missing=True)
            with self.assertRaisesRegex(release.ReleaseError, "both published files"):
                release.check_registry("testpypi", "0.1.1", self.expected, attempts=1)

    def test_authentication_error_is_not_treated_as_an_empty_registry(self):
        denied = urllib.error.HTTPError("https://pypi.org", 403, "forbidden", {}, None)
        self.addCleanup(denied.close)
        with patch.object(release.urllib.request, "urlopen", side_effect=denied):
            with self.assertRaises(urllib.error.HTTPError):
                release.check_registry("pypi", "0.1.1", self.expected, allow_missing=True)

    def test_smoke_enforces_hash_and_isolates_index_and_imports(self):
        calls = []

        def run(argv, *, cwd, env, check):
            calls.append(argv)
            self.assertNotEqual(cwd, ROOT)
            self.assertNotIn("PYTHONPATH", env)
            self.assertNotIn("PIP_EXTRA_INDEX_URL", env)
            self.assertEqual(env["PIP_CONFIG_FILE"], release.os.devnull)
            if "download" in argv:
                requirements = Path(argv[argv.index("-r") + 1]).read_text()
                self.assertEqual(requirements,
                                 f"specromancy-engine==0.1.1 --hash=sha256:{self.hashes[0]}\n")
                self.assertIn("--require-hashes", argv)
                self.assertIn("--no-deps", argv)
                self.assertEqual(argv[argv.index("--index-url") + 1],
                                 "https://test.pypi.org/simple/")
            return subprocess.CompletedProcess(argv, 0)

        with patch.dict(release.os.environ, {"PYTHONPATH": "/unwanted",
                                            "PIP_EXTRA_INDEX_URL": "https://unwanted.invalid"}):
            with patch.object(release.venv.EnvBuilder, "create"):
                with patch.object(release.subprocess, "run", side_effect=run):
                    release.smoke("testpypi", "0.1.1", self.hashes[0])
        self.assertEqual(len(calls), 5)
        self.assertIn("--no-index", calls[1])
        self.assertIn("-I", calls[2])
        self.assertEqual(calls[-1][-3:], ["-m", "specromancy_engine", "--help"])

    def test_smoke_never_installs_after_download_failure(self):
        with patch.object(release.venv.EnvBuilder, "create"):
            with patch.object(release.time, "sleep"):
                with patch.object(release.subprocess, "run",
                                  return_value=subprocess.CompletedProcess([], 1)) as run:
                    with self.assertRaisesRegex(release.ReleaseError, "download the verified wheel"):
                        release.smoke("pypi", "0.1.1", self.hashes[0])
        self.assertEqual(run.call_count, 12)
        self.assertTrue(all("download" in call.args[0] for call in run.call_args_list))


class ReleaseTagTests(unittest.TestCase):
    commit = "a" * 40
    tag_object = "b" * 40

    def response(self, data):
        return io.BytesIO(json.dumps(data).encode())

    def reference(self, sha=None, kind="commit"):
        return {"ref": "refs/tags/v0.1.0", "object": {"type": kind, "sha": sha or self.commit}}

    def error(self, status):
        return urllib.error.HTTPError("https://api.github.com", status, "API error", {}, None)

    def ensure(self):
        release.ensure_tag("owner/repo", "0.1.1", self.commit, "test-token")

    def test_creates_exact_tag_then_verifies_remote_and_retry_does_not_write(self):
        responses = [self.error(404), self.response(self.reference()),
                     self.response(self.reference()), self.response(self.reference())]
        with patch.object(release.urllib.request, "urlopen", side_effect=responses) as request:
            self.ensure()
            self.ensure()
        requests = [call.args[0] for call in request.call_args_list]
        self.assertEqual([req.get_method() for req in requests], ["GET", "POST", "GET", "GET"])
        self.assertEqual(requests[1].full_url, "https://api.github.com/repos/owner/repo/git/refs")
        self.assertEqual(json.loads(requests[1].data), {"ref": "refs/tags/v0.1.0", "sha": self.commit})
        self.assertEqual(requests[0].full_url, "https://api.github.com/repos/owner/repo/git/ref/tags/v0.1.0")
        self.assertTrue(all(req.get_header("Authorization") == "Bearer test-token" for req in requests))

    def test_accepts_matching_annotated_tag_without_writes(self):
        responses = [self.response(self.reference(self.tag_object, "tag")),
                     self.response({"object": {"type": "commit", "sha": self.commit}})]
        with patch.object(release.urllib.request, "urlopen", side_effect=responses) as request:
            self.ensure()
        self.assertTrue(all(call.args[0].get_method() == "GET" for call in request.call_args_list))
        self.assertTrue(request.call_args.args[0].full_url.endswith(f"/tags/{self.tag_object}"))

    def test_rejects_conflicting_lightweight_and_annotated_tags_without_writes(self):
        for responses in ([self.response(self.reference("c" * 40))],
                          [self.response(self.reference(self.tag_object, "tag")),
                           self.response({"object": {"type": "commit", "sha": "c" * 40}})]):
            with patch.object(release.urllib.request, "urlopen", side_effect=responses) as request:
                with self.assertRaisesRegex(release.ReleaseError, "refusing to replace"):
                    self.ensure()
            self.assertTrue(all(call.args[0].get_method() == "GET" for call in request.call_args_list))

    def test_create_race_or_uncertain_response_requires_matching_remote_tag(self):
        for status in (409, 422, 500, "timeout"):
            for target in (self.commit, "c" * 40):
                error = TimeoutError() if status == "timeout" else self.error(status)
                responses = [self.error(404), error, self.response(self.reference(target))]
                with self.subTest(status=status, target=target):
                    with patch.object(release.urllib.request, "urlopen", side_effect=responses) as request:
                        if target == self.commit:
                            self.ensure()
                        else:
                            with self.assertRaisesRegex(release.ReleaseError, "refusing to replace"):
                                self.ensure()
                    self.assertEqual([call.args[0].get_method() for call in request.call_args_list],
                                     ["GET", "POST", "GET"])

    def test_failed_or_unconfirmed_creation_cannot_report_success(self):
        cases = ([self.error(404), self.error(422), self.error(404)],
                 [self.error(404), self.response(self.reference()), self.error(404)],
                 [self.error(404), TimeoutError(), self.error(404)])
        for responses in cases:
            with patch.object(release.urllib.request, "urlopen", side_effect=responses):
                with self.assertRaises((release.ReleaseError, urllib.error.HTTPError, TimeoutError)):
                    self.ensure()

    def test_permission_failures_are_not_missing_tags_and_do_not_retry_writes(self):
        for responses in ([self.error(403)], [self.error(404), self.error(403)]):
            with patch.object(release.urllib.request, "urlopen", side_effect=responses) as request:
                with self.assertRaises(urllib.error.HTTPError):
                    self.ensure()
            self.assertEqual(request.call_count, len(responses))

    def test_invalid_inputs_are_rejected_before_network_access(self):
        for repository, version, commit, token in (
            ("owner/../repo", "0.1.1", self.commit, "token"),
            ("owner/repo", "0.1.1/other", self.commit, "token"),
            ("owner/repo", "0.1.1", "main", "token"),
            ("owner/repo", "0.1.1", self.commit, ""),
        ):
            with patch.object(release.urllib.request, "urlopen") as request:
                with self.assertRaises(release.ReleaseError):
                    release.ensure_tag(repository, version, commit, token)
                request.assert_not_called()

    def test_annotated_tag_cycles_and_noncommit_targets_fail(self):
        for responses in (
            [self.response(self.reference(self.tag_object, "tag")),
             self.response({"object": {"type": "tag", "sha": self.tag_object}})],
            [self.response(self.reference(self.commit, "tree"))],
        ):
            with patch.object(release.urllib.request, "urlopen", side_effect=responses):
                with self.assertRaises(release.ReleaseError):
                    self.ensure()

    def test_workflow_isolates_write_permission_and_gates_publication_on_tag(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        sections = re.split(r"^  ([a-z][a-z0-9-]*):\n", workflow.split("jobs:\n", 1)[1], flags=re.MULTILINE)
        jobs = dict(zip(sections[1::2], sections[2::2]))
        self.assertIn("needs: [prepare, build, verify]", jobs["tag"])
        self.assertIn("needs: [prepare, build, verify, tag]", jobs["testpypi"])
        self.assertEqual([name for name, body in jobs.items() if "contents: write" in body], ["tag"])
        self.assertNotIn("id-token: write", jobs["tag"])
        self.assertIn("ref: ${{ github.sha }}", jobs["tag"])
        self.assertIn("persist-credentials: false", jobs["tag"])
        self.assertIn("RELEASE_COMMIT: ${{ needs.prepare.outputs.commit }}", jobs["tag"])
        self.assertNotIn("pip install", jobs["tag"])
        self.assertNotIn("python -m build", jobs["tag"])


if __name__ == "__main__":
    unittest.main()
