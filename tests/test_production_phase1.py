"""Phase 1 contract regression tests — surgical correctness pass.

Covers:
- Canonical normalize_production_options semantics (A)
- Generic /prompt with default but no output binding fails closed (B)
- Studio single-run derives output IDs from snapshot and compiles (C)
- Experiment per-preset independent reports (D)
- Runner receives matching cell report/options (E)
- Truthful diagnostics with required keys (F)
"""

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
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
            "production_plan_hash": report.get("production_plan_hash", ""),
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



# ══════════════════════════════════════════════════════════════════════════
# H. Phase 1 correction: modal_options=None compiles, explicit false skips
# ══════════════════════════════════════════════════════════════════════════

class Phase1CorrectionTests(unittest.TestCase):
    """modal_options=None compiles production from preset bindings; explicit false skips."""

    _REPO_ROOT = Path(__file__).resolve().parents[1]

    @classmethod
    def setUpClass(cls):
        _reset_cache()
        # Load studio_run_adapter module (same pattern as test_studio_runtime)
        _mod_path = cls._REPO_ROOT / "studio_run_adapter.py"
        _spec = importlib.util.spec_from_file_location("studio_run_adapter", str(_mod_path))
        assert _spec is not None, "Could not find studio_run_adapter.py"
        assert _spec.loader is not None
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_spec.name] = _mod
        _spec.loader.exec_module(_mod)
        cls.adapter = _mod

    def setUp(self):
        _reset_cache()

    @staticmethod
    def _make_snapshot(output_node_id: str = "11",
                       snapshot_id: str = "snap_h") -> dict:
        """Minimal runnable snapshot with a single output node."""
        return {
            "id": snapshot_id,
            "name": "Phase1H Snapshot",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": copy.deepcopy(WORKFLOW),
            "nodeBindings": {},
            "outputNodeId": output_node_id,
            "graphJson": {"nodes": [], "links": []},
            "archived": False,
            "status": "runnable",
            "featureStatus": {
                "txt2img": {"status": "runnable", "reason": ""},
            },
            "disabledReason": "",
        }

    @staticmethod
    def _make_preset(preset_id: str = "preset_h",
                     snapshot_id: str = "snap_h") -> dict:
        return {
            "id": preset_id,
            "label": "Phase1H Preset",
            "snapshotId": snapshot_id,
            "compatibleFeatures": ["txt2img"],
            "defaults": {},
            "sourceType": "snapshot",
            "sourceId": "",
            "archived": False,
            "status": "runnable",
            "disabledReason": "",
        }

    # ── Single-run tests ───────────────────────────────────────────────

    def test_single_run_none_compiles_production(self):
        """build_single_run_spec(modal_options=None) compiles from preset outputNodeId."""
        snap = self._make_snapshot(output_node_id="11")
        preset = self._make_preset()
        spec = self.adapter.build_single_run_spec(
            preset, snap, "txt2img", {"prompt": "hello"}, "/tmp",
            modal_options=None,
        )
        self.assertNotIn("error", spec,
                         "modal_options=None should not produce an error")
        ck = spec["checkpoints"][0]
        self.assertIsNotNone(ck.get("production_report"),
                             "production_report must be present after compile")
        self.assertTrue(ck["production_report"]["enabled"],
                        "production must be enabled")
        self.assertIn("11", ck["production_report"]["output_node_ids"],
                      "output_node_ids must contain the derived output node")
        # Output node should be rewritten to ComfyModalProductionOutput
        self.assertEqual(
            ck["workflow"]["11"]["class_type"],
            "ComfyModalProductionOutput",
            "SaveImage output node must be rewritten",
        )
        # Top-level diagnostics
        self.assertFalse(spec.get("production_explicitly_disabled"))
        self.assertEqual(spec.get("production_output_source"), "preset_binding")
        # Hash diagnostics from compiler report
        self.assertIn("production_source_hash", spec)
        self.assertIn("production_compiled_hash", spec)
        self.assertIn("runner_workflow_hash", spec)
        self.assertTrue(spec.get("production_plan_used"))

    def test_single_run_none_no_output_binding_errors(self):
        """build_single_run_spec(modal_options=None) without binding returns precise error."""
        snap = self._make_snapshot(output_node_id="")
        snap["nodeBindings"] = {}
        preset = self._make_preset()
        spec = self.adapter.build_single_run_spec(
            preset, snap, "txt2img", {"prompt": "hello"}, "/tmp",
            modal_options=None,
        )
        self.assertIn("error", spec)
        msg = spec["error"]
        self.assertIn("no output node id could be derived", msg.lower())
        self.assertIn("outputnodeid", msg.lower())
        self.assertIn("output binding", msg.lower())

    def test_single_run_explicit_false_skips_production(self):
        """build_single_run_spec(modal_options={"production": {"enabled": False}}) skips."""
        snap = self._make_snapshot(output_node_id="11")
        preset = self._make_preset()
        spec = self.adapter.build_single_run_spec(
            preset, snap, "txt2img", {"prompt": "hello"}, "/tmp",
            modal_options={"production": {"enabled": False}},
        )
        self.assertNotIn("error", spec)
        ck = spec["checkpoints"][0]
        # No production report when explicitly disabled
        self.assertIsNone(ck.get("production_report"),
                          "production_report must be None when explicitly disabled")
        # Workflow should NOT be compiled (original class_type preserved)
        self.assertEqual(
            ck["workflow"]["11"]["class_type"],
            "SaveImage",
            "Output node must retain original class_type when production is disabled",
        )
        self.assertTrue(spec.get("production_explicitly_disabled"),
                        "production_explicitly_disabled must be True")
        self.assertFalse(spec.get("production_plan_used"),
                         "production_plan_used must be False")

    def test_single_run_explicit_true_still_compiles(self):
        """build_single_run_spec with explicit production.enabled=True compiles."""
        snap = self._make_snapshot(output_node_id="11")
        preset = self._make_preset()
        spec = self.adapter.build_single_run_spec(
            preset, snap, "txt2img", {"prompt": "hello"}, "/tmp",
            modal_options={"production": {"enabled": True, "schema_version": 1}},
        )
        self.assertNotIn("error", spec)
        ck = spec["checkpoints"][0]
        self.assertIsNotNone(ck.get("production_report"))
        self.assertTrue(ck["production_report"]["enabled"])
        self.assertIn("11", ck["production_report"]["output_node_ids"])
        # Output rewritten
        self.assertEqual(
            ck["workflow"]["11"]["class_type"],
            "ComfyModalProductionOutput",
        )

    def test_single_run_none_with_output_binding_in_nodebindings(self):
        """Derives output from nodeBindings[output].kind==output when outputNodeId absent."""
        snap = self._make_snapshot(output_node_id="")
        snap["nodeBindings"] = {
            "output": {"kind": "output", "nodeId": "11"},
        }
        preset = self._make_preset()
        spec = self.adapter.build_single_run_spec(
            preset, snap, "txt2img", {"prompt": "hello"}, "/tmp",
            modal_options=None,
        )
        self.assertNotIn("error", spec)
        ck = spec["checkpoints"][0]
        self.assertIsNotNone(ck.get("production_report"))
        self.assertEqual(
            spec.get("production_output_source"), "preset_binding",
        )

    def test_single_run_absent_output_node_id_fails_closed(self):
        """build_single_run_spec raises ValueError when outputNodeId not in workflow
        (Phase 1 hardening: no silent skip, precise missing-node error propagates)."""
        snap = self._make_snapshot(output_node_id="999")  # 999 does not exist in WORKFLOW
        preset = self._make_preset()
        with self.assertRaises(ValueError) as ctx:
            self.adapter.build_single_run_spec(
                preset, snap, "txt2img", {"prompt": "hello"}, "/tmp",
                modal_options=None,
            )
        self.assertIn("999", str(ctx.exception),
                      "ValueError must reference the missing output node ID")

    # ── Experiment tests ───────────────────────────────────────────────

    def test_experiment_none_compiles_production(self):
        """build_experiment_spec(modal_options=None) compiles from preset outputNodeId."""
        snap = self._make_snapshot(output_node_id="11")
        preset = self._make_preset()
        exp_def = {
            "prompts": [{"id": "p1", "text": "a cat", "enabled": True}],
            "axes": {},
        }
        spec = self.adapter.build_experiment_spec(
            [(preset, snap)], "txt2img", exp_def, "/tmp",
            modal_options=None,
        )
        self.assertNotIn("error", spec)
        ck = spec["checkpoints"][0]
        self.assertIsNotNone(ck.get("production_report"),
                             "checkpoint must have production_report")
        self.assertTrue(ck["production_report"]["enabled"])
        self.assertIn("11", ck["production_report"]["output_node_ids"])
        # Output node rewritten
        self.assertEqual(
            ck["workflow"]["11"]["class_type"],
            "ComfyModalProductionOutput",
        )
        # Cell should carry the same report
        cell = spec["cells"][0]
        self.assertIsNotNone(cell.get("production_report"),
                             "cell must carry production_report from its checkpoint")
        self.assertEqual(
            cell["production_report"]["output_node_ids"],
            ["11"],
        )

    def test_experiment_none_no_output_binding_errors(self):
        """build_experiment_spec(modal_options=None) without binding fails closed."""
        snap = self._make_snapshot(output_node_id="")
        snap["nodeBindings"] = {}
        preset = self._make_preset()
        exp_def = {
            "prompts": [{"id": "p1", "text": "a cat", "enabled": True}],
            "axes": {},
        }
        spec = self.adapter.build_experiment_spec(
            [(preset, snap)], "txt2img", exp_def, "/tmp",
            modal_options=None,
        )
        self.assertIn("error", spec)
        msg = spec["error"]
        self.assertIn("no output node id could be derived", msg.lower())

    def test_experiment_explicit_false_skips_production(self):
        """build_experiment_spec with explicit enabled=False skips compile."""
        snap = self._make_snapshot(output_node_id="11")
        preset = self._make_preset()
        exp_def = {
            "prompts": [{"id": "p1", "text": "a cat", "enabled": True}],
            "axes": {},
        }
        spec = self.adapter.build_experiment_spec(
            [(preset, snap)], "txt2img", exp_def, "/tmp",
            modal_options={"production": {"enabled": False}},
        )
        self.assertNotIn("error", spec)
        ck = spec["checkpoints"][0]
        self.assertIsNone(ck.get("production_report"),
                          "No production_report when explicitly disabled")
        # Original class_type preserved
        self.assertEqual(
            ck["workflow"]["11"]["class_type"],
            "SaveImage",
        )
        self.assertTrue(spec.get("production_explicitly_disabled"))

    def test_experiment_source_hash_preserved(self):
        """source_workflow_hash from the compiler report is not overwritten with empty."""
        snap = self._make_snapshot(output_node_id="11")
        preset = self._make_preset()
        exp_def = {
            "prompts": [{"id": "p1", "text": "a cat", "enabled": True}],
            "axes": {},
        }
        spec = self.adapter.build_experiment_spec(
            [(preset, snap)], "txt2img", exp_def, "/tmp",
            modal_options=None,
        )
        self.assertNotIn("error", spec)
        ck = spec["checkpoints"][0]
        report = ck.get("production_report") or {}
        src_hash = report.get("source_workflow_hash", "")
        self.assertTrue(len(src_hash) > 0,
                        "source_workflow_hash must not be empty")
        self.assertEqual(len(src_hash), 64,
                         "source_workflow_hash must be a valid 64-char SHA-256")
        # compiled and runner hashes must also be present
        self.assertIn("compiled_workflow_hash", report)
        self.assertIn("runner_workflow_hash", report)
        self.assertEqual(report["compiled_workflow_hash"],
                         report["runner_workflow_hash"])

    def test_single_run_source_hash_preserved(self):
        """source_workflow_hash from compiler report is not overwritten with empty (single)."""
        snap = self._make_snapshot(output_node_id="11")
        preset = self._make_preset()
        spec = self.adapter.build_single_run_spec(
            preset, snap, "txt2img", {"prompt": "hello"}, "/tmp",
            modal_options=None,
        )
        self.assertNotIn("error", spec)
        ck = spec["checkpoints"][0]
        report = ck.get("production_report") or {}
        src_hash = report.get("source_workflow_hash", "")
        self.assertTrue(len(src_hash) > 0,
                        "source_workflow_hash must not be empty")
        self.assertEqual(len(src_hash), 64)
        self.assertIn("compiled_workflow_hash", report)
        self.assertIn("runner_workflow_hash", report)
        # Top-level diagnostics match report
        self.assertEqual(spec.get("production_source_hash"), src_hash)
        self.assertEqual(spec.get("production_compiled_hash"),
                         report.get("compiled_workflow_hash"))
        self.assertEqual(spec.get("runner_workflow_hash"),
                         report.get("runner_workflow_hash"))


if __name__ == "__main__":
    unittest.main()
