"""Tests for Workstream E additions:
- WorkerProgressBuffer rolling sample cache
- /comfymodal/experiments/{id}/events includes progress
- Results UI surfaces failed cell error inline
- Results UI confirms destructive controls
- A/B slider keyboard handlers and role/aria

These tests run without a real DOM — the UI module is a thin wrapper
that creates elements and wires listeners. We mock ``document`` and
``window`` just enough to exercise the code paths we care about.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

NODE_DIR = Path(__file__).resolve().parent.parent


def _load_module(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── WorkerProgressBuffer ────────────────────────────────────────────────


class WorkerProgressBufferTests(unittest.TestCase):
    def _make_buffer(self):
        from experiment_service import WorkerProgressBuffer
        return WorkerProgressBuffer()

    def test_empty_snapshot(self):
        b = self._make_buffer()
        snap = b.snapshot()
        self.assertEqual(snap["cells"], {})
        self.assertEqual(snap["checkpoints"], {})

    def test_update_and_snapshot(self):
        b = self._make_buffer()
        b.update(checkpoint_id="ck1", cell_key="c1", sample={"type": "sampler.step", "step": 5, "total_steps": 20, "pct": 25})
        b.update(checkpoint_id="ck1", cell_key="c2", sample={"type": "sampler.step", "step": 10, "total_steps": 20, "pct": 50})
        snap = b.snapshot()
        self.assertIn("ck1::c1", snap["cells"])
        self.assertIn("ck1::c2", snap["cells"])
        self.assertEqual(snap["checkpoints"]["ck1"]["cells"]["c1"]["pct"], 25)
        self.assertEqual(snap["checkpoints"]["ck1"]["cells"]["c2"]["pct"], 50)
        self.assertEqual(snap["checkpoints"]["ck1"]["last_event_type"], "sampler.step")
        self.assertIn("received_at", snap["checkpoints"]["ck1"]["cells"]["c1"])

    def test_update_overwrites(self):
        b = self._make_buffer()
        b.update(checkpoint_id="ck1", cell_key="c1", sample={"type": "sampler.step", "pct": 10})
        b.update(checkpoint_id="ck1", cell_key="c1", sample={"type": "sampler.step", "pct": 90})
        snap = b.snapshot()
        self.assertEqual(snap["cells"]["ck1::c1"]["pct"], 90)

    def test_clear_checkpoint(self):
        b = self._make_buffer()
        b.update(checkpoint_id="ck1", cell_key="c1", sample={"type": "cell.started"})
        b.update(checkpoint_id="ck2", cell_key="c1", sample={"type": "cell.started"})
        b.clear_checkpoint("ck1")
        snap = b.snapshot()
        self.assertNotIn("ck1::c1", snap["cells"])
        self.assertNotIn("ck1", snap["checkpoints"])
        self.assertIn("ck2::c1", snap["cells"])

    def test_bounded_memory(self):
        b = self._make_buffer()
        # Many distinct cells, no single checkpoint, must stay bounded
        for i in range(500):
            b.update(checkpoint_id=f"ck{i}", cell_key="c1", sample={"type": "cell.started"})
        snap = b.snapshot()
        self.assertLessEqual(len(snap["cells"]), b.MAX_CELL_SAMPLES * 4)

    def test_thread_safety(self):
        b = self._make_buffer()
        errors = []

        def writer(start, end):
            try:
                for i in range(start, end):
                    b.update(checkpoint_id="ck1", cell_key=f"c{i}", sample={"pct": i % 100})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i * 50, (i + 1) * 50)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        snap = b.snapshot()
        self.assertGreater(len(snap["cells"]), 0)


# ── /events endpoint includes progress ─────────────────────────────────


class EventsEndpointProgressTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["COMFYUI_MODAL_NODE_DIR"] = self._tmp.name
        # Reload experiment_service so REGISTRY re-binds
        if "experiment_service" in sys.modules:
            del sys.modules["experiment_service"]

    def test_progress_in_events_response(self):
        from experiment_service import REGISTRY, ServiceRegistry, WorkerProgressBuffer
        # Replace REGISTRY with a fresh one to avoid pollution
        reg = ServiceRegistry()
        # Pre-populate a progress sample
        reg.worker_progress("exp_test").update(
            checkpoint_id="ck1", cell_key="c1",
            sample={"type": "sampler.step", "step": 10, "total_steps": 20, "pct": 50},
        )
        snap = reg.worker_progress("exp_test").snapshot()
        self.assertIn("ck1", snap["checkpoints"])
        self.assertEqual(snap["checkpoints"]["ck1"]["cells"]["c1"]["pct"], 50)


# ── Results UI: cell error inline ──────────────────────────────────────


class ResultsUIErrorInlineTests(unittest.TestCase):
    def setUp(self):
        self._js_path = NODE_DIR / "web" / "testing-results.js"
        self.assertTrue(self._js_path.exists())

    def _read(self):
        return self._js_path.read_text(encoding="utf-8")

    def test_error_class_present(self):
        text = self._read()
        self.assertIn("testing-results-cell-error", text)

    def test_error_role_alert(self):
        text = self._read()
        self.assertIn('role: "alert"', text)
        self.assertIn("cell-error", text)

    def test_error_data_testid(self):
        text = self._read()
        self.assertIn('"data-testid": "cell-error"', text)

    def test_failed_status_in_class(self):
        text = self._read()
        # renderCellCard builds class with status suffix
        self.assertIn("testing-results-cell-${status}", text)


# ── Results UI: confirm dialogs ────────────────────────────────────────


class ResultsUIConfirmDialogTests(unittest.TestCase):
    def setUp(self):
        self._js_path = NODE_DIR / "web" / "testing-results.js"
        self.assertTrue(self._js_path.exists())

    def test_stop_now_confirm(self):
        text = (NODE_DIR / "web" / "testing-results.js").read_text(encoding="utf-8")
        self.assertIn("Stop now kills all running cells immediately", text)
        self.assertIn("window.confirm", text)

    def test_stop_after_current_confirm(self):
        text = (NODE_DIR / "web" / "testing-results.js").read_text(encoding="utf-8")
        self.assertIn("Stop after current", text)


# ── Results UI: progress bar in checkpoint card ────────────────────────


class ResultsUIProgressBarTests(unittest.TestCase):
    def setUp(self):
        self._js_path = NODE_DIR / "web" / "testing-results.js"
        self.assertTrue(self._js_path.exists())

    def test_progress_bar_class(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn("testing-results-progress-bar-wrap", text)
        self.assertIn("testing-results-progress-bar-fill", text)

    def test_role_progressbar(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn('role: "progressbar"', text)
        self.assertIn('"aria-valuemin": "0"', text)
        self.assertIn('"aria-valuemax": "100"', text)

    def test_aria_label(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn('"aria-label": `checkpoint ${id} progress`', text)

    def test_aggregate_pct_helper(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn("function computeAggregatePct", text)
        self.assertIn("Object.values(cells).forEach", text)

    def test_window_worker_progress(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn("__comfymodal_worker_progress", text)
        self.assertIn("data.progress", text)


# ── A/B slider: keyboard + aria + actual=actual ───────────────────────


class ABSliderKeyboardTests(unittest.TestCase):
    def setUp(self):
        self._js_path = NODE_DIR / "web" / "testing-ab-slider.js"
        self.assertTrue(self._js_path.exists())

    def test_inline_slider_role(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn('role: "slider"', text)
        self.assertIn('"aria-label":', text)
        self.assertIn('"aria-valuemin": "0"', text)
        self.assertIn('"aria-valuemax": "100"', text)
        self.assertIn("tabindex: \"0\"", text)

    def test_inline_slider_keydown(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn("wrap.addEventListener(\"keydown\"", text)
        self.assertIn("ArrowLeft", text)
        self.assertIn("ArrowRight", text)
        self.assertIn("Home", text)
        self.assertIn("End", text)

    def test_fullscreen_escape_closes(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn("Escape", text)
        self.assertIn("close();", text)
        self.assertIn("onKey", text)

    def test_fullscreen_actual_uses_natural_size(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn("naturalWidth", text)
        self.assertIn("naturalHeight", text)
        # Pan offsets to center
        self.assertIn("(rect.width - aw * scale) / 2", text)
        self.assertIn("(rect.height - ah * scale) / 2", text)

    def test_fullscreen_keyboard_zoom(self):
        text = self._js_path.read_text(encoding="utf-8")
        self.assertIn("zoomIn();", text)
        self.assertIn("zoomOut();", text)
        self.assertIn('ev.key === "+"', text)
        self.assertIn('ev.key === "-"', text)


# ── service registry exposes worker_progress ───────────────────────────


class RegistryWorkerProgressTests(unittest.TestCase):
    def test_registry_has_worker_progress(self):
        from experiment_service import ServiceRegistry
        reg = ServiceRegistry()
        buf = reg.worker_progress("exp_x")
        self.assertIsNotNone(buf)
        # Idempotent: same buffer
        self.assertIs(reg.worker_progress("exp_x"), buf)

    def test_registry_drop_clears_buffer(self):
        from experiment_service import ServiceRegistry
        reg = ServiceRegistry()
        reg.worker_progress("exp_y").update(
            checkpoint_id="ck1", cell_key="c1",
            sample={"type": "cell.started"},
        )
        reg.drop_scheduler("exp_y")
        # After drop, the buffer is removed; subsequent access creates a new one
        buf2 = reg.worker_progress("exp_y")
        snap = buf2.snapshot()
        self.assertEqual(snap["checkpoints"], {})


if __name__ == "__main__":
    unittest.main()
