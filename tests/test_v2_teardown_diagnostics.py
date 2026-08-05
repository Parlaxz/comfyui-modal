from __future__ import annotations

import inspect
import os
import time
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
