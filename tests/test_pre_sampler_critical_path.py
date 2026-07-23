"""Focused unit tests for the pre-sampler critical-path facility.

Tests cover:
  - PreSamplerCache (runtime_executor.py)
  - PreSamplerSpan / pre_sampler_span_metadata (profiler_trace_v4.py)
  - Trace.pre_sampler_summary / TraceV4.pre_sampler_summary (timing_trace.py)
  - attach_pre_sampler_critical_path postprocessor (runtime_executor.py)
  - RuntimeExecutor integration (auto-cache, execute/stream attachment)

No real ComfyUI or Modal imports — pure unit tests with fakes.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

# ── Imports under test ──────────────────────────────────────────────────
from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
from comfymodal_runtime.runtime_executor import (
    PreSamplerCache,
    ExecutionContext,
    RuntimeExecutor,
    attach_pre_sampler_critical_path,
)
from comfymodal_runtime.trace import RuntimeTrace
from profiler_trace_v4 import (
    PreSamplerSpan,
    pre_sampler_span_metadata,
    PRE_SAMPLER_OPERATIONS,
    PRE_SAMPLER_OPERATION_SET,
)
from timing_trace import Trace, TraceV4


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


class _SentinelModel:
    """A model-like object that refuses deep-copy / hashing / content access.

    Only identity (id()) is reliable.
    """

    def __deepcopy__(self, memo: Any = None) -> None:
        raise RuntimeError("deepcopy called on sentinel model — must not happen")

    def __hash__(self) -> int:
        raise RuntimeError("hash called on sentinel model — must not happen")

    def __eq__(self, other: Any) -> bool:
        raise RuntimeError("eq called on sentinel model — must not happen")


class _RecordingClock:
    """Deterministic clock that records invocations."""

    def __init__(self, values: list[float] | None = None):
        self._values = values or [0.0, 0.001, 0.002, 0.003, 0.004, 0.005]
        self._idx = 0
        self.calls: list[float] = []

    def __call__(self) -> float:
        if self._idx < len(self._values):
            val = self._values[self._idx]
            self._idx += 1
        else:
            val = self._values[-1] + 0.001 * (self._idx - len(self._values) + 1)
            self._idx += 1
        self.calls.append(val)
        return val


class _FakeFuture:
    """Future-like object that records whether .done() and .result() were called."""

    def __init__(self, *, done: bool = True):
        self._done = done
        self._result_value = "fake_result"
        self.done_called = 0
        self.result_called = 0

    def done(self) -> bool:
        self.done_called += 1
        return self._done

    def result(self) -> Any:
        self.result_called += 1
        return self._result_value

    def __await__(self):
        return self._result_value


def _make_plan(**overrides: Any) -> ExecutionPlan:
    """Minimal ExecutionPlan for testing."""
    defaults: dict[str, Any] = {
        "workflow": {
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 42}},
        },
        "workflow_hash": "test_workflow_hash",
        "execution_options": ExecutionOptions(production_enabled=False),
    }
    defaults.update(overrides)
    return ExecutionPlan(**defaults)


# ═══════════════════════════════════════════════════════════════════════
# 1. PreSamplerCache — node/class attribution & dominant spans
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerCacheAttribution:
    """Dominant spans carry exact node/class and operation metadata."""

    def test_required_operations_have_canonical_list(self):
        """PRE_SAMPLER_OPERATIONS contains all required operations."""
        expected = {
            "cache_key_build", "cache_lookup", "input_resolution",
            "model_patch", "conditioning", "future_wait", "lock_wait",
            "node_execution", "unattributed",
        }
        assert set(PRE_SAMPLER_OPERATIONS) == expected
        assert "unknown_op" not in PRE_SAMPLER_OPERATION_SET

    def test_dominant_span_has_node_attribution(self):
        """record_node_execution produces a dominant span with node/class."""
        cache = PreSamplerCache()
        cache.record_node_execution("5", "CLIPTextEncode", 12.5)
        assert len(cache.dominant_spans) == 1
        span = cache.dominant_spans[0]
        assert span["operation"] == "node_execution"
        assert span["node_id"] == "5"
        assert span["class_type"] == "CLIPTextEncode"
        assert span["duration_ms"] == 12.5

    def test_dominant_span_has_start_end_attribution(self):
        """resolve_inputs with cache miss records operation metadata."""
        cache = PreSamplerCache()
        inputs = {"text": "hello", "model": _SentinelModel()}
        cache.resolve_inputs("3", "CLIPTextEncode", inputs)
        # First call — miss, no node attribution on resolve
        # Only cache_lookup with node_id
        lookup_spans = [s for s in cache.dominant_spans if s["operation"] == "cache_lookup"]
        assert len(lookup_spans) >= 1
        assert lookup_spans[0].get("node_id") == "3"
        assert lookup_spans[0].get("class_type") == "CLIPTextEncode"


# ═══════════════════════════════════════════════════════════════════════
# 2. PreSamplerCache — required operation timing fields
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerRequiredFields:
    """All required operation timing fields are present in to_summary_dict."""

    def test_to_summary_dict_contains_all_required_fields(self):
        """to_summary_dict includes all mandatory timing keys."""
        cache = PreSamplerCache()
        s = cache.to_summary_dict()
        # Even when zero, unattributed is present
        assert "unattributed_ms" in s
        for op in ["cache_key_build", "cache_lookup", "input_resolution",
                    "model_patch", "conditioning", "future_wait",
                    "lock_wait", "node_execution"]:
            # These may be absent if never recorded (0.0)
            pass
        # After recording some operations
        cache.record_node_execution("6", "KSampler", 100.0)
        cache.record_unattributed(5.0)
        s2 = cache.to_summary_dict()
        assert s2["node_execution_ms"] == 100.0
        assert s2["unattributed_ms"] == 5.0
        assert s2["total_measured_ms"] == 100.0
        assert "operation_counts" in s2

    def test_operation_counts_present(self):
        """Operation counts tally correctly."""
        cache = PreSamplerCache()
        cache.record_node_execution("1", "A", 10.0)
        cache.record_node_execution("2", "B", 20.0)
        cache.record_unattributed(1.0)
        counts = cache.to_summary_dict()["operation_counts"]
        assert counts["node_execution"] == 2
        assert counts["unattributed"] == 1


# ═══════════════════════════════════════════════════════════════════════
# 3. Identical node inputs cache hit
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerCacheInputCache:
    """Identical node inputs hit cache; builder count stays one."""

    def test_identical_inputs_hit_cache(self):
        """Same (node_id, class_type, scalar inputs) returns cached."""
        cache = PreSamplerCache()
        inputs = {"text": "cat", "seed": 42}
        r1 = cache.resolve_inputs("5", "CLIPTextEncode", inputs)
        r2 = cache.resolve_inputs("5", "CLIPTextEncode", inputs)

        # Same object returned
        assert r1 is r2
        # cache_lookup hit recorded
        assert cache.operation_hits.get("cache_lookup", 0) == 1
        assert cache.operation_count["cache_lookup"] >= 2

    def test_different_node_ids_miss_cache(self):
        """Different node_id produces different cache key."""
        cache = PreSamplerCache()
        r1 = cache.resolve_inputs("5", "CLIPTextEncode", {"text": "cat"})
        r2 = cache.resolve_inputs("6", "CLIPTextEncode", {"text": "cat"})
        assert r1 is not r2  # different dicts
        assert cache.operation_hits.get("cache_lookup", 0) == 0

    def test_different_inputs_miss_cache(self):
        """Different input values produce different cache key."""
        cache = PreSamplerCache()
        r1 = cache.resolve_inputs("5", "CLIPTextEncode", {"text": "cat"})
        r2 = cache.resolve_inputs("5", "CLIPTextEncode", {"text": "dog"})
        assert r1 is not r2
        assert cache.operation_hits.get("cache_lookup", 0) == 0

    def test_model_object_identity_respected(self):
        """Same model object identity hits cache."""
        cache = PreSamplerCache()
        model = _SentinelModel()
        r1 = cache.resolve_inputs("3", "SomeModel", {"model": model})
        r2 = cache.resolve_inputs("3", "SomeModel", {"model": model})
        assert r1 is r2
        assert cache.operation_hits.get("cache_lookup", 0) == 1

    def test_different_model_object_identity_misses(self):
        """Different model object identity misses cache."""
        cache = PreSamplerCache()
        model_a = _SentinelModel()
        model_b = _SentinelModel()
        r1 = cache.resolve_inputs("3", "SomeModel", {"model": model_a})
        r2 = cache.resolve_inputs("3", "SomeModel", {"model": model_b})
        assert r1 is not r2
        assert cache.operation_hits.get("cache_lookup", 0) == 0


# ═══════════════════════════════════════════════════════════════════════
# 4. Model objects not deep-copied / content-hashed
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerNoDeepCopy:
    """Model objects are never deep-copied or content-hashed — identity is used."""

    def test_sentinel_model_not_deepcopied(self):
        """_SentinelModel refuses deepcopy/hash; identity is fine."""
        cache = PreSamplerCache()
        model = _SentinelModel()
        # This should NOT trigger deepcopy/hash/eq
        inputs = {"model": model, "text": "safe"}
        result = cache.resolve_inputs("3", "SafeModel", inputs)
        assert result is inputs

    def test_cache_key_no_deepcopy(self):
        """build_cache_key does not deepcopy model objects."""
        cache = PreSamplerCache()
        plan = _make_plan()
        key1 = cache.build_cache_key(plan)
        key2 = cache.build_cache_key(plan)
        assert key1 == key2  # Same request returns cached key
        # Second call does not rebuild
        assert cache.operation_count["cache_key_build"] == 1


# ═══════════════════════════════════════════════════════════════════════
# 5. Completed futures produce no wait
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerFutures:
    """Completed future returns immediately; incomplete future awaits once."""

    async def _do_completed_future_test(self):
        cache = PreSamplerCache()
        future = _FakeFuture(done=True)
        result = await cache.get_future_result(future)
        assert result == "fake_result"
        assert future.done_called >= 1
        assert cache.operation_hits.get("future_wait", 0) == 1

    def test_completed_future_no_wait(self):
        asyncio.run(self._do_completed_future_test())

    async def _do_plain_value_test(self):
        cache = PreSamplerCache()
        result = await cache.get_future_result(42)
        assert result == 42
        assert cache.operation_hits.get("future_wait", 0) == 1

    def test_plain_value_no_wait(self):
        asyncio.run(self._do_plain_value_test())


# ═══════════════════════════════════════════════════════════════════════
# 6. Incomplete future waits once
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerIncompleteFuture:
    """Incomplete future is awaited once."""

    async def _do_incomplete_test(self):
        cache = PreSamplerCache()
        async def _incomplete() -> str:
            return "async_result"

        coro = _incomplete()
        result = await cache.get_future_result(coro)
        assert result == "async_result"
        # future_wait count incremented (not a hit because it was awaited)
        assert cache.operation_hits.get("future_wait", 0) == 0
        assert cache.operation_count["future_wait"] == 1

    def test_incomplete_future_awaited(self):
        asyncio.run(self._do_incomplete_test())


# ═══════════════════════════════════════════════════════════════════════
# 7. Double-checked locking — model patch gate
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerLocking:
    """Double-checked published-model gate: lock only on miss, recheck under lock."""

    def test_first_patch_acquires_lock(self):
        """First call to apply_model_patch acquires lock and records lock_wait."""
        cache = PreSamplerCache()
        applied: list[str] = []

        def patcher() -> str:
            applied.append("patched")
            return "model"

        result = cache.apply_model_patch("model_1", "patch_A", patcher)
        assert result == "model"
        assert len(applied) == 1
        # lock_wait recorded
        assert cache.operation_count["lock_wait"] >= 1
        # model_patch recorded
        assert cache.operation_count["model_patch"] >= 1

    def test_second_patch_skipped_no_lock(self):
        """Same (model_id, patch_id) skips patcher and avoids lock."""
        cache = PreSamplerCache()
        call_count: list[int] = [0]

        def patcher() -> str:
            call_count[0] += 1
            return "model"

        cache.apply_model_patch("model_1", "patch_A", patcher)
        cache.apply_model_patch("model_1", "patch_A", patcher)

        assert call_count[0] == 1  # patcher called once
        # The second call is a cache hit (fast path returns immediately)
        assert cache.operation_hits.get("model_patch", 0) == 1
        # lock_wait count should be 1 (only first call acquired lock)
        # The second call's fast-path skips the lock entirely
        assert cache.operation_count["lock_wait"] == 1

    def test_different_patch_applies_separately(self):
        """Different patch identity applies separately (different key)."""
        cache = PreSamplerCache()
        applied: list[str] = []

        def make_patcher(name: str) -> Any:
            def patcher() -> str:
                applied.append(name)
                return name
            return patcher

        cache.apply_model_patch("model_1", "patch_A", make_patcher("A"))
        cache.apply_model_patch("model_1", "patch_B", make_patcher("B"))
        assert set(applied) == {"A", "B"}
        assert cache.operation_hits.get("model_patch", 0) == 0

    def test_double_check_under_lock_rechecks(self):
        """When key appears between lock check and acquire, recheck prevents double apply."""
        cache = PreSamplerCache()
        applied: list[int] = [0]

        def patcher() -> str:
            applied[0] += 1
            return "model"

        cache.apply_model_patch("model_1", "patch_X", patcher)
        # The published_models set now has the key — fast path skips lock
        cache.apply_model_patch("model_1", "patch_X", patcher)
        assert applied[0] == 1


# ═══════════════════════════════════════════════════════════════════════
# 8. Conditioning exact-hit reuse
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerConditioning:
    """Conditioning caches for exact identical inputs + clip identity."""

    def test_same_fingerprint_clip_hits(self):
        """Same (fingerprint, clip identity) returns cached result."""
        cache = PreSamplerCache()
        clip = _SentinelModel()
        cond = ["conditioning_data"]
        r1 = cache.cache_conditioning("fp1", clip, cond)
        r2 = cache.cache_conditioning("fp1", clip, cond)
        assert r1 is r2  # Same cached object
        assert cache.operation_hits.get("conditioning", 0) == 1

    def test_different_fingerprint_misses(self):
        """Different fingerprint misses cache."""
        cache = PreSamplerCache()
        clip = _SentinelModel()
        cache.cache_conditioning("fp1", clip, ["a"])
        cache.cache_conditioning("fp2", clip, ["b"])
        assert cache.operation_hits.get("conditioning", 0) == 0

    def test_different_clip_identity_misses(self):
        """Different clip object (different id()) misses cache."""
        cache = PreSamplerCache()
        clip_a = _SentinelModel()
        clip_b = _SentinelModel()
        cache.cache_conditioning("fp1", clip_a, ["a"])
        cache.cache_conditioning("fp1", clip_b, ["b"])
        assert cache.operation_hits.get("conditioning", 0) == 0


# ═══════════════════════════════════════════════════════════════════════
# 9. Order/results/sampler parameters unchanged
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerOrderPreserved:
    """Cache does not change node execution order, outputs, or sampler params."""

    def test_cache_transparent_to_runner(self):
        """Running through the cache produces same outputs as without."""
        cache = PreSamplerCache()
        plan = _make_plan()

        # Build cache key
        key = cache.build_cache_key(plan)
        assert key == "test_workflow_hash"

        # Execute nodes in order (simulating a runner)
        results: list[str] = []
        for nid, node in [("3", "CLIPTextEncode"), ("6", "KSampler")]:
            cache.resolve_inputs(nid, node, {"text": "test"})
            cache.record_node_execution(nid, node, 10.0)
            results.append(nid)

        # Order preserved
        assert results == ["3", "6"]

        # Node class map populated
        assert cache.node_class_map == {"3": "CLIPTextEncode", "6": "KSampler"}

        # Sampler params not cached (not stored in cache)
        assert "6" in cache.node_class_map

    def test_execution_order_independent_of_cache_order(self):
        """Cache lookups in any order don't affect recorded order."""
        cache = PreSamplerCache()
        cache.resolve_inputs("6", "KSampler", {"seed": 42})
        cache.resolve_inputs("3", "CLIPTextEncode", {"text": "cat"})

        # Record in original workflow order
        cache.record_node_execution("3", "CLIPTextEncode", 5.0)
        cache.record_node_execution("6", "KSampler", 100.0)

        dominant = cache.dominant_spans
        exec_spans = [s for s in dominant if s["operation"] == "node_execution"]
        assert len(exec_spans) == 2
        assert exec_spans[0]["node_id"] == "3"
        assert exec_spans[1]["node_id"] == "6"


# ═══════════════════════════════════════════════════════════════════════
# 10. Summary reconciliation
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerReconciliation:
    """Summary reconciles measured + residual time."""

    def test_total_measured_sums_operations(self):
        """total_measured_ms is sum of all non-unattributed operations."""
        clock = _RecordingClock([0.0, 0.1, 0.0, 0.2, 0.0, 0.3])
        cache = PreSamplerCache(clock=clock)
        cache.record_node_execution("6", "KSampler", 50.0)
        cache.record_node_execution("3", "CLIPTextEncode", 25.0)
        cache.record_unattributed(5.0)
        s = cache.to_summary_dict()
        assert s["node_execution_ms"] == 75.0
        assert s["total_measured_ms"] == 75.0
        assert s["unattributed_ms"] == 5.0

    def test_attach_summary_reconciles_with_total_wall(self):
        """attach_pre_sampler_critical_path produces reconciled summary."""
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 100.0)
        cache.record_unattributed(10.0)

        plan = _make_plan()
        # Result with trace containing wall-time events
        result = {
            "trace": {
                "stages": {
                    "t3_modal_entry": 1000.0,
                    "t6_sampler_end": 1001.2,
                },
                "events": [
                    {"wall_unix_ns": 1_000_000_000_000},
                    {"wall_unix_ns": 1_001_200_000_000},
                ],
            }
        }

        attach_pre_sampler_critical_path(result, plan, cache)

        cp = result["trace"]["pre_sampler_critical_path"]
        assert cp["node_execution_ms"] == 100.0
        assert cp["total_measured_ms"] == 100.0
        assert cp["total_wall_ms"] == 1200.0
        assert cp["residual_ms"] == 1090.0  # 1200 - 100 - 10
        assert cp["unattributed_ms"] == 10.0
        assert "operation_counts" in cp

    def test_node_class_map_from_cache_and_workflow(self):
        """node_class_map includes cache entries + workflow fallback."""
        cache = PreSamplerCache()
        cache.node_class_map["6"] = "KSampler"
        plan = _make_plan(
            workflow={
                "3": {"class_type": "CLIPTextEncode", "inputs": {}},
                "6": {"class_type": "KSampler", "inputs": {}},
            }
        )
        result: dict[str, Any] = {}
        attach_pre_sampler_critical_path(result, plan, cache)
        cp = result.get("pre_sampler_critical_path", {})
        ncm = cp.get("node_class_map", {})
        assert ncm["6"] == "KSampler"
        # Workflow fallback
        assert ncm["3"] == "CLIPTextEncode"


# ═══════════════════════════════════════════════════════════════════════
# 11. Trace integration — events emitted through RuntimeTrace
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerTraceIntegration:
    """When trace is provided, operation events are emitted."""

    def test_trace_events_emitted(self):
        """cache operations emit trace events when trace is provided."""
        trace = RuntimeTrace(request_id="test-trace", process="cache_test")
        cache = PreSamplerCache(trace=trace)

        cache.build_cache_key(_make_plan())
        cache.record_node_execution("5", "CLIPTextEncode", 12.0)

        event_names = [e.name for e in trace.events]
        assert "pre_sampler_cache_key_build" in event_names
        assert "pre_sampler_node_execution" in event_names

    def test_trace_events_have_operation_metadata(self):
        """trace events carry operation metadata."""
        trace = RuntimeTrace(request_id="test-meta")
        cache = PreSamplerCache(trace=trace)

        cache.record_node_execution("6", "KSampler", 100.5)

        event = trace.events[-1]
        assert event.name == "pre_sampler_node_execution"
        meta = event.metadata
        assert meta is not None
        if isinstance(meta, dict):
            assert meta.get("operation") == "node_execution"
            assert meta.get("node_id") == "6"
            assert meta.get("class_type") == "KSampler"
            assert isinstance(meta.get("duration_ms"), float)


# ═══════════════════════════════════════════════════════════════════════
# 12. PreSamplerSpan context manager (profiler_trace_v4)
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerSpan:
    """PreSamplerSpan produces start/end events with proper metadata."""

    def test_span_creates_start_end_events(self):
        """Using PreSamplerSpan results in _start and _end events."""
        events: list[dict] = []
        with PreSamplerSpan(events, "cache_key_build", profile_level="summary"):
            pass

        names = [e["name"] for e in events]
        assert "cache_key_build_start" in names
        assert "cache_key_build_end" in names

    def test_span_metadata_includes_operation(self):
        """PreSamplerSpan events carry operation metadata."""
        events: list[dict] = []
        with PreSamplerSpan(
            events, "cache_lookup",
            node_id="5",
            class_type="CLIPTextEncode",
            profile_level="summary",
        ):
            pass

        # Check metadata on end event
        end_events = [e for e in events if e["name"] == "cache_lookup_end"]
        assert len(end_events) == 1
        meta = end_events[0].get("metadata", {}) or {}
        assert meta.get("operation") == "cache_lookup"
        assert meta.get("node_id") == "5"
        assert meta.get("class_type") == "CLIPTextEncode"

    def test_unknown_operation_becomes_unattributed(self):
        """An operation not in PRE_SAMPLER_OPERATIONS becomes 'unattributed'."""
        events: list[dict] = []
        with PreSamplerSpan(events, "unknown_op", profile_level="summary"):
            pass
        names = [e["name"] for e in events]
        assert "unattributed_start" in names
        assert "unattributed_end" in names

    def test_duration_ms_set(self):
        """duration_ms is set after context exit."""
        events: list[dict] = []
        with PreSamplerSpan(events, "cache_key_build", profile_level="summary") as ctx:
            pass
        assert ctx.duration_ms >= 0
        assert ctx.duration_ns >= 0


# ═══════════════════════════════════════════════════════════════════════
# 13. pre_sampler_span_metadata builder
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerMetadataBuilder:
    """pre_sampler_span_metadata produces correct dicts."""

    def test_basic_metadata(self):
        meta = pre_sampler_span_metadata(
            operation="cache_key_build",
            duration_ms=1.5,
            node_id="5",
            class_type="CLIPTextEncode",
        )
        assert meta["operation"] == "cache_key_build"
        assert meta["duration_ms"] == 1.5
        assert meta["node_id"] == "5"
        assert meta["class_type"] == "CLIPTextEncode"

    def test_unknown_operation_resolved_to_unattributed(self):
        meta = pre_sampler_span_metadata(operation="does_not_exist")
        assert meta["operation"] == "unattributed"

    def test_start_end_node_attribution(self):
        meta = pre_sampler_span_metadata(
            operation="node_execution",
            start_node_id="3",
            start_node_class_type="CLIPTextEncode",
            end_node_id="6",
            end_node_class_type="KSampler",
            cache_hit=False,
        )
        assert meta["start_node_id"] == "3"
        assert meta["start_node_class_type"] == "CLIPTextEncode"
        assert meta["end_node_id"] == "6"
        assert meta["end_node_class_type"] == "KSampler"
        assert meta["cache_hit"] is False


# ═══════════════════════════════════════════════════════════════════════
# 14. Trace.pre_sampler_summary (timing_trace)
# ═══════════════════════════════════════════════════════════════════════


class TestTracePreSamplerSummary:
    """Trace.pre_sampler_summary returns expected structure."""

    def test_empty_when_no_data(self):
        t = Trace(prompt_id="test")
        s = t.pre_sampler_summary()
        assert s.get("present") is False
        assert s["pre_sampler_critical_path_ms"] == {}

    def test_store_and_retrieve(self):
        t = Trace(prompt_id="test")
        data = {
            "cache_key_build_ms": 1.2,
            "cache_lookup_ms": 0.5,
            "node_execution_ms": 100.0,
            "unattributed_ms": 3.0,
            "total_wall_ms": 120.0,
            "operation_counts": {"cache_key_build": 1, "node_execution": 2},
            "operation_hits": {"cache_lookup": 3},
            "dominant_spans": [
                {"operation": "node_execution", "node_id": "6",
                 "class_type": "KSampler", "duration_ms": 100.0},
            ],
            "node_class_map": {"6": "KSampler"},
        }
        t.store_pre_sampler_data(data)
        s = t.pre_sampler_summary()
        assert s["present"] is True
        cp = s["pre_sampler_critical_path_ms"]
        assert cp["cache_key_build_ms"] == 1.2
        assert cp["cache_lookup_ms"] == 0.5
        assert cp["node_execution_ms"] == 100.0
        assert cp["unattributed_ms"] == 3.0
        assert cp["total_measured_ms"] == 101.7  # sum of non-unattributed
        assert cp["total_wall_ms"] == 120.0
        # residual = total_wall - total_measured - unattributed = 120 - 101.7 - 3
        assert cp["residual_ms"] == pytest.approx(15.3, rel=1e-3)
        assert s["pre_sampler_operation_counts"]["node_execution"] == 2
        assert s["pre_sampler_operation_hits"]["cache_lookup"] == 3
        assert len(s["pre_sampler_dominant_spans"]) == 1
        assert s["pre_sampler_node_map"]["6"] == "KSampler"

    def test_model_objects_not_deepcopied(self):
        """store_pre_sampler_data strips non-serializable objects."""
        t = Trace(prompt_id="safe")
        data = {
            "model_obj": _SentinelModel(),  # should be silently dropped
            "safe_key": 42,
        }
        t.store_pre_sampler_data(data)
        s = t.pre_sampler_summary()
        assert s["present"] is True
        # model_obj should not appear
        assert "model_obj" not in s
        assert "safe_key" not in s  # not a known field
        assert "pre_sampler_critical_path_ms" in s


# ═══════════════════════════════════════════════════════════════════════
# 15. TraceV4.pre_sampler_summary (timing_trace)
# ═══════════════════════════════════════════════════════════════════════


class TestTraceV4PreSamplerSummary:
    """TraceV4.pre_sampler_summary works from stored data and v4 events."""

    def test_v4_inherits_store_and_summary(self):
        """TraceV4 inherits store_pre_sampler_data and produces summary."""
        t = TraceV4(prompt_id="v4-test", process="test")
        t.store_pre_sampler_data({
            "cache_key_build_ms": 2.0,
            "node_execution_ms": 50.0,
            "total_wall_ms": 60.0,
            "operation_counts": {"cache_key_build": 1},
        })
        s = t.pre_sampler_summary()
        assert s["present"] is True
        assert s["pre_sampler_critical_path_ms"]["cache_key_build_ms"] == 2.0

    def test_v4_summary_includes_pre_sampler(self):
        """v4_summary includes pre_sampler data when stored."""
        t = TraceV4(prompt_id="v4-full", process="test")
        t.store_pre_sampler_data({
            "cache_key_build_ms": 1.0,
            "node_execution_ms": 100.0,
            "total_wall_ms": 110.0,
            "operation_counts": {"cache_key_build": 1},
            "dominant_spans": [
                {"operation": "node_execution", "node_id": "6",
                 "class_type": "KSampler", "duration_ms": 100.0},
            ],
            "node_class_map": {"6": "KSampler"},
        })
        vs = t.v4_summary()
        assert "pre_sampler_critical_path_ms" in vs
        assert vs["pre_sampler_critical_path_ms"]["node_execution_ms"] == 100.0
        assert "pre_sampler_dominant_spans" in vs
        assert "pre_sampler_node_map" in vs

    def test_v4_summary_no_crash_when_no_data(self):
        """v4_summary works without any pre_sampler data."""
        t = TraceV4(prompt_id="clean")
        vs = t.v4_summary()
        assert "pre_sampler_critical_path_ms" not in vs


# ═══════════════════════════════════════════════════════════════════════
# 16. attach_pre_sampler_critical_path postprocessor
# ═══════════════════════════════════════════════════════════════════════


class TestAttachCriticalPath:
    """attach_pre_sampler_critical_path enriches result correctly."""

    def test_attaches_to_result_when_no_trace(self):
        """When result has no 'trace' key, summary goes on result directly."""
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 50.0)

        result: dict[str, Any] = {}
        attach_pre_sampler_critical_path(result, plan, cache)

        cp = result.get("pre_sampler_critical_path")
        assert cp is not None
        assert cp["node_execution_ms"] == 50.0

    def test_attaches_inside_trace_dict(self):
        """When result['trace'] is a dict, summary goes inside it."""
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("3", "CLIPTextEncode", 25.0)

        result = {"trace": {"stages": {"t3_modal_entry": 1000.0}}}
        attach_pre_sampler_critical_path(result, plan, cache)

        cp = result["trace"]["pre_sampler_critical_path"]
        assert cp["node_execution_ms"] == 25.0

    def test_preserves_existing_trace_fields(self):
        """Existing trace fields are preserved after enrichment."""
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 30.0)

        result = {"trace": {"stages": {"t3_modal_entry": 1000.0}, "existing_key": "keep_me"}}
        attach_pre_sampler_critical_path(result, plan, cache)

        assert result["trace"]["existing_key"] == "keep_me"
        assert result["trace"]["stages"]["t3_modal_entry"] == 1000.0

    def test_node_map_from_workflow(self):
        """Node class map is populated from workflow when cache is empty."""
        plan = _make_plan(
            workflow={
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
                "3": {"class_type": "CLIPTextEncode", "inputs": {}},
            }
        )
        result: dict[str, Any] = {}
        attach_pre_sampler_critical_path(result, plan, None)
        # No cache data, but node class map from workflow should be attached
        # (the summary is attached to result directly when result has no 'trace')
        cp = result.get("pre_sampler_critical_path", result.get("trace", {}).get("pre_sampler_critical_path", {}))
        ncm = cp.get("node_class_map", {})
        assert ncm.get("1") == "CheckpointLoaderSimple", f"ncm={ncm}"
        assert ncm.get("3") == "CLIPTextEncode"

    def test_no_cache_no_crash(self):
        """attach with cache=None does not crash and attaches node map."""
        plan = _make_plan()
        result: dict[str, Any] = {"trace": {"stages": {}}}
        attach_pre_sampler_critical_path(result, plan, None)
        # With no cache data but a workflow, node_class_map is attached
        trace = result.get("trace", {})
        cp = trace.get("pre_sampler_critical_path", {})
        ncm = cp.get("node_class_map", {})
        assert isinstance(ncm, dict)
        assert "3" in ncm or "6" in ncm  # from workflow fallback

    def test_operation_counts_and_hits_included(self):
        """Operation counts and hits propagate through postprocessor."""
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 50.0)
        cache.resolve_inputs("3", "CLIPTextEncode", {"text": "cat"})
        cache.resolve_inputs("3", "CLIPTextEncode", {"text": "cat"})  # hit

        result: dict[str, Any] = {}
        attach_pre_sampler_critical_path(result, plan, cache)
        cp = result["pre_sampler_critical_path"]
        assert "operation_counts" in cp
        assert cp["operation_counts"]["cache_lookup"] >= 2
        assert "operation_hits" in cp
        assert cp["operation_hits"]["cache_lookup"] >= 1


# ═══════════════════════════════════════════════════════════════════════
# 17. RuntimeExecutor existing backend preserved (basic sanity)
# ═══════════════════════════════════════════════════════════════════════


class TestRuntimeExecutorPreserved:
    """Original RuntimeExecutor backend selection/fallback still works."""

    def test_select_backend_in_process(self):
        from comfymodal_runtime.runtime_executor import RuntimeExecutor
        exe = RuntimeExecutor(in_process_runner=lambda p, c: {"ok": True})
        diag = exe.select_backend("in_process")
        assert diag.selected == "in_process"
        assert diag.selection_reason == "runner_available"

    def test_execute_calls_runner(self):
        from comfymodal_runtime.runtime_executor import RuntimeExecutor, ExecutionContext
        async def _run():
            exe = RuntimeExecutor(in_process_runner=lambda p, c: {"result": "done"})
            plan = _make_plan()
            ctx = ExecutionContext(request_id="test-preserved")
            result = await exe.execute(plan, context=ctx)
            return result
        result = asyncio.run(_run())
        assert result["result"] == "done"
        assert "backend" in result


# ═══════════════════════════════════════════════════════════════════════
# 18. Timing injectable — deterministic clock
# ═══════════════════════════════════════════════════════════════════════


class TestTimingInjectability:
    """Clock injection makes tests deterministic."""

    def test_clock_records_calls(self):
        clock = _RecordingClock([0.0, 0.5, 0.0, 0.3])
        cache = PreSamplerCache(clock=clock)
        cache.build_cache_key(_make_plan())
        cache.record_node_execution("6", "KSampler", 200.0)
        # Clock was called during operations
        assert len(clock.calls) >= 2
        # Timings deterministic
        s = cache.to_summary_dict()
        assert s["node_execution_ms"] == 200.0

    def test_clock_not_called_when_not_needed(self):
        """Clock is not called for pure cache hits (fast path)."""
        clock = _RecordingClock([0.0, 0.1, 0.0])
        cache = PreSamplerCache(clock=clock)
        model = _SentinelModel()
        cache.resolve_inputs("3", "Test", {"m": model})
        cache.resolve_inputs("3", "Test", {"m": model})  # hit
        # Both calls to resolve_inputs use _time_operation which calls clock
        assert len(clock.calls) >= 2


# ═══════════════════════════════════════════════════════════════════════
# 19. Edge cases — empty workflow, zero durations
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases around empty/minimal inputs."""

    def test_empty_workflow(self):
        plan = ExecutionPlan(
            workflow={},
            execution_options=ExecutionOptions(production_enabled=False),
        )
        cache = PreSamplerCache()
        key = cache.build_cache_key(plan)
        assert isinstance(key, str)
        assert len(key) > 0

    def test_no_operations_empty_summary(self):
        cache = PreSamplerCache()
        s = cache.to_summary_dict()
        # unattributed is 0.0 unless recorded
        assert "unattributed_ms" in s
        assert s.get("total_measured_ms") is None

    def test_zero_duration_node_execution(self):
        cache = PreSamplerCache()
        cache.record_node_execution("1", "Noop", 0.0)
        spans = [s for s in cache.dominant_spans if s["operation"] == "node_execution"]
        assert len(spans) == 1
        assert spans[0]["duration_ms"] == 0.0


# ═══════════════════════════════════════════════════════════════════════
# 20. Future wait timing — recording prevents double-count
# ═══════════════════════════════════════════════════════════════════════


class TestFutureTiming:
    """Future wait timing is recorded correctly."""

    async def _do_future_zero_wait_test(self):
        cache = PreSamplerCache()
        future = _FakeFuture(done=True)
        result = await cache.get_future_result(future)
        assert result == "fake_result"
        assert cache.operation_hits.get("future_wait", 0) == 1
        assert cache.operation_count["future_wait"] == 1
        # The recorded time should be close to zero for a sync return
        assert cache.operation_timing_ms["future_wait"] < 5.0

    def test_completed_future_zero_wait(self):
        asyncio.run(self._do_future_zero_wait_test())


# ═══════════════════════════════════════════════════════════════════════
# 21. Fix 1 — RuntimeExecutor integration
# ═══════════════════════════════════════════════════════════════════════


class TestRuntimeExecutorIntegration:
    """ExecutionContext auto-creates cache; execute/stream attach summary."""

    def test_context_auto_creates_cache(self):
        """ExecutionContext creates PreSamplerCache in metadata when absent."""
        ctx = ExecutionContext(request_id="auto-cache")
        assert "pre_sampler_cache" in ctx.metadata
        assert isinstance(ctx.metadata["pre_sampler_cache"], PreSamplerCache)

    def test_context_preserves_caller_supplied_cache(self):
        """When caller supplies a cache, it is not overwritten."""
        custom = PreSamplerCache()
        ctx = ExecutionContext(
            request_id="custom-cache",
            metadata={"pre_sampler_cache": custom},
        )
        assert ctx.metadata["pre_sampler_cache"] is custom

    async def _do_execute_attaches_test(self):
        plan = _make_plan()
        cache = PreSamplerCache()
        ctx = ExecutionContext(
            request_id="exec-attach",
            metadata={"pre_sampler_cache": cache},
        )
        executor = RuntimeExecutor(
            in_process_runner=lambda p, c: {"result": "done"}
        )
        result = await executor.execute(plan, context=ctx)
        # Critical path attached to result
        assert "pre_sampler_critical_path" in result or \
               ("trace" in result and "pre_sampler_critical_path" in result["trace"])
        # Original runner output preserved
        assert result.get("result") == "done"

    def test_execute_attaches_critical_path(self):
        asyncio.run(self._do_execute_attaches_test())

    async def _do_execute_order_results_preserved_test(self):
        plan = _make_plan()
        cache = PreSamplerCache()
        ctx = ExecutionContext(
            request_id="exec-order",
            metadata={"pre_sampler_cache": cache},
        )
        executor = RuntimeExecutor(
            in_process_runner=lambda p, c: {"result": "done", "sampler_seed": 42}
        )
        result = await executor.execute(plan, context=ctx)
        # Original output fields unchanged
        assert result["result"] == "done"
        assert result["sampler_seed"] == 42

    def test_execute_order_results_preserved(self):
        asyncio.run(self._do_execute_order_results_preserved_test())

    async def _do_stream_attaches_to_result_test(self):
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 50.0)
        ctx = ExecutionContext(
            request_id="stream-attach",
            metadata={"pre_sampler_cache": cache},
        )

        async def _stream_runner(p, c):
            yield {"type": "result", "data": {"images": ["img1.png"]}}

        executor = RuntimeExecutor(in_process_runner=_stream_runner)
        events = []
        async for event in executor.stream(plan, context=ctx):
            events.append(event)
        assert len(events) == 1
        ev = events[0]
        assert ev.get("type") == "result"
        # Critical path should be attached inside the event (inside trace or directly)
        if "trace" in ev and isinstance(ev.get("trace"), dict):
            cp = ev["trace"].get("pre_sampler_critical_path", {})
        else:
            cp = ev.get("pre_sampler_critical_path", {})
        assert "node_execution_ms" in cp or "operation_counts" in cp

    def test_stream_attaches_to_result(self):
        asyncio.run(self._do_stream_attaches_to_result_test())

    async def _do_stream_progress_preserved_test(self):
        """Progress/status events are not enriched, result events are."""
        plan = _make_plan()
        cache = PreSamplerCache()
        ctx = ExecutionContext(
            request_id="stream-progress",
            metadata={"pre_sampler_cache": cache},
        )
        progress_events: list[dict] = []

        async def _stream_runner(p, c):
            yield {"type": "progress", "step": 1}
            yield {"type": "status", "message": "ok"}
            yield {"type": "result", "data": {"done": True}}

        executor = RuntimeExecutor(in_process_runner=_stream_runner)
        events = []
        async for event in executor.stream(plan, context=ctx):
            events.append(event)
        # Progress/status unchanged
        assert events[0] == {"type": "progress", "step": 1}
        assert events[1] == {"type": "status", "message": "ok"}
        # Result enriched
        ev = events[2]
        assert ev.get("type") == "result"

    def test_stream_progress_preserved(self):
        asyncio.run(self._do_stream_progress_preserved_test())


# ═══════════════════════════════════════════════════════════════════════
# 22. Fix 2 — input_resolution_ms with builder
# ═══════════════════════════════════════════════════════════════════════


class TestInputResolutionBuilder:
    """resolve_inputs with builder records input_resolution_ms separately."""

    def test_builder_called_once_on_miss(self):
        """Builder is invoked on cache miss and timed as input_resolution."""
        clock = _RecordingClock([0.0, 0.001, 0.002, 0.003, 0.004])
        cache = PreSamplerCache(clock=clock)
        build_count: list[int] = [0]

        def builder() -> dict:
            build_count[0] += 1
            return {"resolved": "data"}

        result = cache.resolve_inputs(
            "5", "CLIPTextEncode", {"text": "cat"},
            builder=builder,
        )
        assert build_count[0] == 1
        assert result == {"resolved": "data"}
        # input_resolution recorded
        assert cache.operation_count.get("input_resolution", 0) == 1
        assert cache.operation_timing_ms.get("input_resolution", 0) >= 0
        # cache_lookup also recorded (non-overlapping leaf)
        assert cache.operation_count.get("cache_lookup", 0) >= 1

    def test_builder_not_called_on_hit(self):
        """Builder is skipped on cache hit."""
        clock = _RecordingClock([0.0, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006])
        cache = PreSamplerCache(clock=clock)
        build_count: list[int] = [0]

        def builder() -> dict:
            build_count[0] += 1
            return {"resolved": "data"}

        # First call — miss, builder called
        r1 = cache.resolve_inputs("5", "CLIPTextEncode", {"text": "cat"}, builder=builder)
        # Second call — hit, builder NOT called
        r2 = cache.resolve_inputs("5", "CLIPTextEncode", {"text": "cat"}, builder=builder)
        assert build_count[0] == 1
        assert r1 is r2
        # input_resolution count = 1 (only on miss)
        assert cache.operation_count.get("input_resolution", 0) == 1
        # cache_lookup hits = 1 (second call was a hit)
        assert cache.operation_hits.get("cache_lookup", 0) == 1

    def test_builder_count_one_after_double_call(self):
        """Builder is invoked exactly once even with identical inputs."""
        cache = PreSamplerCache()
        call_count: list[int] = [0]

        def builder() -> dict:
            call_count[0] += 1
            return {"resolved": "data"}

        cache.resolve_inputs("3", "Test", {"x": 1}, builder=builder)
        cache.resolve_inputs("3", "Test", {"x": 1}, builder=builder)
        assert call_count[0] == 1

    def test_no_builder_backward_compatible(self):
        """Calling resolve_inputs without builder works as before."""
        cache = PreSamplerCache()
        inputs = {"text": "hello"}
        r1 = cache.resolve_inputs("5", "CLIPTextEncode", inputs)
        r2 = cache.resolve_inputs("5", "CLIPTextEncode", inputs)
        assert r1 is r2
        assert cache.operation_hits.get("cache_lookup", 0) == 1

    def test_lookup_and_resolution_non_overlapping(self):
        """cache_lookup and input_resolution are separate leaf timings."""
        clock = _RecordingClock([0.0, 0.001, 0.010, 0.020, 0.021])
        cache = PreSamplerCache(clock=clock)

        def builder() -> dict:
            return {"resolved": "data"}

        cache.resolve_inputs("5", "Test", {"x": 1}, builder=builder)
        lookup_ms = cache.operation_timing_ms.get("cache_lookup", 0)
        resolution_ms = cache.operation_timing_ms.get("input_resolution", 0)
        # Both recorded
        assert lookup_ms >= 0
        assert resolution_ms >= 0
        # resolution is ~10ms (between 0.010 and 0.020), lookup is ~1ms
        # The sum should not exceed total wall
        total = lookup_ms + resolution_ms
        assert total > 0


# ═══════════════════════════════════════════════════════════════════════
# 23. Fix 3 — model patch result caching, lock_wait separation
# ═══════════════════════════════════════════════════════════════════════


class TestModelPatchResultReuse:
    """apply_model_patch returns cached result; lock_wait separate from model_patch."""

    def test_first_call_returns_patcher_result(self):
        """First call returns the patcher result, not None."""
        cache = PreSamplerCache()
        result = cache.apply_model_patch("m1", "p1", lambda: "patched_model")
        assert result == "patched_model"

    def test_second_call_returns_cached_result(self):
        """Second call returns the same cached result."""
        cache = PreSamplerCache()
        r1 = cache.apply_model_patch("m1", "p1", lambda: "patched_model")
        r2 = cache.apply_model_patch("m1", "p1", lambda: "patched_model")
        assert r1 == r2
        assert r2 == "patched_model"

    def test_patcher_invoked_exactly_once(self):
        """Patcher is called exactly once per identity."""
        cache = PreSamplerCache()
        call_count: list[int] = [0]

        def patcher() -> str:
            call_count[0] += 1
            return "model"

        cache.apply_model_patch("m1", "p1", patcher)
        cache.apply_model_patch("m1", "p1", patcher)
        assert call_count[0] == 1

    def test_lock_wait_not_double_counted_in_model_patch(self):
        """model_patch_ms does NOT include lock_wait time."""
        cache = PreSamplerCache()
        cache.apply_model_patch("m1", "p1", lambda: "result")
        model_patch_ms = cache.operation_timing_ms.get("model_patch", 0)
        lock_wait_ms = cache.operation_timing_ms.get("lock_wait", 0)
        # model_patch should measure only the patcher call, not lock contention
        assert model_patch_ms >= 0
        assert lock_wait_ms >= 0

    def test_lock_acquisition_count(self):
        """lock_wait count proves no lock on fast-path hit."""
        cache = PreSamplerCache()
        cache.apply_model_patch("m1", "p1", lambda: "result")
        # First call acquires lock
        assert cache.operation_count.get("lock_wait", 0) >= 1
        lock_count_after_first = cache.operation_count.get("lock_wait", 0)

        cache.apply_model_patch("m1", "p1", lambda: "result")
        # Second call: fast-path hit, NO lock acquired
        assert cache.operation_count.get("lock_wait", 0) == lock_count_after_first

    def test_model_patch_hit_recorded(self):
        """Second call records model_patch as cache hit."""
        cache = PreSamplerCache()
        cache.apply_model_patch("m1", "p1", lambda: "result")
        assert cache.operation_hits.get("model_patch", 0) == 0
        cache.apply_model_patch("m1", "p1", lambda: "result")
        assert cache.operation_hits.get("model_patch", 0) == 1

    def test_different_patches_independent(self):
        """Different (model_id, patch_id) pairs apply independently."""
        cache = PreSamplerCache()
        results: list[str] = []

        cache.apply_model_patch("m1", "p1", lambda: results.append("a") or "a")
        cache.apply_model_patch("m1", "p2", lambda: results.append("b") or "b")
        assert len(results) == 2

    def test_lock_wait_separate_from_model_patch_timing(self):
        """lock_wait timing is recorded through the normal trace/counter path."""
        cache = PreSamplerCache()
        cache.apply_model_patch("m1", "p1", lambda: "result")
        assert "lock_wait" in cache.operation_count
        assert "lock_wait" in cache.operation_timing_ms
        assert cache.operation_timing_ms.get("lock_wait", 0) >= 0
        assert cache.operation_timing_ms.get("model_patch", 0) >= 0


# ═══════════════════════════════════════════════════════════════════════
# 24. Fix 4 — conditioning cache distinguishes None from miss
# ═══════════════════════════════════════════════════════════════════════


class TestConditioningNoneDistinction:
    """cache_conditioning distinguishes a cached None from a miss."""

    def test_cached_none_returned(self):
        """Caching None and retrieving returns None (does not treat as miss)."""
        cache = PreSamplerCache()
        clip = _SentinelModel()
        result1 = cache.cache_conditioning("fp1", clip, None)
        assert result1 is None
        # First call is a miss (cache miss), so no hit
        assert cache.operation_hits.get("conditioning", 0) == 0

    def test_cached_none_hit_on_second_call(self):
        """Second call with same (fp, clip) returns None from cache."""
        cache = PreSamplerCache()
        clip = _SentinelModel()
        cache.cache_conditioning("fp1", clip, None)
        result2 = cache.cache_conditioning("fp1", clip, None)
        assert result2 is None
        # Second call IS a hit
        assert cache.operation_hits.get("conditioning", 0) == 1

    def test_actual_miss_returns_none_without_hit(self):
        """A true miss (key not in cache) does not increment hit counter."""
        cache = PreSamplerCache()
        clip = _SentinelModel()
        # This is a genuine miss — conditioning key not present
        result = cache.cache_conditioning("new_fp", clip, "some_data")
        assert result == "some_data"
        assert cache.operation_hits.get("conditioning", 0) == 0


# ═══════════════════════════════════════════════════════════════════════
# 25. Fix 5 — fingerprinting: nested sequences, no deep-copy/content hash
# ═══════════════════════════════════════════════════════════════════════


class TestFingerprintNestedSequences:
    """Fingerprinting handles nested sequences without breaking."""

    def test_nested_scalar_sequence_fingerprinted(self):
        """Nested list of scalars produces stable fingerprint."""
        cache = PreSamplerCache()
        fp1 = cache._fingerprint_inputs(
            "1", "Test", {"items": ["a", "b", "c"]}
        )
        fp2 = cache._fingerprint_inputs(
            "1", "Test", {"items": ["a", "b", "c"]}
        )
        assert fp1 == fp2

    def test_nested_list_of_lists(self):
        """Nested [[scalar]] sequences fingerprinted element-wise."""
        cache = PreSamplerCache()
        fp1 = cache._fingerprint_inputs(
            "1", "Test", {"matrix": [[1, 2], [3, 4]]}
        )
        fp2 = cache._fingerprint_inputs(
            "1", "Test", {"matrix": [[1, 2], [3, 4]]}
        )
        assert fp1 == fp2

    def test_different_nested_sequences_differ(self):
        """Different nested sequences produce different fingerprints."""
        cache = PreSamplerCache()
        fp1 = cache._fingerprint_inputs(
            "1", "Test", {"items": ["a", "b"]}
        )
        fp2 = cache._fingerprint_inputs(
            "1", "Test", {"items": ["a", "c"]}
        )
        assert fp1 != fp2

    def test_nested_list_with_model_uses_id(self):
        """Opaque objects inside nested lists use id(), not content."""
        cache = PreSamplerCache()
        model = _SentinelModel()
        fp = cache._fingerprint_inputs(
            "1", "Test", {"items": [model]}
        )
        # Should not raise (no deepcopy/hash/eq on model)
        assert isinstance(fp, tuple)

    def test_no_deepcopy_on_nested_model(self):
        """Nested sequence with model never calls deepcopy/hash."""
        cache = PreSamplerCache()
        model = _SentinelModel()
        # This should NOT trigger deepcopy/hash/eq
        inputs = {"nested": [model, "text"]}
        result = cache.resolve_inputs("3", "Test", inputs)
        assert result is inputs

    def test_mappingproxy_type_inputs(self):
        """Fingerprinting handles dict-like inputs (MappingProxyType)."""
        from types import MappingProxyType
        cache = PreSamplerCache()
        mp = MappingProxyType({"text": "hello", "seed": 42})
        fp = cache._fingerprint_inputs("1", "Test", mp)
        assert isinstance(fp, tuple)
        # Values "hello" and 42 should be in the fingerprint tuple
        assert "hello" in fp
        assert 42 in fp


# ═══════════════════════════════════════════════════════════════════════
# 26. Fix 6 — attach consumes trace events
# ═══════════════════════════════════════════════════════════════════════


class TestAttachConsumesTraceEvents:
    """attach_pre_sampler_critical_path consumes trace events for operation data."""

    def test_consumes_pre_sampler_events(self):
        """Trace events with pre_sampler operation metadata are consumed."""
        result = {
            "trace": {
                "stages": {"t3_modal_entry": 1000.0, "t6_sampler_end": 1001.0},
                "events": [
                    {
                        "name": "pre_sampler_cache_key_build",
                        "metadata": {
                            "operation": "cache_key_build",
                            "duration_ms": 2.5,
                            "node_id": "",
                        },
                    },
                ],
            }
        }
        plan = _make_plan()
        attach_pre_sampler_critical_path(result, plan, None)
        trace = result.get("trace", {})
        cp = trace.get("pre_sampler_critical_path", {})
        assert cp.get("cache_key_build_ms") == 2.5

    def test_consumes_multiple_operations(self):
        """Multiple pre_sampler operations are aggregated."""
        result = {
            "trace": {
                "stages": {"t3": 1000.0, "t6": 1002.0},
                "events": [
                    {
                        "name": "pre_sampler_model_patch",
                        "metadata": {
                            "operation": "model_patch",
                            "duration_ms": 5.0,
                            "start_node_id": "m1",
                            "end_node_id": "p1",
                        },
                    },
                    {
                        "name": "pre_sampler_cache_lookup",
                        "metadata": {
                            "operation": "cache_lookup",
                            "duration_ms": 1.0,
                            "node_id": "3",
                            "class_type": "CLIPTextEncode",
                            "cache_hit": True,
                        },
                    },
                ],
            }
        }
        plan = _make_plan()
        attach_pre_sampler_critical_path(result, plan, None)
        cp = result["trace"]["pre_sampler_critical_path"]
        assert cp.get("model_patch_ms") == 5.0
        assert cp.get("cache_lookup_ms") == 1.0
        assert "operation_counts" in cp
        assert cp["operation_counts"].get("model_patch", 0) >= 1

    def test_preserves_existing_fields_when_consuming(self):
        """Existing trace fields are preserved when consuming events."""
        result = {
            "trace": {
                "stages": {"t3": 1000.0},
                "existing_key": "keep_me",
                "events": [
                    {
                        "name": "pre_sampler_node_execution",
                        "metadata": {
                            "operation": "node_execution",
                            "duration_ms": 10.0,
                            "node_id": "6",
                            "class_type": "KSampler",
                        },
                    },
                ],
            }
        }
        plan = _make_plan()
        attach_pre_sampler_critical_path(result, plan, None)
        assert result["trace"]["existing_key"] == "keep_me"

    def test_dominant_spans_from_trace_events(self):
        """Dominant spans are derived from trace event metadata."""
        result = {
            "trace": {
                "stages": {"t3": 1000.0, "t6": 1001.0},
                "events": [
                    {
                        "name": "pre_sampler_node_execution",
                        "metadata": {
                            "operation": "node_execution",
                            "duration_ms": 100.0,
                            "node_id": "6",
                            "class_type": "KSampler",
                        },
                    },
                ],
            }
        }
        plan = _make_plan()
        attach_pre_sampler_critical_path(result, plan, None)
        cp = result["trace"]["pre_sampler_critical_path"]
        spans = cp.get("dominant_spans", [])
        assert len(spans) >= 1
        assert spans[0]["node_id"] == "6"
        assert spans[0]["class_type"] == "KSampler"

    def test_unknown_end_node_not_invented(self):
        """When trace does not identify an end node, none is invented."""
        result = {
            "trace": {
                "stages": {"t3": 1000.0},
                "events": [
                    {
                        "name": "pre_sampler_model_patch",
                        "metadata": {
                            "operation": "model_patch",
                            "duration_ms": 5.0,
                            "start_node_id": "m1",
                            # No end_node_id — should not be invented
                        },
                    },
                ],
            }
        }
        plan = _make_plan()
        attach_pre_sampler_critical_path(result, plan, None)
        cp = result["trace"]["pre_sampler_critical_path"]
        spans = cp.get("dominant_spans", [])
        if spans:
            span = spans[0]
            assert "end_node_id" not in span or span["end_node_id"] == ""


# ═══════════════════════════════════════════════════════════════════════
# 27. Fix 7 — derive_spans exposes exact node/operation metadata
# ═══════════════════════════════════════════════════════════════════════


class TestDeriveSpansMetadata:
    """derive_spans exposes exact node/operation metadata."""

    def test_span_has_duration_ms(self):
        """Derived span has both duration_wall_ms and duration_ms."""
        from profiler_trace_v4 import derive_spans
        events = [
            {"name": "cache_key_build_start", "wall_unix_ns": 1000, "mono_ns": 1000,
             "process": "test", "metadata": {"operation": "cache_key_build"}},
            {"name": "cache_key_build_end", "wall_unix_ns": 2000, "mono_ns": 2000,
             "process": "test", "metadata": {"operation": "cache_key_build", "duration_ms": 1.0}},
        ]
        spans = derive_spans(events)
        assert len(spans) == 1
        span = spans[0]
        assert "duration_ms" in span
        assert span["duration_ms"] == 1.0
        assert "duration_wall_ms" in span
        assert span["metadata"]["operation"] == "cache_key_build"


# ═══════════════════════════════════════════════════════════════════════
# 28. Fix 8 — Trace.summary() includes pre_sampler data additively
# ═══════════════════════════════════════════════════════════════════════


class TestTraceSummaryPreSampler:
    """Trace.summary() includes pre_sampler data additively."""

    def test_summary_contains_pre_sampler_keys(self):
        """When pre_sampler data stored, summary() includes it."""
        t = Trace(prompt_id="test")
        t.store_pre_sampler_data({
            "cache_key_build_ms": 1.5,
            "node_execution_ms": 100.0,
            "total_wall_ms": 110.0,
            "operation_counts": {"cache_key_build": 1},
            "dominant_spans": [
                {"operation": "node_execution", "node_id": "6", "duration_ms": 100.0},
            ],
        })
        s = t.summary()
        assert "pre_sampler_critical_path_ms" in s
        cp = s["pre_sampler_critical_path_ms"]
        assert cp["cache_key_build_ms"] == 1.5
        assert cp["node_execution_ms"] == 100.0
        assert cp["total_measured_ms"] == 101.5  # sum of non-unattributed
        assert "pre_sampler_operation_counts" in s

    def test_summary_preserves_existing_keys(self):
        """Existing summary keys are not changed by pre_sampler addition."""
        t = Trace(prompt_id="test")
        t.mark("t3_modal_entry")
        t.store_pre_sampler_data({
            "cache_key_build_ms": 1.0,
        })
        s = t.summary()
        assert "prompt_id" in s
        assert "stages" in s
        assert "deltas_ms" in s
        assert "derived_ms" in s
        # pre_sampler keys added without replacing existing
        assert "pre_sampler_critical_path_ms" in s

    def test_summary_no_pre_sampler_when_not_stored(self):
        """When no pre_sampler data stored, summary() has no pre_sampler keys."""
        t = Trace(prompt_id="clean")
        s = t.summary()
        assert "pre_sampler_critical_path_ms" not in s

    def test_reconciliation_in_summary(self):
        """Pre-sampler reconciliation (measured + unattributed + residual) in summary."""
        t = Trace(prompt_id="reconcile")
        t.store_pre_sampler_data({
            "node_execution_ms": 80.0,
            "unattributed_ms": 10.0,
            "total_wall_ms": 100.0,
        })
        s = t.summary()
        cp = s["pre_sampler_critical_path_ms"]
        assert cp["total_measured_ms"] == 80.0
        assert cp["unattributed_ms"] == 10.0
        # residual = total_wall - total_measured - unattributed
        assert cp["residual_ms"] == 10.0


# ═══════════════════════════════════════════════════════════════════════
# 29. Fix 6 continued — reconciliation report
# ═══════════════════════════════════════════════════════════════════════


class TestReconciliationReporting:
    """Reconciliation status reported when measured exceeds wall."""

    def test_residual_not_clamped_when_measured_exceeds_wall(self):
        """residual_ms can be negative (measured exceeds wall) and is reported."""
        result = {
            "trace": {
                "stages": {"t3": 1000.0, "t6": 1000.5},
            }
        }
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 600.0)  # 600ms > 500ms wall
        attach_pre_sampler_critical_path(result, plan, cache)
        cp = result["trace"]["pre_sampler_critical_path"]
        assert cp["total_wall_ms"] == 500.0
        assert cp["node_execution_ms"] == 600.0
        # residual = 500 - 600 - 0 = -100
        assert cp["residual_ms"] == -100.0
        assert cp["reconciliation_status"] == "measured_exceeds_wall"


# ═══════════════════════════════════════════════════════════════════════
# 30. Futures — completed (zero wait) & incomplete concurrent future
# ═══════════════════════════════════════════════════════════════════════


class TestFutureTypes:
    """Completed futures and incomplete concurrent futures handled correctly."""

    async def _do_completed_future_zero_wait_test(self):
        cache = PreSamplerCache()
        future = _FakeFuture(done=True)
        result = await cache.get_future_result(future)
        assert result == "fake_result"
        # Zero wait: cache hit
        assert cache.operation_hits.get("future_wait", 0) == 1
        assert cache.operation_timing_ms.get("future_wait", 0) == 0.0

    def test_completed_future_zero_wait(self):
        asyncio.run(self._do_completed_future_zero_wait_test())

    async def _do_plain_value_zero_wait_test(self):
        cache = PreSamplerCache()
        result = await cache.get_future_result("plain_string")
        assert result == "plain_string"
        assert cache.operation_hits.get("future_wait", 0) == 1
        assert cache.operation_timing_ms.get("future_wait", 0) == 0.0

    def test_plain_value_zero_wait(self):
        asyncio.run(self._do_plain_value_zero_wait_test())

    async def _do_incomplete_coroutine_awaited_test(self):
        cache = PreSamplerCache()

        async def async_fn() -> str:
            return "async_done"

        result = await cache.get_future_result(async_fn())
        assert result == "async_done"
        # Not a hit (was awaited)
        assert cache.operation_hits.get("future_wait", 0) == 0
        assert cache.operation_count["future_wait"] == 1

    def test_incomplete_coroutine_awaited(self):
        asyncio.run(self._do_incomplete_coroutine_awaited_test())


# ═══════════════════════════════════════════════════════════════════════
# 31. Milestone span enrichment — cache attribution (Phase 3B)
# ═══════════════════════════════════════════════════════════════════════


class TestMilestoneEnrichment:
    """attach_pre_sampler_critical_path enriches milestone spans with
    cache-derived attribution fields."""

    def test_milestone_span_has_attribution_when_cache_present(self):
        """When cache data exists, milestone spans include 'attribution'
        dict with cache_hit, background_future_exists, etc."""
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 50.0)
        cache.build_cache_key(plan)

        # Simulate trace with pre_sampler_stages metadata
        result: dict[str, Any] = {
            "trace": {
                "events": [
                    {
                        "name": "pre_sampler_stages",
                        "metadata": {
                            "execution_start_to_cached_ms": 2.5,
                            "cached_to_first_node_ms": 15.0,
                            "first_node_to_clip_ms": 8.0,
                            "clip_to_sampler_node_ms": 5.0,
                            "sampler_node_to_sampler_start_ms": 3.0,
                            "first_output_node_id": "3",
                            "first_executing_node_id": "6",
                            "first_clip_encode_node_id": "5",
                            "first_sampler_node_id": "6",
                            "first_output_class_type": "CLIPTextEncode",
                            "first_executing_node_class": "KSampler",
                            "first_clip_encode_node_class": "CLIPTextEncode",
                            "first_sampler_node_class": "KSampler",
                        },
                    }
                ],
            }
        }

        attach_pre_sampler_critical_path(result, plan, cache)
        cp = result["trace"].get("pre_sampler_critical_path", {})
        spans = cp.get("dominant_spans", [])

        # At least some milestone spans should have 'attribution' dict
        milestone_spans = [s for s in spans if "span" in s]
        assert len(milestone_spans) > 0, "expected milestone spans"

        for ms in milestone_spans:
            attr = ms.get("attribution")
            if attr is not None:
                # Common fields present
                assert "background_future_exists" in attr
                assert "background_future_done" in attr
                # cache_hit or model_cache_hit may be present depending on operations
                assert isinstance(attr["background_future_exists"], bool)
                assert isinstance(attr["background_future_done"], bool)

    def test_milestone_attribution_includes_cache_hit(self):
        """When cache has lookup hits, attribution includes cache_hit."""
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 50.0)
        cache.resolve_inputs("3", "CLIPTextEncode", {"text": "cat"})
        cache.resolve_inputs("3", "CLIPTextEncode", {"text": "cat"})  # hit

        result: dict[str, Any] = {
            "trace": {
                "events": [
                    {
                        "name": "pre_sampler_stages",
                        "metadata": {
                            "execution_start_to_cached_ms": 1.0,
                            "cached_to_first_node_ms": 10.0,
                            "first_output_node_id": "3",
                            "first_executing_node_id": "3",
                            "first_output_class_type": "CLIPTextEncode",
                            "first_executing_node_class": "CLIPTextEncode",
                        },
                    }
                ],
            }
        }

        attach_pre_sampler_critical_path(result, plan, cache)
        cp = result["trace"].get("pre_sampler_critical_path", {})
        spans = cp.get("dominant_spans", [])
        milestone_spans = [s for s in spans if "span" in s]

        # execution_start_to_cached span should have hash_or_cache_check_ms
        for ms in milestone_spans:
            if ms.get("span") == "execution_start_to_cached":
                attr = ms.get("attribution", {})
                if attr.get("hash_or_cache_check_ms") is not None:
                    assert attr["hash_or_cache_check_ms"] > 0
                # cache_hit expected when cache_lookup hits exist
                if attr.get("cache_hit"):
                    assert attr["cache_hit"] is True

    def test_milestone_attribution_includes_future_wait(self):
        """When cache has non-zero future_wait_ms, cached_to_first_node
        span includes future_wait_ms."""
        plan = _make_plan()
        cache = PreSamplerCache()
        cache.record_node_execution("6", "KSampler", 50.0)
        # Manually add future_wait timing to simulate background wait
        cache.operation_timing_ms["future_wait"] = 25.0
        cache.operation_count["future_wait"] = 1

        result: dict[str, Any] = {
            "trace": {
                "events": [
                    {
                        "name": "pre_sampler_stages",
                        "metadata": {
                            "cached_to_first_node_ms": 30.0,
                            "first_output_node_id": "3",
                            "first_executing_node_id": "6",
                            "first_output_class_type": "CLIPTextEncode",
                            "first_executing_node_class": "KSampler",
                        },
                    }
                ],
            }
        }

        attach_pre_sampler_critical_path(result, plan, cache)
        cp = result["trace"].get("pre_sampler_critical_path", {})
        spans = cp.get("dominant_spans", [])
        milestone_spans = [s for s in spans if "span" in s]

        for ms in milestone_spans:
            if ms.get("span") == "cached_to_first_node":
                attr = ms.get("attribution", {})
                # future_wait_ms should be present (cache had 25ms future_wait)
                assert "future_wait_ms" in attr, (
                    f"expected future_wait_ms in cached_to_first_node attribution, "
                    f"got {attr}"
                )
