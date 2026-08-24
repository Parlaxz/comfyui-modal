"""Fallback semantics: a fallback can NEVER be ACCEPTED_NOMINAL."""

from __future__ import annotations

import pytest

from comfymodal_runtime.golden.contracts import DegradationRecord, DegradedReason, GoldenError, RuntimeStatus
from comfymodal_runtime.golden.pipeline import assert_fallback_never_nominal, classify_hard_failure, final_status


def test_classify_hard_failure_shape():
    rec = classify_hard_failure(RuntimeError("qd exploded"))
    assert rec.reason == DegradedReason.QD_HARD_FAILURE_FALLBACK
    assert rec.fallback_used is True
    assert "RuntimeError" in rec.detail["exception_type"]


def test_final_status_mappings():
    assert final_status(True, None) == RuntimeStatus.ACCEPTED_NOMINAL
    assert final_status(False, None) == RuntimeStatus.FAILED
    assert final_status(True, DegradationRecord(reason=DegradedReason.QD_HARD_FAILURE_FALLBACK)) == RuntimeStatus.DEGRADED
    assert final_status(False, DegradationRecord(reason=DegradedReason.BIND_VALIDATION_FAILED)) == RuntimeStatus.DEGRADED


def test_fallback_never_nominal_guard():
    degradation = DegradationRecord(reason=DegradedReason.QD_HARD_FAILURE_FALLBACK)
    with pytest.raises(GoldenError, match="ACCEPTED_NOMINAL"):
        assert_fallback_never_nominal(degradation)
    assert_fallback_never_nominal(None)


def test_qd_hard_failure_maps_to_degraded_not_nominal(tmp_path, monkeypatch):
    from comfymodal_runtime.golden import qd_engine
    from comfymodal_runtime.golden.contracts import DestinationKind, GoldenQDFailure, ModelRole
    from comfymodal_runtime.golden.qd_engine import CpuCopyBackend, GoldenQD4Loader, QD4EngineConfig

    from conftest import build_manifest, contiguous_destination, write_safetensors

    path = write_safetensors(tmp_path / "ok.safetensors", [("w", "F32", (16, 16))])
    manifest = build_manifest(path, ModelRole.CLIP, 4096, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    monkeypatch.setattr(qd_engine._BlockReader, "read_into", lambda self, off, mv, exp: 0)
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    with pytest.raises(GoldenQDFailure) as excinfo:
        loader.load(manifest, contiguous_destination(manifest))
    status = final_status(False, classify_hard_failure(excinfo.value))
    assert status == RuntimeStatus.DEGRADED
