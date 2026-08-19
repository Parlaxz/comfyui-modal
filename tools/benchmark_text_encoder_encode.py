"""Batch D7: generic, model-family-agnostic text-encoder encode benchmark lab.

A zero-spend LOCAL laboratory. No Modal, no downloads, no network, no edits to
any production file.  It builds small deterministic synthetic text encoders from
ComfyUI's own GENERIC building blocks (SDClipModel + CLIPTextModel / T5 / a
BaseLlama-style decoder stack, and the real ``comfy.sd.CLIP`` wrapper for a
multi-encoder) and measures the encode path across eight primary arms:

    P0A  fp32 compute, resident fp16  (CURRENT_COMFY behavior, cast every fwd)
    P0B  fp32 compute, resident fp32  (no casts -> isolates the per-fwd cast tax)
    P1A  fp32+TF32, resident fp16     P1B  fp32+TF32, resident fp32
    P2A  TRUE bf16, resident fp16     P2B  TRUE bf16, resident bf16
    P3A  TRUE fp16, resident fp32     P3B  TRUE fp16, resident fp16

TRUE low precision (P2*/P3*) is achieved by wrapping each encoder's
``transformer.forward`` (an object-level, reversible attribute patch) so the
``embeds``/``dtype`` kwargs are coerced to the policy dtype; Comfy's
``cast_bias_weight`` then casts the weights to the same dtype and ``F.linear``
runs real bf16/fp16 GEMMs (bf16/fp16 SDPA in attention).  The output contract
stays fp32 (sd1_clip's ``.float()`` is untouched).  The first-pass autocast
arms (P0..P4) remain available, labeled ``autocast_legacy``.

Design rules (hard):
  * ``comfy`` is imported LAZILY inside functions only, never at module top, so
    the pure-logic sections (DtypePolicy / Correctness / GlobalTorchSettings /
    synthetic tokens) run without comfy and without CUDA.
  * ``comfy.cli_args`` parses ``sys.argv`` at import time, so any harness CLI
    that may touch comfy must sanitize ``sys.argv`` (keep only unknown args)
    BEFORE the first comfy import.  ``sanitize_argv_for_comfy()`` does this.
  * The arm-planning and arm-application code NEVER consults model names or
    model classes.  Fixture ids ("classic_clip", "large_clip", "t5", "llm",
    "multi_encoder", "xl_llm") are pure registry labels used only for dict
    lookup.
  * Every arm snapshots/restores the touched global torch settings in
    try/finally via ``GlobalTorchSettings``, plus the transformer wraps, the
    resident-dtype state and the ``manual_cast_dtype`` override (reverse-order
    restoration).
"""

from __future__ import annotations

import argparse
import functools
import inspect
import itertools
import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import torch

# ═══════════════════════════════════════════════════════════════════════════
# Public registry labels / arm ids
# ═══════════════════════════════════════════════════════════════════════════

FIXTURE_IDS = ("classic_clip", "large_clip", "t5", "llm", "multi_encoder", "xl_llm")

# The 8 primary arms.  Each is described by (compute dtype, resident dtype):
#   P0A  fp32           / resident fp16  (CURRENT_COMFY behavior, cast every fwd)
#   P0B  fp32           / resident fp32  (no casts -> isolates the cast tax)
#   P1A  fp32+TF32      / resident fp16  (cast every fwd)
#   P1B  fp32+TF32      / resident fp32  (no casts)
#   P2A  TRUE bf16      / resident fp16  (cast fp16->bf16 every fwd)
#   P2B  TRUE bf16      / resident bf16  (no casts - pure bf16)
#   P3A  TRUE fp16      / resident fp32  (cast fp32->fp16 every fwd)
#   P3B  TRUE fp16      / resident fp16  (no casts - pure fp16)
NEW_ARM_IDS = ("P0A", "P0B", "P1A", "P1B", "P2A", "P2B", "P3A", "P3B")

# First-pass autocast arms, kept intact for comparison (mechanism =
# "autocast_legacy" so runs can exclude them by default).
LEGACY_ARM_IDS = ("P0", "P1", "P2", "P3", "P4")

ARM_IDS = NEW_ARM_IDS + LEGACY_ARM_IDS
DEFAULT_ARMS = NEW_ARM_IDS

ARM_INVALID_NOT_LOW_PRECISION = "ARM_INVALID_NOT_LOW_PRECISION"
ARM_INVALID = "ARM_INVALID"

_HUMAN_PREFIX = "[v2.d7]"


# ═══════════════════════════════════════════════════════════════════════════
# Section A — Pure logic (no comfy import needed)
# ═══════════════════════════════════════════════════════════════════════════


class DtypePolicy:
    """Capability-gated arm planning.

    ``plan_arms`` is a pure function of hardware capability flags.  It never
    takes, reads, or branches on model names / model classes.
    """

    @staticmethod
    def preferred_compute_dtype(capability):
        """bf16 if capability >= (8,0), fp16 if >= (7,0), else fp32."""
        if capability is not None and len(capability) >= 1 and capability[0] >= 8:
            return torch.bfloat16
        if capability is not None and len(capability) >= 1 and capability[0] >= 7:
            return torch.float16
        return torch.float32

    @staticmethod
    def _dtype_name(dtype):
        mapping = {
            torch.bfloat16: "bf16",
            torch.float16: "fp16",
            torch.float32: "fp32",
        }
        return mapping.get(dtype, str(dtype))

    @classmethod
    def plan_arms(cls, device_kind, capability, bf16_supported, fp16_supported):
        """Return ordered arm entries: the 8 new arms first, then the
        autocast-legacy arms P0..P4.

        Each entry carries ``arm``, ``status`` ("OK"/"UNSUPPORTED"), ``reason``,
        ``compute_dtype``, ``resident_dtype`` (str or None = fixture default),
        ``mechanism`` ("cast_every_forward" / "no_cast" / "autocast_legacy"),
        ``cast_policy`` and ``tf32`` (bool).
        """
        cuda = device_kind == "cuda"
        cap = capability if (capability is not None and len(capability) >= 1) else None
        cap8 = cap is not None and cap[0] >= 8
        cap7 = cap is not None and cap[0] >= 7

        def entry(arm_id, ok, reason, compute_dtype, resident_dtype, mechanism,
                  cast_policy, tf32=False):
            return {
                "arm": arm_id,
                "status": "OK" if ok else "UNSUPPORTED",
                "reason": None if ok else reason,
                "compute_dtype": compute_dtype,
                "resident_dtype": resident_dtype,
                "mechanism": mechanism,
                "cast_policy": cast_policy,
                "tf32": bool(tf32),
            }

        plan = [
            entry("P0A", True, None, "fp32", "fp16", "cast_every_forward", "cast_every_forward"),
            entry("P0B", True, None, "fp32", "fp32", "no_cast", "resident"),
            entry(
                "P1A",
                cuda and cap8,
                "TF32 requires CUDA with capability >= (8,0)",
                "fp32_tf32", "fp16", "cast_every_forward", "cast_every_forward", tf32=True,
            ),
            entry(
                "P1B",
                cuda and cap8,
                "TF32 requires CUDA with capability >= (8,0)",
                "fp32_tf32", "fp32", "no_cast", "resident", tf32=True,
            ),
            entry(
                "P2A",
                cuda and cap8 and bool(bf16_supported),
                "BF16 compute requires CUDA with capability >= (8,0)",
                "bf16", "fp16", "cast_every_forward", "cast_every_forward",
            ),
            entry(
                "P2B",
                cuda and cap8 and bool(bf16_supported),
                "BF16 compute requires CUDA with capability >= (8,0)",
                "bf16", "bf16", "no_cast", "resident",
            ),
            entry(
                "P3A",
                cuda and cap7 and bool(fp16_supported),
                "FP16 compute requires CUDA with capability >= (7,0)",
                "fp16", "fp32", "cast_every_forward", "cast_every_forward",
            ),
            entry(
                "P3B",
                cuda and cap7 and bool(fp16_supported),
                "FP16 compute requires CUDA with capability >= (7,0)",
                "fp16", "fp16", "no_cast", "resident",
            ),
            # ── first-pass autocast arms, kept for comparison ──
            entry("P0", True, None, "fp32", None, "autocast_legacy", "autocast"),
            entry(
                "P1",
                cuda and cap8,
                "TF32 requires CUDA with capability >= (8,0)",
                "fp32_tf32", None, "autocast_legacy", "autocast", tf32=True,
            ),
            entry(
                "P2",
                cuda and cap8 and bool(bf16_supported),
                "BF16 autocast requires CUDA with capability >= (8,0)",
                "bf16", None, "autocast_legacy", "autocast",
            ),
            entry(
                "P3",
                cuda and cap7 and bool(fp16_supported),
                "FP16 autocast requires CUDA with capability >= (7,0)",
                "fp16", None, "autocast_legacy", "autocast",
            ),
            entry(
                "P4",
                cuda,
                "Preferred-dtype arm requires CUDA",
                cls._dtype_name(cls.preferred_compute_dtype(cap if cuda else None)),
                None, "autocast_legacy", "autocast",
            ),
        ]
        return plan

    @staticmethod
    def status_for(plan, arm_id):
        for entry in plan:
            if entry["arm"] == arm_id:
                return entry
        raise KeyError(arm_id)


class Correctness:
    """Metric computation + classification of a candidate vs a reference."""

    EXACT = "EXACT"
    NUMERICALLY_CLOSE = "NUMERICALLY_CLOSE"
    MATERIAL_DIFFERENCE = "MATERIAL_DIFFERENCE"
    INVALID = "INVALID"
    UNSUPPORTED = "UNSUPPORTED"

    # EXACT if max_abs_error == 0; NUMERICALLY_CLOSE if finite + shape-equal +
    # cosine >= 0.999 and max_abs_error <= 1e-2; MATERIAL_DIFFERENCE if finite +
    # shape-equal but outside those; INVALID if non-finite or shape mismatch.
    COSINE_THRESHOLD = 0.999
    MAX_ABS_THRESHOLD = 1e-2

    @classmethod
    def compare(cls, reference, candidate):
        if reference is None or candidate is None:
            return {
                "class": cls.UNSUPPORTED,
                "reason": "reference or candidate is None",
            }
        if not isinstance(reference, torch.Tensor) or not isinstance(candidate, torch.Tensor):
            return {"class": cls.INVALID, "reason": "non-tensor input"}
        ref = reference.detach().float()
        cand = candidate.detach().float()

        metrics = {
            "shape_ref": list(ref.shape),
            "shape_cand": list(cand.shape),
            "shape_equal": tuple(ref.shape) == tuple(cand.shape),
        }
        if not metrics["shape_equal"]:
            metrics["class"] = cls.INVALID
            metrics["reason"] = "shape mismatch"
            return metrics
        if ref.numel() == 0:
            metrics.update(
                {
                    "nan_ref": 0, "nan_cand": 0, "inf_ref": 0, "inf_cand": 0,
                    "finite_percentage": 100.0,
                    "max_abs_error": 0.0, "mean_abs_error": 0.0, "rms_error": 0.0,
                    "relative_error": None, "cosine_similarity": 1.0,
                    "class": cls.EXACT,
                }
            )
            return metrics

        nan_ref = int(torch.isnan(ref).sum().item())
        nan_cand = int(torch.isnan(cand).sum().item())
        inf_ref = int(torch.isinf(ref).sum().item())
        inf_cand = int(torch.isinf(cand).sum().item())
        finite = (nan_ref + nan_cand + inf_ref + inf_cand) == 0
        metrics["nan_ref"] = nan_ref
        metrics["nan_cand"] = nan_cand
        metrics["inf_ref"] = inf_ref
        metrics["inf_cand"] = inf_cand
        metrics["finite_percentage"] = 100.0 if finite else 0.0
        if not finite:
            metrics["class"] = cls.INVALID
            metrics["reason"] = "non-finite values present"
            return metrics

        diff = cand - ref
        max_abs_error = float(diff.abs().max().item())
        mean_abs_error = float(diff.abs().mean().item())
        rms_error = float(diff.pow(2).mean().sqrt().item())
        denom = float(ref.abs().mean().item())
        relative_error = float(mean_abs_error / denom) if denom > 1e-12 else None
        flat_ref = ref.reshape(1, -1)
        flat_cand = cand.reshape(1, -1)
        cosine = float(torch.nn.functional.cosine_similarity(flat_cand, flat_ref).item())

        metrics.update(
            {
                "max_abs_error": max_abs_error,
                "mean_abs_error": mean_abs_error,
                "rms_error": rms_error,
                "relative_error": relative_error,
                "cosine_similarity": cosine,
            }
        )
        if max_abs_error == 0.0:
            metrics["class"] = cls.EXACT
        elif cosine >= cls.COSINE_THRESHOLD and max_abs_error <= cls.MAX_ABS_THRESHOLD:
            metrics["class"] = cls.NUMERICALLY_CLOSE
        else:
            metrics["class"] = cls.MATERIAL_DIFFERENCE
        return metrics


class GlobalTorchSettings:
    """Snapshot / apply / restore of the torch global settings the arms touch.

    Snapshot values are JSON-safe (str / bool / None) so they can round-trip
    into result dicts and equality checks.
    """

    @staticmethod
    def snapshot():
        autocast_cpu = False
        if hasattr(torch, "is_autocast_enabled"):
            try:
                autocast_cpu = bool(torch.is_autocast_enabled("cpu"))
            except Exception:
                autocast_cpu = bool(torch.is_autocast_cpu_enabled())
        snap = {
            "cuda_matmul_allow_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
            "cudnn_allow_tf32": bool(torch.backends.cudnn.allow_tf32),
            "autocast_cuda_enabled": bool(torch.is_autocast_enabled()),
            "autocast_cpu_enabled": autocast_cpu,
            "float32_matmul_precision": None,
            "autocast_cuda_dtype": None,
        }
        if hasattr(torch, "get_float32_matmul_precision"):
            snap["float32_matmul_precision"] = str(torch.get_float32_matmul_precision())
        if hasattr(torch, "get_autocast_dtype"):
            try:
                snap["autocast_cuda_dtype"] = str(torch.get_autocast_dtype("cuda"))
            except Exception:
                snap["autocast_cuda_dtype"] = None
        return snap

    @staticmethod
    def apply(arm_id, plan_entry):
        """Apply persistent global settings for an arm.

        The TF32 arms (P1 and the new P1A/P1B) enable
        ``torch.backends.cuda.matmul.allow_tf32`` + float32 matmul precision
        "high".  All other arms change nothing globally (P2/P3/P4 use per-call
        autocast contexts; the new low-precision arms are wrap-driven).
        """
        if arm_id in ("P1", "P1A", "P1B"):
            torch.backends.cuda.matmul.allow_tf32 = True
            if hasattr(torch, "set_float32_matmul_precision"):
                torch.set_float32_matmul_precision("high")

    @staticmethod
    def restore(snapshot):
        if "cuda_matmul_allow_tf32" in snapshot and hasattr(
            torch.backends.cuda.matmul, "allow_tf32"
        ):
            torch.backends.cuda.matmul.allow_tf32 = snapshot["cuda_matmul_allow_tf32"]
        if "cudnn_allow_tf32" in snapshot and hasattr(torch.backends.cudnn, "allow_tf32"):
            torch.backends.cudnn.allow_tf32 = snapshot["cudnn_allow_tf32"]
        precision = snapshot.get("float32_matmul_precision")
        if precision is not None and hasattr(torch, "set_float32_matmul_precision"):
            try:
                torch.set_float32_matmul_precision(precision)
            except Exception:
                pass
        if not snapshot.get("autocast_cuda_enabled", False) and torch.is_autocast_enabled():
            # Defensive no-op: the harness always exits its autocast contexts.
            torch.autocast("cuda", enabled=False)


# ═══════════════════════════════════════════════════════════════════════════
# Section B — Fixtures (deterministic synthetic, built from Comfy generic
#             classes; zero downloads).  Fixture ids are registry labels only.
# ═══════════════════════════════════════════════════════════════════════════


def synthetic_tokens(max_length, batch, seed, vocab_size=49408):
    """Comfy token structure: list of batches; each item a list of
    ``(token_id:int, weight:float)`` tuples padded to ``max_length``.

    Deterministic ids in ``[1, vocab_size-2]`` (never equal to common
    end/pad ids such as 0 / 49407), weights all 1.0.
    """
    out = []
    for b in range(batch):
        batch_tokens = []
        for i in range(max_length):
            token_id = ((seed + b * 7919 + i * 104729) % (vocab_size - 2)) + 1
            batch_tokens.append((int(token_id), 1.0))
        out.append(batch_tokens)
    return out


def _clip_config(embed_dim, heads, layers, max_length, vocab_size=49408):
    return {
        "hidden_size": embed_dim,
        "num_attention_heads": heads,
        "num_hidden_layers": layers,
        "intermediate_size": embed_dim * 4,
        "hidden_act": "quick_gelu",
        "max_position_embeddings": max_length,
        "vocab_size": vocab_size,
        "eos_token_id": 49407,
        "layer_norm_eps": 1e-05,
        "initializer_range": 0.02,
    }


def _t5_config(max_length=77):
    return {
        "d_model": 512,
        "d_kv": 64,
        "d_ff": 2048,
        "num_layers": 8,
        "num_heads": 8,
        "vocab_size": 32128,
        "dense_act_fn": "relu",
        "is_gated_act": False,
        "model_type": "t5",
        "relative_attention_num_buckets": 32,
        "dropout_rate": 0.1,
        "layer_norm_epsilon": 1e-6,
        "max_position_embeddings": max_length,
    }


def _llama_config(max_length=77):
    # Only the dataclass *fields* of comfy.text_encoders.llama.Llama2Config may
    # be passed here; the rest (head_dim=128, qkv_bias=False, mlp_activation,
    # final_norm, ...) are class attributes with inherited defaults.
    return {
        "vocab_size": 32000,
        "hidden_size": 512,
        "intermediate_size": 1408,
        "num_hidden_layers": 8,
        "num_attention_heads": 8,
        "num_key_value_heads": 4,
        "max_position_embeddings": max_length,
        "rms_norm_eps": 1e-5,
        "rope_theta": 500000.0,
        "transformer_type": "llama",
    }


def _multi_token_dict(max_length, batch, seed):
    return {
        "l": synthetic_tokens(max_length, batch, seed, vocab_size=49408),
        "llm": synthetic_tokens(max_length, batch, seed, vocab_size=32000),
    }


def _reinit_params(model, seed):
    """Deterministically fill the synthetic model's parameters.

    Comfy's ``disable_weight_init`` ops leave ``reset_parameters`` as a no-op
    (production loads real checkpoint weights), so a freshly built synthetic
    model contains uninitialized ``torch.empty`` storage that produces NaN.
    This walks every module and seeds weights from ``seed``.
    """
    import comfy.ops

    torch.manual_seed(seed)
    with torch.no_grad():
        for module in model.modules():
            weight = getattr(module, "weight", None)
            bias = getattr(module, "bias", None)
            if isinstance(module, (comfy.ops.disable_weight_init.Linear, torch.nn.Linear)):
                if weight is not None:
                    weight.data.normal_(0.0, 0.02)
                if bias is not None:
                    bias.data.zero_()
            elif isinstance(module, (comfy.ops.disable_weight_init.Embedding, torch.nn.Embedding)):
                if weight is not None:
                    weight.data.normal_(0.0, 0.02)
            elif isinstance(module, torch.nn.LayerNorm):
                if weight is not None:
                    weight.data.fill_(1.0)
                if bias is not None:
                    bias.data.zero_()
            else:
                # RMSNorm-style single 1-D weight parameter (decoder/T5 norms).
                if isinstance(weight, torch.nn.Parameter) and weight.dim() == 1:
                    weight.data.fill_(1.0)


def _clip_positions(max_length):
    """CLIP position tables must cover the bundled tokenizer's 77-token pad
    width as well as any requested synthetic length."""
    return max(77, max_length)


def _with_clip_tokens(model, max_length, batch, seed):
    """Attempt real tokenize through the bundled SD1 tokenizer (measured
    separately); fall back to deterministic synthetic tokens on any failure."""
    tokenize_wall_ms = None
    tokenize_mode = "synthetic"
    tokens = {"l": synthetic_tokens(max_length, batch, seed, vocab_size=49408)}
    try:
        import comfy.sd1_clip

        tokenizer = comfy.sd1_clip.SD1Tokenizer(embedding_directory=None)
        t0 = time.perf_counter()
        tokens = tokenizer.tokenize_with_weights(
            "a photo of a cat sitting on a bench in a park during golden hour"
        )
        tokenize_wall_ms = (time.perf_counter() - t0) * 1000.0
        tokenize_mode = "real"
    except Exception:
        tokenize_mode = "unavailable"
    return {
        "model": model,
        "encode_tokens": tokens,
        "tokenize_wall_ms": tokenize_wall_ms,
        "tokenize_mode": tokenize_mode,
        "encode_kind": "raw",
    }


def _build_classic_clip(seed, max_length, batch, resident_dtype):
    import comfy.sd1_clip

    torch.manual_seed(seed)
    model = comfy.sd1_clip.SD1ClipModel(
        device="cpu",
        dtype=resident_dtype,
        model_options={
            "clip_l_model_config": _clip_config(512, 8, 12, _clip_positions(max_length))
        },
    )
    _reinit_params(model, seed)
    return _with_clip_tokens(model, max_length, batch, seed)


def _build_large_clip(seed, max_length, batch, resident_dtype):
    import comfy.sd1_clip

    torch.manual_seed(seed)
    model = comfy.sd1_clip.SD1ClipModel(
        device="cpu",
        dtype=resident_dtype,
        model_options={
            "clip_l_model_config": _clip_config(768, 12, 24, _clip_positions(max_length))
        },
    )
    _reinit_params(model, seed)
    return _with_clip_tokens(model, max_length, batch, seed)


def _build_t5_fixture(seed, max_length, batch, resident_dtype):
    import comfy.sd1_clip
    import comfy.text_encoders.t5

    torch.manual_seed(seed)
    model = comfy.sd1_clip.SDClipModel(
        device="cpu",
        dtype=resident_dtype,
        textmodel_json_config=_t5_config(max_length),
        model_class=comfy.text_encoders.t5.T5,
        special_tokens={"end": 1, "pad": 0},
    )
    _reinit_params(model, seed)
    return {
        "model": model,
        "encode_tokens": synthetic_tokens(max_length, batch, seed, vocab_size=32128),
        "encode_kind": "raw",
        "tokenize_mode": "synthetic",
    }


def _build_llm_fixture(seed, max_length, batch, resident_dtype):
    import comfy.sd1_clip
    import comfy.text_encoders.llama

    torch.manual_seed(seed)
    model = comfy.sd1_clip.SDClipModel(
        device="cpu",
        dtype=resident_dtype,
        textmodel_json_config=_llama_config(max_length),
        model_class=comfy.text_encoders.llama.Llama2,
        special_tokens={"start": 1, "end": 2, "pad": 0},
    )
    _reinit_params(model, seed)
    return {
        "model": model,
        "encode_tokens": synthetic_tokens(max_length, batch, seed, vocab_size=32000),
        "encode_kind": "raw",
        "tokenize_mode": "synthetic",
    }


def _estimate_llama_params(layers, hidden, heads, kv_heads, intermediate, vocab, head_dim=128):
    """Analytic parameter count for a Llama2-style encoder (avoids building
    oversized models on CPU just to shrink them)."""
    inner = heads * head_dim
    kv = kv_heads * head_dim
    per_layer = (
        hidden * inner          # q_proj
        + hidden * kv           # k_proj
        + hidden * kv           # v_proj
        + inner * hidden        # o_proj
        + 2 * hidden * intermediate  # gate_proj + up_proj
        + intermediate * hidden      # down_proj
    )
    return vocab * hidden + layers * per_layer


def _build_xl_llm(seed, max_length, batch, resident_dtype):
    """Largest fixture: a Llama2-style SDClipModel (~800M params, fp16 ~1.6GB).

    VRAM guard: resident (fp16) + state_dict clone + workspace must fit in
    6.0 GB -> estimated param_bytes * 3 < 6.0 GB, else num_hidden_layers is
    shrunk by 4 until it fits (recorded as ``shrunk_layers`` in identity).
    Built on CPU so construction itself never OOMs on the GPU.
    """
    import comfy.sd1_clip
    import comfy.text_encoders.llama

    vocab = 32000
    hidden = 2304
    heads = 16
    kv_heads = 4
    intermediate = 1792
    layers = 32
    shrunk = 0

    guard_bytes = 6.0 * 1024 ** 3
    while _estimate_llama_params(layers, hidden, heads, kv_heads, intermediate, vocab) * 2 * 3 >= guard_bytes:
        layers -= 4
        shrunk += 4

    def _config(l):
        return {
            "vocab_size": vocab,
            "hidden_size": hidden,
            "intermediate_size": intermediate,
            "num_hidden_layers": l,
            "num_attention_heads": heads,
            "num_key_value_heads": kv_heads,
            "max_position_embeddings": max_length,
            "rms_norm_eps": 1e-5,
            "rope_theta": 500000.0,
            "transformer_type": "llama",
        }

    torch.manual_seed(seed)
    model = comfy.sd1_clip.SDClipModel(
        device="cpu",
        dtype=resident_dtype,
        textmodel_json_config=_config(layers),
        model_class=comfy.text_encoders.llama.Llama2,
        special_tokens={"start": 1, "end": 2, "pad": 0},
    )
    _reinit_params(model, seed)
    return {
        "model": model,
        "encode_tokens": synthetic_tokens(max_length, batch, seed, vocab_size=vocab),
        "encode_kind": "raw",
        "tokenize_mode": "synthetic",
        "shrunk_layers": shrunk,
        "configured_layers": 32,
    }


def _make_multi_encoder_classes(max_length, batch, seed):
    """Return (model_class, tokenizer_class).  The model class composites two
    real generic Comfy encoders (a CLIP-style SDClipModel and a BaseLlama-style
    SDClipModel) so the encode path runs both the generic cast machinery and
    the generic attention machinery."""
    import comfy.sd1_clip
    import comfy.text_encoders.llama

    class GenericMultiTE(torch.nn.Module):
        def __init__(self, device="cpu", dtype=None, model_options={}):
            super().__init__()
            self.dtypes = set()
            if dtype is not None:
                self.dtypes.add(dtype)
            self.clip_l = comfy.sd1_clip.SDClipModel(
                device=device,
                dtype=dtype,
                layer="hidden",
                layer_idx=-2,
                layer_norm_hidden_state=False,
                return_projected_pooled=False,
                textmodel_json_config=_clip_config(512, 8, 6, _clip_positions(max_length)),
                model_options=model_options,
            )
            self.llm = comfy.sd1_clip.SDClipModel(
                device=device,
                dtype=dtype,
                textmodel_json_config=_llama_config(max_length),
                model_class=comfy.text_encoders.llama.Llama2,
                special_tokens={"start": 1, "end": 2, "pad": 0},
                model_options=model_options,
            )

        def set_clip_options(self, options):
            self.clip_l.set_clip_options(options)
            self.llm.set_clip_options(options)

        def reset_clip_options(self):
            self.clip_l.reset_clip_options()
            self.llm.reset_clip_options()

        def encode_token_weights(self, token_pairs):
            l_out, l_pooled = self.clip_l.encode_token_weights(token_pairs["l"])
            llm_out, _llm_pooled = self.llm.encode_token_weights(token_pairs["llm"])
            out = torch.cat([l_out, llm_out], dim=-2)
            return out, l_pooled

    class SyntheticDictTokenizer:
        def __init__(self, embedding_directory=None, tokenizer_data={}):
            pass

        def tokenize_with_weights(self, text, return_word_ids=False, **kwargs):
            return _multi_token_dict(max_length, batch, seed)

        def state_dict(self):
            return {}

    return GenericMultiTE, SyntheticDictTokenizer


def _build_multi_encoder(seed, max_length, batch, resident_dtype):
    """Try the real ``comfy.sd.CLIP`` wrapper first (production-shaped
    ``CLIP.encode_from_tokens`` path).  Fall back to the raw composite model
    if the wrapper cannot be constructed."""
    import comfy.sd

    model_class, tokenizer_class = _make_multi_encoder_classes(max_length, batch, seed)

    class _Target:
        pass

    target = _Target()
    target.params = {}
    target.clip = model_class
    target.tokenizer = tokenizer_class

    torch.manual_seed(seed)
    try:
        clip = comfy.sd.CLIP(
            target=target,
            embedding_directory=None,
            parameters=0,
            disable_dynamic=True,
        )
        model = clip.cond_stage_model
        _reinit_params(model, seed)
        encode_kind = "wrapped"
    except Exception as exc:
        model = model_class(device="cpu", dtype=resident_dtype)
        _reinit_params(model, seed)
        clip = None
        encode_kind = "raw_fallback"
        wrapper_status = "unavailable:{}:{}".format(type(exc).__name__, exc)
    else:
        wrapper_status = "clip_wrapper"
    return {
        "model": model,
        "clip": clip,
        "wrapper_status": wrapper_status,
        "encode_tokens": _multi_token_dict(max_length, batch, seed),
        "encode_kind": encode_kind,
        "tokenize_mode": "synthetic",
    }


FIXTURE_REGISTRY = {
    "classic_clip": _build_classic_clip,
    "large_clip": _build_large_clip,
    "t5": _build_t5_fixture,
    "llm": _build_llm_fixture,
    "multi_encoder": _build_multi_encoder,
    "xl_llm": _build_xl_llm,
}


# ═══════════════════════════════════════════════════════════════════════════
# Section C — Execution core
# ═══════════════════════════════════════════════════════════════════════════


def _use_cuda(run_device=None):
    if run_device == "cpu":
        return False
    return bool(torch.cuda.is_available())


def _device_info(run_device=None):
    if _use_cuda(run_device):
        capability = tuple(int(x) for x in torch.cuda.get_device_capability(0))
        return "cuda", capability, True, True
    return "cpu", None, False, False


def _plan_entry_for(arm_id, run_device=None):
    device_kind, capability, bf16, fp16 = _device_info(run_device)
    plan = DtypePolicy.plan_arms(device_kind, capability, bf16, fp16)
    return DtypePolicy.status_for(plan, arm_id)


def _autocast_spec(arm_id, plan_entry):
    """Return ``(device_type, dtype)`` for per-call autocast, or None.

    Only the autocast-legacy arms (P0..P4) may autocast.  The new arms
    (P0A..P3B) implement low precision through the transformer.forward wrap,
    never through autocast -- autocast would keep the Linear INPUT tensors
    fp32 (the very behavior this lab must not measure).
    """
    if arm_id not in LEGACY_ARM_IDS:
        return None
    if arm_id in ("P0", "P1"):
        return None
    if arm_id == "P2":
        return ("cuda", torch.bfloat16)
    if arm_id == "P3":
        return ("cuda", torch.float16)
    compute = plan_entry.get("compute_dtype", "fp32")
    if compute == "bf16":
        return ("cuda", torch.bfloat16)
    if compute == "fp16":
        return ("cuda", torch.float16)
    return None


def _resident_dtype(model):
    """Most common parameter dtype (SDClipModel carries a fp32 logit_scale
    that must not dominate the resident-dtype answer)."""
    counts = {}
    for param in model.parameters():
        counts[param.dtype] = counts.get(param.dtype, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def _class_names(model, extra=None):
    names = [type(model).__name__]
    for attr in ("clip_l", "clip_g", "t5xxl", "llm"):
        sub = getattr(model, attr, None)
        if sub is not None:
            names.append(type(sub).__name__)
    if extra:
        names.extend(extra)
    return names


def _ensure_comfy_importable(comfy_dir=None):
    """Add the parent ComfyUI repo to sys.path if it is not already importable.
    No-op when PYTHONPATH already points at it."""
    if comfy_dir is None:
        candidate = Path(__file__).resolve().parents[3]  # .../custom_nodes -> ComfyUI
        if (candidate / "comfy").is_dir():
            comfy_dir = str(candidate)
    if comfy_dir and comfy_dir not in sys.path:
        sys.path.insert(0, comfy_dir)


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="benchmark_text_encoder_encode.py",
        description="Generic text-encoder encode benchmark lab (zero-spend, local).",
    )
    parser.add_argument("--fixtures", default=None,
                        help="Comma-separated fixture ids or 'all' (default: all)")
    parser.add_argument("--arms", default=None,
                        help="Comma-separated arm ids or 'all' (default: all)")
    parser.add_argument("--mode", default="coarse", choices=("coarse", "deep"),
                        help="coarse = timing only; deep = + torch profiler buckets")
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--tokens", type=int, default=77, dest="max_length")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--json", default=None, metavar="PATH", help="Write JSON results")
    parser.add_argument("--list-fixtures", action="store_true",
                        help="Print fixture ids and exit")
    parser.add_argument("--quick", action="store_true",
                        help="repeats=5, warmup=1")
    parser.add_argument("--comfy-dir", default=None,
                        help="Path to the parent ComfyUI repo (auto-detected by default)")
    return parser


def sanitize_argv_for_comfy():
    """Strip harness-only CLI args from sys.argv so that a subsequent
    ``import comfy`` (whose cli_args module parses sys.argv) is safe.
    Leaves unknown args intact.  Returns the parsed harness args."""
    parser = _build_arg_parser()
    known, unknown = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + unknown
    return known


def prepare_fixture(fixture_id, seed=1234, max_length=77, batch=1, run_device=None):
    """Build, wrap, load and tokenize one fixture.  Returns a SimpleNamespace
    describing it.  Raises if the fixture cannot be built for the given device.
    """
    import comfy.model_management as mm
    import comfy.model_patcher as comfy_mp

    use_cuda = _use_cuda(run_device)
    if use_cuda:
        device = mm.get_torch_device()
        resident_dtype = mm.text_encoder_dtype(device)
    else:
        device = torch.device("cpu")
        resident_dtype = torch.float32

    builder = FIXTURE_REGISTRY[fixture_id]
    built = builder(seed=seed, max_length=max_length, batch=batch, resident_dtype=resident_dtype)
    model = built["model"]
    clip = built.get("clip")

    if clip is not None:
        patcher = clip.patcher
        patcher.set_model_compute_dtype(torch.float32)
    else:
        patcher = comfy_mp.ModelPatcher(
            model,
            load_device=device,
            offload_device=mm.text_encoder_offload_device(),
        )
        patcher.set_model_compute_dtype(torch.float32)
        patcher.is_clip = True

    mm.load_models_gpu([patcher])
    if use_cuda:
        torch.cuda.synchronize()

    # Token structure + encode callable come from the builder package.
    encode_tokens = built["encode_tokens"]
    if clip is not None:
        def _clip_encode(tokens, _clip=clip):
            return _clip.encode_from_tokens(tokens, return_pooled=True)

        encode_fn = _clip_encode
        encode_kind = "wrapped"
    else:
        encode_fn = model.encode_token_weights
        encode_kind = built.get("encode_kind", "raw")
    tokenize_wall_ms = built.get("tokenize_wall_ms")
    tokenize_mode = built.get("tokenize_mode", "synthetic")

    import comfy.ldm.modules.attention as attn_mod

    attention_fn = attn_mod.optimized_attention_for_device(
        device, mask=False, small_input=True
    )
    attention_function = getattr(attention_fn, "__name__", str(attention_fn))

    param_count = int(sum(p.numel() for p in model.parameters()))
    resident = _resident_dtype(model)

    off_device = [name for name, p in model.named_parameters() if str(p.device) != str(device)]

    identity = {
        "fixture": fixture_id,
        "class": _class_names(model, extra=["CLIP"] if clip is not None else None),
        "param_count": param_count,
        "resident_dtype": str(resident),
        "token_count": max_length,
        "batch": batch,
        "device": str(device),
        "params_off_device": off_device,
        "wrapper_status": built.get("wrapper_status"),
        "tokenize_mode": tokenize_mode,
        "shrunk_layers": built.get("shrunk_layers"),
        "configured_layers": built.get("configured_layers"),
    }

    return SimpleNamespace(
        fixture_id=fixture_id,
        model=model,
        patcher=patcher,
        clip=clip,
        encode_tokens=encode_tokens,
        encode_fn=encode_fn,
        encode_kind=encode_kind,
        tokenize_wall_ms=tokenize_wall_ms,
        tokenize_mode=tokenize_mode,
        param_count=param_count,
        resident_dtype=resident,
        class_names=_class_names(model, extra=["CLIP"] if clip is not None else None),
        attention_function=attention_function,
        max_length=max_length,
        batch=batch,
        identity=identity,
    )


def _dtype_from_name(name):
    """Map a resident-dtype string ("fp16"/"fp32"/"bf16") to a torch dtype."""
    return {
        "fp32": torch.float32,
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
    }.get(name)


def _policy_dtype_for(arm_id, plan_entry):
    """Compute dtype for the arm (True low precision for P2*/P3*, fp32 else)."""
    compute = plan_entry.get("compute_dtype", "fp32")
    if compute == "bf16":
        return torch.bfloat16
    if compute == "fp16":
        return torch.float16
    return torch.float32


def _forward_accepts_dtype_or_embeds(forward):
    """Capability check for the transformer-wrap seam.

    Accepts forwards whose signature has an explicit ``dtype`` or ``embeds``
    parameter OR a VAR_KEYWORD (``**kwargs``) parameter.  This covers
    CLIPTextModel.forward (``(*args, **kwargs)`` forwarding into
    CLIPTextModel_.forward which honors dtype/embeds), the decoder-style
    encoders' forwards and BaseLlama.forward (``(input_ids, *args, **kwargs)``
    forwarding into the inner decoder).  Forwards without any of those (e.g.
    plain Linear.forward) are rejected.
    """
    try:
        sig = inspect.signature(forward)
    except (TypeError, ValueError):
        return False
    for _name, param in sig.parameters.items():
        if param.name in ("dtype", "embeds"):
            return True
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return False


def _wrap_transformers(model, policy_dtype):
    """Wrap every submodule's ``transformer.forward`` to coerce the ``embeds``
    and ``dtype`` kwargs to ``policy_dtype``.

    The wrap is an object-level attribute patch on the module instance (the
    bound method is replaced by a wrapper that coerces then forwards to the
    original).  Returns a list of ``(transformer, original_bound_method)`` pairs
    for exact restoration.  Walking ``named_modules()`` covers the multi-encoder
    composite which contains several encoders (one ``transformer`` each).
    """
    wrapped = []
    seen = set()
    for _name, module in model.named_modules():
        transformer = getattr(module, "transformer", None)
        if transformer is None or id(transformer) in seen:
            continue
        seen.add(id(transformer))
        original = getattr(transformer, "forward", None)
        if original is None or not _forward_accepts_dtype_or_embeds(original):
            continue

        def _make(orig, _policy):
            @functools.wraps(orig)
            def _wrapper(*args, **kwargs):
                if kwargs.get("embeds") is not None:
                    kwargs["embeds"] = kwargs["embeds"].to(_policy)
                if "dtype" in kwargs:
                    kwargs["dtype"] = _policy
                return orig(*args, **kwargs)

            return _wrapper

        transformer.forward = _make(original, policy_dtype)
        wrapped.append((transformer, original))
    return wrapped


def _snapshot_model_state(model):
    """Clone every parameter + persistent buffer (dtype + bits) for exact
    post-arm restoration.  Keep it on-device unless VRAM demands otherwise."""
    return {k: v.detach().clone() for k, v in model.state_dict().items()}


def _restore_model_state(model, clone):
    """Restore the model bitwise-exactly from a pre-arm state_dict clone.

    ``load_state_dict(clone, assign=False)`` copies the clone values into the
    CURRENT parameter tensors, casting to the current param dtype -- so first
    restore every float parameter/buffer to the dtype recorded in the clone
    (a mixed-dtype model such as an SD1ClipModel carries a fp32 ``logit_scale``
    among fp16 weights), then the copy is exact.  ``assign=True`` is avoided:
    it would rebind the parameters to the clone tensors, leaving stale
    dtype/device state behind the patcher's weight backup machinery.
    """
    with torch.no_grad():
        for name, value in clone.items():
            if not torch.is_floating_point(value):
                continue
            parts = name.split(".")
            obj = model
            for part in parts[:-1]:
                obj = getattr(obj, part)
            current = getattr(obj, parts[-1])
            if current.dtype != value.dtype:
                current.data = current.data.to(dtype=value.dtype)
    model.load_state_dict(clone, assign=False)


def _set_manual_cast_dtype(fixture, dtype):
    """Set the model's ``manual_cast_dtype`` (both the live attribute and the
    patcher's object_patches entry so reports see it).  Returns the previous
    values for exact restoration."""
    import comfy.utils

    model = fixture.model
    prev_attr = comfy.utils.set_attr(model, "manual_cast_dtype", dtype)
    patcher = fixture.patcher
    prev_patch = patcher.object_patches.get("manual_cast_dtype")
    patcher.object_patches["manual_cast_dtype"] = dtype
    return (prev_attr, prev_patch)


def _restore_manual_cast_dtype(fixture, prev):
    """Restore ``manual_cast_dtype`` attribute + patcher entry from ``prev``."""
    import comfy.utils

    prev_attr, prev_patch = prev
    comfy.utils.set_attr(fixture.model, "manual_cast_dtype", prev_attr)
    patcher = fixture.patcher
    if prev_patch is None:
        patcher.object_patches.pop("manual_cast_dtype", None)
    else:
        patcher.object_patches["manual_cast_dtype"] = prev_patch


def _call_encode(fixture, autocast_spec):
    if autocast_spec is None:
        return fixture.encode_fn(fixture.encode_tokens)
    device_type, dtype = autocast_spec
    with torch.autocast(device_type=device_type, dtype=dtype):
        return fixture.encode_fn(fixture.encode_tokens)


def _verification_pass(fixture, autocast_spec, use_cuda, policy_dtype=None):
    """UNTIMED single encode with activation-dtype hooks + cast accounting.

    ``policy_dtype`` is the arm's requested compute dtype (None for
    autocast-legacy arms); it is recorded alongside the observed evidence so
    the validity gate can compare them.
    """
    import comfy.ops

    info = {}
    seen_first = {}
    seen_all = {}
    seen_input_dtypes = set()
    handles = []
    linear_type = comfy.ops.disable_weight_init.Linear

    def _make_hook():
        def _hook(module, args, kwargs):
            if args and len(args) > 0 and torch.is_tensor(args[0]):
                dtype = args[0].dtype
                cls = type(module).__name__
                seen_first.setdefault(cls, str(dtype))
                seen_all.setdefault(cls, set()).add(str(dtype))
                seen_input_dtypes.add(str(dtype))

        return _hook

    for _name, module in fixture.model.named_modules():
        if isinstance(module, linear_type):
            handles.append(module.register_forward_hook(_make_hook()))

    original_cast = comfy.ops.cast_bias_weight
    cast_state = {
        "calls": 0,
        "bytes": 0,
        "materialized_count": 0,
        "materialized_bytes": 0,
        "returned_dtypes": set(),
        "pairs": [],
    }

    def _counting_cast(module, *args, **kwargs):
        cast_state["calls"] += 1
        try:
            weight = module.weight
            if weight is not None and weight.numel() > 0:
                cast_state["bytes"] += int(weight.numel() * weight.element_size())
        except Exception:
            pass
        result = original_cast(module, *args, **kwargs)
        try:
            returned = result[0]
            resident_dtype = getattr(module.weight, "dtype", None)
            returned_dtype = getattr(returned, "dtype", None)
            is_linear = isinstance(module, linear_type)
            if resident_dtype is not None and returned_dtype is not None:
                returned_dtype_str = str(returned_dtype)
                if is_linear:
                    # GEMM weight-operand evidence only: Embedding/LayerNorm
                    # casts are not matmul operands (the Embedding returns its
                    # resident weight and casts the OUTPUT instead).
                    cast_state["returned_dtypes"].add(returned_dtype_str)
                if returned_dtype_str != str(resident_dtype):
                    # A real materialization happened: the returned weight
                    # differs in dtype from the resident weight.
                    cast_state["materialized_count"] += 1
                    n = int(module.weight.numel() if module.weight is not None else 0)
                    elem = getattr(returned, "element_size", lambda: 2)()
                    cast_state["materialized_bytes"] += int(n * elem)
                in_dtype = None
                if kwargs.get("input") is not None and torch.is_tensor(kwargs["input"]):
                    in_dtype = str(kwargs["input"].dtype)
                elif args and torch.is_tensor(args[0]):
                    in_dtype = str(args[0].dtype)
                cast_state["pairs"].append((type(module).__name__, in_dtype, returned_dtype_str))
        except Exception:
            pass
        return result

    comfy.ops.cast_bias_weight = _counting_cast
    try:
        t0 = time.perf_counter()
        out = _call_encode(fixture, autocast_spec)
        if use_cuda:
            torch.cuda.synchronize()
        cast_wall_ms = (time.perf_counter() - t0) * 1000.0
    finally:
        comfy.ops.cast_bias_weight = original_cast
        for handle in handles:
            handle.remove()

    def _single(dtypes):
        """The one observed dtype, or None when several dtypes were seen."""
        unique = sorted(dtypes)
        return unique[0] if len(unique) == 1 else None

    info["activation_dtype_by_linear_class"] = {k: v for k, v in seen_first.items()}
    info["linear_input_dtypes_seen"] = {k: sorted(v) for k, v in seen_all.items()}
    info["linear_input_dtypes_global"] = sorted(seen_input_dtypes)
    info["actual_linear_input_dtype"] = _single(seen_input_dtypes)
    info["actual_weight_compute_dtype_seen"] = _single(cast_state["returned_dtypes"])
    info["linear_input_dtypes_global"] = sorted(seen_input_dtypes)
    info["weight_dtypes_global"] = sorted(cast_state["returned_dtypes"])
    info["cast_pairs"] = cast_state["pairs"]
    info["output_dtypes"] = {
        "cond": str(out[0].dtype),
        "pooled": str(out[1].dtype) if len(out) > 1 and out[1] is not None else None,
    }
    info["cast_op_count"] = cast_state["calls"]
    info["cast_bytes"] = cast_state["bytes"]
    info["cast_materialized_count"] = cast_state["materialized_count"]
    info["cast_materialized_bytes"] = cast_state["materialized_bytes"]
    info["cast_wall_ms"] = cast_wall_ms
    info["requested_compute_dtype"] = str(policy_dtype) if policy_dtype is not None else None
    info["outputs"] = (
        out[0].detach().cpu(),
        out[1].detach().cpu() if len(out) > 1 and out[1] is not None else None,
    )
    return info


def _stability(fixture, autocast_spec, use_cuda, repeats=3):
    outs = []
    for _ in range(repeats):
        out = _call_encode(fixture, autocast_spec)
        cond = out[0].detach().float().cpu()
        pooled = out[1].detach().float().cpu() if len(out) > 1 and out[1] is not None else None
        outs.append((cond, pooled))
    max_deviation = 0.0
    for a, b in itertools.combinations(outs, 2):
        if a[0] is not None and b[0] is not None and a[0].numel() and b[0].numel():
            cosine = float(
                torch.nn.functional.cosine_similarity(
                    a[0].reshape(1, -1), b[0].reshape(1, -1)
                ).item()
            )
            max_deviation = max(max_deviation, abs(1.0 - cosine))
    return {"cond_max_cosine_deviation": max_deviation, "repeats": repeats}


def _op_bucket(name):
    lowered = name.lower()
    if any(k in lowered for k in ("addmm", "bmm", "matmul", "linear", "cublas", "gemm", "conv")):
        return "GEMM"
    if any(k in lowered for k in ("einsum", "softmax", "sdpa", "scaled_dot_product", "flash_attn", "mem_efficient")):
        return "ATTENTION"
    if any(k in lowered for k in ("layer_norm", "rms_norm", "group_norm", "batch_norm")):
        return "NORM"
    if any(k in lowered for k in ("gelu", "silu", "relu", "erf", "tanh", "sigmoid", "expm1")):
        return "ACTIVATION"
    if any(k in lowered for k in ("copy", "memcpy", "transpose", "permute", "contiguous", "cat", "expand", "repeat", "to(")):
        return "COPY"
    if any(k in lowered for k in ("synchronize", "stream_sync")):
        return "SYNC"
    return "OTHER"


def _deep_profile(fixture, autocast_spec, use_cuda):
    if not use_cuda:
        return {"status": "skipped_cpu"}
    buckets = {
        "GEMM": {"count": 0, "cpu_us": 0.0, "cuda_us": 0.0},
        "ATTENTION": {"count": 0, "cpu_us": 0.0, "cuda_us": 0.0},
        "NORM": {"count": 0, "cpu_us": 0.0, "cuda_us": 0.0},
        "ACTIVATION": {"count": 0, "cpu_us": 0.0, "cuda_us": 0.0},
        "COPY": {"count": 0, "cpu_us": 0.0, "cuda_us": 0.0},
        "SYNC": {"count": 0, "cpu_us": 0.0, "cuda_us": 0.0},
        "OTHER": {"count": 0, "cpu_us": 0.0, "cuda_us": 0.0},
    }
    with torch.profiler.profile(
        activities=[
            torch.profiler.ProfilerActivity.CPU,
            torch.profiler.ProfilerActivity.CUDA,
        ]
    ) as prof:
        _call_encode(fixture, autocast_spec)
    torch.cuda.synchronize()
    for event in prof.key_averages():
        bucket = _op_bucket(event.key)
        entry = buckets[bucket]
        entry["count"] += 1
        entry["cpu_us"] += float(event.self_cpu_time_total)
        cuda_us = getattr(event, "self_device_time_total", None)
        if cuda_us is None:
            cuda_us = getattr(event, "self_cuda_time_total", 0.0)
        entry["cuda_us"] += float(cuda_us)
    return buckets


def _unsupported_result(arm_id, plan_entry, base_identity):
    return {
        "identity": {
            **base_identity,
            "requested_compute_dtype": plan_entry.get("compute_dtype", None),
            "arm_resident_dtype": plan_entry.get("resident_dtype"),
            "mechanism": plan_entry.get("mechanism"),
        },
        "timing": {},
        "casting": {},
        "cuda": {},
        "classification": {"status": "UNSUPPORTED", "reason": plan_entry["reason"]},
        "attention_function": base_identity.get("attention_function"),
        "torch_globals_before": {},
        "torch_globals_after": {},
        "stability": {"skipped": True, "reason": plan_entry["reason"]},
        "deep": None,
        "structure": {"warmup_repeats": 0, "timed_repeats": 0, "total_encode_calls": 0},
        "validity": {"valid": False, "gated": True, "checks": {}},
        "one_time_resident_convert_ms": 0.0,
        "_verification_outputs": (None, None),
        "_last_repeat_output": (None, None),
    }


def run_arm(
    fixture,
    arm_id,
    mode="coarse",
    repeats=15,
    warmup=3,
    batch=1,
    plan_entry=None,
    seed=1234,
    run_device=None,
    quiet=False,
    on_encode=None,
):
    """Run one arm against one prepared fixture.  Returns a full result dict.

    Execution order per arm:
      1. snapshot globals, apply arm settings (TF32 for P1*)
      2. one-time resident-dtype conversion (B arms + P3A) OUTSIDE the timed
         region, wall measured separately as ``one_time_resident_convert_ms``
      3. transformer.forward wrap to the policy dtype (P2*/P3*)
      4. ``manual_cast_dtype`` override to the policy dtype (P2*/P3*)
      5. ``warmup`` encode calls OUTSIDE the timer
      6. ``repeats`` timed encode calls (wall + CUDA event per repeat)
      7. already-resident ``load_models_gpu`` re-entry wall (untimed)
      8. UNTIMED verification encode (activation-dtype hooks + cast accounting
         with materialized-vs-short-circuit split)
      9. 3-repeat stability pass; optional deep torch.profiler buckets
     10. validity gate (evidence-based low-precision check for the new arms)
     11. restore in REVERSE order (object patches, wrappers, resident state,
         torch globals) in ``finally`` -- exception-safe
    """
    use_cuda = _use_cuda(run_device)
    device = torch.device("cuda") if use_cuda else torch.device("cpu")

    if plan_entry is None:
        plan_entry = _plan_entry_for(arm_id, run_device)

    is_legacy = arm_id in LEGACY_ARM_IDS
    policy_dtype = _policy_dtype_for(arm_id, plan_entry)
    resident_dtype_name = plan_entry.get("resident_dtype")
    low_precision_arm = (not is_legacy) and arm_id in ("P2A", "P2B", "P3A", "P3B")

    base_identity = {
        "class": fixture.class_names,
        "param_count": fixture.param_count,
        "resident_dtype": str(fixture.resident_dtype),
        "actual_parameter_dtype": str(fixture.resident_dtype),
        "token_count": fixture.max_length,
        "batch": batch,
        "device": str(device),
        "attention_function": fixture.attention_function,
    }

    if plan_entry["status"] != "OK":
        return _unsupported_result(arm_id, plan_entry, base_identity)

    snapshot = GlobalTorchSettings.snapshot()
    autocast_spec = _autocast_spec(arm_id, plan_entry)
    wall_list = []
    cuda_list = []
    peaks = []
    allocated_before = None
    reserved_before = None
    allocated_after = None
    reserved_after = None
    last_out = None

    state_clone = None
    wrapped = []
    manual_prev = None
    manual_set = False
    one_time_resident_convert_ms = 0.0
    resident_arm_dtype = (
        resident_dtype_name if resident_dtype_name is not None else str(fixture.resident_dtype)
    )

    try:
        GlobalTorchSettings.apply(arm_id, plan_entry)

        # ── one-time resident-dtype conversion (outside the timed region) ──
        if resident_dtype_name is not None:
            resident_target = _dtype_from_name(resident_dtype_name)
            if str(fixture.resident_dtype) != str(resident_target):
                state_clone = _snapshot_model_state(fixture.model)
                t0 = time.perf_counter()
                fixture.model.to(dtype=resident_target)
                if use_cuda:
                    torch.cuda.synchronize()
                one_time_resident_convert_ms = (time.perf_counter() - t0) * 1000.0

        # ── true-low-precision seam: wrap transformer.forward + manual_cast ──
        if low_precision_arm:
            wrapped = _wrap_transformers(fixture.model, policy_dtype)
            manual_prev = _set_manual_cast_dtype(fixture, policy_dtype)
            manual_set = True

        for i in range(warmup):
            if on_encode is not None:
                on_encode(i, "warmup")
            _call_encode(fixture, autocast_spec)
        if use_cuda:
            torch.cuda.synchronize()

        for rep in range(repeats):
            if on_encode is not None:
                on_encode(warmup + rep, "timed")
            if use_cuda:
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                start_event = torch.cuda.Event(enable_timing=True)
                end_event = torch.cuda.Event(enable_timing=True)
                allocated_before = torch.cuda.memory_allocated()
                reserved_before = torch.cuda.memory_reserved()
                start_event.record()
                wall_t0 = time.perf_counter()
            else:
                wall_t0 = time.perf_counter()

            out = _call_encode(fixture, autocast_spec)
            last_out = out

            if use_cuda:
                end_event.record()
                torch.cuda.synchronize()
                wall_t1 = time.perf_counter()
                cuda_list.append(float(start_event.elapsed_time(end_event)))
                peaks.append(int(torch.cuda.max_memory_allocated()))
                allocated_after = torch.cuda.memory_allocated()
                reserved_after = torch.cuda.memory_reserved()
            else:
                wall_t1 = time.perf_counter()
            wall_list.append((wall_t1 - wall_t0) * 1000.0)

        # Already-resident load re-entry wall (same call CLIP.load_model uses).
        import comfy.model_management as mm

        t0 = time.perf_counter()
        mm.load_models_gpu([fixture.patcher])
        if use_cuda:
            torch.cuda.synchronize()
        load_reentry_wall_ms = (time.perf_counter() - t0) * 1000.0

        verification = _verification_pass(
            fixture, autocast_spec, use_cuda, policy_dtype=policy_dtype
        )

        post_forward_ms = 0.0
        if fixture.encode_kind == "wrapped" and fixture.clip is not None:
            t0 = time.perf_counter()
            fixture.model.encode_token_weights(fixture.encode_tokens)
            if use_cuda:
                torch.cuda.synchronize()
            raw_wall = (time.perf_counter() - t0) * 1000.0
            t0 = time.perf_counter()
            fixture.clip.encode_from_tokens(fixture.encode_tokens, return_pooled=True)
            if use_cuda:
                torch.cuda.synchronize()
            wrapped_wall = (time.perf_counter() - t0) * 1000.0
            post_forward_ms = max(0.0, wrapped_wall - raw_wall)

        stability = _stability(fixture, autocast_spec, use_cuda)

        deep = None
        if mode == "deep":
            deep = _deep_profile(fixture, autocast_spec, use_cuda)

        forward_median_ms = statistics.median(wall_list) if wall_list else None
        forward_mean_ms = statistics.mean(wall_list) if wall_list else None
        forward_std_ms = statistics.stdev(wall_list) if len(wall_list) > 1 else 0.0
        cuda_median_ms = statistics.median(cuda_list) if cuda_list else None
        cuda_mean_ms = statistics.mean(cuda_list) if cuda_list else None
        cuda_std_ms = statistics.stdev(cuda_list) if len(cuda_list) > 1 else 0.0
        peak_allocated = max(peaks) if peaks else None

        # ── hard validity gate (new arms only; legacy evidence is recorded) ──
        requested = str(policy_dtype)
        actual_in = verification.get("actual_linear_input_dtype")
        actual_w = verification.get("actual_weight_compute_dtype_seen")
        effective_manual = getattr(fixture.model, "manual_cast_dtype", None)
        effective_manual_str = str(effective_manual) if effective_manual is not None else "None"
        tf32_needed = bool(plan_entry.get("tf32", False))
        tf32_actual = bool(torch.backends.cuda.matmul.allow_tf32)

        checks = {
            "linear_input_dtype": actual_in == requested,
            "weight_compute_dtype": actual_w == requested,
            "manual_cast_dtype": effective_manual_str == requested,
            "tf32_enabled": (not tf32_needed) or tf32_actual,
        }
        valid = bool(
            checks["linear_input_dtype"]
            and checks["weight_compute_dtype"]
            and checks["manual_cast_dtype"]
            and checks["tf32_enabled"]
        )
        validity = {
            "valid": valid,
            "gated": not is_legacy,
            "requested_compute_dtype": requested,
            "actual_linear_input_dtype": actual_in,
            "actual_weight_compute_dtype_seen": actual_w,
            "manual_cast_dtype_during_arm": effective_manual_str,
            "allow_tf32_during_arm": tf32_actual,
            "sdpa_input_dtype_observed": actual_in,
            "sdpa_flash_capable": actual_in in ("torch.bfloat16", "torch.float16"),
            "checks": checks,
            "observed_linear_input_dtypes": verification.get("linear_input_dtypes_global"),
            "observed_weight_dtypes": verification.get("weight_dtypes_global"),
        }

        if is_legacy:
            classification = {"status": "OK", "reason": None}
        elif not valid:
            classification = {
                "status": (
                    ARM_INVALID_NOT_LOW_PRECISION if low_precision_arm else ARM_INVALID
                ),
                "reason": "validity gate failed: {}".format(
                    [k for k, v in checks.items() if not v]
                ),
            }
        else:
            classification = {"status": "OK", "reason": None}

        result = {
            "identity": {
                **base_identity,
                "requested_compute_dtype": plan_entry.get("compute_dtype", None),
                "arm_resident_dtype": resident_arm_dtype,
                "mechanism": plan_entry.get("mechanism"),
                "actual_activation_dtype": verification.get(
                    "activation_dtype_by_linear_class", {}
                ),
            },
            "timing": {
                "tokenize_wall_ms": fixture.tokenize_wall_ms,
                "one_time_resident_convert_ms": one_time_resident_convert_ms,
                "load_reentry_wall_ms": load_reentry_wall_ms,
                "forward_wall_median_ms": forward_median_ms,
                "forward_wall_mean_ms": forward_mean_ms,
                "forward_wall_std_ms": forward_std_ms,
                "forward_cuda_event_median_ms": cuda_median_ms,
                "forward_cuda_event_mean_ms": cuda_mean_ms,
                "forward_cuda_event_std_ms": cuda_std_ms,
                "forward_wall_ms_list": [round(x, 4) for x in wall_list],
                "forward_cuda_event_ms_list": [round(x, 4) for x in cuda_list],
                "post_forward_ms": post_forward_ms,
                "total_encode_ms": (
                    (forward_median_ms or 0.0) + (post_forward_ms or 0.0)
                ),
            },
            "casting": {
                "cast_op_count": verification["cast_op_count"],
                "cast_bytes": verification["cast_bytes"],
                "cast_materialized_count": verification["cast_materialized_count"],
                "cast_materialized_bytes": verification["cast_materialized_bytes"],
                "cast_wall_ms": verification["cast_wall_ms"],
                "per_forward_weight_rematerialization": verification["cast_op_count"] > 0,
                "per_forward_weight_materialized": verification["cast_materialized_count"] > 0,
                "manual_cast_dtype": str(fixture.patcher.object_patches.get("manual_cast_dtype")),
                "force_cast_weights": bool(fixture.patcher.force_cast_weights),
            },
            "cuda": {
                "allocated_before": allocated_before,
                "allocated_after": allocated_after,
                "peak_allocated": peak_allocated,
                "reserved_before": reserved_before,
                "reserved_after": reserved_after,
            },
            "classification": classification,
            "validity": validity,
            "torch_globals_before": snapshot,
            "torch_globals_after": None,
            "stability": stability,
            "deep": deep,
            "structure": {
                "warmup_repeats": warmup,
                "timed_repeats": repeats,
                "total_encode_calls": warmup + repeats,
            },
            "_restored": False,
            "verification": {k: v for k, v in verification.items() if k != "outputs"},
        }
        result["_verification_outputs"] = verification["outputs"]
        result["_last_repeat_output"] = (
            last_out[0].detach().cpu(),
            last_out[1].detach().cpu()
            if last_out is not None and len(last_out) > 1 and last_out[1] is not None
            else None,
        ) if last_out is not None else (None, None)
        return result
    finally:
        # Reverse-order, exception-safe restoration.
        try:
            if low_precision_arm and manual_set:
                _restore_manual_cast_dtype(fixture, manual_prev)
            for transformer, original in wrapped:
                transformer.forward = original
            if state_clone is not None:
                _restore_model_state(fixture.model, state_clone)
                state_clone = None
        finally:
            GlobalTorchSettings.restore(snapshot)
            if "result" in locals() and result is not None:
                restored = GlobalTorchSettings.snapshot()
                result["_restored"] = restored == snapshot
                result["torch_globals_after"] = restored


def _compare_outputs(reference, candidate):
    ref_cond, ref_pooled = reference
    cand_cond, cand_pooled = candidate
    cond_metrics = Correctness.compare(ref_cond, cand_cond)
    if ref_pooled is not None or cand_pooled is not None:
        pooled_metrics = Correctness.compare(ref_pooled, cand_pooled)
    else:
        pooled_metrics = {
            "class": Correctness.UNSUPPORTED,
            "reason": "encoder produces no pooled output",
        }
    classes = [cond_metrics["class"], pooled_metrics["class"]]
    if Correctness.INVALID in classes:
        overall = Correctness.INVALID
    elif Correctness.MATERIAL_DIFFERENCE in classes:
        overall = Correctness.MATERIAL_DIFFERENCE
    elif Correctness.NUMERICALLY_CLOSE in classes:
        overall = Correctness.NUMERICALLY_CLOSE
    elif Correctness.EXACT in classes:
        overall = Correctness.EXACT
    else:
        overall = Correctness.UNSUPPORTED
    return {"class": overall, "cond": cond_metrics, "pooled": pooled_metrics}


def run_matrix(
    fixture_ids,
    arm_ids,
    mode="coarse",
    repeats=15,
    warmup=3,
    batch=1,
    max_length=77,
    seed=1234,
    run_device=None,
    on_encode=None,
):
    """Iterate fixture x arm.  P0 runs first per fixture and becomes the
    correctness reference for the other arms."""
    device_kind, capability, bf16, fp16 = _device_info(run_device)
    plan = DtypePolicy.plan_arms(device_kind, capability, bf16, fp16)
    plan_by_arm = {entry["arm"]: entry for entry in plan}

    results = {
        "meta": {
            "device_kind": device_kind,
            "capability": list(capability) if capability else None,
            "torch_version": torch.__version__,
            "python_version": sys.version.split()[0],
            "comfy_version": None,
            "seed": seed,
            "max_length": max_length,
            "batch": batch,
            "mode": mode,
            "repeats": repeats,
            "warmup": warmup,
        },
        "arms": plan,
        "fixtures": {},
    }
    try:
        import comfy
        results["meta"]["comfy_version"] = getattr(comfy, "__version__", "unknown")
    except Exception:
        pass

    for fixture_id in fixture_ids:
        fixture_entry = {"identity": {}, "arms": {}, "correctness": {}, "stability": {}}
        results["fixtures"][fixture_id] = fixture_entry
        try:
            fixture = prepare_fixture(
                fixture_id, seed=seed, max_length=max_length, batch=batch,
                run_device=run_device,
            )
        except Exception as exc:
            fixture_entry["status"] = "unavailable"
            fixture_entry["reason"] = "{}: {}".format(type(exc).__name__, exc)
            continue
        fixture_entry["status"] = "ok"
        fixture_entry["identity"] = fixture.identity

        # P0A is the correctness reference (P0 for legacy-only runs).
        reference_arm = "P0A" if "P0A" in arm_ids else ("P0" if "P0" in arm_ids else None)
        p0_reference = None
        for arm_id in arm_ids:
            arm_result = run_arm(
                fixture,
                arm_id,
                mode=mode,
                repeats=repeats,
                warmup=warmup,
                batch=batch,
                plan_entry=plan_by_arm[arm_id],
                seed=seed,
                run_device=run_device,
                on_encode=on_encode,
            )
            fixture_entry["arms"][arm_id] = arm_result
            fixture_entry["stability"][arm_id] = arm_result["stability"]

            if (
                reference_arm is not None
                and arm_id == reference_arm
                and arm_result["classification"]["status"] == "OK"
            ):
                p0_reference = arm_result["_last_repeat_output"]
            elif (
                reference_arm is not None
                and arm_id != reference_arm
                and p0_reference is not None
                and arm_result["classification"]["status"] == "OK"
            ):
                candidate = arm_result["_last_repeat_output"]
                if candidate is not None and candidate[0] is not None:
                    fixture_entry["correctness"][arm_id] = _compare_outputs(
                        p0_reference, candidate
                    )

        if reference_arm is None:
            fixture_entry["correctness"]["note"] = "no P0A/P0 reference arm run"

    return results


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, torch.dtype):
        return str(value)
    if isinstance(value, torch.Tensor):
        return {
            "__tensor__": True,
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "device": str(value.device),
        }
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        return str(value)
    except Exception:
        return None


def _resolve_fixtures(raw):
    if raw is None:
        return list(FIXTURE_IDS)
    items = [x.strip() for x in raw.split(",") if x.strip()]
    if items == ["all"]:
        return list(FIXTURE_IDS)
    for item in items:
        if item not in FIXTURE_IDS:
            raise SystemExit("unknown fixture: {!r} (available: {})".format(item, ", ".join(FIXTURE_IDS)))
    return items


def _resolve_arms(raw):
    if raw is None:
        return list(DEFAULT_ARMS)
    items = [x.strip() for x in raw.split(",") if x.strip()]
    if items == ["all"]:
        return list(ARM_IDS)
    for item in items:
        if item not in ARM_IDS:
            raise SystemExit("unknown arm: {!r} (available: {})".format(item, ", ".join(ARM_IDS)))
    return items


def main(argv=None):
    parser = _build_arg_parser()
    args, unknown = parser.parse_known_args(argv)
    # comfy.cli_args parses sys.argv at import time — keep only unknown args.
    sys.argv = [sys.argv[0]] + unknown

    # Env-var overrides for runs through the embedded python.
    if args.fixtures is None and os.environ.get("COMFYMODAL_D7_FIXTURES"):
        args.fixtures = os.environ["COMFYMODAL_D7_FIXTURES"]
    if args.arms is None and os.environ.get("COMFYMODAL_D7_ARMS"):
        args.arms = os.environ["COMFYMODAL_D7_ARMS"]
    if os.environ.get("COMFYMODAL_D7_MODE"):
        args.mode = os.environ["COMFYMODAL_D7_MODE"]
    if os.environ.get("COMFYMODAL_D7_REPEATS"):
        try:
            args.repeats = int(os.environ["COMFYMODAL_D7_REPEATS"])
        except ValueError:
            pass

    if args.quick:
        args.repeats = 5
        args.warmup = 1

    fixture_ids = _resolve_fixtures(args.fixtures)
    arm_ids = _resolve_arms(args.arms)

    if args.list_fixtures:
        for fid in FIXTURE_IDS:
            print(fid)
        return 0

    _ensure_comfy_importable(args.comfy_dir)

    device_kind, capability, bf16, fp16 = _device_info(None)
    plan = DtypePolicy.plan_arms(device_kind, capability, bf16, fp16)
    print("{} device={} capability={}".format(_HUMAN_PREFIX, device_kind, list(capability) if capability else None))
    for entry in plan:
        print(
            "{} arm_plan {} status={} compute={}{}".format(
                _HUMAN_PREFIX,
                entry["arm"],
                entry["status"],
                entry["compute_dtype"],
                "" if entry["status"] == "OK" else " reason={}".format(entry["reason"]),
            )
        )

    if not torch.cuda.is_available() and not all(
        entry["status"] == "UNSUPPORTED" for entry in plan
    ):
        # CPU-only: P0 (and nothing else) can run if the fixtures build on CPU.
        print("{} warning: CUDA unavailable; only P0 is runnable (on CPU).".format(_HUMAN_PREFIX))

    try:
        results = run_matrix(
            fixture_ids,
            arm_ids,
            mode=args.mode,
            repeats=args.repeats,
            warmup=args.warmup,
            batch=args.batch,
            max_length=args.max_length,
            seed=args.seed,
            run_device=None,
        )
    except Exception as exc:
        error_doc = {
            "status": "error",
            "error": "{}: {}".format(type(exc).__name__, exc),
            "fixtures": fixture_ids,
            "arms": arm_ids,
        }
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(error_doc, fh, indent=2)
        print("{} FATAL: {}: {}".format(_HUMAN_PREFIX, type(exc).__name__, exc))
        return 1

    for fixture_id in fixture_ids:
        entry = results["fixtures"].get(fixture_id, {})
        if entry.get("status") == "unavailable":
            print(
                "{} fixture={} status=unavailable reason={}".format(
                    _HUMAN_PREFIX, fixture_id, entry.get("reason")
                )
            )
            continue
        for arm_id in arm_ids:
            arm = entry.get("arms", {}).get(arm_id)
            if not arm:
                continue
            status = arm["classification"]["status"]
            if status == "UNSUPPORTED":
                print(
                    "{} fixture={} arm={} status=UNSUPPORTED reason={}".format(
                        _HUMAN_PREFIX,
                        fixture_id,
                        arm_id,
                        arm["classification"]["reason"],
                    )
                )
                continue
            validity = arm.get("validity") or {}
            actual_act = validity.get("actual_linear_input_dtype")
            v_flag = (
                "VALID" if validity.get("valid") else "INVALID"
                if validity.get("gated") else "INFO"
            )
            timing = arm["timing"]
            correctness = entry.get("correctness", {}).get(arm_id)
            cls = correctness["class"] if correctness else "n/a"
            if status != "OK":
                print(
                    "{} fixture={} arm={} status={} actual_act={} validity={} reason={}".format(
                        _HUMAN_PREFIX,
                        fixture_id,
                        arm_id,
                        status,
                        actual_act,
                        v_flag,
                        arm["classification"]["reason"],
                    )
                )
                continue
            print(
                "{} fixture={} arm={} status=OK actual_act={} validity={} forward_median_ms={:.3f} cuda_event_ms={} class={}".format(
                    _HUMAN_PREFIX,
                    fixture_id,
                    arm_id,
                    actual_act,
                    v_flag,
                    timing.get("forward_wall_median_ms") or 0.0,
                    "{:.3f}".format(timing.get("forward_cuda_event_median_ms"))
                    if timing.get("forward_cuda_event_median_ms") is not None
                    else "n/a",
                    cls,
                )
            )
            resident_ms = timing.get("one_time_resident_convert_ms")
            if resident_ms:
                print(
                    "{} fixture={} arm={} one_time_resident_convert_ms={:.3f}".format(
                        _HUMAN_PREFIX, fixture_id, arm_id, resident_ms
                    )
                )
            print(
                "{} fixture={} arm={} settings_restored={}".format(
                    _HUMAN_PREFIX,
                    fixture_id,
                    arm_id,
                    arm.get("_restored", True),
                )
            )

    if args.json:
        safe = _json_safe(results)
        for fid in results["fixtures"]:
            entry = safe["fixtures"][fid]
            if "arms" in entry:
                for arm_id in list(entry["arms"]):
                    arm = entry["arms"][arm_id]
                    for private in ("_verification_outputs", "_last_repeat_output"):
                        arm.pop(private, None)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(safe, fh, indent=2, default=str)
        print("{} wrote json -> {}".format(_HUMAN_PREFIX, args.json))

    return 0


if __name__ == "__main__":
    sys.exit(main())

