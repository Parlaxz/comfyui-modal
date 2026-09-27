"""Focused tests for the variance storage-registry enhancements.

Covers, CPU-only (real torch where available, duck-typed fakes otherwise):
  1  _merge_overlapping_intervals dedups aliased/overlapping intervals
  2  build_unique_storage_registry dedups shared-storage views (alias_count)
  3  build_unique_storage_registry reports unsupported entries (meta/sparse/
     empty/non-CPU) separately, never run-fatal
  4  non-contiguous tensors are still scanned via their backing storage
  5  alias/overlap/unsupported counts surface on the registry
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_HAS_TORCH = False
try:
    import torch
    _HAS_TORCH = True
except ImportError:
    torch = None

from comfymodal_runtime.cpu_snapshot_models import (
    StorageRange,
    StorageRegistry,
    _merge_overlapping_intervals,
    _tensor_support_class,
    build_unique_storage_registry,
)


class _FakeStorage:
    def __init__(self, ptr, nbytes):
        self._ptr = ptr
        self._nbytes = nbytes

    def data_ptr(self):
        return self._ptr

    def nbytes(self):
        return self._nbytes


class _FakeTensor:
    _storage: "_FakeStorage | None"

    def __init__(self, device="cpu", is_meta=False, numel=1,
                 is_sparse=False, is_quantized=False, is_mkldnn=False):
        self.device = device
        self.is_meta = is_meta
        self._numel = numel
        self.is_sparse = is_sparse
        self.is_quantized = is_quantized
        self.is_mkldnn = is_mkldnn
        self.element_size = lambda: 4
        self._storage = None

    def numel(self):
        return self._numel

    def untyped_storage(self):
        return self._storage

    def storage(self):
        return self._storage


class _FakeModule:
    def __init__(self, tensors):
        self._tensors = list(tensors)

    def parameters(self):
        return iter(self._tensors)

    def buffers(self):
        return iter([])


class MergeIntervalsTest(unittest.TestCase):
    def test_merge_overlapping_intervals(self):
        merged, overlap_count, overlap_bytes = _merge_overlapping_intervals(
            [(100, 100), (150, 100), (1000, 50)]
        )
        self.assertEqual(merged, [(100, 150), (1000, 50)])
        self.assertEqual(overlap_count, 1)
        self.assertEqual(overlap_bytes, 50)  # raw 250 - union 200

    def test_merge_contained_intervals(self):
        merged, overlap_count, _ = _merge_overlapping_intervals(
            [(1000, 500), (1200, 100)]
        )
        self.assertEqual(merged, [(1000, 500)])
        self.assertEqual(overlap_count, 1)

    def test_merge_disjoint_no_overlap(self):
        merged, overlap_count, overlap_bytes = _merge_overlapping_intervals(
            [(100, 100), (1000, 50)]
        )
        self.assertEqual(merged, [(100, 100), (1000, 50)])
        self.assertEqual(overlap_count, 0)
        self.assertEqual(overlap_bytes, 0)

    def test_empty(self):
        self.assertEqual(_merge_overlapping_intervals([]), ([], 0, 0))


class RegistryDedupTest(unittest.TestCase):
    def _storage_tensor(self, ptr, nbytes):
        t = _FakeTensor()
        t._storage = _FakeStorage(ptr, nbytes)
        return t

    def test_shared_storage_view_dedup(self):
        st = _FakeStorage(ptr=4096, nbytes=8192)
        t1 = _FakeTensor()
        t1._storage = st
        t2 = _FakeTensor()
        t2._storage = st  # same storage object -> alias
        reg = build_unique_storage_registry(_FakeModule([t1, t2]))
        self.assertEqual(reg.unique_storage_count, 1)
        self.assertEqual(reg.alias_count, 1)
        self.assertEqual(len(reg.ranges), 1)
        self.assertEqual(reg.total_bytes, 8192)

    def test_exact_duplicate_range_dedup(self):
        t1 = self._storage_tensor(4096, 4096)
        t2 = self._storage_tensor(4096, 4096)  # distinct storage, same range
        reg = build_unique_storage_registry(_FakeModule([t1, t2]))
        self.assertEqual(reg.unique_storage_count, 1)
        self.assertEqual(reg.alias_count, 1)
        self.assertEqual(reg.total_bytes, 4096)

    def test_unsupported_entries_reported_not_fatal(self):
        supported = self._storage_tensor(4096, 4096)
        meta = _FakeTensor(is_meta=True)
        sparse = _FakeTensor(is_sparse=True)
        empty = _FakeTensor(numel=0)
        noncpu = _FakeTensor(device="cuda")
        quantized = _FakeTensor(is_quantized=True)
        reg = build_unique_storage_registry(
            _FakeModule([supported, meta, sparse, empty, noncpu, quantized])
        )
        self.assertEqual(reg.unique_storage_count, 1)
        self.assertEqual(reg.total_bytes, 4096)
        self.assertEqual(reg.unsupported_count, 5)
        reasons = {entry["reason"] for entry in reg.unsupported_entries}
        self.assertEqual(reasons, {"meta", "sparse", "empty", "device:cuda", "quantized"})
        self.assertEqual(len(reg.ranges), 1)

    def test_non_contiguous_still_scanned(self):
        if not _HAS_TORCH:
            self.skipTest("torch required")
        base = torch.empty(8, 8)
        view = base.t().contiguous()
        # Two distinct parameters with distinct storages -> 2 ranges.
        mod = _FakeModule([torch.nn.Parameter(base), torch.nn.Parameter(view)])
        reg = build_unique_storage_registry(mod)
        self.assertEqual(reg.unique_storage_count, 2)
        self.assertEqual(reg.total_bytes, base.numel() * 4 + view.numel() * 4)
        self.assertEqual(reg.unsupported_count, 0)


class SupportClassTest(unittest.TestCase):
    def test_tensor_support_class(self):
        self.assertEqual(_tensor_support_class(_FakeTensor()), (True, ""))
        self.assertEqual(_tensor_support_class(_FakeTensor(is_meta=True)), (False, "meta"))
        self.assertEqual(_tensor_support_class(_FakeTensor(is_sparse=True)), (False, "sparse"))
        self.assertEqual(_tensor_support_class(_FakeTensor(numel=0)), (False, "empty"))
        self.assertEqual(_tensor_support_class(_FakeTensor(device="cuda")), (False, "device:cuda"))


class RegistryAccountingTest(unittest.TestCase):
    def _storage_tensor(self, ptr, nbytes):
        t = _FakeTensor()
        t._storage = _FakeStorage(ptr, nbytes)
        return t

    def test_registry_accounting_from_registry(self):
        from comfymodal_runtime import variance_diagnostics as vd
        reg = build_unique_storage_registry(_FakeModule([self._storage_tensor(4096, 4096)]))
        acc = vd.registry_accounting(reg)
        self.assertEqual(acc["unique_storage_count"], 1)
        self.assertEqual(acc["total_bytes"], 4096)
        self.assertEqual(acc["unsupported_count"], 0)
        self.assertGreaterEqual(acc["expected_pages"], 1)
        self.assertEqual(acc["alias_count"], 0)
        self.assertEqual(acc["overlap_count"], 0)

    def test_registry_accounting_from_model(self):
        from comfymodal_runtime import variance_diagnostics as vd
        # Alias/overlap/unsupported surface but never fail the accounting.
        supported = self._storage_tensor(4096, 4096)
        alias = self._storage_tensor(4096, 4096)  # exact duplicate range
        meta = _FakeTensor(is_meta=True)
        acc = vd.registry_accounting(_FakeModule([supported, alias, meta]))
        self.assertEqual(acc["unique_storage_count"], 1)
        self.assertEqual(acc["alias_count"], 1)
        self.assertEqual(acc["unsupported_count"], 1)
        self.assertEqual(acc["total_bytes"], 4096)
        self.assertGreaterEqual(acc["expected_pages"], 1)


class ActivationPublicationTest(unittest.TestCase):
    def test_publication_from_existing_boundary(self):
        from comfymodal_runtime import variance_diagnostics as vd
        from comfymodal_runtime.trace import RuntimeTrace
        trace = RuntimeTrace(request_id="r1")
        trace.emit("unet_early_activation_scheduled", phase="execution")
        trace.emit("unet_early_activation_completed", phase="execution")
        ms, source = vd.activation_publication_ms(trace)
        self.assertIsInstance(ms, float)
        self.assertEqual(source, "early_activation_completed")

    def test_publication_unavailable_when_absent(self):
        from comfymodal_runtime import variance_diagnostics as vd
        from comfymodal_runtime.trace import RuntimeTrace
        trace = RuntimeTrace(request_id="r1")
        self.assertEqual(vd.activation_publication_ms(trace), (None, "unavailable"))
        self.assertEqual(vd.activation_publication_ms(None), (None, "unavailable"))


if __name__ == "__main__":
    unittest.main()
