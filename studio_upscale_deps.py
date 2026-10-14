"""Phase 11 Upscale dependency manifest (tests + declarations only).

Single-source-of-truth rule: the runtime lane owns
``studio_upscale_run.py`` / ``studio_upscale_vosr2.py`` /
``studio_upscale_seedvr2.py``.  This module declares the heavy-dependency
surface and re-exports the runtime contract constants so tests lock parity
by construction instead of duplicating literals:

* method literal ``vosr2`` | ``seedvr2`` — explicit only, never ``"auto"``;
* weights bundles resolved from ``COMFYMODAL_VOSR2_WEIGHTS`` /
  ``COMFYMODAL_SEEDVR2_WEIGHTS`` or the ``upscale_models`` folder;
* heavy inference on Modal via the single entrypoint ``studio_upscale``
  (explicit ``method`` in the payload) on the config-owned app
  (``COMFYMODAL_UPSCALE_APP_NAME``); local adapters fail closed with
  explicit ``VOSR2_UNAVAILABLE*`` / ``SEEDVR2_UNAVAILABLE*`` errors.

Importing this module is FAST-safe: it only re-exports constants from
modules whose top level is stdlib-only (torch/Modal/ComfyUI stay lazily
imported inside adapter functions), and ``MODAL_PIP_PINS`` stays an empty
tuple until the runtime lane vendors backend packages — so
``python tools/test_perf.py --fast -- tests -m fast_unit`` never pays for
heavy imports here.
"""

from __future__ import annotations

from typing import Any

from studio_upscale_run import (
    UPSCALE_METHODS,
    UPSCALE_MODAL_APP_ENV,
    UPSCALE_MODAL_TIMEOUT_S,
    UPSCALE_REMOTE_FUNCTION,
)
from studio_upscale_seedvr2 import ERROR_CODE as SEEDVR2_ERROR_CODE
from studio_upscale_seedvr2 import SEEDVR2_METHOD
from studio_upscale_seedvr2 import DEFAULT_SEED as SEEDVR2_DEFAULT_SEED
from studio_upscale_vosr2 import ERROR_CODE as VOSR2_ERROR_CODE
from studio_upscale_vosr2 import VOSR2_METHOD
from studio_upscale_vosr2 import DEFAULT_SEED as VOSR2_DEFAULT_SEED
from studio_upscale_vosr2 import DEFAULT_TILE_OVERLAP as VOSR2_DEFAULT_TILE_OVERLAP
from studio_upscale_vosr2 import DEFAULT_TILE_SIZE as VOSR2_DEFAULT_TILE_SIZE
from studio_upscale_vosr2 import DEFAULT_VAE_TILE_SIZE as VOSR2_DEFAULT_VAE_TILE_SIZE

# Method → fail-closed dependency error code (mirrors the adapters).
UPSCALE_DEP_ERROR_CODES: dict[str, str] = {
    VOSR2_METHOD: VOSR2_ERROR_CODE,
    SEEDVR2_METHOD: SEEDVR2_ERROR_CODE,
}

# Declared heavy-dependency surface (weights + upstream checkouts + Modal).
# Nothing here is downloaded automatically; every absence fails closed.
UPSCALE_WEIGHT_ENV_VARS: tuple[str, str] = (
    "COMFYMODAL_VOSR2_WEIGHTS",
    "COMFYMODAL_SEEDVR2_WEIGHTS",
)
UPSCALE_REPO_ENV_VARS: tuple[str, ...] = (
    "COMFYMODAL_VOSR2_REPO",
)
UPSCALE_WEIGHT_FILES: dict[str, tuple[str, ...]] = {
    VOSR2_METHOD: ("args.json", "ema_model.safetensors"),
    SEEDVR2_METHOD: ("seedvr2_ema_3b.pth", "ema_vae.pth"),
}

# Foundation the backends run on when vendored.  Already provided by
# comfyapp.py ``_FOUNDATION_IMAGE`` (CUDA 13.0 + cu130 torch); referenced so
# the runtime lane wires the same boundary instead of a second one.
MODAL_FOUNDATION_REF: str = (
    "nvidia/cuda:13.0.0-devel-ubuntu24.04 + cu130 torch "
    "(see comfyapp.py _FOUNDATION_IMAGE)"
)

# Backend PyPI pins.  Intentionally EMPTY: the backends are upstream
# checkouts + weight bundles (see upscale_dependency_lock.txt), not PyPI
# packages, and fabricating versions would be dishonest.  The runtime lane
# fills this tuple if a backend ever gains an installable package.
MODAL_PIP_PINS: tuple[str, ...] = ()


def check_upscale_dependencies(
    method: Any, *, available_backends: Any = None
) -> dict[str, Any]:
    """FAST-safe dependency gate summary using the real error codes.

    Never imports torch/Modal/ComfyUI.  Unknown/auto methods report the
    ``UPSCALE_UNKNOWN_METHOD``-style contract error; known methods absent
    from ``available_backends`` report the adapter's own
    ``VOSR2_UNAVAILABLE`` / ``SEEDVR2_UNAVAILABLE`` code (fail-closed,
    matching ``*_unavailable`` precedent).  Pass a container of available
    method names in tests to exercise the ok path without heavy imports.
    """
    if not isinstance(method, str) or method not in UPSCALE_METHODS:
        return {
            "ok": False,
            "method": None,
            "missing": [],
            "errors": [
                f"UPSCALE_UNKNOWN_METHOD: unknown upscale method {method!r}: "
                f"expected exactly 'vosr2' or 'seedvr2' (no Auto)"
            ],
        }
    available = set(available_backends) if available_backends is not None else set()
    if method not in available:
        code = UPSCALE_DEP_ERROR_CODES[method]
        return {
            "ok": False,
            "method": method,
            "missing": [method],
            "errors": [
                f"{code}: the {method} upscale backend is not "
                f"installed/vendored; upscale cannot run "
                f"(source: current image filename; no fallback, no auto)"
            ],
        }
    return {"ok": True, "method": method, "missing": [], "errors": []}
