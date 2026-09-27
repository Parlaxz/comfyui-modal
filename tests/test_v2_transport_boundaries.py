"""Focused Phase-2 transport/provenance boundary tests.

Proves exact event order and field propagation for:
- first-event-result receipt (final_result_received before the first result)
- status-then-result order
- submission (first __anext__) distinct from generator creation
- remote result emission boundary (remote_result_emit) reaching the host
- local receipt -> caller return boundary (execute_plan_return)
- deferred persistence stays post-yield and never enters caller-visible timing
- active-read completed-record identity matching (request vs restore session)
"""

from __future__ import annotations

import asyncio
import time
import unittest
from types import SimpleNamespace
from typing import Any

from canonical_execution import build_execution_plan, execute_plan
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.trace import RuntimeTrace


# ═══════════════════════════════════════════════════════════════════════
# Helpers: fake lazy async generator + v2 handle factory
# ═══════════════════════════════════════════════════════════════════════


class _FakeLazyAsyncGen:
    """Simulates Modal's lazy async generator object (aio() == creation,
    __anext__ == submission/first iteration).

    Modal SDK 1.4.3 exposes NO ``input_id``/``input_created_at`` generator
    attributes — those are only learned from yielded event metadata.
    """

    def __init__(self, events: list[dict] | None = None) -> None:
        self._events = list(events or [])
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event


def _make_v2_handle_factory(events: list[dict] | None = None):
    def _factory(**kwargs: Any) -> Any:
        return SimpleNamespace(
            run_plan_stream=SimpleNamespace(
                remote_gen=SimpleNamespace(
                    aio=lambda *a, **kw: _FakeLazyAsyncGen(list(events or [])),
                ),
            ),
        )

    return _factory


def _build_plan(prompt_id: str):
    return build_execution_plan(
        {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
        prompt_id=prompt_id,
        validate=False,
    )


def _make_trace(request_id: str) -> RuntimeTrace:
    trace = RuntimeTrace(request_id=request_id, process="local")
    trace.set_metadata(
        request_origin_info={
            "request_id": request_id,
            "trigger_source": "test",
            "local_receive_wall_ns": int(time.time() * 1_000_000_000),
            "local_receive_mono_ns": time.monotonic_ns(),
        },
    )
    return trace


def _run_execute(events: list[dict], prompt_id: str) -> tuple[dict, RuntimeTrace]:
    transport = ModalTransport(v2_handle_factory=_make_v2_handle_factory(events))
    plan = _build_plan(prompt_id)
    trace = _make_trace(prompt_id)
    result = asyncio.run(execute_plan(plan, transport=transport, trace=trace))
    return result, trace


def _event_names(trace: RuntimeTrace) -> list[str]:
    return [e.name for e in trace.events]


# ═══════════════════════════════════════════════════════════════════════
# Item 4/5: first-event-result receipt + status-then-result ordering
# ═══════════════════════════════════════════════════════════════════════


class TestFirstEventResultReceipt(unittest.TestCase):
    """When the FIRST remote event is already the result, the transport must
    still emit final_result_received before yielding it, and execute_plan must
    stamp local_result_received + the caller-return boundary."""

    def test_first_event_result_emits_receipt_markers(self):
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
        result, trace = _run_execute(events, "first-event-result")
        names = _event_names(trace)
        self.assertIn("final_result_received", names,
                      "final_result_received must be emitted for first-event result")
        self.assertIn("local_result_received", names,
                      "execute_plan must stamp local_result_received at result availability")
        lt = result["local_timing"]
        self.assertIsNotNone(lt.get("local_result_received_wall_ns"))
        self.assertIsNotNone(lt.get("local_result_received_mono_ns"))
        self.assertIsNotNone(lt.get("caller_return_wall_unix_ns"))
        self.assertIsNotNone(lt.get("caller_return_mono_ns"))
        self.assertIsNotNone(lt.get("local_result_received_to_caller_return_ms"))
        # order: receipt before caller return
        self.assertLess(
            names.index("local_result_received"),
            names.index("execute_plan_return"),
        )

    def test_status_then_result_order(self):
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        result, trace = _run_execute(events, "status-then-result")
        names = _event_names(trace)
        # final_result_received emitted exactly once, only for the result
        self.assertEqual(names.count("final_result_received"), 1)
        self.assertIn("modal_first_remote_event", names)
        self.assertLess(
            names.index("modal_submission_attempt"),
            names.index("modal_first_remote_event"),
        )
        # caller-return boundary is the terminal event
        self.assertEqual(names[-1], "execute_plan_return")
        self.assertLess(
            names.index("local_result_received"),
            names.index("execute_plan_return"),
        )
        lt = result["local_timing"]
        self.assertIsNotNone(lt.get("local_result_received_to_caller_return_ms"))


# ═══════════════════════════════════════════════════════════════════════
# Item 2: submission (first __anext__) distinct from generator creation
# ═══════════════════════════════════════════════════════════════════════


class TestSubmissionDistinctFromGeneratorCreation(unittest.TestCase):
    """modal_submission_attempt must be the first-iteration boundary, never
    the generator-creation boundary, and both must survive into local_timing."""

    def test_submission_boundary_distinct_and_present(self):
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        result, trace = _run_execute(events, "sub-vs-gen")
        names = _event_names(trace)
        self.assertIn("modal_generator_created", names)
        self.assertIn("modal_submission_attempt", names)
        self.assertIn("modal_first_iteration_start", names)
        # generator creation strictly precedes first iteration / submission
        self.assertLess(names.index("modal_generator_created"), names.index("modal_first_iteration_start"))
        self.assertLess(names.index("modal_first_iteration_start"), names.index("modal_submission_attempt"))
        # distinct timestamps: submission captured at first __anext__, not
        # creation.  Compare raw captured monotonic values (the created
        # event's own monotonic is inflated by the trace's per-event guard).
        created = next(e for e in trace.events if e.name == "modal_generator_created")
        submission = next(e for e in trace.events if e.name == "modal_submission_attempt")
        created_meta_mono = created.metadata.get("mono_ns")
        self.assertIsNotNone(created_meta_mono,
                             "modal_generator_created must carry the captured mono boundary")
        self.assertLessEqual(
            int(created_meta_mono), int(submission.monotonic_ns),
            "submission boundary must be captured after generator creation",
        )
        # local_timing exposes the separate boundaries (not absent on normal path)
        lt = result["local_timing"]
        self.assertIsNotNone(lt.get("generator_create_ms"))
        self.assertIsNotNone(lt.get("generator_created_to_first_iteration_ms"))
        self.assertIsNotNone(lt.get("local_receive_to_actual_submission_ms"))
        # submission metadata round-trips through trace metadata
        self.assertIn("modal_submission_attempt_wall_ns", trace._metadata)


# ═══════════════════════════════════════════════════════════════════════
# Item 3: remote result emission boundary reaches the host
# ═══════════════════════════════════════════════════════════════════════


class TestRemoteResultEmitPropagation(unittest.TestCase):
    """The remote_result_emit boundary (stamped immediately before the remote
    yield) must survive through the host merge and local_timing, giving a
    direct remote emit -> local receipt interval."""

    def test_remote_result_emit_survives_to_host(self):
        _emit_wall_ns = time.time_ns() + 1_000_000  # just after now
        _emit_mono_ns = time.monotonic_ns() + 1_000_000
        remote_trace = {
            "events": [
                {
                    "name": "remote_result_emit",
                    "process": "remote",
                    "phase": "method",
                    "wall_unix_ns": _emit_wall_ns,
                    "monotonic_ns": _emit_mono_ns,
                    "request_id": "remote-emit",
                    "container_session_id": "cs-boundary",
                    "trace_id": "tid-boundary",
                    "metadata": {"request_id": "remote-emit", "event_type": "result"},
                },
            ],
            "metadata": {},
        }
        result_data = {
            "images": [],
            "outputs": {},
            "remote_result_emit_wall_unix_ns": _emit_wall_ns,
            "remote_result_emit_mono_ns": _emit_mono_ns,
            "trace": remote_trace,
        }
        events = [{"type": "result", "data": result_data}]
        result, trace = _run_execute(events, "remote-emit")
        # event survives in the host-visible merged trace
        merged_names = [
            (e.get("name") if isinstance(e, dict) else getattr(e, "name", ""))
            for e in result["trace"]["events"]
        ]
        self.assertIn("remote_result_emit", merged_names)
        # raw field carried on the result payload
        self.assertEqual(result["remote_result_emit_wall_unix_ns"], _emit_wall_ns)
        lt = result["local_timing"]
        self.assertEqual(lt.get("remote_result_emit_wall_unix_ns"), _emit_wall_ns)
        # remote emit -> local receipt interval is computed (not inferred tail)
        self.assertIsNotNone(lt.get("remote_result_emit_to_local_receipt_ms"))


# ═══════════════════════════════════════════════════════════════════════
# Item 5: caller-return boundary exposed in local_timing + trace
# ═══════════════════════════════════════════════════════════════════════


class TestCallerReturnBoundary(unittest.TestCase):
    """execute_plan stamps a dedicated boundary immediately before returning
    and exposes it in local_timing and trace metadata."""

    def test_caller_return_boundary_exposed(self):
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
        result, trace = _run_execute(events, "caller-return")
        names = _event_names(trace)
        self.assertEqual(names[-1], "execute_plan_return")
        lt = result["local_timing"]
        self.assertIsNotNone(lt.get("caller_return_wall_unix_ns"))
        self.assertIsNotNone(lt.get("caller_return_mono_ns"))
        self.assertIsNotNone(lt.get("local_result_received_to_caller_return_ms"))
        self.assertGreaterEqual(
            lt["caller_return_mono_ns"],
            lt["local_result_received_mono_ns"],
        )
        # trace metadata carries the boundary for host consumers
        self.assertIn("caller_return_wall_unix_ns", result["trace"]["metadata"])


# ═══════════════════════════════════════════════════════════════════════
# Item 6: deferred persistence stays post-yield / out of caller timing
# ═══════════════════════════════════════════════════════════════════════


class TestDeferredPersistenceNotInCallerTiming(unittest.TestCase):
    """A deferred persistence event after the result must not extend the
    caller-visible completion; execute_plan returns at result availability."""

    def test_persistence_yielded_after_result(self):
        events = [
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "data": {"persist_status": "ok", "commit_pending": False}},
        ]
        transport = ModalTransport(v2_handle_factory=_make_v2_handle_factory(events))
        plan = _build_plan("persist-after-result")
        received: list[str] = []

        async def _run():
            async for msg in transport.run_plan_stream(
                plan,
                gpu="",
                workspace={},
                trace={},
                runtime_trace=None,
                plan_dict=None,
            ):
                received.append(str(msg.get("type")))

        asyncio.run(_run())
        self.assertEqual(received[0], "result")
        self.assertEqual(received[1], "persistence",
                         "deferred persistence must be yielded after the result")

    def test_caller_visible_timing_has_no_persistence_tail(self):
        events = [
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "data": {"persist_status": "ok"}},
        ]
        result, trace = _run_execute(events, "persist-not-in-timing")
        lt = result["local_timing"]
        # No fabricated persistence/encode-tail intervals leak into caller timing.
        for key in lt:
            self.assertNotIn("persist", str(key))
            self.assertNotIn("deferred", str(key))
        # Caller-return boundary still present (completion at result availability).
        self.assertIsNotNone(lt.get("caller_return_wall_unix_ns"))
        names = _event_names(trace)
        self.assertIn("execute_plan_return", names)
        # Deferred persistence, when recorded, is strictly post-receipt and
        # does NOT precede the caller-return boundary.
        if "deferred_commit_end" in names:
            self.assertLess(
                names.index("local_result_received"),
                names.index("deferred_commit_end"),
                "deferred persistence must be recorded after result receipt",
            )


# ═══════════════════════════════════════════════════════════════════════
# Item 1: active-read completed-record identity matching
# ═══════════════════════════════════════════════════════════════════════


class TestActiveReadDrainIdentity(unittest.TestCase):
    """_drain_completed_active_read_diagnostics must associate records by exact
    restore identities when request_id is empty, refine by exact request_id when
    present, and never consume another request/session's read."""

    def setUp(self):
        import comfyapp as _comfyapp_module
        self._ca_module = _comfyapp_module
        self._orig = list(_comfyapp_module._COMPLETED_ACTIVE_READS)
        _comfyapp_module._COMPLETED_ACTIVE_READS[:] = []

    def tearDown(self):
        self._ca_module._COMPLETED_ACTIVE_READS[:] = self._orig

    def _record(self, active_read_id="r1", request_id="", restored_instance_id="inst-A",
                restore_session_id="sess-1", **extra):
        rec = {
            "active_read_id": active_read_id,
            "owner": "preload",
            "loader_type": "CLIPLoader",
            "phase": "restore",
            "request_id": request_id,
            "restored_instance_id": restored_instance_id,
            "restore_session_id": restore_session_id,
            "path_hash": "h_" + active_read_id,
            "file_size": 123,
            "wall_ms": 1.5,
            "thread_cpu_ms": None,
            "process_cpu_ms": None,
            "start_wall_unix_ns": 1,
            "start_monotonic_ns": 2,
            "end_wall_unix_ns": 3,
            "end_monotonic_ns": 4,
        }
        rec.update(extra)
        return rec

    def _drain(self, **kwargs):
        return self._ca_module._drain_completed_active_read_diagnostics(**kwargs)

    def test_empty_request_id_matching_restore_identities_drains(self):
        self._ca_module._COMPLETED_ACTIVE_READS.append(
            self._record(active_read_id="r-pre", request_id="", restored_instance_id="inst-A", restore_session_id="sess-1")
        )
        matched = self._drain(request_id="", restored_instance_id="inst-A", restore_session_id="sess-1")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["active_read_id"], "r-pre")
        # complete record fields preserved verbatim
        self.assertEqual(matched[0]["restored_instance_id"], "inst-A")
        self.assertEqual(matched[0]["restore_session_id"], "sess-1")
        self.assertEqual(matched[0]["path_hash"], "h_r-pre")
        self.assertEqual(matched[0]["file_size"], 123)
        self.assertEqual(matched[0]["wall_ms"], 1.5)
        self.assertEqual(matched[0]["start_wall_unix_ns"], 1)
        self.assertEqual(matched[0]["end_monotonic_ns"], 4)
        self.assertEqual(self._ca_module._COMPLETED_ACTIVE_READS, [], "matched record must be drained")

    def test_mismatched_restore_identities_retained(self):
        self._ca_module._COMPLETED_ACTIVE_READS.append(
            self._record(active_read_id="r-pre", restored_instance_id="inst-A", restore_session_id="sess-1")
        )
        matched = self._drain(request_id="", restored_instance_id="inst-B", restore_session_id="sess-2")
        self.assertEqual(matched, [])
        self.assertEqual(len(self._ca_module._COMPLETED_ACTIVE_READS), 1, "mismatch must be retained")

    def test_no_cross_session_leakage(self):
        self._ca_module._COMPLETED_ACTIVE_READS.append(
            self._record(active_read_id="r-s1", restored_instance_id="inst-A", restore_session_id="sess-1")
        )
        self._ca_module._COMPLETED_ACTIVE_READS.append(
            self._record(active_read_id="r-s2", restored_instance_id="inst-A", restore_session_id="sess-2")
        )
        matched = self._drain(request_id="", restored_instance_id="inst-A", restore_session_id="sess-1")
        self.assertEqual([m["active_read_id"] for m in matched], ["r-s1"])
        remaining = [r["active_read_id"] for r in self._ca_module._COMPLETED_ACTIVE_READS]
        self.assertEqual(remaining, ["r-s2"], "other session's read must not be consumed")

    def test_exact_request_match_drains_only_that_request(self):
        self._ca_module._COMPLETED_ACTIVE_READS.append(
            self._record(active_read_id="r-req1", request_id="req-1")
        )
        self._ca_module._COMPLETED_ACTIVE_READS.append(
            self._record(active_read_id="r-req2", request_id="req-2")
        )
        matched = self._drain(request_id="req-1", restored_instance_id="", restore_session_id="")
        self.assertEqual([m["active_read_id"] for m in matched], ["r-req1"])
        remaining = [r["active_read_id"] for r in self._ca_module._COMPLETED_ACTIVE_READS]
        self.assertEqual(remaining, ["r-req2"], "another request's read must not be consumed")

    def test_request_tagged_record_not_consumed_by_restore_identity_drain(self):
        # A record that carries its own request_id must not be consumed by a
        # restore-identity-only drain (prevents another request/model read from
        # being consumed).
        self._ca_module._COMPLETED_ACTIVE_READS.append(
            self._record(active_read_id="r-tagged", request_id="req-9",
                         restored_instance_id="inst-A", restore_session_id="sess-1")
        )
        matched = self._drain(request_id="", restored_instance_id="inst-A", restore_session_id="sess-1")
        self.assertEqual(matched, [], "request-tagged record must not be consumed without its exact request")
        self.assertEqual(len(self._ca_module._COMPLETED_ACTIVE_READS), 1)


# ═══════════════════════════════════════════════════════════════════════
# Remediation: SDK input-id resilience + event-metadata input IDs
# ═══════════════════════════════════════════════════════════════════════


class TestInputIdFromEventMetadata(unittest.TestCase):
    """Modal SDK 1.4.3 exposes no generator input_id attributes; input IDs are
    learned from yielded event metadata, and the transport is resilient when
    no input ID exists at all."""

    def test_transport_works_without_generator_input_attributes(self):
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        transport = ModalTransport(v2_handle_factory=_make_v2_handle_factory(events))
        plan = _build_plan("no-input-attrs")
        trace = _make_trace("no-input-attrs")

        async def _run():
            async for _ in transport.run_plan_stream(
                plan, gpu="", workspace={},
                trace={"prompt_id": "no-input-attrs"},
                runtime_trace=trace,
                plan_dict=None,
            ):
                pass

        asyncio.run(_run())
        # No generator attribute -> no fabricated observation event, no crash.
        self.assertNotIn(
            "modal_input_id_observed",
            [e.name for e in trace.events],
        )
        self.assertEqual(trace._metadata.get("modal_input_id", ""), "")

    def test_input_id_learned_from_result_event_metadata(self):
        events = [
            {"type": "result", "data": {
                "images": [], "outputs": {},
                "modal_input_id": "evt-id-789",
            }},
        ]
        transport = ModalTransport(v2_handle_factory=_make_v2_handle_factory(events))
        plan = _build_plan("evt-input-id")
        trace = _make_trace("evt-input-id")

        async def _run():
            async for _ in transport.run_plan_stream(
                plan, gpu="", workspace={},
                trace={"prompt_id": "evt-input-id"},
                runtime_trace=trace,
                plan_dict=None,
            ):
                pass

        asyncio.run(_run())
        observed = [e for e in trace.events if e.name == "modal_input_id_observed"]
        self.assertEqual(len(observed), 1)
        self.assertEqual(trace._metadata.get("modal_input_id"), "evt-id-789")


# ═══════════════════════════════════════════════════════════════════════
# Remediation: active-read producer record completeness
# ═══════════════════════════════════════════════════════════════════════


class TestActiveReadProducerCompleteness(unittest.TestCase):
    """The producer (_complete_active_model_read) writes every identity and
    wall/mono boundary field onto the completed record."""

    def setUp(self):
        import comfyapp as _comfyapp_module
        self._ca_module = _comfyapp_module
        self._orig_reads = list(_comfyapp_module._ACTIVE_MODEL_READS)
        self._orig_completed = list(_comfyapp_module._COMPLETED_ACTIVE_READS)
        _comfyapp_module._ACTIVE_MODEL_READS.clear()
        _comfyapp_module._COMPLETED_ACTIVE_READS[:] = []

    def tearDown(self):
        self._ca_module._ACTIVE_MODEL_READS.clear()
        self._ca_module._ACTIVE_MODEL_READS.update(self._orig_reads)
        self._ca_module._COMPLETED_ACTIVE_READS[:] = self._orig_completed

    def test_completed_record_carries_identity_and_boundaries(self):
        key = "k_complete_record"
        entry = {
            "owner": "restore_preload",
            "loader_type": "CLIPLoader",
            "phase": "restore",
            "request_id": "req-complete",
            "restored_instance_id": "inst-X",
            "restore_session_id": "sess-9",
            "active_read_id": "arid-complete",
            "active_read_path_hash": "hash-complete",
            "active_read_file_size": 456,
            "start_wall_unix_ns": 111,
            "start_monotonic_ns": 222,
            "start_thread_time_ns": 1,
            "start_process_time_ns": 2,
            "native_tid": 42,
        }
        self._ca_module._ACTIVE_MODEL_READS[key] = dict(entry)
        self._ca_module._complete_active_model_read(key)
        self.assertEqual(len(self._ca_module._COMPLETED_ACTIVE_READS), 1)
        rec = self._ca_module._COMPLETED_ACTIVE_READS[0]
        for field in (
            "request_id", "restored_instance_id", "restore_session_id",
            "owner", "path_hash", "file_size",
            "start_wall_unix_ns", "start_monotonic_ns",
            "end_wall_unix_ns", "end_monotonic_ns",
        ):
            self.assertIn(field, rec, "completed record must carry " + field)
        self.assertEqual(rec["request_id"], "req-complete")
        self.assertEqual(rec["restored_instance_id"], "inst-X")
        self.assertEqual(rec["restore_session_id"], "sess-9")
        self.assertEqual(rec["owner"], "restore_preload")
        self.assertEqual(rec["path_hash"], "hash-complete")
        self.assertEqual(rec["start_wall_unix_ns"], 111)
        self.assertIsInstance(rec["end_wall_unix_ns"], int)
        self.assertIsInstance(rec["end_monotonic_ns"], int)
        self.assertGreaterEqual(rec["end_monotonic_ns"], rec["start_monotonic_ns"])


# ═══════════════════════════════════════════════════════════════════════
# Remediation: final merged trace lifecycle + persistence public shape
# ═══════════════════════════════════════════════════════════════════════


class TestFinalMergedTraceLifecycle(unittest.TestCase):
    """The host reconciliation view (result['trace']['events']) must carry the
    exact lifecycle: submission, final_result_received, local_result_received,
    execute_plan_return."""

    def test_lifecycle_events_present_in_final_merged_trace(self):
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
        result, trace = _run_execute(events, "merged-lifecycle")
        merged_names = [
            (e.get("name") if isinstance(e, dict) else getattr(e, "name", ""))
            for e in result["trace"]["events"]
        ]
        for name in (
            "modal_submission_attempt",
            "final_result_received",
            "local_result_received",
            "execute_plan_return",
        ):
            self.assertIn(name, merged_names,
                          name + " must be present in the final merged trace")
        self.assertLess(
            merged_names.index("local_result_received"),
            merged_names.index("execute_plan_return"),
        )
        # local_timing passed to host reconciliation carries the boundaries.
        lt = result["local_timing"]
        self.assertIsNotNone(lt.get("local_result_received_wall_ns"))
        self.assertIsNotNone(lt.get("caller_return_wall_unix_ns"))


class TestDeferredPersistencePublicShape(unittest.TestCase):
    """The public persistence event dict stays clean: internal trace events
    are carried separately through the trace, never on the yielded event."""

    def test_yielded_persistence_event_has_no_trace_events_field(self):
        import comfymodal_runtime.modal_app as modal_app
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        # Simulate a completed deferred commit so finalization returns a real
        # persistence event with an internal _trace_events payload.
        entrypoint._deferred_commit_pending = True
        entrypoint._deferred_commit_task = None
        entrypoint._deferred_commit_diag = None
        event = asyncio.run(
            entrypoint._finalize_deferred_commit(request_id="shape-test")
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.get("type"), "persistence")
        self.assertNotIn("_trace_events", event,
                         "public persistence event must not carry _trace_events")
        self.assertEqual(event.get("skipped"), True)
        self.assertEqual(event.get("status"), "ok")


# ═══════════════════════════════════════════════════════════════════════
# Persistence-drain lifecycle: registry + bounded join/cancel at teardown
# ═══════════════════════════════════════════════════════════════════════


class _HangingGen:
    """Fake remote generator whose post-result iteration never completes
    (the drain must be cancelled cleanly by the bounded join seam)."""

    def __init__(self, events: list[dict] | None = None) -> None:
        self._events = list(events or [{"type": "result", "data": {"images": [], "outputs": {}}}])
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._index >= len(self._events):
            await asyncio.sleep(3600)  # never completes
        event = self._events[self._index]
        self._index += 1
        return event

    async def aclose(self) -> None:
        pass


def _make_hanging_factory(events: list[dict] | None = None):
    return lambda **kwargs: SimpleNamespace(
        run_plan_stream=SimpleNamespace(
            remote_gen=SimpleNamespace(
                aio=lambda *a, **kw: _HangingGen(list(events or [])),
            ),
        ),
    )


class TestPersistenceDrainLifecycle(unittest.TestCase):
    """The transport tracks spawned persistence drains in an explicit registry
    and the teardown seams join them with a bounded timeout (or cancel them
    cleanly), so no drain task is ever left pending at loop shutdown."""

    def setUp(self):
        import comfymodal_runtime.modal_transport as mt
        self._mt = mt
        self._orig_handles = dict(mt._PERSISTENCE_DRAIN_HANDLES)
        self._orig_status = dict(mt._PERSISTENCE_STATUS_BY_PROMPT)
        mt._PERSISTENCE_DRAIN_HANDLES.clear()
        mt._PERSISTENCE_STATUS_BY_PROMPT.clear()

    def tearDown(self):
        self._mt._PERSISTENCE_DRAIN_HANDLES.clear()
        self._mt._PERSISTENCE_DRAIN_HANDLES.update(self._orig_handles)
        self._mt._PERSISTENCE_STATUS_BY_PROMPT.clear()
        self._mt._PERSISTENCE_STATUS_BY_PROMPT.update(self._orig_status)

    def _pending_drain_tasks(self) -> list:
        return [
            t for t in asyncio.all_tasks()
            if not t.done()
            and t.get_coro() is not None
            and t.get_coro().cr_code.co_name
            in ("_drain_persistence_iterator", "_shielded_drain")
        ]

    def test_quick_persistence_completion_recorded_and_joined(self):
        events = [
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "status": "ok", "commit_ms": 2.5, "detail": "committed", "skipped": False},
        ]
        transport = ModalTransport(v2_handle_factory=_make_v2_handle_factory(events))
        plan = _build_plan("persist-quick")
        trace = _make_trace("persist-quick")
        received: list[str] = []

        async def _run():
            agen = transport.run_plan_stream(
                plan, gpu="", workspace={},
                trace={"prompt_id": "persist-quick"},
                runtime_trace=trace,
                plan_dict=None,
            )
            async for msg in agen:
                received.append(str(msg.get("type")))
                if msg.get("type") == "result":
                    break  # caller returns at result; explicit close spawns the drain
            await agen.aclose()  # deterministic: finally registers the drain
            self.assertIn("persist-quick", self._mt._PERSISTENCE_DRAIN_HANDLES)
            records = await transport.close_persistence_drains(timeout=5.0)
            # Registry cleared and zero pending drain tasks (checked on the loop).
            self.assertNotIn("persist-quick", self._mt._PERSISTENCE_DRAIN_HANDLES)
            self.assertEqual(self._pending_drain_tasks(), [])
            return records

        records = asyncio.run(_run())
        self.assertEqual(received, ["result"],
                         "deferred persistence is NOT part of the caller-visible result")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "ok")
        self.assertEqual(records[0]["commit_ms"], 2.5)
        # Public persistence record shape unchanged (no internal fields).
        self.assertNotIn("_trace_events", records[0])
        # Trace captured the deferred-commit evidence.
        trace_names = [e.name for e in trace.events]
        self.assertIn("deferred_commit_end", trace_names)

    def test_timeout_cancels_hanging_drain_cleanly(self):
        transport = ModalTransport(v2_handle_factory=_make_hanging_factory())
        plan = _build_plan("persist-timeout")
        trace = _make_trace("persist-timeout")

        async def _run():
            agen = transport.run_plan_stream(
                plan, gpu="", workspace={},
                trace={"prompt_id": "persist-timeout"},
                runtime_trace=trace,
                plan_dict=None,
            )
            async for _ in agen:
                break  # consume result only; explicit close spawns the drain
            await agen.aclose()
            # Drain is registered and will never complete on its own.
            self.assertIn("persist-timeout", self._mt._PERSISTENCE_DRAIN_HANDLES)
            record = await self._mt.join_persistence_drain(
                "persist-timeout", timeout=0.1
            )
            # Cancelled cleanly: registry cleared, zero pending drain tasks.
            self.assertNotIn("persist-timeout", self._mt._PERSISTENCE_DRAIN_HANDLES)
            self.assertEqual(self._pending_drain_tasks(), [])
            return record

        record = asyncio.run(_run())
        self.assertIsNone(record, "no persistence event was received")

    def test_teardown_leaves_zero_pending_drain_tasks(self):
        import contextlib
        import io as _io

        def _drive():
            transport = ModalTransport(v2_handle_factory=_make_hanging_factory())
            plan = _build_plan("persist-teardown")
            trace = _make_trace("persist-teardown")

            async def _run():
                agen = transport.run_plan_stream(
                    plan, gpu="", workspace={},
                    trace={"prompt_id": "persist-teardown"},
                    runtime_trace=trace,
                    plan_dict=None,
                )
                async for _ in agen:
                    break
                await agen.aclose()
                # Drain definitely pending (hanging iterator).
                self.assertGreater(len(self._pending_drain_tasks()), 0)
                await self._mt.join_all_persistence_drains(timeout=0.1)
                self.assertEqual(self._pending_drain_tasks(), [])

            asyncio.run(_run())

        err = _io.StringIO()
        with contextlib.redirect_stderr(err):
            _drive()
        # No task is left pending, so loop shutdown must not destroy any.
        self.assertNotIn("Task was destroyed", err.getvalue())

    def test_execute_plan_spawns_joinable_drain(self):
        """execute_plan's bounded close seam deterministically spawns the
        post-result drain, and the transport join collects the trailing
        persistence record without delaying or altering the result."""
        events = [
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "status": "ok", "commit_ms": 1.0, "detail": "done", "skipped": False},
        ]
        transport = ModalTransport(v2_handle_factory=_make_v2_handle_factory(events))
        plan = _build_plan("exec-plan-drain")
        trace = _make_trace("exec-plan-drain")

        async def _run():
            result = await execute_plan(plan, transport=transport, trace=trace)
            # execute_plan's finally acloses the stream -> drain registered.
            self.assertIn("exec-plan-drain", self._mt._PERSISTENCE_DRAIN_HANDLES)
            records = await transport.close_persistence_drains(timeout=5.0)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "ok")
            self.assertEqual(self._pending_drain_tasks(), [])
            return result

        result = asyncio.run(_run())
        self.assertEqual(result["outputs"], {})

    def test_public_persistence_event_shape_unchanged_via_drain(self):
        events = [
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "status": "ok", "commit_ms": 0.0, "detail": "no commit needed", "skipped": True},
        ]
        transport = ModalTransport(v2_handle_factory=_make_v2_handle_factory(events))
        plan = _build_plan("persist-shape")
        yielded: list[dict] = []

        async def _run():
            agen = transport.run_plan_stream(
                plan, gpu="", workspace={},
                trace={"prompt_id": "persist-shape"},
                runtime_trace=None,
                plan_dict=None,
            )
            async for msg in agen:
                yielded.append(msg)
                if msg.get("type") == "result":
                    break
            await agen.aclose()
            # Drain receives the trailing persistence event (not caller-visible
            # in the yielded stream, but the public event shape is preserved).
            await self._mt.join_persistence_drain("persist-shape", timeout=5.0)
            # The record has exactly the public fields.
            record = self._mt.get_persistence_status("persist-shape")
            self.assertIsNotNone(record)
            self.assertEqual(
                set(record.keys()), {"status", "commit_ms", "detail", "skipped"},
                "persistence record shape must stay unchanged",
            )
            self.assertNotIn("_trace_events", record)

        asyncio.run(_run())
        self.assertEqual([e.get("type") for e in yielded], ["result"])


class TestBenchmarkPersistenceMerge(unittest.TestCase):
    """The host benchmark seam merges received deferred-commit evidence into
    the structured artifact trace without touching caller-visible stages."""

    def test_merge_deferred_commit_trace_events_idempotent(self):
        from comfymodal_runtime.trace import RuntimeTrace
        from tools.benchmark_v2_direct import _merge_deferred_commit_trace_events

        trace = RuntimeTrace(request_id="merge-deferred", process="local")
        trace.emit("deferred_commit_end", phase="local", metadata={"status": "ok"})
        result = {
            "trace": {
                "events": [
                    {"name": "local_result_received", "wall_unix_ns": 1, "monotonic_ns": 1},
                ],
                "metadata": {},
            },
        }
        _merge_deferred_commit_trace_events(result, trace)
        names = [e.get("name") for e in result["trace"]["events"]]
        self.assertIn("deferred_commit_end", names)
        self.assertIn("local_result_received", names,
                      "existing result trace events must be preserved")
        # Idempotent: second merge adds nothing.
        _merge_deferred_commit_trace_events(result, trace)
        self.assertEqual(len([e for e in result["trace"]["events"]
                              if e.get("name") == "deferred_commit_end"]), 1)
        # Caller-visible stages untouched.
        self.assertNotIn("stages", result["trace"])

# -- D1 registry-proof store isolation (never write the real shared store;
#    see tests/d1_store_isolation.py) -----------------------------------
import sys as _d1_sys
from pathlib import Path as _d1_Path

if str(_d1_Path(__file__).resolve().parents[1]) not in _d1_sys.path:
    _d1_sys.path.insert(0, str(_d1_Path(__file__).resolve().parents[1]))
from tests.d1_store_isolation import isolate_module_store, restore_module_store


def setUpModule():
    isolate_module_store()


def tearDownModule():
    restore_module_store()
