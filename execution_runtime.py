"""Canonical execution-mode resolver for comfyui-modal.

H12 (V2-only execution consolidation): Modal V2 is the ONLY public Studio
execution engine.  The V1/legacy and shadow engines are retired; their mode
strings remain RECOGNIZED solely so persisted settings can be migrated and
explicit retired-mode requests can be rejected truthfully — recognition is
never execution reachability.

Single authoritative source: all code paths (normal graph, Studio single-run,
Studio experiments) route through ``resolve_execution_mode()``.

Resolution order (first match wins):
  1. Request-captured mode (from ``modal_options`` / explicit field).
     Only ``v2`` is executable.  An explicit retired value (``v1`` /
     ``legacy`` / ``shadow``) is surfaced with ``retired=True`` so the
     dispatch layer can reject the request before any execution — a retired
     request is never silently relabeled as V2.
  2. Valid ``COMFYMODAL_RUNTIME`` env override.  The env-lock MECHANISM is
     preserved, but its accepted vocabulary has collapsed to ``{v2}``:
     retired values are logged as refused and fall through to the next
     precedence (which can only yield v2).
  3. Persisted server setting (from ``.modal_settings.json``).  Only a
     literal ``v2`` is honored; retired/stale values are logged and ignored
     (startup migration rewrites them once).
  4. Default: v2.

The environment override remains **locked**: when it resolves, it cannot be
overridden by request or setting.
"""

from __future__ import annotations

import os
import logging
from typing import Any

_log = logging.getLogger(__name__)

# ── Canonical public mode names ─────────────────────────────────────────────
MODE_V2 = "v2"

# ── Retired modes ────────────────────────────────────────────────────────────
# Recognized on input for migration / deprecation reporting only.  No dispatch
# path may execute them (the Comparison runner's frozen legacy seam does not
# consult this resolver).
MODE_V1 = "v1"
MODE_SHADOW = "shadow"
RETIRED_MODES = (MODE_V1, MODE_SHADOW)

_ENGINE_V1_RETIRED_NOTICE = "Engine V1 retired; future runs use V2."

# ── Internal legacy aliases (recognized on input, never exposed to users) ───
_LEGACY_ALIASES: dict[str, str] = {
    "legacy": MODE_V1,
    "v1": MODE_V1,
    "v2": MODE_V2,
    "shadow": MODE_SHADOW,
}

# ── Wildcard set of all recognizable input values ───────────────────────────
_VALID_INPUTS = frozenset(_LEGACY_ALIASES.keys())


def normalize_mode(raw: str | None) -> str | None:
    """Normalize a raw mode string to v1/v2/shadow, accepting legacy aliases.

    Recognition-only: the live resolver can produce/executes ``v2`` alone.
    Returns ``None`` for unknown/unrecognized values.
    """
    if not raw or not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    return _LEGACY_ALIASES.get(key)


def is_retired_mode(mode: str | None) -> bool:
    """True when *mode* names a retired engine (v1 or shadow)."""
    return mode in RETIRED_MODES


def engine_v1_retired_notice() -> str:
    """The canonical one-time migration notice text."""
    return _ENGINE_V1_RETIRED_NOTICE


def _get_os_env_mode() -> str | None:
    """Read the ``COMFYMODAL_RUNTIME`` env var under the collapsed vocabulary.

    Only ``v2`` resolves.  Retired values are logged as refused; garbage is
    logged and ignored.  Both fall through to the next precedence.
    """
    val = os.environ.get("COMFYMODAL_RUNTIME", "").strip().lower()
    if not val:
        return None
    if val == MODE_V2:
        return MODE_V2
    if val in _VALID_INPUTS:
        _log.warning(
            "COMFYMODAL_RUNTIME=%r is retired and refused; ignoring "
            "(only 'v2' is accepted). %s",
            val,
            _ENGINE_V1_RETIRED_NOTICE,
        )
        return None
    _log.warning("Ignoring unrecognized COMFYMODAL_RUNTIME=%r", val)
    return None


def _get_persisted_mode(modal_settings: dict | None = None) -> str | None:
    """Read persisted execution_mode from server settings.

    Only an exact ``v2`` value is honored.  Retired or stale persisted values
    are ignored here (the startup migration rewrites them once); they can
    never select a retired engine.
    """
    if not modal_settings or not isinstance(modal_settings, dict):
        return None
    raw = modal_settings.get("execution_mode")
    normalized = normalize_mode(raw)
    if normalized == MODE_V2:
        return MODE_V2
    if normalized is not None:
        _log.warning(
            "Persisted execution_mode=%r is retired and ignored; using V2. %s",
            raw,
            _ENGINE_V1_RETIRED_NOTICE,
        )
    return None


def _get_request_mode(modal_options: dict | None = None, *, extra: dict | None = None) -> str | None:
    """Extract captured execution_mode from a request's modal_options or extra.

    Returns the normalized string (v1/v2/shadow) so callers can reject
    retired values truthfully instead of silently substituting V2.
    """
    # Prefer explicit execution_mode in extra (captured at submission)
    if isinstance(extra, dict):
        raw = extra.get("execution_mode")
        if raw:
            return normalize_mode(raw)
    # Fall back to modal_options
    if isinstance(modal_options, dict):
        raw = modal_options.get("execution_mode")
        if raw:
            return normalize_mode(raw)
    return None


def resolve_execution_mode(
    *,
    modal_options: dict | None = None,
    extra: dict | None = None,
    modal_settings: dict | None = None,
) -> dict[str, Any]:
    """Resolve the execution mode with full metadata.

    Returns
    -------
    dict with keys:
        mode : str
            ``"v2"`` for every executable resolution.  A request that
            explicitly carries a retired engine surfaces that exact string
            together with ``retired=True`` so the dispatcher can reject it.
        source : str
            "request", "env_override", "server_setting", or "default".
        locked : bool
            True when COMFYMODAL_RUNTIME resolved the mode.
        retired : bool
            True only for explicit request-captured retired engines; such
            resolutions must never execute.
    """
    # 1. Request-captured mode. Once a request has been accepted, its mode
    # remains immutable even if the process environment changes afterward.
    req_mode = _get_request_mode(modal_options, extra=extra)
    if req_mode:
        if req_mode == MODE_V2:
            return {
                "mode": MODE_V2,
                "source": "request",
                "locked": False,
                "retired": False,
            }
        # Explicit retired-engine request: surface truthfully for rejection.
        return {
            "mode": req_mode,
            "source": "request",
            "locked": False,
            "retired": True,
        }

    # 2. Environment override applies to requests without a captured mode.
    # Vocabulary collapsed to {v2}: retired values are refused upstream and
    # fall through to the next precedence.
    env_mode = _get_os_env_mode()
    if env_mode:
        return {
            "mode": env_mode,
            "source": "env_override",
            "locked": True,
            "retired": False,
        }

    # 3. Persisted server setting (v2 only after migration)
    persisted = _get_persisted_mode(modal_settings)
    if persisted:
        return {
            "mode": persisted,
            "source": "server_setting",
            "locked": False,
            "retired": False,
        }

    # 4. Default v2
    return {
        "mode": MODE_V2,
        "source": "default",
        "locked": False,
        "retired": False,
    }


def retired_request_mode(
    modal_options: dict | None = None,
    *,
    extra: dict | None = None,
) -> str | None:
    """Return the retired engine mode an explicit request carries, if any.

    Dispatch sites call this BEFORE acceptance/execution and reject with a
    truthful 4xx error when it returns a value.  Returns ``None`` when the
    request carries no retired engine selection.
    """
    resolved = resolve_execution_mode(modal_options=modal_options, extra=extra)
    if resolved.get("retired"):
        return resolved["mode"]
    return None


def retired_mode_error(mode: str) -> str:
    """Truthful rejection message for an explicitly retired engine request."""
    if mode == MODE_SHADOW:
        return (
            "Execution engine 'shadow' is retired and cannot execute. "
            + _ENGINE_V1_RETIRED_NOTICE
        )
    return (
        f"Execution engine '{mode}' is retired and cannot execute. "
        + _ENGINE_V1_RETIRED_NOTICE
    )


def validate_config_payload(payload: dict) -> str | None:
    """Validate a POST /comfymodal/config execution_mode value.

    Returns an error message string on failure, or None on success.
    V2 is the only accepted engine; v1/legacy/shadow are rejected.
    """
    mode = payload.get("execution_mode")
    if mode is None:
        return None  # not setting execution_mode
    if not isinstance(mode, str):
        return "execution_mode must be a string"
    normalized = mode.strip().lower()
    if normalized == MODE_V2:
        return None
    if normalized in ("v1", "legacy"):
        return f"Rejected: {mode!r}. " + _ENGINE_V1_RETIRED_NOTICE
    if normalized == MODE_SHADOW:
        return "Shadow mode is retired and not a user-selectable setting."
    return f"Invalid execution_mode: {mode!r}. Must be 'v2'."


def capture_execution_mode(modal_options: dict | None = None, *, extra: dict | None = None, modal_settings: dict | None = None) -> str:
    """Capture the immutable execution mode at request submission time.

    Returns the executable mode string for the request.  Callers must run
    :func:`retired_request_mode` first and reject retired requests; capture
    itself only ever yields ``v2`` for acceptable requests.
    """
    resolved = resolve_execution_mode(modal_options=modal_options, extra=extra, modal_settings=modal_settings)
    if resolved.get("retired"):
        raise ValueError(retired_mode_error(resolved["mode"]))
    return resolved["mode"]
