"""Explicit SeedVR2 upscale adapter (Phase 11, backend only).

Wraps the upstream SeedVR one-step video restorer
(https://github.com/ByteDance-Seed/SeedVR, Apache-2.0) as directly as
practical: a single still image is staged as a one-frame input and passed
to the upstream SeedVR2 3B one-step CLI
``projects/inference_seedvr2_3b.py`` via subprocess — the repository
exposes NO importable ``seedvr`` package, so the network call executes
upstream code directly.  No inference is reimplemented here.

Upstream CLI surface (verified against ByteDance-Seed/SeedVR ``main``,
``projects/inference_seedvr2_3b.py`` — argparse ``__main__``)::

    python projects/inference_seedvr2_3b.py --video_path <input-dir>
        --output_dir <output-dir> --res_h <int> --res_w <int>
        [--seed <int> --sp_size 1 --out_fps <float>]

Hardcoded cwd-relative paths (no flags; the script MUST run with
``cwd`` set to the SeedVR checkout root): ``./configs_3b/main.yaml``
(runner config), ``./ckpts/seedvr2_ema_3b.pth`` (DiT checkpoint),
``pos_emb.pt`` / ``neg_emb.pt`` (pre-extracted text embeds, loaded from the
checkout cwd).  The adapter stages the operator weights into ``./ckpts/``
(best-effort symlink of ``seedvr2_ema_3b.pth`` from ``weights_dir`` when the
checkout copy is absent and the checkout is writable) and otherwise fails
closed with an explicit staging message.

SeedVR2 takes no scale parameter upstream — it takes target resolution
(``res_h``/``res_w``).  This adapter derives the target from the requested
*scale* and rounds each side to a multiple of 16, as required by the model.

Checkout resolution: ``COMFYMODAL_SEEDVR2_REPO`` (alias
``COMFYMODAL_SEEDVR_REPO``) must point at a SeedVR checkout containing
``projects/inference_seedvr2_3b.py``.

Expected weights (~28GB): ``seedvr2_ema_3b.pth`` + ``ema_vae.pth``,
resolved from ``COMFYMODAL_SEEDVR2_WEIGHTS`` or the ``upscale_models``
folder.  GPU-only: CUDA is required and the adapter fails closed without
it.  Missing packages, weights, or CUDA produce ``SeedVR2Unavailable``
with an explicit ``SEEDVR2_UNAVAILABLE_*`` message — never a fake success,
never a silent download or substitute.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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


def _repo_root() -> Path | None:
    for knob in ("COMFYMODAL_SEEDVR2_REPO", "COMFYMODAL_SEEDVR_REPO"):
        override = (os.environ.get(knob) or "").strip()
        if override and (
            Path(override) / "projects" / "inference_seedvr2_3b.py"
        ).is_file():
            return Path(override)
    return None


def _stage_file(staged: Path, dest: Path, what: str) -> None:
    """Best-effort symlink (else copy) of an operator weight into the
    checkout.  Raises ``SeedVR2Unavailable`` when the source is absent or
    the checkout is not writable."""
    if dest.is_file():
        return
    if not staged.is_file():
        raise SeedVR2Unavailable(
            f"SEEDVR2_UNAVAILABLE: {what} not found at {dest} (upstream "
            f"hardcodes ./{dest.name} with no override flag) and no staged "
            f"copy was available in {staged.parent}. Place {staged.name} in "
            "either location. Downloads are never performed automatically."
        )
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.symlink_to(staged)
        except OSError:
            shutil.copy2(staged, dest)
    except OSError as exc:
        raise SeedVR2Unavailable(
            f"SEEDVR2_UNAVAILABLE: cannot stage {staged.name} into the "
            f"checkout at {dest} ({exc}); place it there or make the "
            "checkout writable. No inference was performed."
        ) from exc
    if not dest.is_file():
        raise SeedVR2Unavailable(
            f"SEEDVR2_UNAVAILABLE: checkpoint not found at {dest} "
            f"(upstream hardcodes ./{dest.name} with no override flag) and "
            f"no staged copy was available in {staged.parent}. Place "
            f"{staged.name} in either location. Downloads are never "
            "performed automatically."
        )


def _ensure_staged(repo_root: Path, weights_dir: Path) -> None:
    """Stage operator weights/configs onto the checkout's hardcoded
    cwd-relative paths (best-effort symlink, read-only safe).

    Upstream hardcodes ``./configs_3b/main.yaml``,
    ``./ckpts/seedvr2_ema_3b.pth``, ``./ckpts/ema_vae.pth`` (via
    ``vae.checkpoint`` in ``configs_3b/main.yaml``), and ``pos_emb.pt`` /
    ``neg_emb.pt`` with no override flags, so the CLI must run with
    ``cwd=repo_root`` and those files must exist there.  When a checkout
    copy is absent but the operator weights dir holds it, symlink (or copy)
    it in; anything still missing raises explicit ``SEEDVR2_UNAVAILABLE``
    (fail-closed).
    """
    script = repo_root / "projects" / "inference_seedvr2_3b.py"
    if not script.is_file():
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: upstream SeedVR checkout not found at "
            f"{repo_root} (missing projects/inference_seedvr2_3b.py). Clone "
            "https://github.com/ByteDance-Seed/SeedVR and set "
            "COMFYMODAL_SEEDVR2_REPO to the checkout. No inference was "
            "performed."
        )
    if not (repo_root / "configs_3b" / "main.yaml").is_file():
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: upstream config not found at "
            f"{repo_root / 'configs_3b' / 'main.yaml'} (hardcoded relative "
            "path ./configs_3b/main.yaml with no override flag). Use a full "
            "SeedVR checkout. No inference was performed."
        )
    _stage_file(
        weights_dir / "seedvr2_ema_3b.pth",
        repo_root / "ckpts" / "seedvr2_ema_3b.pth",
        "DiT checkpoint",
    )
    _stage_file(
        weights_dir / "ema_vae.pth",
        repo_root / "ckpts" / "ema_vae.pth",
        "VAE checkpoint (configs_3b/main.yaml vae.checkpoint)",
    )
    for emb in ("pos_emb.pt", "neg_emb.pt"):
        _stage_file(
            weights_dir / emb,
            repo_root / emb,
            "upstream text-embed file",
        )


def _run_cli(
    repo_root: Path,
    video_dir: str,
    out_dir: str,
    *,
    res_w: int,
    res_h: int,
    seed: int,
) -> Path:
    """Drive the real upstream SeedVR2 CLI with ``cwd`` set to the checkout
    so its hardcoded relative paths resolve::

        python projects/inference_seedvr2_3b.py --video_path <dir>
            --output_dir <dir> --res_h H --res_w W --seed S

    Returns the output image path (input basename preserved by upstream).
    """
    script = repo_root / "projects" / "inference_seedvr2_3b.py"
    cmd = [
        sys.executable or "python",
        str(script),
        "--video_path",
        video_dir,
        "--output_dir",
        out_dir,
        "--res_h",
        str(res_h),
        "--res_w",
        str(res_w),
        "--seed",
        str(seed),
    ]
    try:
        # Upstream expects torchrun-provided rendezvous env for its
        # single-process init_process_group (init_torch → env:// store).
        # Provide the single-rank equivalent explicitly; port is picked
        # free at call time so concurrent calls in one container cannot
        # collide.  No upstream code is modified.
        import socket as _socket

        _env = dict(os.environ)
        _env.setdefault("MASTER_ADDR", "127.0.0.1")
        _env.setdefault("RANK", "0")
        _env.setdefault("WORLD_SIZE", "1")
        if not _env.get("MASTER_PORT"):
            with _socket.socket() as _s:
                _s.bind(("127.0.0.1", 0))
                _env["MASTER_PORT"] = str(_s.getsockname()[1])
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=str(repo_root),
            env=_env,
        )
    except Exception as exc:
        raise SeedVR2Unavailable(
            f"SEEDVR2_UNAVAILABLE: failed to launch upstream SeedVR2 CLI: {exc}"
        ) from exc
    produced = sorted(
        Path(out_dir).glob("*.png"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
    )
    expected_names = {p.name for p in Path(video_dir).glob("*")}
    expected = None
    for candidate in produced:
        if candidate.name in expected_names or candidate.suffix.lower() == ".png":
            expected = candidate
            break
    if proc.returncode != 0 or expected is None or not expected.is_file():
        tail = ((proc.stderr or proc.stdout) or "")[-2000:]
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: upstream SeedVR2 CLI failed "
            f"(exit={proc.returncode}): {tail}"
        )
    return expected


def upscale_seedvr2(image: Any, scale: Any, seed: int = DEFAULT_SEED) -> Any:
    """Upscale a PIL image by *scale* with SeedVR2 one-step inference.

    The target resolution is derived from *scale* via
    :func:`seedvr2_target_size` (multiples of 16); the image is staged as a
    one-frame input for the upstream video CLI, which runs with
    ``cwd`` set to the SeedVR checkout so its hardcoded relative paths
    (``./configs_3b/main.yaml``, ``./ckpts/seedvr2_ema_3b.pth``,
    ``pos_emb.pt`` / ``neg_emb.pt``) resolve.  Returns a PIL image.
    Raises ``SeedVR2Unavailable`` (fail-closed) when CUDA, the upstream
    checkout, or the weights are missing.
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

    repo_root = _repo_root()
    if repo_root is None:
        # Diagnostic detail is intentional: this is the only signal the
        # operator gets from inside the container about knob vs checkout.
        diag = []
        for knob in ("COMFYMODAL_SEEDVR2_REPO", "COMFYMODAL_SEEDVR_REPO"):
            val = (os.environ.get(knob) or "").strip()
            if not val:
                diag.append(f"{knob}=<unset>")
                continue
            probe = Path(val) / "projects" / "inference_seedvr2_3b.py"
            try:
                exists = Path(val).is_dir()
                has_script = probe.is_file()
            except OSError:
                exists, has_script = False, False
            diag.append(f"{knob}={val} dir={exists} script={has_script}")
        raise SeedVR2Unavailable(
            "SEEDVR2_UNAVAILABLE: upstream SeedVR checkout not found "
            f"({'; '.join(diag)}). Clone "
            "https://github.com/ByteDance-Seed/SeedVR and set "
            "COMFYMODAL_SEEDVR2_REPO to the checkout root (expected "
            "projects/inference_seedvr2_3b.py with cwd-relative "
            "./configs_3b/main.yaml, ./ckpts/seedvr2_ema_3b.pth, pos_emb.pt "
            "/ neg_emb.pt). There is no importable seedvr package; the "
            "adapter drives the upstream CLI directly. No inference was "
            "performed."
        )
    _ensure_staged(repo_root, weights_dir)
    with tempfile.TemporaryDirectory(prefix="seedvr2-in-") as tmp_in, \
        tempfile.TemporaryDirectory(prefix="seedvr2-out-") as tmp_out:
        src_name = "input.png"
        rgb.save(os.path.join(tmp_in, src_name))
        dst = _run_cli(
            repo_root,
            tmp_in,
            tmp_out,
            res_w=target_w,
            res_h=target_h,
            seed=int(seed),
        )
        return Image.open(dst).convert("RGB")
