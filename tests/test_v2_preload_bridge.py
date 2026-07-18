"""Focused tests for the live v2 restore/preload loader bridge."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.model_preload import ModelPreloadCoordinator, V2LoaderBridge
from comfymodal_runtime.restore_plan import build_restore_model_spec
from comfymodal_runtime.trace import RuntimeTrace


class _FakeClip:
    pass


def _fake_nodes(calls: list[tuple]) -> SimpleNamespace:
    class UNETLoader:
        def load_unet(self, unet_name, weight_dtype):
            calls.append(("unet", unet_name, weight_dtype))
            return (f"prepared-unet:{unet_name}:{weight_dtype}",)

    class CLIPLoader:
        def load_clip(self, clip_name, type="stable_diffusion", device="default"):
            calls.append(("clip", clip_name, type, device))
            return (_FakeClip(),)

    class DualCLIPLoader:
        def load_clip(self, clip_name1, clip_name2, type, device="default"):
            calls.append(("dual_clip", clip_name1, clip_name2, type, device))
            return (_FakeClip(),)

    class CLIPTextEncode:
        def encode(self, clip, text):
            calls.append(("prefill", id(clip), text))
            return (f"conditioning:{text}",)

    return SimpleNamespace(
        NODE_CLASS_MAPPINGS={
            "UNETLoader": UNETLoader,
            "CLIPLoader": CLIPLoader,
            "DualCLIPLoader": DualCLIPLoader,
            "CLIPTextEncode": CLIPTextEncode,
        }
    )


class V2PreloadBridgeTests(unittest.TestCase):
    def test_worker_pool_is_created_after_snapshot_boundary(self):
        coordinator = ModelPreloadCoordinator(unet_loader=lambda _key: "unet")
        try:
            self.assertIsNone(coordinator._pool)
            preparation = coordinator.prepare(
                ModelRestoreKey(unet_identity="u"),
                PrefillKey(model_key=ModelRestoreKey(unet_identity="u")),
                prepare_clip=False,
            )
            self.assertIsNotNone(coordinator._pool)
            self.assertEqual(coordinator.wait_unet(preparation), "unet")
        finally:
            coordinator.close()

    def _plan(self, workflow: dict, *, prefill: bool = True) -> RestorePlan:
        model_key = ModelRestoreKey(
            unet_identity="unet.safetensors",
            clip_identity="clip.safetensors",
            clip_type="flux",
        )
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="bundle-hash" if prefill else "",
            encode_options={
                "eligible": prefill,
                "encodes": [{"node_id": "3", "text": "a cat"}],
            },
        )
        return RestorePlan(
            generation=7,
            model_key=model_key,
            prefill_key=prefill_key,
            model_spec=build_restore_model_spec(workflow, {"unet": ["unet.safetensors"]}),
            prefill_spec=dict(prefill_key.encode_options),
        )

    def test_restore_preload_is_consumed_by_real_loader_methods(self):
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="req-1", process="remote")
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"},
            },
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
        }

        bridge.prepare(self._plan(workflow), trace=trace)
        with bridge.request_scope():
            unet = nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "unet.safetensors", "default"
            )
            clip = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "clip.safetensors", "flux"
            )
            conditioning = nodes.NODE_CLASS_MAPPINGS["CLIPTextEncode"]().encode(
                clip[0], "a cat"
            )

        self.assertEqual(unet, ("prepared-unet:unet.safetensors:default",))
        self.assertIsInstance(clip[0], _FakeClip)
        self.assertEqual(conditioning, ("conditioning:a cat",))
        self.assertEqual([call[0] for call in calls].count("unet"), 1)
        self.assertEqual([call[0] for call in calls].count("clip"), 1)
        self.assertEqual([call[0] for call in calls].count("prefill"), 1)
        event_names = [event.name for event in trace.events]
        for expected in (
            "unet_prepare_start",
            "clip_prepare_start",
            "graph_unet_demand",
            "graph_unet_consumed",
            "graph_clip_demand",
            "graph_clip_consumed",
            "graph_prefill_consumed",
        ):
            self.assertIn(expected, event_names)
        diagnostics = bridge.diagnostics()
        self.assertIn("unet_actual_graph_wait_ms", diagnostics)
        self.assertIn("clip_actual_graph_wait_ms", diagnostics)

    def test_loader_mismatch_falls_through_to_original(self):
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False))
        with bridge.request_scope():
            result = nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "different.safetensors", "default"
            )
        self.assertEqual(result, ("prepared-unet:different.safetensors:default",))
        self.assertIn(("unet", "unet.safetensors", "default"), calls)
        self.assertIn(("unet", "different.safetensors", "default"), calls)


if __name__ == "__main__":
    unittest.main()
