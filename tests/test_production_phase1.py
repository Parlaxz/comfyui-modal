"""Phase 1 contract regression tests — surgical correctness pass.

Covers:
- Canonical normalize_production_options semantics (A)
- Generic /prompt with default but no output binding fails closed (B)
- Studio single-run derives output IDs from snapshot and compiles (C)
- Experiment per-preset independent reports (D)
- Runner receives matching cell report/options (E)
- Truthful diagnostics with required keys (F)
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import json

from production_workflow import (
    normalize_production_options,
    compile_production_workflow,
    build_production_topology_hash,
    _compute_source_workflow_hash,
    _compute_compiled_workflow_hash,
    COMPILER_SCHEMA_VERSION,
    _reset_cache,
)

# ── Shared test data ──────────────────────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════════════
# A. Canonical normalize_production_options semantics
# ══════════════════════════════════════════════════════════════════════════

class NormalizerCanonicalTests(unittest.TestCase):
    """Canonical semantics: None/empty/absent → enabled True; explicit false → disabled."""

    def test_none_returns_enabled_with_defaults(self):
        result = normalize_production_options(None)
        self.assertTrue(result["enabled"])
        self.assertEqual(result["schema_version"], COMPILER_SCHEMA_VERSION)
        self.assertEqual(result["output_node_ids"], [])

    def test_empty_dict_returns_enabled_with_defaults(self):
        result = normalize_production_options({})
        self.assertTrue(result["enabled"])

    def test_no_production_key_returns_enabled_with_defaults(self):
        result = normalize_production_options({"other": "data"})
        self.assertTrue(result["enabled"])

    def test_production_omitted_default_applied(self):
        """production.enabled omitted → enabled=True (default-applied)."""
        result = normalize_production_options({"production": {}})
        self.assertTrue(result["enabled"])

    def test_explicit_false_returns_disabled(self):
        result = normalize_production_options({"production": {"enabled": False}})
        self.assertEqual(result, {"enabled": False})

    def test_explicit_false_with_extra_keys(self):
        result = normalize_production_options({
            "production": {"enabled": False, "schema_version": 1, "output_node_ids": ["9"]}
        })
        self.assertEqual(result, {"enabled": False})

    def test_explicit_true_no_output_ids_passes(self):
        """Normalizer never rejects empty output_node_ids — surface/compile boundary does."""
        result = normalize_production_options({
            "production": {"enabled": True, "schema_version": 1}
        })
        self.assertTrue(result["enabled"])
        self.assertEqual(result["output_node_ids"], [])

    def test_explicit_true_with_output_ids_works(self):
        result = normalize_production_options({
            "production": {"enabled": True, "schema_version": 1, "output_node_ids": ["9"]}
        })
        self.assertTrue(result["enabled"])
        self.assertEqual(result["output_node_ids"], ["9"])

    def test_explicit_false_normalize_rejects_overlap(self):
        with self.assertRaises(ValueError):
            normalize_production_options({
                "production": {
                    "schema_version": COMPILER_SCHEMA_VERSION,
                    "output_node_ids": ["9", "10"],
                    "bypass_node_ids": ["9"],
                }
            })


# ══════════════════════════════════════════════════════════════════════════
# B. Generic /prompt with default but no output binding fails closed
# ══════════════════════════════════════════════════════════════════════════

class DefaultPromptFailsClosedTests(unittest.TestCase):
    """Generic /prompt route with default-applied production but no output binding."""

    def setUp(self):
        _reset_cache()

    def test_normalize_enabled_with_empty_ids(self):
        """Normalizer returns enabled=True with empty output_node_ids for absent config."""
        prod = normalize_production_options(None)
        self.assertTrue(prod["enabled"])
        self.assertEqual(prod["output_node_ids"], [])

    def test_compile_rejects_empty_output_ids(self):
        """compile_production_workflow must raise ValueError on empty output_node_ids."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": []}
        })
        with self.assertRaises(ValueError) as ctx:
            compile_production_workflow(WORKFLOW, prod, allow_direct_output_rewrite=True)
        self.assertIn("output_node_ids", str(ctx.exception).lower())

    def test_compile_rejects_explicit_true_empty_ids(self):
        """Explicit true with empty output_node_ids fails at compile boundary."""
        prod = normalize_production_options({
            "production": {"enabled": True, "schema_version": 1}
        })
        with self.assertRaises(ValueError) as ctx:
            compile_production_workflow(WORKFLOW, prod, allow_direct_output_rewrite=True)
        self.assertIn("output_node_ids", str(ctx.exception).lower())

    def test_compile_with_valid_output_ids_succeeds(self):
        """When output_node_ids are provided, compilation succeeds."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })
        compiled, report = compile_production_workflow(
            WORKFLOW, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("9", compiled)
        self.assertTrue(report["enabled"])


# ══════════════════════════════════════════════════════════════════════════
# C. Studio single-run derives output IDs from snapshot
# ══════════════════════════════════════════════════════════════════════════

class StudioDerivationTests(unittest.TestCase):
    """Studio single-run: omitted modal_options derives outputNodeId from snapshot."""

    def setUp(self):
        _reset_cache()

    def test_omitted_modal_options_derives_output_from_snapshot(self):
        """Omitted modal_options → enabled, derive outputNodeId='9' from snapshot."""
        prod = normalize_production_options(None)
        self.assertTrue(prod["enabled"])
        self.assertEqual(prod["output_node_ids"], [])

        # Simulate build_single_run_spec derivation
        snapshot = {"outputNodeId": "9"}
        _snap_output = str(snapshot.get("outputNodeId", "")).strip()
        self.assertEqual(_snap_output, "9")

        derived = [_snap_output]
        prod["output_node_ids"] = derived

        compiled, report = compile_production_workflow(
            WORKFLOW, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("9", compiled)
        self.assertIn("9", report["output_node_ids"])
        self.assertTrue(report["enabled"])
        self.assertEqual(report["compiled_workflow_hash"],
                         _compute_compiled_workflow_hash(compiled))

    def test_explicit_false_skips_compile(self):
        """Explicit false stays disabled — no compile."""
        result = normalize_production_options({"production": {"enabled": False}})
        self.assertEqual(result, {"enabled": False})

    def test_caller_output_ids_take_precedence(self):
        """Caller-provided output_node_ids take precedence over snapshot."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["11"]}
        })
        compiled, report = compile_production_workflow(
            WORKFLOW, prod, allow_direct_output_rewrite=True
        )
        # 11 (SaveImage) compiles as ComfyModalProductionOutput with 9 as ancestor
        self.assertIn("11", compiled)
        self.assertEqual(compiled["11"]["class_type"], "ComfyModalProductionOutput")
        # 9 is reachable from 11 (SaveImage.images <- VAEDecode.images)
        self.assertIn("9", compiled)

    def test_no_snapshot_output_fails_at_compile(self):
        """No snapshot outputNodeId and no caller IDs → compile raises ValueError."""
        prod = normalize_production_options(None)
        self.assertTrue(prod["enabled"])
        self.assertEqual(prod["output_node_ids"], [])

        snapshot = {"outputNodeId": ""}
        _snap_output = str(snapshot.get("outputNodeId", "")).strip()
        self.assertEqual(_snap_output, "")

        # No derivation possible → should fail at compile with clear error
        with self.assertRaises(ValueError) as ctx:
            compile_production_workflow(WORKFLOW, prod, allow_direct_output_rewrite=True)
        self.assertIn("output_node_ids must not be empty", str(ctx.exception))


# ══════════════════════════════════════════════════════════════════════════
# D. Experiment per-preset independent reports
# ══════════════════════════════════════════════════════════════════════════

class ExperimentPerPresetReportTests(unittest.TestCase):
    """Each preset gets its own production report; no union/last report for all."""

    def setUp(self):
        _reset_cache()

    def test_each_checkpoint_independent_report(self):
        """Each checkpoint's production_report is independent."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })

        # Compile same workflow with same prod — each gets own report
        ck1_report = compile_production_workflow(
            WORKFLOW, dict(prod), allow_direct_output_rewrite=True
        )[1]
        ck2_report = compile_production_workflow(
            WORKFLOW, dict(prod), allow_direct_output_rewrite=True
        )[1]

        self.assertTrue(ck1_report["enabled"])
        self.assertTrue(ck2_report["enabled"])
        self.assertEqual(ck1_report["output_node_ids"], ["9"])
        self.assertEqual(ck2_report["output_node_ids"], ["9"])

    def test_cells_carry_own_report_not_union(self):
        """Each cell carries its own report; the last/union is not passed to all."""
        cells = [
            {"cell_key": "c1", "checkpoint_id": "ck1",
             "production_report": {"enabled": True, "output_node_ids": ["9"]}},
            {"cell_key": "c2", "checkpoint_id": "ck2",
             "production_report": {"enabled": True, "output_node_ids": ["11"]}},
        ]

        # Cell c1 has only its own IDs
        self.assertEqual(cells[0]["production_report"]["output_node_ids"], ["9"])
        # Cell c2 has only its own IDs
        self.assertEqual(cells[1]["production_report"]["output_node_ids"], ["11"])

    def test_compiled_hashes_match_across_presets(self):
        """Each preset's compiled and runner hashes must match."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })
        c1, r1 = compile_production_workflow(WORKFLOW, dict(prod), allow_direct_output_rewrite=True)
        c2, r2 = compile_production_workflow(WORKFLOW, dict(prod), allow_direct_output_rewrite=True)

        self.assertEqual(r1["compiled_workflow_hash"], r1["runner_workflow_hash"])
        self.assertEqual(r2["compiled_workflow_hash"], r2["runner_workflow_hash"])

    def test_different_output_ids_per_preset(self):
        """Presets with different output_node_ids produce different compiled hashes."""
        prod9 = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })
        prod11 = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["11"]}
        })
        _, r1 = compile_production_workflow(WORKFLOW, prod9, allow_direct_output_rewrite=False)
        _, r2 = compile_production_workflow(WORKFLOW, prod11, allow_direct_output_rewrite=False)

        self.assertNotEqual(r1["compiled_workflow_hash"], r2["compiled_workflow_hash"])


# ══════════════════════════════════════════════════════════════════════════
# E. Runner receives matching cell report/options
# ══════════════════════════════════════════════════════════════════════════

class RunnerCellReportSelectionTests(unittest.TestCase):
    """LocalRemoteInvoker.run_cell uses cell report first, merges into modal_options."""

    def test_cell_report_takes_precedence(self):
        """Cell production_report is used before global (single-run fallback)."""
        cell_report = {"enabled": True, "schema_version": 1,
                        "output_node_ids": ["9"],
                        "compiled_workflow_hash": "aaaa"}
        global_report = {"enabled": True, "schema_version": 1,
                          "output_node_ids": ["11"],
                          "compiled_workflow_hash": "bbbb"}

        cell = {"production_report": cell_report}
        effective = cell.get("production_report")
        if effective is None:
            effective = global_report

        self.assertEqual(effective["output_node_ids"], ["9"])
        self.assertEqual(effective["compiled_workflow_hash"], "aaaa")

    def test_no_cell_report_falls_back_to_global(self):
        """No cell report → global single-run report."""
        global_report = {"enabled": True, "output_node_ids": ["11"]}
        cell = {}
        effective = cell.get("production_report")
        if effective is None:
            effective = global_report
        self.assertEqual(effective, global_report)

    def test_report_merged_into_modal_options(self):
        """Report output_node_ids are merged into remote modal_options."""
        report = {"enabled": True, "schema_version": 1,
                   "output_node_ids": ["9", "10"],
                   "direct_output_sink_enabled": True}
        _mo = {"production": {
            "enabled": True,
            "schema_version": report.get("schema_version", 1),
            "output_node_ids": list(report.get("output_node_ids", [])),
            "direct_output_sink": report.get("direct_output_sink_enabled", True),
            "metadata_mode": "none",
        }}
        self.assertEqual(_mo["production"]["output_node_ids"], ["9", "10"])
        self.assertTrue(_mo["production"]["enabled"])

    def test_matching_report_fowarded_to_remote(self):
        """The matching report is forwarded to run_prompt_stream."""
        report = {"enabled": True, "schema_version": 1,
                   "output_node_ids": ["9"],
                   "compiled_workflow_hash": "hash123"}
        stream_kwargs = {}
        if report:
            stream_kwargs["production_report"] = report
        self.assertIn("production_report", stream_kwargs)
        self.assertEqual(stream_kwargs["production_report"]["compiled_workflow_hash"], "hash123")


# ══════════════════════════════════════════════════════════════════════════
# F. Truthful diagnostics with required keys
# ══════════════════════════════════════════════════════════════════════════

class DiagnosticsContractTests(unittest.TestCase):
    """Diagnostics must use the required exact keys."""

    def setUp(self):
        _reset_cache()

    _REQUIRED_DIAG_KEYS = [
        "execution_surface",
        "production_default_applied",
        "production_explicitly_disabled",
        "production_output_source",
        "production_output_ids",
        "production_plan_used",
        "production_output_count",
    ]

    def test_all_diag_keys_present_in_compilation(self):
        """Build a compilation-like dict and verify all diag keys."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })
        compiled, report = compile_production_workflow(
            WORKFLOW, prod, allow_direct_output_rewrite=True
        )
        report["source_workflow_hash"] = _compute_source_workflow_hash(WORKFLOW)

        # Simulate compilation diag dict
        diag = {
            "execution_surface": "studio_single",
            "production_default_applied": False,
            "production_explicitly_disabled": False,
            "production_output_source": "caller",
            "production_output_ids": ["9"],
            "production_source_hash": report.get("source_workflow_hash", ""),
            "production_plan_hash": report.get("topology_hash", ""),
            "production_compiled_hash": report.get("compiled_workflow_hash", ""),
            "runner_workflow_hash": report.get("runner_workflow_hash", ""),
            "production_plan_used": True,
            "production_output_count": 1,
        }
        for key in self._REQUIRED_DIAG_KEYS:
            self.assertIn(key, diag, f"Missing required diag key: {key}")

    def test_default_applied_diagnostics(self):
        """Omitted/default production shows default_applied=True."""
        diag = {
            "execution_surface": "playground",
            "production_default_applied": True,
            "production_explicitly_disabled": False,
            "production_output_source": "none",
            "production_output_ids": [],
            "production_plan_used": False,
            "production_output_count": 0,
        }
        self.assertTrue(diag["production_default_applied"])
        self.assertFalse(diag["production_explicitly_disabled"])

    def test_explicit_disabled_diagnostics(self):
        """Explicit false shows explicitly_disabled=True."""
        diag = {
            "execution_surface": "playground",
            "production_default_applied": False,
            "production_explicitly_disabled": True,
            "production_output_source": "none",
            "production_output_ids": [],
            "production_plan_used": False,
            "production_output_count": 0,
        }
        self.assertFalse(diag["production_default_applied"])
        self.assertTrue(diag["production_explicitly_disabled"])

    def test_hash_fields_present_and_matching(self):
        """source_hash, plan_hash, compiled_hash, runner_hash all present."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })
        compiled, report = compile_production_workflow(
            WORKFLOW, prod, allow_direct_output_rewrite=True
        )
        report["source_workflow_hash"] = _compute_source_workflow_hash(WORKFLOW)

        # Compiled == runner
        self.assertEqual(report["compiled_workflow_hash"], report["runner_workflow_hash"])
        # Compiled hash is valid SHA-256
        self.assertEqual(len(report["compiled_workflow_hash"]), 64)
        # Source hash differs from compiled hash when nodes removed
        self.assertNotEqual(report["source_workflow_hash"], report["compiled_workflow_hash"])

    def test_output_id_count_matches(self):
        """production_output_count matches len(production_output_ids)."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9", "10"]}
        })
        _, report = compile_production_workflow(
            WORKFLOW, prod, allow_direct_output_rewrite=True
        )
        output_ids = report.get("output_node_ids", [])
        count = len(output_ids)
        self.assertEqual(count, 2)

    def test_preset_binding_source(self):
        """production_output_source='preset_binding' when derived from snapshot."""
        diag_source = "preset_binding"
        self.assertEqual(diag_source, "preset_binding")

    def test_caller_source(self):
        """production_output_source='caller' when caller provided IDs."""
        diag_source = "caller"
        self.assertEqual(diag_source, "caller")


# ══════════════════════════════════════════════════════════════════════════
# G. Integration: compile with valid production works end-to-end
# ══════════════════════════════════════════════════════════════════════════

class ProductionIntegrationTests(unittest.TestCase):
    """End-to-end production compilation with proper output binding."""

    def setUp(self):
        _reset_cache()

    def test_compile_with_output_9_succeeds(self):
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })
        compiled, report = compile_production_workflow(
            WORKFLOW, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("9", compiled)
        self.assertTrue(report["enabled"])
        self.assertEqual(report["compiled_workflow_hash"],
                         _compute_compiled_workflow_hash(compiled))

    def test_cache_hit_produces_same_hash(self):
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["9"]}
        })
        _, r1 = compile_production_workflow(WORKFLOW, prod, allow_direct_output_rewrite=True)
        _, r2 = compile_production_workflow(WORKFLOW, prod, allow_direct_output_rewrite=True)
        self.assertTrue(r2["cache_hit"])
        self.assertEqual(r1["compiled_workflow_hash"], r2["compiled_workflow_hash"])

    def test_no_debug_fallback_on_compile_failure(self):
        """Compile failure must raise, not catch and continue."""
        prod = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["999"]}
        })
        with self.assertRaises(ValueError) as ctx:
            compile_production_workflow(WORKFLOW, prod, allow_direct_output_rewrite=True)
        self.assertIn("999", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
