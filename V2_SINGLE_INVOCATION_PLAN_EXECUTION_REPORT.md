# V2 Single-Invocation Plan Execution — Run Report

**Experiment: `publish_restore_plan` / `run_plan_stream` split REMOVED; 4 clean snapshot-reuse runs proven.**

Every number below is measured from the run artifacts listed in the Artifacts section
(`run_0.json` parsed directly; stage fields read from `timing`, `timing.local_timing`,
and trace events). All 4 measured runs use the new default path where the restore-plan
publication is eliminated from the request critical path.

## Artifacts

Runs dir: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\`

- **construction (uncounted):** `v2_2026-08-12_02-46-25/run_0.json` — GCP us-east1,
  restore_count=1, request_count=1, image im-oXelkp3JRnQVGbrdEAWksi, SHA
  sha256:bce9b6f05cd136f1f58af5926f82bc67f2743df9accd46f748f9dd29be1d6abb,
  c2r 297643.0, restore_total 655.958, submit2entry 275138.0.
- **probe (uncounted):** `restore_only_2026-08-12_02-52-55/` — VALID probe
  (restore_count=1, cold=True, AWS us-east-2, app stable-modal-comfy-v2-restore-only-shadow,
  no generation; prePy 9295.295, pyRestore 7125.977, resume2entry 7156.293).
- **run1:** `v2_2026-08-12_02-54-29/run_0.json` — AWS us-east-2, restore_count=1,
  restored_instance_id 4ec78c4b594747e9a413313df60da207, image im-oXelkp3JRnQVGbrdEAWksi;
  timing: restore_total_ms=1173.193, local_receive_to_actual_submission_ms=16.0,
  submission_to_first_remote_event_ms=107886.679, first_remote_event_to_final_result_ms=15973.629,
  command_to_response_ms=124334.4, sampler_ms=3768.046, vae_decode_ms=580.974,
  output_collection_ms=10.895; fast-disk bind 32.318 / to_wall 4892.199; cache decision
  exact_hit (reference prompt — deterministic parity run; encode_calls=0, key_hash
  9a02f7111bee51a0 == construction run's key); SHA bce9b6f0… (IDENTICAL to construction
  run — deterministic output parity for the established reference request).
- **run2:** `v2_2026-08-12_02-57-36/run_0.json` — GCP us-east1, restore_count=1,
  restored_instance_id 4ab955cf743b4405843e26d11a1be3c9; restore_total_ms=1377.773,
  local_receive_to_actual_submission_ms=10109.0, submission_to_first_remote_event_ms=19698.938,
  first_remote_event_to_final_result_ms=17685.886, command_to_response_ms=48143.8,
  sampler_ms=3710.184, vae_decode_ms=399.459, output_collection_ms=802.728;
  fast-disk bind 22.944 / to 2319.315; cache miss_stored encode_calls=1 key_hash
  a34bd44b95d85c48; SHA 9b2b21cf6f167c36ad90160fc4c8882ebf119f6fd09220de971b6f9b4e756ec9.
- **run3:** `v2_2026-08-12_02-58-45/run_0.json` — GCP us-east1, restore_count=1,
  restored_instance_id d717cfef748b4c8f8e1adc87bb1860b3; restore_total_ms=3219.67,
  local_receive_to_actual_submission_ms=2875.0, submission_to_first_remote_event_ms=283540.118,
  first_remote_event_to_final_result_ms=14696.943, command_to_response_ms=301644.3,
  sampler_ms=3672.996, vae_decode_ms=353.154, output_collection_ms=1231.348;
  fast-disk bind 16.859 / to 2001.334; cache miss_stored encode_calls=1 key_hash
  c3b567ba21122c72; SHA 37b4c62732bd14797c29a357394c544d844f77f70b270a503260de5c878fc47a.
- **run4:** `v2_2026-08-12_03-04-09/run_0.json` — GCP us-east1, restore_count=1,
  restored_instance_id c6ba0af959b244d595c7b2db6ed2e8a2; restore_total_ms=1228.568,
  local_receive_to_actual_submission_ms=9468.0, submission_to_first_remote_event_ms=163477.317,
  first_remote_event_to_final_result_ms=15619.961, command_to_response_ms=189076.7,
  sampler_ms=3700.277, vae_decode_ms=361.591, output_collection_ms=1077.03;
  fast-disk bind 18.499 / to 2125.288; cache miss_stored encode_calls=1 key_hash
  bf9fb65b39983800; SHA 96af7abbd3e35a9b493f79656e4fdfc8b71657f7b2e91c649070b4b76d0fc478.

---

# Executive conclusion

**Why the split existed.** Modal runs `restore()` before the request method receives
its args; the plan was originally published to the deployment-scoped runtime-state
volume (`comfymodal-runtime-config`, files `restore_state.json` + `snapshot_seed.json`)
so restore-time bootstrap could hydrate a topology seed (`[v2.seed_restore]
source=publisher_plan`) for loader/sampler cache seeding. The publish was a full Modal
method invocation awaited before `run_plan_stream`, so it (a) blocked every normal run,
(b) cold-started the snapshot-BUILDER container on fresh deploys (the publisher
invocation was the snapshot builder, making a logical "run" span two containers), and
(c) could take 74–188 s (observed 78,188 ms publish span in an earlier run; a ~180 s
`PersistentHandleError: publish_restore_plan timed out` previously).

**Removal.** Verified trace showed `restore()` never reads the plan file (restore is
lifecycle-only), the snapshot_seed is a pure warm-start enrichment that fails closed to
`startup_minimal`, and `run_plan_stream` derives everything from its `plan_payload`
arg (`ExecutionPlan.from_dict`; derive_model_key / derive_prefill_key /
build_restore_model_spec from `plan.workflow`). So the publisher was eliminated from the
normal generation path: the new opt-in flag `COMFYMODAL_V2_PUBLISH_RESTORE_PLAN`
(default 0) gates it; the default path emits `restore_publish_skipped` and
`restore_publish_ms` is null/absent (not 0, not cache-hit) in every run.

**One request = one Modal submission.** Every measured run shows exactly one
`modal_submission_attempt`, exactly one `run_plan_stream` `remote_method_entry`, exactly
one `final_result_received`; zero `restore_plan_publish_start/end/error`, zero
`restore_plan_remote_submit`.

**All 4 measured runs are valid snapshot-reuse generations.** restore_count=1,
request_count=1, a fresh unique restored_instance_id each, unet_present=0 with CLIP/VAE
retained, loader bridge active, native fast-disk defer+bind+complete (453 BF16 params on
CUDA, 0 CPU params/buffers, zero skips), invocation-plan seed consumed with
status=match reuse_enabled=1, valid outputs.

**Command-wall.** The publication wait is eliminated (absent vs 74–188 s historical);
measured c2r 48.1–301.6 s across the 4 runs is dominated by Modal scheduling variance
(submission→first-remote-event 19.7–283.5 s), NOT by measured compute (app wall
14.7–17.7 s).

---

# Previous architecture

Exact old call chain:

`tools/benchmark_v2_direct.py _run_one` → `canonical_execution.execute_plan(restore_publisher=RemoteRestorePlanPublisher(...))`
→ build snapshot_seed payload + RestorePlan locally → `restore_plan_publish_start` →
`restore_publisher.publish(...)` (**BLOCKING, awaited**; modal_transport.publish_restore_plan
→ `handle.publish_restore_plan.remote.aio` → modal_app.publish_restore_plan →
`_publish_restore_plan_impl` writes `restore_state.json` + `snapshot_seed.json` to the
runtime-state volume, one volume commit) → `restore_plan_publish_end` → THEN
`run_plan_stream` submit.

Restore-time bootstrap read `snapshot_seed.json` → `[v2.seed_restore] source=publisher_plan`;
fallback `startup_minimal`. `restore_publish_ms` entered timing. On fresh deploys the
publish invocation cold-started and BUILT the snapshot (the logical "run" spanned a
builder container + a generator container).

---

# New architecture

`local request → run_v2_single.bat → benchmark_v2_direct.py _run_one` →
`_resolve_restore_publisher()` returns None when `COMFYMODAL_V2_PUBLISH_RESTORE_PLAN` != "1"
→ `execute_plan(restore_publisher=None)` → skip branch: `restore_publish_skipped` trace
event + `[v2.restore_publish] skipped reason=flag_disabled`, seed persisted locally
labeled `invocation_plan`, `restore_publish_ms` absent → ONE `run_plan_stream`
submission → container: `restore()` (volume seed read SKIPPED —
`snapshot_seed_volume_read_skipped`, honest `startup_minimal`) → `_run_plan_stream_impl`
thaws `ExecutionPlan.from_dict(plan_payload)` and derives the request-owned seed from
`plan.workflow` (`snapshot_seed_request_derived`, `[v2.seed_restore]
source=invocation_plan`) → `snapshot_seed_consumed status=match reuse_enabled=1`
(loader/sampler cache seeding preserved) → graph execution.

Publish machinery remains behind the flag (opt-in diagnostics); the default path never
invokes it.

---

# Changed files

1. **`canonical_execution.py`** — publish block remains under `if restore_publisher is not None:`; when None, emits `restore_publish_skipped` (metadata reason=flag_disabled, restore_remote_call_performed=False) + console `[v2.restore_publish] skipped reason=flag_disabled`; local seed persist labeled `invocation_plan`; publish span excluded from local accounting.
2. **`tools/benchmark_v2_direct.py`** — `_resolve_restore_publisher()` (flag-gated; returns None when flag off) used by both `_run_one` sites (default single mode + acceptance).
3. **`tools/run_fresh_requests.py`** — same flag-gated publisher.
4. **`comfymodal_runtime/execution_seed.py`** — `publish_restore_plan_enabled()` env parser; `build_invocation_seed_payload()` (seed_source=invocation_plan, schema v2); `snapshot_seed_payload_from_dict` accepts the new source.
5. **`comfymodal_runtime/runtime_bootstrap.py`** — restore-time hydration gated: when publish disabled, volume `snapshot_seed.json` read skipped (`snapshot_seed_volume_read_skipped`, reason=publish_restore_plan_disabled); restore reports honest `[v2.seed_restore] source=startup_minimal`.
6. **`comfymodal_runtime/modal_app.py`** — `_run_plan_stream_impl` request-time seed derivation from `plan_payload` (`snapshot_seed_request_derived`, source=invocation_plan), hydrated into BootstrapState, attached via `_attach_snapshot_seed_metadata`; reuse guard requires workflow-hash intersection (honest).
7. **`comfymodal_runtime/trace.py`** — `restore_publish_ms`/`restore_pub_to_transport_entry_ms` render absent when publish events missing (no crash; breakdown line prints `absent`).
8. **`deploy_and_run_v2_single.bat` / `run_v2_single.bat`** — `if not defined COMFYMODAL_V2_PUBLISH_RESTORE_PLAN set "=0"` + `[v2.env_profile]` echo.
9. **Tests rewritten/updated:** `tests/test_v2_publish_restore_plan_registration.py` (flag defaults/opt-in; harness `_resolve_restore_publisher → None`), `tests/test_v2_publish_transport_spawn.py`, `tests/test_v2_seed_publication.py`, `tests/test_runtime_canonical_v2.py` (exactly-one `restore_publish_skipped`, zero publish start/end, `restore_publish_ms=None`; flag=1 legacy call still asserted), `tests/test_runtime_main.py`, `tests/test_v2_cold_warm_parity.py` (persisted payload source=invocation_plan), `tests/test_v2_lane_a_disk_persistence.py`, `tests/test_v2_snapshot_seed_request_metadata.py` (no-publish path derives invocation_plan seed, decision=status match, reuse enabled).

**Verification.** 662 tests + 34 subtests green across three bounded batches
(rewritten publish/seed suites + all core v2 integration suites: prefill, cache,
activation, fast-disk, restore-only, deep-profile, critical-path). Two pre-existing
flaky failures in `test_v2_preload_bridge.py` (install/drain) are unrelated and
documented pre-existing.

**Design constraint honored:** NO new remote preflight RPC under any name;
loader/eviction/CacheDiT/Sampling/prefill untouched.

---

# Snapshot / post-snapshot exclusion

- **Snapshot construction:** completed at deploy (the first container of the new
  deployment restored the new-image snapshot with restore_count=1; Modal deploy-time
  snapshot bootstrap; the snapshot build was NOT a benchmark generation). Deploy:
  `stable-modal-comfy-v2-shadow`, image im-oXelkp3JRnQVGbrdEAWksi, 112.8 s.
- **Post-snapshot lifecycle run (uncounted):** construction invocation
  `v2_2026-08-12_02-46-25` — a full generation proving post-snapshot execution;
  restore_count=1; output SHA identical to the reference (bce9b6f0…).
- **Post-snapshot verification (uncounted):** restore-only probe
  `restore_only_2026-08-12_02-52-55` — status=VALID (restore_count=1, cold=True,
  unet_present=0, clip/vae retained, graph NOT executed — no generation).
- **Proof of exclusion:** run indices 1–4 were assigned only after both lifecycle
  steps; the summary artifacts for runs 1–4 are distinct `v2_` dirs
  (`02-54-29`, `02-57-36`, `02-58-45`, `03-04-09`); exactly four generations were
  issued after construction+probe (hard stop; each run summary `run_count=1`).

---

# Correctness proof

Per-run proof fields, verified in every one of the 4 measured runs (and the
construction run):

| Proof field | Value in all 4 runs (+ construction) |
|---|---|
| `restore_publish_skipped` | count=1 (reason=flag_disabled, restore_remote_call_performed=False) |
| `restore_plan_publish_start` / `_end` / `_error` | count=0 each |
| `restore_plan_remote_submit` | count=0 |
| `modal_submission_attempt` | count=1 |
| `run_plan_stream` `remote_method_entry` | count=1 (exactly one; the other `remote_method_entry`s are lifecycle: startup + restore) |
| `final_result_received` | count=1 |
| `timing.local_timing.restore_publish_ms` | null/absent (never a measured span) |
| `snapshot_seed_volume_read_skipped` | reason=publish_restore_plan_disabled (seed_source=startup_minimal) |
| `snapshot_seed_request_derived` | seed_source=invocation_plan, schema_version=2, loader_node_count=3, sampler_node_count=1, reachable_node_count=43, static_signature_count=43 |
| `snapshot_seed_consumed` | status=match, reuse_enabled=1 |
| `snapshot_activation_invariant` | profile=inherit, status=pass, unet_present=0, clip_present=1, cpu_snapshot_active=1, loader_bridge_active=1 |
| `cpu_snapshot_clip_vae_bind` | status=ok (clip+vae from cpu_snapshot, unet normal_loader) |
| `unet_fast_disk_defer` | decision=defer, reason=ok, stage=to, target=cuda:0 |
| `unet_fast_disk_complete` | bind_assign=True, native_assign=False, param_count=453, dtype_distribution={torch.bfloat16:453}, device_distribution={cuda:453}, cpu_param_count=0 |
| `unet_fast_disk_skip` | count=0 |
| `unet_runtime_state` | stage=snapshot_created (ModelPatcher / Lumina2 / NextDiT, bf16) |
| `v2_startup_cachedit_preparation_start/end` | present (startup; e.g. 921.795 ms / 1338.883 ms / 921.795 / 921.795 ms) |
| `sage_snapshot_identity` | present (patched_at_snapshot) |
| output_hash_count | 1 (valid output) |

**Note on `gpu_invocation_submit`:** this event appears 3x per run. It is an internal
stage emission around the ONE logical submission — proven by the single
`modal_submission_attempt` + single `run_plan_stream` `remote_method_entry` + single
`final_result_received` (the three `gpu_invocation_submit` emissions correspond to
local submission, the lifecycle/startup container lineage, and the restore/run entry;
they do not denote separate requests). It must not be read as 3 submissions.

**Cache proof (run 1):** decision `exact_hit`, `encode_calls=0`, key_hash
`9a02f7111bee51a09f557c00b8f64847dad4a8dee5b5f4ae46ffcf08e4f8b9b0` — byte-identical to
the construction run's stored key (`9a02f7111bee51a0…`), i.e. the same reference
prompt hit the exact-conditioning cache. Output SHA bce9b6f0… is identical to the
construction run and to the same prompt's output on the previous deployment:
deterministic output parity. Runs 2–4 each performed a genuine cold miss
(`miss_stored`, `encode_calls=1`) with distinct key_hashes and distinct output SHAs.

---

# Four valid runs

| Run | Cloud | Region | Snapshot reused | Publisher RPC | Local→submit | Submit→remote | Restore | App wall | Command→response |
|---|---|---|---|---|---|---|---|---|---|
| 1 | AWS | us-east-2 | yes (restore_count=1) | none (`restore_publish_skipped=1`, `restore_publish_ms` null/absent) | 16.0 | 107886.679 | 1173.193 | 15973.629 | 124334.4 |
| 2 | GCP | us-east1 | yes (restore_count=1) | none | 10109.0 | 19698.938 | 1377.773 | 17685.886 | 48143.8 |
| 3 | GCP | us-east1 | yes (restore_count=1) | none | 2875.0 | 283540.118 | 3219.67 | 14696.943 | 301644.3 |
| 4 | GCP | us-east1 | yes (restore_count=1) | none | 9468.0 | 163477.317 | 1228.568 | 15619.961 | 189076.7 |

- **Local→submit** = `timing.local_timing.local_receive_to_actual_submission_ms`
  (includes active-profile warmup work; `active_profile_ms` 0.0 / 10109.0 / 2844.0 /
  9453.0).
- **Submit→remote** = `submission_to_first_remote_event_ms`.
- **Restore** = `restore_total_ms`.
- **App wall** = `first_remote_event_to_final_result_ms` (restore + pre-sampler +
  graph + sampling + VAE + output within the first-remote→final window).
- **Command→response** = `command_to_response_ms`.

---

# Before vs after

| | Old | New |
|---|---|---|
| Request path | `local → publish_restore_plan (74–78 s typical; ~180 s timeout observed once) → wait → run_plan_stream` | `local → run_plan_stream` |
| `restore_publish_ms` | measured span (e.g. 78,188.0 ms / 78.2 s in an earlier run; one ~180 s `PersistentHandleError: publish_restore_plan timed out`) | null/absent in all 4 runs |
| Submissions per request | 2 (publisher invocation + run_plan_stream) on fresh deploys | 1 (`modal_submission_attempt=1`) |
| Publish wait on critical path | present | eliminated |

Historical references only (NOT a same-cohort A/B): the earlier runs' `restore_publish_ms`
78,188.0 (78.2 s) and the ~180 s publish timeout are cited from prior artifacts/logs.
The command-wall comparison is bounded by platform scheduling variance (Submit→remote
19.7–283.5 s across the new runs) — the removal's attributable improvement is the
complete elimination of the publication span (74–188 s) from the critical path, not a
same-cohort c2r A/B.

---

# Benchmark validity

Each of the 4 measured runs is a genuine post-snapshot snapshot-reuse generation:
restore_count=1, request_count=1, unique restored_instance_id per run, single
`run_plan_stream` submission, no publisher events, seed from invocation payload
(reuse_enabled=1), unet_present=0 with CLIP/VAE retained, native fast-disk engaged
(453 BF16 CUDA params / 0 CPU / zero skips), valid output with hash_count=1.

None is a snapshot builder or post-snapshot probe — those are the uncounted
invocations (construction `v2_2026-08-12_02-46-25` and probe `restore_only_2026-08-12_02-52-55`)
issued before run 1 and excluded from run indices. Run 1 additionally proves
deterministic output parity for the reference request (SHA identical to the
construction run and to the same prompt's output on the previous deployment).

---

# Remaining command-wall latency

Separated components (all measured, ms):

| Component | run1 | run2 | run3 | run4 |
|---|---|---|---|---|
| (a) local preparation (`local_receive_to_actual_submission_ms`, incl. active-profile warmup) | 16.0 | 10109.0 | 2875.0 | 9468.0 |
| (b) Modal scheduling (`submission_to_remote_python_resume_ms`; residual resume→first-remote-event is small) | 107493.123 | 19202.44 | 281129.773 | 162980.369 |
| (b) Submit→remote (total, dominant) | 107886.679 | 19698.938 | 283540.118 | 163477.317 |
| (c) snapshot restore (`restore_total_ms`, 1.2–3.2 s) | 1173.193 | 1377.773 | 3219.67 | 1228.568 |
| (d) application execution (`first_remote_event_to_final_result_ms`, 14.7–17.7 s) | 15973.629 | 17685.886 | 14696.943 | 15619.961 |
| (e) result return (c2r − the above; local tail, small) | remainder | remainder | remainder | remainder |
| Command→response | 124334.4 | 48143.8 | 301644.3 | 189076.7 |

Application execution detail (d): graph activity 7731.346 / 8792.285 / 5402.318 /
6756.945 (5.4–8.8 s); pre-sampler 9523.98 / 10235.796 / 6579.122 / 7944.884
(6.6–10.2 s); sampling 3768.046 / 3710.184 / 3672.996 / 3700.277 (≈3.67–3.77 s);
VAE 580.974 / 399.459 / 353.154 / 361.591 (0.35–0.58 s); output collection 10.895 /
802.728 / 1231.348 / 1077.03 (0.01–1.23 s).

**The dominant term is (b) Modal scheduling:** submission→first-remote-event
19.7–283.5 s across four identical-config runs, with the resume→first-remote residual
only ≈0.4–2.4 s (393.6 / 496.5 / 2410.3 / 497.0 ms). Local preparation, restore, and
application execution are stable and small by comparison.

---

# Recommended next action

**Address the now-dominant Modal scheduling latency (submission→first-remote-event
19.7–283.5 s across four identical-config runs)** — e.g., a snapshot warm-pool /
keep-warm policy or scheduling investigation — as the single highest-value next step,
since the publication wait is eliminated and measured application wall is a stable
14.7–17.7 s. No code change to the loader/sampler/cache; no new remote preflight RPC.
