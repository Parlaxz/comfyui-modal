"""Offline tests for the D4 forensic reconciliation batch.

Covers the D4 contract for ``comfymodal_runtime.trace`` (``cpu_affinity_count``,
``effective_cores_from``, ``forensic_intervals_disjoint``) and
``comfymodal_runtime.unet_fastsafetensors`` (``_fs_meta_reconcile``,
``_fs_pipeline_reconcile``, ``_fs_forensics_enabled``, and the ``_fs_meta_construct``
always-on / deep-profile / renamed-terminology metrics).

Written against the D4 contract EXACTLY (function names, signatures, and key
names are the API).  stdlib + torch only — ``comfy`` is never imported here.

NOTE: when the D4 implementation lane has not yet landed, the module imports
cleanly but the contract functions do not exist yet, so each test fails with
AttributeError until the lane lands.  That is expected and is reported by the
orchestrator (see the test module docstring in the parent lane).
"""

from __future__ import annotations

import os
import types
import unittest

import torch

import comfymodal_runtime.trace as trace
import comfymodal_runtime.unet_fastsafetensors as fs

_FORENSICS_ENV = "COMFYMODAL_V2_UNET_FORENSICS"

# Deep-profile keys produced ONLY when forensics are enabled (see contract).
_DEEP_PROFILE_KEYS = (
    "meta_module_construct_ms_by_class",
    "meta_module_construct_total_wall_ms",
    "meta_module_construct_count",
    "meta_module_first_op_wall_ms",
    "meta_gc_wall_ms",
    "meta_gc_count",
)

# Keys produced by _fs_meta_construct regardless of the forensics flag.
_ALWAYS_ON_KEYS = (
    "meta_import_wall_ms",
    "meta_context_entry_wall_ms",
    "meta_get_model_wall_ms",
    "meta_param_validate_wall_ms",
    "meta_sampling_detect_wall_ms",
    "meta_return_prep_wall_ms",
    "meta_worker_execution_wall_ms",
    "meta_worker_thread_cpu_ms",
    "meta_non_thread_cpu_wall_ms",
    "meta_worker_effective_cores",
    # Derived reconciliation keys (always-on per contract).
    "meta_execution_children_ms",
    "meta_execution_residual_ms",
    "meta_lifecycle_children_ms",
    "meta_lifecycle_residual_ms",
    "meta_reconcile_status",
)

# The old misleading names must NOT be produced anywhere (renamed in D4).
_OLD_MISLEADING_KEYS = (
    "meta_wait_estimate_ms",
    "meta_worker_cpu_ms",
    "meta_worker_total_wall_ms",
)

# The 22 fastsafe pipeline accounting phases (order mirrors the serial child
# chain in _fs_try_pipeline; the parallel worker walls live inside join_delay
# and must NOT be summed separately).
_PIPELINE_PHASE_NAMES = (
    "metrics_init",
    "eligibility",
    "header_config",
    "parity_gate",
    "target_and_mem",
    "worker_creation",
    "worker_submit",
    "join_delay",
    "post_join_prep",
    "post_load_gates",
    "transform_gate",
    "bind",
    "zero_copy_proof",
    "mem2",
    "sweep",
    "final_to",
    "final_sync",
    "validate",
    "patcher",
    "owner_attach",
    "telemetry",
    "return_gap",
)


class _MetaConfig:
    """Tiny fake ZImage-family config for ``_fs_meta_construct`` tests.

    Mirrors the MetaConstructionTests fake in
    ``tests/test_c9_fastsafetensors_integration.py``: ``get_model`` builds a
    real meta ``torch.nn.Sequential`` of ``Linear(4, 4)`` modules inside a
    ``torch.device("meta")`` context, and the returned model exposes
    ``model_sampling`` with ``model_config``/``model_type`` attributes so the
    sampling poison-detection path is exercisable.
    """

    def __init__(self):
        self.supported_inference_dtypes = [torch.bfloat16, torch.float16, torch.float32]

    @staticmethod
    def get_model(meta_sd, prefix):
        with torch.no_grad(), torch.device("meta"):
            _m = torch.nn.Sequential(
                torch.nn.Linear(4, 4),
                torch.nn.Linear(4, 4),
                torch.nn.Linear(4, 4),
            )
        # Plain namespace object (not an nn.Module) so the sampling
        # poison-detection walk sees model_config/model_type attributes.
        setattr(_m, "model_sampling", types.SimpleNamespace(
            model_config=object(), model_type="zimage"))
        return _m


def _set_env(name, value):
    """Set *name* and return a restore callable (for ``addCleanup``)."""
    _saved = os.environ.get(name)
    os.environ[name] = value

    def _restore():
        if _saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = _saved

    return _restore


def _clear_env(name):
    """Unset *name* and return a restore callable (for ``addCleanup``)."""
    _saved = os.environ.get(name)
    os.environ.pop(name, None)

    def _restore():
        if _saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = _saved

    return _restore


def _tiled_accounting_intervals(total_ms=1000.0, durations_ms=None):
    """Build 22 disjoint intervals that tile ``[base, base + total_ms]`` exactly.

    Durations are whole milliseconds (exact floats) so the ms sums are exact.
    Default tiling: 21 intervals of 45 ms + 1 interval of 55 ms = 1000.0 ms.
    """
    if durations_ms is None:
        durations_ms = [45.0] * 21 + [55.0]
    assert len(durations_ms) == len(_PIPELINE_PHASE_NAMES)
    assert abs(sum(durations_ms) - total_ms) < 1e-9, "durations must tile total_ms"
    _base = 1_000_000_000_000  # arbitrary absolute mono_ns base
    _cursor_ns = _base
    _intervals = []
    for _name, _d in zip(_PIPELINE_PHASE_NAMES, durations_ms):
        _end_ns = _cursor_ns + int(round(_d * 1_000_000))
        _intervals.append((_name, _cursor_ns, _end_ns))
        _cursor_ns = _end_ns
    return _intervals


class TraceHelperTests(unittest.TestCase):
    """Direct tests for the trace helper functions (contract item 1)."""

    def test_cpu_affinity_count_positive(self):
        """cpu_affinity_count() returns a positive int (sched_getaffinity with
        os.cpu_count fallback)."""
        _n = trace.cpu_affinity_count()
        self.assertIsInstance(_n, int)
        self.assertGreater(_n, 0)

    def test_effective_cores_calculation(self):
        """effective_cores_from(cpu_ms, wall_ms): None-safe, wall<=0 -> None,
        else round(cpu/wall, 4)."""
        self.assertEqual(trace.effective_cores_from(150.0, 300.0), 0.5)
        self.assertIsNone(trace.effective_cores_from(None, 300.0))
        self.assertIsNone(trace.effective_cores_from(150.0, 0.0))
        self.assertIsNone(trace.effective_cores_from(150.0, -1.0))
        self.assertIsNone(trace.effective_cores_from(150.0, None))
        self.assertIsNone(trace.effective_cores_from(None, None))
        self.assertEqual(trace.effective_cores_from(0.0, 300.0), 0.0)

    def test_forensic_intervals_disjoint_helper(self):
        """forensic_intervals_disjoint: touching ends allowed, gaps allowed,
        overlaps detected with a name-containing detail, unsorted input sorted
        internally."""
        # Touching ends (end == next start) are allowed.
        _ok, _detail = trace.forensic_intervals_disjoint(
            [("a", 100, 200), ("b", 200, 300)])
        self.assertTrue(_ok)
        self.assertIsNone(_detail)
        # A gap between intervals is fine.
        _ok, _detail = trace.forensic_intervals_disjoint(
            [("a", 100, 200), ("b", 250, 300)])
        self.assertTrue(_ok)
        self.assertIsNone(_detail)
        # Overlap is detected and the violating pair is named.
        _ok, _detail = trace.forensic_intervals_disjoint(
            [("a", 100, 200), ("b", 150, 300)])
        self.assertFalse(_ok)
        self.assertIsNotNone(_detail)
        assert _detail is not None
        self.assertIn("a", _detail)
        self.assertIn("b", _detail)
        # Unsorted input is still handled correctly (sorted by start).
        _ok, _detail = trace.forensic_intervals_disjoint(
            [("b", 150, 300), ("a", 100, 200)])
        self.assertFalse(_ok)
        assert _detail is not None
        self.assertIn("a", _detail)
        self.assertIn("b", _detail)
        _ok, _detail = trace.forensic_intervals_disjoint(
            [("b", 250, 300), ("a", 100, 200)])
        self.assertTrue(_ok)
        self.assertIsNone(_detail)


class MetaReconcileTests(unittest.TestCase):
    """Tests for ``_fs_meta_reconcile`` (contract item 2, first entry)."""

    def test_meta_reconcile_nonzero_start_delay(self):
        """Synthetic fake-clock fixture: children sum to 190.0, execution
        residual 10.0, lifecycle children 215.0, lifecycle residual 0.0, status
        OK; the start delay is counted exactly once (in lifecycle, never inside
        the execution children sum)."""
        _d = fs._fs_meta_reconcile(
            start_delay_ms=15.0,
            execution_wall_ms=200.0,
            import_ms=2.0,
            context_entry_ms=1.0,
            get_model_ms=150.0,
            param_validate_ms=20.0,
            sampling_detect_ms=10.0,
            sampling_fix_ms=5.0,
            return_prep_ms=2.0,
            lifecycle_total_ms=215.0,
        )
        self.assertEqual(_d["meta_execution_children_ms"], 190.0)
        self.assertEqual(_d["meta_execution_residual_ms"], 10.0)
        self.assertEqual(_d["meta_lifecycle_children_ms"], 215.0)
        self.assertEqual(_d["meta_lifecycle_residual_ms"], 0.0)
        self.assertEqual(_d["meta_reconcile_status"], "OK")
        # Start delay appears exactly once: lifecycle_children = start_delay +
        # execution_wall = execution_children + execution_residual +
        # start_delay.  It is NOT folded into execution_children (which would
        # make it 205.0 and shrink the execution residual to -5.0).
        _exec_children = 2.0 + 1.0 + 150.0 + 20.0 + 10.0 + 5.0 + 2.0
        self.assertEqual(_d["meta_execution_children_ms"], _exec_children)
        self.assertNotEqual(_d["meta_execution_children_ms"], 205.0)
        self.assertEqual(
            _d["meta_lifecycle_children_ms"],
            _d["meta_execution_children_ms"] + _d["meta_execution_residual_ms"] + 15.0,
        )

    def test_meta_reconcile_execution_vs_lifecycle(self):
        """Second fixture with nonzero residuals: execution_residual ==
        execution_wall - sum(children), lifecycle_residual == lifecycle_total -
        (start_delay + execution_wall), and status GAP when |lifecycle_residual|
        >= 5.0; None inputs are treated as 0.0."""
        _d = fs._fs_meta_reconcile(
            start_delay_ms=10.0,
            execution_wall_ms=180.0,
            import_ms=3.0,
            context_entry_ms=2.0,
            get_model_ms=120.0,
            param_validate_ms=10.0,
            sampling_detect_ms=5.0,
            sampling_fix_ms=3.0,
            return_prep_ms=1.0,
            lifecycle_total_ms=200.0,
        )
        _children = 3.0 + 2.0 + 120.0 + 10.0 + 5.0 + 3.0 + 1.0
        self.assertEqual(_d["meta_execution_children_ms"], _children)
        self.assertEqual(_d["meta_execution_residual_ms"], 180.0 - _children)
        self.assertEqual(_d["meta_execution_residual_ms"], 36.0)
        self.assertEqual(_d["meta_lifecycle_children_ms"], 10.0 + 180.0)
        self.assertEqual(
            _d["meta_lifecycle_residual_ms"], 200.0 - (10.0 + 180.0))
        self.assertEqual(_d["meta_lifecycle_residual_ms"], 10.0)
        # |10.0| >= 5.0 -> GAP.
        self.assertEqual(_d["meta_reconcile_status"], "GAP")
        # None inputs are treated as 0.0.
        _d2 = fs._fs_meta_reconcile(
            start_delay_ms=None,
            execution_wall_ms=100.0,
            import_ms=None,
            context_entry_ms=None,
            get_model_ms=90.0,
            param_validate_ms=None,
            sampling_detect_ms=None,
            sampling_fix_ms=None,
            return_prep_ms=None,
            lifecycle_total_ms=100.0,
        )
        self.assertEqual(_d2["meta_execution_children_ms"], 90.0)
        self.assertEqual(_d2["meta_execution_residual_ms"], 10.0)
        self.assertEqual(_d2["meta_lifecycle_children_ms"], 100.0)
        self.assertEqual(_d2["meta_lifecycle_residual_ms"], 0.0)
        self.assertEqual(_d2["meta_reconcile_status"], "OK")


class PipelineReconcileTests(unittest.TestCase):
    """Tests for ``_fs_pipeline_reconcile`` (contract item 2, second entry)."""

    def test_pipeline_accounting_disjoint_exact(self):
        """Synthetic EXACT fixture: total_ms=1000.0 tiled by 22 disjoint
        intervals covering [0, 1000]; children sum exactly 1000.0, residual
        0.0, status OK, accounting_disjoint True, overlap detail None."""
        _total = 1000.0
        _ivs = _tiled_accounting_intervals(_total)
        _d = fs._fs_pipeline_reconcile(_total, _ivs)
        self.assertEqual(_d["pipeline_total_ms"], _total)
        self.assertEqual(_d["accounting_children_ms"], 1000.0)
        self.assertEqual(_d["residual_ms"], 0.0)
        self.assertLess(abs(_d["residual_ms"]), 10.0)
        self.assertEqual(_d["reconciliation_status"], "OK")
        self.assertTrue(_d["accounting_disjoint"])
        self.assertIsNone(_d["accounting_overlap_detail"])

    def test_pipeline_accounting_overlap_detected(self):
        """Fixture with two overlapping intervals: accounting_disjoint False,
        accounting_overlap_detail names the violating pair, children sum !=
        total, and status GAP (|residual| >= 10.0)."""
        _ivs = _tiled_accounting_intervals()
        # Extend join_delay so it overlaps the start of post_join_prep.
        _idx = _PIPELINE_PHASE_NAMES.index("join_delay")
        _name, _s, _e = _ivs[_idx]
        _ivs = list(_ivs)
        _ivs[_idx] = (_name, _s, _e + int(10.0 * 1_000_000))
        _d = fs._fs_pipeline_reconcile(1000.0, _ivs)
        self.assertFalse(_d["accounting_disjoint"])
        _detail = _d["accounting_overlap_detail"]
        self.assertIsNotNone(_detail)
        self.assertIn("join_delay", _detail)
        self.assertIn("post_join_prep", _detail)
        self.assertNotEqual(_d["accounting_children_ms"], 1000.0)
        # residual = 1000.0 - 1010.0 = -10.0 -> |residual| == 10.0 -> GAP.
        self.assertEqual(_d["reconciliation_status"], "GAP")

    def test_pipeline_accounting_nested_contained_intervals(self):
        """Nested-detail fixture: join_delay CONTAINS two smaller worker
        intervals that are NOT in the accounting list; disjoint stays True and
        the children sum excludes the contained workers (== sum of the 22 outer
        intervals only)."""
        _ivs = _tiled_accounting_intervals()
        _idx = _PIPELINE_PHASE_NAMES.index("join_delay")
        _jname, _js, _je = _ivs[_idx]
        _jdur_ns = _je - _js
        # Two sub-intervals strictly inside join_delay (worker threads run
        # concurrently under the join); deliberately NOT in the accounting list.
        _worker_a = ("fastsafe_worker_a", _js, _js + _jdur_ns // 2)
        _worker_b = ("fastsafe_worker_b", _js + _jdur_ns // 2, _je)
        _d = fs._fs_pipeline_reconcile(1000.0, _ivs)
        self.assertTrue(_d["accounting_disjoint"])
        self.assertIsNone(_d["accounting_overlap_detail"])
        _expected_outer = sum((_e - _s) for _, _s, _e in _ivs) / 1_000_000
        self.assertEqual(_d["accounting_children_ms"], _expected_outer)
        self.assertEqual(_d["accounting_children_ms"], 1000.0)
        # If the contained workers were wrongly summed, the children would be
        # larger — proving the exclusion.
        _naive = _expected_outer + sum(
            (_e - _s) for _, _s, _e in (_worker_a, _worker_b)) / 1_000_000
        self.assertGreater(_naive, _d["accounting_children_ms"])


class MetaConstructForensicsTests(unittest.TestCase):
    """Tests for ``_fs_forensics_enabled`` + ``_fs_meta_construct`` metric
    surface (contract items 2, 5-7).  Every test that touches the forensics env
    var sets/restores it via ``addCleanup``."""

    def test_wall_minus_thread_cpu_terminology(self):
        """Always-on keys use the D4 terminology: meta_worker_thread_cpu_ms and
        meta_non_thread_cpu_wall_ms are present; the old misleading names
        (meta_wait_estimate_ms / meta_worker_cpu_ms / meta_worker_total_wall_ms)
        are absent; meta_worker_effective_cores equals
        effective_cores_from(thread_cpu, execution_wall)."""
        _restore = _set_env(_FORENSICS_ENV, "1")
        self.addCleanup(_restore)
        _metrics = {}
        _model = fs._fs_meta_construct(_MetaConfig(), {}, _metrics)
        self.assertTrue(list(_model.parameters()))
        self.assertIn("meta_worker_thread_cpu_ms", _metrics)
        self.assertIn("meta_non_thread_cpu_wall_ms", _metrics)
        self.assertIn("meta_worker_execution_wall_ms", _metrics)
        self.assertGreater(_metrics["meta_worker_execution_wall_ms"], 0.0)
        self.assertGreaterEqual(_metrics["meta_non_thread_cpu_wall_ms"], 0.0)
        for _k in _OLD_MISLEADING_KEYS:
            self.assertNotIn(_k, _metrics)
        _cpu = _metrics["meta_worker_thread_cpu_ms"]
        _wall = _metrics["meta_worker_execution_wall_ms"]
        if _cpu is not None:
            self.assertAlmostEqual(
                _metrics["meta_worker_effective_cores"],
                trace.effective_cores_from(_cpu, _wall),
                places=4,
            )

    def test_deep_profiler_default_off(self):
        """With COMFYMODAL_V2_UNET_FORENSICS unset or \"0\":
        _fs_forensics_enabled() is False and _fs_meta_construct produces NO
        meta_module_construct_*/meta_gc_* keys but DOES produce the always-on
        keys."""
        _r1 = _clear_env(_FORENSICS_ENV)
        self.addCleanup(_r1)
        self.assertFalse(fs._fs_forensics_enabled())
        _metrics = {}
        _model = fs._fs_meta_construct(_MetaConfig(), {}, _metrics)
        self.assertTrue(list(_model.parameters()))
        for _k in _DEEP_PROFILE_KEYS:
            self.assertNotIn(_k, _metrics)
        for _k in _ALWAYS_ON_KEYS:
            self.assertIn(_k, _metrics)
        _r2 = _set_env(_FORENSICS_ENV, "0")
        self.addCleanup(_r2)
        self.assertFalse(fs._fs_forensics_enabled())
        _metrics2 = {}
        fs._fs_meta_construct(_MetaConfig(), {}, _metrics2)
        for _k in _DEEP_PROFILE_KEYS:
            self.assertNotIn(_k, _metrics2)

    def test_deep_profiler_explicit_on(self):
        """With COMFYMODAL_V2_UNET_FORENSICS=\"1\" (and the truthy spellings):
        _fs_forensics_enabled() is True and _fs_meta_construct metrics contain
        the full deep-profile key set (module_construct_ms_by_class is a dict
        with at least one class entry) plus the always-on keys."""
        for _v in ("1", "true", "yes", "on"):
            _r = _set_env(_FORENSICS_ENV, _v)
            self.addCleanup(_r)
            self.assertTrue(fs._fs_forensics_enabled())
        _r_main = _set_env(_FORENSICS_ENV, "1")
        self.addCleanup(_r_main)
        _metrics = {}
        _model = fs._fs_meta_construct(_MetaConfig(), {}, _metrics)
        self.assertTrue(list(_model.parameters()))
        _by_class = _metrics["meta_module_construct_ms_by_class"]
        self.assertIsInstance(_by_class, dict)
        self.assertGreaterEqual(len(_by_class), 1)
        for _k in _DEEP_PROFILE_KEYS:
            self.assertIn(_k, _metrics)
        for _k in _ALWAYS_ON_KEYS:
            self.assertIn(_k, _metrics)


if __name__ == "__main__":
    unittest.main()
