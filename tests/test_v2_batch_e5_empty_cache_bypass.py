"""Batch E5 fail-closed empty-cache bypass tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from comfymodal_runtime.empty_cache_bypass import (
    EMPTY_CACHE_BYPASS_FLAG,
    SOFT_CACHE_REASONS,
    bypass_enabled,
    evaluate_bypass,
    execute_soft_cache,
)


def _decision(**overrides):
    values = {
        "enabled": True,
        "soft_cache_reason": "free_memory_defensive_no_unload",
        "models_unloaded_count": 0,
        "physical_free_bytes": 100,
        "operation_required_bytes": 10,
        "minimum_required_bytes": 20,
        "allocator_backend": "native",
        "capture_active": False,
        "custom_allocator_active": False,
        "custom_pool_active": False,
    }
    values.update(overrides)
    return evaluate_bypass(**values)


def _run(decision, *, fail_empty=False):
    calls: list[str] = []
    events: list[dict] = []

    def synchronize() -> None:
        calls.append("synchronize")

    def empty_cache() -> None:
        calls.append("empty_cache")
        if fail_empty:
            raise RuntimeError("native allocation retry exhausted")

    def ipc_collect() -> None:
        calls.append("ipc_collect")

    try:
        execute_soft_cache(
            decision,
            synchronize=synchronize,
            empty_cache=empty_cache,
            ipc_collect=ipc_collect,
            event_sink=events.append,
        )
    except RuntimeError:
        pass
    return calls, events


class TestE5DecisionMatrix(unittest.TestCase):
    def test_defensive_huge_headroom_skips_only_empty_cache(self) -> None:
        decision = _decision()
        calls, events = _run(decision)
        self.assertTrue(decision["eligible"])
        self.assertEqual(calls, ["synchronize", "ipc_collect"])
        self.assertEqual(events[-1]["empty_cache_executed"], False)
        self.assertEqual(events[-1]["soft_cache_reason"], "free_memory_defensive_no_unload")
        for key in (
            "physical_free_bytes",
            "required_bytes",
            "minimum_required_bytes",
            "headroom_ratio",
            "allocator_backend",
            "capture_active",
            "custom_pool_active",
            "models_unloaded_count",
            "empty_cache_executed",
        ):
            self.assertIn(key, events[-1])

    def test_after_unload_uses_native_full_cleanup(self) -> None:
        decision = _decision(soft_cache_reason="free_memory_after_unload")
        calls, events = _run(decision)
        self.assertFalse(decision["eligible"])
        self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])
        self.assertFalse(events[-1]["eligible"])

    def test_dead_model_cleanup_uses_native_full_cleanup(self) -> None:
        decision = _decision(soft_cache_reason="cleanup_models_gc_dead_model")
        calls, _ = _run(decision)
        self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_vae_oom_retry_uses_native_full_cleanup(self) -> None:
        decision = _decision(soft_cache_reason="vae_oom_retry")
        calls, _ = _run(decision)
        self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_other_reason_uses_native_full_cleanup(self) -> None:
        decision = _decision(soft_cache_reason="other")
        calls, _ = _run(decision)
        self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_insufficient_headroom_uses_native(self) -> None:
        decision = _decision(physical_free_bytes=39)
        calls, _ = _run(decision)
        self.assertFalse(decision["eligible"])
        self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_unknown_state_uses_native(self) -> None:
        cases = (
            "models_unloaded_count",
            "physical_free_bytes",
            "operation_required_bytes",
            "minimum_required_bytes",
            "allocator_backend",
            "capture_active",
            "custom_allocator_active",
            "custom_pool_active",
        )
        for name in cases:
            with self.subTest(name=name):
                decision = _decision(**{name: None})
                calls, _ = _run(decision)
                self.assertFalse(decision["eligible"])
                self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_graph_capture_uses_native(self) -> None:
        decision = _decision(capture_active=True)
        calls, _ = _run(decision)
        self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_custom_allocator_and_pool_use_native(self) -> None:
        for field in ("custom_allocator_active", "custom_pool_active"):
            with self.subTest(field=field):
                decision = _decision(**{field: True})
                calls, _ = _run(decision)
                self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_feature_off_preserves_native_operations(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(bypass_enabled())
        decision = _decision(enabled=False)
        calls, _ = _run(decision)
        self.assertEqual(calls, ["synchronize", "empty_cache", "ipc_collect"])

    def test_flag_is_default_off_and_explicitly_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(bypass_enabled())
        with patch.dict(os.environ, {EMPTY_CACHE_BYPASS_FLAG: "1"}, clear=True):
            self.assertTrue(bypass_enabled())

    def test_all_source_reasons_are_explicit(self) -> None:
        self.assertEqual(
            SOFT_CACHE_REASONS,
            {
                "free_memory_after_unload",
                "free_memory_defensive_no_unload",
                "cleanup_models_gc_dead_model",
                "vae_oom_retry",
                "other",
            },
        )

    def test_decision_emits_runtime_trace_event(self) -> None:
        events: list[dict] = []

        class _Trace:
            def emit(self, name, *, phase, metadata):
                events.append({"name": name, "phase": phase, **metadata})

        variable = SimpleNamespace(get=lambda: _Trace())
        module = SimpleNamespace(_ACTIVE_REQUEST_TRACE=variable)
        with patch.dict(sys.modules, {"comfymodal_runtime.model_preload": module}):
            execute_soft_cache(
                _decision(),
                synchronize=lambda: None,
                empty_cache=lambda: self.fail("empty_cache must be skipped"),
                ipc_collect=lambda: None,
            )
        self.assertEqual(events[-1]["name"], "empty_cache_bypass_decision")
        self.assertEqual(events[-1]["phase"], "execution")
        self.assertFalse(events[-1]["empty_cache_executed"])


class TestE5NativeFailureBoundary(unittest.TestCase):
    def test_native_empty_cache_failure_is_not_swallowed(self) -> None:
        decision = _decision(soft_cache_reason="free_memory_after_unload")
        calls: list[str] = []

        def fail_empty() -> None:
            calls.append("empty_cache")
            raise RuntimeError("native allocation retry exhausted")

        with self.assertRaisesRegex(RuntimeError, "retry exhausted"):
            execute_soft_cache(
                decision,
                synchronize=lambda: calls.append("synchronize"),
                empty_cache=fail_empty,
                ipc_collect=lambda: calls.append("ipc_collect"),
            )
        self.assertEqual(calls, ["synchronize", "empty_cache"])


class TestE5SourceBranchWiring(unittest.TestCase):
    def test_pinned_comfy_source_passes_authoritative_reasons(self) -> None:
        comfy_root = Path(__file__).resolve().parents[3]
        source = (comfy_root / "comfy" / "model_management.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('soft_cache_reason="free_memory_after_unload"', source)
        self.assertIn('soft_cache_reason="free_memory_defensive_no_unload"', source)
        self.assertIn('soft_cache_reason="cleanup_models_gc_dead_model"', source)
        self.assertIn('soft_empty_cache(soft_cache_reason="other")', source)
        self.assertIn("minimum_memory_required=minimum_memory_required", source)
        self.assertIn("execute_soft_cache(", source)


if __name__ == "__main__":
    unittest.main()
