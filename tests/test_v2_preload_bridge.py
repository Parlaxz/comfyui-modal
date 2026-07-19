"""Focused tests for the live v2 restore/preload loader bridge.

Phase 4 terminal outcomes, worker events and identity diagnostics.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan, stable_hash
from comfymodal_runtime.model_preload import ModelPreloadCoordinator, V2LoaderBridge, _LOADER_MISS
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
            # legacy events (preserved)
            "unet_prepare_start",
            "clip_prepare_start",
            "graph_unet_demand",
            "graph_unet_consumed",
            "graph_clip_demand",
            "graph_clip_consumed",
            "graph_prefill_consumed",
            # Phase 4 worker events
            "preload_submitted",
            "preload_worker_started",
            "preload_worker_finished",
            # Phase 4 terminal outcome — prepared
            "graph_model_demand",
            "graph_wait_started",
            "graph_wait_finished",
            "prepared_result_consumed",
        ):
            self.assertIn(expected, event_names)

        # Verify terminal outcome metadata for each lane
        unet_terminal = [e for e in trace.events if e.name == "prepared_result_consumed" and e.metadata.get("lane") == "UNET"]
        self.assertEqual(len(unet_terminal), 1)
        self.assertEqual(unet_terminal[0].metadata.get("terminal_outcome"), "prepared")
        self.assertIn("hashed_planned_identity", unet_terminal[0].metadata)
        self.assertIn("graph_wait_duration_ms", unet_terminal[0].metadata)

        clip_terminal = [e for e in trace.events if e.name == "prepared_result_consumed" and e.metadata.get("lane") == "CLIP"]
        self.assertEqual(len(clip_terminal), 1)
        self.assertEqual(clip_terminal[0].metadata.get("terminal_outcome"), "prepared")

        prefill_terminal = [e for e in trace.events if e.name == "prepared_result_consumed" and e.metadata.get("lane") == "prefill"]
        self.assertEqual(len(prefill_terminal), 1)
        self.assertEqual(prefill_terminal[0].metadata.get("terminal_outcome"), "prepared")
        self.assertIn("hashed_requested_identity", prefill_terminal[0].metadata)
        self.assertEqual(
            prefill_terminal[0].metadata["hashed_requested_identity"],
            stable_hash("a cat"),
        )
        # Timing fields: cache-miss path (first call) has real diagnostics
        cbd = prefill_terminal[0].metadata.get("completed_before_demand_ms")
        gwd = prefill_terminal[0].metadata.get("graph_wait_duration_ms")
        self.assertIsNotNone(cbd, "completed_before_demand_ms must be set (cache miss)")
        self.assertIsNotNone(gwd, "graph_wait_duration_ms must be set (cache miss)")
        self.assertIsInstance(cbd, (int, float))
        self.assertIsInstance(gwd, (int, float))

        # No fallback events on the success path
        for bad in ("identity_mismatch", "request_spec_missing", "future_failed", "future_unavailable", "original_loader_fallback"):
            self.assertNotIn(bad, event_names, f"fallback event '{bad}' must not appear on success path")

        # Worker events carry lane metadata
        worker_events = [e for e in trace.events if e.name in ("preload_worker_started", "preload_worker_finished")]
        for event in worker_events:
            self.assertIn(event.metadata.get("lane"), ("unet", "clip", "prefill"))

        diagnostics = bridge.diagnostics()
        self.assertIn("unet_actual_graph_wait_ms", diagnostics)
        self.assertIn("clip_actual_graph_wait_ms", diagnostics)

    def test_loader_mismatch_falls_through_to_original(self):
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="req-2", process="remote")
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)
        with bridge.request_scope():
            result = nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "different.safetensors", "default"
            )
        self.assertEqual(result, ("prepared-unet:different.safetensors:default",))
        self.assertIn(("unet", "unet.safetensors", "default"), calls)
        self.assertIn(("unet", "different.safetensors", "default"), calls)

        # Phase 4: identity mismatch events
        event_names = [event.name for event in trace.events]
        self.assertIn("identity_mismatch", event_names)
        self.assertIn("original_loader_fallback", event_names)
        mismatch_events = [e for e in trace.events if e.name == "identity_mismatch"]
        for event in mismatch_events:
            self.assertEqual(event.metadata.get("terminal_outcome"), "fallback_identity_mismatch")
            self.assertEqual(event.metadata.get("lane"), "UNET")
            self.assertIn("hashed_planned_identity", event.metadata)
            self.assertIn("hashed_requested_identity", event.metadata)
            self.assertNotEqual(
                event.metadata["hashed_planned_identity"],
                event.metadata["hashed_requested_identity"],
                "mismatched identities must have different hashes",
            )


    def test_missing_spec_emits_request_spec_missing(self):
        """When _model_key is None, consume emits request_spec_missing + original_loader_fallback."""
        bridge = V2LoaderBridge()
        bridge.install(_fake_nodes([]))
        # Clearly not prepare — _model_key and _preparation are None from init
        trace = RuntimeTrace(request_id="req-3", process="remote")
        bridge._trace = trace
        result = bridge._consume_unet((), {"unet_name": "any.safetensors"})
        self.assertIs(result, _LOADER_MISS)
        event_names = [e.name for e in trace.events]
        self.assertIn("request_spec_missing", event_names)
        self.assertIn("original_loader_fallback", event_names)
        terminal = [e for e in trace.events if e.name == "request_spec_missing"]
        self.assertEqual(len(terminal), 1)
        self.assertEqual(terminal[0].metadata.get("terminal_outcome"), "fallback_missing_spec")
        self.assertEqual(terminal[0].metadata.get("lane"), "UNET")

    def test_clip_identity_mismatch_emits_terminal_event(self):
        """CLIP identity mismatch emits identity_mismatch with fallback_identity_mismatch."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="req-4", process="remote")
        workflow = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)
        with bridge.request_scope():
            result = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "different-clip.safetensors", "flux"
            )
        # Falls through to original loader
        self.assertIsInstance(result[0], _FakeClip)
        event_names = [e.name for e in trace.events]
        self.assertIn("identity_mismatch", event_names)
        clip_mismatch = [e for e in trace.events if e.name == "identity_mismatch" and e.metadata.get("lane") == "CLIP"]
        self.assertEqual(len(clip_mismatch), 1)
        self.assertEqual(clip_mismatch[0].metadata.get("terminal_outcome"), "fallback_identity_mismatch")

    def test_future_failure_emits_future_failed(self):
        """When the loaded worker crashes, _consume_unet emits future_failed.

        Injects a broken unet_loader into the bridge's coordinator to
        exercise the graph-consumer catch path where future_failed is emitted.
        """
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        # Replace the real _load_unet with a broken one that crashes
        bridge._load_unet = lambda key: (_ for _ in ()).throw(RuntimeError("simulated worker crash"))
        bridge.coordinator.unet_loader = bridge._load_unet

        trace = RuntimeTrace(request_id="req-5", process="remote")
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "broken.safetensors", "weight_dtype": "default"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)

        # Allow the worker to fail (it was submitted asynchronously)
        import time
        time.sleep(0.3)

        # Consume via the bridge with the *planned* identity so we pass
        # identity check and reach wait_unet, where the failed future
        # triggers future_failed.
        result = bridge._consume_unet((), {"unet_name": "unet.safetensors"})
        self.assertIs(result, _LOADER_MISS)

        event_names = [e.name for e in trace.events]
        self.assertIn("preload_worker_failed", event_names,
                      "worker failure must emit preload_worker_failed")
        self.assertIn("future_failed", event_names,
                      "graph wait failure must emit future_failed")
        failed_events = [e for e in trace.events if e.name == "future_failed"]
        self.assertEqual(len(failed_events), 1)
        self.assertEqual(failed_events[0].metadata.get("terminal_outcome"), "fallback_future_error")
        self.assertEqual(failed_events[0].metadata.get("error_category"), "RuntimeError")

    def test_every_graph_demand_has_exactly_one_terminal_outcome(self):
        """Every graph loader demand must end in exactly one terminal outcome.

        For the success path (three lanes: UNET, CLIP, prefill), verify
        exactly three *prepared_result_consumed* events and zero fallback
        terminal events.
        """
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="req-6", process="remote")
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
        }
        bridge.prepare(self._plan(workflow), trace=trace)
        with bridge.request_scope():
            nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet("unet.safetensors", "default")
            clip = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip("clip.safetensors", "flux")
            nodes.NODE_CLASS_MAPPINGS["CLIPTextEncode"]().encode(clip[0], "a cat")

        terminal_outcomes = [e for e in trace.events if "terminal_outcome" in e.metadata]
        self.assertEqual(
            len(terminal_outcomes), 3,
            f"expected exactly 3 terminal outcome events (UNET, CLIP, prefill), got {len(terminal_outcomes)}",
        )
        for event in terminal_outcomes:
            self.assertEqual(event.metadata["terminal_outcome"], "prepared")


if __name__ == "__main__":
    unittest.main()
