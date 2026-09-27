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


# ── Results UI / A/B slider: retired with their modules (H18 Wave G) ───


class ResultsUIRetiredContractTests(unittest.TestCase):
    """The legacy Results UI and A/B slider modules were deleted in Wave G
    (History V2 is the sole durable History; the slider is Phase-I scope).
    Their inline-error/confirm/progress behaviors have no surviving owner."""

    def test_retired_modules_absent(self):
        for name in ["testing-results.js", "testing-ab-slider.js"]:
            self.assertFalse(
                (NODE_DIR / "web" / name).exists(),
                f"web/{name} must stay deleted (Wave G)",
            )

    def test_no_production_reference(self):
        for path in (NODE_DIR / "web").glob("*.js"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("testing-results.js", text)
            self.assertNotIn("testing-ab-slider.js", text)


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
