"""TRUE-COLD VOSR2 upscale adapter (Phase 11, backend only).

Thin IN-PROCESS adapter around the actual upstream VOSR one-step upscaler
(https://github.com/cswry/VOSR, Apache-2.0).  No inference math is
reimplemented here: every model class and every inference helper is imported
from the upstream checkout (``COMFYMODAL_VOSR2_REPO``, baked at
``/opt/upstream/VOSR`` on the Modal image) and called directly.  The old
per-request ``subprocess`` path (new interpreter + imports + model build +
weight load every call, 51-75s true-cold) is gone: there is no ``subprocess``,
no ``socket``, and no CLI argv anywhere in this module.

Upstream symbols used, exactly as defined in ``inference_vosr_onestep.py``
(``main``), ``vosr.py`` (``VOSR.sample_onestep``), ``tiled_vae.py``
(``encode_dispatch`` / ``decode_dispatch``), ``models/lightningdit.py``
(``LightningDiT``), ``models/light_decoder.py`` (``LightDecoder``),
``models/qwenimage_vae2d.py`` (``AutoencoderKLQwenImage2D.from_pretrained``)
or ``diffusers`` (``AutoencoderKL`` for ``ae_type == "sd2"``)::

    config (args.json) -> DiT/VAE/DINO class construction -> checkpoint
    reads -> CPU state -> .to(cuda) -> decode/preprocess -> DINO fwd ->
    VAE encode -> one-step DiT -> VAE decode -> color align -> PNG

STATIC vs PER-IMAGE split (the whole point of this file):

* STATIC INITIALIZATION — :func:`vosr2_static_init` (called from Modal
  ``startup(snap=True)``): ``args.json`` read, path resolution, upstream
  imports, class construction, CPU-resident state.  Snapshot-capturable:
  ZERO ``torch.cuda`` calls, ZERO network, ZERO subprocess, ZERO path
  re-scanning afterwards.  Quiescent on return (``eval``, no grad).
* PER-IMAGE EXECUTION — :func:`upscale_vosr2` (after
  :func:`vosr2_restore`): PNG decode, bicubic pre-upscale, DINO forward,
  VAE encode, one-step DiT, VAE decode, color align, PNG materialization.
  Uses only the cached static state — no imports, no config reads, no
  ``is_file`` scans, no network in the request path (fail closed on a
  missing pre-warmed DINOv2 cache).

SNAPSHOT STRATEGY SWITCH (operator knob, both kept — nothing else dead)::

    COMFYMODAL_VOSR2_SNAPSHOT_MODE = "lean" | "cpu_weights"  (default "lean")

* ``lean``: static init constructs model shells and records weight paths
  (no weight bytes read); :func:`vosr2_restore` re-reads weights from the
  Volume post-restore, then H2D.  Small snapshot, pays source reads
  post-restore.
* ``cpu_weights``: static init reads + materializes all weights CPU-resident
  (snapshot captures them); restore only does H2D.  Large snapshot, minimal
  post-restore work.

TILING RULE: inputs whose OUTPUT long side (``max(w, h) * round(scale)``) is
at most ``VOSR2_FULL_IMAGE_MAX_PX`` (2048) take the normal full-image path —
DiT tiling disabled (``tile_size = 0``), full-image VAE
(``vae_tile_size = None``) — so 400x400-class images never pay tiling
overhead.  Only genuinely large/extreme outputs honor the caller's
``tile_size`` / ``tile_overlap`` / ``vae_tile_size`` (upstream
``tiled_latent_inference`` + ``encode_dispatch`` / ``decode_dispatch``).
Upstream's own latent-fit fast path remains the final arbiter inside the
tiled kernels.

OFFLINE RULE: the adapter NEVER downloads.  Upstream ``load_dinov2`` needs a
pre-warmed ``torch.hub`` cache (baked source clone + Volume ``.pth`` /
``trusted_list`` staged into the checkout-relative
``preset/ckpts/torch_cache``); when no staged cache, knob content, or hub
cache exists, static init raises explicit ``VOSR2_UNAVAILABLE`` fail-closed.

CUDA/Modal is the realistic target: CUDA is required and the adapter fails
closed otherwise.  Missing packages, weights, or CUDA produce
``VOSR2Unavailable`` with an explicit ``VOSR2_UNAVAILABLE_*`` message —
never a fake success, never a silent download or substitute.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import types
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

VOSR2_METHOD = "vosr2"

ERROR_CODE = "VOSR2_UNAVAILABLE"

DEFAULT_TILE_SIZE = 512
DEFAULT_TILE_OVERLAP = 64
DEFAULT_VAE_TILE_SIZE = 256
DEFAULT_SEED = 0

# Snapshot strategy switch (see module docstring).  Read once per static
# init; unknown values fail closed so a typo can never silently pick a path.
VOSR2_SNAPSHOT_MODE_ENV = "COMFYMODAL_VOSR2_SNAPSHOT_MODE"
SNAPSHOT_MODE_LEAN = "lean"
SNAPSHOT_MODE_CPU_WEIGHTS = "cpu_weights"
VOSR2_SNAPSHOT_MODES = (SNAPSHOT_MODE_LEAN, SNAPSHOT_MODE_CPU_WEIGHTS)

# Tiling rule: outputs at/below this long side take the full-image path.
VOSR2_FULL_IMAGE_MAX_PX = 2048

# Upstream weight search order inside the checkpoint dir
# (inference_vosr_onestep.py: clean_weights/ -> checkpoints/ -> root,
# ema_model.safetensors first, model.safetensors fallback).  The staged
# Volume bundle keeps the HF layout (args.json at the root, weights under
# checkpoints/).
_WEIGHT_SEARCH_DIRS = ("clean_weights", "checkpoints", "")
_WEIGHT_SEARCH_NAMES = ("ema_model.safetensors", "model.safetensors")

# args.json keys with no bundle-independent default: upstream main() reads
# them straight off the merged namespace, so a bundle missing any of these
# fails closed here with the missing names instead of an AttributeError
# deep in model construction.
_REQUIRED_CONFIG_KEYS = (
    "ae_type",
    "enc_type",
    "layer_dinov2b_list",
    "dim",
    "depth",
    "num_heads",
    "mlp_ratio",
    "enc_dim",
    "encdim_ratio",
    "resolution",
    "patch_size",
    "time_dist",
    "cfg_ratio",
    "cfg_scale",
    "interp_type",
    "t_start",
    "t_end",
    "dinov2_size",
)

# Upstream CLI defaults (inference_vosr_onestep.py argparse) overlaid under
# the bundle's args.json so getattr() below never needs a fallback that
# could drift from upstream.
_CONFIG_DEFAULTS: dict[str, Any] = {
    "infer_steps": 1,
    "align_method": "wavelet",
    "tile_size": 0,
    "tile_overlap": 32,
    "vae_tile_size": None,
    "vae_tile_overlap": None,
    "posterior_mode": True,
    "process_size": 512,
    "auxiliary_time_cond": True,
    "use_qknorm": False,
    "use_swiglu": False,
    "use_rope": False,
    "use_rmsnorm": False,
    "wo_shift": False,
}

# Instrumented timing keys.  Load/restore keys and per-image keys are
# disjoint by construction (the only shared key is ``snapshot_mode``), so
# load + inference can never be lumped.
STARTUP_TIMING_KEYS = (
    "args_read_ms",
    "imports_ms",
    "dinov2_stage_ms",
    "vae_source_read_ms",
    "vae_cpu_materialize_ms",
    "dinov2_source_read_ms",
    "dinov2_cpu_materialize_ms",
    "dit_source_read_ms",
    "dit_cpu_materialize_ms",
    "light_decoder_source_read_ms",
    "light_decoder_cpu_materialize_ms",
    "startup_total_ms",
)
RESTORE_TIMING_KEYS = (
    "restore_entry_wall_unix_ns",
    "mutable_reset_ms",
    "cuda_init_ms",
    "dit_source_read_ms",
    "vae_source_read_ms",
    "dinov2_source_read_ms",
    "light_decoder_source_read_ms",
    "dit_cpu_materialize_ms",
    "vae_cpu_materialize_ms",
    "dinov2_cpu_materialize_ms",
    "dit_h2d_ms",
    "vae_h2d_ms",
    "dinov2_h2d_ms",
    "light_decoder_h2d_ms",
    "model_ready_ms",
    "restore_total_ms",
    "restore_exit_wall_unix_ns",
)
REQUEST_TIMING_KEYS = (
    "request_entry_wall_unix_ns",
    "seed_ms",
    "decode_ms",
    "dinov2_fwd_ms",
    "vae_encode_ms",
    "dit_onestep_ms",
    "vae_decode_ms",
    "color_correct_ms",
    "materialize_ms",
    "request_total_ms",
    "response_wall_unix_ns",
)

# Container state.  ``models`` holds CPU-resident executables after static
# init (cpu_weights mode) or constructed shells + recorded paths (lean mode)
# until restore() materializes them; ``restored`` flips once CUDA init + H2D
# have run exactly once per container.
_VOSR2_STATIC: dict[str, Any] = {
    "ready": False,
    "restored": False,
    "static_key": "",
    "snapshot_mode": SNAPSHOT_MODE_LEAN,
    "weights_dir": "",
    "repo_root": "",
    "config": None,
    "modules": {},
    "models": {},
    "weight_paths": {},
    "device": "cpu",
    "flexible_forward_set": False,
    "startup_timing": {},
    "restore_timing": {},
}

_LAST_TIMING: dict[str, Any] = {}


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


def snapshot_mode() -> str:
    """Resolve the snapshot weight strategy (fail closed on unknown values)."""
    raw = (os.environ.get(VOSR2_SNAPSHOT_MODE_ENV) or "").strip().lower()
    if not raw:
        return SNAPSHOT_MODE_LEAN
    if raw not in VOSR2_SNAPSHOT_MODES:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: unknown {VOSR2_SNAPSHOT_MODE_ENV}={raw!r}: "
            f"expected one of {list(VOSR2_SNAPSHOT_MODES)}"
        )
    return raw


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


def _repo_root() -> Path | None:
    override = (os.environ.get("COMFYMODAL_VOSR2_REPO") or "").strip()
    if override and (Path(override) / "inference_vosr_onestep.py").is_file():
        return Path(override)
    return None


def _find_weights(weights_dir: Path) -> Path | None:
    for sub in _WEIGHT_SEARCH_DIRS:
        for name in _WEIGHT_SEARCH_NAMES:
            candidate = weights_dir / sub / name if sub else weights_dir / name
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


# Knobs pointing at vendored / pre-warmed dinov2 content (first hit wins).
_DINOV2_KNOBS = (
    "COMFYMODAL_VOSR2_DINOV2",
    "COMFYMODAL_VOSR2_DINOV2_PATH",
    "COMFYMODAL_VOSR2_TORCH_HUB",
)

_QWEN_AE_DEFAULT = "preset/ckpts/Qwen-Image-vae-2d"
_SD2_AE_DEFAULT = "preset/ckpts/stable-diffusion-2-1-base"
_SD2_LIGHT_DECODER_DEFAULT = "preset/ckpts/sd21_lwdecoder.pth"


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
    checkout-relative hub cache.  File operations only — never downloads;
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
    # torch.hub companions inside a pre-warmed hub cache: trusted_list at the
    # cache root and the dinov2 weight .pth under checkpoints/.
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


def _ensure_dinov2_offline(repo_root: Path, weights_dir: Path) -> Path:
    """Stage (or verify) the pre-warmed DINOv2 hub cache.  File operations
    only — no network, no reachability probes.  Fails closed when upstream
    ``load_dinov2`` (``torch.hub.load`` of ``facebookresearch/dinov2``)
    could not run offline.  Returns the repo cache dir."""
    repo_cache = repo_root / "preset" / "ckpts" / "torch_cache"
    if _has_dinov2_content(repo_cache):
        return repo_cache
    for knob in _DINOV2_KNOBS:
        candidate = (os.environ.get(knob) or "").strip()
        if not candidate:
            continue
        if _try_stage_into_repo_cache(Path(candidate), repo_cache):
            return repo_cache
    hub_dir = (os.environ.get("TORCH_HUB_DIR") or "").strip()
    if hub_dir:
        if _try_stage_into_repo_cache(Path(hub_dir), repo_cache):
            return repo_cache
    else:
        try:
            default_hub = Path.home() / ".cache" / "torch" / "hub"
        except Exception:
            default_hub = None
        if default_hub is not None and _try_stage_into_repo_cache(
            default_hub, repo_cache
        ):
            return repo_cache
    if _has_dinov2_content(weights_dir):
        if _try_stage_into_repo_cache(weights_dir, repo_cache):
            return repo_cache
    raise VOSR2Unavailable(
        "VOSR2_UNAVAILABLE: dinov2 weights are not pre-warmed, so upstream "
        "load_dinov2 (a torch.hub fetch of facebookresearch/dinov2) cannot "
        "run offline and no download is ever attempted. Pre-warm with one of: "
        f"bake the facebookresearch_dinov2 cache into {repo_cache}; or set "
        "COMFYMODAL_VOSR2_DINOV2 (aliases COMFYMODAL_VOSR2_DINOV2_PATH, "
        "COMFYMODAL_VOSR2_TORCH_HUB) to a pre-warmed hub cache / vendored "
        "dinov2 files; or set TORCH_HUB_DIR to a pre-warmed cache. "
        "Downloads are never performed automatically."
    )


def _resolve_ae_path(config: Any, repo_root: Path, weights_dir: Path) -> Path:
    """Resolve the VAE directory to an absolute local path (no downloads,
    no checkout mutation — the caller passes it straight to
    ``from_pretrained``)."""
    ae_type = str(getattr(config, "ae_type", "qwen")).lower()
    raw = str(
        getattr(config, "ae_path", "")
        or (_QWEN_AE_DEFAULT if ae_type == "qwen" else _SD2_AE_DEFAULT)
    )
    candidate = Path(raw)
    if candidate.is_absolute():
        if candidate.is_dir():
            return candidate
    else:
        repo_copy = repo_root / raw
        try:
            if repo_copy.is_dir() and any(repo_copy.iterdir()):
                return repo_copy
        except OSError:
            pass
        vol_copy = weights_dir / candidate.name
        try:
            if vol_copy.is_dir():
                return vol_copy
        except OSError:
            pass
    raise VOSR2Unavailable(
        "VOSR2_UNAVAILABLE: VAE dir not found "
        f"(ae_path={raw!r}; checked {repo_root / raw} and "
        f"{weights_dir / Path(raw).name}). Place the bundled VAE dir "
        "(Qwen-Image-vae-2d for ae_type=qwen) beside args.json. Downloads "
        "are never performed automatically."
    )


def _resolve_light_decoder_path(
    config: Any, repo_root: Path, weights_dir: Path
) -> Path | None:
    """Resolve the sd2-only LightDecoder checkpoint (None for qwen)."""
    if str(getattr(config, "ae_type", "qwen")).lower() != "sd2":
        return None
    raw = str(
        getattr(config, "light_decoder_path", "") or _SD2_LIGHT_DECODER_DEFAULT
    )
    candidate = Path(raw)
    paths = (
        [candidate]
        if candidate.is_absolute()
        else [repo_root / raw, weights_dir / candidate.name]
    )
    for path in paths:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    raise VOSR2Unavailable(
        "VOSR2_UNAVAILABLE: LightDecoder checkpoint not found "
        f"({raw!r}). Place {Path(raw).name} beside args.json. Downloads "
        "are never performed automatically."
    )


def _read_config(weights_dir: Path) -> Any:
    """Read + validate the bundle args.json over the upstream CLI defaults."""
    try:
        with open(weights_dir / "args.json", "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: cannot read "
            f"{weights_dir / 'args.json'} ({exc}). No inference was performed."
        ) from exc
    except ValueError as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: invalid JSON in "
            f"{weights_dir / 'args.json'} ({exc}). No inference was performed."
        ) from exc
    if not isinstance(raw, dict):
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: invalid args.json "
            f"at {weights_dir / 'args.json'} (expected a JSON object). "
            "No inference was performed."
        )
    merged = dict(_CONFIG_DEFAULTS)
    merged.update(raw)
    # Timestep-embedding structure (mirrors upstream main): one-step models
    # carry auxiliary_time_cond=False; old distilled ckpts lack the key.
    if merged.get("auxiliary_time_cond", None) is None:
        merged["auxiliary_time_cond"] = True
    merged["auxiliary_time_cond"] = bool(merged["auxiliary_time_cond"])
    if merged.get("infer_steps", None) is None:
        merged["infer_steps"] = 1
    missing = [key for key in _REQUIRED_CONFIG_KEYS if key not in merged]
    if missing:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: args.json at "
            f"{weights_dir / 'args.json'} is missing required keys: "
            f"{', '.join(missing)}. No inference was performed."
        )
    return types.SimpleNamespace(**merged)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _static_key(weights_dir: Path, repo_root: Path, mode: str) -> str:
    return f"{weights_dir}\x00{repo_root}\x00{mode}"


def _reset_vosr2_state() -> None:
    """Test-only hook: drop all cached static/restored state and timings."""
    _VOSR2_STATIC.update(
        {
            "ready": False,
            "restored": False,
            "static_key": "",
            "snapshot_mode": SNAPSHOT_MODE_LEAN,
            "weights_dir": "",
            "repo_root": "",
            "config": None,
            "modules": {},
            "models": {},
            "weight_paths": {},
            "device": "cpu",
            "flexible_forward_set": False,
            "startup_timing": {},
            "restore_timing": {},
        }
    )
    _LAST_TIMING.clear()


def vosr2_is_static_ready() -> bool:
    """Return whether CPU static init has completed in this container."""
    return bool(_VOSR2_STATIC["ready"])


def vosr2_is_restored() -> bool:
    """Return whether post-snapshot restore (CUDA init + H2D) has run."""
    return bool(_VOSR2_STATIC["restored"])


def get_last_vosr2_timing() -> dict[str, Any]:
    """Return the last combined restore + per-image timing decomposition."""
    return dict(_LAST_TIMING)


def vosr2_static_init(
    snap: bool = True,
    *,
    weights_dir: Path | None = None,
    repo_root: Path | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """STATIC INITIALIZATION (Modal ``startup(snap=True)``).

    Imports, ``args.json``, path resolution, class construction, CPU state —
    snapshot-capturable.  Makes ZERO ``torch.cuda`` calls, performs ZERO
    network I/O and ZERO subprocess calls; every weight byte it reads is a
    local file read (``cpu_weights`` mode) or deferred to restore (``lean``
    mode).  Returns ``{"status": "ready", ...}`` for platform capture.
    Idempotent per (weights_dir, repo_root, mode).
    """
    # NOTE: this function body must stay free of torch.cuda touches — the
    # fast_unit contract asserts it via AST (snapshot capture happens after
    # this returns, before any CUDA context exists).
    if snap is not True:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: vosr2_static_init requires snap=True "
            "(CPU-only static initialization)"
        )
    t_total = time.perf_counter()
    timing: dict[str, Any] = {key: 0.0 for key in STARTUP_TIMING_KEYS}
    mode_value = mode or snapshot_mode()
    if mode_value not in VOSR2_SNAPSHOT_MODES:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: unknown snapshot mode {mode_value!r}: "
            f"expected one of {list(VOSR2_SNAPSHOT_MODES)}"
        )
    weights = weights_dir or _weights_dir()
    _check_weights(weights)
    repo = repo_root or _repo_root()
    if repo is None:
        diag = (os.environ.get("COMFYMODAL_VOSR2_REPO") or "").strip()
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: upstream VOSR checkout not found "
            f"(COMFYMODAL_VOSR2_REPO={diag or '<unset>'}). Clone "
            "https://github.com/cswry/VOSR and set COMFYMODAL_VOSR2_REPO "
            "to the checkout (expected inference_vosr_onestep.py). "
            "No inference was performed."
        )
    key = _static_key(weights, repo, mode_value)
    if _VOSR2_STATIC["ready"] and _VOSR2_STATIC["static_key"] == key:
        ready = {
            "status": "ready",
            "snapshot_mode": mode_value,
            "cached": True,
            "startup_timing": dict(_VOSR2_STATIC["startup_timing"]),
        }
        return ready
    _reset_vosr2_state()

    t0 = time.perf_counter()
    config = _read_config(weights)
    timing["args_read_ms"] = _ms(t0)

    # DINOv2 offline staging is file work (symlink/copy of pre-warmed
    # content) — static-time safe, request path never touches it.
    t0 = time.perf_counter()
    repo_cache = _ensure_dinov2_offline(repo, weights)
    timing["dinov2_stage_ms"] = _ms(t0)

    ae_path = _resolve_ae_path(config, repo, weights)
    dit_path = _find_weights(weights)
    assert dit_path is not None  # _check_weights passed
    light_decoder_path = _resolve_light_decoder_path(config, repo, weights)

    t0 = time.perf_counter()
    try:
        import torch
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: torch is not installed; VOSR2 requires "
            "torch with CUDA support"
        ) from exc
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    try:
        from models.lightningdit import LightningDiT
        from models.light_decoder import LightDecoder
        from vosr import VOSR
        from tiled_vae import encode_dispatch, decode_dispatch
        import inference_vosr_onestep as upstream
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: upstream VOSR modules not importable from "
            f"{repo} ({type(exc).__name__}: {exc}). Use a full VOSR "
            "checkout. No inference was performed."
        ) from exc
    try:
        from safetensors.torch import load_file
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: safetensors is not installed; VOSR2 "
            f"requires it to read {dit_path.name} ({exc})"
        ) from exc
    ae_type = str(getattr(config, "ae_type", "qwen")).lower()
    vae_loader: Any = None
    if ae_type == "qwen":
        try:
            from models.qwenimage_vae2d import AutoencoderKLQwenImage2D

            vae_loader = AutoencoderKLQwenImage2D.from_pretrained
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: Qwen VAE module not importable "
                f"({type(exc).__name__}: {exc}). No inference was performed."
            ) from exc
    elif ae_type == "sd2":
        try:
            from diffusers import AutoencoderKL

            vae_loader = AutoencoderKL.from_pretrained
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: diffusers AutoencoderKL not importable "
                f"({type(exc).__name__}: {exc}). No inference was performed."
            ) from exc
    else:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: unknown ae_type {ae_type!r} in args.json "
            "(expected 'qwen' or 'sd2'). No inference was performed."
        )
    timing["imports_ms"] = _ms(t0)

    # Point torch.hub at the absolute pre-warmed repo cache (CPU config, no
    # network) so upstream load_dinov2 runs fully offline.
    try:
        torch.hub.set_dir(str(repo_cache))
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: cannot configure torch.hub cache "
            f"({exc}). No inference was performed."
        ) from exc

    def _json_number(name: str, value: Any) -> Any:
        # Preserve args.json-native numeric types verbatim (upstream CLI
        # setattr-merges them): int stays int so dim arithmetic like
        # hidden_size * encdim_ratio keeps producing ints for torch.empty.
        # bool/str/None fail closed instead of silently coercing.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: args.json "
                f"{name!r} must be a number, got {value!r}. "
                "No inference was performed."
            )
        return value

    base_channel = 4 if ae_type == "sd2" else 16
    layer_list = list(getattr(config, "layer_dinov2b_list"))
    dit_kwargs = {
        "input_size": int(getattr(config, "resolution")) // 8,
        "patch_size": int(getattr(config, "patch_size")),
        "in_channels": 2 * base_channel,
        "out_channels": base_channel,
        "hidden_size": int(getattr(config, "dim")),
        "depth": int(getattr(config, "depth")),
        "num_heads": int(getattr(config, "num_heads")),
        "mlp_ratio": _json_number("mlp_ratio", getattr(config, "mlp_ratio")),
        "z_dims": int(getattr(config, "enc_dim")),
        "encdim_ratio": _json_number("encdim_ratio", getattr(config, "encdim_ratio")),
        "auxiliary_time_cond": bool(getattr(config, "auxiliary_time_cond")),
        "use_qknorm": bool(getattr(config, "use_qknorm")),
        "use_swiglu": bool(getattr(config, "use_swiglu")),
        "use_rope": bool(getattr(config, "use_rope")),
        "use_rmsnorm": bool(getattr(config, "use_rmsnorm")),
        "wo_shift": bool(getattr(config, "wo_shift")),
        "num_fused_layers": len(layer_list),
    }
    try:
        dit = LightningDiT(**dit_kwargs)
    except Exception as exc:
        import traceback as _tb

        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: failed to construct LightningDiT "
            f"({type(exc).__name__}: {exc}). kwargs={dit_kwargs!r} "
            f"trace={_tb.format_exc()[-2500:]} No inference was performed."
        ) from exc

    models: dict[str, Any] = {
        "dit": dit,
        "vae": None,
        "venc": None,
        "light_decoder": None,
        "vosr": None,
    }
    weight_paths = {
        "dit": str(dit_path),
        "ae_path": str(ae_path),
        "light_decoder": str(light_decoder_path) if light_decoder_path else "",
    }

    if mode_value == SNAPSHOT_MODE_CPU_WEIGHTS:
        # Weights resident: every byte is read + materialized on CPU now so
        # the platform snapshot captures them.
        t0 = time.perf_counter()
        try:
            vae = vae_loader(str(ae_path))
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to load VAE from "
                f"{ae_path} ({type(exc).__name__}: {exc}). "
                "No inference was performed."
            ) from exc
        timing["vae_source_read_ms"] = _ms(t0)
        t0 = time.perf_counter()
        try:
            vae.eval()
            for param in vae.parameters():
                param.requires_grad_(False)
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to freeze VAE "
                f"({type(exc).__name__}: {exc})."
            ) from exc
        timing["vae_cpu_materialize_ms"] = _ms(t0)
        models["vae"] = vae

        t0 = time.perf_counter()
        try:
            venc = upstream.load_dinov2(config, "cpu")
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to load dinov2 "
                f"({type(exc).__name__}: {exc}). No inference was performed."
            ) from exc
        timing["dinov2_source_read_ms"] = _ms(t0)
        t0 = time.perf_counter()
        try:
            venc.eval()
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to freeze dinov2 "
                f"({type(exc).__name__}: {exc})."
            ) from exc
        timing["dinov2_cpu_materialize_ms"] = _ms(t0)
        models["venc"] = venc

        t0 = time.perf_counter()
        try:
            if str(dit_path).endswith(".safetensors"):
                dit_state = load_file(str(dit_path))
            else:
                dit_state = torch.load(str(dit_path), map_location="cpu")
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to read DiT weights from "
                f"{dit_path} ({type(exc).__name__}: {exc}). "
                "No inference was performed."
            ) from exc
        timing["dit_source_read_ms"] = _ms(t0)
        t0 = time.perf_counter()
        try:
            dit.load_state_dict(dit_state, strict=False)
            dit.eval()
            for param in dit.parameters():
                param.requires_grad_(False)
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to materialize DiT weights "
                f"({type(exc).__name__}: {exc})."
            ) from exc
        timing["dit_cpu_materialize_ms"] = _ms(t0)

        if light_decoder_path is not None:
            t0 = time.perf_counter()
            try:
                raw_decoder = torch.load(str(light_decoder_path), map_location="cpu")
            except Exception as exc:
                raise VOSR2Unavailable(
                    "VOSR2_UNAVAILABLE: failed to read LightDecoder from "
                    f"{light_decoder_path} ({exc})."
                ) from exc
            timing["light_decoder_source_read_ms"] = _ms(t0)
            t0 = time.perf_counter()
            try:
                decoder_config = raw_decoder["config"]
                light_decoder = LightDecoder(
                    in_channels=decoder_config["in_channels"],
                    out_channels=decoder_config["out_channels"],
                    block_out_channels=tuple(decoder_config["block_out_channels"]),
                    layers_per_block=decoder_config["layers_per_block"],
                )
                light_decoder.load_state_dict(raw_decoder["model_state_dict"])
                light_decoder.eval()
                for param in light_decoder.parameters():
                    param.requires_grad_(False)
            except Exception as exc:
                raise VOSR2Unavailable(
                    "VOSR2_UNAVAILABLE: failed to materialize LightDecoder "
                    f"({type(exc).__name__}: {exc})."
                ) from exc
            timing["light_decoder_cpu_materialize_ms"] = _ms(t0)
            models["light_decoder"] = light_decoder

    # The VOSR sampler object carries no weights (flow-matching controller
    # over the DiT) — construct it on CPU in both modes.  The accelerator
    # stub is deliberately a plain CPU device, never the upstream helper
    # (which queries CUDA availability and must not run pre-snapshot).
    try:
        cpu_accelerator = types.SimpleNamespace(device=torch.device("cpu"))
        vosr_model = VOSR(
            time_dist=getattr(config, "time_dist"),
            cfg_ratio=float(getattr(config, "cfg_ratio")),
            cfg_scale=float(getattr(config, "cfg_scale")),
            interp_type=str(getattr(config, "interp_type")),
            accelerator=cpu_accelerator,
            t_start=float(getattr(config, "t_start")),
            t_end=float(getattr(config, "t_end")),
            args=config,
        )
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: failed to construct VOSR controller "
            f"({type(exc).__name__}: {exc}). No inference was performed."
        ) from exc
    models["vosr"] = vosr_model

    if mode_value == SNAPSHOT_MODE_CPU_WEIGHTS:
        for name in ("dit", "vae", "venc"):
            model = models.get(name)
            if model is not None:
                try:
                    model.eval()
                except Exception:
                    pass

    timing["startup_total_ms"] = _ms(t_total)
    _VOSR2_STATIC.update(
        {
            "ready": True,
            "restored": False,
            "static_key": key,
            "snapshot_mode": mode_value,
            "weights_dir": str(weights),
            "repo_root": str(repo),
            "config": config,
            "modules": {
                "torch": torch,
                "load_file": load_file,
                "LightningDiT": LightningDiT,
                "LightDecoder": LightDecoder,
                "VOSR": VOSR,
                "encode_dispatch": encode_dispatch,
                "decode_dispatch": decode_dispatch,
                "upstream": upstream,
                "vae_loader": vae_loader,
            },
            "models": models,
            "weight_paths": weight_paths,
            "device": "cpu",
            "startup_timing": dict(timing),
            "restore_timing": {},
        }
    )
    return {
        "status": "ready",
        "snapshot_mode": mode_value,
        "cached": False,
        "startup_timing": dict(timing),
    }


def vosr2_restore(snap: bool = False) -> dict[str, Any]:
    """POST-SNAPSHOT RESTORE (Modal ``restore(snap=False)``).

    Minimal by design: mutable-state reset, CUDA init exactly once, H2D
    materialization (reading weights from the Volume first in ``lean``
    mode), then request-ready.  Idempotent — repeat calls return the
    cached restore timing without re-reading or re-transferring.
    """
    if snap is not False:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: vosr2_restore requires snap=False "
            "(post-snapshot GPU materialization)"
        )
    if _VOSR2_STATIC["restored"]:
        return {
            "status": "ready",
            "snapshot_mode": _VOSR2_STATIC["snapshot_mode"],
            "cached": True,
            "restore_timing": dict(_VOSR2_STATIC["restore_timing"]),
        }
    if not _VOSR2_STATIC["ready"]:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: restore called before static init; "
            "run vosr2_static_init(snap=True) first. No inference was "
            "performed."
        )
    t_total = time.perf_counter()
    restore_entry_ns = time.time_ns()
    timing: dict[str, Any] = {key: 0.0 for key in RESTORE_TIMING_KEYS}
    timing["restore_entry_wall_unix_ns"] = restore_entry_ns

    modules = _VOSR2_STATIC["modules"]
    models = _VOSR2_STATIC["models"]
    config = _VOSR2_STATIC["config"]
    weight_paths = _VOSR2_STATIC["weight_paths"]
    torch = modules["torch"]
    load_file = modules["load_file"]
    upstream = modules["upstream"]
    mode_value = _VOSR2_STATIC["snapshot_mode"]

    # Mutable-state reset: drop stale distributed rendezvous env (mirror of
    # the upstream helper's first act) and re-assert quiescent eval mode.
    t0 = time.perf_counter()
    for var in (
        "WORLD_SIZE",
        "RANK",
        "LOCAL_RANK",
        "LOCAL_WORLD_SIZE",
        "GROUP_RANK",
        "ROLE_RANK",
        "MASTER_ADDR",
        "MASTER_PORT",
        "TORCHELASTIC_RUN_ID",
        "TORCHELASTIC_MAX_RESTARTS",
    ):
        os.environ.pop(var, None)
    for model in models.values():
        if model is not None:
            try:
                model.eval()
            except Exception:
                pass
    timing["mutable_reset_ms"] = _ms(t0)

    # CUDA init, exactly once per container.
    t0 = time.perf_counter()
    try:
        if not torch.cuda.is_available():
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: CUDA is not available; VOSR2 inference "
                "is GPU-only and has no CPU fallback"
            )
        torch.cuda.init()
    except VOSR2Unavailable:
        raise
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: CUDA init failed "
            f"({type(exc).__name__}: {exc})"
        ) from exc
    timing["cuda_init_ms"] = _ms(t0)
    device = torch.device("cuda")

    if mode_value == SNAPSHOT_MODE_LEAN:
        # Lean: weights are re-read from the Volume post-restore (the
        # snapshot holds shells + paths only), then materialized on CPU.
        t0 = time.perf_counter()
        try:
            vae = modules["vae_loader"](weight_paths["ae_path"])
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to load VAE from "
                f"{weight_paths['ae_path']} "
                f"({type(exc).__name__}: {exc}). No inference was performed."
            ) from exc
        timing["vae_source_read_ms"] = _ms(t0)
        t0 = time.perf_counter()
        try:
            vae.eval()
            for param in vae.parameters():
                param.requires_grad_(False)
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to freeze VAE "
                f"({type(exc).__name__}: {exc})."
            ) from exc
        timing["vae_cpu_materialize_ms"] = _ms(t0)
        models["vae"] = vae

        t0 = time.perf_counter()
        try:
            venc = upstream.load_dinov2(config, "cpu")
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to load dinov2 "
                f"({type(exc).__name__}: {exc}). No inference was performed."
            ) from exc
        timing["dinov2_source_read_ms"] = _ms(t0)
        t0 = time.perf_counter()
        try:
            venc.eval()
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to freeze dinov2 "
                f"({type(exc).__name__}: {exc})."
            ) from exc
        timing["dinov2_cpu_materialize_ms"] = _ms(t0)
        models["venc"] = venc

        dit_path = weight_paths["dit"]
        t0 = time.perf_counter()
        try:
            if str(dit_path).endswith(".safetensors"):
                dit_state = load_file(str(dit_path))
            else:
                dit_state = torch.load(str(dit_path), map_location="cpu")
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to read DiT weights from "
                f"{dit_path} ({type(exc).__name__}: {exc}). "
                "No inference was performed."
            ) from exc
        timing["dit_source_read_ms"] = _ms(t0)
        t0 = time.perf_counter()
        try:
            models["dit"].load_state_dict(dit_state, strict=False)
            models["dit"].eval()
            for param in models["dit"].parameters():
                param.requires_grad_(False)
        except Exception as exc:
            raise VOSR2Unavailable(
                "VOSR2_UNAVAILABLE: failed to materialize DiT weights "
                f"({type(exc).__name__}: {exc})."
            ) from exc
        timing["dit_cpu_materialize_ms"] = _ms(t0)

        if weight_paths.get("light_decoder"):
            t0 = time.perf_counter()
            try:
                raw_decoder = torch.load(
                    weight_paths["light_decoder"], map_location="cpu"
                )
            except Exception as exc:
                raise VOSR2Unavailable(
                    "VOSR2_UNAVAILABLE: failed to read LightDecoder from "
                    f"{weight_paths['light_decoder']} ({exc})."
                ) from exc
            timing["light_decoder_source_read_ms"] = _ms(t0)
            t0 = time.perf_counter()
            try:
                decoder_config = raw_decoder["config"]
                light_decoder = modules["LightDecoder"](
                    in_channels=decoder_config["in_channels"],
                    out_channels=decoder_config["out_channels"],
                    block_out_channels=tuple(decoder_config["block_out_channels"]),
                    layers_per_block=decoder_config["layers_per_block"],
                )
                light_decoder.load_state_dict(raw_decoder["model_state_dict"])
                light_decoder.eval()
                for param in light_decoder.parameters():
                    param.requires_grad_(False)
            except Exception as exc:
                raise VOSR2Unavailable(
                    "VOSR2_UNAVAILABLE: failed to materialize LightDecoder "
                    f"({type(exc).__name__}: {exc})."
                ) from exc
            timing["light_decoder_cpu_materialize_ms"] = _ms(t0)
            models["light_decoder"] = light_decoder

    # H2D materialization, one timed transfer per resident model.
    for name in ("dit", "vae", "venc", "light_decoder"):
        model = models.get(name)
        if model is None:
            continue
        t0 = time.perf_counter()
        try:
            model.to(device)
            model.eval()
        except Exception as exc:
            raise VOSR2Unavailable(
                f"VOSR2_UNAVAILABLE: failed to move {name} to CUDA "
                f"({type(exc).__name__}: {exc})"
            ) from exc
        timing[f"{name}_h2d_ms"] = _ms(t0)

    # Upstream main() rebinds the DiT forward to the resolution-flexible
    # variant after load — same line, applied once here.
    t0 = time.perf_counter()
    try:
        if not _VOSR2_STATIC["flexible_forward_set"]:
            models["dit"].forward = models["dit"].forward_flexible
            _VOSR2_STATIC["flexible_forward_set"] = True
        try:
            torch.cuda.synchronize()
        except Exception:
            pass
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: failed to finalize DiT for inference "
            f"({type(exc).__name__}: {exc})"
        ) from exc
    timing["model_ready_ms"] = _ms(t0)

    timing["restore_total_ms"] = _ms(t_total)
    timing["restore_exit_wall_unix_ns"] = time.time_ns()
    _VOSR2_STATIC.update(
        {
            "restored": True,
            "device": device,
            "restore_timing": dict(timing),
        }
    )
    return {
        "status": "ready",
        "snapshot_mode": mode_value,
        "cached": False,
        "restore_timing": dict(timing),
    }


def resolve_vosr2_tiling(
    width: int,
    height: int,
    scale: Any,
    tile_size: int = DEFAULT_TILE_SIZE,
    tile_overlap: int = DEFAULT_TILE_OVERLAP,
    vae_tile_size: int | None = DEFAULT_VAE_TILE_SIZE,
) -> dict[str, Any]:
    """Apply the tiling rule: outputs at/below ``VOSR2_FULL_IMAGE_MAX_PX``
    take the full-image path (DiT tiling off, full-image VAE); larger
    outputs honor the caller's tiling knobs."""
    try:
        int_scale = int(round(float(scale)))
    except (TypeError, ValueError) as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: scale must be a number >= 1, "
            f"got {scale!r}"
        ) from exc
    if int_scale < 1:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: rounded upscale factor must be >= 1, got {scale!r}"
        )
    try:
        out_long = max(int(width), int(height)) * int_scale
    except (TypeError, ValueError) as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: image dimensions must be integers, "
            f"got {(width, height)!r}"
        ) from exc
    if out_long <= VOSR2_FULL_IMAGE_MAX_PX:
        return {
            "tiling": "full",
            "tile_size": 0,
            "tile_overlap": 0,
            "vae_tile_size": None,
            "output_long_side": out_long,
        }
    return {
        "tiling": "tiled",
        "tile_size": int(tile_size),
        "tile_overlap": int(tile_overlap),
        "vae_tile_size": None if vae_tile_size is None else int(vae_tile_size),
        "output_long_side": out_long,
    }


def _pil_to_tensor(rgb: Any, torch: Any) -> Any:
    """PIL RGB -> ``[1, 3, H, W]`` float tensor in [-1, 1] (mirrors the
    upstream ``ToTensor() * 2 - 1`` without importing torchvision)."""
    arr = np.asarray(rgb, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0) * 2.0 - 1.0
    return tensor


def _tensor_to_pil(tensor: Any) -> Any:
    """Model output tensor in [-1, 1] -> PIL RGB (mirrors upstream
    ``ToPILImage()(t[0].cpu() * 0.5 + 0.5)`` without torchvision)."""
    shape = getattr(tensor, "shape", None)
    first = tensor[0] if shape is not None and len(shape) == 4 else tensor
    if hasattr(first, "detach"):
        arr = first.detach().cpu().numpy()
    else:
        arr = np.asarray(first)
    if arr.ndim == 3 and arr.shape[0] in (1, 3):
        arr = np.transpose(arr, (1, 2, 0))
    arr = np.clip(arr * 0.5 + 0.5, 0.0, 1.0)
    return Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8))


def upscale_vosr2(
    image: Any,
    scale: Any = 4,
    tile_size: int = DEFAULT_TILE_SIZE,
    tile_overlap: int = DEFAULT_TILE_OVERLAP,
    vae_tile_size: int = DEFAULT_VAE_TILE_SIZE,
    seed: int = DEFAULT_SEED,
) -> Any:
    """Upscale a PIL RGB image by *scale* with VOSR2 one-step inference.

    PER-IMAGE EXECUTION: decode, preprocess, DINO forward, VAE encode,
    one-step DiT, VAE decode, color align, materialize.  Uses only cached
    static state — no imports, no config reads, no path scans, no network.
    (First call in a process without ``startup``/``restore`` self-warms the
    local fallback path; the Modal path always arrives pre-restored.)

    Returns a PIL image.  Raises ``VOSR2Unavailable`` (fail-closed) when
    CUDA, the upstream checkout, or the weights bundle is missing.  The last
    combined restore + per-image timing decomposition is available via
    :func:`get_last_vosr2_timing` (additive keys only).
    """
    # NOTE: no imports, no path scans, no network in this body — the
    # fast_unit contract asserts the import-free property via AST.
    factor = validate_vosr2_scale(scale)
    if not isinstance(image, Image.Image):
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: image must be a PIL image, "
            f"got {type(image).__name__}"
        )
    rgb = image.convert("RGB")
    int_scale = int(round(factor))
    if int_scale < 1:
        raise VOSR2Unavailable(
            f"VOSR2_UNAVAILABLE: rounded upscale factor must be >= 1, got {scale!r}"
        )
    if not _VOSR2_STATIC["ready"]:
        vosr2_static_init()
    if not _VOSR2_STATIC["restored"]:
        vosr2_restore()

    t_total = time.perf_counter()
    timing: dict[str, Any] = {key: 0.0 for key in REQUEST_TIMING_KEYS}
    timing["request_entry_wall_unix_ns"] = time.time_ns()

    modules = _VOSR2_STATIC["modules"]
    models = _VOSR2_STATIC["models"]
    config = _VOSR2_STATIC["config"]
    torch = modules["torch"]
    upstream = modules["upstream"]
    encode_dispatch = modules["encode_dispatch"]
    decode_dispatch = modules["decode_dispatch"]
    device = _VOSR2_STATIC["device"]

    try:
        t0 = time.perf_counter()
        torch.manual_seed(int(seed))
        torch.cuda.manual_seed_all(int(seed))
        np.random.seed(int(seed))
        timing["seed_ms"] = _ms(t0)

        tiling = resolve_vosr2_tiling(
            rgb.width, rgb.height, int_scale, tile_size, tile_overlap, vae_tile_size
        )
        # Per-request execution namespace: a copy, so request knobs can
        # never mutate the cached static config.
        exec_args = types.SimpleNamespace(**vars(config))
        exec_args.upscale = int_scale
        exec_args.seed = int(seed)
        exec_args.tile_size = tiling["tile_size"]
        exec_args.tile_overlap = tiling["tile_overlap"]
        exec_args.vae_tile_size = tiling["vae_tile_size"]
        exec_args.vae_tile_overlap = None

        target_w, target_h = rgb.width * int_scale, rgb.height * int_scale
        t0 = time.perf_counter()
        pre_upscaled = rgb.resize((target_w, target_h), Image.BICUBIC)
        lq = _pil_to_tensor(pre_upscaled, torch).to(device)
        timing["decode_ms"] = _ms(t0)

        no_grad = torch.no_grad()
        with no_grad:
            if tiling["tile_size"] > 0:
                # Genuinely large output: upstream latent-space tiled DiT
                # (which pre-computes per-tile DINO features and blends in
                # latent space, then decodes once).  DINO/VAE sub-timings
                # stay 0.0 — the fused cost is reported under dit_onestep_ms
                # with tiling="tiled" so the two are never lumped.
                t0 = time.perf_counter()
                sr_tensor = upstream.tiled_latent_inference(
                    models["dit"],
                    models["vae"],
                    models["venc"],
                    lq,
                    exec_args,
                    device,
                    models["light_decoder"],
                )
                timing["dit_onestep_ms"] = _ms(t0)
            else:
                t0 = time.perf_counter()
                lq_latent, latents_mean, latents_std = encode_dispatch(
                    models["vae"], lq, exec_args, device
                )
                timing["vae_encode_ms"] = _ms(t0)
                t0 = time.perf_counter()
                venc_features = upstream.get_venc_features(
                    models["venc"], lq, exec_args
                )
                timing["dinov2_fwd_ms"] = _ms(t0)
                t0 = time.perf_counter()
                sr_latent = models["vosr"].sample_onestep(
                    models["dit"],
                    lq_latent,
                    n_steps=int(getattr(exec_args, "infer_steps", 1)),
                    venc_fea=venc_features,
                )
                timing["dit_onestep_ms"] = _ms(t0)
                t0 = time.perf_counter()
                sr_tensor = decode_dispatch(
                    models["vae"],
                    sr_latent,
                    exec_args,
                    latents_mean,
                    latents_std,
                    models["light_decoder"],
                )
                timing["vae_decode_ms"] = _ms(t0)

        t0 = time.perf_counter()
        sr_img = _tensor_to_pil(sr_tensor)
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        timing["materialize_ms"] = _ms(t0)

        t0 = time.perf_counter()
        align_method = str(getattr(exec_args, "align_method", "wavelet"))
        if align_method == "adain":
            out_img = upstream.adain_color_fix(sr_img, pre_upscaled)
        elif align_method == "wavelet":
            out_img = upstream.wavelet_color_fix(sr_img, pre_upscaled)
        elif align_method == "nofix":
            out_img = sr_img
        else:
            raise VOSR2Unavailable(
                f"VOSR2_UNAVAILABLE: unknown align_method {align_method!r} "
                "(expected 'wavelet', 'adain', or 'nofix')"
            )
        timing["color_correct_ms"] = _ms(t0)
    except VOSR2Unavailable:
        raise
    except Exception as exc:
        raise VOSR2Unavailable(
            "VOSR2_UNAVAILABLE: VOSR2 inference failed "
            f"({type(exc).__name__}: {exc})"
        ) from exc

    timing["request_total_ms"] = _ms(t_total)
    timing["response_wall_unix_ns"] = time.time_ns()
    combined = dict(_VOSR2_STATIC["restore_timing"])
    combined.update(timing)
    combined["snapshot_mode"] = _VOSR2_STATIC["snapshot_mode"]
    combined["tiling"] = tiling["tiling"]
    combined["tile_size_effective"] = tiling["tile_size"]
    combined["tile_overlap_effective"] = tiling["tile_overlap"]
    combined["vae_tile_size_effective"] = tiling["vae_tile_size"]
    combined["output_size"] = [out_img.width, out_img.height]
    _LAST_TIMING.clear()
    _LAST_TIMING.update(combined)
    return out_img
