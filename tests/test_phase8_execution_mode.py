"""H12 execution-mode tests: V2-only resolver, config, dispatch, invoker.

Scope
-----
- ``execution_runtime``: collapsed vocabulary — only ``v2`` resolves/executes;
  retired strings (v1/legacy/shadow) remain RECOGNIZED for migration and
  truthful rejection but are never executable.
- ``COMFYMODAL_RUNTIME`` ops lock: mechanism preserved, vocabulary collapsed
  to ``{v2}``; retired values logged-and-refused.
- Explicit request-captured retired modes: surfaced via ``retired=True`` /
  ``retired_request_mode`` so dispatchers reject truthfully (never silently
  relabeled as V2).
- POST /comfymodal/config validation: v2 accepted; v1/legacy/shadow rejected.
- Studio Single dispatch: retired requests rejected before acceptance; the
  non-V2 branch through ``direct_studio_run_completion`` is gone.
- Scheduler registration: V2ExperimentInvoker is the only registered invoker.

All tests mock transports and remote calls (no Modal, no GPU, no deploy).
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

# Ensure the custom-node root is importable
_NODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NODE_DIR not in sys.path:
    sys.path.insert(0, _NODE_DIR)

# ---------------------------------------------------------------------------
# 1. Resolver unit tests
# ---------------------------------------------------------------------------

from execution_runtime import (
    MODE_V1,
    MODE_V2,
    MODE_SHADOW,
    RETIRED_MODES,
    normalize_mode,
    is_retired_mode,
    resolve_execution_mode,
    retired_request_mode,
    retired_mode_error,
    engine_v1_retired_notice,
    validate_config_payload,
    capture_execution_mode,
)


class TestNormalizeModeRecognition(unittest.TestCase):
    """Recognition survives retirement (needed for migration + rejection)."""

    def test_v1_aliases(self):
        for alias in ("v1", "V1", "legacy", "LEGACY", "Legacy"):
            self.assertEqual(normalize_mode(alias), MODE_V1, f"alias={alias!r}")

    def test_v2(self):
        for val in ("v2", "V2"):
            self.assertEqual(normalize_mode(val), MODE_V2, f"val={val!r}")

    def test_shadow(self):
        for val in ("shadow", "SHADOW", "Shadow"):
            self.assertEqual(normalize_mode(val), MODE_SHADOW, f"val={val!r}")

    def test_invalid_returns_none(self):
        self.assertIsNone(normalize_mode(""))
        self.assertIsNone(normalize_mode("unknown"))
        self.assertIsNone(normalize_mode(None))
        self.assertIsNone(normalize_mode(42))

    def test_retired_classification(self):
        self.assertTrue(is_retired_mode(MODE_V1))
        self.assertTrue(is_retired_mode(MODE_SHADOW))
        self.assertFalse(is_retired_mode(MODE_V2))
        self.assertEqual(RETIRED_MODES, (MODE_V1, MODE_SHADOW))


class TestResolveExecutionModeV2Only(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("COMFYMODAL_RUNTIME", None)

    def test_default_is_v2(self):
        resolved = resolve_execution_mode()
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertEqual(resolved["source"], "default")
        self.assertFalse(resolved["locked"])
        self.assertFalse(resolved.get("retired"))

    def test_persisted_v2_honored(self):
        resolved = resolve_execution_mode(modal_settings={"execution_mode": "v2"})
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertEqual(resolved["source"], "server_setting")

    def test_persisted_v1_cannot_resolve_to_v1(self):
        """A stale persisted v1 value can never select the retired engine."""
        resolved = resolve_execution_mode(modal_settings={"execution_mode": "v1"})
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertNotEqual(resolved["source"], "server_setting")
        self.assertFalse(resolved.get("retired"))

    def test_env_v2_is_locked(self):
        os.environ["COMFYMODAL_RUNTIME"] = "v2"
        resolved = resolve_execution_mode(
            extra={"execution_mode": "v2"},
            modal_settings={"execution_mode": "v2"},
        )
        # Request precedence still wins over env for captured requests.
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertEqual(resolved["source"], "request")

    def test_env_v2_locks_uncaptured_requests(self):
        os.environ["COMFYMODAL_RUNTIME"] = "v2"
        resolved = resolve_execution_mode(modal_settings={"execution_mode": "v2"})
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertEqual(resolved["source"], "env_override")
        self.assertTrue(resolved["locked"])

    def test_env_v1_refused_falls_through_to_v2(self):
        os.environ["COMFYMODAL_RUNTIME"] = "v1"
        resolved = resolve_execution_mode()
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertFalse(resolved["locked"])

    def test_env_legacy_refused(self):
        os.environ["COMFYMODAL_RUNTIME"] = "legacy"
        resolved = resolve_execution_mode()
        self.assertEqual(resolved["mode"], MODE_V2)

    def test_env_shadow_refused(self):
        os.environ["COMFYMODAL_RUNTIME"] = "shadow"
        resolved = resolve_execution_mode()
        self.assertEqual(resolved["mode"], MODE_V2)

    def test_env_garbage_ignored(self):
        os.environ["COMFYMODAL_RUNTIME"] = "bogus"
        resolved = resolve_execution_mode()
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertEqual(resolved["source"], "default")

    def test_request_captured_wins_over_persisted(self):
        resolved = resolve_execution_mode(
            extra={"execution_mode": "v2"},
            modal_settings={"execution_mode": "v1"},
        )
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertEqual(resolved["source"], "request")

    def test_explicit_retired_request_surfaced_not_executable(self):
        """An explicit v1 request is surfaced with retired=True — never
        silently relabeled as V2 and never returned as executable."""
        resolved = resolve_execution_mode(modal_options={"execution_mode": "v1"})
        self.assertEqual(resolved["mode"], MODE_V1)
        self.assertEqual(resolved["source"], "request")
        self.assertTrue(resolved["retired"])

    def test_explicit_legacy_alias_request_surfaced_as_v1(self):
        resolved = resolve_execution_mode(modal_options={"execution_mode": "legacy"})
        self.assertEqual(resolved["mode"], MODE_V1)
        self.assertTrue(resolved["retired"])

    def test_explicit_shadow_request_surfaced(self):
        resolved = resolve_execution_mode(modal_options={"execution_mode": "shadow"})
        self.assertEqual(resolved["mode"], MODE_SHADOW)
        self.assertTrue(resolved["retired"])

    def test_env_cannot_resurrect_retired_engines(self):
        """Even COMFYMODAL_RUNTIME=v1 cannot make a clean request execute V1."""
        os.environ["COMFYMODAL_RUNTIME"] = "v1"
        resolved = resolve_execution_mode(extra={"execution_mode": "v2"})
        self.assertEqual(resolved["mode"], MODE_V2)


class TestRetiredRequestGuard(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("COMFYMODAL_RUNTIME", None)

    def test_clean_request_returns_none(self):
        self.assertIsNone(retired_request_mode(None))
        self.assertIsNone(retired_request_mode({"execution_mode": "v2"}))
        self.assertIsNone(retired_request_mode({}))

    def test_retired_requests_detected(self):
        self.assertEqual(retired_request_mode({"execution_mode": "v1"}), MODE_V1)
        self.assertEqual(retired_request_mode({"execution_mode": "legacy"}), MODE_V1)
        self.assertEqual(retired_request_mode({"execution_mode": "shadow"}), MODE_SHADOW)

    def test_error_message_truthful(self):
        msg = retired_mode_error("v1")
        self.assertIn("retired", msg)
        self.assertIn(engine_v1_retired_notice(), msg)
        self.assertIn("shadow", retired_mode_error("shadow"))


class TestValidateConfigPayload(unittest.TestCase):
    def test_accepts_v2(self):
        self.assertIsNone(validate_config_payload({"execution_mode": "v2"}))

    def test_rejects_v1(self):
        err = validate_config_payload({"execution_mode": "v1"})
        self.assertIsNotNone(err)
        self.assertIn("Engine V1 retired", err)

    def test_rejects_legacy_alias(self):
        err = validate_config_payload({"execution_mode": "legacy"})
        self.assertIsNotNone(err)
        self.assertIn("Engine V1 retired", err)

    def test_rejects_shadow(self):
        err = validate_config_payload({"execution_mode": "shadow"})
        self.assertIsNotNone(err)
        self.assertIn("retired", err)

    def test_rejects_invalid(self):
        err = validate_config_payload({"execution_mode": "invalid"})
        self.assertIsNotNone(err)
        self.assertIn("Invalid", err)

    def test_rejects_non_string(self):
        err = validate_config_payload({"execution_mode": 42})
        self.assertIsNotNone(err)
        self.assertIn("string", err)

    def test_none_when_not_present(self):
        self.assertIsNone(validate_config_payload({"gpu": "rtx-pro-6000"}))


class TestAvailableExecutionModesRemoved(unittest.TestCase):
    def test_constant_removed_from_module(self):
        import execution_runtime
        self.assertFalse(hasattr(execution_runtime, "AVAILABLE_EXECUTION_MODES"))


class TestCaptureExecutionMode(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("COMFYMODAL_RUNTIME", None)

    def test_capture_defaults_to_v2(self):
        self.assertEqual(capture_execution_mode(), MODE_V2)

    def test_capture_v2_request(self):
        self.assertEqual(capture_execution_mode(modal_options={"execution_mode": "v2"}), MODE_V2)

    def test_capture_never_returns_retired_engine(self):
        """Capture refuses retired requests (callers guard first; this is the
        defensive backstop)."""
        with self.assertRaises(ValueError):
            capture_execution_mode(modal_options={"execution_mode": "v1"})
        with self.assertRaises(ValueError):
            capture_execution_mode(modal_options={"execution_mode": "shadow"})

    def test_capture_with_retired_persisted_value_yields_v2(self):
        self.assertEqual(
            capture_execution_mode(modal_settings={"execution_mode": "v1"}),
            MODE_V2,
        )


# ---------------------------------------------------------------------------
# 2. Studio Single dispatch — retired requests rejected before execution
# ---------------------------------------------------------------------------

class TestStudioSingleRetiredRejection(unittest.TestCase):
    @patch("__init__._load_modal_settings")
    def test_v1_request_rejected_without_execution(self, mock_settings):
        mock_settings.return_value = {"execution_mode": "v2"}
        from studio_run_adapter import handle_studio_run_async
        import asyncio

        executed = {}

        async def _must_not_execute(*args, **kwargs):
            executed["called"] = True
            return {"status": "ok"}

        with patch("studio_run_adapter.playground_adapter_direct_run", new=_must_not_execute):
            result = asyncio.run(handle_studio_run_async(
                "preset_1", "txt2img", {"prompt": "test"},
                _NODE_DIR, modal_options={"execution_mode": "v1"},
            ))
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("error_code"), "EXECUTION_MODE_RETIRED")
        self.assertNotIn("called", executed)

    @patch("__init__._load_modal_settings")
    def test_shadow_request_rejected_without_execution(self, mock_settings):
        mock_settings.return_value = {"execution_mode": "v2"}
        from studio_run_adapter import handle_studio_run_async
        import asyncio

        async def _must_not_execute(*args, **kwargs):
            return {"status": "ok"}

        with patch("studio_run_adapter.playground_adapter_direct_run", new=_must_not_execute):
            result = asyncio.run(handle_studio_run_async(
                "preset_1", "txt2img", {"prompt": "test"},
                _NODE_DIR, modal_options={"execution_mode": "shadow"},
            ))
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("error_code"), "EXECUTION_MODE_RETIRED")


# ---------------------------------------------------------------------------
# 3. Scheduler registration — V2 invoker only
# ---------------------------------------------------------------------------

class TestSchedulerV2OnlyRegistration(unittest.TestCase):
    def test_no_local_remote_invoker_registration_in_schedule_and_start(self):
        """The mode-selected LocalRemoteInvoker branch is removed from
        ``_schedule_and_start``."""
        import inspect
        import studio_run_adapter
        src = inspect.getsource(studio_run_adapter._schedule_and_start)
        self.assertNotIn("LocalRemoteInvoker(", src)
        self.assertIn("V2ExperimentInvoker(", src)

    def test_single_dispatch_has_no_direct_completion_branch(self):
        """The direct=True non-V2 branch (V1 fallback + shadow comparison) is
        removed from ``handle_studio_run_async``."""
        import inspect
        import studio_run_adapter
        src = inspect.getsource(studio_run_adapter.handle_studio_run_async)
        self.assertNotIn("_record_shadow_plan_comparison(", src)
        self.assertNotIn("direct_studio_run_completion(", src)


# ---------------------------------------------------------------------------
# 4. Workflow dispatch — legacy run removed, retired requests rejected
# ---------------------------------------------------------------------------

class TestWorkflowV2Only(unittest.TestCase):
    def test_workflow_legacy_run_removed(self):
        import studio_workflow_run
        self.assertFalse(hasattr(studio_workflow_run, "_workflow_legacy_run"))

    def test_workflow_handler_has_no_legacy_branch(self):
        import inspect
        import studio_workflow_run
        src = inspect.getsource(studio_workflow_run.handle_workflow_run_async)
        self.assertNotIn("_workflow_legacy_run", src)
        self.assertIn("EXECUTION_MODE_RETIRED", src)


# ---------------------------------------------------------------------------
# 5. Canvas dispatch — V2-only structural proof
# ---------------------------------------------------------------------------

class TestCanvasV2Only(unittest.TestCase):
    def test_canvas_prompt_handler_has_no_v1_executor_call(self):
        """The canvas prompt job executes through execute_plan only; the
        execute_modal_prompt branch is gone."""
        with open(os.path.join(_NODE_DIR, "__init__.py"), encoding="utf-8") as f:
            src = f.read()
        # The canvas dispatch region must not call the V1 executor anymore.
        self.assertNotIn("result = await execute_modal_prompt(", src)
        self.assertNotIn('if _mode in {"v2", "shadow"}:', src)
        self.assertIn('"error": "execution_mode_retired"', src)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
