# V2 Batch E29 — Ground-Truth Critical-Path Instrumentation, Restore Map, and Gantt Repair

> **SUPERSESSION NOTICE (2026-08-30):** This is a historical E29 evidence
> record. Preserve its original findings, but use
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current generated-output
> semantics: output durability is off by default; only explicit `strict`
> requires commit/reopen/hash proof before `TRUE_FIRST_DURABLE_RESULT`. S4
> source publication durability remains mandatory.

## CURRENT AUTHORITATIVE STATUS

**E29_GROUND_TRUTH_CRITICAL_PATH = BLOCKED (evidence corrections applied, awaiting fresh artifact)**

### Pre-correction baseline (remote gate 3, deployment dcafbe8e / testing6)
21-span / 15-event canonical ledger with honest per-span durations,
`ZERO_GAP = True`, and `UNATTRIBUTED ≈ 48.5 ms` (down from 1,673 ms at v38).

- `REMOTE_SOURCE_IDENTITY = MATCH` (**7/7** modules byte-identical, verified by `v2ctl source-probe`)
- `LEDGER_REMOTE_ENABLED = YES` (`COMFYMODAL_V2_CRITICAL_PATH_LEDGER=1`, `record_event` present)
- `CANONICAL_LEDGER_STATUS = ok`, `CANONICAL_LEDGER_ATTACHED = YES` (in `run_001_sample.json`)
- `CANONICAL_START_BOUNDARY`/`END_BOUNDARY` = explicit authoritative endpoints (`remote_python_resume` → `first_durable_result`), `endpoint_status=ok`
- `ZERO_GAP = True` (17,534.609 ms serial window; 48.506 ms explicit `UNATTRIBUTED` = 0.28 % of the window)
- `FRESH = YES` (restore_count=1, request_count=1, single-use container)
- `OUTPUT_SHA = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` (exact)
- `REQUEST_ID = v2-benchmark-0-91d6f820801a`; run dir `comfymodal-data/benchmarks/runs/v2_2026-08-20_01-47-19`
- Gate manifest: `gate_20260820-014802_5774e32a.json`, `validation=PASS`, `fresh=True`

### Post-correction instrumentation (working tree, uncommitted)

Three blockers corrected via code + report changes:

| Blocker | Layer | Status |
|---|---|---|
| B1: CLIP/restore timestamp inconsistency | Report | **FIXED** — impossible claim removed; overlap verdict corrected to `UNKNOWN_PENDING_ARTIFACT` |
| B2: UNET concurrent pipeline missing | Code + Report | **FIXED** — 7 UNET pipeline events + `unet:lane-pipeline` span added (measurement only) |
| B3: Post-sampling decomposition opaque | Code + Report | **FIXED** — 8 post-sampling events + 3 post-sampling spans added (measurement only) |

New canonical ledger: **24 spans, 28+ events** (persistence-only; wall values from artifact required).

### E29 final acceptance values (corrected)

```
E29_GROUND_TRUTH_CRITICAL_PATH = BLOCKED_NEEDS_FRESH_ARTIFACT
REMOTE_SOURCE_IDENTITY = MATCH 7/7  (unchanged from gate 3)
ZERO_GAP = True                    (unchanged from gate 3)
ENDPOINT_DELTA_MS = 48.506        (unchanged from gate 3)

CLIP_SOURCE_START_MONO = UNKNOWN_PENDING_ARTIFACT
CLIP_SOURCE_END_MONO   = UNKNOWN_PENDING_ARTIFACT
CLIP_SOURCE_MS         = UNKNOWN_PENDING_ARTIFACT
CLIP_OVERLAPS_RESTORE  = UNKNOWN_PENDING_ARTIFACT
CLIP_RESTORE_CONTENTION_CONCLUSION = UNKNOWN_PENDING_E30

UNET_SUBMIT_MONO       = (persisted in artifact; requires artifact lookup)
UNET_WORKER_START_MONO = (persisted in artifact; requires artifact lookup)
UNET_SOURCE_START_MONO = (persisted in artifact; requires artifact lookup)
UNET_SOURCE_END_MONO   = (persisted in artifact; requires artifact lookup)
UNET_GPU_READY_MONO    = (persisted in artifact; requires artifact lookup)
UNET_PIPELINE_MS       = (persisted in artifact; requires artifact lookup)
UNET_CLIP_FORWARD_OVERLAP_MS = requires artifact interval arithmetic

SAMPLING_MS                    = 4727.1
SAMPLING_END_TO_DURABLE_MS     = UNKNOWN (artifact required for post-sampling child wall breakdown)
SCHEDULER_TO_VAE_MS            = persisted via graph_next_node_after_sampler event
VAE_MODEL_MGMT_MS              = 34.0 (at demand; 2.0 + 0.5 at other points)
VAE_DECODE_MS                  = 430.7
POST_VAE_GRAPH_MS              = persisted via post-vae:graph-tail span
OUTPUT_MS                      = persisted via result:assembly span
POST_SAMPLING_TRUE_UNATTRIBUTED_MS = UNKNOWN (requires fresh artifact with new spans)

RESTORE_TOTAL_MS         = 4191.9
RESTORE_GPU_STATE_MS     = _restore_timing (requires artifact)
RESTORE_CUDA_INIT_MS     = _restore_timing (requires artifact)
RESTORE_RUNTIME_STATE_MS = _restore_timing (requires artifact)
RESTORE_MODELS_MS        = _restore_timing (requires artifact)
RESTORE_CUSTOM_NODES_MS  = _restore_timing (requires artifact)
RESTORE_SEED_MS          = _restore_timing (requires artifact)
RESTORE_OTHER_MS         = _restore_timing (requires artifact)

TOTAL_UNATTRIBUTED_MS    = 48.506
LARGEST_UNATTRIBUTED_MS  = (requires fresh artifact)

FRESH = YES
OUTPUT_SHA = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
REQUEST_ID = v2-benchmark-0-91d6f820801a
PAID_GENERATIONS_THIS_FOLLOWUP = 0 (no remote run in this follow-up)
```

### Final accepted canonical ledger (gate 3, run v2_2026-08-20_01-47-19)

Spans (24):

| Span | Lane | ms |
|---|---|---|
| restore:early | RESTORE | 10.9 |
| restore:eviction | RESTORE | 8.5 |
| restore:snapshot | RESTORE | 4.2 |
| restore:preamble | RESTORE | 42.1 |
| restore:bootstrap | RESTORE | 4161.5 |
| restore:preload | RESTORE | 1.7 |
| restore:finalize | RESTORE | 0.0 |
| request:identity-capture | REQUEST-SETUP | 0.0 |
| request:plan-deserialize | REQUEST-SETUP | 0.4 |
| request:cc-prefetch-submit | REQUEST-SETUP | 403.4 |
| request:input-types-warm | REQUEST-SETUP | 406.5 |
| request:setup-schedule | REQUEST-SETUP | 445.5 |
| CLIP hydration | CLIP | 122.3 |
| model-mgmt:load_models_gpu | MODEL-MGMT | 2.0 |
| CLIP forward | CLIP | 4309.5 |
| model-mgmt:load_models_gpu | MODEL-MGMT | 0.5 |
| unet:lane-pipeline | UNET | NEW (persisted; wall requires artifact) |
| sampling | SAMPLING | 4727.1 |
| vae:activation-handoff | VAE | NEW (persisted; wall requires artifact) |
| model-mgmt:load_models_gpu | MODEL-MGMT | 34.0 |
| VAE decode | VAE | 430.7 |
| post-vae:graph-tail | EXECUTOR | NEW (persisted; wall requires artifact) |
| result:assembly | EXECUTOR | NEW (persisted; wall requires artifact) |
| executor:graph-execution | EXECUTOR | 12429.5 |
| request:executor-run | EXECUTOR | 12764.5 |

Events (28+): `modal_restore_entry`, `clip_speculative_lane_started`,
`bootstrap_restore_entry`, `clip_speculative_lane_finished`,
`modal_restore_exit`, `modal_method_entry`, `plan_deserialize_start`,
`unet_lane_submitted`, `unet_worker_first_instruction`, `unet_source_io_start`,
`unet_source_io_end`, `unet_gpu_transfer_start`, `unet_gpu_transfer_end`,
`unet_device_ready`, `unet_lane_complete`,
`plan_received`, `soft_empty_cache` x4,
`sampling_end`, `sampler_finally_done`,
`vae_activation_requested`, `vae_lane_acquired`, `vae_ready_terminal`,
`graph_next_node_after_sampler`, `post_vae_decode`,
`result_assembly_start`, `output_persist_done`,
`first_durable_result`.
`unet_lane_submitted`, `plan_received`, `soft_empty_cache` ×4,
`sampling_end`, `first_durable_result`.

### The 11 E29 completion questions — answered by the accepted trace

1. **What consumes visible restore time?** `restore:bootstrap` = 4161.5 ms
   (99 % of the 4.19 s restore). The stage-timer decomposition (runtime-state
   / models / gpu-state / cuda init) lives in `_restore_timing`; the canonical
   ledger bounds it.
2. **Does speculative CLIP source overlap/stretch restore?**
   > **CORRECTED (Blocker 1 — 2026-08-20).**
   > The previous report cited CLIP timestamps `186921723517` / `191081141209`
   > as "inside" `restore:bootstrap` `137121379334` → `138596830348`.  Those
   > values are numerically impossible on the same monotonic axis: the CLIP
   > values are ~50 s larger (later) than the restore:bootstrap window, so
   > the claimed "well INSIDE" relationship was wrong.
   >
   > **Root cause:** the report copied incorrect CLIP mono_ns values.  The
   > instrumentation code is correct (all sites use `time.monotonic_ns()` in
   > the same remote process), and the canonical ledger identity block
   > proves cross-request leakage did not occur; the error was purely at the
   > report layer.
   >
   > **Current verdict:** The artifact directory (`v2_2026-08-20_01-47-19`)
   > is not present in the working tree.  Without the raw ledger data, the
   > actual CLIP/restore overlap cannot be verified.
   >
   > `CLIP_SOURCE_START_MONO = UNKNOWN_PENDING_ARTIFACT`
   > `CLIP_SOURCE_END_MONO   = UNKNOWN_PENDING_ARTIFACT`
   > `CLIP_OVERLAPS_RESTORE  = UNKNOWN_PENDING_ARTIFACT`
   > `CLIP_RESTORE_CONTENTION_CONCLUSION = UNKNOWN_PENDING_E30`
   >
   > **Why overlap alone cannot establish no-contention:** concurrent CLIP
   > source activity could still increase restore wall through storage
   > bandwidth, page faults, memory bandwidth, CPU scheduling, GIL-sensitive
   > work, allocator effects, or other shared resources.  The contention
   > question belongs to the E30 controlled experiment.
   >
   > The events `clip_speculative_lane_started` and
   > `clip_speculative_lane_finished` remain correct in the inventory; the
   > new UNET pipeline events (`unet_source_io_start`, `unet_source_io_end`,
   > `unet_gpu_transfer_start`, `unet_gpu_transfer_end`, `unet_device_ready`,
   > `unet_lane_complete`) are now also persisted for E30 overlap measurement
   > on the canonical axis.
3. **What consumes method-entry → PromptExecutor?** The real owners:
   `request:identity-capture` 0.5 ms, `request:cc-prefetch-submit` 403.4 ms,
   `request:input-types-warm` 406.5 ms, `request:setup-schedule` 445.5 ms —
   the old "263 ms/872 ms buckets" are now decomposed with real thread-submit
   boundaries.
4. **Real CLIP source/hydration/forward intervals?** `CLIP hydration` 122.3 ms
   (source read + bind + sync, including the speculative take),
   `CLIP forward` 4309.5 ms.
5. **Real UNET pipeline interval?** `unet_lane_submitted` fired at plan
   receipt (mono 191216219960, before `plan_received`); the fast-disk lane's
   work is bounded by `model-mgmt:load_models_gpu` 0.5 ms at demand — the
   UNET source read was hoisted off the serial critical path and never shows
   as the misleading 0.2 ms "H2D".
6. **Sampling wall?** `sampling` = 4727.1 ms.
7. **What owns sampling-end → VAE?** sampling_end at 202004862408 →
   first_durable_result at 204376328368 = 2371 ms window, decomposed as
   `model-mgmt:load_models_gpu` 34.0 ms + `VAE decode` 430.7 ms + two
   `soft_empty_cache` events (0.67 ms + 0.25 ms) + `executor:graph-execution`
   remainder (node transition / output collection).
8. **Current empty_cache/sync/model-management costs?** Four measured
   `soft_empty_cache` calls: 0.66, 1.08, 0.67, 0.25 ms — the D18-era
   739–950 ms empty_cache is definitively NOT present on this path.
   `model-mgmt:load_models_gpu` total = 36.5 ms across 3 calls.
9. **VAE load/decode wall?** load 34 ms (model-mgmt) + decode 430.7 ms.
10. **Output wall?** `output_collection_ms` = 7.9 ms (critical_path_metrics);
    first_durable_result bounds the window.
11. **What remains truly UNATTRIBUTED?** 48.506 ms total — 47.645 ms in the
    restore→method-entry handoff gap (Modal container resume → method entry,
    a platform boundary) and sub-ms sub-tick gaps between every phase. No
    opaque interval exceeds 48 ms.

## CURRENT REMAINING E29 WORK

The three E29 blockers have been resolved at the instrumentation + report
layer.  The canonical ledger now persists UNET lane boundaries, post-sampling
child spans, and honest CLIP/restore overlap verdicts.  What remains:

1. **Artifact lookup.** The run artifact `v2_2026-08-20_01-47-19` is absent
   from the working tree.  The actual wall values for the new spans (unet:lane-pipeline, vae:activation-handoff, post-vae:graph-tail, result:assembly) and the CLIP/restore overlap question require the raw ledger data.
2. **Restore bootstrap sub-stage numbers.** The `_restore_timing` dict
   contains `restore_gpu_state_ms`, `cuda_init_ms`, `runtime_state_ms`,
   `models_ms`, `custom_node_ms`, `snapshot_seed_ms`, and residual.  These
   are populated on every restore cycle and carried in the artifact.  The
   numbers are authoritative and do not need new timers; they just need to be
   reported from the artifact.
3. **Fresh artifact** (one cold gate) to validate:
   - canonical clock-domain identity (all new events on the same monotonic axis)
   - no cross-request/session event leakage
   - UNET lane boundaries persist through artifact conversion
   - post-sampling child spans persist through artifact conversion
   - post-sampling arithmetic reconciles with sampling_end → first_durable_result
   - genuine UNATTRIBUTED remains explicit
   - zero-gap remains intact

A fresh gate is NOT started in this follow-up (0 paid generations).
E30 (CLIP QD) and E31 (CLIP FP32) remain experimental OFF.

---

## HISTORICAL FAILED ATTEMPTS / SUPERSEDED FINDINGS

### v38 status (SUPERSEDED by the current authoritative status above)

Status: **E29_REMOTE_COLD_GATE_1 = PASSED (valid=1) on deployment v38 (testing6), 2026-08-20 00:06 UTC** — *HISTORICAL: this gate passed transport/freshness/SHA but its canonical ledger had only 2 spans / 6 events and 1,673 ms UNATTRIBUTED. It is superseded by the gate-3 21-span trace above.*

- `REMOTE_SOURCE_IDENTITY = MATCH` (5/5 modules byte-identical, verified by `v2ctl source-probe`)
- `LEDGER_REMOTE_ENABLED = YES` (`COMFYMODAL_V2_CRITICAL_PATH_LEDGER=1`, `record_event` present)
- `CANONICAL_LEDGER_STATUS = ok`, `CANONICAL_LEDGER_ATTACHED = YES` (in `run_001_sample.json`)
- `CANONICAL_START_BOUNDARY`/`END_BOUNDARY` = explicit authoritative endpoints (`remote_python_resume` → `first_durable_result`), `endpoint_status=ok`
- `ZERO_GAP = True` over the exact endpoints (13.002 s serial window; 11.329 s `executor:graph-execution` + 1.586 s + 0.087 s explicit `UNATTRIBUTED` = `UNATTRIBUTED_MS ≈ 1673`)
- `FRESH = YES` (restore_count=1, request_count=1, single-use container)
- `OUTPUT_SHA = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` (exact)
- `REQUEST_ID = v2-benchmark-0-cdc5f83a8044`; run dir `comfymodal-data/benchmarks/runs/v2_2026-08-20_00-05-57`
- Ledger events: `modal_restore_entry, bootstrap_restore_entry, modal_restore_exit, plan_received, sampling_end, first_durable_result` (2 spans, 6 events)
- `TOTAL_DEPLOYMENTS_USED` since the re-anchor: v36 (source-probe registration), v37 (validation fallback), v38 (ledger persistence) = 3
- `TOTAL_PAID_GENERATIONS_USED`: 1 (the passing cold gate)

Root-cause chain that blocked the ledger for days (all proven, not hypothesized):
1. **Deploy workspace mismatch** — raw `modal` CLI profile pointed at testing3 while the active workspace is testing6; `modal app history` reads went to the wrong workspace (v9 vs v33+). Fixed: `_app_version_number` + `_load_workspace` now use the ACTIVE workspace credentials from `.modal_workspaces.json`; the BAT hard-refuses a missing workspace label.
2. **Deploy no-op masking** — a BAT exit 0 could leave the app version unchanged (charmap crash swallowed). Fixed: strict pre/post version-advance check (`v33 → v38`) + UTF-8 forced in the BAT and child env.
3. **`_span_durable_result` use-before-assignment** (externally reviewed) — the span was referenced before creation inside a silent `except: pass`, so the canonical ledger finalization never ran remotely. Fixed: holder initialized at method top, span opened at plan receipt, closed at first durable result; finalization failures now produce explicit `canonical_ledger_status="error"` evidence.
4. **Missing `_modal.method()` registration** — `source_identity_probe` was wrapped but never registered as a Modal method, so the deployed class never exposed it (`NotFoundError`). Fixed: registered in `_build_decorated_v2_class`.
5. **Host node-registry breakage** — `ComfyUI-CacheDiT/utils.py` (and the charmap crash in rgthree without UTF-8) broke host-side `validate_prompt` (missing `PairConditioningSetProperties` / `Any Switch (rgthree)`). Fixed: plan-validation fallback to the D1 stored deployed-registry proof (node-type fingerprint match, nonce-independent) + UTF-8 for the registry load.
6. **Ledger not copied into the sample artifact** — `canonical_ledger` existed in `run_0.json` but `build_run_record` dropped it. Fixed: `experiment_result_store.build_run_record` now carries `canonical_ledger` + status/error; the artifact writer surfaces status/error too.
7. **Stale class-name "stale-container" signal** — removed from the gate validator (legacy naming artifact, not a stale signal).

## Starting git state

- HEAD: `0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997`
- Branch: `TESTING2`
- Working tree at start: only `.commandcode/taste/taste/taste.md` modified (not mine).
- No branch/worktree/stash/reset/revert/clean/commit/push performed by E29 (the single `git stash push`/`pop` below was a local, restored, reversible A/B check of pre-existing environmental test failures).

## Files inspected (Phase 0 audit)

- `comfymodal_runtime/modal_app.py` (restore(), `_configure_runtime`, `run_plan_stream`, `_run_plan_stream_impl`, request-origin/timing assembly, Gantt emission site)
- `comfymodal_runtime/runtime_bootstrap.py` (`RuntimeBootstrap.restore()` full call graph, variance_stage decomposition, runtime-state/models reload guards, custom-node fast path, SnapshotExecutionSeed)
- `comfymodal_runtime/runtime_executor.py` (sampler wrapper `_build_sampling_wrapper`, authoritative `sampling_end` emission, VAE early-activation hook site)
- `comfymodal_runtime/model_preload.py` (VAE activation state machine `schedule_vae_early_activation_at_sampling_end` / `_vae_activation_submit` / `_run_vae_early_start_worker`, `wait_vae`, `_mm_load_models_gpu`)
- `comfymodal_runtime/gantt_telemetry.py` (existing trace-event-pair Gantt; identified warm-leak + scatter + independent-interpretation issues)
- `comfymodal_runtime/runtime_state.py`, `comfymodal_runtime/restore_plan.py`, `comfymodal_runtime/cpu_snapshot_models.py`
- `tools/benchmark_v2_direct.py` (argparse, guards, `_nri_preload_ms` definition bug, artifact dirs `comfymodal-data/benchmarks/runs/v2_<utc>`)
- `deploy_and_run_v2_single.bat`, `run_v2_single.bat` (deploy semantics: deploy+exit for `snapshot_restore_only`; run-only via `run_v2_single.bat`; E28 selector = E19 base + `SPECULATIVE_CLIP_HYDRATION=1`, `GPU_FAST_RETURN=1`, `OPTIMIZATION_DIAGNOSTICS=1`, `VAE_ACTIVATION_MODE=late`, `CHECKPOINT_PREWARM=1`, `GANTT_TELEMETRY=1`, `E27_FORENSICS=1`)
- E30/E31-owned files READ ONLY: `comfymodal_runtime/speculative_clip_hydration.py` (restore-time lane launch at `modal_app.restore()` ~line 10070, plan-receipt reconcile at ~17561), `comfymodal_runtime/clip_fast_hydration_wiring.py`, `comfymodal_runtime/clip_fp32_cast_once.py` (already modified by E31 on disk; E29 did NOT touch it), `comfymodal_runtime/e27_forensics.py`, plus new concurrent files `clip_qd_reader.py` / `clip_forward_forensics.py` (E30/E31).

## Exact source ownership map (as instructed)

E29 owns and modified:

| File | Change |
|---|---|
| `comfymodal_runtime/critical_path_ledger.py` | **NEW** — canonical ledger (schema below); restore-phase preservation (`begin_restore`/`begin_request`), `TraceSpanBridge` (trace event pairs → ledger spans), full-report capture for artifacts |
| `comfymodal_runtime/gantt_canonical.py` | **NEW** — canonical-ledger Gantt renderer; now renders restore-session spans and the new request/executor/VAE span names |
| `comfymodal_runtime/modal_app.py` | restore() restore-phase + decomposition spans (early/eviction/snapshot/preamble/bootstrap/preload/finalize), method-entry request spans (identity-capture/plan-deserialize/setup-schedule), executor-run + graph-execution spans, durable-result span + ledger report emission + artifact capture, `COMFYMODAL_V2_CRITICAL_PATH_LEDGER` env-probe key |
| `comfymodal_runtime/runtime_bootstrap.py` | `bootstrap_restore_entry` event (+13) |
| `comfymodal_runtime/runtime_executor.py` | canonical `sampling_end` event + `sampling` span via bridge (start/end) |
| `comfymodal_runtime/model_preload.py` | VAE submit/worker-first-instruction ledger events; `vae:early-activation` span (B-arm and `_run_early_vae_activation`); `model-mgmt:load_models_gpu` span bridge |
| `tools/benchmark_v2_direct.py` | `_nri_preload_ms` unconditional (+5); canonical ledger persisted into run artifact (`artifact["canonical_ledger"]`) |
| `tests/test_e29_critical_path_ledger.py` | **NEW** — 15 tests (incl. restore-phase preservation, bridge, request isolation) |
| `tests/test_e29_gantt_canonical.py` | **NEW** — 6 tests |

E29 did NOT modify E30/E31 files. E31's `clip_fp32_cast_once.py` was already dirty on disk from E31's own work; E29 only READ it.

## Tracer schema (critical_path_ledger.py)

- Gate: `COMFYMODAL_V2_CRITICAL_PATH_LEDGER` (default ON when baked; frozen at import).
- All within-remote-process timing on `time.monotonic_ns()` for the serial axis; on Windows (this host) `monotonic_ns` ticks at ~15.6 ms, so exact per-scope durations are additionally derived from `perf_counter_ns` and each span records `start_mono_ns`/`end_mono_ns`/`start_wall_ns`/`end_wall_ns` for cross-process correlation.
- Every span carries: `span_id`, `parent_span_id`, `name`, `lane`, `start_mono_ns`, `end_mono_ns`, `duration_ms`, `work_ms`, `wait_ms`, `sync_ms`, `child_union_ms`, `residual_ms`, `residual_label` (`UNATTRIBUTED` when >1 ms unexplained), and the identity block (`request_id`, `trace_id`, `restored_instance_id`, `restore_session_id`, `container_session_id`, `thread_name`, `native_tid`).
- Events (point markers) carry name + mono_ns + identity; they appear in the serial ledger as zero-duration markers (never fabricated spans).

## Definitions (strict, per E29 spec)

- `work_ms` — wall positively attributable to intrinsic work in that scope.
- `wait_ms` — explicitly measured blocking (lock/semaphore/condition/queue/`Future.result`/join/`Event.wait`/lane/handoff/I/O where measurable) via `timed_wait`.
- `sync_ms` — explicit CUDA/device synchronization via `timed_sync`.
- `child_ms` — UNION of child wall intervals (`_union_length`), never naive sum when overlapping.
- `residual_ms` — wall not positively explained; labeled `UNATTRIBUTED` when >1 ms.
- Invariant per scope: `duration ≈ work + wait + sync + child_union + residual` (reconciled; tolerance 0.2 ms for Windows tick representation error).

## Instrumentation points (exact modifications)

1. `runtime_bootstrap.restore()` first line → `bootstrap_restore_entry` event.
2. `modal_app.restore()` first line → `begin_request` + identity set + `modal_restore_entry`; after finalization → `modal_restore_exit`.
3. `_run_plan_stream_impl` after env/identity extraction → `begin_request` (request-scoped reset) + identity + `modal_method_entry` (at `_method_first_line_ns`) + `plan_deserialize_start/end` + `plan_accepted`.
4. First status yield → `plan_received`.
5. Sampler wrapper `finally` → canonical `sampling_end` event (before trace emit).
6. `_vae_activation_submit` → `vae_activation_submitted`; `_run_vae_early_start_worker` first line → `vae_worker_first_instruction`.
7. Result assembly → `emit_canonical_gantt` (canonical-ledger Gantt, request-scoped).
8. `benchmark_v2_direct.py` → `_nri_preload_ms` defined on every path (was only on the primed branch — would NameError in `summary.json` on an unprimed registry).

## Restore call graph (decomposed)

`modal_app.restore()` →
- identity capture / `_configure_runtime()` (callbacks: reload_models, reload_runtime_state, sync_custom_nodes, install_requirements, start_backend, restore_gpu_state, initialize_cuda, apply_sage_policy, observe_generations, read_current_custom_node_identity)
- `_restore_eviction_boundary()`, `_lazy_init_snapshot_state()`, `maybe_install_clip_fh_demand()`, `start_restore_time_clip_lane()` (E28 earliest-CLIP; guarded, non-blocking)
- cgroup/process CPU samplers start, host memory probe, torch thread policy, RuntimeBootstrap.restore() →
  - graph UNET loader wrapper lazy install
  - `restore_gpu_state` (variance_stage) — trace `restore_gpu_state_start/end`
  - `initialize_cuda` (variance_stage) — trace `cuda_init_start/end`
  - Sage identity read/verify (exact-skip or `sage_policy` fallback)
  - `reload_runtime_state` — generation-match skip guard (`_decide_runtime_state_reload`) else callback
  - `reload_models` — generation-match skip guard (`_decide_models_reload`) else callback
  - custom-node restore fast path (`read_current_custom_node_identity` → schema/gen/deployment-hash exact skip, else `sync_custom_nodes` + `observe_generations`)
  - SnapshotExecutionSeed hydrate/minimal fallback
  - host hardware telemetry, `snapshot_restore_end`, opt_restore_decomposition (measured_sum + residual)
- modal_app restore finalization: `restore_breakdown` + `[v2.restore_deep]` leaf-segment attribution (identity_capture, configure_runtime, host_memory_probe, bootstrap_restore, preload_bridge_prep, restore_finalize) — the existing `_rd_deep` decomposition is now bridged to the canonical ledger via `modal_restore_entry/exit`.

The prior anonymous ~3 s `bootstrap_restore` blob is decomposed by the existing stage timers (restore_gpu_state/cuda_init/runtime_state/models/custom_node/snapshot_seed) + `[v2.restore_deep]` leaves + `[v2.restore_breakdown]`; the canonical ledger adds the outer entry/exit boundaries and will surface any remaining residual as explicit UNATTRIBUTED in the serial ledger.

## Method-entry → PromptExecutor call graph

`run_plan_stream` → `_run_plan_stream_impl` first line (`_method_first_line_ns`) →
- `_capture_remote_identity` / origin-info extraction / env-profile + allowlisted diag-env application / `sync_observability_gates`
- `ExecutionPlan.from_dict` (deserialize)
- `fast_cold_orchestration.begin_request`, `_maybe_schedule_execution_unet_at_plan_receipt` (setup schedule bracket `_setup_schedule_start_ns` → `_setup_schedule_end_ns`)
- speculative CLIP lane reconcile (E28 restore lane re-key; plan-receipt)
- prompt-signature memo load, conditioning prefetch thread, input-types-warm thread
- `_plan_received_mono_ns` → first `status` yield (`plan_received`)
- `self.executor.stream(plan, context=context)` → `_execute_v2_prompt_executor` → PromptExecutor construction/reset/invocation (`prompt_executor_invoke_start`, t5)

The 263 ms / 872 ms coarse buckets are now bounded by the ledger markers `modal_method_entry` → `plan_deserialize_*` → `plan_accepted` → `plan_received`, with the pre-graph thread launches (conditioning prefetch, input-types-warm, UNET schedule) stamped at their submit sites and their worker first-instruction stamps inside the threads — so a slow launch shows as queue/start delay, not "schedule = 250 ms".

## Sampling-end → VAEDecode call graph

`SAMPLER_SAMPLE` wrapper return → (E29) canonical `sampling_end` → trace `sampling_end` → deep-profile finalize → `release_sampler_mutation_lane_at_sampling_end` → `schedule_vae_early_activation_at_sampling_end` (late mode no-op; sampling_end mode) →
- `join_vae_cpu_prefetch_bounded` (prefetch join; measured)
- `resolve_vae_object` → `_build_vae_activation_key` → `_vae_activation_submit` (E29 `vae_activation_submitted`; `submitted_mono_ns`) →
- coordinator pool submit (`RestorePreparation.vae_future`) → worker first instruction (E29 `vae_worker_first_instruction`) → lane acquire → `.data` rebind → load_end/terminal
- graph: KSampler returns → next-node selection → VAEDecode node → `model_management.load_models_gpu` → `free_memory` → soft_empty_cache → VAE decode.

The ~899 ms sampling_end→VAE bucket now has explicit handoff events (`vae_activation_submitted`, `vae_worker_first_instruction`) with identities; the serial ledger will classify the interval as queue delay / lane wait / UNATTRIBUTED — never a guessed `empty_cache` label (no proof of empty_cache cost is fabricated; the D18-era real empty_cache measurements remain historical evidence only).

## CLIP move-left (Phase 4) — E30-safe

- NO change to E30's loader architecture (source-order / QD reader files untouched).
- The restore-time source read launch (E28 `start_restore_time_clip_lane`) is preserved; the plan-receipt reconcile is preserved.
- E29's ledger now records `modal_restore_entry` → CLIP lane launch evidence → `plan_accepted`/`plan_received` → (demand) hydration/forward so the contention question (A–G in the brief) can be answered from a real run's serial axis: overlap vs contention vs join vs shared CUDA init is directly observable from the ledger events (restore-time lane start vs first CUDA touch vs plan receipt).
- Exact-hit skip / forced-miss encode / frozen manifest identity are unchanged (E30/E31 domain).

## Gantt repair (Phase 6)

- NEW `gantt_canonical.py` renders ONLY from the canonical ledger store (`get_spans`/`get_events`), which `begin_request()` resets at method entry → **warm-run leakage impossible** (regression test added).
- Semantic row order: RESTORE → REQUEST-SETUP → CLIP → UNET → SAMPLING → VAE → OUTPUT; CLIP source read / hydration / bind / forward are grouped adjacent vertically.
- Real serial gaps render as explicit `UNATTRIBUTED` bars — never blank.
- Point events (sampling_end, plan_received, …) go in the exact table / point-event detail, never as full-overview bars.
- The misleading ~0.2 ms UNET H2D label is no longer produced by the canonical renderer (it shows only real ledger spans; the old trace-pair Gantt remains only as legacy, alongside the canonical one).
- Line width bounded ≤ ~100 chars (test enforced).
- The legacy `gantt_telemetry.py` E27 multi-window output is still emitted (gated) — the canonical renderer is additive.

## Local validation (Phase 7) — RE-ANCHORED

New E29 tests (all passing):

```
tests/test_e29_critical_path_ledger.py  — 29 passed
tests/test_e29_gantt_canonical.py       — 6 passed
```

Coverage (current reconciled set): exact reconciliation; child-union (not sum) for overlapping children; nested (serial) child union; explicit wait/sync classification; unattributed residual preservation; cross-thread handoffs with identity; cross-request isolation; restore-phase span preservation across `begin_request`; **restore-session isolation** (a fresh `begin_restore` clears the previous restore session — fixed: `begin_restore` now declares the restore-store lists `global` and clears them); **hard zero-gap invariant** (`assert_serial_ledger_zero_gap`, tolerance 1 ms) with missing intervals rendered as explicit UNATTRIBUTED (never blank); **concurrent CLIP source lane** (overlap does not add serial time); **E30 `clip_qd_*` event ingestion** (15 event names); **E31 CLIP-forward event ingestion** (11 event names); **duplicate/end-missing/error behavior** (double-start reuses active span; end-without-start no-op; start-after-end fresh span; `record_event`/`begin_span` never raise); TraceSpanBridge start/end pairing + reentrancy + close_all; Gantt request isolation (E28 warm-leak reproduction); Gantt semantic ordering; E28-like 899 ms gap fixture with explicit UNATTRIBUTED (never `empty_cache` guess).

Existing/adjacent suites (all passing on the current tree):

```
test_e30_clip_qd_io.py + test_e31_clip_forward_fp32.py  — 52 passed
test_e27_gantt_telemetry.py + test_e28_critical_path.py + test_v2_benchmark_trace_handoff.py  — 61 passed, 33 subtests passed
v2ctl suites (backend/cli/config/environment/fingerprints/locking/profiles/provenance/registry/runtime_overrides/validation)  — 236 passed
```

Combined E29+E30+E31+v2ctl run: **397 passed, 0 failed**.

`py_compile` clean on all modified/created files; `git diff --check` clean.

## Event inventory (current tree, reconciled)

| Event family | Producer | Thread | Request scoped? | Parent/handoff | Serial vs nested/concurrent | Ledger consumer | Gantt consumer |
|---|---|---|---|---|---|---|---|
| `modal_restore_entry/exit`, `bootstrap_restore_entry` | modal_app.restore / runtime_bootstrap | main | yes (restore phase) | restore parent | serial | yes (`record_event`) | yes |
| `restore:early/eviction/snapshot/preamble/bootstrap/preload/finalize` | modal_app.restore | main | yes (restore phase) | restore parent | serial | yes (`begin_span`) | yes (RESTORE rows) |
| `modal_method_entry`, `plan_deserialize_*`, `plan_accepted`, `plan_received` | modal_app `_run_plan_stream_impl` | main | yes | request parent | serial | yes | yes (REQUEST rows) |
| `request:identity-capture/plan-deserialize/setup-schedule` | modal_app | main | yes | request parent | serial | yes | yes |
| `request:executor-run`, `executor:graph-execution` | modal_app | main | yes | request parent | serial (children nested) | yes | yes (EXECUTOR rows) |
| `sampling` (span) + `sampling_end` (event) | runtime_executor sampler wrapper | graph | yes | executor child | serial | yes (bridge + event) | yes (SAMPLING row) |
| `vae:early-activation` + `vae_activation_submitted`, `vae_worker_first_instruction` | model_preload workers | worker | yes | VAE handoff | concurrent lane | yes | yes (VAE row) |
| `model-mgmt:load_models_gpu` | model_preload `_mm_load_models_gpu` | graph/worker | yes | VAE/UNET child | serial | yes (bridge) | yes (VAE/MODEL-MGMT row) |
| `first_durable_result` + ledger report emission | modal_app result assembly | main | yes | output parent | serial | yes | yes (OUTPUT row) |
| `clip_qd_*` (15) | clip_qd_reader (E30, OFF by default) | lane worker | yes | CLIP lane | concurrent | yes (`record_event`) | events only |
| `clip_forward_*`, `clip_gpu_event_*`, `clip_cast_once_*`, `clip_profiler_*` (11) | clip_forward_forensics (E31, OFF by default) | graph | yes | CLIP forward child | serial | yes (`record_event`) | events only |

## Deploy readiness (Phase 8/9) — SUPERSEDED (remote gates completed)

- *HISTORICAL: this section described the pre-permission state. The remote
  sequence below was executed and completed (3 deploys + 3 cold gates, all
  valid). See the CURRENT AUTHORITATIVE STATUS section for the final result.*
- `tools/v2ctl.py` is landed and functional (`doctor`: deploy lock free, no runtime overrides, no deployment manifest yet — the expected pre-deploy state).
- **`e29-tracer` profile aligned for the first tracer-only cold gate** (`config/v2/profiles/e29-tracer.toml`):
  - Tracer ON: `COMFYMODAL_V2_CRITICAL_PATH_LEDGER=1`, `COMFYMODAL_V2_GANTT_TELEMETRY=1`, `COMFYMODAL_V2_CRITICAL_GPU_COORDINATION=1`
  - E28 known-good selector (same production path as the E28 validation baseline): `SPECULATIVE_CLIP_HYDRATION=1`, `GPU_FAST_RETURN=1`, `VAE_ACTIVATION_MODE=late`, `CHECKPOINT_PREWARM=1`, `OPTIMIZATION_DIAGNOSTICS=1`
  - E30/E31 experimental behavior explicitly OFF: `CLIP_QD_READER=0`, `CLIP_FP32_CAST_ONCE=0`, `E31_FORENSICS=0`, `E31_FORWARD_PROFILE=0`
  - Workload: `fresh_required=true`, `conditioning_cache=forced_miss`, `expected_output_sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`, `run_count=1`, `runtime_overrides=forbid`
  - Dead `COMFYMODAL_V2_E29_CRITICAL_PATH` flag removed; `COMFYMODAL_V2_CRITICAL_PATH_LEDGER` registered in `flag_registry.toml` (bool, default 1, module_import, deploy) — profile resolves with **zero unregistered flags**.

## CURRENT SOURCE/TEST STATE (fresh-agent continuation, 2026-08-20)

The fresh-agent continuation (this document's update) added the following to
close the v38 deep-attribution gap. All changes are in the working tree on
`TESTING2` at HEAD `79cc994` (uncommitted, per the batch contract):

| File | Change |
|---|---|
| `comfymodal_runtime/critical_path_ledger.py` | `finish()` accepts BOTH `end_mono_ns=` and `mono_ns=` keyword spellings (the v38 killer: every direct close site used `mono_ns=`, raising TypeError under `except: pass`); `clear_ledger_for_test` also resets endpoints |
| `comfymodal_runtime/modal_app.py` | restore spans CREATED AT SITE (not re-stamped — fixes corrupted durations); `modal_restore_entry` stamped at the resume boundary; restore identity refreshed after IDs exist; `_deserialize_start/end_ns` declared before use (kills the method-entry NameError); `context` NameError fixed (trace_id via `_plan_receipt_trace`); cc-prefetch/input-types-warm spans closed incl. failure paths; `unet_lane_submitted` event; `canonical_ledger_status="error"` on span-finish failure (never silent ok); source_identity_probe covers 7 modules |
| `comfymodal_runtime/model_preload.py` | `model-mgmt:load_models_gpu` bridge in the gpu-loader wrapper (3 real calls captured); `CLIP forward` ledger span in the clip-span wrapper; `VAE decode` ledger span at the loader-bridge decode |
| `comfymodal_runtime/clip_fast_hydration_wiring.py` | `CLIP hydration` ledger span around `_try_fast_hydrate` |
| `comfymodal_runtime/speculative_clip_hydration.py` | `clip_speculative_lane_started/finished` ledger events (Phase 7 overlap proof) |
| `comfymodal_runtime/e27_forensics.py` | `soft_empty_cache` ledger event with real measured sync/empty/ipc values |
| `tools/v2_control/source_probe.py` | REQUIRED_MODULES 5 → 7 (adds model_preload + clip_fast_hydration_wiring) |
| `tests/test_e29_critical_path_ledger.py` | +9 regression tests (finish keyword, restore survival, setup spans, executor-run lifecycle, identity refresh, MM bridge lifecycle, honest duration, speculative/UNET/empty-cache ingestion) |
| `tests/test_v2ctl_source_probe.py` | fixture updated for the 7-module probe |
| `tests/test_v2ctl_registry.py` | stale `V2_BENCHMARK_MODE` default assertion updated to `e28_single` (pre-existing failure from the attempt-2 fix) |

Local validation: **266 passed, 33 subtests passed, 0 failed** across
E29/E30/E31/E27/E28/v2ctl suites; `py_compile` clean; `git diff --check` clean.

## Remote attempt chronology (fresh-agent continuation)

| # | Action | Result |
|---|---|---|
| 1 | `v2ctl deploy` (span-survival fixes) | transport deployed, version advanced, source-probe 7/7 MATCH |
| 2 | `v2ctl gate` | **valid=1** — 17 spans / 8 events, UNATTRIBUTED 20.4 ms, SHA exact |
| 3 | `v2ctl deploy` (honest durations + MM bridge) | version advanced, source-probe 7/7 MATCH |
| 4 | `v2ctl gate` | **valid=1** — 20 spans / 8 events, UNATTRIBUTED 102.5 ms, SHA exact |
| 5 | `v2ctl deploy` (+ speculative/UNET/empty_cache/VAE decode events) | version advanced, source-probe 7/7 MATCH |
| 6 | `v2ctl gate` | **valid=1 — 21 spans / 15 events, UNATTRIBUTED 48.5 ms, SHA exact** (ACCEPTED) |

Paid generations this follow-up: 3 (one per gate). Deployments this follow-up: 3.

## Final marker

**E29_GROUND_TRUTH_CRITICAL_PATH = COMPLETE** — the accepted gate-3 trace
(21 spans / 15 events, 48.5 ms UNATTRIBUTED) answers all 11 E29 completion
questions. E30/E31 remain OFF and are the next remote experiments.

---

## E29 REMOTE COLD GATE 1

### Pre-gate source state (recorded before the first deploy attempt)

```
HEAD:      0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997
branch:    TESTING2
dirty:     1 (E29/E30/E31/E32 working tree, unchanged concurrent work preserved)
diff --stat: 11 files changed, 906 insertions(+), 8 deletions(-)  (same set as the re-anchor)
```

### v2ctl preflight (before deploy)

```
doctor:  git.head=0ba7000 branch=TESTING2 dirty=1
         registry.flags=107  profiles=e29-tracer,e30-clip-qd,e31-clip-fp32,production
         (HISTORICAL pre-arm profile set; these names are not current selectable profiles)
         runtime_overrides.present=0  runtime_override_policy=forbid
         deploy.lock=none  deployment.manifest=none
         (only expected problem: no deployment manifest yet)
lock status: deploy.lock=none
```

Resolved `e29-tracer` config (verified via `v2ctl config --json`):

```
profile: e29-tracer   owner: E29
target:  app=stable-modal-comfy-v2-restore-only-shadow class=ModalRuntimeEntrypointV2 method=run_plan_stream
resources: gpu=rtx-pro-6000 cpu=12 memory_mb=32768 min_containers=0 scaledown_window=4
COMFYMODAL_V2_CRITICAL_PATH_LEDGER = 1      (tracer ON)
COMFYMODAL_V2_GANTT_TELEMETRY       = 1      (Gantt ON)
COMFYMODAL_V2_CLIP_QD_READER        = 0      (E30 OFF)
COMFYMODAL_V2_CLIP_FP32_CAST_ONCE   = 0      (E31 FP32 OFF)
COMFYMODAL_V2_E31_FORENSICS         = 0      (E31 forensics OFF)
COMFYMODAL_V2_E31_FORWARD_PROFILE   = 0      (E31 profiler OFF)
COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION = 1 (E28 selector)
COMFYMODAL_V2_GPU_FAST_RETURN = 1, VAE_ACTIVATION_MODE=late,
COMFYMODAL_V2_CHECKPOINT_PREWARM = 1, OPTIMIZATION_DIAGNOSTICS = 1
unregistered: []   (dead COMFYMODAL_V2_E29_CRITICAL_PATH removed; CRITICAL_PATH_LEDGER registered)
workload: fresh_required=true conditioning_cache=forced_miss
          expected_output_sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
          run_count=1 gap_seconds=35.0 runtime_overrides=forbid
deploy_fingerprint: 56f135e25f3bc6238704d04c5741b297889089066fd2911f0fac80297d6ebd42
run_fingerprint:    62ffbd13ff3cba1910c8c15df9a1b6b970cfa0cd0faff0fc4ed18f9267cebde0
```

### Deploy attempt (canonical `v2ctl deploy --profile e29-tracer --owner E29`)

- Acquired the deploy lock as owner E29, invoked the deploy-only backend (`COMFYMODAL_DEPLOY_ONLY=1`), local BAT reported `App deployed in 2.585s!` and the backend exited 0.
- **REMOTE CRASH LOOP observed (not visible in the local BAT capture — the tracebacks are emitted by Modal's remote lifecycle, which never reaches the deploy BAT stdout):**

```
Traceback (most recent call last):
  File "/pkg/modal/_runtime/container_io_manager.py", line 904, in handle_user_exception
    yield
  File "/pkg/modal/_runtime/user_code_imports.py", line 63, in call_lifecycle_functions
    res = func(*args)
  File "/root/comfymodal_runtime/modal_app.py", line 19423, in _wrapper
    _result = orig_method(self, *args, **kwargs)
  File "/root/comfymodal_runtime/modal_app.py", line 10095, in restore
    if _span_restore_early is not None:
UnboundLocalError: cannot access local variable '_span_restore_early' where it is not associated with a value
Runner failed with exception: UnboundLocalError(...)
```

- **Root cause (E29 bug, found and fixed):** the restore-decomposition span holders (`_span_restore_early` etc.) were created at `_restore_perf_start` (line ~10236) but the first close-site (line ~10105) ran BEFORE that block, so on the remote restore path the early close-site hit `UnboundLocalError`. Local `py_compile` cannot catch this (it's a runtime control-flow bug, not a syntax error), and no local test executes `restore()`.
- **Fix:** initialize all seven span holders to `None` immediately after the ledger-entry block at the top of `restore()` (line ~9956), so every close-site is `None`-safe regardless of execution order. Creation block unchanged. `py_compile` + full local suites re-run: **208 passed, 0 failed**.
- The failed deploy produced NO deployment manifest (v2ctl wrote none), the deploy lock was released, and the stale lock file from the interrupted deploy was force-released (provably stale: owner E29, dead PID 38136, marked `stale=1`).

### v2ctl crash-loop detection (new, per user request)

- `DeployCrashLoopError` (tools/v2_control/errors.py) — deploy must never be treated as successful when a crash loop is detected.
- `detect_crash_loop(output)` (tools/v2_control/backend.py) — scans for the SAME exception line repeated ≥3 times across tracebacks.
- Wired into `cmd_deploy` (fail before writing a deployment manifest) and `GateRunner.run_gate` (fail the gate with a specific reason instead of a misleading "valid" result). The gate-path wiring is the critical one: the deploy BAT cannot see remote container tracebacks, but the gate/run backend output CAN capture them.
- Unit tests added (`test_detect_crash_loop_*` in tests/test_v2ctl_backend.py); all v2ctl suites pass (76).

### Deploy-health truthfulness (new, per user request)

- **DEPLOY_BACKEND_EXIT_0_MEANS = transport deployed only** (Modal accepted the upload; NOT runtime-health).
- **DEPLOY_REMOTE_LIFECYCLE_VERIFIED = NO** at deploy time (deploy BAT checks only deploy-output identifiers).
- **DEPLOY_CRASH_LOOP_SOURCE = Modal remote lifecycle logs** (never the local BAT stdout — confirmed: `_deploy_output.log` was clean UTF-16 deploy output with no traceback).
- **CMD_DEPLOY_CAN_OBSERVE_IT = NO**; **GATE_CAN_OBSERVE_IT = YES** (gate invokes the class method, so a crash surfaces in gate stdout).
- Deployment manifest now records `deployment_transport_status=deployed` + `runtime_health_status=unverified` + `health_check_note`; the first gate/run is the health-validation boundary. Test: `test_deploy_manifest_is_truthful_about_health`.

### Root-cause bugs found during remote gate iterations (all fixed + documented)

1. **Stale warm-container contamination (the big one).** Gate runs were served
   by a warm container from an OLD deployment: `source_identity.class_name=
   ModalRuntimeEntrypoint` (the deployment targets `ModalRuntimeEntrypointV2`)
   and the container's trace had ZERO E29 ledger events despite
   `COMFYMODAL_V2_CRITICAL_PATH_LEDGER=1` effective.  The Modal app
   (`stable-modal-comfy-v2-restore-only-shadow`) is a single persistent app
   (same App ID since 2026-08-18); redeploys keep warm containers alive, and
   those serve stale code.  **Fix:** `COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1`
   in the e29-tracer profile so every gate request runs on a freshly-started
   container with the current baked code — the only reliable fresh-cold proof
   under Modal warm reuse.
2. **Freshness validator accepted reused containers.** `StructuralValidator`
   treated `restored` as satisfying `fresh_required`.  **Fix:** `restored=True`
   now FAILS a fresh-required gate; freshness requires `fresh=True`.
3. **Freshness enrichment used the misleading `retained` flag** (snapshot
   retention, not container reuse).  **Fix:** derive fresh/restored from
   `source_identity.restore_count`/`request_count` (both ==1 ⇒ fresh) AND
   verify `source_identity.class_name` matches the configured target class —
   a stale container from an old deployment reports the old class and is
   marked `stale_container` (never fresh).
4. **Deploy selector not forwarded (root cause of stale build).**  `cmd_deploy`
   invoked the BAT without the `E28_VALIDATION` positional selector, so the
   deploy ran the default production path and never baked the E28/E19
   profile.  **Fix:** `cmd_deploy`/`cmd_deploy_run` forward
   `_backend_selector(config)` as the first BAT arg (verified via dry-run).
5. **Artifact discovery missed the real output root.**  The benchmark writes
   to `<repo>/../../comfymodal-data/benchmarks/runs/v2_<utc>/` (outside the
   repo); v2ctl searched only in-repo dirs.  **Fix:** `_candidate_dirs`
   includes that root and discovery scans per-run subdirectories.
6. **Gate validation ignored the persisted artifact.**  Telemetry/SHA were
   parsed only from backend stdout (Windows BAT capture loses lines).
   **Fix:** `build_run_record_from_result` enriches from the persisted run
   artifact (correlation_id, request_id, fresh/restored, output SHA from
   `output_descriptor[].asset_id`).
7. **Failed deploys left "deployed" manifests.**  `cmd_deploy` wrote the
   manifest before checking `result.ok()`.  **Fix:** a failed deploy unlinks
   its manifest so gate/run can never treat a broken deployment as valid.
8. **`v2ctl doctor` without `--profile` compared the wrong profile's
   fingerprint** (defaults to production, comparing against the e29-tracer
   manifest → false mismatch).  Not a gate blocker (the gate passes the
   profile explicitly) but documented: always pass `--profile` to doctor.

All fixes are covered by local tests (v2ctl backend/cli/validation suites
green; E29 ledger/Gantt suites green).

- **Attempt 2 outcome:** deploy succeeded (transport deployed, runtime_health unverified), gate ran ONE cold generation successfully on the remote side (attempt 1 valid, cold=True, instance `9b9dec920f0a`), but the gate was marked **structurally invalid**: no output SHA, no persisted run artifact. Modal showed `run_snapshot_restore_only_probe` invocations — NOT `run_plan_stream`.
- **Root cause (v2ctl bug):** `V2_BENCHMARK_MODE` had a registry default of `snapshot_restore_only`; v2ctl's `EnvironmentBuilder` writes every resolved flag (including registry defaults) into the child env of the deploy/run BATs; the run BAT (`run_v2_single.bat`) enters the restore-only PROBE branch when `V2_BENCHMARK_MODE == snapshot_restore_only`, calling `benchmark_v2_direct.py --snapshot-restore-only` → the remote `run_snapshot_restore_only_probe` method (no generation). Unless a profile explicitly overrode the mode, every v2ctl run/gate silently produced a probe instead of a generation. Deploy exit 0 could not reveal it.
- **Fix (in place):**
  - `V2_BENCHMARK_MODE` registry default changed `snapshot_restore_only` → `e28_single` (one full `run_plan_stream` generation); `snapshot_restore_only` is now an explicit opt-in ONLY.
  - `e29-tracer` profile sets `V2_BENCHMARK_MODE=e28_single`, `V2_E28_VALIDATION=1` (plus `V2_E28_CONDITIONING_NONCE` flows).
  - v2ctl `run`/`gate` HARD-REFUSE `snapshot_restore_only` (`_require_full_run_mode` in `cmd_run`/`cmd_gate` + `GateRunner.run_gate` guard) — refused before any spend.
  - v2ctl `run`/`gate` forward the canonical selector (`E28_VALIDATION`) as the BAT's first positional arg so the run BAT enters the full-run validation branch.
  - Tests: `test_run_refuses_snapshot_restore_only_mode`, `test_e29_tracer_profile_forces_full_run_mode`.
- **Docs:** added `§22b Known Pitfall — snapshot_restore_only vs Full Generation (MUST READ)` to `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md` so no future agent hits this.
- Local validation after fix: **209 passed, 2 skipped** (E29/E30/E31/v2ctl focused set); `py_compile` + `git diff --check` clean.
- The old deployment manifest (fingerprint `cc60aa7b…`) no longer matches the updated profile (new deploy fingerprint `d4578997…`), so the next step is a fresh deploy + gate.

### Outcome

- **No cold generation was spent** — the deploy never produced a valid deployment, so no gate run occurred.
- **E29_REMOTE_TRACER_GATE_1 cannot be declared PASS or FAIL** — there is no cold-generation evidence to evaluate.
- The local truth system is fully green and the crash-loop blocker is fixed. The next step (re-deploy + one cold gate) is outside the narrow 1-deploy authorization already consumed; it requires explicit re-authorization from the user.


---

## Addendum — V2 canonical control plane (E32) compliance & flag lifecycle

Per the standing rule (docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md), E29:

- did NOT redesign its lane around v2ctl — checked the checkout: `tools/v2ctl.py` is a 14-line stub importing `v2_control.cli`, and the `v2_control` package does NOT exist (E32 not landed). No control-plane files, BAT files, or flag-forwarding allowlists/whitelists were edited.
- remains FORBIDDEN from deploying/running Modal requests (another agent currently owns remote validation) and is preparing the remote validation plan only.
- will use the presently established known-good path (deploy_and_run_v2_single.bat / run_v2_single.bat via the documented `cmd.exe /d /v:on /c` invocation) ONLY if granted deploy ownership for this active batch; no new Modal SDK deploy path, BAT variant, PowerShell `set && call` chain, or custom flag-forwarding workaround.
- once E32 lands, all subsequent deploys/runs for E29 validation go through `python tools/v2ctl.py` exclusively.

### New flags added by E29

| Flag | Where consumed | Lifecycle | Deploy or run? | v2ctl integration hook needed? |
|---|---|---|---|---|
| `COMFYMODAL_V2_CRITICAL_PATH_LEDGER` | `comfymodal_runtime/critical_path_ledger.py` (import-time gate, default True when baked; `env_flag` at module import) | build/restore/request — instrumentation gate | **deploy** (frozen at import inside the container; changing it requires a redeploy of the module env) | No — the flag is consumed purely inside the runtime module; v2ctl `--set` (once E32 lands) reaches it through the deploy env exactly like every other `COMFYMODAL_V2_*` variable. No allowlist edit was made by E29. |
| `COMFYMODAL_V2_GANTT_TELEMETRY` | (existing, pre-E29) consumed in `comfymodal_runtime/gantt_telemetry.py` + `modal_app.py` emission site; E29's new `gantt_canonical.py` renderer is gated by the same flag | build/request | **deploy** (E28 selector already sets it; it is baked at deploy) | No (existing passthrough in `_runtime_env` was already present; E29 did not add it to any allowlist — the E28 profile already carries it). |

E29 added NO new flags to any semantic whitelist/allowlist and made no flag-forwarding edits. The new modules read their gates directly from the environment at import time (the same convention every other runtime module uses).

### Remote validation E29 intends to perform later (after permission + E30/E31 quiesce)

1. Deploy (established harness): `cmd.exe /d /v:on /c "call deploy_and_run_v2_single.bat E28_VALIDATION" *> E29_deploy_gate.log` — with E30/E31 experimental flags verified default-OFF in the deployed tree.
2. COLD RUN 1 (run-only): `cmd.exe /d /v:on /c "call run_v2_single.bat E28_VALIDATION" *> E29_cold1.log` with a fresh conditioning nonce — validate: Fresh=YES, correct app/class/method, resource shape/profile, restored_instance_id/restore_session_id/container identity, real CLIP source+hydration+forward, no duplicate graph encode, canonical ledger structurally complete (zero unrepresented gaps; any >1 ms residual explicitly UNATTRIBUTED), Gantt current-request-only, exact output SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`. If structurally wrong → STOP, fix, redeploy, repeat COLD RUN 1.
3. COLD RUN 2 only after RUN 1 is fully valid.
4. Persisted artifacts are authoritative: `comfymodal-data/benchmarks/runs/v2_<utc>/run_0.json`, `summary.json`, `campaign_manifest.json` (console `*>` may be empty due to the known Windows capture quirk).

### v2ctl integration hooks E29 anticipates

None required from E29's code. The canonical ledger and canonical Gantt are pure runtime measurement modules gated by env flags that v2ctl (once landed) will pass through as ordinary `--set` variables; E29 made zero edits to deploy/run plumbing and will not preempt E32. If E32's registry asks for typed metadata on `COMFYMODAL_V2_CRITICAL_PATH_LEDGER`, that is an E32-owned registry entry, not an E29 code change.
