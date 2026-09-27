# V2 Generic Pre-Sampler First-Node Delay Research

Date: 2026-08-13 (initial) / 2026-08-13 (follow-up revision: causality tightened, verdict regraded)
Scope: READ-ONLY timing investigation. No source modified, nothing deployed, no generation requests issued, no branches created.
Baseline: `V2_10_COLD_RUNS_35S_COOLDOWN.md` (10 cold runs, 35 s cooldown, deployment `b557b2401f293223`).
Artifacts: `ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-13_23-06-56\run_0..run_9.json` (all timestamps below are `monotonic_ns` extracted from `result.trace.events`; ms values are relative to `prompt_executor_invoke_start` unless stated).
Prior art: `V2_UNET_READ_H2D_OVERLAP_RESEARCH.md` (read-start placement, lane overlap), `V2_WATERFALL_FINAL_CORRECTNESS_REPORT.md` (accounting model).

---

## 1. Executive verdict

**The recurring ~0.55–0.70 s "Node: ImpactSwitch" row is wall-clock time whose wall interval lies entirely inside the concurrent UNET checkpoint-read window, and whose node-owned work is microseconds. The most defensible description of the cause is: same-process resource contention during the UNET read. The specific mechanism (GIL starvation vs CPU scheduling starvation vs page-cache/memory-pressure contention) is NOT directly measured and remains unproven.**

Regraded causal statements (see §2, §8, §9, §14):

- **PROVEN:** (a) the long ImpactSwitch/PENDING wall interval overlaps the UNET read window (bounded, §5–§7, §11); (b) the row duration covaries strongly with checkpoint-read duration across all 10 runs (0.42–0.64×); (c) the node's own implementation is O(1) (µs); (d) no explicit MutationLane wait or UNET-future join exists in that node's path (non-sampler, non-loader); (e) the UNET lane (read→get_model→bind→H2D) is the binding pre-sampler critical path.
- **STRONGLY SUPPORTED:** generic same-process resource contention associated with the concurrent UNET read is the cause of the long wall interval.
- **UNPROVEN:** the exact subtype — GIL starvation, CPU scheduling starvation, or page-cache/memory-pressure contention — and the split among them. No thread-CPU sampling exists for these runs; do not claim a specific mechanism.

**Practical conclusion (unchanged and still sound):**

- Do **not** optimize ImpactSwitch specifically. The node costs µs; hardcoding a third-party-node optimization would be wrong on the merits.
- The ~600 ms row is **not** a ~600 ms critical-path opportunity (§11: making it 0 ms moves sampling start ≈ 0 ms).
- G1 (plan-receipt UNET lane scheduling, prior report D1) remains the only demonstrated wall-time win in this area.

---

## 2. Exact timer semantics

**Start:** `comfymodal_runtime/runtime_executor.py:2575` — `_t0 = time.perf_counter_ns()` inside `_patched_exec_node`, immediately before delegating to ComfyUI's per-node `execution.execute`.

**Stop:** `runtime_executor.py:2597` — `_elapsed = _ns_ms(_t0)` in the `finally` around `await _orig_exec_node(...)` (`:2593`). A hard cutoff clips the sampler node's window at `sampling_start` (`:2601-2616`).

**Record:** `runtime_executor.py:2624-2628` appends `{node_id, class_type, duration_ms}` to `state["_pre_sampler_node_timings"]`. **Records carry no start/end timestamps — only `duration_ms`** (relevant to §11).

**Display:** `v2_waterfall.py:1440-1457` renders `Node: <class>` detail rows from `pre_sampler_structured_report.per_node_timings`, filtered to `duration_ms >= 25.0` or strategic class (`:1435-1439`), with `start_ns=None, end_ns=None` (`:1444-1445`). Node rows therefore have **no timeline position** — overlap cannot be read from the table; it must be bounded from trace events (§5–§7, §11).

**What the window contains (inside the timer):** the entire ComfyUI `execute()` call:

| Step | Location | Cost | V2 wrapper |
|---|---|---|---|
| `caches.outputs.get(unique_id)` | execution.py:437 | µs, in-process dict (caching.py:150-235; no providers registered) | timing-only (runtime_executor.py:3003-3052) |
| `get_input_data(...)` | execution.py:484 | µs for lazy/switch nodes (marks missing, execution.py:170-179; link cache lookups graph.py:216-224) | `_patched_get_input_data` runtime_executor.py:2507-2521 → `input_resolution_ms` |
| `send_sync("executing")` | execution.py:487 | put_nowait on in-process queue (comfyapp.py:18190-18228); milestone bookkeeping | `_send_sync_wrapper` modal_app.py:12856-13024 — sampler-only branches (UNET join 12959, lane acquire 12989) **skip non-sampler nodes** |
| `caches.objects.get(unique_id)` | execution.py:489 | node object construction (GeneralSwitch init trivial) | — |
| `check_lazy_status` (lazy nodes) | execution.py:498-511 | PENDING + strong link for missing inputs | — |
| `get_output_data` → `_async_map_node_over_list` → `f(**inputs)` | execution.py:536/336/298 | the node FUNCTION (µs for ImpactSwitch) | — |
| `resolve_map_node_over_list_results` | execution.py:223-233 | awaits spawned tasks → `future_wait_ms` | runtime_executor.py:3487-3511 |

**Outside the timer:** staging/topo (`stage_node_execution`, graph.py:236-267), PENDING restaging loop (execution.py:779-780), `before_node_execution` hooks (none registered in this stack), cache-gather, `cached_to_first_node_ms`.

---

## 3. Generic ComfyUI call path (first node → FUNCTION) — two distinct passes

```
PromptExecutor.execute_async (ComfyUI\execution.py:716)
  → DynamicPrompt → set_prompt → cache gather (716-767)
  → await execution_list.stage_node_execution()          (768; graph.py:236-267, first node picked)
  → await execute(server, dynprompt, caches, node_id, ...) (774)      ◄ _t0 here (timer starts)
       ├─ await caches.outputs.get(unique_id)            (437)
       ├─ get_input_data(...)                            (484)
       ├─ server.send_sync("executing", ...)             (487)
       ├─ await caches.objects.get(unique_id)            (489)  — node object construction
       ├─ check_lazy_status (lazy inputs)                (498-511)
       └─ ... either PENDING (below) or get_output_data → FUNCTION (536/336/298)
  → finally: _elapsed (timer stops, runtime_executor.py:2597)
```

Lazy nodes (ImpactSwitch: every `inputN` slot is `lazy: True`, util_nodes.py:38-48) execute **twice**, and the two passes are **not the same code path**:

**Pass 1 — PENDING discovery path** (never reaches the node FUNCTION):
1. `caches.outputs.get` (437) — cache miss lookup, O(1) dict.
2. `get_input_data` (484 → 155-219) — iterates ~5 inputs; for linked inputs calls `execution_list.get_cache` (graph.py:216-224, dict lookups) and `mark_missing()` for the not-yet-executed upstream (execution.py:170-179). It does **not** resolve the missing input.
3. `send_sync("executing")` (487) — in-process queue put + milestone bookkeeping.
4. `caches.objects.get` (489) — constructs the node object (GeneralSwitch; trivial `__init__`).
5. `check_lazy_status` (498-503) — mapped via `_async_map_node_over_list` (one asyncio task per slice, execution.py:288-290) and `resolve_map_node_over_list_results` (223-233, `asyncio.wait`). ImpactSwitch's own `check_lazy_status` (util_nodes.py:50-59) is `int()` + string concat + dict membership — O(1).
6. Required-inputs non-empty → `make_input_strong_link(unique_id, i)` per missing input (execution.py:508-511; graph.py:120-128 — a dict/set insertion) → `return (PENDING, None, None)`.
7. (outside the timer) execute_async loop: `unstage_node_execution()` + re-pick (execution.py:779-780); the upstream node then executes in its own timer window; the lazy node is re-staged.

**PENDING-specific operation audit (can any of these plausibly take hundreds of ms?):**

| Operation | Where | Complexity |
|---|---|---|
| graph mutation / strong-link insertion | graph.py:120-128 | O(1) — set/dict insert |
| dependency traversal / staging | execution.py:779-780, graph.py:236-267 | O(pending) bookkeeping; single re-pick |
| cache/object access | caching.py:150-235, execution.py:437/489 | O(1) dict; no serialization; no providers |
| dynamic prompt operations | `check_lazy_status` util_nodes.py:50-59; dynprompt.get_node | O(1) |
| async task creation | execution.py:288-290 (one `create_task`) | O(1) |
| restaging | execution.py:779-780 | O(1) |
| hidden synchronization | — | none (no locks, futures, events in this path) |

**Every PENDING-specific operation is O(1)/tiny. The PENDING path's own work is sub-millisecond and cannot itself produce a 624 ms duration.** The long wall interval must therefore be environmental (waiting/starvation), not path work.

**Pass 2 — resolved-input path** (reaches the node FUNCTION):
1. `caches.outputs.get` (437) — now a hit-or-compute signature on resolved inputs.
2. `get_input_data` (484) — input now cached upstream; resolved from the execution cache (O(1)).
3. `send_sync` (487); 4. `objects.get` (489) — already constructed.
5. `check_lazy_status` (498-511) — returns `[]` (input available) → proceeds.
6. `get_output_data` (536) → `_async_map_node_over_list` (336) → `nodes.before_node_execution()` (251) → `f(**inputs)` (298) → `doit` (util_nodes.py:61-87: `int()`, concat, dict lookup, linear scan of ~60 workflow nodes for the label — tens of µs).
7. `resolve_map_node_over_list_results` (223-233); output cache write.

**Do not interpret the two passes as "same code path".** They share the generic machinery (cache get, get_input_data, send_sync, objects.get) but diverge: pass 1 terminates at the PENDING decision; pass 2 executes the FUNCTION. The measured delta (624.564 ms vs 22.981 ms in run_0) cannot be explained by the path difference — both passes' own work is µs-scale — so the delta is environmental. Pass 2's 22.981 ms is *not* an exact "uncontended baseline of the same work" (it is a different, slightly larger set of operations incl. the FUNCTION), but it is the closest available measure of this node's real cost and it ran with the lane complete.

---

## 4. V2 wrapper path (what runs around the same window)

- **UNET lane scheduling:** `schedule_execution_unet` (modal_app.py:11416, gated on snapshot-unet-absent) submits the fast-disk loader to the coordinator pool (`model_preload.py:8501-8532`, `_submit("unet", ...)`; worker thread `thread_native_id=81` in artifacts). It runs **before** `_execute_v2_prompt_executor` (modal_app.py:11449). In run_0 the lane was scheduled 177.9 ms *before* `prompt_executor_invoke_start` and `read_start` fired 29.4 ms before invoke — the read is already running when the first node executes.
- **Lane worker chain (thread 81, concurrent with node execution):** checkpoint `read_start/read_end` (load_torch_file wrapper, model_preload.py:2074-2117) → construction (`get_model`) → bind (`unet_fast_disk_bind_start/end`, model_preload.py:4322-4401) → H2D (`unet_fast_disk_to_start/end`, model_preload.py:4008-4270) → `unet_fast_disk_complete` (4412).
- **Graph-side joins:** `wait_unet` → `future.result()` at loader demand (`model_preload.py:8819`); exclusive-owner join `graph_unet_join_or_adopt` (`12143`, env-gated, default off); sampler-boundary join at first-sampler `send_sync` (modal_app.py:12959, `unet_graph_join` event) + mutation-lane acquire `_lane.acquire("sampler")` (modal_app.py:12989, `sampler_lane_wait_start/end`).
- **None of these fire for ImpactSwitch.** The non-sampler `_send_sync_wrapper` path is milestone bookkeeping + `put_nowait` (modal_app.py:12859-12936, 13021; comfyapp.py:18226-18228). ImpactSwitch's `execute()` contains **no join, no lane acquire, no future wait** — its window is Python executing on the graph thread (thread 2) while the lane worker (thread 81) reads/allocates 12.3 GB of parameters in the same process.
- `execution_warm.py` daemons warm `INPUT_TYPES`/folders ahead of the graph (modal_app.py:9258-9289, 15912-15923); fire-and-forget, not joined inside the node timer.

---

## 5. Healthy-run timeline (run_0 = md Run 1, GCP/us-east4, IS pass 1 = 624.564 ms)

Anchor: `prompt_executor_invoke_start` mono `2579536299505`. All values ms relative to anchor.

```
-177.9  unet_execution_schedule (t2)        lane submitted before executor invoke (modal_app.py:11416)
-176.4  unet_loader_start (t81)             fast-disk loader begins on pool worker
 -29.4  read_start (t81)                    UNET checkpoint read begins
   0.0  prompt_executor_invoke_start (t2)
  +9.8  first_executing_node (t2)           Any Switch (rgthree), 0.325 ms — 39.2 ms into the read
 +15.2  first clip-encode-class node (t2)   CLIPLoader
 [+90]  node-chain cumulative ~89.6 ms      (All Switch..SimpleMath+ windows, dominated by CLIPTextEncode 81.4 ms)
[≥+109] ImpactSwitch pass 1 (t2) 624.564 ms ◄ bounds: start ≥ +109.2, end ≤ +733.8 (§11)
 +733.8 graph_unet_wait_start (t2)          UNETLoader node begins executing → joins lane future
+1460.3 read_end (t81)                      read = 1.490 s (event span; md row 1.477 s via active_read_records)
+1529.1 bind_start (t81)                    25.5 ms bind
+1555.1 H2D to_start (t81)                  2.454 s synchronized H2D
+4009.5 H2D to_end (t81)
+4011.3 unet_fast_disk_complete (t81)       lane ready (H2D end → ready 1.8 ms)
+4014.1 graph_unet_wait_end (t2)            loader join completes (2.8 ms after lane ready)
+4063.3 sampler_lane_wait_start (t2)        ClownsharKSampler begins; lane wait 0.06 ms
+4188.7 sampling_start (t2)                 sampler node window 132.655 ms (clipped at start)
```

Read duration: 1460.3 − (−29.4) = **1489.7 ms**; H2D: 4009.5 − 1555.1 = **2454.4 ms** (md: 2.454 s ✓).

- ImpactSwitch pass 1 bounds: **[≥+109.2, ≤+733.8]** — fully contained in the read window **[−29.4, +1460.3]** with ≥138.6 ms margin on the start side and ≥726.5 ms on the end side (§11). **Containment: BOUNDED/PROVEN.**
- ImpactSwitch pass 2: 22.981 ms, after EmptyImage/ImageRotate, i.e. after `unet_fast_disk_complete` (+4011.3) — lane finished. Note: pass 2 is a different code path (doit), not an identical-work baseline (§3).
- Pre-sampler window (4.053 s) ≈ lane chain read 1.490 s + get_model 60 ms + bind 25 ms + H2D 2.454 s (+ sampler overhead) — **lane-bound, not node-bound.**

## 6. Run 4 timeline (run_3 = md Run 4, GCP/us-east4, IS pass 1 = 736.999 ms)

Anchor: `prompt_executor_invoke_start` mono `2778287518036`.

```
 -29.5  read_start (t81)
   0.0  prompt_executor_invoke_start
 +14.8  first_executing_node (t2)
[≥+105] ImpactSwitch pass 1 736.999 ms      ◄ bounds: start ≥ +105.5, end ≤ +842.5 (§11)
 +842.5 graph_unet_wait_start (t2)          UNETLoader node joins lane future
+1311.8 read_end (t81)                      read = 1.341 s (event span; md row 1.336 s)
+1389.7 H2D to_start (t81)                  9.229 s H2D @ 1.3 GB/s (bad-host bandwidth)
+10620.2 complete (t81)                     lane ready; pre-sampler total 10.681 s
+10695.8 sampler_lane_wait_start (t2)       sampler → sampling 137.1 ms
```

- IS pass 1 bounds **[≥+105.5, ≤+842.5]** ⊂ read window **[−29.5, +1311.8]**; margins ≥135.0 ms / ≥469.3 ms. **Containment: BOUNDED/PROVEN.**
- The 9.2 s H2D is the run's dominant cost, begins *after* the IS window closed, and is untouched by any node scheduling. The elevated 737 ms (vs ~580 typical) tracks the slower read/contention on this host.

## 7. AWS Run 7 timeline (run_6 = md Run 7, AWS/eu-south-2, IS pass 1 = 1.091 s)

Anchor: `prompt_executor_invoke_start` mono `64336899626`.

```
-164.0  read_start (t81)                    read begins 164 ms before executor invoke
   0.0  prompt_executor_invoke_start
  +4.8  first_executing_node (t2)
[≥+237] ImpactSwitch pass 1 1.091 s         ◄ bounds: start ≥ +237.0, end ≤ +1328.0 (§11)
+1328.0 graph_unet_wait_start (t2)          UNETLoader node joins lane future
+1691.1 read_end (t81)                      read = 1.855 s (event span; md row 1.708 s via active_read_records)
+1797.4 H2D to_start (t81)                  3.275 s H2D @ 3.8 GB/s
+5074.6 complete (t81)                      lane ready; pre-sampler 5.127 s
+5132.4 sampler_lane_wait_start (t2)        sampler → sampling 130.5 ms
+5262.9 sampling_start (t2)
```

- IS pass 1 bounds **[≥+237.0, ≤+1328.0]** ⊂ read window **[−164.0, +1691.1]**; margins ≥401.0 ms / ≥363.1 ms. **Containment: BOUNDED/PROVEN** (robust even if the narrower active-read window of 1.708 s is used: end +1328.0 still leaves ≥380 ms margin before a 1.708 s window starting at −164.0).
- IS pass 1 (1.091 s) ≈ 0.64 × the 1.708 s checkpoint read — largest inflation of the batch on the slowest-read host (method-entry setup 633.6 ms, conditioning lookup 94.5 ms — everything slower on this host).

---

## 8. ImpactSwitch actual work vs attributed wait

| Question | Answer | Evidence |
|---|---|---|
| Does ImpactSwitch's FUNCTION consume 600 ms? | **No — µs.** | GeneralSwitch.doit is O(1) (util_nodes.py:61-87); lazy inputs shrink input fetch |
| Does the PENDING path consume 600 ms? | **No.** | §3 audit: every PENDING-specific op (link insert, restage, cache access, check_lazy_status, task creation, sync) is O(1)/µs-scale |
| Input preparation? | **No — µs.** | `_patched_get_input_data` measures `input_resolution_ms` ≈ small; lazy marking is a dict scan (execution.py:170-179) |
| Mutation-lane / resource wait? | **No.** | Non-sampler nodes never acquire `MutationLane` (acquires only at modal_app.py:12989 sampler branch and pool workers); sampler lane wait measures 0.06-0.09 ms |
| Model join (UNET readiness)? | **No.** | Joins (`future.result()`, model_preload.py:8819/12143) fire in loader/sampler nodes, not ImpactSwitch; no `unet_graph_join` event for it |
| before_node_execution hooks? | **No.** | No hooks registered in this stack |
| send_sync / telemetry? | **No.** | `_prog_q.put_nowait` (comfyapp.py:18228), milestone setdefaults; sampler branches skipped |
| Cache get / write? | **No.** | In-process dict, zero-copy (caching.py:150-235), no providers |
| **What it actually is** | **Wall time whose interval sits inside the UNET read window while the lane worker (thread 81) reads/allocates 12.3 GB in the same process. Cause description: same-process resource contention during the UNET read — STRONGLY SUPPORTED. Exact mechanism (GIL vs CPU scheduling vs page-cache/memory pressure): UNPROVEN.** | §5–§7 overlap bounds; §3 pass audit; 0.42–0.64× read correlation across all 10 runs; pass-2-vs-pass-1 23 ms vs 624 ms |

The first ImpactSwitch pass (PENDING discovery) runs while the pool worker is inside `load_torch_file`/construction of the 6.9 GB checkpoint (bfloat16, 453 tensors, 12.3 GB parameter bytes) on the same 12-vCPU process. The graph thread's µs-scale Python executes inside that contended window. The same node's pass 2, executed with the lane complete, measures ~23 ms. The exact starvation mechanism is not distinguished by any existing measurement (no thread-CPU sampling in these artifacts) and is deliberately not claimed.

---

## 9. Is the issue generic? — two separate claims

**GENERICITY OF THE RESOURCE CONTENTION: HIGH.** The contended resource (the fast-disk UNET lane: read→construct→bind→H2D in-process) is workflow-independent in this deployment shape (snapshot-unet-absent, exact-hit). Any node whose execution window falls inside the lane's active phase would experience the same environmental pressure. This is a property of the runtime, not of any node class.

**GENERICITY OF THE EXACT NODE-TIMER MANIFESTATION: NOT YET EMPIRICALLY PROVEN.** The 10-run batch used one workflow, and the large inflated row is only ever observed on ImpactSwitch's pass 1. The counter-evidence is instructive:

- The benchmark's actual first executing node is **Any Switch (rgthree), 0.325 ms** (`first_executing_node_monotonic_ns` = +9.8 ms, i.e. **39.2 ms after `read_start`**), yet it took only 0.325 ms. At that moment the read had already begun, but the node's window was tiny and very early in the read — before the loader had entered the bulk of its CPU/allocator-heavy phase.
- The next >25 ms node record in run_0 is CLIPTextEncode at 81.4 ms (also within the read window; its composition is not separately measured, so it is only *consistent with* contention, not proof).
- ImpactSwitch pass 1 is the **first graph-thread window that extends deep into the read's active phase** (~130+ ms into the read, after ~90 ms of node-chain work) and the **only one that spans hundreds of milliseconds**. It is a lazy PENDING pass — pure discovery, no productive computation — so the entire contended window is exposed as row time.

So the accurate statement is:

> **The contention is generic (environmental). Whether a given node class displays the inflated row depends on when its execution window falls relative to the lane's CPU-heavy phase — in this workflow, ImpactSwitch's PENDING pass is the first node whose window sits in that phase. That a different cheap node class would show the same inflation is plausible but NOT empirically proven by these 10 runs.**

ImpactSwitch's specific properties (lazy inputs, O(1) FUNCTION, PENDING double-execution) do not make it a culprit — they merely determine *which* window is exposed. No ImpactSwitch-specific optimization is warranted.

---

## 10. Generic optimization candidates

Only options that shorten **TOTAL WALL** count; attribution-only changes are marked as such.

| # | Candidate | Expected saving (real wall) | Attribution or wall? | Workflows affected | Correctness risk | Location | Confidence |
|---|---|---|---|---|---|---|---|
| G1 | **Start UNET read at plan receipt** (D1 of prior report: schedule `schedule_execution_unet` from plan-derived identity, `modal_app.py` after plan parse ~15828; single-flight guard model_preload.py:10110-10116) | ≈70-110 ms healthy; ≈220 ms run-4-class; ≈600 ms run-7-class | **Wall** (read is the pre-sampler binding edge; earlier read → earlier lane completion) | All fast-disk (snapshot-unet-absent) workflows | Low-medium (identity-divergence guard; gate on same `_snapshot_unet_absent` predicate) | modal_app.py plan-receipt path | **High** (prior report; also *reduces* the contended window overlapping early nodes) |
| G2 | Reduce read-lane CPU/allocator footprint during its active phase (GIL release during tensor load, chunked/safetensors-native path, allocator-friendly reads) | Small; speculative — 0-50 ms | Wall (small) + shrinks node-row inflation | All | Medium-high (shared ComfyUI loader machinery) | model_preload.py fast-disk loader | Low-Medium — **do not start without §12 deep instrumentation** |
| G3 | **Add `start_perf_ns`/`end_perf_ns` (+ optional pass/outcome) to `per_node_timings` records** (runtime_executor.py:2624-2628); waterfall positions rows as non-accounting overlap rows | 0 (observability) | Attribution only | All | None | runtime_executor.py + v2_waterfall.py | High — **recommended; minimal scope in §12** |
| G4 | Attribute contended overlap separately (e.g., "node wall vs lane-overlapped" split in the report) | 0 | Attribution only | All | None | v2_waterfall.py | High (cosmetic; do not present as a saving) |
| G5-G7 | Overlap resource hydration with prior nodes / avoid redundant model-state sync / await activation before first consumer | Already implemented or ≈0 | Wall | — | — | — | No action |

**The one real lever is G1.** G2 is speculative and must wait for §12 deep instrumentation. G3/G4 are observability.

---

## 11. Overlap proof (Issue 4) and critical-path counterfactual (Issue 5)

### 11.1 Overlap derivation — BOUNDED/PROVEN, not EXACT

Per-node records carry only `duration_ms` (runtime_executor.py:2624-2628); **exact node-enter/exit timestamps do not exist**. The interval is therefore *bounded*, not measured:

- **Upper bound on pass-1 end:** pass 1 is the 16th per-node record (execution order from append-per-execution), immediately before the UNETLoader record. The UNETLoader node's graph-side execution begins at or before `graph_unet_wait_start` (the loader's demand/wait fires inside the loader's own execution, model_preload.py:11261-11304). Hence **pass 1 end ≤ `graph_unet_wait_start`** (conservative; the real end is earlier by the loader node's pre-wait overhead).
- **Lower bound on pass-1 start:** start ≥ (graph_unet_wait_start − duration).
- **Read window:** [`read_start`, `read_end`] (event pair, thread 81).

| Run | Pass 1 duration | graph_unet_wait_start (rel. invoke) | ⇒ pass 1 interval | Read window | Start margin | End margin | Containment |
|---|---|---|---|---|---|---|---|
| run_0 (md R1) | 624.564 ms | +733.8 ms | [≥ +109.2, ≤ +733.8] | [−29.4, +1460.3] | ≥138.6 ms | ≥726.5 ms | **BOUNDED/PROVEN** |
| run_3 (md R4) | 736.999 ms | +842.5 ms | [≥ +105.5, ≤ +842.5] | [−29.5, +1311.8] | ≥135.0 ms | ≥469.3 ms | **BOUNDED/PROVEN** |
| run_6 (md R7) | 1.091 s | +1328.0 ms | [≥ +237.0, ≤ +1328.0] | [−164.0, +1691.1] | ≥401.0 ms | ≥363.1 ms | **BOUNDED/PROVEN** |

The exact position of the node window inside the read window is **APPROXIMATE** (start not timestamped), but its containment is **BOUNDED/PROVEN** with large margins on both sides in all three runs. The conclusion does not depend on the unmeasured start.

### 11.2 Critical path — the ~600 ms is not removable wall time

Binding chain (run_0, healthy, invoke-relative):

```
read_start −29.4 → read_end +1460.3 (1.490 s)
  → get_model (60.2 ms) → bind +1529.1→+1554.5 (25.5 ms)
  → H2D +1555.1→+4009.5 (2.454 s) → ready (complete) +4011.3
  → graph_unet_wait_end +4014.1 (graph released 2.8 ms after lane ready)
  → sampler_lane_wait_start +4063.3 → sampling_start +4188.7
```

The graph thread reached the loader demand at +733.8 and **waited on the UNET future until +4014.1** (3.28 s). The node chain (0.66–0.92 s total, fully inside that wait) is not the binding edge: the lane (≈3.98 s) is.

**Counterfactual:** if ImpactSwitch pass 1's 624.6 ms wall became 0 ms while the UNET lane is unchanged, the graph thread would reach the loader demand at ≈+109 instead of +733.8 — and then **wait on the lane future until +4011.3 regardless**. The lane completes at the same instant, the sampler node starts at the same instant, and sampling begins at the same instant.

> **Answer: sampling would begin ≈ 0 ms earlier. The node row is real wall time but fully overlapped with the lane, which is the binding constraint. This is the key reason not to optimize the node.**

---

## 12. Instrumentation still needed — minimal vs deep

**G3 minimal (recommended; small, safe, unlocks direct display):**

- Extend each `per_node_timings` record (runtime_executor.py:2624-2628) with:
  - `start_perf_ns`, `end_perf_ns` (perf_counter domain, already captured at 2575/2597)
  - `node_id`, `class_type`, `duration_ms` (existing)
  - `pass` / outcome **if cheaply derivable**: capture `_orig_exec_node`'s returned `ExecutionResult` in the wrapper (it is the awaited value at 2593) — record `"PENDING"` vs `"COMPLETE"` (lazy double-execution becomes visible). No new timers, no deep hooks.
- Waterfall: position node rows using start/end as **non-accounting overlap rows** (they already are `included_in_total=False`, v2_waterfall.py:1440-1457) with real `start_ns`/`end_ns`.
- Overhead: two perf-counter reads + a dict append per node — < 1 µs per node, < 0.001% of a 15 s run.

**Deep instrumentation (optional — only if we later decide to investigate the contention subtype):**

- Thread-CPU attribution during the read window (extend `comfymodal_runtime/thread_cpu_sampler.py`): per-thread CPU% for graph thread (2) vs lane worker (81) — the only way to separate GIL starvation from CPU scheduling starvation.
- Page-cache/memory-pressure probes (RSS, page faults, allocator stats) across the read — the only way to separate memory-pressure contention.
- `actual_node_function_start/end` around `f(**inputs)` (execution.py:298) — separates node-Python from generic machinery inside the window.

**Classification: G3 minimal timestamps = recommended (do it). Deep GIL/thread-CPU instrumentation = optional, only if the contention subtype becomes decision-relevant. Do not require deep instrumentation for G1.**

---

## 13. Recommended next implementation

1. **Do not implement any ImpactSwitch-specific optimization.** The node is µs; hardcoding third-party-node logic is wrong and would not move wall time.
2. **Implement G1 (plan-receipt UNET read start)** per `V2_UNET_READ_H2D_OVERLAP_RESEARCH.md` §13 — the only real critical-path reduction (≈70-110 ms healthy; up to ≈600 ms slow-host), reusing existing single-flight scheduling and the snapshot-unet-absent gate. Stop conditions from prior report §14 apply.
3. **Implement G3 minimal timestamps** (start/end perf ns + outcome) — zero-risk observability that turns §11's bounds into direct display.
4. Defer deep contention-subtype instrumentation (§12 deep) until/unless G2 or another lane needs it.

Completion criteria: pre-sampler window shrinks by G1's expected amount; node rows gain timestamps and visibly sit inside the read/H2D lanes; no change to ImpactSwitch or any custom-node code.

---

## 14. Final verdict (categorized)

```
ImpactSwitch-specific bottleneck                        = NO
~600 ms directly removable from total wall              = NO
Resource-contention association                         = STRONGLY SUPPORTED
  (same-process resource contention during the UNET read;
   overlap PROVEN, covariance PROVEN, mechanism subtype unproven)
Specific GIL cause                                      = UNPROVEN
  (GIL starvation vs CPU scheduling starvation vs page-cache/memory pressure
   is not distinguished by any existing measurement)
Exact manifestation generic across arbitrary node classes = UNPROVEN
  (resource contention itself generic: HIGH;
   whether another node class would show the same inflated row is plausible
   but not empirically demonstrated — only ImpactSwitch pass 1 is observed)
G1 plan-receipt scheduling remains valid                = YES
G3 timestamps worth implementing                        = YES
Further research needed before implementation decisions = NO
  (G1 and G3 can proceed; deep contention-subtype research is optional,
   not a blocker)
```

---

## Appendix: raw per-node records (run_0, selected, in execution order)

```
 987  Any Switch (rgthree)          0.325 ms   (first executing node, below display filter; 39.2 ms into the read)
  62  CLIPLoader                    1.709 ms
  67  CLIPTextEncode               81.360 ms   (within read window; composition not separately measured)
935:929 ImpactSwitch             624.564 ms   (pass 1 — PENDING discovery, bounds [≥+109, ≤+734] inside read)
  66  UNETLoader                 3289.168 ms   (graph-side join of lane: read+bind+H2D; wait 3.28 s)
935:926 EmptyImage               17.536 ms
935:928 ImageRotate                1.747 ms
935:929 ImpactSwitch              22.981 ms   (pass 2 — doit, AFTER lane complete → lane-finished context)
1242 ClownsharKSampler_Beta      132.655 ms   (clipped at sampling_start)
```

`UNETLoader`'s 3.29 s row is the graph-side join of the lane (read 1.49 s + get_model 60 ms + bind 25 ms + H2D 2.45 s) — a second, larger instance of node rows charging wall time that is really lane time; the UNET lane detail rows (Checkpoint read / Bind / Synchronized H2D) are already rendered as overlap details under `pre_sampler_execution` (v2_waterfall.py:1579-1717).
