"""v2ctl configuration resolution (Batch E32, Agent A).

Resolves the effective configuration for a deploy/run:

    built-in defaults → base(parent) profile → selected profile
    → explicit CLI options → --inherit → --set

Ambient shell environment NEVER merges (design §6); the only way host env
participates is an explicit ``--inherit NAME`` resolved against the caller's
``os.environ``.

Python 3.11 stdlib only.  The only subprocess allowed anywhere in v2ctl is
``git`` inside :func:`compute_git_state`.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Mapping

from .errors import FlagError
from .profiles import Profiles
from .registry import FlagRegistry

DEPLOY_RELEVANT_PATHS = (
    "comfymodal_runtime",
    "comfyapp.py",
    "tools/benchmark_v2_direct.py",
    "config/v2",
)

_EXPLICIT_SOURCES = ("cli", "inherit", "set")

# Dotted cli_options keys accepted by ConfigResolver.resolve.
_CLI_OPTION_KEYS = frozenset(
    {
        "owner",
        "target.app",
        "target.class",
        "target.method",
        "resources.gpu",
        "resources.cpu",
        "resources.memory_mb",
        "resources.min_containers",
        "resources.scaledown_window",
        "workload.fresh_required",
        "workload.conditioning_cache",
        "workload.expected_output_sha",
        "workload.run_count",
        "workload.gap_seconds",
        "workload.nonce",
    }
)

# Where the registry TOML lives relative to the repository root.
_REGISTRY_REL_PATH = Path("config") / "v2" / "flag_registry.toml"
_PROFILES_REL_PATH = Path("config") / "v2" / "profiles"


@dataclass
class Target:
    app: str
    class_name: str
    method: str


@dataclass
class Resources:
    gpu: str
    cpu: int
    memory_mb: int
    min_containers: int
    scaledown_window: int


@dataclass
class Workload:
    fresh_required: bool
    conditioning_cache: str
    expected_output_sha: str
    run_count: int
    gap_seconds: float
    nonce: str


@dataclass
class GitState:
    head: str
    branch: str
    dirty: bool
    dirty_hashes: dict[str, str] = field(default_factory=dict)  # relpath -> sha1


@dataclass
class ResolvedFlag:
    name: str
    value: str
    source: str  # "default" | "profile:<name>" | "cli" | "inherit" | "set"
    registered: bool
    consumed_at: str
    change_requires: str
    type: str
    description: str

    def is_deploy_required(self) -> bool:
        return self.change_requires in ("build", "deploy")

    def is_run_safe(self) -> bool:
        return self.change_requires in ("run", "none")


@dataclass
class ResolvedConfig:
    profile_name: str
    owner: str
    target: Target
    resources: Resources
    workload: Workload
    flags: list[ResolvedFlag]  # sorted by name; includes registered defaults
    unregistered: list[ResolvedFlag]  # explicit-but-unregistered, sorted
    runtime_override_policy: str
    git: GitState

    def flag(self, name: str) -> ResolvedFlag | None:
        """Return the effective flag (registered first, then unregistered)."""
        for flag in self.flags:
            if flag.name == name:
                return flag
        for flag in self.unregistered:
            if flag.name == name:
                return flag
        return None

    def to_dict(self) -> dict:
        """JSON-safe representation (values are all plain JSON types)."""
        return {
            "profile_name": self.profile_name,
            "owner": self.owner,
            "target": {
                "app": self.target.app,
                "class": self.target.class_name,
                "method": self.target.method,
            },
            "resources": {
                "gpu": self.resources.gpu,
                "cpu": self.resources.cpu,
                "memory_mb": self.resources.memory_mb,
                "min_containers": self.resources.min_containers,
                "scaledown_window": self.resources.scaledown_window,
            },
            "workload": {
                "fresh_required": self.workload.fresh_required,
                "conditioning_cache": self.workload.conditioning_cache,
                "expected_output_sha": self.workload.expected_output_sha,
                "run_count": self.workload.run_count,
                "gap_seconds": self.workload.gap_seconds,
                "nonce": self.workload.nonce,
            },
            "flags": [_flag_to_dict(f) for f in self.flags],
            "unregistered": [_flag_to_dict(f) for f in self.unregistered],
            "runtime_override_policy": self.runtime_override_policy,
            "git": {
                "head": self.git.head,
                "branch": self.git.branch,
                "dirty": self.git.dirty,
                "dirty_hashes": dict(sorted(self.git.dirty_hashes.items())),
            },
        }


def _flag_to_dict(flag: ResolvedFlag) -> dict:
    return {
        "name": flag.name,
        "value": flag.value,
        "source": flag.source,
        "registered": flag.registered,
        "consumed_at": flag.consumed_at,
        "change_requires": flag.change_requires,
        "type": flag.type,
        "description": flag.description,
    }


class ConfigResolver:
    """Resolves a full :class:`ResolvedConfig` for the control plane."""

    def __init__(self, repo_root: Path, profiles: Profiles, registry: FlagRegistry) -> None:
        self.repo_root = Path(repo_root)
        self.profiles = profiles
        self.registry = registry

    # -- resolution -------------------------------------------------------

    def resolve(
        self,
        *,
        profile_name: str = "production",
        cli_options: dict[str, str] | None = None,
        sets: list[tuple[str, str]] | None = None,
        inherits: list[str] | None = None,
        inherit_from: Mapping[str, str] | None = None,
    ) -> ResolvedConfig:
        """Resolve the effective configuration (precedence per design §6)."""
        self.registry.load()
        rp = self.profiles.resolve(profile_name)
        cli_options = dict(cli_options or {})

        _reject_unknown_cli_options(cli_options)
        target = self._resolve_target(rp.target, cli_options)
        resources = self._resolve_resources(rp.resources, cli_options)
        workload = self._resolve_workload(rp.workload, cli_options)
        owner = cli_options.get("owner", rp.owner or "")

        # Explicit flag channel: profile < --inherit < --set (last wins).
        explicit: dict[str, tuple[str, str]] = {}
        for name, value in rp.environment.items():
            FlagRegistry.validate_name(name)
            explicit[name] = (value, f"profile:{rp.name}")
        for name in inherits or []:
            if inherit_from is None or name not in inherit_from:
                raise FlagError(
                    f"--inherit {name!r}: variable not present in the provided environment"
                )
            FlagRegistry.validate_name(name)
            explicit[name] = (inherit_from[name], "inherit")
        for name, value in sets or []:
            FlagRegistry.validate_name(name)
            explicit[name] = (value, "set")

        # Resolve aliases to their canonical registered name; the dict order
        # above already encodes precedence (later sources overwrite).
        canonical_explicit: dict[str, tuple[str, str]] = {}
        for name, pair in explicit.items():
            flagdef = self.registry.get(name)
            key = flagdef.name if flagdef is not None else name
            canonical_explicit[key] = pair

        flags: list[ResolvedFlag] = []
        unregistered: list[ResolvedFlag] = []
        registered = {fd.name for fd in self.registry.all_flags()}

        for flagdef in self.registry.all_flags():
            name = flagdef.name
            if name in canonical_explicit:
                value, source = canonical_explicit[name]
                value = flagdef.validate_value(value)  # FlagError on failure
                flags.append(
                    ResolvedFlag(
                        name=name,
                        value=value,
                        source=source,
                        registered=True,
                        consumed_at=flagdef.consumed_at,
                        change_requires=flagdef.change_requires,
                        type=flagdef.type,
                        description=flagdef.description,
                    )
                )
            else:
                flags.append(
                    ResolvedFlag(
                        name=name,
                        value=flagdef.default,
                        source="default",
                        registered=True,
                        consumed_at=flagdef.consumed_at,
                        change_requires=flagdef.change_requires,
                        type=flagdef.type,
                        description=flagdef.description,
                    )
                )

        for name, (value, source) in canonical_explicit.items():
            if name not in registered:
                # Unknown is allowed; unknown is not trusted (design §7.3).
                unregistered.append(
                    ResolvedFlag(
                        name=name,
                        value=value,
                        source=source,
                        registered=False,
                        consumed_at="",
                        change_requires="unknown",
                        type="",
                        description="",
                    )
                )

        flags.sort(key=lambda f: f.name)
        unregistered.sort(key=lambda f: f.name)

        return ResolvedConfig(
            profile_name=rp.name,
            owner=owner,
            target=target,
            resources=resources,
            workload=workload,
            flags=flags,
            unregistered=unregistered,
            runtime_override_policy=str(rp.runtime_overrides.get("policy", "forbid")),
            git=compute_git_state(self.repo_root),
        )

    # -- structural resolution --------------------------------------------

    def _resolve_target(self, profile_target: dict, cli_options: dict) -> Target:
        return Target(
            app=str(cli_options.get("target.app", profile_target.get("app", ""))),
            class_name=str(
                cli_options.get("target.class", profile_target.get("class", ""))
            ),
            method=str(cli_options.get("target.method", profile_target.get("method", ""))),
        )

    def _resolve_resources(self, profile_resources: dict, cli_options: dict) -> Resources:
        return Resources(
            gpu=str(
                cli_options.get("resources.gpu", profile_resources.get("gpu", ""))
            ),
            cpu=_coerce_int(
                cli_options.get("resources.cpu", profile_resources.get("cpu", 0)),
                "resources.cpu",
            ),
            memory_mb=_coerce_int(
                cli_options.get(
                    "resources.memory_mb", profile_resources.get("memory_mb", 0)
                ),
                "resources.memory_mb",
            ),
            min_containers=_coerce_int(
                cli_options.get(
                    "resources.min_containers",
                    profile_resources.get("min_containers", 0),
                ),
                "resources.min_containers",
            ),
            scaledown_window=_coerce_int(
                cli_options.get(
                    "resources.scaledown_window",
                    profile_resources.get("scaledown_window", 0),
                ),
                "resources.scaledown_window",
            ),
        )

    def _resolve_workload(self, profile_workload: dict, cli_options: dict) -> Workload:
        return Workload(
            fresh_required=_coerce_bool(
                cli_options.get(
                    "workload.fresh_required",
                    profile_workload.get("fresh_required", True),
                ),
                "workload.fresh_required",
            ),
            conditioning_cache=str(
                cli_options.get(
                    "workload.conditioning_cache",
                    profile_workload.get("conditioning_cache", ""),
                )
            ),
            expected_output_sha=str(
                cli_options.get(
                    "workload.expected_output_sha",
                    profile_workload.get("expected_output_sha", ""),
                )
            ),
            run_count=_coerce_int(
                cli_options.get(
                    "workload.run_count", profile_workload.get("run_count", 1)
                ),
                "workload.run_count",
            ),
            gap_seconds=_coerce_float(
                cli_options.get(
                    "workload.gap_seconds", profile_workload.get("gap_seconds", 0.0)
                ),
                "workload.gap_seconds",
            ),
            nonce=str(cli_options.get("workload.nonce", "")),
        )

    # -- safety -----------------------------------------------------------

    def check_run_safety(self, config: ResolvedConfig, run_only: bool) -> None:
        """Refuse run-only execution when explicit flags require a deploy.

        ``run_only=True``: any flag explicitly overridden at run time
        (source cli/inherit/set) whose lifecycle is build/deploy — plus any
        explicitly-set unregistered flag — makes a run unsafe.  The deploy
        manifest diff itself lives in the CLI; this check is the
        self-contained guard over the resolved configuration.
        """
        if not run_only:
            return
        offenders: list[str] = []
        for flag in config.flags:
            if flag.source not in _EXPLICIT_SOURCES:
                continue
            if flag.change_requires in ("build", "deploy"):
                offenders.append(
                    f"{flag.name}={flag.value} "
                    f"(source={flag.source}, change_requires={flag.change_requires})"
                )
        for flag in config.unregistered:
            if flag.source in _EXPLICIT_SOURCES:
                offenders.append(
                    f"{flag.name}={flag.value} (unregistered, source={flag.source})"
                )
        if offenders:
            raise FlagError(
                "run-only configuration refuses changed deploy-required flags:\n  "
                + "\n  ".join(sorted(offenders))
            )

    # -- --set parsing ------------------------------------------------------

    @staticmethod
    def parse_set_spec(spec: str) -> tuple[str, str]:
        """Parse ``NAME=VALUE``.  Raises FlagError on bad syntax."""
        if not isinstance(spec, str) or "=" not in spec:
            raise FlagError(
                f"invalid --set spec {spec!r}: expected NAME=VALUE"
            )
        name, value = spec.split("=", 1)
        name = name.strip()
        if not name:
            raise FlagError(f"invalid --set spec {spec!r}: empty variable name")
        FlagRegistry.validate_name(name)
        return name, value


# -- git state ----------------------------------------------------------------


def compute_git_state(repo_root: Path) -> GitState:
    """Capture head/branch/dirty state plus sha1s of deploy-relevant changes.

    Tolerates git absence or a non-git directory: head/branch become
    ``"unknown"`` and dirty stays False.  Local git subprocess only.
    """
    repo_root = Path(repo_root)

    head = "unknown"
    branch = "unknown"
    dirty = False
    dirty_hashes: dict[str, str] = {}

    head_res = _git(repo_root, ["rev-parse", "HEAD"])
    if head_res is not None:
        value = head_res.stdout.strip()
        if value:
            head = value

    branch_res = _git(repo_root, ["branch", "--show-current"])
    if branch_res is not None:
        value = branch_res.stdout.strip()
        if value:
            branch = value

    status_res = _git(repo_root, ["status", "--porcelain"])
    if status_res is not None:
        lines = [line for line in status_res.stdout.splitlines() if line.strip()]
        dirty = bool(lines)
        for rel in _porcelain_paths(lines):
            rel_norm = rel.rstrip("/")
            if _is_deploy_relevant(rel_norm):
                _hash_path(repo_root, rel_norm, dirty_hashes)

    return GitState(
        head=head,
        branch=branch,
        dirty=dirty,
        dirty_hashes=dict(sorted(dirty_hashes.items())),
    )


def _git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _porcelain_paths(lines: list[str]) -> list[str]:
    """Extract changed paths from ``git status --porcelain`` lines."""
    paths: list[str] = []
    for line in lines:
        if len(line) < 4:
            continue
        if line.startswith("?? ") or line.startswith("!! "):
            paths.append(_unquote(line[3:].strip()))
            continue
        rest = line[3:].strip()
        # Renames/copies: "R  old -> new" — track the destination.
        if " -> " in rest:
            rest = rest.split(" -> ")[-1].strip()
        paths.append(_unquote(rest))
    return paths


def _unquote(path: str) -> str:
    # Best-effort: porcelain quotes C-escaped paths; plain names are unquoted.
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        inner = path[1:-1]
        return (
            inner.replace('\\\\', "\\")
            .replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\t", "\t")
        )
    return path


def _is_deploy_relevant(rel: str) -> bool:
    for entry in DEPLOY_RELEVANT_PATHS:
        if rel == entry or rel.startswith(entry + "/"):
            return True
    return False


def _hash_path(repo_root: Path, rel: str, out: dict[str, str]) -> None:
    """sha1 each file under ``rel`` (file or directory), keyed by relpath."""
    full = repo_root.joinpath(*PurePosixPath(rel).parts)
    if full.is_file():
        out[rel] = _sha1_hex(full)
        return
    if full.is_dir():
        for child in sorted(full.rglob("*")):
            if child.is_file():
                child_rel = child.relative_to(repo_root).as_posix()
                out[child_rel] = _sha1_hex(child)


def _sha1_hex(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -- coercion helpers ----------------------------------------------------------


def _reject_unknown_cli_options(cli_options: dict) -> None:
    for key in cli_options:
        if key not in _CLI_OPTION_KEYS:
            raise FlagError(f"unknown cli option {key!r}; expected one of: {', '.join(sorted(_CLI_OPTION_KEYS))}")


def _coerce_bool(value: object, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    raise FlagError(f"{key}: invalid boolean {value!r}")


def _coerce_int(value: object, key: str) -> int:
    if isinstance(value, bool):
        raise FlagError(f"{key}: invalid integer {value!r}")
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip(), 10)
    except ValueError as exc:
        raise FlagError(f"{key}: invalid integer {value!r}") from exc


def _coerce_float(value: object, key: str) -> float:
    if isinstance(value, bool):
        raise FlagError(f"{key}: invalid float {value!r}")
    if isinstance(value, float):
        return value
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise FlagError(f"{key}: invalid float {value!r}") from exc
