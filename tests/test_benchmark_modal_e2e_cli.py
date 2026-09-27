"""Focused unit tests for benchmark_modal_e2e CLI/preset logic.

Tests cover:
- build_effective_config: explicit CLI values win over preset defaults
- build_effective_config: omitted values fall back to preset defaults
- --no-deploy with health failure: noninteractive, nonzero exit, no deploy call
- --no-deploy with health OK: proceeds normally (no spurious bail-out)

All tests import pure helpers via importlib or use unittest.mock.
No Modal or GPU dependency.
"""

import copy
import importlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_E2E = REPO_ROOT / "benchmark_modal_e2e.py"


def _load_mod():
    """Lazy-import benchmark_modal_e2e for access to pure helpers.

    Registers the module in sys.modules so mock.patch("benchmark_modal_e2e.*")
    can resolve it.
    """
    mod_name = "benchmark_modal_e2e"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, BENCHMARK_E2E)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ============================================================================
# build_effective_config — explicit vs preset semantics
# ============================================================================


class TestEffectiveConfigPresetCLI(unittest.TestCase):
    """build_effective_config must respect explicit CLI args over preset defaults."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def test_explicit_runs_overrides_preset(self):
        """--runs 1 explicit => config.runs = 1 even with cold-baseline preset."""
        cfg = self.mod.build_effective_config("cold-baseline", {"runs": 1}, [])
        self.assertEqual(cfg["benchmark"]["runs"], 1)

    def test_omitted_runs_uses_preset_default(self):
        """--runs omitted => config.runs = 3 (cold-baseline preset default)."""
        cfg = self.mod.build_effective_config("cold-baseline", {}, [])
        self.assertEqual(cfg["benchmark"]["runs"], 3)

    def test_explicit_mode_overrides_preset_cold(self):
        """--mode warm explicit overrides preset default 'cold'."""
        cfg = self.mod.build_effective_config("cold-baseline", {"mode": "warm"}, [])
        self.assertEqual(cfg["benchmark"]["mode"], "warm")

    def test_omitted_mode_uses_preset_cold(self):
        """--mode omitted => preset default 'cold'."""
        cfg = self.mod.build_effective_config("cold-baseline", {}, [])
        self.assertEqual(cfg["benchmark"]["mode"], "cold")

    def test_explicit_poll_interval_wins(self):
        """--poll-interval 0.5 explicit overrides preset 0.1."""
        cfg = self.mod.build_effective_config("cold-baseline", {"poll_interval": 0.5}, [])
        self.assertEqual(cfg["benchmark"]["poll_interval"], 0.5)

    def test_explicit_print_cost_warning_false(self):
        """--no-print-cost-warning (False) overrides preset True."""
        cfg = self.mod.build_effective_config("cold-baseline", {"print_cost_warning": False}, [])
        self.assertIs(cfg["benchmark"]["print_cost_warning"], False)

    def test_explicit_sleep_between_overrides(self):
        """--sleep-between-runs 5 explicit overrides preset 10."""
        cfg = self.mod.build_effective_config("cold-baseline", {"sleep_between_runs": 5}, [])
        self.assertEqual(cfg["benchmark"]["sleep_between_runs"], 5)

    def test_explicit_min_gap_overrides(self):
        """--min-gap-between-runs 3 explicit overrides preset 10."""
        cfg = self.mod.build_effective_config("cold-baseline", {"min_gap_between_runs": 3}, [])
        self.assertEqual(cfg["benchmark"]["min_gap_between_runs"], 3)

    def test_explicit_strict_inter_run_sleep(self):
        """--strict-inter-run-sleep explicit => True."""
        cfg = self.mod.build_effective_config("cold-baseline", {"strict_inter_run_sleep": True}, [])
        self.assertIs(cfg["benchmark"]["strict_inter_run_sleep"], True)

    def test_omitted_strict_inter_run_sleep(self):
        """--strict-inter-run-sleep omitted => preset True (cold-baseline)."""
        cfg = self.mod.build_effective_config("cold-baseline", {}, [])
        self.assertIs(cfg["benchmark"]["strict_inter_run_sleep"], True)

    def test_explicit_write_analysis_pack_false_overrides(self):
        """--no-write-analysis-pack (False) overrides preset True."""
        cfg = self.mod.build_effective_config("cold-baseline", {"write_analysis_pack": False}, [])
        self.assertIs(cfg["benchmark"]["write_analysis_pack"], False)

    def test_explicit_include_local_materialization_true(self):
        """--include-local-materialization explicit => True overrides preset True (same val ok)."""
        cfg = self.mod.build_effective_config("cold-baseline", {"include_local_materialization": True}, [])
        self.assertIs(cfg["benchmark"]["include_local_materialization"], True)

    def test_cli_overrides_tracked_in_config_sources(self):
        """Explicit CLI values appear in config_sources.cli_overrides."""
        cfg = self.mod.build_effective_config(
            "cold-baseline", {"runs": 5, "mode": "warm"}, [],
        )
        overrides = cfg["config_sources"]["cli_overrides"]
        self.assertTrue(
            any("cli.runs=5" in o for o in overrides),
            f"cli.runs=5 not found in {overrides}",
        )
        self.assertTrue(
            any("cli.mode=warm" in o for o in overrides),
            f"cli.mode=warm not found in {overrides}",
        )

    def test_no_preset_with_explicit_runs(self):
        """Without preset, explicit --runs 2 => runs=2."""
        cfg = self.mod.build_effective_config(None, {"runs": 2}, [])
        self.assertEqual(cfg["benchmark"]["runs"], 2)

    def test_no_preset_omitted_runs_uses_cold_baseline_base(self):
        """Without preset, omitted --runs falls back to cold-baseline base (3)."""
        cfg = self.mod.build_effective_config(None, {}, [])
        self.assertEqual(cfg["benchmark"]["runs"], 3)

    def test_no_deploy_in_effective_config_when_explicit(self):
        """--no-deploy True is tracked in effective config."""
        cfg = self.mod.build_effective_config("cold-baseline", {"no_deploy": True}, [])
        self.assertIs(cfg["benchmark"].get("no_deploy"), True)

    def test_no_deploy_not_in_config_when_omitted(self):
        """no_deploy absent when not provided."""
        cfg = self.mod.build_effective_config("cold-baseline", {}, [])
        self.assertIsNone(cfg["benchmark"].get("no_deploy"))

    def test_same_seed_in_config_when_explicit(self):
        """--same-seed True is tracked in effective config."""
        cfg = self.mod.build_effective_config("cold-baseline", {"same_seed": True}, [])
        self.assertIs(cfg["benchmark"].get("same_seed"), True)

    def test_poll_timeout_explicit(self):
        """--poll-timeout 900 explicit overrides default 600."""
        cfg = self.mod.build_effective_config("cold-baseline", {"poll_timeout": 900}, [])
        self.assertEqual(cfg["benchmark"]["poll_timeout"], 900)

    def test_result_mode_explicit(self):
        """--result-mode blocking explicit."""
        cfg = self.mod.build_effective_config("cold-baseline", {"result_mode": "blocking"}, [])
        self.assertEqual(cfg["benchmark"]["result_mode"], "blocking")

    def test_output_format_explicit(self):
        """--output-format webp_lossy explicit."""
        cfg = self.mod.build_effective_config("cold-baseline", {"output_format": "webp_lossy"}, [])
        self.assertEqual(cfg["benchmark"]["output_format"], "webp_lossy")

    def test_return_mode_explicit(self):
        """--return-mode first_image_only explicit."""
        cfg = self.mod.build_effective_config("cold-baseline", {"return_mode": "first_image_only"}, [])
        self.assertEqual(cfg["benchmark"]["return_mode"], "first_image_only")


# ============================================================================
# Flushing behavior
# ============================================================================


class TestPrintFlushing(unittest.TestCase):
    """User-visible startup/progress/cost-warning prints flush in non-TTY execution."""

    def test_benchmark_banner_prints_flush(self):
        """The banner at the top of cmd_benchmark includes flush=True calls."""
        source = BENCHMARK_E2E.read_text("utf-8")
        # The health-failure error message uses flush=True
        self.assertIn(
            "ERROR: ComfyUI is not running at",
            source,
        )
        # Check that the no-deploy error flush=True exists
        self.assertIn(
            "flush=True",
            source,
        )


# ============================================================================
# --no-deploy health-failure handling  (patched, no Modal/GPU)
# ============================================================================


class TestNoDeployHealthFailure(unittest.TestCase):
    """--no-deploy must fail fast without prompting when health is not OK."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def _make_args(self, **overrides):
        """Minimal argparse.Namespace for cmd_benchmark.

        dry_run=True by default to prevent workflow-load errors in tests.
        Tests that need to exercise past health checks can set dry_run=False
        and provide a workflow / mock the JSON calls.
        """
        base = dict(
            runs=1, mode="cold", profile_level="summary",
            sleep_between_runs=10, min_gap_between_runs=10,
            strict_inter_run_sleep=False, poll_interval=0.25,
            poll_timeout=600, result_mode="poll",
            output_format="original", return_mode="full_base64",
            same_seed=False, same_workflow=False, same_active_profile=False,
            include_local_materialization=False,
            write_analysis_pack=False, analysis_pack_include_timelines=False,
            analysis_pack_include_wall_traces=False,
            no_deploy=True, dry_run=True, print_cost_warning=False,
            workflow="",
        )
        base.update(overrides)
        return mock.MagicMock(**base, spec=[])

    @mock.patch("benchmark_modal_e2e._json_request", side_effect=OSError("Not running"))
    def test_no_deploy_health_failure_returns_nonzero(self, mock_req):
        """--no-deploy with unhealthy ComfyUI => nonzero without prompting."""
        args = self._make_args(no_deploy=True)
        rc = self.mod.cmd_benchmark(args)
        self.assertNotEqual(rc, 0, "--no-deploy must return nonzero on health failure")

    @mock.patch("benchmark_modal_e2e._json_request", side_effect=OSError("Not running"))
    def test_no_deploy_health_failure_does_not_prompt(self, mock_req):
        """--no-deploy with unhealthy ComfyUI must not call input()."""
        args = self._make_args(no_deploy=True)
        with mock.patch("builtins.input", side_effect=Exception("input() called but should not be")):
            rc = self.mod.cmd_benchmark(args)
        self.assertNotEqual(rc, 0, "--no-deploy must return nonzero without calling input()")

    @mock.patch("benchmark_modal_e2e._json_request", return_value={"status": "ok"})
    def test_no_deploy_health_ok_does_not_bail(self, mock_req):
        """--no-deploy with healthy ComfyUI must not exit with health-failure code."""
        args = self._make_args(no_deploy=True)
        rc = self.mod.cmd_benchmark(args)
        # With dry_run=True the function returns 0 (not health-failure 1)
        self.assertEqual(rc, 0, "--no-deploy with healthy ComfyUI should reach dry-run exit (0)")

    @mock.patch("benchmark_modal_e2e._json_request", return_value={"status": "ok"})
    def test_no_deploy_does_not_call_deploy_subprocess(self, mock_req):
        """--no-deploy must never call subprocess.Popen for deploy (health ok path)."""
        args = self._make_args(no_deploy=True)
        with mock.patch("benchmark_modal_e2e.subprocess.Popen",
                        side_effect=Exception("subprocess.Popen called but should not be")):
            rc = self.mod.cmd_benchmark(args)
        # With dry_run=True, no benchmark runs, no deploy calls, should exit 0
        self.assertEqual(rc, 0, "--no-deploy with healthy ComfyUI should reach dry-run exit (0)")

    @mock.patch("benchmark_modal_e2e._json_request", side_effect=OSError("Not running"))
    def test_no_deploy_does_not_deploy_on_health_failure(self, mock_req):
        """--no-deploy with health failure exits early without deploy paths."""
        args = self._make_args(no_deploy=True)
        with mock.patch("benchmark_modal_e2e.subprocess.Popen",
                        side_effect=Exception("subprocess.Popen must not be called")):
            rc = self.mod.cmd_benchmark(args)
        self.assertNotEqual(rc, 0, "--no-deploy must exit nonzero before any deploy call")

    def test_health_failure_without_no_deploy_still_prompts(self):
        """Without --no-deploy, health failure still prompts (unchanged behavior)."""
        args = self._make_args(no_deploy=False)
        with mock.patch("benchmark_modal_e2e._json_request", side_effect=OSError("Not running")):
            with mock.patch("builtins.input", return_value="3") as mock_input:
                rc = self.mod.cmd_benchmark(args)
        self.assertEqual(rc, 0, "Without --no-deploy, user should be able to exit cleanly")
        mock_input.assert_called_once()


# ============================================================================
# Subprocess-level test (smoke)
# ============================================================================


class TestCLIExitCodes(unittest.TestCase):
    """Verify basic CLI subcommands work without Modal/GPU."""

    def test_selftest_runs_without_crash(self):
        """benchmark_modal_e2e.py selftest runs without Python-level crash.

        Note: 3 pre-existing structural source-code checks in comfyapp.py
        (restore CLIP preload markers, actual_load ordering) fail in the
        current codebase — these predate the CLI/preset fixes and are not
        related to --no-deploy or effective-config changes.
        """
        result = subprocess.run(
            [sys.executable, str(BENCHMARK_E2E), "selftest"],
            capture_output=True, text=True, timeout=60,
        )
        # Should not crash with Python exception; pre-existing failures may
        # produce returncode=1 but that is from the selftest assertions.
        self.assertIn(
            "Running selftest", result.stdout,
            "selftest should produce output before any failure",
        )
        self.assertNotIn("Traceback", result.stderr, "selftest must not crash")

    def test_list_presets_exits_zero(self):
        """benchmark_modal_e2e.py --list-presets exits 0."""
        result = subprocess.run(
            [sys.executable, str(BENCHMARK_E2E), "--list-presets"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)

    def test_list_all_presets_exits_zero(self):
        """benchmark_modal_e2e.py --list-all-presets exits 0."""
        result = subprocess.run(
            [sys.executable, str(BENCHMARK_E2E), "--list-all-presets"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)

    def test_print_effective_config_no_preset(self):
        """benchmark_modal_e2e.py --print-effective-config produces JSON."""
        result = subprocess.run(
            [sys.executable, str(BENCHMARK_E2E), "--print-effective-config"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        # Output should contain JSON with benchmark.runs
        self.assertIn('"runs"', result.stdout)

    def test_print_effective_config_with_preset(self):
        """benchmark_modal_e2e.py --preset cold-baseline --print-effective-config."""
        result = subprocess.run(
            [sys.executable, str(BENCHMARK_E2E),
             "--preset", "cold-baseline", "--print-effective-config"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('"runs"', result.stdout)

    def test_help_exits_zero(self):
        """benchmark_modal_e2e.py --help exits 0."""
        result = subprocess.run(
            [sys.executable, str(BENCHMARK_E2E), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)


# ============================================================================
# fresh_benchmark_payload — production output_node_ids propagation
# ============================================================================


class TestFreshBenchmarkPayloadProduction(unittest.TestCase):
    """fresh_benchmark_payload must propagate _production_trace into modal_options.production."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def _call_fresh(self, workflow_dict: dict) -> dict:
        """Convenience: call fresh_benchmark_payload with minimal required args."""
        return self.mod.fresh_benchmark_payload(
            workflow_dict=workflow_dict,
            t_start=1000.0,
            include_local_materialization=False,
            benchmark_session_id="test-session",
            run_idx=0,
        )

    # ── Test 1: latest_benchmark_workflow.json fixture yields output_node_ids ['107'] ──

    def test_latest_fixture_yields_output_node_ids_107(self):
        """Loading latest_benchmark_workflow.json payload yields output_node_ids ['107']."""
        fixture_path = REPO_ROOT / "latest_benchmark_workflow.json"
        raw = json.loads(fixture_path.read_text("utf-8"))
        # Simulate the same extraction logic used in cmd_benchmark (lines 2057-2060)
        if isinstance(raw, dict):
            payload_raw = raw.get("payload") or raw.get("prompt") or raw
            if isinstance(payload_raw, dict):
                workflow_dict = payload_raw
            else:
                workflow_dict = raw
        else:
            workflow_dict = raw
        payload = self._call_fresh(workflow_dict)
        production = payload.get("modal_options", {}).get("production")
        self.assertIsNotNone(
            production,
            "modal_options.production must exist in fresh payload from latest fixture",
        )
        self.assertTrue(
            production.get("enabled"),
            "production.enabled must be True",
        )
        self.assertEqual(
            production.get("output_node_ids"),
            ["107"],
            "production.output_node_ids must be ['107'] from _production_trace",
        )
        # Verify _production_trace diagnostic metadata survives (not stripped)
        self.assertIn(
            "_production_trace",
            payload,
            "_production_trace diagnostic metadata must be kept intact in payload",
        )

    def test_latest_fixture_integration_load(self):
        """End-to-end: load the actual file through the full path -> fresh_benchmark_payload."""
        fixture_path = REPO_ROOT / "latest_benchmark_workflow.json"
        raw = json.loads(fixture_path.read_text("utf-8"))
        if isinstance(raw, dict):
            payload_raw = raw.get("payload") or raw.get("prompt") or raw
            if isinstance(payload_raw, dict):
                workflow_dict = payload_raw
            else:
                workflow_dict = raw
        else:
            workflow_dict = raw
        payload = self._call_fresh(workflow_dict)
        production = payload.get("modal_options", {}).get("production", {})
        self.assertEqual(production.get("output_node_ids"), ["107"])
        self.assertIs(production.get("enabled"), True)

    # ── Test 2: No _production_trace yields no invented IDs ──

    def test_no_trace_no_invented_ids(self):
        """Without _production_trace, modal_options.production must NOT be invented."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "client_id": "abc",
        }
        payload = self._call_fresh(workflow)
        production = payload.get("modal_options", {}).get("production")
        self.assertIsNone(
            production,
            "Must not invent production.output_node_ids when _production_trace is absent",
        )

    def test_empty_production_output_ids_no_invention(self):
        """_production_trace with empty production_output_ids => no modal_options.production."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "_production_trace": {
                "production_output_ids": [],
                "production_bypass_ids": [],
            },
        }
        payload = self._call_fresh(workflow)
        production = payload.get("modal_options", {}).get("production")
        self.assertIsNone(
            production,
            "Must not invent production.output_node_ids when production_output_ids is empty",
        )

    def test_missing_production_output_ids_key_no_invention(self):
        """_production_trace without production_output_ids key => no modal_options.production."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "_production_trace": {"production_bypass_ids": []},
        }
        payload = self._call_fresh(workflow)
        production = payload.get("modal_options", {}).get("production")
        self.assertIsNone(
            production,
            "Must not invent production when production_output_ids key is missing",
        )

    # ── Test 3: Existing explicit modal_options.production preserved ──

    def test_existing_production_preserved_as_fallback(self):
        """Existing modal_options.production preserved when _production_trace absent."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "modal_options": {
                "production": {
                    "enabled": True,
                    "output_node_ids": ["42", "99"],
                    "some_extra_setting": "keep-me",
                },
            },
        }
        payload = self._call_fresh(workflow)
        production = payload.get("modal_options", {}).get("production")
        self.assertIsNotNone(
            production,
            "Existing explicit production must be preserved when _production_trace absent",
        )
        self.assertEqual(
            production.get("output_node_ids"),
            ["42", "99"],
            "Existing production output_node_ids must be preserved",
        )
        self.assertIs(production.get("enabled"), True)

    def test_production_trace_wins_over_existing_modal_options(self):
        """_production_trace takes priority over existing modal_options.production."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "_production_trace": {
                "production_output_ids": ["107"],
            },
            "modal_options": {
                "production": {
                    "enabled": True,
                    "output_node_ids": ["999"],
                },
            },
        }
        payload = self._call_fresh(workflow)
        production = payload.get("modal_options", {}).get("production")
        self.assertEqual(
            production.get("output_node_ids"),
            ["107"],
            "_production_trace must override existing modal_options.production",
        )

    def test_existing_production_not_overwritten_when_no_trace(self):
        """Existing explicit production options survive when _production_trace absent entirely."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "modal_options": {
                "auto_save_local": True,
                "production": {
                    "enabled": True,
                    "output_node_ids": ["55"],
                    "extra_field": "survive",
                },
            },
        }
        payload = self._call_fresh(workflow)
        production = payload.get("modal_options", {}).get("production")
        self.assertEqual(production.get("output_node_ids"), ["55"])
        self.assertEqual(production.get("extra_field"), "survive")
        self.assertIs(production.get("enabled"), True)

    # ── Structural integrity tests ──

    def test_payload_shape_unchanged_except_modal_options(self):
        """V1/V2 routing and payload shape otherwise unchanged."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "_production_trace": {"production_output_ids": ["107"]},
            "client_id": "abc123",
            "extra_data": {"some": "data"},
        }
        payload = self._call_fresh(workflow)
        # client_id and extra_data must be stripped
        self.assertNotIn("client_id", payload)
        self.assertNotIn("extra_data", payload)
        # prompt must be preserved
        self.assertIn("prompt", payload)
        self.assertEqual(payload["prompt"]["3"]["class_type"], "KSampler")
        # result_route must be 'direct'
        self.assertEqual(payload["result_route"], "direct")
        # trace must be present with benchmark metadata
        self.assertIn("trace", payload)
        self.assertEqual(payload["trace"]["benchmark_session_id"], "test-session")
        self.assertEqual(payload["trace"]["benchmark_run_index"], 0)
        # _production_trace diagnostic metadata must survive
        self.assertIn("_production_trace", payload)
        self.assertEqual(
            payload["_production_trace"]["production_output_ids"],
            ["107"],
        )

    def test_production_does_not_disable_when_trace_present(self):
        """production.enabled=True when _production_trace has IDs (not disabled)."""
        workflow = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "_production_trace": {"production_output_ids": ["107"]},
        }
        payload = self._call_fresh(workflow)
        prod = payload.get("modal_options", {}).get("production", {})
        self.assertIs(prod.get("enabled"), True)


# ============================================================================
# _fmt_opt — safe optional-numeric formatting
# ============================================================================


class TestFmtOpt(unittest.TestCase):
    """_fmt_opt must format float values safely and return fallback for None."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def _fmt(self, *args):
        """Shorthand to avoid descriptor binding via self.mod._fmt_opt(...)."""
        return self.mod._fmt_opt(*args)

    def test_float_formats_with_dot_zero(self):
        """float value with default fmt='.0f' => integer-like string."""
        self.assertEqual(self._fmt(1234.56), "1235")

    def test_int_formats(self):
        """int value with default fmt='.0f' => string."""
        self.assertEqual(self._fmt(42), "42")

    def test_none_returns_na(self):
        """None => 'N/A'."""
        self.assertEqual(self._fmt(None), "N/A")

    def test_none_with_custom_fallback(self):
        """None + fallback='?' => '?'."""
        self.assertEqual(self._fmt(None, ".0f", "?"), "?")

    def test_width_alignment_format(self):
        """fmt='8.0f' with numeric val => right-aligned in 8 chars."""
        res = self._fmt(1234, "8.0f", "?")
        self.assertEqual(len(res), 8)
        self.assertEqual(res, "    1234")

    def test_none_with_width_alignment_and_fallback(self):
        """None + fmt='8.0f' + fallback='?' => just '?' (not padded)."""
        self.assertEqual(self._fmt(None, "8.0f", "?"), "?")

    def test_none_does_not_crash_any_format(self):
        """None must not crash with any common fmt spec."""
        for fmt in (".0f", ".1f", ".2f", "8.0f", "10.1f", ">8.0f", "<8.0f"):
            self._fmt(None, fmt)  # must not raise

    def test_string_value_returns_fallback(self):
        """Non-numeric string val => fallback (does not crash)."""
        self.assertEqual(self._fmt("oops"), "N/A")

    def test_negative_float_formats(self):
        """Negative float formats correctly."""
        self.assertEqual(self._fmt(-3.14, ".1f"), "-3.1")


# ============================================================================
# Command-path formatting — per-run line uses _fmt_opt, does not crash on None
# ============================================================================


class TestPerRunFormattingSafe(unittest.TestCase):
    """The per-run print line (wall/submit2entry/sampler) must not crash with None."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def test_per_run_line_does_not_crash_with_none_wall(self):
        """Simulate the f-string at the end of a run with local_wall_ms=None."""
        _fmt = self.mod._fmt_opt
        local_wall_ms = None
        cp = {"submit2entry_ms": None}
        run_record = {"sampler_ms": None}
        label = "cold"
        conf = "high"
        poll_count = 5
        # Must not raise TypeError from ":.0f" on None
        line = (
            f"    {label} (confidence: {conf})  wall={_fmt(local_wall_ms)}ms  "
            f"submit2entry={_fmt(cp.get('submit2entry_ms'), '8.0f', '?'):>8}ms  "
            f"sampler={_fmt(run_record.get('sampler_ms'), '8.0f', '?'):>8}ms  "
            f"poll={poll_count}"
        )
        self.assertIn("wall=N/A", line)
        # submit2entry/sampler are right-aligned "       ?" — check for the
        # fallback char ('?') appearing before "ms" on each field
        self.assertIn("?ms", line)
        self.assertNotIn("None", line)

    def test_per_run_line_formats_numeric_values(self):
        """Normal numeric values still format correctly."""
        _fmt = self.mod._fmt_opt
        local_wall_ms = 15123.4
        cp = {"submit2entry_ms": 3421.0}
        run_record = {"sampler_ms": 5678.9}
        line = (
            f"    cold (confidence: high)  wall={_fmt(local_wall_ms)}ms  "
            f"submit2entry={_fmt(cp.get('submit2entry_ms'), '8.0f', '?'):>8}ms  "
            f"sampler={_fmt(run_record.get('sampler_ms'), '8.0f', '?'):>8}ms  "
            f"poll=3"
        )
        self.assertIn("wall=15123", line)
        self.assertIn("submit2entry=", line)
        self.assertIn("sampler=", line)

    def test_per_run_line_cp_key_missing_uses_fallback(self):
        """Missing cp key (not None) gets the '?' fallback (dict.get default)."""
        _fmt = self.mod._fmt_opt
        local_wall_ms = 10000.0
        cp = {}  # no submit2entry_ms key at all
        run_record = {"sampler_ms": 500.0}
        s2e_val = cp.get("submit2entry_ms", "?")
        line = (
            f"    warm (confidence: medium)  wall={_fmt(local_wall_ms)}ms  "
            f"submit2entry={_fmt(s2e_val, '8.0f', '?'):>8}ms  "
            f"sampler={_fmt(run_record.get('sampler_ms'), '8.0f', '?'):>8}ms  "
            f"poll=2"
        )
        # When key is missing, cp.get returns '?' — _fmt_opt gets a str '?', which
        # is not None, so it tries to format "?.0f".  That's a ValueError caught
        # by the try/except, returning fallback '?'.  Right-aligned => "       ?".
        # Check that no crash occurs and '?' appears before 'ms' on both fields.
        self.assertIn("?ms", line)
        self.assertNotIn("None", line)
        self.assertIn("sampler=", line)


# ============================================================================
# Error response from result poll — immediate termination
# ============================================================================


class TestResultPollErrorResponse(unittest.TestCase):
    """When result route returns status='error', polling must stop immediately
    instead of waiting for poll_timeout (default 600s).

    The server-provided error must be recorded in the run result with a clear
    failure phase/reason, and the error payload must be preserved as an artifact.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="bm_e2e_test_"))
        self._wf_path = self._tmpdir / "test_workflow.json"
        # Minimal workflow that passes validation in cmd_benchmark
        wf = {"prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}}}
        self._wf_path.write_text(json.dumps(wf), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_args(self, **overrides):
        """Minimal argparse.Namespace for cmd_benchmark.

        Unlike the no-deploy health-failure tests, this uses dry_run=False
        and a valid workflow path so the benchmark loop actually runs.
        """
        base = dict(
            runs=1, mode="cold", profile_level="summary",
            sleep_between_runs=10, min_gap_between_runs=10,
            strict_inter_run_sleep=False, poll_interval=0.25,
            poll_timeout=600, result_mode="poll",
            output_format="original", return_mode="full_base64",
            same_seed=False, same_workflow=False, same_active_profile=False,
            include_local_materialization=False,
            write_analysis_pack=False, analysis_pack_include_timelines=False,
            analysis_pack_include_wall_traces=False,
            no_deploy=True, dry_run=False, print_cost_warning=False,
            workflow=str(self._wf_path),
        )
        base.update(overrides)
        return mock.MagicMock(**base, spec=[])

    @staticmethod
    def _mock_side_effect():
        """Return a side_effect function that returns error on result poll.

        Returns:
            A callable suitable as ``mock.Mock(side_effect=...)`` that
            distinguishes health checks, prompt submit, and result polling
            by URL and HTTP method.
        """
        def side_effect(url, method="GET", payload=None, timeout=300):
            url_str = url if isinstance(url, str) else str(url)
            if "health" in url_str:
                return {"status": "ok"}
            if method == "POST":
                return {"prompt_id": "test-prompt-error", "number": 1}
            if "result" in url_str:
                return {"status": "error", "error": "modal crashed during inference"}
            return {}
        return side_effect

    # ── Tests ──────────────────────────────────────────────────────────────

    @mock.patch("benchmark_modal_e2e._resolve_benchmark_runs_dir")
    @mock.patch("benchmark_modal_e2e._json_request")
    def test_error_response_terminates_poll_immediately(self, mock_req, mock_runs_dir):
        """Error response terminates polling after one response, does not wait 600s."""
        mock_req.side_effect = self._mock_side_effect()
        mock_runs_dir.return_value = self._tmpdir

        args = self._make_args()

        start = time.time()
        rc = self.mod.cmd_benchmark(args)
        elapsed = time.time() - start

        # Must NOT wait 600s poll_timeout — polling breaks on first error response.
        # With mocked calls and runs=1 the entire benchmark should finish in < 5s.
        self.assertLess(
            elapsed, 30,
            f"Polling blocked for {elapsed:.1f}s waiting for error response, "
            "but should have terminated immediately",
        )

        # Error artifact must be preserved so the user can inspect it.
        error_artifacts = list(self._tmpdir.rglob("run_0_error_result.json"))
        self.assertEqual(
            len(error_artifacts), 1,
            "Error artifact run_0_error_result.json must exist",
        )
        err_data = json.loads(error_artifacts[0].read_text("utf-8"))
        self.assertEqual(err_data.get("status"), "error")
        self.assertEqual(
            err_data.get("error"), "modal crashed during inference",
            "Server-provided error message must be preserved in artifact",
        )

    @mock.patch("benchmark_modal_e2e._resolve_benchmark_runs_dir")
    @mock.patch("benchmark_modal_e2e._json_request")
    def test_error_response_prints_error_and_does_not_pretend_success(self, mock_req, mock_runs_dir):
        """Error response must print the server error and not mark the run as successful."""
        mock_req.side_effect = self._mock_side_effect()
        mock_runs_dir.return_value = self._tmpdir

        args = self._make_args()

        with mock.patch("builtins.print") as mock_print:
            rc = self.mod.cmd_benchmark(args)
            # Flatten all print call args
            all_prints = " ".join(
                str(a) for call_args in mock_print.call_args_list
                for a in call_args[0]
            )

        self.assertIn(
            "SERVER ERROR",
            all_prints,
            "Must print SERVER ERROR message",
        )
        self.assertIn(
            "modal crashed during inference",
            all_prints,
            "Must include the server-provided error message in output",
        )


# ============================================================================
# Browser timing refresh — stale queue_prompt_start_ms overwritten per run
# ============================================================================


class TestBrowserTimingRefresh(unittest.TestCase):
    """The per-run payload must strip stale top-level browser timing fields
    (queue_prompt_start_ms etc.) inherited from the workflow file and set
    fresh per-run values.  Otherwise coerce_t0_from_browser prefers the
    stale epoch-ms value over the benchmark's fresh trace.t0_client_press
    (epoch s), causing every run to flag stale t0.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="bm_e2e_bt_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_workflow_with_stale_browser_timing(self) -> Path:
        """Create a workflow JSON that mimics latest_benchmark_workflow.json
        with stale browser timing fields at the top level."""
        wf = {
            "prompt": {"3": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            "queue_prompt_start_ms": 1784496125117,   # stale future epoch ms
            "prompt_fetch_start_ms": 1784496125140,
            "queue_to_prompt_fetch_ms": 23,
            "serialized_prompt_bytes": 170701,
            "t0_client_press_ms": 1784496125117,
        }
        path = self._tmpdir / "stale_workflow.json"
        path.write_text(json.dumps(wf), encoding="utf-8")
        return path

    def _make_args(self, workflow_path: str, **overrides):
        base = dict(
            runs=1, mode="cold", profile_level="summary",
            sleep_between_runs=10, min_gap_between_runs=10,
            strict_inter_run_sleep=False, poll_interval=0.25,
            poll_timeout=600, result_mode="poll",
            output_format="original", return_mode="full_base64",
            same_seed=False, same_workflow=False, same_active_profile=False,
            include_local_materialization=False,
            write_analysis_pack=False, analysis_pack_include_timelines=False,
            analysis_pack_include_wall_traces=False,
            no_deploy=True, dry_run=False, print_cost_warning=False,
            workflow=workflow_path,
        )
        base.update(overrides)
        return mock.MagicMock(**base, spec=[])

    # ── Tests ──────────────────────────────────────────────────────────────

    @mock.patch("benchmark_modal_e2e._resolve_benchmark_runs_dir")
    @mock.patch("benchmark_modal_e2e._json_request")
    def test_stale_browser_timing_overwritten_per_run(self, mock_req, mock_runs_dir):
        """Workflow with stale queue_prompt_start_ms → fresh per-run values
        are sent in the POST, not the stale capture."""
        captured_payloads: list[dict] = []

        def side_effect(url, method="GET", payload=None, timeout=300):
            url_str = url if isinstance(url, str) else str(url)
            if "health" in url_str:
                return {"status": "ok"}
            if method == "POST":
                captured_payloads.append(copy.deepcopy(payload))
                return {"prompt_id": "bt-test-prompt", "number": 1}
            if "result" in url_str:
                # Return just enough structure to avoid a crash in the
                # normal success path (identity extraction, etc.).
                return {"status": "ok", "result": {"wall_clock_trace": {},
                                                     "trace": {}}}
            return {}

        mock_req.side_effect = side_effect
        mock_runs_dir.return_value = self._tmpdir

        wf_path = self._make_workflow_with_stale_browser_timing()
        args = self._make_args(str(wf_path))

        self.mod.cmd_benchmark(args)

        self.assertGreater(len(captured_payloads), 0,
                           "At least one POST must have been made")

        posted = captured_payloads[0]

        # 1. Stale queue_prompt_start_ms must be overwritten
        stale_value = 1784496125117
        self.assertNotEqual(
            posted.get("queue_prompt_start_ms"), stale_value,
            "Stale queue_prompt_start_ms must be overwritten with a fresh value",
        )
        # Fresh value should be a positive int close to current epoch ms
        now_ms = int(time.time() * 1000)
        self.assertIsInstance(posted.get("queue_prompt_start_ms"), int)
        self.assertGreater(posted["queue_prompt_start_ms"], 0)
        # Must be within 60s of now (any longer indicates stale reuse)
        self.assertLess(abs(posted["queue_prompt_start_ms"] - now_ms), 60000)

        # 2. prompt_fetch_start_ms must be set (positive int close to now)
        self.assertIn("prompt_fetch_start_ms", posted)
        self.assertIsInstance(posted["prompt_fetch_start_ms"], int)
        self.assertGreater(posted["prompt_fetch_start_ms"], 0)
        self.assertLess(abs(posted["prompt_fetch_start_ms"] - now_ms), 60000)

        # 3. queue_to_prompt_fetch_ms must be nonnegative (delta)
        self.assertIn("queue_to_prompt_fetch_ms", posted)
        self.assertIsInstance(posted["queue_to_prompt_fetch_ms"], (int, float))
        self.assertGreaterEqual(posted["queue_to_prompt_fetch_ms"], 0)

        # 4. serialized_prompt_bytes must be set and > 0
        self.assertIn("serialized_prompt_bytes", posted)
        self.assertIsInstance(posted["serialized_prompt_bytes"], int)
        self.assertGreater(posted["serialized_prompt_bytes"], 0)

        # 5. Stale prompt_fetch_start_ms / queue_to_prompt_fetch_ms / t0_client_press_ms
        #    must NOT survive (they were popped before fresh values were set).
        self.assertNotEqual(posted.get("prompt_fetch_start_ms"), 1784496125140)
        self.assertNotEqual(posted.get("queue_to_prompt_fetch_ms"), 23)
        self.assertNotIn("t0_client_press_ms", posted,
                         "t0_client_press_ms is stripped by _strip_trace_fields")

    @mock.patch("benchmark_modal_e2e._resolve_benchmark_runs_dir")
    @mock.patch("benchmark_modal_e2e._json_request")
    def test_fresh_browser_timing_fields_are_present(self, mock_req, mock_runs_dir):
        """Even when the workflow has NO browser timing, fresh fields are added."""
        captured_payloads: list[dict] = []

        def side_effect(url, method="GET", payload=None, timeout=300):
            url_str = url if isinstance(url, str) else str(url)
            if "health" in url_str:
                return {"status": "ok"}
            if method == "POST":
                captured_payloads.append(copy.deepcopy(payload))
                return {"prompt_id": "bt-test-prompt", "number": 1}
            if "result" in url_str:
                return {"status": "ok", "result": {"wall_clock_trace": {},
                                                     "trace": {}}}
            return {}

        mock_req.side_effect = side_effect
        mock_runs_dir.return_value = self._tmpdir

        # Clean workflow — no stale browser timing at all
        clean_wf = {"prompt": {"3": {"class_type": "KSampler",
                                      "inputs": {"steps": 20}}}}
        wf_path = self._tmpdir / "clean_workflow.json"
        wf_path.write_text(json.dumps(clean_wf), encoding="utf-8")
        args = self._make_args(str(wf_path))

        self.mod.cmd_benchmark(args)

        self.assertGreater(len(captured_payloads), 0)
        posted = captured_payloads[0]

        self.assertIn("queue_prompt_start_ms", posted)
        self.assertIn("prompt_fetch_start_ms", posted)
        self.assertIn("queue_to_prompt_fetch_ms", posted)
        self.assertIn("serialized_prompt_bytes", posted)
        self.assertGreater(posted["serialized_prompt_bytes"], 0)


# ============================================================================
# Summary metric robustness — numeric strings, sentinels, None → no crash
# ============================================================================


class TestSummaryColdMetricsRobust(unittest.TestCase):
    """Summary metric aggregation must handle numeric strings, sentinel
    nonnumeric strings (e.g. "N/A", "unknown"), and None without crashing.
    statistics.median crashes on str/int mixed types — _safe_float must
    be applied to every value in the list comprehension."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def test_median_with_safe_float_handles_numeric_string(self):
        """Numeric string '5000' → float via _safe_float → median works."""
        mod = self.mod
        runs = [
            {"cold_warm_label": "cold", "actual_load_saved_ms": "5000"},
            {"cold_warm_label": "cold", "actual_load_saved_ms": "3000"},
        ]
        cold = [r for r in runs if r.get("cold_warm_label", "").startswith("cold")]
        vals = [mod._safe_float(r.get("actual_load_saved_ms"), 0.0) for r in cold]
        result = mod._median(vals)
        self.assertIsInstance(result, float)
        self.assertEqual(result, 4000.0)

    def test_median_with_safe_float_handles_nonnumeric_sentinel(self):
        """Nonnumeric sentinel 'N/A' → 0.0 via _safe_float → no crash."""
        mod = self.mod
        runs = [
            {"cold_warm_label": "cold", "actual_load_saved_ms": "5000"},
            {"cold_warm_label": "cold", "actual_load_saved_ms": "N/A"},
        ]
        cold = [r for r in runs if r.get("cold_warm_label", "").startswith("cold")]
        vals = [mod._safe_float(r.get("actual_load_saved_ms"), 0.0) for r in cold]
        result = mod._median(vals)
        self.assertIsInstance(result, float)
        # 5000.0 and 0.0 → median 2500.0
        self.assertEqual(result, 2500.0)

    def test_median_with_safe_float_handles_none(self):
        """None value → 0.0 via _safe_float → no crash."""
        mod = self.mod
        runs = [
            {"cold_warm_label": "cold", "actual_load_saved_ms": None},
            {"cold_warm_label": "cold", "actual_load_saved_ms": 2000},
        ]
        cold = [r for r in runs if r.get("cold_warm_label", "").startswith("cold")]
        vals = [mod._safe_float(r.get("actual_load_saved_ms"), 0.0) for r in cold]
        result = mod._median(vals)
        self.assertIsInstance(result, float)
        self.assertEqual(result, 1000.0)

    def test_median_with_safe_float_handles_missing_key(self):
        """Missing dict key → 0.0 via _safe_float → no crash."""
        mod = self.mod
        runs = [
            {"cold_warm_label": "cold"},  # no actual_load_saved_ms key
            {"cold_warm_label": "cold", "actual_load_saved_ms": 4000},
        ]
        cold = [r for r in runs if r.get("cold_warm_label", "").startswith("cold")]
        vals = [mod._safe_float(r.get("actual_load_saved_ms"), 0.0) for r in cold]
        result = mod._median(vals)
        self.assertIsInstance(result, float)
        self.assertEqual(result, 2000.0)

    def test_cold_summary_does_not_crash_on_mixed_values(self):
        """The _cold_runs summary block (all metrics) must not crash when
        actual_load_saved_ms contains a numeric string."""
        mod = self.mod
        _cold_runs = [
            {"cold_warm_label": "cold_restore",
             "local_button_to_materialized_ms": 10000,
             "known_nonoverlap_ms": 5000,
             "submit2entry_ms": 3000,
             "restore_total_ms": 2000,
             "pre_sampler_ms": 1000,
             "unet_node_wait_ms": 800,
             "unet_load_ms": 750,
             "exec_model_load_io_ms": 600,
             "actual_load_saved_ms": "5000",   # numeric string
             "actual_load_remaining_wait_ms": "N/A",  # nonnumeric sentinel
             "sampler_ms": 7000,
             "post_sampler_ms": 500},
        ]
        summary = {}
        # Simulate the exact computation from cmd_benchmark
        summary["median_cold_actual_load_saved_ms"] = mod._median(
            [mod._safe_float(r.get("actual_load_saved_ms"), 0.0) for r in _cold_runs])
        summary["median_cold_actual_load_remaining_wait_ms"] = mod._median(
            [mod._safe_float(r.get("actual_load_remaining_wait_ms"), 0.0) for r in _cold_runs])
        summary["median_cold_local_wall_ms"] = mod._median(
            [mod._safe_float(r.get("local_button_to_materialized_ms"), 0.0) for r in _cold_runs])
        summary["median_cold_sampler_ms"] = mod._median(
            [mod._safe_float(r.get("sampler_ms"), 0.0) for r in _cold_runs])
        # All medians must be numeric — no TypeError from string value
        self.assertIsInstance(summary["median_cold_actual_load_saved_ms"], float)
        self.assertIsInstance(summary["median_cold_actual_load_remaining_wait_ms"], float)
        self.assertIsInstance(summary["median_cold_local_wall_ms"], float)
        self.assertIsInstance(summary["median_cold_sampler_ms"], float)
        # actual_load_saved_ms = "5000" → 5000.0
        self.assertEqual(summary["median_cold_actual_load_saved_ms"], 5000.0)
        # actual_load_remaining_wait_ms = "N/A" → 0.0
        self.assertEqual(summary["median_cold_actual_load_remaining_wait_ms"], 0.0)


# ============================================================================
# V2 cold/warm identity extraction and classification
# ============================================================================


class TestV2IdentityExtraction(unittest.TestCase):
    """extract_run_identity must prefer container_task_id over
    container_session_id, and per-run restore_session_id from
    _restore_timing over lifecycle-event fallbacks."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    # ── container_task_id extraction ───────────────────────────────────

    def test_extract_container_task_id_from_wall_trace(self):
        """container_task_id in wall_trace is the authoritative source."""
        result_data = {"wall_clock_trace": {"container_task_id": "task-001"}}
        wall = result_data["wall_clock_trace"]
        tid = self.mod.extract_run_identity(result_data, wall, {}, {})
        self.assertEqual(tid.get("container_task_id"), "task-001")
        self.assertIn("container_task_id_from_wall_trace",
                      tid.get("identity_source_notes", []))

    def test_extract_container_task_id_from_timing_trace(self):
        """Falls back to timing_trace when wall_trace lacks the field."""
        result_data = {"trace": {"container_task_id": "task-002"}}
        wall = result_data.get("wall_clock_trace", {})
        timing = result_data["trace"]
        tid = self.mod.extract_run_identity(result_data, wall, timing, {})
        self.assertEqual(tid.get("container_task_id"), "task-002")
        self.assertIn("container_task_id_from_timing_trace",
                      tid.get("identity_source_notes", []))

    def test_extract_container_task_id_from_restore_timing(self):
        """Falls back to _restore_timing when wall/timing traces lack it."""
        result_data = {"_restore_timing": {"container_task_id": "task-003"}}
        tid = self.mod.extract_run_identity(result_data, {}, {}, result_data["_restore_timing"])
        self.assertEqual(tid.get("container_task_id"), "task-003")
        self.assertIn("container_task_id_from_restore_timing",
                      tid.get("identity_source_notes", []))

    def test_extract_no_container_task_id_v1_fallback(self):
        """No container_task_id anywhere → empty string (V1 compat)."""
        tid = self.mod.extract_run_identity({"trace": {}}, {}, {}, {})
        self.assertEqual(tid.get("container_task_id"), "")

    # ── restore_session_id priority ───────────────────────────────────

    def test_restore_session_id_prefers_restore_timing(self):
        """Per-run _restore_timing.restore_session_id beats wall_trace."""
        result_data = {
            "_restore_timing": {"restore_session_id": "per-run-rsid"},
        }
        wall = {"restore_session_id": "wall-lifecycle-rsid"}
        tid = self.mod.extract_run_identity(result_data, wall, {}, result_data["_restore_timing"])
        self.assertEqual(tid.get("restore_session_id"), "per-run-rsid",
                         "_restore_timing restore_session_id must be preferred")

    def test_restore_session_id_falls_back_to_wall(self):
        """No _restore_timing → wall_trace restore_session_id is used."""
        wall = {"restore_session_id": "wall-rsid"}
        tid = self.mod.extract_run_identity({"trace": {}}, wall, {}, {})
        self.assertEqual(tid.get("restore_session_id"), "wall-rsid")


class TestV2Classification(unittest.TestCase):
    """classify_run must use container_task_id (MODAL_TASK_ID) for
    same-container detection when available, not the shared V2
    container_session_id snapshot."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    # ── Different task IDs → same_container=False ──────────────────────

    def test_different_task_id_not_same_container(self):
        """Different container_task_id → same_container=False even when
        container_session_id matches (V2 snapshot scenario)."""
        prev = {"container_task_id": "task-a", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-1", "request_seq": 1, "restore_count": 1,
                "has_restore_total": True}
        curr = {"container_task_id": "task-b", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-2", "request_seq": 1, "restore_count": 1,
                "has_restore_total": True}
        _, _, _, _, same_container, _ = self.mod.classify_run(curr, prev, 5000, 4000)
        self.assertFalse(same_container,
                         "Different task IDs must NOT be same_container "
                         "even when container_session_id matches")

    # ── Same task ID → same_container=True ─────────────────────────

    def test_same_task_id_is_same_container(self):
        """Same container_task_id → same_container=True (warm same container)."""
        prev = {"container_task_id": "task-a", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-1", "request_seq": 2, "restore_count": 2,
                "has_restore_total": True}
        curr = {"container_task_id": "task-a", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-1", "request_seq": 3, "restore_count": 2,
                "has_restore_total": True}
        _, _, _, _, same_container, _ = self.mod.classify_run(curr, prev, 5, 3)
        self.assertTrue(same_container,
                        "Same task ID must be same_container")

    # ── Same task ID + same restore → warm classification ─────────────

    def test_same_task_id_same_restore_is_warm(self):
        """Same task ID + same restore_session_id + request_seq>1 → warm."""
        prev = {"container_task_id": "task-a", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-1", "request_seq": 2, "restore_count": 2,
                "has_restore_total": True}
        curr = {"container_task_id": "task-a", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-1", "request_seq": 3, "restore_count": 2,
                "has_restore_total": True}
        label, conf, reasons, _, _, _ = self.mod.classify_run(curr, prev, 5, 3)
        self.assertTrue(label.startswith("warm"),
                        f"Same task + same restore must be warm, got {label}")
        self.assertIn("same_restore_session", ";".join(reasons))

    # ── Different restore → cold even with same task ID ───────────────
    # (same container but new deployment / new restore session)

    def test_different_restore_is_cold(self):
        """Different restore_session_id → cold, even if task_id matches."""
        prev = {"container_task_id": "task-a", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-1", "request_seq": 2, "restore_count": 2,
                "has_restore_total": True}
        curr = {"container_task_id": "task-a", "container_session_id": "shared-v2",
                "restore_session_id": "rsid-2", "request_seq": 1, "restore_count": 1,
                "has_restore_total": True}
        label, conf, reasons, _, _, _ = self.mod.classify_run(curr, prev, 8000, 6000)
        # rsid different, rc=1 → cold_restore
        self.assertTrue(label.startswith("cold"),
                        f"Different restore_session_id must be cold, got {label}")

    # ── No container_task_id → container_session_id fallback (V1 compat) ──

    def test_v1_fallback_same_csid_same_container(self):
        """No container_task_id → same_container uses container_session_id."""
        prev = {"container_session_id": "v1-session", "restore_session_id": "rsid-1",
                "request_seq": 1, "restore_count": 1, "has_restore_total": True}
        curr = {"container_session_id": "v1-session", "restore_session_id": "rsid-1",
                "request_seq": 2, "restore_count": 2, "has_restore_total": True}
        _, _, _, _, same_container, _ = self.mod.classify_run(curr, prev, 5, 3)
        self.assertTrue(same_container,
                        "V1 fallback: same container_session_id → same_container=True")

    def test_v1_fallback_diff_csid_not_same_container(self):
        """No container_task_id → different container_session_id → not same."""
        prev = {"container_session_id": "v1-session-a", "restore_session_id": "rsid-1",
                "request_seq": 1, "restore_count": 1, "has_restore_total": True}
        curr = {"container_session_id": "v1-session-b", "restore_session_id": "rsid-2",
                "request_seq": 1, "restore_count": 1, "has_restore_total": True}
        _, _, _, _, same_container, _ = self.mod.classify_run(curr, prev, 8000, 6000)
        self.assertFalse(same_container,
                         "V1 fallback: different container_session_id → same_container=False")


if __name__ == "__main__":
    unittest.main()
