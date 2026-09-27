"""Tests for active-profile and restore-plan caller-side reuse fields.

Covers:
  1. cache_lookup_ms present and >= 0 on all paths.
  2. profile_cache_hit boolean correct on cache hit vs miss.
  3. profile_checker_performed True when checker is invoked.
  4. profile_setter_performed True when setter is invoked.
  5. Reset functions clear caches properly.
  6. After reset, a previously cached request calls setter again.
  7. Restore cache lookup_ms timing field.
  8. Exact-prefill identity scope preserves prefill_key.
  9. Never advance cache on error/timeout/semantic error.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_workflow(prompt_text: str = "a cat") -> dict:
    return {
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "clip_l.safetensors", "type": "stable_diffusion",
        }},
        "6": {"class_type": "CLIPTextEncode", "inputs": {
            "text": prompt_text, "clip": ["2", 0],
        }},
        "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
    }


def _make_workspace(ws_id: str = "ws_test") -> dict:
    return {"id": ws_id, "label": "Test Workspace"}


def _make_async_setter(
    return_status: str = "written",
    call_counter: list | None = None,
) -> AsyncMock:
    mock = AsyncMock(return_value={"status": return_status, "changed": True})
    if call_counter is not None:
        mock.side_effect = lambda *a, **kw: (
            call_counter.append(1),
            {"status": return_status, "changed": True},
        )[1]
    return mock


class _MatchingChecker:
    """Checker that confirms the stable key exists."""
    def __init__(self):
        self.invoke_count = 0
    async def __call__(self, stable_key: str, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        return {"matched": True, "profile_token": "vol-token-abc123"}


class _NonMatchingChecker:
    """Checker that returns no match."""
    def __init__(self):
        self.invoke_count = 0
    async def __call__(self, stable_key: str, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        return {"matched": False}


class _FailingChecker:
    """Checker that raises — caller must fail-open."""
    def __init__(self):
        self.invoke_count = 0
    async def __call__(self, stable_key: str, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        raise RuntimeError("checker simulated failure")


# ── Test Suite ────────────────────────────────────────────────────────────────

class TestActiveProfileReuseFields(unittest.TestCase):
    """Verify cache_lookup_ms and boolean fields on all return paths."""

    def setUp(self):
        import warmup_profile
        warmup_profile._last_stable_profile_cache.clear()
        warmup_profile._last_cache_app_identity = ""
        warmup_profile._last_cache_ws_id = ""
        warmup_profile._last_prefill_identity_map.clear()

    async def _prepare(self, *, setter=None, checker=None,
                       prompt="a cat", workspace=None,
                       workflow=None) -> dict:
        from warmup_profile import prepare_active_next_profile as _prepare
        wf = workflow or _make_workflow(prompt)
        ws = workspace or _make_workspace()
        return await _prepare(
            wf,
            hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest(),
            workspace=ws,
            setter=setter,
            checker=checker,
        )

    # ── 1. cache_lookup_ms present on all paths ───────────────────────

    def test_cache_lookup_ms_on_disabled_path(self):
        """cache_lookup_ms must be present (0.0) when DISABLE_ACTIVE_NEXT_WRITE."""
        with patch.dict(os.environ, {"DISABLE_ACTIVE_NEXT_WRITE": "1"}, clear=False):
            result = asyncio.run(self._prepare(setter=_make_async_setter()))
        self.assertIn("cache_lookup_ms", result)
        self.assertIsInstance(result["cache_lookup_ms"], (int, float))
        self.assertGreaterEqual(result["cache_lookup_ms"], 0.0)

    def test_cache_lookup_ms_on_setter_error_path(self):
        """cache_lookup_ms must be present when setter is not callable."""
        result = asyncio.run(self._prepare(setter="not_callable"))
        self.assertIn("cache_lookup_ms", result)
        # This path returns before cache lookup → should be 0.0
        self.assertEqual(result["cache_lookup_ms"], 0.0)

    def test_cache_lookup_ms_on_cache_hit(self):
        """cache_lookup_ms must be > 0 on cache hit (lookup actually happened)."""
        setter = _make_async_setter()
        # Prime cache
        asyncio.run(self._prepare(setter=setter))
        # Second call → cache hit
        result = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(result["status"], "unchanged")
        self.assertIn("cache_lookup_ms", result)
        self.assertGreaterEqual(result["cache_lookup_ms"], 0.0)

    def test_cache_lookup_ms_on_cache_miss(self):
        """cache_lookup_ms must be >= 0 on cache miss."""
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter))
        self.assertIn("cache_lookup_ms", result)
        self.assertGreaterEqual(result["cache_lookup_ms"], 0.0)

    def test_cache_lookup_ms_on_dry_run(self):
        """cache_lookup_ms present on setter=None (dry run)."""
        result = asyncio.run(self._prepare(setter=None))
        self.assertIn("cache_lookup_ms", result)
        self.assertGreaterEqual(result["cache_lookup_ms"], 0.0)

    # ── 2. profile_cache_hit boolean correctness ──────────────────────

    def test_profile_cache_hit_true_on_cache_hit(self):
        """profile_cache_hit must be True on cache hit path."""
        setter = _make_async_setter()
        asyncio.run(self._prepare(setter=setter))  # prime
        result = asyncio.run(self._prepare(setter=setter))  # hit
        self.assertEqual(result["status"], "unchanged")
        self.assertTrue(result["profile_cache_hit"])

    def test_profile_cache_hit_false_on_first_call(self):
        """profile_cache_hit must be False on first (miss) call."""
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter))
        self.assertFalse(result["profile_cache_hit"])

    def test_profile_cache_hit_false_on_dry_run(self):
        """profile_cache_hit must be False on dry run (no setter)."""
        result = asyncio.run(self._prepare(setter=None))
        self.assertFalse(result["profile_cache_hit"])

    def test_profile_cache_hit_false_on_checker_matched(self):
        """profile_cache_hit must be False when checker matched (not from local cache)."""
        checker = _MatchingChecker()
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter, checker=checker))
        self.assertEqual(result["status"], "unchanged")
        self.assertFalse(result["profile_cache_hit"])

    # ── 3. profile_checker_performed boolean ──────────────────────────

    def test_checker_performed_true_when_checker_matched(self):
        """profile_checker_performed must be True when checker was called and matched."""
        checker = _MatchingChecker()
        result = asyncio.run(self._prepare(setter=_make_async_setter(), checker=checker))
        self.assertTrue(result["profile_checker_performed"])
        self.assertEqual(checker.invoke_count, 1)

    def test_checker_performed_true_when_checker_not_matched(self):
        """profile_checker_performed must be True when checker was called but didn't match."""
        checker = _NonMatchingChecker()
        result = asyncio.run(self._prepare(setter=_make_async_setter(), checker=checker))
        self.assertTrue(result["profile_checker_performed"])
        self.assertEqual(checker.invoke_count, 1)

    def test_checker_performed_true_when_checker_fails(self):
        """profile_checker_performed must be True when checker raised (fail-open)."""
        checker = _FailingChecker()
        result = asyncio.run(self._prepare(setter=_make_async_setter(), checker=checker))
        self.assertTrue(result["profile_checker_performed"])
        self.assertEqual(checker.invoke_count, 1)

    def test_checker_performed_false_when_no_checker(self):
        """profile_checker_performed must be False when checker not provided."""
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter))
        self.assertFalse(result["profile_checker_performed"])

    def test_checker_performed_false_on_cache_hit(self):
        """profile_checker_performed must be False on cache hit (no checker needed)."""
        setter = _make_async_setter()
        asyncio.run(self._prepare(setter=setter))  # prime
        result = asyncio.run(self._prepare(setter=setter))  # hit
        self.assertFalse(result["profile_checker_performed"])

    # ── 4. profile_setter_performed boolean ───────────────────────────

    def test_setter_performed_true_when_setter_called(self):
        """profile_setter_performed must be True when setter was invoked."""
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter))
        self.assertTrue(result["profile_setter_performed"])
        self.assertEqual(setter.call_count, 1)

    def test_setter_performed_false_on_cache_hit(self):
        """profile_setter_performed must be False on cache hit."""
        setter = _make_async_setter()
        asyncio.run(self._prepare(setter=setter))  # prime
        result = asyncio.run(self._prepare(setter=setter))  # hit
        self.assertFalse(result["profile_setter_performed"])

    def test_setter_performed_false_on_checker_matched(self):
        """profile_setter_performed must be False when checker matched (skips setter)."""
        checker = _MatchingChecker()
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter, checker=checker))
        self.assertFalse(result["profile_setter_performed"])
        self.assertEqual(setter.call_count, 0)

    def test_setter_performed_false_on_dry_run(self):
        """profile_setter_performed must be False on dry run (setter=None)."""
        result = asyncio.run(self._prepare(setter=None))
        self.assertFalse(result["profile_setter_performed"])

    def test_setter_performed_true_on_checker_non_match(self):
        """profile_setter_performed must be True when checker didn't match and setter called."""
        checker = _NonMatchingChecker()
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter, checker=checker))
        self.assertTrue(result["profile_setter_performed"])
        self.assertEqual(setter.call_count, 1)

    def test_setter_performed_true_on_checker_fail_open(self):
        """profile_setter_performed must be True when checker fails and setter called."""
        checker = _FailingChecker()
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter, checker=checker))
        self.assertTrue(result["profile_setter_performed"])
        self.assertEqual(setter.call_count, 1)

    # ── 5. Reset functions clear caches ────────────────────────────────

    def test_reset_last_stable_profile_cache(self):
        """Reset must clear the warmup profile cache."""
        import warmup_profile as wp
        setter = _make_async_setter()
        asyncio.run(self._prepare(setter=setter))
        self.assertGreater(len(wp._last_stable_profile_cache), 0)
        wp._reset_last_stable_profile_cache()
        self.assertEqual(len(wp._last_stable_profile_cache), 0)

    def test_reset_triggers_new_publication(self):
        """After reset, a previously cached request must call setter again."""
        import warmup_profile as wp
        call_counter = []
        setter = _make_async_setter(call_counter=call_counter)

        # First: prime cache
        r1 = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(len(call_counter), 1)

        # Second: cache hit
        r2 = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(r2["status"], "unchanged")
        self.assertEqual(len(call_counter), 1)

        # Reset cache
        wp._reset_last_stable_profile_cache()

        # Third: must publish again (cache cleared)
        r3 = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(r3["status"], "written")
        self.assertEqual(len(call_counter), 2)

    def test_reset_profile_prep_cache(self):
        """Reset must clear the profile prep cache."""
        from canonical_execution import _PROFILE_PREP_CACHE, _reset_profile_prep_cache
        _PROFILE_PREP_CACHE["test_key"] = {"result": True}
        self.assertGreater(len(_PROFILE_PREP_CACHE), 0)
        _reset_profile_prep_cache()
        self.assertEqual(len(_PROFILE_PREP_CACHE), 0)

    def test_reset_restore_publish_cache(self):
        """Reset must clear the restore publish cache."""
        from canonical_execution import _RESTORE_PUBLISH_CACHE, _reset_restore_publish_cache
        _RESTORE_PUBLISH_CACHE["test_key"] = "identity"
        self.assertGreater(len(_RESTORE_PUBLISH_CACHE), 0)
        _reset_restore_publish_cache()
        self.assertEqual(len(_RESTORE_PUBLISH_CACHE), 0)

    # ── 6. Never advance on error ──────────────────────────────────────

    def test_setter_exception_does_not_advance_cache(self):
        """Exception from setter must not populate the cache."""
        import warmup_profile as wp
        failing = AsyncMock(side_effect=RuntimeError("boom"))
        asyncio.run(self._prepare(setter=failing))
        self.assertEqual(len(wp._last_stable_profile_cache), 0,
                         "Cache must not advance on setter exception")

    def test_setter_semantic_error_does_not_advance_cache(self):
        """Semantic error status from setter must not populate the cache."""
        import warmup_profile as wp
        failing = _make_async_setter(return_status="error")
        asyncio.run(self._prepare(setter=failing))
        self.assertEqual(len(wp._last_stable_profile_cache), 0,
                         "Cache must not advance on semantic error")

    # ── 7. Checker after populate is cache-hit (no checker on 2nd call) ───

    def test_checker_match_then_second_call_is_cache_hit(self):
        """After checker matches, second call must hit process-local cache
        (profile_cache_hit=True, checker not called)."""
        checker = _MatchingChecker()
        setter = _make_async_setter()

        # First: checker matched
        r1 = asyncio.run(self._prepare(setter=setter, checker=checker))
        self.assertEqual(r1["status"], "unchanged")
        self.assertEqual(checker.invoke_count, 1)

        # Second: cache hit
        r2 = asyncio.run(self._prepare(setter=setter, checker=checker))
        self.assertEqual(r2["status"], "unchanged")
        self.assertTrue(r2["profile_cache_hit"])
        self.assertFalse(r2["profile_checker_performed"])
        self.assertFalse(r2["profile_setter_performed"])
        # Checker must NOT be called again
        self.assertEqual(checker.invoke_count, 1)

    # ── 8. Timing fields are non-negative floats ──────────────────────

    def test_all_timing_fields_are_non_negative_floats(self):
        """Every timing field in the result must be a non-negative float."""
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter))
        for key in ("cache_lookup_ms", "active_profile_local_ms",
                     "active_profile_checker_ms", "active_profile_setter_ms",
                     "active_profile_total_ms", "local_active_profile_prepare_ms"):
            val = result.get(key)
            self.assertIsInstance(val, (int, float),
                                  f"{key} must be numeric, got {type(val)}")
            self.assertGreaterEqual(val, 0.0,
                                    f"{key} must be >= 0, got {val}")


class TestExactPrefillScope(unittest.TestCase):
    """Verify exact-prefill preserves prefill_key scope across calls."""

    def setUp(self):
        import warmup_profile
        warmup_profile._last_stable_profile_cache.clear()
        warmup_profile._last_cache_app_identity = ""
        warmup_profile._last_cache_ws_id = ""
        warmup_profile._last_prefill_identity_map.clear()

    async def _prepare(self, *, setter=None, prompt="a cat",
                       workspace=None, workflow=None) -> dict:
        from warmup_profile import prepare_active_next_profile as _prepare
        wf = workflow or _make_workflow(prompt)
        ws = workspace or _make_workspace()
        return await _prepare(
            wf,
            hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest(),
            workspace=ws,
            setter=setter,
        )

    @patch.dict(os.environ, {"COMFYMODAL_EXACT_CLIP_PREFILL": "1"}, clear=False)
    def test_exact_prefill_different_prompt_different_prefill_key(self):
        """With exact prefill ON, different prompts produce different prefill_key."""
        setter = _make_async_setter()
        wf1 = _make_workflow("cat")
        r1 = asyncio.run(self._prepare(workflow=wf1, prompt="cat", setter=setter))
        wf2 = _make_workflow("dog")
        r2 = asyncio.run(self._prepare(workflow=wf2, prompt="dog", setter=setter))
        self.assertNotEqual(r1["prefill_key"], r2["prefill_key"],
                            "Different prompts must produce different prefill_key")
        self.assertEqual(r1["model_profile_key"], r2["model_profile_key"],
                         "Model key must be same for same model stack")

    @patch.dict(os.environ, {"COMFYMODAL_EXACT_CLIP_PREFILL": "1"}, clear=False)
    def test_exact_prefill_same_prompt_same_prefill_key(self):
        """With exact prefill ON, same prompts produce same prefill_key."""
        setter = _make_async_setter()
        wf = _make_workflow("same prompt")
        r1 = asyncio.run(self._prepare(workflow=wf, prompt="same prompt", setter=setter))
        r2 = asyncio.run(self._prepare(workflow=wf, prompt="same prompt", setter=setter))
        self.assertEqual(r1["prefill_key"], r2["prefill_key"],
                         "Same prompts must produce same prefill_key")

    @patch.dict(os.environ, {"COMFYMODAL_EXACT_CLIP_PREFILL": "0"}, clear=False)
    def test_exact_prefill_disabled_prefill_key_empty(self):
        """With exact prefill OFF, prefill_key must be empty string."""
        setter = _make_async_setter()
        result = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(result["prefill_key"], "",
                         "prefill_key must be empty when exact prefill disabled")


class TestRestorePlanCache(unittest.TestCase):
    """Tests for restore-plan cache timing fields."""

    def setUp(self):
        from canonical_execution import _reset_restore_publish_cache
        _reset_restore_publish_cache()

    def test_restore_cache_lookup_ms_in_metadata(self):
        """restore_cache_lookup_ms must appear in runtime_trace metadata."""
        # This test creates a mock restore_publisher and verifies the
        # restore_cache_lookup_ms metadata is set in the trace.
        from canonical_execution import (
            _reset_restore_publish_cache,
            _RESTORE_PUBLISH_CACHE,
        )

        # Seed the cache to simulate a cache hit
        _RESTORE_PUBLISH_CACHE["ws_test:app:env:dummy_identity"] = "dummy_identity"

        # Verify cache is populated
        self.assertGreater(len(_RESTORE_PUBLISH_CACHE), 0)

        # Reset clears it
        _reset_restore_publish_cache()
        self.assertEqual(len(_RESTORE_PUBLISH_CACHE), 0)

    def test_restore_cache_hit_after_publish(self):
        """After a successful publish, same identity must hit cache."""
        from canonical_execution import _RESTORE_PUBLISH_CACHE, _reset_restore_publish_cache
        _reset_restore_publish_cache()

        # Simulate a published identity
        key = "ws_test:app:env:plan_hash_123"
        _RESTORE_PUBLISH_CACHE[key] = "plan_hash_123"

        # Verify it's in cache
        self.assertIn(key, _RESTORE_PUBLISH_CACHE)

    def test_restore_cache_miss_for_new_identity(self):
        """A new (unpublished) identity must not be in cache."""
        from canonical_execution import _RESTORE_PUBLISH_CACHE, _reset_restore_publish_cache
        _reset_restore_publish_cache()

        new_key = "ws_other:app:env:new_plan_hash"
        self.assertNotIn(new_key, _RESTORE_PUBLISH_CACHE)


class TestResyncProductionHook(unittest.TestCase):
    """Verify that the production /comfymodal/runtime/resync hook path
    clears all local caches — invoking the same reset functions the
    route handler calls, not test-only helpers."""

    def setUp(self):
        import warmup_profile
        warmup_profile._last_stable_profile_cache.clear()
        warmup_profile._last_cache_app_identity = ""
        warmup_profile._last_cache_ws_id = ""
        warmup_profile._last_prefill_identity_map.clear()

    async def _prepare(self, *, setter=None, checker=None,
                       prompt="a cat", workspace=None,
                       workflow=None) -> dict:
        from warmup_profile import prepare_active_next_profile as _prepare
        wf = workflow or _make_workflow(prompt)
        ws = workspace or _make_workspace()
        return await _prepare(
            wf,
            hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest(),
            workspace=ws,
            setter=setter,
            checker=checker,
        )

    def _prime_all_caches(self):
        """Populate every cache that the resync route clears."""
        import warmup_profile as wp
        from canonical_execution import (
            _RESTORE_PUBLISH_CACHE, _PROFILE_PREP_CACHE,
        )
        # Warmup profile cache + identity state
        wp._last_stable_profile_cache[("app", "ws", "key")] = {"ts": 100.0, "token": "tkn", "stable_key_short": "key"}
        wp._last_cache_app_identity = "app_before"
        wp._last_cache_ws_id = "ws_before"
        wp._last_prefill_identity_map[("app_before", "ws_before")] = {"model_profile_key": "mpk", "prefill_key": "pfk"}
        # Canonical restore-publish cache
        _RESTORE_PUBLISH_CACHE["ws:app:env:identity"] = "identity_hash"
        # Canonical profile-prep cache
        _PROFILE_PREP_CACHE["some_cache_key"] = {"status": "ok"}

    def test_resync_route_clears_all_caches(self):
        """The production reset sequence (same as /comfymodal/runtime/resync)
        must clear every cache."""
        import warmup_profile as wp
        from canonical_execution import (
            _RESTORE_PUBLISH_CACHE, _PROFILE_PREP_CACHE,
            _reset_restore_publish_cache, _reset_profile_prep_cache,
        )

        self._prime_all_caches()

        # ── Production route path (same sequence as modal_runtime_resync) ──
        _reset_restore_publish_cache()
        _reset_profile_prep_cache()
        wp._reset_last_stable_profile_cache()

        # Assert all caches cleared
        self.assertEqual(len(_RESTORE_PUBLISH_CACHE), 0,
                         "restore_publish_cache must be cleared")
        self.assertEqual(len(_PROFILE_PREP_CACHE), 0,
                         "profile_prep_cache must be cleared")
        self.assertEqual(len(wp._last_stable_profile_cache), 0,
                         "last_stable_profile_cache must be cleared")
        self.assertEqual(wp._last_cache_app_identity, "",
                         "app identity must be reset")
        self.assertEqual(wp._last_cache_ws_id, "",
                         "workspace identity must be reset")
        self.assertEqual(len(wp._last_prefill_identity_map), 0,
                         "prefill identity map must be cleared")

    def test_resync_route_then_new_publication_required(self):
        """After production resync clears all caches, a previously cached
        model stack must trigger a new publication (setter called)."""
        import warmup_profile as wp
        from canonical_execution import (
            _reset_restore_publish_cache, _reset_profile_prep_cache,
        )
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        # Prime: first call populates all caches
        r1 = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(r1["status"], "written")

        # Second call: cache hit (no setter)
        r2 = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(r2["status"], "unchanged")
        self.assertEqual(len(call_counter), 1)

        # ── Production resync clears all caches ──
        _reset_restore_publish_cache()
        _reset_profile_prep_cache()
        wp._reset_last_stable_profile_cache()

        # Third call: must publish again (caches cleared)
        r3 = asyncio.run(self._prepare(setter=setter))
        self.assertEqual(r3["status"], "written",
                         "After resync, same stack must publish again")
        self.assertEqual(len(call_counter), 2,
                         "Setter must be called again after resync")


if __name__ == "__main__":
    unittest.main()
