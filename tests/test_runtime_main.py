"""Focused tests for bootstrap, preload, executor, and transport primitives."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from types import SimpleNamespace
import unittest
from pathlib import Path
from typing import Any

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, ModelRestoreKey, PrefillKey
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint, ModalRuntimeSpec, build_modal_resources
from comfymodal_runtime.model_preload import ModelPreloadCoordinator
from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap, ensure_models_symlink
from comfymodal_runtime.runtime_executor import ExecutionContext, RuntimeExecutor
from comfymodal_runtime.trace import RuntimeTrace


class TestBootstrap(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "directory symlink requires elevated Windows privileges")
    def test_model_symlink_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "comfy"
            models = Path(tmp) / "models"
            root.mkdir()
            models.mkdir()
            first = ensure_models_symlink(str(models), str(root))
            second = ensure_models_symlink(str(models), str(root))
            self.assertEqual(first, second)
            self.assertTrue((root / "models").is_symlink())

    @unittest.skipIf(os.name == "nt", "directory symlink requires elevated Windows privileges")
    def test_existing_models_directory_is_replaced_by_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "comfy"
            models = Path(tmp) / "models"
            root.mkdir()
            models.mkdir()
            (root / "models").mkdir()
            (root / "models" / "baked-stub").write_text("stub", encoding="utf-8")

            ensure_models_symlink(str(models), str(root))

            self.assertTrue((root / "models").is_symlink())
            self.assertEqual((root / "models").resolve(), models.resolve())

    def test_lifecycle_order_and_no_startup_install(self):
        calls: list[str] = []
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            reload_models=lambda: calls.append("models"),
            reload_runtime_state=lambda: calls.append("state"),
            sync_custom_nodes=lambda: calls.append("nodes"),
            start_backend=lambda: calls.append("backend") or "in_process",
            restore_gpu_state=lambda: calls.append("gpu"),
            initialize_cuda=lambda: calls.append("cuda") or {"cuda_available": 1},
            apply_sage_policy=lambda: calls.append("sage"),
        )
        trace = RuntimeTrace(request_id="r")
        bootstrap.startup(trace=trace)
        bootstrap.restore(trace=trace)
        self.assertEqual(calls[:4], ["models", "state", "nodes", "backend"])
        self.assertEqual(calls[4:], ["gpu", "cuda", "sage", "state", "models", "nodes"])
        self.assertEqual(bootstrap.state.backend, "in_process")

    def test_backend_callback_controls_snapshot_cuda_policy(self):
        observed: list[str | None] = []
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            start_backend=lambda: observed.append(os.environ.get("CUDA_VISIBLE_DEVICES")) or "in_process",
        )

        before = os.environ.get("CUDA_VISIBLE_DEVICES")
        bootstrap.startup(snapshot=True)

        self.assertEqual(observed, [before])

    def test_install_requirements_callback_fires_after_nodes_in_startup(self):
        calls: list[str] = []
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(
                comfyui_root=tempfile.gettempdir(),
                models_path=str(model_path),
                install_requirements_on_startup=True,
            ),
            reload_models=lambda: calls.append("models"),
            reload_runtime_state=lambda: calls.append("state"),
            sync_custom_nodes=lambda: calls.append("nodes"),
            install_requirements=lambda: calls.append("install_reqs"),
            start_backend=lambda: calls.append("backend") or "in_process",
        )
        trace = RuntimeTrace(request_id="r")
        bootstrap.startup(trace=trace)
        self.assertIn("install_reqs", calls)
        self.assertEqual(calls[:4], ["models", "state", "nodes", "install_reqs"])
        self.assertEqual(calls[4:], ["backend"])

    def test_install_requirements_not_called_when_flag_off(self):
        calls: list[str] = []
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(
                comfyui_root=tempfile.gettempdir(),
                models_path=str(model_path),
                install_requirements_on_startup=False,
            ),
            sync_custom_nodes=lambda: calls.append("nodes"),
            install_requirements=lambda: calls.append("install_reqs"),
            start_backend=lambda: calls.append("backend") or "in_process",
        )
        bootstrap.startup()
        self.assertNotIn("install_reqs", calls)

    def test_startup_emits_per_stage_trace_events(self):
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        trace = RuntimeTrace(request_id="test-startup-stages")
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            reload_models=lambda: None,
            reload_runtime_state=lambda: None,
            sync_custom_nodes=lambda: None,
            start_backend=lambda: "in_process",
        )
        bootstrap.startup(trace=trace)
        names = {e.name for e in trace.events}
        for expected in (
            "snapshot_restore_start",
            "models_symlink_start",
            "models_symlink_end",
            "manager_offline_start",
            "manager_offline_end",
            "reload_models_start",
            "reload_models_end",
            "reload_runtime_state_start",
            "reload_runtime_state_end",
            "sync_custom_nodes_start",
            "sync_custom_nodes_end",
            "comfyui_path_setup_start",
            "comfyui_path_setup_end",
            "backend_startup_start",
            "backend_startup_end",
            "observe_generations_start",
            "observe_generations_end",
            "snapshot_restore_end",
        ):
            with self.subTest(event=expected):
                self.assertIn(expected, names)

    def test_startup_captures_identity_metadata(self):
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        trace = RuntimeTrace(request_id="test-identity")
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            start_backend=lambda: "in_process",
        )
        os.environ["MODAL_TASK_ID"] = "task-999"
        os.environ["MODAL_IMAGE_ID"] = "img-abc"
        os.environ["MODAL_CLOUD_PROVIDER"] = "aws"
        os.environ["MODAL_REGION"] = "us-east-1"
        try:
            bootstrap.startup(trace=trace)
            self.assertEqual(bootstrap.state.modal_task_id, "task-999")
            self.assertEqual(bootstrap.state.modal_image_id, "img-abc")
            self.assertEqual(bootstrap.state.modal_cloud_provider, "aws")
            self.assertEqual(bootstrap.state.modal_region, "us-east-1")
            # Verify metadata emitted in snapshot_restore_start
            start_events = [e for e in trace.events if e.name == "snapshot_restore_start"]
            self.assertGreaterEqual(len(start_events), 1)
            meta = start_events[0].metadata
            self.assertEqual(meta.get("modal_task_id"), "task-999")
            self.assertEqual(meta.get("snapshot_enabled"), "True")
        finally:
            for key in ("MODAL_TASK_ID", "MODAL_IMAGE_ID", "MODAL_CLOUD_PROVIDER", "MODAL_REGION"):
                os.environ.pop(key, None)

    def test_restore_emits_per_stage_trace_events(self):
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        trace = RuntimeTrace(request_id="test-restore-stages")
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            restore_gpu_state=lambda: None,
            initialize_cuda=lambda: {"device": "cuda:0", "cuda_available": "1"},
            apply_sage_policy=lambda: True,
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
        )
        bootstrap.restore(trace=trace)
        names = {e.name for e in trace.events}
        for expected in (
            "snapshot_restore_start",
            "restore_gpu_state_start",
            "restore_gpu_state_end",
            "cuda_init_start",
            "cuda_init_end",
            "sage_policy_start",
            "sage_policy_end",
            "reload_runtime_state_start",
            "reload_runtime_state_end",
            "reload_models_start",
            "reload_models_end",
            "sync_custom_nodes_start",
            "sync_custom_nodes_end",
            "observe_generations_start",
            "observe_generations_end",
            "snapshot_restore_end",
        ):
            with self.subTest(event=expected):
                self.assertIn(expected, names)

    def test_restore_captures_sage_policy_result(self):
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        trace = RuntimeTrace(request_id="test-sage")
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            restore_gpu_state=lambda: None,
            initialize_cuda=lambda: {"device": "cuda:0"},
            apply_sage_policy=lambda: True,
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
        )
        bootstrap.restore(trace=trace)
        self.assertEqual(bootstrap.state.sage_mode, "baked_cuda")
        self.assertEqual(bootstrap.state.sage_reason, "patched")
        # Verify metadata in sage_policy_end event
        sage_ends = [e for e in trace.events if e.name == "sage_policy_end"]
        self.assertGreaterEqual(len(sage_ends), 1)
        self.assertEqual(sage_ends[0].metadata.get("sage_mode"), "baked_cuda")
        self.assertEqual(sage_ends[0].metadata.get("sage_reason"), "patched")

    def test_restore_captures_sage_policy_false_result(self):
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            restore_gpu_state=lambda: None,
            initialize_cuda=lambda: {"device": "cuda:0"},
            apply_sage_policy=lambda: False,
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
            observe_generations=lambda: {"runtime_state": "gen-5", "custom_nodes": "gen-3"},
        )
        state = bootstrap.restore()
        self.assertEqual(state.sage_mode, "triton_fallback")
        self.assertEqual(state.sage_reason, "not-patched-or-not-found")

    def test_restore_captures_stage_durations_in_state(self):
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        trace = RuntimeTrace(request_id="test-durations")
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            restore_gpu_state=lambda: None,
            initialize_cuda=lambda: {"device": "cuda:0"},
            apply_sage_policy=lambda: True,
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
            observe_generations=lambda: {"runtime_state": "gen-5", "custom_nodes": "gen-3"},
        )
        state = bootstrap.restore(trace=trace)
        self.assertIn("snapshot_restore", state.stage_durations)
        self.assertIn("restore_gpu_state", state.stage_durations)
        self.assertIn("cuda_init", state.stage_durations)
        self.assertIn("sage_policy", state.stage_durations)
        self.assertIn("reload_runtime_state", state.stage_durations)
        self.assertIn("reload_models", state.stage_durations)
        self.assertIn("sync_custom_nodes", state.stage_durations)
        for name, duration_ms in state.stage_durations.items():
            self.assertIsInstance(duration_ms, (int, float))
            self.assertGreaterEqual(duration_ms, 0)

    def test_startup_captures_stage_durations_in_state(self):
        model_path = Path(tempfile.gettempdir()) / "models"
        model_path.mkdir(exist_ok=True)
        trace = RuntimeTrace(request_id="test-startup-durations")
        bootstrap = RuntimeBootstrap(
            BootstrapConfig(comfyui_root=tempfile.gettempdir(), models_path=str(model_path)),
            reload_models=lambda: None,
            reload_runtime_state=lambda: None,
            sync_custom_nodes=lambda: None,
            start_backend=lambda: "in_process",
            observe_generations=lambda: {"runtime_state": "gen-5", "custom_nodes": "gen-3"},
        )
        state = bootstrap.startup(trace=trace)
        self.assertIn("snapshot_restore", state.stage_durations)
        self.assertIn("models_symlink", state.stage_durations)
        self.assertIn("reload_models", state.stage_durations)
        self.assertIn("backend_startup", state.stage_durations)
        self.assertIn("observe_generations", state.stage_durations)
        for name, duration_ms in state.stage_durations.items():
            self.assertIsInstance(duration_ms, (int, float))
            self.assertGreaterEqual(duration_ms, 0)


class TestModelPreload(unittest.TestCase):
    def test_two_lanes_and_exact_prefill_are_measured(self):
        events: list[str] = []

        def load_unet(key):
            events.append("unet")
            time.sleep(0.01)
            return "UNET"

        def load_clip(key):
            events.append("clip")
            time.sleep(0.01)
            return "CLIP"

        def prefill(key, clip):
            events.append(f"prefill:{clip}")
            return "CONDITIONING"

        coordinator = ModelPreloadCoordinator(
            unet_loader=load_unet,
            clip_loader=load_clip,
            prefill_loader=prefill,
        )
        try:
            model_key = ModelRestoreKey(unet_identity="u")
            prep = coordinator.prepare(model_key, PrefillKey(model_key=model_key, prompt_bundle_hash="p"))
            self.assertEqual(coordinator.wait_unet(prep), "UNET")
            self.assertEqual(coordinator.wait_prefill(prep), "CONDITIONING")
            self.assertIn("clip", events)
            self.assertGreaterEqual(coordinator.diagnostics(prep)["unet_completed_at"], prep.diagnostics.unet_started_at)
        finally:
            coordinator.close()


class TestRuntimeExecutor(unittest.TestCase):
    def test_explicit_backend_and_diagnostics(self):
        async def run():
            plan = ExecutionPlan(execution_options=ExecutionOptions(requested_backend="in_process"))
            executor = RuntimeExecutor(in_process_runner=lambda plan, ctx: {"images": []})
            result = await executor.execute(plan)
            self.assertEqual(result["backend"]["selected"], "in_process")

        asyncio.run(run())

    def test_fallback_is_explicit(self):
        async def run():
            plan = ExecutionPlan(execution_options=ExecutionOptions(requested_backend="in_process"))

            def fail(plan, context):
                raise RuntimeError("boom")

            executor = RuntimeExecutor(
                in_process_runner=fail,
                subprocess_runner=lambda plan, ctx: {"ok": True},
                allow_compatibility_fallback=True,
            )
            result = await executor.execute(plan)
            self.assertEqual(result["backend"]["selected"], "subprocess")
            self.assertTrue(result["backend"]["fallback_attempted"])

        asyncio.run(run())


class TestModalTransport(unittest.TestCase):
    def test_transport_preserves_plan_payload(self):
        observed: dict = {}

        async def stream(**kwargs):
            observed.update(kwargs)
            yield {"type": "result", "data": {"ok": True}}

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            messages = [message async for message in transport.run_plan_stream(plan)]
            self.assertEqual(messages[-1]["data"], {"ok": True})
            self.assertEqual(observed["workflow"], plan.to_dict()["workflow"])
            self.assertFalse(observed["modal_options"]["production"]["enabled"])

        asyncio.run(run())

    def test_modal_resources_preserve_cold_start_settings(self):
        resources = build_modal_resources(spec=ModalRuntimeSpec())
        self.assertEqual(resources["spec"].min_containers, 0)
        self.assertEqual(resources["spec"].scaledown_window, 4)

    def test_v2_modal_class_is_registered_separately(self):
        import comfymodal_runtime.modal_app as modal_app

        if modal_app.ModalRuntimeEntrypointRemote is None:
            self.skipTest("Modal/comfyapp deployment resources unavailable")
        self.assertIsNotNone(modal_app.ModalRuntimeEntrypointRemote)
        self.assertEqual(modal_app.APP_NAME, "stable-modal-comfy-v2-shadow")
        self.assertIn("comfymodal_runtime", modal_app.V2_SOURCE_MODULES)
        self.assertIn("comfyapp", modal_app.V2_SOURCE_MODULES)

    def test_entrypoint_stream_delegates_typed_plan(self):
        async def run():
            executor = RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True})
            entrypoint = ModalRuntimeEntrypoint(executor=executor)
            messages = [
                message async for message in entrypoint.run_plan_stream(
                    ExecutionPlan(workflow={"1": {}}).to_dict()
                )
            ]
            self.assertEqual(messages[-1]["data"]["ok"], True)

        asyncio.run(run())

    def test_entrypoint_stream_merges_lifecycle_trace_into_result(self):
        async def run():
            lifecycle = RuntimeTrace(process="remote")
            lifecycle.emit("snapshot_restore_end", phase="restore")
            executor = RuntimeExecutor(
                in_process_runner=lambda plan, ctx: {
                    "trace": RuntimeTrace(process="remote").to_dict(),
                    "ok": True,
                }
            )
            entrypoint = ModalRuntimeEntrypoint(executor=executor)
            entrypoint._lifecycle_trace = lifecycle
            messages = [
                message async for message in entrypoint.run_plan_stream(
                    ExecutionPlan(workflow={"1": {}}).to_dict()
                )
            ]
            names = {event["name"] for event in messages[-1]["data"]["trace"]["events"]}
            self.assertIn("snapshot_restore_end", names)

        asyncio.run(run())

    def test_default_v2_transport_targets_registered_class(self):
        observed: dict[str, Any] = {}

        async def remote_stream(payload, **kwargs):
            observed["payload"] = payload
            observed["kwargs"] = kwargs
            yield {"type": "result", "data": {"ok": True}}

        # The current transport invokes publish_restore_plan via the handle's
        # ``publish_restore_plan.remote.aio(...)`` (the older plain-callable
        # shape was replaced).
        async def publish(payload, snapshot_seed=None):
            observed["restore_plan"] = payload
            return {"status": "published", "generation": 3}

        handle = SimpleNamespace(
            run_plan_stream=SimpleNamespace(remote_gen=SimpleNamespace(aio=remote_stream)),
            publish_restore_plan=SimpleNamespace(remote=SimpleNamespace(aio=publish)),
        )

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler"}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=lambda **kwargs: handle,
            )
            messages = [
                message async for message in transport.run_plan_stream(
                    plan,
                    gpu="rtx-pro-6000",
                    workspace={"id": "ws"},
                    trace={"prompt_id": "req-1"},
                )
            ]
            self.assertEqual(messages[-1]["data"], {"ok": True})
            self.assertEqual(observed["payload"]["workflow"], plan.to_dict()["workflow"])
            self.assertEqual(observed["kwargs"]["request_id"], "req-1")
            published = await transport.publish_restore_plan(
                {"generation": 3}, workspace={"id": "ws"},
            )
            self.assertEqual(published["generation"], 3)

        asyncio.run(run())

    def test_resolve_v2_cloud_returns_empty_for_rtx_pro_6000_when_unset(self):
        self.assertEqual(ModalTransport._resolve_v2_cloud("rtx-pro-6000"), "")

    def test_resolve_v2_cloud_returns_empty_for_other_gpus(self):
        self.assertEqual(ModalTransport._resolve_v2_cloud("a100-80gb"), "")

    def test_resolve_v2_cloud_env_var_overrides_default(self):
        os.environ["COMFYMODAL_V2_CLOUD"] = "aws"
        try:
            self.assertEqual(ModalTransport._resolve_v2_cloud("rtx-pro-6000"), "aws")
            self.assertEqual(ModalTransport._resolve_v2_cloud("a100-80gb"), "aws")
        finally:
            os.environ.pop("COMFYMODAL_V2_CLOUD", None)

    def test_resolve_v2_cloud_empty_env_returns_empty(self):
        os.environ["COMFYMODAL_V2_CLOUD"] = ""
        try:
            self.assertEqual(ModalTransport._resolve_v2_cloud("rtx-pro-6000"), "")
        finally:
            os.environ.pop("COMFYMODAL_V2_CLOUD", None)

    def test_v2_handle_cache_key_includes_cloud(self):
        from comfymodal_runtime.modal_transport import HandleCacheKey
        key = HandleCacheKey("ws", "app", "cls", environment="", gpu="rtx-pro-6000", cloud="gcp")
        self.assertEqual(key.cloud, "gcp")
        key2 = HandleCacheKey("ws", "app", "cls", environment="", gpu="rtx-pro-6000")
        self.assertEqual(key2.cloud, "")

    def test_resolve_environment_returns_empty_when_unset(self):
        """Both env vars absent -> empty string."""
        for var in ("COMFYMODAL_V2_ENVIRONMENT", "MODAL_ENVIRONMENT"):
            os.environ.pop(var, None)
        try:
            self.assertEqual(ModalTransport._resolve_environment(), "")
        finally:
            for var in ("COMFYMODAL_V2_ENVIRONMENT", "MODAL_ENVIRONMENT"):
                os.environ.pop(var, None)

    def test_resolve_environment_prefers_v2_var(self):
        """COMFYMODAL_V2_ENVIRONMENT wins over MODAL_ENVIRONMENT."""
        os.environ["COMFYMODAL_V2_ENVIRONMENT"] = "v2-staging"
        os.environ["MODAL_ENVIRONMENT"] = "shared-prod"
        try:
            self.assertEqual(ModalTransport._resolve_environment(), "v2-staging")
        finally:
            os.environ.pop("COMFYMODAL_V2_ENVIRONMENT", None)
            os.environ.pop("MODAL_ENVIRONMENT", None)

    def test_resolve_environment_ignores_modal_environment(self):
        """Only COMFYMODAL_V2_ENVIRONMENT is honored — ambient
        MODAL_ENVIRONMENT is intentionally NOT consulted ("" is returned so
        SDK lookups use the default deployed environment)."""
        os.environ.pop("COMFYMODAL_V2_ENVIRONMENT", None)
        os.environ["MODAL_ENVIRONMENT"] = "shared-prod"
        try:
            self.assertEqual(ModalTransport._resolve_environment(), "")
        finally:
            os.environ.pop("COMFYMODAL_V2_ENVIRONMENT", None)
            os.environ.pop("MODAL_ENVIRONMENT", None)

    def test_v2_handle_cache_key_includes_environment(self):
        """HandleCacheKey.environment is set and included in equality."""
        from comfymodal_runtime.modal_transport import HandleCacheKey
        key_a = HandleCacheKey("ws", "app", "cls", environment="staging")
        key_b = HandleCacheKey("ws", "app", "cls", environment="prod")
        key_default = HandleCacheKey("ws", "app", "cls")
        self.assertEqual(key_a.environment, "staging")
        self.assertEqual(key_b.environment, "prod")
        self.assertEqual(key_default.environment, "")
        self.assertNotEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_default)

    def test_v2_handle_cache_isolation_by_environment(self):
        """Handles for different environment values must not collide in cache."""
        transport = ModalTransport()
        # Directly populate the cache with two different environment keys
        from comfymodal_runtime.modal_transport import HandleCacheKey
        k1 = HandleCacheKey("ws", "app", "Cls", environment="staging")
        k2 = HandleCacheKey("ws", "app", "Cls", environment="prod")
        transport.handle_cache.put(k1, "handle-staging")
        transport.handle_cache.put(k2, "handle-prod")
        self.assertEqual(transport.handle_cache.get(k1), "handle-staging")
        self.assertEqual(transport.handle_cache.get(k2), "handle-prod")
        self.assertIsNone(transport.handle_cache.get(
            HandleCacheKey("ws", "app", "Cls")
        ))

    def test_configure_runtime_does_not_set_install_requirements_true(self):
        """_configure_runtime must leave install_requirements_on_startup at its default (False).

        V2 diagnosis containers must not install custom-node requirements at
        startup.  The runtime may still install requirements through explicit
        callback paths; this test only guards against the BootstrapConfig override.
        """
        source = Path("comfymodal_runtime/modal_app.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "install_requirements_on_startup=True",
            source,
            "_configure_runtime must not hard-code install_requirements_on_startup=True",
        )
        # Also confirm the BootstrapConfig default is False
        from comfymodal_runtime.runtime_bootstrap import BootstrapConfig
        self.assertFalse(BootstrapConfig().install_requirements_on_startup)

    def test_stream_iteration_does_not_add_local_timeout(self):
        """Stream instrumentation preserves the transport's existing iteration semantics."""
        source = Path("comfymodal_runtime/modal_transport.py").read_text(encoding="utf-8")
        self.assertNotIn("_STREAM_FIRST_EVENT_TIMEOUT", source)
        self.assertNotIn("asyncio.wait_for", source)
        self.assertNotIn("ait.aclose", source)


if __name__ == "__main__":
    unittest.main()
