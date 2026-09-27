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
            # True total early-activation wall (scheduled -> completed).
            trace.emit_at("unet_early_activation_scheduled",
                          wall_unix_ns=1_000_000_000, monotonic_ns=1_000_000_000)
            trace.emit_at("unet_early_activation_completed",
                          wall_unix_ns=1_003_000_000, monotonic_ns=1_003_000_000)
            mp._emit_unet_worker_variance(
                trace, state={"submitted_mono_ns": 1_000_000_000,
                              "worker_started_mono_ns": 1_000_000_000,
                              "unet_resolved_mono_ns": 1_000_000_000},
                request_id="r1", mode="sampling_end",
                registry_setup=_reg, page_traversal=None,
                synchronized_load=_sync, pretouch_record=None,
                registry_record={"unique_storage_count": 1234, "total_bytes": 500},
                patcher_ms=0.5, patcher_counts={"cast_count": 10}, patcher_nested=True,
            )
        event = next(e for e in trace.events if e.name == "unet_activation_worker_variance")
        self.assertEqual(event.metadata["loader_reconciliation"]["reconciliation_status"], "complete")
        self.assertEqual(event.metadata["patcher_bookkeeping_nested"], True)
        self.assertEqual(event.metadata["synchronized_load"]["stage"], "synchronized_load")
        # Reconciled against the TRUE total (3 ms), not the self-sum.
        self.assertEqual(event.metadata["loader_reconciliation"]["loader_wall_ms"], 3.0)
        self.assertEqual(event.metadata["early_activation_total_ms"], 3.0)

    def test_emit_worker_variance_emits_queue_cpu_wait_and_new_stages(self):
        trace = RuntimeTrace(request_id="r2")
        with patch.dict(os.environ, {"COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "1"},
                        clear=False):
            _reg = vd.deltas_with_evidence(self._snap(1_000_000), self._snap(2_000_000))
            _sync = vd.deltas_with_evidence(self._snap(2_000_000), self._snap(4_000_000))
            _reg["wall_ms"] = 1.0
            _sync["wall_ms"] = 2.0
            _dtype = vd.deltas_with_evidence(self._snap(4_000_000), self._snap(5_000_000))
            _dtype["wall_ms"] = 1.0
            _bb = vd.deltas_with_evidence(self._snap(5_000_000), self._snap(7_000_000))
            _bb["wall_ms"] = 2.0
            trace.emit_at("unet_early_activation_scheduled",
                          wall_unix_ns=1_000_000_000, monotonic_ns=1_000_000_000)
            trace.emit_at("unet_early_activation_completed",
                          wall_unix_ns=1_050_000_000, monotonic_ns=1_050_000_000)
            mp._emit_unet_worker_variance(
                trace,
                state={
                    "submitted_mono_ns": 1_000_000_000,
                    "worker_started_mono_ns": 1_005_000_000,
                    "unet_resolved_mono_ns": 1_010_000_000,
                },
                request_id="r2", mode="clip_gpu_ready",
                registry_setup=_reg, page_traversal=None,
                synchronized_load=_sync, pretouch_record=None,
                registry_record=None,
                patcher_ms=None, patcher_counts={}, patcher_nested=False,
                dtype_layout_preparation=_dtype,
                post_load_bookkeeping=_bb,
            )
        event = next(e for e in trace.events if e.name == "unet_activation_worker_variance")
        meta = event.metadata
        # Queue delay = worker_started - submitted = 5 ms.
        self.assertEqual(meta["queue_delay_ms"], 5.0)
        # CPU-snapshot wait = unet_resolved - worker_started = 5 ms.
        self.assertEqual(meta["cpu_snapshot_wait_ms"], 5.0)
        # True total = completed - scheduled = 50 ms.
        self.assertEqual(meta["early_activation_total_ms"], 50.0)
        # New stage records are carried through.
        self.assertEqual(meta["dtype_layout_preparation"]["wall_ms"], 1.0)
        self.assertEqual(meta["post_load_bookkeeping"]["wall_ms"], 2.0)
        # loader_reconciliation reconciles against the TRUE total (50 ms), not
        # the self-sum of the measured sub-stages.
        self.assertEqual(meta["loader_reconciliation"]["loader_wall_ms"], 50.0)

    def test_emit_worker_variance_missing_timestamps_are_none(self):
        trace = RuntimeTrace(request_id="r3")
        with patch.dict(os.environ, {"COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "1"},
                        clear=False):
            mp._emit_unet_worker_variance(
                trace, state={},
                request_id="r3", mode="late",
                registry_setup=None, page_traversal=None,
                synchronized_load=None, pretouch_record=None,
                registry_record=None,
                patcher_ms=None, patcher_counts={}, patcher_nested=False,
            )
        event = next(e for e in trace.events if e.name == "unet_activation_worker_variance")
        meta = event.metadata
        self.assertIsNone(meta["queue_delay_ms"])
        self.assertIsNone(meta["cpu_snapshot_wait_ms"])
        self.assertIsNone(meta["early_activation_total_ms"])
        self.assertIsNone(meta["dtype_layout_preparation"])
        self.assertIsNone(meta["post_load_bookkeeping"])


class _FakeStorage:
    def __init__(self, ptr, nbytes):
        self._ptr = ptr
        self._nbytes = nbytes

    def data_ptr(self):
        return self._ptr

    def nbytes(self):
        return self._nbytes


class _PinnedTensor:
    def __init__(self, storage, is_cuda=False):
        self._storage = storage
        self._cuda = is_cuda

    @property
    def is_cuda(self):
        return self._cuda

    def untyped_storage(self):
        return self._storage

    def storage(self):
        return self._storage


class _PinnedModel:
    def __init__(self, tensors):
        self._tensors = tensors

    def parameters(self):
        return iter(self._tensors)

    def buffers(self):
        return iter([])


class _RaisingCudart:
    def cudaHostRegister(self, ptr, nbytes, flags):
        raise RuntimeError("cuda")


def _fake_torch_with_cudart(cudart_cls):
    """Build a minimal fake ``torch`` module whose ``cuda.cudart()`` returns a
    fresh *cudart_cls* instance.  ``cudart`` is attached as an instance
    attribute (not a class lambda) so accessing it on the instance does not
    bind ``self`` and turn it into a bound method."""
    cuda_obj = type("Cuda", (), {})()
    cuda_obj.cudart = lambda: cudart_cls()
    return type("Torch", (), {"cuda": cuda_obj})()


class PinnedTransferTest(unittest.TestCase):
    def test_pinned_transfer_enabled_flag(self):
        with patch.dict(os.environ, {"COMFYMODAL_V2_PIN_UNET_TRANSFER": "on"},
                        clear=False):
            self.assertTrue(mp._pinned_transfer_enabled())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYMODAL_V2_PIN_UNET_TRANSFER", None)
            self.assertFalse(mp._pinned_transfer_enabled())
        for val in ("1", "true", "yes", "on"):
            with patch.dict(os.environ, {"COMFYMODAL_V2_PIN_UNET_TRANSFER": val},
                            clear=False):
                self.assertTrue(mp._pinned_transfer_enabled())

    def test_pin_cpu_storages_registers_and_dedupes(self):
        registers = []
        unregisters = []

        class FakeCudart:
            def cudaHostRegister(self, ptr, nbytes, flags):
                registers.append((ptr, nbytes, flags))

            def cudaHostUnregister(self, ptr):
                unregisters.append(ptr)

        fake_torch = _fake_torch_with_cudart(FakeCudart)
        model = _PinnedModel([
            _PinnedTensor(_FakeStorage(0x1000, 100)),
            _PinnedTensor(_FakeStorage(0x2000, 200)),
            _PinnedTensor(_FakeStorage(0x1000, 100)),  # duplicate ptr+nbytes
            _PinnedTensor(_FakeStorage(0x3000, 0)),    # zero nbytes -> skip
            _PinnedTensor(_FakeStorage(0x4000, 100), is_cuda=True),  # CUDA -> skip
        ])
        with patch.dict(sys.modules, {"torch": fake_torch}):
            pins = mp._pin_cpu_storages_for_transfer(model)
        self.assertEqual(registers, [(0x1000, 100, 0), (0x2000, 200, 0)])
        self.assertEqual(len(pins), 2)
        for unpin in pins:
            unpin()
        self.assertEqual(sorted(unregisters), [0x1000, 0x2000])

    def test_pin_cpu_storages_empty_on_missing_cudart(self):
        fake_torch = type("Torch", (), {"cuda": type("Cuda", (), {})()})()
        fake_torch.cuda.cudart = lambda: None
        model = _PinnedModel([_PinnedTensor(_FakeStorage(0x1000, 100))])
        with patch.dict(sys.modules, {"torch": fake_torch}):
            self.assertEqual(mp._pin_cpu_storages_for_transfer(model), [])

    def test_pin_cpu_storages_never_raises(self):
        fake_torch = _fake_torch_with_cudart(_RaisingCudart)
        model = _PinnedModel([_PinnedTensor(_FakeStorage(0x1000, 100))])
        with patch.dict(sys.modules, {"torch": fake_torch}):
            self.assertEqual(mp._pin_cpu_storages_for_transfer(model), [])

    def test_worker_load_try_finally_unpins_on_load_failure(self):
        """When _mm_load_models_gpu raises, the finally block still unpins the
        registered host storages before the failure is returned."""
        unregisters = []

        def fake_unpin():
            unregisters.append("unpinned")

        with patch.object(mp, "_pinned_transfer_enabled", return_value=True), \
             patch.object(mp, "_pin_cpu_storages_for_transfer",
                          return_value=[fake_unpin]), \
             patch.object(mp, "_mm_load_models_gpu",
                          side_effect=RuntimeError("load boom")), \
             patch.object(mp, "_check_early_activation_vram",
                          return_value={"ok": True, "clip_retained": False}), \
             patch.object(mp, "_resolve_clip_patcher", return_value=None), \
             patch.object(mp, "_unet_loaded_bytes", return_value=0), \
             patch.object(mp, "_gpu_allocated_bytes", return_value=0), \
             patch.object(mp, "_capture_phase_counters", return_value={}):
            from types import SimpleNamespace
            bridge = SimpleNamespace(coordinator=SimpleNamespace(
                wait_unet=lambda *a, **k: _PinnedModel([_PinnedTensor(_FakeStorage(0x1, 1))]),
            ))
            state = {}
            result = mp._run_early_unet_activation(
                bridge, prep=None, trace=None, request_id="r_pin",
                state=state, clip=None, key_hash="h", mode="late",
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "load_failed")
        # The finally unpinned even though the load raised.
        self.assertEqual(unregisters, ["unpinned"])


if __name__ == "__main__":
    unittest.main()
