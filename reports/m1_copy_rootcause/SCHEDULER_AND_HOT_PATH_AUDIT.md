# M1 SCHEDULER AND HOT-PATH AUDIT (production-006, live code)

All line references are to the immutable `production-006` tag `42cf4d0` as
checked out in `.slim/worktrees/m1-loader-forensics`, i.e. exactly what the
counted cohort ran. Evidence classes are stated per claim.

## 1. Exact production-006 identity

| field | value | class |
|---|---|---|
| tag | `production-006` (annotated) | CODE-PROVEN |
| commit | `42cf4d048a8dbc66535753a857cc5cd99135f074` | CODE-PROVEN |
| cohort runtime commit | `5d41f742...` (tag differs by documentation only) | CODE-PROVEN (`git diff 5d41f742 42cf4d0` = 1 doc file) |
| deployment fingerprint | `1b0e49ea` | DIRECTLY MEASURED (deploy receipt) |
| profile | `golden_p1_parallel_c0_source_h100` | CODE-PROVEN |
| app / class / method | `batch-c0-source-h100` / `ModalRuntimeEntrypointV2` / `run_golden_parallel_stream` | CODE-PROVEN |
| GPU / CPU / memory | `H100!` / 12 / 24576 MiB | CODE-PROVEN |
| expected output SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` | DIRECTLY MEASURED, 10/10 |
| source owner processes | 1 (`process_id=62`) | DIRECTLY MEASURED |
| reader processes | 0 | DIRECTLY MEASURED |
| reader threads | 4 (`c0-source-0..3`, native tids 64,65,66,67) | DIRECTLY MEASURED |
| mmap lifecycle | `whole` | DIRECTLY MEASURED, 10/10 |
| per-extent mmap/munmap executed | 0 (`mmap_map_count=0`, `mmap_unmap_count=0`) | DIRECTLY MEASURED, 10/10 both roles |
| QD target | 4 | DIRECTLY MEASURED |
| arena | 512 MiB, 8 slots × 64 MiB, host-registered | DIRECTLY MEASURED |
| pacing floor | 4 ms, **enforced** at copy start | CODE-PROVEN + DIRECTLY MEASURED (`min_source_gap_ms` 4.015-4.068) |
| H2D | C0 async dispatcher, 1 dedicated stream, 8 start + 8 end events, one-shot | DIRECTLY MEASURED |
| H2D aggregation | **disabled** (`aggregated_submission_count=0`, `non_aggregated=120/184`) | DIRECTLY MEASURED |

## 2. Exact loader call graph (live path)

Proven by dispatch condition `golden_model_transport.py:758-760`
(`self._c0_enabled = c0_streaming and (source_engine == "mmap_fresh" or
self._c0_source_threads_enabled)`) and by construction
`golden_io_process_v2.py:4469-4482`.

```text
Golden load entry                       golden_serial.py:11422 (CLIP) / :13033 (UNET)
└─ GoldenModelTransport.load
   └─ _load_c0_source_threads_sync       golden_model_transport.py:1176
      ├─ inspect/parse safetensors       golden_model_transport.py:303-354
      ├─ build range plan (64 MiB units) golden_model_transport.py:1183-1195
      ├─ C0 arena + cudaHostRegister     golden_io_process_v2.py:1160-1190
      ├─ SourceThreadProcess.spawn        golden_source_threads.py:848-855  (ONE Popen)
      │  └─ child: 4 reader THREADS      golden_source_threads.py:1719 (_run_reader_loop)
      │     └─ per extent: claim → pace → memmove → publish READY
      │                                 golden_source_threads.py:1719-1790
      │                                 execute_block :1627-1690
      ├─ bridge.publish_all (PLAN)       golden_model_transport.py:1202
      ├─ wait_ready (doorbell + table)   golden_source_threads.py:1076-1119
      ├─ H2D submit (dispatcher)         golden_qd_transport.py
      ├─ completion event → slot FREE    golden_source_threads.py:1141-1164
      ├─ wait_quiescent                  golden_model_transport.py:1262
      ├─ manager.snapshot()              golden_source_threads.py:1214  (per-op records)
      ├─ tensor views / state dict       golden_model_transport.py:1264
      └─ bind / adoption / storage proof golden_serial.py
```

Note the naming trap, resolved: `COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE="mmap_fresh"`
is the **C0 arm-selection name**, while `COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE="whole"`
is the **mapping lifecycle** tested independently at `golden_source_threads.py:1576-1578`
and applied at `:1646-1650`. `whole` wins at run time. Proven by
`mmap_map_count=0` and `map_start_ns=0` on all 1216 measured extents.

## 3. Scheduler semantics — every question answered from code

| question | answer | evidence |
|---|---|---|
| how is the next range selected? | one global shared counter `header[7]` (`next_range`), `uint64`, in the control segment | `golden_source_threads.py:87-89`, claim/increment `:729-751` |
| static or dynamic? | **dynamic** — any free reader takes the next counter value | `:729-751` |
| contiguous or striped? | **contiguous ascending** — ordinal == file offset order | `ordinal` == `source_offset/64MiB` in all 1216 records |
| sticky reader regions? | **NO** | no per-reader region state exists in the claim path |
| work stealing? | **NO WORK STEALING** | single shared counter; no steal queue, no victim scan |
| when would stealing occur? | never; the counter is the only work source | `:729-751` |
| can a free reader always claim? | only if `next_range < len(plan)` **AND** a slot is FREE; otherwise it blocks | `:729-740`, `:1758-1783` |
| can one reader retain work while others idle? | yes, transiently: the counter advances before the copy, so a reader owns its claimed extent; others idle only if the counter is exhausted or all slots are busy | `:740-751` |
| does assignment need the parent? | **NO** — only the shared control lock; the parent installs plans and releases slots, it does not schedule extents | `:715-720` ("must be called under the control lock"), `:1997-2000`, `:2028-2045` |
| PLAN/ACK per model or per extent? | **per model generation** — one PLAN carries all ranges | `:946-952`, `:1507-1514`, ACK once at `:2043-2045` |
| is READY authoritative or a hint? | the **shared slot table + header counts are authoritative**; the doorbell is a hint | table `:541-549`, recovery `_recover_ready_from_table` `:1048-1074` |
| exact doorbell behaviour | one JSON `READY_BLOCK` line per READY extent on the owner's stdout, emitted **outside** the control lock; the parent blocks on it with a 250 ms bounded slice | `:1695-1697`, `:1087-1099` |
| recovery behaviour | on timeout slice / unusable doorbell / final timeout, the parent re-derives READY ownership by scanning the slot table | `:1048-1074`, `:1076-1119` |

## 4. Lock graph

| lock | type | created | acquired | purpose |
|---|---|---|---|---|
| `_FileLock._thread_lock` | `threading.Lock` | `:482-485` | `:489` / released `:496` | in-process mutual exclusion |
| `_FileLock` process lock | POSIX `fcntl.flock` | same | `:490` / `:495` | cross-process mutual exclusion with the parent |
| `GlobalSourcePacer._lock` | `threading.Lock` | `:294-302` | `:356` / released `:390`, fallback `:399` | 4 ms global start spacing |
| owner `emit_lock` | `threading.Lock` | `:1872-1873` | `:1876-1878` | serialise JSON doorbell writes |
| `SourceThreadProcess._lock` | `_FileLock` | `:800-805` | `:920-925, 993-997, 1003-1017, 1059-1074, 1123-1139, 1143-1164, 1179-1183, 1187-1190` | owner/parent protocol + slot table |
| `GoldenModelTransport._lock` | `threading.RLock` | `golden_model_transport.py:727-732` | `:783-791, 845-909, 996-1145` | transport lifecycle |
| `GpuDestinationPool._lock` | `threading.Lock` | `golden_model_transport.py:145-150` | `:177-180, 186-213, 216-228` | GPU destination growth |

### Per-extent lock sequence (thread topology)

1. `_FileLock` for `claim_block` — `:1748-1773`. Work inside: free-slot scan over
   `SLOT_COUNT=8` (O(8), bounded), FILLING scan (O(8)), O(1) header/slot writes.
   **No range scan.**
2. **No lock** during pointer derivation, pacing sleep, or the native `memmove`
   — `:1639-1678`.
3. `GlobalSourcePacer._lock` covers the pacing wait and is **released before the
   copy** via `mark_actual_start` — `:371-392`.
4. `_FileLock` for `publish_ready` — `:1689-1690`. O(1) plus a fixed 26-field pack.
5. `emit_lock` for the doorbell JSON — `:1875-1878`. O(1).

### Lock conclusions (the three proofs requested)

- **Is any lock held across the native memcpy? NO.** The copy is at `:1664-1665`,
  after `mark_actual_start()` releases the pacer lock (`:371-392`); the control
  lock is not held across the operation (`:1630-1634`, `:1689-1690`).
- **Is any lock held across an H2D completion wait? NO.** Slot release happens
  only in the dispatcher's completion callback (`:1141-1164`, invoked from
  `:1345-1347`); quiescence is checked after dispatcher finalisation
  (`golden_model_transport.py:1262`).
- **Do readers serialise anywhere unexpectedly? NO.** Native copies run
  concurrently: measured concurrency is QD4 on 456/480 CLIP ops and 713/736 UNET
  ops, and per-reader busy wall is even to within ~1.5%.

### Sleeps, polling, bounded waits

| mechanism | constant | location |
|---|---|---|
| pacer sleep | dynamic from `PACER_GAP_NS=4_000_000` | `:73`, `:321-325`, `:367-369`, `:376-380` |
| reader capacity wait slice | `CAPACITY_WAIT_SLICE_S=0.25` | `:153-156`, `:1778-1783` |
| consumer READY slice | `min(remaining, 0.25)` | `:1098` |
| quiescence poll sleep | `0.0005 s` | `:1174-1184` |
| process-reader startup poll | `0.001 s` | `:1959-1965` (process arm only) |

## 5. Python / GIL / object accounting for one source extent

Enumerated from `execute_block` `:1627-1690` and `_run_reader_loop` `:1832-1908`:

- reader-loop function calls, `with lock` context management
- one `memoryview(arena_buf)` **plus one bounded slice** (`:1639`)
- `ctypes.c_void_p` ×2, `ctypes.c_size_t` ×1 per native call (`:1664-1665`)
- `ctypes.c_char.from_buffer(target)` + `ctypes.addressof` (`:1660`)
- one 26-field tuple built in place (`:1771-1795`)
- one READY dict + JSON serialise + stdout write/flush (`:1695-1697`, `:1875-1878`)
- consumer side: `ReadyRecord`, dispatcher record, lease dict, publish call (`:1329-1357`)

Answers:

- **Is an extent-sized Python `bytes` ever materialised? NO.** The destination is
  a `memoryview` slice of the pre-existing arena (`:1639`) and the native call
  writes into it directly. `bytes(...)` appears only for control/plan metadata
  (`:562-569`, `:582-586`), never for payload. The dispatcher's
  `python_payload_materialization=true` flag refers to the legacy reader mode,
  not this path.
- **Any full extent-sized intermediate per op? NO.**
- **How are pointers obtained?** source: `plan.map_address + source_offset`,
  cached once per generation (`:1646-1650`). destination: `ctypes.addressof` on
  the slot memoryview, recomputed per op (`:1639-1660`).
- **libc binding lifetime?** constructed **once per process** by `_init_native`
  (`:1713-1716`) via `_native_mmap_setup` (`:1472-1482`) as
  `ctypes.CDLL(None, use_errno=True)`.
- **Does the native call release the GIL?** **YES.** `CDLL` (as opposed to
  `PyDLL`) releases the GIL for the duration of the call. This is now corroborated
  empirically: `time.thread_time_ns()` advances by ~94% of wall across the call
  (median ratio 0.938 CLIP / 0.942 UNET over 1216 extents), which is only
  possible if the calling thread is genuinely descheduled from the interpreter
  and running native code.

## 6. 32 MiB vs 64 MiB — resolved completely

The historical ambiguity came from a **nominal telemetry field**, not behaviour.

| quantity | CLIP | UNET | class |
|---|---|---|---|
| logical source planning unit | 64 MiB | 64 MiB | CODE-PROVEN `golden_model_transport.py:1183-1195` |
| physical source-copy unit | 64 MiB | 64 MiB | CODE-PROVEN `golden_source_threads.py:70` `SLOT_BYTES` |
| arena slot size | 64 MiB | 64 MiB | DIRECTLY MEASURED `slot_bytes=67108864` |
| H2D submission unit | 64 MiB | 64 MiB | DIRECTLY MEASURED `h2d_max_submission_bytes=67108864`, `h2d_min=58981376` (CLIP tail) |
| tail extent | 58 981 376 B = 56.249 MiB | 28 895 360 B = 27.557 MiB | DERIVED from measured bytes/ops |
| data-section bytes | 8 044 936 192 (7672.25 MiB) | 12 309 817 472 (11 739.56 MiB) | DIRECTLY MEASURED |
| source operation count | 120 = ceil(7672.25/64) | 184 = ceil(11739.56/64) | DIRECTLY MEASURED, matches exactly |
| H2D operation count | 120 | 184 | DIRECTLY MEASURED, 1:1 with source ops |
| ops if 32 MiB unit | 240 | 367 | **MISMATCH — proves 32 MiB is not the unit** |

**The 32 MiB field.** `dispatcher.source_block_bytes = 33554432` on 10/10 runs is
a **stale nominal label** in the dispatcher telemetry; it does not control the
live C0 source-thread path. The controlling constants are 64 MiB
(`golden_source_threads.py:68-70`, `golden_model_transport.py:705-711`), and C0
rejects non-QD4/64 geometry. A nominal 32 MiB default also exists elsewhere in
config (`COMFYMODAL_V2_CLIP_QD_BLOCK_MIB`), unread by this path.

**Definitive statement: every physical source operation and every H2D operation
is 64 MiB, except one tail extent per model. The 32 MiB value is a label, not a
behaviour.**

## 7. Pacer

`PACER_GAP_NS = 4_000_000` (`:73`). For the thread topology,
`GlobalSourcePacer.paced_copy` (`:350-395`) holds its lock while reserving the
next actual start, sleeps to the floor, then requires the callback to mark the
actual boundary **immediately before** `memmove`; the lock is released at that
marker (`:371-392`).

**The floor is ENFORCED, not advisory, and the measurement point is copy start,
not claim time.** Direct evidence: `pacer_gap_violation_count = 0` on 10/10 runs
and 4 M1 runs, and `min_source_gap_ms` 4.015-4.068 (CLIP) / 4.021-4.068 (UNET).
Measured pacing cost: **1.77% of CLIP source wall** (36.73 ms over 120 extents)
and **2.32% of UNET source wall** (55.70 ms over 184 extents), affecting only
17/120 and 25/184 extents respectively.

The cross-process `SharedSourcePacer` is weaker (reserves under the shared lock,
then validates actual start) and is not the production-006 arm.

## 8. READY publication cost

`memcpy_end → ready_ns` measured across all 1216 extents:
p50 = **0.000 ms**, p90 = 0.001 ms, max = 0.010 ms.

Publication is a monotonic read plus an O(1) slot-table write under the control
lock. It is **not** a meaningful cost, and the doorbell JSON write happens
after the timestamp, outside the lock.

## 9. Data-coverage status for Phase 1

| item | status |
|---|---|
| exact call graph | CODE-PROVEN |
| scheduler semantics (12 questions) | CODE-PROVEN |
| lock graph + three proofs | CODE-PROVEN |
| GIL release | CODE-PROVEN + empirically corroborated |
| 32/64 MiB semantics | RESOLVED (DIRECTLY MEASURED + DERIVED) |
| pacer enforcement | CODE-PROVEN + DIRECTLY MEASURED |
| extent semantics (120 / 184) | DIRECTLY MEASURED |
| per-extent wall + CPU | DIRECTLY MEASURED (1216 extents) |
