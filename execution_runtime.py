"""Canonical execution-mode resolver for comfyui-modal.

Normalizes v1, v2, shadow modes publicly; accepts legacy aliases internally.
Single authoritative source: all code paths (normal graph, Studio single-run,
Studio experiments) route through ``resolve_execution_mode()``.

Resolution order (first match wins):
  1. Request-captured mode (from ``modal_options`` / explicit field).
  2. Valid ``COMFYMODAL_RUNTIME`` env override.
  3. Persisted server setting (from ``.modal_settings.json``).
  4. Default: v2.

The environment override is **locked**: when set, it cannot be overridden by
request or setting, and the frontend displays it as "Managed by COMFYMODAL_RUNTIME".
"""

from __future__ import annotations

import os
import logging
from typing import Any

_log = logging.getLogger(__name__)

# ── Canonical public mode names ─────────────────────────────────────────────
MODE_V1 = "v1"
MODE_V2 = "v2"
MODE_SHADOW = "shadow"

# ── Internal legacy aliases (accepted on input, never exposed to users) ─────
_LEGACY_ALIASES: dict[str, str] = {
    "legacy": MODE_V1,
    "v1": MODE_V1,
    "v2": MODE_V2,
    "shadow": MODE_SHADOW,
}

# ── Wildcard set of all acceptable input values (public + legacy) ──────────
_VALID_INPUTS = frozenset(_LEGACY_ALIASES.keys())

# ── Public modes exposed to Settings UI ────────────────────────────────────
AVAILABLE_EXECUTION_MODES = [
    {"value": MODE_V2, "label": "V2 — Recommended"},
    {"value": MODE_V1, "label": "V1 — Legacy"},
]


def normalize_mode(raw: str | None) -> str | None:
    """Normalize a raw mode string to v1/v2/shadow, accepting legacy aliases.

    Returns ``None`` for unknown/unrecognized values.
    """
    if not raw or not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    return _LEGACY_ALIASES.get(key)


def _get_os_env_mode() -> str | None:
    """Read and normalize the ``COMFYMODAL_RUNTIME`` env var."""
    val = os.environ.get("COMFYMODAL_RUNTIME", "").strip().lower()
    if not val:
        return None
    normalized = _LEGACY_ALIASES.get(val)
    if normalized:
        return normalized
    _log.warning("Ignoring unrecognized COMFYMODAL_RUNTIME=%r", val)
    return None


def _get_persisted_mode(modal_settings: dict | None = None) -> str | None:
    """Read persisted execution_mode from server settings."""
    if not modal_settings or not isinstance(modal_settings, dict):
        return None
    raw = modal_settings.get("execution_mode")
    return normalize_mode(raw)


def _get_request_mode(modal_options: dict | None = None, *, extra: dict | None = None) -> str | None:
    """Extract captured execution_mode from a request's modal_options or extra."""
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
            Normalized mode: "v1", "v2", or "shadow".
        source : str
            "request", "env_override", "server_setting", or "default".
        locked : bool
            True when COMFYMODAL_RUNTIME is set (env override locked).
    """
    # 1. Request-captured mode. Once a request has been accepted, its mode
    # remains immutable even if the process environment changes afterward.
    req_mode = _get_request_mode(modal_options, extra=extra)
    if req_mode:
        return {
            "mode": req_mode,
            "source": "request",
            "locked": False,
        }

    # 2. Environment override applies to requests without a captured mode.
    # It is locked so the UI cannot claim a different engine.
    env_mode = _get_os_env_mode()
    if env_mode:
        return {
            "mode": env_mode,
            "source": "env_override",
            "locked": True,
        }

    # 3. Persisted server setting
    persisted = _get_persisted_mode(modal_settings)
    if persisted:
        return {
            "mode": persisted,
            "source": "server_setting",
            "locked": False,
        }

    # 4. Default v2
    return {
        "mode": MODE_V2,
        "source": "default",
        "locked": False,
    }


def is_v2(modal_options: dict | None = None, *, extra: dict | None = None, modal_settings: dict | None = None) -> bool:
    """Convenience: return True if resolved mode is v2 or shadow."""
    resolved = resolve_execution_mode(modal_options=modal_options, extra=extra, modal_settings=modal_settings)
    return resolved["mode"] in (MODE_V2, MODE_SHADOW)


def is_shadow(modal_options: dict | None = None, *, extra: dict | None = None, modal_settings: dict | None = None) -> bool:
    """Convenience: return True if resolved mode is shadow."""
    resolved = resolve_execution_mode(modal_options=modal_options, extra=extra, modal_settings=modal_settings)
    return resolved["mode"] == MODE_SHADOW


def validate_config_payload(payload: dict) -> str | None:
    """Validate a POST /comfymodal/config execution_mode value.

    Returns an error message string on failure, or None on success.
    Only public modes (v1, v2) are accepted; shadow is rejected.
    """
    mode = payload.get("execution_mode")
    if mode is None:
        return None  # not setting execution_mode
    if not isinstance(mode, str):
        return "execution_mode must be a string"
    normalized = mode.strip().lower()
    if normalized == MODE_SHADOW:
        return "Shadow mode is not a user-selectable setting."
    if normalized not in (MODE_V1, MODE_V2):
        return f"Invalid execution_mode: {mode!r}. Must be 'v1' or 'v2'."
    return None


def capture_execution_mode(modal_options: dict | None = None, *, extra: dict | None = None, modal_settings: dict | None = None) -> str:
    """Capture the immutable execution mode at request submission time.

    Returns the normalized mode string (v1/v2/shadow) for the request.
    This value must be persisted in request metadata / modal_options
    so later execution sees the mode that was active at submission.
    """
    resolved = resolve_execution_mode(modal_options=modal_options, extra=extra, modal_settings=modal_settings)
    return resolved["mode"]
