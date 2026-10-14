"""Explicit VOSR2 upscale adapter (Phase 11, backend only).

Wraps the upstream VOSR one-step upscaler (https://github.com/cswry/VOSR,
Apache-2.0) as directly as practical: the primary path shells out to the
upstream ``inference_vosr_onestep.py`` CLI from a local VOSR checkout, and a
best-effort import path covers an installed ``vosr`` package.  No inference
is reimplemented here.

Upstream CLI surface (verified against cswry/VOSR ``main``,
``inference_vosr_onestep.py`` — argparse ``main()``)::

    python inference_vosr_onestep.py -c <checkpoint-dir> \\
        -i <input-file-or-dir> -o <output-dir> -u <int-scale>

Required flags are ``-c/--checkpoint`` (directory holding ``args.json`` +
the ``*.safetensors`` weights — resolved here from ``COMFYMODAL_VOSR2_WEIGHTS``),
``-i/--input_image``, and ``-o/--output_dir``; ``-u/--upscale`` is
``type=int``, so the adapter rounds the requested factor to the nearest int
(``int(round(scale))``) at the CLI boundary.  Optional pass-through flags
(also verified upstream): ``--tile_size`` (``type=int``, ``0`` disables),
``--tile_overlap``, ``--vae_tile_size`` (default ``None`` = full-image VAE),
and ``--seed``.

Expected weights bundle (~7GB): ``args.json`` + ``ema_model.safetensors``
plus the bundled Qwen VAE and dinov2_vitl14 files, resolved from
``COMFYMODAL_VOSR2_WEIGHTS`` or the ``upscale_models`` folder.

DINOv2 PRE-WARM (offline operation): upstream ``load_dinov2`` calls
``torch.hub.load('facebookresearch/dinov2', 'dinov2_vitl14')`` (variant per
``args.enc_type``), which fetches from GitHub at inference time, and the
script pins its hub cache with
``torch.hub.set_dir('preset/ckpts/torch_cache')`` (checkout-relative).  To
run offline, pre-warm BEFORE the first call with one of:

* bake the hub cache into the image / checkout, e.g. run once with network
  so ``<repo>/preset/ckpts/torch_cache`` holds the ``facebookresearch_dinov2``
  checkout; or
* point ``COMFYMODAL_VOSR2_DINOV2`` (aliases: ``COMFYMODAL_VOSR2_DINOV2_PATH``,
  ``COMFYMODAL_VOSR2_TORCH_HUB``) at a directory holding a pre-warmed hub
  cache (a ``facebookresearch_dinov2`` / ``*dinov2*`` entry) or at the
  vendored dinov2 files from the HF bundle — the adapter best-effort
  symlinks/copies them into ``<repo>/preset/ckpts/torch_cache``; or
* set ``TORCH_HUB_DIR`` to a pre-warmed hub cache — the adapter stages it
  into the checkout-relative cache for the same reason.

The adapter itself NEVER downloads anything: when no staged cache, no knob
content, and no network to GitHub are available, it raises the existing
explicit ``VOSR2_UNAVAILABLE`` error (fail-closed) instead of attempting a
silent download.

CUDA/Modal is the realistic target: this adapter requires CUDA and fails
closed otherwise.  Missing packages, weights, or CUDA produce
``VOSR2Unavailable`` with an explicit ``VOSR2_UNAVAILABLE_*`` message —
never a fake success, never a silent download or substitute.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
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


# Upstream weight search order inside the ``-c`` checkpoint dir
# (inference_vosr_onestep.py: clean_weights/ → checkpoints/ → root,
# ema_model.safetensors first).  The staged Volume bundle keeps the HF
# layout (args.json at the root, weights under checkpoints/).
_WEIGHT_SEARCH_DIRS = ("clean_weights", "checkpoints", "")


def _find_weights(weights_dir: Path) -> Path | None:
    for sub in _WEIGHT_SEARCH_DIRS:
        candidate = weights_dir / sub / "ema_model.safetensors" if sub else weights_dir / "ema_model.safetensors"
        if candidate.is_file():
            return candidate
    return None


def _check_weights(weights_dir: Path) -> None:
    missing = []
    if not (weights_dir / "args.json").is_file():
        missing.append("args.json")
    if _find_weights(weights_dir) is None:
        missing.append("ema_model.safetensors")
    if missing:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: weights bundle not found at "
            f"{weights_dir} (missing: {', '.join(missing)}). "
            "Place the VOSR bundle (args.json + ema_model.safetensors "
            "under clean_weights/ or checkpoints/ + "
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


# Knobs pointing at vendored / pre-warmed dinov2 content (first hit wins).
_DINOV2_KNOBS = (
    "COMFYMODAL_VOSR2_DINOV2",
    "COMFYMODAL_VOSR2_DINOV2_PATH",
    "COMFYMODAL_VOSR2_TORCH_HUB",
)


def _has_dinov2_content(directory: Path) -> bool:
    try:
        for entry in directory.iterdir():
            name = entry.name.lower()
            if "dinov2" in name or name.startswith("facebookresearch"):
                return True
    except OSError:
        return False
    return False


def _try_stage_into_repo_cache(source: Path, repo_cache: Path) -> bool:
    """Best-effort symlink/copy of pre-warmed dinov2 content into the
    checkout-relative hub cache upstream pins via
    ``torch.hub.set_dir('preset/ckpts/torch_cache')``.  Never downloads;
    returns True when the repo cache now holds dinov2 content."""
    try:
        repo_cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        return _has_dinov2_content(repo_cache)
    if _has_dinov2_content(repo_cache):
        return True
    try:
        if source.is_dir():
            for entry in source.iterdir():
                name = entry.name.lower()
                if "dinov2" not in name and not name.startswith("facebookresearch"):
                    continue
                link = repo_cache / entry.name
                if link.exists():
                    continue
                try:
                    link.symlink_to(entry, target_is_directory=entry.is_dir())
                except OSError:
                    try:
                        if entry.is_dir():
                            shutil.copytree(entry, link)
                        else:
                            shutil.copy2(entry, link)
                    except OSError:
                        continue
        elif source.is_file() and "dinov2" in source.name.lower():
            link = repo_cache / source.name
            if not link.exists():
                try:
                    link.symlink_to(source)
                except OSError:
                    try:
                        shutil.copy2(source, link)
                    except OSError:
                        pass
    except OSError:
        pass
    # torch.hub companions inside a pre-warmed hub cache (HF torch_cache/
    # layout): trusted_list (torch>=2 hub trust) at the cache root and the
    # dinov2 weight .pth under checkpoints/ (torch.hub's
    # load_state_dict_from_url cache dir).  Stage both into the matching
    # repo-cache locations so torch.hub.load runs fully offline.
    try:
        trusted = source / "trusted_list"
        if trusted.is_file() and not (repo_cache / "trusted_list").exists():
            try:
                shutil.copy2(trusted, repo_cache / "trusted_list")
            except OSError:
                pass
        ckpt_src = source / "checkpoints"
        if ckpt_src.is_dir():
            ckpt_dst = repo_cache / "checkpoints"
            try:
                ckpt_dst.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            for entry in ckpt_src.iterdir():
                if not entry.is_file() or "dinov2" not in entry.name.lower():
                    continue
                link = ckpt_dst / entry.name
                if link.exists():
                    continue
                try:
                    link.symlink_to(entry)
                except OSError:
                    try:
                        shutil.copy2(entry, link)
                    except OSError:
                        continue
    except OSError:
        pass
    return _has_dinov2_content(repo_cache)


def _ensure_vae_staged(repo_root: Path, weights_dir: Path) -> None:
    """Stage the Qwen VAE dir onto the checkout-relative ``ae_path``.

    Staged ``args.json`` carries ``"ae_path": "preset/ckpts/Qwen-Image-vae-2d"``
    (checkout-relative; the CLI runs with ``cwd=repo_root``), while the
    operator bundle holds ``Qwen-Image-vae-2d/`` beside ``args.json``.
    Best-effort symlink (else copy); fail-closed when neither exists.
    """
    target = repo_root / "preset" / "ckpts" / "Qwen-Image-vae-2d"
    if target.is_dir() and any(target.iterdir()):
        return
    staged = weights_dir / "Qwen-Image-vae-2d"
    if not staged.is_dir():
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: Qwen VAE dir not found at "
            f"{staged} (checkout-relative preset/ckpts/Qwen-Image-vae-2d "
            "also absent). Place the bundled Qwen-Image-vae-2d dir beside "
            "args.json. Downloads are never performed automatically."
        )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.exists():
            return
        try:
            target.symlink_to(staged, target_is_directory=True)
        except OSError:
            shutil.copytree(staged, target)
    except OSError as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: cannot stage Qwen VAE dir into the "
            f"checkout at {target} ({exc}). No inference was performed."
        ) from exc


def _network_reachable(host: str = "github.com", port: int = 443, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ensure_dinov2_offline(repo_root: Path, weights_dir: Path) -> None:
    """Fail closed when upstream ``load_dinov2`` (``torch.hub.load`` of
    ``facebookresearch/dinov2``) can neither work offline nor fetch.

    Order: staged checkout cache → ``COMFYMODAL_VOSR2_*`` knob content →
    ``TORCH_HUB_DIR`` cache → vendored dinov2 files beside the weights →
    live network (upstream fetches itself) → explicit ``VOSR2_UNAVAILABLE``.
    This function never downloads; staging is symlink/copy of local files.
    """
    repo_cache = repo_root / "preset" / "ckpts" / "torch_cache"
    if _has_dinov2_content(repo_cache):
        return
    for knob in _DINOV2_KNOBS:
        candidate = (os.environ.get(knob) or "").strip()
        if not candidate:
            continue
        if _try_stage_into_repo_cache(Path(candidate), repo_cache):
            return
    hub_dir = (os.environ.get("TORCH_HUB_DIR") or "").strip()
    if hub_dir:
        if _try_stage_into_repo_cache(Path(hub_dir), repo_cache):
            return
    else:
        try:
            default_hub = Path.home() / ".cache" / "torch" / "hub"
        except Exception:
            default_hub = None
        if default_hub is not None and _try_stage_into_repo_cache(
            default_hub, repo_cache
        ):
            return
    if _has_dinov2_content(weights_dir):
        # Vendored dinov2 files shipped beside args.json in the HF bundle.
        if _try_stage_into_repo_cache(weights_dir, repo_cache):
            return
    if _network_reachable():
        # Upstream torch.hub.load can fetch itself; allow the CLI attempt
        # (its failure still surfaces as VOSR2_UNAVAILABLE below).
        return
    raise VOSR2Unavailable(
        "VOSR2_UNAVAILABLE: dinov2 weights are not pre-warmed and the "
        "network is unreachable, so upstream load_dinov2 "
        "(torch.hub.load('facebookresearch/dinov2', ...)) cannot run. "
        "Pre-warm offline with one of: run once with network access so "
        f"{repo_cache} holds the facebookresearch_dinov2 cache; or set "
        "COMFYMODAL_VOSR2_DINOV2 (aliases COMFYMODAL_VOSR2_DINOV2_PATH, "
        "COMFYMODAL_VOSR2_TORCH_HUB) to a pre-warmed hub cache / vendored "
        "dinov2 files; or set TORCH_HUB_DIR to a pre-warmed cache. "
        "Downloads are never performed automatically."
    )


def _run_cli(
    src_path: str,
    out_dir: str,
    weights_dir: Path,
    repo_root: Path,
    *,
    scale: float,
    tile_size: int,
    tile_overlap: int,
    vae_tile_size: int | None,
    seed: int,
) -> Path:
    """Invoke the real upstream CLI surface::

        python inference_vosr_onestep.py -c <weights> -i <src> -o <outdir>
            -u <int-scale> [--tile_size … --tile_overlap … --vae_tile_size …
            --seed … --force_rerun]

    Upstream ``-u/--upscale`` is ``type=int`` (argparse exits 2 on floats),
    so the float factor is rounded explicitly to the nearest int here.
    Upstream writes ``<outdir>/<input-stem>.png``; returns that path.
    Runs with ``cwd=repo_root`` so checkout-relative state
    (``preset/ckpts/torch_cache``, ``args.json`` lookup) resolves.
    """
    cli = repo_root / "inference_vosr_onestep.py"
    int_scale = int(round(scale))
    if int_scale < 1:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: rounded upscale factor must be >= 1, got {scale!r}"
        )
    cmd = [
        sys.executable or "python",
        str(cli),
        "-c",
        str(weights_dir),
        "-i",
        src_path,
        "-o",
        out_dir,
        "-u",
        str(int_scale),
        "--tile_size",
        str(tile_size),
        "--tile_overlap",
        str(tile_overlap),
        "--seed",
        str(seed),
        "--force_rerun",
    ]
    if vae_tile_size is not None:
        cmd += ["--vae_tile_size", str(vae_tile_size)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=str(repo_root),
        )
    except Exception as exc:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: failed to launch upstream VOSR CLI: {exc}"
        ) from exc
    expected = Path(out_dir) / (Path(src_path).stem + ".png")
    if proc.returncode != 0 or not expected.is_file():
        tail = ((proc.stderr or proc.stdout) or "")[-2000:]
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: upstream VOSR CLI failed "
            f"(exit={proc.returncode}): {tail}"
        )
    return expected


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
        _ensure_dinov2_offline(repo_root, weights_dir)
        _ensure_vae_staged(repo_root, weights_dir)
        with tempfile.TemporaryDirectory(prefix="vosr2-") as tmp:
            src = os.path.join(tmp, "input.png")
            out_dir = os.path.join(tmp, "out")
            os.makedirs(out_dir, exist_ok=True)
            rgb.save(src)
            dst = _run_cli(
                src,
                out_dir,
                weights_dir,
                repo_root,
                scale=factor,
                tile_size=int(tile_size),
                tile_overlap=int(tile_overlap),
                vae_tile_size=None if vae_tile_size is None else int(vae_tile_size),
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
