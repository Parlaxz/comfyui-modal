"""D1 local-dispatch batch: node-registry preload + trigger→submission line.

The D1 fix preloads the FULL ComfyUI node registry ONCE in ``main`` before the
run loop (``_ensure_full_node_registry``), so ``_run_one``'s per-run await
short-circuits via the ``_NODE_REGISTRY_READY`` fast path and run-1
local_receive→worker_start is ~0.  The preload cost is reported as the
explicit harness-setup metric ``node_registry_preload_ms`` — never inside a
per-run submission window (C3 scheduling semantics preserved).

Covered here (all deterministic, NO real sleeping, NO Modal, NO network;
fake clocks / mocks everywhere):
  T1  build_host_submission_breakdown_line with a PRELOADED registry
      (node_registry_end <= local_receive) gates the three in-window registry
      fields to absent and reports node_registry_preload_ms.
  T2  The pinned inside-window fixture (registry_start AFTER local_receive)
      renders the three registry fields byte-identically and
      node_registry_preload_ms absent.
  T3  build_trigger_to_submission_line reconciles a synthetic trace to
      trigger_to_submission_ms=40.0, residual 0.0, status complete.
  T4  Missing events degrade: every schema value absent, status incomplete,
      no raise.
  T5  _run_one with a patched-ready registry short-circuits (fast), emits
      benchmark_iteration_selected + local_worker_submit, and yields
      benchmark_iteration_selected_to_local_worker_submit_ms=0.0.
  T6  _intentional_cold_wait brackets + records + prints the wait.
  T7  _PYTHON_FIRST_LINE_MONO_NS exists and is positive.
  T8  AST: main preloads the registry before any mode dispatch.
"""

from __future__ import annotations

import asyncio
import ast
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HARNESS_PATH = _REPO_ROOT / "tools" / "benchmark_v2_direct.py"

_BVD_MODULE: Any = None


def _bvd():
    """Lazy guarded import of the heavy benchmark harness module."""
    global _BVD_MODULE
    if _BVD_MODULE is None:
        import sys
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        import tools.benchmark_v2_direct as _mod
        _BVD_MODULE = _mod
    return _BVD_MODULE


# ============================================================================
# Shared synthetic-clock helpers
# ============================================================================


class _SeqClock:
    """Deterministic (wall, mono) pair source for patching _capture_ts.

    The first three calls (T0 / local_receive / worker_start) return the SAME
    pair — modeling the D1 fast path where the registry is already preloaded
    so trigger→receive→worker_start is instantaneous.  Later calls advance by
    ``step_ns`` each so every subsequent event is strictly increasing.
    """

    def __init__(self, base_wall: int = 1_700_000_000_000_000_000,
                 base_mono: int = 1_000_000_000_000, step_ns: int = 1_000_000):
        self._n = 0
        self._base_wall = int(base_wall)
        self._base_mono = int(base_mono)
        self._step_ns = int(step_ns)

    def __call__(self) -> tuple[int, int]:
        n = self._n
        self._n += 1
        if n < 3:
            return (self._base_wall, self._base_mono)
        step = (n - 2) * self._step_ns
        return (self._base_wall + step, self._base_mono + step)


# ============================================================================
# Host submission breakdown fixtures (mirrors test_v2_host_submission_breakdown)
# ============================================================================

_REQ = "req-d1-host-1"
_NS_PER_MS = 1_000_000
_BASE_NS = 1_700_000_000_000_000_000
_COMMAND_START_UNIX_MS = _BASE_NS // _NS_PER_MS

# Inside-window fixture (registry runs AFTER local_receive) — the pinned
# shape from tests/test_v2_host_submission_breakdown.py.
_OFFSETS = {
    "python_first_line": 200,
    "local_receive": 250,
    "node_registry_start": 1250,
    "node_registry_end": 18250,
    "worker_start": 18280,
    "plan_build_call_start": 18290,
    "execute_plan_call_start": 18353,
    "transport_entry": 18358,
    "handle_lookup_end": 18360,
    "payload_serialize_end": 18361,
    "modal_submission_attempt": 18361,
    "modal_first_remote_event": 23681,
}

_LOCAL_TIMING = {
    "worker_start_to_plan_build_ms": 10.0,
    "plan_build_ms": 63.0,
    "transport_entry_to_handle_lookup_ms": 0.0,
    "handle_lookup_ms": 2.0,
    "payload_serialize_ms": 1.0,
    "generator_create_ms": 0.0,
    "generator_created_to_first_iteration_ms": 0.0,
    "local_receive_to_actual_submission_ms": 18111.0,
    "first_iteration_to_first_remote_event_ms": 5320.0,
}


def _wall(offset_ms: int) -> int:
    return _BASE_NS + offset_ms * _NS_PER_MS


def _event(name: str, offset_ms: int) -> dict:
    return {"name": name, "wall_unix_ns": _wall(offset_ms)}


def _events() -> list[dict]:
    return [
        _event("worker_start", _OFFSETS["worker_start"]),
        _event("build_execution_plan_call_start", _OFFSETS["plan_build_call_start"]),
        _event("execute_plan_call_start", _OFFSETS["execute_plan_call_start"]),
        _event("transport_entry", _OFFSETS["transport_entry"]),
        _event("modal_handle_lookup_start", _OFFSETS["transport_entry"]),
        _event("modal_handle_lookup_end", _OFFSETS["handle_lookup_end"]),
        _event("modal_payload_serialize_start", _OFFSETS["handle_lookup_end"]),
        _event("modal_payload_serialize_end", _OFFSETS["payload_serialize_end"]),
        _event("modal_generator_create_start", _OFFSETS["payload_serialize_end"]),
        _event("modal_generator_created", _OFFSETS["payload_serialize_end"]),
        _event("modal_submission_attempt", _OFFSETS["modal_submission_attempt"]),
        _event("modal_first_remote_event", _OFFSETS["modal_first_remote_event"]),
    ]


def _artifact(events=None, local_timing: Any | None = None) -> dict:
    if events is None:
        events = _events()
    if local_timing is None:
        local_timing = dict(_LOCAL_TIMING)
    return {
        "request_id": _REQ,
        "result": {
            "trace": {"events": list(events)},
            "local_timing": dict(local_timing),
        },
    }


def _inside_window_kwargs() -> dict:
    """The pinned inside-window fixture: registry starts AFTER local_receive."""
    return {
        "command_start_unix_ms": _COMMAND_START_UNIX_MS,
        "python_first_line_ns": _wall(_OFFSETS["python_first_line"]),
        "local_receive_wall_ns": _wall(_OFFSETS["local_receive"]),
        "node_registry_start_ns": _wall(_OFFSETS["node_registry_start"]),
        "node_registry_end_ns": _wall(_OFFSETS["node_registry_end"]),
        "scheduling_ms": 1596.0,
        "scheduling_source": "result_carried",
    }


def _preloaded_kwargs() -> dict:
    """Preloaded fixture: registry ENDS before local_receive (registry done in
    ``main`` before the run loop)."""
    kwargs = _inside_window_kwargs()
    kwargs["node_registry_start_ns"] = _wall(50)
    kwargs["node_registry_end_ns"] = _wall(200)  # <= local_receive (250)
    return kwargs


def _parse(line):
    assert line is not None
    return dict(part.split("=", 1) for part in line.split(" ") if "=" in part)


# ============================================================================
# T1 / T2 — build_host_submission_breakdown_line preload gating
# ============================================================================


class TestHostBreakdownPreloadGating(unittest.TestCase):
    def test_preloaded_registry_gates_in_window_fields(self):
        """Registry preloaded before local_receive → in-window registry fields
        absent, node_registry_preload_ms numeric, submission unchanged."""
        bvd = _bvd()
        line = bvd.build_host_submission_breakdown_line(
            _artifact(), **_preloaded_kwargs()
        )
        self.assertTrue(str(line).startswith("[v2.host_submission_breakdown]"))
        parts = _parse(line)
        self.assertEqual(parts["request_id"], _REQ)
        self.assertEqual(parts["local_receive_to_registry_start_ms"], "absent")
        self.assertEqual(parts["node_registry_init_ms"], "absent")
        self.assertEqual(parts["registry_end_to_worker_start_ms"], "absent")
        self.assertEqual(parts["node_registry_preload_ms"], "150.0")
        # Unchanged fields.
        self.assertEqual(parts["local_receive_to_submission_ms"], "18111.0")
        self.assertEqual(parts["worker_start_to_plan_build_start_ms"], "10.0")
        self.assertEqual(parts["plan_build_ms"], "63.0")
        self.assertEqual(parts["scheduling_source"], "result_carried")

    def test_inside_window_registry_fields_unchanged(self):
        """Pinned fixture (registry_start AFTER local_receive): the three
        registry fields render exactly as before and preload is absent."""
        bvd = _bvd()
        line = bvd.build_host_submission_breakdown_line(
            _artifact(), **_inside_window_kwargs()
        )
        self.assertTrue(str(line).startswith("[v2.host_submission_breakdown]"))
        parts = _parse(line)
        self.assertEqual(parts["local_receive_to_registry_start_ms"], "1000.0")
        self.assertEqual(parts["node_registry_init_ms"], "17000.0")
        self.assertEqual(parts["registry_end_to_worker_start_ms"], "30.0")
        self.assertEqual(parts["node_registry_preload_ms"], "absent")
        self.assertEqual(parts["local_receive_to_submission_ms"], "18111.0")

    def test_no_registry_stamps_still_absent(self):
        """Neither preload nor in-window: all registry fields absent."""
        bvd = _bvd()
        kwargs = _inside_window_kwargs()
        kwargs["node_registry_start_ns"] = None
        kwargs["node_registry_end_ns"] = None
        parts = _parse(bvd.build_host_submission_breakdown_line(_artifact(), **kwargs))
        self.assertEqual(parts["local_receive_to_registry_start_ms"], "absent")
        self.assertEqual(parts["node_registry_init_ms"], "absent")
        self.assertEqual(parts["registry_end_to_worker_start_ms"], "absent")
        self.assertEqual(parts["node_registry_preload_ms"], "absent")


# ============================================================================
# T3 — build_trigger_to_submission_line reconciles a synthetic trace
# ============================================================================

_BASE_MONO = 1_000_000_000_000
_BASE_WALL = 1_700_000_000_000_000_000


def _emit_chain(trace: Any, offsets_ms: dict[str, int]) -> None:
    """emit_at every chain event at wall/mono = base + offset*1ms."""
    for name, offset_ms in offsets_ms.items():
        trace.emit_at(
            name,
            wall_unix_ns=_BASE_WALL + offset_ms * _NS_PER_MS,
            monotonic_ns=_BASE_MONO + offset_ms * _NS_PER_MS,
            phase="local",
        )


def _synthetic_reconcile_trace() -> Any:
    """Build a RuntimeTrace whose measured-children partition sums EXACTLY to
    the trigger→submission window (40.0 ms) and ends at modal_submission_attempt.

    Child deltas (all numeric):
      lr→ws 10, ws→plan_build_start 5, plan_build 10, plan_build_end→exec 5,
      exec→plan_materialization 2, plan_materialization 3, mat→active_profile 2,
      active_profile 1, restore_plan_build 0, transport_entry→handle_lookup 2,
      handle_lookup 0, payload_materialization 0, payload_size_measurement 0,
      payload_size_to_serialize_end 0, payload_ready_to_modal_call 0,
      generator_create 0, generator_created_to_first_iteration 0 = 40.0.
    """
    from comfymodal_runtime.trace import RuntimeTrace
    trace = RuntimeTrace(request_id="x")
    _emit_chain(trace, {
        "benchmark_iteration_selected": 0,
        "local_worker_submit": 0,
        "worker_start": 10,
        "plan_build_start": 15,
        "plan_build_end": 25,
        "execute_plan_entry": 30,
        "plan_materialization_start": 32,
        "plan_materialization_end": 35,
        "active_profile_prepare_start": 37,
        "active_profile_prepare_end": 38,
        "restore_plan_build_start": 38,
        "restore_plan_build_end": 38,
        "transport_entry": 38,
        "modal_handle_ready": 40,
        "modal_handle_lookup_start": 40,
        "modal_handle_lookup_end": 40,
        "modal_payload_serialize_start": 40,
        "payload_measure_size_start": 40,
        "payload_measure_size_end": 40,
        "modal_payload_serialize_end": 40,
        "modal_generator_create_start": 40,
        "modal_generator_created": 40,
        "modal_first_iteration_start": 40,
        "modal_submission_attempt": 40,
    })
    return trace


_TRIGGER_SCHEMA_FIELDS = (
    "request_id",
    "benchmark_iteration_selected_to_local_worker_submit_ms",
    "local_worker_submit_to_worker_start_ms",
    "worker_start_to_plan_build_start_ms",
    "plan_build_ms",
    "plan_build_end_to_modal_handle_ready_ms",
    "modal_handle_ready_to_modal_submission_attempt_ms",
    "intentional_cold_wait_before_run_ms",
    "trigger_to_submission_ms",
    "measured_children_ms",
    "residual_ms",
    "reconciliation_status",
)


class TestTriggerToSubmissionLine(unittest.TestCase):
    def test_trigger_line_reconciles(self):
        """Synthetic full chain: trigger_to_submission 40.0, residual 0.0,
        status complete, every schema field present."""
        bvd = _bvd()
        trace = _synthetic_reconcile_trace()
        line = bvd.build_trigger_to_submission_line(
            trace,
            origin={"request_id": "x", "local_receive_mono_ns": _BASE_MONO},
            cold_wait_before_ms=20000.0,
        )
        self.assertTrue(str(line).startswith("[v2.trigger_to_submission]"))
        parts = _parse(line)
        for field in _TRIGGER_SCHEMA_FIELDS:
            self.assertIn(field, parts, f"missing schema field: {field}")
        self.assertEqual(parts["trigger_to_submission_ms"], "40.0")
        self.assertEqual(parts["intentional_cold_wait_before_run_ms"], "20000.0")
        self.assertEqual(parts["measured_children_ms"], "40.0")
        self.assertEqual(parts["residual_ms"], "0.0")
        self.assertEqual(parts["reconciliation_status"], "complete")
        self.assertEqual(parts["benchmark_iteration_selected_to_local_worker_submit_ms"], "0.0")

    def test_missing_events_degrade(self):
        """Empty trace → every schema value absent, status incomplete, no raise."""
        bvd = _bvd()
        from comfymodal_runtime.trace import RuntimeTrace
        trace = RuntimeTrace(request_id="")
        line = bvd.build_trigger_to_submission_line(trace)
        self.assertTrue(str(line).startswith("[v2.trigger_to_submission]"))
        parts = _parse(line)
        for field in _TRIGGER_SCHEMA_FIELDS:
            self.assertIn(field, parts, f"missing schema field: {field}")
        self.assertEqual(parts["trigger_to_submission_ms"], "absent")
        self.assertEqual(parts["measured_children_ms"], "absent")
        self.assertEqual(parts["residual_ms"], "absent")
        self.assertEqual(parts["intentional_cold_wait_before_run_ms"], "absent")
        self.assertEqual(parts["reconciliation_status"], "incomplete")


# ============================================================================
# T5 — _run_one registry short-circuit + trigger/breakdown events
# ============================================================================


def _valid_runtime_trace() -> dict[str, Any]:
    """Minimal result-trace that _identity/_timing/build_waterfall accept
    (same pattern as tests/test_v2_benchmark_trace_handoff.py)."""
    from comfymodal_runtime.runtime_shape import runtime_shape_config
    shape = runtime_shape_config().identity_payload()
    remote_metadata = {
        "method_name": "run_plan_stream",
        "app_name": "stable-modal-comfy-v2-shadow",
        "class_name": "ModalRuntimeEntrypointV2",
        "gpu": "rtx-pro-6000",
        "cpu": 16,
        "memory_mb": 49152,
        "fingerprint": "test-snapshot-fingerprint",
        "runtime_shape": shape,
        "runtime_shape_fingerprint": shape["runtime_shape_fingerprint"],
        "runtime_shape_label": None,
        "stored_snapshot_model_order": "O0",
    }
    return {
        "events": [
            {"name": "remote_method_entry", "metadata": remote_metadata},
            {
                "name": "runtime_shape_observed",
                "metadata": {**shape, "status": "baseline_passthrough"},
            },
        ],
        "metadata": {},
    }


class TestRunOneRegistryShortCircuit(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self.output_dir = self._tmp
        self.workspace = {"token_id": "t", "token_secret": "s"}
        self.transport = mock.AsyncMock()
        self.workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        self.modal_options = {"production": {"enabled": False}}
        self.captured_trace: Any = None

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    async def _run_one_with_fakes(self) -> tuple[str, dict[str, Any]]:
        bvd = _bvd()
        result = {"trace": _valid_runtime_trace()}
        clock = _SeqClock()
        call_log: list[dict[str, Any]] = []

        async def fake_execute_plan(plan: Any, **kw: Any) -> dict[str, Any]:
            call_log.append(kw)
            self.captured_trace = kw.get("trace")
            return result

        buf = io.StringIO()
        with (
            mock.patch("tools.benchmark_v2_direct._capture_ts", clock),
            mock.patch("tools.benchmark_v2_direct.normalize_production_options", return_value={}),
            mock.patch("tools.benchmark_v2_direct.build_execution_plan", return_value={}),
            mock.patch("tools.benchmark_v2_direct.execute_plan", fake_execute_plan),
            mock.patch("tools.benchmark_v2_direct._ensure_full_node_registry", mock.AsyncMock(return_value=True)),
            mock.patch("tools.benchmark_v2_direct._validate_runtime_shape", return_value={}),
            mock.patch("tools.benchmark_v2_direct._validate_remote_profile"),
            mock.patch("tools.benchmark_v2_direct.reconcile_waterfall_local"),
            mock.patch("tools.benchmark_v2_direct._handle_full_trace_artifact", mock.AsyncMock()),
            mock.patch("comfymodal_runtime.modal_transport.join_persistence_drain", mock.AsyncMock()),
            mock.patch("sys.stdout", buf),
        ):
            artifact = await bvd._run_one(
                index=0,
                workflow=self.workflow,
                modal_options=self.modal_options,
                workspace=self.workspace,
                transport=self.transport,
                output_dir=self.output_dir,
            )
        return buf.getvalue(), artifact

    async def test_registry_short_circuit_and_events(self):
        """With the registry patched-ready, _run_one completes fast, emits
        benchmark_iteration_selected + local_worker_submit, and the trigger
        line reports benchmark_iteration_selected_to_local_worker_submit_ms=0.0
        (deterministic fake clock)."""
        out, artifact = await self._run_one_with_fakes()

        self.assertIsInstance(artifact, dict)
        self.assertEqual(artifact["run_index"], 0)

        # Trigger line printed.
        self.assertIn("[v2.trigger_to_submission]", out)
        trigger_line = next(
            ln for ln in out.splitlines() if ln.startswith("[v2.trigger_to_submission]")
        )
        parts = _parse(trigger_line)
        self.assertEqual(parts["benchmark_iteration_selected_to_local_worker_submit_ms"], "0.0")
        self.assertEqual(parts["local_worker_submit_to_worker_start_ms"], "0.0")

        # The trace carried the D1 events.
        trace = self.captured_trace
        self.assertIsNotNone(trace)
        names = {evt.name for evt in trace.events}
        self.assertIn("benchmark_iteration_selected", names)
        self.assertIn("local_worker_submit", names)

        # Canonical breakdown computed over the captured trace: the preload
        # fast path leaves local_receive→worker_start at exactly 0.0.
        from comfymodal_runtime.trace import _build_local_submission_breakdown
        bd = _build_local_submission_breakdown(
            trace,
            origin={"request_id": "x", "local_receive_mono_ns": 1_000_000_000_000},
            transport_meta={},
        )
        self.assertEqual(bd["local_receive_to_worker_start_ms"], 0.0)


# ============================================================================
# T6 — _intentional_cold_wait brackets + records + prints
# ============================================================================


class TestIntentionalColdWait(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bvd = _bvd()
        self._bvd = bvd
        self._saved = list(bvd._COLD_WAITS)
        bvd._COLD_WAITS.clear()

    def tearDown(self):
        self._bvd._COLD_WAITS.clear()
        self._bvd._COLD_WAITS.extend(self._saved)

    async def test_cold_wait_brackets_and_records(self):
        bvd = self._bvd
        sleep_log: list[float] = []

        async def fake_sleep(seconds: float, *args: Any, **kwargs: Any) -> None:
            sleep_log.append(float(seconds))

        class _TwoStepClock:
            def __init__(self):
                self._calls = 0

            def __call__(self):
                if self._calls == 0:
                    self._calls += 1
                    return (1_700_000_000_000_000_000, 1_000_000_000_000)
                return (1_700_000_000_000_020_000_000, 1_000_000_000_000 + 20_000_000_000)

        buf = io.StringIO()
        with (
            mock.patch("tools.benchmark_v2_direct.asyncio.sleep", fake_sleep),
            mock.patch("tools.benchmark_v2_direct._capture_ts", _TwoStepClock()),
            mock.patch("sys.stdout", buf),
        ):
            record = await bvd._intentional_cold_wait(20)

        self.assertEqual(sleep_log, [20.0])
        self.assertEqual(record["requested_seconds"], 20.0)
        self.assertEqual(record["waited_mono_ms"], 20000.0)
        self.assertEqual(bvd._COLD_WAITS[-1]["requested_seconds"], 20.0)
        self.assertEqual(bvd._COLD_WAITS[-1]["waited_mono_ms"], 20000.0)
        self.assertIn("[v2.harness] intentional_cold_wait", buf.getvalue())
        self.assertIn("start_mono_ns=1000000000000", buf.getvalue())
        self.assertIn("end_mono_ns=1020000000000", buf.getvalue())


# ============================================================================
# T7 — _PYTHON_FIRST_LINE_MONO_NS exists and is positive
# ============================================================================


class TestPythonFirstLineMonoStamp(unittest.TestCase):
    def test_cli_entry_mono_stamp_exists(self):
        bvd = _bvd()
        value = bvd._PYTHON_FIRST_LINE_MONO_NS
        self.assertIsInstance(value, int)
        self.assertGreater(value, 0)


# ============================================================================
# T8 — AST: main preloads the registry before any mode dispatch
# ============================================================================


class TestMainPreloadsRegistryBeforeModes(unittest.TestCase):
    def test_main_preloads_registry_before_modes(self):
        source = _HARNESS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        main_defs = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "main"
        ]
        self.assertEqual(len(main_defs), 1)
        main_fn = main_defs[0]

        def _first_call_line(fn_node: Any, func_name: str) -> int:
            return min(
                node.lineno
                for node in ast.walk(fn_node)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == func_name
            )

        registry_line = _first_call_line(main_fn, "_ensure_full_node_registry")

        # The ``snapshot_restore_only_backfill`` branch is an early-return
        # path (returns before the preload; never reaches the benchmark flow),
        # so its ``_load_workspace`` call is excluded.  The benchmark-flow
        # workspace load is the LAST ``_load_workspace`` in ``main`` — it must
        # come AFTER the preload (Edit 1h places the preload between the
        # backfill return and ``requested_shape``).
        workspace_lines = [
            node.lineno
            for node in ast.walk(main_fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_load_workspace"
        ]
        self.assertGreaterEqual(len(workspace_lines), 1)
        benchmark_workspace_line = max(workspace_lines)
        self.assertLess(registry_line, benchmark_workspace_line)

        for mode_fn in (
            "_run_one",
            "_run_acceptance_sequence",
            "_run_variance_cold",
            "_run_snapshot_restore_only",
            "_run_volume_read",
        ):
            mode_calls = [
                node.lineno
                for node in ast.walk(main_fn)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == mode_fn
            ]
            self.assertGreaterEqual(
                len(mode_calls), 1,
                f"main must dispatch to {mode_fn}",
            )
            for mode_line in mode_calls:
                self.assertLess(
                    registry_line, mode_line,
                    f"registry preload must precede {mode_fn} dispatch",
                )


if __name__ == "__main__":
    unittest.main()
