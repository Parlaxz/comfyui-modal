"""R44B Lane E: request-scoped FastSafe reachability harness.

Narrow validation coverage for the new request-time fast-path modules:

* ``comfymodal_runtime.request_fastpath``      (context lifecycle, descriptors)
* ``comfymodal_runtime.request_clip_fastsafe`` (producer + forward boundary)
* ``comfymodal_runtime.request_unet_fastsafe`` (ordering cases + D15 arbiter)
* ``comfymodal_runtime.gpu_lane_coordination`` (additive clip-end hook)

Everything except the descriptor-header group runs dependency-free via
injected fake modules (no Modal, no network, no CUDA, no golden bridge, no
modal_app/config_authority imports).  Each test opens its own request
context through ``request_fastpath.begin`` and tears it down in ``finally``
so the ContextVar never leaks between tests.
"""
from __future__ import annotations

import contextvars
import inspect
import json
import os
import sys
import threading
import types

import pytest

from comfymodal_runtime import gpu_lane_coordination as coord
from comfymodal_runtime import request_clip_fastsafe as rcfs
from comfymodal_runtime import request_fastpath as rfp
from comfymodal_runtime import request_unet_fastsafe as rufs

FAKE_TENSOR = object()
TENSOR_KEY = "w"
NATIVE_MARKER = "__native_read__"
UNET_PATCHER_SENTINEL = "UNET_PATCHER_SENTINEL"

_AUTO_DESCRIPTOR = object()


# ---------------------------------------------------------------------------
# Shared fakes / fixtures
# ---------------------------------------------------------------------------


class FakeTrace:
    """Records telemetry emissions the way RuntimeTrace.emit is called."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, name, phase=None, metadata=None, **extra):
        md = dict(metadata or {})
        md.update(extra)
        self.events.append((str(name), md))

    def names(self) -> list[str]:
        return [name for name, _ in self.events]


class FakeLoader:
    def __init__(self, label: str = "loader") -> None:
        self.label = label
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeFB:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeDescriptor:
    """Frozen stand-in for ModelFileDescriptor (header-only contract)."""

    def __init__(self, *, keys=(TENSOR_KEY,), metadata=None, size_bytes=2048, fresh=True):
        self.keys = tuple(keys)
        self.metadata = dict(metadata or {})
        self.size_bytes = int(size_bytes)
        self._fresh = bool(fresh)

    def fresh(self) -> bool:
        return self._fresh


@pytest.fixture
def fastsafe_env(monkeypatch):
    """Enable the request fast-path flags; disable live GPU coordination."""
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.setenv(rfp.FLAG_UNET, "1")
    monkeypatch.setenv(rfp.FLAG_SOURCE_PREP, "1")
    monkeypatch.delenv(coord.COORDINATION_FLAG, raising=False)
    monkeypatch.delenv(coord.SCOPED_CUDA_READINESS_FLAG, raising=False)


@pytest.fixture
def fake_torch(monkeypatch):
    """CUDA-less torch stand-in so producers never hit fail-closed on CUDA."""
    mod = types.ModuleType("torch")
    mod.cuda = types.SimpleNamespace(
        current_device=lambda: 0,
        memory_allocated=lambda: 4096,
        memory_reserved=lambda: 8192,
        empty_cache=lambda: None,
        is_available=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "torch", mod)
    return mod


def _assert_json_leaves(value) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_json_leaves(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_leaves(item)
        return
    raise AssertionError(f"non-JSON-safe leaf: {type(value)!r}")


def _install_fake_checkpoint_prewarm(monkeypatch):
    cp_mod = types.ModuleType("comfymodal_runtime.checkpoint_prewarm")
    cp_mod.PREWARM_THREADS_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS"
    cp_mod.PREWARM_CHUNK_MB_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB"
    prewarmers: list = []

    class FakePrewarmer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started_paths = None
            self.joined = False
            prewarmers.append(self)

        def start(self, paths):
            self.started_paths = list(paths)
            return True

        def before_demand_load(self):
            return None

        def stop_and_join_before_demand(self):
            self.joined = True
            return True

    cp_mod.CheckpointPrewarmer = FakePrewarmer
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.checkpoint_prewarm", cp_mod)
    return prewarmers


def _install_fake_loader_selection(monkeypatch):
    ls_mod = types.ModuleType("comfymodal_runtime.loader_selection")
    observed: list = []
    ls_mod.record_observed = lambda role, arm, **kw: observed.append((role, arm, dict(kw)))
    ls_mod.normalize_observed = lambda role, arm: (
        "native_comfy" if arm == "native" else arm
    )
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.loader_selection", ls_mod)
    return observed


# ---------------------------------------------------------------------------
# Group 1: context lifecycle (pure)
# ---------------------------------------------------------------------------


def test_context_claim_single_flight_and_state_transitions():
    ctx = rfp.begin(request_id="ctx-1")
    try:
        assert rfp.current() is ctx
        assert ctx.clip_state == "idle"
        assert ctx.unet_state == "idle"
        # Single-flight: first claim wins, duplicate is refused.
        assert ctx.claim_physical_load("clip") is True
        assert ctx.claim_physical_load("clip") is False
        assert ctx.clip_state == "loading"
        assert ctx.unet_state == "idle"
        # Mark transitions follow the frozen vocabulary.
        ctx.mark_clip_loaded()
        assert ctx.clip_state == "ready"
        ctx.mark_clip_forward_start()
        assert ctx.clip_state == "forwarding"
        ctx.mark_clip_forward_end()
        assert ctx.clip_state == "critical_done"
        assert ctx.clip_forward_done_event().is_set()
        assert ctx.summary()["clip_forward_wall_ms"] is not None
    finally:
        rfp.teardown(ctx)


def test_context_release_claim_then_reclaim_pins_actual_semantics():
    """DOCUMENTED SPEC DEVIATION (reported, not fixed): the lane spec expected
    a post-release re-claim to stay False ('single-flight per ctx'), but
    ``release_claim`` clears the latch, so a re-claim succeeds.  This test
    pins the ACTUAL implementation behavior."""
    ctx = rfp.begin(request_id="ctx-release")
    try:
        assert ctx.claim_physical_load("unet") is True
        ctx.release_claim("unet", "probe_reason")
        assert "unet:probe_reason" in ctx.terminal_reasons()
        assert ctx.claim_physical_load("unet") is True
    finally:
        rfp.teardown(ctx)


def test_context_record_terminal_is_append_only_and_sticky():
    ctx = rfp.begin(request_id="ctx-term")
    try:
        ctx.record_terminal("r1", role="clip")
        ctx.record_terminal("r2")
        before = ctx.terminal_reasons()
        ctx.record_terminal("r3", role="unet")
        after = ctx.terminal_reasons()
        assert before == ("clip:r1", "r2")
        assert after[: len(before)] == before  # sticky: never erased
        assert "unet:r3" in after
    finally:
        rfp.teardown(ctx)


def test_context_summary_is_json_safe():
    ctx = rfp.begin(request_id="ctx-sum")
    try:
        assert ctx.claim_physical_load("clip") is True
        ctx.mark_clip_loaded()
        ctx.record_terminal("boom", role="clip")
        summary = ctx.summary()
        json.dumps(summary)  # must serialize
        _assert_json_leaves(summary)
        assert set(summary["states"]) == {"clip", "unet"}
        assert summary["states"]["clip"] == "ready"
        assert summary["claims"]["clip"] is True
        assert "clip:boom" in summary["terminal_reasons"]
    finally:
        rfp.teardown(ctx)


def test_context_teardown_idempotent_and_current_binding():
    ctx = rfp.begin(request_id="ctx-td")
    assert rfp.current() is ctx
    rfp.teardown(ctx)
    assert rfp.current() is None
    rfp.teardown(ctx)  # idempotent, never raises
    assert ctx.summary()["torn_down"] is True


def test_context_arm_and_join_source_prep_with_fake_prewarmer(monkeypatch):
    prewarmers = _install_fake_checkpoint_prewarm(monkeypatch)
    ctx = rfp.begin(request_id="ctx-prep")
    try:
        assert ctx.arm_unet_source_prep(["a.sft"]) is True
        # Idempotent arming: second call does not spawn another prewarmer.
        assert ctx.arm_unet_source_prep(["b.sft"]) is True
        assert len(prewarmers) == 1
        assert prewarmers[0].started_paths == ["a.sft"]
        joined = ctx.join_unet_source_prep(timeout_s=5.0)
        assert joined["armed"] is True
        assert joined["joined"] is True
        assert prewarmers[0].joined is True
        # Idempotent join.
        assert ctx.join_unet_source_prep()["joined"] is True
        assert ctx.summary()["source_prep_armed"] is True
        assert ctx.summary()["source_prep_joined"] is True
    finally:
        rfp.teardown(ctx)


# ---------------------------------------------------------------------------
# Group 2: descriptor (real safetensors header work)
# ---------------------------------------------------------------------------


def test_descriptor_builds_header_only_from_real_safetensors(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("safetensors")
    from safetensors.torch import save_file

    path = tmp_path / "desc.safetensors"
    save_file({"w": torch.zeros(2, 2)}, str(path))
    desc = rfp.build_descriptor("clip", str(path))
    assert desc is not None
    assert desc.role == "clip"
    assert desc.keys == ("w",)
    assert desc.shapes == {"w": (2, 2)}
    assert desc.dtypes.get("w")
    assert desc.size_bytes > 0
    assert desc.fresh() is True


def test_descriptor_missing_path_returns_none(tmp_path):
    assert rfp.build_descriptor("clip", str(tmp_path / "missing.safetensors")) is None


def test_descriptor_freshness_detects_mtime_bump(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("safetensors")
    from safetensors.torch import save_file

    path = tmp_path / "fresh.safetensors"
    save_file({"w": torch.zeros(2, 2)}, str(path))
    desc = rfp.build_descriptor("clip", str(path))
    assert desc is not None
    assert desc.fresh() is True
    bumped = desc.mtime_ns + 10**9
    os.utime(str(path), ns=(bumped, bumped))  # same size, new mtime
    assert desc.fresh() is False


def test_descriptor_lru_cache_returns_same_object(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("safetensors")
    from safetensors.torch import save_file

    path = tmp_path / "cached.safetensors"
    save_file({"w": torch.zeros(2, 2)}, str(path))
    first = rfp.build_descriptor("clip", str(path))
    second = rfp.build_descriptor("clip", str(path))
    assert first is not None
    assert first is second  # same stat key -> cached immutable object


# ---------------------------------------------------------------------------
# Group 3/4 fakes: CLIP producer world (mocked transport seams)
# ---------------------------------------------------------------------------


def _install_clip_fakes(monkeypatch, tmp_path, *, descriptor=_AUTO_DESCRIPTOR,
                        fail_owner_attach=False):
    # folder_paths: resolve the clip name to a real (existence-only) file.
    fp_mod = types.ModuleType("folder_paths")
    ckpt_file = tmp_path / "clip.safetensors"
    ckpt_file.write_bytes(b"x")  # existence only; the descriptor itself is faked
    resolved = str(ckpt_file)
    fp_mod.get_full_path = lambda kind, name: resolved
    monkeypatch.setitem(sys.modules, "folder_paths", fp_mod)

    # comfy.utils: recorder standing in for the native reader.
    comfy_mod = types.ModuleType("comfy")
    utils_mod = types.ModuleType("comfy.utils")
    ltf_calls: list = []

    def load_torch_file(ckpt, *args, **kwargs):
        ltf_calls.append((str(ckpt), args, kwargs))
        return {NATIVE_MARKER: str(ckpt)}

    utils_mod.load_torch_file = load_torch_file
    comfy_mod.utils = utils_mod
    monkeypatch.setitem(sys.modules, "comfy", comfy_mod)
    monkeypatch.setitem(sys.modules, "comfy.utils", utils_mod)

    # clip_fast_hydration: ownership/hydration seams.
    cfh_mod = types.ModuleType("comfymodal_runtime.clip_fast_hydration")
    owner_calls: list = []
    hydrated_calls: list = []
    cfh_mod.MODE_FASTSAFE = "fastsafe"
    cfh_mod.OWNER_ATTR = "_test_owners"

    def owner_attach(clip, loader, fb):
        if fail_owner_attach:
            raise RuntimeError("owner_attach_boom")
        owner_calls.append((loader, fb))

    cfh_mod.owner_attach = owner_attach
    cfh_mod.mark_clip_hydrated = lambda clip: hydrated_calls.append(clip)
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.clip_fast_hydration", cfh_mod)

    # clip_fast_hydration_wiring: transport + mode-recorder seams.
    wiring_mod = types.ModuleType("comfymodal_runtime.clip_fast_hydration_wiring")
    fs_calls: list = []
    owners_created: list = []

    def _fastsafe_load(path, metrics=None):
        fs_calls.append(str(path))
        if metrics is not None:
            metrics["fastsafe_setup_wall_ms"] = 0.1
            metrics["fastsafe_copy_wall_ms"] = 1.0
            metrics["fastsafe_get_keys_wall_ms"] = 0.0
            metrics["fastsafe_get_tensor_loop_wall_ms"] = 0.2
        loader, fb = FakeLoader("clip"), FakeFB()
        owners_created.append((loader, fb))
        return ({TENSOR_KEY: FAKE_TENSOR}, loader, fb)

    wiring_mod._fastsafe_load = _fastsafe_load
    record_mode_calls: list = []
    wiring_mod._record_mode = lambda clip, mode, md: record_mode_calls.append(
        (mode, dict(md))
    )
    monkeypatch.setitem(
        sys.modules, "comfymodal_runtime.clip_fast_hydration_wiring", wiring_mod
    )

    observed = _install_fake_loader_selection(monkeypatch)

    if descriptor is _AUTO_DESCRIPTOR:
        descriptor = FakeDescriptor()
    monkeypatch.setattr(rfp, "build_descriptor", lambda *a, **k: descriptor)

    return types.SimpleNamespace(
        resolved_path=resolved,
        ltf_calls=ltf_calls,
        fs_calls=fs_calls,
        owners_created=owners_created,
        owner_calls=owner_calls,
        hydrated_calls=hydrated_calls,
        record_mode_calls=record_mode_calls,
        observed=observed,
        descriptor=descriptor,
    )


def _install_fake_nodes_clip(monkeypatch, *, encode_raises=False):
    nodes_mod = types.ModuleType("nodes")
    clip_calls: list = []
    received_sds: list = []

    def original_load_clip(self, clip_name):
        """Mimics comfy CLIPLoader.load_clip: resolves the path and reads it
        through comfy.utils.load_torch_file (guarded in the fast-path)."""
        import comfy.utils
        import folder_paths

        path = folder_paths.get_full_path("text_encoders", clip_name)
        sd = comfy.utils.load_torch_file(path, safe_load=True, return_metadata=False)
        received_sds.append(sd)
        clip_calls.append(clip_name)
        return (sd,)

    class CLIPLoader:
        load_clip = original_load_clip

    class DualCLIPLoader:
        def load_clip(self, clip_name1, clip_name2):
            return ({"dual": True},)

    class CLIPTextEncode:
        def encode(self, text):
            if encode_raises:
                raise ValueError("encode_boom")
            return (["cond"], ["pooled"])

    mappings = {
        "CLIPLoader": CLIPLoader,
        "DualCLIPLoader": DualCLIPLoader,
        "CLIPTextEncode": CLIPTextEncode,
    }
    nodes_mod.NODE_CLASS_MAPPINGS = mappings
    monkeypatch.setitem(sys.modules, "nodes", nodes_mod)
    return types.SimpleNamespace(mappings=mappings, clip_calls=clip_calls,
                                 received_sds=received_sds)


def _attach_clip_wrappers_manually(monkeypatch, nodes) -> None:
    """Attach the REAL wrappers to the fake node classes via the installer.

    The installer is exercised directly (it wraps all three targets using its
    own sentinel pattern), so every subject code path
    (wrapper -> producer -> guard -> fail-closed) stays under real test.
    """
    assert rcfs.install_request_clip_fastsafe() is True


def test_install_request_clip_fastsafe_installs_all_targets(monkeypatch):
    """FIX 1 regression guard: the installer must complete on fake node
    mappings, wrapping all three targets exactly once with the originals
    preserved as sentinels (historically it raised ValueError from
    ``dict(_WRAPPER_TARGETS)`` over 3-tuples and could never install)."""
    nodes = _install_fake_nodes_clip(monkeypatch)
    try:
        assert rcfs.install_request_clip_fastsafe() is True

        for class_key, method_name in (
            ("CLIPLoader", "load_clip"),
            ("DualCLIPLoader", "load_clip"),
        ):
            wrapped = getattr(nodes.mappings[class_key], method_name)
            # Wrapped exactly once: sentinel present, original NOT wrapped.
            assert getattr(wrapped, rcfs._MARKER, False) is True
            original = getattr(wrapped, rcfs._ORIGINAL_ATTR, None)
            assert callable(original)
            assert getattr(original, rcfs._MARKER, False) is not True
            # Idempotent re-install must not stack a second wrapper.
            assert rcfs.install_request_clip_fastsafe() is True
            assert getattr(nodes.mappings[class_key], method_name) is wrapped

        encode_wrapped = nodes.mappings["CLIPTextEncode"].encode
        assert getattr(encode_wrapped, rcfs._MARKER, False) is True
        encode_original = getattr(encode_wrapped, rcfs._ORIGINAL_ATTR, None)
        assert callable(encode_original)
        assert getattr(encode_original, rcfs._MARKER, False) is not True
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 3: CLIP reachability (THE KEY TEST)
# ---------------------------------------------------------------------------


def test_clip_fastsafe_producer_single_physical_read_serves_sd(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    fakes = _install_clip_fakes(monkeypatch, tmp_path)
    nodes = _install_fake_nodes_clip(monkeypatch)
    _attach_clip_wrappers_manually(monkeypatch, nodes)
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="clip-ok", trace=trace)
        try:
            instance = nodes.mappings["CLIPLoader"]()
            result = instance.load_clip(clip_name="clip.safetensors")

            # Single physical read: exactly one FastSafe transport per path.
            assert fakes.fs_calls == [fakes.resolved_path]
            # The load_torch_file seam engaged: the native reader NEVER ran;
            # the fake original was served the resident CUDA dict instead.
            assert fakes.ltf_calls == []
            assert len(nodes.received_sds) == 1
            served = nodes.received_sds[0]
            assert NATIVE_MARKER not in served
            assert served[TENSOR_KEY] is FAKE_TENSOR
            # Node return shape preserved.
            assert result == (served,)
            # Lifecycle + provenance bookkeeping.
            assert ctx.clip_state == "ready"
            assert fakes.observed == [("clip", "fastsafetensors_direct_gpu", {})]
            assert len(fakes.owner_calls) == 1
            assert fakes.hydrated_calls and fakes.hydrated_calls[0] is served
            assert fakes.record_mode_calls[0][0] == "fastsafe"
            assert ctx.result("clip") is served  # publish_result payload
            # Telemetry window emitted.
            names = trace.names()
            assert "clip_fast_load_start" in names
            assert "clip_fast_load_end" in names
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()

    # Golden-free lane proof: no golden bridge loaded anywhere, and the CLIP
    # fastsafe module neither mentions nor imports golden/model_preload.
    assert "comfymodal_runtime.golden_runtime_bridge" not in sys.modules
    source = inspect.getsource(rcfs)
    assert "golden_runtime_bridge" not in source
    assert "import model_preload" not in source  # docstring mentions are fine


# ---------------------------------------------------------------------------
# Group 4: CLIP negative / fail-closed
# ---------------------------------------------------------------------------


def test_clip_fastsafe_descriptor_failure_falls_back_native(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    fakes = _install_clip_fakes(monkeypatch, tmp_path, descriptor=None)
    nodes = _install_fake_nodes_clip(monkeypatch)
    _attach_clip_wrappers_manually(monkeypatch, nodes)
    try:
        ctx = rfp.begin(request_id="clip-desc-fail")
        try:
            instance = nodes.mappings["CLIPLoader"]()
            result = instance.load_clip(clip_name="clip.safetensors")

            # No transport attempted; the native reader served the original.
            assert fakes.fs_calls == []
            assert len(fakes.ltf_calls) == 1
            assert NATIVE_MARKER in nodes.received_sds[0]
            # Request survives natively.
            assert result == (nodes.received_sds[0],)
            # Sticky terminal reason + released claim.
            assert "clip:clip_descriptor_unavailable" in ctx.terminal_reasons()
            assert ctx.summary()["claims"]["clip"] is False
            # Nothing published; the canonical native fallback observation IS
            # recorded on this path (FIX 2: matches the mid-flight failure
            # path, since the native method runs immediately after).
            assert ctx.result("clip") is None
            assert len(fakes.observed) == 1
            role, arm, kwargs = fakes.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kwargs.get("fallback_attempted") is True
            assert kwargs.get("fallback_loader") == "native_comfy"
            assert kwargs.get("fallback_reason") == "descriptor_unavailable"
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_clip_fastsafe_midflight_failure_closes_owners_and_survives(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    fakes = _install_clip_fakes(monkeypatch, tmp_path, fail_owner_attach=True)
    nodes = _install_fake_nodes_clip(monkeypatch)
    _attach_clip_wrappers_manually(monkeypatch, nodes)
    try:
        ctx = rfp.begin(request_id="clip-mid-fail")
        try:
            instance = nodes.mappings["CLIPLoader"]()
            result = instance.load_clip(clip_name="clip.safetensors")

            # Transport happened, then the (injected) attach failure tripped
            # the fail-closed path: every owner closed safely.
            assert len(fakes.fs_calls) == 1
            loader, fb = fakes.owners_created[0]
            assert loader.closed is True
            assert fb.closed is True
            # Canonical native fallback observation recorded.
            assert len(fakes.observed) == 1
            role, arm, kwargs = fakes.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kwargs.get("fallback_attempted") is True
            # Sticky terminal ledger carries the clip reason.
            assert any(
                "clip_fastsafe_failed:RuntimeError" in reason
                for reason in ctx.terminal_reasons()
            )
            # Partial result never published.
            assert ctx.result("clip") is None
            # Request survives: the original ran and its tuple came back.
            assert result == (nodes.received_sds[-1],)
            assert NATIVE_MARKER in nodes.received_sds[-1]
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 5: forward boundary (CLIPTextEncode.encode wrapper)
# ---------------------------------------------------------------------------


def test_clip_encode_wrapper_marks_forward_window(
    fastsafe_env, monkeypatch, fake_torch
):
    nodes = _install_fake_nodes_clip(monkeypatch)
    _attach_clip_wrappers_manually(monkeypatch, nodes)
    try:
        ctx = rfp.begin(request_id="enc-ok")
        try:
            ctx.mark_clip_loaded()
            instance = nodes.mappings["CLIPTextEncode"]()
            out = instance.encode("hello")
            assert out == (["cond"], ["pooled"])
            assert ctx.clip_state == "critical_done"
            assert ctx.clip_forward_done_event().is_set()
            summary = ctx.summary()
            assert summary["clip_forward_started"] is True
            assert summary["clip_forward_done"] is True
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_clip_encode_wrapper_exception_sets_event_and_terminal(
    fastsafe_env, monkeypatch, fake_torch
):
    nodes = _install_fake_nodes_clip(monkeypatch, encode_raises=True)
    _attach_clip_wrappers_manually(monkeypatch, nodes)
    try:
        ctx = rfp.begin(request_id="enc-boom")
        try:
            ctx.mark_clip_loaded()
            instance = nodes.mappings["CLIPTextEncode"]()
            with pytest.raises(ValueError):
                instance.encode("hello")
            # Event fires even on failure (releases the UNET GPU phase).
            assert ctx.clip_forward_done_event().is_set()
            assert "clip:clip_forward_failed:ValueError" in ctx.terminal_reasons()
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_clip_encode_disengaged_passthrough(fastsafe_env, monkeypatch):
    nodes = _install_fake_nodes_clip(monkeypatch)
    _attach_clip_wrappers_manually(monkeypatch, nodes)
    try:
        # No request context active: pure passthrough, zero interference.
        instance = nodes.mappings["CLIPTextEncode"]()
        assert instance.encode("hello") == (["cond"], ["pooled"])
        assert rfp.current() is None
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 6 fakes: UNET producer world
# ---------------------------------------------------------------------------


def _install_unet_fakes(monkeypatch, tmp_path, *, eligible=(True, "ok"),
                        gate_fail_first=False):
    # folder_paths (node-identical resolution).
    fp_mod = types.ModuleType("folder_paths")
    unet_file = tmp_path / "unet.safetensors"
    unet_file.write_bytes(b"x")
    resolved = str(unet_file)
    fp_mod.get_full_path_or_raise = lambda kind, name: resolved
    fp_mod.get_full_path = lambda kind, name: resolved
    monkeypatch.setitem(sys.modules, "folder_paths", fp_mod)

    # model_preload stand-in (only the request-trace ContextVar is touched).
    mp_mod = types.ModuleType("comfymodal_runtime.model_preload")
    mp_mod._ACTIVE_REQUEST_TRACE = contextvars.ContextVar(
        "fake_r44b_active_request_trace", default=None
    )
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.model_preload", mp_mod)

    prewarmers = _install_fake_checkpoint_prewarm(monkeypatch)

    # unet_fastsafetensors seams.
    fs_mod = types.ModuleType("comfymodal_runtime.unet_fastsafetensors")
    fs_calls: list = []
    owners_created: list = []
    order: list = []

    def _fs_fastsafe_load(path, device_str, metrics):
        order.append("fastsafe_load")
        fs_calls.append(str(path))
        metrics["fastsafe_file_gpu_wall_ms"] = 1.5
        loader, fb = FakeLoader("unet"), FakeFB()
        owners_created.append((loader, fb))
        return ({TENSOR_KEY: FAKE_TENSOR}, loader, fb)

    fs_mod._fs_eligible = lambda node, inputs, extra: tuple(eligible)
    fs_mod._fs_fastsafe_load = _fs_fastsafe_load
    fs_mod._FS_OWNER_ATTR = "_test_fs_owner"

    class _FastsafeOwner:
        def __init__(self, loader, fb):
            self.loader = loader
            self.fb = fb

    fs_mod._FastsafeOwner = _FastsafeOwner
    fs_mod._fs_validate_final = lambda model, dev: {
        "all_params_on_target": True,
        "residual_meta_count": 0,
    }
    monkeypatch.setitem(
        sys.modules, "comfymodal_runtime.unet_fastsafetensors", fs_mod
    )

    observed = _install_fake_loader_selection(monkeypatch)

    # GPU-lane coordination recorders (real module, patched attributes).
    gate_calls: list = []
    race_state = {"fail_first": bool(gate_fail_first)}

    def fake_begin_unet_gpu_phase(request_id="", trace=None, *, reason=""):
        gate_calls.append(reason)
        order.append("gate_begin")
        if race_state["fail_first"]:
            race_state["fail_first"] = False
            raise RuntimeError("unet_gpu_during_clip_critical")
        return coord._UnetToken(None, str(request_id), trace, True, True, 0)

    monkeypatch.setattr(coord, "begin_unet_gpu_phase", fake_begin_unet_gpu_phase)
    monkeypatch.setattr(
        coord,
        "unet_transfer_start",
        lambda token, *, reason="": (order.append("transfer_start"), 12345)[1],
    )
    monkeypatch.setattr(
        coord,
        "unet_transfer_end",
        lambda token, started_ns, *, success=True, reason="": order.append(
            "transfer_end"
        ),
    )

    # Adoption composition stubbed at the module seam.
    adopt_calls: list = []

    def fake_adopt(path, tensors, loader, fb, model_options, device_str, metrics):
        adopt_calls.append(str(path))
        order.append("adopt")
        return (UNET_PATCHER_SENTINEL, 1, 1)

    monkeypatch.setattr(rufs, "_adopt_fastsafe_cuda_storages", fake_adopt)

    # Header descriptor stubbed (keeps the group filesystem-free).
    descriptor = FakeDescriptor(keys=("w",), size_bytes=4096)
    monkeypatch.setattr(rfp, "build_descriptor", lambda *a, **k: descriptor)

    return types.SimpleNamespace(
        resolved_path=resolved,
        order=order,
        gate_calls=gate_calls,
        fs_calls=fs_calls,
        owners_created=owners_created,
        adopt_calls=adopt_calls,
        observed=observed,
        prewarmers=prewarmers,
        descriptor=descriptor,
    )


def _install_fake_nodes_unet(monkeypatch):
    nodes_mod = types.ModuleType("nodes")
    unet_calls: list = []

    class UNETLoader:
        def load_unet(self, unet_name, weight_dtype):
            unet_calls.append((unet_name, weight_dtype))
            return ((NATIVE_MARKER, "unet"),)

    mappings = {"UNETLoader": UNETLoader}
    nodes_mod.NODE_CLASS_MAPPINGS = mappings
    monkeypatch.setitem(sys.modules, "nodes", nodes_mod)
    return types.SimpleNamespace(mappings=mappings, unet_calls=unet_calls)


# ---------------------------------------------------------------------------
# Group 6: UNET reachability
# ---------------------------------------------------------------------------


def test_unet_fastsafe_after_clip_prep_joins_before_gpu_gate(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    fakes = _install_unet_fakes(monkeypatch, tmp_path)
    nodes = _install_fake_nodes_unet(monkeypatch)
    rufs.uninstall_for_tests()
    try:
        assert rufs.install_request_unet_fastsafe() is True
        trace = FakeTrace()
        ctx = rfp.begin(request_id="unet-after-clip", trace=trace)
        try:
            # CLIP fully done: weights ready AND forward critical section left.
            ctx.mark_clip_loaded()
            ctx.mark_clip_forward_start()
            ctx.mark_clip_forward_end()

            # Record when the source-prep fence runs relative to the gate.
            original_join = ctx.join_unet_source_prep

            def joining(*args, **kwargs):
                fakes.order.append("prep_join")
                return original_join(*args, **kwargs)

            ctx.join_unet_source_prep = joining  # instance-level shadow

            instance = nodes.mappings["UNETLoader"]()
            result = instance.load_unet("unet.safetensors", "default")

            # Native loader never executed; adoption pipeline did.
            assert nodes.unet_calls == []
            assert fakes.adopt_calls == [fakes.resolved_path]
            assert len(fakes.fs_calls) == 1
            assert fakes.observed == [("unet", "fastsafetensors", {})]
            assert ctx.result("unet") is UNET_PATCHER_SENTINEL
            assert result == (UNET_PATCHER_SENTINEL,)
            # D15 structural guarantee: the source-prep join happened BEFORE
            # the UNET GPU gate was acquired (gate never held during read/prep),
            # and the FastSafe transfer runs strictly inside the gate.
            order = fakes.order
            assert order.index("prep_join") < order.index("gate_begin")
            assert order.index("gate_begin") < order.index("transfer_start")
            assert order.index("transfer_start") < order.index("fastsafe_load")
            assert order.index("fastsafe_load") < order.index("adopt")
            assert fakes.prewarmers and fakes.prewarmers[0].joined is True
        finally:
            rfp.teardown(ctx)
    finally:
        rufs.uninstall_for_tests()


def test_unet_fastsafe_d15_race_waits_and_retries_once(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    fakes = _install_unet_fakes(monkeypatch, tmp_path, gate_fail_first=True)
    nodes = _install_fake_nodes_unet(monkeypatch)
    rufs.uninstall_for_tests()
    try:
        rufs.install_request_unet_fastsafe()
        ctx = rfp.begin(request_id="unet-race")
        try:
            # Fresh ctx: UNET arrives before CLIP (event unset) -> inline path,
            # but the gate arbiter raises the D15 race signal on first entry.
            # A timer releases the CLIP forward-done event after 50 ms; the
            # wrapper must wait on it and retry exactly once.
            original_join = ctx.join_unet_source_prep

            def joining(*args, **kwargs):
                fakes.order.append("prep_join")
                return original_join(*args, **kwargs)

            ctx.join_unet_source_prep = joining  # instance-level shadow

            timer = threading.Timer(
                0.05, ctx.clip_forward_done_event().set
            )
            timer.start()
            try:
                instance = nodes.mappings["UNETLoader"]()
                result = instance.load_unet("unet.safetensors", "default")
            finally:
                timer.join()

            assert result == (UNET_PATCHER_SENTINEL,)
            assert len(fakes.gate_calls) == 2  # retry happened
            assert fakes.order.count("gate_begin") == 2
            assert fakes.order.index("prep_join") < fakes.order.index("gate_begin")
            assert ctx.result("unet") is UNET_PATCHER_SENTINEL
            assert nodes.unet_calls == []
        finally:
            rfp.teardown(ctx)
    finally:
        rufs.uninstall_for_tests()


def test_unet_fastsafe_case_b_waits_for_continuation_result(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    """R44C repair regression: clip loaded but forward NOT done (case b).

    The wrapper must BOUNDED-WAIT on the continuation's published result.
    ``FastPathRequestContext.result(timeout_s=None)`` returns immediately,
    so an unwaited call would fail-close with ``result_future_empty``,
    fall back to the native loader (double physical load) while the daemon
    continuation still ran the FastSafe pipeline.
    """
    fakes = _install_unet_fakes(monkeypatch, tmp_path)
    nodes = _install_fake_nodes_unet(monkeypatch)
    rufs.uninstall_for_tests()
    try:
        assert rufs.install_request_unet_fastsafe() is True
        trace = FakeTrace()
        ctx = rfp.begin(request_id="unet-case-b", trace=trace)
        try:
            # CLIP weights ready but the forward critical section is still
            # open: forward-done event unset -> case b background path.
            # The graph executor reaches CLIPTextEncode shortly after; a
            # timer simulates the forward completing and releasing the
            # continuation while the wrapper waits on the published result.
            ctx.mark_clip_loaded()
            # Record when the source-prep fence runs relative to the gate
            # (same instance-level shadow the other ordering tests use).
            original_join = ctx.join_unet_source_prep

            def joining(*args, **kwargs):
                fakes.order.append("prep_join")
                return original_join(*args, **kwargs)

            ctx.join_unet_source_prep = joining  # instance-level shadow
            timer = threading.Timer(0.05, ctx.clip_forward_done_event().set)
            timer.start()

            instance = nodes.mappings["UNETLoader"]()
            try:
                result = instance.load_unet("unet.safetensors", "default")
            finally:
                timer.join()

            # The wrapper waited for the continuation and returned its
            # adopted patcher; the native loader never executed; exactly one
            # FastSafe transfer + adoption happened.
            assert result == (UNET_PATCHER_SENTINEL,)
            assert nodes.unet_calls == []
            assert fakes.adopt_calls == [fakes.resolved_path]
            assert len(fakes.fs_calls) == 1
            assert fakes.observed == [("unet", "fastsafetensors", {})]
            assert ctx.result("unet") is UNET_PATCHER_SENTINEL
            # Prep join still precedes the GPU gate inside the continuation.
            order = fakes.order
            assert order.index("prep_join") < order.index("gate_begin")
        finally:
            rfp.teardown(ctx)
    finally:
        rufs.uninstall_for_tests()


def test_unet_fastsafe_unet_first_serial_inline_no_wait(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    fakes = _install_unet_fakes(monkeypatch, tmp_path)
    nodes = _install_fake_nodes_unet(monkeypatch)
    rufs.uninstall_for_tests()
    try:
        rufs.install_request_unet_fastsafe()
        trace = FakeTrace()
        ctx = rfp.begin(request_id="unet-first", trace=trace)
        try:
            # Ordering case c: no clip state at all -> inline WITHOUT waiting
            # on the (unset) forward-done event.
            assert ctx.clip_forward_done_event().is_set() is False
            instance = nodes.mappings["UNETLoader"]()
            result = instance.load_unet("unet.safetensors", "default")

            assert result == (UNET_PATCHER_SENTINEL,)
            assert nodes.unet_calls == []
            assert len(fakes.gate_calls) == 1  # no retry/wait cycle
            assert ctx.result("unet") is UNET_PATCHER_SENTINEL
            # Telemetry records the serial ordering mode.
            ordering_events = [
                md for name, md in trace.events if name == "unet_request_ordering"
            ]
            assert ordering_events and ordering_events[0].get("mode") == (
                "unet_first_serial"
            )
            # Correctness over overlap: the forward-done event was never
            # awaited (still unset at completion).
            assert ctx.clip_forward_done_event().is_set() is False
        finally:
            rfp.teardown(ctx)
    finally:
        rufs.uninstall_for_tests()


def test_unet_fastsafe_ineligible_falls_through_without_fallback_poisoning(
    fastsafe_env, monkeypatch, tmp_path, fake_torch
):
    fakes = _install_unet_fakes(
        monkeypatch, tmp_path, eligible=(False, "family_not_zimage")
    )
    nodes = _install_fake_nodes_unet(monkeypatch)
    rufs.uninstall_for_tests()
    try:
        rufs.install_request_unet_fastsafe()
        ctx = rfp.begin(request_id="unet-ineligible")
        try:
            instance = nodes.mappings["UNETLoader"]()
            result = instance.load_unet("unet.safetensors", "default")

            # Straight to the original; no gate, no transport, no adoption.
            assert result == ((NATIVE_MARKER, "unet"),)
            assert nodes.unet_calls == [("unet.safetensors", "default")]
            assert fakes.gate_calls == []
            assert fakes.fs_calls == []
            assert fakes.adopt_calls == []
            # Ineligible is NOT a fallback: no native_comfy poisoning.
            assert fakes.observed == []
            # Sticky terminal reason records the ineligibility.
            assert any(
                "unet_fastsafe_ineligible:family_not_zimage" in reason
                for reason in ctx.terminal_reasons()
            )
        finally:
            rfp.teardown(ctx)
    finally:
        rufs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 7: gpu_lane_coordination additive hook
# ---------------------------------------------------------------------------


def test_clip_critical_end_callbacks_hook_semantics():
    saved = list(coord._CLIP_CRITICAL_END_CALLBACKS)
    try:
        coord._CLIP_CRITICAL_END_CALLBACKS.clear()
        # Non-callables are silently ignored.
        coord.register_clip_critical_end_callback(None)
        coord.register_clip_critical_end_callback(42)
        assert coord._CLIP_CRITICAL_END_CALLBACKS == []

        fired: list[str] = []

        def boom():
            raise RuntimeError("callback_boom")

        coord.register_clip_critical_end_callback(lambda: fired.append("a"))
        coord.register_clip_critical_end_callback(boom)
        coord.register_clip_critical_end_callback(lambda: fired.append("b"))

        # Firing never raises, even when an individual callback raises.
        coord._fire_clip_critical_end_callbacks()
        assert fired == ["a", "b"]
    finally:
        coord._CLIP_CRITICAL_END_CALLBACKS[:] = saved


# ---------------------------------------------------------------------------
# Group 8: telemetry adaptive snapshot suppression (FIX 5)
# ---------------------------------------------------------------------------


class SnapshotTrace:
    """TeardownDiagnostics-style sink: ``emit`` accepts a ``snapshot``
    parameter whose DEFAULT captures a full process snapshot."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, bool]] = []

    def emit(self, name, phase=None, metadata=None, snapshot=True):
        self.calls.append((str(name), phase, dict(metadata or {}), snapshot))

    def probe_calls(self, name: str):
        return [call for call in self.calls if call[0] == name]


def test_telemetry_suppresses_snapshot_when_supported_and_plain_otherwise():
    # Sink WITH a snapshot parameter -> must receive snapshot=False.
    snap_trace = SnapshotTrace()
    ctx = rfp.begin(request_id="snap-suppress", trace=snap_trace)
    try:
        ctx.telemetry("probe_event", value=1)
        calls = snap_trace.probe_calls("probe_event")
        assert len(calls) == 1
        name, phase, md, snapshot = calls[0]
        assert name == "probe_event"
        assert phase == "execution"
        assert md == {"value": 1}
        assert snapshot is False
    finally:
        rfp.teardown(ctx)

    # RuntimeTrace-style sink (no snapshot param) -> plain call, never raises.
    plain_trace = FakeTrace()
    ctx = rfp.begin(request_id="plain-emit", trace=plain_trace)
    try:
        ctx.telemetry("probe_event", value=2)
        probes = [md for name, md in plain_trace.events if name == "probe_event"]
        assert probes == [{"value": 2}]
    finally:
        rfp.teardown(ctx)
