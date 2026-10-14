"""Explicit VOSR2 upscale adapter (Phase 11, backend only).

Wraps the upstream VOSR one-step upscaler (https://github.com/cswry/VOSR,
Apache-2.0) as directly as practical: the primary path shells out to the
upstream ``inference_vosr_onestep.py`` CLI from a local VOSR checkout, and a
best-effort import path covers an installed ``vosr`` package.  No inference
is reimplemented here.

Expected weights bundle (~7GB): ``args.json`` + ``ema_model.safetensors``
plus the bundled Qwen VAE and dinov2_vitl14 files, resolved from
``COMFYMODAL_VOSR2_WEIGHTS`` or the ``upscale_models`` folder.

CUDA/Modal is the realistic target: this adapter requires CUDA and fails
closed otherwise.  Missing packages, weights, or CUDA produce
``VOSR2Unavailable`` with an explicit ``VOSR2_UNAVAILABLE_*`` message —
never a fake success, never a silent download or substitute.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

VOSR2_METHOD = "vosr2"

ERROR_CODE = "VOSR2_UNAVAILABLE"

DEFAULT_TILE_SIZE = 512
DEFAULT_TILE_OVERLAP = 64
DEFAULT_VAE_TILE_SIZE = 256
DEFAULT_SEED = 0

_BUNDLE: dict[str, Any] = {}


class VOSR2Unavailable(RuntimeError):
    """VOSR2 cannot execute in this environment (fail-closed)."""

    error_code = ERROR_CODE


def validate_vosr2_scale(scale: Any) -> float:
    """Validate the requested upscale factor.  Returns the numeric scale."""
    try:
        value = float(scale)
    except (TypeError, ValueError) as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: scale must be a number >= 1, "
            f"got {scale!r}"
        ) from exc
    if not (value >= 1):
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: scale must be >= 1, got {scale!r}"
        )
    return value


def _weights_dir() -> Path:
    override = (os.environ.get("COMFYMODAL_VOSR2_WEIGHTS") or "").strip()
    if override:
        return Path(override)
    try:
        import folder_paths  # type: ignore

        for candidate in folder_paths.get_folder_paths("upscale_models"):
            return Path(candidate) / "VOSR"
    except Exception:
        pass
    return Path("models") / "upscale_models" / "VOSR"


def _check_weights(weights_dir: Path) -> None:
    missing = [
        name
        for name in ("args.json", "ema_model.safetensors")
        if not (weights_dir / name).is_file()
    ]
    if missing:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: weights bundle not found at "
            f"{weights_dir} (missing: {', '.join(missing)}). "
            "Place the VOSR bundle (args.json + ema_model.safetensors + "
            "Qwen VAE + dinov2_vitl14, ~7GB) there or set "
            "COMFYMODAL_VOSR2_WEIGHTS. Downloads are never performed "
            "automatically."
        )


def _require_cuda() -> None:
    try:
        import torch
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: torch is not installed; VOSR2 requires "
            "torch with CUDA support"
        ) from exc
    if not torch.cuda.is_available():
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: CUDA is not available; VOSR2 inference "
            "is GPU-only and has no CPU fallback"
        )


def _repo_root() -> Path | None:
    override = (os.environ.get("COMFYMODAL_VOSR2_REPO") or "").strip()
    if override and (Path(override) / "inference_vosr_onestep.py").is_file():
        return Path(override)
    return None


def _run_cli(
    src_path: str,
    dst_path: str,
    weights_dir: Path,
    repo_root: Path,
    *,
    scale: float,
    tile_size: int,
    tile_overlap: int,
    vae_tile_size: int,
    seed: int,
) -> None:
    cli = repo_root / "inference_vosr_onestep.py"
    cmd = [
        "python",
        str(cli),
        "-u",
        str(scale),
        "--input",
        src_path,
        "--output",
        dst_path,
        "--weights",
        str(weights_dir),
        "--tile_size",
        str(tile_size),
        "--tile_overlap",
        str(tile_overlap),
        "--vae_tile_size",
        str(vae_tile_size),
        "--seed",
        str(seed),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except Exception as exc:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: failed to launch upstream VOSR CLI: {exc}"
        ) from exc
    if proc.returncode != 0 or not Path(dst_path).is_file():
        tail = ((proc.stderr or proc.stdout) or "")[-2000:]
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: upstream VOSR CLI failed "
            f"(exit={proc.returncode}): {tail}"
        )


def upscale_vosr2(
    image: Any,
    scale: Any = 4,
    tile_size: int = DEFAULT_TILE_SIZE,
    tile_overlap: int = DEFAULT_TILE_OVERLAP,
    vae_tile_size: int = DEFAULT_VAE_TILE_SIZE,
    seed: int = DEFAULT_SEED,
) -> Any:
    """Upscale a PIL RGB image by *scale* with VOSR2 one-step inference.

    Returns a PIL image.  Raises ``VOSR2Unavailable`` (fail-closed) when
    CUDA, the upstream package/CLI checkout, or the weights bundle is
    missing.  The loaded weights bundle is cached per directory and reused.
    """
    from PIL import Image

    factor = validate_vosr2_scale(scale)
    if not isinstance(image, Image.Image):
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: image must be a PIL image, "
            f"got {type(image).__name__}"
        )
    rgb = image.convert("RGB")
    _require_cuda()
    weights_dir = _weights_dir()
    _check_weights(weights_dir)

    cache_key = str(weights_dir)
    if cache_key not in _BUNDLE:
        _BUNDLE[cache_key] = {"weights_dir": str(weights_dir)}
    _ = _BUNDLE[cache_key]

    repo_root = _repo_root()
    if repo_root is not None:
        with tempfile.TemporaryDirectory(prefix="vosr2-") as tmp:
            src = os.path.join(tmp, "input.png")
            dst = os.path.join(tmp, "output.png")
            rgb.save(src)
            _run_cli(
                src,
                dst,
                weights_dir,
                repo_root,
                scale=factor,
                tile_size=int(tile_size),
                tile_overlap=int(tile_overlap),
                vae_tile_size=int(vae_tile_size),
                seed=int(seed),
            )
            return Image.open(dst).convert("RGB")

    try:
        import vosr  # type: ignore  # noqa: F401
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: upstream VOSR modules not found. Clone "
            "https://github.com/cswry/VOSR and set COMFYMODAL_VOSR2_REPO "
            "to the checkout (for inference_vosr_onestep.py), or install "
            "the vosr package. No inference was performed."
        ) from exc
    raise VOSR2Unavailable(
        "VOSR2_UNAVAILABLE: installed vosr package exposes no known "
        "one-step entrypoint used by this adapter; use a VOSR checkout "
        "with inference_vosr_onestep.py via COMFYMODAL_VOSR2_REPO."
    )
