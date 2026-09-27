# V2 Batch B2 — Snapshot Capture Hygiene + Stage-13 Decomposition

Date: 2026-08-14. Working tree, no commit, no deploy, no Modal runs. Parallel Batch-B lanes active; write ownership respected (`modal_app.py`, `snapshot_build_manifest.py`, new hygiene/breakdown helpers, dedicated tests only).

---

## 1. Snapshot boundary

- The snapshot is captured by Modal immediately after `startup()` (`@modal.enter(snap=True)`, applied at `modal_app.py:17200-17204`) returns. The capture boundary in the working tree is the `return {...}` at `modal_app.py:9038-9045` (the block previously at 9018-9025; shifted +20 by the hygiene insert).
- The hygiene pass runs **inside `startup()`**, between the restore-memory-arm freeze block (`except Exception: pass`, `:8995-8996`) and `_startup_return_wall_ns = time.time_ns()` (`:9018`) — i.e. immediately before the capture boundary, after model eviction (`_evict_snapshot_models`, `:8923-8960`), snapshot manifest (`:8971-9005`), and pool close.
- Gate: `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE` — `0` = disabled (default, production behavior byte-identical), `1` = enabled (shadow validation). Read with the repo's shared truthy-set semantics (`{"1","true","yes","on"}` after trim+lower; absent → off), same pattern as every other V2 flag.
- `gc.collect()` and `malloc_trim(0)` run **only when the flag is enabled**; when disabled, no GC call, no trim, no event, no print — behavior unchanged.

## 2. Hygiene implementation

New module `comfymodal_runtime/snapshot_capture_hygiene.py` (208 lines, never raises):

1. Measure **before**: `/proc/self/status` (VmRSS, RssAnon, RssFile, VmSize, VmData — kB ints) + cgroup memory.current (v2 `/sys/fs/cgroup/memory.current`, v1 `usage_in_bytes` fallback).
2. `gc_collected = gc.collect()` (return value = objects collected).
3. `malloc_trim(0)` via the repo's existing safe ctypes pattern (`ctypes.CDLL("libc.so.6", use_errno=True)`, `argtypes=[c_size_t]`, `restype=c_int`; `except (AttributeError, OSError)` → `unsupported`, `except Exception` → `error`, both → `(False, None)`, continue normally). No new dependency. On non-Linux (e.g. Windows dev) `CDLL("libc.so.6")` raises OSError → nonfatal `unavailable`.
4. Measure **after** (same sources).
5. Build + store the `snapshot_capture_hygiene` event, print a compact `[v2.snapshot_capture_hygiene] ...` line (flushed), return the dict.

The event is also merged into `_restore_timing["snapshot_capture_hygiene"]` when the flag is on, so the startup return payload carries it to the host. Deltas are `before − after` (positive = bytes returned/freed). No model/state mutation beyond allocator reclaim (GC only collects unreachable objects; no cache clears, no weakref breaks).

**Explicitly NOT implemented** (out of scope): `posix_fadvise(DONTNEED)`, model eviction changes, CLIP/VAE removal, import restructuring, pre-touch, page traversal.

## 3. Memory sources available

| Source | Fields | Availability |
|---|---|---|
| `/proc/self/status` | VmRSS, RssAnon, RssFile, VmSize, VmData, VmHWM, VmStk, Threads | Hard capture source; RssAnon/RssFile are kernel 4.5+ fields, expected present in the sandbox but treated as nullable |
| `/proc/self/smaps_rollup` | Rss/Pss/Private_*/Shared_*/Anonymous | **Known unavailable under gVisor** (documented in `V2_SNAPSHOT_ARCHITECTURE_AND_WORKING_SET_RESEARCH.md` §Evidence) — recorded as `None`, never fabricated |
| `/proc/self/maps` | total/anonymous/file-backed mapping counts + top paths by count | Present; mapping **counts**, not bytes |
| cgroup `memory.current` (v2) / `usage_in_bytes` (v1) | current bytes | Readable in some runs only (`FAST_DISK…:121` observed both) — `None` when absent |
| `/proc/self/task`, `/proc/self/fd`, `/proc/<pid>/stat` | thread/fd/child counts | Existing manifest sources |
| `resource.getrusage().ru_maxrss` | maxrss ceiling | Via existing `_report_host_memory` (unchanged) |
| `snapshot_build_manifest` | per-role retained-model `storage_bytes`, module counts, GC object summary | Existing; extended this batch (§5) |

## 4. Measurement limitations

- **Actual pages-file bytes remain unmeasured** (no Modal API; `smaps_rollup` unavailable in-sandbox). This batch adds hard capture-composition evidence, not forensic accounting.
- **RSS ≠ pages-file bytes.** The VmRSS before/after delta is a *lower bound* on anonymous pages returned by the pass; interior fragmentation and file-page residue are not visible.
- **Anonymous/file-backed byte split is a proxy**: RssAnon/RssFile from `/proc/self/status` are process-accounting views; gVisor's MemoryFile serialization selection (private vs file-backed) is inferred, not proven.
- Deltas are computed only when both endpoints are ints; unavailable = `None` (serialized as null), **never fabricated zeros**.
- `hygiene_wall_ms` includes both GC and trim; GC cost is allocator-dependent and unmeasured separately (intentional — one bounded pass, one number).

## 5. Snapshot manifest changes

`comfymodal_runtime/snapshot_build_manifest.py` — additive only:

- `_capture_status()` now also parses `RssAnon` → `status.rss_anon`, `RssFile` → `status.rss_file` (kB ints; existing `key.lower()` keys byte-identical).
- New `_capture_cgroup()` → `{"available": bool, "memory_current_bytes": int | None}` (v2 path, v1 fallback, fully guarded); manifest dict gains `"cgroup"`.
- `capture_snapshot_manifest(..., hygiene: dict | None = None)` — when the hygiene event dict is passed, it is stored as `manifest["capture_hygiene"]` (correlates the manifest capture with the hygiene before/after pass).
- Compact `[v2.snapshot_manifest]` line extended with `rss_anon_kb=... rss_file_kb=...` (additive).
- No smaps assumption, no per-page scans, no VMA walk beyond the existing `/proc/self/maps` count pass. `COMFYMODAL_V2_SNAPSHOT_MANIFEST=1` remains the gate (default off).

## 6. Capture event schema

`[v2.snapshot_capture_hygiene]` / `snapshot_capture_hygiene` dict (28 keys; `None` → printed as `unavailable`):

```
enabled                                # 1 when flag on
gc_collected                           # gc.collect() return (objects collected)
malloc_trim_available                  # bool
malloc_trim_result                     # int (libc return) | None
hygiene_wall_ms                        # round((t1-t0)/1e6, 3)
before_rss_kb / after_rss_kb / delta_rss_kb
before_rss_anon_kb / after_rss_anon_kb / delta_rss_anon_kb
before_rss_file_kb / after_rss_file_kb / delta_rss_file_kb
before_vmsize_kb / after_vmsize_kb / delta_vmsize_kb
before_vmdata_kb / after_vmdata_kb / delta_vmdata_kb
cgroup_memory_current_before_bytes / ..._after_bytes / ..._delta_bytes
manifest_status                        # "captured" | "not_captured"
anonymous_measurement_status           # "ok" | "unavailable"
file_backed_measurement_status         # "ok" | "unavailable"
before_mono_ns / after_mono_ns
```

## 7. Stage-13 current path

Stage 13 ("Output encode / descriptor", 236–261 ms baseline; ~247 ms Batch-A RUN 1) is the window `output_collect_start → remote_result_emit` (both same-process monotonic), assembled in `_execute_v2_prompt_executor` (output collection, asset write, descriptor build) and `_run_plan_stream_impl` (trace merge, identity enrichment, raw timestamps/intervals/clock-scopes, critical-path build, full-trace artifact, cgroup report, resource telemetry, GPU allocation, waterfall build/attach, emit stamp). All enrichment is pre-stamp (Stage-13 attributed per the corrected `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` accounting); Stage 14 remains platform transport. This batch adds **decomposition only — no optimization**, no waterfall accounting change, no trace-field removal.

## 8. Stage-13 new timing boundaries

All boundaries are `time.monotonic_ns()` stamps; executor-side stamps ride in `result["_stage13_boundaries"]` (popped from the yielded event after use — never serialized); stream-side stamps are local. Inserted sites (working tree):

| Boundary | Where |
|---|---|
| `output_collect_start_mono_ns` | `_execute_v2_prompt_executor` before `trace.emit("output_collect_start")` (`:13959`) |
| `persist_start_mono_ns` | before `trace.emit("output_persist_start")` (`:14087`) |
| `asset_write_end_mono_ns` | after `await self._persist_output_assets(...)` (`:14095`) |
| `descriptor_end_mono_ns` | **reused** existing `_descriptor_end_mono_ns` (`:14106`) |
| `exec_result_ready_mono_ns` | before `return result` (`:14356-14366` stash) |
| `interval_start_mono_ns` | `_run_plan_stream_impl` before raw-timestamp construction (`:16707`) |
| `interval_end_mono_ns` | after `clock_scopes` block (`:16859`) |
| `resource_start_mono_ns` | before `_resource_tel` summarize (`:16933`) |
| `resource_end_mono_ns` | after `gpu_allocation` (`:16954`) |
| `waterfall_start_mono_ns` | before `build_waterfall` block (`:16955`) |
| `waterfall_end_mono_ns` | after waterfall try/except (`:16990`) |
| `emit_mono_ns` | **reused** existing `data["remote_result_emit_mono_ns"]` from `_stamp_remote_result_emit` |

Children (ms, round 3) and their exact arithmetic:

```
output_collection_ms    = persist_start − output_collect_start
asset_local_write_ms    = asset_write_end − persist_start
descriptor_build_ms     = descriptor_end − asset_write_end
trace_enrichment_ms     = interval_start − exec_result_ready
interval_build_ms       = interval_end − interval_start
resource_enrichment_ms  = resource_end − resource_start
waterfall_build_ms      = waterfall_end − waterfall_start
other_pre_emit_ms       = (exec_result_ready − descriptor_end)
                        + (resource_start − interval_end)
                        + (emit − waterfall_end)
```

Emitted as `data["output_stage13_breakdown"]` in `_run_plan_stream_impl` immediately before the result yield (`:17002-17021`). Raw executor stamps are popped (`data.pop("_stage13_boundaries", None)`) so the envelope is unchanged.

## 9. Accounting proof

`build_stage13_breakdown` (new pure module `comfymodal_runtime/stage13_breakdown.py`) returns `status` (`ok`/`partial`), `boundaries_present`, `stage13_total_ms`, the 8 children, `sum_children_ms`, `reconciliation_ms = stage13_total_ms − sum_children_ms`, `reconciliation_status` (`ok` if `|reconciliation_ms| ≤ 1.0 ms` else `gap`), `children_order`.

Tiling identity (by construction): the 8 children partition `[output_collect_start, emit]` into contiguous spans, so `sum(children) == stage13_total` exactly before rounding (verified by unit tests: ladder fixtures reconcile to ±1.0 ms tolerance, `status=ok`; a deliberately non-monotonic overlapping fixture yields `gap`). Reconciliation is **reported, never enforced** — no behavior change, no waterfall accounting change.

## 10. Tests

New dedicated test files (25 tests, all passing; no Modal runs, no ComfyUI graphs):

- `tests/test_v2_snapshot_capture_hygiene.py` (10): flag off = no event/no GC/no print; flag on calls GC once + trim safely (stubbed); malloc_trim unavailable is nonfatal; null-preserving before/after; no fake zeros; event emitted once per run; no model/state mutation (gc enabled-state, sys.modules, env unchanged); manifest_status param; wall/mono stamps sane.
- `tests/test_v2_stage13_breakdown.py` (8): children order; nonnegative durations; children reconcile parent within tolerance; partial on missing boundaries; input not mutated; negative-diff → None child + partial; tolerance breach → `gap`; JSON-safe.
- `tests/test_v2_snapshot_manifest_hygiene_extensions.py` (7): status parses rss_anon/rss_file; unreadable proc → `{}` no raise; cgroup reader available/unavailable; `capture_hygiene` key; manifest with all helpers stubbed; never raises on unreadable proc; extended print line.

Verification run (local, no Modal): `25 passed` (new) + `52 passed` (adjacent regression: `test_v2_batch_a_g1_terminal_stamps.py`, `test_v2_waterfall_contract.py`).

## 11. Risks

- **GC at capture boundary** (flag-on only): may slow startup by a few ms (allocator-dependent) and could theoretically free objects referenced only by weakref chains — no such pattern exists at the capture point; the pass is after model eviction where GC is already exercised.
- **malloc_trim correctness**: glibc-only; guarded via ctypes with `use_errno`; all failure modes → `unavailable`, pass continues. No dependency added.
- **Measurement honesty**: unavailable sources stay `None`; deltas only with both endpoints int. No fake zeros by construction.
- **Stage-13 stamps**: additive; the only new always-on cost is ~12 monotonic reads + one dict build (<0.1 ms). The `_stage13_boundaries` key is popped before yield, so envelope semantics are unchanged; `descriptor_end_mono_ns`/`output_persist_end` semantics untouched.
- **Concurrent Batch-B lanes**: only owned files were written; `runtime_bootstrap.py`, `model_preload.py`, `runtime_executor.py`, `v2_waterfall.py`, `host_hardware_telemetry.py`, harness tools untouched. Line numbers cited may drift with later batches.
- **Batch-A preservation**: G1 plan-receipt scheduling, terminal cleanup stamps, models reload guard, G3 rows, host telemetry, PNG level 1, descriptor-only result, deferred persistence, CLIP+VAE snapshot, UNET excluded — none modified.

## 12. Integrated-run measurement contract

Shadow validation deployment (next batch, not this task): `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE=1` + `COMFYMODAL_V2_SNAPSHOT_MANIFEST=1`. Per run, capture from logs:

- `[v2.snapshot_capture_hygiene]` line: `gc_collected`, `malloc_trim_available/result`, `before/after/delta_rss_kb` (+ anon/file/vmsize/vmdata, cgroup when readable), `hygiene_wall_ms`, `manifest_status`.
- `[v2.snapshot_manifest]` `before_capture` line: `rss_kb`, `rss_anon_kb`, `rss_file_kb`, `mappings/anon/file`, `gc_objects`.
- Startup payload `_restore_timing.snapshot_capture_hygiene` (event dict).
- Result event `output_stage13_breakdown`: 8 children + `stage13_total_ms` + `reconciliation_ms`/`status`.
- Baseline run (flag off) for byte-identical comparison: no hygiene line, no `snapshot_capture_hygiene` key, unchanged startup payload.

## 13. Stop conditions

- Any event shows `status=partial` or `boundaries_present=false` on the real path (stamp wiring regression) → stop, inspect stamps.
- `reconciliation_status=gap` with `|reconciliation_ms| > 1.0 ms` on ≥3 consecutive runs → stop, re-check tiling (children must be contiguous, non-overlapping, no double-counted regions).
- Hygiene flag-on run shows startup failure, exception in `startup()` tail, or GC collecting live objects (evident via manifest `gc_objects` collapse) → disable flag, investigate.
- `before_*` values all `unavailable` with real Linux sandbox (proc readable by the manifest) → instrumentation regression, stop.

## 14. Next decision rules

- If any Stage-13 child exceeds **>50 ms** on the integrated run (per the ≥10-run protocol, 35 s cooldown): that child becomes the trim candidate (trace/waterfall/interval/resource in priority order per `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` §5.2) — a follow-up optimization batch, **not** this one.
- If `delta_rss_kb` (before−after) is meaningful (>~10 MB median) and restore-side A/B shows no regression: promote `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE` default from 0 → 1 only after explicit review (production-default change requires its own decision).
- If cgroup `memory_current` is consistently absent in-sandbox: keep the field but exclude it from all subsequent decision math (matches known gVisor behavior).
- Reconcile with the runtime-state/models reload-guard lane results before any combined benchmark attribution.

---

## Completion output

- **report path** = `V2_BATCH_B_SNAPSHOT_HYGIENE_AND_STAGE13_REPORT.md`
- **changed files** =
  - `comfymodal_runtime/snapshot_capture_hygiene.py` (new)
  - `comfymodal_runtime/stage13_breakdown.py` (new)
  - `comfymodal_runtime/snapshot_build_manifest.py` (extended)
  - `comfymodal_runtime/modal_app.py` (additive stamps/blocks)
  - `tests/test_v2_snapshot_capture_hygiene.py` (new)
  - `tests/test_v2_stage13_breakdown.py` (new)
  - `tests/test_v2_snapshot_manifest_hygiene_extensions.py` (new)
- **commit** = none
- **deploy count** = 0
- **Modal runs** = 0
- **allocator hygiene implemented** = YES
- **feature flag** = `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE` (0 disabled default / 1 enabled)
- **gc before capture** = YES (flag-gated)
- **malloc_trim before capture** = YES (flag-gated, Linux-only guarded)
- **memory before/after captured** = YES (RSS/anon/file/vmsize/vmdata + cgroup when readable)
- **snapshot manifest ready** = YES (extended status + cgroup + capture_hygiene)
- **stage13 decomposition implemented** = YES
- **stage13 children reconcile** = YES (tiling, ±1.0 ms tolerance, unit-tested)
- **Stage13 behavior changed** = NO (decomposition only)
- **ready for integration** = YES
