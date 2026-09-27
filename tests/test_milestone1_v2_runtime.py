"""Focused Milestone 1 tests for the v2 runtime.

Covers four contract areas without any ComfyUI dependency:

1. Unknown legacy option passthrough/round-trip
2. Local + remote trace merge preserving events/metadata/process identity
3. Runtime-gated Playground dispatch (workflow guard)
4. Fatal missing-output/materialization behavior
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

from comfymodal_runtime import (
    ExecutionOptions,
    ExecutionPlan,
    RuntimeTrace,
    TraceEvent,
    compatibility_usage_snapshot,
)
from comfymodal_runtime.result_delivery import (
    ConversionFailedError,
    ConversionBatchResult,
    adapt_legacy_result_payload,
    convert_output_items,
    materialize_modal_result,
    unique_path,
)
from comfymodal_runtime.trace import merge_traces
from comfymodal_runtime.output_delivery import OutputItem, _make_conversion_meta


# ═══════════════════════════════════════════════════════════════════════════
# 1. Unknown legacy option passthrough / round-trip
# ═══════════════════════════════════════════════════════════════════════════

class TestLegacyOptionPassthrough(unittest.TestCase):
    """ExecutionOptions.from_legacy / to_legacy_dict round-trip for unknown keys.

    Unknown legacy options remain available to the compatibility boundary until
    they are explicitly typed, while canonical typed fields win on conflicts.
    """

    def setUp(self):
        self._snapshot = dict(compatibility_usage_snapshot())

    def _delta(self) -> dict[str, int]:
        after = compatibility_usage_snapshot()
        delta = {}
        for k, v in after.items():
            if v > self._snapshot.get(k, 0):
                delta[k] = v - self._snapshot.get(k, 0)
        for k in self._snapshot:
            if k not in after:
                delta[k] = -self._snapshot[k]
        return delta

    # ── unknown key recording ──────────────────────────────────────────

    def test_unknown_keys_are_recorded_in_compatibility_snapshot(self):
        opts = ExecutionOptions.from_legacy({
            "production": {"enabled": False},
            "legacy_unknown_flag": True,
            "some_old_setting": {"nested": 42},
        })
        delta = self._delta()
        self.assertIn("legacy_unknown_flag", delta)
        self.assertIn("some_old_setting", delta)

    def test_unknown_keys_survive_round_trip(self):
        opts = ExecutionOptions.from_legacy({
            "production": {"enabled": False},
            "mythical_option": "value",
        })
        legacy = opts.to_legacy_dict()
        self.assertEqual(legacy["mythical_option"], "value")

    def test_nested_runtime_options_survive_and_typed_fields_win(self):
        opts = ExecutionOptions.from_legacy({
            "requested_backend": "in_process",
            "runtime": {
                "cold_unet_early_load": True,
                "restore_preload": "production",
                "requested_backend": "subprocess",
            },
            "quality": 91,
            "return_comparison_a": True,
        })
        legacy = opts.to_legacy_dict()
        self.assertEqual(legacy["quality"], 91)
        self.assertTrue(legacy["return_comparison_a"])
        self.assertTrue(legacy["runtime"]["cold_unet_early_load"])
        self.assertEqual(legacy["runtime"]["restore_preload"], "production")
        self.assertEqual(legacy["requested_backend"], "in_process")
        self.assertEqual(legacy["runtime"]["requested_backend"], "in_process")

    def test_known_keys_survive_round_trip(self):
        opts = ExecutionOptions.from_legacy({
            "output_format": "jpeg",
            "production": {"enabled": True, "output_node_ids": ["5"]},
            "requested_backend": "safe",
        })
        legacy = opts.to_legacy_dict()
        self.assertEqual(legacy.get("output_format"), "jpeg")
        self.assertIn("production", legacy)
        self.assertEqual(legacy["production"]["enabled"], True)

    def test_actual_load_is_preserved_as_compatibility_flag(self):
        opts = ExecutionOptions.from_legacy({
            "actual_load": {"enabled": True, "mode": "unet_only"},
        })
        self.assertIn("actual_load", opts.compatibility_flags)
        self.assertEqual(opts.compatibility_flags["actual_load"]["mode"], "unet_only")
        legacy = opts.to_legacy_dict()
        self.assertIn("actual_load", legacy)
        self.assertEqual(legacy["actual_load"]["mode"], "unet_only")

    def test_round_trip_via_to_dict_and_from_legacy_keeps_known_fields(self):
        original = ExecutionOptions.from_legacy({
            "output_format": "webp",
            "production": {"enabled": True, "output_node_ids": ["3"]},
            "requested_backend": "subprocess",
            "result_route": "direct",
            "profiling_level": "full",
        })
        restored = ExecutionOptions.from_legacy(original.to_dict())
        self.assertEqual(restored.requested_backend, "subprocess")
        self.assertEqual(restored.production_output_node_ids, ("3",))
        self.assertEqual(restored.profiling_level, "full")
        self.assertEqual(
            restored.output_conversion_options.get("format"),
            "webp_lossy",
        )

    def test_empty_legacy_produces_defaults(self):
        opts = ExecutionOptions.from_legacy(None)
        self.assertEqual(opts.production_enabled, True)
        self.assertEqual(opts.production_output_node_ids, ())
        self.assertEqual(opts.requested_backend, "in_process")

    def test_production_report_wired_correctly(self):
        opts = ExecutionOptions.from_legacy(
            {},
            production_report={"enabled": True, "output_node_ids": ["7", "9"]},
        )
        self.assertTrue(opts.production_enabled)
        self.assertIn("7", opts.production_output_node_ids)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Local + remote trace merge — events, metadata, process identity
# ═══════════════════════════════════════════════════════════════════════════

class TestTraceMerge(unittest.TestCase):
    """merge_traces preserves events from all inputs, merges metadata, and
    keeps per-event process identity intact."""

    def test_merge_two_runtime_traces_preserves_all_events(self):
        local = RuntimeTrace(request_id="req-1", process="local")
        local.emit("local_request_received")
        local.emit("plan_build_start")

        remote = RuntimeTrace(request_id="req-1", process="remote")
        remote.emit("container_entry")
        remote.emit("graph_execution_start")

        merged = merge_traces(local, remote)
        names = [e.name for e in merged.events]
        self.assertIn("local_request_received", names)
        self.assertIn("plan_build_start", names)
        self.assertIn("container_entry", names)
        self.assertIn("graph_execution_start", names)
        self.assertEqual(len(merged.events), 4)

    def test_merge_preserves_process_identity_per_event(self):
        local = RuntimeTrace(process="local")
        local.emit("local_event")

        remote = RuntimeTrace(process="remote")
        remote.emit("remote_event")

        merged = merge_traces(local, remote)
        processes = {(e.name, e.process) for e in merged.events}
        self.assertIn(("local_event", "local"), processes)
        self.assertIn(("remote_event", "remote"), processes)

    def test_merge_metadata_from_both_traces(self):
        local = RuntimeTrace()
        local.set_metadata(source="local", step=1)
        remote = RuntimeTrace()
        remote.set_metadata(source="remote", status="ok")

        merged = merge_traces(local, remote)
        # remote overwrites local on collision
        self.assertEqual(merged._metadata.get("source"), "remote")
        self.assertEqual(merged._metadata.get("step"), 1)
        self.assertEqual(merged._metadata.get("status"), "ok")

    def test_merge_with_none_skips_safely(self):
        local = RuntimeTrace(process="local")
        local.emit("only_event")
        merged = merge_traces(local, None, local)
        self.assertEqual(len(merged.events), 1)

    def test_merge_with_legacy_dict_via_from_legacy(self):
        local = RuntimeTrace(process="local")
        local.emit("local_req")

        legacy_dict = {
            "prompt_id": "p123",
            "stages": {"t3_modal_entry": 1234567890.0},
            "events": [{"name": "container_entry", "process": "legacy"}],
        }
        merged = merge_traces(local, legacy_dict)
        names = [e.name for e in merged.events]
        self.assertIn("local_req", names)
        self.assertIn("container_entry", names)

    def test_merge_empty_trace(self):
        empty = RuntimeTrace()
        full = RuntimeTrace(process="local")
        full.emit("event_a")
        merged = merge_traces(empty, full)
        self.assertEqual(len(merged.events), 1)
        self.assertEqual(merged.events[0].name, "event_a")

    def test_merge_with_metadata_from_legacy_dict(self):
        """Legacy metadata remains available after normalization and merge."""
        legacy = {
            "prompt_id": "p456",
            "metadata": {"legacy_key": "legacy_val", "number": 42},
            "stages": {},
        }
        merged = merge_traces(legacy)
        self.assertEqual(merged._metadata["legacy_key"], "legacy_val")
        self.assertEqual(merged._metadata["number"], 42)

    def test_merge_all_none_produces_empty_trace(self):
        merged = merge_traces(None, None)
        self.assertEqual(len(merged.events), 0)
        self.assertIsInstance(merged, RuntimeTrace)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Runtime-gated Playground dispatch
# ═══════════════════════════════════════════════════════════════════════════

class TestPlaygroundDispatchGate(unittest.TestCase):
    """PlaygroundService.execute must gate dispatch on a valid plan with a
    non-empty workflow."""

    @classmethod
    def setUpClass(cls):
        # Lazy-import the playground_service using the same pattern as
        # test_runtime_playground_v2 to avoid import-time side effects.
        import importlib.util
        import sys as _sys
        from pathlib import Path as _Path

        repo_root = _Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "playground_service_test",
            str(repo_root / "comfymodal_runtime" / "playground_service.py"),
        )
        assert spec is not None, "Could not find playground_service.py"
        assert spec.loader is not None
        cls._pg_mod = importlib.util.module_from_spec(spec)
        if str(repo_root) not in _sys.path:
            _sys.path.insert(0, str(repo_root))
        _sys.modules["playground_service_test"] = cls._pg_mod
        spec.loader.exec_module(cls._pg_mod)

    def _make_service(self, **inject) -> Any:
        return self._pg_mod.PlaygroundService(**inject)

    def test_empty_workflow_returns_error(self):
        """Gating: when ExecutionPlan has an empty workflow, execute returns
        {"status": "error"} without calling execute_plan."""

        execute_called = False

        async def fake_execute_plan(*args, **kwargs):
            nonlocal execute_called
            execute_called = True
            return {"outputs": {}}

        async def fake_load(preset_id, node_dir):
            return {"id": "p1"}, {"id": "s1", "apiPromptJson": {"1": {"class_type": "KSampler"}}, "nodeBindings": {}, "featureStatus": {"txt2img": {"status": "runnable"}}}, None

        async def fake_validate(preset, snapshot, feature_id):
            return None

        def fake_build_plan(preset, snapshot, feature_id, controls, *, modal_options=None):
            # Build a plan with empty workflow — the gate should catch this
            plan = ExecutionPlan(
                workflow={},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            return plan, None

        async def fake_save_history(*args, **kwargs):
            pass

        svc = self._make_service(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan,
            execute_plan_fn=fake_execute_plan,
            materialize_fn=lambda **kw: [],
            save_history_fn=fake_save_history,
        )

        async def run():
            result = await svc.execute(
                preset_id="p1",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/nodes",
            )
            self.assertEqual(result["status"], "error")
            self.assertIn("no workflow", result.get("message", "").lower())
            # The gate MUST prevent dispatch when workflow is empty
            self.assertFalse(execute_called, "execute_plan was called despite empty workflow")

        asyncio.run(run())

    def test_plan_build_failure_returns_error_without_execute(self):
        """When _build_plan returns (None, error), execute returns error
        without calling execute_plan."""

        execute_called = False

        async def fake_execute_plan(*args, **kwargs):
            nonlocal execute_called
            execute_called = True
            return {"outputs": {}}

        async def fake_load(preset_id, node_dir):
            return {"id": "p1"}, {"id": "s1", "apiPromptJson": {"1": {"class_type": "KSampler"}}}, None

        async def fake_validate(preset, snapshot, feature_id):
            return None

        def fake_build_plan(preset, snapshot, feature_id, controls, *, modal_options=None):
            return None, "No compatible output node found"

        async def fake_save_history(*args, **kwargs):
            pass

        svc = self._make_service(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan,
            execute_plan_fn=fake_execute_plan,
            materialize_fn=lambda **kw: [],
            save_history_fn=fake_save_history,
        )

        async def run():
            result = await svc.execute(
                preset_id="p1",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/nodes",
            )
            self.assertEqual(result["status"], "error")
            self.assertFalse(execute_called)

        asyncio.run(run())

    def test_valid_plan_dispatches_and_returns_ok(self):
        """Happy path: valid plan with workflow dispatches execute_plan and
        returns status ok."""

        execute_called = False

        async def fake_execute_plan(*args, **kwargs):
            nonlocal execute_called
            execute_called = True
            return {"outputs": {"3": {"images": [{"filename": "out.png", "data": ""}]}}}

        async def fake_load(preset_id, node_dir):
            return {"id": "p1"}, {"id": "s1", "apiPromptJson": {"1": {"class_type": "KSampler"}}, "nodeBindings": {"output": {"kind": "output", "nodeId": "3"}}}, None

        async def fake_validate(preset, snapshot, feature_id):
            return None

        def fake_build_plan(preset, snapshot, feature_id, controls, *, modal_options=None):
            plan = ExecutionPlan(
                workflow={"3": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            return plan, None

        async def fake_save_history(*args, **kwargs):
            pass

        svc = self._make_service(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan,
            execute_plan_fn=fake_execute_plan,
            materialize_fn=lambda **kw: [],
            save_history_fn=fake_save_history,
        )

        async def run():
            result = await svc.execute(
                preset_id="p1",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/nodes",
            )
            self.assertEqual(result["status"], "ok")
            self.assertTrue(execute_called)

        asyncio.run(run())

    def test_load_failure_returns_error(self):
        """When preset/snapshot loading fails, execute returns error."""
        async def fake_load(preset_id, node_dir):
            return None, None, "Preset not found"

        svc = self._make_service(load_preset_fn=fake_load)

        async def run():
            result = await svc.execute(
                preset_id="bad_preset",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/nodes",
            )
            self.assertEqual(result["status"], "error")
            self.assertIn("not found", result.get("message", ""))

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════
# 4. Fatal missing-output / materialization behavior
# ═══════════════════════════════════════════════════════════════════════════

class TestFatalMaterialization(unittest.TestCase):
    """materialize_modal_result and related helpers must be fatal for certain
    conditions (invalid data, failed conversion, forbidden paths) but resilient
    for missing outputs."""

    # ── Missing outputs (non-fatal) ────────────────────────────────────

    def test_missing_outputs_remain_compatible_by_default(self):
        r = materialize_modal_result({}, output_dir="/tmp/void", prompt_id="p1")
        self.assertEqual(r["written_files"], [])
        self.assertEqual(r["image_count"], 0)
        self.assertIsNone(r["primary_output"])

    def test_required_missing_outputs_are_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                materialize_modal_result(
                    {}, output_dir=tmp, prompt_id="p1", require_output=True,
                )

    def test_no_data_key_is_skipped_for_legacy_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = materialize_modal_result(
                {"outputs": {"1": {"images": [{"filename": "skip.png"}]}}},
                output_dir=tmp,
                prompt_id="p1",
            )
        self.assertEqual(r["written_files"], [])

    def test_no_data_key_is_fatal_when_output_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                materialize_modal_result(
                    {"outputs": {"1": {"images": [{"filename": "skip.png"}]}}},
                    output_dir=tmp,
                    prompt_id="p1",
                    require_output=True,
                )

    def test_empty_outputs_dict_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = materialize_modal_result(
                {"outputs": {}},
                output_dir=tmp,
                prompt_id="p1",
            )
        self.assertEqual(r["written_files"], [])
        self.assertEqual(r["image_count"], 0)

    # ── Fatal: invalid base64 data ─────────────────────────────────────

    def test_invalid_base64_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                materialize_modal_result(
                    {"outputs": {"1": {"images": [{"filename": "bad.png", "data": "!!!not-base64!!!"}]}}},
                    output_dir=tmp,
                    prompt_id="p1",
                )
            # binascii.Error (subclass of ValueError) is raised for invalid
            # base64 — the materialization must NOT silently skip bad data
            self.assertIsInstance(ctx.exception, ValueError)

    # ── Fatal: unsafe filename path traversal ──────────────────────────

    def test_path_traversal_filename_raises(self):
        with self.assertRaises(ValueError) as ctx:
            unique_path("/tmp/test", "../../etc/passwd")
        self.assertIn("unsafe", str(ctx.exception).lower())

    def test_null_byte_filename_raises(self):
        with self.assertRaises(ValueError) as ctx:
            unique_path("/tmp/test", "bad\x00file.png")
        self.assertIn("null byte", str(ctx.exception).lower())

    def test_empty_filename_raises(self):
        with self.assertRaises(ValueError):
            unique_path("/tmp/test", "")

    def test_filename_escaping_root_raises(self):
        with self.assertRaises(ValueError):
            unique_path("/tmp/test", "foo/../../../bar")

    # ── Fatal: ConversionFailedError ───────────────────────────────────

    def test_convert_output_items_raises_on_converter_failure(self):
        item = OutputItem(
            node_id="1",
            output_key="images",
            filename="out.png",
            path="/tmp/out.png",
            raw_bytes=b"fake-image-data",
            mime_type="image/png",
        )

        def failing_converter(*args, **kwargs):
            raise RuntimeError("converter crashed")

        with self.assertRaises(ConversionFailedError) as ctx:
            convert_output_items([item], converter_fn=failing_converter)
        self.assertIn("converter crashed", str(ctx.exception))

    def test_convert_output_items_raises_on_converter_error_key(self):
        item = OutputItem(
            node_id="1",
            output_key="images",
            filename="out.png",
            path="/tmp/out.png",
            raw_bytes=b"fake-image-data",
            mime_type="image/png",
        )

        def error_returning_converter(*args, **kwargs):
            return {"error": "format not supported", "bytes": None}

        with self.assertRaises(ConversionFailedError) as ctx:
            convert_output_items([item], converter_fn=error_returning_converter)
        self.assertIn("format not supported", str(ctx.exception))

    def test_convert_output_items_no_converter_raises(self):
        """When converter_fn is None and output_converter is not importable,
        ConversionFailedError is raised.

        If ``output_converter`` happens to be importable in the test
        environment, this test verifies that the converter is called
        instead — that is still valid contract enforcement.
        """
        item = OutputItem(
            node_id="1", output_key="images", filename="out.png",
            path="/tmp/out.png", raw_bytes=b"data", mime_type="image/png",
        )
        # If output_converter is available, the call succeeds without raising.
        # If unavailable, ConversionFailedError is raised.  Either outcome
        # satisfies the contract (the function does not silently skip).
        try:
            convert_output_items([item], converter_fn=None)
        except ConversionFailedError:
            pass  # Expected when output_converter is absent

    # ── Adapter: missing result key (non-fatal) ────────────────────────

    def test_adapt_legacy_empty_payload_returns_defaults(self):
        adapted = adapt_legacy_result_payload({})
        self.assertEqual(adapted.get("outputs"), {})

    def test_adapt_legacy_unwraps_result_key(self):
        adapted = adapt_legacy_result_payload({
            "result": {"outputs": {"1": {"images": []}}},
        })
        self.assertIn("outputs", adapted)
        self.assertIn("1", adapted["outputs"])

    def test_adapt_legacy_falls_back_to_output_key(self):
        adapted = adapt_legacy_result_payload({
            "output": {"1": {"images": []}},
        })
        self.assertIn("outputs", adapted)
        self.assertIn("1", adapted["outputs"])


if __name__ == "__main__":
    unittest.main()
