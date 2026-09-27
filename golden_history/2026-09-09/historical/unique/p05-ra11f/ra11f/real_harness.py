"""Disposable, process-isolated RA11F probe for the installed ComfyUI packages.

This module is intentionally separate from :mod:`ra11f.harness`.  It copies the
current ComfyUI source and the installed custom-node trees into a temporary
directory, then invokes the real ``nodes`` loader in a child interpreter.  No
loader state, package files, configuration, models, output, GPU, Modal, or
network activity is shared with the live installation.

The probe is discovery-only.  A successful import is not an execution or
parity claim; parity is exact and scoped, and any observed unsafe signal keeps
the package unsafe to narrow.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import hashlib
import importlib
import inspect
import io
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import warnings
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMFY_ROOT = REPO_ROOT.parents[1]
REGISTRY_NAME = ".studio_custom_nodes.json"
SCHEMA_VERSION = "ra11f.real.v1"
EXCLUDED_NAMES = {"comfyui-modal", "comfyui-modal-r42", "comfyui-modal-r41"}


def _json(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_json(value), sort_keys=True).encode()).hexdigest()


def _workflow_prompt(path: Path) -> dict[str, dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = document.get("payload", document)
    prompt = payload.get("prompt", payload.get("outputs", {}))
    if not isinstance(prompt, Mapping):
        raise ValueError(f"workflow has no mapping prompt: {path}")
    return {str(k): dict(v) for k, v in prompt.items() if isinstance(v, Mapping)}


def workflow_class_ids(prompt: Mapping[Any, Mapping[str, Any]]) -> list[str]:
    """Return real class IDs in stable prompt order, retaining unknown IDs."""
    result: list[str] = []
    for entry in prompt.values():
        class_id = entry.get("class_type", entry.get("class_id"))
        if class_id is not None and str(class_id) not in result:
            result.append(str(class_id))
    return result


def package_selection(prompt: Mapping[Any, Mapping[str, Any]], owner_map: Mapping[str, str]) -> dict[str, Any]:
    """Resolve an external package set without authorizing unknown classes."""
    classes = workflow_class_ids(prompt)
    unknown = [class_id for class_id in classes if class_id not in owner_map]
    return {
        "class_ids": classes,
        "unknown_class_ids": unknown,
        "selected_packages": sorted({str(owner_map[class_id]) for class_id in classes if class_id in owner_map}),
        "fallback": bool(unknown),
    }


def load_registry(repo_root: Path = REPO_ROOT, comfy_root: Path | None = None) -> list[dict[str, Any]]:
    """Load installed package metadata and retain only existing real trees."""
    registry_path = repo_root / REGISTRY_NAME
    records = json.loads(registry_path.read_text(encoding="utf-8"))
    result: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        install_path = Path(str(raw.get("install_path", "")))
        if not install_path.is_dir() and comfy_root is not None:
            install_path = comfy_root / "custom_nodes" / install_path.name
        name = install_path.name
        if not install_path.is_dir() or name in EXCLUDED_NAMES or name.endswith(".disabled"):
            continue
        resolved = install_path.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        result.append({
            "package_id": name,
            "name": str(raw.get("name", name)),
            "install_path": str(resolved),
            "classes_metadata": [str(v) for v in raw.get("classes", [])],
            "repo_url": str(raw.get("repo_url", "")),
            "installed_commit": str(raw.get("installed_commit", "")),
        })
    return result


def _source_flags(package: Mapping[str, Any]) -> dict[str, Any]:
    """Conservative source audit; it assigns no proof level or safety grade."""
    root = Path(str(package["install_path"]))
    text_parts: list[str] = []
    files: list[str] = []
    for path in root.rglob("*.py"):
        try:
            text_parts.append(path.read_text(encoding="utf-8", errors="replace"))
            files.append(str(path.relative_to(root)).replace("\\", "/"))
        except OSError:
            continue
    text = "\n".join(text_parts)
    checks = {
        "dynamic_imports": bool(re.search(r"(?:importlib(?:\.|\s)|__import__\s*\(|pkgutil\.)", text)),
        "routes_hooks": bool(re.search(r"(?:add_route|APIRouter|routes?\s*=|hook|on_load|on_unload|comfy_entrypoint)", text, re.I)),
        "filesystem_writes": bool(re.search(r"(?:open\s*\([^\n]*(?:['\"]w|['\"]a)|write_text\s*\(|write_bytes\s*\(|makedirs\s*\(|mkdir\s*\(|rmtree\s*\()", text)),
        "reloads": bool(re.search(r"importlib\.reload\s*\(", text)),
        # Source scanning cannot prove the transitive import/runtime closure;
        # remain conservative even when no specific pattern matched.
        "unknown_transitive_behavior": True,
    }
    reasons = [name for name, present in checks.items() if present]
    if not reasons:
        reasons.append("no flagged source pattern; runtime behavior remains unproven")
    return {
        "package_id": str(package["package_id"]),
        "source_files_scanned": len(files),
        "flags": checks,
        "reasons": reasons,
        "proof_level": "not_assigned",
        "safe_to_narrow": False,
    }


def package_audits(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_source_flags(record) for record in records]


def metadata_owner_map(records: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Return only explicit registry ownership, never inferred proof."""
    result: dict[str, str] = {}
    for record in records:
        package_id = str(record["package_id"])
        for class_id in record.get("classes_metadata", []):
            result.setdefault(str(class_id), package_id)
    return result


def _copy_tree(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, copy_function=shutil.copy2)


def make_sandbox(comfy_root: Path, records: Iterable[Mapping[str, Any]], parent: Path | None = None) -> Path:
    """Copy only runtime source and actual registered package trees."""
    sandbox = Path(tempfile.mkdtemp(prefix="ra11f_real_", dir=str(parent) if parent else None))
    for path in comfy_root.iterdir():
        if path.is_file() and path.suffix == ".py":
            shutil.copy2(path, sandbox / path.name)
    # These are import/runtime support packages used by the current nodes.py;
    # model, input, output, user, and temp data are deliberately not copied.
    for directory in (
        "comfy",
        "comfy_api",
        "comfy_api_nodes",
        "comfy_config",
        "comfy_execution",
        "comfy_extras",
        "api_server",
        "app",
        "input",
        "middleware",
        "utils",
    ):
        _copy_tree(comfy_root / directory, sandbox / directory)
    custom_nodes = sandbox / "custom_nodes"
    custom_nodes.mkdir()
    for record in records:
        source = Path(str(record["install_path"]))
        _copy_tree(source, custom_nodes / str(record["package_id"]))
    (sandbox / "models").mkdir()
    return sandbox


def _fd_snapshot() -> list[str]:
    proc = Path("/proc/self/fd")
    if proc.exists():
        return sorted(p.name for p in proc.iterdir())
    try:
        import psutil  # type: ignore
        return [str(v) for v in psutil.Process().open_files()]
    except Exception:
        return []


def _resource_snapshot() -> dict[str, Any]:
    threads = [{"name": t.name, "ident": t.ident, "daemon": t.daemon, "alive": t.is_alive()} for t in threading.enumerate()]
    return {
        "thread_count": len(threads),
        "threads": threads,
        "non_daemon_threads": [t for t in threads if not t["daemon"]],
        "open_fds": _fd_snapshot(),
        "fd_observation_available": bool(_fd_snapshot()),
    }


def _tree_snapshot(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            result[str(path.relative_to(root)).replace("\\", "/")] = {"size": stat.st_size}
        except OSError:
            pass
    return result


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(v) for v in value]
    return {"type": type(value).__name__, "module": getattr(type(value), "__module__", "")}


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append({"level": record.levelname, "message": self.format(record)})


class MonotonicPackageController:
    """Small request-local admission record; it never unloads or reloads a package."""

    def __init__(self) -> None:
        self.attempted: set[str] = set()
        self.initialized: set[str] = set()
        self.complete_discovery_used = False

    def plan(self, selected: Iterable[str], *, complete: bool = False) -> list[str]:
        if complete:
            self.complete_discovery_used = True
            return sorted({str(package_id) for package_id in selected if str(package_id) not in self.attempted})
        if self.complete_discovery_used:
            return []
        return sorted({str(package_id) for package_id in selected if str(package_id) not in self.attempted})

    def record(self, package_id: str, success: bool) -> None:
        package_id = str(package_id)
        self.attempted.add(package_id)
        if success:
            self.initialized.add(package_id)

    def snapshot(self) -> dict[str, Any]:
        return {"attempted": sorted(self.attempted), "initialized": sorted(self.initialized), "complete_discovery_used": self.complete_discovery_used, "no_unload_reload": True}


def _package_id(path: str, custom_root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(custom_root.resolve()).parts[0]
    except (ValueError, IndexError):
        return Path(path).name


def _module_observation(before: set[str], package_id: str) -> dict[str, Any]:
    after = set(sys.modules)
    names = sorted(after - before)
    return {"package_id": package_id, "imported_modules": names}


def _normalize_path(value: Any, sandbox: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(sandbox), "<sandbox>").replace("\\", "/")
    if isinstance(value, Mapping):
        return {str(k): _normalize_path(v, sandbox) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_path(v, sandbox) for v in value]
    return value


async def _invoke_loader(nodes: Any, mode: str, sandbox: Path, selected: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    custom_root = sandbox / "custom_nodes"
    observations: list[dict[str, Any]] = []
    original = nodes.load_custom_node

    async def observed(path: str, ignore=set(), module_parent="custom_nodes") -> bool:
        package_id = _package_id(path, custom_root)
        before = set(sys.modules)
        started = time.perf_counter()
        try:
            success = await original(path, ignore, module_parent)
        except Exception as exc:  # the upstream loader normally catches this
            success = False
            observations.append({"package_id": package_id, "error": f"{type(exc).__name__}: {exc}"})
        observation = _module_observation(before, package_id)
        observation.update({"path": str(path), "success": bool(success), "wall_ms": round((time.perf_counter() - started) * 1000, 3)})
        module_name = str(path).replace(".", "_x_")
        module = sys.modules.get(module_name)
        if module is not None:
            lifecycle = {}
            for name in dir(module):
                lowered = name.lower()
                if any(token in lowered for token in ("route", "hook", "load", "unload", "lifecycle")):
                    if name.startswith("_"):
                        continue
                    try:
                        lifecycle[name] = _safe_value(getattr(module, name))
                    except Exception:
                        lifecycle[name] = "<unreadable>"
            observation["lifecycle_observations"] = lifecycle
        observations.append(observation)
        return bool(success)

    nodes.load_custom_node = observed
    try:
        if mode == "FULL":
            await nodes.init_external_custom_nodes()
        else:
            base_names = set(nodes.NODE_CLASS_MAPPINGS.keys())
            for package_id in sorted(selected):
                await nodes.load_custom_node(str(custom_root / package_id), base_names, module_parent="custom_nodes")
    finally:
        nodes.load_custom_node = original
    return observations, [str(v) for v in sorted(sys.modules)]


def _state(nodes: Any, observations: list[dict[str, Any]], modules: list[str], sandbox: Path) -> dict[str, Any]:
    mappings: dict[str, Any] = {}
    relative: dict[str, str] = {}
    for class_id, node_cls in getattr(nodes, "NODE_CLASS_MAPPINGS", {}).items():
        rel = str(getattr(node_cls, "RELATIVE_PYTHON_MODULE", ""))
        mappings[str(class_id)] = {"owner": rel.rsplit(".", 1)[-1] if rel else "", "class": getattr(node_cls, "__name__", type(node_cls).__name__), "module": getattr(node_cls, "__module__", "")}
        relative[str(class_id)] = rel
    loaded = _normalize_path(_safe_value(getattr(nodes, "LOADED_MODULE_DIRS", {})), sandbox)
    web = _normalize_path(_safe_value(getattr(nodes, "EXTENSION_WEB_DIRS", {})), sandbox)
    imported = sorted(set(modules))
    normalized_observations = _normalize_path(copy.deepcopy(observations), sandbox)
    normalized_modules = [_normalize_path(str(v), sandbox) for v in modules]
    return {
        "class_mappings": _normalize_path(dict(sorted(mappings.items())), sandbox),
        "class_owner": {k: v["owner"] for k, v in sorted(mappings.items())},
        "RELATIVE_PYTHON_MODULE": dict(sorted(relative.items())),
        "display_mappings": _safe_value(getattr(nodes, "NODE_DISPLAY_NAME_MAPPINGS", {})),
        "LOADED_MODULE_DIRS": loaded,
        "EXTENSION_WEB_DIRS": web,
        "imported_module_names": sorted(set(normalized_modules)),
        "import_order": [str(v["package_id"]) for v in normalized_observations],
        "package_observations": normalized_observations,
        "import_failures": [v for v in normalized_observations if not v.get("success", True) or v.get("error")],
        "routes_hooks_lifecycle": [v for v in normalized_observations if v.get("lifecycle_observations")],
    }


def _owner_map(state: Mapping[str, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in state.get("class_owner", {}).items() if v}


def _run_child(arm: str, comfy_root: Path, workflow: Path, owner_map: Mapping[str, str], records: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    sandbox: Path | None = None
    capture = _Capture()
    root_logger = logging.getLogger()
    root_logger.addHandler(capture)
    root_logger.setLevel(logging.INFO)
    before_resources = _resource_snapshot()
    try:
        sandbox = make_sandbox(comfy_root, records)
        before_files = _tree_snapshot(sandbox)
        original_argv = sys.argv[:]
        # cli_args reads --base-directory during the real imports.
        sys.argv = [sys.argv[0], "--base-directory", str(sandbox)]
        sys.path.insert(0, str(sandbox))
        try:
            nodes = importlib.import_module("nodes")
            prompt = _workflow_prompt(workflow)
            selection = package_selection(prompt, owner_map)
            classes = selection["class_ids"]
            unknown = selection["unknown_class_ids"]
            selected = set(selection["selected_packages"])
            fallback = selection["fallback"]
            selected_before_complete = False
            controller = MonotonicPackageController()
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                if arm == "SELECTIVE" and fallback:
                    # An unknown class invalidates the owner-derived selection.
                    # The complete real loader is the only permissible fallback.
                    planned = controller.plan((record["package_id"] for record in records), complete=True)
                    observations, imported = awaitable_run(_invoke_loader(nodes, "FULL", sandbox, set()))
                    selected_before_complete = False
                else:
                    planned = controller.plan((record["package_id"] for record in records) if arm == "FULL" else selected, complete=arm == "FULL")
                    observations, imported = awaitable_run(_invoke_loader(nodes, arm, sandbox, set(planned)))
                for observation in observations:
                    controller.record(str(observation["package_id"]), bool(observation.get("success", False)))
            after_files = _tree_snapshot(sandbox)
            state = _state(nodes, observations, imported, sandbox)
            state["filesystem"] = {
                "before": before_files,
                "after": after_files,
                "created": sorted(set(after_files) - set(before_files)),
                "removed": sorted(set(before_files) - set(after_files)),
            }
            state["package_resources"] = {
                package_id: sorted(
                    path[len(f"custom_nodes/{package_id}/") :]
                    for path in before_files
                    if path.startswith(f"custom_nodes/{package_id}/")
                )
                for package_id in (str(record["package_id"]) for record in records)
            }
            mutations = state["filesystem"]["created"] + state["filesystem"]["removed"]
            state["package_filesystem_mutations"] = {
                package_id: [path for path in mutations if path.startswith(f"custom_nodes/{package_id}/")]
                for package_id in (str(record["package_id"]) for record in records)
            }
            state["controller"] = controller.snapshot()
            after_resources = _resource_snapshot()
            return {
                "schema_version": SCHEMA_VERSION,
                "arm": arm,
                "status": "ok",
                "sandbox": {"disposable": True, "base_directory_used": True},
                "workflow": {"path": str(workflow), "class_ids": classes, "unknown_class_ids": unknown},
                "selection": {"selected_packages": sorted(selected), "fallback": fallback, "selected_before_complete": selected_before_complete, "reason": "unknown class owner; complete discovery required" if fallback else "owner observation from FULL"},
                "state": state,
                "resources": {"before": before_resources, "after": after_resources, "thread_delta": after_resources["thread_count"] - before_resources["thread_count"], "fd_delta": len(after_resources["open_fds"]) - len(before_resources["open_fds"])},
                "warnings": [str(item.message) for item in caught_warnings],
                "logging": capture.records,
                "errors": [item["message"] for item in capture.records if item["level"] in {"ERROR", "CRITICAL"}],
                "wall_ms": round((time.perf_counter() - started) * 1000, 3),
                "claims": {"real_package_discovery": True, "real_package_parity": False, "execution": False, "output": False, "modal": False},
            }
        finally:
            sys.argv = original_argv
            try:
                sys.path.remove(str(sandbox))
            except ValueError:
                pass
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "arm": arm,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "claims": {"real_package_discovery": False, "real_package_parity": False, "execution": False, "output": False, "modal": False},
            "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    finally:
        root_logger.removeHandler(capture)
        if sandbox is not None:
            shutil.rmtree(sandbox, ignore_errors=True)


# Kept as a named helper so tests can patch/inspect the only async boundary.
def awaitable_run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _make_projection(full_state: Mapping[str, Any], label: str, explicit_owners: Mapping[str, str] | None = None) -> dict[str, Any]:
    owners = dict(explicit_owners or {})
    observed = _owner_map(full_state)
    if explicit_owners:
        allowed = set(explicit_owners.values())
        observed = {class_id: package_id for class_id, package_id in observed.items() if package_id in allowed}
    owners.update(observed)
    by_package: dict[str, list[str]] = {}
    for class_id, package_id in owners.items():
        if package_id:
            by_package.setdefault(package_id, []).append(class_id)
    packages = sorted((package, sorted(classes)) for package, classes in by_package.items())
    chosen: list[tuple[str, list[str]]]
    if label == "projection_a":
        chosen = packages[:1]
    else:
        chosen = packages[1:2] or packages[:1]
    prompt: dict[str, Any] = {}
    for index, (package, classes) in enumerate(chosen):
        if classes:
            prompt[f"ra11f-{label}-{index}"] = {"class_type": classes[0], "inputs": {}}
    return {"name": label, "prompt": prompt, "selected_packages_expected": [p for p, _ in chosen], "discovery_only": True}


def _scoped_state(state: Mapping[str, Any], packages: set[str]) -> dict[str, Any]:
    owners = state.get("class_owner", {})
    classes = {str(k) for k, v in owners.items() if str(v) in packages}
    result = {
        "class_mappings": {k: v for k, v in state.get("class_mappings", {}).items() if k in classes},
        "class_owner": {k: v for k, v in owners.items() if k in classes},
        "RELATIVE_PYTHON_MODULE": {k: v for k, v in state.get("RELATIVE_PYTHON_MODULE", {}).items() if k in classes},
        "display_mappings": {k: v for k, v in state.get("display_mappings", {}).items() if k in classes},
        "import_order": [p for p in state.get("import_order", []) if p in packages],
        "package_observations": [o for o in state.get("package_observations", []) if o.get("package_id") in packages],
        "package_resources": {k: v for k, v in state.get("package_resources", {}).items() if k in packages},
        "package_filesystem_mutations": {k: v for k, v in state.get("package_filesystem_mutations", {}).items() if k in packages},
    }
    # Wall time is captured evidence, but is not a registration-parity field.
    # Sandbox paths were normalized in _state and are stable across processes.
    result["package_observations"] = [{k: v for k, v in observation.items() if k != "wall_ms"} for observation in result["package_observations"]]
    observed = result["package_observations"]
    result["imported_module_names"] = sorted({m for o in observed for m in o.get("imported_modules", [])})
    result["import_failures"] = [o for o in observed if not o.get("success", True) or o.get("error")]
    result["routes_hooks_lifecycle"] = [o for o in observed if o.get("lifecycle_observations")]
    for field in ("LOADED_MODULE_DIRS", "EXTENSION_WEB_DIRS"):
        value = state.get(field, {})
        result[field] = {k: v for k, v in value.items() if k in packages or any(str(p) in str(v) for p in packages)}
    filesystem = state.get("filesystem", {})
    # Absolute before/after manifests contain the complete copied sandbox and
    # are not a useful scoped comparison.  Compare only observed mutations.
    result["filesystem"] = {
        key: [p for p in value if any(p == package or p.startswith(package + "/") or f"/{package}/" in p for package in packages)]
        for key, value in filesystem.items()
        if key in {"created", "removed"} and isinstance(value, list)
    }
    return result


def compare_scoped(full: Mapping[str, Any], selective: Mapping[str, Any], packages: Iterable[str]) -> dict[str, Any]:
    package_set = {str(v) for v in packages}
    full_scope = _scoped_state(full.get("state", {}), package_set)
    selective_state = _scoped_state(selective.get("state", {}), package_set)
    fields = sorted(set(full_scope) | set(selective_state))
    entries = {field: {"matches": full_scope.get(field) == selective_state.get(field), "full": _json(full_scope.get(field)), "selective": _json(selective_state.get(field))} for field in fields}
    side_effect_delta = full_scope.get("filesystem") != selective_state.get("filesystem")
    exact = all(entry["matches"] for entry in entries.values())
    full_raw = full.get("state", {})
    out_of_scope = {
        field: _json(value)
        for field, value in full_raw.items()
        if field not in full_scope
    }
    return {"scope": {"packages": sorted(package_set), "full_out_of_scope_preserved": True}, "fields": entries, "exact_scoped_match": exact, "side_effect_delta": side_effect_delta, "full_out_of_scope": out_of_scope, "full_scoped": _json(full_scope), "selective": _json(selective_state)}


def _run_process(command: list[str], output: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    if output.exists():
        try:
            return json.loads(output.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"schema_version": SCHEMA_VERSION, "status": "subprocess_error", "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def run_experiment(artifact: str | os.PathLike[str], root: str | os.PathLike[str] | None = None, workflow: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    comfy_root = Path(root).resolve() if root else DEFAULT_COMFY_ROOT.resolve()
    workflow_path = Path(workflow).resolve() if workflow else (REPO_ROOT / "latest_benchmark_workflow.json").resolve()
    records = load_registry(REPO_ROOT, comfy_root)
    audits = package_audits(records)
    with tempfile.TemporaryDirectory(prefix="ra11f_real_driver_") as temporary:
        temp = Path(temporary)
        full_workflow = temp / "golden.json"
        full_workflow.write_text(json.dumps({"prompt": _workflow_prompt(workflow_path)}), encoding="utf-8")
        full_output = temp / "full.json"
        full_command = [sys.executable, "-m", "ra11f.real_harness", "--arm", "FULL", "--root", str(comfy_root), "--workflow", str(full_workflow), "--output", str(full_output)]
        full = _run_process(full_command, full_output)
        full_state = full.get("state", {})
        package_ids = {str(record["package_id"]) for record in records}
        observed_owner_map = {class_id: package_id for class_id, package_id in _owner_map(full_state).items() if package_id in package_ids}
        explicit_owner_map = metadata_owner_map(records)
        owner_map = dict(explicit_owner_map)
        owner_map.update(observed_owner_map)
        owner_map_path = temp / "owner_map.json"
        owner_map_path.write_text(json.dumps(owner_map, sort_keys=True), encoding="utf-8")
        workflows = [{"name": "golden", "source": str(workflow_path), "prompt": _workflow_prompt(workflow_path), "discovery_only": True}]
        workflows.extend(_make_projection(full_state, label, owner_map) for label in ("projection_a", "projection_b"))
        selective_results: list[dict[str, Any]] = []
        commands = [{"arm": "FULL", "command": full_command, "returncode": 0 if full.get("status") != "subprocess_error" else full.get("returncode")}]
        for item in workflows:
            input_path = temp / f"{item['name']}.json"
            input_path.write_text(json.dumps({"prompt": item["prompt"]}), encoding="utf-8")
            output_path = temp / f"{item['name']}.selective.json"
            command = [sys.executable, "-m", "ra11f.real_harness", "--arm", "SELECTIVE", "--root", str(comfy_root), "--workflow", str(input_path), "--owner-map-file", str(owner_map_path), "--output", str(output_path)]
            selective = _run_process(command, output_path)
            packages = {owner_map[class_id] for class_id in workflow_class_ids(item["prompt"]) if class_id in owner_map}
            comparison = compare_scoped(full, selective, packages) if full.get("state") and selective.get("state") else {"exact_scoped_match": False, "reason": "one arm did not produce state"}
            unsafe = (
                not comparison.get("exact_scoped_match", False)
                or comparison.get("side_effect_delta", False)
                or bool(selective.get("selection", {}).get("fallback"))
                or any(a["package_id"] in packages and any(a["flags"].values()) for a in audits)
            )
            selective_results.append({"workflow": item, "result": selective, "comparison": comparison, "candidate_unsafe": unsafe, "selected_packages": sorted(packages)})
            commands.append({"arm": "SELECTIVE", "workflow": item["name"], "command": command, "returncode": 0 if selective.get("status") != "subprocess_error" else selective.get("returncode")})
        for audit in audits:
            package_id = audit["package_id"]
            related = [entry for entry in selective_results if package_id in entry["selected_packages"]]
            audit["observed_candidate_unsafe"] = any(entry["candidate_unsafe"] for entry in related) if related else False
            audit["safe_to_narrow"] = bool(related) and all(not entry["candidate_unsafe"] for entry in related) and not any(audit["flags"].values())
    result = {
        "schema_version": "ra11f.real.experiment.v1",
        "status": "ok",
        "command_metadata": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(), "fresh_subprocesses": True, "network": "not used", "commands": commands},
        "environment": {"comfy_root": str(comfy_root), "workflow": str(workflow_path), "package_count": len(records), "sandbox_policy": "copy-only disposable temp process"},
        "arms": {"FULL": full, "SELECTIVE": selective_results},
        "owner_observation": owner_map,
        "owner_observation_sources": {class_id: "FULL" if class_id in observed_owner_map else "explicit_registry_metadata" for class_id in owner_map},
        "workflows": [{k: v for k, v in item.items() if k != "prompt"} | {"class_ids": workflow_class_ids(item["prompt"]), "prompt_digest": _digest(item["prompt"])} for item in workflows],
        "package_audits": audits,
        "claims": {"real_package_parity": all(entry["comparison"].get("exact_scoped_match", False) and not entry["candidate_unsafe"] for entry in selective_results), "execution": False, "output": False, "modal": False, "models_or_gpu": False},
        "limitations": ["Discovery only: no model, GPU, workflow execution, output, Modal, or network path was used.", "FULL-only state is retained; comparisons are scoped to owner-selected package closure.", "Import failures are evidence and do not make a package safe.", "No P3/P4 proof levels are assigned by this probe."],
    }
    artifact_path = Path(artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(_json(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the disposable real-package RA11F discovery probe")
    parser.add_argument("--experiment")
    parser.add_argument("--root")
    parser.add_argument("--workflow")
    parser.add_argument("--arm", choices=("FULL", "SELECTIVE"))
    parser.add_argument("--owner-map", default="{}")
    parser.add_argument("--owner-map-file")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    output = Path(args.output) if args.output else None
    if args.experiment:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = run_experiment(args.experiment, args.root, args.workflow)
        print(json.dumps(_json(result), indent=2, sort_keys=True))
        return 0
    if not args.arm:
        parser.error("--arm or --experiment is required")
    records = load_registry(REPO_ROOT, Path(args.root).resolve() if args.root else DEFAULT_COMFY_ROOT.resolve())
    owner_map = json.loads(Path(args.owner_map_file).read_text(encoding="utf-8")) if args.owner_map_file else json.loads(args.owner_map)
    workflow_path = Path(args.workflow).resolve() if args.workflow else (REPO_ROOT / "latest_benchmark_workflow.json").resolve()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = _run_child(args.arm, Path(args.root).resolve() if args.root else DEFAULT_COMFY_ROOT.resolve(), workflow_path, owner_map, records)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(_json(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(_json(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
