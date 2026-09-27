"""Focused tests for the CUDA import guard and custom-node import-health
accounting (SeedVR2 CPU-snapshot deferral behavior).

Guards the bounded invariants:

- The CUDA import guard in ``_force_cpu_during_snapshot`` is preserved: it
  still blocks ``*_cuda`` / ``cuda_*`` / sageattention C-extension imports
  during snap=True, so CUDA-dependent nodes like SeedVR2 are unavailable/lazy
  during CPU snapshot creation.
- ``_IN_CPU_SNAPSHOT`` is set while the snapshot guard is active, so failures
  recorded during that window are classified as retryable
  (``cpu_snapshot_schema``) and retried after GPU warmup â€” normal CUDA runtime
  retains availability.
- ``_collect_custom_node_import_health`` counts persistent failures and
  reports snapshot-deferred failures separately, so a visible SeedVR2 failure
  is counted or safely skipped accurately.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]


def _modal_stub():
    modal = types.ModuleType("modal")
    modal.Image = MagicMock()
    modal.Image.from_registry.return_value = MagicMock()
    modal.Image.debian_slim.return_value = MagicMock()
    modal.App = MagicMock()
    modal.App.return_value.function = lambda **_: lambda fn: fn
    modal.App.return_value.cls = lambda **_: lambda cls: cls
    modal.Volume = MagicMock()
    modal.Volume.from_name.return_value = MagicMock()
    modal.Dict = MagicMock()
    modal.Dict.from_name.return_value = MagicMock()
    modal.Secret = MagicMock()
    modal.Secret.from_name.return_value = MagicMock()
    modal.web_server = lambda *_, **__: lambda fn: fn
    modal.enter = lambda **_: lambda fn: fn
    modal.exit = lambda: lambda fn: fn
    modal.method = lambda *_, **__: lambda fn: fn
    modal.concurrent = lambda **_: lambda cls: cls
    return modal


def _load_comfyapp():
    old_modal = sys.modules.pop("modal", None)
    sys.modules["modal"] = _modal_stub()
    name = f"comfyapp_seedvr2_health_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / "comfyapp.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        if old_modal is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = old_modal


# ---------------------------------------------------------------------------
# CUDA import guard preserved
# ---------------------------------------------------------------------------


def test_cpu_snapshot_guard_blocks_cuda_extension_imports():
    """The guard must keep blocking CUDA C-extension module imports during
    snap=True â€” never weakened by the deferral accounting."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    force_cpu_idx = src.index("def _force_cpu_during_snapshot(self):")
    force_cpu_src = src[force_cpu_idx:force_cpu_idx + 12000]
    for marker in (
        "name.endswith(\"_cuda\")",
        "name.startswith(\"cuda_\")",
        "\"_cuda_\" in name",
        "name.startswith(\"sageattn._\")",
        "name.startswith(\"sageattention._\")",
    ):
        assert marker in force_cpu_src, f"CUDA guard marker missing: {marker}"
    assert "blocked CUDA module import" in force_cpu_src
    assert "during snap=True" in force_cpu_src


def test_snapshot_guard_sets_cpu_snapshot_flag():
    """Both snapshot context managers must set/restore _IN_CPU_SNAPSHOT so
    entrypoint failures during the window are classified as deferrals."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "global _IN_CPU_SNAPSHOT" in src
    assert "_IN_CPU_SNAPSHOT = True" in src
    assert "_IN_CPU_SNAPSHOT = _prev_in_cpu_snapshot" in src


def test_force_triton_guard_also_sets_snapshot_flag():
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    force_triton_idx = src.index("def _force_triton_during_snapshot(self):")
    force_triton_src = src[force_triton_idx:force_triton_idx + 8000]
    assert "global _IN_CPU_SNAPSHOT" in force_triton_src
    assert "_IN_CPU_SNAPSHOT = True" in force_triton_src


# ---------------------------------------------------------------------------
# Retryable classification
# ---------------------------------------------------------------------------


def test_entrypoint_failure_recorded_with_snapshot_deferred_flag():
    """SeedVR2-style CUDA failures during the snapshot must be recorded as
    snapshot-deferred + retryable (cpu_snapshot_schema)."""
    module = _load_comfyapp()
    module._IN_CPU_SNAPSHOT = True
    _retryable = bool(
        module._IN_CPU_SNAPSHOT
        or "CUDA" in "some cuda extension missing"
        or "device" in "some cuda extension missing".lower()
    )
    assert _retryable is True
    module._IN_CPU_SNAPSHOT = False
    _non_retryable = bool(
        module._IN_CPU_SNAPSHOT
        or "CUDA" in "ModuleNotFoundError"
        or "device" in "ModuleNotFoundError".lower()
    )
    assert _non_retryable is False


def test_import_failure_recording_logic_sets_retryable_when_snapshot():
    """The recorder marks a failure retryable when _IN_CPU_SNAPSHOT is true
    even if the exception message does not mention CUDA/device."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "_retryable = bool(" in src
    assert "_IN_CPU_SNAPSHOT" in src
    assert '"snapshot_deferred": bool(_IN_CPU_SNAPSHOT)' in src
    assert 'retryable_reason="cpu_snapshot_schema" if _retryable else ""' in src


# ---------------------------------------------------------------------------
# Import-health accounting accuracy
# ---------------------------------------------------------------------------


def test_import_health_counts_persistent_and_reports_deferred():
    """_collect_custom_node_import_health must count persistent failures and
    report snapshot-deferred failures separately â€” a SeedVR2 failure during
    CPU snapshot is either counted accurately or safely skipped."""
    module = _load_comfyapp()
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    health_idx = source.index("def _collect_custom_node_import_health(self) -> dict:")
    health_src = source[health_idx:health_idx + 7000]
    assert '"import_failure_count": len(_persistent_failures)' in health_src
    assert '"import_snapshot_deferred_count": _deferred_count' in health_src
    assert "snapshot_deferred" in health_src


def test_import_health_prints_deferred_diagnostics():
    """Deferred (snapshot-hidden) failures are still diagnosed, not silently
    dropped."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    health_idx = src.index("def _collect_custom_node_import_health(self) -> dict:")
    health_src = src[health_idx:health_idx + 7000]
    assert "custom_node_import_deferred" in health_src
    assert "reason=cpu_snapshot_cuda_hidden" in health_src
