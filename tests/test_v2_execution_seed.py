"""Focused tests for schema-v2 SnapshotExecutionSeed and the pure graph
analysis module ``comfymodal_runtime.execution_seed``.

Covers: v1 from_dict readability, v2 roundtrip + stable_hash sensitivity to
sampler/structural fields, forbidden-state exclusion, backward reachability and
execution order, conservative static/dynamic classification (unknown => dynamic),
insertion-order independence, malformed/cyclic fallback, and loader/sampler
discovery.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from comfymodal_runtime.contracts import SnapshotExecutionSeed
from comfymodal_runtime.execution_seed import build_snapshot_execution_seed


# ── Fixtures ───────────────────────────────────────────────────────────────


def _make_workflow() -> dict[str, dict[str, Any]]:
    """Canonical ComfyUI-shaped workflow with an unreachable orphan node."""
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd3.5_large.safetensors"}},
        "6": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "sd3"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["6", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad", "clip": ["6", 0]}},
        "9": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 4.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["5", 0],
                "negative": ["8", 0],
                "latent_image": ["9", 0],
            },
        },
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["7", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["13", 0]}},
        "99": {"class_type": "CLIPTextEncode", "inputs": {"text": "orphan", "clip": ["6", 0]}},
    }


def _make_unknown_workflow() -> dict[str, dict[str, Any]]:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
        "20": {"class_type": "MysteryNode", "inputs": {"foo": "bar", "cfg": 2.0, "model": ["1", 0]}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["20", 0]}},
    }


_V1_PAYLOAD: dict[str, Any] = {
    "schema_version": 1,
    "workflow_hash": "wf-v1",
    "output_node_ids": ["4", "10"],
    "loader_node_ids": ["4", "6", "7"],
    "loader_cache_signatures": [{"node_id": "unet", "signature": "sig-unet"}],
    "sampler_node_ids": ["10"],
    "sampler_static_inputs": [{"node_id": "10", "sampler_name": "euler"}],
    "custom_node_generation": "gen-1",
    "deployment_combined_hash": "dep-1",
}

_FORBIDDEN_KEYS = (
    "outputs",
    "latents",
    "conditioning",
    "request_id",
    "client_id",
    "cancellation",
    "progress",
    "random_state",
    "cuda",
)


# ── Schema v1 readability ──────────────────────────────────────────────────


class TestSchemaV1Readability(unittest.TestCase):
    def test_default_schema_version_is_v2(self):
        self.assertEqual(SnapshotExecutionSeed().schema_version, 2)
        self.assertEqual(SnapshotExecutionSeed(schema_version=1).schema_version, 1)

    def test_v1_payload_roundtrip_preserves_v1_fields(self):
        seed = SnapshotExecutionSeed.from_dict(_V1_PAYLOAD)
        self.assertEqual(seed.schema_version, 1)
        self.assertEqual(seed.workflow_hash, "wf-v1")
        # source_workflow_hash derived from workflow_hash for v1 payloads.
        self.assertEqual(seed.source_workflow_hash, "wf-v1")
        self.assertEqual(seed.output_node_ids, ("4", "10"))
        self.assertEqual(seed.loader_node_ids, ("4", "6", "7"))
        self.assertEqual(seed.loader_cache_signatures[0]["node_id"], "unet")
        self.assertEqual(seed.sampler_node_ids, ("10",))
        self.assertEqual(seed.sampler_static_inputs[0]["sampler_name"], "euler")
        self.assertEqual(seed.custom_node_generation, "gen-1")
        self.assertEqual(seed.deployment_combined_hash, "dep-1")
        # Schema-v2-only structural fields fall back to empty defaults.
        self.assertEqual(seed.reachable_node_ids, ())
        self.assertEqual(seed.execution_order_hint, ())
        self.assertEqual(seed.static_node_signatures, ())
        self.assertEqual(seed.dynamic_input_map, ())

        out = seed.to_dict()
        self.assertEqual(out["schema_version"], 1)
        self.assertEqual(out["workflow_hash"], "wf-v1")
        self.assertEqual(out["output_node_ids"], ["4", "10"])
        self.assertEqual(out["sampler_node_ids"], ["10"])

    def test_v1_payload_with_missing_optional_keys(self):
        seed = SnapshotExecutionSeed.from_dict({"schema_version": 1, "workflow_hash": "w"})
        self.assertEqual(seed.schema_version, 1)
        self.assertEqual(seed.loader_cache_signatures, ())
        self.assertEqual(seed.static_node_signatures, ())
        json.dumps(seed.to_dict())  # still JSON-safe


# ── V2 roundtrip and hash sensitivity ──────────────────────────────────────


class TestV2RoundtripAndHash(unittest.TestCase):
    def test_v2_roundtrip_is_identity(self):
        seed = build_snapshot_execution_seed(
            _make_workflow(),
            output_node_ids=["12", "13"],
            custom_node_generation="gen",
            deployment_combined_hash="dep",
        )
        self.assertEqual(seed.schema_version, 2)
        restored = SnapshotExecutionSeed.from_dict(seed.to_dict())
        self.assertEqual(restored.to_dict(), seed.to_dict())
        self.assertEqual(restored.stable_hash, seed.stable_hash)
        # Every to_dict payload is JSON-serializable.
        json.dumps(seed.to_dict())

    def test_sampler_fields_change_stable_hash(self):
        base = SnapshotExecutionSeed(workflow_hash="w", sampler_node_ids=("10",))
        with_static = SnapshotExecutionSeed(
            workflow_hash="w",
            sampler_node_ids=("10",),
            sampler_static_inputs=({"node_id": "10", "sampler_name": "euler"},),
        )
        with_different_sampler_ids = SnapshotExecutionSeed(workflow_hash="w", sampler_node_ids=("10", "11"))
        self.assertNotEqual(base.stable_hash, with_static.stable_hash)
        self.assertNotEqual(base.stable_hash, with_different_sampler_ids.stable_hash)

    def test_structural_fields_change_stable_hash(self):
        base = SnapshotExecutionSeed(workflow_hash="w", output_node_ids=("12",))
        with_reachable = SnapshotExecutionSeed(workflow_hash="w", output_node_ids=("12",), reachable_node_ids=("12", "10"))
        with_signatures = SnapshotExecutionSeed(
            workflow_hash="w",
            output_node_ids=("12",),
            static_node_signatures=({"node_id": "10", "node_class": "KSampler", "static_inputs": {}, "hash": "h"},),
        )
        with_dynamic_map = SnapshotExecutionSeed(
            workflow_hash="w",
            output_node_ids=("12",),
            dynamic_input_map=({"node_id": "10", "input": "seed", "reason": "seed"},),
        )
        self.assertNotEqual(base.stable_hash, with_reachable.stable_hash)
        self.assertNotEqual(base.stable_hash, with_signatures.stable_hash)
        self.assertNotEqual(base.stable_hash, with_dynamic_map.stable_hash)

    def test_loader_cache_signatures_change_stable_hash(self):
        base = SnapshotExecutionSeed(workflow_hash="w", loader_node_ids=("4",))
        with_sig = SnapshotExecutionSeed(
            workflow_hash="w",
            loader_node_ids=("4",),
            loader_cache_signatures=({"node_id": "4", "signature": "s"},),
        )
        self.assertNotEqual(base.stable_hash, with_sig.stable_hash)


# ── Forbidden-state exclusion ──────────────────────────────────────────────


class TestForbiddenStateExclusion(unittest.TestCase):
    def test_from_dict_ignores_forbidden_runtime_state(self):
        seed = build_snapshot_execution_seed(
            _make_workflow(),
            output_node_ids=["12", "13"],
            workflow_hash="wh",
        )
        payload = dict(seed.to_dict())
        payload["outputs"] = {"12": ["image-bytes"]}
        payload["latents"] = ["latent-tensor"]
        payload["conditioning"] = {"cond": "tensor"}
        payload["request_id"] = "req-1"
        payload["client_id"] = "client-1"
        payload["cancellation"] = {"cancel": True}
        payload["progress"] = {"step": 3}
        payload["random_state"] = 12345
        payload["cuda"] = {"handle": "cuda:0"}

        restored = SnapshotExecutionSeed.from_dict(payload)
        out = restored.to_dict()
        for key in _FORBIDDEN_KEYS:
            self.assertNotIn(key, out, f"forbidden key leaked: {key}")
        # Structural data still intact.
        self.assertEqual(out["workflow_hash"], "wh")
        self.assertEqual(out["output_node_ids"], list(seed.output_node_ids))

    def test_to_dict_never_emits_forbidden_keys(self):
        seed = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12", "13"])
        for key in _FORBIDDEN_KEYS:
            self.assertNotIn(key, seed.to_dict())


# ── Reachable traversal and execution order ────────────────────────────────


class TestReachabilityAndOrder(unittest.TestCase):
    def test_reachable_excludes_orphans(self):
        seed = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12"])
        self.assertNotIn("99", seed.reachable_node_ids, "orphan must not be reachable")
        self.assertNotIn("99", seed.static_node_signatures, "orphan must have no signature")
        self.assertNotIn("99", seed.dynamic_input_map, "orphan must have no dynamic entries")

    def test_no_outputs_uses_canonical_node_set(self):
        seed = build_snapshot_execution_seed(_make_workflow())
        self.assertEqual(set(seed.reachable_node_ids), set(_make_workflow()))
        self.assertEqual(len(seed.execution_order_hint), len(_make_workflow()))

    def test_execution_order_is_topological(self):
        seed = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12", "13"])
        order = list(seed.execution_order_hint)
        self.assertEqual(len(order), len(seed.reachable_node_ids))
        position = {node_id: index for index, node_id in enumerate(order)}
        # Sources must appear before their dependents.
        self.assertLess(position["6"], position["5"])
        self.assertLess(position["6"], position["8"])
        self.assertLess(position["4"], position["10"])
        self.assertLess(position["5"], position["10"])
        self.assertLess(position["9"], position["10"])
        self.assertLess(position["10"], position["13"])
        self.assertLess(position["13"], position["12"])
        # KSampler's own static inputs sampled deterministically.
        self.assertIn("10", order)

    def test_chain_order_is_preserved(self):
        workflow = {
            "1": {"class_type": "A", "inputs": {}},
            "2": {"class_type": "B", "inputs": {"a": ["1", 0]}},
            "3": {"class_type": "C", "inputs": {"b": ["2", 0]}},
        }
        seed = build_snapshot_execution_seed(workflow, output_node_ids=["3"])
        self.assertEqual(seed.execution_order_hint, ("1", "2", "3"))


# ── Static vs dynamic classification ───────────────────────────────────────


class TestStaticDynamicClassification(unittest.TestCase):
    def test_loader_and_sampler_static_inputs(self):
        seed = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12", "13"])
        by_id = {entry["node_id"]: entry for entry in seed.static_node_signatures}

        loader = by_id["4"]
        self.assertEqual(loader["node_class"], "CheckpointLoaderSimple")
        self.assertEqual(loader["static_inputs"]["ckpt_name"], "sd3.5_large.safetensors")
        self.assertTrue(loader["hash"])

        clip_loader = by_id["6"]
        self.assertEqual(clip_loader["static_inputs"]["clip_name"], "t5xxl_fp16.safetensors")
        self.assertEqual(clip_loader["static_inputs"]["type"], "sd3")

        sampler = by_id["10"]
        self.assertEqual(sampler["node_class"], "KSampler")
        self.assertEqual(sampler["static_inputs"]["sampler_name"], "euler")
        self.assertEqual(sampler["static_inputs"]["scheduler"], "normal")
        # Link edges are static (frozen tuple form inside the frozen mapping).
        self.assertEqual(sampler["static_inputs"]["model"], (("4", 0),))
        self.assertEqual(sampler["static_inputs"]["positive"], (("5", 0),))
        self.assertEqual(sampler["static_inputs"]["negative"], (("8", 0),))
        self.assertEqual(sampler["static_inputs"]["latent_image"], (("9", 0),))

    def test_known_dynamic_inputs_are_dynamic(self):
        seed = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12", "13"])
        dynamic = {(entry["node_id"], entry["input"]): entry["reason"] for entry in seed.dynamic_input_map}

        self.assertEqual(dynamic[("5", "text")], "prompt_text")
        self.assertEqual(dynamic[("8", "text")], "prompt_text")
        self.assertEqual(dynamic[("10", "seed")], "seed")
        self.assertEqual(dynamic[("10", "denoise")], "denoise_user_controlled")
        self.assertEqual(dynamic[("9", "width")], "spatial_dimension")
        self.assertEqual(dynamic[("9", "height")], "spatial_dimension")

    def test_unknown_inputs_are_dynamic_never_static(self):
        seed = build_snapshot_execution_seed(_make_unknown_workflow(), output_node_ids=["3"])
        by_id = {entry["node_id"]: entry for entry in seed.static_node_signatures}
        mystery = by_id["20"]
        # Only the link edge is static; foo/cfg are unknown -> dynamic.
        self.assertEqual(mystery["static_inputs"], {"model": (("1", 0),)})
        dynamic = {(entry["node_id"], entry["input"]): entry["reason"] for entry in seed.dynamic_input_map}
        self.assertEqual(dynamic[("20", "foo")], "unknown_dynamic")
        self.assertEqual(dynamic[("20", "cfg")], "unknown_dynamic")
        # Unknown input is never guessed static.
        self.assertNotIn("foo", mystery["static_inputs"])
        self.assertNotIn("cfg", mystery["static_inputs"])

    def test_request_metadata_keys_are_dynamic(self):
        workflow = {
            "1": {"class_type": "CustomInput", "inputs": {"request_metadata": {"user": "x"}, "request_id": "rid"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        seed = build_snapshot_execution_seed(workflow, output_node_ids=["2"])
        dynamic = {(entry["node_id"], entry["input"]): entry["reason"] for entry in seed.dynamic_input_map}
        self.assertEqual(dynamic[("1", "request_metadata")], "request_metadata")
        self.assertEqual(dynamic[("1", "request_id")], "request_metadata")


# ── Determinism under reordering ───────────────────────────────────────────


class TestInsertionOrderIndependence(unittest.TestCase):
    def test_reordered_workflow_produces_identical_seed(self):
        wf_a = _make_workflow()
        wf_b = {
            node_id: {
                "class_type": node["class_type"],
                "inputs": dict(reversed(list(node["inputs"].items()))),
            }
            for node_id, node in reversed(list(wf_a.items()))
        }
        seed_a = build_snapshot_execution_seed(wf_a, output_node_ids=["13", "12"], workflow_hash="wh")
        seed_b = build_snapshot_execution_seed(wf_b, output_node_ids=["12", "13"], workflow_hash="wh")
        self.assertEqual(seed_a.to_dict(), seed_b.to_dict())
        self.assertEqual(seed_a.stable_hash, seed_b.stable_hash)

    def test_reordered_output_ids_produce_identical_seed(self):
        seed_a = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12", "13"])
        seed_b = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["13", "12"])
        self.assertEqual(seed_a.reachable_node_ids, seed_b.reachable_node_ids)
        self.assertEqual(seed_a.execution_order_hint, seed_b.execution_order_hint)

    def test_workflow_hash_computed_deterministically_when_omitted(self):
        wf_a = _make_workflow()
        wf_b = {
            node_id: {
                "class_type": node["class_type"],
                "inputs": dict(reversed(list(node["inputs"].items()))),
            }
            for node_id, node in reversed(list(wf_a.items()))
        }
        self.assertEqual(
            build_snapshot_execution_seed(wf_a, output_node_ids=["12"]).workflow_hash,
            build_snapshot_execution_seed(wf_b, output_node_ids=["12"]).workflow_hash,
        )


# ── Malformed / cyclic fallback ────────────────────────────────────────────


class TestMalformedAndCyclicFallback(unittest.TestCase):
    def test_cycle_falls_back_to_stable_order(self):
        workflow = {
            "1": {"class_type": "NodeA", "inputs": {"x": ["2", 0]}},
            "2": {"class_type": "NodeB", "inputs": {"y": ["1", 0]}},
        }
        seed = build_snapshot_execution_seed(workflow, output_node_ids=["1"])
        self.assertEqual(set(seed.reachable_node_ids), {"1", "2"})
        self.assertEqual(sorted(seed.execution_order_hint), ["1", "2"])
        # Deterministic across reordered input.
        seed2 = build_snapshot_execution_seed(
            {nid: workflow[nid] for nid in reversed(list(workflow))},
            output_node_ids=["1"],
        )
        self.assertEqual(seed.execution_order_hint, seed2.execution_order_hint)

    def test_self_loop_falls_back(self):
        workflow = {"5": {"class_type": "NodeC", "inputs": {"z": ["5", 0]}}}
        seed = build_snapshot_execution_seed(workflow, output_node_ids=["5"])
        self.assertEqual(seed.execution_order_hint, ("5",))

    def test_malformed_nodes_are_dropped_without_error(self):
        workflow = {
            "1": {"class_type": "NodeA", "inputs": {}},
            "2": "not-a-dict",
            "3": {"inputs": {}},
            "4": None,
            "": {"class_type": "EmptyId", "inputs": {}},
        }
        seed = build_snapshot_execution_seed(workflow, output_node_ids=["1"])
        self.assertEqual(set(seed.reachable_node_ids), {"1"})
        self.assertEqual(seed.execution_order_hint, ("1",))

    def test_link_to_missing_node_is_ignored(self):
        workflow = {
            "1": {"class_type": "NodeA", "inputs": {"missing": ["ghost", 0]}},
        }
        seed = build_snapshot_execution_seed(workflow, output_node_ids=["1"])
        self.assertEqual(seed.reachable_node_ids, ("1",))
        self.assertEqual(seed.execution_order_hint, ("1",))


# ── Loader/sampler discovery and metadata normalization ────────────────────


class TestDiscoveryAndMetadata(unittest.TestCase):
    def test_loader_and_sampler_discovery(self):
        seed = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12", "13"])
        self.assertEqual(seed.loader_node_ids, ("4", "6", "7"))
        self.assertEqual(seed.sampler_node_ids, ("10",))

    def test_preserved_metadata_is_json_safe_normalized(self):
        class _FakeTensor:
            pass

        seed = build_snapshot_execution_seed(
            _make_workflow(),
            output_node_ids=["12", "13"],
            loader_cache_signatures=[
                {"node_id": "unet", "signature": "sig-unet", "tensor": _FakeTensor()},
                {"node_id": "clip", "signature": "sig-clip"},
            ],
            sampler_static_inputs=[{"node_id": "10", "sampler_name": "euler", "obj": _FakeTensor()}],
        )
        self.assertEqual(len(seed.loader_cache_signatures), 2)
        self.assertEqual(seed.loader_cache_signatures[0]["node_id"], "unet")
        self.assertEqual(seed.loader_cache_signatures[0]["signature"], "sig-unet")
        self.assertNotIn("tensor", seed.loader_cache_signatures[0], "tensor leaf must be stripped")
        self.assertEqual(seed.loader_cache_signatures[1]["signature"], "sig-clip")
        self.assertEqual(len(seed.sampler_static_inputs), 1)
        self.assertEqual(seed.sampler_static_inputs[0]["sampler_name"], "euler")
        self.assertNotIn("obj", seed.sampler_static_inputs[0])
        # to_dict remains fully JSON-serializable.
        json.dumps(seed.to_dict())

    def test_empty_entries_dropped(self):
        seed = build_snapshot_execution_seed(
            _make_workflow(),
            output_node_ids=["12"],
            loader_cache_signatures=[{"only_tensor": object()}],
        )
        self.assertEqual(seed.loader_cache_signatures, ())

    def test_all_signatures_carry_stable_hashes(self):
        seed = build_snapshot_execution_seed(_make_workflow(), output_node_ids=["12", "13"])
        self.assertTrue(all(entry["hash"] for entry in seed.static_node_signatures))
        self.assertTrue(all(entry["node_class"] for entry in seed.static_node_signatures))


if __name__ == "__main__":
    unittest.main()
