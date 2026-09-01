"""Regression tests for end-to-end V2 waterfall restoration wiring.

These are source-contract tests (AST-based, matching the repo's existing
audit-test style) that pin the backend wiring contract:

1. modal_app.py builds + attaches ``data["waterfall"]`` (via waterfall_to_dict)
   for EVERY successful V2 request, no longer gated to benchmark-only.
2. __init__.py success metadata carries ``result["waterfall"]`` into ``_meta``
   and ``_finish_job`` persists it in the run-history timing payload.
3. v2_experiment_invoker carries the returned waterfall in its timing_payload.
4. studio_run_adapter preserves it into Studio timing.json/timing_summary and
   meta on both the scheduler and direct paths.
"""

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    src = path.read_text(encoding="utf-8")
    if src.startswith("\ufeff"):
        src = src[1:]
    return src


def _func_source(src, name):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    return None


def _has_import(src, module_name, names=None):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module_name:
            if names is None:
                return True
            imported = {a.name for a in node.names if a.name}
            if names.issubset(imported):
                return True
    return False


class ModalAppTerminalWaterfallTests(unittest.TestCase):
    """The V2 terminal result path must attach waterfall for every request."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(REPO_ROOT / "comfymodal_runtime" / "modal_app.py")

    def test_waterfall_to_dict_imported(self):
        # Relative import (``from .v2_waterfall import ...``) — AST reports the
        # module basename with level=1.
        self.assertTrue(
            _has_import(self.src, "v2_waterfall", {"waterfall_to_dict"}),
            "waterfall_to_dict must be imported for serialization",
        )

    def test_shared_attach_helper_imported(self):
        self.assertTrue(
            _has_import(self.src, "v2_waterfall", {"attach_waterfall"}),
            "attach_waterfall must be imported for shared finalization",
        )

    def test_terminal_result_attaches_waterfall(self):
        # The inline V2 result path delegates serialization to the shared
        # idempotent finalizer.
        self.assertIn(
            "attach_waterfall(data, report=_waterfall, run_label=_run_label)",
            self.src,
        )

    def test_waterfall_rendered_to_logs(self):
        # Rendering happens inside the shared helper; render_waterfall must
        # still be imported for the helper contract.
        self.assertTrue(
            _has_import(self.src, "v2_waterfall", {"render_waterfall"}),
            "render_waterfall must be imported",
        )

    def test_truthful_normal_run_label_present(self):
        # Every successful request builds the report; a truthful label for
        # normal runs must exist alongside the benchmark label.
        self.assertIn('_run_label = "remote normal run"', self.src)
        self.assertIn("remote benchmark run", self.src)

    def test_waterfall_failure_is_best_effort(self):
        # A waterfall error attaches an error marker and never fails the prompt.
        self.assertIn('data["waterfall"] = {', self.src)
        self.assertIn('"status": "error",', self.src)


class LocalMetaPersistenceTests(unittest.TestCase):
    """__init__.py success metadata/history carries waterfall end to end."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(REPO_ROOT / "__init__.py")

    def test_success_meta_carries_waterfall(self):
        self.assertIn(
            '"waterfall": result.get("waterfall", {}) if isinstance(result, dict) else {},',
            self.src,
        )

    def test_finish_job_uses_timing_payload_helper(self):
        self.assertIn("timings=_timing_payload_with_waterfall(meta_obj),", self.src)

    def test_timing_payload_helper_preserves_trace_and_waterfall(self):
        helper = _func_source(self.src, "_timing_payload_with_waterfall")
        if helper is None:
            self.fail("_timing_payload_with_waterfall not defined in __init__.py")
        # ast.unparse normalizes string quotes to single quotes.
        self.assertIn("payload = dict(meta_obj.get('trace') or {})", helper)
        self.assertIn("payload['waterfall'] = meta_obj['waterfall']", helper)

    def test_cell_completed_copies_waterfall_before_result_pop(self):
        # The experiment remote-event handler must carry the graph result's
        # waterfall into the durable payload before stripping result/base64.
        self.assertIn('payload["waterfall"] = copy.deepcopy(_wf)', self.src)
        self.assertIn('_wf = result_data.get("waterfall")', self.src)
        self.assertIn('data.pop("result", None)', self.src)

    def test_cell_history_metadata_carries_waterfall(self):
        self.assertIn(
            '"waterfall": payload.get("waterfall", {}),',
            self.src,
        )

    def test_cell_materialization_has_shared_finalizer_fallback(self):
        # If an upstream client bypassed the wrapper, graph-like result_data
        # must still be finalized so history retains a waterfall.
        self.assertIn("is_graph_result(result_data)", self.src)
        self.assertIn(
            'attach_waterfall(\n                                    result_data,',
            self.src,
        )
        self.assertIn('run_label="experiment cell materialize"', self.src)

    def test_golden_cell_fallback_suppresses_only_duplicate_render(self):
        self.assertIn('result_data.get("golden_telemetry")', self.src)
        self.assertIn('result_data.get("golden_identity")', self.src)
        self.assertIn("print_render=not _is_golden_result", self.src)

    def test_generic_cell_fallback_remains_print_enabled(self):
        self.assertIn("_is_golden_result = (", self.src)
        self.assertIn("print_render=not _is_golden_result", self.src)


class InvokerTimingPayloadTests(unittest.TestCase):
    """V2 experiment invoker carries the returned waterfall in timing_payload."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(REPO_ROOT / "comfymodal_runtime" / "v2_experiment_invoker.py")

    def test_timing_payload_carries_waterfall(self):
        self.assertIn(
            '"waterfall": result.get("waterfall", {}) if isinstance(result, dict) else {},',
            self.src,
        )


class StudioAdapterPersistenceTests(unittest.TestCase):
    """Studio timing.json/timing_summary and meta preserve the waterfall."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(REPO_ROOT / "studio_run_adapter.py")

    def test_scheduler_path_copies_waterfall_into_timings(self):
        self.assertIn('"_restore_timing", "scheduler_trace", "waterfall"', self.src)

    def test_scheduler_path_meta_carries_waterfall(self):
        self.assertIn(
            'if timing_payload and isinstance(timing_payload.get("waterfall"), dict):',
            self.src,
        )
        self.assertIn('meta_merge["waterfall"] = copy.deepcopy(timing_payload["waterfall"])', self.src)

    def test_direct_path_copies_waterfall_into_timings(self):
        self.assertIn('timings["waterfall"] = copy.deepcopy(_waterfall)', self.src)

    def test_direct_path_meta_carries_waterfall(self):
        self.assertIn('if _waterfall and isinstance(_waterfall, dict):', self.src)
        self.assertIn('meta_merge["waterfall"] = copy.deepcopy(_waterfall)', self.src)


if __name__ == "__main__":
    unittest.main()
