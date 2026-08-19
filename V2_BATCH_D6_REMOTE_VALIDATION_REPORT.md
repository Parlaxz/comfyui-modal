# V2 Batch D6 — Remote Validation Report (Semantic-Neutral Cache Nonce + One Cold Run)

- **Date:** 2026-08-16
- **Branch:** current main only · no branch · no worktree · **commit: none**
- **C4:** untouched (not executed)
- **Deploys: 1 · Modal requests: 1 (the single authorized true-cold request)**
- **Run id:** `v2-benchmark-0-090d16887f52` (artifacts dir
  `comfymodal-data/benchmarks/runs/v2_2026-08-16_01-04-16`)
- **Nonce:** `e036379d-d597-4928-8961-d13e6d7be753` (fresh UUID, semantic-neutral)

---

## 0. Executive verdict

> **run validity = INVALID** for the D6 fast-path validation objectives.

The single authorized request executed cleanly (exit 0), produced a
**byte-for-byte EXACT output match** with the canonical reference SHA, and
validated the D1 zero-gap dispatch, the semantic-neutral cache nonce, and
the true-cold restore platform. **However, the D6 fast-path flags
(`CLIP_FAST_HYDRATION`, `CLIP_SNAPSHOT_EXCLUDE_WEIGHTS`,
`CLIP_COLD_FORENSICS`, `UNET_FASTSAFETENSORS`) were NOT baked into the
deployed container**, so the run exercised the NATIVE baseline paths
(native CLIP CPU→GPU with a 12.4 GB CUDA delta; native UNET synchronized
H2D at 3.1 GB/s). The CLIP fast hydration / snapshot exclusion / UNET
fastsafetensors / cold-forensics gates are therefore INVALID (not
exercised), not FAILED-by-behavior.

Per the hard-gate rule: **one more run is NOT automatically purchased.**
The exact corrected procedure is documented in §10.

---

## 1. What this run DID validate (PASS)

| Gate | Result | Evidence |
|---|---|---|
| Fresh | **YES** | `Fresh: YES`; restored_instance_id `5f09d1d6…`; restore_count=1 |
| restore_count / request_count | **1 / 1** | identity: `restore_count: 1, request_count: 1` |
| Stored snapshot order expected | **YES** | `stored_snapshot_model_order: "O0"`, `construction_order_semantics: model_construction_order_only` |
| B1 exact generation match | **YES** | output SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` == canonical reference (see §7) |
| Registry proof store HIT | **YES** | `[v2.harness] node_registry_preload_skipped store_generation_entry=yes`; `registry_load=skipped store_hit=yes`; `[v2.plan_proof] memo=hit` |
| Full node registry NOT imported after user trigger | **YES** | `registry_load_ms=0.0`, `registry_store_hit=True`; `node_registry_preload_ms=0.0` |
| Conditioning cache decision = MISS (nonce) | **YES** | `clip_conditioning_cache_lookup`: hit_count=0, miss_count=1; `clip_conditioning_cache_decision`: `decision=miss_stored`, `key_hash=248952081d4cff0a…`, `encode_calls=1` |
| encode_calls == 1 | **YES** | `encode_calls: 1`, `encode_loop_wall_ms: 6272.152` |
| Intrusive UNET forensics OFF | **YES** (default) | `COMFYMODAL_V2_UNET_FORENSICS` default OFF; no deep-profile keys |
| Final result present | **YES** | `[v2.png_output] width=1088 height=1920 bytes=3129718 sha=20b10e1f…` |
| Semantic neutrality of the nonce | **PROVEN** | byte-identical output with a fresh nonce vs the canonical reference (see §7) |

---

## 2. What this run did NOT exercise (INVALID — flags not baked)

| Gate | Expected | Observed |
|---|---|---|
| CLIP fast hydration status = success | fastsafetensors direct-GPU hydration | **NOT OBSERVED** — zero `clip_fh_*` events in the remote trace; native CLIP path ran (`clip_forward_end duration_ms=6121.092`, `cuda_allocated_delta_bytes=12,448,251,392` = 12.4 GB native CPU→GPU) |
| CLIP fallback_count = 0 | — | **N/A** (feature off) |
| no native duplicate CLIP CPU→GPU transfer | — | **FAILED** (native 12.4 GB transfer happened; nothing to compare against) |
| CLIP zero-copy bind proof | — | **N/A** (feature off) |
| no physical full-size CPU CLIP payload restored | — | **N/A** (snapshot exclusion off) |
| UNET fastsafetensors status = success | fastsafe pipeline | **NOT OBSERVED** — zero `unet_fastsafetensors_pipeline` / `meta_worker` events; waterfall shows NATIVE path: `Checkpoint read 3.814s`, `UNET get_model 532.999ms`, `Bind 364.330ms`, `Synchronized H2D (3.1 GB/s) 3.968s` |
| UNET fallback_count = 0 | — | **N/A** (feature off) |
| native UNET mmap/H2D replay absent | — | **FAILED** (synchronized H2D 3.968 s at 3.1 GB/s present) |
| D4 pipeline accounting disjoint | — | **N/A** (no fastsafe pipeline ran) |
| clip_cold forensics events | — | **N/A** — `core_wrapper_install` event reports `clip_cold_forensics.status=disabled` in the container |

**Root cause (operator-side, not a code defect):** the deploy ran from a
shell in which the D6 env vars were NOT defined (they were set in a
different shell session), so `deploy_and_run_v2_single.bat`'s
`if not defined … set …=0` pins defaulted all fast-path flags to 0 and
`_runtime_env()` baked 0s into the container. The image itself is correct
(`fastsafetensors==0.3.3` confirmed installed during the image build —
deploy log: "Successfully installed fastsafetensors-0.3.3"). The flag
transport mechanism (F2 `_runtime_env` passthrough + launcher pins) is
verified locally by tests; it simply was not exercised because the flags
were absent from the deploy process environment.

---

## 3. D1 analysis (PASS)

| Metric | Value |
|---|---|
| process_start_to_response_ms | **38578.309** |
| user_equivalent_trigger_to_response_ms | **38823.336** |
| user_equivalent_trigger_to_modal_submission_ms | **724.107** |
| command_to_enqueue_ms | 0.556 (trigger→local_receive) + 73.0 (→generator create) |
| placement / scheduling | Scheduling time = **4229 ms** (footer) |
| non_scheduling | Command (without scheduling) -> Response = **34.594 s** |
| registry_proof_prime | **prime_ok=true, store_entry_persisted=true** (verified pre-run; D1 hash-key defect found & fixed, §9) |
| registry_proof_store_hit | **YES** (`store_generation_entry=yes`, `store_hit=yes`) |
| full_registry_import_after_trigger | **NO** (`registry_load_ms=0.0`) |
| trigger_to_submission residual/status | `trigger_to_submission_ms=125.0` (plan_build 78.0 + handle_ready 0.0 + submission 47.0); residual ≈ 0; status complete |

Footer semantics (permanent, no TOTAL WALL):

```
COMMAND -> RESPONSE:                       38.823s
Command (without scheduling) -> Response:  34.594s
Scheduling time:                            4.229s
```

---

## 4. Generic CLIP analysis (native path — fast hydration NOT exercised)

### Snapshot
- snapshot physical CLIP weight bytes = **unavailable** (exclusion flag off; native snapshot holds full weights)
- snapshot exclusion status = **not applied** (flag not baked)
- manifest eligibility/status = **N/A** (no `clip_fh_capture` event; feature off)

### Hydration (native)
- hydration scheduled at / worker start / first encode demand = **N/A** (D3 off)
- file_to_gpu_wall_ms / checkpoint_bytes / effective GB/s / bind_wall_ms / zero_copy / owner mode = **N/A**
- RSS delta / CUDA allocated delta = **12,448,251,392 bytes** CUDA delta observed inside `clip_forward_end` (native CPU→GPU; no D3 zero-copy bind)
- fallback_count = **N/A** (feature off)

### D2 reconciliation (native)
- D2 normal H2D bytes = **≈ 12.4 GB** (CUDA delta inside clip_forward; native ModelPatcher transfer)
- D2 transfer_ops / resident_before = **unavailable** (clip_cold_forensics disabled in container)
- load_models_gpu wall = `load_models_gpu_duration duration_ms=64.827` (sampler call) + graph-model-loading call
- GPU-ready wait = `clip_gpu_prepare_end duration_ms=13.696`; graph-level CLIP wait exposed at the CLIPTextEncode node: **2604.452 ms** (pre_sampler_structured_report clip_text_encode_nodes)
- sync_count/sync_ms, CUDA event wall = **unavailable** (forensics off)

### Actual encoding (native)
| Metric | Value |
|---|---|
| tokenize_ms | **106.767** |
| encode_total_ms | **6139.035** (clip_raw_encode_end) |
| forward_ms | **6121.092** |
| post_forward_ms | ≈ 18 ms (encode − forward) |
| encode_calls | **1** |
| token_count/batch_count | unavailable (forensics off) |
| resident_at_last_encode | native (full model resident after first encode) |
| reload/multiple-move count | 1 load observed (single encode path) |

### Critical-path exposure (native)
- hydration total / hidden / exposed = **N/A** (no D3 hydration); the CLIP GPU-ready wait exposed on the graph critical path = **2604.452 ms** at `CLIPTextEncode` (node 67).

---

## 5. UNET / meta analysis (native path — fastsafetensors NOT exercised)

- pipeline_total_ms / accounting_children / residual / status = **N/A** (no fastsafe pipeline; no `[v2.fastsafe.reconcile]` line)
- worker A/B overlap / meta_* fields = **N/A** (no meta worker ran)
- Native UNET loader, from the waterfall (non-accounting detail rows):
  - Checkpoint read **3.814 s**
  - UNET get_model **532.999 ms**
  - Bind **364.330 ms**
  - Synchronized H2D **3.968 s @ 3.1 GB/s**
  - H2D end → UNET ready **3.035 ms**
- input_types_warm:
  - wall_ms = **1715.648** (input_types_warm_ms), classes = **31**
  - thread_cpu_ms / effective_cores / cpu_affinity_count / overlap_meta_ms / overlap_fastsafe_ms / overlap_scope = **unavailable** in the captured trace (the console line carried only wall+classes; no fastsafe workers existed to overlap with)
- Deep profiler: **OFF** (default; no meta_module_construct_* keys)

---

## 6. D5 analysis (native path)

- remote_setup reconciliation: `remote_setup_schedule` event present — `schedule_ms=1618.072`, `cc_prefetch_scheduled=1`, `input_types_warm_scheduled=1`, `seed_derived=1`; `method_entry_to_prompt_executor_ms=2369.884`; full top-level segment tiling computed host-side in the run artifact
- ImpactSwitch / large pre-sampler nodes (per-node walls from
  pre_sampler_structured_report): ImpactSwitch **35.775 ms** and **48.649 ms**;
  Any Switch (rgthree) 398.8 ms; `sampler_lane_wait_ms=0.105`
- Wait windows present in trace: `graph_wait_*` (CLIP / prefill / UNET lanes),
  `gpu_lane_wait_*`, `sampler_lane_wait_*` — available for offline D5
  reconciliation
- UNET loader_total / exposed / hidden = **N/A for the fastsafe schema**
  (native loader ran; the D5 exposed/hidden calculation was built for the
  fastsafetensors/early-activation event schema)
- Further-UNET-gain recommendation: **not assessable from this run** (native
  loader only; no fastsafe pipeline, no meta worker, no D4 accounting)

---

## 7. Correctness gate

```
canonical reference SHA = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
run output SHA          = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
OUTPUT_SHA_EXACT        = YES
```

The PNG output (`width=1088 height=1920 bytes=3129718`, `compress_level=1`)
matches the canonical reference **byte-for-byte** despite a fresh cache
nonce — this is direct proof that `--conditioning-cache-nonce` is
semantically neutral (no effect on prompt, seed, sampler, model inputs, or
output bytes).

---

## 8. Snapshot / platform observation (record only — no C4)

| Item | Value |
|---|---|
| provider | **GCP** (`CLOUD_PROVIDER_GCP`) |
| region | **us-south1** |
| host fingerprint | `56de22f2e6931b68b3357703c4e9adaae3875984143483576b1a74f574519673` |
| CPU identity | AMD Family 191 Model 2, visible=28 (waterfall header); torch intraop 12 / interop 14 |
| GPU | RTX PRO 6000 Blackwell · VRAM 97,250 MiB · CUDA 13.0 · CC 12.0 |
| image id | `im-yMCzzn1d2iCVfNml8Byxg7`; container task `ta-01M041J6HF1XY5QFZPVQ5KCKGR` |
| pre-Python interval | **13.224 s** (Modal pre-Python snapshot restoration) |
| Python restore | **5.739 s** (restore_total_ms=5678.451; snapshot_restore_ms=3332.68; folder_warm 2950.772) |
| restore_gpu_state | **1294.374 ms** (restore_gpu_state_ms; cuda_init 612.48) |
| restore bootstrap | backend_startup 20266.84 ms (container boot window) |
| restore residual | `restore_end_to_modal_method_entry_ms=47.21` (no C4 attribution) |
| maxRSS | 34.89 GiB |

---

## 9. Integration defect found & fixed during this batch (local, no redeploy)

**D1 prime gate initially failed after the deploy** (`store_entry_persisted:
false`) because `_registry_proof_store_covers` looked up the **source**
workflow hash (`14f815f1…`) while the store is keyed by the **dispatch**
(production-compiled) hash (`2e43d4c0…`) — a guaranteed miss whenever
production compile is enabled. Fixed locally:

- `canonical_execution.py`: new `resolve_dispatch_workflow_hash(...)` —
  single source of truth mirroring `build_execution_plan`'s compile step;
  `build_execution_plan` now uses it for `dispatch_hash` (plan semantics
  unchanged).
- `tools/benchmark_v2_direct.py`: all three `_registry_proof_store_covers`
  call sites pass `modal_options`/`production_options` so the coverage
  check uses the dispatch hash.
- New tests `tests/test_v2_d1_dispatch_hash.py` (8 tests) + existing D1
  suites: 72 OK.
- Live local prime re-run: `{"store_entry_persisted": true, "prime_ok":
  true}` → exit 0 (no Modal involved in the prime itself).

This fix is harness/plan-build-local; the deployed container is unaffected
by it.

---

## 10. Final classification & next paid run

```
D1_DISPATCH                    = PASS
CLIP_FAST_HYDRATION            = INVALID   (flag not baked; native path ran)
CLIP_SNAPSHOT_EXCLUSION        = INVALID   (flag not baked)
UNET_FASTSAFE                  = INVALID   (flag not baked; native H2D ran)
META_CAUSE                     = STILL OPAQUE (no meta worker; cannot assess)
INPUT_TYPES_WARM_CONTENTION    = INCONCLUSIVE (warm ran 1715.6 ms; no fastsafe
                                                workers to measure overlap)
UNET_EXPOSED_WAIT              = N/A (fastsafe schema not exercised; native
                                 loader ~8.68 s read+bind+H2D, hidden under
                                 pre-sampler/restore windows)
OUTPUT_PARITY                  = EXACT
NEXT_PAID_RUN                  = OTHER — ONE corrected redeploy + ONE run with
                                 the D6 flags baked into the DEPLOY process env
                                 (see below). Not executed.
```

**Exact corrected procedure (do NOT execute automatically):**

1. In ONE shell, set all eight flags then run the deploy so the launcher
   pins preserve them and `_runtime_env()` bakes them:
   ```
   set COMFYMODAL_V2_UNET_FASTSAFETENSORS=1
   set COMFYMODAL_V2_CLIP_FAST_HYDRATION=1
   set COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1
   set COMFYMODAL_V2_CLIP_COLD_FORENSICS=1
   set COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=1
   set COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=1
   set COMFYMODAL_V2_INPUT_TYPES_WARM=1
   set COMFYMODAL_V2_UNET_FORENSICS=0
   deploy_and_run_v2_single.bat
   ```
   Verify the deploy log shows the new identity AND (post-run) the remote
   trace contains `clip_fh_capture`, `unet_fastsafetensors_pipeline`, and
   `clip_cold_forensics.status=installed` — the definitive baked-flag proof.
2. Then ONE run with a FRESH nonce:
   ```
   set V2_BENCHMARK_RUNS=1
   python tools\benchmark_v2_direct.py --conditioning-cache-nonce <fresh-uuid>
   ```
   (no `--unique-prompt-suffix`, no QD sweep, no INPUT_TYPES_WARM=0, no C4).
3. Same gate table as §1/§2, same output-SHA gate
   (`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`).

---

## 11. Final status

```
run validity        = INVALID (fast-path objectives not exercised; flags not
                      baked into the deployed container). D1 + nonce + parity
                      gates all PASS; fast-path gates NOT OBSERVED.
run id              = v2-benchmark-0-090d16887f52 (v2_2026-08-16_01-04-16)
provider/region/host= GCP / us-south1 / RTX PRO 6000 Blackwell (im-yMCzzn…)
D1 result           = PASS (prime ok, store hit, registry skipped after
                      trigger, trigger→submission 125 ms)
command→response    = 38.823 s
non-scheduling      = 34.594 s
scheduling          = 4.229 s
CLIP hydration      = NOT EXERCISED (native forward 6121 ms, 12.4 GB CUDA
                      delta; fast hydration flag absent)
CLIP encode         = 1 call, 6139 ms total (tokenize 106.8, forward 6121);
                      exposed GPU-ready wait 2604 ms at CLIPTextEncode
CLIP critical path  = 2604.452 ms exposed (native GPU-ready wait)
snapshot exclusion  = NOT EXERCISED (flag absent)
UNET loader         = NATIVE (read 3814 ms + get_model 533 + bind 364 +
                      sync H2D 3968 ms @ 3.1 GB/s) — fastsafe absent
meta breakdown      = N/A (no meta worker)
input_types_warm    = ran 1715.6 ms / 31 classes; overlap N/A
D5 exposed/hidden   = native-path wait windows recorded; fastsafe schema N/A
output SHA          = 20b10e1f… (EXACT)
classification      = D1 PASS · CLIP_FAST_HYDRATION INVALID ·
                      CLIP_SNAPSHOT_EXCLUSION INVALID · UNET_FASTSAFE INVALID ·
                      META_CAUSE STILL OPAQUE ·
                      INPUT_TYPES_WARM_CONTENTION INCONCLUSIVE ·
                      UNET_EXPOSED_WAIT N/A · OUTPUT_PARITY EXACT
next paid run       = OTHER — one corrected deploy (flags baked) + one run
                      (fresh nonce). NOT executed.
commit              = none
deploy count        = 1
Modal request count = 1
```

Local changes made during this batch (no commit): `--conditioning-cache-nonce`
(CLI + cache-key + telemetry + tests), `resolve_dispatch_workflow_hash` D1
fix (+ tests). Full local matrix green before the remote steps.

---

# CORRECTED FAST-PATH RUN — appended section (2026-08-16)

> **run validity = INVALID** for the CLIP fast-hydration objective.
> UNET fastsafe + D4 + input_types_warm + output parity: **STRONG PASS**.
> D1 + nonce + snapshot-exclusion capture: **PASS**.
> CLIP fast-hydration success gate: **NOT MET** (no `clip_fh_hydration_*`
> events in the captured artifact; CLIP forward shows a native-scale CUDA
> allocation). Per the hard-gate rule: **STOP. No third request.**

- **Run id:** `v2-benchmark-0-06813ab11164` (artifacts
  `comfymodal-data/benchmarks/runs/v2_2026-08-16_03-11-06`)
- **Nonce:** `6575ef1d-4d59-4bb5-a46b-4e18865f0c9d` (fresh UUID)
- **Deploy (corrected):** `stable-modal-comfy-v2-restore-only-shadow`,
  generation `4ee9e0d0…`, deployment hash `e8f269ee…`, deployed
  2026-08-16T02:13:29Z. Deployed via the **atomic `V2_D6_FASTPATH_VALIDATION=1`
  profile** (launcher force-set the 8 flags; `--verify-d6-profile` printed
  `validation=PASS` before `modal deploy`); `fastsafetensors==0.3.3`
  installed in the image; D1 `--prime-registry-proof` → `store_entry_persisted:
  true, prime_ok: true`; the deploy issued **zero** inference requests.
- **Provider/region/host:** GCP / us-south1 / RTX PRO 6000 Blackwell,
  CPU 12, mem 32768 MiB, runtime-shape fingerprint `f504e296…`.

## 12. Structural gates (corrected run)

| Gate | Result | Evidence |
|---|---|---|
| Fresh | **YES** | Fresh; restore_count=1, request_count=1 |
| registry proof store HIT | **YES** | `[v2.harness] registry_load=skipped store_hit=yes`; `[v2.plan_proof] memo=hit` |
| full registry import after trigger | **NO** | `registry_load_ms` not incurred (store hit) |
| conditioning cache | **miss_stored** | lookup hit=0/miss=1; decision=miss_stored; key_hash `48de3b5a…`; encode_calls=1; encode_loop_wall_ms=5341.908 |
| DEPLOYED FLAG PROOF | **PASS** | `clip_fh_capture status=excluded` (params_replaced=399, payload_bytes_removed=**8,044,936,196**), `clip_fh_install status=installed` (candidates incl. fastsafetensors_direct_gpu), `clip_cold_forensics.status=installed`, `unet_fastsafetensors_pipeline flag=on` |
| clip_fh_capture | **PRESENT** | excluded, 8.04 GB payload removed at capture |
| clip_fh_hydration_start/end | **ABSENT** | not in the captured artifact (513 events; only capture+install present) |
| clip_cold_forensics.status | **installed** | (was `disabled` in the invalid run) |
| unet_fastsafetensors_pipeline | **PRESENT** | flag=on, eligibility=ok, family=ZImage, loader_version=0.3.3, nogds=true, use_buf_register=false |
| unet_fastsafetensors_reconcile | **PRESENT** | pipeline_total 3414.26, children 3412.76, residual 1.50, status OK, accounting_disjoint=true |
| Output SHA | **EXACT** | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` |

## 13. UNET / meta / D4 (corrected run) — STRONG PASS

`unet_fastsafetensors_pipeline` (from the artifact):

```
flag=on eligibility=ok family=ZImage loader_version=0.3.3
nogds=true use_buf_register=false max_copy_block_size_bytes=1 GiB
header_config_wall_ms=9.75 value_probe_wall_ms=1.37
meta_get_model_wall_ms=2979.08 sampling_fix_wall_ms=1.13
fastsafe_setup_wall_ms=18.16 fastsafe_file_gpu_wall_ms=2856.35
fastsafe_instantiate_wall_ms=0.85 worker_a_wall_ms=2981.20
worker_b_wall_ms=2875.41 join_delay_ms=2979.03
tensor_count=453 param_count=453 total_bytes=12,309,817,472
fastsafe_gbps=4.31 bind_wall_ms=7.99 owner_mode=loader_retained
owner_attr=_comfymodal_fastsafe_owner
```

`unet_fastsafetensors_reconcile` (D4 disjointness):

```
pipeline_total_ms=3414.26 accounting_children_ms=3412.76
residual_ms=1.50 reconciliation_status=OK accounting_disjoint=true
accounting_overlap_detail=null
meta_worker_start_delay_ms=0.69 meta_worker_execution_wall_ms=2981.20
meta_lifecycle_total_ms=2981.94 meta_execution_children_ms=2981.06
meta_execution_residual_ms=0.14 meta_lifecycle_residual_ms=0.06
meta_reconcile_status=OK
meta_worker_thread_cpu_ms=410.0 meta_worker_effective_cores=0.138
meta_non_thread_cpu_wall_ms=2571.20 worker_ab_overlap_ms=2875.45
input_types_warm_overlap_meta_ms=2974.02
input_types_warm_overlap_fastsafe_ms=2875.45
input_types_warm_overlap_scope=complete
```

- D2 patcher evidence for the UNET (patcher `46956473766416`, Lumina2):
  `device_distribution {cuda:0: 453}`, `loaded_mem_bytes=12,309,821,472`,
  `status ok`, `wall_ms=41.465` — **GPU-resident via fastsafe**, no native
  mmap/H2D replay.
- input_types_warm: **3593.416 ms / 31 classes**; overlap vs meta
  2974 ms and vs fastsafe 2875 ms, **scope=complete** → contention
  **SUPPORTED** (the warm daemon fully overlapped both fastsafe workers).
- Deep profiler: OFF (`forensics_enabled=false` in the reconcile event).
- META_CAUSE: **EXPLAINED** — `meta_get_model_wall_ms=2979` is essentially the
  whole `meta_worker_execution_wall_ms=2981`; thread CPU 410 ms → effective
  cores 0.14; non-thread-CPU wall 2571 ms is the model constructor running
  outside the worker thread's CPU time (dominant cost is model construction,
  not scheduling).

## 14. CLIP (corrected run) — capture PASS, hydration gate NOT MET

- Snapshot capture: **exclusion applied** — `clip_fh_capture status=excluded`,
  `params_replaced=399`, `payload_bytes_removed=8,044,936,196` (8.04 GB).
- Demand wrapper: **installed** (`clip_fh_install status=installed`,
  mode_candidates include `fastsafetensors_direct_gpu`).
- **Hydration events: `clip_fh_hydration_start/end` are ABSENT from the
  captured artifact.** `hydration_source` / `file_to_gpu_wall_ms` /
  zero-copy evidence for CLIP: **not present** in run_0.json.
- D2 forensics (installed) shows the CLIP patcher
  (`clip_role=clip`, ZImageTEModel_, patcher `46955215872272`):
  `device_distribution {cpu: 399}`, `loaded_mem_bytes=8,044,936,196`,
  source_files `[qwen_3_4b.safetensors]` — i.e., at patcher-load time the
  CLIP was **fully CPU-resident** (8.04 GB on CPU), not GPU-resident.
- CLIP forward span: `clip_forward_end cuda_allocated_delta_bytes =
  12,343,840,768` (~12.3 GB CUDA allocation inside forward) — the same
  magnitude as the native invalid run (12.4 GB), indicating a normal
  CPU→GPU materialization during encode rather than a zero-copy bind.
- Encode: tokenize 36.04 ms, gpu_prepare 8.82 ms (cuda delta 0),
  forward 5279.36 ms, raw_encode 5294.12 ms, encode_calls=1,
  CLIPTextEncode node 5328.4 ms.

**Interpretation (honest, not fabricated):** the snapshot-exclusion CAPTURE
evidence is present, but the RESTORE-side fast hydration did not produce the
required `clip_fh_hydration_start/end` telemetry in the captured artifact, and
the CLIP appears fully CPU-resident at patcher-load with a native-scale CUDA
allocation during forward. Per the hard gate ("actual feature evidence must
exist: clip_fh_hydration_start/end") this gate is **NOT MET**. Root cause is
a local code path question (demand wrapper reached `already_hydrated`/
native path and did not emit hydration events into the captured trace) —
to be reproduced and fixed locally before any future run.

## 15. D1 / permanent footer (corrected run)

```
process_start_to_response_ms                = 22374.998
user_equivalent_trigger_to_response_ms      = 22690.748
user_equivalent_trigger_to_modal_submission = 1007.36
trigger_to_submission_ms                    = plan_build 110 + submission (≈ local)
registry_proof_prime                        = true (store_entry_persisted true)
registry_proof_store_hit                    = YES
full_registry_import_after_trigger          = NO

COMMAND -> RESPONSE:                       22.690s
Command (without scheduling) -> Response:  18.459s
Scheduling time:                            4.231s
```

## 16. Corrected-run classification

```
D1_DISPATCH                    = PASS
CLIP_FAST_HYDRATION            = INVALID  (no clip_fh_hydration_start/end in
                                           captured artifact; CLIP CPU-resident
                                           at patcher load; native-scale CUDA
                                           delta in forward)
CLIP_SNAPSHOT_EXCLUSION        = CAPTURE PASS (8.04 GB removed) / restore-side
                                           NOT DEMONSTRATED
UNET_FASTSAFE                  = STRONG (GPU-resident, 4.31 GB/s, reconcile OK
                                           disjoint, owner retained)
META_CAUSE                     = EXPLAINED (get_model ≈ execution wall;
                                           non-thread-CPU 2571 ms)
INPUT_TYPES_WARM_CONTENTION    = SUPPORTED (overlap complete vs meta+fastsafe)
UNET_EXPOSED_WAIT              = loader total 3414 ms; graph wait window
                                           recorded (D5 events present)
OUTPUT_PARITY                  = EXACT
NEXT_PAID_RUN                  = OTHER — no further run of this configuration
                                           until the CLIP hydration telemetry
                                           gap is reproduced and fixed locally
                                           (root-cause the demand-wrapper
                                           already_hydrated/native path and the
                                           missing clip_fh_hydration events).
                                           NOT executed.
```

## 17. Final status (cumulative, both D6 remote runs)

```
run validity        = INVALID (corrected run: UNET fastsafe + D4 + parity PASS;
                      CLIP fast-hydration gate NOT MET — hydration events absent)
run id              = corrected: v2-benchmark-0-06813ab11164
                      baseline : v2-benchmark-0-090d16887f52 (native)
provider/region/host= GCP / us-south1 / RTX PRO 6000 Blackwell
deploy profile proof= PASS (V2_D6_FASTPATH_VALIDATION=1 → validation=PASS block)
D1                  = PASS (store hit, registry skipped after trigger)
command→response    = 22.690 s
non-scheduling      = 18.459 s
scheduling          = 4.231 s
CLIP fast hydration = INVALID (events absent; native-scale forward CUDA delta)
CLIP encode         = 1 call, 5294 ms total (tokenize 36, forward 5279)
CLIP exposed/hidden = N/A (fast hydration not proven)
snapshot exclusion  = capture applied (8.04 GB); restore-side not demonstrated
UNET fastsafe       = STRONG (GPU-resident 453 params, 4.31 GB/s, reconcile OK)
meta                = EXPLAINED (get_model 2979 ms ≈ worker wall 2981 ms)
input_types_warm    = 3593 ms, overlap complete vs meta+fastsafe (contention
                      SUPPORTED)
UNET exposed/hidden = loader total 3414 ms (D5 events recorded)
output SHA          = 20b10e1f… (EXACT)
comparison vs native= CLIP encode 5294 ms vs native 6139 ms; UNET fastsafe
                      4.31 GB/s direct-GPU vs native 3.1 GB/s synchronized H2D
                      (different hosts/paths — cross-host totals NOT subtracted)
classification      = D1 PASS · CLIP_FAST_HYDRATION INVALID ·
                      CLIP_SNAPSHOT_EXCLUSION PARTIAL · UNET_FASTSAFE STRONG ·
                      META_CAUSE EXPLAINED ·
                      INPUT_TYPES_WARM_CONTENTION SUPPORTED ·
                      UNET_EXPOSED_WAIT 3414 ms loader · OUTPUT_PARITY EXACT
next paid run       = OTHER — fix CLIP hydration telemetry locally first.
                      NOT executed.
commit              = none
total D6 deploys    = 2 (1 invalid-batch deploy + 1 corrected profile deploy)
total D6 Modal requests = 2 (1 invalid + 1 corrected)
```

---

# §18 — CLIP Restore-Lifecycle Root Cause (local batch; 0 deploys, 0 requests)

**Date:** 2026-08-16 · commit: none · C4 untouched.

## CLIP first materialization point

**The capture-phase eviction fresh reload — `modal_app.py:6718-6724`
(native `_cpu_load_clip` reload) → `modal_app.py:6778`
(`_container_retained.clip = _reloaded_model`) — running AFTER the D3 strip
(trace event 54: `clip_fh_capture status=excluded params_replaced=399
payload_bytes_removed=8,044,936,196`) and BEFORE the Modal memory-snapshot
fork (event 68).**

The 399 / 8.04 GB CPU CLIP parameters were **freshly reloaded from the
checkpoint file during snapshot capture by the eviction retain role**
(`deploy_and_run_v2_single.bat:61-63` pins `EVICT_MODELS_BEFORE_SNAPSHOT=1`
+ `EVICT_RETAIN_ROLE=clip_vae`; deploy log confirmed `eviction_enabled=1
eviction_role=clip_vae`). The eviction path nulls the D3-stripped clip
(`modal_app.py:6469-6470` — manifest + wrapper discarded with it), reloads a
fresh full-weight CLIP into `_container_retained` (`6778`), and the fork
serializes it. Restore then serves that full object
(`cpu_snapshot_clip_vae_bind clip_source=cpu_snapshot
cpu_snapshot_clip_reused=1`, trace 225-226) → native encode →
`device_distribution={cpu:399}` `loaded_mem_bytes=8,044,936,196` at
patcher-load (trace 305-307) → zero `clip_fh_hydration_*` events.

## Root cause

Integration conflict between the eviction retain-role experiment (launcher-
pinned) and D3 snapshot weight exclusion: the eviction fresh reload
re-materializes the full CLIP after the strip and before the fork,
discarding the excluded object that carried the frozen manifest + demand
wrapper. Not a telemetry bug, not the `already_hydrated` predicate (which is
marker-only and provably never fires on CPU residency alone), and not a
restore-time native reconstruction.

## Local proof (this batch, 0 deploys / 0 requests)

- capture exclusion physically effective locally = **YES** (in-place meta
  replacement; gc sweep found 0 live original storages; new regression test
  `test_exclusion_frees_original_storages`)
- storage aliases remaining after exclusion = **NONE in the capture path**
  (per-owner audit: CLIP/cond_stage_model/ModelPatcher/current_loaded_models
  (weakrefs)/cached_patcher_init (paths only)/container/registries all FREE;
  the only RETAIN is the eviction re-reload — the bug)
- restore state immediately before demand = **CPU_NATIVE_MATERIALIZED**
  (fresh full object, `get_clip_manifest is None`, no wrapper)
- why hydration_start/end absent = wrapper existed only on the DISCARDED
  stripped object; served object had no manifest/wrapper → silent
  `no_manifest` native path
- already_hydrated predicate = marker-only; CPU residency never qualifies
  (regression test: `test_cpu_materialized_before_demand_is_never_called_already_fast_hydrated`)
- wrapper-install ordering = capture install preceded eviction reload, so the
  wrapper was lost with the discarded object (not installed too late — wrong
  object lifetime)
- trace routing = one real hole fixed: restore-site install passed
  `trace=getattr(self,"_trace",None)` — `self._trace` is never assigned, so
  restore-installed hydrator events were dropped by the `_emit` None-guard;
  now uses `self._lifecycle_trace`. Startup events route correctly (the
  capture `clip_fh_capture`/`clip_fh_install` ARE in the artifact)

## Fixes landed (default-OFF, fail-closed, generic)

| Lane | Files | Change |
|---|---|---|
| F-A | `comfymodal_runtime/modal_app.py` | Eviction×D3 reconcile: freeze manifest (deepcopy) pre-eviction; re-apply attach+strip+demand-wrapper to the reloaded clip pre-fork; post-strip registry recompute; `clip_fh_eviction_reconcile` event; trace threaded into `_evict_snapshot_models`; restore install trace hole fixed |
| F-B | `clip_fast_hydration.py`, `clip_fast_hydration_wiring.py` | Explicit state taxonomy (EXCLUDED_PLACEHOLDER / CPU_NATIVE_MATERIALIZED / GPU_FAST_HYDRATED / GPU_NATIVE_LOADED / INVALID) + `clip_hydration_state()`; `clip_fh_hydration_decision` on EVERY demand branch with state_before/after; `clip_state_checkpoint` (default-OFF); summary carries state |
| F-C | `modal_app.py`, `model_preload.py`, `clip_cold_path_forensics.py` | 8 restore-side checkpoints (capture_pre_snapshot_return, restore_first_instruction, restore_after_retained_model_handling, restore_after_gpu_state, restore_after_snapshot_model_validation, restore_after_cpu_snapshot_bridge, conditioning_prefetch_worker_start, modelpatcher_load_entry) — 14 sites total |
| F-D | `tests/test_v2_clip_restore_lifecycle.py` (new) | 16 tests reproducing the real lifecycle + regression fixtures |

## Task 11 matrix (sequential, no contention)

| Batch | Result |
|---|---|
| D2/D3/state/eviction-reconcile/lifecycle suites | **118 OK (2 skips)** |
| cpu_snapshot_lifecycle + cpu_snapshot_models + restore_only + preload_bridge | **450 OK** |
| D1 dispatch/hash/proof + nonce + D6 profile + suffix | **106 OK** |
| runtime playground + submission timing + observability + breakdown | **251 OK** |
| py_compile (71 files) + `_test_clip_fast_hydration.py` | OK · 9/9 ALL PASS |

**Total: 925 tests OK + 2 skips, 0 unexplained failures.**

## Metrics position (corrected per evidence discipline)

META_LOCATION = explained (get_model 2979 ms ≈ 2981 ms Worker-A execution).
META_ROOT_CAUSE = still unresolved (wall − thread_time is not proof of
scheduler wait; the future INPUT_TYPES_WARM=0 A/B is the causal test).
INPUT_TYPES_WARM_STATUS = contention SUPPORTED (concurrence evidence only,
not causal proof).

## READY_FOR_ANOTHER_REMOTE_CLIP_VALIDATION = YES

Next ONE request (definition only, NOT executed): one canonical deploy with
`V2_D6_FASTPATH_VALIDATION=1` → expect `clip_fh_eviction_reconcile
status=excluded_after_eviction_reload` and `clip_state_checkpoint
capture_pre_snapshot_return state=EXCLUDED_PLACEHOLDER` in the persisted
trace; then one true-cold request with a fresh nonce → expect
`clip_fh_hydration_decision` with `state_before=EXCLUDED_PLACEHOLDER`,
`clip_fh_hydration_start/end`, D2 patcher boundary `{cuda:399}` with
`transfer_ops=0`, `encode_calls=1`, cache `miss_stored`, output SHA EXACT
`20b10e1f…`. Full detail: `V2_BATCH_D6_CLIP_RESTORE_LIFECYCLE_ROOT_CAUSE.md`.

---

# §19 — Post-Eviction Reconcile Batch Outcome (1 deploy attempt, 0 requests)

**Date:** 2026-08-16 · commit: none · C4 untouched · **Modal requests this batch = 0**

## Executive verdict

> **run validity = INVALID — capture-side gate FAILED. The single authorized
> deploy executed once, but the memory-snapshot build crashed on every
> attempt at the eviction weakref-death gate, so no usable snapshot was
> created. Per the hard gates: STOP — the true-cold request was NOT issued.**

## What happened (evidence from the Modal app log, deploy4 window)

1. **Local profile verification: PASS** (`[v2.d6_deploy_profile] validation=PASS`, exit 0).
2. **Deploy executed exactly once** with `V2_D6_FASTPATH_VALIDATION=1` +
   `snapshot_restore_only`. Server-side image deploy succeeded:
   `✓ App deployed in 144.928s!` + `=== V2 deploy verified OK ===` (d6_deploy4.log L585-592).
3. **Snapshot build FAILED on every attempt** — ~20 repeated full startups in
   the app log (1786861290–1786866275) all crash identically at
   `_evict_snapshot_models` step 12:
   ```
   [v2.snapshot_model_eviction] stage=snapshot_pre_capture enabled=1
       status=object_still_alive clip_original_id=47453872010768
       original_clip_alive_after_full_eviction=1
   RuntimeError('Full eviction failed: original weakrefs still alive: CLIP(id=47453872010768)')
   ```
   (modal_app.py:6637). No `Snapshot created` marker ever appears in the
   deploy4 window → **no usable memory snapshot exists**; the repeated
   startups are Modal cold-start retries (the post-deploy identity-record
   remote call), all failing identically.
4. **Capture-side gates FAILED**: `clip_fh_eviction_reconcile` and
   `clip_state_checkpoint capture_pre_snapshot_return` never emitted. The
   capture-side `[v2.clip_state]` prints DID prove the D3 exclusion itself
   works (`capture_post_exclusion state=EXCLUDED_PLACEHOLDER cpu_bytes=0
   meta_params=399 manifest_eligible=True`) — the failure is strictly the
   eviction weakref-death gate AFTER exclusion.
5. **Post-deploy local steps never completed** (identity record hung on
   crashing cold starts; client killed by the 90-min shell timeout).
   `.deployed_state.json` is stale (previous identity `e8f269ee…`); the D1
   prime for the new deployment did not run.

## Root cause (proven locally with the real wiring code)

**F-B's `_LAST_CLIP` module-global strong reference** roots the D3-stripped
original CLIP, defeating the eviction weakref-death proof:

- Capture-time install path: `maybe_install_clip_fh_demand`
  (clip_fast_hydration_wiring.py:979) → `_note_excluded(..., clip)` (:1048-1051)
  → `_note_clip(clip)` (:212-225) → `_LAST_CLIP = clip` (module global).
- The eviction contract (modal_app.py:6538-6544) requires the original clip
  weakref to die after `cpu_models.clip = None` + `gc.collect()` x2. The
  module-global strong reference makes that impossible.
- Deploy3 (pre-F-B) passed this exact check with
  `original_clip_alive_after_full_eviction=0`; deploy4 (post-F-B) fails on
  every attempt — the regression is this batch's F-B summary `state` feature.
- Empirical repro (D3 flags on, real wiring, fake clip + manifest + container):
  before fix → `_LAST_CLIP is clip: True`, `clip weakref alive after del+gc: True`.

## Fix (landed locally, default-OFF behavior preserved)

`comfymodal_runtime/clip_fast_hydration_wiring.py`:
- `_LAST_CLIP` now stores `weakref.ref(clip)` (never the object): L43 `import
  weakref`, L73 declaration comment, L224 `_LAST_CLIP = weakref.ref(clip)`
  (TypeError-guarded), L1057 `clip_fh_request_summary` dereferences via
  `isinstance(_clip_ref, weakref.ref)`.
- `_ACTIVE_TRACE`/`_RECORD`/`_LAST_EXCLUDED` verified NOT to hold model
  objects (trace holds JSON-safe events; record dicts hold mode strings).
- Repro after fix: `_LAST_CLIP is weakref: True`, `rooted: False`,
  `clip weakref alive after del+gc: False` — eviction gate now provable.

## Regression tests (new, `TestEvictionNoRootingWeakref` in tests/test_v2_clip_eviction_reconcile.py)

- `test_install_does_not_root_clip` — the eviction-contract regression: weakref
  taken before install must be dead after `del` + `gc.collect()` x2 (fails on
  the old code).
- `test_summary_state_attached_while_clip_alive` — summary `state` feature
  preserved while the clip is alive; absent after drop; never raises.
- `test_note_clip_weakref_non_weakrefable_guard` — None / `__slots__` object →
  `_LAST_CLIP is None`; weakrefable clip stored as a weakref only.

## Verification (this batch, sequential)

| Check | Result |
|---|---|
| `run_tests.py` eviction_reconcile + hydration_states + restore_lifecycle + phase_d_telemetry | **67 OK (1 skip)** |
| `run_tests.py` snapshot_restore_only + clip_fast_hydration_production + clip_cold_forensics | **141 OK (1 skip)** |
| `ast.parse` wiring + test file | OK |
| Repro before/after fix | alive True → **False** |

## Classification (final)

- **run validity** = INVALID (capture-side gate failure; snapshot build never
  succeeded; request NOT issued — STOP)
- **run id** = n/a (no request executed; deploy4 image `im-bA4ITDEoGQzM8EBlTVa6dm`
  deployed but snapshot unusable)
- **provider/region/host** = GCP / us-central1 (deploy4-era container sessions
  per app log `cloud=CLOUD_PROVIDER_GCP region=us-central1`)
- **capture exclusion survived eviction** = NO — eviction gate itself crashed
  (rooting regression); exclusion applied at capture (EXCLUDED_PLACEHOLDER,
  cpu_bytes=0) but the snapshot fork never happened
- **restore placeholder survived** = NOT TESTED (no snapshot → no restore)
- **hydration decision / CLIP direct-GPU hydration / clean encoder forward /
  CLIP lane total / UNET lane total / which lane gates sampling / output SHA /
  command→response / non-scheduling / scheduling** = N/A (no request issued)
- **D1** = NOT COMPLETED for the new identity (post-deploy steps interrupted;
  `.deployed_state.json` stale at `e8f269ee…`)
- **generic dtype optimization priority** = N/A — deferred: no clean
  GPU-resident encoder-forward measurement exists yet; the classification rule
  applies only after the corrected CLIP run
- **next recommended experiment** = ONE corrected redeploy (with the weakref
  fix) + ONE true-cold request per §18/root-cause doc — NOT executed
- **commit** = none · **deploy count (this batch)** = 1 · **Modal requests
  (this batch)** = 0 (total D6: 3 deploys / 2 requests)

---

# §20 — Post-Eviction Weakref Repair: Final Rooting Audit + Corrected Validation Preflight (ZERO-SPEND)

**Date:** 2026-08-16 · commit: none · C4 untouched · **Modal deploys = 0 ·
Modal requests = 0** (this batch is local-only preflight).

This section documents the systematic local proof that the deploy4 failure
(`RuntimeError('Full eviction failed: original weakrefs still alive:
CLIP(...)')` — §19) is fully repaired and that no other diagnostic/lifecycle
object can root the pre-eviction CLIP. The deploy4 failure remains a
preserved historical event (§19); nothing here overwrites it.

## 1. ROOTING AUDIT RESULT — PASS

Systematic object-retention audit (40 surfaces, exp-1 lane, read-only) across
clip_fast_hydration.py, clip_fast_hydration_wiring.py, clip_cold_path_forensics.py,
model_preload.py, modal_app.py, runtime_executor.py, trace.py,
cpu_snapshot_models.py, restore_plan.py, canonical_execution.py, env.py,
tools/benchmark_v2_direct.py + parent ComfyUI model_management.py /
model_patcher.py. Empirical gc verification with the real wiring install path
(fake fixtures, no comfy import): after drop + `gc.collect()` x2 the clip is
DEAD even with a live `_ACTIVE_TRACE` holding real events.

| Surface | Verdict |
|---|---|
| `_LAST_CLIP` (wiring:73/224) | ✅ weakref-only (the deploy4 regression, fixed) |
| `_ACTIVE_TRACE` (wiring:72/1010) | ✅ value-only events; empirically non-rooting while live |
| `_RECORD` / `_LAST_EXCLUDED` (wiring:61/1069) | ✅ value-only (mode strings, bools) |
| `_wrapped` closure (cfh:1392-1420) | ✅ unrooted clip→wrapper→clip cycle, collected by gc (proven) |
| `_hydrator` closure (wiring:1002) | ✅ captures trace+comfy_utils only, no clip cell |
| forensics `_INSTANCE`/`_installed`/`_trace` (forensics:142-187/155/1591) | ✅ functions + value-only event data; clip passed as call arg only |
| `_ACTIVE_REQUEST` ContextVar (forensics:89) | ✅ request-scoped value object |
| `_FAST_DISK_UNET_DEFERRALS` (model_preload:5670) | ✅ `model_ref` is a weakref |
| `_ACTIVE_V2_LOADER_BRIDGE` + bridge `_snapshot_loader_outputs`/`_preparation` (model_preload:11504/11574) | ✅ request-scope / restore-time; `clear()` + pools closed BEFORE eviction (modal_app:9162/6339) |
| `_C6_RING_SOURCES` (model_preload:260/4824) | ⚠️ bounded mmap-tensor UNET store (≤12, reset L1246) — tensors, not CLIP module; cannot trip the gate; observation only |
| `current_loaded_models` LoadedModel (parent model_management.py:687) | ✅ `_model = weakref.ref`; eviction also purges |
| `ModelPatcher.current_patcher`/backup/patches | ✅ cleared by cleanup/detach (modal_app:6458-89) + free_memory |
| `_cpu_snapshot_models` / `cpu_models.clip` (modal_app:5268/6527) | ✅ nulled at eviction step 8 |
| `_container_retained` (modal_app:6534) | ✅ container kept, clip nulled |
| `_snapshot_eviction_retained_model` (modal_app:6973) | ✅ holds only the FRESH post-eviction reload; cleared 7386 |
| canonical/telemetry caches (canonical_execution:118-441, host_hardware_telemetry:70-524) | ✅ value-only |
| trace records (contracts.py:333-340/1216-21) | ✅ MappingProxy frozen, JSON-safe leaves |

**No strong reference surface can root the pre-eviction CLIP.** Worst-case
closure-chain analysis: every reachable root is either weakref, value-only,
nulled-before-gc, or a collectable unrooted cycle.

## 2. `_LAST_CLIP` REPAIR VERIFIED — PASS

- Stores only `weakref.ref(clip)` or None (wiring:212-226, guarded TypeError).
- Safe deref in `clip_fh_request_summary` (wiring:1056-1065).
- No parallel strong field; no exception/debug path stores the object.
- Regression tests (TestEvictionNoRootingWeakref, 8 tests): live weakref
  summary works · dead weakref summary truthful (no resurrection) · repeated
  replacement retargets · summary after old clip collection · no rooting
  (`vars(wiring)` scan) · exception-path no-retention · non-weakrefable guard.

## 3. EXACT LIFECYCLE REPRODUCED — PASS (real wiring code)

tests/test_v2_clip_eviction_lifecycle.py (new, 5 tests) drives the REAL
cfh/wiring helpers through the full lifecycle: CPU_NATIVE_MATERIALIZED →
attach manifest → exclude (EXCLUDED_PLACEHOLDER, cpu_bytes=0) → install
wrapper → hold only weakref → clear container refs → `gc.collect()` x2 →
**original dead (hard eviction contract)** → fresh reload (new_clip is not
original; pre-reconcile CPU_NATIVE_MATERIALIZED) → reconcile via real helpers
(attach frozen manifest → strip → install wrapper) → EXCLUDED_PLACEHOLDER,
cpu_bytes=0, meta==full count, manifest present+eligible, wrapper marker,
container.clip is new_clip. Repeated 3× with module-global scan proving no
iteration clip retained.

## 4. PHYSICAL STORAGE ALIAS PROOF — PASS

| Metric | Value |
|---|---|
| logical_parameter_bytes_removed | 173,696 (params_replaced=22 == full count) |
| unique_original_storage_bytes_still_reachable | 0 (data_ptr scan; gc scan of original ptrs = 0) |
| full_cpu_payload_reachable | False (state=EXCLUDED_PLACEHOLDER, cpu_bytes=0) |
| rss_before / rss_after / delta | 416.8 / 423.0 MB (Windows allocator retains arenas — reported, NOT asserted) |

Storage-identity reachability is the stronger proof; RSS is informational.

## 5. EVICTION RECONCILE ORDERING — CONFIRMED

Current capture ordering (verified): load original CPU CLIP → attach D3
manifest → strip original → install wrapper → eviction discards original →
original weakref dies → eviction reloads NEW CPU-native CLIP → reconcile NEW
object (attach manifest, strip, install wrapper) → capture_pre_snapshot_return
→ Modal fork. `_container_retained.clip is new_clip`; manifest/wrapper live on
the NEW object; nothing lives only on the discarded object.

## 6. HYDRATION STATE MACHINE — INTACT

Taxonomy retained (EXCLUDED_PLACEHOLDER / CPU_NATIVE_MATERIALIZED /
GPU_FAST_HYDRATED / GPU_NATIVE_LOADED / INVALID). CPU-native existence NEVER
implies already-fast-hydrated (marker-only `clip_hydrated()`; decision events
carry state_before/decision/reason/manifest_present/wrapper_present/
owner_present/state_after; no model-name branches). Covered by
test_v2_clip_hydration_states.py + test_v2_clip_restore_lifecycle.py.

## 7. TRACE ROUTING — PASS (one low-severity residual noted)

- `self._trace` hole fully closed: zero occurrences in modal_app.py; restore
  install now passes `self._lifecycle_trace` (modal_app:9625-9628).
- Every D6 event reaches the persisted artifact: startup/lifecycle trace
  (capture + eviction-reconcile + demand via install-time closure capture),
  restore trace extended into lifecycle, request trace merged at 17505.
- All metadata JSON-safe value-only; `clip_fh_request_summary` reads state via
  the `_LAST_CLIP` weakref; TraceEvent metadata frozen (mappingproxy).
- Residual (low severity, diagnostic-only): three `_ACTIVE_TRACE`-fallback
  sites (clip_load_model_entry, conditioning_prefetch_worker_start,
  modelpatcher_load_entry) drop events only if no install ever succeeded
  (safe no-op, never a crash). Restore-without-startup edge is theoretical
  (startup always precedes restore in the Modal snapshot flow).

## 8. D1 IDENTITY HYGIENE — DOCUMENTED + TESTED

- `.deployed_state.json` is STALE (e8f269ee…/4ee9e0d0…, container_readback,
  2026-08-16T02:13:29 — the earlier corrected deploy; deploy4 never recorded).
- The registry-proof store's 8 entries are keyed to that stale anchor
  (canonical entry 405eb308…, workflow_hash 2e43d4c0…, eligible, validation
  present — healthy but STALE-anchored).
- Fail-closed proven: a NEW deployed identity (new generation + deployment
  hash) → anchor mismatch → `lookup` miss → `_registry_proof_store_covers`
  False → live registry import + prime required. New tests:
  tests/test_v2_d1_stale_identity.py (3 tests: full anchor change, partial
  deployment-hash drift, store not rewritten on miss).
- NEXT-DEPLOY sequence (current launcher anchors): (1) D6 profile force-set
  bat:124-142; (2) `--verify-d6-profile` gate bat:149-156 (hard-fail before
  deploy); (3) workspace load bat:158-173; (4) publish custom nodes bat:295/
  461; (5) deploy bat:302/470; (6) `record_deployment_identity.py` bat:334/
  485 (reads container-baked identity; hard-fail on empty triple); (7)
  `--prime-registry-proof` bat:341/492 (hard-fail when covers=False under the
  new anchor). Hard-fail: persisted identity != effective identity (step 6
  aborts → stale state never silently reused; `_registry_proof_store_covers`
  also flips False under a new anchor).

## 9. Capture-gate expectations for the corrected deploy (NOT run)

The corrected deploy must show, BEFORE any request: eviction
`original_clip_alive_after_full_eviction=0`; `clip_fh_eviction_reconcile
status=excluded_after_eviction_reload wrapper_installed=installed`;
`clip_state_checkpoint capture_pre_snapshot_return state=EXCLUDED_PLACEHOLDER
cpu_bytes=0 cpu_params=0 meta_params=399 manifest_eligible=true`; and finally
`Snapshot created`. Any failure → STOP, no request.

## 10. Test matrix (sequential, this batch)

| Batch | Result |
|---|---|
| eviction_reconcile(19) + eviction_lifecycle(5) + hydration_states + restore_lifecycle + phase_d_telemetry | **79 OK (1 skip)** |
| d6_deploy_profile + d1_stale_identity + d1_registry_proof_store + d1_dispatch_hash + d1_store_isolation + plan_validation_proof + deployment_proof | **76 OK** |
| cpu_snapshot_lifecycle + cpu_snapshot_models + snapshot_restore_only | **381 OK** |
| clip_fast_hydration_production + clip_cold_forensics + preload_bridge + runtime_playground_v2 | **195 OK (1 skip)** (1 intermittent failure twice, resolved on re-run — pre-existing Windows timer flake `test_sync_count_and_wall_attributed` sync_ms==0.0, documented since F5/6; not a regression) |
| py_compile (67 runtime + 5 test files) | OK |

**Total: 731 tests OK + 2 skips, 0 unexplained relevant failures.**

## 11. Files

- Created: tests/test_v2_clip_eviction_lifecycle.py (5 tests),
  tests/test_v2_d1_stale_identity.py (3 tests).
- Modified: comfymodal_runtime/clip_fast_hydration_wiring.py (`_LAST_CLIP`
  weakref + deref guards — the deploy4 repair), tests/test_v2_clip_eviction_reconcile.py
  (+8 tests: 5 weakref lifecycle + 2 trace-JSON-safety + 1 earlier).
- Prior-batch repair retained: modal_app.py eviction reconcile + restore
  trace fix; cfh.py state taxonomy; F-C checkpoints.

## 12. READY_FOR_CORRECTED_D6_DEPLOY = YES

Exact next procedure (NOT executed — awaits authorization):

**ONE deploy** (same shell):
```
set V2_D6_FASTPATH_VALIDATION=1
set V2_BENCHMARK_MODE=snapshot_restore_only
set COMFYMODAL_DEPLOY_TIMEOUT_SECONDS=5400
deploy_and_run_v2_single.bat
```
Gate check BEFORE any request: app log must show `original_clip_alive_after_full_eviction=0`,
`clip_fh_eviction_reconcile status=excluded_after_eviction_reload
wrapper_installed=installed`, `capture_pre_snapshot_return
state=EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399 manifest_eligible=true`,
`Snapshot created`, and `record_deployment_identity.py` + `--prime-registry-proof`
must both succeed with the NEW identity (recorded hash ≠ e8f269ee…).

**ONE true-cold request** (fresh nonce; the standing user-confirmed vehicle is
the default single-run loop, run count 1 — `--snapshot-restore-only` is a
no-op probe that cannot produce the required gates):
```
set V2_BENCHMARK_RUNS=1
run_v2_single.bat --conditioning-cache-nonce <FRESH_UUID>
```
Required: restore checkpoint chain all EXCLUDED_PLACEHOLDER →
`clip_fh_hydration_decision decision=hydrate state_before=EXCLUDED_PLACEHOLDER`
→ `clip_fh_hydration_start/end` (success, fallback_count=0) → GPU_FAST_HYDRATED,
cpu full bytes 0, fastsafe owner retained → D2 boundary transfer_ops=0,
H2D bytes=0 → cache `miss_stored`, `encode_calls=1` → output SHA EXACT
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`. No second
request automatically.
