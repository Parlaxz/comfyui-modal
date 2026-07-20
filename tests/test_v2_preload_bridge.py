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

    class VAELoader:
        def load_vae(self, vae_name):
            calls.append(("vae", vae_name))
            return (f"vae:{vae_name}",)

    class CLIPTextEncode:
        def encode(self, clip, text):
            calls.append(("prefill", id(clip), text))
            return (f"conditioning:{text}",)

    return SimpleNamespace(
        NODE_CLASS_MAPPINGS={
            "UNETLoader": UNETLoader,
            "CLIPLoader": CLIPLoader,
            "DualCLIPLoader": DualCLIPLoader,
            "VAELoader": VAELoader,
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

    def test_execution_prefill_model_wait_does_not_overwrite_graph_wait(self):
        coordinator = ModelPreloadCoordinator(unet_loader=lambda _key: "unet")
        trace = RuntimeTrace(request_id="prefill-wait", process="remote")
        try:
            model_key = ModelRestoreKey(unet_identity="u")
            preparation = coordinator.prepare(
                model_key,
                PrefillKey(model_key=model_key),
                prepare_clip=False,
            )
            self.assertEqual(
                coordinator.wait_unet(
                    preparation,
                    trace=trace,
                    demand_source="execution_prefill",
                ),
                "unet",
            )
            self.assertEqual(preparation.diagnostics.unet_actual_graph_wait_ms, 0.0)
            wait_events = [
                event
                for event in trace.events
                if event.name in {"unet_wait_start", "unet_wait_end"}
            ]
            self.assertEqual(len(wait_events), 2)
            self.assertTrue(all(event.phase == "execution" for event in wait_events))
            self.assertTrue(
                all(
                    event.metadata.get("demand_source") == "execution_prefill"
                    for event in wait_events
                )
            )
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
        # CLIPTextEncode falls back to original because prefill is now
        # deferred to execution-phase single-flight (schedule_execution_prefill).
        # The original encode still produces correct conditioning.
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
            # Prefill is deferred to execution — graph calls original directly
            "graph_prefill_demand",
            # Phase 4 worker events
            "preload_submitted",
            "preload_worker_started",
            "preload_worker_finished",
            # Phase 4 terminal outcome — UNET and CLIP are prepared
            "graph_model_demand",
            "graph_wait_started",
            "graph_wait_finished",
            "prepared_result_consumed",
        ):
            self.assertIn(expected, event_names)

        # Prefill falls back to original during graph time (deferred)
        self.assertIn("original_loader_fallback", event_names,
                      "prefill should fall back to original when not scheduled for execution")

        # Verify terminal outcome metadata for UNET and CLIP lanes
        unet_terminal = [e for e in trace.events if e.name == "prepared_result_consumed" and e.metadata.get("lane") == "UNET"]
        self.assertEqual(len(unet_terminal), 1)
        self.assertEqual(unet_terminal[0].metadata.get("terminal_outcome"), "prepared")
        self.assertIn("hashed_planned_identity", unet_terminal[0].metadata)
        self.assertIn("graph_wait_duration_ms", unet_terminal[0].metadata)

        clip_terminal = [e for e in trace.events if e.name == "prepared_result_consumed" and e.metadata.get("lane") == "CLIP"]
        self.assertEqual(len(clip_terminal), 1)
        self.assertEqual(clip_terminal[0].metadata.get("terminal_outcome"), "prepared")

        # No fallback events on the UNET/CLIP success path
        for bad in ("identity_mismatch", "request_spec_missing", "future_failed", "future_unavailable"):
            bad_events = [e for e in trace.events if e.name == bad and e.metadata.get("lane") in ("UNET", "CLIP")]
            self.assertEqual(len(bad_events), 0, f"fallback event '{bad}' must not appear for UNET/CLIP")

        # Worker events carry lane metadata (UNET and CLIP lanes only; prefill is deferred)
        worker_events = [e for e in trace.events if e.name in ("preload_worker_started", "preload_worker_finished")]
        for event in worker_events:
            self.assertIn(event.metadata.get("lane"), ("unet", "clip"))

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
        self.assertIn("hashed_planned_identity", failed_events[0].metadata,
                      "future_failed must carry hashed_planned_identity")
        self.assertNotEqual(
            failed_events[0].metadata["hashed_planned_identity"], "",
            "hashed_planned_identity must be non-empty",
        )

    def test_every_graph_demand_has_exactly_one_terminal_outcome(self):
        """Every graph loader demand must end in exactly one terminal outcome.

        For the success path (UNET and CLIP from prepared restore, prefill
        deferred to execution fallback), verify that UNET and CLIP produce
        *prepared* while prefill produces *fallback_unavailable* (since no
        execution prefill was scheduled in this test).
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
        # UNET prepared + CLIP prepared + prefill fallback = 3 terminal outcomes
        self.assertEqual(
            len(terminal_outcomes), 3,
            f"expected exactly 3 terminal outcome events (UNET, CLIP, prefill), got {len(terminal_outcomes)}",
        )
        for event in terminal_outcomes:
            lane = event.metadata.get("lane", "")
            if lane in ("UNET", "CLIP"):
                self.assertEqual(
                    event.metadata["terminal_outcome"], "prepared",
                    f"{lane} should be 'prepared', got {event.metadata['terminal_outcome']}",
                )
            else:
                # Prefill is deferred — falls back to original encoder
                self.assertIn(
                    event.metadata["terminal_outcome"],
                    ("fallback_unavailable",),
                    f"prefill should fall back, got {event.metadata['terminal_outcome']}",
                )


    # ── Phase 0: Canonical per-lane event vocabulary ──────────────────

    def _assert_bridge_events_for_lane(
        self,
        events: list,
        lane: str,
        *,
        expect_graph_demand: bool = True,
    ) -> None:
        """Assert bridge-level canonical events exist for *lane*.

        These fire without core dispatch wrappers: ``submitted``,
        ``ready``/``failed`` (producer) and ``graph_demand``,
        ``graph_wait_start``, ``graph_wait_end`` (consumer).
        Wrapper-only events (``read_*``, ``cpu_prepare_*``, ``gpu_*``)
        are tested separately via ``test_core_wrapper_*`` methods.
        """
        # Producer events fired unconditionally from run()
        for name in ("submitted", "ready"):
            matching = [e for e in events if e.name == name and e.metadata.get("lane") == lane]
            self.assertEqual(
                len(matching), 1,
                f"expected exactly one '{name}' event for lane {lane!r}, got {len(matching)}",
            )
            self.assertEqual(matching[0].phase, "restore",
                             f"'{name}' for lane {lane!r} should have phase='restore'")
        # No failed on success path
        failed = [e for e in events if e.name == "failed" and e.metadata.get("lane") == lane]
        self.assertEqual(len(failed), 0, f"lane {lane!r} should not have 'failed' on success path")
        # Consumer events (phase="execution")
        if expect_graph_demand:
            for name in ("graph_demand", "graph_wait_start", "graph_wait_end"):
                matching = [e for e in events if e.name == name and e.metadata.get("lane") == lane]
                self.assertEqual(
                    len(matching), 1,
                    f"expected exactly one '{name}' event for lane {lane!r}, got {len(matching)}",
                )
                self.assertEqual(matching[0].phase, "execution",
                                 f"'{name}' for lane {lane!r} should have phase='execution'")

    def test_canonical_events_emitted_for_all_lanes(self):
        """submitted/ready/graph_demand/graph_wait_start/end for UNET and CLIP."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-all", process="remote")
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
            nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet("unet.safetensors", "default")
            nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip("clip.safetensors", "flux")

        events = list(trace.events)
        self._assert_bridge_events_for_lane(events, "UNET")
        self._assert_bridge_events_for_lane(events, "CLIP")

    def test_bridge_event_ordering(self):
        """submitted < ready; graph_demand <= graph_wait_start <= graph_wait_end."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-order", process="remote")
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)
        with bridge.request_scope():
            nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet("unet.safetensors", "default")

        events = list(trace.events)

        def _t(name: str) -> int:
            match = [e for e in events if e.name == name and e.metadata.get("lane") == "UNET"]
            return match[0].monotonic_ns if match else 0

        t_submit = _t("submitted")
        t_ready = _t("ready")
        self.assertGreater(t_submit, 0, "submitted must exist")
        self.assertGreater(t_ready, 0, "ready must exist")
        self.assertLess(t_submit, t_ready, "submitted < ready")

        # Consumer ordering
        t_gd = _t("graph_demand")
        t_gws = _t("graph_wait_start")
        t_gwe = _t("graph_wait_end")
        self.assertGreater(t_gd, 0, "graph_demand must exist")
        self.assertGreater(t_gws, 0, "graph_wait_start must exist")
        self.assertGreater(t_gwe, 0, "graph_wait_end must exist")
        self.assertLessEqual(t_gd, t_gws, "graph_demand <= graph_wait_start")
        self.assertLessEqual(t_gws, t_gwe, "graph_wait_start <= graph_wait_end")

    def test_overlapping_unet_clip_lane_routing(self):
        """Concurrent UNET/CLIP each get correct submitted/ready lane."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-overlap", process="remote")
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
            nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet("unet.safetensors", "default")
            nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip("clip.safetensors", "flux")

        events = list(trace.events)

        for name in ("submitted", "ready"):
            unet = [e for e in events if e.name == name and e.metadata.get("lane") == "UNET"]
            clip = [e for e in events if e.name == name and e.metadata.get("lane") == "CLIP"]
            self.assertEqual(len(unet), 1, f"exactly one UNET '{name}'")
            self.assertEqual(len(clip), 1, f"exactly one CLIP '{name}'")

    def test_failure_emits_failed_events(self):
        """When a loader raises, the lane emits ``failed`` not ``ready``."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-fail", process="remote")
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "broken.safetensors", "weight_dtype": "default"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)
        # Inject failure into the coordinator's loader
        bridge.coordinator.unet_loader = lambda key: (_ for _ in ()).throw(
            RuntimeError("simulated crash")
        )
        import time
        time.sleep(0.3)

        result = bridge._consume_unet((), {"unet_name": "unet.safetensors"})
        self.assertIs(result, _LOADER_MISS, "must fall back on worker crash")

        events = list(trace.events)
        failed_events = [e for e in events if e.name == "failed" and e.metadata.get("lane") == "UNET"]
        self.assertGreaterEqual(len(failed_events), 1,
                                "UNET lane must emit 'failed' on crash")
        ready_events = [e for e in events if e.name == "ready" and e.metadata.get("lane") == "UNET"]
        self.assertEqual(len(ready_events), 0, "UNET lane must NOT emit 'ready' on crash")

        gwe = [e for e in events if e.name == "graph_wait_end" and e.metadata.get("lane") == "UNET"]
        self.assertGreaterEqual(len(gwe), 1)
        self.assertEqual(gwe[0].metadata.get("status"), "error")

        self.assertIn("preload_worker_failed", [e.name for e in events])
        self.assertIn("future_failed", [e.name for e in events])

    def test_graph_demand_wait_events_with_existing(self):
        """Canonical graph_demand/wait_start/wait_end appear alongside existing."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-graph", process="remote")
        workflow = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)
        with bridge.request_scope():
            nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip("clip.safetensors", "flux")

        events = list(trace.events)
        for existing in ("graph_clip_demand", "graph_clip_wait_start", "graph_clip_wait_end",
                         "graph_model_demand", "graph_wait_started", "graph_wait_finished"):
            self.assertIn(existing, [e.name for e in events],
                          f"existing event '{existing}' must remain")

        for name in ("graph_demand", "graph_wait_start", "graph_wait_end"):
            matching = [e for e in events if e.name == name and e.metadata.get("lane") == "CLIP"]
            self.assertEqual(len(matching), 1, f"expected one '{name}' for CLIP")
            self.assertEqual(matching[0].phase, "execution")

    def test_no_duplicate_original_loader_calls(self):
        """Original loader called exactly once per identity match."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-nodup", process="remote")
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
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)
        with bridge.request_scope():
            nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet("unet.safetensors", "default")
            nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip("clip.safetensors", "flux")

        unet_calls = [c for c in calls if c[0] == "unet"]
        clip_calls = [c for c in calls if c[0] == "clip"]
        self.assertEqual(len(unet_calls), 1, "UNET original loader called exactly once")
        self.assertEqual(len(clip_calls), 1, "CLIP original loader called exactly once")

        event_names = [e.name for e in trace.events]
        for bad in ("identity_mismatch", "request_spec_missing",
                     "future_failed", "future_unavailable"):
            bad_for_lane = [
                e for e in trace.events
                if e.name == bad and e.metadata.get("lane") in ("UNET", "CLIP")
            ]
            self.assertEqual(len(bad_for_lane), 0,
                             f"unexpected fallback event '{bad}' for UNET/CLIP")

    def test_no_duplicate_clip_loader_for_identity_match(self):
        """CLIP original loader called exactly once when planned identity matches."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-clip-nodup", process="remote")
        workflow = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=trace)
        with bridge.request_scope():
            result = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "clip.safetensors", "flux"
            )

        self.assertIsInstance(result[0], _FakeClip)
        clip_calls = [c for c in calls if c[0] == "clip"]
        self.assertEqual(len(clip_calls), 1,
                         "CLIP original loader must be called exactly once on identity match")
        self.assertEqual(clip_calls[0][1], "clip.safetensors",
                         "CLIP call must use the correct identity")

        event_names = [e.name for e in trace.events]
        self.assertIn("graph_clip_demand", event_names)
        self.assertIn("graph_clip_consumed", event_names)
        self.assertIn("prepared_result_consumed", event_names)

        # Verify terminal outcome metadata
        terminal = [
            e for e in trace.events
            if e.name == "prepared_result_consumed" and e.metadata.get("lane") == "CLIP"
        ]
        self.assertEqual(len(terminal), 1)
        self.assertEqual(terminal[0].metadata.get("terminal_outcome"), "prepared")
        self.assertIn("hashed_planned_identity", terminal[0].metadata)

        # No fallback events for CLIP
        for bad in ("identity_mismatch", "request_spec_missing", "original_loader_fallback"):
            bad_for_clip = [
                e for e in trace.events
                if e.name == bad and e.metadata.get("lane") == "CLIP"
            ]
            self.assertEqual(len(bad_for_clip), 0,
                             f"unexpected fallback event '{bad}' for CLIP on identity match")

    # ── Phase 0 gate-1: Core dispatch wrapper tests ───────────────────

    def _make_fake_comfy(self):
        """Create fake ``comfy.utils`` and ``comfy.model_management`` modules."""
        class FakeUtils:
            def load_torch_file(self, ckpt, safe_load=False, device=None, return_metadata=False):
                return {"weight": "fake"}

        class FakeModelManagement:
            def load_models_gpu(self, models, memory_required=0, force_patch_weights=False,
                                minimum_memory_required=None, force_full_load=False):
                return None

        import types
        utils_mod = types.ModuleType("comfy.utils")
        utils_mod.load_torch_file = FakeUtils().load_torch_file
        mm_mod = types.ModuleType("comfy.model_management")
        mm_mod.load_models_gpu = FakeModelManagement().load_models_gpu
        return utils_mod, mm_mod

    def _install_on_fakes(self):
        """Install core dispatch wrappers on fake comfy modules.

        Returns (utils_mod, mm_mod) so tests can call the original functions
        through the wrappers.
        """
        from comfymodal_runtime.model_preload import (
            _make_torch_file_wrapper, _make_gpu_loader_wrapper,
        )
        utils_mod, mm_mod = self._make_fake_comfy()
        # Install on the fake modules
        orig_torch = utils_mod.load_torch_file
        utils_mod.load_torch_file = _make_torch_file_wrapper(orig_torch)
        orig_gpu = mm_mod.load_models_gpu
        mm_mod.load_models_gpu = _make_gpu_loader_wrapper(orig_gpu)
        return utils_mod, mm_mod

    def _events_from(self, lane_trace):
        """Return the trace events emitted by *lane_trace*."""
        return list(lane_trace._trace.events)

    def test_core_wrapper_single_read(self):
        """Single load_torch_file fires one read_start/read_end + cpu_prepare."""
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        trace = RuntimeTrace(request_id="wr-single", process="remote")
        lane = ModelLaneTrace(trace, "UNET", expected_read_count=1)
        utils_mod, _mm = self._install_on_fakes()

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            utils_mod.load_torch_file("model.safetensors")
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
        lane.ready()

        ev = self._events_from(lane)
        self.assertEqual(len([e for e in ev if e.name == "read_start" and e.metadata.get("lane") == "UNET"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "read_end" and e.metadata.get("lane") == "UNET"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "cpu_prepare_start" and e.metadata.get("lane") == "UNET"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "cpu_prepare_end" and e.metadata.get("lane") == "UNET"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "ready" and e.metadata.get("lane") == "UNET"]), 1)

    def test_core_wrapper_dual_clip_reads_then_cpu(self):
        """Two load_torch_file calls followed by cpu_prepare_start."""
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        trace = RuntimeTrace(request_id="wr-dual", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", expected_read_count=2)
        utils_mod, _mm = self._install_on_fakes()

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            utils_mod.load_torch_file("clip_l.safetensors")
            utils_mod.load_torch_file("t5xxl.safetensors")
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
        lane.ready()

        ev = self._events_from(lane)
        read_starts = [e for e in ev if e.name == "read_start"]
        read_ends = [e for e in ev if e.name == "read_end"]
        cpu_starts = [e for e in ev if e.name == "cpu_prepare_start"]
        self.assertEqual(len(read_starts), 2, "two read_start events")
        self.assertEqual(len(read_ends), 2, "two read_end events")
        self.assertEqual(len(cpu_starts), 1, "one cpu_prepare_start")
        # cpu_prepare_start fires after second read_end
        self.assertGreaterEqual(
            cpu_starts[0].monotonic_ns, read_ends[1].monotonic_ns,
            "cpu_prepare_start after second read_end",
        )

    def test_core_wrapper_no_gpu_commit_for_unet(self):
        """UNET read only — no load_models_gpu call, no gpu_commit events."""
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        trace = RuntimeTrace(request_id="wr-nogpu", process="remote")
        lane = ModelLaneTrace(trace, "UNET", expected_read_count=1)
        utils_mod, mm_mod = self._install_on_fakes()

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            utils_mod.load_torch_file("model.safetensors")
            # No call to load_models_gpu — typical UNET preparation
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
        lane.ready()

        ev = self._events_from(lane)
        gpu_commits = [e for e in ev if e.name in ("gpu_commit_start", "gpu_commit_end")]
        gpu_waits = [e for e in ev if e.name in ("gpu_lane_wait_start", "gpu_lane_wait_end")]
        self.assertEqual(len(gpu_commits), 0, "no gpu_commit events for UNET read-only prep")
        self.assertEqual(len(gpu_waits), 0, "no gpu_lane_wait events for UNET read-only prep")

    def test_core_wrapper_conditional_clip_gpu_commit(self):
        """CLIP lane: load_models_gpu fires gpu_commit_start/end + waits."""
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        trace = RuntimeTrace(request_id="wr-gpu", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", expected_read_count=1)
        utils_mod, mm_mod = self._install_on_fakes()

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            utils_mod.load_torch_file("clip.safetensors")
            mm_mod.load_models_gpu(["clip_model"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
        lane.ready()

        ev = self._events_from(lane)
        self.assertEqual(len([e for e in ev if e.name == "gpu_commit_start"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "gpu_commit_end"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "gpu_lane_wait_start"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "gpu_lane_wait_end"]), 1)
        for name in ("gpu_lane_wait_start", "gpu_lane_wait_end"):
            evt = [e for e in ev if e.name == name][0]
            self.assertEqual(evt.metadata.get("status"), "unlocked",
                             f"{name} carries status=unlocked")

    def test_core_wrapper_cpu_prepare_ends_before_gpu_commit(self):
        """cpu_prepare_end fires before gpu_commit_start."""
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        trace = RuntimeTrace(request_id="wr-cpuend", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", expected_read_count=1)
        utils_mod, mm_mod = self._install_on_fakes()

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            utils_mod.load_torch_file("clip.safetensors")
            mm_mod.load_models_gpu(["clip_model"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
        lane.ready()

        ev = self._events_from(lane)
        cpu_end = [e for e in ev if e.name == "cpu_prepare_end"][0]
        gpu_start = [e for e in ev if e.name == "gpu_commit_start"][0]
        self.assertLessEqual(cpu_end.monotonic_ns, gpu_start.monotonic_ns,
                             "cpu_prepare_end <= gpu_commit_start")

    def test_core_wrapper_reentrant_gpu(self):
        """Nested load_models_gpu calls do not duplicate events."""
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        trace = RuntimeTrace(request_id="wr-reent", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", expected_read_count=1)
        utils_mod, mm_mod = self._install_on_fakes()

        # Mock a nested call by wrapping load_models_gpu to call itself
        original = mm_mod.load_models_gpu
        def nested_gpu(models, **kw):
            # Simulates reentrancy: inner call before outer work
            original(models, **kw)
            return None

        # Replace the wrapper to call itself recursively at depth 1
        # Build a chain: mm_mod.load_models_gpu -> wrapper -> nested -> wrapper -> original
        from comfymodal_runtime.model_preload import _make_gpu_loader_wrapper
        mm_mod.load_models_gpu = _make_gpu_loader_wrapper(nested_gpu)

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            utils_mod.load_torch_file("clip.safetensors")
            mm_mod.load_models_gpu(["clip_model"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
        lane.ready()

        ev = self._events_from(lane)
        gpu_starts = [e for e in ev if e.name == "gpu_commit_start"]
        gpu_ends = [e for e in ev if e.name == "gpu_commit_end"]
        # Only outer scope emits commit events
        self.assertEqual(len(gpu_starts), 1, "nested gpu must not duplicate commit_start")
        self.assertEqual(len(gpu_ends), 1, "nested gpu must not duplicate commit_end")

    def test_core_wrapper_exception_closes_spans(self):
        """Exception in load_torch_file closes open spans and emits failed."""
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        trace = RuntimeTrace(request_id="wr-exc", process="remote")
        lane = ModelLaneTrace(trace, "UNET", expected_read_count=1)
        utils_mod, _mm = self._install_on_fakes()

        # Make load_torch_file raise
        def broken_torch(*a, **kw):
            raise RuntimeError("disk error")

        from comfymodal_runtime.model_preload import _make_torch_file_wrapper
        utils_mod.load_torch_file = _make_torch_file_wrapper(broken_torch)

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            with self.assertRaises(RuntimeError):
                utils_mod.load_torch_file("model.safetensors")
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
        lane.failed()

        ev = self._events_from(lane)
        self.assertEqual(len([e for e in ev if e.name == "read_start"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "read_end"]), 1)
        self.assertEqual(len([e for e in ev if e.name == "failed"]), 1)
        # cpu_prepare may or may not have started — but no ready
        self.assertEqual(len([e for e in ev if e.name == "ready"]), 0)
        read_end = [e for e in ev if e.name == "read_end"][0]
        self.assertEqual(read_end.metadata.get("status"), None)  # no extra status

    def test_core_wrapper_pass_through_outside_lane(self):
        """Wrappers pass through with no events when no lane context active."""
        from comfymodal_runtime.model_preload import _ACTIVE_LANE_TRACE
        utils_mod, mm_mod = self._install_on_fakes()

        # No lane context set — wrappers must be pass-through
        result = utils_mod.load_torch_file("model.safetensors")
        self.assertEqual(result, {"weight": "fake"})
        mm_mod.load_models_gpu(["model"])

    def test_core_wrapper_concurrent_lane_routing(self):
        """Two lane traces active on different threads route events correctly.

        Uses threading Events for deterministic ordering without sleeps.
        """
        from comfymodal_runtime.model_preload import (
            ModelLaneTrace, _ACTIVE_LANE_TRACE,
        )
        import threading

        trace1 = RuntimeTrace(request_id="wr-con-1", process="remote")
        trace2 = RuntimeTrace(request_id="wr-con-2", process="remote")
        lane1 = ModelLaneTrace(trace1, "UNET", expected_read_count=1)
        lane2 = ModelLaneTrace(trace2, "CLIP", expected_read_count=1)
        utils_mod, _mm = self._install_on_fakes()

        barrier = threading.Barrier(2, timeout=5)
        results: dict[str, list] = {}
        lock = threading.Lock()

        def worker(lane, lane_name, name):
            token = _ACTIVE_LANE_TRACE.set(lane)
            try:
                barrier.wait()
                utils_mod.load_torch_file(f"{name}.safetensors")
            finally:
                _ACTIVE_LANE_TRACE.reset(token)
            lane.ready()
            with lock:
                results[lane_name] = list(lane._trace.events)

        t1 = threading.Thread(target=worker, args=(lane1, "UNET", "unet"))
        t2 = threading.Thread(target=worker, args=(lane2, "CLIP", "clip"))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        self.assertIn("UNET", results)
        self.assertIn("CLIP", results)
        for ev in results["UNET"]:
            self.assertEqual(ev.metadata.get("lane"), "UNET")
        for ev in results["CLIP"]:
            self.assertEqual(ev.metadata.get("lane"), "CLIP")
        self.assertEqual(len([e for e in results["UNET"] if e.name == "read_start"]), 1)
        self.assertEqual(len([e for e in results["CLIP"] if e.name == "read_start"]), 1)

    # ── Phase 0 gate-1: exact CLIP read count derivation ────────────

    def test_compute_clip_expected_read_count_single(self):
        """``_compute_clip_expected_read_count`` returns 1 for CLIPLoader."""
        from comfymodal_runtime.model_preload import V2LoaderBridge
        from comfymodal_runtime.contracts import ModelRestoreKey

        bridge = V2LoaderBridge()
        bridge._model_key = ModelRestoreKey(unet_identity="u", clip_identity="clip.safetensors")
        bridge._model_spec = {
            "loaders": {
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "clip.safetensors"}],
            }
        }
        self.assertEqual(bridge._compute_clip_expected_read_count(), 1)

    def test_compute_clip_expected_read_count_dual(self):
        """``_compute_clip_expected_read_count`` returns 2 for DualCLIPLoader."""
        from comfymodal_runtime.model_preload import V2LoaderBridge
        from comfymodal_runtime.contracts import ModelRestoreKey

        bridge = V2LoaderBridge()
        bridge._model_key = ModelRestoreKey(
            unet_identity="u",
            clip_identity="clip_g.safetensors||clip_l.safetensors",
        )
        bridge._model_spec = {
            "loaders": {
                "clip": [{
                    "loader_class": "DualCLIPLoader",
                    "clip_name1": "clip_g.safetensors",
                    "clip_name2": "clip_l.safetensors",
                }],
            }
        }
        self.assertEqual(bridge._compute_clip_expected_read_count(), 2)

    def test_compute_clip_expected_read_count_fallback(self):
        """Falls back to 1 when request cannot be resolved."""
        from comfymodal_runtime.model_preload import V2LoaderBridge
        from comfymodal_runtime.contracts import ModelRestoreKey

        bridge = V2LoaderBridge()
        bridge._model_key = ModelRestoreKey(unet_identity="u", clip_identity="clip.safetensors")
        bridge._model_spec = {"loaders": {"clip": []}}
        self.assertEqual(bridge._compute_clip_expected_read_count(), 1)

    def test_expected_read_counts_flow_to_coordinator(self):
        """Bridge passes exact expected_read_counts to the coordinator."""
        from unittest.mock import patch
        from comfymodal_runtime.model_preload import ModelPreloadCoordinator, V2LoaderBridge

        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-flow", process="remote")
        workflow = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
        }

        with patch.object(
            ModelPreloadCoordinator, "prepare",
            wraps=bridge.coordinator.prepare,
        ) as mock_prepare:
            bridge.prepare(self._plan(workflow), trace=trace)

        call_kwargs = mock_prepare.call_args[1]
        erc = call_kwargs.get("expected_read_counts", {})
        self.assertEqual(erc.get("unet"), 1, "UNET expected_read_count=1")
        self.assertEqual(erc.get("clip"), 1, "CLIPLoader expected_read_count=1")

    def test_expected_read_counts_dual_flows_to_coordinator(self):
        """DualCLIPLoader expected_read_count=2 flows to the coordinator."""
        from unittest.mock import patch
        from comfymodal_runtime.model_preload import ModelPreloadCoordinator, V2LoaderBridge
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
        from comfymodal_runtime.restore_plan import build_restore_model_spec

        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="phase0-flow-dual", process="remote")

        workflow = {
            "1": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "clip_g.safetensors",
                    "clip_name2": "clip_l.safetensors",
                    "type": "sdxl",
                },
            },
        }
        model_key = ModelRestoreKey(
            unet_identity="",
            clip_identity="clip_g.safetensors||clip_l.safetensors",
            clip_type="sdxl",
        )
        # The plan's model_spec is keyed by unet identity, so DualCLIPLoader
        # won't appear unless we use a plan that includes it.  Pass an
        # explicit model_spec via a custom RestorePlan.
        plan = RestorePlan(
            generation=1,
            model_key=model_key,
            prefill_key=PrefillKey(model_key=model_key),
            model_spec=build_restore_model_spec(workflow, {"unet": []}),
        )

        with patch.object(
            ModelPreloadCoordinator, "prepare",
            wraps=bridge.coordinator.prepare,
        ) as mock_prepare:
            bridge.prepare(plan, trace=trace)

        call_kwargs = mock_prepare.call_args[1]
        erc = call_kwargs.get("expected_read_counts", {})
        self.assertEqual(erc.get("clip"), 2, "DualCLIPLoader expected_read_count=2")

    # ── Phase 0 gate-1: install infrastructure tests ─────────────────

    def test_get_live_module_uses_sys_modules_only(self):
        """``_get_live_module`` only checks ``sys.modules``, never imports."""
        from comfymodal_runtime.model_preload import _get_live_module
        import sys
        # A module that definitely doesn't exist should return None, not raise.
        result = _get_live_module("_nonexistent_module_xyz")
        self.assertIsNone(result, "must return None for unavailable modules")

    def test_install_separate_components(self):
        """Read and GPU wrapper status are tracked independently."""
        import comfymodal_runtime.model_preload as mp
        from comfymodal_runtime.model_preload import _install_read_wrapper, _install_gpu_wrapper
        import types
        # Reset global state (module-level flags may be True from prior tests).
        # Must reference through the module, not from-import, because bools
        # are imported by value.
        mp._read_wrapper_installed = False
        mp._gpu_wrapper_installed = False

        utils_mod = types.ModuleType("comfy.utils")
        utils_mod.load_torch_file = lambda ckpt, **kw: {"weights": ckpt}
        mm_mod = types.ModuleType("comfy.model_management")
        mm_mod.load_models_gpu = lambda models, **kw: None

        # Install only the read wrapper
        status_r = _install_read_wrapper(utils_module=utils_mod)
        self.assertEqual(status_r, "installed")
        self.assertTrue(mp._read_wrapper_installed)
        self.assertFalse(mp._gpu_wrapper_installed, "GPU must NOT be installed yet")
        self.assertTrue(
            getattr(utils_mod.load_torch_file, "_comfy_modal_read_wrapper", False),
            "read wrapper sentinel must be set",
        )

        # Install only the GPU wrapper
        status_g = _install_gpu_wrapper(mm_module=mm_mod)
        self.assertEqual(status_g, "installed")
        self.assertTrue(mp._gpu_wrapper_installed)
        self.assertTrue(
            getattr(mm_mod.load_models_gpu, "_comfy_modal_gpu_wrapper", False),
            "GPU wrapper sentinel must be set",
        )

    def test_install_idempotent_cross_instance(self):
        """Calling install again does not double-wrap (sentinel guard)."""
        from comfymodal_runtime.model_preload import (
            _install_read_wrapper, _install_gpu_wrapper,
        )
        import types

        import comfymodal_runtime.model_preload as mp
        mp._read_wrapper_installed = False
        mp._gpu_wrapper_installed = False

        utils_mod = types.ModuleType("comfy.utils")
        utils_mod.load_torch_file = lambda ckpt, **kw: {"w": ckpt}
        mm_mod = types.ModuleType("comfy.model_management")
        mm_mod.load_models_gpu = lambda models, **kw: None

        # First install
        self.assertEqual(_install_read_wrapper(utils_module=utils_mod), "installed")
        orig_func = utils_mod.load_torch_file

        # Second install (same module, different "caller") — should detect sentinel
        status = _install_read_wrapper(utils_module=utils_mod)
        self.assertEqual(status, "already_installed")
        self.assertIs(utils_mod.load_torch_file, orig_func,
                      "function must not be double-wrapped")

    def test_install_trace_diagnostics(self):
        """``_ensure_core_wrappers`` emits ``core_wrapper_install`` events when trace provided."""
        from comfymodal_runtime.model_preload import _ensure_core_wrappers
        trace = RuntimeTrace(request_id="install-diag", process="remote")

        # In test environment comfy is not in sys.modules, so both components
        # report "unavailable" — the diagnostic events should still be emitted.
        result = _ensure_core_wrappers(trace=trace)

        self.assertIn("load_torch_file", result)
        self.assertIn("load_models_gpu", result)
        # Events should be present on the trace
        diag_events = [e for e in trace.events if e.name == "core_wrapper_install"]
        self.assertGreaterEqual(len(diag_events), 1,
                                "at least one core_wrapper_install event")

    def test_install_partial_then_retry(self):
        """Simulate partial availability: no comfy → retry with it."""
        from comfymodal_runtime.model_preload import (
            _ensure_core_wrappers, _install_read_wrapper,
            _read_wrapper_installed, _gpu_wrapper_installed,
        )
        import types

        import comfymodal_runtime.model_preload as mp
        mp._read_wrapper_installed = False
        mp._gpu_wrapper_installed = False

        # First call — no comfy available in sys.modules
        result1 = _ensure_core_wrappers()
        self.assertEqual(result1.get("load_torch_file"), "unavailable")

        # Now simulate that comfy.utils becomes available (e.g. nodes.py loaded it).
        # Register a fake module in sys.modules.
        import sys
        utils_mod = types.ModuleType("comfy.utils")
        utils_mod.load_torch_file = lambda ckpt, **kw: {"w": ckpt}
        sys.modules["comfy.utils"] = utils_mod

        try:
            # Retry — read wrapper should install now
            result2 = _ensure_core_wrappers()
            self.assertEqual(result2.get("load_torch_file"), "installed",
                             "retry after comfy.utils appears must install read wrapper")
            self.assertTrue(_read_wrapper_installed)
        finally:
            # Clean up sys.modules to avoid polluting other tests
            sys.modules.pop("comfy.utils", None)

    def test_get_live_module_returns_existing(self):
        """``_get_live_module`` returns existing ``sys.modules`` entries."""
        from comfymodal_runtime.model_preload import _get_live_module
        import sys
        # The `sys` module itself should be findable.
        self.assertIs(_get_live_module("sys"), sys,
                      "must return the live sys module")


    # ── Phase 0: late worker event drain ────────────────────────────

    def test_drain_worker_events_recovers_late_events(self):
        """Drain copies worker events; no prefix duplication; phases preserved."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        restore_trace = RuntimeTrace(request_id="drain-test", process="remote")
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
        plan = self._plan(workflow, prefill=False)
        bridge.prepare(plan, trace=restore_trace)

        # Create execution trace and drain.
        exec_trace = RuntimeTrace(request_id="drain-exec", process="remote")
        drained = bridge.drain_worker_events(exec_trace)

        # After drain, execution trace has late worker events (ready, etc.)
        # but NOT restore prefix (submitted, preload_schedule_*) which are
        # before the cursor and already in the restore trace snapshot.
        exec_names = [e.name for e in exec_trace.events]
        self.assertIn("ready", exec_names, "ready must be in drained trace")
        self.assertNotIn("submitted", exec_names,
                         "submitted is restore-prefix, must not be duplicated")
        self.assertNotIn("preload_schedule_start", exec_names,
                         "restore prefix must not be duplicated")

        # No duplicates of non-diagnostic events.
        # ``core_wrapper_install`` and ``unet_decompose_install`` are
        # diagnostic events that legitimately fire once per install
        # attempt (bridge.install + worker fallback).
        _DIAG_EVENTS = frozenset({"core_wrapper_install", "unet_decompose_install"})
        from collections import Counter
        event_names_no_diag = [n for n in exec_names if n not in _DIAG_EVENTS]
        name_counts = Counter(event_names_no_diag)
        dupes = {n: c for n, c in name_counts.items() if c > 1}
        self.assertEqual(len(dupes), 0,
                         f"drained events must have no duplicates: {dupes}")

        # Drained events preserve original phase='restore'.
        for event in exec_trace.events:
            self.assertEqual(event.phase, "restore",
                             "drained events must preserve phase='restore'")

        # Drain is idempotent (second drain yields 0 new events).
        drained2 = bridge.drain_worker_events(exec_trace)
        self.assertEqual(drained2, 0, "second drain must return 0")
        self.assertEqual(len(exec_trace.events), drained + 0,
                         "no new events after second drain")

    def test_drain_worker_events_failure_path(self):
        """Failure path: drain copies failed, not ready.

        To exercise the failure, we inject the broken loader *before*
        prepare (so the submitted worker actually uses it).
        """
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
        # Use a coordinator with a broken loader directly.
        coordinator = ModelPreloadCoordinator(
            unet_loader=lambda key: (_ for _ in ()).throw(
                RuntimeError("simulated crash")
            ),
        )
        bridge = V2LoaderBridge()
        bridge.coordinator = coordinator

        restore_trace = RuntimeTrace(request_id="drain-fail", process="remote")
        model_key = ModelRestoreKey(unet_identity="broken.safetensors")
        bridge._model_key = model_key
        bridge._prefill_key = PrefillKey(model_key=model_key)

        # Prepare via coordinator directly (bypasses bridge.prepare).
        prep = coordinator.prepare(model_key, bridge._prefill_key,
                                   exact_prefill=False, trace=restore_trace)
        bridge._preparation = prep
        bridge._preparation_trace = restore_trace
        bridge._preparation_event_cursor = len(restore_trace.events)

        exec_trace = RuntimeTrace(request_id="drain-fail-exec", process="remote")
        drained = bridge.drain_worker_events(exec_trace)

        # Worker may have completed before or after the cursor (race).
        # If before cursor: drained == 0, but failed is already on restore_trace.
        # If after cursor: drained > 0, failed is on exec_trace.
        # In either case, failed must appear somewhere and never ready.
        all_names = [e.name for e in restore_trace.events] + [e.name for e in exec_trace.events]
        self.assertIn("failed", all_names, "failed must be in restore or exec trace")
        self.assertNotIn("ready", all_names, "ready must NOT appear on failure")
        # No duplicates across merged names (core_wrapper_install and
        # unet_decompose_install can appear once per install attempt).
        _DIAG_EVENTS = frozenset({"core_wrapper_install", "unet_decompose_install"})
        from collections import Counter
        non_diag = [n for n in all_names if n not in _DIAG_EVENTS]
        dupes = {n: c for n, c in Counter(non_diag).items() if c > 1}
        self.assertEqual(len(dupes), 0, f"no duplicates: {dupes}")

    def test_drain_idempotent_no_duplicate_prefix(self):
        """Drain never duplicates events already on the execution trace."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        restore_trace = RuntimeTrace(request_id="drain-nodup", process="remote")
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"},
            },
        }
        bridge.prepare(self._plan(workflow, prefill=False), trace=restore_trace)
        early_count = len(restore_trace.events)

        exec_trace = RuntimeTrace(request_id="drain-nodup-exec", process="remote")
        bridge.drain_worker_events(exec_trace)

        # The execution trace has exactly the new events (restore trace grew by
        # drained count, or already contained them — in either case no dupes).
        from collections import Counter
        name_counts = Counter(e.name for e in exec_trace.events)
        dupes = {n: c for n, c in name_counts.items() if c > 1}
        self.assertEqual(len(dupes), 0,
                         f"execution trace must have no duplicate events: {dupes}")

        # No restore prefix in execution trace.
        self.assertNotIn("preload_schedule_start", [e.name for e in exec_trace.events])

    def test_drain_noop_when_no_trace(self):
        """drain_worker_events returns 0 safely with no preparation."""
        bridge = V2LoaderBridge()
        result = bridge.drain_worker_events(None)
        self.assertEqual(result, 0)
        result = bridge.drain_worker_events(RuntimeTrace(request_id="noop"))
        self.assertEqual(result, 0)

    # ── Phase 1-2: VAE, mutation lane, state machine ────────────────

    def test_mutation_lane_acquire_release(self):
        """Acquire blocks until release; one owner at a time."""
        from comfymodal_runtime.model_preload import _get_mutation_lane
        import threading

        lane = _get_mutation_lane()
        events: list[str] = []
        lock = threading.Lock()

        def worker(name: str, delay: float):
            lane.acquire(name)
            with lock:
                events.append(f"{name}_acquired")
            if delay > 0:
                import time
                time.sleep(delay)
            lane.release(name)
            with lock:
                events.append(f"{name}_released")

        t1 = threading.Thread(target=worker, args=("UNET", 0.05))
        t2 = threading.Thread(target=worker, args=("CLIP", 0.01))
        t1.start()
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)

        self.assertIn("UNET_acquired", events)
        self.assertIn("UNET_released", events)
        self.assertIn("CLIP_acquired", events)
        self.assertIn("CLIP_released", events)

    def test_vae_prepare_via_coordinator(self):
        """Coordinator submits a VAE future when prepare_vae=True."""
        calls: list[tuple] = []
        def fake_vae_loader(key):
            calls.append(("vae", key.vae_identity))
            return "vae_model"

        coordinator = ModelPreloadCoordinator(vae_loader=fake_vae_loader)
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
        model_key = ModelRestoreKey(unet_identity="u", clip_identity="c", vae_identity="vae.safetensors")
        prep = coordinator.prepare(model_key, PrefillKey(model_key=model_key),
                                   exact_prefill=False, prepare_unet=False, prepare_clip=False,
                                   prepare_vae=True, expected_read_counts={"vae": 1})
        self.assertIsNotNone(prep.vae_future, "VAE future must be created")
        result = coordinator.wait_vae(prep)
        self.assertEqual(result, "vae_model")
        self.assertEqual(calls, [("vae", "vae.safetensors")])

    def test_vae_skipped_when_no_identity(self):
        """Coordinator skips VAE when model_key.vae_identity is empty."""
        coordinator = ModelPreloadCoordinator(vae_loader=lambda k: "vae")
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
        model_key = ModelRestoreKey(unet_identity="u", clip_identity="c", vae_identity="")
        prep = coordinator.prepare(model_key, PrefillKey(model_key=model_key),
                                   exact_prefill=False, prepare_unet=False, prepare_clip=False,
                                   prepare_vae=True)
        self.assertIsNone(prep.vae_future, "VAE future must be None when identity empty")

    def test_model_load_state_values(self):
        """ModelLoadState has all required states."""
        from comfymodal_runtime.model_preload import ModelLoadState
        self.assertIn(ModelLoadState.PENDING, ModelLoadState)
        self.assertIn(ModelLoadState.READING, ModelLoadState)
        self.assertIn(ModelLoadState.CPU_READY, ModelLoadState)
        self.assertIn(ModelLoadState.GPU_COMMITTING, ModelLoadState)
        self.assertIn(ModelLoadState.READY, ModelLoadState)
        self.assertIn(ModelLoadState.FAILED, ModelLoadState)

    def test_vae_consume_falls_through_when_no_key(self):
        """VAE consumer falls back to original loader when no plan."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="vae-fallback", process="remote")
        bridge._trace = trace
        # No plan set up — should emit request_spec_missing
        result = bridge._consume_vae((), {"vae_name": "vae.safetensors"})
        self.assertIs(result, _LOADER_MISS)
        names = [e.name for e in trace.events]
        self.assertIn("request_spec_missing", names)
        self.assertIn("original_loader_fallback", names)

    def test_vae_identity_mismatch_falls_through(self):
        """VAE identity mismatch emits fallback."""
        from comfymodal_runtime.contracts import ModelRestoreKey
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="vae-mismatch", process="remote")
        bridge._model_key = ModelRestoreKey(unet_identity="u", clip_identity="c",
                                             vae_identity="planned_vae.safetensors")
        bridge._preparation = bridge.coordinator.prepare(
            bridge._model_key, PrefillKey(model_key=bridge._model_key),
            exact_prefill=False, prepare_unet=False, prepare_clip=False,
            prepare_vae=False, trace=trace)
        bridge._trace = trace
        result = bridge._consume_vae((), {"vae_name": "different_vae.safetensors"})
        self.assertIs(result, _LOADER_MISS)
        names = [e.name for e in trace.events]
        self.assertIn("identity_mismatch", names)
        self.assertIn("original_loader_fallback", names)


    # ── Per-lane prepare flags ───────────────────────────────────────

    def test_prepare_per_lane_flags_skip_unet(self):
        """``prepare_unet=False`` skips UNET submission but still prepares CLIP + VAE."""
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
        from comfymodal_runtime.restore_plan import build_restore_model_spec

        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="lane-skip-unet", process="remote")
        # Workflow with CLIPLoader so model_spec includes clip loaders.
        wf = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "2": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        }
        model_key = ModelRestoreKey(
            unet_identity="unet.safetensors",
            clip_identity="clip.safetensors",
            vae_identity="vae.safetensors",
        )
        plan = RestorePlan(
            generation=1,
            model_key=model_key,
            prefill_key=PrefillKey(model_key=model_key),
            model_spec=build_restore_model_spec(wf, {"unet": []}),
        )
        preparation = bridge.prepare(plan, trace=trace, prepare_unet=False)
        self.assertIsNotNone(preparation)
        self.assertIsNone(preparation.unet_future, "UNET future must be None when prepare_unet=False")
        self.assertIsNotNone(preparation.clip_future, "CLIP future must still exist")
        self.assertIsNotNone(preparation.vae_future, "VAE future must still exist when only UNET is skipped")
        # CLIP still works via bridge
        with bridge.request_scope():
            clip = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "clip.safetensors", "flux"
            )
            self.assertIsInstance(clip[0], _FakeClip)
        # Cleanup
        bridge.close_workers()

    def test_prepare_per_lane_flags_skip_unet_and_vae(self):
        """``prepare_unet=False, prepare_vae=False`` skips both; only CLIP future exists."""
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
        from comfymodal_runtime.restore_plan import build_restore_model_spec

        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="lane-skip-both", process="remote")
        wf = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "2": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        }
        model_key = ModelRestoreKey(
            unet_identity="unet.safetensors",
            clip_identity="clip.safetensors",
            vae_identity="vae.safetensors",
        )
        plan = RestorePlan(
            generation=1,
            model_key=model_key,
            prefill_key=PrefillKey(model_key=model_key),
            model_spec=build_restore_model_spec(wf, {"unet": []}),
        )
        preparation = bridge.prepare(plan, trace=trace,
                                     prepare_unet=False, prepare_vae=False)
        self.assertIsNotNone(preparation)
        self.assertIsNone(preparation.unet_future,
                          "UNET future must be None when prepare_unet=False")
        self.assertIsNotNone(preparation.clip_future, "CLIP future must still exist")
        self.assertIsNone(preparation.vae_future,
                          "VAE future must be None when prepare_vae=False")
        # CLIP still works via bridge
        with bridge.request_scope():
            clip = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "clip.safetensors", "flux"
            )
            self.assertIsInstance(clip[0], _FakeClip)
        bridge.close_workers()

    def test_prepare_per_lane_flags_skip_clip(self):
        """``prepare_clip=False`` skips CLIP submission but still prepares UNET."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="lane-skip-clip", process="remote")
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
        plan = self._plan(workflow, prefill=False)
        preparation = bridge.prepare(plan, trace=trace, prepare_clip=False)
        self.assertIsNotNone(preparation)
        self.assertIsNotNone(preparation.unet_future, "UNET future must still exist")
        self.assertIsNone(preparation.clip_future, "CLIP future must be None when prepare_clip=False")
        # UNET still works via bridge
        with bridge.request_scope():
            unet = nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "unet.safetensors", "default"
            )
            self.assertEqual(unet, ("prepared-unet:unet.safetensors:default",))
        bridge.close_workers()

    def test_prepare_per_lane_flags_default_stays_computed(self):
        """Default (all ``None``) uses existing computed behavior (all lanes)."""
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
        plan = self._plan(workflow, prefill=False)
        preparation = bridge.prepare(plan)
        self.assertIsNotNone(preparation)
        self.assertIsNotNone(preparation.unet_future, "UNET future must exist by default")
        self.assertIsNone(preparation.clip_future, "CLIP future is absent (no clip in plan model_spec)")
        bridge.close_workers()

    # ── Bridge fallback for absent V2 futures ────────────────────────

    def test_unet_skipped_falls_through_to_original(self):
        """When ``prepare_unet=False``, UNET consumption falls through to original loader.

        The bridge's ``_consume_unet`` returns ``_LOADER_MISS``, so the
        original (unpatched) UNETLoader handles the request.
        """
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="unet-skip-fallthrough", process="remote")
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"},
            },
        }
        plan = self._plan(workflow, prefill=False)
        bridge.prepare(plan, trace=trace, prepare_unet=False)
        with bridge.request_scope():
            result = nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "unet.safetensors", "default"
            )
        # Falls through to original loader (both planned and requested load)
        self.assertEqual(result, ("prepared-unet:unet.safetensors:default",))
        unet_calls = [c for c in calls if c[0] == "unet"]
        self.assertEqual(len(unet_calls), 1,
                         "original UNET loader must be called exactly once")
        # Trace shows the bridge fallback emissions
        event_names = [e.name for e in trace.events]
        self.assertIn("future_unavailable", event_names,
                       "must emit future_unavailable when UNET future absent")
        self.assertIn("original_loader_fallback", event_names,
                       "must emit original_loader_fallback when UNET falls through")
        # Verify hashed_planned_identity in future_unavailable
        unavailable_events = [e for e in trace.events if e.name == "future_unavailable"]
        self.assertGreaterEqual(len(unavailable_events), 1)
        for ev in unavailable_events:
            if ev.metadata.get("lane") == "UNET":
                self.assertIn("hashed_planned_identity", ev.metadata,
                              "future_unavailable must carry hashed_planned_identity")
                self.assertNotEqual(
                    ev.metadata["hashed_planned_identity"], "",
                    "hashed_planned_identity must be non-empty",
                )

    def test_vae_skipped_falls_through_to_original(self):
        """When ``prepare_vae=False``, VAE consumption falls through to original loader."""
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
        from comfymodal_runtime.restore_plan import build_restore_model_spec

        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="vae-skip-fallthrough", process="remote")
        workflow = {
            "1": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "vae.safetensors"},
            },
        }
        model_key = ModelRestoreKey(
            unet_identity="u",
            clip_identity="c",
            vae_identity="vae.safetensors",
        )
        plan = RestorePlan(
            generation=1,
            model_key=model_key,
            prefill_key=PrefillKey(model_key=model_key),
            model_spec=build_restore_model_spec(workflow, {"unet": []}),
        )
        bridge._trace = trace
        # Manually set up preparation with no VAE future.
        bridge._model_key = model_key
        bridge._prefill_key = PrefillKey(model_key=model_key)
        prep = bridge.coordinator.prepare(
            model_key, bridge._prefill_key,
            exact_prefill=False,
            prepare_unet=False, prepare_clip=False, prepare_vae=False,
            trace=trace,
        )
        bridge._preparation = prep
        result = bridge._consume_vae((), {"vae_name": "vae.safetensors"})
        self.assertIs(result, _LOADER_MISS, "VAE must fall through when future absent")
        names = [e.name for e in trace.events]
        self.assertIn("future_unavailable", names)
        self.assertIn("original_loader_fallback", names)

    # ── Cleanup: joining legacy background threads ───────────────────

    def test_join_legacy_background_threads_noop_when_no_futures(self):
        """``_join_legacy_background_threads`` returns 0 when API has no futures."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        entrypoint = ModalRuntimeEntrypoint()
        # API with no _actual_load_futures
        api = SimpleNamespace()
        joined = entrypoint._join_legacy_background_threads(api)
        self.assertEqual(joined, 0)

    def test_join_legacy_background_threads_noop_when_none_api(self):
        """Returns 0 when api is None."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        entrypoint = ModalRuntimeEntrypoint()
        joined = entrypoint._join_legacy_background_threads(None)
        self.assertEqual(joined, 0)

    def test_join_legacy_background_threads_skips_dead(self):
        """Only alive threads are joined; dead threads are skipped."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
        import threading

        entrypoint = ModalRuntimeEntrypoint()
        done_event = threading.Event()

        def dead_worker():
            pass

        t = threading.Thread(target=dead_worker, daemon=True)
        t.start()
        t.join(timeout=5)  # thread is now dead
        api = SimpleNamespace()
        api._actual_load_futures = {"key1": t}
        joined = entrypoint._join_legacy_background_threads(api, join_timeout=0.01)
        self.assertEqual(joined, 0, "dead thread must not be counted as joined")

    def test_join_legacy_background_threads_joins_alive(self):
        """Alive threads are joined within the timeout."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
        import threading
        import time

        entrypoint = ModalRuntimeEntrypoint()
        started = threading.Event()
        can_finish = threading.Event()

        def worker():
            started.set()
            can_finish.wait(timeout=5)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        started.wait(timeout=5)
        api = SimpleNamespace()
        api._actual_load_futures = {"alive_key": t}
        # Join with short timeout — thread will still be alive after.
        joined = entrypoint._join_legacy_background_threads(api, join_timeout=0.05)
        self.assertEqual(joined, 1, "one alive thread must be joined")
        # Cleanup
        can_finish.set()
        t.join(timeout=5)

    def test_join_legacy_background_threads_recovers_on_missing_attr(self):
        """Missing _actual_load_futures attribute does not raise."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        entrypoint = ModalRuntimeEntrypoint()
        api = SimpleNamespace()  # no _actual_load_futures
        joined = entrypoint._join_legacy_background_threads(api)
        self.assertEqual(joined, 0)

    def test_join_legacy_background_threads_handles_exception_in_thread(self):
        """Exception during thread.join is swallowed (preserves error behavior)."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        entrypoint = ModalRuntimeEntrypoint()
        # Thread that raises on join (simulated by broken is_alive)
        class BrokenThread:
            def is_alive(self):
                return True
            def join(self, timeout=None):
                raise RuntimeError("join failed")

        api = SimpleNamespace()
        api._actual_load_futures = {"broken": BrokenThread()}
        # Must not propagate — exception is swallowed.
        joined = entrypoint._join_legacy_background_threads(api, join_timeout=0.01)
        self.assertEqual(joined, 0, "join that raises does not count as joined")

    # ── UNET deferral eligibility check ──────────────────────────────

    def test_check_unet_deferral_eligible_happy_path(self):
        """Eligible when API has both helpers and plan has unet_identity."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        api = SimpleNamespace()
        api._patch_unet_loader_cache = lambda: None
        api._start_production_restore_unet = lambda *a, **kw: {"submitted": True}
        plan = SimpleNamespace()
        plan.model_key = SimpleNamespace(unet_identity="unet.safetensors")
        self.assertTrue(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(api, plan)
        )

    def test_check_unet_deferral_eligible_no_unet_identity(self):
        """Not eligible when plan has no unet_identity."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        api = SimpleNamespace()
        api._patch_unet_loader_cache = lambda: None
        api._start_production_restore_unet = lambda *a, **kw: {"submitted": True}
        plan = SimpleNamespace()
        plan.model_key = SimpleNamespace(unet_identity="")
        self.assertFalse(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(api, plan)
        )

    def test_check_unet_deferral_eligible_no_plan(self):
        """Not eligible when plan is None."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        api = SimpleNamespace()
        api._patch_unet_loader_cache = lambda: None
        api._start_production_restore_unet = lambda *a, **kw: {"submitted": True}
        self.assertFalse(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(api, None)
        )

    def test_check_unet_deferral_eligible_missing_patch(self):
        """Not eligible when _patch_unet_loader_cache is absent."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        api = SimpleNamespace()
        api._start_production_restore_unet = lambda *a, **kw: {"submitted": True}
        plan = SimpleNamespace()
        plan.model_key = SimpleNamespace(unet_identity="unet.safetensors")
        self.assertFalse(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(api, plan)
        )

    def test_check_unet_deferral_eligible_missing_start(self):
        """Not eligible when _start_production_restore_unet is absent."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        api = SimpleNamespace()
        api._patch_unet_loader_cache = lambda: None
        plan = SimpleNamespace()
        plan.model_key = SimpleNamespace(unet_identity="unet.safetensors")
        self.assertFalse(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(api, plan)
        )

    def test_check_unet_deferral_eligible_never_raises(self):
        """Eligibility check never raises on broken input."""
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

        self.assertFalse(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(None, None)
        )
        self.assertFalse(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(
                object(), SimpleNamespace()
            )
        )
        self.assertFalse(
            ModalRuntimeEntrypoint._check_unet_deferral_eligible(
                SimpleNamespace(), object()
            )
        )

    # ── Extension: extend existing preparation instead of clear+reprepare ──

    def test_extension_preserves_clip_and_adds_unet(self):
        """Extending after clip-only prepare preserves clip, adds UNET, no duplicate CLIP call."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="ext-preserve", process="remote")
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
        }

        # Step 1: clip-only prepare
        plan = self._plan(workflow, prefill=False)
        prep = bridge.prepare(plan, trace=trace, prepare_unet=False, prepare_vae=False)
        self.assertIsNotNone(prep)
        self.assertIsNone(prep.unet_future, "UNET future must be None in clip-only prepare")
        self.assertIsNotNone(prep.clip_future, "CLIP future must exist")
        bridge.close_workers()

        clip_calls_before = [c for c in calls if c[0] == "clip"]
        self.assertEqual(len(clip_calls_before), 1, "CLIP loaded once in clip-only prepare")

        # Step 2: extend with UNET only
        extended = bridge.extend_preparation(prepare_unet=True, prepare_vae=False, trace=trace)
        self.assertIsNotNone(extended)
        self.assertIs(extended, prep, "extend must return the same preparation object")
        bridge.close_workers()

        clip_calls_after = [c for c in calls if c[0] == "clip"]
        unet_calls = [c for c in calls if c[0] == "unet"]
        self.assertEqual(len(clip_calls_after), 1,
                         "CLIP must NOT be loaded again during extension")
        self.assertEqual(len(unet_calls), 1,
                         "UNET loaded once during extension")

        # Step 3: graph consumption uses prepared objects
        with bridge.request_scope():
            unet_result = nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "unet.safetensors", "default"
            )
            clip_result = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "clip.safetensors", "flux"
            )

        self.assertEqual(unet_result, ("prepared-unet:unet.safetensors:default",))
        self.assertIsInstance(clip_result[0], _FakeClip,
                              "graph must return originally prepared CLIP object")

        # No fallback events for UNET or CLIP
        for bad in ("identity_mismatch", "request_spec_missing", "original_loader_fallback"):
            bad_for_lane = [
                e for e in trace.events
                if e.name == bad and e.metadata.get("lane") in ("UNET", "CLIP")
            ]
            self.assertEqual(len(bad_for_lane), 0,
                             f"unexpected fallback event '{bad}' for UNET/CLIP")

        # Verify trace has extension events
        event_names = [e.name for e in trace.events]
        self.assertIn("preload_extension_submitted", event_names,
                      "trace must contain preload_extension_submitted")

    def test_extension_adds_vae_when_identity_present(self):
        """Extension submits VAE when model_key.vae_identity is non-empty."""
        from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
        from comfymodal_runtime.restore_plan import build_restore_model_spec

        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="ext-vae", process="remote")
        workflow = {
            "1": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
        }
        model_key = ModelRestoreKey(
            unet_identity="unet.safetensors",
            clip_identity="clip.safetensors",
            vae_identity="vae.safetensors",
        )
        plan = RestorePlan(
            generation=1,
            model_key=model_key,
            prefill_key=PrefillKey(model_key=model_key),
            model_spec=build_restore_model_spec(workflow, {"unet": []}),
        )

        # Step 1: clip-only prepare
        prep = bridge.prepare(plan, trace=trace, prepare_unet=False, prepare_clip=True, prepare_vae=False)
        bridge.close_workers()
        self.assertIsNotNone(prep.clip_future)

        # Step 2: extend with VAE only
        bridge.extend_preparation(prepare_unet=False, prepare_vae=True, trace=trace)
        bridge.close_workers()

        self.assertIsNotNone(prep.vae_future, "VAE future must be created during extension")
        vae_calls = [c for c in calls if c[0] == "vae"]
        self.assertEqual(len(vae_calls), 1, "VAE loaded once during extension")

        # CLIP still called only once
        clip_calls = [c for c in calls if c[0] == "clip"]
        self.assertEqual(len(clip_calls), 1, "CLIP must NOT be reloaded during VAE extension")

    def test_extension_idempotent_no_duplicate(self):
        """Calling extend twice does not duplicate futures or original loader calls."""
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge = V2LoaderBridge()
        bridge.install(nodes)
        trace = RuntimeTrace(request_id="ext-idem", process="remote")
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "unet.safetensors", "weight_dtype": "default"}},
        }
        plan = self._plan(workflow, prefill=False)

        bridge.prepare(plan, trace=trace, prepare_unet=False, prepare_vae=False)
        bridge.close_workers()

        # First extend
        bridge.extend_preparation(prepare_unet=True, trace=trace)
        bridge.close_workers()
        unet_after_first = len([c for c in calls if c[0] == "unet"])
        self.assertEqual(unet_after_first, 1, "UNET loaded once after first extend")

        # Second extend — should be no-op (future already present)
        bridge.extend_preparation(prepare_unet=True, prepare_vae=True, trace=trace)
        bridge.close_workers()
        unet_after_second = len([c for c in calls if c[0] == "unet"])
        self.assertEqual(unet_after_second, 1,
                         "UNET must NOT be loaded again during second extend (idempotent)")
        self.assertIn("preload_extension_skipped", [e.name for e in trace.events],
                      "idempotent extend must emit preload_extension_skipped")

    def test_extension_none_preparation_returns_none(self):
        """extend_preparation returns None when no preparation exists."""
        bridge = V2LoaderBridge()
        result = bridge.extend_preparation(prepare_unet=True, trace=None)
        self.assertIsNone(result, "extend_preparation must return None with no preparation")

    # ── SD state-dict wrapper and residual ──────────────────────────

    def _with_fake_sd_module(self):
        """Temporarily install a fake ``comfy.sd`` module in sys.modules
        whose ``load_diffusion_model_state_dict`` calls known subfunction
        wrappers (calculate_parameters, weight_dtype) so child wrapper
        events and residual are exercised."""
        import sys, types
        mod = types.ModuleType("comfy.sd")
        def fake_load_state_dict(ckpt, filter_prefix=None):
            # Exercise the installed child wrappers
            utils = sys.modules.get("comfy.utils")
            if utils is not None:
                if callable(getattr(utils, "calculate_parameters", None)):
                    utils.calculate_parameters(ckpt)
                if callable(getattr(utils, "weight_dtype", None)):
                    utils.weight_dtype(ckpt, "fp16")
            return {"model": "fake"}
        mod.load_diffusion_model_state_dict = fake_load_state_dict
        prev = sys.modules.get("comfy.sd")
        sys.modules["comfy.sd"] = mod
        return mod, prev

    def _cleanup_fake_modules(self, prev_modules: dict):
        import sys
        for name, prev in prev_modules.items():
            if prev is not None:
                sys.modules[name] = prev
            else:
                sys.modules.pop(name, None)

    def _reset_decompose_globals(self):
        import comfymodal_runtime.model_preload as mp
        mp._unet_decompose_ensure_done = False
        mp._sd_wrapper_installed = False
        mp._subfn_wrappers_installed = False

    def test_unet_sd_wrapper_one_outer_span(self):
        """SD state-dict wrapper emits exactly one outer start/end pair, no duplicate from decompose targets."""
        from comfymodal_runtime.model_preload import (
            _ensure_unet_decompose_wrappers, _ACTIVE_LANE_TRACE, ModelLaneTrace,
        )
        self._reset_decompose_globals()
        fake_sd, prev_sd = self._with_fake_sd_module()
        trace = RuntimeTrace(request_id="sd-outer", process="remote")
        lane = ModelLaneTrace(trace, "UNET")
        try:
            install_result = _ensure_unet_decompose_wrappers(trace=trace)
            self.assertIn("load_diffusion_model_state_dict", install_result,
                          "SD wrapper must be in install result")
        finally:
            self._cleanup_fake_modules({"comfy.sd": prev_sd})

        event_names = [e.name for e in trace.events]
        sd_installs = [e for e in trace.events if e.name == "unet_sd_wrapper_install"]
        self.assertGreaterEqual(len(sd_installs), 1,
                                "must emit unet_sd_wrapper_install")

    def test_unet_sd_residual_arithmetic(self):
        """Child subfunction durations are tracked and residual = whole - child_total.
        Each wrapped child emits exactly one start AND one end, and the residual
        event shows measured_child_count and measured_children matching invoked
        child wrappers (nonzero count from calculate_parameters + weight_dtype)."""
        import sys, types
        from comfymodal_runtime.model_preload import (
            _ensure_unet_decompose_wrappers, _ACTIVE_LANE_TRACE, ModelLaneTrace,
        )
        self._reset_decompose_globals()
        fake_sd, prev_sd = self._with_fake_sd_module()

        # Register fake modules for subfunction wrappers
        prev_utils = sys.modules.get("comfy.utils")
        utils_mod = types.ModuleType("comfy.utils")
        utils_mod.calculate_parameters = lambda sd: 12345
        utils_mod.weight_dtype = lambda sd, dtype: sd
        sys.modules["comfy.utils"] = utils_mod

        trace = RuntimeTrace(request_id="sd-residual", process="remote")
        lane = ModelLaneTrace(trace, "UNET")
        _ensure_unet_decompose_wrappers(trace=trace)

        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            fake_sd.load_diffusion_model_state_dict({"test": "data"})
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        self._cleanup_fake_modules({"comfy.sd": prev_sd, "comfy.utils": prev_utils})

        # ── Each child wrapper emits one start AND one end ───────────
        for child_name in ("calculate_parameters", "weight_dtype"):
            starts = [e for e in trace.events if e.name == f"unet_{child_name}_start"]
            ends = [e for e in trace.events if e.name == f"unet_{child_name}_end"]
            self.assertEqual(
                len(starts), 1,
                f"{child_name} must emit exactly one start, got {len(starts)}",
            )
            self.assertEqual(
                len(ends), 1,
                f"{child_name} must emit exactly one end, got {len(ends)}",
            )
            # End event must carry duration_ms
            self.assertIn("duration_ms", ends[0].metadata,
                          f"{child_name} end must carry duration_ms")
            self.assertGreaterEqual(ends[0].metadata["duration_ms"], 0,
                                    f"{child_name} duration_ms must be >= 0")

        # ── Outer SD event has residual ──────────────────────────────
        end_events = [e for e in trace.events if e.name == "unet_load_diffusion_model_state_dict_end"]
        self.assertEqual(len(end_events), 1)
        meta = end_events[0].metadata
        self.assertGreaterEqual(meta["measured_child_total_ms"], 0)
        self.assertAlmostEqual(
            meta["duration_ms"],
            meta["measured_child_total_ms"] + meta["residual_ms"],
            delta=0.02,
            msg="duration_ms ≈ child_total + residual (within clock precision)",
        )
        self.assertGreaterEqual(meta["measured_child_count"], 2,
                                "measured_child_count must be >= 2 (calculate_parameters + weight_dtype)")
        # measured_children list must contain entries for invoked wrappers
        self.assertIsInstance(meta.get("measured_children"), (list, tuple),
                              "measured_children must be list or tuple after freeze")
        self.assertGreaterEqual(len(meta["measured_children"]), 2,
                                "measured_children list must have entries for both invoked wrappers")
        # Each child entry is a non-negative duration
        for child_dur in meta["measured_children"]:
            self.assertGreaterEqual(child_dur, 0)

    # ── Phase 0 gate-4: Pregraph ordering ───────────────────────────


if __name__ == "__main__":
    unittest.main()
