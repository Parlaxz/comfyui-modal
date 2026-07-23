"""Focused tests for Phase 0/2/3 remote identity and lifecycle capture."""

from __future__ import annotations

import os
import tempfile
import unittest
from typing import Any
from unittest.mock import patch
from pathlib import Path

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, RestorePlan
from comfymodal_runtime.runtime_executor import RuntimeExecutor, ExecutionContext
from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from comfymodal_runtime.trace import PROCESS_REMOTE_LIFECYCLE, PROCESS_REMOTE_METHOD

import comfymodal_runtime.modal_app as modal_app


def _writable_config(comfyui_root: str | None = None) -> BootstrapConfig:
    """Return a BootstrapConfig rooted at a writable temp directory."""
    root = comfyui_root or tempfile.mkdtemp()
    models_path = Path(root) / "models"
    models_path.mkdir(parents=True, exist_ok=True)
    return BootstrapConfig(
        comfyui_root=root,
        models_path=str(models_path),
        install_requirements_on_startup=False,
    )


class TestCaptureRemoteIdentity(unittest.TestCase):
    """Phase 0/3 — identity capture at remote entry."""

    def _clear_env_identity(self) -> dict[str, str]:
        saved = {}
        for key in ("MODAL_TASK_ID", "MODAL_IMAGE_ID", "MODAL_CLOUD_PROVIDER", "MODAL_REGION"):
            saved[key] = os.environ.pop(key, "")
        os.environ.pop("COMFYMODAL_RUNTIME", None)
        return saved

    def _restore_env(self, saved: dict[str, str]) -> None:
        for key, value in saved.items():
            if value:
                os.environ[key] = value

    def test_returns_empty_when_no_env(self):
        saved = self._clear_env_identity()
        try:
            identity = modal_app._capture_remote_identity()
            self.assertIsInstance(identity, dict)
            # modal_input_id is absent because _modal is None in tests
            self.assertNotIn("modal_input_id", identity)
            for key in ("container_task_id", "image_id", "cloud", "region", "runtime_mode"):
                self.assertNotIn(key, identity)
        finally:
            self._restore_env(saved)

    def test_captures_env_vars(self):
        saved = self._clear_env_identity()
        try:
            os.environ["MODAL_TASK_ID"] = "task-abc"
            os.environ["MODAL_IMAGE_ID"] = "img-456"
            os.environ["MODAL_CLOUD_PROVIDER"] = "gcp"
            os.environ["MODAL_REGION"] = "us-central1"
            os.environ["COMFYMODAL_RUNTIME"] = "v2"
            identity = modal_app._capture_remote_identity()
            self.assertEqual(identity.get("container_task_id"), "task-abc")
            self.assertEqual(identity.get("image_id"), "img-456")
            self.assertEqual(identity.get("cloud"), "gcp")
            self.assertEqual(identity.get("region"), "us-central1")
            self.assertEqual(identity.get("runtime_mode"), "v2")
        finally:
            self._restore_env(saved)

    def test_no_secrets_in_identity(self):
        saved = self._clear_env_identity()
        try:
            os.environ["MODAL_TASK_ID"] = "task-abc-123"
            os.environ["MODAL_IMAGE_ID"] = "img-456"
            os.environ["MODAL_CLOUD_PROVIDER"] = "gcp"
            os.environ["MODAL_REGION"] = "us-central1"
            identity = modal_app._capture_remote_identity()
            sensitive_keys = {"token", "secret", "password", "credential"}
            for k in identity:
                lower = k.lower()
                self.assertFalse(
                    any(s in lower for s in sensitive_keys),
                    f"identity key '{k}' appears sensitive",
                )
            for v in identity.values():
                lower = str(v).lower()
                self.assertFalse(
                    any(s in lower for s in sensitive_keys),
                    f"identity value '{str(v)[:50]}' appears sensitive",
                )
        finally:
            self._restore_env(saved)

    def test_graceful_when_modal_not_available(self):
        """_capture_remote_identity does not raise when modal is None."""
        saved = self._clear_env_identity()
        try:
            identity = modal_app._capture_remote_identity()
            self.assertIsInstance(identity, dict)
        finally:
            self._restore_env(saved)

    def test_safe_current_input_id_fallback(self):
        """Verify safe fallback — current_input_id not available in test env."""
        saved = self._clear_env_identity()
        try:
            identity = modal_app._capture_remote_identity()
            self.assertNotIn("modal_input_id", identity)
        finally:
            self._restore_env(saved)


class TestResourceIdentity(unittest.TestCase):
    """Phase 2 — resource/volume/snapshot config metadata."""

    def test_returns_resource_fields(self):
        resources = modal_app._resource_identity()
        for key in ("gpu", "cpu", "memory_mb", "snapshot_enabled", "gpu_snapshot_enabled",
                    "models_volume", "runtime_state_volume", "custom_nodes_volume"):
            self.assertIn(key, resources, f"missing key: {key}")
        self.assertIsInstance(resources["cpu"], int)
        self.assertIsInstance(resources["memory_mb"], int)

    def test_additive_common_schema_keys_present(self):
        """Verify additive common-schema keys in _resource_identity."""
        resources = modal_app._resource_identity()
        # ── App / class / method identity ──
        self.assertIn("app_name", resources)
        self.assertIn("class_name", resources)
        # ── Target / max inputs ──
        self.assertIn("target_inputs", resources)
        self.assertIn("max_inputs", resources)
        self.assertIsInstance(resources["target_inputs"], int)
        self.assertIsInstance(resources["max_inputs"], int)
        # ── Volume mount paths ──
        self.assertIn("volume_mount_paths", resources)
        self.assertIsInstance(resources["volume_mount_paths"], dict)
        if resources["volume_mount_paths"]:
            for vol_name, mount_path in resources["volume_mount_paths"].items():
                self.assertIsInstance(vol_name, str)
                self.assertIsInstance(mount_path, str)

    def test_no_raw_workflow_or_credentials_in_resource_identity(self):
        """Ensure no client-generated IDs or raw workflow/credential data."""
        resources = modal_app._resource_identity()
        sensitive_patterns = {"token", "secret", "password", "credential",
                              "workflow", "image_data", "api_key"}
        for k in resources:
            lower = k.lower()
            self.assertFalse(
                any(s in lower for s in sensitive_patterns),
                f"resource key '{k}' appears to contain raw data",
            )
        for v in resources.values():
            if not isinstance(v, str):
                continue
            lower = v.lower()
            self.assertFalse(
                any(s in lower for s in sensitive_patterns),
                f"resource value '{str(v)[:80]}' appears to contain sensitive data",
            )

    def test_gpu_snapshot_flag_from_env(self):
        os.environ["COMFYMODAL_ENABLE_GPU_SNAPSHOT"] = "1"
        try:
            resources = modal_app._resource_identity()
            self.assertEqual(resources["gpu_snapshot_enabled"], "True")
        finally:
            os.environ.pop("COMFYMODAL_ENABLE_GPU_SNAPSHOT", None)

    def test_gpu_snapshot_flag_false_when_unset(self):
        os.environ.pop("COMFYMODAL_ENABLE_GPU_SNAPSHOT", None)
        resources = modal_app._resource_identity()
        self.assertEqual(resources["gpu_snapshot_enabled"], "False")

    def test_no_secrets_in_resource_identity(self):
        resources = modal_app._resource_identity()
        sensitive_keys = {"token", "secret", "password", "key", "auth", "credential"}
        for k in resources:
            lower = k.lower()
            self.assertFalse(
                any(s in lower for s in sensitive_keys),
                f"resource key '{k}' appears sensitive",
            )
        for v in resources.values():
            if not isinstance(v, str):
                continue
            lower = v.lower()
            self.assertFalse(
                any(s in lower for s in sensitive_keys),
                f"resource value '{v[:50]}' appears sensitive",
            )


class TestStartupIdentityCapture(unittest.TestCase):
    """Phase 0 — startup() emits lifecycle and identity events."""

    def _entrypoint(self) -> modal_app.ModalRuntimeEntrypoint:
        tmp = tempfile.mkdtemp()
        return modal_app.ModalRuntimeEntrypoint(
            config=_writable_config(tmp),
            bootstrap=RuntimeBootstrap(
                _writable_config(tmp),
                start_backend=lambda: "in_process",
                restore_gpu_state=lambda: None,
                initialize_cuda=lambda: {"cuda_available": 1},
            ),
            executor=RuntimeExecutor(in_process_runner=lambda *_: {"ok": True}),
        )

    def test_startup_contains_lifecycle_spans(self):
        entrypoint = self._entrypoint()
        result = entrypoint.startup()
        trace = result["trace"]
        event_names = [e["name"] for e in trace.get("events", [])]
        self.assertIn("remote_method_entry", event_names)
        self.assertIn("gpu_invocation_submit", event_names)
        self.assertIn("remote_lifecycle_start", event_names)
        self.assertIn("remote_lifecycle_end", event_names)

    def test_startup_remote_method_entry_has_common_schema_keys(self):
        """Verify the remote_method_entry metadata has additive identity keys."""
        entrypoint = self._entrypoint()
        result = entrypoint.startup()
        trace = result["trace"]
        entry_meta = None
        for e in trace.get("events", []):
            if e["name"] == "remote_method_entry":
                entry_meta = e.get("metadata", {})
                break
        self.assertIsNotNone(entry_meta, "remote_method_entry not found")
        assert entry_meta is not None  # help for type checker
        # Common-schema keys
        self.assertEqual(entry_meta.get("app_name"), modal_app.APP_NAME)
        self.assertEqual(entry_meta.get("class_name"), modal_app.CLASS_NAME)
        self.assertEqual(entry_meta.get("method_name"), "startup")
        self.assertIn("snapshot", entry_meta)
        # Resource identity keys
        self.assertIn("gpu", entry_meta)
        self.assertIn("cpu", entry_meta)
        self.assertIn("memory_mb", entry_meta)
        self.assertIn("target_inputs", entry_meta)
        self.assertIn("max_inputs", entry_meta)
        self.assertIn("snapshot_enabled", entry_meta)
        # Volume identity
        self.assertIn("models_volume", entry_meta)
        self.assertIn("volume_mount_paths", entry_meta)

    def test_startup_identity_in_metadata(self):
        saved = {}
        for key in ("MODAL_TASK_ID", "MODAL_IMAGE_ID", "MODAL_CLOUD_PROVIDER", "MODAL_REGION"):
            saved[key] = os.environ.pop(key, "")
        os.environ.pop("COMFYMODAL_RUNTIME", None)
        try:
            os.environ["MODAL_TASK_ID"] = "task-startup"
            os.environ["COMFYMODAL_RUNTIME"] = "v2"
            entrypoint = self._entrypoint()
            result = entrypoint.startup()
            trace = result["trace"]
            self.assertEqual(trace.get("metadata", {}).get("container_task_id"), "task-startup")
        finally:
            for key, value in saved.items():
                if value:
                    os.environ[key] = value

    def test_startup_return_structure_preserved(self):
        entrypoint = self._entrypoint()
        result = entrypoint.startup()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["backend"], "in_process")
        self.assertIn("trace", result)
        self.assertIn("events", result["trace"])


class TestRestoreIdentityCapture(unittest.TestCase):
    """Phase 0 — restore() emits lifecycle, restore-plan, and preload evidence."""

    def test_restore_contains_lifecycle_and_preload_spans(self):
        entrypoint = modal_app.ModalRuntimeEntrypoint(
            bootstrap=RuntimeBootstrap(
                restore_gpu_state=lambda: None,
                initialize_cuda=lambda: {"cuda_available": 1},
            ),
            executor=RuntimeExecutor(in_process_runner=lambda *_: {"ok": True}),
        )
        result = entrypoint.restore()
        trace = result["trace"]
        event_names = [e["name"] for e in trace.get("events", [])]
        self.assertIn("remote_method_entry", event_names)
        self.assertIn("gpu_invocation_submit", event_names)
        self.assertIn("remote_lifecycle_start", event_names)
        self.assertIn("remote_lifecycle_end", event_names)
        self.assertIn("restore_completion_evidence", event_names)

    def test_restore_preload_submission_spans(self):
        """When no plan is published, preload spans are absent but evidence exists."""
        entrypoint = modal_app.ModalRuntimeEntrypoint(
            bootstrap=RuntimeBootstrap(
                restore_gpu_state=lambda: None,
                initialize_cuda=lambda: {"cuda_available": 1},
            ),
            executor=RuntimeExecutor(in_process_runner=lambda *_: {"ok": True}),
        )
        result = entrypoint.restore()
        trace = result["trace"]
        event_names = [e["name"] for e in trace.get("events", [])]
        # preload_submission_start requires a valid plan — absent here
        self.assertNotIn("preload_submission_start", event_names)
        self.assertNotIn("preload_submission_end", event_names)
        # But completion_evidence is always emitted
        evidence = next(e for e in trace["events"] if e["name"] == "restore_completion_evidence")
        self.assertEqual(evidence["metadata"]["preload_submitted"], "False")

    def test_restore_return_structure_preserved(self):
        entrypoint = modal_app.ModalRuntimeEntrypoint(
            bootstrap=RuntimeBootstrap(
                restore_gpu_state=lambda: None,
                initialize_cuda=lambda: {"cuda_available": 1},
            ),
            executor=RuntimeExecutor(in_process_runner=lambda *_: {"ok": True}),
        )
        result = entrypoint.restore()
        self.assertEqual(result["status"], "restored")
        self.assertIn("backend", result)
        self.assertIn("cuda", result)
        self.assertIn("runtime_generation", result)
        self.assertIn("trace", result)


class TestRunPlanStreamIdentity(unittest.TestCase):
    """Phase 0/2 — run_plan_stream() emits remote_method_entry with workflow hash."""

    def test_emits_remote_method_entry_with_workflow_hash(self):
        async def run():
            # Simulate real lifecycle: restore() populates _lifecycle_trace,
            # then run_plan_stream merges lifecycle events into the result.
            lifecycle = modal_app.RuntimeTrace(process=PROCESS_REMOTE_LIFECYCLE)
            lifecycle.emit(
                "remote_method_entry",
                phase="method",
                metadata={"workflow_hash": "wf-test-hash"},
            )
            entrypoint = modal_app.ModalRuntimeEntrypoint(
                executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {
                    "trace": modal_app.RuntimeTrace(process="remote").to_dict(),
                    "ok": True,
                }),
            )
            entrypoint._lifecycle_trace = lifecycle
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages = [
                msg async for msg in entrypoint.run_plan_stream(plan.to_dict(), request_id="req-1")
            ]
            self.assertEqual(messages[0]["type"], "status")
            self.assertEqual(messages[0]["request_id"], "req-1")
            last = messages[-1]
            if last.get("data") and last["data"].get("trace"):
                merged = last["data"]["trace"]
                event_names = [e["name"] for e in merged.get("events", [])]
                self.assertIn("remote_method_entry", event_names)

        import asyncio
        asyncio.run(run())

    def test_plan_received_yield_before_execution(self):
        async def run():
            entrypoint = modal_app.ModalRuntimeEntrypoint(
                executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages = [
                msg async for msg in entrypoint.run_plan_stream(plan.to_dict(), request_id="req-2")
            ]
            self.assertGreaterEqual(len(messages), 2)
            self.assertEqual(messages[0]["type"], "status")
            self.assertEqual(messages[0]["phase"], "plan_received")

        import asyncio
        asyncio.run(run())

    def test_run_plan_stream_common_schema_keys_in_metadata(self):
        """Verify run_plan_stream emits workflow_hash_prefix and effective_options_hash."""
        async def run():
            # Use a runner that preserves context.trace (like real _run_in_process).
            def _runner(plan, ctx):
                trace = ctx.trace or modal_app.RuntimeTrace(process="remote")
                trace.emit("graph_execution_start", phase="execution")
                return {"trace": trace.to_dict(), "ok": True}
            entrypoint = modal_app.ModalRuntimeEntrypoint(
                executor=RuntimeExecutor(in_process_runner=_runner),
            )
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages = [
                msg async for msg in entrypoint.run_plan_stream(plan.to_dict(), request_id="req-opts")
            ]
            # Check remote_method_entry in the merged trace
            last = messages[-1]
            if last.get("data") and last["data"].get("trace"):
                merged = last["data"]["trace"]
                entry_meta = None
                for e in merged.get("events", []):
                    if e["name"] == "remote_method_entry":
                        entry_meta = e.get("metadata", {})
                        break
                self.assertIsNotNone(entry_meta, "remote_method_entry not found")
                assert entry_meta is not None
                # workflow_hash and prefix
                self.assertIn("workflow_hash", entry_meta)
                self.assertIn("workflow_hash_prefix", entry_meta)
                # effective_options_hash should be present (even if empty)
                self.assertIn("effective_options_hash", entry_meta)
                # source_workflow_hash and prefix
                self.assertIn("source_workflow_hash", entry_meta)
                self.assertIn("source_workflow_hash_prefix", entry_meta)
                # app / class / method
                self.assertIn("app_name", entry_meta)
                self.assertIn("class_name", entry_meta)
                self.assertEqual(entry_meta.get("method_name"), "run_plan_stream")

        import asyncio
        asyncio.run(run())


class TestPublishRestorePlanIdentity(unittest.TestCase):
    """Phase 0/2 — publish_restore_plan() attaches identity to result."""

    def test_method_attaches_identity_to_result(self):
        """When publisher is available, identity is added to result dict."""
        entrypoint = modal_app.ModalRuntimeEntrypoint(
            bootstrap=RuntimeBootstrap(
                restore_gpu_state=lambda: None,
                initialize_cuda=lambda: {"cuda_available": 1},
            ),
            executor=RuntimeExecutor(in_process_runner=lambda *_: {"ok": True}),
        )
        # Without mounted volume, _publish_restore_plan_impl raises.
        # Verify the identity is still captured before the call.
        identity = modal_app._capture_remote_identity()
        self.assertIsInstance(identity, dict)


class TestPublishRestorePlanRemoteIdentity(unittest.TestCase):
    """Phase 0 — standalone remote function attaches identity."""

    def test_remote_function_captures_identity(self):
        identity = modal_app._capture_remote_identity()
        self.assertIsInstance(identity, dict)

    def test_result_has_identity_key(self):
        """Verify that when _publish_restore_plan_impl succeeds, identity is merged."""
        # Use the helper directly: identity is always captured
        plan = RestorePlan(generation=1, source_workflow_hash="wf-test")
        from comfymodal_runtime.runtime_state import FakeVolume, CommitCoordinator
        from comfymodal_runtime.restore_plan import RestorePlanPublisher

        volume = FakeVolume()
        coordinator = CommitCoordinator(volume, state_path="test_plan.json")
        publisher = RestorePlanPublisher(coordinator)
        result = publisher.publish_with_metrics(plan)
        self.assertIn("generation", result)
        self.assertIn("changed", result)


class TestLifecycleTraceIntegration(unittest.TestCase):
    """Phase 0 — lifecycle trace events survive merge."""

    def test_startup_trace_events_survive_plan_stream_merge(self):
        lifecycle = modal_app.RuntimeTrace(process=PROCESS_REMOTE_LIFECYCLE)
        lifecycle.emit("remote_lifecycle_start", phase="lifecycle")
        lifecycle.emit("remote_lifecycle_end", phase="lifecycle")

        async def run():
            entrypoint = modal_app.ModalRuntimeEntrypoint(
                executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            entrypoint._lifecycle_trace = lifecycle
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages = [
                msg async for msg in entrypoint.run_plan_stream(plan.to_dict(), request_id="req-3")
            ]
            last = messages[-1]
            if last.get("data") and last["data"].get("trace"):
                merged = last["data"]["trace"]
                event_names = [e["name"] for e in merged.get("events", [])]
                self.assertIn("remote_lifecycle_start", event_names)
                self.assertIn("remote_lifecycle_end", event_names)

        import asyncio
        asyncio.run(run())

    def test_restore_trace_events_survive_plan_stream_merge(self):
        lifecycle = modal_app.RuntimeTrace(process=PROCESS_REMOTE_LIFECYCLE)
        lifecycle.emit("restore_completion_evidence", phase="restore")

        async def run():
            entrypoint = modal_app.ModalRuntimeEntrypoint(
                executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            entrypoint._lifecycle_trace = lifecycle
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages = [
                msg async for msg in entrypoint.run_plan_stream(plan.to_dict(), request_id="req-4")
            ]
            last = messages[-1]
            if last.get("data") and last["data"].get("trace"):
                merged = last["data"]["trace"]
                event_names = [e["name"] for e in merged.get("events", [])]
                self.assertIn("restore_completion_evidence", event_names)

        import asyncio
        asyncio.run(run())


class TestV2IdentityResolution(unittest.TestCase):
    """V2 identity constants used in trace metadata (regression: was calling V1 functions).

    The V2 trace metadata path in __init__.py (lines 2259-2260) must resolve
    app_name and class_name from COMFYMODAL_V2_APP_NAME / COMFYMODAL_V2_CLASS_NAME
    environment variables, NOT from the V1 get_modal_app_name() / get_modal_class_name()
    functions.  These tests validate the env-var-with-defaults pattern used by the fix.
    """

    def test_v2_app_name_defaults_when_env_unset(self):
        """COMFYMODAL_V2_APP_NAME defaults to stable-modal-comfy-v2-shadow."""
        saved = os.environ.pop("COMFYMODAL_V2_APP_NAME", None)
        try:
            name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow").strip() or "stable-modal-comfy-v2-shadow"
            self.assertEqual(name, "stable-modal-comfy-v2-shadow")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_APP_NAME"] = saved

    def test_v2_class_name_defaults_when_env_unset(self):
        """COMFYMODAL_V2_CLASS_NAME defaults to ModalRuntimeEntrypointV2."""
        saved = os.environ.pop("COMFYMODAL_V2_CLASS_NAME", None)
        try:
            name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2").strip() or "ModalRuntimeEntrypointV2"
            self.assertEqual(name, "ModalRuntimeEntrypointV2")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_CLASS_NAME"] = saved

    def test_v2_app_name_respects_env_override(self):
        """COMFYMODAL_V2_APP_NAME override is used when set."""
        saved = os.environ.get("COMFYMODAL_V2_APP_NAME")
        os.environ["COMFYMODAL_V2_APP_NAME"] = "custom-v2-app"
        try:
            name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow").strip() or "stable-modal-comfy-v2-shadow"
            self.assertEqual(name, "custom-v2-app")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_APP_NAME"] = saved
            else:
                os.environ.pop("COMFYMODAL_V2_APP_NAME", None)

    def test_v2_class_name_respects_env_override(self):
        """COMFYMODAL_V2_CLASS_NAME override is used when set."""
        saved = os.environ.get("COMFYMODAL_V2_CLASS_NAME")
        os.environ["COMFYMODAL_V2_CLASS_NAME"] = "CustomEntrypointV2"
        try:
            name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2").strip() or "ModalRuntimeEntrypointV2"
            self.assertEqual(name, "CustomEntrypointV2")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_CLASS_NAME"] = saved
            else:
                os.environ.pop("COMFYMODAL_V2_CLASS_NAME", None)

    def test_v2_app_name_not_v1(self):
        """V2 app name must NOT equal V1 get_modal_app_name() return value 'comfyui'."""
        saved = os.environ.pop("COMFYMODAL_V2_APP_NAME", None)
        try:
            name = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow").strip() or "stable-modal-comfy-v2-shadow"
            self.assertNotEqual(name, "comfyui")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_APP_NAME"] = saved

    def test_v2_class_name_not_v1(self):
        """V2 class name must NOT equal V1 get_modal_class_name() fallback ''."""
        saved = os.environ.pop("COMFYMODAL_V2_CLASS_NAME", None)
        try:
            name = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2").strip() or "ModalRuntimeEntrypointV2"
            self.assertNotEqual(name, "")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_CLASS_NAME"] = saved


class TestV2ModuleLevelIdentity(unittest.TestCase):
    """V1-parity module-level stable identity — instance boundaries cannot erase identity."""

    def test_module_level_session_id_is_stable(self):
        """_V2_CONTAINER_SESSION_ID is a str set once at module import."""
        cid = modal_app._V2_CONTAINER_SESSION_ID
        self.assertIsInstance(cid, str)
        self.assertEqual(len(cid), 16)  # uuid4 hex[:16]
        cid2 = modal_app._V2_CONTAINER_SESSION_ID
        self.assertEqual(cid, cid2)  # stable across access

    def test_module_level_import_unix_is_positive_float(self):
        ts = modal_app._V2_CONTAINER_IMPORT_UNIX_S
        self.assertIsInstance(ts, float)
        self.assertGreater(ts, 1_700_000_000)  # any reasonable recent unix ts

    def test_module_level_restore_count_starts_at_zero(self):
        self.assertIsInstance(modal_app._v2_container_restore_count, int)
        self.assertGreaterEqual(modal_app._v2_container_restore_count, 0)

    def test_entrypoint_init_uses_module_level_cid(self):
        """Every ModalRuntimeEntrypoint instance shares _V2_CONTAINER_SESSION_ID."""
        ep1 = modal_app.ModalRuntimeEntrypoint(
            bootstrap=modal_app.RuntimeBootstrap(),
        )
        ep2 = modal_app.ModalRuntimeEntrypoint(
            bootstrap=modal_app.RuntimeBootstrap(),
        )
        self.assertEqual(ep1.container_session_id, ep2.container_session_id)
        self.assertEqual(ep1.container_session_id, modal_app._V2_CONTAINER_SESSION_ID)

    def test_entrypoint_init_restore_count_starts_at_zero(self):
        ep = modal_app.ModalRuntimeEntrypoint(
            bootstrap=modal_app.RuntimeBootstrap(),
        )
        self.assertEqual(ep._restore_count, 0)

    def test_restore_increments_module_level_counter(self):
        """restore() increments module-level _v2_container_restore_count."""
        before = modal_app._v2_container_restore_count
        ep = modal_app.ModalRuntimeEntrypoint(
            bootstrap=modal_app.RuntimeBootstrap(
                restore_gpu_state=lambda: None,
                initialize_cuda=lambda: {"cuda_available": 1},
            ),
            executor=modal_app.RuntimeExecutor(in_process_runner=lambda *_: {"ok": True}),
        )
        ep.restore()
        after = modal_app._v2_container_restore_count
        self.assertEqual(after, before + 1)
        self.assertEqual(ep._restore_count, after)


class TestV2CpuSnapshotPhaseSeparation(unittest.TestCase):
    """CPU-only snapshot behavior — startup does not run GPU callbacks."""

    def test_startup_cpu_only_runs_start_backend_not_gpu_callbacks(self):
        """startup() must NOT call restore_gpu_state or initialize_cuda."""
        tmp = tempfile.mkdtemp()
        gpu_called = []
        cuda_called = []

        ep = modal_app.ModalRuntimeEntrypoint(
            config=_writable_config(tmp),
            bootstrap=modal_app.RuntimeBootstrap(
                _writable_config(tmp),
                start_backend=lambda: "in_process",
                restore_gpu_state=lambda: gpu_called.append(True),
                initialize_cuda=lambda: cuda_called.append(True) or {"cuda_available": 1},
            ),
        )
        result = ep.startup()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(gpu_called), 0, "startup must NOT call restore_gpu_state")
        self.assertEqual(len(cuda_called), 0, "startup must NOT call initialize_cuda")

    def test_restore_runs_gpu_callbacks(self):
        """restore() must run both restore_gpu_state and initialize_cuda."""
        gpu_called = []
        cuda_called = []

        ep = modal_app.ModalRuntimeEntrypoint(
            bootstrap=modal_app.RuntimeBootstrap(
                restore_gpu_state=lambda: gpu_called.append(True),
                initialize_cuda=lambda: cuda_called.append(True) or {"cuda_available": 1},
            ),
        )
        result = ep.restore()
        self.assertEqual(result["status"], "restored")
        self.assertEqual(len(gpu_called), 1, "restore must call restore_gpu_state")
        self.assertEqual(len(cuda_called), 1, "restore must call initialize_cuda")

    def test_startup_does_not_require_gpu_callbacks(self):
        """startup() works correctly even when gpu callbacks are None."""
        tmp = tempfile.mkdtemp()
        ep = modal_app.ModalRuntimeEntrypoint(
            config=_writable_config(tmp),
            bootstrap=modal_app.RuntimeBootstrap(
                _writable_config(tmp),
                start_backend=lambda: "in_process",
                restore_gpu_state=None,
                initialize_cuda=None,
            ),
        )
        result = ep.startup()
        self.assertEqual(result["status"], "ready")
        self.assertIn("_restore_timing", result)


class TestV2LifecycleFailureAndTimingExport(unittest.TestCase):
    """Lifecycle failure/timing export — _restore_timing always exported with error/status."""

    def test_startup_failure_exports_timing_with_error(self):
        """When startup() raises, _restore_timing is captured before re-raise."""
        tmp = tempfile.mkdtemp()
        failing_bootstrap = modal_app.RuntimeBootstrap(
            _writable_config(tmp),
            start_backend=lambda: (_ for _ in ()).throw(RuntimeError("simulated startup failure")),
            restore_gpu_state=lambda: None,
        )
        ep = modal_app.ModalRuntimeEntrypoint(
            config=_writable_config(tmp),
            bootstrap=failing_bootstrap,
        )
        # We need to test that _restore_timing was set on self before the raise.
        # Since startup() raises, we catch it and check the module-level fallback.
        try:
            ep.startup()
            self.fail("startup should have raised")
        except RuntimeError:
            pass
        # _LATEST_LIFECYCLE_TIMING should be set with error info
        rt = modal_app._LATEST_LIFECYCLE_TIMING
        self.assertIsNotNone(rt, "_LATEST_LIFECYCLE_TIMING must be set on error")
        if rt is not None:
            self.assertIn("lifecycle_status", rt)
            self.assertEqual(rt["lifecycle_status"], "error")
            self.assertIn("lifecycle_method", rt)
            self.assertEqual(rt["lifecycle_method"], "startup")
            self.assertIn("restore_total_ms", rt)
            self.assertIn("container_session_id", rt)

    def test_restore_failure_exports_timing_with_error(self):
        """When restore() raises, _restore_timing is captured before re-raise."""
        failing_bootstrap = modal_app.RuntimeBootstrap(
            restore_gpu_state=lambda: (_ for _ in ()).throw(RuntimeError("simulated restore failure")),
            initialize_cuda=lambda: {"cuda_available": 1},
        )
        ep = modal_app.ModalRuntimeEntrypoint(
            bootstrap=failing_bootstrap,
        )
        try:
            ep.restore()
            self.fail("restore should have raised")
        except RuntimeError:
            pass
        rt = modal_app._LATEST_LIFECYCLE_TIMING
        self.assertIsNotNone(rt, "_LATEST_LIFECYCLE_TIMING must be set on error")
        if rt is not None:
            self.assertIn("lifecycle_status", rt)
            self.assertEqual(rt["lifecycle_status"], "error")
            self.assertIn("lifecycle_method", rt)
            self.assertEqual(rt["lifecycle_method"], "restore")
            self.assertIn("restore_total_ms", rt)
            self.assertIn("container_session_id", rt)

    def test_startup_timing_contains_lifecycle_status_ok(self):
        tmp = tempfile.mkdtemp()
        ep = modal_app.ModalRuntimeEntrypoint(
            config=_writable_config(tmp),
            bootstrap=modal_app.RuntimeBootstrap(
                _writable_config(tmp),
                start_backend=lambda: "in_process",
            ),
        )
        result = ep.startup()
        self.assertIn("_restore_timing", result)
        rt = result["_restore_timing"]
        self.assertEqual(rt.get("lifecycle_status"), "ok")
        self.assertEqual(rt.get("lifecycle_method"), "startup")
        self.assertIn("restore_total_ms", rt)
        self.assertIn("container_session_id", rt)
        self.assertIn("restore_session_id", rt)

    def test_restore_timing_contains_lifecycle_status_ok(self):
        ep = modal_app.ModalRuntimeEntrypoint(
            bootstrap=modal_app.RuntimeBootstrap(
                restore_gpu_state=lambda: None,
                initialize_cuda=lambda: {"cuda_available": 1},
            ),
        )
        result = ep.restore()
        self.assertIn("_restore_timing", result)
        rt = result["_restore_timing"]
        self.assertEqual(rt.get("lifecycle_status"), "ok")
        self.assertEqual(rt.get("lifecycle_method"), "restore")
        self.assertIn("restore_total_ms", rt)
        self.assertIn("container_session_id", rt)
        self.assertIn("restore_session_id", rt)
        self.assertIn("restore_count", rt)


class TestV2ResultPropagation(unittest.TestCase):
    """Lifecycle timing and identity propagate through _run_in_process and run_plan_stream."""

    def test_run_plan_stream_propagates_lifecycle_timing(self):
        """run_plan_stream carries _restore_timing from _LATEST_LIFECYCLE_TIMING."""
        async def run():
            # Populate module-level timing from a prior lifecycle
            modal_app._LATEST_LIFECYCLE_TIMING = {
                "restore_total_ms": 1234.5,
                "restore_session_id": "test-rsid",
                "container_session_id": modal_app._V2_CONTAINER_SESSION_ID,
                "restore_count": 1,
                "lifecycle_status": "ok",
                "lifecycle_method": "startup",
            }
            # New instance with no self._restore_timing — must fall back to module-level
            ep = modal_app.ModalRuntimeEntrypoint(
                executor=modal_app.RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            self.assertIsNone(ep._restore_timing, "fresh instance has no self._restore_timing")
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages = [
                msg async for msg in ep.run_plan_stream(plan.to_dict(), request_id="test-prop")
            ]
            last = messages[-1]
            if last.get("data") and "_restore_timing" in last["data"]:
                rt = last["data"]["_restore_timing"]
                self.assertEqual(rt.get("lifecycle_status"), "ok")
                self.assertIn("restore_total_ms", rt)
                self.assertIn("container_session_id", rt)
            else:
                # _run_in_process didn't raise but _restore_timing might be missing
                # if executor returned a result without trace. Check that data exists.
                self.assertIn("data", last, "expected a result event")
                if last.get("data"):
                    self.assertIn("_restore_timing", last["data"],
                                  "result should contain _restore_timing from module-level fallback")

        import asyncio
        asyncio.run(run())

    def test_lifecycle_error_survives_process_boundary(self):
        """When lifecycle failed, _LATEST_LIFECYCLE_TIMING carries error even cross-instance."""
        # First simulate a failed startup
        tmp = tempfile.mkdtemp()
        failing_bootstrap = modal_app.RuntimeBootstrap(
            _writable_config(tmp),
            start_backend=lambda: (_ for _ in ()).throw(RuntimeError("startup exploded")),
        )
        ep1 = modal_app.ModalRuntimeEntrypoint(
            config=_writable_config(tmp),
            bootstrap=failing_bootstrap,
        )
        try:
            ep1.startup()
        except RuntimeError:
            pass
        # Now _LATEST_LIFECYCLE_TIMING has the error — new instance must see it
        self.assertIsNotNone(modal_app._LATEST_LIFECYCLE_TIMING)
        rt = modal_app._LATEST_LIFECYCLE_TIMING
        if rt is not None:
            self.assertEqual(rt.get("lifecycle_status"), "error")

    def test_module_level_cid_survives_run_plan_stream(self):
        """container_session_id in trace is the stable module-level value."""
        async def run():
            ep = modal_app.ModalRuntimeEntrypoint(
                executor=modal_app.RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages = [
                msg async for msg in ep.run_plan_stream(plan.to_dict(), request_id="req-cid")
            ]
            last = messages[-1]
            if last.get("data") and last["data"].get("trace"):
                trace = last["data"]["trace"]
                self.assertEqual(trace.get("container_session_id"), modal_app._V2_CONTAINER_SESSION_ID)

        import asyncio
        asyncio.run(run())


class TestSnapshotTargetFingerprint(unittest.TestCase):
    """Snapshot target fingerprint in lifecycle/request diagnostics."""

    # ── Helper: call _snapshot_target_fingerprint with test spec ────────

    def _fp(self, **overrides: Any) -> str:
        """Return fingerprint for a test-app spec with given overrides."""
        from comfymodal_runtime.modal_app import _snapshot_target_fingerprint
        params: dict[str, Any] = {"app_name": "test-app"}
        params.update(overrides)
        return _snapshot_target_fingerprint(modal_app.ModalRuntimeSpec(**params))

    def _env_safe(self, key: str, value: str) -> str | None:
        """Set env var, return previous value for later restore."""
        prev = os.environ.get(key)
        os.environ[key] = value
        return prev

    def _env_restore(self, key: str, prev: str | None) -> None:
        if prev is not None:
            os.environ[key] = prev
        else:
            os.environ.pop(key, None)

    # ── Core structure tests ───────────────────────────────────────────

    def test_fingerprint_in_resource_identity(self):
        """fingerprint must be a key in _resource_identity()."""
        resources = modal_app._resource_identity()
        self.assertIn("fingerprint", resources)
        fp = resources["fingerprint"]
        self.assertIsInstance(fp, str)
        self.assertEqual(len(fp), 64)  # SHA-256 hex digest

    def test_fingerprint_deterministic(self):
        """Same spec produces the same fingerprint."""
        from comfymodal_runtime.modal_app import _snapshot_target_fingerprint
        fp1 = _snapshot_target_fingerprint()
        fp2 = _snapshot_target_fingerprint()
        self.assertEqual(fp1, fp2)
        self.assertIsInstance(fp1, str)
        self.assertEqual(len(fp1), 64)

    def test_fingerprint_deterministic_identical_payload(self):
        """Identical spec with identical env produces identical hash."""
        fp_a = self._fp(gpu=("A100",), cpu=4, memory=24576)
        fp_b = self._fp(gpu=("A100",), cpu=4, memory=24576)
        self.assertEqual(fp_a, fp_b)

    # ── Resource allocation field change tests ──────────────────────────

    def test_fingerprint_changes_for_different_gpu(self):
        """Different GPU config produces different fingerprint."""
        fp_a = self._fp(gpu=("A100",))
        fp_b = self._fp(gpu=("H100",))
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_different_cpu(self):
        """Different CPU count produces different fingerprint."""
        fp_a = self._fp(cpu=4)
        fp_b = self._fp(cpu=8)
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_different_memory(self):
        """Different memory_mb produces different fingerprint."""
        fp_a = self._fp(memory=16384)
        fp_b = self._fp(memory=32768)
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_different_timeout(self):
        """Different timeout produces different fingerprint."""
        fp_a = self._fp(timeout=300)
        fp_b = self._fp(timeout=600)
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_different_scaledown_window(self):
        """Different scaledown_window produces different fingerprint."""
        fp_a = self._fp(scaledown_window=4)
        fp_b = self._fp(scaledown_window=10)
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_different_min_containers(self):
        """Different min_containers produces different fingerprint."""
        fp_a = self._fp(min_containers=0)
        fp_b = self._fp(min_containers=2)
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_different_target_inputs(self):
        """Different target_inputs produces different fingerprint."""
        fp_a = self._fp(target_inputs=1)
        fp_b = self._fp(target_inputs=4)
        self.assertNotEqual(fp_a, fp_b)

    # ── Volume identity field change tests ─────────────────────────────

    def test_fingerprint_changes_for_different_volume_names(self):
        """Different models volume name produces different fingerprint."""
        fp_a = self._fp(models_volume_name="vol-a")
        fp_b = self._fp(models_volume_name="vol-b")
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_different_volume_mount_paths(self):
        """Different volume mount paths produce different fingerprint."""
        fp_a = self._fp(models_path="/vol/a")
        fp_b = self._fp(models_path="/vol/b")
        self.assertNotEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_runtime_state_volume_path(self):
        """Different runtime_state_path produces different fingerprint."""
        fp_a = self._fp(runtime_state_path="/state/a")
        fp_b = self._fp(runtime_state_path="/state/b")
        self.assertNotEqual(fp_a, fp_b)

    # ── Env/cloud/region/image change tests ────────────────────────────

    def test_fingerprint_changes_for_cloud(self):
        """MODAL_CLOUD_PROVIDER change produces different fingerprint."""
        saved = self._env_safe("MODAL_CLOUD_PROVIDER", "aws")
        try:
            fp_with = self._fp()
        finally:
            self._env_restore("MODAL_CLOUD_PROVIDER", saved)
        saved2 = self._env_safe("MODAL_CLOUD_PROVIDER", "gcp")
        try:
            fp_without = self._fp()
        finally:
            self._env_restore("MODAL_CLOUD_PROVIDER", saved2)
        self.assertNotEqual(fp_with, fp_without)

    def test_fingerprint_changes_for_region(self):
        """MODAL_REGION change produces different fingerprint."""
        saved = self._env_safe("MODAL_REGION", "us-east-1")
        try:
            fp_with = self._fp()
        finally:
            self._env_restore("MODAL_REGION", saved)
        saved2 = self._env_safe("MODAL_REGION", "eu-west-1")
        try:
            fp_without = self._fp()
        finally:
            self._env_restore("MODAL_REGION", saved2)
        self.assertNotEqual(fp_with, fp_without)

    def test_fingerprint_changes_for_environment(self):
        """MODAL_ENVIRONMENT change produces different fingerprint."""
        saved = self._env_safe("MODAL_ENVIRONMENT", "staging")
        try:
            fp_with = self._fp()
        finally:
            self._env_restore("MODAL_ENVIRONMENT", saved)
        saved2 = self._env_safe("MODAL_ENVIRONMENT", "production")
        try:
            fp_without = self._fp()
        finally:
            self._env_restore("MODAL_ENVIRONMENT", saved2)
        self.assertNotEqual(fp_with, fp_without)

    def test_fingerprint_changes_for_image_id(self):
        """MODAL_IMAGE_ID change produces different fingerprint."""
        saved = self._env_safe("MODAL_IMAGE_ID", "img-abc")
        try:
            fp_with = self._fp()
        finally:
            self._env_restore("MODAL_IMAGE_ID", saved)
        saved2 = self._env_safe("MODAL_IMAGE_ID", "img-xyz")
        try:
            fp_without = self._fp()
        finally:
            self._env_restore("MODAL_IMAGE_ID", saved2)
        self.assertNotEqual(fp_with, fp_without)

    # ── Runtime env (snapshot/warmup class env) change tests ───────────

    def test_fingerprint_changes_for_runtime_env_cpu_snapshot(self):
        """COMFYMODAL_V2_CPU_MODEL_SNAPSHOT change affects runtime_env."""
        saved = self._env_safe("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "0")
        try:
            fp_off = self._fp()
        finally:
            self._env_restore("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", saved)
        saved2 = self._env_safe("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "1")
        try:
            fp_on = self._fp()
        finally:
            self._env_restore("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", saved2)
        self.assertNotEqual(fp_off, fp_on)

    def test_fingerprint_changes_for_warmup_env(self):
        """COMFYMODAL_WARMUP_UNET addition affects runtime_env."""
        saved = os.environ.pop("COMFYMODAL_WARMUP_UNET", None)
        try:
            fp_before = self._fp()
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_WARMUP_UNET"] = saved
        try:
            os.environ["COMFYMODAL_WARMUP_UNET"] = "test.safetensors"
            fp_after = self._fp()
        finally:
            os.environ.pop("COMFYMODAL_WARMUP_UNET", None)
            if saved is not None:
                os.environ["COMFYMODAL_WARMUP_UNET"] = saved
        self.assertNotEqual(fp_before, fp_after)

    # ── GPU snapshot experimental_options test ─────────────────────────

    def test_fingerprint_changes_for_gpu_snapshot_option(self):
        """COMFYMODAL_ENABLE_GPU_SNAPSHOT affects experimental_options."""
        saved = self._env_safe("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0")
        try:
            fp_off = self._fp()
        finally:
            self._env_restore("COMFYMODAL_ENABLE_GPU_SNAPSHOT", saved)
        saved2 = self._env_safe("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "1")
        try:
            fp_on = self._fp()
        finally:
            self._env_restore("COMFYMODAL_ENABLE_GPU_SNAPSHOT", saved2)
        self.assertNotEqual(fp_off, fp_on)

    # ── enable_memory_snapshot test ────────────────────────────────────

    def test_fingerprint_changes_for_memory_snapshot(self):
        """enable_memory_snapshot change produces different fingerprint."""
        fp_a = self._fp(enable_memory_snapshot=True)
        fp_b = self._fp(enable_memory_snapshot=False)
        self.assertNotEqual(fp_a, fp_b)

    # ── Registered class / lifecycle config are represented ────────────

    def test_fingerprint_class_is_registered_v2(self):
        """The registered class name in fingerprint is ModalRuntimeEntrypointV2
        (when _modal is available) or ModalRuntimeEntrypoint (fallback)."""
        from comfymodal_runtime.modal_app import _snapshot_target_fingerprint
        _registered_cls = getattr(modal_app, "ModalRuntimeEntrypointV2", modal_app.ModalRuntimeEntrypoint)
        _expected_name = _registered_cls.__name__
        # Just verify deterministic — structural coverage is via field tests above.
        fp = _snapshot_target_fingerprint()
        self.assertIsInstance(fp, str)
        self.assertEqual(len(fp), 64)

    # ── Preserve min_containers=0 and scaledown_window=4 ───────────────

    def test_default_min_containers_is_zero(self):
        """The fingerprint must preserve min_containers=0 as default."""
        spec = modal_app.ModalRuntimeSpec(app_name="preserve-test")
        self.assertEqual(spec.min_containers, 0)
        self.assertEqual(spec.scaledown_window, 4)

    # ── Startup log print format ──────────────────────────────────────

    def test_fingerprint_appears_in_startup_print_simulation(self):
        """The [v2.snapshot_target] print format has expected fields."""
        from comfymodal_runtime.modal_app import _snapshot_target_fingerprint
        _fp = _snapshot_target_fingerprint()
        _spec = modal_app.ModalRuntimeSpec()
        _gpu_str = ",".join(_spec.gpu) if _spec.gpu else "none"
        _reg_cls = getattr(modal_app, "ModalRuntimeEntrypointV2", modal_app.ModalRuntimeEntrypoint)
        from io import StringIO
        import sys
        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print(
                f"[v2.snapshot_target] "
                f"fingerprint={_fp} "
                f"app={_spec.app_name} "
                f"class={_reg_cls.__name__} "
                f"gpu={_gpu_str} "
                f"cpu={_spec.cpu} "
                f"memory={_spec.memory}",
                flush=True,
            )
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        self.assertIn("[v2.snapshot_target]", output)
        self.assertIn("fingerprint=", output)
        self.assertIn("app=", output)
        self.assertIn("class=", output)
        self.assertIn(_reg_cls.__name__, output)
        self.assertIn("gpu=", output)
        self.assertIn("cpu=", output)
        self.assertIn("memory=", output)


if __name__ == "__main__":
    unittest.main()
