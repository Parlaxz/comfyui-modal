"""R44I3 ARM A: SAME-DTYPE CLIP residency (BF16 checkpoint -> BF16 live).

The per-request cast_once_fp16 architecture is no longer the production
target.  With ``COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY=1`` the fast arm
pairs the checkpoint dtype with ITSELF in the adoption gate, so the proven
R44F parity lane runs: meta skeleton + assign bind of the served FastSafe
CUDA tensors — ZERO conversion, ZERO second representation, owners retained
until ON_DETACH.

Coverage:
* gate unit: override OFF preserves cast_once_fp16 selection; override ON
  selects same_storage_assign for BF16-under-FP16-policy and records the
  override source;
* producer END-TO-END through the scoped seams with the realistic NESTED
  Qwen fixture: live parameters share storage with staged tensors, BF16
  dtype preserved, owners retained (no early retirement), canonical arm
  observed, full accounting published;
* fail-closed preserved when a served key is absent from the live tree.

All local, CPU-only, no Modal/network/CUDA required.
"""
from __future__ import annotations

import sys
import types

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import request_clip_fastsafe as rcfs
from comfymodal_runtime import request_fastpath as rfp

from tests.test_r44i1_clip_namespace import (  # noqa: E402
    BLOB_KEY,
    EMBED_KEY,
    FakeDescriptor,
    FakeLoader,
    FakeTrace,
    QWEN_KEYS,
    _install_world,
    _staged_values,
)


@pytest.fixture(autouse=True)
def _restore_pkg_submodule_attrs():
    """Same contract as test_r44i1: producer code resolves injected fakes via
    ``from . import <name>``, which BINDS a package attribute on first use.
    Without restoring these attributes, this file's fakes leak into every
    later suite (the R44B loader_selection / wiring pollution class)."""
    import comfymodal_runtime as pkg

    attrs = (
        "clip_fast_hydration",
        "clip_fast_hydration_wiring",
        "loader_selection",
        "model_preload",
        "checkpoint_prewarm",
    )
    saved = {name: getattr(pkg, name, None) for name in attrs}
    yield
    for name, value in saved.items():
        if value is None:
            try:
                delattr(pkg, name)
            except Exception:
                pass
        else:
            try:
                setattr(pkg, name, value)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Gate units
# ---------------------------------------------------------------------------


def _gate_env(monkeypatch, *, residency):
    """Fake comfy.model_management + policy dtype for gate calls."""
    mm_mod = types.ModuleType("comfy.model_management")
    mm_mod.text_encoder_device = lambda: torch.device("cuda:0")
    monkeypatch.setitem(sys.modules, "comfy", types.ModuleType("comfy"))
    monkeypatch.setitem(sys.modules, "comfy.model_management", mm_mod)
    monkeypatch.setattr(rcfs, "_expected_te_dtype_str", lambda: "torch.float16")
    if residency:
        monkeypatch.setenv(rcfs._SAME_DTYPE_RESIDENCY_ENV, "1")
    else:
        monkeypatch.delenv(rcfs._SAME_DTYPE_RESIDENCY_ENV, raising=False)


def _bf16_descriptor():
    staged = _staged_values(torch.bfloat16)
    desc = FakeDescriptor(
        keys=tuple(staged.keys()),
        dtypes={**{k: "BF16" for k in QWEN_KEYS}, BLOB_KEY: "U8"},
        shapes={**QWEN_KEYS, BLOB_KEY: (8,)},
    )
    return staged, desc


def test_gate_without_override_keeps_cast_once_fp16(monkeypatch):
    _gate_env(monkeypatch, residency=False)
    _, desc = _bf16_descriptor()
    ok, reason, details = rcfs._native_adoption_gates(
        ("clip_name",), (), {"clip_name": "qwen_tiny.safetensors"}, [desc]
    )
    assert ok is True, reason
    assert details["adoption_mode"] == "cast_once_fp16"
    assert details["expected_te_dtype"] == "torch.float16"
    assert details["native_policy_te_dtype"] == "torch.float16"
    assert details["effective_live_dtype"] == "torch.float16"
    assert details["same_dtype_residency_override"] == 0
    assert "same_dtype_residency" not in details


def test_gate_with_override_selects_same_storage_assign(monkeypatch):
    _gate_env(monkeypatch, residency=True)
    _, desc = _bf16_descriptor()
    ok, reason, details = rcfs._native_adoption_gates(
        ("clip_name",), (), {"clip_name": "qwen_tiny.safetensors"}, [desc]
    )
    assert ok is True, reason
    assert details["adoption_mode"] == "same_storage_assign"
    assert details["checkpoint_dtype"] == "BF16"
    assert details["expected_te_dtype"] == "torch.bfloat16"
    # Policy vs effective residency recorded SEPARATELY (R44I3 contract).
    assert details["native_policy_te_dtype"] == "torch.float16"
    assert details["effective_live_dtype"] == "torch.bfloat16"
    assert details["same_dtype_residency_override"] == 1
    assert details["expected_te_dtype_source"] == "same_dtype_residency_override"
    assert details["same_dtype_residency"] is True


def test_gate_override_still_rejects_non_uniform_and_quant(monkeypatch):
    _gate_env(monkeypatch, residency=True)
    _, desc = _bf16_descriptor()
    mixed = FakeDescriptor(
        keys=tuple(QWEN_KEYS) + (BLOB_KEY,),
        dtypes={**{k: "BF16" for k in QWEN_KEYS}, BLOB_KEY: "U8",
                EMBED_KEY: "F16"},
        shapes={**QWEN_KEYS, BLOB_KEY: (8,)},
    )
    ok, reason, _ = rcfs._native_adoption_gates(
        ("clip_name",), (), {"clip_name": "x"}, [mixed]
    )
    assert ok is False and reason.startswith("non_uniform_dtype")


def test_runtime_env_generic_v2_namespace_passthrough(monkeypatch):
    """R44I3 bug-class fix: a NEW COMFYMODAL_V2_* flag present in the deploy
    environment must cross the Modal class-env boundary WITHOUT a per-key
    entry in modal_app._runtime_env (the R44D/R44F/R44I3 silent-drop class).
    """
    # Importing modal_app transitively loads helper modules (including
    # golden_runtime_bridge) into sys.modules; R44B asserts that bridge is
    # NEVER loaded by the request fast path, so drop exactly that litter
    # (and only if THIS test introduced it) afterwards.
    _bridge = "comfymodal_runtime.golden_runtime_bridge"
    _bridge_preloaded = _bridge in sys.modules
    try:
        modal_app = pytest.importorskip("comfymodal_runtime.modal_app")
        monkeypatch.setenv("COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY", "1")
        monkeypatch.setenv("COMFYMODAL_V2_R44I3_PASSTHROUGH_CANARY", "7")
        env = modal_app._runtime_env(None)
        assert env.get("COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY") == "1"
        assert env.get("COMFYMODAL_V2_R44I3_PASSTHROUGH_CANARY") == "7"
        # Explicit defaults still apply for keys absent from the environment.
        monkeypatch.delenv("COMFYMODAL_V2_REQUEST_FASTSAFE", raising=False)
        env2 = modal_app._runtime_env(None)
        assert env2.get("COMFYMODAL_V2_REQUEST_FASTSAFE") == "0"
    finally:
        if not _bridge_preloaded:
            sys.modules.pop(_bridge, None)


# ---------------------------------------------------------------------------
# ARM B: FP16 volume twin (preconverted once, FP16->FP16 parity bind)
# ---------------------------------------------------------------------------


def test_producer_fp16_volume_twin_same_storage(monkeypatch, tmp_path):
    """Twin present + flag on -> producer serves the TWIN path, gate selects
    same_storage_assign NATURALLY (F16 policy parity), zero-copy bind."""
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP_NATIVE_ADOPT, "1")
    monkeypatch.delenv(rcfs._SAME_DTYPE_RESIDENCY_ENV, raising=False)
    monkeypatch.setenv(rcfs._FP16_VOLUME_TWIN_ENV, "1")
    world = _install_world(monkeypatch, tmp_path)

    twin_path = str(tmp_path / "qwen_tiny.fp16.safetensors")
    (tmp_path / "qwen_tiny.fp16.safetensors").write_bytes(b"x")

    wiring = sys.modules["comfymodal_runtime.clip_fast_hydration_wiring"]
    f16_tensors = _staged_values(torch.float16)

    def _twin_load(path, metrics=None):
        world.fs_calls.append(str(path))
        tensors = f16_tensors if str(path) == twin_path else _staged_values(torch.bfloat16)
        world.tensors_by_path[str(path)] = tensors
        loader, fb = FakeLoader(), FakeLoader()
        world.owners_created.append((loader, fb))
        return (dict(tensors), loader, fb)

    wiring._fastsafe_load = _twin_load

    def _desc_for(role, path, **k):
        dtypes = {**{key: "F16" for key in QWEN_KEYS}, BLOB_KEY: "U8"}
        return FakeDescriptor(
            keys=tuple(QWEN_KEYS) + (BLOB_KEY,),
            dtypes=dtypes,
            shapes={**QWEN_KEYS, BLOB_KEY: (8,)},
        )

    monkeypatch.setattr(rfp, "build_descriptor", _desc_for)

    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44i3-armB", trace=trace)
        try:
            result = __import__("nodes").NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                clip_name="qwen_tiny.safetensors"
            )
            clip = result[0]
            csm = clip.cond_stage_model
            served = world.tensors_by_path[twin_path]

            # The TWIN was transported, not the BF16 original.
            assert world.fs_calls == [twin_path]

            emb = None
            for name_, mod in csm.named_modules():
                if isinstance(mod, torch.nn.Embedding) and name_.endswith("embed_tokens"):
                    emb = mod.weight
                    break
            assert emb is not None
            assert emb.dtype == torch.float16
            assert emb.data_ptr() == served[EMBED_KEY].data_ptr()

            start = trace.payloads("clip_fast_load_start")[0]
            assert start["adoption_mode"] == "same_storage_assign"
            assert start["checkpoint_dtype"] == "F16"
            assert start["native_policy_dtype"] == "torch.float16"
            assert start["effective_live_dtype"] == "torch.float16"
            assert start["same_dtype_residency_override"] == 0
            assert any(
                name_ == "clip_fp16_volume_twin_selected" for name_, _md in trace.events
            )
            end = trace.payloads("clip_fast_load_end")[0]
            assert end["bind_mode"] == "same_storage"
            assert end["owner_retained"] is True
            live_dtypes = set(end["parameter_dtypes"])
            assert "torch.float16" in live_dtypes
            assert "torch.bfloat16" not in live_dtypes
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_producer_twin_missing_falls_back_to_original(monkeypatch, tmp_path):
    """No twin file -> original BF16 path used; with residency override off
    the gate selects cast_once_fp16 exactly as before ARM B existed."""
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP_NATIVE_ADOPT, "1")
    monkeypatch.delenv(rcfs._SAME_DTYPE_RESIDENCY_ENV, raising=False)
    monkeypatch.setenv(rcfs._FP16_VOLUME_TWIN_ENV, "1")
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44i3-armB-miss")
        try:
            __import__("nodes").NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                clip_name="qwen_tiny.safetensors"
            )
            assert world.fs_calls == [world.resolved]
            assert not str(world.fs_calls[0]).endswith(".fp16.safetensors")
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Producer end-to-end (parity arm, nested fixture)
# ---------------------------------------------------------------------------


def _parity_flags(monkeypatch):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP_NATIVE_ADOPT, "1")
    monkeypatch.setenv(rcfs._SAME_DTYPE_RESIDENCY_ENV, "1")


def test_producer_same_dtype_residency_end_to_end(monkeypatch, tmp_path):
    _parity_flags(monkeypatch)
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44i3-armA", trace=trace)
        try:
            result = __import__("nodes").NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                clip_name="qwen_tiny.safetensors"
            )
            clip = result[0]
            csm = clip.cond_stage_model
            served = world.tensors_by_path[world.resolved]

            # Single physical read; guarded seam served the staged tensors.
            assert world.fs_calls == [world.resolved]
            assert world.ltf_calls == []

            # ZERO-COPY same-storage proof: the live parameter IS the staged
            # tensor object (assign bind), BF16 dtype preserved.
            emb_name, emb = None, None
            for name, mod in csm.named_modules():
                if isinstance(mod, torch.nn.Embedding) and name.endswith("embed_tokens"):
                    emb_name, emb = name, mod.weight
                    break
            assert emb is not None, f"embed_tokens not found under {emb_name}"
            staged_emb = served[EMBED_KEY]
            assert emb.dtype == torch.bfloat16
            assert emb.data_ptr() == staged_emb.data_ptr()

            start = trace.payloads("clip_fast_load_start")[0]
            assert start["adoption_mode"] == "same_storage_assign"
            assert start["expected_runtime_dtype"] == "torch.bfloat16"
            # R44I3 telemetry triple: policy vs effective vs override.
            assert start["native_policy_dtype"] == "torch.float16"
            assert start["effective_live_dtype"] == "torch.bfloat16"
            assert start["same_dtype_residency_override"] == 1

            end = trace.payloads("clip_fast_load_end")[0]
            assert end["ok"] is True
            assert end["bind_mode"] == "same_storage"
            assert end["adoption_mode"] == "same_storage_assign"
            assert end["sampled_same_storage_count"] == len(QWEN_KEYS)
            # Exactly ONE non-same-storage entry: the tokenizer blob (U8),
            # which is never a live parameter.
            assert end["non_same_storage_count"] == 1
            # Owners RETAINED in parity mode: staging IS the live weights.
            assert end["owner_retained"] is True
            # R44I3: ctor-owned logit_scale tolerated + reported (outside
            # the derived native recipient), never fatal.
            assert end["parameter_count"] == len(QWEN_KEYS) + 1
            # No stale FP16 materialization: meta skeleton means ZERO FP16
            # parameters exist; weights are BF16 (+ the FP32 ctor constant).
            live_dtypes = set(end["parameter_dtypes"])
            assert "torch.bfloat16" in live_dtypes
            assert "torch.float16" not in live_dtypes

            # Canonical arm observed WITHOUT fallback; result published.
            assert world.observed == [("clip", "fastsafetensors_direct_gpu", {})]
            assert ctx.result("clip") is clip

            # No early source release ran (retirement is cast-mode-only).
            loader, fb = world.owners_created[0]
            assert loader.release_calls == 0 and fb.release_calls == 0
            assert loader.closed is False and fb.closed is False
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_producer_parity_missing_key_still_fails_closed(monkeypatch, tmp_path):
    _parity_flags(monkeypatch)
    world = _install_world(monkeypatch, tmp_path)
    wiring = sys.modules["comfymodal_runtime.clip_fast_hydration_wiring"]

    # Parity-mode fail-closed shape: the served dict LACKS one checkpoint
    # key the live tree defines.  With a meta skeleton the corresponding
    # parameter can never be assigned -> meta_residual -> fail closed.
    dropped = "model.norm.weight"
    base_tensors = {
        k: v for k, v in _staged_values(torch.bfloat16).items() if k != dropped
    }

    def _broken_load(path, metrics=None):
        world.fs_calls.append(str(path))
        world.tensors_by_path[str(path)] = dict(base_tensors)
        loader, fb = FakeLoader(), FakeLoader()
        world.owners_created.append((loader, fb))
        return (dict(base_tensors), loader, fb)

    wiring._fastsafe_load = _broken_load
    broken_desc = FakeDescriptor(
        keys=tuple(base_tensors.keys()),
        dtypes={**{k: "BF16" for k in QWEN_KEYS if k != dropped}, BLOB_KEY: "U8"},
        shapes={**{k: s for k, s in QWEN_KEYS.items() if k != dropped},
                BLOB_KEY: (8,)},
    )
    monkeypatch.setattr(rfp, "build_descriptor", lambda *a, **k: broken_desc)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44i3-armA-miss")
        try:
            result = __import__("nodes").NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                clip_name="qwen_tiny.safetensors"
            )
            assert len(world.fs_calls) == 1
            loader, fb = world.owners_created[0]
            assert loader.closed is True and fb.closed is True
            role, arm, kw = world.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kw.get("fallback_attempted") is True
            reasons = " | ".join(ctx.terminal_reasons())
            assert "clip_fastsafe_failed:RuntimeError" in reasons
            assert ctx.result("clip") is None
            assert isinstance(result, tuple) and len(result) == 1
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()
