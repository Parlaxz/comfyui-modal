from __future__ import annotations

import pytest

from comfymodal_runtime import golden_io_process_v2 as c0


pytestmark = pytest.mark.fast_unit


def test_registration_selectors_are_default_off_and_overlap(monkeypatch):
    monkeypatch.delenv(c0.C0_REGISTRATION_DIAG_ENV, raising=False)
    monkeypatch.delenv(c0.C0_REGISTRATION_ORDER_ENV, raising=False)
    assert c0.c0_registration_diag_enabled() is False
    assert c0.c0_registration_order() == "overlap"
    assert c0.c0_registration_context_preinit_enabled() is False


def test_registration_order_selector_is_explicit(monkeypatch):
    monkeypatch.setenv(c0.C0_REGISTRATION_ORDER_ENV, "register_first")
    assert c0.c0_registration_order() == "register_first"
    monkeypatch.setenv(c0.C0_REGISTRATION_ORDER_ENV, "invalid")
    with pytest.raises(ValueError, match="REGISTRATION_ORDER_invalid"):
        c0.c0_registration_order()


def test_registration_delta_preserves_wall_cpu_and_rusage_deltas():
    before = {
        "wall_monotonic_ns": 100,
        "process_cpu_ns": 20,
        "thread_cpu_ns": 10,
        "rusage": {"process": {"user_s": 1.0, "minor_faults": 3}},
    }
    after = {
        "wall_monotonic_ns": 500,
        "process_cpu_ns": 70,
        "thread_cpu_ns": 35,
        "rusage": {"process": {"user_s": 1.25, "minor_faults": 8}},
    }
    delta = c0._registration_delta(before, after)
    assert delta["wall_ns"] == 400
    assert delta["process_cpu_ns"] == 50
    assert delta["thread_cpu_ns"] == 25
    assert delta["rusage"]["process"] == {"user_s": 0.25, "minor_faults": 5}
