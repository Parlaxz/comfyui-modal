"""H12 — V2-only execution consolidation tests.

Covers the frozen H12 obligations that are not pinned elsewhere:

1. Persisted execution_mode migration matrix (v1/legacy/shadow/garbage → v2,
   idempotent, persisted rewrite, one-time notice, env-lock precedence).
2. POST /config retired-engine rejection (v1 / legacy / shadow) via the real
   route handler.
3. GET /config truthfulness: no available_execution_modes / readiness engine
   advertising; migration notice surfaced.
4. Comparison survival proof: the frozen legacy executor seam is reachable
   ONLY from the Comparison runner; no Studio/Workflow/Experiment/canvas
   dispatch path reaches it.
5. No-new-irreproducible-run proofs at adapter level for Single, Workflow,
   Experiment, and canvas Cloud.

No live Modal calls, no GPU, no deploy.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_NODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NODE_DIR not in sys.path:
    sys.path.insert(0, _NODE_DIR)

import __init__ as init_mod
from execution_runtime import (
    MODE_V1,
    MODE_V2,
    MODE_SHADOW,
    engine_v1_retired_notice,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Persisted migration matrix
# ---------------------------------------------------------------------------

class MigrationMatrixTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings_file = Path(self._tmp.name) / ".modal_settings.json"
        self._orig_file = init_mod._MODAL_SETTINGS_FILE
        init_mod._MODAL_SETTINGS_FILE = str(self.settings_file)
        init_mod._modal_settings_cache = None
        self.addCleanup(setattr, init_mod, "_MODAL_SETTINGS_FILE", self._orig_file)
        self.addCleanup(setattr, init_mod, "_modal_settings_cache", None)
        self.addCleanup(self._clear_notice)

    def _clear_notice(self):
        init_mod._EXECUTION_MODE_MIGRATION_NOTICE = None

    def _write(self, payload: dict):
        self.settings_file.write_text(json.dumps(payload), encoding="utf-8")

    def _disk(self) -> dict:
        return json.loads(self.settings_file.read_text(encoding="utf-8"))

    def test_1_persisted_v1_migrates_to_v2_on_disk(self):
        self._write({"execution_mode": "v1", "gpu": "l4"})
        settings = init_mod._load_modal_settings()
        self.assertEqual(settings["execution_mode"], MODE_V2)
        disk = self._disk()
        self.assertEqual(disk["execution_mode"], MODE_V2, "migration must rewrite the persisted value")
        self.assertEqual(disk.get("gpu"), "l4", "unrelated settings preserved")

    def test_2_legacy_alias_normalizes_to_v2(self):
        self._write({"execution_mode": "legacy"})
        settings = init_mod._load_modal_settings()
        self.assertEqual(settings["execution_mode"], MODE_V2)
        self.assertEqual(self._disk()["execution_mode"], MODE_V2)

    def test_3_already_v2_is_untouched(self):
        self._write({"execution_mode": "v2"})
        before = self._disk()
        settings = init_mod._load_modal_settings()
        self.assertEqual(settings["execution_mode"], MODE_V2)
        self.assertIsNone(init_mod._EXECUTION_MODE_MIGRATION_NOTICE, "no notice for clean state")
        self.assertEqual(self._disk(), before)

    def test_4_garbage_safely_normalizes_to_v2(self):
        self._write({"execution_mode": "not-a-mode"})
        settings = init_mod._load_modal_settings()
        self.assertEqual(settings["execution_mode"], MODE_V2)
        self.assertEqual(self._disk()["execution_mode"], MODE_V2)

    def test_5_shadow_persisted_value_never_survives(self):
        self._write({"execution_mode": "shadow"})
        settings = init_mod._load_modal_settings()
        self.assertEqual(settings["execution_mode"], MODE_V2)
        self.assertEqual(self._disk()["execution_mode"], MODE_V2)

    def test_6_second_load_is_idempotent_no_repeat_notice(self):
        self._write({"execution_mode": "v1"})
        init_mod._load_modal_settings()
        first_notice = init_mod._EXECUTION_MODE_MIGRATION_NOTICE
        self.assertIsNotNone(first_notice)
        # Simulate a fresh process load against the rewritten file.
        init_mod._modal_settings_cache = None
        init_mod._EXECUTION_MODE_MIGRATION_NOTICE = None
        init_mod._load_modal_settings()
        self.assertIsNone(
            init_mod._EXECUTION_MODE_MIGRATION_NOTICE,
            "repeat startup must NOT re-migrate or re-notice",
        )
        self.assertEqual(self._disk()["execution_mode"], MODE_V2)

    def test_7_notice_text_is_truthful_canonical(self):
        self._write({"execution_mode": "v1"})
        init_mod._load_modal_settings()
        self.assertEqual(
            init_mod._EXECUTION_MODE_MIGRATION_NOTICE,
            "Engine V1 retired; future runs use V2.",
        )

    def test_8_env_lock_wins_over_migrated_setting(self):
        self._write({"execution_mode": "v1"})
        settings = init_mod._load_modal_settings()
        self.assertEqual(settings["execution_mode"], MODE_V2)
        os.environ["COMFYMODAL_RUNTIME"] = "v2"
        self.addCleanup(os.environ.pop, "COMFYMODAL_RUNTIME")
        resolved = init_mod.resolve_execution_mode(modal_settings=settings)
        self.assertEqual(resolved["mode"], MODE_V2)
        self.assertTrue(resolved["locked"])
        self.assertEqual(resolved["source"], "env_override")

    def test_9_save_never_persists_retired_engine(self):
        self._write({"execution_mode": "v2"})
        init_mod._load_modal_settings()
        init_mod._save_modal_settings({"execution_mode": "v1", "quality": 80})
        self.assertEqual(self._disk()["execution_mode"], MODE_V2)
        self.assertEqual(self._disk().get("quality"), 80)

    def test_10_comfymodal_enabled_is_never_mapped_into_execution_mode(self):
        """The browser canvas key is never reinterpreted server-side."""
        self._write({"execution_mode": "v1"})
        settings = init_mod._load_modal_settings()
        self.assertNotIn("comfymodal_enabled", settings)
        self.assertEqual(settings["execution_mode"], MODE_V2)


# ---------------------------------------------------------------------------
# 2. /config contract
# ---------------------------------------------------------------------------

class ConfigContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_routes_registered import _StubServer, _build_init_with_stub

        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings_file = Path(self._tmp.name) / ".modal_settings.json"
        self._orig_file = self.init_mod._MODAL_SETTINGS_FILE
        self.init_mod._MODAL_SETTINGS_FILE = str(self.settings_file)
        self.init_mod._modal_settings_cache = None
        self.init_mod._EXECUTION_MODE_MIGRATION_NOTICE = None
        self.addCleanup(setattr, self.init_mod, "_MODAL_SETTINGS_FILE", self._orig_file)
        self.addCleanup(setattr, self.init_mod, "_modal_settings_cache", None)
        self.addCleanup(setattr, self.init_mod, "_EXECUTION_MODE_MIGRATION_NOTICE", None)

    def _handlers(self):
        from tests.test_routes_registered import _handler_for

        get = _handler_for(self.init_mod, "GET", "/comfymodal/config")
        post = _handler_for(self.init_mod, "POST", "/comfymodal/config")
        return get, post

    def _request(self, body=None):
        from tests.test_routes_registered import _MockRequest

        return _MockRequest(json_body=body if body is not None else {})

    def test_11_get_config_advertises_no_retired_engine(self):
        get, _ = self._handlers()
        body = json.loads(_run(get(self._request())).body)
        self.assertEqual(body["execution_mode"], MODE_V2)
        self.assertNotIn("available_execution_modes", body)
        self.assertNotIn("execution_readiness", body)

    def test_12_post_config_rejects_retired_engines(self):
        _, post = self._handlers()
        for retired in ("v1", "legacy", "shadow"):
            resp = _run(post(self._request({"execution_mode": retired})))
            self.assertEqual(resp.status, 400, retired)
            payload = json.loads(resp.body)
            self.assertEqual(payload["status"], "error", retired)
        disk = json.loads(self.settings_file.read_text(encoding="utf-8")) if self.settings_file.exists() else {}
        self.assertNotIn(disk.get("execution_mode"), (MODE_V1, MODE_SHADOW))

    def test_13_post_config_accepts_v2(self):
        _, post = self._handlers()
        resp = _run(post(self._request({"execution_mode": "v2"})))
        self.assertEqual(resp.status, 200)
        disk = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(disk["execution_mode"], MODE_V2)

    def test_14_migration_notice_surfaced_via_get_config(self):
        self.settings_file.write_text(json.dumps({"execution_mode": "v1"}), encoding="utf-8")
        get, _ = self._handlers()
        body = json.loads(_run(get(self._request())).body)
        self.assertEqual(body.get("engine_migration_notice"), "Engine V1 retired; future runs use V2.")


# ---------------------------------------------------------------------------
# 3. No new irreproducible modern runs (adapter-level proofs)
# ---------------------------------------------------------------------------

class RetiredRequestRejectionTests(unittest.TestCase):
    """A NEW request carrying v1/legacy/shadow can never execute the retired
    engine on any modern surface."""

    def setUp(self):
        import studio_run_adapter

        self.adapter = studio_run_adapter

    def test_15_single_rejects_all_retired_modes(self):
        for retired in ("v1", "legacy", "shadow"):
            with patch.object(self.adapter, "playground_adapter_direct_run") as v2_run, \
                 patch("__init__._load_modal_settings", return_value={"execution_mode": MODE_V2}):
                result = _run(self.adapter.handle_studio_run_async(
                    "preset_x", "txt2img", {}, _NODE_DIR,
                    modal_options={"execution_mode": retired},
                ))
            self.assertEqual(result["status"], "error", retired)
            self.assertEqual(result["error_code"], "EXECUTION_MODE_RETIRED", retired)
            v2_run.assert_not_called()

    def test_16_experiment_rejects_retired_modes_before_scheduler(self):
        for retired in ("v1", "shadow"):
            result = self.adapter.handle_studio_experiment(
                ["preset_x"], "txt2img", {"defaults": {}, "axes": {}}, _NODE_DIR,
                modal_options={"execution_mode": retired},
            )
            self.assertEqual(result["status"], "error", retired)
            self.assertEqual(result["error_code"], "EXECUTION_MODE_RETIRED", retired)

    def test_17_canvas_guard_helper_rejects_retired_modes(self):
        from execution_runtime import retired_request_mode
        self.assertEqual(retired_request_mode({"execution_mode": "v1"}), MODE_V1)
        self.assertEqual(retired_request_mode({"execution_mode": "shadow"}), MODE_SHADOW)
        self.assertIsNone(retired_request_mode({"execution_mode": "v2"}))
        self.assertIsNone(retired_request_mode(None))


# ---------------------------------------------------------------------------
# 4. Comparison survival proof (frozen C/E sequencing seam)
# ---------------------------------------------------------------------------

class ComparisonSurvivalAuditTests(unittest.TestCase):
    """Post-H14 caller audit: the Comparison execution seam is retired
    (Wave E); no studio/workflow/comparison dispatch may use a V1 executor.
    The only remaining direct ``run_prompt_stream`` call in __init__.py is
    the warmup route (Wave F/G destination — untouched by Wave E)."""

    def _read(self, rel: str) -> str:
        with open(os.path.join(_NODE_DIR, rel), encoding="utf-8") as f:
            return f.read()

    def test_18_comparison_run_route_retired_not_executing(self):
        """H14 Wave E: /comparison/run stays registered but returns the frozen
        bounded retired response and never streams through the executor.
        H19 Wave G: the dead ``_execute_comparison_profile`` body was deleted
        (zero production callers since H14)."""
        src = self._read("__init__.py")
        self.assertIn("/comfymodal/comparison/run", src)
        self.assertIn('"error_code": "COMPARISON_RETIRED"', src)
        handler_start = src.index("async def comparison_run(")
        handler_end = src.index("@_server.routes.get", handler_start)
        self.assertNotIn("run_prompt_stream", src[handler_start:handler_end])
        self.assertNotIn("_execute_comparison_profile", src)  # H19: deleted

    def test_19_no_studio_or_workflow_dispatch_uses_v1_executor(self):
        adapter_src = self._read("studio_run_adapter.py")
        workflow_src = self._read("studio_workflow_run.py")
        # The Workflow legacy V1 path is fully retired (no definition, no call).
        self.assertNotIn("def _workflow_legacy_run", workflow_src)
        self.assertNotIn("_workflow_legacy_run(", workflow_src)
        # The Single handler no longer calls the V1 completion boundary.
        single_src = adapter_src.split("async def handle_studio_run_async")[1].split("\ndef handle_studio_run(")[0]
        self.assertNotIn("direct_studio_run_completion(", single_src)
        self.assertNotIn("_record_shadow_plan_comparison(", adapter_src)
        # The scheduler registers only the V2 invoker.
        sched_src = adapter_src.split("async def _schedule_and_start")[1].split("\nasync def ")[0]
        self.assertIn("V2ExperimentInvoker(", sched_src)
        self.assertNotIn("LocalRemoteInvoker(", sched_src)

    def test_20_canvas_cloud_has_no_v1_branch(self):
        src = self._read("__init__.py")
        self.assertNotIn("result = await execute_modal_prompt(", src)
        self.assertNotIn('if _mode in {"v2", "shadow"}:', src)

    def test_21_experiment_runner_v1_class_deleted_by_wave_g(self):
        """H19 Wave G deleted the retired V1 ``LocalRemoteInvoker`` class
        (zero production registrations since H12); no production module
        imports it as an invoker anymore."""
        import experiment_runner
        self.assertFalse(hasattr(experiment_runner, "LocalRemoteInvoker"))
        adapter_src = self._read("studio_run_adapter.py")
        self.assertNotIn("from experiment_runner import LocalRemoteInvoker", adapter_src)
        init_src = self._read("__init__.py")
        self.assertNotIn("LocalRemoteInvoker,", init_src)


if __name__ == "__main__":
    unittest.main()
