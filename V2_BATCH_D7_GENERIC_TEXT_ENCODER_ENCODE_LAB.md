# V2 Batch D7 — Generic Text-Encoder ENCODE Lab (FP32 / TF32 / BF16 / FP16)

Date: 2026-08-16 · Branch: current main (no branch, no worktree) · Commit: **none**
Modal requests: **0** · Deploys: **0** · Paid runs: **0** · Downloads: **0**

Zero-spend laboratory answering: *when a ComfyUI text encoder is already fully GPU-resident, how long does encoding itself take, and how does generic compute-dtype policy affect that time?*

Runtime: RTX 3070 (Ampere sm_86, 8 GB) · torch 2.8.0+cu128 (system python 3.11.9) · pinned ComfyUI v0.24.0 (f49bdb6).

---

## 1. Executive conclusion

**Text-encoder ENCODE is 7–27 ms in the measured generic fixtures (77 tokens, batch 1, GPU-resident, CUDA-event device time). It is launch/memory-bound, not tensor-core-bound, and no generic dtype arm reliably speeds it up at production token counts.**

- P0 (current Comfy behavior: hardcoded fp32 compute, fp16 resident weights) is **already the fastest or tied-fastest arm** on 4 of 5 fixtures. TF32, BF16, FP16 arms were neutral-to-slower (up to +40%).
- The dominant generic cost is **uncached per-forward weight rematerialization**: every Linear layer casts its resident fp16 weight to fp32 on **every** encode (99–195 cast ops, 126–417 MB moved per forward; cast CPU wall ≈ the forward wall itself). This tax is paid in *every* arm.
- Comfy's generic wrapper is confirmed to force this: `sd.py:254-255` `set_model_compute_dtype(torch.float32)` → `force_cast_weights=True` + `manual_cast_dtype` object patch; compute input dtype is hardcoded fp32 (`sd1_clip.py:213,279`); `ops.py:375-376` re-casts per forward with no cache.
- **Correctness:** FP16 and TF32 outputs are NUMERICALLY_CLOSE to P0 (max abs err ~2–4e-3, cosine ≈ 1.0, 100% finite). BF16 is **MATERIAL_DIFFERENCE** on these fixtures (max abs err ~2.5–3.5e-2) — an honest classification, not a crash; bf16's 7-bit mantissa is real.
- **For the 12-second goal, encode time is a non-issue:** even a large production encoder fits inside the UNET lane's 2.4–2.7 s. The measured overheads that matter (output D2H copy 7–10 ms; `load_models_gpu` re-entry 7–17 ms) are milliseconds — nothing on the 2.6 s exposed budget.
- Biggest generic wins ranked: (1) eliminate the per-forward weight cast (resident == compute dtype, or cache the cast), (2) defer/eliminate the output intermediate-device copy, (3) avoid `load_models_gpu` re-entry overhead. **None of these is a dtype-policy change.** A dtype-policy production experiment is not recommended on this evidence.

## 2. Generic Comfy encode call graph (pinned v0.24.0, verified from source)

```
CLIPTextEncode.encode (nodes.py:75)  [custom node hooks CLIPTextEncode.encode only for
  │                                    the exact-conditioning-cache pre-check; no dtype changes]
  ├─ clip.tokenize(text) (sd.py:307) → SD1Tokenizer.tokenize_with_weights (sd1_clip.py:566)
  │     CPU-only; real bundled tokenizer measured 0.5–0.8 ms
  └─ clip.encode_from_tokens_scheduled (sd.py:320) → encode_from_tokens (sd.py:381)
       ├─ reset/set_clip_options (sd.py:382-388)
       ├─ self.load_model(tokens) (sd.py:390) → model_management.load_models_gpu (843)
       │     → LoadedModel.model_load (718) → ModelPatcher.partially_load (1202)
       │     → patch_model (applies object_patches incl. manual_cast_dtype, 1061-1064)
       │     → load (928): patch_weight_to_device (1021) + torch.cuda.synchronize (1023)
       ├─ with model_management.cuda_device_context(device) (sd.py:394)   # device only, NO autocast
       ├─ cond_stage_model.encode_token_weights(tokens) (sd.py:395)
       │     = ClipTokenWeightEncoder.encode_token_weights (sd1_clip.py:28)
       │       → SDClipModel.forward (sd1_clip.py:260)
       │           ├─ process_tokens: embeddings FORCED fp32 (sd1_clip.py:213, 237)
       │           ├─ transformer(..., dtype=torch.float32) (sd1_clip.py:279)  # HARDCODED
       │           └─ CLIPTextModel_.forward (clip_model.py:163) → CLIPEncoder
       │                → optimized_attention_for_device(small_input=True) (clip_model.py:115)
       │                → attention_pytorch (SDPA) [runtime-confirmed; fp32 → math backend]
       │       → output postprocess: pooled[0:1].to(intermediate_device) + cond cat .to(intermediate_device)
       │         (sd1_clip.py:48-68) — blocking GPU→CPU copy (CPU by default)
       └─ sd.py:397-408: no further dtype/device changes → [[cond, {"pooled_output": pooled}]]
consumed by comfy/conds.py CONDRegular → sampler_helpers.convert_cond → UNet extra_conds
  (cond moved back to GPU lazily at first UNet forward, model_base.py e.g. :873)
```

### Dtype-affecting locations (CONFIRMED from source unless noted)

| Concern | Location | Finding |
|---|---|---|
| Compute dtype | `sd.py:255` → `model_patcher.py:686-690` | `set_model_compute_dtype(torch.float32)`; sets `object_patches["manual_cast_dtype"]=fp32` AND `force_cast_weights=True` |
| Compute dtype | `sd1_clip.py:279` | transformer called with `dtype=torch.float32` hardcoded |
| Input activation dtype | `sd1_clip.py:213,237` | embeddings forced fp32 |
| Autocast | whole `comfy/` tree | **none active** on the encode path; only `get_autocast_device` helper (`model_management.py:1208`); only `torch.autocast` call is in `attention_split` upcast branch (not default) |
| Resident weight dtype | `model_management.py:1150-1165` | `text_encoder_dtype()` default **fp16** (CLI flags `--fp16/--bf16/--fp32-text-enc` etc. change storage only) |
| Weight casting during forward | `ops.py:281,375-376` | `cast_bias_weight`: dtype derived from **input** dtype; `weight.to(dtype)` per forward when mismatch; **uncached** (`cast_to` short-circuits only when dtype already matches) |
| Output dtype / device | `sd1_clip.py:46-68` | cond + pooled cast `.float()` (fp32) and moved to `intermediate_device()` = **CPU** by default (`model_management.py:1168-1172`) — blocking D2H copy per encode |
| Attention backend | `attention.py:778-791` | `attention_pytorch` (SDPA) if `pytorch_attention_enabled()` (runtime-confirmed True on torch 2.8) else `attention_basic`; fp32 → SDPA **math** backend (flash/FA2 are fp16/bf16-only) |
| TF32 | whole `comfy/` tree | **untouched** (PyTorch default: `allow_tf32=False` since 1.12) |
| CUDA sync | `model_patcher.py:1023` | per-module `torch.cuda.synchronize()` during load only; `soft_empty_cache` (1944) on free_memory |
| Load-path dtype | `model_patcher.py:855-857,1029` | storage dtype preserved (cast only for LoRA-patched keys) |
| Production inference_mode | `execution.py:736` | node execution already wrapped in `torch.inference_mode()` — harness P0 numbers are conservative (no wrapper) |
| manual_cast_dtype | `model_patcher.py:162,910-916` | only read for low-vram memory estimation, **not** by the forward cast path |

Key runtime-confirmed facts (from the lab's verification pass): Linear input activation dtype = **fp32 in every arm** (autocast lowers only the internal matmul, not the Comfy cast path); output dtype = fp32 in every arm; per-forward weight rematerialization = **YES** in every arm; attention function = `attention_pytorch`; patcher `force_cast_weights=True` + `manual_cast_dtype=fp32` (via the P0 mirror of `sd.py:254-255`).

## 3. Research findings (authoritative sources; see full citation set in the lane report)

1. **TF32**: opt-in since PyTorch 1.12 (`allow_tf32=False` default); `torch.set_float32_matmul_precision("high")` = TF32 on CUDA, capability-gated automatically (PyTorch docs v2.7). TF32 = 19-bit (FP16 mantissa, FP32 range). Ampere peak ratios (A100 official): TF32 8× FP32, FP16/BF16 16× FP32; GA10x consumer derived ≈ 4×/8× (no official consumer peak published).
2. **When 16-bit helps**: encoders at 77–512 tokens are launch/memory-bound (NVIDIA: <~140 FLOPs/byte ⇒ memory-bound); flash-attention is fp16/bf16-only and gains shrink at short sequences ⇒ expected dtype gains single-digit %, not 2–8×. **The lab confirms: none at all here.**
3. **Failure modes**: fp16 overflow risk (attention logits, max 65k); autocast's sanctioned pattern upcasts softmax/LN to fp32; bf16 = FP32 range, 7-bit mantissa (Kalamkar et al. 2019) — no overflow, real rounding error; T5-fp16 NaN reports are anecdotal (unverifiable via login-gated search). Lab result: zero NaN/Inf in all arms.
4. **Generic torch-level levers**: `inference_mode` (strictly faster than no_grad; already active in production execution), autocast, `set_float32_matmul_precision`, SDPA backend selection, `torch.compile` (reduce-overhead = CUDA graphs for small batches; per-family guard risk), CUDA graphs (static shapes; output copy must be excluded).
5. **Cast cost**: Comfy casts every weight per forward with no cache (verified in source); ~1.5 GB moved per 500 MB encoder per encode ≈ ms-scale on 448 GB/s (3070). The lab measured 126–417 MB cast per forward with cast CPU wall ≈ forward wall.
6. **Comfy wrapper**: yes — it forces fp32 compute + fp16 resident + per-forward rematerialization generically (family-agnostic; no model names involved). CLI `--fp16-text-enc` etc. change *storage only* — the fp32 compute force is applied after load, so those flags do NOT give fp16 compute (a trap for naive optimization).
7. **Generic opportunities** ranked by evidence — see §9.
8. **Must-reject (model-specific)**: GQA/MQA head rewrites, T5 fused attention, per-family early exit, named-layer quantization, flash-attention architecture variants, layer fusion, TensorRT/ONNX export. Generic gate: only dtype/capability/shape/flag-based logic.

## 4. Benchmark architecture

New isolated tooling (no production changes):

- `tools/benchmark_text_encoder_encode.py` (1507 lines) — standalone lab. Pure-logic core (`DtypePolicy`, `Correctness`, `GlobalTorchSettings`) imports no torch/comfy; comfy is lazy-imported after sys.argv sanitization (comfy/cli_args parses argv). Fixtures are built from Comfy's own generic classes; arms apply capability-gated settings; timing uses CUDA events with wall cross-check; every arm restores all torch globals in `finally`.
- Timing boundaries: fixture construction, `load_models_gpu` residency, and 3 warm-up encodes happen **outside** the timer. Timed region = `encode_token_weights` only, per repeat, bracketed by `torch.cuda.synchronize()` + CUDA events. `tokenize`, `load_models_gpu` re-entry, and post-forward (`CLIP.encode_from_tokens` delta incl. output D2H copy) are measured separately. Report: CPU wall + CUDA-event device time.
- Verification pass (untimed): activation dtype hooks on Linear modules, `cast_bias_weight` wrapper counting cast ops/bytes/wall, output dtypes, attention function, patcher capabilities, torch globals before/after (restoration proof).
- Modes: `coarse` (default) and `deep` (torch.profiler operator breakdown bucketed into GEMM/ATTENTION/NORM/ACTIVATION/COPY/SYNC/OTHER).
- CLI: `--fixtures/--arms/--mode/--repeats/--warmup/--batch/--tokens/--seed/--json/--list-fixtures/--quick` + `COMFYMODAL_D7_*` env overrides; JSON results.

## 5. Dtype matrix (arms)

| Arm | Requested compute | Mechanism (generic) | Gate | On RTX 3070 |
|---|---|---|---|---|
| P0 | fp32 | none — exact current Comfy behavior | — | OK |
| P1 | fp32 + TF32 | `torch.set_float32_matmul_precision("high")` + `allow_tf32=True` | CUDA + sm ≥ 8.0 | OK |
| P2 | bf16 | `torch.autocast("cuda", bfloat16)` around encode | CUDA + sm ≥ 8.0 | OK |
| P3 | fp16 | `torch.autocast("cuda", float16)` around encode | CUDA + sm ≥ 7.0 | OK |
| P4 | preferred | capability pick: bf16 (sm≥8.0) → fp16 (sm≥7.0) → fp32; autocast | CUDA | OK (bf16) |

Honesty controls: the harness records **requested** vs **actual** activation dtype (fp32 at Linear inputs in every arm — Comfy's cast path forces it), resident parameter dtype (fp16 in every arm), output dtype (fp32 in every arm), `manual_cast_dtype` (fp32), and reports per-arm rematerialization. An arm that Comfy silently converts is reported as such — no arm claims a compute dtype it didn't achieve. Arms that cannot apply on a device are classified **UNSUPPORTED** with reason (unit-tested via capability matrix).

## 6. Fixture matrix

All fixtures: deterministic random weights (seeded), **real Comfy generic classes** through the real `ClipTokenWeightEncoder` path, resident fp16 (production default), 77 tokens, batch 1. Zero downloads.

| Fixture | Generic class (Comfy) | Params | Tokenizer | Notes |
|---|---|---|---|---|
| classic_clip | `SD1ClipModel` (sd1_clip.py) | 63.4 M | real bundled SD1 (0.78 ms) | classic-CLIP category |
| large_clip | `SDClipModel` (OpenCLIP-style config) | 208.7 M | real bundled SD1 (0.49 ms) | larger-CLIP category |
| t5 | `SDClipModel(model_class=text_encoders.t5.T5)` | 41.6 M | synthetic (no bundled T5 tokenizer) | T5-family category |
| llm | `SDClipModel(model_class=text_encoders.llama.Llama2)` | 46.3 M | synthetic | LLM-style encoder category |
| multi_encoder | real `comfy.sd.CLIP` wrapper, 2 sub-encoders (CLIP-style + Llama2) | 90.8 M | synthetic | multi-encoder CLIP object; full `encode_from_tokens` path |

**Unavailable locally:** real trained weights for every category (no local checkpoints; the only local encoders are 4B–24B LLM-class files that exceed 8 GB VRAM — qwen_3_4b/8b, mistral_3_small, flux-2-klein-9b text encoder — explicitly not downloaded per batch rules). Synthetic fixtures substitute for dtype/cast machinery measurement; real-weight encode validation remains a production-fixture experiment (§12). Tokenize for T5/LLM/multi unavailable (no bundled vocab) — reported, not faked.

## 7. Performance results (primary measurements)

Device-time (CUDA-event) forward medians, ms; wall ≈ device (Δ ≤ 0.02 ms). 15 repeats, 3 warm-up, stability across 3 further repeats: cosine deviation ≤ 8.3e-7 (deterministic fixtures stable).

| Fixture | P0 fp32 | P1 TF32 | P2 bf16 | P3 fp16 | P4 pref(bf16) | Δ(P1 vs P0) | Δ(P3 vs P0) |
|---|---|---|---|---|---|---|---|
| classic_clip | **10.32** | 12.22 | 14.47 | 13.33 | 14.36 | +18% | +29% |
| large_clip | 23.86 | **22.80** | 22.59 | **21.28** | 23.06 | −4.4% | −10.8% |
| t5 | **6.70** | 8.51 | 8.12 | 8.95 | 9.43 | +27% | +34% |
| llm | **9.30** | 10.13 | 11.10 | 10.88 | 10.70 | +9% | +17% |
| multi_encoder | 26.46 | **24.96** | 25.93 | 26.18 | 26.54 | −5.7% | −1.0% |

Bold = best. **P0 is fastest or tied on 4/5; no arm is consistently faster. Spread is largely kernel-selection variance at this scale.**

Secondary boundaries (ms):

| Fixture | tokenize | load re-entry (resident) | post-forward (output copy + wrapper) | total (multi) |
|---|---|---|---|---|
| classic_clip | 0.78 | 7.6–13.3 | 0 | — |
| large_clip | 0.49 | 6.7–16.9 | 0 | — |
| t5 | n/a | 8.0–12.6 | 0 | — |
| llm | n/a | 7.0–10.4 | 0 | — |
| multi_encoder | n/a | 7.2–9.8 | **7.3–10.4** | 33.8–36.3 |

Casting (identical across arms — the tax is arm-independent):

| Fixture | cast ops/forward | cast bytes/forward | cast CPU wall (ms) |
|---|---|---|---|
| classic_clip | 99 | 126.6 MB | 13.6–16.1 |
| large_clip | 195 | 416.9 MB | 21.5–24.8 |
| t5 | 50 | 83.2 MB | 7.9–11.3 |
| llm | 57 | 92.5 MB | 10.6–11.8 |
| multi_encoder | 108 | 181.4 MB | 26.1–28.1 |

CUDA memory: allocated before == after in every cell (no growth); peak = steady +6–17 MB; reserved flat. torch globals before == after in every cell (`_restored=True`, 25/25 cells) — no leaked settings.

Deep profile (classic_clip P0, torch.profiler): GPU busy ≈ 6.6 ms of 10.8 ms wall. GEMM cuda 3.50 ms (7 ops), COPY cuda 2.03 ms (11 ops), NORM 0.17 ms, OTHER cpu 9.92 ms / cuda 0.87 ms, SYNC cpu 4.07 ms. Under bf16: GEMM cuda halves to 1.50 ms, but COPY grows to 2.75 ms and OTHER cpu to 10.1 ms → net wall up. t5: COPY cuda 7.6 ms (!) even in P0. → CPU-side launch/cast/copy work dominates; raw matmul throughput is not the constraint.

Torch-version cross-check (embedded python 2.12+cu130, quick run): absolute P0 numbers differ (t5 fp32 notably slower), bf16 arms similar — findings hold, absolutes are torch-version dependent.

## 8. Correctness results (vs P0 reference; cond tensor; 100% finite, zero NaN/Inf, shapes equal everywhere)

| Fixture | P1 TF32 | P2 BF16 | P3 FP16 | P4 pref(bf16) |
|---|---|---|---|---|
| classic_clip | NUMERICALLY_CLOSE (2.0e-3 / cos 1.000000) | MATERIAL_DIFFERENCE (3.5e-2 / 0.999969) | NUMERICALLY_CLOSE (3.4e-3) | MATERIAL_DIFFERENCE (3.5e-2) |
| large_clip | CLOSE (2.3e-3) | MATERIAL (3.5e-2) | CLOSE (3.3e-3) | MATERIAL (3.5e-2) |
| t5 | CLOSE (2.8e-3) | MATERIAL (3.2e-2) | CLOSE (3.8e-3) | MATERIAL (3.2e-2) |
| llm | CLOSE (1.6e-3) | MATERIAL (2.5e-2) | CLOSE (2.1e-3) | MATERIAL (2.5e-2) |
| multi_encoder | CLOSE (1.9e-3) | MATERIAL (3.5e-2) | CLOSE (2.9e-3) | MATERIAL (3.5e-2) |

(parentheticals = max abs error / cosine). Pooled outputs track cond. Thresholds: CLOSE = cos ≥ 0.999 ∧ max_abs ≤ 1e-2; MATERIAL = finite but beyond. **No arm is EXACT; none is INVALID; none is UNSUPPORTED on this GPU.** BF16's ~3.5e-2 max-abs on random-weight fixtures reflects its 7-bit mantissa — real trained models may drift less (normalized activations), which the production fixture experiment must re-verify; classification is honest, not "didn't crash".

## 9. Generic optimization ranking (measured evidence, not theory)

| # | Candidate | Layer | Expected saving (measured basis) | Risk / numerical risk | Capability gate | Fallback |
|---|---|---|---|---|---|---|
| 1 | **Eliminate per-forward weight rematerialization** — resident dtype == compute dtype at load, or cache the fp16→fp32 cast (Comfy caches nothing today) | Comfy patcher/ops | est. 20–35% of encode wall at these sizes (cast CPU wall ≈ forward wall; GPU GEMM time halves when matmul dtype matches); grows with encoder size | low; VRAM +N GB for resident fp32 | VRAM budget (generic memory accounting) + dtype capability | keep per-forward cast (current) |
| 2 | **Defer/eliminate output intermediate-device copy** (7–10 ms blocking D2H per encode on multi fixture) | Comfy sd.py/sd1_clip output path | ~7–10 ms per encode | low; downstream expects CPU cond | consumer-side generic (gpu-only mode exists: `--gpu-only`) | current CPU copy |
| 3 | **Avoid `load_models_gpu` re-entry overhead** (7–17 ms even when fully resident) | Comfy model_management / caller | 7–17 ms per encode node | low | cache/ownership logic (overlaps D6/D9 lanes) | current short-circuit |
| 4 | TF32 opt-in (`set_float32_matmul_precision("high")`) | torch-level | neutral here (−5%…+27% noise); may help GEMM-bound large encoders | low; 1e-3-level rounding (CLOSE) | sm ≥ 8.0 | P0 |
| 5 | FP16 compute via autocast | torch-level | none at this scale (slower on 3/5) | low-moderate; CLOSE numerically | sm ≥ 7.0 | P0 |
| 6 | BF16 compute via autocast | torch-level | none at this scale (slower on 4/5) | **moderate; MATERIAL_DIFFERENCE** | sm ≥ 8.0 | P0 |
| 7 | SDPA backend pinning (flash for 16-bit, mem-efficient for fp32) | torch-level | small (attention CPU 0.6 ms here); grows with seq len | low | SDPA kernel matrix | current |
| 8 | `torch.compile` / CUDA graphs on encode | torch-level | plausible in launch-bound regime (reduce-overhead targets small batches) but unproven here; compile cost + per-family guard risk | moderate | static shapes; eager fallback on guard failure | eager |
| 9 | `inference_mode` | torch-level | **already active in production** (`execution.py:736`) — harness P0 (no wrapper) is conservative; nothing to add | none | n/a | n/a |
| 10 | `allow_fp16/bf16_reduced_precision_reduction` | torch-level | unmeasured micro-arm; reduction precision only | moderate | dtype-gated | off |

## 10. Rejected model-specific approaches

GQA/MQA head rewriting (Qwen-class), T5 fused attention / rel-bias special-casing, per-family early exit / layer pruning, named-layer quantization (e.g., "quantize out_proj"), flash-attention architecture variants, layer fusion, TensorRT/ONNX export of the TE. All require architecture constants or layer-name semantics; none passes the generic gate (dtype/capability/shape/flag only). The harness's test suite enforces model-name independence behaviorally and structurally.

## 11. Relevance to the 12-second target

Planning assumptions: Modal ~1.0 s + restore ~3.5 s + sampling ~4.9 s = 9.4 s → **~2.6 s** for all other exposed work; UNET generic fast-loader healthy target 2.4–2.7 s, overlapped with TE preparation.

Measured here: pure GPU-resident encode = **7–27 ms** across the generic fixture range (63–209 M params, 77 tokens). Extrapolation to production-scale encoders (T5-XXL-class, 256 tokens, A100-class GPU) lands in the ~50–200 ms band — an order of magnitude below the 2.6 s budget. Even with the wrapper overheads (load re-entry 7–17 ms, output copy 7–10 ms), the **entire TE-side encode envelope is ~30–60 ms vs a 2.4–2.7 s UNET lane**; it can trivially finish inside the UNET lane's window. No overlap evidence is needed to conclude encode is not critical-path: the critical TE cost remains *hydration* (GB-scale H2D — D6 territory), not encode. Dtype policy is irrelevant to the 12 s goal on this evidence.

## 12. Exact recommended next production experiment

**Do not ship a dtype-policy change.** The single smallest, highest-information generic production experiment:

> **Cast-tax elimination probe on a real production fixture:** with a production T5-XXL-class text encoder already GPU-resident, run encode twice — (a) current P0 path (resident fp16, per-forward fp32 rematerialization), (b) same weights constructed resident-fp32 (or cast-once-at-load cached fp32 copies) via generic `model_options["dtype"]` plumbing — and compare CUDA-event encode time + cast-op/byte counters. Gate purely on VRAM budget (generic memory accounting). Expected: ms-scale encode saving (20–35% of encode wall at production sizes); **do not touch TF32/BF16/FP16 defaults**; correctness vs P0 must be EXACT for this arm (same compute dtype, no precision change — only cast scheduling changes).

Second experiment (only if the first shows a need): TF32 opt-in for the TE forward on sm≥8.0, verifying the measured-neutral result at production GEMM sizes.

---

## Final response

```
GENERIC_ENCODE_BASELINE = P0 (CUDA-event, GPU-resident): 10.32 ms classic_clip (63M) · 23.86 ms large_clip (209M) · 6.70 ms t5 (42M) · 9.30 ms llm (46M) · 26.46 ms multi (91M, forward only; 33.8 ms total incl. post-forward)
TF32_RESULT = neutral-to-slightly-negative (−4.4%..−5.7% on large fixtures, +9%..+27% on small; NUMERICALLY_CLOSE, max_abs ~2e-3) — no reliable generic win at 77-token scale
BF16_RESULT = slower on 4/5 fixtures (+13%..+40%; −5% on large_clip); MATERIAL_DIFFERENCE (max_abs 2.5–3.5e-2) — not a generic default
FP16_RESULT = mixed (−10.8% on large_clip, +17%..+34% on small); NUMERICALLY_CLOSE (max_abs ~3e-3) — no reliable win
DECLARED_DTYPE_RESULT (P4 = preferred bf16) = slower on 4/5 (+8%..+41%); MATERIAL_DIFFERENCE — the "natural" preferred dtype is not a win at this scale
BIGGEST_GENERIC_ENCODE_WIN = eliminate uncached per-forward fp16→fp32 weight rematerialization (est. 20–35% of encode wall; 126–417 MB cast per forward); then output D2H copy deferral (7–10 ms); then load_models_gpu re-entry avoidance (7–17 ms)
CASTING_OVERHEAD = 50–195 cast ops and 83–417 MB per forward (every arm); cast CPU wall 8–28 ms ≈ forward wall; per-forward weight rematerialization = YES (uncached, ops.py:375-376)
GENERIC_COMFY_DTYPE_FINDING = Comfy forces fp32 compute (sd.py:255; sd1_clip.py:213,279) + fp16 resident storage (model_management.py:1150-1165) + uncached per-forward weight casts (ops.py:375-376); no autocast, no TF32 anywhere; fp32 SDPA falls to math backend; encode is launch/memory-bound at production token counts → dtype arms neutral-to-slower; CLI --fp16-text-enc etc. change storage only (compute stays fp32 — trap)
NUMERICAL_RISK = BF16: MATERIAL_DIFFERENCE (7-bit mantissa; max_abs ~3.5e-2 on these fixtures) · FP16: NUMERICALLY_CLOSE (max_abs ~3e-3) · TF32: NUMERICALLY_CLOSE (max_abs ~2e-3) · zero NaN/Inf, 100% finite, shapes equal, deterministic fixtures stable (cosine dev ≤ 8.3e-7)
FIXTURES_TESTED = 5 generic categories via real Comfy classes, random-weight synthetic: classic_clip (SD1ClipModel 63.4M), large_clip (SDClipModel 208.7M), t5 (SDClipModel+T5 41.6M), llm (SDClipModel+Llama2 46.3M), multi_encoder (comfy.sd.CLIP, 2 sub-encoders, 90.8M)
FIXTURES_UNAVAILABLE = real-trained-weight encoders (no local checkpoints; local 4B–24B LLM encoders exceed 8 GB VRAM; not downloaded per rules); tokenize for T5/LLM/multi (no bundled vocabs) — reported, not faked
FILES_CREATED = tools/benchmark_text_encoder_encode.py · tests/test_v2_d7_text_encoder_encode_lab.py · tools/d7_results_full.json · tools/d7_deep_profile.json
FILES_MODIFIED = none (production files untouched)
TESTS = tests.test_v2_d7_text_encoder_encode_lab: 24 tests OK (1 skip — CUDA-absent matrix, CUDA present); py_compile OK (both files); full matrix run on system python + cross-check on embedded python
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none

READY_FOR_GENERIC_DTYPE_PRODUCTION_EXPERIMENT = YES — but the experiment is NOT a dtype change: probe cast-tax elimination on a real production fixture (resident-fp32 or cast-once-at-load fp32 copies, VRAM-gated, correctness must stay EXACT vs P0), then optionally verify TF32 neutrality at production GEMM sizes. Neither change ships from this batch; nothing implemented in production.
```

## You asked for:
- A zero-spend lab measuring GPU-resident generic Comfy text-encoder encode time across FP32/TF32/BF16/FP16 arms, with source-verified call-path mapping, deep research, correctness gates, and generic optimization ranking (Parts 1–12), plus harness, tests, and the V2_BATCH_D7 report.

## You should now manually check:
- **Harness reuse:** `python tools\benchmark_text_encoder_encode.py --fixtures all --arms all --repeats 15 --json <path>` (with `PYTHONPATH` = parent ComfyUI repo) reproduces the tables; `--mode deep` for operator buckets; `--list-fixtures` for fixture roster.
- **Real-weight caveat:** correctness classes (esp. bf16 MATERIAL_DIFFERENCE) were measured on random-weight fixtures — before any production dtype adoption, re-verify on a real trained encoder (recommended experiment §12); expect smaller drift on normalized real activations.
- **Variance:** absolute timings drift across runs/GPU clocks/torch versions (e.g., t5 P0 6.7 ms vs 14.9 ms between runs; torch 2.12 differs from 2.8) — compare ratios/medians, not single samples.
- **Test hygiene:** `python run_tests.py tests.test_v2_d7_text_encoder_encode_lab` should stay green (35 OK / 1 skip); JSON result artifacts are regenerable and disposable.
- **Concurrent lanes:** D6 (hydration/restore) owns the actual TE critical-path cost; this batch measured only the encode slice — the 12 s verdict assumes hydration remains the binding constraint.

---

# True Low-Precision Compute Follow-up

Date: 2026-08-16 (same batch, continuation) · Branch: current main · Commit: **none** · Modal requests/deploys: **0** · ZERO SPEND.

## Why this follow-up exists

The first D7 pass used `torch.autocast` for the BF16/FP16 arms. That did **not** change the generic encoder's actual compute dtype: Comfy's `manual_cast` ops derive the per-forward weight-cast target from the **input** dtype, and the generic path hardcodes fp32 inputs (`sd1_clip.py:213,237,279`). Actual Linear input activations remained FP32 in every arm — P2/P3 were autocast-around-Comfy experiments, not true low-precision compute. This section corrects that with a genuine, process-local, fully generic mechanism, a hard runtime validity gate, and two casting policies.

## Mechanism (proven, generic, reversible)

Process-local override: wrap each encoder's `transformer.forward` (object-level attribute patch) to coerce the `embeds` and `dtype` kwargs to the requested compute dtype, then call the original. Capability check is signature-based (explicit `dtype`/`embeds` params **or** `**kwargs`) — no model names, no family checks. Applies to every sub-encoder in a composite (`multi_encoder` wraps both its CLIP and Llama transformers). With bf16/fp16 embeds, `cast_bias_weight` casts weights to match and `F.linear` runs true low-precision GEMMs; attention runs low-precision SDPA (flash-capable); output contract stays fp32 (`sd1_clip.py:281-294`). Restoration: original bound methods, `patcher.object_patches["manual_cast_dtype"]`, resident state (exact `state_dict` clone restore — bf16↔fp16 roundtrips are lossy), and all torch globals are restored after every arm (verified `settings_restored=True` in all 48 cells).

Smoke-verified seam evidence (Linear-input dtype hooks): classic_clip/large_clip/t5/llm/multi_encoder → `torch.bfloat16` / `torch.float16` under P2/P3; fp32 under P0/P1; outputs fp32 throughout.

## Hard arm-validity gate (per arm, from runtime instrumentation)

Arm VALID only if `requested_compute_dtype == actual_linear_input_dtype == actual_weight_compute_dtype_seen == manual_cast_dtype_during_arm` (and for TF32 arms: `allow_tf32` active during the timed region). Example evidence (xl_llm P2B, from JSON `validity`): `requested=torch.bfloat16, actual_linear_input_dtype=torch.bfloat16, actual_weight_compute_dtype_seen=torch.bfloat16, manual_cast_dtype_during_arm=torch.bfloat16, observed_linear_input_dtypes=["torch.bfloat16"], observed_weight_dtypes=["torch.bfloat16"], checks={all true}`. Any failure → `ARM_INVALID_NOT_LOW_PRECISION`, no timing published. **All 48 fixture×arm cells (6 fixtures × 8 arms) came out VALID.** Legacy autocast arms (P0–P4) remain available but report `actual_act=None validity=INFO` — the mixed-dtype evidence that autocast does not achieve uniform low precision (honest distinction, per requirement).

## Arm × policy matrix and results

Arms: **A = CURRENT_COMFY_CAST_EVERY_FORWARD** (resident ≠ compute; per-forward casts), **B = COMPUTE_DTYPE_RESIDENT** (resident == compute; cast once, outside timer, one-time cost reported separately).

CUDA-event forward medians (ms), 77 tokens, batch 1, RTX 3070, 15 repeats, 3 warm-up:

| Fixture (params) | P0A fp32/fp16res | P0B fp32/fp32res | P1A tf32/fp16res | P1B tf32/fp32res | P2A **bf16**/fp16res | P2B **bf16**/bf16res | P3A **fp16**/fp32res | P3B **fp16**/fp16res |
|---|---|---|---|---|---|---|---|---|
| classic_clip (63.4M) | 10.19 | 8.05 | 11.08 | 7.81 | 10.31 | 8.01 | 10.77 | 8.08 |
| large_clip (208.7M) | 19.81 | 15.03 | 20.04 | 14.99 | 19.49 | 14.87 | 19.55 | 14.54 |
| t5 (41.6M) | 7.27 | 7.25 | 8.10 | 7.18 | 7.94 | 6.90 | 7.82 | 6.90 |
| llm (46.3M) | 9.36 | 8.16 | 9.25 | 7.61 | 10.16 | 8.52 | 9.87 | 8.79 |
| multi_encoder (90.8M) | 22.20 | 18.55 | 21.69 | 18.28 | 22.81 | 19.41 | 23.00 | 19.97 |
| xl_llm (**847.7M**) | 43.85 | 30.22 | 37.86 | 29.89 | 36.18 | 32.02 | 37.10 | 32.32 |

Casting evidence (per forward, all fixtures): A-arms materialize 98–100% of cast calls (xl_llm P0A: 224/225 casts, **3.10 GB moved per forward**; P2A 1.55 GB; t5 50 casts/100 MB); B-arms materialize **0** (short-circuit). One-time resident conversion (outside timer): 2.9–13.3 ms small fixtures; xl_llm 85.4 ms (fp32), 31.5 ms (bf16). Peak GPU: xl_llm P0B 5.4 GB (of 8 GB — fits, tight); all cells allocated-before == after.

Correctness vs P0A reference (cond tensor; 100% finite, zero NaN/Inf, shapes equal, stable across repeats):

| Arm | Classification | max abs err / cosine |
|---|---|---|
| P0B | **EXACT** (bitwise, all fixtures) | 0.0 / 1.0 |
| P1A/P1B | NUMERICALLY_CLOSE | 1.6–3.6e-3 / ≥0.999999 |
| P2A/P2B (true bf16) | **MATERIAL_DIFFERENCE** (all fixtures) | 5.0e-2–1.02e-1 / ≥0.99984 |
| P3A/P3B (true fp16) | NUMERICALLY_CLOSE (≤209M); MATERIAL at 848M (borderline) | 4.8–9.8e-3 / ≥0.999997; xl_llm 1.15e-2 / 0.999996 |

Deep profile (xl_llm, device µs per forward): P0A GEMM 20.2k · COPY 26.6k · OTHER 26.2k → P0B GEMM 20.7k · **COPY 0.6k** · OTHER 26.7k → P2B GEMM **7.6k** · COPY 1.3k · OTHER 12.4k. CPU-side OTHER ≈ 30 ms in every arm. Interpretation: cast/copy is ~26 ms of device time per forward at 848M and vanishes under policy B; bf16 GEMMs are ~3× faster on device (20.7→7.6k µs) — **yet wall time does not improve** because encode is CPU-dispatch/launch-bound at 77 tokens (wall ≈ CPU launch overhead, GPU underutilized). This is the same finding as pass 1, now with true-low-precision + device-level evidence at 848M.

## Answers to the required questions

1. **Does TRUE BF16 compute speed up generic text encoding? NO.** P2B vs P0B: 0% (classic), −1% (large), −5% (t5), +4% (llm), +5% (multi), +6% (xl_llm). Device GEMM time drops ~63% but wall doesn't move — launch-bound. No reliable win at any scale tested.
2. **Does TRUE FP16 compute speed it up? NO.** P3B vs P0B: 0%, −3%, −5%, +8%, +8%, +7%. Same noise band, no reliable win.
3. **How much of P0 is per-forward cast tax? 0.3% (t5) to 31% (xl_llm) of forward wall** — ~13–24% on CLIP/LLM/multi fixtures; ≈26 ms device-time of 44 ms wall at 848M; the tax grows with encoder size (P0A materializes 3.1 GB/forward at 848M).
4. **What happens when resident dtype == compute dtype?** Policy B: per-forward casts drop to 0 (materialized), and at fp32 (P0B) the output is **bitwise EXACT** vs P0A while being 13–31% faster on ≥200M fixtures. One-time conversion cost is outside the timed region (3–85 ms) and amortizable.
5. **What numerical drift results?** True bf16: MATERIAL_DIFFERENCE everywhere (max abs 5e-2–1.02e-1; 7-bit mantissa at 848M depth); true fp16: NUMERICALLY_CLOSE up to 209M (max abs <1e-2), borderline-MATERIAL at 848M (1.15e-2 vs 1e-2 threshold, cosine still 0.999996); zero NaN/Inf in all 48 cells. P0B: EXACT.
6. **Is a generic low-precision production policy promising? NO.** At 77–256-token production encode, the wall is launch/cast-bound, not matmul-throughput-bound — even true bf16/fp16 compute buys nothing while bf16 costs real drift. The original pass-1 finding (dtype arms neutral-to-slower) is confirmed with genuine low-precision execution and corrected evidence.
7. **Is a generic CAST-ONCE / resident-compute-dtype policy more promising than changing precision itself? YES — clearly.** P0B (resident fp32 = compute fp32, no per-forward rematerialization) is faster on every ≥200M fixture (13–31%) with bitwise-identical output and zero numerical risk. The cast tax, not precision, is the exploitable generic cost. VRAM cost: 2× weight footprint (xl_llm peak 5.4/8 GB). Precision itself is a dead end at this scale.

## Production-scale caveat (unchanged and now explicit)

Timing cannot be extrapolated linearly to 4B+ encoders: at T5-XXL-class d_model (4096–5120), GEMMs become denser and tensor-core effects and the cast tax both grow (cast tax grows at least linearly with parameter count — 3.1 GB/forward at 848M suggests ~15 GB/forward at 4B, ≈ tens of ms even on A100 bandwidth). The production-scale verdict remains dependent on **D6's clean remote encoder measurement**; this lab's value is the mechanism proof (true low-precision is achievable generically), the cast-tax quantification, and the launch-bound diagnosis — all of which shape what D6 should measure.

## Operational notes (honesty)

- One full-matrix invocation failed transiently at fixture preparation with a `load_state_dict` error; the identical re-run completed all 48 cells successfully (not reproduced; no code change between runs). Reported for completeness.
- Harness changes: 8 new arms (P0A–P3B) with hard validity gate; `xl_llm` fixture (847.7M params, VRAM-guarded, `shrunk_layers` recorded — 0 here); cast accounting split (materialized vs short-circuit); one-time conversion timing; P0A is the correctness reference; legacy autocast arms retained and labeled.
- New artifacts: `tools/d7_lp_results.json` (48 cells), `tools/d7_lp_deep.json` (xl_llm P0A/P0B/P2B buckets).

## Final response

```
ORIGINAL_P2_P3_ACTUALLY_LOW_PRECISION = NO
TRUE_BF16_ARM_VALID = YES (48/48 cells VALID; Linear-input + GEMM-weight + manual_cast evidence bf16 everywhere; legacy autocast arms remain INFO-only)
TRUE_FP16_ARM_VALID = YES (same gate, fp16)
P0_FORWARD = 10.19 ms classic_clip (63M) · 19.81 large_clip (209M) · 7.27 t5 (42M) · 9.36 llm (46M) · 22.20 multi (91M) · 43.85 xl_llm (848M) — CUDA-event medians
TRUE_BF16_FORWARD = P2B: 8.01 / 14.87 / 6.90 / 8.52 / 19.41 / 32.02 ms (0%..−5% small, +4..+6% large vs P0B — NO speedup)
TRUE_FP16_FORWARD = P3B: 8.08 / 14.54 / 6.90 / 8.79 / 19.97 / 32.32 ms (NO reliable speedup)
CAST_EVERY_FORWARD_COST = 0.3% (t5) to 31% (xl_llm) of forward wall; ~26 ms device-time of 44 ms at 848M; P0A materializes 3.10 GB/forward vs 0 under resident policy
COMPUTE_DTYPE_RESIDENT_RESULT = P0B: bitwise EXACT vs P0A, 13–31% faster on ≥200M fixtures; one-time conversion 2.9–85 ms outside timer; peak 5.4/8 GB at 848M
BF16_CORRECTNESS = MATERIAL_DIFFERENCE everywhere (max_abs 5.0e-2–1.02e-1, cos ≥0.99984); 100% finite, 0 NaN/Inf
FP16_CORRECTNESS = NUMERICALLY_CLOSE ≤209M (max_abs 4.8–9.8e-3), MATERIAL_DIFFERENCE at 848M (1.15e-2 borderline, cos 0.999996); 100% finite
LARGEST_FIXTURE = xl_llm — 847,726,849 params (Llama2-style via SDClipModel), fp16 resident 1.58 GB, peak 5.43 GB, 32 layers, no OOM, shrunk_layers=0
PRODUCTION_SCALE_TIMING_KNOWN = NO (4B+ extrapolation explicitly not claimed; verdict depends on D6 remote measurement)
BEST_GENERIC_POLICY = CAST-ONCE / resident-compute-dtype (P0B-style): keep FP32 compute, set resident == compute once at load, eliminate per-forward rematerialization — faster AND bitwise-identical; changing precision itself offers no wall win at production token counts
READY_FOR_PRODUCTION_DTYPE_EXPERIMENT = YES — smallest experiment: cast-once resident-fp32 text encoder (VRAM-gated), measured on a real production fixture by D6's clean remote timing; do NOT change compute precision
FILES_CHANGED = tools/benchmark_text_encoder_encode.py (extended: 8 arms + validity gate + wrap mechanism + xl_llm) · tests/test_v2_d7_text_encoder_encode_lab.py (extended) · artifacts tools/d7_lp_results.json, tools/d7_lp_deep.json · V2_BATCH_D7_GENERIC_TEXT_ENCODER_ENCODE_LAB.md (this section)
TESTS = 35 OK (1 skip — CUDA-absent matrix) + py_compile OK
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
```
