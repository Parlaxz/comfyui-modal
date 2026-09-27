# RA4 Sage / Comfy Kitchen Attention Forensics

**Scope:** read-only investigation of the current ComfyModal Golden workflow,
historical artifacts, Git history, pinned ComfyUI, SageAttention upstream, and
Comfy Kitchen upstream.

**Repository state:** this report is the only file created by RA4. No source,
dependency, deployment, shared environment, or Git state was changed.

## 1. Executive verdict

The current workflow requests Sage through `PathchSageAttentionKJ`, but the
request is converted to a PyTorch callable before Sage is reached:

```text
PathchSageAttentionKJ / sage_attention=auto
  -> ComfyModal KJNodes get_sage_func wrapper
  -> attention_fallback
  -> comfy.ldm.modules.attention.attention_pytorch
  -> comfy.ops.scaled_dot_product_attention
```

RA1 directly observed this chain on three accepted Golden runs. The artifact
records `actual_backend=pytorch_sdpa`, `pytorch_override=300`,
`sage_override=0`, and a callable chain ending at `attention_pytorch`
(`artifacts/phase_p1_serial_golden_v1/cohort_2026-08-29_07-04-45_e2294c/summary.json:1882-1919`).

The first **decision** that permits fallback is the Sage runtime policy:
missing `.so` files, failed `_fused` import, or failed CUDA smoke test produce
`triton_fallback` (`comfyapp.py:6484-6493`). The first **callable-level** edge
that actually turns an automatic/explicit Sage request into PyTorch is
`patch_kjnodes_get_sage_func()` returning `attention_fallback`
(`comfyapp.py:6496-6531`). That closure calls KJNodes' PyTorch function
(`comfyapp.py:6513-6525`).

The strongest current root-cause conclusion is a policy/availability/cache
failure, not proof that Sage source was never installed. The current image
build pins and builds SageAttention 2.2.0, but runtime acceptance is weak and
a cached fallback can be reused without re-probing.

The correct first restoration target is **official SageAttention 2.2.0
SageAttention2++ behavior on `sm120`**, not Sage3. Golden Sage must be
fail-closed: an unavailable, incompatible, failed, or unexpectedly bypassed
Sage path must fail the run rather than silently relabeling PyTorch as Sage.

The pinned local ComfyUI is `v0.24.0`, commit
`f49bdb655707b97952dcef40e12e5af1f08d2007`, with `comfy-kitchen==0.2.10`.
It lacks the official Comfy Kitchen INT8 attention integration. That
integration was added by ComfyUI commit
[`bf4c9a08`](https://github.com/Comfy-Org/ComfyUI/commit/bf4c9a08fc854df6d3b2bef1b92b509e2ef2d2c9);
current upstream uses Kitchen 0.2.31. Kitchen INT8 is a supported conditional
candidate for this target, but is not available through the current pin.

## 2. Exact current Sage state machine

### 2.1 Request and model patch path

The Golden workflow contains `PathchSageAttentionKJ` with intended selector
`sage_attention=auto`. KJNodes obtains a Sage callable through `get_sage_func`
and installs an attention override in the active model patcher.

At restore, ComfyModal scans loaded modules for `model_optimization_nodes.py`
and calls `patch_kjnodes_get_sage_func()` with the selected
`baked_cuda_available` boolean (`comfyapp.py:14563-14578`).

### 2.2 Runtime-mode selection

`_select_sage_runtime_mode()` performs this sequence
(`comfyapp.py:14449-14507`):

1. Reuse a sticky per-instance mode if one was already selected.
2. Read runtime mode and probe overrides.
3. An explicit `baked_cuda` or `triton_fallback` override wins immediately.
4. If probing is disabled, load the persistent cache.
5. If no cache exists, default Blackwell/RTX PRO 6000 to `baked_cuda` and all
   other GPUs to `triton_fallback` without proving the package.
6. If probing is enabled, load the cache.
7. On a cache miss, enumerate `sageattention/*.so`, verify `_fused`, locate a
   supported backend symbol, and execute a tiny CUDA smoke test.
8. `choose_sage_runtime_mode()` returns `disabled`, `triton_fallback`, or
   `baked_cuda`, with reasons for disabled, missing extensions, unusable
   extensions, smoke failure, or usable compiled extensions.
9. Persist the result and return it as the sticky runtime mode.

### 2.3 Capability characterization

The current verifier (`comfyapp.py:14421-14447`) checks:

- at least one `sageattention/*.so`;
- importability of `sageattention._fused`;
- a callable named first `sageattn_qk_int8_pv_fp16_cuda`, then
  `sageattn_qk_int8_pv_fp8_cuda`;
- a tiny `[1,16,8,64]`, FP16, CUDA smoke call in `NHD` layout.

It does not prove the production Z-Image geometry. Also,
`_preferred_sage_backend()` currently prefers FP16 and supplies
`pv_accum_dtype="fp32+fp32"` for the FP8 candidate
(`comfyapp.py:14409-14419`), unlike the upstream Blackwell Sage2++
recommendation of FP8-PV, per-warp Q/K quantization, and
`pv_accum_dtype="fp32+fp16"`.

### 2.4 First fallback edge

When the selected mode is not `baked_cuda`, the wrapper sees `auto` or a
selector containing `sageattn` and returns a new `attention_fallback` closure
(`comfyapp.py:6507-6527`). It does not call the original KJNodes Sage selector.
The closure calls the captured `attention_pytorch` function, so the flow never
reaches ComfyUI's `attention_sage` or a Sage native extension.

This is earlier than the fallback inside ComfyUI `attention_sage()`, which also
catches a Sage exception and calls PyTorch
(`ComfyUI/comfy/ldm/modules/attention.py:543-591`). RA1 proves the active edge
is the ComfyModal KJNodes wrapper, not that inner Sage fallback.

### 2.5 ComfyUI attention seam

Pinned ComfyUI `JointAttention` calls
`optimized_attention_masked(..., skip_reshape=True, transformer_options=...)`
(`ComfyUI/comfy/ldm/lumina/model.py:139-165`). `wrap_attn` checks
`transformer_options["optimized_attention_override"]` and dispatches to it
before the selected global function
(`ComfyUI/comfy/ldm/modules/attention.py:127-143`). The override chain is
therefore more authoritative for this workflow than the global
`optimized_attention` variable.

## 3. Current observed evidence

The three accepted RA1 observations passed the exact Golden SHA and CacheDiT
contract:

| Observation | Sampling wall | CacheDiT | SHA |
|---|---:|---|---|
| `07-04-45_e2294c` | 6401.144 ms | 17 / 10 / 7 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `07-07-46_ce93a9` | 5899.185 ms | 17 / 10 / 7 | same |
| `07-09-47_144216` | 5980.058 ms | 17 / 10 / 7 | same |

RA1 reports a median near 5.98 s and explicitly says attention is Sage
override -> fallback -> `attention_pytorch` -> PyTorch SDPA
(`RA1_SAMPLER_NEXTDIT_DECOMPOSITION_AND_REPAIR_REPORT.md:22-37`). CacheDiT is
healthy and is not the failure.

## 4. Historical implementation and backend determination

| Era/evidence | Intended or observed variant | Actual evidence classification |
|---|---|---|
| SageAttention 1.0.6 branch | Triton V1, primarily older GPU target | Not the preferred Blackwell target; no fast-run proof |
| June baked-Sage plan | SageAttention 2.2.0 CUDA artifact | `STRONGLY_SUPPORTED_SAGE` as intended design, not kernel proof (`docs/superpowers/plans/2026-06-01-baked-sageattention-restore.md:1-21,226-240`) |
| `PERFORMANCE_BASELINE.md` v2.14.0 | Labeled `baked_cuda` on RTX PRO 6000 SM12.0 | `STRONGLY_SUPPORTED_SAGE`, but no native trace (`PERFORMANCE_BASELINE.md:1-8,57-62`) |
| June optimization notes | Claims Sage2.2.0 Blackwell CUDA and ~5.174 s sampler | Documentation only (`optimization_summary_2026-06-03.md:30-46`) |
| R43, commit `9a428fdb19b958b1b217f8f805055fca56207965`, 2026-08-24 18:18:55 -0500 | Fast 4.8-5.0 s regime with Sage configured | `UNKNOWN`; no callable or kernel marker |
| Current image | SageAttention v2.2.0 source build | Recipe exists; current runtime proves fallback |

The historical 4.835 s run is not `PROVEN_FUSED_SAGE` or
`PROVEN_SAGE_TRITON`. It is at most strongly supported as an intended Sage
configuration and `UNKNOWN` as an executed backend. Timing cannot distinguish
fused CUDA Sage, Sage Triton, or another optimized path.

## 5. Regression window and candidate changes

The smallest defensible window is between the R43 fast-path checkpoint on
2026-08-24 and the Aug 27-29 Golden lifecycle/policy revisions. Exact
single-commit attribution is not proven because historical fast artifacts lack
callable/kernel markers.

| Candidate | Supporting evidence | Limitation | Effect/confidence |
|---|---|---|---|
| Sage policy/KJNodes wrapper | Current wrapper explicitly converts non-baked mode to PyTorch; RA1 sees it | Wrapper is deterministic safe-fallback behavior | Direct mechanism / high |
| Snapshot CUDA-extension blocker | Snapshot blocks `sageattention._*` and CUDA modules (`comfyapp.py:16816-16901`) | Blocker is removed in `finally`; restore is intended to reselect baked CUDA | Import/order failure / moderate |
| Persistent runtime cache | Cache can return `triton_fallback` before probing | It does invalidate obvious GPU/version changes | Fallback survives changes / high |
| Image/build boundary | `.deploy_log:140-150` orders CUDA13, Torch cu130, Triton, Sage build | Build recipe does not prove compatible target symbols | Native import/launch failure / moderate |
| Torch/CUDA/GPU drift | Historical logs mention Torch 2.12 cu130; target is Torch 2.13 cu130 | SM12/CUDA13 remain officially plausible | ABI/launch failure / low-moderate |
| ComfyUI wrapper API | KJNodes depends on `optimized_attention_override` seam | RA1 proves the override itself is reached | Not first current edge / low |

Most likely is a failed/blocked characterization, a persisted
`triton_fallback`, skipped retry, then intentional KJNodes fallback. This is
more credible than a CacheDiT or sampler semantic regression.

## 6. Runtime-mode cache audit

### 6.1 Cache contract

- Path: `/root/comfymodal_runtime_state/.sage_runtime_cache.json`
  (`comfyapp.py:7800-7805`).
- Fields: `mode`, `reason`, `gpu_name`, `sage_version`, `created_at`
  (`comfyapp.py:14535-14552`).
- Validation fields: only `gpu_name` and `sage_version`
  (`comfyapp.py:14519-14533`).
- Write: temporary JSON, `os.replace`, then asynchronous volume commit
  (`comfyapp.py:14553-14559`).
- Lifetime: selected mode is sticky on the app instance.

### 6.2 Failure modes

The identity omits extension hashes/ELF identity, Sage source commit/build
flags, Torch/C++ ABI, `torch.version.cuda`, toolkit `nvcc`, NVIDIA driver,
ComfyUI/KJNodes/ComfyModal source, image/deployment/provider/region, policy
version, backend symbol, and production shape.

Consequently:

1. An old failed probe can poison later deployments when GPU name and Sage
   version still match.
2. A fallback can survive source/dependency changes, especially if the package
   reports the same version or an empty version string.
3. Equal reported GPU names can reuse a decision across providers.
4. Blackwell recognition in the no-cache default is only a string heuristic,
   not a `sm120` capability proof.
5. A cache hit or sticky mode suppresses retry after Sage becomes available.

The exact repair is to version the cache schema and include source/image
identity, Sage commit, extension manifest hash, Torch/CUDA/driver identity,
GPU capability, selected symbol, and probe policy. Invalidate on any mismatch;
do not persist or reuse negative results for explicit Golden Sage; always make
Golden restore do a fresh positive capability/probe check.

## 7. Official SageAttention support on the target

Official sources:

- [SageAttention main](https://github.com/thu-ml/SageAttention)
- [SageAttention v2.2.0](https://github.com/thu-ml/SageAttention/tree/v2.2.0)
- [v2.2.0 core.py](https://raw.githubusercontent.com/thu-ml/SageAttention/v2.2.0/sageattention/core.py)
- [v2.2.0 setup.py](https://raw.githubusercontent.com/thu-ml/SageAttention/v2.2.0/setup.py)
- [SM120 support PR #109](https://github.com/thu-ml/SageAttention/pull/109)
- [Sage3 long-context issue #382](https://github.com/thu-ml/SageAttention/issues/382)

The target RTX PRO 6000 Blackwell Server Edition is SM 12.0 (`sm120`). Official
SageAttention2 source recognizes SM12.0, and the upstream Blackwell requirement
is CUDA >=12.8. Target CUDA 13.0 satisfies that requirement. Torch 2.13.0+cu130
is technically plausible and has upstream issue evidence, but it is not a
blanket ABI guarantee for every image or driver.

### 7.1 Recommended variant

Use **SageAttention v2.2.0, automatic SageAttention2++ `sm120` path**:

```python
from sageattention import sageattn
out = sageattn(q, k, v, tensor_layout="HND", is_causal=False)
```

For explicit verification, the expected Blackwell path is the FP8-PV CUDA
function with per-warp Q/K quantization and `pv_accum_dtype="fp32+fp16"`.
Upstream uses the `sm89` CUDA extension family for the SM120 route; absence of
an `_qattn_sm120` file is not itself a failure. Expected native files include
`_fused*.so` and `_qattn_sm89*.so` under `sageattention/`.

SageAttention2 is the right precision-sensitive baseline because upstream says
Sage2 is more accurate and recommends it over Sage3 for precision-sensitive
applications. Sage3 is a separate future experiment: it has additional
long-sequence/TMA uncertainty on this target class and explicit unsupported
input SDPA fallback behavior.

### 7.2 Build and proof requirements

The current image recipe already has the right broad shape: CUDA
`13.0.0-devel-ubuntu24.04`, Torch from the cu130 index, Triton >=3.0,
SageAttention Git ref `v2.2.0`, `TORCH_CUDA_ARCH_LIST=12.0+PTX`, `.so`
enumeration, and `_fused` import assertions (`comfyapp.py:7833-7897`).

The recipe is not sufficient proof. Record independently:

```text
torch.__version__
torch.version.cuda
torch.cuda.get_device_capability()
nvcc --version
nvidia-smi / driver version
sageattention.__file__
sageattention._fused.__file__
sageattention._qattn_sm89.__file__
```

Then profile the real active attention call. Native proof needs the expected
Sage custom CUDA kernels or native custom-op activity in a PyTorch profiler or
Nsight trace during a production-shaped call. Import success, `.so` presence,
Triton cache files, or a node label is insufficient.

## 8. Exact recommended Sage restoration design

For an explicit Golden Sage arm:

```text
request Sage
  -> fresh identity-bound capability probe
  -> exact Sage2++ backend selected
  -> representative production-shape probe
  -> strict callable instrumentation
  -> real Sage native kernel
```

Any of these must fail the run: unavailable package, missing/incompatible
extension, `_fused` import failure, unsupported SM/Torch/CUDA/driver, failed
probe, Sage exception, KJNodes/ComfyUI fallback, observed
`attention_pytorch`/SDPA, or unexpected backend call.

Normal workflows may retain upstream fallback semantics. Strictness belongs to
the Golden experiment policy.

The smallest implementation surface is:

1. `comfyapp.py`: `_preferred_sage_backend()`,
   `_verify_baked_sageattention_runtime()`, `_select_sage_runtime_mode()`,
   cache helpers, `patch_kjnodes_get_sage_func()`, and strict diagnostics.
2. Existing RA1 instrumentation in `comfymodal_runtime/golden_serial.py` and
   `comfymodal_runtime/sampling_deep_profile.py`, making backend/fallback counts
   a hard gate.
3. Tests for cache invalidation, strict failure, exact backend selection, and
   no-SDPA behavior.

Keep the snapshot CUDA-import blocker, but make restore probing fresh for
Golden. Select the upstream Sage2++ callable rather than the current
FP16-first / `fp32+fp32` preference. Do not patch ComfyUI core to hide a
failure.

## 9. Current Comfy Kitchen integration status

### 9.1 Local pinned state

The local ComfyUI checkout is v0.24.0 at commit
`f49bdb655707b97952dcef40e12e5af1f08d2007`.

Evidence that the official attention integration is absent:

- `ComfyUI/comfy/cli_args.py:94` has `--enable-triton-backend`, but no
  `--use-ck-attention`.
- `ComfyUI/comfy/ldm/modules/attention.py:23-40,739-776` has Sage, Flash,
  xFormers, and PyTorch selection, but no
  `attention_comfy_kitchen_int8`.
- `ComfyUI/requirements.txt:25` pins `comfy-kitchen==0.2.10`.
- Local Kitchen imports in `comfy/float.py` and `comfy/quant_ops.py` support
  quantization utilities, not the INT8 attention integration.
- Local logs report Kitchen 0.2.10 and CUDA quantization capabilities, not the
  official INT8 attention backend.

The current pinned Modal source is therefore not ready for the Kitchen arm.

### 9.2 Official integration

Official sources:

- [ComfyUI integration commit bf4c9a08](https://github.com/Comfy-Org/ComfyUI/commit/bf4c9a08fc854df6d3b2bef1b92b509e2ef2d2c9)
- [Current ComfyUI attention](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/ldm/modules/attention.py)
- [Current ModelAttentionBackend](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_model_advanced.py)
- [Comfy Kitchen](https://github.com/Comfy-Org/comfy-kitchen)
- [Kitchen INT8 attention](https://github.com/Comfy-Org/comfy-kitchen/blob/main/comfy_kitchen/sage_attention.py)
- [Kitchen INT8 tests](https://github.com/Comfy-Org/comfy-kitchen/blob/main/tests/test_int8_attention.py)

The supported path is a ComfyUI update to the official integration or a later
compatible revision, with the matching Kitchen pin. The original integration
used Kitchen 0.2.30; current upstream uses 0.2.31. Prefer that update over a
home-grown implementation. If an update is impossible, backport the complete
official integration as a bounded change rather than recreating its dispatcher.

The global `--use-ck-attention` path is fail-closed when Kitchen INT8 is absent.
`ModelAttentionBackend` can warn and fall back to PyTorch when a requested
backend is unavailable. A successful node execution is therefore not proof:
selected backend and actual native operation must be recorded.

## 10. Comfy Kitchen compatibility with RA1 NextDiT

### 10.1 Observed geometry

The RA1 artifact records the repeated real attention input as:

```text
pre-projection input: [B=1, sequence=8448, model_dim=3840]
dtype: bfloat16
device: cuda:0
```

The model config identifies Z-Image/Lumina2 with `dim=3840`, `n_heads=30`,
`n_kv_heads=30`, BF16, and patch size 2. The source splits Q/K/V and moves them
to `[B,H,S,D]` (`ComfyUI/comfy/ldm/lumina/model.py:139-163`):

```text
q: [1, 30, 8448, 128]
k: [1, 30, 8448, 128]
v: [1, 30, 8448, 128]
dtype: bfloat16
layout: HND
GQA: no (30 Q heads / 30 KV heads)
causal: false
mask: None in this path
```

`patchify_and_embed()` sets `cap_mask=None` and returns `mask=None`
(`ComfyUI/comfy/ldm/lumina/model.py:702-800`). The RA1 summary contains 300
PyTorch override observations across ten real computes; repeated shape evidence
is consistent. The model declares 32 main layers, so the instrumentation count
is an observed dispatch scope, not a claim that every refiner/main layer was
counted identically.

### 10.2 Kitchen constraints

Official Kitchen INT8 attention accepts four-dimensional CUDA tensors, FP32,
FP16, or BF16, head dimensions up to 256, unequal Q/K lengths, and Q-heads
divisible by KV-heads. It has native CUDA/HIP implementations and no eager
fallback for this INT8 operation. It has no `is_causal` parameter; causal
semantics require an explicit mask.

The RA1 geometry satisfies these constraints: BF16, head dimension 128,
equal head counts, no mask, and non-causal attention. The intended backend is
native CUDA Kitchen INT8. Triton/eager must not be reported as Kitchen INT8.

Prove every measured run with:

```text
requested_backend=COMFY_KITCHEN_INT8
selected_backend=comfy_kitchen_int8
availability=True
actual_callable=comfy_kitchen.int8_attention (or official native wrapper)
native_backend=cuda
fallback_count=0
```

A profiler/Nsight trace must show Kitchen native custom CUDA activity. If
`ModelAttentionBackend` logs “unavailable; using PyTorch attention,” the arm is
PyTorch and must be labeled/rejected.

## 11. Exactness implications

Kitchen INT8 attention quantizes Q/K/V to signed INT8, uses unsigned INT8
attention probabilities, and performs fused transforms and FP32 scaling and
softmax-related arithmetic. It is not a bitwise replacement for BF16 PyTorch
SDPA or Sage.

Official sources/tests establish numerical correctness within tolerances, not
bitwise equality. CUDA parallel reductions and backend differences can also
produce small differences. Report these independently:

```text
PERFORMANCE=<timings>
EXACT_GOLDEN_SHA_MATCH=YES|NO
```

If Kitchen is faster but SHA differs, it is a performance candidate that does
not satisfy the exact Golden contract. Never weaken the canonical SHA gate.

## 12. Three-arm benchmark design

| Arm | Requested backend | Acceptance condition |
|---|---|---|
| A | PyTorch SDPA | Actual callable ends at PyTorch SDPA; explicit baseline |
| B | Restored Sage2++ | Actual callable reaches Sage2++ native CUDA; zero fallback |
| C | Comfy Kitchen INT8 | Official `comfy_kitchen_int8` selected and native CUDA observed; zero fallback |

All arms use the same model, workflow, prompt, seed, sampler, scheduler,
CacheDiT 17/10/7 contract, QD/model-loading path, restore policy, GPU class,
stage order, timing boundaries, and no-concurrency condition. Backend selector
and package identity belong in run identity, without silently changing source or
deployment identity.

One deployment is safe only with a request-local/model-level selector on the
active ModelPatcher immediately before sampling, restoration of previous state,
no concurrent requests, and actual-callable proof. If the implementation uses
process-global CLI flags, global `optimized_attention`, sticky mutable KJNodes
state, or cannot restore the patcher, use separate deployments. Never toggle a
global flag between arms and call that a fair comparison.

Record per arm:

- total Golden sampling wall;
- ten real NextDiT compute wall;
- cumulative attention wall and attention CUDA wall;
- cumulative MLP wall;
- first compute and steady-state compute median;
- seven CacheDiT skips and 17/10/7 counters;
- Python-resume -> durable wall;
- requested/selected/actual backend, native kernel, and fallback count;
- package/version, ComfyUI/KJNodes revisions, GPU/provider/region;
- output SHA and `EXACT_GOLDEN_SHA_MATCH`.

The primary comparison is Sage versus Kitchen versus PyTorch on identical
`[1,30,8448,128]`, BF16, HND, non-causal, unmasked attention. Do not benchmark
an arm whose actual callable is PyTorch.

## 13. Files/functions for the implementer

Touch or verify only:

- `comfyapp.py`: `_preferred_sage_backend`,
  `_verify_baked_sageattention_runtime`, `_select_sage_runtime_mode`, cache
  helpers, `patch_kjnodes_get_sage_func`, and strict diagnostics;
- `comfymodal_runtime/golden_serial.py`;
- `comfymodal_runtime/sampling_deep_profile.py`;
- focused tests for strict policy, cache identity, and actual backend proof;
- the ComfyUI pin/requirements boundary and official
  `ModelAttentionBackend` integration, through an upstream update or faithful
  bounded backport.

Do not infer Sage from node configuration, timing, imports, `.so` presence, or
Triton cache files. Do not allow Golden Sage to fall back silently. Do not use
Sage3 first, home-grow Kitchen attention, benchmark a silent fallback, weaken
the SHA gate, mix global state between arms, or remove the snapshot CUDA blocker
without re-proving restore safety.

## 14. Confidence-ranked conclusions

1. **High:** Current RA1 production attention is PyTorch SDPA, directly recorded.
2. **High:** The first callable fallback is the ComfyModal KJNodes wrapper,
   not ComfyUI's inner Sage exception fallback.
3. **High:** The runtime cache key is too weak and can preserve fallback over
   source, image, Torch, CUDA, driver, and extension changes.
4. **High:** SageAttention2.2.0/Sage2++ is the correct first Blackwell target;
   actual driver/ABI/build proof remains required.
5. **High:** Pinned local ComfyUI lacks official Kitchen INT8 attention and uses
   Kitchen 0.2.10.
6. **High:** RA1 Z-Image attention geometry satisfies Kitchen's documented
   native INT8 constraints.
7. **Moderate:** Failed/blocked characterization plus persisted
   `triton_fallback` and skipped retry is the most likely regression mechanism.
8. **Moderate:** Exact historical 4.8-5.0 s backend is unknown; intended Sage is
   strongly supported but native execution is unproven.
9. **Likely/conditional:** Kitchen is supported on the target if Linux CUDA
   wheel and driver prerequisites are met, but requires official integration and
   native availability proof.

RA4_EXPLORATION_COMPLETE=YES
REPOSITORY_MODIFIED=NO
CURRENT_BACKEND=PYTORCH_SDPA
SAGE_FIRST_BROKEN_EDGE=patch_kjnodes_get_sage_func: non-baked auto/sageattn -> attention_fallback -> attention_pytorch
HISTORICAL_SAGE_CLASSIFICATION=UNKNOWN
RECOMMENDED_SAGE_VARIANT=SageAttention2.2.0 SageAttention2++ sm120 FP8-PV CUDA
COMFY_KITCHEN_SUPPORTED_ON_TARGET=LIKELY
COMFY_KITCHEN_INTEGRATION_PATH=official ComfyUI ModelAttentionBackend / --use-ck-attention integration from bf4c9a08 or later, with matching comfy-kitchen
THREE_ARM_COMPARISON_READY=YES
REPORT=RA4_SAGE_AND_KITCHEN_ATTENTION_FORENSICS_REPORT.md
