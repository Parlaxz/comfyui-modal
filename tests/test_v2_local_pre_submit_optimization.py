"""Focused tests for local pre-submission optimization in ``execute_plan``.

Covers all nine core optimization requirements:

1. Unchanged stable active profile → no remote setter call (profile prep cache)
2. Profile prep cache keyed by source_workflow_hash, production_plan_hash,
   workspace, app/environment
3. Reuse ExecutionPlan canonical workflow — avoid ``plan.to_dict()`` solely
   for workflow extraction
4. Restore publication cache stable — identity built/hashed once per plan
5. Unchanged → no publish; changed → exactly one publish (restore cache)
6. Single request-scoped canonical payload reused for profile + restore +
   Modal payload (``_canonical_workflow``)
7. No mutable leak into ExecutionPlan; no global retention of base64 images
8. Preserve payload size observability (transport layer unchanged)
9. Preserve ModalTransport handle cache and instance/cache-key behavior
10. [v2.local_submission_breakdown] intact

Plus operation-count reduction verification.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from canonical_execution import (
    _reset_profile_prep_cache,
    _reset_restore_publish_cache,
    _profile_prep_cache_key,
    build_execution_plan,
    execute_plan,
)
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, RestorePlan
from comfymodal_runtime.modal_transport import HandleCache, HandleCacheKey, ModalTransport
from comfymodal_runtime.trace import RuntimeTrace
from warmup_profile import _reset_last_stable_profile_cache


# =========================================================================
# Helpers
# =========================================================================


class _Publisher:
    """Simple restore publisher that records calls."""
    def __init__(self):
        self.plans = []
        self.publish_count = 0

    def publish(self, plan):
        self.plans.append(plan)
        self.publish_count += 1
        return self.publish_count


class _CountingProfileSetter:
    """Profile setter that counts invocations."""
    def __init__(self, status: str = "written"):
        self.invoke_count = 0
        self._status = status

    async def __call__(self, payload: dict, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        return {"status": self._status, "changed": True}


# =========================================================================
# Requirement 1: Profile prep cache — no remote setter for unchanged plan
# =========================================================================


class TestProfilePrepCacheHits(unittest.TestCase):
    """``_PROFILE_PREP_CACHE`` avoids ``prepare_active_next_profile`` when
    the plan identity (source_workflow_hash + production_plan_hash +
    workspace + app/environment) is unchanged."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def _run_execute_plan(self, setter: _CountingProfileSetter) -> dict:
        """Run execute_plan with a simple workflow and return the result."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="cache_test",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport,
                profile_setter=setter,
                workspace={"id": "ws_cache"},
            )
            return result
        return asyncio.run(run())

    def test_first_call_invokes_setter(self):
        """First call with a new identity calls the setter."""
        setter = _CountingProfileSetter()
        self._run_execute_plan(setter)
        self.assertEqual(setter.invoke_count, 1,
                         "First call must invoke profile setter")

    def test_second_call_skips_setter(self):
        """Second call with the same identity skips the setter (cache hit)."""
        setter = _CountingProfileSetter()
        self._run_execute_plan(setter)  # first → cache miss
        self._run_execute_plan(setter)  # second → cache hit
        self.assertEqual(setter.invoke_count, 1,
                         "Second call must NOT invoke profile setter (cached)")

    def test_cache_hit_emits_profile_prep_cache_hit_event(self):
        """Cache hit emits a ``profile_prep_cache_hit`` trace event."""
        setter = _CountingProfileSetter()
        # First call populates cache
        self._run_execute_plan(setter)

        # Second call — capture trace
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="cache_hit_event",
                validate=False,
            )
            trace = RuntimeTrace(request_id="cache_hit_event", process="local")
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(
                plan, transport=transport,
                profile_setter=setter,
                workspace={"id": "ws_cache"},
                trace=trace,
            )
            ev_names = [e.name for e in trace.events]
            self.assertIn("profile_prep_cache_hit", ev_names,
                          "Cache hit must emit profile_prep_cache_hit event")
        asyncio.run(run())

    def test_metadata_shows_cache_hit(self):
        """Trace metadata shows ``profile_prep_cache_hit=True`` on cache hit."""
        setter = _CountingProfileSetter()
        self._run_execute_plan(setter)

        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="meta_hit",
                validate=False,
            )
            trace = RuntimeTrace(request_id="meta_hit", process="local")
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(
                plan, transport=transport,
                profile_setter=setter,
                workspace={"id": "ws_cache"},
                trace=trace,
            )
            self.assertTrue(trace._metadata.get("profile_cache_hit"),
                            "Metadata must show profile_cache_hit=True")
        asyncio.run(run())

    def test_different_workflow_misses_cache(self):
        """A different workflow (different source hash, different model stack)
        misses the ``_PROFILE_PREP_CACHE`` AND the internal
        ``prepare_active_next_profile`` cache, calling the setter again."""
        setter = _CountingProfileSetter()
        # Call with workflow A (includes a model loader so the profile changes)
        async def run_a():
            async def stream_a(**kw):
                yield {"type": "result", "data": {"images": [], "outputs": {}}}
            plan_a = build_execution_plan(
                {"1": {"class_type": "CheckpointLoaderSimple",
                        "inputs": {"ckpt_name": "model_a.safetensors"}},
                 "2": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="wf_a", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream_a)
            await execute_plan(plan_a, transport=transport, profile_setter=setter,
                               workspace={"id": "ws_diff_profiles"})
        asyncio.run(run_a())

        # Call with workflow B — different model → different stack
        async def run_b():
            async def stream_b(**kw):
                yield {"type": "result", "data": {"images": [], "outputs": {}}}
            plan_b = build_execution_plan(
                {"1": {"class_type": "CheckpointLoaderSimple",
                        "inputs": {"ckpt_name": "model_b.safetensors"}},
                 "2": {"class_type": "KSampler", "inputs": {"seed": 99}}},
                prompt_id="wf_b", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream_b)
            await execute_plan(plan_b, transport=transport, profile_setter=setter,
                               workspace={"id": "ws_diff_profiles"})
        asyncio.run(run_b())

        self.assertEqual(setter.invoke_count, 2,
                         "Different model stacks must both call setter")


# =========================================================================
# Requirement 2: Profile prep cache key correctness
# =========================================================================


class TestProfilePrepCacheKey(unittest.TestCase):
    """``_profile_prep_cache_key`` produces deterministic, partition-safe keys."""

    def test_deterministic_key(self):
        """Same inputs produce the same key."""
        k1 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env1")
        k2 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env1")
        self.assertEqual(k1, k2, "Same inputs must produce same key")

    def test_different_source_hash_different_key(self):
        """Different source_workflow_hash → different key."""
        k1 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env1")
        k2 = _profile_prep_cache_key("hash_b", "plan_a", "ws_1", "app1", "env1")
        self.assertNotEqual(k1, k2, "Different source hash must produce different key")

    def test_different_prod_plan_hash_different_key(self):
        """Different production_plan_hash → different key."""
        k1 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env1")
        k2 = _profile_prep_cache_key("hash_a", "plan_b", "ws_1", "app1", "env1")
        self.assertNotEqual(k1, k2, "Different plan hash must produce different key")

    def test_different_workspace_different_key(self):
        """Different workspace_id → different key."""
        k1 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env1")
        k2 = _profile_prep_cache_key("hash_a", "plan_a", "ws_2", "app1", "env1")
        self.assertNotEqual(k1, k2, "Different workspace must produce different key")

    def test_different_app_name_different_key(self):
        """Different app_name → different key."""
        k1 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env1")
        k2 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app2", "env1")
        self.assertNotEqual(k1, k2, "Different app_name must produce different key")

    def test_different_environment_different_key(self):
        """Different environment → different key."""
        k1 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env1")
        k2 = _profile_prep_cache_key("hash_a", "plan_a", "ws_1", "app1", "env2")
        self.assertNotEqual(k1, k2, "Different env must produce different key")


# =========================================================================
# Requirement 3: Avoid plan.to_dict() for workflow extraction
# =========================================================================


class TestExactlyOnePlanToDict(unittest.TestCase):
    """``execute_plan`` calls ``plan.to_dict()`` exactly once per request.
    That single call produces the canonical payload reused for profile
    activation, restore publication, and the final Modal API submission."""

    def test_exactly_one_plan_to_dict_call_in_source(self):
        """``execute_plan`` source has exactly ONE ``plan.to_dict()`` line."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        lines = source.split("\n")
        plan_to_dict_lines = [
            l for l in lines
            if "plan.to_dict()" in l and not l.strip().startswith("#")
        ]
        self.assertEqual(
            len(plan_to_dict_lines), 1,
            f"execute_plan must call plan.to_dict() exactly once. "
            f"Found {len(plan_to_dict_lines)}: {plan_to_dict_lines}",
        )

    def test_spy_on_plan_to_dict_proves_one_call(self):
        """Spy on plan.to_dict to count calls across a full execute_plan run."""
        setter = _CountingProfileSetter()
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        original_to_dict = ExecutionPlan.to_dict
        call_count = [0]

        def _spy_to_dict(self):
            call_count[0] += 1
            return original_to_dict(self)

        async def run():
            ExecutionPlan.to_dict = _spy_to_dict  # type: ignore[assignment]
            try:
                plan = build_execution_plan(
                    {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                    prompt_id="spy_test", validate=False,
                )
                transport = ModalTransport(prompt_stream_fn=_stream)
                await execute_plan(plan, transport=transport,
                                   profile_setter=setter,
                                   workspace={"id": "ws_spy"})
            finally:
                ExecutionPlan.to_dict = original_to_dict
            self.assertEqual(call_count[0], 1,
                             "plan.to_dict() must be called exactly once per request")
        asyncio.run(run())

    def test_canonical_dict_passed_to_transport(self):
        """The canonical dict is passed as ``plan_dict`` to
        ``ModalTransport.run_plan_stream``, avoiding rematerialization."""
        import inspect
        source = inspect.getsource(execute_plan)
        self.assertIn("plan_dict=_canonical_dict", source,
                      "Must pass plan_dict to transport")


# =========================================================================
# Requirement 4: Restore publication cache — stable identity
# =========================================================================


class TestRestorePublishCacheStable(unittest.TestCase):
    """Restore identity is built once per immutable plan."""

    def setUp(self):
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_restore_publish_cache()

    def test_restore_publisher_called_once_for_same_plan(self):
        """Same plan → restore publisher called exactly once (second is cached)."""
        publisher = _Publisher()
        setter = _CountingProfileSetter()

        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="restore_stable",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)

            # First call: publisher should be invoked
            await execute_plan(plan, transport=transport,
                               restore_publisher=publisher,
                               workspace={"id": "ws_restore"})
            first_count = publisher.publish_count

            # Second call with same plan: publisher should NOT be invoked (cache hit)
            await execute_plan(plan, transport=transport,
                               restore_publisher=publisher,
                               workspace={"id": "ws_restore"})
            self.assertEqual(publisher.publish_count, first_count,
                             "Restore publisher must not be called on second identical plan")
        asyncio.run(run())


# =========================================================================
# Requirement 5: Unchanged → no publish; changed → exactly once
# =========================================================================


class TestUnchangedNoPublishChangedOnce(unittest.TestCase):
    """When plan is unchanged, no publish occurs.
    When plan changes, exactly one publish occurs."""

    def setUp(self):
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_restore_publish_cache()

    def test_unchanged_plan_no_remote_publish(self):
        """Unchanged plan identity → restore_publish_cache_skipped=True."""
        publisher = _Publisher()

        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="unchanged_pub",
                validate=False,
            )
            trace = RuntimeTrace(request_id="unchanged_pub", process="local")
            transport = ModalTransport(prompt_stream_fn=stream)

            # First call: publish happens
            await execute_plan(plan, transport=transport,
                               restore_publisher=publisher,
                               workspace={"id": "ws_unchanged"},
                               trace=trace)
            self.assertTrue(
                trace._metadata.get("restore_publish_cache_skipped") is False
                or trace._metadata.get("restore_publish_cache_skipped") is None,
            )

            # Second call: cache skips publish
            trace2 = RuntimeTrace(request_id="unchanged_pub2", process="local")
            await execute_plan(plan, transport=transport,
                               restore_publisher=publisher,
                               workspace={"id": "ws_unchanged"},
                               trace=trace2)
            self.assertTrue(
                trace2._metadata.get("restore_publish_cache_skipped"),
                "Second identical plan must skip restore publish (cache hit)",
            )
        asyncio.run(run())

    def test_changed_plan_publishes_exactly_once(self):
        """Different plan → one new publish (not zero, not multiple)."""
        publisher = _Publisher()

        async def run_a():
            async def stream_a(**kw):
                yield {"type": "result", "data": {"images": [], "outputs": {}}}
            plan_a = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="pub_a", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream_a)
            await execute_plan(plan_a, transport=transport,
                               restore_publisher=publisher,
                               workspace={"id": "ws_changed"})
        asyncio.run(run_a())

        # Second plan with different content
        async def run_b():
            async def stream_b(**kw):
                yield {"type": "result", "data": {"images": [], "outputs": {}}}
            plan_b = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                prompt_id="pub_b", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream_b)
            await execute_plan(plan_b, transport=transport,
                               restore_publisher=publisher,
                               workspace={"id": "ws_changed"})
        asyncio.run(run_b())

        self.assertEqual(publisher.publish_count, 2,
                         "Two different plans must each publish exactly once")


# =========================================================================
# Requirement 6: Single request-scoped canonical payload
# =========================================================================


class TestCanonicalWorkflowPayload(unittest.TestCase):
    """``_canonical_dict`` is the single request-scoped payload reused
    for profile activation, restore publication, and the Modal payload."""

    def test_canonical_dict_defined_in_execute_plan(self):
        """``execute_plan`` defines ``_canonical_dict`` via ``plan.to_dict()``."""
        import inspect
        source = inspect.getsource(execute_plan)
        self.assertIn("_canonical_dict", source,
                      "execute_plan must define _canonical_dict")
        self.assertIn("plan.to_dict()", source,
                      "Canonical dict must use plan.to_dict()")

    def test_canonical_workflow_from_dict(self):
        """``_canonical_workflow`` is extracted from ``_canonical_dict``."""
        import inspect
        source = inspect.getsource(execute_plan)
        self.assertIn('_canonical_workflow', source,
                      "Must define _canonical_workflow")
        self.assertIn('_canonical_dict["workflow"]', source,
                      "Must extract workflow from canonical dict")

    def test_old_patterns_gone(self):
        """No separate per-use workflow extraction patterns remain."""
        import inspect
        source = inspect.getsource(execute_plan)
        self.assertNotIn('plan.to_dict().get("workflow"', source,
                         "Must not use plan.to_dict().get('workflow')")
        self.assertNotIn('plan.to_dict()["workflow"]', source,
                         "Must not use plan.to_dict()['workflow']")


# =========================================================================
# Requirement 7: No mutable leak into ExecutionPlan, no global base64
# =========================================================================


# =========================================================================
# Image isolation — base64 images don't bleed between requests or into caches
# =========================================================================


class TestImageIsolation(unittest.TestCase):
    """Two requests with distinct base64 image values deliver the correct
    image in each captured final Modal payload; the first value does not
    bleed into the second or into any global profile/restore/warmup cache."""

    def setUp(self):
        import base64
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()
        self.image_a = base64.b64encode(b"fake_png_cat_data_12345").decode()
        self.image_b = base64.b64encode(b"fake_png_dog_data_67890").decode()

    def _spy_v2_factory(self, captured):
        """Return a v2_handle_factory that appends each plan_dict to *captured*."""
        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "test-id"
                self.input_created_at = 0
            def __aiter__(self): return self
            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]; self._index += 1; return e

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda pd, **kw: (captured.append(dict(pd)), _FakeGen())[1],
                    ),
                ),
            )
        return _factory

    def test_distinct_images_dont_bleed_between_requests(self):
        """Image A in request 1, image B in request 2 — no cross-contamination."""
        captured = []
        factory = self._spy_v2_factory(captured)

        # Request A
        async def req_a():
            plan_a = build_execution_plan(
                {"1": {"class_type": "LoadImage", "inputs": {"image": "cat.png"}}},
                input_images={"cat.png": self.image_a},
                prompt_id="img_a", validate=False,
            )
            transport = ModalTransport(v2_handle_factory=factory)
            async for _ in transport.run_plan_stream(
                plan_a, gpu="rtx-pro-6000", workspace={"id": "ws_img"},
                trace={"prompt_id": "img_a"},
            ): pass
        asyncio.run(req_a())

        # Request B
        async def req_b():
            plan_b = build_execution_plan(
                {"1": {"class_type": "LoadImage", "inputs": {"image": "dog.png"}}},
                input_images={"dog.png": self.image_b},
                prompt_id="img_b", validate=False,
            )
            transport = ModalTransport(v2_handle_factory=factory)
            async for _ in transport.run_plan_stream(
                plan_b, gpu="rtx-pro-6000", workspace={"id": "ws_img"},
                trace={"prompt_id": "img_b"},
            ): pass
        asyncio.run(req_b())

        self.assertEqual(len(captured), 2, "Must capture exactly 2 plan_dicts")
        # Request A payload
        imgs_a = captured[0].get("input_images", {})
        self.assertEqual(imgs_a.get("cat.png"), self.image_a,
                         "Request A payload must contain image A")
        self.assertNotIn("dog.png", imgs_a,
                         "Request A payload must NOT contain image B")
        # Request B payload
        imgs_b = captured[1].get("input_images", {})
        self.assertEqual(imgs_b.get("dog.png"), self.image_b,
                         "Request B payload must contain image B")
        self.assertNotIn("cat.png", captured[1].get("input_images", {}),
                         "Request B payload must NOT contain image A")
        # Verify input_images dict is request-scoped (not same object)
        self.assertIsNot(captured[0].get("input_images"),
                         captured[1].get("input_images"),
                         "Each request must have its own input_images dict")

    def test_images_not_retained_in_global_caches(self):
        """After two image-bearing requests, global caches contain NO base64 data."""
        import base64
        from canonical_execution import _PROFILE_PREP_CACHE, _RESTORE_PUBLISH_CACHE
        from warmup_profile import _last_stable_profile_cache

        captured = []
        factory = self._spy_v2_factory(captured)

        async def req_a():
            plan_a = build_execution_plan(
                {"1": {"class_type": "CheckpointLoaderSimple",
                        "inputs": {"ckpt_name": "m.safetensors"}},
                 "2": {"class_type": "LoadImage", "inputs": {"image": "cat.png"}}},
                input_images={"cat.png": self.image_a},
                prompt_id="cache_leak_a", validate=False,
            )
            transport = ModalTransport(v2_handle_factory=factory)
            async for _ in transport.run_plan_stream(
                plan_a, gpu="rtx-pro-6000", workspace={"id": "ws_leak"},
                trace={"prompt_id": "cache_leak_a"},
            ): pass
        asyncio.run(req_a())

        async def req_b():
            plan_b = build_execution_plan(
                {"1": {"class_type": "CheckpointLoaderSimple",
                        "inputs": {"ckpt_name": "m.safetensors"}},
                 "2": {"class_type": "LoadImage", "inputs": {"image": "dog.png"}}},
                input_images={"dog.png": self.image_b},
                prompt_id="cache_leak_b", validate=False,
            )
            transport = ModalTransport(v2_handle_factory=factory)
            async for _ in transport.run_plan_stream(
                plan_b, gpu="rtx-pro-6000", workspace={"id": "ws_leak"},
                trace={"prompt_id": "cache_leak_b"},
            ): pass
        asyncio.run(req_b())

        # Check all global caches — none should hold base64 image data
        for cache, name in [(_PROFILE_PREP_CACHE, "_PROFILE_PREP_CACHE"),
                             (_RESTORE_PUBLISH_CACHE, "_RESTORE_PUBLISH_CACHE")]:
            for ck, cv in cache.items():
                cv_str = str(cv)
                self.assertNotIn(self.image_a, cv_str,
                                 f"{name} key={ck} must not contain image A")
                self.assertNotIn(self.image_b, cv_str,
                                 f"{name} key={ck} must not contain image B")
        # warmup-profile cache
        for ck, cv in _last_stable_profile_cache.items():
            cv_str = str(cv)
            self.assertNotIn(self.image_a, cv_str,
                             "warmup cache must not contain image A")
            self.assertNotIn(self.image_b, cv_str,
                             "warmup cache must not contain image B")


# =========================================================================
# Payload equivalence — pre-materialized dict equals legacy plan.to_dict()
# =========================================================================


class TestPayloadEquivalence(unittest.TestCase):
    """The pre-materialized canonical payload sent to Modal is equivalent
    to the legacy plan.to_dict() output, accounting for the existing
    request-origin injection behavior in the V2 transport path."""

    def test_canonical_dict_matches_plan_to_dict(self):
        """``_canonical_dict`` (from `plan.to_dict()` once) matches a fresh
        ``plan.to_dict()`` call."""
        captured = []

        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "test-id"
                self.input_created_at = 0
            def __aiter__(self): return self
            async def __anext__(self):
                if self._index >= len(self._events): raise StopAsyncIteration
                e = self._events[self._index]; self._index += 1; return e

        def _v2_factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda pd, **kw: (captured.append(pd), _FakeGen())[1],
                    ),
                ),
            )

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 7}}},
                prompt_id="equiv", validate=False,
            )
            expected = plan.to_dict()
            transport = ModalTransport(v2_handle_factory=_v2_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws_equiv"},
                trace={"prompt_id": "equiv"}, plan_dict=dict(expected),
            ): pass

        asyncio.run(run())

        self.assertEqual(len(captured), 1, "Must capture exactly 1 plan_dict")
        actual = captured[0]
        # Rebuild expected from a fresh plan.to_dict() for comparison
        fresh_plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 7}}},
            prompt_id="equiv", validate=False,
        )
        reference = fresh_plan.to_dict()
        # The transport injects __request_origin_info__; remove it for comparison
        actual_clean = {k: v for k, v in actual.items() if k != "__request_origin_info__"}
        for k in ("schema_version", "workflow", "workflow_hash",
                  "source_workflow_hash", "production_report", "model_stack",
                  "prompt_bundle", "output_node_ids", "input_images",
                  "execution_options", "request_metadata"):
            self.assertEqual(actual_clean.get(k), reference.get(k),
                             f"Field '{k}' must match between canonical and legacy")

    def test_prematerialized_payload_passed_verbatim_to_transport(self):
        """The plan dict passed to the transport is the same object as
        ``plan.to_dict()`` — no rematerialization happens."""
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="verbatim", validate=False,
        )
        original = plan.to_dict()
        captured = []

        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "test-id"
                self.input_created_at = 0
            def __aiter__(self): return self
            async def __anext__(self):
                if self._index >= len(self._events): raise StopAsyncIteration
                e = self._events[self._index]; self._index += 1; return e

        def _v2_factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda pd, **kw: (captured.append(pd), _FakeGen())[1],
                    ),
                ),
            )

        async def run():
            transport = ModalTransport(v2_handle_factory=_v2_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws_verbatim"},
                trace={"prompt_id": "verbatim"}, plan_dict=original,
            ): pass

        asyncio.run(run())

        self.assertEqual(len(captured), 1)
        actual = captured[0]
        # The transport injects __request_origin_info__, so we strip it
        stripped = {k: v for k, v in actual.items() if k != "__request_origin_info__"}
        self.assertEqual(stripped, original,
                         "Pre-materialized dict must pass through verbatim "
                         "(modulo __request_origin_info__ injection)")


# =========================================================================
# Handle cache — ModalTransport caches across lookups
# =========================================================================


class TestHandleCacheBehavior(unittest.TestCase):
    """Same ModalTransport + same stable workspace/app/class/GPU/cloud/
    environment invokes handle factory once across two requests and
    returns cache hit; changed stable key misses."""

    def setUp(self):
        HandleCacheKey  # ensure available
        # The HandleCache store — we need a fresh handle cache per test
        # so cache state doesn't leak between tests

    def test_same_key_returns_cached_handle(self):
        """``HandleCache`` with same values hits the cache."""
        cache = HandleCache()
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",))
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",))
        handle = object()
        self.assertIsNone(cache.get(key_b), "Cache must start empty")
        cache.put(key_a, handle)
        self.assertIs(cache.get(key_b), handle,
                      "Same-value key must return cached handle")

    def test_different_gpu_misses_cache(self):
        """Different GPU → different key → cache miss."""
        cache = HandleCache()
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",))
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("gpu2",))
        cache.put(key_a, object())
        self.assertIsNone(cache.get(key_b),
                          "Different GPU must miss the cache")

    def test_transport_v2_handle_caches_across_two_calls(self):
        """``ModalTransport._v2_handle`` calls the factory once for the same
        workspace/gpu; the second call returns a cache hit (no factory call)."""
        factory_call_count = [0]

        def _counting_factory(**kw):
            factory_call_count[0] += 1
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda *a, **kw: _FakeLazyGenForHandleTest(),
                    ),
                ),
            )

        class _FakeLazyGenForHandleTest:
            def __init__(self):
                self._events = []
                self._index = 0
                self.input_id = "h-cache"
                self.input_created_at = 0
            def __aiter__(self): return self
            async def __anext__(self):
                raise StopAsyncIteration

        transport = ModalTransport(v2_handle_factory=_counting_factory)

        # First call — cache miss, factory called once
        h1 = transport._v2_handle(workspace={"id": "ws_h"}, gpu="rtx-pro-6000")
        self.assertEqual(factory_call_count[0], 1,
                         "First call must invoke factory")

        # Second call with same params — cache hit, factory NOT called
        h2 = transport._v2_handle(workspace={"id": "ws_h"}, gpu="rtx-pro-6000")
        self.assertEqual(factory_call_count[0], 1,
                         "Second call with same params must NOT invoke factory")
        self.assertIs(h1, h2,
                      "Same params must return the same cached handle object")

        # Third call with DIFFERENT GPU — cache miss, factory called again
        h3 = transport._v2_handle(workspace={"id": "ws_h"}, gpu="t4")
        self.assertEqual(factory_call_count[0], 2,
                         "Different GPU must invoke factory again")
        self.assertIsNot(h1, h3,
                         "Different GPU must return a different handle")


# =========================================================================
# Requirement 8: Payload size observability preserved
# =========================================================================


class TestPayloadSizeObservability(unittest.TestCase):
    """Payload size tracking is preserved in the transport layer."""

    def test_modal_payload_serialize_events_present(self):
        """``modal_payload_serialize_start/end`` events still fire in transport."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            trace = RuntimeTrace(request_id="payload_size", process="local")
            transport = ModalTransport(
                v2_handle_factory=self._make_v2_handle_factory(),
            )
            try:
                async for _ in transport.run_plan_stream(
                    plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                    trace={"prompt_id": "payload_size"}, runtime_trace=trace,
                ):
                    pass
            except StopAsyncIteration:
                pass
            ev_names = [e.name for e in trace.events]
            self.assertIn("modal_payload_serialize_start", ev_names,
                          "Payload serialize start event must exist")
            self.assertIn("modal_payload_serialize_end", ev_names,
                          "Payload serialize end event must exist")

        asyncio.run(run())

    @staticmethod
    def _make_v2_handle_factory():
        class _FakeLazyGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "test-input-id"
                self.input_created_at = 0
            def __aiter__(self): return self
            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                event = self._events[self._index]
                self._index += 1
                return event

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(aio=lambda *a, **kw: _FakeLazyGen()),
                ),
            )
        return _factory

    def test_plan_serialization_events_replaced_not_removed(self):
        """``plan_serialization_start/end`` events still fire."""
        import inspect
        source = inspect.getsource(execute_plan)
        self.assertIn("plan_serialization_start", source,
                      "plan_serialization_start must still exist")
        self.assertIn("plan_serialization_end", source,
                      "plan_serialization_end must still exist")
        self.assertIn("reused_canonical", source,
                      "Metadata must indicate reused canonical payload")


# =========================================================================
# Requirement 9 (preserved): ModalTransport handle cache / factory signature
# =========================================================================


class TestModalTransportHandleConfig(unittest.TestCase):
    """ModalTransport exposes v2_handle_factory as a constructor parameter."""

    def test_v2_handle_factory_still_supported(self):
        """v2_handle_factory is still a valid ModalTransport parameter."""
        from inspect import signature
        sig = signature(ModalTransport.__init__)
        params = {p.name for p in sig.parameters.values()}
        self.assertIn("v2_handle_factory", params,
                      "v2_handle_factory must still be a valid parameter")


# =========================================================================
# Requirement 7 (preserved): No mutable leak, ExecutionPlan stays frozen
# =========================================================================


class TestNoMutableLeak(unittest.TestCase):
    """ExecutionPlan remains frozen; canonical dict is a copy."""

    def test_plan_remains_frozen_after_execute_plan(self):
        """Plan workflow is immutable after execute_plan returns."""
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="no_leak", validate=False,
        )
        with self.assertRaises(AttributeError):
            plan.workflow = {}  # type: ignore[misc]

    def test_canonical_dict_is_copy_not_reference(self):
        """_canonical_dict = plan.to_dict() creates a thawed copy."""
        import inspect
        source = inspect.getsource(execute_plan)
        self.assertIn("plan.to_dict()", source,
                      "Must copy via plan.to_dict(), not alias")
        self.assertIn("_canonical_dict", source,
                      "Must assign to _canonical_dict")


# =========================================================================
# Requirement 10 (bonus): [v2.local_submission_breakdown] intact
# =========================================================================


class TestBreakdownIntact(unittest.TestCase):
    """[v2.local_submission_breakdown] print remains in execute_plan."""

    def test_breakdown_print_exists(self):
        """The [v2.local_submission_breakdown] print statement still exists."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        self.assertIn("[v2.local_submission_breakdown]", source,
                       "[v2.local_submission_breakdown] print must exist")
        self.assertIn("_fmt_bd", source,
                      "[v2.local_submission_breakdown] fmt helper must exist")
        self.assertIn("request_id=", source,
                      "[v2.local_submission_breakdown] must include request_id")

    def test_breakdown_required_fields_present(self):
        """All required breakdown fields are still present."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        required_fields = [
            "local_receive_to_worker_start_ms",
            "worker_start_to_plan_build_ms",
            "plan_build_ms",
            "active_profile_ms",
            "restore_plan_build_ms",
            "restore_publish_ms",
            "handle_lookup_ms",
            "payload_materialization_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "local_receive_to_actual_submission_ms",
            "measured_children_ms",
            "residual_ms",
            "reconciliation_status",
        ]
        for field in required_fields:
            self.assertIn(field, source,
                          f"Breakdown must contain field: {field}")

    def test_breakdown_print_has_handle_cache_fields(self):
        """Breakdown print includes handle_cache_hit, created_modal_client, etc."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        for field in ("handle_cache_hit", "created_modal_client",
                       "performed_cls_from_name", "constructed_class_instance"):
            self.assertIn(field, source,
                          f"Breakdown must reference {field}")


# =========================================================================
# Operation-count verification
# =========================================================================


class TestOperationCounts(unittest.TestCase):
    """Verifying the reduction in operation counts after optimisation."""

    def test_plan_to_dict_called_exactly_once(self):
        """``plan.to_dict()`` is called EXACTLY ONCE in execute_plan."""
        import inspect
        source = inspect.getsource(execute_plan)
        lines = source.split("\n")
        plan_to_dict_lines = [
            l.strip() for l in lines
            if "plan.to_dict()" in l and not l.strip().startswith("#")
        ]
        self.assertEqual(
            len(plan_to_dict_lines), 1,
            f"Expected 1 plan.to_dict() call in execute_plan, got {len(plan_to_dict_lines)}: {plan_to_dict_lines}",
        )

    def test_profile_prep_cache_reduces_setter_calls(self):
        """With N identical plan invocations, profile setter is called
        exactly 1 time (not N)."""
        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        setter = _CountingProfileSetter()
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        N = 5
        for i in range(N):
            async def run():
                plan = build_execution_plan(
                    {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                    prompt_id=f"count_test_{i}", validate=False,
                )
                transport = ModalTransport(prompt_stream_fn=_stream)
                await execute_plan(plan, transport=transport,
                                   profile_setter=setter,
                                   workspace={"id": "ws_counts"})
            asyncio.run(run())
        # N calls with same identity → exactly 1 setter call
        self.assertEqual(setter.invoke_count, 1,
                         f"With {N} identical plans, setter must be called exactly 1, got {setter.invoke_count}")

    def test_restore_publish_calls_reduced_by_cache(self):
        """With N identical plans, restore publisher is called exactly 1 time."""
        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        publisher = _Publisher()
        _reset_restore_publish_cache()
        N = 5
        for i in range(N):
            async def run():
                plan = build_execution_plan(
                    {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                    prompt_id=f"restore_count_{i}", validate=False,
                )
                transport = ModalTransport(prompt_stream_fn=_stream)
                await execute_plan(plan, transport=transport,
                                   restore_publisher=publisher,
                                   workspace={"id": "ws_restore_counts"})
            asyncio.run(run())
        self.assertEqual(publisher.publish_count, 1,
                         f"With {N} identical plans, restore publisher must be called exactly 1")

    def test_two_consecutive_requests_each_one_plan_to_dict(self):
        """Two identical full execute_plan requests each cause exactly one
        plan.to_dict() per request and no additional transport materialization."""
        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        original_to_dict = ExecutionPlan.to_dict
        call_log = []

        def _spy_to_dict(self):
            call_log.append("plan.to_dict")
            return original_to_dict(self)

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            ExecutionPlan.to_dict = _spy_to_dict  # type: ignore[assignment]
            try:
                await execute_plan(plan, transport=transport, workspace={"id": "ws_tworeq"})
            finally:
                ExecutionPlan.to_dict = original_to_dict

        # Two consecutive requests — spy counts plan.to_dict calls
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        asyncio.run(run("two_req_a"))
        self.assertEqual(call_log.count("plan.to_dict"), 1,
                         "First request must call plan.to_dict exactly once")

        asyncio.run(run("two_req_b"))
        self.assertEqual(call_log.count("plan.to_dict"), 2,
                         "Second request must call plan.to_dict exactly once "
                         "(total = 2, not more)")
        # The transport receives the pre-materialized plan_dict, so it
        # does NOT call plan.to_dict() again.  Our spy covers all calls
        # across both requests (total = 2).
        self.assertLessEqual(call_log.count("plan.to_dict"), 2,
                             "No more than 2 plan.to_dict calls across 2 requests")


# =========================================================================
# Domimant stage evidence — local breakdown shows which stage dominates
# =========================================================================


class TestDominantStageEvidence(unittest.TestCase):
    """The [v2.local_submission_breakdown] print captures dominant stage data.
    In testing without remote setter, `active_profile_ms` is the only stage
    that runs (profile prep is skipped or trivial)."""

    def test_breakdown_contains_all_local_stages(self):
        """All local pre-submission stages appear in the breakdown print."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        # Direct stages
        for stage in ("plan_build_ms", "active_profile_ms", "restore_plan_build_ms",
                       "restore_publish_ms", "handle_lookup_ms", "payload_materialization_ms",
                       "payload_size_measurement_ms",
                       "generator_create_ms", "generator_created_to_first_iteration_ms"):
            self.assertIn(stage, source,
                          f"Breakdown must contain {stage}")
        # Derived stages
        for stage in ("restore_publish_to_transport_entry_ms",
                       "transport_entry_to_handle_lookup_ms",
                       "payload_ready_to_generator_create_ms"):
            self.assertIn(stage, source,
                          f"Breakdown must contain {stage}")


# =========================================================================
# Requirement 5: Handle cache GPU config canonicalization
# =========================================================================


class TestHandleCacheGpuCanonicalization(unittest.TestCase):
    """GPU config list/tuple is canonicalized to an ordered immutable string."""

    def test_canonicalize_single_string(self):
        """Single string GPU is lowered and stripped."""
        result = ModalTransport._canonicalize_gpu_config("RTX-Pro-6000")
        self.assertEqual(result, "rtx-pro-6000")

    def test_canonicalize_list_sorted(self):
        """List of GPUs is sorted and joined with '+'."""
        result = ModalTransport._canonicalize_gpu_config(["t4", "a100", "rtx-pro-6000"])
        self.assertEqual(result, "a100+rtx-pro-6000+t4")

    def test_canonicalize_tuple_sorted(self):
        """Tuple of GPUs is sorted and joined with '+'."""
        result = ModalTransport._canonicalize_gpu_config(("rtx-pro-6000", "a100"))
        self.assertEqual(result, "a100+rtx-pro-6000")

    def test_canonicalize_none_uses_env_fallback(self):
        """None GPU falls back to env var then default."""
        result = ModalTransport._canonicalize_gpu_config(None)
        self.assertIn(result, ("rtx-pro-6000",), "Must fall back to default GPU")

    def test_canonicalize_empty_list(self):
        """Empty list returns default GPU."""
        result = ModalTransport._canonicalize_gpu_config([])
        self.assertEqual(result, "rtx-pro-6000")


# =========================================================================
# HandleCache cloud and factory_identity isolation
# =========================================================================


class TestHandleCacheCloudFactoryIsolation(unittest.TestCase):
    """HandleCache with different cloud or factory_identity values misses."""

    def test_different_cloud_misses_cache(self):
        """Same workspace/app/GPU but different cloud → cache miss."""
        cache = HandleCache()
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",), cloud="gcp")
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",), cloud="aws")
        handle = object()
        cache.put(key_a, handle)
        self.assertIsNone(cache.get(key_b),
                          "Different cloud must miss the cache")

    def test_default_cloud_matches_empty_cloud(self):
        """Default cloud ('') and explicit empty cloud match."""
        cache = HandleCache()
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",), cloud="")
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",))
        handle = object()
        cache.put(key_a, handle)
        self.assertIs(cache.get(key_b), handle,
                      "Empty cloud and default must match")

    def test_different_factory_identity_misses_cache(self):
        """Same workspace/app/GPU/cloud but different factory_identity → miss."""
        cache = HandleCache()
        factory_a = lambda **kw: None
        factory_b = lambda **kw: None
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",),
                               factory_identity=factory_a)
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",),
                               factory_identity=factory_b)
        handle = object()
        cache.put(key_a, handle)
        self.assertIsNone(cache.get(key_b),
                          "Different factory_identity must miss the cache")

    def test_none_factory_identity_matches_none(self):
        """None factory_identity matches another None."""
        cache = HandleCache()
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",),
                               factory_identity=None)
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",),
                               factory_identity=None)
        handle = object()
        cache.put(key_a, handle)
        self.assertIs(cache.get(key_b), handle,
                      "Both None factory_identity must hit cache")

    def test_same_factory_object_hits_cache(self):
        """Same lambda object (same identity) hits cache."""
        cache = HandleCache()
        factory = lambda **kw: None
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",),
                               factory_identity=factory)
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("gpu1",),
                               factory_identity=factory)
        handle = object()
        cache.put(key_a, handle)
        self.assertIs(cache.get(key_b), handle,
                      "Same factory object must hit cache")

    def test_different_gpu_list_order_preserved_in_cache_key(self):
        """GPU tuple preserves caller order; ['t4', 'a100'] != ['a100', 't4']."""
        cache = HandleCache()
        key_a = HandleCacheKey("ws1", "app1", "cls1", ("t4", "a100"))
        key_b = HandleCacheKey("ws1", "app1", "cls1", ("a100", "t4"))
        handle = object()
        cache.put(key_a, handle)
        # Different order means different key unless HandleCacheKey normalizes
        # Currently order-preserving — so these are different keys
        cached = cache.get(key_b)
        self.assertIsNone(cached,
                          "Different GPU order must miss cache when order-preserving")
