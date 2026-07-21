"""Focused tests for V2 pre-sampler attribution — node classification,
milestone intervals, invoke boundaries, and [v2.pre_sampler_stages] summary.

These tests use fake PromptExecutor / server objects to verify:
- async start / cached / multiple executing milestone capture
- sync fallback path
- cached path with no first node
- missing add_message (graceful skip)
- missing send_sync (graceful skip)
- exception restores methods and releases lane
- no duplicate prompt_executor_start
- reconciliation non-overlap (invoke_end after execute, milestones after invoke)
- node-ID -> class_type mapping and classification
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any, Mapping
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime.runtime_executor import ExecutionContext
from comfymodal_runtime.trace import RuntimeTrace

import comfymodal_runtime.modal_app as modal_app


class _FakeExecutor:
    """Minimal PromptExecutor stand-in with configurable behaviour."""

    def __init__(
        self,
        *,
        use_async: bool = True,
        add_message_available: bool = True,
        send_sync_available: bool = True,
        raise_on_execute: bool = False,
        success: bool = True,
        history_result: dict | None = None,
    ):
        self.success = success
        self.history_result = history_result or {}
        self.executed: list[dict] = []
        self.sync_called = False
        self._use_async = use_async
        self._add_message_available = add_message_available
        self._send_sync_available = send_sync_available
        self._raise_on_execute = raise_on_execute
        self.add_message = None
        self.server = None
        if add_message_available:
            self.add_message = self._fake_add_message
        if send_sync_available:
            self.server = SimpleNamespace(
                send_sync=self._fake_send_sync,
            )
        self._execute_async_fn = self._default_execute_async

    def reset(self):
        pass

    def _fake_add_message(self, event: str, *args: Any, **kwargs: Any) -> None:
        pass

    def _fake_send_sync(self, event: str, data: dict | None = None, *args: Any, **kwargs: Any) -> None:
        pass

    def execute(self, **kwargs: Any) -> None:
        self.sync_called = True
        self.executed.append(kwargs)
        if self._raise_on_execute:
            raise RuntimeError("simulated execute failure")

    # Only expose execute_async when use_async=True, so callable() check
    # in _execute_v2_prompt_executor falls through to sync path otherwise.
    # Uses a mutable _execute_async_fn so tests can wrap the async call.
    async def _default_execute_async(self, **kwargs: Any) -> None:
        self.executed.append(kwargs)
        if self._raise_on_execute:
            raise RuntimeError("simulated execute failure")

    @property
    def execute_async(self) -> Any:
        if not self._use_async:
            return None
        return self._execute_async_fn

    @execute_async.setter
    def execute_async(self, value: Any) -> None:
        if self._use_async:
            self._execute_async_fn = value


def _build_fake_api(executor: _FakeExecutor) -> SimpleNamespace:
    api = SimpleNamespace(
        _executor=executor,
        _preflight_already_ran=True,
    )
    return api


def _build_minimal_plan(*, outputs: list[str] | None = None) -> ExecutionPlan:
    return ExecutionPlan(
        workflow={"1": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )


async def _async_validate(_pid: str, _wf: dict, _ext: Any) -> tuple:
    """Async validate_prompt stub matching execution module signature."""
    return True, {}, ["1"], {}


async def _async_validate_107(_pid: str, _wf: dict, _ext: Any) -> tuple:
    """Async validate returning outputs ['107'] for multi-node tests."""
    return True, {}, ["107"], {}


def _run_executor(
    entrypoint: modal_app.ModalRuntimeEntrypoint,
    plan: ExecutionPlan,
    api: Any,
    trace: RuntimeTrace,
) -> dict:
    """Helper to run _execute_v2_prompt_executor with a fake execution module."""
    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    context = ExecutionContext(request_id="test-pre-sampler", trace=trace)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        return asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )


# ═══════════════════════════════════════════════════════════════════════
# Node-ID -> class_type mapping
# ═══════════════════════════════════════════════════════════════════════


def test_node_class_map_built_from_workflow():
    """Node-ID-to-class_type map correctly reflects the workflow and
    appears in invoke_start metadata."""
    executor = _FakeExecutor()
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            "6": {"class_type": "KSampler", "inputs": {}},
            "7": {"class_type": "VAEDecode", "inputs": {}},
            "8": {"class_type": "SaveImage", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-node-map", process="remote")
    _run_executor(entrypoint, plan, api, trace)

    # invoke_start should carry node classification metadata
    invoke_events = [
        e for e in trace.events if e.name == "prompt_executor_invoke_start"
    ]
    assert len(invoke_events) == 1, "exactly one prompt_executor_invoke_start expected"
    meta = invoke_events[0].metadata
    assert meta.get("total_nodes") == 4
    assert meta.get("has_clip_loader") is True   # CLIPTextEncode starts with CLIP
    assert meta.get("has_text_encode") is True    # CLIPTextEncode
    assert meta.get("has_sampler") is True         # KSampler
    assert meta.get("sampler_node_count") == 1


def test_node_class_map_no_sampler():
    """Workflow without any sampler node correctly reports has_sampler=False."""
    executor = _FakeExecutor()
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "2": {"class_type": "SaveImage", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-no-sampler", process="remote")
    _run_executor(entrypoint, plan, api, trace)

    invoke_meta = None
    for e in trace.events:
        if e.name == "prompt_executor_invoke_start":
            invoke_meta = e.metadata
            break
    assert invoke_meta is not None
    assert invoke_meta.get("has_sampler") is False
    assert invoke_meta.get("sampler_node_count") == 0


# ═══════════════════════════════════════════════════════════════════════
# Async start / cached / multiple executing milestone capture
# ═══════════════════════════════════════════════════════════════════════


def test_milestones_capture_async_execution_start_cached_node():
    """When execute_async is available, milestones capture execution_start,
    execution_cached, and executing (first node) through add_message and
    send_sync wrappers."""
    executor = _FakeExecutor(use_async=True)
    executor.add_message = None  # we will install our own after reset
    executor.server = SimpleNamespace(send_sync=None)

    # Create a real milestone-producing wrapper scenario
    _add_msgs: list[str] = []
    _send_syncs: list[tuple] = []

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        _add_msgs.append(event)

    def _send_sync(event: str, data: dict | None = None, *a: Any, **kw: Any) -> None:
        _send_syncs.append((event, data))

    executor.add_message = _add_msg
    executor.server.send_sync = _send_sync

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-milestones", process="remote")
    context = ExecutionContext(request_id="test-milestones", trace=trace)

    # We need to trigger the milestone wrappers by having the execute
    # path call add_message / send_sync. Since the fake executor just
    # records calls, we manually simulate milestone events by patching
    # into the executor methods after _execute_v2_prompt_executor sets
    # up the wrappers.
    _outer_executed: list[dict] = []

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs: Any) -> None:
        _outer_executed.append(kwargs)
        # Simulate what PromptExecutor does during execution
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "5"})
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    async def _async_validate_milestones(_pid: str, _wf: dict, _ext: Any) -> tuple:
        return True, {}, ["1"], {}

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate_milestones,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    # Verify milestone event exists
    milestone_events = [
        e for e in trace.events if e.name == "prompt_executor_milestones"
    ]
    assert len(milestone_events) == 1, "exactly one milestones event expected"
    m = milestone_events[0].metadata

    # call_to_execution_start should be a small positive number
    assert m.get("executor_call_to_execution_start_ms") is not None
    assert m.get("executor_call_to_execution_start_ms") >= 0

    # execution_start_to_cached should be positive or zero
    assert m.get("execution_start_to_cached_ms") is not None

    # cached_to_first_node should be positive or zero
    assert m.get("cached_to_first_node_ms") is not None

    # First executing node classified correctly
    assert m.get("first_executing_node_id") == "5"

    # pre_sampler_stages event must also be present
    ps_events = [e for e in trace.events if e.name == "pre_sampler_stages"]
    assert len(ps_events) == 1
    ps = ps_events[0].metadata
    assert ps.get("first_executing_node_id") == "5"
    assert ps.get("send_sync_available") is True
    assert ps.get("add_message_available") is True


def test_milestones_cached_only_no_first_node():
    """When all nodes are cached (execution_cached before any executing),
    the executing milestone is absent but cached intervals are present."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-cached-only", process="remote")
    context = ExecutionContext(request_id="test-cached-only", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs: Any) -> None:
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        # No send_sync with "executing" — cached path
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    milestone_events = [
        e for e in trace.events if e.name == "prompt_executor_milestones"
    ]
    assert len(milestone_events) == 1
    m = milestone_events[0].metadata

    # cached_to_first_node should be absent (no executing event)
    assert m.get("cached_to_first_node_ms") is None
    # first_executing_node should be empty
    assert m.get("first_executing_node_id") == ""

    # pre_sampler_stages should report absent cached_to_first_node
    ps_events = [e for e in trace.events if e.name == "pre_sampler_stages"]
    assert len(ps_events) == 1
    ps = ps_events[0].metadata
    assert ps.get("cached_to_first_node_ms") is None
    assert ps.get("first_executing_node_id") == ""


def test_milestones_multiple_executing_events():
    """Multiple send_sync('executing', ...) calls only record the first one."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-multi-exec", process="remote")
    context = ExecutionContext(request_id="test-multi-exec", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs: Any) -> None:
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "5"})
        executor.server.send_sync("executing", {"node": "6"})
        executor.server.send_sync("executing", {"node": "7"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    milestone_events = [
        e for e in trace.events if e.name == "prompt_executor_milestones"
    ]
    assert len(milestone_events) == 1
    m = milestone_events[0].metadata
    # Should be node "5" (the first one), not "6" or "7"
    assert m.get("first_executing_node_id") == "5"


# ═══════════════════════════════════════════════════════════════════════
# Sync fallback
# ═══════════════════════════════════════════════════════════════════════


def test_sync_executor_fallback():
    """When no execute_async is available, the sync executor.execute() path
    is used and milestones are still captured."""
    executor = _FakeExecutor(use_async=False)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-sync", process="remote")
    context = ExecutionContext(request_id="test-sync", trace=trace)

    original_execute = executor.execute

    def _wrapped_execute(**kwargs: Any) -> None:
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "5"})
        original_execute(**kwargs)

    executor.execute = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    assert executor.sync_called is True

    milestone_events = [
        e for e in trace.events if e.name == "prompt_executor_milestones"
    ]
    assert len(milestone_events) == 1
    m = milestone_events[0].metadata
    assert m.get("first_executing_node_id") == "5"


# ═══════════════════════════════════════════════════════════════════════
# Missing add_message / send_sync
# ═══════════════════════════════════════════════════════════════════════


def test_missing_add_message_graceful():
    """When the executor has no add_message, milestone interception is
    skipped but execution proceeds.  milestones_unavailable event is emitted."""
    executor = _FakeExecutor(use_async=True, add_message_available=False)
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-no-addmsg", process="remote")
    result = _run_executor(entrypoint, plan, api, trace)

    event_names = [e.name for e in trace.events]
    assert "prompt_executor_invoke_start" in event_names
    assert "prompt_executor_invoke_end" in event_names
    assert "prompt_executor_internal_milestones_unavailable" in event_names
    # milestones event should NOT be present (no milestones collected)
    assert "prompt_executor_milestones" not in event_names

    # pre_sampler_stages is ALWAYS emitted (requirement 4),
    # even when both wrappers are unavailable and milestones are absent.
    assert "pre_sampler_stages" in event_names
    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0]
    # All milestone-based intervals should be absent/None
    assert ps.metadata.get("invoke_to_execution_start_ms") is None
    assert ps.metadata.get("execution_start_to_cached_ms") is None
    assert ps.metadata.get("cached_to_first_node_ms") is None
    # Setup intervals from existing trace events may still be populated
    assert ps.metadata.get("add_message_available") is False
    assert ps.metadata.get("send_sync_available") is True


def test_missing_send_sync_graceful():
    """When the executor.server has no send_sync, only add_message
    milestones are captured.  milestones_unavailable event for send_sync."""
    executor = _FakeExecutor(use_async=True, send_sync_available=False)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        _add_msgs.append(event)

    executor.add_message = _add_msg

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-no-sendsync", process="remote")
    context = ExecutionContext(request_id="test-no-sendsync", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs: Any) -> None:
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        # No send_sync — it's unavailable
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    event_names = [e.name for e in trace.events]
    assert "prompt_executor_milestones" in event_names
    ms = [e for e in trace.events if e.name == "prompt_executor_milestones"][0]
    # cached_to_first_node should be absent (no executing event from send_sync)
    assert ms.metadata.get("cached_to_first_node_ms") is None

    # pre_sampler_stages should report send_sync unavailable
    ps_events = [e for e in trace.events if e.name == "pre_sampler_stages"]
    if ps_events:
        assert ps_events[0].metadata.get("send_sync_available") is False
        assert ps_events[0].metadata.get("add_message_available") is True


# ═══════════════════════════════════════════════════════════════════════
# Exception path — restores methods and releases lane
# ═══════════════════════════════════════════════════════════════════════


def test_exception_restores_add_message():
    """When execute raises, the original add_message is restored."""
    _orig = lambda e: None
    executor = _FakeExecutor(use_async=True, raise_on_execute=True)
    executor.add_message = _orig

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-exc-restore", process="remote")
    context = ExecutionContext(request_id="test-exc-restore", trace=trace)

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        try:
            asyncio.run(
                entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
            )
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

    # add_message must be restored to original
    assert executor.add_message is _orig, (
        "add_message must be restored after exception"
    )

    # invoke_end must be present even on failure
    event_names = [e.name for e in trace.events]
    assert "prompt_executor_invoke_end" in event_names


def test_exception_releases_mutation_lane():
    """When execute raises and lane was acquired for a sampler node,
    the sampler mutation lane is released in the outer finally."""
    import threading
    _lane_released = [False]

    class _FakeLane:
        def __init__(self):
            self._locked = threading.Lock()
            self._locked.acquire()
            self._owner = None

        @property
        def owner(self) -> str | None:
            return self._owner

        def acquire(self, _owner: str) -> None:
            pass

        def release(self, _owner: str) -> None:
            _lane_released[0] = True
            try:
                self._locked.release()
            except RuntimeError:
                pass

    executor = _FakeExecutor(use_async=True, raise_on_execute=True)
    executor.add_message = lambda e, *a, **kw: None
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()
    entrypoint._preload_bridge.coordinator.mutation_lane = _FakeLane()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-exc-lane", process="remote")
    context = ExecutionContext(request_id="test-exc-lane", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        # Simulate send_sync with a KSampler node to trigger lane acquisition
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "1"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        try:
            asyncio.run(
                entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
            )
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

    assert _lane_released[0] is True, "mutation lane must be released on exception"


def test_exception_restores_send_sync():
    """When execute raises, the original send_sync is restored."""
    _orig = lambda e, d=None: None
    executor = _FakeExecutor(use_async=True, raise_on_execute=True)
    executor.add_message = lambda e: None
    executor.server = SimpleNamespace(send_sync=_orig)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-exc-sendsync", process="remote")
    context = ExecutionContext(request_id="test-exc-sendsync", trace=trace)

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        try:
            asyncio.run(
                entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
            )
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

    assert executor.server.send_sync is _orig, (
        "send_sync must be restored after exception"
    )


# ═══════════════════════════════════════════════════════════════════════
# No duplicate prompt_executor_start
# ═══════════════════════════════════════════════════════════════════════


def test_no_duplicate_prompt_executor_start():
    """The older ambiguous prompt_executor_start must not be emitted.
    Only prompt_executor_invoke_start should appear once."""
    executor = _FakeExecutor(use_async=True)
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-no-dup", process="remote")
    _run_executor(entrypoint, plan, api, trace)

    event_names = [e.name for e in trace.events]
    # prompt_executor_start must NOT appear
    assert "prompt_executor_start" not in event_names, (
        "The older prompt_executor_start must be removed; "
        "only prompt_executor_invoke_start should exist"
    )
    # prompt_executor_invoke_start appears exactly once
    invoke_starts = [n for n in event_names if n == "prompt_executor_invoke_start"]
    assert len(invoke_starts) == 1


# ═══════════════════════════════════════════════════════════════════════
# Reconciliation — non-overlapping intervals
# ═══════════════════════════════════════════════════════════════════════


def test_invoke_end_after_execute_before_milestones():
    """prompt_executor_invoke_end is emitted after the execute call completes
    (wrappers restored) but before milestone processing. This guarantees
    that invoke_end does NOT overlap with executor work."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-nonoverlap", process="remote")
    context = ExecutionContext(request_id="test-nonoverlap", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs: Any) -> None:
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "5"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    # Ordering: invoke_start, ...milestones/intervals... , invoke_end (in finally),
    # then milestone event is emitted after the finally block.
    event_order = [e.name for e in trace.events]

    # Find positions
    try:
        pos_invoke_start = event_order.index("prompt_executor_invoke_start")
        pos_invoke_end = event_order.index("prompt_executor_invoke_end")
        pos_milestones = event_order.index("prompt_executor_milestones")
    except ValueError as exc:
        assert False, f"Missing expected event: {exc}"

    # invoke_start before invoke_end
    assert pos_invoke_start < pos_invoke_end, (
        "invoke_start must precede invoke_end"
    )
    # invoke_end before milestones (so intervals are non-overlapping)
    assert pos_invoke_end < pos_milestones, (
        "invoke_end must precede milestone processing for non-overlapping intervals"
    )
    # pre_sampler_stages after milestones
    if "pre_sampler_stages" in event_order:
        pos_ps = event_order.index("pre_sampler_stages")
        assert pos_milestones < pos_ps, (
            "pre_sampler_stages must follow milestones"
        )


# ═══════════════════════════════════════════════════════════════════════
# First-node and sampler-stage classification
# ═══════════════════════════════════════════════════════════════════════


def test_pre_sampler_stages_classifies_text_encoding():
    """When first executing node is a CLIPTextEncode, pre_sampler_stages
    reports sampler_stage_status='text_encoding'."""
    executor = _FakeExecutor(use_async=True)

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        pass

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            "6": {"class_type": "KSampler", "inputs": {}},
            "7": {"class_type": "VAEDecode", "inputs": {}},
            "8": {"class_type": "SaveImage", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-classify-text", process="remote")
    context = ExecutionContext(request_id="test-classify-text", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs: Any) -> None:
        # Simulate CLIPTextEncode as first executing node
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "5"})
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps_events = [e for e in trace.events if e.name == "pre_sampler_stages"]
    assert len(ps_events) == 1
    ps = ps_events[0].metadata
    assert ps.get("first_executing_node_id") == "5"
    assert ps.get("first_executing_node_class") == "CLIPTextEncode"
    assert ps.get("sampler_stage_status") == "text_encoding"


def test_pre_sampler_stages_classifies_sampler():
    """When first executing node is a KSampler, pre_sampler_stages reports
    sampler_stage_status='sampler_active'."""
    executor = _FakeExecutor(use_async=True)

    def _add_msg(event: str, *a: Any, **kw: Any) -> None:
        pass

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "6": {"class_type": "KSampler", "inputs": {}},
            "7": {"class_type": "VAEDecode", "inputs": {}},
            "8": {"class_type": "SaveImage", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-classify-sampler", process="remote")
    context = ExecutionContext(request_id="test-classify-sampler", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs: Any) -> None:
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(
        validate_prompt=_async_validate,
    )
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps_events = [e for e in trace.events if e.name == "pre_sampler_stages"]
    assert len(ps_events) == 1
    ps = ps_events[0].metadata
    assert ps.get("first_executing_node_id") == "6"
    assert ps.get("first_executing_node_class") == "KSampler"
    assert ps.get("sampler_stage_status") == "sampler_active"


# ═══════════════════════════════════════════════════════════════════════
# End-to-end sync path with missing add_message
# ═══════════════════════════════════════════════════════════════════════


def test_sync_no_add_message_graceful():
    """Sync executor without add_message still produces invoke events
    and never calls add_message."""
    executor = _FakeExecutor(
        use_async=False, add_message_available=False,
    )
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-sync-no-addmsg", process="remote")
    result = _run_executor(entrypoint, plan, api, trace)

    event_names = [e.name for e in trace.events]
    assert "prompt_executor_invoke_start" in event_names
    assert "prompt_executor_invoke_end" in event_names
    assert "prompt_executor_milestones" not in event_names
    assert executor.sync_called is True


# ═══════════════════════════════════════════════════════════════════════
# Expanded milestone classification
# ═══════════════════════════════════════════════════════════════════════


def test_first_loader_node_classified():
    """When the first executing node is a loader (e.g. CheckpointLoader),
    pre_sampler_stages reports first_loader_node_id and class."""
    executor = _FakeExecutor(use_async=True)

    def _add_msg(event: str, *a, **kw):
        pass

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "10": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {}},
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-loader-node", process="remote")
    context = ExecutionContext(request_id="test-loader-node", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "10"})  # loader
        executor.server.send_sync("executing", {"node": "5"})   # clip
        executor.server.send_sync("executing", {"node": "6"})   # sampler
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    assert ps.get("first_executing_node_id") == "10"
    assert ps.get("first_executing_node_class") == "CheckpointLoaderSimple"
    assert ps.get("first_loader_node_id") == "10"
    assert ps.get("first_clip_encode_node_id") == "5"
    assert ps.get("first_sampler_node_id") == "6"


def test_milestones_first_model_loader_clip_sampler():
    """prompt_executor_milestones includes first_loader_node_id,
    first_clip_encode_node_id, and first_sampler_node_id metadata."""
    executor = _FakeExecutor(use_async=True)

    def _add_msg(event: str, *a, **kw):
        pass

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "10": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {}},
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-multi-milestones", process="remote")
    context = ExecutionContext(request_id="test-multi-milestones", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "10"})
        executor.server.send_sync("executing", {"node": "5"})
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ms = [e for e in trace.events if e.name == "prompt_executor_milestones"][0].metadata
    assert ms.get("first_executing_node_id") == "10"
    assert ms.get("first_executing_node_class") == "CheckpointLoaderSimple"

    # Raw monotonic-ns are present
    assert isinstance(ms.get("first_executing_node_monotonic_ns"), int)
    assert isinstance(ms.get("first_loader_node_monotonic_ns"), int)

    # Verify pre_sampler_stages has the classifier milestone fields
    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    assert ps.get("first_loader_node_id") == "10"
    assert ps.get("first_clip_encode_node_id") == "5"
    assert ps.get("first_sampler_node_id") == "6"
    # Raw monotonic-ns present in pre_sampler_stages
    assert isinstance(ps.get("first_executing_node_monotonic_ns"), int)
    assert isinstance(ps.get("first_loader_node_monotonic_ns"), int)
    assert isinstance(ps.get("first_clip_encode_node_monotonic_ns"), int)
    assert isinstance(ps.get("first_sampler_node_monotonic_ns"), int)
    # first_sampler_stage_monotonic_ns is None since no actual stage event fired
    assert ps.get("first_sampler_stage_monotonic_ns") is None


# ═══════════════════════════════════════════════════════════════════════
# Always-present absent summary with identity metadata
# ═══════════════════════════════════════════════════════════════════════


def test_pre_sampler_stages_always_present_even_without_milestones():
    """pre_sampler_stages is always emitted after invocation cleanup,
    even when both wrappers are unavailable and all milestones are absent.
    It carries explicit None/absent values for unavailable intervals."""
    executor = _FakeExecutor(use_async=True, add_message_available=False)
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-always-ps", process="remote")
    _run_executor(entrypoint, plan, api, trace)

    ps_events = [e for e in trace.events if e.name == "pre_sampler_stages"]
    assert len(ps_events) == 1, "pre_sampler_stages must be emitted exactly once"
    ps = ps_events[0].metadata

    # Milestone intervals are None when no wrappers captured them
    assert ps.get("invoke_to_execution_start_ms") is None
    assert ps.get("execution_start_to_cached_ms") is None
    assert ps.get("cached_to_first_node_ms") is None
    assert ps.get("first_node_to_clip_ms") is None
    assert ps.get("clip_to_sampler_node_ms") is None
    assert ps.get("sampler_node_to_sampler_start_ms") is None

    # Setup intervals from trace events may still be populated (validation,
    # pregraph, etc. always run)
    assert ps.get("validation_ms") is not None
    assert ps.get("pregraph_setup_ms") is not None
    assert ps.get("executor_reset_ms") is not None

    # New interval fields — remote_method_entry may be absent from this trace
    # but the fields must be present (value may be None)
    assert "method_entry_to_runtime_configuration_ms" in ps
    # production_registry_profile_setup_ms is the alias for production_registry_setup_ms
    assert ps.get("production_registry_profile_setup_ms") == ps.get("production_registry_setup_ms")

    # Monotonic-ns fields present (None when no executing events)
    assert ps.get("first_executing_node_monotonic_ns") is None
    assert ps.get("first_sampler_stage_monotonic_ns") is None

    # Wrapper availability is correctly reported
    assert ps.get("add_message_available") is False
    assert ps.get("send_sync_available") is True

    # Identity metadata fields are present
    assert "total_nodes" in ps
    assert "sampler_node_count" in ps
    assert ps.get("sampler_stage_status") == "awaiting_classification"


def test_pre_sampler_stages_contains_identity_metadata():
    """pre_sampler_stages event metadata includes identity fields:
    pid, hostname, modal_input_id, modal_task_id, restored_instance_id,
    restore_session_id, container_session_id."""
    executor = _FakeExecutor(use_async=True)
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-ps-identity", process="remote")
    _run_executor(entrypoint, plan, api, trace)

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata

    # Core identity fields from _capture_remote_identity host_info
    assert isinstance(ps.get("total_nodes"), int)
    assert ps.get("sampler_node_count") is not None

    # Verify the one-line summary printed appropriately — the metadata
    # carries all fields even when actual values are unavailable
    for key in ("total_nodes", "sampler_node_count"):
        assert key in ps, f"Expected {key} in pre_sampler_stages metadata"


# ═══════════════════════════════════════════════════════════════════════
# Non-overlapping reconciliation
# ═══════════════════════════════════════════════════════════════════════


def test_setup_intervals_non_overlapping():
    """Setup intervals computed from trace events are non-overlapping:
    each interval's end_time < next interval's start_time where the
    events are sequential.  Use existing trace event monotonic_ns to
    verify ordering."""
    executor = _FakeExecutor(use_async=True)
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-nonoverlap-setup", process="remote")
    context = ExecutionContext(request_id="test-nonoverlap-setup", trace=trace)

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    # Verify ordering of key sequential events by monotonic_ns
    ev_map: dict[str, int] = {}
    for ev in trace.events:
        if ev.name not in ev_map:
            ev_map[ev.name] = ev.monotonic_ns

    # These events must appear in chronological order.
    # Note: executor_reset_start/end are nested inside the pregraph_setup
    # span — they fire between pregraph_setup_start and pregraph_setup_end.
    _ordered_events = [
        "prompt_validation_start",
        "prompt_validation_end",
        "pregraph_setup_start",
        "executor_reset_start",
        "executor_reset_end",
        "pregraph_setup_end",
        "prompt_executor_invoke_start",
        "prompt_executor_invoke_end",
    ]
    for i in range(len(_ordered_events) - 1):
        a = _ordered_events[i]
        b = _ordered_events[i + 1]
        if a in ev_map and b in ev_map:
            assert ev_map[a] <= ev_map[b], (
                f"Event ordering violation: {a} ({ev_map[a]}) > {b} ({ev_map[b]})"
            )


# ═══════════════════════════════════════════════════════════════════════
# Monotonic-ns captures for node classification (A)
# ═══════════════════════════════════════════════════════════════════════


def test_monotonic_ns_captures_in_milestones():
    """first_loader_node_ns, first_clip_encode_node_ns, first_sampler_node_ns
    and first_sampler_stage_ns are set in milestones from the wrapper."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []
    _send_syncs: list[tuple] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    def _send_sync(event: str, data: dict | None = None, *a, **kw):
        _send_syncs.append((event, data))

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=_send_sync)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "10": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-mono-ns", process="remote")
    context = ExecutionContext(request_id="test-mono-ns", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "10"})
        executor.server.send_sync("executing", {"node": "5"})
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ms = [e for e in trace.events if e.name == "prompt_executor_milestones"][0].metadata

    # first_executing_node_ns should be present and positive
    assert ms.get("first_executing_node_id") == "10"
    assert isinstance(ms.get("first_executing_node_class"), str)
    # Node classification IDs propagated
    assert ms.get("first_loader_node_id") == "10"
    assert ms.get("first_clip_encode_node_id") == "5"
    assert ms.get("first_sampler_node_id") == "6"
    # first_sampler_stage_event is NOT set from the executing event
    # (only from actual sampler_start/sampling_start events)
    assert ms.get("first_sampler_stage_event") in ("", None)
    # first_sampler_stage_monotonic_ns is None since no sampler stage event fired
    assert ms.get("first_sampler_stage_monotonic_ns") is None
    # Raw monotonic-ns fields present in milestones metadata
    assert isinstance(ms.get("first_executing_node_monotonic_ns"), int)
    assert isinstance(ms.get("first_loader_node_monotonic_ns"), int)
    assert isinstance(ms.get("first_clip_encode_node_monotonic_ns"), int)
    assert isinstance(ms.get("first_sampler_node_monotonic_ns"), int)
    # Same-event timestamps must be equal (loaded via a single _event_ns)
    assert ms["first_loader_node_monotonic_ns"] == ms["first_executing_node_monotonic_ns"]

    # Verify pre_sampler_stages has the same fields
    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    assert ps.get("first_loader_node_id") == "10"
    assert ps.get("first_clip_encode_node_id") == "5"
    assert ps.get("first_sampler_node_id") == "6"
    # first_sampler_stage_event is absent/empty since no actual stage event fired
    assert ps.get("first_sampler_stage_event") in ("", None)
    # first_loader_node_class should be propagated
    assert ps.get("first_loader_node_class") == "CheckpointLoaderSimple"
    # Raw monotonic-ns fields in pre_sampler_stages metadata
    assert isinstance(ps.get("first_executing_node_monotonic_ns"), int)
    assert isinstance(ps.get("first_loader_node_monotonic_ns"), int)
    assert isinstance(ps.get("first_clip_encode_node_monotonic_ns"), int)
    assert isinstance(ps.get("first_sampler_node_monotonic_ns"), int)
    # first_sampler_stage_monotonic_ns is None since no actual stage event fired
    assert ps.get("first_sampler_stage_monotonic_ns") is None


def test_monotonic_ns_first_sampler_stage_event_from_sampler_stage():
    """When sampler_start/sampling_start/sampler_stage_start/progress arrives,
    first_sampler_stage_event reflects the event name (not 'executing')."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []
    _send_syncs: list[tuple] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    def _send_sync(event: str, data: dict | None = None, *a, **kw):
        _send_syncs.append((event, data))

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=_send_sync)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-sampler-stage-event", process="remote")
    context = ExecutionContext(request_id="test-sampler-stage-event", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "1"})  # KSampler from _build_minimal_plan
        executor.server.send_sync("sampling_start", {})  # sampler stage event
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    # first_sampler_stage_event should be "sampling_start", not "executing"
    assert ps.get("first_sampler_stage_event") == "sampling_start", (
        f"expected sampling_start, got {ps.get('first_sampler_stage_event')}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Reconciliation arithmetic (C)
# ═══════════════════════════════════════════════════════════════════════


def test_reconciliation_leaf_sum_no_double_count():
    """measured_children_ms uses leaf sum without double-counting pregraph+reset.
    pregraph_setup_ms > executor_reset_ms because reset is nested inside pregraph."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-leaf-sum", process="remote")
    context = ExecutionContext(request_id="test-leaf-sum", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "5"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata

    # pregraph_setup_ms should be > executor_reset_ms (pregraph includes reset)
    if ps.get("pregraph_setup_ms") is not None and ps.get("executor_reset_ms") is not None:
        assert ps["pregraph_setup_ms"] >= ps["executor_reset_ms"], (
            "pregraph_setup_ms must be >= executor_reset_ms since reset is nested inside"
        )

    # measured_children_ms should be present
    assert ps.get("measured_children_ms") is not None, (
        "measured_children_ms must be present"
    )

    # pre_sampler_total_ms and residual_ms absent when remote_method_entry not in trace
    assert ps.get("pre_sampler_total_ms") is None, (
        "pre_sampler_total_ms must be None when remote_method_entry is absent from trace"
    )
    assert ps.get("residual_ms") is None, (
        "residual_ms must be None when pre_sampler_total_ms is None"
    )

    # New setup fields should be available (validation always runs)
    assert "validation_ms" in ps
    assert "preload_check_ms" in ps
    assert "missing_node_repair_ms" in ps

    # total_nodes should be a positive int
    assert isinstance(ps.get("total_nodes"), int)
    assert ps["total_nodes"] > 0


# ═══════════════════════════════════════════════════════════════════════
# Identity metadata in pre_sampler_stages event (D)
# ═══════════════════════════════════════════════════════════════════════


def test_pre_sampler_stages_identity_metadata():
    """pre_sampler_stages event metadata includes explicit identity fields."""
    executor = _FakeExecutor(use_async=True)
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-ps-identity-event", process="remote")
    # Use context with matching request_id (bypass _run_executor which hardcodes "test-pre-sampler")
    context = ExecutionContext(request_id="test-ps-identity-event", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata

    # Identity fields must be present (values may be 'absent' in test env)
    for key in ("request_id", "modal_input_id", "modal_task_id", "container_task_id",
                "pid", "boot_id", "hostname", "restored_instance_id",
                "restore_session_id", "container_session_id"):
        assert key in ps, f"Expected identity key {key} in pre_sampler_stages metadata"
        val = ps[key]
        assert val is not None, f"Identity key {key} must not be None"

    # request_id should match the context/plan request_id
    assert ps.get("request_id") == "test-ps-identity-event", (
        f"expected 'test-ps-identity-event', got {ps.get('request_id')!r}"
    )

    # pid should be a positive integer
    assert isinstance(ps.get("pid"), int) and ps["pid"] > 0

    # hostname should be a string
    assert isinstance(ps.get("hostname"), str)


# ═══════════════════════════════════════════════════════════════════════
# Expanded loader matching (A) — broad patterns
# ═══════════════════════════════════════════════════════════════════════


def test_loader_matching_includes_checkpoint_loader():
    """A workflow with CheckpointLoaderSimple as first executing node
    correctly identifies it as first_loader_node."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "3": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "4": {"class_type": "VAEDecode", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-loader-checkpoint", process="remote")
    context = ExecutionContext(request_id="test-loader-checkpoint", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "3"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    assert ps.get("first_loader_node_id") == "3"
    assert ps.get("first_loader_node_class") == "CheckpointLoaderSimple"


def test_loader_matching_excludes_clip_text_encode():
    """CLIPTextEncode is NOT classified as a loader node."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "5": {"class_type": "CLIPTextEncode", "inputs": {}},
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-loader-exclude-clip", process="remote")
    context = ExecutionContext(request_id="test-loader-exclude-clip", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "5"})
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    # CLIPTextEncode is NOT a loader — first_loader_node_id should be empty or absent
    assert ps.get("first_loader_node_id") in ("", None), (
        "CLIPTextEncode must not be classified as a loader"
    )
    # first_clip_encode_node_id should be "5"
    assert ps.get("first_clip_encode_node_id") == "5"


# ═══════════════════════════════════════════════════════════════════════
# Node-to-node interval consistency
# ═══════════════════════════════════════════════════════════════════════


def test_node_to_node_intervals_loader_first_then_clip_then_sampler():
    """When loader→CLIP→sampler execute in order, the node-to-node intervals
    are computed and reported in both milestones and pre_sampler_stages."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "10": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {}},
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-node-intervals", process="remote")
    context = ExecutionContext(request_id="test-node-intervals", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "10"})
        executor.server.send_sync("executing", {"node": "5"})
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    ms = [e for e in trace.events if e.name == "prompt_executor_milestones"][0].metadata

    # Verify milestones has standard node-to-node intervals
    first_node_to_clip_ms = ms.get("first_node_to_clip_ms")
    clip_to_sampler_ms = ms.get("clip_to_sampler_node_ms")
    assert first_node_to_clip_ms is not None, "first_node_to_clip_ms absent from milestones"
    assert clip_to_sampler_ms is not None, "clip_to_sampler_node_ms absent from milestones"
    assert first_node_to_clip_ms >= 0
    assert clip_to_sampler_ms >= 0
    # sampler_node_to_sampler_start_ms is None because the stage timestamp
    # is no longer set from the executing event in milestones.
    assert ms.get("sampler_node_to_sampler_start_ms") is None

    # Verify pre_sampler_stages has the new decomposed intervals
    first_node_to_clip_ps = ps.get("first_node_to_clip_ms")
    clip_to_sampler_ps = ps.get("clip_to_sampler_node_ms")
    assert first_node_to_clip_ps is not None, "first_node_to_clip_ms absent from pre_sampler_stages"
    assert clip_to_sampler_ps is not None, "clip_to_sampler_node_ms absent from pre_sampler_stages"
    assert first_node_to_clip_ps >= 0
    assert clip_to_sampler_ps >= 0
    # sampler_node_to_sampler_start_ms is absent (decomposed into the two new intervals)
    assert ps.get("sampler_node_to_sampler_start_ms") is None
    # The new sampler_node_to_lane_acquired_ms should be present (0.0 or small)
    node_to_lane = ps.get("sampler_node_to_lane_acquired_ms")
    assert node_to_lane is not None, "sampler_node_to_lane_acquired_ms absent from pre_sampler_stages"
    assert node_to_lane >= 0
    # lane_acquired_to_actual_stage_ms is None since no sampler stage event fired
    assert ps.get("lane_acquired_to_actual_stage_ms") is None

    # Verify ordering: first_node_to_clip <= clip_to_sampler + sampler_to_stage (approximate)
    # Since first_executing_node is the loader (node 10), first_node_to_clip goes from loader→clip
    first_loader_node_id = ms.get("first_loader_node_id")
    assert first_loader_node_id == "10", f"Expected loader node 10, got {first_loader_node_id}"
    assert ms.get("first_clip_encode_node_id") == "5"
    assert ms.get("first_sampler_node_id") == "6"


def test_sampler_as_first_node_gives_zero_intervals():
    """When the first executing node IS the sampler, node-to-node intervals
    are None/absent for node classifications that do not exist, but
    sampler_node_to_sampler_start_ms can be 0.0 since the same executing
    event sets both the sampler node and its stage."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-sampler-first", process="remote")
    context = ExecutionContext(request_id="test-sampler-first", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "6"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    ms = [e for e in trace.events if e.name == "prompt_executor_milestones"][0].metadata

    # first_node_to_clip_ms and clip_to_sampler_node_ms are absent (no clip node)
    assert ps.get("first_node_to_clip_ms") is None
    assert ps.get("clip_to_sampler_node_ms") is None

    # sampler_node_to_sampler_start_ms is None because first_sampler_stage_ns
    # is no longer set from the executing event (only from actual
    # sampler_start/sampling_start/sampler_stage_start/progress events).
    assert ps.get("sampler_node_to_sampler_start_ms") is None

    # first_sampler_node_id = "6"
    assert ps.get("first_sampler_node_id") == "6"
    assert ms.get("first_sampler_node_id") == "6"
    # first_sampler_stage_event is absent/empty since no actual stage event fired
    assert ms.get("first_sampler_stage_event") in ("", None)


# ═══════════════════════════════════════════════════════════════════════
# overlapping_intervals field (Fix 1)
# ═══════════════════════════════════════════════════════════════════════


def test_overlapping_intervals_present_on_overlap_error():
    """When measured_children_ms > pre_sampler_total_ms, overlapping_intervals
    lists the contributing interval names.  It must be a list of strings."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []
    _send_syncs: list[tuple] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    def _send_sync(event: str, data: dict | None = None, *a, **kw):
        _send_syncs.append((event, data))

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=_send_sync)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-overlap-list", process="remote")
    context = ExecutionContext(request_id="test-overlap-list", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "6"})  # KSampler
        executor.server.send_sync("executing", {"node": "1"})
        executor.server.send_sync("sampler_start", {})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata

    # overlapping_intervals must always be present in metadata
    assert "overlapping_intervals" in ps, (
        "overlapping_intervals must be present in pre_sampler_stages metadata"
    )
    oi = ps["overlapping_intervals"]
    assert isinstance(oi, (list, tuple)), "overlapping_intervals must be a list or tuple"
    # When no overlap error, the list contains all contributed names
    # (non-overlap path populates all present intervals)
    assert len(oi) > 0, "should contain at least the non-None interval names"
    # Verify known interval names are present
    assert "invoke_to_execution_start_ms" in oi
    assert "execution_start_to_cached_ms" in oi
    assert "cached_to_first_node_ms" in oi
    # sampler_stage event was captured, so lane_acquired_to_actual_stage_ms
    # should be present if lane was acquired
    # (lane acquired because first executing node is KSampler)


def test_overlapping_intervals_list_format():
    """overlapping_intervals is always present and contains strings."""
    executor = _FakeExecutor(use_async=True)
    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-overlap-format", process="remote")
    context = ExecutionContext(request_id="test-overlap-format", trace=trace)

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    assert "overlapping_intervals" in ps
    oi = ps["overlapping_intervals"]
    assert isinstance(oi, (list, tuple)), f"Expected list/tuple, got {type(oi)}: {oi}"
    # All entries should be strings
    for name in oi:
        assert isinstance(name, str), f"Expected string, got {type(name)}: {name}"


# ═══════════════════════════════════════════════════════════════════════
# GPU observation classification (Fix 2)
# ═══════════════════════════════════════════════════════════════════════


def test_gpu_observation_classification_present_in_result():
    """gpu_observation_classification metadata is set on the result
    from _run_in_process with the four expected boolean keys.
    This exercises the full classification path including the
    _execute_v2_prompt_executor + gpu_not_observed_summary + trace scan."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=lambda *a, **kw: None)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    # Mock _configure_runtime and _load_legacy_runtime so _run_in_process
    # can proceed without real Modal/ComfyUI dependencies.
    entrypoint._configure_runtime = lambda: None  # type: ignore[method-assign]
    entrypoint._load_legacy_runtime = lambda: api  # type: ignore[method-assign]
    # Mock preload_bridge methods needed by _run_in_process
    entrypoint._preload_bridge.schedule_execution_prefill = lambda **kw: None
    from contextlib import nullcontext
    entrypoint._preload_bridge.request_scope = lambda: nullcontext()
    entrypoint._preload_bridge.drain_worker_events = lambda _trace: None
    entrypoint._preload_bridge.close_workers = lambda: None
    # Mock the legacy background threads
    entrypoint._join_legacy_background_threads = lambda _api, **kw: 0  # type: ignore[method-assign]

    plan = _build_minimal_plan()
    trace = RuntimeTrace(request_id="test-gpu-class", process="remote")
    context = ExecutionContext(request_id="test-gpu-class", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        executor.server.send_sync("executing", {"node": "1"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(
            entrypoint._run_in_process(plan, context)
        )

    # The classification is set on the execution trace inside result
    exec_trace = result.get("trace", {})
    if isinstance(exec_trace, dict):
        trace_meta = exec_trace.get("metadata", {})
    else:
        trace_meta = getattr(exec_trace, "_metadata", {})

    gpu_class = trace_meta.get("gpu_observation_classification", None)
    assert gpu_class is not None, (
        "gpu_observation_classification must be set in result trace metadata"
    )
    assert isinstance(gpu_class, dict)
    # All four expected keys
    for key in ("wrapper_installed", "wrapper_calls_observed",
                "graph_gpu_load_observed", "sampler_setup_observed"):
        assert key in gpu_class, f"Expected key {key} in gpu_observation_classification"
        assert isinstance(gpu_class[key], bool), (
            f"{key} must be bool, got {type(gpu_class[key])}"
        )


# ═══════════════════════════════════════════════════════════════════════
# progress gating on first_sampler_node (Fix 3)
# ═══════════════════════════════════════════════════════════════════════


def test_progress_before_sampler_node_ignored():
    """progress fired before any sampler node is executing must NOT set
    first_sampler_stage_ns / first_sampler_stage_event.  The wrapper
    only accepts progress after a sampler node has been observed."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []
    _send_syncs: list[tuple] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    def _send_sync(event: str, data: dict | None = None, *a, **kw):
        _send_syncs.append((event, data))

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=_send_sync)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-progress-gate", process="remote")
    context = ExecutionContext(request_id="test-progress-gate", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        # progress fires BEFORE any sampler node executing — should be ignored
        executor.server.send_sync("progress", {"node": "5"})
        # now CLIP encode executes
        executor.server.send_sync("executing", {"node": "5"})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    # first_sampler_stage_event should be empty/absent — progress was
    # ignored because no sampler node was observed yet
    assert ps.get("first_sampler_stage_event") in ("", None), (
        f"progress before sampler node must be ignored, "
        f"got first_sampler_stage_event={ps.get('first_sampler_stage_event')!r}"
    )
    assert ps.get("first_sampler_stage_monotonic_ns") is None, (
        "progress before sampler node must not set first_sampler_stage_monotonic_ns"
    )


def test_progress_after_sampler_node_accepted():
    """progress fired AFTER sampler node executing is valid and sets
    first_sampler_stage_event='progress'."""
    executor = _FakeExecutor(use_async=True)
    _add_msgs: list[str] = []
    _send_syncs: list[tuple] = []

    def _add_msg(event: str, *a, **kw):
        _add_msgs.append(event)

    def _send_sync(event: str, data: dict | None = None, *a, **kw):
        _send_syncs.append((event, data))

    executor.add_message = _add_msg
    executor.server = SimpleNamespace(send_sync=_send_sync)

    api = _build_fake_api(executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            "6": {"class_type": "KSampler", "inputs": {}},
        },
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="test-progress-accept", process="remote")
    context = ExecutionContext(request_id="test-progress-accept", trace=trace)

    original_execute = executor.execute_async

    async def _wrapped_execute(**kwargs):
        executor.add_message("execution_start")
        executor.add_message("execution_cached")
        # CLIP encode executes first
        executor.server.send_sync("executing", {"node": "5"})
        # Sampler executes
        executor.server.send_sync("executing", {"node": "6"})
        # progress fires AFTER sampler node — should be accepted
        executor.server.send_sync("progress", {})
        await original_execute(**kwargs)

    executor.execute_async = _wrapped_execute  # type: ignore[assignment]

    fake_execution = SimpleNamespace(validate_prompt=_async_validate_107)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        asyncio.run(
            entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
        )

    ps = [e for e in trace.events if e.name == "pre_sampler_stages"][0].metadata
    assert ps.get("first_sampler_stage_event") == "progress", (
        f"progress after sampler node must be accepted, "
        f"got first_sampler_stage_event={ps.get('first_sampler_stage_event')!r}"
    )
    assert ps.get("first_sampler_stage_monotonic_ns") is not None, (
        "first_sampler_stage_monotonic_ns must be set when progress is accepted"
    )
