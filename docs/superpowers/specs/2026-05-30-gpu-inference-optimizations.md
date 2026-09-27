# GPU Inference Optimizations — Per-GPU Reference

> For Modally deployed ComfyUI (Linux containers, Triton available). Target workflow: FLUX2 with Qwen3 8B TE + 9B FP8 UNet, 20 steps.
>
> **Working reference, 2026-05-31** — update with measured deployment logs before treating projected speedups as production guidance.

## GPU ↔ Architecture Map

| GPU | Arch | SM | VRAM | Modal Name |
|-----|------|----|------|------------|
| T4 | Turing | 7.5 | 16 GB | `t4` |
| A10G | Ampere | 8.6 | 24 GB | `a10g` |
| A100 (any) | Ampere | 8.0 | 40/80 GB | `a100` / `a100-40gb` / `a100-80gb` |
| L4 | Ada | 8.9 | 24 GB | `l4` |
| L40S | Ada | 8.9 | 48 GB | `l40s` |
| H100 | Hopper | 9.0 | 80 GB | `h100` |
| H200 | Hopper | 9.0 | 141 GB | `h200` |
| RTX PRO 6000 | Blackwell | 12.0 | 96 GB | `rtx-pro-6000` |
| B200 | Blackwell | 12.0 | 180 GB | `b200` |

## Optimization Key

| Symbol | Meaning |
|--------|---------|
| ✅✅ | Best-in-class / strongly recommended |
| ✅ | Works, measurable gain |
| ⚠️ | Works but has notable caveats |
| ❌ | Not supported / actively harmful |

## Important Pre-Notes

1. **Speedup figures are end-to-end estimates for the FLUX2 workflow**, not per-op microbenchmarks.
2. **Attention backends are mutually exclusive** — SageAttention, FlashAttention, xFormers, and SDPA all replace the same `F.scaled_dot_product_attention` call. Pick one per architecture (see "Pick" row).
3. **SDPA (PyTorch's `scaled_dot_product_attention`) is the default fallback.** It auto-dispatches between FlashAttention-2 (SM 8.0+, FP16/BF16, head dim 64/128), Memory-Efficient backend, or Math backend. FA2 is **not guaranteed** for all input shapes.
4. **torch.compile requires Triton.** On Modal Linux, Triton ships with the PyTorch wheel. SageAttention2 additionally requires `triton ≥3.0.0`, which stable PyTorch may not bundle — upgrade explicitly.
5. **Avoid blanket `--fast`** for the current FLUX2 workflow. In measured RTX PRO 6000 runs it regressed VAE decode from ~300ms to ~1900ms and affected output quality. Revisit only with explicit A/B logs.
6. **FLUX2 VRAM warning:** Qwen3 8B FP8 TE + 9B FP8 UNet ≈ 17 GB weights alone, plus activations. **T4 (16 GB) is borderline infeasible.** A10G / L4 (24 GB) is tight.

---

## T4 (Turing SM 7.5, 16 GB)

**Default flags to set:** `--force-fp16`

| Opt | Verdict | End-to-end gain | Notes |
|-----|---------|-----------------|-------|
| FP16/BF16 | ✅✅ | ~35% | Must have. No BF16 Tensor Cores (Turing) — use FP16. |
| SageAttention | ❌ | — | Needs SM 8.0+. No path. |
| FlashAttention2 | ✅ | ~1.3-1.5× attention | SM 7.0+ supports FA2. However, PyTorch SDPA may select MemEff backend on SM 7.5 for many input shapes. FA2 performance on Turing is significantly worse than Ampere+. |
| xFormers | ⚠️ | ~1.1× | Works but ComfyUI blacklists buggy versions (v0.0.21-0.0.26). SDPA is fine. |
| FP8 | ❌ | — | No FP8 Tensor Cores on Turing. Software fallback slower than FP16. |
| torch.compile | ✅ | 1.1-1.3× | T4's 320 GB/s memory bandwidth is the bottleneck for FLUX2. Compile helps modestly on DiT attention ops. |
| cuDNN autotune | ⚠️ | ~3-8% | Small benefit on Turing. Workspace buffers compete with 16 GB VRAM — may cause OOM on FLUX2. |
| Channels-last | ✅ | 3-8% | UNet conv layers see modest gain. For DiT (FLUX2), convs are a small fraction — benefit is lower. Risk of format-thrashing overhead on unsupported ops. |
| **Pick** | | **SDPA (FA2)** | Only viable attention backend. Skip xFormers on Turing. |
| **Verdict** | | **~1.3-1.7× over baseline** | Budget tier. Bottlenecked by memory bandwidth (320 GB/s) and no INT8/FP8/SA. FLUX2 with 16 GB is likely infeasible. |

---

## A10G / A100 (Ampere SM 8.0/8.6, 24-80 GB)

**Default flags in this worker:** `--force-fp16 --use-sage-attention`

| Opt | Verdict | End-to-end gain | Notes |
|-----|---------|-----------------|-------|
| FP16/BF16 | ✅✅ | ~40% VRAM, ~35% speed | BF16 Tensor Cores available on Ampere (SM 8.0+). Use BF16 for wider range. |
| SageAttention2 | ✅ | ~1.5× attention (INT8) | INT8 Tensor Cores on SM 8.0+. SageAttention paper (PMLR 2025) benchmarks ~2-3× over FA2 on Ampere. Requires Triton ≥3.0. Explicitly install `triton>=3.0.0`. |
| FlashAttention2 | ✅✅ | ~1.3-1.7× attention | Already in PyTorch SDPA. **Auto-selected** for FP16/BF16, head dim 64/128, SM 8.0+. |
| xFormers | ⚠️ | ~1.05-1.15× | ComfyUI blacklists v0.0.21-0.0.26 (`BROKEN_XFORMERS`). On Ampere, xFormers provides minimal gain over SDPA FA2. |
| FP8 (E4M3) | ❌ | — | No FP8 Tensor Cores on Ampere. Software emulation is slower than FP16. Confirmed by NVIDIA. |
| torch.compile | ✅ | 1.2-1.5× (A10G) / 1.5-2× (A100) | A10G (600 GB/s, fewer TCs) benefits less than A100 (2000 GB/s). Full Triton on Modal Linux. `mode="max-autotune"`. |
| cuDNN autotune | ✅ | 5-12% end-to-end | Per-op conv speedup is ~1.3×, but end-to-end gain for mixed conv-attention (FLUX2) is much smaller. A100 has VRAM headroom on 40/80 GB. |
| Channels-last | ✅ | 3-10% | Measurable conv speedup on UNet layers. FLUX2 has few convs — lower benefit. |
| **Pick** | | **SageAttention2** (best perf) or **SDPA FA2** (zero effort) | SageAttention2 gives meaningful lift on Ampere+ INT8 cores. Fall back to SDPA if Triton version mismatch (need ≥3.0). |
| **A10G verdict** | | **~1.4-2.0× over baseline** | Solid value. SageAttention + compile give biggest lift. 24 GB is tight for FLUX2 (17 GB weights + activations). |
| **A100 verdict** | | **~1.8-2.5× over baseline** | More VRAM headroom. Larger compile gain. Giants: SageAttention + compile. |

---

## L4 / L40S (Ada SM 8.9, 24-48 GB)

**Default flags in this worker:** `--force-fp16 --use-sage-attention`

| Opt | Verdict | End-to-end gain | Notes |
|-----|---------|-----------------|-------|
| FP16/BF16 | ✅✅ | ~35% | Done. |
| SageAttention2 | ✅✅ | ~1.5-2× attention | Ada INT8 Tensor Cores are fast. **But**: the "~2.7×" figure cited in SageAttention paper is RTX 4090 (fully-enabled AD102). L40S is cut-down AD102. L4 is AD106 (~300 GB/s — bandwidth bottlenecked). Corrected gain: L40S ~1.8-2× attention, L4 ~1.5×. |
| FlashAttention2 | ✅✅ | ~1.3-1.7× attention | Already in PyTorch SDPA. |
| xFormers | ⚠️ | Negligible | xFormers is NOT harmful — it works. But it provides **no benefit over SDPA FA2** on Ada. ComfyUI community recommends disabling. SageAttention README says "Skip xFormers — it adds no benefit." Some xFormers versions (0.0.31+) can cause crashes on Blackwell 50-series, not Ada. |
| FP8 (E4M3) | ✅✅ | ~1.3-1.7× vs FP16 | Ada has FP8 Tensor Cores (SM 8.9). Use `comfy-kitchen` FP8 checkpoints. For FLUX2 (9B UNet FP8): reduces memory bandwidth pressure. **Not** 2× end-to-end — it's ~2× per matmul, but total pipeline includes non-matmul ops. |
| torch.compile | ✅✅ | 1.5-2× (DiT) | Ada benefits strongly. FLUX2's mixed conv-attention limits max gain (pure-attention models get more). Full Triton on Modal Linux. |
| cuDNN autotune | ✅✅ | 5-15% end-to-end | Ada cuDNN is mature. L40S has 48 GB — plenty of headroom. |
| Channels-last | ✅ | 3-8% | Same caveat: format thrashing risk. |
| **Pick** | | **SageAttention2** (best perf on Ada) | FA3 not available on Ada (SM 8.9). SageAttention2 is the top attention opt. |
| **L4 verdict** | | **~1.5-2.5× over baseline** | Great value but L4's 300 GB/s bandwidth limits gains. The 24 GB VRAM is tight for FLUX2. |
| **L40S verdict** | | **~2-3× over baseline** | FP8 + SageAttention + compile all stack. Best Ada card for FLUX2. 48 GB is comfortable. |

---

## H100 / H200 (Hopper SM 9.0, 80-141 GB)

**Default flags in this worker:** none. Native FP8/BF16 paths are preferred; opt into attention backends explicitly after measurement.

| Opt | Verdict | End-to-end gain | Notes |
|-----|---------|-----------------|-------|
| FP16/BF16 | ✅✅ | ~35% | Baseline. |
| FlashAttention3 | ✅✅ | ~1.5-2× (FP16) / ~2-3× (FP8) attention | **Hopper exclusive.** FA3 uses WGMMA + TMA — SM 9.0 only. Not available on Ada, Blackwell. PyTorch blog benchmarks: "1.5-2.0x faster than FlashAttention-2 with FP16." The 3× upper bound requires optimal sequence lengths and FP8. |
| SageAttention2 | ✅✅ | ~1.3-1.5× attention | **Alternative to FA3, not stackable.** SageAttention2 paper states it "matches the speed of FlashAttention3(fp8)" as an alternative implementation. Use FA3 on Hopper (it's more optimized for SM 9.0). SageAttention2 if FA3 has issues. |
| FlashAttention2 | ✅✅ | ~1.3-1.7× | Also available as fallback. |
| xFormers | ⚠️ | Negligible | FA3/SA/SDPA all faster. No reason to install. |
| FP8 (E4M3) | ✅✅ | ~1.5-2× vs FP16 | Hopper has FP8 Tensor Cores with FP8 accumulation. Native support. |
| NVFP4 | ❌ | — | Blackwell only. |
| torch.compile | ✅✅ | 1.8-2.5× (DiT) | Hopper compilation is well-optimized. `mode="max-autotune"` recommended. |
| cuDNN autotune | ✅✅ | 10-15% end-to-end | Big gain on Hopper. Sufficient VRAM. |
| Channels-last | ✅ | 3-8% | Works. |
| **Pick** | | **FA3** (best perf) | FA3 + FP8 is the peak combo for Hopper. SageAttention2 as fallback. |
| **Verdict** | | **~2.5-3.5× over baseline** | FA3 (OR SageAttention2, not both) + FP8 + compile. At H100/H200 price points this is the expected tier. |

---

## RTX PRO 6000 / B200 (Blackwell SM 12.0/10.0, 96-180 GB)

**Critical prerequisite:** CUDA 12.8+ (CUDA 12.8 fully supports Blackwell, including NVFP4 micro-scaled formats in cuBLASLt). CUDA 13.0 extends B300 (SM 103) and DGX Spark support but is NOT required for Blackwell.

**Default flags in this worker:** none. Native SDPA/FP8 paths are preferred; opt into attention backends explicitly after measurement.

**Do NOT install xFormers** on Blackwell — pip dependency resolution may downgrade PyTorch from the cu128 build. If you must install it, pin PyTorch first (`pip install torch==<cu128-version>`) or use `--no-deps`. xFormers v0.0.31+ is known to cause crashes on Blackwell 50-series (ComfyUI issue #8861).

| Opt | Verdict | End-to-end gain | Notes |
|-----|---------|-----------------|-------|
| FP16/BF16 | ✅✅ | ~35% | Baseline. |
| FlashAttention-4 | ✅✅ | ~2-3× attention (BF16) | **RELEASED** (v4.0.0.beta0, March 2026, arXiv 2603.05451). Targets Blackwell and Hopper using CuTeDSL. Reaches 1613 TFLOPS (71% utilization) on B200 BF16. Integrated with PyTorch FlexAttention (PyTorch blog, March 2026). Install as `flash-attn-4`. **This should be the primary attention backend on Blackwell.** |
| SageAttention2++ | ✅✅ | ~1.2-1.35× over SDPA | Works on Blackwell (setup.py patch may be needed). Real kernel variant (`--pv_accum_dtype fp32+fp16` two-level accumulation). FA4 is preferred (better Blackwell optimization), SageAttention2++ is a fallback. |
| FlashAttention2 | ✅✅ | ~1.3-1.7× | Works. FA4 is better. |
| FlashAttention3 | ❌ | — | SM 9.0 only. Blackwell is SM 10.0/12.0. |
| xFormers | ❌❌ | **Risk of PyTorch downgrade** | pip dependency resolution may downgrade PyTorch from cu128 to an older build, removing Blackwell kernel support. Pin PyTorch or `--no-deps`. Even if installed, provides no benefit over FA4/SA. |
| FP8 (MXFP8) | ✅ | ~1.3-1.5× | Via `comfy-kitchen`. MXFP8 block quantization (32-element blocks, E8M0 scales). Eager backend only currently. |
| NVFP4 | ✅✅ | ~1.5-2× vs FP8 (~2.5-3.5× vs FP16) | **Blackwell exclusive.** 4-bit float with 2-level scaling (E4M2 per 16-element block + FP32 per-tensor). Needs CUDA 12.8+ (not 13.0 — that's a common misconception). Use `comfy-kitchen[cublas]`. **NVFP4 pipeline in ComfyUI is not fully production-mature yet** — expect some friction. |
| torch.compile | ✅✅ | 1.5-2.5× (DiT) | CUDA 12.8+ + Triton. Well-supported. |
| cuDNN autotune | ✅✅ | 10-20% end-to-end | Blackwell's new Tensor Core features (NVFP4, 2-CTA MMA, TMEM, Tensor Memory) likely amplify autotune benefit. Exact ComfyUI benchmarks not public yet. |
| Channels-last | ✅ | 3-8% | Works. |
| **Pick** | | **FA4** (best attention) + **NVFP4** (best quantization) | FA4 for attention, NVFP4 for weights. Compile + autotune on top. |
| **Verdict** | | **~2.5-4× over baseline (conservative — pipeline not mature)** | FA4 is real and released. NVFP4 pipeline in ComfyUI still maturing. The upper bound depends on ComfyUI/`comfy-kitchen` integration. RTX PRO 6000 (96 GB) and B200 (180 GB) have abundant VRAM. |

---

## Priority Stack by GPU

### T4 (budget)
```
--force-fp16  →  cuDNN autotune  →  channels-last
```
That's it. 3 flags. Don't try Sage, FP8, or heavy compile. **FLUX2 likely infeasible on 16 GB.**

### A10G (standard)
```
--force-fp16  →  --use-sage-attention  →  optional torch.compile A/B
```
Avoid blanket `--fast` unless an A/B run shows no quality or VAE regression. Explicitly upgrade Triton before SageAttention2 experiments: `pip install triton>=3.0.0 --upgrade`.

### L4 / L40S (high-mem)
```
--force-fp16  →  --use-sage-attention  →  FP8 checkpoints where applicable  →  optional torch.compile A/B
```
For L40S: add FP8 checkpoints. For FLUX: `--fp8-quantile --fp8-fast-mode`.
Avoid blanket `--fast` unless an A/B run shows no quality or VAE regression.
L4 (24 GB) is tight for FLUX2 — monitor OOMs.

### H100 / H200 (high-mem)
```
native SDPA by default  →  optional attention backend A/B  →  optional torch.compile
```
Install `flash-attn-4` or `flash-attn` only when the runtime can actually route ComfyUI attention through it.
FP8 checkpoints strongly recommended.
torch.compile is available via the ComfyUI wrapper; measure first-run compile cost separately from steady-state speed.
SageAttention2 available as fallback if FA3/FA4 have issues.

### B200 / RTX PRO 6000 (high-mem)
```
CUDA 12.8+ (mandatory — NOT 13.0 specifically)
native SDPA by default  →  optional COMFYMODAL_ATTENTION_BACKEND A/B  →  optional torch.compile
```
Install `flash-attn-4` only when the runtime can actually route ComfyUI attention through it.
Use NVFP4 checkpoints with `comfy-kitchen[cublas]`.
torch.compile is available via the ComfyUI wrapper; measure first-run compile cost separately from steady-state speed.
SageAttention2++ / `sage_qk_int8_pv_fp16_cuda` is explicit opt-in via `COMFYMODAL_ATTENTION_BACKEND=sage_qk_int8_pv_fp16_cuda` when installed.
**xFormers — pin PyTorch before installing, or skip entirely.**

---

## How to Pass Flags in Modal

In `comfyapp.py`, flags are selected by `GPU_OPTIMIZATION_FLAGS` and propagated to the subprocess backend. The in-process backend mirrors the same settings in `comfy.cli_args.args`.

```python
extra_args = [
    "--force-fp16",
    "--use-sage-attention",
]
```

For per-GPU flag sets, key off the `gpu` field in `ModalWorkerConfig`:

```python
GPU_FLAGS = {
    "t4":   ["--force-fp16"],
    "a10g": ["--force-fp16", "--use-sage-attention"],
    "l4":   ["--force-fp16", "--use-sage-attention"],
    "l40s": ["--force-fp16", "--use-sage-attention"],
    "a100": ["--force-fp16", "--use-sage-attention"],
    "a100-40gb": ["--force-fp16", "--use-sage-attention"],
    "a100-80gb": ["--force-fp16", "--use-sage-attention"],
    "h100": [],
    "h200": [],
    "rtx-pro-6000": [],
    "b200":  [],
}
```

Note: SageAttention is not listed for Hopper/Blackwell — FA3/FA4 are the preferred attention backends there. SageAttention can be added as a fallback.

---

## Revision History

| Date | Changes |
|------|---------|
| 2026-05-31 | Aligned worker defaults with measured RTX PRO 6000 behavior: removed `--fast`, removed Blackwell/Hopper `--force-fp16`, defaulted Blackwell/Hopper to native SDPA, and made Sage CUDA backend explicit opt-in. |
