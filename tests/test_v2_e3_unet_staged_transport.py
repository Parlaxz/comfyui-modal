"""Offline contract tests for the generic UNET staged transport adapter."""

from __future__ import annotations

import os
import tempfile
import types
from pathlib import Path
from unittest import mock

import torch

import comfymodal_runtime.unet_fastsafetensors as fs
from tests.test_c9_fastsafetensors_integration import (
    _FakeFB,
    _FakeFSTLoader,
    _FakeTrace,
    _Patch,
    _TinyModule,
    ZImage,
    _c6_fake,
    _fs_common_patches,
    _tiny_header,
    _tiny_sd,
    _write_tiny_file,
)


class _TransportArtifact:
    def __init__(self, label: str, order: list[str]):
        self.label = label
        self.order = order
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        self.order.append(f"close:{self.label}")


def _staged_module(tensors, order, *, fail_commit=False):
    def build_plan(path, manifest):
        order.append("plan")
        return _TransportArtifact("plan", order)

    def prepare(plan):
        order.append("prepare")
        return _TransportArtifact("prepared", order)

    def commit(prepared, target):
        order.append("commit")
        if fail_commit:
            raise RuntimeError("commit boom")
        return {
            "tensors": tensors,
            "owner": _TransportArtifact("committed", order),
            "metrics": {"h2d_ms": 3.25},
        }

    return types.SimpleNamespace(
        build_plan=build_plan,
        prepare=prepare,
        commit=commit,
    )


def _pipeline_patches(path, tensors, staged_module):
    patches = _fs_common_patches(
        path,
        _tiny_header(),
        ZImage(),
        tensors,
        target=torch.device("cpu"),
        expected_params=40,
        expected_bytes=80,
    )
    patches.update({
        "_fs_staged_module": lambda: staged_module,
        "_c6_comfy_fn": _c6_fake(),
    })
    return patches


def _run_pipeline(path, patches):
    trace = _FakeTrace()
    with _Patch(fs, **patches), \
            _Patch(fs, _ACTIVE_LANE_TRACE=types.SimpleNamespace(
                get=lambda: types.SimpleNamespace(_trace=trace))), \
            mock.patch.dict(os.environ, {
                fs._STAGED_TRANSPORT_FLAG: "1",
            }, clear=False):
        result = fs._fs_try_pipeline(
            None,
            None,
            {"unet_name": "generic.safetensors", "weight_dtype": "default"},
            None,
        )
    events = [event for event in trace.events
              if event[0] == "unet_fastsafetensors_pipeline"]
    assert len(events) == 1
    return result, events[0][2], trace


def test_staged_plan_prepare_commit_are_separate_and_generic():
    order = []
    tensors = _tiny_sd()
    module = _staged_module(tensors, order)
    with mock.patch.object(fs, "_fs_staged_module", lambda: module):
        plan = fs._fs_staged_plan("model.safetensors", _tiny_header())
        prepared = fs._fs_staged_prepare(plan)
        committed = fs._fs_staged_commit(prepared, torch.device("cpu"))

    assert order[:3] == ["plan", "prepare", "commit"]
    loaded, inner_owner, metrics = fs._fs_staged_result(committed)
    assert loaded.keys() == tensors.keys()
    assert inner_owner.label == "committed"
    assert metrics["h2d_ms"] == 3.25


def test_adapter_matches_real_staged_helper_surface():
    from comfymodal_runtime import staged_safetensors

    assert fs._fs_staged_fn(staged_safetensors, ("plan",)) is staged_safetensors.plan
    assert fs._fs_staged_fn(staged_safetensors, ("prepare",)) is staged_safetensors.prepare
    assert fs._fs_staged_fn(staged_safetensors, ("commit",)) is staged_safetensors.commit
    with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {
        fs._STAGED_TRANSPORT_FLAG: "1",
    }, clear=False):
        path = str(Path(td) / "real-contract.safetensors")
        _write_tiny_file(path)
        plan = fs._fs_staged_plan(path, _tiny_header(), torch.device("cpu"))
    assert type(plan).__name__ == "StagePlan"
    assert plan.enabled is True


def test_staged_eligibility_does_not_require_zimage_or_filename():
    class GenericConfig:
        supported_inference_dtypes = [torch.bfloat16]

    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "arbitrary-name.safetensors")
        _write_tiny_file(path)
        module = _staged_module(_tiny_sd(), [])
        patches = _fs_common_patches(
            path, _tiny_header(), GenericConfig(), _tiny_sd(),
            target=torch.device("cpu"), expected_params=40, expected_bytes=80,
        )
        patches["_fs_staged_module"] = lambda: module
        with _Patch(fs, **patches):
            eligible, reason = fs._fs_staged_eligible(
                None,
                {"unet_name": "arbitrary-name.safetensors",
                 "weight_dtype": "default"},
                None,
            )
    assert eligible, reason


def test_staged_pipeline_preserves_bind_and_d15_order():
    order = []
    tensors = _tiny_sd()
    module = _staged_module(tensors, order)
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "model.safetensors")
        _write_tiny_file(path)
        patches = _pipeline_patches(path, tensors, module)
        gate = object()
        patches["_gpu_coord"] = types.SimpleNamespace(
            start_request=lambda *a: None,
            begin_unet_gpu_phase=lambda *a, **k: (order.append("gate") or gate),
            unet_transfer_start=lambda *a, **k: (order.append("transfer_start") or 1),
            unet_transfer_end=lambda *a, **k: order.append("transfer_end"),
            record_unet_ready=lambda *a, **k: None,
            end_unet_gpu_phase=lambda *a, **k: order.append("gate_end"),
        )
        with mock.patch.object(fs, "_fs_fastsafe_load",
                              side_effect=AssertionError("direct path used")):
            result, metrics, _trace = _run_pipeline(path, patches)

    assert result is not None
    assert order.index("gate") < order.index("prepare")
    assert order.index("prepare") < order.index("commit")
    assert order.index("commit") < order.index("transfer_end")
    assert order.index("transfer_end") < order.index("gate_end")
    assert metrics["staged_transport"] is True
    assert metrics["key_set_ok"] is True
    assert metrics["residual_meta_after"] == 0
    assert metrics["unet_staged_h2d_ms"] == 3.25
    assert metrics["unet_staged_bind_ms"] is not None
    assert hasattr(result[0], fs._STAGED_OWNER_ATTR)


def test_staged_commit_failure_uses_direct_fastsafe_once():
    order = []
    tensors = _tiny_sd()
    module = _staged_module(tensors, order, fail_commit=True)
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "model.safetensors")
        _write_tiny_file(path)
        patches = _pipeline_patches(path, tensors, module)
        loader = _FakeFSTLoader(tensors)
        fb = _FakeFB(tensors)
        direct = mock.Mock(return_value=(tensors, loader, fb))
        patches["_fs_fastsafe_load"] = direct
        result, metrics, _trace = _run_pipeline(path, patches)

    assert result is not None
    direct.assert_called_once()
    assert order.count("commit") == 1
    assert metrics["fallback_count"] == 1
    assert metrics["unet_staged_fallback_reason"].startswith("RuntimeError:")
    assert metrics["owner_mode"] == "loader_retained"
    assert hasattr(result[0], fs._FS_OWNER_ATTR)


def test_staged_owner_releases_all_transport_artifacts_once():
    order = []
    plan = _TransportArtifact("plan", order)
    prepared = _TransportArtifact("prepared", order)
    committed = _TransportArtifact("committed", order)
    inner = _TransportArtifact("inner", order)
    owner = fs._StagedTransportOwner(plan, prepared, committed, inner)

    owner.close()
    owner.close()

    assert all(artifact.close_calls == 1
               for artifact in (plan, prepared, committed, inner))
