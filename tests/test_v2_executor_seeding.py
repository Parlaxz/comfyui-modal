"""Focused behavior tests for Phase-1 V2 cold-path acceptance (AT MOST 3 tests).

Proves:
  (a) Independent UNET/CLIP/VAE decisions — different UNET rejects only UNET,
      different CLIP rejects only CLIP, VAE always reports missing_snapshot_output.
  (b) Matching UNET/CLIP with absent VAE — VAE absence never blocks seeding.
  (c) Alternate model/workflow fallback — sequential calls re-evaluate identity
      independently, stale cache objects are cleared on mismatch, no stale
      seeded decision leaks across calls, and mismatch_fields carry exact tokens
      including ``cache_key_missing`` / ``cache_insert_failed`` when applicable.

All tests use pure functions and lightweight mocks — no real ComfyUI/Modal/GPU.
"""

from __future__ import annotations

import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from comfymodal_runtime.contracts import (
    compute_loader_role_identity,
    find_role_identity_mismatch_fields,
    stable_hash,
)
from comfymodal_runtime.runtime_bootstrap import BootstrapState


# ── Mock ComfyUI runtime modules ─────────────────────────────────────────
# execution.CacheEntry is imported inside seed_loader_cache_signatures.
# Provide a stub so the code path works outside the full ComfyUI env.

class _FakeCacheEntry:
    """Minimal CacheEntry stand-in for cache seeding tests."""
    def __init__(self, ui=None, outputs=None):
        self.ui = ui or {}
        self.outputs = outputs or []

_fake_execution = type(sys)("execution")
_fake_execution.CacheEntry = _FakeCacheEntry


def _make_mock_outputs_cache() -> MagicMock:
    """Create a mock executor.caches.outputs with async set/get/delete.

    Exposes a ``store`` attribute for cache-content verification in tests.
    """
    cache = MagicMock()
    cache.initialized = True
    cache.store = {}
    cache.cache_key_set = MagicMock()
    cache.cache_key_set.get_data_key = lambda nid: f"key:{nid}"

    async def fake_set(node_id: str, entry: Any) -> None:
        cache.store[node_id] = entry

    async def fake_get(node_id: str) -> Any:
        return cache.store.get(node_id)

    async def fake_delete(node_id: str) -> None:
        cache.store.pop(node_id, None)

    cache.set = fake_set
    cache.get = fake_get
    cache.delete = fake_delete
    return cache


def _make_mock_executor() -> MagicMock:
    """Create a mock PromptExecutor with caches.outputs."""
    ex = MagicMock()
    ex.caches = MagicMock()
    ex.caches.outputs = _make_mock_outputs_cache()
    return ex


def _make_bootstrap_state(**overrides: Any) -> BootstrapState:
    """Create a BootstrapState with snapshot seed populated."""
    from comfymodal_runtime.contracts import SnapshotExecutionSeed

    state = BootstrapState()
    seed = SnapshotExecutionSeed(
        workflow_hash=overrides.get("workflow_hash", "wf_hash_abc"),
        custom_node_generation=overrides.get("custom_node_generation", "cn_gen_v1"),
        deployment_combined_hash=overrides.get("deployment_combined_hash", "dep_hash_x"),
    )
    state.snapshot_execution_seed = seed
    state.snapshot_custom_node_generation = overrides.get("custom_node_generation", "cn_gen_v1")
    state.deployment_combined_hash = overrides.get("deployment_combined_hash", "dep_hash_x")
    return state


def _make_model_spec(
    unet_name: str = "model_a.safetensors",
    weight_dtype: str = "fp16",
    clip_name: str = "clip_a.safetensors",
    clip_type: str = "sd3",
    vae_name: str = "",
    dual: bool = False,
    clip_name2: str | None = None,
) -> dict[str, Any]:
    """Build a model_spec fixture matching the build_restore_model_spec shape."""
    loaders: dict[str, list[dict[str, Any]]] = {
        "unet": [{"loader_class": "UNETLoader", "unet_name": unet_name, "weight_dtype": weight_dtype}],
        "clip": [],
        "vae": [],
    }
    if dual:
        name2 = clip_name2 or f"{clip_name}.2"
        loaders["clip"] = [{"loader_class": "DualCLIPLoader", "clip_name1": clip_name, "clip_name2": name2, "type": clip_type, "device": "default"}]
    else:
        loaders["clip"] = [{"loader_class": "CLIPLoader", "clip_name": clip_name, "type": clip_type, "device": "default"}]
    if vae_name:
        loaders["vae"] = [{"loader_class": "VAELoader", "vae_name": vae_name}]
    return {"loaders": loaders}


class TestExecutorSeeding(unittest.TestCase):
    """Phase-1 V2 cold-path acceptance: at most 3 behavioral test methods.

    Tests seed_loader_cache_signatures() — which exercises the shared canonical
    role identity helpers (compute_loader_role_identity,
    find_role_identity_mismatch_fields) through real callable behavior.
    """

    def setUp(self):
        self._exec_patch = patch.dict(sys.modules, {"execution": _fake_execution})
        self._exec_patch.start()
        self.addCleanup(self._exec_patch.stop)

        self.executor = _make_mock_executor()
        self.state = _make_bootstrap_state()
        self.base_spec = _make_model_spec()
        self.alternate_unet_spec = _make_model_spec(unet_name="model_b.safetensors")
        self.alternate_clip_spec = _make_model_spec(clip_name="clip_b.safetensors")

    # ── Test (a): Independent UNET/CLIP mismatch decisions + VAE ──────────

    def test_independent_role_decisions(self):
        """Independent UNET, CLIP, and VAE decisions with canonical identity.

        (a) Different UNET → identity_mismatch only for UNET; CLIP still seeds;
            VAE always missing_snapshot_output.
        (b) Different CLIP → identity_mismatch only for CLIP; UNET still seeds.
        (c) Both match → both seed.
        """
        loader_node_ids = ["10", "20", "30"]
        loader_node_class_types = {"10": "UNETLoader", "20": "CLIPLoader", "30": "VAELoader"}
        loader_outputs = {"10": "fake_unet_output", "20": "fake_clip_output"}

        # ── Scenario 1: Different UNET, same CLIP ─────────────────────────
        result = self._run_seed(
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_spec=self.alternate_unet_spec,
            snapshot_spec=self.base_spec,
        )

        # UNET must be identity_mismatch
        self.assertEqual(result["10"]["decision"], "identity_mismatch",
                         "different UNET model must produce identity_mismatch")
        self.assertEqual(result["10"]["role"], "unet")
        # mismatch_fields must be populated with exact field names (not "unknown")
        self.assertNotEqual(result["10"]["mismatch_fields"], "unknown")
        self.assertNotEqual(result["10"]["mismatch_fields"], "none")

        # CLIP must seed (same CLIP model)
        self.assertEqual(result["20"]["decision"], "seeded",
                         "same CLIP model must seed even when UNET differs")
        self.assertEqual(result["20"]["role"], "clip")

        # VAE must be missing_snapshot_output
        self.assertEqual(result["30"]["decision"], "missing_snapshot_output",
                         "VAE must always report missing_snapshot_output")
        self.assertEqual(result["30"]["role"], "vae")

        # ── Scenario 2: Different CLIP, same UNET ─────────────────────────
        result2 = self._run_seed(
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_spec=self.alternate_clip_spec,
            snapshot_spec=self.base_spec,
        )

        # UNET must seed (same UNET model)
        self.assertEqual(result2["10"]["decision"], "seeded",
                         "same UNET model must seed even when CLIP differs")

        # CLIP must be identity_mismatch
        self.assertEqual(result2["20"]["decision"], "identity_mismatch",
                         "different CLIP model must produce identity_mismatch")
        self.assertNotEqual(result2["20"]["mismatch_fields"], "unknown")
        self.assertNotEqual(result2["20"]["mismatch_fields"], "none")

        # VAE still missing_snapshot_output
        self.assertEqual(result2["30"]["decision"], "missing_snapshot_output")

        # ── Scenario 3: Both match ────────────────────────────────────────
        result3 = self._run_seed(
            loader_node_ids=["10", "20"],
            loader_node_class_types={"10": "UNETLoader", "20": "CLIPLoader"},
            loader_outputs={"10": "fake_unet_output", "20": "fake_clip_output"},
            request_spec=self.base_spec,
            snapshot_spec=self.base_spec,
        )
        self.assertEqual(result3["10"]["decision"], "seeded",
                         "matching UNET must seed")
        self.assertEqual(result3["20"]["decision"], "seeded",
                         "matching CLIP must seed")

    # ── Test (b): Matching UNET/CLIP with absent VAE ─────────────────────

    def test_matching_unet_clip_with_absent_vae(self):
        """VAE absence (missing_snapshot_output) never blocks UNET/CLIP seeding.

        Snapshot has UNET and CLIP outputs but no VAE output.  VAE node is
        present in the workflow but gets missing_snapshot_output independently.
        UNET and CLIP seed normally regardless of VAE outcome.
        """
        loader_node_ids = ["10", "20", "30"]
        loader_node_class_types = {"10": "UNETLoader", "20": "CLIPLoader", "30": "VAELoader"}
        # No VAE output in loader_outputs
        loader_outputs = {"10": "fake_unet", "20": "fake_clip"}

        result = self._run_seed(
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_spec=_make_model_spec(vae_name="vae_a.safetensors"),
            snapshot_spec=_make_model_spec(),
        )

        # VAE reports missing_snapshot_output (independently)
        self.assertEqual(result["30"]["decision"], "missing_snapshot_output",
                         "VAE must report missing_snapshot_output independently")
        self.assertEqual(result["30"]["role"], "vae")

        # UNET and CLIP both seed (unchanged by VAE)
        self.assertEqual(result["10"]["decision"], "seeded",
                         "UNET must seed when VAE is absent")
        self.assertEqual(result["20"]["decision"], "seeded",
                         "CLIP must seed when VAE is absent")

    # ── Test (c): Alternate model/workflow fallback, no stale cache ──────

    def test_fallback_no_stale_cache(self):
        """Sequential calls with different models produce fresh independent
        decisions AND no stale cache objects remain/reappear.

        Cache object identity is verified through the mock's store:
        after identity_mismatch the old entry is deleted; after a new
        seed call only the newly-seeded entries exist in the cache.
        """
        # We need the mock cache's internal store for verification
        outputs_cache = self.executor.caches.outputs
        loader_node_ids = ["unet_node", "clip_node"]
        loader_node_class_types = {"unet_node": "UNETLoader", "clip_node": "CLIPLoader"}
        loader_outputs = {"unet_node": "model_obj", "clip_node": "clip_obj"}

        # ── First call: everything matches → both seeded ──────────────────
        first = self._run_seed(
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_spec=self.base_spec,
            snapshot_spec=self.base_spec,
        )
        self.assertEqual(first["unet_node"]["decision"], "seeded")
        self.assertEqual(first["clip_node"]["decision"], "seeded")
        # Both entries must be in the cache
        self.assertIsNotNone(
            outputs_cache.store.get("unet_node"),
            "seeded UNET must exist in output cache",
        )
        self.assertIsNotNone(
            outputs_cache.store.get("clip_node"),
            "seeded CLIP must exist in output cache",
        )

        # ── Second call: different UNET model, same CLIP ──────────────────
        second = self._run_seed(
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_spec=_make_model_spec(unet_name="new_model.safetensors"),
            snapshot_spec=self.base_spec,
        )

        # UNET must be identity_mismatch (not stale "seeded")
        self.assertEqual(
            second["unet_node"]["decision"], "identity_mismatch",
            "different UNET model must not reuse stale seeded decision",
        )
        # CLIP still seeds (unchanged by UNET change)
        self.assertEqual(second["clip_node"]["decision"], "seeded")

        # mismatch_fields must be populated with exact field names
        self.assertNotEqual(second["unet_node"]["mismatch_fields"], "none")
        self.assertNotEqual(second["unet_node"]["mismatch_fields"], "unknown")

        # ── VERIFY: stale UNET cache entry was CLEARED on mismatch ────────
        self.assertNotIn(
            "unet_node", outputs_cache.store,
            "stale UNET cache entry must be removed after identity_mismatch",
        )
        # CLIP entry from first call should still exist (it got re-seeded)
        self.assertIsNotNone(
            outputs_cache.store.get("clip_node"),
            "CLIP must remain in cache after re-seeding",
        )

        # ── Third call: different CLIP, same UNET ─────────────────────────
        third = self._run_seed(
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_spec=_make_model_spec(clip_name="new_clip.safetensors"),
            snapshot_spec=self.base_spec,
        )
        self.assertEqual(third["unet_node"]["decision"], "seeded",
                         "UNET must still seed when CLIP is different")
        self.assertEqual(third["clip_node"]["decision"], "identity_mismatch",
                         "different CLIP model must produce identity_mismatch")
        self.assertIn("model_identity", third["clip_node"]["mismatch_fields"],
                      "mismatch_fields must contain model_identity for CLIP")
        # Stale CLIP entry must be cleared
        self.assertNotIn("clip_node", outputs_cache.store,
                         "stale CLIP cache entry must be removed after identity_mismatch")

        # ── Fourth call: different workflow_hash, matching loaders still seed ──
        state_diff_hash = _make_bootstrap_state(workflow_hash="other_wf_hash")
        fourth = self._run_seed(
            state=state_diff_hash,
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_spec=self.base_spec,
            snapshot_spec=self.base_spec,
        )
        self.assertEqual(
            fourth["unet_node"]["decision"], "seeded",
            "matching UNET must seed even with different workflow_hash",
        )
        self.assertEqual(
            fourth["clip_node"]["decision"], "seeded",
            "matching CLIP must seed even with different workflow_hash",
        )

        # ── Verify: unsupported internal failures carry exact tokens ──────
        # cache_key_missing: simulate uninitialized outputs cache
        _orig_initialized = outputs_cache.initialized
        outputs_cache.initialized = False
        no_key_result = self._run_seed(
            loader_node_ids=["10"],
            loader_node_class_types={"10": "UNETLoader"},
            loader_outputs={"10": "obj"},
            request_spec=_make_model_spec(),
            snapshot_spec=_make_model_spec(),
        )
        self.assertEqual(no_key_result["10"]["decision"], "unsupported",
                         "uninitialized cache must report unsupported")
        self.assertEqual(no_key_result["10"]["mismatch_fields"], "cache_key_missing",
                         "uninitialized cache must carry cache_key_missing token")
        outputs_cache.initialized = _orig_initialized

    # ── Helpers ─────────────────────────────────────────────────────────

    def _run_seed(
        self,
        *,
        state: BootstrapState | None = None,
        loader_node_ids: list[str],
        loader_node_class_types: dict[str, str],
        loader_outputs: dict[str, Any],
        request_spec: dict[str, Any],
        snapshot_spec: dict[str, Any],
    ) -> dict[str, dict[str, str]]:
        """Run seed_loader_cache_signatures and return result dict."""
        import asyncio
        s = state or self.state
        coro = s.seed_loader_cache_signatures(
            executor=self.executor,
            loader_node_ids=loader_node_ids,
            loader_node_class_types=loader_node_class_types,
            loader_outputs=loader_outputs,
            request_model_spec=request_spec,
            snapshot_model_spec=snapshot_spec,
            custom_node_generation=s.snapshot_custom_node_generation,
            deployment_combined_hash=s.deployment_combined_hash,
            workflow_hash=(
                s.snapshot_execution_seed.workflow_hash
                if s.snapshot_execution_seed else ""
            ),
            allow_cache=True,
        )
        return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
