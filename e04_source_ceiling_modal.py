"""Dedicated, non-Golden Modal endpoint for Experiment 06 source measurements."""

from __future__ import annotations

import os
from pathlib import Path

import modal


_ROOT = Path(__file__).resolve().parent
_APP_NAME = os.environ.get(
    "COMFYMODAL_E04_APP_NAME", "sept-unetclip-04-source-ceiling-oracle"
)
_MODELS_ROOT = "/root/models"
_VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")
_DECLARED_MODAL_CPU = 12

try:
    # This deliberately uses a small stdlib image: the arm performs only
    # positioned reads from the mounted checkpoint files.
    _image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu")
        .entrypoint([])
    )
    _image = _image.add_local_python_source("comfymodal_runtime", copy=True)
    _image = _image.add_local_file(
        str(_ROOT / "e04_source_ceiling_modal.py"),
        "/root/e04_source_ceiling_modal.py",
        copy=True,
    )
except Exception as exc:
    raise RuntimeError("Experiment 04 oracle image construction failed") from exc

_models_volume = modal.Volume.from_name(_VOLUME_NAME, create_if_missing=False)
_models_mount = _models_volume.with_mount_options(read_only=True)

app = modal.App(_APP_NAME, image=_image, include_source=False)


@app.function(
    image=_image,
    gpu=None,
    cpu=_DECLARED_MODAL_CPU,
    memory=8192,
    timeout=3600,
    retries=0,
    min_containers=0,
    single_use_containers=True,
    volumes={_MODELS_ROOT: _models_mount},
    env={
        "COMFYMODAL_E04_SOURCE_ORACLE": "1",
        # Keep the source artifact's declared Modal allocation distinct from
        # the runtime-shape CPU observed inside the container.
        "COMFYMODAL_E04_DECLARED_CPU": str(_DECLARED_MODAL_CPU),
        "COMFYMODAL_V2_CPU_REQUEST": str(_DECLARED_MODAL_CPU),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    },
)
def run_source_ceiling_oracle(
    role: str,
    model_name: str,
    arm: str,
    attempt_id: str = "",
    qd: int = 4,
    block_bytes: int = 256 * 1024 * 1024,
) -> dict:
    from comfymodal_runtime.source_ceiling_oracle import (
        run_source_ceiling_oracle as _run,
    )

    return _run(role, model_name, arm, attempt_id, qd, block_bytes)
