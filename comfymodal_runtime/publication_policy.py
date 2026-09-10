"""Pure publication policy shared by archive, image, and identity builders.

This module deliberately imports only the Python standard library.  It is the
single source of truth for names which are local control-plane state,
credentials, caches, or generated output and must not be published.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
import stat
from pathlib import Path
from typing import Iterator


_log = logging.getLogger(__name__)


# Directory names are matched at every depth.  Keep this set intentionally
# conservative: these are either local state/build products or directories
# which have never been part of the published custom-node source tree.
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({
    ".git", ".slim", ".commandcode", ".opencode", ".runtime_state",
    "__pycache__", "node_modules", ".venv", "venv", ".ipynb_checkpoints",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".eggs",
    ".cache", ".repowise", "ra11f", "reports", "example_workflows",
    "workflows", "wheelhouse", "wheels", "build", "dist", "artifacts",
    "output", "test-results", "playwright-report", "playwright/.cache",
    ".playwright-mcp", ".experiments", ".run_history", "benchmark_runs",
    "benchmark_logs", "optimization_logs", ".comfymodal_experiments",
    ".custom_node_requirements", ".baked_custom_node_deps", ".presets",
    ".preset_blobs", ".v2ctl", ".comfymodal_control", "tests", "test", "examples", "benchmarks",
    "benchmark", "traces", "logs", "scripts", ".github", "MagicMock",
    "reference", "docs",
})

# Compatibility spelling used by existing callers/tests.
EXCLUDED_DIRS = EXCLUDED_DIR_NAMES

EXCLUDED_FILENAMES: frozenset[str] = frozenset({
    # 1.3.1 legacy-cleanup evidence (KEEP): the .studio_* entries below are
    # still the live Studio authority (snapshots/presets/backends JSON) with
    # active test dependents (test_runtime_deployment_spec,
    # test_studio_runtime gitignore/compat tests, publication-guard tests).
    # Per the conditional-removal contract they must not be removed.
    ".gitignore", ".env", ".civitai_token", ".hf_token",
    ".modal_workspaces.json", ".deployed_state.json", ".modal_settings.json",
    ".deployed_version", ".deploy_log", "modal_logs.txt", "_deploy_output.log",
    ".custom_nodes.json", "custom_nodes_generation.json",
    ".last_v2_dependency_cache_identity.json", ".last_custom_node_context_manifest.json",
    "comfymodal_experiment_presets.json", "comfymodal_experiment_state.json",
    ".studio_presets.json", ".studio_snapshots.json", ".studio_backends.json",
    ".studio_workflows.json", ".studio_workflow_versions.json",
    ".studio_workflow_mappings.json", ".studio_workflow_presets.json",
    ".studio_model_library.json", ".studio_custom_nodes.json",
    ".studio_workflow_compatibility.json", ".deploy_warmup_state.json",
    "latest_benchmark_workflow.json", "apply_experiment_preset.py",
    "run_experiment_stage.py", "BENCHMARK_WORKFLOW.md",
    "i2i-check.json", "stack-input-values.json", "current-auto-preview.json",
})

EXCLUDED_EXTENSIONS: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".md", ".tmp", ".ref", ".log", ".trace", ".jsonl",
    ".whl", ".patch", ".diff", ".gz", ".zip", ".tar", ".bundle",
})

EXCLUDED_PREFIXES: tuple[str, ...] = (
    "before_v2_", "before_", "benchmark_", "trace_", "AUDIT_",
)
EXCLUDED_INFIXES: tuple[str, ...] = (".v21610_backup",)
GENERATED_JSON_PREFIXES: tuple[str, ...] = (
    "temp_", "_last_", "studio-", "clean_", "latest_benchmark_",
    ".modal_", ".model_", ".last_", ".profile_",
)
IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
})
EXCLUDED_GLOBS: tuple[str, ...] = (
    ".env.*", ".experiment_leases.db*", "*_runtime.json", ".studio_*.tmp",
    "audit-*.png", "comfyui-home.png", "*-current.png", "*-grid.png",
    "workflow-cards.png", "workflow-oriented-results.png",
    "results-page-current.png", "setup-page-current.png", "modal-body-*.json",
    "status-after-*.json", "summary-status-*.json", "setup-body-debug.json",
    "setup-eval.json", "setup-console-errors*.txt", "setup-console-warnings*.txt",
    "playwright-*.md",
)

# The deployment identity builder hashes source code only.  Publication
# generation is deliberately broader: it covers every included semantic file,
# including JSON configuration consumed by custom nodes.
IDENTITY_SOURCE_EXTENSIONS: frozenset[str] = frozenset({".py", ".js", ".mjs"})
GENERATION_SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".mjs", ".txt", ".toml", ".cfg", ".json",
})
ALLOWED_SOURCE_EXTENSIONS = IDENTITY_SOURCE_EXTENSIONS

# These are the text formats for which the existing source identity contract
# treats CRLF and LF as equivalent.  Other included files, including binary
# assets, are hashed byte-for-byte.
CANONICAL_TEXT_EXTENSIONS: frozenset[str] = GENERATION_SOURCE_EXTENSIONS

LOCAL_CLONE_RE = re.compile(
    r"^comfyui-modal-(?:agent\d+(?:[-_].*)?|agent[-_].*|worktree(?:[-_].*)?|wt(?:[-_].*)?|dc\d+)$",
    re.IGNORECASE,
)

COMFYMODAL_CANONICAL_NODE_NAME = "comfyui-modal"
COMFYMODAL_DUPLICATE_TYPO_NAMES = frozenset({"comyui-modal-pagesfile-probe"})
COMFYMODAL_LOCAL_CUSTOM_NODES_ENV = "COMFYMODAL_LOCAL_CUSTOM_NODES"

# The custom-node source is a shared resource.  Keep its Volume and the one
# app allowed to mutate it independent of whichever Golden app consumes it.
CUSTOM_NODES_VOLUME_NAME = "comfyui-custom-nodes"
CUSTOM_NODES_PUBLISHER_APP_NAME = "comfyui-custom-nodes-publisher"


def is_local_clone_name(name: str) -> bool:
    """Return whether *name* is a known local agent/worktree clone."""
    return bool(LOCAL_CLONE_RE.fullmatch(str(name)))


def comfymodal_duplicate_reason(node_name: str, node_path: str | os.PathLike[str]) -> str | None:
    """Return the safety reason for a second ComfyModal checkout.

    Names alone are intentionally insufficient: a valid node called
    ``comfyui-modal`` remains publishable, while renamed copies are rejected
    when their git metadata or source markers identify them as this plugin.
    """
    if str(node_name).casefold() == COMFYMODAL_CANONICAL_NODE_NAME.casefold():
        return None
    if str(node_name).casefold() in {
        name.casefold() for name in COMFYMODAL_DUPLICATE_TYPO_NAMES
    }:
        return "comfymodal_duplicate_typo"
    path = os.fspath(node_path)
    try:
        git_path = os.path.join(path, ".git")
        if os.path.isfile(git_path):
            with open(git_path, "r", encoding="utf-8", errors="replace") as handle:
                git_line = (handle.read(512) or "").strip()
            if git_line.lower().startswith("gitdir:"):
                git_dir = git_line.split(":", 1)[1].strip()
                if not os.path.isabs(git_dir):
                    git_dir = os.path.join(path, git_dir)
                normalized = os.path.normpath(git_dir).replace("\\", "/")
                if ".git/worktrees/" in normalized and "comfyui-modal" in normalized.casefold():
                    return "comfymodal_duplicate_worktree"
        elif os.path.isdir(git_path):
            config_path = os.path.join(git_path, "config")
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8", errors="replace") as handle:
                    if "comfyui-modal.git" in handle.read(4096).casefold():
                        return "comfymodal_duplicate_worktree"
        if (
            os.path.isfile(os.path.join(path, "comfyapp.py"))
            and os.path.isdir(os.path.join(path, "comfymodal_runtime"))
            and os.path.isfile(os.path.join(path, "comfymodal_runtime", "modal_app.py"))
        ):
            return "comfymodal_duplicate_worktree"
    except (OSError, UnicodeError):
        # A failed safety probe must not make an otherwise valid node
        # disappear.  The archive/image callers still apply all other rules.
        return None
    return None


# Descriptive compatibility spelling for callers that need the old predicate
# name without carrying the implementation outside the shared policy.
is_comfymodal_duplicate_dir = comfymodal_duplicate_reason


def is_excluded_dir_name(name: str) -> bool:
    """Return whether a bare directory name is excluded at any depth."""
    value = str(name)
    lowered = value.casefold()
    return (
        lowered in {item.casefold() for item in EXCLUDED_DIR_NAMES}
        or lowered.startswith(tuple(prefix.casefold() for prefix in EXCLUDED_PREFIXES))
        or any(infix.casefold() in lowered for infix in EXCLUDED_INFIXES)
        or is_local_clone_name(value)
    )


def custom_node_filter_reason(node_name: str, node_path: str | os.PathLike[str]) -> str | None:
    """Return the canonical top-level custom-node publication decision."""
    path = os.fspath(node_path)
    if not os.path.isdir(path):
        return "not_directory"
    if os.path.islink(path):
        return "symlink"
    if str(node_name).startswith("."):
        return "hidden_directory"
    if is_excluded_dir_name(node_name):
        return "generated_or_environment_directory"
    if is_local_clone_name(node_name):
        return "local_agent_or_worktree_clone"
    return comfymodal_duplicate_reason(node_name, path)


def iter_syncable_custom_node_dirs(root: str | Path) -> list[str]:
    """Return the one canonical list used by archive, image, volume and hash."""
    root_path = os.fspath(root)
    if not os.path.isdir(root_path):
        return []
    return sorted(
        name for name in os.listdir(root_path)
        if custom_node_filter_reason(name, os.path.join(root_path, name)) is None
    )


def _looks_like_custom_nodes_source_root(path: str | os.PathLike[str]) -> bool:
    # Keep this private historical spelling as a compatibility wrapper.  Root
    # selection itself lives in custom_node_root so every caller gets the same
    # worktree/explicit-root policy.
    from .custom_node_root import looks_like_custom_nodes_root

    return looks_like_custom_nodes_root(path)


def resolve_custom_nodes_root(
    anchor: str | Path,
    *,
    explicit: str | Path | None = None,
    fallback_roots: tuple[str | Path, ...] = (),
) -> str:
    """Compatibility wrapper for the canonical custom-node root resolver."""
    from .custom_node_root import resolve_custom_nodes_root_details

    return resolve_custom_nodes_root_details(
        anchor,
        explicit=explicit,
        fallback_roots=fallback_roots,
    ).root


def is_excluded_name(name: str) -> bool:
    """Return whether a bare file name is local, generated, or sensitive."""
    value = str(name)
    lowered = value.casefold()
    if lowered in {item.casefold() for item in EXCLUDED_FILENAMES}:
        return True
    if lowered.startswith(tuple(prefix.casefold() for prefix in EXCLUDED_PREFIXES)):
        return True
    if any(infix.casefold() in lowered for infix in EXCLUDED_INFIXES):
        return True
    if any(fnmatch.fnmatchcase(lowered, pattern.casefold()) for pattern in EXCLUDED_GLOBS):
        return True
    if lowered.endswith(".json") and lowered.startswith(
        tuple(prefix.casefold() for prefix in GENERATED_JSON_PREFIXES)
    ):
        return True
    if Path(value).suffix.casefold() in IMAGE_EXTENSIONS and (
        "screenshot" in lowered or "validation" in lowered
    ):
        return True
    return Path(value).suffix.casefold() in EXCLUDED_EXTENSIONS


def is_excluded_path(relative_path: str | os.PathLike[str]) -> bool:
    """Apply directory rules to parents and file rules to the final part."""
    parts = [part for part in str(relative_path).replace("\\", "/").split("/") if part]
    if not parts:
        return False
    if any(is_excluded_dir_name(part) for part in parts):
        return True
    return is_excluded_name(parts[-1])


def is_publishable_top_level_node(name: str, *, is_directory: bool, is_symlink: bool = False) -> bool:
    """Pure top-level node decision; callers provide filesystem facts."""
    return bool(
        is_directory
        and not is_symlink
        and not str(name).startswith(".")
        and not is_excluded_dir_name(name)
        and not is_local_clone_name(name)
    )


def iter_source_files(
    root: str | Path,
    *,
    extensions: frozenset[str] = IDENTITY_SOURCE_EXTENSIONS,
) -> Iterator[Path]:
    """Yield deterministic, regular source files without following symlinks."""
    root_path = Path(root).resolve()
    normalized_extensions = {ext.casefold() for ext in extensions}
    for dirpath_str, dirnames, filenames in os.walk(str(root_path), followlinks=False):
        dirpath = Path(dirpath_str)
        dirnames[:] = sorted(
            name for name in dirnames
            if not is_excluded_dir_name(name)
            and not (dirpath / name).is_symlink()
            and not (
                dirpath == root_path
                and custom_node_filter_reason(name, dirpath / name) is not None
            )
        )
        for filename in sorted(filenames):
            path = dirpath / filename
            if path.is_symlink() or Path(filename).suffix.casefold() not in normalized_extensions:
                continue
            if not is_excluded_name(filename):
                yield path


def iter_publication_files(root: str | Path) -> Iterator[Path]:
    """Yield the complete canonical custom-node publication set.

    Unlike ``iter_source_files`` this includes every non-excluded extension.
    Both the host publisher and the remote consumer use this set for the
    persisted publication generation.
    """
    raw_root = Path(root).expanduser()
    try:
        raw_root_stat = raw_root.lstat()
    except OSError as exc:
        raise OSError(f"custom-node source root is unreadable: {raw_root}") from exc
    if stat.S_ISLNK(raw_root_stat.st_mode):
        raise ValueError(f"symlink is not a publishable source root: {raw_root}")
    root_path = raw_root.resolve(strict=False)
    try:
        root_stat = root_path.lstat()
    except OSError as exc:
        raise OSError(f"custom-node source root is unreadable: {root_path}") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise ValueError(f"custom-node source root is not a directory: {root_path}")

    for entry in os.scandir(root_path):
        try:
            entry_stat = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise OSError(f"custom-node tree entry is unreadable: {entry.path}") from exc
        if stat.S_ISLNK(entry_stat.st_mode) or not (
            stat.S_ISDIR(entry_stat.st_mode) or stat.S_ISREG(entry_stat.st_mode)
        ):
            raise ValueError(f"special file is not publishable: {entry.path}")

    def raise_walk_error(error: OSError) -> None:
        raise error

    for node_name in iter_syncable_custom_node_dirs(root_path):
        node_path = root_path / node_name
        node_stat = node_path.lstat()
        if not stat.S_ISDIR(node_stat.st_mode) or stat.S_ISLNK(node_stat.st_mode):
            raise ValueError(f"syncable custom-node root is not a regular directory: {node_path}")
        included_count = 0
        for dirpath_str, dirnames, filenames in os.walk(
            str(node_path), followlinks=False, onerror=raise_walk_error
        ):
            dirpath = Path(dirpath_str)
            for name in (*dirnames, *filenames):
                path = dirpath / name
                try:
                    entry_stat = path.lstat()
                except OSError as exc:
                    raise OSError(f"custom-node tree entry is unreadable: {path}") from exc
                if stat.S_ISLNK(entry_stat.st_mode):
                    raise ValueError(f"symlink is not publishable: {path}")
                if name in dirnames and not stat.S_ISDIR(entry_stat.st_mode):
                    raise ValueError(f"non-directory traversal entry is not publishable: {path}")
                if name in filenames and not stat.S_ISREG(entry_stat.st_mode):
                    raise ValueError(f"special file is not publishable: {path}")
            dirnames[:] = sorted(
                name for name in dirnames
                if not is_excluded_path(
                    f"{node_name}/{(dirpath / name).relative_to(node_path).as_posix()}"
                )
            )
            for filename in sorted(filenames):
                path = dirpath / filename
                relative = path.relative_to(root_path).as_posix()
                if is_excluded_path(relative):
                    continue
                included_count += 1
                yield path
        if included_count == 0:
            _log.warning(
                "[v2.custom_node_publish] name=%s status=skipped reason=no_publishable_files",
                node_name,
            )
            continue


def canonical_publication_bytes(path: str | Path, data: bytes) -> bytes:
    """Return canonical bytes for one included publication file."""
    if Path(path).suffix.casefold() in CANONICAL_TEXT_EXTENSIONS:
        return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def publication_manifest_digest(
    entries: Iterator[dict[str, object]] | list[dict[str, object]],
) -> str:
    """Hash a canonical ``path``/``size``/``sha256`` publication manifest."""
    canonical_entries = [
        {
            "path": str(entry["path"]),
            "size": int(str(entry["size"])),
            "sha256": str(entry["sha256"]),
        }
        for entry in entries
    ]
    canonical_entries.sort(key=lambda entry: entry["path"])
    raw = json.dumps(
        canonical_entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compute_publication_generation(root: str | Path) -> str:
    """Return the full-content generation for the publication set."""
    entries: list[dict[str, object]] = []
    for path in iter_publication_files(root):
        data = canonical_publication_bytes(path, path.read_bytes())
        entries.append({
            "path": path.relative_to(Path(root).resolve()).as_posix(),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return publication_manifest_digest(entries) if entries else ""


def image_ignore_patterns(prefix: str = "") -> list[str]:
    """Return deterministic glob patterns suitable for ``add_local_dir``."""

    def case_insensitive_glob(value: str) -> str:
        """Encode both cases without expanding into an exponential list."""
        return "".join(
            f"[{character.lower()}{character.upper()}]"
            if character.isalpha()
            else character
            for character in value
        )

    def case_variants(value: str) -> tuple[str, ...]:
        variants = [""]
        for character in value:
            if character.isalpha():
                variants = [
                    f"{variant}{case}"
                    for variant in variants
                    for case in (character.lower(), character.upper())
                ]
            else:
                variants = [f"{variant}{character}" for variant in variants]
        return tuple(variants)

    patterns = [f"{prefix}{name}/" for name in sorted(EXCLUDED_DIR_NAMES)]
    patterns.extend(
        f"{prefix}{case_insensitive_glob(name)}/"
        for name in sorted(EXCLUDED_DIR_NAMES)
    )
    patterns.extend(f"{prefix}{name}" for name in sorted(EXCLUDED_FILENAMES))
    patterns.extend(f"{prefix}*{ext}" for ext in sorted(EXCLUDED_EXTENSIONS))
    patterns.extend(f"{prefix}{glob}" for glob in EXCLUDED_GLOBS)
    patterns.extend(f"{prefix}{prefix_name}*" for prefix_name in EXCLUDED_PREFIXES)
    patterns.extend(
        f"{prefix}{case_insensitive_glob(prefix_name)}*"
        for prefix_name in EXCLUDED_PREFIXES
    )
    patterns.extend(f"{prefix}*{infix}*" for infix in EXCLUDED_INFIXES)
    patterns.extend(
        f"{prefix}{json_prefix}*{extension}"
        for json_prefix in GENERATED_JSON_PREFIXES
        for extension in case_variants(".json")
    )
    patterns.extend(
        f"{prefix}*{kind}*{extension_variant}"
        for kind in ("screenshot", "validation")
        for extension in sorted(IMAGE_EXTENSIONS)
        for extension_variant in case_variants(extension)
    )
    # Modal's image matcher is case-sensitive, while ``is_excluded_name``
    # treats the Markdown extension case-insensitively.
    patterns.extend(f"{prefix}*.{extension}" for extension in ("mD", "Md", "MD"))
    return patterns


# Dependency context is deliberately narrower than source publication.  In
# particular, ordinary Python implementation files must not become inputs to a
# third-party dependency layer merely because they live beside requirements.
DEPENDENCY_FILENAMES: frozenset[str] = frozenset({
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "install.py",
})
DEPENDENCY_EXTENSIONS: frozenset[str] = frozenset({".txt", ".pip", ".in", ".cfg", ".toml"})


def normalize_dependency_text(value: str | bytes) -> str:
    """Normalize dependency declarations without including filesystem noise."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="strict")
    lines = [line.rstrip() for line in str(value).replace("\r\n", "\n").replace("\r", "\n").splitlines()]
    return "\n".join(lines) + ("\n" if lines else "")


def dependency_context_identity(context: dict[str, str] | None) -> str:
    """Return a stable digest for a normalized dependency-only file map."""
    payload = {
        str(path).replace("\\", "/"): str(digest)
        for path, digest in sorted((context or {}).items())
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
