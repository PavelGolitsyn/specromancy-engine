"""Resolve the version from this source checkout or installed metadata."""

from importlib.metadata import version
from pathlib import Path
import tomllib


def get_version() -> str:
    package = Path(__file__).resolve().parent
    project_file = package.parent.parent / "pyproject.toml"
    # Only the producer's src layout can supply checkout metadata. Never search
    # the working directory or prefer an unrelated installed distribution.
    if package.parent.name == "src" and project_file.is_file():
        with project_file.open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
        if project.get("name") == "specromancy-engine":
            return project["version"]
    return version("specromancy-engine")
