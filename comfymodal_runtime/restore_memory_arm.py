"""Experiment 6 (``restore_memory``): frozen deployment GPU VRAM capacity.

Baseline: ``comfyapp._restore_in_process_gpu_state`` calls
``comfy.model_management.get_total_memory(...)`` (a ``torch.cuda.mem_get_info``
round trip, ~236-339 ms) to learn the deployment GPU's TOTAL physical VRAM.
That value is immutable per physical GPU, so this arm freezes it once at
snapshot-construction time via ``nvidia-smi`` (NO CUDA init — a snapshot build
must never touch CUDA) and the restored container reads the frozen value
instead of re-querying CUDA during the restore path.

Semantic equality: on the same GPU, ``nvidia-smi`` ``memory.total`` equals
``torch.cuda.mem_get_info()[1]`` — both report the physical VRAM of the
deployment GPU, so assigning the frozen MiB value to
``comfy.model_management.total_vram`` is identical to the queried value.

Safe fallbacks (never raises, never touches CUDA):

* arm off (default)  -> ``apply_frozen_total_vram_or_none`` returns ``None``
  and the caller keeps the exact current query path (baseline);
* state dir unresolvable -> no freeze, no read;
* frozen file missing/corrupt -> ``None`` + one fallback log line.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid

from .v2_experiments import restore_total_vram_frozen_enabled

_FROZEN_FILENAME = "gpu_capacity_frozen.json"

# One-time per-process logs (freeze path + apply fallback detail).
_FREEZE_LOG_LOCK = threading.Lock()
_FREEZE_LOGGED = False
_FREEZE_STATUS_LOG_LOCK = threading.Lock()
_FREEZE_STATUS_LOGGED = False


def frozen_capacity_path() -> str:
    """Resolve the frozen GPU-capacity JSON path, or ``""`` when unresolvable.

    Resolution order:

      1. ``COMFYMODAL_V2_STATE_VOLUME_ROOT`` when set (state volume root);
      2. the directory part of ``COMFYMODAL_V2_RESTORE_STATE_FILE`` when it
         contains one (e.g. ``/mnt/comfymodal_runtime_state/restore_state.json``);
      3. ``""`` — unresolvable → no freeze, safe fallback.
    """
    state_dir = ""
    root = os.environ.get("COMFYMODAL_V2_STATE_VOLUME_ROOT", "").strip()
    if root:
        state_dir = root
    else:
        state_file = os.environ.get("COMFYMODAL_V2_RESTORE_STATE_FILE", "").strip()
        if state_file:
            parent = os.path.dirname(state_file)
            if parent:
                state_dir = parent
    if not state_dir:
        return ""
    return os.path.join(state_dir, _FROZEN_FILENAME)


def _freeze_log_once(line: str) -> None:
    """Print exactly one freeze-path log line per process.  Never raises."""
    global _FREEZE_LOGGED
    with _FREEZE_LOG_LOCK:
        if _FREEZE_LOGGED:
            return
        _FREEZE_LOGGED = True
    try:
        print(f"[restore_memory_arm] {line}", flush=True)
    except Exception:
        pass


def _freeze_status_log_once(line: str) -> None:
    """Print exactly one freeze-status line per process.  Never raises."""
    global _FREEZE_STATUS_LOGGED
    with _FREEZE_STATUS_LOG_LOCK:
        if _FREEZE_STATUS_LOGGED:
            return
        _FREEZE_STATUS_LOGGED = True
    try:
        print(f"[restore_memory_arm] {line}", flush=True)
    except Exception:
        pass


def maybe_freeze_snapshot_gpu_capacity() -> None:
    """Called ONCE at snapshot-construction startup (``snap=True``).

    Runs ``nvidia-smi --query-gpu=memory.total,name`` (NO CUDA init) with a
    10 s timeout, parses ``<mib>, <name>``, and atomically writes
    ``{"gpu_name", "total_vram_mib", "source", "captured_at"}`` to
    ``frozen_capacity_path()``.  On any failure logs
    ``[restore_memory_arm] freeze skipped: <reason>`` once and writes nothing.
    Never raises.
    """
    try:
        path = frozen_capacity_path()
        if not path:
            _freeze_log_once("freeze skipped: no_state_dir")
            return
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            _freeze_log_once(f"freeze skipped: nvidia_smi_rc={proc.returncode}")
            return
        first_line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
        if not first_line or "," not in first_line:
            _freeze_log_once("freeze skipped: unparsable_nvidia_smi_output")
            return
        _mib_part, _name_part = first_line.split(",", 1)
        total_vram_mib = int(_mib_part.strip())
        gpu_name = _name_part.strip()
        payload = {
            "gpu_name": gpu_name,
            "total_vram_mib": total_vram_mib,
            "source": "nvidia-smi",
            "captured_at": time.time(),
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, sort_keys=True, separators=(",", ":"))
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        _freeze_log_once(
            f"freeze stored source=nvidia-smi vram_mib={total_vram_mib} "
            f"gpu_name={gpu_name!r}"
        )
        _freeze_status_log_once(
            f"freeze status=ok path={path} gpu_name={gpu_name} "
            f"vram_mib={total_vram_mib} file_written=1"
        )
    except Exception as exc:
        _freeze_log_once(f"freeze skipped: {type(exc).__name__}:{exc}"[:160])


def apply_frozen_total_vram_or_none() -> float | None:
    """Return the frozen deployment total VRAM (MiB), else ``None`` (baseline).

    When ``restore_total_vram_frozen_enabled()`` is False this returns
    ``None`` immediately — the caller keeps the exact current query path.
    Otherwise the frozen file is read; missing/corrupt -> ``None`` + one
    ``[v2.experiment] restore_memory arm=optimized effective=baseline
    fallback=no_frozen_capacity`` log; valid -> one ``[v2.experiment]``
    source log + ``float(n)``.  Never raises, never touches CUDA.
    """
    if not restore_total_vram_frozen_enabled():
        return None
    path = ""
    try:
        path = frozen_capacity_path()
        if not path or not os.path.isfile(path):
            _apply_fallback_log_once()
            _apply_frozen_log_once(
                f"requested=optimized frozen_capacity_path={path} "
                "frozen_capacity_present=0 effective=baseline "
                "fallback=no_frozen_capacity"
            )
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            _apply_fallback_log_once()
            _apply_frozen_log_once(
                f"requested=optimized frozen_capacity_path={path} "
                "frozen_capacity_present=0 effective=baseline "
                "fallback=no_frozen_capacity"
            )
            return None
        total_mib = int(data.get("total_vram_mib", -1))
        if total_mib <= 0:
            _apply_fallback_log_once()
            _apply_frozen_log_once(
                f"requested=optimized frozen_capacity_path={path} "
                "frozen_capacity_present=0 effective=baseline "
                "fallback=no_frozen_capacity"
            )
            return None
        try:
            print(
                f"[v2.experiment] restore_memory arm=optimized "
                f"source=snapshot_frozen vram_mib={total_mib}",
                flush=True,
            )
        except Exception:
            pass
        _apply_frozen_log_once(
            f"requested=optimized frozen_capacity_path={path} "
            "frozen_capacity_present=1 effective=optimized "
            "fallback=none frozen_capacity_used=1"
        )
        return float(total_mib)
    except Exception:
        _apply_fallback_log_once()
        _apply_frozen_log_once(
            f"requested=optimized frozen_capacity_path={path} "
            "frozen_capacity_present=0 effective=baseline "
            "fallback=no_frozen_capacity"
        )
        return None


_APPLY_FALLBACK_LOGGED = False
_APPLY_FALLBACK_LOCK = threading.Lock()


def _apply_fallback_log_once() -> None:
    """Log the no-frozen-capacity fallback once per process.  Never raises."""
    global _APPLY_FALLBACK_LOGGED
    with _APPLY_FALLBACK_LOCK:
        if _APPLY_FALLBACK_LOGGED:
            return
        _APPLY_FALLBACK_LOGGED = True
    try:
        print(
            "[v2.experiment] restore_memory arm=optimized "
            "effective=baseline fallback=no_frozen_capacity",
            flush=True,
        )
    except Exception:
        pass


_APPLY_FROZEN_LOGGED = False
_APPLY_FROZEN_LOCK = threading.Lock()


def _apply_frozen_log_once(line: str) -> None:
    """Log one compact restore-memory-arm diagnostic per process.  Never raises."""
    global _APPLY_FROZEN_LOGGED
    with _APPLY_FROZEN_LOCK:
        if _APPLY_FROZEN_LOGGED:
            return
        _APPLY_FROZEN_LOGGED = True
    try:
        print(f"[v2.restore_memory_arm] {line}", flush=True)
    except Exception:
        pass
