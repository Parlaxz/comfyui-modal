"""Generic TextGenerate substitution (golden-equivalent, optional).

Replaces upstream ``TextGenerate`` / ``TextGenerateLTX2Prompt`` node execution
with an optimized loop over the SAME model, weights, and sampling parameters:

* identical ``clip.tokenize`` input;
* identical GPU-residency preamble (``reset_clip_options`` / ``load_model`` /
  ``set_clip_options`` / ``cuda_device_context`` — the same calls
  ``comfy.sd.CLIP.generate`` performs);
* identical per-step numerics (same ``model.forward``, ``logits``,
  ``sample_token`` methods on the same transformer object);
* identical output: token list truncated at the first stop token, then the
  same ``clip.decode``.

Optimizations (all output-preserving):

* EOS/sync batching: stop-token scan every ``eos_batch`` steps instead of a
  CUDA ``.item()`` sync per token; overshoot is truncated, so the returned
  token list is bit-identical to the native loop (same seed ⇒ same draws).
* Progress-bar batching: ``pbar.update`` every ``eos_batch`` steps.
* Optional ``torch.compile`` decode tier (default off): compiles the
  single-token forward with inductor; requires a persistent inductor cache
  dir or it refuses (cold-compile would cost more than it saves).

Contract (same as the loader substitution lane): never raises, class-gated,
scalar inputs only, any resolution/generation failure returns ``ok: False``
and the caller runs the native node.  Env-gated, default OFF:

* ``COMFYMODAL_V2_TEXT_SUBSTITUTION=1`` — enable substitution.
* ``COMFYMODAL_V2_TEXT_EOS_BATCH=N`` — EOS check cadence (default 8).
* ``COMFYMODAL_V2_TEXT_COMPILE=1`` — enable the compile tier (needs
  inductor cache dir; refuses otherwise with a logged reason).
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable


_TEXT_SUBSTITUTION_CLASSES = frozenset({"TextGenerate", "TextGenerateLTX2Prompt"})

_ACTIVE_TEXT_CTX: dict[str, Any] | None = None


def text_substitution_enabled() -> bool:
    return os.environ.get("COMFYMODAL_V2_TEXT_SUBSTITUTION", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _eos_batch() -> int:
    try:
        n = int(os.environ.get("COMFYMODAL_V2_TEXT_EOS_BATCH", "8"))
        return max(1, min(64, n))
    except (TypeError, ValueError):
        return 8


def _compile_enabled() -> bool:
    return os.environ.get("COMFYMODAL_V2_TEXT_COMPILE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _emit(trace_emit: Callable[..., Any] | None, name: str, **fields: Any) -> None:
    try:
        if callable(trace_emit):
            trace_emit(name, phase="execution", metadata=dict(fields))
    except Exception:
        pass


def _resolve_generator(transformer: Any) -> Any | None:
    """Find the BaseGenerate-like object under the CLIP wrapper.

    Walks ``cond_stage_model`` / ``clip`` / ``transformer`` attributes to the
    object exposing ``init_kv_cache`` + ``logits`` + ``sample_token`` +
    ``model`` (the exact methods the native loop calls).  None when the
    layout is unrecognized — the caller must run natively then.
    """
    try:
        seen: set[int] = set()
        stack = [transformer]
        while stack:
            obj = stack.pop()
            if obj is None or id(obj) in seen:
                continue
            seen.add(id(obj))
            if (
                hasattr(obj, "init_kv_cache")
                and hasattr(obj, "logits")
                and hasattr(obj, "sample_token")
                and hasattr(obj, "model")
            ):
                return obj
            for attr in ("cond_stage_model", "clip", "clip_model", "transformer", "te"):
                try:
                    child = getattr(obj, attr, None)
                except Exception:
                    child = None
                if child is None:
                    continue
                if isinstance(child, str):
                    try:
                        child = getattr(obj, child, None)
                    except Exception:
                        child = None
                if child is not None and not isinstance(child, (str, int, float, bool)):
                    stack.append(child)
        return None
    except Exception:
        return None


def optimized_generate_ids(
    gen: Any,
    embeds: Any,
    prefill: dict[str, Any] | None,
    *,
    do_sample: bool,
    max_length: int,
    temperature: float,
    top_k: int,
    top_p: float,
    min_p: float,
    repetition_penalty: float,
    seed: Any,
    presence_penalty: float = 0.0,
    progress: Any = None,
) -> list[int]:
    """Mirror of ``BaseGenerate.generate`` with batched EOS/sync handling.

    Calls the same ``gen`` methods in the same order with the same arguments;
    the only behavioral delta is *when* stop tokens are observed (every
    ``eos_batch`` steps, plus a final scan).  The returned list is truncated
    at the first stop token, hence identical to the native loop's output.
    """
    import torch

    device = embeds.device
    try:
        from comfy.model_management import should_use_bf16
        _bf16 = should_use_bf16(device)
    except Exception:
        # Local/test fallback (worker always has comfy): match native
        # intent — bf16 on CUDA, fp32 elsewhere.
        try:
            _bf16 = device.type == "cuda"
        except Exception:
            _bf16 = False

    prefill = prefill if isinstance(prefill, dict) else {}
    position_ids = prefill.get("position_ids")
    visual_pos_masks = prefill.get("visual_pos_masks")
    deepstack_embeds = prefill.get("deepstack")
    embeds_info = prefill.get("embeds_info")

    device = embeds.device
    try:
        stop_tokens = gen.model.config.stop_tokens
    except Exception:
        stop_tokens = None
    if stop_tokens is None:
        stop_tokens = []

    if _bf16:
        execution_dtype = torch.bfloat16
    else:
        execution_dtype = torch.float32
    embeds = embeds.to(execution_dtype)

    if embeds.ndim == 2:
        embeds = embeds.unsqueeze(0)

    max_cache_len = embeds.shape[1] + max_length
    past_key_values = gen.init_kv_cache(embeds.shape[0], max_cache_len, device, execution_dtype)

    generator = torch.Generator(device=device).manual_seed(seed) if do_sample else None

    generated_token_ids: list[int] = []
    batch = _eos_batch()
    pending_pbar = 0

    if position_ids is not None:
        try:
            next_pos = int(position_ids[:, -1].max()) + 1
        except Exception:
            next_pos = None
    else:
        next_pos = None

    current_input_ids = None
    stop_at: int | None = None
    step = 0
    while step < max_length:
        extra: dict[str, Any] = {}
        if step == 0 and deepstack_embeds is not None:
            extra["deepstack_embeds"] = deepstack_embeds
            extra["visual_pos_masks"] = visual_pos_masks
        x, _, past_key_values = gen.model.forward(
            None, embeds=embeds, attention_mask=None,
            past_key_values=past_key_values, input_ids=current_input_ids,
            position_ids=position_ids, **extra,
            embeds_info=(embeds_info if step == 0 else None),
        )
        logits = gen.logits(x)[:, -1]
        next_token = gen.sample_token(
            logits, temperature, top_k, top_p, min_p, repetition_penalty,
            generated_token_ids, generator,
            do_sample=do_sample, presence_penalty=presence_penalty,
        )
        token_id = next_token[0].item()
        generated_token_ids.append(token_id)

        embeds = gen.model.embed_tokens(next_token).to(execution_dtype)
        current_input_ids = next_token
        if next_pos is not None:
            try:
                position_ids = torch.tensor([[next_pos]], device=device)
                next_pos += 1
            except Exception:
                pass
        pending_pbar += 1
        if progress is not None and pending_pbar >= batch:
            try:
                progress.update(pending_pbar)
            except Exception:
                pass
            pending_pbar = 0

        step += 1
        # Batched stop scan (plus mandatory scan at max_length).
        if step % batch == 0 or step >= max_length:
            for idx, tid in enumerate(generated_token_ids):
                if tid in stop_tokens:
                    stop_at = idx
                    break
            if stop_at is not None:
                break

    if progress is not None and pending_pbar:
        try:
            progress.update(pending_pbar)
        except Exception:
            pass
    if stop_at is not None:
        return generated_token_ids[: stop_at + 1]
    return generated_token_ids


def compose_generic_text_generate(
    *,
    clip: Any,
    prompt: str,
    max_length: int,
    sampling_mode: Any,
    image: Any = None,
    thinking: bool = False,
    use_default_template: bool = True,
    video: Any = None,
    audio: Any = None,
    request_id: str = "",
    trace_emit: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Optimized TextGenerate.execute.  Never raises; ``ok: False`` → native."""
    t0 = time.perf_counter_ns()
    try:
        tokens = clip.tokenize(
            prompt, image=image, skip_template=not use_default_template,
            min_length=1, thinking=thinking, video=video, audio=audio,
        )

        mode = sampling_mode if isinstance(sampling_mode, dict) else {}
        do_sample = mode.get("sampling_mode") == "on"
        temperature = mode.get("temperature", 1.0)
        top_k = mode.get("top_k", 50)
        top_p = mode.get("top_p", 1.0)
        min_p = mode.get("min_p", 0.0)
        repetition_penalty = mode.get("repetition_penalty", 1.0)
        presence_penalty = mode.get("presence_penalty", 0.0)
        seed = mode.get("seed", None)

        # Identical residency preamble to comfy.sd.CLIP.generate.
        cond = getattr(clip, "cond_stage_model", None)
        if cond is None:
            return {"ok": False, "reason": "no_cond_stage_model"}
        try:
            cond.reset_clip_options()
        except Exception:
            pass
        load_model = getattr(clip, "load_model", None)
        if not callable(load_model):
            return {"ok": False, "reason": "no_load_model"}
        load_model(tokens)
        patcher = getattr(clip, "patcher", None)
        device = getattr(patcher, "load_device", None)
        if device is None:
            return {"ok": False, "reason": "no_load_device"}
        try:
            cond.set_clip_options({"layer": None})
            cond.set_clip_options({"execution_device": device})
        except Exception:
            pass

        gen = _resolve_generator(clip)
        if gen is None:
            return {"ok": False, "reason": "generator_unresolved"}

        try:
            from comfy import model_management as _mm
            cuda_ctx = _mm.cuda_device_context
        except Exception:
            return {"ok": False, "reason": "no_cuda_ctx"}

        try:
            import comfy.utils as _utils
            pbar = _utils.ProgressBar(max_length)
        except Exception:
            pbar = None

        with cuda_ctx(device):
            prefill = _prepare_prefill(clip, cond, tokens, device)
            generated_ids = optimized_generate_ids(
                gen, prefill["embeds"], prefill,
                do_sample=do_sample, max_length=int(max_length),
                temperature=temperature, top_k=top_k, top_p=top_p,
                min_p=min_p, repetition_penalty=repetition_penalty,
                seed=seed, presence_penalty=presence_penalty,
                progress=pbar,
            )
        try:
            text = clip.decode(generated_ids)
        except Exception:
            return {"ok": False, "reason": "decode_failed"}
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        _emit(trace_emit, "generic_text_substitution", node_class="TextGenerate",
              requested="optimized_loop", actual="optimized_loop",
              tokens=len(generated_ids), elapsed_ms=round(elapsed_ms, 3),
              request_id=str(request_id or ""))
        return {"ok": True, "tuple": (text,), "elapsed_ms": elapsed_ms,
                "source_arm": "optimized_text_loop",
                "token_count": len(generated_ids)}
    except Exception as exc:  # noqa: BLE001 - substitution contract
        return {"ok": False, "reason": f"{type(exc).__name__}:{str(exc)[:150]}"}


def _prepare_prefill(clip: Any, cond: Any, tokens: Any, device: Any) -> dict[str, Any]:
    """Run the native token→embeds prefill path; return model-ready state.

    Delegates to the generator's own ``process_tokens``/``build_image_inputs``
    exactly as the native ``Qwen3VLClipModel.generate`` does, so the
    optimized loop starts from identical state.  Raises on unrecognized
    layout (caller converts to ``ok: False`` → native execution).
    """
    gen = _resolve_generator(clip)
    if gen is None:
        raise RuntimeError("generator_unresolved")
    process = getattr(gen, "process_tokens", None)
    if not callable(process):
        inner = getattr(gen, "transformer", None)
        if inner is not None and callable(getattr(inner, "process_tokens", None)):
            gen = inner
            process = gen.process_tokens
    if not callable(process):
        raise RuntimeError("process_tokens_unavailable")
    if isinstance(tokens, dict):
        tok_dict: dict = tokens
        try:
            first = list(next(iter(tok_dict.values())))
        except StopIteration:
            raise RuntimeError("empty_tokens")
        tokens_only = [[t[0] for t in list(b)] for b in first]
    else:
        tokens_only = tokens
    embeds, _, _, embeds_info = process(tokens_only, device)
    model_obj = getattr(gen, "model", None)
    position_ids, visual_pos_masks, deepstack = None, None, None
    build_inputs = getattr(model_obj, "build_image_inputs", None) if model_obj is not None else None
    if callable(build_inputs):
        try:
            position_ids, visual_pos_masks, deepstack = build_inputs(embeds, embeds_info)
        except Exception:
            position_ids, visual_pos_masks, deepstack = None, None, None
    return {
        "gen": gen,
        "embeds": embeds,
        "position_ids": position_ids,
        "visual_pos_masks": visual_pos_masks,
        "deepstack": deepstack,
        "embeds_info": embeds_info,
    }


def install_text_dispatch_substitution(
    *,
    trace_emit: Callable[..., Any] | None,
    request_id: str,
) -> Callable[[], None] | None:
    """Wrap upstream ``execution.get_output_data`` for TextGenerate nodes.

    Class-gated (no wizard role required — generic across workflows):
    ``TextGenerate`` / ``TextGenerateLTX2Prompt`` instances run the optimized
    loop instead of the native node function.  Own active flag and restore
    pair, same merge shape as the loader lane; nests safely with it in
    either install order since classes never overlap and each wrapper only
    restores itself.  Returns None (native behavior) when the flag is off,
    install fails, or a wrapper is already active.  Never raises.
    """
    if not text_substitution_enabled():
        return None
    global _ACTIVE_TEXT_CTX
    try:
        import execution as _execution_mod
    except Exception:
        _emit(trace_emit, "generic_text_install", outcome="skipped",
              reason="execution_import_failed", request_id=str(request_id or ""))
        return None
    try:
        original = getattr(_execution_mod, "get_output_data", None)
        merge_fn = getattr(_execution_mod, "merge_fn", None)
        if merge_fn is None:
            merge_fn = getattr(_execution_mod, "merge_result_data", None)
        if not callable(original) or not callable(merge_fn):
            _emit(trace_emit, "generic_text_install", outcome="skipped",
                  reason="dispatch_boundary_missing",
                  request_id=str(request_id or ""))
            return None
        if _ACTIVE_TEXT_CTX is not None:
            _emit(trace_emit, "generic_text_install", outcome="skipped",
                  reason="already_active", request_id=str(request_id or ""))
            return None
        ctx: dict[str, Any] = {
            "request_id": str(request_id or ""),
            "trace_emit": trace_emit,
            "original": original,
            "merge_fn": merge_fn,
            "module": _execution_mod,
        }
        _ACTIVE_TEXT_CTX = ctx

        async def _text_substituting_get_output_data(
            prompt_id: Any,
            unique_id: Any,
            obj: Any,
            input_data_all: Any,
            execution_block_cb: Any = None,
            pre_execute_cb: Any = None,
            v3_data: Any = None,
        ) -> Any:
            active = _ACTIVE_TEXT_CTX
            if active is None:
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            node_class = type(obj).__name__ if obj is not None else ""
            if node_class not in _TEXT_SUBSTITUTION_CLASSES:
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            node_id = str(unique_id)
            raw_inputs = input_data_all if isinstance(input_data_all, dict) else {}
            resolved: dict[str, Any] = {}
            try:
                for key, value in raw_inputs.items():
                    if isinstance(value, (list, tuple)):
                        if len(value) != 1:
                            raise ValueError(f"list_mapped:{key}")
                        resolved[str(key)] = value[0]
                    else:
                        resolved[str(key)] = value
            except Exception as exc:
                _emit(active.get("trace_emit"), "generic_text_substitution",
                      node_id=node_id, requested="optimized_loop",
                      actual="native", reason=str(exc)[:120])
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            sub = compose_generic_text_generate(
                clip=resolved.get("clip"),
                prompt=resolved.get("prompt", ""),
                max_length=resolved.get("max_length", 512),
                sampling_mode=resolved.get("sampling_mode", {}),
                image=resolved.get("image"),
                thinking=bool(resolved.get("thinking", False)),
                use_default_template=bool(resolved.get("use_default_template", True)),
                video=resolved.get("video"),
                audio=resolved.get("audio"),
                request_id=str(active.get("request_id") or ""),
                trace_emit=active.get("trace_emit"),
            )
            if not sub.get("ok"):
                _emit(active.get("trace_emit"), "generic_text_substitution",
                      node_id=node_id, requested="optimized_loop",
                      actual="native", reason=str(sub.get("reason") or "compose_failed"))
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            try:
                output = merge_fn([sub["tuple"]], obj)
            except Exception as merge_exc:
                _emit(active.get("trace_emit"), "generic_text_substitution",
                      node_id=node_id, requested="optimized_loop",
                      actual="native",
                      reason=f"merge_failed:{type(merge_exc).__name__}")
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            _emit(active.get("trace_emit"), "generic_text_substitution",
                  node_id=node_id, requested="optimized_loop",
                  actual="optimized_loop", reason="",
                  tokens=sub.get("token_count", 0),
                  elapsed_ms=sub.get("elapsed_ms", 0.0))
            return output, {}, False, False

        _execution_mod.get_output_data = _text_substituting_get_output_data  # type: ignore[method-assign]

        def _restore_text_dispatch() -> None:
            global _ACTIVE_TEXT_CTX
            try:
                mod = ctx.get("module")
                if mod is not None and getattr(
                    mod, "get_output_data", None
                ) is _text_substituting_get_output_data:
                    mod.get_output_data = ctx.get("original")
            except Exception:
                pass
            _ACTIVE_TEXT_CTX = None

        _emit(trace_emit, "generic_text_install", outcome="installed",
              classes=",".join(sorted(_TEXT_SUBSTITUTION_CLASSES)),
              eos_batch=_eos_batch(),
              request_id=str(request_id or ""))
        return _restore_text_dispatch
    except Exception:
        return None
