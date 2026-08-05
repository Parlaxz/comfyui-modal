from __future__ import annotations

import inspect
import os
import sys
import time
from types import ModuleType, SimpleNamespace
from pathlib import Path
from unittest.mock import patch


def test_diagnostics_are_inert_without_flag(capsys, monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", raising=False)
    from comfymodal_runtime.teardown_diagnostics import TeardownDiagnostics

    diagnostics = TeardownDiagnostics(container_session_id="session")
    diagnostics.emit("exit_hook_start")
    assert diagnostics.enabled is False
    assert capsys.readouterr().out == ""


def test_enabled_snapshot_is_bounded_and_redacts(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", "1")
    from comfymodal_runtime.teardown_diagnostics import TeardownDiagnostics

    diagnostics = TeardownDiagnostics(container_session_id="session")
    diagnostics.configure_paths(runtime_state=str(tmp_path))
    diagnostics.record_file_write(Path(tmp_path) / "state.json", volume="runtime")
    diagnostics.emit(
        "cleanup_stage_start",
        stage="state",
        secret_value="must-not-appear",
    )
    output = capsys.readouterr().out
    assert "[v2.teardown]" in output
    assert "must-not-appear" not in output
    assert '"event":"cleanup_stage_start"' in output
    assert '"wall_unix_ns":' in output
    assert '"threads":' in output
    assert '"processes":' in output
    assert '"files_written":' in output


def test_snapshot_does_not_initialize_cuda(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", "1")
    from comfymodal_runtime import teardown_diagnostics

    class FakeCuda:
        def __init__(self):
            self.initialized_calls = 0

        def is_initialized(self):
            self.initialized_calls += 1
            return False

    fake_cuda = FakeCuda()
    fake_torch = type("Torch", (), {"cuda": fake_cuda})()
    with patch.dict(teardown_diagnostics.sys.modules, {"torch": fake_torch}):
        diagnostics = teardown_diagnostics.TeardownDiagnostics()
        diagnostics.snapshot()
    assert fake_cuda.initialized_calls == 1


def test_sampler_stop_is_bounded():
    from comfymodal_runtime.modal_app import _ProcessCpuSampler

    sampler = _ProcessCpuSampler(time.monotonic_ns())
    sampler.start()
    sampler.stop(timeout=0.2)
    assert sampler._thread is None or not sampler._thread.is_alive()
    source = inspect.getsource(_ProcessCpuSampler.stop)
    assert "join()" not in source.replace("join(timeout", "")


def test_exit_cleanup_is_idempotent(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", raising=False)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
    from comfymodal_runtime.model_preload import V2LoaderBridge

    entrypoint = ModalRuntimeEntrypoint()
    entrypoint.exit()
    entrypoint.exit()
    assert V2LoaderBridge().close_workers() == {
        "present": 0,
        "done_before_wait": 0,
        "failed": 0,
        "pool": {
            "pool_present": False,
            "thread_count": 0,
            "alive_thread_count": 0,
            "alive_threads": [],
        },
    }


class _ReleaseCuda:
    def __init__(self, *, initialized=True):
        self.initialized = initialized
        self.initialized_calls = 0
        self.synchronize_calls = 0
        self.empty_cache_calls = 0
        self.allocated = 128
        self.reserved = 256

    def is_initialized(self):
        self.initialized_calls += 1
        return self.initialized

    def memory_allocated(self):
        return self.allocated

    def memory_reserved(self):
        return self.reserved

    def synchronize(self):
        self.synchronize_calls += 1

    def empty_cache(self):
        self.empty_cache_calls += 1
        self.allocated = 0
        self.reserved = 0


def _release_modules(*, unload=True, initialized=True, calls=None, devices=()):
    calls = calls if calls is not None else []
    cuda = _ReleaseCuda(initialized=initialized)
    torch_module = SimpleNamespace(cuda=cuda)
    fake_mm = SimpleNamespace(
        cleanup_models=lambda: calls.append("cleanup_models"),
        get_all_torch_devices=lambda: list(devices),
        free_memory=lambda required, device, keep_loaded: calls.append(
            ("free_memory", device, keep_loaded)
        ),
    )
    if unload:
        fake_mm.unload_all_models = lambda: calls.append("unload_all_models")
    fake_comfy = ModuleType("comfy")
    fake_comfy.__path__ = []
    return fake_comfy, fake_mm, torch_module, cuda


def _enabled_release(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST", "1")
    monkeypatch.delenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", raising=False)


def test_release_disabled_is_a_noop(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST", raising=False)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    entrypoint = ModalRuntimeEntrypoint()
    original_bridge = entrypoint._preload_bridge
    result = entrypoint._release_gpu_after_request(request_id="disabled")
    assert result["status"] == "disabled"
    assert entrypoint._preload_bridge is original_bridge


def test_release_prefers_unload_all_models_and_resets_live_executor(monkeypatch):
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, cuda = _release_modules(calls=calls)
    executor = SimpleNamespace(reset=lambda: calls.append("executor_reset"))
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(_executor=executor)
    snapshot_models = SimpleNamespace(unet=object(), clip=object(), vae=object())
    entrypoint._cpu_snapshot_models = snapshot_models
    entrypoint._cpu_snapshot_models_active = True
    entrypoint.bootstrap.state.snapshot_loader_outputs = {"unet": snapshot_models.unet}
    entrypoint.bootstrap.state.snapshot_execution_seed = object()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="one")
    assert result["unload_all_models_ran"] is True
    assert result["device_fallback_ran"] is False
    assert result["legacy_executor_reset"] is True
    assert calls[:2] == ["unload_all_models", "cleanup_models"]
    assert calls[-1] == "executor_reset"
    assert cuda.synchronize_calls == 1
    assert cuda.empty_cache_calls == 1
    assert entrypoint._cpu_snapshot_models is snapshot_models
    assert entrypoint._cpu_snapshot_models_active is False
    assert entrypoint.bootstrap.state.snapshot_loader_outputs
    assert entrypoint.bootstrap.state.snapshot_execution_seed is not None


def test_release_fallback_targets_torch_devices_not_cpu(monkeypatch):
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    cpu = SimpleNamespace(type="cpu")
    cuda_device = SimpleNamespace(type="cuda", index=0)
    calls = []
    fake_comfy, fake_mm, fake_torch, _ = _release_modules(
        unload=False,
        initialized=False,
        calls=calls,
        devices=(cpu, cuda_device),
    )
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="fallback")
    assert result["unload_all_models_ran"] is False
    assert result["device_fallback_ran"] is True
    assert [item[1] for item in calls if isinstance(item, tuple)] == [cuda_device]


def test_release_diagnostics_include_memory_and_bounded_stage_results(capsys, monkeypatch):
    _enabled_release(monkeypatch)
    monkeypatch.setenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", "1")
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        entrypoint._release_gpu_after_request(
            diagnostics=entrypoint._teardown_diagnostics,
            request_id="diagnostic",
        )
    output = capsys.readouterr().out
    assert '"event":"request_gpu_release_start"' in output
    assert '"event":"request_gpu_release_end"' in output
    assert '"unload_all_models_ran":true' in output
    assert '"device_fallback_ran":false' in output
    assert '"legacy_executor_reset":false' in output
    assert '"cuda_allocated_before":128' in output
    assert '"cuda_allocated_after":0' in output
    assert '"cuda_reserved_before":256' in output
    assert '"cuda_reserved_after":0' in output
    assert '"stage_results":' in output
    assert '"cleanup_errors":' in output


def test_release_does_not_initialize_cuda_when_not_initialized(monkeypatch):
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    fake_comfy, fake_mm, fake_torch, cuda = _release_modules(initialized=False)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="no-init")
    assert result["cuda_allocated_before"] is None
    assert result["cuda_allocated_after"] is None
    assert cuda.synchronize_calls == 0
    assert cuda.empty_cache_calls == 0


def test_repeated_release_calls_are_safe_and_run_once(monkeypatch):
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        first = entrypoint._release_gpu_after_request(request_id="same")
        second = entrypoint._release_gpu_after_request(request_id="same")
    assert first["release_performed"] is True
    assert second["status"] == "already_released"
    assert calls.count("unload_all_models") == 1


def test_release_errors_are_stage_recorded_and_never_raise(monkeypatch):
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    class HostileBridge:
        def close_workers(self, **kwargs):
            raise RuntimeError("close")

        def clear(self):
            raise RuntimeError("clear")

    fake_comfy = ModuleType("comfy")
    fake_comfy.__path__ = []
    fake_mm = SimpleNamespace(
        unload_all_models=lambda: (_ for _ in ()).throw(RuntimeError("unload")),
        get_all_torch_devices=lambda: (_ for _ in ()).throw(RuntimeError("devices")),
        free_memory=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("free")),
        cleanup_models=lambda: (_ for _ in ()).throw(RuntimeError("cleanup")),
    )
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(
        is_initialized=lambda: (_ for _ in ()).throw(RuntimeError("cuda")),
    ))
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._preload_bridge = HostileBridge()
    entrypoint._legacy_api = SimpleNamespace(
        _executor=SimpleNamespace(reset=lambda: (_ for _ in ()).throw(RuntimeError("reset"))),
    )
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="hostile")
    assert result["status"] == "error"
    assert result["cleanup_errors"]
    assert "preload_workers" in result["cleanup_errors"]
    assert "preload_references" in result["cleanup_errors"]


def test_run_plan_stream_releases_after_terminal_yield_and_production_cleanup(monkeypatch):
    import asyncio

    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        entrypoint = ModalRuntimeEntrypoint()
        order = []

        async def impl(*args, **kwargs):
            yield {"type": "result", "data": {"ok": True}, "request_id": "ordered"}

        entrypoint._run_plan_stream_impl = impl
        entrypoint._run_pending_production_cleanup = lambda: order.append("production_cleanup")
        entrypoint._release_gpu_after_request = lambda **kwargs: order.append("gpu_release")
        messages = []
        async for message in entrypoint.run_plan_stream({}, request_id="ordered"):
            messages.append(message)
            if message["type"] == "result":
                assert order == []
        return messages, order

    messages, order = asyncio.run(run())
    assert messages[-1]["data"] == {"ok": True}
    assert order == ["production_cleanup", "gpu_release"]


def test_run_plan_stream_response_survives_cleanup_failures(monkeypatch):
    import asyncio

    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        entrypoint = ModalRuntimeEntrypoint()

        async def impl(*args, **kwargs):
            yield {"type": "result", "data": {"ok": True}, "request_id": "safe"}

        entrypoint._run_plan_stream_impl = impl
        entrypoint._run_pending_production_cleanup = lambda: (_ for _ in ()).throw(RuntimeError("production"))
        entrypoint._release_gpu_after_request = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("release"))
        return [message async for message in entrypoint.run_plan_stream({}, request_id="safe")]

    messages = asyncio.run(run())
    assert messages[-1]["type"] == "result"
    assert messages[-1]["data"] == {"ok": True}


def test_release_end_is_observable_before_later_exit_hook(capsys, monkeypatch):
    import asyncio
    import json

    _enabled_release(monkeypatch)
    monkeypatch.setenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", "1")
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        calls = []
        fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)
        entrypoint = ModalRuntimeEntrypoint()

        async def impl(*args, **kwargs):
            yield {"type": "result", "data": {"ok": True}, "request_id": "exit-order"}

        entrypoint._run_plan_stream_impl = impl
        with patch.dict(sys.modules, {
            "comfy": fake_comfy,
            "comfy.model_management": fake_mm,
            "torch": fake_torch,
        }):
            messages = [
                message async for message in entrypoint.run_plan_stream(
                    {}, request_id="exit-order",
                )
            ]
            entrypoint.exit()
        return messages

    messages = asyncio.run(run())
    assert messages[-1]["type"] == "result"
    events = []
    for line in capsys.readouterr().out.splitlines():
        if line.startswith("[v2.teardown] "):
            events.append(json.loads(line[len("[v2.teardown] "):])["event"])
    assert events.index("request_gpu_release_end") < events.index("exit_hook_start")


def test_second_request_preserves_snapshot_identity_and_configuration(monkeypatch):
    import asyncio

    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        calls = []
        fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)
        entrypoint = ModalRuntimeEntrypoint()
        snapshot_models = SimpleNamespace(unet=object(), clip=object(), vae=object())
        entrypoint._cpu_snapshot_models = snapshot_models
        entrypoint._cpu_snapshot_models_active = True
        entrypoint.bootstrap.state.snapshot_model_identities = {"unet": "u", "clip": "c"}
        entrypoint.bootstrap.state.snapshot_execution_seed = object()
        seen = []

        async def impl(*args, **kwargs):
            seen.append((entrypoint._cpu_snapshot_models, entrypoint._cpu_snapshot_models_active))
            yield {"type": "result", "data": {"ok": True}, "request_id": kwargs["request_id"]}

        entrypoint._run_plan_stream_impl = impl
        with patch.dict(sys.modules, {
            "comfy": fake_comfy,
            "comfy.model_management": fake_mm,
            "torch": fake_torch,
        }):
            first = [message async for message in entrypoint.run_plan_stream({}, request_id="first")]
            second = [message async for message in entrypoint.run_plan_stream({}, request_id="second")]
        return entrypoint, snapshot_models, seen, first, second

    entrypoint, snapshot_models, seen, first, second = asyncio.run(run())
    assert first[-1]["data"]["ok"] is True
    assert second[-1]["data"]["ok"] is True
    assert seen[0][0] is snapshot_models
    assert seen[1][0] is snapshot_models
    assert entrypoint.bootstrap.state.snapshot_execution_seed is not None
