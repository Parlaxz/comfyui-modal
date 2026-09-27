"""Focused tests for run_prompt_options builder and merge helpers.

Tests are self-contained (no Modal, no Torch) and follow the repo's
unittest style with ``importlib.util`` module loading so the production
module is exercised through its public API.
"""

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "run_prompt_options.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_prompt_options", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ── Test cases ────────────────────────────────────────────────────────────


class TestBuildRunPromptOptions(unittest.TestCase):
    """Verify the builder produces canonical production/actual_load defaults."""

    def setUp(self):
        self.mod = load_module()

    def test_builder_returns_canonical_shape(self):
        result = self.mod.build_run_prompt_options(
            production_output_node_ids=["107", "42"],
            enable_actual_load=True,
        )
        self.assertIn("production", result)
        self.assertIn("actual_load", result)
        # production
        prod = result["production"]
        self.assertTrue(prod["enabled"])
        self.assertEqual(prod["output_node_ids"], ["42", "107"])
        # actual_load
        al = result["actual_load"]
        self.assertTrue(al["enabled"])
        self.assertEqual(al["mode"], "unet_vae_only")

    def test_builder_normalizes_output_ids(self):
        result = self.mod.build_run_prompt_options(
            production_output_node_ids=["107", "42", "107", " 3 "],
            enable_actual_load=True,
        )
        self.assertEqual(
            result["production"]["output_node_ids"],
            ["3", "42", "107"],
        )

    def test_builder_empty_ids(self):
        result = self.mod.build_run_prompt_options(
            production_output_node_ids=[],
            enable_actual_load=False,
        )
        self.assertEqual(result["production"]["output_node_ids"], [])
        self.assertFalse(result["actual_load"]["enabled"])
        self.assertEqual(result["actual_load"]["mode"], "unet_vae_only")

    def test_builder_actual_load_disabled(self):
        result = self.mod.build_run_prompt_options(
            production_output_node_ids=["7"],
            enable_actual_load=False,
        )
        self.assertFalse(result["actual_load"]["enabled"])


class TestEnsureRunPromptOptions(unittest.TestCase):
    """Verify the merge helper preserves caller keys and sets defaults."""

    def setUp(self):
        self.mod = load_module()
        self.base_builder = self.mod.build_run_prompt_options(
            production_output_node_ids=["107"],
            enable_actual_load=True,
        )

    def test_merge_from_none(self):
        merged = self.mod.ensure_run_prompt_options(None, self.base_builder)
        self.assertIn("production", merged)
        self.assertIn("actual_load", merged)
        self.assertTrue(merged["production"]["enabled"])
        self.assertTrue(merged["actual_load"]["enabled"])
        self.assertEqual(merged["actual_load"]["mode"], "unet_vae_only")

    def test_merge_from_empty(self):
        merged = self.mod.ensure_run_prompt_options({}, self.base_builder)
        self.assertTrue(merged["production"]["enabled"])
        self.assertTrue(merged["actual_load"]["enabled"])

    def test_retains_caller_keys(self):
        existing = {
            "runtime": {"foo": "bar"},
            "output_format": "webp",
            "comfymodal_scheduler_test": {"enabled": True},
        }
        merged = self.mod.ensure_run_prompt_options(existing, self.base_builder)
        self.assertEqual(merged["runtime"], {"foo": "bar"})
        self.assertEqual(merged["output_format"], "webp")
        self.assertEqual(merged["comfymodal_scheduler_test"], {"enabled": True})
        # Builder defaults were also applied
        self.assertTrue(merged["production"]["enabled"])
        self.assertTrue(merged["actual_load"]["enabled"])

    def test_preserves_explicit_production_disabled(self):
        existing = {"production": {"enabled": False}}
        merged = self.mod.ensure_run_prompt_options(existing, self.base_builder)
        self.assertIs(merged["production"]["enabled"], False)
        # actual_load still gets defaults
        self.assertTrue(merged["actual_load"]["enabled"])

    def test_preserves_explicit_actual_load_disabled(self):
        existing = {"actual_load": {"enabled": False}}
        merged = self.mod.ensure_run_prompt_options(existing, self.base_builder)
        self.assertIs(merged["actual_load"]["enabled"], False)
        # production still gets defaults
        self.assertTrue(merged["production"]["enabled"])

    def test_merges_existing_not_opt_out(self):
        existing = {
            "production": {"enabled": True, "output_node_ids": ["99"]},
            "actual_load": {"enabled": True, "mode": "clip_vae_only"},
        }
        merged = self.mod.ensure_run_prompt_options(existing, self.base_builder)
        # Existing sub-keys preserved
        self.assertEqual(merged["production"]["output_node_ids"], ["99"])
        self.assertEqual(merged["actual_load"]["mode"], "clip_vae_only")
        # Builder's output_node_ids were overridden by existing
        self.assertNotEqual(
            merged["production"]["output_node_ids"],
            self.base_builder["production"]["output_node_ids"],
        )


class TestActualLoadStreamKwargsDefaults(unittest.TestCase):
    """Verify that the scheduler/V2 stream-kwargs construction includes
    actual_load config on the default path.

    H19 rename: formerly TestLocalRemoteInvokerActualLoad — the retired V1
    invoker was deleted; this pins the still-live build/ensure
    run-prompt-options contract its callers rely on.
    """

    def setUp(self):
        self.mod = load_module()

    def test_default_stream_kwargs_include_actual_load(self):
        """Simulate the shared stream-kwargs construction:
        1. Build _mo from modal_options (None for default path)
        2. Merge production report if present
        3. Call build/ensure_run_prompt_options
        4. Verify actual_load is present with correct defaults.
        """
        # Simulate no existing modal_options (default path)
        _mo = {}

        # Simulate an effective production report
        _effective_prod_report = {
            "enabled": True,
            "schema_version": 1,
            "output_node_ids": ["7", "42"],
            "direct_output_sink_enabled": True,
        }
        if _effective_prod_report and _effective_prod_report.get("enabled"):
            _mo.setdefault("production", {}).update({
                "enabled": True,
                "schema_version": _effective_prod_report.get("schema_version", 1),
                "output_node_ids": list(_effective_prod_report.get("output_node_ids", [])),
                "direct_output_sink": _effective_prod_report.get("direct_output_sink_enabled", True),
                "metadata_mode": "none",
            })

        # Builder step (shared by every execution path)
        _prod_ids_for_builder = []
        if _mo.get("production") and _mo["production"].get("enabled"):
            _prod_ids_for_builder = _mo["production"].get("output_node_ids", [])
        _builder_opts = self.mod.build_run_prompt_options(
            production_output_node_ids=_prod_ids_for_builder,
            enable_actual_load=True,
        )
        _mo = self.mod.ensure_run_prompt_options(_mo, _builder_opts)

        # Verify actual_load defaults are present
        self.assertIn("actual_load", _mo)
        self.assertTrue(_mo["actual_load"]["enabled"])
        self.assertEqual(_mo["actual_load"]["mode"], "unet_vae_only")

        # Verify production output IDs survived (numeric sort: 7 < 42)
        self.assertEqual(
            _mo["production"]["output_node_ids"],
            ["7", "42"],  # sorted by the builder
        )

        # Simulate a caller opt-out: explicit actual_load disabled
        _mo_opts_out = {"actual_load": {"enabled": False}}
        _merged_out = self.mod.ensure_run_prompt_options(_mo_opts_out, _builder_opts)
        self.assertIs(_merged_out["actual_load"]["enabled"], False)


class TestComfyappActualLoadResolution(unittest.TestCase):
    """Server-side actual-load option resolution (testable without Modal)."""

    def setUp(self):
        self.mod = load_module()

    def _simulate_resolution(self, modal_options=None):
        """Simulate the resolution logic from _prompt_async_actual_load."""
        _req_al = (modal_options or {}).get("actual_load", {})
        if isinstance(_req_al, dict):
            eff_enabled = _req_al.get("enabled", False)  # PROMPT_ASYNC_ACTUAL_LOAD default
            eff_mode = _req_al.get("mode", "clip_vae_only")  # ACTUAL_LOAD_MODE default
        else:
            eff_enabled = False
            eff_mode = "clip_vae_only"
        eff_enabled = bool(eff_enabled)
        eff_mode = str(eff_mode).strip().lower()
        if eff_mode not in ("off", "clip_vae_only", "unet_only", "unet_vae_only"):
            eff_mode = "clip_vae_only"
        return eff_enabled, eff_mode

    def test_default_resolution_falls_back_to_env_values(self):
        """No modal_options → use env defaults (disabled, clip_vae_only)."""
        enabled, mode = self._simulate_resolution(None)
        self.assertFalse(enabled)
        self.assertEqual(mode, "clip_vae_only")

    def test_request_overrides_enabled(self):
        """builder's actual_load.enabled=True overrides the False env default."""
        modal_opts = {"actual_load": {"enabled": True}}
        enabled, mode = self._simulate_resolution(modal_opts)
        self.assertTrue(enabled)

    def test_request_overrides_mode(self):
        """builder's actual_load.mode=unet_vae_only overrides clip_vae_only."""
        modal_opts = {"actual_load": {"enabled": True, "mode": "unet_vae_only"}}
        enabled, mode = self._simulate_resolution(modal_opts)
        self.assertTrue(enabled)
        self.assertEqual(mode, "unet_vae_only")
        # Mode should pass the validate check
        self.assertIn(mode, ("off", "clip_vae_only", "unet_only", "unet_vae_only"))

    def test_explicit_opt_out_preserved(self):
        """Caller actual_load.enabled=False is preserved."""
        modal_opts = {"actual_load": {"enabled": False}}
        enabled, mode = self._simulate_resolution(modal_opts)
        self.assertFalse(enabled)

    def test_invalid_mode_falls_back(self):
        modal_opts = {"actual_load": {"enabled": True, "mode": "invalid_mode"}}
        enabled, mode = self._simulate_resolution(modal_opts)
        self.assertTrue(enabled)
        self.assertEqual(mode, "clip_vae_only")  # fallback to env default


class TestActualLoadSummary(unittest.TestCase):
    """Verify actual_load_summary shape in the trace path."""

    def setUp(self):
        self.mod = load_module()

    def test_summary_in_builder_output(self):
        """The builder doesn't produce summary directly (it's in _prompt_async_actual_load),
        but we verify the invariant: when actual_load options are merged,
        the remote side receives the right settings to produce a summary."""
        result = self.mod.build_run_prompt_options(
            production_output_node_ids=[],
            enable_actual_load=True,
        )
        self.assertTrue(result["actual_load"]["enabled"])
        self.assertEqual(result["actual_load"]["mode"], "unet_vae_only")

        # Simulate the server-side summary construction
        summary = {
            "enabled": result["actual_load"]["enabled"],
            "mode": result["actual_load"]["mode"],
        }
        self.assertEqual(summary, {"enabled": True, "mode": "unet_vae_only"})

    def test_summary_present_when_disabled(self):
        """Summary must be present even when actual_load is disabled."""
        result = self.mod.build_run_prompt_options(
            production_output_node_ids=[],
            enable_actual_load=False,
        )
        summary = {
            "enabled": result["actual_load"]["enabled"],
            "mode": result["actual_load"]["mode"],
        }
        self.assertFalse(summary["enabled"])
        self.assertIn("mode", summary)


if __name__ == "__main__":
    unittest.main()
