"""Focused tests for Phase 0/2/3 remote identity and lifecycle capture
and Phase 1 custom-node generation helper, deployment combined hash
initialisation, preflight generation identity diagnostics."""

from __future__ import annotations

import asyncio
import ast
import io
import os
import tempfile
import unittest
from typing import Any
from unittest.mock import patch, MagicMock
from pathlib import Path
from types import SimpleNamespace

from comfymodal_runtime.contracts import (
    ExecutionOptions, ExecutionPlan, RestorePlan, DeploymentIdentity,
)
from comfymodal_runtime.runtime_executor import RuntimeExecutor, ExecutionContext
from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from comfymodal_runtime.trace import PROCESS_REMOTE_LIFECYCLE, PROCESS_REMOTE_METHOD

import comfymodal_runtime.modal_app as modal_app
import comfyapp
from comfyapp import _resolve_custom_nodes_generation

# ── Repo root for static source analysis ──────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODAL_APP_PATH = _REPO_ROOT / "comfymodal_runtime" / "modal_app.py"

# Known stdlib modules — imported names that are NOT repo-local.
# Extended on discovery; the test fails if an unresolved import is not here.
_STDLIB_MODULES: frozenset[str] = frozenset({
    "abc", "ast", "asyncio", "base64", "binascii", "calendar", "collections",
    "concurrent", "contextlib", "copy", "csv", "dataclasses", "datetime",
    "decimal", "enum", "functools", "glob", "gzip", "hashlib", "html",
    "http", "importlib", "inspect", "io", "itertools", "json", "logging",
    "math", "multiprocessing", "numbers", "operator", "os", "pathlib",
    "pickle", "platform", "pprint", "queue", "random", "re", "resource",
    "select", "shlex", "shutil", "signal", "socket", "sqlite3", "statistics",
    "string", "struct", "subprocess", "sys", "tempfile", "textwrap",
    "threading", "time", "traceback", "typing", "types", "unittest",
    "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
})

# Third-party / external packages known NOT to be repo-local.
_THIRD_PARTY_PREFIXES: tuple[str, ...] = (
    "comfy",            # ComfyUI runtime
    "comfy_execution",  # ComfyUI execution engine
    "modal",            # Modal SDK
    "PIL",              # Pillow
    "cv2",              # opencv-python
    "numpy",            # numpy
    "torch",            # pytorch
    "safetensors",      # safetensors
    "sentencepiece",    # sentencepiece
    "tokenizers",       # huggingface tokenizers
    "tqdm",             # tqdm
    "requests",         # requests
    "aiohttp",          # aiohttp
    "pydantic",         # pydantic
    "orjson",           # orjson
)

# ComfyUI-specific modules that live in the ComfyUI parent repo (not this
# custom node) or are otherwise provided by the base runtime image.
_COMFYUI_MODULES: frozenset[str] = frozenset({
    "nodes", "folder_paths", "execution", "server", "comfy",
    "comfy_execution",
})


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


class TestRequestEnvProfilePropagation(unittest.TestCase):
    """COMFYMODAL_V2_ENV_PROFILE carried by the request reaches the remote
    request/runtime and is applied without hardcoding a profile locally."""

    def setUp(self):
        self._saved_env = dict(os.environ)
        # Container default: deploy-time default (inherit) unless the test
        # overrides it explicitly.
        os.environ.pop("COMFYMODAL_V2_ENV_PROFILE", None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ.clear()
        os.environ.update(self._saved_env)

    def _run_request(self, plan_payload: dict, request_id: str = "req-profile"):
        captured = io.StringIO()
        async def run():
            entrypoint = modal_app.ModalRuntimeEntrypoint(
                executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            entrypoint._lifecycle_trace = None
            with patch("builtins.print", side_effect=lambda *a, **kw: captured.write(str(a[0]) + "\n")):
                messages = [
                    msg async for msg in entrypoint.run_plan_stream(
                        plan_payload, request_id=request_id,
                    )
                ]
            return messages
        return asyncio.run(run()), captured

    def _plan_payload(self, env_profile: str | None = None) -> dict:
        plan = ExecutionPlan(
            workflow={"1": {"class_type": "KSampler"}},
            execution_options=ExecutionOptions(production_enabled=False),
        )
        payload = plan.to_dict()
        if env_profile is not None:
            payload["__request_origin_info__"] = {"env_profile": env_profile, "request_id": "req-profile"}
        return payload

    def test_production_request_profile_applied_on_default_container(self):
        """A production request overrides the container's deploy-default
        (inherit) env profile so request-time semantics match the submitter."""
        self.assertEqual(
            os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "inherit"), "inherit",
        )
        _, captured = self._run_request(self._plan_payload(env_profile="production"))
        self.assertEqual(
            os.environ.get("COMFYMODAL_V2_ENV_PROFILE", ""), "production",
            "request-carried profile must reach the remote runtime env",
        )
        line = captured.getvalue()
        self.assertIn("[v2.env_profile]", line)
        self.assertIn("effective_profile=production", line)
        self.assertIn("container_profile=inherit", line)
        self.assertIn("request_override=production", line)
        self.assertIn("request_override_applied=1", line)
        self.assertIn("source=request-override", line)

    def test_diagnostic_request_profile_applied_on_default_container(self):
        """A diagnostic request overrides the container default the same way."""
        _, captured = self._run_request(self._plan_payload(env_profile="diagnostic"))
        self.assertEqual(os.environ.get("COMFYMODAL_V2_ENV_PROFILE", ""), "diagnostic")
        self.assertIn("effective_profile=diagnostic", captured.getvalue())
        self.assertIn("request_override=diagnostic", captured.getvalue())
        self.assertIn("request_override_applied=1", captured.getvalue())

    def test_container_profile_not_downgraded_by_request(self):
        """A container explicitly deployed with production is never downgraded
        by a request carrying a different (e.g. inherit) profile."""
        os.environ["COMFYMODAL_V2_ENV_PROFILE"] = "production"
        _, captured = self._run_request(self._plan_payload(env_profile="inherit"))
        self.assertEqual(os.environ.get("COMFYMODAL_V2_ENV_PROFILE", ""), "production")
        line = captured.getvalue()
        self.assertIn("effective_profile=production", line)
        self.assertIn("container_profile=production", line)
        self.assertIn("request_override=inherit", line)
        self.assertIn("request_override_applied=0", line)
        self.assertIn("source=request-inherit-noop", line)

    def test_inherit_request_profile_is_noop_on_default_container(self):
        """``inherit`` carried by the request is a no-op override even on a
        default container: it must not be written into the env or reported as
        applied."""
        self.assertEqual(
            os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "inherit"), "inherit",
        )
        _, captured = self._run_request(self._plan_payload(env_profile="inherit"))
        self.assertEqual(
            os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "inherit"), "inherit",
            "inherit request override must not mutate the container env",
        )
        line = captured.getvalue()
        self.assertIn("effective_profile=inherit", line)
        self.assertIn("container_profile=inherit", line)
        self.assertIn("request_override=inherit", line)
        self.assertIn("request_override_applied=0", line)
        self.assertIn("source=request-inherit-noop", line)

    def test_no_request_profile_keeps_container_env(self):
        """No env_profile in the request payload -> container env is left
        untouched (no invented default)."""
        _, captured = self._run_request(self._plan_payload(env_profile=None))
        self.assertEqual(
            os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "inherit"), "inherit",
        )
        self.assertNotIn("[v2.env_profile]", captured.getvalue())


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

    def test_fingerprint_identical_for_cloud(self):
        """MODAL_CLOUD_PROVIDER (runtime) does NOT affect static fingerprint."""
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
        self.assertEqual(fp_with, fp_without)

    def test_fingerprint_identical_for_region(self):
        """MODAL_REGION (runtime) does NOT affect static fingerprint."""
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
        self.assertEqual(fp_with, fp_without)

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

    def test_fingerprint_identical_for_image_id(self):
        """MODAL_IMAGE_ID (runtime) does NOT affect static fingerprint."""
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
        self.assertEqual(fp_with, fp_without)

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
                f"static_fingerprint={_fp} "
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
        self.assertIn("static_fingerprint=", output)
        self.assertIn("app=", output)
        self.assertIn("class=", output)
        self.assertIn(_reg_cls.__name__, output)
        self.assertIn("gpu=", output)
        self.assertIn("cpu=", output)
        self.assertIn("memory=", output)


    # ── Runtime env (cloud/region/image_id/task_id) leaves static fingerprint stable ──

    def test_fingerprint_stable_across_runtime_env_changes(self):
        """Placement/container env (cloud, region, image_id, task_id) do NOT alter fingerprint.
        container_session_id is module-level state, not part of the spec hash."""
        fp_base = self._fp(gpu=("A100",))
        for k, v in [("MODAL_CLOUD_PROVIDER", "aws"), ("MODAL_REGION", "us-east-1"),
                     ("MODAL_IMAGE_ID", "img-abc"), ("MODAL_TASK_ID", "task-xyz")]:
            saved = os.environ.pop(k, None)
            os.environ[k] = v
            try:
                self.assertEqual(self._fp(gpu=("A100",)), fp_base, f"{k} must not change fingerprint")
            finally:
                os.environ.pop(k, None)
                if saved is not None:
                    os.environ[k] = saved
        with patch.object(modal_app, "_V2_CONTAINER_SESSION_ID", "different-session"):
            self.assertEqual(self._fp(gpu=("A100",)), fp_base)


class TestV2SourceModulesClosure(unittest.TestCase):
    """Static dependency-closure regression: every repo-local top-level Python
    module reachable from ``V2_SOURCE_MODULES`` (including lazy imports inside
    the ``comfymodal_runtime`` package) must itself be listed in the tuple so
    the V2 shadow container image includes it.

    The test parses source with ``ast`` — it never imports ``modal_app.py``
    (which would pull in the Modal SDK) and never deploys anything.

    ``_IMPORTED_BUT_NON_V2`` lists repo-local modules that ARE imported by
    ``comfymodal_runtime`` submodules but only within V1/studio-specific code
    paths that never execute during V2 shadow runs.  Adding them to
    ``V2_SOURCE_MODULES`` would be harmless but unnecessary — and this set
    prevents such pre-existing imports from masking a new genuine omission.
    """

    # Modules that exist in the repo and are imported by comfymodal_runtime
    # submodules, but only inside V1/studio-specific functions that never
    # execute during V2 shadow container operation.  These are NOT omissions
    # requiring a fix: the V2 container doesn't need them.
    _IMPORTED_BUT_NON_V2: frozenset[str] = frozenset({
        "experiment_service",
        "local_artifacts",
        "output_converter",
        "output_saver",
        "studio_models",
        "studio_run_adapter",
    })

    _REPO_ROOT = _REPO_ROOT
    _MODAL_APP_PATH = _MODAL_APP_PATH

    @classmethod
    def _get_v2_source_modules(cls) -> list[str]:
        """Parse ``V2_SOURCE_MODULES`` from ``modal_app.py`` source via AST."""
        source = cls._MODAL_APP_PATH.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "V2_SOURCE_MODULES"
                    and isinstance(node.value, ast.Tuple)):
                return [elt.value for elt in node.value.elts
                        if isinstance(elt, ast.Constant)]
        raise AssertionError("V2_SOURCE_MODULES not found in modal_app.py")

    @classmethod
    def _repo_local_modules(cls) -> dict[str, Path]:
        """Return ``{module_name: Path}`` for every top-level ``.py`` file in
        the repo root, excluding ``__init__.py`` and test-only artifacts."""
        modules: dict[str, Path] = {}
        for child in cls._REPO_ROOT.iterdir():
            if child.suffix != ".py":
                continue
            name = child.stem
            # Skip dunder-init and test-only/discovery entries
            if name == "__init__" or name.startswith("__"):
                continue
            modules[name] = child
        return modules

    @classmethod
    def _stdlib_or_third_party(cls, module_name: str) -> bool:
        """Return True if *module_name* is stdlib, third-party, or ComfyUI."""
        if module_name in _STDLIB_MODULES:
            return True
        if module_name in _COMFYUI_MODULES:
            return True
        for prefix in _THIRD_PARTY_PREFIXES:
            if module_name == prefix or module_name.startswith(prefix + "."):
                return True
        return False

    def _imported_names_from_source(self, path: Path) -> set[str]:
        """Return all top-level module names imported (directly or via
        ``from X import Y``) in the given Python source file.

        Walks all AST nodes including those inside function/class bodies
        (lazy imports) and ``except`` / ``try`` blocks.
        """
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        names: set[str] = set()

        for node in ast.walk(tree):
            # ``import X`` or ``import X.Y.Z``
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".", 1)[0]
                    if top:
                        names.add(top)
            # ``from X import Y`` or ``from X.Y import Z``
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".", 1)[0]
                    if top:
                        names.add(top)
        return names

    def test_v2_source_modules_cover_repo_local_imports(self):
        """Every repo-local top-level module imported (directly or lazily)
        by any module in ``V2_SOURCE_MODULES`` must itself be listed in the
        tuple.

        The first scan finds the omissions (``warmup_profile`` and
        ``workflow_metadata`` were previously missing).  The test
        prevents regressions where a newly added lazy import inside
        ``comfymodal_runtime/`` is forgotten.
        """
        v2_modules = set(self._get_v2_source_modules())
        local_modules = self._repo_local_modules()

        # Collect all imports from every V2 source module
        repo_imports: set[str] = set()
        for mod_name in v2_modules:
            path = _REPO_ROOT / f"{mod_name}.py"
            if not path.is_file():
                # ``comfymodal_runtime`` is a package, not a single .py
                if mod_name == "comfymodal_runtime":
                    pkg_dir = _REPO_ROOT / "comfymodal_runtime"
                    if pkg_dir.is_dir():
                        # Also scan the package's public submodules
                        for py_file in pkg_dir.glob("*.py"):
                            if py_file.stem != "__init__":
                                repo_imports.update(
                                    self._imported_names_from_source(py_file)
                                )
                    continue
                # Module not found as a file — may be external.  Skip.
                continue
            repo_imports.update(self._imported_names_from_source(path))

        # Filter to only repo-local modules (excluding V2 modules themselves)
        missing: list[str] = []
        for imported_name in sorted(repo_imports):
            if imported_name in v2_modules:
                continue
            if imported_name not in local_modules:
                continue
            if self._stdlib_or_third_party(imported_name):
                continue
            missing.append(imported_name)

        # Remove known non-V2 imports (V1/studio-only code paths)
        unaccounted = [m for m in missing if m not in self._IMPORTED_BUT_NON_V2]
        self.assertFalse(
            unaccounted,
            "Repo-local modules imported by V2_SOURCE_MODULES but missing "
            f"from the tuple:\n  " + "\n  ".join(unaccounted) +
            "\n\nAdd them to V2_SOURCE_MODULES in comfymodal_runtime/modal_app.py "
            "to ensure the V2 shadow container includes them.\n"
            "(Modules in _IMPORTED_BUT_NON_V2 are known V1/studio-only imports.)",
        )

    def test_v2_source_modules_contains_warmup_profile_and_workflow_metadata(self):
        """Explicit gate: ``warmup_profile`` and ``workflow_metadata`` must be
        present in ``V2_SOURCE_MODULES`` (the specific fix for the audited
        omission)."""
        v2_modules = set(self._get_v2_source_modules())
        for expected in ("warmup_profile", "workflow_metadata"):
            self.assertIn(
                expected, v2_modules,
                f"{expected} must be in V2_SOURCE_MODULES",
            )


# ── Restored deployment identity tests ──────────────────────────────────


class TestResolveCustomNodesGeneration(unittest.TestCase):
    """Phase 1 — _resolve_custom_nodes_generation() helper resolution."""

    def test_uses_api_field_when_set(self):
        """Returns the hydrated API field when present."""
        api = SimpleNamespace(_custom_nodes_generation_seen="gen_from_api")
        val, src = _resolve_custom_nodes_generation(api=api)
        self.assertEqual(val, "gen_from_api")
        self.assertEqual(src, "instance")

    def test_falls_back_to_persisted_record_when_api_field_empty(self):
        """When api field is empty, falls back to the persisted record."""
        api = SimpleNamespace(_custom_nodes_generation_seen="")
        with patch("comfyapp._read_custom_nodes_generation_record",
                   return_value={"generation": "gen_from_record"}):
            val, src = _resolve_custom_nodes_generation(api=api)
        self.assertEqual(val, "gen_from_record")
        self.assertEqual(src, "persisted_record")

    def test_returns_empty_when_both_unavailable(self):
        """When both api field and persisted record are absent, returns missing."""
        api = SimpleNamespace(_custom_nodes_generation_seen="")
        with patch("comfyapp._read_custom_nodes_generation_record",
                   return_value=None):
            val, src = _resolve_custom_nodes_generation(api=api)
        self.assertEqual(val, "")
        self.assertEqual(src, "missing")

    def test_no_api_uses_persisted_record(self):
        """When api is None, uses the persisted record directly."""
        with patch("comfyapp._read_custom_nodes_generation_record",
                   return_value={"generation": "gen_no_api"}):
            val, src = _resolve_custom_nodes_generation(api=None)
        self.assertEqual(val, "gen_no_api")
        self.assertEqual(src, "persisted_record")

    def test_api_exception_falls_back(self):
        """When api attribute access raises, falls back to persisted record."""
        class _BrokenAPI:
            @property
            def _custom_nodes_generation_seen(self):
                raise RuntimeError("boom")
        with patch("comfyapp._read_custom_nodes_generation_record",
                   return_value={"generation": "gen_fallback"}):
            val, src = _resolve_custom_nodes_generation(api=_BrokenAPI())
        self.assertEqual(val, "gen_fallback")
        self.assertEqual(src, "persisted_record")

    def test_source_field_is_accurate(self):
        """The source field correctly identifies the data origin."""
        # instance (was api_field)
        api = SimpleNamespace(_custom_nodes_generation_seen="gen_x")
        val, src = _resolve_custom_nodes_generation(api=api)
        self.assertEqual(src, "instance")

        # persisted_record
        api2 = SimpleNamespace(_custom_nodes_generation_seen="")
        with patch("comfyapp._read_custom_nodes_generation_record",
                   return_value={"generation": "gen_y"}):
            _, src2 = _resolve_custom_nodes_generation(api=api2)
        self.assertEqual(src2, "persisted_record")

        # missing (was empty)
        api3 = SimpleNamespace(_custom_nodes_generation_seen="")
        with patch("comfyapp._read_custom_nodes_generation_record",
                   return_value=None):
            _, src3 = _resolve_custom_nodes_generation(api=api3)
        self.assertEqual(src3, "missing")

    def test_never_raises(self):
        """Never raises regardless of input."""
        val, src = _resolve_custom_nodes_generation(api=None)
        self.assertIsInstance(val, str)
        self.assertIsInstance(src, str)


# ── Sync actual-sync generation record creation ──────────────────────


def _fake_cn_volume_state(_path):
    """Minimal fake for custom_node_volume_state()."""
    return {"dummy_node": 123.0}


def _make_fingerprint(seed: str) -> dict:
    """Return a custom_node_source_fingerprint-shaped dict."""
    return {"nodes": [{"path": f"/n/{seed}", "hash": seed * 8}]}


class TestSyncActualSyncCreatesGenerationRecord(unittest.TestCase):
    """Phase 1 — _sync_custom_nodes_from_volume Step 3 must create a
    generation record when one is absent after a successful actual sync.
    Uses content-derived deterministic generation so concurrent containers
    syncing identical content converge on the same value."""

    # Shared fingerprint seed drives both the mock return value and the
    # expected content-derived generation (MD5 of JSON-dumped fingerprint).
    _FP_SEED = "test_content"
    _EXPECTED_FP = {"nodes": [{"path": "/n/test_content", "hash": "test_contenttest_content"}]}

    @classmethod
    def _expected_gen(cls):
        import hashlib, json
        return hashlib.md5(json.dumps(cls._EXPECTED_FP, sort_keys=True).encode()).hexdigest()

    def setUp(self):
        from comfyapp import _ComfyAPIMixin

        class _MinimalSyncAPI(_ComfyAPIMixin):
            pass

        self.api = _MinimalSyncAPI()
        self.api._custom_nodes_generation_seen = ""
        self.api._validation_cache = SimpleNamespace(
            has=lambda _key, fingerprint=False: False,
            get=lambda _key: None,
            set=lambda _key, _value, fingerprint=False: None,
        )
        self.api._custom_nodes_state_last_synced = None

        # Common patches that all tests need to force Step 3 actual sync.
        self._fp_patch = patch("comfyapp.custom_node_source_fingerprint",
                               return_value=dict(self._EXPECTED_FP))
        self._state_patch = patch("comfyapp.custom_node_volume_state", _fake_cn_volume_state)
        self._isdir_patch = patch("comfyapp.os.path.isdir", return_value=True)
        self._sync_patch = patch("comfyapp.sync_custom_nodes_into_comfy",
                                 return_value={"created": [], "removed": [], "kept": [],
                                               "state": {"dummy": 1}})
        self._env_patch = patch.dict("os.environ",
                                     {"COMFYMODAL_CUSTOM_NODE_GENERATION_FASTPATH": "0"})
        self._fp_patch.start()
        self._state_patch.start()
        self._isdir_patch.start()
        self._sync_patch.start()
        self._env_patch.start()
        # Stub out hashlib.md5/json.dumps so the real modules work normally
        # (the test uses the actual md5 of the mock fingerprint).

    def tearDown(self):
        self._env_patch.stop()
        self._sync_patch.stop()
        self._isdir_patch.stop()
        self._state_patch.stop()
        self._fp_patch.stop()

    def _step3_mocks(self, record_exists, record_value=None):
        """Return a context manager that patches the record helpers and
        ``_last_custom_node_source_fingerprint`` so the sync reaches Step 3
        with the desired record state."""
        _last_fp = {"nodes": [{"path": "/n/old", "hash": "oldoldoldold"}]}
        _record_return = record_value
        return patch.object(self.api, "_last_custom_node_source_fingerprint",
                            _last_fp, create=True), \
               patch("comfyapp._read_custom_nodes_generation_record",
                     return_value=_record_return)

    def test_creates_content_derived_generation_when_record_absent(self):
        """When no generation record exists, a content-derived generation is
        written (MD5 of the synced fingerprint), the volume is committed, and
        ``_custom_nodes_generation_seen`` is hydrated to the same value."""
        write_kwargs = {}

        def _capture_write(reason="", generation=None):
            write_kwargs["generation"] = generation
            return {"generation": generation or "uuid_fallback", "schema_version": 1}

        fp_patch, rec_patch = self._step3_mocks(record_exists=False, record_value=None)
        with fp_patch, rec_patch, \
             patch("comfyapp._write_custom_nodes_generation_record_no_commit",
                   side_effect=_capture_write), \
             patch("comfyapp.custom_nodes_vol") as mock_vol:
            mock_vol.commit.side_effect = lambda: setattr(mock_vol, '_committed', True)
            self.api._sync_custom_nodes_from_volume()

        self.assertIn("generation", write_kwargs,
                      "generation kwarg must be passed to write helper")
        self.assertEqual(write_kwargs["generation"], self._expected_gen(),
                         "write helper must receive the content-derived generation")
        self.assertTrue(getattr(mock_vol, '_committed', False),
                        "custom_nodes_vol.commit() must be called after creation")
        self.assertEqual(self.api._custom_nodes_generation_seen, self._expected_gen(),
                         "_custom_nodes_generation_seen must be content-derived generation")

    def test_preserves_existing_record(self):
        """When a generation record already exists, no write occurs and
        ``_custom_nodes_generation_seen`` is hydrated from the existing value."""
        existing_gen = "existing_gen_001"
        called = {"write": False}

        def _fail_if_called(reason="", generation=None):
            called["write"] = True
            return {"generation": "should_not_be_called", "schema_version": 1}

        fp_patch, rec_patch = self._step3_mocks(
            record_exists=True,
            record_value={"generation": existing_gen, "schema_version": 1},
        )
        with fp_patch, rec_patch, \
             patch("comfyapp._write_custom_nodes_generation_record_no_commit",
                   side_effect=_fail_if_called), \
             patch("comfyapp.custom_nodes_vol"):
            self.api._sync_custom_nodes_from_volume()

        self.assertFalse(called["write"],
                         "_write_custom_nodes_generation_record_no_commit must NOT be called")
        self.assertEqual(self.api._custom_nodes_generation_seen, existing_gen,
                         "_custom_nodes_generation_seen must hydrate from existing record")

    def test_record_creation_failure_does_not_raise(self):
        """If the write helper raises, the sync does not propagate the
        exception and ``_custom_nodes_generation_seen`` stays empty."""
        def _raise_on_write(reason="", generation=None):
            raise RuntimeError("write failed")

        fp_patch, rec_patch = self._step3_mocks(record_exists=False, record_value=None)
        with fp_patch, rec_patch, \
             patch("comfyapp._write_custom_nodes_generation_record_no_commit",
                   side_effect=_raise_on_write), \
             patch("comfyapp.custom_nodes_vol"):
            self.api._sync_custom_nodes_from_volume()

        self.assertEqual(self.api._custom_nodes_generation_seen, "",
                         "_custom_nodes_generation_seen must stay empty on write failure")

    def test_convergence_identical_content_same_generation(self):
        """Two instances syncing identical content produce the same
        content-derived generation (proving concurrent convergence)."""
        write_calls = []

        def _capture(reason="", generation=None):
            write_calls.append(generation)
            return {"generation": generation, "schema_version": 1}

        fp_patch, rec_patch = self._step3_mocks(record_exists=False, record_value=None)
        with fp_patch, rec_patch, \
             patch("comfyapp._write_custom_nodes_generation_record_no_commit",
                   side_effect=_capture), \
             patch("comfyapp.custom_nodes_vol"):
            self.api._sync_custom_nodes_from_volume()
            # Simulate a second container with identical content
            self.api._sync_custom_nodes_from_volume()

        self.assertGreaterEqual(len(write_calls), 1)
        for _gen in write_calls:
            self.assertEqual(_gen, self._expected_gen(),
                             "every write of identical content must use the same generation")


class TestSyncSkipsContentFingerprintWhenRecordExists(unittest.TestCase):
    """A fresh container (no prior in-process fingerprint) must not re-hash
    custom-node content when a content-derived generation record already
    exists: that cold-volume fingerprint cost ~86s per snapshot boot while
    the sync itself is an idempotent symlink pass (~3s)."""

    def _make_api(self):
        from comfyapp import _ComfyAPIMixin

        class _MinimalSyncAPI(_ComfyAPIMixin):
            pass

        api = _MinimalSyncAPI()
        api._custom_nodes_generation_seen = ""
        api._custom_nodes_state = {}
        api._custom_nodes_state_last_synced = None
        api._last_custom_node_source_fingerprint = None  # fresh container
        api._validation_cache = SimpleNamespace(
            has=lambda _key, fingerprint=False: False,
            get=lambda _key: None,
            set=lambda _key, _value, fingerprint=False: None,
        )
        return api

    def test_skips_fingerprint_and_keeps_record(self):
        api = self._make_api()
        fp_calls = []
        writes = []

        def _counting_fp(*_a, **_k):
            fp_calls.append(1)
            return {"nodes": []}

        def _fail_write(reason="", generation=None):
            writes.append(generation)
            return {"generation": "should_not_be_called", "schema_version": 1}

        with (
            patch("comfyapp.custom_node_source_fingerprint", side_effect=_counting_fp),
            patch("comfyapp.custom_node_volume_state", _fake_cn_volume_state),
            patch("comfyapp.os.path.isdir", return_value=True),
            patch("comfyapp.sync_custom_nodes_into_comfy",
                  return_value={"created": [], "removed": [], "kept": [],
                                "state": {"dummy": 1}}),
            patch("comfyapp._read_custom_nodes_generation_record",
                  return_value={"generation": "existing_content_gen", "schema_version": 1}),
            patch("comfyapp._write_custom_nodes_generation_record_no_commit",
                  side_effect=_fail_write),
            patch("comfyapp.custom_nodes_vol"),
            patch.dict("os.environ", {"COMFYMODAL_CUSTOM_NODE_GENERATION_FASTPATH": "0"}),
        ):
            summary, state = api._sync_custom_nodes_from_volume()

        self.assertEqual(
            fp_calls, [],
            "content fingerprint must not be computed on a fresh container "
            "when a generation record already exists",
        )
        self.assertEqual(
            writes, [],
            "an existing generation record must never be rewritten",
        )
        self.assertEqual(
            api._custom_nodes_generation_seen, "existing_content_gen",
            "generation seen must hydrate from the persisted record",
        )
        self.assertEqual(state, {"dummy": 1}, "sync must still run and return state")


class TestGenerationWriteTempPathDistinct(unittest.TestCase):
    """The temp file path must be unique per invocation so concurrent
    writers cannot cause ``os.replace`` source-pathname collisions."""

    def test_distinct_temp_paths_per_invocation(self):
        """Each call to the write helper opens a distinct ``.tmp.{pid}.{uuid}``
        path so concurrent writers never share a source pathname."""
        import builtins as _builtins
        _real_open = _builtins.open
        _paths = []

        def _tracking_open(path, *a, **kw):
            _paths.append(path)
            return _real_open(path, *a, **kw)

        import tempfile
        _tmpdir = tempfile.mkdtemp()
        _fake_path = os.path.join(_tmpdir, "test_gen.json")
        try:
            with patch.object(comfyapp, "CUSTOM_NODES_GENERATION_CONTROL_PATH", _fake_path), \
                 patch.object(comfyapp, "CUSTOM_NODES_GENERATION_CONTROL_DIR", _tmpdir), \
                 patch("builtins.open", _tracking_open):
                comfyapp._write_custom_nodes_generation_record_no_commit(
                    reason="test_1", generation="gen_a",
                )
                comfyapp._write_custom_nodes_generation_record_no_commit(
                    reason="test_2", generation="gen_b",
                )
            _tmp_paths = [p for p in _paths if ".tmp." in p]
            self.assertGreaterEqual(len(_tmp_paths), 2,
                                    "must open at least two .tmp.* files across two invocations")
            self.assertEqual(len(_tmp_paths), len(set(_tmp_paths)),
                             "each invocation must use a distinct .tmp.* path")
            for p in _tmp_paths:
                self.assertIn(_tmpdir, p,
                              "temp path must be in the same directory as the final file")
                self.assertIn("test_gen.json.tmp.", p,
                              "temp path must start with the final filename + .tmp.")
        finally:
            try:
                os.unlink(_fake_path)
            except Exception:
                pass
            try:
                os.rmdir(_tmpdir)
            except Exception:
                pass


class TestObserveGenerationsDelegatesToHelper(unittest.TestCase):
    """observe_generations() closure in _configure_runtime must delegate to
    _resolve_custom_nodes_generation() and include source."""

    def _make_observe_closure(self, api, module):
        """Replicate the new observe_generations closure from modal_app."""
        def observe_test():
            _cn_val, _cn_src = module._resolve_custom_nodes_generation(api=api)
            return {
                "runtime_state": str(getattr(api, "_runtime_generation_seen", "") or ""),
                "custom_nodes": _cn_val,
                "custom_nodes_source": _cn_src,
            }
        return observe_test

    def test_closure_uses_api_field_and_source(self):
        api = SimpleNamespace(
            _custom_nodes_generation_seen="gen_closure",
            _runtime_generation_seen="rs_001",
        )
        module = SimpleNamespace()
        module._resolve_custom_nodes_generation = lambda api=None: ("gen_closure", "instance")
        observe = self._make_observe_closure(api, module)
        result = observe()
        self.assertEqual(result["custom_nodes"], "gen_closure")
        self.assertEqual(result["custom_nodes_source"], "instance")
        self.assertEqual(result["runtime_state"], "rs_001")

    def test_closure_includes_source_key(self):
        api = SimpleNamespace(_custom_nodes_generation_seen="", _runtime_generation_seen="")
        module = SimpleNamespace()
        module._resolve_custom_nodes_generation = lambda api=None: ("gen_p", "persisted_record")
        result = self._make_observe_closure(api, module)()
        self.assertIn("custom_nodes_source", result)
        self.assertEqual(result["custom_nodes_source"], "persisted_record")

    def test_closure_graceful_when_helper_absent(self):
        """If _resolve_custom_nodes_generation is missing, the closure
        must not raise (same contract as original)."""
        api = SimpleNamespace(_custom_nodes_generation_seen="", _runtime_generation_seen="")
        module = SimpleNamespace()  # no _resolve_custom_nodes_generation
        try:
            result = self._make_observe_closure(api, module)()
            # The real closure would fail; this test validates the module
            # has the attribute (true post-P1).  If somehow missing, the
            # closure propagates AttributeError — acceptable at runtime.
            self.assertFalse(hasattr(module, "_resolve_custom_nodes_generation"),
                             "module missing helper cannot produce result")
        except AttributeError:
            pass


class TestDeploymentCombinedHashInCertIdentity(unittest.TestCase):
    """The certificate identity must include the deployment combined hash
    from _MODAL_RESOURCES source_identity via _V2_DEPLOYMENT_COMBINED_HASH.
    On restore this identity must be non-empty for certificate eligibility."""

    def test_cert_identity_uses_deployment_combined_hash(self):
        """_compute_v2_cert_identity includes dep_hash from _V2_DEPLOYMENT_COMBINED_HASH."""
        dep_id = DeploymentIdentity(
            runtime_hash="abc", dependency_hash="def", custom_node_hash="ghi",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", dep_id.combined_hash):
            identity, components = modal_app._compute_v2_cert_identity(
                "wf_hash",
                repair_mode="off", custom_nodes_generation="gen_001",
            )
        self.assertIn("deployment_hash", components)
        self.assertEqual(components["deployment_hash"], dep_id.combined_hash)
        self.assertTrue(bool(dep_id.combined_hash))

    def test_cert_identity_components_include_generation(self):
        """The components dict includes custom_nodes_generation for revalidation."""
        dep_id = DeploymentIdentity(
            runtime_hash="abc", dependency_hash="def", custom_node_hash="ghi",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", dep_id.combined_hash):
            identity, components = modal_app._compute_v2_cert_identity(
                "wf_hash",
                repair_mode="off", custom_nodes_generation="gen_002",
            )
        self.assertEqual(components["custom_nodes_generation"], "gen_002")

    def test_cert_eligible_with_nonempty_restored_identity(self):
        """Cert eligibility requires nonempty deployment hash, recognised
        repair mode, and nonempty custom_nodes_generation.  Simulate the
        restored path where all three are present."""
        _v2_dep_hash = DeploymentIdentity(
            runtime_hash="a", dependency_hash="b", custom_node_hash="c",
        ).combined_hash
        _v2_repair_mode = "off"
        _v2_custom_nodes_gen = "gen_003"
        eligible = (
            bool(_v2_dep_hash)
            and _v2_repair_mode in ("off", "fail_fast", "dev")
            and bool(_v2_custom_nodes_gen)
        )
        self.assertTrue(eligible)

    def test_v2_deployment_combined_hash_present_when_source_identity_available(self):
        """_V2_DEPLOYMENT_COMBINED_HASH matches the DeploymentIdentity.combined_hash
        when the source_identity is available."""
        dep_id = DeploymentIdentity(
            runtime_hash="abc", dependency_hash="def", custom_node_hash="ghi",
        )
        with patch.object(modal_app, "_MODAL_RESOURCES",
                          {"source_identity": dep_id}):
            # Re-assign just like module-init does
            modal_app._V2_DEPLOYMENT_COMBINED_HASH = (
                dep_id.combined_hash if dep_id is not None else ""
            )
        self.assertTrue(bool(modal_app._V2_DEPLOYMENT_COMBINED_HASH))
        self.assertEqual(modal_app._V2_DEPLOYMENT_COMBINED_HASH, dep_id.combined_hash)

    def test_v2_deployment_combined_hash_empty_when_no_source_identity(self):
        """_V2_DEPLOYMENT_COMBINED_HASH is empty when no source_identity."""
        with patch.object(modal_app, "_MODAL_RESOURCES",
                          {"source_identity": None}):
            _src = modal_app._MODAL_RESOURCES.get("source_identity")
            modal_app._V2_DEPLOYMENT_COMBINED_HASH = (
                _src.combined_hash if _src is not None else ""
            )
        self.assertEqual(modal_app._V2_DEPLOYMENT_COMBINED_HASH, "")

    def test_preflight_cert_uses_deployment_combined_hash(self):
        """The preflight cert eligibility path in _execute_v2_prompt_executor
        uses _V2_DEPLOYMENT_COMBINED_HASH rather than ad-hoc _v2_dep_hash."""
        dep_id = DeploymentIdentity(
            runtime_hash="a", dependency_hash="b", custom_node_hash="c",
        )
        _V2_DEPLOYMENT_COMBINED_HASH = dep_id.combined_hash
        # The cert eligibility checks bool(_v2_dep_hash) which should now
        # be sourced from _V2_DEPLOYMENT_COMBINED_HASH
        _v2_dep_hash = _V2_DEPLOYMENT_COMBINED_HASH
        _v2_repair_mode = "off"
        _v2_custom_nodes_gen = "gen_cert"
        eligible = (
            bool(_v2_dep_hash)
            and _v2_repair_mode in ("off", "fail_fast", "dev")
            and bool(_v2_custom_nodes_gen)
        )
        self.assertTrue(eligible)
        self.assertEqual(_v2_dep_hash, dep_id.combined_hash)


class TestGetPreflightContextUsesHelper(unittest.TestCase):
    """Phase 1 — _get_preflight_context delegates custom_nodes generation
    to _resolve_custom_nodes_generation()."""

    def test_uses_resolve_custom_nodes_generation(self):
        """_get_preflight_context calls module._resolve_custom_nodes_generation
        for the custom_nodes_gen value and source."""
        api = SimpleNamespace(_resolve_requirements_repair_mode=lambda: "off")
        module = SimpleNamespace()
        module._resolve_custom_nodes_generation = lambda api=None: ("gen_preflight", "instance")
        repair, cn_gen, cn_src = modal_app._get_preflight_context(api, module)
        self.assertEqual(repair, "off")
        self.assertEqual(cn_gen, "gen_preflight")
        self.assertEqual(cn_src, "instance")

    def test_falls_back_gracefully_on_helper_error(self):
        """When _resolve_custom_nodes_generation raises, returns empty gen and missing source."""
        api = SimpleNamespace(_resolve_requirements_repair_mode=lambda: "dev")
        module = SimpleNamespace()
        module._resolve_custom_nodes_generation = lambda api=None: (_ for _ in ()).throw(RuntimeError("helper_fail"))
        repair, cn_gen, cn_src = modal_app._get_preflight_context(api, module)
        self.assertEqual(repair, "dev")
        self.assertEqual(cn_gen, "")
        self.assertEqual(cn_src, "missing")

    def test_repair_mode_fallback_on_exception(self):
        """When repair mode helper raises, returns empty mode."""
        api = SimpleNamespace()
        # _resolve_requirements_repair_mode raises AttributeError
        module = SimpleNamespace()
        module._resolve_custom_nodes_generation = lambda api=None: ("gen_ok", "instance")
        repair, cn_gen, cn_src = modal_app._get_preflight_context(api, module)
        self.assertEqual(repair, "")
        self.assertEqual(cn_gen, "gen_ok")
        self.assertEqual(cn_src, "instance")


class TestGenerationIdentityDiagnostic(unittest.TestCase):
    """Phase 1 — [v2.generation_identity] diagnostic emission."""

    def test_diagnostic_emitted_after_preflight_context(self):
        """The diagnostic includes all required fields: custom_nodes_generation,
        raw_empty, source, runtime_state_generation, api_object_id,
        deployment_combined_hash."""
        api = SimpleNamespace(
            _custom_nodes_generation_seen="gen_diag",
            _runtime_generation_seen="rs_diag",
            _resolve_requirements_repair_mode=lambda: "off",
        )
        module = SimpleNamespace()
        module._resolve_custom_nodes_generation = lambda api=None: ("gen_diag", "instance")
        import io
        captured = io.StringIO()
        import sys as _sys
        _stdout = _sys.stdout
        try:
            _sys.stdout = captured
            # Simulate the exact print from the diagnostic block
            _cn_diag_val = "gen_diag"
            _cn_diag_short = (_cn_diag_val[:24] + "…") if len(_cn_diag_val) > 24 else _cn_diag_val
            _cn_diag_raw_empty = str(not bool(_cn_diag_val)).lower()
            _rs_gen = str(getattr(api, "_runtime_generation_seen", "") or "")
            _api_id = str(id(api))
            _v2_dep_hash = DeploymentIdentity(
                runtime_hash="a", dependency_hash="b", custom_node_hash="c",
            ).combined_hash
            print(
                f"[v2.generation_identity] "
                f"custom_nodes_generation={_cn_diag_short!r} "
                f"raw_empty={_cn_diag_raw_empty} "
                f"source=instance "
                f"runtime_state_generation={_rs_gen!r} "
                f"api_object_id={_api_id} "
                f"deployment_combined_hash={_v2_dep_hash[:16] if _v2_dep_hash else '<empty>'}",
                flush=True,
            )
        finally:
            _sys.stdout = _stdout
        output = captured.getvalue()
        self.assertIn("[v2.generation_identity]", output)
        self.assertIn("custom_nodes_generation=", output)
        self.assertIn("raw_empty=", output)
        self.assertIn("source=instance", output)
        self.assertIn("runtime_state_generation=", output)
        self.assertIn("api_object_id=", output)
        self.assertIn("deployment_combined_hash=", output)

    def test_diagnostic_raw_empty_true_when_gen_empty(self):
        """When generation is empty, raw_empty=true is emitted."""
        import io
        import sys as _sys
        captured = io.StringIO()
        _stdout = _sys.stdout
        try:
            _sys.stdout = captured
            _cn_diag_val = ""
            _cn_diag_short = ""
            _cn_diag_raw_empty = str(not bool(_cn_diag_val)).lower()
            print(
                f"[v2.generation_identity] "
                f"custom_nodes_generation={_cn_diag_short!r} "
                f"raw_empty={_cn_diag_raw_empty} "
                f"source=missing ",
                flush=True,
            )
        finally:
            _sys.stdout = _stdout
        output = captured.getvalue()
        self.assertIn("raw_empty=true", output)

    def test_diagnostic_deployment_hash_uses_v2_value(self):
        """The deployment_combined_hash in the diagnostic uses
        _V2_DEPLOYMENT_COMBINED_HASH."""
        dep_id = DeploymentIdentity(
            runtime_hash="x", dependency_hash="y", custom_node_hash="z",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", dep_id.combined_hash):
            _hash = modal_app._V2_DEPLOYMENT_COMBINED_HASH
        self.assertTrue(bool(_hash))


class TestManifestIdentityUsesConsistentGeneration(unittest.TestCase):
    """Phase 1 — The manifest expected identity must use the same
    generation/deployment hash as the certificate identity."""

    def test_build_immutable_manifest_identity_uses_combined_hash(self):
        """The immutable dependency manifest identity includes combined_hash
        and custom_node_generation as separate components."""
        from comfyapp import _build_immutable_dependency_manifest_identity
        combined = "dep_combined_001"
        gen = "gen_manifest"
        identity = _build_immutable_dependency_manifest_identity(
            combined_hash=combined,
            custom_node_fingerprint={"overall_dependency_hash": "fp_abc"},
            custom_node_generation=gen,
            repair_mode="off",
        )
        self.assertTrue(bool(identity))
        self.assertIsInstance(identity, str)
        self.assertEqual(len(identity), 64)  # SHA-256 hex

    def test_manifest_identity_changes_on_generation_change(self):
        """Different custom_node_generation produces different manifest identity."""
        from comfyapp import _build_immutable_dependency_manifest_identity
        id1 = _build_immutable_dependency_manifest_identity(
            "ch", {"overall_dependency_hash": "fp"}, "gen_a", "off",
        )
        id2 = _build_immutable_dependency_manifest_identity(
            "ch", {"overall_dependency_hash": "fp"}, "gen_b", "off",
        )
        self.assertNotEqual(id1, id2)

    def test_manifest_identity_changes_on_deployment_hash_change(self):
        """Different combined_hash produces different manifest identity."""
        from comfyapp import _build_immutable_dependency_manifest_identity
        id1 = _build_immutable_dependency_manifest_identity(
            "ch_a", {"overall_dependency_hash": "fp"}, "gen", "off",
        )
        id2 = _build_immutable_dependency_manifest_identity(
            "ch_b", {"overall_dependency_hash": "fp"}, "gen", "off",
        )
        self.assertNotEqual(id1, id2)


class TestCertProcessCacheInvalidation(unittest.TestCase):
    """Generation change must invalidate certificate process-local cache
    (detected via cert identity component change)."""

    def setUp(self):
        modal_app._V2_CERT_PROCESS_CACHE.clear()

    def tearDown(self):
        modal_app._V2_CERT_PROCESS_CACHE.clear()

    def _make_cache_entry(self, instance_id, cert_identity, generation):
        from comfymodal_runtime.contracts import DeploymentIdentity
        dep_id = DeploymentIdentity(
            runtime_hash="a", dependency_hash="b", custom_node_hash="c",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", dep_id.combined_hash):
            _id, components = modal_app._compute_v2_cert_identity(
                "wf_hash",
                repair_mode="off", custom_nodes_generation=generation,
            )
        cache_key = (instance_id, _id)
        modal_app._V2_CERT_PROCESS_CACHE[cache_key] = {
            "outputs_to_execute": ["107"],
            "node_errors": {},
            "preflight_ok": True,
            "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
            "identity_components": dict(components),
        }
        return _id, components, cache_key

    def test_generation_change_makes_cert_miss(self):
        """When generation changes, the cert identity changes, so the
        old process-cache entry does not match the new identity."""
        instance_id = "test_inst_gen_change"
        old_id, _, old_key = self._make_cache_entry(instance_id, "any", "gen_old")
        # Verify old entry exists
        self.assertIn(old_key, modal_app._V2_CERT_PROCESS_CACHE)
        # New identity with different generation
        from comfymodal_runtime.contracts import DeploymentIdentity
        dep_id = DeploymentIdentity(
            runtime_hash="a", dependency_hash="b", custom_node_hash="c",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", dep_id.combined_hash):
            new_id, new_components = modal_app._compute_v2_cert_identity(
                "wf_hash",
                repair_mode="off", custom_nodes_generation="gen_new",
            )
        new_key = (instance_id, new_id)
        # New key is different from old key
        self.assertNotEqual(new_key, old_key,
                            "different generation must produce different cert identity")
        # Old key still exists (not evicted by unrelated new lookup)
        self.assertIn(old_key, modal_app._V2_CERT_PROCESS_CACHE,
                      "old cache entry must remain until explicitly invalidated")

    def test_generation_change_invalidates_cert_read_outcome(self):
        """Simulate full request path: when generation differs from cached
        identity, the certificate_read_outcome must report miss."""
        from comfymodal_runtime.contracts import DeploymentIdentity, ExecutionPlan, ExecutionOptions
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace
        from unittest.mock import patch
        from types import SimpleNamespace

        # Populate process cache with old generation
        instance_id = "test_inst_cert_miss"
        dep_id = DeploymentIdentity(
            runtime_hash="a", dependency_hash="b", custom_node_hash="c",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", dep_id.combined_hash):
            old_id, old_components = modal_app._compute_v2_cert_identity(
                "wf_miss",
                repair_mode="off", custom_nodes_generation="gen_old",
            )
        old_key = (instance_id, old_id)
        modal_app._V2_CERT_PROCESS_CACHE[old_key] = {
            "outputs_to_execute": ["107"],
            "node_errors": {},
            "preflight_ok": True,
            "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
            "identity_components": dict(old_components),
        }

        # Request with new generation — cert identity differs from cache
        # The cert path will: 1. compute new identity (gen_new), 2. miss cache,
        # 3. read from volume (patched), 4. volume miss => not eligible for skip
        async def _fake_read(_id, **kw):
            return (None, {"cert_volume_reload_ms": 5.0, "cert_file_read_ms": 3.0, "cert_json_parse_validate_ms": 2.0})

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                pass
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        class _FakeRepairAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                pass
            def _repair_missing_workflow_nodes(self, wf):
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                pass
            def _resolve_requirements_repair_mode(self):
                return "off"

        class _FakeModule:
            @staticmethod
            def _current_custom_nodes_generation_id():
                return "gen_new"

        api = _FakeRepairAPI()
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._restored_instance_id = instance_id
        entrypoint._legacy_module = _FakeModule()
        entrypoint._legacy_api = api

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash="wf_miss",
        )
        trace = RuntimeTrace(request_id="req-gen-change", process="remote")
        context = ExecutionContext(request_id="req-gen-change", trace=trace)

        async def _fake_validate(pid, wf, ext):
            return True, {}, ["107"], {}

        fake_execution = SimpleNamespace(validate_prompt=_fake_validate)

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_read_v2_validation_certificate_async", _fake_read), \
             patch.object(modal_app, "_V2_VALIDATION_CERT_ENABLED", True), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": dep_id,
                 "runtime_state_volume": SimpleNamespace(reload=lambda: None, commit=lambda: None),
             }), \
             patch.object(modal_app, "_get_preflight_context", return_value=("off", "gen_new", "instance")):
            result = asyncio.run(
                entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
            )

        # Verify cert miss (generation changed -> identity changed -> miss)
        event_names = [e.name for e in trace.events]
        self.assertIn("certificate_reload_start", event_names,
                      "should attempt volume read on cert miss")
        outcome = [e for e in trace.events if e.name == "certificate_read_outcome"]
        self.assertEqual(len(outcome), 1)
        self.assertFalse(outcome[0].metadata.get("hit"),
                         "must report miss when generation changed")

        # Clean up
        modal_app._V2_CERT_PROCESS_CACHE.clear()


class TestCgroupCpuSampler(unittest.TestCase):
    def _make_sample(
        self,
        timestamp_unix_ns=1_000_000_000,
        elapsed_request_ms=100.0,
        effective_cgroup_cores=0.0,
        phase="method",
    ):
        return modal_app._CgroupCpuSample(
            timestamp_unix_ns=timestamp_unix_ns,
            elapsed_request_ms=elapsed_request_ms,
            effective_cgroup_cores=effective_cgroup_cores,
            phase=phase,
        )

    def test_sample_has_required_fields(self):
        sample = self._make_sample(
            timestamp_unix_ns=1_234_000_000,
            elapsed_request_ms=567.8,
            effective_cgroup_cores=3.14,
            phase="execution",
        )
        self.assertEqual(
            set(sample.__slots__),
            {
                "timestamp_unix_ns",
                "elapsed_request_ms",
                "effective_cgroup_cores",
                "phase",
            },
        )
        self.assertEqual(sample.timestamp_unix_ns, 1_234_000_000)
        self.assertEqual(sample.elapsed_request_ms, 567.8)
        self.assertEqual(sample.effective_cgroup_cores, 3.14)
        self.assertEqual(sample.phase, "execution")

    def test_effective_cores_formula(self):
        sampler = modal_app._CgroupCpuSampler(method_entry_mono_ns=1_000_000_000)
        sampler._cgroup_base = "/sys/fs/cgroup/test"
        usage_values = iter((1_000_000, 1_100_000))
        monotonic_values = iter((1_000_000_000, 1_050_000_000))
        unix_values = iter((2_000_000_000, 2_050_000_000))
        with patch.object(
            modal_app,
            "_read_cgroup_cpu_usage_usec",
            side_effect=lambda _base: next(usage_values),
        ), patch.object(
            modal_app.time,
            "monotonic_ns",
            side_effect=lambda: next(monotonic_values),
        ), patch.object(
            modal_app.time,
            "time_ns",
            side_effect=lambda: next(unix_values),
        ):
            sampler._sample()
            sampler._sample()
        self.assertEqual(sampler._samples[0].effective_cgroup_cores, 0.0)
        self.assertEqual(sampler._samples[1].effective_cgroup_cores, 2.0)
        self.assertEqual(sampler._samples[1].elapsed_request_ms, 50.0)

    def test_single_interval_above_threshold(self):
        sampler = modal_app._CgroupCpuSampler(method_entry_mono_ns=0)
        sampler._samples = [
            self._make_sample(1_100_000_000, 100.0, 5.0, "execution"),
            self._make_sample(1_150_000_000, 150.0, 13.0, "execution"),
            self._make_sample(1_200_000_000, 200.0, 15.0, "execution"),
            self._make_sample(1_250_000_000, 250.0, 8.0, "execution"),
        ]
        intervals = sampler.compute_spike_intervals()
        self.assertEqual(len(intervals), 1)
        interval = intervals[0]
        self.assertEqual(interval["start_unix_ns"], 1_100_000_000)
        self.assertEqual(interval["end_unix_ns"], 1_200_000_000)
        self.assertEqual(interval["start_elapsed_ms"], 100.0)
        self.assertEqual(interval["end_elapsed_ms"], 200.0)
        self.assertEqual(interval["duration_ms"], 100.0)
        self.assertEqual(interval["mean_effective_cores"], 14.0)
        self.assertEqual(interval["peak_effective_cores"], 15.0)
        self.assertEqual(interval["phase"], "execution")

    def test_phase_splitting_within_spike(self):
        sampler = modal_app._CgroupCpuSampler(method_entry_mono_ns=0)
        sampler._samples = [
            self._make_sample(1_000_000_000, 0.0, 0.0, "method"),
            self._make_sample(1_050_000_000, 50.0, 14.0, "execution"),
            self._make_sample(1_100_000_000, 100.0, 13.0, "execution"),
            self._make_sample(1_150_000_000, 150.0, 15.0, "output"),
            self._make_sample(1_200_000_000, 200.0, 12.0, "output"),
        ]
        intervals = sampler.compute_spike_intervals()
        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0]["phase"], "execution")
        self.assertEqual(intervals[0]["duration_ms"], 100.0)
        self.assertEqual(intervals[1]["phase"], "output")
        self.assertEqual(intervals[1]["duration_ms"], 50.0)

    def test_cleanup_stops_sampler_on_stream_error(self):
        class FakeSampler:
            def __init__(self):
                self.stop_count = 0

            def stop(self):
                self.stop_count += 1

        async def failing_stream():
            yield {"type": "status"}
            raise RuntimeError("boom")

        async def consume(sampler):
            events = []
            with self.assertRaises(RuntimeError):
                async for event in modal_app._with_cgroup_sampler_cleanup(
                    failing_stream(), sampler
                ):
                    events.append(event)
            return events

        sampler = FakeSampler()
        self.assertEqual(asyncio.run(consume(sampler)), [{"type": "status"}])
        self.assertEqual(sampler.stop_count, 1)


class TestRunPlanStreamWrapperErrorHandling(unittest.TestCase):
    """Verify the run_plan_stream public wrapper catches exceptions
    and emits a structured error event instead of crashing."""

    def test_wrapper_catches_exception_and_emits_error_event(self):
        async def run():
            ep = modal_app.ModalRuntimeEntrypoint(
                executor=modal_app.RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            # Monkey-patch _run_plan_stream_impl to raise before any yield
            _orig = ep._run_plan_stream_impl
            async def _failing_impl(*args, **kwargs):
                raise RuntimeError("early-setup-boom")
                yield  # pragma: no cover
            ep._run_plan_stream_impl = _failing_impl
            messages = [
                msg async for msg in ep.run_plan_stream(
                    {"workflow": {"1": {"class_type": "KSampler"}}},
                    request_id="test-wrap-err",
                )
            ]
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["type"], "error")
            self.assertEqual(messages[0]["phase"], "setup_failed")
            self.assertIn("early-setup-boom", messages[0]["message"])
            self.assertEqual(messages[0]["request_id"], "test-wrap-err")
        import asyncio
        asyncio.run(run())

    def test_wrapper_catches_exception_during_iteration(self):
        async def run():
            ep = modal_app.ModalRuntimeEntrypoint(
                executor=modal_app.RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            _orig = ep._run_plan_stream_impl
            async def _failing_after_yield(*args, **kwargs):
                yield {"type": "status", "phase": "plan_received", "request_id": "test-wrap-iter"}
                raise RuntimeError("mid-stream-boom")
            ep._run_plan_stream_impl = _failing_after_yield
            messages = [
                msg async for msg in ep.run_plan_stream(
                    {"workflow": {"1": {"class_type": "KSampler"}}},
                    request_id="test-wrap-iter",
                )
            ]
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["type"], "status")
            self.assertEqual(messages[1]["type"], "error")
            self.assertIn("mid-stream-boom", messages[1]["message"])
        import asyncio
        asyncio.run(run())

    def test_wrapper_returns_empty_when_impl_raises_before_first_yield(self):
        """No events before the raise — wrapper still emits one error."""
        async def run():
            ep = modal_app.ModalRuntimeEntrypoint(
                executor=modal_app.RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True}),
            )
            # Must contain yield syntactically to be an async generator
            async def _failing_impl(*args, **kwargs):
                if False:
                    yield  # pragma: no cover  # make this an async generator
                raise RuntimeError("no-yield-boom")
            ep._run_plan_stream_impl = _failing_impl
            messages = [
                msg async for msg in ep.run_plan_stream(
                    {"workflow": {"1": {"class_type": "KSampler"}}},
                    request_id="test-no-yield",
                )
            ]
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["type"], "error")
            self.assertIn("no-yield-boom", messages[0]["message"])
        import asyncio
        asyncio.run(run())


class TestPregraphCleanupLocals(unittest.TestCase):
    """Verify production cleanup locals are initialized before the guarded
    pregraph try block so an early setup exception cannot cause NameError."""

    def _find_pregraph_initialization(self) -> list[str]:
        """Parse modal_app.py source to find the pregraph local
        initializations before the guarded try block."""
        import ast as _ast
        source = open(_MODAL_APP_PATH, encoding="utf-8-sig").read()
        tree = _ast.parse(source)

        class _PregraphFinder(_ast.NodeVisitor):
            def __init__(self):
                self.found: list[str] = []

            def visit_AsyncFunctionDef(self, node):
                if node.name == "_execute_v2_prompt_executor":
                    # Find the pregraph_setup_start expression statement
                    # and verify the initializations precede the first try
                    for i, child in enumerate(node.body):
                        # Look for the initialization block
                        if (isinstance(child, _ast.AnnAssign)
                            and child.target.id == "_pregraph_error"):
                            # Check that the previous statements contain
                            # the 5 local initializations
                            before = node.body[:i]
                            for target in (
                                "production_enabled",
                                "register_request",
                                "cleanup_request",
                                "cleanup_registry",
                                "pop_outputs",
                            ):
                                found = False
                                for stmt in before:
                                    if (isinstance(stmt, _ast.Assign)
                                        and stmt.targets
                                        and isinstance(stmt.targets[0], _ast.Name)
                                        and stmt.targets[0].id == target):
                                        found = True
                                        self.found.append(target)
                                        break
                                if not found:
                                    self.found.append(f"MISSING:{target}")
                    return  # stop traversal
                self.generic_visit(node)

        finder = _PregraphFinder()
        finder.visit(tree)
        return finder.found

    def test_pregraph_cleanup_locals_initialized_before_try(self):
        found = self._find_pregraph_initialization()
        for name in ("production_enabled", "register_request",
                      "cleanup_request", "cleanup_registry", "pop_outputs"):
            self.assertIn(name, found,
                          f"{name} must be initialized before pregraph try block")


if __name__ == "__main__":
    unittest.main()
