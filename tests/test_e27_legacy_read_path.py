"""Regression coverage for the direct and instrumented Golden read paths."""

from __future__ import annotations

import ast
import inspect

from comfymodal_runtime import golden_serial as gs
from comfymodal_runtime.e27_source_mechanism import ActualSourceTelemetry


def test_legacy_read_path_has_no_instrumentation_callback_or_lambda(monkeypatch):
    source = inspect.getsource(gs._read_at)
    tree = ast.parse(source)
    function = tree.body[0]
    assert isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))

    legacy_branch = next(
        node for node in function.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(comparator, ast.Constant) and comparator.value is None
            for comparator in node.test.comparators
        )
    )
    assert not any(isinstance(node, ast.Lambda) for node in ast.walk(legacy_branch))
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "physical_read"
        for node in ast.walk(legacy_branch)
    )

    calls = []

    def fake_preadv(_fd, buffers, offset):
        calls.append(offset)
        view = buffers[0]
        view[:] = b"legacy"
        return len(view)

    monkeypatch.setattr(gs.os, "preadv", fake_preadv, raising=False)
    target = bytearray(6)
    assert gs._read_at(0, memoryview(target), 12) == 6
    assert target == b"legacy"
    assert calls == [12]


def test_instrumented_read_path_records_physical_events_and_provenance(monkeypatch):
    telemetry = ActualSourceTelemetry(expected_ranges=((0, 4),))

    def fake_preadv(_fd, buffers, offset):
        view = buffers[0]
        view[:] = b"data"
        return len(view)

    monkeypatch.setattr(gs.os, "preadv", fake_preadv, raising=False)
    target = bytearray(4)
    assert gs._read_at(0, memoryview(target), 0, actual_source=telemetry) == 4

    assert target == b"data"
    assert len(telemetry.events) == 1
    assert telemetry.actual_inflight == 0
    assert telemetry.report()["physical_syscall_provenance"] == "golden_serial._read_at"
