# V2 Final: UNET Ownership + Post-Restore Rehoming — Report

**Questions:** (1) is the cache-hit early-activation race (worker scheduled, sampler
`blocking_owner=absent`, graph `load_models_gpu` running concurrently) the cause of the
duplicate UNET loads and exit-139 crashes, and does one authoritative request-scoped owner
fix it? (2) does cloning the restored UNET into fresh anonymous RAM after restore produce a
clearly tighter, faster transfer path (the production rehome fix)? (3) does the integrated
unpinned shadow meet the acceptance criteria?

**Answers (direct measurement, shadow deployments only):**

1. **Yes and yes.** The graph `load_models_gpu` path never serialized against the scheduled
   early-activation worker — both moved/pached the same ModelPatcher concurrently. Under the
   exclusive-owner gate (worker publishes an ownership claim before touching storage/CUDA; the
   graph joins the worker's future at the sampler boundary *before* acquiring the mutation lane,
   and again at the load entry), **8/8 valid cold GCP runs show exactly one UNET migration,
   zero SIGSEGV, zero cancelled request-used workers, zero duplicate graph loads (graph load
   collapsed from ~7.5-13.5 s to ~2.4-5.3 ms cache validation), and zero sampler acquires while
   a future was pending.**
2. **No.** The rehome clone must read the 12.3 GB restored pages once, and those pages read
   slowly for *any* full read — GPU DMA *and* parallel CPU memcpy (7-12.4 s on the affected
   containers; the fresh-clone H2D itself is consistently fast at 0.57-0.75 s). The clone is
   byte-identical and identity-preserving (5/5 runs, verified against the actual GPU-transferred
   bytes), but the total path (1.1-4.6 s isolated, 7.6-13.1 s integrated) is **not clearly
   tighter and faster** than the direct restored-page load (0.6-19 s, pool-dependent). Per the
   protocol, the rehome hypothesis is **rejected**; only default-off diagnostics are retained.
3. **Not met.** The integrated rehome arm failed the acceptance gate at the 2-run check
   (clone+transfer 7.6-13.1 s vs <3 s; application execution 14.4-17.2 s vs <13 s) and was
   stopped per the protocol instead of burning the remaining runs. The **ownership-only
   probes-off** configuration (phase B) met the <13 s application-execution goal **4/4** on GCP
   (8.1-11.3 s) — that is the evidence-backed configuration, kept default-off behind one env
   gate.

## Root cause of the crashes and duplicate loads (proven)

Reproduced container log (pre-fix, GCP, exit 139):

```
25.990 [v2.unet_early_activation] event=scheduled trigger=conditioning_cache_hit ...
       [v2.unet_ownership] event=claim ... (worker claimed ownership)
26.351 [v2.sampler_boundary] event=sampler_lane_requested ... blocking_owner=absent
26.941 [v2.gpu_load_boundary] event=load_models_gpu_start ... contains_registered_unet=1
       caller_classification=graph_model_loading        ← graph proceeded, no join
30.452 Transient snapshot error: failed to restore container from snapshot with exit code 139
```

The graph-side `load_models_gpu` ran on the graph thread with **no mutation lane and no join of
the worker's future**, while the worker concurrently ran diagnostics/load on the same UNET
(claim→release up to 14.4 s with the worker's load and the graph's load overlapping; the worker
then ended `cancelled` with `transfer_count=0` while the graph's own load produced the result).
That concurrent patch/move of one ModelPatcher from two threads is the SIGSEGV candidate, and
it also explains the duplicate 7.5-13.5 s "transfers" (two loads of the same model, both slow,
both counted).

The fix (default-off gate `COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER`):

- **Worker claim/release ledger** — the early-activation worker publishes `ownership.claimed_mono_ns`
  before touching storage or CUDA and `released_mono_ns` at its terminal boundary (exact timestamps,
  recorded always, printed under the gate).
- **Sampler-boundary join** — at the first sampler node, *before* the sampler acquires the
  mutation lane, the graph joins the request's activation future (bounded 120 s). This removes
  both the concurrent-load race and the worker-blocked-on-sampler-lane stall.
- **Load-entry join-or-adopt** — the `load_models_gpu` wrapper joins/adopts the same future
  before any pretouch/page-readiness/registry inspection of the registered UNET.
- **Strong storage references** during all native diagnostics (a concurrent `.data` replacement
  can no longer free a storage mid-traversal → use-after-free eliminated).

## Experiment 1 — ownership, GCP, exclusive owner ON (4 + 4 valid cold)

All runs: `restore_count=1, request_count=1`, fresh identity, cache-hit trigger
`conditioning_cache_hit`, `late` activation, single-use containers, minimal teardown,
CPU 16 / 49152 MiB / RTX PRO 6000 / TBASE / O0. Snapshot-builder attempt + the following
request excluded per arm. GCP pin only (no region pin). Raw artifacts:
`comfymodal-data/benchmarks/runs/v2_2026-08-06_18-23-09_ownership` (probes on) and
`v2_2026-08-06_18-31-29_ownership` (probes off).

| arm | attempt | class | app-exec (ms) | pre-sampler (ms) | join wait (ms) | migration | graph-load wall (ms) | real H2D (ms) | traversal (ms / GB/s) | residency |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| probes_on | 0000 | excl. (builder) | — | 44322 | — | 0 (graph) | 9495 | — | — | — |
| probes_on | 0001 | excl. (after) | — | 21279 | 9232 | 1 | 3.5 | 695 | 13732 / 0.9 | 1.0 |
| probes_on | 0002 | **cold** | 12889 | 7515 | 4690 | 1 | 3.4 | 805 | 332 / 37.0 | 1.0 |
| probes_on | 0003 | **cold** | 22872 | 17475 | 15305 | 1 | 4.2 | 982 | 6528 / 1.9 | 1.0 |
| probes_on | 0004 | **cold** | 13702 | 8053 | 5143 | 1 | 4.0 | 1005 | 741 / 16.6 | 1.0 |
| probes_on | 0005 | **cold** | 13416 | 7765 | 5842 | 1 | 4.7 | 708 | 129 / 95.3 | 1.0 |
| probes_off | 0000 | excl. (builder) | — | 18495 | 13422 | 1 | 2.8 | — | — | — |
| probes_off | 0001 | excl. (after) | — | 12564 | 6965 | 1 | 2.4 | — | — | — |
| probes_off | 0002 | **cold** | 8134 | 2639 | 828 | 1 | 2.4 | — | — | — |
| probes_off | 0003 | **cold** | 8061 | 2689 | 1003 | 1 | 2.6 | — | — | — |
| probes_off | 0004 | **cold** | 11298 | 5753 | 3794 | 1 | 3.0 | — | — | — |
| probes_off | 0005 | **cold** | 8355 | 2802 | 981 | 1 | 5.3 | — | — | — |

Every valid run: `decision=join → outcome=ready`, worker terminal `ready`, `transfer_count=1`,
`exactly_one_migration=True`, `suspected_duplicate_graph_load=False`, `worker_cancelled=False`,
`sampler_owner_absent_while_pending=[]`. **Zero SIGSEGV / zero snapshot fallback / zero
`blocking_owner=absent` while a future was pending.** The graph load after the join is a pure
cache validation (2.4-5.3 ms). Phase-B application execution: **4/4 < 13 s** (8.06-11.30 s).

Key attribution: the "slow transfer" spans in earlier studies were inflated by the diagnostics
themselves — the 1-byte-per-page traversal takes 0.13-13.7 s depending on the restored pages'
per-page access cost, and the load-span event includes probes + lane wait + transfer. The real
H2D partition (variance gate) was only 0.69-1.00 s on every phase-A run today. Phase-B worker
totals (join waits) were 0.83-3.79 s.

## Experiment 2 — post-restore rehoming, paired measurements (4 valid cold)

Dedicated shadow method `run_rehoming_experiment` (no graph execution), alternating order per
run (`clone_first` / `original_first`), same container for each pair. Raw artifacts:
`comfymodal-data/benchmarks/runs/v2_2026-08-06_19-08-49_rehoming` (+ supporting batch
`v2_2026-08-06_18-59-50_rehoming`).

| run | order | original restored H2D (ms) | clone CPU copy (ms) | fresh clone H2D (ms) | clone+H2D (ms) | byte-eq |
|---|---|---:|---:|---:|---:|---|
| 0 (excl. builder) | original_first | 2210 | 3228 | 641 | 3869 | all_equal |
| 1 | clone_first | 658 | 3296 | 571 | 3866 | all_equal |
| 2 | original_first | 8749 | 3853 | 748 | 4601 | all_equal |
| 3 | clone_first | 643 | 1224 | 669 | 1894 | all_equal |
| 4 | original_first | 1283 | 1656 | 747 | 2404 | all_equal |
| support A | clone_first | 583 | 551 | 585 | 1135 | all_equal |
| support B | original_first | 19050 | 500 | 600 | 1100 | all_equal |

Every run: 454 storages / 12,309,821,472 bytes; fingerprint hash identical before/after the
clone; post-clone backing 454 anonymous / 0 volume; residency 1.0; byte-equality vs the actual
GPU-transferred original bytes `all_equal`.

- Fresh-clone H2D is **always fast** (571-748 ms) regardless of pool condition.
- The original restored-storage H2D swings 583 ms → 19.05 s (pool-dependent).
- The clone CPU copy itself inherits the restored-page read cost: 0.5-3.9 s isolated,
  and 7.0-14.8 s on the affected containers in the integrated arm (parallel 8-thread memmove
  measured 7 cores busy at ~1.7 GB/s/core — the *pages*, not the copy kernel, are slow).
- Acceptance ("clone+H2D <3 s every run") failed 2/4 official runs (3.87, 4.60 s); the total
  path is not clearly tighter and faster than the direct load. **Rehome rejected for
  production; the hook stays default-off diagnostics.**

## Experiment 3 — integrated unpinned shadow (stopped at the 2-run gate)

Config: unpinned, exclusive owner ON, rehome ON, all heavy diagnostics OFF. Raw artifacts:
`comfymodal-data/benchmarks/runs/v2_2026-08-06_19-50-48_integrated` (2 valid cold runs
preserved; earlier pre-memmove batch in `v2_2026-08-06_19-28-57_integrated`).

| run | clone (ms) | worker load (ms) | join wait (ms) | app-exec (ms) | migration | acceptance |
|---|---|---:|---:|---:|---:|---|
| 0-1 | excl. (builder + after) | — | — | — | — | — |
| 2 | 9336 | 10138 | 9925 | 17165 | 1 | FAIL (clone+transfer >3 s; app-exec >13 s) |
| 3 | 6970 | 7634 | 5548 | 14387 | 1 | FAIL (same) |

The acceptance gate failed on both valid runs → the study was stopped immediately (crash-aware
runner: any exit-139 / snapshot-restore failure / stream loss dumps
`crash_diagnostics.json` and aborts instead of retrying through the problem).

## Required conclusions

- **Ownership fix: supported and verified.** One authoritative request-scoped UNET owner
  (claim-before-touch, sampler-boundary + load-entry join-or-adopt) eliminates the concurrent
  worker/graph mutation, the duplicate migrations, the cancelled workers, and the exit-139
  crashes — 10/10 post-fix GCP runs crash-free vs repeated 139s before. With probes off it also
  meets the <13 s application-execution goal 4/4 on GCP.
- **Rehome: not supported.** The restored pages are slow for any full read (GPU DMA or parallel
  CPU memcpy); the clone just moves the cost. Fresh memory is fast, but you must read the slow
  pages once either way. Correctness and identity are preserved 5/5, but the path is not
  clearly tighter and faster. Retained default-off only.
- **Integrated rehome arm: rejected** by its own acceptance gate at the 2-run checkpoint per
  protocol; attempts preserved.
- Nothing speculative ships: both new mechanisms are env-gated default-off. The evidence-backed
  production lever is `COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER=1`.

## Files changed

- `comfymodal_runtime/unet_backing.py` — strong storage refs in `traverse_unet_pages` /
  `mincore_unet_residency` (use-after-free fix); storage-faithful fresh-RAM rehome clone
  (parallel `ctypes.memmove`, ties/views/params preserved) + `rehome_after_restore_enabled`;
  `measure_model_synced_h2d` / `measure_tensors_synced_h2d` (read-only, name-paired);
  `unet_metadata_fingerprint`; `unet_byte_equality`.
- `comfymodal_runtime/model_preload.py` — `COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER` gate; ownership
  claim/release ledger; `graph_unet_join_or_adopt`; graph-side join in the `load_models_gpu`
  wrapper before any UNET inspection; rehome hook in the early-activation worker (before the
  load, after probes); reconciliation fields (ownership/graph_join/rehome_clone);
  `contains_registered_unet` added to `graph_gpu_load_start` metadata.
- `comfymodal_runtime/modal_app.py` — env passthrough for both new gates (they were silently
  dropped by the `_runtime_env` allowlist — the root deployment bug of the first attempt);
  sampler-boundary join before the mutation-lane acquire; `run_rehoming_experiment` shadow
  method registration.
- `comfymodal_runtime/rehoming_experiment.py` — **new**: dedicated no-graph shadow method
  (paired restored-vs-clone H2D, alternating order, GPU-byte equality proof, identity
  fingerprints, residency/backing/faults).
- `tools/run_ownership_rehoming_study.py` — **new**: runner for the three experiments with
  crash detection (exit-139 / snapshot-restore failure / stream loss → immediate stop +
  `crash_diagnostics.json` pack) and per-run ownership/join/migration checks.
- `deploy_and_run_ownership_rehoming.py` — **new**: shadow deploy script (4 shadow apps:
  ownership GCP probes-on/off, rehoming, integrated unpinned).
- `V2_FINAL_OWNERSHIP_AND_REHOMING_REPORT.md` — this report.

## Tests

- Local: clone fidelity (tied storages, strided views, values, identities), ownership
  join-or-adopt unit checks (join / already_ready / adopt / gate-off), compile checks.
- Suites: `test_v2_unet_early_activation`, `test_v2_quiesced_transfer`,
  `test_v2_page_readiness`, `test_model_preload_critical_path` (130 passed);
  `test_variance_diagnostics` + `test_v2_preload_bridge` (67 passed, 1 pre-existing
  cursor-timing race that also fails on pristine HEAD in this filesystem);
  `test_v2_cpu_eviction`, `test_model_preload_attribution`, `test_v2_full_trace_report`,
  `test_audit_round8_diagnostics` (360 passed; 2 pre-existing failures that fail on HEAD too).

Final commit SHA: see the head commit of `main` at the time of writing.
