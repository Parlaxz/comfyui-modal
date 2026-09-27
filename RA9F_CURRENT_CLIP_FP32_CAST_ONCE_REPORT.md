# RA9F — Current CLIP FP32 Cast-Once Proof and Integration Design

## Scope and evidence boundary

This is a read-only current-source audit. `golden_serial.py` was not changed,
and no Golden wiring, deployment, Modal request, or remote A/B was performed.
The pinned ComfyUI checkout is at `f49bdb655707b97952dcef40e12e5af1f08d2007`
(`v0.24.0-dirty`); its unrelated local `comfy/model_management.py` diff does
not change the audited `cast_to` body at `:1470-1496`.

Evidence used:

- current Golden CLIP load/forward source;
- current pinned ComfyUI source for CLIP, Qwen, Linear, RMSNorm, and `cast_to`;
- RV2B's five current remote runs and source-match proof;
- RA9B and the historical E31 report, with the old 2.03 s counter explicitly
  excluded as a whole-forward measurement;
- existing deterministic E31 helper tests (`75 passed`).

RV2B's CLIP forward median is approximately 1543 ms (range 1273–2427 ms).
It did not emit per-forward cast counts, so that wall is not cast-only timing.

## Current Golden execution path

The current Golden path is direct and does not import or call
`clip_fp32_cast_once.py`:

1. `comfymodal_runtime/golden_serial.py:4338-4485` performs one QD read/H2D
   per checkpoint, constructs through `comfy.sd.load_text_encoder_state_dicts`,
   and uses the dynamic patcher plus `assign=True` adoption. It passes the
   transported state dicts unchanged; there is no FP32 transform in this path.
2. `golden_serial.py:4509-4557` proves the selected scope by pointer/storage
   identity. RV2B reports that scope as `cuda:0`, `torch.bfloat16`, with 398
   Qwen tensors and 8,044,936,192 completed H2D bytes
   (`RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md:240-255`).
3. `golden_serial.py:4622-4688` runs the real `CLIPTextEncode` closure and
   `encode_from_tokens_scheduled`; the stage explicitly labels repeated cast
   work `UNPROVEN` at `:4723-4753`. That label is a telemetry limitation, not
   evidence that the casts do not happen.
4. The current source-match proof in RV2B binds this runtime to the current
   source path. No `torch.compile` call or alternate Qwen operator is enabled
   by current Golden. A separately compiled or fallback path would require its
   own proof.

## Exact current operator path

### Entry and compute dtype

- `comfy/sd.py:320-379` selects the unscheduled path for ordinary encoding and
  calls `encode_from_tokens`.
- `comfy/sd.py:381-404` calls `cond_stage_model.encode_token_weights`.
- `comfy/sd1_clip.py:735-738` unwraps the Qwen-specific token-weight mapping.
- `comfy/sd1_clip.py:212-213` creates token IDs and requests embedding output
  with `out_dtype=torch.float32`.
- `comfy/sd1_clip.py:279` invokes the transformer with `dtype=torch.float32`;
  output and masking conversions at `:282-294` are activation/output work,
  not parameter-residency conversion.

Therefore current Golden compute dtype is **`torch.float32`**.

### Resident parameter dtype and load behavior

- `comfy/text_encoders/flux.py:209-211,217-230` selects
  `Qwen3_4BModel`/`Qwen3_4B` for this scope.
- `comfy/sd1_clip.py:109-120` selects `comfy.ops.manual_cast` and constructs
  the model with the selected text-encoder dtype.
- `comfy/sd1_clip.py:308-309` loads with `assign=getattr(..., False)`; the
  current Golden dynamic patcher makes this assignment path active, and
  `golden_serial.py:4475-4485` passes the actual transported tensors.
- RV2B's current source-matched remote adoption proof records the resulting
  selected Qwen scope as BF16/CUDA, not FP32 (`RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md:240-255`).

Thus current normal Golden resident parameter dtype is **`torch.bfloat16`**.
The load/adoption step does not widen those tensors; any widening in the
current normal path occurs at operator use.

### Linear conversions: current repeated work is proven

- `comfy/text_encoders/llama.py:466-480,546-567` builds four attention
  projections plus three MLP projections per layer, all through `ops.Linear`;
  Qwen has 36 layers (`:207-228`). This is 252 Linear weight call sites.
- `comfy/ops.py:777-809` makes `manual_cast.Linear` use the cast-weight
  forward path.
- `comfy/ops.py:445-503` routes Linear forward to `cast_bias_weight`.
- `comfy/ops.py:357-382` first uses `cast_to` for device placement and then
  executes `weight.to(dtype=dtype)` whenever the weight dtype differs from the
  FP32 input dtype.
- `comfy/model_management.py:1470-1481` returns the original tensor only
  when dtype/device already match; BF16 -> FP32 therefore produces a distinct
  FP32 tensor.

The current Golden path has BF16 resident weights and FP32 Linear inputs, and
the current source-match remote forward succeeded on that path. Consequently
the existence of repeated BF16 -> FP32 Linear parameter conversion work is
**PROVEN**. The exact current runtime count/bytes were not emitted by RV2B;
the historical E31 accounting of 252 and 14,533,263,360 FP32 destination
bytes is source-consistent but is not relabeled as a fresh current measurement.

### RMSNorm conversions: current repeated work is proven

- `comfy/text_encoders/llama.py:384-396` implements the Qwen RMSNorm and
  passes its parameter to `comfy.ldm.common_dit.rms_norm`.
- `comfy/ldm/common_dit.py:16` aliases that function to `comfy.rmsnorm.rms_norm`.
- `comfy/rmsnorm.py:7-11` calls `comfy.model_management.cast_to(weight,
  dtype=x.dtype, device=x.device)` on every norm invocation.
- Qwen's current configuration has 36 layers and uses q/k RMSNorms
  (`llama.py:207-228`); each block also has input and post-attention norms
  (`:561-567`), and the final norm is constructed at `:686-689`. The current
  model therefore has 145 RMSNorm invocations when the complete forward runs
  (four per block plus final). The historical approximately-73 observation is
  not reused as a current count.

With BF16 resident norm weights and FP32 activations, `cast_to` takes the
  dtype-conversion branch each time. Current repeated BF16 -> FP32 RMSNorm
  parameter conversion work is therefore **PROVEN**; exact physical allocation
  and remote per-call timing remain unmeasured.

## Allocation and compiled/native caveats

The current normal path creates temporary FP32 tensors per operator call, not
one persistent model-sized FP32 destination. Their aggregate conversion
traffic can be model-sized over a forward. The temporary lifetime and allocator
reuse can hide fresh physical allocation: allocator reuse does not turn a
real BF16 -> FP32 `.to()` operation into a no-op. `memory_allocated()` deltas
would not by themselves prove physical allocation, peak reservation, or
fragmentation.

Current Golden does not enable `torch.compile` or a Qwen-specific fused weight
path. `comfy/ops.py:33-37` only suppresses interruption checks while compiling;
it does not remove the cast condition. Any future compiled graph, low-VRAM/
vbar path, or native fallback needs separate operator-level instrumentation.
RV2B's current artifact proves the normal selected scope and output, but not
the per-forward conversion ledger.

## Cast-once helper audit

`comfymodal_runtime/clip_fp32_cast_once.py` is current and reachable only from
optional hydration paths, including `clip_fast_hydration_wiring.py:1546-1565`
and `:1661-1687`; its environment gate defaults off. It is **not reachable
from current Golden Serial**, which has no helper reference in its load or
forward path.

### What is sound

- `clip_fp32_cast_once.py:85-265` gates on the flag and all-BF16 manifests,
  validates key sets/shapes/dtypes, widens each model tensor once with
  `tensor.to(torch.float32)`, and returns the original input unchanged on
  failure. Partial work cannot be reported as applied.
- `clip_fast_hydration.py:1476-1531` binds the returned mapping through
  `load_sd` with `can_assign_sd=True`; the adopted parameter storage is the
  FP32 tensor, rather than a hidden FP32 cache.
- `clip_fp32_cast_once.py:268-321,486-856,946-977` provides provenance,
  exact key/shape/dtype/device/storage/byte checks, and fail-closed residency
  proof.
- `clip_fast_hydration_wiring.py:1546-1569,1790-1836` checks patch functions,
  verifies residency after bind completion, and advances the cast generation
  only after proof. The normal exception path restores the marker and returns
  a native fallback (`:2004-2048`).
- `clip_fp32_cast_once.py:980-1074` installs/restores a real-forward hook and
  does not itself issue a forward.

### Why the current helper integration is not valid yet

`OWNERSHIP_TRANSFER_HELPER_VALID` is **NO** for the requested integration
contract, despite the widening/adoption primitive being sound:

1. `apply_cast_once` returns new FP32 mappings but does not own or clear the
   caller's BF16 source views. In the current optional wiring,
   `clip_fast_hydration_wiring.py:1639-1687` retains source/transformed maps,
   and `:1814-1818` passes `per_file_sds` into the forward-proof closure before
   `:1851-1857` retires the source owners. Tokenizer entries are also passed
   through rather than widened. The owner-retirement contract therefore needs
   the caller to drop every source-backed view before closing the owner; that
   boundary is not proven here. This is an integration defect outside the
   allowed isolated-helper edit scope.
2. The direct helper generation key at `:368-424` contains object,
   `cond_stage_model`, and patcher-current-object identities, but no independent
   source/manifest generation digest. A same-identity source-generation change
   is not independently represented. Surrounding hydration fingerprints also
   intentionally omit parameter values (`clip_fast_hydration.py:974-1012`), so
   in-place parameter mutation is not automatic generation invalidation.
3. Patch registration and storage replacement are guarded by the surrounding
   hydration fingerprint and `assert_compute_ready_no_patches` at
   `clip_fast_hydration_wiring.py:1546-1565`, but the helper's generation map
   alone does not observe every mutation. Explicit invalidation is required.
4. `verify_resident_fp32(..., expect_device=...)` rejects device mismatch and
   the verifier rejects dtype/storage/byte mismatch. `apply_cast_once` itself
   widens on each tensor's existing device and does not accept an expected
   device; device safety is consequently a bind/proof responsibility.
5. The current model-free CPU snapshot contract is incompatible with retaining
   model-sized FP32 parameter storage or source owners at capture. The helper
   has no snapshot exclusion/lifecycle mechanism; cast-once state must be
   released before a model-free snapshot.

The existing tests prove the useful local subset: one widening, second-forward
zero real conversions through a fake cast surface, pointer stability, exact
residency mapping, mismatch rejection, failure-closed proof, generation
identity, and owner-retirement primitives. They do not prove current Golden
behavior, source-owner closure ordering, independent source-generation
invalidation, or remote latency/equivalence. No new test or helper edit was
made because repairing the identified lifetime/source-generation gaps requires
the owning hydration wiring or a new explicit seam contract, and Golden wiring
is prohibited in this lane.

## Current-safe seam for later integration (design only)

If later integrated outside this lane, the seam should require:

1. Read BF16 source once and widen into independent FP32 tensors before bind.
2. Bind with `assign=True` and prove every compute-scope parameter is FP32,
   on the expected device, and storage-identical to the widened destination.
3. Keep the source owner alive through bind and all proof callbacks; before
   retirement, remove all source-backed state-dict, tokenizer, and callback
   references. Retire the owner only after that transition succeeds.
4. Carry a stable source/manifest generation identity alongside parameter,
   patch, device, dtype, and storage predicates. Any unknown predicate fails
   closed to the normal BF16 path.
5. Keep one adopted FP32 representation as parameter storage. Do not retain a
   second model-sized BF16 GPU copy after the ownership transition.
6. Exclude/release this state before any model-free snapshot capture.
7. Instrument the actual current forward boundary with real-conversion counts,
   destination bytes, output/equivalence identity, fallback status, and owner
   lifetime. A remote same-deployment ON/OFF A/B is required for latency or
   end-to-end benefit claims.

## Final status

```text
RA9F_COMPLETE=YES
CURRENT_REPEATED_LINEAR_CASTS=PROVEN
CURRENT_REPEATED_RMSNORM_CASTS=PROVEN
CURRENT_RESIDENT_DTYPE=torch.bfloat16
CURRENT_COMPUTE_DTYPE=torch.float32
OWNERSHIP_TRANSFER_HELPER_VALID=NO
DUAL_MODEL_SIZED_GPU_COPY_REQUIRED=NO
GOLDEN_WIRING_CHANGED=NO
REMOTE_AB_REQUIRED=YES
MODAL_CONTACTED=NO
REPORT=RA9F_CURRENT_CLIP_FP32_CAST_ONCE_REPORT.md
```
