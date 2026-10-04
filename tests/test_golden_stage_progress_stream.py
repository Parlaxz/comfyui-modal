"""Focused contracts for opt-in live Golden stage progress."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from comfymodal_runtime.golden_serial import GoldenTelemetryRecorder


pytestmark = pytest.mark.fast_unit


def test_recorder_emits_ordered_authoritative_stage_events() -> None:
    events: list[dict] = []
    ticks = iter(range(100, 110))
    recorder = GoldenTelemetryRecorder(
        monotonic=lambda: next(ticks),
        wall=lambda: next(ticks) * 10,
        stage_observer=events.append,
        request_id="studio-request-1",
    )

    recorder.begin_stage("golden_clip_load")
    recorder.end_stage("golden_clip_load")
    recorder.begin_stage("golden_unet_load")
    recorder.fail_stage("golden_unet_load", ValueError("bad checkpoint"))

    assert [event["phase"] for event in events] == [
        "started", "completed", "started", "failed"
    ]
    assert [event["sequence"] for event in events] == [1, 2, 3, 4]
    assert all(event["request_id"] == "studio-request-1" for event in events)
    assert all(event["schema"] == "golden_stage_event_v1" for event in events)
    assert events[0]["end_monotonic_ns"] is None
    assert events[1]["entry_monotonic_ns"] == events[0]["entry_monotonic_ns"]
    assert events[1]["end_monotonic_ns"] is not None
    assert events[-1]["ok"] is False
    assert events[-1]["error"] == "ValueError: bad checkpoint"


def test_observer_failure_isolated_from_stage_boundaries() -> None:
    def broken_observer(_event: dict) -> None:
        raise RuntimeError("observer is unavailable")

    recorder = GoldenTelemetryRecorder(stage_observer=broken_observer, request_id="req")
    recorder.begin_stage("golden_sampling")
    recorder.end_stage("golden_sampling")
    recorder.begin_stage("golden_output")
    recorder.fail_stage("golden_output", RuntimeError("output failed"))

    assert recorder.intervals["golden_sampling"].ok is True
    assert recorder.intervals["golden_output"].ok is False


def test_parallel_boundaries_have_one_request_sequence_without_serial_claim() -> None:
    events: list[dict] = []
    events_lock = threading.Lock()

    def observe(event: dict) -> None:
        with events_lock:
            events.append(event)

    recorder = GoldenTelemetryRecorder(
        stage_observer=observe,
        request_id="parallel-request",
    )
    barrier = threading.Barrier(4)

    def run(index: int) -> None:
        stage = f"golden_parallel_{index}"
        recorder.begin_stage(stage)
        barrier.wait()
        recorder.end_stage(stage)

    with recorder.concurrent_stage_mode():
        threads = [threading.Thread(target=run, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert [event["sequence"] for event in events] == list(range(1, 9))
    assert sum(event["phase"] == "started" for event in events) == 4
    assert sum(event["phase"] == "completed" for event in events) == 4
    assert all("serial" not in event for event in events)


def test_default_modal_path_has_no_queue_or_task_and_one_terminal_result() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "comfymodal_runtime" / "modal_app.py").read_text(
        encoding="utf-8"
    )
    marker = "if not stream_golden_stage_events:"
    start = source.index(marker)
    end = source.index("                    else:", start)
    default_branch = source[start:end]

    assert 'request.get("stream_golden_stage_events") is True' in source
    assert "result = await execute_golden(" in default_branch
    assert "asyncio.Queue" not in default_branch
    assert "create_task" not in default_branch
    assert "stage_observer" not in default_branch
    assert source.count('yield {"type": "result", "data": result_data}') == 1
