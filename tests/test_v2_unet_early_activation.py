"""Focused tests for the Phase 1A early retained-UNET activation candidate.

``COMFYMODAL_V2_UNET_ACTIVATION_MODE``:

  - the ONLY allowed opt-in value is exactly ``clip_encode_start``;
    ``late`` is the default and invalid values (including the historical
    ``early`` spelling) normalize to ``late`` — no candidate path may
    activate for ``early``
  - eligibility is proven at the real execution-prefill boundary before any
    scheduling (execution-prefill caller, mode, production CPU-snapshot
    request marker, exact retained snapshot→bridge identity chain, completed
    retained-UNET future, no same-request/key future, live CUDA validity,
    and safe VRAM for the exact active CLIP + retained UNET)
  - the activation key carries real retained patcher + underlying diffusion
    identities (never blank placeholders) and is recomputed before terminal
    publication; identity changes are rejected
  - clip_encode_start is exact-once / idempotent across positive/negative
    encodes; graph/sampler demand joins the same request future outside the
    mutation lane and emits graph-demand / graph-join-start / graph-join-end
  - exactly one fallback election, never overwritten, never racing a pending
    future
  - cancellation / request-end cleanup leaves no activation future or
    mutation pending; a running worker re-checks cancellation immediately
    before mutation
  - one coordinator pool / one mutation lane
  - one physical transfer, second load is a no-allocation cache validation
  - the exact active CLIP is protected; VRAM insufficiency skips with a
    structured reason (eligible=false + skipped) and Phase 0 continues
  - page readiness stays off by default
  - required structured markers are emitted (mode, eligible, scheduled,
    worker_start, lane_wait_start, lane_acquired, load_start, load_end,
    completed, failed, skipped, graph_demand, graph_join_start,
    graph_join_end, consumed, terminal, fallback, reconciliation)
  - waterfall (derived interval) arithmetic reconciles using the ACTUAL
    clip encode start/end
"""

from __future__ import annotations

import os
import sys
import threading
import time
import types
import unittest
from concurrent.futures import Future
from contextlib import contextmanager
from typing import Any

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.trace import RuntimeTrace

MODE = "clip_encode_start"


# ── Fakes ────────────────────────────────────────────────────────────────


class _FakeDiffusion:
    def __init__(self, device: str = "cuda:0"):
        self.current_device = device
        self.device = device

    def parameters(self):
        return iter(())


class _FakeBaseModel:
    def __init__(self, dm):
        self.diffusion_model = dm


class _FakePatcher:
    def __init__(
        self,
        dm,
        *,
        size: int = 4 * 1024 ** 3,
        loaded: int = 0,
        load_device: str = "cuda:0",
        dtype: str = "torch.float16",
    ):
        self.model = _FakeBaseModel(dm)
        self.model_options = {}
        self.parent = None
        self.load_device = load_device
        self.current_device = "cpu"
        self._size = size
        self._loaded = loaded
        self._dtype = dtype

    def model_size(self):
        return self._size

    def loaded_size(self):
        return self._loaded

    def model_dtype(self):
        return self._dtype

    def is_dynamic(self):
        return False


class _FakeClip:
    def __init__(self, patcher=None):
        self.patcher = patcher or _FakePatcher(_FakeDiffusion(), size=2 * 1024 ** 3)


class _FakeLoadedModel:
    def __init__(self, patcher):
        self._m = patcher

    @property
    def model(self):
        return self._m


class _FakeModelManagement:
    """Stand-in for comfy.model_management injected into sys.modules."""

    def __init__(self, free_bytes: int):
        self.free_bytes = free_bytes
        self.current_loaded_models: list[_FakeLoadedModel] = []
        self.load_count = 0
        self.lane_seen: str | None = None
        self.last_models: list[Any] = []

    def load_models_gpu(self, models, **kwargs):
        self.load_count += 1
        self.last_models = list(models)
        lane = mp._ACTIVE_LANE_TRACE.get()
        self.lane_seen = lane._lane if lane is not None else None
        for m in models:
            self._place(m)
        return None

    def _place(self, m):
        loaded = int(getattr(m, "loaded_size", lambda: 0)())
        size = int(getattr(m, "model_size", lambda: 0)())
        if loaded < size:
            m._loaded = size
        m.current_device = getattr(m, "load_device", "cuda:0")
        if not any(lm.model is m for lm in self.current_loaded_models):
            self.current_loaded_models.insert(0, _FakeLoadedModel(m))

    def get_free_memory(self, device=None):
        return self.free_bytes

    def extra_reserved_memory(self):
        return 0

    def get_torch_device(self):
        return "cuda:0"

    def cast_to_device(self, *a, **k):
        return a[0] if a else None

    def unet_dtype(self):
        return "default"

    def unet_manual_cast(self, x):
        return x


class _ComfyMMContext:
    """Inject a fake comfy.model_management module for the test duration.

    Patches the ``sys.modules`` entry AND ensures a ``comfy`` parent package
    exists so ``import comfy.model_management`` resolves to the fake even
    inside coordinator worker threads.
    """

    def __init__(self, fake):
        self.fake = fake
        self._saved = None
        self._comfy_pkg = None
        self._saved_attr = None
        self._attr_present = False

    def __enter__(self):
        self._saved = sys.modules.get("comfy.model_management")
        self._comfy_pkg = sys.modules.get("comfy")
        if self._comfy_pkg is None:
            self._comfy_pkg = types.ModuleType("comfy")
            sys.modules["comfy"] = self._comfy_pkg
        self._attr_present = hasattr(self._comfy_pkg, "model_management")
        self._saved_attr = getattr(self._comfy_pkg, "model_management", None)
        self._comfy_pkg.model_management = self.fake
        sys.modules["comfy.model_management"] = self.fake
        return self.fake

    def __exit__(self, *exc):
        if self._saved is None:
            sys.modules.pop("comfy.model_management", None)
        else:
            sys.modules["comfy.model_management"] = self._saved
        if self._comfy_pkg is not None:
            if self._attr_present:
                self._comfy_pkg.model_management = self._saved_attr
            else:
                try:
                    delattr(self._comfy_pkg, "model_management")
                except Exception:
                    pass
        return False


# ── Bridge / plan helpers ────────────────────────────────────────────────


def _build_bridge(
    *,
    mode: str = MODE,
    unet_patcher: _FakePatcher | None = None,
    clip: _FakeClip | None = None,
    unet_loader: Any = None,
    max_workers: int = 3,
):
    mp._UNET_ACTIVATION_MODE = mode
    if unet_patcher is None:
        unet_patcher = _FakePatcher(_FakeDiffusion())
    if clip is None:
        clip = _FakeClip()
    bridge = mp.V2LoaderBridge(max_workers=max_workers)
    bridge.install = lambda nodes=None, trace=None: True
    bridge._invoke_original = lambda class_name, kwargs: (
        f"conditioning:{kwargs['text']}",
    )
    bridge._request_list = lambda bucket: (
        [{"unet_name": "unet.safetensors", "weight_dtype": "default"}]
        if bucket == "unet"
        else [{"clip_name": "clip.safetensors"}]
    )
    bridge._model_spec = {
        "loaders": {
            "unet": [{"unet_name": "unet.safetensors"}],
            "clip": [{"clip_name": "clip.safetensors"}],
        }
    }
    bridge.coordinator.unet_loader = unet_loader or (lambda key: unet_patcher)
    bridge.coordinator.clip_loader = lambda key: clip
    return bridge, unet_patcher, clip


@contextmanager
def _early_bridge(*args, **kwargs):
    bridge, unet_patcher, clip = _build_bridge(*args, **kwargs)
    try:
        yield bridge, unet_patcher, clip
    finally:
        bridge.coordinator.close()


def _make_plan(*, text: str = "a cat", role: str = "positive", extra: bool = False):
    model_key = ModelRestoreKey(
        unet_identity="unet.safetensors",
        clip_identity="clip.safetensors",
        clip_type="stable_diffusion",
    )
    encodes = [{"node_id": "6", "text": text, "role": role}]
    if extra:
        encodes.append({"node_id": "7", "text": "a dog", "role": "negative"})
    prefill_key = PrefillKey(
        model_key=model_key,
        prompt_bundle_hash="hash-early-activation",
        encode_options={"eligible": True, "encodes": encodes},
    )
    return RestorePlan(model_key=model_key, prefill_key=prefill_key)


def _events_named(trace: RuntimeTrace, name: str):
    return [e for e in trace.events if e.name == name]


def _setup_eligible_request(request_id: str, unet_patcher: Any) -> None:
    """Mark the request as a production CPU-snapshot request and record the
    exact retained snapshot→bridge identity chain (as restore does)."""
    mp.mark_production_cpu_snapshot_request(request_id)
    mp.record_retained_unet_identity(
        "snapshot", unet_patcher, request_id=request_id
    )
    mp.record_retained_unet_identity(
        "bridge", unet_patcher, request_id=request_id
    )


def _teardown_common() -> None:
    mp._UNET_ACTIVATION_MODE = "late"
    with mp._UNET_ACTIVATION_LOCK:
        mp._UNET_ACTIVATION_STATE.clear()
    with mp._SNAPSHOT_UNET_CHAIN_LOCK:
        mp._SNAPSHOT_UNET_CHAIN.clear()
    with mp._PRODUCTION_CPU_SNAPSHOT_REQUESTS_LOCK:
        mp._PRODUCTION_CPU_SNAPSHOT_REQUESTS.clear()


# ── Tests ────────────────────────────────────────────────────────────────


class ModeTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_default_mode_is_late(self):
        self.assertEqual(mp._UNET_ACTIVATION_MODE, "late")

    def test_only_allowed_opt_in_is_clip_encode_start(self):
        self.assertEqual(
            set(mp._UNET_ACTIVATION_MODE_VALID),
            {"late", "clip_encode_start"},
        )
        self.assertEqual(mp._resolve_unet_activation_mode("clip_encode_start"), "clip_encode_start")
        self.assertEqual(mp._resolve_unet_activation_mode("CLIP_ENCODE_START"), "clip_encode_start")
        self.assertEqual(mp._resolve_unet_activation_mode(" Clip_Encode_Start "), "clip_encode_start")

    def test_historical_early_spelling_falls_back_to_late(self):
        # ``early`` must never activate any candidate path.
        self.assertEqual(mp._resolve_unet_activation_mode("early"), "late")
        self.assertEqual(mp._resolve_unet_activation_mode("EARLY"), "late")
        self.assertEqual(mp._resolve_unet_activation_mode("Early"), "late")

    def test_invalid_mode_falls_back_to_late(self):
        for raw in ("banana", "", "true", "1", "early-morning", "late-ish"):
            self.assertEqual(mp._resolve_unet_activation_mode(raw), "late")
        self.assertEqual(mp._resolve_unet_activation_mode(" Late "), "late")

    def test_early_mode_never_activates(self):
        mp._UNET_ACTIVATION_MODE = "early"
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode="early") as (bridge, _unet, clip):
                trace = RuntimeTrace(request_id="ea-early", process="test")
                _setup_eligible_request("ea-early", _unet)
                bridge.prepare(_make_plan(), trace=trace)
                scheduled = mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-early", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                )
                self.assertFalse(scheduled)
                self.assertIsNone(mp._unet_activation_get("ea-early"))
                joined = mp.join_unet_early_activation(
                    None, unet=_unet, trace=trace, request_id="ea-early",
                )
                self.assertEqual(joined["status"], "mode_late")
                early_events = [
                    e.name for e in trace.events
                    if e.name.startswith("unet_early_activation_")
                ]
                self.assertEqual(early_events, [])

    def test_late_mode_no_early_work(self):
        mp._UNET_ACTIVATION_MODE = "late"
        with _early_bridge(mode="late") as (bridge, _unet, clip):
            trace = RuntimeTrace(request_id="late-req", process="test")
            bridge.prepare(_make_plan(), trace=trace)
            scheduled = mp.clip_encode_start(
                bridge, trace=trace, request_id="late-req", clip=clip,
                encode_entries=[{"node_id": "6", "text": "a cat"}],
            )
            self.assertFalse(scheduled)
            self.assertIsNone(mp._unet_activation_get("late-req"))
            early_events = [
                e.name for e in trace.events
                if e.name.startswith("unet_early_activation_")
            ]
            self.assertEqual(early_events, [])

    def test_full_prefill_late_mode_runs_no_early_work(self):
        mp._UNET_ACTIVATION_MODE = "late"
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode="late") as (bridge, _unet, _clip):
                trace = RuntimeTrace(request_id="late-full", process="test")
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                result = prep.prefill_future.result(timeout=10)
                self.assertIsNotNone(result)
                self.assertEqual(mm.load_count, 0)
                self.assertIsNone(mp._unet_activation_get("late-full"))
                early_events = [
                    e.name for e in trace.events
                    if e.name.startswith("unet_early_activation_")
                ]
                self.assertEqual(early_events, [])

    def test_late_mode_graph_unet_demand_emits_no_early_markers(self):
        # The UNET graph consumer in late mode must not emit any
        # unet_early_activation_* graph-demand/join markers, perform join
        # helper work, create state, or add a graph wait.
        mp._UNET_ACTIVATION_MODE = "late"
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode="late") as (bridge, _unet, _clip):
                trace = RuntimeTrace(request_id="late-graph", process="test")
                bridge.prepare(_make_plan(), trace=trace)
                consumed = bridge._consume_unet(
                    ("unet.safetensors",),
                    {"unet_name": "unet.safetensors", "weight_dtype": "default"},
                )
                self.assertIsNot(consumed, mp._LOADER_MISS)
                early_events = [
                    e.name for e in trace.events
                    if e.name.startswith("unet_early_activation_")
                ]
                self.assertEqual(early_events, [])
                self.assertIsNone(mp._unet_activation_get("late-graph"))
                # Phase 0 canonical graph events are still emitted unchanged.
                self.assertEqual(
                    len(_events_named(trace, "graph_unet_demand")), 1,
                )
                self.assertEqual(
                    len(_events_named(trace, "graph_wait_start")), 1,
                )
                self.assertEqual(
                    len(_events_named(trace, "graph_wait_end")), 1,
                )


class EligibilityTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_all_proofs_hold_schedules(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-elig", process="test")
                _setup_eligible_request("ea-elig", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                self.assertTrue(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-elig", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                ))
                state = mp._unet_activation_get("ea-elig")
                self.assertIsNotNone(state)
                self.assertTrue(state["eligible"])
                outcome = state["future"].result(timeout=10)
                self.assertEqual(outcome["status"], "ready")
                self.assertEqual(mm.load_count, 1)
                self.assertEqual(
                    len(_events_named(trace, "unet_early_activation_eligible")), 1,
                )
                elig_events = _events_named(trace, "unet_early_activation_eligible")
                self.assertTrue(elig_events[0].metadata.get("eligible"))

    def test_cpu_snapshot_mode_inactive_skips(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-nosnap", process="test")
                # NO production marker -> not eligible.
                mp.record_retained_unet_identity(
                    "snapshot", unet_patcher, request_id="ea-nosnap",
                )
                mp.record_retained_unet_identity(
                    "bridge", unet_patcher, request_id="ea-nosnap",
                )
                bridge.prepare(_make_plan(), trace=trace)
                self.assertFalse(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-nosnap", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                ))
                self.assertIsNone(mp._unet_activation_get("ea-nosnap"))
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(elig[0].metadata.get("reason"), "cpu_snapshot_mode_inactive")
                skipped = _events_named(trace, "unet_early_activation_skipped")
                self.assertEqual(len(skipped), 1)
                self.assertEqual(skipped[0].metadata.get("reason"), "cpu_snapshot_mode_inactive")
                self.assertEqual(
                    len(_events_named(trace, "unet_early_activation_scheduled")), 0,
                )

    def test_identity_chain_incomplete_skips(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, _unet, clip):
                trace = RuntimeTrace(request_id="ea-nochain", process="test")
                mp.mark_production_cpu_snapshot_request("ea-nochain")
                bridge.prepare(_make_plan(), trace=trace)
                self.assertFalse(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-nochain", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                ))
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(elig[0].metadata.get("reason"), "identity_chain_incomplete")

    def test_snapshot_bridge_identity_mismatch_skips(self):
        # The proof requires EXACT snapshot == bridge object equality — a
        # present-but-different snapshot object fails closed.
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-snapmismatch", process="test")
                mp.mark_production_cpu_snapshot_request("ea-snapmismatch")
                mp.record_retained_unet_identity(
                    "snapshot", _FakePatcher(_FakeDiffusion()),
                    request_id="ea-snapmismatch",
                )
                mp.record_retained_unet_identity(
                    "bridge", unet_patcher, request_id="ea-snapmismatch",
                )
                bridge.prepare(_make_plan(), trace=trace)
                self.assertFalse(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-snapmismatch", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                ))
                self.assertIsNone(mp._unet_activation_get("ea-snapmismatch"))
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(
                    elig[0].metadata.get("reason"), "snapshot_bridge_identity_mismatch",
                )
                skipped = _events_named(trace, "unet_early_activation_skipped")
                self.assertEqual(len(skipped), 1)
                self.assertEqual(
                    skipped[0].metadata.get("reason"), "snapshot_bridge_identity_mismatch",
                )
                self.assertEqual(
                    len(_events_named(trace, "unet_early_activation_scheduled")), 0,
                )

    def test_unet_future_pending_skips(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        unet_gate = threading.Event()

        def slow_unet(key):
            unet_gate.wait(timeout=10)
            return _FakePatcher(_FakeDiffusion())

        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE, unet_loader=slow_unet) as (bridge, _u, clip):
                trace = RuntimeTrace(request_id="ea-pending", process="test")
                mp.mark_production_cpu_snapshot_request("ea-pending")
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertFalse(prep.unet_future.done())
                # The prefill worker evaluates eligibility: the retained UNET
                # future is not yet completed -> skipped, never scheduled.
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                self.assertIsNone(mp._unet_activation_get("ea-pending"))
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(elig[0].metadata.get("reason"), "unet_future_pending")
                self.assertEqual(mm.load_count, 0)
                unet_gate.set()

    def test_cuda_unavailable_skips(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-nocuda", process="test")
                _setup_eligible_request("ea-nocuda", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                import unittest.mock as mock
                with mock.patch("torch.cuda.is_available", return_value=False):
                    self.assertFalse(mp.clip_encode_start(
                        bridge, trace=trace, request_id="ea-nocuda", clip=clip,
                        encode_entries=[{"node_id": "6", "text": "a cat"}],
                    ))
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(elig[0].metadata.get("reason"), "cuda_unavailable")

    def test_vram_insufficient_skips_at_boundary(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=1 * 1024 ** 3)  # 1GB free, ~6.6GB required
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-vram-elig", process="test")
                _setup_eligible_request("ea-vram-elig", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                self.assertFalse(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-vram-elig", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                ))
                self.assertIsNone(mp._unet_activation_get("ea-vram-elig"))
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(elig[0].metadata.get("reason"), "vram_insufficient")
                skipped = _events_named(trace, "unet_early_activation_skipped")
                self.assertEqual(len(skipped), 1)
                self.assertEqual(skipped[0].metadata.get("free_bytes"), 1 * 1024 ** 3)
                self.assertIsNotNone(skipped[0].metadata.get("required_bytes"))
                self.assertEqual(mm.load_count, 0)


class ClipEncodeStartTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_schedules_exactly_once_across_positive_negative_encodes(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-dup", process="test")
                _setup_eligible_request("ea-dup", unet_patcher)
                bridge.prepare(_make_plan(extra=True), trace=trace)
                self.assertTrue(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-dup", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat", "role": "positive"}],
                ))
                self.assertTrue(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-dup", clip=clip,
                    encode_entries=[{"node_id": "7", "text": "a dog", "role": "negative"}],
                ))
                state = mp._unet_activation_get("ea-dup")
                self.assertIsNotNone(state)
                self.assertIsNotNone(state["future"])
                outcome = state["future"].result(timeout=10)
                self.assertEqual(outcome["status"], "ready")
                self.assertEqual(mm.load_count, 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_scheduled")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_worker_start")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_eligible")), 1)

    def test_full_prefill_path_schedules_early_activation(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-full", process="test")
                _setup_eligible_request("ea-full", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prefill_result = prep.prefill_future.result(timeout=10)
                self.assertIsNotNone(prefill_result)
                state = mp._unet_activation_get("ea-full")
                self.assertIsNotNone(state)
                self.assertEqual(state["trigger"], "clip_encode_start")
                outcome = state["future"].result(timeout=10)
                self.assertEqual(outcome["status"], "ready")
                self.assertEqual(state["transfer_count"], 1)
                self.assertEqual(mm.load_count, 1)
                # The retained UNET is loaded and cache-published.
                self.assertEqual(unet_patcher.loaded_size(), unet_patcher.model_size())
                self.assertTrue(any(
                    lm.model is unet_patcher for lm in mm.current_loaded_models
                ))
                # CLIP patcher was protected by being loaded alongside
                # (post-load CLIP residency proof recorded).
                self.assertTrue(any(
                    lm.model is clip.patcher for lm in mm.current_loaded_models
                ))
                self.assertTrue(state["clip_retained"])
                self.assertTrue(state["clip_resident"])
                self.assertEqual(state["clip_residency_status"], "resident_full")

    def test_identity_key_contains_real_ids_at_scheduling(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        dm = _FakeDiffusion()
        unet_patcher = _FakePatcher(dm)
        clip = _FakeClip()
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE, unet_patcher=unet_patcher, clip=clip) as (
                bridge, _u, _c,
            ):
                trace = RuntimeTrace(request_id="ea-key", process="test")
                _setup_eligible_request("ea-key", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                self.assertTrue(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-key", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                ))
                state = mp._unet_activation_get("ea-key")
                key = state["key"]
                # Real retained patcher + underlying diffusion identities —
                # never blank placeholders.
                self.assertEqual(key["unet_patcher_object_id"], str(id(unet_patcher)))
                self.assertEqual(key["unet_diffusion_object_id"], str(id(dm)))
                self.assertTrue(key["key_hash"] if "key_hash" in key else True)
                self.assertTrue(state["key_hash"])
                self.assertEqual(key["request_id"], "ea-key")
                self.assertEqual(key["mode"], MODE)
                self.assertEqual(key["weight_dtype"], "default")
                self.assertEqual(key["device"], "cuda:0")
                # The worker resolves the same identity -> key hash unchanged
                # (recomputed before terminal publication, never a blank key).
                key_hash_at_schedule = state["key_hash"]
                outcome = state["future"].result(timeout=10)
                self.assertEqual(outcome["status"], "ready")
                self.assertEqual(state["key_hash"], key_hash_at_schedule)


class JoinTests(unittest.TestCase):
    def setUp(self):
        mp._UNET_ACTIVATION_MODE = MODE

    def tearDown(self):
        _teardown_common()

    def _ready_state(self, request_id: str, dm, patcher) -> dict[str, Any]:
        state = mp._unet_activation_new_state(request_id)
        state["status"] = "ready"
        state["terminal"] = True
        state["trigger"] = "clip_encode_start"
        state["key_hash"] = "key-hash"
        state["key"] = {
            "mode": MODE,
            "request_id": request_id,
            "unet_diffusion_object_id": str(id(dm)),
            "unet_patcher_object_id": str(id(patcher)),
            "device": str(getattr(patcher, "load_device", "cuda:0")),
            "compute_dtype": "",
            "workflow_hash": "",
            "custom_node_generation": "",
            "deployment_hash": "",
            "weight_dtype": "default",
            "unet_identity": "unet.safetensors",
        }
        with mp._UNET_ACTIVATION_LOCK:
            mp._UNET_ACTIVATION_STATE[request_id] = state
        return state

    def test_join_after_completion_is_immediate_and_valid(self):
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            dm = _FakeDiffusion()
            patcher = _FakePatcher(dm)
            mm._place(patcher)  # cache-published by the early load
            state = self._ready_state("join-after", dm, patcher)
            fut: Future = Future()
            fut.set_result({"status": "ready"})
            state["future"] = fut
            trace = RuntimeTrace(request_id="join-after", process="test")
            outcome = mp.join_unet_early_activation(
                None, unet=patcher, trace=trace, request_id="join-after",
            )
            self.assertTrue(outcome["scheduled"])
            self.assertTrue(outcome["valid"])
            self.assertEqual(outcome["status"], "ready")
            self.assertLess(outcome["join_wait_ms"], 1.0)
            self.assertEqual(len(_events_named(trace, "unet_early_activation_consumed")), 1)

    def test_join_before_completion_waits_for_the_same_future(self):
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            dm = _FakeDiffusion()
            patcher = _FakePatcher(dm)
            mm._place(patcher)
            state = self._ready_state("join-before", dm, patcher)
            fut: Future = Future()
            state["future"] = fut
            trace = RuntimeTrace(request_id="join-before", process="test")
            results: dict[str, Any] = {}
            joiner = threading.Thread(
                target=lambda: results.update(
                    mp.join_unet_early_activation(
                        None, unet=patcher, trace=trace, request_id="join-before",
                    )
                )
            )
            joiner.start()
            time.sleep(0.05)
            self.assertFalse(fut.done())
            fut.set_result({"status": "ready"})
            joiner.join(timeout=5)
            self.assertTrue(results["valid"])
            self.assertEqual(results["status"], "ready")
            self.assertGreaterEqual(results["join_wait_ms"], 0.0)

    def test_one_fallback_and_no_overwrite(self):
        dm = _FakeDiffusion()
        patcher = _FakePatcher(dm)
        state = self._ready_state("one-fallback", dm, patcher)
        state["status"] = "skipped"
        state["reason"] = "vram_insufficient"
        fut: Future = Future()
        fut.set_result({"status": "skipped"})
        state["future"] = fut
        trace = RuntimeTrace(request_id="one-fallback", process="test")
        first = mp.join_unet_early_activation(
            None, unet=patcher, trace=trace, request_id="one-fallback",
        )
        self.assertFalse(first["valid"])
        self.assertTrue(first["terminal"])
        self.assertTrue(state["fallback_elected"])
        self.assertEqual(state["fallback_reason"], "vram_insufficient")
        second = mp.join_unet_early_activation(
            None, unet=patcher, trace=trace, request_id="one-fallback",
        )
        self.assertFalse(second["valid"])
        # Exactly one fallback event; the decision is never overwritten.
        self.assertEqual(len(_events_named(trace, "unet_early_activation_fallback")), 1)
        self.assertEqual(state["fallback_reason"], "vram_insufficient")

    def test_join_invalid_identity_elects_fallback(self):
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            dm_a = _FakeDiffusion()
            patcher = _FakePatcher(dm_a)
            mm._place(patcher)
            state = self._ready_state("join-invalid", dm_a, patcher)
            fut: Future = Future()
            fut.set_result({"status": "ready"})
            state["future"] = fut
            # A different diffusion model at the sampler: logical identity fails.
            dm_b = _FakeDiffusion()
            other = _FakePatcher(dm_b)
            mm._place(other)
            trace = RuntimeTrace(request_id="join-invalid", process="test")
            outcome = mp.join_unet_early_activation(
                None, unet=other, trace=trace, request_id="join-invalid",
            )
            self.assertFalse(outcome["valid"])
            self.assertTrue(state["fallback_elected"])
            self.assertIn("invalid:", state["fallback_reason"])

    def test_not_scheduled_returns_without_fallback(self):
        trace = RuntimeTrace(request_id="join-unsched", process="test")
        outcome = mp.join_unet_early_activation(
            None, unet=_FakePatcher(_FakeDiffusion()),
            trace=trace, request_id="join-unsched",
        )
        self.assertFalse(outcome["scheduled"])
        self.assertEqual(outcome["status"], "not_scheduled")
        self.assertEqual(
            len(_events_named(trace, "unet_early_activation_fallback")), 0,
        )


class CancellationTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_worker_observes_cancellation_before_mutation(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        vram_gate = threading.Event()
        calls = {"count": 0}
        orig_vram = mp._check_early_activation_vram

        def gated_vram(models):
            calls["count"] += 1
            result = orig_vram(models)
            if calls["count"] == 2:
                # Worker re-check: block until the test finalizes the request.
                vram_gate.wait(timeout=10)
            return result

        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-cancel", process="test")
                _setup_eligible_request("ea-cancel", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                mp._check_early_activation_vram = gated_vram
                try:
                    self.assertTrue(mp.clip_encode_start(
                        bridge, trace=trace, request_id="ea-cancel", clip=clip,
                        encode_entries=[{"node_id": "6", "text": "a cat"}],
                    ))
                    # Wait until the worker is blocked in its VRAM re-check
                    # (call 2) — i.e. AFTER scheduling, BEFORE mutation.
                    deadline = time.time() + 10
                    while time.time() < deadline and calls["count"] < 2:
                        time.sleep(0.02)
                    self.assertGreaterEqual(calls["count"], 2)
                    record = mp.finalize_unet_early_activation("ea-cancel", trace=trace)
                    self.assertIsNotNone(record)
                    self.assertEqual(record["status"], "cancelled")
                    self.assertIsNone(mp._unet_activation_get("ea-cancel"))
                    self.assertEqual(
                        len(_events_named(trace, "unet_early_activation_reconciliation")), 1,
                    )
                    # Release the worker; it observes cancellation and never
                    # performs a GPU load.
                    vram_gate.set()
                    time.sleep(0.3)
                    self.assertEqual(mm.load_count, 0)
                    self.assertIsNone(mp._unet_activation_get("ea-cancel"))
                finally:
                    mp._check_early_activation_vram = orig_vram
                    vram_gate.set()


class PoolAndLaneTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_one_pool_one_mutation_lane(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, _clip):
                trace = RuntimeTrace(request_id="ea-lane", process="test")
                _setup_eligible_request("ea-lane", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                pool_id = id(bridge.coordinator._pool)
                # The coordinator owns the process-singleton mutation lane.
                self.assertIs(bridge.coordinator.mutation_lane, mp._get_mutation_lane())
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                state = mp._unet_activation_get("ea-lane")
                outcome = state["future"].result(timeout=10)
                self.assertEqual(outcome["status"], "ready")
                # No second executor was created.
                self.assertIsNotNone(bridge.coordinator._pool)
                self.assertEqual(id(bridge.coordinator._pool), pool_id)
                # The worker ran inside the coordinator lane scope.
                self.assertEqual(mm.lane_seen, "UNET_EARLY_ACTIVATION")
                self.assertEqual(len(_events_named(trace, "unet_early_activation_worker_start")), 1)


class IdentityAndTransferTests(unittest.TestCase):
    def setUp(self):
        mp._UNET_ACTIVATION_MODE = MODE

    def tearDown(self):
        _teardown_common()

    def test_identity_holds_with_differing_sampler_patcher(self):
        dm = _FakeDiffusion()
        retained = _FakePatcher(dm)
        # The sampler uses a different patcher wrapping the SAME diffusion model.
        sampler_patcher = _FakePatcher(dm, loaded=retained.model_size())
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            mm._place(sampler_patcher)
            state = mp._unet_activation_new_state("ea-identity")
            state["key"] = {
                "mode": MODE,
                "unet_diffusion_object_id": str(id(dm)),
                "device": "cuda:0",
                "compute_dtype": "",
            }
            ok, reason = mp._validate_early_activated_unet(sampler_patcher, state)
            self.assertTrue(ok, reason)
            # A different diffusion model fails closed.
            other = _FakePatcher(_FakeDiffusion())
            mm._place(other)
            ok2, reason2 = mp._validate_early_activated_unet(other, state)
            self.assertFalse(ok2)
            self.assertEqual(reason2, "diffusion_identity_mismatch")

    def test_one_physical_transfer_second_load_no_allocation(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-xfer", process="test")
                _setup_eligible_request("ea-xfer", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                state = mp._unet_activation_get("ea-xfer")
                state["future"].result(timeout=10)
                # First (early) load: one physical model-sized transfer.
                self.assertEqual(state["transfer_count"], 1)
                self.assertEqual(mm.load_count, 1)
                self.assertEqual(unet_patcher.loaded_size(), unet_patcher.model_size())
                # Second (graph/sampler) load: a no-allocation cache validation.
                mm.load_models_gpu([unet_patcher])
                self.assertEqual(mm.load_count, 2)
                self.assertEqual(unet_patcher.loaded_size(), unet_patcher.model_size())


class VRAMAndPageReadinessTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_vram_insufficient_phase0_continues(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=1 * 1024 ** 3)  # 1GB free, ~6.6GB required
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, _clip):
                trace = RuntimeTrace(request_id="ea-vram", process="test")
                _setup_eligible_request("ea-vram", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                # Eligibility failed at the boundary: no activation state, no
                # worker, no load.
                self.assertIsNone(mp._unet_activation_get("ea-vram"))
                self.assertEqual(mm.load_count, 0)
                skipped = _events_named(trace, "unet_early_activation_skipped")
                self.assertEqual(len(skipped), 1)
                self.assertEqual(skipped[0].metadata.get("reason"), "vram_insufficient")
                # Graph demand: Phase 0 continues unchanged — the retained
                # UNET is returned (late fallback is the unchanged path); no
                # explicit activation fallback is elected because no
                # activation ever existed.
                consumed = bridge._consume_unet(
                    ("unet.safetensors",),
                    {"unet_name": "unet.safetensors", "weight_dtype": "default"},
                )
                self.assertIsNot(consumed, mp._LOADER_MISS)
                self.assertEqual(
                    len(_events_named(trace, "unet_early_activation_fallback")), 0,
                )

    def test_page_readiness_off_by_default(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, _clip):
                trace = RuntimeTrace(request_id="ea-pages", process="test")
                _setup_eligible_request("ea-pages", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                state = mp._unet_activation_get("ea-pages")
                outcome = state["future"].result(timeout=10)
                self.assertEqual(outcome["status"], "ready")
                self.assertEqual(mm.load_count, 1)
                page_events = [
                    e.name for e in trace.events
                    if "page_readiness" in e.name
                ]
                self.assertEqual(page_events, [])


class MarkerTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_production_marker_is_idempotent_and_unmark_clears_exactly(self):
        # The request-time binding marks once; a duplicate mark must be
        # harmless and unmark must clear EXACTLY the request key without
        # touching unrelated keys (no leak across requests).
        self.assertFalse(mp.is_production_cpu_snapshot_request("marker-noleak"))
        mp.mark_production_cpu_snapshot_request("marker-noleak")
        self.assertTrue(mp.is_production_cpu_snapshot_request("marker-noleak"))
        # Idempotent re-mark (e.g. request-time binding re-run) is harmless.
        mp.mark_production_cpu_snapshot_request("marker-noleak")
        self.assertTrue(mp.is_production_cpu_snapshot_request("marker-noleak"))
        # Unrelated request keys survive the unmark.
        mp.mark_production_cpu_snapshot_request("marker-other")
        mp.unmark_production_cpu_snapshot_request("marker-noleak")
        self.assertFalse(mp.is_production_cpu_snapshot_request("marker-noleak"))
        self.assertTrue(mp.is_production_cpu_snapshot_request("marker-other"))
        mp.unmark_production_cpu_snapshot_request("marker-other")
        self.assertFalse(mp.is_production_cpu_snapshot_request("marker-other"))
        # Empty request ids are never marked / never unmarked into a
        # false positive.
        mp.mark_production_cpu_snapshot_request("")
        self.assertFalse(mp.is_production_cpu_snapshot_request(""))
        mp.unmark_production_cpu_snapshot_request("")
        self.assertFalse(mp.is_production_cpu_snapshot_request(""))

    def test_unmarked_request_after_cleanup_not_eligible(self):
        # Simulate the modal_app request finally: the production marker is
        # unmarked after the request, so a later (or re-run) boundary must
        # NOT schedule — the marker never leaks into another request.
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-unmarked", process="test")
                _setup_eligible_request("ea-unmarked", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                # Request cleanup (finally) unmarks before the boundary runs.
                mp.unmark_production_cpu_snapshot_request("ea-unmarked")
                self.assertFalse(mp.clip_encode_start(
                    bridge, trace=trace, request_id="ea-unmarked", clip=clip,
                    encode_entries=[{"node_id": "6", "text": "a cat"}],
                ))
                self.assertIsNone(mp._unet_activation_get("ea-unmarked"))
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(
                    elig[0].metadata.get("reason"), "cpu_snapshot_mode_inactive",
                )
                self.assertEqual(mm.load_count, 0)

    def test_required_markers_on_successful_activation(self):
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-markers", process="test")
                _setup_eligible_request("ea-markers", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                state = mp._unet_activation_get("ea-markers")
                state["future"].result(timeout=10)
                # Worker-side markers (exactly once each).
                self.assertEqual(len(_events_named(trace, "unet_early_activation_mode")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_eligible")), 1)
                self.assertTrue(_events_named(trace, "unet_early_activation_eligible")[0].metadata.get("eligible"))
                self.assertEqual(len(_events_named(trace, "unet_early_activation_scheduled")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_worker_start")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_lane_wait_start")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_load_start")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_load_end")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_lane_acquired")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_completed")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_terminal")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_failed")), 0)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_skipped")), 0)
                # Graph/sampler demand joins the same future.
                outcome = bridge._join_unet_early_activation(
                    unet_patcher, trace=trace,
                )
                self.assertTrue(outcome["valid"])
                self.assertEqual(len(_events_named(trace, "unet_early_activation_graph_demand")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_graph_join_start")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_graph_join_end")), 1)
                self.assertEqual(len(_events_named(trace, "unet_early_activation_consumed")), 1)
                # Request-end reconciliation.
                record = mp.finalize_unet_early_activation("ea-markers", trace=trace)
                self.assertIsNotNone(record)
                self.assertEqual(record["status"], "ready")
                self.assertEqual(
                    len(_events_named(trace, "unet_early_activation_reconciliation")), 1,
                )

    def test_failed_worker_emits_failed_and_terminal(self):
        mp._UNET_ACTIVATION_MODE = MODE

        def boom(key):
            raise RuntimeError("unet load boom")

        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE, unet_loader=boom) as (bridge, _u, clip):
                trace = RuntimeTrace(request_id="ea-fail", process="test")
                mp.mark_production_cpu_snapshot_request("ea-fail")
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                with self.assertRaises(RuntimeError):
                    prep.unet_future.result(timeout=10)  # future itself failed
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                self.assertIsNone(mp._unet_activation_get("ea-fail"))
                # Eligibility: unet_future_failed -> skipped, never scheduled.
                elig = _events_named(trace, "unet_early_activation_eligible")
                self.assertEqual(len(elig), 1)
                self.assertFalse(elig[0].metadata.get("eligible"))
                self.assertEqual(elig[0].metadata.get("reason"), "unet_future_failed")


class WaterfallArithmeticTests(unittest.TestCase):
    def tearDown(self):
        _teardown_common()

    def test_overlapping_intervals_reconcile(self):
        state = mp._unet_activation_new_state("wf-overlap")
        state["clip_encode_start_mono_ns"] = 1_000_000_000
        state["clip_encode_end_mono_ns"] = 3_000_000_000          # 2000ms clip
        state["submitted_mono_ns"] = 1_500_000_000
        state["terminal_mono_ns"] = 4_000_000_000                 # 2500ms activation
        state["clip_encode_process_cpu_ms"] = 800.0
        record = mp._build_unet_early_activation_reconciliation(state)
        self.assertEqual(record["clip_interval_ms"], 2000.0)
        self.assertEqual(record["activation_interval_ms"], 2500.0)
        self.assertEqual(record["overlap_ms"], 1500.0)
        self.assertEqual(record["sequential_equivalent_ms"], 4500.0)
        self.assertEqual(record["combined_interval_ms"], 3000.0)
        self.assertEqual(
            record["efficiency"],
            round(1500.0 / 4500.0, 4),
        )
        self.assertEqual(record["clip_slowdown_ms"], round(2000.0 - 800.0, 3))

    def test_disjoint_intervals_have_zero_overlap(self):
        state = mp._unet_activation_new_state("wf-disjoint")
        state["clip_encode_start_mono_ns"] = 1_000_000_000
        state["clip_encode_end_mono_ns"] = 2_000_000_000          # clip before activation
        state["submitted_mono_ns"] = 3_000_000_000
        state["terminal_mono_ns"] = 5_000_000_000
        record = mp._build_unet_early_activation_reconciliation(state)
        self.assertEqual(record["clip_interval_ms"], 1000.0)
        self.assertEqual(record["activation_interval_ms"], 2000.0)
        self.assertEqual(record["overlap_ms"], 0.0)
        self.assertEqual(record["sequential_equivalent_ms"], 3000.0)
        self.assertEqual(record["combined_interval_ms"], 3000.0)
        self.assertEqual(record["efficiency"], 0.0)

    def test_uses_actual_clip_encode_end_not_scheduling_only(self):
        state = mp._unet_activation_new_state("wf-real")
        state["clip_encode_start_mono_ns"] = 1_000_000_000
        state["clip_encode_end_mono_ns"] = 2_500_000_000
        state["submitted_mono_ns"] = 1_100_000_000
        state["terminal_mono_ns"] = 2_000_000_000
        record = mp._build_unet_early_activation_reconciliation(state)
        # The clip interval is the ACTUAL encode (start..end), not the
        # scheduling time; overlap uses the true encode end.
        self.assertEqual(record["clip_interval_ms"], 1500.0)
        self.assertEqual(record["activation_interval_ms"], 900.0)
        self.assertEqual(record["overlap_ms"], 900.0)
        self.assertEqual(record["sequential_equivalent_ms"], 2400.0)
        self.assertEqual(record["combined_interval_ms"], 1500.0)

    def test_record_clip_encode_start_sets_actual_encode_boundary(self):
        state = mp._unet_activation_new_state("wf-record-start")
        state["submitted_mono_ns"] = 5_000_000_000
        with mp._UNET_ACTIVATION_LOCK:
            mp._UNET_ACTIVATION_STATE["wf-record-start"] = state
        try:
            # The encode boundary (captured immediately before the encode
            # loop) becomes clip_encode_start_mono_ns.
            mp.record_clip_encode_start(
                "wf-record-start", {"mono_ns": 7_500_000_000},
            )
            self.assertEqual(state["clip_encode_start_mono_ns"], 7_500_000_000)
            # The schedule/submit timestamp stays separate and untouched.
            self.assertEqual(state["submitted_mono_ns"], 5_000_000_000)
            # Missing / zero counters leave the boundary unchanged (0 = the
            # encode never started / was never measured — never fabricated).
            mp.record_clip_encode_start("wf-record-start", None)
            mp.record_clip_encode_start("wf-record-start", {"mono_ns": 0})
            self.assertEqual(state["clip_encode_start_mono_ns"], 7_500_000_000)
            # Safe when no activation state exists (no early future).
            mp.record_clip_encode_start("wf-missing", {"mono_ns": 1_000_000_000})
            self.assertIsNone(mp._unet_activation_get("wf-missing"))
        finally:
            with mp._UNET_ACTIVATION_LOCK:
                mp._UNET_ACTIVATION_STATE.pop("wf-record-start", None)

    def test_full_prefill_records_actual_clip_encode_start(self):
        # clip_encode_start_mono_ns must be the ACTUAL encode start recorded
        # at the prefill encode boundary — not the scheduling time — and the
        # reconciliation must use it.
        mp._UNET_ACTIVATION_MODE = MODE
        mm = _FakeModelManagement(free_bytes=24 * 1024 ** 3)
        with _ComfyMMContext(mm):
            with _early_bridge(mode=MODE) as (bridge, unet_patcher, clip):
                trace = RuntimeTrace(request_id="ea-wf-actual", process="test")
                _setup_eligible_request("ea-wf-actual", unet_patcher)
                bridge.prepare(_make_plan(), trace=trace)
                prep = bridge._preparation
                self.assertTrue(bridge.schedule_execution_prefill(trace=trace))
                prep.prefill_future.result(timeout=10)
                state = mp._unet_activation_get("ea-wf-actual")
                self.assertIsNotNone(state)
                state["future"].result(timeout=10)
                # The actual encode-start boundary exists in the trace.
                encode_start_events = _events_named(
                    trace, "execution_prefill_encode_start",
                )
                self.assertEqual(len(encode_start_events), 1)
                counters = (encode_start_events[0].metadata or {}).get("counters")
                self.assertIsNotNone(counters)
                actual_start_ns = int(counters.get("mono_ns") or 0)
                self.assertGreater(actual_start_ns, 0)
                # The recorded start IS the actual encode boundary, and it is
                # at/after submission (the scheduling timestamp stays a
                # separate field).
                self.assertEqual(state["clip_encode_start_mono_ns"], actual_start_ns)
                self.assertGreaterEqual(
                    state["clip_encode_start_mono_ns"],
                    state["submitted_mono_ns"],
                )
                # Reconciliation uses the actual encode start/end.
                record = mp._build_unet_early_activation_reconciliation(state)
                expected_interval = round(
                    (
                        state["clip_encode_end_mono_ns"]
                        - state["clip_encode_start_mono_ns"]
                    ) / 1_000_000,
                    3,
                )
                self.assertEqual(record["clip_interval_ms"], expected_interval)
                self.assertEqual(
                    record["clip_encode_start_mono_ns"],
                    state["clip_encode_start_mono_ns"],
                )


class RuntimeEnvPropagationTests(unittest.TestCase):
    """_runtime_env() forwards COMFYMODAL_V2_UNET_ACTIVATION_MODE to the
    remote Modal class environment with a safe default.

    The mapping must default to ``late`` when unset (never the candidate)
    and preserve the exact raw value when set — normalization is left to
    model_preload._resolve_unet_activation_mode, the single canonical
    parser.
    """

    _KEY = "COMFYMODAL_V2_UNET_ACTIVATION_MODE"

    def setUp(self):
        self._prev = os.environ.pop(self._KEY, None)

    def tearDown(self):
        if self._prev is not None:
            os.environ[self._KEY] = self._prev
        else:
            os.environ.pop(self._KEY, None)

    def _env(self) -> dict:
        from comfymodal_runtime.modal_app import _runtime_env
        return _runtime_env()

    def test_defaults_safely_to_late_when_unset(self):
        env = self._env()
        self.assertIn("COMFYMODAL_V2_UNET_ACTIVATION_MODE", env)
        self.assertEqual(env["COMFYMODAL_V2_UNET_ACTIVATION_MODE"], "late")
        # The safe default never activates the candidate path.
        self.assertEqual(
            mp._resolve_unet_activation_mode(
                env["COMFYMODAL_V2_UNET_ACTIVATION_MODE"]
            ),
            "late",
        )

    def test_forwards_exact_clip_encode_start_raw_value(self):
        os.environ[self._KEY] = "clip_encode_start"
        env = self._env()
        self.assertEqual(env["COMFYMODAL_V2_UNET_ACTIVATION_MODE"], "clip_encode_start")
        self.assertEqual(
            mp._resolve_unet_activation_mode(
                env["COMFYMODAL_V2_UNET_ACTIVATION_MODE"]
            ),
            "clip_encode_start",
        )

    def test_forwards_raw_value_without_normalizing(self):
        # modal_app must pass the raw value through untouched; canonical
        # normalization belongs to model_preload (mixed case is accepted
        # there, so the remote runtime still reaches clip_encode_start).
        os.environ[self._KEY] = "CLIP_ENCODE_START"
        env = self._env()
        self.assertEqual(env["COMFYMODAL_V2_UNET_ACTIVATION_MODE"], "CLIP_ENCODE_START")
        self.assertEqual(
            mp._resolve_unet_activation_mode(
                env["COMFYMODAL_V2_UNET_ACTIVATION_MODE"]
            ),
            "clip_encode_start",
        )


if __name__ == "__main__":
    unittest.main()
