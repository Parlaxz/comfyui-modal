"""Offline P2 contract tests for the self-contained Golden serial module.

The module is loaded by path on purpose.  These tests exercise the narrow
runtime seams with synthetic sessions and nodes; they do not import ComfyUI,
Modal, or require a CUDA device.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest
import torch


MODULE_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_serial.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("golden_serial_p2_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gs = _load_module()


def _request(prompt=None, *, extra_data=None):
    return gs.GoldenRequest(
        request_id="p2-request",
        prompt=prompt or {},
        extra_data=extra_data or {},
    )


def _minimal_session(recorder=None, **kwargs):
    session = object.__new__(gs.GoldenSession)
    session.recorder = recorder or gs.GoldenTelemetryRecorder()
    session.request = _request()
    session.contract = gs.GoldenWorkflowContract()
    session.snapshot_proof = kwargs.get("snapshot_proof")
    session.telemetry_path = kwargs.get("telemetry_path")
    session.volume = kwargs.get("volume")
    session.volume_mount_root = kwargs.get("volume_mount_root")
    session.clip_owner = None
    session.unet_owner = None
    session.vae_owner = None
    session.clip_owners = []
    return session


def test_external_restore_is_observed_verbatim_and_never_timed_as_local_work(monkeypatch, tmp_path):
    metadata = {
        "restore_method_end_mono_ns": 1234,
        "remote_python_resume_wall_unix_ns": 5678,
        "adapter_marker": {"source": "real-restore"},
    }
    handle = gs.GoldenVolumeHandle(object(), str(tmp_path))
    session = gs.GoldenSession(
        _request(),
        volume=handle,
        restore_metadata=metadata,
    )
    # Only the CUDA capability observation is faked; no CUDA work is performed.
    monkeypatch.setattr(gs.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(gs.torch.cuda, "current_device", lambda: 0)
    monkeypatch.setattr(gs.torch.cuda, "get_device_name", lambda _device: "synthetic-gpu")
    monkeypatch.setattr(gs.torch.cuda, "memory_allocated", lambda: 0)

    baseline = asyncio.run(gs.golden_restore(session))
    document = session.recorder.to_json_dict()
    observed = document["external_restore"]
    assert observed["restore_method_end_mono_ns"] == metadata["restore_method_end_mono_ns"]
    assert observed["adapter_marker"] == metadata["adapter_marker"]
    assert observed["remote_python_resume_wall_ns"] == 5678  # normalized alias
    assert baseline["observation_only"] is True
    assert baseline["external_restore_interval"] == observed
    assert document["events"][0]["name"] == gs.EVENT_REAL_RESTORE
    # An observation timestamp is not a fabricated restore duration.
    assert "actual_restore_duration_ms" not in observed
    interval = document["stages"][0]
    assert interval["details"]["observation_only"] is True

    result = gs.GoldenFinalResult(
        request_id="p2-request",
        image_sha256="a" * 64,
        asset_path="asset.png",
        volume_rel_path="output_assets/asset.png",
        true_durable=True,
        seriality_violation_count=0,
        executed_nodes=[],
        restore_observation=observed,
    )
    assert result.restore_metadata == observed
    assert result.real_restore_interval == observed


def test_top_level_order_and_return_are_distinct_from_assembled_event(monkeypatch, tmp_path):
    calls = []
    captured = {}
    payload = b"synthetic committed asset"
    asset_path = tmp_path / "asset.png"
    asset_path.write_bytes(payload)
    expected_digest = hashlib.sha256(payload).hexdigest()
    contract = gs.GoldenWorkflowContract(expected_output_png_sha256=expected_digest)

    async def fake_stage(session, name):
        calls.append(name)
        captured.setdefault("session", session)
        session.recorder.begin_stage(name)
        session.recorder.end_stage(name, ready=True)
        return None

    for name in gs.STAGE_ORDER[:-1]:
        monkeypatch.setattr(gs, name, lambda session, _name=name: fake_stage(session, _name))

    async def fake_output(session):
        calls.append("golden_output")
        captured["session"] = session
        session.recorder.begin_stage("golden_output")
        session.pending_durability = gs.PendingDurability(
            asset_abs_path=str(asset_path),
            volume_rel_path="asset.png",
            sha256=expected_digest,
            byte_count=len(payload),
            sidecar_path=str(tmp_path / "asset.json"),
            volume_mount_root=str(tmp_path),
        )
        session.recorder.end_stage("golden_output", ready=True)

    monkeypatch.setattr(gs, "golden_output", fake_output)

    async def fake_commit(volume, pending, recorder, **_kwargs):
        calls.append("golden_durable_commit")
        recorder.begin_stage("golden_durable_commit")
        pending.committed = True
        proof = gs.verify_committed_object(pending, expected_sha256=expected_digest)
        recorder.mark_reopen_verified(proof)
        recorder.end_stage("golden_durable_commit", ready=True)

    monkeypatch.setattr(gs, "golden_durable_commit", fake_commit)

    async def fake_teardown(session):
        calls.append("golden_teardown")
        recorder = session.recorder
        recorder.begin_stage("golden_teardown")
        recorder.end_stage("golden_teardown", ready=True)

    monkeypatch.setattr(gs, "golden_teardown", fake_teardown)
    result = asyncio.run(
        gs.golden_serial_execute(
            _request(),
            volume=object(),
            volume_mount_root=str(tmp_path),
            contract=contract,
        )
    )

    recorder = captured["session"].recorder
    names = [event["name"] for event in recorder.events]
    assert calls == list(gs.STAGE_ORDER) + ["golden_teardown"]
    assert result.true_durable is True
    assert "RESULT_ASSEMBLED" in names
    assert "RESULT_EMIT" not in names
    assert names.index("RESULT_ASSEMBLED") < names.index("TEARDOWN_COMPLETE")
    teardown_end = recorder.intervals["golden_teardown"].end_monotonic_ns
    complete_event = next(e for e in recorder.events if e["name"] == "TEARDOWN_COMPLETE")
    assert teardown_end <= complete_event["monotonic_ns"]


def test_sampler_prepare_wall_interval_contains_trailing_work_and_reports_fake_delta(monkeypatch):
    class Clock:
        value = 0

        def tick(self):
            self.value += 1
            return self.value

    clock = Clock()
    recorder = gs.GoldenTelemetryRecorder(monotonic=clock.tick, wall=clock.tick)
    session = _minimal_session(recorder)
    session.clip = object()
    session.conditioning = object()
    session.patcher = object()
    session.node_map = types.SimpleNamespace(
        clip_loader_id="clip", clip_encode_id="encode", unet_loader_id="unet", sampler_id="sampler"
    )
    session.recorder.begin_stage("golden_unet_load")
    session.recorder.end_stage("golden_unet_load", ready=True)

    work_finished = []

    class Runner:
        def __init__(self):
            self.executed = []
            self.ui_outputs = {}
            self._golden_futures = set()

        def seed(self, *_args):
            pass

        def begin_scope(self, _allowed):
            pass

        def end_scope(self):
            pass

        async def run_closure(self, *_args, **_kwargs):
            clock.value += 100  # meaningful sampler-preparation work
            work_finished.append(clock.value)
            self.executed.append({"node_id": "prep", "class_type": "Prep", "stage_class": "prepare"})

        def assert_quiescent(self):
            pass

    session.runner = Runner()
    allocations = iter((10, 42))
    monkeypatch.setattr(gs.torch.cuda, "memory_allocated", lambda: next(allocations))

    details = asyncio.run(gs.golden_sampler_prepare(session))
    interval = recorder.intervals["golden_sampler_prepare"]
    assert interval.entry_monotonic_ns < work_finished[0] < interval.end_monotonic_ns
    assert details["cuda_alloc_delta_bytes_bounded_check"] == 32
    assert recorder.reconcile_seriality()["ok"] is True


def test_teardown_ends_before_persistence_and_does_not_call_snapshot_proof(tmp_path):
    class Clock:
        value = 0

        def tick(self):
            self.value += 1
            return self.value

    clock = Clock()
    recorder = gs.GoldenTelemetryRecorder(monotonic=clock.tick, wall=clock.tick)
    persist_calls = []

    def persist(path):
        persist_calls.append((str(path), clock.value))
        clock.value += 10  # represents write + flush + fsync
        return str(path)

    recorder.persist = persist
    proof_calls = []
    session = _minimal_session(
        recorder,
        telemetry_path=str(tmp_path / "telemetry.json"),
        snapshot_proof=lambda: proof_calls.append(True),
    )
    asyncio.run(gs.golden_teardown(session))
    end = recorder.intervals["golden_teardown"].end_monotonic_ns
    assert persist_calls == []
    assert end is not None
    assert proof_calls == []


def test_volume_mount_binding_and_reopen_hash_are_fail_closed(tmp_path):
    with pytest.raises(RuntimeError, match="volume_mount_root_required"):
        gs.GoldenVolumeHandle(object())

    volume = object()
    handle = gs.GoldenVolumeHandle(volume, tmp_path, label="synthetic")
    assert handle.handle is volume
    assert handle.mount_root == str(tmp_path)
    assert handle.mounted_filesystem_root == str(tmp_path)

    root = tmp_path / "mounted"
    root.mkdir()
    inside = root / "asset.bin"
    payload = b"committed synthetic asset"
    inside.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    pending = gs.PendingDurability(
        asset_abs_path=str(inside),
        volume_rel_path="asset.bin",
        sha256=digest,
        byte_count=len(payload),
        sidecar_path=str(root / "asset.json"),
        committed=True,
        volume_mount_root=str(root),
    )
    proof = gs.verify_committed_object(pending, expected_sha256=digest)
    assert proof["byte_count"] == len(payload)
    assert proof["sha256"] == digest
    assert Path(proof["asset_path"]).read_bytes() == payload

    mismatched = gs.PendingDurability(
        asset_abs_path=str(inside),
        volume_rel_path="other.bin",
        sha256=digest,
        byte_count=len(payload),
        sidecar_path=str(root / "asset.json"),
        committed=True,
        volume_mount_root=str(root),
    )
    with pytest.raises(RuntimeError, match="durable_asset_path_mismatch"):
        gs.verify_committed_object(mismatched, expected_sha256=digest)

    outside = tmp_path / "outside.bin"
    for path, mount, marker in (
        (inside, None, "volume_mount_root_required"),
        (outside, str(root / "missing"), "volume_mount_root_missing"),
        (outside, str(root), "asset_outside_volume_mount"),
    ):
        with pytest.raises(RuntimeError, match=marker):
            gs._require_path_in_volume(str(path), mount)

    session = gs.GoldenSession(_request(), volume=handle)
    assert session.volume is volume
    assert session.volume_mount_root == str(tmp_path)


def test_snapshot_proof_is_passive_fails_closed_and_counts_dynamic_patcher():
    root = types.SimpleNamespace(unchanged="yes")
    proof = gs.golden_snapshot_content_proof(roots=[root], snapshot_size_bytes=1)
    assert proof["passive"] is True
    assert proof["tensor_count"] == 0
    assert proof["snapshot_size_bytes"] == 1
    assert proof["snapshot_size_limit_bytes"] == 5 * 1024**3
    assert root.unchanged == "yes"

    with pytest.raises(RuntimeError, match="no_surfaces_supplied"):
        gs.golden_snapshot_content_proof()
    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero"):
        gs.golden_snapshot_content_proof(roots=[getattr(torch, "zeros")(2)], snapshot_size_bytes=1)

    ModelPatcherDynamic = type("ModelPatcherDynamic", (), {})
    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero") as error:
        gs.golden_snapshot_content_proof(roots=[ModelPatcherDynamic()], snapshot_size_bytes=1)
    assert "model_patcher_count" in str(error.value)


def test_native_detection_conversion_errors_propagate_and_absent_quant_is_valid():
    def prefix(state):
        assert state == {"model.weight": 1}
        return "model."

    def strip(state, replacements, *, filter_keys):
        assert replacements == {"model.": ""}
        assert filter_keys is True
        return {"weight": state["model.weight"]}

    def exploding_quant(*_args, **_kwargs):
        raise ValueError("unexpected quant conversion failure")

    with pytest.raises(ValueError, match="unexpected quant conversion failure"):
        gs._native_detection_input({"model.weight": 1}, {"m": 1}, prefix, strip, exploding_quant)

    detected, metadata, used_prefix = gs._native_detection_input(
        {"model.weight": 1}, {"m": 1}, prefix, strip, None
    )
    assert detected == {"weight": 1}
    assert metadata == {"m": 1}
    assert used_prefix == "model."


def test_quiescence_requires_joined_workers_waited_events_and_no_live_operation():
    transport = {
        "stats": {
            "quiescence": {
                "workers_joined": True,
                "h2d_events_waited": True,
                "copies_complete": True,
                "operation_live": False,
            }
        }
    }
    assert gs._require_transport_quiescence(transport, tag="synthetic") ["workers_joined"] is True

    for key in ("workers_joined", "h2d_events_waited", "copies_complete"):
        bad = {"stats": {"quiescence": dict(transport["stats"]["quiescence"])}}
        bad["stats"]["quiescence"][key] = False
        with pytest.raises(RuntimeError, match="qd_not_quiescent"):
            gs._require_transport_quiescence(bad, tag="synthetic")
    bad = {"stats": {"quiescence": {**transport["stats"]["quiescence"], "operation_live": True}}}
    with pytest.raises(RuntimeError, match="qd_operation_live"):
        gs._require_transport_quiescence(bad, tag="synthetic")


class _Recorder:
    def __init__(self):
        self.events = []


def _prompt(edges):
    return {
        node_id: {"class_type": node_id, "inputs": dict(inputs)}
        for node_id, inputs in edges.items()
    }


def test_runner_preserves_seeded_objects_and_dependency_order():
    recorder = _Recorder()

    class Dep:
        FUNCTION = "go"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}}

        def go(self):
            recorder.events.append("dep")
            return ("dependency",)

    class Consumer:
        FUNCTION = "go"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"dep": "OUT", "seed": "OUT"}}

        def go(self, dep, seed):
            recorder.events.append("consumer")
            assert dep == "dependency"
            assert seed is seeded_value
            return (seed,)

    class Seeded:
        FUNCTION = "go"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}}

        def go(self):
            raise AssertionError("seeded node must not execute")

    seeded_value = object()
    prompt = _prompt({
        "Dep": {},
        "Seeded": {},
        "Consumer": {"dep": ["Dep", 0], "seed": ["Seeded", 0]},
    })
    runner = gs.GoldenSerialRunner(prompt, node_classes={"Dep": Dep, "Seeded": Seeded, "Consumer": Consumer})
    runner.seed("Seeded", [[seeded_value]])
    asyncio.run(runner.run_closure("Consumer", include_target=True))
    assert recorder.events == ["dep", "consumer"]
    assert runner.cache["Consumer"].outputs == [[seeded_value]]


def test_runner_handles_list_hidden_and_lazy_inputs_without_background_tasks():
    recorder = _Recorder()

    class Source:
        FUNCTION = "go"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}}

        def go(self):
            recorder.events.append("source")
            return ("lazy-source",)

    class LazyListHidden:
        FUNCTION = "go"
        INPUT_IS_LIST = True
        OUTPUT_IS_LIST = (True,)

        @classmethod
        def INPUT_TYPES(cls):
            return {
                "required": {"values": ["OUT", {"lazy": True}]},
                "hidden": {"unique_id": "UNIQUE_ID"},
            }

        def check_lazy_status(self, values=None, unique_id=None):
            return ["values"] if values is None else []

        def go(self, values, unique_id):
            recorder.events.append(("consumer", tuple(values), unique_id))
            return ([*values, unique_id],)

    prompt = _prompt({
        "Source": {},
        "LazyListHidden": {"values": ["Source", 0]},
    })
    runner = gs.GoldenSerialRunner(prompt, node_classes={"Source": Source, "LazyListHidden": LazyListHidden})
    asyncio.run(runner.run_closure("LazyListHidden", include_target=True))
    assert recorder.events == ["source", ("consumer", ("lazy-source",), ["LazyListHidden"])]
    assert runner.cache["LazyListHidden"].outputs == [["lazy-source", ["LazyListHidden"]]]
    runner.assert_quiescent()


def test_v3_node_output_marker_normalizes_result_ui_and_rejects_block_or_expand(monkeypatch):
    internal = types.ModuleType("comfy_api.internal")

    class NodeOutputMarker:
        def __init__(self, result, ui=None, *, block_execution=None, expand=None):
            self.result = result
            self.ui = ui
            self.block_execution = block_execution
            self.expand = expand

    setattr(internal, "_NodeOutputInternal", NodeOutputMarker)
    comfy_api = types.ModuleType("comfy_api")
    setattr(comfy_api, "internal", internal)
    monkeypatch.setitem(sys.modules, "comfy_api", comfy_api)
    monkeypatch.setitem(sys.modules, "comfy_api.internal", internal)

    class Node:
        OUTPUT_IS_LIST = (False,)

    runner = gs.GoldenSerialRunner({}, node_classes={})
    outputs, ui, expanded = runner._outputs_from_returns(
        [NodeOutputMarker(("value",), {"images": ["synthetic.png"]})], Node
    )
    assert outputs == [["value"]]
    assert ui == {"images": ["synthetic.png"]}
    assert expanded is False

    with pytest.raises(RuntimeError, match="block_execution_unsupported"):
        runner._outputs_from_returns([NodeOutputMarker(("value",), block_execution=object())], Node)
    with pytest.raises(RuntimeError, match="expand_unsupported"):
        runner._outputs_from_returns([NodeOutputMarker(("value",), expand={"x": {}})], Node)


def test_canonical_node_resolution_remains_exact_and_fail_closed():
    prompt = {
        "88": {"class_type": "CLIPLoader", "inputs": {"clip_name": gs.CANONICAL_CLIP_NAME, "type": gs.CANONICAL_CLIP_TYPE}},
        "67": {"class_type": "CLIPTextEncode", "inputs": {}},
        "214": {"class_type": "UNETLoader", "inputs": {"unet_name": gs.CANONICAL_UNET_NAME}},
        "1242": {"class_type": "VAELoader", "inputs": {"vae_name": gs.CANONICAL_VAE_NAME}},
        "175": {"class_type": gs.CANONICAL_SAMPLER_CLASS, "inputs": {}},
        "1178": {"class_type": "VAEDecode", "inputs": {}},
    }
    node_map = gs.resolve_golden_node_map(prompt)
    assert node_map == gs.GoldenNodeMap("88", "67", "214", "1242", "175", "1178")
    broken = dict(prompt)
    del broken["175"]
    with pytest.raises(RuntimeError, match="canonical_nodes_missing:sampler"):
        gs.resolve_golden_node_map(broken)


def test_restore_metadata_is_authoritative_over_request_extra_data(monkeypatch, tmp_path):
    authoritative = {
        "restore_method_end_mono_ns": 1234,
        "remote_python_resume_wall_unix_ns": 5678,
        "adapter_marker": {"source": "adapter"},
    }
    request = _request(
        extra_data={
            "restore_timing": {
                "restore_method_end_mono_ns": 999999,
                "adapter_marker": {"source": "request"},
                "actual_restore_duration_ms": 999.0,
            },
            "restore_method_end_mono_ns": 999999,
            "actual_restore_duration_ms": 999.0,
        }
    )
    session = gs.GoldenSession(
        request,
        volume=gs.GoldenVolumeHandle(object(), str(tmp_path)),
        restore_metadata=authoritative,
    )
    monkeypatch.setattr(gs.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(gs.torch.cuda, "current_device", lambda: 0)
    monkeypatch.setattr(gs.torch.cuda, "get_device_name", lambda _device: "synthetic-gpu")
    monkeypatch.setattr(gs.torch.cuda, "memory_allocated", lambda: 0)

    baseline = asyncio.run(gs.golden_restore(session))
    observed = session.recorder.to_json_dict()["external_restore"]
    assert observed["restore_method_end_mono_ns"] == 1234
    assert observed["adapter_marker"] == {"source": "adapter"}
    assert observed["remote_python_resume_wall_ns"] == 5678
    assert "actual_restore_duration_ms" not in observed
    assert baseline["external_restore_interval"] == observed
    # The local observation interval is telemetry only; it is not presented as
    # an external restore duration or as a fabricated request-time measurement.
    details = session.recorder.intervals["golden_restore"].details
    assert details["observation_only"] is True
    assert details["external_restore_interval"] == observed
    assert "duration_ms" not in details


def test_teardown_has_no_snapshot_proof_and_does_not_persist(tmp_path):
    recorder = gs.GoldenTelemetryRecorder()
    persist_calls = []
    proof_calls = []
    session = _minimal_session(
        recorder,
        telemetry_path=str(tmp_path / "telemetry.json"),
        snapshot_proof=lambda: proof_calls.append(True),
    )

    def persist(path):
        interval = recorder.intervals.get("golden_teardown")
        persist_calls.append(None if interval is None else interval.end_monotonic_ns)
        if interval is not None and interval.end_monotonic_ns is not None:
            raise RuntimeError("post_end_persistence_failure")
        return str(path)

    recorder.persist = persist
    asyncio.run(gs.golden_teardown(session))
    assert persist_calls == []
    assert proof_calls == []

    assert recorder.intervals["golden_teardown"].end_monotonic_ns is not None


def test_top_level_persists_once_after_teardown_complete_and_reports_persist_wall(monkeypatch, tmp_path):
    calls = []
    payload = b"synthetic committed asset"
    asset_path = tmp_path / "asset.png"
    asset_path.write_bytes(payload)
    expected_digest = hashlib.sha256(payload).hexdigest()
    contract = gs.GoldenWorkflowContract(expected_output_png_sha256=expected_digest)

    async def fake_stage(session, name):
        session.recorder.begin_stage(name)
        session.recorder.end_stage(name, ready=True)

    for name in gs.STAGE_ORDER[:-1]:
        monkeypatch.setattr(gs, name, lambda session, _name=name: fake_stage(session, _name))

    async def fake_output(session):
        session.recorder.begin_stage("golden_output")
        session.pending_durability = gs.PendingDurability(
            asset_abs_path=str(asset_path), volume_rel_path="asset.png",
            sha256=expected_digest, byte_count=len(payload),
            sidecar_path=str(tmp_path / "asset.json"), volume_mount_root=str(tmp_path),
        )
        session.recorder.end_stage("golden_output", ready=True)

    monkeypatch.setattr(gs, "golden_output", fake_output)

    async def fake_commit(volume, pending, recorder, **_kwargs):
        recorder.begin_stage("golden_durable_commit")
        pending.committed = True
        proof = gs.verify_committed_object(pending, expected_sha256=expected_digest)
        recorder.mark_reopen_verified(proof)
        recorder.end_stage("golden_durable_commit", ready=True)

    monkeypatch.setattr(gs, "golden_durable_commit", fake_commit)

    captured = {}

    async def fake_teardown(session):
        captured["session"] = session
        session.recorder.begin_stage("golden_teardown")
        session.recorder.end_stage("golden_teardown", ready=True)

    monkeypatch.setattr(gs, "golden_teardown", fake_teardown)
    persist_impl = gs.GoldenTelemetryRecorder.persist

    def persist_once(recorder, path):
        calls.append({
            "path": str(path),
            "teardown_end": recorder.intervals["golden_teardown"].end_monotonic_ns,
            "events": [event["name"] for event in recorder.events],
        })
        return persist_impl(recorder, path)

    monkeypatch.setattr(gs.GoldenTelemetryRecorder, "persist", persist_once)
    target = tmp_path / "telemetry.json"
    result = asyncio.run(gs.golden_serial_execute(
        _request(), volume=object(), volume_mount_root=str(tmp_path),
        telemetry_path=str(target), contract=contract,
    ))

    assert len(calls) == 1
    assert calls[0]["teardown_end"] is not None
    assert calls[0]["events"][-1] == gs.EVENT_TEARDOWN_COMPLETE
    assert result.telemetry_persist_ms is not None
    assert result.telemetry_persist_ms >= 0
    assert target.exists()


def test_true_first_durable_requires_canonical_commit_reopen_hash_proof(tmp_path):
    payload = b"synthetic committed bytes"
    digest = hashlib.sha256(payload).hexdigest()
    asset = tmp_path / "asset.png"
    asset.write_bytes(payload)

    class Volume:
        def commit(self):
            return None

    pending = gs.PendingDurability(
        asset_abs_path=str(asset),
        volume_rel_path="asset.png",
        sha256=digest,
        byte_count=len(payload),
        sidecar_path=str(tmp_path / "asset.json"),
        committed=False,
        volume_mount_root=str(tmp_path),
    )
    with pytest.raises(RuntimeError, match="mount_reopen_proof"):
        asyncio.run(gs.golden_durable_commit(Volume(), pending, gs.GoldenTelemetryRecorder()))

    # The canonical proof API may return a private typed proof rather than a
    # forgeable marker dict; both expose the proof fields for inspection.
    recorder = gs.GoldenTelemetryRecorder()
    reopened = asyncio.run(
        gs.golden_durable_commit(Volume(), pending, recorder, expected_sha256=digest)
    )
    assert reopened["sha256"] == digest
    assert reopened["byte_count"] == len(payload)
    recorder.mark_true_durable()
    assert recorder.true_durable_marked is True


def test_unet_dynamic_gate_and_allocation_checkpoints_are_offline_contracts(monkeypatch):
    comfy = types.ModuleType("comfy")
    model_patcher = types.ModuleType("comfy.model_patcher")
    dynamic = type("ModelPatcherDynamic", (), {})
    legacy = type("ModelPatcher", (), {})
    setattr(model_patcher, "ModelPatcherDynamic", dynamic)
    setattr(model_patcher, "CoreModelPatcher", dynamic)
    setattr(comfy, "model_patcher", model_patcher)
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.model_patcher", model_patcher)

    assert gs.require_dynamic_core_model_patcher(tag="unet") is dynamic
    setattr(model_patcher, "CoreModelPatcher", legacy)
    with pytest.raises(RuntimeError, match="unet_dynamic_core_model_patcher_required"):
        gs.require_dynamic_core_model_patcher(tag="unet")

    # The event/interval shape is testable without constructing a CUDA model.
    recorder = gs.GoldenTelemetryRecorder()
    recorder.begin_stage("golden_unet_load")
    checkpoints = [
        {"name": "before_skeleton", "allocated_bytes": 10, "reserved_bytes": 20},
        {"name": "after_skeleton", "allocated_bytes": 30, "reserved_bytes": 40},
        {"name": "after_qd_destination", "allocated_bytes": 50, "reserved_bytes": 60},
        {"name": "after_assign_adoption", "allocated_bytes": 50, "reserved_bytes": 60},
    ]
    for checkpoint in checkpoints:
        recorder.event("unet_cuda_allocation_checkpoint", checkpoint=checkpoint)
    recorder.end_stage(
        "golden_unet_load", ready=True, cuda_allocation_checkpoints=checkpoints
    )
    events = [
        event for event in recorder.events
        if event["name"] == "unet_cuda_allocation_checkpoint"
    ]
    assert [event["fields"]["checkpoint"]["name"] for event in events] == [
        item["name"] for item in checkpoints
    ]
    assert recorder.intervals["golden_unet_load"].details[
        "cuda_allocation_checkpoints"
    ] == checkpoints


def test_runner_quiescence_rejects_leaked_future_and_accepts_completed_future():
    async def exercise():
        runner = gs.GoldenSerialRunner({}, node_classes={})
        pending = asyncio.get_running_loop().create_future()
        runner._golden_futures.add(pending)
        with pytest.raises(RuntimeError, match="golden_future_pending"):
            runner.assert_quiescent()

        pending.set_result("complete")
        await pending
        runner.assert_quiescent()

        task = asyncio.create_task(asyncio.sleep(0))
        runner._golden_futures.add(task)
        with pytest.raises(RuntimeError, match="golden_future_pending"):
            runner.assert_quiescent()
        await task
        runner.assert_quiescent()

    asyncio.run(exercise())


def test_teardown_checks_real_runner_quiescence_and_records_failure():
    async def exercise():
        runner = gs.GoldenSerialRunner({}, node_classes={})
        pending = asyncio.get_running_loop().create_future()
        runner._golden_futures.add(pending)
        session = _minimal_session()
        session.runner = runner

        with pytest.raises(RuntimeError, match="golden_future_pending"):
            await gs.golden_teardown(session)
        interval = session.recorder.intervals["golden_teardown"]
        assert interval.end_monotonic_ns is not None
        assert interval.ok is False

        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass

    asyncio.run(exercise())


def test_durable_commit_precondition_failure_has_stage_interval():
    recorder = gs.GoldenTelemetryRecorder()
    with pytest.raises(RuntimeError, match="pending_durability"):
        asyncio.run(
            gs.golden_durable_commit(
                object(), None, recorder, expected_sha256="a" * 64
            )
        )
    interval = recorder.intervals["golden_durable_commit"]
    assert interval.entry_monotonic_ns is not None
    assert interval.end_monotonic_ns is not None
    assert interval.ok is False


def test_snapshot_size_evidence_is_required_and_bounded():
    surface = {"runtime": "clean"}
    with pytest.raises(RuntimeError, match="snapshot_size_unavailable"):
        gs.golden_snapshot_content_proof(roots=[surface])
    with pytest.raises(RuntimeError, match="snapshot_size_limit"):
        gs.golden_snapshot_content_proof(
            roots=[surface], snapshot_size_bytes=5 * 1024**3
        )


def test_deep_clean_runtime_scaffolding_uses_size_gate_not_graph_depth():
    surface = {}
    cursor = surface
    for _ in range(64):
        cursor["nested"] = {}
        cursor = cursor["nested"]
    cursor["callback"] = lambda: None
    proof = gs.golden_snapshot_content_proof(roots=[surface], snapshot_size_bytes=1)
    assert proof["passive"] is True
    assert proof["snapshot_size_bytes"] == 1
    assert proof["snapshot_size_source"] == gs.SNAPSHOT_SIZE_SOURCE
    assert proof["snapshot_size_is_serialized"] is False


def test_cyclic_snapshot_surface_is_ignored_without_traversal_crash():
    surface = {}
    surface["self"] = surface
    proof = gs.golden_snapshot_content_proof(roots=[surface], snapshot_size_bytes=1)
    assert proof["passive"] is True
    assert proof["tensor_count"] == 0


def test_runtime_scaffolding_is_bounded_without_hiding_direct_contamination():
    surface = {}
    cursor = surface
    for _ in range(20):
        cursor["child"] = {}
        cursor = cursor["child"]
    cursor["cycle"] = surface

    imported = types.ModuleType("runtime_scaffolding")
    imported.__dict__["callback"] = lambda: None
    imported.__dict__["deep_globals"] = {"nested": {"nested": {"nested": {}}}}
    cursor["imported"] = imported

    proof = gs.golden_snapshot_content_proof(roots=[surface], snapshot_size_bytes=1)
    assert proof["passive"] is True
    assert proof["tensor_count"] == 0

    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero"):
        gs.golden_snapshot_content_proof(roots=[torch.zeros(1)], snapshot_size_bytes=1)


def test_duplicate_canonical_nodes_fail_closed():
    prompt = {
        "clip-a": {"class_type": "CLIPLoader", "inputs": {"clip_name": gs.CANONICAL_CLIP_NAME, "type": gs.CANONICAL_CLIP_TYPE}},
        "clip-b": {"class_type": "CLIPLoader", "inputs": {"clip_name": gs.CANONICAL_CLIP_NAME, "type": gs.CANONICAL_CLIP_TYPE}},
        "encode": {"class_type": "CLIPTextEncode", "inputs": {}},
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": gs.CANONICAL_UNET_NAME}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": gs.CANONICAL_VAE_NAME}},
        "sampler": {"class_type": gs.CANONICAL_SAMPLER_CLASS, "inputs": {}},
        "decode": {"class_type": "VAEDecode", "inputs": {}},
    }
    with pytest.raises(RuntimeError, match="duplicate|ambiguous"):
        gs.resolve_golden_node_map(prompt)


def test_saveimage_selected_socket_must_be_zero(tmp_path):
    prompt = {
        "decode": {"class_type": "VAEDecode", "inputs": {}},
        "switch": {
            "class_type": "Any Switch (rgthree)",
            "inputs": {"any_02": ["decode", 1]},
        },
        "save": {
            "class_type": "SaveImage",
            "inputs": {"images": ["switch", 0]},
        },
    }

    class SaveImage:
        FUNCTION = "save_images"

        def save_images(self, **_kwargs):
            return {"ui": {}}

    class Runner:
        def _classes(self):
            return {"SaveImage": SaveImage}

        async def run_closure(self, *_args, **_kwargs):
            raise AssertionError("socket contract should fail before execution")

        def assert_quiescent(self):
            pass

    session = _minimal_session()
    session.request = _request(prompt)
    session.runner = Runner()
    session.node_map = gs.GoldenNodeMap("clip", "encode", "unet", "vae", "sampler", "decode")
    session.volume_mount_root = str(tmp_path)
    with pytest.raises(RuntimeError, match="selected_input_mismatch"):
        asyncio.run(gs.golden_output(session))


def test_output_and_commit_containment_and_reopen_hash_are_fail_closed(tmp_path):
    mount = tmp_path / "mount"
    outside = tmp_path / "outside"
    mount.mkdir()
    outside.mkdir()
    for path in (outside / "absolute.png", outside / "absolute.json"):
        with pytest.raises(RuntimeError, match="asset_outside_volume_mount"):
            gs._require_path_in_volume(str(path), str(mount))

    link = mount / "output-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this Windows host")
    with pytest.raises(RuntimeError, match="asset_outside_volume_mount"):
        gs._require_path_in_volume(str(link / "asset.png"), str(mount))
    with pytest.raises(RuntimeError, match="asset_outside_volume_mount"):
        gs._require_path_in_volume(str(outside / "sidecar.json"), str(mount))

    payload = b"durable payload"
    digest = hashlib.sha256(payload).hexdigest()
    asset = mount / "asset.png"
    asset.write_bytes(payload)
    pending = gs.PendingDurability(
        asset_abs_path=str(asset),
        volume_rel_path="asset.png",
        sha256=digest,
        byte_count=len(payload),
        sidecar_path=str(mount / "asset.json"),
        volume_mount_root=str(mount),
    )

    class MutatingVolume:
        def commit(self):
            asset.write_bytes(b"changed after write")

    with pytest.raises(RuntimeError, match="durable_(byte_count|sha)_mismatch"):
        asyncio.run(
            gs.golden_durable_commit(
                MutatingVolume(),
                pending,
                gs.GoldenTelemetryRecorder(),
                expected_sha256=digest,
            )
        )
