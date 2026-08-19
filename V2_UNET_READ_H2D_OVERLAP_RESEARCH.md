# V2 UNET Read → Construction → H2D Critical-Path Overlap Research

Date: 2026-08-13
Scope: READ-ONLY architecture/timeline investigation. No source code modified, nothing deployed, no generation requests issued.
Baseline: `V2_10_COLD_RUNS_35S_COOLDOWN.md` (10 cold runs, production-equivalent restore, UNET excluded from CPU snapshot, single-use containers).
Source evidence: `comfymodal_runtime/model_preload.py`, `comfymodal_runtime/modal_app.py`, `comfymodal_runtime/runtime_executor.py`, `comfymodal_runtime/restore_plan.py`, `comfymodal_runtime/cpu_snapshot_models.py`, `comfyapp.py`, `docs/round-results/2026-06-01-loader-seeding-retrospective.md`, `V2_SINGLE_INVOCATION_PLAN_EXECUTION_REPORT.md`.
Excluded mechanisms (do not reopen): pinned staging, whole-UNET cudaHostRegister, Sampling changes, CacheDiT changes, step reduction, output-quality changes, CLIP removal from snapshot.

---

## 1. Executive finding

The native fast-disk UNET pipeline (read → construct → bind → H2D) is **already maximally overlapped downstream of its start point**:

- Construction, bind, and H2D already run on the restore worker thread, concurrent with graph setup, PromptExecutor, and pre-sampler node execution — **not** at graph demand.
- H2D is **not** gated on `load_models_gpu`/graph demand. It fires in the worker immediately after bind (`_fast_disk_handle_bind` → `_fast_disk_replay_to`, `model_preload.py:4407`).
- The graph joins the worker's future at `UNETLoader` demand (`wait_unet`); on healthy runs this join wait is ≈0.

**The one genuinely avoidable serial edge is the read-start placement.** The lane is submitted at `modal_app.py:11416`, after `_configure_runtime`/`_load_legacy_runtime`, `graph_execution_start`, and the entire CPU-snapshot binding block (`modal_app.py:10926–11356`), plus the prefill submit. The model identity, checkpoint name, weight dtype, and the "snapshot has no retained UNET" decision are all knowable **at plan receipt** (~20–40 ms after method entry). Hoisting the lane submit to plan receipt recovers:

| Scenario | Exposed gap today | Recoverable by plan-receipt read start |
|---|---:|---:|
| Healthy exact hit (runs 2/6/8/9) | ~90–110 ms | **<200 ms** (≈70–110 ms realistic) |
| Slow first request / slow host (run 7, AWS) | ~600–660 ms | **500–1000 ms** (≈600 ms) |
| Bad-host bandwidth (run 4) | ~220 ms | **200–500 ms** (≈220 ms) |

**The bigger structural exposure is not schedulable:** on an exact hit there is no CLIP encode, so only ~0.66–0.92 s of pre-sampler node work exists to overlap the ~3.1–3.6 s UNET pipeline. ≈2.5–2.9 s of that pipeline sits exposed inside the pre-sampler window. That is a consequence of the exact-hit design (deliberately no concurrent GPU work), not of bad scheduling. Scheduling changes buy ≈100 ms healthy; they do not touch the H2D tail.

**Recommendation:** implement the plan-receipt read start (Section 13) as a low-risk, high-certainty scheduling change. Proceed — the change is cheap and safe, but its healthy ceiling is small (~100 ms); set expectations accordingly.

---

## 2. Current load/activation call graph

```
Modal restore()                          [no plan on no-publish path — identity unknown here]
  └─ restore completes → container snapshot: CLIP retained in CPU snapshot, UNET ABSENT
method entry (_run_plan_stream_impl, modal_app.py:15672)      [asyncio main]
  ├─ plan deserialize ExecutionPlan.from_dict (modal_app.py:15828)   [identity becomes derivable]
  ├─ plan_received status yield (modal_app.py:16306)
  ├─ RuntimeExecutor.stream → _run_in_process (modal_app.py:16312)
  │    ├─ _configure_runtime / _load_legacy_runtime / graph_execution_start (10907–10918)
  │    ├─ CPU-snapshot request binding block (10926–11356)
  │    │    ├─ derive keys, retarget, use_ready_clip → _init_ready_preparation
  │    │    ├─ _enforce_snapshot_activation_invariant (11361)
  │    │    └─ sets _cpu_snapshot_active / _cpu_snapshot_models (container state)
  │    ├─ schedule_execution_prefill (11382)   [pool submit #1 → prefill worker]
  │    └─ schedule_execution_unet (11416)      [pool submit #2 → restore worker]  ◄ READ STARTS HERE
  └─ _execute_v2_prompt_executor → executor.execute (13123–13145)   [asyncio main]
       ├─ pre-sampler nodes run on main thread (ImpactSwitch → ClownsharKSampler_Beta)
       ├─ graph reaches UNETLoader → _consume_unet (model_preload.py:10842)
       │    └─ coordinator.wait_unet → future.result()  (blocking join, ≈0 on healthy runs)
       └─ sampler wrapper: lane acquire + identity verify + residency proof (~125–137 ms)
```

Worker-side (restore worker thread, single flight, `schedule_execution_unet` → `_execution_unet` → `_load_unet` → original `UNETLoader`, `model_preload.py:10137–10156/10636`):

```
UNET active read (load_torch_file wrapper: read_start/read_end)
  → get_model (model_config.get_model, instrumented 5910)
  → model.to() deferred by fast-disk guard (_fast_disk_maybe_defer_to, 4273)
  → bind: load_model_weights(assign=True) (_fast_disk_handle_bind, 4322)
  → H2D: exactly one real original model.to(target) (_fast_disk_replay_to, 4008/4407)
  → publish future → graph join (wait_unet) → sampling
```

Key structural facts:

- The whole UNET pipeline runs **before and independently of** graph demand; the graph join is a cache-hit join.
- `schedule_execution_unet` needs only: bridge `_preparation` + `_model_key.unet_identity` + `_request_list("unet")` + the snapshot-unet-absent decision (`model_preload.py:10100–10128`). All four are derivable at plan receipt; the first two are currently only populated by the binding block.
- Single-flight/idempotent: `prep.unet_future is not None` → no-op (`model_preload.py:10110–10116`). Duplicate scheduling is impossible by construction.
- The lane-start marker `_EXECUTION_UNET_LANE_START_MONO` (`model_preload.py:10144`) is recorded on the worker; `COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS` (default 0) is the only intentional H2D delay.

---

## 3. Current critical path

Measured phases (method-entry-relative), from the baseline's per-run waterfall tables.

### Healthy runs (exact hit, cold, single-use)

| Phase (run 2 / 6 / 8 / 9) | Run 2 | Run 6 | Run 8 | Run 9 |
|---|---:|---:|---:|---:|
| restore → method entry | 15 ms | 34 ms | 16 ms | 19 ms |
| method entry → graph start | 84.5 ms | 198.4 ms | 181.2 ms | 92.8 ms |
| graph setup | 45.2 ms | 36.8 ms | 59.8 ms | 43.2 ms |
| PromptExecutor/cache setup | 9.4 ms | 7.9 ms | 14.9 ms | 14.8 ms |
| Pre-sampler execution (total) | 3618 ms | 3202 ms | 3657 ms | 3545 ms |
| ├─ conditioning exact-hit lookup (prefill worker) | 43.6 ms | 35.6 ms | 52.3 ms | 49.5 ms |
| ├─ pre-sampler nodes (main thread) | 831.5 ms | 662.3 ms | 756.5 ms | 809.5 ms |
| ├─ UNET read (worker) | 1187 ms | 1062 ms | 1323 ms | 1185 ms |
| ├─ read end → construction done | 0.2 ms | 0.1 ms | 0.5 ms | 0.2 ms |
| ├─ UNET get_model | 47.9 ms | 74.4 ms | 63.0 ms | 60.0 ms |
| ├─ bind | 20.4 ms | 18.4 ms | 28.1 ms | 23.3 ms |
| └─ H2D (GB/s) | 2332 ms (5.3) | 2008 ms (6.1) | 2224 ms (5.5) | 2219 ms (5.5) |
| sampler node → sampling (lane→stage) | 128.0 ms | 103.0 ms | 126.0 ms | 125.3 ms |
| sampling | 4806 ms | 4758 ms | 4802 ms | 4837 ms |

### Problem runs

| Phase | Run 4 (GCP/us-east4, bad host) | Run 7 (AWS/eu-south-2, slow first request) |
|---|---:|---:|
| restore → method entry | 15 ms | 270 ms |
| method entry → graph start | 228.8 ms | 633.6 ms |
| graph setup | 68.9 ms | 172.5 ms |
| Pre-sampler execution | 10681 ms | 5127 ms |
| ├─ nodes | 922.9 ms | 1268 ms |
| ├─ read | 1336 ms | 1708 ms |
| ├─ get_model / bind | 48.1 / 21.1 ms | 83.1 / 15.7 ms |
| └─ H2D (GB/s) | **9229 ms (1.3)** | 3274 ms (3.8) |
| sampler node → sampling | 137.1 ms | 130.5 ms |
| sampling | 4816 ms | 4884 ms |

### DAG (run 2, method-entry-relative, ms)

```
restore complete ─────────────── (before method entry; no plan available)
method entry (0)
  ├─ plan parse (≈20–40)
  ├─ plan_received yield / stream entry (≈+10)
  ├─ configure + legacy runtime + graph_execution_start (→ 84.5)
  ├─ snapshot binding block (→ ≈115) ──────────────┐
  ├─ prefill submit (≈11382)                        │
  ├─ UNET submit (≈11416)  ◄ READ START ≈115 ◄─────┘  [SERIAL EDGE S1]
  ├─ PromptExecutor invoke (≈130)
  │     ├─ exact-hit lookup 43.6  (prefill worker, concurrent)
  │     ├─ nodes 831.5 (main thread, concurrent with UNET pipeline)
  │     └─ worker: read 1187 → get_model 47.9 → bind 20.4 → H2D 2332
  │           → UNET READY ≈ 3702
  ├─ sampler node joins future (≈0 wait) → wrapper 128.0 → sampling start ≈ 3830
  └─ sampling 4806 → end ≈ 8636
  (reconciliation ≈ 2.6 ms — accounting closes; cumulative 13.214 s − method-entry offset 4.653 s = 8.56 s ✓)
```

Dependencies: read→get_model→bind→H2D is inherently serial (state-dict → config → module → weights → device). Concurrent spans: prefill lookup and pre-sampler nodes overlap the worker pipeline. Serial edges that are **avoidable**: S1 (plan receipt → read start). Serial edges that are **inherent**: plan parse, node execution, wrapper overhead, the read→H2D chain itself.

Exposed critical path (healthy): pre-sampler window 3618 ms − node work 831 ms ≈ **2787 ms** of UNET pipeline exposed (runs 6/8/9: 2540/2900/2735 ms). There is no concurrent GPU work on an exact hit to hide it.

---

## 4. Actual overlap already happening

1. **UNET pipeline vs pre-sampler nodes** — the worker runs read/construct/bind/H2D while the main thread executes ImpactSwitch/ClownsharK (≈0.66–0.92 s hidden). Already implemented via execution-phase lane (`schedule_execution_unet`).
2. **Prefill vs UNET lane** — CLIP prefill (exact-hit lookup 36–52 ms; full encode on miss) runs on the prefill worker concurrently with the UNET lane (submitted 11382 before 11416).
3. **VAE early activation** — VAE load/H2D (764–944 ms) overlaps the post-sampling/VAE-transition window via the sampler lane release (`schedule_vae_early_activation_at_sampling_end`). Same overlap pattern, different stage — proof the machinery exists.
4. **MutationLane serialization** — GPU-mutating commits (load_models_gpu) are serialized FIFO (UNET/CLIP/prefill/VAE/sampler). The fast-disk **H2D runs outside the lane** (it is not a `load_models_gpu` mutation).
5. **Early UNET activation** (`_run_early_unet_activation`, 13571) — overlaps retained-UNET H2D with CLIP encode, but **only for retained CPU-snapshot UNETs**; the fast-disk deployment shape is excluded by the eligibility gates (`unet_future_pending`/`no_retained_unet`, 12344–12367). Inapplicable here by design.

Measured overlap effectiveness: node work hides 21–23% of the UNET pipeline on healthy runs; the rest is exposed.

---

## 5. Earliest safe read start

**Plan receipt** — after `ExecutionPlan.from_dict` (`modal_app.py:15828`), ≈20–40 ms after method entry.

Dependency proof:
- **Identity/name/dtype**: `derive_model_key(workflow)` is a pure dict scan (`restore_plan.py:226–244`); the request seed derivation already scans the workflow at this point (`modal_app.py:15981`), proving usability. `build_restore_model_spec` extracts `unet_name` + `weight_dtype` (`restore_plan.py:292–298`).
- **Snapshot-unet-absent decision**: depends only on container state (`_cpu_snapshot_models.unet is None`), which exists before the request; the binding block currently re-derives it at `modal_app.py:11407–11412`.
- **Bridge state**: `schedule_execution_unet` needs `_preparation` + `_model_key` (`model_preload.py:10100–10128`); both are settable from the plan alone — `V2LoaderBridge.prepare()` already publishes exactly this from a `RestorePlan` at restore time (`model_preload.py:8984–8996`), and `_init_ready_preparation` (`10248–10308`) is the pattern for publishing a preparation directly.
- **Full path resolution** is *not* needed to start reading — the loader resolves the path inside `_load_unet` on the worker (original `UNETLoader` machinery); the name suffices to open the file.

What blocks it today: the asyncio-thread serial block between plan receipt and `modal_app.py:11416` (legacy runtime load, graph_execution_start, the full binding block, prefill submit). Nothing in that block changes any input the read depends on. **Not** gated on restore completion (restore finishes pre-entry) and **not** gated on the executor.

**Earliest possible is plan receipt, not method entry**: identity requires the parsed plan (~10–30 ms parse cost); parsing the raw payload again at method entry duplicates logic for negligible gain.

---

## 6. Earliest safe construction start

Immediately after the read, in the worker — **unchanged by any candidate**.

Dependency proof: `get_model` needs the checkpoint's state-dict metadata; ComfyUI's original loader runs read→config→get_model inside `_load_unet` on the worker (`model_preload.py:10636–10689`). Nothing from the graph/executor/snapshot-binding side is needed. Construction's only gate is the read start → **moving the read earlier moves construction earlier with zero additional dependencies**.

---

## 7. Earliest safe H2D start

**Already at its earliest safe point.**

- The single real H2D (`_fast_disk_replay_to`, `model_preload.py:4008/4407`) is invoked by the bind wrapper **in the worker** immediately after `load_model_weights(assign=True)` (bind at 4383 → replay at 4407) — not inside `load_models_gpu` at graph demand. The graph's later `load_models_gpu` is a cache-validation no-op (one construction/H2D invariant, `model_preload.py:10080–10086`).
- Gates: fast-disk guard set (high-VRAM, plain ModelPatcher, load/offload/target device equality, no quant/fp8/channels-last) and the bind-time guards — none depend on graph demand or the sampler.
- H2D→bind gap (get_model+bind tail, ≈60–120 ms) is inherent: weights must be assigned before transfer.
- "Launch H2D before first explicit sampler consumer" — already true; the consumer joins a completed future on healthy runs.

The only lever on H2D timing is again the **read start** (Section 5).

---

## 8. Unnecessary serial dependencies

| Edge | Today | Nature | Exposed on healthy run |
|---|---|---|---|
| **S1: plan receipt → read start** | Lane submitted after legacy-runtime load + graph start + binding block + prefill submit (`modal_app.py:11416`) | **AVOIDABLE** — none of the skipped work feeds the read's inputs | **≈90–110 ms** (runs 2/6/8/9: 84.5–198 ms setup; read starts at the end of it); ≈600 ms on run-7-class hosts; ≈220 ms on run-4-class hosts |
| S2: sampler wrapper (lane acquire → actual stage) | 103–137 ms after UNET ready; identity verify + residency proof + lane acquire | Partially avoidable — on cache-miss requests the FIFO wait behind prefill's CLIP load is included; on exact hits ≈0 lane contention | ≈0 on hits; up to ~125 ms on misses |
| S3: PromptExecutor/cache setup before first node | 8–17 ms | Minor; nodes could theoretically start earlier | ≈10–15 ms |
| S4: read-end→get_model (0.1–0.5 ms), H2D-end→ready (1.6–1.9 ms) | Worker chain | Inherent (attribution boundaries) | ≈2 ms |
| S5: method entry → plan parse | 10–30 ms deserialize | Inherent (identity lives in the plan) | ≈10–30 ms |
| S6: restore → method | 15–270 ms | Inherent — restore has **no plan** on the no-publish path (V1 lesson: never add request-identity work to restore) | — |

**Biggest avoidable serial edge: S1** — the read-start placement. It is the only edge that is purely reschedulable; everything else is either inherent or already overlapped.

---

## 9. Candidate designs

| # | Candidate | Feasibility | Gain | Verdict |
|---|---|---|---|---|
| D1 | **Begin UNET active-read at plan receipt** (before binding block / graph setup / prefill submit) | HIGH — identity, dtype, snapshot-unet-absent all plan/container-derivable (Section 5); single-flight guard prevents duplicates (`10110–10116`); `prepare()`/`_init_ready_preparation` show the publication pattern | ≈70–110 ms healthy; ≈600 ms run-7-class; ≈220 ms run-4-class | **RECOMMENDED** |
| D2 | Begin read at method entry (raw payload, before plan parse) | LOW-MEDIUM — duplicates parsing logic for ≈10–30 ms | ≈10–30 ms | Subsumed by D1 |
| D3 | Pre-resolve expected UNET via workflow-hash→model-key store | LOW VALUE — `derive_model_key` is a free single-pass dict scan; no persistent mapping exists or is needed | ≈0 | Skip |
| D4 | Construct module while graph setup runs | **Already true** — worker runs read→construct→bind→H2D concurrently with graph setup/nodes; construction cannot precede the read in the same worker | — | No change; D1 is the lever |
| D5 | Bind as soon as read completes | **Already true** — bind runs in the worker at `_fast_disk_handle_bind` (`4322`), not at graph demand | — | Already implemented |
| D6 | Launch H2D via early-activation path | INAPPLICABLE — early activation requires a retained CPU-resident snapshot UNET (eligibility gates 12344–12367); fast-disk path excluded by design. H2D already fires at its earliest point in the worker | — | Do not reuse; would require loosening the retained-identity correctness gate |
| D7 | Side-stream H2D / MutationLane priority | LOW — fast-disk H2D already runs outside the lane; lane FIFO only adds ~125 ms on misses; no concurrent GPU work exists on exact hits for a stream to overlap | ≈0 hits / ≤125 ms misses | Low value; revisit only with miss-heavy traffic |
| D8 | Separate readiness future from node execution | **Already the design** — `unet_future` is separate; `ready` fires on the worker; graph joins via `wait_unet`; readiness-slack metric exists (11263–11292) | — | Already implemented |
| D9 | Page preload (madvise WILLNEED) before construction | INAPPLICABLE to fast-disk — the read **is** the page-in; WILLNEED applies to already-mapped snapshot memory (flag `COMFYMODAL_V2_PAGE_READINESS_MODE=willneed`, off by default) | — | Orthogonal; leave gated |
| D10 | Chunked read→bind→H2D pipelining (transfer early layers while later tensors still read) | Would require streaming tensor-by-tensor transfer — a **new memory-copy mechanism**, out of scope per constraints; high risk (partial-module states, guard interactions) | theoretical | Out of scope / stop-condition territory |

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Identity divergence: plan-receipt derivation differs from binding-block derivation | Medium | Single source of truth — reuse `derive_model_key`/`build_restore_model_spec` in both; sampler identity verify (`verify_retained_unet_identity`) remains the runtime check |
| Wasted read if snapshot binding later decides UNET is retained | Low | Gate on the same `_snapshot_unet_absent` condition; in the current deployment shape the decision is container-deterministic and known at plan receipt; single-flight guard prevents double read in any case |
| Worker failure before binding block publishes | Low | Existing error semantics preserved: `_consume_model_impl` surfaces `_LOADER_MISS` at graph demand exactly as today |
| Disk/bandwidth contention from earlier read (slow-provider class, run 4) | Low | On exact hits nothing else reads at plan-receipt time; on misses the prefill encode already overlaps today — contention profile unchanged, just shifted earlier |
| GPU memory | None | Read is file→page-cache/CPU only; no GPU allocation until H2D, which is unchanged |
| CPU memory | None | Same single state-dict lifetime; no snapshot duplication introduced |
| Restore-time work creep (V1 regression class) | Medium | Hard rule: nothing before plan receipt, nothing in `restore()`/`startup(snap=True)` (SIGSEGV + 3.7–12.1 s restore regression history) |

---

## 11. Expected savings

Exposed gap between earliest-safe start (plan receipt, ≈20–40 ms) and current start (≈100–130 ms healthy; ≈650 ms run-7-class; ≈250 ms run-4-class):

| Scenario | Recoverable | Bucket |
|---|---:|---|
| Healthy exact hit (runs 2/6/8/9) | ≈70–110 ms | **<200 ms** |
| Slow first request / slow host (run 7, AWS) | ≈600 ms | **500–1000 ms** |
| Bad-host bandwidth (run 4) | ≈220 ms | **200–500 ms** |

TOTAL WALL impact: ≈0.5–0.7% on a healthy 15.5 s request; up to ≈4% on run-7-class hosts; ≈0.8% on run-4-class hosts. Sampling (4.8 s) unaffected.

**Ceiling note:** the ≈2.5–2.9 s exposed UNET pipeline on exact hits is structural — only ≈0.66–0.92 s of concurrent main-thread work exists to hide it, and exact hits deliberately skip CLIP encode (the one work item that could overlap the H2D). Scheduling cannot close that gap; only concurrent GPU work or faster transfer could, both out of scope.

---

## 12. Run 4 implications

Run 4 (H2D 9.229 s @ 1.3 GB/s, pre-sampler 10.681 s) is a **host-bandwidth problem, not a scheduling problem**:

- Read (1.336 s), get_model (48 ms), bind (21 ms), sampler gap (137 ms), sampling (4.816 s) are all within normal range; only the H2D collapsed (1.3 vs 5–6 GB/s).
- Earlier read start would still recover ≈220 ms (the setup-phase delta) **with no contention risk**: at plan receipt on an exact hit, nothing else is reading or transferring. It does not create more contention on a bad host; it simply moves the same I/O earlier.
- The 9.2 s H2D itself is untouched by any scheduling change — do not expect D1 to rescue run-4-class hosts beyond the ≈220 ms.

---

## 13. Recommended implementation design

**D1: plan-receipt UNET lane scheduling** (no new threads, no GPU changes, no new copy paths, no new timers).

1. **Identity derivation** — at plan receipt (`modal_app.py`, immediately after `ExecutionPlan.from_dict`), derive the model key using the exact same `derive_model_key`/`build_restore_model_spec` path the binding block uses (single source of truth).
2. **Gate** — compute the snapshot-unet-absent decision from container state (`_cpu_snapshot_models.unet is None`), same predicate as `modal_app.py:11407–11412`. If false, skip (preserves retained-UNET and legacy configurations untouched).
3. **Publish bridge state** — if the bridge lacks `_preparation`/`_model_key`, publish a minimal preparation from the plan (reuse the `_init_ready_preparation` pattern, `model_preload.py:10248–10308`); the CLIP decision is deferred (prefill scheduling is unchanged).
4. **Submit lane** — call the existing single-flight `coordinator.schedule_execution_unet` path (through a thin new bridge entry, e.g. `schedule_execution_unet_from_plan(plan, trace)`); the worker runs the existing `_execution_unet` → `_load_unet` unchanged.
5. **Reconcile, don't change** — `_run_in_process` keeps its existing `schedule_execution_prefill`/`schedule_execution_unet` calls verbatim; they become idempotent no-ops (`prep.unet_future is not None`). The binding block still runs; the graph join (`wait_unet`), identity verification, and `_LOADER_MISS` error semantics are untouched.
6. **Observability** — rely on the existing `[v2.execution_unet]` marker and lane trace events; no new timers.

Expected wall effect: −≈100 ms healthy / −≈600 ms slow-host first request, at essentially zero behavioral risk.

---

## 14. Stop conditions

Abort or roll back the plan-receipt scheduling if any of the following appear:

1. **Identity divergence** — any run where the sampler identity verification (`verify_retained_unet_identity`) fails, or where the plan-receipt-derived key differs from the binding-block-derived key (enforce one derivation path; if that is not achievable, stop).
2. **Restore/startup work creep** — any need to move identity work before plan receipt, into `restore()`, or into `startup(snap=True)` (V1 regression class: 3.7–12.1 s restore regression, loader-seeding SIGSEGV). The plan-receipt boundary is the hard floor.
3. **Gate weakening** — if any configuration must schedule the read before the snapshot-unet-absent decision is definitive (retained-UNET ambiguity), stop: the gate is the safety.
4. **Provider-bandwidth regression** — A/B on a run-4-class host showing the earlier read degrading read or H2D throughput (contention shift) beyond the recovered setup time.
5. **Error-semantics drift** — any change to how a failed early lane surfaces at graph demand (must remain `_LOADER_MISS`/existing fallback exactly as today).
6. **Theoretical-only complexity** — if D10-style chunked pipelining is ever proposed to close the H2D exposure: it is a new copy mechanism, explicitly out of scope; treat its proposal as a stop signal for the scheduling line and a new decision point.

---

## Appendix: measured run reference (from V2_10_COLD_RUNS_35S_COOLDOWN.md)

- Healthy reference runs: 2 (GCP/us-east4, TOTAL 15.708 s), 6 (GCP/us-east1, 16.426 s), 8 (GCP/us-east4, 15.146 s), 9 (GCP/us-east4, 16.408 s).
- Problem runs: 4 (GCP/us-east4, 26.471 s — H2D 9.229 s @ 1.3 GB/s), 7 (AWS/eu-south-2, 15.456 s — method setup 633.6 ms).
- Sampling is stable at 4.76–4.88 s across all runs; H2D healthy 2.0–2.45 s @ 5–6 GB/s; checkpoint read 1.06–1.71 s.
- All runs: cold (Fresh: YES), exact conditioning-cache hit (CLIP encode skipped), UNET excluded from CPU snapshot.
