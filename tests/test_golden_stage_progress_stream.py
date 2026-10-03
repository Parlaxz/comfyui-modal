"""Focused contracts for the optional Golden stage progress lane."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERIAL_PATH = ROOT / "comfymodal_runtime" / "golden_serial.py"
MODAL_PATH = ROOT / "comfymodal_runtime" / "modal_app.py"

pytestmark = pytest.mark.fast_unit


def _load_serial_module():
    spec = importlib.util.spec_from_file_location(
        "golden_serial_stage_progress_under_test", SERIAL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gs = _load_serial_module()


class _Clock:
    def __init__(self):
        self.value = 100

    def tick(self):
        self.value += 10
        return self.value


def test_stage_observer_reports_authoritative_boundaries_without_child_telemetry():
    clock = _Clock()
    observed = []
    recorder = gs.GoldenTelemetryRecorder(
        monotonic=clock.tick,
        wall=clock.tick,
        request_id="remote-actual",
        stage_observer=observed.append,
    )

    recorder.begin_stage("golden_clip_load")
    recorder.end_stage("golden_clip_load", ready=True)

    assert [event["phase"] for event in observed] == ["started", "completed"]
    assert [event["sequence"] for event in observed] == [0, 1]
    assert all(event["schema"] == "golden_stage_event_v1" for event in observed)
    assert all(event["type"] == "golden_stage" for event in observed)
    assert all(event["request_id"] == "remote-actual" for event in observed)
    assert all(event["stage"] == "golden_clip_load" for event in observed)
    assert observed[0]["ok"] is None
    assert observed[0]["end_monotonic_ns"] is None
    assert observed[1]["ok"] is True
    assert observed[1]["entry_monotonic_ns"] < observed[1]["end_monotonic_ns"]
    assert observed[1]["entry_wall_ns"] < observed[1]["end_wall_ns"]
    # The progress lane is not copied into the persisted child event stream.
    assert recorder.events == []


def test_failed_observer_delivery_is_best_effort_and_failure_message_is_bounded():
    observed = []

    def observer(event):
        observed.append(event)
        raise RuntimeError("observer must not change Golden")

    recorder = gs.GoldenTelemetryRecorder(
        request_id="remote-failure",
        stage_observer=observer,
    )
    recorder.begin_stage("golden_sampling")
    recorder.fail_stage("golden_sampling", ValueError("x" * 5000))

    assert observed[-1]["phase"] == "failed"
    assert observed[-1]["ok"] is False
    assert len(observed[-1]["error"]) <= 512
    assert recorder._intervals["golden_sampling"].ok is False


def test_default_modal_golden_path_is_still_a_direct_await():
    source = MODAL_PATH.read_text(encoding="utf-8")
    assert "stream_golden_stage_events" in source
    assert "if not stream_golden_stage_events:" in source
    default_branch = source.split("if not stream_golden_stage_events:", 1)[1]
    default_branch = default_branch.split("else:", 1)[0]
    assert "await execute_golden(" in default_branch
    assert "asyncio.create_task(" not in default_branch
    assert "stage_observer=" not in default_branch


def test_execute_entrypoints_accept_the_optional_observer():
    assert "stage_observer" in inspect.signature(gs.golden_serial_execute).parameters

    parallel_path = ROOT / "comfymodal_runtime" / "golden_parallel.py"
    parallel_source = parallel_path.read_text(encoding="utf-8")
    assert "stage_observer" in parallel_source
