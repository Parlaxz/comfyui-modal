# E38B — Canonical Timing, Reconciliation, and Fail-Closed Validation Contract Audit

Date: 2026-08-21 · Scope: current local checkout (dirty, preserved) + raw E37 artifacts · Mode: READ-ONLY forensic audit. No source, test, profile, or deployment changes were made. The only file created is this report.

Authoritative inputs:
- Run artifacts: `..\..\comfymodal-data\benchmarks\runs\v2_2026-08-21_22-35-45\` (`run_001_sample.json`, `run_0.json`, `summary.json`, `campaign_manifest.json`, `run_001_sample.json.v2ctl-provenance.json`)
- Gate: `.v2ctl/gates/gate_20260821-223621_f76e3da7.json`
- Source: `comfymodal_runtime/v2_waterfall.py`, `comfymodal_runtime/critical_path_ledger.py`, `canonical_execution.py`, `tools/v2_control/{backend,validation,cli}.py`, `comfyapp.py`, `comfymodal_runtime/modal_app.py`

Evidence language: **CONFIRMED** (source+artifact proven), **SUPPORTED INFERENCE**, **HYPOTHESIS**, **UNKNOWN**, **UNOBSERVABLE**.

---

## 1. Executive verdict

1. **ROOT CAUSE CONFIRMED** for the E37 `-7741.041552 ms` residual. It is *not* a clock-domain bug and *not* a single defect. It is the exact sum of two stacked accounting failures in the legacy waterfall's reconciliation formula (`v2_waterfall.py:2275-2316`):
   - **Component A = 6607.378944 ms** — the "Modal scheduling" window is closed at two different timestamps in two waterfall views: the local/final view closes it at a Modal-log-derived wall timestamp `1787351764187174144`, the remote partial view closes it at the container's own `time.time_ns()` python-resume stamp `1787351757579795200`. The 6.607 s gap between those two domains is double-counted: once inside `scheduling_time_ms` and again inside the application stage chain.
   - **Component B = 1133.662608 ms** — even with the remote (container-consistent) scheduling boundary, the application chain (10593.168308 ms) exceeds the host post-scheduling window (9459.5057 ms) because the host command→response boundary precedes container durable completion, compounded by a ≥1.1 s cross-machine wall-clock offset proven by a cause/effect inversion (`remote_result_emit` container-wall stamp appears 1103.36 ms *after* the local caller-return stamp that causally follows it).
   - Verification: `6607.378944 + 1133.662608 = 7741.041552` — exact to the last decimal of `reconciliation_ms = -7741.041552000001`.
2. **The E38 clock-mismatch theory (perf_counter vs monotonic epochs) is FALSE for this system.** Remote containers run CPython 3.11 on Linux where both functions use the same underlying clock; local Windows Python 3.11.9 does use different clocks, but no production code path ever subtracts across the two functions. The real cross-domain hazards are: (a) Modal log-line timestamps vs container `time.time_ns()`, (b) host Windows wall vs container Linux wall.
3. **Gate-valid and `validation_status=FAILED` coexist because they are disjoint validation layers with no cross-check**: the canonical gate (`tools/v2_control/validation.py`) predicates on backend exit code, output SHA, QD mode/fallback, 240/240 reconciliation, and provenance — it never reads the artifact's waterfall `validation_status`/`reconciliation_ms`.
4. **Recommendation**: keep the canonical critical-path ledger as the ONE acceptance truth; demote the legacy waterfall to diagnostic-only (Option B). Repair its two known defects so its diagnostics stop lying, but never let it gate acceptance.

---

## 2. Runtime Python / clock facts

| Fact | Value | Evidence |
|---|---|---|
| Remote image Python | `modal.Image.debian_slim(python_version="3.11")` on all V2 images → CPython **3.11.x Linux** | CONFIRMED, `comfyapp.py:8273` (+ ~20 more sites); exact micro version not pinned → UNKNOWN |
| Local control-plane Python | **3.11.9 on Windows** | CONFIRMED (measured during audit) |
| CPython 3.11 Linux: perf_counter vs monotonic | **Same underlying clock** (`pytime.c`: `_PyTime_GetPerfCounterWithInfo` delegates to `_PyTime_GetMonotonicClockWithInfo`; typically `clock_gettime(CLOCK_MONOTONIC)`) | CONFIRMED (CPython source + docs) |
| CPython 3.11/3.12 Windows | Different clocks: monotonic=`GetTickCount64()`, perf_counter=`QueryPerformanceCounter()`; different origins | CONFIRMED (docs/source) |
| CPython 3.13 | perf_counter changed to use the same clock as monotonic on all platforms | CONFIRMED (docs "Changed in version 3.13") |
| Cross-process comparability | Both clocks are system-wide per machine → comparable within one machine, same function; **never comparable across machines/containers** | CONFIRMED (docs) |
| `get_clock_info` recorded in any E37 artifact | No | CONFIRMED absent → E39 must record `time.get_clock_info("monotonic")` and `("perf_counter")` at runtime in both processes |
| Docs' epoch guarantee between the two functions | None ("reference point of the returned value is undefined"); only same-clock differences are valid by contract | CONFIRMED |

Consequence: on the actual remote runtime (Linux 3.11), mixing `perf_counter_ns` and `monotonic_ns` absolute values would not even misbehave in CPython practice — but it is still a documentation-level contract violation and must stay banned.

---

## 3. Clock Domain Registry

| # | Domain | Producer sites (examples) | Process / machine / OS | Clock fn | Unit | Monotonic | Cross-process comparable | Serialized fields (examples) |
|---|---|---|---|---|---|---|---|---|
| D1 | Remote mono axis | `critical_path_ledger.py:93-107`, `contracts.py:1406-1441`, `clean_lane.py:47`, `checkpoint_prewarm.py` | remote container, Linux | `time.monotonic_ns()` | ns | yes | within container only | `mono_ns`, `*_mono_ns`, ledger span/event endpoints |
| D2 | Remote wall | `contracts.py` TraceEvent `wall_unix_ns`, `_restore_timing` (`remote_python_resume_wall_unix_ns`, `restore_method_start/end_wall_unix_ns`), `timing_trace.py:776-784` | remote container | `time.time_ns()` | epoch ns | no | only vs same machine | `wall_unix_ns`, `*_wall_unix_ns` |
| D3 | Remote perf | `clip_qd_reader.py:664-1729`, `clip_fast_hydration.py:497-851`, `clip_fp32_cast_once.py` | remote container | `perf_counter[_ns]()` | s/ns | yes | within process | QD read/issue/completion ms, hydration stage ms |
| D4 | GPU events | `clip_qd_reader.py:1459-1462` | remote GPU | `torch.cuda.Event(enable_timing)` | ms (GPU) | yes (stream-ordered) | no | H2D CUDA-event ms |
| D5 | CPU/thread timers | `clip_qd_reader.py:1245-1268`, `checkpoint_prewarm.py:560,769-782` | remote container | `process_time()`, `thread_time()` | s | per-process/per-thread semantics | no | `cpu_ms`, `thread_cpu_ms` |
| D6 | Local host wall | `modal_client.py:470-542`, `canonical_execution.py:213,2001-2079,3071,3318`, `worker_control.py` | local Windows host | `time.time()/time_ns()` | epoch s/ns | no | only vs same machine | `t0/t1`, `local_receive_wall_ns`, `caller_return_wall_unix_ns`, `created_at` |
| D7 | Local host mono | `canonical_execution.py:2603-2647,3319`, `experiment_service.py:576` | local Windows host | `monotonic_ns()/perf_counter_ns()/monotonic()` | ns/s | yes | within host only | `local_receive_mono_ns`, transport interval ms |
| D8 | Modal log-line timestamps | parsed Modal app logs feeding waterfall stages with `provenance:"modal_app_log"` | Modal infrastructure (clock source undocumented) | unknown (server-side or observation-time) | epoch ns after parse | n/a | **NOT valid vs D2/D6** | `modal_scheduling` start/end, restore-banner boundaries |
| D9 | Filesystem mtimes | `backend.py:905,936`, `experiment_service.py:1156-1159`, `comfyapp.py:17226`, `run_history.py:196-201` | local host | `st_mtime` | epoch s | no | host only | artifact selection order |
| D10 | CUDA event host issue | `clip_qd_reader.py` paired H2D timing | remote | perf_counter around issue + CUDA elapsed | ms | yes | no | `h2d_host_issue_ms=127.399`, `h2d_cuda_ms=27.3155` |

Arithmetic-domain violations found (all CONFIRMED in E37 artifact unless noted):
- V1: D8 vs D2 — `pre_python_snapshot_restore` start (log domain) vs end (container wall): −6607.378944 ms inversion.
- V2: D8 vs D2 — `modal_scheduling` end differs 6607.378944 ms between final and remote waterfall views (same pair, different consumer).
- V3: D2(container) vs D6(host) — `submission_to_remote_python_resume_ms=12094.987` and `remote_result_emit→local receipt` carry unquantified inter-machine offset; offset ≥1103.362 ms proven by emit-after-return contradiction.
- V4: D1(remote mono) vs D6/D7(local) — `remote_local_return` (31.0 ms, local mono `462110812000000`) sits in the same additive chain as remote-mono stages.
- No V-type violation exists for perf_counter-vs-monotonic within one process (searched exhaustively; zero mixed-function subtractions).

---

## 4. E37 authoritative endpoint map

Run: request `v2-benchmark-0-c9ac6e750942`, profile `e37-clean-lane-qd4`, fresh restored container (`fresh=true`, `restore_count=1`).

| Endpoint | Source fn / place | Clock domain | Process | Point/interval | Can be absent | Zero valid | Accounting bucket |
|---|---|---|---|---|---|---|---|
| Restore banner (platform) | Modal log parse → waterfall platform stages | D8 | infra/host | point | yes | no | scheduling/platform |
| `remote_python_resume` | `_restore_timing.remote_python_resume_wall_unix_ns` + ledger mono twin | D2 + D1 | remote | point | no (E37 present) | no | platform→application seam |
| `modal_restore_entry` / `modal_restore_exit` | ledger events (names confirmed in artifact event list) | D1 | remote | points | yes | no | restore |
| restore method start/end | `_restore_timing.restore_method_start/end_wall_unix_ns` | D2 | remote | interval bounds | no | no | restore |
| method entry | ledger `modal_method_entry` / trace `remote_method_entry` | D1/D2 | remote | point | no | no | application start |
| plan identity accepted | ledger `plan_received`/`plan_deserialize_*` | D1 | remote | interval | yes | no | application/setup |
| QD start / first / last completion / device-ready | ledger `clip_qd_*` events; stats dict | D1(+D3,D10) | remote | points + intervals | yes | no | CLIP source |
| CLIP bind / forward start-end | ledger `clip_qd_bind`, forward spans | D1/D3 | remote | interval | no | no | CLIP forward |
| UNET load | model-mgmt ledger spans (`load_models_gpu` 840.785) | D1 | remote | interval | yes | no | UNET |
| sampling start/end | ledger/waterfall measured stages (220765653645→225514019797) | D1 | remote | interval | no | no | sampler |
| VAE transition/decode | `post_sampling_transition`, `vae` stages | D1 | remote | intervals | no | no | VAE |
| output start/end | `output_persistence` (encode/descriptor children) | D1 | remote | interval | no | no | output |
| first durable | ledger `first_durable_result` mono `226925149733` = `output_persistence.end` | D1 | remote | point | no | no | durable boundary |
| remote terminal | `remote_result_emit` (≈ first_durable here, Δ7.7 µs) | D2 | remote | point | yes | no | response handoff |
| post-durable cleanup | detail `output_deferred_commit` (UNAVAILABLE in E37) | — | remote | interval | yes | — | post-durable |
| local first response / caller return | `execute_plan_return` emit (`canonical_execution.py:3318-3327`) | D6/D7 | local | point | no | no | response |
| command-to-response | waterfall `total_ms = 25915.3009` (command_start→caller_return) | D6 | local | interval | no | no | top-level total |

Ledger serial chain (authoritative, zero-gap, `canonical_ledger_status="ok"`): `remote_python_resume_mono → first_durable_result_mono` = 10562.860481 ms, tiled by: restore:early 9.006, restore:eviction 343.996, restore:snapshot 4.086, restore:preamble 44.159, restore:bootstrap 250.764, restore:preload 0.947, restore:finalize 7.64, identity-capture 0.068, plan-deserialize 0.706, setup-schedule 91.571, CLIP hydration 1149.953, load_models_gpu 0.803, CLIP forward 1110.221, load_models_gpu 840.785, sampling 4748.2, load_models_gpu 57.792, VAE decode 381.287, graph-tail 166.932, executor:graph-execution 9658.875 (parent scope), result:assembly 93.142, request:executor-run 9746.282 (parent scope). Parent scopes overlap children by design (union accounting), children tile the axis.

---

## 5. Timing producers and consumers

| Product | Boundaries claimed | Consumes | Sum vs union | Double-count risk | Clamps/invents zero | Stale-survival | Overwrite risk | Accepts failed proc? | Runs before freeze? |
|---|---|---|---|---|---|---|---|---|---|
| `critical_path_ledger` (remote) | resume→first_durable, zero-gap | D1 stamps at code sites | child UNION + labeled residual | no (by construction) | no (UNATTRIBUTED label) | no (request-scoped reset) | no | reports regardless; status field exists | finalized in-container before result |
| Canonical ledger validation (gate) | algorithm proof | ledger payload via sample record | n/a | no | no | reads only run_001_sample record | no | only via exit_code predicate (gap §11) | after artifact write |
| `final_reconciled_waterfall` (host) | command→response split sched/non-sched | D6/D7/D8/D2/D1 mixed | SUMS top-level stages | **YES (V1-V4)** | marks INVALID, no clamp; missing→unavailable | merges legacy stages if remote empty (`canonical_execution.py:2562-2566`) | host re-renders over remote report | n/a (diagnostic) | yes — attached before caller-return stamp |
| `remote_partial_waterfall` | same, remote boundaries | D1/D2 | sums | YES (component B) | same | no | preserved if valid | n/a | in-container |
| `gantt_canonical` / render | visualization of above | waterfall report | display | inherits | display "-" | inherits | no | n/a | n/a |
| `full_execution_trace` | event stream | merged D1-D7 events | raw | carries mixed domains | no | merged last-wins (`_host_boundary_*` LAST occurrence) | merge can shadow remote with host events | n/a | yes |
| `summary.json` timing | mixed legacy aliases | many producers incl. `restore_total_ms`=startup alias (`modal_app.py:9674,9690`) | mixed | YES (aliases) | defaults 0 in places | YES (restore_breakdown carries non-request lifecycle values) | record builder selects | n/a | written by store |
| `restore_breakdown` | "restore" | startup-path aggregates | mixed | YES | zeros | **YES — `backend_startup_ms=20091.85` cannot be inside this 678 ms restore()** | no | n/a | n/a |
| `experiment_result_store` record | sample record | result dict | passthrough | inherits | inherits | inherits | builds run_001_sample | n/a | before gate |
| Host reconciliation (`canonical_execution.py:2603-3023`) | t1→submission leaves | D6/D7 (+D2 for cross-process lines) | leaf sums w/ signed residual | guarded (overlap_error) | None→None (no zero-invent) | per-request | no | n/a | yes |
| backend/v2ctl validation | acceptance | exit code, SHA, QD, provenance | n/a | no | no | binds identity strictly (§10) | no | **exit_code==0 only** | after write |
| Gate JSON | acceptance record | validation.py predicates | n/a | no | no | no | no | see §11 | final |
| first-durable reporting | durable boundary | ledger endpoint | point | no | no | endpoint-bound (`set_authoritative_endpoints`) | no | n/a | in-container |
| command-to-response reporting | command→caller return | D6 | interval | no | no | no | no | n/a | at return |

Key structural facts:
- Reconciliation formula (CONFIRMED, `v2_waterfall.py:2275-2316`): `accounted_denom = non_scheduling_ms (= total − scheduling_time)`; `accounted = Σ(top_level ∧ included_in_total ∧ ¬concurrent ∧ duration≠None ∧ status≠INVALID)`; `reconciliation = accounted_denom − accounted`; FAILED when `|reconciliation| > RECONCILIATION_HARD_MS (50)`.
- Negative residuals are retained and surfaced (warnings + EXCEEDS_TOLERANCE), never clamped — good. But nothing downstream consumes them (§1.3).
- Post-durable writes cannot retroactively flip an already-written gate JSON, but the waterfall attach happens *before* caller-return stamping (`canonical_execution.py:3304-3313`), i.e., diagnostics are computed mid-finalization while later fields (`caller_return_*`) are still mutating the result — a freeze-order smell (SUPPORTED INFERENCE).

---

## 6. Exact derivation of the −7741 ms residual

All values from `run_001_sample.json` (CONFIRMED):

```
total_ms                = 25915.3009                     (command_start → caller_return, host wall)
command_to_enqueue_ms   = 4360.8079                      (local_preparation 4251.808 + handle_submission 108.9999)

── final_reconciled_waterfall ──────────────────────────
modal_scheduling        = 18702.366244                   [1787351745484807900 → 1787351764187174144]  (end: D8 log domain)
scheduling_time_ms      = 4360.8079 + 18702.366244 = 23063.174144
non_scheduling_ms       = 25915.3009 − 23063.174144  =  2852.126756
accounted               = Σ app-chain top_level stages   = 10593.168308
reconciliation          = 2852.126756 − 10593.168308     = −7741.041552   ✓ EXACT MATCH

── remote_partial_waterfall ────────────────────────────
modal_scheduling        = 12094.9873                     [1787351745484807900 → 1787351757579795200]  (end: D2 container wall = python_resume)
scheduling_time_ms      = 4360.8079 + 12094.9873   = 16455.7952
non_scheduling_ms       = 25915.3009 − 16455.7952   =  9459.5057
reconciliation          = 9459.5057 − 10593.168308       = −1133.662608   ✓ EXACT MATCH

── decomposition ───────────────────────────────────────
A = 1787351764187174144 − 1787351757579795200 = 6607378944 ns = 6607.378944 ms   (same start, two different ends)
B = 1133.662608 ms
A + B = 7741.041552 ms = |−7741.041552000001|                                    ✓ EXACT
```

The application chain (identical in both views), ms:
`application_restore 678.229882 + restore_to_method_entry 46.486813 + remote_method_setup 126.00899 + prompt_executor_cache_setup 308.285 + pre_sampler_execution 2356.85 + sampler_node_to_sampling 887.446315 + sampling 4748.366152 + post_sampling_transition 769.52306 + vae 381.6909 + output_persistence 259.281196 + remote_local_return 31.0 = 10593.168308`.

Why the chain exceeds each window:
- **vs remote window (B)**: chain spans resume→first_durable ≈ 10562.86 ms on the container mono axis (resume mono 216362289252 → durable mono 226925149733; independently confirmed by container-wall resume→emit = 10562.868138 ms, Δ7.7 µs). The host window grants only 9459.51 ms because `total_ms` ends at host caller-return, which — after subtracting enqueue+submission→resume — lands ~1.1 s before the container's durable/emit moment. Proof of inter-machine offset: `remote_result_emit` container-wall `1787351768142663338` vs derived host caller-return wall `1787351741124000000 + 25915.3009 ms = 1787351767039300900` → emit appears **1103.362 ms AFTER** the return that causally follows it. Cause-after-effect ⇒ the two wall clocks disagree by ≥1.1 s (CONFIRMED contradiction; exact skew vs network transit split: UNKNOWN).
- **vs final window (A)**: additionally, the final view stretches the scheduling window 6.607 s past python-resume by using the D8 log-domain timestamp, pulling 6.607 s of already-counted application time into `scheduling_time_ms` as well.

Competing explanations (from the brief) — verdicts:
- A perf/monotonic mismatch: **REJECTED** (§7).
- B child spans double-counted: **REJECTED as cause** (ledger unions; waterfall sums only top-level exclusive stages).
- C overlapping children summed: **REJECTED** for the −7741 (top-level stages are sequential); minor overlaps exist but are flagged INVALID, not summed.
- D parent/child semantic mismatch: **PARTIAL** — true between waterfall "scheduling" and ledger "restore", but not the arithmetic cause.
- E stale backend_startup/restore fields: **CONFIRMED as a separate defect** (`restore_breakdown.backend_startup_ms=20091.85`), not part of −7741.
- F local/remote clocks mixed: **CONFIRMED — primary cause** (components A and B both).
- G stage starts before selected parent: **CONFIRMED** (application_restore starts inside scheduling window) — the structural enabler of the double count.
- H endpoint inversion: **CONFIRMED twice** (`pre_python_snapshot_restore` −6607.38; `remote_return_handoff` start 1787351768142663338 > end 1787351767018790900, inverted ~1123.87 ms) — symptoms of F.
- I legacy projection maps different meanings into one additive waterfall: **CONFIRMED** — the formula's premise "everything after enqueue is non-scheduling" is false when restore begins before the scheduling window closes and durable completes after response.
- J mutation/finalization order: **SUPPORTED INFERENCE** (waterfall attached pre-freeze) — not part of −7741.
- K other: none found.

**ROOT CAUSE CONFIRMED** (F + G + I, manifesting as H; quantified exactly).

---

## 7. Clock-mismatch hypothesis verdict (E38 correction)

**VERDICT: FALSE as stated.** `perf_counter_ns` vs `monotonic_ns` did not and could not produce −7741 here:
1. Remote runs CPython 3.11 on Linux where both are the same underlying clock (CONFIRMED, §2).
2. Exhaustive search found **zero** production call sites subtracting across the two functions (CONFIRMED, Lane A sweep + verification).
3. Container-internal consistency is excellent: resume→durable agrees between mono and wall axes to 7.7 µs (CONFIRMED).
The real defects are cross-*process/machine/infrastructure* wall comparisons (V1–V4) and a boundary-overlap accounting premise. E39 must not "fix" perf/monotonic mixing; it must ban cross-domain wall arithmetic and fix the waterfall window definitions.

---

## 8. Restore-field semantic reconciliation

| Concept (new name) | E37 field(s) | Value | Boundary actually measured | Verdict for canonical schema |
|---|---|---|---|---|
| Platform snapshot materialization | banner→python_resume; waterfall platform stages; `submission_to_remote_python_resume_ms=12094.987` (skew-contaminated) | ~12–18.7 s | Modal placement + snapshot materialization up to first Python byte | KEEP as platform span, endpoints from ONE domain (container), never logs×wall |
| Python restore method wall | `restore_method_ms=678.233` (start/end wall, D2); ledger tiles it | 678.233 | restore() entry→exit in container | KEEP (rename `restore_method_wall_ms`) |
| Restore child semantic spans | ledger `restore:*` (early 9.006, **eviction 343.996**, snapshot 4.086, preamble 44.159, bootstrap 250.764, preload 0.947, finalize 7.64) | Σ=660.598 | union of instrumented children inside restore(); ~17.6 ms unattributed vs method wall | KEEP (children of the above) |
| Legacy restore aggregate | `restore_total_ms=303.653` | 303.653 | comfyapp `_profile_ms(restore_start)` producer (`comfyapp.py:20631,22409`); **alias hazard**: `modal_app.py:9674,9690` writes `startup_total_ms` into the same key | DIAGNOSTIC-ONLY; rename or delete later |
| Legacy startup aggregate masquerading as restore | `restore_breakdown.backend_startup_ms=20091.85`, `folder_warm_ms=1096.655`, `sync_custom_nodes_ms=480.89`, … | mixed | startup-path aggregates (`modal_app.py:9674-10520` region); 20 s cannot fit inside the 678 ms method → different lifecycle segment carried under "restore" | DELETE from canonical; keep only under explicit `legacy_startup_breakdown` |
| Restore-exit → method-entry | `restore_end_to_modal_method_entry_ms=46.496` | 46.496 | seam span | KEEP |

These four "restore" numbers measure genuinely different boundaries and must NOT be forced equal. Today the shared `restore_total_ms` key with two producers (method wall vs startup aggregate) is the misleading alias.

---

## 9. Residual / double-counting findings and correct rules

Current state: ledger does union-accounting correctly with labeled residual; waterfall sums exclusive top-level stages but against windows that can overlap the chain; host reconciliation emits signed residuals + `overlap_error` without clamping (good); nothing clamps negatives to zero anywhere material (CONFIRMED).

Rules E39 must adopt:
1. Residual may be signed internally, but **negative residual outside ε ⇒ INVALID**, never clamped, never accepted.
2. Children are always interval-UNIONed; summing allowed only after pairwise-disjointness is proven from endpoints.
3. `work/wait/sync` must be declared inclusive/exclusive of children; default exclusive-with-union like the ledger.
4. Semantic unattributed time (labeled, e.g., ledger UNATTRIBUTED 17.6 ms in restore) is a *different property* from arithmetic reconciliation residual. Persist both, separately named.
5. Missing endpoint ⇒ field ABSENT (never 0); zero only when both endpoints exist and are equal.
6. A window and its content must share one clock domain and one process; cross-domain windows are UNRESOLVED, not reconciled.

---

## 10. Artifact association findings

- Canonical v2ctl discovery is strict-identity bound: invocation/request ID, profile, profile-config fingerprint, deterministic name/path ordering; ambiguity raises `ProvenanceError`; stdout request_id must match artifact (`backend.py:873-958`). Status literal `"validated"`.
- mtime selection survives ONLY in `legacy_mode` + non-strict branches, explicitly commented "Compatibility-only legacy selector… never enter this branch for canonical calls", and labels such records `provenance_validation_status="legacy_mtime"` (`backend.py:899-906,934-939,961`). **CONFIRMED: no canonical E37 path can consume an mtime-selected artifact.**
- Residual mtime/newest selectors exist OUTSIDE v2ctl (`comfyapp.py:17226`, `experiment_service.py:1156-1159`, `run_history.py:196-201`, tools scripts) — not reachable from the canonical gate; out of scope per instructions.
- Note: OneDrive-synced artifact trees make mtimes actively hostile (sync rewrites); the identity-bound design is what makes E37 trustworthy.

---

## 11. Process/container health findings

Today's health predicate (CONFIRMED): `backend_ok = (local backend subprocess exit_code == 0)` (`validation.py:179-183,1044`) plus artifact parseability and SHA equality. There is **no** predicate for: SIGABRT/native abort evidence, container terminal state, stream termination, partial-response detection, or timeout/cancel markers. An E36-style native abort occurring *after* result emission (or masked from the local capture) would leave exit_code 0 + parseable artifact + matching SHA ⇒ gate-valid. Crash-loop detection exists only as deploy/run log heuristics elsewhere, not in the acceptance invariant. This is the fail-closed gap.

Required fail-closed process-health predicate (spec, not implemented):
```
process_health = PASS iff ALL of:
  backend_exit_code == 0
  AND no abort signature in captured stderr/stdout (SIGABRT, "Aborted", core dump, native traceback)
  AND remote terminal marker present (remote_result_emit) AND stream ended with explicit terminal event
  AND result marked complete (not partial/cancelled/timeout)
  AND container terminal state observed clean OR explicitly absent-and-required-false
Any check unobservable ⇒ health = UNKNOWN ⇒ run NOT nominal.
```

---

## 12. Fallback / path status findings

Represented today: QD fallback/mode (`validation.py:820-827` — CLEAN_LANE fails on `fallback=true` or `mode!="QD4"`), conditioning decision/lookup status, clean-lane launch policy, speculative-hydration absence tolerance. NOT represented as run-level status: FASTSAFE/native fallback, duplicate-demand reread, cache fallback, plan/identity fallback, GPU-allocation rollback, source-reader retirement failure (some have local fields, none roll up).

Minimal contract (spec):
```
RuntimeStatus := NOMINAL | DEGRADED(reason_code+) | FAILED(reason_code+)
FAILED: process health FAIL, SHA mismatch, mandatory endpoint missing, exception in request path.
DEGRADED: any fallback engaged (qd/fast_safe/native/cache/plan/identity), speculative miss,
  duplicate demand reread, partial GPU rollback recovered, reader retirement failure,
  reconciliation INCOMPLETE (diagnostic), health UNKNOWN.
NOMINAL: all predicates of §15 pass with zero degraded reasons.
G1/E39 performance cohorts accept ONLY NOMINAL. DEGRADED runs may feed algorithm-proof cohorts, never performance statistics.
```

---

## 13. Canonical vs legacy timing recommendation

- Option A (make waterfall equivalent to ledger): high risk — requires re-plumbing window semantics across host/remote; large blast radius.
- **Option B (RECOMMENDED, least risky): canonical ledger is the single acceptance truth; legacy waterfall becomes diagnostic-only.** Concretely: (1) gate gains a ledger-completeness predicate and the §11/§12 predicates; (2) waterfall keeps rendering but its `validation_status` is renamed `diagnostic_status` and is explicitly excluded from acceptance; (3) repair its two defects (single-domain scheduling end = container python_resume; exclude pre-response overlap from accounted or reconcile against resume→emit window) so diagnostics stop lying; (4) summary.json restore aliases renamed/deprecated.
- Option C (new representation): unnecessary — the ledger already is the correct minimal representation; adding a third system increases divergence risk.
A diagnostic view may be incomplete without invalidating the E37 algorithm proof (which rests on the ledger + provenance + SHA, all intact), but it must be visually marked non-authoritative.

---

## 14. Proposed canonical timing schema (E39/G1)

```json
{
  "schema": "comfymodal.timing.v3", 
  "identity": {
    "invocation_id", "request_id", "run_id",
    "deployment_fingerprint", "resolved_config_fingerprint",
    "source_identity_status", "profile",
    "artifact_schema_version", "output_sha"
  },
  "health": {
    "process_terminal": {"exit_code": 0, "abort_signature": null, "stream_terminal": "result_complete"},
    "container_terminal": {"observed": false, "state": "unknown"},
    "runtime_status": "NOMINAL | DEGRADED(reason[]) | FAILED(reason[])",
    "fallback_reasons": [],
    "artifact_completeness": {"parseable": true, "frozen_before_validation": true, "missing_endpoint_set": []}
  },
  "clock_metadata": {
    "domains": {"remote_mono": "monotonic_ns@container", "remote_wall": "time_ns@container", "local_mono": "monotonic_ns@host", "local_wall": "time_ns@host"},
    "get_clock_info": {"remote": {"monotonic": {}, "perf_counter": {}}, "local": {"monotonic": {}, "perf_counter": {}}},
    "cross_domain_arithmetic_used": false
  },
  "boundaries": {  
    "command_start", "modal_submission", "restore_banner", "first_python", "python_restore_exit",
    "method_entry", "graph_start", "sampling_start", "sampling_end", "vae_start", "vae_end",
    "first_durable", "remote_terminal", "local_response"
  },  // each: {domain, process, value_ns}; every pair-arithmetic validated same-domain
  "spans": {      
    "restore": {"method_wall", "children_union", "children": {...}, "unattributed"},
    "setup", "clip_source": {"qd": {"start","first_completion","last_completion","device_ready","bind","h2d_host_issue","h2d_cuda"}},
    "clip_forward", "unet", "sampler", "vae", "output"
  },  // ledger-native, union-accounted
  "accounting": {
    "serial_axis": "remote_mono: first_python→first_durable",
    "union_coverage_ms", "semantic_unattributed_ms",
    "arithmetic_residual_ms", "residual_rule": "INVALID_if_abs_gt_epsilon",
    "partial_diagnostic_status": "ok | incomplete(set)"
  },
  "post_durable": { "persistence", "cleanup", "teardown", "excluded_from_first_durable_metric": true }
}
```

---

## 15. Single fail-closed acceptance invariant

A run is **ACCEPTED_NOMINAL** iff ALL hold; else exactly one state: `REJECTED(predicate_set)`:

1. backend process exited 0; no abort signature; stream terminally complete (§11)
2. artifact parseable AND frozen before validation ran
3. invocation/request/run identity exact; deployment/config/source fingerprints exact; profile exact
4. expected output SHA exact
5. canonical endpoint set complete (absences listed, never zero-filled)
6. all mandatory durations finite, non-negative, same-domain-pair computed
7. clock metadata recorded; no cross-domain arithmetic used
8. ledger serial axis zero-gap with union coverage; |arithmetic residual| ≤ ε(50 ms hard/10 ms target)
9. intended loader/path proven (QD4, no fallback, forced-miss encode executed)
10. RuntimeStatus == NOMINAL (§12)
11. first_durable proven on the authoritative endpoints
12. post-durable work excluded from the first-durable metric

E37 today: passes 3,4,5,9,11; fails 1-partly (no abort/stream checks exist), 7 (cross-domain arithmetic used in diagnostics), 8 (waterfall only — ledger itself is fine), 10 (status system absent) ⇒ under the new invariant E37's algorithm proof stands, but the run is NOT yet ACCEPTED_NOMINAL; it is algorithm-valid with diagnostic disagreement.

---

## 16. Required deterministic tests for E39 (spec — do not implement here)

| Test | Setup | Expected |
|---|---|---|
| negative_residual | parent 100, children sum 150 | status REJECTED(residual_negative); no clamp; diagnostic retains −50 |
| overlapping_children | two children sharing 30 ms | union used; coverage uses 170 not 200; no failure if declared concurrent |
| same_clock_vs_cross_clock | (a) mono−mono; (b) wall_container−wall_host | (a) computes; (b) refused at builder level → UNRESOLVED, never a number |
| missing_endpoint_vs_zero | end==start → 0; end absent → ABSENT | 0 accepted as zero; absent renders "absent" and fails completeness predicate |
| subprocess_nonzero_exit | fake backend exit 3 | gate REJECTED(process_exit) regardless of SHA |
| sigabrt_evidence | stderr contains SIGABRT marker, exit 0 | gate REJECTED(abort_signature) |
| partial_waterfall | submission marker missing | diagnostic partial_flags set; acceptance unaffected; ledger still gates |
| telemetry_persist_failure | ledger finalize raises | canonical_ledger_status="error"; gate REJECTED(ledger_missing) — never silent pass |
| stale_artifact_newer_mtime | older identity artifact with newest mtime | canonical selector ignores mtime; picks identity match; legacy path labels legacy_mtime |
| wrong_request_id | artifact id ≠ stdout id | ProvenanceError; gate invalid |
| wrong_config_fingerprint | resolved-config mismatch | gate invalid (already covered; keep as regression) |
| degraded_fallback | qd.fallback=true | RuntimeStatus DEGRADED(qd_fallback); excluded from NOMINAL cohort |
| postdurable_persist_fail_after_durable | first_durable ok, deferred commit raises | first-durable metric intact; run DEGRADED(post_durable), not FAILED |
| e37_style_disagreement | ledger ok + waterfall diagnostic FAILED | acceptance follows ledger+invariant; diagnostic disagreement reported, not gating |

---

## 17. Minimal source areas E39 will need to touch

1. `comfymodal_runtime/v2_waterfall.py` — single-domain scheduling end (use container python_resume, drop D8 end for window math); fix `remote_return_handoff` endpoint pairing; rename `validation_status`→`diagnostic_status`; keep render.
2. `tools/v2_control/validation.py` — add §15 predicates (ledger completeness, abort/stream health, RuntimeStatus, freeze-order check); consume ledger as truth.
3. `tools/v2_control/backend.py` — surface health fields already captured; no selection changes needed.
4. `canonical_execution.py` — mark cross-process wall intervals as UNRESOLVED-bounded (or annotate skew); move waterfall attach after caller-return stamping (freeze order).
5. `comfymodal_runtime/modal_app.py` — record `get_clock_info` + python micro version at container start; de-alias `restore_total_ms` startup writer (`:9674,9690`).
6. New small module: RuntimeStatus classifier (pure function over existing fields).
7. Tests: new files per §16.

## 18. Source areas E39 should NOT touch

- `comfymodal_runtime/critical_path_ledger.py` accounting core (union/residual contract is correct and proven).
- `comfymodal_runtime/clip_qd_reader.py` timing internals (paired H2D host+CUDA design is intentional and correct).
- Strict-canonical artifact selection in `backend.py` (identity binding is correct; do not "simplify" it back toward mtime).
- Profile TOMLs, deploy plumbing/BAT wrappers, flag registry (out of contract scope).
- Any historical report/markdown (claims, not code).

---

## 19. Final answers

1. **What exactly caused E37's negative residual?** The legacy waterfall reconciliation `non_scheduling_ms − Σ(application stages)` double-counted wall time across mismatched windows: 6607.378944 ms because the final view closed the scheduling window on a Modal-log-domain timestamp 6.607 s after the container's own python-resume stamp (the same mix that made `pre_python_snapshot_restore` negative), plus 1133.662608 ms because the application chain extends past the host response boundary — dominated by a ≥1.1 s container-vs-host wall offset proven by emit-after-return inversion, possibly plus a small genuine post-response durable tail (split UNKNOWN). Exact: 6607.378944 + 1133.662608 = 7741.041552.
2. **Is perf_counter_ns vs monotonic_ns actually a bug in this runtime?** No. Remote is CPython 3.11/Linux where both share one clock; no code mixes them; container axes agree to microseconds. The E38 theory is rejected; the real hazards are log-timestamp×container-wall and host-wall×container-wall comparisons.
3. **Which timing representation should be authoritative?** The remote critical-path ledger (`remote_python_resume_mono → first_durable_result_mono`, union-accounted, zero-gap, identity-scoped) — it is already correct and was the basis of the E37 algorithm proof.
4. **Which legacy timing fields should be diagnostic-only or deleted later?** Diagnostic-only: whole waterfall `validation_status` (→ `diagnostic_status`), `restore_total_ms` (ambiguous dual-producer alias), `restore_breakdown` aggregates (`backend_startup_ms`, `folder_warm_ms`, `sync_custom_nodes_ms`, …), `submit2entry`-style legacy deltas. Keep/rename: `restore_method_wall_ms`, ledger `restore:*` children, `restore_end_to_method_entry`, platform banner→first-python as a container-domain span.
5. **How could gate-valid and validation_status=FAILED coexist?** Two disjoint layers: the gate validates exit-code/SHA/QD/provenance/ledger-proof from the sample record; nothing reads the embedded waterfall's reconciliation verdict. No cross-check exists by design accident.
6. **Minimum change so that can never happen again?** Make the gate consume ONE acceptance object: add to `validation.py` the ledger-completeness + §15 predicates and a rule that any embedded diagnostic `EXCEEDS_TOLERANCE`/negative-residual forces review status (acceptance may still pass ONLY via the ledger invariant, with the disagreement recorded) — plus fix the waterfall's scheduling-window domain so the diagnostic stops producing false negatives.
7. **How should a structurally correct but timing-incomplete diagnostic run be labeled?** `RuntimeStatus = DEGRADED(diagnostic_incomplete, missing_endpoint_set=[...])` — algorithm proof may stand; excluded from G1/E39 performance cohorts; never FAILED unless a §15 mandatory predicate fails.
8. **What exact predicates must pass before G1 statistics are trustworthy?** All twelve of §15, with cohorts restricted to `RuntimeStatus == NOMINAL`, fresh-container identity verified per run, identical deployment/config/source fingerprints across the cohort, and clock metadata recorded for every run.

— End of E38B audit. No code, tests, profiles, or deployments were modified. Worktree state preserved.
