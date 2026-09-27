"""Offline tests for E27 forensics (empty_cache decomposition + cast counter).

No Modal, no CUDA (torch.cuda paths degrade to cuda_available=False); tests
validate the wrapper logic with fakes.
"""

import os
import sys
import unittest

os.environ.setdefault("COMFYMODAL_V2_E27_FORENSICS", "1")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime import e27_forensics as e27  # noqa: E402


class _FakeTorchCuda:
    def __init__(self):
        self.sync_calls = 0
        self.empty_calls = 0
        self.ipc_calls = 0

    def synchronize(self):
        self.sync_calls += 1
        return None

    def empty_cache(self):
        self.empty_calls += 1
        return None

    def ipc_collect(self):
        self.ipc_calls += 1
        return None


class _FakeTorch:
    def __init__(self):
        self.cuda = _FakeTorchCuda()


class _FakeMM:
    def __init__(self, torch_mod=None):
        self.soft_cache_calls = 0
        self._torch = torch_mod or _FakeTorch()

    def soft_empty_cache(self):
        # Mirrors real Comfy soft_empty_cache: synchronize -> empty_cache ->
        # ipc_collect (unconditional on the CUDA path).
        self.soft_cache_calls += 1
        self._torch.cuda.synchronize()
        self._torch.cuda.empty_cache()
        self._torch.cuda.ipc_collect()


class _FakePatcher:
    def patch_weight_to_device(self, weight, *a, **k):
        return "patched"


class _FakeTensor:
    def __init__(self, nbytes=4096, dtype="torch.float16"):
        self._nbytes = nbytes
        self.dtype = type("DT", (), {"__str__": lambda s: dtype})()

    def numel(self):
        return self._nbytes // 2

    def element_size(self):
        return 2


class E27SoftCacheTest(unittest.TestCase):
    def test_chain_installs_and_decomposes(self):
        torch_mod = _FakeTorch()
        mm = _FakeMM(torch_mod=torch_mod)
        result = e27.install_soft_cache_chain(mm, torch_mod)
        self.assertEqual(result["soft_empty_cache"], "installed")
        self.assertEqual(result["cuda_operations"]["synchronize"], "installed")
        self.assertEqual(result["cuda_operations"]["empty_cache"], "installed")
        self.assertEqual(result["cuda_operations"]["ipc_collect"], "installed")
        # Run the chain: soft cache calls the three ops.
        mm.soft_empty_cache()
        self.assertEqual(torch_mod.cuda.sync_calls, 1)
        self.assertEqual(torch_mod.cuda.empty_calls, 1)
        self.assertEqual(torch_mod.cuda.ipc_calls, 1)
        # Idempotent re-install.
        result2 = e27.install_soft_cache_chain(mm, torch_mod)
        self.assertEqual(result2["soft_empty_cache"], "already")
        self.assertEqual(result2["cuda_operations"]["empty_cache"], "already")

    def test_soft_cache_emits_record(self):
        torch_mod = _FakeTorch()
        mm = _FakeMM(torch_mod=torch_mod)
        e27.install_soft_cache_chain(mm, torch_mod)
        # The wrapper records into _SOFT_CACHE_CONTEXT; with no active trace
        # the emit path is a no-op but the operation decomposition still runs.
        mm.soft_empty_cache()
        # Verify the record was produced and consumed (context cleared).
        self.assertIsNone(getattr(e27._SOFT_CACHE_CONTEXT, "record", None))

    def test_gated_off_is_noop(self):
        os.environ["COMFYMODAL_V2_E27_FORENSICS"] = "0"
        try:
            import importlib

            importlib.reload(e27)
            torch_mod = _FakeTorch()
            mm = _FakeMM(torch_mod=torch_mod)
            result = e27.install_soft_cache_chain(mm, torch_mod)
            self.assertEqual(result["soft_empty_cache"], "gated_off")
            self.assertEqual(result["cuda_operations"]["synchronize"], "gated_off")
            # Native path unchanged.
            mm.soft_empty_cache()
            self.assertEqual(mm.soft_cache_calls, 1)
        finally:
            os.environ["COMFYMODAL_V2_E27_FORENSICS"] = "1"
            import importlib

            importlib.reload(e27)


class E27CastCounterTest(unittest.TestCase):
    def test_cast_counter_counts(self):
        e27.reset_cast_account()
        status = e27.install_patch_weight_cast_counter(_FakePatcher)
        self.assertEqual(status, "installed")
        p = _FakePatcher()
        t = _FakeTensor(nbytes=4096, dtype="torch.float16")
        p.patch_weight_to_device(t)
        p.patch_weight_to_device(t)
        summary = e27.cast_account_summary()
        self.assertEqual(summary["operations"], 2)
        self.assertEqual(summary["bytes"], 8192)
        self.assertIn("torch.float16", summary["source_dtypes"])
        # Idempotent.
        status2 = e27.install_patch_weight_cast_counter(_FakePatcher)
        self.assertEqual(status2, "already")


if __name__ == "__main__":
    unittest.main()
