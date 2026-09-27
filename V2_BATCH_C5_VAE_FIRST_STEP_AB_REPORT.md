# V2 Batch C5 — VAE First-Step A/B Experiment Report (sampling_end vs sampling_first_step)

Date: 2026-08-14
Mode: causal A/B, one valid run per arm (minimum useful data), CURRENT main.
Commit: none. Deploys: 1 (Arm B deploy #4; the first Arm-B deploy attempt failed
transiently before producing any deployment — see §3). Modal requests: 3
(Arm A valid 1; Arm B 1 invalid/not-counted + 1 valid).

Standing campaign rule applied: start with the minimum (1 valid A + 1 valid B);
result is ambiguous due to host variance → **STOP, no additional runs purchased**.

---

## 1. Executive summary

- **Arm A (sampling_end, deploy #3):** valid true-cold run. VAE activation at
  sampling_end: `load_wall_ms = 759.0 ms` (full-load worker, on the critical
  path), decode join 29.6 ms. Non-scheduling 12,123.8 ms, sampling 4,797.7 ms.
- **Arm B (sampling_first_step, deploy #4):** valid true-cold run. Exactly one
  VAE activation triggered at `first_sampler_step`; pre-copy of the
  snapshot-restored VAE params = **70.2 ms** (`load_wall_ms`), fully inside the
  sampling window (`overlap_ms = 3,775.8 ms`); decode join **0.008 ms**; no
  fallback, no duplicate activation, no UNET touch; output SHA **identical** to
  Arm A.
- **Structural C5 behavior: CONFIRMED** (one transfer, actual overlap, event
  order, output parity).
- **Performance claim: INCONCLUSIVE.** Arm B ran on a materially heavier host
  (GCP us-east4 vs us-east1; every unrelated stage slower: pre-Python restore
  8.65 s vs 2.50 s, UNET H2D 3.99 s vs 2.01 s, pre-sampler 5.09 s vs 3.03 s),
  so the B−A stage deltas (non-scheduling +10.32 s, sampling +414.8 ms,
  post-sampling/VAE +300.4 ms) cannot be attributed to the VAE-mode change at
  n=1 per arm. Additionally, the work that actually moved under sampling was
  only **70.2 ms / 34.7 MB** — far below the ~0.9 s premise — so the
  theoretically claimable win is small and invisible under the host noise.
- **No C5 performance saving is claimed.** `sampling_end` remains the
  recommended production default; `sampling_first_step` stays opt-in.

## 2. Protocol and run inventory

| Step | Time (UTC) | Result | Notes |
|---|---|---|---|
| A-1 | 20:11:03 (`v2_2026-08-14_20-11-03`) | **VALID** — Batch A/B/C PASS in-console, exit 0 | deploy #3, `sampling_end`; no redeploy (per brief) |
| B deploy #1 | 20:1x | **FAILED transiently** | Modal build-context race: `tests\__pycache__\test_model_library.cpython-311.pyc was modified during build process` (concurrent Python touching pyc during the build scan). No image produced, `.deployed_state.json` untouched. Retried. |
| B deploy #2 | 20:22:45Z | **SUCCESS — deploy #4** | `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_first_step` one-off env override (launcher defaults unchanged); image `im-QUAP7pDTMAOCBSw856erlQ`; C1 identity triple frozen |
| B-1 | ~20:2x | **NOT COUNTED** (per brief) | Known post-deploy B1 convergence transition: `reloaded_generation_mismatch`, reload 108.6 ms; all other gates healthy |
| B-2 | 20:26:02 (`v2_2026-08-14_20-26-02`) | **VALID** — Batch A/B/C PASS in-console, exit 0 | B1 `exact_match`; B is this run |

Arm B deploy identity (`.deployed_state.json`, `source: container_readback`):
`deployment_combined_hash=f4cda0ff0461beeb7bdb4402217aa2635781dcf15ebf3dcfb94e3e531bc05777`,
`custom_nodes_generation=0fa72e8f58a71cfd2859a0b64fbc6545`,
`overall_dependency_hash=be68be1945de2a29c5bb09360d3056d6f3d6d4e3ed8c203d2d0fa82d86d3076c`,
`deployed_at=2026-08-14T20:22:45.877573+00:00`, `comfyui_core_match=1`.

## 3. Structural validity (both arms)

| Check | Arm A | Arm B |
|---|---|---|
| Fresh / restore_count / request_count | YES / 1 / 1 | YES / 1 / 1 |
| Batch B corrected acceptance | PASS | PASS |
| Batch C strict acceptance | PASS | PASS |
| C1 plan identity source | `persisted_record` | `persisted_record` |
| plan parity (deployment / generation / dependency) | true / true / true | true / true / true |
| future_fast_path_eligible | true | true |
| plan_proof_decision / consumed | `plan_validation_fast_path` / true | `plan_validation_fast_path` / true |
| cert source / consumed | `plan_validation` / true | `plan_validation` / true |
| no cert volume fallback | yes | yes |
| B1 runtime-state skip | `exact_match`, invoked=0, 0.0 ms | `exact_match`, invoked=0, 0.0 ms |
| models-volume skip | `exact_match`, invoked=0 | `exact_match`, invoked=0 |
| signature_cache_hit / topo_lazy_hits | true (volume, 2.8 ms) / 36 | true (volume, 3.6 ms) / 36 |
| conditioning | `exact_hit` | `exact_hit` |
| exactly one UNET read/bind/H2D | 1 (2,010.8 ms, 453 params) | 1 (3,994.6 ms, 453 params) |
| Stage13 | 72.8 ms, 8 children | 71.1 ms, 8 children |
| host telemetry Tier A / forensic | 11.6 ms / none | 6.3 ms / none |
| VAE activations | exactly 1 | exactly 1 |
| output PNG sha | `20b10e1f…e5260` | `20b10e1f…e5260` (**identical**) |

## 4. Side-by-side measurements

All timings are C3 NON-SCHEDULING-consistent; never the old TOTAL WALL metric.

### Primary

| Metric | Arm A (sampling_end) | Arm B (sampling_first_step) | B − A |
|---|---|---|---|
| COMMAND -> RESPONSE | 38,472.0 ms | 59,864.4 ms | +21,392.4 ms |
| Command (without scheduling) -> Response | 12,123.8 ms | 22,448.7 ms | **+10,324.9 ms** |
| Scheduling time | 26,348.2 ms | 37,415.8 ms | +11,067.6 ms |

(Arithmetic reconciles both arms: A 12,123.8 + 26,348.2 = 38,472.0; B 22,448.7
+ 37,415.8 = 59,864.5 ≈ 59,864.4.)

### VAE-specific

| Metric | Arm A | Arm B | B − A |
|---|---|---|---|
| Sampling duration | 4,797.7 ms | 5,212.5 ms | +414.8 ms |
| sampling_end timestamp (event) | sampling_end source `sampler_sample_wrapper` | same | — |
| VAE activation trigger | `sampling_end` | `sampling_first_step` (at `first_sampler_step`) | — |
| scheduled → worker/load start | 2.39 ms | 28.34 ms (thread spawn) | — |
| VAE load wall (`load_wall_ms`) | **759.0 ms** (full-load worker) | **70.2 ms** (transfer-only pre-copy) | −688.8 ms |
| precopy_wall_ms | n/a (A worker records no precopy) | 70.221 | — |
| overlap_ms | 0 (activation after sampling_end) | **3,775.785** | — |
| overlap fraction = overlap/precopy | 0 | 3,775.785 / 70.221 = **53.8** | — |
| sampling_end_wait_ms (worker wait before sampling_end) | 0 | 3,705.41 | — |
| consumed join_wait_ms | 29.565 | **0.008** | −29.6 ms |
| phase-3 lane_wait_ms | 1.903 | 0.0 | — |
| post-sampling / VAE transition stage | 731.5 ms | 991.5 ms | +260.0 ms |
| VAE decode stage | 376.2 ms | 416.6 ms | +40.4 ms |
| transfer_count | 1 | 1 | 0 |
| GPU allocated delta | n/a (not recorded by A-path worker) | 34,693,120 B (34.7 MB) | — |
| fallback reason | none (terminal ready/ok) | none (terminal ready/ok) | — |

Interpretation of the VAE rows (see also §6): A's 759.0 ms is the **full-load
worker** activation at sampling_end (`residency_status=resident_full`,
`vae_prepare_start/end` events present) — on the critical path. B's 70.2 ms is
the **transfer-only pre-copy** of the snapshot-restored VAE inner model
(`residency_status=gpu_resident`, no prepare events) — entirely off the
critical path, with the decode joining in 0.008 ms. These are not the same work
scope, so "759 → 70 ms moved under sampling" is **not** the correct reading;
the correct reading is: the pure param H2D was ~70 ms in B and it ran during
sampling; the other ~689 ms of A's load_wall is full-load-worker scope
(prep/restore work) that the B path did not re-perform at sampling_end. Output
parity (identical SHA) confirms functional equivalence of the consumed VAE.

### Context / confounders

| Metric | Arm A | Arm B | Note |
|---|---|---|---|
| provider / region | GCP / us-east1 | GCP / us-east4 | **different hosts** |
| image | im-vWYB6KSQgvn7R7h9pEuhe0 | im-QUAP7pDTMAOCBSw856erlQ | expected (B deploy) |
| CPU (vendor/family/model/visible) | AMD 191/2, 28 | AMD 191/2, 28 | same family |
| CPU peak / >16-core | n/a in artifacts | n/a in artifacts | not present in these artifacts |
| pre-Python restore | 2,496.2 ms | 8,654.8 ms | B 3.5× |
| Python/application restore | 489.3 ms | 1,432.7 ms | B 2.9× |
| remote method setup | 192.5 ms | 800.0 ms | B 4.2× |
| pre-sampler (incl. checkpoint read) | 3,034.1 ms (read 1,036 ms) | 5,091.7 ms (read 1,723 ms) | B 1.7× |
| UNET H2D / GB/s | 2,010.8 ms / 6.1 GB/s | 3,994.6 ms / 3.1 GB/s | B 2× |
| Stage13 | 72.8 ms | 71.1 ms | comparable |
| Tier A | 11.6 ms | 6.3 ms | comparable |
| slow-H2D forensic | none | none | none |

## 5. Required calculations

1. **B − A non-scheduling wall** = 22,448.7 − 12,123.8 = **+10,324.9 ms** (host-dominated; the B host was slower on every unrelated stage by 1.7–4.2×).
2. **B − A sampling wall** = 5,212.5 − 4,797.7 = **+414.8 ms** (host-confounded; a 70 ms / 34.7 MB H2D pre-copy cannot plausibly account for it).
3. **B − A post-sampling/VAE transition wall** = (991.5 + 416.6) − (731.5 + 376.2) = 1,408.1 − 1,107.7 = **+300.4 ms** (host-confounded; the VAE activation segment itself was removed from B's critical path — see 6 — yet the stage total is larger because B's host was slower).
4. **VAE transfer overlap fraction** = 3,775.785 / 70.221 = **53.8×** (the 70 ms transfer sat entirely inside the 5.2 s sampling window; the fraction is dominated by the worker's idle wait — after its 70 ms pre-copy it waited 3,705 ms for sampling_end, then bound the lane with 0.0 ms lane wait).
5. **Remaining VAE wait after sampling** = consumed join **0.008 ms** (decode did not wait; the worker's own pre-sampling_end idle wait was 3,705.4 ms — that wait is off the critical path by construction).
6. **Amount of the original A VAE-transfer/post-sampling cost that disappeared from the critical path** = A's VAE activation segment at sampling_end (load 759.0 + lane 1.9 + join 29.6 ≈ **790.5 ms**) → B's post-sampling VAE activation ≈ **0 ms** (join 0.008, lane 0.0). Of that ~790 ms, the portion that genuinely moved under sampling is the **70.2 ms / 34.7 MB pre-copy**; the remainder is A-path full-load-worker work (policy prep/restore scope) that the transfer-only B path did not perform at sampling_end (and, per identical output SHA, did not need to for correctness).

**Win test (brief §"Required calculations"):** a useful C5 win requires BOTH
meaningful VAE work moved under sampling AND no equal sampling slowdown.
- Moved under sampling: 70.2 ms (small; the ~0.9 s premise did not materialize as transfer work — the A-path 759 ms load_wall is a broader work scope).
- Sampling slowdown: +414.8 ms (host-confounded; cannot be attributed, but also cannot be excluded at n=1).
→ **No win claimable.**

## 6. VAE event sequences (verbatim from artifacts)

### Arm A (sampling_end)

```
sampling_start                                    (node 1242, 8 steps)
first_sampler_step                                (watchdog hook only — VAE not scheduled here in this mode)
sampling_end                    duration_ms=4797.712
vae_early_activation_scheduled  mode=sampling_end trigger=sampling_end source=snapshot_vae
vae_early_activation_load_start mode=sampling_end trigger=sampling_end
  ... transfer + prep (full-load worker; vae_prepare_start/end present) ...
vae_early_activation_terminal   status=ready reason=ok transfer_count=1
vae_early_activation_consumed   join_wait_ms=29.565 transfer_count=1 cache_present=true
vae_decode_start / vae_decode_end  duration_ms=376.602
reconciliation: load_wall_ms=759.034 lane_wait_ms=1.903 join_wait_ms=29.565 residency_status=resident_full
```

### Arm B (sampling_first_step)

```
sampling_start                                    (node 1242, 8 steps)
first_sampler_step                                (hook)
vae_early_activation_scheduled  mode=sampling_first_step trigger=sampling_first_step trigger_mono_ns=165767997691 source=snapshot_vae
vae_early_activation_load_start mode=sampling_first_step trigger=sampling_first_step
  ... phase-1 pre-copy (NO lane, NO mutation) 70.2 ms ...    (precopy_start_mono_ns = trigger + 1378.0 ms)
sampling_end                    duration_ms=5212.505
vae_early_activation_load_end   load_wall_ms=70.221
vae_early_activation_terminal   status=ready reason=ok transfer_count=1   (phase-3 lane bind, lane_wait=0.0)
vae_early_activation_consumed   join_wait_ms=0.008 transfer_count=1 cache_present=true
vae_decode_start / vae_decode_end  duration_ms=417.056
reconciliation (worker): overlap_ms=3775.785 sampling_end_wait_ms=3705.41 load_wall_ms=70.221 gpu_allocated_delta_bytes=34693120 residency_status=gpu_resident
reconciliation (consumed): join_wait_ms=0.008 lane_wait_ms=0.0
```

B contract checks: exactly one scheduled event ✓; `mode`/`trigger=sampling_first_step` ✓;
scheduling at first_sampler_step ✓; event order scheduled → load_start → terminal(ready)
→ consumed(ready) ✓; `transfer_count==1` ✓; `overlap_ms>0` (3,775.8) ✓;
`precopy_wall_ms` present (70.221) ✓; `sampling_end_wait_ms` present (3,705.41) ✓;
`join_wait_ms` present (0.008) ✓; no VAE fallback ✓; no duplicate activation ✓;
no early UNET unload/move (C5 gate tests + no UNET code path touched) ✓;
output SHA identical to A ✓.

Waterfall detail caveat: B's rendered waterfall shows `VAE load/H2D = 3.750 s`
— that detail row spans load_start→terminal *including the intentional
3.7 s sampling_end wait* (overlapped, off the critical path). A's identical row
(758.3 ms) is on the critical path. The two detail rows are therefore **not
cross-arm comparable**; the authoritative comparisons are the reconciliation
`load_wall_ms` / `join_wait_ms` used in §4/§5.

## 7. Full valid waterfalls (verbatim, host-reconciled, final)

### Arm A — `v2_2026-08-14_20-11-03` (sampling_end)

```
V2 COLD WATERFALL - run 1 (local reconcile)
Request:   v2-benchmark-0-2f496da0209b | Instance: 83198ce5748941e6bad3ed439862d782 | Fresh: YES
Platform:  GCP/us-east1 | GPU: RTX PRO 6000 Blackwell | VRAM 97,250 MiB | CUDA 13.0 | CC 12.0
CPU:       AMD Family 191 Model 2 | visible=28
Telemetry: maxRSS=34.91 GiB

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (non-scheduling)           |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Modal pre-Python snapshot restoration          |     2.496s |     2.496s |  20.589% | ########                                 |
|   2 | Python/application restore                     | 489.290 ms |     2.985s |   4.036% | ##                                       |
|   3 | Restore-to-method entry                        |  38.979 ms |     3.024s |   0.322% | #                                        |
|   4 | Remote method setup                            | 192.536 ms |     3.217s |   1.588% | #                                        |
|     |   method entry to graph start                  | 134.572 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 134.506 ms |            |          |                                          |
|     |   graph setup                                  |  57.963 ms |            |          |                                          |
|   5 | PromptExecutor/cache setup                     |   7.052 ms |     3.224s |   0.058% | #                                        |
|   6 | Pre-sampler execution                          |     3.034s |     6.258s |  25.026% | ##########                               |
|     |   Conditioning cache exact_hit lookup=42.935ms |  42.935 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 385.291 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 135.309 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.036s |            |          |                                          |
|     |   Read end -> construction done                |   0.141 ms |            |          |                                          |
|     |   UNET get_model                               |  59.099 ms |            |          |                                          |
|     |   Bind                                         |  28.076 ms |            |          |                                          |
|     |   Synchronized H2D (6.1 GB/s)                  |     2.011s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   2.421 ms |            |          |                                          |
|   7 | Sampler node to sampling                       | 127.468 ms |     6.386s |   1.051% | #                                        |
|     |   lane acquired to actual stage                | 127.440 ms |            |          |                                          |
|   8 | Sampling                                       |     4.798s |    11.183s |  39.572% | ################                         |
|   9 | Post-sampling / VAE transition                 | 731.511 ms |    11.915s |   6.034% | ##                                       |
|  10 | VAE decode                                     | 376.190 ms |    12.291s |   3.103% | #                                        |
|     |   VAE load/H2D                                 | 758.301 ms |            |          |                                          |
|  11 | Output encode / descriptor                     | 239.239 ms |    12.530s |   1.973% | #                                        |
|     |   PNG encode                                   | 168.192 ms |            |          |                                          |
|  12 | Local result handling / caller return          |  16.000 ms |    12.546s |   0.132% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | RECONCILIATION                                 |   2.729 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
COMMAND -> RESPONSE:                     38.472s
Command (without scheduling) -> Response:   12.124s
Scheduling time:                         26.348s
```

### Arm B — `v2_2026-08-14_20-26-02` (sampling_first_step)

```
V2 COLD WATERFALL - run 1 (local reconcile)
Request:   v2-benchmark-0-45977c9faf64 | Instance: 4daeb001f06c401282762fa520c78f70 | Fresh: YES
Platform:  GCP/us-east4 | GPU: RTX PRO 6000 Blackwell | VRAM 97,250 MiB | CUDA 13.0 | CC 12.0
CPU:       AMD Family 191 Model 2 | visible=28
Telemetry: maxRSS=34.86 GiB

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (non-scheduling)           |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Modal pre-Python snapshot restoration          |     8.655s |     8.655s |  38.554% | ###############                          |
|   2 | Python/application restore                     |     1.433s |    10.087s |   6.382% | ###                                      |
|   3 | Restore-to-method entry                        |  16.681 ms |    10.104s |   0.074% | #                                        |
|   4 | Remote method setup                            | 799.981 ms |    10.904s |   3.564% | #                                        |
|     |   method entry to graph start                  | 697.910 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 697.816 ms |            |          |                                          |
|     |   graph setup                                  | 102.072 ms |            |          |                                          |
|   5 | PromptExecutor/cache setup                     |  12.514 ms |    10.917s |   0.056% | #                                        |
|   6 | Pre-sampler execution                          |     5.092s |    16.008s |  22.682% | #########                                |
|     |   Conditioning cache exact_hit lookup=69.735ms |  69.735 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 496.858 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  52.432 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 191.351 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.723s |            |          |                                          |
|     |   Read end -> construction done                |   0.206 ms |            |          |                                          |
|     |   UNET get_model                               |  64.762 ms |            |          |                                          |
|     |   Bind                                         |  20.638 ms |            |          |                                          |
|     |   Synchronized H2D (3.1 GB/s)                  |     3.995s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   3.235 ms |            |          |                                          |
|   7 | Sampler node to sampling                       | 183.659 ms |    16.192s |   0.818% | #                                        |
|     |   lane acquired to actual stage                | 183.632 ms |            |          |                                          |
|   8 | Sampling                                       |     5.212s |    21.404s |  23.220% | #########                                |
|   9 | Post-sampling / VAE transition                 | 991.536 ms |    22.396s |   4.417% | ##                                       |
|  10 | VAE decode                                     | 416.631 ms |    22.813s |   1.856% | #                                        |
|     |   VAE load/H2D                                 |     3.750s |            |          |                                          |
|  11 | Output encode / descriptor                     | 235.986 ms |    23.049s |   1.051% | #                                        |
|     |   PNG encode                                   | 166.695 ms |            |          |                                          |
|  12 | Local result handling / caller return          |  16.000 ms |    23.065s |   0.071% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | RECONCILIATION                                 |  -0.730 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
COMMAND -> RESPONSE:                     59.864s
Command (without scheduling) -> Response:   22.449s
Scheduling time:                         37.416s
```

## 8. Classification

- **Structure (C5 implementation): CONFIRMED** — one transfer, actual overlap,
  correct event order, no fallback, no duplicate, no UNET unload/move, output
  parity (identical SHA).
- **Performance (A/B): INCONCLUSIVE** — host variance prevents separating the
  VAE-mode change from unrelated changes (different regions us-east1 vs
  us-east4; B's host slower on every unrelated stage by 1.7–4.2×; n=1 per
  arm). In addition, the work that moved under sampling was only **70.2 ms /
  34.7 MB**, so even the direction of any real effect (~70 ms ceiling) is
  invisible under the observed noise (±10 s non-scheduling, ±400 ms sampling).
- Per the brief: **STOP, no additional runs purchased** to strengthen the
  label.

## 9. Outcome fields

- **Measured C5 saving:** none claimable (no stage-level evidence of an
  Arm-B advantage; B was slower on every stage on its host; the overlapped
  transfer was 70 ms).
- **Sampler contention observed:** no (sampling B−A = +414.8 ms is
  host-confounded; 70 ms / 34.7 MB of H2D cannot explain it; no in-sampling
  contention signal).
- **C5 recommended production default:** `sampling_end` (unchanged). The
  `sampling_first_step` path remains available and opt-in; its structural
  behavior is proven correct, but no win is demonstrated.
- **Additional runs needed:** none automatic. A future matched-host A/B
  (same region / comparable load, ideally interleaved) could resolve the
  performance question, but must first decide the worker-scope equivalence:
  the transfer-only pre-copy is ~70 ms, not the ~0.9 s of the A-path
  full-load `load_wall_ms` — the realistic win ceiling is ~70 ms unless the
  VAE prep/restore work in A's load wall can also be moved or eliminated.

## 10. Deviations / notes

- Arm B deploy attempt #1 failed transiently (Modal build-context pyc race —
  `tests\__pycache__\test_model_library.cpython-311.pyc was modified during
  build process`); no deployment was produced, nothing changed; retry
  succeeded. The C5 implementation was not modified.
- B-1 hit the known post-deploy B1 reconstruction/convergence transition
  (`reloaded_generation_mismatch`, reload 108.6 ms) and was not counted, per
  the brief; B-2 converged (`exact_match`) and is the valid B run.
- No strict-Batch-A-raise deviation occurred on either valid run (both
  PASSed in-console; no slow-H2D forensic on either).
- `cpu_peak_cores` / `cpu_above_16_ms` were not present in these artifacts
  (activation-diagnosis fields absent); reported as n/a rather than inferred.
- The B waterfall's `VAE load/H2D 3.750 s` detail row includes the intentional
  3.7 s sampling_end wait (overlapped) — not cross-arm comparable (§6 caveat).
- Nothing was optimized; C4 hygiene A/B not started; C6 not implemented;
  no commit.

Artifacts: `v2_2026-08-14_20-11-03/run_0.json` (A),
`v2_2026-08-14_20-26-02/run_0.json` (B) under `comfymodal-data/benchmarks/runs/`;
console logs `v2_c5_armA_validation.log`, `v2_c5_armB_deploy{,_2}.log`,
`v2_c5_armB_validation{,_2}.log` at the repo root.
