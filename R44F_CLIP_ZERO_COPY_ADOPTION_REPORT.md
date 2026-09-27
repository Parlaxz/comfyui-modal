# R44F — Native CLIP Zero-Copy (Same-Storage) Adoption Attempt: GATE INVALID / CLIP PROOF FAILED

Batch: R44F · Owner: R44F (single deployment owner) · Worktree `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af` (no commits/push/merge/reset)
Profile `r44-request-fastsafe` (controls frozen) · Exactly ONE deployment (`59444807…`) · Exactly ONE paid cold request · **GATE INVALID** · STOPPED after the gate.
Gate: `.v2ctl/gates/gate_20260824-050525_ff132f65.json` **gate_valid = false**, reasons `[structural] runtime_status_not_nominal:DEGRADED`, `[structural] loader_unobserved_clip`, `[structural] loader_observed_mismatch_clip` · request `v2-benchmark-0-cb40e0c40c4c` · SHA exact ✓ · provenance validated · backend exit 0.

Companion raw log: `R44F_CLIP_ZERO_COPY_ADOPTION_RAW_LOG.txt` (key payloads verbatim, labeled with source file and line ranges).

> **VERDICT UP FRONT: this R44F gate is INVALID and the requested CLIP zero-copy proof FAILED.**
> Native CLIP same-storage adoption was **never exercised**: the CLIP FastSafe arm skipped itself at
> eligibility time (`clip_fastsafe_skip`, reason `native_adoption_ineligible`,
> detail `dtype_parity_mismatch:file_0:BF16`). Do NOT cite this batch as CLIP zero-copy success.

---

## A. Objective

Adopt native CLIP weights via the FastSafe same-storage path (the pattern already proven on UNET),
so that `load_models_gpu(role=CLIP)` becomes bookkeeping instead of a second full model-sized
device materialization (~8 GB allocated delta measured in R44E), while preserving native Comfy
CLIP semantics end-to-end. Success criterion for this batch: a VALID cold gate with
`bind_mode = same_storage` observed on the CLIP arm, `copied_count = 0`, and RuntimeStatus NOMINAL.

## B. Repo / worktree state

```text
worktree : ../comfyui-modal-r42
branch   : r42-golden-reconciliation
HEAD     : 0c59f46e3238f421378e8852ebc548da815b70af
dirty    : pre-existing dirty changes preserved byte-for-byte; no commits, no resets,
           no code changes after the cold gate
```

## C. Deployment and run identity

| Field | Value |
|---|---|
| deploy_fingerprint | `5944480788bd446939160bd2f22bd9751462eea96196bc0cdb97069c2d755c82` |
| profile | `r44-request-fastsafe` |
| run_fingerprint | `ff132f65299ec78d673d2c0bcb6cc159f5cf44efa43fccef5ec127e541ed89f5` |
| request_id | `v2-benchmark-0-cb40e0c40c4c` |
| expected_output_sha | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` |
| output_sha (observed) | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` — EXACT MATCH |
| backend_exit_code | 0 |
| provenance_validation_status | `validated` |

The generation itself was byte-exact against the golden SHA — the failure is structural
telemetry/eligibility, not output correctness.

## D. Gate result — INVALID

Gate artifact: `.v2ctl/gates/gate_20260824-050525_ff132f65.json`

```text
gate_valid = false
reasons:
  [structural] runtime_status_not_nominal:DEGRADED
  [structural] loader_unobserved_clip
  [structural] loader_observed_mismatch_clip
```

Exactly ONE cold R44F gate was run. It is INVALID for the requested CLIP proof. No second paid
request was made.

## E. Root cause — CLIP native adoption never exercised (measured, not inferred)

run_0.json trace event `clip_fastsafe_skip` (lines 5257–5289):

```text
reason : native_adoption_ineligible
detail : dtype_parity_mismatch:file_0:BF16
gates:
  device_arg       = default
  expected_te_dtype = torch.float16
  te_device        = cuda:0
  file_0_dtypes    = [BF16]
```

Interpretation (strictly what the evidence shows): the CLIP FastSafe eligibility gate requires
dtype parity between the expected text-encoder dtype (`torch.float16`) and the on-disk file dtypes;
the checkpoint file is `BF16`, so the arm declared itself ineligible and skipped BEFORE any
adoption attempt. Consequently:

- **CLIP native adoption was NOT exercised.** There is no CLIP `bind_mode`, no sampled storage
  counts, no CLIP four-point CUDA closure for this run — none exist because the arm skipped.
- `loader_selection.clip`: requested == effective == `fastsafetensors_direct_gpu`, but
  **observed = "" (empty)** (run_0.json lines 10366–10374).
- `gpu_loading_observed = ["not_observed"]` (run_0.json lines 7358–7360).
- `runtime_status = {"status": "DEGRADED", "reasons": ["loader_unobserved_clip"]}`
  (run_0.json lines 10392–10397).

This is why the gate fails structurally even though the output SHA matched.

## F. Consequence — CLIP ran the CPU-owner path again (no zero-copy)

With the FastSafe arm skipped, CLIP fell back to the native path and repeated the R44E-measured
second-materialization behavior. From run_0.json `cpu_owner_records` (lines 848–860):

```text
load_models_gpu role=CLIP      wall 2299.661 ms
  cuda_allocated_delta_bytes   = 8,101,709,312   (~8.10 GB — model-sized device materialization)
  cuda_reserved_delta_bytes    = 8,103,395,328
```

From run_0.json stage deltas (lines 7454–7458):

```text
clip_forward               = 2451.3 ms
clip_raw_encode            = 4763.4 ms
clip_scheduled_conditioning= 4776.85 ms
```

**No zero-copy claim is made for CLIP from this batch.** These numbers describe the fallback
native path, not the adoption under test.

## G. Successful CONTROL evidence in the same request (does NOT rescue the CLIP gate)

The UNET arm ran its full pipeline successfully in the same request (run_0.json lines 6152–6190):

```text
unet_fastsafe_pipeline:
  status                              = ok
  bind_mode                           = same_storage
  storage_identity_matched / total    = 453 / 453
  copied_count                        = 0
  final_validation_all_params_on_target = true
  owner_retained                      = true
  adopt_ms                            = 123.22
  file_to_gpu_wall_ms                 = 629.2175
```

Combined with the exact output SHA match, this confirms the harness, deployment, ledger, and the
UNET same-storage mechanism all worked in this very request. **However, this control evidence does
NOT rescue the CLIP gate**: the gate reasons are CLIP-specific (`loader_unobserved_clip`,
`loader_observed_mismatch_clip`, `runtime_status_not_nominal:DEGRADED`) and remain unresolved.
The batch verdict stays INVALID/FAILED for the requested CLIP proof.

## H. Cold gate / runtime context (healthy except structural telemetry)

```text
GPU              : rtx-pro-6000
CPU              : 12          (BASELINE_CPU 12 == deployed 12)
memory           : 32768 MB    (BASELINE_MEMORY 32768 == deployed 32768)
runtime shape    : f504e296c398bdcb2c4c07e2  (RUNTIME_FINGERPRINT match)
RUN_COUNT        : 1           (exactly one run)
backend          : requested in_process == selected in_process, selection_reason runner_available,
                   fallback_attempted false (run_0.json lines 7397–7405)
endpoint/backend : ok
canonical ledger : status ok, zero_gap true (gate telemetry lines 265–268; run_0.json line 10358)
provenance       : validated
```

Everything environmental was nominal; the only failures are the three structural gate reasons
traced to the CLIP dtype eligibility skip.

## I. Explicit stop rule and next action

- **STOP RULE HONORED:** no second paid request, no redeploy, no code change after the cold gate.
  All work stopped immediately when `gate_valid = false` was observed.
- **Next action:** investigate and resolve the CLIP dtype eligibility mismatch
  (`dtype_parity_mismatch:file_0:BF16` vs `expected_te_dtype torch.float16`) BEFORE any future
  paid proof attempt. This report deliberately does NOT prescribe an unverified fix — the correct
  resolution (adjusting the eligibility predicate vs. handling BF16 checkpoints natively vs.
  selecting a different checkpoint) must be established from source analysis first
  (see `comfymodal_runtime/request_clip_fastsafe.py` eligibility gate around line 559 and the skip
  emission around line 1100; existing coverage in `tests/test_r44f_clip_zero_copy.py`).

## J. Artifact paths

| Artifact | Path (relative to `../comfyui-modal-r42` unless absolute) |
|---|---|
| Gate result | `.v2ctl/gates/gate_20260824-050525_ff132f65.json` |
| Run record | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_05-04-36\run_0.json` |
| Selected run sample | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_05-04-36\run_001_sample.json` |
| Summary | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_05-04-36\summary.json` |
| Campaign manifest | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_05-04-36\campaign_manifest.json` |
| Deploy manifest | `.v2ctl/deployments/deploy_20260824-000339_59444807.json` |
| CLIP FastSafe source (eligibility gate / skip emission) | `comfymodal_runtime/request_clip_fastsafe.py` (~line 559 dtype parity check; ~line 1100 `native_adoption_ineligible` skip) |
| UNET FastSafe control source | `comfymodal_runtime/request_unet_fastsafe.py` |
| Existing R44F tests | `tests/test_r44f_clip_zero_copy.py` (incl. `test_gates_reject_dtype_parity_mismatch`, line 564) |

## K. Final verdict fields

```text
R44F_ONE_COLD_GATE_RUN                    = YES
R44F_GATE_VALID                           = NO
R44F_CLIP_ZERO_COPY_PROOF                 = FAILED (INVALID gate)
R44F_CLIP_NATIVE_ADOPTION_EXERCISED       = NO  (skipped: native_adoption_ineligible /
                                                 dtype_parity_mismatch:file_0:BF16)
R44F_CLIP_LOADER_OBSERVED                 = ""  (empty → loader_unobserved_clip)
R44F_RUNTIME_STATUS                       = DEGRADED
R44F_OUTPUT_SHA_EXACT                     = YES (20b10e1f…90e5260)
R44F_PROVENANCE                           = validated
R44F_UNET_CONTROL_SAME_STORAGE            = YES (453/453, copied 0 — control only, does not
                                                 rescue the CLIP gate)
R44F_SECOND_PAID_REQUEST                  = NO
R44F_POST_GATE_CODE_CHANGE                = NO
R44F_NEXT_ACTION                          = resolve CLIP dtype eligibility mismatch before any
                                            future proof (investigation first; no prescribed fix)
```

— R44F, stopped after the single INVALID cold gate. No tuning performed; controls remain frozen.
