"""Phase 11 upscale dispatch (backend only): explicit VOSR2 / SeedVR2.

Exactly two methods, no Auto, no generic framework, no registry.  The
stored workflow is never mutated: an upscale is a derived result that
carries the source asset identity in its meta.

Request validation, Modal-vs-local dispatch, and result materialization
live here so the ``POST /comfymodal/studio/upscale`` route stays thin.
Heavy inference runs on Modal whenever a Modal workspace is active; the
local adapter path is a fail-closed fallback that raises explicit
``*_UNAVAILABLE`` errors when CUDA, upstream modules, or weights are
missing.  Generate/Edit paths are untouched.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

UPSCALE_METHODS = ("vosr2", "seedvr2")

# Remote entrypoint looked up on the config-owned Modal app when a Modal
# workspace is active.  Deployments are config-owned (v2ctl); this module
# never deploys anything, it only calls the already-deployed single
# ``studio_upscale`` entrypoint (method travels explicitly in the payload)
# and fails closed when it is absent.
UPSCALE_MODAL_APP_ENV = "COMFYMODAL_UPSCALE_APP_NAME"
UPSCALE_REMOTE_FUNCTION = "studio_upscale"
UPSCALE_MODAL_TIMEOUT_S = 1800.0


class UpscaleRequestError(ValueError):
    """A 400-class upscale request problem."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.http_status = 400


class UpscaleRunError(RuntimeError):
    """A non-400 upscale failure (dependency/Modal/unexpected)."""

    def __init__(
        self, error_code: str, message: str, http_status: int = 500
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status


def parse_upscale_request(body: Any) -> dict[str, Any]:
    """Validate the upscale JSON body.  Returns normalized params.

    Raises ``UpscaleRequestError`` (400) for missing fields, unknown
    methods — including ``"auto"`` — and out-of-range options.
    """
    if not isinstance(body, dict):
        raise UpscaleRequestError(
            "UPSCALE_BAD_REQUEST", "expected a JSON object body"
        )
    raw_method = body.get("method", "")
    method = str(raw_method or "").strip().lower()
    if not method:
        raise UpscaleRequestError(
            "UPSCALE_METHOD_REQUIRED",
            "method is required: exactly 'vosr2' or 'seedvr2'",
        )
    if method == "auto" or method not in UPSCALE_METHODS:
        raise UpscaleRequestError(
            "UPSCALE_UNKNOWN_METHOD",
            f"unknown upscale method {raw_method!r}: expected exactly "
            "'vosr2' or 'seedvr2' (no Auto)",
        )
    source_image = str(body.get("source_image") or "").strip()
    if not source_image:
        raise UpscaleRequestError(
            "UPSCALE_SOURCE_REQUIRED",
            "source_image is required (a ComfyUI input filename)",
        )
    if (
        "/" in source_image
        or "\\" in source_image
        or ".." in source_image
    ):
        raise UpscaleRequestError(
            "UPSCALE_BAD_SOURCE",
            f"refusing unsafe image reference {source_image!r}",
        )
    scale = body.get("scale", 4)
    try:
        scale_value = float(scale)
    except (TypeError, ValueError) as exc:
        raise UpscaleRequestError(
            "UPSCALE_BAD_SCALE",
            f"scale must be a number >= 1, got {scale!r}",
        ) from exc
    if not (scale_value >= 1):
        raise UpscaleRequestError(
            "UPSCALE_BAD_SCALE", f"scale must be >= 1, got {scale!r}"
        )

    def _opt_int(name: str, default: int, lo: int, hi: int) -> int:
        raw = body.get(name, default)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise UpscaleRequestError(
                "UPSCALE_BAD_OPTION",
                f"{name} must be an integer in [{lo}, {hi}], got {raw!r}",
            ) from exc
        if not (lo <= value <= hi):
            raise UpscaleRequestError(
                "UPSCALE_BAD_OPTION",
                f"{name} must be in [{lo}, {hi}], got {raw!r}",
            )
        return value

    params: dict[str, Any] = {
        "method": method,
        "source_image": source_image,
        "scale": scale_value,
        "seed": _opt_int("seed", 0 if method == "vosr2" else 666, 0, 2**31 - 1),
    }
    if method == "vosr2":
        params["tile_size"] = _opt_int("tile_size", 512, 64, 2048)
        params["tile_overlap"] = _opt_int("tile_overlap", 64, 0, 512)
        params["vae_tile_size"] = _opt_int("vae_tile_size", 256, 32, 1024)
    return params


def resolve_source_path(source_image: str) -> str:
    """Resolve a ComfyUI input filename to a local path (traversal-safe)."""
    try:
        import folder_paths  # type: ignore

        input_dir = str(folder_paths.get_input_directory())
    except Exception as exc:
        raise UpscaleRunError(
            "UPSCALE_INPUT_UNAVAILABLE",
            "ComfyUI input directory unavailable",
            http_status=500,
        ) from exc
    path = os.path.join(input_dir, source_image)
    if not os.path.isfile(path):
        raise UpscaleRunError(
            "UPSCALE_SOURCE_NOT_FOUND",
            f"image {source_image!r} not found on server — re-upload it",
            http_status=404,
        )
    return path


def _load_source_rgb(source_path: str) -> Any:
    from PIL import Image

    try:
        return Image.open(source_path).convert("RGB")
    except Exception as exc:
        raise UpscaleRunError(
            "UPSCALE_SOURCE_UNREADABLE",
            f"could not read source image: {exc}",
            http_status=400,
        ) from exc


def _modal_workspace_active(workspace: dict | None) -> bool:
    return bool(
        isinstance(workspace, dict)
        and workspace.get("id")
        and workspace.get("token_id")
        and workspace.get("token_secret")
    )


async def _run_on_modal(
    method: str,
    rgb: Any,
    params: dict[str, Any],
    workspace: dict[str, Any],
) -> tuple[Any, str]:
    """Run heavy upscale inference on Modal via the config-owned app.

    Calls the already-deployed single ``studio_upscale`` entrypoint with
    the explicit ``method`` in the payload (revalidated here before send;
    the remote side revalidates again).  Never deploys.  Raises
    ``UpscaleRunError`` (503) when the entrypoint is absent or the call
    fails, and ``UpscaleRequestError`` (400) for an unknown method.
    """
    try:
        import modal
    except Exception as exc:
        raise UpscaleRunError(
            "UPSCALE_MODAL_UNAVAILABLE",
            "modal SDK is not installed; cannot run upscale on Modal",
            http_status=503,
        ) from exc
    try:
        from modal_client import get_modal_app_name
    except Exception:
        get_modal_app_name = None  # type: ignore[assignment]
    if get_modal_app_name is not None:
        try:
            default_app = str(get_modal_app_name())
        except Exception:
            default_app = "comfyui"
    else:
        default_app = "comfyui"
    if method not in UPSCALE_METHODS:
        raise UpscaleRequestError(
            "UPSCALE_UNKNOWN_METHOD",
            f"unknown upscale method {method!r}: expected exactly "
            "'vosr2' or 'seedvr2' (no Auto)",
        )
    app_name = (os.environ.get(UPSCALE_MODAL_APP_ENV) or default_app).strip() or default_app
    remote_name = UPSCALE_REMOTE_FUNCTION
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    payload = {
        "method": method,
        "image_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "scale": params["scale"],
        "seed": params["seed"],
        "tile_size": params.get("tile_size"),
        "tile_overlap": params.get("tile_overlap"),
        "vae_tile_size": params.get("vae_tile_size"),
    }
    try:
        client = modal.Client.from_credentials(
            workspace["token_id"], workspace["token_secret"]
        )
        fn = modal.Function.from_name(app_name, remote_name, client=client)
        raw = await asyncio.wait_for(
            asyncio.to_thread(fn.remote, payload),
            timeout=UPSCALE_MODAL_TIMEOUT_S,
        )
    except Exception as exc:
        raise UpscaleRunError(
            "UPSCALE_MODAL_UNAVAILABLE",
            f"Modal upscale entrypoint {app_name}.{remote_name} "
            f"unavailable: {type(exc).__name__}: {exc}. Deploy it via "
            "v2ctl; no local fallback was attempted for heavy inference.",
            http_status=503,
        ) from exc
    if not isinstance(raw, dict) or raw.get("status") != "ok":
        detail = ""
        if isinstance(raw, dict):
            detail = str(raw.get("message") or raw.get("error") or "")[:500]
        raise UpscaleRunError(
            "UPSCALE_MODAL_FAILED",
            f"Modal upscale {method} via {remote_name} failed: "
            f"{detail or 'remote error'}",
            http_status=502,
        )
    try:
        out_bytes = base64.b64decode(raw["image_b64"])
        from PIL import Image

        out = Image.open(io.BytesIO(out_bytes)).convert("RGB")
    except Exception as exc:
        raise UpscaleRunError(
            "UPSCALE_MODAL_BAD_RESULT",
            f"Modal upscale {method} via {remote_name} returned an "
            f"unreadable image: {exc}",
            http_status=502,
        ) from exc
    return out, "modal"


def _run_local(method: str, rgb: Any, params: dict[str, Any]) -> tuple[Any, str]:
    """Run the explicit local adapter (fail-closed without deps/CUDA)."""
    if method == "vosr2":
        from studio_upscale_vosr2 import VOSR2Unavailable, upscale_vosr2

        try:
            return (
                upscale_vosr2(
                    rgb,
                    scale=params["scale"],
                    tile_size=params["tile_size"],
                    tile_overlap=params["tile_overlap"],
                    vae_tile_size=params["vae_tile_size"],
                    seed=params["seed"],
                ),
                "local",
            )
        except VOSR2Unavailable as exc:
            raise UpscaleRunError(
                getattr(exc, "error_code", "VOSR2_UNAVAILABLE"),
                str(exc),
                http_status=503,
            ) from exc
    from studio_upscale_seedvr2 import SeedVR2Unavailable, upscale_seedvr2

    try:
        return (
            upscale_seedvr2(rgb, scale=params["scale"], seed=params["seed"]),
            "local",
        )
    except SeedVR2Unavailable as exc:
        raise UpscaleRunError(
            getattr(exc, "error_code", "SEEDVR2_UNAVAILABLE"),
            str(exc),
            http_status=503,
        ) from exc


def _save_result(
    out: Any, method: str, scale_value: float, studio_output_dir: Any
) -> tuple[str, str, bytes]:
    from local_artifacts import get_studio_outputs_dir

    out_dir = (
        Path(studio_output_dir) if studio_output_dir is not None else get_studio_outputs_dir()
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    scale_tag = str(scale_value).replace(".", "p")
    filename = f"studio-upscale-{method}-{scale_tag}x-{uuid.uuid4().hex[:8]}.png"
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    raw = buf.getvalue()
    (out_dir / filename).write_bytes(raw)
    asset_id = hashlib.sha256(raw).hexdigest()
    return filename, asset_id, raw


async def handle_upscale_async(
    body: Any,
    workspace: dict[str, Any] | None = None,
    studio_output_dir: Any = None,
) -> dict[str, Any]:
    """Validate, execute, and materialize an upscale as a result candidate.

    Never mutates the stored workflow.  Returns a Studio-consumable dict
    with ``output_paths``/``output_path``/``primary_asset_id``/``meta``.
    Raises ``UpscaleRequestError`` (400) or ``UpscaleRunError``.
    """
    t0 = time.perf_counter()
    params = parse_upscale_request(body)
    method = params["method"]
    scale_value = params["scale"]

    t_load0 = time.perf_counter()
    source_path = await asyncio.to_thread(
        resolve_source_path, params["source_image"]
    )
    rgb = await asyncio.to_thread(_load_source_rgb, source_path)
    src_size = [rgb.width, rgb.height]
    t_load_ms = round((time.perf_counter() - t_load0) * 1000, 2)

    t_infer0 = time.perf_counter()
    modal_active = _modal_workspace_active(workspace)
    if modal_active:
        assert isinstance(workspace, dict)
        out, backend = await _run_on_modal(method, rgb, params, workspace)
    else:
        out, backend = await asyncio.to_thread(_run_local, method, rgb, params)
    t_infer_ms = round((time.perf_counter() - t_infer0) * 1000, 2)

    t_save0 = time.perf_counter()
    filename, asset_id, _raw = await asyncio.to_thread(
        _save_result, out, method, scale_value, studio_output_dir
    )
    t_save_ms = round((time.perf_counter() - t_save0) * 1000, 2)
    total_ms = round((time.perf_counter() - t0) * 1000, 2)

    run_id = f"upscale_{uuid.uuid4().hex[:12]}"
    meta = {
        "upscale_method": method,
        "scale": scale_value,
        "source_asset": params["source_image"],
        "seed": params["seed"],
        "source_size": src_size,
        "output_size": [out.width, out.height],
        "backend": backend,
        "modal_used": backend == "modal",
        "primary_asset_id": asset_id,
        "output_paths": [filename],
        "timings": {
            "load_ms": t_load_ms,
            "inference_ms": t_infer_ms,
            "save_ms": t_save_ms,
            "total_ms": total_ms,
        },
    }
    if method == "vosr2":
        meta["tile_size"] = params["tile_size"]
        meta["tile_overlap"] = params["tile_overlap"]
        meta["vae_tile_size"] = params["vae_tile_size"]
    _log.info(
        "Studio upscale ok: method=%s scale=%s backend=%s out=%s total_ms=%s",
        method,
        scale_value,
        backend,
        filename,
        total_ms,
    )
    return {
        "status": "ok",
        "runId": run_id,
        "output_paths": [filename],
        "output_path": filename,
        "primary_asset_id": asset_id,
        "meta": meta,
    }
