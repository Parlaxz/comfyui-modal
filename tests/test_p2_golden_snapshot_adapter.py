"""Focused P2-2 Golden snapshot/adapter checks.

These tests exercise the small adapter seams with fakes.  They do not start
ComfyUI, load models, or invoke CUDA.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from comfymodal_runtime import modal_app
from comfymodal_runtime import golden_serial
from comfymodal_runtime.trace import RuntimeTrace


def test_golden_gate_uses_dynamic_flag_or_profile(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM", raising=False)
    monkeypatch.delenv("COMFYMODAL_V2CTL_PROFILE", raising=False)
    assert modal_app._golden_serial_profile_active() is False

    monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM", "yes")
    assert modal_app._golden_serial_profile_active() is True

    monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM", "0")
    monkeypatch.setenv("COMFYMODAL_V2CTL_PROFILE", " golden_p1 ")
    assert modal_app._golden_serial_profile_active() is True


def test_startup_source_keeps_non_golden_cpu_snapshot_gate_and_golden_bypass():
    source = Path(modal_app.__file__).read_text(encoding="utf-8")
    golden_branch = source.index("if _golden_serial_active:")
    cpu_gate = source.index("elif _cpu_model_snapshot_enabled():", golden_branch)
    assert source.index("_clear_cpu_snapshot_state_for_golden()", golden_branch) < cpu_gate
    surfaces = source.index("_golden_pre_capture_surfaces = self._golden_snapshot_proof_surfaces()", golden_branch)
    assert source.index("_clear_cpu_snapshot_state_for_golden()", golden_branch) < surfaces
    assert source.index("self._run_golden_snapshot_content_proof(") > cpu_gate


def test_golden_state_clear_drops_snapshot_model_references():
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._cpu_snapshot_models = cast(Any, object())
    entrypoint._snapshot_eviction_retained_model = object()
    entrypoint._cpu_snapshot_models_active = True
    entrypoint._clear_cpu_snapshot_state_for_golden()
    assert entrypoint._cpu_snapshot_models is None
    assert entrypoint._snapshot_eviction_retained_model is None
    assert entrypoint._cpu_snapshot_models_active is False


def test_golden_restore_rejects_snapshot_model_residue():
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._cpu_snapshot_models = cast(Any, object())
    with pytest.raises(RuntimeError, match="golden_restore_model_residue"):
        entrypoint._assert_golden_restore_model_free()


def test_golden_execution_rejects_preload_residue():
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._preload_bridge._preparation = cast(Any, object())
    with pytest.raises(RuntimeError, match="golden_preload_state_forbidden"):
        entrypoint._assert_golden_execution_isolated()


def test_pre_capture_proof_is_recorded_and_errors_fail_closed(monkeypatch, tmp_path):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))

    calls = []

    def clean_proof(**kwargs):
        calls.append(kwargs)
        assert entrypoint._legacy_api in kwargs["roots"]
        assert kwargs["snapshot_size_bytes"] == 123 * 1024
        assert kwargs["snapshot_size_source"] == golden_serial.SNAPSHOT_SIZE_SOURCE
        assert kwargs["snapshot_size_is_serialized"] is False
        return {
            "schema": "golden_snapshot_content_proof_v1",
            "passive": True,
            "surface_count": 1,
            "snapshot_size_bytes": kwargs["snapshot_size_bytes"],
            "snapshot_size_source": kwargs["snapshot_size_source"],
            "snapshot_size_is_serialized": False,
            "tensor_count": 0,
            "parameter_bytes": 0,
            "model_patcher_count": 0,
            "qd_owner_count": 0,
            "open_payload_reader_count": 0,
            "preload_worker_count": 0,
            "future_count": 0,
            "nonzero": {},
            "nonzero_roles": {},
        }

    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.read_process_status_fields",
        lambda: {"rss_kb": 123},
    )
    monkeypatch.setattr(golden_serial, "golden_snapshot_content_proof", clean_proof)
    trace = RuntimeTrace(process="remote")
    proof = entrypoint._run_golden_snapshot_content_proof(trace=trace)
    assert calls and proof["proven"] is True
    assert calls[0]["persist_path"] == str(tmp_path / "golden_snapshot_content_proof.json")
    assert entrypoint._restore_timing["golden_snapshot_content_proof"] == proof
    assert trace.to_dict()["metadata"]["golden_snapshot_content_proof"] == proof

    def failing_proof(**_kwargs):
        raise RuntimeError("contaminated")

    monkeypatch.setattr(golden_serial, "golden_snapshot_content_proof", failing_proof)
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof(trace=trace)
    assert entrypoint._restore_timing["golden_snapshot_content_proof"]["proven"] is False


def test_pre_capture_proof_rejects_incomplete_result(monkeypatch):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}

    monkeypatch.setattr(
        golden_serial,
        "golden_snapshot_content_proof",
        lambda **_kwargs: {"schema": "golden_snapshot_content_proof_v1", "passive": True},
    )
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof()


@pytest.mark.parametrize("rss_kb", [None, 0, True, "123"])
def test_pre_capture_proof_fails_closed_when_process_rss_is_invalid(monkeypatch, rss_kb):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}
    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.read_process_status_fields",
        lambda: {"rss_kb": rss_kb},
    )
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof()
    failure = entrypoint._restore_timing["golden_snapshot_content_proof"]
    assert failure["snapshot_size_source"] == golden_serial.SNAPSHOT_SIZE_SOURCE
    assert failure["snapshot_size_is_serialized"] is False


def test_pre_capture_proof_fails_closed_at_snapshot_size_limit(monkeypatch):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}
    limit = golden_serial.GOLDEN_SNAPSHOT_SIZE_LIMIT_BYTES
    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.read_process_status_fields",
        lambda: {"rss_kb": limit // 1024},
    )
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof()
    assert "process_rss_limit" in entrypoint._restore_timing[
        "golden_snapshot_content_proof"
    ]["error"]


def test_adapter_passes_mount_restore_metadata_and_terminal_timestamps(monkeypatch, tmp_path):
    volume = object()
    monkeypatch.setitem(modal_app._MODAL_RESOURCES, "runtime_state_volume", volume)
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))
    monkeypatch.setattr(
        "comfymodal_runtime.golden_aimdo_activation.activate_golden_dynamic_vram",
        lambda: {"activated": True, "already_activated": False, "is_dynamic_alias": True},
    )
    installed_nodes = SimpleNamespace(NODE_CLASS_MAPPINGS={"X": object()})
    monkeypatch.setitem(sys.modules, "nodes", installed_nodes)

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    restore_metadata = {
        "remote_python_resume_wall_unix_ns": 100,
        "remote_python_resume_mono_ns": 100,
        "restore_method_start_wall_unix_ns": 100,
        "restore_method_start_mono_ns": 100,
        "restore_method_end_wall_unix_ns": 200,
        "restore_method_end_mono_ns": 200,
        "restore_method_status": "success",
    }
    entrypoint._restore_timing = restore_metadata
    calls = []

    async def fake_execute(request, **kwargs):
        calls.append((request, kwargs))
        Path(kwargs["telemetry_path"]).write_text(
            json.dumps({
                "schema": "golden_p1_telemetry_v1",
                "stages": [{
                    "name": "golden_teardown",
                    "end_monotonic_ns": 10,
                    "end_wall_ns": 10,
                    "ok": True,
                }],
                "events": [{
                    "name": "TEARDOWN_COMPLETE",
                    "monotonic_ns": 11,
                    "wall_ns": 11,
                    "fields": {"request_id": request.request_id},
                }],
            }),
            encoding="utf-8",
        )
        return golden_serial.GoldenFinalResult(
            request_id=request.request_id,
            image_sha256="a" * 64,
            asset_path="out.png",
            volume_rel_path="golden/out.png",
            true_durable=True,
            seriality_violation_count=0,
            executed_nodes=[],
        )

    monkeypatch.setattr(golden_serial, "golden_serial_execute", fake_execute)

    async def collect():
        return [
            event
            async for event in entrypoint.run_golden_serial_stream(
                {"request_id": "p2", "prompt": {"1": {"class_type": "X"}}}
            )
        ]

    events = asyncio.run(collect())
    assert len(calls) == 1
    kwargs = calls[0][1]
    assert kwargs["volume"] is volume
    assert kwargs["volume_mount_root"] == str(tmp_path)
    assert kwargs["restore_metadata"] == restore_metadata
    assert kwargs["node_classes"] is installed_nodes.NODE_CLASS_MAPPINGS

    terminal = next(event["data"]["terminal"] for event in events if event["type"] == "result")
    for key in (
        "return_wall_unix_ns",
        "return_mono_ns",
        "yield_wall_unix_ns",
        "yield_mono_ns",
    ):
        assert isinstance(terminal[key], int)
    assert terminal["return_mono_ns"] <= terminal["yield_mono_ns"]
    telemetry = next(event["data"]["golden_telemetry"] for event in events if event["type"] == "result")
    teardown = next(stage for stage in telemetry["stages"] if stage["name"] == "golden_teardown")
    teardown_complete = next(
        event for event in telemetry["events"] if event["name"] == "TEARDOWN_COMPLETE"
    )
    assert teardown["end_monotonic_ns"] <= teardown_complete["monotonic_ns"]
    assert [event["name"] for event in telemetry["events"]] == ["TEARDOWN_COMPLETE"]
    assert "adapter_completion" not in telemetry


def test_adapter_rejects_runtime_mount_identity_mismatch(monkeypatch, tmp_path):
    class MismatchedVolume:
        volume_mount_root = str(tmp_path / "other")

    with pytest.raises(RuntimeError, match="golden_runtime_mount_root_identity_mismatch"):
        modal_app._validate_golden_runtime_mount_root(MismatchedVolume())


def test_adapter_rejects_missing_restore_metadata(monkeypatch, tmp_path):
    monkeypatch.setitem(modal_app._MODAL_RESOURCES, "runtime_state_volume", object())
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))
    entrypoint = modal_app.ModalRuntimeEntrypoint()

    async def collect():
        return [
            event
            async for event in entrypoint.run_golden_serial_stream(
                {"request_id": "missing-meta", "prompt": {"1": {"class_type": "X"}}}
            )
        ]

    events = asyncio.run(collect())
    assert events and events[0]["type"] == "error"
    assert "golden_restore_metadata_missing" in events[0]["message"]


def test_adapter_rejects_contract_override(monkeypatch, tmp_path):
    monkeypatch.setitem(modal_app._MODAL_RESOURCES, "runtime_state_volume", object())
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._restore_timing = {
        "remote_python_resume_wall_unix_ns": 100,
        "remote_python_resume_mono_ns": 100,
        "restore_method_start_wall_unix_ns": 100,
        "restore_method_start_mono_ns": 100,
        "restore_method_end_wall_unix_ns": 200,
        "restore_method_end_mono_ns": 200,
        "restore_method_status": "success",
    }

    async def collect():
        return [
            event
            async for event in entrypoint.run_golden_serial_stream(
                {
                    "request_id": "contract-override",
                    "prompt": {"1": {"class_type": "X"}},
                    "contract": {"workflow_sha256": "0" * 64},
                }
            )
        ]

    events = asyncio.run(collect())
    assert events and events[0]["type"] == "error"
    assert "golden_contract_override_not_allowed" in events[0]["message"]
