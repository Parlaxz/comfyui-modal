"""Dedicated experimental Phase-2 audit endpoint.

This module is not the production app and is not invoked by plan generation.
The parent operator owns any future deploy/run.  Its image is the existing
canonical CUDA image, not the stdlib-only source oracle image.
"""

from __future__ import annotations

from pathlib import Path

import modal

from comfymodal_runtime.phase2_audit_control import (
    CONTROL_APP_NAME,
    CPU,
    MEMORY_MB,
    MODELS_MOUNT,
    MODELS_VOLUME_NAME,
    run_phase2_audit_request as _run,
)

from comfymodal_runtime.modal_app import _reference_image

_ROOT = Path(__file__).resolve().parent
_image = _reference_image().add_local_file(
    str(_ROOT / "phase2_audit_modal.py"), "/root/phase2_audit_modal.py", copy=True
)
_models_volume = modal.Volume.from_name(MODELS_VOLUME_NAME, create_if_missing=False)
_models_mount = _models_volume.with_mount_options(read_only=True)
app = modal.App(CONTROL_APP_NAME, image=_image, include_source=False)


@app.function(
    image=_image,
    gpu="rtx-pro-6000",
    cpu=CPU,
    memory=MEMORY_MB,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={MODELS_MOUNT: _models_mount},
    env={
        "COMFYMODAL_PHASE2_AUDIT": "1",
        "COMFYMODAL_PHASE3_STATUS": "stopped",
        "COMFYMODAL_V2_CPU_REQUEST": str(CPU),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_phase2_audit(
    role: str,
    model_name: str,
    arm: str,
    qd: int,
    block_bytes: int,
    attempt_id: str = "",
) -> dict:
    return _run(role, model_name, arm, qd, block_bytes, attempt_id, models_root=MODELS_MOUNT)
