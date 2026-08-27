# OC7 — Batch Teardown and Post-Result Timing-Completeness Audit

Date: 2026-08-25
Mode: READ ONLY. No deploy, no paid runs, no source changes.
Outputs: this file + `OC7_TEARDOWN_TIMING_CLAIMS_2026-08-25.csv`.

Scope note (evidence availability): the brief's READ list names `SoT / v2.1`,
`O5/O6/O7/O8`, `OB6`, `OB7`, `OB8`. No files with those designations exist in
either checkout (`comfyui-modal`, `comfyui-modal-r42`) as of this audit
(searched: root MDs, docs/, reports/ (empty), .v2ctl/, .opencode/, .slim/,
r42 lane, full-tree filename and content searches for `O5..O8/OB6..OB8/OC*/SoT`,
and the exact anchor numbers). Their content could not be read directly. Where
the brief attributes findings to those phases (e.g., "Phase O/OB found
`MINIMAL_GPU_TEARDOWN=0` in good and bad cohorts"), OC7 re-derived the claim
from primary artifacts instead of trusting the summary; every re-derivation is
cited below. All other listed evidence classes exist and were read.

---

## 1. GOLDENTEARDOWN CONTRACT — derived from code

The serialized single-use teardown part is exactly this call chain:

```
run_plan_stream (outer) sees first terminal event (result|error|cancelled)
  -> stamps request_terminal_start                     modal_app.py:17897-17905 (orch checkout)
  -> _run_terminal_cleanup_sync()                      :17739-17774
       -> _run_pending_production_cleanup()            :15821-15862   (production registry cleanup; idempotent)
       -> _release_gpu_after_request()                 :6009-6410     (THE release function)
  -> stamps terminal_cleanup start/end onto event      :5491-5516 (_stamp_terminal_cleanup)
  -> yields terminal event to Modal transport          :17927
```

### What the release function owns (`_release_gpu_after_request`, modal_app.py:6009-6410)

Gates: `COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST` (else `disabled` early-exit,
:6017-6018); mode selection at :6020-6026 — explicit env value wins, otherwise
default = `_resolve_single_use_containers()` (:2842).

Bounded stages (always run, both modes):

| Stage | Site | Work |
|---|---|---|
| cuda_memory_before | :6126 | read-only CUDA snapshot |
| request_samplers | :6128-6144 | stop `_cgroup_sampler`/`_process_cpu_sampler` (0.5 s timeout each) |
| preload_workers | :6146-6159 | `bridge.close_workers(timeout=_PRELOAD_WORKER_JOIN_BUDGET_S=5.0 (:308), cancel_futures=True, wait_futures=False)` |
| legacy_request_workers | :6161-6168 | join legacy background threads (0.5 s) |
| activation_references | :6170-6209 | cancel stall watchdog, clear retained UNET identity chain, page-readiness clear, finalize UNET/VAE early activation, unmark CPU-snapshot request, close speculative CLIP hydration lane (owners closed + empty_cache inside lane close) |
| preload_references | :6211-6217 | bridge.clear |
| request_references | :6219-6235 | graph trace None, dead load-future sweep, eviction-retention state reset |

Full-only stages (skipped when minimal): `model_management_unload`
(unload_all_models with temporary offload_device→CPU pinning, :6239-6293),
`device_fallback` (`free_memory(1e30, dev, keep_loaded=[])`, only if unload
failed, :6295-6321), `model_management_cleanup` (`cleanup_models`,
:6323-6332), `legacy_executor_reset` (:6334-6344), `garbage_collection`
(`gc.collect()`, :6346-6351), `cuda_cleanup`
(`torch.cuda.synchronize()` + `torch.cuda.empty_cache()`, :6353-6377).
Diagnostics: `request_gpu_release_start` / `..._teardown_mode` /
`..._end` (with per-stage `elapsed_ms`) emitted to `[v2.teardown]` stdout only
(teardown_diagnostics.py:347-386); never persisted into run artifacts.

### What the teardown part does NOT own (proven by code)

| Obligation | Actual owner | Proof site |
|---|---|---|
| Output persistence (PNG/thumbnail bytes → runtime-state volume) | Output path `_persist_output_assets` writes files + starts commit BEFORE durable result | modal_app.py:16082-16179 |
| Asset Volume commit completion ("Variant A" deferred commit) | Stream tail/finalizer awaits stashed task AFTER result yield | `_finalize_deferred_commit` :16215-16314; awaited in stream tail/finalizer (impl tail + outer finally :17994-17997); idempotent |
| Result assembly + ledger persist (`output_persist_done`, canonical ledger written into artifact) | Inside `_run_plan_stream_impl` before yield | :19775-19873 |
| Result transport (remote emit → local receipt → execute_plan_return) | Modal transport + host after the event is yielded | `_stamp_remote_result_emit` :5412-5488; E6 §Exact Lifecycle steps 4-6 |
| Conditioning-cache durability flush + final Volume commit | `@modal.exit` stage `conditioning_cache_flush` | exit hook :5897-5911 |
| Platform process/container exit | Modal platform after `@modal.exit`; OS reclaims remaining CUDA without app empty_cache | E6 §True-Exit Determination; docs/v2-single-use-container-teardown.md |

Therefore the GOLDENTEARDOWN contract: **the serialized single-use teardown
span is responsible for application-owned reference/worker/service release and
— only when full mode is selected — model unload + GC + CUDA cache reclaim. It
is NOT responsible for output persistence, Volume commit, result transport, or
platform process exit.** Minimal mode explicitly transfers final GPU-memory
reclaim to process termination (A/B: 12.63 GB retained to process exit).

Post-stream second attempt exists by design: decorated wrapper `finally` calls
`_release_after_stream_complete` (:17776-17814, wrapper :20130-20165) which
RESETS the per-request guard and re-executes the effective release after the
generator frame dies; the pre-yield attempt is documented as best-effort while
the frame is alive. Exit hook runs a conditional third path (only when
`_terminal_response_delivered`, :5920-5929).

---

## 2. Candidates / classes audited

### C1. Historical controlled full-vs-minimal A/B (2026-08-05)
Source: `V2_VARIANCE_CAUSAL_FIX_REPORT.md:11-39,149-160`. Two single-use cold
runs, identical workload, teardown diagnostics on; A = full
`unload_all_models()`, B = minimal bounded cleanup. Measured via
`[v2.teardown]` events (`request_gpu_release_*`, `exit_hook_*`,
`python_atexit`) and run artifacts `v2_2026-08-05_23-33-32` (A) /
`v2_2026-08-05_23-36-01` (B).

Truth: **TOTAL for the individual release function** — `request_gpu_release_
start→end` brackets the whole function including all stages and diagnostics;
stage table itemizes interior (unload 1,929.4 ms; GC 627.3 ms). **PARTIAL for
FIRST_DURABLE_TO_EXIT**: the A/B compares the function and the exit-hook stamp
pair, but it does not span deferred-commit drain, post-stream re-release
accounting into a first-durable→exit total, or process exit time. In B, 12.63
GB CUDA remains allocated at span end and is released only by process
termination — so B's "total" is complete for the FUNCTION but deliberately
incomplete for memory-reclaim-to-exit. Exit hook measured separately (23.9 vs
20.3 ms) and container disappearance observed post-hook in both arms.
Result delivery identical (107 outputs, exit 0) — no output-owned work moved
into either arm.

### C2. Historical reusable-container 24 s exit-lag class
Source: `docs/v2-single-use-container-teardown.md`. Without
`single_use_containers=True`, `target_inputs/max_inputs=1` only limit
concurrency; Modal returned the container to its input loop and invoked
`@modal.exit` ~24 s after GPU release ended (15:59:23 → 15:59:47 stamp gap on
run `v2-benchmark-0-7c4a0eccd73c`). Classifies as C (process/platform exit
time) contaminated into a teardown narrative: app teardown was NOT responsible
(`docs/v2-single-use-container-teardown.md:14-17`). With single-use enabled,
post-stream release and `exit_hook_start` occur in the same second
(`v2-benchmark-0-d70a20d5a908`).

### C3. Good few-ms terminal-cleanup cohorts (current era)
Artifact-derived cohort (all runs under
`ComfyUI\comfymodal-data\benchmarks\runs\`, field
`terminal_cleanup_start/end_wall_unix_ns` diff, extracted across every run dir):
2026-08-14 03:01+ ≈0.1 ms; 2026-08-15…08-24(19:29) ≈0.1–1.9 ms typical band
0.5–0.9 ms. Examples with provenance:
`v2_2026-08-23_20-53-40` (0.5 ms; profile r43-known-fast; git_head
`0c59f46` orchestration golden lineage), `v2_2026-08-24_12-11-30` (0.5 ms),
`v2_2026-08-24_19-29-04` (0.6 ms).

In-container mode derivation: `_runtime_env()` forwards
`SINGLE_USE_CONTAINERS` and `RELEASE_GPU_AFTER_REQUEST` into the container
env but does NOT forward `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN` (forward list
modal_app.py:2974-3120; the only other MINIMAL references are the
request-carried allowlist :589 and the required-env identity manifest list
:16476). Host-side v2ctl manifests record `MINIMAL_GPU_TEARDOWN="0"` for every
v2ctl-era deployment checked (good AND bad: run manifests
`run_20260821-*` … `run_20260825-110538_*`, both checkouts' `.v2ctl/runs`),
but inside the container the variable resolves to "" → default path
(:6026) → minimal bounded release because SINGLE_USE=1 was forwarded.
The 0.5–1.9 ms band is magnitude-consistent with the controlled minimal arm
(2.455 ms) running with an empty/near-empty worker set. The 0.1 ms sub-band is
magnitude-consistent with a disabled/already-released early exit (:6017-6018,
:6034-6038); which early-exit applies per run is not recorded in artifacts
(UNKNOWN).

### C4. Bad 2.2–11.8 s terminal-cleanup cohorts (current era)
Same extraction: 2026-08-24 21:03 onward — 3181.5–6869.7 ms on 08-24 evening;
2204.0–11812.7 ms on 08-25 (max `v2_2026-08-25_07-00-09` = 11,812.7 ms; bad
reference `v2_2026-08-25_02-55-12` = 3,133.7 ms; K1 cohort runs
06-51-50/06-55-04/06-57-4x = 3007.8/7116.7/7658 ms; latest 16-04-15 =
3272.1 ms). Value distribution clusters (~3.1-3.5 s, ~6.3-7.1 s, ~8.3-8.5 s,
11.8 s) are compatible with bounded-stage waits stacking (preload-worker join
budget alone is 5.0 s, modal_app.py:308/:6151-6155; sampler stops 0.5 s each)
plus variable extras — but per-stage attribution is impossible from artifacts
because stage_results live only in `[v2.teardown]` stdout and
`console_capture=null` in the era's run manifests, and
`COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS` is absent from the effective environment
of these deployments. MEASURED span completeness: TOTAL for whatever ran inside
the stamped window (it is a pure mono/wall bracket around production cleanup +
release); PARTIAL for FIRST_DURABLE_TO_EXIT (excludes transport, deferred
commit, post-stream re-release, exit hook, process exit). Root cause of the
inflation: NOT established by any artifact (see §5).

### C5. Mixed 2.1–2.5 s cohort (2026-08-14/08-17)
`v2_2026-08-14_20-54-44`=2257.4, `21-25-55`=2111.4, `21-47-28`=2330.0,
`22-20-03`=2311.5, `22-24-00`=2238.4, `22-26-50`=2452.9, `22-43-10`=2482.2,
`22-46-08`=2266.6; `v2_2026-08-17_16-04-13`=2307.8 — interleaved same-day runs
at 0.1 ms. Magnitude matches the controlled FULL arm (2,560 ms) closely, i.e.,
consistent with full-mode release genuinely executing in-container in those
runs (pre-v2ctl tooling era; direct host env may have reached the container).
Mode per run not recorded in artifacts: classification UNKNOWN, magnitude match
only.

### C6. Intermediate 380.8–880.0 ms cohort (2026-08-19)
`v2_2026-08-19_20-50-05`=867.0, `20-54-34`=380.8, `21-06-32`=880.0 among
0.1–1.1 ms neighbors. No stage breakdown captured. UNKNOWN composition; spans
neither the minimal nor the full historical magnitude cleanly.

### C7. Current minimal single-use branch (code)
Default resolution path :6026 with SINGLE_USE=1 forwarded → minimal. Owned
work = bounded stages above; model unload/GC/empty_cache skipped; CUDA
reclaim delegated to process exit. Expected span magnitude: sub-ms to few ms
(A/B control: 2.455 ms).

### C8. Current exit hook (code)
`exit()` :5843-5935: bounded stages request_samplers, preload_workers,
preload_thread_sweep (non-daemon `comfymodal-*` joins within budget),
trace_services, legacy_request_workers, conditioning_cache_flush (signal +
join + drain + one explicit Volume commit when dirty — durability backstop),
production_cleanup fallback; then conditional `request_gpu_release` when
terminal response was delivered. Stamps `exit_hook_start/end`. This is the
first application-visible true-exit boundary (E6 §True-Exit Determination);
process/container termination follows; OS reclaims remaining CUDA.

### C9. Separate generator/post-stream release path (code)
Decorated outer wrapper `finally` → `_release_after_stream_complete`
(resets guard, re-runs production cleanup + effective release). Runs AFTER the
response stream is consumed; not proof of container closure (E6). Present in
both checkouts (r42 adds R44J2 decomposition stamps gpu_release_begin/end,
post_stream_release_start/end — stdout-only like all teardown diagnostics).

---

## 3. Timing-completeness classification

Legend — MEASURED_OPERATION_COMPLETENESS: does the number measure its named
operation fully? GOLDEN_PART_COMPLETENESS: coverage of the serialized
single-use teardown obligation set (§1 contract). CONTAMINATION: non-teardown
work inside the span.

| # | Timing | Class | M.O.C. | G.P.C. | Contamination |
|---|---|---|---|---|---|
| 1 | A/B full terminal release 2560.334 ms | A (+D-free) | TOTAL (function) | TOTAL for full-mode obligation incl. unload/GC/cache | none (result delivery identical both arms) |
| 2 | A/B unload stage 1929.4 ms | A-part | TOTAL (stage) | part | none |
| 3 | A/B GC stage 627.3 ms | A-part | TOTAL (stage) | part | none |
| 4 | A/B minimal release 2.455 ms | A | TOTAL (function) | TOTAL for minimal-mode obligation (reclaim intentionally deferred to exit) | none |
| 5 | A/B post-stream 633.8 / 2.0 ms | A (second entry) | TOTAL (function re-entry) | partial (outside serialized window) | none |
| 6 | A/B exit hook 23.9 / 20.3 ms | B/C boundary | TOTAL (hook) | partial (service work only; conditional release may add) | conditioning-cache flush commit included (durability, exit-owned) |
| 7 | Reusable ~24 s release→exit lag | C | n/a (interval between separate stamps) | n/a | platform scaledown idle, NOT app teardown |
| 8 | Good few-ms cohorts 0.1–1.9 ms | A (minimal or early-exit) | TOTAL (window) | TOTAL for minimal obligation | none evidenced; per-run early-exit identity unknown |
| 9 | Bad 2.2–11.8 s cohorts | A-window inflated | TOTAL (window) | OVER-complete relative to minimal contract (unattributed waits) | suspected bounded-wait stacks; unproven |
| 10 | Mixed 2.1–2.5 s cohort | A (full-consistent) | TOTAL (window) | full-mode-like | none evidenced; mode UNKNOWN |
| 11 | 380–880 ms intermediate cohort | A (unknown mix) | TOTAL (window) | UNKNOWN | unknown |
| 12 | Deferred-commit await (post-yield) | D (output-owned late) | n/a code-derived | out-of-contract BY DESIGN | correctly EXCLUDED from teardown spans |

Cross-cutting flags (per brief):
- POST_DURABLE_APPLICATION_WORK_INCLUDED: rows 1-6 NO (spans sit after the
  first-durable boundary and exclude later app work); rows 8-11 NO for what is
  included, but the windows themselves are PARTIAL proxies for
  first-durable→exit totals (they exclude deferred commit, post-stream
  re-release, exit hook, atexit); row 12 YES by definition.
- OUTPUT_OWNED_LATE_WORK_INCLUDED: NO for all teardown rows (persistence and
  ledger finalize complete before/at first_durable_result :19806-19817; asset
  commit drained post-yield outside teardown spans). Row 6 partially includes
  a DIFFERENT persistence (conditioning-cache flush commit) — exit-owned, not
  output-owned.
- PROCESS_EXIT_INCLUDED: NO for all rows 1-5, 8-12. Row 7 IS the process-exit
  lag class. Minimal-mode rows (4, 8) rely on process exit for 12.63 GB CUDA
  reclaim that their numbers do not contain.

## 4. Full-vs-minimal A/B truth vs good/bad cohort truth

- A/B truth (kept intact): controlled, same-workload, single-variable
  comparison proving the RELEASE FUNCTION totals 2560.334 vs 2.455 ms and that
  generation/result delivery were identical. It proves function-level totals;
  it does NOT prove anything about first-durable→exit totals, and the minimal
  arm leaves reclaim to the platform.
- Cohort truth: good few-ms and bad 2.2–11.8 s current-era cohorts BOTH ran
  with host-side `MINIMAL_GPU_TEARDOWN=0` recorded (verified in
  `.v2ctl/runs/*.json` provenance for 08-21…08-25 deploys in both checkouts),
  and in-container that flag was inert (not forwarded by `_runtime_env`;
  containers resolved minimal via SINGLE_USE=1). Therefore neither the flag
  value nor a good/bad difference in it explains the flip.
- Flip timing: last good run 2026-08-24 19:29 (0.6 ms) → first bad run
  2026-08-24 21:03 (3785.7 ms). Between them lie the R44I3-era r42-lane
  deploys (deploy_20260824-200437_096df343 20:04, -202958_632443ba 20:29;
  bad-reference deploy_20260824-211747_32d41196 21:17; source lane git_head
  `6040c459` + J1 dirty edits vs good-era `0c59f46` orchestration lineage).
  Source lane changed AND runtime state changed; the artifacts cannot separate
  them.

## 5. Historical root cause — verdict

CLAIM TESTED: "ARM-A owner retention + MINIMAL_GPU_TEARDOWN=0 caused the
good→bad flip."

Verdict: **NOT PROVEN — do not resurrect.**
- MINIMAL_GPU_TEARDOWN=0 is present in good AND bad cohort configs
  (re-derived: run manifests 20260821-123804 through 20260825-110538, profiles
  e37-clip-qd4/e37-clean-lane-qd4/r43-known-fast/r44-request-fastsafe/
  production — all `MINIMAL_GPU_TEARDOWN="0"`), matching the Phase O/OB
  finding quoted in the brief. A constant cannot be the discriminator.
- Additionally, the flag was INERT in-container: `_runtime_env()` does not
  forward it; containers resolved mode from SINGLE_USE_CONTAINERS=1 → minimal.
  So even the premise "MINIMAL=0 caused full teardown to run" is false for
  these deployments.
- ARM-A owner retention: no artifact in this workspace directly demonstrates
  owner-retained GPU tensors inside the terminal-cleanup window of the bad
  cohorts (no [v2.teardown] stage captures, console_capture=null). The
  temporal association with R44I3 ARM-A deploys is real but is confounded with
  (i) the checkout/lane change (0c59f46 → 6040c459+J1) and (ii) any
  host/state variance. Temporal adjacency ≠ cause.
- Kept strictly separate: the 2026-08-05 controlled A/B remains valid
  OPTIMIZATION evidence (function-level saving ~2.56 s + ~0.63 s). It is NOT
  regression-cause evidence for the 2026-08-24 flip and must not be cited as
  such.

## 6. First-durable → exit ownership map (code order)

1. `output_persist_done` + `first_durable_result` (= `remote_result_emit`)
   — modal_app.py:19780-19853. Owner: OUTPUT/result assembly. Files already
   written (:16107-16152); ledger report persisted into artifact here.
2. Outer loop identifies terminal event; `request_terminal_start`.
   — :17897-17905.
3. TERMINAL-CLEANUP WINDOW (the audited teardown span):
   production registry cleanup + GPU release (bounded or full per resolved
   mode). Owners: TEARDOWN. Excludes everything in 4-8.
   — :17739-17774, :6009-6410; stamped :17906-17926.
4. Yield → Modal transport → `local_result_received` → local merge →
   `execute_plan_return`. Owner: PLATFORM TRANSPORT + host.
   — :17927; E6 steps 4-6; `_stamp_remote_result_emit` docstring :5419-5425.
5. Stream tail/finalizer: `_finalize_deferred_commit` — awaits asset Volume
   commit (OUTPUT-owned late work), emits definitive persistence event;
   fallback release only if step 3 never ran. — :16215+; impl tail; outer
   finally :17967-17997.
6. Decorated wrapper `finally`: `_release_after_stream_complete` — guard
   reset + effective re-release after frame death. Owner: TEARDOWN (second
   entry). — :17776-17814, :20160-20164.
7. `@modal.exit`: service cleanup + conditioning-cache flush/final commit +
   conditional release if terminal delivered; `exit_hook_start/end` stamps.
   Owner: EXIT-OWNED APPLICATION CLEANUP (incl. one durability commit distinct
   from output assets). — :5843-5935.
8. `python_atexit` stamp (teardown_diagnostics.py:412-432), then platform
   process termination; OS reclaims remaining CUDA (no app empty_cache).
   Owner: PLATFORM. — E6 §True-Exit; A/B row "CUDA allocated after release".

FIRST_DURABLE_TO_EXIT therefore decomposes into: [teardown window] +
[transport] + [deferred commit drain] + [post-stream re-release] + [exit hook]
+ [platform termination]. No existing timing measures that sum end-to-end;
every historical teardown number covers only component(s).

## 7. Evidence gaps

1. O5/O6/O7/O8, OB6/OB7/OB8, "SoT / v2.1" documents absent from both
   checkouts (searched filenames + contents). Brief attributions re-derived
   from primary artifacts where possible.
2. Per-stage release timings (`request_gpu_release_end.stage_results`) and
   J2 `gpu_release_begin/end` decomposition exist only in container stdout;
   `console_capture=null` for v2ctl-era runs and
   `COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS` not in effective_environment → bad
   cohort inflation (C4) has NO stage-level attribution.
3. Early-exit identity (disabled vs already_released) for the 0.1 ms sub-band
   not recorded in artifacts.
4. In-container teardown_mode is inferred (env-forwarding analysis + magnitude
   match), not read from a per-run container record, for ALL v2ctl-era runs.
5. No timing spans first-durable→exit continuously; exit-hook and release
   stamps are disjoint intervals; python_atexit has no elapsed pairing.
6. C5/C6 cohort modes unrecorded (pre-v2ctl tooling era).
7. `record_volume_commit` is a stub returning None
   (teardown_diagnostics.py:440-441) — volume-commit events are not actually
   captured despite the API name.
8. OC6 cross-reference: OC6-relevant boundaries used here
   (first_durable_result, remote_result_emit, local_result_received,
   execute_plan_return, exit_hook_start/end, python_atexit) are cited from
   existing artifacts/source per instructions; OC6 output not waited on.

## 8. Raw appendix (verbatim extracts)

A/B table (V2_VARIANCE_CAUSAL_FIX_REPORT.md:17-31):
```
| Metric | A: full `unload_all_models()` | B: minimal bounded cleanup |
| Run | `v2_2026-08-05_23-33-32` | `v2_2026-08-05_23-36-01` |
| `teardown_mode` | `full` | `minimal` |
| Terminal release elapsed | **2,560.334 ms** | **2.455 ms** |
| `model_management_unload` stage | 1,929.4 ms | skipped |
| `garbage_collection` stage | 627.3 ms | skipped |
| `device_fallback` / `cleanup_models` / `cuda_cleanup` | ran | skipped |
| CUDA allocated after release | 34,603,008 B (reclaimed) | 12,634,373,120 B (retained; released at process exit) |
| Post-stream re-release | 633.8 ms (idempotent re-run) | 2.0 ms |
| `exit_hook_start` → `exit_hook_end` | 23.9 ms | 20.3 ms |
| Result delivery | 107 outputs, exit 0 | 107 outputs, exit 0 |
| Container disappeared after exit hook | yes | yes |
```

Terminal-cleanup cohort extraction (method: regex over every
runs/*/run_0.json|run_001_sample.json,
`terminal_cleanup_start_wall_unix_ns` vs `..._end_wall_unix_ns`; wall ns diff;
full listing preserved in session transcript; representative values):
```
v2_2026-08-14_20-54-44 2257.4 | 21-25-55 2111.4 | 21-47-28 2330.0 | 22-20-03 2311.5
v2_2026-08-14_22-24-00 2238.4 | 22-26-50 2452.9 | 22-43-10 2482.2 | 22-46-08 2266.6   (interleaved 0.1 ms runs)
v2_2026-08-17_16-04-13 2307.8
v2_2026-08-19_20-50-05 867.0 | 20-54-34 380.8 | 21-06-32 880.0   (neighbors 0.1–1.1)
v2_2026-08-23_20-53-40 … 20-56-38  0.5–0.7   (r43-known-fast, 0c59f46)
v2_2026-08-24_12-11-30 0.5 | 16-52-02 0.7 | 19-29-04 0.6        ← last good
v2_2026-08-24_21-03-26 3785.7 | 21-06-25 3266.3 | 21-07-28 6869.7 ← first bad
v2_2026-08-24_21-37-12 3181.5 | 21-38-23 6780.7 | 21-39-59 6867.4
v2_2026-08-24_21-57-31 6338.4 | 21-58-42 6373.3 | 21-59-33 3201.3
v2_2026-08-25_01-05-13 6623.9 | 01-30-55 3541.9 | 01-37-17 7036.7 | 01-38-26 6981.5
v2_2026-08-25_02-18-37 6592.1 | 02-23-38 3504.8 | 02-28-50 8319.5 | 02-33-39 6977.4
v2_2026-08-25_02-50-39 3080.4 | 02-51-37 6495.8 | 02-52-47 8460.8 | 02-53-53 6969.4
v2_2026-08-25_02-55-12 3133.7   (current-bad reference, K1 §7)
v2_2026-08-25_06-13-50 4096.1 | 06-16-03 2294.3 | 06-21-47 2204.0 | 06-49-33 7658.0
v2_2026-08-25_06-51-50 3007.8 | 06-55-04 7116.7 | 07-00-09 11812.7 | 07-01-28 6998.4
v2_2026-08-25_15-34-30 3143.0 | 16-00-31 3102.4 | 16-04-15 3272.1
(pre-08-14 eras: field absent)
```

Config provenance (effective_environment, `.v2ctl/runs/` manifests):
```
good v2_2026-08-23_20-5x (run_20260823-155723_98eb4e88.json): profile=r43-known-fast
  git_head=0c59f46e3238f421378e8852ebc548da815b70af
  COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN="0" RELEASE_GPU_AFTER_REQUEST="1"
  COMFYMODAL_V2_SINGLE_USE_CONTAINERS="1"
bad v2_2026-08-25_15-34-30 (run_20260825-103525_4433bbc1.json): profile=r44-request-fastsafe
  git_head=6040c459f2766f2ccb2f97799c08ff53b616d54a (lane comfyui-modal-r42, J1 dirty)
  COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN="0" (source=default) RELEASE_GPU_AFTER_REQUEST="1" (profile)
  COMFYMODAL_V2_SINGLE_USE_CONTAINERS="1" (profile)
all v2ctl-era manifests checked (both checkouts, 08-21→08-25): identical trio.
```

Env-forwarding proof (`_runtime_env`, comfymodal_runtime/modal_app.py:2974+):
forwards `COMFYMODAL_V2_SINGLE_USE_CONTAINERS` and
`COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST`; `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN`
NOT in the built env (only sites: request allowlist :589, reads :6020/:6181,
required-env identity list :16476).

Current-run terminal-cleanup sample (v2_2026-08-25_16-04-15/run_0.json):
```
"terminal_cleanup_start_wall_unix_ns": 1787673918517239417
"terminal_cleanup_end_wall_unix_ns":   1787673921789345397   → 3272.106 ms
```

Key source sites (orchestration checkout, working tree):
release fn :6009-6410; mode select :6020-6026; bounded stages :6124-6235;
full-only stages :6239-6377; terminal sync :17739-17774; guard-reset
re-release :17776-17814; wrapper finally :20130-20165; exit hook :5843-5935;
join budget :308 (_PRELOAD_WORKER_JOIN_BUDGET_S = 5.0); production cleanup
:15821-15862; deferred commit :16215+; stamps :5412-5488/:5491-5516;
first-durable block :19780-19856; asset persistence :16082-16179;
diagnostics class teardown_diagnostics.py (emit :347-386; atexit :412-432;
stub :440-441).

## 9. Hashes

SHA-256 (PowerShell Get-FileHash, 2026-08-25):

Deliverables:
```
835F6EB17B91C87748A732776A24AA67D67B7A5337B5D19D13C8BE99E45147D7  OC7_TEARDOWN_TIMING_COMPLETENESS_2026-08-25.md (pre-hash-append content basis; this section added post-write — see CSV for paired claim set)
83C8530177059157AF8C78FCB2987C3A031C0D2AE70D3E11219C3C4D5A6803CA  OC7_TEARDOWN_TIMING_CLAIMS_2026-08-25.csv
```

Primary evidence files as read:
```
58F7F999E178F14EEDB3299D1215E042F9B840A6F113A908593572487BBF2CEC  V2_VARIANCE_CAUSAL_FIX_REPORT.md
BA9101E5FB04D6E82B5E6962E38CA102EC0134E8C2B63D450803FE58D514832D  docs/v2-single-use-container-teardown.md
838FFBE272865813E781391F128F7BBF5E0B2D617AD8BB725F5A0FD96C289F10  V2_BATCH_E6_POST_RESPONSE_GPU_CLEANUP.md
55722C892D7331D24E98ECDE02DD88FF5AB8A341452E602AC6FAFEEF227F8137  comfymodal_runtime/modal_app.py   (matches K1 recorded before-state SHA)
8EA514A953751B9A99066C03A2C1685BD73C8A3D5B52D8B5E213E5124AE11941  comfymodal_runtime/teardown_diagnostics.py
```
