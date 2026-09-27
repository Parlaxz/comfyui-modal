"""Unit tests for _run_benchmark.py helper functions.

Covers cold-run validation, output validation, and result summary logic.
"""

import base64
import hashlib
import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from workflow_metadata import prompt_sha256

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SCRIPT = REPO_ROOT / "_run_benchmark.py"


# ============================================================================
# Test helpers: produce minimal valid/malformed result dicts
# ============================================================================

def _make_result(
    *,
    error: str | None = None,
    has_trace: bool = True,
    has_restore: bool = True,
    has_outputs: bool = True,
    output_count: int = 1,
    output_bytes: int = 500_000,
    trace_stages: dict | None = None,
    restore_timing: dict | None = None,
) -> dict:
    """Build a realistic Modal result dict for testing helpers.

    The output data is sized to *output_bytes* (total across all images).
    This lets callers precisely control whether validation passes or fails
    the ``_MIN_OUTPUT_BYTES`` (1024) threshold.
    """
    result: dict = {}
    if error:
        result["error"] = error
        return result

    # trace
    if has_trace:
        result["trace"] = {
            "stages": trace_stages or {
                "t3_modal_entry": 1_700_000_000.0,
                "t9_modal_return": 1_700_000_010.0,
            },
            "deltas_ms": {
                "remote_total": 10_000,
                "t3b_to_t8": 8_000,
                "inference_total": 7_000,
                "clip_load": 500,
                "sampler": 4_000,
                "graph_overhead": 200,
            },
        }
    # restore_timing
    if has_restore:
        result["_restore_timing"] = restore_timing or {
            "restore_start_unix_s": 1_700_000_000.0,
            "restore_end_unix_s": 1_700_000_005.0,
            "restore_total_ms": 5_000.0,
            "warmup_preload_ms": 2_000.0,
            "warmup_wf_ms": 1_000.0,
            "preload_mode": "split",
            "sage_mode": "baked_cuda",
            "wce_enabled": True,
            "wce_source": "env",
            "warmup_direct_clip_encode_ms": 300.0,
        }
    # outputs: each image gets output_bytes // output_count bytes of data
    if has_outputs:
        outputs = {}
        bytes_per_image = output_bytes // max(output_count, 1)
        raw_data = os.urandom(max(bytes_per_image, 0))
        data_b64 = base64.b64encode(raw_data).decode("ascii")
        for i in range(output_count):
            nid = str(i + 1)
            outputs[nid] = {
                "images": [{"data": data_b64, "filename": f"img_{i}.png"}],
            }
        result["outputs"] = outputs

    # return payload info
    result["_return_payload_info"] = {
        "image_count": output_count,
        "b64_bytes": output_bytes,
        "return_mode": "full_base64",
    }
    return result


def _make_workflow(*, with_load_image: bool = False, with_unet: bool = True,
                   with_clip: bool = True, with_vae: bool = True) -> dict:
    """Build a minimal workflow dict."""
    workflow = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors"}},
        "2": {"class_type": "CLIPLoader",   "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader",    "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "KSampler",     "inputs": {"seed": 42, "steps": 20, "cfg": 3.5}},
    }
    if with_load_image:
        workflow["5"] = {"class_type": "LoadImage", "inputs": {"image": "input.png"}}
    return workflow


def _make_artifact(
    *,
    run_index: int = 1,
    validation_status: str = "passed",
    has_waterfall: bool = True,
    has_return_payload: bool = True,
    waterfall: dict | None = None,
    accepted_cold_run: bool = True,
) -> dict:
    """Build an enriched artifact dict as produced by the main benchmark loop.

    ``summarize_results`` expects ``validation_status``, ``error``,
    ``accepted_cold_run``, and ``cold_validation_status`` at the top level.
    """
    wf = waterfall or {
        "benchmark_wall_ms": 15_000.0,
        "workflow_load_ms": 2.0,
        "platform_restore_ms": 3_500.0,
        "app_restore_ms": 5_000.0,
        "remote_execute_ms": 5_000.0,
        "modal_return_to_client_ms": 500.0,
        "local_postprocess_ms": 100.0,
        "app_controlled_ms": 10_000.0,
        "known_cold_ms": 13_500.0,
        "untracked_after_platform_ms": 1_500.0,
    }
    artifact: dict = {
        "benchmark_set_id": "20260606_120000",
        "config_label": "default",
        "code_version": "2.14.1",
        "run_index": run_index,
        "run": f"RUN-{run_index}",
        "timestamp": "20260606_120000",
        "wall_clock_s": 15.0,
        "validation_status": validation_status,
        "cold_validation_status": "valid_cold" if validation_status == "passed" else "invalid_warm_reuse",
        "accepted_cold_run": accepted_cold_run,
        "error": None,
        "missing_fields": [],
        "validation_errors": [],
        "workflow_hash": "abc123",
        "output_count": 1,
        "output_bytes": 500_000,
    }
    if has_waterfall:
        artifact["waterfall"] = wf
    if has_return_payload:
        artifact["return_payload_info"] = {
            "image_count": 1,
            "b64_bytes": 500_000,
            "return_mode": "full_base64",
        }
    return artifact


def _make_artifacts(count: int = 3) -> list[dict]:
    """Return *count* valid artifact dicts."""
    return [_make_artifact(run_index=i + 1) for i in range(count)]


# ============================================================================
# Tests
# ============================================================================

class TestRunBenchmarkImports(unittest.TestCase):
    """Verify the helper functions are importable from _run_benchmark."""

    def test_module_imports(self):
        """The module can be imported and has expected function names."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.assertIsNotNone(spec, f"Could not find spec for {BENCHMARK_SCRIPT}")
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:
            self.fail(f"Module {BENCHMARK_SCRIPT} failed to import: {exc}")

        # Expected helpers
        for name in (
            "load_workflow",
            "build_input_images",
            "extract_warmup_profile",
            "compute_waterfall",
            "validate_cold_run",
            "summarize_results",
            "build_benchmark_set_id",
            "get_config_label",
            "get_code_version",
            "build_bridge_trace",
            "classify_cold_run",
            "validate_output_payload",
            "summarize_benchmark_set",
            "label_derived_clock_fields",
            "build_matrix_row",
            "check_workflow_node_types",
            "_build_preflight_failure_artifact",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(mod, name), f"_run_benchmark missing {name}")


class TestLoadWorkflow(unittest.TestCase):
    """load_workflow() edge cases."""

    def setUp(self):
        self.workflow_file = REPO_ROOT / "latest_benchmark_workflow.json"
        if not self.workflow_file.is_file():
            self.skipTest(f"Workflow file not found: {self.workflow_file}")

    def test_load_workflow_returns_dict(self):
        """load_workflow returns a dict."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        workflow = mod.load_workflow()
        self.assertIsInstance(workflow, dict)
        self.assertGreater(len(workflow), 0)

    def test_load_workflow_extracts_prompt_from_snapshot(self):
        """If the JSON has a 'payload' key, its 'prompt' sub-key becomes the workflow."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        snapshot = {
            "captured_at": time.time(),
            "workflow_hash": "abc123",
            "payload": {"prompt": {"1": {"class_type": "KSampler"}}},
        }
        workflow = mod.load_workflow(json_payload=snapshot)
        self.assertEqual(workflow, {"1": {"class_type": "KSampler"}})

    def test_load_workflow_direct_prompt(self):
        """If passed a prompt dict directly (no payload wrapper)."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        workflow = mod.load_workflow(json_payload={"prompt": {"1": {"class_type": "KSampler"}}})
        self.assertEqual(workflow, {"1": {"class_type": "KSampler"}})


class TestBuildInputImages(unittest.TestCase):
    """build_input_images() creates dummy black images for LoadImage nodes."""

    def test_no_load_image_nodes(self):
        """Workflow with no LoadImage nodes returns empty dict."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        wf = _make_workflow(with_load_image=False)
        images = mod.build_input_images(wf)
        self.assertEqual(images, {})

    def test_load_image_node_creates_dummy(self):
        """LoadImage node produces a base64-encoded black PNG."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        wf = _make_workflow(with_load_image=True)
        images = mod.build_input_images(wf)
        self.assertIn("input.png", images)
        self.assertIsInstance(images["input.png"], str)
        self.assertGreater(len(images["input.png"]), 100)  # b64 > raw PNG size
        # Verify it's valid base64 that decodes to a PNG
        import base64
        decoded = base64.b64decode(images["input.png"])
        self.assertTrue(decoded.startswith(b"\x89PNG"), "Not a valid PNG header")


class TestExtractWarmupProfile(unittest.TestCase):
    """extract_warmup_profile() extracts UNET/CLIP/VAE from workflow."""

    def test_extracts_unet_clip_vae(self):
        """Returns dict with unet, clip1, clip2, vae, clip_type."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        wf = _make_workflow(with_unet=True, with_clip=True, with_vae=True)
        profile, models = mod.extract_warmup_profile(wf)
        self.assertIn("unet", profile)
        self.assertIn("clip1", profile)
        self.assertIn("clip2", profile)
        self.assertIn("vae", profile)
        self.assertIn("clip_type", profile)
        self.assertEqual(profile["unet"], "flux1-dev.safetensors")

    def test_no_models_returns_empty_values(self):
        """Workflow with no loader nodes returns profile with empty strings."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        profile, models = mod.extract_warmup_profile(wf)
        self.assertEqual(profile.get("unet", ""), "")
        self.assertEqual(profile.get("clip1", ""), "")
        self.assertEqual(profile.get("clip2", ""), "")


class TestValidateColdRun(unittest.TestCase):
    """validate_cold_run() checks result validity and returns validation dict."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_valid_result_passes(self):
        """All fields present → validation_status 'passed'."""
        result = _make_result()
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["validation_status"], "passed")
        self.assertIn("output_count", outcome)
        self.assertIn("output_bytes", outcome)
        self.assertGreater(outcome["output_count"], 0)
        self.assertGreater(outcome["output_bytes"], 0)

    def test_missing_trace_fails(self):
        """No trace → validation_status 'failed' with reason."""
        result = _make_result(has_trace=False)
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["validation_status"], "failed")
        self.assertIn("trace", outcome.get("missing_fields", []))

    def test_missing_restore_timing_fails(self):
        """No _restore_timing → validation_status 'failed'."""
        result = _make_result(has_restore=False)
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["validation_status"], "failed")
        self.assertIn("_restore_timing", outcome.get("missing_fields", []))

    def test_missing_outputs_fails(self):
        """No outputs → validation_status 'failed'."""
        result = _make_result(has_outputs=False)
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["validation_status"], "failed")
        self.assertIn("outputs", outcome.get("missing_fields", []))

    def test_error_in_result_fails(self):
        """Result has 'error' key → validation_status 'failed'."""
        result = _make_result(error="timeout")
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["validation_status"], "failed")
        self.assertEqual(outcome.get("error"), "timeout")

    def test_zero_output_bytes_fails(self):
        """Output with zero bytes → validation_status 'failed'."""
        result = _make_result(output_bytes=0)
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["validation_status"], "failed")
        self.assertIn("output_bytes", outcome.get("validation_errors", []))

    def test_tiny_output_fails_threshold(self):
        """Very small output bytes (less than 1024) fails validation."""
        result = _make_result(output_bytes=100)
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["validation_status"], "failed")
        self.assertIn("output_bytes", outcome.get("validation_errors", []))

    def test_detects_output_count(self):
        """Counts output images correctly."""
        result = _make_result(output_count=3, output_bytes=1_500_000)
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome["output_count"], 3)
        self.assertGreater(outcome["output_bytes"], 1_000_000)

    def test_includes_lifecycle_markers(self):
        """Outcome dict includes lifecycle markers like restore_total_ms."""
        result = _make_result()
        wf = _make_workflow()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertIn("restore_total_ms", outcome)
        self.assertIsInstance(outcome.get("restore_total_ms"), (int, float))
        self.assertIn("preload_mode", outcome)
        self.assertIn("sage_mode", outcome)

    def test_includes_workflow_hash(self):
        """Outcome includes workflow_hash derived from the workflow."""
        wf = _make_workflow()
        import importlib
        workflow_meta = importlib.import_module("workflow_metadata")
        expected_hash = workflow_meta.prompt_sha256(wf)
        result = _make_result()
        outcome = self.mod.validate_cold_run(result, wf)
        self.assertEqual(outcome.get("workflow_hash"), expected_hash)


class TestComputeWaterfall(unittest.TestCase):
    """compute_waterfall() returns correct timing breakdown."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_basic_waterfall_structure(self):
        """Returns dict with expected keys."""
        # Simulate timestamps
        t0 = 100.0
        t1 = 100.001   # 1ms for workflow load
        t2 = 100.002   # 1ms for pre-modal work
        t3 = 115.0     # 13s modal call
        t4 = 115.010   # 10ms to parse result
        t5 = 115.020   # 10ms local postprocess
        result = _make_result()

        wf = self.mod.compute_waterfall(t0, t1, t2, t3, t4, t5, result)

        required_keys = {
            "benchmark_wall_ms",
            "workflow_load_ms",
            "platform_restore_ms",
            "app_restore_ms",
            "remote_execute_ms",
            "modal_return_to_client_ms",
            "local_postprocess_ms",
            "app_controlled_ms",
            "known_cold_ms",
            "untracked_after_platform_ms",
        }
        self.assertTrue(required_keys.issubset(wf.keys()), f"Missing keys: {required_keys - wf.keys()}")

    def test_workflow_load_ms(self):
        """workflow_load_ms = (t1 - t0) * 1000."""
        wf = self.mod.compute_waterfall(100.0, 100.005, 100.006, 110.0, 110.01, 110.02, _make_result())
        self.assertAlmostEqual(wf["workflow_load_ms"], 5.0, places=1)

    def test_modal_call_wall(self):
        """modal_call_wall_ms = (t3 - t2) * 1000."""
        wf = self.mod.compute_waterfall(100.0, 100.001, 100.002, 115.0, 115.01, 115.02, _make_result())
        self.assertAlmostEqual(wf["modal_call_wall_ms"], 14998.0, delta=2)

    def test_no_remote_exec_end_fallback(self):
        """When t9_modal_return missing, remote_execute_ms is 0."""
        result = _make_result(trace_stages={"t3_modal_entry": 1_700_000_000.0})
        wf = self.mod.compute_waterfall(100.0, 100.001, 100.002, 115.0, 115.01, 115.02, result)
        self.assertEqual(wf["remote_execute_ms"], 0.0)

    def test_no_app_restore_timestamps(self):
        """When restore_start_unix_s missing, platform_restore_ms and app_restore_ms default to 0."""
        result = _make_result(restore_timing={"restore_total_ms": None})
        wf = self.mod.compute_waterfall(100.0, 100.001, 100.002, 115.0, 115.01, 115.02, result)
        self.assertEqual(wf["platform_restore_ms"], 0.0)
        self.assertEqual(wf["app_restore_ms"], 0.0)

    def test_app_controlled_ms(self):
        """app_controlled_ms = app_restore_ms + remote_execute_ms."""
        wf = self.mod.compute_waterfall(100.0, 100.001, 100.002, 115.0, 115.01, 115.02, _make_result(
            restore_timing={
                "restore_start_unix_s": 100.002,
                "restore_end_unix_s": 105.0,
                "restore_total_ms": 4_998.0,
            },
        ))
        self.assertAlmostEqual(wf["app_controlled_ms"], wf["app_restore_ms"] + wf["remote_execute_ms"])


class TestSummarizeResults(unittest.TestCase):
    """summarize_results() produces aggregate statistics."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_summary_includes_run_count(self):
        """Summary total_runs equals len(results)."""
        results = _make_artifacts(3)
        summary = self.mod.summarize_results(results)
        self.assertEqual(summary["total_runs"], 3)
        self.assertEqual(summary["valid_runs"], 3)

    def test_summary_counts_invalid_runs(self):
        """Invalid results are counted separately."""
        results = _make_artifacts(2)
        results.append(_make_artifact(run_index=3, validation_status="failed"))
        summary = self.mod.summarize_results(results)
        self.assertEqual(summary["total_runs"], 3)
        self.assertEqual(summary["valid_runs"], 2)

    def test_summary_includes_avg_waterfall(self):
        """Summary includes avg_* fields for waterfall metrics."""
        results = _make_artifacts(3)
        summary = self.mod.summarize_results(results)
        for key in ("avg_benchmark_wall_ms", "avg_app_restore_ms", "avg_remote_execute_ms"):
            with self.subTest(key=key):
                self.assertIn(key, summary)

    def test_summary_returns_hydrated_summary_list(self):
        """Summary includes a 'runs' list with per-run enrichment."""
        results = _make_artifacts(3)
        summary = self.mod.summarize_results(results)
        self.assertIn("runs", summary)
        self.assertEqual(len(summary["runs"]), 3)

    def test_summary_handles_empty_list(self):
        """Empty results list returns safe defaults."""
        summary = self.mod.summarize_results([])
        self.assertEqual(summary["total_runs"], 0)
        self.assertEqual(summary["valid_runs"], 0)


class TestBuildBenchmarkSetId(unittest.TestCase):
    """build_benchmark_set_id() returns a unique, deterministic-like ID."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_returns_string(self):
        """Returns a non-empty string."""
        bid = self.mod.build_benchmark_set_id()
        self.assertIsInstance(bid, str)
        self.assertGreater(len(bid), 0)

    def test_is_timestamp_based(self):
        """Starts with YYYYMMDD prefix."""
        bid = self.mod.build_benchmark_set_id()
        # Should be timestamp-based: e.g. "20260606_..."
        import re
        self.assertRegex(bid, r"^\d{8}_")


class TestGetConfigLabel(unittest.TestCase):
    """get_config_label() reads from env or returns default."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_default_label(self):
        """Returns 'default' when env not set."""
        with mock.patch.dict("os.environ", {}, clear=True):
            label = self.mod.get_config_label()
            self.assertEqual(label, "default")

    def test_env_var(self):
        """Reads COMFYMODAL_CONFIG_LABEL from env."""
        with mock.patch.dict("os.environ", {"COMFYMODAL_CONFIG_LABEL": "test-config"}):
            label = self.mod.get_config_label()
            self.assertEqual(label, "test-config")


class TestGetCodeVersion(unittest.TestCase):
    """get_code_version() reads comfyapp version."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_returns_string(self):
        """Returns a non-empty string or 'unknown'."""
        version = self.mod.get_code_version()
        self.assertIsInstance(version, str)


class TestBridgeFaithfulValidation(unittest.TestCase):
    """Test bridge-style cold classification and output validation helpers."""

    def test_classify_cold_run_rejects_missing_restore_markers(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.classify_cold_run({}, {"stages": {"t3_modal_entry": 1.0}})

        self.assertEqual(result["validation_status"], "invalid_warm_reuse")
        self.assertFalse(result["is_valid_cold"])

    def test_classify_cold_run_accepts_restore_and_trace_markers(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        restore = {
            "restore_total_ms": 5000.0,
            "restore_start_unix_s": 10.0,
            "restore_end_unix_s": 15.0,
        }
        trace = {"stages": {"t3_modal_entry": 15.5}}

        result = mod.classify_cold_run(restore, trace)

        self.assertEqual(result["validation_status"], "valid_cold")
        self.assertTrue(result["is_valid_cold"])

    def test_classify_cold_run_rejects_stale_restore_markers(self):
        """Reject a run where restore_end_unix_s is far in the past relative to
        t3_modal_entry — that indicates stale _restore_timing from warm reuse."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # restore ended 120s before t3_modal_entry — stale, warm reuse
        restore = {
            "restore_total_ms": 7000.0,
            "restore_start_unix_s": 80.0,
            "restore_end_unix_s": 87.0,
        }
        trace = {"stages": {"t3_modal_entry": 207.0}}

        result = mod.classify_cold_run(restore, trace)

        self.assertEqual(result["validation_status"], "invalid_warm_reuse")
        self.assertFalse(result["is_valid_cold"])

    def test_validate_output_payload_rejects_blank_filename(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.validate_output_payload({"images": [{"filename": "", "data": "abc"}], "videos": []})

        self.assertFalse(result["ok"])
        self.assertEqual(result["invalid_entries"], 1)

    def test_validate_output_payload_rejects_empty_payload(self):
        """Empty images/videos with no expected_count must be rejected."""
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.validate_output_payload({"images": [], "videos": []})

        self.assertFalse(result["ok"])
        self.assertEqual(result["output_count"], 0)
        self.assertEqual(result["invalid_entries"], 0)

    def test_validate_output_payload_distinguishes_b64_chars_from_decoded_bytes(self):
        import importlib, base64
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # 10 raw bytes → base64 encodes to 16 chars (with padding)
        raw = b"\x00" * 10
        b64_data = base64.b64encode(raw).decode("ascii")  # "AAAAAAAAAAAAAA==" → 16 chars

        result = mod.validate_output_payload({
            "images": [{"filename": "out.png", "data": b64_data}],
            "videos": [],
        })

        self.assertTrue(result["ok"])
        self.assertEqual(result["output_b64_chars"], 16)   # base64 string length
        self.assertEqual(result["output_bytes"], 10)        # decoded byte count
        self.assertNotEqual(result["output_b64_chars"], result["output_bytes"])  # verify distinction


class TestBuildBridgeTrace(unittest.TestCase):
    """build_bridge_trace() returns a dict matching the bridge timing seed."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_returns_dict_with_expected_seed_keys(self):
        """Returns dict containing all four bridge seed fields."""
        trace = self.mod.build_bridge_trace(prompt_id="test-prompt")
        self.assertIsInstance(trace, dict)
        for key in ("prompt_id", "t0_client_press", "t1_local_recv", "t2_local_dispatch"):
            with self.subTest(key=key):
                self.assertIn(key, trace)

    def test_prompt_id_is_set(self):
        """The prompt_id passed to build_bridge_trace appears in the result."""
        trace = self.mod.build_bridge_trace(prompt_id="my-benchmark-run")
        self.assertEqual(trace["prompt_id"], "my-benchmark-run")

    def test_timestamps_are_recent_positives(self):
        """Timestamp fields are positive floats close to time.time()."""
        before = time.time()
        trace = self.mod.build_bridge_trace()
        after = time.time()
        for key in ("t0_client_press", "t1_local_recv", "t2_local_dispatch"):
            with self.subTest(key=key):
                val = trace[key]
                self.assertIsInstance(val, float)
                # Should be between the before and after snapshots
                self.assertGreaterEqual(val, before)
                self.assertLessEqual(val, after)

    def test_default_prompt_id_is_empty(self):
        """When no prompt_id given, defaults to empty string."""
        trace = self.mod.build_bridge_trace()
        self.assertEqual(trace["prompt_id"], "")


class TestWorkflowNodeTypePreflight(unittest.TestCase):
    """Preflight check for workflow class_type compatibility with remote runtime."""

    def setUp(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    # ── check_workflow_node_types ─────────────────────────────────────

    def test_detects_missing_class_types(self):
        workflow = {
            "1": {"class_type": "KSampler"},
            "2": {"class_type": "VAEDecode"},
            "3": {"class_type": "CustomNodeX"},
        }
        remote_types = {"KSampler", "VAEDecode", "CLIPLoader"}

        result = self.mod.check_workflow_node_types(workflow, remote_types)

        self.assertFalse(result["compatible"])
        self.assertIn("CustomNodeX", result["missing_types"])
        self.assertNotIn("KSampler", result["missing_types"])
        self.assertEqual(result["unique_class_types"], 3)

    def test_passes_when_all_types_present(self):
        workflow = {
            "1": {"class_type": "KSampler"},
            "2": {"class_type": "VAEDecode"},
        }
        remote_types = {"KSampler", "VAEDecode", "CLIPLoader"}

        result = self.mod.check_workflow_node_types(workflow, remote_types)

        self.assertTrue(result["compatible"])
        self.assertEqual(result["missing_types"], [])

    def test_empty_workflow_passes(self):
        result = self.mod.check_workflow_node_types({}, {"KSampler"})
        self.assertTrue(result["compatible"])
        self.assertEqual(result["missing_types"], [])

    def test_rejects_workflow_with_multiple_missing_types(self):
        workflow = {
            "1": {"class_type": "KSampler"},
            "2": {"class_type": "MissingA"},
            "3": {"class_type": "MissingB"},
        }
        remote_types = {"KSampler", "VAEDecode"}

        result = self.mod.check_workflow_node_types(workflow, remote_types)

        self.assertFalse(result["compatible"])
        self.assertCountEqual(result["missing_types"], ["MissingA", "MissingB"])
        self.assertEqual(result["total_remote_types"], 2)

    def test_skips_non_dict_or_missing_class_type_entries(self):
        """Entries without a valid class_type should be silently ignored."""
        workflow = {
            "1": {"class_type": "KSampler"},
            "2": "not_a_dict",
            "3": {"not_class_type": "VAEDecode"},
        }
        remote_types = {"KSampler"}

        result = self.mod.check_workflow_node_types(workflow, remote_types)

        self.assertTrue(result["compatible"])
        self.assertEqual(result["unique_class_types"], 1)

    def test_counts_unique_class_types_not_instances(self):
        """Duplicate class_type values count as one, not per-instance."""
        workflow = {
            "1": {"class_type": "KSampler"},
            "2": {"class_type": "KSampler"},
            "3": {"class_type": "VAEDecode"},
            "4": {"class_type": "KSampler"},
        }
        remote_types = {"KSampler", "VAEDecode"}

        result = self.mod.check_workflow_node_types(workflow, remote_types)

        self.assertTrue(result["compatible"])
        self.assertEqual(result["unique_class_types"], 2)

    def test_handles_empty_remote_types_set(self):
        """Empty remote set means every workflow type is missing."""
        workflow = {
            "1": {"class_type": "KSampler"},
            "2": {"class_type": "VAEDecode"},
        }

        result = self.mod.check_workflow_node_types(workflow, set())

        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_types"], ["KSampler", "VAEDecode"])
        self.assertEqual(result["total_remote_types"], 0)

    def test_accepts_list_as_remote_types(self):
        """List input is converted to set internally."""
        workflow = {"1": {"class_type": "KSampler"}}
        result = self.mod.check_workflow_node_types(workflow, ["KSampler", "VAEDecode"])
        self.assertTrue(result["compatible"])

    # ── _build_preflight_failure_artifact ─────────────────────────────

    def test_failure_artifact_contains_preflight_reason(self):
        """Preflight artifact uses 'preflight_blocked' cold status and a clear reason."""
        preflight = {
            "compatible": False,
            "missing_types": ["CustomNodeX"],
            "unique_class_types": 1,
            "total_remote_types": 100,
        }
        artifact = self.mod._build_preflight_failure_artifact(
            "set1", "default", "v1", preflight, reason="incompatible_workflow",
        )

        self.assertEqual(artifact["run"], "PREFLIGHT")
        self.assertEqual(artifact["cold_validation_status"], "preflight_blocked")
        self.assertEqual(artifact["preflight_reason"], "incompatible_workflow")
        self.assertEqual(artifact["preflight"]["missing_types"], ["CustomNodeX"])
        self.assertIs(artifact["accepted_cold_run"], False)
        self.assertEqual(artifact["validation_status"], "failed")

    def test_failure_artifact_object_info_reason(self):
        """object_info_failed reason produces a distinct artifact."""
        preflight = {"error": "Connection refused"}
        artifact = self.mod._build_preflight_failure_artifact(
            "set1", "default", "v1", preflight, reason="object_info_failed",
        )

        self.assertEqual(artifact["preflight_reason"], "object_info_failed")
        self.assertEqual(artifact["cold_validation_status"], "preflight_blocked")
        self.assertIn("object_info_failed", artifact["error"])
        self.assertIn("preflight", artifact)
        self.assertEqual(artifact["preflight"]["error"], "Connection refused")


class TestBenchmarkSummaries(unittest.TestCase):
    """Test benchmark set summary, matrix rows, and derived clock labelling."""

    def test_summarize_set_counts_only_accepted_cold_runs(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        summary = mod.summarize_benchmark_set([
            {"accepted_cold_run": True, "waterfall": {"benchmark_wall_ms": 1000.0}},
            {"accepted_cold_run": False, "waterfall": {"benchmark_wall_ms": 50.0}},
            {"accepted_cold_run": True, "waterfall": {"benchmark_wall_ms": 900.0}},
        ])

        self.assertEqual(summary["valid_cold_runs"], 2)
        self.assertEqual(summary["median_wall_ms"], 1000.0)

    def test_build_matrix_row_contains_cost_fields(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        row = mod.build_matrix_row(
            "reload_cleanup",
            {"benchmark_set_id": "base", "median_wall_ms": 20000.0, "median_restore_ms": 12000.0, "median_prompt_ms": 7000.0, "spread_ms": 1000.0, "valid_cold_runs": 3},
            {"benchmark_set_id": "after", "median_wall_ms": 18000.0, "median_restore_ms": 10000.0, "median_prompt_ms": 7000.0, "spread_ms": 900.0, "valid_cold_runs": 3},
            gpu_hourly_cost=2.5,
        )

        self.assertIn("estimated_cost_per_cold_start_before", row)
        self.assertIn("estimated_savings_per_1000_cold_starts", row)

    def test_derived_mixed_clock_fields_are_marked_non_authoritative(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        derived = mod.label_derived_clock_fields({"platform_restore_ms": 123.0})

        self.assertEqual(derived["platform_restore_ms"]["authority"], "derived_mixed_clock")


if __name__ == "__main__":
    unittest.main()
