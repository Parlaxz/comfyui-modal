from __future__ import annotations

import json
import os
import struct
import threading

import pytest

from comfymodal_runtime import golden_model_transport as transport_module
from comfymodal_runtime.golden_model_transport import GoldenModelTransport


pytestmark = pytest.mark.fast_unit


def _write_safetensors(path, payload: bytes = b"abcd") -> None:
    header = {
        "__metadata__": {"format": "pt"},
        "tensor": {
            "dtype": "U8",
            "shape": [len(payload)],
            "data_offsets": [0, len(payload)],
        },
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + payload)


def _count_parses(monkeypatch):
    calls = []
    original = transport_module._parse_layout

    def wrapped(path, identity):
        calls.append((path, identity))
        return original(path, identity)

    monkeypatch.setattr(transport_module, "_parse_layout", wrapped)
    return calls


def test_preresolve_populates_cache_for_followup_inspect(tmp_path, monkeypatch):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path)
    calls = _count_parses(monkeypatch)
    transport = GoldenModelTransport()

    holder = transport.begin_layout_preresolve(str(path))
    joined = transport.join_layout_preresolve(str(path))
    inspected = transport.inspect(str(path))

    assert joined is holder
    assert inspected is holder.result
    assert holder.error is None
    assert len(calls) == 1


def test_preresolve_is_single_flight_for_one_path(tmp_path, monkeypatch):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path)
    calls = _count_parses(monkeypatch)
    transport = GoldenModelTransport()

    first = transport.begin_layout_preresolve(str(path))
    second = transport.begin_layout_preresolve(str(path))
    joined = transport.join_layout_preresolve(str(path))

    assert first is second is joined
    assert joined.done.is_set()
    assert len(calls) == 1


def test_preresolve_uses_separate_holders_for_different_paths(tmp_path, monkeypatch):
    first_path = tmp_path / "first.safetensors"
    second_path = tmp_path / "second.safetensors"
    _write_safetensors(first_path, b"first")
    _write_safetensors(second_path, b"second")
    calls = _count_parses(monkeypatch)
    transport = GoldenModelTransport()

    first = transport.begin_layout_preresolve(str(first_path))
    first.done.wait()
    second = transport.begin_layout_preresolve(str(second_path))
    transport.join_layout_preresolve(str(second_path))

    assert first is not second
    assert first.path != second.path
    assert first.error is None
    assert second.error is None
    assert len(calls) == 2


def test_preresolve_failure_is_recorded_and_inspect_fails_closed(tmp_path):
    path = tmp_path / "invalid.safetensors"
    path.write_bytes(struct.pack("<Q", 10) + b"bad")
    transport = GoldenModelTransport()

    holder = transport.begin_layout_preresolve(str(path))
    transport.join_layout_preresolve(str(path))

    assert isinstance(holder.error, ValueError)
    prefix = str(holder.error).split(":", 1)[0]
    with pytest.raises(type(holder.error), match=prefix):
        transport.inspect(str(path))
    assert str(path.resolve()) not in transport.layout_cache


def test_preresolve_revalidates_identity_before_reusing_layout(tmp_path, monkeypatch):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, b"a")
    calls = _count_parses(monkeypatch)
    transport = GoldenModelTransport()

    holder = transport.begin_layout_preresolve(str(path))
    transport.join_layout_preresolve(str(path))
    first = holder.result
    _write_safetensors(path, b"a changed payload")
    second = transport.inspect(str(path))

    assert second is not first
    assert second.data_bytes != first.data_bytes
    assert len(calls) == 2


def test_join_without_begin_does_not_start_parse(tmp_path, monkeypatch):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path)
    calls = _count_parses(monkeypatch)
    transport = GoldenModelTransport()

    holder = transport.join_layout_preresolve(str(path))

    assert holder.started_ns is None
    assert holder.finished_ns is None
    assert holder.done.is_set()
    assert calls == []


def test_preresolve_holder_exposes_completion_telemetry(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path)
    transport = GoldenModelTransport()

    holder = transport.begin_layout_preresolve(str(path))
    transport.join_layout_preresolve(str(path))

    assert isinstance(holder.started_ns, int)
    assert isinstance(holder.finished_ns, int)
    assert isinstance(holder.ms, float)
    assert holder.done.is_set()


def test_begin_preresolve_never_raises_for_nonexistent_path(tmp_path):
    path = tmp_path / "missing.safetensors"
    transport = GoldenModelTransport()

    holder = transport.begin_layout_preresolve(str(path))
    joined = transport.join_layout_preresolve(str(path))

    assert joined is holder
    assert isinstance(holder.error, FileNotFoundError)
    assert str(path.resolve()) not in transport.layout_cache


def test_inspect_cache_hit_and_identity_refresh_regression(tmp_path, monkeypatch):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, b"initial")
    calls = _count_parses(monkeypatch)
    transport = GoldenModelTransport()

    first = transport.inspect(str(path))
    assert transport.inspect(str(path)) is first
    assert len(calls) == 1

    _write_safetensors(path, b"different size")
    refreshed = transport.inspect(str(path))

    assert refreshed is not first
    assert len(calls) == 2


def test_join_layout_preresolve_is_bounded_when_the_preresolve_never_finishes() -> None:
    """The join must not put the request event loop behind an unbounded read.

    The pre-resolve is an optimization: golden_unet_load's own inspect() stays
    the canonical parse.  An unbounded wait here would serialize the whole
    request behind one header read on a host that stalls, so the join is
    budgeted and expiry is observable through ``completed``.
    """
    import threading
    import time

    from comfymodal_runtime.golden_model_transport import (
        LAYOUT_PRERESOLVE_JOIN_BUDGET_S,
        GoldenModelTransport,
        LayoutPreresolve,
    )

    transport = GoldenModelTransport()
    holder = LayoutPreresolve(
        path=os.path.abspath("/nonexistent/model.safetensors"),
        started_ns=time.perf_counter_ns(),
        finished_ns=None,
        done=threading.Event(),
    )
    transport._layout_preresolve = holder

    started = time.monotonic()
    joined = transport.join_layout_preresolve(
        "/nonexistent/model.safetensors", timeout_s=0.05
    )
    elapsed = time.monotonic() - started

    assert joined is holder
    assert joined.completed is False, "expiry must be observable"
    assert elapsed < 2.0, f"join took {elapsed:.3f}s; it must honour its budget"
    # The production default must exist and be finite.
    assert 0.0 < LAYOUT_PRERESOLVE_JOIN_BUDGET_S < 30.0


def test_join_layout_preresolve_returns_completed_holder_when_the_work_landed() -> None:
    from comfymodal_runtime.golden_model_transport import (
        GoldenModelTransport,
        LayoutPreresolve,
    )

    transport = GoldenModelTransport()
    done = threading.Event()
    done.set()
    holder = LayoutPreresolve(
        path=os.path.abspath("/nonexistent/model.safetensors"),
        started_ns=1,
        finished_ns=2_000_000,
        done=done,
    )
    transport._layout_preresolve = holder

    joined = transport.join_layout_preresolve("/nonexistent/model.safetensors")

    assert joined is holder
    assert joined.completed is True
    assert joined.ms == pytest.approx(2.0)
