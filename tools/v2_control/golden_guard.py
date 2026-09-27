"""Local-only guardrails for the supported Golden control commands."""
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
from comfymodal_runtime.publication_policy import custom_node_filter_reason, iter_publication_files, iter_syncable_custom_node_dirs
from .locking import DeployLock

NOT_SENT, REMOTE_FAILED, ARTIFACT_DNF, INVALID, VALID = "NOT_SENT", "REMOTE_FAILED", "ARTIFACT_DNF", "INVALID", "VALID"
PROTECTED_APP = "stable-modal-comfy-v2-golden-p1"
DEFAULT_PROFILE = "golden_p1"
DEFAULT_TIMEOUT = DEFAULT_DEPLOY_TIMEOUT = DEFAULT_SOURCE_PROBE_TIMEOUT = 1_800.0
DEFAULT_DISK_FREE_GB, MAX_RETRIES = 10.0, 3
_APP_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
REQUIRED_LOCAL_PATHS = ("config/v2/modal_target.toml", ".modal_workspaces.json", ".runtime_state", ".v2ctl")
BOOTSTRAP_FILE_PATHS = (".modal_workspaces.json", ".deployed_state.json", ".deploy_warmup_state.json", ".v2ctl", ".runtime_state", "credentials", ".cache", "artifacts")
SKIPPED_BOOTSTRAP_DIRS = frozenset({".cache", ".v2ctl", ".runtime_state", "artifacts", ".experiments", "output"})
GOLDEN_REMINDERS = ("deep profiler off", "correctness smoke", "true-cold", "restore_count=1", "request_count=1", "exact SHA", "no fallback", "seriality", "valid slow runs")


@dataclass(frozen=True)
class GitSnapshot:
    branch: str
    head: str
    dirty_paths: tuple[str, ...]
    inspection_errors: tuple[str, ...] = ()

    @property
    def dirty(self) -> bool: return bool(self.dirty_paths)
    def as_dict(self) -> dict[str, Any]:
        return {"branch": self.branch, "head": self.head, "dirty": self.dirty, "dirty_paths": list(self.dirty_paths), "inspection_errors": list(self.inspection_errors)}


@dataclass(frozen=True)
class DiskCheck:
    path: str
    free_bytes: int
    required_bytes: int
    threshold_bytes: int

    @property
    def ok(self) -> bool: return self.free_bytes >= max(self.required_bytes, self.threshold_bytes)
    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "free_bytes": self.free_bytes, "free_gb": round(self.free_bytes / (1024 ** 3), 2), "required_bytes": self.required_bytes, "threshold_bytes": self.threshold_bytes, "ok": self.ok}


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
        return {"operation": self.operation, "command": list(self.command), "attempted": self.attempted, "returncode": self.returncode, "timed_out": self.timed_out, "duration_seconds": round(self.duration_seconds, 3), "outcome": self.outcome, "timeout_classification": self.timeout_classification, "stdout": self.stdout, "stderr": self.stderr, "inspections": list(self.inspections)}


def resolve_repo_root(start: Path | str | None = None) -> Path:
    candidate = Path(start or __file__).resolve()
    candidate = candidate.parent if candidate.is_file() else candidate
    for path in (candidate, *candidate.parents):
        if (path / "tools/v2ctl.py").is_file() and (path / "tools/v2_control").is_dir(): return path
    raise ValueError(f"cannot resolve comfyui-modal repository root from {start or __file__}")


def resolve_comfyui_root(repo_root: Path | str) -> Path:
    root = Path(repo_root).resolve()
    if root.parent.name == "custom_nodes": return root.parent.parent
    if (root / "custom_nodes").is_dir(): return root
    raise ValueError(f"cannot resolve ComfyUI root from {root}")


def resolve_custom_nodes_root(repo_root: Path | str) -> Path:
    root = Path(repo_root).resolve()
    return root.parent if root.parent.name == "custom_nodes" else root / "custom_nodes"


def canonical_paths(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    paths = {
        "repo_root": str(root), "comfyui_root": str(resolve_comfyui_root(root)), "custom_nodes_root": str(resolve_custom_nodes_root(root)),
        "config": str(root / "config/v2"), "modal_target": str(root / "config/v2/modal_target.toml"), "workspace_file": str(root / ".modal_workspaces.json"),
        "runtime_state": str(root / ".runtime_state"), "control_state": str(root / ".v2ctl"), "artifact_root": str(root / "artifacts"), "artifacts": str(root / "artifacts"), "v2ctl": str(root / "tools/v2ctl.py"),
    }
    return {"paths": paths, "worktree": worktree_occupancy(root), "required_local_paths": [str(root / p) for p in REQUIRED_LOCAL_PATHS], "bootstrap_files": list(BOOTSTRAP_FILE_PATHS), "skipped_large_or_runtime_dirs": sorted(SKIPPED_BOOTSTRAP_DIRS)}


def _git(root: Path, *args: str, timeout: float = 15.0) -> tuple[str, str | None]:
    try:
        result = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=timeout, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return "", f"git {' '.join(args)}: {type(exc).__name__}: {exc}"
    if result.returncode:
        detail = (result.stderr or result.stdout or "nonzero exit").strip()
        return "", f"git {' '.join(args)}: exit {result.returncode}: {detail[:500]}"
    return result.stdout, None


def capture_git_snapshot(repo_root: Path | str) -> GitSnapshot:
    root = Path(repo_root).resolve()
    branch, e1 = _git(root, "branch", "--show-current")
    head, e2 = _git(root, "rev-parse", "HEAD")
    status, e3 = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    paths = [line[3:].strip().rsplit(" -> ", 1)[-1].strip().strip('"') for line in status.splitlines() if len(line) >= 4]
    return GitSnapshot(branch.strip() or "unknown", head.strip() or "unknown", tuple(sorted(set(paths))), tuple(e for e in (e1, e2, e3) if e))


def save_git_snapshot(path: Path | str, snapshot: GitSnapshot) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def load_git_snapshot(path: Path | str) -> GitSnapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return GitSnapshot(str(data.get("branch", "unknown")), str(data.get("head", "unknown")), tuple(sorted(str(item) for item in data.get("dirty_paths", ()) or ())))


def dirty_diff(baseline: GitSnapshot, current: GitSnapshot) -> dict[str, Any]:
    before, now = set(baseline.dirty_paths), set(current.dirty_paths)
    return {"pre_existing_dirty": sorted(before), "experiment_owned_dirty": sorted(now - before), "cleaned_since_baseline": sorted(before - now), "current_dirty": sorted(now)}


def _compact_paths(paths: Iterable[str], limit: int = 100) -> dict[str, Any]:
    values = sorted(set(paths))
    return {"paths": values[:limit], "count": len(values), "truncated": len(values) > limit}


def disk_check(path: Path | str, *, min_free_gb: float = DEFAULT_DISK_FREE_GB, required_bytes: int = 0, usage_fn: Callable[[str], Any] = shutil.disk_usage) -> DiskCheck:
    value = float(min_free_gb)
    if isinstance(min_free_gb, bool) or not math.isfinite(value) or value < 0: raise ValueError("min_free_gb must be finite and non-negative")
    if int(required_bytes) < 0: raise ValueError("required_bytes must be non-negative")
    target = Path(path).resolve()
    return DiskCheck(str(target), int(usage_fn(str(target)).free), int(required_bytes), int(value * 1024 ** 3))


def process_alive(pid: object) -> bool:
    try: value = int(str(pid))
    except (TypeError, ValueError): return False
    if value <= 0: return False
    if os.name == "nt":
        try:
            result = subprocess.run(["tasklist", "/FI", f"PID eq {value}"], capture_output=True, text=True, timeout=10, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired): return True
        return result.returncode == 0 and "No tasks" not in f"{result.stdout}\n{result.stderr}"
    try: os.kill(value, 0)
    except ProcessLookupError: return False
    except OSError: return True
    return True


def worktree_occupancy(repo_root: Path | str, *, active_marker: Path | str | None = None, conflicting_pids: Iterable[object] = ()) -> dict[str, Any]:
    """Dirty files do not occupy a worktree; active markers and live PIDs do."""
    root = Path(repo_root).resolve()
    marker = Path(active_marker) if active_marker else root / ".v2ctl/active.json"
    data: Mapping[str, Any] = {}
    if marker.is_file():
        try:
            loaded = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(loaded, dict): data = loaded
        except (OSError, ValueError): data = {"marker_unreadable": True}
    active = marker.is_file() and data.get("active", True) is not False
    pids = [int(str(pid)) for pid in conflicting_pids if str(pid).lstrip("-").isdigit()]
    live = [pid for pid in pids if process_alive(pid)]
    return {"occupied": active or bool(live), "active_marker": str(marker), "active_marker_present": marker.is_file(), "active_marker_active": active, "conflicting_pids": pids, "live_conflicting_pids": live, "dirty_is_occupancy": False}


def classify_lock(lock: DeployLock) -> dict[str, Any]:
    status = lock.status()
    if status is None:
        path = getattr(lock, "_lock_path", None)
        try: present = bool(path and os.path.lexists(os.fspath(path)))
        except OSError: present = True
        return {"present": present, "ambiguous": present, "corrupt_or_unreadable": present, "stale": False, "live_owner": False}
    stale = lock.is_stale(status)
    return {"present": True, "ambiguous": False, "corrupt_or_unreadable": False, "stale": stale, "live_owner": not stale, **{key: status.get(key) for key in ("owner", "pid", "host", "target", "profile")}}


def classify_outcome(*, attempted: bool, returncode: int | None = None, timed_out: bool = False, artifact_found: bool = False, valid: bool = False, error_kind: str = "") -> str:
    if not attempted: return NOT_SENT
    if timed_out or (returncode is not None and returncode != 0): return REMOTE_FAILED
    if not artifact_found: return ARTIFACT_DNF
    return VALID if valid else INVALID


def _validate_app(app: str) -> str:
    value = str(app or "").strip().lower()
    if value == PROTECTED_APP or not _APP_RE.fullmatch(value): raise ValueError(f"invalid or production-protected Golden app: {app!r}")
    return value


def supported_command(repo_root: Path | str, operation: str, app: str) -> tuple[str, ...]:
    root, app = Path(repo_root).resolve(), _validate_app(app)
    script = root / "tools/v2ctl.py"
    if operation == "deploy": return (sys.executable, str(script), "golden", "deploy", "--app", app)
    if operation in {"source-probe", "source_probe"}: return (sys.executable, str(script), "--profile", DEFAULT_PROFILE, "--app", app, "source-probe")
    raise ValueError(f"unsupported guarded operation: {operation}")


def _inspect_supported_state(repo_root: Path, app: str) -> dict[str, Any]:
    commands = (("lock status", "lock", "status"), ("golden status", "golden", "status", "--app", app), ("doctor", "doctor", "--profile", DEFAULT_PROFILE, "--app", app))
    result: dict[str, Any] = {}
    for name, *args in commands:
        try:
            completed = subprocess.run([sys.executable, str(repo_root / "tools/v2ctl.py"), *args], cwd=str(repo_root), capture_output=True, text=True, timeout=30, check=False)
            result[name] = {"returncode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-2000:]}
        except (OSError, subprocess.TimeoutExpired) as exc: result[name] = {"error": type(exc).__name__}
    result["lock"] = classify_lock(DeployLock(repo_root / ".v2ctl/deploy.lock"))
    return result


def _timeout_retry_is_proven_safe(state: Mapping[str, Any]) -> bool:
    lock = state.get("lock", {})
    return bool(state.get("retry_safe") is True and state.get("remote_completion") in {"not_started", "failed"} and isinstance(lock, Mapping) and not lock.get("present"))


def _inspection_text(state: Mapping[str, Any]) -> str:
    try: return json.dumps(state, sort_keys=True, default=str)[:4000]
    except (TypeError, ValueError): return repr(state)[:4000]


def run_safe_operation(repo_root: Path | str, operation: str, app: str, *, timeout: float | None = None, retries: int = 0, run_fn: Callable[..., Any] = subprocess.run) -> SafeOperationResult:
    root, command = Path(repo_root).resolve(), supported_command(repo_root, operation, app)
    default = DEFAULT_DEPLOY_TIMEOUT if operation == "deploy" else DEFAULT_SOURCE_PROBE_TIMEOUT
    limit = float(timeout if timeout is not None else default)
    if not math.isfinite(limit) or limit <= 0 or retries < 0 or retries > MAX_RETRIES: raise ValueError(f"timeout must be finite and positive; retries must be between 0 and {MAX_RETRIES}")
    inspections: list[dict[str, Any]] = []
    started = time.monotonic()
    for attempt in range(retries + 1):
        if attempt:
            state = _inspect_supported_state(root, _validate_app(app)); inspections.append({"attempt": attempt, "state": state})
            lock = state.get("lock", {})
            if isinstance(lock, Mapping) and lock.get("present") and not lock.get("stale"):
                return SafeOperationResult(operation, command, False, None, False, time.monotonic() - started, NOT_SENT, inspections=tuple(inspections))
        try:
            completed = run_fn(command, cwd=str(root), capture_output=True, text=True, timeout=limit, check=False)
            code = int(str(getattr(completed, "returncode", 1))); stdout = str(getattr(completed, "stdout", "") or ""); stderr = str(getattr(completed, "stderr", "") or "")
            if code == 0: return SafeOperationResult(operation, command, True, code, False, time.monotonic() - started, VALID, stdout=stdout, stderr=stderr, inspections=tuple(inspections))
            if attempt == retries: return SafeOperationResult(operation, command, True, code, False, time.monotonic() - started, REMOTE_FAILED, stdout=stdout, stderr=stderr, inspections=tuple(inspections))
        except subprocess.TimeoutExpired as exc:
            state = _inspect_supported_state(root, _validate_app(app)); inspections.append({"attempt": attempt, "after_timeout": True, "state": state}); safe = _timeout_retry_is_proven_safe(state)
            if attempt < retries and safe: continue
            classification = "operation_timeout_no_retry" if safe else "operation_timeout_state_ambiguous"
            return SafeOperationResult(operation, command, True, None, True, time.monotonic() - started, REMOTE_FAILED, timeout_classification=classification, stdout=str(exc.stdout or ""), stderr=(str(exc.stderr or "") + "\nstate_inspection=" + _inspection_text(state))[-8000:], inspections=tuple(inspections))
        except OSError as exc:
            return SafeOperationResult(operation, command, False, None, False, time.monotonic() - started, NOT_SENT, stderr=f"{type(exc).__name__}: {exc}", inspections=tuple(inspections))
    raise AssertionError("bounded operation loop did not return")


def external_repo_changes(repo_root: Path | str) -> list[dict[str, Any]]:
    root, custom = Path(repo_root).resolve(), resolve_custom_nodes_root(repo_root)
    if not custom.is_dir(): return []
    changed = []
    for node in sorted(custom.iterdir()):
        if not node.is_dir() or node.resolve() == root or not (node / ".git").exists(): continue
        raw, _ = _git(node, "status", "--porcelain=v1", "--untracked-files=all")
        paths = [line[3:].strip() for line in raw.splitlines() if len(line) >= 4]
        if paths: changed.append({"path": str(node.resolve()), "changed_paths": paths})
    return changed


def _value(data: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = data
        for key in path:
            if not isinstance(value, Mapping) or key not in value: break
            value = value[key]
        else:
            if value is not None: return value
    return None


def _status_match(value: Any, accepted: set[str]) -> bool:
    return value if isinstance(value, bool) else str(value or "").strip().casefold() in accepted


def _manifest_target(data: Mapping[str, Any]) -> Mapping[str, Any]:
    target = _value(data, ("target",), ("deploy_inputs", "target"), ("deployment_identity",))
    return target if isinstance(target, Mapping) else {}


def _effective_flags(data: Mapping[str, Any]) -> dict[str, str]:
    paths = (("effective_environment",), ("effective_config", "deploy_flags"), ("effective_config", "flags"), ("effective_config", "effective_environment"), ("deploy_inputs", "deploy_flags"), ("deploy_inputs", "effective_flags"), ("flags",))
    for path in paths:
        value = _value(data, path)
        if isinstance(value, Mapping): return {str(key): str(item) for key, item in value.items()}
    return {}


def _parse_expected_flags(values: Iterable[str] | Mapping[str, Any]) -> tuple[dict[str, str], list[str]]:
    if isinstance(values, Mapping): return {str(key): str(value) for key, value in values.items()}, []
    expected, errors = {}, []
    for raw in values or ():
        text = str(raw)
        if "=" not in text or not text.split("=", 1)[0].strip(): errors.append(f"invalid expected flag {text!r}; use NAME=VALUE"); continue
        name, value = text.split("=", 1); expected[name.strip()] = value
    return expected, errors


def _telemetry_families(path: Path) -> tuple[set[str], str | None]:
    if not path.exists(): return set(), "telemetry path does not exist"
    files = [path] if path.is_file() else sorted(path.rglob("*.json*")) if path.is_dir() else []
    if not files: return set(), "telemetry path is not a readable file or JSON directory"
    families: set[str] = set()
    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).casefold() in {"family", "event_family", "eventfamily"} and isinstance(item, str): families.add(item)
                visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    try:
        for file in files:
            text = file.read_text(encoding="utf-8")
            try: visit(json.loads(text))
            except json.JSONDecodeError:
                for line in text.splitlines():
                    if line.strip(): visit(json.loads(line))
    except (OSError, UnicodeError, ValueError) as exc: return families, f"telemetry could not be read: {type(exc).__name__}: {exc}"
    return families, None


def _custom_nodes_report(root: Path) -> dict[str, Any]:
    published = list(iter_publication_files(root)); counts: dict[str, int] = {}
    for path in published:
        parts = path.relative_to(root).parts
        if parts: counts[parts[0]] = counts.get(parts[0], 0) + 1
    included, skipped = set(iter_syncable_custom_node_dirs(root)), []
    for entry in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        reason = custom_node_filter_reason(entry.name, entry)
        if reason is not None: skipped.append({"name": entry.name, "reason": reason})
        elif entry.name not in counts: included.discard(entry.name); skipped.append({"name": entry.name, "reason": "no_publishable_files"})
    return {"included": sorted(included), "skipped": skipped, "publication_file_count": len(published)}


def _deployment_evidence(root: Path, profile: str, app: str, errors: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"manifest": None, "source_probe": None, "flag_effective": {}}
    try:
        from . import config as config_mod, fingerprints as fingerprints_mod, profiles as profiles_mod, registry as registry_mod
        registry = registry_mod.FlagRegistry(root / "config/v2/flag_registry.toml")
        config = config_mod.ConfigResolver(root, profiles_mod.Profiles(root / "config/v2/profiles"), registry).resolve(profile_name=profile, cli_options={"target.app": _validate_app(app)} if app else {})
        result["flag_effective"] = {flag.name: str(flag.value) for flag in (*config.flags, *config.unregistered)}
        result["deploy_fingerprint"] = fingerprints_mod.FingerprintEngine(config).deploy_fingerprint()
        result["target_identity"] = {"app": str(config.target.app), "class": str(config.target.class_name), "method": str(config.target.method), "profile": str(config.profile_name)}
        for path in sorted((root / ".v2ctl/deployments").glob("deploy_*.json"), reverse=True):
            try: data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc: errors.append(f"manifest {path} could not be read: {type(exc).__name__}: {exc}"); continue
            if not isinstance(data, dict): continue
            target = _manifest_target(data); manifest_profile = _value(data, ("profile",), ("deploy_inputs", "profile"), ("artifacts", "profile"), ("deployment_identity", "profile"))
            if manifest_profile != profile or (app and (target.get("app") or target.get("app_name")) != app): continue
            source = _value(data, ("source_identity_status",), ("source_identity", "status"), ("source_identity", "verdict"), ("source_identity",)); health = _value(data, ("runtime_health_status",), ("runtime_health", "status"), ("runtime_health",), ("health", "status"), ("health",))
            source = source.get("status", source.get("verdict")) if isinstance(source, Mapping) else source; health = health.get("status", health.get("verdict")) if isinstance(health, Mapping) else health
            result["manifest"] = {"path": str(path), "deploy_fingerprint": _value(data, ("deploy_fingerprint",), ("deploy_inputs", "deploy_fingerprint"), ("deployment_identity", "deploy_fingerprint")), "profile": manifest_profile, "target": dict(target), "source_identity_status": "MATCH" if _status_match(source, {"match", "verified", "ok", "healthy"}) else str(source or "MISSING"), "runtime_health_status": "READY" if _status_match(health, {"ready", "healthy", "ok"}) else str(health or "MISSING"), "effective_flags": _effective_flags(data)}
            break
        fingerprint = (result["manifest"] or {}).get("deploy_fingerprint")
        if fingerprint:
            for path in sorted((root / ".v2ctl/source-probes").glob("*.json"), reverse=True):
                try: data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError): continue
                if not isinstance(data, dict) or _value(data, ("deploy_fingerprint",), ("classification", "deploy_fingerprint")) != fingerprint: continue
                verdict = _value(data, ("verdict",), ("classification", "verdict"), ("source_identity_status",))
                result["source_probe"] = {"path": str(path), "deploy_fingerprint": fingerprint, "verdict": verdict, "status": "MATCH" if _status_match(verdict, {"match", "verified", "ok"}) else "FAIL"}; break
    except Exception as exc:
        result["resolution_error"] = f"{type(exc).__name__}: {exc}"; errors.append(result["resolution_error"])
    return result


def preflight(repo_root: Path | str, *, profile: str = DEFAULT_PROFILE, app: str = "", baseline_file: Path | str | None = None, min_free_gb: float = DEFAULT_DISK_FREE_GB, telemetry_path: Path | str | None = None, require_evidence: bool = False, expected_flags: Iterable[str] | Mapping[str, Any] = (), required_events: Iterable[str] = (), require_operation: bool = False) -> dict[str, Any]:
    root, current = Path(repo_root).resolve(), capture_git_snapshot(repo_root); errors = list(current.inspection_errors)
    try: baseline = load_git_snapshot(baseline_file) if baseline_file and Path(baseline_file).is_file() else current
    except (OSError, ValueError, TypeError) as exc: baseline = current; errors.append(f"baseline could not be read: {type(exc).__name__}: {exc}")
    disk, lock = disk_check(root, min_free_gb=min_free_gb), classify_lock(DeployLock(root / ".v2ctl/deploy.lock"))
    try:
        resolution = resolve_custom_nodes_root_details(root); nodes_root = Path(resolution.root); custom_nodes = _custom_nodes_report(nodes_root)
    except (OSError, RuntimeError, ValueError) as exc:
        nodes_root, resolution, custom_nodes = resolve_custom_nodes_root(root), None, {"included": [], "skipped": []}; errors.append(f"custom-nodes resolution failed: {type(exc).__name__}: {exc}")
    identity_error = ""
    if app:
        try: app = _validate_app(app)
        except ValueError as exc: identity_error = str(exc)
    if profile and not str(profile).startswith("golden_p1"): identity_error = identity_error or f"Golden guard requires a golden_p1 profile, got {profile!r}"
    deployment = _deployment_evidence(root, profile, app, errors) if profile and not identity_error else {"manifest": None, "source_probe": None, "flag_effective": {}}
    expected, expected_errors = _parse_expected_flags(expected_flags); errors.extend(expected_errors); required = [str(value) for value in required_events]
    if telemetry_path or required:
        path = Path(telemetry_path).resolve() if telemetry_path else root / "__missing_telemetry__"; families, telemetry_error = _telemetry_families(path); lowered = {family.casefold() for family in families}
        deployment["telemetry"] = {"path": str(path), "present": telemetry_error is None, "families": sorted(families), "required_events": {event: event.casefold() in lowered for event in required}}
        if telemetry_error and required: errors.append(telemetry_error)
    persisted = (deployment.get("manifest") or {}).get("effective_flags", {}); deployment["expected_flags"] = {name: {"expected": value, "actual": persisted.get(name), "match": persisted.get(name) == value} for name, value in expected.items()}
    diff = {}
    for name, values in dirty_diff(baseline, current).items():
        compact = _compact_paths(values); diff.update({name: compact["paths"], f"{name}_count": compact["count"], f"{name}_truncated": compact["truncated"]})
    git, compact = current.as_dict(), _compact_paths(current.dirty_paths); git.update({"dirty_paths": compact["paths"], "dirty_paths_count": compact["count"], "dirty_paths_truncated": compact["truncated"], "diff": diff})
    external = external_repo_changes(root)
    for change in external: change["changed_paths"] = _compact_paths(change["changed_paths"], limit=40)
    report = {"profile": profile, "app": str(app or "").strip().lower(), "git": git, "disk": disk.as_dict(), "occupancy": worktree_occupancy(root), "resolution_errors": errors, "custom_nodes_resolution": resolution.as_dict() if resolution else None, "canonical_custom_nodes_root": str(nodes_root), "custom_nodes": custom_nodes, "external_repo_protection": {"mode": "read-only", "changed": external}, "lock": lock, "deployment_checks": deployment, "reminders": list(GOLDEN_REMINDERS)}
    if identity_error: deployment["identity_error"] = identity_error
    telemetry, manifest, probe = deployment.get("telemetry", {}), deployment.get("manifest") or {}, deployment.get("source_probe") or {}; target, identity = manifest.get("target", {}), deployment.get("target_identity", {})
    target_ok = bool(manifest.get("profile") == profile and target.get("app", target.get("app_name")) == app and target.get("class", target.get("class_name")) == identity.get("class") and target.get("method") == identity.get("method")); fingerprint_ok = bool(manifest.get("deploy_fingerprint") and manifest.get("deploy_fingerprint") == deployment.get("deploy_fingerprint"))
    evidence_ok = bool(manifest and fingerprint_ok and target_ok and manifest.get("source_identity_status") == "MATCH" and manifest.get("runtime_health_status") in {"READY", "HEALTHY"} and probe.get("status") == "MATCH" and probe.get("deploy_fingerprint") == manifest.get("deploy_fingerprint") and (not telemetry_path or telemetry.get("present")) and all(item["match"] for item in deployment["expected_flags"].values()) and all(telemetry.get("required_events", {}).get(event) is True for event in required)); deployment["evidence_ok"] = evidence_ok
    report["ok"] = bool(disk.ok and not identity_error and not errors and (not (require_evidence or expected or required) or (evidence_ok and not report["occupancy"]["occupied"])) and (not require_operation or not report["occupancy"]["occupied"]))
    return report


def bootstrap_worktree(repo_root: Path | str, destination: Path | str) -> dict[str, Any]:
    """Create a detached source worktree and copy no credentials or runtime state."""
    root, target = Path(repo_root).resolve(), Path(destination).resolve()
    if target.exists(): raise ValueError(f"bootstrap destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "worktree", "add", "--detach", str(target), "HEAD"], cwd=str(root), check=True, capture_output=True, text=True, timeout=60)
    skipped = [{"path": path, "reason": "secret_or_runtime_state_not_copied" if (root / path).exists() or os.path.lexists(root / path) else "missing_required_ignored_file"} for path in BOOTSTRAP_FILE_PATHS]
    return {"worktree": str(target), "copied": [], "skipped": skipped, "required_ignored_files_missing": [path for path in REQUIRED_LOCAL_PATHS if path != "config/v2/modal_target.toml" and not (root / path).exists()], "large_caches_copied": False}
