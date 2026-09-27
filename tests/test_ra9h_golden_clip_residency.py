"""Focused RA9H tests for Golden CLIP residency and ownership seams."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfymodal_runtime import clip_fast_hydration as cfh  # noqa: E402
from comfymodal_runtime import clip_fp32_cast_once as ra9g  # noqa: E402
from comfymodal_runtime import golden_serial as gs  # noqa: E402


class _Owner:
    def __init__(self, log=None):
        self.released = 0
        self.log = log if log is not None else []

    def release_storage(self, purge_allocator=False):
        self.log.append("owner_release")
        self.released += 1


def _manifest_and_identity(*, device="cpu"):
    manifest = {
        "file_index": 0,
        "dtype": "torch.bfloat16",
        "key_set": ["weight"],
        "key_shapes": {"weight": [4]},
    }
    identity = ra9g.build_source_manifest_identity(
        [manifest],
        identity={
            "checkpoint_identity": "authoritative-checkpoint",
            "manifest_generation": "authoritative-generation",
            "selected_tensor_scope": "authoritative-scope",
            "model_patch_identity": "authoritative-patch",
        },
        target_device=device,
    )
    return manifest, identity


def _transfer(log=None):
    manifest, identity = _manifest_and_identity()
    source = {"weight": torch.arange(4, dtype=torch.bfloat16)}
    owner = _Owner(log)
    transfer = ra9g.ClipFP32OwnershipTransfer(
        [source], [owner], [manifest], identity, strict=True
    )
    transformed, _ = transfer.transform_once()
    return transfer, transformed, owner, identity


def test_selector_defaults_explicit_and_invalid_fail_closed(monkeypatch):
    monkeypatch.delenv(gs.CLIP_FP32_CAST_ONCE_ENV, raising=False)
    assert gs.resolve_clip_residency() == "bf16"
    assert gs.GoldenRequest("r", {}).clip_residency == "bf16"
    assert gs.GoldenRequest("r", {}, clip_residency="FP32_CAST_ONCE").clip_residency == "fp32_cast_once"
    with pytest.raises(ValueError, match="clip_residency_invalid"):
        gs.GoldenRequest("r", {}, clip_residency="silent_fallback")
    for raw in ("0", "false", "off"):
        monkeypatch.setenv(gs.CLIP_FP32_CAST_ONCE_ENV, raw)
        assert gs.GoldenRequest("r", {}).clip_residency == "bf16"
    for raw in ("1", "true", "on"):
        monkeypatch.setenv(gs.CLIP_FP32_CAST_ONCE_ENV, raw)
        assert gs.GoldenRequest("r", {}).clip_residency == "fp32_cast_once"
    # The canonical env parser's established safe failure for an invalid
    # explicit bool is false; the request remains BF16 rather than guessing.
    monkeypatch.setenv(gs.CLIP_FP32_CAST_ONCE_ENV, "invalid")
    assert gs.GoldenRequest("r", {}).clip_residency == "bf16"


def test_named_ra9h_telemetry_fields_are_flat_and_unavailable_is_not_zero():
    payload = gs.GoldenTelemetryRecorder().to_json_dict()
    for name in gs._RA9H_TELEMETRY_FIELDS:
        assert name in payload
    assert payload["clip_residency_requested"] == "bf16"
    assert payload["clip_residency_effective"] == "bf16"
    assert payload["clip_load_total_ms"] is None
    assert payload["cast_once_transform_ms"] is None
    assert payload["cast_once_bind_ms"] is None
    assert payload["cast_once_proof_ms"] is None
    assert payload["clip_forward_total_ms"] is None


def test_compute_dtype_uses_real_qwen_boundary_evidence_not_residency():
    assert gs._clip_compute_dtype_from_forward_evidence([], {}) == (
        None,
        {
            "status": "UNPROVEN",
            "forward_count": 0,
            "input_dtypes": [],
            "output_dtypes": [],
            "cast_destination_dtypes": [],
        },
    )
    dtype, evidence = gs._clip_compute_dtype_from_forward_evidence(
        [{
            "input_facts": [{"dtype": "torch.bfloat16", "device": "cuda:0"}],
            "output_facts": [{"dtype": "torch.float32", "device": "cuda:0"}],
            "conversion_entries": [{"destination_dtype": "torch.float32"}],
        }],
        {"conversions": [{"destination_dtype": "torch.float32"}]},
    )
    assert dtype == "torch.float32"
    assert evidence["status"] == "PROVEN"


def test_compute_dtype_mixed_output_evidence_fails_closed():
    dtype, evidence = gs._clip_compute_dtype_from_forward_evidence(
        [{
            "input_facts": [{"dtype": "torch.bfloat16", "device": "cpu"}],
            "output_facts": [
                {"dtype": "torch.float32", "device": "cpu"},
                {"dtype": "torch.bfloat16", "device": "cpu"},
            ],
            "conversion_entries": [{"destination_dtype": "torch.float32"}],
        }],
        {"conversions": [{"destination_dtype": "torch.float32"}]},
    )
    assert dtype is None
    assert evidence["status"] == "OBSERVED"
    assert evidence["reason"] == "mixed_or_missing_forward_boundary_dtype"


def test_compute_dtype_truncated_forward_evidence_fails_closed():
    dtype, evidence = gs._clip_compute_dtype_from_forward_evidence(
        [{
            "input_facts": [{"dtype": "torch.bfloat16", "device": "cpu"}],
            "output_facts": [{"dtype": "torch.float32", "device": "cpu"}],
            "output_facts_truncated": True,
            "conversion_entries": [{"destination_dtype": "torch.float32"}],
        }],
        {"conversions": [{"destination_dtype": "torch.float32"}]},
    )
    assert dtype is None
    assert evidence["reason"] == "bounded_forward_facts_truncated"


def test_compute_dtype_ignores_unrelated_conversion_outside_selected_qwen_forward():
    dtype, evidence = gs._clip_compute_dtype_from_forward_evidence(
        [
            {
                "input_facts": [{"dtype": "torch.bfloat16", "device": "cpu"}],
                "output_facts": [{"dtype": "torch.float32", "device": "cpu"}],
                "conversion_entries": [],
            },
            {
                "input_facts": [{"dtype": "torch.bfloat16", "device": "cpu"}],
                "output_facts": [{"dtype": "torch.float32", "device": "cpu"}],
                "conversion_entries": [{"destination_dtype": "torch.float32"}],
            },
        ],
        {"conversions": [{"destination_dtype": "torch.float32"}]},
    )
    assert dtype is None
    assert evidence["status"] == "OBSERVED"
    assert evidence["cast_destination_dtypes"] == []
    assert evidence["reason"] == "mixed_or_missing_forward_boundary_dtype"


def test_forward_fact_collection_signals_bounded_truncation():
    facts = gs._clip_forward_tensor_facts(
        [torch.ones(1), torch.ones(1), torch.ones(1)], limit=2
    )
    assert len(facts) == 2
    assert facts.truncated is True


def test_cast_once_failure_classification_uses_lifecycle_phase():
    assert gs._clip_cast_once_failure_classification("constructor_preflight") == (
        False, "constructor_preflight_failure"
    )
    assert gs._clip_cast_once_failure_classification("bind") == (
        True, "fatal_bind_or_proof"
    )
    assert gs._clip_cast_once_failure_classification("proof") == (
        True, "fatal_bind_or_proof"
    )


def test_request_freezes_mode_and_run_identity():
    request = gs.GoldenRequest("run-1", {"1": {"class_type": "X"}}, clip_residency="bf16")
    session = gs.GoldenSession.__new__(gs.GoldenSession)
    session.request = request
    session.contract = gs.GoldenWorkflowContract()
    session.qd_transport_arm = "legacy"
    session.clip_residency = request.clip_residency
    session.run_identity = {
        "request_id": request.request_id,
        "clip_residency": request.clip_residency,
        "qd_transport_arm": session.qd_transport_arm,
    }
    assert request.clip_residency == "bf16"
    assert session.run_identity["clip_residency"] == "bf16"
    with pytest.raises(Exception):
        request.clip_residency = "fp32_cast_once"


@pytest.mark.parametrize("arm", ["legacy", "dispatcher"])
def test_both_qd_transport_seams_are_explicit_and_request_local(monkeypatch, arm):
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, arm)
    assert gs.golden_qd_transport_arm() == arm
    with gs._golden_qd_transport_arm_scope("legacy"):
        assert gs.golden_qd_transport_arm() == "legacy"
    assert gs.golden_qd_transport_arm() == arm


def test_actual_bind_receipt_storage_proof_and_cleanup_order():
    log = []
    transfer, transformed, owner, identity = _transfer(log)
    clip = types.SimpleNamespace(cond_stage_model=object())
    destination = transformed[0]
    with mock.patch.object(cfh, "_leaf_loaders", return_value=[clip.cond_stage_model]), mock.patch.object(
        cfh, "_leaf_param_map", return_value=destination
    ):
        actual = ra9g.actual_bind_destination_map(clip, identity.expected_keys)
        receipt = ra9g.build_actual_bind_receipt(clip, actual, identity, assign=True)
        transfer.acknowledge_actual_bind(actual, receipt=receipt, assign=True, clip=clip)
        transfer.prove_storage(expected_device="cpu")
        assert owner.released == 0
        transfer.drop_source_references(receipt={"receipt": "source-dropped"})
        assert transfer.source_mappings is None
        before_retirement = transfer.source_free_storage_proof(actual, expected_device="cpu")
        assert before_retirement["source_free"] is False
        assert before_retirement["source_refs"] == 0
        assert before_retirement["owner_refs"] == 1
        transfer.retire_owners()
        after_retirement = transfer.source_free_storage_proof(actual, expected_device="cpu")
        assert after_retirement["source_free"] is True
        assert after_retirement["source_refs"] == 0
        assert after_retirement["owner_refs"] == 0
        transfer.mark_ready(clip)
    assert log == ["owner_release"]
    assert transfer.state == ra9g.READY
    assert receipt["actual_bind"] is True
    snapshot = transfer.snapshot()
    assert snapshot["metadata_only"] is True
    assert not any(isinstance(value, torch.Tensor) for value in snapshot.values())
    json.dumps(snapshot)


def test_actual_bind_receipt_rejects_fake_destination_and_keeps_source_live():
    transfer, transformed, owner, _ = _transfer()
    with pytest.raises(ra9g.BindReceiptError):
        transfer.acknowledge_actual_bind(
            transformed, receipt={"receipt_marker": "fake"}, assign=True
        )
    assert transfer.source_mappings is not None
    assert owner.released == 0
    transfer.release()
    assert owner.released == 1


def test_missing_identity_fails_closed_before_fp32_transform():
    manifest = {
        "file_index": 0,
        "dtype": "torch.bfloat16",
        "key_set": ["weight"],
        "key_shapes": {"weight": [1]},
    }
    with pytest.raises(ra9g.OwnershipTransferError, match="missing stable identity"):
        ra9g.build_source_manifest_identity([manifest], identity={}, target_device="cpu")
    # The helper intentionally does not synthesize path/stat identity.
    assert gs._ra9h_authoritative_identity(
        types.SimpleNamespace(request=types.SimpleNamespace(extra_data={}))
    ) == {}


def test_forward_conversion_counter_is_bounded_and_reports_real_allocations(monkeypatch):
    fake_mm = types.ModuleType("comfy.model_management")
    calls = {"forward": 0}

    def cast_to(tensor, dtype=None, device=None, **kwargs):
        calls["forward"] += 1
        return tensor.to(dtype=dtype, device=device) if dtype is not None or device is not None else tensor

    fake_mm.cast_to = cast_to
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    with gs._ra9h_forward_conversion_instrumentation(enabled=True) as record:
        output = fake_mm.cast_to(torch.ones(2, dtype=torch.bfloat16), dtype=torch.float32)
        assert output.dtype is torch.float32
    assert record["status"] == "RUN"
    assert record["conversion_count"] == 1
    assert record["destination_bytes"] == 8
    assert record["synchronization"] == "none"
    assert calls["forward"] == 1


def test_bf16_control_forward_counter_runs_without_conversion(monkeypatch):
    fake_mm = types.ModuleType("comfy.model_management")
    calls = {"forward": 0}

    def cast_to(tensor, dtype=None, device=None, **kwargs):
        calls["forward"] += 1
        return tensor

    fake_mm.cast_to = cast_to
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    with gs._ra9h_forward_conversion_instrumentation(enabled=True) as record:
        output = fake_mm.cast_to(torch.ones(2, dtype=torch.bfloat16), dtype=torch.bfloat16)
        assert output.dtype is torch.bfloat16
    assert calls["forward"] == 1
    assert record["status"] == "RUN"
    assert record["conversion_count"] == 0
    assert record["destination_bytes"] == 0


def test_forward_conversion_unavailable_is_not_run_not_zero(monkeypatch):
    monkeypatch.setitem(sys.modules, "comfy.model_management", types.ModuleType("comfy.model_management"))
    with gs._ra9h_forward_conversion_instrumentation(enabled=True) as record:
        pass
    assert record["status"] == "NOT RUN"
    assert record["conversion_count"] is None
    assert record["destination_bytes"] is None


def test_forward_conversion_diagnostics_pair_two_real_boundaries(monkeypatch):
    fake_mm = types.ModuleType("comfy.model_management")

    def cast_to(tensor, dtype=None, device=None, **kwargs):
        return tensor.to(dtype=dtype, device=device)

    fake_mm.cast_to = cast_to
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    with gs._ra9h_forward_conversion_instrumentation(enabled=True) as record:
        observe = record["_observe_forward"]
        for index in (0, 1):
            observe("start", index)
            fake_mm.cast_to(torch.ones(2, dtype=torch.bfloat16), dtype=torch.float32)
            observe("end", index)
    assert record["real_forward_count"] == 2
    assert [item["conversion_count"] for item in record["per_forward"]] == [1, 1]
    assert [
        len(item["conversion_entries"]) for item in record["per_forward"]
    ] == [1, 1]
    assert record["repeated_conversion_count"] == 1
    assert record["forward_diagnostics_status"] == "PROVEN"


def _ra9h_scope_snapshot(tensor, name="weight"):
    storage = tensor.untyped_storage()
    storage_ptr = int(storage.data_ptr())
    data_ptr = int(tensor.data_ptr())
    return {
        "status": "proven",
        "entries": [{
            "name": name,
            "storage_ptr": storage_ptr,
            "storage_bytes": int(storage.nbytes()),
            "data_ptr": data_ptr,
            "storage_offset_bytes": data_ptr - storage_ptr,
            "tensor_bytes": int(tensor.numel() * tensor.element_size()),
        }],
    }


def test_selected_parameter_conversion_is_proven_in_one_forward(monkeypatch):
    fake_mm = types.ModuleType("comfy.model_management")

    def cast_to(tensor, dtype=None, device=None, **kwargs):
        return tensor.to(dtype=dtype, device=device)

    fake_mm.cast_to = cast_to
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    source = torch.ones(4, dtype=torch.bfloat16)
    with gs._ra9h_forward_conversion_instrumentation(
        enabled=True, scope_snapshot=lambda: _ra9h_scope_snapshot(source)
    ) as record:
        observe = record["_observe_forward"]
        observe("start", 0)
        fake_mm.cast_to(source, dtype=torch.float32)
        observe("end", 0)
    assert record["parameter_scope_proof_status"] == "PROVEN"
    assert record["selected_parameter_conversion_count"] == 1
    assert record["selected_parameter_conversion_bytes"] == 16
    assert record["selected_parameter_conversion_source_bytes"] == 8
    assert record["selected_parameter_source_dtypes"] == ["torch.bfloat16"]
    assert record["selected_parameter_destination_dtypes"] == ["torch.float32"]
    assert record["per_forward_selected_parameter_conversion_counts"] == [1]


def test_unmatched_activation_conversion_does_not_count_as_selected_parameter(monkeypatch):
    fake_mm = types.ModuleType("comfy.model_management")
    fake_mm.cast_to = lambda tensor, dtype=None, device=None, **kwargs: tensor.to(dtype=dtype, device=device)
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    parameter = torch.ones(4, dtype=torch.bfloat16)
    activation = torch.ones(4, dtype=torch.bfloat16)
    with gs._ra9h_forward_conversion_instrumentation(
        enabled=True, scope_snapshot=lambda: _ra9h_scope_snapshot(parameter)
    ) as record:
        observe = record["_observe_forward"]
        observe("start", 0)
        fake_mm.cast_to(activation, dtype=torch.float32)
        observe("end", 0)
    assert record["all_conversion_count"] == 1
    assert record["parameter_scope_proof_status"] == "PROVEN"
    assert record["selected_parameter_conversion_count"] == 0
    assert record["selected_parameter_conversion_bytes"] == 0


def test_activation_conversion_stays_separate_from_proven_parameter_conversion(monkeypatch):
    fake_mm = types.ModuleType("comfy.model_management")
    fake_mm.cast_to = lambda tensor, dtype=None, device=None, **kwargs: tensor.to(dtype=dtype, device=device)
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    parameter = torch.ones(4, dtype=torch.bfloat16)
    activation = torch.ones(2, dtype=torch.bfloat16)
    with gs._ra9h_forward_conversion_instrumentation(
        enabled=True, scope_snapshot=lambda: _ra9h_scope_snapshot(parameter)
    ) as record:
        observe = record["_observe_forward"]
        observe("start", 0)
        fake_mm.cast_to(parameter, dtype=torch.float32)
        fake_mm.cast_to(activation, dtype=torch.float32)
        observe("end", 0)
    assert record["all_conversion_count"] == 2
    assert record["all_conversion_bytes"] == 24
    assert record["parameter_scope_proof_status"] == "PROVEN"
    assert record["selected_parameter_conversion_count"] == 1
    assert record["selected_parameter_conversion_bytes"] == 16


def test_fp32_no_conversion_proves_selected_zero_with_one_forward(monkeypatch):
    fake_mm = types.ModuleType("comfy.model_management")
    fake_mm.cast_to = lambda tensor, dtype=None, device=None, **kwargs: tensor
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    parameter = torch.ones(4, dtype=torch.float32)
    with gs._ra9h_forward_conversion_instrumentation(
        enabled=True, scope_snapshot=lambda: _ra9h_scope_snapshot(parameter)
    ) as record:
        observe = record["_observe_forward"]
        observe("start", 0)
        fake_mm.cast_to(parameter, dtype=torch.float32)
        observe("end", 0)
    assert record["parameter_scope_proof_status"] == "PROVEN"
    assert record["selected_parameter_conversion_count"] == 0
    assert record["selected_parameter_conversion_bytes"] == 0
    assert record["forward_diagnostics_status"] == "UNPROVEN"


def test_missing_cast_seam_leaves_parameter_proof_unproven(monkeypatch):
    monkeypatch.setitem(sys.modules, "comfy.model_management", types.ModuleType("comfy.model_management"))
    with gs._ra9h_forward_conversion_instrumentation(enabled=True) as record:
        pass
    assert record["parameter_scope_proof_status"] == "UNPROVEN"
    assert record["selected_parameter_conversion_count"] is None


def test_failure_and_cancellation_cleanup_do_not_publish_ready():
    log = []
    transfer, _transformed, owner, _ = _transfer(log)
    transfer.fail(RuntimeError("forward failed"))
    assert transfer.state == ra9g.FAILED
    transfer.release()
    assert owner.released == 1
    assert transfer.state != ra9g.READY

    log = []
    cancelled, _transformed, owner, _ = _transfer(log)
    cancelled.fail(asyncio.CancelledError())
    cancelled.release()
    assert owner.released == 1
    assert cancelled.state != ra9g.READY


def test_session_cleanup_plumbing_releases_incomplete_transfer():
    transfer, _transformed, owner, _ = _transfer()
    session = types.SimpleNamespace(
        clip_ownership_transfer=transfer,
        recorder=gs.GoldenTelemetryRecorder(),
    )
    gs.GoldenSession.cleanup_clip_ownership_transfer(session)
    assert owner.released == 1
    assert session.clip_ownership_transfer is None
    assert any(event["name"] == "clip_fp32_cast_once_cleanup" for event in session.recorder.events)


def test_manifest_adapter_uses_transport_facts_without_extra_read_or_h2d():
    source = torch.ones(3, dtype=torch.bfloat16)
    manifest = gs._ra9h_manifest_for_transport(
        {"sd": {"weight": source}, "stats": {"source_read_count": 1, "h2d_completed_bytes": 6}}, 0
    )
    assert manifest["key_set"] == ["weight"]
    assert manifest["key_shapes"] == {"weight": [3]}
    assert manifest["file_index"] == 0


def test_golden_fp32_loader_uses_one_actual_assign_bind_seam(monkeypatch):
    """The experimental arm transforms once and adopts through the existing loader."""
    fake_sd = types.ModuleType("comfy.sd")
    fake_mp = types.ModuleType("comfy.model_patcher")
    fake_mm = types.ModuleType("comfy.model_management")
    fake_folder_paths = types.ModuleType("folder_paths")
    captured = {}

    class DynamicPatcher:
        def is_dynamic(self):
            captured["postflight_phase"] = session.clip_residency_record.get(
                "lifecycle_phase"
            )
            return True

    class Loader(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(
                torch.empty(4, device="meta", dtype=torch.float32)
            )
            # Constructor-owned structural state is not supplied by the
            # checkpoint and must be declared by the live Golden path.
            self.constructor_scale = torch.nn.Parameter(
                torch.ones(1, dtype=torch.float32)
            )

    def load_text_encoder_state_dicts(state_dicts, **kwargs):
        captured["calls"] = captured.get("calls", 0) + 1
        captured["state_dicts"] = state_dicts
        destination = Loader()
        destination.load_state_dict(state_dicts[0], strict=False, assign=True)
        clip = types.SimpleNamespace(
            cond_stage_model=destination,
            patcher=DynamicPatcher(),
            tokenize=lambda *a, **k: {},
            encode_from_tokens_scheduled=lambda *a, **k: "conditioning",
        )
        captured["clip"] = clip
        return clip

    fake_sd.load_text_encoder_state_dicts = load_text_encoder_state_dicts
    fake_sd.CLIPType = types.SimpleNamespace(LUMINA2="LUMINA2")
    fake_mp.CoreModelPatcher = DynamicPatcher
    fake_mp.ModelPatcherDynamic = DynamicPatcher
    fake_mm.text_encoder_initial_device = lambda *a, **k: "native"
    fake_folder_paths.get_folder_paths = lambda _name: []
    monkeypatch.setitem(sys.modules, "comfy.sd", fake_sd)
    monkeypatch.setitem(sys.modules, "comfy.model_patcher", fake_mp)
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    monkeypatch.setitem(sys.modules, "folder_paths", fake_folder_paths)
    fake_comfy = types.ModuleType("comfy")
    fake_comfy.sd = fake_sd
    fake_comfy.model_patcher = fake_mp
    fake_comfy.model_management = fake_mm
    monkeypatch.setitem(sys.modules, "comfy", fake_comfy)

    source = {"weight": torch.arange(4, dtype=torch.bfloat16)}
    owner = gs.GoldenQDOwner(None, [], "cpu", "clip")
    fake_read_calls = {"read": 0}

    def fake_read(path, **kwargs):
        fake_read_calls["read"] += 1
        return {
            "sd": source,
            "owner": owner,
            "stats": {
                "gpu_bytes": 8,
                "source_read_count": 1,
                "h2d_completed_bytes": 8,
                "quiescence": {"workers_joined": True, "h2d_events_waited": True, "copies_complete": True, "operation_live": False},
            },
            "header_metadata": None,
        }

    monkeypatch.setattr(gs, "read_file_qd_gpu", fake_read)
    monkeypatch.setattr(gs, "_require_transport_quiescence", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(
        gs,
        "select_and_validate_qd_adoption_scope",
        lambda *_a, **_k: {
            "selected_scope": "",
            "outer_extra_count": 0,
            "outer_extra_bytes": 0,
            "outer_extra_devices": [],
            "outer_extra_names": [],
            "matched_count": 1,
            "same_storage_count": 1,
            "copied_storage_count": 0,
        },
    )
    monkeypatch.setattr(
        gs,
        "_clip_compute_identity",
        lambda *_a, **_k: {"compute_ready": True, "compute_scope_device": "cpu", "compute_scope_dtype": "torch.float32", "compute_scope_storage_proven": True},
    )

    session = types.SimpleNamespace(
        recorder=gs.GoldenTelemetryRecorder(),
        contract=gs.GoldenWorkflowContract(),
        clip_paths=["/authority/qwen.safetensors"],
        clip_owners=[],
        clip_owner=None,
        qd_transaction_owners=[],
        clip_residency="fp32_cast_once",
        clip_source_identity={
            "checkpoint_identity": "checkpoint-authority",
            "manifest_generation": "generation-authority",
            "selected_tensor_scope": "scope-authority",
            "model_patch_identity": "patch-authority",
            "target_device": "cpu",
        },
        run_identity={},
        clip_ownership_transfer=None,
        clip_ownership_transfer_record={},
        clip_residency_record={},
        model_paths={},
    )
    # GoldenSession methods are intentionally used directly; this keeps the
    # fake at the adapter boundary without constructing unrelated runtime state.
    session.register_qd_owner = gs.GoldenSession.register_qd_owner.__get__(session, gs.GoldenSession)
    clip = asyncio.run(gs.golden_clip_load(session))
    assert captured["calls"] == 1
    assert captured["postflight_phase"] == "bind"
    assert captured["state_dicts"][0]["weight"].dtype is torch.float32
    assert clip.cond_stage_model.weight.data_ptr() == captured["state_dicts"][0]["weight"].data_ptr()
    assert (
        clip.cond_stage_model.weight.untyped_storage().data_ptr()
        == captured["state_dicts"][0]["weight"].untyped_storage().data_ptr()
    )
    assert fake_read_calls["read"] == 1
    assert session.clip_residency_record["status"] == "READY"
    assert session.clip_residency_record["actual"] == "fp32_cast_once"
    assert session.clip_residency_record["fallback"] is False
    assert session.clip_ownership_transfer is None
    assert session.clip_ownership_transfer_record["bind_proof"][
        "structural_destination_keys"
    ] == ["constructor_scale"]
    assert owner.closed is True
    assert any(event["name"] == "clip_fp32_cast_once_actual_bind" for event in session.recorder.events)
    assert clip.patcher.is_dynamic()
    named = session.recorder.to_json_dict()
    assert named["clip_residency_requested"] == "fp32_cast_once"
    assert named["clip_residency_effective"] == "fp32_cast_once"
    assert named["cast_once_attempted"] is True
    assert named["cast_once_applied"] is True
    assert named["cast_once_fallback"] is False
    assert named["selected_tensor_count"] == 1
    assert named["source_dtype"] == "torch.bfloat16"
    assert named["resident_dtype"] == "torch.float32"
    # Compute dtype is intentionally unavailable until an actual selected
    # Qwen forward boundary supplies input/output evidence; residency alone is
    # not a compute claim.
    assert named["compute_dtype"] is None
    assert named["expected_device"] == "cpu"
    assert named["cast_destination_bytes"] == 16
    assert named["adopted_parameter_count"] == 1
    assert named["adopted_storage_proven"] is True
    assert named["source_refs_dropped"] is True
    assert named["source_owner_retired"] is True
    assert named["clip_load_total_ms"] is not None
    assert named["cast_once_transform_ms"] is not None
    assert named["cast_once_bind_ms"] is not None
    assert named["cast_once_proof_ms"] is not None
    assert named["clip_forward_total_ms"] is None


def test_golden_bind_seam_rejects_unrelated_extra_after_structural_discovery():
    class ConstructorModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.ones(2, dtype=torch.float32))
            self.constructor_scale = torch.nn.Parameter(
                torch.ones(1, dtype=torch.float32)
            )

    model = ConstructorModel()
    clip = types.SimpleNamespace(cond_stage_model=model)
    structural = ra9g.discover_structural_destination_keys(clip, {"weight"})
    assert structural == ["constructor_scale"]

    model.register_parameter(
        "unrelated_extra", torch.nn.Parameter(torch.ones(1, dtype=torch.float32))
    )
    with pytest.raises(ra9g.OwnershipTransferError, match="actual destination extra keys"):
        ra9g.actual_bind_destination_map(
            clip, {"weight"}, declared_structural_keys=structural
        )
