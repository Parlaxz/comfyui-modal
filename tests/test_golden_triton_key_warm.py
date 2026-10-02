"""Pre-snapshot Triton environment-key warm.

``triton.runtime.cache.triton_key`` is ``@functools.lru_cache``-decorated and
hashes the installed Triton software environment. In the production-008
exhaustive profile that was 613.8 ms of self time inside the request's first
Triton compile (``get_cache_key`` 645.6 ms).

Triton is a Linux/CUDA-only dependency, so these tests inject a synthetic
``triton.runtime.cache`` module built on a *real* ``functools.lru_cache``
wrapper. That is the point of the test: the wiring must call the exact
request-time function object and let Triton's own cache serve repeats.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast_unit

MODULE_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_serial.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("golden_serial_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("golden_serial_under_test", module)
    spec.loader.exec_module(module)
    return module


gs = _load_module()


def _install_fake_triton(*, calls: list | None = None, raising: bool = False):
    """Install a synthetic ``triton.runtime.cache`` with a real lru_cache key."""

    counter = {"n": 0}

    @functools.lru_cache()
    def triton_key():
        counter["n"] += 1
        if raising:
            raise RuntimeError("triton unavailable")
        if calls is not None:
            calls.append(1)
        # Stand in for hashing every triton module plus libtriton.
        return "3.3.0-" + "ab" * 64

    triton = types.ModuleType("triton")
    runtime = types.ModuleType("triton.runtime")
    cache = types.ModuleType("triton.runtime.cache")
    cache.triton_key = triton_key
    triton.runtime = runtime
    runtime.cache = cache

    saved = {k: sys.modules.get(k) for k in ("triton", "triton.runtime", "triton.runtime.cache")}
    sys.modules["triton"] = triton
    sys.modules["triton.runtime"] = runtime
    sys.modules["triton.runtime.cache"] = cache
    return cache, counter, saved


def _restore(saved):
    for name, value in saved.items():
        if value is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = value


# ── the warm invokes the real request-time function ──────────────────────


def test_warm_invokes_the_exact_triton_key_and_returns_its_value():
    calls: list = []
    cache, counter, saved = _install_fake_triton(calls=calls)
    try:
        record = gs.warm_triton_key()
    finally:
        _restore(saved)

    assert record["warmed"] is True
    # The value is whatever the installed implementation produced, not a constant
    # invented here: it must be the exact object the module holds.
    assert record["key"] == cache.triton_key()
    # The warm computed it once; the assertion above was served by the cache.
    assert counter["n"] == 1


def test_warm_populates_the_implementation_own_cache_so_repeats_are_served_by_it():
    calls: list = []
    cache, counter, saved = _install_fake_triton(calls=calls)
    try:
        gs.warm_triton_key()
        assert cache.triton_key.cache_info().misses == 1
        assert cache.triton_key.cache_info().hits == 0

        # Repeat calls must be served by Triton's own lru_cache, not recomputed.
        for _ in range(10):
            assert cache.triton_key() == cache.triton_key()
        info = cache.triton_key.cache_info()
        assert info.misses == 1
        assert info.hits == 20
        assert len(calls) == 1
    finally:
        _restore(saved)


def _triton_modules() -> list:
    return sorted(n for n in sys.modules if n == "triton" or n.startswith("triton."))


def test_warm_produces_no_gpu_specific_kernel_artifact():
    """The warm only hashes software; it must not create any compiled kernel."""
    calls: list = []
    cache, counter, saved = _install_fake_triton(calls=calls)
    try:
        before = _triton_modules()
        record = gs.warm_triton_key()
        after = _triton_modules()
    finally:
        _restore(saved)

    assert record["warmed"] is True
    # No new Triton compilation/runtime modules were pulled in by the warm.
    assert after == before
    # The only triton modules present are the ones the caller installed.
    assert after == ["triton", "triton.runtime", "triton.runtime.cache"]


def test_warm_is_idempotent_and_does_not_rehash():
    calls: list = []
    cache, counter, saved = _install_fake_triton(calls=calls)
    try:
        gs.warm_triton_key()
        gs.warm_triton_key()
        gs.warm_triton_key()
    finally:
        _restore(saved)

    assert counter["n"] == 1
    assert len(calls) == 1


# ── failure must never affect a request ──────────────────────────────────


def test_warm_failure_is_reported_not_raised():
    saved = {k: sys.modules.get(k) for k in ("triton", "triton.runtime", "triton.runtime.cache")}
    for k in saved:
        sys.modules.pop(k, None)
    try:
        record = gs.warm_triton_key()
    finally:
        _restore(saved)

    assert record["warmed"] is False
    assert record["reason"] == "ModuleNotFoundError"
    assert "key" not in record


def test_warm_failure_inside_triton_is_reported_not_raised():
    cache, counter, saved = _install_fake_triton(raising=True)
    try:
        record = gs.warm_triton_key()
    finally:
        _restore(saved)

    assert record["warmed"] is False
    assert record["reason"] == "RuntimeError"


def test_missing_cache_module_is_reported_not_raised():
    triton = types.ModuleType("triton")
    runtime = types.ModuleType("triton.runtime")
    triton.runtime = runtime
    runtime.cache = None  # attribute exists but is not a module
    saved = {k: sys.modules.get(k) for k in ("triton", "triton.runtime", "triton.runtime.cache")}
    sys.modules["triton"] = triton
    sys.modules["triton.runtime"] = runtime
    sys.modules.pop("triton.runtime.cache", None)
    try:
        record = gs.warm_triton_key()
    finally:
        _restore(saved)

    assert record["warmed"] is False
    assert record["reason"]