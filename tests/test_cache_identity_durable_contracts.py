"""Focused Phase 2 contracts for durable cache/deployment identity seams.

This module intentionally does not import ``comfymodal_runtime.modal_app`` or
``comfyapp``.  The latter constructs the Modal image graph at import time, so
the small helpers needed here are loaded from their source AST with explicit,
import-safe stubs.
"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import Mock, patch

import pytest

from comfymodal_runtime.contracts import DEPLOYMENT_HASH_NAMESPACE, DeploymentIdentity
from comfymodal_runtime.deployment_spec import (
    build_canonical_boundary_identity,
    compute_aggregate_hash,
    validate_persisted_identity_pair,
    validate_canonical_boundary_identity,
)
from tools.v2_control import cli
from tools.v2_control.fingerprints import FingerprintEngine


ROOT = Path(__file__).resolve().parents[1]


def _identity(*, source: str = "source", dependency: str = "dependency"):
    return build_canonical_boundary_identity(
        foundation_inputs={"foundation": "stable"},
        dependency_inputs={"dependency": dependency},
        accelerator_inputs={"accelerator": "stable"},
        source_inputs={"source": source},
        late_config_inputs={"late": "stable"},
    )


def _source_identity() -> DeploymentIdentity:
    file_hashes = {
        "modal_app.py": "a" * 64,
        "custom_node_root_0/node.py": "b" * 64,
    }
    return DeploymentIdentity(
        runtime_hash=compute_aggregate_hash({"modal_app.py": file_hashes["modal_app.py"]}),
        dependency_hash="c" * 64,
        custom_node_hash=compute_aggregate_hash({"custom_node_root_0/node.py": file_hashes["custom_node_root_0/node.py"]}),
        source_bytes=123,
        file_hashes=file_hashes,
        deployment_hash="canonical-deployment-hash",
        hash_namespace=DEPLOYMENT_HASH_NAMESPACE,
    )


def _source_function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _extract_function(
    path: Path, name: str, namespace: dict[str, Any]
) -> tuple[Callable[..., Any], dict[str, Any]]:
    namespace = dict(namespace)
    function = _source_function(path, name)
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return cast(Callable[..., Any], namespace[name]), namespace


def _load_persisted_plan_reader() -> Callable[[], tuple[Any, Any] | None]:
    """Load the exact pure reader without importing the image builder."""
    reader, _ = _extract_function(
        ROOT / "comfyapp.py",
        "_load_persisted_canonical_plan_metadata",
        {
            "json": json,
            "os": os,
            "_CANONICAL_PLAN_METADATA_ENV": "COMFYMODAL_CANONICAL_IMAGE_PLAN",
            "_CANONICAL_PLAN_METADATA_PATH_ENV": "COMFYMODAL_CANONICAL_IMAGE_PLAN_PATH",
        },
    )
    return reader


def _load_persisted_plan_writer(metadata_path: Path) -> Callable[..., Any]:
    """Load the actual host-side typed metadata writer without Modal."""
    writer = _source_function(ROOT / "comfyapp.py", "_persist_canonical_plan_metadata")
    namespace: dict[str, Any] = {
        "Any": Any,
        "json": json,
        "Path": Path,
        "_INSIDE_MODAL_CONTAINER": False,
        "_CANONICAL_PLAN_METADATA_HOST_PATH": str(metadata_path),
        "_CANONICAL_PLAN_METADATA_ENV": "COMFYMODAL_CANONICAL_IMAGE_PLAN",
    }
    module = ast.Module(body=[writer], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(ROOT / "comfyapp.py"), "exec"), namespace)
    return cast(Callable[..., Any], namespace["_persist_canonical_plan_metadata"])


def _load_reference_image() -> tuple[Callable[[], Any], dict[str, Any]]:
    return _extract_function(
        ROOT / "comfymodal_runtime" / "modal_app.py",
        "_reference_image",
        {"Any": Any, "importlib": importlib},
    )


def _load_resource_builder() -> tuple[Callable[..., dict[str, Any]], dict[str, Any]]:
    """Load the actual resource validation path without importing Modal."""
    function = _source_function(
        ROOT / "comfymodal_runtime" / "modal_app.py", "build_modal_resources"
    )
    namespace: dict[str, Any] = {
        "Any": Any,
        "ModalRuntimeSpec": Any,
        "DEPLOYMENT_HASH_NAMESPACE": DEPLOYMENT_HASH_NAMESPACE,
        "importlib": importlib,
        "runtime_shape_config": lambda **_: SimpleNamespace(identity_payload=lambda: {}),
        "validate_canonical_boundary_identity": validate_canonical_boundary_identity,
        "validate_persisted_identity_pair": validate_persisted_identity_pair,
        "_modal": None,
    }
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(ROOT / "comfymodal_runtime" / "modal_app.py"), "exec"), namespace)
    return cast(Callable[..., dict[str, Any]], namespace["build_modal_resources"]), namespace


def test_durable_contract_module_is_import_safe_without_modal_app():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.ImportFrom)
        and node.module == "comfymodal_runtime.modal_app"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Import)
        and any(alias.name == "comfymodal_runtime.modal_app" for alias in node.names)
        for node in ast.walk(tree)
    )


def test_canonical_identity_boundaries_and_missing_inputs_are_strict():
    baseline = _identity()
    changed = _identity(source="source-b", dependency="dependency-b")
    assert changed.source != baseline.source
    assert changed.dependency != baseline.dependency
    assert changed.deployment != baseline.deployment
    assert changed.foundation == baseline.foundation
    assert changed.accelerator == baseline.accelerator
    assert changed.late_config == baseline.late_config

    for field_name in (
        "foundation",
        "dependency",
        "accelerator",
        "source",
        "late_config",
        "deployment",
        "request",
    ):
        with pytest.raises(ValueError, match="canonical identity incomplete"):
            validate_canonical_boundary_identity(replace(baseline, **{field_name: ""}))


def test_reference_image_returns_existing_canonical_plan_without_rebuild_or_mutation():
    image = object()

    @dataclass(frozen=True)
    class Plan:
        final_image: Any
        source: Any

    plan = Plan(final_image=image, source=object())
    builder = Mock(side_effect=AssertionError("canonical plan must not be rebuilt"))
    legacy = SimpleNamespace(CANONICAL_IMAGE_PLAN=plan, build_canonical_image_plan=builder)
    reference, namespace = _load_reference_image()
    importer = Mock(return_value=legacy)
    with patch.object(namespace["importlib"], "import_module", importer):
        assert reference() is image

    importer.assert_called_once_with("comfyapp")
    builder.assert_not_called()
    assert plan.final_image is image
    assert plan.source is not image


def test_reference_image_uses_builder_only_when_canonical_plan_is_absent():
    image = object()
    plan = SimpleNamespace(final_image=image, source=object())
    builder = Mock(return_value=plan)
    legacy = SimpleNamespace(build_canonical_image_plan=builder)
    reference, namespace = _load_reference_image()
    importer = Mock(return_value=legacy)
    with patch.object(namespace["importlib"], "import_module", importer):
        assert reference() is image

    importer.assert_called_once_with("comfyapp")
    builder.assert_called_once_with()


@pytest.mark.parametrize(
    "legacy",
    [
        SimpleNamespace(),
        SimpleNamespace(CANONICAL_IMAGE_PLAN=SimpleNamespace(final_image=None, source=None)),
    ],
)
def test_reference_image_fails_closed_for_absent_or_invalid_plans(legacy: Any):
    reference, namespace = _load_reference_image()
    importer = Mock(return_value=legacy)
    with patch.object(namespace["importlib"], "import_module", importer):
        with pytest.raises(RuntimeError, match="unable to build v2 image"):
            reference()
    importer.assert_called_once_with("comfyapp")


def test_persisted_plan_writer_and_reader_roundtrip_through_actual_serialization(tmp_path):
    source_identity = _source_identity()
    canonical_identity = build_canonical_boundary_identity(
        source_identity=source_identity,
        foundation_inputs={"foundation": "stable"},
        dependency_inputs={"dependency": "stable"},
        accelerator_inputs={"accelerator": "stable"},
        late_config_inputs={"late": "stable"},
    )
    source_identity = source_identity.with_deployment_hash(canonical_identity.deployment)
    metadata_path = tmp_path / ".baked_custom_node_deps" / "canonical_image_plan.json"
    writer = _load_persisted_plan_writer(metadata_path)
    assert writer(source_identity, canonical_identity) is None
    serialized = metadata_path.read_text(encoding="utf-8")

    reader = _load_persisted_plan_reader()
    with patch.dict(
        os.environ,
        {
            "COMFYMODAL_CANONICAL_IMAGE_PLAN": "",
            "COMFYMODAL_CANONICAL_IMAGE_PLAN_PATH": str(metadata_path),
        },
        clear=False,
    ):
        restored = reader()
    assert restored is not None
    restored_source, restored_canonical = restored
    assert serialized == json.dumps(
        {
            "source_identity": source_identity.to_dict(),
            "canonical_identity": canonical_identity.to_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert restored_source.to_dict() == source_identity.to_dict()
    assert restored_canonical.to_dict() == canonical_identity.to_dict()
    assert restored_source.combined_hash == restored_canonical.deployment


def test_persisted_plan_rejects_namespace_and_source_canonical_hash_tampering():
    source_identity = _source_identity()
    canonical_identity = build_canonical_boundary_identity(
        source_identity=source_identity,
        foundation_inputs={"foundation": "stable"},
        dependency_inputs={"dependency": "stable"},
        accelerator_inputs={"accelerator": "stable"},
        late_config_inputs={"late": "stable"},
    )
    source_identity = source_identity.with_deployment_hash(canonical_identity.deployment)
    reader = _load_persisted_plan_reader()

    payload = {
        "source_identity": source_identity.to_dict(),
        "canonical_identity": canonical_identity.to_dict(),
    }
    payload["canonical_identity"]["hash_namespace"] = "wrong/namespace"
    with patch.dict(os.environ, {"COMFYMODAL_CANONICAL_IMAGE_PLAN": json.dumps(payload)}, clear=False):
        with pytest.raises(RuntimeError, match="invalid persisted canonical image-plan metadata"):
            reader()

    payload["canonical_identity"]["hash_namespace"] = DEPLOYMENT_HASH_NAMESPACE
    payload["source_identity"]["deployment_hash"] = ""
    with patch.dict(os.environ, {"COMFYMODAL_CANONICAL_IMAGE_PLAN": json.dumps(payload)}, clear=False):
        with pytest.raises(RuntimeError, match="invalid persisted canonical image-plan metadata"):
            reader()

    mismatched_source = source_identity.with_deployment_hash("different-deployment")
    payload["source_identity"] = mismatched_source.to_dict()
    with patch.dict(os.environ, {"COMFYMODAL_CANONICAL_IMAGE_PLAN": json.dumps(payload)}, clear=False):
        restored = reader()
    assert restored is not None
    restored_source, restored_identity = restored

    builder, namespace = _load_resource_builder()
    plan = SimpleNamespace(source_identity=restored_source, identity=restored_identity)
    with patch.object(
        namespace["importlib"],
        "import_module",
        return_value=SimpleNamespace(CANONICAL_IMAGE_PLAN=plan),
    ):
        with pytest.raises(RuntimeError, match="hash mismatch"):
            builder(spec=SimpleNamespace(cpu=2, memory=4096))


@dataclass
class _Target:
    app: str = "phase2-test-app"
    class_name: str = "ModalRuntimeEntrypointV2"
    method: str = "run_plan_stream"


@dataclass
class _Resources:
    gpu: str = "light-fixture-gpu"
    cpu: int = 2
    memory_mb: int = 4096
    min_containers: int = 0
    scaledown_window: int = 4


@dataclass
class _Workload:
    fresh_required: bool = True
    conditioning_cache: str = "forced_miss"
    expected_output_sha: str = ""
    run_count: int = 1
    gap_seconds: float = 0.0
    nonce: str = "phase2-test"


@dataclass
class _Git:
    head: str = "phase2-test-head"
    branch: str = "tests"
    dirty: bool = False
    dirty_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class _Flag:
    name: str
    value: str
    change_requires: str = "run"


@dataclass
class _Config:
    profile_name: str = "phase2"
    owner: str = "tests"
    target: _Target = field(default_factory=_Target)
    resources: _Resources = field(default_factory=_Resources)
    workload: _Workload = field(default_factory=_Workload)
    flags: list[_Flag] = field(default_factory=lambda: [
        _Flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0", "deploy"),
        _Flag("V2_BENCHMARK_GAP_SECONDS", "0.0", "run"),
        _Flag("COMFYMODAL_V2_PREFILL_LANES", "critical", "deploy"),
        _Flag("COMFYMODAL_V2_NATIVE_FAST_DISK_UNET", "0", "late"),
    ])
    unregistered: list[_Flag] = field(default_factory=list)
    runtime_override_policy: str = "forbid"
    git: _Git = field(default_factory=_Git)


def test_actual_fingerprint_engine_separates_all_deploy_boundaries_from_request():
    base = _Config()
    baseline = FingerprintEngine(base).canonical_identity()

    source = copy.deepcopy(base)
    source.git.dirty_hashes = {"tools/v2_control/cli.py": "source-change"}
    source_identity = FingerprintEngine(source).canonical_identity()
    assert source_identity.source != baseline.source
    assert source_identity.foundation == baseline.foundation
    assert source_identity.dependency == baseline.dependency
    assert source_identity.accelerator == baseline.accelerator
    assert source_identity.late_config == baseline.late_config
    assert FingerprintEngine(source).deploy_fingerprint() != FingerprintEngine(base).deploy_fingerprint()
    assert FingerprintEngine(source).run_fingerprint() != FingerprintEngine(base).run_fingerprint()

    foundation = copy.deepcopy(base)
    foundation.target.class_name = "DifferentEntrypoint"
    foundation_identity = FingerprintEngine(foundation).canonical_identity()
    assert foundation_identity.foundation != baseline.foundation
    assert foundation_identity.source == baseline.source
    assert foundation_identity.dependency == baseline.dependency
    assert foundation_identity.accelerator == baseline.accelerator
    assert foundation_identity.late_config == baseline.late_config
    assert foundation_identity.request != baseline.request

    dependency = copy.deepcopy(base)
    dependency.profile_name = "dependency-change"
    dependency_identity = FingerprintEngine(dependency).canonical_identity()
    assert dependency_identity.dependency != baseline.dependency
    assert dependency_identity.foundation == baseline.foundation
    assert dependency_identity.source == baseline.source
    assert dependency_identity.accelerator == baseline.accelerator
    assert dependency_identity.late_config == baseline.late_config
    assert dependency_identity.request != baseline.request

    accelerator = copy.deepcopy(base)
    accelerator.resources.gpu = "different-gpu"
    accelerator_identity = FingerprintEngine(accelerator).canonical_identity()
    assert accelerator_identity.accelerator != baseline.accelerator
    assert accelerator_identity.foundation == baseline.foundation
    assert accelerator_identity.source == baseline.source
    assert accelerator_identity.dependency == baseline.dependency
    assert accelerator_identity.late_config == baseline.late_config
    assert accelerator_identity.request != baseline.request

    late_config = copy.deepcopy(base)
    late_config.flags[-1].value = "1"
    late_identity = FingerprintEngine(late_config).canonical_identity()
    assert late_identity.late_config != baseline.late_config
    assert late_identity.foundation == baseline.foundation
    assert late_identity.source == baseline.source
    assert late_identity.dependency == baseline.dependency
    assert late_identity.accelerator == baseline.accelerator
    assert late_identity.request != baseline.request

    request_only = copy.deepcopy(base)
    request_only.workload.nonce = "request-change"
    request_identity = FingerprintEngine(request_only).canonical_identity()
    assert request_identity.deployment == baseline.deployment
    assert request_identity.request != baseline.request
    assert request_identity.foundation == baseline.foundation
    assert request_identity.dependency == baseline.dependency
    assert request_identity.accelerator == baseline.accelerator
    assert request_identity.source == baseline.source
    assert request_identity.late_config == baseline.late_config
    assert FingerprintEngine(request_only).deploy_fingerprint() == FingerprintEngine(base).deploy_fingerprint()
    assert FingerprintEngine(request_only).run_fingerprint() != FingerprintEngine(base).run_fingerprint()


def test_committed_git_head_changes_source_and_deployment_only():
    base = _Config()
    baseline = FingerprintEngine(base).canonical_identity()
    committed = copy.deepcopy(base)
    committed.git.head = "different-committed-head"
    changed = FingerprintEngine(committed).canonical_identity()

    assert changed.source != baseline.source
    assert changed.deployment != baseline.deployment
    assert changed.foundation == baseline.foundation
    assert changed.dependency == baseline.dependency
    assert changed.accelerator == baseline.accelerator
    assert changed.late_config == baseline.late_config


@pytest.mark.parametrize("field", [
    "runtime_hash",
    "dependency_hash",
    "custom_node_hash",
    "file_hashes",
    "source_bytes",
])
def test_nonempty_persisted_source_tampering_fails_reader_or_resource(field):
    source_identity = _source_identity()
    canonical_identity = build_canonical_boundary_identity(
        source_identity=source_identity,
        foundation_inputs={"foundation": "stable"},
        dependency_inputs={"dependency": "stable"},
        accelerator_inputs={"accelerator": "stable"},
        late_config_inputs={"late": "stable"},
    )
    source_identity = source_identity.with_deployment_hash(canonical_identity.deployment)
    payload = {
        "source_identity": source_identity.to_dict(),
        "canonical_identity": canonical_identity.to_dict(),
    }
    if field == "file_hashes":
        payload["source_identity"]["file_hashes"]["modal_app.py"] = "d" * 64
    elif field == "source_bytes":
        payload["source_identity"][field] = source_identity.source_bytes + 1
    else:
        payload["source_identity"][field] = "e" * 64

    reader = _load_persisted_plan_reader()
    parser_checked_fields = {"runtime_hash", "custom_node_hash", "file_hashes"}
    with patch.dict(
        os.environ,
        {"COMFYMODAL_CANONICAL_IMAGE_PLAN": json.dumps(payload)},
        clear=False,
    ):
        if field in parser_checked_fields:
            with pytest.raises(RuntimeError, match="invalid persisted canonical image-plan metadata"):
                reader()
            return

        restored = reader()

    assert restored is not None
    restored_source, restored_identity = restored
    builder, namespace = _load_resource_builder()
    plan = SimpleNamespace(source_identity=restored_source, identity=restored_identity)
    with patch.object(
        namespace["importlib"],
        "import_module",
        return_value=SimpleNamespace(CANONICAL_IMAGE_PLAN=plan),
    ):
        with pytest.raises(RuntimeError, match="source manifest hash mismatch"):
            builder(spec=SimpleNamespace(cpu=2, memory=4096))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("deployment_hash", None),
        ("deployment_hash", ""),
        ("deploy_fingerprint", None),
        ("deploy_fingerprint", ""),
        ("deployment_hash_namespace", "wrong/namespace"),
        ("fingerprint_algorithm", "wrong-algorithm"),
        ("schema_version", 1),
    ],
)
def test_schema_two_manifest_rejects_invalid_identity_fields(field, value):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = _Config()
        fingerprints = FingerprintEngine(config)
        path = cli.write_deployment_manifest(root, cast(Any, config), fingerprints, {}, None)
        written = json.loads(path.read_text(encoding="utf-8"))
        if value is None:
            written.pop(field)
        else:
            written[field] = value
        path.write_text(json.dumps(written), encoding="utf-8")
        assert cli.latest_deployment_manifest(root) is None


def test_schema_two_manifest_uses_actual_writer_reader_and_consistent_hashes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = _Config()
        fingerprints = FingerprintEngine(config)
        path = cli.write_deployment_manifest(root, cast(Any, config), fingerprints, {}, None)
        written = json.loads(path.read_text(encoding="utf-8"))
        accepted = cli.latest_deployment_manifest(root)

        assert accepted is not None
        assert accepted["schema_version"] == 2
        assert accepted["deployment_hash_namespace"] == DEPLOYMENT_HASH_NAMESPACE
        assert accepted["deployment_hash"]

        written["deployment_hash"] = "different-deployment"
        path.write_text(json.dumps(written), encoding="utf-8")
        assert cli.latest_deployment_manifest(root) is None


@pytest.mark.parametrize("arguments", [("--help",), ("version",)])
def test_v2ctl_direct_script_bootstraps_without_ambient_pythonpath(arguments: tuple[str, ...]):
    entrypoint = ROOT / "tools" / "v2ctl.py"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory() as cwd:
        completed = subprocess.run(
            [sys.executable, "-S", str(entrypoint), *arguments],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    assert completed.returncode == 0, completed.stderr
    assert "v2ctl" in completed.stdout
