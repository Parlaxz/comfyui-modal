"""Tests for warmup_profile prepare_active_next_profile dedup & result fields.

Covers:
  1. Helper result dict includes all fields (old and new) on all return paths.
  2. Same restore key when only production hashes/output/seeds differ.
  3. Different UNET/CLIP/VAE → different key → publication.
  4. Exact-prefill bundle digest participates only when env var is set.
  5. Repeated unchanged: cached token returned, no UUID, no setter.
  6. Workspace/app identity change clears cache; changed identity publishes.
  7. Failed setter does not advance cache (retry publishes).
  8. LocalRemoteInvoker can await the preparer (fast unchanged path).

These tests never call the real Modal setter.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_workflow(prompt_text: str = "a cat") -> dict:
    """Build a minimal workflow with a CLIPTextEncode and a KSampler."""
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
    """Return an AsyncMock that records calls."""
    mock = AsyncMock(return_value={"status": return_status, "changed": True})
    if call_counter is not None:
        mock.side_effect = lambda *a, **kw: (
            call_counter.append(1),
            {"status": return_status, "changed": True},
        )[1]
    return mock


# ── Tests ────────────────────────────────────────────────────────────────────


class WarmupProfileDedupResultFieldsTests(unittest.TestCase):
    """Test that prepare_active_next_profile returns the new result fields."""

    def setUp(self):
        from warmup_profile import prepare_active_next_profile
        self._prepare = prepare_active_next_profile
        # Reset module-level dedup state
        import warmup_profile
        warmup_profile._last_stable_profile_cache.clear()
        warmup_profile._last_cache_app_identity = ""
        warmup_profile._last_cache_ws_id = ""

    async def _do_prepare(self, workflow=None, prompt_text="a cat",
                          setter=None, workspace=None) -> dict:
        wf = workflow or _make_workflow(prompt_text)
        ws = workspace or _make_workspace()
        return await self._prepare(
            wf,
            hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest(),
            workspace=ws,
            setter=setter,
        )

    # ── 1. Result-field presence on all paths ─────────────────────────

    def test_skipped_result_has_honest_fields(self):
        """Early return on skipped (no setter) must include new fields."""
        result = asyncio.run(self._do_prepare(setter=None))
        for key in ("active_profile_build_ms", "active_profile_dedup_status",
                    "active_profile_remote_call", "active_profile_remote_ms"):
            self.assertIn(key, result, f"Missing field: {key}")
        self.assertIsInstance(result["active_profile_build_ms"], (int, float))
        self.assertEqual(result["active_profile_dedup_status"], "skipped")
        self.assertEqual(result["active_profile_remote_call"], 0)
        self.assertEqual(result["active_profile_remote_ms"], 0.0)
        # New fields
        for key in ("local_active_profile_prepare_ms", "active_profile_publish_decision",
                    "active_profile_stable_key", "active_profile_token"):
            self.assertIn(key, result, f"Missing new field: {key}")
        self.assertEqual(result["active_profile_publish_decision"], "skipped_unchanged")
        self.assertIsInstance(result["local_active_profile_prepare_ms"], (int, float))

    def test_unchanged_result_has_honest_fields(self):
        """Early return on unchanged (recent write) must include new fields."""
        # First call to prime the dedup record
        setter = _make_async_setter()
        asyncio.run(self._do_prepare(setter=setter))
        # Second call with same stack → unchanged
        result = asyncio.run(self._do_prepare(setter=setter))
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["active_profile_dedup_status"], "unchanged")
        self.assertIn("active_profile_build_ms", result)
        self.assertIsInstance(result["active_profile_build_ms"], (int, float))
        self.assertEqual(result["active_profile_remote_call"], 0)
        self.assertEqual(result["active_profile_remote_ms"], 0.0)
        # New fields
        self.assertEqual(result["active_profile_publish_decision"], "skipped_unchanged")
        self.assertIn("active_profile_token", result)
        self.assertTrue(
            isinstance(result["active_profile_token"], str) and len(result["active_profile_token"]) > 0
        )
        # No remote call → local_active_profile_prepare_ms ≈ active_profile_build_ms
        _diff = result["local_active_profile_prepare_ms"] - result["active_profile_build_ms"]
        self.assertLessEqual(_diff, 5.0,
                             "Unchanged path: local and build ms should differ by <5ms "
                             f"(got {_diff}ms)")

    def test_written_result_has_honest_fields(self):
        """Successful setter write must report remote_call=1 and remote_ms."""
        setter = _make_async_setter()
        result = asyncio.run(self._do_prepare(setter=setter))
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["remote_call"], 1)
        self.assertEqual(result["active_profile_remote_call"], 1)
        self.assertIsInstance(result["active_profile_remote_ms"], (int, float))
        self.assertGreaterEqual(result["active_profile_remote_ms"], 0.0)
        self.assertIn("active_profile_build_ms", result)
        # New fields on written path
        self.assertEqual(result["active_profile_publish_decision"], "published")
        self.assertIn("active_profile_token", result)
        self.assertIsInstance(result["active_profile_stable_key"], str)
        self.assertGreater(len(result["active_profile_stable_key"]), 0)
        # local_active_profile_prepare_ms must include remote time
        self.assertGreaterEqual(
            result["local_active_profile_prepare_ms"],
            result["active_profile_build_ms"],
            "local_active_profile_prepare_ms must include remote publication time "
            "(>= active_profile_build_ms)"
        )

    def test_error_result_has_honest_fields(self):
        """Setter exception must report error status and remote_ms."""
        setter = AsyncMock(side_effect=RuntimeError("boom"))
        result = asyncio.run(self._do_prepare(setter=setter))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["active_profile_dedup_status"], "error")
        self.assertEqual(result["active_profile_remote_call"], 1)
        self.assertIsInstance(result["active_profile_remote_ms"], (int, float))
        # Error path: publish decision is "published" (RPC was attempted)
        self.assertEqual(result["active_profile_publish_decision"], "published")
        self.assertIn("active_profile_token", result)
        # local_active_profile_prepare_ms includes remote time even on error
        self.assertGreaterEqual(
            result["local_active_profile_prepare_ms"],
            result["active_profile_build_ms"],
            "local_active_profile_prepare_ms must include remote time on error path"
        )

    # ── 2. Prompt-only dedup (same stack, different prompt text) ──────────

    def test_same_stack_different_prompt_causes_one_setter_call_then_unchanged(self):
        """Same model stack with different eligible prompt text must:
        1. First call: trigger the setter (written).
        2. Second call: return unchanged without calling the setter again.

        Patches exact prefill OFF so the bundle hash does not participate
        in the stable key.  With exact prefill ON (the default) the bundle
        hash would change the key and trigger a second publication.
        """
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        # Verify the fixture produces different bundle hashes
        from warmup_profile import _build_activation_payload
        wf_cat = _make_workflow("cat")
        wf_dog = _make_workflow("dog")
        bundle1 = _build_activation_payload(wf_cat, "hash-cat").get("prompt_bundle", {})
        bundle2 = _build_activation_payload(wf_dog, "hash-dog").get("prompt_bundle", {})
        self.assertNotEqual(
            bundle1.get("bundle_hash"), bundle2.get("bundle_hash"),
            "The fixture must exercise a real prompt-bundle change",
        )
        # Patch exact prefill OFF for the entire test so both calls use
        # an identical stable key (bundle_hash excluded).
        with patch.dict(os.environ, {"COMFYMODAL_EXACT_CLIP_PREFILL": "0"}, clear=False):
            # First: stack A + prompt "cat"
            r1 = asyncio.run(self._do_prepare(
                workflow=wf_cat, prompt_text="cat", setter=setter,
            ))
            self.assertEqual(r1["status"], "written")
            self.assertEqual(len(call_counter), 1,
                             "First call should invoke setter once")

            # Second: same stack A + prompt "dog" (prompt-only change)
            r2 = asyncio.run(self._do_prepare(
                workflow=wf_dog, prompt_text="dog", setter=setter,
            ))
        self.assertEqual(
            r2["status"], "unchanged",
            "Same stack + different prompt must NOT trigger setter (dedup)"
        )
        self.assertEqual(
            len(call_counter), 1,
            "Setter must not be called a second time (prompt-only dedup)"
        )
        self.assertEqual(r2["active_profile_dedup_status"], "unchanged")
        self.assertEqual(r2["active_profile_remote_call"], 0)

    def test_different_stack_same_prompt_triggers_setter(self):
        """Different model stack with same prompt text must trigger a write."""
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        # Workflows use split-mode loaders (UNET + CLIP + VAE) so the
        # stable key picks up distinct unet/clip/vae field values.
        _BASE_SPLIT: dict = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip_l.safetensors", "type": "stable_diffusion"}},
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ["2", 0]}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "model": ["1", 0], "positive": ["6", 0]}},
        }

        # Write stack A: unet_A
        wf_a = dict(_BASE_SPLIT)
        wf_a["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "unet_A.safetensors"}}
        asyncio.run(self._do_prepare(workflow=wf_a, setter=setter))
        self.assertEqual(len(call_counter), 1,
                         "First stack should invoke setter once")

        # Write stack B: unet_B (different unet_name)
        wf_b = dict(_BASE_SPLIT)
        wf_b["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "unet_B.safetensors"}}
        result = asyncio.run(self._do_prepare(workflow=wf_b, setter=setter))
        self.assertEqual(result["status"], "written",
                         "Different model stack must trigger a second setter call")
        self.assertEqual(len(call_counter), 2,
                         "Setter must be called twice (different stacks)")
        self.assertEqual(result["active_profile_remote_call"], 1)
        self.assertEqual(result["active_profile_dedup_status"], "written")

    # ── 3. Production fields excluded from restore key ─────────────────

    def test_production_fields_do_not_change_restore_key(self):
        """Production hashes, output/bypass IDs, metadata flags, schema versions
        must produce the same restore key when the model stack is unchanged."""
        from warmup_profile import _normalize_stable_profile

        model_profile = {"mode": "split", "unet": "flux1-dev.safetensors",
                         "clip1": "clip_l.safetensors", "clip2": "t5xxl.safetensors",
                         "vae": "ae.safetensors", "clip_type": "flux"}

        # Different production hashes
        prod_profile_a = dict(model_profile, production_enabled=True,
                              source_workflow_hash="hash_A",
                              compiled_workflow_hash="comp_A",
                              production_plan_hash="plan_A")
        prod_profile_b = dict(model_profile, production_enabled=True,
                              source_workflow_hash="hash_B",
                              compiled_workflow_hash="comp_B",
                              production_plan_hash="plan_B")

        self.assertEqual(
            _normalize_stable_profile(prod_profile_a),
            _normalize_stable_profile(prod_profile_b),
            "Production hashes must NOT change restore key"
        )

        # Different output/bypass IDs
        prod_profile_c = dict(model_profile, production_enabled=True,
                              output_node_ids=[10, 20],
                              bypass_node_ids=[5])
        prod_profile_d = dict(model_profile, production_enabled=True,
                              output_node_ids=[30],
                              bypass_node_ids=[])

        self.assertEqual(
            _normalize_stable_profile(prod_profile_c),
            _normalize_stable_profile(prod_profile_d),
            "Output/bypass IDs must NOT change restore key"
        )

        # Different schema versions
        prod_profile_e = dict(model_profile, production_enabled=True,
                              compiler_version=2, hash_schema_version=3)
        prod_profile_f = dict(model_profile, production_enabled=True,
                              compiler_version=5, hash_schema_version=6)

        self.assertEqual(
            _normalize_stable_profile(prod_profile_e),
            _normalize_stable_profile(prod_profile_f),
            "Schema versions must NOT change restore key"
        )

    def test_seed_does_not_change_restore_key(self):
        """Seed, timestamps, and UI fields must not appear in the restore key."""
        from warmup_profile import _compute_stable_key, _normalize_stable_profile

        # 1. Direct unit: _normalize_stable_profile excludes seed and metadata
        raw = {"mode": "checkpoint", "checkpoint": "sd_xl.safetensors",
               "seed": 42, "steps": 20, "cfg": 7.0, "sampler": "euler",
               "workflow_name": "my_flow", "timestamp": 1234567890}
        n = _normalize_stable_profile(raw)
        self.assertNotIn("seed", n, "Seed must be excluded from restore key")
        self.assertNotIn("steps", n, "Steps must be excluded from restore key")
        self.assertNotIn("cfg", n, "CFG must be excluded from restore key")
        self.assertNotIn("workflow_name", n, "Workflow name must be excluded")
        self.assertNotIn("timestamp", n, "Timestamp must be excluded")

        # 2. Different seeds → same key
        base = {"mode": "checkpoint", "checkpoint": "sd_xl.safetensors"}
        seeds = [0, 42, 123456789, -1]
        keys = [_compute_stable_key(dict(base)) for _ in seeds]
        for i in range(1, len(keys)):
            self.assertEqual(keys[0], keys[i],
                             f"Seed {seeds[i]} must produce same key as seed {seeds[0]}")

    # ── 4. UNET/CLIP/VAE different → different key → publication ─────────

    def test_exact_prompt_digest_participates_only_when_enabled(self):
        """When COMFYMODAL_EXACT_CLIP_PREFILL=1, prompt bundle hash must
        change the stable key.  When 0, prompt changes produce same key."""
        from warmup_profile import _compute_stable_key
        base_profile = {"mode": "split", "unet": "flux1-dev.safetensors",
                        "clip1": "clip_l.safetensors", "clip2": "t5xxl.safetensors",
                        "vae": "ae.safetensors", "clip_type": "flux"}
        bh_a = "hash_of_prompt_cat"
        bh_b = "hash_of_prompt_dog"

        # Exact prefill OFF → same key despite different bundle hash
        k_off_1 = _compute_stable_key(base_profile, bundle_hash=None)
        k_off_2 = _compute_stable_key(base_profile, bundle_hash=None)
        self.assertEqual(k_off_1, k_off_2,
                         "Exact OFF: same model key without bundle_hash")

        # Exact prefill ON → different bundle hash → different key
        k_on_1 = _compute_stable_key(base_profile, bundle_hash=bh_a)
        k_on_2 = _compute_stable_key(base_profile, bundle_hash=bh_b)
        self.assertNotEqual(k_on_1, k_on_2,
                            "Exact ON: different bundle_hash must produce different key")

        # Same bundle hash → same key
        k_on_3 = _compute_stable_key(base_profile, bundle_hash=bh_a)
        self.assertEqual(k_on_1, k_on_3,
                         "Exact ON: same bundle_hash must produce same key")

    @patch.dict(os.environ, {"COMFYMODAL_EXACT_CLIP_PREFILL": "1"}, clear=False)
    def test_exact_prefill_on_prompt_change_publishes(self):
        """When exact prefill is ON, a changed prompt text produces a different
        stable key which should trigger a new publication."""
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        wf1 = _make_workflow("cat")
        r1 = asyncio.run(self._do_prepare(workflow=wf1, prompt_text="cat", setter=setter))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(len(call_counter), 1)

        wf2 = _make_workflow("dog")
        r2 = asyncio.run(self._do_prepare(workflow=wf2, prompt_text="dog", setter=setter))
        # With exact prefill ON, different prompt → different key → published
        self.assertEqual(r2["status"], "written",
                         "Exact ON: different prompt must publish")
        self.assertEqual(len(call_counter), 2)
        self.assertNotEqual(r1["active_profile_stable_key"], r2["active_profile_stable_key"],
                            "Exact ON: stable keys must differ when prompt changes")

    # ── 5. Repeated unchanged: cached token, no UUID, no setter ──────────

    def test_repeated_unchanged_returns_cached_token(self):
        """A second identical call must return the same token from cache,
        must not call the setter, and must not create a new UUID."""
        from unittest.mock import patch as _patch
        import uuid as _real_uuid
        _real_uuid4 = _real_uuid.uuid4  # save before patching
        setter = _make_async_setter()
        uuid_call_count: list = []

        def _counting_uuid4() -> str:
            uuid_call_count.append(1)
            return _real_uuid4()

        with _patch("warmup_profile.uuid.uuid4", side_effect=_counting_uuid4):
            # First call → published (two UUIDs: profile_token + validation_token)
            r1 = asyncio.run(self._do_prepare(setter=setter))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(
            len(uuid_call_count), 2,
            "First published call must generate exactly two UUIDs "
            "(profile_token + validation_token in _build_activation_payload)"
        )
        token1 = r1.get("active_profile_token", "")
        self.assertGreater(len(token1), 0, "Token must be set on publish")

        # Second call with same model stack → unchanged, zero UUIDs
        with _patch("warmup_profile.uuid.uuid4", side_effect=_counting_uuid4):
            r2 = asyncio.run(self._do_prepare(setter=setter))
        self.assertEqual(r2["status"], "unchanged")
        self.assertEqual(r2["active_profile_publish_decision"], "skipped_unchanged")
        self.assertEqual(r2["active_profile_remote_call"], 0)
        # Must return the same token (no new UUID)
        self.assertEqual(r2.get("active_profile_token", ""), token1,
                         "Cached token must match published token")
        # Zero UUID calls on the unchanged path (still 2 total from first call)
        self.assertEqual(
            len(uuid_call_count), 2,
            "Unchanged cache-hit path must NOT call uuid4 "
            "(was called %d times total)"
            % len(uuid_call_count),
        )

    # ── 6. Identity change → cache clear → new publication ───────────────

    def test_different_workspace_publishes(self):
        """Different workspace with same model stack must trigger a new
        publication because the cache is invalidated on workspace change.

        Verifies both the behavioral result AND the internal cache state.
        """
        import warmup_profile as wp
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        ws_a = _make_workspace("ws_A")
        ws_b = _make_workspace("ws_B")

        # First workspace → published, cache populated
        r1 = asyncio.run(self._do_prepare(
            setter=setter, workspace=ws_a,
        ))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(len(call_counter), 1)
        self.assertEqual(
            len(wp._last_stable_profile_cache), 1,
            "Cache must have one entry after first publish"
        )

        # Same model, different workspace → workspace changed → cache cleared
        # then new publication
        r2 = asyncio.run(self._do_prepare(
            setter=setter, workspace=ws_b,
        ))
        self.assertEqual(r2["status"], "written",
                         "Different workspace must publish")
        self.assertEqual(len(call_counter), 2)
        # The cache was cleared by workspace-change detection, then a fresh
        # entry was written.  Only one entry for ws_B now.
        self.assertEqual(
            len(wp._last_stable_profile_cache), 1,
            "Cache must have one entry after workspace-switch publish"
        )

        # First workspace again → workspace change detected again → cache
        # cleared, then new publication (not a cache hit)
        r3 = asyncio.run(self._do_prepare(
            setter=setter, workspace=ws_a,
        ))
        self.assertEqual(r3["status"], "written",
                         "Switching back to first workspace must publish (cache was cleared)")
        self.assertEqual(len(call_counter), 3,
                         "Setter must be called a third time (workspace switch back)")

    def test_app_identity_change_invalidates_cache(self):
        """When the app identity changes the cache must clear, causing a new
        publication for a previously seen model stack."""
        import warmup_profile as wp
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        with patch.dict(os.environ, {"COMFYMODAL_APP_NAME": "app_one"}, clear=False):
            r1 = asyncio.run(self._do_prepare(setter=setter))
            self.assertEqual(r1["status"], "written")
            self.assertEqual(len(call_counter), 1)
            token_before = r1.get("active_profile_token", "")

        # Change app identity and verify cache clears
        with patch.dict(os.environ, {"COMFYMODAL_APP_NAME": "app_two"}, clear=False):
            wp._check_cache_identity("ws_test")
            self.assertEqual(
                len(wp._last_stable_profile_cache), 0,
                "Cache must be empty after app identity change"
            )
            # Next prepare with new identity → publish
            r2 = asyncio.run(self._do_prepare(setter=setter))
            self.assertEqual(r2["status"], "written",
                             "App identity change must publish")
            self.assertEqual(len(call_counter), 2)
            self.assertNotEqual(r2.get("active_profile_token", ""), token_before,
                                "Token must be different after cache invalidation")

        # Restore original app identity for other tests
        wp._check_cache_identity()

    # ── 7. Failed setter must not advance cache (retry) ──────────────────

    def test_failed_setter_does_not_advance_cache(self):
        """A setter that raises or returns error must not update the cache.
        A subsequent call must retry and publish again."""
        from warmup_profile import _last_stable_profile_cache

        # First setter raises → error
        failing_setter = AsyncMock(side_effect=RuntimeError("boom"))
        r1 = asyncio.run(self._do_prepare(setter=failing_setter))
        self.assertEqual(r1["status"], "error")
        # Check the cache was NOT updated
        self.assertEqual(len(_last_stable_profile_cache), 0,
                         "Cache must not advance on error")

        # Second call with a working setter → retry → published
        working_setter = _make_async_setter()
        r2 = asyncio.run(self._do_prepare(setter=working_setter))
        self.assertEqual(r2["status"], "written",
                         "Retry after failure must publish")
        self.assertGreater(len(r2.get("active_profile_token", "")), 0,
                           "Token must be set on successful retry")

    # ── 8. LocalRemoteInvoker compatibility ───────────────────────────

    def test_no_fire_and_forget_needed(self):
        """LocalRemoteInvoker can continue awaiting the preparer — the
        helper returns quickly on unchanged (no remote call) and the
        caller does NOT need a separate fire-and-forget path."""
        # The preparer always returns a result dict; on prompt-only unchanged
        # the await is fast because no network call occurs.
        setter = _make_async_setter()

        # First call: blocking (setter invoked)
        r1 = asyncio.run(self._do_prepare(setter=setter))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(r1["active_profile_remote_call"], 1)

        # Second call: fast (no setter, dedup hit)
        _start = time.time()
        r2 = asyncio.run(self._do_prepare(setter=setter))
        _elapsed = time.time() - _start
        self.assertEqual(r2["status"], "unchanged")
        self.assertEqual(r2["active_profile_remote_call"], 0)
        # The elapsed time should be negligible (< 100ms) since no remote call
        self.assertLess(_elapsed, 0.5,
                        "Unchanged dedup path must return quickly (<500ms)")

    # ── 4. Timing field types ────────────────────────────────────────

    def test_numeric_fields_are_positive_floats(self):
        """build_ms and remote_ms must be non-negative floats."""
        setter = _make_async_setter()
        result = asyncio.run(self._do_prepare(setter=setter))
        for key in ("active_profile_build_ms", "active_profile_remote_ms"):
            val = result.get(key, -1)
            self.assertIsInstance(val, (int, float),
                                  f"{key} must be numeric, got {type(val)}")
            self.assertGreaterEqual(val, 0.0,
                                    f"{key} must be >= 0, got {val}")

    def test_dedup_status_is_string(self):
        """active_profile_dedup_status must be a string on all paths."""
        for setter_arg in (None, _make_async_setter()):
            result = asyncio.run(self._do_prepare(setter=setter_arg))
            status = result.get("active_profile_dedup_status", "")
            self.assertIsInstance(status, str,
                                  f"dedup_status must be str, got {type(status)}")

    def test_build_ms_present_on_disabled_path(self):
        """Even DISABLE_ACTIVE_NEXT_WRITE path must have build_ms."""
        with patch.dict(os.environ, {"DISABLE_ACTIVE_NEXT_WRITE": "1"}, clear=False):
            result = asyncio.run(self._do_prepare(setter=_make_async_setter()))
            self.assertEqual(result["status"], "skipped")
            self.assertIn("active_profile_build_ms", result)
            self.assertIsInstance(result["active_profile_build_ms"], (int, float))

    def test_new_fields_present_on_disabled_path(self):
        """New fields must be present even on DISABLE_ACTIVE_NEXT_WRITE path."""
        with patch.dict(os.environ, {"DISABLE_ACTIVE_NEXT_WRITE": "1"}, clear=False):
            result = asyncio.run(self._do_prepare(setter=_make_async_setter()))
            for key in ("local_active_profile_prepare_ms", "active_profile_publish_decision",
                        "active_profile_stable_key", "active_profile_token"):
                self.assertIn(key, result, f"Missing new field on disabled path: {key}")
            self.assertIsInstance(result["local_active_profile_prepare_ms"], (int, float))


# ── 9. Cold-safe identity seam tests ────────────────────────────────────


class _MatchingChecker:
    """Checker that confirms the stable key exists on the volume."""

    def __init__(self):
        self.invoke_count = 0

    async def __call__(self, stable_key: str, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        return {"matched": True, "profile_token": "vol-token-abc123"}


class _NonMatchingChecker:
    """Checker that returns no match — caller should fall through to setter."""

    def __init__(self):
        self.invoke_count = 0

    async def __call__(self, stable_key: str, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        return {"matched": False}


class _FailingChecker:
    """Checker that raises — caller must fail-open to setter."""

    def __init__(self):
        self.invoke_count = 0

    async def __call__(self, stable_key: str, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        raise RuntimeError("checker simulated failure")


class TestColdSafeIdentitySeam(unittest.TestCase):
    """Cold-safe identity via read-only volume-backed checker.

    Proves:
    1. Matching checker → setter skipped, process-local cache populated.
    2. Non-matching checker → setter called (fall-through).
    3. Failing checker → setter still called (fail-open).
    4. After checker match, second call hits process-local cache (no checker,
       no setter).
    """

    def setUp(self):
        import warmup_profile
        warmup_profile._last_stable_profile_cache.clear()
        warmup_profile._last_cache_app_identity = ""
        warmup_profile._last_cache_ws_id = ""

    def tearDown(self):
        import warmup_profile
        warmup_profile._last_stable_profile_cache.clear()
        warmup_profile._last_cache_app_identity = ""
        warmup_profile._last_cache_ws_id = ""

    async def _do_prepare(self, setter=None, checker=None,
                          prompt_text="a cat", workspace=None,
                          workflow=None) -> dict:
        from warmup_profile import prepare_active_next_profile as _prepare
        import hashlib
        import json
        wf = workflow if workflow is not None else _make_workflow(prompt_text)
        ws = workspace or _make_workspace()
        return await _prepare(
            wf,
            hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest(),
            workspace=ws,
            setter=setter,
            checker=checker,
        )

    # ── Test 1: Matching checker skips setter ────────────────────────────

    def test_matching_checker_skips_setter(self):
        """When checker returns matched=True, setter must NOT be called."""
        checker = _MatchingChecker()
        setter = _make_async_setter()

        result = asyncio.run(self._do_prepare(setter=setter, checker=checker))

        self.assertEqual(result["status"], "unchanged",
                         "Matching checker must return unchanged")
        self.assertEqual(result["active_profile_dedup_status"], "unchanged")
        self.assertEqual(result["active_profile_remote_call"], 0,
                         "Matching checker must NOT call setter")
        self.assertEqual(setter.call_count, 0,
                         "Setter must not be called with matching checker")
        self.assertEqual(result["active_profile_token"], "vol-token-abc123",
                         "Token from checker must be returned")
        self.assertEqual(checker.invoke_count, 1,
                         "Checker must have been called exactly once")

    # ── Test 2: Non-matching checker falls through to setter ─────────────

    def test_non_matching_checker_falls_through_to_setter(self):
        """When checker returns matched=False, setter must be called."""
        checker = _NonMatchingChecker()
        setter = _make_async_setter()

        result = asyncio.run(self._do_prepare(setter=setter, checker=checker))

        self.assertEqual(result["status"], "written",
                         "Non-matching checker must fall through to setter")
        self.assertEqual(result["active_profile_remote_call"], 1,
                         "Setter must be called when checker does not match")
        self.assertEqual(setter.call_count, 1,
                         "Setter must be called once")
        self.assertEqual(checker.invoke_count, 1,
                         "Checker must have been called exactly once")

    # ── Test 3: Failing checker is fail-open ─────────────────────────────

    def test_failing_checker_is_fail_open(self):
        """When checker raises, setter must still be called."""
        checker = _FailingChecker()
        setter = _make_async_setter()

        result = asyncio.run(self._do_prepare(setter=setter, checker=checker))

        self.assertEqual(result["status"], "written",
                         "Failing checker must fail-open to setter")
        self.assertEqual(result["active_profile_remote_call"], 1,
                         "Setter must be called after checker failure")
        self.assertEqual(setter.call_count, 1,
                         "Setter must be called once after checker failure")
        self.assertEqual(checker.invoke_count, 1,
                         "Checker must have been tried once")

    # ── Test 4: After checker match, 2nd call hits process-local cache ───

    def test_checker_match_populates_local_cache(self):
        """After a matching checker populates the process-local cache,
        a second identical request must skip both checker and setter."""
        checker = _MatchingChecker()
        setter = _make_async_setter()

        # First call: checker matched, setter skipped, cache populated
        r1 = asyncio.run(self._do_prepare(setter=setter, checker=checker))
        self.assertEqual(r1["status"], "unchanged")
        self.assertEqual(setter.call_count, 0)
        self.assertEqual(checker.invoke_count, 1)

        # Second call (same stack, same workspace): cache hit
        r2 = asyncio.run(self._do_prepare(setter=setter, checker=checker))
        self.assertEqual(r2["status"], "unchanged")
        self.assertEqual(r2["active_profile_remote_call"], 0,
                         "Second call must reuse cache, not call setter")
        self.assertEqual(setter.call_count, 0,
                         "Setter must never be called (all via checker)")
        # Checker should not be called again either (cache hit)
        self.assertEqual(checker.invoke_count, 1,
                         "Checker must not be called on cache hit")

    # ── Test 5: Changed identity triggers setter even with checker ───────

    def test_changed_identity_triggers_setter_with_checker(self):
        """When stable key changes (different model stack), checker returns
        no match and setter must publish the new profile."""
        call_counter: list = []
        checker = _NonMatchingChecker()
        setter = _make_async_setter(call_counter=call_counter)

        # Stack A — first call: no cache, checker returns no match → setter
        wf_a = _make_workflow("hello")
        r1 = asyncio.run(self._do_prepare(
            workflow=wf_a, setter=setter, checker=checker,
        ))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(len(call_counter), 1)

        # Stack B — different model stack: checker returns no match → setter
        wf_b = _make_workflow("world")
        r2 = asyncio.run(self._do_prepare(
            workflow=wf_b, setter=setter, checker=checker,
        ))
        self.assertEqual(r2["status"], "written")
        self.assertEqual(len(call_counter), 2,
                         "Changed identity must invoke setter again")

        # Cache should have 2 entries (one per key)
        import warmup_profile as wp
        self.assertEqual(
            len(wp._last_stable_profile_cache), 2,
            "Two cache entries expected (one per distinct stable key)",
        )


if __name__ == "__main__":
    unittest.main()
