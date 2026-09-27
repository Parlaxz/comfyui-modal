# V2 Batch-B — Integrated Acceptance and Cohort Report

Date: 2026-08-14
Scope: reconciliation of all Batch-B lanes into one coherent runtime, the
remaining semantic integration patches, strict RUN-1 acceptance, and the
controlled cold data set. No new optimizations were added. No commit (the
checkout carries unrelated dirty Studio/browser/history work; nothing was
committed per the brief).

**Campaign convention (established by the continuation brief):**
- Cohort2 r0 (17:10:30, run 0) is the successful post-reconstruction cold
  **validation/check run** — NOT performance data.
- Cohort2 r1 (17:10:30, run 1) is **actual data run #1** (valid).
- The intended data set is 3–5 actual data runs total.

**Data collection status: STOPPED at the campaign stop condition.** One
additional run was attempted (17:29:13) and is **INVALID** as performance
data: its Batch-B acceptance gate PASSED, but the campaign's required
evidence check caught `plan_proof_decision=legacy_validation_fallback`
(`custom_nodes_generation_mismatch,dependency_proof_mismatch`) with the
certificate falling back to `volume_read` — exactly the "unexpected
plan-proof/certificate legacy fallback" stop condition. Per the brief, data
collection stops immediately; the exact cause is diagnosed in §8b. The final
valid data set is **1 run (Cohort2 r1)**. The strict RUN 1 PASSED.

---

## 1. Exact integrated file list

| Lane | Files | Status |
|---|---|---|
| B1 runtime-state volume reload guard | `comfymodal_runtime/runtime_bootstrap.py`, `comfymodal_runtime/runtime_generation.py`, `tests/test_runtime_state_reload_guard.py` | integrated as delivered; **+1 production wiring patch (see §2)** |
| B2 snapshot allocator hygiene | `comfymodal_runtime/snapshot_capture_hygiene.py`, `tests/test_v2_snapshot_capture_hygiene.py` | integrated as delivered; **+1 deploy-env passthrough fix (§2)** |
| B2 snapshot build manifest | `comfymodal_runtime/snapshot_build_manifest.py`, `tests/test_v2_snapshot_manifest_hygiene_extensions.py` | integrated as delivered |
| B2 stage-13 decomposition | `comfymodal_runtime/stage13_breakdown.py`, `tests/test_v2_stage13_breakdown.py` | integrated as delivered |
| B2 runtime integration | `comfymodal_runtime/modal_app.py` | **4 integration patches (§2)** |
| Batch-B acceptance harness | `tools/batch_b_acceptance.py`, `tests/test_batch_b_acceptance.py` | **8 reconciliation edits + 1 regression test (§2)** |
| Batch-A preservation harness | `tools/batch_a_acceptance.py`, `tests/test_batch_a_acceptance.py` | reused as-is (delegated by Batch B) |
| Runner | `tools/benchmark_v2_direct.py` | **1 host-side clock-skew correction (§2)** |

## 2. Reconciliation edits

All divergences were reconciled on the consumer/harness side or as additive
runtime wiring; no validated Batch-A runtime behavior was rewritten.

| # | File | Edit |
|---|---|---|
| 1 | `comfymodal_runtime/modal_app.py` (startup) | B1 construction-finalization call `self.bootstrap.finalize_runtime_state_generation(trace=trace, reason="construction")` placed at the semantic boundary — **after** `maybe_freeze_snapshot_gpu_capacity()` / `gpu_capacity_frozen.json` write, **before** snapshot capture (landed at lines 9000–9014; capture happens only when startup returns). Baseline generation stored into `_restore_timing["runtime_state_generation_baseline"]`. |
| 2 | `comfymodal_runtime/modal_app.py` (startup) | Snapshot-manifest record persisted into `_restore_timing["snapshot_manifest"]` (capture return value no longer discarded; lines 8978–8985). |
| 3 | `comfymodal_runtime/modal_app.py` (restore finalization) | `restore_timing_local` now starts from the startup timing dict so construction-time evidence (`snapshot_capture_hygiene`, `snapshot_manifest`, `runtime_state_generation_baseline`) reaches the run artifact (lines 10804–10826). |
| 4 | `comfymodal_runtime/modal_app.py` (`_runtime_env`) | Added `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE` explicit passthrough — without it the flag was silently dropped by `_runtime_env` and the container never produced the hygiene record (found pre-RUN-1; required the second deploy). |
| 5 | `tools/batch_b_acceptance.py` | Runtime-state evidence phase restriction: `reload_runtime_state_start/end` events are only counted as restore-lane evidence when `phase=="restore"` (construction containers legitimately emit `phase="startup"` reload events; they are not restore evidence). |
| 6 | `tools/batch_b_acceptance.py` | Stage-13 children resolution: `children_order` entries already carry the `_ms` suffix — resolve flat keys as-is instead of appending `_ms` again. |
| 7 | `tools/batch_b_acceptance.py` | Hygiene field names accepted: `before_rss_kb`/`after_rss_kb`/`before_rss_anon_kb`/`after_rss_anon_kb`/`gc_collected`/`malloc_trim_available` (runtime spelling). |
| 8 | `tools/batch_b_acceptance.py` | Invoked normalization: int `0/1` from event metadata normalized to bool (`_boolish`). |
| 9 | `tools/batch_b_acceptance.py` | Generation-check evidence also read from the `runtime_state_reload_decision` event's `check_ms` metadata; decision event loop restricted to restore phase. |
| 10 | `tools/batch_b_acceptance.py` | New non-gating informational check `stage13_boundaries_absence` (the private `_stage13_boundaries` transport must never survive into the yielded result). |
| 11 | `tests/test_batch_b_acceptance.py` | Runtime-spelled fixtures (true emission shapes: `_ms`-suffixed `children_order`, restore-phase decision event with int invoked, startup-phase reload events) + regression test for the startup-events false failure. |
| 12 | `tools/benchmark_v2_direct.py` | Host-side clock-skew correction in `reconcile_waterfall_local`: when the host result-receipt wall stamp precedes the container result-emit stamp (negative cross-process interval), the skew is subtracted from the residual; recorded as `clock_skew_correction_ms` + warning. This restores reconciliation to the true window (Batch-A gate mirrors the run's own `reconciliation_status`; the first RUN 1 failed on a −149.7 ms skew artifact, magnitude exactly equal to the measured container-vs-host clock skew). |

## 3. Local test results

- `python -m unittest tests.test_runtime_state_reload_guard tests.test_v2_snapshot_capture_hygiene tests.test_v2_stage13_breakdown tests.test_v2_snapshot_manifest_hygiene_extensions tests.test_batch_b_acceptance tests.test_batch_a_acceptance -v` → **106 tests OK** (0.273 s).
- `python -m pytest tests/test_v2_snapshot_capture_hygiene.py tests/test_v2_stage13_breakdown.py tests/test_v2_snapshot_manifest_hygiene_extensions.py -q` → **25 passed**.
- Adjacent regression suites (`tests.test_models_volume_reload_guard`, `tests.test_v2_transport_boundaries`, `tests.test_v2_waterfall_contract`) → **36 tests OK**.
- `py_compile` on all modified Python files → **OK**.
- Pre-flight proof: the actual failed RUN-1 artifact (`v2_2026-08-14_16-37-06/run_0.json`) re-validated against the fixed harness + skew correction → **PASS (all 8 gates)**, proving the fixes against real runtime output before the re-run.

## 4. Deploy identity

Two deploys were performed; the first (pre-hygiene-passthrough fix) was
superseded and never validated. **The integrated deployment is deploy #2.**

```
deployment        = stable-modal-comfy-v2-restore-only-shadow
deploy #2 hash    = f73cb563e99a67eaa32423692aa0872a081c9d7ecf258ecb6a4e7f4a7c7a37a1
image (runtime)   = im-B1LdSHCggPdDMnEPTU8kop
image (deps)      = im-rVK4NYsJDZiYQUOdqHwvWO / im-tMvmq2fwewYbUThgkNqdny
deployed_at       = 2026-08-14T16:36:57Z
comfyui           = 0.24.0 (commit f49bdb655707b979, host==deployed, core_match=1)
custom_nodes_generation = 6d27025c563e5293c315906f6a533cfe
manifest_classes  = 2399
runtime_shape     = TBASE / O0 / 12 CPU / 32768 MB
fingerprint       = f504e296c398bdcb2c4c07e2
dependency manifest hash = be68be1945de2a29 (unchanged from Batch A)
env profile       = inherit (snapshot_restore_only lineage); UNET excluded from
                    CPU snapshot; eviction clip_vae/idle 0; prefill critical;
                    release_gpu_after_request=0; single-use cold containers
cloud/region      = UNPINNED (GCP us-east4 observed for runs 1–4; GCP us-east1
                    for runs 5–7; provider/region preserved per run, never
                    filtered)
Batch-B runtime flags baked: COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE=1,
                    COMFYMODAL_V2_SNAPSHOT_MANIFEST=1
```

Deploy count: 2 total; the validated integrated deployment was deployed once
(deploy #2). The pre-fix deploy #1 (hash `ab9d5c5f47ed648e`, image
`im-NtVRAWViQzyLvIlMagTkI7`) was replaced before any validation run.

## 5. Strict RUN-1 acceptance block (RUN 1C — 16:53:10, complete flags)

```
BATCH B ACCEPTANCE

Batch A preserved:
PASS

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: skipped_generation_match
invoked: NO
reload ms: 0.0
generation check: YES
local only: YES

Snapshot hygiene:
enabled: 1
before RSS: 27007828.0
after RSS: 24734984.0
delta: -2272844.0
trim status: 1
manifest status: {'vmsize': 30379644, 'vmrss': 27007828, 'vmdata': 26269272, 'threads': 46}

Stage 13:
gate: READY
expectation: 1
total: 72.8
children: 8
largest child: waterfall_build_ms=38.4
reconciliation: 0.0

Host telemetry:
overhead (Tier A): 8.3
Tier B forensic probe: n/a
total probe: 8.3
forensic trigger: NO

TOTAL WALL: 167879.7 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: PASS
```

RUN 1C was a genuinely cold single-use run: `Fresh: YES`, unique
`restored_instance_id=f588d0e038314f38b3201790e7169073`, `restore_count=1`,
`request_count=1`, `image_id=im-B1LdSHCggPdDMnEPTU8kop`, GCP us-east4. It ran
during an extreme Modal scheduling stretch (158 s scheduling; TOTAL WALL
informational only and never gated — the run still PASSED).

## 6. RUN-1 evidence (RUN 1C artifact, `v2_2026-08-14_16-53-10/run_0.json`)

Batch A preservation (harness gates 1/4–7, all PASS): fresh identity, STATUS
OK (`reconciliation_status=OK` after skew correction), G1 plan-receipt
schedule present, exactly one UNET fast-disk H2D (2323.7 ms), one bind,
later schedule `already_prepared`, UNET identity match,
`reload_models_ms=0.0` + `reload_models_invoked=False` (models guard skip),
node timestamps present, terminal stamps valid, `snapshot_unet_absent=1`.

B1 runtime-state guard:

```
[runtime_state_generation_baseline] source=runtime_config_generation_json
  generation=0470c5e7833b… files=2 write_ms=3.454 fail_closed_reload=0
runtime_state_reload_decision (phase=restore):
  decision=skipped_generation_match reason=exact_match
  runtime_state_reload_invoked=0 check_ms=3.641
_restore_timing: reload_runtime_state_ms=0.0
                 reload_runtime_state_invoked=False
                 reload_runtime_state_reason=not_invoked
```

- construction baseline marker: schema v2 (`runtime_config_generation.json`,
  `schema_version=2`, generation + 2-file content manifest
  `prescan_custom_nodes.json` + `gpu_capacity_frozen.json`);
- generation match YES, content-manifest match YES;
- decision `skipped_generation_match`, reason `exact_match`;
- reload callback not invoked; no remote runtime-state reload RPC (no
  `reload_runtime_state_start/end` restore-phase events; `local only: YES`);
- local guard check cost: 2.0–3.7 ms on healthy hosts.

B2 hygiene (capture boundary, Linux): exactly one record,
`enabled=1 gc_collected=94 malloc_trim_available=True malloc_trim_result=1
hygiene_wall_ms=685.117 before_rss_kb=27007828 after_rss_kb=24734984
delta_rss_kb=-2272844` + RssAnon/RssFile/VmSize/VmData/cgroup deltas + manifest
`status` present (`[v2.snapshot_capture_hygiene]` console line emitted at
construction; identical record carried on every restore — it is a
construction-time measurement).

B2 stage 13: `output_stage13_breakdown` present with all eight children
(`children_order`), `stage13_total_ms=72.8`, `sum_children_ms≈total`,
`reconciliation_ms≈0.0` (status `ok`), largest child `waterfall_build_ms`
(38.4); `_stage13_boundaries` absent from the yielded result.

Telemetry: Tier-A 8.3 ms ≤ 20 ms; no slow-H2D forensic trigger on RUN 1C
(H2D 2323.7 ms < 4000 ms).

## 7. Executed runs and cohort table

| Run | Time (dir) | Instance (prefix) | Region | Scheduling | TOTAL WALL excl sched | Restore total | B1 check_ms | reload_rs_ms | UNET H2D | Stage13 total | Tier-A | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RUN 1 (failed, pre-fix) | 16-37-06 | f8eec92394 | us-east4 | 7.32 s | 32.90 s* | 418.7 ms | 3.708 | 0.0 | 2659.9 ms | 79.3 | 14.67 | FAIL (3 harness bugs → fixed, §2) |
| RUN 1B | 16-51-50 | 52210ee48a | us-east4 | 13.77 s | ~24.5 s | 294.2 ms | 2.03 | 0.0 | 2368.7 ms | 72.7 | 10.73 | PASS (hygiene/manifest gates off — incomplete flag set; not the strict RUN 1) |
| **RUN 1C (strict)** | 16-53-10 | f588d0e038 | us-east4 | 158.1 s | ~31.1 s | 270.7 ms | 3.641 | 0.0 | 2323.7 ms | 72.8 | 8.26 | **PASS** |
| Cohort1 r0 | 16-56-47 | 55d08eb76b | us-east4 | 58.9 s | ~30.2 s | 407.0 ms | 0.867 | 159.9 | 2373.6 ms | 74.0 | 8.26 | FAIL (runtime-state guard — correct fail-closed, §8) |
| Probe | 17-07-20 | 8a33ac47c2 | us-east1 | 18.3 s | ~72.3 s | 6886.0 ms | 1163.7 | 0.0 | 3498.9 ms | 75.3 | 27.55 | FAIL (Tier-A host variance: fingerprint probe 24.84 ms) |
| Cohort2 r0 | 17-10-30 | da7c2b19cb | us-east1 | 18.3 s | 45.2 s | 1195.2 ms | 213.6 | 0.0 | 4013.6 ms | 74.3 | 15.10 | **PASS** (slow-H2D forensic triggered, correctly classified) |
| Cohort2 r1 | 17-10-30 | 1877e583dc | us-east1 | 77.1 s | 24.6 s | 921.6 ms | 5.619 | 0.0 | 3380.6 ms | 82.1 | 15.29 | completed (no gate at index 1) → **data run #1 (valid)** |
| **Data run #2 (attempt)** | 17-29-13 | f0878affc4 | us-east1 | — | 32.8 s | 289.1 ms | 3.338 | 0.0 | 2159.0 ms | 73.8 | 11.2 | gate PASS, but **INVALID — stop condition (§8b)** |

*RUN 1's waterfall_local was pre-fix (EXCEEDS_TOLERANCE, −149.7 ms skew
artifact); the same artifact passes after the §2.12 skew correction.

**Campaign convention:** Cohort2 r0 (17:10:30, run 0) is the successful
post-reconstruction cold **validation/check run** — not performance data.
Cohort2 r1 (17:10:30, run 1) is **data run #1** (valid). The continuation
attempted one additional run (17:29:13); it triggered the campaign stop
condition (unexpected plan-proof/certificate legacy fallback, §8b) and is
**not valid performance data**. Per the brief, data collection stops
immediately. **Final valid data set: 1 run (Cohort2 r1); n=1 — medians equal
that run's values, ranges are single values.**

## 8. Platform event: snapshot re-construction and B1 fail-closed

RUN 1/1B/1C restored from the deploy-#2 snapshot (construction session
`fd1a0903d3904c6d`, baseline generation `18d12d07b56a…`). ~20 minutes after
deploy, Modal re-constructed the snapshot (new session
`1d9343783e5a46e9`, new baseline `0470c5e7833b…`); the marker write from that
re-construction was not yet visible on the shared runtime-state volume when
cohort1 r0 restored, so the guard read the old marker and correctly
fail-closed: `reloaded_generation_mismatch / generation_mismatch`,
`check_ms=0.867`, reload executed (159.9 ms), run completed healthy. By the
probe run (17:07) the volume had converged and the guard resumed skipping
(`exact_match`, reload 0.0). **The B1 guard performed exactly its designed
fail-closed behavior on a genuine platform divergence — it never skipped on a
mismatch.**

## 8b. Data run #2 (17:29:13) — campaign stop condition, exact cause

The continuation attempted one additional true-cold data run with the full
flag set (`V2_BENCHMARK_RUNS=1`, strict Batch-B gate, 35 s separation). The
Batch-B acceptance block printed **OVERALL: PASS** (Batch A preserved,
runtime-state skip, hygiene, Stage-13, Tier-A 11.2 ms all green), but the
campaign's required evidence check caught a structural invariant failure:

```
plan_snapshot_parity: deployment_hash_match=True  workflow_registry_match=True
  custom_nodes_generation_match=False  dependency_proof_match=False
plan_proof_decision: decision=legacy_validation_fallback
  reason=custom_nodes_generation_mismatch,dependency_proof_mismatch  consumed=False
certificate_read_outcome: cert_decision=volume_read  cert_cache_hit=False
  cert_source=volume        (healthy runs: plan_validation_fast_path, consumed=True)
```

Per the brief this is the "unexpected plan-proof/certificate legacy fallback"
stop condition: **STOP, do not continue collecting data, diagnose first.**
No further runs were attempted after diagnosis.

**Exact cause (fully traced):**

1. The plan's deployment identity is built on the HOST at plan-build time by
   `_collect_plan_deployment_identity` (canonical_execution.py:1117), which
   sources `custom_nodes_generation` and `dependency_manifest_identity`
   (`overall_dependency_hash`) from the deploy-generated baked manifest
   `.baked_custom_node_deps/custom_node_deps_baked.json`
   (`_read_baked_custom_node_manifest`, canonical_execution.py:965).
2. That local baked manifest was **regenerated at 17:15:04 UTC** (with
   `.last_custom_node_context_manifest.json` at 17:15:05 UTC) by a
   **concurrent worker process** (a deploy/publish flow — the same comfyapp
   writer that produced the deploy-time artifact; these files are not touched
   by this session's runner). The regenerated manifest now carries
   `production_custom_node_generation=cda45320f541704626be740e3e3270f3` —
   **different from the generation frozen into the snapshot proof at deploy #2**
   (`.deployed_state.json` unchanged since 16:36:57 UTC, generation
   `6d27025c563e5293c315906f6a533cfe`).
3. `evaluate_plan_snapshot_parity` (contracts.py:677) compares plan-carried
   vs snapshot-frozen fields: `deployment_combined_hash` (from unchanged
   `.deployed_state.json`) still matches, but `custom_nodes_generation` and
   the derived `dependency_manifest_identity` no longer match →
   `future_fast_path_eligible=False` → `plan_proof_decision=legacy_validation_fallback`
   → certificate fast path (`plan_validation_fast_path`) unavailable →
   `volume_read` fallback.
4. Corroboration: the unrelated concurrent run at 17:16:39
   (`v2-benchmark-0-0896981aed9d`, not this session's) shows the **identical**
   parity failure on the same deployment — the divergence began at ~17:15 UTC
   with the manifest regeneration, affecting every plan build since.

**Classification:** NOT a Batch-B integration regression and NOT a B1
fail-closed event. All Batch-B evidence on the run was healthy: B1
`skipped_generation_match / exact_match`, invoked=0, reload 0.0, check 3.338 ms;
models-volume skip intact; conditioning `exact_hit`; signature cache hit and
`topo_lazy_hits=36` intact; exactly one UNET read/bind/H2D (2159 ms); Stage-13
valid (73.8 ms, 8 children, reconciliation 0.0); Tier-A 11.2 ms. The failure
is a **host-side plan-identity divergence caused by a concurrent worker's
regeneration of the local baked custom-node manifest** — the plan no longer
matches the frozen snapshot proof, so the runtime correctly falls back to
legacy validation (fail-safe behavior, same category as the allowed B1
fail-closed transition: such a run is not valid performance data).

**Convergence path (not executed — do-not-deploy/do-not-change-source
constraints):** the local baked manifest must return to the deploy-#2 value
(or be regenerated in lockstep with a matching snapshot proof) before plan
proofs can match again. The volume itself is stable; the divergence is purely
the host-side baked manifest artifact. Data collection was stopped per the
brief; a fresh validation run must follow only after the concurrent
manifest regeneration has settled.

## 8c. Final valid data set (n = 1)

Per the campaign convention, Cohort2 r0 is the validation/check run (excluded
from performance data) and **Cohort2 r1 is data run #1 — the only valid data
run**. The continuation's data run #2 (17:29:13) was invalidated by the
stop condition (§8b), and per the brief no further runs were attempted. The
intended 3–5 run data set was therefore **not achieved**; with n = 1 the
"median" is the single run's value and the "range" is that value (no spread
claimable).

**Cohort2 r1 (data run #1) — full record** (artifact
`v2_2026-08-14_17-10-30/run_1.json`, console `v2_batchb_cohort2_console.log`):

- provider/region: GCP us-east1; instance `1877e583dc4e…`; restore_count=1,
  request_count=1 (Fresh=YES); snapshot age 942 991 ms (re-constructed
  snapshot session `1d9343783e5a46e9`).
- scheduling: 77 178 ms (first iteration → first remote event); scheduling
  excluded from TOTAL WALL (platform variance preserved, not rejected).
- TOTAL WALL excl scheduling: **24 573.6 ms**.
- app-controlled/post-resume wall (`controllable_wall_ms`): **19 349.2 ms**.
- pre-Python snapshot restore: 5445.3 ms.
- Python/application restore: application_restore 1282.2 ms; restore_total
  921.6 ms (snapshot_restore 889.0, restore_gpu_state 842.6, cuda_init 3.4,
  folder_warm 8078.1 — folder_warm is platform-side warm-up, excluded from
  the app-controlled figure).
- remote method setup: 764.8 ms.
- PromptExecutor/cache setup: 9.9 ms.
- pre-sampler: 9566.5 ms (waterfall stage; timing `pre_sampler_ms` 11 077.8).
- checkpoint read: no explicit checkpoint_read stage emitted (UNET fast-disk
  path; active-read evidence intact — Batch-A gate passed).
- UNET get_model: 126.5 ms; bind: 45.9 ms (1 bind end event); H2D: 3380.6 ms
  (exactly one `unet_fast_disk_complete`).
- sampling: 5059.7 ms (waterfall; timing `sampler_ms` 3765.8) —
  sampler_node_to_sampling 179.2 ms; post_sampling_transition 943.4 ms.
- VAE transition/decode: 1172.1 ms.
- Stage13: total **82.1 ms**, 8 children, reconciliation 0.001 ms (ok);
  largest child waterfall_build (from run-0 shape 38.9 ms; run 1
  `output_stage13_breakdown` children_order 8/8).
- result handoff: remote_local_return 32.0 ms; local_receive_to_result_return
  94 914.6 ms (includes scheduling).
- B1 local check: **5.619 ms**; `reload_runtime_state_ms=0.0`, invoked=0,
  decision `skipped_generation_match` / `exact_match`; models reload 0.0/0.
- Tier-A telemetry: **15.29 ms** (≤ 20 ms); Tier-B forensic: none triggered
  (H2D 3380.6 < 4000 ms).
- signature cache: `signature_cache_eligible=True`,
  `signature_cache_hit=True`, source=volume, reuse 3.5 ms;
  **`topo_lazy_hits=36`**; conditioning `decision=exact_hit` (lookup hit=1,
  miss=0, payload_memory_hit=1, normal_fallback=0).
- plan-proof/certificate: `plan_validation_fast_path`, consumed=True (no
  legacy fallback — the fast path this run required).
- UNET identity match: `unet_identity=z_image_turbo_bf`, identity_matches all
  True; exactly one UNET read/bind/H2D; later schedule
  `already_prepared`.

**n = 1 medians/ranges (single-run values, no spread):**

| Metric | Value |
|---|---|
| TOTAL WALL excl scheduling | 24 573.6 ms |
| app-controlled/post-resume wall | 19 349.2 ms |
| restore (application) | 1282.2 ms |
| pre-sampler | 9566.5 ms |
| H2D | 3380.6 ms |
| sampling | 5059.7 ms |
| Stage13 total | 82.1 ms |

## 9. B1 measured saving

- Historical remote runtime-state reload: ~81.9 ms median (pre-B1).
- Measured on the integrated deployment: `reload_runtime_state_ms=0.0` on all
  6 healthy skip runs; guard local check cost median **3.7 ms** on healthy
  hosts (2.03 / 3.641 / 3.708 / 5.619), two outliers 213.6 ms and 1163.7 ms on
  heavily loaded hosts (mount-latency-dominated O(1) reads — the decision
  stayed correct).
- **Measured saving ≈ 78 ms per healthy run** (81.9 − 3.7), plus zero remote
  Volume RPCs; the single fail-closed reload observed cost 159.9 ms (the
  platform divergence case, not the healthy path).

## 10. Hygiene measurements (construction-time record)

Single real Linux construction record (identical per run — captured once at
the capture boundary, snapshot-carried):

```
before_rss_kb=27007828 (25.76 GiB)   after_rss_kb=24734984 (23.59 GiB)
delta_rss_kb=-2272844 (-2.17 GiB)    before_rss_anon_kb / after_rss_anon_kb
  and RssFile/VmSize/VmData + cgroup memory.current deltas recorded
hygiene_wall_ms=685.117  gc_collected=94  malloc_trim_available=True
  malloc_trim_result=1  manifest_status={vmsize,vmrss,vmdata,threads}
```

- Exactly one hygiene event; `malloc_trim_available=True` on Linux;
- real before/after values, no fabricated zeros; unavailable → `None`
  convention honored in the module (verified by unit tests);
- hygiene wall time recorded (685 ms — includes gc + malloc_trim + two
  `/proc` reads + cgroup reads on the loaded construction container);
- **restore correlation:** no observable relationship between hygiene deltas
  and restore/pre-Python restore duration (restore total 270–1195 ms across
  runs, 6886 ms on the loaded-host probe; hygiene is a single construction
  measurement, so cross-run correlation is not applicable — n = 1 record).
  RSS decreased 2.17 GiB at capture; per the brief this is a measurement, not
  an acceptance criterion, and no win is claimed.

## 11. Stage-13 child distribution (6 healthy runs, n=6)

| Child | Median ms | p90 ms | Max ms |
|---|---|---|---|
| output_collection | 1.81 | 1.89 | 1.99 |
| asset_local_write | 0.81 | 1.10 | 1.21 |
| descriptor_build | 5.80 | 6.27 | 6.66 |
| trace_enrichment | 25.62 | 28.55 | 28.68 |
| interval_build | 0.02 | 0.03 | 0.06 |
| resource_enrichment | 0.24 | 0.27 | 0.32 |
| **waterfall_build** | **38.69** | **40.20** | **41.11** |
| other_pre_emit | 1.72 | 1.79 | 3.14 |

Parent/children reconcile within tolerance on every run
(`reconciliation_ms` ≤ 0.121 ms); largest child consistently
`waterfall_build` (≈38.7 ms median), followed by `trace_enrichment`
(≈25.6 ms). No Stage-13 optimization was performed in this batch.

## 12. Host/provider variance

- Provider/region unpinned: GCP us-east4 (runs 1–4) and GCP us-east1 (runs
  5–7). Scheduling 7.3 s–158.1 s — extreme platform scheduling variance today;
  TOTAL WALL (informational) 24.6–167.9 s.
- Tier-A telemetry: 8.3–15.3 ms on 6 runs (≤ 20 ms ✓); the probe run hit
  27.55 ms (fingerprint probe 24.84 ms on a loaded host). Historical envelope
  on the same lineage includes 101–109 ms probes — probe cost is host-load
  variable, not an app regression (telemetry lane untouched by Batch B).
- Clock skew: container-vs-host skew (−149.7 ms on RUN 1, −235 ms on RUN 1B)
  observed at the emit boundary; corrected host-side (§2.12) and recorded as
  `clock_skew_correction_ms`.
- Slow-H2D forensic: **one observed** — cohort2 r0 (H2D 4013.6 ms ≥ 4000 ms
  threshold): `host_forensic_slow_h2d` present, Tier-A 15.1 ms ≤ 20 ms,
  Tier-B forensic probe 95.1 ms reported separately → classified PASS by the
  harness exactly per the corrected contract.

## 13. Conclusions

**CONFIRMED**
- B1 construction-finalization marker is schema v2, written at the semantic
  boundary (after `gpu_capacity_frozen.json`, before capture), and the
  restore-time guard skips exactly on generation + content-manifest match
  (`skipped_generation_match / exact_match`), with `runtime_state_reload_invoked=0`
  and `reload_runtime_state_ms=0.0`.
- B1 never skips on a mismatch: the platform snapshot re-construction race
  produced a genuine generation mismatch and the guard fail-closed reloaded
  (159.9 ms) — evidence is runtime-state-specific, never models-volume.
- Stage-13 decomposition emits all eight children and reconciles within
  tolerance; `_stage13_boundaries` does not survive into the yielded result.
- Hygiene instrumentation is present when enabled, with real before/after
  values, `malloc_trim_available=True`, cgroup value, and null honesty.
- Batch-A structural invariants preserved on every gated run.
- Strict RUN 1 PASSED (RUN 1C) with the complete Batch-B flag set.
- Slow-H2D forensic (H2D ≥ 4000 ms) triggered exactly once and was classified
  PASS with Tier-A within budget and Tier-B reported separately.

**SUPPORTED INFERENCE**
- B1 removes the historical ~81.9 ms median remote reload: measured
  `reload_runtime_state_ms=0.0` on 6/6 healthy runs with a ~3.7 ms median
  local check (≈78 ms saving per healthy run, 0 remote RPCs). Based on the
  stated 81.9 ms historical median for the same restore lineage.
- `waterfall_build` (≈38.7 ms median, 40.2 ms p90) is the largest Stage-13
  child and the most plausible next optimization target; `trace_enrichment`
  (≈25.6 ms) second.
- The −2.17 GiB RSS delta at capture is attributable to gc + malloc_trim
  hygiene (order-of-magnitude consistent with freed anonymous memory), but is
  not claimed as a win.

**UNKNOWN**
- Whether allocator hygiene materially reduces captured RSS/anon/cgroup
  memory vs no-hygiene — no A/B construction comparison was run (single
  construction record).
- Any relationship between hygiene deltas and restore duration — n=1
  construction record, no correlation computable.
- The multi-run data distribution — data collection was stopped at the
  campaign stop condition after 1 valid data run (Cohort2 r1); median/p90
  TOTAL WALL and per-child distributions over the intended 3–5 data runs
  cannot be claimed (n=1; values below are single-run).
- The exact Modal mechanism behind the ~20-min snapshot re-construction
  (snapshot retention/eviction) — platform-side, unverified.

## 14. Next optimization candidates (ranked from measured evidence only)

1. **Stage-13 `waterfall_build`** — 38.7 ms median / 40.2 ms p90, the
   consistent largest child; does not consistently exceed ~50 ms, so it is a
   candidate, not a proven win.
2. **Stage-13 `trace_enrichment`** — 25.6 ms median / 28.6 ms p90.
3. (No Stage-13 optimization was performed in this batch; the brief forbade
   adding optimizations.)

---

# Appendix — Full Run Logs

The complete console logs of every executed run batch are embedded below,
verbatim (converted from the UTF-16 Tee capture). They contain the full
acceptance blocks, waterfall tables, submission breakdowns, and artifact
summaries. Artifacts (`run_*.json`) live in
`comfymodal-data/benchmarks/runs/v2_2026-08-14_{16-37-06,16-51-50,16-53-10,16-56-47,17-07-20,17-10-30}/`.

## A. v2_batchb_run1_console.log — RUN 1 (pre-fix harness; FAIL)

`
[v2.env_profile]
env_profile=inherit
thread_policy=TBASE
snapshot_model_order=O0
baseline_cpu_request=12
baseline_memory_request=32768
memory_request_mb=32768
vae_policy=v1
release_gpu_after_request=0
cpu_model_snapshot=1
native_fast_disk_unet=1
publish_restore_plan=0
vae_snapshot=1
clip_conditioning_cache=1
unet_activation_mode=late
vae_activation_mode=sampling_end
persistent_local_handle=1
full_trace=0
residency_diagnostics=0
deep_model_diag=0
pagefault_tracking=0
eviction_enabled=0
eviction_role=none
eviction_idle_seconds=0
prefill_lanes=critical
prefill_wait_for_unet=0
restore_torch_threads=none
variance_pretouch=0
volume_read_run_count=3
restore_only_app=stable-modal-comfy-v2-restore-only-shadow
restore_only_run_count=6
snapshot_exclude_unet=
=== Running one V2 benchmark trial against the existing deployment ===
=== Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
[v2.host] python_first_line_wall_unix_ns=1786725426723874700
{"guard": {"allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768, "changed_axes": []}, "runtime_shape": {"cpu_request": 12, "malloc_arena_max": null, "memory_request": 32768, "mkl_num_threads": null, "numexpr_num_threads": null, "omp_num_threads": null, "openblas_num_threads": null, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "snapshot_model_order": "O0", "thread_policy": "TBASE", "torch_interop_threads": null, "torch_intraop_threads": null}}
run_v2_single.bat : WARNING:root:WARNING: You need pytorch with cu130 or higher to use optimized CUDA operations.
At line:1 char:234
+ ... CH_B_EXPECT_SLOW_H2D_FORENSIC='1'; & .\run_v2_single.bat 2>&1 | Tee-O ...
+                                        ~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (WARNING:root:WA...UDA operations.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[v2.harness] prompt_server_mirror instance_set=True
WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

Package diffusers installed failed
Package diffusers installed failed
[33mModule 'diffusers' load failed. If you don't have it installed, do it:[0m
[33mpip install diffusers[0m
[34m[ComfyUI-Easy-Use] server: [0mv1.3.6 [92mLoaded[0m
[34m[ComfyUI-Easy-Use] web root: [0mC:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-easy-use\web_version/v2 [92mLoaded[0m
[exact_prefill.local] enabled=1 source=env
[timing_trace] module loaded __file__=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\timing_trace.py TRACE_VERSION=2.0.0
[timing_trace] module directory in sys.path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\__init__.py", line 7, in <module>
    from .src.interfaces import comfy_entrypoint, SeedVR2Extension
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\__init__.py", line 8, in <module>
    from .video_upscaler import SeedVR2VideoUpscaler
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\video_upscaler.py", line 10, in <module>
    from ..utils.downloads import download_weight
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\downloads.py", line 14, in <module>
    from .model_registry import MODEL_REGISTRY, DEFAULT_VAE
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\model_registry.py", line 12, in <module>
    from ..models.dit_3b.nadit import NaDiT as NaDiT3B
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\nadit.py", line 24, in <module>
    from .embedding import TimeEmbedding
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\embedding.py", line 17, in <module>
    from diffusers.models.embeddings import get_timestep_embedding
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\__init__.py", line 3, in <module>
    from .configuration_utils import ConfigMixin
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\configuration_utils.py", line 34, in 
<module>
    from .utils import DIFFUSERS_CACHE, HUGGINGFACE_CO_RESOLVE_ENDPOINT, DummyObject, deprecate, logging
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\__init__.py", line 37, in 
<module>
    from .dynamic_modules_utils import get_class_from_dynamic_module
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\dynamic_modules_utils.py", line 
29, in <module>
    from huggingface_hub import HfFolder, cached_download, hf_hub_download, model_info
ImportError: cannot import name 'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler module for custom nodes: cannot import name 
'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ckpts path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using symlinks: False[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ort providers: ['CUDAExecutionProvider', 'DirectMLExecutionProvider', 'OpenVINOExecutionProvider', 
'ROCMExecutionProvider', 'CPUExecutionProvider', 'CoreMLExecutionProvider'][0m
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\node_wrappers\dwpose.py:26: UserWarning: DWPose: Onnxruntime not 
found or doesn't come with acceleration providers, switch to OpenCV with CPU device. DWPose might run very slowly
  warnings.warn("DWPose: Onnxruntime not found or doesn't come with acceleration providers, switch to OpenCV with CPU 
device. DWPose might run very slowly")
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\__init__.py", line 2, in <module>
    from .nodes.ai.FL_Fal_Gemini_ImageEdit import FL_Fal_Gemini_ImageEdit
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\nodes\ai\FL_Fal_Gemini_ImageEdit.py", line 10, in <module>
    import fal_client
ModuleNotFoundError: No module named 'fal_client'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes module for custom nodes: No module named 'fal_client'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_sam3\__init__.py", 
line 11, in <module>
    from .src.comfyui_sam3.nodes import NODE_CLASS_MAPPINGS
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3\src\comfyui_sam3\nodes.py", line 6, in <module>
    from sam3.model_builder import build_sam3_image_model, build_sam3_video_model
ModuleNotFoundError: No module named 'sam3'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3 module for custom nodes: No module named 'sam3'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1073, in get_code
  File "<frozen importlib._bootstrap_external>", line 1130, in get_data
FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comyui-modal-pagesfile-probe module for custom nodes: [Errno 2] No such file or 
directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*, /comfymodal/history-v2/feed, /comfymodal/history-v2/generations/{id}/*, /comfymodal/history-v2/experiments/{id}/*, /comfymodal/history-v2/assets/{id}
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
ΓÜá∩╕Å  SeedVR2 optimizations check: SageAttention Γ¥î | Flash Attention Γ¥î | Triton Γ¥î
≡ƒÆí For best performance: pip install sageattention flash-attn triton
≡ƒôè Initial CUDA memory: 6.91GB free / 8.00GB total
### ComfyUI-Workflow-Encrypt: Copy .js from 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-workflow-encrypt\js\comfyui-workflow-encrypt.js' to 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\web\extensions\comfyui-workflow-encrypt'
# ≡ƒÿ║dzNodes: LayerStyle -> [1;33mCannot import name 'guidedFilter' from 'cv2.ximgproc'
A few nodes cannot works properly, while most nodes are not affected. Please REINSTALL package 'opencv-contrib-python'.
For detail refer to [4mhttps://github.com/chflame163/ComfyUI_LayerStyle/issues/5[0m[m
(RES4LYF) Init
(RES4LYF) Importing beta samplers.
(RES4LYF) Importing legacy samplers.

[92m[rgthree-comfy] Loaded 48 epic nodes. ≡ƒÄë[0m

[33m[rgthree-comfy] ComfyUI's new Node 2.0 rendering may be incompatible with some rgthree-comfy nodes and features, breaking some rendering as well as losing the ability to access a node's properties (a vital part of many nodes). It also appears to run MUCH more slowly spiking CPU usage and causing jankiness and unresponsiveness, especially with large workflows. Personally I am not planning to use the new Nodes 2.0 and, unfortunately, am not able to invest the time to investigate and overhaul rgthree-comfy where needed. If you have issues when Nodes 2.0 is enabled, I'd urge you to switch it off as well and join me in hoping ComfyUI is not planning to deprecate the existing, stable canvas rendering all together.
[0m
[v2.harness] production_output_registered output=True comparer=True
[v2.harness] node_registry_initialized classes=2192
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=miss
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-0-5e01eac1090a local_receive_to_worker_start_ms=16969.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16969.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=16.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=17063.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] owner_ready pid=19496
[v2.local_handle] decision=persistent_hit
FETCH ComfyRegistry Data: 5/172
FETCH ComfyRegistry Data: 10/172
[v2.local_submission_breakdown] request_id=v2-benchmark-0-5e01eac1090a local_receive_to_worker_start_ms=16969.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16969.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=16.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=17063.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=17063.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
FETCH ComfyRegistry Data: 15/172
FETCH ComfyRegistry Data: 20/172
FETCH ComfyRegistry Data: 25/172
FETCH ComfyRegistry Data: 30/172
[v2.request_origin] request_id=v2-benchmark-0-5e01eac1090a trigger_source=benchmark local_prompt_enqueued_unix_ns=None local_prompt_ack_ready_unix_ns=None modal_generator_created_unix_ns=1786725444057787000 modal_submission_attempt_unix_ns=1786725444057787000 modal_first_event_received_unix_ns=1786725451306139200 modal_first_iteration_start_unix_ns=1786725444057787000 modal_first_remote_event_unix_ns=1786725451306139200 dispatch_to_modal_entry_ms=7315.428 local_receive_to_actual_submission_ms=17063.0 local_receive_to_result_return_ms=36271.201 t0_to_t1_ms=0.986 t1_to_queue_enqueue_ms=None local_receive_to_enqueue_ms=None queue_wait_before_worker_ms=None plan_build_ms=78.0 active_profile_ms=0.0 handle_lookup_ms=0.0 payload_serialize_ms=0.0 local_residual_ms=0.0 clock_reconciliation_residual_ms=0.0 route_unattributed_ms=None worker_unattributed_ms=None reconciliation_status=incomplete missing_stages=local_receive_to_enqueue_ms overlap_error= modal_input_id=in-01M00J5AZ5GWK86RCNFB3FM6X9:1786725444582-0 trigger_to_local_receive_ms=0.986 local_receive_to_generator_create_start_ms=17056.801 generator_create_ms=13.0 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=7248.352 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=656.352 restore_end_to_modal_method_entry_ms=18.913 modal_method_entry_to_executor_ms=470.09 submission_to_remote_python_resume_ms=6640.163 unexplained_pre_remote_ms=7248.352
[v2.remote_request_origin] request_id=v2-benchmark-0-5e01eac1090a trigger_source=benchmark ui_trigger_unix_ms=1786725426987 local_receive_wall_unix_ns=1786725426987985920 local_receive_mono_ns=181551546000000 modal_generator_create_start_wall_unix_ns=1786725444044786600 modal_generator_create_start_mono_ns=181568609000000 modal_generator_created_wall_unix_ns=1786725444057787000 modal_generator_created_mono_ns=181568609000000 modal_first_iteration_start_wall_unix_ns=1786725444057787000 modal_first_iteration_start_mono_ns=181568609000000 modal_submission_attempt_wall_unix_ns=1786725444057787000 modal_submission_attempt_mono_ns=181568609000000 modal_first_remote_event_wall_unix_ns=1786725451306139200 modal_first_remote_event_mono_ns=181575859000000 modal_submission_boundary_source=first_iteration_proxy remote_python_resume_wall_unix_ns=1786725450697949952 restore_method_start_wall_unix_ns=1786725450697949952 restore_method_end_wall_unix_ns=1786725451354301696 modal_method_entry_wall_unix_ns=1786725451373214720 prompt_executor_invoke_start_wall_unix_ns=1786725451843304960 trigger_to_local_receive_ms=0.986 local_receive_to_generator_create_start_ms=17056.801 generator_create_ms=13.0 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=7248.352 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=656.352 restore_end_to_modal_method_entry_ms=18.913 modal_method_entry_to_executor_ms=470.09 submission_to_remote_python_resume_ms=6640.163 unexplained_pre_remote_ms=7248.352 modal_input_id=in-01M00J5AZ5GWK86RCNFB3FM6X9:1786725444582-0
[v2.local_submission_breakdown.final] request_id=v2-benchmark-0-5e01eac1090a local_receive_to_worker_start_ms=16969.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16969.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=16.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=17063.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=17063.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent modal_submission_attempt_unix_ns=1786725444057787000 modal_generator_created_unix_ns=1786725444057787000 modal_first_iteration_start_unix_ns=1786725444057787000 modal_first_remote_event_unix_ns=1786725451306139200 dispatch_to_modal_entry_ms=7315.428 local_receive_to_actual_submission_ms=17063.0 local_receive_to_result_return_ms=36271.201
FETCH ComfyRegistry Data: 35/172
WATERFALL RECONCILIATION (local rebuild) replaced remote PARTIAL report with the full host-reconciled report
WATERFALL RECONCILIATION (local rebuild)
  command_to_response_ms            36701.2
  top_level_accounted_ms            33045.2
  global_residual_ms                -149.7
  global_residual_pct               -0.5
  reconciliation_status             EXCEEDS_TOLERANCE
  controllable_application_wall_ms  30210.7
  platform_wall_ms                  6640.2
  modal_restore_begin_unavailable   no
  OLD vs NEW accounted_ms 30210.7 -> 33045.2 | residual_ms -149.7 -> -149.7
production_adjusted_total_wall_ms=15945.74
FETCH ComfyRegistry Data: 40/172
[v2.experiment] saved=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_16-37-06\run_001_sample.json
{"run_index": 0, "request_id": "v2-benchmark-0-5e01eac1090a", "identity": {"app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint", "method_name": "run_plan_stream", "gpu": ["RTX-PRO-6000"], "cpu": 12, "memory_mb": 32768, "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "runtime_shape": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "stored_snapshot_model_order": "O0", "restore_count": 1, "request_count": 1, "restored_instance_id": "f8eec92394dc423cbe243e46a9910d7f", "restore_session_id": "98c08eab77f9421b9ecd09887276e2a5", "container_task_id": "ta-01M00J5BPG6JR7J5KQQZFRCA9R", "modal_container_id": "", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "modal_input_id": "in-01M00J5AZ5GWK86RCNFB3FM6X9:1786725444582-0", "container_session_id": "fd1a0903d3904c6d"}, "runtime_shape": {"requested": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "deployed": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "observed": {"stage": "request_entry", "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "thread_policy": "TBASE", "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "native_thread_count": 53, "configured_omp": null, "configured_mkl": null, "configured_openblas": null, "configured_numexpr": null, "malloc_arena_max": null, "native_library_settings": {"OMP_NUM_THREADS": "12", "MKL_NUM_THREADS": "12", "OPENBLAS_NUM_THREADS": "12", "NUMEXPR_NUM_THREADS": null, "MALLOC_ARENA_MAX": null}, "torch_intraop_threads": 12, "torch_interop_threads": 14, "actual_torch_intraop_threads": 12, "actual_torch_interop_threads": 14, "requested_torch_intraop_threads": null, "requested_torch_interop_threads": null, "requested_vs_actual_match": true, "status": "baseline_passthrough", "error": "", "trace_id": "5382f50419c84d1e", "pid": 2, "thread_native_id": 2, "restored_instance_id": "f8eec92394dc423cbe243e46a9910d7f", "restore_session_id": "98c08eab77f9421b9ecd09887276e2a5", "legacy_container_session_id": "fd1a0903d3904c6d", "container_task_id": "ta-01M00J5BPG6JR7J5KQQZFRCA9R", "modal_input_id": "in-01M00J5AZ5GWK86RCNFB3FM6X9:1786725444582-0", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint"}, "stored_snapshot_model_order": "O0", "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "guard": {"changed_axes": [], "allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768}, "construction_order_semantics": "model_construction_order_only"}, "timing": {"wall_ms": 19236.4, "handle_lookup_ms": 13.0, "submission_to_first_remote_event_ms": 7248.352, "command_to_response_ms": 36701.2, "submit2entry_ms": 7329.429, "t3b_to_t8_ms": 11502.195, "restore_total_ms": 418.657, "pre_sampler_ms": 6476.54, "sampler_ms": 3658.92, "vae_decode_ms": 407.045, "output_collection_ms": 7.738, "snapshot_callback_age_at_restore_ms": 70752.093, "snapshot_callback_to_command_start_ms": 46390.297, "command_start_to_restore_start_ms": 24124.95, "local_timing": {"t0_to_t1_ms": 0.986, "t1_to_queue_enqueue_ms": null, "local_receive_to_enqueue_ms": null, "local_body_read_ms": null, "local_json_parse_ms": null, "local_preflight_ms": null, "local_queue_lock_wait_ms": null, "local_queue_enqueue_ms": null, "queue_wait_before_worker_ms": null, "plan_build_ms": 78.0, "active_profile_ms": 0.0, "restore_plan_build_ms": null, "restore_publish_ms": null, "handle_lookup_ms": 0.0, "payload_serialize_ms": 0.0, "payload_materialization_ms": 0.0, "payload_size_measurement_ms": 0.0, "generator_create_ms": 13.0, "local_residual_ms": 0.0, "clock_reconciliation_residual_ms": 0.0, "route_unattributed_ms": null, "worker_unattributed_ms": null, "reconciliation_status": "incomplete", "missing_stages": ["local_receive_to_enqueue_ms"], "overlap_error": "", "stage_attribution_residual_ms": {"route_unattributed_ms": null, "worker_unattributed_ms": null, "missing_stages": ["local_receive_to_enqueue_ms"], "reconciliation_status": "incomplete", "overlap_error": ""}, "local_receive_to_generator_create_ms": 17063.0, "generator_create_to_first_iteration_ms": 0.0, "first_iteration_to_first_remote_event_ms": 7248.352, "local_receive_to_actual_submission_ms": 17063.0, "trigger_to_local_receive_ms": 0.986, "local_receive_to_generator_create_start_ms": 17056.801, "generator_created_to_first_iteration_ms": 0.0, "remote_python_resume_to_restore_start_ms": 0.0, "restore_method_ms": 656.352, "restore_end_to_modal_method_entry_ms": 18.913, "modal_method_entry_to_executor_ms": 470.09, "submission_to_remote_python_resume_ms": 6640.163, "unexplained_pre_remote_ms": 7248.352, "local_result_received_wall_ns": 1786725463259186700, "local_result_received_mono_ns": 181587812000000, "local_receive_to_result_return_ms": 36271.201, "result_received_to_return_ms": 15.001, "remote_result_emit_wall_unix_ns": 1786725463408650969, "remote_result_emit_to_local_receipt_ms": null, "caller_return_wall_unix_ns": 1786725463274187300, "caller_return_mono_ns": 181587828000000, "local_result_received_to_caller_return_ms": 16.0, "modal_restore_begin_wall_unix_ns": null}, "restore_breakdown": {"restore_total_ms": 418.657, "models_symlink_ms": 3.44, "manager_offline_ms": 1.18, "reload_models_ms": 0.0, "reload_runtime_state_ms": 0.0, "v2_startup_custom_node_source_copy_ms": 367.16, "sync_custom_nodes_ms": 367.3, "install_requirements_ms": 0.01, "v2_startup_comfyui_path_startup_ms": 0.34, "comfyui_path_setup_ms": 0.49, "v2_startup_backend_startup_ms": 19953.37, "backend_startup_ms": 19954.11, "observe_generations_ms": 0.83, "snapshot_restore_ms": 396.0, "snapshot_callback_age_at_restore_ms": 70752.093, "restore_gpu_state_ms": 263.415, "cuda_init_ms": 100.15, "v2_startup_snapshot_execution_seed_ms": 1.05, "initialize_cuda_ms": 100.049, "snapshot_identity_checks_ms": 0.0, "cpu_snapshot_retargeting_ms": 0.0, "folder_warm_ms": 3275.033}, "early_activation_total_ms": null, "queue_delay_ms": null, "cpu_snapshot_wait_ms": null, "dtype_layout_preparation_ms": null, "post_load_bookkeeping_ms": null, "submission_to_remote_python_resume_ms": 6640.163, "remote_python_resume_to_restore_start_ms": 0.0, "restore_to_method_entry_ms": 18.913, "method_entry_to_first_remote_event_ms": null, "first_remote_event_to_final_result_ms": 11953.048, "transfer_queue_delay_ms": null, "synchronized_transfer_ms": null, "quiesce_wait_ms": null, "graph_activity_ms": 5249.109, "sampler_lane_wait_ms": 0.089, "quiesced_transfer": null}}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-5e01eac1090a  Instance: f8eec92394dc423cbe243e46a9910d7f  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east4
TOTAL WALL:           32.896s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    36.701s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 414.986 ms | 414.986 ms |   1.262% | #                                        |
|   2 | Modal handle and submission                    |    17.070s |    17.485s |  51.891% | #####################                    |
|   3 | Modal pre-Python snapshot restoration          |     2.835s |    20.319s |   8.617% | ###                                      |
|   4 | Python/application restore                     | 656.348 ms |    20.976s |   1.995% | #                                        |
|   5 | Restore-to-method entry                        |  18.903 ms |    20.995s |   0.057% | #                                        |
|   6 | Remote method setup                            | 470.135 ms |    21.465s |   1.429% | #                                        |
|     |   method entry to graph start                  | 391.656 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 391.616 ms |            |          |                                          |
|     |   graph setup                                  |  78.479 ms |            |          |                                          |
|     |   preload check                                |  29.191 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |     2.352s |    23.817s |   7.150% | ###                                      |
|     |   execution to cached                          |     1.670s |            |          |                                          |
|     |   cached to first node                         | 681.219 ms |            |          |                                          |
|   8 | Pre-sampler execution                          |     2.897s |    26.714s |   8.806% | ####                                     |
|     |   Conditioning cache decision=miss_stored h... |   0.719 ms |            |          |                                          |
|     |   CLIP encode (1 calls)                        |     5.132s |            |          |                                          |
|     |   Node: ImpactSwitch                           |  25.933 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  49.096 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 137.037 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.938s |            |          |                                          |
|     |   Read end -> construction done                |   0.847 ms |            |          |                                          |
|     |   UNET get_model                               | 286.108 ms |            |          |                                          |
|     |   Bind                                         | 173.854 ms |            |          |                                          |
|     |   Synchronized H2D (4.6 GB/s)                  |     2.660s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.443 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 128.707 ms |    26.842s |   0.391% | #                                        |
|     |   lane acquired to actual stage                | 128.680 ms |            |          |                                          |
|  10 | Sampling                                       |     4.753s |    31.595s |  14.448% | ######                                   |
|  11 | Post-sampling / VAE transition                 | 774.609 ms |    32.370s |   2.355% | #                                        |
|  12 | VAE decode                                     | 407.045 ms |    32.777s |   1.237% | #                                        |
|     |   VAE load/H2D                                 | 804.824 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 252.445 ms |    33.029s |   0.767% | #                                        |
|     |   PNG encode                                   | 174.919 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  16.000 ms |    33.045s |   0.049% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     3.806s |            |          |                                          |
|     | RECONCILIATION                                 | -149.706 ms |            |          |                                          |
|     | STATUS                                         | EXCEEDS_TOLERANCE |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.prompt_executor_breakdown] request_id=v2-benchmark-0-5e01eac1090a exec_to_cached_ms=1670.348 dynamic_prompt_ms=0.004 is_changed_ms=0.171 signature_keys_ms=1665.859 seed_apply_ms=absent clean_unused_ms=0.04 cache_gather_ms=0.099 cleanup_gc_ms=11.855 residual_ms=-7.68 c2f_cached_to_first_node_ms=681.219 c2f_topo_walk_ms=681.012 c2f_topo_input_info_ms=300.304 c2f_topo_other_ms=380.708 c2f_stage_ms=1.266 c2f_first_node_prefix_ms=0.164 c2f_residual_ms=-1.223 signature_cache_eligible=True signature_cache_fallback=no_entry signature_cache_hit=False signature_cache_key_hash=8ffd5d7760804fa9ba99b1419063ecd931de3044a0f30a33c8a000a3197235c9 signature_cache_requested=True signature_cache_source=none topo_lazy_pending=36
[v2.conditioning_exact_hit_breakdown] request_id=v2-benchmark-0-5e01eac1090a decision=miss_stored lookup_wall_ms=0.719 total_ms=0.516 key_build_ms=0.175 lock_wait_ms=0.001 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=33 entry_lookup_ms=0.139 header_bytes=0 data_bytes=0 lru_touch_ms=0.0 lru_touch_mode=sync children_ms=0.315 residual_ms=0.201 entries_requested=1 hit_count=0 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=1 normal_lookup_fallback=0 payload_memory_hit=0 payload_memory_source= prefetch_join_ms=22.816 prefetch_join_timeout=0 prefetch_overlap_ms=0.0 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=335.196 volume_reload_ms=0.0
[v2.folder_warm] request_id=v2-benchmark-0-5e01eac1090a folder_warm_ms=3275.033 folder_warm_folders=29
[v2.input_types_warm] request_id=v2-benchmark-0-5e01eac1090a input_types_warm_ms=1097.75 input_types_warm_classes=31
[v2.png_output] request_id=v2-benchmark-0-5e01eac1090a compress_level=1 png_encode_ms=174.913 png_compress_ms=163.882 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
[v2.host_submission_breakdown] request_id=v2-benchmark-0-5e01eac1090a command_start_to_python_first_line_ms=150.875 python_first_line_to_local_receive_ms=264.111 local_receive_to_registry_start_ms=absent node_registry_init_ms=16949.802 registry_end_to_worker_start_ms=17.998 worker_start_to_plan_build_start_ms=0.0 plan_build_ms=78.0 plan_build_to_transport_entry_ms=5.998 transport_entry_to_handle_lookup_ms=1.001 handle_lookup_ms=13.0 payload_serialize_ms=0.0 generator_create_ms=13.0 generator_created_to_submission_ms=0.0 local_receive_to_submission_ms=17063.0 submission_boundary_source=first_anext first_remote_signal_ms=7248.352 scheduling_ms=3805.645 scheduling_source=modal_app_log
BATCH B ACCEPTANCE

Batch A preserved:
FAIL

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: skipped_generation_match
invoked: NO
reload ms: 0.0
generation check: YES
local only: NO

Snapshot hygiene:
enabled: 0
before RSS: n/a
after RSS: n/a
delta: n/a
trim status: n/a
manifest status: n/a

Stage 13:
gate: READY
expectation: 1
total: 79.3
children: 0
largest child: n/a=n/a
reconciliation: 79.3

Host telemetry:
overhead (Tier A): 14.7
Tier B forensic probe: n/a
total probe: 14.7
forensic trigger: NO

TOTAL WALL: 19236.4 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: FAIL

FAILED CHECKS:
  batch_a_preserved: validate_batch_a preserved 14/16 non-telemetry checks; fresh=YES, reconciliation_ms=-149.70566300000064 (hard cap 50 ms); host_telemetry_overhead/host_slow_forensic re-evaluated under the Batch-B Tier-A/Tier-B contract
  runtime_state_guard: evidence='decision, invoked, reload_ms, generation_check', decision='skipped_generation_match', invoked=False (source: exact), reload_ms=0.0, generation_check=True, local_only=False (reload_runtime_state_start event present); FAILED: generation check is not local: reload_runtime_state_start event present
  stage13_breakdown: largest_child=n/a, reconciliation=79.321 ms; FAILED: children list missing; sum(children)=0 does not reconcile stage13_total=79.321 (delta 79.321 ms > tolerance 10 ms)
Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8679, in <module>
    asyncio.run(_run_main_with_drain_teardown())
  File "C:\Program Files\Python311\Lib\asyncio\runners.py", line 190, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "C:\Program Files\Python311\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Program Files\Python311\Lib\asyncio\base_events.py", line 654, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8639, in _run_main_with_drain_teardown
    await main(
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8261, in main
    raise RuntimeError("batch-b acceptance: RUN 1 FAILED Batch-B gates")
RuntimeError: batch-b acceptance: RUN 1 FAILED Batch-B gates
Cannot connect to comfyregistry.
FETCH DATA from: https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json[ComfyUI-Manager] Due to a network error, switching to local mode.
=> custom-node-list.json
=> cannot schedule new futures after shutdown
FETCH DATA from: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-manager\custom-node-list.json [DONE]
=== ERROR: Benchmark failed ===
=== Total command-to-response time: 43.626s ===

`

## B. v2_batchb_run1b_console.log — RUN 1B (incomplete flags; PASS)

`
[v2.env_profile]
env_profile=inherit
thread_policy=TBASE
snapshot_model_order=O0
baseline_cpu_request=12
baseline_memory_request=32768
memory_request_mb=32768
vae_policy=v1
release_gpu_after_request=0
cpu_model_snapshot=1
native_fast_disk_unet=1
publish_restore_plan=0
vae_snapshot=1
clip_conditioning_cache=1
unet_activation_mode=late
vae_activation_mode=sampling_end
persistent_local_handle=1
full_trace=0
residency_diagnostics=0
deep_model_diag=0
pagefault_tracking=0
eviction_enabled=0
eviction_role=none
eviction_idle_seconds=0
prefill_lanes=critical
prefill_wait_for_unet=0
restore_torch_threads=none
variance_pretouch=0
volume_read_run_count=3
restore_only_app=stable-modal-comfy-v2-restore-only-shadow
restore_only_run_count=6
snapshot_exclude_unet=
=== Running one V2 benchmark trial against the existing deployment ===
=== Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
[v2.host] python_first_line_wall_unix_ns=1786726310157526800
{"guard": {"allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768, "changed_axes": []}, "runtime_shape": {"cpu_request": 12, "malloc_arena_max": null, "memory_request": 32768, "mkl_num_threads": null, "numexpr_num_threads": null, "omp_num_threads": null, "openblas_num_threads": null, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "snapshot_model_order": "O0", "thread_policy": "TBASE", "torch_interop_threads": null, "torch_intraop_threads": null}}
run_v2_single.bat : WARNING:root:WARNING: You need pytorch with cu130 or higher to use optimized CUDA operations.
At line:1 char:234
+ ... CH_B_EXPECT_SLOW_H2D_FORENSIC='1'; & .\run_v2_single.bat 2>&1 | Tee-O ...
+                                        ~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (WARNING:root:WA...UDA operations.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[v2.harness] prompt_server_mirror instance_set=True
WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

Package diffusers installed failed
Package diffusers installed failed
[33mModule 'diffusers' load failed. If you don't have it installed, do it:[0m
[33mpip install diffusers[0m
[34m[ComfyUI-Easy-Use] server: [0mv1.3.6 [92mLoaded[0m
[34m[ComfyUI-Easy-Use] web root: [0mC:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-easy-use\web_version/v2 [92mLoaded[0m
[exact_prefill.local] enabled=1 source=env
[timing_trace] module loaded __file__=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\timing_trace.py TRACE_VERSION=2.0.0
[timing_trace] module directory in sys.path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\__init__.py", line 7, in <module>
    from .src.interfaces import comfy_entrypoint, SeedVR2Extension
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\__init__.py", line 8, in <module>
    from .video_upscaler import SeedVR2VideoUpscaler
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\video_upscaler.py", line 10, in <module>
    from ..utils.downloads import download_weight
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\downloads.py", line 14, in <module>
    from .model_registry import MODEL_REGISTRY, DEFAULT_VAE
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\model_registry.py", line 12, in <module>
    from ..models.dit_3b.nadit import NaDiT as NaDiT3B
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\nadit.py", line 24, in <module>
    from .embedding import TimeEmbedding
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\embedding.py", line 17, in <module>
    from diffusers.models.embeddings import get_timestep_embedding
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\__init__.py", line 3, in <module>
    from .configuration_utils import ConfigMixin
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\configuration_utils.py", line 34, in 
<module>
    from .utils import DIFFUSERS_CACHE, HUGGINGFACE_CO_RESOLVE_ENDPOINT, DummyObject, deprecate, logging
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\__init__.py", line 37, in 
<module>
    from .dynamic_modules_utils import get_class_from_dynamic_module
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\dynamic_modules_utils.py", line 
29, in <module>
    from huggingface_hub import HfFolder, cached_download, hf_hub_download, model_info
ImportError: cannot import name 'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler module for custom nodes: cannot import name 
'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ckpts path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using symlinks: False[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ort providers: ['CUDAExecutionProvider', 'DirectMLExecutionProvider', 'OpenVINOExecutionProvider', 
'ROCMExecutionProvider', 'CPUExecutionProvider', 'CoreMLExecutionProvider'][0m
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\node_wrappers\dwpose.py:26: UserWarning: DWPose: Onnxruntime not 
found or doesn't come with acceleration providers, switch to OpenCV with CPU device. DWPose might run very slowly
  warnings.warn("DWPose: Onnxruntime not found or doesn't come with acceleration providers, switch to OpenCV with CPU 
device. DWPose might run very slowly")
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\__init__.py", line 2, in <module>
    from .nodes.ai.FL_Fal_Gemini_ImageEdit import FL_Fal_Gemini_ImageEdit
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\nodes\ai\FL_Fal_Gemini_ImageEdit.py", line 10, in <module>
    import fal_client
ModuleNotFoundError: No module named 'fal_client'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes module for custom nodes: No module named 'fal_client'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_sam3\__init__.py", 
line 11, in <module>
    from .src.comfyui_sam3.nodes import NODE_CLASS_MAPPINGS
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3\src\comfyui_sam3\nodes.py", line 6, in <module>
    from sam3.model_builder import build_sam3_image_model, build_sam3_video_model
ModuleNotFoundError: No module named 'sam3'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3 module for custom nodes: No module named 'sam3'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1073, in get_code
  File "<frozen importlib._bootstrap_external>", line 1130, in get_data
FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comyui-modal-pagesfile-probe module for custom nodes: [Errno 2] No such file or 
directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*, /comfymodal/history-v2/feed, /comfymodal/history-v2/generations/{id}/*, /comfymodal/history-v2/experiments/{id}/*, /comfymodal/history-v2/assets/{id}
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
ΓÜá∩╕Å  SeedVR2 optimizations check: SageAttention Γ¥î | Flash Attention Γ¥î | Triton Γ¥î
≡ƒÆí For best performance: pip install sageattention flash-attn triton
≡ƒôè Initial CUDA memory: 6.91GB free / 8.00GB total
### ComfyUI-Workflow-Encrypt: Copy .js from 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-workflow-encrypt\js\comfyui-workflow-encrypt.js' to 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\web\extensions\comfyui-workflow-encrypt'
# ≡ƒÿ║dzNodes: LayerStyle -> [1;33mCannot import name 'guidedFilter' from 'cv2.ximgproc'
A few nodes cannot works properly, while most nodes are not affected. Please REINSTALL package 'opencv-contrib-python'.
For detail refer to [4mhttps://github.com/chflame163/ComfyUI_LayerStyle/issues/5[0m[m
(RES4LYF) Init
(RES4LYF) Importing beta samplers.
(RES4LYF) Importing legacy samplers.

[92m[rgthree-comfy] Loaded 48 magnificent nodes. ≡ƒÄë[0m

[33m[rgthree-comfy] ComfyUI's new Node 2.0 rendering may be incompatible with some rgthree-comfy nodes and features, breaking some rendering as well as losing the ability to access a node's properties (a vital part of many nodes). It also appears to run MUCH more slowly spiking CPU usage and causing jankiness and unresponsiveness, especially with large workflows. Personally I am not planning to use the new Nodes 2.0 and, unfortunately, am not able to invest the time to investigate and overhaul rgthree-comfy where needed. If you have issues when Nodes 2.0 is enabled, I'd urge you to switch it off as well and join me in hoping ComfyUI is not planning to deprecate the existing, stable canvas rendering all together.
[0m
[v2.harness] production_output_registered output=True comparer=True
[v2.harness] node_registry_initialized classes=2192
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=miss
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-0-39e1e2601c00 local_receive_to_worker_start_ms=16391.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16391.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16469.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] owner_ready pid=19496
[v2.local_handle] decision=persistent_hit
FETCH ComfyRegistry Data: 5/172
FETCH ComfyRegistry Data: 10/172
FETCH ComfyRegistry Data: 15/172
FETCH ComfyRegistry Data: 20/172
[v2.local_submission_breakdown] request_id=v2-benchmark-0-39e1e2601c00 local_receive_to_worker_start_ms=16391.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16391.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16469.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16469.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
FETCH ComfyRegistry Data: 25/172
FETCH ComfyRegistry Data: 30/172
FETCH ComfyRegistry Data: 35/172
[v2.request_origin] request_id=v2-benchmark-0-39e1e2601c00 trigger_source=benchmark local_prompt_enqueued_unix_ns=None local_prompt_ack_ready_unix_ns=None modal_generator_created_unix_ns=1786726326900085300 modal_submission_attempt_unix_ns=1786726326900085300 modal_first_event_received_unix_ns=1786726341066183600 modal_first_iteration_start_unix_ns=1786726326900085300 modal_first_remote_event_unix_ns=1786726341066183600 dispatch_to_modal_entry_ms=13770.074 local_receive_to_actual_submission_ms=16469.0 local_receive_to_result_return_ms=40983.164 t0_to_t1_ms=0.523 t1_to_queue_enqueue_ms=None local_receive_to_enqueue_ms=None queue_wait_before_worker_ms=None plan_build_ms=78.0 active_profile_ms=0.0 handle_lookup_ms=0.0 payload_serialize_ms=0.0 local_residual_ms=0.0 clock_reconciliation_residual_ms=0.0 route_unattributed_ms=None worker_unattributed_ms=None reconciliation_status=incomplete missing_stages=local_receive_to_enqueue_ms overlap_error= modal_input_id=in-01M00K092YE0D65BJ53FY23TFF:1786726327391-0 trigger_to_local_receive_ms=0.523 local_receive_to_generator_create_start_ms=16476.563 generator_create_ms=2.999 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=14166.098 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=886.743 restore_end_to_modal_method_entry_ms=17.313 modal_method_entry_to_executor_ms=941.157 submission_to_remote_python_resume_ms=12866.019 unexplained_pre_remote_ms=13262.043
[v2.remote_request_origin] request_id=v2-benchmark-0-39e1e2601c00 trigger_source=benchmark ui_trigger_unix_ms=1786726310420 local_receive_wall_unix_ns=1786726310420522752 local_receive_mono_ns=182434984000000 modal_generator_create_start_wall_unix_ns=1786726326897086100 modal_generator_create_start_mono_ns=182451453000000 modal_generator_created_wall_unix_ns=1786726326900085300 modal_generator_created_mono_ns=182451453000000 modal_first_iteration_start_wall_unix_ns=1786726326900085300 modal_first_iteration_start_mono_ns=182451453000000 modal_submission_attempt_wall_unix_ns=1786726326900085300 modal_submission_attempt_mono_ns=182451453000000 modal_first_remote_event_wall_unix_ns=1786726341066183600 modal_first_remote_event_mono_ns=182465625000000 modal_submission_boundary_source=first_iteration_proxy remote_python_resume_wall_unix_ns=1786726339766104064 restore_method_start_wall_unix_ns=1786726339766104064 restore_method_end_wall_unix_ns=1786726340652846848 modal_method_entry_wall_unix_ns=1786726340670159616 prompt_executor_invoke_start_wall_unix_ns=1786726341611316480 trigger_to_local_receive_ms=0.523 local_receive_to_generator_create_start_ms=16476.563 generator_create_ms=2.999 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=14166.098 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=886.743 restore_end_to_modal_method_entry_ms=17.313 modal_method_entry_to_executor_ms=941.157 submission_to_remote_python_resume_ms=12866.019 unexplained_pre_remote_ms=13262.043 modal_input_id=in-01M00K092YE0D65BJ53FY23TFF:1786726327391-0
[v2.local_submission_breakdown.final] request_id=v2-benchmark-0-39e1e2601c00 local_receive_to_worker_start_ms=16391.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16391.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16469.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16469.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent modal_submission_attempt_unix_ns=1786726326900085300 modal_generator_created_unix_ns=1786726326900085300 modal_first_iteration_start_unix_ns=1786726326900085300 modal_first_remote_event_unix_ns=1786726341066183600 dispatch_to_modal_entry_ms=13770.074 local_receive_to_actual_submission_ms=16469.0 local_receive_to_result_return_ms=40983.164
FETCH ComfyRegistry Data: 40/172
WATERFALL RECONCILIATION (local rebuild) replaced remote PARTIAL report with the full host-reconciled report
WATERFALL RECONCILIATION (local rebuild)
  command_to_response_ms            41413.7
  top_level_accounted_ms            38884.1
  global_residual_ms                -236.0
  global_residual_pct               -0.6
  reconciliation_status             EXCEEDS_TOLERANCE
  controllable_application_wall_ms  28783.6
  platform_wall_ms                  12866.0
  modal_restore_begin_unavailable   no
  OLD vs NEW accounted_ms 28783.6 -> 38884.1 | residual_ms -236.0 -> -236.0
production_adjusted_total_wall_ms=22268.584
[v2.experiment] saved=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_16-51-50\run_001_sample.json
{"run_index": 0, "request_id": "v2-benchmark-0-39e1e2601c00", "identity": {"app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint", "method_name": "run_plan_stream", "gpu": ["RTX-PRO-6000"], "cpu": 12, "memory_mb": 32768, "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "runtime_shape": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "stored_snapshot_model_order": "O0", "restore_count": 1, "request_count": 1, "restored_instance_id": "52210ee48a624f79953939f0f4aa9a22", "restore_session_id": "47473b77d01c4c7fb83a0c3df4257987", "container_task_id": "ta-01M00K09PKE7S8DKZ7CBMVZYGR", "modal_container_id": "", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "modal_input_id": "in-01M00K092YE0D65BJ53FY23TFF:1786726327391-0", "container_session_id": "fd1a0903d3904c6d"}, "runtime_shape": {"requested": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "deployed": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "observed": {"stage": "request_entry", "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "thread_policy": "TBASE", "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "native_thread_count": 53, "configured_omp": null, "configured_mkl": null, "configured_openblas": null, "configured_numexpr": null, "malloc_arena_max": null, "native_library_settings": {"OMP_NUM_THREADS": "12", "MKL_NUM_THREADS": "12", "OPENBLAS_NUM_THREADS": "12", "NUMEXPR_NUM_THREADS": null, "MALLOC_ARENA_MAX": null}, "torch_intraop_threads": 12, "torch_interop_threads": 14, "actual_torch_intraop_threads": 12, "actual_torch_interop_threads": 14, "requested_torch_intraop_threads": null, "requested_torch_interop_threads": null, "requested_vs_actual_match": true, "status": "baseline_passthrough", "error": "", "trace_id": "44013d2a964d402b", "pid": 2, "thread_native_id": 2, "restored_instance_id": "52210ee48a624f79953939f0f4aa9a22", "restore_session_id": "47473b77d01c4c7fb83a0c3df4257987", "legacy_container_session_id": "fd1a0903d3904c6d", "container_task_id": "ta-01M00K09PKE7S8DKZ7CBMVZYGR", "modal_input_id": "in-01M00K092YE0D65BJ53FY23TFF:1786726327391-0", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint"}, "stored_snapshot_model_order": "O0", "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "guard": {"changed_axes": [], "allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768}, "construction_order_semantics": "model_construction_order_only"}, "timing": {"wall_ms": 24525.7, "handle_lookup_ms": 2.999, "submission_to_first_remote_event_ms": 14166.098, "command_to_response_ms": 41413.7, "submit2entry_ms": 13773.074, "t3b_to_t8_ms": 9986.574, "restore_total_ms": 294.196, "pre_sampler_ms": 4907.735, "sampler_ms": 3666.289, "vae_decode_ms": 393.361, "output_collection_ms": 8.272, "snapshot_callback_age_at_restore_ms": 960175.159, "snapshot_callback_to_command_start_ms": 929821.297, "command_start_to_restore_start_ms": 29762.104, "local_timing": {"t0_to_t1_ms": 0.523, "t1_to_queue_enqueue_ms": null, "local_receive_to_enqueue_ms": null, "local_body_read_ms": null, "local_json_parse_ms": null, "local_preflight_ms": null, "local_queue_lock_wait_ms": null, "local_queue_enqueue_ms": null, "queue_wait_before_worker_ms": null, "plan_build_ms": 78.0, "active_profile_ms": 0.0, "restore_plan_build_ms": null, "restore_publish_ms": null, "handle_lookup_ms": 0.0, "payload_serialize_ms": 0.0, "payload_materialization_ms": 0.0, "payload_size_measurement_ms": 0.0, "generator_create_ms": 2.999, "local_residual_ms": 0.0, "clock_reconciliation_residual_ms": 0.0, "route_unattributed_ms": null, "worker_unattributed_ms": null, "reconciliation_status": "incomplete", "missing_stages": ["local_receive_to_enqueue_ms"], "overlap_error": "", "stage_attribution_residual_ms": {"route_unattributed_ms": null, "worker_unattributed_ms": null, "missing_stages": ["local_receive_to_enqueue_ms"], "reconciliation_status": "incomplete", "overlap_error": ""}, "local_receive_to_generator_create_ms": 16469.0, "generator_create_to_first_iteration_ms": 0.0, "first_iteration_to_first_remote_event_ms": 14166.098, "local_receive_to_actual_submission_ms": 16469.0, "trigger_to_local_receive_ms": 0.523, "local_receive_to_generator_create_start_ms": 16476.563, "generator_created_to_first_iteration_ms": 0.0, "remote_python_resume_to_restore_start_ms": 0.0, "restore_method_ms": 886.743, "restore_end_to_modal_method_entry_ms": 17.313, "modal_method_entry_to_executor_ms": 941.157, "submission_to_remote_python_resume_ms": 12866.019, "unexplained_pre_remote_ms": 13262.043, "local_result_received_wall_ns": 1786726351403687000, "local_result_received_mono_ns": 182475953000000, "local_receive_to_result_return_ms": 40983.164, "result_received_to_return_ms": 12.999, "remote_result_emit_wall_unix_ns": 1786726351639370797, "remote_result_emit_to_local_receipt_ms": null, "caller_return_wall_unix_ns": 1786726351417686200, "caller_return_mono_ns": 182475968000000, "local_result_received_to_caller_return_ms": 15.0, "modal_restore_begin_wall_unix_ns": null}, "restore_breakdown": {"restore_total_ms": 294.196, "models_symlink_ms": 3.44, "manager_offline_ms": 1.18, "reload_models_ms": 0.0, "reload_runtime_state_ms": 0.0, "v2_startup_custom_node_source_copy_ms": 367.16, "sync_custom_nodes_ms": 367.3, "install_requirements_ms": 0.01, "v2_startup_comfyui_path_startup_ms": 0.34, "comfyui_path_setup_ms": 0.49, "v2_startup_backend_startup_ms": 19953.37, "backend_startup_ms": 19954.11, "observe_generations_ms": 0.83, "snapshot_restore_ms": 266.47, "snapshot_callback_age_at_restore_ms": 960175.159, "restore_gpu_state_ms": 234.287, "cuda_init_ms": 4.81, "v2_startup_snapshot_execution_seed_ms": 1.01, "initialize_cuda_ms": 4.751, "snapshot_identity_checks_ms": 0.0, "cpu_snapshot_retargeting_ms": 0.0, "folder_warm_ms": 2592.77}, "early_activation_total_ms": null, "queue_delay_ms": null, "cpu_snapshot_wait_ms": null, "dtype_layout_preparation_ms": null, "post_load_bookkeeping_ms": null, "submission_to_remote_python_resume_ms": 12866.019, "remote_python_resume_to_restore_start_ms": 0.0, "restore_to_method_entry_ms": 17.313, "method_entry_to_first_remote_event_ms": 396.024, "first_remote_event_to_final_result_ms": 10337.503, "transfer_queue_delay_ms": null, "synchronized_transfer_ms": null, "quiesce_wait_ms": null, "graph_activity_ms": 3607.997, "sampler_lane_wait_ms": 0.079, "quiesced_transfer": null}}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-39e1e2601c00  Instance: 52210ee48a624f79953939f0f4aa9a22  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east4
TOTAL WALL:           38.648s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    41.414s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 416.523 ms | 416.523 ms |   1.078% | #                                        |
|   2 | Modal handle and submission                    |    16.480s |    16.896s |  42.640% | #################                        |
|   3 | Modal pre-Python snapshot restoration          |    10.100s |    26.997s |  26.134% | ##########                               |
|   4 | Python/application restore                     | 886.740 ms |    27.883s |   2.294% | #                                        |
|   5 | Restore-to-method entry                        |  17.312 ms |    27.901s |   0.045% | #                                        |
|   6 | Remote method setup                            | 941.213 ms |    28.842s |   2.435% | #                                        |
|     |   method entry to graph start                  | 875.718 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 875.677 ms |            |          |                                          |
|     |   graph setup                                  |  65.495 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  12.646 ms |    28.854s |   0.033% | #                                        |
|   8 | Pre-sampler execution                          |     3.595s |    32.450s |   9.303% | ####                                     |
|     |   Conditioning cache exact_hit lookup=39.946ms |  39.946 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 562.447 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  39.091 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 122.288 ms |            |          |                                          |
|     |   Checkpoint read                              |     2.004s |            |          |                                          |
|     |   Read end -> construction done                |   0.499 ms |            |          |                                          |
|     |   UNET get_model                               |  68.160 ms |            |          |                                          |
|     |   Bind                                         |  27.373 ms |            |          |                                          |
|     |   Synchronized H2D (5.2 GB/s)                  |     2.369s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.442 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 115.269 ms |    32.565s |   0.298% | #                                        |
|     |   lane acquired to actual stage                | 115.244 ms |            |          |                                          |
|  10 | Sampling                                       |     4.831s |    37.396s |  12.501% | #####                                    |
|  11 | Post-sampling / VAE transition                 | 837.286 ms |    38.234s |   2.166% | #                                        |
|  12 | VAE decode                                     | 393.361 ms |    38.627s |   1.018% | #                                        |
|     |   VAE load/H2D                                 | 867.879 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 242.189 ms |    38.869s |   0.627% | #                                        |
|     |   PNG encode                                   | 171.343 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  15.000 ms |    38.884s |   0.039% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     2.766s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.298 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.prompt_executor_breakdown] request_id=v2-benchmark-0-39e1e2601c00 exec_to_cached_ms=11.447 dynamic_prompt_ms=0.003 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.018 cache_gather_ms=0.069 cleanup_gc_ms=1.007 residual_ms=10.35 c2f_cached_to_first_node_ms=0.65 c2f_topo_walk_ms=0.518 c2f_topo_input_info_ms=0.113 c2f_topo_other_ms=0.405 c2f_stage_ms=1.221 c2f_first_node_prefix_ms=0.148 c2f_residual_ms=-1.237 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=8ffd5d7760804fa9ba99b1419063ecd931de3044a0f30a33c8a000a3197235c9 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.632 topo_lazy_hits=36
[v2.conditioning_exact_hit_breakdown] request_id=v2-benchmark-0-39e1e2601c00 decision=exact_hit lookup_wall_ms=39.946 total_ms=39.678 key_build_ms=0.189 lock_wait_ms=0.002 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=34 entry_lookup_ms=27.497 header_bytes=3752 data_bytes=2900184 lru_touch_ms=11.722 lru_touch_mode=sync children_ms=39.41 residual_ms=0.268 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=7.804 prefetch_join_timeout=0 prefetch_overlap_ms=39.855 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=529.535 volume_reload_ms=0.0
[v2.folder_warm] request_id=v2-benchmark-0-39e1e2601c00 folder_warm_ms=2592.77 folder_warm_folders=29
[v2.input_types_warm] request_id=v2-benchmark-0-39e1e2601c00 input_types_warm_ms=1246.303 input_types_warm_classes=31
[v2.png_output] request_id=v2-benchmark-0-39e1e2601c00 compress_level=1 png_encode_ms=171.339 png_compress_ms=166.844 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
[v2.host_submission_breakdown] request_id=v2-benchmark-0-39e1e2601c00 command_start_to_python_first_line_ms=153.527 python_first_line_to_local_receive_ms=262.996 local_receive_to_registry_start_ms=0.0 node_registry_init_ms=16379.561 registry_end_to_worker_start_ms=18.0 worker_start_to_plan_build_start_ms=1.0 plan_build_ms=78.0 plan_build_to_transport_entry_ms=5.002 transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=2.999 payload_serialize_ms=0.0 generator_create_ms=2.999 generator_created_to_submission_ms=0.0 local_receive_to_submission_ms=16469.0 submission_boundary_source=first_anext first_remote_signal_ms=14166.098 scheduling_ms=2765.541 scheduling_source=modal_app_log
BATCH B ACCEPTANCE

Batch A preserved:
PASS

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: skipped_generation_match
invoked: NO
reload ms: 0.0
generation check: YES
local only: YES

Snapshot hygiene:
enabled: 0
before RSS: n/a
after RSS: n/a
delta: n/a
trim status: n/a
manifest status: n/a

Stage 13:
gate: READY
expectation: 1
total: 72.7
children: 8
largest child: waterfall_build_ms=38.5
reconciliation: 0.0

Host telemetry:
overhead (Tier A): 10.7
Tier B forensic probe: n/a
total probe: 10.7
forensic trigger: NO

TOTAL WALL: 24525.7 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: PASS
{
  "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\comfymodal-data\\benchmarks\\runs\\v2_2026-08-14_16-51-50",
  "target": {
    "app_name": "stable-modal-comfy-v2-restore-only-shadow",
    "class_name": "ModalRuntimeEntrypointV2",
    "gpu": "rtx-pro-6000"
  },
  "runtime_shape": {
    "requested": {
      "thread_policy": "TBASE",
      "torch_intraop_threads": null,
      "torch_interop_threads": null,
      "omp_num_threads": null,
      "mkl_num_threads": null,
      "openblas_num_threads": null,
      "numexpr_num_threads": null,
      "malloc_arena_max": null,
      "snapshot_model_order": "O0",
      "cpu_request": 12,
      "memory_request": 32768,
      "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
      "runtime_shape_label": null
    },
    "guard": {
      "changed_axes": [],
      "allow_multi_axis": false,
      "baseline_cpu_request": 12,
      "baseline_memory_request": 32768
    }
  },
  "run_count": 1,
  "gap_seconds": 35.0,
  "trace_handoff_errors": 0,
  "waterfall_runs": 1,
  "runs": [
    {
      "run_index": 0,
      "request_id": "v2-benchmark-0-39e1e2601c00",
      "identity": {
        "app_name": "stable-modal-comfy-v2-restore-only-shadow",
        "class_name": "ModalRuntimeEntrypoint",
        "method_name": "run_plan_stream",
        "gpu": [
          "RTX-PRO-6000"
        ],
        "cpu": 12,
        "memory_mb": 32768,
        "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce",
        "runtime_shape": {
          "thread_policy": "TBASE",
          "torch_intraop_threads": null,
          "torch_interop_threads": null,
          "omp_num_threads": null,
          "mkl_num_threads": null,
          "openblas_num_threads": null,
          "numexpr_num_threads": null,
          "malloc_arena_max": null,
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null
        },
        "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
        "runtime_shape_label": null,
        "stored_snapshot_model_order": "O0",
        "restore_count": 1,
        "request_count": 1,
        "restored_instance_id": "52210ee48a624f79953939f0f4aa9a22",
        "restore_session_id": "47473b77d01c4c7fb83a0c3df4257987",
        "container_task_id": "ta-01M00K09PKE7S8DKZ7CBMVZYGR",
        "modal_container_id": "",
        "image_id": "im-B1LdSHCggPdDMnEPTU8kop",
        "cloud": "CLOUD_PROVIDER_GCP",
        "region": "us-east4",
        "modal_input_id": "in-01M00K092YE0D65BJ53FY23TFF:1786726327391-0",
        "container_session_id": "fd1a0903d3904c6d"
      },
      "runtime_shape": {
        "requested": {
          "thread_policy": "TBASE",
          "torch_intraop_threads": null,
          "torch_interop_threads": null,
          "omp_num_threads": null,
          "mkl_num_threads": null,
          "openblas_num_threads": null,
          "numexpr_num_threads": null,
          "malloc_arena_max": null,
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null
        },
        "deployed": {
          "thread_policy": "TBASE",
          "torch_intraop_threads": null,
          "torch_interop_threads": null,
          "omp_num_threads": null,
          "mkl_num_threads": null,
          "openblas_num_threads": null,
          "numexpr_num_threads": null,
          "malloc_arena_max": null,
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null
        },
        "observed": {
          "stage": "request_entry",
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null,
          "thread_policy": "TBASE",
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "native_thread_count": 53,
          "configured_omp": null,
          "configured_mkl": null,
          "configured_openblas": null,
          "configured_numexpr": null,
          "malloc_arena_max": null,
          "native_library_settings": {
            "OMP_NUM_THREADS": "12",
            "MKL_NUM_THREADS": "12",
            "OPENBLAS_NUM_THREADS": "12",
            "NUMEXPR_NUM_THREADS": null,
            "MALLOC_ARENA_MAX": null
          },
          "torch_intraop_threads": 12,
          "torch_interop_threads": 14,
          "actual_torch_intraop_threads": 12,
          "actual_torch_interop_threads": 14,
          "requested_torch_intraop_threads": null,
          "requested_torch_interop_threads": null,
          "requested_vs_actual_match": true,
          "status": "baseline_passthrough",
          "error": "",
          "trace_id": "44013d2a964d402b",
          "pid": 2,
          "thread_native_id": 2,
          "restored_instance_id": "52210ee48a624f79953939f0f4aa9a22",
          "restore_session_id": "47473b77d01c4c7fb83a0c3df4257987",
          "legacy_container_session_id": "fd1a0903d3904c6d",
          "container_task_id": "ta-01M00K09PKE7S8DKZ7CBMVZYGR",
          "modal_input_id": "in-01M00K092YE0D65BJ53FY23TFF:1786726327391-0",
          "image_id": "im-B1LdSHCggPdDMnEPTU8kop",
          "cloud": "CLOUD_PROVIDER_GCP",
          "region": "us-east4",
          "app_name": "stable-modal-comfy-v2-restore-only-shadow",
          "class_name": "ModalRuntimeEntrypoint"
        },
        "stored_snapshot_model_order": "O0",
        "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce",
        "guard": {
          "changed_axes": [],
          "allow_multi_axis": false,
          "baseline_cpu_request": 12,
          "baseline_memory_request": 32768
        },
        "construction_order_semantics": "model_construction_order_only"
      },
      "timing": {
        "wall_ms": 24525.7,
        "handle_lookup_ms": 2.999,
        "submission_to_first_remote_event_ms": 14166.098,
        "command_to_response_ms": 41413.7,
        "submit2entry_ms": 13773.074,
        "t3b_to_t8_ms": 9986.574,
        "restore_total_ms": 294.196,
        "pre_sampler_ms": 4907.735,
        "sampler_ms": 3666.289,
        "vae_decode_ms": 393.361,
        "output_collection_ms": 8.272,
        "snapshot_callback_age_at_restore_ms": 960175.159,
        "snapshot_callback_to_command_start_ms": 929821.297,
        "command_start_to_restore_start_ms": 29762.104,
        "local_timing": {
          "t0_to_t1_ms": 0.523,
          "t1_to_queue_enqueue_ms": null,
          "local_receive_to_enqueue_ms": null,
          "local_body_read_ms": null,
          "local_json_parse_ms": null,
          "local_preflight_ms": null,
          "local_queue_lock_wait_ms": null,
          "local_queue_enqueue_ms": null,
          "queue_wait_before_worker_ms": null,
          "plan_build_ms": 78.0,
          "active_profile_ms": 0.0,
          "restore_plan_build_ms": null,
          "restore_publish_ms": null,
          "handle_lookup_ms": 0.0,
          "payload_serialize_ms": 0.0,
          "payload_materialization_ms": 0.0,
          "payload_size_measurement_ms": 0.0,
          "generator_create_ms": 2.999,
          "local_residual_ms": 0.0,
          "clock_reconciliation_residual_ms": 0.0,
          "route_unattributed_ms": null,
          "worker_unattributed_ms": null,
          "reconciliation_status": "incomplete",
          "missing_stages": [
            "local_receive_to_enqueue_ms"
          ],
          "overlap_error": "",
          "stage_attribution_residual_ms": {
            "route_unattributed_ms": null,
            "worker_unattributed_ms": null,
            "missing_stages": [
              "local_receive_to_enqueue_ms"
            ],
            "reconciliation_status": "incomplete",
            "overlap_error": ""
          },
          "local_receive_to_generator_create_ms": 16469.0,
          "generator_create_to_first_iteration_ms": 0.0,
          "first_iteration_to_first_remote_event_ms": 14166.098,
          "local_receive_to_actual_submission_ms": 16469.0,
          "trigger_to_local_receive_ms": 0.523,
          "local_receive_to_generator_create_start_ms": 16476.563,
          "generator_created_to_first_iteration_ms": 0.0,
          "remote_python_resume_to_restore_start_ms": 0.0,
          "restore_method_ms": 886.743,
          "restore_end_to_modal_method_entry_ms": 17.313,
          "modal_method_entry_to_executor_ms": 941.157,
          "submission_to_remote_python_resume_ms": 12866.019,
          "unexplained_pre_remote_ms": 13262.043,
          "local_result_received_wall_ns": 1786726351403687000,
          "local_result_received_mono_ns": 182475953000000,
          "local_receive_to_result_return_ms": 40983.164,
          "result_received_to_return_ms": 12.999,
          "remote_result_emit_wall_unix_ns": 1786726351639370797,
          "remote_result_emit_to_local_receipt_ms": null,
          "caller_return_wall_unix_ns": 1786726351417686200,
          "caller_return_mono_ns": 182475968000000,
          "local_result_received_to_caller_return_ms": 15.0,
          "modal_restore_begin_wall_unix_ns": null
        },
        "restore_breakdown": {
          "restore_total_ms": 294.196,
          "models_symlink_ms": 3.44,
          "manager_offline_ms": 1.18,
          "reload_models_ms": 0.0,
          "reload_runtime_state_ms": 0.0,
          "v2_startup_custom_node_source_copy_ms": 367.16,
          "sync_custom_nodes_ms": 367.3,
          "install_requirements_ms": 0.01,
          "v2_startup_comfyui_path_startup_ms": 0.34,
          "comfyui_path_setup_ms": 0.49,
          "v2_startup_backend_startup_ms": 19953.37,
          "backend_startup_ms": 19954.11,
          "observe_generations_ms": 0.83,
          "snapshot_restore_ms": 266.47,
          "snapshot_callback_age_at_restore_ms": 960175.159,
          "restore_gpu_state_ms": 234.287,
          "cuda_init_ms": 4.81,
          "v2_startup_snapshot_execution_seed_ms": 1.01,
          "initialize_cuda_ms": 4.751,
          "snapshot_identity_checks_ms": 0.0,
          "cpu_snapshot_retargeting_ms": 0.0,
          "folder_warm_ms": 2592.77
        },
        "early_activation_total_ms": null,
        "queue_delay_ms": null,
        "cpu_snapshot_wait_ms": null,
        "dtype_layout_preparation_ms": null,
        "post_load_bookkeeping_ms": null,
        "submission_to_remote_python_resume_ms": 12866.019,
        "remote_python_resume_to_restore_start_ms": 0.0,
        "restore_to_method_entry_ms": 17.313,
        "method_entry_to_first_remote_event_ms": 396.024,
        "first_remote_event_to_final_result_ms": 10337.503,
        "transfer_queue_delay_ms": null,
        "synchronized_transfer_ms": null,
        "quiesce_wait_ms": null,
        "graph_activity_ms": 3607.997,
        "sampler_lane_wait_ms": 0.079,
        "quiesced_transfer": null
      }
    }
  ]
}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-39e1e2601c00  Instance: 52210ee48a624f79953939f0f4aa9a22  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east4
TOTAL WALL:           38.648s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    41.414s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 416.523 ms | 416.523 ms |   1.078% | #                                        |
|   2 | Modal handle and submission                    |    16.480s |    16.896s |  42.640% | #################                        |
|   3 | Modal pre-Python snapshot restoration          |    10.100s |    26.997s |  26.134% | ##########                               |
|   4 | Python/application restore                     | 886.740 ms |    27.883s |   2.294% | #                                        |
|   5 | Restore-to-method entry                        |  17.312 ms |    27.901s |   0.045% | #                                        |
|   6 | Remote method setup                            | 941.213 ms |    28.842s |   2.435% | #                                        |
|     |   method entry to graph start                  | 875.718 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 875.677 ms |            |          |                                          |
|     |   graph setup                                  |  65.495 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  12.646 ms |    28.854s |   0.033% | #                                        |
|   8 | Pre-sampler execution                          |     3.595s |    32.450s |   9.303% | ####                                     |
|     |   Conditioning cache exact_hit lookup=39.946ms |  39.946 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 562.447 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  39.091 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 122.288 ms |            |          |                                          |
|     |   Checkpoint read                              |     2.004s |            |          |                                          |
|     |   Read end -> construction done                |   0.499 ms |            |          |                                          |
|     |   UNET get_model                               |  68.160 ms |            |          |                                          |
|     |   Bind                                         |  27.373 ms |            |          |                                          |
|     |   Synchronized H2D (5.2 GB/s)                  |     2.369s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.442 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 115.269 ms |    32.565s |   0.298% | #                                        |
|     |   lane acquired to actual stage                | 115.244 ms |            |          |                                          |
|  10 | Sampling                                       |     4.831s |    37.396s |  12.501% | #####                                    |
|  11 | Post-sampling / VAE transition                 | 837.286 ms |    38.234s |   2.166% | #                                        |
|  12 | VAE decode                                     | 393.361 ms |    38.627s |   1.018% | #                                        |
|     |   VAE load/H2D                                 | 867.879 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 242.189 ms |    38.869s |   0.627% | #                                        |
|     |   PNG encode                                   | 171.343 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  15.000 ms |    38.884s |   0.039% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     2.766s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.298 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.experiment] campaign manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_16-51-50\campaign_manifest.json
FETCH ComfyRegistry Data: 45/172
Cannot connect to comfyregistry.
FETCH DATA from: https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json[ComfyUI-Manager] Due to a network error, switching to local mode.
=> custom-node-list.json
=> cannot schedule new futures after shutdown
FETCH DATA from: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-manager\custom-node-list.json [DONE]
=== Single V2 benchmark completed ===
=== Total command-to-response time: 51.869s ===

`

## C. v2_batchb_run1c_console.log — RUN 1C strict RUN 1 (PASS)

`
[v2.env_profile]
env_profile=inherit
thread_policy=TBASE
snapshot_model_order=O0
baseline_cpu_request=12
baseline_memory_request=32768
memory_request_mb=32768
vae_policy=v1
release_gpu_after_request=0
cpu_model_snapshot=1
native_fast_disk_unet=1
publish_restore_plan=0
vae_snapshot=1
clip_conditioning_cache=1
unet_activation_mode=late
vae_activation_mode=sampling_end
persistent_local_handle=1
full_trace=0
residency_diagnostics=0
deep_model_diag=0
pagefault_tracking=0
eviction_enabled=0
eviction_role=none
eviction_idle_seconds=0
prefill_lanes=critical
prefill_wait_for_unet=0
restore_torch_threads=none
variance_pretouch=0
volume_read_run_count=3
restore_only_app=stable-modal-comfy-v2-restore-only-shadow
restore_only_run_count=6
snapshot_exclude_unet=
=== Running one V2 benchmark trial against the existing deployment ===
=== Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
[v2.host] python_first_line_wall_unix_ns=1786726389791875500
{"guard": {"allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768, "changed_axes": []}, "runtime_shape": {"cpu_request": 12, "malloc_arena_max": null, "memory_request": 32768, "mkl_num_threads": null, "numexpr_num_threads": null, "omp_num_threads": null, "openblas_num_threads": null, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "snapshot_model_order": "O0", "thread_policy": "TBASE", "torch_interop_threads": null, "torch_intraop_threads": null}}
run_v2_single.bat : WARNING:root:WARNING: You need pytorch with cu130 or higher to use optimized CUDA operations.
At line:1 char:327
+ ... MFYMODAL_V2_SNAPSHOT_MANIFEST='1'; & .\run_v2_single.bat 2>&1 | Tee-O ...
+                                        ~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (WARNING:root:WA...UDA operations.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[v2.harness] prompt_server_mirror instance_set=True
WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

Package diffusers installed failed
Package diffusers installed failed
[33mModule 'diffusers' load failed. If you don't have it installed, do it:[0m
[33mpip install diffusers[0m
[34m[ComfyUI-Easy-Use] server: [0mv1.3.6 [92mLoaded[0m
[34m[ComfyUI-Easy-Use] web root: [0mC:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-easy-use\web_version/v2 [92mLoaded[0m
[exact_prefill.local] enabled=1 source=env
[timing_trace] module loaded __file__=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\timing_trace.py TRACE_VERSION=2.0.0
[timing_trace] module directory in sys.path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\__init__.py", line 7, in <module>
    from .src.interfaces import comfy_entrypoint, SeedVR2Extension
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\__init__.py", line 8, in <module>
    from .video_upscaler import SeedVR2VideoUpscaler
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\video_upscaler.py", line 10, in <module>
    from ..utils.downloads import download_weight
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\downloads.py", line 14, in <module>
    from .model_registry import MODEL_REGISTRY, DEFAULT_VAE
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\model_registry.py", line 12, in <module>
    from ..models.dit_3b.nadit import NaDiT as NaDiT3B
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\nadit.py", line 24, in <module>
    from .embedding import TimeEmbedding
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\embedding.py", line 17, in <module>
    from diffusers.models.embeddings import get_timestep_embedding
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\__init__.py", line 3, in <module>
    from .configuration_utils import ConfigMixin
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\configuration_utils.py", line 34, in 
<module>
    from .utils import DIFFUSERS_CACHE, HUGGINGFACE_CO_RESOLVE_ENDPOINT, DummyObject, deprecate, logging
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\__init__.py", line 37, in 
<module>
    from .dynamic_modules_utils import get_class_from_dynamic_module
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\dynamic_modules_utils.py", line 
29, in <module>
    from huggingface_hub import HfFolder, cached_download, hf_hub_download, model_info
ImportError: cannot import name 'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler module for custom nodes: cannot import name 
'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ckpts path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using symlinks: False[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ort providers: ['CUDAExecutionProvider', 'DirectMLExecutionProvider', 'OpenVINOExecutionProvider', 
'ROCMExecutionProvider', 'CPUExecutionProvider', 'CoreMLExecutionProvider'][0m
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\node_wrappers\dwpose.py:26: UserWarning: DWPose: Onnxruntime not 
found or doesn't come with acceleration providers, switch to OpenCV with CPU device. DWPose might run very slowly
  warnings.warn("DWPose: Onnxruntime not found or doesn't come with acceleration providers, switch to OpenCV with CPU 
device. DWPose might run very slowly")
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\__init__.py", line 2, in <module>
    from .nodes.ai.FL_Fal_Gemini_ImageEdit import FL_Fal_Gemini_ImageEdit
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\nodes\ai\FL_Fal_Gemini_ImageEdit.py", line 10, in <module>
    import fal_client
ModuleNotFoundError: No module named 'fal_client'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes module for custom nodes: No module named 'fal_client'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_sam3\__init__.py", 
line 11, in <module>
    from .src.comfyui_sam3.nodes import NODE_CLASS_MAPPINGS
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3\src\comfyui_sam3\nodes.py", line 6, in <module>
    from sam3.model_builder import build_sam3_image_model, build_sam3_video_model
ModuleNotFoundError: No module named 'sam3'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3 module for custom nodes: No module named 'sam3'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1073, in get_code
  File "<frozen importlib._bootstrap_external>", line 1130, in get_data
FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comyui-modal-pagesfile-probe module for custom nodes: [Errno 2] No such file or 
directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*, /comfymodal/history-v2/feed, /comfymodal/history-v2/generations/{id}/*, /comfymodal/history-v2/experiments/{id}/*, /comfymodal/history-v2/assets/{id}
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
ΓÜá∩╕Å  SeedVR2 optimizations check: SageAttention Γ¥î | Flash Attention Γ¥î | Triton Γ¥î
≡ƒÆí For best performance: pip install sageattention flash-attn triton
≡ƒôè Initial CUDA memory: 6.91GB free / 8.00GB total
### ComfyUI-Workflow-Encrypt: Copy .js from 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-workflow-encrypt\js\comfyui-workflow-encrypt.js' to 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\web\extensions\comfyui-workflow-encrypt'
# ≡ƒÿ║dzNodes: LayerStyle -> [1;33mCannot import name 'guidedFilter' from 'cv2.ximgproc'
A few nodes cannot works properly, while most nodes are not affected. Please REINSTALL package 'opencv-contrib-python'.
For detail refer to [4mhttps://github.com/chflame163/ComfyUI_LayerStyle/issues/5[0m[m
(RES4LYF) Init
(RES4LYF) Importing beta samplers.
(RES4LYF) Importing legacy samplers.

[92m[rgthree-comfy] Loaded 48 fantastic nodes. ≡ƒÄë[0m

[33m[rgthree-comfy] ComfyUI's new Node 2.0 rendering may be incompatible with some rgthree-comfy nodes and features, breaking some rendering as well as losing the ability to access a node's properties (a vital part of many nodes). It also appears to run MUCH more slowly spiking CPU usage and causing jankiness and unresponsiveness, especially with large workflows. Personally I am not planning to use the new Nodes 2.0 and, unfortunately, am not able to invest the time to investigate and overhaul rgthree-comfy where needed. If you have issues when Nodes 2.0 is enabled, I'd urge you to switch it off as well and join me in hoping ComfyUI is not planning to deprecate the existing, stable canvas rendering all together.
[0m
[v2.harness] production_output_registered output=True comparer=True
[v2.harness] node_registry_initialized classes=2192
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=miss
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-0-618c4bfa020a local_receive_to_worker_start_ms=16703.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16703.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16781.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] owner_ready pid=19496
[v2.local_handle] decision=persistent_hit
FETCH ComfyRegistry Data: 5/172
FETCH ComfyRegistry Data: 10/172
FETCH ComfyRegistry Data: 15/172
FETCH ComfyRegistry Data: 20/172
FETCH ComfyRegistry Data: 25/172
FETCH ComfyRegistry Data: 30/172
FETCH ComfyRegistry Data: 35/172
FETCH ComfyRegistry Data: 40/172
FETCH ComfyRegistry Data: 45/172
FETCH ComfyRegistry Data: 50/172
FETCH ComfyRegistry Data: 55/172
FETCH ComfyRegistry Data: 60/172
FETCH ComfyRegistry Data: 65/172
FETCH ComfyRegistry Data: 70/172
FETCH ComfyRegistry Data: 75/172
FETCH ComfyRegistry Data: 80/172
FETCH ComfyRegistry Data: 85/172
FETCH ComfyRegistry Data: 90/172
FETCH ComfyRegistry Data: 95/172
FETCH ComfyRegistry Data: 100/172
FETCH ComfyRegistry Data: 105/172
FETCH ComfyRegistry Data: 110/172
FETCH ComfyRegistry Data: 115/172
FETCH ComfyRegistry Data: 120/172
FETCH ComfyRegistry Data: 125/172
FETCH ComfyRegistry Data: 130/172
FETCH ComfyRegistry Data: 135/172
FETCH ComfyRegistry Data: 140/172
FETCH ComfyRegistry Data: 145/172
FETCH ComfyRegistry Data: 150/172
FETCH ComfyRegistry Data: 155/172
FETCH ComfyRegistry Data: 160/172
FETCH ComfyRegistry Data: 165/172
FETCH ComfyRegistry Data: 170/172
FETCH ComfyRegistry Data [DONE]
FETCH DATA from: https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json [DONE]
[v2.local_submission_breakdown] request_id=v2-benchmark-0-618c4bfa020a local_receive_to_worker_start_ms=16703.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16703.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16781.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16781.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.request_origin] request_id=v2-benchmark-0-618c4bfa020a trigger_source=benchmark local_prompt_enqueued_unix_ns=None local_prompt_ack_ready_unix_ns=None modal_generator_created_unix_ns=1786726406839329900 modal_submission_attempt_unix_ns=1786726406839329900 modal_first_event_received_unix_ns=1786726564683141000 modal_first_iteration_start_unix_ns=1786726406839329900 modal_first_remote_event_unix_ns=1786726564683141000 dispatch_to_modal_entry_ms=158087.143 local_receive_to_actual_submission_ms=16781.0 local_receive_to_result_return_ms=184643.266 t0_to_t1_ms=0.875 t1_to_queue_enqueue_ms=None local_receive_to_enqueue_ms=None queue_wait_before_worker_ms=None plan_build_ms=78.0 active_profile_ms=0.0 handle_lookup_ms=0.0 payload_serialize_ms=0.0 local_residual_ms=0.0 clock_reconciliation_residual_ms=0.0 route_unattributed_ms=None worker_unattributed_ms=None reconciliation_status=incomplete missing_stages=local_receive_to_enqueue_ms overlap_error= modal_input_id=in-01M00K2Q2BE5CMRQG4CDXJ6WAB:1786726407244-0 trigger_to_local_receive_ms=0.875 local_receive_to_generator_create_start_ms=16782.455 generator_create_ms=3.0 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=157843.811 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=505.785 restore_end_to_modal_method_entry_ms=17.24 modal_method_entry_to_executor_ms=198.342 submission_to_remote_python_resume_ms=157564.118 unexplained_pre_remote_ms=157843.811
[v2.remote_request_origin] request_id=v2-benchmark-0-618c4bfa020a trigger_source=benchmark ui_trigger_unix_ms=1786726390053 local_receive_wall_unix_ns=1786726390053875456 local_receive_mono_ns=182514609000000 modal_generator_create_start_wall_unix_ns=1786726406836330200 modal_generator_create_start_mono_ns=182531390000000 modal_generator_created_wall_unix_ns=1786726406839329900 modal_generator_created_mono_ns=182531390000000 modal_first_iteration_start_wall_unix_ns=1786726406839329900 modal_first_iteration_start_mono_ns=182531390000000 modal_submission_attempt_wall_unix_ns=1786726406839329900 modal_submission_attempt_mono_ns=182531390000000 modal_first_remote_event_wall_unix_ns=1786726564683141000 modal_first_remote_event_mono_ns=182689234000000 modal_submission_boundary_source=first_iteration_proxy remote_python_resume_wall_unix_ns=1786726564403447552 restore_method_start_wall_unix_ns=1786726564403447552 restore_method_end_wall_unix_ns=1786726564909232896 modal_method_entry_wall_unix_ns=1786726564926472960 prompt_executor_invoke_start_wall_unix_ns=1786726565124814592 trigger_to_local_receive_ms=0.875 local_receive_to_generator_create_start_ms=16782.455 generator_create_ms=3.0 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=157843.811 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=505.785 restore_end_to_modal_method_entry_ms=17.24 modal_method_entry_to_executor_ms=198.342 submission_to_remote_python_resume_ms=157564.118 unexplained_pre_remote_ms=157843.811 modal_input_id=in-01M00K2Q2BE5CMRQG4CDXJ6WAB:1786726407244-0
[v2.local_submission_breakdown.final] request_id=v2-benchmark-0-618c4bfa020a local_receive_to_worker_start_ms=16703.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16703.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16781.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16781.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent modal_submission_attempt_unix_ns=1786726406839329900 modal_generator_created_unix_ns=1786726406839329900 modal_first_iteration_start_unix_ns=1786726406839329900 modal_first_remote_event_unix_ns=1786726564683141000 dispatch_to_modal_entry_ms=158087.143 local_receive_to_actual_submission_ms=16781.0 local_receive_to_result_return_ms=184643.266
WATERFALL RECONCILIATION (local rebuild) replaced remote PARTIAL report with the full host-reconciled report
WATERFALL RECONCILIATION (local rebuild)
  command_to_response_ms            185075.1
  top_level_accounted_ms            31452.6
  global_residual_ms                -305.9
  global_residual_pct               -1.0
  reconciliation_status             EXCEEDS_TOLERANCE
  controllable_application_wall_ms  27817.0
  platform_wall_ms                  157564.1
  modal_restore_begin_unavailable   no
  OLD vs NEW accounted_ms 27817.0 -> 31452.6 | residual_ms -305.9 -> -305.9
production_adjusted_total_wall_ms=14482.224
[v2.experiment] saved=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_16-53-10\run_001_sample.json
{"run_index": 0, "request_id": "v2-benchmark-0-618c4bfa020a", "identity": {"app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint", "method_name": "run_plan_stream", "gpu": ["RTX-PRO-6000"], "cpu": 12, "memory_mb": 32768, "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "runtime_shape": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "stored_snapshot_model_order": "O0", "restore_count": 1, "request_count": 1, "restored_instance_id": "f588d0e038314f38b3201790e7169073", "restore_session_id": "5d1e97497a114bb9ad62115839b34843", "container_task_id": "ta-01M00K7B5MB2TC7FS8AMBZ6C4R", "modal_container_id": "", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "modal_input_id": "in-01M00K2Q2BE5CMRQG4CDXJ6WAB:1786726407244-0", "container_session_id": "fd1a0903d3904c6d"}, "runtime_shape": {"requested": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "deployed": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "observed": {"stage": "request_entry", "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "thread_policy": "TBASE", "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "native_thread_count": 53, "configured_omp": null, "configured_mkl": null, "configured_openblas": null, "configured_numexpr": null, "malloc_arena_max": null, "native_library_settings": {"OMP_NUM_THREADS": "12", "MKL_NUM_THREADS": "12", "OPENBLAS_NUM_THREADS": "12", "NUMEXPR_NUM_THREADS": null, "MALLOC_ARENA_MAX": null}, "torch_intraop_threads": 12, "torch_interop_threads": 14, "actual_torch_intraop_threads": 12, "actual_torch_interop_threads": 14, "requested_torch_intraop_threads": null, "requested_torch_interop_threads": null, "requested_vs_actual_match": true, "status": "baseline_passthrough", "error": "", "trace_id": "61fb4cb05dfb460c", "pid": 2, "thread_native_id": 2, "restored_instance_id": "f588d0e038314f38b3201790e7169073", "restore_session_id": "5d1e97497a114bb9ad62115839b34843", "legacy_container_session_id": "fd1a0903d3904c6d", "container_task_id": "ta-01M00K7B5MB2TC7FS8AMBZ6C4R", "modal_input_id": "in-01M00K2Q2BE5CMRQG4CDXJ6WAB:1786726407244-0", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint"}, "stored_snapshot_model_order": "O0", "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "guard": {"changed_axes": [], "allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768}, "construction_order_semantics": "model_construction_order_only"}, "timing": {"wall_ms": 167879.7, "handle_lookup_ms": 3.0, "submission_to_first_remote_event_ms": 157843.811, "command_to_response_ms": 185075.1, "submit2entry_ms": 158090.143, "t3b_to_t8_ms": 9829.083, "restore_total_ms": 270.669, "pre_sampler_ms": 4826.057, "sampler_ms": 3669.618, "vae_decode_ms": 386.815, "output_collection_ms": 8.487, "snapshot_callback_age_at_restore_ms": 1184455.207, "snapshot_callback_to_command_start_ms": 1009452.297, "command_start_to_restore_start_ms": 174768.447, "local_timing": {"t0_to_t1_ms": 0.875, "t1_to_queue_enqueue_ms": null, "local_receive_to_enqueue_ms": null, "local_body_read_ms": null, "local_json_parse_ms": null, "local_preflight_ms": null, "local_queue_lock_wait_ms": null, "local_queue_enqueue_ms": null, "queue_wait_before_worker_ms": null, "plan_build_ms": 78.0, "active_profile_ms": 0.0, "restore_plan_build_ms": null, "restore_publish_ms": null, "handle_lookup_ms": 0.0, "payload_serialize_ms": 0.0, "payload_materialization_ms": 0.0, "payload_size_measurement_ms": 0.0, "generator_create_ms": 3.0, "local_residual_ms": 0.0, "clock_reconciliation_residual_ms": 0.0, "route_unattributed_ms": null, "worker_unattributed_ms": null, "reconciliation_status": "incomplete", "missing_stages": ["local_receive_to_enqueue_ms"], "overlap_error": "", "stage_attribution_residual_ms": {"route_unattributed_ms": null, "worker_unattributed_ms": null, "missing_stages": ["local_receive_to_enqueue_ms"], "reconciliation_status": "incomplete", "overlap_error": ""}, "local_receive_to_generator_create_ms": 16781.0, "generator_create_to_first_iteration_ms": 0.0, "first_iteration_to_first_remote_event_ms": 157843.811, "local_receive_to_actual_submission_ms": 16781.0, "trigger_to_local_receive_ms": 0.875, "local_receive_to_generator_create_start_ms": 16782.455, "generator_created_to_first_iteration_ms": 0.0, "remote_python_resume_to_restore_start_ms": 0.0, "restore_method_ms": 505.785, "restore_end_to_modal_method_entry_ms": 17.24, "modal_method_entry_to_executor_ms": 198.342, "submission_to_remote_python_resume_ms": 157564.118, "unexplained_pre_remote_ms": 157843.811, "local_result_received_wall_ns": 1786726574697141900, "local_result_received_mono_ns": 182699250000000, "local_receive_to_result_return_ms": 184643.266, "result_received_to_return_ms": 13.0, "remote_result_emit_wall_unix_ns": 1786726575002146126, "remote_result_emit_to_local_receipt_ms": null, "caller_return_wall_unix_ns": 1786726574710142000, "caller_return_mono_ns": 182699265000000, "local_result_received_to_caller_return_ms": 15.0, "modal_restore_begin_wall_unix_ns": null}, "restore_breakdown": {"restore_total_ms": 270.669, "models_symlink_ms": 3.44, "manager_offline_ms": 1.18, "reload_models_ms": 0.0, "reload_runtime_state_ms": 0.0, "v2_startup_custom_node_source_copy_ms": 367.16, "sync_custom_nodes_ms": 367.3, "install_requirements_ms": 0.01, "v2_startup_comfyui_path_startup_ms": 0.34, "comfyui_path_setup_ms": 0.49, "v2_startup_backend_startup_ms": 19953.37, "backend_startup_ms": 19954.11, "observe_generations_ms": 0.83, "snapshot_restore_ms": 248.28, "snapshot_callback_age_at_restore_ms": 1184455.207, "restore_gpu_state_ms": 218.647, "cuda_init_ms": 3.42, "v2_startup_snapshot_execution_seed_ms": 0.9, "initialize_cuda_ms": 3.372, "snapshot_identity_checks_ms": 0.0, "cpu_snapshot_retargeting_ms": 0.0, "folder_warm_ms": 1800.481}, "early_activation_total_ms": null, "queue_delay_ms": null, "cpu_snapshot_wait_ms": null, "dtype_layout_preparation_ms": null, "post_load_bookkeeping_ms": null, "submission_to_remote_python_resume_ms": 157564.118, "remote_python_resume_to_restore_start_ms": 0.0, "restore_to_method_entry_ms": 17.24, "method_entry_to_first_remote_event_ms": null, "first_remote_event_to_final_result_ms": 10014.001, "transfer_queue_delay_ms": null, "synchronized_transfer_ms": null, "quiesce_wait_ms": null, "graph_activity_ms": 3567.409, "sampler_lane_wait_ms": 0.086, "quiesced_transfer": null}}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-618c4bfa020a  Instance: f588d0e038314f38b3201790e7169073  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east4
TOTAL WALL:           31.147s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:   185.075s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 418.875 ms | 418.875 ms |   1.345% | #                                        |
|   2 | Modal handle and submission                    |    16.785s |    17.204s |  53.892% | ######################                   |
|   3 | Modal pre-Python snapshot restoration          |     3.636s |    20.840s |  11.673% | #####                                    |
|   4 | Python/application restore                     | 505.774 ms |    21.346s |   1.624% | #                                        |
|   5 | Restore-to-method entry                        |  17.239 ms |    21.363s |   0.055% | #                                        |
|   6 | Remote method setup                            | 198.392 ms |    21.561s |   0.637% | #                                        |
|     |   method entry to graph start                  | 140.383 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 140.340 ms |            |          |                                          |
|     |   graph setup                                  |  58.010 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  13.822 ms |    21.575s |   0.044% | #                                        |
|   8 | Pre-sampler execution                          |     3.554s |    25.129s |  11.409% | #####                                    |
|     |   Conditioning cache exact_hit lookup=47.237ms |  47.237 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 570.532 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 116.770 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.255s |            |          |                                          |
|     |   Read end -> construction done                |   0.422 ms |            |          |                                          |
|     |   UNET get_model                               |  59.400 ms |            |          |                                          |
|     |   Bind                                         |  27.000 ms |            |          |                                          |
|     |   Synchronized H2D (5.3 GB/s)                  |     2.324s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.363 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 110.036 ms |    25.239s |   0.353% | #                                        |
|     |   lane acquired to actual stage                | 110.014 ms |            |          |                                          |
|  10 | Sampling                                       |     4.806s |    30.045s |  15.430% | ######                                   |
|  11 | Post-sampling / VAE transition                 | 765.384 ms |    30.810s |   2.457% | #                                        |
|  12 | VAE decode                                     | 386.816 ms |    31.197s |   1.242% | #                                        |
|     |   VAE load/H2D                                 | 806.302 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 240.799 ms |    31.438s |   0.773% | #                                        |
|     |   PNG encode                                   | 169.789 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  15.000 ms |    31.453s |   0.048% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |   153.928s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.922 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.prompt_executor_breakdown] request_id=v2-benchmark-0-618c4bfa020a exec_to_cached_ms=12.29 dynamic_prompt_ms=0.004 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.016 cache_gather_ms=0.107 cleanup_gc_ms=1.022 residual_ms=11.141 c2f_cached_to_first_node_ms=0.728 c2f_topo_walk_ms=0.564 c2f_topo_input_info_ms=0.107 c2f_topo_other_ms=0.457 c2f_stage_ms=1.319 c2f_first_node_prefix_ms=0.155 c2f_residual_ms=-1.31 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=8ffd5d7760804fa9ba99b1419063ecd931de3044a0f30a33c8a000a3197235c9 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.966 topo_lazy_hits=36
[v2.conditioning_exact_hit_breakdown] request_id=v2-benchmark-0-618c4bfa020a decision=exact_hit lookup_wall_ms=47.237 total_ms=46.976 key_build_ms=0.164 lock_wait_ms=0.002 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=34 entry_lookup_ms=16.537 header_bytes=3752 data_bytes=2900184 lru_touch_ms=29.9 lru_touch_mode=sync children_ms=46.603 residual_ms=0.373 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=0.025 prefetch_join_timeout=0 prefetch_overlap_ms=41.656 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=79.913 volume_reload_ms=0.0
[v2.folder_warm] request_id=v2-benchmark-0-618c4bfa020a folder_warm_ms=1800.481 folder_warm_folders=29
[v2.input_types_warm] request_id=v2-benchmark-0-618c4bfa020a input_types_warm_ms=815.663 input_types_warm_classes=31
[v2.png_output] request_id=v2-benchmark-0-618c4bfa020a compress_level=1 png_encode_ms=169.778 png_compress_ms=164.993 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
[v2.host_submission_breakdown] request_id=v2-benchmark-0-618c4bfa020a command_start_to_python_first_line_ms=156.875 python_first_line_to_local_receive_ms=262.0 local_receive_to_registry_start_ms=0.0 node_registry_init_ms=16664.454 registry_end_to_worker_start_ms=34.0 worker_start_to_plan_build_start_ms=0.999 plan_build_ms=78.0 plan_build_to_transport_entry_ms=6.0 transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=3.0 payload_serialize_ms=0.0 generator_create_ms=3.0 generator_created_to_submission_ms=0.0 local_receive_to_submission_ms=16781.0 submission_boundary_source=first_anext first_remote_signal_ms=157843.811 scheduling_ms=153928.464 scheduling_source=modal_app_log
BATCH B ACCEPTANCE

Batch A preserved:
PASS

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: skipped_generation_match
invoked: NO
reload ms: 0.0
generation check: YES
local only: YES

Snapshot hygiene:
enabled: 1
before RSS: 27007828.0
after RSS: 24734984.0
delta: -2272844.0
trim status: 1
manifest status: {'vmsize': 30379644, 'vmrss': 27007828, 'vmdata': 26269272, 'threads': 46}

Stage 13:
gate: READY
expectation: 1
total: 72.8
children: 8
largest child: waterfall_build_ms=38.4
reconciliation: 0.0

Host telemetry:
overhead (Tier A): 8.3
Tier B forensic probe: n/a
total probe: 8.3
forensic trigger: NO

TOTAL WALL: 167879.7 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: PASS
{
  "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\comfymodal-data\\benchmarks\\runs\\v2_2026-08-14_16-53-10",
  "target": {
    "app_name": "stable-modal-comfy-v2-restore-only-shadow",
    "class_name": "ModalRuntimeEntrypointV2",
    "gpu": "rtx-pro-6000"
  },
  "runtime_shape": {
    "requested": {
      "thread_policy": "TBASE",
      "torch_intraop_threads": null,
      "torch_interop_threads": null,
      "omp_num_threads": null,
      "mkl_num_threads": null,
      "openblas_num_threads": null,
      "numexpr_num_threads": null,
      "malloc_arena_max": null,
      "snapshot_model_order": "O0",
      "cpu_request": 12,
      "memory_request": 32768,
      "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
      "runtime_shape_label": null
    },
    "guard": {
      "changed_axes": [],
      "allow_multi_axis": false,
      "baseline_cpu_request": 12,
      "baseline_memory_request": 32768
    }
  },
  "run_count": 1,
  "gap_seconds": 35.0,
  "trace_handoff_errors": 0,
  "waterfall_runs": 1,
  "runs": [
    {
      "run_index": 0,
      "request_id": "v2-benchmark-0-618c4bfa020a",
      "identity": {
        "app_name": "stable-modal-comfy-v2-restore-only-shadow",
        "class_name": "ModalRuntimeEntrypoint",
        "method_name": "run_plan_stream",
        "gpu": [
          "RTX-PRO-6000"
        ],
        "cpu": 12,
        "memory_mb": 32768,
        "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce",
        "runtime_shape": {
          "thread_policy": "TBASE",
          "torch_intraop_threads": null,
          "torch_interop_threads": null,
          "omp_num_threads": null,
          "mkl_num_threads": null,
          "openblas_num_threads": null,
          "numexpr_num_threads": null,
          "malloc_arena_max": null,
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null
        },
        "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
        "runtime_shape_label": null,
        "stored_snapshot_model_order": "O0",
        "restore_count": 1,
        "request_count": 1,
        "restored_instance_id": "f588d0e038314f38b3201790e7169073",
        "restore_session_id": "5d1e97497a114bb9ad62115839b34843",
        "container_task_id": "ta-01M00K7B5MB2TC7FS8AMBZ6C4R",
        "modal_container_id": "",
        "image_id": "im-B1LdSHCggPdDMnEPTU8kop",
        "cloud": "CLOUD_PROVIDER_GCP",
        "region": "us-east4",
        "modal_input_id": "in-01M00K2Q2BE5CMRQG4CDXJ6WAB:1786726407244-0",
        "container_session_id": "fd1a0903d3904c6d"
      },
      "runtime_shape": {
        "requested": {
          "thread_policy": "TBASE",
          "torch_intraop_threads": null,
          "torch_interop_threads": null,
          "omp_num_threads": null,
          "mkl_num_threads": null,
          "openblas_num_threads": null,
          "numexpr_num_threads": null,
          "malloc_arena_max": null,
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null
        },
        "deployed": {
          "thread_policy": "TBASE",
          "torch_intraop_threads": null,
          "torch_interop_threads": null,
          "omp_num_threads": null,
          "mkl_num_threads": null,
          "openblas_num_threads": null,
          "numexpr_num_threads": null,
          "malloc_arena_max": null,
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null
        },
        "observed": {
          "stage": "request_entry",
          "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2",
          "runtime_shape_label": null,
          "thread_policy": "TBASE",
          "snapshot_model_order": "O0",
          "cpu_request": 12,
          "memory_request": 32768,
          "native_thread_count": 53,
          "configured_omp": null,
          "configured_mkl": null,
          "configured_openblas": null,
          "configured_numexpr": null,
          "malloc_arena_max": null,
          "native_library_settings": {
            "OMP_NUM_THREADS": "12",
            "MKL_NUM_THREADS": "12",
            "OPENBLAS_NUM_THREADS": "12",
            "NUMEXPR_NUM_THREADS": null,
            "MALLOC_ARENA_MAX": null
          },
          "torch_intraop_threads": 12,
          "torch_interop_threads": 14,
          "actual_torch_intraop_threads": 12,
          "actual_torch_interop_threads": 14,
          "requested_torch_intraop_threads": null,
          "requested_torch_interop_threads": null,
          "requested_vs_actual_match": true,
          "status": "baseline_passthrough",
          "error": "",
          "trace_id": "61fb4cb05dfb460c",
          "pid": 2,
          "thread_native_id": 2,
          "restored_instance_id": "f588d0e038314f38b3201790e7169073",
          "restore_session_id": "5d1e97497a114bb9ad62115839b34843",
          "legacy_container_session_id": "fd1a0903d3904c6d",
          "container_task_id": "ta-01M00K7B5MB2TC7FS8AMBZ6C4R",
          "modal_input_id": "in-01M00K2Q2BE5CMRQG4CDXJ6WAB:1786726407244-0",
          "image_id": "im-B1LdSHCggPdDMnEPTU8kop",
          "cloud": "CLOUD_PROVIDER_GCP",
          "region": "us-east4",
          "app_name": "stable-modal-comfy-v2-restore-only-shadow",
          "class_name": "ModalRuntimeEntrypoint"
        },
        "stored_snapshot_model_order": "O0",
        "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce",
        "guard": {
          "changed_axes": [],
          "allow_multi_axis": false,
          "baseline_cpu_request": 12,
          "baseline_memory_request": 32768
        },
        "construction_order_semantics": "model_construction_order_only"
      },
      "timing": {
        "wall_ms": 167879.7,
        "handle_lookup_ms": 3.0,
        "submission_to_first_remote_event_ms": 157843.811,
        "command_to_response_ms": 185075.1,
        "submit2entry_ms": 158090.143,
        "t3b_to_t8_ms": 9829.083,
        "restore_total_ms": 270.669,
        "pre_sampler_ms": 4826.057,
        "sampler_ms": 3669.618,
        "vae_decode_ms": 386.815,
        "output_collection_ms": 8.487,
        "snapshot_callback_age_at_restore_ms": 1184455.207,
        "snapshot_callback_to_command_start_ms": 1009452.297,
        "command_start_to_restore_start_ms": 174768.447,
        "local_timing": {
          "t0_to_t1_ms": 0.875,
          "t1_to_queue_enqueue_ms": null,
          "local_receive_to_enqueue_ms": null,
          "local_body_read_ms": null,
          "local_json_parse_ms": null,
          "local_preflight_ms": null,
          "local_queue_lock_wait_ms": null,
          "local_queue_enqueue_ms": null,
          "queue_wait_before_worker_ms": null,
          "plan_build_ms": 78.0,
          "active_profile_ms": 0.0,
          "restore_plan_build_ms": null,
          "restore_publish_ms": null,
          "handle_lookup_ms": 0.0,
          "payload_serialize_ms": 0.0,
          "payload_materialization_ms": 0.0,
          "payload_size_measurement_ms": 0.0,
          "generator_create_ms": 3.0,
          "local_residual_ms": 0.0,
          "clock_reconciliation_residual_ms": 0.0,
          "route_unattributed_ms": null,
          "worker_unattributed_ms": null,
          "reconciliation_status": "incomplete",
          "missing_stages": [
            "local_receive_to_enqueue_ms"
          ],
          "overlap_error": "",
          "stage_attribution_residual_ms": {
            "route_unattributed_ms": null,
            "worker_unattributed_ms": null,
            "missing_stages": [
              "local_receive_to_enqueue_ms"
            ],
            "reconciliation_status": "incomplete",
            "overlap_error": ""
          },
          "local_receive_to_generator_create_ms": 16781.0,
          "generator_create_to_first_iteration_ms": 0.0,
          "first_iteration_to_first_remote_event_ms": 157843.811,
          "local_receive_to_actual_submission_ms": 16781.0,
          "trigger_to_local_receive_ms": 0.875,
          "local_receive_to_generator_create_start_ms": 16782.455,
          "generator_created_to_first_iteration_ms": 0.0,
          "remote_python_resume_to_restore_start_ms": 0.0,
          "restore_method_ms": 505.785,
          "restore_end_to_modal_method_entry_ms": 17.24,
          "modal_method_entry_to_executor_ms": 198.342,
          "submission_to_remote_python_resume_ms": 157564.118,
          "unexplained_pre_remote_ms": 157843.811,
          "local_result_received_wall_ns": 1786726574697141900,
          "local_result_received_mono_ns": 182699250000000,
          "local_receive_to_result_return_ms": 184643.266,
          "result_received_to_return_ms": 13.0,
          "remote_result_emit_wall_unix_ns": 1786726575002146126,
          "remote_result_emit_to_local_receipt_ms": null,
          "caller_return_wall_unix_ns": 1786726574710142000,
          "caller_return_mono_ns": 182699265000000,
          "local_result_received_to_caller_return_ms": 15.0,
          "modal_restore_begin_wall_unix_ns": null
        },
        "restore_breakdown": {
          "restore_total_ms": 270.669,
          "models_symlink_ms": 3.44,
          "manager_offline_ms": 1.18,
          "reload_models_ms": 0.0,
          "reload_runtime_state_ms": 0.0,
          "v2_startup_custom_node_source_copy_ms": 367.16,
          "sync_custom_nodes_ms": 367.3,
          "install_requirements_ms": 0.01,
          "v2_startup_comfyui_path_startup_ms": 0.34,
          "comfyui_path_setup_ms": 0.49,
          "v2_startup_backend_startup_ms": 19953.37,
          "backend_startup_ms": 19954.11,
          "observe_generations_ms": 0.83,
          "snapshot_restore_ms": 248.28,
          "snapshot_callback_age_at_restore_ms": 1184455.207,
          "restore_gpu_state_ms": 218.647,
          "cuda_init_ms": 3.42,
          "v2_startup_snapshot_execution_seed_ms": 0.9,
          "initialize_cuda_ms": 3.372,
          "snapshot_identity_checks_ms": 0.0,
          "cpu_snapshot_retargeting_ms": 0.0,
          "folder_warm_ms": 1800.481
        },
        "early_activation_total_ms": null,
        "queue_delay_ms": null,
        "cpu_snapshot_wait_ms": null,
        "dtype_layout_preparation_ms": null,
        "post_load_bookkeeping_ms": null,
        "submission_to_remote_python_resume_ms": 157564.118,
        "remote_python_resume_to_restore_start_ms": 0.0,
        "restore_to_method_entry_ms": 17.24,
        "method_entry_to_first_remote_event_ms": null,
        "first_remote_event_to_final_result_ms": 10014.001,
        "transfer_queue_delay_ms": null,
        "synchronized_transfer_ms": null,
        "quiesce_wait_ms": null,
        "graph_activity_ms": 3567.409,
        "sampler_lane_wait_ms": 0.086,
        "quiesced_transfer": null
      }
    }
  ]
}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-618c4bfa020a  Instance: f588d0e038314f38b3201790e7169073  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east4
TOTAL WALL:           31.147s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:   185.075s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 418.875 ms | 418.875 ms |   1.345% | #                                        |
|   2 | Modal handle and submission                    |    16.785s |    17.204s |  53.892% | ######################                   |
|   3 | Modal pre-Python snapshot restoration          |     3.636s |    20.840s |  11.673% | #####                                    |
|   4 | Python/application restore                     | 505.774 ms |    21.346s |   1.624% | #                                        |
|   5 | Restore-to-method entry                        |  17.239 ms |    21.363s |   0.055% | #                                        |
|   6 | Remote method setup                            | 198.392 ms |    21.561s |   0.637% | #                                        |
|     |   method entry to graph start                  | 140.383 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 140.340 ms |            |          |                                          |
|     |   graph setup                                  |  58.010 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  13.822 ms |    21.575s |   0.044% | #                                        |
|   8 | Pre-sampler execution                          |     3.554s |    25.129s |  11.409% | #####                                    |
|     |   Conditioning cache exact_hit lookup=47.237ms |  47.237 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 570.532 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 116.770 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.255s |            |          |                                          |
|     |   Read end -> construction done                |   0.422 ms |            |          |                                          |
|     |   UNET get_model                               |  59.400 ms |            |          |                                          |
|     |   Bind                                         |  27.000 ms |            |          |                                          |
|     |   Synchronized H2D (5.3 GB/s)                  |     2.324s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.363 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 110.036 ms |    25.239s |   0.353% | #                                        |
|     |   lane acquired to actual stage                | 110.014 ms |            |          |                                          |
|  10 | Sampling                                       |     4.806s |    30.045s |  15.430% | ######                                   |
|  11 | Post-sampling / VAE transition                 | 765.384 ms |    30.810s |   2.457% | #                                        |
|  12 | VAE decode                                     | 386.816 ms |    31.197s |   1.242% | #                                        |
|     |   VAE load/H2D                                 | 806.302 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 240.799 ms |    31.438s |   0.773% | #                                        |
|     |   PNG encode                                   | 169.789 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  15.000 ms |    31.453s |   0.048% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |   153.928s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.922 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.experiment] campaign manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_16-53-10\campaign_manifest.json
=== Single V2 benchmark completed ===
=== Total command-to-response time: 190.286s ===

`

## D. v2_batchb_cohort_console.log — cohort attempt 1 (run 0 FAIL, platform re-construction)

`
[v2.env_profile]
env_profile=inherit
thread_policy=TBASE
snapshot_model_order=O0
baseline_cpu_request=12
baseline_memory_request=32768
memory_request_mb=32768
vae_policy=v1
release_gpu_after_request=0
cpu_model_snapshot=1
native_fast_disk_unet=1
publish_restore_plan=0
vae_snapshot=1
clip_conditioning_cache=1
unet_activation_mode=late
vae_activation_mode=sampling_end
persistent_local_handle=1
full_trace=0
residency_diagnostics=0
deep_model_diag=0
pagefault_tracking=0
eviction_enabled=0
eviction_role=none
eviction_idle_seconds=0
prefill_lanes=critical
prefill_wait_for_unet=0
restore_torch_threads=none
variance_pretouch=0
volume_read_run_count=3
restore_only_app=stable-modal-comfy-v2-restore-only-shadow
restore_only_run_count=6
snapshot_exclude_unet=
=== Running one V2 benchmark trial against the existing deployment ===
=== Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
[v2.host] python_first_line_wall_unix_ns=1786726606881500100
{"guard": {"allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768, "changed_axes": []}, "runtime_shape": {"cpu_request": 12, "malloc_arena_max": null, "memory_request": 32768, "mkl_num_threads": null, "numexpr_num_threads": null, "omp_num_threads": null, "openblas_num_threads": null, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "snapshot_model_order": "O0", "thread_policy": "TBASE", "torch_interop_threads": null, "torch_intraop_threads": null}}
run_v2_single.bat : WARNING:root:WARNING: You need pytorch with cu130 or higher to use optimized CUDA operations.
At line:1 char:364
+ ... MFYMODAL_V2_SNAPSHOT_MANIFEST='1'; & .\run_v2_single.bat 2>&1 | Tee-O ...
+                                        ~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (WARNING:root:WA...UDA operations.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[v2.harness] prompt_server_mirror instance_set=True
WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

Package diffusers installed failed
Package diffusers installed failed
[33mModule 'diffusers' load failed. If you don't have it installed, do it:[0m
[33mpip install diffusers[0m
[34m[ComfyUI-Easy-Use] server: [0mv1.3.6 [92mLoaded[0m
[34m[ComfyUI-Easy-Use] web root: [0mC:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-easy-use\web_version/v2 [92mLoaded[0m
[exact_prefill.local] enabled=1 source=env
[timing_trace] module loaded __file__=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\timing_trace.py TRACE_VERSION=2.0.0
[timing_trace] module directory in sys.path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\__init__.py", line 7, in <module>
    from .src.interfaces import comfy_entrypoint, SeedVR2Extension
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\__init__.py", line 8, in <module>
    from .video_upscaler import SeedVR2VideoUpscaler
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\video_upscaler.py", line 10, in <module>
    from ..utils.downloads import download_weight
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\downloads.py", line 14, in <module>
    from .model_registry import MODEL_REGISTRY, DEFAULT_VAE
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\model_registry.py", line 12, in <module>
    from ..models.dit_3b.nadit import NaDiT as NaDiT3B
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\nadit.py", line 24, in <module>
    from .embedding import TimeEmbedding
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\embedding.py", line 17, in <module>
    from diffusers.models.embeddings import get_timestep_embedding
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\__init__.py", line 3, in <module>
    from .configuration_utils import ConfigMixin
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\configuration_utils.py", line 34, in 
<module>
    from .utils import DIFFUSERS_CACHE, HUGGINGFACE_CO_RESOLVE_ENDPOINT, DummyObject, deprecate, logging
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\__init__.py", line 37, in 
<module>
    from .dynamic_modules_utils import get_class_from_dynamic_module
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\dynamic_modules_utils.py", line 
29, in <module>
    from huggingface_hub import HfFolder, cached_download, hf_hub_download, model_info
ImportError: cannot import name 'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler module for custom nodes: cannot import name 
'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ckpts path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using symlinks: False[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ort providers: ['CUDAExecutionProvider', 'DirectMLExecutionProvider', 'OpenVINOExecutionProvider', 
'ROCMExecutionProvider', 'CPUExecutionProvider', 'CoreMLExecutionProvider'][0m
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\node_wrappers\dwpose.py:26: UserWarning: DWPose: Onnxruntime not 
found or doesn't come with acceleration providers, switch to OpenCV with CPU device. DWPose might run very slowly
  warnings.warn("DWPose: Onnxruntime not found or doesn't come with acceleration providers, switch to OpenCV with CPU 
device. DWPose might run very slowly")
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\__init__.py", line 2, in <module>
    from .nodes.ai.FL_Fal_Gemini_ImageEdit import FL_Fal_Gemini_ImageEdit
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\nodes\ai\FL_Fal_Gemini_ImageEdit.py", line 10, in <module>
    import fal_client
ModuleNotFoundError: No module named 'fal_client'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes module for custom nodes: No module named 'fal_client'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_sam3\__init__.py", 
line 11, in <module>
    from .src.comfyui_sam3.nodes import NODE_CLASS_MAPPINGS
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3\src\comfyui_sam3\nodes.py", line 6, in <module>
    from sam3.model_builder import build_sam3_image_model, build_sam3_video_model
ModuleNotFoundError: No module named 'sam3'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3 module for custom nodes: No module named 'sam3'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1073, in get_code
  File "<frozen importlib._bootstrap_external>", line 1130, in get_data
FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comyui-modal-pagesfile-probe module for custom nodes: [Errno 2] No such file or 
directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*, /comfymodal/history-v2/feed, /comfymodal/history-v2/generations/{id}/*, /comfymodal/history-v2/experiments/{id}/*, /comfymodal/history-v2/assets/{id}
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
ΓÜá∩╕Å  SeedVR2 optimizations check: SageAttention Γ¥î | Flash Attention Γ¥î | Triton Γ¥î
≡ƒÆí For best performance: pip install sageattention flash-attn triton
≡ƒôè Initial CUDA memory: 6.91GB free / 8.00GB total
### ComfyUI-Workflow-Encrypt: Copy .js from 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-workflow-encrypt\js\comfyui-workflow-encrypt.js' to 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\web\extensions\comfyui-workflow-encrypt'
# ≡ƒÿ║dzNodes: LayerStyle -> [1;33mCannot import name 'guidedFilter' from 'cv2.ximgproc'
A few nodes cannot works properly, while most nodes are not affected. Please REINSTALL package 'opencv-contrib-python'.
For detail refer to [4mhttps://github.com/chflame163/ComfyUI_LayerStyle/issues/5[0m[m
(RES4LYF) Init
(RES4LYF) Importing beta samplers.
(RES4LYF) Importing legacy samplers.

[92m[rgthree-comfy] Loaded 48 fantastic nodes. ≡ƒÄë[0m

[33m[rgthree-comfy] ComfyUI's new Node 2.0 rendering may be incompatible with some rgthree-comfy nodes and features, breaking some rendering as well as losing the ability to access a node's properties (a vital part of many nodes). It also appears to run MUCH more slowly spiking CPU usage and causing jankiness and unresponsiveness, especially with large workflows. Personally I am not planning to use the new Nodes 2.0 and, unfortunately, am not able to invest the time to investigate and overhaul rgthree-comfy where needed. If you have issues when Nodes 2.0 is enabled, I'd urge you to switch it off as well and join me in hoping ComfyUI is not planning to deprecate the existing, stable canvas rendering all together.
[0m
[v2.harness] production_output_registered output=True comparer=True
[v2.harness] node_registry_initialized classes=2192
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=miss
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-0-186eb4adb1fd local_receive_to_worker_start_ms=16140.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16140.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16218.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] owner_ready pid=19496
[v2.local_handle] decision=persistent_hit
FETCH ComfyRegistry Data: 5/172
FETCH ComfyRegistry Data: 10/172
FETCH ComfyRegistry Data: 15/172
FETCH ComfyRegistry Data: 20/172
FETCH ComfyRegistry Data: 25/172
FETCH ComfyRegistry Data: 30/172
FETCH ComfyRegistry Data: 35/172
FETCH ComfyRegistry Data: 40/172
FETCH ComfyRegistry Data: 45/172
FETCH ComfyRegistry Data: 50/172
FETCH ComfyRegistry Data: 55/172
FETCH ComfyRegistry Data: 60/172
FETCH ComfyRegistry Data: 65/172
FETCH ComfyRegistry Data: 70/172
FETCH ComfyRegistry Data: 75/172
FETCH ComfyRegistry Data: 80/172
FETCH ComfyRegistry Data: 85/172
FETCH ComfyRegistry Data: 90/172
FETCH ComfyRegistry Data: 95/172
[v2.local_submission_breakdown] request_id=v2-benchmark-0-186eb4adb1fd local_receive_to_worker_start_ms=16140.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16140.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16218.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16218.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
FETCH ComfyRegistry Data: 100/172
FETCH ComfyRegistry Data: 105/172
FETCH ComfyRegistry Data: 110/172
[v2.request_origin] request_id=v2-benchmark-0-186eb4adb1fd trigger_source=benchmark local_prompt_enqueued_unix_ns=None local_prompt_ack_ready_unix_ns=None modal_generator_created_unix_ns=1786726623366345300 modal_submission_attempt_unix_ns=1786726623367345400 modal_first_event_received_unix_ns=1786726682200158500 modal_first_iteration_start_unix_ns=1786726623367345400 modal_first_remote_event_unix_ns=1786726682200158500 dispatch_to_modal_entry_ms=58923.657 local_receive_to_actual_submission_ms=16218.0 local_receive_to_result_return_ms=85396.654 t0_to_t1_ms=0.5 t1_to_queue_enqueue_ms=None local_receive_to_enqueue_ms=None queue_wait_before_worker_ms=None plan_build_ms=78.0 active_profile_ms=0.0 handle_lookup_ms=0.0 payload_serialize_ms=0.0 local_residual_ms=0.0 clock_reconciliation_residual_ms=0.0 route_unattributed_ms=None worker_unattributed_ms=None reconciliation_status=incomplete missing_stages=local_receive_to_enqueue_ms overlap_error= modal_input_id=in-01M00K9AH0A7X1EZHYKG5ZFVYA:1786726623777-0 trigger_to_local_receive_ms=0.5 local_receive_to_generator_create_start_ms=16215.845 generator_create_ms=1.999 generator_created_to_first_iteration_ms=1.0 first_iteration_to_first_remote_event_ms=58832.813 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=674.391 restore_end_to_modal_method_entry_ms=17.599 modal_method_entry_to_executor_ms=430.74 submission_to_remote_python_resume_ms=58231.668 unexplained_pre_remote_ms=58832.813
[v2.remote_request_origin] request_id=v2-benchmark-0-186eb4adb1fd trigger_source=benchmark ui_trigger_unix_ms=1786726607148 local_receive_wall_unix_ns=1786726607148500480 local_receive_mono_ns=182731703000000 modal_generator_create_start_wall_unix_ns=1786726623364345800 modal_generator_create_start_mono_ns=182747921000000 modal_generator_created_wall_unix_ns=1786726623366345300 modal_generator_created_mono_ns=182747921000000 modal_first_iteration_start_wall_unix_ns=1786726623367345400 modal_first_iteration_start_mono_ns=182747921000000 modal_submission_attempt_wall_unix_ns=1786726623367345400 modal_submission_attempt_mono_ns=182747921000000 modal_first_remote_event_wall_unix_ns=1786726682200158500 modal_first_remote_event_mono_ns=182806750000000 modal_submission_boundary_source=first_iteration_proxy remote_python_resume_wall_unix_ns=1786726681599013376 restore_method_start_wall_unix_ns=1786726681599013376 restore_method_end_wall_unix_ns=1786726682273403904 modal_method_entry_wall_unix_ns=1786726682291002880 prompt_executor_invoke_start_wall_unix_ns=1786726682721742848 trigger_to_local_receive_ms=0.5 local_receive_to_generator_create_start_ms=16215.845 generator_create_ms=1.999 generator_created_to_first_iteration_ms=1.0 first_iteration_to_first_remote_event_ms=58832.813 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=674.391 restore_end_to_modal_method_entry_ms=17.599 modal_method_entry_to_executor_ms=430.74 submission_to_remote_python_resume_ms=58231.668 unexplained_pre_remote_ms=58832.813 modal_input_id=in-01M00K9AH0A7X1EZHYKG5ZFVYA:1786726623777-0
[v2.local_submission_breakdown.final] request_id=v2-benchmark-0-186eb4adb1fd local_receive_to_worker_start_ms=16140.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=16140.0 worker_queue_ms=0.0 plan_build_ms=78.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16218.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16218.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent modal_submission_attempt_unix_ns=1786726623367345400 modal_generator_created_unix_ns=1786726623366345300 modal_first_iteration_start_unix_ns=1786726623367345400 modal_first_remote_event_unix_ns=1786726682200158500 dispatch_to_modal_entry_ms=58923.657 local_receive_to_actual_submission_ms=16218.0 local_receive_to_result_return_ms=85396.654
FETCH ComfyRegistry Data: 115/172
WATERFALL RECONCILIATION (local rebuild) replaced remote PARTIAL report with the full host-reconciled report
WATERFALL RECONCILIATION (local rebuild)
  command_to_response_ms            85829.2
  top_level_accounted_ms            30516.1
  global_residual_ms                -297.6
  global_residual_pct               -1.0
  reconciliation_status             EXCEEDS_TOLERANCE
  controllable_application_wall_ms  27895.1
  platform_wall_ms                  58231.7
  modal_restore_begin_unavailable   no
  OLD vs NEW accounted_ms 27895.1 -> 30516.1 | residual_ms -297.6 -> -297.6
FETCH ComfyRegistry Data: 120/172
production_adjusted_total_wall_ms=14099.154
[v2.experiment] saved=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_16-56-47\run_001_sample.json
{"run_index": 0, "request_id": "v2-benchmark-0-186eb4adb1fd", "identity": {"app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint", "method_name": "run_plan_stream", "gpu": ["RTX-PRO-6000"], "cpu": 12, "memory_mb": 32768, "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "runtime_shape": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "stored_snapshot_model_order": "O0", "restore_count": 1, "request_count": 1, "restored_instance_id": "55d08eb76bb6408494db716b387df85c", "restore_session_id": "ae59bd82f10a47b79fc262af4c9d8c14", "container_task_id": "ta-01M00K9B31VK19488S9EG6P21R", "modal_container_id": "", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "modal_input_id": "in-01M00K9AH0A7X1EZHYKG5ZFVYA:1786726623777-0", "container_session_id": "1d9343783e5a46e9"}, "runtime_shape": {"requested": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "deployed": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "observed": {"stage": "request_entry", "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "thread_policy": "TBASE", "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "native_thread_count": 53, "configured_omp": null, "configured_mkl": null, "configured_openblas": null, "configured_numexpr": null, "malloc_arena_max": null, "native_library_settings": {"OMP_NUM_THREADS": "12", "MKL_NUM_THREADS": "12", "OPENBLAS_NUM_THREADS": "12", "NUMEXPR_NUM_THREADS": null, "MALLOC_ARENA_MAX": null}, "torch_intraop_threads": 12, "torch_interop_threads": 14, "actual_torch_intraop_threads": 12, "actual_torch_interop_threads": 14, "requested_torch_intraop_threads": null, "requested_torch_interop_threads": null, "requested_vs_actual_match": true, "status": "baseline_passthrough", "error": "", "trace_id": "19ed5f045c634e60", "pid": 2, "thread_native_id": 2, "restored_instance_id": "55d08eb76bb6408494db716b387df85c", "restore_session_id": "ae59bd82f10a47b79fc262af4c9d8c14", "legacy_container_session_id": "1d9343783e5a46e9", "container_task_id": "ta-01M00K9B31VK19488S9EG6P21R", "modal_input_id": "in-01M00K9AH0A7X1EZHYKG5ZFVYA:1786726623777-0", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east4", "app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint"}, "stored_snapshot_model_order": "O0", "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "guard": {"changed_axes": [], "allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768}, "construction_order_semantics": "model_construction_order_only"}, "timing": {"wall_ms": 69198.2, "handle_lookup_ms": 2.0, "submission_to_first_remote_event_ms": 58832.813, "command_to_response_ms": 85830.2, "submit2entry_ms": 58926.657, "t3b_to_t8_ms": 10086.095, "restore_total_ms": 407.027, "pre_sampler_ms": 4874.375, "sampler_ms": 3685.577, "vae_decode_ms": 371.775, "output_collection_ms": 7.973, "snapshot_callback_age_at_restore_ms": 20449.681, "snapshot_callback_to_command_start_ms": null, "command_start_to_restore_start_ms": 74871.013, "local_timing": {"t0_to_t1_ms": 0.5, "t1_to_queue_enqueue_ms": null, "local_receive_to_enqueue_ms": null, "local_body_read_ms": null, "local_json_parse_ms": null, "local_preflight_ms": null, "local_queue_lock_wait_ms": null, "local_queue_enqueue_ms": null, "queue_wait_before_worker_ms": null, "plan_build_ms": 78.0, "active_profile_ms": 0.0, "restore_plan_build_ms": null, "restore_publish_ms": null, "handle_lookup_ms": 0.0, "payload_serialize_ms": 0.0, "payload_materialization_ms": 0.0, "payload_size_measurement_ms": 0.0, "generator_create_ms": 1.999, "local_residual_ms": 0.0, "clock_reconciliation_residual_ms": 0.0, "route_unattributed_ms": null, "worker_unattributed_ms": null, "reconciliation_status": "incomplete", "missing_stages": ["local_receive_to_enqueue_ms"], "overlap_error": "", "stage_attribution_residual_ms": {"route_unattributed_ms": null, "worker_unattributed_ms": null, "missing_stages": ["local_receive_to_enqueue_ms"], "reconciliation_status": "incomplete", "overlap_error": ""}, "local_receive_to_generator_create_ms": 16218.0, "generator_create_to_first_iteration_ms": 0.0, "first_iteration_to_first_remote_event_ms": 58832.813, "local_receive_to_actual_submission_ms": 16218.0, "trigger_to_local_receive_ms": 0.5, "local_receive_to_generator_create_start_ms": 16215.845, "generator_created_to_first_iteration_ms": 1.0, "remote_python_resume_to_restore_start_ms": 0.0, "restore_method_ms": 674.391, "restore_end_to_modal_method_entry_ms": 17.599, "modal_method_entry_to_executor_ms": 430.74, "submission_to_remote_python_resume_ms": 58231.668, "unexplained_pre_remote_ms": 58832.813, "local_result_received_wall_ns": 1786726692545154300, "local_result_received_mono_ns": 182817109000000, "local_receive_to_result_return_ms": 85396.654, "result_received_to_return_ms": 11.999, "remote_result_emit_wall_unix_ns": 1786726692855516777, "remote_result_emit_to_local_receipt_ms": null, "caller_return_wall_unix_ns": 1786726692557153400, "caller_return_mono_ns": 182817109000000, "local_result_received_to_caller_return_ms": 0.0, "modal_restore_begin_wall_unix_ns": null}, "restore_breakdown": {"restore_total_ms": 407.027, "models_symlink_ms": 3.2, "manager_offline_ms": 0.92, "reload_models_ms": 0.0, "reload_runtime_state_ms": 159.859, "v2_startup_custom_node_source_copy_ms": 358.79, "sync_custom_nodes_ms": 358.89, "install_requirements_ms": 0.01, "v2_startup_comfyui_path_startup_ms": 0.08, "comfyui_path_setup_ms": 0.15, "v2_startup_backend_startup_ms": 16629.52, "backend_startup_ms": 16630.22, "observe_generations_ms": 0.82, "snapshot_restore_ms": 383.85, "snapshot_callback_age_at_restore_ms": 20449.681, "restore_gpu_state_ms": 183.174, "cuda_init_ms": 3.15, "v2_startup_snapshot_execution_seed_ms": 1.32, "initialize_cuda_ms": 3.089, "snapshot_identity_checks_ms": 0.0, "cpu_snapshot_retargeting_ms": 0.0, "folder_warm_ms": 2015.961}, "early_activation_total_ms": null, "queue_delay_ms": null, "cpu_snapshot_wait_ms": null, "dtype_layout_preparation_ms": null, "post_load_bookkeeping_ms": null, "submission_to_remote_python_resume_ms": 58231.668, "remote_python_resume_to_restore_start_ms": 0.0, "restore_to_method_entry_ms": 17.599, "method_entry_to_first_remote_event_ms": null, "first_remote_event_to_final_result_ms": 10344.996, "transfer_queue_delay_ms": null, "synchronized_transfer_ms": null, "quiesce_wait_ms": null, "graph_activity_ms": 3569.024, "sampler_lane_wait_ms": 0.101, "quiesced_transfer": null}}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-186eb4adb1fd  Instance: 55d08eb76bb6408494db716b387df85c  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east4
TOTAL WALL:           30.218s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    85.829s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 420.500 ms | 420.500 ms |   1.392% | #                                        |
|   2 | Modal handle and submission                    |    16.219s |    16.639s |  53.672% | #####################                    |
|   3 | Modal pre-Python snapshot restoration          |     2.621s |    19.260s |   8.674% | ###                                      |
|   4 | Python/application restore                     | 674.381 ms |    19.935s |   2.232% | #                                        |
|   5 | Restore-to-method entry                        |  17.598 ms |    19.952s |   0.058% | #                                        |
|   6 | Remote method setup                            | 430.779 ms |    20.383s |   1.426% | #                                        |
|     |   method entry to graph start                  | 357.693 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 357.655 ms |            |          |                                          |
|     |   graph setup                                  |  73.086 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  12.487 ms |    20.396s |   0.041% | #                                        |
|   8 | Pre-sampler execution                          |     3.556s |    23.952s |  11.769% | #####                                    |
|     |   Conditioning cache exact_hit lookup=43.404ms |  43.404 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 402.687 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  29.913 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 137.116 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.472s |            |          |                                          |
|     |   Read end -> construction done                |   0.543 ms |            |          |                                          |
|     |   UNET get_model                               |  57.796 ms |            |          |                                          |
|     |   Bind                                         |  23.884 ms |            |          |                                          |
|     |   Synchronized H2D (5.2 GB/s)                  |     2.373s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.270 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 130.370 ms |    24.082s |   0.431% | #                                        |
|     |   lane acquired to actual stage                | 130.348 ms |            |          |                                          |
|  10 | Sampling                                       |     4.847s |    28.929s |  16.040% | ######                                   |
|  11 | Post-sampling / VAE transition                 | 972.519 ms |    29.902s |   3.218% | #                                        |
|  12 | VAE decode                                     | 371.775 ms |    30.274s |   1.230% | #                                        |
|     |   VAE load/H2D                                 | 995.053 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 242.373 ms |    30.516s |   0.802% | #                                        |
|     |   PNG encode                                   | 170.185 ms |            |          |                                          |
|  14 | Local result handling / caller return          |   0.000 ms |    30.516s |   0.000% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |    55.611s |            |          |                                          |
|     | RECONCILIATION                                 |  12.755 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
|     | TARGET 10MS                                    |     MISSED |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.prompt_executor_breakdown] request_id=v2-benchmark-0-186eb4adb1fd exec_to_cached_ms=4.581 dynamic_prompt_ms=0.004 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.015 cache_gather_ms=0.064 cleanup_gc_ms=0.699 residual_ms=3.799 c2f_cached_to_first_node_ms=0.711 c2f_topo_walk_ms=0.56 c2f_topo_input_info_ms=0.107 c2f_topo_other_ms=0.453 c2f_stage_ms=1.266 c2f_first_node_prefix_ms=0.15 c2f_residual_ms=-1.265 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=8ffd5d7760804fa9ba99b1419063ecd931de3044a0f30a33c8a000a3197235c9 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.222 topo_lazy_hits=36
[v2.conditioning_exact_hit_breakdown] request_id=v2-benchmark-0-186eb4adb1fd decision=exact_hit lookup_wall_ms=43.404 total_ms=43.117 key_build_ms=0.105 lock_wait_ms=0.002 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=34 entry_lookup_ms=17.529 header_bytes=3752 data_bytes=2900184 lru_touch_ms=25.192 lru_touch_mode=sync children_ms=42.828 residual_ms=0.289 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=8.896 prefetch_join_timeout=0 prefetch_overlap_ms=44.906 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=320.242 volume_reload_ms=0.0
[v2.folder_warm] request_id=v2-benchmark-0-186eb4adb1fd folder_warm_ms=2015.961 folder_warm_folders=29
[v2.input_types_warm] request_id=v2-benchmark-0-186eb4adb1fd input_types_warm_ms=855.383 input_types_warm_classes=31
[v2.png_output] request_id=v2-benchmark-0-186eb4adb1fd compress_level=1 png_encode_ms=170.171 png_compress_ms=159.187 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
[v2.host_submission_breakdown] request_id=v2-benchmark-0-186eb4adb1fd command_start_to_python_first_line_ms=153.5 python_first_line_to_local_receive_ms=267.0 local_receive_to_registry_start_ms=0.0 node_registry_init_ms=16119.336 registry_end_to_worker_start_ms=18.517 worker_start_to_plan_build_start_ms=0.991 plan_build_ms=78.0 plan_build_to_transport_entry_ms=5.0 transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=2.0 payload_serialize_ms=0.0 generator_create_ms=1.999 generator_created_to_submission_ms=1.0 local_receive_to_submission_ms=16218.0 submission_boundary_source=first_anext first_remote_signal_ms=58832.813 scheduling_ms=55610.664 scheduling_source=modal_app_log
BATCH B ACCEPTANCE

Batch A preserved:
PASS

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: reloaded_generation_mismatch
invoked: YES
reload ms: 159.9
generation check: YES
local only: NO

Snapshot hygiene:
enabled: 1
before RSS: 27008184.0
after RSS: 24727496.0
delta: -2280688.0
trim status: 1
manifest status: {'vmsize': 30360836, 'vmrss': 27006876, 'vmdata': 26250464, 'threads': 46}

Stage 13:
gate: READY
expectation: 1
total: 74.0
children: 8
largest child: waterfall_build_ms=38.9
reconciliation: 0.0

Host telemetry:
overhead (Tier A): 8.3
Tier B forensic probe: n/a
total probe: 8.3
forensic trigger: NO

TOTAL WALL: 69198.2 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: FAIL

FAILED CHECKS:
  runtime_state_guard: evidence='decision, invoked, reload_ms, generation_check', decision='reloaded_generation_mismatch', invoked=True (source: exact), reload_ms=159.859, generation_check=True, local_only=False (runtime-state reload invoked (a reload is not a local check)); FAILED: decision='reloaded_generation_mismatch' != skipped_generation_match; invoked=True (expected False; source: exact); reload_runtime_state_ms=159.859 is neither 0 nor local-check-only (local check budget 10 ms); generation check is not local: runtime-state reload invoked (a reload is not a local check)
Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8713, in <module>
    asyncio.run(_run_main_with_drain_teardown())
  File "C:\Program Files\Python311\Lib\asyncio\runners.py", line 190, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "C:\Program Files\Python311\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Program Files\Python311\Lib\asyncio\base_events.py", line 654, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8673, in _run_main_with_drain_teardown
    await main(
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8295, in main
    raise RuntimeError("batch-b acceptance: RUN 1 FAILED Batch-B gates")
RuntimeError: batch-b acceptance: RUN 1 FAILED Batch-B gates
Cannot connect to comfyregistry.
FETCH DATA from: https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json[ComfyUI-Manager] Due to a network error, switching to local mode.
=> custom-node-list.json
=> cannot schedule new futures after shutdown
FETCH DATA from: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-manager\custom-node-list.json [DONE]
=== ERROR: Benchmark failed ===
=== Total command-to-response time: 92.480s ===

`

## E. v2_batchb_probe_console.log — probe run (Tier-A variance FAIL)

`
[v2.env_profile]
env_profile=inherit
thread_policy=TBASE
snapshot_model_order=O0
baseline_cpu_request=12
baseline_memory_request=32768
memory_request_mb=32768
vae_policy=v1
release_gpu_after_request=0
cpu_model_snapshot=1
native_fast_disk_unet=1
publish_restore_plan=0
vae_snapshot=1
clip_conditioning_cache=1
unet_activation_mode=late
vae_activation_mode=sampling_end
persistent_local_handle=1
full_trace=0
residency_diagnostics=0
deep_model_diag=0
pagefault_tracking=0
eviction_enabled=0
eviction_role=none
eviction_idle_seconds=0
prefill_lanes=critical
prefill_wait_for_unet=0
restore_torch_threads=none
variance_pretouch=0
volume_read_run_count=3
restore_only_app=stable-modal-comfy-v2-restore-only-shadow
restore_only_run_count=6
snapshot_exclude_unet=
=== Running one V2 benchmark trial against the existing deployment ===
=== Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
[v2.host] python_first_line_wall_unix_ns=1786727239754243500
{"guard": {"allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768, "changed_axes": []}, "runtime_shape": {"cpu_request": 12, "malloc_arena_max": null, "memory_request": 32768, "mkl_num_threads": null, "numexpr_num_threads": null, "omp_num_threads": null, "openblas_num_threads": null, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "snapshot_model_order": "O0", "thread_policy": "TBASE", "torch_interop_threads": null, "torch_intraop_threads": null}}
run_v2_single.bat : WARNING:root:WARNING: You need pytorch with cu130 or higher to use optimized CUDA operations.
At line:1 char:327
+ ... MFYMODAL_V2_SNAPSHOT_MANIFEST='1'; & .\run_v2_single.bat 2>&1 | Tee-O ...
+                                        ~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (WARNING:root:WA...UDA operations.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[v2.harness] prompt_server_mirror instance_set=True
WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

Package diffusers installed failed
Package diffusers installed failed
[33mModule 'diffusers' load failed. If you don't have it installed, do it:[0m
[33mpip install diffusers[0m
[34m[ComfyUI-Easy-Use] server: [0mv1.3.6 [92mLoaded[0m
[34m[ComfyUI-Easy-Use] web root: [0mC:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-easy-use\web_version/v2 [92mLoaded[0m
[exact_prefill.local] enabled=1 source=env
[timing_trace] module loaded __file__=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\timing_trace.py TRACE_VERSION=2.0.0
[timing_trace] module directory in sys.path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\__init__.py", line 7, in <module>
    from .src.interfaces import comfy_entrypoint, SeedVR2Extension
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\__init__.py", line 8, in <module>
    from .video_upscaler import SeedVR2VideoUpscaler
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\video_upscaler.py", line 10, in <module>
    from ..utils.downloads import download_weight
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\downloads.py", line 14, in <module>
    from .model_registry import MODEL_REGISTRY, DEFAULT_VAE
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\model_registry.py", line 12, in <module>
    from ..models.dit_3b.nadit import NaDiT as NaDiT3B
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\nadit.py", line 24, in <module>
    from .embedding import TimeEmbedding
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\embedding.py", line 17, in <module>
    from diffusers.models.embeddings import get_timestep_embedding
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\__init__.py", line 3, in <module>
    from .configuration_utils import ConfigMixin
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\configuration_utils.py", line 34, in 
<module>
    from .utils import DIFFUSERS_CACHE, HUGGINGFACE_CO_RESOLVE_ENDPOINT, DummyObject, deprecate, logging
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\__init__.py", line 37, in 
<module>
    from .dynamic_modules_utils import get_class_from_dynamic_module
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\dynamic_modules_utils.py", line 
29, in <module>
    from huggingface_hub import HfFolder, cached_download, hf_hub_download, model_info
ImportError: cannot import name 'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler module for custom nodes: cannot import name 
'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ckpts path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using symlinks: False[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ort providers: ['CUDAExecutionProvider', 'DirectMLExecutionProvider', 'OpenVINOExecutionProvider', 
'ROCMExecutionProvider', 'CPUExecutionProvider', 'CoreMLExecutionProvider'][0m
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\node_wrappers\dwpose.py:26: UserWarning: DWPose: Onnxruntime not 
found or doesn't come with acceleration providers, switch to OpenCV with CPU device. DWPose might run very slowly
  warnings.warn("DWPose: Onnxruntime not found or doesn't come with acceleration providers, switch to OpenCV with CPU 
device. DWPose might run very slowly")
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\__init__.py", line 2, in <module>
    from .nodes.ai.FL_Fal_Gemini_ImageEdit import FL_Fal_Gemini_ImageEdit
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\nodes\ai\FL_Fal_Gemini_ImageEdit.py", line 10, in <module>
    import fal_client
ModuleNotFoundError: No module named 'fal_client'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes module for custom nodes: No module named 'fal_client'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_sam3\__init__.py", 
line 11, in <module>
    from .src.comfyui_sam3.nodes import NODE_CLASS_MAPPINGS
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3\src\comfyui_sam3\nodes.py", line 6, in <module>
    from sam3.model_builder import build_sam3_image_model, build_sam3_video_model
ModuleNotFoundError: No module named 'sam3'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3 module for custom nodes: No module named 'sam3'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1073, in get_code
  File "<frozen importlib._bootstrap_external>", line 1130, in get_data
FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comyui-modal-pagesfile-probe module for custom nodes: [Errno 2] No such file or 
directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*, /comfymodal/history-v2/feed, /comfymodal/history-v2/generations/{id}/*, /comfymodal/history-v2/experiments/{id}/*, /comfymodal/history-v2/assets/{id}
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
ΓÜá∩╕Å  SeedVR2 optimizations check: SageAttention Γ¥î | Flash Attention Γ¥î | Triton Γ¥î
≡ƒÆí For best performance: pip install sageattention flash-attn triton
≡ƒôè Initial CUDA memory: 6.91GB free / 8.00GB total
### ComfyUI-Workflow-Encrypt: Copy .js from 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-workflow-encrypt\js\comfyui-workflow-encrypt.js' to 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\web\extensions\comfyui-workflow-encrypt'
# ≡ƒÿ║dzNodes: LayerStyle -> [1;33mCannot import name 'guidedFilter' from 'cv2.ximgproc'
A few nodes cannot works properly, while most nodes are not affected. Please REINSTALL package 'opencv-contrib-python'.
For detail refer to [4mhttps://github.com/chflame163/ComfyUI_LayerStyle/issues/5[0m[m
(RES4LYF) Init
(RES4LYF) Importing beta samplers.
(RES4LYF) Importing legacy samplers.

[92m[rgthree-comfy] Loaded 48 fantastic nodes. ≡ƒÄë[0m

[33m[rgthree-comfy] ComfyUI's new Node 2.0 rendering may be incompatible with some rgthree-comfy nodes and features, breaking some rendering as well as losing the ability to access a node's properties (a vital part of many nodes). It also appears to run MUCH more slowly spiking CPU usage and causing jankiness and unresponsiveness, especially with large workflows. Personally I am not planning to use the new Nodes 2.0 and, unfortunately, am not able to invest the time to investigate and overhaul rgthree-comfy where needed. If you have issues when Nodes 2.0 is enabled, I'd urge you to switch it off as well and join me in hoping ComfyUI is not planning to deprecate the existing, stable canvas rendering all together.
[0m
[v2.harness] production_output_registered output=True comparer=True
[v2.harness] node_registry_initialized classes=2192
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=miss
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-0-17f67ff46dc5 local_receive_to_worker_start_ms=20281.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=20281.0 worker_queue_ms=0.0 plan_build_ms=94.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=20375.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] owner_ready pid=19496
[v2.local_handle] decision=persistent_hit
FETCH ComfyRegistry Data: 5/172
FETCH ComfyRegistry Data: 10/172
FETCH ComfyRegistry Data: 15/172
FETCH ComfyRegistry Data: 20/172
FETCH ComfyRegistry Data: 25/172
FETCH ComfyRegistry Data: 30/172
FETCH ComfyRegistry Data: 35/172
FETCH ComfyRegistry Data: 40/172
FETCH ComfyRegistry Data: 45/172
FETCH ComfyRegistry Data: 50/172
FETCH ComfyRegistry Data: 55/172
FETCH ComfyRegistry Data: 60/172
FETCH ComfyRegistry Data: 65/172
FETCH ComfyRegistry Data: 70/172
FETCH ComfyRegistry Data: 75/172
FETCH ComfyRegistry Data: 80/172
FETCH ComfyRegistry Data: 85/172
FETCH ComfyRegistry Data: 90/172
FETCH ComfyRegistry Data: 95/172
FETCH ComfyRegistry Data: 100/172
FETCH ComfyRegistry Data: 105/172
FETCH ComfyRegistry Data: 110/172
[v2.local_submission_breakdown] request_id=v2-benchmark-0-17f67ff46dc5 local_receive_to_worker_start_ms=20281.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=20281.0 worker_queue_ms=0.0 plan_build_ms=94.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=15.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=20375.0 generator_create_ms=15.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=20390.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
FETCH ComfyRegistry Data: 115/172
FETCH ComfyRegistry Data: 120/172
FETCH ComfyRegistry Data: 125/172
[v2.request_origin] request_id=v2-benchmark-0-17f67ff46dc5 trigger_source=benchmark local_prompt_enqueued_unix_ns=None local_prompt_ack_ready_unix_ns=None modal_generator_created_unix_ns=1786727260453309300 modal_submission_attempt_unix_ns=1786727260453309300 modal_first_event_received_unix_ns=1786727332341037100 modal_first_iteration_start_unix_ns=1786727260453309300 modal_first_remote_event_unix_ns=1786727332341037100 dispatch_to_modal_entry_ms=71443.231 local_receive_to_actual_submission_ms=20390.0 local_receive_to_result_return_ms=104289.899 t0_to_t1_ms=0.266 t1_to_queue_enqueue_ms=None local_receive_to_enqueue_ms=None queue_wait_before_worker_ms=None plan_build_ms=94.0 active_profile_ms=0.0 handle_lookup_ms=15.0 payload_serialize_ms=0.0 local_residual_ms=0.0 clock_reconciliation_residual_ms=0.0 route_unattributed_ms=None worker_unattributed_ms=None reconciliation_status=incomplete missing_stages=local_receive_to_enqueue_ms overlap_error= modal_input_id=in-01M00KWRSW55MZ8M35BH4P4JQ9:1786727260989-0 trigger_to_local_receive_ms=0.266 local_receive_to_generator_create_start_ms=20380.044 generator_create_ms=2.999 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=71887.728 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=7764.837 restore_end_to_modal_method_entry_ms=36.457 modal_method_entry_to_executor_ms=1315.766 submission_to_remote_python_resume_ms=63641.937 unexplained_pre_remote_ms=64086.433
[v2.remote_request_origin] request_id=v2-benchmark-0-17f67ff46dc5 trigger_source=benchmark ui_trigger_unix_ms=1786727240070 local_receive_wall_unix_ns=1786727240070265856 local_receive_mono_ns=183364625000000 modal_generator_create_start_wall_unix_ns=1786727260450309800 modal_generator_create_start_mono_ns=183385000000000 modal_generator_created_wall_unix_ns=1786727260453309300 modal_generator_created_mono_ns=183385015000000 modal_first_iteration_start_wall_unix_ns=1786727260453309300 modal_first_iteration_start_mono_ns=183385015000000 modal_submission_attempt_wall_unix_ns=1786727260453309300 modal_submission_attempt_mono_ns=183385015000000 modal_first_remote_event_wall_unix_ns=1786727332341037100 modal_first_remote_event_mono_ns=183456890000000 modal_submission_boundary_source=first_iteration_proxy remote_python_resume_wall_unix_ns=1786727324095246080 restore_method_start_wall_unix_ns=1786727324095246080 restore_method_end_wall_unix_ns=1786727331860082944 modal_method_entry_wall_unix_ns=1786727331896540416 prompt_executor_invoke_start_wall_unix_ns=1786727333212306688 trigger_to_local_receive_ms=0.266 local_receive_to_generator_create_start_ms=20380.044 generator_create_ms=2.999 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=71887.728 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=7764.837 restore_end_to_modal_method_entry_ms=36.457 modal_method_entry_to_executor_ms=1315.766 submission_to_remote_python_resume_ms=63641.937 unexplained_pre_remote_ms=64086.433 modal_input_id=in-01M00KWRSW55MZ8M35BH4P4JQ9:1786727260989-0
[v2.local_submission_breakdown.final] request_id=v2-benchmark-0-17f67ff46dc5 local_receive_to_worker_start_ms=20281.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=20281.0 worker_queue_ms=0.0 plan_build_ms=94.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=15.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=20375.0 generator_create_ms=15.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=20390.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent modal_submission_attempt_unix_ns=1786727260453309300 modal_generator_created_unix_ns=1786727260453309300 modal_first_iteration_start_unix_ns=1786727260453309300 modal_first_remote_event_unix_ns=1786727332341037100 dispatch_to_modal_entry_ms=71443.231 local_receive_to_actual_submission_ms=20390.0 local_receive_to_result_return_ms=104289.899
FETCH ComfyRegistry Data: 130/172
WATERFALL RECONCILIATION (local rebuild) replaced remote PARTIAL report with the full host-reconciled report
WATERFALL RECONCILIATION (local rebuild)
  command_to_response_ms            104810.2
  top_level_accounted_ms            48532.2
  global_residual_ms                -134.8
  global_residual_pct               -0.3
  reconciliation_status             EXCEEDS_TOLERANCE
  controllable_application_wall_ms  41303.1
  platform_wall_ms                  63641.9
  modal_restore_begin_unavailable   no
  OLD vs NEW accounted_ms 41303.1 -> 48532.2 | residual_ms -134.8 -> -134.8
production_adjusted_total_wall_ms=28143.348
[v2.experiment] saved=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_17-07-20\run_001_sample.json
{"run_index": 0, "request_id": "v2-benchmark-0-17f67ff46dc5", "identity": {"app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint", "method_name": "run_plan_stream", "gpu": ["RTX-PRO-6000"], "cpu": 12, "memory_mb": 32768, "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "runtime_shape": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "stored_snapshot_model_order": "O0", "restore_count": 1, "request_count": 1, "restored_instance_id": "8a33ac47c29349a685188968356ebf46", "restore_session_id": "50058e8b0ba84ed58fe9efb183123871", "container_task_id": "ta-01M00KYDSZHH4M64608WFHB8XR", "modal_container_id": "", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east1", "modal_input_id": "in-01M00KWRSW55MZ8M35BH4P4JQ9:1786727260989-0", "container_session_id": "1d9343783e5a46e9"}, "runtime_shape": {"requested": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "deployed": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "observed": {"stage": "request_entry", "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "thread_policy": "TBASE", "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "native_thread_count": 52, "configured_omp": null, "configured_mkl": null, "configured_openblas": null, "configured_numexpr": null, "malloc_arena_max": null, "native_library_settings": {"OMP_NUM_THREADS": "12", "MKL_NUM_THREADS": "12", "OPENBLAS_NUM_THREADS": "12", "NUMEXPR_NUM_THREADS": null, "MALLOC_ARENA_MAX": null}, "torch_intraop_threads": 12, "torch_interop_threads": 14, "actual_torch_intraop_threads": 12, "actual_torch_interop_threads": 14, "requested_torch_intraop_threads": null, "requested_torch_interop_threads": null, "requested_vs_actual_match": true, "status": "baseline_passthrough", "error": "", "trace_id": "00bc90b46e2341bc", "pid": 2, "thread_native_id": 2, "restored_instance_id": "8a33ac47c29349a685188968356ebf46", "restore_session_id": "50058e8b0ba84ed58fe9efb183123871", "legacy_container_session_id": "1d9343783e5a46e9", "container_task_id": "ta-01M00KYDSZHH4M64608WFHB8XR", "modal_input_id": "in-01M00KWRSW55MZ8M35BH4P4JQ9:1786727260989-0", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east1", "app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint"}, "stored_snapshot_model_order": "O0", "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "guard": {"changed_axes": [], "allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768}, "construction_order_semantics": "model_construction_order_only"}, "timing": {"wall_ms": 83936.8, "handle_lookup_ms": 4.0, "submission_to_first_remote_event_ms": 71887.728, "command_to_response_ms": 104810.2, "submit2entry_ms": 71447.232, "t3b_to_t8_ms": 11407.111, "restore_total_ms": 6885.991, "pre_sampler_ms": 6303.489, "sampler_ms": 3712.323, "vae_decode_ms": 389.804, "output_collection_ms": 9.176, "snapshot_callback_age_at_restore_ms": 663556.673, "snapshot_callback_to_command_start_ms": 578153.938, "command_start_to_restore_start_ms": 84525.246, "local_timing": {"t0_to_t1_ms": 0.266, "t1_to_queue_enqueue_ms": null, "local_receive_to_enqueue_ms": null, "local_body_read_ms": null, "local_json_parse_ms": null, "local_preflight_ms": null, "local_queue_lock_wait_ms": null, "local_queue_enqueue_ms": null, "queue_wait_before_worker_ms": null, "plan_build_ms": 94.0, "active_profile_ms": 0.0, "restore_plan_build_ms": null, "restore_publish_ms": null, "handle_lookup_ms": 15.0, "payload_serialize_ms": 0.0, "payload_materialization_ms": 0.0, "payload_size_measurement_ms": 0.0, "generator_create_ms": 2.999, "local_residual_ms": 0.0, "clock_reconciliation_residual_ms": 0.0, "route_unattributed_ms": null, "worker_unattributed_ms": null, "reconciliation_status": "incomplete", "missing_stages": ["local_receive_to_enqueue_ms"], "overlap_error": "", "stage_attribution_residual_ms": {"route_unattributed_ms": null, "worker_unattributed_ms": null, "missing_stages": ["local_receive_to_enqueue_ms"], "reconciliation_status": "incomplete", "overlap_error": ""}, "local_receive_to_generator_create_ms": 20375.0, "generator_create_to_first_iteration_ms": 0.0, "first_iteration_to_first_remote_event_ms": 71887.728, "local_receive_to_actual_submission_ms": 20390.0, "trigger_to_local_receive_ms": 0.266, "local_receive_to_generator_create_start_ms": 20380.044, "generator_created_to_first_iteration_ms": 0.0, "remote_python_resume_to_restore_start_ms": 0.0, "restore_method_ms": 7764.837, "restore_end_to_modal_method_entry_ms": 36.457, "modal_method_entry_to_executor_ms": 1315.766, "submission_to_remote_python_resume_ms": 63641.937, "unexplained_pre_remote_ms": 64086.433, "local_result_received_wall_ns": 1786727344360165200, "local_result_received_mono_ns": 183468921000000, "local_receive_to_result_return_ms": 104289.899, "result_received_to_return_ms": 19.005, "remote_result_emit_wall_unix_ns": 1786727344499803984, "remote_result_emit_to_local_receipt_ms": null, "caller_return_wall_unix_ns": 1786727344380171300, "caller_return_mono_ns": 183468937000000, "local_result_received_to_caller_return_ms": 16.0, "modal_restore_begin_wall_unix_ns": null}, "restore_breakdown": {"restore_total_ms": 6885.991, "models_symlink_ms": 3.2, "manager_offline_ms": 0.92, "reload_models_ms": 0.0, "reload_runtime_state_ms": 0.0, "v2_startup_custom_node_source_copy_ms": 358.79, "sync_custom_nodes_ms": 358.89, "install_requirements_ms": 0.01, "v2_startup_comfyui_path_startup_ms": 0.08, "comfyui_path_setup_ms": 0.15, "v2_startup_backend_startup_ms": 16629.52, "backend_startup_ms": 16630.22, "observe_generations_ms": 0.82, "snapshot_restore_ms": 6856.81, "folder_warm_ms": 6877.987, "snapshot_callback_age_at_restore_ms": 663556.673, "restore_gpu_state_ms": 5608.035, "cuda_init_ms": 11.36, "v2_startup_snapshot_execution_seed_ms": 1.37, "initialize_cuda_ms": 11.222, "snapshot_identity_checks_ms": 0.0, "cpu_snapshot_retargeting_ms": 0.0}, "early_activation_total_ms": null, "queue_delay_ms": null, "cpu_snapshot_wait_ms": null, "dtype_layout_preparation_ms": null, "post_load_bookkeeping_ms": null, "submission_to_remote_python_resume_ms": 63641.937, "remote_python_resume_to_restore_start_ms": 0.0, "restore_to_method_entry_ms": 36.457, "method_entry_to_first_remote_event_ms": 444.497, "first_remote_event_to_final_result_ms": 12019.128, "transfer_queue_delay_ms": null, "synchronized_transfer_ms": null, "quiesce_wait_ms": null, "graph_activity_ms": 4752.982, "sampler_lane_wait_ms": 0.106, "quiesced_transfer": null}}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-17f67ff46dc5  Instance: 8a33ac47c29349a685188968356ebf46  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east1
TOTAL WALL:           48.397s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:   104.810s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 500.266 ms | 500.266 ms |   1.034% | #                                        |
|   2 | Modal handle and submission                    |    20.383s |    20.883s |  42.116% | #################                        |
|   3 | Modal pre-Python snapshot restoration          |     7.229s |    28.112s |  14.937% | ######                                   |
|   4 | Python/application restore                     |     7.765s |    35.877s |  16.044% | ######                                   |
|   5 | Restore-to-method entry                        |  36.455 ms |    35.914s |   0.075% | #                                        |
|   6 | Remote method setup                            |     1.316s |    37.230s |   2.719% | #                                        |
|     |   method entry to graph start                  |     1.027s |            |          |                                          |
|     |   method entry to runtime configuration        |     1.027s |            |          |                                          |
|     |   graph setup                                  | 288.428 ms |            |          |                                          |
|     |   production registry setup                    | 166.601 ms |            |          |                                          |
|     |   pregraph setup                               | 167.032 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |   7.685 ms |    37.237s |   0.016% | #                                        |
|   8 | Pre-sampler execution                          |     4.745s |    41.982s |   9.805% | ####                                     |
|     |   Conditioning cache exact_hit lookup=59.235ms |  59.235 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 429.096 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  50.911 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 153.021 ms |            |          |                                          |
|     |   Checkpoint read                              |     2.385s |            |          |                                          |
|     |   Read end -> construction done                |   0.160 ms |            |          |                                          |
|     |   UNET get_model                               |  58.658 ms |            |          |                                          |
|     |   Bind                                         |  22.191 ms |            |          |                                          |
|     |   Synchronized H2D (3.5 GB/s)                  |     3.499s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.363 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 144.529 ms |    42.127s |   0.299% | #                                        |
|     |   lane acquired to actual stage                | 144.505 ms |            |          |                                          |
|  10 | Sampling                                       |     4.937s |    47.064s |  10.201% | ####                                     |
|  11 | Post-sampling / VAE transition                 | 822.976 ms |    47.887s |   1.700% | #                                        |
|  12 | VAE decode                                     | 389.805 ms |    48.277s |   0.805% | #                                        |
|     |   VAE load/H2D                                 | 847.265 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 239.245 ms |    48.516s |   0.494% | #                                        |
|     |   PNG encode                                   | 165.861 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  16.000 ms |    48.532s |   0.033% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |    56.413s |            |          |                                          |
|     | RECONCILIATION                                 |   4.820 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.prompt_executor_breakdown] request_id=v2-benchmark-0-17f67ff46dc5 exec_to_cached_ms=6.43 dynamic_prompt_ms=0.005 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.02 cache_gather_ms=0.074 cleanup_gc_ms=1.274 residual_ms=5.057 c2f_cached_to_first_node_ms=0.779 c2f_topo_walk_ms=0.592 c2f_topo_input_info_ms=0.087 c2f_topo_other_ms=0.505 c2f_stage_ms=1.417 c2f_first_node_prefix_ms=0.149 c2f_residual_ms=-1.379 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=8ffd5d7760804fa9ba99b1419063ecd931de3044a0f30a33c8a000a3197235c9 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.652 topo_lazy_hits=36
[v2.conditioning_exact_hit_breakdown] request_id=v2-benchmark-0-17f67ff46dc5 decision=exact_hit lookup_wall_ms=59.235 total_ms=58.931 key_build_ms=0.232 lock_wait_ms=0.002 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=34 entry_lookup_ms=23.385 header_bytes=3752 data_bytes=2900184 lru_touch_ms=27.865 lru_touch_mode=sync children_ms=51.484 residual_ms=7.447 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=242.008 prefetch_join_timeout=0 prefetch_overlap_ms=284.402 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=722.332 volume_reload_ms=0.0
[v2.folder_warm] request_id=v2-benchmark-0-17f67ff46dc5 folder_warm_ms=6877.987 folder_warm_folders=29
[v2.input_types_warm] request_id=v2-benchmark-0-17f67ff46dc5 input_types_warm_ms=1365.18 input_types_warm_classes=31
[v2.png_output] request_id=v2-benchmark-0-17f67ff46dc5 compress_level=1 png_encode_ms=165.841 png_compress_ms=159.653 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
[v2.host_submission_breakdown] request_id=v2-benchmark-0-17f67ff46dc5 command_start_to_python_first_line_ms=184.244 python_first_line_to_local_receive_ms=316.022 local_receive_to_registry_start_ms=0.0 node_registry_init_ms=20254.017 registry_end_to_worker_start_ms=29.576 worker_start_to_plan_build_start_ms=1.0 plan_build_ms=94.0 plan_build_to_transport_entry_ms=5.999 transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=15.0 payload_serialize_ms=1.001 generator_create_ms=2.999 generator_created_to_submission_ms=0.0 local_receive_to_submission_ms=20390.0 submission_boundary_source=first_anext first_remote_signal_ms=71887.728 scheduling_ms=56412.807 scheduling_source=modal_app_log
BATCH B ACCEPTANCE

Batch A preserved:
PASS

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: skipped_generation_match
invoked: NO
reload ms: 0.0
generation check: YES
local only: YES

Snapshot hygiene:
enabled: 1
before RSS: 27008184.0
after RSS: 24727496.0
delta: -2280688.0
trim status: 1
manifest status: {'vmsize': 30360836, 'vmrss': 27006876, 'vmdata': 26250464, 'threads': 46}

Stage 13:
gate: READY
expectation: 1
total: 75.3
children: 8
largest child: waterfall_build_ms=38.0
reconciliation: 0.0

Host telemetry:
overhead (Tier A): 27.5
Tier B forensic probe: n/a
total probe: 27.5
forensic trigger: NO

TOTAL WALL: 83936.8 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: FAIL

FAILED CHECKS:
  host_telemetry_overhead: Tier-A overhead=27.549999999999997 ms vs hard cap 20 ms on healthy H2D (3498.935 ms); slow-trigger probe=0 ms (must be 0 on healthy)
Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8713, in <module>
    asyncio.run(_run_main_with_drain_teardown())
  File "C:\Program Files\Python311\Lib\asyncio\runners.py", line 190, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "C:\Program Files\Python311\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Program Files\Python311\Lib\asyncio\base_events.py", line 654, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8673, in _run_main_with_drain_teardown
    await main(
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui-modal\tools\benchmark_v2_direct.py", line 8295, in main
    raise RuntimeError("batch-b acceptance: RUN 1 FAILED Batch-B gates")
RuntimeError: batch-b acceptance: RUN 1 FAILED Batch-B gates
Cannot connect to comfyregistry.
FETCH DATA from: https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json[ComfyUI-Manager] Due to a network error, switching to local mode.
=> custom-node-list.json
=> cannot schedule new futures after shutdown
FETCH DATA from: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-manager\custom-node-list.json [DONE]
=== ERROR: Benchmark failed ===
=== Total command-to-response time: 110.944s ===

`

## F. v2_batchb_cohort2_console.log — cohort attempt 2 (run 0 PASS, run 1 completed, aborted)

`
[v2.env_profile]
env_profile=inherit
thread_policy=TBASE
snapshot_model_order=O0
baseline_cpu_request=12
baseline_memory_request=32768
memory_request_mb=32768
vae_policy=v1
release_gpu_after_request=0
cpu_model_snapshot=1
native_fast_disk_unet=1
publish_restore_plan=0
vae_snapshot=1
clip_conditioning_cache=1
unet_activation_mode=late
vae_activation_mode=sampling_end
persistent_local_handle=1
full_trace=0
residency_diagnostics=0
deep_model_diag=0
pagefault_tracking=0
eviction_enabled=0
eviction_role=none
eviction_idle_seconds=0
prefill_lanes=critical
prefill_wait_for_unet=0
restore_torch_threads=none
variance_pretouch=0
volume_read_run_count=3
restore_only_app=stable-modal-comfy-v2-restore-only-shadow
restore_only_run_count=6
snapshot_exclude_unet=
=== Running one V2 benchmark trial against the existing deployment ===
=== Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
[v2.host] python_first_line_wall_unix_ns=1786727430542734600
{"guard": {"allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768, "changed_axes": []}, "runtime_shape": {"cpu_request": 12, "malloc_arena_max": null, "memory_request": 32768, "mkl_num_threads": null, "numexpr_num_threads": null, "omp_num_threads": null, "openblas_num_threads": null, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "snapshot_model_order": "O0", "thread_policy": "TBASE", "torch_interop_threads": null, "torch_intraop_threads": null}}
run_v2_single.bat : WARNING:root:WARNING: You need pytorch with cu130 or higher to use optimized CUDA operations.
At line:1 char:364
+ ... MFYMODAL_V2_SNAPSHOT_MANIFEST='1'; & .\run_v2_single.bat 2>&1 | Tee-O ...
+                                        ~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (WARNING:root:WA...UDA operations.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[v2.harness] prompt_server_mirror instance_set=True
WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

WARNING:root:
----------------------------------------------------------------------------
[Impact Pack] The SAM2 functionality is unavailable because the `facebook/sam2` dependency is not installed.

Installation command:
C:\Program Files\Python311\python.exe -m pip install git+https://github.com/facebookresearch/sam2
----------------------------------------------------------------------------

Package diffusers installed failed
Package diffusers installed failed
[33mModule 'diffusers' load failed. If you don't have it installed, do it:[0m
[33mpip install diffusers[0m
[34m[ComfyUI-Easy-Use] server: [0mv1.3.6 [92mLoaded[0m
[34m[ComfyUI-Easy-Use] web root: [0mC:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-easy-use\web_version/v2 [92mLoaded[0m
[exact_prefill.local] enabled=1 source=env
[timing_trace] module loaded __file__=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\timing_trace.py TRACE_VERSION=2.0.0
[timing_trace] module directory in sys.path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\__init__.py", line 7, in <module>
    from .src.interfaces import comfy_entrypoint, SeedVR2Extension
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\__init__.py", line 8, in <module>
    from .video_upscaler import SeedVR2VideoUpscaler
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\interfaces\video_upscaler.py", line 10, in <module>
    from ..utils.downloads import download_weight
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\downloads.py", line 14, in <module>
    from .model_registry import MODEL_REGISTRY, DEFAULT_VAE
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\utils\model_registry.py", line 12, in <module>
    from ..models.dit_3b.nadit import NaDiT as NaDiT3B
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\nadit.py", line 24, in <module>
    from .embedding import TimeEmbedding
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\src\models\dit_3b\embedding.py", line 17, in <module>
    from diffusers.models.embeddings import get_timestep_embedding
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\__init__.py", line 3, in <module>
    from .configuration_utils import ConfigMixin
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\configuration_utils.py", line 34, in 
<module>
    from .utils import DIFFUSERS_CACHE, HUGGINGFACE_CO_RESOLVE_ENDPOINT, DummyObject, deprecate, logging
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\__init__.py", line 37, in 
<module>
    from .dynamic_modules_utils import get_class_from_dynamic_module
  File "C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\diffusers\utils\dynamic_modules_utils.py", line 
29, in <module>
    from huggingface_hub import HfFolder, cached_download, hf_hub_download, model_info
ImportError: cannot import name 'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler module for custom nodes: cannot import name 
'cached_download' from 'huggingface_hub' 
(C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\huggingface_hub\__init__.py)
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ckpts path: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using symlinks: False[0m
[36;20m[C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_controlnet_aux] | 
INFO -> Using ort providers: ['CUDAExecutionProvider', 'DirectMLExecutionProvider', 'OpenVINOExecutionProvider', 
'ROCMExecutionProvider', 'CPUExecutionProvider', 'CoreMLExecutionProvider'][0m
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_controlnet_aux\node_wrappers\dwpose.py:26: UserWarning: DWPose: Onnxruntime not 
found or doesn't come with acceleration providers, switch to OpenCV with CPU device. DWPose might run very slowly
  warnings.warn("DWPose: Onnxruntime not found or doesn't come with acceleration providers, switch to OpenCV with CPU 
device. DWPose might run very slowly")
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\__init__.py", line 2, in <module>
    from .nodes.ai.FL_Fal_Gemini_ImageEdit import FL_Fal_Gemini_ImageEdit
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes\nodes\ai\FL_Fal_Gemini_ImageEdit.py", line 10, in <module>
    import fal_client
ModuleNotFoundError: No module named 'fal_client'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_fill-nodes module for custom nodes: No module named 'fal_client'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui_sam3\__init__.py", 
line 11, in <module>
    from .src.comfyui_sam3.nodes import NODE_CLASS_MAPPINGS
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3\src\comfyui_sam3\nodes.py", line 6, in <module>
    from sam3.model_builder import build_sam3_image_model, build_sam3_video_model
ModuleNotFoundError: No module named 'sam3'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comfyui_sam3 module for custom nodes: No module named 'sam3'
WARNING:root:Traceback (most recent call last):
  File "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\nodes.py", line 2212, in load_custom_node
    module_spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1073, in get_code
  File "<frozen importlib._bootstrap_external>", line 1130, in get_data
FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'

WARNING:root:Cannot import C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June 
Install\ComfyUI\custom_nodes\comyui-modal-pagesfile-probe module for custom nodes: [Errno 2] No such file or 
directory: 'C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June 
Install\\ComfyUI\\custom_nodes\\comyui-modal-pagesfile-probe\\__init__.py'
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*, /comfymodal/history-v2/feed, /comfymodal/history-v2/generations/{id}/*, /comfymodal/history-v2/experiments/{id}/*, /comfymodal/history-v2/assets/{id}
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
[exact_prefill.local] enabled=1 source=env
[comfyui-modal] Routes registered: /comfymodal/prompt, /comfymodal/model/install, /comfymodal/models/batch-install, /comfymodal/models/inject, /comfymodal/models/inject-all, /comfymodal/health, /comfymodal/object_info, /comfymodal/cancel/{id}, /comfymodal/models, /comfymodal/sync/status, /comfymodal/sync/models, /comfymodal/sync/custom-nodes, /comfymodal/runtime/resync, /comfymodal/runtime/state, /comfymodal/comparison/*, /comfymodal/experiments/*, /comfymodal/presets/*, /comfymodal/assets/{id}, /comfymodal/run-history/*, /comfymodal/deploy-warmup/*, /comfymodal/history/*
ΓÜá∩╕Å  SeedVR2 optimizations check: SageAttention Γ¥î | Flash Attention Γ¥î | Triton Γ¥î
≡ƒÆí For best performance: pip install sageattention flash-attn triton
≡ƒôè Initial CUDA memory: 6.91GB free / 8.00GB total
### ComfyUI-Workflow-Encrypt: Copy .js from 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-workflow-encrypt\js\comfyui-workflow-encrypt.js' to 'C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\web\extensions\comfyui-workflow-encrypt'
# ≡ƒÿ║dzNodes: LayerStyle -> [1;33mCannot import name 'guidedFilter' from 'cv2.ximgproc'
A few nodes cannot works properly, while most nodes are not affected. Please REINSTALL package 'opencv-contrib-python'.
For detail refer to [4mhttps://github.com/chflame163/ComfyUI_LayerStyle/issues/5[0m[m
(RES4LYF) Init
(RES4LYF) Importing beta samplers.
(RES4LYF) Importing legacy samplers.

[92m[rgthree-comfy] Loaded 48 epic nodes. ≡ƒÄë[0m

[33m[rgthree-comfy] ComfyUI's new Node 2.0 rendering may be incompatible with some rgthree-comfy nodes and features, breaking some rendering as well as losing the ability to access a node's properties (a vital part of many nodes). It also appears to run MUCH more slowly spiking CPU usage and causing jankiness and unresponsiveness, especially with large workflows. Personally I am not planning to use the new Nodes 2.0 and, unfortunately, am not able to invest the time to investigate and overhaul rgthree-comfy where needed. If you have issues when Nodes 2.0 is enabled, I'd urge you to switch it off as well and join me in hoping ComfyUI is not planning to deprecate the existing, stable canvas rendering all together.
[0m
[v2.harness] production_output_registered output=True comparer=True
[v2.harness] node_registry_initialized classes=2192
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=miss
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-0-fca6be8396ee local_receive_to_worker_start_ms=22656.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=22656.0 worker_queue_ms=0.0 plan_build_ms=110.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=22781.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] owner_ready pid=19496
[v2.local_handle] decision=persistent_hit
FETCH ComfyRegistry Data: 5/172
FETCH ComfyRegistry Data: 10/172
FETCH ComfyRegistry Data: 15/172
FETCH ComfyRegistry Data: 20/172
FETCH ComfyRegistry Data: 25/172
FETCH ComfyRegistry Data: 30/172
[v2.local_submission_breakdown] request_id=v2-benchmark-0-fca6be8396ee local_receive_to_worker_start_ms=22656.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=22656.0 worker_queue_ms=0.0 plan_build_ms=110.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=22781.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=22781.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
FETCH ComfyRegistry Data: 35/172
FETCH ComfyRegistry Data: 40/172
FETCH ComfyRegistry Data: 45/172
FETCH ComfyRegistry Data: 50/172
FETCH ComfyRegistry Data: 55/172
[v2.request_origin] request_id=v2-benchmark-0-fca6be8396ee trigger_source=benchmark local_prompt_enqueued_unix_ns=None local_prompt_ack_ready_unix_ns=None modal_generator_created_unix_ns=1786727453617171000 modal_submission_attempt_unix_ns=1786727453617171000 modal_first_event_received_unix_ns=1786727472214117200 modal_first_iteration_start_unix_ns=1786727453617171000 modal_first_remote_event_unix_ns=1786727472214117200 dispatch_to_modal_entry_ms=18296.155 local_receive_to_actual_submission_ms=22781.0 local_receive_to_result_return_ms=58328.213 t0_to_t1_ms=0.734 t1_to_queue_enqueue_ms=None local_receive_to_enqueue_ms=None queue_wait_before_worker_ms=None plan_build_ms=110.0 active_profile_ms=0.0 handle_lookup_ms=0.0 payload_serialize_ms=0.0 local_residual_ms=0.0 clock_reconciliation_residual_ms=0.0 route_unattributed_ms=None worker_unattributed_ms=None reconciliation_status=incomplete missing_stages=local_receive_to_enqueue_ms overlap_error= modal_input_id=in-01M00M2NEN6181YQXEFPN9M157:1786727454165-0 trigger_to_local_receive_ms=0.734 local_receive_to_generator_create_start_ms=22781.436 generator_create_ms=4.001 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=18596.946 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=1876.918 restore_end_to_modal_method_entry_ms=45.085 modal_method_entry_to_executor_ms=1309.606 submission_to_remote_python_resume_ms=16374.152 unexplained_pre_remote_ms=16674.944
[v2.remote_request_origin] request_id=v2-benchmark-0-fca6be8396ee trigger_source=benchmark ui_trigger_unix_ms=1786727430831 local_receive_wall_unix_ns=1786727430831733760 local_receive_mono_ns=183555390000000 modal_generator_create_start_wall_unix_ns=1786727453613169900 modal_generator_create_start_mono_ns=183578171000000 modal_generator_created_wall_unix_ns=1786727453617171000 modal_generator_created_mono_ns=183578171000000 modal_first_iteration_start_wall_unix_ns=1786727453617171000 modal_first_iteration_start_mono_ns=183578171000000 modal_submission_attempt_wall_unix_ns=1786727453617171000 modal_submission_attempt_mono_ns=183578171000000 modal_first_remote_event_wall_unix_ns=1786727472214117200 modal_first_remote_event_mono_ns=183596765000000 modal_submission_boundary_source=first_iteration_proxy remote_python_resume_wall_unix_ns=1786727469991322880 restore_method_start_wall_unix_ns=1786727469991322880 restore_method_end_wall_unix_ns=1786727471868240896 modal_method_entry_wall_unix_ns=1786727471913325568 prompt_executor_invoke_start_wall_unix_ns=1786727473222931968 trigger_to_local_receive_ms=0.734 local_receive_to_generator_create_start_ms=22781.436 generator_create_ms=4.001 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=18596.946 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=1876.918 restore_end_to_modal_method_entry_ms=45.085 modal_method_entry_to_executor_ms=1309.606 submission_to_remote_python_resume_ms=16374.152 unexplained_pre_remote_ms=16674.944 modal_input_id=in-01M00M2NEN6181YQXEFPN9M157:1786727454165-0
[v2.local_submission_breakdown.final] request_id=v2-benchmark-0-fca6be8396ee local_receive_to_worker_start_ms=22656.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=22656.0 worker_queue_ms=0.0 plan_build_ms=110.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=22781.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=22781.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19380 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent modal_submission_attempt_unix_ns=1786727453617171000 modal_generator_created_unix_ns=1786727453617171000 modal_first_iteration_start_unix_ns=1786727453617171000 modal_first_remote_event_unix_ns=1786727472214117200 dispatch_to_modal_entry_ms=18296.155 local_receive_to_actual_submission_ms=22781.0 local_receive_to_result_return_ms=58328.213
FETCH ComfyRegistry Data: 60/172
WATERFALL RECONCILIATION (local rebuild) replaced remote PARTIAL report with the full host-reconciled report
WATERFALL RECONCILIATION (local rebuild)
  command_to_response_ms            58799.9
  top_level_accounted_ms            45422.2
  global_residual_ms                -191.5
  global_residual_pct               -0.4
  reconciliation_status             EXCEEDS_TOLERANCE
  controllable_application_wall_ms  42617.3
  platform_wall_ms                  16374.2
  modal_restore_begin_unavailable   no
  OLD vs NEW accounted_ms 42617.3 -> 45422.2 | residual_ms -191.5 -> -191.5
production_adjusted_total_wall_ms=22625.328
[v2.experiment] saved=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_17-10-30\run_001_sample.json
{"run_index": 0, "request_id": "v2-benchmark-0-fca6be8396ee", "identity": {"app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint", "method_name": "run_plan_stream", "gpu": ["RTX-PRO-6000"], "cpu": 12, "memory_mb": 32768, "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "runtime_shape": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "stored_snapshot_model_order": "O0", "restore_count": 1, "request_count": 1, "restored_instance_id": "da7c2b19cbb942d98403e0eacb65c952", "restore_session_id": "9cf0aba65ed2493c86a99ec1a907940b", "container_task_id": "ta-01M00M30E17SPWZB9FPQE29M6R", "modal_container_id": "", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east1", "modal_input_id": "in-01M00M2NEN6181YQXEFPN9M157:1786727454165-0", "container_session_id": "1d9343783e5a46e9"}, "runtime_shape": {"requested": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "deployed": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "observed": {"stage": "request_entry", "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "thread_policy": "TBASE", "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "native_thread_count": 53, "configured_omp": null, "configured_mkl": null, "configured_openblas": null, "configured_numexpr": null, "malloc_arena_max": null, "native_library_settings": {"OMP_NUM_THREADS": "12", "MKL_NUM_THREADS": "12", "OPENBLAS_NUM_THREADS": "12", "NUMEXPR_NUM_THREADS": null, "MALLOC_ARENA_MAX": null}, "torch_intraop_threads": 12, "torch_interop_threads": 14, "actual_torch_intraop_threads": 12, "actual_torch_interop_threads": 14, "requested_torch_intraop_threads": null, "requested_torch_interop_threads": null, "requested_vs_actual_match": true, "status": "baseline_passthrough", "error": "", "trace_id": "b226061ba2e74915", "pid": 2, "thread_native_id": 2, "restored_instance_id": "da7c2b19cbb942d98403e0eacb65c952", "restore_session_id": "9cf0aba65ed2493c86a99ec1a907940b", "legacy_container_session_id": "1d9343783e5a46e9", "container_task_id": "ta-01M00M30E17SPWZB9FPQE29M6R", "modal_input_id": "in-01M00M2NEN6181YQXEFPN9M157:1786727454165-0", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east1", "app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint"}, "stored_snapshot_model_order": "O0", "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "guard": {"changed_axes": [], "allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768}, "construction_order_semantics": "model_construction_order_only"}, "timing": {"wall_ms": 35569.9, "handle_lookup_ms": 4.001, "submission_to_first_remote_event_ms": 18596.946, "command_to_response_ms": 58799.9, "submit2entry_ms": 18300.156, "t3b_to_t8_ms": 16354.638, "restore_total_ms": 1195.205, "pre_sampler_ms": 11147.499, "sampler_ms": 3695.446, "vae_decode_ms": 431.272, "output_collection_ms": 8.654, "snapshot_callback_age_at_restore_ms": 809256.131, "snapshot_callback_to_command_start_ms": 768958.939, "command_start_to_restore_start_ms": 39616.323, "local_timing": {"t0_to_t1_ms": 0.734, "t1_to_queue_enqueue_ms": null, "local_receive_to_enqueue_ms": null, "local_body_read_ms": null, "local_json_parse_ms": null, "local_preflight_ms": null, "local_queue_lock_wait_ms": null, "local_queue_enqueue_ms": null, "queue_wait_before_worker_ms": null, "plan_build_ms": 110.0, "active_profile_ms": 0.0, "restore_plan_build_ms": null, "restore_publish_ms": null, "handle_lookup_ms": 0.0, "payload_serialize_ms": 0.0, "payload_materialization_ms": 0.0, "payload_size_measurement_ms": 0.0, "generator_create_ms": 4.001, "local_residual_ms": 0.0, "clock_reconciliation_residual_ms": 0.0, "route_unattributed_ms": null, "worker_unattributed_ms": null, "reconciliation_status": "incomplete", "missing_stages": ["local_receive_to_enqueue_ms"], "overlap_error": "", "stage_attribution_residual_ms": {"route_unattributed_ms": null, "worker_unattributed_ms": null, "missing_stages": ["local_receive_to_enqueue_ms"], "reconciliation_status": "incomplete", "overlap_error": ""}, "local_receive_to_generator_create_ms": 22781.0, "generator_create_to_first_iteration_ms": 0.0, "first_iteration_to_first_remote_event_ms": 18596.946, "local_receive_to_actual_submission_ms": 22781.0, "trigger_to_local_receive_ms": 0.734, "local_receive_to_generator_create_start_ms": 22781.436, "generator_created_to_first_iteration_ms": 0.0, "remote_python_resume_to_restore_start_ms": 0.0, "restore_method_ms": 1876.918, "restore_end_to_modal_method_entry_ms": 45.085, "modal_method_entry_to_executor_ms": 1309.606, "submission_to_remote_python_resume_ms": 16374.152, "unexplained_pre_remote_ms": 16674.944, "local_result_received_wall_ns": 1786727489159946800, "local_result_received_mono_ns": 183613718000000, "local_receive_to_result_return_ms": 58328.213, "result_received_to_return_ms": 15.0, "remote_result_emit_wall_unix_ns": 1786727489351095986, "remote_result_emit_to_local_receipt_ms": null, "caller_return_wall_unix_ns": 1786727489174946600, "caller_return_mono_ns": 183613734000000, "local_result_received_to_caller_return_ms": 16.0, "modal_restore_begin_wall_unix_ns": null}, "restore_breakdown": {"restore_total_ms": 1195.205, "models_symlink_ms": 3.2, "manager_offline_ms": 0.92, "reload_models_ms": 0.0, "reload_runtime_state_ms": 0.0, "v2_startup_custom_node_source_copy_ms": 358.79, "sync_custom_nodes_ms": 358.89, "install_requirements_ms": 0.01, "v2_startup_comfyui_path_startup_ms": 0.08, "comfyui_path_setup_ms": 0.15, "v2_startup_backend_startup_ms": 16629.52, "backend_startup_ms": 16630.22, "observe_generations_ms": 0.82, "snapshot_restore_ms": 1162.96, "snapshot_callback_age_at_restore_ms": 809256.131, "restore_gpu_state_ms": 902.035, "cuda_init_ms": 6.09, "v2_startup_snapshot_execution_seed_ms": 2.46, "initialize_cuda_ms": 5.894, "snapshot_identity_checks_ms": 0.0, "cpu_snapshot_retargeting_ms": 0.0, "folder_warm_ms": 7935.265}, "early_activation_total_ms": null, "queue_delay_ms": null, "cpu_snapshot_wait_ms": null, "dtype_layout_preparation_ms": null, "post_load_bookkeeping_ms": null, "submission_to_remote_python_resume_ms": 16374.152, "remote_python_resume_to_restore_start_ms": 0.0, "restore_to_method_entry_ms": 45.085, "method_entry_to_first_remote_event_ms": 300.792, "first_remote_event_to_final_result_ms": 16945.83, "transfer_queue_delay_ms": null, "synchronized_transfer_ms": null, "quiesce_wait_ms": null, "graph_activity_ms": 9568.242, "sampler_lane_wait_ms": 0.082, "quiesced_transfer": null}}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-fca6be8396ee  Instance: da7c2b19cbb942d98403e0eacb65c952  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east1
TOTAL WALL:           45.231s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    58.800s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 456.734 ms | 456.734 ms |   1.010% | #                                        |
|   2 | Modal handle and submission                    |    22.785s |    23.242s |  50.376% | ####################                     |
|   3 | Modal pre-Python snapshot restoration          |     2.805s |    26.047s |   6.201% | ##                                       |
|   4 | Python/application restore                     |     1.877s |    27.924s |   4.150% | ##                                       |
|   5 | Restore-to-method entry                        |  45.081 ms |    27.969s |   0.100% | #                                        |
|   6 | Remote method setup                            |     1.310s |    29.279s |   2.896% | #                                        |
|     |   method entry to graph start                  | 820.231 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 819.960 ms |            |          |                                          |
|     |   graph setup                                  | 489.494 ms |            |          |                                          |
|     |   preload check                                | 124.483 ms |            |          |                                          |
|     |   residual before executor invoke              | 291.418 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  17.339 ms |    29.296s |   0.038% | #                                        |
|   8 | Pre-sampler execution                          |     9.551s |    38.847s |  21.116% | ########                                 |
|     |   Conditioning cache exact_hit lookup=164.6... | 164.663 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           |     2.861s |            |          |                                          |
|     |   Node: ImpactSwitch                           |  52.951 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 137.555 ms |            |          |                                          |
|     |   Checkpoint read                              |     6.543s |            |          |                                          |
|     |   Read end -> construction done                |   0.659 ms |            |          |                                          |
|     |   UNET get_model                               |  81.468 ms |            |          |                                          |
|     |   Bind                                         |  33.630 ms |            |          |                                          |
|     |   Synchronized H2D (3.1 GB/s)                  |     4.013s |            |          |                                          |
|     |   H2D end -> UNET ready                        |  98.298 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 130.589 ms |    38.978s |   0.289% | #                                        |
|     |   lane acquired to actual stage                | 130.568 ms |            |          |                                          |
|  10 | Sampling                                       |     4.856s |    43.834s |  10.736% | ####                                     |
|  11 | Post-sampling / VAE transition                 | 905.768 ms |    44.739s |   2.003% | #                                        |
|  12 | VAE decode                                     | 431.272 ms |    45.171s |   0.953% | #                                        |
|     |   VAE load/H2D                                 | 930.016 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 235.502 ms |    45.406s |   0.521% | #                                        |
|     |   PNG encode                                   | 162.999 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  16.000 ms |    45.422s |   0.035% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |    13.569s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.334 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.prompt_executor_breakdown] request_id=v2-benchmark-0-fca6be8396ee exec_to_cached_ms=14.008 dynamic_prompt_ms=0.005 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.02 cache_gather_ms=0.162 cleanup_gc_ms=1.344 residual_ms=12.477 c2f_cached_to_first_node_ms=0.763 c2f_topo_walk_ms=0.6 c2f_topo_input_info_ms=0.103 c2f_topo_other_ms=0.497 c2f_stage_ms=1.435 c2f_first_node_prefix_ms=0.155 c2f_residual_ms=-1.427 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=8ffd5d7760804fa9ba99b1419063ecd931de3044a0f30a33c8a000a3197235c9 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=4.011 topo_lazy_hits=36
[v2.conditioning_exact_hit_breakdown] request_id=v2-benchmark-0-fca6be8396ee decision=exact_hit lookup_wall_ms=164.663 total_ms=164.025 key_build_ms=0.242 lock_wait_ms=0.002 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=34 entry_lookup_ms=117.21 header_bytes=3752 data_bytes=2900184 lru_touch_ms=44.892 lru_touch_mode=sync children_ms=162.346 residual_ms=1.679 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=353.778 prefetch_join_timeout=0 prefetch_overlap_ms=497.51 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=884.832 volume_reload_ms=0.0
[v2.folder_warm] request_id=v2-benchmark-0-fca6be8396ee folder_warm_ms=7935.265 folder_warm_folders=29
[v2.input_types_warm] request_id=v2-benchmark-0-fca6be8396ee input_types_warm_ms=4281.03 input_types_warm_classes=31
[v2.png_output] request_id=v2-benchmark-0-fca6be8396ee compress_level=1 png_encode_ms=162.992 png_compress_ms=158.087 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
[v2.host_submission_breakdown] request_id=v2-benchmark-0-fca6be8396ee command_start_to_python_first_line_ms=167.735 python_first_line_to_local_receive_ms=288.999 local_receive_to_registry_start_ms=0.0 node_registry_init_ms=22605.437 registry_end_to_worker_start_ms=57.0 worker_start_to_plan_build_start_ms=1.0 plan_build_ms=110.0 plan_build_to_transport_entry_ms=7.999 transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=4.001 payload_serialize_ms=0.0 generator_create_ms=4.001 generator_created_to_submission_ms=0.0 local_receive_to_submission_ms=22781.0 submission_boundary_source=first_anext first_remote_signal_ms=18596.946 scheduling_ms=13569.182 scheduling_source=modal_app_log
BATCH B ACCEPTANCE

Batch A preserved:
PASS

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: skipped_generation_match
invoked: NO
reload ms: 0.0
generation check: YES
local only: YES

Snapshot hygiene:
enabled: 1
before RSS: 27008184.0
after RSS: 24727496.0
delta: -2280688.0
trim status: 1
manifest status: {'vmsize': 30360836, 'vmrss': 27006876, 'vmdata': 26250464, 'threads': 46}

Stage 13:
gate: READY
expectation: 1
total: 74.3
children: 8
largest child: waterfall_build_ms=38.9
reconciliation: 0.0

Host telemetry:
overhead (Tier A): 15.1
Tier B forensic probe: 95.1
total probe: 110.2
forensic trigger: YES

TOTAL WALL: 35569.9 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: PASS
FETCH ComfyRegistry Data: 65/172
FETCH ComfyRegistry Data: 70/172
FETCH ComfyRegistry Data: 75/172
FETCH ComfyRegistry Data: 80/172
FETCH ComfyRegistry Data: 85/172
FETCH ComfyRegistry Data: 90/172
FETCH ComfyRegistry Data: 95/172
FETCH ComfyRegistry Data: 100/172
FETCH ComfyRegistry Data: 105/172
FETCH ComfyRegistry Data: 110/172
FETCH ComfyRegistry Data: 115/172
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=hit
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-1-7cbb6e141672 local_receive_to_worker_start_ms=0.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=0.0 worker_queue_ms=0.0 plan_build_ms=16.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19284 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] decision=persistent_hit
FETCH ComfyRegistry Data: 120/172
FETCH ComfyRegistry Data: 125/172
FETCH ComfyRegistry Data: 130/172
FETCH ComfyRegistry Data: 135/172
FETCH ComfyRegistry Data: 140/172
FETCH ComfyRegistry Data: 145/172
FETCH ComfyRegistry Data: 150/172
FETCH ComfyRegistry Data: 155/172
FETCH ComfyRegistry Data: 160/172
FETCH ComfyRegistry Data: 165/172
FETCH ComfyRegistry Data: 170/172
FETCH ComfyRegistry Data [DONE]
FETCH DATA from: https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json [DONE]
[v2.local_submission_breakdown] request_id=v2-benchmark-1-7cbb6e141672 local_receive_to_worker_start_ms=0.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=0.0 worker_queue_ms=0.0 plan_build_ms=16.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19284 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.request_origin] request_id=v2-benchmark-1-7cbb6e141672 trigger_source=benchmark local_prompt_enqueued_unix_ns=None local_prompt_ack_ready_unix_ns=None modal_generator_created_unix_ns=1786727528229475700 modal_submission_attempt_unix_ns=1786727528229475700 modal_first_event_received_unix_ns=1786727605407688500 modal_first_iteration_start_unix_ns=1786727528229475700 modal_first_remote_event_unix_ns=1786727605407688500 dispatch_to_modal_entry_ms=77149.589 local_receive_to_actual_submission_ms=16.0 local_receive_to_result_return_ms=94914.606 t0_to_t1_ms=0.933 t1_to_queue_enqueue_ms=None local_receive_to_enqueue_ms=None queue_wait_before_worker_ms=None plan_build_ms=16.0 active_profile_ms=0.0 handle_lookup_ms=0.0 payload_serialize_ms=0.0 local_residual_ms=0.0 clock_reconciliation_residual_ms=0.0 route_unattributed_ms=None worker_unattributed_ms=None reconciliation_status=incomplete missing_stages=local_receive_to_enqueue_ms overlap_error= modal_input_id=in-01M00M4Y6PPWK66F5PHJRBFZRW:1786727528662-0 trigger_to_local_receive_ms=0.933 local_receive_to_generator_create_start_ms=25.542 generator_create_ms=2.001 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=77178.213 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=1282.222 restore_end_to_modal_method_entry_ms=49.55 modal_method_entry_to_executor_ms=764.744 submission_to_remote_python_resume_ms=75817.817 unexplained_pre_remote_ms=75846.44
[v2.remote_request_origin] request_id=v2-benchmark-1-7cbb6e141672 trigger_source=benchmark ui_trigger_unix_ms=1786727528201 local_receive_wall_unix_ns=1786727528201932544 local_receive_mono_ns=183652765000000 modal_generator_create_start_wall_unix_ns=1786727528227474800 modal_generator_create_start_mono_ns=183652781000000 modal_generator_created_wall_unix_ns=1786727528229475700 modal_generator_created_mono_ns=183652781000000 modal_first_iteration_start_wall_unix_ns=1786727528229475700 modal_first_iteration_start_mono_ns=183652781000000 modal_submission_attempt_wall_unix_ns=1786727528229475700 modal_submission_attempt_mono_ns=183652781000000 modal_first_remote_event_wall_unix_ns=1786727605407688500 modal_first_remote_event_mono_ns=183729968000000 modal_submission_boundary_source=first_iteration_proxy remote_python_resume_wall_unix_ns=1786727604047292416 restore_method_start_wall_unix_ns=1786727604047292416 restore_method_end_wall_unix_ns=1786727605329514752 modal_method_entry_wall_unix_ns=1786727605379065088 prompt_executor_invoke_start_wall_unix_ns=1786727606143808768 trigger_to_local_receive_ms=0.933 local_receive_to_generator_create_start_ms=25.542 generator_create_ms=2.001 generator_created_to_first_iteration_ms=0.0 first_iteration_to_first_remote_event_ms=77178.213 remote_python_resume_to_restore_start_ms=0.0 restore_method_ms=1282.222 restore_end_to_modal_method_entry_ms=49.55 modal_method_entry_to_executor_ms=764.744 submission_to_remote_python_resume_ms=75817.817 unexplained_pre_remote_ms=75846.44 modal_input_id=in-01M00M4Y6PPWK66F5PHJRBFZRW:1786727528662-0
[v2.local_submission_breakdown.final] request_id=v2-benchmark-1-7cbb6e141672 local_receive_to_worker_start_ms=0.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=0.0 worker_queue_ms=0.0 plan_build_ms=16.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=0.0 payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=16.0 generator_create_ms=0.0 generator_created_to_first_iteration_ms=invalid_negative local_receive_to_actual_submission_ms=16.0 measured_children_ms=absent residual_ms=absent reconciliation_status=overlap profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19284 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent modal_submission_attempt_unix_ns=1786727528229475700 modal_generator_created_unix_ns=1786727528229475700 modal_first_iteration_start_unix_ns=1786727528229475700 modal_first_remote_event_unix_ns=1786727605407688500 dispatch_to_modal_entry_ms=77149.589 local_receive_to_actual_submission_ms=16.0 local_receive_to_result_return_ms=94914.606
WATERFALL RECONCILIATION (local rebuild) replaced remote PARTIAL report with the full host-reconciled report
WATERFALL RECONCILIATION (local rebuild)
  command_to_response_ms            94946.1
  top_level_accounted_ms            24794.6
  global_residual_ms                -221.0
  global_residual_pct               -0.9
  reconciliation_status             EXCEEDS_TOLERANCE
  controllable_application_wall_ms  19349.2
  platform_wall_ms                  75817.8
  modal_restore_begin_unavailable   no
  OLD vs NEW accounted_ms 19349.2 -> 24794.6 | residual_ms -221.0 -> -221.0
production_adjusted_total_wall_ms=1968.134
[v2.experiment] saved=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-14_17-10-30\run_002_sample.json
{"run_index": 1, "request_id": "v2-benchmark-1-7cbb6e141672", "identity": {"app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint", "method_name": "run_plan_stream", "gpu": ["RTX-PRO-6000"], "cpu": 12, "memory_mb": 32768, "fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "runtime_shape": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "stored_snapshot_model_order": "O0", "restore_count": 1, "request_count": 1, "restored_instance_id": "1877e583dc4e4876a025f9dbc1c1ff57", "restore_session_id": "eae2b16f9d4349b5848afd5fc583c6ba", "container_task_id": "ta-01M00M713RGQ0A55D9HWD4RBJR", "modal_container_id": "", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east1", "modal_input_id": "in-01M00M4Y6PPWK66F5PHJRBFZRW:1786727528662-0", "container_session_id": "1d9343783e5a46e9"}, "runtime_shape": {"requested": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "deployed": {"thread_policy": "TBASE", "torch_intraop_threads": null, "torch_interop_threads": null, "omp_num_threads": null, "mkl_num_threads": null, "openblas_num_threads": null, "numexpr_num_threads": null, "malloc_arena_max": null, "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null}, "observed": {"stage": "request_entry", "runtime_shape_fingerprint": "f504e296c398bdcb2c4c07e2", "runtime_shape_label": null, "thread_policy": "TBASE", "snapshot_model_order": "O0", "cpu_request": 12, "memory_request": 32768, "native_thread_count": 53, "configured_omp": null, "configured_mkl": null, "configured_openblas": null, "configured_numexpr": null, "malloc_arena_max": null, "native_library_settings": {"OMP_NUM_THREADS": "12", "MKL_NUM_THREADS": "12", "OPENBLAS_NUM_THREADS": "12", "NUMEXPR_NUM_THREADS": null, "MALLOC_ARENA_MAX": null}, "torch_intraop_threads": 12, "torch_interop_threads": 14, "actual_torch_intraop_threads": 12, "actual_torch_interop_threads": 14, "requested_torch_intraop_threads": null, "requested_torch_interop_threads": null, "requested_vs_actual_match": true, "status": "baseline_passthrough", "error": "", "trace_id": "b7682a2016d84833", "pid": 2, "thread_native_id": 2, "restored_instance_id": "1877e583dc4e4876a025f9dbc1c1ff57", "restore_session_id": "eae2b16f9d4349b5848afd5fc583c6ba", "legacy_container_session_id": "1d9343783e5a46e9", "container_task_id": "ta-01M00M713RGQ0A55D9HWD4RBJR", "modal_input_id": "in-01M00M4Y6PPWK66F5PHJRBFZRW:1786727528662-0", "image_id": "im-B1LdSHCggPdDMnEPTU8kop", "cloud": "CLOUD_PROVIDER_GCP", "region": "us-east1", "app_name": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypoint"}, "stored_snapshot_model_order": "O0", "snapshot_target_fingerprint": "30f9278d77368a23d886169ce332b534c8369fc7f4c38818357b082aadde05ce", "guard": {"changed_axes": [], "allow_multi_axis": false, "baseline_cpu_request": 12, "baseline_memory_request": 32768}, "construction_order_semantics": "model_construction_order_only"}, "timing": {"wall_ms": 94926.1, "handle_lookup_ms": 2.001, "submission_to_first_remote_event_ms": 77178.213, "command_to_response_ms": 192772.1, "submit2entry_ms": 77151.59, "t3b_to_t8_ms": 17156.771, "restore_total_ms": 921.573, "pre_sampler_ms": 11077.752, "sampler_ms": 3765.767, "vae_decode_ms": 1172.067, "output_collection_ms": 10.617, "snapshot_callback_age_at_restore_ms": 942990.519, "snapshot_callback_to_command_start_ms": 768958.939, "command_start_to_restore_start_ms": 173672.292, "local_timing": {"t0_to_t1_ms": 0.933, "t1_to_queue_enqueue_ms": null, "local_receive_to_enqueue_ms": null, "local_body_read_ms": null, "local_json_parse_ms": null, "local_preflight_ms": null, "local_queue_lock_wait_ms": null, "local_queue_enqueue_ms": null, "queue_wait_before_worker_ms": null, "plan_build_ms": 16.0, "active_profile_ms": 0.0, "restore_plan_build_ms": null, "restore_publish_ms": null, "handle_lookup_ms": 0.0, "payload_serialize_ms": 0.0, "payload_materialization_ms": 0.0, "payload_size_measurement_ms": 0.0, "generator_create_ms": 2.001, "local_residual_ms": 0.0, "clock_reconciliation_residual_ms": 0.0, "route_unattributed_ms": null, "worker_unattributed_ms": null, "reconciliation_status": "incomplete", "missing_stages": ["local_receive_to_enqueue_ms"], "overlap_error": "", "stage_attribution_residual_ms": {"route_unattributed_ms": null, "worker_unattributed_ms": null, "missing_stages": ["local_receive_to_enqueue_ms"], "reconciliation_status": "incomplete", "overlap_error": ""}, "local_receive_to_generator_create_ms": 16.0, "generator_create_to_first_iteration_ms": 0.0, "first_iteration_to_first_remote_event_ms": 77178.213, "local_receive_to_actual_submission_ms": 16.0, "trigger_to_local_receive_ms": 0.933, "local_receive_to_generator_create_start_ms": 25.542, "generator_created_to_first_iteration_ms": 0.0, "remote_python_resume_to_restore_start_ms": 0.0, "restore_method_ms": 1282.222, "restore_end_to_modal_method_entry_ms": 49.55, "modal_method_entry_to_executor_ms": 764.744, "submission_to_remote_python_resume_ms": 75817.817, "unexplained_pre_remote_ms": 75846.44, "local_result_received_wall_ns": 1786727623116538300, "local_result_received_mono_ns": 183747671000000, "local_receive_to_result_return_ms": 94914.606, "result_received_to_return_ms": 29.553, "remote_result_emit_wall_unix_ns": 1786727623337767947, "remote_result_emit_to_local_receipt_ms": null, "caller_return_wall_unix_ns": 1786727623147073100, "caller_return_mono_ns": 183747703000000, "local_result_received_to_caller_return_ms": 32.0, "modal_restore_begin_wall_unix_ns": null}, "restore_breakdown": {"restore_total_ms": 921.573, "models_symlink_ms": 3.2, "manager_offline_ms": 0.92, "reload_models_ms": 0.0, "reload_runtime_state_ms": 0.0, "v2_startup_custom_node_source_copy_ms": 358.79, "sync_custom_nodes_ms": 358.89, "install_requirements_ms": 0.01, "v2_startup_comfyui_path_startup_ms": 0.08, "comfyui_path_setup_ms": 0.15, "v2_startup_backend_startup_ms": 16629.52, "backend_startup_ms": 16630.22, "observe_generations_ms": 0.82, "snapshot_restore_ms": 889.01, "snapshot_callback_age_at_restore_ms": 942990.519, "restore_gpu_state_ms": 842.562, "cuda_init_ms": 3.42, "v2_startup_snapshot_execution_seed_ms": 1.89, "initialize_cuda_ms": 3.327, "snapshot_identity_checks_ms": 0.0, "cpu_snapshot_retargeting_ms": 0.0, "folder_warm_ms": 8078.083}, "early_activation_total_ms": null, "queue_delay_ms": null, "cpu_snapshot_wait_ms": null, "dtype_layout_preparation_ms": null, "post_load_bookkeeping_ms": null, "submission_to_remote_python_resume_ms": 75817.817, "remote_python_resume_to_restore_start_ms": 0.0, "restore_to_method_entry_ms": 49.55, "method_entry_to_first_remote_event_ms": 28.623, "first_remote_event_to_final_result_ms": 17708.85, "transfer_queue_delay_ms": null, "synchronized_transfer_ms": null, "quiesce_wait_ms": null, "graph_activity_ms": 9576.548, "sampler_lane_wait_ms": 0.129, "quiesced_transfer": null}}
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 2 (local reconcile)
Request: v2-benchmark-1-7cbb6e141672  Instance: 1877e583dc4e4876a025f9dbc1c1ff57  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east1
TOTAL WALL:           24.574s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    94.946s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.933 ms |   0.933 ms |   0.004% | #                                        |
|   2 | Modal handle and submission                    |  27.543 ms |  28.476 ms |   0.112% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     5.445s |     5.474s |  22.159% | #########                                |
|   4 | Python/application restore                     |     1.282s |     6.756s |   5.218% | ##                                       |
|   5 | Restore-to-method entry                        |  49.548 ms |     6.806s |   0.202% | #                                        |
|   6 | Remote method setup                            | 764.790 ms |     7.570s |   3.112% | #                                        |
|     |   method entry to graph start                  | 556.325 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 556.279 ms |            |          |                                          |
|     |   graph setup                                  | 208.465 ms |            |          |                                          |
|     |   residual before executor invoke              |  31.147 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |   9.942 ms |     7.580s |   0.040% | #                                        |
|   8 | Pre-sampler execution                          |     9.567s |    17.147s |  38.930% | ################                         |
|     |   Conditioning cache exact_hit lookup=48.950ms |  48.950 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 801.599 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  74.146 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 188.642 ms |            |          |                                          |
|     |   Checkpoint read                              |     6.580s |            |          |                                          |
|     |   Read end -> construction done                |   0.823 ms |            |          |                                          |
|     |   UNET get_model                               | 126.475 ms |            |          |                                          |
|     |   Bind                                         |  46.095 ms |            |          |                                          |
|     |   Synchronized H2D (3.6 GB/s)                  |     3.380s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.631 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 179.193 ms |    17.326s |   0.729% | #                                        |
|     |   lane acquired to actual stage                | 179.148 ms |            |          |                                          |
|  10 | Sampling                                       |     5.060s |    22.386s |  20.590% | ########                                 |
|  11 | Post-sampling / VAE transition                 | 943.379 ms |    23.329s |   3.839% | ##                                       |
|  12 | VAE decode                                     |     1.172s |    24.501s |   4.770% | ##                                       |
|     |   VAE load/H2D                                 |     1.596s |            |          |                                          |
|  13 | Output encode / descriptor                     | 261.382 ms |    24.763s |   1.064% | #                                        |
|     |   PNG encode                                   | 181.239 ms |            |          |                                          |
|  14 | Local result handling / caller return          |  32.000 ms |    24.795s |   0.130% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |    70.373s |            |          |                                          |
|     | RECONCILIATION                                 |   0.238 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
[v2.prompt_executor_breakdown] request_id=v2-benchmark-1-7cbb6e141672 exec_to_cached_ms=8.053 dynamic_prompt_ms=0.003 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.018 cache_gather_ms=0.17 cleanup_gc_ms=1.867 residual_ms=5.995 c2f_cached_to_first_node_ms=1.283 c2f_topo_walk_ms=0.606 c2f_topo_input_info_ms=0.113 c2f_topo_other_ms=0.493 c2f_stage_ms=1.708 c2f_first_node_prefix_ms=0.684 c2f_residual_ms=-1.715 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=8ffd5d7760804fa9ba99b1419063ecd931de3044a0f30a33c8a000a3197235c9 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.519 topo_lazy_hits=36
[v2.conditioning_exact_hit_breakdown] request_id=v2-benchmark-1-7cbb6e141672 decision=exact_hit lookup_wall_ms=48.95 total_ms=48.68 key_build_ms=0.505 lock_wait_ms=0.002 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=34 entry_lookup_ms=17.285 header_bytes=3752 data_bytes=2900184 lru_touch_ms=30.15 lru_touch_mode=sync children_ms=47.942 residual_ms=0.738 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=41.283 prefetch_join_timeout=0 prefetch_overlap_ms=108.777 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=638.756 volume_reload_ms=0.0
[v2.folder_warm] request_id=v2-benchmark-1-7cbb6e141672 folder_warm_ms=8078.083 folder_warm_folders=29
[v2.input_types_warm] request_id=v2-benchmark-1-7cbb6e141672 input_types_warm_ms=1612.705 input_types_warm_classes=31
[v2.png_output] request_id=v2-benchmark-1-7cbb6e141672 compress_level=1 png_encode_ms=181.308 png_compress_ms=169.504 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
[v2.host_submission_breakdown] request_id=v2-benchmark-1-7cbb6e141672 command_start_to_python_first_line_ms=167.735 python_first_line_to_local_receive_ms=97659.198 local_receive_to_registry_start_ms=absent node_registry_init_ms=22605.437 registry_end_to_worker_start_ms=74764.761 worker_start_to_plan_build_start_ms=0.0 plan_build_ms=16.0 plan_build_to_transport_entry_ms=6.028 transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=2.001 payload_serialize_ms=0.0 generator_create_ms=2.001 generator_created_to_submission_ms=0.0 local_receive_to_submission_ms=16.0 submission_boundary_source=first_anext first_remote_signal_ms=77178.213 scheduling_ms=70372.502 scheduling_source=modal_app_log
[v2.plan_proof] schema=1 payload=yes validated=True outputs=2 wf_hash=2e43d4c0ba3b82c0 dep_complete=True reg_proof=1 memo=hit
cpu_snapshot_unet_mode=reuse
[v2.benchmark] phase=execute_plan_start
[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0 consumer_requires_publication=0 checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0
[v2.restore_publish] skipped reason=flag_disabled
[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=2e43d4c0ba3b82c0 loader_nodes=3 sampler_nodes=1 reachable_nodes=43 static_signatures=43
[v2.local_submission_breakdown.pre_dispatch] request_id=v2-benchmark-2-d433561e1881 local_receive_to_worker_start_ms=0.0 worker_start_to_normalize_start_ms=0.0 normalize_production_options_ms=0.0 normalize_end_to_trace_construct_start_ms=0.0 runtime_trace_construct_ms=0.0 trace_construct_to_options_copy_start_ms=0.0 benchmark_options_copy_ms=0.0 options_copy_to_client_id_start_ms=0.0 client_id_generation_ms=0.0 client_id_end_to_plan_call_ms=0.0 plan_call_to_function_entry_ms=0.0 worker_start_to_plan_build_ms=0.0 local_receive_to_plan_build_start_ms=0.0 worker_queue_ms=0.0 plan_build_ms=16.0 plan_build_to_execute_plan_entry_ms=0.0 execute_plan_entry_to_plan_materialization_ms=0.0 plan_materialization_ms=0.0 plan_materialization_to_active_profile_ms=0.0 active_profile_ms=0.0 restore_plan_build_ms=absent restore_publish_ms=absent restore_publish_to_transport_entry_ms=absent transport_entry_to_handle_lookup_ms=0.0 handle_lookup_ms=absent payload_materialization_ms=0.0 payload_size_measurement_ms=0.0 payload_size_to_serialize_end_ms=0.0 payload_ready_to_modal_call_ms=0.0 local_receive_to_modal_call_ms=31.0 generator_create_ms=absent generator_created_to_first_iteration_ms=absent local_receive_to_actual_submission_ms=absent measured_children_ms=absent residual_ms=absent reconciliation_status=incomplete profile_cache_hit=False profile_remote_call_performed=False profile_checker_matched=False restore_publish_cache_hit=absent restore_remote_call_performed=absent handle_cache_hit=absent plan_to_dict_count=1 payload_bytes=19284 active_profile_local_ms=0.0 active_profile_cache_lookup_ms=0.0 active_profile_checker_ms=0.0 active_profile_setter_ms=0.0 active_profile_total_ms=0.0 created_modal_client=False performed_cls_from_name=False constructed_class_instance=False input_image_count=0 workflow_node_count=43 unmeasured_boundary=absent
[v2.local_handle] decision=persistent_hit

`
