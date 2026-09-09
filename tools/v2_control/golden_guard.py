"""Small, local-only guardrails for Golden experiments.

This module is intentionally a policy helper rather than another control
plane.  It resolves the checkout, records a small git baseline, checks host
disk space, and delegates deployment/source probing to the supported v2ctl
commands.  It never edits a worktree, an external custom-node repository, or
the deploy lock on its own.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from comfymodal_runtime.custom_node_root import resolve_custom_nodes_root_details
from comfymodal_runtime.publication_policy import (
    custom_node_filter_reason,
    iter_publication_files,
    iter_syncable_custom_node_dirs,
)

from .locking import DeployLock


NOT_SENT = "NOT_SENT"
REMOTE_FAILED = "REMOTE_FAILED"
ARTIFACT_DNF = "ARTIFACT_DNF"
INVALID = "INVALID"
VALID = "VALID"

PROTECTED_APP = "stable-modal-comfy-v2-golden-p1"
DEFAULT_PROFILE = "golden_p1"
DEFAULT_DEPLOY_TIMEOUT = 1_800.0
DEFAULT_SOURCE_PROBE_TIMEOUT = 1_800.0
DEFAULT_DISK_FREE_GB = 10.0
MAX_RETRIES = 3
_APP_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

# These are the small, ignored inputs a fresh checkout may need.  Caches,
# artifacts, manifests, locks, and run history are deliberately not copied.
REQUIRED_LOCAL_PATHS = (
    "config/v2/modal_target.toml",
    ".modal_workspaces.json",
    ".runtime_state",
    ".v2ctl",
)
BOOTSTRAP_FILE_PATHS = (
    ".modal_workspaces.json",
    ".deployed_state.json",
    ".deploy_warmup_state.json",
    ".v2ctl",
    ".runtime_state",
    "credentials",
    ".cache",
    "artifacts",
)
SKIPPED_BOOTSTRAP_DIRS = frozenset(
    {".cache", ".v2ctl", ".runtime_state", "artifacts", ".experiments", "output"}
)

GOLDEN_REMINDERS = (
    "deep profiler off",
    "correctness smoke",
    "true-cold",
    "restore_count=1",
    "request_count=1",
    "exact SHA",
    "no fallback",
    "seriality",
    "valid slow runs",
)


@dataclass(frozen=True)
class GitSnapshot:
    branch: str
    head: str
    dirty_paths: tuple[str, ...]
    inspection_errors: tuple[str, ...] = ()

    @property
    def dirty(self) -> bool:
        return bool(self.dirty_paths)

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "head": self.head,
            "dirty": self.dirty,
            "dirty_paths": list(self.dirty_paths),
            "inspection_errors": list(self.inspection_errors),
        }


@dataclass(frozen=True)
class DiskCheck:
    path: str
    free_bytes: int
    required_bytes: int
    threshold_bytes: int

    @property
    def ok(self) -> bool:
        return self.free_bytes >= max(self.required_bytes, self.threshold_bytes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "free_bytes": self.free_bytes,
            "free_gb": round(self.free_bytes / (1024**3), 2),
            "required_bytes": self.required_bytes,
            "threshold_bytes": self.threshold_bytes,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class SafeOperationResult:
    operation: str
    command: tuple[str, ...]
    attempted: bool
    returncode: int | None
    timed_out: bool
    duration_seconds: float
    outcome: str
    timeout_classification: str = "none"
    stdout: str = ""
    stderr: str = ""
    inspections: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "command": list(self.command),
            "attempted": self.attempted,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "duration_seconds": round(self.duration_seconds, 3),
            "outcome": self.outcome,
            "timeout_classification": self.timeout_classification,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "inspections": list(self.inspections),
        }


def resolve_repo_root(start: Path | str | None = None) -> Path:
    """Find the checkout containing the canonical ``tools/v2ctl.py``."""
    candidate = Path(start or __file__).resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for path in (candidate, *candidate.parents):
        if (path / "tools" / "v2ctl.py").is_file() and (path / "tools" / "v2_control").is_dir():
            return path
    raise ValueError(f"cannot resolve comfyui-modal repository root from {start or __file__}")


def resolve_comfyui_root(repo_root: Path | str) -> Path:
    root = Path(repo_root).resolve()
    if root.parent.name == "custom_nodes":
        return root.parent.parent
    custom_nodes = root / "custom_nodes"
    if custom_nodes.is_dir():
        return root
    raise ValueError(f"cannot resolve ComfyUI root from {root}")


def resolve_custom_nodes_root(repo_root: Path | str) -> Path:
    root = Path(repo_root).resolve()
    return root.parent if root.parent.name == "custom_nodes" else root / "custom_nodes"


def canonical_paths(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    paths = {
        "repo_root": str(root),
        "comfyui_root": str(resolve_comfyui_root(root)),
        "custom_nodes_root": str(resolve_custom_nodes_root(root)),
        "v2ctl": str(root / "tools" / "v2ctl.py"),
        "config": str(root / "config" / "v2"),
        "modal_target": str(root / "config" / "v2" / "modal_target.toml"),
        "workspace_file": str(root / ".modal_workspaces.json"),
        "runtime_state": str(root / ".runtime_state"),
        "control_state": str(root / ".v2ctl"),
    }
    return {
        "paths": paths,
        "worktree": worktree_occupancy(root),
        "required_local_paths": [str(root / p) for p in REQUIRED_LOCAL_PATHS],
        "bootstrap_files": list(BOOTSTRAP_FILE_PATHS),
        "skipped_large_or_runtime_dirs": sorted(SKIPPED_BOOTSTRAP_DIRS),
    }


def _git_checked(repo_root: Path, *args: str, timeout: float = 15.0) -> tuple[str, str | None]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(repo_root), capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return "", f"git {' '.join(args)}: {type(exc).__name__}: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "nonzero exit").strip()
        return "", f"git {' '.join(args)}: exit {result.returncode}: {detail[:500]}"
    return result.stdout, None


def _git(repo_root: Path, *args: str, timeout: float = 15.0) -> str:
    """Compatibility wrapper for read-only callers which only need stdout."""
    return _git_checked(repo_root, *args, timeout=timeout)[0]


def capture_git_snapshot(repo_root: Path | str) -> GitSnapshot:
    root = Path(repo_root).resolve()
    branch_raw, branch_error = _git_checked(root, "branch", "--show-current")
    head_raw, head_error = _git_checked(root, "rev-parse", "HEAD")
    raw, status_error = _git_checked(root, "status", "--porcelain=v1", "--untracked-files=all")
    errors = tuple(error for error in (branch_error, head_error, status_error) if error)
    paths: list[str] = []
    for line in raw.splitlines():
        if len(line) >= 4:
            value = line[3:].strip()
            if " -> " in value:
                value = value.rsplit(" -> ", 1)[-1].strip()
            paths.append(value.strip('"'))
    return GitSnapshot(
        branch_raw.strip() or "unknown",
        head_raw.strip() or "unknown",
        tuple(sorted(set(paths))),
        errors,
    )


def save_git_snapshot(path: Path | str, snapshot: GitSnapshot) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def load_git_snapshot(path: Path | str) -> GitSnapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return GitSnapshot(
        str(data.get("branch", "unknown")), str(data.get("head", "unknown")),
        tuple(sorted(str(item) for item in data.get("dirty_paths", ()) or ())),
    )


def dirty_diff(baseline: GitSnapshot, current: GitSnapshot) -> dict[str, Any]:
    before, now = set(baseline.dirty_paths), set(current.dirty_paths)
    return {
        "pre_existing_dirty": sorted(before),
        "experiment_owned_dirty": sorted(now - before),
        "cleaned_since_baseline": sorted(before - now),
        "current_dirty": sorted(now),
    }


def _compact_paths(paths: Iterable[str], limit: int = 100) -> dict[str, Any]:
    values = sorted(set(paths))
    return {
        "paths": values[:limit],
        "count": len(values),
        "truncated": len(values) > limit,
    }


def disk_check(path: Path | str, *, min_free_gb: float = DEFAULT_DISK_FREE_GB,
               required_bytes: int = 0,
               usage_fn: Callable[[str], Any] = shutil.disk_usage) -> DiskCheck:
    if isinstance(min_free_gb, bool) or not math.isfinite(float(min_free_gb)) or float(min_free_gb) < 0:
        raise ValueError("min_free_gb must be finite and non-negative")
    if int(required_bytes) < 0:
        raise ValueError("required_bytes must be non-negative")
    target = Path(path).resolve()
    free = int(usage_fn(str(target)).free)
    return DiskCheck(str(target), free, int(required_bytes), int(min_free_gb * 1024**3))


def process_alive(pid: object) -> bool:
    try:
        value = int(str(pid))
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {value}"], capture_output=True,
                text=True, timeout=10, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return True  # inability to prove death is occupied
        return result.returncode == 0 and "No tasks" not in f"{result.stdout}\n{result.stderr}"
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def worktree_occupancy(repo_root: Path | str, *, active_marker: Path | str | None = None,
                       conflicting_pids: Iterable[object] = ()) -> dict[str, Any]:
    """Dirty files do not occupy a worktree; only an active marker/live PID does."""
    root = Path(repo_root).resolve()
    marker = Path(active_marker) if active_marker else root / ".v2ctl" / "active.json"
    marker_data: Mapping[str, Any] = {}
    if marker.is_file():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                marker_data = value
        except (OSError, ValueError):
            marker_data = {"marker_unreadable": True}
    # Presence is the explicit marker.  A caller may disarm it with
    # ``{"active": false}``; an unreadable marker remains occupied.
    marker_active = marker.is_file() and marker_data.get("active", True) is not False
    pids = [int(str(pid)) for pid in conflicting_pids if str(pid).lstrip("-").isdigit()]
    live_pids = [pid for pid in pids if process_alive(pid)]
    return {
        "occupied": marker_active or bool(live_pids),
        "active_marker": str(marker),
        "active_marker_present": marker.is_file(),
        "active_marker_active": marker_active,
        "conflicting_pids": pids,
        "live_conflicting_pids": live_pids,
        "dirty_is_occupancy": False,
    }


def classify_lock(lock: DeployLock) -> dict[str, Any]:
    status = lock.status()
    if status is None:
        lock_path = getattr(lock, "_lock_path", None)
        try:
            present = bool(lock_path and os.path.lexists(os.fspath(lock_path)))
        except OSError:
            present = True
        if present:
            return {
                "present": True,
                "ambiguous": True,
                "corrupt_or_unreadable": True,
                "stale": False,
                "live_owner": False,
            }
        return {"present": False, "ambiguous": False, "stale": False, "live_owner": False}
    stale = lock.is_stale(status)
    return {
        "present": True,
        "ambiguous": False,
        "corrupt_or_unreadable": False,
        "stale": stale,
        "live_owner": not stale,
        "owner": status.get("owner"),
        "pid": status.get("pid"),
        "host": status.get("host"),
        "target": status.get("target"),
        "profile": status.get("profile"),
    }


def classify_outcome(*, attempted: bool, returncode: int | None = None,
                     timed_out: bool = False, artifact_found: bool = False,
                     valid: bool = False, error_kind: str = "") -> str:
    if not attempted:
        return NOT_SENT
    if timed_out or (returncode is not None and returncode != 0):
        return REMOTE_FAILED
    if not artifact_found:
        return ARTIFACT_DNF
    return VALID if valid else INVALID


def _validate_app(app: str) -> str:
    value = str(app or "").strip().lower()
    if value == PROTECTED_APP or not _APP_RE.fullmatch(value):
        raise ValueError(f"invalid or production-protected Golden app: {app!r}")
    return value


def supported_command(repo_root: Path | str, operation: str, app: str) -> tuple[str, ...]:
    root = Path(repo_root).resolve()
    script = root / "tools" / "v2ctl.py"
    app = _validate_app(app)
    if operation == "deploy":
        return (sys.executable, str(script), "golden", "deploy", "--app", app)
    if operation in {"source-probe", "source_probe"}:
        return (sys.executable, str(script), "--profile", DEFAULT_PROFILE, "--app", app, "source-probe")
    raise ValueError(f"unsupported guarded operation: {operation}")


def _inspect_supported_state(repo_root: Path, app: str) -> dict[str, Any]:
    """Use only public local inspection commands before a retry."""
    commands = (
        ("lock status", sys.executable, str(repo_root / "tools" / "v2ctl.py"), "lock", "status"),
        ("golden status", sys.executable, str(repo_root / "tools" / "v2ctl.py"), "golden", "status", "--app", app),
        ("doctor", sys.executable, str(repo_root / "tools" / "v2ctl.py"), "doctor", "--profile", DEFAULT_PROFILE, "--app", app),
    )
    result: dict[str, Any] = {}
    for name, *command in commands:
        try:
            completed = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, timeout=30, check=False)
            result[name] = {"returncode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-2000:]}
        except (OSError, subprocess.TimeoutExpired) as exc:
            result[name] = {"error": type(exc).__name__}
    lock = classify_lock(DeployLock(repo_root / ".v2ctl" / "deploy.lock"))
    result["lock"] = lock
    return result


def _timeout_retry_is_proven_safe(state: Mapping[str, Any]) -> bool:
    """Require an explicit supported-state proof before retrying a timeout."""
    lock = state.get("lock", {})
    return bool(
        state.get("retry_safe") is True
        and state.get("remote_completion") in {"not_started", "failed"}
        and isinstance(lock, Mapping)
        and not lock.get("present")
    )


def _inspection_text(state: Mapping[str, Any]) -> str:
    try:
        return json.dumps(state, sort_keys=True, default=str)[:4000]
    except (TypeError, ValueError):
        return repr(state)[:4000]


def _inspect_timeout_state(repo_root: Path, app: str) -> dict[str, Any]:
    try:
        state = _inspect_supported_state(repo_root, app)
        return state if isinstance(state, dict) else {"inspection_error": "unsupported inspection result"}
    except Exception as exc:  # inspection failure is itself ambiguous evidence
        return {"inspection_error": f"{type(exc).__name__}: {exc}", "ambiguous": True}


def run_safe_operation(repo_root: Path | str, operation: str, app: str, *,
                       timeout: float | None = None, retries: int = 0,
                       run_fn: Callable[..., Any] = subprocess.run) -> SafeOperationResult:
    """Run exactly one supported command, with bounded optional retries."""
    root = Path(repo_root).resolve()
    command = supported_command(root, operation, app)
    timeout = float(timeout if timeout is not None else (DEFAULT_DEPLOY_TIMEOUT if operation == "deploy" else DEFAULT_SOURCE_PROBE_TIMEOUT))
    if not math.isfinite(timeout) or timeout <= 0 or retries < 0 or retries > MAX_RETRIES:
        raise ValueError(f"timeout must be finite and positive; retries must be between 0 and {MAX_RETRIES}")
    inspections: list[dict[str, Any]] = []
    started = time.monotonic()
    for attempt in range(retries + 1):
        if attempt:
            state = _inspect_timeout_state(root, _validate_app(app))
            inspections.append({"attempt": attempt, "state": state})
            lock_state = state.get("lock", {})
            if isinstance(lock_state, Mapping) and lock_state.get("present") and not lock_state.get("stale"):
                return SafeOperationResult(operation, command, False, None, False, time.monotonic() - started, NOT_SENT, inspections=tuple(inspections))
        try:
            completed = run_fn(command, cwd=str(root), capture_output=True, text=True, timeout=timeout, check=False)
            code = int(str(getattr(completed, "returncode", 1)))
            stdout = str(getattr(completed, "stdout", "") or "")
            stderr = str(getattr(completed, "stderr", "") or "")
            if code == 0:
                outcome = VALID
                return SafeOperationResult(operation, command, True, code, False, time.monotonic() - started, outcome, stdout=stdout, stderr=stderr, inspections=tuple(inspections))
            if attempt < retries:
                continue
            return SafeOperationResult(operation, command, True, code, False, time.monotonic() - started, REMOTE_FAILED, stdout=stdout, stderr=stderr, inspections=tuple(inspections))
        except subprocess.TimeoutExpired as exc:
            # A subprocess timeout does not prove that a remote deployment did
            # not finish.  Inspect supported local state before making either
            # decision; absent an explicit proof, fail closed and never retry.
            state = _inspect_supported_state(root, _validate_app(app))
            inspections.append({"attempt": attempt, "after_timeout": True, "state": state})
            if attempt < retries and _timeout_retry_is_proven_safe(state):
                continue
            classification = (
                "operation_timeout_state_ambiguous"
                if not _timeout_retry_is_proven_safe(state)
                else "operation_timeout_no_retry"
            )
            evidence = _inspection_text(state)
            return SafeOperationResult(
                operation, command, True, None, True, time.monotonic() - started,
                REMOTE_FAILED, timeout_classification=classification,
                stdout=str(exc.stdout or ""),
                stderr=(str(exc.stderr or "") + "\nstate_inspection=" + evidence)[-8000:],
                inspections=tuple(inspections),
            )
        except OSError as exc:
            return SafeOperationResult(operation, command, False, None, False, time.monotonic() - started, NOT_SENT, stderr=f"{type(exc).__name__}: {exc}", inspections=tuple(inspections))
    raise AssertionError("bounded operation loop did not return")


def external_repo_changes(repo_root: Path | str) -> list[dict[str, Any]]:
    """Inspect top-level external nodes without writing to them."""
    root = Path(repo_root).resolve()
    custom_root = resolve_custom_nodes_root(root)
    changed: list[dict[str, Any]] = []
    if not custom_root.is_dir():
        return changed
    for node in sorted(custom_root.iterdir()):
        if not node.is_dir() or node.resolve() == root or not (node / ".git").exists():
            continue
        raw = _git(node, "status", "--porcelain=v1", "--untracked-files=all")
        paths = [line[3:].strip() for line in raw.splitlines() if len(line) >= 4]
        if paths:
            changed.append({"path": str(node.resolve()), "changed_paths": paths})
    return changed


def _first_value(data: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = data
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                value = None
                break
            value = value[key]
        if value is not None:
            return value
    return None


def _status_match(value: Any, accepted: set[str]) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in accepted


def _manifest_target(data: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _first_value(
        data,
        ("target",),
        ("deploy_inputs", "target"),
        ("deployment_identity",),
    )
    return value if isinstance(value, Mapping) else {}


def _effective_manifest_flags(data: Mapping[str, Any]) -> dict[str, str]:
    candidates = (
        _first_value(data, ("effective_environment",)),
        _first_value(data, ("effective_config", "deploy_flags")),
        _first_value(data, ("effective_config", "flags")),
        _first_value(data, ("effective_config", "effective_environment")),
        _first_value(data, ("deploy_inputs", "deploy_flags")),
        _first_value(data, ("deploy_inputs", "effective_flags")),
        _first_value(data, ("flags",)),
    )
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return {str(key): str(value) for key, value in candidate.items()}
    return {}


def _parse_expected_flags(values: Iterable[str] | Mapping[str, Any]) -> tuple[dict[str, str], list[str]]:
    if isinstance(values, Mapping):
        return {str(key): str(value) for key, value in values.items()}, []
    expected: dict[str, str] = {}
    errors: list[str] = []
    for raw in values or ():
        text = str(raw)
        if "=" not in text or not text.split("=", 1)[0].strip():
            errors.append(f"invalid expected flag {text!r}; use NAME=VALUE")
            continue
        name, value = text.split("=", 1)
        expected[name.strip()] = value
    return expected, errors


def _telemetry_families(path: Path) -> tuple[set[str], str | None]:
    if not path.exists():
        return set(), "telemetry path does not exist"
    files = [path] if path.is_file() else sorted(path.rglob("*.json*")) if path.is_dir() else []
    if not files:
        return set(), "telemetry path is not a readable file or JSON directory"
    families: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).casefold() in {"family", "event_family", "eventfamily"}:
                    if isinstance(item, str):
                        families.add(item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    try:
        for file in files:
            text = file.read_text(encoding="utf-8")
            try:
                visit(json.loads(text))
            except json.JSONDecodeError:
                for line in text.splitlines():
                    if line.strip():
                        visit(json.loads(line))
    except (OSError, UnicodeError, ValueError) as exc:
        return families, f"telemetry could not be read: {type(exc).__name__}: {exc}"
    return families, None


def _custom_nodes_report(nodes_root: Path) -> dict[str, Any]:
    # iter_publication_files performs the canonical strict malformed/symlink
    # checks.  The top-level grouping below is only for an auditable report.
    published = list(iter_publication_files(nodes_root))
    counts: dict[str, int] = {}
    for path in published:
        relative = path.relative_to(nodes_root).parts
        if relative:
            counts[relative[0]] = counts.get(relative[0], 0) + 1
    included = set(iter_syncable_custom_node_dirs(nodes_root))
    skipped: list[dict[str, str]] = []
    for entry in sorted(nodes_root.iterdir(), key=lambda value: value.name.casefold()):
        reason = custom_node_filter_reason(entry.name, entry)
        if reason is not None:
            skipped.append({"name": entry.name, "reason": reason})
        elif entry.name not in counts:
            included.discard(entry.name)
            skipped.append({"name": entry.name, "reason": "no_publishable_files"})
    return {"included": sorted(included), "skipped": skipped, "publication_file_count": len(published)}


def preflight(repo_root: Path | str, *, profile: str = DEFAULT_PROFILE, app: str = "",
              baseline_file: Path | str | None = None, min_free_gb: float = DEFAULT_DISK_FREE_GB,
              telemetry_path: Path | str | None = None, require_evidence: bool = False,
              expected_flags: Iterable[str] | Mapping[str, Any] = (),
              required_events: Iterable[str] = (), require_operation: bool = False) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    current = capture_git_snapshot(root)
    resolution_errors = list(current.inspection_errors)
    try:
        baseline = load_git_snapshot(baseline_file) if baseline_file and Path(baseline_file).is_file() else current
    except (OSError, ValueError, TypeError) as exc:
        baseline = current
        resolution_errors.append(f"baseline could not be read: {type(exc).__name__}: {exc}")
    disk = disk_check(root, min_free_gb=min_free_gb)
    lock = classify_lock(DeployLock(root / ".v2ctl" / "deploy.lock"))
    try:
        nodes_resolution = resolve_custom_nodes_root_details(root)
        nodes_root = Path(nodes_resolution.root)
        custom_nodes = _custom_nodes_report(nodes_root)
    except (OSError, RuntimeError, ValueError) as exc:
        nodes_root = Path(resolve_custom_nodes_root(root))
        nodes_resolution = None
        custom_nodes = {"included": [], "skipped": []}
        resolution_errors.append(f"custom-nodes resolution failed: {type(exc).__name__}: {exc}")
    deployment: dict[str, Any] = {"manifest": None, "source_probe": None, "flag_effective": {}}
    identity_error = ""
    if app:
        try:
            app = _validate_app(app)
        except ValueError as exc:
            identity_error = str(exc)
    if profile and not str(profile).startswith("golden_p1"):
        identity_error = identity_error or f"Golden guard requires a golden_p1 profile, got {profile!r}"
    if profile and not identity_error:
        try:
            from . import config as config_mod
            from . import fingerprints as fingerprints_mod
            from . import profiles as profiles_mod
            from . import registry as registry_mod
            registry = registry_mod.FlagRegistry(root / "config" / "v2" / "flag_registry.toml")
            config = config_mod.ConfigResolver(root, profiles_mod.Profiles(root / "config" / "v2" / "profiles"), registry).resolve(
                profile_name=profile, cli_options={"target.app": _validate_app(app)} if app else {}
            )
            deployment["flag_effective"] = {flag.name: str(flag.value) for flag in (*config.flags, *config.unregistered)}
            deployment["deploy_fingerprint"] = fingerprints_mod.FingerprintEngine(config).deploy_fingerprint()
            target_config = {
                "app": str(config.target.app),
                "class": str(config.target.class_name),
                "method": str(config.target.method),
                "profile": str(config.profile_name),
            }
            deployment["target_identity"] = target_config
            manifests = sorted((root / ".v2ctl" / "deployments").glob("deploy_*.json"), reverse=True)
            for path in manifests:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    resolution_errors.append(f"manifest {path} could not be read: {type(exc).__name__}: {exc}")
                    continue
                if not isinstance(data, dict):
                    continue
                target = _manifest_target(data)
                manifest_profile = _first_value(data, ("profile",), ("deploy_inputs", "profile"), ("artifacts", "profile"), ("deployment_identity", "profile"))
                manifest_app = target.get("app") or target.get("app_name")
                if manifest_profile == profile and (not app or manifest_app == app):
                    source_status = _first_value(data, ("source_identity_status",), ("source_identity", "status"), ("source_identity", "verdict"), ("source_identity",))
                    health_status = _first_value(data, ("runtime_health_status",), ("runtime_health", "status"), ("runtime_health",), ("health", "status"), ("health",))
                    if isinstance(source_status, Mapping):
                        source_status = source_status.get("status", source_status.get("verdict"))
                    if isinstance(health_status, Mapping):
                        health_status = health_status.get("status", health_status.get("verdict"))
                    deployment["manifest"] = {
                        "path": str(path),
                        "deploy_fingerprint": _first_value(data, ("deploy_fingerprint",), ("deploy_inputs", "deploy_fingerprint"), ("deployment_identity", "deploy_fingerprint")),
                        "profile": manifest_profile,
                        "target": dict(target),
                        "source_identity_status": "MATCH" if _status_match(source_status, {"match", "verified", "ok", "healthy"}) else str(source_status or "MISSING"),
                        "runtime_health_status": "READY" if _status_match(health_status, {"ready", "healthy", "ok"}) else str(health_status or "MISSING"),
                        "effective_flags": _effective_manifest_flags(data),
                    }
                    break
            manifest_fp = (deployment["manifest"] or {}).get("deploy_fingerprint")
            if manifest_fp:
                probes = sorted((root / ".v2ctl" / "source-probes").glob("*.json"), reverse=True)
                for path in probes:
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    if isinstance(data, dict) and _first_value(data, ("deploy_fingerprint",), ("classification", "deploy_fingerprint")) == manifest_fp:
                        classification = data.get("classification", {})
                        verdict = _first_value(data, ("verdict",), ("classification", "verdict"), ("source_identity_status",))
                        deployment["source_probe"] = {"path": str(path), "deploy_fingerprint": manifest_fp, "verdict": verdict, "status": "MATCH" if _status_match(verdict, {"match", "verified", "ok"}) else "FAIL"}
                        break
        except Exception as exc:  # report, do not hide dirty state
            deployment["resolution_error"] = f"{type(exc).__name__}: {exc}"
            resolution_errors.append(deployment["resolution_error"])
    expected, expected_errors = _parse_expected_flags(expected_flags)
    resolution_errors.extend(expected_errors)
    required = [str(value) for value in required_events]
    if telemetry_path or required:
        path = Path(telemetry_path).resolve() if telemetry_path else root / "__missing_telemetry__"
        families, telemetry_error = _telemetry_families(path)
        family_keys = {family.casefold() for family in families}
        deployment["telemetry"] = {"path": str(path), "present": telemetry_error is None, "families": sorted(families), "required_events": {family: family.casefold() in family_keys for family in required}}
        if telemetry_error and required:
            resolution_errors.append(telemetry_error)
    persisted = (deployment.get("manifest") or {}).get("effective_flags", {})
    deployment["expected_flags"] = {name: {"expected": value, "actual": persisted.get(name), "match": persisted.get(name) == value} for name, value in expected.items()}
    diff = dirty_diff(baseline, current)
    compact_diff: dict[str, Any] = {}
    for name, values in diff.items():
        compact = _compact_paths(values)
        compact_diff[name] = compact["paths"]
        compact_diff[f"{name}_count"] = compact["count"]
        compact_diff[f"{name}_truncated"] = compact["truncated"]
    compact_git = current.as_dict()
    compact_paths = _compact_paths(current.dirty_paths)
    compact_git["dirty_paths"] = compact_paths["paths"]
    compact_git["dirty_paths_count"] = compact_paths["count"]
    compact_git["dirty_paths_truncated"] = compact_paths["truncated"]
    compact_git["diff"] = compact_diff
    external_changes = external_repo_changes(root)
    for change in external_changes:
        change["changed_paths"] = _compact_paths(change.get("changed_paths", ()), limit=40)
    report = {
        "profile": profile,
        "app": str(app or "").strip().lower(),
        "git": compact_git,
        "disk": disk.as_dict(),
        "occupancy": worktree_occupancy(root),
        "resolution_errors": resolution_errors,
        "custom_nodes_resolution": nodes_resolution.as_dict() if nodes_resolution else None,
        "canonical_custom_nodes_root": str(nodes_root),
        "custom_nodes": custom_nodes,
        "external_repo_protection": {"mode": "read-only", "changed": external_changes},
        "lock": lock,
        "deployment_checks": deployment,
        "reminders": list(GOLDEN_REMINDERS),
    }
    if identity_error:
        report["deployment_checks"]["identity_error"] = identity_error
    telemetry = deployment.get("telemetry", {})
    telemetry_ok = not telemetry_path or bool(telemetry.get("present"))
    source_probe = deployment.get("source_probe") or {}
    manifest = deployment.get("manifest") or {}
    target = manifest.get("target", {})
    target_ok = bool(
        manifest.get("profile") == profile
        and target.get("app", target.get("app_name")) == app
        and target.get("class", target.get("class_name")) == deployment.get("target_identity", {}).get("class")
        and target.get("method") == deployment.get("target_identity", {}).get("method")
    )
    fingerprint_ok = manifest.get("deploy_fingerprint") == deployment.get("deploy_fingerprint") and bool(manifest.get("deploy_fingerprint"))
    expected_ok = all(item["match"] for item in deployment["expected_flags"].values())
    events_ok = all((telemetry.get("required_events", {}).get(family) is True) for family in required)
    evidence_ok = bool(
        manifest and fingerprint_ok and target_ok
        and manifest.get("source_identity_status") == "MATCH"
        and manifest.get("runtime_health_status") in {"READY", "HEALTHY"}
        and source_probe.get("status") == "MATCH"
        and source_probe.get("deploy_fingerprint") == manifest.get("deploy_fingerprint")
        and telemetry_ok and expected_ok and events_ok
    )
    report["deployment_checks"]["evidence_ok"] = evidence_ok
    report["ok"] = bool(
        disk.ok and not identity_error and not resolution_errors
        and (not (require_evidence or expected or required) or (evidence_ok and not report["occupancy"]["occupied"]))
        and (not require_operation or not report["occupancy"]["occupied"])
    )
    return report


def bootstrap_worktree(repo_root: Path | str, destination: Path | str) -> dict[str, Any]:
    """Create a detached worktree without copying secrets or runtime state."""
    root = Path(repo_root).resolve()
    target = Path(destination).resolve()
    if target.exists():
        raise ValueError(f"bootstrap destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "worktree", "add", "--detach", str(target), "HEAD"], cwd=str(root), check=True, capture_output=True, text=True, timeout=60)
    copied: list[str] = []
    skipped: list[dict[str, str]] = []
    for relative in BOOTSTRAP_FILE_PATHS:
        source = root / relative
        if source.exists() or os.path.lexists(source):
            skipped.append({"path": relative, "reason": "secret_or_runtime_state_not_copied"})
        else:
            skipped.append({"path": relative, "reason": "missing_required_ignored_file"})
    ignored_missing = [
        relative for relative in REQUIRED_LOCAL_PATHS
        if relative != "config/v2/modal_target.toml" and not (root / relative).exists()
    ]
    return {
        "worktree": str(target),
        "copied": copied,
        "skipped": skipped,
        "required_ignored_files_missing": ignored_missing,
        "large_caches_copied": False,
    }
