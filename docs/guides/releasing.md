# Publish a release through GitHub Actions

The manual [Release to PyPI workflow](../../.github/workflows/release.yml) takes
one full release-commit SHA. It builds one wheel and source distribution,
verifies them, creates the version tag, publishes them to TestPyPI, checks the
registry installation, and promotes those same files to PyPI. Nothing is published by ordinary pushes
or pull requests.

This is a maintainer workflow in GitHub Actions, separate from the engine's
consumer-defined pipelines. The engine itself never publishes packages.
Specromancy Engine targets Linux/macOS; Windows remains unverified.

## One-time setup

1. Merge `release.yml`, `tools/release.py`, their tests, and these instructions
   into the repository's default branch. GitHub only exposes a manual workflow
   when its definition exists on the default branch. Run this workflow from that
   branch; selecting another branch causes its jobs to be skipped.
2. Create and verify accounts on [TestPyPI](https://test.pypi.org/account/register/)
   and [PyPI](https://pypi.org/account/register/), including two-factor authentication
   and saved recovery codes. These are separate registries and account setups.
3. In the GitHub repository, open **Settings → Environments**. Create two
   environments named exactly `testpypi` and `pypi`. Restrict each environment's
   deployment branch to the default branch, normally `main`.
4. For a confirmation before the real upload, configure **Required reviewers**
   on `pypi`. A solo maintainer can select themselves and leave **Prevent
   self-review** unchecked. Required-reviewer availability depends on repository
   visibility and the GitHub plan. **Without a reviewer rule, the workflow
   automatically proceeds to PyPI after TestPyPI verification.** Merely naming
   an environment in YAML does not configure an approval rule.
5. On each registry, configure a GitHub Trusted Publisher using the table below.
   For a new project, use the account's **Publishing → Add a new pending
   publisher** page. For an existing project you own, use the project's
   **Manage → Publishing** page instead.

| Field | TestPyPI | PyPI |
| --- | --- | --- |
| PyPI project name (new project) | `specromancy-engine` | `specromancy-engine` |
| GitHub owner | `PavelGolitsyn` | `PavelGolitsyn` |
| Repository | `specromancy-engine` | `specromancy-engine` |
| Workflow filename | `release.yml` | `release.yml` |
| Environment | `testpypi` | `pypi` |

The tag job uses the workflow's `GITHUB_TOKEN` with job-scoped `contents: write`.
Repository or organization policy and tag rules must allow this job to create
`v*` tags. A permission or ruleset denial fails the job and prevents uploading;
the workflow does not bypass those rules or require a personal access token.

Enter the filename `release.yml`, not its full `.github/workflows/` path. Do not
add a PyPI API token to GitHub secrets. The publishing jobs use short-lived OIDC
credentials through PyPA's publishing action. A pending publisher creates the
project on first successful publication; it does not reserve the name in advance.

References: [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/),
[GitHub environment setup and availability](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
and [manual workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

## Prepare the release commit

1. Finish the release changes and merge them into the default branch. The
   workflow accepts only a full lowercase 40-character commit SHA in that
   branch's history, not a branch name, short SHA, or pull-request-only commit.
2. Set `project.version` in [`pyproject.toml`](../../pyproject.toml) to the intended
   release; this is the only version field to edit. The runtime `__version__`
   is derived automatically. Reinstall editable environments with
   `python -m pip install -e .` after a bump to refresh installed metadata.
   Keep general documentation version-neutral; update
   it when behavior or support changes, not for a version bump alone. Preserve
   versions in historical release evidence. Distribution tests read the project version;
   isolated release tests use their own fixture version, which should not be
   changed when bumping a release.
   The root `README.md` is also the package description on PyPI and TestPyPI.
   Keep local links as relative Markdown reference links, with single-line
   definitions such as `[installation]: docs/guides/installation.md`.
   The build converts their destinations to absolute GitHub URLs using
   `v<project.version>` and generates the Documentation project URL from the
   same version. No manual tag edits in README links are needed. See the
   [build metadata contract](distribution-verification.md#readme-build-metadata)
   for authoring conventions.
   The workflow reads the version from the selected commit's `pyproject.toml`;
   it does not edit files or bump versions. It currently accepts final
   `MAJOR.MINOR.PATCH` versions rather than prerelease versions.
3. Copy the full SHA from GitHub's commit page or run `git rev-parse HEAD` in a
   clean checkout of that commit. Save it with the release notes.
4. Include all linked documentation in the selected commit. You do not need to
   create or push a tag manually: after verification, the workflow creates
   `v<project.version>` at that exact commit, before uploading to TestPyPI.
   New tags are lightweight Git tags. An existing lightweight or annotated tag
   is accepted only if it resolves to the selected commit; a conflicting tag
   fails the release and is never moved or replaced. Builds can run before the
   tag exists, and the generated URLs start resolving once it is created.

## Trigger and follow the release

1. Open **Actions → Release to PyPI → Run workflow** in GitHub.
2. Leave the branch selector on the repository's default branch.
3. Paste the full release commit SHA into `release_commit` and click
   **Run workflow**. This authorizes creating the version tag and publishing to
   both registries, subject to any configured environment approvals.
4. Watch the jobs in order:

   ```text
   validate commit → build wheel + sdist once
       → verify on Linux/macOS × Python 3.11.15/3.14.4
       → create or verify the version tag at the release commit
       → upload to TestPyPI → verify hashes + clean installation
       → pypi environment approval (if configured)
       → upload the same files to PyPI → verify hashes + clean installation
   ```

5. If `pypi` requires review, open **Review deployments** after TestPyPI checks
   pass. Inspect the release SHA, version, artifact hashes, verification jobs,
   and TestPyPI page before approving. Check that the README renders correctly
   and its documentation, example, and directory links open successfully;
   package installation checks do not verify these links. Approval promotes
   the already-built files; it does not rebuild them.
6. A successful final `pypi-smoke` job confirms that both files are visible on
   PyPI with the expected hashes and the downloaded wheel installs successfully.
   Users can then install that release, replacing `<version>` with the version
   reported by the workflow:

   ```sh
   python -m pip install "specromancy-engine==<version>"
   ```

Download the `release-distributions-<attempt>` artifact and verification logs
from the Actions run if you want to attach packages to a GitHub Release.
The run summary records the source commit, workflow commit, and package hashes.
Artifacts are retained for 90 days, subject to repository retention limits;
keep permanent release evidence separately if needed.

## What the gates enforce

- Release control comes from the workflow's pinned default-branch commit. The
  package and its tests come from the selected release commit. All checkouts
  disable persisted Git credentials.
- Builds and tests have no OIDC publishing permission. Only the two upload jobs
  have `id-token: write`; they do not build or execute the engine. All actions
  are pinned to commit SHAs.
- Only the tag job has `contents: write`. It runs the release helper from the
  pinned default-branch workflow commit, receives the validated commit and
  version from preparation, and never builds or executes candidate package code.
  It creates the tag through the GitHub API and verifies its resolved commit
  before allowing TestPyPI publication. It never updates or deletes a tag.
- All four matrix entries run the full suite, check generated adapters, and
  verify the same downloaded wheel and sdist, including an offline sdist rebuild.
  Rebuilt wheels are verification outputs, never substituted for the release wheel.
- Downstream jobs download the specific artifact ID from this run and compare
  both file hashes with the build job's outputs. The upload directory must
  contain exactly the two selected package files.
- Before either upload, registry metadata is checked for conflicting filenames,
  differing hashes, or yanked files. Identical files can be skipped on retry.
  After upload, both registry hashes must match. A fresh environment downloads
  the wheel with pip's hash enforcement, installs it outside the checkout,
  checks its version, and exercises both CLI entry points.
- Registry checks and downloads retry briefly for propagation delays. A failed
  TestPyPI upload or smoke check prevents PyPI promotion. A failure after a PyPI
  upload reports failure but cannot undo files that are already public.
- Concurrent releases are serialized; a new trigger does not cancel an upload
  already in progress.

## Recover a failed run

For a transient upload, registry, or smoke failure, use **Re-run failed jobs**
on the original Actions run. Successful build outputs and the retained artifact
ID are reused. The preflight accepts already-uploaded files only if their hashes
match; it can safely finish an upload that published just one of the two files.

The same retry applies if tag creation fails or its response is interrupted.
The job accepts a matching tag left by a previous attempt, including one created
despite a lost response. A tag remains if a later publishing step fails; do not
delete or move it to retry. Fix permission/ruleset failures before rerunning the
failed job. A conflicting tag requires selecting the correct release commit or
preparing a new version, rather than overwriting the existing tag.

Do not use **Re-run all jobs** or start a new run to promote an already-uploaded
candidate. A fresh build can have different archive bytes even at the same
commit, and the registry conflict check will reject it. Re-running a failed
build before any upload is fine. If retained artifacts expire, recover the
original verified files and review recovery separately; do not disable the hash
checks or replace published files.

For a metadata/version conflict, fix the cause before trying again. A published
version's filenames cannot be reused for corrected bytes. If package contents
need correction after publication, prepare a new version and
repeat the release checks. Do not delete a release as a way to reuse its filenames.

Local tests and workflow linting cannot prove your account's Trusted Publisher
or environment configuration. The first real run verifies those external
settings. The workflow creates Git tags and publishes packages; GitHub Release
notes and attachments remain a separate maintainer action.
