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

    def test_default_v2_transport_targets_registered_class(self):
        observed: dict[str, Any] = {}

        async def remote_stream(payload, **kwargs):
            observed["payload"] = payload
            observed["kwargs"] = kwargs
            yield {"type": "result", "data": {"ok": True}}

        def publish(payload):
            observed["restore_plan"] = payload
            return {"status": "published", "generation": 3}

        handle = SimpleNamespace(
            run_plan_stream=SimpleNamespace(remote_gen=SimpleNamespace(aio=remote_stream)),
            publish_restore_plan=SimpleNamespace(remote=publish),
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


if __name__ == "__main__":
    unittest.main()
