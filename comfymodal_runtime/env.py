"""Environment value helpers shared by V2 runtime modules.

Single shared boolean-flag parser for every runtime env flag read.  All
module-local parsers were consolidated onto :func:`env_flag` in commit
9628c51 ("Complete V2 cache snapshot and timing fixes"); see
``tests/test_env_flags.py`` for the audited conversion table.

Exact semantics (do not change without updating the audit tests):

* Signature: ``env_flag(name: str, default: bool = False)``.
* If the variable is **absent** from the environment, ``default`` is
  returned unchanged (this preserves each call site's pre-commit absent
  semantics, e.g. ``os.environ.get(name, "1") == "1"`` → ``default=True``).
* Otherwise the raw value is stripped of surrounding whitespace and
  lowercased.  ``True`` only for the exact strings ``1``, ``true``,
  ``yes``, ``on``.
* Any other explicit value — ``0``, ``false``, ``no``, ``off``, the empty
  string, or an unrecognised token — is ``False``.  Explicit values are
  never ``None`` and never raise.
"""

from __future__ import annotations

import os


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
"""Canonical truth set accepted by :func:`env_flag` after trim + lower."""

OBSERVABILITY_MODES = frozenset({"full", "production", "off"})
"""Supported V2 observability policies."""


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def observability_mode(default: str | None = None) -> str:
    """Return the normalized V2 observability mode.

    An unset mode preserves the existing behavior: non-production containers
    keep the full diagnostic policy while production containers use the
    lightweight policy. Invalid values fail closed to the same profile-based
    default.
    """
    profile = os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "inherit").strip().lower()
    fallback = default or ("production" if profile == "production" else "full")
    raw = os.environ.get("COMFYMODAL_V2_OBSERVABILITY_MODE", "").strip().lower()
    return raw if raw in OBSERVABILITY_MODES else fallback


def observability_allows(feature: str) -> bool:
    """Return whether *feature* is allowed by the active observability mode."""
    mode = observability_mode()
    if mode == "off":
        return False
    if mode == "full":
        return True
    return feature not in {
        "cpu_sampler",
        "deep_model_diagnostics",
        "detailed_activation",
        "full_trace",
        "pagefault_tracking",
        "residency",
        "unet_forward_diagnostics",
    }


def observability_gate(flag_name: str, feature: str, *, default: bool = False) -> bool:
    """Resolve one observability gate from the current environment.

    A gate is enabled only when its dedicated flag is set AND the active
    observability mode allows *feature*.  This is the single formula used at
    import time to freeze the module-level gate constants and again at request
    time (via the ``sync_observability_gates`` helpers in ``model_preload`` /
    ``modal_app``) so that module-level gates and call-time
    ``observability_allows`` checks agree for the effective env profile.
    """
    return env_flag(flag_name, default=default) and observability_allows(feature)
