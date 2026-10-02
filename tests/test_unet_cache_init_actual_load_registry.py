"""Focused tests for actual-load registry init via the UNET-cache init path.

Fast-disk snapshot activation can reach the patched graph loader without
first calling ``_start_production_restore_unet``, so ``_actual_load_locks``
(and its required companion ``_actual_load_futures``) may be absent at
graph-fallback time.  ``_init_unet_cache`` must therefore initialise the
actual-load registry so the fallback does not raise
``AttributeError: ... _actual_load_locks``.
"""

from __future__ import annotations

import pytest

from tests.test_comfyapp_runtime_state import load_module


@pytest.fixture()
def mixin():
    module = load_module()
    return module._ComfyAPIMixin()


def test_init_unet_cache_initializes_actual_load_locks(mixin):
    """_init_unet_cache must create _actual_load_locks when absent."""
    assert not hasattr(mixin, "_actual_load_locks"), (
        "fresh mixin must not have _actual_load_locks before init"
    )
    mixin._init_unet_cache()
    assert hasattr(mixin, "_actual_load_locks"), (
        "_init_unet_cache must create _actual_load_locks"
    )
    assert isinstance(mixin._actual_load_locks, dict)
    assert len(mixin._actual_load_locks) == 0


def test_init_unet_cache_initializes_companion_futures(mixin):
    """_init_unet_cache must also create the _actual_load_futures companion."""
    assert not hasattr(mixin, "_actual_load_futures")
    mixin._init_unet_cache()
    assert hasattr(mixin, "_actual_load_futures"), (
        "_init_unet_cache must create _actual_load_futures"
    )
    assert isinstance(mixin._actual_load_futures, dict)
    assert len(mixin._actual_load_futures) == 0


def test_init_unet_cache_is_idempotent_and_preserves_existing(mixin):
    """Repeated init must not clobber an existing locks dict."""
    mixin._init_unet_cache()
    mixin._actual_load_locks["existing"] = object()
    mixin._init_unet_cache()
    assert "existing" in mixin._actual_load_locks, (
        "repeated init must preserve existing lock entries"
    )
