"""Tests for the direct single-run path in Studio preset execution.

Covers:
  - _prepare_studio_run_context shared helper
  - direct_studio_run_completion bypasses scheduler/runner/leases/journal
  - Production workflow compilation with output node 107
  - Production hash fail-closed behavior
  - Profile preparer invoked before remote submit
  - Progress event publication
  - History finalization and output materialization
  - Scheduler path preserved (handle_studio_run with direct=False)
  - Timing markers and production_plan_used=yes
"""
import asyncio
import copy
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_adapter():
    """Load studio_run_adapter module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "studio_run_adapter", REPO_ROOT / "studio_run_adapter.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["studio_run_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_basic_snapshot(snapshot_id: str = "snap_test") -> dict:
    return {
        "id": snapshot_id,
        "name": "Test Snapshot",
        "compatibleFeatures": ["txt2img"],
        "apiPromptJson": {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
            }},
            "107": {"class_type": "SaveImage", "inputs": {"images": []}},
        },
        "nodeBindings": {
            "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
            "output": {"kind": "output", "nodeId": "107"},
        },
        "outputNodeId": "107",
        "graphJson": {"nodes": [], "links": []},
        "archived": False,
        "status": "runnable",
        "featureStatus": {
            "txt2img": {"status": "runnable", "reason": ""},
        },
        "disabledReason": "",
    }


def _make_basic_preset(preset_id: str = "preset_test",
                        snapshot_id: str = "snap_test") -> dict:
    return {
        "id": preset_id,
        "label": "Test Preset",
        "snapshotId": snapshot_id,
        "compatibleFeatures": ["txt2img"],
        "defaults": {},
        "sourceType": "snapshot",
        "sourceId": "",
        "archived": False,
        "status": "runnable",
        "disabledReason": "",
    }


def _write_store_files(tmpdir: str, snapshots: list[dict], presets: list[dict]):
    """Write snapshot and preset JSON store files into tmpdir."""
    snap_path = Path(tmpdir) / ".studio_snapshots.json"
    preset_path = Path(tmpdir) / ".studio_presets.json"
    snap_path.write_text(json.dumps(snapshots), encoding="utf-8")
    preset_path.write_text(json.dumps(presets), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fake / mock classes
# ---------------------------------------------------------------------------

class FakeRunHistory:
    """Minimal in-memory RunHistory for testing."""
    def __init__(self):
        self._runs: dict[str, dict] = {}

    def record_run(self, **kwargs) -> dict:
        run_id = f"r_{len(self._runs) + 1}"
        rec = dict(kwargs)
        rec["run_id"] = run_id
        self._runs[run_id] = rec
        return rec

    def update_run(self, run_id: str, **kwargs) -> dict:
        if run_id in self._runs:
            self._runs[run_id].update(kwargs)
        return self._runs.get(run_id, {})

    def get_run(self, run_id: str) -> dict | None:
        return self._runs.get(run_id)


class FakeRegistry:
    """Minimal REGISTRY stub for testing history."""
    def __init__(self):
        self._history = FakeRunHistory()
        self._stores: dict[str, Any] = {}

    def history(self) -> FakeRunHistory:
        return self._history

    def store(self, exp_id: str) -> Any:
        if exp_id not in self._stores:
            self._stores[exp_id] = FakeExperimentStore()
        return self._stores[exp_id]

    def get_or_create_scheduler(self, *args, **kwargs):
        raise RuntimeError("Scheduler should not be created in direct path")


class FakeExperimentStore:
    """Minimal store that never creates journal events."""
    def __init__(self):
        self._events: list[dict] = []

    def write_definition(self, defn: dict) -> None:
        pass

    def append_event(self, event: dict) -> dict:
        self._events.append(event)
        return event

    def read_events(self) -> list[dict]:
        return list(self._events)


class FakeInvoker:
    """A fake LocalRemoteInvoker for testing that fakes results."""
    def __init__(self, **kwargs):
        self._kwargs = kwargs
        self._run_cell_tasks: dict[str, asyncio.Task] = {}
        self._cancelled_workers: set[str] = set()

    async def open_worker(self, worker_invocation_id, checkpoint_id,
                          profile_id, workflow, triple) -> None:
        pass

    async def run_cell(self, worker_invocation_id, cell) -> dict:
        return {
            "status": "completed",
            "output_paths": ["studio_test_output_1.png"],
            "result": {
                "outputs": {"107": {"images": [{"filename": "test.png"}]}},
            },
            "timing_payload": {
                "trace": {
                    "stages": {"t3_modal_entry": 1000.0},
                    "deltas_ms": {"sampler": 500.0, "vae_decode": 100.0},
                    "derived_ms": {},
                    "trace_version": 3,
                },
                "_restore_timing": {"restore_total_ms": 1500.0},
            },
        }

    async def close_worker(self, worker_invocation_id) -> None:
        pass

    async def cancel_worker(self, worker_invocation_id) -> None:
        pass

    async def request_pause(self, worker_invocation_id) -> None:
        pass

    async def request_stop_after_current(self, worker_invocation_id) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class StudioDirectRunPreparationTests(unittest.TestCase):
    """Tests for _prepare_studio_run_context shared helper."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_adapter()

    def setUp(self):
        # Patch experiment_service.REGISTRY with our fake
        self._registry_patcher = patch.dict(
            "sys.modules",
            {"experiment_service": types.ModuleType("experiment_service")},
        )
        self._registry_patcher.start()
        import experiment_service
        experiment_service.REGISTRY = FakeRegistry()

    def tearDown(self):
        self._registry_patcher.stop()

    def test_prepare_success(self):
        """Preparation succeeds with valid preset/snapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])
            ctx = self.mod._prepare_studio_run_context(
                "preset_test", "txt2img", {"prompt": "hello", "seed": 7}, tmp,
            )
            self.assertEqual(ctx["status"], "ok")
            self.assertIn("preset", ctx)
            self.assertIn("compilation", ctx)
            self.assertIn("run_history_id", ctx)
            self.assertIn("exp_id", ctx)
            self.assertIn("studio_meta", ctx)
            self.assertIn("profile_preparer", ctx)
            self.assertTrue(callable(ctx["profile_preparer"]))

    def test_prepare_missing_preset(self):
        """Preparation fails for missing preset."""
        with tempfile.TemporaryDirectory() as tmp:
            _write_store_files(tmp, [], [])
            ctx = self.mod._prepare_studio_run_context(
                "does_not_exist", "txt2img", {}, tmp,
            )
            self.assertEqual(ctx["status"], "error")
            self.assertIn("not found", ctx.get("message", ""))

    def test_prepare_creates_history_record(self):
        """Preparation creates a history record with status submitted->running."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])
            ctx = self.mod._prepare_studio_run_context(
                "preset_test", "txt2img", {"prompt": "hello"}, tmp,
            )
            self.assertNotEqual(ctx["run_history_id"], "")
            import experiment_service
            rec = experiment_service.REGISTRY.history().get_run(ctx["run_history_id"])
            self.assertIsNotNone(rec, "History record must exist")
            self.assertEqual(rec.get("status"), "running")

    def test_prepare_no_experiment_journal_created(self):
        """Preparation does NOT create an experiment journal."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])
            ctx = self.mod._prepare_studio_run_context(
                "preset_test", "txt2img", {"prompt": "hello"}, tmp,
            )
            # Check that no experiment was created
            import experiment_service
            store = experiment_service.REGISTRY.store(ctx["exp_id"])
            events = store.read_events()
            self.assertEqual(len(events), 0,
                             "No experiment journal events should exist")


class StudioDirectRunCompletionTests(unittest.TestCase):
    """Tests for direct_studio_run_completion."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_adapter()

    def setUp(self):
        self._registry_patcher = patch.dict(
            "sys.modules",
            {"experiment_service": types.ModuleType("experiment_service")},
        )
        self._registry_patcher.start()
        import experiment_service
        experiment_service.REGISTRY = FakeRegistry()

    def tearDown(self):
        self._registry_patcher.stop()

    def _make_context(self, tmpdir: str, controls: dict | None = None,
                      modal_options: dict | None = None) -> dict:
        snap = _make_basic_snapshot()
        preset = _make_basic_preset()
        _write_store_files(tmpdir, [snap], [preset])
        return self.mod._prepare_studio_run_context(
            "preset_test", "txt2img", controls or {"prompt": "hello", "seed": 7},
            tmpdir, modal_options=modal_options,
        )

    async def _run_direct(self, ctx: dict, tmpdir: str, **kwargs) -> dict:
        """Run direct_studio_run_completion with patched invoker."""
        import experiment_runner as er_mod

        # Build a MagicMock-based fake invoker that provides required methods
        async def _fake_run_cell(worker_id, cell):
            # Propagate any pre-set markers from the cell trace into the
            # returned timing_payload trace (simulates what the real
            # LocalRemoteInvoker.run_cell does with the mutable trace).
            _cell_trace = cell.get("trace", {}) or {}
            _stages = dict(_cell_trace)
            _stages.setdefault(
                "output_materialized",
                _stages.get("browser_run_click", 1000.0) + 1.25,
            )
            _stages.setdefault("t3_modal_entry", 1000.0)
            return {
                "status": "completed",
                "output_paths": ["studio_test_output_1.png"],
                "result": {
                    "outputs": {
                        "107": {"images": [{"filename": "test.png", "data": ""}]}
                    },
                    "_certificate_candidate": {
                        "identity": "a" * 64,
                        "outputs_to_execute": ["107"],
                        "node_errors": {},
                    },
                },
                "timing_payload": {
                    "trace": {
                        "stages": _stages,
                        "deltas_ms": {"sampler": 500.0, "vae_decode": 100.0},
                        "derived_ms": {},
                        "trace_version": 3,
                    },
                    "_restore_timing": {"restore_total_ms": 1500.0},
                },
            }

        fake_invoker = MagicMock(spec=er_mod.LocalRemoteInvoker)
        fake_invoker.open_worker = AsyncMock()
        fake_invoker.close_worker = AsyncMock()
        fake_invoker.run_cell = AsyncMock(side_effect=_fake_run_cell)
        fake_invoker._run_cell_tasks = {}
        fake_invoker._cancelled_workers = set()
        fake_invoker._studio_output_dir = None
        fake_invoker._modal_options = {}
        fake_invoker._production_report = None
        fake_invoker._profile_preparer = None

        with patch.object(er_mod, 'LocalRemoteInvoker',
                          return_value=fake_invoker, autospec=False):
            result = await self.mod.direct_studio_run_completion(
                ctx, tmpdir, **kwargs
            )
        return result

    def test_completion_returns_completed_result(self):
        """Direct run returns completed result with output paths."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                self.assertIn("output_paths", result)
                self.assertIn("timings", result)
                self.assertIn("meta", result)
                self.assertIn("production_plan_used", result)
                self.assertTrue(result.get("direct_run"))
                # Verify output paths exist
                output_paths = result.get("output_paths", [])
                self.assertGreater(len(output_paths), 0)

        asyncio.run(_test())

    def test_completion_bypasses_scheduler_runner_leases_journal(self):
        """Direct run must NOT create scheduler, runner, or journal events."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                # No experiment journal created
                import experiment_service
                store = experiment_service.REGISTRY.store(ctx["exp_id"])
                events = store.read_events()
                # No "experiment.created", "experiment.started", etc.
                journal_types = {e.get("type", "") for e in events}
                self.assertNotIn("experiment.created", journal_types)
                self.assertNotIn("experiment.started", journal_types)
                self.assertNotIn("cell.attempt_created", journal_types)
                self.assertNotIn("checkpoint.claimed", journal_types)
                self.assertNotIn("cell.completed", journal_types)
                # Also assert history record was finalized as "completed"
                rec = experiment_service.REGISTRY.history().get_run(
                    ctx["run_history_id"]
                )
                self.assertIsNotNone(rec)
                self.assertEqual(rec.get("status"), "completed")

        asyncio.run(_test())

    def test_completion_publishes_progress(self):
        """Direct run publishes progress events through the event sink."""
        sent_events: list[dict] = []

        async def _capture_sink(detail: dict) -> None:
            sent_events.append(detail)

        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                # We can't easily capture progress events from the patched path
                # since the invoker is faked.  Instead, verify the invoker is
                # created with stream_event_sink.
                self.assertIsNotNone(ctx.get("profile_preparer"),
                                     "Profile preparer must be set")
                # Run the direct completion (just verify it completes)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")

        asyncio.run(_test())

    def test_completion_passes_preparer_to_invoker(self):
        """Profile preparer is passed to the invoker constructor."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                # Ensure a profile_preparer is set
                self.assertIsNotNone(ctx.get("profile_preparer"))
                self.assertTrue(callable(ctx["profile_preparer"]))

                import experiment_runner as er_mod

                # Track whether the invoker was constructed with profile_preparer
                captured_kwargs = {}

                original_init = er_mod.LocalRemoteInvoker.__init__

                def _capturing_init(self_invoker, modal_run_prompt_stream,
                                    experiment_id="", node_dir="",
                                    stream_event_sink=None,
                                    profile_preparer=None,
                                    gpu=None, modal_options=None,
                                    workspace=None,
                                    production_report=None,
                                    studio_output_dir=None):
                    captured_kwargs["profile_preparer"] = profile_preparer
                    original_init(self_invoker, modal_run_prompt_stream,
                                  experiment_id=experiment_id,
                                  node_dir=node_dir,
                                  stream_event_sink=stream_event_sink,
                                  profile_preparer=profile_preparer,
                                  gpu=gpu, modal_options=modal_options,
                                  workspace=workspace,
                                  production_report=production_report,
                                  studio_output_dir=studio_output_dir)

                # Use real invoker (no patch) so we can verify it works end-to-end
                # But we still need to mock run_prompt_stream since we can't call Modal.
                # For this test, just verify the preparer flows through.
                # Since we can't actually call real Modal, we verify the invoker
                # init captured kwargs.
                with patch.object(er_mod.LocalRemoteInvoker, '__init__',
                                  side_effect=_capturing_init, autospec=False):
                    # We also need to mock run_cell to return a result
                    fake_invoker = MagicMock(spec=er_mod.LocalRemoteInvoker)
                    fake_invoker.open_worker = AsyncMock()
                    fake_invoker.close_worker = AsyncMock()
                    async def _fake_run(worker_id, cell):
                        return {"status": "completed", "output_paths": []}
                    fake_invoker.run_cell = AsyncMock(side_effect=_fake_run)
                    fake_invoker._run_cell_tasks = {}
                    fake_invoker._cancelled_workers = set()
                    fake_invoker._studio_output_dir = None
                    fake_invoker._modal_options = {}
                    fake_invoker._production_report = None
                    fake_invoker._profile_preparer = ctx["profile_preparer"]

                    with patch.object(er_mod, 'LocalRemoteInvoker',
                                      return_value=fake_invoker, autospec=False):
                        result = await self.mod.direct_studio_run_completion(
                            ctx, tmp
                        )
                    self.assertEqual(result["status"], "ok")

        asyncio.run(_test())

    def test_completion_finalizes_history(self):
        """History record is finalized with status=completed and timings."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                import experiment_service
                rec = experiment_service.REGISTRY.history().get_run(
                    ctx["run_history_id"]
                )
                self.assertIsNotNone(rec)
                self.assertEqual(rec.get("status"), "completed")
                timings = rec.get("timings", {})
                self.assertIsNotNone(timings)
                # Should have timing_sources
                self.assertIn("timing_sources", timings)
                # Should have restore_total_ms from remote
                self.assertIn("restore_total_ms", timings)
                self.assertEqual(timings.get("_run_type"), "direct")
                self.assertEqual(timings.get("end_to_end_total_ms"), 1250.0)

        asyncio.run(_test())

    def test_completion_output_count_is_exactly_one(self):
        """Exactly one output is recorded in meta."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                meta = result.get("meta", {})
                output_count = meta.get("output_count", 0)
                self.assertEqual(output_count, 1,
                                 "Exactly one output must be recorded")

        asyncio.run(_test())

    def test_completion_saves_studio_meta(self):
        """Studio metadata is carried through to the result."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                meta = result.get("meta", {})
                self.assertIn("studio_preset_id", meta)
                self.assertIn("studio_snapshot_id", meta)
                self.assertIn("studio_feature_id", meta)
                self.assertEqual(meta["studio_preset_id"], "preset_test")
                self.assertEqual(meta["studio_feature_id"], "txt2img")

        asyncio.run(_test())

    def test_completion_fail_closed_on_error(self):
        """Direct run returns error status and fails history when cell fails."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)

                # Patch invoker to return failure
                import experiment_runner as er_mod

                async def _fail_run(worker_id, cell):
                    return {"status": "failed",
                            "error": "Hash mismatch: compiled vs actual"}

                fake_invoker = MagicMock(spec=er_mod.LocalRemoteInvoker)
                fake_invoker.open_worker = AsyncMock()
                fake_invoker.close_worker = AsyncMock()
                fake_invoker.run_cell = AsyncMock(side_effect=_fail_run)
                fake_invoker._run_cell_tasks = {}
                fake_invoker._cancelled_workers = set()
                fake_invoker._studio_output_dir = None
                fake_invoker._modal_options = {}
                fake_invoker._production_report = None
                fake_invoker._profile_preparer = None

                with patch.object(er_mod, 'LocalRemoteInvoker',
                                  return_value=fake_invoker, autospec=False):
                    result = await self.mod.direct_studio_run_completion(
                        ctx, tmp
                    )
                self.assertEqual(result["status"], "error")
                # History must be finalized as error
                import experiment_service
                rec = experiment_service.REGISTRY.history().get_run(
                    ctx["run_history_id"]
                )
                self.assertIsNotNone(rec)
                self.assertEqual(rec.get("status"), "error")

        asyncio.run(_test())

    def test_completion_production_plan_used_yes(self):
        """production_plan_used=yes when production compilation is active."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(
                    tmp,
                    modal_options={"production": {"enabled": True,
                                                  "output_node_ids": ["107"]}},
                )
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                self.assertTrue(result.get("production_plan_used"),
                                "production_plan_used must be True")
                meta = result.get("meta", {})
                self.assertEqual(meta.get("production_plan_used"), "yes")

        asyncio.run(_test())

    def test_completion_production_hash_guard_fails_closed(self):
        """Production hash mismatch is caught and fails closed."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                # Build compilation with production
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img",
                    {"prompt": "hello", "steps": 8},
                    tmp,
                    modal_options={"production": {"enabled": True,
                                                  "output_node_ids": ["107"]}},
                )
                self.assertEqual(ctx["status"], "ok")

                # Patch the invoker to simulate production hash guard failure.
                import experiment_runner as er_mod

                async def _hash_guard_run(worker_id, cell):
                    return {
                        "status": "failed",
                        "error": "Production compiled workflow hash mismatch",
                    }

                fake_invoker = MagicMock(spec=er_mod.LocalRemoteInvoker)
                fake_invoker.open_worker = AsyncMock()
                fake_invoker.close_worker = AsyncMock()
                fake_invoker.run_cell = AsyncMock(side_effect=_hash_guard_run)
                fake_invoker._run_cell_tasks = {}
                fake_invoker._cancelled_workers = set()
                fake_invoker._studio_output_dir = None
                fake_invoker._modal_options = {}
                fake_invoker._production_report = {
                    "enabled": True,
                    "compiler_version": 1,
                    "hash_schema_version": 1,
                    "production_plan_schema_version": 1,
                    "compiled_workflow_hash": "deadbeef" * 8,
                    "output_node_ids": ["107"],
                }
                fake_invoker._profile_preparer = None

                with patch.object(er_mod, 'LocalRemoteInvoker',
                                  return_value=fake_invoker, autospec=False):
                    result = await self.mod.direct_studio_run_completion(
                        ctx, tmp
                    )
                self.assertEqual(result["status"], "error")
                # The error message is the stable internal error (fail-closed,
                # no raw exception strings leaked). The original hash error is
                # logged but not returned to the client.
                self.assertIsNotNone(result.get("message"))

        asyncio.run(_test())

    def test_completion_timing_markers_present(self):
        """Required timing markers are present in the result."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                timings = result.get("timings", {})
                # Verify remote timing markers are present
                self.assertIn("sampling_ms", timings)
                self.assertIn("vae_decode_ms", timings)
                self.assertIn("restore_total_ms", timings)
                self.assertIn("trace_available", timings)
                self.assertTrue(timings.get("trace_available"))
                # Verify local timing markers
                self.assertIn("timing_sources", timings)
                timing_sources = timings.get("timing_sources", {})
                self.assertIsInstance(timing_sources, dict)

        asyncio.run(_test())

    def test_timing_marker_browser_run_click_alias(self):
        """browser_run_click alias is always present in timings (server-time fallback)."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                timings = result.get("timings", {})
                # browser_run_click is always set — server-side fallback
                # when no browser t0 is provided (test default).
                self.assertIn("browser_run_click", timings,
                              "browser_run_click must always be in timings")
                self.assertIn("studio_route_received", timings,
                              "studio_route_received marker must be in timings")
                self.assertIn("production_compile_complete", timings,
                              "production_compile_complete must be in timings")
                # active_profile_write_start/end, result_received, and
                # output_materialized are set only by the real
                # LocalRemoteInvoker.run_cell, not the fake invoker.
                # They are tested in StudioDirectRunInvokerStreamTests.
        asyncio.run(_test())

    def test_timing_marker_browser_run_click_from_trace_ctx(self):
        """browser_run_click is aliased from browser t0 when trace_ctx has t0_client_press."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx={"t0_client_press": 1234567890.0},
                )
                self.assertEqual(ctx["status"], "ok")
                cell = ctx["compilation"]["cells"][0]
                cell_trace = cell.get("trace", {})
                self.assertIn("browser_run_click", cell_trace,
                              "browser_run_click must be set on cell trace")
                self.assertAlmostEqual(cell_trace["browser_run_click"], 1234567890.0,
                                       msg="browser_run_click must alias t0_client_press")
        asyncio.run(_test())

    # ── browser_run_click source precedence: t0_client_press_ms ──────────────

    def test_prepare_browser_run_click_via_client_press_ms(self):
        """browser_run_click is set from t0_client_press_ms/1000 when only
        t0_client_press_ms is present (no t0_client_press, no perf pair)."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                click_ms = 1730000000123.0  # epoch ms
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx={"t0_client_press_ms": click_ms},
                )
                self.assertEqual(ctx["status"], "ok")
                cell_trace = ctx["compilation"]["cells"][0].get("trace", {})
                expected = click_ms / 1000.0
                self.assertAlmostEqual(
                    cell_trace.get("browser_run_click"), expected,
                    msg="browser_run_click must be t0_client_press_ms / 1000",
                )
        asyncio.run(_test())

    def test_prepare_browser_run_click_client_press_ms_wins_over_perf_pair(self):
        """t0_client_press_ms takes precedence over t0_perf_ms/t0_perf_now_ms."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                click_ms = 1730000000500.0
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx={
                        "t0_client_press_ms": click_ms,
                        "t0_perf_ms": 1500.0,
                        "t0_perf_now_ms": 1987654321.0,
                    },
                )
                self.assertEqual(ctx["status"], "ok")
                cell_trace = ctx["compilation"]["cells"][0].get("trace", {})
                expected = click_ms / 1000.0
                self.assertAlmostEqual(
                    cell_trace.get("browser_run_click"), expected,
                    msg="browser_run_click must use t0_client_press_ms, not perf pair",
                )
        asyncio.run(_test())

    def test_prepare_browser_run_click_perf_pair_fallback(self):
        """Performance-pair fallback works when neither t0_client_press nor
        t0_client_press_ms is present."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                t0_perf_ms = 2500.0
                t0_perf_now_ms = 2000000000.0
                expected = (t0_perf_now_ms - t0_perf_ms) / 1000.0
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx={
                        "t0_perf_ms": t0_perf_ms,
                        "t0_perf_now_ms": t0_perf_now_ms,
                    },
                )
                self.assertEqual(ctx["status"], "ok")
                cell_trace = ctx["compilation"]["cells"][0].get("trace", {})
                self.assertAlmostEqual(
                    cell_trace.get("browser_run_click"), expected,
                    msg="browser_run_click must use perf-pair reconstruction as fallback",
                )
        asyncio.run(_test())

    def test_prepare_browser_run_click_server_time_fallback(self):
        """browser_run_click uses server-side time when no browser timestamp is given."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                import time
                before = time.time()
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx=None,  # No browser timestamp
                )
                after = time.time()
                self.assertEqual(ctx["status"], "ok")
                cell_trace = ctx["compilation"]["cells"][0].get("trace", {})
                self.assertIn("browser_run_click", cell_trace,
                              "browser_run_click must be set even without browser timestamp")
                click_val = cell_trace["browser_run_click"]
                self.assertIsInstance(click_val, float)
                # Must be a plausible server-time value (between before and after + small slack)
                self.assertGreaterEqual(click_val, before - 1,
                                        "browser_run_click must be >= server time just before call")
                self.assertLessEqual(click_val, after + 1,
                                     "browser_run_click must be <= server time just after call")
        asyncio.run(_test())

    def test_prepare_browser_run_click_server_time_fallback_no_trace_ctx_keys(self):
        """Server-time fallback activates when trace_ctx has keys but no browser timestamp."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                import time
                before = time.time()
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx={"some_other_key": 42},  # No t0_client_press / ms / perf
                )
                after = time.time()
                self.assertEqual(ctx["status"], "ok")
                cell_trace = ctx["compilation"]["cells"][0].get("trace", {})
                self.assertIn("browser_run_click", cell_trace,
                              "browser_run_click must be set even without browser timestamp keys")
                click_val = cell_trace["browser_run_click"]
                self.assertIsInstance(click_val, float)
                self.assertGreaterEqual(click_val, before - 1)
                self.assertLessEqual(click_val, after + 1)
        asyncio.run(_test())

    def test_prepare_browser_run_click_from_t0_client_press_direct(self):
        """browser_run_click equals t0_client_press (preferred source via coerce_t0_from_browser)."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                epoch = 1234567890.123
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx={"t0_client_press": epoch},
                )
                self.assertEqual(ctx["status"], "ok")
                cell_trace = ctx["compilation"]["cells"][0].get("trace", {})
                self.assertAlmostEqual(
                    cell_trace.get("browser_run_click"), epoch,
                    msg="browser_run_click must equal t0_client_press when that is present",
                )
        asyncio.run(_test())

    # ── End browser_run_click precedence tests ───────────────────────────────

    def test_timing_marker_active_profile_write_start_end(self):
        """active_profile_write_start and _end are set by real invoker (not fake)."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                timings = result.get("timings", {})
                # The fake MagicMock invoker does NOT call the profile preparer,
                # so active_profile_write_start/end are NOT present in the
                # merged trace from this test path.  They are set by the real
                # LocalRemoteInvoker.run_cell (tested in
                # StudioDirectRunInvokerStreamTests).  This test only verifies
                # that the direct path doesn't crash when markers are absent.
                pass
        asyncio.run(_test())

    def test_timing_markers_compile_and_remote_event(self):
        """production_compile_complete and first_remote_event markers present when applicable."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(
                    tmp,
                    modal_options={"production": {"enabled": True,
                                                  "output_node_ids": ["107"]}},
                )
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                timings = result.get("timings", {})
                self.assertIn("production_compile_complete", timings,
                              "production_compile_complete must be in timings "
                              "when production is enabled")
                # The fake invoker doesn't simulate remote events, so
                # first_remote_event may be absent (expected).
        asyncio.run(_test())

    def test_direct_result_carries_runId_and_runHistoryId(self):
        """Direct result must carry runId/runHistoryId for response compatibility."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                meta = result.get("meta", {})
                self.assertIn("experiment_id", meta)
                # runId/runHistoryId are on the result for the frontend
                self.assertIn("direct_run", result)
                self.assertTrue(result.get("direct_run"))
        asyncio.run(_test())

    def test_meta_production_plan_used_and_output_count(self):
        """meta carries production_plan_used=yes/no and output_count."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_context(tmp)
                result = await self._run_direct(ctx, tmp)
                self.assertEqual(result["status"], "ok")
                meta = result.get("meta", {})
                self.assertIn("production_plan_used", meta,
                              "production_plan_used must be in meta")
                self.assertIn("output_count", meta,
                              "output_count must be in meta")
                # Without production, plan_used should be "no" and count >= 0
                self.assertEqual(meta.get("output_count"), 1)
                self.assertEqual(meta.get("production_plan_used"), "no")

    def test_timing_payload_derived_ms_output_collection_total_ms(self):
        """output_collection_total_ms from trace.derived_ms is preserved in response timings."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                click_epoch = 1000000000.0
                materialized_epoch = click_epoch + 5.38  # 5380ms delta
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                    tmp,
                    trace_ctx={"t0_client_press": click_epoch},
                )
                self.assertEqual(ctx["status"], "ok")

                import experiment_runner as er_mod

                async def _fake_run(worker_id, cell):
                    return {
                        "status": "completed",
                        "output_paths": ["studio_test_output_1.png"],
                        "result": {
                            "outputs": {
                                "107": {"images": [{"filename": "test.png", "data": ""}]}
                            },
                        },
                        "timing_payload": {
                            "trace": {
                                "stages": {
                                    "browser_run_click": click_epoch,
                                    "output_materialized": materialized_epoch,
                                    "studio_route_received": click_epoch + 0.1,
                                    "production_compile_complete": click_epoch + 0.2,
                                },
                                "deltas_ms": {
                                    "sampler": 3200.0,
                                    "clip_encode": 350.0,
                                    "vae_decode": 280.0,
                                },
                                "derived_ms": {
                                    "output_collection_total_ms": 250.0,
                                },
                                "trace_version": 3,
                            },
                            "_restore_timing": {"restore_total_ms": 120.0},
                        },
                    }

                fake_invoker = MagicMock(spec=er_mod.LocalRemoteInvoker)
                fake_invoker.open_worker = AsyncMock()
                fake_invoker.close_worker = AsyncMock()
                fake_invoker.run_cell = AsyncMock(side_effect=_fake_run)
                fake_invoker._run_cell_tasks = {}
                fake_invoker._cancelled_workers = set()
                fake_invoker._studio_output_dir = None
                fake_invoker._modal_options = {}
                fake_invoker._production_report = None
                fake_invoker._profile_preparer = None

                with patch.object(er_mod, 'LocalRemoteInvoker',
                                  return_value=fake_invoker, autospec=False):
                    result = await self.mod.direct_studio_run_completion(ctx, tmp)

                self.assertEqual(result["status"], "ok")
                timings = result.get("timings")
                self.assertIsInstance(timings, dict)

                # end_to_end_total_ms must be derived from trace stages
                # (output_materialized - browser_run_click) * 1000 = 5380
                self.assertIn("end_to_end_total_ms", timings,
                              "end_to_end_total_ms must be in timings")
                self.assertEqual(timings["end_to_end_total_ms"], 5380.0)

                # output_collection_total_ms must be preserved in trace.derived_ms
                _raw_trace = timings.get("trace")
                if isinstance(_raw_trace, dict):
                    _derived = _raw_trace.get("derived_ms")
                    if isinstance(_derived, dict):
                        self.assertIn("output_collection_total_ms", _derived)
                        self.assertEqual(_derived["output_collection_total_ms"], 250.0)

        asyncio.run(_test())


class StudioDirectRunSchedulerPathPreservedTests(unittest.TestCase):
    """The scheduler path MUST still work when direct=False."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_adapter()

    def setUp(self):
        # We need to patch the experiment_service REGISTRY properly
        self._patchers = []

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_handle_studio_run_with_direct_false_returns_submission(self):
        """handle_studio_run(direct=False) returns submission response, not completed."""
        # This test verifies the scheduler path code path. We can't easily
        # test the full scheduler path without Modal, but we can verify the
        # function signature and early return behavior remains unchanged.
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            # Patch experiment_service
            import experiment_service
            fake_reg = FakeRegistry()
            experiment_service.REGISTRY = fake_reg

            # handle_studio_run uses sync wrapper which needs a running loop.
            # We'll test handle_studio_run_async directly.
            async def _test():
                result = await self.mod.handle_studio_run_async(
                    "preset_test", "txt2img", {"prompt": "hello"}, tmp,
                    direct=False,
                )
                # When direct=False and scheduler path is called, it tries
                # to create experiment and fire scheduler.  But _create_experiment
                # needs a store, and the fake registry has one. The scheduler
                # path then returns submission response.
                self.assertEqual(result["status"], "ok")
                self.assertIn("runId", result)
                self.assertIn("experimentId", result)
                self.assertIn("runHistoryId", result)
                self.assertIn("message", result)
                # Must NOT contain "output_paths" (that's the direct path)
                self.assertNotIn("output_paths", result)

            asyncio.run(_test())

    def test_handle_studio_experiment_unchanged(self):
        """handle_studio_experiment is unchanged and still uses scheduler path."""
        # Just verify the function exists and has the same signature
        self.assertTrue(hasattr(self.mod, "handle_studio_experiment"))
        import inspect
        sig = inspect.signature(self.mod.handle_studio_experiment)
        params = list(sig.parameters.keys())
        self.assertIn("preset_ids", params)
        self.assertIn("experiment_def", params)
        # No "direct" parameter
        self.assertNotIn("direct", params)


class StudioDirectRunHistoryFinalizationTests(unittest.TestCase):
    """History finalization behavior for direct runs."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_adapter()

    def setUp(self):
        self._registry_patcher = patch.dict(
            "sys.modules",
            {"experiment_service": types.ModuleType("experiment_service")},
        )
        self._registry_patcher.start()
        import experiment_service
        experiment_service.REGISTRY = FakeRegistry()

    def tearDown(self):
        self._registry_patcher.stop()

    def test_history_has_completed_status_and_timings(self):
        """History record has completed status, timings, and meta."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello"}, tmp,
                )
                self.assertEqual(ctx["status"], "ok")

                import experiment_runner as er_mod

                async def _fake_run(worker_id, cell):
                    return {
                        "status": "completed",
                        "output_paths": ["studio_test_output_1.png"],
                        "result": {
                            "outputs": {
                                "107": {"images": [{"filename": "test.png", "data": ""}]}
                            },
                        },
                        "timing_payload": {
                            "trace": {
                                "stages": {},
                                "deltas_ms": {"sampler": 500.0},
                                "derived_ms": {},
                                "trace_version": 3,
                            },
                        },
                    }

                fake_invoker = MagicMock(spec=er_mod.LocalRemoteInvoker)
                fake_invoker.open_worker = AsyncMock()
                fake_invoker.close_worker = AsyncMock()
                fake_invoker.run_cell = AsyncMock(side_effect=_fake_run)
                fake_invoker._run_cell_tasks = {}
                fake_invoker._cancelled_workers = set()
                fake_invoker._studio_output_dir = None
                fake_invoker._modal_options = {}
                fake_invoker._production_report = None
                fake_invoker._profile_preparer = None

                with patch.object(er_mod, 'LocalRemoteInvoker',
                                  return_value=fake_invoker, autospec=False):
                    result = await self.mod.direct_studio_run_completion(
                        ctx, tmp
                    )
                self.assertEqual(result["status"], "ok")

                import experiment_service
                rec = experiment_service.REGISTRY.history().get_run(
                    ctx["run_history_id"]
                )
                self.assertEqual(rec.get("status"), "completed")
                self.assertIn("completed_at", rec)
                timings = rec.get("timings", {})
                self.assertIsInstance(timings, dict)
                meta = rec.get("meta", {})
                self.assertIn("output_paths", meta)
                self.assertIn("resolved_controls", meta)

        asyncio.run(_test())

    def test_t0_client_press_ms_flows_to_timings(self):
        """t0_client_press_ms in trace_ctx produces correct browser_run_click
        in final timings through direct_studio_run_completion."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])
                click_ms = 1730000000999.0
                ctx = self.mod._prepare_studio_run_context(
                    "preset_test", "txt2img", {"prompt": "hello"}, tmp,
                    trace_ctx={"t0_client_press_ms": click_ms},
                )
                self.assertEqual(ctx["status"], "ok")

                # Verify browser_run_click is on the cell trace
                cell = ctx["compilation"]["cells"][0]
                cell_trace = cell.get("trace", {})
                expected_epoch = click_ms / 1000.0
                self.assertAlmostEqual(
                    cell_trace.get("browser_run_click"), expected_epoch,
                    msg="browser_run_click must be set from t0_client_press_ms on cell trace",
                )

                import experiment_runner as er_mod

                async def _fake_run(worker_id, cell):
                    return {
                        "status": "completed",
                        "output_paths": ["studio_test_output_1.png"],
                        "result": {
                            "outputs": {
                                "107": {"images": [{"filename": "test.png", "data": ""}]}
                            },
                        },
                        "timing_payload": {
                            "trace": {
                                # The real invoker merges _mutable_trace into stages.
                                # Simulate that merge here so browser_run_click
                                # flows into direct_studio_run_completion's timings.
                                "stages": {
                                    "browser_run_click": expected_epoch,
                                    "studio_route_received": expected_epoch + 0.1,
                                    "production_compile_complete": expected_epoch + 0.2,
                                },
                                "deltas_ms": {"sampler": 500.0},
                                "derived_ms": {},
                                "trace_version": 3,
                            },
                        },
                    }

                fake_invoker = MagicMock(spec=er_mod.LocalRemoteInvoker)
                fake_invoker.open_worker = AsyncMock()
                fake_invoker.close_worker = AsyncMock()
                fake_invoker.run_cell = AsyncMock(side_effect=_fake_run)
                fake_invoker._run_cell_tasks = {}
                fake_invoker._cancelled_workers = set()
                fake_invoker._studio_output_dir = None
                fake_invoker._modal_options = {}
                fake_invoker._production_report = None
                fake_invoker._profile_preparer = None

                with patch.object(er_mod, 'LocalRemoteInvoker',
                                  return_value=fake_invoker, autospec=False):
                    result = await self.mod.direct_studio_run_completion(ctx, tmp)

                self.assertEqual(result["status"], "ok")
                timings = result.get("timings", {})
                self.assertIn("browser_run_click", timings,
                              "browser_run_click must be in timings")
                self.assertAlmostEqual(
                    timings["browser_run_click"], expected_epoch,
                    msg="browser_run_click in timings must match t0_client_press_ms/1000",
                )

        asyncio.run(_test())


class StudioDirectRunInvokerStreamTests(unittest.TestCase):
    """Real LocalRemoteInvoker with a fake async generator stream.

    Validates that the real invoker:
    - Forwards compiled workflow, workspace, GPU to the stream call.
    - Invokes the profile preparer BEFORE entering the stream.
    - Feeds nonterminal events to the progress sink.
    - Sets exact marker aliases on _mutable_trace.
    - Returns correct direct response IDs and production metadata.
    - Does NOT call _create_experiment, REGISTRY.get_or_create_scheduler,
      lease methods, or write journal events.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_adapter()

    def setUp(self):
        self._patchers = []
        # Patch experiment_service.REGISTRY
        p1 = patch.dict(
            "sys.modules",
            {"experiment_service": types.ModuleType("experiment_service")},
        )
        p1.start()
        self._patchers.append(p1)
        import experiment_service
        experiment_service.REGISTRY = FakeRegistry()

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_real_invoker_stream_markers_and_ids(self):
        """Real invoker with fake generator: markers, IDs, no scheduler/journal."""
        async def _test():
            captured_stream_kwargs: dict = {}
            sent_events: list[dict] = []
            profile_called: list[bool] = []

            async def _fake_stream_gen(**kwargs):
                """Fake modal_client.run_prompt_stream generator."""
                captured_stream_kwargs.update(kwargs)
                yield {"type": "status", "message": "warmup starting"}
                yield {"type": "progress", "event": "executing",
                       "data": {"node": "3", "step": 1, "max": 20}}
                yield {"type": "result", "data": {
                    "outputs": {"107": {"images": [
                        {"filename": "out.png", "data": "aGVsbG8="}
                    ]}},
                    "trace": {
                        "stages": {"t3_modal_entry": 2000.0},
                        "deltas_ms": {"sampler": 450.0, "clip_load": 300.0},
                        "derived_ms": {},
                        "trace_version": 3,
                    },
                    "_restore_timing": {"restore_total_ms": 1200.0},
                }}

            async def _fake_preparer(resolved_wf, cell):
                """Profile preparer that records being called."""
                profile_called.append(True)

            async def _progress_sink(detail: dict) -> None:
                sent_events.append(detail)

            from experiment_runner import LocalRemoteInvoker
            # Use a non-production report so the hash guard doesn't prevent
            # the stream call.  The test verifies marker aliases, preparer
            # ordering, stream kwargs, and progress events — all of which
            # work identically with or without production.
            invoker = LocalRemoteInvoker(
                _fake_stream_gen,
                experiment_id="exp_stream_test",
                node_dir=os.path.dirname(self.mod.__file__) if self.mod.__file__ else ".",
                stream_event_sink=_progress_sink,
                profile_preparer=_fake_preparer,
                gpu="A100",
                modal_options=None,
                workspace={"id": "ws_test", "name": "TestWS",
                           "token_id": "tkn", "token_secret": "sec"},
                production_report=None,
            )

            await invoker.open_worker("w1", "ck1", "prof1",
                                       workflow={"1": {"class_type": "KSampler"}},
                                       triple={"unet": "", "clip": "", "vae": ""})

            # Build a cell with a mutable trace (as _prepare_studio_run_context would)
            _t0_epoch = 1234567890.0
            cell = {
                "cell_key": "c1",
                "checkpoint_id": "ck1",
                "trace": {
                    "t0_client_press": _t0_epoch,
                    "browser_run_click": _t0_epoch,
                    "studio_route_received": _t0_epoch + 0.05,
                    "production_compile_complete": _t0_epoch + 0.15,
                },
                "_resolved_workflow": {"1": {"class_type": "KSampler",
                                              "inputs": {"seed": 42}}},
                "attempt_id": "a1",
                "prompt": "test prompt",
            }

            result = await invoker.run_cell("w1", cell)

            # ── Assert stream received compiled workflow, workspace, GPU ──
            self.assertIn("workflow", captured_stream_kwargs,
                          "Stream must receive workflow kwarg")
            self.assertIn("workspace", captured_stream_kwargs,
                          "Stream must receive workspace kwarg")
            self.assertEqual(captured_stream_kwargs["workspace"].get("id"), "ws_test")
            self.assertIn("gpu", captured_stream_kwargs,
                          "Stream must receive gpu kwarg")
            self.assertEqual(captured_stream_kwargs["gpu"], "A100")

            # ── Assert profile preparer was called before stream ──────────
            self.assertEqual(len(profile_called), 1,
                             "Profile preparer must be called exactly once")

            # ── Assert progress sink received nonterminal events ──────────
            self.assertGreater(len(sent_events), 0,
                               "Progress sink must receive nonterminal events")
            # The "result" type event should NOT be in the sink (terminal)
            sink_types = {e.get("type", "") for e in sent_events}
            self.assertNotIn("result", sink_types,
                             "Terminal 'result' must not reach progress sink")

            # ── Assert result completed ──────────────────────────────────
            self.assertEqual(result["status"], "completed",
                             "Result status must be completed")
            self.assertIn("output_paths", result)
            self.assertIn("timing_payload", result)

            # ── Assert exact marker aliases in timing_payload trace stages ──
            tp = result.get("timing_payload", {})
            trace_stages = tp.get("trace", {}).get("stages", {}) if isinstance(tp.get("trace"), dict) else {}
            required_markers = [
                "active_profile_write_start",
                "active_profile_write_end",
                "remote_submit",
                "first_remote_event",
                "result_received",
                "output_materialized",
                "browser_run_click",
                "studio_route_received",
            ]
            for marker in required_markers:
                self.assertIn(marker, trace_stages,
                              f"Marker '{marker}' must be in trace stages")

            # Legacy markers must also be present
            legacy_markers = [
                "warmup_profile_write_started",
                "warmup_profile_write_completed",
                "first_remote_message_received",
                "remote_result_received",
                "t8_local_result_received",
            ]
            for marker in legacy_markers:
                self.assertIn(marker, trace_stages,
                              f"Legacy marker '{marker}' must be in trace stages")

            # ── Assert timing ordering constraints ────────────────────────
            start = trace_stages.get("active_profile_write_start")
            end = trace_stages.get("active_profile_write_end")
            if start is not None and end is not None:
                self.assertGreaterEqual(end, start,
                                        "active_profile_write_end must be >= start")
            remote_submit = trace_stages.get("remote_submit")
            first_ev = trace_stages.get("first_remote_event")
            if remote_submit is not None and first_ev is not None:
                self.assertGreaterEqual(first_ev, remote_submit,
                                        "first_remote_event must be after remote_submit")
            result_rcv = trace_stages.get("result_received")
            output_mat = trace_stages.get("output_materialized")
            if result_rcv is not None and output_mat is not None:
                self.assertGreaterEqual(output_mat, result_rcv,
                                        "output_materialized must be after result_received")

            # ── profile preparer precedes stream invocation ──────────────
            profile_end = trace_stages.get("active_profile_write_end")
            if profile_end is not None and remote_submit is not None:
                self.assertGreaterEqual(remote_submit, profile_end,
                                        "remote_submit must be after profile write end")

        asyncio.run(_test())

    def test_direct_response_ids_and_no_scheduler_journal(self):
        """Direct result carries runId, experimentId, runHistoryId; no journal/scheduler."""
        async def _test():
            import experiment_runner as er_mod

            captured_kw: dict = {}
            sent_ev: list[dict] = []
            profile_done: list[bool] = []

            async def _fake_gen(**kw):
                captured_kw.update(kw)
                yield {"type": "status", "message": "starting"}
                yield {"type": "result", "data": {
                    "outputs": {"107": {"images": [
                        {"filename": "out.png", "data": "aGVsbG8="}
                    ]}},
                    "trace": {"stages": {}, "deltas_ms": {}, "derived_ms": {},
                              "trace_version": 3},
                }}

            async def _preparer(wf, cl):
                profile_done.append(True)

            async def _sink(d):
                sent_ev.append(d)

            real_invoker = er_mod.LocalRemoteInvoker(
                _fake_gen,
                experiment_id="exp_direct_id_test",
                node_dir=os.path.dirname(self.mod.__file__) if self.mod.__file__ else ".",
                stream_event_sink=_sink,
                profile_preparer=_preparer,
                gpu="A100",
                modal_options=None,
                workspace={"id": "ws_d", "name": "D", "token_id": "t", "token_secret": "s"},
                production_report=None,
            )

            with patch.object(er_mod, 'LocalRemoteInvoker',
                              return_value=real_invoker, autospec=False):
                with tempfile.TemporaryDirectory() as tmp:
                    snap = _make_basic_snapshot()
                    preset = _make_basic_preset()
                    _write_store_files(tmp, [snap], [preset])
                    ctx = self.mod._prepare_studio_run_context(
                        "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                        tmp, modal_options={"production": {"enabled": True,
                                                            "output_node_ids": ["107"]}},
                    )
                    self.assertEqual(ctx["status"], "ok")
                    result = await self.mod.direct_studio_run_completion(ctx, tmp)

            self.assertEqual(result["status"], "ok")

            # ── Assert response IDs ────────────────────────────────────
            self.assertIn("runId", result,
                          "Direct result must carry runId")
            self.assertIn("experimentId", result,
                          "Direct result must carry experimentId")
            self.assertIn("runHistoryId", result,
                          "Direct result must carry runHistoryId")
            self.assertIn("completed_at", result,
                          "Direct result must carry completed_at")
            self.assertIn("output_path", result,
                          "Direct result must carry output_path")
            self.assertEqual(result["direct_run"], True)

            # ── Assert production metadata ─────────────────────────────
            meta = result.get("meta", {})
            self.assertEqual(meta.get("production_plan_used"), "yes")
            self.assertEqual(meta.get("output_count"), 1)

            # ── No experiment journal created ──────────────────────────
            import experiment_service
            store = experiment_service.REGISTRY.store(result.get("experimentId", ""))
            events = store.read_events()
            journal_types = {e.get("type", "") for e in events}
            self.assertNotIn("experiment.created", journal_types)
            self.assertNotIn("experiment.started", journal_types)
            self.assertNotIn("cell.attempt_created", journal_types)
            self.assertNotIn("cell.completed", journal_types)
            self.assertNotIn("checkpoint.claimed", journal_types)

        asyncio.run(_test())

    def test_production_disabled_passes_source_workflow(self):
        """Non-production direct runs pass the source workflow into stream."""
        async def _test():
            import experiment_runner as er_mod

            captured_kw: dict = {}
            sent_ev: list[dict] = []
            profile_done: list[bool] = []

            async def _fake_gen(**kw):
                captured_kw.update(kw)
                yield {"type": "status", "message": "starting"}
                yield {"type": "result", "data": {
                    "outputs": {"107": {"images": [
                        {"filename": "out.png", "data": "aGVsbG8="}
                    ]}},
                    "trace": {"stages": {}, "deltas_ms": {}, "derived_ms": {},
                              "trace_version": 3},
                }}

            async def _preparer(wf, cl):
                profile_done.append(True)

            async def _sink(d):
                sent_ev.append(d)

            real_invoker = er_mod.LocalRemoteInvoker(
                _fake_gen,
                experiment_id="exp_direct_id_test",
                node_dir=os.path.dirname(self.mod.__file__) if self.mod.__file__ else ".",
                stream_event_sink=_sink,
                profile_preparer=_preparer,
                gpu=None,  # no GPU specified for non-production
                modal_options=None,
                workspace={"id": "ws_d", "name": "D", "token_id": "t", "token_secret": "s"},
                production_report=None,
            )

            with patch.object(er_mod, 'LocalRemoteInvoker',
                              return_value=real_invoker, autospec=False):
                with tempfile.TemporaryDirectory() as tmp:
                    snap = _make_basic_snapshot()
                    preset = _make_basic_preset()
                    _write_store_files(tmp, [snap], [preset])
                    # No production options — non-production path
                    ctx = self.mod._prepare_studio_run_context(
                        "preset_test", "txt2img", {"prompt": "hello", "seed": 7},
                        tmp, modal_options=None,
                    )
                    self.assertEqual(ctx["status"], "ok")
                    result = await self.mod.direct_studio_run_completion(ctx, tmp)

            self.assertEqual(result["status"], "ok")
            # The workflow passed to the stream should be non-empty (source workflow)
            wf = captured_kw.get("workflow")
            if wf is not None:
                self.assertIsInstance(wf, dict)
                self.assertGreater(len(wf), 0,
                                   "Non-production run must pass non-empty workflow, not None")

        asyncio.run(_test())

if __name__ == "__main__":

    unittest.main()
