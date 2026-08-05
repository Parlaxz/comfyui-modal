"""Focused tests for the early-activation worker CPU-registry source selection.

Covers, CPU-only (fake modules/tensors, no CUDA/Modal):
  1  _model_is_cpu_resident distinguishes CPU vs CUDA first param
  2  _resolve_unet_cpu_registry_from_model uses worker-attached registry
  3  _resolve_unet_cpu_registry_from_model builds fresh on a CPU model
  4  live-root-cause: a post-transfer CUDA model must NOT erase the retained
     CPU registry (attached registry wins over a CUDA model)
  5  _resolve_unet_cpu_registry_from_model -> post_transfer_unavailable when
     CUDA model has no attached registry
  6  _resolve_unet_cpu_pretouch_from_model returns the attached pretouch
  7  _emit_unet_worker_variance emits a reconciliation-complete record
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from comfymodal_runtime import model_preload as mp
from comfymodal_runtime import variance_diagnostics as vd
from comfymodal_runtime.trace import RuntimeTrace


class _FakeTensor:
    def __init__(self, device="cpu"):
        self.device = device


class _FakeModel:
    def __init__(self, device="cpu"):
        self._param = _FakeTensor(device)

    def parameters(self):
        return iter([self._param])

    def buffers(self):
        return iter([])


class ModelResidencyTest(unittest.TestCase):
    def test_cpu_resident_true(self):
        self.assertTrue(mp._model_is_cpu_resident(_FakeModel("cpu")))

    def test_cuda_resident_false(self):
        self.assertFalse(mp._model_is_cpu_resident(_FakeModel("cuda")))


class RegistrySourceTest(unittest.TestCase):
    def test_worker_attached_registry_wins(self):
        unet = _FakeModel("cuda")  # post-transfer model
        attached = {"unique_storage_count": 1234, "total_bytes": 5_000_000_000,
                    "expected_pages": 1_000_000, "source": "worker_attached"}
        setattr(unet, mp._CPU_STORAGE_REGISTRY_ATTR, attached)
        rec, source = mp._resolve_unet_cpu_registry_from_model(unet)
        self.assertIsNotNone(rec)
        self.assertEqual(source, "worker_attached")
        # Attached CPU registry must NOT be erased by the CUDA model.
        self.assertEqual(rec["unique_storage_count"], 1234)
        self.assertEqual(rec["total_bytes"], 5_000_000_000)

    def test_fresh_build_on_cpu_model(self):
        unet = _FakeModel("cpu")
        with patch.object(mp, "registry_accounting",
                          return_value={"unique_storage_count": 7, "total_bytes": 100}):
            rec, source = mp._resolve_unet_cpu_registry_from_model(unet)
        self.assertIsNotNone(rec)
        self.assertEqual(source, "fresh_cpu")
        self.assertEqual(rec["total_bytes"], 100)

    def test_post_transfer_unavailable(self):
        unet = _FakeModel("cuda")  # no attached registry
        rec, source = mp._resolve_unet_cpu_registry_from_model(unet)
        self.assertIsNone(rec)
        self.assertEqual(source, "post_transfer_unavailable")

    def test_none_model(self):
        rec, source = mp._resolve_unet_cpu_registry_from_model(None)
        self.assertIsNone(rec)
        self.assertEqual(source, "no_registered_unet")

    def test_attached_pretouch_resolved(self):
        unet = _FakeModel("cuda")
        setattr(unet, mp._CPU_PRETOUCH_ATTR, {"status": "ok", "checksum": 42})
        self.assertEqual(mp._resolve_unet_cpu_pretouch_from_model(unet),
                         {"status": "ok", "checksum": 42})
        self.assertIsNone(mp._resolve_unet_cpu_pretouch_from_model(_FakeModel("cpu")))


class WorkerVarianceEmitTest(unittest.TestCase):
    def _snap(self, mono):
        return {
            "mono_ns": mono,
            "wall_unix_ns": mono,
            "process_cpu_ns": mono,
            "thread_cpu_ns": mono,
            "native_tid": 7,
            "faults": {"major_faults": 0, "minor_faults": 0},
            "rss_bytes": 100,
            "smaps_rollup": None,
            "io": None,
            "numa": None,
            "threads": None,
            "native_thread_count": 4,
            "fingerprint": {"pid": "1"},
        }

    def test_emit_worker_variance_reconciliation_complete(self):
        trace = RuntimeTrace(request_id="r1")
        with patch.dict(os.environ, {"COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "1"},
                        clear=False):
            _reg = vd.deltas_with_evidence(self._snap(1_000_000), self._snap(2_000_000))
            _sync = vd.deltas_with_evidence(self._snap(2_000_000), self._snap(4_000_000))
            _reg["wall_ms"] = 1.0
            _reg["stage"] = "registry_setup"
            _sync["wall_ms"] = 2.0
            _sync["stage"] = "synchronized_load"
            mp._emit_unet_worker_variance(
                trace, request_id="r1", mode="sampling_end",
                registry_setup=_reg, page_traversal=None,
                synchronized_load=_sync, pretouch_record=None,
                registry_record={"unique_storage_count": 1234, "total_bytes": 500},
                patcher_ms=0.5, patcher_counts={"cast_count": 10}, patcher_nested=True,
            )
        event = next(e for e in trace.events if e.name == "unet_activation_worker_variance")
        self.assertEqual(event.metadata["loader_reconciliation"]["reconciliation_status"], "complete")
        self.assertEqual(event.metadata["patcher_bookkeeping_nested"], True)
        self.assertEqual(event.metadata["synchronized_load"]["stage"], "synchronized_load")


if __name__ == "__main__":
    unittest.main()
