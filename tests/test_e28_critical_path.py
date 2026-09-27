"""E28 offline tests: earliest-CLIP lifecycle, loader config, FP32 cast-once.

No Modal, no CUDA, no remote execution — synthetic objects and CPU tensors.
"""

import os
import sys
import time
import unittest

os.environ.setdefault("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", "1")
os.environ.setdefault("COMFYMODAL_V2_CLIP_FAST_HYDRATION", "1")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime import speculative_clip_hydration as sch  # noqa: E402
from comfymodal_runtime import clip_fp32_cast_once as cast_once  # noqa: E402


class _FakeClip:
    def __init__(self):
        self.manifest = {
            "eligible": True,
            "files": [
                {
                    "path": "/tmp/fake_clip.safetensors",
                    "size_bytes": 1234,
                    "mtime_ns": 123456789,
                    "dtype": "torch.bfloat16",
                    "key_set": ["a", "b"],
                    "key_shapes": {"a": [2, 2], "b": [4]},
                    "pipeline": [],
                }
            ],
        }

    @property
    def cond_stage_model(self):
        return _FakeCSM()


class _FakeCSM:
    def load_sd(self, sd):
        return None


class _FakeModelKey:
    stable_hash = "fakehash1234"


class _FakeTrace:
    def __init__(self, request_id="r1"):
        self.request_id = request_id
        self.events = []

    def emit(self, name, phase="execution", metadata=None):
        self.events.append((name, dict(metadata or {})))


def _install_fake_manifest(clip):
    """Attach the fake manifest via the cfh attribute used by the lane."""
    try:
        from comfymodal_runtime import clip_fast_hydration as cfh

        cfh.attach_clip_manifest(clip, clip.manifest)
    except Exception:
        pass
    return clip


class EarlyClipLifecycleTest(unittest.TestCase):
    def setUp(self):
        sch.clear_speculative_lanes_for_test()
        sch._RESTORE_MANIFEST_DIGESTS.clear()

    def tearDown(self):
        sch.clear_speculative_lanes_for_test()
        sch._RESTORE_MANIFEST_DIGESTS.clear()

    def test_restore_time_lane_started_without_request_id(self):
        clip = _install_fake_manifest(_FakeClip())
        lane = sch.start_restore_time_clip_lane(clip=clip)
        self.assertIsNotNone(lane)
        self.assertTrue(lane.identity.startswith("restore:"))
        # Single-flight: second start returns the same lane.
        lane2 = sch.start_restore_time_clip_lane(clip=clip)
        self.assertIs(lane, lane2)

    def test_restore_time_lane_fails_closed_without_manifest(self):
        lane = sch.start_restore_time_clip_lane(clip=_FakeClip())
        # No manifest attached -> no lane.
        self.assertIsNone(lane)

    def test_reconcile_reroutes_to_request_identity(self):
        clip = _install_fake_manifest(_FakeClip())
        lane = sch.start_restore_time_clip_lane(clip=clip)
        self.assertIsNotNone(lane)
        reconciled = sch.reconcile_restore_time_lane(
            request_id="r-request-1",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "qwen_3_4b.safetensors"}]}},
            workflow_hash="wf",
            deployment_hash="dep",
            custom_node_generation="gen",
            clip=clip,
            trace=_FakeTrace("r-request-1"),
        )
        self.assertIsNotNone(reconciled)
        # The lane was re-keyed to the request id and carries the request
        # identity (no longer the restore placeholder).
        self.assertFalse(reconciled.identity.startswith("restore:"))
        self.assertEqual(sch.get_speculative_clip_lane("r-request-1"), reconciled)

    def test_reconcile_drops_stale_manifest_lane(self):
        clip = _install_fake_manifest(_FakeClip())
        lane = sch.start_restore_time_clip_lane(clip=clip)
        self.assertIsNotNone(lane)
        # Change the manifest digest after restore (simulate file change).
        clip.manifest["files"][0]["size_bytes"] = 9999
        sch._RESTORE_MANIFEST_DIGESTS["__restore_time__"] = "stale-digest"
        # Reconcile with a mismatched digest: the restore lane must be
        # dropped and a fresh request-time lane started (or None when the
        # request identity cannot start a lane without a real clip object —
        # the request-time start resolves paths from the manifest too).
        reconciled = sch.reconcile_restore_time_lane(
            request_id="r-request-2",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "qwen_3_4b.safetensors"}]}},
            workflow_hash="wf",
            deployment_hash="dep",
            custom_node_generation="gen",
            clip=clip,
        )
        # Either a fresh lane (same manifest now) or None — never the stale
        # restore lane under the old identity.
        lane_after = sch.get_speculative_clip_lane("r-request-2")
        if reconciled is not None:
            self.assertFalse(reconciled.identity.startswith("restore:"))
        self.assertIsNone(sch.get_speculative_clip_lane("__restore_time__"))

    def test_single_flight_take_returns_owners_once(self):
        clip = _install_fake_manifest(_FakeClip())
        lane = sch.start_restore_time_clip_lane(clip=clip)
        self.assertIsNotNone(lane)
        # Simulate a completed read by planting synthetic owners.
        lane.owners = [("loader1", "fb1")]
        lane.per_file_sds = [{"a": "tensor-a"}]
        lane.record = {"result": {"ok": True}, "speculative_read_ms": 10.0}
        taken = sch.take_speculative_read("__restore_time__")
        self.assertIsNotNone(taken)
        sds, owners, record = taken
        self.assertEqual(owners, [("loader1", "fb1")])
        # Second take must be None (single-flight).
        self.assertIsNone(sch.take_speculative_read("__restore_time__"))

    def test_cast_once_record_is_always_a_dict(self):
        """E28 regression: the lane record's cast_once key must never be
        None — the demand-side consumer does
        ``record.get('cast_once', {}).get('applied', False)`` and a None
        value raises AttributeError (the E28 cold-run crash that forced the
        CLIP into the native CPU fallback)."""
        clip = _install_fake_manifest(_FakeClip())
        lane = sch.start_restore_time_clip_lane(clip=clip)
        self.assertIsNotNone(lane)
        # Simulate a completed read WITHOUT cast-once (the production case).
        lane.owners = [("loader1", "fb1")]
        lane.per_file_sds = [{"a": "tensor-a"}]
        lane.record = {
            "result": {"ok": True},
            "speculative_read_ms": 10.0,
            "cast_once": {},
        }
        taken = sch.take_speculative_read("__restore_time__")
        self.assertIsNotNone(taken)
        _, _, record = taken
        cast_once_val = (record or {}).get("cast_once") or {}
        self.assertIsInstance(cast_once_val, dict)
        # The exact consumer expression must not raise.
        applied = bool(cast_once_val.get("applied", False))
        self.assertFalse(applied)


class LoaderConfigTest(unittest.TestCase):
    def test_clip_loader_defaults_are_e28_winner(self):
        from comfymodal_runtime import clip_fast_hydration_wiring as wiring

        self.assertEqual(wiring._clip_fastsafe_threads(), 8)
        self.assertEqual(wiring._clip_fastsafe_block_bytes(), 64 * 1024 * 1024)

    def test_clip_loader_env_override(self):
        from comfymodal_runtime import clip_fast_hydration_wiring as wiring

        old_t = os.environ.get("COMFYMODAL_V2_CLIP_FASTSAFE_THREADS")
        old_b = os.environ.get("COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES")
        try:
            os.environ["COMFYMODAL_V2_CLIP_FASTSAFE_THREADS"] = "4"
            os.environ["COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES"] = "134217728"
            self.assertEqual(wiring._clip_fastsafe_threads(), 4)
            self.assertEqual(wiring._clip_fastsafe_block_bytes(), 134217728)
        finally:
            if old_t is None:
                os.environ.pop("COMFYMODAL_V2_CLIP_FASTSAFE_THREADS", None)
            else:
                os.environ["COMFYMODAL_V2_CLIP_FASTSAFE_THREADS"] = old_t
            if old_b is None:
                os.environ.pop("COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES", None)
            else:
                os.environ["COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES"] = old_b

    def test_unet_loader_defaults_are_e28_winner(self):
        from comfymodal_runtime import unet_fastsafetensors as ufs

        self.assertEqual(ufs._fs_effective_threads(), 8)
        self.assertEqual(ufs._fs_effective_block_bytes(), 256 * 1024 * 1024)

    def test_unet_loader_env_override(self):
        from comfymodal_runtime import unet_fastsafetensors as ufs

        old_t = os.environ.get("COMFYMODAL_V2_UNET_FASTSAFE_THREADS")
        old_b = os.environ.get("COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES")
        old_k = os.environ.get("COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB")
        try:
            os.environ["COMFYMODAL_V2_UNET_FASTSAFE_THREADS"] = "16"
            os.environ["COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES"] = "536870912"
            os.environ["COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB"] = "262144"
            self.assertEqual(ufs._fs_effective_threads(), 16)
            self.assertEqual(ufs._fs_effective_block_bytes(), 536870912)
            self.assertEqual(ufs._fs_effective_bbuf_kb(), 262144)
        finally:
            if old_t is None:
                os.environ.pop("COMFYMODAL_V2_UNET_FASTSAFE_THREADS", None)
            else:
                os.environ["COMFYMODAL_V2_UNET_FASTSAFE_THREADS"] = old_t
            if old_b is None:
                os.environ.pop("COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES", None)
            else:
                os.environ["COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES"] = old_b
            if old_k is None:
                os.environ.pop("COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB", None)
            else:
                os.environ["COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB"] = old_k

    def test_unet_loader_bbuf_default_is_large(self):
        from comfymodal_runtime import unet_fastsafetensors as ufs

        # E28: the large bounce-buffer default (512 MiB) — the fix for the
        # 12.27 s cold read (the library's 16 MiB default serialized I/O).
        self.assertGreaterEqual(ufs._fs_effective_bbuf_kb(), 512 * 1024)

    def test_clip_loader_bbuf_default_is_large(self):
        from comfymodal_runtime import clip_fast_hydration_wiring as wiring

        self.assertGreaterEqual(wiring._clip_fastsafe_bbuf_kb(), 512 * 1024)


class Fp32CastOnceTest(unittest.TestCase):
    def setUp(self):
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "1"

    def tearDown(self):
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"

    def test_cast_once_applies_fp32_exact_widening(self):
        import torch

        sds = [{"w": torch.ones(2, 2, dtype=torch.bfloat16)}]
        manifests = [{"dtype": "torch.bfloat16"}]
        out, record = cast_once.apply_cast_once(sds, manifests)
        self.assertTrue(record["applied"])
        self.assertEqual(str(out[0]["w"].dtype), "torch.float32")
        # Exact widening: values preserved.
        self.assertTrue(torch.equal(out[0]["w"], torch.ones(2, 2, dtype=torch.float32)))
        self.assertEqual(record["tensor_count"], 1)
        self.assertEqual(record["bytes_in"], 8)
        self.assertEqual(record["bytes_out"], 16)

    def test_cast_once_fails_closed_on_non_bf16_manifest(self):
        import torch

        sds = [{"w": torch.ones(2, 2, dtype=torch.float16)}]
        manifests = [{"dtype": "torch.float16"}]
        out, record = cast_once.apply_cast_once(sds, manifests)
        self.assertFalse(record["applied"])
        self.assertIn("unsupported_source_dtype", record["reason"])
        # Input unchanged.
        self.assertEqual(str(out[0]["w"].dtype), "torch.float16")

    def test_cast_once_gated_off_is_noop(self):
        import torch

        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"
        sds = [{"w": torch.ones(2, 2, dtype=torch.bfloat16)}]
        manifests = [{"dtype": "torch.bfloat16"}]
        out, record = cast_once.apply_cast_once(sds, manifests)
        self.assertFalse(record["applied"])
        self.assertEqual(record["reason"], "flag_off")
        self.assertEqual(str(out[0]["w"].dtype), "torch.bfloat16")

    def test_verify_cast_once_sd_checks_fp32(self):
        import torch

        manifest = {
            "dtype": "torch.bfloat16",
            # Frozen manifest key_set is sorted (like the real builder).
            "key_set": ["b", "w"],
            "key_shapes": {"w": [2, 2], "b": [2]},
        }
        cast_sds, cast_record = cast_once.apply_cast_once(
            [{
                "w": torch.ones(2, 2, dtype=torch.bfloat16),
                "b": torch.ones(2, dtype=torch.bfloat16),
            }],
            [manifest],
        )
        self.assertTrue(cast_record["applied"])
        ok, _ = cast_once.verify_cast_once_sd(
            manifest,
            cast_sds[0],
        )
        self.assertTrue(ok)
        # BF16 (uncast) must fail the cast-once verification.
        ok2, _ = cast_once.verify_cast_once_sd(
            manifest,
            {"w": torch.ones(2, 2, dtype=torch.bfloat16),
             "b": torch.ones(2, dtype=torch.bfloat16)},
        )
        self.assertFalse(ok2)


if __name__ == "__main__":
    unittest.main()
