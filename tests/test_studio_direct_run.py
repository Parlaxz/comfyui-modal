"""Studio single-run dispatch contract after H19 Wave G dead-code cleanup.

The retired V1 single-run implementation (``direct_studio_run_completion``,
``_prepare_studio_run_context``, ``_handle_studio_run_scheduler``, the
``direct=`` scheduler branch, and ``_playground_runtime_mode``) was deleted
by H19. This module now pins the surviving V2-only contract:

  - handle_studio_run_async dispatches unconditionally to the
    PlaygroundService adapter (V2 ExecutionPlan path)
  - no scheduler/context/V1-completion residue remains in the handler
  - retired engine requests are still rejected before any execution
  - POST /comfymodal/studio/run stays registered (MODERN_LIVE V2)

Former dedicated V1-implementation tests were removed with their subject;
still-valid contracts live in tests/test_runtime_playground_v2.py,
tests/test_phase8_execution_mode.py and tests/test_h12_v2_only_consolidation.py.
"""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _adapter_src() -> str:
    return (REPO_ROOT / "studio_run_adapter.py").read_text(encoding="utf-8")


def _handler_source() -> str:
    src = _adapter_src()
    start = src.index("async def handle_studio_run_async")
    end = src.index("\ndef handle_studio_run(", start)
    return src[start:end]


class StudioSingleRunV2OnlyContractTests(unittest.TestCase):
    """The Single run seam is V2-only with zero V1/scheduler residue."""

    def test_handler_has_no_deleted_helper_references(self):
        """handle_studio_run_async contains no reference to any helper H19
        deleted (caller-proof: zero production callers at deletion time)."""
        src = _handler_source()
        for gone in ("direct_studio_run_completion", "_prepare_studio_run_context",
                     "_handle_studio_run_scheduler"):
            self.assertNotIn(gone, src)

    def test_direct_parameter_removed(self):
        """The retired ``direct=`` kwarg is gone from both handlers."""
        import inspect
        import studio_run_adapter
        for fn in (studio_run_adapter.handle_studio_run_async,
                   studio_run_adapter.handle_studio_run):
            self.assertNotIn("direct", inspect.signature(fn).parameters)

    def test_deleted_helpers_absent_from_module(self):
        """The deleted helpers no longer exist anywhere in the module."""
        import studio_run_adapter
        for gone in ("_playground_runtime_mode", "_prepare_studio_run_context",
                     "_handle_studio_run_scheduler", "direct_studio_run_completion"):
            self.assertFalse(hasattr(studio_run_adapter, gone), gone)

    def test_handler_dispatches_unconditionally_to_v2_adapter(self):
        """Every accepted request reaches playground_adapter_direct_run."""
        import studio_run_adapter

        async def _fake_direct(*args, **kwargs):
            return {"status": "ok", "output_paths": [], "v2": True}

        with patch.object(studio_run_adapter, "playground_adapter_direct_run",
                          new=_fake_direct), \
             patch("__init__._load_modal_settings", return_value={}):
            result = asyncio.run(studio_run_adapter.handle_studio_run_async(
                "preset_x", "txt2img", {}, REPO_ROOT,
                modal_options={"execution_mode": "v2"},
            ))
        self.assertEqual(result.get("status"), "ok")
        self.assertTrue(result.get("v2"))

    def test_retired_engine_request_rejected_before_dispatch(self):
        """Retired modes never reach the V2 boundary (H12 contract kept)."""
        import studio_run_adapter

        async def _must_not_execute(*args, **kwargs):
            raise AssertionError("retired request must not execute")

        with patch.object(studio_run_adapter, "playground_adapter_direct_run",
                          new=_must_not_execute), \
             patch("__init__._load_modal_settings", return_value={}):
            result = asyncio.run(studio_run_adapter.handle_studio_run_async(
                "preset_x", "txt2img", {}, REPO_ROOT,
                modal_options={"execution_mode": "v1"},
            ))
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("error_code"), "EXECUTION_MODE_RETIRED")


class StudioRunRouteStillRegisteredTests(unittest.TestCase):
    """POST /comfymodal/studio/run remains a registered MODERN_LIVE route."""

    def test_route_decorator_present(self):
        src = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('@_server.routes.post("/comfymodal/studio/run")', src)


if __name__ == "__main__":
    unittest.main()
