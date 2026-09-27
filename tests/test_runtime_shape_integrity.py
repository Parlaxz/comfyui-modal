from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from comfymodal_runtime import runtime_shape
from comfymodal_runtime.cpu_snapshot_models import snapshot_construction_order
from tools.benchmark_v2_direct import _runtime_shape_guard


_ENV_KEYS = (
    "COMFYMODAL_V2_THREAD_POLICY",
    "COMFYMODAL_V2_TORCH_INTRAOP_THREADS",
    "COMFYMODAL_V2_TORCH_INTEROP_THREADS",
    "COMFYMODAL_V2_NATIVE_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "MALLOC_ARENA_MAX",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER",
    "COMFYMODAL_V2_CPU_REQUEST",
    "COMFYMODAL_V2_MEMORY_REQUEST",
    "COMFYMODAL_V2_MEMORY_MB",
    "COMFYMODAL_V2_RUNTIME_SHAPE_ID",
    "COMFYMODAL_V2_RUNTIME_SHAPE_LABEL",
    "COMFYMODAL_V2_RESTORE_TORCH_THREADS",
)


@pytest.fixture(autouse=True)
def clean_runtime_shape_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    runtime_shape._TORCH_POLICY_APPLIED = None


def test_tbase_is_pass_through_and_keeps_native_settings_out_of_environment() -> None:
    config = runtime_shape.runtime_shape_config()
    assert config.thread_policy == "TBASE"
    assert config.snapshot_model_order == "O0"
    assert config.memory_request == 8192
    assert config.torch_intraop_threads is None
    assert config.torch_interop_threads is None
    assert config.environment() == {
        "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
        "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
        "COMFYMODAL_V2_CPU_REQUEST": "16",
        "COMFYMODAL_V2_MEMORY_REQUEST": "8192",
        "COMFYMODAL_V2_MEMORY_MB": "8192",
        "COMFYMODAL_V2_RUNTIME_SHAPE_FINGERPRINT": config.runtime_shape_fingerprint,
    }


def test_tbase_application_only_observes(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTorch:
        def get_num_threads(self) -> int:
            return 7

        def get_num_interop_threads(self) -> int:
            return 3

        def set_num_threads(self, value: int) -> None:
            raise AssertionError(f"TBASE attempted to set intraop={value}")

        def set_num_interop_threads(self, value: int) -> None:
            raise AssertionError(f"TBASE attempted to set interop={value}")

    monkeypatch.setitem(sys.modules, "torch", FakeTorch())
    observed = runtime_shape.apply_torch_thread_policy(stage="snapshot", enforce=True)
    assert observed["status"] == "baseline_passthrough"
    assert observed["torch_intraop_threads"] == 7
    assert observed["torch_interop_threads"] == 3


def test_active_policy_is_explicit_and_fingerprint_is_not_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_THREAD_POLICY", "T1")
    monkeypatch.setenv("COMFYMODAL_V2_RUNTIME_SHAPE_LABEL", "thread-winner")
    config = runtime_shape.runtime_shape_config()
    assert config.torch_intraop_threads == 12
    assert config.torch_interop_threads == 4
    assert config.environment()["OMP_NUM_THREADS"] == "12"
    assert config.runtime_shape_label == "thread-winner"
    first_fingerprint = config.runtime_shape_fingerprint
    monkeypatch.delenv("COMFYMODAL_V2_RUNTIME_SHAPE_LABEL")
    assert runtime_shape.runtime_shape_config().runtime_shape_fingerprint == first_fingerprint


def test_conflicting_memory_aliases_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_MEMORY_REQUEST", "40960")
    monkeypatch.setenv("COMFYMODAL_V2_MEMORY_MB", "49152")
    with pytest.raises(RuntimeError, match="conflict"):
        runtime_shape.runtime_shape_config()


def test_manual_runtime_shape_id_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_RUNTIME_SHAPE_ID", "reused")
    with pytest.raises(RuntimeError, match="RUNTIME_SHAPE_LABEL"):
        runtime_shape.runtime_shape_config()


def test_thread_application_emits_event_and_restore_validation_does_not_reapply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_THREAD_POLICY", "T1")

    class FakeTorch:
        def __init__(self) -> None:
            self.intraop = 2
            self.interop = 2
            self.set_calls: list[tuple[str, int]] = []

        def get_num_threads(self) -> int:
            return self.intraop

        def get_num_interop_threads(self) -> int:
            return self.interop

        def set_num_threads(self, value: int) -> None:
            self.set_calls.append(("intraop", value))
            self.intraop = value

        def set_num_interop_threads(self, value: int) -> None:
            self.set_calls.append(("interop", value))
            self.interop = value

    fake_torch = FakeTorch()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    events: list[dict] = []
    trace = SimpleNamespace(
        emit=lambda name, phase, metadata: events.append(
            {"name": name, "phase": phase, "metadata": metadata}
        )
    )
    applied = runtime_shape.apply_torch_thread_policy(
        stage="snapshot", trace=trace, enforce=True
    )
    assert applied["status"] == "applied"
    assert applied["requested_vs_actual_match"] is True
    assert events[-1]["name"] == "runtime_shape_observed"
    calls_before_validation = list(fake_torch.set_calls)
    fake_torch.intraop = 2
    with pytest.raises(RuntimeError, match="mismatch"):
        runtime_shape.validate_torch_thread_policy(
            stage="after_restore", trace=trace, enforce=True
        )
    assert fake_torch.set_calls == calls_before_validation


def test_snapshot_orders_are_explicit() -> None:
    assert snapshot_construction_order("O0") == ("clip", "unet", "vae")
    assert snapshot_construction_order("O1") == ("unet", "vae", "clip")
    assert snapshot_construction_order("O2") == ("unet", "clip", "vae")
    assert snapshot_construction_order("O3") == ("clip", "vae", "unet")
    with pytest.raises(RuntimeError, match="unsupported"):
        snapshot_construction_order("O9")


def test_benchmark_guard_rejects_multiple_changed_axes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_BASELINE_CPU_REQUEST", "16")
    monkeypatch.setenv("COMFYMODAL_V2_BASELINE_MEMORY_REQUEST", "49152")
    with pytest.raises(RuntimeError, match="multiple axes"):
        _runtime_shape_guard({
            "thread_policy": "T1",
            "snapshot_model_order": "O1",
            "cpu_request": 16,
            "memory_request": 49152,
        })


def test_benchmark_guard_allows_explicit_multi_axis_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_ALLOW_MULTI_AXIS", "1")
    guard = _runtime_shape_guard({
        "thread_policy": "T1",
        "snapshot_model_order": "O1",
        "cpu_request": 16,
        "memory_request": 49152,
    })
    assert guard["changed_axes"] == ["thread_policy", "snapshot_model_order"]
    assert guard["allow_multi_axis"] is True
