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


def _code_only(source: str) -> str:
    """Drop ``#`` comments so prose about a construct is not read as the construct."""
    lines = []
    for line in source.split("\n"):
        stripped = line.split("#", 1)[0] if line.lstrip().startswith("#") else line
        lines.append(stripped)
    return "\n".join(lines)


def test_default_modal_path_has_no_queue_or_task_and_one_terminal_result() -> None:
    """The ordinary v2ctl adapter must contain no Studio machinery at all.

    Studio streaming is selected by a dedicated Modal method, never by a
    request payload key, so nothing in the ordinary branch can construct a
    queue, a task or an observer.
    """
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "comfymodal_runtime" / "modal_app.py").read_text(
        encoding="utf-8"
    )
    # The payload key that used to select streaming must be gone entirely.
    assert "stream_golden_stage_events" not in _code_only(source)

    marker = "if stage_stream_factory is None:"
    start = source.index(marker)
    end = source.index("                    else:", start)
    default_branch = _code_only(source[start:end])

    assert "result = await execute_golden(" in default_branch
    assert "asyncio.Queue" not in default_branch
    assert "create_task" not in default_branch
    assert "stage_observer" not in default_branch
    assert source.count('yield {"type": "result", "data": result_data}') == 1


def test_studio_stream_uses_no_timer_and_polls_nothing() -> None:
    """Studio progress must be edge-triggered, not polled.

    A previous revision re-armed a 50 ms wait_for timer for the whole request
    purely to notice completion. Cost must be proportional to real stage
    boundaries, not to elapsed time.
    """
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "comfymodal_runtime" / "modal_app.py").read_text(
        encoding="utf-8"
    )
    start = source.index("async def _studio_stage_stream(")
    end = source.index("studio_request = dict(request)", start)
    studio_stream = _code_only(source[start:end])

    assert "asyncio.wait_for" not in studio_stream
    assert "asyncio.sleep" not in studio_stream
    assert "item = await stage_queue.get()" in studio_stream
    # The sentinel is what closes the stream.
    assert "done_marker" in studio_stream


def test_studio_calls_the_dedicated_adapter_not_the_profile_method() -> None:
    """Studio must not reach Golden through the profile's own method.

    Routing Studio through the ordinary method is what put the progress bridge
    inside the v2ctl path and regressed it.
    """
    repo_root = Path(__file__).resolve().parents[1]
    studio = (repo_root / "studio_golden_run.py").read_text(encoding="utf-8")
    assert 'STUDIO_STREAM_METHOD = "run_golden_studio_stream"' in studio
    assert "getattr(handle, STUDIO_STREAM_METHOD)" in studio
    assert 'getattr(handle, profile.target["method"])' not in studio
