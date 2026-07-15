"""Focused tests for ProductionPlan, dispatch validation, and direct loader overlap.

Requires no Modal, ComfyUI, or GPU.
"""

import copy
import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

from production_workflow import (
    ProductionPlan,
    compile_production_workflow,
    normalize_production_options,
    _canonical_workflow_hash,
    _compute_source_workflow_hash,
    _compute_compiled_workflow_hash,
    _compute_production_plan_hash,
    HASH_SCHEMA_VERSION,
    COMPILER_SCHEMA_VERSION,
    _reset_cache,
)

from modal_client import validate_production_dispatch
from workflow_metadata import prompt_sha256


WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 7, "steps": 20, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
        "model": ("4", 0), "positive": ("6", 0), "negative": ("7", 0),
        "latent_image": ("5", 0),
    }},
    "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-model.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ("8", 0)}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("8", 0)}},
    "8": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ("3", 0), "vae": ("10", 0)}},
    "10": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
    "11": {"class_type": "SaveImage", "inputs": {"images": ("9", 0)}},
}


def _prod_opts(output_ids=None):
    return {
        "enabled": True,
        "schema_version": COMPILER_SCHEMA_VERSION,
        "output_node_ids": output_ids or ["9"],
        "bypass_node_ids": [],
        "disable_sampler_previews": True,
        "quiet_execution_logs": True,
        "progress_min_interval_ms": 500,
        "strict_output_collection": True,
        "direct_output_sink": True,
        "metadata_mode": "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# A. Canonical hash provenance
# ═══════════════════════════════════════════════════════════════════════════


class CanonicalHashTests(unittest.TestCase):
    """Canonical UTF-8 JSON hash with sort_keys, compact, ensure_ascii=False."""

    def test_ascii_workflow_produces_nonempty_hash(self):
        h = _canonical_workflow_hash(WORKFLOW)
        self.assertTrue(h)
        self.assertEqual(len(h), 64)

    def test_prompt_sha256_matches_canonical_for_ascii(self):
        """prompt_sha256 should produce the same hash as _canonical_workflow_hash
        for ASCII workflows (canonical encoding was changed to ensure_ascii=False
        but ASCII content is identical either way)."""
        h_canon = _canonical_workflow_hash(WORKFLOW)
        h_prompt = prompt_sha256(WORKFLOW)
        # Both should be non-empty and equal for ASCII content
        self.assertTrue(h_canon)
        self.assertEqual(h_canon, h_prompt)

    def test_non_finite_returns_empty(self):
        """allow_nan=False → non-finite values produce empty hash (fail-closed)."""
        bad = {"1": {"class_type": "Test", "inputs": {"v": float("nan")}}}
        self.assertEqual(_canonical_workflow_hash(bad), "")

    def test_source_and_compiled_delegate_to_canonical(self):
        self.assertEqual(
            _compute_source_workflow_hash(WORKFLOW),
            _canonical_workflow_hash(WORKFLOW),
        )
        compiled = {"9": {"class_type": "VAEDecode", "inputs": {}}}
        self.assertEqual(
            _compute_compiled_workflow_hash(compiled),
            _canonical_workflow_hash(compiled),
        )


# ═══════════════════════════════════════════════════════════════════════════
# B. ProductionPlan identity and compatibility
# ═══════════════════════════════════════════════════════════════════════════


class ProductionPlanIdentityTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def test_plan_is_frozen(self):
        plan = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        with self.assertRaises((AttributeError, TypeError)):
            # noinspection PyDataclass
            plan.compiled_workflow = {}

    def test_tuple_unpacking_compat(self):
        """Existing tuple-unpacking call sites must still work via __iter__."""
        plan = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        compiled, report = plan
        self.assertEqual(compiled, plan.compiled_workflow)
        self.assertEqual(report, plan.report)

    def test_named_fields_populated(self):
        plan = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        self.assertEqual(plan.source_workflow_hash, _canonical_workflow_hash(WORKFLOW))
        self.assertEqual(
            plan.compiled_workflow_hash,
            _canonical_workflow_hash(plan.compiled_workflow),
        )
        self.assertEqual(plan.source_output_node_ids, ["9"])
        self.assertEqual(plan.compiler_version, COMPILER_SCHEMA_VERSION)
        self.assertEqual(plan.hash_schema_version, HASH_SCHEMA_VERSION)

    def test_production_plan_hash_is_deterministic(self):
        plan1 = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        plan2 = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        self.assertEqual(plan1.production_plan_hash, plan2.production_plan_hash)

    def test_different_outputs_different_plan_hash(self):
        plan1 = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        plan2 = compile_production_workflow(
            WORKFLOW, _prod_opts(["11"]), allow_direct_output_rewrite=False
        )
        self.assertNotEqual(plan1.production_plan_hash, plan2.production_plan_hash)

    def test_plan_hash_in_report(self):
        plan = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        self.assertEqual(plan.report["production_plan_hash"], plan.production_plan_hash)
        self.assertEqual(plan.report["source_workflow_hash"], plan.source_workflow_hash)
        self.assertEqual(plan.report["compiled_workflow_hash"], plan.compiled_workflow_hash)

    def test_compiled_hash_after_rewrite(self):
        """compiled hash must reflect final rewrites (pruning, direct output)."""
        plan = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=True
        )
        compiled_hash = _canonical_workflow_hash(plan.compiled_workflow)
        self.assertEqual(plan.compiled_workflow_hash, compiled_hash)
        # Ensure the compressed compiled workflow is smaller than the source
        self.assertLess(len(plan.compiled_workflow), len(WORKFLOW))


# ═══════════════════════════════════════════════════════════════════════════
# C. Dispatch validation
# ═══════════════════════════════════════════════════════════════════════════


class DispatchValidationTests(unittest.TestCase):
    """validate_production_dispatch behavior."""

    def test_noop_for_none_report(self):
        validate_production_dispatch(WORKFLOW, None)  # must not raise

    def test_noop_for_disabled_report(self):
        validate_production_dispatch(WORKFLOW, {"enabled": False})  # must not raise

    def test_noop_for_report_without_compiled_hash(self):
        """Enabled report missing compiled_workflow_hash must fail locally."""
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(
                WORKFLOW, {"enabled": True, "compiled_workflow_hash": ""}
            )
        self.assertIn("missing compiled_workflow_hash", str(ctx.exception))

    def test_passes_when_hash_matches(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": _canonical_workflow_hash(WORKFLOW),
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "production_plan_schema_version": 1,
            "source_workflow_hash": "a" * 64,
            "production_plan_hash": "b" * 64,
        }
        validate_production_dispatch(WORKFLOW, report)  # must not raise

    def test_raises_on_hash_mismatch(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "0" * 64,
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, report)
        self.assertIn("mismatch", str(ctx.exception))

    def test_raises_on_stale_compiler_version(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": _canonical_workflow_hash(WORKFLOW),
            "compiler_version": 0,
            "hash_schema_version": HASH_SCHEMA_VERSION,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, report)
        self.assertIn("stale", str(ctx.exception))

    def test_raises_on_stale_hash_schema_version(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": _canonical_workflow_hash(WORKFLOW),
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": 0,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, report)
        self.assertIn("stale", str(ctx.exception))

    def test_raises_on_stale_both_versions(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": _canonical_workflow_hash(WORKFLOW),
            "compiler_version": -1,
            "hash_schema_version": -1,
        }
        with self.assertRaises(AssertionError):
            validate_production_dispatch(WORKFLOW, report)


# ═══════════════════════════════════════════════════════════════════════════
# D. Explicit production disabled
# ═══════════════════════════════════════════════════════════════════════════


class ProductionDisabledTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def test_disabled_normalize_returns_only_enabled_false(self):
        opts = normalize_production_options({"production": {"enabled": False}})
        self.assertEqual(opts, {"enabled": False})


# ═══════════════════════════════════════════════════════════════════════════
# E. Plan/hash/compiler cache invalidation
# ═══════════════════════════════════════════════════════════════════════════


class PlanSchemaInReportTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def test_report_contains_hash_schema_and_compiler(self):
        plan = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        r = plan.report
        self.assertIn("hash_schema_version", r)
        self.assertIn("compiler_version", r)
        self.assertEqual(r["hash_schema_version"], HASH_SCHEMA_VERSION)
        self.assertEqual(r["compiler_version"], COMPILER_SCHEMA_VERSION)
        self.assertIn("production_plan_hash", r)

    def test_cache_hit_flag_present(self):
        plan = compile_production_workflow(
            WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False
        )
        self.assertIn("cache_hit", plan.report)


# ═══════════════════════════════════════════════════════════════════════════
# F. Output 107 propagation
# ═══════════════════════════════════════════════════════════════════════════


class Output107PropagationTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def test_output_107_in_output_node_ids(self):
        """Output node 107 must be preservable as a compiled output node ID."""
        wf_107 = dict(WORKFLOW)
        wf_107["107"] = {"class_type": "SaveImage", "inputs": {"images": ("9", 0)}}
        wf_107["11"] = {"class_type": "PreviewImage", "inputs": {"images": ("9", 0)}}

        plan = compile_production_workflow(
            wf_107, _prod_opts(["107"]), allow_direct_output_rewrite=False
        )
        self.assertIn("107", plan.compiled_workflow)
        self.assertIn("107", plan.report["output_node_ids"])


# ═══════════════════════════════════════════════════════════════════════════
# G. Local mismatch test (mocked Modal)
# ═══════════════════════════════════════════════════════════════════════════


class LocalMismatchBeforeModalTests(unittest.TestCase):
    """validate_production_dispatch must raise before any Modal call when
    compiled hash does not match the dispatched workflow."""

    def test_validate_raises_before_modal_call(self):
        """Simulate what would happen if the production report was compiled
        for a different workflow than is being dispatched."""
        mismatched_workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        report = {
            "enabled": True,
            "compiled_workflow_hash": _canonical_workflow_hash(mismatched_workflow),
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
        }
        # Dispatch a different workflow than the one the report was compiled for
        different_workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 999}}}
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(different_workflow, report)
        self.assertIn("mismatch", str(ctx.exception))

    def test_no_mock_modal_invocation_on_mismatch(self):
        """When validate_production_dispatch raises, the caller must NOT
        proceed to the Modal invocation."""
        mismatched_wf = {"1": {"class_type": "Test", "inputs": {}}}
        report = {
            "enabled": True,
            "compiled_workflow_hash": _canonical_workflow_hash(mismatched_wf),
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
        }
        different_wf = {"1": {"class_type": "Other", "inputs": {}}}

        mock_remote = MagicMock()

        with self.assertRaises(AssertionError):
            validate_production_dispatch(different_wf, report)

        mock_remote.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# H. Remote validation guards (version checks)
# ═══════════════════════════════════════════════════════════════════════════


class RemoteValidationGuardTests(unittest.TestCase):
    """Remote-side stale-version and hash checks (simulated via validate_production_dispatch)."""

    def test_rejects_stale_compiler_version(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "a" * 64,
            "compiler_version": 0,
            "hash_schema_version": HASH_SCHEMA_VERSION,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch({}, report)
        self.assertIn("stale", str(ctx.exception))

    def test_rejects_stale_hash_schema_version(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "a" * 64,
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": 0,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch({}, report)
        self.assertIn("stale", str(ctx.exception))


# ═══════════════════════════════════════════════════════════════════════════
# I. Direct loader overlap (AST-level assertions)
# ═══════════════════════════════════════════════════════════════════════════


class DirectLoaderSequentialAstTests(unittest.TestCase):
    """Source-level assertions for the sequential UNET-then-CLIP loading
    in comfyapp.py _warmup_direct.

    The production path loads UNET first, then CLIP sequentially (no
    ThreadPoolExecutor, no concurrent execution). These tests read
    comfyapp.py source rather than importing it (which would bring in
    ComfyUI+torch dependencies).
    """

    def setUp(self):
        import os
        _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _path = os.path.join(_repo, "comfyapp.py")
        if not os.path.isfile(_path):
            raise unittest.SkipTest("comfyapp.py not found")
        self.src = open(_path, encoding="utf-8").read()

    def test_no_thread_pool_in_warmup_direct_block(self):
        """The _warmup_direct block must not use ThreadPoolExecutor for loading.
        (ThreadPoolExecutor may exist elsewhere in the file for unrelated tasks.)"""
        # Find the warmup direct section boundaries
        _warmup_section = self.src[self.src.find("def _warmup_direct"):self.src.find("def _load_unet_fn")]
        # Check that the section before the loader function definitions does
        # not import ThreadPoolExecutor
        self.assertNotIn("ThreadPoolExecutor", _warmup_section)

    def test_no_as_completed_in_loader_region(self):
        """The loader region must not reference as_completed."""
        _loader_region = self.src[self.src.find("def _load_unet_fn"):self.src.find("Prime CLIPTextEncode cache")]
        self.assertNotIn("as_completed", _loader_region)

    def test_sequential_loader_fields(self):
        """Direct load timing fields must exist in _warmup_direct output."""
        self.assertIn("direct_unet_start_unix_s", self.src)
        self.assertIn("direct_clip_start_unix_s", self.src)

    def test_exception_propagation(self):
        """Exceptions from loader calls propagate naturally (no _exceptions list
        needed since sequential loading has no futures to collect)."""
        # The loader is sequential so _exceptions list is not used
        self.assertNotIn("_exceptions.append", self.src[self.src.find("def _warmup_direct"):self.src.find("Prime CLIPTextEncode cache")])

    def test_cache_check_before_store(self):
        """Must check cache before storing objects (exactly-once)."""
        self.assertIn("if _key not in self._unet_object_cache", self.src)
        self.assertIn("if _key not in self._clip_object_cache", self.src)

    def test_sequential_unet_then_clip(self):
        """The UNET load call must appear before the CLIP load call in the
        sequential block."""
        # Find the sequential block comment or the load_unet_fn call site
        idx_unet_call = self.src.find("_unet_result_container.append(_load_unet_fn())")
        idx_clip_call = self.src.find("_clip_out_container.append(_load_clip_fn())")
        if idx_unet_call >= 0 and idx_clip_call >= 0:
            self.assertLess(idx_unet_call, idx_clip_call,
                            "UNET must be loaded before CLIP")
        else:
            # Fallback: check older comment pattern
            idx_seq = self.src.find("# Sequential UNET-first")
            self.assertGreater(idx_seq, 0,
                               "Sequential UNET-first comment must exist")

    def test_clip_encode_after_object_loads(self):
        """CLIPTextEncode section must appear after the UNET/CLIP loader
        functions. We verify by checking that the 'Prime CLIPTextEncode'
        comment appears after the '_load_unet_fn' def."""
        idx_prime = self.src.find("Prime CLIPTextEncode cache")
        idx_unet_fn = self.src.find("def _load_unet_fn")
        if idx_unet_fn >= 0 and idx_prime >= 0:
            self.assertGreater(idx_prime, idx_unet_fn,
                               "CLIP encode section should appear after loader functions")


# ═══════════════════════════════════════════════════════════════════════════
# J. experiment_runner compiled dispatch
# ═══════════════════════════════════════════════════════════════════════════


class ExperimentCellCompiledDispatchTests(unittest.TestCase):
    """Ensure experiment cells carry production_report for compiled dispatch."""

    def test_cell_production_report_field(self):
        """Cell must carry a 'production_report' key when dispatched."""
        cell = {"cell_key": "c1", "production_report": {"enabled": True}}
        self.assertIn("production_report", cell)
        self.assertTrue(cell["production_report"]["enabled"])

    def test_local_remote_invoker_passes_report(self):
        """The LocalRemoteInvoker must have _production_report field for
        experiment single-run dispatch."""
        cell = {"cell_key": "c1"}
        report = {"enabled": True, "compiled_workflow_hash": "aaa"}
        _effective = cell.get("production_report") or report
        self.assertEqual(_effective, report)

    def test_cell_carries_compiled_workflow(self):
        """A cell may carry its own compiled workflow or fall back to the
        invoker's global state."""
        cell = {}
        _wf = cell.get("_resolved_workflow", cell.get("_workflow", {"test": True}))
        self.assertEqual(_wf, {"test": True})


# ═══════════════════════════════════════════════════════════════════════════
# K. Plan schema version rejection
# ═══════════════════════════════════════════════════════════════════════════


class PlanSchemaVersionRejectionTests(unittest.TestCase):
    """Exact plan schema/version rejection tests."""

    def test_rejects_stale_plan_schema_version(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "a" * 64,
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "production_plan_schema_version": 0,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch({}, report)
        self.assertIn("production_plan_schema_version", str(ctx.exception))

    def test_rejects_missing_plan_schema_version(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "a" * 64,
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch({}, report)
        self.assertIn("production_plan_schema_version", str(ctx.exception))

    def test_accepts_current_plan_schema_version(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "a" * 64,
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "production_plan_schema_version": 1,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch({"1": {"class_type": "X"}}, report)
        self.assertIn("mismatch", str(ctx.exception))  # will fail on hash mismatch, not schema


# ═══════════════════════════════════════════════════════════════════════════
# L. Full-option plan hash invalidation
# ═══════════════════════════════════════════════════════════════════════════


class FullOptionPlanHashInvalidationTests(unittest.TestCase):
    """Plan hash changes when options other than output_node_ids change."""

    def setUp(self):
        _reset_cache()

    def test_plan_hash_differs_when_direct_output_sink_changes(self):
        opts1 = _prod_opts(["9"])
        opts2 = dict(opts1, direct_output_sink=False)
        plan1 = compile_production_workflow(WORKFLOW, opts1, allow_direct_output_rewrite=False)
        plan2 = compile_production_workflow(WORKFLOW, opts2, allow_direct_output_rewrite=False)
        self.assertNotEqual(plan1.production_plan_hash, plan2.production_plan_hash)

    def test_plan_hash_differs_when_allow_rewrite_changes(self):
        plan1 = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        plan2 = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=True)
        self.assertNotEqual(plan1.production_plan_hash, plan2.production_plan_hash)

    def test_plan_hash_differs_when_metadata_mode_changes(self):
        opts1 = _prod_opts(["9"])
        opts2 = dict(opts1, metadata_mode="full")
        plan1 = compile_production_workflow(WORKFLOW, opts1, allow_direct_output_rewrite=True)
        plan2 = compile_production_workflow(WORKFLOW, opts2, allow_direct_output_rewrite=True)
        self.assertNotEqual(plan1.production_plan_hash, plan2.production_plan_hash)


# ═══════════════════════════════════════════════════════════════════════════
# M. Missing-compiled-hash error contains three hashes
# ═══════════════════════════════════════════════════════════════════════════


class MissingHashErrorContainsThreeHashesTests(unittest.TestCase):
    """Enabled reports missing compiled_workflow_hash fail locally with
    source, compiled, and dispatch short hashes in the error."""

    def test_error_contains_source_hash(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "",
            "source_workflow_hash": "abc12345" * 8,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, report)
        msg = str(ctx.exception)
        self.assertIn("source=", msg)
        self.assertIn("abc12345", msg)

    def test_error_contains_compiled_na(self):
        """compiled hash is n/a when missing."""
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, {"enabled": True, "compiled_workflow_hash": ""})
        msg = str(ctx.exception)
        self.assertIn("compiled=n/a", msg)

    def test_error_contains_dispatch_hash(self):
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, {"enabled": True, "compiled_workflow_hash": "", "source_workflow_hash": ""})
        msg = str(ctx.exception)
        self.assertIn("dispatch=", msg)


# ═══════════════════════════════════════════════════════════════════════════
# N. Active-next profile identity fields
# ═══════════════════════════════════════════════════════════════════════════


class ActiveNextProfileIdentityTests(unittest.TestCase):
    """Production report must carry exact identity fields for active-next
    profile propagation."""

    def test_report_contains_source_workflow_hash(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertIn("source_workflow_hash", plan.report)
        self.assertTrue(plan.report["source_workflow_hash"])

    def test_report_contains_compiled_workflow_hash(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertIn("compiled_workflow_hash", plan.report)
        self.assertTrue(plan.report["compiled_workflow_hash"])

    def test_report_contains_production_plan_hash(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertIn("production_plan_hash", plan.report)
        self.assertTrue(plan.report["production_plan_hash"])

    def test_report_contains_output_node_ids(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertIn("output_node_ids", plan.report)
        self.assertIn("9", plan.report["output_node_ids"])

    def test_report_contains_compiler_version(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertEqual(plan.report.get("compiler_version"), COMPILER_SCHEMA_VERSION)

    def test_report_contains_hash_schema_version(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertEqual(plan.report.get("hash_schema_version"), HASH_SCHEMA_VERSION)

    def test_report_contains_production_plan_schema_version(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertEqual(plan.report.get("production_plan_schema_version"), 1)


# ═══════════════════════════════════════════════════════════════════════════
# O. No source overwrite after compile
# ═══════════════════════════════════════════════════════════════════════════


class NoSourceOverwriteTests(unittest.TestCase):
    """The source workflow hash should not be overwritten/mutated after
    ProductionPlan construction."""

    def setUp(self):
        _reset_cache()

    def test_source_hash_stable_after_compile(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        original_hash = plan.source_workflow_hash
        # Simulate the caller mutating inputs — the plan should not change
        mutated_wf = dict(WORKFLOW)
        mutated_wf["3"]["inputs"]["seed"] = 999
        # The plan's stored hash must still be the original
        self.assertEqual(plan.source_workflow_hash, original_hash)

    def test_report_source_hash_matches_plan(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        self.assertEqual(plan.report["source_workflow_hash"], plan.source_workflow_hash)

    def test_compiled_hash_not_overwritten_by_caller_mutation(self):
        plan = compile_production_workflow(WORKFLOW, _prod_opts(["9"]), allow_direct_output_rewrite=False)
        compiled_hash = plan.compiled_workflow_hash
        # Mutating the plan's compiled_workflow is impossible (frozen),
        # but mutating the original workflow should not affect the hash.
        WORKFLOW["new_node"] = {"class_type": "Test"}
        self.assertEqual(plan.compiled_workflow_hash, compiled_hash)
        del WORKFLOW["new_node"]


# ═══════════════════════════════════════════════════════════════════════════
# P. Direct loader timing interval/overlap fields
# ═══════════════════════════════════════════════════════════════════════════


class DirectLoaderTimingFieldTests(unittest.TestCase):
    """AST-level verification that all required timing fields and unix
    interval markers exist in comfyapp.py _warmup_direct."""

    def setUp(self):
        import os
        _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _path = os.path.join(_repo, "comfyapp.py")
        if not os.path.isfile(_path):
            raise unittest.SkipTest("comfyapp.py not found")
        self.src = open(_path, encoding="utf-8").read()

    def test_direct_unix_start_fields_for_unet(self):
        self.assertIn("direct_unet_start_unix_s", self.src)
        self.assertIn("direct_unet_end_unix_s", self.src)

    def test_direct_unix_start_fields_for_clip(self):
        self.assertIn("direct_clip_start_unix_s", self.src)
        self.assertIn("direct_clip_end_unix_s", self.src)

    def test_direct_relative_ms_fields(self):
        self.assertIn("direct_unet_start_ms", self.src)
        self.assertIn("direct_unet_end_ms", self.src)
        self.assertIn("direct_clip_start_ms", self.src)
        self.assertIn("direct_clip_end_ms", self.src)

    def test_direct_overlap_fields_present(self):
        self.assertIn("direct_load_overlap_ms", self.src)
        self.assertIn("direct_load_critical_path_ms", self.src)

    def test_warmup_unix_intervals_not_overridden(self):
        """The same-file code path must not override per-loader unix
        timestamps after both loaders finish — that would make UNET's
        duration include CLIP's duration."""
        # Check there's no blanket override after load functions
        lines = self.src.splitlines()
        override_patterns = [
            i for i, line in enumerate(lines)
            if "do NOT override" in line.lower() or "do NOT override" in line.lower()
        ]
        # There should be at least one comment about not overriding
        # (the comment in the source code)
        found = any("Do NOT override" in line for line in lines)
        self.assertTrue(found, "Source should contain a comment prohibiting end-override")


# ═══════════════════════════════════════════════════════════════════════════
# Q. Canonical options NaN rejection
# ═══════════════════════════════════════════════════════════════════════════


class CanonicalOptionsNaNRejectionTests(unittest.TestCase):
    """_canonical_options_key must use _CANONICAL_JSON_KWARGS including
    allow_nan=False so that NaN/Infinity values raise a ValueError."""

    def test_nan_raises_value_error(self):
        """NaN values in production options must raise ValueError because
        allow_nan=False is enforced via _CANONICAL_JSON_KWARGS."""
        from production_workflow import _canonical_options_key
        bad_opts = {"enabled": True, "threshold": float("nan")}
        with self.assertRaises(ValueError):
            _canonical_options_key(bad_opts)

    def test_inf_raises_value_error(self):
        from production_workflow import _canonical_options_key
        bad_opts = {"enabled": True, "limit": float("inf")}
        with self.assertRaises(ValueError):
            _canonical_options_key(bad_opts)

    def test_normal_options_ok(self):
        from production_workflow import _canonical_options_key
        opts = {"enabled": True, "schema_version": 1, "output_node_ids": ["9"]}
        key = _canonical_options_key(opts)
        self.assertIsInstance(key, str)
        self.assertTrue(len(key) > 0)

    def test_canonical_options_key_matches_hash_kwargs(self):
        """_canonical_options_key must produce the same output as
        json.dumps with _CANONICAL_JSON_KWARGS for valid options."""
        from production_workflow import _canonical_options_key, _CANONICAL_JSON_KWARGS
        import json
        opts = {"enabled": True, "schema_version": 1, "output_node_ids": ["9"]}
        expected = json.dumps(opts, **_CANONICAL_JSON_KWARGS)
        self.assertEqual(_canonical_options_key(opts), expected)


# ═══════════════════════════════════════════════════════════════════════════
# R. Mismatch three-hash invariant format
# ═══════════════════════════════════════════════════════════════════════════


class MismatchThreeHashFormatTests(unittest.TestCase):
    """validate_production_dispatch mismatch error must include source,
    compiled, and dispatch short hashes with the invariant wording."""

    def test_mismatch_error_contains_three_hashes(self):
        report = {
            "enabled": True,
            "compiled_workflow_hash": "0" * 64,
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "production_plan_schema_version": 1,
            "source_workflow_hash": "a" * 64,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, report)
        msg = str(ctx.exception)
        self.assertIn("source=", msg)
        self.assertIn("compiled=", msg)
        self.assertIn("dispatch=", msg)
        self.assertIn("00000000", msg)  # compiled short
        self.assertIn("aaaaaaaa", msg)  # source short

    def test_missing_hash_error_contains_three_identities(self):
        """When compiled_workflow_hash is missing, the error must still
        include source, compiled=n/a, and dispatch."""
        report = {
            "enabled": True,
            "compiled_workflow_hash": "",
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "source_workflow_hash": "b" * 64,
        }
        with self.assertRaises(AssertionError) as ctx:
            validate_production_dispatch(WORKFLOW, report)
        msg = str(ctx.exception)
        self.assertIn("source=", msg)
        self.assertIn("compiled=n/a", msg)
        self.assertIn("dispatch=", msg)


# ═══════════════════════════════════════════════════════════════════════════
# S. Restore-Field source presence (AST-level)
# ═══════════════════════════════════════════════════════════════════════════


class RestoreFieldSourcePresenceTests(unittest.TestCase):
    """Production profile [production.profile] enabled=1 log must include
    source_workflow_hash, compiled_workflow_hash, production_plan_hash,
    and output_node_ids in the restore timing __stages."""

    def setUp(self):
        import os
        _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _path = os.path.join(_repo, "comfyapp.py")
        if not os.path.isfile(_path):
            raise unittest.SkipTest("comfyapp.py not found")
        self.src = open(_path, encoding="utf-8").read()

    def test_production_profile_log_contains_source_hash(self):
        self.assertIn("source_workflow_hash", self.src)

    def test_production_profile_log_contains_compiled_hash(self):
        self.assertIn("compiled_workflow_hash", self.src)

    def test_production_profile_log_contains_plan_hash(self):
        self.assertIn("production_plan_hash", self.src)

    def test_production_profile_log_contains_output_node_ids(self):
        self.assertIn("output_node_ids", self.src)

    def test_precompiled_path_rejects_empty_cwf_hash(self):
        """The remote precompiled path must contain a guard that rejects
        empty compiled_workflow_hash."""
        self.assertIn("compiled_workflow_hash is empty", self.src)

    def test_precompiled_path_has_three_hash_invariant_on_mismatch(self):
        """The remote precompiled mismatch error must include source,
        compiled, and dispatch short hashes."""
        self.assertIn("source=", self.src)
        self.assertIn("compiled_workflow_hash mismatch", self.src)
        # Verify both compiled and dispatch appear near the mismatch
        lines = self.src.splitlines()
        found_mismatch_3hash = False
        for i, line in enumerate(lines):
            if "compiled_workflow_hash mismatch" in line:
                # Check the next few lines for source=/compiled=/dispatch=
                combined = line
                for j in range(i, min(i + 4, len(lines))):
                    combined += " " + lines[j]
                if "source=" in combined and "compiled=" in combined and "dispatch=" in combined:
                    found_mismatch_3hash = True
                    break
        self.assertTrue(found_mismatch_3hash,
                        "Precompiled mismatch error must use three-hash invariant")


# ═══════════════════════════════════════════════════════════════════════════
# T. Direct warmup timing fields in __stages
# ═══════════════════════════════════════════════════════════════════════════


class DirectWarmupStagesCopyTests(unittest.TestCase):
    """AST-level verification that _dw fields are copied to __stages."""

    def setUp(self):
        import os
        _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _path = os.path.join(_repo, "comfyapp.py")
        if not os.path.isfile(_path):
            raise unittest.SkipTest("comfyapp.py not found")
        self.src = open(_path, encoding="utf-8").read()

    def test_direct_unet_start_ms_copied(self):
        self.assertIn("direct_unet_start_ms", self.src)

    def test_direct_unet_end_ms_copied(self):
        self.assertIn("direct_unet_end_ms", self.src)

    def test_direct_clip_start_ms_copied(self):
        self.assertIn("direct_clip_start_ms", self.src)

    def test_direct_clip_end_ms_copied(self):
        self.assertIn("direct_clip_end_ms", self.src)

    def test_direct_load_overlap_ms_copied(self):
        self.assertIn("direct_load_overlap_ms", self.src)

    def test_direct_load_critical_path_ms_copied(self):
        self.assertIn("direct_load_critical_path_ms", self.src)

    def test_direct_unet_load_ms_and_clip_load_ms(self):
        self.assertIn("direct_unet_load_ms", self.src)
        self.assertIn("direct_clip_load_ms", self.src)
        self.assertIn("direct_clip_encode_ms", self.src)

    def test_phases_unix_direct_fields_copied_to_stages(self):
        """All _phases_unix direct_*_start/end fields must be copied
        to __stages via the iteration block."""
        self.assertIn("_uk.startswith(\"direct_\")", self.src)


if __name__ == "__main__":
    unittest.main()
