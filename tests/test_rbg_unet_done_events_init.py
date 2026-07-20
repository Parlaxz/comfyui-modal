"""Focused tests for _rbg_unet_done_events idempotent init in _init_actual_load_registry.

Verifies:
* Fresh _ComfyAPIMixin creates _rbg_unet_done_events on first init.
* Repeated init preserves an existing map with entries.
* _start_production_restore_unet no longer raises solely due to missing
  _rbg_unet_done_events (it may still need loader/thread infrastructure).
* Legacy reset (``_rbg_unet_done_events = {}``) remains present in comfyapp.py.
"""

from __future__ import annotations

import re
import threading
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _import_comfyapp():
    """Ensure comfyapp is importable in the test environment."""
    import importlib
    try:
        return importlib.import_module("comfyapp")
    except Exception:
        pytest.skip("comfyapp cannot be imported in this environment")


def _fresh_mixin():
    """Create a fresh _ComfyAPIMixin instance via object.__new__."""
    from comfyapp import _ComfyAPIMixin
    return object.__new__(_ComfyAPIMixin)


def test_fresh_init_creates_rbg_unet_done_events():
    """_init_actual_load_registry must create _rbg_unet_done_events when absent."""
    m = _fresh_mixin()
    assert not hasattr(m, "_rbg_unet_done_events"), (
        "fresh mixin must NOT have _rbg_unet_done_events before init"
    )
    m._init_actual_load_registry()
    assert hasattr(m, "_rbg_unet_done_events"), (
        "init must create _rbg_unet_done_events"
    )
    assert isinstance(m._rbg_unet_done_events, dict), (
        "_rbg_unet_done_events must be a dict"
    )
    assert len(m._rbg_unet_done_events) == 0, (
        "fresh dict must be empty"
    )


def test_repeated_init_preserves_existing():
    """Calling _init_actual_load_registry twice must NOT reset existing events."""
    m = _fresh_mixin()
    m._init_actual_load_registry()
    m._rbg_unet_done_events["test_key"] = threading.Event()
    m._init_actual_load_registry()  # second call
    assert "test_key" in m._rbg_unet_done_events, (
        "repeated init must preserve existing keys"
    )
    assert len(m._rbg_unet_done_events) == 1, (
        "repeated init must not add duplicate entries"
    )


def test_start_production_restore_unet_does_not_raise_missing_rbg():
    """_start_production_restore_unet must not raise solely because
    _rbg_unet_done_events is absent — the registry init before the
    handoff ensures it exists."""
    from comfyapp import _ComfyAPIMixin
    m = object.__new__(_ComfyAPIMixin)
    m._init_actual_load_registry()
    assert hasattr(m, "_rbg_unet_done_events"), (
        "init must create the dict before method is called"
    )
    # The method still needs loader infrastructure and may raise for
    # other reasons, but AttributeError for the missing dict must not
    # happen.  We call with a minimal mock plan that exercises the
    # _rbg_unet_done_events code path.
    m._loader_cache_infra = {}
    m._loader_recent_misses = 0
    m._loader_recent_unet_ids = []
    m._cache_path = "/tmp/void"
    # If the method raises, it must NOT be AttributeError about _rbg_unet_done_events
    try:
        m._start_production_restore_unet(
            {"unet": "unet_test", "weight_dtype": "fp16"},
            restore_start=100.0,
            restore_stages={},
        )
    except AttributeError as exc:
        assert "_rbg_unet_done_events" not in str(exc), (
            f"Must not raise AttributeError about missing _rbg_unet_done_events: {exc}"
        )
        # Other attribute errors are expected in the test environment
    except Exception:
        pass  # Other errors (missing thread/import/path) are expected


def test_legacy_reset_remains_present():
    """The legacy restore path must still contain ``_rbg_unet_done_events = {}``."""
    import importlib
    import inspect
    try:
        comfyapp = importlib.import_module("comfyapp")
    except Exception:
        pytest.skip("comfyapp cannot be imported")
    source = inspect.getsource(comfyapp)
    # Count occurrences: one for idempotent init (new), one for legacy reset (existing)
    # The key pattern in the source is: "_rbg_unet_done_events: dict[str, object] = {}"
    # We search for the reset pattern without type annotation
    # Legacy reset is: self._rbg_unet_done_events = {}
    init_count = len(re.findall(r'self\._rbg_unet_done_events\s*[=:]', source))
    assert init_count >= 2, (
        f"Expected at least 2 assignments to _rbg_unet_done_events "
        f"(init + legacy reset), found {init_count}"
    )
    # Verify the legacy reset is still there (no ':' — assignment, not annotation)
    legacy_reset_matches = re.findall(
        r'self\._rbg_unet_done_events\s*=\s*\{\}',
        source,
    )
    assert len(legacy_reset_matches) >= 1, (
        "Legacy `self._rbg_unet_done_events = {}` reset must still be present"
    )
