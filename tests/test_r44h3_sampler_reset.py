"""R44H3 — sampler telemetry request-lifecycle fix.

Guarantees (all local, CPU-only, no Modal/network/CUDA required):

A. WIRING  — ``reset_request()`` is called EXACTLY ONCE in production code,
   as the FIRST statement of ``ModalRuntimeEntrypoint.run_plan_stream``
   (the single production request entry; ``run_prompt_stream`` delegates
   there), so it runs BEFORE any sampler event can emit.
B. ORDER   — the reset call structurally precedes every other statement in
   the handler (no execution/yield can happen before it).
C. ISOLATION — a real ``reset_request`` clears ALL prior-request sampler
   state (boundaries, ticks, tail, lmg records, emitted flag) so stale
   events from request N can never leak into request N+1.
D. SAFETY  — resetting twice is idempotent-safe: installed sub-timing
   patches are removed exactly once and the second reset never raises or
   double-restores patched globals.
E. NEUTRALITY — sampler behavior/event schemas untouched: the telemetry
   module still emits the same four durable event names with the same
   metadata keys after a lifecycle reset (R44I2 appends a deferred
   authoritative ``sampling_start`` and a final ``sampler_telemetry_status``
   after those four; legacy names/keys unchanged).
"""

import ast
import os
import sys
import time
import unittest

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# Defensive: pin this worktree's package (mirrors test_r44h2 pattern).
for _name in [k for k in list(sys.modules)
              if k == "comfymodal_runtime" or k.startswith("comfymodal_runtime.")]:
    _mod = sys.modules.get(_name)
    _path0 = getattr(getattr(_mod, "__path__", None), "__getitem__", lambda *_: "")(0)
    if _path0 and not os.path.normcase(_path0).startswith(os.path.normcase(_HERE)):
        del sys.modules[_name]

from comfymodal_runtime import sampler_telemetry as st  # noqa: E402

MODAL_APP_PATH = os.path.join(_HERE, "comfymodal_runtime", "modal_app.py")
RUNTIME_DIR = os.path.join(_HERE, "comfymodal_runtime")


def _modal_app_source() -> str:
    with open(MODAL_APP_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _find_function(tree: ast.AST, name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def _reset_request_calls(fn_node: ast.AST) -> list[ast.Call]:
    """All ``...reset_request(...)`` call nodes inside a function body."""
    calls = []
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            func = node.func
            attr = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else ""
            )
            if attr == "reset_request":
                calls.append(node)
    return calls


# ── A + B: wiring & ordering (structural, no heavy import) ────────────────


class WiringTest(unittest.TestCase):
    """reset_request is wired exactly once, first, in run_plan_stream."""

    def setUp(self):
        self.tree = ast.parse(_modal_app_source(), filename=MODAL_APP_PATH)

    def test_exactly_one_reset_call_in_run_plan_stream(self):
        fn = _find_function(self.tree, "run_plan_stream")
        calls = _reset_request_calls(fn)
        self.assertEqual(
            len(calls), 1,
            "run_plan_stream must call reset_request EXACTLY once",
        )

    def test_reset_is_first_statement_of_handler(self):
        fn = _find_function(self.tree, "run_plan_stream")
        first = fn.body[0]
        # The reset lives in a fail-safe try block as statement #0.
        self.assertIsInstance(first, ast.Try, "first statement must be the guarded reset")
        found = False
        for stmt in ast.walk(first):
            if isinstance(stmt, ast.Call):
                f = stmt.func
                attr = f.attr if isinstance(f, ast.Attribute) else (
                    f.id if isinstance(f, ast.Name) else ""
                )
                if attr == "reset_request":
                    found = True
        self.assertTrue(found, "guarded first statement must contain the reset call")
        # Nothing executes before it: it IS the first statement.
        self.assertEqual(fn.body.index(first), 0)

    def test_run_prompt_stream_delegates_to_run_plan_stream(self):
        """Single call site covers both production entry points."""
        fn = _find_function(self.tree, "run_prompt_stream")
        src = ast.unparse(fn)
        self.assertIn("self.run_plan_stream(", src)
        # ...and run_prompt_stream itself adds NO second reset call.
        self.assertEqual(len(_reset_request_calls(fn)), 0)

    def test_no_other_production_call_sites(self):
        """Exactly ONE reset_request call site across all runtime modules."""
        hits = []
        for root, dirs, files in os.walk(RUNTIME_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                with open(path, "r", encoding="utf-8") as fh:
                    try:
                        tree = ast.parse(fh.read(), filename=path)
                    except SyntaxError:
                        continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        f = node.func
                        attr = f.attr if isinstance(f, ast.Attribute) else (
                            f.id if isinstance(f, ast.Name) else ""
                        )
                        if attr == "reset_request":
                            rel = os.path.relpath(path, _HERE).replace("\\", "/")
                            hits.append((rel, getattr(node, "lineno", 0)))
        self.assertEqual(len(hits), 1, f"expected exactly one production call site, got {hits}")
        self.assertEqual(hits[0][0], "comfymodal_runtime/modal_app.py")


# ── C: isolation — stale state cannot cross requests ──────────────────────


class RequestIsolationTest(unittest.TestCase):
    def setUp(self):
        st.reset_request("")

    def tearDown(self):
        st._TELEMETRY._remove_subtiming_patches()
        st.reset_request("")

    def test_stale_events_cleared_for_next_request(self):
        # Request A produces boundaries/ticks/tail/emitted state.
        st.reset_request("req-A")
        st.note_sampler_node_entry("1242", "ClownsharKSampler_Beta")
        st.note_sampling_start(111, 222, node_id="1242", steps=8)
        st.note_first_eval(333)
        st.note_progress_tick(step=0, source="wrapper_callback")
        st.finish_sampler_tail(444_000_000, 555)
        snap_a = st.snapshot()
        self.assertEqual(snap_a["request_id"], "req-A")
        self.assertGreater(snap_a["sampling_start_mono_ns"], 0)
        self.assertEqual(snap_a["tick_count"], 1)
        self.assertIsNotNone(snap_a["tail"])

        # Request B starts: ONE reset wipes everything from A.
        st.reset_request("req-B")
        snap_b = st.snapshot()
        self.assertEqual(snap_b["request_id"], "req-B")
        self.assertEqual(snap_b["node_entry_mono_ns"], 0)
        self.assertEqual(snap_b["sampling_start_mono_ns"], 0)
        self.assertEqual(snap_b["first_eval_mono_ns"], 0)
        self.assertEqual(snap_b["tick_count"], 0)
        self.assertIsNone(snap_b["tail"])
        self.assertEqual(snap_b["lmg_records"], [])

        # The wrapper-store resolver must NOT serve request A's timestamp.
        mono, src = st.resolve_sampling_start(None, None)
        self.assertIsNone(mono)
        self.assertEqual(src, "unavailable")

    def test_emitted_flag_resets_per_request(self):
        class _FakeTrace:
            def __init__(self):
                self.names = []

            def emit(self, name, phase=None, metadata=None):
                self.names.append(name)

        st.reset_request("emit-cycle")
        st.note_progress_tick(step=0, source="t")
        ft = _FakeTrace()
        st.emit_durable_events(ft)
        self.assertEqual(st.emit_durable_events(ft), 0)  # once per request
        st.reset_request("emit-cycle-2")
        st.note_progress_tick(step=0, source="t")
        self.assertGreater(st.emit_durable_events(ft), 0)  # fresh scope emits again


# ── D: double-reset safety (patches removed exactly once) ─────────────────


class DoubleResetSafetyTest(unittest.TestCase):
    def tearDown(self):
        st._TELEMETRY._remove_subtiming_patches()
        st.reset_request("")

    def test_double_reset_removes_patches_once_and_restores_globals(self):
        import copy as _copy
        import gc as _gc

        orig_gc = _gc.collect
        orig_dc = _copy.deepcopy
        try:
            st.reset_request("double-reset")
            st._TELEMETRY._install_subtiming_patches()
            self.assertIsNot(_gc.collect, orig_gc)
            # Production sequence shape: reset at request start while patches
            # from a previous request are still installed — then a defensive
            # second reset.  Neither may raise or corrupt the globals.
            st.reset_request("double-reset-2")
            st.reset_request("double-reset-2")
            self.assertIs(_gc.collect, orig_gc)
            self.assertIs(_copy.deepcopy, orig_dc)
            self.assertFalse(st._TELEMETRY._patches_installed)
        finally:
            _gc.collect = orig_gc  # type: ignore[assignment]
            _copy.deepcopy = orig_dc  # type: ignore[assignment]


# ── E: neutrality — schemas unchanged after lifecycle reset ───────────────


class SchemaNeutralityTest(unittest.TestCase):
    def test_durable_event_names_and_keys_stable_after_reset(self):
        class _FakeTrace:
            def __init__(self):
                self.events = []

            def emit(self, name, phase=None, metadata=None):
                self.events.append((name, dict(metadata or {})))

        st.reset_request("schema-test")
        st.note_sampler_node_entry("n1", "KSampler")
        # Real-clock sampling start so it strictly follows the captured
        # node-entry stamp (prep phase requires start > entry).
        st.note_sampling_start(time.monotonic_ns() + 1, 0,
                               node_id="n1", steps=4, sigmas_len=5)
        st.note_first_eval(time.monotonic_ns() + 2)
        st.note_progress_tick(step=0, source="wrapper_callback")
        st.finish_sampler_tail(3_000_000, 3_000)
        ft = _FakeTrace()
        n = st.emit_durable_events(ft)
        names = [x[0] for x in ft.events]
        # R44I2: the four legacy events keep their order; the deferred
        # authoritative sampling_start (FakeTrace has no .events, so the
        # dedup guard emits) and the mandatory sampler_telemetry_status are
        # appended after them.
        self.assertEqual(n, 6)
        self.assertEqual(
            names,
            ["sampler_prep_phase", "sampler_first_eval_start",
             "sampler_step_ticks", "sampler_tail",
             "sampling_start", "sampler_telemetry_status"],
        )
        prep = dict(ft.events)["sampler_prep_phase"]
        for key in ("node_id", "node_class", "request_id", "start_mono_ns",
                    "end_mono_ns", "wall_ms", "sigmas_len",
                    "sampling_start_source"):
            self.assertIn(key, prep)
        tail = dict(ft.events)["sampler_tail"]
        for key in ("start_mono_ns", "end_mono_ns", "wall_ms",
                    "gc_collect_ms", "cpu_transfer_wall_ms"):
            self.assertIn(key, tail)


if __name__ == "__main__":
    unittest.main()
