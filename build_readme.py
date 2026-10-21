"""Build-only README metadata, independent of Git and the engine runtime.

Local README destinations use single-line Markdown reference definitions.
Directory destinations end in '/'; image references use labels beginning with
'image-'. These explicit conventions also work in an sdist that omits the
linked repository files. Inline links should use absolute URLs.
"""
from __future__ import annotations

from pathlib import Path
import posixpath
import re
import tomllib
from urllib.parse import quote, urlsplit, urlunsplit


REFERENCE = re.compile(r"^( {0,3}\[([^\]\n]+)\]:[ \t]*)(<[^>\n]+>|\S+)(.*)$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def absolute_url(destination: str, repository: str, version: str, *, image: bool = False) -> str:
    """Resolve a repository-root destination without inspecting the filesystem."""
    parts = urlsplit(destination)
    if parts.scheme or parts.netloc:
        return destination
    path = posixpath.normpath(parts.path.lstrip("/") or "README.md")
    if path == ".." or path.startswith("../") or "\\" in path:
        raise ValueError(f"README link escapes the repository: {destination}")
    tag = quote(f"v{version}", safe="")
    kind = "tree" if parts.path.endswith("/") else "blob"
    if image:
        # GitHub's raw endpoint serves image bytes instead of an HTML file view.
        kind = "raw"
    path = quote(path, safe="/%:@!$&'()*+,;=-._~")
    base = f"{repository.rstrip('/')}/{kind}/{tag}/{path}"
    return urlunsplit((*urlsplit(base)[:3], parts.query, parts.fragment))


def render_readme(source: str, repository: str, version: str) -> str:
    """Rewrite reference destinations, preserving prose, titles, and code blocks."""
    result = []
    fence = ""
    for line in source.splitlines(keepends=True):
        marker = FENCE.match(line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = ""
            result.append(line)
            continue
        if marker:
            fence = marker[1]
            result.append(line)
            continue
        match = REFERENCE.match(line)
        if match:
            target = match[3]
            angled = target.startswith("<")
            url = absolute_url(target[1:-1] if angled else target, repository, version,
                               image=match[2].lower().startswith("image-"))
            if angled:
                url = f"<{url}>"
            line = line[:match.start(3)] + url + line[match.end(3):]
        elif not line.startswith(("    ", "\t")):
            prose = re.sub(r"(`+).*?\1", "", line)
            for inline in re.finditer(r"\]\(<?([^\s)>]+)", prose):
                parts = urlsplit(inline[1])
                if not parts.scheme and not parts.netloc:
                    raise ValueError("Use a Markdown reference definition for local README links: "
                                     + inline[1])
        result.append(line)
    return "".join(result)


def build_metadata(root: Path) -> dict:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = config["project"]["version"]
    repository = config["tool"]["specromancy-build"]["repository"]
    return {
        "long_description": render_readme((root / "README.md").read_text(encoding="utf-8"),
                                          repository, version),
        "long_description_content_type": "text/markdown",
        "project_urls": {
            "Homepage": repository,
            "Documentation": absolute_url("docs/README.md", repository, version),
            "Issues": f"{repository}/issues",
        },
    }
