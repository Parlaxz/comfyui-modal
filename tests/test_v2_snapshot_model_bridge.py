"""Focused tests for V2LoaderBridge.use_ready_models — snapshot model consumption.

Proves that pre-loaded CLIP/UNET objects are returned by wrapped graph
loaders, originals are not called, no model-file reads occur on hit,
duplicate-file dual specs are preserved, prompt-only changes rebind,
and mismatch falls through to original loaders.  All tests use mocks
only — no real ComfyUI/Modal/GPU.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import unittest

from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan, stable_hash
from comfymodal_runtime.model_preload import V2LoaderBridge
from comfymodal_runtime.restore_plan import build_restore_model_spec, derive_model_key
from comfymodal_runtime.trace import RuntimeTrace
from comfymodal_runtime.modal_app import _cpu_snapshot_specs_match, _cpu_snapshot_model_keys_match


class _FakeClip:
    """Minimal CLIP stub for snapshot model tests."""
    pass


def _fake_nodes(calls: list[tuple]) -> SimpleNamespace:
    """Create fake ComfyUI node classes that record invocations in *calls*."""
    class UNETLoader:
        def load_unet(self, unet_name, weight_dtype):
            calls.append(("unet", unet_name, weight_dtype))
            return (f"original-unet:{unet_name}:{weight_dtype}",)

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


def _make_snapshot_spec(
    unet_name: str = "snapshot_unet.safetensors",
    clip_name: str = "snapshot_clip.safetensors",
    clip_type: str = "sd3",
    weight_dtype: str = "default",
    dual: bool = False,
    clip_name2: str | None = None,
) -> dict:
    """Build a model_spec matching a CPU snapshot."""
    if dual:
        name2 = clip_name2 if clip_name2 is not None else f"{clip_name}.2"
        return {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": unet_name, "weight_dtype": weight_dtype}],
                "clip": [{"loader_class": "DualCLIPLoader", "clip_name1": clip_name, "clip_name2": name2, "type": clip_type, "device": "default"}],
                "vae": [],
            },
        }
    return {
        "loaders": {
            "unet": [{"loader_class": "UNETLoader", "unet_name": unet_name, "weight_dtype": weight_dtype}],
            "clip": [{"loader_class": "CLIPLoader", "clip_name": clip_name, "type": clip_type, "device": "default"}],
            "vae": [],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Snapshot models returned by wrapped graph loaders
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotModelConsumptionTests(unittest.TestCase):
    """use_ready_models — snapshot CLIP/UNET returned by graph loaders."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="snap-consume", process="remote")
        self.unet_obj = object()
        self.clip_obj = _FakeClip()
        self.model_key = ModelRestoreKey(
            unet_identity="snapshot_unet.safetensors",
            clip_identity="snapshot_clip.safetensors",
            clip_type="sd3",
        )
        self.prefill_key = PrefillKey(
            model_key=self.model_key,
            prompt_bundle_hash="bundle-snap",
        )
        self.model_spec = _make_snapshot_spec()

    def _activate(self):
        """Install snapshot models on the bridge via use_ready_models."""
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=self.prefill_key,
            model_spec=self.model_spec,
            unet=self.unet_obj,
            clip=self.clip_obj,
            trace=self.trace,
        )

    def test_unet_returns_exact_snapshot_object(self):
        """UNET graph loader returns the exact snapshot UNET object."""
        self._activate()
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "snapshot_unet.safetensors", "default"
            )
        # Must be a 1-tuple wrapping the exact snapshot unet object
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], self.unet_obj)

    def test_clip_returns_exact_snapshot_object(self):
        """CLIP graph loader returns the exact snapshot CLIP object."""
        self._activate()
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "snapshot_clip.safetensors", "sd3"
            )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], self.clip_obj)

    def test_both_return_snapshot_objects(self):
        """Both UNET and CLIP return snapshot objects from the same request."""
        self._activate()
        with self.bridge.request_scope():
            unet_result = self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "snapshot_unet.safetensors", "default"
            )
            clip_result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "snapshot_clip.safetensors", "sd3"
            )
        self.assertIs(unet_result[0], self.unet_obj)
        self.assertIs(clip_result[0], self.clip_obj)

    def test_trace_has_consumed_events(self):
        """Graph consumption emits graph_demand/graph_wait/prepared_result_consumed."""
        self._activate()
        with self.bridge.request_scope():
            self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "snapshot_unet.safetensors", "default"
            )
            self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "snapshot_clip.safetensors", "sd3"
            )
        event_names = [e.name for e in self.trace.events]
        for expected in (
            "graph_demand",
            "graph_wait_start",
            "graph_wait_end",
            "prepared_result_consumed",
        ):
            self.assertIn(expected, event_names,
                          f"expected event {expected!r} in trace")
        # Must have terminal_outcome=prepared for both lanes
        terminal = [
            e for e in self.trace.events
            if e.name == "prepared_result_consumed"
        ]
        self.assertEqual(len(terminal), 2)
        for ev in terminal:
            self.assertEqual(ev.metadata.get("terminal_outcome"), "prepared")

    def test_preparation_has_completed_futures(self):
        """After use_ready_models, both futures are done with correct results."""
        self._activate()
        prep = self.bridge._preparation
        self.assertIsNotNone(prep)
        self.assertTrue(prep.unet_future.done())
        self.assertTrue(prep.clip_future.done())
        self.assertIs(prep.unet_future.result(), self.unet_obj)
        self.assertIs(prep.clip_future.result(), self.clip_obj)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Original loaders NOT called on snapshot hit
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotOriginalNotCalledTests(unittest.TestCase):
    """Original node loader methods are NOT invoked when snapshot is active."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="snap-no-orig", process="remote")
        self.model_key = ModelRestoreKey(
            unet_identity="u.safetensors",
            clip_identity="c.safetensors",
            clip_type="sd3",
        )
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec=_make_snapshot_spec(unet_name="u.safetensors", clip_name="c.safetensors"),
            unet=object(),
            clip=_FakeClip(),
            trace=self.trace,
        )

    def test_unet_original_not_called(self):
        """Original UNET loader must not be called on snapshot hit."""
        with self.bridge.request_scope():
            self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "u.safetensors", "default"
            )
        unet_calls = [c for c in self.calls if c[0] == "unet"]
        self.assertEqual(len(unet_calls), 0,
                         "original UNET loader must not be called on hit")

    def test_clip_original_not_called(self):
        """Original CLIP loader must not be called on snapshot hit."""
        with self.bridge.request_scope():
            self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "c.safetensors", "sd3"
            )
        clip_calls = [c for c in self.calls if c[0] == "clip"]
        self.assertEqual(len(clip_calls), 0,
                         "original CLIP loader must not be called on hit")

    def test_no_request_time_model_file_reads_on_hit(self):
        with self.bridge.request_scope():
            self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "u.safetensors", "default"
            )
            self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "c.safetensors", "sd3"
            )
        model_file_read_paths = [
            call for call in self.calls if call[0] in {"unet", "clip", "dual_clip"}
        ]
        self.assertEqual(model_file_read_paths, [])

    def test_vae_original_still_called(self):
        """Original VAE loader is still called (VAE not part of snapshot)."""
        self.bridge._model_key = ModelRestoreKey(
            unet_identity="u.safetensors",
            clip_identity="c.safetensors",
            vae_identity="ae.safetensors",
            clip_type="sd3",
        )
        with self.bridge.request_scope():
            self.nodes.NODE_CLASS_MAPPINGS["VAELoader"]().load_vae(
                "ae.safetensors"
            )
        vae_calls = [c for c in self.calls if c[0] == "vae"]
        self.assertEqual(len(vae_calls), 1,
                         "original VAE loader must still be called on snapshot hit")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Duplicate-file dual CLIP spec preserved
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotDualClipSpecTests(unittest.TestCase):
    """DualCLIPLoader with duplicate clip filenames is preserved."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="snap-dual", process="remote")
        self.clip_obj = _FakeClip()
        self.unet_obj = object()
        self.workflow = {
            "1": {"class_type": "DualCLIPLoader", "inputs": {
                "clip_name1": "clip_g.safetensors", "clip_name2": "clip_g.safetensors", "type": "sd3",
            }},
            "2": {"class_type": "UNETLoader", "inputs": {
                "unet_name": "u.safetensors", "weight_dtype": "default",
            }},
        }
        self.dual_spec = _make_snapshot_spec(
            unet_name="u.safetensors",
            clip_name="clip_g.safetensors",
            dual=True,
            clip_name2="clip_g.safetensors",  # same filename twice
        )
        self.model_key = derive_model_key(self.workflow)
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec=self.dual_spec,
            unet=self.unet_obj,
            clip=self.clip_obj,
            trace=self.trace,
        )

    def test_dual_spec_loader_class_is_DualCLIPLoader(self):
        """Model spec must preserve loader_class=DualCLIPLoader."""
        spec = self.bridge._model_spec
        clip_loaders = spec.get("loaders", {}).get("clip", [])
        self.assertEqual(len(clip_loaders), 1)
        self.assertEqual(clip_loaders[0].get("loader_class"), "DualCLIPLoader")

    def test_dual_spec_has_both_clip_names(self):
        """Dual spec must contain both clip_name1 and clip_name2."""
        spec = self.bridge._model_spec
        clip_loaders = spec.get("loaders", {}).get("clip", [])
        self.assertEqual(clip_loaders[0].get("clip_name1"), "clip_g.safetensors")
        self.assertEqual(clip_loaders[0].get("clip_name2"), "clip_g.safetensors")

    def test_dual_clip_ready_future_holds_single_object(self):
        """Dual CLIP snapshot stores a single CLIP object (not two)."""
        prep = self.bridge._preparation
        self.assertIsNotNone(prep.clip_future)
        self.assertTrue(prep.clip_future.done())
        result = prep.clip_future.result()
        self.assertIs(result, self.clip_obj)

    def test_duplicate_dual_workflow_key_and_spec_match(self):
        """Real workflow with duplicate DualCLIPLoader matches snapshot key/spec."""
        request_key = derive_model_key(self.workflow)
        request_spec = build_restore_model_spec(self.workflow)
        self.assertTrue(
            _cpu_snapshot_model_keys_match(request_key, self.bridge._model_key),
            "request key must match snapshot key for duplicate dual CLIP",
        )
        self.assertTrue(
            _cpu_snapshot_specs_match(request_spec, self.bridge._model_spec),
            "request spec must match snapshot spec for duplicate dual CLIP",
        )

    def test_duplicate_dual_clip_graph_returns_snapshot_object(self):
        """DualCLIPLoader with identical filenames returns snapshot clip."""
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["DualCLIPLoader"]().load_clip(
                "clip_g.safetensors", "clip_g.safetensors", "sd3"
            )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], self.clip_obj)
        dual_calls = [c for c in self.calls if c[0] == "dual_clip"]
        self.assertEqual(len(dual_calls), 0, "original DualCLIPLoader not called")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Mismatch falls through to original loader
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotMismatchFallbackTests(unittest.TestCase):
    """When graph requests different identity, falls through to original."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="snap-mismatch", process="remote")
        self.bridge.use_ready_models(
            model_key=ModelRestoreKey(
                unet_identity="planned_unet.safetensors",
                clip_identity="planned_clip.safetensors",
                clip_type="sd3",
            ),
            prefill_key=PrefillKey(model_key=ModelRestoreKey(
                unet_identity="planned_unet.safetensors",
                clip_identity="planned_clip.safetensors",
                clip_type="sd3",
            )),
            model_spec=_make_snapshot_spec(
                unet_name="planned_unet.safetensors",
                clip_name="planned_clip.safetensors",
            ),
            unet=object(),
            clip=_FakeClip(),
            trace=self.trace,
        )

    def test_unet_mismatch_falls_through(self):
        """Different UNET name falls through to original loader."""
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "different.safetensors", "default"
            )
        self.assertEqual(result, ("original-unet:different.safetensors:default",))
        event_names = [e.name for e in self.trace.events]
        self.assertIn("identity_mismatch", event_names)
        self.assertIn("original_loader_fallback", event_names)

    def test_clip_mismatch_falls_through(self):
        """Different CLIP name falls through to original loader."""
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "different.safetensors", "sd3"
            )
        self.assertIsInstance(result[0], _FakeClip)
        event_names = [e.name for e in self.trace.events]
        self.assertIn("identity_mismatch", event_names)

    def test_clip_hit_when_identity_matches(self):
        """CLIP loader returns snapshot object when clip_name+type match planned."""
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "planned_clip.safetensors", "sd3"
            )
        self.assertIsInstance(result, tuple)
        event_names = [e.name for e in self.trace.events]
        self.assertIn("prepared_result_consumed", event_names)

    def test_no_snapshot_models_unloaded(self):
        """Snapshot objects remain available after mismatch fallback."""
        prep = self.bridge._preparation
        self.assertTrue(prep.unet_future.done())
        self.assertTrue(prep.clip_future.done())


# ═══════════════════════════════════════════════════════════════════════════
# 5. Prompt-only change rebinds with same objects
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotPromptOnlyRebindTests(unittest.TestCase):
    """Prompt-only changes re-call use_ready_models with same objects/new prefill."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="snap-prompt", process="remote")
        self.unet_obj = object()
        self.clip_obj = _FakeClip()
        self.model_key = ModelRestoreKey(
            unet_identity="u.safetensors",
            clip_identity="c.safetensors",
            clip_type="sd3",
        )
        self.model_spec = _make_snapshot_spec(unet_name="u.safetensors", clip_name="c.safetensors")

        # First activation with original prefill key
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key, prompt_bundle_hash="original_hash"),
            model_spec=self.model_spec,
            unet=self.unet_obj,
            clip=self.clip_obj,
            trace=self.trace,
        )

    def test_rebind_with_new_prefill_key(self):
        """Rebinding with same model_key but new prefill key updates bridge."""
        new_prefill_key = PrefillKey(
            model_key=self.model_key,
            prompt_bundle_hash="new_prompt_hash",
        )
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=new_prefill_key,
            model_spec=self.model_spec,
            unet=self.unet_obj,
            clip=self.clip_obj,
            trace=self.trace,
        )
        self.assertEqual(
            self.bridge._prefill_key.prompt_bundle_hash,
            "new_prompt_hash",
        )
        # Both futures must still point to the same objects
        prep = self.bridge._preparation
        self.assertIs(prep.unet_future.result(), self.unet_obj)
        self.assertIs(prep.clip_future.result(), self.clip_obj)

    def test_rebind_still_consumes_snapshot_objects(self):
        """After rebind, graph loaders return the snapshot objects."""
        new_prefill_key = PrefillKey(
            model_key=self.model_key,
            prompt_bundle_hash="rebind_hash",
        )
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=new_prefill_key,
            model_spec=self.model_spec,
            unet=self.unet_obj,
            clip=self.clip_obj,
            trace=self.trace,
        )
        with self.bridge.request_scope():
            unet_result = self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "u.safetensors", "default"
            )
            clip_result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "c.safetensors", "sd3"
            )
        self.assertIs(unet_result[0], self.unet_obj)
        self.assertIs(clip_result[0], self.clip_obj)

    def test_prefill_results_cleared_on_rebind(self):
        """Old prefill results are cleared when use_ready_models is called again."""
        # First set some prefill results
        with self.bridge._prefill_lock:
            self.bridge._prefill_results[(42, "hello")] = "old_result"
        # Rebind
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key, prompt_bundle_hash="new"),
            model_spec=self.model_spec,
            unet=self.unet_obj,
            clip=self.clip_obj,
            trace=self.trace,
        )
        with self.bridge._prefill_lock:
            self.assertNotIn((42, "hello"), self.bridge._prefill_results)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Model/spec mismatch clears bridge
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotModelMismatchClearTests(unittest.TestCase):
    """Model/spec mismatch clears bridge; original graph loaders run."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="snap-clear", process="remote")

    def test_unet_mismatch_detected_by_specs_match(self):
        """Different UNET filename causes projection mismatch."""
        snap_spec = _make_snapshot_spec(
            unet_name="snap_unet.safetensors",
            clip_name="c.safetensors",
        )
        request_spec = _make_snapshot_spec(
            unet_name="different_unet.safetensors",
            clip_name="c.safetensors",
        )
        self.assertFalse(
            _cpu_snapshot_specs_match(request_spec, snap_spec),
            "different UNET must not projection-match",
        )

    def test_weight_dtype_mismatch_clears(self):
        """Different weight_dtype causes projection mismatch."""
        snap_spec = _make_snapshot_spec(weight_dtype="fp16")
        request_spec = _make_snapshot_spec(weight_dtype="fp32")
        self.assertFalse(
            _cpu_snapshot_specs_match(request_spec, snap_spec),
            "different weight_dtype must not projection-match",
        )

    def test_clip_type_mismatch_clears(self):
        """Different CLIP type causes no projection match via model_key."""
        snap_key = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3")
        request_key = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sdxl")
        self.assertFalse(
            _cpu_snapshot_model_keys_match(request_key, snap_key),
            "different clip_type must not match",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. use_ready_models returns RestorePreparation
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotUseReadyModelsReturnTests(unittest.TestCase):
    """use_ready_models returns a proper RestorePreparation."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)

    def test_returns_restore_preparation(self):
        """use_ready_models returns a RestorePreparation instance."""
        prep = self.bridge.use_ready_models(
            model_key=ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3"),
            prefill_key=PrefillKey(),
            model_spec={"loaders": {"unet": [], "clip": [], "vae": []}},
            unet=object(),
            clip=_FakeClip(),
        )
        from comfymodal_runtime.model_preload import RestorePreparation
        self.assertIsInstance(prep, RestorePreparation)
        self.assertIsNotNone(prep.unet_future)
        self.assertIsNotNone(prep.clip_future)

    def test_coordinator_has_active_preparation(self):
        """Coordinator._active must be set so wait_* works without explicit prep."""
        self.bridge.use_ready_models(
            model_key=ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3"),
            prefill_key=PrefillKey(),
            model_spec={"loaders": {"unet": [], "clip": [], "vae": []}},
            unet=object(),
            clip=_FakeClip(),
        )
        self.assertIsNotNone(self.bridge.coordinator._active)
        self.assertIs(self.bridge.coordinator._active, self.bridge._preparation)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Bridge state after use_ready_models
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotBridgeStateTests(unittest.TestCase):
    """Bridge fields are correctly set after use_ready_models."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.model_key = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3")
        self.prefill_key = PrefillKey(model_key=self.model_key, prompt_bundle_hash="test_hash")
        self.model_spec = _make_snapshot_spec()
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=self.prefill_key,
            model_spec=self.model_spec,
            unet=object(),
            clip=_FakeClip(),
        )

    def test_model_key_set(self):
        """Bridge._model_key must match the supplied key."""
        self.assertEqual(self.bridge._model_key, self.model_key)

    def test_prefill_key_set(self):
        """Bridge._prefill_key must match the supplied key."""
        self.assertEqual(self.bridge._prefill_key.prompt_bundle_hash, "test_hash")

    def test_model_spec_set(self):
        """Bridge._model_spec must contain the loaders."""
        self.assertIn("loaders", self.bridge._model_spec)


# ═══════════════════════════════════════════════════════════════════════════
# 9. Retarget has no eager .to(cuda)
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotRetargetNoEagerCudaTests(unittest.TestCase):
    """retarget_cpu_snapshot_models sets device fields without transferring
    model weights or calling .to(cuda)."""

    def test_retarget_sets_fields_no_to(self):
        """retarget only sets load_device/offload_device, never calls .to()."""
        from comfymodal_runtime.cpu_snapshot_models import (
            retarget_cpu_snapshot_models,
            CpuSnapshotModels,
        )
        from comfymodal_runtime.contracts import ModelRestoreKey
        from types import SimpleNamespace

        unet_stub = SimpleNamespace()
        clip_stub = _FakeClip()

        def fake_mm():
            class _MM:
                @staticmethod
                def get_torch_device():
                    return "cuda:0"
                @staticmethod
                def unet_offload_device():
                    return "cpu"
                @staticmethod
                def text_encoder_device():
                    return "cuda:0"
                @staticmethod
                def text_encoder_offload_device():
                    return "cpu"
            return _MM

        models = CpuSnapshotModels(
            model_key=ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3"),
            model_spec={"loaders": {"unet": [], "clip": [], "vae": []}},
            normalized_profile={"mode": "split", "unet": "u", "clip1": "c", "clip_type": "sd3"},
            file_facts=(),
            unet=unet_stub,
            clip=clip_stub,
        )
        # Attach minimal patcher shape for validation
        unet_stub.load_device = "cpu"
        unet_stub.offload_device = "cpu"
        unet_stub.named_parameters = lambda recurse=True: iter([])
        unet_stub.named_buffers = lambda recurse=True: iter([])
        unet_stub.model = SimpleNamespace(
            named_parameters=lambda recurse=True: iter([]),
            named_buffers=lambda recurse=True: iter([]),
            diffusion_model=SimpleNamespace(
                named_parameters=lambda recurse=True: iter([]),
                named_buffers=lambda recurse=True: iter([]),
            ),
        )
        clip_stub.patcher = SimpleNamespace(load_device="cpu", offload_device="cpu")
        clip_stub.tokenizer = object()
        clip_stub.named_parameters = lambda recurse=True: iter([])
        clip_stub.named_buffers = lambda recurse=True: iter([])
        clip_stub.cond_stage_model = SimpleNamespace(
            named_parameters=lambda recurse=True: iter([]),
            named_buffers=lambda recurse=True: iter([]),
        )

        mm = fake_mm()
        ok, reason = retarget_cpu_snapshot_models(models, model_management=mm)
        self.assertTrue(ok, reason)
        # Verify devices were set
        self.assertEqual(unet_stub.load_device, "cuda:0")
        self.assertEqual(unet_stub.offload_device, "cpu")
        self.assertEqual(clip_stub.patcher.load_device, "cuda:0")
        self.assertEqual(clip_stub.patcher.offload_device, "cpu")
        # Verify .to was NOT called (no to attribute on SimpleNamespace)
        self.assertFalse(hasattr(unet_stub, "to"),
                         "retarget must not call .to() on model objects")


# ═══════════════════════════════════════════════════════════════════════════
# 10. Clear resets _preparation and coordinator._active
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotClearResetsTests(unittest.TestCase):
    """clear() resets bridge state and coordinator._active."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.bridge.use_ready_models(
            model_key=ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3"),
            prefill_key=PrefillKey(),
            model_spec={"loaders": {"unet": [], "clip": [], "vae": []}},
            unet=object(),
            clip=_FakeClip(),
        )
        self.assertIsNotNone(self.bridge.coordinator._active)

    def test_clear_resets_preparation(self):
        """clear() sets _preparation to None."""
        self.bridge.clear()
        self.assertIsNone(self.bridge._preparation)

    def test_clear_resets_coordinator_active(self):
        """clear() sets coordinator._active to None."""
        self.bridge.clear()
        self.assertIsNone(self.bridge.coordinator._active)

    def test_clear_preserves_other_coordinator_state(self):
        """clear() only sets coordinator._active = None; does not close pool or mutate callers."""
        # Check coordinator is still usable after clear
        self.bridge.clear()
        self.assertIsNone(self.bridge.coordinator._active)
        # A subsequent use_ready_models should work
        self.bridge.use_ready_models(
            model_key=ModelRestoreKey(unet_identity="u2", clip_identity="c2", clip_type="sd3"),
            prefill_key=PrefillKey(),
            model_spec={"loaders": {"unet": [], "clip": [], "vae": []}},
            unet=object(),
            clip=_FakeClip(),
        )
        self.assertIsNotNone(self.bridge.coordinator._active)

    def test_clear_subsequent_use_falls_through(self):
        """After clear(), wrapped loader falls through to original in request_scope."""
        self.bridge.clear()
        self.assertIsNone(self.bridge._preparation)
        self.assertIsNone(self.bridge.coordinator._active)
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "c.safetensors", "sd3"
            )
        self.assertIsInstance(result[0], _FakeClip)
        clip_calls = [c for c in self.calls if c[0] == "clip"]
        self.assertEqual(len(clip_calls), 1,
                         "original loader must be called after clear")


# ═══════════════════════════════════════════════════════════════════════════
# 11. VAE original path preserved
# ═══════════════════════════════════════════════════════════════════════════


class SnapshotVAEPathPreservedTests(unittest.TestCase):
    """VAE remains on original graph-loading path; not affected by snapshot."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="snap-vae", process="remote")
        self.bridge.use_ready_models(
            model_key=ModelRestoreKey(
                unet_identity="u.safetensors",
                clip_identity="c.safetensors",
                vae_identity="ae.safetensors",
                clip_type="sd3",
            ),
            prefill_key=PrefillKey(model_key=ModelRestoreKey(
                unet_identity="u.safetensors",
                clip_identity="c.safetensors",
                clip_type="sd3",
            )),
            model_spec=_make_snapshot_spec(unet_name="u.safetensors", clip_name="c.safetensors"),
            unet=object(),
            clip=_FakeClip(),
            trace=self.trace,
        )

    def test_vae_goes_to_original_loader(self):
        """VAE graph call falls through to original loader."""
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["VAELoader"]().load_vae(
                "ae.safetensors"
            )
        self.assertEqual(result, ("vae:ae.safetensors",))
        vae_calls = [c for c in self.calls if c[0] == "vae"]
        self.assertEqual(len(vae_calls), 1)
        event_names = [e.name for e in self.trace.events]
        self.assertIn("original_loader_fallback", event_names)

    def test_vae_mismatch_still_original(self):
        """Different VAE name still goes to original loader (no snapshot VAE)."""
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["VAELoader"]().load_vae(
                "different_vae.safetensors"
            )
        self.assertEqual(result, ("vae:different_vae.safetensors",))




# 12. use_ready_clip — clip-only snapshot (no UNET future)


class SnapshotUseReadyClipTests(unittest.TestCase):
    """use_ready_clip — clip-only bridge preparation with no snapshot UNET."""

    def setUp(self):
        self.calls: list[tuple] = []
        self.nodes = _fake_nodes(self.calls)
        self.bridge = V2LoaderBridge()
        self.bridge.install(self.nodes)
        self.trace = RuntimeTrace(request_id="use_ready_clip", process="remote")
        self.clip_obj = _FakeClip()
        self.model_key = ModelRestoreKey(
            unet_identity="u.safetensors",
            clip_identity="c.safetensors",
            clip_type="sd3",
        )
        self.prefill_key = PrefillKey(
            model_key=self.model_key,
            prompt_bundle_hash="clip-only-test",
        )
        self.model_spec = _make_snapshot_spec()

    def _activate(self):
        return self.bridge.use_ready_clip(
            model_key=self.model_key,
            prefill_key=self.prefill_key,
            model_spec=self.model_spec,
            clip=self.clip_obj,
            trace=self.trace,
        )

    def test_use_ready_clip_returns_restore_preparation(self):
        """use_ready_clip returns a RestorePreparation instance."""
        prep = self._activate()
        from comfymodal_runtime.model_preload import RestorePreparation
        self.assertIsInstance(prep, RestorePreparation)

    def test_clip_future_is_completed(self):
        """clip_future is done and holds the exact clip object."""
        prep = self._activate()
        self.assertIsNotNone(prep.clip_future)
        self.assertTrue(prep.clip_future.done())
        self.assertIs(prep.clip_future.result(), self.clip_obj)

    def test_unet_future_is_none(self):
        """unet_future is None (no snapshot UNET)."""
        prep = self._activate()
        self.assertIsNone(prep.unet_future,
                          "use_ready_clip must NOT set unet_future")

    def test_preparation_has_no_unet_diagnostics(self):
        """UNET diagnostics are zero (no snapshot UNET)."""
        prep = self._activate()
        self.assertEqual(prep.diagnostics.unet_started_at, 0.0)
        self.assertEqual(prep.diagnostics.unet_completed_at, 0.0)

    def test_clip_object_identity_preserved(self):
        """Clip future returns the exact same clip object reference."""
        prep = self._activate()
        self.assertIs(prep.clip_future.result(), self.clip_obj)

    def test_clip_graph_hit_returns_snapshot(self):
        """CLIP graph loader returns the snapshot CLIP on hit."""
        self._activate()
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "c.safetensors", "sd3"
            )
        self.assertIs(result[0], self.clip_obj)

    def test_unet_graph_falls_through_to_original(self):
        """UNET graph loader falls through to original (no snapshot UNET)."""
        self._activate()
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "u.safetensors", "default"
            )
        self.assertEqual(result, ("original-unet:u.safetensors:default",))

    def test_unet_falls_through_triggers_future_unavailable(self):
        """UNET graph call emits future_unavailable and original_loader_fallback
        (no snapshot UNET future = no identity comparison)."""
        self._activate()
        with self.bridge.request_scope():
            self.nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(
                "u.safetensors", "default"
            )
        event_names = [e.name for e in self.trace.events]
        self.assertIn("future_unavailable", event_names)
        self.assertIn("original_loader_fallback", event_names)

    def test_clip_hit_emits_prepared_result_consumed(self):
        """CLIP hit emits prepared_result_consumed terminal event."""
        self._activate()
        with self.bridge.request_scope():
            self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "c.safetensors", "sd3"
            )
        event_names = [e.name for e in self.trace.events]
        self.assertIn("prepared_result_consumed", event_names)
        terminal = [
            e for e in self.trace.events
            if e.name == "prepared_result_consumed"
        ]
        self.assertEqual(len(terminal), 1)
        self.assertEqual(terminal[0].metadata.get("terminal_outcome"), "prepared")

    def test_rebind_with_new_prefill_key(self):
        """Rebind updates prefill_key while keeping same clip."""
        new_prefill_key = PrefillKey(
            model_key=self.model_key,
            prompt_bundle_hash="rebind_hash",
        )
        self.bridge.use_ready_clip(
            model_key=self.model_key,
            prefill_key=new_prefill_key,
            model_spec=self.model_spec,
            clip=self.clip_obj,
            trace=self.trace,
        )
        self.assertEqual(
            self.bridge._prefill_key.prompt_bundle_hash,
            "rebind_hash",
        )
        self.assertIs(
            self.bridge._preparation.clip_future.result(), self.clip_obj,
        )

    def test_coordinator_active_after_use_ready_clip(self):
        """coordinator._active is set so wait_clip works."""
        self._activate()
        self.assertIsNotNone(self.bridge.coordinator._active)
        self.assertIs(self.bridge.coordinator._active, self.bridge._preparation)

    def test_extend_preparation_adds_unet_after_clip_only(self):
        """After use_ready_clip, extend_preparation(prepare_unet=True) submits UNET."""
        self._activate()
        self.assertIsNone(self.bridge._preparation.unet_future)
        # Extend with UNET
        self.bridge.extend_preparation(
            prepare_unet=True, prepare_vae=False, trace=self.trace,
        )
        prep = self.bridge._preparation
        self.assertIsNotNone(prep.unet_future)
        # UNET future should be submitted to thread pool, may or may not be done
        # Just verify it exists and is a Future
        from concurrent.futures import Future
        self.assertIsInstance(prep.unet_future, Future)
        # VAE must remain None (prepare_vae=False)
        self.assertIsNone(prep.vae_future)

    def test_extend_preparation_keeps_clip_future(self):
        """After use_ready_clip + extend, existing clip future remains intact."""
        self._activate()
        self.bridge.extend_preparation(
            prepare_unet=True, prepare_vae=False, trace=self.trace,
        )
        prep = self.bridge._preparation
        self.assertTrue(prep.clip_future.done())
        self.assertIs(prep.clip_future.result(), self.clip_obj)

    def test_clear_after_use_ready_clip(self):
        """clear() resets state after use_ready_clip."""
        self._activate()
        self.bridge.clear()
        self.assertIsNone(self.bridge._preparation)
        self.assertIsNone(self.bridge.coordinator._active)

    def test_use_ready_clip_with_missing(self):
        """CLIP identity mismatch falls through to original loader."""
        self._activate()
        with self.bridge.request_scope():
            result = self.nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                "different.safetensors", "sd3"
            )
        self.assertIsInstance(result[0], _FakeClip)
        clip_calls = [c for c in self.calls if c[0] == "clip"]
        self.assertEqual(len(clip_calls), 1,
                         "original CLIP loader must be called on mismatch")


if __name__ == "__main__":
    unittest.main()
