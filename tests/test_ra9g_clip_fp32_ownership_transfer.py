"""RA9G: request-local CLIP FP32 ownership-transfer contract.

These tests use CPU tensors and deliberately exercise the protocol rather
than CUDA or the production loader.  The production adapter can provide the
same bind receipt and the existing source-owner retirement callback.
"""

import os
import sys
import unittest
from unittest import mock

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from comfymodal_runtime import clip_fp32_cast_once as ra9g  # noqa: E402
from comfymodal_runtime import clip_fast_hydration as cfh  # noqa: E402
from comfymodal_runtime import clip_fast_hydration_wiring as wiring  # noqa: E402


class _Owner:
    def __init__(self):
        self.released = 0

    def release_storage(self, purge_allocator=False):
        self.released += 1


class _FlakyOwner:
    def __init__(self):
        self.calls = 0

    def release_storage(self, purge_allocator=False):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary release failure")


def _fixture(*, generation="manifest-1", scope="clip.transformer", device="cpu"):
    source = {"weight": torch.arange(4, dtype=torch.bfloat16)}
    manifests = [{
        "dtype": "torch.bfloat16",
        "key_set": ["weight"],
        "key_shapes": {"weight": [4]},
    }]
    identity = ra9g.build_source_manifest_identity(
        manifests,
        identity={
            "checkpoint_identity": "checkpoint-1",
            "manifest_generation": generation,
            "selected_tensor_scope": scope,
            "model_patch_identity": "patch-1",
        },
        target_device=device,
    )
    return source, manifests, identity


def _transfer(*, generation="manifest-1", device="cpu"):
    source, manifests, identity = _fixture(generation=generation, device=device)
    owner = _Owner()
    transfer = ra9g.construct_ownership_transfer(
        [source], [owner], manifests, identity=identity, strict=True
    )
    transformed, _ = transfer.transform_once()
    return transfer, source, transformed, owner, identity


class RA9GOwnershipTransferTest(unittest.TestCase):
    def test_successful_bf16_to_fp32_transfer_and_metadata_only_snapshot(self):
        transfer, source, transformed, owner, _ = _transfer()
        self.assertEqual(transfer.state, ra9g.FP32_BOUND_UNPROVEN)
        self.assertEqual(transformed[0]["weight"].dtype, torch.float32)
        transfer.bind(transformed, assign=True, adopted=True)
        proof = transfer.prove_storage()
        self.assertEqual(proof["parameter_count"], 1)
        self.assertEqual(proof["source_bytes"], 8)
        self.assertEqual(proof["destination_bytes"], 16)
        self.assertEqual(proof["fp32_param_count"], 1)
        self.assertEqual(proof["fp32_bytes"], 16)
        self.assertEqual(proof["count_by_dtype"]["torch.float32"], 1)
        self.assertTrue(proof["source_alive_through_proof"])
        self.assertTrue(proof["no_second_model_sized_copy"])
        self.assertEqual(proof["duplicate_model_sized_fp32_bytes"], 0)
        self.assertIn("after_storage_proof_source_alive", proof["ownership_checkpoints"])
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.retire_owners()
        transfer.drop_source_refs()
        self.assertIsNone(transfer.source_mappings)
        self.assertIsNone(transfer.transformed_mappings)
        transfer.retire_owners()
        self.assertEqual(owner.released, 1)
        record = transfer.mark_ready()
        self.assertEqual(record["status"], ra9g.READY)
        self.assertIn("after_source_owner_retirement", record["ownership_checkpoints"])
        snapshot = transfer.snapshot()
        self.assertTrue(snapshot["metadata_only"])
        self.assertFalse(any(isinstance(value, torch.Tensor) for value in snapshot.values()))
        self.assertEqual(source["weight"].dtype, torch.bfloat16)

    def test_transform_is_exactly_once_and_generation_change_is_distinct(self):
        transfer, _, _, _, identity = _transfer()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.transform_once()
        _, _, changed_identity = _fixture(generation="manifest-2")
        self.assertNotEqual(identity.digest, changed_identity.digest)

    def test_identity_and_device_are_explicit(self):
        source, manifests, _ = _fixture()
        with self.assertRaises(ra9g.OwnershipTransferError):
            ra9g.construct_ownership_transfer(
                [source], [_Owner()], manifests,
                identity={"checkpoint_identity": "only-checkpoint"},
                target_device="cpu",
            )
        transfer, _, transformed, _, _ = _transfer(device="cuda:0")
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.bind(transformed, assign=True)
        self.assertEqual(transfer.state, ra9g.FAILED)

    def test_exact_keys_shapes_dtypes_and_assign_adoption_pointer(self):
        transfer, _, transformed, _, _ = _transfer()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.bind({"wrong": transformed[0]["weight"]}, assign=True)
        self.assertEqual(transfer.state, ra9g.FAILED)

        transfer, _, transformed, _, _ = _transfer()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.bind(transformed, assign=False)
        self.assertEqual(transfer.state, ra9g.FAILED)

        transfer, _, transformed, _, _ = _transfer()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.bind({"weight": transformed[0]["weight"].clone()}, assign=True)
        self.assertEqual(transfer.state, ra9g.FAILED)

    def test_bind_failure_keeps_source_authoritative_and_failed_transfer_cannot_advance(self):
        transfer, source, transformed, _, _ = _transfer()
        bad = {"weight": transformed[0]["weight"].reshape(2, 2)}
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.bind(bad, assign=True)
        self.assertIsNotNone(transfer.source_mappings)
        self.assertIs(transfer.source_mappings[0]["weight"], source["weight"])
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.mark_ready()
        transfer.release()
        self.assertIsNone(transfer.source_mappings)

    def test_storage_proof_failure_is_unready(self):
        transfer, _, transformed, _, _ = _transfer()
        transfer.acknowledge_bind(transformed, assign=True)
        transformed[0]["weight"] = transformed[0]["weight"].clone()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.prove_storage()
        self.assertEqual(transfer.state, ra9g.FAILED)

    def test_external_source_release_requires_receipt(self):
        transfer, _, transformed, _, identity = _transfer()
        transfer = ra9g.ClipFP32OwnershipTransfer(
            transfer.source_mappings, list(transfer.owner_handles),
            [{"dtype": "torch.bfloat16", "key_set": ["weight"], "key_shapes": {"weight": [4]}}],
            identity, external_source_release_callback=lambda: None,
        )
        transformed, _ = transfer.transform_once()
        transfer.bind(transformed, assign=True)
        transfer.prove_storage()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.drop_source_refs()
        self.assertEqual(transfer.state, ra9g.FAILED)

    def test_partial_cast_cleanup_and_explicit_fallback(self):
        source, manifests, _ = _fixture()
        source2 = {"bias": torch.ones(2, dtype=torch.bfloat16)}
        manifests2 = [{
            "dtype": "torch.bfloat16", "key_set": ["bias"], "key_shapes": {"bias": [2]},
        }]
        identity = ra9g.build_source_manifest_identity(
            manifests + manifests2,
            identity={
                "checkpoint_identity": "checkpoint-partial",
                "manifest_generation": "partial-1",
                "selected_tensor_scope": "clip.transformer",
                "model_patch_identity": "patch-1",
            },
            target_device="cpu",
        )
        original_to = torch.Tensor.to
        calls = {"count": 0}

        def fail_second(tensor, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("synthetic allocation failure")
            return original_to(tensor, *args, **kwargs)

        transfer = ra9g.ClipFP32OwnershipTransfer([source, source2], [_Owner()], manifests + manifests2, identity)
        with mock.patch.object(torch.Tensor, "to", fail_second):
            with self.assertRaises(RuntimeError):
                transfer.transform_once()
        self.assertEqual(transfer.state, ra9g.FAILED)
        self.assertIsNone(transfer.transformed_mappings)
        self.assertIsNotNone(transfer.source_mappings)

        fallback = ra9g.ClipFP32OwnershipTransfer([source], [_Owner()], manifests, identity)
        fallback.mark_fallback("normal BF16 path")
        self.assertEqual(fallback.state, ra9g.FAILED)
        self.assertTrue(fallback.status()["fallback"])
        fallback.release()

    def test_quiescence_rejects_active_state_and_no_dual_representation(self):
        transfer, _, _, _, _ = _transfer()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.assert_quiescent()
        transfer.release()
        self.assertEqual(transfer.status()["source_refs"], 0)
        self.assertEqual(transfer.status()["transformed_refs"], 0)

    def test_same_object_explicit_source_generation_invalidates_legacy_claim(self):
        class Clip:
            source_generation = "source-a"

        clip = Clip()
        ra9g.mark_cast_once_applied(clip)
        self.assertEqual(ra9g.cast_once_generation(clip), 1)
        clip.source_generation = "source-b"
        self.assertEqual(ra9g.cast_once_generation(clip), 0)
        ra9g.invalidate_cast_once(clip)

    def test_global_registries_are_scalar_metadata_only(self):
        for registry in (ra9g._CAST_ONCE_HYDRATION_GENERATION, ra9g._TRANSFER_REGISTRY):
            for key, value in registry.items():
                self.assertIsInstance(key, str)
                self.assertFalse(isinstance(value, torch.Tensor))
                self.assertFalse(any(isinstance(item, torch.Tensor) for item in (value.values() if isinstance(value, dict) else (value,))))

    def test_actual_bind_receipt_and_source_free_proof(self):
        transfer, _, transformed, _, identity = _transfer()

        class _Model:
            pass

        clip = type("Clip", (), {})()
        clip.cond_stage_model = _Model()
        destination = transformed[0]
        with mock.patch.object(cfh, "_leaf_loaders", return_value=[clip.cond_stage_model]), \
             mock.patch.object(cfh, "_leaf_param_map", return_value=destination):
            actual = ra9g.actual_bind_destination_map(clip, identity.expected_keys)
            receipt = ra9g.build_actual_bind_receipt(clip, actual, identity, assign=True)
            transfer.acknowledge_actual_bind(actual, receipt=receipt, assign=True)
            transfer.prove_storage()
            transfer.drop_source_refs()
            before_retirement = transfer.source_free_storage_proof(actual, expected_device="cpu")
            self.assertFalse(before_retirement["source_free"])
            self.assertEqual(before_retirement["source_refs"], 0)
            self.assertEqual(before_retirement["owner_refs"], 1)
            transfer.retire_owners()
            transfer.mark_ready()
            proof = transfer.source_free_storage_proof(actual, expected_device="cpu")
        self.assertTrue(receipt["actual_bind"])
        self.assertEqual(receipt["receipt_marker"], "ra9g.actual_bind.v1")
        self.assertTrue(proof["ok"])
        self.assertEqual(proof["source_refs"], 0)
        self.assertEqual(proof["owner_refs"], 0)

    def test_real_torch_assign_replaces_meta_parameter_and_proves_actual_pointer(self):
        transfer, _source, transformed, owner, identity = _transfer()

        class Loader(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(
                    torch.empty(4, device="meta", dtype=torch.float32)
                )

            def load_sd(self, state_dict):
                self.load_state_dict(state_dict, assign=True)

        class Clip:
            pass

        clip = Clip()
        clip.cond_stage_model = Loader()
        clip.cond_stage_model.load_sd(transformed[0])
        adopted = clip.cond_stage_model.weight
        assert adopted.data_ptr() == transformed[0]["weight"].data_ptr()
        assert adopted.untyped_storage().data_ptr() == transformed[0]["weight"].untyped_storage().data_ptr()

        actual = ra9g.actual_bind_destination_map(clip, identity.expected_keys)
        receipt = ra9g.build_actual_bind_receipt(clip, actual, identity, assign=True)
        transfer.acknowledge_actual_bind(actual, receipt=receipt, assign=True, clip=clip)
        transfer.prove_storage(expected_device="cpu")
        self.assertEqual(actual["weight"].data_ptr(), transformed[0]["weight"].data_ptr())
        transfer.drop_source_refs(receipt={"source_refs_dropped": True})
        transfer.retire_owners()
        self.assertTrue(transfer.source_free_storage_proof(actual, expected_device="cpu")["ok"])
        self.assertEqual(owner.released, 1)

    def test_actual_bind_rejects_fake_transformed_mapping_without_receipt(self):
        transfer, _, transformed, _, _ = _transfer()
        with self.assertRaises(ra9g.BindReceiptError):
            transfer.acknowledge_actual_bind(
                transformed, receipt={"actual_bind": True}, assign=True
            )

    def test_failed_release_preserves_handle_for_retry(self):
        source, manifests, identity = _fixture()
        owner = _FlakyOwner()
        transfer = ra9g.ClipFP32OwnershipTransfer([source], [owner], manifests, identity)
        transformed, _ = transfer.transform_once()
        transfer.bind(transformed, assign=True)
        transfer.prove_storage()
        transfer.drop_source_refs()
        with self.assertRaises(ra9g.OwnershipTransferError):
            transfer.retire_owners()
        self.assertIsNotNone(transfer.owner_handles)
        transfer.retire_owners()
        self.assertIsNone(transfer.owner_handles)

    def test_swapped_file_mappings_fail_closed_before_cast(self):
        source_one = {"weight": torch.ones(4, dtype=torch.bfloat16)}
        source_two = {"bias": torch.ones(2, dtype=torch.bfloat16)}
        manifests = [
            {
                "file_index": 0,
                "dtype": "torch.bfloat16",
                "key_set": ["weight"],
                "key_shapes": {"weight": [4]},
            },
            {
                "file_index": 1,
                "dtype": "torch.bfloat16",
                "key_set": ["bias"],
                "key_shapes": {"bias": [2]},
            },
        ]
        identity = ra9g.build_source_manifest_identity(
            manifests,
            identity={
                "checkpoint_identity": "checkpoint-routed",
                "manifest_generation": "routed-1",
                "selected_tensor_scope": "clip.transformer",
                "model_patch_identity": "patch-1",
            },
            target_device="cpu",
        )
        transfer = ra9g.ClipFP32OwnershipTransfer(
            [source_two, source_one], [_Owner(), _Owner()], manifests, identity
        )
        with self.assertRaises(ra9g.OwnershipTransferError) as caught:
            transfer.transform_once()
        self.assertIn("source file 0 key set mismatch", str(caught.exception))
        self.assertEqual(transfer.state, ra9g.FAILED)

    def test_cleanup_does_not_retry_non_destructive_api_without_contract(self):
        class _NoKeywordRelease:
            def __init__(self):
                self.calls = 0

            def release_storage(self):
                self.calls += 1

        owner = _NoKeywordRelease()
        cleanup = wiring._close_source_owners([owner])
        # The keyword call is rejected before the method body; importantly,
        # the unsafe no-argument retry never invokes it.
        self.assertEqual(owner.calls, 0)
        self.assertFalse(cleanup["ok"])
        self.assertTrue(cleanup["errors"])

    def test_requested_cast_fallback_is_recorded_as_bf16(self):
        wiring._RECORD.pop("", None)
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "1"}):
            result = wiring._record_mode(
                object(), cfh.MODE_NATIVE, {"ok": True, "reason": "identity unavailable"}
            )
            summary = wiring.clip_fh_request_summary("")
        self.assertTrue(result["cast_once_requested"])
        self.assertFalse(result["cast_once_applied"])
        self.assertEqual(result["cast_once_fallback"], "ordinary_bf16")
        self.assertGreaterEqual(result["fallback_count"], 1)
        self.assertTrue(summary["cast_once_requested"])
        self.assertFalse(summary["cast_once_applied"])
        self.assertGreaterEqual(summary["fallback_count"], 1)

    def test_wiring_adapter_uses_actual_bind_contract(self):
        transfer, _, transformed, _, identity = _transfer()

        class _Model:
            pass

        clip = type("Clip", (), {})()
        clip.cond_stage_model = _Model()
        with mock.patch.object(cfh, "hydrate_clip_bind", return_value=(True, "actual-bind")), \
             mock.patch.object(cfh, "_leaf_loaders", return_value=[clip.cond_stage_model]), \
             mock.patch.object(cfh, "_leaf_param_map", return_value=transformed[0]):
            record, evidence = wiring._bind_with_ownership_transfer(
                clip, transfer, transformed, require_no_meta=False
            )
        self.assertEqual(evidence, "actual-bind")
        self.assertTrue(record["storage_proven"])
        self.assertEqual(record["bind_receipt"]["receipt_marker"], "ra9g.actual_bind.v1")


if __name__ == "__main__":
    unittest.main()
