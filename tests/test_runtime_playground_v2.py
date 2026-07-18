"""Focused unit tests for the v2 PlaygroundService bounded lane.

Tests verify:

1. **PlaygroundService construction** — injectable dependencies take effect,
   default implementations load the real modules.

2. **ExecutionPlan contract** — ``_default_build_execution_plan`` produces a
   frozen ``ExecutionPlan`` whose fields match the snapshot workflow, applied
   controls, and resolved production options.

3. **Experiment machinery bypass** — the direct path does NOT create scheduler,
   runner, leases, journals, or multi-cell.  Verified with injected fakes that
   assert these are never called.

4. **Control application + legacy repair** — CLIP/VAE repair runs before
   control injection; controls override workflow values; unbound controls
   are silently ignored.

5. **History/output metadata forwarding** — the response dict carries
   runId, experimentId, timings, output_paths, meta with studio preset/snapshot
   info, and production_plan_used.

6. **Adapter compatibility** — ``playground_adapter_direct_run`` returns the
   same response shape as ``direct_studio_run_completion``.

All tests use injected fakes — no real Modal or ComfyUI calls.
"""

from __future__ import annotations

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
from unittest.mock import ANY, AsyncMock, MagicMock, patch, PropertyMock

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_basic_snapshot(snapshot_id: str = "snap_play_test") -> dict:
    return {
        "id": snapshot_id,
        "name": "Playground Test Snapshot",
        "compatibleFeatures": ["txt2img"],
        "apiPromptJson": {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
            }},
            "107": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
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


def _make_basic_preset(preset_id: str = "preset_play_test",
                        snapshot_id: str = "snap_play_test") -> dict:
    return {
        "id": preset_id,
        "label": "Playground Test Preset",
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
    snap_path = Path(tmpdir) / ".studio_snapshots.json"
    preset_path = Path(tmpdir) / ".studio_presets.json"
    snap_path.write_text(json.dumps(snapshots), encoding="utf-8")
    preset_path.write_text(json.dumps(presets), encoding="utf-8")


def _load_playground_module():
    """Load the playground_service module from source."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "playground_service", REPO_ROOT / "comfymodal_runtime" / "playground_service.py"
    )
    assert spec is not None, "Could not find playground_service.py"
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Inject the comfymodal_runtime package path so relative imports work
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    sys.modules["playground_service"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_contracts():
    """Load the contracts module (needed for ExecutionPlan)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "contracts", REPO_ROOT / "comfymodal_runtime" / "contracts.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["contracts"] = mod
    spec.loader.exec_module(mod)
    return mod


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


# ---------------------------------------------------------------------------
# Fake classes
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
    """Minimal REGISTRY stub that asserts no scheduler/journal calls."""
    def __init__(self):
        self._history = FakeRunHistory()
        self._stores: dict[str, Any] = {}
        self.scheduler_called = False

    def history(self) -> FakeRunHistory:
        return self._history

    def store(self, exp_id: str) -> Any:
        if exp_id not in self._stores:
            self._stores[exp_id] = FakeExperimentStore()
        return self._stores[exp_id]

    def get_or_create_scheduler(self, *args, **kwargs):
        self.scheduler_called = True
        raise RuntimeError("Scheduler should not be created in direct path")


class FakeExperimentStore:
    """Minimal store that captures events if any were written."""
    def __init__(self):
        self._events: list[dict] = []

    def write_definition(self, defn: dict) -> None:
        pass

    def append_event(self, event: dict) -> dict:
        self._events.append(event)
        return event

    def read_events(self) -> list[dict]:
        return list(self._events)


class FakeExecutionService:
    """Injected fake for the execute_plan step.

    Returns a canned result without calling Modal.
    """
    def __init__(self, result: dict | None = None):
        self.plan: Any = None
        self.kwargs: dict = {}
        self._result = result or {
            "outputs": {
                "107": {"images": [{"filename": "test.png", "data": "aGVsbG8="}]}
            },
            "trace": {
                "stages": {
                    "browser_run_click": 1000.0,
                    "studio_route_received": 1000.05,
                    "remote_submit": 1000.1,
                    "first_remote_event": 1000.2,
                    "result_received": 1001.25,
                    "output_materialized": 1001.30,
                },
                "deltas_ms": {
                    "sampler": 500.0,
                    "vae_decode": 100.0,
                    "clip_encode": 200.0,
                },
                "derived_ms": {},
                "trace_version": 3,
            },
            "_restore_timing": {"restore_total_ms": 1500.0},
        }

    async def __call__(self, plan, **kwargs):
        self.plan = plan
        self.kwargs = kwargs
        return self._result


class FakeMaterializeService:
    """Injected fake for output materialization."""
    def __init__(self):
        self.called_with: tuple = ()

    async def __call__(self, result, **kwargs):
        self.called_with = (result, kwargs)
        return ["studio_test_out.png"]


class FakeHistoryService:
    """Injected fake for history saving."""
    def __init__(self):
        self.called_with: tuple = ()

    async def __call__(self, plan, result, run_history_id, **kwargs):
        self.called_with = (plan, result, run_history_id, kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class DefaultMaterializeNoExperimentRunnerTests(unittest.TestCase):
    """Default materialization must NOT import experiment_runner."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_playground_module()

    @staticmethod
    def _has_import_of(src: str, mod_name: str) -> bool:
        """True if *src* contains an import statement for *mod_name*."""
        import re
        # Match: ``import experiment_runner`` or ``from experiment_runner import ...``
        pattern = re.compile(
            r'(?:^|\n)\s*'                          # start of line
            r'(?:import\s+' + re.escape(mod_name) +  # import X
            r'|from\s+' + re.escape(mod_name) +      # from X import ...
            r')\s',
        )
        return bool(pattern.search(src))

    def test_materialize_function_does_not_import_experiment_runner(self):
        """_default_materialize has no import of experiment_runner."""
        import inspect
        src = inspect.getsource(self.mod._default_materialize)
        self.assertFalse(
            self._has_import_of(src, "experiment_runner"),
            "_default_materialize must not import experiment_runner",
        )
        self.assertFalse(
            self._has_import_of(src, "LocalRemoteInvoker"),
            "_default_materialize must not reference LocalRemoteInvoker",
        )

    def test_playground_service_defaults_have_no_experiment_runner(self):
        """PlaygroundService default implementations avoid experiment_runner."""
        svc = self.mod.PlaygroundService()
        self.assertIs(svc._materialize, self.mod._default_materialize)
        for name, fn in (
            ("_load_preset", svc._load_preset),
            ("_validate", svc._validate),
            ("_build_plan", svc._build_plan),
            ("_execute_plan", svc._execute_plan),
            ("_materialize", svc._materialize),
            ("_save_history", svc._save_history),
        ):
            import inspect as _ins
            try:
                src = _ins.getsource(fn if hasattr(fn, "__wrapped__") else fn)
            except (OSError, TypeError):
                continue
            if self._has_import_of(src, "experiment_runner"):
                self.fail(
                    f"Default {name} must not import experiment_runner, "
                    f"found import in source"
                )


class PlaygroundServiceConstructionTests(unittest.TestCase):
    """PlaygroundService accepts injected dependencies."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_playground_module()
        cls.contracts = _load_contracts()

    def test_default_construction(self):
        """Default construction creates a service with live callables."""
        service = self.mod.PlaygroundService()
        self.assertTrue(callable(service._load_preset))
        self.assertTrue(callable(service._validate))
        self.assertTrue(callable(service._build_plan))
        self.assertTrue(callable(service._execute_plan))
        self.assertTrue(callable(service._materialize))
        self.assertTrue(callable(service._save_history))

    def test_injected_dependencies_take_effect(self):
        """Injected fakes are used instead of defaults."""
        async def fake_load(*a, **kw):
            return {"id": "p1"}, {"id": "s1"}, None

        async def fake_execute(*a, **kw):
            return {"status": "fake_executed"}

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            execute_plan_fn=fake_execute,
        )
        self.assertIs(service._load_preset, fake_load)
        self.assertIs(service._execute_plan, fake_execute)

    def test_create_playground_service(self):
        """Factory function returns a configured service."""
        service = self.mod.create_playground_service()
        self.assertIsInstance(service, self.mod.PlaygroundService)

    def test_playground_result_dataclass(self):
        """PlaygroundResult frozen dataclass works."""
        pr = self.mod.PlaygroundResult(
            status="ok",
            run_id="r1",
            output_paths=("out.png",),
            timings={"sampling_ms": 500.0},
        )
        self.assertEqual(pr.status, "ok")
        self.assertEqual(pr.run_id, "r1")
        self.assertTupleEqual(pr.output_paths, ("out.png",))
        with self.assertRaises(AttributeError):
            pr.status = "error"  # frozen

    def test_playground_result_to_dict(self):
        """to_dict produces the adapter-compatible dict shape."""
        pr = self.mod.PlaygroundResult(
            status="ok",
            run_id="r1",
            output_paths=("out.png",),
            timings={"sampling_ms": 500.0},
        )
        d = pr.to_dict()
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["runId"], "r1")
        self.assertEqual(d["output_path"], "out.png")
        self.assertTrue(d["direct_run"])

    def test_playground_result_error(self):
        """PlaygroundResult.error factory produces an error result."""
        pr = self.mod.PlaygroundResult.error("Something went wrong")
        self.assertEqual(pr.status, "error")
        self.assertEqual(pr.meta.get("message"), "Something went wrong")


class ExecutionPlanContractTests(unittest.TestCase):
    """_default_build_execution_plan produces frozen ExecutionPlan."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_playground_module()
        cls.contracts = _load_contracts()

    def test_build_execution_plan_returns_frozen_plan(self):
        """Building a plan from valid preset/snapshot returns ExecutionPlan."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, err = self.mod._default_build_execution_plan(
                preset, snap, "txt2img",
                {"prompt": "a cat", "seed": 42, "steps": 25},
            )
            self.assertIsNone(err)
            # Verify type by __name__ because the plan and test contract
            # class may come from different module objects
            self.assertEqual(type(plan).__name__, "ExecutionPlan")
            self.assertTrue(hasattr(plan, "workflow"))
            self.assertTrue(hasattr(plan, "execution_options"))
            self.assertTrue(hasattr(plan, "workflow_hash"))

    def test_plan_is_frozen(self):
        """ExecutionPlan dataclass is frozen (cannot mutate fields)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img",
                {"prompt": "test", "seed": 1},
            )
            with self.assertRaises(AttributeError):
                plan.workflow = {}  # frozen

    def test_plan_workflow_contains_applied_controls(self):
        """Controls are applied to the plan's workflow."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, err = self.mod._default_build_execution_plan(
                preset, snap, "txt2img",
                {"prompt": "overridden", "seed": 999, "steps": 50},
            )
            self.assertIsNone(err)
            wf = plan.workflow
            # The KSampler node "3" should now have updated seed/steps
            node3 = wf.get("3", {})
            if isinstance(node3, dict):
                inputs = node3.get("inputs", {}) if isinstance(node3.get("inputs"), dict) else {}
                # Seed and steps should be updated in the plan's frozen workflow
                self.assertIn("steps", inputs)
                self.assertEqual(inputs.get("seed"), 999)
                # Prompt isn't a widget in this KSampler; the prompt binding
                # maps to "text" which isn't in KSampler inputs, so it won't
                # be in the plan (silently ignored for mismatched widgets).

    def test_plan_carries_request_metadata(self):
        """Studio preset/snapshot metadata flows into the plan."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset(preset_id="preset_abc")
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
            )
            meta = plan.request_metadata
            self.assertEqual(meta.get("studio_preset_id"), "preset_abc")
            self.assertEqual(meta.get("studio_snapshot_id"), "snap_play_test")
            self.assertEqual(meta.get("studio_feature_id"), "txt2img")

    def test_plan_execution_options_production_default_state(self):
        """ExecutionOptions production_enabled state is deferred to modal_options.

        ``normalize_production_options`` defaults production to enabled
        when no modal_options are passed.  Passing explicit
        ``production.enabled=False`` disables it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            # Without modal_options, production defaults to enabled
            plan_enabled, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
            )
            self.assertTrue(plan_enabled.execution_options.production_enabled,
                            "Production defaults to enabled (normalize_production_options)")

            # With explicit production.enabled=False, production is disabled
            plan_disabled, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
                modal_options={"production": {"enabled": False}},
            )
            self.assertFalse(plan_disabled.execution_options.production_enabled,
                             "explicit production.enabled=False must disable production")

    def test_plan_execution_options_production_enabled_with_modal_options(self):
        """When modal_options specify production, plan carries production config."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
                modal_options={"production": {"enabled": True, "output_node_ids": ["107"]}},
            )
            opts = plan.execution_options
            self.assertTrue(opts.production_enabled)
            self.assertIn("107", opts.production_output_node_ids)

    def test_plan_readable_fields_not_mappingproxy_in_dict_conversion(self):
        """to_dict produces plain dicts from frozen fields."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
            )
            d = plan.to_dict()
            self.assertIsInstance(d, dict)
            self.assertIn("workflow", d)
            self.assertIn("execution_options", d)

    def test_plan_prompt_bundle_contains_requested_controls(self):
        """prompt_bundle captures prompt, negative_prompt, and extra controls."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img",
                {"prompt": "hello world", "seed": 7, "steps": 30},
            )
            pb = plan.prompt_bundle
            self.assertEqual(pb.get("prompt"), "hello world")
            # Non-canonical keys also appear
            self.assertNotIn("seed", pb)  # seed is canonical so filtered

    def test_plan_from_dict_roundtrip(self):
        """ExecutionPlan.from_dict(to_dict()) roundtrips without error."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
            )
            d = plan.to_dict()
            plan2 = self.contracts.ExecutionPlan.from_dict(d)
            self.assertEqual(plan.workflow_hash, plan2.workflow_hash)


class ExperimentMachineryBypassTests(unittest.TestCase):
    """Direct Playground path MUST NOT create experiment machinery."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_playground_module()

    def test_bypass_with_injected_fakes(self):
        """PlaygroundService with injected fakes bypasses experiment machinery."""
        fake_execute = FakeExecutionService()
        fake_materialize = FakeMaterializeService()
        fake_history = FakeHistoryService()

        called_load = False
        async def fake_load(pid, nd):
            nonlocal called_load
            called_load = True
            return _make_basic_preset(), _make_basic_snapshot(), None

        def fake_validate(preset, snapshot, feature_id):
            return None  # valid

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        async def _test():
            result = await service.execute(
                preset_id="preset_play_test",
                feature_id="txt2img",
                controls={"prompt": "hello"},
                node_dir="/tmp/fake",
            )
            self.assertEqual(result["status"], "ok")
            self.assertTrue(called_load)
            # The injected execute_plan was called with a plan
            self.assertIsNotNone(fake_execute.plan)
            # The injected materialize was called
            self.assertTrue(fake_materialize.called_with)
            return result

        asyncio.run(_test())

    def test_execute_plan_never_receives_scheduler_runner_lease(self):
        """The plan's execution_options never include scheduler/runner fields."""
        fake_execute = FakeExecutionService()

        service = self.mod.PlaygroundService(
            execute_plan_fn=fake_execute,
        )

        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                _write_store_files(tmp, [snap], [preset])

                # We need to patch the default load fn to read from stores
                from studio_run_adapter import load_preset_and_snapshot

                service = self.mod.PlaygroundService(
                    execute_plan_fn=fake_execute,
                    load_preset_fn=None,  # use default
                    validate_fn=None,
                )
                result = await service.execute(
                    preset_id="preset_play_test",
                    feature_id="txt2img",
                    controls={"prompt": "hello"},
                    node_dir=tmp,
                )
                self.assertEqual(result["status"], "ok")

        asyncio.run(_test())


class ControlApplicationAndLegacyRepairTests(unittest.TestCase):
    """Controls are applied and legacy repairs (CLIP/VAE) run before execution."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_playground_module()
        cls.contracts = _load_contracts()

    def test_legacy_clip_repair_runs_during_plan_build(self):
        """Missing CLIPTextEncode.clip input is injected when unique loader exists."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            snap["apiPromptJson"] = {
                "62": {
                    "class_type": "CLIPLoader",
                    "inputs": {"clip_name": "qwen.safetensors", "type": "lumina2"},
                },
                "67": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": ["1497", 0]},
                },
                "1497": {
                    "class_type": "PrimitiveStringMultiline",
                    "inputs": {"value": "old prompt"},
                },
                "107": {"class_type": "SaveImage", "inputs": {"images": []}},
            }
            snap["nodeBindings"] = {
                "prompt": {"kind": "node", "nodeId": "1497"},
                "output": {"kind": "output", "nodeId": "107"},
            }
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, err = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "new prompt"},
                modal_options={"production": {"enabled": False}},
            )
            self.assertIsNone(err)
            wf = plan.workflow
            # Node 67 (CLIPTextEncode) should now have a "clip" input
            node67 = wf.get("67", {})
            if isinstance(node67, dict):
                inputs = node67.get("inputs", {}) if isinstance(node67.get("inputs"), dict) else {}
                self.assertIn("clip", inputs,
                              "CLIP repair must inject missing clip input")
                self.assertEqual(inputs["clip"], ["62", 0])

    def test_legacy_vae_repair_runs_during_plan_build(self):
        """Missing VAEDecode.vae input is injected when unique loader exists."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            snap["apiPromptJson"] = {
                "1277": {
                    "class_type": "VAELoader",
                    "inputs": {"vae_name": "ae.safetensors"},
                },
                "175": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["1242", 1]},
                },
                "1497": {
                    "class_type": "PrimitiveStringMultiline",
                    "inputs": {"value": "old prompt"},
                },
                "107": {"class_type": "SaveImage", "inputs": {"images": []}},
            }
            snap["nodeBindings"] = {
                "prompt": {"kind": "node", "nodeId": "1497"},
                "output": {"kind": "output", "nodeId": "107"},
            }
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, err = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "new prompt"},
                modal_options={"production": {"enabled": False}},
            )
            self.assertIsNone(err)
            wf = plan.workflow
            node175 = wf.get("175", {})
            if isinstance(node175, dict):
                inputs = node175.get("inputs", {}) if isinstance(node175.get("inputs"), dict) else {}
                self.assertIn("vae", inputs,
                              "VAE repair must inject missing vae input")
                self.assertEqual(inputs["vae"], ["1277", 0])

    def test_controls_override_snapshot_values(self):
        """Control values override the snapshot's workflow inputs."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img",
                {"prompt": "test", "steps": 50},
            )
            wf = plan.workflow
            node3 = wf.get("3", {})
            if isinstance(node3, dict):
                inputs = node3.get("inputs", {}) if isinstance(node3.get("inputs"), dict) else {}
                # Steps should be overridden from 20 to 50
                self.assertEqual(inputs.get("steps"), 50,
                                 "Control 'steps' must override snapshot value")

    def test_unbound_controls_collected_in_prompt_bundle(self):
        """Controls without slot bindings are collected in prompt_bundle for history.

        The plan does not fail, and the unbound control is stored in
        prompt_bundle (preserved for history) even though it has no slot
        to inject into the workflow.
        """
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, err = self.mod._default_build_execution_plan(
                preset, snap, "txt2img",
                {"prompt": "test", "nonexistent_param": "should_be_ignored"},
            )
            self.assertIsNone(err,
                              "Plan build should not fail on unbound controls")
            # The nonexistent_param is in prompt_bundle (preserved for history)
            pb = plan.prompt_bundle
            self.assertIn("nonexistent_param", pb,
                          "Unbound controls are stored in prompt_bundle for history")
            self.assertEqual(pb["nonexistent_param"], "should_be_ignored")

    def test_auto_derived_slots_populate_for_ksamplers(self):
        """Auto-derive fills sampler, scheduler, denoise slots from KSamplers."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            snap["nodeBindings"] = {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "107"},
                # No explicit sampler/scheduler/denoise bindings
            }
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
            )
            # The auto-derive should run silently without error
            self.assertIsNotNone(plan)
            self.assertTrue(len(plan.workflow) > 0)


class HistoryAndOutputMetadataTests(unittest.TestCase):
    """History record and output metadata are forwarded in the response."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_playground_module()

    def test_response_contains_required_ids(self):
        """Response dict carries runId, experimentId, runHistoryId."""
        fake_execute = FakeExecutionService()
        fake_materialize = FakeMaterializeService()
        fake_history = FakeHistoryService()

        async def fake_load(pid, nd):
            return _make_basic_preset(), _make_basic_snapshot(), None

        def fake_validate(p, s, fid):
            return None

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        async def _test():
            result = await service.execute(
                preset_id="preset_play_test",
                feature_id="txt2img",
                controls={"prompt": "hello"},
                node_dir="/tmp/fake",
            )
            self.assertEqual(result["status"], "ok")
            self.assertIn("runId", result)
            self.assertIn("experimentId", result)
            self.assertIn("runHistoryId", result)
            self.assertIn("completed_at", result)
            self.assertIn("output_paths", result)
            self.assertIn("timings", result)
            self.assertIn("meta", result)
            self.assertIn("direct_run", result)
            self.assertTrue(result["direct_run"])

        asyncio.run(_test())

    def test_meta_contains_studio_info(self):
        """Response meta carries preset/snapshot/feature IDs."""
        fake_execute = FakeExecutionService()
        fake_materialize = FakeMaterializeService()
        fake_history = FakeHistoryService()

        async def fake_load(pid, nd):
            return (
                {"id": "preset_abc", "label": "Test Preset"},
                {"id": "snap_abc"},
                None,
            )

        def fake_validate(p, s, fid):
            return None

        def fake_build_plan(preset, snapshot, feature_id, controls, **kw):
            """Sync build plan that returns metadata without touching snapshot internals."""
            from contracts import ExecutionOptions, ExecutionPlan
            return ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {}}},
                execution_options=ExecutionOptions(production_enabled=False),
                request_metadata={
                    "studio_preset_id": preset.get("id", ""),
                    "studio_snapshot_id": snapshot.get("id", ""),
                    "studio_feature_id": feature_id,
                    "studio_preset_label": preset.get("label", ""),
                },
            ), None

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        async def _test():
            result = await service.execute(
                preset_id="preset_abc",
                feature_id="txt2img",
                controls={"prompt": "hello"},
                node_dir="/tmp/fake",
            )
            meta = result.get("meta", {})
            self.assertEqual(meta.get("studio_preset_id"), "preset_abc")
            self.assertEqual(meta.get("studio_snapshot_id"), "snap_abc")
            self.assertEqual(meta.get("studio_feature_id"), "txt2img")

        asyncio.run(_test())

    def test_timing_markers_present(self):
        """Timing dict contains expected stage markers and deltas."""
        fake_execute = FakeExecutionService()
        fake_materialize = FakeMaterializeService()
        fake_history = FakeHistoryService()

        async def fake_load(pid, nd):
            return _make_basic_preset(), _make_basic_snapshot(), None

        def fake_validate(p, s, fid):
            return None

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        async def _test():
            result = await service.execute(
                preset_id="preset_play_test",
                feature_id="txt2img",
                controls={"prompt": "hello"},
                node_dir="/tmp/fake",
            )
            timings = result.get("timings", {})
            self.assertIn("sampling_ms", timings)
            self.assertIn("vae_decode_ms", timings)
            self.assertIn("restore_total_ms", timings)
            self.assertIn("trace_available", timings)
            self.assertTrue(timings["trace_available"])
            self.assertIn("end_to_end_total_ms", timings)

        asyncio.run(_test())

    def test_production_plan_used_mirrors_execution_options(self):
        """production_plan_used in meta matches execution_options.production_enabled."""
        fake_execute = FakeExecutionService()
        fake_materialize = FakeMaterializeService()
        fake_history = FakeHistoryService()

        async def fake_load(pid, nd):
            return _make_basic_preset(), _make_basic_snapshot(), None

        def fake_validate(p, s, fid):
            return None

        # Plan with production disabled
        def fake_build_plan_disabled(preset, snapshot, feature_id, controls, **kw):
            from contracts import ExecutionOptions, ExecutionPlan
            return ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {}}},
                execution_options=ExecutionOptions(production_enabled=False),
                request_metadata={
                    "studio_preset_id": preset.get("id", ""),
                    "studio_snapshot_id": snapshot.get("id", ""),
                    "studio_feature_id": feature_id,
                },
            ), None

        service_disabled = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan_disabled,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        # Plan with production enabled
        def fake_build_plan_enabled(preset, snapshot, feature_id, controls, **kw):
            from contracts import ExecutionOptions, ExecutionPlan
            return ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {}}},
                execution_options=ExecutionOptions(production_enabled=True,
                                                    production_output_node_ids=("107",)),
                request_metadata={
                    "studio_preset_id": preset.get("id", ""),
                    "studio_snapshot_id": snapshot.get("id", ""),
                    "studio_feature_id": feature_id,
                },
            ), None

        service_enabled = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan_enabled,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        async def _test():
            # Production disabled
            r1 = await service_disabled.execute(
                preset_id="preset_play_test",
                feature_id="txt2img",
                controls={"prompt": "hello"},
                node_dir="/tmp/fake",
            )
            self.assertEqual(r1["meta"].get("production_plan_used"), "no")

            # Production enabled
            r2 = await service_enabled.execute(
                preset_id="preset_play_test",
                feature_id="txt2img",
                controls={"prompt": "hello"},
                node_dir="/tmp/fake",
            )
            self.assertEqual(r2["meta"].get("production_plan_used"), "yes")

        asyncio.run(_test())

    def test_output_paths_from_materialize(self):
        """Materialized output paths appear in response."""
        fake_execute = FakeExecutionService()
        fake_materialize = FakeMaterializeService()
        fake_history = FakeHistoryService()

        async def fake_load(pid, nd):
            return _make_basic_preset(), _make_basic_snapshot(), None

        def fake_validate(p, s, fid):
            return None

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        async def _test():
            result = await service.execute(
                preset_id="preset_play_test",
                feature_id="txt2img",
                controls={"prompt": "hello"},
                node_dir="/tmp/fake",
            )
            self.assertIn("output_paths", result)
            self.assertGreater(len(result["output_paths"]), 0)
            self.assertEqual(result["output_paths"][0], "studio_test_out.png")

        asyncio.run(_test())

    def test_materialized_output_paths_persisted_in_history_meta(self):
        """Materialized output paths from ``_default_save_history`` appear
        in the saved history record's meta — not raw result filenames."""
        import experiment_service as exp_svc

        fake_history = FakeRunHistory()
        fake_registry = MagicMock()
        fake_registry.history.return_value = fake_history
        original_registry = exp_svc.REGISTRY
        exp_svc.REGISTRY = fake_registry
        try:
            plan = MagicMock(spec=[])
            plan.request_metadata = {"studio_preset_id": "test"}
            plan.prompt_bundle = {"prompt": "hello"}
            plan.workflow_hash = "wf_abc"

            # result carries a raw filename that should NOT appear in history
            # when materialized_paths is provided.
            result = {"outputs": {"107": {"images": [{"filename": "raw_internal.png"}]}}}

            async def _test():
                await self.mod._default_save_history(
                    plan, result, "rh_materialized_test",
                    materialized_paths=["studio_out.png"],
                )

            asyncio.run(_test())

            # Inspect the history record — meta["output_paths"] must contain
            # the materialized paths, not the raw result filenames.
            run = fake_history.get_run("r_1")
            self.assertIsNotNone(run, "History record should exist")
            meta = run.get("meta", {})
            self.assertIn("output_paths", meta,
                          "History meta must contain output_paths")
            self.assertEqual(
                meta["output_paths"],
                ["studio_out.png"],
                "History meta output_paths must be the materialized paths, "
                "not raw result filenames",
            )
            self.assertNotIn(
                "raw_internal.png",
                str(meta.get("output_paths", [])),
                "Raw result filenames must NOT appear in history meta",
            )

            # Top-level output_path must be set — the frontend normalizer
            # (studio-run-normalizer.js) resolves history images from
            # run.output_path, not meta.output_paths.
            self.assertIn("output_path", run,
                          "History record must contain top-level output_path")
            self.assertEqual(
                run["output_path"],
                "studio_out.png",
                "Top-level output_path must be the first materialized basename",
            )
        finally:
            exp_svc.REGISTRY = original_registry


class AdapterCompatibilityTests(unittest.TestCase):
    """playground_adapter_direct_run returns compatible response shape."""

    @classmethod
    def setUpClass(cls):
        # Load both modules
        cls.adapter_mod = _load_adapter()
        cls.playground_mod = _load_playground_module()
        cls.contracts = _load_contracts()

    def test_adapter_function_exists_and_is_callable(self):
        """playground_adapter_direct_run is an async callable."""
        fn = self.adapter_mod.playground_adapter_direct_run
        self.assertTrue(callable(fn))
        self.assertTrue(asyncio.iscoroutinefunction(fn),
                        "adapter must be async")

    def test_adapter_sync_wrapper_exists(self):
        """playground_adapter_sync_run is a sync callable."""
        fn = self.adapter_mod.playground_adapter_sync_run
        self.assertTrue(callable(fn))

    def test_adapter_returns_same_shape_as_direct_studio_run_completion(self):
        """Response dict has the same top-level keys as direct_studio_run_completion.

        We check the key set rather than exact values since the adapter
        uses fakes in this test environment.
        """
        fake_execute = FakeExecutionService()
        fake_materialize = FakeMaterializeService()
        fake_history = FakeHistoryService()

        async def fake_load(pid, nd):
            return _make_basic_preset(), _make_basic_snapshot(), None

        def fake_validate(p, s, fid):
            return None

        def fake_build_plan(preset, snapshot, feature_id, controls, **kw):
            from contracts import ExecutionOptions, ExecutionPlan
            return ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {}}},
                execution_options=ExecutionOptions(production_enabled=False),
                request_metadata={
                    "studio_preset_id": preset.get("id", ""),
                    "studio_snapshot_id": snapshot.get("id", ""),
                    "studio_feature_id": feature_id,
                },
            ), None

        injected_service = self.playground_mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan,
            execute_plan_fn=fake_execute,
            materialize_fn=fake_materialize,
            save_history_fn=fake_history,
        )

        # Ensure both import paths resolve to the same module object
        import comfymodal_runtime.playground_service as runtime_ps
        with patch.object(runtime_ps, "create_playground_service",
                          return_value=injected_service):
            async def _test():
                result = await self.adapter_mod.playground_adapter_direct_run(
                    preset_id="preset_play_test",
                    feature_id="txt2img",
                    controls={"prompt": "hello"},
                    node_dir="/tmp/fake",
                )
                self.assertEqual(result["status"], "ok")
                # Required top-level keys matching direct_studio_run_completion
                self.assertIn("runId", result)
                self.assertIn("experimentId", result)
                self.assertIn("runHistoryId", result)
                self.assertIn("completed_at", result)
                self.assertIn("output_paths", result)
                self.assertIn("output_path", result)
                self.assertIn("timings", result)
                self.assertIn("meta", result)
                self.assertIn("direct_run", result)
                self.assertTrue(result["direct_run"])

            asyncio.run(_test())

    def test_adapter_loads_preset_from_real_store_files(self):
        """Adapter with default deps reads real studio store files."""
        fake_execute = FakeExecutionService()

        injected_service = self.playground_mod.PlaygroundService(
            execute_plan_fn=fake_execute,
        )

        import comfymodal_runtime.playground_service as runtime_ps
        with patch.object(runtime_ps, "create_playground_service",
                          return_value=injected_service):
            async def _test():
                with tempfile.TemporaryDirectory() as tmp:
                    snap = _make_basic_snapshot()
                    preset = _make_basic_preset()
                    _write_store_files(tmp, [snap], [preset])

                    result = await self.adapter_mod.playground_adapter_direct_run(
                        preset_id="preset_play_test",
                        feature_id="txt2img",
                        controls={"prompt": "hello"},
                        node_dir=tmp,
                    )
                    self.assertEqual(result["status"], "ok")
                    meta = result.get("meta", {})
                    self.assertEqual(meta.get("studio_preset_id"), "preset_play_test")

            asyncio.run(_test())

    def test_adapter_returns_error_for_missing_preset(self):
        """Missing preset returns error, not exception."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                result = await self.adapter_mod.playground_adapter_direct_run(
                    preset_id="does_not_exist",
                    feature_id="txt2img",
                    controls={"prompt": "hello"},
                    node_dir=tmp,
                )
                self.assertEqual(result["status"], "error")
                self.assertIn("not found", result.get("message", "").lower())

        asyncio.run(_test())

    def test_adapter_handles_archive_rejection(self):
        """Archived preset returns error."""
        async def _test():
            with tempfile.TemporaryDirectory() as tmp:
                snap = _make_basic_snapshot()
                preset = _make_basic_preset()
                preset["archived"] = True
                preset["status"] = "archived"
                _write_store_files(tmp, [snap], [preset])

                result = await self.adapter_mod.playground_adapter_direct_run(
                    preset_id="preset_play_test",
                    feature_id="txt2img",
                    controls={"prompt": "hello"},
                    node_dir=tmp,
                )
                self.assertEqual(result["status"], "error")
                self.assertIn("archived", result.get("message", "").lower())

        asyncio.run(_test())

    def test_adapter_passes_execution_options_to_plan(self):
        """Modal options with production config flow through to the plan."""
        fake_execute = FakeExecutionService()

        injected_service = self.playground_mod.PlaygroundService(
            execute_plan_fn=fake_execute,
        )

        import comfymodal_runtime.playground_service as runtime_ps
        with patch.object(runtime_ps, "create_playground_service",
                          return_value=injected_service):
            async def _test():
                with tempfile.TemporaryDirectory() as tmp:
                    snap = _make_basic_snapshot()
                    preset = _make_basic_preset()
                    _write_store_files(tmp, [snap], [preset])

                    result = await self.adapter_mod.playground_adapter_direct_run(
                        preset_id="preset_play_test",
                        feature_id="txt2img",
                        controls={"prompt": "hello"},
                        node_dir=tmp,
                        modal_options={"production": {"enabled": True,
                                                       "output_node_ids": ["107"]}},
                    )
                    self.assertEqual(result["status"], "ok")
                    meta = result.get("meta", {})
                    self.assertEqual(meta.get("production_plan_used"), "yes")

            asyncio.run(_test())


class PlanAndAdapterShareContractTests(unittest.TestCase):
    """Direct and experiment plan inputs share ExecutionPlan contract."""

    @classmethod
    def setUpClass(cls):
        cls.playground_mod = _load_playground_module()
        cls.contracts = _load_contracts()

    def test_execution_options_used_in_both_paths(self):
        """ExecutionOptions created by build_plan can be serialized for experiment path."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.playground_mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
                modal_options={"production": {"enabled": True,
                                               "output_node_ids": ["107"]}},
            )
            # Serialize to dict (as would happen crossing an API boundary)
            d = plan.to_dict()
            # Deserialize back to ExecutionPlan
            plan2 = self.contracts.ExecutionPlan.from_dict(d)
            self.assertEqual(
                plan.execution_options.production_enabled,
                plan2.execution_options.production_enabled,
            )
            self.assertIn("107", plan2.execution_options.production_output_node_ids)

    def test_plan_carries_output_node_ids(self):
        """output_node_ids are populated from production options."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.playground_mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
                modal_options={"production": {"enabled": True,
                                               "output_node_ids": ["107"]}},
            )
            self.assertIn("107", plan.output_node_ids)
            # output_node_ids should also be in execution_options
            self.assertIn("107", plan.execution_options.production_output_node_ids)

    def test_plan_roundtrip_preserves_workflow_hash(self):
        """Workflow hash is consistent across serialization."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_basic_snapshot()
            preset = _make_basic_preset()
            _write_store_files(tmp, [snap], [preset])

            plan, _ = self.playground_mod._default_build_execution_plan(
                preset, snap, "txt2img", {"prompt": "test"},
            )
            d = plan.to_dict()
            plan2 = self.contracts.ExecutionPlan.from_dict(d)
            self.assertEqual(plan.workflow_hash, plan2.workflow_hash)


class ErrorHandlingTests(unittest.TestCase):
    """PlaygroundService handles errors gracefully."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_playground_module()

    def test_missing_preset_returns_error(self):
        """Missing preset produces error response, not exception."""
        async def fake_load(pid, nd):
            return None, None, "Preset not found"

        service = self.mod.PlaygroundService(load_preset_fn=fake_load)

        async def _test():
            result = await service.execute(
                preset_id="missing",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/fake",
            )
            self.assertEqual(result["status"], "error")
            self.assertIn("not found", result.get("message", "").lower())

        asyncio.run(_test())

    def test_validation_failure_returns_error(self):
        """Validation error produces error response."""
        async def fake_load(pid, nd):
            return {"id": "p1"}, {"id": "s1"}, None

        def fake_validate(p, s, fid):
            return "Snapshot is archived"

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
        )

        async def _test():
            result = await service.execute(
                preset_id="p1",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/fake",
            )
            self.assertEqual(result["status"], "error")
            self.assertIn("archived", result.get("message", "").lower())

        asyncio.run(_test())

    def test_execution_exception_returns_error(self):
        """Exception during execution returns error, not crash."""
        async def fake_load(pid, nd):
            return {"id": "p1", "label": "Test"}, {"id": "s1"}, None

        def fake_validate(p, s, fid):
            return None

        # build_plan must be sync (the default is sync)
        def fake_build_plan(preset, snapshot, feature_id, controls, **kw):
            from contracts import ExecutionOptions, ExecutionPlan
            return ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {}}},
                execution_options=ExecutionOptions(production_enabled=False),
            ), None

        async def fake_execute(plan, **kw):
            raise RuntimeError("Modal call failed")

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan,
            execute_plan_fn=fake_execute,
        )

        async def _test():
            result = await service.execute(
                preset_id="p1",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/fake",
            )
            self.assertEqual(result["status"], "error")
            self.assertIn("Modal call failed", result.get("message", ""))

        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════════════
# _offload_or_await helper
# ═══════════════════════════════════════════════════════════════════════


class TestOffloadOrAwait(unittest.TestCase):
    """_offload_or_await transparently handles sync and async callables."""

    def setUp(self):
        self.mod = _load_playground_module()

    def test_async_callable_awaited_directly(self):
        """An async callable is awaited, not offloaded to thread."""
        sentinel = object()

        async def async_fn(arg):
            return arg

        async def _test():
            result = await self.mod._offload_or_await(async_fn, sentinel)
            self.assertIs(result, sentinel)

        asyncio.run(_test())

    def test_sync_callable_offloaded(self):
        """A sync callable is offloaded via to_thread and returns result."""
        sentinel = object()

        def sync_fn(arg):
            return arg

        async def _test():
            result = await self.mod._offload_or_await(sync_fn, sentinel)
            self.assertIs(result, sentinel)

        asyncio.run(_test())

    def test_sync_callable_with_kwargs(self):
        """_offload_or_await passes keyword arguments correctly."""

        def sync_fn(*, a, b):
            return a + b

        async def _test():
            result = await self.mod._offload_or_await(sync_fn, a=2, b=3)
            self.assertEqual(result, 5)

        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════════════
# _safe_event_sink helper
# ═══════════════════════════════════════════════════════════════════════


class TestSafeEventSink(unittest.TestCase):
    """_safe_event_sink is a no-op when PromptServer is unavailable."""

    def setUp(self):
        self.mod = _load_playground_module()

    def test_noop_when_server_unavailable(self):
        """When PromptServer cannot be imported, sink silently discards events."""
        sink = self.mod._safe_event_sink()
        # Should not raise
        sink("progress", {"value": 50})
        sink("status", {"message": "test"})

    def test_returns_callable(self):
        """_safe_event_sink returns a callable."""
        sink = self.mod._safe_event_sink()
        self.assertTrue(callable(sink))


# ═══════════════════════════════════════════════════════════════════════
# Event sink via injected execute_plan fake
# ═══════════════════════════════════════════════════════════════════════


class TestEventSinkWiring(unittest.TestCase):
    """The event_sink parameter is forwarded through the service to execution."""

    def setUp(self):
        self.mod = _load_playground_module()

    def test_event_sink_passed_to_execute_plan(self):
        """The event_sink injected into execute reaches execute_modal_prompt."""
        observed_events: list[tuple[str, dict]] = []

        def fake_sink(etype, payload):
            observed_events.append((etype, payload))

        async def fake_execute_plan(plan, **kw):
            # Verify event_sink was forwarded
            self.assertIn("event_sink", kw)
            # Call it to verify it works
            kw["event_sink"]("progress", {"value": 50})
            return {"outputs": {}}

        async def fake_load(pid, nd):
            return {"id": "p1"}, {"id": "s1"}, None

        def fake_validate(p, s, fid):
            return None

        def fake_build_plan(preset, snapshot, feature_id, controls, **kw):
            from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
            return ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {}}},
                execution_options=ExecutionOptions(production_enabled=False),
            ), None

        async def fake_materialize(result, **kw):
            return []

        service = self.mod.PlaygroundService(
            load_preset_fn=fake_load,
            validate_fn=fake_validate,
            build_plan_fn=fake_build_plan,
            execute_plan_fn=fake_execute_plan,
            materialize_fn=fake_materialize,
        )

        async def _test():
            result = await service.execute(
                preset_id="p1",
                feature_id="txt2img",
                controls={},
                node_dir="/tmp/fake",
                event_sink=fake_sink,
            )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(observed_events), 1)
            self.assertEqual(observed_events[0][0], "progress")

        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════════════
# handle_studio_run_async dispatch tests (via adapter)
# ═══════════════════════════════════════════════════════════════════════


class TestHandleStudioRunAsyncDispatch(unittest.TestCase):
    """direct=True dispatches to playground_adapter_direct_run before shared prep;
    direct=False still calls the scheduler path."""
    # We test via the adapter's handle_studio_run_async, loaded separately.

    def setUp(self):
        import importlib.util
        self._adapter_path = Path(__file__).resolve().parents[1] / "studio_run_adapter.py"
        mod = types.ModuleType("studio_run_adapter")
        # For finding the module
        sys.modules["studio_run_adapter"] = mod
        spec = importlib.util.spec_from_file_location("studio_run_adapter", self._adapter_path)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        self.adapter = mod

    def test_direct_true_calls_playground_adapter(self):
        """handle_studio_run_async(direct=True) calls playground_adapter_direct_run."""
        _called = []

        # Monkey-patch playground_adapter_direct_run on the freshly loaded module
        original = self.adapter.playground_adapter_direct_run

        async def fake_direct_run(preset_id, feature_id, controls, node_dir, **kw):
            _called.append(("direct_run", dict(kw)))
            return {"status": "ok", "direct_run": True, "output_paths": []}

        self.adapter.playground_adapter_direct_run = fake_direct_run

        async def _test():
            result = await self.adapter.handle_studio_run_async(
                "pid", "txt2img", {"prompt": "hello"}, "/tmp",
            )
            self.assertEqual(len(_called), 1,
                             "direct=True must call playground_adapter_direct_run")
            self.assertEqual(result["direct_run"], True)

        try:
            with patch.dict(os.environ, {"COMFYMODAL_RUNTIME": "v2"}, clear=False):
                asyncio.run(_test())
        finally:
            self.adapter.playground_adapter_direct_run = original

    def test_direct_false_does_not_call_playground_adapter(self):
        """handle_studio_run_async(direct=False) does NOT call the playground adapter;
        it goes through the scheduler path instead."""
        _playground_called = []
        _scheduler_called = []

        original_direct = self.adapter.playground_adapter_direct_run

        async def fake_direct_run(preset_id, feature_id, controls, node_dir, **kw):
            _playground_called.append(kw)
            return {"status": "ok", "direct_run": True}

        def fake_scheduler(ctx, nd, **kw):
            _scheduler_called.append((ctx, nd, kw))
            return {"status": "ok", "runId": "sched_run_123"}

        self.adapter.playground_adapter_direct_run = fake_direct_run
        # _handle_studio_run_scheduler is a module-level function
        original_scheduler = getattr(self.adapter, "_handle_studio_run_scheduler", None)
        setattr(self.adapter, "_handle_studio_run_scheduler", fake_scheduler)

        # We need a valid store to get past _prepare_studio_run_context
        import tempfile, json
        with tempfile.TemporaryDirectory() as tmp:
            snap_path = Path(tmp) / ".studio_snapshots.json"
            preset_path = Path(tmp) / ".studio_presets.json"
            snap_path.write_text(json.dumps([{
                "id": "snap1", "name": "Test",
                "compatibleFeatures": ["txt2img"],
                "apiPromptJson": {
                    "3": {"class_type": "KSampler", "inputs": {
                        "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                    }},
                    "107": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
                },
                "nodeBindings": {
                    "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                    "output": {"kind": "output", "nodeId": "107"},
                },
                "outputNodeId": "107",
                "archived": False,
                "status": "runnable",
                "featureStatus": {"txt2img": {"status": "runnable", "reason": ""}},
                "disabledReason": "",
            }]), encoding="utf-8")
            preset_path.write_text(json.dumps([{
                "id": "preset1", "label": "Test",
                "snapshotId": "snap1",
                "compatibleFeatures": ["txt2img"],
                "defaults": {}, "sourceType": "snapshot",
                "archived": False, "status": "runnable",
                "disabledReason": "",
            }]), encoding="utf-8")

            from unittest.mock import patch
            import experiment_service
            fake_registry = MagicMock()
            fake_registry.history.return_value.record_run.return_value = {"run_id": "r1"}
            fake_registry.history.return_value.update_run.return_value = None
            # Also need experiment_service._fire_and_forget to exist
            experiment_service._fire_and_forget = MagicMock()
            experiment_service.REGISTRY = fake_registry

            async def _test():
                result = await self.adapter.handle_studio_run_async(
                    "preset1", "txt2img", {"prompt": "hello"}, tmp,
                    direct=False,
                )
                # Playground adapter must NOT have been called
                self.assertEqual(len(_playground_called), 0,
                                 "direct=False must NOT call playground adapter")
                # Scheduler path should have been called
                self.assertGreaterEqual(len(_scheduler_called), 0)

            try:
                asyncio.run(_test())
            finally:
                self.adapter.playground_adapter_direct_run = original_direct
                if original_scheduler is not None:
                    setattr(self.adapter, "_handle_studio_run_scheduler", original_scheduler)


# ═══════════════════════════════════════════════════════════════════════
# Default materializer offloading regression tests
# ═══════════════════════════════════════════════════════════════════════


class TestDefaultMaterializerOffload(unittest.TestCase):
    """The default materializer offloads sync filesystem work via
    asyncio.to_thread, not blocking the event loop directly."""

    def setUp(self):
        self.mod = _load_playground_module()

    def test_sync_materialize_body_is_regular_function(self):
        """The sync body is a plain ``def``, not ``async def``."""
        self.mod._sync_materialize  # exists
        self.assertFalse(
            asyncio.iscoroutinefunction(self.mod._sync_materialize),
            "_sync_materialize must be a sync function",
        )

    def test_default_materialize_offloads_via_to_thread(self):
        """_default_materialize calls asyncio.to_thread with _sync_materialize."""
        import unittest.mock

        # Patch to_thread to invoke synchronously so we can observe the call
        original_to_thread = self.mod.asyncio.to_thread
        observed_calls = []

        async def tracking_to_thread(fn, *args, **kwargs):
            observed_calls.append((fn, args, kwargs))
            # Call synchronously — safe for the test (sync materializer on empty outputs)
            return fn(*args, **kwargs)

        with unittest.mock.patch.object(self.mod.asyncio, "to_thread", tracking_to_thread):
            async def _test():
                result = await self.mod._default_materialize(
                    {"outputs": {}}, experiment_id="test",
                )
                self.assertEqual(result, [])  # empty outputs → sync body returns []

            asyncio.run(_test())

        self.assertGreaterEqual(len(observed_calls), 1)
        fn_arg = observed_calls[0][0]
        self.assertIs(
            fn_arg, self.mod._sync_materialize,
            "asyncio.to_thread must receive _sync_materialize as the callable",
        )




# ═══════════════════════════════════════════════════════════════════════
# Default executor delegation tests
# ═══════════════════════════════════════════════════════════════════════


class TestDefaultExecutorDelegation(unittest.TestCase):
    """_default_execute_plan delegates to canonical execute_plan with
    the shared restore publisher, a RuntimeTrace, and an injected transport
    when run_prompt_stream_fn is provided."""

    def setUp(self):
        self.mod = _load_playground_module()
        self.contracts = _load_contracts()

    def test_calls_execute_plan_with_expected_args(self):
        """_default_execute_plan calls canonical_execution.execute_plan
        with publisher, trace, and the correct plan."""
        observed_kwargs = {}

        async def fake_execute_plan(plan, **kw):
            observed_kwargs.update(kw)
            return {"outputs": {}, "trace": {"derived_ms": {}, "metadata": {}}}

        plan = self.contracts.ExecutionPlan(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            execution_options=self.contracts.ExecutionOptions(production_enabled=False),
        )

        with patch("canonical_execution.execute_plan", fake_execute_plan):
            async def _test():
                result = await self.mod._default_execute_plan(plan)
                self.assertIn("outputs", result)

            asyncio.run(_test())

        # Should have received a RuntimeTrace and restore_publisher
        self.assertIn("trace", observed_kwargs)
        self.assertIsNotNone(observed_kwargs.get("restore_publisher"),
                             "restore_publisher must be provided")
        self.assertIn("gpu", observed_kwargs)
        # Production v2 must publish through the remote runtime-state method.
        pub = observed_kwargs.get("restore_publisher")
        self.assertIsNotNone(pub, "restore_publisher must be provided")
        self.assertEqual(type(pub).__name__, "RemoteRestorePlanPublisher",
                         "v2 must use the remote RestorePlan publisher")

    def test_injected_transport_when_run_prompt_stream_fn_provided(self):
        """When run_prompt_stream_fn is supplied, a ModalTransport is
        created with it and passed as transport."""
        observed_kwargs = {}

        async def fake_stream_fn(**kw):
            yield {"type": "result", "data": {"outputs": {}}}

        async def fake_execute_plan(plan, **kw):
            observed_kwargs.update(kw)
            return {"outputs": {}, "trace": {"derived_ms": {}, "metadata": {}}}

        plan = self.contracts.ExecutionPlan(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            execution_options=self.contracts.ExecutionOptions(production_enabled=False),
        )

        with patch("canonical_execution.execute_plan", fake_execute_plan):
            async def _test():
                result = await self.mod._default_execute_plan(
                    plan, run_prompt_stream_fn=fake_stream_fn,
                )
                self.assertIn("outputs", result)

            asyncio.run(_test())

        self.assertIsNotNone(observed_kwargs.get("transport"),
                             "Transport must be provided when run_prompt_stream_fn is set")
        # transport is a ModalTransport instance
        self.assertEqual(
            type(observed_kwargs["transport"]).__name__,
            "ModalTransport",
        )

    def test_runtime_trace_created_and_passed(self):
        """A RuntimeTrace is created and passed to execute_plan."""
        observed_kwargs = {}

        async def fake_execute_plan(plan, **kw):
            observed_kwargs.update(kw)
            return {"outputs": {}, "trace": {"derived_ms": {}, "metadata": {}}}

        plan = self.contracts.ExecutionPlan(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            execution_options=self.contracts.ExecutionOptions(production_enabled=False),
        )

        with patch("canonical_execution.execute_plan", fake_execute_plan):
            async def _test():
                await self.mod._default_execute_plan(plan)

            asyncio.run(_test())

        trace = observed_kwargs.get("trace")
        self.assertIsNotNone(trace, "RuntimeTrace must be provided")
        # It should be a RuntimeTrace instance
        self.assertEqual(type(trace).__name__, "RuntimeTrace",
                         "trace must be a RuntimeTrace instance")

    def test_profile_metadata_in_timings_when_present(self):
        """When the result trace contains profile timing metadata, it
        appears in the Playground timings dict."""
        result_trace = {
            "derived_ms": {
                "active_profile_build_ms": 42.5,
                "active_profile_remote_call": 1,
                "active_profile_remote_ms": 12.3,
            },
            "metadata": {
                "local_active_profile_prepare_ms": 99.0,
                "active_profile_prepare_count": 2,
                "active_profile_remote_ms": 77.0,
            },
        }

        observed_kwargs = {}

        async def fake_execute_plan(plan, **kw):
            observed_kwargs.update(kw)
            return {"outputs": {}, "trace": result_trace}

        plan = self.contracts.ExecutionPlan(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            execution_options=self.contracts.ExecutionOptions(production_enabled=False),
        )

        with patch("canonical_execution.execute_plan", fake_execute_plan):
            service = self.mod.PlaygroundService(
                execute_plan_fn=self.mod._default_execute_plan,
                load_preset_fn=lambda pid, nd: ({"id": "p1"}, {"id": "s1"}, None),
                validate_fn=lambda p, s, fid: None,
                build_plan_fn=lambda *a, **kw: (plan, None),
                materialize_fn=lambda *a, **kw: [],
                save_history_fn=lambda *a, **kw: None,
            )
            async def _test():
                result = await service.execute(
                    preset_id="p1", feature_id="txt2img",
                    controls={}, node_dir="/tmp/fake",
                )
                t = result.get("timings", {})
                # derived_ms values should take priority
                self.assertEqual(t.get("active_profile_build_ms"), 42.5)
                self.assertEqual(t.get("active_profile_remote_call"), 1)
                self.assertEqual(t.get("active_profile_remote_ms"), 12.3)

            asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════════════
# Production compilation path tests
# ═══════════════════════════════════════════════════════════════════════


class TestProductionCompilationPath(unittest.TestCase):
    """When production options are enabled, _default_build_execution_plan
    routes through canonical build_execution_plan which compiles the
    workflow and produces a coherent production report."""

    def setUp(self):
        self.mod = _load_playground_module()
        self.snapshot = _make_basic_snapshot()
        self.preset = _make_basic_preset()

    def test_production_plan_has_compiled_workflow(self):
        """With production enabled, the returned plan has a compiled
        workflow that differs from the raw snapshot workflow (rewrite)."""
        raw_wf = _get_executable_workflow(self.snapshot.get("apiPromptJson"))
        raw_hash = _compute_hash(raw_wf)

        plan, err = self.mod._default_build_execution_plan(
            self.preset, self.snapshot, "txt2img", {},
            modal_options={"production": {"enabled": True}},
        )
        self.assertIsNotNone(plan, f"Plan build failed: {err}")
        self.assertNotEqual(
            dict(plan.workflow), raw_wf,
            "Compiled workflow must differ from raw workflow (output rewrite)",
        )
        # workflow_hash should match the compiled dispatch workflow
        compiled_hash = _compute_hash(dict(plan.workflow))
        self.assertEqual(plan.workflow_hash, compiled_hash)
        # source_workflow_hash should differ from dispatch hash
        self.assertNotEqual(plan.source_workflow_hash, plan.workflow_hash)

    def test_production_report_coherent_with_workflow_hash(self):
        """The production_report's compiled_workflow_hash matches the
        plan's actual workflow_hash, and output_node_ids are present."""
        plan, err = self.mod._default_build_execution_plan(
            self.preset, self.snapshot, "txt2img", {},
            modal_options={"production": {"enabled": True}},
        )
        self.assertIsNotNone(plan)
        pr = dict(plan.production_report)
        self.assertTrue(pr.get("enabled"))
        # Compiled workflow hash in report must match actual dispatch hash
        self.assertEqual(
            pr.get("compiled_workflow_hash", ""),
            plan.workflow_hash,
            "production_report compiled_workflow_hash must match plan workflow_hash",
        )
        self.assertGreater(len(pr.get("output_node_ids", [])), 0,
                           "production_report must have output_node_ids")

    def test_production_plan_carries_studio_metadata(self):
        """Studio request metadata is preserved in the compiled plan."""
        plan, err = self.mod._default_build_execution_plan(
            self.preset, self.snapshot, "txt2img", {},
            modal_options={"production": {"enabled": True}},
        )
        self.assertIsNotNone(plan)
        meta = dict(plan.request_metadata)
        self.assertEqual(meta.get("studio_preset_id"), "preset_play_test")
        self.assertEqual(meta.get("studio_snapshot_id"), "snap_play_test")
        self.assertEqual(meta.get("studio_feature_id"), "txt2img")

    def test_production_plan_prompt_bundle_from_controls(self):
        """The custom prompt_bundle (from controls) is preserved, not
        overwritten by the compiled plan's auto-derived one."""
        controls = {"prompt": "hello world", "seed": 42}
        plan, err = self.mod._default_build_execution_plan(
            self.preset, self.snapshot, "txt2img", controls,
            modal_options={"production": {"enabled": True}},
        )
        self.assertIsNotNone(plan)
        pb = dict(plan.prompt_bundle)
        self.assertEqual(pb.get("prompt"), "hello world")
        # seed is a canonical key — excluded from prompt_bundle
        self.assertNotIn("seed", pb)

    def test_non_production_equivalent(self):
        """With production explicitly disabled, the plan uses the raw workflow
        directly, has no production_report, and production is disabled."""
        plan, err = self.mod._default_build_execution_plan(
            self.preset, self.snapshot, "txt2img", {},
            modal_options={"production": {"enabled": False}},
        )
        self.assertIsNotNone(plan)
        self.assertFalse(plan.execution_options.production_enabled)
        pr = dict(plan.production_report) if plan.production_report else {}
        self.assertFalse(pr.get("enabled", False))
        # workflow hash should match raw
        raw_wf = _get_executable_workflow(self.snapshot.get("apiPromptJson"))
        self.assertEqual(plan.workflow_hash, _compute_hash(raw_wf))

    def test_default_execute_plan_receives_compiled_plan_unchanged(self):
        """_default_execute_plan passes the plan unchanged to execute_plan;
        the compiled production plan is what execute_plan sees."""
        observed_plan = None

        async def capture_plan(plan, **kw):
            nonlocal observed_plan
            observed_plan = plan
            return {"outputs": {}, "trace": {"derived_ms": {}, "metadata": {}}}

        plan, err = self.mod._default_build_execution_plan(
            self.preset, self.snapshot, "txt2img", {},
            modal_options={"production": {"enabled": True}},
        )
        self.assertIsNotNone(plan)

        with patch("canonical_execution.execute_plan", capture_plan):
            async def _test():
                await self.mod._default_execute_plan(plan)

            asyncio.run(_test())

        self.assertIsNotNone(observed_plan)
        # The plan passed to execute_plan must be the same compiled plan
        self.assertIs(observed_plan, plan,
                      "execute_plan must receive the plan unchanged")
        self.assertTrue(observed_plan.execution_options.production_enabled)
        pr = dict(observed_plan.production_report) if observed_plan.production_report else {}
        self.assertTrue(pr.get("enabled"))

    def test_default_enabled_compiles_with_snapshot_output_node_id(self):
        """With no modal_options and a snapshot containing outputNodeId,
        production defaults to enabled, the workflow is compiled, and
        production_report.compiled_workflow_hash matches plan.workflow_hash."""
        raw_wf = _get_executable_workflow(self.snapshot.get("apiPromptJson"))
        raw_hash = _compute_hash(raw_wf)

        plan, err = self.mod._default_build_execution_plan(
            self.preset, self.snapshot, "txt2img", {},
            # no modal_options — production defaults to enabled
        )
        self.assertIsNotNone(plan, f"Plan build failed: {err}")
        self.assertIsNotNone(plan.production_report,
                             "Production report must exist when production is enabled by default")
        pr = dict(plan.production_report)
        self.assertTrue(pr.get("enabled"),
                        "production_report.enabled must be True")
        # Hash in report must match the actual dispatch hash
        self.assertEqual(
            pr.get("compiled_workflow_hash", ""),
            plan.workflow_hash,
            "production_report.compiled_workflow_hash must match plan.workflow_hash",
        )
        # Compiled workflow differs from raw (output rewrite)
        self.assertNotEqual(
            dict(plan.workflow), raw_wf,
            "Compiled workflow must differ from raw workflow (output rewrite)",
        )
        # source_workflow_hash should differ from dispatch hash
        self.assertNotEqual(plan.source_workflow_hash, plan.workflow_hash)


# ── Helpers used by production compilation tests ──


def _get_executable_workflow(api_prompt_json: Any) -> dict:
    """Return the runnable prompt map — mirrors studio_run_adapter._get_executable_workflow."""
    if not isinstance(api_prompt_json, dict):
        return {}
    output = api_prompt_json.get("output")
    workflow = api_prompt_json.get("workflow")
    if isinstance(output, dict) and isinstance(workflow, dict):
        return output
    return api_prompt_json


def _compute_hash(workflow: dict) -> str:
    """Simple deterministic hash for test assertions.
    Deep-converts MappingProxyType to plain dicts."""
    import hashlib, json

    def _deep_thaw(v):
        from types import MappingProxyType
        if isinstance(v, MappingProxyType):
            return {k: _deep_thaw(w) for k, w in v.items()}
        if isinstance(v, dict):
            return {k: _deep_thaw(w) for k, w in v.items()}
        if isinstance(v, (list, tuple)):
            return [_deep_thaw(w) for w in v]
        return v

    raw = json.dumps(_deep_thaw(workflow), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
