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


def test_release_minimal_teardown_skips_unload_cleanup_gc_and_cuda(monkeypatch):
    """Minimal teardown (COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=1) keeps the
    reference-release stages but SKIPS unload/device-fallback/cleanup/
    executor-reset/gc/cuda-cleanup, leaves unload_all_models_ran False, and
    reports teardown_mode='minimal' with the pre-exit allocation recorded via
    cuda_before (cuda_after stays empty).
    """
    _enabled_release(monkeypatch)
    monkeypatch.setenv("COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN", "1")
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, cuda = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="minimal")

    assert result["teardown_mode"] == "minimal"
    assert result["unload_all_models_ran"] is False
    assert result["device_fallback_ran"] is False
    assert result["legacy_executor_reset"] is False
    # Reference / bookkeeping stages KEPT.
    for kept in ("preload_workers", "activation_references",
                 "preload_references", "request_references",
                 "request_samplers", "legacy_request_workers"):
        assert kept in result["stage_results"], kept
    # Unload / cleanup / gc / cuda stages SKIPPED.
    for skipped in ("model_management_unload", "device_fallback",
                    "model_management_cleanup", "legacy_executor_reset",
                    "garbage_collection", "cuda_cleanup"):
        assert skipped not in result["stage_results"], skipped
    assert "unload_all_models" not in calls
    assert "cleanup_models" not in calls
    assert "executor_reset" not in calls
    assert cuda.synchronize_calls == 0
    assert cuda.empty_cache_calls == 0
    # cuda_after is empty in minimal mode, so the evidence uses cuda_before.
    assert result["cuda_allocated_before"] == 128
    assert result["cuda_allocated_after"] == 128
    assert result["cuda_reserved_after"] == 256


def test_release_minimal_teardown_defaults_to_full(capsys, monkeypatch):
    """For REUSABLE containers (single-use off) and no explicit minimal flag the
    release stays 'full' and the teardown_mode event carries 'full'."
    """
    _enabled_release(monkeypatch)
    monkeypatch.setenv("COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS", "1")
    monkeypatch.delenv("COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN", raising=False)
    monkeypatch.setenv("COMFYMODAL_V2_SINGLE_USE_CONTAINERS", "0")
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(
            diagnostics=entrypoint._teardown_diagnostics,
            request_id="full-mode",
        )
    assert result["teardown_mode"] == "full"
    assert result["unload_all_models_ran"] is True
    output = capsys.readouterr().out
    assert '"event":"request_gpu_release_teardown_mode"' in output
    assert '"teardown_mode":"full"' in output


def test_release_minimal_teardown_defaults_on_for_single_use(monkeypatch):
    """When COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN is unset but the container is
    single-use, the minimal bounded teardown path is the DEFAULT: skip
    unload/cleanup/gc/cuda and rely on process exit, leaving
    unload_all_models_ran False.
    """
    _enabled_release(monkeypatch)
    monkeypatch.delenv("COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN", raising=False)
    monkeypatch.setenv("COMFYMODAL_V2_SINGLE_USE_CONTAINERS", "1")
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, cuda = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="single-use-default")

    assert result["teardown_mode"] == "minimal"
    assert result["unload_all_models_ran"] is False
    assert result["device_fallback_ran"] is False
    assert result["legacy_executor_reset"] is False
    for kept in ("preload_workers", "activation_references",
                 "preload_references", "request_references",
                 "request_samplers", "legacy_request_workers"):
        assert kept in result["stage_results"], kept
    for skipped in ("model_management_unload", "device_fallback",
                    "model_management_cleanup", "legacy_executor_reset",
                    "garbage_collection", "cuda_cleanup"):
        assert skipped not in result["stage_results"], skipped
    assert "unload_all_models" not in calls
    assert "cleanup_models" not in calls
    assert "executor_reset" not in calls
    assert cuda.synchronize_calls == 0
    assert cuda.empty_cache_calls == 0


def test_release_minimal_teardown_defaults_off_for_reusable(monkeypatch):
    """When COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN is unset and the container is
    REUSABLE, the full unload path is the DEFAULT: unload_all_models runs and
    unload_all_models_ran is True.
    """
    _enabled_release(monkeypatch)
    monkeypatch.delenv("COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN", raising=False)
    monkeypatch.setenv("COMFYMODAL_V2_SINGLE_USE_CONTAINERS", "0")
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, cuda = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="reusable-default")

    assert result["teardown_mode"] == "full"
    assert result["unload_all_models_ran"] is True
    assert result["device_fallback_ran"] is False
    assert calls.count("unload_all_models") == 1
    assert cuda.synchronize_calls == 1
    assert cuda.empty_cache_calls == 1


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


def test_run_plan_stream_cleanup_begins_at_terminal_before_handoff(monkeypatch):
    """Cleanup begins synchronously as the request call produces the terminal
    event, BEFORE that event is handed off to the consumer.  The finalizer is
    not required and nothing waits an extra event-loop turn.
    """
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
                # Cleanup ran synchronously inside the producing call, so the
                # sequence is already complete when the consumer sees the event.
                assert order == ["production_cleanup", "gpu_release"]
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


def test_release_requests_full_gc_collect_without_generation(monkeypatch):
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    calls = []
    fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)

    class FakeGc:
        def __init__(self):
            self.collect_calls = []

        def collect(self, *args):
            self.collect_calls.append(args)

    fake_gc = FakeGc()
    entrypoint = ModalRuntimeEntrypoint()
    snapshot_models = SimpleNamespace(unet=object(), clip=object(), vae=object())
    entrypoint._cpu_snapshot_models = snapshot_models
    entrypoint._cpu_snapshot_models_active = True
    entrypoint.bootstrap.state.snapshot_loader_outputs = {"unet": snapshot_models.unet}
    entrypoint.bootstrap.state.snapshot_execution_seed = object()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
        "gc": fake_gc,
    }):
        result = entrypoint._release_gpu_after_request(request_id="full-gc")
    assert result["status"] == "ok"
    assert fake_gc.collect_calls == [()]
    assert entrypoint._cpu_snapshot_models is snapshot_models
    assert entrypoint._cpu_snapshot_models_active is False
    assert entrypoint.bootstrap.state.snapshot_loader_outputs
    assert entrypoint.bootstrap.state.snapshot_execution_seed is not None


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


def test_terminal_cleanup_begins_without_second_item(monkeypatch):
    """Terminal event is delivered AND cleanup runs even when the consumer
    never requests a second item.

    Cleanup executes synchronously inside the producing call the moment the
    terminal result/error event is identified, so it does not depend on the
    remote consumer resuming the generator, on an extra event-loop turn, or on
    the generator finalizer running.
    """
    import asyncio

    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        entrypoint = ModalRuntimeEntrypoint()
        order = []

        async def impl(*args, **kwargs):
            yield {"type": "result", "data": {"ok": True}, "request_id": "single"}

        entrypoint._run_plan_stream_impl = impl
        entrypoint._run_pending_production_cleanup = lambda: order.append("production_cleanup")
        entrypoint._release_gpu_after_request = lambda **kwargs: order.append("gpu_release")

        agen = entrypoint.run_plan_stream({}, request_id="single")
        # Consumer reads exactly one item (the terminal event) and stops —
        # it does NOT request a second item.  Cleanup already ran synchronously
        # before this event was returned, so the order is already complete.
        first = await agen.__anext__()
        assert first["type"] == "result"
        assert order == ["production_cleanup", "gpu_release"]
        # Deterministically reconcile the generator to avoid GC warnings.
        await agen.aclose()
        return first, order

    first, order = asyncio.run(run())
    assert first["data"] == {"ok": True}
    assert order == ["production_cleanup", "gpu_release"]


def test_terminal_cleanup_order_survives_errors_without_second_item(monkeypatch):
    """Cleanup runs production cleanup then GPU release in order and the
    terminal response survives cleanup errors even when the consumer never
    requests a second item.
    """
    import asyncio

    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        entrypoint = ModalRuntimeEntrypoint()
        order = []

        def hostile_production():
            order.append("production_cleanup")
            raise RuntimeError("production")

        def hostile_release(**kwargs):
            order.append("gpu_release")
            raise RuntimeError("release")

        async def impl(*args, **kwargs):
            yield {"type": "result", "data": {"ok": True}, "request_id": "error-cleanup"}

        entrypoint._run_plan_stream_impl = impl
        entrypoint._run_pending_production_cleanup = hostile_production
        entrypoint._release_gpu_after_request = hostile_release

        agen = entrypoint.run_plan_stream({}, request_id="error-cleanup")
        first = await agen.__anext__()
        await agen.aclose()
        return first, order

    first, order = asyncio.run(run())
    assert first["type"] == "result"
    assert first["data"] == {"ok": True}
    assert order == ["production_cleanup", "gpu_release"]


def test_repeated_terminal_cleanup_guard_is_idempotent(monkeypatch):
    """A repeated generator close/exit racing the synchronous cleanup cannot
    duplicate the sequence: the per-request cleanup guard runs it exactly once.
    """
    import asyncio

    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        entrypoint = ModalRuntimeEntrypoint()
        order = []

        async def impl(*args, **kwargs):
            yield {"type": "result", "data": {"ok": True}, "request_id": "dup"}

        entrypoint._run_plan_stream_impl = impl
        entrypoint._run_pending_production_cleanup = lambda: order.append("production_cleanup")
        entrypoint._release_gpu_after_request = lambda **kwargs: order.append("gpu_release")

        agen = entrypoint.run_plan_stream({}, request_id="dup")
        first = await agen.__anext__()
        assert order == ["production_cleanup", "gpu_release"]
        # Repeated generator close/exit cannot duplicate: cleanup already ran
        # synchronously, and the generator finalizer's fallback is a no-op.
        await agen.aclose()
        await agen.aclose()
        return first, order

    first, order = asyncio.run(run())
    assert first["data"] == {"ok": True}
    assert order == ["production_cleanup", "gpu_release"]


def test_post_stream_release_hook_reruns_effective_release(monkeypatch):
    """The request-handler post-stream release hook re-executes the effective
    GPU release even when ``run_plan_stream`` already marked the per-request
    release done (that first attempt runs while the generator frame is still
    alive and cannot actually free memory).  It resets the per-request release
    state so the unload / gc / empty_cache run again at the frame-released
    boundary.
    """
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    _enabled_release(monkeypatch)
    calls = []
    fake_comfy, fake_mm, fake_torch, cuda = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    # Simulate an earlier best-effort release that already claimed the slot.
    entrypoint._request_gpu_release_done = True
    entrypoint._request_gpu_release_request_id = "post"
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_after_stream_complete(request_id="post")
    assert result["status"] == "ok"
    assert result["unload_all_models_ran"] is True
    assert result["device_fallback_ran"] is False
    assert cuda.synchronize_calls == 1
    assert cuda.empty_cache_calls == 1
    assert calls.count("unload_all_models") == 1
    assert entrypoint._request_gpu_release_request_id == "post"


def test_post_stream_release_hook_is_safe_and_idempotent(monkeypatch):
    """The post-stream release hook never raises and is safe to run repeatedly;
    a later release after a completed effective release is a no-op.
    """
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    _enabled_release(monkeypatch)
    calls = []
    fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        first = entrypoint._release_after_stream_complete(request_id="post-2")
        second = entrypoint._release_after_stream_complete(request_id="post-2")
    assert first["status"] == "ok"
    assert second["status"] == "already_released"
    assert calls.count("unload_all_models") == 1


def test_run_plan_stream_marks_terminal_delivered_for_exit_release(monkeypatch):
    """run_plan_stream sets _terminal_response_delivered when a terminal event
    is produced, so the modal.exit shutdown fallback still releases the GPU if
    the post-stream hook path is not taken.
    """
    import asyncio

    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    async def run():
        entrypoint = ModalRuntimeEntrypoint()

        async def impl(*args, **kwargs):
            yield {"type": "result", "data": {"ok": True}, "request_id": "exit-flag"}

        entrypoint._run_plan_stream_impl = impl
        async for _ in entrypoint.run_plan_stream({}, request_id="exit-flag"):
            pass
        return entrypoint

    entrypoint = asyncio.run(run())
    assert entrypoint._terminal_response_delivered is True


def _fake_pin_unload_env(*, cpu_marker, cuda_marker, patchers):
    """Build fake comfy/model_management/torch modules for the offload-pin test.

    Returns (fake_comfy, fake_mm, fake_torch, unload_seen_offloads) where
    ``unload_seen_offloads`` is filled by the fake ``unload_all_models`` with a
    snapshot of each patcher's ``offload_device`` at the moment of unload.
    """
    import torch as _real_torch  # noqa: F401  (ensure a torch module exists)

    unload_seen_offloads = []

    class FakePatcher:
        def __init__(self):
            self.offload_device = cuda_marker

    if patchers is None:
        patchers = [FakePatcher(), FakePatcher()]

    class FakeBaseModel:
        def __init__(self, patcher):
            self.patcher = patcher

    entries = [FakeBaseModel(p) for p in patchers]

    def fake_unload_all():
        unload_seen_offloads.append([p.offload_device for p in patchers])

    fake_mm = SimpleNamespace(
        current_loaded_models=entries,
        unload_all_models=fake_unload_all,
        get_all_torch_devices=lambda: [],
        free_memory=lambda *a, **k: None,
        cleanup_models=lambda: None,
    )
    fake_torch = SimpleNamespace(
        cuda=_ReleaseCuda(),
        device=lambda *a, **k: cpu_marker,
    )
    fake_comfy = ModuleType("comfy")
    fake_comfy.__path__ = []
    return fake_comfy, fake_mm, fake_torch, unload_seen_offloads, patchers


def test_unload_pins_patcher_offload_to_cpu_and_restores(monkeypatch):
    """During unload_all_models() every loaded patcher's offload_device is
    temporarily pinned to CPU (so ModelPatcher.detach() moves weights to CPU,
    not CUDA), and the original offload devices are restored afterward.
    """
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    cpu_marker = SimpleNamespace(type="cpu", kind="cpu-marker")
    cuda_marker = SimpleNamespace(type="cuda", index=0)
    fake_comfy, fake_mm, fake_torch, seen, patchers = _fake_pin_unload_env(
        cpu_marker=cpu_marker, cuda_marker=cuda_marker, patchers=None,
    )
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="pin-cpu")

    assert result["status"] == "ok"
    assert result["unload_all_models_ran"] is True
    # Every patcher's offload_device was CPU at the moment unload ran.
    assert seen == [[cpu_marker, cpu_marker]]
    # Original offload devices are restored after the release.
    assert [p.offload_device for p in patchers] == [cuda_marker, cuda_marker]


def test_unload_pin_restores_offload_when_unload_raises(monkeypatch):
    """Even when unload_all_models() raises, the original offload devices are
    restored (finally), preserving warm-path state and not masking the error.
    """
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    cpu_marker = SimpleNamespace(type="cpu", kind="cpu-marker")
    cuda_marker = SimpleNamespace(type="cuda", index=0)
    unload_seen_offloads = []

    class FakePatcher:
        def __init__(self):
            self.offload_device = cuda_marker

    patcher = FakePatcher()

    class FakeBaseModel:
        def __init__(self):
            self.patcher = patcher

    def hostile_unload_all():
        unload_seen_offloads.append(patcher.offload_device)
        raise RuntimeError("unload boom")

    fake_mm = SimpleNamespace(
        current_loaded_models=[FakeBaseModel()],
        unload_all_models=hostile_unload_all,
        get_all_torch_devices=lambda: [],
        free_memory=lambda *a, **k: None,
        cleanup_models=lambda: None,
    )
    fake_torch = SimpleNamespace(
        cuda=_ReleaseCuda(),
        device=lambda *a, **k: cpu_marker,
    )
    fake_comfy = ModuleType("comfy")
    fake_comfy.__path__ = []
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="pin-raise")

    assert result["status"] == "error"
    assert "model_management_unload" in result["cleanup_errors"]
    # Offload was CPU during the (raising) unload, then restored afterward.
    assert unload_seen_offloads == [cpu_marker]
    assert patcher.offload_device is cuda_marker


def test_unload_pin_degrades_when_torch_lacks_device(monkeypatch):
    """When torch has no usable device() (e.g. minimal fakes), the unload still
    runs and no patcher offload is mutated — graceful degradation preserves
    existing behavior.
    """
    _enabled_release(monkeypatch)
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    cuda_marker = SimpleNamespace(type="cuda", index=0)
    unload_seen_offloads = []

    class FakePatcher:
        def __init__(self):
            self.offload_device = cuda_marker

    patcher = FakePatcher()

    class FakeBaseModel:
        def __init__(self):
            self.patcher = patcher

    def fake_unload_all():
        unload_seen_offloads.append(patcher.offload_device)

    fake_mm = SimpleNamespace(
        current_loaded_models=[FakeBaseModel()],
        unload_all_models=fake_unload_all,
        get_all_torch_devices=lambda: [],
        free_memory=lambda *a, **k: None,
        cleanup_models=lambda: None,
    )
    # torch without a device() callable (only cuda helpers).
    fake_torch = SimpleNamespace(cuda=_ReleaseCuda())
    fake_comfy = ModuleType("comfy")
    fake_comfy.__path__ = []
    entrypoint = ModalRuntimeEntrypoint()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        result = entrypoint._release_gpu_after_request(request_id="pin-degrade")

    assert result["status"] == "ok"
    assert result["unload_all_models_ran"] is True
    # Offload device was left untouched (cpu_device unavailable).
    assert unload_seen_offloads == [cuda_marker]
    assert patcher.offload_device is cuda_marker


def test_release_close_preload_workers_uses_bounded_budget(monkeypatch):
    """The release path joins preload workers with the shared bounded budget
    (_PRELOAD_WORKER_JOIN_BUDGET_S, default 5s) so a surviving non-daemon
    worker is joined before exit without an unbounded wait.
    """
    from comfymodal_runtime.modal_app import (
        ModalRuntimeEntrypoint,
        _PRELOAD_WORKER_JOIN_BUDGET_S,
    )

    _enabled_release(monkeypatch)
    calls = []
    close_calls = []
    fake_comfy, fake_mm, fake_torch, _ = _release_modules(calls=calls)

    class FakeBridge:
        def close_workers(self, **kwargs):
            close_calls.append(kwargs)
            return {"pool": {"alive_thread_count": 0, "thread_count": 1}}

    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._preload_bridge = FakeBridge()
    with patch.dict(sys.modules, {
        "comfy": fake_comfy,
        "comfy.model_management": fake_mm,
        "torch": fake_torch,
    }):
        entrypoint._release_gpu_after_request(request_id="budget")

    assert len(close_calls) == 1
    assert close_calls[0]["timeout"] == _PRELOAD_WORKER_JOIN_BUDGET_S
    assert close_calls[0]["timeout"] == 5.0
    # Bounded: a finite positive timeout, never None (which would block forever).
    assert close_calls[0]["timeout"] is not None and close_calls[0]["timeout"] > 0
    assert close_calls[0]["cancel_futures"] is True
    assert close_calls[0]["wait_futures"] is False


def test_join_lingering_preload_threads_joins_bounded(monkeypatch):
    """A lingering non-daemon 'comfymodal-restore-*' worker is joined by the
    shutdown sweep and reported as joined.  Other threads are left untouched.
    """
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    class FakeThread:
        def __init__(self, name):
            self.name = name
            self.alive = True
            self.joined = False
            self.daemon = False

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.joined = True
            self.alive = False

    worker = FakeThread("comfymodal-restore-unet-abc123")
    other = FakeThread("some-other-thread")
    with patch(
        "comfymodal_runtime.modal_app.threading.enumerate",
        return_value=[worker, other],
    ):
        result = ModalRuntimeEntrypoint()._join_lingering_preload_threads(budget_s=5.0)

    assert worker.joined is True
    assert other.joined is False
    assert result["found"] == 1
    assert result["joined"] == 1
    assert result["still_alive"] == 0


def test_sweep_matches_app_owned_thread_names(monkeypatch):
    """The generalized sweep joins every non-daemon app-owned worker thread
    (comfymodal-restore-*, comfymodal-stall-watchdog-*, etc.) and reports it,
    while leaving non-app and current-thread-like threads alone.
    """
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    class FakeThread:
        def __init__(self, name):
            self.name = name
            self.alive = True
            self.joined = False
            self.daemon = False

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.joined = True
            self.alive = False

    restore = FakeThread("comfymodal-restore-unet-aaa")
    watchdog = FakeThread("comfymodal-stall-watchdog-0123456789abcdef")
    unrelated = FakeThread("comfy-worker-xyz")
    with patch(
        "comfymodal_runtime.modal_app.threading.enumerate",
        return_value=[restore, watchdog, unrelated],
    ):
        result = ModalRuntimeEntrypoint()._join_lingering_preload_threads(budget_s=5.0)

    assert restore.joined is True
    assert watchdog.joined is True
    assert unrelated.joined is False
    assert result["found"] == 2
    assert result["joined"] == 2
    assert result["still_alive"] == 0


def test_sweep_ignores_infrastructure_and_daemon_threads(monkeypatch):
    """The sweep never joins Modal/runtime infrastructure threads or daemon
    threads, and never joins the current thread.
    """
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    joined = []

    class InfraThread:
        def __init__(self, name, daemon=True):
            self.name = name
            self.daemon = daemon

        def is_alive(self):
            return True

        def join(self, timeout=None):
            joined.append(self.name)

    modal_thread = InfraThread("Modal-Handler-1")
    asyncio_thread = InfraThread("asyncio_runner_0")
    main_like = InfraThread("MainThread")
    daemon_app = InfraThread("comfymodal-restore-unet-daemon", daemon=True)
    with patch(
        "comfymodal_runtime.modal_app.threading.enumerate",
        return_value=[modal_thread, asyncio_thread, main_like, daemon_app],
    ):
        result = ModalRuntimeEntrypoint()._join_lingering_preload_threads(budget_s=5.0)

    assert joined == []
    assert result["found"] == 0
    assert result["joined"] == 0
    assert result["still_alive"] == 0


def test_sweep_excludes_current_thread(monkeypatch):
    """The sweep never joins the current (calling) thread even if it were
    matched by name.
    """
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
    import threading

    current = threading.current_thread()
    original_name = current.name
    current.name = "comfymodal-restore-something"  # rename for the test
    try:
        with patch(
            "comfymodal_runtime.modal_app.threading.enumerate",
            return_value=[current],
        ):
            result = ModalRuntimeEntrypoint()._join_lingering_preload_threads(budget_s=5.0)
    finally:
        current.name = original_name
    assert result["found"] == 0
    assert result["joined"] == 0
    assert result["still_alive"] == 0


def test_join_lingering_preload_threads_stays_bounded_when_unjoinable(monkeypatch):
    """If a preload worker ignores the join and stays alive, the sweep reports
    it as still_alive and returns quickly (bounded by the budget) instead of
    blocking interpreter exit indefinitely.
    """
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
    import time

    class StuckThread:
        def __init__(self, name):
            self.name = name
            self.joined = 0
            self.daemon = False

        def is_alive(self):
            return True  # never finishes

        def join(self, timeout=None):
            self.joined += 1  # stays alive despite join

    worker = StuckThread("comfymodal-restore-vae-xyz789")
    with patch(
        "comfymodal_runtime.modal_app.threading.enumerate",
        return_value=[worker],
    ):
        started = time.monotonic()
        result = ModalRuntimeEntrypoint()._join_lingering_preload_threads(budget_s=0.2)
        elapsed = time.monotonic() - started

    assert result["still_alive"] == 1
    assert result["joined"] == 0
    assert result["found"] == 1
    # Bounded: returns promptly, well under the budget.
    assert elapsed < 1.0
