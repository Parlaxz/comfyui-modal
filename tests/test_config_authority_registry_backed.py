"""The flag registry is the only place a runtime control is defined.

config_authority used to restate 129 flags with their own type, default, enum
set and description.  Those copies drifted: 74 defaults and 11 types disagreed
with the registry, and 16 flags the runtime resolved were not declared there at
all.  It is now a thin resolver, so these tests lock the shape that prevents a
second specification table from reappearing.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

from comfymodal_runtime import config_authority as ca
from comfymodal_runtime import config_schema

MODULE = Path(ca.__file__).resolve()
REGISTRY = {e["name"]: e for e in config_schema.load_registry()}


def test_every_runtime_resolved_flag_is_declared_in_the_registry():
    """A resolvable flag must exist in the single authority."""
    undeclared = sorted(set(ca.GOLDEN_CONTROL_FLAGS) - set(REGISTRY))
    assert undeclared == [], (
        "runtime resolves flags the registry does not declare: %r" % (undeclared,)
    )


def test_registry_declares_no_flag_the_runtime_cannot_resolve():
    """The reverse direction: every registry flag the runtime claims is present."""
    missing = sorted(set(ca._CLASSIFICATION) - set(ca.GOLDEN_CONTROL_FLAGS))
    assert missing == [], (
        "classification metadata without a resolvable spec: %r" % (missing,)
    )


def test_resolution_reads_type_and_default_from_the_registry():
    """Spot-check that a spec's facts track the registry, not a local copy."""
    for name, spec in ca.GOLDEN_CONTROL_FLAGS.items():
        entry = REGISTRY[name]
        choices = tuple(entry.get("enum_values") or ())
        expected_type = "enum" if choices else str(entry["type"])
        assert spec["type"] == expected_type, name
        assert spec["description"] == str(entry.get("description", "")), name
        # The registry stores defaults as strings; the resolver coerces them to
        # the declared type, and that coerced value is what it publishes.
        assert spec["default"] == ca._coerce(str(entry["default"]), spec)[1], name


def test_source_declares_no_literal_default_or_enum_table():
    """Structural guard: no hand-written type/default/choice facts remain.

    This is what stops the drift from coming back.  The only literal metadata
    left in the module is the classification map, which the registry does not
    carry.
    """
    tree = ast.parse(io.open(MODULE, encoding="utf-8").read())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "_spec":
            continue
        # Any surviving _spec(...) call reintroduces a local type/default.
        offenders.append(ast.dump(node)[:80])
    assert offenders == [], (
        "config_authority still builds specs by hand: %r" % (offenders,)
    )


def test_resolve_rejects_values_outside_the_registry_enum_set():
    """Enum constraints come from the registry, so they are enforced from it."""
    for name, spec in ca.GOLDEN_CONTROL_FLAGS.items():
        choices = tuple(spec.get("choices") or ())
        if not choices:
            continue
        allowed = choices[0]
        resolved = ca.resolve({name: allowed})
        assert resolved.get(name) == allowed, name
        # An unlisted value is refused and falls back to the registry default,
        # which is not necessarily the first choice.
        rejected = "definitely_not_a_valid_choice"
        assert rejected not in choices, name
        assert ca.resolve({name: rejected}).get(name) == spec["default"], name


def test_fast_disk_unet_stays_disabled():
    """Guards the behaviour-preserving decision on this cleanup.

    The registry once declared the native fast-disk UNET loader enabled while
    the runtime has always run it disabled.  Current verified runtime behaviour
    is authoritative, so the registry says disabled.
    """
    assert REGISTRY["COMFYMODAL_V2_NATIVE_FAST_DISK_UNET"]["default"] == "0"
    assert ca.resolve({}).get("COMFYMODAL_V2_NATIVE_FAST_DISK_UNET") is False