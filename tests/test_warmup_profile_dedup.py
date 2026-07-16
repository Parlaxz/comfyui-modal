"""Tests for warmup_profile prepare_active_next_profile dedup & result fields.

Covers:
  1. Same restore stack with different eligible prompt text → one setter
     call, then unchanged (prompt-only dedup).
  2. Helper result dict includes the new honest fields (build_ms, dedup_status,
     remote_call, remote_ms) on all return paths (skipped, unchanged, written).
  3. LocalRemoteInvoker does NOT need a new fire-and-forget path — the
     helper's built-in dedup handles prompt-only changes locally.
  4. Timing extraction preserves dedup_status (string) and numeric fields
     (remote_ms, build_ms) in the timing payload.

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
        warmup_profile._last_written_stable_profile.clear()

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

    def test_error_result_has_honest_fields(self):
        """Setter exception must report error status and remote_ms."""
        setter = AsyncMock(side_effect=RuntimeError("boom"))
        result = asyncio.run(self._do_prepare(setter=setter))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["active_profile_dedup_status"], "error")
        self.assertEqual(result["active_profile_remote_call"], 1)
        self.assertIsInstance(result["active_profile_remote_ms"], (int, float))

    # ── 2. Prompt-only dedup (same stack, different prompt text) ──────────

    def test_same_stack_different_prompt_causes_one_setter_call_then_unchanged(self):
        """Same model stack with different eligible prompt text must:
        1. First call: trigger the setter (written).
        2. Second call: return unchanged without calling the setter again.
        """
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        # First: stack A + prompt "cat"
        wf1 = _make_workflow("cat")
        r1 = asyncio.run(self._do_prepare(
            workflow=wf1, prompt_text="cat", setter=setter,
        ))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(len(call_counter), 1,
                         "First call should invoke setter once")

        # Second: same stack A + prompt "dog" (prompt-only change)
        wf2 = _make_workflow("dog")
        from warmup_profile import _build_activation_payload
        bundle1 = _build_activation_payload(wf1, "hash-cat").get("prompt_bundle", {})
        bundle2 = _build_activation_payload(wf2, "hash-dog").get("prompt_bundle", {})
        self.assertNotEqual(
            bundle1.get("bundle_hash"), bundle2.get("bundle_hash"),
            "The fixture must exercise a real prompt-bundle change",
        )
        r2 = asyncio.run(self._do_prepare(
            workflow=wf2, prompt_text="dog", setter=setter,
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

    # ── 3. Production hash diffs trigger setter ───────────────────────

    def test_production_hash_change_triggers_setter(self):
        """Two production payloads with identical model stack + options but
        different source_workflow_hash / compiled_workflow_hash / production_plan_hash
        must produce distinct dedup keys and each invoke the setter.
        Prompt-only changes (different text, same hashes) must still be deduped.
        """
        call_counter: list = []
        setter = _make_async_setter(call_counter=call_counter)

        # Build two production option dicts that differ only in the
        # three production hash fields.
        _BASE_PROD_OPTS: dict = {
            "enabled": True,
            "output_node_ids": [10],
            "bypass_node_ids": [],
            "metadata_mode": "all",
            "direct_output_sink": True,
            "allow_direct_output_rewrite": True,
            "allow_rgthree_comparer_rewrite": True,
            "compiler_version": 2,
            "hash_schema_version": 3,
            "production_plan_schema_version": 1,
        }
        prod_opts_a = dict(_BASE_PROD_OPTS, source_workflow_hash="hash_A",
                           compiled_workflow_hash="comp_A",
                           production_plan_hash="plan_A")
        prod_opts_b = dict(_BASE_PROD_OPTS, source_workflow_hash="hash_B",
                           compiled_workflow_hash="comp_B",
                           production_plan_hash="plan_B")

        wf = _make_workflow("same prompt")

        async def _run(opts):
            return await self._prepare(
                wf,
                hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest(),
                workspace=_make_workspace(),
                setter=setter,
                production_options=opts,
            )

        # First production payload → written
        r1 = asyncio.run(_run(prod_opts_a))
        self.assertEqual(r1["status"], "written")
        self.assertEqual(len(call_counter), 1)

        # Second production payload (different hashes, same model/options) → written
        r2 = asyncio.run(_run(prod_opts_b))
        self.assertEqual(
            r2["status"], "written",
            "Different production hash must trigger a setter call "
            "(same model stack + same production options)"
        )
        self.assertEqual(len(call_counter), 2)
        self.assertEqual(r2["active_profile_remote_call"], 1)
        self.assertEqual(r2["active_profile_dedup_status"], "written")

        # Verify profile keys differ
        self.assertNotEqual(r1["profile_key"], r2["profile_key"],
                            "Profile keys must differ when production hashes differ")

        # Repeat with prompt-only change (same hashes as prod_opts_b) → unchanged
        async def _run_2(wf2, opts):
            return await self._prepare(
                wf2,
                hashlib.sha256(json.dumps(wf2, sort_keys=True).encode()).hexdigest(),
                workspace=_make_workspace(),
                setter=setter,
                production_options=opts,
            )
        wf_diff_prompt = _make_workflow("different prompt with same model stack")
        r3 = asyncio.run(_run_2(wf_diff_prompt, prod_opts_b))
        self.assertEqual(
            r3["status"], "unchanged",
            "Same production hashes + different prompt must NOT trigger setter"
        )
        self.assertEqual(len(call_counter), 2,
                         "Setter must not be called a third time (prompt-only dedup)")
        self.assertEqual(r3["active_profile_remote_call"], 0)
        self.assertEqual(r3["active_profile_dedup_status"], "unchanged")

    # ── 4. LocalRemoteInvoker compatibility ───────────────────────────

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


if __name__ == "__main__":
    unittest.main()
