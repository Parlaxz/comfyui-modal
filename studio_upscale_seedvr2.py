"""Explicit SeedVR2 upscale adapter (Phase 11, backend only).

Wraps the upstream SeedVR one-step video restorer
(https://github.com/ByteDance-Seed/SeedVR, Apache-2.0) as directly as
practical: a single still image is wrapped as a one-frame clip and passed
to the upstream SeedVR2 3B one-step entrypoint.  No inference is
reimplemented here.

SeedVR2 takes no scale parameter upstream — it takes target resolution
(``res_h``/``res_w``).  This adapter derives the target from the requested
*scale* and rounds each side to a multiple of 16, as required by the model.

Expected weights (~28GB): ``seedvr2_ema_3b.pth`` + ``ema_vae.pth``,
resolved from ``COMFYMODAL_SEEDVR2_WEIGHTS`` or the ``upscale_models``
folder.  GPU-only: CUDA is required and the adapter fails closed without
it.  Missing packages, weights, or CUDA produce ``SeedVR2Unavailable``
with an explicit ``SEEDVR2_UNAVAILABLE_*`` message — never a fake success,
never a silent download or substitute.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

SEEDVR2_METHOD = "seedvr2"

ERROR_CODE = "SEEDVR2_UNAVAILABLE"

DEFAULT_SEED = 666


class SeedVR2Unavailable(RuntimeError):
    """SeedVR2 cannot execute in this environment (fail-closed)."""

    error_code = ERROR_CODE


def seedvr2_target_size(width: int, height: int, scale: Any) -> tuple[int, int]:
    """Derive the SeedVR2 target (res_w, res_h) from *scale*.

    Each side is ``round(side * scale)`` snapped down to a multiple of 16
    (minimum 16).  Raises ``SeedVR2Unavailable`` for non-numeric scales or
    scales < 1.
    """
    try:
        factor = float(scale)
    except (TypeError, ValueError) as exc:
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: scale must be a number >= 1, "
            f"got {scale!r}"
        ) from exc
    if not (factor >= 1):
        raise SeedVR2Unavailable(
            f"SEEDVR2_UNAVAILABLE: scale must be >= 1, got {scale!r}"
        )
    target_w = max(16, (int(round(width * factor)) // 16) * 16)
    target_h = max(16, (int(round(height * factor)) // 16) * 16)
    return target_w, target_h


def _weights_dir() -> Path:
    override = (os.environ.get("COMFYMODAL_SEEDVR2_WEIGHTS") or "").strip()
    if override:
        return Path(override)
    try:
        import folder_paths  # type: ignore

        for candidate in folder_paths.get_folder_paths("upscale_models"):
            return Path(candidate) / "SeedVR2"
    except Exception:
        pass
    return Path("models") / "upscale_models" / "SeedVR2"


def _check_weights(weights_dir: Path) -> None:
    missing = [
        name
        for name in ("seedvr2_ema_3b.pth", "ema_vae.pth")
        if not (weights_dir / name).is_file()
    ]
    if missing:
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: weights not found at "
            f"{weights_dir} (missing: {', '.join(missing)}). "
            "Place the SeedVR2 3B bundle (seedvr2_ema_3b.pth + "
            "ema_vae.pth, ~28GB) there or set COMFYMODAL_SEEDVR2_WEIGHTS. "
            "Downloads are never performed automatically."
        )


def _require_cuda() -> None:
    try:
        import torch
    except Exception as exc:
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: torch is not installed; SeedVR2 "
            "requires torch with CUDA support"
        ) from exc
    if not torch.cuda.is_available():
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: CUDA is not available; SeedVR2 "
            "inference is GPU-only and has no CPU fallback"
        )


def upscale_seedvr2(image: Any, scale: Any, seed: int = DEFAULT_SEED) -> Any:
    """Upscale a PIL image by *scale* with SeedVR2 one-step inference.

    The target resolution is derived from *scale* via
    :func:`seedvr2_target_size` (multiples of 16); the image is wrapped as
    a one-frame clip for the upstream video model.  Returns a PIL image.
    Raises ``SeedVR2Unavailable`` (fail-closed) when CUDA, the upstream
    package, or the weights are missing.
    """
    from PIL import Image

    if not isinstance(image, Image.Image):
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: image must be a PIL image, "
            f"got {type(image).__name__}"
        )
    rgb = image.convert("RGB")
    target_w, target_h = seedvr2_target_size(rgb.width, rgb.height, scale)
    _require_cuda()
    weights_dir = _weights_dir()
    _check_weights(weights_dir)

    try:
        import seedvr  # type: ignore  # noqa: F401
    except Exception as exc:
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: upstream SeedVR modules not found. Clone "
            "https://github.com/ByteDance-Seed/SeedVR and make its "
            "seedvr2 one-step entrypoint importable. No inference was "
            "performed."
        ) from exc
    raise SeedVR2Unavailable(
        "SEEDVR2_UNAVAILABLE: installed seedvr package exposes no known "
        f"one-step entrypoint (target was res_w={target_w} "
        f"res_h={target_h} seed={int(seed)}); use an upstream SeedVR "
        "checkout with the SeedVR2 one-step API."
    )
