"""A Golden control flag must reach the container, not just the config layer.

There are three separate places a Golden flag has to be declared, and missing
any one of them fails *silently* rather than loudly:

1. ``config/v2/flag_registry.toml``   - the v2ctl/local control plane
2. ``comfymodal_runtime/config_authority.py`` - the runtime authority
3. ``_runtime_env()`` in ``modal_app.py`` - a hand-written allowlist that
   becomes Modal's class-level ``env=``

The copy-stall probe was declared in the first two and missed the third, so it
never entered the container. Nothing raised: the probe simply reported itself
unavailable and a diagnostic cohort silently collected no evidence. These tests
close that gap by requiring the three declarations to agree.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FLAG_REGISTRY = REPO / "config" / "v2" / "flag_registry.toml"

GOLDEN_CONTROL_FLAGS = (
    "COMFYMODAL_GOLDEN_SOURCE_COPY_PROBE",
    "COMFYMODAL_GOLDEN_SOURCE_COPY_PROBE_MINCORE",
)


def _registry_flags() -> set[str]:
    data = tomllib.loads(FLAG_REGISTRY.read_text(encoding="utf-8"))
    return {str(entry["name"]) for entry in data.get("flag", []) if "name" in entry}


def _authority_flags() -> set[str]:
    from comfymodal_runtime.config_authority import GOLDEN_CONTROL_FLAGS as authority

    return set(authority)


def _runtime_env_keys() -> set[str]:
    """Static keys of the container env allowlist, without importing ComfyUI.

    ``_runtime_env`` needs the whole runtime import graph, so the keys are read
    from the source instead. That keeps this test cheap and importable.
    """
    source = (REPO / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
    start = source.index("def _runtime_env(")
    end = source.index("\ndef ", start + 1)
    body = source[start:end]
    return set(re.findall(r'^\s*"(COMFYMODAL_[A-Z0-9_]+)"\s*:', body, re.MULTILINE))


@pytest.mark.parametrize("flag", GOLDEN_CONTROL_FLAGS)
def test_flag_is_in_the_v2ctl_registry(flag: str) -> None:
    assert flag in _registry_flags(), f"{flag} missing from flag_registry.toml"


@pytest.mark.parametrize("flag", GOLDEN_CONTROL_FLAGS)
def test_flag_is_in_the_runtime_authority(flag: str) -> None:
    assert flag in _authority_flags(), f"{flag} missing from config_authority.py"


@pytest.mark.parametrize("flag", GOLDEN_CONTROL_FLAGS)
def test_flag_reaches_the_container_env(flag: str) -> None:
    """The gate that failed silently: declared upstream, dropped before the container."""
    assert flag in _runtime_env_keys(), (
        f"{flag} is declared but absent from _runtime_env(); it will never reach "
        "the container and any diagnostic depending on it will silently do nothing"
    )


def test_probe_flags_default_to_off() -> None:
    """Counted profiles must be unaffected by default."""
    from comfymodal_runtime.config_authority import GOLDEN_CONTROL_FLAGS as authority

    for flag in GOLDEN_CONTROL_FLAGS:
        default = authority[flag].get("default")
        assert default in (False, "0"), (
            f"{flag} must default OFF so counted profiles are unchanged, got {default!r}"
        )