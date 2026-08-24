"""R44H3 guards for bounded nominal CLIP validation."""
from __future__ import annotations

import inspect

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import request_clip_fastsafe as rcfs


def test_nominal_validator_has_no_full_tensor_cpu_proof(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_CLIP_CAST_ONCE_DEEP_VALIDATION", raising=False)
    source = inspect.getsource(rcfs._validate_cast_once_bind)
    assert "_bounded_sample_cpu" in source
    assert "validation_mode == _VALIDATION_MODE_DEEP" in source
    assert rcfs._cast_once_validation_mode() == rcfs._VALIDATION_MODE_BOUNDED


def test_bounded_sample_cpu_is_element_bounded():
    tensor = torch.arange(1024 * 1024, dtype=torch.bfloat16).reshape(1024, 1024)
    sample, count = rcfs._bounded_sample_cpu(tensor, 7)
    assert count <= 7
    assert sample.numel() == count
    assert sample.device.type == "cpu"
    assert count * tensor.element_size() <= 7 * tensor.element_size()


def test_deep_validation_is_explicit_diagnostic_only(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_CLIP_CAST_ONCE_DEEP_VALIDATION", "1")
    assert rcfs._cast_once_validation_mode() == rcfs._VALIDATION_MODE_DEEP
    monkeypatch.delenv("COMFYMODAL_CLIP_CAST_ONCE_DEEP_VALIDATION")
    assert rcfs._cast_once_validation_mode() == rcfs._VALIDATION_MODE_BOUNDED
