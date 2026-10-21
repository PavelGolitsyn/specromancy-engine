# Publish a release through GitHub Actions

The manual [Release to PyPI workflow](../../.github/workflows/release.yml) takes
one full release-commit SHA. It builds one wheel and source distribution,
verifies them, publishes them to TestPyPI, checks the registry installation,
and promotes those same files to PyPI. Nothing is published by ordinary pushes
or pull requests.

This is a maintainer workflow in GitHub Actions, separate from the engine's
consumer-defined pipelines. The engine itself never publishes packages.
Version 0.1.0 targets Linux/macOS; Windows remains unverified.

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
| Repository | `specromancy` | `specromancy` |
| Workflow filename | `release.yml` | `release.yml` |
| Environment | `testpypi` | `pypi` |

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
2. Confirm that `pyproject.toml`, the runtime `__version__`, version-specific
   tests, documentation, and project URLs describe the intended release.
   The workflow reads the version from the selected commit's `pyproject.toml`;
   it does not edit files or bump versions. It currently accepts final
   `MAJOR.MINOR.PATCH` versions, such as `0.1.0`, rather than prerelease versions.
3. Copy the full SHA from GitHub's commit page or run `git rev-parse HEAD` in a
   clean checkout of that commit. Save it with the release notes.
4. Ensure version-specific documentation URLs resolve before publishing. If
   they use `v0.1.0`, create and push that tag for the selected commit. For
   version 0.1.0, from the verified checkout:

   ```sh
   git tag -a v0.1.0 -m "Specromancy Engine v0.1.0"
   git push origin v0.1.0
   ```

   If the tag already exists, verify it points to your selected commit rather
   than recreating or moving it. The workflow rejects an existing version tag
   that points elsewhere. It does not create tags or GitHub Releases.

## Trigger and follow the release

1. Open **Actions → Release to PyPI → Run workflow** in GitHub.
2. Leave the branch selector on the repository's default branch.
3. Paste the full release commit SHA into `release_commit` and click
   **Run workflow**. This authorizes publishing to both registries, subject to
   any configured environment approvals.
4. Watch the jobs in order:

   ```text
   validate commit → build wheel + sdist once
       → verify on Linux/macOS × Python 3.11.15/3.14.4
       → upload to TestPyPI → verify hashes + clean installation
       → pypi environment approval (if configured)
       → upload the same files to PyPI → verify hashes + clean installation
   ```

5. If `pypi` requires review, open **Review deployments** after TestPyPI checks
   pass. Inspect the release SHA, version, artifact hashes, verification jobs,
   and TestPyPI page before approving. Approval promotes the already-built
   files; it does not rebuild them.
6. A successful final `pypi-smoke` job confirms that both files are visible on
   PyPI with the expected hashes and the downloaded wheel installs successfully.
   Users can then run:

   ```sh
   python -m pip install specromancy-engine==0.1.0
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

Do not use **Re-run all jobs** or start a new run to promote an already-uploaded
candidate. A fresh build can have different archive bytes even at the same
commit, and the registry conflict check will reject it. Re-running a failed
build before any upload is fine. If retained artifacts expire, recover the
original verified files and review recovery separately; do not disable the hash
checks or replace published files.

For a metadata/version conflict, fix the cause before trying again. A published
version's filenames cannot be reused for corrected bytes. If package contents
need correction after publication, prepare a new version, such as `0.1.1`, and
repeat the release checks. Do not delete a release as a way to reuse its filenames.

Local tests and workflow linting cannot prove your account's Trusted Publisher
or environment configuration. The first real run verifies those external
settings. The workflow only publishes packages; GitHub Release notes and
attachments remain a separate maintainer action.
