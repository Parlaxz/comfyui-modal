from __future__ import annotations

import sys
import types

import pytest

from comfymodal_runtime import triton_cache


pytestmark = pytest.mark.fast_unit


class _FakeJITFunction:
    """Stands in for triton.runtime.jit.JITFunction."""

    calls = 0

    def _do_compile(self, kernel, options, *args, **kwargs):
        type(self).calls += 1
        return ("compiled", kernel, options)


class _Options:
    num_warps = 8
    num_stages = 3
    num_ctas = 1
    maxnreg = None
    debug = False


@pytest.fixture(autouse=True)
def _always_uninstall():
    """Never let a failed assertion leak a wrapped _do_compile into the next test."""
    yield
    try:
        triton_cache.uninstall_compile_request_observer()
    except Exception:
        pass


def _install_fake_triton(monkeypatch):
    triton_pkg = types.ModuleType("triton")
    runtime_pkg = types.ModuleType("triton.runtime")
    jit_mod = types.ModuleType("triton.runtime.jit")
    jit_mod.JITFunction = _FakeJITFunction
    runtime_pkg.jit = jit_mod
    triton_pkg.runtime = runtime_pkg
    monkeypatch.setitem(sys.modules, "triton", triton_pkg)
    monkeypatch.setitem(sys.modules, "triton.runtime", runtime_pkg)
    monkeypatch.setitem(sys.modules, "triton.runtime.jit", jit_mod)
    triton_cache.reset_compile_request_events()
    return jit_mod


def test_observer_records_only_the_matched_kernel(monkeypatch):
    jit_mod = _install_fake_triton(monkeypatch)
    result = triton_cache.install_compile_request_observer(name_filter="bmm")
    assert result["installed"] is True

    class bmm_outer_product(_FakeJITFunction):
        src = "def bmm_outer_product(a, b, BLOCK_M: tl.constexpr): ..."

    class unrelated_kernel(_FakeJITFunction):
        src = "def unrelated(x): ..."

    bmm_outer_product.__name__ = "bmm_outer_product"
    unrelated_kernel.__name__ = "unrelated_kernel"

    bmm_outer_product()._do_compile("kern", _Options(), 4, 8, 16, 32)
    unrelated_kernel()._do_compile("kern2", _Options(), 1)

    events = triton_cache.compile_request_events()
    assert len(events) == 2
    matched = [e for e in events if e["matched"]]
    assert len(matched) == 1
    assert matched[0]["kernel"] == "bmm_outer_product"
    # The real arguments are captured, not guessed.
    assert matched[0]["specialization_args"] == [4, 8, 16, 32]
    assert matched[0]["option_num_warps"] == 8
    assert matched[0]["option_num_stages"] == 3
    assert matched[0]["src_sha256"]
    triton_cache.uninstall_compile_request_observer()


def test_observer_is_transparent_and_removable(monkeypatch):
    jit_mod = _install_fake_triton(monkeypatch)
    pristine = _FakeJITFunction._do_compile
    _FakeJITFunction.calls = 0

    triton_cache.install_compile_request_observer(name_filter="bmm")
    assert _FakeJITFunction._do_compile is not pristine

    # Observation must not change behaviour or the return value.
    out = _FakeJITFunction()._do_compile("kern", _Options(), 1, 2)
    assert out[0] == "compiled"
    assert _FakeJITFunction.calls == 1

    # Removal must restore the installed attribute exactly.
    removed = triton_cache.uninstall_compile_request_observer()
    assert removed["removed"] is True
    assert _FakeJITFunction._do_compile is pristine
    _FakeJITFunction()._do_compile("kern", _Options(), 1)
    assert _FakeJITFunction.calls == 2


def test_kernel_name_is_discovered_even_without_dunder_name(monkeypatch):
    """A JITFunction instance has no ``__name__``; the source must still match.

    Reading ``self.__name__`` yields '' on an instance, so an observer built on
    it installs cleanly, matches nothing, and looks identical to a kernel that
    never compiled. That is exactly how Phase 2 lost a cycle.
    """
    _install_fake_triton(monkeypatch)

    class _Kernel(_FakeJITFunction):
        src = (
            "@triton.jit\n"
            "def bmm_outer_product(a_ptr, b_ptr, c_ptr, M, N, "
            "BLOCK_M: tl.constexpr, BLOCK_N: tl.constexpr):\n"
            "    pass\n"
        )

    instance = _Kernel()
    assert getattr(instance, "__name__", "") == ""

    triton_cache.install_compile_request_observer(name_filter="bmm")
    instance._do_compile("kern", _Options(), 1, 2)
    events = triton_cache.compile_request_events()
    assert len(events) == 1
    assert events[0]["matched"] is True
    assert events[0]["kernel"] == "bmm_outer_product"
    assert events[0]["specialization_args"] == [1, 2]


def test_observer_reports_install_failure_instead_of_silence(monkeypatch):
    """A failed install must be visible, not indistinguishable from no calls."""
    broken = types.ModuleType("triton.runtime.jit")
    # No JITFunction attribute at all: importing it must fail cleanly.
    monkeypatch.setitem(sys.modules, "triton", types.ModuleType("triton"))
    monkeypatch.setitem(sys.modules, "triton.runtime", types.ModuleType("triton.runtime"))
    monkeypatch.setitem(sys.modules, "triton.runtime.jit", broken)
    result = triton_cache.install_compile_request_observer(name_filter="bmm")
    assert result["installed"] is False
    assert result["reason"]


def test_double_install_is_idempotent(monkeypatch):
    _install_fake_triton(monkeypatch)
    first = triton_cache.install_compile_request_observer(name_filter="bmm")
    second = triton_cache.install_compile_request_observer(name_filter="bmm")
    assert first["installed"] is True
    assert second.get("reason") == "already_installed"
    triton_cache.uninstall_compile_request_observer()


def test_cache_tree_snapshot_reports_real_key_directories(tmp_path):
    (tmp_path / "abc123").mkdir()
    (tmp_path / "abc123" / "kern.cubin").write_bytes(b"x" * 10)
    (tmp_path / "zzz").mkdir()
    tree = triton_cache.snapshot_triton_cache_tree(tmp_path)
    assert tree["exists"] is True
    assert tree["dirs"] == ["abc123", "zzz"]
    # The directory name is Triton's own cache key; this is why no key formula
    # has to be re-derived.
    assert {row["path"] for row in tree["files"]} == {"abc123/kern.cubin"}


def test_cache_tree_snapshot_handles_missing_root(tmp_path):
    tree = triton_cache.snapshot_triton_cache_tree(tmp_path / "absent")
    assert tree["exists"] is False
    assert tree["files"] == []


def test_arg_describer_captures_tensor_identity_without_retaining_tensor():
    class FakeTensor:
        shape = (2, 1024, 1)
        stride = lambda self: (1024, 1, 1)  # noqa: E731
        dtype = "torch.bfloat16"
        device = "cuda:0"

    described = triton_cache._describe_compile_arg(FakeTensor())
    assert described["shape"] == [2, 1024, 1]
    assert described["stride"] == [1024, 1, 1]
    assert described["dtype"] == "torch.bfloat16"
    assert described["device"] == "cuda:0"