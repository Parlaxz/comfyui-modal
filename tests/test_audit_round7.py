"""Tests for audit round 7: waterfall wiring, topology hash, workspace isolation, active-next bounding."""

import ast
import re
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_stripped(path):
    src = path.read_text(encoding="utf-8")
    if src.startswith("\ufeff"):
        src = src[1:]
    return src


def _find_function_source(src, name):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    return None


def _load_waterfall_function():
    """Load only the waterfall helper so its arithmetic can be exercised."""
    src = _read_stripped(REPO_ROOT / "comfyapp.py")
    tree = ast.parse(src)
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_log_cold_start_waterfall"
    )
    namespace = {
        "env_flag": lambda _name: False,
        "_WATERFALL_GLYPH": {"ok": "OK", "miss": "--", "na": "  "},
        "_PLATFORM_OUTLIER_THRESHOLD_MS": 10000,
    }
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, "<waterfall-test>", "exec"), namespace)
    return namespace["_log_cold_start_waterfall"]


# ── Phase 1: Topology hash ──────────────────────────────────────────────


class TopologyHashMutableWorkflowTests(unittest.TestCase):
    """Phase 1: Mutable-workflow hash regression test."""

    def setUp(self):
        from production_workflow import build_production_topology_hash, _reset_cache
        self._hash = build_production_topology_hash
        self._reset = _reset_cache
        self._reset()

    def test_hash_changes_when_workflow_mutates(self):
        """Hash must change when the workflow dict is mutated, proving
        the cache was correctly removed."""
        wf = {"1": {"class_type": "A", "inputs": {}}}
        prod = {"enabled": True, "schema_version": 1,
                "output_node_ids": ["1"], "bypass_node_ids": [],
                "direct_output_sink": True}
        h1 = self._hash(wf, prod, allow_direct_output_rewrite=True)
        # Mutate the SAME dict object
        wf["1"]["class_type"] = "B"
        h2 = self._hash(wf, prod, allow_direct_output_rewrite=True)
        self.assertNotEqual(h1, h2, "mutating workflow must change hash (no object-ID cache)")


# ── Phase 2: Waterfall wiring on in-process streaming path ──────────────


class WaterfallStreamingPathTests(unittest.TestCase):
    """Phase 2: Verify the waterfall is called on the actual
    in-process streaming path, not just the non-streaming path."""

    def test_waterfall_called_on_in_process_streaming_success(self):
        """_log_cold_start_waterfall must be called inside the
        _exec closure of run_prompt_stream's in-process branch
        with label='run_prompt_stream_in_process'."""
        src = _read_stripped(REPO_ROOT / "comfyapp.py")
        self.assertIn(
            'label="run_prompt_stream_in_process"',
            src,
            "run_prompt_stream in-process path must call fall with "
            "label='run_prompt_stream_in_process'",
        )

    def test_waterfall_called_on_in_process_streaming_failure(self):
        """_log_cold_start_waterfall must also be called on the
        failure path with label='run_prompt_stream_in_process_failure'."""
        src = _read_stripped(REPO_ROOT / "comfyapp.py")
        self.assertIn(
            'label="run_prompt_stream_in_process_failure"',
            src,
            "run_prompt_stream failure path must call fall with "
            "label='run_prompt_stream_in_process_failure'",
        )

    def test_failure_path_builds_partial_trace(self):
        """The failure path must build a partial trace summary
        with timing_quality='partial' before calling the waterfall."""
        src = _read_stripped(REPO_ROOT / "comfyapp.py")
        # Check the raw source (before ast.unparse converts quotes)
        self.assertIn(
            '"partial"',
            src,
            "failure path must set timing_quality='partial'",
        )


# ── Phase 3: Waterfall categories ───────────────────────────────────────


class WaterfallCategoryTests(unittest.TestCase):
    """Phase 3: Verify waterfall labels, ordering, and non-overlap."""

    def test_client_press_to_modal_entry_label(self):
        """The client-press-to-modal-entry span must use the
        correct label (not 'submit_to_restore_entry')."""
        src = _read_stripped(REPO_ROOT / "comfyapp.py")
        self.assertNotIn("submit_to_restore_entry", src,
                         "'submit_to_restore_entry' label must not appear")
        self.assertIn("client_press_to_modal_entry", src,
                      "'client_press_to_modal_entry' label must appear")

    def test_snapshot_hydration_gap_is_unavailable(self):
        """The platform snapshot hydration gap must be reported
        as unavailable (None value), not fabricated from restore timestamps."""
        src = _read_stripped(REPO_ROOT / "comfyapp.py")
        # Look for the function containing the gap line
        wf_src = _find_function_source(src, "_log_cold_start_waterfall")
        self.assertIsNotNone(wf_src)
        # Must have a line for platform_snapshot_hydration_gap
        self.assertIn("platform_snapshot_hydration_gap", wf_src)
        # The value must be None (unavailable)
        self.assertRegex(
            wf_src,
            r'platform_snapshot_hydration_gap.*None',
            "snapshot hydration gap must be None, not a fabricated timestamp",
        )

    def test_output_collection_forward_ordering(self):
        """Output collection must use _d(t8b_st, t9), not _d(t9, t8b_st)."""
        wf_src = _find_function_source(_read_stripped(REPO_ROOT / "comfyapp.py"),
                                        "_log_cold_start_waterfall")
        self.assertIsNotNone(wf_src)
        # Must NOT have _d(t9, t8b_st)
        self.assertNotIn("_d(t9, t8b_st)", wf_src)
        # Must have _d(t8b_st, t9)
        self.assertIn("_d(t8b_st, t9)", wf_src)

    def test_no_parent_child_double_count(self):
        """Old test -> intended invariant -> replacement coverage.

        Old test: match the implementation's ``not in c`` expression.
        Intended invariant: a parent critical-path span must not be added
        again through its displayed child spans.
        Why stale: the implementation's tuple field and arithmetic can change
        without changing that semantic contract.
        Replacement coverage: execute the helper with nested child deltas and
        assert the emitted total contains only the three parent spans.
        """
        waterfall = _load_waterfall_function()
        summary = {
            "prompt_id": "waterfall-test",
            "stages": {
                "t0_client_press": 1000.0,
                "t2_local_dispatch": 1001.0,
                "t3_modal_entry": 1002.0,
                "t3b_validate_done": 1002.5,
                "t3c_prep_done": 1003.0,
                "t8b_outputs_collected": 1004.5,
                "t9_modal_return": 1005.0,
                "t10_local_materialized": 1006.0,
            },
            "deltas_ms": {
                # These local children total the client-to-entry parent span.
                "t0_to_t1": 100.0,
                "t1_to_t2": 900.0,
                # These execution children are nested in the remote parent.
                "t3_to_t3b": 500.0,
                "t3b_to_t3c": 500.0,
                "clip_load": 250.0,
                "sampler": 1500.0,
                "t8b_to_t9": 500.0,
            },
            "restore": {"restore_total_ms": 500.0},
            "derived_ms": {},
        }
        with patch("builtins.print") as print_mock:
            waterfall(summary)

        sum_lines = [
            str(call.args[0])
            for call in print_mock.call_args_list
            if call.args and "known_nonoverlap_total" in str(call.args[0])
        ]
        self.assertEqual(len(sum_lines), 1)
        # 2,000 client->entry + 3,000 remote execution + 1,000 return.
        match = re.search(r"known_nonoverlap_total\s+([0-9.]+)", sum_lines[0])
        self.assertIsNotNone(match)
        self.assertAlmostEqual(float(match.group(1)), 6000.0)

    def test_missing_stages_appear(self):
        """The waterfall must include a missing_stages list when
        stages are absent."""
        wf_src = _find_function_source(_read_stripped(REPO_ROOT / "comfyapp.py"),
                                        "_log_cold_start_waterfall")
        self.assertIsNotNone(wf_src)
        self.assertIn("missing_stages", wf_src,
                      "waterfall must track missing_stages")

    def test_timing_quality_classified(self):
        """The waterfall must classify timing_quality as
        complete, partial, or invalid_order."""
        wf_src = _find_function_source(_read_stripped(REPO_ROOT / "comfyapp.py"),
                                        "_log_cold_start_waterfall")
        self.assertIsNotNone(wf_src)
        self.assertIn("timing_quality", wf_src)


# ── Phase 4: Platform diagnostics ──────────────────────────────────────


class PlatformDiagnosticsTests(unittest.TestCase):
    """Phase 4: Platform diagnostics on streaming path."""

    def test_platform_diag_collected_on_streaming_path(self):
        """The in-process streaming trace_summary must be enriched
        with platform diagnostics."""
        src = _read_stripped(REPO_ROOT / "comfyapp.py")
        # Must call _collect_platform_diagnostics in the _exec closure
        self.assertIn(
            "_collect_platform_diagnostics(self.__class__.__name__)",
            src,
        )

    def test_platform_diag_no_secrets(self):
        """Platform diagnostics must not expose credentials."""
        src = _read_stripped(REPO_ROOT / "comfyapp.py")
        wf_src = _find_function_source(src, "_collect_platform_diagnostics")
        self.assertIsNotNone(wf_src)
        self.assertNotIn("token", wf_src.lower(),
                         "platform diag must not reference tokens")
        self.assertNotIn("secret", wf_src.lower(),
                         "platform diag must not reference secrets")
        self.assertNotIn("credential", wf_src.lower(),
                         "platform diag must not reference credentials")


# ── Phase 5: Preflight breakdown ───────────────────────────────────────


class PreflightBreakdownTests(unittest.TestCase):
    """Phase 5: Preflight instrumentation."""

    def test_preflight_breakdown_printed(self):
        """_execute_in_process must print a [preflight.breakdown] line."""
        eip_src = _find_function_source(
            _read_stripped(REPO_ROOT / "comfyapp.py"), "_execute_in_process"
        )
        self.assertIsNotNone(eip_src)
        self.assertIn("preflight.breakdown", eip_src,
                      "_execute_in_process must print preflight.breakdown")

    def test_preflight_timing_stored_on_self(self):
        """Preflight timings must be stored as instance attrs."""
        eip_src = _find_function_source(
            _read_stripped(REPO_ROOT / "comfyapp.py"), "_execute_in_process"
        )
        self.assertIsNotNone(eip_src)
        for attr in ("_preflight_input_image_ms", "_preflight_missing_node_repair_ms",
                     "_preflight_workflow_hash_ms", "_preflight_production_compile_ms"):
            self.assertIn(attr, eip_src,
                          f"{attr} must be stored as instance attr")

    def test_preflight_sorted_by_largest(self):
        """The breakdown must report the largest contributor."""
        eip_src = _find_function_source(
            _read_stripped(REPO_ROOT / "comfyapp.py"), "_execute_in_process"
        )
        self.assertIsNotNone(eip_src)
        self.assertIn("largest", eip_src,
                      "preflight breakdown must report largest contributor")
        self.assertIn("largest_ms", eip_src,
                      "preflight breakdown must report largest_ms")


# ── Phase 7: Workspace isolation ────────────────────────────────────────


class WorkspaceIsolationTests(unittest.TestCase):
    """Phase 7: Workspace propagation in normal and comparison paths."""

    def test_normal_prompt_passes_workspace_to_set_active_warmup_profile(self):
        src = _read_stripped(REPO_ROOT / "__init__.py")
        self.assertIn(
            "set_active_warmup_profile(",
            src,
        )
        self.assertIn(
            "workspace=_request_workspace",
            src,
            "_execute_job must pass workspace to set_active_warmup_profile",
        )

    # H19 Wave G: test_normal_prompt_passes_workspace_to_run_prompt_stream
    # and both comparison-workspace stream tests were removed — their
    # subjects (the V1 direct stream call in _execute_job and the deleted
    # _execute_comparison_profile body) no longer exist; __init__.py has
    # ZERO direct run_prompt_stream calls (V2 owns streaming via
    # ModalTransport). Workspace threading into V2 plans is pinned by the
    # runtime/playground suites.


# ── Phase 8: Active-next bounding ───────────────────────────────────────


class ActiveNextBoundingTests(unittest.TestCase):
    """Phase 8: Active-next dedup dict bounding and small-TTL fix."""

    def test_active_next_dict_pruned_above_100_entries(self):
        src = _read_stripped(REPO_ROOT / "__init__.py")
        eip_src = _find_function_source(src, "_execute_job")
        self.assertIsNotNone(eip_src)
        self.assertIn("> 100", eip_src,
                      "active-next dedup must be pruned when > 100 entries")
        self.assertIn("_last_written_stable_profile = {", eip_src,
                      "active-next dedup pruning must rebuild the dict")

    def test_small_ttl_refresh_before_expiration(self):
        src = _read_stripped(REPO_ROOT / "__init__.py")
        eip_src = _find_function_source(src, "_execute_job")
        self.assertIsNotNone(eip_src)
        # Find the refresh_after_s formula section
        self.assertIn("_effective_ttl_s = max(2.0, float(_ACTIVE_NEXT_PROFILE_TTL_S))",
                      eip_src,
                      "small-TTL fix must floor at 2.0")
        self.assertIn("_refresh_after_s = min(",
                      eip_src,
                      "refresh formula must use min()")
        self.assertIn("_effective_ttl_s - 1.0",
                      eip_src,
                      "refresh formula must ensure gap before expiration")
        self.assertIn("max(1.0, _refresh_after_s)",
                      eip_src,
                      "refresh formula must floor at 1.0")

    def test_no_unbounded_active_next_dict(self):
        """The active-next dedup dict must be bounded (no unbounded growth)."""
        src = _read_stripped(REPO_ROOT / "__init__.py")
        eip_src = _find_function_source(src, "_execute_job")
        self.assertIsNotNone(eip_src)
        self.assertIn("len(_last_written_stable_profile)", eip_src,
                      "active-next dedup must check dict size for pruning")


if __name__ == "__main__":
    unittest.main()
