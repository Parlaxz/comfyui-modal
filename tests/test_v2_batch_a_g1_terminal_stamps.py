"""Batch-A G1 + terminal-cleanup stamps: targeted local validation.

Covers, with lightweight fakes (no Modal, no ComfyUI graph, no real model
loading):

- ``_stamp_terminal_cleanup`` populates the four timing fields on the
  terminal event data (and falls back to the event dict when no data).
- Plan-receipt early-UNET eligibility gate: eligible fast-disk shape
  schedules; retained-UNET / legacy / ambiguous / role-mismatch / missing
  identity shapes skip early (returns False, never raises).
- Request-scoped identity stash is set only when eligible and reset per
  call.
- Single-flight: an already in-flight UNET lane is never replaced by the
  plan-receipt path.
- Carry-over in ``_init_ready_preparation`` (real ``V2LoaderBridge`` with a
  fake node registry): an in-flight same-key UNET future survives a
  clip-only publication; a done (previous-request) future or a different
  key is NOT carried; the coordinator's ``schedule_execution_unet`` is
  idempotent (same future returned on duplicate submit).
"""

from __future__ import annotations

import threading
import time
import types
from typing import Any


# ── Minimal shared fixtures ───────────────────────────────────────────────


WORKFLOW = {
    "1": {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": "model.safetensors", "weight_dtype": "default"},
    },
    "2": {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": "clip.safetensors", "type": "stable_diffusion"},
    },
}

WORKFLOW_OTHER_UNET = {
    "1": {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": "other.safetensors", "weight_dtype": "default"},
    },
    "2": {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": "clip.safetensors", "type": "stable_diffusion"},
    },
}


class FakePlan:
    def __init__(self, workflow: dict | None = WORKFLOW) -> None:
        self.workflow = dict(workflow) if workflow is not None else {}
        self.model_stack = {}
        self.workflow_hash = "abc123"
        self.request_id = "req-1"


class FakeModels:
    def __init__(self, unet: Any = None, clip: Any = object(), vae: Any = object(), spec: Any = None) -> None:
        self.unet = unet
        self.clip = clip
        self.vae = vae
        self.model_spec = spec
        self.model_key = None


class FakeBridge:
    def __init__(self) -> None:
        self._preparation = None
        self._model_key = None
        self.schedule_calls: list[str] = []
        self.init_calls = 0

    def _init_ready_preparation(self, **kwargs: Any) -> Any:
        self.init_calls += 1
        self._model_key = kwargs["model_key"]
        self._preparation = types.SimpleNamespace(
            model_key=kwargs["model_key"],
            unet_future=None,
            clip_future=None,
        )
        return self._preparation

    def schedule_execution_unet(self, *, trace: Any = None, request_id: str = "") -> bool:
        self.schedule_calls.append(request_id)
        if self._preparation is not None:
            self._preparation.unet_future = _FakeFuture(done=False)
        return True


class _FakeFuture:
    def __init__(self, done: bool = True) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


def _make_entrypoint(models: FakeModels, bridge: FakeBridge | None = None, active: bool = False) -> Any:
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint

    entry = ModalRuntimeEntrypoint.__new__(ModalRuntimeEntrypoint)
    entry._cpu_snapshot_models = models
    entry._cpu_snapshot_models_active = active
    entry._preload_bridge = bridge or FakeBridge()
    entry._lazy_init_snapshot_state = lambda: None
    return entry


def _early_schedule(entry: Any, plan: Any, request_id: str = "r1") -> bool:
    return entry._maybe_schedule_execution_unet_at_plan_receipt(
        plan,
        request_id=request_id,
    )


# ── Terminal-cleanup stamps ───────────────────────────────────────────────


def test_terminal_cleanup_stamps_ride_event_data():
    from comfymodal_runtime.modal_app import _stamp_terminal_cleanup

    event = {"type": "result", "data": {"remote_result_emit_wall_unix_ns": 111}}
    _stamp_terminal_cleanup(
        event,
        start_wall_ns=101,
        start_mono_ns=202,
        end_wall_ns=303,
        end_mono_ns=404,
        request_id="r1",
    )
    data = event["data"]
    assert data["terminal_cleanup_start_wall_unix_ns"] == 101
    assert data["terminal_cleanup_start_mono_ns"] == 202
    assert data["terminal_cleanup_end_wall_unix_ns"] == 303
    assert data["terminal_cleanup_end_mono_ns"] == 404
    # Existing fields untouched (no result semantics change).
    assert data["remote_result_emit_wall_unix_ns"] == 111
    assert len(data) == 5


def test_terminal_cleanup_stamps_fallback_to_event_dict():
    from comfymodal_runtime.modal_app import _stamp_terminal_cleanup

    event = {"type": "error", "message": "x"}
    _stamp_terminal_cleanup(
        event,
        start_wall_ns=1,
        start_mono_ns=2,
        end_wall_ns=3,
        end_mono_ns=4,
        request_id="r1",
    )
    assert event["terminal_cleanup_start_mono_ns"] == 2
    assert event["terminal_cleanup_end_mono_ns"] == 4


def test_terminal_cleanup_window_monotonic_increasing():
    from comfymodal_runtime.modal_app import _stamp_terminal_cleanup

    event: dict[str, Any] = {"type": "result", "data": {}}
    start_wall = time.time_ns()
    start_mono = time.monotonic_ns()
    end_wall = time.time_ns()
    end_mono = time.monotonic_ns()
    _stamp_terminal_cleanup(
        event,
        start_wall_ns=start_wall,
        start_mono_ns=start_mono,
        end_wall_ns=end_wall,
        end_mono_ns=end_mono,
        request_id="r1",
    )
    assert end_mono - start_mono >= 0
    assert end_wall - start_wall >= 0


# ── G1 plan-receipt eligibility gate ──────────────────────────────────────


def test_g1_eligible_fast_disk_shape_schedules_and_stashes_identity():
    from comfymodal_runtime.restore_plan import build_restore_model_spec, derive_model_key, derive_prefill_key

    spec = build_restore_model_spec(dict(WORKFLOW), {})
    models = FakeModels(unet=None, clip=object(), vae=object(), spec=spec)
    bridge = FakeBridge()
    entry = _make_entrypoint(models, bridge=bridge, active=False)

    ok = _early_schedule(entry, FakePlan())

    assert ok is True
    assert bridge.schedule_calls == ["r1"]
    assert bridge.init_calls == 1
    # Identity stash matches the exact binding-block derivation (same calls).
    key = derive_model_key(dict(WORKFLOW))
    assert entry._plan_receipt_request_model_key == key
    assert entry._plan_receipt_request_prefill_key == derive_prefill_key(key, dict(WORKFLOW))
    assert entry._plan_receipt_request_model_spec == spec
    # Early marker emitted into the request trace.
    assert entry._plan_receipt_trace is not None
    names = [e.name for e in entry._plan_receipt_trace.events]
    assert "unet_execution_plan_receipt_schedule" in names


def test_g1_eligible_when_snapshot_already_active():
    from comfymodal_runtime.restore_plan import build_restore_model_spec

    spec = build_restore_model_spec(dict(WORKFLOW), {})
    models = FakeModels(unet=None, clip=object(), vae=object(), spec=spec)
    bridge = FakeBridge()
    entry = _make_entrypoint(models, bridge=bridge, active=True)

    assert _early_schedule(entry, FakePlan()) is True
    assert bridge.schedule_calls == ["r1"]


def test_g1_retained_unet_skips_early():
    models = FakeModels(unet=object(), clip=object(), vae=object(), spec={})
    bridge = FakeBridge()
    entry = _make_entrypoint(models, bridge=bridge, active=True)

    assert _early_schedule(entry, FakePlan()) is False
    assert bridge.schedule_calls == []
    assert bridge.init_calls == 0
    # Request-scoped stash reset even when skipped.
    assert entry._plan_receipt_request_model_key is None


def test_g1_legacy_no_snapshot_skips_early():
    bridge = FakeBridge()
    entry = _make_entrypoint(FakeModels(unet=None), bridge=bridge)
    entry._cpu_snapshot_models = None

    assert _early_schedule(entry, FakePlan()) is False
    assert bridge.schedule_calls == []


def test_g1_inactive_without_clip_skips_early():
    models = FakeModels(unet=None, clip=None, vae=None, spec={})
    bridge = FakeBridge()
    entry = _make_entrypoint(models, bridge=bridge, active=False)

    assert _early_schedule(entry, FakePlan()) is False
    assert bridge.schedule_calls == []


def test_g1_role_mismatch_skips_early():
    from comfymodal_runtime.restore_plan import build_restore_model_spec

    # Snapshot spec derived from a DIFFERENT unet name than the request.
    snapshot_spec = build_restore_model_spec(dict(WORKFLOW_OTHER_UNET), {})
    models = FakeModels(unet=None, clip=object(), vae=object(), spec=snapshot_spec)
    bridge = FakeBridge()
    entry = _make_entrypoint(models, bridge=bridge, active=True)

    assert _early_schedule(entry, FakePlan()) is False
    assert bridge.schedule_calls == []


def test_g1_missing_unet_identity_skips_early():
    # Workflow without any UNETLoader.
    plan = FakePlan(workflow={"2": WORKFLOW["2"]})
    models = FakeModels(unet=None, clip=object(), vae=object(), spec={})
    bridge = FakeBridge()
    entry = _make_entrypoint(models, bridge=bridge, active=True)

    assert _early_schedule(entry, plan) is False
    assert bridge.schedule_calls == []


def test_g1_malformed_plan_never_raises():
    models = FakeModels(unet=None, clip=object(), vae=object(), spec={})
    bridge = FakeBridge()
    entry = _make_entrypoint(models, bridge=bridge, active=True)

    # Missing workflow entirely — derivation yields empty identity, skips.
    assert _early_schedule(entry, FakePlan(workflow=None)) is False
    # A throwaway models object that breaks attribute access must not raise.
    broken = types.SimpleNamespace()
    entry._cpu_snapshot_models = broken
    assert _early_schedule(entry, FakePlan()) is False


def test_g1_inflight_lane_is_respected_single_flight():
    spec = {}
    models = FakeModels(unet=None, clip=object(), vae=object(), spec=spec)
    bridge = FakeBridge()
    # Simulate an already-published prep with an in-flight UNET lane.
    bridge._preparation = types.SimpleNamespace(
        model_key="any", unet_future=_FakeFuture(done=False), clip_future=None,
    )
    bridge._model_key = "any"
    entry = _make_entrypoint(models, bridge=bridge, active=True)

    assert _early_schedule(entry, FakePlan()) is False
    assert bridge.schedule_calls == []
    assert bridge.init_calls == 0  # never replaced


# ── Carry-over in _init_ready_preparation (real bridge, fake node registry) ──


class _FakeNodes:
    NODE_CLASS_MAPPINGS = {
        name: type(f"Node_{name}", (), {method: (lambda self, *a, **k: None)})
        for name, method in {
            "UNETLoader": "load_unet",
            "CLIPLoader": "load_clip",
            "DualCLIPLoader": "load_clip",
            "VAELoader": "load_vae",
            "CLIPTextEncode": "encode",
            "VAEDecode": "decode",
        }.items()
    }


def _real_bridge():
    from comfymodal_runtime.model_preload import V2LoaderBridge

    bridge = V2LoaderBridge()
    bridge._nodes = _FakeNodes
    return bridge


def _key(unet: str) -> Any:
    from comfymodal_runtime.contracts import ModelRestoreKey

    return ModelRestoreKey(unet_identity=unet, clip_identity="clip.safetensors")


def _pf(key: Any) -> Any:
    from comfymodal_runtime.contracts import PrefillKey

    return PrefillKey(model_key=key, prompt_bundle_hash="h")


def _spec(unet: str) -> dict[str, Any]:
    return {"loaders": {"unet": [{"unet_name": unet, "weight_dtype": "default"}]}}


def test_carry_over_inflight_same_key_survives_clip_only_publication():
    from comfymodal_runtime.model_preload import _LOADER_MISS

    bridge = _real_bridge()
    try:
        key = _key("model.safetensors")
        prep1 = bridge._init_ready_preparation(
            model_key=key, prefill_key=_pf(key), model_spec=_spec("model.safetensors"), trace=None,
        )
        release = threading.Event()

        def _slow_work() -> str:
            release.wait(timeout=5)
            return "unet-ready"

        prep1.unet_future = bridge.coordinator.schedule_execution_unet(
            _slow_work, prep1, trace=None,
        )
        assert prep1.unet_future is not None and not prep1.unet_future.done()

        # Binding-block clip-only publication (UNET == _LOADER_MISS) with the
        # same model key must carry the in-flight future (single flight).
        clip = object()
        prep2 = bridge._init_ready_preparation(
            model_key=key, prefill_key=_pf(key), model_spec=_spec("model.safetensors"),
            unet=_LOADER_MISS, clip=clip, trace=None,
        )
        assert prep2.unet_future is prep1.unet_future
        assert prep2.clip_future is not None
        # Diagnostics object shared so the worker's completion timestamp is
        # readable through the new preparation.
        assert prep2.diagnostics is prep1.diagnostics

        release.set()
        assert prep2.unet_future.result(timeout=5) == "unet-ready"
        assert prep1.diagnostics.unet_completed_at is not None
    finally:
        bridge.coordinator.close()


def test_carry_over_skipped_for_done_previous_request_future():
    from comfymodal_runtime.model_preload import _LOADER_MISS

    bridge = _real_bridge()
    try:
        key = _key("model.safetensors")
        prep1 = bridge._init_ready_preparation(
            model_key=key, prefill_key=_pf(key), model_spec=_spec("model.safetensors"), trace=None,
        )
        prep1.unet_future = bridge.coordinator.schedule_execution_unet(
            lambda: "old", prep1, trace=None,
        )
        assert prep1.unet_future.result(timeout=5) == "old"
        assert prep1.unet_future.done()

        # A DONE future belongs to a previous request: never carried, so the
        # next request gets its own fresh lane.
        prep2 = bridge._init_ready_preparation(
            model_key=key, prefill_key=_pf(key), model_spec=_spec("model.safetensors"),
            unet=_LOADER_MISS, clip=object(), trace=None,
        )
        assert prep2.unet_future is None
    finally:
        bridge.coordinator.close()


def test_carry_over_skipped_for_different_key():
    from comfymodal_runtime.model_preload import _LOADER_MISS

    bridge = _real_bridge()
    try:
        key_a = _key("a.safetensors")
        prep1 = bridge._init_ready_preparation(
            model_key=key_a, prefill_key=_pf(key_a), model_spec=_spec("a.safetensors"), trace=None,
        )
        release = threading.Event()

        def _slow() -> str:
            release.wait(timeout=5)
            return "a-ready"

        prep1.unet_future = bridge.coordinator.schedule_execution_unet(_slow, prep1, trace=None)

        key_b = _key("b.safetensors")
        prep2 = bridge._init_ready_preparation(
            model_key=key_b, prefill_key=_pf(key_b), model_spec=_spec("b.safetensors"),
            unet=_LOADER_MISS, clip=object(), trace=None,
        )
        assert prep2.unet_future is None  # different identity: never carried
        release.set()
        prep1.unet_future.result(timeout=5)
    finally:
        bridge.coordinator.close()


def test_coordinator_schedule_execution_unet_is_single_flight():
    from comfymodal_runtime.model_preload import _LOADER_MISS

    bridge = _real_bridge()
    try:
        key = _key("model.safetensors")
        prep = bridge._init_ready_preparation(
            model_key=key, prefill_key=_pf(key), model_spec=_spec("model.safetensors"), trace=None,
        )
        fut1 = bridge.coordinator.schedule_execution_unet(lambda: 42, prep, trace=None)
        fut2 = bridge.coordinator.schedule_execution_unet(lambda: 43, prep, trace=None)
        assert fut1 is fut2 is prep.unet_future
        # The later (duplicate) schedule is an idempotent no-op: one lane only.
        assert fut1.result(timeout=5) == 42
        # Bridge-level schedule_execution_unet with a prepared future is also
        # a no-op that returns True (already_prepared) — no second submission.
        assert bridge.schedule_execution_unet(trace=None, request_id="dup") is True
        assert prep.unet_future is fut1
    finally:
        bridge.coordinator.close()
