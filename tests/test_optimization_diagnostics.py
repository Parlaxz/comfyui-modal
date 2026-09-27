"""Tests for comfymodal_runtime.optimization_diagnostics.

Proves the instrumentation contract:

* inactive (zero behavior change) when ``COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS`` is off
* correctly reports synthetic stage timings when enabled
* does not add unwanted CUDA synchronization in default mode
* aggregates tensor/storage stats (bounded output, never per-tensor spam)
* handles unsupported ``/proc`` / getrusage counters gracefully (Windows-safe)
* all emitted event names carry the ``opt_`` prefix
"""

from __future__ import annotations

import importlib
import os
import sys
import time
import unittest
from types import SimpleNamespace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from comfymodal_runtime import optimization_diagnostics as od

FLAG = "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS"
SYNC_FLAG = "COMFYMODAL_V2_OPT_DIAG_SYNC_CUDA"


def _reload(env: dict[str, "str | None"]) -> None:
    """Apply *env* to os.environ, then reload the module so its frozen
    import-time gates match the new environment."""
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(od)


class FakeTrace:
    """Minimal recorder mirroring the real trace.emit contract."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, name, *, phase="", metadata=None):
        ev = {
            "name": name,
            "phase": phase,
            "metadata": dict(metadata or {}),
            "monotonic_ns": time.monotonic_ns(),
            "wall_unix_ns": time.time_ns(),
        }
        self.events.append(ev)
        return ev

    def names(self) -> list[str]:
        return [e["name"] for e in self.events]

    def event(self, name: str) -> dict | None:
        for e in self.events:
            if e["name"] == name:
                return e
        return None


class FakeStorage:
    def __init__(self, nbytes: int, filename=None):
        self._nbytes = nbytes
        self._filename = filename

    def nbytes(self) -> int:
        return self._nbytes

    def filename(self):
        return self._filename


class FakeTensor:
    """CPU-only fake tensor: dtype, pinned, contiguous, storage."""

    def __init__(self, nbytes: int, dtype="float32", pinned=False,
                 contiguous=True, file_backed=False):
        self._storage = FakeStorage(nbytes, "/x/checkpoint.safetensors" if file_backed else None)
        self.dtype = dtype
        self._pinned = pinned
        self._contiguous = contiguous

    def is_pinned(self) -> bool:
        return self._pinned

    def is_contiguous(self) -> bool:
        return self._contiguous

    def untyped_storage(self):
        return self._storage

    def numel(self):
        return self._storage.nbytes() // 4

    def element_size(self):
        return 4


class FakeCuda:
    """Injectable CUDA provider that counts synchronize() calls."""

    def __init__(self, available=True):
        self.available = available
        self.sync_calls = 0
        self._time = 0.0

    def is_available(self) -> bool:
        return self.available

    def Event(self, enable_timing=True):
        return _FakeEvent(self)

    def synchronize(self):
        self.sync_calls += 1

    def elapsed(self, start_ts: float, end_ts: float) -> float:
        return (end_ts - start_ts) * 1000.0  # seconds -> ms


class _FakeEvent:
    def __init__(self, cuda: FakeCuda):
        self._cuda = cuda

    def record(self):
        self._cuda._time += 0.25  # 250 ms of fake device time per record

    def elapsed_time(self, other: "_FakeEvent") -> float:
        return self._cuda.elapsed(self._cuda._time, other._cuda._time)


class OptimizationDiagnosticsTests(unittest.TestCase):
    """Flag-off behavior: everything must be a safe no-op."""

    def setUp(self) -> None:
        _reload({FLAG: None, SYNC_FLAG: None})

    def tearDown(self) -> None:
        _reload({FLAG: None, SYNC_FLAG: None})

    def test_disabled_emit_returns_none(self) -> None:
        tr = FakeTrace()
        self.assertIsNone(od.emit_opt(tr, "anything", metadata={"x": 1}))
        self.assertEqual(tr.events, [])

    def test_disabled_stage_emits_nothing(self) -> None:
        tr = FakeTrace()
        with od.opt_stage("sample_stage", tr, phase="execution"):
            time.sleep(0.001)
        self.assertEqual(tr.events, [])

    def test_disabled_tensor_stats_empty(self) -> None:
        stats = od.OptTensorStats()
        for _ in range(5):
            stats.record(FakeTensor(1024))
        out = stats.finish()
        self.assertEqual(out["count"], 0)
        self.assertFalse(out.get("storages_scanned"))

    def test_disabled_cuda_interval_never_syncs(self) -> None:
        cuda = FakeCuda()
        iv = od.OptCudaInterval(cuda=cuda)
        iv.begin().end(realize=True)  # even realize=True is inert when off
        self.assertIsNone(iv.elapsed_ms)
        self.assertEqual(cuda.sync_calls, 0)

    def test_disabled_host_snapshot_still_safe(self) -> None:
        snap = od.host_snapshot()  # must not raise on Windows
        self.assertIn("mono_ns", snap)
        self.assertIn("thread_cpu_ns", snap)
        delta = od.host_deltas(snap, od.host_snapshot())
        self.assertIn("wall_ms", delta)
        self.assertIn("effective_cores", delta)


class OptimizationDiagnosticsEnabledTests(unittest.TestCase):
    """Flag-on behavior: synthetic stage timings and aggregation."""

    def setUp(self) -> None:
        _reload({FLAG: "1", SYNC_FLAG: None})

    def tearDown(self) -> None:
        _reload({FLAG: None, SYNC_FLAG: None})

    def test_stage_emits_start_end_with_duration(self) -> None:
        tr = FakeTrace()
        with od.opt_stage("unit_test_stage", tr, phase="execution", metadata={"k": "v"}):
            # Embedded Windows Python has ~15.6ms monotonic ticks; sleep
            # across several ticks so duration is measurable anywhere.
            time.sleep(0.05)
        names = tr.names()
        self.assertEqual(names, ["opt_unit_test_stage_start", "opt_unit_test_stage_end"])
        end = tr.event("opt_unit_test_stage_end")
        if end is None:
            self.fail("missing end event")
        self.assertGreaterEqual(end["metadata"]["duration_ms"], 20.0)
        self.assertEqual(end["metadata"]["k"], "v")
        start = tr.event("opt_unit_test_stage_start")
        if start is None:
            self.fail("missing start event")
        self.assertLessEqual(start["monotonic_ns"], end["monotonic_ns"])
        self.assertLessEqual(start["wall_unix_ns"], end["wall_unix_ns"])

    def test_emit_prefix_and_metadata(self) -> None:
        tr = FakeTrace()
        od.emit_opt(tr, "some_metric", phase="restore", metadata={"ms": 12.5})
        ev = tr.event("opt_some_metric")
        self.assertIsNotNone(ev)
        if ev is None:
            self.fail("missing event")
        self.assertEqual(ev["phase"], "restore")
        self.assertEqual(ev["metadata"]["ms"], 12.5)

    def test_tensor_stats_aggregation(self) -> None:
        stats = od.OptTensorStats()
        tensors = [
            FakeTensor(1 << 20, dtype="float32"),                      # lt_1MiB boundary → 1MiB bucket
            FakeTensor((8 << 20) - 1, dtype="float32"),                # 1_8MiB
            FakeTensor(64 << 20, dtype="bfloat16"),                    # 64_256MiB
            FakeTensor(300 << 20, dtype="bfloat16", pinned=True),      # 256MiB_1GiB, pinned
            FakeTensor(1 << 30, dtype="float16", file_backed=True),    # ge_1GiB, mmap
        ]
        for t in tensors:
            stats.record(t)
        out = stats.finish()
        self.assertEqual(out["count"], 5)
        self.assertEqual(out["pinned_count"], 1)
        self.assertEqual(out["contiguous_count"], 5)
        self.assertEqual(out["mmap_backed_count"], 1)
        self.assertEqual(sum(out["size_bucket_counts"].values()), 5)
        self.assertEqual(out["by_dtype_bytes"]["bfloat16"], (64 << 20) + (300 << 20))
        self.assertLessEqual(len(out["first_n"]), od.MAX_STORAGES_FIRST_N)
        self.assertLessEqual(len(out["largest_n"]), od.MAX_STORAGES_LARGEST_N)
        self.assertGreaterEqual(out["largest_n"][0]["bytes"], out["largest_n"][-1]["bytes"])

    def test_tensor_stats_bounded_with_many_tensors(self) -> None:
        def _run(n: int) -> str:
            stats = od.OptTensorStats()
            for i in range(n):
                stats.record(FakeTensor((i + 1) * 1024, file_backed=(i % 3 == 0)))
            return str(stats.finish())

        out = od.OptTensorStats()
        for i in range(500):
            out.record(FakeTensor((i + 1) * 1024, file_backed=(i % 3 == 0)))
        res = out.finish()
        self.assertEqual(res["count"], 500)
        self.assertEqual(len(res["first_n"]), od.MAX_STORAGES_FIRST_N)
        self.assertEqual(len(res["largest_n"]), od.MAX_STORAGES_LARGEST_N)
        # bounded: output size must not scale linearly with input count
        self.assertLess(abs(len(_run(50)) - len(_run(500))), 500)

    def test_host_deltas_math(self) -> None:
        before = od.host_snapshot()
        after = od.host_snapshot()
        # force measurable thread cpu usage
        _spin = sum(range(200000))
        del _spin
        after = od.host_snapshot()
        d = od.host_deltas(before, after)
        self.assertGreaterEqual(d["wall_ms"], 0.0)
        if d["thread_cpu_ms"] is not None:
            self.assertGreaterEqual(d["thread_cpu_ms"], 0.0)

    def test_effective_gbps(self) -> None:
        self.assertEqual(od.effective_gbps(12_310_000_000, 2214.0), 5.560)
        self.assertIsNone(od.effective_gbps(0, 100.0))
        self.assertIsNone(od.effective_gbps(100, 0.0))

    def test_wall_overlap_math(self) -> None:
        # a=[1,3]ms fully inside b=[0.5,4]ms → overlap covers 100% of a
        # (b_within_a_frac == 1.0) and 2/3.5 of b (a_within_b_frac).
        r = od.wall_overlap_ms(1_000_000, 3_000_000, 500_000, 4_000_000)
        self.assertEqual(r["overlap_ms"], 2.0)
        self.assertEqual(r["b_within_a_frac"], 1.0)
        self.assertAlmostEqual(r["a_within_b_frac"], 0.5714, places=4)
        # no overlap
        r2 = od.wall_overlap_ms(1_000_000, 2_000_000, 3_000_000, 4_000_000)
        self.assertEqual(r2["overlap_ms"], 0.0)


class OptimizationDiagnosticsCudaTests(unittest.TestCase):
    """CUDA-event intervals must not synchronize unless explicitly allowed."""

    def setUp(self) -> None:
        _reload({FLAG: "1", SYNC_FLAG: None})

    def tearDown(self) -> None:
        _reload({FLAG: None, SYNC_FLAG: None})

    def test_default_mode_no_sync_on_realize_reuse(self) -> None:
        cuda = FakeCuda()
        iv = od.OptCudaInterval(cuda=cuda)
        iv.begin().end()          # record pair, no sync
        self.assertEqual(cuda.sync_calls, 0)
        # caller performs its own sync, then reuses it via realize()
        cuda.synchronize()
        self.assertEqual(cuda.sync_calls, 1)
        ms = iv.realize()
        self.assertIsNotNone(ms)
        self.assertEqual(cuda.sync_calls, 1)  # realize itself never syncs

    def test_end_realize_requires_sync_flag(self) -> None:
        cuda = FakeCuda()
        iv = od.OptCudaInterval(cuda=cuda)
        iv.begin().end(realize=True)  # SYNC_FLAG off → no sync, unrealized
        self.assertEqual(cuda.sync_calls, 0)
        self.assertIsNone(iv.elapsed_ms)

    def test_end_realize_with_sync_flag_syncs(self) -> None:
        _reload({FLAG: "1", SYNC_FLAG: "1"})
        try:
            cuda = FakeCuda()
            iv = od.OptCudaInterval(cuda=cuda)
            iv.begin().end(realize=True)
            self.assertEqual(cuda.sync_calls, 1)
            self.assertIsNotNone(iv.elapsed_ms)
        finally:
            _reload({FLAG: "1", SYNC_FLAG: None})

    def test_unavailable_cuda_is_safe(self) -> None:
        cuda = FakeCuda(available=False)
        iv = od.OptCudaInterval(cuda=cuda)
        iv.begin().end()
        self.assertIsNone(iv.elapsed_ms)
        self.assertEqual(cuda.sync_calls, 0)

    def test_transfer_probe_end_to_end_no_extra_sync(self) -> None:
        cuda = FakeCuda()
        tr = FakeTrace()
        model = SimpleNamespace(parameters=lambda: iter([
            FakeTensor(1 << 20, pinned=True),
            FakeTensor(2 << 20),
        ]), buffers=lambda: iter([]))
        probe = od.OptTransferProbe(tr, phase="restore", metadata={"copy_api": "module.to"}, cuda=cuda)
        probe.begin(model)
        time.sleep(0.05)          # cross monotonic ticks so cpu_wall_ms > 0
        probe.end(model)          # caller's sync happens here in real code
        cuda.synchronize()        # the pre-existing sync being reused
        probe.emit("unet_h2d_transfer")
        ev = tr.event("opt_unet_h2d_transfer")
        self.assertIsNotNone(ev)
        if ev is None:
            self.fail("missing event")
        m = ev["metadata"]
        self.assertGreater(m["cpu_wall_ms"], 20.0)
        self.assertEqual(m["source_pinned"], True)
        self.assertEqual(m["tensor_stats"]["count"], 2)  # source scan only
        self.assertEqual(m["tensor_stats"]["total_bytes"], (1 << 20) + (2 << 20))
        self.assertEqual(m["post_tensor_stats"]["count"], 2)  # destination scan
        self.assertIn("effective_gbps", m)
        self.assertIn("stream", m)
        # only the caller's sync — the probe added none
        self.assertEqual(cuda.sync_calls, 1)


class OptimizationDiagnosticsFlagParsingTests(unittest.TestCase):
    """env_flag semantics for the two gates (audit-style)."""

    def _parse(self, value: str | None, sync: str | None) -> tuple[bool, bool]:
        _reload({FLAG: value, SYNC_FLAG: sync})
        try:
            return od.opt_diag_enabled(), od.sync_cuda_allowed()
        finally:
            _reload({FLAG: None, SYNC_FLAG: None})

    def test_absent_is_off(self) -> None:
        self.assertEqual(self._parse(None, None), (False, False))

    def test_truthy_values_on(self) -> None:
        for v in ("1", "true", "TRUE", "yes", "on", " On "):
            self.assertEqual(self._parse(v, None), (True, False), v)

    def test_falsy_values_off(self) -> None:
        for v in ("0", "false", "no", "off", "", "2", "banana"):
            self.assertEqual(self._parse(v, None), (False, False), v)

    def test_sync_flag_independent(self) -> None:
        self.assertEqual(self._parse(None, "1"), (False, True))
        self.assertEqual(self._parse("1", "1"), (True, True))


if __name__ == "__main__":
    unittest.main()
