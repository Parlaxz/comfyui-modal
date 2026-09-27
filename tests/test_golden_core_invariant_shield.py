"""SW5 TEST-ONLY regression shield for the Golden core invariants.

This file is intentionally offline.  It uses the self-contained Golden module,
small fake nodes, and the pure custom-node publication policy; it does not
deploy, contact Modal, initialize CUDA, or modify application source.

The existing P1/P2/RA9C suites remain the detailed implementation tests.  The
checks here cover the cross-cutting invariants which are easiest to regress
when those implementations are changed: dispatch, serial await boundaries,
ownership/quiescence, identity separation, request-time capture state,
publication identity, and forbidden teardown behavior.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import inspect
import os
import sys
import threading
import textwrap
from pathlib import Path

import pytest
import torch


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "comfymodal_runtime" / "golden_serial.py"
MODAL_APP_PATH = ROOT / "comfymodal_runtime" / "modal_app.py"
COMFYAPP_PATH = ROOT / "comfyapp.py"
POLICY_PATH = ROOT / "comfymodal_runtime" / "publication_policy.py"
WARMUP_PATH = ROOT / "deploy_warmup.py"
SAMPLING_DEEP_PROFILE_PATH = ROOT / "comfymodal_runtime" / "sampling_deep_profile.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gs = _load(GOLDEN_PATH, "golden_core_invariant_shield_golden")
policy = _load(POLICY_PATH, "golden_core_invariant_shield_policy")
warmup = _load(WARMUP_PATH, "golden_core_invariant_shield_warmup")
deep_profile = _load(
    SAMPLING_DEEP_PROFILE_PATH, "golden_core_invariant_shield_sampling_deep_profile"
)


def _function_node(path: Path, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return next(
        item for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )


def _function_source(path: Path, name: str) -> str:
    node = _function_node(path, name)
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def _called_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_dispatch_routes_heavy_nodes_and_falls_through_to_prepare():
    assert gs.classify_node("CLIPLoader") == "clip_load"
    assert gs.classify_node("CLIPTextEncode") == "clip_forward"
    assert gs.classify_node("UNETLoader") == "unet_load"
    assert gs.classify_node("VAELoader") == "vae_load"
    assert gs.classify_node("VAEDecode") == "vae_decode"
    assert gs.classify_node(gs.CANONICAL_SAMPLER_CLASS) == "sampling"
    assert gs.classify_node("SomeCustomSamplerNode") == "sampling"
    assert gs.classify_node("SaveImage") == "prepare"
    assert gs.classify_node("UnknownCustomNode") == "prepare"


def test_modal_golden_adapter_delegates_once_without_legacy_or_generic_execution():
    """The adapter is arm-agnostic, so both QD arms share this boundary."""
    function = _function_node(MODAL_APP_PATH, "run_golden_serial_stream")
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    assert sum(_called_name(node) == "golden_serial_execute" for node in calls) == 1
    forbidden = {
        "run_plan_stream",
        "run_prompt_stream",
        "ExecutionPlan",
        "PromptExecutor",
        "execute_v2_prompt_executor",
        "legacy_executor",
        "legacy_execute",
    }
    called = {_called_name(node) for node in calls}
    assert not called.intersection(forbidden)
    assert not any("executor" in name.lower() for name in called)


def test_stage_order_is_exact_and_vae_load_precedes_sampling():
    expected = (
        "golden_restore",
        "golden_request_setup",
        "golden_clip_load",
        "golden_clip_forward",
        "golden_unet_load",
        "golden_sampler_prepare",
        "golden_vae_load",
        "golden_sampling",
        "golden_sampler_tail",
        "golden_vae_decode",
        "golden_output",
        "golden_durable_commit",
    )
    assert gs.STAGE_ORDER == expected
    assert gs.STAGE_ORDER.index("golden_vae_load") < gs.STAGE_ORDER.index("golden_sampling")


@pytest.mark.parametrize("stage", ["golden_clip_load", "golden_unet_load", "golden_vae_load"])
def test_heavy_qd_stages_prove_quiescence_before_stage_end(stage):
    source = _function_source(GOLDEN_PATH, stage)
    assert "_require_transport_quiescence" in source
    assert source.index("_require_transport_quiescence") < source.index("rec.end_stage")


def test_telemetry_rejects_overlap_and_duplicate_stage_entries():
    recorder = gs.GoldenTelemetryRecorder()
    recorder.begin_stage("first")
    with pytest.raises(RuntimeError, match="telemetry_stage_overlap:first"):
        recorder.begin_stage("second")
    recorder.end_stage("first", ready=True)
    with pytest.raises(RuntimeError, match="telemetry_duplicate_stage_entry:first"):
        recorder.begin_stage("first")
    assert recorder.intervals["first"].ok is True


def test_runner_resolves_async_node_before_advancing_to_dependent_node():
    events: list[str] = []

    class Source:
        FUNCTION = "run"

        @staticmethod
        def INPUT_TYPES():
            return {"required": {}}

        async def run(self):
            events.append("source-start")
            await asyncio.sleep(0)
            events.append("source-end")
            return ("value",)

    class Sink:
        FUNCTION = "run"

        @staticmethod
        def INPUT_TYPES():
            return {"required": {"value": ("STRING", {})}}

        def run(self, value):
            events.append(f"sink:{value}")
            return (value + "-used",)

    runner = gs.GoldenSerialRunner(
        {
            "source": {"class_type": "Source", "inputs": {}},
            "sink": {"class_type": "Sink", "inputs": {"value": ["source", 0]}},
        },
        node_classes={"Source": Source, "Sink": Sink},
    )

    asyncio.run(runner.run_closure("sink", include_target=True))

    assert events == ["source-start", "source-end", "sink:value"]
    runner.assert_quiescent()


def test_qd_quiescence_requires_join_events_copies_and_no_live_operation():
    valid = {
        "stats": {
            "quiescence": {
                "workers_joined": True,
                "h2d_events_waited": True,
                "copies_complete": True,
                "operation_live": False,
            }
        }
    }
    assert gs._require_transport_quiescence(valid, tag="shield")
    for key in ("workers_joined", "h2d_events_waited", "copies_complete"):
        bad = {"stats": {"quiescence": dict(valid["stats"]["quiescence"])}}
        bad["stats"]["quiescence"][key] = False
        with pytest.raises(RuntimeError, match="shield_qd_not_quiescent"):
            gs._require_transport_quiescence(bad, tag="shield")
    bad = {"stats": {"quiescence": {**valid["stats"]["quiescence"], "operation_live": True}}}
    with pytest.raises(RuntimeError, match="shield_qd_operation_live"):
        gs._require_transport_quiescence(bad, tag="shield")


def test_owner_lifetime_keeps_backing_storage_until_explicit_close():
    staging_source = _function_source(GOLDEN_PATH, "release_staging")
    staging_tree = ast.parse(textwrap.dedent(staging_source))
    assert not any(
        isinstance(node, ast.Call) and _called_name(node) in {"release_storage", "clear"}
        for node in ast.walk(staging_tree)
    )
    assert "_gpu_buf" not in staging_source

    backing = object()
    owner = gs.GoldenQDOwner(backing, [object()], "cpu:0", "unet")
    owner.release_staging()
    assert owner.gpu_buf is backing
    assert owner.closed is False
    owner.close()
    owner.close()
    assert owner.gpu_buf is None
    assert owner.closed is True


def test_unet_assign_binding_is_same_storage_and_retains_owner():
    source = _function_source(GOLDEN_PATH, "golden_unet_load")
    tree = ast.parse(source)
    load_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) == "load_model_weights"
    ]
    assert len(load_calls) == 1
    assert any(
        keyword.arg == "assign"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in load_calls[0].keywords
    )
    assert "validate_unet_binding(model, views" in source
    assert "session.unet_owner = transport[\"owner\"]" in source
    assert "session.register_qd_owner(session.unet_owner)" in source

    class FakeModel:
        def __init__(self, tensor):
            self.weight = tensor
            self.assign_seen = None

        def named_parameters(self):
            return [("weight", self.weight)]

        def named_buffers(self):
            return []

        def load_model_weights(self, values, _prefix, *, assign):
            self.assign_seen = assign
            self.weight = values["weight"]
            return None

    view = getattr(torch, "empty")((2,), dtype=getattr(torch, "bfloat16"))
    model = FakeModel(view.clone())
    model.load_model_weights({"weight": view}, "", assign=True)
    assert model.assign_seen is True
    identity = gs.validate_unet_binding(
        model, {"weight": view}, expected_count=1, device_prefix="cpu"
    )
    assert identity["same_storage_count"] == 1
    owner = gs.GoldenQDOwner(view, [], "cpu:0", "unet")
    assert owner.gpu_buf is view

    model.weight = view.clone()
    with pytest.raises(RuntimeError, match="bind_copied_storage"):
        gs.validate_unet_binding(
            model, {"weight": view}, expected_count=1, device_prefix="cpu"
        )


def test_snapshot_proof_rejects_model_storage_and_open_request_surfaces():
    owner = gs.GoldenQDOwner(object(), [], "cpu:0", "unet")
    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero"):
        gs.golden_snapshot_content_proof(roots=[owner], snapshot_size_bytes=1)

    class Reader:
        def __init__(self):
            self.closed = False

        def read(self):
            return b""

    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero"):
        gs.golden_snapshot_content_proof(roots=[Reader()], snapshot_size_bytes=1)


def test_snapshot_proof_rejects_patcher_worker_and_pending_future_without_leaks():
    class ModelPatcher:
        pass

    class Reader:
        def __init__(self):
            self.closed = False

        def read(self):
            return b""

    loop = asyncio.new_event_loop()
    pending = loop.create_future()

    def assert_rejected(surface):
        with pytest.raises(RuntimeError, match="snapshot_proof_nonzero"):
            gs.golden_snapshot_content_proof(roots=[surface], snapshot_size_bytes=1)

    for surface in (ModelPatcher(), gs.GoldenQDOwner(object(), [], "cpu:0", "unet"), Reader(), pending):
        assert_rejected(surface)

    started = threading.Event()
    release = threading.Event()
    worker = threading.Thread(
        target=lambda: (started.set(), release.wait(2)),
        name="golden-qd-shield-worker",
    )
    worker.start()
    assert started.wait(1)
    try:
        with pytest.raises(RuntimeError, match="snapshot_proof_nonzero"):
            gs.golden_snapshot_content_proof(roots=[{"marker": 1}], snapshot_size_bytes=1)
    finally:
        release.set()
        worker.join(timeout=2)
        pending.cancel()
        loop.close()
    assert not worker.is_alive()


def test_workflow_and_output_sha_policies_are_distinct():
    prompt = {"node": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}}}
    workflow_sha = gs.canonical_workflow_sha256(prompt)
    changed_sha = gs.canonical_workflow_sha256({**prompt, "other": {"class_type": "Noop"}})
    contract = gs.GoldenWorkflowContract()
    assert workflow_sha != changed_sha
    assert workflow_sha != contract.expected_output_png_sha256
    assert contract.workflow_sha256 != contract.expected_output_png_sha256


def test_output_durability_policy_defaults_off_and_rejects_invalid_explicit_value(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_OUTPUT_DURABILITY", raising=False)
    assert gs.resolve_output_durability().mode == "off"
    monkeypatch.setenv("COMFYMODAL_OUTPUT_DURABILITY", "strict")
    assert gs.resolve_output_durability().mode == "strict"
    monkeypatch.setenv("COMFYMODAL_OUTPUT_DURABILITY", "sometimes")
    with pytest.raises(gs.ConfigurationError):
        gs.resolve_output_durability()


def test_durable_path_source_order_is_commit_reopen_verify_then_marker():
    source = _function_source(GOLDEN_PATH, "golden_serial_execute")
    positions = [
        source.index("await golden_durable_commit"),
        source.index("session.recorder.mark_true_durable()"),
        source.index("result = session.build_final_result()"),
        source.index("await golden_teardown(session)"),
    ]
    assert positions == sorted(positions)
    assert "await golden_durable_commit" in source
    assert "session.recorder.mark_true_durable()" in source


def test_durability_separates_expected_sha_policy_from_reopened_integrity(tmp_path):
    data = b"offline-golden-output"
    actual_sha = hashlib.sha256(data).hexdigest()
    configured_sha = "0" * 64
    artifact = gs.ReadyOutputArtifact(
        raw_bytes=data,
        sha256=actual_sha,
        byte_count=len(data),
        filename=f"{actual_sha}.png",
    )
    asset = tmp_path / "output_assets" / artifact.filename
    asset.parent.mkdir()
    asset.write_bytes(data)
    sidecar = asset.with_suffix(".json")
    sidecar.write_text("{}", encoding="utf-8")
    pending = gs.PendingDurability(
        asset_abs_path=str(asset),
        volume_rel_path=f"output_assets/{artifact.filename}",
        sha256=actual_sha,
        byte_count=len(data),
        sidecar_path=str(sidecar),
        volume_mount_root=str(tmp_path),
    )
    assert pending.committed is False

    blocked = gs.GoldenTelemetryRecorder()
    blocked.output_durability_mode = "strict"
    with pytest.raises(RuntimeError, match="successful_commit_stage"):
        blocked.mark_true_durable()

    pending.committed = True
    proof = gs.verify_committed_object(
        pending,
        expected_sha256=configured_sha,
        enforce_expected_sha=False,
    )
    assert proof.sha256 == artifact.sha256 == actual_sha
    assert proof.byte_count == artifact.byte_count == len(data)
    with pytest.raises(RuntimeError, match="durable_expected_output_sha_mismatch"):
        gs.verify_committed_object(
            pending,
            expected_sha256=configured_sha,
            enforce_expected_sha=True,
        )

    recorder = gs.GoldenTelemetryRecorder()
    recorder.output_durability_mode = "strict"
    recorder.begin_stage("golden_durable_commit")
    recorder.end_stage("golden_durable_commit", ready=True)
    with pytest.raises(RuntimeError, match="invalid_proof"):
        recorder.mark_reopen_verified(proof.as_dict())
    recorder.mark_reopen_verified(proof)
    recorder.mark_true_durable()
    assert recorder.true_durable_marked is True

    asset.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    with pytest.raises(RuntimeError, match="durable_sha_mismatch"):
        gs.verify_committed_object(
            pending,
            expected_sha256=configured_sha,
            enforce_expected_sha=False,
        )


def test_golden_teardown_source_contains_no_broad_reclamation():
    tree = ast.parse(GOLDEN_PATH.read_text(encoding="utf-8"), filename=str(GOLDEN_PATH))
    function = next(
        item for item in ast.walk(tree)
        if isinstance(item, ast.AsyncFunctionDef) and item.name == "golden_teardown"
    )
    called_attributes = {
        node.attr for node in ast.walk(function)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
    }
    assert not called_attributes.intersection(
        {
            "empty_cache",
            "collect",
            "purge",
            "unload_all_models",
            "free_memory",
            "cleanup_models",
            "soft_empty_cache",
            "ipc_collect",
            "release_storage",
        }
    )
    assert not any(
        isinstance(node, ast.Call)
        and _dotted_name(node.func) in {"torch.cuda.synchronize", "cuda.synchronize"}
        for node in ast.walk(function)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to"
        for node in ast.walk(function)
    )


def test_diagnostics_are_opt_in_and_do_not_follow_from_default():
    # These selectors are intentionally independent; default execution must
    # not instantiate the optional sampler or stage diagnostics.
    assert gs.GOLDEN_SAMPLING_DIAGNOSTICS_ENV != gs.GOLDEN_STAGE_DIAGNOSTICS_ENV
    assert gs.GOLDEN_SAMPLING_DIAGNOSTICS_ENV != gs.GOLDEN_QD_TRANSPORT_ENV
    assert gs.GOLDEN_STAGE_DIAGNOSTICS_ENV != gs.GOLDEN_QD_TRANSPORT_ENV


def test_sampling_deep_profile_defaults_off_and_only_explicit_levels_opt_in(monkeypatch):
    monkeypatch.delenv(deep_profile.FLAG_ENV, raising=False)
    assert deep_profile.resolve_profile_level() == "off"
    monkeypatch.setenv(deep_profile.FLAG_ENV, "invalid")
    assert deep_profile.resolve_profile_level() == "off"
    for level in ("steps", "blocks"):
        monkeypatch.setenv(deep_profile.FLAG_ENV, level)
        assert deep_profile.resolve_profile_level() == level
    assert deep_profile.FLAG_ENV != gs.GOLDEN_STAGE_DIAGNOSTICS_ENV
    assert deep_profile._DEFAULT_LEVEL == "off"


def test_request_time_capture_guard_excludes_capture_and_exactly_one_follow_up(tmp_path):
    guard = warmup.GoldenCaptureGuard(tmp_path / "guard.json", deployment_identity="deploy-a")
    startup = guard.observe_request(request_id="startup", request_time_capture=False)
    assert startup["classification"] == "ELIGIBLE"
    captured = guard.observe_request(
        request_id="capture", request_time_capture=True, capture_identity="snap-1"
    )
    assert captured["classification"] == "SNAPSHOT_CAPTURE"
    follow_up = guard.observe_request(request_id="after-capture", request_time_capture=False)
    assert follow_up["classification"] == "INVALID_DIRECTLY_AFTER_SNAPSHOT_CAPTURE"
    later = guard.observe_request(request_id="eligible-again", request_time_capture=False)
    assert later["classification"] == "ELIGIBLE"
    recaptured = guard.observe_request(
        request_id="capture-again", request_time_capture=True, capture_identity="snap-2"
    )
    assert recaptured["classification"] == "SNAPSHOT_CAPTURE"
    second_follow_up = guard.observe_request(request_id="after-capture-again", request_time_capture=False)
    assert second_follow_up["classification"] == "INVALID_DIRECTLY_AFTER_SNAPSHOT_CAPTURE"
    assert guard.observe_request(request_id="eligible-twice", request_time_capture=False)["classification"] == "ELIGIBLE"


def test_publication_policy_separates_publishable_nodes_from_control_state():
    assert policy.is_publishable_top_level_node("example-node", is_directory=True)
    assert not policy.is_publishable_top_level_node(".hidden", is_directory=True)
    assert not policy.is_publishable_top_level_node("tests", is_directory=True)
    assert not policy.is_publishable_top_level_node(
        "example-node", is_directory=True, is_symlink=True
    )
    assert policy.is_publishable_top_level_node("example-node", is_directory=False) is False


def test_publication_generation_is_full_content_and_line_ending_stable(tmp_path):
    node = tmp_path / "node-a"
    node.mkdir()
    (node / "nodes.py").write_bytes(b"VALUE = 1\r\n")
    (node / "config.json").write_text('{"enabled":true}', encoding="utf-8")
    (tmp_path / "benchmark_runs").mkdir()
    (tmp_path / "benchmark_runs" / "ignored.json").write_text("ignored", encoding="utf-8")
    narrow_before = tuple(
        (
            path.relative_to(tmp_path).as_posix(),
            hashlib.sha256(
                policy.canonical_publication_bytes(path, path.read_bytes())
            ).hexdigest(),
        )
        for path in policy.iter_source_files(tmp_path)
    )
    first = policy.compute_publication_generation(tmp_path)

    (node / "nodes.py").write_bytes(b"VALUE = 1\n")
    assert policy.compute_publication_generation(tmp_path) == first
    (node / "config.json").write_text('{"enabled":false}', encoding="utf-8")
    narrow_after = tuple(
        (
            path.relative_to(tmp_path).as_posix(),
            hashlib.sha256(
                policy.canonical_publication_bytes(path, path.read_bytes())
            ).hexdigest(),
        )
        for path in policy.iter_source_files(tmp_path)
    )
    assert narrow_after == narrow_before
    assert policy.compute_publication_generation(tmp_path) != first


def test_s4_generation_wrapper_realpaths_only_expected_root_and_rejects_root_symlink(tmp_path):
    function_source = _function_source(COMFYAPP_PATH, "custom_node_source_generation")
    tree = ast.parse(textwrap.dedent(function_source))
    generation_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) == "compute_publication_generation"
    ]
    assert len(generation_calls) == 1
    realpath_call = generation_calls[0].args[0]
    assert isinstance(realpath_call, ast.Call)
    assert _dotted_name(realpath_call.func) == "os.path.realpath"
    assert len(realpath_call.args) == 1
    assert isinstance(realpath_call.args[0], ast.Name)
    assert realpath_call.args[0].id == "source_root"

    node = tmp_path / "node-a"
    node.mkdir()
    (node / "nodes.py").write_text("VALUE = 1\n", encoding="utf-8")
    linked_root = tmp_path / "linked-root"
    try:
        linked_root.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("root symlinks unavailable on this Windows filesystem")
    with pytest.raises(ValueError, match="symlink is not a publishable source root"):
        policy.compute_publication_generation(linked_root)


def test_publication_walker_rejects_nested_symlinks(tmp_path):
    node = tmp_path / "node-a"
    node.mkdir()
    (node / "nodes.py").write_text("VALUE = 1\n", encoding="utf-8")
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    link = node / "linked.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this Windows filesystem")
    with pytest.raises(ValueError, match="symlink"):
        list(policy.iter_publication_files(tmp_path))


def test_source_contracts_keep_serial_executor_and_publication_generation_explicit():
    golden_source = GOLDEN_PATH.read_text(encoding="utf-8")
    publication_source = POLICY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(golden_source, filename=str(GOLDEN_PATH))
    assert not any(
        isinstance(node, ast.Name) and node.id == "PromptExecutor"
        for node in ast.walk(tree)
    )
    assert "compute_publication_generation" in publication_source
    assert "full-content generation" in publication_source
    assert inspect.iscoroutinefunction(gs.golden_serial_execute)
