"""RA11F: a deliberately isolated, synthetic ComfyUI discovery experiment.

The adapter mirrors the narrow observable contract of ComfyUI's external-node
loader: ordered top-level package attempts, package imports, V1 mappings and
display mappings, V3 node/schema registration, and failure continuation. It
does not import installed ComfyUI or custom-node packages. Results therefore
support resolver, fallback, monotonicity, and resource-observation evidence;
they do not claim real package parity or Modal end-to-end performance.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_profile.json"


def _json(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_json(value), sort_keys=True).encode()).hexdigest()


def _profile() -> dict[str, Any]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _golden_source_observation(profile: Mapping[str, Any]) -> dict[str, Any]:
    source = ROOT / str(profile["source_workflow"])
    try:
        prompt = json.loads(source.read_text(encoding="utf-8"))["payload"]["prompt"]
        return {
            "source_exists": True,
            "source_entry_count": len(prompt),
            "source_absent_ids": [node_id for node_id in ("1501",) if node_id not in prompt],
            "source_1262_model": prompt.get("1262", {}).get("inputs", {}).get("model"),
        }
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"source_exists": False, "error": f"{type(exc).__name__}: {exc}"}


def _record(
    package_id: str,
    class_ids: Iterable[str],
    *,
    proof_level: int = 4,
    registration_kind: str = "V1",
    aliases: Iterable[str] = (),
    generated_ids: Iterable[str] = (),
    roles: Iterable[str] = ("execution",),
    prerequisites: Iterable[str] = (),
    imports: Iterable[str] = ("nodes",),
    safe: str = "proven",
    side_effects: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "package_id": package_id,
        "initializer_id": f"{package_id}.initializer",
        "class_ids": list(class_ids),
        "aliases": list(aliases),
        "generated_ids": list(generated_ids),
        "registration_kind": registration_kind,
        "proof_level": proof_level,
        "safe_to_lazy_initialize": safe,
        "roles": list(roles),
        "prerequisites": list(prerequisites),
        "imports": list(imports),
        "display_mappings": {class_id: f"Display {class_id}" for class_id in class_ids},
        "relative_python_module": f"{package_id}.nodes",
        "collision_behavior": "last_registration_wins",
        "v3_nodes": list(class_ids) if registration_kind == "V3" else [],
        "schemas": {class_id: {"name": class_id, "version": 3} for class_id in class_ids}
        if registration_kind == "V3"
        else {},
        "registration_only": "registration_only" in roles,
        "validation_only": "validation_only" in roles,
        "graph_global_providers": [],
        "preprocessing": [],
        "lazy_dynamic": "lazy_dynamic" in roles,
        "sampler_scheduler": {},
        "model_attention_hooks": [],
        "routes": [],
        "web_dirs": [],
        "model_paths": [],
        "mutable_registries": [],
        "package_metadata": {
            "source": "RA11F synthetic fixture",
            "repository": "synthetic://published",
            "revision": "ra11f",
        },
        "side_effects": dict(side_effects or {}),
    }
    result.update(extra)
    return result


def default_records() -> list[dict[str, Any]]:
    """Return generic records for Golden and non-Golden synthetic fixtures."""
    golden_classes = _profile()["class_ids"]
    return [
        _record("golden_fixture", golden_classes, roles=("execution", "validation_only"), imports=("nodes", "output"), side_effects={"routes": ["/synthetic/golden"], "web_dirs": ["web/golden"]}),
        _record("synthetic_v1", ["SyntheticV1"], aliases=["v1-alias"], roles=("execution",), imports=("nodes", "v1_helpers")),
        _record("synthetic_v3", ["SyntheticV3"], registration_kind="V3", roles=("registration_only", "execution"), imports=("nodes", "v3_schema"), side_effects={"routes": ["/synthetic/v3"]}),
        _record("synthetic_global", ["GraphGlobal"], roles=("graph_global", "preprocessing"), imports=("nodes", "global_hooks"), side_effects={"writes": ["synthetic_global/provider.marker"]}, graph_global_providers=["everywhere.provider"], preprocessing=["graph-global-normalize"], routes=["/synthetic/global"], web_dirs=["web/global"], model_paths=["models/synthetic"], mutable_registries=["graph_providers"]),
        _record("synthetic_lazy", ["LazyDynamic"], aliases=["lazy-alias"], generated_ids=["generated:lazy"], roles=("lazy_dynamic", "execution"), imports=("nodes", "lazy_expander"), lazy_dynamic=True, preprocessing=["expand-lazy-branch"]),
        _record("synthetic_sampler", ["SyntheticSampler"], roles=("execution", "sampler_scheduler"), imports=("nodes", "sampler_registry"), sampler_scheduler={"samplers": ["synthetic_euler"], "schedulers": ["synthetic_normal"]}, model_attention_hooks=["synthetic_attention_hook"], mutable_registries=["sampler_registry", "scheduler_registry"]),
        _record("synthetic_collision_early", ["CollisionNode"], roles=("execution",), imports=("nodes",), collision_behavior="first_registration_is_overridden"),
        _record("synthetic_collision_late", ["CollisionNode"], roles=("execution",), imports=("nodes",), collision_behavior="last_registration_wins"),
        _record("synthetic_unsafe", ["UnsafeNode"], proof_level=2, safe="unknown", roles=("execution",), imports=("nodes", "dynamic_import"), side_effects={"unresolved": ["runtime-selected-module"]}),
        _record("synthetic_partial", ["PartialNode"], proof_level=3, safe="proven", imports=("nodes", "fails_after_mutation"), side_effects={"partial_failure": "after_mapping_mutation"}),
    ]


def golden_prompt() -> dict[str, dict[str, Any]]:
    profile = _profile()
    classes = profile["class_ids"]
    prompt: dict[str, dict[str, Any]] = {}
    for number in range(profile["runtime_node_count"] - 2):
        class_type = classes[number] if number < len(classes) else "GoldenFixtureNode"
        prompt[str(number + 1)] = {"class_type": class_type, "inputs": {"source_id": str(number)}}
    prompt["1262"] = {"class_type": "LGNoiseInjectionLatent", "inputs": {"model": ["1499", 0]}}
    # The profile is an intentionally synthetic representation: map the two
    # real fixture-only IDs to the generic fixture class without changing IDs.
    prompt["1262"]["class_type"] = "GoldenFixtureNode"
    prompt["1499"] = {"class_type": "GoldenFixtureNode", "inputs": {}}
    return prompt


def synthetic_prompt() -> dict[str, dict[str, Any]]:
    return {
        "A-1": {"class_type": "SyntheticV1", "inputs": {}},
        "A-2": {"class_type": "v1-alias", "inputs": {}},
        "A-3": {"class_type": "CollisionNode", "inputs": {}},
    }


def semantic_prompt() -> dict[str, dict[str, Any]]:
    return {
        "B-v3": {"class_type": "SyntheticV3", "inputs": {}},
        "B-global": {"class_type": "GraphGlobal", "inputs": {}},
        "B-lazy": {"class_type": "generated:lazy", "inputs": {"branch": "selected"}},
        "B-sampler": {"class_type": "SyntheticSampler", "inputs": {"scheduler": "synthetic_normal"}},
    }


def unsafe_prompt() -> dict[str, dict[str, Any]]:
    return {"unsafe-id": {"class_type": "UnsafeNode", "inputs": {"module": "runtime-selected"}}}


@dataclass
class Resolution:
    workflow_runtime_closure: set[str] = field(default_factory=set)
    process_initialized_set: set[str] = field(default_factory=set)
    missing_from_process: set[str] = field(default_factory=set)
    node_ids: list[str] = field(default_factory=list)
    class_ids: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    generated_ids: list[str] = field(default_factory=list)
    semantic_requirements: dict[str, Any] = field(default_factory=dict)
    safe: bool = True
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "WORKFLOW_RUNTIME_CLOSURE": sorted(self.workflow_runtime_closure),
            "PROCESS_INITIALIZED_SET": sorted(self.process_initialized_set),
            "PROCESS_INITIALIZED_SET_DIFFERENCE": sorted(self.missing_from_process),
            "node_ids": self.node_ids,
            "class_ids": self.class_ids,
            "aliases": self.aliases,
            "generated_ids": self.generated_ids,
            "semantic_requirements": _json(self.semantic_requirements),
            "safe": self.safe,
            "reasons": self.reasons,
        }


class WorkflowClosureResolver:
    def __init__(self, records: Iterable[Mapping[str, Any]]):
        self.records = {str(record["package_id"]): dict(record) for record in records}
        self.class_index: dict[str, list[str]] = {}
        for package_id, record in self.records.items():
            keys = list(record.get("class_ids", [])) + list(record.get("aliases", [])) + list(record.get("generated_ids", []))
            for key in keys:
                self.class_index.setdefault(str(key), []).append(package_id)

    def resolve(self, prompt: Mapping[Any, Mapping[str, Any]], initialized: Iterable[str] = ()) -> Resolution:
        if not isinstance(prompt, Mapping):
            return Resolution(safe=False, reasons=["prompt must be a mapping"])
        process_initialized_set = {str(v) for v in initialized}
        result = Resolution(process_initialized_set=process_initialized_set, missing_from_process=set())
        selected: set[str] = set()
        for raw_id, entry in prompt.items():
            node_id = str(raw_id)
            result.node_ids.append(node_id)
            if not isinstance(entry, Mapping):
                result.safe = False
                result.reasons.append(f"node {node_id} is not an object")
                continue
            class_id = entry.get("class_type", entry.get("class_id"))
            if class_id is None:
                result.safe = False
                result.reasons.append(f"node {node_id} has no class ID")
                continue
            class_id = str(class_id)
            result.class_ids.append(class_id)
            package_ids = self.class_index.get(class_id, [])
            if not package_ids:
                result.safe = False
                result.reasons.append(f"unknown class {class_id}")
                continue
            result.aliases.extend(str(v) for package_id in package_ids for v in self.records[package_id].get("aliases", []))
            result.generated_ids.extend(str(v) for package_id in package_ids for v in self.records[package_id].get("generated_ids", []))
            selected.update(package_ids)

        pending = list(selected)
        while pending:
            package_id = pending.pop()
            if package_id in result.workflow_runtime_closure:
                continue
            record = self.records[package_id]
            result.workflow_runtime_closure.add(package_id)
            for prerequisite in record.get("prerequisites", []):
                if prerequisite not in self.records:
                    result.safe = False
                    result.reasons.append(f"unknown prerequisite {prerequisite} for {package_id}")
                elif prerequisite not in result.workflow_runtime_closure:
                    pending.append(prerequisite)
            if int(record.get("proof_level", 0)) < 3:
                result.safe = False
                result.reasons.append(f"{package_id} lacks P3 closure proof")
            if record.get("safe_to_lazy_initialize") != "proven":
                result.safe = False
                result.reasons.append(f"{package_id} is not proven safe to lazy initialize")
            for field_name in ("registration_only", "validation_only", "lazy_dynamic"):
                if record.get(field_name):
                    result.semantic_requirements.setdefault(field_name, []).append(package_id)
            for field_name in ("graph_global_providers", "preprocessing", "sampler_scheduler", "model_attention_hooks", "routes", "web_dirs", "model_paths", "mutable_registries"):
                value = record.get(field_name)
                if value:
                    result.semantic_requirements.setdefault(field_name, {})[package_id] = value
            result.semantic_requirements.setdefault("initializer_prerequisites", {})[package_id] = list(record.get("prerequisites", []))
            result.semantic_requirements.setdefault("package_metadata", {})[package_id] = record.get("package_metadata", {})
        result.aliases = list(dict.fromkeys(result.aliases))
        result.generated_ids = list(dict.fromkeys(result.generated_ids))
        result.missing_from_process = result.workflow_runtime_closure - result.process_initialized_set
        return result


class ProcessState:
    """Monotonic process registry with serialized, duplicate-safe init."""

    def __init__(self, env: "SyntheticPublishedEnvironment"):
        self.env = env
        self.lock = threading.RLock()
        self.initialized: set[str] = set()
        self.attempted: set[str] = set()
        self.partial_failures: dict[str, str] = {}
        self.mappings: dict[str, str] = {}
        self.display_mappings: dict[str, str] = {}
        self.v3_nodes: list[str] = []
        self.schemas: dict[str, Any] = {}
        self.relative_modules: dict[str, str] = {}
        self.aliases: dict[str, str] = {}
        self.generated_ids: dict[str, str] = {}
        self.registries: dict[str, list[str]] = {}
        self.mutable_registries: list[str] = []
        self.hooks: list[str] = []
        self.global_providers: list[str] = []
        self.preprocessing: list[str] = []
        self.routes: list[str] = []
        self.web_dirs: list[str] = []
        self.model_paths: list[str] = []
        self.import_order: list[str] = []
        self.initializer_wall_ms: dict[str, float] = {}
        self.import_failures: list[dict[str, str]] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.observable_resources: dict[str, list[str]] = {"executors": [], "futures": [], "timers": [], "background": []}
        self.declared_side_effects: dict[str, dict[str, Any]] = {}
        self.initializer_events: list[dict[str, Any]] = []
        self._initializer_sequence = 0
        self._active_initializers = 0
        self.max_concurrent_initializers = 0

    def _begin_initializer(self, package_id: str) -> int:
        self._initializer_sequence += 1
        self._active_initializers += 1
        self.max_concurrent_initializers = max(self.max_concurrent_initializers, self._active_initializers)
        return self._initializer_sequence

    def _end_initializer(self, sequence: int, package_id: str, status: str) -> None:
        self._active_initializers -= 1
        self.initializer_events.append({"sequence": sequence, "package_id": package_id, "status": status})

    def apply_record(self, record: Mapping[str, Any]) -> None:
        package_id = str(record["package_id"])
        side_effects = dict(record.get("side_effects", {}))
        self.declared_side_effects[package_id] = _json(side_effects)
        if record.get("registration_kind", "V1") == "V1":
            for class_id in record.get("class_ids", []):
                previous = self.mappings.get(str(class_id))
                if previous is not None:
                    self.errors.append(f"mapping override {class_id}: {previous} -> {package_id}")
                self.mappings[str(class_id)] = package_id
        for class_id, display in record.get("display_mappings", {}).items():
            self.display_mappings[str(class_id)] = str(display)
        self.v3_nodes.extend(v for v in record.get("v3_nodes", []) if v not in self.v3_nodes)
        self.schemas.update(record.get("schemas", {}))
        self.relative_modules[package_id] = str(record.get("relative_python_module", ""))
        for alias in record.get("aliases", []):
            self.aliases[str(alias)] = package_id
        for generated in record.get("generated_ids", []):
            self.generated_ids[str(generated)] = package_id
        for registry, values in record.get("sampler_scheduler", {}).items():
            self.registries.setdefault(str(registry), [])
            self.registries[str(registry)].extend(v for v in values if v not in self.registries[str(registry)])
        mutable_registries = list(record.get("mutable_registries", [])) + list(side_effects.get("mutable_registries", []))
        self.mutable_registries.extend(v for v in mutable_registries if v not in self.mutable_registries)
        self.hooks.extend(v for v in record.get("model_attention_hooks", []) if v not in self.hooks)
        self.global_providers.extend(v for v in record.get("graph_global_providers", []) if v not in self.global_providers)
        for field_name, destination in (
            ("preprocessing", self.preprocessing),
            ("routes", self.routes),
            ("web_dirs", self.web_dirs),
            ("model_paths", self.model_paths),
        ):
            values = list(record.get(field_name, [])) + list(side_effects.get(field_name, []))
            destination.extend(v for v in values if v not in destination)
        for resource in side_effects.get("background", []):
            self.observable_resources["background"].append(str(resource))

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> dict[str, Any]:
        return {
            "initialized": sorted(self.initialized),
            "attempted": sorted(self.attempted),
            "partial_failures": dict(sorted(self.partial_failures.items())),
            "v1_class_mappings": dict(sorted(self.mappings.items())),
            "display_mappings": dict(sorted(self.display_mappings.items())),
            "v3_node_list": sorted(self.v3_nodes),
            "v3_schemas": _json(self.schemas),
            "RELATIVE_PYTHON_MODULE": dict(sorted(self.relative_modules.items())),
            "aliases": dict(sorted(self.aliases.items())),
            "generated_ids": dict(sorted(self.generated_ids.items())),
            "sampler_scheduler_registries": _json(self.registries),
            "mutable_registries": sorted(self.mutable_registries),
            "model_attention_hooks": sorted(self.hooks),
            "graph_global_providers": sorted(self.global_providers),
            "preprocessing": sorted(self.preprocessing),
            "routes": sorted(self.routes),
            "route_count": len(self.routes),
            "web_dirs": sorted(self.web_dirs),
            "model_paths": sorted(self.model_paths),
            "model_path_count": len(self.model_paths),
            "import_order": self.import_order,
            "package_initializer_wall_ms": dict(sorted(self.initializer_wall_ms.items())),
            "import_failures": self.import_failures,
            "warnings": self.warnings,
            "errors": self.errors,
            "observable_resources": _json(self.observable_resources),
            "declared_side_effects": _json(self.declared_side_effects),
            "initialization_serialization": {
                "serialized": self.max_concurrent_initializers <= 1,
                "lock_scope": "complete_package_initializer",
                "max_concurrent_initializers": self.max_concurrent_initializers,
                "initializer_events": list(self.initializer_events),
            },
        }


class SyntheticPublishedEnvironment:
    def __init__(self, records: Iterable[Mapping[str, Any]]):
        self.records = [dict(record) for record in records]
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ra11f_sandbox_"))
        self.package_root = self.temp_dir / "published"
        self.side_effect_root = self.temp_dir / "package-owned"
        self.package_root.mkdir()
        self.side_effect_root.mkdir()
        self.namespace = f"ra11f_sandbox_{os.getpid()}"
        self.module_names: dict[str, str] = {}
        self._write_packages()

    def _write_packages(self) -> None:
        for index, record in enumerate(self.records):
            module_name = f"{self.namespace}_p{index}"
            package_dir = self.package_root / module_name
            package_dir.mkdir()
            (package_dir / "__init__.py").write_text("# synthetic package entrypoint\n", encoding="utf-8")
            for module in record.get("imports", ["nodes"]):
                filename = package_dir / f"{module}.py"
                if "fails_after_mutation" in module:
                    filename.write_text("raise RuntimeError('synthetic import failure')\n", encoding="utf-8")
                else:
                    filename.write_text(f"MODULE_NAME = {module!r}\n", encoding="utf-8")
            self.module_names[str(record["package_id"])] = module_name

    def __enter__(self) -> "SyntheticPublishedEnvironment":
        sys.path.insert(0, str(self.package_root))
        return self

    def __exit__(self, *_: Any) -> None:
        try:
            sys.path.remove(str(self.package_root))
        except ValueError:
            pass
        for module_name in self.module_names.values():
            for loaded in [name for name in sys.modules if name == module_name or name.startswith(module_name + ".")]:
                sys.modules.pop(loaded, None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def tree_snapshot(self, root: Path | None = None) -> list[str]:
        scan_root = root or self.temp_dir
        return sorted(str(path.relative_to(self.temp_dir)).replace("\\", "/") for path in scan_root.rglob("*") if path.is_file())


class SyntheticDiscoveryAdapter:
    """Faithful narrow adapter for the observable ComfyUI discovery contract."""

    def __init__(self, env: SyntheticPublishedEnvironment, state: ProcessState):
        self.env = env
        self.state = state

    def discover(self, package_ids: Iterable[str] | None = None) -> dict[str, Any]:
        selected = set(package_ids) if package_ids is not None else {str(record["package_id"]) for record in self.env.records}
        # Hold the process lock across admission, imports, side effects, and
        # registration.  Admission-only locking permits two initializers to
        # mutate shared ComfyUI-like globals at the same time.
        with self.state.lock:
            for record in self.env.records:
                package_id = str(record["package_id"])
                if package_id not in selected:
                    continue
                if package_id in self.state.attempted:
                    continue
                self.state.attempted.add(package_id)
                sequence = self.state._begin_initializer(package_id)
                module_name = self.env.module_names[package_id]
                package_start = time.perf_counter()
                self.state.import_order.append(package_id)
                status = "failed"
                record_applied = False
                try:
                    for child in record.get("imports", ["nodes"]):
                        importlib.import_module(f"{module_name}.{child}")
                    side_effects = record.get("side_effects", {})
                    for relative in side_effects.get("writes", []):
                        target = self.env.side_effect_root / str(relative)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(f"created by {package_id}\n", encoding="utf-8")
                    self.state.apply_record(record)
                    record_applied = True
                    if side_effects.get("partial_failure"):
                        raise RuntimeError(str(side_effects["partial_failure"]))
                    self.state.initialized.add(package_id)
                    status = "initialized"
                except Exception as exc:
                    side_effects = record.get("side_effects", {})
                    if side_effects.get("partial_failure") and not record_applied:
                        self.state.apply_record(record)
                    message = f"{package_id}: {type(exc).__name__}: {exc}"
                    self.state.import_failures.append({"package_id": package_id, "error": message})
                    self.state.partial_failures[package_id] = message
                    self.state.errors.append(message)
                finally:
                    self.state.initializer_wall_ms[package_id] = round((time.perf_counter() - package_start) * 1000, 3)
                    self.state._end_initializer(sequence, package_id, status)
        return self.state.snapshot()

    def complete_discovery(self) -> dict[str, Any]:
        return self.discover()


def _rss_bytes() -> int | None:
    try:
        import resource

        getrusage = getattr(resource, "getrusage")
        self_usage = getattr(resource, "RUSAGE_SELF")
        value = int(getrusage(self_usage).ru_maxrss)
        return value * (1024 if sys.platform != "darwin" else 1)
    except Exception:
        return None


def _fd_snapshot() -> list[str]:
    fd_dir = Path("/proc/self/fd")
    if not fd_dir.exists():
        return []
    return sorted(path.name for path in fd_dir.iterdir())


def _resource_snapshot(env: SyntheticPublishedEnvironment, state: ProcessState | None = None) -> dict[str, Any]:
    threads = [
        {"name": thread.name, "ident": thread.ident, "daemon": thread.daemon, "alive": thread.is_alive()}
        for thread in threading.enumerate()
    ]
    state_snapshot = state.snapshot() if state is not None else {}
    return {
        "module_count": len(sys.modules),
        "sandbox_modules": sorted(name for name in sys.modules if name.startswith(env.namespace)),
        "rss_bytes": _rss_bytes(),
        "thread_count": len(threads),
        "threads": threads,
        "non_daemon_threads": [thread for thread in threads if not thread["daemon"]],
        "observable_executors": [],
        "observable_futures": [],
        "observable_timers": [],
        "open_fds": _fd_snapshot(),
        "observable_resources": state_snapshot.get("observable_resources", {"executors": [], "futures": [], "timers": [], "background": []}),
        "declared_side_effects": state_snapshot.get("declared_side_effects", {}),
        "package_owned_files": env.tree_snapshot(env.side_effect_root),
    }


def _initialize(
    resolver: WorkflowClosureResolver,
    adapter: SyntheticDiscoveryAdapter,
    state: ProcessState,
    prompt: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    with state.lock:
        resolution = resolver.resolve(prompt, state.initialized)
        trace = ["resolve"]
        if resolution.safe:
            trace.append("selective_initialization")
            adapter.discover(resolution.missing_from_process)
            mode = "derived"
        else:
            trace.extend(["unsafe_or_unknown", "complete_discovery"])
            adapter.complete_discovery()
            mode = "complete_fallback"
        required_classes = set(resolution.class_ids)
        missing_classes = sorted(class_id for class_id in required_classes if class_id not in state.mappings and class_id not in state.aliases and class_id not in state.generated_ids and class_id not in state.v3_nodes)
        valid = not missing_classes
        if missing_classes:
            state.errors.append(f"required classes absent after discovery: {missing_classes}")
        return {
            "mode": mode,
            "selection_trace": trace,
            "selective_initialization_before_complete": False,
            "resolution": resolution.as_dict(),
            "validation": {"valid": valid, "missing_classes": missing_classes},
            "state": state.snapshot(),
        }


def _arm_result(arm: str) -> dict[str, Any]:
    records = default_records()
    resolver = WorkflowClosureResolver(records)
    result: dict[str, Any] = {
        "schema_version": "ra11f.v1",
        "arm": arm,
        "authority": "synthetic complete discovery adapter",
        "environment": {"kind": "synthetic_published_environment", "network": "not used", "installed_environment": "complete synthetic package set"},
        "claims": {"real_package_parity": False, "modal_e2e": False, "measurements_are_supporting_evidence": True, "synthetic_only": True},
    }
    profile = _profile()
    result["golden_profile"] = {"profile": profile, "source_observation": _golden_source_observation(profile)}
    result["metadata_records"] = records
    with SyntheticPublishedEnvironment(records) as env:
        state = ProcessState(env)
        adapter = SyntheticDiscoveryAdapter(env, state)
        before = _resource_snapshot(env, state)
        files_before = env.tree_snapshot(env.side_effect_root)
        started = time.perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            if arm == "FULL":
                adapter.complete_discovery()
                closure = resolver.resolve(golden_prompt(), state.initialized)
                operation = {"mode": "complete", "closure": closure.as_dict(), "validation": {"valid": True, "missing_classes": []}, "state": state.snapshot()}
            elif arm == "DERIVED":
                operation = _initialize(resolver, adapter, state, golden_prompt())
            elif arm == "FALLBACK":
                operation = _initialize(resolver, adapter, state, unsafe_prompt())
            elif arm == "SEQUENCE":
                operation = _run_sequence(resolver, adapter, state)
            else:
                raise ValueError(f"unknown arm {arm}")
        after = _resource_snapshot(env, state)
        result["closure_ready_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
        result["package_initializer_wall_ms"] = dict(sorted(state.initializer_wall_ms.items()))
        result["operation"] = operation
        result["warnings"] = [str(item.message) for item in caught]
        result["resource_capture"] = {"before": before, "after": after, "rss_delta_bytes": _delta(before.get("rss_bytes"), after.get("rss_bytes")), "module_delta": after["module_count"] - before["module_count"], "thread_delta": after["thread_count"] - before["thread_count"], "fd_delta": len(after["open_fds"]) - len(before["open_fds"])}
        files_after = env.tree_snapshot(env.side_effect_root)
        result["filesystem"] = {"before": files_before, "after": files_after, "package_owned_mutations": sorted(set(files_after) - set(files_before))}
        result["mapping_digest"] = _digest(state.snapshot()["v1_class_mappings"])
        result["output_behavior_evidence"] = _arm_output_behavior_evidence(arm, operation)
        result["measurement_note"] = "Fresh-process wall, module count, RSS, threads and FDs are local supporting measurements only."
    return result


def _delta(before: Any, after: Any) -> int | None:
    return None if before is None or after is None else int(after) - int(before)


def _stable_behavior(value: Any) -> Any:
    """Remove measurements from a synthetic behavior representation."""
    if isinstance(value, Mapping):
        return {
            str(key): _stable_behavior(item)
            for key, item in value.items()
            if not (str(key).endswith("_ms") or str(key) in {"rss_delta_bytes", "module_delta", "thread_delta", "fd_delta"})
        }
    if isinstance(value, (list, tuple)):
        return [_stable_behavior(item) for item in value]
    return _json(value)


def _arm_output_behavior_evidence(arm: str, operation: Mapping[str, Any]) -> dict[str, Any]:
    if arm in {"FULL", "DERIVED"}:
        return {
            "kind": "golden_exact_contract",
            "status": "UNPROVEN_NOT_EXECUTED",
            "reason": "models/GPU/Modal/output path were not run",
            "synthetic_only": True,
            "execution_claim": False,
            "output": {"status": "NOT_GENERATED", "reason": "The Golden output path was not run."},
            "behavior": {"status": "NOT_EXECUTED", "reason": "Only synthetic discovery and closure behavior was exercised."},
        }
    representation = _stable_behavior(operation)
    return {
        "kind": "synthetic_behavioral_representation",
        "status": "SYNTHETIC_ONLY",
        "reason": "Synthetic package discovery behavior only; no real Golden execution occurred.",
        "synthetic_only": True,
        "execution_claim": False,
        "output": {"status": "NOT_GENERATED", "reason": "No synthetic image/output bytes are produced by this harness."},
        "behavior": {"representation": representation, "digest": _digest(representation)},
    }


_PARITY_FIELDS = (
    "v1_class_mappings",
    "display_mappings",
    "v3_node_list",
    "v3_schemas",
    "RELATIVE_PYTHON_MODULE",
    "aliases",
    "generated_ids",
    "sampler_scheduler_registries",
    "mutable_registries",
    "model_attention_hooks",
    "graph_global_providers",
    "preprocessing",
    "routes",
    "web_dirs",
    "model_paths",
    "import_order",
    "import_failures",
    "collision_override_errors",
    "declared_side_effects",
)


def _scoped_state(state: Mapping[str, Any], records: Iterable[Mapping[str, Any]], closure: set[str]) -> dict[str, Any]:
    records_by_id = {str(record["package_id"]): record for record in records}
    scoped_records = [records_by_id[package_id] for package_id in sorted(closure) if package_id in records_by_id]
    class_ids = {str(value) for record in scoped_records for value in record.get("class_ids", [])}
    aliases = {str(value) for record in scoped_records for value in record.get("aliases", [])}
    generated_ids = {str(value) for record in scoped_records for value in record.get("generated_ids", [])}
    v3_nodes = {str(value) for record in scoped_records for value in record.get("v3_nodes", [])}
    scoped_class_ids = {str(value) for record in scoped_records for value in record.get("class_ids", [])}
    registry_values = {
        str(registry): {str(value) for record in scoped_records for value in record.get("sampler_scheduler", {}).get(registry, [])}
        for registry in {str(key) for record in scoped_records for key in record.get("sampler_scheduler", {})}
    }
    list_values = {
        field_name: {str(value) for record in scoped_records for value in list(record.get(field_name, [])) + list(record.get("side_effects", {}).get(field_name, []))}
        for field_name in ("model_attention_hooks", "graph_global_providers", "preprocessing", "routes", "web_dirs", "model_paths", "mutable_registries")
    }
    errors = [str(error) for error in state.get("errors", [])]
    relevant_errors = [
        error
        for error in errors
        if any(package_id in error for package_id in closure)
        or ("override" in error.lower() and any(class_id in error for class_id in scoped_class_ids))
    ]
    scoped = {
        "v1_class_mappings": {key: value for key, value in state.get("v1_class_mappings", {}).items() if key in class_ids},
        "display_mappings": {key: value for key, value in state.get("display_mappings", {}).items() if key in class_ids},
        "v3_node_list": [value for value in state.get("v3_node_list", []) if value in v3_nodes],
        "v3_schemas": {key: value for key, value in state.get("v3_schemas", {}).items() if key in v3_nodes},
        "RELATIVE_PYTHON_MODULE": {key: value for key, value in state.get("RELATIVE_PYTHON_MODULE", {}).items() if key in closure},
        "aliases": {key: value for key, value in state.get("aliases", {}).items() if key in aliases},
        "generated_ids": {key: value for key, value in state.get("generated_ids", {}).items() if key in generated_ids},
        "sampler_scheduler_registries": {
            registry: [value for value in values if str(value) in registry_values.get(registry, set())]
            for registry, values in state.get("sampler_scheduler_registries", {}).items()
            if registry in registry_values
        },
        "import_order": [value for value in state.get("import_order", []) if value in closure],
        "import_failures": [item for item in state.get("import_failures", []) if item.get("package_id") in closure],
        "collision_override_errors": relevant_errors,
        "declared_side_effects": {key: value for key, value in state.get("declared_side_effects", {}).items() if key in closure},
    }
    for field_name, allowed in list_values.items():
        scoped[field_name] = [value for value in state.get(field_name, []) if str(value) in allowed]
    return scoped


def _subtract(full: Any, scoped: Any) -> Any:
    if isinstance(full, Mapping) and isinstance(scoped, Mapping):
        return {key: value for key, value in full.items() if key not in scoped}
    if isinstance(full, list) and isinstance(scoped, list):
        remaining = list(scoped)
        extras = []
        for value in full:
            if value in remaining:
                remaining.remove(value)
            else:
                extras.append(value)
        return extras
    return None


def _parity_entry(full: Any, derived: Any) -> dict[str, Any]:
    return {
        "matches": full == derived,
        "full": _json(full),
        "derived": _json(derived),
        "full_extra": _json(_subtract(full, derived)),
        "derived_extra": _json(_subtract(derived, full)),
    }


def _build_parity(full_state: Mapping[str, Any], derived_state: Mapping[str, Any], records: Iterable[Mapping[str, Any]], closure: set[str]) -> dict[str, Any]:
    full_scoped = _scoped_state(full_state, records, closure)
    derived_scoped = _scoped_state(derived_state, records, closure)
    fields = {field_name: _parity_entry(full_scoped.get(field_name, {}), derived_scoped.get(field_name, {})) for field_name in _PARITY_FIELDS}
    full_raw = dict(full_state)
    derived_raw = dict(derived_state)
    full_raw["collision_override_errors"] = [error for error in full_state.get("errors", []) if "override" in str(error).lower()]
    derived_raw["collision_override_errors"] = [error for error in derived_state.get("errors", []) if "override" in str(error).lower()]
    full_out_of_scope = {field_name: _subtract(full_raw.get(field_name), full_scoped.get(field_name)) for field_name in _PARITY_FIELDS}
    return {
        "scope": {"derived_workflow_runtime_closure": sorted(closure), "comparison": "FULL scoped to derived closure versus DERIVED", "full_out_of_scope_preserved": True},
        "fields": fields,
        "full_out_of_scope": _json(full_out_of_scope),
        "all_relevant_fields_match": all(entry["matches"] for entry in fields.values()),
        "full_scoped_state": _json(full_scoped),
        "derived_scoped_state": _json(derived_scoped),
    }


def _run_sequence(resolver: WorkflowClosureResolver, adapter: SyntheticDiscoveryAdapter, state: ProcessState) -> dict[str, Any]:
    snapshots = []
    mappings_at_start: dict[str, str] = {}
    for label, prompt in (("A", synthetic_prompt()), ("B", semantic_prompt()), ("A", synthetic_prompt()), ("B", semantic_prompt())):
        before = set(state.initialized)
        operation = _initialize(resolver, adapter, state, prompt)
        if not mappings_at_start:
            mappings_at_start = dict(state.mappings)
        snapshots.append({"workflow": label, "operation": operation, "initialized_before": sorted(before), "initialized_after": sorted(state.initialized)})
    monotonic = all(set(snapshots[index]["initialized_after"]).issubset(set(snapshots[index + 1]["initialized_after"])) for index in range(len(snapshots) - 1))
    retained = all(state.mappings.get(key) == value for key, value in mappings_at_start.items())
    return {"sequence": snapshots, "monotonic_initialized_set": monotonic, "mappings_and_hooks_retained": retained, "duplicate_initialization_prevented": len(state.import_order) == len(set(state.import_order)), "no_unload_reload_revision_swap": True, "state": state.snapshot()}


def run_arm(arm: str, output: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = _arm_result(arm.upper())
        result["process_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
        result["status"] = "ok" if result["operation"].get("validation", {}).get("valid", True) or arm.upper() == "SEQUENCE" else "failed_closed"
    except Exception as exc:
        result = {"schema_version": "ra11f.v1", "arm": arm.upper(), "status": "error", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_json(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def run_experiment(artifact: str | os.PathLike[str]) -> dict[str, Any]:
    artifact_path = Path(artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    arms: dict[str, Any] = {}
    commands = []
    for arm in ("FULL", "DERIVED", "FALLBACK", "SEQUENCE"):
        command = [sys.executable, "-m", "ra11f", "--arm", arm]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        commands.append({"arm": arm, "command": command, "returncode": completed.returncode})
        if completed.returncode:
            arms[arm] = {"status": "subprocess_error", "stderr": completed.stderr, "stdout": completed.stdout}
        else:
            try:
                arms[arm] = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                arms[arm] = {"status": "schema_error", "error": str(exc), "stdout": completed.stdout, "stderr": completed.stderr}
    full_state = arms.get("FULL", {}).get("operation", {}).get("state", {})
    derived_operation = arms.get("DERIVED", {}).get("operation", {})
    derived_state = derived_operation.get("state", {})
    closure = set(derived_operation.get("resolution", {}).get("WORKFLOW_RUNTIME_CLOSURE", []))
    raw_parity = _build_parity(full_state, derived_state, arms.get("FULL", {}).get("metadata_records", default_records()), closure)
    mapping_entry = raw_parity["fields"]["v1_class_mappings"]
    full_mapping = mapping_entry["full"]
    derived_mapping = mapping_entry["derived"]
    result = {
        "schema_version": "ra11f.experiment.v1",
        "command_metadata": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(), "cwd": str(ROOT), "fresh_subprocesses": True, "commands": commands},
        "arms": arms,
        "parity": {
            "full_vs_derived_relevant_v1_mapping_match": {key: full_mapping.get(key) == derived_mapping.get(key) for key in sorted(set(full_mapping) | set(derived_mapping))},
            "full_vs_derived_relevant_v1_mapping_parity": mapping_entry["matches"],
            "derived_authorized_only_proven_records": derived_operation.get("resolution", {}).get("safe") is True,
            "raw_registration_global_parity": raw_parity,
        },
        "limitations": ["Synthetic adapter only; no installed package imports.", "No network, installers, GPU, Modal, or production source paths used.", "Golden exact-contract status remains UNPROVEN_NOT_EXECUTED because models/GPU/Modal/output path were not run."],
        "artifact_kind": "raw_ra11f_arm_results",
    }
    artifact_path.write_text(json.dumps(_json(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the isolated RA11F closure experiment")
    parser.add_argument("--arm", choices=("FULL", "DERIVED", "FALLBACK", "SEQUENCE"))
    parser.add_argument("--output")
    parser.add_argument("--experiment")
    args = parser.parse_args(argv)
    if args.experiment:
        print(json.dumps(run_experiment(args.experiment), indent=2, sort_keys=True))
        return 0
    if not args.arm:
        parser.error("--arm or --experiment is required")
    print(json.dumps(run_arm(args.arm, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
