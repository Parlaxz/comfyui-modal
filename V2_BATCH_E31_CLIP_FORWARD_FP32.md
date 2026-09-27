# V2 Batch E31 — CLIP Forward Variance + Correct FP32 Cast-Once Evaluation

**Mode:** RE-ANCHOR AUDIT + IMPLEMENTATION + LOCAL VALIDATION + REMOTE A/B PREPARATION
**Owner:** Agent E31 (CLIP forward / FP32-cast)
**Date:** 2026-08-19 (re-anchor)
**Git HEAD:** `0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997` (branch `TESTING2`)

```
E31_CLIP_FORWARD_FP32 = READY_FOR_V2CTL_REMOTE_AB
REMOTE_DECISION       = NOT_YET_PROVEN
REMOTE_DEPLOYS        = 0
REMOTE_REQUESTS       = 0
REMOTE_SNAPSHOTS      = 0
```

No commit, push, branch, worktree, stash, reset, revert, or clean was
performed.  No Modal deploy / request / snapshot was performed.  No E29 or
E30 file was modified by E31 except the additive, E31-marked block in
`clip_fast_hydration_wiring.py` (the file E30 also touches, E31-appended at
the cast-once bind proof point).

---

## 0. Evidence separation (this report obeys it)

| Class | What it means | Used for |
|---|---|---|
| **SOURCE-PROVEN** | Verifiable from pinned comfy/runtime source at HEAD | call graph, cast mechanics, dtype flow |
| **LOCAL-MEASURED** | Measured on the dev box (CPU/CUDA mechanics only) | unit tests, classification taxonomy, timing-helper correctness |
| **E28-HISTORICAL** | Numbers quoted from E28 run artifacts (run_0.json) | variance comparison, cast-wall constants |
| **REMOTE-MEASURED** | Numbers from authorized v2ctl remote runs | **NOT YET AVAILABLE — nothing here claims it** |
| **INFERRED** | Reasoned from the above, not directly measured | hypothesis ranking, cast-once implication |
| **UNKNOWN** | Not determinable without a remote run | GPU ms of the 252 casts, end-to-end ON/OFF delta |

---

## 1. Git state

```text
git rev-parse HEAD        => 0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997
git branch --show-current => TESTING2
```

E31-owned files (modified/created by this batch):
- `comfymodal_runtime/clip_forward_forensics.py` (E31 new, extended)
- `comfymodal_runtime/clip_fp32_cast_once.py` (E31 modified)
- `comfymodal_runtime/clip_fast_hydration_wiring.py` (E31-marked additive block only)
- `tests/test_e31_clip_forward_fp32.py` (E31 new, extended)
- `config/v2/flag_registry.toml` (E31 flag metadata; E32 registry)
- `config/v2/profiles/e31-clip-fp32-qd4-arm-a.toml` (current E31 QD4 control arm)
- `config/v2/profiles/e31-clip-fp32-qd4-arm-b.toml` (current E31 QD4 experiment arm)
- `V2_BATCH_E31_CLIP_FORWARD_FP32.md` (this report)

Concurrent-ownership boundary: E29 owns `critical_path_ledger.py`,
`gantt_canonical.py`, `modal_app.py`, `runtime_bootstrap.py`,
`runtime_executor.py`, `model_preload.py` (their current diffs are E29/E30's
work, not E31's).  E30 owns `clip_qd_reader.py`, `bench_e30_clip_qd.py`,
`e30_env_probe.py`, `test_e30_clip_qd_io.py`.  E31 did NOT modify any of
those (the E30 seam in `speculative_clip_hydration.py` was already present).

---

## 2. Phase 0 reconciliation — CURRENT_E31 state (LOCAL-MEASURED)

```
CURRENT_E31_FILES:
  comfymodal_runtime/clip_forward_forensics.py   (E31 forensics module)
  comfymodal_runtime/clip_fp32_cast_once.py      (E28 cast-once + E31 extension)
  tests/test_e31_clip_forward_fp32.py            (29 tests)
  config/v2/profiles/e31-clip-fp32-qd4-arm-a.toml
  config/v2/profiles/e31-clip-fp32-qd4-arm-b.toml
  config/v2/flag_registry.toml                   (E31 flag metadata added)
  V2_BATCH_E31_CLIP_FORWARD_FP32.md              (this report)

FP32_ON_PATH  = COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=1  (deploy-baked + profile)
FP32_OFF_PATH = flag absent/0 (production default)

FORWARD_GPU_TIMING_IMPLEMENTED    = YES  (ForwardTimer, one post-forward sync)
PER_CAST_GPU_TIMING_IMPLEMENTED   = YES  (deferred event pairs, resolved after sync)
PERSISTENT_FP32_PROVEN_LOCALLY    = YES  (residency verifier + generation; local tests)
INVALIDATION_COMPLETE             = YES  (identity-keyed generation, fail-closed)
REMOTE_AB_PERFORMED               = NO   (not authorized; zero remote activity)
```

**Corrections applied to stale report statements:**
- The previous report's §3.1 run table was **wrong** (see §4): it mixed two
  different measurements and misattributed regions/values.  Rebuilt from the
  raw `run_0.json` artifacts.
- The previous report's "input is BF16" premise was **wrong** (see §3):
  Comfy's CLIP text encoder runs FP32.

---

## 3. Phase 1 — the actual Qwen forward/cast call graph (SOURCE-PROVEN)

### 3.1 Construction + hydration (bind-time, once)

| Step | Evidence |
|---|---|
| `sd.load_text_encoder_state_dicts` → `TEModel.QWEN3_4B` → `flux.klein_te` | `comfy/sd.py:1590-1596`, `comfy/text_encoders/flux.py:217-231` |
| `SDClipModel.__init__` picks `comfy.ops.manual_cast` (no custom_operations/quant) | `comfy/sd1_clip.py:109-117` |
| Runtime hydrates the BF16 checkpoint via `load_state_dict(assign=True)` | `clip_fast_hydration.py:1340-1362` → `comfy/sd1_clip.py:308-309`; torch `assign` does **no dtype conversion** (verified in installed torch source) |
| **Result: resident parameter dtype = BF16** (the checkpoint tensors become the parameters) | SOURCE-PROVEN |

### 3.2 Forward dtype flow (per encode)

```
CLIP.encode_from_tokens → SDClipModel.forward (comfy/sd1_clip.py:260-303)
  process_tokens: embedding(tokens, out_dtype=torch.float32)   # sd1_clip.py:213,250
    Embedding.forward_comfy_cast_weights: BF16 weight → out_dtype=None guard
      → cast_bias_weight(self, device=..., dtype=None, ...)     # NO dtype conversion
      → F.embedding(...).to(dtype=torch.float32)                # embeds = FP32
  transformer(..., embeds=embeds, dtype=torch.float32)          # sd1_clip.py:279
    per layer (36):
      input_layernorm  RMSNorm (plain nn.Module) → rms_norm → cast_to(weight, FP32)
      self_attn        q/k/v/o_proj ops.Linear (manual_cast, bias=False)
        → forward_comfy_cast_weights → cast_bias_weight(self, input, offloadable=True)
          dtype = input.dtype = FP32                            # comfy/ops.py:285-290
          weight.dtype (BF16) != FP32 → weight.to(dtype=torch.float32)   # REAL
      mlp              gate/up/down_proj ops.Linear → same REAL BF16→FP32 cast
      post_attention   RMSNorm (plain) → tiny cast_to
    final norm (plain RMSNorm) → tiny cast_to
  → outputs[0] FP32 activations
```

**Definitive dtype relationship (SOURCE-PROVEN):** Comfy's CLIP text encoder
computes in **FP32** (`out_dtype=torch.float32` embeds; `dtype=torch.float32`
into the transformer).  The resident weights are **BF16** (assign of the
BF16 checkpoint).  Therefore every `manual_cast` Linear performs a **REAL
BF16→FP32 conversion of its weight per forward** — `comfy/ops.py:375-376`
(`if weight_has_function or weight.dtype != dtype: weight = weight.to(...)`).

### 3.3 The "252 bias + 1 weight" oddity — RESOLVED (SOURCE-PROVEN)

- Qwen-3-4B in this path has **zero bias parameters** (`qkv_bias=False`,
  MLP `bias=False`).
- The E27 counter classified a call as "bias" when `args[1]` was non-None —
  for the 252 Linear calls `args[1]` is the **input activation**, not a bias
  (`comfy/ops.py:281-382`: `cast_bias_weight(s, input=None, ...)`).
- The real accounting: **253 weight casts/forward = 252 REAL BF16→FP32
  Linear weight conversions + 1 embedding call with `dtype=None` (no-op)**,
  plus ~73 tiny RMSNorm `cast_to` calls (not through `cast_bias_weight`).
- Exact byte reconciliation (matches the measured 15.31 GB exactly):

| Call | Elements | Result dtype | Dest bytes |
|---|---|---|---|
| 252 Linear weights | 3,633,315,840 | FP32 (4 B) | 14,533,263,360 |
| 1 embedding weight | 388,956,160 | BF16 (2 B) | 777,912,320 |
| **Total** | 4,022,272,000 | — | **15,311,175,680** |

- The FP32 dest dtypes measured by E28 were **the actual cast results**
  (BF16 resident → FP32 compute) — not a parsing artifact and not
  "FP32 resident casting down".

### 3.4 Cast-once implication (SOURCE-PROVEN + LOCAL-MEASURED)

| Configuration | Resident | Input | Per-forward cast_bias_weight |
|---|---|---|---|
| Cast-once OFF (production) | BF16 | FP32 | **252 REAL conversions** (14.53 GB dest) every forward |
| Cast-once ON | FP32 | FP32 | `weight.dtype == dtype` → **no `.to()` at all** (call-site host overhead only) |

**The E28 cast-once design is directionally correct and eliminates the real
conversions** (it does NOT make the tax worse, and it does NOT leave a
"still-real FP32→BF16" tax — the previous report's claim to the contrary was
wrong).  The one-time cost is the bind-time BF16→FP32 widening
(+8.04 GB VRAM resident, exact: 8,044,936,192 → 16,089,872,384 bytes),
repeated-forward cost is ~0 real conversions (LOCAL-MEASURED:
`test_second_forward_no_repeat_conversion`).

### 3.5 E28's "~8 ms saving, leave OFF" conclusion — status

The E28 conclusion is **not proven** (its `cuda_event_wall_ms = 0.0` was a
back-to-back no-sync event pair, and its own cast-wall data — 707-731 ms OFF
vs 2.2 ms ON — contradicts the "~8 ms" framing).  E31's corrected
measurement (deferred event pairs + one sync) will produce the actual GPU
conversion time.  **No unsupported FP32 conclusion remains in this report.**

---

## 4. Phase 2 — raw E28 run comparison (E28-HISTORICAL, corrected)

### 4.1 The "2.03 s clean run" is a measurement artifact

The E31-previous report's §3.1 table was **wrong on every contested row**.
Rebuilt from the raw `run_0.json` artifacts (all runs: RTX PRO 6000,
restore_count=1, request_count=1, output SHA `20b10e1f...e5260`):

| Run dir | Cloud/region | CPU/Mem | counter ms | trace diff ms | cast wall (253) | UNET prefetch overlap | health |
|---|---|---|---|---|---|---|---|
| 00-32-58 | GCP us-west1 | 12C/32G | 3720.9 | 3723.1 | 707.1 | none (never_started) | SEVERELY_CONTENDED |
| **00-50-03** | GCP us-east4 | 16C/48G | **2029.2** | 2031.3 | 783.8 | none | **CLEAN** (broken baseline) |
| 00-54-04 | GCP us-east4 | 16C/48G | 1871.3 | 1873.6 | 731.8 | none | CLEAN |
| 01-40-33 | AWS us-east-2 | 16C/48G | 5512.8 | 5531.3 | 8.2 | 12.31 GB frac 1.0, 5050.9 ms | SEVERELY_CONTENDED |
| 01-41-16 | GCP us-east4 | 16C/48G | 3482.3 | 3605.1 | 6.4 | 12.31 GB frac 1.0, 2985.7 ms | DEGRADED |
| 01-43-36 | AWS us-east-2 | 16C/48G | 5274.8 | 5281.6 | 7.9 | 12.31 GB frac 1.0, 4848.7 ms | SEVERELY_CONTENDED |
| 01-54-59 | GCP us-east4 | 16C/48G | 2857.2 | 2866.5 | n/a | 12.31 GB frac 1.0, 3423.8 ms | DEGRADED |
| 02-04-23 (cast-once ON) | GCP us-east4 | 16C/48G | 3416.8 | 3423.8 | 2.2 | 12.31 GB frac 1.0, 3646.8 ms | DEGRADED |
| 02-17-52 | GCP us-south1 | 12C/28G | 4473.5 | 4481.4 | 7.0 | 12.31 GB frac 1.0, 3490.6 ms | SEVERELY_CONTENDED |
| 02-20-56 | GCP us-west1 | 12C/28G | 5589.9 | 5827.5 | 6.4 | 12.31 GB frac 1.0, **5088.9 ms** | SEVERELY_CONTENDED (process_cpu 25.97 s) |

Key corrections vs the previous report:
1. **00-50-03 is the E28 "broken baseline"** — the cast-once AttributeError
   forced CLIP into `native_cpu_h2d` (INVALID/PARTIAL cpu=398 cuda=0); the
   GPU forward never ran.  Its 2029 ms is the **cast-counter value over the
   prefill cast region** (the E27 counter with the wrong signature), NOT a
   whole-forward span.
2. The sub-2.4 s "clean" numbers (00-50-03, 00-54-04, 00-55-28) are all
   pre-fix runs where the counter measured the cast region — **there is no
   valid whole-forward measurement in any pre-fix run**.
3. Region is NOT the separator: us-east4 produced both 1871 ms (broken
   counter) and 3605 ms (trace diff).  The separator is the **UNET 12.31 GB
   prewarm overlap** state (never_started vs completed/full).
4. The cast wall (~707-784 ms in the counter-measured runs) is present in
   BOTH "classes" — it cannot explain the 2.0 vs 3.4+ gap.

### 4.2 Ranked variance hypotheses, each with a falsification test

| # | Hypothesis | Evidence | Falsification test (future remote A/B) |
|---|---|---|---|
| H1 | **Concurrent 4-thread UNET prewarm (12.31 GB FUSE read) overlapping the forward** | Every ≥3.4 s run has prefetch wall 2898-5089 ms fully overlapping forward; the 5.5 s runs are exactly the full-12.31 GB reads | Same deployment, alternating `COMFYMODAL_V2_CHECKPOINT_PREWARM=0` vs =1 on the SAME region/host; H1 confirmed iff the OFF-arm forward falls to ~1.9-2.4 s and the 3.4-5.6 s cluster disappears |
| H2 | **Host CPU/IO contention (co-tenant noise)** | 02-20-56 process_cpu 25.97 s over 5.79 s wall; 01-43-36 19.8 s over 5.48 s | One pinned region, inject a 2-thread busy-loop co-tenant vs idle, prefetch disabled; confirmed iff forward tracks the injected load |
| H3 | **Region/host placement** | us-east4 spans 1871→3605; us-south1 4473; us-west1 5589; us-central1 8095 | Repeat the H1 A/B on us-east4 AND us-west1; if they converge with prefetch OFF + idle host, region is not first-order |
| H4 | **Per-forward 253-cast tax (~0.7 s host)** | cast wall 707-784 ms in ALL counter-measured runs (clean AND contended) | E31 corrected counter + ForwardTimer on one host, OFF/ON alternating; tax real iff forward drops ~0.7 s — it cannot explain the 2.0 vs 3.4+ gap either way |
| H5 | **Instrumentation overhead** | the wrapper's own wall is ~35% of the "2.03 s forward" | `COMFYMODAL_V2_E27_FORENSICS=1` vs =0, 5 runs |
| H6 | **Graph/duplicate encode** | all runs single encode, no cache-hit | warm-conditioning-cache second run should show ~0 ms encode |

**Ranking: H1 ≈ H2 > H3 > H4 > H5 > H6.**

---

## 5. Phase 3/4 — corrected GPU timing (implemented, LOCAL-MEASURED)

`comfymodal_runtime/clip_forward_forensics.py`:

- **ForwardTimer** — start/end events recorded on
  `torch.cuda.current_stream()`; ONE synchronize after the forward; then
  `elapsed_time`.  Reports `host_wall_ms`, `gpu_elapsed_ms`,
  `host_only_residual_ms`, `event_overhead_ms`; CUDA-absent → `None` (never
  a fabricated 0.0).
- **Per-cast timing is now DEFERRED** (the E28 bug class fixed): the wrapper
  records start/end event pairs per call WITHOUT reading `elapsed_time` at
  call time and WITHOUT per-call sync; the pairs are queued
  (`_cast_pending_events`) and resolved once after the forward sync by
  `resolve_pending_cast_events()` (called from `ForwardTimer.end()`).
  Pairs recorded on a stream that is not current at resolution are dropped
  (never fabricated).
- **Classification** per call: REAL_CONVERSION / REAL_COPY_NO_DTYPE_CHANGE /
  VIEW_ALIAS / NOOP_SAME_TENSOR / NOOP_SAME_STORAGE / OTHER — with
  source/result dtype, device, data_ptr, storage ptr, numel, bytes, and a
  module-path label (`module_paths` aggregate).  Bounded per-call ring
  (`COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT`, default 1024).
- **Tuple handling fixed**: `cast_bias_weight` with `offloadable=True`
  returns `(weight, bias, offload_stream)` — the third element is never
  recorded as a bias; a bias record is only produced when the module
  actually HAS a bias (the Qwen path has none → 253 weight records, 0 bias
  records, which is the true accounting).
- **Exception safety**: the wrapper never returns from `finally` (would
  swallow the propagating exception); recording is guarded by success.

## 6. Phase 5 — true FP32 cast-once (implemented, LOCAL-MEASURED)

- `apply_cast_once` (E28, retained): BF16 checkpoint → one-time exact
  widening → FP32 CUDA storage → zero-copy `assign=True` bind.  The
  parameter storage IS the FP32 tensor (ownership model A — no second
  representation to go stale).  Non-BF16 tensors (e.g. tokenizer blobs) pass
  through.  `bytes_out` measured from the actual cast tensor.
- **Demand-time proof wired at the bind site** (new, `clip_fast_hydration_wiring.py`
  E31 block): when the flag is on, after `hydrate_clip_bind` succeeds,
  `verify_resident_fp32(clip)` proves every file-covered leaf parameter is
  FP32 + CUDA + storage-stable, then `mark_cast_once_applied(clip)` bumps
  the generation.  Failure emits `clip_fh_cast_once_residency_failed` (a
  visible event, never a silent claim) — fail-closed.
- **Generation is identity-keyed** (new): object id + cond_stage_model id +
  patcher current_object id.  Rehydration/replacement produces a new key →
  generation 0 → no stale claim.  `invalidate_cast_once` removes the claim.
- Repeated forward: LOCAL-MEASURED zero real conversions
  (`test_second_forward_no_repeat_conversion`).
- Subset question (do all 398 tensors need FP32?): SOURCE-PROVEN — the
  compute-relevant set is the 398 BF16 tensors minus tokenizer blobs; the
  embedding weight also benefits (its `to(dtype=float32)` on embeds is
  output-side, not weight-side, but the resident FP32 embedding is consumed
  directly).  The verifier measures the ACTUAL resident distribution per
  model; nothing is hardcoded.

## 7. Phase 6 — invalidation (fail-closed, LOCAL-MEASURED)

- New checkpoint identity / rehydration / new model object → new identity
  key → generation 0.
- Patch application / weight mutation / device move → parameters rewritten
  in place; the FP32 storage is the storage, so a subsequent forward either
  consumes the mutated FP32 values or the regular cast path handles it; the
  demand-time verifier re-runs before any cast-once claim.
- Partial cast failure → `apply_cast_once` returns the input unchanged with
  `applied=False` + `reason` + `partial_tensor_count`/`partial_bytes_out`;
  the bind then proceeds with BF16 (normal path) — never a half-FP32 model.
- Tests: `test_invalidation_generation`, `test_generation_keyed_on_identity_not_object_id`,
  `test_invalidate_removes_claim`, `test_verify_resident_fp32_fails_closed_on_bf16`.

## 8. Phase 7 — forward variance forensics (implemented, default OFF)

- `ForwardProfiler` — one-shot `torch.profiler` pass (CPU+CUDA when
  available), JSON-safe op table (top-40 by time, cpu/cuda self totals).
  Gated by `COMFYMODAL_V2_E31_FORWARD_PROFILE` (default 0).  Never enabled
  in production; no import-time CUDA work with the gate off (tested).
- The primary zero-overhead path remains ForwardTimer + per-cast deferred
  event pairs.

## 9. Phase 8 — E29 ledger integration (implemented)

E31 events are emitted on the E29 canonical ledger axis
(`critical_path_ledger.record_event`) ONLY when the E31 forensics gate is
ON, via `emit_ledger_event` (allow-listed names, unknown names dropped):

```
clip_forward_start / clip_forward_end
clip_gpu_event_start / clip_gpu_event_end
clip_forward_gpu_ms
clip_cast_once_start / clip_cast_once_end / clip_cast_once_gpu_ms   (RESERVED — emitted by the cast-once bind path in the remote A/B arm; the local bind proof emits clip_fh_cast_once_applied / clip_fh_cast_once_residency_failed trace events today)
clip_forward_cast_summary
clip_profiler_start / clip_profiler_end
```

`ForwardTimer.start()/end()` emit the forward pair + gpu_ms;
`emit_cast_summary_ledger()` pushes the aggregate classification counts
(per-call evidence stays in the bounded ring, never on the ledger).  No
competing request timeline: these ride the existing request-scoped ledger
store (`begin_request` resets it per request).  Tested with the ledger
cleared: gate-on → events present; gate-off → absent; unknown name → absent.

## 10. Phase 9 — flags / v2ctl (registered)

Registered in `config/v2/flag_registry.toml` (E32's registry; verified via
`python tools/v2ctl.py flags explain COMFYMODAL_V2_E31_FORENSICS`):

| Flag | Type | Default | consumed_at | change_requires |
|---|---|---|---|---|
| `COMFYMODAL_V2_CLIP_FP32_CAST_ONCE` | bool | 0 | module_import | deploy |
| `COMFYMODAL_V2_E31_FORENSICS` | bool | 0 | module_import | deploy |
| `COMFYMODAL_V2_E31_FORWARD_PROFILE` | bool | 0 | module_import | deploy |
| `COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT` | int | 1024 | module_import | deploy |

The deleted/legacy `config/v2/profiles/e31-clip-fp32.toml` name is historical
report nomenclature and is not selectable. Current selectable E31 arms are
`e31-clip-fp32-qd4-arm-a.toml` / `e31-clip-fp32-qd4-arm-b.toml` and the
corresponding `e31-clip-fp32-fastsafe-arm-a.toml` /
`e31-clip-fp32-fastsafe-arm-b.toml`. No forwarding whitelist edits were made.
The E31 forensics/profile flags are NOT in any request-env passthrough list
(they are deploy-baked via v2ctl env), which matches their
`consumed_at=module_import` lifecycle.

## 11. Phase 10 — local validation (LOCAL-MEASURED)

```
python -m pytest tests/test_e31_clip_forward_fp32.py -q   => 29 passed
python -m pytest tests/test_e28_critical_path.py -q       => 16 passed
python -m pytest tests/test_e27_forensics.py -q           => 4 passed
python -m pytest tests/test_v2ctl_*.py (validation/registry/profiles) => pass
python -m pytest tests/test_e28_critical_path.py tests/test_e31_clip_forward_fp32.py -q => 45 passed
python -m py_compile comfymodal_runtime/clip_forward_forensics.py \
                     comfymodal_runtime/clip_fp32_cast_once.py \
                     comfymodal_runtime/clip_fast_hydration_wiring.py  => COMPILE_OK
git diff --check                                               => DIFF_CHECK_OK
```

Test coverage (29 tests): default-OFF no-CUDA import; install no-op;
classification taxonomy; corrected wrapper arg parsing (real source dtype);
deferred per-cast timing (pairs queued, not read pre-sync; resolved
post-sync; drained without fabrication); offloadable 3-tuple not counted as
bias; module-prefix facts; ForwardTimer wall/gpu semantics (None when CUDA
absent); cast-once gated no-op + exact widening + byte accounting; fail-
closed residency; identity-keyed generation; second-forward zero real
conversions; profiler gate; ledger event emission (on/off/unknown-name).

**Local GPU caution (explicit):** local timings are mechanics-only.  They
prove the measurement protocol and the classification are correct; they do
NOT predict Modal speed.  The remote A/B decides ON/OFF.

## 12. Remote A/B protocol (PREPARED, NOT EXECUTED — v2ctl only)

When the user authorizes remote work:
1. **Deploy** via `python tools/v2ctl.py ...` (the only supported
   interface; no BAT wrappers, no PowerShell env chains, no improvised
   Modal SDK, no whitelist edits).
2. **Structural cold gate**: one genuinely fresh container per arm (Fresh:
   yes, restore_count=1, same container_session_id/restored_instance_id as
   a prior run → WARM → invalid, repeat) with the exact workload and output
   SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`.
3. **Arms** (same deployment/resource shape, alternating OFF/ON/OFF/ON):
   - Arm A: `COMFYMODAL_V2_E31_FORENSICS=1`, `COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=0`
   - Arm B: `COMFYMODAL_V2_E31_FORENSICS=1`, `COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=1`
   - Arm C (variance control, H1 falsification): prewarm OFF vs ON on the
     same region.
4. **Measure per run**: FP32 applied + generation; resident dtype
   distribution/bytes; cast classification totals (real conversions vs
   no-ops); real conversion bytes; per-cast GPU ms (deferred event pairs);
   whole-forward GPU ms + host wall + host-only residual; thread/process
   CPU; UNET prefetch overlap; provider/region; resource shape; exact SHA;
   fresh/warm identity.
5. **Decision rule**:
   - **ON** only if: output SHA exact; real conversions eliminated
     (REAL_CONVERSION count ≈ 0 on arm B); measurable repeatable whole-
     forward win (same region, prefetch state controlled); VRAM
     (+8.04 GB for Qwen-3-4B) acceptable; no downstream regression.
   - **OFF** only if: ON truly removes real conversion work AND synchronized
     GPU evidence shows little/no useful end-to-end benefit (or regression)
     — never "probably ~8 ms".

## 13. Status / verdict

```
E31_CLIP_FORWARD_FP32 = READY_FOR_V2CTL_REMOTE_AB
REMOTE_DECISION       = NOT_YET_PROVEN
REMOTE_DEPLOYS        = 0
REMOTE_REQUESTS       = 0
REMOTE_SNAPSHOTS      = 0

SOURCE-PROVEN:  Qwen CLIP runs FP32 compute on BF16-resident weights;
                252 REAL BF16→FP32 weight conversions/forward (14.53 GB);
                cast-once ON makes those conversions disappear
                (weight.dtype == input.dtype → no .to()); E28 "~8 ms"
                conclusion unproven (invalid cuda_event_wall_ms=0.0).
LOCAL-MEASURED: measurement protocol correct (deferred events, one sync);
                classification + second-forward no-repeat + invalidation
                proven; 29 E31 tests pass.
E28-HISTORICAL: "2.03 s clean forward" was the broken baseline (never ran
                a GPU forward); cast wall ~707-784 ms constant; UNET
                prewarm overlap + host CPU contention are the ranked
                variance causes (H1/H2), each with a falsification A/B.
REMOTE-MEASURED: none.
INFERRED:       cast-once eliminates ~14.5 GB/forward of real conversions;
                the end-to-end win depends on GPU conversion time +
                host/overlap state (unmeasured).
UNKNOWN:        actual GPU ms of the 252 conversions; end-to-end ON/OFF
                delta on a fresh container; VRAM pressure interplay.
```

STOP — awaiting user permission before ANY remote work.
