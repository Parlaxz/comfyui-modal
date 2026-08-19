"""Unified V2 A/B experiment registry.

Experiments are declared once in ``EXPERIMENT_SPECS`` with a bounded arm set
and a selector describing how the arm is chosen:

- ``request``: the arm is resolved from ``os.environ`` at request-call time.
  ``modal_app._apply_request_variance_diagnostics`` applies request-carried
  allowlisted values to ``os.environ`` before a request method runs, so a
  single request can flip its own experiment arms.
- ``container``: resolved from the container environment (deployment-level).
- ``deployment``: resolved from the deployment environment (set at deploy
  time; not per-request selectable).

All parsers are safe when the environment is unset (they return the
experiment default).  Invalid int values fall back to the default and print a
``[v2.experiment] ERROR invalid_arm`` line so a misconfigured deployment is
visible without ever crashing a request.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EXPERIMENT_SPECS",
    "ExperimentSpec",
    "ExperimentSelection",
    "resolve_experiment",
    "resolve_all_experiments",
    "emit_experiment_selection",
    "experiment_line",
    "unet_pinned_staging_enabled",
    "unet_staging_chunk_mb",
    "vae_early_start_ms",
    "vae_expected_sampling_ms",
    "png_compress_level",
    "conditioning_async_lru_enabled",
    "restore_total_vram_frozen_enabled",
    "log_invalid_arm",
]

_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class ExperimentSpec:
    """Static description of one V2 experiment.

    ``arms`` is the bounded set of allowed arm names; ``selector`` is
    ``"request"`` | ``"container"`` | ``"deployment"``; ``env_key`` is the
    environment variable the arm is resolved from; ``default_arm`` is used
    whenever the env value is unset or invalid.
    """

    name: str
    arms: tuple[str, ...]
    selector: str            # "request" | "container" | "deployment"
    env_key: str
    default_arm: str
    implementation_version: str


EXPERIMENT_SPECS: dict[str, ExperimentSpec] = {
    "unet_transfer": ExperimentSpec(
        name="unet_transfer",
        arms=("baseline", "pinned_staging"),
        selector="request",
        env_key="COMFYMODAL_V2_UNET_PINNED_STAGING",
        default_arm="baseline",
        implementation_version="1",
    ),
    "vae_overlap": ExperimentSpec(
        name="vae_overlap",
        arms=("baseline", "early_250", "early_500", "early_750", "early_1000"),
        selector="request",
        env_key="COMFYMODAL_V2_VAE_EARLY_START_MS",
        default_arm="baseline",
        implementation_version="1",
    ),
    "png_encode": ExperimentSpec(
        name="png_encode",
        arms=("level6", "level1"),
        selector="request",
        env_key="COMFYMODAL_V2_PNG_COMPRESS_LEVEL",
        default_arm="level1",
        implementation_version="1",
    ),
    "conditioning_hit": ExperimentSpec(
        name="conditioning_hit",
        arms=("sync_lru", "async_lru"),
        selector="request",
        env_key="COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU",
        default_arm="sync_lru",
        implementation_version="1",
    ),
    "restore_memory": ExperimentSpec(
        name="restore_memory",
        arms=("baseline", "optimized"),
        selector="deployment",
        env_key="COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN",
        default_arm="baseline",
        implementation_version="1",
    ),
}


@dataclass(frozen=True)
class ExperimentSelection:
    """Resolved arm for one experiment at a point in time.

    ``effective_settings`` carries the raw env value(s) that produced the arm
    (e.g. ``{"pinned_staging": True, "chunk_mb": 512}``).  ``source`` is
    ``"env"`` when the experiment's env key was present in ``os.environ`` at
    resolution time (even if the value fell back to the default arm), else
    ``"default"``.
    """

    name: str
    arm: str
    effective_settings: Mapping[str, Any]
    implementation_version: str
    selector: str
    source: str  # "env" | "default"


# ── Low-level env parsers ──────────────────────────────────────────────


def _env_bool(env_key: str) -> bool:
    """Parse a boolean env flag: true only for ``{1,true,yes,on}``.

    Case-insensitive, whitespace-stripped; every other value (including
    unset/empty) is ``False``.
    """
    raw = os.environ.get(env_key, "").strip().lower()
    return raw in _BOOL_TRUE


def _env_int(env_key: str) -> int | None:
    """Return the parsed int env value, or ``None`` when unset/empty or
    not a base-10 integer."""
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ── Per-experiment accessors (validated, default-safe) ─────────────────


def unet_pinned_staging_enabled() -> bool:
    """COMFYMODAL_V2_UNET_PINNED_STAGING — request-selectable."""
    return _env_bool("COMFYMODAL_V2_UNET_PINNED_STAGING")


def unet_staging_chunk_mb() -> int:
    """COMFYMODAL_V2_UNET_STAGING_CHUNK_MB.

    Default 512; parseable values clamped to 16..8192; invalid (present but
    not a base-10 integer) -> 512 with a logged error.
    """
    raw = os.environ.get("COMFYMODAL_V2_UNET_STAGING_CHUNK_MB", "").strip()
    if not raw:
        return 512
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        log_invalid_arm("unet_transfer", "COMFYMODAL_V2_UNET_STAGING_CHUNK_MB", raw, 512)
        return 512
    return max(16, min(8192, parsed))


def vae_early_start_ms() -> int:
    """COMFYMODAL_V2_VAE_EARLY_START_MS — request-selectable.

    Allowed {0, 250, 500, 750, 1000}; any other value (or non-int) -> 0
    (baseline) with a logged error.
    """
    _VAE_EARLY_ALLOWED = frozenset({0, 250, 500, 750, 1000})
    raw = os.environ.get("COMFYMODAL_V2_VAE_EARLY_START_MS", "").strip()
    if not raw:
        return 0
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed not in _VAE_EARLY_ALLOWED:
        log_invalid_arm("vae_overlap", "COMFYMODAL_V2_VAE_EARLY_START_MS", raw, 0)
        return 0
    return parsed


def vae_expected_sampling_ms() -> int:
    """COMFYMODAL_V2_VAE_EXPECTED_SAMPLING_MS.

    Default 4900; parseable values clamped to 100..30000; unset/invalid -> 4900.
    """
    value = _env_int("COMFYMODAL_V2_VAE_EXPECTED_SAMPLING_MS")
    if value is None:
        return 4900
    return max(100, min(30000, value))


def png_compress_level() -> int:
    """COMFYMODAL_V2_PNG_COMPRESS_LEVEL — request-selectable.

    Allowed {1, 6}; any other value (or non-int) -> 1 with a logged error.
    """
    _PNG_LEVEL_ALLOWED = frozenset({1, 6})
    raw = os.environ.get("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "").strip()
    if not raw:
        return 1
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed not in _PNG_LEVEL_ALLOWED:
        log_invalid_arm("png_encode", "COMFYMODAL_V2_PNG_COMPRESS_LEVEL", raw, 1)
        return 1
    return parsed


def conditioning_async_lru_enabled() -> bool:
    """COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU — request-selectable."""
    return _env_bool("COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU")


def restore_total_vram_frozen_enabled() -> bool:
    """COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN — deployment-selectable."""
    return _env_bool("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN")


def log_invalid_arm(name: str, env_key: str, value: Any, fallback: Any) -> None:
    """Print a one-line ``[v2.experiment] ERROR invalid_arm`` diagnostic.

    Called whenever an env value for experiment *name* was present but did not
    map to an allowed arm, so the misconfiguration is visible in logs.
    """
    print(
        f"[v2.experiment] ERROR invalid_arm "
        f"experiment={name} env_key={env_key} value={value!r} fallback={fallback}",
        flush=True,
    )


# ── Resolution ─────────────────────────────────────────────────────────


def resolve_experiment(name: str) -> ExperimentSelection:
    """Resolve one experiment from ``os.environ`` at call time.

    Reads the experiment's env key fresh on every call (request overrides are
    applied to ``os.environ`` by ``modal_app`` before the request method runs).
    The arm is derived from the validated accessors; invalid values fall back
    to the experiment default with a logged error.
    """
    spec = EXPERIMENT_SPECS[name]
    env_value = os.environ.get(spec.env_key)
    source = "env" if env_value is not None else "default"

    if spec.name == "unet_transfer":
        pinned = unet_pinned_staging_enabled()
        arm = "pinned_staging" if pinned else "baseline"
        effective: Mapping[str, Any] = {
            "pinned_staging": pinned,
            "chunk_mb": unet_staging_chunk_mb(),
        }
    elif spec.name == "vae_overlap":
        early_ms = vae_early_start_ms()
        arm = f"early_{early_ms}" if early_ms else "baseline"
        effective = {
            "early_start_ms": early_ms,
            "expected_sampling_ms": vae_expected_sampling_ms(),
        }
    elif spec.name == "png_encode":
        level = png_compress_level()
        arm = f"level{level}"
        effective = {"compress_level": level}
    elif spec.name == "conditioning_hit":
        async_lru = conditioning_async_lru_enabled()
        arm = "async_lru" if async_lru else "sync_lru"
        effective = {"async_lru": async_lru}
    elif spec.name == "restore_memory":
        frozen = restore_total_vram_frozen_enabled()
        arm = "optimized" if frozen else "baseline"
        effective = {"total_vram_frozen": frozen}
    else:  # pragma: no cover — guarded by EXPERIMENT_SPECS[name] lookup
        raise ValueError(f"Unknown experiment: {name!r}")

    if arm not in spec.arms:
        arm = spec.default_arm
    return ExperimentSelection(
        name=spec.name,
        arm=arm,
        effective_settings=effective,
        implementation_version=spec.implementation_version,
        selector=spec.selector,
        source=source,
    )


def resolve_all_experiments() -> dict[str, ExperimentSelection]:
    """Resolve every declared experiment into a name -> selection map."""
    return {name: resolve_experiment(name) for name in EXPERIMENT_SPECS}


def experiment_line(selection: ExperimentSelection) -> str:
    """Render the canonical ``[v2.experiment]`` one-line summary for a
    selection: experiment, arm, implementation version, selector, source, and
    the effective settings as compact JSON."""
    settings_json = json.dumps(
        selection.effective_settings,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "[v2.experiment] "
        f"experiment={selection.name} "
        f"arm={selection.arm} "
        f"implementation_version={selection.implementation_version} "
        f"selector={selection.selector} "
        f"source={selection.source} "
        f"settings={settings_json}"
    )


def emit_experiment_selection(
    trace: Any,
    selection: ExperimentSelection,
    *,
    phase: str = "execution",
) -> None:
    """Emit an ``experiment_selection`` trace event and print the canonical
    one-line summary.  ``trace`` must expose ``emit(name, phase=..., metadata=...)``
    (e.g. ``RuntimeTrace``)."""
    trace.emit(
        "experiment_selection",
        phase=phase,
        metadata={
            "experiment_name": selection.name,
            "arm": selection.arm,
            "effective_settings": selection.effective_settings,
            "implementation_version": selection.implementation_version,
            "selector": selection.selector,
            "source": selection.source,
        },
    )
    print(experiment_line(selection), flush=True)
