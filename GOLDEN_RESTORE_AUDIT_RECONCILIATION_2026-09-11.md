# Golden Restore Audit — Reconciliation / Correction Pass

**Status:** READ-ONLY reconciliation. No edits, commits, deploys, or paid calls.
**Date:** 2026-09-11
**Worktree:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
**HEAD SHA:** `b81510606894bb4d03e8af7c243dd85b76f61f3b` (branch `TESTING2`)
**Corrected report path:** `GOLDEN_RESTORE_AUDIT_RECONCILIATION_2026-09-11.md`
**Supersedes:** `GOLDEN_RESTORE_ARCHAEOLOGY_MINIMAL_REBUILD_AUDIT_2026-09-11.md` where they conflict.

This pass begins from zero and re-derives the contract. The prior report is not authoritative. Oracle opinions are not treated as evidence; current code and raw timings are.

---

## A. Corrections to the previous report

| # | Previous claim | Verdict | Evidence | New conclusion |
|---|---|---|---|---|
| A1 | `restore_gpu_state_ms ≈ 599 ms` **is** the "~600 ms residual" | **REJECTED / corrected** | `restore_gpu_state` is invoked inside `bootstrap.restore()` (`runtime_bootstrap.py:2068-2088`), which is called at `modal_app.py:13204`. `bootstrap_restore_ms` is `[13191 … 13224]` (`modal_app.py:13191-13193,13224-13226,14679-14691`). `post_snapshot_restore` is `[12781 … 14823]`. So `restore_gpu_state ⊂ bootstrap ⊂ post_snapshot_restore`. The `restore_total − post_snapshot_restore` gap falls **before** line 12781 and cannot be `restore_gpu_state`. | There are **two different candidate ~600 ms intervals**: (a) the pre-marker interval `[12604,12781)`; (b) `restore_gpu_state` inside bootstrap. The prior report conflated them. |
| A2 | The pre-marker interval is ~600 ms | **UNRESOLVED** | The exact tuple `restore_total≈2053.55 / bootstrap_restore≈1419.961 / residual≈614.619 / post_snapshot_restore≈1451.381` is **absent** from the current tree (searched `*.md,*.log,*.txt,*.json`, excluding `.slim`). Closest current-tree `[v2.restore_deep]` runs show `residual_ms` of **23.586 / 29.072 / 71.198 ms** and `bootstrap_restore_ms` of **684.493 / 689.98 / 1645.568 ms**. | The interval structurally exists (pre-marker) but its magnitude is not substantiated by any current-tree artifact. `residual_ms` is a derived remainder (`restore_total − Σ named deep timers`), **not** an independently timed interval, and must not be added to the model. |
| A3 | Runtime-state / models / custom-node checks are "cheap O(1) generation compares" | **REJECTED** (2 of 3) | Models: one `models_generation.json` read + `isdir` (`runtime_bootstrap.py:1552-1597`; `comfyapp.py:1937-1962`) → genuinely O(1). Runtime-state: **on the MATCH path** `verify_runtime_state_manifest` SHA-256 hashes every present manifest file (`runtime_bootstrap.py:1748-1750`; `runtime_generation.py:228-239` → `_sha256_file` at `:87-92`) → O(files × bytes). Custom-node: O(1) metadata compare, but the normal uncached restore first calls `custom_nodes_vol.reload()` (`modal_app.py:10751-10758`, and `10480-10484` via `sync_custom_nodes`) → O(1) metadata **plus Volume RPC** on the hot path. | Only **models** is O(1). Runtime-state does file-hash verification on match. Custom-node does a Volume reload on the uncached match path. |
| A4 | Restore should keep a cheap custom-node generation mismatch gate | **REJECTED** | Request-time missing-node detection is workflow-specific: `comfyapp.py:15794-15800` checks only the workflow's `class_type` values against `nodes.NODE_CLASS_MAPPINGS`; missing classes fail explicitly at `comfyapp.py:15828-15877`. Extra published node D does not invalidate a workflow using A. | **No custom-node identity check belongs in normal restore.** Delete Volume.reload, generation compare, and mismatch gate. |
| A5 | Eager CUDA init (synchronize / device probes) is proven essential before request readiness | **CORRECTED** | `_initialize_cuda_context` (`comfyapp.py:18544-18625`) only probes `is_available`/`current_device`, calls `torch.cuda.synchronize` (`:18574`), and reads `get_device_name` (`:18593`) for telemetry; it does no GPU work whose completion readiness depends on. The pure logical repair (`args.cpu=False`, `cpu_state=GPU`, `vram_state=HIGH_VRAM`) lives in `_restore_in_process_gpu_state` (`comfyapp.py:20242-20246`). | **Split A/B:** logical GPU-state repair (A) is required before first request; forced eager CUDA init/synchronize (B) is **not proven** required and is deferrable to first GPU use. |
| A6 | Runtime-state reconciliation protects request correctness | **CORRECTED** | Only `prescan_custom_nodes.json` and optional `gpu_capacity_frozen.json` are manifest-relevant (`runtime_generation.py:57-83`). Both are restore-time evidence / optional preparation; request node/model resolution uses live registries/loaders (`comfyapp.py:15794-15800`, `18809-18849`). | Removing runtime-state reconciliation produces **no demonstrated Golden Parallel request-correctness failure** when mounted state matches. Under the manual-only custom-node policy, even the prescan rationale disappears. |
| A7 | Models reconciliation protects request correctness | **CONFIRMED** | A changed mounted models Volume can make a request load a wrong/missing model at `comfyapp.py:18809-18849`; the guard compares mounted `models_generation.json` to the snapshot baseline (`runtime_bootstrap.py:1508-1597`). | Keep the models guard; it is the one request-correctness-relevant identity check. |
| A8 | Sage must be verified synchronously in restore | **CORRECTED** | `runtime_bootstrap.py:2121-2263` splits into config selection (`2204-2214`; `sage_policy.py:44-86`), policy application (`2215-2225`), identity verify (`2132-2162`), fallback detection (`2175-2185`; `sage_policy.py:346-361`), telemetry. None is fundamentally required before the first request; only before the first Sage-dependent forward. | Sage config/identity can be captured at `snap=True` and asserted at first Sage use. Restore execution is determinism/fail-fast/telemetry, not correctness. |
| A9 | Move CPU-snapshot activation, CacheDiT/RES4LYF, preload, speculative CLIP, folder warm, clean-lane to "first use" | **REJECTED — delete instead** | CPU snapshot activation is gated `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT` default **False** (`config_authority.py:152`) and Golden explicitly clears it (`modal_app.py:11055-11070`); CacheDiT/RES4LYF prep (`runtime_bootstrap.py:898-1102`) is legacy; preload bridge / production UNET defer belong to other profiles (`config_authority.py:112-114,183`); speculative CLIP lane is historical; clean-lane is E37-only; folder warm was **rejected** for contention. | Delete from Golden Parallel, do not defer. See §D. |
| A10 | `modal_app.restore()` is ~1,290 lines; `RuntimeBootstrap.restore()` ~800 | **CORRECTED** | Next top-level method after `def restore` (`modal_app.py:12583`) is `async def _run_in_process` at `modal_app.py:14876`. | `modal_app.restore()` physical span = **12583–14875 = 2,293 lines** (the prior ~1,290 counted only to the `finally` tail). `RuntimeBootstrap.restore()` = **1984–2786 = 803 lines**. |
| A11 | E37 minimal restore proves Golden can use the same contract | **DOWNGRADED** | E37 (`comfyapp.py:20411-20537`) is backend/CUDA-only and explicitly skips custom-node sync, model-generation reads, models reload, prompt-cache hydration, preload, UNET defer, warming (`comfyapp.py:20423-20440`); it does not operate Golden's CPU-snapshot activation, snapshot-carried identity, execution seed, or model-free invariants. | E37 = **precedent / working pattern**, not proof. Its body is transferable only for a backend/CUDA-only profile. |
| A12 | Folder warming can be "started after ready" | **REJECTED** | `CAMPAIGN_REPORT_CLIP_FORWARD_CONTENTION.md:45-46,115`: concurrent 12.3 GB warm throttles CLIP forward (+2.25 s mean), "non-viable in this shape on 4 CPU / 16 GiB"; `DISCRIMINATORS_SYNTHESIS_REPORT.md:27-29`: 2 GiB cold reads under forward tax it +0.3–1.7 s. | Do **not** run folder warming in Golden Parallel at all (not even deferred). It is contention, not an optimization. |

---

## B. Correct current timing model

Explicit nesting, no double-counting:

```text
restore()                                      modal_app.py:12583 .. 14875   (2,293 lines)
│
├─ restore_total_ms  =  perf_counter(14489) − perf_counter(12604)      (success path)
│                       also recomputed in the finally path at 14845
│                       (emitted at 14753 / 14767 / 14845)
│
├── PRE-MARKER interval  [12604 .. 12781)          NOT measured by any named child
│      • _resolve_restore_clip_probe_source(...)    12605  — cheap by default (see below)
│      • probe-state dict + optional QD2 thread     12608-12633
│      • sync_observability_gates()                 12639  — diagnostic module imports
│      • _emit_golden_diagnostics_config(...)       12640
│      • guarded imports: critical_path_ledger      12649,12691
│      • ledger begin/identity/span/endpoints       12655-12730
│      • guarded import: gantt_telemetry            12738 + point spans 12740-12754
│      • optional snapshot manifest (env-gated off) 12762-12779
│
└── post_snapshot_restore  [12781 .. 14823]        duration_ms (its own timer)
       ├── restore:early/eviction/snapshot/preamble/finalize spans
       ├── bootstrap_restore_ms  [13191 .. 13224]  (bracket around bootstrap.restore() @13204)
       │     └── restore_gpu_state_ms  (~599 in the 2026-09-11 breakdown)   ⊂ bootstrap
       │     └── cuda_init_ms          (~69)                                ⊂ bootstrap
       │     └── runtime-state / models / custom-node / seed stages         ⊂ bootstrap
       ├── bootstrap generation diagnostics        13223-13262
       ├── CPU-snapshot activation block           13432-14188   (NOT active in Golden)
       ├── preload / defer block                   14190-14442
       └── restore finalization                    14444-14574
```

**Rules that remove double-counting:**
- `restore_gpu_state_ms` ⊂ `bootstrap_restore_ms` ⊂ `post_snapshot_restore` ⊂ `restore_total_ms`. It can never be added to the pre-marker gap.
- `residual_ms` = `restore_total_ms − Σ(present named deep timers)` — a derived remainder, not a timed interval. Never add it as another interval.
- `restore_total_ms` (success path, to 14489) is captured slightly **before** `post_snapshot_restore` end (14823); use the **finally** recomputation (14845) when comparing with the post-marker duration.

**Measured facts from the current tree (2026-09-11 `restore_breakdown` artifact in `EXPERIMENT_EVIDENCE_golden_p1_parallel_1796a2b8de1a42a0_2026-09-11.md`):**

```text
restore_total_ms          1288.389
  restore_gpu_state_ms     599.188   (inside bootstrap)
  sync_custom_nodes_ms     236.670   (inside bootstrap)
  reload_runtime_state_ms  184.658   (inside bootstrap)
  cuda_init_ms              69.430   (inside bootstrap)
  snapshot_execution_seed_ms 2.990
  observe_generations_ms     0.740
  folder_warm_ms          1029.428   (background thread; overlaps)
restore_method_ms         1318.049
```

**Pre-marker cost hypothesis, corrected:** `_resolve_restore_clip_probe_source` is **cheap by default**. `_restore_clip_probe_source_mode` defaults to `"models_volume"` (`modal_app.py:308`), and that branch returns a plain dict with **no stat/read/copy** (`modal_app.py:330-337`). Only `local_cache` mode stats a staged file (`:389-416`). Therefore the pre-marker interval is dominated by **module imports / initialization** (`json`, `os`, `threading` already loaded; then `critical_path_ledger`, `gantt_telemetry`, and the modules pulled in by `sync_observability_gates`: `model_preload` gate sync, optional `clip_forward_forensics`, optional `e27_forensics`). No Volume RPC occurs in `[12604,12781)`. **Static evidence cannot assign ~600 ms to this region.**

---

## C. Revised essential restore contract (from zero)

Each operation is admitted only with a named concrete failure.

| Operation | Concrete failure if omitted | Why snap=True cannot cover it | Why first-use cannot cover it | Expected wall cost |
|---|---|---|---|---|
| **Reset true container-local mutable state** — UNET barrier events + boundary anchor, `_rbg_unet_done_events`, nonce/session/restore-instance ids, `_active_next_read_dedup` + counts, `_RES4LYF/_CACHEDIT_PREPARED`, `_request_count`, stage timers, identity epoch/cache/scope | A second/warm restore inherits a set barrier → boundary workers wake immediately and behave like `after_clip_preload`; stale nonce/dedup/prepared flags leak across restores (P1 bug fixed at `comfyapp.py:20312-20341`, `modal_app.py:12946-12969,13188-13189,14452`) | These are per-restore event/lock state; snap=True captures the *pre*-restore values, which are exactly the stale values | Cannot be deferred: the first request/worker reads them immediately | µs–low ms |
| **Repair minimal logical GPU state** — `args.cpu=False`, `cpu_state=GPU`, `DISABLE_SMART_MEMORY=False`, `vram_state=HIGH_VRAM`, `get_torch_device()` returns `cuda` (`comfyapp.py:20242-20251`) | Backend was initialized under `force_cpu_during_snapshot`; captured `cpu_state=CPU` → model placement stays CPU and CUDA-only attention paths fail | The CPU state is what got captured; snap=True cannot both hide CUDA and leave GPU state | First request would run the graph on CPU / fail before repair | pure assignments + one device get; **do not bundle** the memory queries |
| **Models generation guard** — read mounted `models_generation.json`, compare to snapshot baseline, fail closed on mismatch (`runtime_bootstrap.py:1508-1597`) | Request loads a wrong or missing model under the same logical name (`comfyapp.py:18809-18849`) | Baseline is captured at startup; the failure is an out-of-band Volume mutation after capture | Request is where the wrong model is used — too late to "repair" | one small JSON read (sub-ms) |
| **Minimal timing/status telemetry** — `restore_start`, `restore_end`, `restore_total_ms`, `restore_method_status`, `failure_reason` | No operator-visible restore timing/status | n/a | n/a | µs |

**Explicitly NOT admitted (not proven):**
- Forced `torch.cuda.synchronize()` / `get_device_name` before readiness (defer to first GPU use; `comfyapp.py:18574,18593`).
- `get_total_memory` / `memory_stats` / `mem_get_info` / `psutil.virtual_memory()` in restore (`comfyapp.py:20267-20276`).
- Runtime-state reconciliation (no request-correctness failure; §A6).
- Any custom-node identity check / Volume reload (`§A4`).
- Sage synchronous verification (`§A8`).
- Execution-seed rebuild in restore (make it fail-closed; freeze inputs at snap=True).
- Ledger / Gantt / samplers / host-memory / `_rd_deep` / eviction / folder warm / CPU-snapshot activation / CacheDiT / RES4LYF / preload / UNET defer / speculative CLIP / clean-lane.

> Note on the first candidate: even `reset` + logical GPU repair alone may be sufficient to make requests runnable; the models guard is the only *additional* check with a named request-correctness failure. The contract above is the proven floor, not a fixed target.

---

## D. Revised DELETE / MOVE / DEFER table

| Item | Location | Classification |
|---|---|---|
| Container-local mutable-state reset | `comfyapp.py:20312-20341`; `modal_app.py:12946-12969,13188-13189` | **KEEP IN RESTORE** |
| Logical GPU-state repair (A) | `comfyapp.py:20242-20251` | **KEEP IN RESTORE** |
| Models generation guard | `runtime_bootstrap.py:1508-1597` | **KEEP IN RESTORE** |
| Minimal restore telemetry | `modal_app.py:14488+` (reduced) | **KEEP IN RESTORE** |
| Thread policy | `modal_app.py:13045-13052` | **MOVE TO SNAP=True** (already applied at `11270`) |
| Observability gate resolution | `modal_app.py:12639` | **MOVE TO SNAP=True** |
| Execution-seed inputs (cert hash, loader identities, deployment hash) | `runtime_bootstrap.py:2610-2684` | **MOVE TO SNAP=True** (build/attach fail-closed at request) |
| Execution-seed request attach | `modal_app.py:20218-20254`; `runtime_executor.py:4141-4152` | **FIRST USE / request** (fail-closed; pure enrichment) |
| Custom-node publish/scan/hash/verify | `tools/v2_control/custom_nodes.py:804-965`; `publication_policy.py:419-429` | **MANUAL ONLY** |
| Custom-node deploy gate | `tools/v2_control/cli.py:2808-2822,2887-2913,2959-2962` | **MANUAL ONLY** (remove from normal deploy) |
| Auto custom-node sync / generation compare / mismatch gate | `runtime_bootstrap.py:2442-2609`; `modal_app.py:10440-10563` | **DELETE** |
| Restore-time custom-node `Volume.reload()` | `modal_app.py:10727-10787` | **DELETE** |
| `observe_generations` / parity reporting in restore | `runtime_bootstrap.py:2584-2609`; `custom_node_parity.py` | **DIAGNOSTIC ONLY** (manual/audit) |
| Runtime-state manifest hash verification | `runtime_bootstrap.py:1696-1774`; `runtime_generation.py:210-247` | **DELETE from readiness** (optional diagnostic; no request-input evidence) |
| Runtime-state reload decision/stage | `runtime_bootstrap.py:2265-2352` | **DELETE from readiness** |
| Sage select + apply in restore | `runtime_bootstrap.py:2121-2263` | **FIRST USE** (assert cached baked mode at first Sage use) |
| Sage identity/config capture | `sage_policy.py:44-137` | **MOVE TO SNAP=True** |
| CPU-snapshot activation/retarget/validation | `modal_app.py:13432-14188`; `cpu_snapshot_models.py:2708,2960` | **DELETE** (gate default False; Golden clears it at `11055-11070`) |
| CacheDiT restore prep | `runtime_bootstrap.py:898-979` | **DELETE** |
| RES4LYF restore prep | `runtime_bootstrap.py:986-1102` | **DELETE** |
| Preload bridge orchestration | `modal_app.py:13838-14155` | **DELETE from Golden** (other profile) |
| Production UNET defer | `modal_app.py:14308-14419` | **DELETE from Golden** (other profile) |
| Speculative CLIP restore lane | `modal_app.py:14598-14610`; `speculative_clip_hydration.py:1231+` | **DELETE** (historical) |
| Folder warming | `modal_app.py:13005-13010`; `execution_warm.py:30+` | **DELETE** (contention, §A12) |
| Pre-marker ledger / Gantt / manifest / probe scaffolding | `modal_app.py:12605-12780` (minus cheap probe resolve) | **DELETE / DIAGNOSTIC ONLY** |
| `_rd_deep` + residual emission | `modal_app.py:14649-14739` | **DELETE / DIAGNOSTIC ONLY** |
| Cgroup + process CPU samplers | `modal_app.py:12938-12944`; `_CgroupCpuSampler` | **DIAGNOSTIC ONLY** |
| Host memory probe / host fingerprint | `modal_app.py:12938-12944,14741-14778`; `runtime_bootstrap.py:2687-2697` | **DIAGNOSTIC ONLY** |
| Eviction boundary (RSS/GC) | `modal_app.py:9528` | **DELETE** (keep only a cheap model-free assertion if Golden requires it) |
| Full-trace identity/milestone in restore | `modal_app.py:13100-13122` | **DIAGNOSTIC ONLY** (opt-in) |
| Clean-lane calls | `modal_app.py:13177,13207,14809` | **DELETE** (no-op unless flag; `clean_lane.py:39-43`) |
| Clock/`resource_identity` double-compute, `_detect_gpu_allocation`, hostname | `modal_app.py:13125,13162,14802,14752` | **DELETE** |
| `torch.cuda.synchronize` / `get_device_name` before readiness | `comfyapp.py:18574,18593` | **FIRST USE** (not proven required) |
| `get_total_memory` / `psutil` in restore | `comfyapp.py:20267-20276` | **DELETE** (or `UNKNOWN` — measure first) |

---

## E. Revised minimal pseudocode

```python
def restore(self):
    t0 = perf_counter()

    # 1. Repair only state that fundamentally cannot survive the CPU snapshot.
    reset_true_container_local_state()   # barriers, nonces, session ids, dedup sets, prepared flags, counts

    # 2. Repair the logical ComfyUI GPU state captured as CPU.
    #    (assignments only; NO synchronize / memory_stats / mem_get_info / psutil)
    restore_minimum_logical_gpu_state()  # args.cpu=False; cpu_state=GPU; vram_state=HIGH_VRAM; assert get_torch_device().type == "cuda"

    # 3. The one proven request-correctness identity check.
    assert_models_generation_matches_snapshot()   # one JSON read; fail closed on mismatch

    # 4. Minimal telemetry.
    emit_restore_total(perf_counter() - t0)

    return ready

# NOT in restore: custom-node identity/reload/gate; runtime-state reconciliation;
# Sage verification; execution-seed rebuild; ledger/Gantt/samplers/host probes;
# eviction; folder warm; CPU-snapshot activation; CacheDiT/RES4LYF/preload/defer.
```

---

## F. Remaining unknowns (small experiments before implementation — do not run here)

1. **Pre-marker magnitude.** Take one current run containing both `restore_total_ms` (finally value, `modal_app.py:14845`) and the `post_snapshot_restore` start (`[v2.startup_stage] stage=post_snapshot_restore event=start monotonic_ns=…`) and subtract. Candidate owners if large: the guarded imports in the pre-marker slice (`critical_path_ledger`, `gantt_telemetry`, and `sync_observability_gates` → `model_preload`, `clip_forward_forensics`, `e27_forensics`). **The exact 2053/1420/615/1451 run is not in this tree.**
2. **`restore_gpu_state` ≈ 599 ms decomposition.** Read `[v2.restore_breakdown]`/`_RESTORE_STAGE_TIMERS` across 3 restores, or split the timer (future work) to attribute between first CUDA driver probe, `get_total_memory` (`memory_stats`+`mem_get_info`), `psutil.virtual_memory`, and `apply_frozen_total_vram_or_none`.
3. **Snapshot GPU logical state.** Confirm whether the snapshot captures `cpu_state=CPU` or `GPU` (assert `get_torch_device().type` at restore with the repair disabled, on a diagnostic run). Determines whether step 2 is truly required.
4. **Eager-CUDA A/B.** Compare `logical GPU repair only` vs `logical repair + eager CUDA init/synchronize` on **resume → FIRST_RESULT_READY** (shifting synchronize into CLIP is not automatically a win).
5. **Models guard behavior.** Confirm the one-JSON guard actually detects an out-of-band models Volume mutation (generation bump then restore on an old snapshot).
6. **Execution-seed equivalence.** Confirm the request-derived seed path (`COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0`, `modal_app.py:20254-20400`) produces equivalent warm-start behavior to the restore-built seed for a Golden workflow.
7. **Reduced contract validity.** Verify the `reset + logical GPU repair + models guard` contract runs a Golden Parallel workflow end-to-end on a diagnostic deployment, and that a missing node fails via `comfyapp.py:15828-15877`.

---

## Appendix — reference metadata

**Worktree:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
**HEAD SHA:** `b81510606894bb4d03e8af7c243dd85b76f61f3b`
**Corrected report path:** `GOLDEN_RESTORE_AUDIT_RECONCILIATION_2026-09-11.md`

**Key locations:** `modal_app.py:12583-14875` (restore, 2,293 lines); `:12604` (`_restore_perf_start`); `:12781` (post_snapshot_restore start); `:13191-13226` (bootstrap brackets); `:14488,14845` (restore_total); `:14679-14706` (residual); `:419-428,298-416` (probe source); `:770-803` (sync_observability_gates); `:10440-10563,10727-10787` (custom-node); `runtime_bootstrap.py:1984-2786` (restore, 803 lines); `:1508-1597` (models); `:1696-1774` (runtime-state); `:2121-2263` (Sage); `:2442-2609` (custom-node); `:2610-2684` (seed); `comfyapp.py:18544-18625` (`_initialize_cuda_context`); `:20197-20288` (`_restore_in_process_gpu_state`); `:20312-20341` (mutable reset); `:20411-20537` (E37); `:15794-15877` (missing-node gate); `:18809-18849` (model loaders); `comfymodal_runtime/runtime_generation.py:57-92,210-247`; `config_authority.py:97,112-114,152,183`.

**Evidence artifacts:** `EXPERIMENT_EVIDENCE_golden_p1_parallel_1796a2b8de1a42a0_2026-09-11.md` (restore_breakdown); `CAMPAIGN_REPORT_CLIP_FORWARD_CONTENTION.md:45-46,115`; `DISCRIMINATORS_SYNTHESIS_REPORT.md:27-29`; `v2_pcc_deploy2_construction.log` / `v2_d10_applogs_full.txt:514` / `v2_d10_applogs_v41_deploy3.txt:504` (`[v2.restore_deep]`).

**Rule adherence:** read-only; no edits/commits/deploys; prior report treated as non-authoritative; Oracle not used as evidence; obsolete work deleted rather than deferred where the current architecture does not support it.
