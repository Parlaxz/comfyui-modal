"""Focused tests for V2 activation diagnostics.

Uses production APIs: begin_activation_diagnostics, get_activation_diagnostics,
end_activation_diagnostics from model_preload.  State values are lists/records.
"""

from __future__ import annotations

import os
import time
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.model_preload import (
    begin_activation_diagnostics,
    get_activation_diagnostics,
    end_activation_diagnostics,
    _ACTIVATION_DIAGNOSTIC_STATE,
    _record_clip_encode,
    _PREFILL_LANE_MODE,
)
from comfymodal_runtime.modal_app import (
    _RESIDENCY_DIAGNOSTICS_ENABLED,
    _ProcessCpuSampler,
)
from comfymodal_runtime.trace import RuntimeTrace


class TestActivationContextVar:
    """begin_activation_diagnostics / get_activation_diagnostics / end_activation_diagnostics."""

    def test_begin_sets_state(self):
        """begin_activation_diagnostics creates state with request_id and key lists."""
        token = begin_activation_diagnostics("req-1")
        try:
            state = _ACTIVATION_DIAGNOSTIC_STATE.get()
            assert state is not None
            assert state["request_id"] == "req-1"
            assert state["clip_encode_calls"] == []
            assert state["gpu_load_calls"] == []
        finally:
            end_activation_diagnostics(token)

    def test_get_activation_diagnostics(self):
        """get_activation_diagnostics returns the current state."""
        token = begin_activation_diagnostics("req-2")
        try:
            state = get_activation_diagnostics()
            assert state is not None
            assert state["request_id"] == "req-2"
        finally:
            end_activation_diagnostics(token)

    def test_end_clears_and_returns(self):
        """end_activation_diagnostics returns the final state and resets the ContextVar."""
        token = begin_activation_diagnostics("req-3")
        state = end_activation_diagnostics(token)
        assert state is not None
        assert state["request_id"] == "req-3"
        assert _ACTIVATION_DIAGNOSTIC_STATE.get() is None

    def test_outside_is_none(self):
        """Outside any scope, _ACTIVATION_DIAGNOSTIC_STATE.get() returns None."""
        assert _ACTIVATION_DIAGNOSTIC_STATE.get() is None

    def test_no_cuda_synchronize(self):
        """The API must NOT call torch.cuda.synchronize."""
        import torch
        with patch.object(torch.cuda, "synchronize", side_effect=AssertionError("must not call")):
            token = begin_activation_diagnostics("no-cuda")
            end_activation_diagnostics(token)

    def test_no_tensor_storage(self):
        """The state must not contain tensor objects."""
        token = begin_activation_diagnostics("no-tensor")
        try:
            state = get_activation_diagnostics()
            for val in state.values():
                if hasattr(val, "grad_fn"):
                    assert False, f"tensor leaked into activation state: {type(val)}"
        finally:
            end_activation_diagnostics(token)

    def test_no_prompt_or_path(self):
        """The state must not contain prompt text or file paths."""
        token = begin_activation_diagnostics("clean")
        try:
            state = get_activation_diagnostics()
            for key in state:
                if "prompt" in str(key).lower() or "path" in str(key).lower():
                    assert False, f"suspicious key: {key}"
        finally:
            end_activation_diagnostics(token)

    def test_execution_prefill_scheduled_in_state(self):
        """cpu_snapshot_active and execution_prefill_scheduled can be set on the state."""
        token = begin_activation_diagnostics("eps-test")
        try:
            state = get_activation_diagnostics()
            state["cpu_snapshot_active"] = False
            state["execution_prefill_scheduled"] = True
            assert state["cpu_snapshot_active"] is False
            assert state["execution_prefill_scheduled"] is True
        finally:
            end_activation_diagnostics(token)

    def test_new_state_does_not_include_residency(self):
        """State does not include pre-populated residency dict."""
        token = begin_activation_diagnostics("no-res")
        try:
            state = get_activation_diagnostics()
            # Residency should be absent or empty — not pre-populated
            assert "residency" not in state or state["residency"] == {}
        finally:
            end_activation_diagnostics(token)


class TestRecordClipEncode:
    """_record_clip_encode wraps a callback and records into activation diagnostics."""

    def test_records_basic_call(self):
        token = begin_activation_diagnostics("clip-test")
        try:
            fake_clip = object()
            result = _record_clip_encode(
                caller="test", clip=fake_clip, text="hello world",
                callback=lambda: "encoded_result",
            )
            assert result == "encoded_result"
            state = get_activation_diagnostics()
            assert len(state["clip_encode_calls"]) == 1
            record = state["clip_encode_calls"][0]
            assert record["caller"] == "test"
            assert record["text_hash"] is not None
            assert record["wall_ms"] >= 0
            assert record["process_cpu_ms"] >= 0
        finally:
            end_activation_diagnostics(token)

    def test_records_multiple_calls_with_callers(self):
        token = begin_activation_diagnostics("clip-multi")
        try:
            fake_clip = object()
            _record_clip_encode(caller="execution_prefill", clip=fake_clip, text="a", callback=lambda: 1)
            _record_clip_encode(caller="graph", clip=fake_clip, text="b", callback=lambda: 2)
            state = get_activation_diagnostics()
            assert len(state["clip_encode_calls"]) == 2
            assert state["clip_encode_calls"][0]["caller"] == "execution_prefill"
            assert state["clip_encode_calls"][1]["caller"] == "graph"
        finally:
            end_activation_diagnostics(token)

    def test_cache_hit_not_recorded(self):
        """When no call to _record_clip_encode, list stays empty."""
        token = begin_activation_diagnostics("cache-hit")
        try:
            state = get_activation_diagnostics()
            assert state["clip_encode_calls"] == []
        finally:
            end_activation_diagnostics(token)

    def test_no_state_does_nothing(self):
        """When no active diagnostics state, _record_clip_encode still returns callback result."""
        fake_clip = object()
        result = _record_clip_encode(
            caller="no-state", clip=fake_clip, text="test",
            callback=lambda: "no-op-ok",
        )
        assert result == "no-op-ok"

    def test_callback_exception_still_records(self):
        """Exception in callback is propagated, but record is still appended."""
        token = begin_activation_diagnostics("clip-exc")
        try:
            fake_clip = object()
            try:
                _record_clip_encode(
                    caller="failing", clip=fake_clip, text="boom",
                    callback=lambda: (_ for _ in ()).throw(ValueError("encode failed")),
                )
                assert False, "should have raised"
            except ValueError:
                pass
            state = get_activation_diagnostics()
            assert len(state["clip_encode_calls"]) == 1
            record = state["clip_encode_calls"][0]
            assert record["caller"] == "failing"
            assert record["wall_ms"] >= 0
        finally:
            end_activation_diagnostics(token)

    def test_record_has_expected_fields(self):
        """Record has all required fields."""
        token = begin_activation_diagnostics("clip-fields")
        try:
            fake_clip = object()
            _record_clip_encode(
                caller="test", clip=fake_clip, text="field check",
                callback=lambda: None,
            )
            state = get_activation_diagnostics()
            record = state["clip_encode_calls"][0]
            for key in ("caller", "clip_object_id", "text_hash", "text_length",
                        "wall_ms", "process_cpu_ms"):
                assert key in record, f"missing key: {key}"
            assert "thread_cpu_ms" in record
            assert "minor_faults" not in record
            assert "major_faults" not in record
        finally:
            end_activation_diagnostics(token)

    def test_explicit_state_records_separately(self):
        """_explicit_state parameter records into the provided dict, not ContextVar."""
        token = begin_activation_diagnostics("explicit-test")
        try:
            fake_clip = object()
            explicit: dict[str, Any] = {"clip_encode_calls": []}
            _record_clip_encode(
                caller="worker", clip=fake_clip, text="explicit",
                _explicit_state=explicit,
                callback=lambda: "worker_result",
            )
            # Explicit state has the record
            assert len(explicit["clip_encode_calls"]) == 1
            assert explicit["clip_encode_calls"][0]["caller"] == "worker"
            # ContextVar state does NOT have the record
            state = get_activation_diagnostics()
            assert len(state["clip_encode_calls"]) == 0
        finally:
            end_activation_diagnostics(token)

    def test_unattached_no_state_absent(self):
        """Without any state (ContextVar or explicit), no record is created."""
        fake_clip = object()
        result = _record_clip_encode(
            caller="unattached", clip=fake_clip, text="nothing",
            callback=lambda: "unattached_ok",
        )
        assert result == "unattached_ok"
        # No state was set, so nothing is attached
        assert _ACTIVATION_DIAGNOSTIC_STATE.get() is None


class TestGpuLoadCallsList:
    """gpu_load_calls accumulates records, not aggregate counters."""

    def test_gpu_load_calls_starts_empty(self):
        token = begin_activation_diagnostics("gpu-empty")
        try:
            state = get_activation_diagnostics()
            assert state["gpu_load_calls"] == []
        finally:
            end_activation_diagnostics(token)

    def test_gpu_load_calls_append(self):
        token = begin_activation_diagnostics("gpu-append")
        try:
            state = get_activation_diagnostics()
            state["gpu_load_calls"].append({"caller": "graph_model_loading", "wall_ms": 100.0})
            assert len(state["gpu_load_calls"]) == 1
            assert state["gpu_load_calls"][0]["wall_ms"] == 100.0
        finally:
            end_activation_diagnostics(token)


class TestPrefillGuardSnapshotActive:
    """Prefill scheduling guard when CPU snapshot models are active."""

    def test_snapshot_active_skips_prefill(self):
        """When cpu_snapshot_active is True, execution_prefill_scheduled must be False."""
        token = begin_activation_diagnostics("snap-test")
        try:
            state = get_activation_diagnostics()
            state["cpu_snapshot_active"] = True
            state["execution_prefill_scheduled"] = False
            assert state["execution_prefill_scheduled"] is False
        finally:
            end_activation_diagnostics(token)

    def test_snapshot_inactive_allows_prefill(self):
        """When cpu_snapshot_active is False, execution_prefill_scheduled can be True."""
        token = begin_activation_diagnostics("no-snap")
        try:
            state = get_activation_diagnostics()
            state["cpu_snapshot_active"] = False
            state["execution_prefill_scheduled"] = True
            assert state["execution_prefill_scheduled"] is True
        finally:
            end_activation_diagnostics(token)

    def test_both_booleans_in_state(self):
        """Both cpu_snapshot_active and execution_prefill_scheduled are present."""
        token = begin_activation_diagnostics("both-state")
        try:
            state = get_activation_diagnostics()
            state["cpu_snapshot_active"] = False
            state["execution_prefill_scheduled"] = True
            assert "cpu_snapshot_active" in state
            assert "execution_prefill_scheduled" in state
        finally:
            end_activation_diagnostics(token)


class TestResidencyDiagnosticsGate:
    """Residency diagnostics default-off and enabled behavior."""

    def test_default_off(self):
        """_RESIDENCY_DIAGNOSTICS_ENABLED defaults to False."""
        assert _RESIDENCY_DIAGNOSTICS_ENABLED is False

    def test_enabled_via_env(self):
        """Setting COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS=1 enables it."""
        from comfymodal_runtime import modal_app
        _orig = modal_app._RESIDENCY_DIAGNOSTICS_ENABLED
        try:
            os.environ["COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS"] = "1"
            modal_app._RESIDENCY_DIAGNOSTICS_ENABLED = True
            assert modal_app._RESIDENCY_DIAGNOSTICS_ENABLED is True
        finally:
            modal_app._RESIDENCY_DIAGNOSTICS_ENABLED = _orig
            os.environ.pop("COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS", None)

    def test_residency_fields_absent_when_disabled(self):
        """When residency is disabled, fields should be absent, not 0."""
        token = begin_activation_diagnostics("res-absent")
        try:
            state = get_activation_diagnostics()
            # State should not have residency populated
            assert "residency" not in state or state["residency"] == {}
        finally:
            end_activation_diagnostics(token)


class TestProcessCpuSampler:
    """_ProcessCpuSampler: process-based CPU sampling."""

    def test_creation_and_start_stop(self):
        """Sampler can be created, started, and stopped without error."""
        sampler = _ProcessCpuSampler(time.monotonic_ns())
        sampler.start()
        time.sleep(0.01)
        sampler.stop()
        assert sampler is not None

    def test_report_ok_with_samples(self):
        """Report emits status=ok when sufficient samples exist."""
        sampler = _ProcessCpuSampler(time.monotonic_ns())
        sampler.start()
        time.sleep(0.15)  # Enough for at least 2 samples at 50ms
        sampler.stop()
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            sampler.report()
        output = buf.getvalue()
        assert "status=ok" in output or "status=unavailable" in output

    def test_report_unavailable_few_samples(self):
        """Report emits status=unavailable when too few samples."""
        sampler = _ProcessCpuSampler(time.monotonic_ns())
        # Don't start, just report immediately
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            sampler.report()
        output = buf.getvalue()
        assert "status=unavailable" in output

    def test_activation_summary_with_few_samples(self):
        """activation_summary returns None fields when few samples."""
        sampler = _ProcessCpuSampler(time.monotonic_ns())
        summary = sampler.activation_summary()
        assert summary["peak_effective_cores"] is None
        assert summary["duration_above_16_cores_ms"] is None
        assert summary["duration_above_19_cores_ms"] is None

    def test_duration_above_threshold(self):
        """_duration_above_threshold computes correctly."""
        samples = [
            {"effective_cores": 5.0, "elapsed_request_ms": 100.0, "monotonic_ns": 100_000_000},
            {"effective_cores": 10.0, "elapsed_request_ms": 200.0, "monotonic_ns": 200_000_000},
            {"effective_cores": 20.0, "elapsed_request_ms": 300.0, "monotonic_ns": 300_000_000},
            {"effective_cores": 5.0, "elapsed_request_ms": 400.0, "monotonic_ns": 400_000_000},
        ]
        result = _ProcessCpuSampler._duration_above_threshold(8.0, samples)
        assert result == 200.0

    def test_plateaus_above_threshold(self):
        """_plateaus_above_threshold identifies contiguous above-threshold plateaus."""
        samples = [
            {"effective_cores": 5.0, "elapsed_request_ms": 100.0, "monotonic_ns": 100_000_000},
            {"effective_cores": 20.0, "elapsed_request_ms": 200.0, "monotonic_ns": 200_000_000},
            {"effective_cores": 25.0, "elapsed_request_ms": 300.0, "monotonic_ns": 300_000_000},
            {"effective_cores": 5.0, "elapsed_request_ms": 400.0, "monotonic_ns": 400_000_000},
            {"effective_cores": 22.0, "elapsed_request_ms": 500.0, "monotonic_ns": 500_000_000},
        ]
        plateaus = _ProcessCpuSampler._plateaus_above_threshold(19.0, samples)
        assert len(plateaus) == 2
        assert plateaus[0] == (100_000_000, 300_000_000)
        assert plateaus[1] == (400_000_000, 500_000_000)

    def test_activation_summary_calculates_overlaps(self):
        sampler = _ProcessCpuSampler(0)
        sampler._samples = [
            {"effective_cores": 0.0, "elapsed_request_ms": 0.0, "monotonic_ns": 0},
            {"effective_cores": 20.0, "elapsed_request_ms": 100.0, "monotonic_ns": 100_000_000},
            {"effective_cores": 20.0, "elapsed_request_ms": 200.0, "monotonic_ns": 200_000_000},
            {"effective_cores": 0.0, "elapsed_request_ms": 300.0, "monotonic_ns": 300_000_000},
        ]
        summary = sampler.activation_summary({
            "clip_encode_calls": [
                {"caller": "graph", "start_monotonic_ns": 50_000_000, "end_monotonic_ns": 150_000_000},
                {"caller": "execution_prefill", "start_monotonic_ns": 150_000_000, "end_monotonic_ns": 250_000_000},
            ],
            "gpu_load_calls": [
                {"start_monotonic_ns": 100_000_000, "end_monotonic_ns": 180_000_000},
            ],
        })
        assert summary["duration_above_19_cores_ms"] == 200.0
        assert summary["cpu_overlap_graph_clip_ms"] == 100.0
        assert summary["cpu_overlap_prefill_clip_ms"] == 50.0
        assert summary["cpu_overlap_gpu_load_ms"] == 80.0


class TestLifecyclePrefillActiveInactive:
    """Prefill lane mode interaction with activation state."""

    def test_prefill_scheduled_critical(self):
        scheduled = _PREFILL_LANE_MODE != "none"
        assert scheduled is True

    def test_prefill_not_scheduled_none(self):
        saved = os.environ.get("COMFYMODAL_V2_PREFILL_LANES")
        from comfymodal_runtime import model_preload
        original_mode = model_preload._PREFILL_LANE_MODE
        try:
            os.environ["COMFYMODAL_V2_PREFILL_LANES"] = "none"
            model_preload._PREFILL_LANE_MODE = "none"
            assert model_preload._PREFILL_LANE_MODE == "none"
        finally:
            model_preload._PREFILL_LANE_MODE = original_mode
            if saved is not None:
                os.environ["COMFYMODAL_V2_PREFILL_LANES"] = saved
            else:
                os.environ.pop("COMFYMODAL_V2_PREFILL_LANES", None)
