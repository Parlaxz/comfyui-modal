"""Focused tests for V2 prefill overlap optimisation.

``COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET`` controls whether execution-phase
prefill blocks on UNET before encoding (legacy barrier, default off).

Tests verify:
  - Default mode does NOT wait for an unfinished UNET future.
  - ``COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=1`` restores the old UNET barrier.
  - CLIP errors still fail open (fall through to original CLIPTextEncode).
  - Idempotence is preserved (calling twice returns True both times).
  - Trace metadata/events reflect the wait_for_unet policy and UNET status.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace
from typing import Any

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.trace import RuntimeTrace


# ── Helpers ────────────────────────────────────────────────────────────


def _build_bridge(
    *,
    unet_loader: Any = None,
    clip_loader: Any = None,
    invoke_original: Any = None,
    max_workers: int = 3,
) -> mp.V2LoaderBridge:
    """Build a V2LoaderBridge with mocked internals suitable for prefill tests.

    All callables default to a simple pass-through that returns an acceptable
    value so that the prefill callback structure is exercised.
    """
    bridge = mp.V2LoaderBridge(max_workers=max_workers)
    bridge.install = lambda nodes=None, trace=None: True
    bridge._request_list = lambda bucket: [{"clip_name": "clip_l.safetensors"}]
    bridge._model_spec = {
        "loaders": {
            "unet": [{"uname_name": "unet.safetensors"}],
            "clip": [{"clip_name": "clip_l.safetensors"}],
        }
    }
    bridge.coordinator.clip_loader = clip_loader or (lambda key: SimpleNamespace())
    bridge.coordinator.unet_loader = unet_loader or (lambda key: "unet-done")
    bridge._invoke_original = invoke_original or (
        lambda class_name, kwargs: (f"conditioning:{kwargs['text']}",)
    )
    return bridge


def _make_plan(
    unet_identity: str = "unet.safetensors",
    clip_identity: str = "clip_l.safetensors",
    text: str = "a happy cat",
    role: str = "positive",
) -> RestorePlan:
    """Minimal RestorePlan with a single critical-role encode entry."""
    model_key = ModelRestoreKey(
        unet_identity=unet_identity,
        clip_identity=clip_identity,
        clip_type="stable_diffusion",
    )
    prefill_key = PrefillKey(
        model_key=model_key,
        prompt_bundle_hash="hash-test-overlap",
        encode_options={
            "eligible": True,
            "encodes": [
                {
                    "node_id": "6",
                    "text": text,
                    "role": role,
                }
            ],
        },
    )
    return RestorePlan(model_key=model_key, prefill_key=prefill_key)


def _wait_future(fut: Future[Any] | None, timeout: float = 5.0) -> Any:
    """Wait for a future with a reasonable timeout."""
    if fut is None:
        return None
    return fut.result(timeout=timeout)


# ── Tests ──────────────────────────────────────────────────────────────


class TestV2PrefillOverlapDefault:
    """Default prefill overlap: does NOT block on UNET."""

    def test_default_does_not_block_on_unfinished_unet(self):
        """Default behaviour waits for CLIP only and encodes without UNET.

        Uses a blocking unet_loader (paused on a threading.Event) to prove
        that the prefill callback completes before UNET finishes.
        """
        unet_barrier = threading.Event()
        clips_loaded = threading.Event()
        encode_called = threading.Event()

        def slow_unet(key: Any) -> str:
            unet_barrier.wait(timeout=5)
            return "unet-done"

        encode_results: list[str] = []

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_called.set()
            text = kwargs.get("text", "")
            encode_results.append(text)
            return (f"conditioning:{text}",)

        bridge = _build_bridge(
            unet_loader=slow_unet,
            invoke_original=tracking_encode,
            max_workers=2,
        )

        trace = RuntimeTrace(request_id="overlap-default", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        prep = bridge._preparation
        assert prep is not None
        assert prep.unet_future is not None
        # UNET is blocked — not yet done
        assert not prep.unet_future.done(), "UNET future must be pending"

        # Schedule execution prefill (default: wait_for_unet=False)
        scheduled = bridge.schedule_execution_prefill(trace=trace)
        assert scheduled is True, "prefill must be scheduled"

        # The prefill callback should complete without UNET being done.
        prefill_result = _wait_future(prep.prefill_future, timeout=5)
        assert prefill_result is not None, "prefill future must return a result"
        assert isinstance(prefill_result, dict), "prefill result must be a dict"
        assert len(prefill_result) == 1, "expected one encoded entry"

        # UNET must still be pending when prefill completed.
        assert not prep.unet_future.done(), (
            "UNET must still be pending after prefill completes in default mode"
        )

        # Encode must have been called.
        assert encode_results == ["a happy cat"], "encode must have been called"

        # Trace events: wait_for_unet=False, unet_pending=True
        scheduled_events = [
            e for e in trace.events if e.name == "execution_prefill_scheduled"
        ]
        assert len(scheduled_events) == 1
        assert scheduled_events[0].metadata.get("wait_for_unet") is False
        assert scheduled_events[0].metadata.get("unet_future_exists") is True

        unet_status_events = [
            e for e in trace.events if e.name == "execution_prefill_unet_status"
        ]
        assert len(unet_status_events) == 1, (
            "execution_prefill_unet_status must be emitted in default mode"
        )
        assert unet_status_events[0].metadata.get("wait_for_unet") is False
        assert unet_status_events[0].metadata.get("unet_pending") is True
        assert unet_status_events[0].metadata.get("unet_skipped") is False
        assert unet_status_events[0].metadata.get("unet_resolved") is False

        completed_events = [
            e for e in trace.events if e.name == "execution_prefill_completed"
        ]
        assert len(completed_events) == 1
        assert completed_events[0].metadata.get("wait_for_unet") is False
        assert completed_events[0].metadata.get("unet_pending") is True

        # Ensure no wait_unet trace emitted from the prefill path in default mode.
        unet_wait_prefill = [
            e
            for e in trace.events
            if e.name == "unet_wait_start"
            and e.metadata.get("demand_source") == "execution_prefill"
        ]
        assert len(unet_wait_prefill) == 0, (
            "default mode must NOT call wait_unet from execution_prefill"
        )

        # Clean up: release UNET so the worker can exit.
        unet_barrier.set()
        _wait_future(prep.unet_future, timeout=5)
        bridge.coordinator.close()

    def test_trace_events_reflect_unet_skipped_when_no_unet(self):
        """When plan has no UNET, status shows unet_skipped=True."""
        bridge = _build_bridge(max_workers=1)
        trace = RuntimeTrace(request_id="overlap-no-unet", process="remote")

        model_key = ModelRestoreKey(clip_identity="clip_l.safetensors")
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="hash-no-unet",
            encode_options={
                "eligible": True,
                "encodes": [
                    {"node_id": "6", "text": "cat", "role": "positive"}
                ],
            },
        )
        plan = RestorePlan(model_key=model_key, prefill_key=prefill_key)
        bridge.prepare(plan, trace=trace)

        assert bridge._preparation is not None
        assert bridge._preparation.unet_future is None, "UNET future must be absent"

        bridge.schedule_execution_prefill(trace=trace)

        prep = bridge._preparation
        prefill_result = _wait_future(prep.prefill_future, timeout=5)
        assert prefill_result is not None

        status_events = [
            e for e in trace.events if e.name == "execution_prefill_unet_status"
        ]
        assert len(status_events) >= 1
        assert status_events[0].metadata.get("unet_skipped") is True
        assert status_events[0].metadata.get("unet_pending") is False

        completed_events = [
            e for e in trace.events if e.name == "execution_prefill_completed"
        ]
        assert len(completed_events) >= 1
        assert completed_events[0].metadata.get("unet_skipped") is True

        bridge.coordinator.close()

    def test_trace_events_reflect_unet_resolved_when_already_done(self):
        """When UNET finishes before prefill, status shows unet_resolved=True."""
        bridge = _build_bridge(max_workers=2)
        trace = RuntimeTrace(request_id="overlap-resolved", process="remote")

        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        prep = bridge._preparation
        assert prep is not None

        # Wait for UNET to complete before scheduling prefill.
        _wait_future(prep.unet_future, timeout=5)
        assert prep.unet_future is not None and prep.unet_future.done()

        bridge.schedule_execution_prefill(trace=trace)

        prefill_result = _wait_future(prep.prefill_future, timeout=5)
        assert prefill_result is not None

        status_events = [
            e for e in trace.events if e.name == "execution_prefill_unet_status"
        ]
        assert len(status_events) >= 1
        assert status_events[0].metadata.get("unet_skipped") is False
        assert status_events[0].metadata.get("unet_pending") is False
        assert status_events[0].metadata.get("unet_resolved") is True

        completed_events = [
            e for e in trace.events if e.name == "execution_prefill_completed"
        ]
        assert len(completed_events) >= 1
        assert completed_events[0].metadata.get("unet_resolved") is True

        bridge.coordinator.close()


class TestV2PrefillOverlapLegacyBarrier:
    """Legacy barrier (COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=1): waits for UNET."""

    def test_env_1_waits_for_unet(self):
        """With env=1, prefill waits for UNET before CLIP."""
        unet_barrier = threading.Event()
        clip_loaded = threading.Event()

        def slow_unet(key: Any) -> str:
            unet_barrier.wait(timeout=5)
            return "unet-done"

        encode_called = threading.Event()
        encode_results: list[str] = []

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_called.set()
            text = kwargs.get("text", "")
            encode_results.append(text)
            return (f"conditioning:{text}",)

        bridge = _build_bridge(
            unet_loader=slow_unet,
            invoke_original=tracking_encode,
            max_workers=2,
        )

        trace = RuntimeTrace(request_id="overlap-legacy", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        prep = bridge._preparation
        assert prep is not None
        assert prep.unet_future is not None
        assert not prep.unet_future.done(), "UNET must be pending"

        # Monkey-patch the module-level constant to simulate env=1.
        saved = mp._V2_PREFILL_WAIT_FOR_UNET
        try:
            mp._V2_PREFILL_WAIT_FOR_UNET = True
            scheduled = bridge.schedule_execution_prefill(trace=trace)
            assert scheduled is True, "prefill must be scheduled"

            # Give the scheduler a moment to start the callback.
            time.sleep(0.2)

            # Prefill future should NOT be done yet because UNET is blocked.
            assert prep.prefill_future is not None
            assert not prep.prefill_future.done(), (
                "prefill future must still be pending when UNET is blocked (env=1)"
            )

            # Trace events should show wait_for_unet=True, no status event yet
            # (status is only emitted in default mode).
            scheduled_events = [
                e for e in trace.events if e.name == "execution_prefill_scheduled"
            ]
            assert len(scheduled_events) >= 1
            assert scheduled_events[0].metadata.get("wait_for_unet") is True

            # No unet_status event in legacy mode (only in default).
            status_events = [
                e for e in trace.events if e.name == "execution_prefill_unet_status"
            ]
            assert len(status_events) == 0, (
                "execution_prefill_unet_status must NOT be emitted in legacy mode"
            )

            # Now release UNET.
            unet_barrier.set()

            # Prefill should now complete.
            prefill_result = _wait_future(prep.prefill_future, timeout=5)
            assert prefill_result is not None
            assert isinstance(prefill_result, dict)
            assert len(prefill_result) == 1

            # Completed event shows wait_for_unet=True
            completed_events = [
                e for e in trace.events if e.name == "execution_prefill_completed"
            ]
            assert len(completed_events) >= 1
            assert completed_events[0].metadata.get("wait_for_unet") is True

        finally:
            mp._V2_PREFILL_WAIT_FOR_UNET = saved
            unet_barrier.set()  # ensure UNET worker exits
            bridge.coordinator.close()

    def test_env_1_emits_unet_wait_trace(self):
        """With env=1, unet_wait_start with demand_source=execution_prefill appears."""
        bridge = _build_bridge(max_workers=2)
        trace = RuntimeTrace(request_id="overlap-legacy-trace", process="remote")

        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        saved = mp._V2_PREFILL_WAIT_FOR_UNET
        try:
            mp._V2_PREFILL_WAIT_FOR_UNET = True
            bridge.schedule_execution_prefill(trace=trace)

            prep = bridge._preparation
            assert prep is not None
            _wait_future(prep.prefill_future, timeout=5)

            # Verify unet_wait_start with execution_prefill demand source exists.
            unet_waits = [
                e
                for e in trace.events
                if e.name == "unet_wait_start"
                and e.metadata.get("demand_source") == "execution_prefill"
            ]
            assert len(unet_waits) >= 1, (
                "legacy mode must emit unet_wait_start for execution_prefill"
            )
        finally:
            mp._V2_PREFILL_WAIT_FOR_UNET = saved
            bridge.coordinator.close()


class TestV2PrefillOverlapError:
    """CLIP errors still fail open — graph falls back to original CLIPTextEncode."""

    def test_clip_error_returns_none_and_falls_back(self):
        """When wait_clip raises, prefill returns None; graph falls back."""
        bridge = _build_bridge(max_workers=1)

        # Make CLIP loader raise an error.
        bridge.coordinator.clip_loader = lambda key: (_ for _ in ()).throw(
            RuntimeError("simulated CLIP crash")
        )

        trace = RuntimeTrace(request_id="overlap-clip-error", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        prep = bridge._preparation
        assert prep is not None
        bridge.schedule_execution_prefill(trace=trace)

        # Prefill future should complete with None (the callback returned None).
        prefill_result = _wait_future(prep.prefill_future, timeout=5)
        assert prefill_result is None, (
            "prefill must return None when CLIP fails — triggers fallback"
        )

        # Trace should have execution_prefill_failed.
        failed_events = [
            e for e in trace.events if e.name == "execution_prefill_failed"
        ]
        assert len(failed_events) >= 1
        assert failed_events[0].metadata.get("phase") == "wait_clip"

        bridge.coordinator.close()

    def test_no_clip_returns_none(self):
        """When CLIP result is None, prefill returns None (graph falls back)."""
        bridge = _build_bridge(max_workers=1)
        bridge.coordinator.clip_loader = lambda key: None

        trace = RuntimeTrace(request_id="overlap-no-clip", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        prep = bridge._preparation
        assert prep is not None
        bridge.schedule_execution_prefill(trace=trace)

        prefill_result = _wait_future(prep.prefill_future, timeout=5)
        assert prefill_result is None, (
            "prefill must return None when clip is None"
        )

        failed_events = [
            e for e in trace.events if e.name == "execution_prefill_failed"
            and e.metadata.get("reason") == "no_clip"
        ]
        assert len(failed_events) >= 1

        bridge.coordinator.close()

    def test_unet_error_in_legacy_mode_returns_none(self):
        """Legacy mode: when wait_unet raises, prefill returns None."""
        bridge = _build_bridge(max_workers=1)

        # Make UNET loader raise so the future fails.
        bridge.coordinator.unet_loader = lambda key: (_ for _ in ()).throw(
            RuntimeError("simulated UNET crash")
        )

        trace = RuntimeTrace(request_id="overlap-unet-error", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        saved = mp._V2_PREFILL_WAIT_FOR_UNET
        try:
            mp._V2_PREFILL_WAIT_FOR_UNET = True
            bridge.schedule_execution_prefill(trace=trace)

            prep = bridge._preparation
            assert prep is not None
            prefill_result = _wait_future(prep.prefill_future, timeout=5)
            assert prefill_result is None

            failed_events = [
                e for e in trace.events if e.name == "execution_prefill_failed"
            ]
            assert len(failed_events) >= 1
            assert failed_events[0].metadata.get("phase") == "wait_unet"
        finally:
            mp._V2_PREFILL_WAIT_FOR_UNET = saved
            bridge.coordinator.close()


class TestV2PrefillOverlapIdempotent:
    """Idempotence: calling schedule_execution_prefill twice works."""

    def test_idempotence_preserved(self):
        """Calling schedule_execution_prefill twice returns True both times."""
        bridge = _build_bridge(max_workers=1)
        trace = RuntimeTrace(request_id="overlap-idempotent", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        first = bridge.schedule_execution_prefill(trace=trace)
        second = bridge.schedule_execution_prefill(trace=trace)

        assert first is True
        assert second is True

        prep = bridge._preparation
        assert prep is not None
        assert prep.prefill_future is not None
        prefill_result = _wait_future(prep.prefill_future, timeout=5)
        assert prefill_result is not None

        bridge.coordinator.close()

    def test_idempotent_after_completion(self):
        """Calling again after prefill completes returns True (already_scheduled)."""
        bridge = _build_bridge(max_workers=1)
        trace = RuntimeTrace(request_id="overlap-idem-complete", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        first = bridge.schedule_execution_prefill(trace=trace)
        assert first is True

        prep = bridge._preparation
        assert prep is not None
        _wait_future(prep.prefill_future, timeout=5)

        second = bridge.schedule_execution_prefill(trace=trace)
        assert second is True

        # Should emit "already_scheduled" skip event.
        skip_events = [
            e for e in trace.events if e.name == "execution_prefill_skip"
            and e.metadata.get("reason") == "already_scheduled"
        ]
        assert len(skip_events) >= 1

        bridge.coordinator.close()


class TestV2PrefillOverlapCombined:
    """Combined scenario: default + legacy env var path correctness."""

    def test_default_and_legacy_produce_different_trace_signatures(self):
        """Default produces execution_prefill_unet_status; legacy does not."""
        for use_legacy, expected_status_count in [(False, 1), (True, 0)]:
            bridge = _build_bridge(max_workers=1)
            trace = RuntimeTrace(
                request_id=f"overlap-sig-{'legacy' if use_legacy else 'default'}",
                process="remote",
            )
            plan = _make_plan()

            saved = mp._V2_PREFILL_WAIT_FOR_UNET
            try:
                mp._V2_PREFILL_WAIT_FOR_UNET = use_legacy
                bridge.prepare(plan, trace=trace)

                bridge.schedule_execution_prefill(trace=trace)

                prep = bridge._preparation
                assert prep is not None
                _wait_future(prep.prefill_future, timeout=5)

                status_count = len([
                    e for e in trace.events
                    if e.name == "execution_prefill_unet_status"
                ])
                assert status_count == expected_status_count, (
                    f"expected {expected_status_count} unet_status events "
                    f"({'legacy' if use_legacy else 'default'}), got {status_count}"
                )

                # Both modes emit execution_prefill_completed with wait_for_unet flag.
                completed = [
                    e for e in trace.events if e.name == "execution_prefill_completed"
                ]
                assert len(completed) >= 1
                assert completed[0].metadata.get("wait_for_unet") == use_legacy

            finally:
                mp._V2_PREFILL_WAIT_FOR_UNET = saved
                bridge.coordinator.close()


class TestV2LoaderBridgeMaxWorkers:
    """Default max_workers=3 enables UNET+CLIP+VAE concurrent loading."""

    def test_default_creates_coordinator_with_three_workers(self):
        bridge = mp.V2LoaderBridge()
        assert bridge.coordinator._max_workers == 3

    def test_coordinator_caps_at_three(self):
        bridge = mp.V2LoaderBridge(max_workers=10)
        assert bridge.coordinator._max_workers == 3

    def test_coordinator_accepts_one_worker(self):
        bridge = mp.V2LoaderBridge(max_workers=1)
        assert bridge.coordinator._max_workers == 1


class TestV2LoaderBridgeCloseWorkers:
    """close_workers waits for restore futures and shuts down the pool;
    the coordinator recreates a pool on the next submit."""

    def test_close_workers_waits_for_restore_futures_and_shuts_pool(self):
        bridge = _build_bridge(max_workers=2)
        plan = _make_plan()
        bridge.prepare(plan)
        prep = bridge._preparation
        assert prep is not None
        assert bridge.coordinator._pool is not None, "pool must exist after prepare"
        bridge.close_workers()
        assert bridge.coordinator._pool is None, "pool must be None after close_workers"
        assert prep.unet_future is not None and prep.unet_future.done()
        assert prep.clip_future is not None and prep.clip_future.done()

    def test_coordinator_recreates_pool_for_execution_prefill_after_close(self):
        bridge = _build_bridge(max_workers=2)
        plan = _make_plan()
        bridge.prepare(plan)
        bridge.close_workers()
        assert bridge.coordinator._pool is None, "pool must be None after close_workers"
        trace = RuntimeTrace(request_id="close-recreate", process="remote")
        scheduled = bridge.schedule_execution_prefill(trace=trace)
        assert scheduled is True, "execution prefill must still succeed"
        assert bridge.coordinator._pool is not None, "pool must be recreated"
        prep = bridge._preparation
        assert prep is not None
        result = _wait_future(prep.prefill_future, timeout=5)
        assert result is not None
        bridge.close_workers()

    def test_close_workers_swallows_worker_exceptions(self):
        def failing_loader(key):
            raise RuntimeError("simulated worker crash")
        bridge = _build_bridge(unet_loader=failing_loader, max_workers=1)
        plan = _make_plan()
        bridge.prepare(plan)
        prep = bridge._preparation
        assert prep is not None
        assert prep.unet_future is not None
        close_workers_raised = False
        try:
            bridge.close_workers()
        except Exception:
            close_workers_raised = True
        assert not close_workers_raised, "close_workers must swallow worker exceptions"
        assert bridge.coordinator._pool is None, "pool must be shut down even with worker errors"

    def test_close_workers_no_preparation_is_noop(self):
        bridge = mp.V2LoaderBridge(max_workers=2)
        assert bridge._preparation is None
        bridge.close_workers()
        assert bridge.coordinator._pool is None
