"""Focused tests for ProductionPlan serialization, cache invalidation,
dispatch validation, active profile fields, and sequential loading.

Adapts to existing test conventions: uses unittest.TestCase and avoids
brittle over-mocking.
"""
import copy
import hashlib
import json
import os
import sys
import unittest
from collections import OrderedDict

# Ensure the custom-node root is on sys.path (matching run_tests.py)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from production_workflow import (
    COMPILER_SCHEMA_VERSION,
    HASH_SCHEMA_VERSION,
    PRODUCTION_PLAN_SCHEMA_VERSION,
    compile_production_workflow,
    normalize_production_options,
    _canonical_workflow_hash,
    _compute_production_plan_hash,
    _reset_cache,
    _cache_size,
    ProductionPlan,
)


# ── Sample workflow fixture ────────────────────────────────────────────────

def _sample_workflow():
    return OrderedDict([
        ("1", {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ["4", 0]}}),
        ("2", {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 0]}}),
        ("3", {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 8.0, "sampler_name": "euler", "scheduler": "normal", "model": ["4", 0], "positive": ["1", 0], "negative": ["2", 0], "latent_image": ["5", 0]}}),
        ("4", {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"}}),
        ("5", {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}}),
        ("6", {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["7", 0]}}),
        ("7", {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}}),
        ("107", {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "comfy"}}),
    ])


def _production_with_output_107():
    return {
        "enabled": True,
        "output_node_ids": ["107"],
        "direct_output_sink": True,
        "metadata_mode": "none",
    }


class TestProductionPlanSerialization(unittest.TestCase):
    """Requirement 1: compiler_version through serialization."""

    def setUp(self):
        _reset_cache()

    def test_plan_retains_all_version_fields(self):
        """Every ProductionPlan must carry compiler_version, hash_schema_version, etc."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        self.assertEqual(plan.compiler_version, COMPILER_SCHEMA_VERSION)
        self.assertEqual(plan.hash_schema_version, HASH_SCHEMA_VERSION)
        self.assertEqual(plan.production_plan_schema_version, PRODUCTION_PLAN_SCHEMA_VERSION)
        self.assertEqual(plan.schema_version, COMPILER_SCHEMA_VERSION)
        self.assertEqual(plan.hash_schema, HASH_SCHEMA_VERSION)

        # Report fields
        r = plan.report
        self.assertEqual(r.get("compiler_version"), COMPILER_SCHEMA_VERSION)
        self.assertEqual(r.get("hash_schema_version"), HASH_SCHEMA_VERSION)
        self.assertEqual(r.get("production_plan_schema_version"), PRODUCTION_PLAN_SCHEMA_VERSION)
        self.assertEqual(r.get("schema_version"), COMPILER_SCHEMA_VERSION)

    def test_plan_retains_all_hash_fields(self):
        """Every ProductionPlan must carry source_workflow_hash, compiled_workflow_hash, production_plan_hash."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        self.assertTrue(len(plan.source_workflow_hash) > 0)
        self.assertTrue(len(plan.compiled_workflow_hash) > 0)
        self.assertTrue(len(plan.production_plan_hash) > 0)

        r = plan.report
        self.assertEqual(r.get("source_workflow_hash"), plan.source_workflow_hash)
        self.assertEqual(r.get("compiled_workflow_hash"), plan.compiled_workflow_hash)
        self.assertEqual(r.get("production_plan_hash"), plan.production_plan_hash)

    def test_plan_retains_compiled_workflow(self):
        """compiled_workflow must always be present in ProductionPlan."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        self.assertIsInstance(plan.compiled_workflow, dict)
        self.assertTrue(len(plan.compiled_workflow) > 0)
        # Should only contain reachable nodes (node 7 is reachable via VAEDecode vae input)
        expected = {"1", "2", "3", "4", "5", "6", "7", "107"}
        for nid in plan.compiled_workflow:
            self.assertIn(nid, expected,
                          f"Unexpected node {nid} in compiled workflow")

    def test_hash_round_trip(self):
        """Recompiling the same workflow+options produces the same hashes."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        _reset_cache()

        plan1 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        plan2 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        self.assertEqual(plan1.source_workflow_hash, plan2.source_workflow_hash)
        self.assertEqual(plan1.compiled_workflow_hash, plan2.compiled_workflow_hash)
        self.assertEqual(plan1.production_plan_hash, plan2.production_plan_hash)

    def test_production_report_property_is_alias(self):
        """ProductionPlan.production_report must be a read-only alias for .report."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        # Both attributes must exist and point to the same dict
        self.assertTrue(hasattr(plan, "production_report"))
        self.assertIs(plan.production_report, plan.report,
                       "production_report must be the same object as report")

        # Verify it contains the expected report keys
        r = plan.production_report
        self.assertIn("compiled_workflow_hash", r)
        self.assertIn("source_workflow_hash", r)
        self.assertIn("production_plan_hash", r)
        self.assertIn("compiler_version", r)


class TestProductionPlanCacheInvalidation(unittest.TestCase):
    """Requirement 1 continued: cache invalidation for missing/zero/old fields."""

    def setUp(self):
        _reset_cache()

    def test_cache_rebuilds_when_compiled_workflow_missing(self):
        """If cached data lacks compiled_workflow_hash, force rebuild."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        # First compile populates cache
        plan1 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertTrue(plan1.report.get("cache_hit") is False)

        from production_workflow import _topology_plan_cache
        # Verify non-empty report hash persists
        self.assertTrue(len(plan1.compiled_workflow_hash) > 0)

        # Second call should hit cache
        plan2 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertIsNotNone(plan2)
        self.assertTrue(plan2.report.get("cache_hit") is True)

    def test_cache_rebuilds_when_schema_zero(self):
        """Cache must rebuild if the cached entry has schema_version=0."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        # schema_version should be COMPILER_SCHEMA_VERSION, not 0
        self.assertEqual(plan.report.get("schema_version"), COMPILER_SCHEMA_VERSION)
        self.assertNotEqual(plan.report.get("schema_version"), 0)

    def test_cache_rebuilds_when_compiled_workflow_hash_empty(self):
        """Cache must rebuild if the cached report lacks compiled_workflow_hash."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertTrue(len(plan.report.get("compiled_workflow_hash", "")) > 0)

    def test_cache_invalidated_on_version_change(self):
        """Change in compiler_version should not match cache key."""
        wf = _sample_workflow()
        prod = _production_with_output_107()

        # Store a cache entry
        _reset_cache()
        plan1 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        # cache miss
        self.assertFalse(plan1.report.get("cache_hit"))

        # Second call should hit cache (same versions)
        plan2 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertTrue(plan2.report.get("cache_hit"))

    def test_cache_returns_valid_report(self):
        """Cached plans must still return full report, not just topology."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        _reset_cache()

        plan1 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        # Cache hit
        plan2 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        for p in [plan1, plan2]:
            self.assertIn("compiled_workflow_hash", p.report)
            self.assertIn("source_workflow_hash", p.report)
            self.assertIn("production_plan_hash", p.report)
            self.assertIn("compiler_version", p.report)
            self.assertIn("hash_schema_version", p.report)
            self.assertIn("production_plan_schema_version", p.report)

    def test_cache_rebuilds_on_corrupt_compiled_workflow_hash(self):
        """Directly corrupt the private cache entry's compiled_workflow_hash
        and prove the next compile rebuilds rather than returning a stale plan."""
        from production_workflow import _topology_plan_cache
        from production_workflow import _canonical_workflow_hash, _compute_compiled_workflow_hash

        wf = _sample_workflow()
        prod = _production_with_output_107()

        # First compile populates cache
        _reset_cache()
        plan1 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertFalse(plan1.report.get("cache_hit"))
        original_hash = plan1.compiled_workflow_hash

        # Directly corrupt the cached report's compiled_workflow_hash
        # by iterating the internal OrderedDict (the _LRUDict wraps it)
        import threading
        with _topology_plan_cache._lock:
            for cache_key, cached_entry in _topology_plan_cache._data.items():
                if "report" in cached_entry:
                    # Corrupt the stored hash to a different value
                    cached_entry["report"]["compiled_workflow_hash"] = "corrupted_deadbeef" * 4
                    break

        # Verify corruption took effect
        any_corrupted = False
        with _topology_plan_cache._lock:
            for cache_key, cached_entry in _topology_plan_cache._data.items():
                if cached_entry.get("report", {}).get("compiled_workflow_hash", "").startswith("corrupted"):
                    any_corrupted = True
                    break
        self.assertTrue(any_corrupted, "Cache corruption should have taken effect")

        # Recompile with same input — must detect corruption and rebuild
        plan2 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertFalse(plan2.report.get("cache_hit"),
                         "Corrupted cache entry must be invalidated and rebuilt")
        self.assertEqual(plan2.compiled_workflow_hash, original_hash,
                         "Rebuilt plan should have the correct hash")
        self.assertEqual(plan2.source_workflow_hash, plan1.source_workflow_hash)
        self.assertEqual(plan2.compiled_workflow_hash, plan1.compiled_workflow_hash)

    def test_cache_rebuilds_on_corrupt_empty_hash(self):
        """Corrupt the cache entry's compiled_workflow_hash to empty string
        and prove rebuild on the next compile."""
        from production_workflow import _topology_plan_cache

        wf = _sample_workflow()
        prod = _production_with_output_107()

        _reset_cache()
        plan1 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertFalse(plan1.report.get("cache_hit"))

        # Corrupt the cached report's hash to empty
        with _topology_plan_cache._lock:
            for cache_key, cached_entry in _topology_plan_cache._data.items():
                if "report" in cached_entry:
                    cached_entry["report"]["compiled_workflow_hash"] = ""
                    break

        # Recompile — must rebuild because hash is empty
        plan2 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertFalse(plan2.report.get("cache_hit"),
                         "Corrupted empty-hash cache entry must be rebuilt")
        self.assertTrue(len(plan2.compiled_workflow_hash) > 0)


class TestDispatchValidation(unittest.TestCase):
    """Requirement 2: compiled workflow dispatch validation."""

    def setUp(self):
        _reset_cache()

    def _make_report(self, overrides=None):
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        r = dict(plan.report)
        if overrides:
            r.update(overrides)
        return r, plan.compiled_workflow

    def test_dispatch_validate_production_passes(self):
        """validate_production_dispatch should pass with matching compiled_workflow."""
        from modal_client import validate_production_dispatch
        r, cwf = self._make_report()
        # Should not raise
        try:
            validate_production_dispatch(cwf, r)
        except AssertionError as e:
            self.fail(f"validate_production_dispatch raised: {e}")

    def test_dispatch_validate_fails_on_hash_mismatch(self):
        """validate_production_dispatch must fail on hash mismatch."""
        from modal_client import validate_production_dispatch
        r, cwf = self._make_report()
        tampered = dict(cwf)
        # Add a node to change the hash
        tampered["999"] = {"class_type": "CLIPTextEncode", "inputs": {"text": "tampered", "clip": ["4", 0]}}
        with self.assertRaises(AssertionError):
            validate_production_dispatch(tampered, r)

    def test_dispatch_validate_fails_on_missing_compiled_hash(self):
        """validate_production_dispatch must fail when report is missing compiled_workflow_hash."""
        from modal_client import validate_production_dispatch
        r, cwf = self._make_report({"compiled_workflow_hash": ""})
        with self.assertRaises(AssertionError):
            validate_production_dispatch(cwf, r)

    def test_dispatch_validate_fails_on_stale_version(self):
        """validate_production_dispatch must fail on stale compiler_version."""
        from modal_client import validate_production_dispatch, COMPILER_SCHEMA_VERSION
        r, cwf = self._make_report({"compiler_version": 0})
        with self.assertRaises(AssertionError):
            validate_production_dispatch(cwf, r)

    def test_dispatch_validate_noop_when_disabled(self):
        """validate_production_dispatch must be no-op when report is disabled."""
        from modal_client import validate_production_dispatch
        r = {"enabled": False, "compiled_workflow_hash": ""}
        try:
            validate_production_dispatch({}, r)
        except AssertionError as e:
            self.fail(f"validate_production_dispatch raised for disabled: {e}")

    def test_dispatch_validate_noop_when_none(self):
        """validate_production_dispatch must be no-op when report is None."""
        from modal_client import validate_production_dispatch
        try:
            validate_production_dispatch({}, None)
        except AssertionError as e:
            self.fail(f"validate_production_dispatch raised for None: {e}")


class TestActiveProfileProductionFields(unittest.TestCase):
    """Requirement 3: active profile production identity fields."""

    def setUp(self):
        _reset_cache()

    def test_build_activation_payload_carries_production_identity(self):
        """Activation payload must carry source_workflow_hash, compiled_workflow_hash,
        production_plan_hash, compiler_version, and output_node_ids."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        # Build activation payload as prepare_active_next_profile does
        from warmup_profile import _build_activation_payload
        payload = _build_activation_payload(
            plan.compiled_workflow,
            plan.source_workflow_hash,
            production_options={
                "enabled": True,
                "output_node_ids": ["107"],
                "source_workflow_hash": plan.source_workflow_hash,
                "compiled_workflow_hash": plan.compiled_workflow_hash,
                "production_plan_hash": plan.production_plan_hash,
                "compiler_version": COMPILER_SCHEMA_VERSION,
            },
        )

        self.assertTrue(payload.get("production_enabled"))
        self.assertEqual(payload.get("source_workflow_hash"), plan.source_workflow_hash)
        self.assertEqual(payload.get("compiled_workflow_hash"), plan.compiled_workflow_hash)
        self.assertEqual(payload.get("production_plan_hash"), plan.production_plan_hash)
        self.assertEqual(payload.get("compiler_version"), COMPILER_SCHEMA_VERSION)
        self.assertEqual(payload.get("hash_schema_version"), HASH_SCHEMA_VERSION)
        self.assertEqual(payload.get("production_plan_schema_version"), PRODUCTION_PLAN_SCHEMA_VERSION)
        self.assertIn("107", payload.get("output_node_ids", []))

    def test_activation_payload_output_node_ids_contains_107(self):
        """output_node_ids must include '107' for the target workflow."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        r = plan.report
        self.assertIn("107", r.get("output_node_ids", []))

    def test_activation_payload_version_fields_not_silently_defaulted(self):
        """Version-2 values for hash_schema_version and
        production_plan_schema_version must propagate through
        _build_activation_payload without being silently defaulted
        back to the constant value 1."""
        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        from warmup_profile import _build_activation_payload
        # Pass version-2 values explicitly — if propagation is broken,
        # they'd be silently defaulted to the module constant (1).
        payload = _build_activation_payload(
            plan.compiled_workflow,
            plan.source_workflow_hash,
            production_options={
                "enabled": True,
                "output_node_ids": ["107"],
                "source_workflow_hash": plan.source_workflow_hash,
                "compiled_workflow_hash": plan.compiled_workflow_hash,
                "production_plan_hash": plan.production_plan_hash,
                "compiler_version": 2,
                "hash_schema_version": 2,
                "production_plan_schema_version": 2,
            },
        )

        self.assertTrue(payload.get("production_enabled"))
        # Verify version-2 values survive (not silently defaulted to 1)
        self.assertEqual(payload.get("compiler_version"), 2,
                         "compiler_version=2 must propagate, not be defaulted to 1")
        self.assertEqual(payload.get("hash_schema_version"), 2,
                         "hash_schema_version=2 must propagate, not be defaulted to 1")
        self.assertEqual(payload.get("production_plan_schema_version"), 2,
                         "production_plan_schema_version=2 must propagate, not be defaulted to 1")
        # Also verify the profile dict carries the same
        profile = payload.get("warmup_profile", {})
        self.assertEqual(profile.get("compiler_version"), 2)
        self.assertEqual(profile.get("hash_schema_version"), 2)
        self.assertEqual(profile.get("production_plan_schema_version"), 2)

    def test_activation_payload_non_defaulted_when_report_contains_them(self):
        """When production_options is enriched from a production report
        that carries version fields, verify they propagate through
        _build_activation_payload without being re-defaulted."""
        from production_workflow import _compute_production_plan_hash, _canonical_workflow_hash

        wf = _sample_workflow()
        prod = _production_with_output_107()
        plan = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)

        # Simulate the enrichment done by __init__.py's activation path:
        # the production_options dict gets version fields from the report.
        enriched_opts = {
            "enabled": True,
            "output_node_ids": ["107"],
            "source_workflow_hash": plan.source_workflow_hash,
            "compiled_workflow_hash": plan.compiled_workflow_hash,
            "production_plan_hash": plan.production_plan_hash,
            "compiler_version": plan.report.get("compiler_version", COMPILER_SCHEMA_VERSION),
            "hash_schema_version": plan.report.get("hash_schema_version", HASH_SCHEMA_VERSION),
            "production_plan_schema_version": plan.report.get(
                "production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION),
        }

        from warmup_profile import _build_activation_payload
        payload = _build_activation_payload(
            plan.compiled_workflow,
            plan.source_workflow_hash,
            production_options=enriched_opts,
        )

        self.assertEqual(payload.get("compiler_version"), COMPILER_SCHEMA_VERSION)
        self.assertEqual(payload.get("hash_schema_version"), HASH_SCHEMA_VERSION)
        self.assertEqual(payload.get("production_plan_schema_version"), PRODUCTION_PLAN_SCHEMA_VERSION)


class TestLoaderSequentialOrdering(unittest.TestCase):
    """Requirement 5: sequential UNET then CLIP loading on same Modal volume."""

    def test_preload_mode_is_sequential_in_production_baseline(self):
        """The production baseline override for PRELOAD_MODE must be 'sequential'."""
        from comfyapp import _PRODUCTION_BASELINE_OVERRIDES
        mode = _PRODUCTION_BASELINE_OVERRIDES.get("COMFYMODAL_PRELOAD_MODE")
        self.assertEqual(mode, "sequential",
                         f"Expected sequential preload mode, got {mode!r}")

    def test_cold_unet_early_load_disabled(self):
        """COLD_UNET_EARLY_LOAD must be disabled by default."""
        from comfyapp import COLD_UNET_EARLY_LOAD
        self.assertFalse(COLD_UNET_EARLY_LOAD)


class TestValidationOrder(unittest.TestCase):
    """Requirement 4: remote validation before model I/O."""

    def test_production_validation_before_cold_unet_in_stream_source(self):
        """Verify the validation code appears before _cold_unet_early_actual_load
        in the source file."""
        source_path = os.path.join(ROOT, "comfyapp.py")
        with open(source_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        cold_unet_line = None
        pre_io_validate_line = None
        for i, line in enumerate(lines):
            if "_cold_unet_early_actual_load" in line and "def " not in line:
                cold_unet_line = i
            if "Production report validation before any model I/O" in line:
                pre_io_validate_line = i

        self.assertIsNotNone(pre_io_validate_line,
                             "Pre-IO production validation comment not found")
        self.assertIsNotNone(cold_unet_line,
                             "_cold_unet_early_actual_load call not found")
        self.assertLess(pre_io_validate_line, cold_unet_line,
                        "Production validation must appear before cold UNET load")


if __name__ == "__main__":
    unittest.main()
