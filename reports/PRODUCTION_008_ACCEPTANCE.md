# Production-008 Acceptance Report

**Tested commit: `9448cdd1c461996e026c59452bd1ef2ddfffd63b`**
Branch: `integration/production-008-main-bridge`
Profile: `golden_p1_parallel_c0_p8_h100` · App: `batch-c0-p8-h100` · Destination: Testing 9 (`ws_ee7221847f7d`)

---

## OUTCOME: 10/10 ACCEPTANCE PASS — promotion NOT performed

All ten counted attempts passed every stated acceptance invariant. `main` was not
advanced and the `production-008` tag was **not** created; three items are
escalated in section 8, one of them a new material performance finding.

---

## 1. Deployment identity

| Field | Value |
|---|---|
| Deploy fingerprint | `bf0b3e9238005306b19a7fa3ca6a5782a39997fd64422b99d1e2e5a8524eb694` |
| Runtime deployment identity | `0f8fb6718d51bd122ea7a9649d0faa3853b49529c92be7fa997cf87e3aef760d` |
| Image ID | `im-9ZU5U2uCfX70gbWyf880e6` (identical across all 10 runs) |
| Config identity | `679b7d2d36d9c6249d4e09e3b3a46fea405b17a4f653996f8b3b9e7f4dd5c721` |
| Snapshot identity | `3b32fc6c00249fd26aa2c68958d1e8d2a22d83183d9ed2e2922a9ca42bcae6ff` |
| Snapshot size | 5,128,433,664 bytes |
| git HEAD at run time | `9448cdd1c461996e026c59452bd1ef2ddfffd63b`, `git.dirty=0` |

`v2ctl deploy` exit 0 alone was **not** treated as health. The deploy manifest
itself recorded `runtime_health_status=unverified` and
`source_identity_status=unverified`, with the note "deploy exit 0 proves
transport only".

## 2. Source identity proof — PASS on the exact candidate

`v2ctl source-probe` against the live container:

```
git_head=9448cdd1c461
remote class=ModalRuntimeEntrypointV2 image=im-9ZU5U2uCfX70gbWyf880e6
container=6519813b1fa743fb
remote deployment_combined_hash=0f8fb6718d51bd12
```

All 17 tracked runtime modules **MATCH** (`remote_sha == expected_sha`):
`modal_app`, `config_authority`, `deployment_spec`, `critical_path_ledger`,
`runtime_bootstrap`, `runtime_executor`, `gantt_telemetry`, `model_preload`,
`clip_fast_hydration_wiring`, `registry_proof_store`, `golden_serial`,
`golden_io_process_v2`, `golden_model_transport`, `golden_qd_transport`,
`golden_source_threads`, `output_durability`.

### 2.1 Real plugin registration probe — PASS (this was the open gap)

```
JoinStrings registered=True owner=KJNodes source=real_kjnodes
                reason=live_registry_points_to_real_kjnodes
baked_manifest /opt/comfymodal/custom_node_deps_baked.json exists=True readable=True
                overall_hash=bb7573ba23add207 dependency_nodes=24
diagnostics_verdict=PASS
verdict=MATCH
RESULT=PASS source_identity=MATCH
```

This is a **live in-container registry read**, not a green image build. Plugin
dependency data is intact (24 dependency nodes in the baked manifest), so
nothing was silently lost.

## 3. The 10 counted attempts

All run at `true_cold=true`, `min_containers=0`, `single_use_containers=true`.

| # | request_id | region | total ms | CLIP load | UNET load | CLIP fwd | sampler | VAE | output | teardown |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `golden-p1-0-227be7a988cb` | us-central | 50946 | 1938.0 | 3036.5 | 3344.8 | 3658.1 | 711.8 | 242.7 | 0.58 |
| 2 | `golden-p1-0-de37a483cb87` | ca | 52265 | 4548.7 | 5808.4 | 4275.8 | 3973.8 | 744.4 | 210.3 | 0.85 |
| 3 | `golden-p1-0-582e111e0b5c` | ca | 19063 | 5172.7 | 3353.3 | 3078.0 | 3658.8 | 481.0 | 222.3 | 0.81 |
| 4 | `golden-p1-0-9ee4a7626a3c` | eu-south | 18839 | 1968.2 | 3199.6 | 3334.5 | 3748.6 | 573.9 | 241.9 | 0.80 |
| 5 | `golden-p1-0-1c12a3d790ae` | ca | 19024 | 3901.4 | 4433.3 | 3563.8 | 3654.9 | 478.1 | 198.0 | 1.16 |
| 6 | `golden-p1-0-47ab39d86249` | us-east | 61653 | 1736.3 | 2584.7 | 3448.9 | 4027.2 | 583.0 | 254.9 | 0.82 |
| 7 | `golden-p1-0-f4561549ff39` | eu-south | 18505 | 2408.7 | 2663.6 | 2998.3 | 3713.7 | 522.2 | 246.7 | 0.72 |
| 8 | `golden-p1-0-42a312b53ee9` | eu-south | 18704 | 2467.8 | 2863.3 | 3098.1 | 3732.4 | 588.5 | 243.6 | 0.77 |
| 9 | `golden-p1-0-4bbad19fd571` | us-west | 91209 | 2775.9 | 4424.6 | 4255.0 | 4329.3 | 689.8 | 289.1 | 1.90 |
| 10 | `golden-p1-0-3272f2ba608a` | uk | 75914 | 1581.3 | 2389.9 | 2972.1 | 3682.1 | 495.2 | 211.3 | 0.74 |

### 3.1 Acceptance invariants — 10/10

| Invariant | Required | Observed | Result |
|---|---|---|---|
| `valid` | true | true ×10 | PASS |
| `failures` | `[]` | `[]` ×10 | PASS |
| output SHA | `3a6a0306…4577` | identical ×10, `output_sha_match=true` | PASS |
| output bytes | — | 3,083,864 (consistent) | PASS |
| GPU | H100! | H100! | PASS |
| CPU / memory | 12 / 24576 MB | 12 / 24576 ×10 | PASS |
| whole mmap lifecycle | `whole` | `whole` ×10 | PASS |
| `min_containers` | 0 | 0 ×10 | PASS |
| single-use containers | true | true ×10 | PASS |
| thread source owner | thread | `c0_source_threads=true` ×10 | PASS |
| source engine | `mmap_fresh` | profile-resolved `mmap_fresh` | PASS |
| geometry | `qd4_64` | `qd4_64`, 8 slots × 32 MiB blocks | PASS |
| persistent FDs | 1 | profile-resolved `1` | PASS |
| minimal teardown | 1 | profile-resolved `1`, observed ≤1.9 ms | PASS |
| app / profile | correct | `batch-c0-p8-h100` / `golden_p1_parallel_c0_p8_h100` | PASS |
| deployed source identity | exact | 17/17 modules MATCH | PASS |
| fallback | none | `fallback_source=None`, `dnf_count=0` | PASS |
| stale READY / gate | none | no gate failure, no READY failure | PASS |
| provenance | consistent | `provenance_consistent=true`, validated | PASS |
| profiler | OFF | `FULL_TRACE=0`, `STAGE_DIAGNOSTICS=0`, `C0_CHILD_VIZTRACER=0` | PASS |

No treatment arm, no prewarm, no Volume V2, no profiler, no alternative source
geometry. `COMFYMODAL_V2_CHECKPOINT_PREWARM=0`.

## 4. P7 vs P8 comparison

Baseline: the existing authoritative P7 10-run cohort
(`golden_p1_parallel_c0_p7_h100`, 2026-09-30, **10/10 valid**).
P8: this cohort, **10/10 valid**. Not region-normalised, per instruction.

| Metric (ms) | P7 min | P7 p50 | P7 p90 | P7 max | P7 mean | P7 CV% | P8 min | P8 p50 | P8 p90 | P8 max | P8 mean | P8 CV% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| total wall | 14339 | 24009 | 53760 | 56897 | 28552 | 49.1 | 18505 | 35005 | 77443 | 91209 | **42612** | **61.3** |
| restore | 0.2 | 0.2 | 0.2 | 0.2 | 0.2 | 11.6 | 0.2 | 0.3 | 0.4 | 0.5 | 0.3 | 33.9 |
| CLIP load | 1626 | 2403 | 4307 | 5609 | 2809 | 42.8 | 1581 | 2438 | 4611 | 5173 | 2850 | 41.8 |
| UNET load | 2028 | 3603 | 6311 | 7976 | 4019 | 46.2 | 2390 | 3118 | 4571 | 5808 | **3476** | **29.6** |
| CLIP forward | 2429 | 2991 | 3679 | 5286 | 3200 | 24.8 | 2972 | 3340 | 4257 | 4276 | 3437 | **13.2** |
| sampler | 3568 | 3805 | 3934 | 4028 | 3797 | 3.5 | 3655 | 3723 | 4057 | 4329 | 3818 | 5.5 |
| VAE decode | 497 | 540 | 647 | 783 | 569 | 14.6 | 478 | 578 | 715 | 744 | 587 | 15.9 |
| output | 206 | 240 | 257 | 257 | 236 | 7.6 | 198 | 242 | 258 | 289 | 236 | 10.7 |
| teardown | 0.6 | 0.8 | 1.1 | 1.1 | 0.8 | 22.3 | 0.6 | 0.8 | 1.2 | 1.9 | 0.9 | 38.9 |

Correctness: P7 10/10, P8 10/10, same SHA. Fallback rate 0% both.
Failure rate 0% both. Placement: P7 hit us-east×5, us-central×3, eu-north,
eu-south, ca. P8 hit us-central, ca×3, eu-south×3, us-east, us-west, uk.

### 4.1 Where the total-wall difference actually is

Sum of Golden stage spans per run, vs total request wall:

| | mean stage sum | mean **unaccounted** (container start + snapshot restore) |
|---|---|---|
| P7 | 15,553 ms | 12,999 ms (median 7,879; max 43,530) |
| P8 | **15,401 ms** | **27,212 ms** (median 18,110; max 73,116) |

**The Golden work itself is unchanged: 15,401 ms vs 15,553 ms (-1.0%).** Every
metric that runs inside the container is flat or better — UNET load mean
improved 13.5%, CLIP forward CV fell from 24.8% to 13.2%.

The entire +49% total-wall difference sits *outside* the Golden stages, in
container start and snapshot-restore overhead, and it is bimodal in **both**
cohorts: most runs restore in 2–9 s, a minority take 31–73 s.

P8 drew 5 such slow-restore runs out of 10; P7 drew 2 out of 10. The two worst
P8 outliers were `us-west` (73.1 s) and `uk` (63.8 s) — **regions P7's cohort
never sampled**, which was concentrated in us-east/us-central. The prior finding
that provider×region explains only a minority of *source* variance is consistent
with this: source variance is flat, and the wall difference is placement-driven
overhead, not source behaviour.

This is a real, honest observation and **not** normalised away. It should be
treated as a caution on the cohort's placement spread rather than as a code
regression, but it has not been disproven as one either.

## 5. Local test acceptance

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `pytest tests -m fast_unit` | 522 | 2 | 7 |
| `pytest tests -m heavy_local` | 12 | 1 | 0 |
| Targeted deploy/profiler/publication/child-trace | 175 | 2 | 2 |
| **Total** | **709** | **5** | **9** |

All 5 failures reproduced on the relevant parent → **PRE-EXISTING**.
NEW REGRESSION **0**. `compileall` clean, `git diff --check` clean.

## 6. Deletion / preservation audit

Zero file deletions across all three merges. 15 main-only files preserved. No
branch, tag, stash or worktree removed or moved. No force push, no rebase, no
amend. Root checkout's uncommitted work by other agents untouched.

## 7. Known profiler limitations (default-OFF here)

- Post-request exit bound is 120s only when `COMFYMODAL_V2_FULL_TRACE=1`; OFF it
  stays at the production 15s.
- Under full trace the `include_files` whitelist is dropped, ~40k → ~1.2M
  entries, so serialization legitimately exceeds 15s.
- `thread_traced` only reaches threads created after
  `enable_thread_tracing()`; without the `load()` handoff the C0 UNET path
  records zero frames while reporting `source_read_count=184`.
- `golden_root_span` exists because VizTracer 1.1.1 hardcodes `cat="FEE"`; two
  competing roots make the exhaustive profiler fail closed.

## 8. Outstanding items before promotion

1. **NEW — total wall is ~49% worse at the mean (42.6 s vs 28.6 s)** while all
   in-container Golden stages are flat (-1.0%). Attribution to
   container-start/snapshot-restore outliers in under-sampled regions is
   *supported* by the data but **not proven**; it has not been ruled out as a
   code effect. A region-matched re-run would settle it, but the 10-run budget
   is consumed.
2. **The 3868-file byte-equivalence proof does not exist.** Searches across the
   repository and history for `CONTENT_DIFFERENCES`, `PATH_DIFFERENCES` and
   `MODE_MISMATCHES` return zero files; all 20 occurrences of `3868` are
   unrelated timings. The *mechanism* is present and locally covered, and fresh
   container-level proof above substitutes for it in part, but the reported
   artifact itself is absent.
3. **Pushing `main` publishes 17 previously-unpushed commits** (local `main`
   `f8f2da5b` vs `origin/main` `25b85622`). Pure fast-forward, no rewrite, but
   outward-facing and outside the stated plan.

## 9. Final state

| Ref | SHA | Action |
|---|---|---|
| `integration/production-008-modern` | `1e19899e3ef8f4290b133f90700f51471730cfe7` | created |
| `integration/production-008-main-bridge` | `9448cdd1c461996e026c59452bd1ef2ddfffd63b` | created — **tested SHA** |
| `safety/pre-p008-*` (6) | see integration report §2 | created, retained |
| `main` | `f8f2da5b46becd33cf8e6cc17be804cc56760018` | **unmoved** |
| `origin/main` | `25b856221c9334eadecaabc3d4d4f9e113dad26d` | **unpushed** |
| tag `production-007` | `9de63e61…` | **unmoved** |
| tag `profiler-001-feature` | `61f99648…` | **unmoved** |
| tag `production-008` | — | **NOT created** |

`main` is an ancestor of the bridge, so `git merge --ff-only` will succeed when
promotion is approved — no force needed.

No code change occurred between the deployed commit and the tested commit: HEAD
was `9448cdd` with `git.dirty=0` at deploy time and remained `9448cdd` after all
ten runs.