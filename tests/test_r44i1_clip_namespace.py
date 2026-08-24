"""R44I1: NATIVE CLIP checkpoint->live KEY-NAMESPACE reconciliation.

Root cause under test (R44H3 remote failure ``missing_key:model.embed_tokens.weight``):

* Native Comfy does NOT rename Qwen/Llama text-encoder keys.  The staged
  dict reaches ``<recipient>.load_state_dict(sd, strict=False)`` VERBATIM,
  and the recipient sits BELOW wrapper prefixes:
  ``cond_stage_model.transformer`` (``llama.Qwen3_4B``) -> child ``model``
  (``Llama2_``).  Outer ``cond_stage_model.state_dict()`` names are
  therefore ``transformer.model.<checkpoint key>``.
* The former R44H1 validator looked raw staged keys up directly in the
  OUTER namespace and failed closed on every real Qwen checkpoint.
* The R44H1/H3 local fixtures were FLAT (staged key == outer state_dict
  key), so the mismatch could never reproduce locally.

Coverage:

* REAL pinned ``comfy.text_encoders.llama.Qwen3_4B`` (tiny dims, CPU) —
  live namespace proof + full cast-once validation through the REAL
  ``load_state_dict(assign=False)`` BF16->FP16 conversion path;
* deterministic recipient derivation (unique / missing / AMBIGUOUS
  fail-closed);
* unbound-parameter policy: fatal INSIDE the derived recipient,
  native-legitimate (counted, reported) OUTSIDE it (constant-init
  ``logit_scale`` pattern);
* producer END-TO-END through the scoped seams with a REALISTIC NESTED
  fixture (authentic Qwen key names, real delegation chain
  ``CLIP.load_sd -> csm.load_sd -> transformer.load_state_dict``) plus the
  R44I1 telemetry contract (mapping mode, direct/remapped/alias counts,
  bounded mapping samples including ``model.embed_tokens.weight``).

All local, CPU-only, no Modal/network/CUDA required.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import request_clip_fastsafe as rcfs
from comfymodal_runtime import request_fastpath as rfp

# ---------------------------------------------------------------------------
# Authentic Qwen3-4B checkpoint key material (R44E: 398 tensors, uniform
# BF16, no transform markers, lm_head absent by native config lm_head=False).
# Representative subset covering embedding / attention / MLP / normalization
# / final norm.  No output/head key exists; no tied aliases exist.
# ---------------------------------------------------------------------------

EMBED_KEY = "model.embed_tokens.weight"

QWEN_KEYS: dict[str, tuple[int, ...]] = {
    EMBED_KEY: (16, 8),
    "model.layers.0.self_attn.q_proj.weight": (8, 8),
    "model.layers.0.self_attn.k_proj.weight": (4, 8),
    "model.layers.0.self_attn.v_proj.weight": (4, 8),
    "model.layers.0.self_attn.o_proj.weight": (8, 8),
    "model.layers.0.mlp.gate_proj.weight": (16, 8),
    "model.layers.0.mlp.up_proj.weight": (16, 8),
    "model.layers.0.mlp.down_proj.weight": (8, 16),
    "model.layers.0.input_layernorm.weight": (8,),
    "model.layers.0.post_attention_layernorm.weight": (8,),
    "model.norm.weight": (8,),
}
BLOB_KEY = "spiece_model"

_ST_TO_SAFETENSORS = {
    torch.float32: "F32",
    torch.float16: "F16",
    torch.bfloat16: "BF16",
}


def _staged_values(dtype: torch.dtype) -> dict[str, torch.Tensor]:
    tensors = {
        key: torch.full(shape, 0.5 + 0.25 * i, dtype=dtype)
        for i, (key, shape) in enumerate(QWEN_KEYS.items())
    }
    tensors[BLOB_KEY] = torch.zeros(8, dtype=torch.uint8)
    return tensors


# ---------------------------------------------------------------------------
# Realistic NESTED module tree mirroring the pinned delegation chain:
# CLIP.load_sd -> cond_stage_model.load_sd -> self.transformer.load_state_dict
# (SDClipModel wrapper prefix "transformer." + Qwen3_4B child "model.").
# ---------------------------------------------------------------------------


class _W(torch.nn.Module):
    """Leaf module exposing exactly one ``weight`` parameter."""

    def __init__(self, shape, dtype, device):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.empty(shape, dtype=dtype, device=device))


class _Attn(torch.nn.Module):
    def __init__(self, dtype, device):
        super().__init__()
        self.q_proj = _W((8, 8), dtype, device)
        self.k_proj = _W((4, 8), dtype, device)
        self.v_proj = _W((4, 8), dtype, device)
        self.o_proj = _W((8, 8), dtype, device)


class _MLP(torch.nn.Module):
    def __init__(self, dtype, device):
        super().__init__()
        self.gate_proj = _W((16, 8), dtype, device)
        self.up_proj = _W((16, 8), dtype, device)
        self.down_proj = _W((8, 16), dtype, device)


class _Block(torch.nn.Module):
    def __init__(self, dtype, device):
        super().__init__()
        self.self_attn = _Attn(dtype, device)
        self.mlp = _MLP(dtype, device)
        self.input_layernorm = _W((8,), dtype, device)
        self.post_attention_layernorm = _W((8,), dtype, device)


class _LlamaLike(torch.nn.Module):
    """Mirrors llama.Llama2_: embed_tokens / layers / norm (lm_head=False)."""

    def __init__(self, dtype, device):
        super().__init__()
        self.embed_tokens = torch.nn.Embedding(16, 8).to(
            dtype=dtype, device=device
        )
        self.layers = torch.nn.ModuleList([_Block(dtype, device)])
        self.norm = _W((8,), dtype, device)


class _QwenLike(torch.nn.Module):
    """Mirrors llama.Qwen3_4B: the ACTUAL load_state_dict recipient."""

    def __init__(self, dtype, device):
        super().__init__()
        self.model = _LlamaLike(dtype, device)

    def load_sd(self, sd):
        return self.load_state_dict(
            sd, strict=False, assign=getattr(self, "can_assign_sd", False)
        )


class _CSM(torch.nn.Module):
    """Mirrors SDClipModel nesting: wrapper prefix + constant-init
    logit_scale that native load_sd NEVER sources from checkpoints."""

    def __init__(self, dtype, device):
        super().__init__()
        self.transformer = _QwenLike(dtype, device)
        self.logit_scale = torch.nn.Parameter(torch.tensor(4.6055))

    def load_sd(self, sd):
        return self.transformer.load_sd(sd)


class _FakePatcher:
    def __init__(self, model):
        self.model = model
        self.load_device = torch.device("cuda:0")
        self.offload_device = torch.device("cpu")
        self.callbacks: dict[str, list] = {}

    def is_dynamic(self):
        # R44I3 remote fidelity: pinned comfy CLIP.__init__ builds a
        # CoreModelPatcher whose is_dynamic() is True (model_patcher.py),
        # so native CLIP.load_sd sprays can_assign_sd=True unless the
        # cast-once seam pins it False for the load window.
        return True

    def add_callback(self, call_type, callback):
        self.callbacks.setdefault(call_type, []).append(callback)

    def get_all_callbacks(self, call_type):
        return list(self.callbacks.get(call_type, []))

    def detach(self, unpatch_all=True):
        for callback in self.get_all_callbacks("on_detach_after"):
            callback(self, unpatch_all)


class FakeTrace:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, name, phase=None, metadata=None, **extra):
        md = dict(metadata or {})
        md.update(extra)
        self.events.append((str(name), md))

    def payloads(self, name: str) -> list[dict]:
        return [md for evt, md in self.events if evt == name]


class FakeLoader:
    def __init__(self) -> None:
        self.closed = False
        self.release_calls = 0
        self.purge_requests: list[bool] = []

    def close(self) -> None:
        self.closed = True

    def release_storage(self, *, purge_allocator: bool = False) -> None:
        self.purge_requests.append(bool(purge_allocator))
        self.release_calls += 1


class FakeFB(FakeLoader):
    pass


class FakeDescriptor:
    def __init__(self, *, keys, dtypes, shapes, size_bytes=4096, metadata=None):
        self.role = "clip"
        self.keys = tuple(keys)
        self.shapes = dict(shapes)
        self.dtypes = dict(dtypes)
        self.metadata = dict(metadata or {})
        self.size_bytes = int(size_bytes)
        self.target_device = "cuda:0"

    def fresh(self) -> bool:
        return True


def _fake_torch(monkeypatch):
    mod = types.ModuleType("torch")
    for name in dir(torch):
        if name.startswith("__"):
            continue
        try:
            mod.__dict__[name] = getattr(torch, name)
        except Exception:
            pass
    mod.cuda = types.SimpleNamespace(
        current_device=lambda: 0,
        is_available=lambda: True,
        memory_allocated=lambda: 4096,
        memory_reserved=lambda: 8192,
        max_memory_allocated=lambda: 8192,
        max_memory_reserved=lambda: 16384,
        reset_peak_memory_stats=lambda: None,
        empty_cache=lambda: None,
        synchronize=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "torch", mod)
    return mod


@pytest.fixture(autouse=True)
def _restore_pkg_submodule_attrs():
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


def _install_world(monkeypatch, tmp_path, *, drop_live_key: bool = False):
    """Producer harness with a REALISTIC NESTED Qwen fixture."""
    world = types.SimpleNamespace(
        resolved=str(tmp_path / "qwen_tiny.safetensors"),
        fs_calls=[],
        ltf_calls=[],
        observed=[],
        owners_created=[],
        tensors_by_path={},
        built_clips=[],
        mm_load_calls=[],
        current_loaded=[],
    )
    (tmp_path / "qwen_tiny.safetensors").write_bytes(b"x")

    fp_mod = types.ModuleType("folder_paths")
    fp_mod.get_full_path = lambda kind, name: world.resolved
    monkeypatch.setitem(sys.modules, "folder_paths", fp_mod)

    _fake_torch(monkeypatch)

    comfy_mod = types.ModuleType("comfy")
    utils_mod = types.ModuleType("comfy.utils")

    def load_torch_file(ckpt_path, *args, **kwargs):
        world.ltf_calls.append(str(ckpt_path))
        return {"__native_read__": str(ckpt_path)}

    utils_mod.load_torch_file = load_torch_file

    sd_mod = types.ModuleType("comfy.sd")

    class _NativeLoadSD:
        def __call__(self, clip_self, sd, full_model=False):
            can_assign = clip_self.patcher.is_dynamic()
            for m in clip_self.cond_stage_model.modules():
                m.can_assign_sd = can_assign
            return clip_self.cond_stage_model.load_sd(sd)

    class CLIP:
        load_sd = _NativeLoadSD()

    sd_mod.CLIP = CLIP

    mm_mod = types.ModuleType("comfy.model_management")

    mm_mod.text_encoder_device = lambda: torch.device("cuda:0")
    mm_mod.text_encoder_dtype = lambda device=None: torch.float16
    mm_mod.text_encoder_initial_device = (
        lambda load_device, offload_device, model_size=0: torch.device("meta")
    )

    def load_models_gpu(models, memory_required=0, force_patch_weights=False,
                        force_full_load=False, **kw):
        world.mm_load_calls.append((tuple(models), force_full_load))
        for m in models:
            world.current_loaded.append(types.SimpleNamespace(model=m))

    mm_mod.load_models_gpu = load_models_gpu
    mm_mod.current_loaded_models = world.current_loaded

    comfy_mod.utils = utils_mod
    comfy_mod.sd = sd_mod
    comfy_mod.model_management = mm_mod
    monkeypatch.setitem(sys.modules, "comfy", comfy_mod)
    monkeypatch.setitem(sys.modules, "comfy.utils", utils_mod)
    monkeypatch.setitem(sys.modules, "comfy.sd", sd_mod)
    monkeypatch.setitem(sys.modules, "comfy.model_management", mm_mod)

    pe_mod = types.ModuleType("comfy.patcher_extension")

    class CallbacksMP:
        ON_DETACH = "on_detach_after"

    pe_mod.CallbacksMP = CallbacksMP
    comfy_mod.patcher_extension = pe_mod
    monkeypatch.setitem(sys.modules, "comfy.patcher_extension", pe_mod)

    cfh_mod = types.ModuleType("comfymodal_runtime.clip_fast_hydration")
    cfh_mod.MODE_FASTSAFE = "fastsafetensors_direct_gpu"
    cfh_mod.OWNER_ATTR = "_r44i1_test_owners"
    cfh_mod._TOKENIZER_BLOB_KEYS = (BLOB_KEY,)

    def owner_attach(clip, loader, fb):
        owners = getattr(clip.patcher, cfh_mod.OWNER_ATTR, None)
        if owners is None:
            owners = []
            setattr(clip.patcher, cfh_mod.OWNER_ATTR, owners)
        owners.append(types.SimpleNamespace(loader=loader, fb=fb))

    def release_owner(clip):
        patcher = getattr(clip, "patcher", None)
        owners = getattr(patcher, cfh_mod.OWNER_ATTR, None) if patcher else None
        if not owners:
            return False
        for owner in owners:
            for component in (owner.loader, owner.fb):
                if component is not None:
                    component.close()
        delattr(patcher, cfh_mod.OWNER_ATTR)
        return True

    def retire_source_owners(owners, *, bf16_bytes=0, fp32_bytes=0, clip=None):
        retired = 0
        for owner in list(owners):
            components = (
                tuple(owner)
                if isinstance(owner, (tuple, list))
                else (owner.loader, owner.fb)
            )
            ok = True
            for component in components:
                if component is None:
                    continue
                try:
                    component.release_storage(purge_allocator=False)
                except Exception:
                    ok = False
            retired += 1 if ok else 0
        all_ok = len(owners) > 0 and retired == len(owners)
        if all_ok:
            owners.clear()
            patcher = getattr(clip, "patcher", None)
            attached = (
                getattr(patcher, cfh_mod.OWNER_ATTR, None)
                if patcher is not None
                else None
            )
            if isinstance(attached, list):
                attached.clear()
                try:
                    delattr(patcher, cfh_mod.OWNER_ATTR)
                except Exception:
                    pass
        return {
            "ok": all_ok,
            "owners_retired": retired,
            "owners_failed": len(owners),
            "owner_bytes_before": int(max(0, bf16_bytes)),
            "per_owner": [],
        }

    cfh_mod.owner_attach = owner_attach
    cfh_mod.release_owner = release_owner
    cfh_mod.retire_source_owners = retire_source_owners
    cfh_mod.mark_clip_hydrated = lambda clip: None
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.clip_fast_hydration", cfh_mod)

    wiring_mod = types.ModuleType("comfymodal_runtime.clip_fast_hydration_wiring")

    def _fastsafe_load(path, metrics=None):
        world.fs_calls.append(str(path))
        tensors = _staged_values(torch.bfloat16)
        world.tensors_by_path[str(path)] = tensors
        if metrics is not None:
            metrics["fastsafe_setup_wall_ms"] = 0.1
            metrics["fastsafe_copy_wall_ms"] = 1.0
            metrics["fastsafe_get_keys_wall_ms"] = 0.0
            metrics["fastsafe_get_tensor_loop_wall_ms"] = 0.2
        loader, fb = FakeLoader(), FakeFB()
        world.owners_created.append((loader, fb))
        return (tensors, loader, fb)

    wiring_mod._fastsafe_load = _fastsafe_load
    wiring_mod._record_mode = lambda clip, mode, md: None
    monkeypatch.setitem(
        sys.modules, "comfymodal_runtime.clip_fast_hydration_wiring", wiring_mod
    )

    ls_mod = types.ModuleType("comfymodal_runtime.loader_selection")
    ls_mod.record_observed = lambda role, arm, **kw: world.observed.append(
        (role, arm, dict(kw))
    )
    ls_mod.normalize_observed = lambda role, arm: (
        "native_comfy" if arm == "native" else arm
    )
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.loader_selection", ls_mod)

    nodes_mod = types.ModuleType("nodes")

    def build_fake_clip():
        import comfy.model_management as comfy_mm
        import comfy.sd
        import comfy.utils

        out = comfy.utils.load_torch_file(world.resolved, safe_load=True)
        initial_device = comfy_mm.text_encoder_initial_device(
            torch.device("cuda:0"), torch.device("cpu"), 1024
        )
        csm = _CSM(torch.float16, initial_device)
        clip = types.SimpleNamespace()
        clip.cond_stage_model = csm
        clip.patcher = _FakePatcher(csm)
        clip.tokenizer = types.SimpleNamespace(name="fake-tokenizer")
        world.built_clips.append(clip)
        comfy.sd.CLIP.load_sd(clip, out)
        return (clip,)

    class CLIPLoader:
        def load_clip(self, clip_name, type="stable_diffusion", device="default"):
            return build_fake_clip()

    nodes_mod.NODE_CLASS_MAPPINGS = {
        "CLIPLoader": CLIPLoader,
        "CLIPTextEncode": type("CLIPTextEncode", (), {"encode": staticmethod(lambda text: ([text], []))}),
    }
    monkeypatch.setitem(sys.modules, "nodes", nodes_mod)

    st_name = "BF16"
    world.descriptor = FakeDescriptor(
        keys=tuple(QWEN_KEYS.keys()) + (BLOB_KEY,),
        dtypes={**{k: st_name for k in QWEN_KEYS}, BLOB_KEY: "U8"},
        shapes={**QWEN_KEYS, BLOB_KEY: (8,)},
    )
    monkeypatch.setattr(rfp, "build_descriptor", lambda *a, **k: world.descriptor)
    monkeypatch.setattr(rcfs, "_current_cuda_device_str", lambda: "cpu")
    return world


# ---------------------------------------------------------------------------
# Recipient derivation unit behavior
# ---------------------------------------------------------------------------


def _nested_clip():
    csm = _CSM(torch.float16, torch.device("cpu"))
    return types.SimpleNamespace(
        cond_stage_model=csm, patcher=object(), tokenizer=object()
    )


def test_recipient_resolution_nested_unique():
    clip = _nested_clip()
    csm = clip.cond_stage_model
    candidates = rcfs._resolve_loadsd_recipients(csm, set(QWEN_KEYS))
    assert len(candidates) == 1
    prefix, name, module = candidates[0]
    assert prefix == "transformer."
    assert name == "transformer"
    assert module is csm.transformer


def test_recipient_resolution_flat_root():
    class Flat(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.zeros(4, 3))

    flat = Flat()
    candidates = rcfs._resolve_loadsd_recipients(flat, {"weight"})
    assert len(candidates) == 1
    prefix, name, module = candidates[0]
    assert prefix == ""
    assert module is flat


def test_missing_key_fail_closed_realistic_name():
    clip = _nested_clip()
    served = _staged_values(torch.bfloat16)
    served[EMBED_KEY + "_renamed"] = served.pop(EMBED_KEY)
    desc = FakeDescriptor(
        keys=tuple(served.keys()),
        dtypes={k: "BF16" for k in QWEN_KEYS},
        shapes={**QWEN_KEYS},
    )
    desc.shapes[EMBED_KEY + "_renamed"] = QWEN_KEYS[EMBED_KEY]
    with pytest.raises(RuntimeError, match=r"^missing_key:model\.embed_tokens"):
        rcfs._validate_cast_once_bind(
            clip, [served], [desc], "torch.float16", "cpu"
        )


def test_ambiguous_recipient_fails_closed():
    class Twin(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.a = _QwenLike(torch.float16, torch.device("cpu"))
            self.b = _QwenLike(torch.float16, torch.device("cpu"))

    clip = types.SimpleNamespace(
        cond_stage_model=Twin(), patcher=object(), tokenizer=object()
    )
    served = {k: torch.full(s, 1.0, dtype=torch.bfloat16) for k, s in QWEN_KEYS.items()}
    desc = FakeDescriptor(
        keys=tuple(QWEN_KEYS),
        dtypes={k: "BF16" for k in QWEN_KEYS},
        shapes=dict(QWEN_KEYS),
    )
    with pytest.raises(RuntimeError, match=r"^ambiguous_live_key:model\.embed_tokens\.weight:2$"):
        rcfs._validate_cast_once_bind(
            clip, [served], [desc], "torch.float16", "cpu"
        )


def test_unbound_parameter_inside_recipient_fails_closed():
    clip = _nested_clip()
    csm = clip.cond_stage_model
    # A random-init leftover INSIDE the recipient namespace.
    csm.transformer.model.unused_head = torch.nn.Parameter(
        torch.zeros((4,), dtype=torch.float16)
    )
    served = {k: torch.full(s, 1.0, dtype=torch.bfloat16) for k, s in QWEN_KEYS.items()}
    # Simulate the completed native single cast so only the leftover fails.
    with torch.no_grad():
        for k, t in csm.transformer.state_dict().items():
            if k in served:
                t.copy_(served[k].to(torch.float16))
    desc = FakeDescriptor(
        keys=tuple(QWEN_KEYS),
        dtypes={k: "BF16" for k in QWEN_KEYS},
        shapes=dict(QWEN_KEYS),
    )
    with pytest.raises(RuntimeError, match=r"^unbound_parameter:transformer\.model\.unused_head$"):
        rcfs._validate_cast_once_bind(
            clip, [served], [desc], "torch.float16", "cpu"
        )


# ---------------------------------------------------------------------------
# REAL pinned Qwen3_4B (tiny dims) — live namespace + full cast-once proof
# ---------------------------------------------------------------------------


def _real_llama():
    try:
        comfy_root = str(Path(__file__).resolve().parents[3])
        if comfy_root not in sys.path:
            sys.path.insert(0, comfy_root)
        import comfy.ops
        import comfy.text_encoders.llama as llama

        return llama, comfy.ops
    except Exception:
        return None, None


def test_real_pinned_qwen3_4b_live_namespace_matches_checkpoint():
    llama, ops = _real_llama()
    if llama is None:
        pytest.skip("real pinned comfy.text_encoders.llama unavailable")
    cfg = dict(
        vocab_size=64,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=1,
        num_attention_heads=1,
        num_key_value_heads=1,
    )
    model = llama.Qwen3_4B(
        cfg, dtype=torch.float16, device="cpu", operations=ops.disable_weight_init()
    )
    keys = list(model.state_dict().keys())
    # Stage E/F/G/I ground truth: the recipient's own namespace IS the raw
    # checkpoint namespace (verbatim, no rename, no strip).
    assert EMBED_KEY in keys
    assert all(k.startswith("model.") for k in keys)
    # No persistent buffers, no lm_head, no tied aliases: state_dict ==
    # named_parameters exactly.
    assert set(keys) == {name for name, _p in model.named_parameters()}
    assert len(list(model.named_buffers())) == 0
    assert not any("lm_head" in k for k in keys)


def test_real_pinned_qwen_cast_once_validation_native_mapping():
    llama, ops = _real_llama()
    if llama is None:
        pytest.skip("real pinned comfy.text_encoders.llama unavailable")
    cfg = dict(
        vocab_size=64,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=1,
        num_attention_heads=1,
        num_key_value_heads=1,
    )
    skeleton = llama.Qwen3_4B(
        cfg, dtype=torch.float16, device="cpu", operations=ops.disable_weight_init()
    )
    live_names = dict(skeleton.state_dict()).keys()
    staged = {
        k: torch.full(tuple(t.shape), 0.5 + 0.125 * i, dtype=torch.bfloat16)
        for i, (k, t) in enumerate(skeleton.state_dict().items())
    }
    # THE native operation: ONE BF16->FP16 copy-cast into final storage.
    skeleton.load_state_dict(staged, strict=False, assign=False)

    class _Wrap(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.transformer = skeleton
            self.logit_scale = torch.nn.Parameter(torch.tensor(4.6055))

        def load_sd(self, sd):
            return self.transformer.load_sd(sd)

    csm = _Wrap()
    clip = types.SimpleNamespace(
        cond_stage_model=csm, patcher=object(), tokenizer=object()
    )

    class _Desc:
        keys = tuple(staged.keys())
        shapes = {k: tuple(t.shape) for k, t in staged.items()}
        dtypes = {k: "BF16" for k in staged}
        metadata = {}

    accounting = rcfs._validate_cast_once_bind(
        clip, [dict(staged)], [_Desc()], "torch.float16", "cpu"
    )
    n = len(list(live_names))
    assert accounting["checkpoint_tensor_count"] == n
    assert accounting["cast_once_count"] == n
    assert accounting["direct_match_count"] == 0
    assert accounting["remapped_count"] == n
    assert accounting["alias_count"] == 0
    assert accounting["missing_count"] == 0
    assert accounting["ambiguous_count"] == 0
    # The constant-init wrapper parameter is native-legitimate: counted,
    # reported, never fatal.
    assert accounting["extra_live_parameter_count"] == 1
    assert accounting["extra_live_parameter_sample"] == ["logit_scale"]
    assert accounting["validation_mapping_mode"] == "native_recipient_state_dict"
    assert accounting["validation_full_model_scan"] is False
    assert accounting["recipient_module_names"] == ["transformer"]
    samples = {m["source_key"]: m for m in accounting["mapping_samples"]}
    assert EMBED_KEY in samples
    assert samples[EMBED_KEY] == {
        "source_key": EMBED_KEY,
        "loadsd_key": EMBED_KEY,
        "live_key": f"transformer.{EMBED_KEY}",
        "mapping_kind": "native_wrapper_prefix",
    }
    # Bit-exact single-cast proof on the REAL module.
    assert torch.equal(
        skeleton.state_dict()[EMBED_KEY], staged[EMBED_KEY].to(torch.float16)
    )


# ---------------------------------------------------------------------------
# Producer END-TO-END through the scoped seams (REALISTIC NESTED fixture)
# ---------------------------------------------------------------------------


def test_producer_end_to_end_nested_namespace_and_telemetry(monkeypatch, tmp_path):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP_NATIVE_ADOPT, "1")
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44i1-e2e", trace=trace)
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

            # EXACTLY ONE conversion into FINAL storage below the wrapper.
            emb = csm.transformer.model.embed_tokens.weight
            assert emb.dtype == torch.float16
            assert bool(torch.equal(emb, served[EMBED_KEY].to(torch.float16)))
            assert emb.data_ptr() != served[EMBED_KEY].data_ptr()

            end = trace.payloads("clip_fast_load_end")[0]
            assert end["ok"] is True
            assert end["bind_mode"] == "cast_once_fp16"
            # R44I1 telemetry contract:
            assert end["raw_checkpoint_key_count"] == len(QWEN_KEYS) + 1
            assert end["transformed_loadsd_key_count"] == len(QWEN_KEYS) + 1
            assert end["live_parameter_key_count"] == len(QWEN_KEYS) + 1
            assert end["key_mapping_mode"] == "native_recipient_state_dict"
            assert end["validation_mapping_mode"] == "native_recipient_state_dict"
            assert end["direct_key_count"] == 0
            assert end["remapped_key_count"] == len(QWEN_KEYS)
            assert end["alias_key_count"] == 0
            assert end["missing_key_count"] == 0
            assert end["ambiguous_key_count"] == 0
            # logit_scale: outside-recipient ctor leftover, tolerated+reported.
            assert end["extra_live_key_count"] == 1
            assert end["recipient_modules"] == ["transformer"]
            assert end["validation_full_model_scan"] is False
            sample_map = {m["source_key"]: m for m in end["mapping_samples"]}
            assert sample_map[EMBED_KEY]["live_key"] == f"transformer.{EMBED_KEY}"
            assert sample_map[EMBED_KEY]["mapping_kind"] == "native_wrapper_prefix"
            # R44I3: the assign pin MUST have engaged (remote CoreModelPatcher
            # reports is_dynamic() True; without the pin the BF16 checkpoint
            # tensors are ASSIGNED over the FP16 skeleton -> bind_dtype_mismatch).
            assert end["assign_pin_added_calls"] >= 1
            assert end["is_dynamic_observed_true_calls"] >= 1

            # Truth: canonical arm observed WITHOUT fallback; result published.
            assert world.observed == [("clip", "fastsafetensors_direct_gpu", {})]
            assert ctx.result("clip") is clip

            # Early staging release ran non-destructively.
            loader, fb = world.owners_created[0]
            assert loader.release_calls == 1 and fb.release_calls == 1
            assert loader.closed is False and fb.closed is False
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_producer_missing_key_still_fails_closed_nested(monkeypatch, tmp_path):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP_NATIVE_ADOPT, "1")
    world = _install_world(monkeypatch, tmp_path)
    # H3-class reproduction: the served checkpoint carries one key the live
    # tree never defines (the exact shape of the remote
    # missing_key:model.embed_tokens.weight failure under the old validator).
    wiring = sys.modules["comfymodal_runtime.clip_fast_hydration_wiring"]

    base_tensors = _staged_values(torch.bfloat16)
    base_tensors["model.does_not_exist.weight"] = torch.zeros((4,), dtype=torch.bfloat16)

    def _broken_load(path, metrics=None):
        world.fs_calls.append(str(path))
        world.tensors_by_path[str(path)] = dict(base_tensors)
        loader, fb = FakeLoader(), FakeFB()
        world.owners_created.append((loader, fb))
        return (dict(base_tensors), loader, fb)

    wiring._fastsafe_load = _broken_load
    broken_desc = FakeDescriptor(
        keys=tuple(base_tensors.keys()),
        dtypes={**{k: "BF16" for k in base_tensors}, BLOB_KEY: "U8"},
        shapes={**QWEN_KEYS, BLOB_KEY: (8,), "model.does_not_exist.weight": (4,)},
    )
    monkeypatch.setattr(rfp, "build_descriptor", lambda *a, **k: broken_desc)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44i1-missing")
        try:
            result = __import__("nodes").NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(
                clip_name="qwen_tiny.safetensors"
            )
            # Transport happened, then validation failed CLOSED to native.
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


def _remote_assign_repro_world(monkeypatch):
    """Minimal pinned-comfy mirror for the R44I3 assign-semantics fix.

    Mirrors the REAL remote dispatch exactly: ``sd.py CLIP.load_sd`` reads
    ``patcher.is_dynamic()`` (CoreModelPatcher -> True), sprays
    ``can_assign_sd`` over every module, and ``SDClipModel/Qwen3_4B`` run
    ``load_state_dict(sd, strict=False, assign=can_assign_sd)``.
    """
    comfy_mod = types.ModuleType("comfy")
    utils_mod = types.ModuleType("comfy.utils")
    utils_mod.load_torch_file = lambda *a, **k: {}
    sd_mod = types.ModuleType("comfy.sd")

    class _NativeLoadSD:
        def __call__(self, clip_self, sd, full_model=False):
            can_assign = clip_self.patcher.is_dynamic()
            for m in clip_self.cond_stage_model.modules():
                m.can_assign_sd = can_assign
            return clip_self.cond_stage_model.load_sd(sd)

    class CLIP:
        load_sd = _NativeLoadSD()

    sd_mod.CLIP = CLIP
    mm_mod = types.ModuleType("comfy.model_management")
    mm_mod.text_encoder_initial_device = (
        lambda load_device, offload_device, model_size=0: offload_device
    )
    comfy_mod.utils = utils_mod
    comfy_mod.sd = sd_mod
    comfy_mod.model_management = mm_mod
    monkeypatch.setitem(sys.modules, "comfy", comfy_mod)
    monkeypatch.setitem(sys.modules, "comfy.utils", utils_mod)
    monkeypatch.setitem(sys.modules, "comfy.sd", sd_mod)
    monkeypatch.setitem(sys.modules, "comfy.model_management", mm_mod)
    return sd_mod


def _assign_probe_clip():
    skeleton = _CSM(torch.float16, torch.device("cpu"))
    patcher = _FakePatcher(skeleton)
    return types.SimpleNamespace(
        cond_stage_model=skeleton,
        patcher=patcher,
        tokenizer=types.SimpleNamespace(),
    )


def _probe_descriptor():
    staged = _staged_values(torch.bfloat16)
    desc = FakeDescriptor(
        keys=tuple(staged.keys()),
        dtypes={**{k: "BF16" for k in QWEN_KEYS}, BLOB_KEY: "U8"},
        shapes={**QWEN_KEYS, BLOB_KEY: (8,)},
    )
    return staged, desc


def test_remote_core_patcher_assign_true_reproduced_then_pinned_fix(monkeypatch):
    """R44I3 remote failure reproduction + fix proof.

    Run 1 (v2-benchmark-0-f3938a3f67bd) failed with
    ``bind_dtype_mismatch:model.embed_tokens.weight`` because the remote
    CoreModelPatcher.is_dynamic()==True drove native
    ``load_state_dict(assign=True)``: the BF16 checkpoint tensors were
    ASSIGNED over the FP16 skeleton (no conversion).  This test proves both
    halves through the mirrored real dispatch.
    """
    sd_mod = _remote_assign_repro_world(monkeypatch)
    staged, desc = _probe_descriptor()
    expected_dtype = "torch.float16"

    # -- Half 1: WITHOUT the pin, native dispatch assigns BF16 over FP16. --
    stub = _assign_probe_clip()
    sd_mod.CLIP.load_sd(stub, dict(staged))
    emb = stub.cond_stage_model.transformer.model.embed_tokens.weight
    assert emb.dtype == torch.bfloat16, (
        "expected the unpinned native dispatch to ASSIGN the BF16 tensor "
        "(exact remote mechanism)"
    )
    # The validator must fail closed on the unpinned dispatch.  With
    # same-object serving the assigned live tensor ALIASES the staging, so
    # the storage-independence proof fires first (aliasing_unexpected);
    # either violation class proves the assign pin is REQUIRED for
    # cast-once.
    with pytest.raises(RuntimeError, match="aliasing_unexpected:model.embed_tokens.weight"):
        rcfs._validate_cast_once_bind(
            stub, [dict(staged)], [desc], expected_dtype, "cuda:0"
        )

    # -- Half 2: WITH the cast-once seam installed, the pin forces
    #    assign=False and Comfy performs the single BF16->FP16 cast into
    #    final live storage; validation passes fully. --
    stub2 = _assign_probe_clip()
    counters: dict = {}
    restore = rcfs._install_native_construction_seams(
        {}, counters, skeleton_device=None, force_assign=False
    )
    try:
        sd_mod.CLIP.load_sd(stub2, dict(staged))
    finally:
        restore()
    emb2 = stub2.cond_stage_model.transformer.model.embed_tokens.weight
    assert emb2.dtype == torch.float16
    assert bool(torch.equal(emb2, staged[EMBED_KEY].to(torch.float16)))
    assert emb2.data_ptr() != staged[EMBED_KEY].data_ptr()
    # Pin engagement evidence + published-patcher fidelity: the instance
    # shadow is gone after the load window.
    assert counters.get("assign_pin_added_calls", 0) >= 1
    assert counters.get("is_dynamic_observed_true_calls", 0) >= 1
    assert "is_dynamic" not in stub2.patcher.__dict__
    accounting = rcfs._validate_cast_once_bind(
        stub2, [dict(staged)], [desc], expected_dtype, "cpu"
    )
    assert accounting["missing_count"] == 0
    assert accounting["ambiguous_count"] == 0
    assert accounting["extra_live_parameter_count"] == 1
    assert accounting["remapped_count"] == len(QWEN_KEYS)
    assert accounting["direct_match_count"] == 0
