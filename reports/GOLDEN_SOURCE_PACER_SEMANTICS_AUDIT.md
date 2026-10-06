# Golden Source Pacer Semantics Audit

Audit date: 2026-10-06

## 1. Source identity and audit basis

- Checked-out repository `HEAD`: `4b991d4e3eb09086acfc52b3413aab8b90cd6b0a`.
- The audited runtime/config files are clean relative to that commit. The worktree already had unrelated edits in `studio_golden_run.py`, `.opencode/skills/benchmark-modal/SKILL.md`, `.opencode/skills/comfymodal-golden-ops/SKILL.md`, `tests/browser/fake/studio-fake-workflow-run.spec.mjs`, `web/studio-playground.js`, and `web/studio-styles.js`; none were changed for this audit.
- Latest config-owned deployment record found: `.v2ctl/deployments/deploy_20261005-144259_33c68320.json`, profile `golden_p1_parallel_c0_p8_h100`, target `batch-c0-p8-h100`, method `run_golden_parallel_stream`, deployment fingerprint `33c68320d3d7c91ff204816ea0941653dd284c80aaf5eb37cc46571da7fefaf5`.
- That deployment record has `source_identity_status: "unknown"`, `request_id: null`, and no run artifacts. Therefore it proves the selected profile/configuration, but does **not** prove the remote container's exact source bytes or provide a run from that deployment. The findings below are a source audit of the checked-out SHA plus that deployment's recorded selectors.
- Codebase-memory graph tools were unavailable in this session; call paths were checked directly in current source and exact source snippets.
- No source code was changed, and no deploy or benchmark was run. This report is the requested audit artifact.

## 2. Current configured/executed source path

The latest recorded Golden target selects the C0 parallel source-owner profile. Its effective deployment environment includes:

| Setting | Recorded value | Effect |
| --- | --- | --- |
| `COMFYMODAL_GOLDEN_MODEL_TRANSPORT` | `1` | Selects `GoldenModelTransport` for canonical model loads. |
| `COMFYMODAL_GOLDEN_C0_SOURCE_THREADS` | `1` | Selects the persistent C0 source-owner implementation. |
| `COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND` | `thread` | One source-owner process with four reader threads. |
| `COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE` | `whole` | Whole-file `MAP_PRIVATE` mapping per source-owner address space and model plan. |
| `COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING` | `1` | Enables the shared C0 arena. |
| `COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE` | `mmap_fresh` | C0 source-engine identity; with source threads enabled, the selected data kernel is the source-owner path below, not the old exact-window M2 reader. |
| `COMFYMODAL_GOLDEN_C0_READER_GATE` | `0` | Disables the optional reader-side gate in the older forked-reader implementation; it does not disable `GlobalSourcePacer` in the selected source-thread path. |
| `COMFYMODAL_GOLDEN_C0_SOURCE_VOLUME_V1` | `0` | No alternate Volume V1 range reader. |
| `COMFYMODAL_GOLDEN_C0_PRIVATE_SPLIT_IO` | `0` | No extra private-buffer copy before the source arena. |
| `COMFYMODAL_GOLDEN_LOADER_PROCESS` | `0` | No separate Golden loader-process path. |

Current source call graph:

```text
ModalRuntimeEntrypointV2.run_golden_parallel_stream
  -> golden_parallel_execute
     -> golden_clip_load
     -> golden_unet_load
     -> golden_vae_load
        -> GoldenModelTransport.load / load_sync
           -> _load_c0_sync
              -> _load_c0_source_threads_sync
                 -> inspect safetensors layout; allocate GPU destination
                 -> construct 64 MiB SourceRanges from layout.data_start/data_bytes
                 -> SourcePlanBridge.publish_all
                    -> SourceThreadProcess.plan_once sends one PLAN per model
                    -> source-owner installs descriptor and whole-file mmap
                    -> four persistent readers self-claim a range and free slot
                       -> execute_block
                          -> _paced_copy / GlobalSourcePacer.paced_copy
                          -> mark_actual_start
                          -> libc.memmove(mapped model range -> shared arena slot)
                       -> publish READY_BLOCK after the copy
                 -> parent dispatcher submits H2D and releases slot after completion
```

Evidence: `modal_app.py:22848-22858,23065-23076,23579-23600`; `golden_parallel.py:16-41,313-342,468-478,605-612`; `golden_serial.py:11726-11729,11903-11919,13615-13654,14664-14690`; `golden_model_transport.py:807-835,1342-1421,1684-1695`; `golden_source_threads.py:1366-1446,1696-1774,1788-1857,1919-2020`.

CLIP, UNET, and VAE reach the same `GoldenModelTransport` singleton/source-owner in the selected profile. The common C0 loader lock serializes model-plan installation; the source owner and pacer instance persist while the runtime loads the successive model generations. The VAE stage's run telemetry does not emit the same `golden_model_transport_load` event as the CLIP/UNET stages, so it lacks the same pacer summary in retained run artifacts; the source code still selects the same transport branch when model transport is enabled.

## 3. Authoritative source-launch boundary

For the recorded `whole` lifecycle, `build_plan()` opens the model file and creates a read-only `MAP_PRIVATE` mapping without `MAP_POPULATE` (`golden_source_threads.py:1639-1684`). In `execute_block()`, the reader calculates a source pointer into that already-created mapping, prepares the destination slot, and then calls `mark_actual_start()` immediately before `libc.memmove()` (`golden_source_threads.py:1715-1735`). The native `memmove` is the first operation in this source-owner path that consumes the model **data range** and can fault/materialize those mapped pages.

Thus the closest current source-range launch boundary is the timestamp sampled in `mark_actual_start()` directly before entering `libc.memmove`. Mapping creation, PLAN installation, range/slot claims, pipe delivery, READY publication, H2D, and CUDA completion are not the source-range launch boundary.

One separate pre-plan operation is worth distinguishing: a cache miss in `GoldenModelTransport.inspect()` can call `_parse_layout()`, which reads the safetensors 8-byte header length and header JSON before building the source ranges (`golden_model_transport.py:1035-1091,350-380`). UNET layout pre-resolution can do that work on a helper thread (`golden_model_transport.py:1093-1132`). Those are metadata/layout reads, not consumption of the mapped model data range defined above, and they are not paced. If “actual source launch” were broadened to include every metadata/header read from the checkpoint file, those reads would be outside this pacer.

## 4. Active pacer implementation and state

The selected thread topology constructs one `GlobalSourcePacer()` in `_child_main()` and passes that same object to all four persistent reader threads (`golden_source_threads.py:1935-1936,2000-2020`). Its production interval is the module constant `PACER_GAP_NS = 4_000_000` (`golden_source_threads.py:91-96`). The production caller does not pass a different interval.

The active `paced_copy()` algorithm (`golden_source_threads.py:373-423`) is, semantically:

1. Acquire the shared thread lock.
2. Read the last recorded copy-start marker and `time.monotonic_ns()`.
3. Sleep until the last marker plus `gap_ns`, if necessary.
4. Invoke the copy callback. The callback samples `time.monotonic_ns()`, rechecks against the previous marker, corrects a sub-interval marker if necessary, stores it as the new actual marker, and releases the lock.
5. The callback immediately calls `libc.memmove()` and returns the marker timestamp.

State and bookkeeping:

| State | Use |
| --- | --- |
| `gap_ns` | Fixed 4,000,000 ns minimum. |
| `_clock` | Defaults to `time.monotonic_ns`. |
| `_sleep` | Defaults to `time.sleep`; nanoseconds are converted once by `/ 1e9` to seconds. |
| `_lock` | One `threading.Lock` owned by the source-owner process and shared by its four reader threads. |
| `actual_timestamps_ns` | Shared-in-process ordered copy-start markers; the active gate reads the most recent entry. |
| `last_start_ns`, `timestamps_ns` | Updated as marker/reservation bookkeeping; `paced_copy()` gates from `actual_timestamps_ns`, not from an independently planned timestamp. |
| `wait_ns`, correction/zero-delay counters | Telemetry only. |
| `reader_id`, `ordinal` arguments | Accepted by `paced_copy()` but not used to choose a delay. |

`GlobalSourcePacer.reserve()` exists, but no production call site in the selected path calls it. The production path is `execute_block()` -> `_paced_copy()` -> `paced_copy()`.

## 5. Locking and reservation semantics

- **Lock protecting active pacer state:** `GlobalSourcePacer._lock`, an ordinary `threading.Lock`, created once by the source-owner child. The separate `_FileLock` in `golden_source_threads.py` protects shared slot/header transitions; in the selected thread mode it is not the pacer lock.
- **Acquisition/read/update:** `paced_copy()` acquires `_lock` before reading the last marker and holds it through its wait. `mark_actual_start()` samples the clock, performs a correction loop if needed, appends the marker, mirrors it to `last_start_ns`, records wait telemetry, then releases `_lock`.
- **Sleeping:** The thread-mode pacer holds `_lock` while sleeping for the minimum interval and while performing marker correction. This makes the shared marker decision single-writer; another reader cannot calculate the same legal marker time.
- **Lock during native copy:** No. The lock is released inside the marker callback, before `execute_block()` enters `libc.memmove()`.
- **Can launches invert or bunch after marker/reservation?** Yes. For example, R0 records marker 100 ms and is descheduled after the callback releases `_lock` but before its `memmove` call. R1 then records 104 ms and enters `memmove`; R0 resumes and enters `memmove` at 105 ms. The recorded marker gap is 4 ms, but the native source-copy entries are only 1 ms apart and are inverted. The code permits this exact scheduling window.
- **Timestamp basis:** In the active thread path, `last_start_ns` is set from the observed monotonic marker immediately before `memmove`, not from a future planned target. However, it is still sampled before the native function entry, not at or after that entry. `memcpy_start_ns` in the operation record is this marker, although the native function used here is `memmove`.

Consequently the pacer’s shared markers are globally spaced, but the code does not guarantee globally spaced native source-copy entries. The test `tests/test_c0_source_threads.py:427-463` also treats invocation of the marker as “actual” and sleeps after it to stand in for native copying; it does not timestamp entry into `libc.memmove()`.

The selectable `process` topology has a weaker variant. Each `_reader_main()` owns a `SharedSourcePacer`; it reserves `HEADER[12]` under the shared `_FileLock`, releases that lock before sleeping/copying, and only records its callback marker in a reader-local list (`golden_source_threads.py:425-495,2219-2234`). A reader preempted after writing the shared reservation can let another reader reserve and copy first. The local pacer telemetry is not itself global. This topology is **not** the latest deployment’s selection (`SOURCE_WORKER_KIND=thread`).

## 6. Global scope and model-generation behavior

In the deployed `thread` topology, all four source readers call the same pacer object; the state is not per reader, slot, lane, region, or model. The `reader_id` and range ordinal do not affect the gap. The pacer is created once when the source-owner process starts, not once per PLAN.

Installing the next model generation resets generation-scoped slot/counter/operation-ring state in `install_generation_header()` but does not reset `GlobalSourcePacer.actual_timestamps_ns` or `last_start_ns` (`golden_source_threads.py:1874-1905`). Therefore the marker floor carries across CLIP -> UNET -> VAE plans while that source owner persists. It resets only when the source-owner process is restarted/recreated. The P8 profile inherits Golden’s single-use-container configuration, so the normal experiment lifecycle is one request per container.

The process topology similarly leaves shared header field 12 unchanged when a new generation is installed, although its actual-marker tracking is per reader process and its physical-start guarantee is weaker as described above. The non-C0 persistent M2 path is different: it resets its shared `last_start` to zero at every model load (`golden_model_transport.py:1210-1223`), so its claim clock resets at CLIP/UNET/VAE boundaries.

## 7. Source-pacer call sites and path classification

| Call site / engine | What it paces | Current P8 path? | Classification |
| --- | --- | --- | --- |
| `golden_source_threads.GlobalSourcePacer.paced_copy()` via `_paced_copy()` in `execute_block()` | Reader-side marker immediately before whole-map `libc.memmove`, shared across four threads. | **Yes** (`SOURCE_THREADS=1`, worker kind `thread`, lifecycle `whole`). | Active source-range pacer. Marker spacing is global; native-call entry spacing is not guaranteed. |
| `golden_source_threads.SharedSourcePacer.paced_copy()` via the same `_paced_copy()` | Shared-header launch reservation across independent reader processes. | No (`worker_kind=thread`). | Alternative topology; reservation-to-copy preemption window can invert/bunch starts. |
| `golden_io_process_v2._mmap_launch_gate()` from `_do_fill_mmap()` | Coordinator-side 4 ms dispatch/claim reservation, before the request is sent over the reader pipe. | No. Source-thread mode routes `_load_c0_sync()` to `_load_c0_source_threads_sync()` and does not use the old C0 reader pool. | Legacy claim pacer only; cannot establish reader-side source-start spacing by itself. |
| `golden_io_process_v2._mmap_actual_launch_gate()` from `_mmap_reader_fill()` | Optional shared reader-side gate before the old reader’s mmap/memcpy operation. | No; `C0_READER_GATE=0` and the source-thread branch bypasses this reader. | Legacy optional gate, default/currently configured OFF. Not a second active P8 pacer. |
| `m2_source_core._alloc_gate()` called by `_reader()` / `_persistent_reader_load()` | Shared multiprocessing launch reservation for the standalone persistent M2 reader, before mmap and/or staging waits. | No; C0 is enabled and source threads take precedence. | Legacy non-C0 M2 path. Reservation time can drift from actual memcpy; per-model `_last_start` is reset. |
| `source_race_oracle` pacing helpers | Independent diagnostic/source-race experiment. | No. The separate `run_source_race_oracle` Modal method is not `run_golden_parallel_stream`. | Diagnostic only. |
| Normal Golden `read_file_qd_gpu` / static-e27 path | No source-thread pacer. | Not selected by latest P8 deployment (`GOLDEN_MODEL_TRANSPORT=1`, C0 source threads enabled). | Separate Golden serial/base profile; do not conflate with P8 whole-mmap source owner. |

The legacy 4 ms values in `golden_io_process_v2.py` and `golden_model_transport.py` are not active alongside the source-thread pacer in the selected path. In particular, the effective `C0_READER_GATE=0` does not create a second delay and does not turn off `GlobalSourcePacer`.

## 8. Hidden-dependency audit

| Candidate dependency | Active thread pacer behavior | Classification |
| --- | --- | --- |
| Previous source operation completion or duration | Not read. The lock is released at the start marker; native copies may overlap. | Outside pacing; completion is not an interval input. |
| Number of active readers / QD | Not read. Four threads contend on one lock, but no QD-dependent interval is calculated. | Synchronization contention may make gaps longer; no extra pacing rule. |
| Reader identity / recent per-reader launch | Not read; no per-reader timer or spacing. | Harmless ignored metadata. |
| Model identity, source offset, range ordinal, slot identity | Not read by the pacer; the caller’s `reader_id`/`ordinal` arguments are ignored. | Outside pacing. |
| Slot availability, arena state, work-queue occupancy, capacity wait | A reader must first claim a range/free slot. If it cannot, it waits before entering the pacer. | Required ownership/capacity correctness outside the pacer; can delay a request, not change X. |
| READY state, dispatcher state, H2D completion, CUDA events | Occur after source copy. H2D completion governs slot release/wakeup only. | Required ownership/capacity correctness outside the pacer; not an interval input. |
| Generation/model boundary | Not read; thread pacer state persists across plan generations. | Harmless generation bookkeeping outside the pacing decision. |
| Whether the previous read was slow | Not read; no duration-based cool-down. | No hidden duration condition. |
| Parent/coordinator claim time or pipe delivery | Current source workers self-claim; the parent sends one PLAN per model and receives READY only after the copy. No per-range parent dispatch precedes the copy. | Not part of active pacing. The old coordinator gate is a different, inactive path. |
| mmap creation | Whole-map setup occurs at plan install. It does not consume the payload range; pacing happens before the native copy. | Outside the source-range launch boundary. |
| Sleeps outside the pacer | Capacity/wakeup, plan/quiescence, dispatcher and stage scheduling can block before another reader reaches the pacer. | Outside pacing; may increase observed gap only. |
| Reader-lock contention | All readers share one lock, held through pacing sleep and marker correction. | Required synchronization; can add delay/ordering effects but does not change X. |
| Post-marker scheduling before `libc.memmove` | Lock is released before the native call; another reader can pass its own marker and copy first. | **Changes actual source-launch spacing; permits sub-4 ms physical entry gaps.** |
| Optional `cpu_qd2_prefetch` request | Deployment permits it (`GOLDEN_CPU_QD2_PREFETCH=1`), but the request field defaults false and retained P8-profile runs report false. If explicitly true, `prepare_cpu_clip_prefetch()` starts two `preadv` reader threads outside `GlobalSourcePacer`; the M2 branch does not pass that ticket into `GoldenModelTransport`. | Not active in the retained normal P8 runs; conditional unpaced source reads if request-opted-in, so they are outside the C0 source pacer’s global scope. |
| Layout/header parsing | Cache misses can read the safetensors header before PLAN/pacing; this reads metadata, not the mapped data range. | Required plan metadata outside the stated payload-launch boundary; would be unpaced if the contract were broadened to every file read. |

## 9. Configuration and units

- Active P8 source-thread interval: `PACER_GAP_NS = 4_000_000` in `golden_source_threads.py:96`; no profile or environment variable overrides it.
- Conversion: `4_000_000 ns / 1_000_000 = 4 ms`; the sleep argument is `delay / 1e9` seconds. Pacer comparisons and stored timestamps remain integer nanoseconds. There is no double millisecond conversion or microsecond conversion.
- Clock: `time.monotonic_ns()` by default for both active source-thread pacing and its operation timestamps. No wall clock is used for the interval.
- `GlobalSourcePacer` and `SharedSourcePacer` default to the same constant. The P8 coordinator does not run a separate source-thread claim gate.
- Legacy gates also use `4_000_000 ns`: `MMAP_LAUNCH_GAP_NS` in `golden_io_process_v2.py` and `MIN_LAUNCH_GAP_NS` in `golden_model_transport.py`. Their scopes differ and they are not simultaneously active in the selected P8 route.
- Registry defaults without the P8 profile are `C0_SOURCE_THREADS=0`, `C0_MMAP_LIFECYCLE=fresh`, and `C0_READER_GATE=0`; the recorded P8 deployment explicitly resolves source threads on, `thread`, and `whole`.

## 10. Existing-artifact spacing verification

### Nearest recent source-thread/whole-mmap evidence

The latest config-owned P8 deployment record itself has no request/run artifacts and has `source_identity_status: unknown`; no post-deployment raw start series exists locally for the exact `batch-c0-p8-h100` deployment.

The nearest retained same-profile current-Golden evidence is the 2026-10-05 P8-profile cohort on `batch-p13-rgn-ca/us` in `artifacts/fast_state_runs.json` (24 valid attempts, 48 CLIP/UNET source-generation summaries). The artifacts identify `c0_source_threads=true`, `c0_mmap_lifecycle=whole`, `cpu_qd2_prefetch=false`, and 16 x 64 MiB slots. The retained `golden_source_threads.py`, `golden_model_transport.py`, `golden_io_process_v2.py`, `golden_parallel.py`, and `golden_serial.py` files in that run’s `bisect-armA` worktree have the same SHA-256 bytes as the audited checkout for these runtime files; the pacer module hash is `f851a6c60f572a2e9ec8a66937b6de92e868c7d5f9d4b437d0dec03e2e917728`. The app adapter file differs, and this is a different target app/deployment fingerprint than the latest P8 deployment.

Available per-generation **marker** telemetry for those 48 model loads:

| Measure | Available result |
| --- | --- |
| Marker operations | 24 CLIP loads x 120 operations and 24 UNET loads x 184 operations. |
| Minimum of the stored per-load minimum marker gaps | 4.002329 ms. |
| Maximum of the stored per-load minimum marker gaps | 4.103295 ms. |
| Per-load `pacer_gap_violation_count` | 0 in all 48 summaries. |
| Marker deltas below 4.0 / 3.9 / 3.5 ms within those model generations | 0 / 0 / 0, implied by each stored minimum and zero-violation counter. |
| p1 / p50 over all individual gaps | Not available; per-operation timestamps were removed from the persisted transport detail. |
| Worst reader pairs | Not available; individual operation records were not retained. |
| Cross-model boundary deltas | Not available in the compact artifacts; the per-generation operation ring resets at PLAN install. |
| Physical `libc.memmove` entry deltas | Not recorded. The values above are pre-call marker timestamps. |

These summaries support a >=4 ms **marker** floor for those profile-aligned runs; they are not proof of physical native-entry spacing or of the exact latest P8 deployment. In `_load_c0_source_threads_sync()`, `source_operation_records` are used transiently for the summary and then removed from `source_telemetry_compact` (`golden_model_transport.py:1474-1480,1569-1637`). The all-generation pacer telemetry list is emitted by the child only at shutdown; the parent's `stop()` waits for process exit without draining that final telemetry frame (`golden_source_threads.py:2117-2131,1320-1347`).

### Historical claim-only diagnostic (excluded from current P8 measurements)

`artifacts/testing9_viztrace/viztrace_parent_child_summary.json` is an older `fresh` / `qd4_128` exact-window reader diagnostic, not the P8 whole-map source-thread topology. Its reader telemetry contains 158 `memcpy_start_ns` copy-start markers across CLIP and UNET and per-operation `mmap_launch_gap_wait_ns`; `mmap_actual_gate_wait_ns` is null. It is useful only as a historical comparison for the old coordinator-claim path, not as current production evidence.

Sorting those 158 markers globally across readers/models gives 157 deltas (p1 uses linear interpolation on sorted values):

| Measure | Historical diagnostic result |
| --- | --- |
| Minimum | 3.401269 ms |
| p1 | 3.731505 ms |
| p50 | 12.209810 ms |
| Count <4.0 / <3.9 / <3.5 ms | 7 / 4 / 1 |
| Cross-model CLIP -> UNET marker delta | 176.433759 ms (no boundary violation in this artifact). |

The seven smallest marker gaps were: 3.401269 ms CLIP R0->R2; 3.668568 ms UNET R0->R3; 3.780955 ms UNET R1->R2; 3.793300 ms CLIP R1->R3; 3.936373 ms UNET R2->R0; 3.948953 ms CLIP R3->R1; 3.995578 ms CLIP R3->R0. This old path calls `_mmap_launch_gate()` before pipe delivery; the emitted per-operation `mmap_actual_gate_wait_ns` is null while `mmap_launch_gap_wait_ns` records the coordinator wait. The source copy markers can bunch after dispatch/IPC. The artifact does not store a reservation timestamp series, so reservation-gap percentiles cannot be independently calculated from it. Its `memcpy_start_ns` is the old reader's copy-start telemetry marker, not an instrumentation timestamp taken atomically at the native C entry.

This historical diagnostic demonstrates why claim spacing is not authoritative. The current P8 source-thread configuration does not route through that coordinator gate; it routes through the in-owner reader-side `GlobalSourcePacer` described above.

## 11. Verdict

### `PARTIAL — LOGICAL CONTRACT CORRECT, ACTUAL LAUNCH NOT GUARANTEED`

The active thread-mode pacer makes globally shared, 4 ms minimum decisions from the last recorded copy-start marker and monotonic time. It does not add duration, QD, reader, model, slot, arena, H2D, READY, queue, generation, or coordinator timing rules. It is global across the four source threads and persists across model-plan generations.

However, `last_actual_source_launch` is updated and the pacer lock is released **before** the native `libc.memmove()` call begins. A reader descheduled in that handoff window can let another reader enter `memmove` first and then resume close behind it. Current telemetry records the pre-call marker, not the physical native entry. Therefore the code does not guarantee the requested physical behavior `actual source launch N+1 >= actual source launch N + 4 ms`. The latest deployment record also does not attest its source identity, so the audited checkout cannot be byte-bound to that remote deployment from retained evidence.
