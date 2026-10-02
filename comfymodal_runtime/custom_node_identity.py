"""Canonical, read-only identity resolution for one custom-node directory.

Identity is deliberately independent from publication packaging.  This module
only reads local metadata and never changes a checkout or contacts a remote.
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit
from typing import Any, Iterable, Mapping


HIGH_CONFIDENCE = "high"
MEDIUM_CONFIDENCE = "medium"
WEAK_CONFIDENCE = "weak"
AMBIGUOUS_CONFIDENCE = "ambiguous"


@dataclass(frozen=True)
class PluginIdentity:
    """The display identity and provenance of one plugin directory."""

    identity: str | None
    identity_source: str
    confidence: str
    comparison_key: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "identity_source": self.identity_source,
            "confidence": self.confidence,
        }


def _github_identity(parts: Any) -> tuple[str, str] | None:
    host = (parts.hostname or "").casefold()
    if host != "github.com":
        return None
    path = (parts.path or "").strip("/")
    bits = [unquote(bit) for bit in path.split("/") if bit]
    if len(bits) != 2:
        return None
    owner, repo = bits
    if repo.casefold().endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return None
    return owner, repo


def normalize_repository_url(value: str) -> str | None:
    """Normalize a repository URL while retaining display casing.

    GitHub URLs are reduced to their owner/repository pair.  Other hosts are
    normalized only enough to remove transport-only spelling differences; they
    remain distinct from GitHub and from one another.
    """
    raw = str(value or "").strip()
    if not raw:
        return None

    # SCP syntax (git@github.com:owner/repo.git) is not understood by
    # urlsplit.  Treat it as SSH without preserving credentials in the key.
    scp = re.match(r"^(?:[^@/\s]+@)?([^:/\s]+):(.+)$", raw)
    ssh_scp = re.match(r"^ssh://(?:[^@/\s]+@)?([^:/\s]+):(.+)$", raw)
    if ssh_scp:
        host, path = ssh_scp.groups()
        parts = urlsplit("ssh://" + host + "/" + path.lstrip("/"))
    elif scp and "://" not in raw:
        host, path = scp.groups()
        parts = urlsplit("ssh://" + host + "/" + path.lstrip("/"))
    else:
        candidate = raw
        if candidate.startswith("git+"):
            candidate = candidate[4:]
        parts = urlsplit(candidate)
        if not parts.scheme or not parts.netloc:
            return None

    github = _github_identity(parts)
    if github is not None:
        owner, repo = github
        return f"https://github.com/{owner}/{repo}"

    scheme = (parts.scheme or "https").casefold()
    hostname = (parts.hostname or "").casefold()
    if not hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    authority = hostname if port is None or default_port else f"{hostname}:{port}"
    path = (parts.path or "/").rstrip("/") or "/"
    return f"{scheme}://{authority}{path}"


def _run_git(path: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def _own_git_remotes(plugin: Path) -> tuple[list[str], bool]:
    """Return URLs only when ``plugin`` is the repository's own root."""
    git_marker = plugin / ".git"
    if not git_marker.exists():  # Do not let git -C walk into a parent repo.
        return [], False
    root = _run_git(plugin, ["rev-parse", "--show-toplevel"])
    if not root:
        return [], False
    try:
        if Path(root).resolve() != plugin.resolve():
            return [], False
    except OSError:
        return [], False

    remotes: list[str] = []
    for remote in _run_git(plugin, ["remote"]).splitlines():
        remote = remote.strip()
        if not remote:
            continue
        for mode in ([], ["--push"]):
            for url in _run_git(plugin, ["remote", "get-url", *mode, "--all", remote]).splitlines():
                normalized = normalize_repository_url(url)
                if normalized and normalized not in remotes:
                    remotes.append(normalized)
    return remotes, True


def _url_candidates_from_pyproject(plugin: Path) -> list[str]:
    path = plugin / "pyproject.toml"
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    project = raw.get("project")
    urls = project.get("urls") if isinstance(project, Mapping) else None
    if not isinstance(urls, Mapping):
        return []
    candidates: list[str] = []
    for key in ("Repository", "repository", "Homepage", "homepage"):
        value = urls.get(key)
        if isinstance(value, str):
            normalized = normalize_repository_url(value)
            if normalized and normalized not in candidates:
                candidates.append(normalized)
    return candidates


def _basename(plugin: Path) -> str:
    # Explicitly handle callers passing a trailing separator or mixed Windows
    # and POSIX separators before applying the weak fallback.
    raw = os.fspath(plugin).rstrip("/\\")
    return re.split(r"[/\\]", raw)[-1] if raw else ""


def _provenance_url(plugin: Path, provenance: Any) -> str | None:
    if isinstance(provenance, str):
        return normalize_repository_url(provenance)
    if not isinstance(provenance, Mapping):
        return None
    value = provenance.get("repo_url", provenance.get("repository_url"))
    return normalize_repository_url(value) if isinstance(value, str) else None


def resolve_plugin_identity(
    plugin_dir: str | Path,
    *,
    provenance: Mapping[str, Any] | str | None = None,
    basename_collisions: Iterable[str] = (),
) -> PluginIdentity:
    """Resolve one plugin using provenance, own-root git, pyproject, basename."""
    plugin = Path(plugin_dir)
    from_provenance = _provenance_url(plugin, provenance)
    if from_provenance:
        return PluginIdentity(from_provenance, "installation_provenance", HIGH_CONFIDENCE,
                              from_provenance.casefold())

    remotes, own_root = _own_git_remotes(plugin)
    if own_root and remotes:
        keys = {item.casefold() for item in remotes}
        if len(keys) != 1:
            return PluginIdentity(None, "git_remote_ambiguous", AMBIGUOUS_CONFIDENCE)
        display = next(item for item in remotes if item.casefold() == next(iter(keys)))
        return PluginIdentity(display, "git_remote", HIGH_CONFIDENCE, display.casefold())

    urls = _url_candidates_from_pyproject(plugin)
    if urls:
        keys = {item.casefold() for item in urls}
        if len(keys) != 1:
            return PluginIdentity(None, "pyproject_urls_ambiguous", AMBIGUOUS_CONFIDENCE)
        display = next(item for item in urls if item.casefold() == next(iter(keys)))
        return PluginIdentity(display, "pyproject_url", MEDIUM_CONFIDENCE, display.casefold())

    name = _basename(plugin)
    if not name:
        return PluginIdentity(None, "basename_missing", AMBIGUOUS_CONFIDENCE)
    if name.casefold() in {str(item).casefold() for item in basename_collisions}:
        return PluginIdentity(None, "basename_collision", AMBIGUOUS_CONFIDENCE)
    return PluginIdentity(name, "basename", WEAK_CONFIDENCE, f"basename:{name.casefold()}")


__all__ = ["PluginIdentity", "normalize_repository_url", "resolve_plugin_identity"]
