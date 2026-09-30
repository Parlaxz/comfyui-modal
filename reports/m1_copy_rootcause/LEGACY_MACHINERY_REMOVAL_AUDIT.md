# M1 LEGACY MACHINERY / DEAD ARCHITECTURE REMOVAL AUDIT

**READ-ONLY AUDIT. Nothing was removed, specialised, or optimised.**

Baseline truth used: one CUDA-sterile source-owner **process** (`process_id=62`),
**4 reader threads** (`c0-source-0..3`, tids 64-67), **whole** `MAP_PRIVATE`
mapping per model generation, 8×64 MiB registered arena, C0 async H2D
dispatcher, generation IDs + READY authoritative table + doorbell + table
recovery + stale-generation rejection + completion-gated release + 30 s gates.

Evidence classes: **CODE-PROVEN** (read in the live committed source),
**DIRECTLY MEASURED** (from the 10-run production-006 cohort and/or 1216 M1
per-extent records), **DERIVED**, **HISTORICAL**, **SUPPORTED INFERENCE**,
**UNKNOWN**.

## 0. Headline correction to a common misreading

The historical experiment ledger that dominates the repo
(`SOURCE_IO_EXPERIMENT_LEDGER.md`) describes **4 reader PROCESSES with FRESH
per-extent mmap**. production-006 is **4 reader THREADS with WHOLE mmap**. The
difference is not cosmetic:

- `mmap_map_count = 0` and `mmap_unmap_count = 0` on **10/10** runs, both roles.
- `map_start_ns = 0` and `munmap_start_ns = 0` on **1216/1216** M1 extents.
- `workers_ready = 4`, `source_worker_kind = "thread"`, one `process_id`.

Therefore: the per-extent mmap/munmap machinery is **present in code but provably
not executed**, and the per-reader-process machinery is **present in code but
provably not executed**. Neither costs wall time today. Their cost is
*maintenance and branch surface*, not latency.

## 1. IPC path table — parent↔owner is required, owner↔reader-process is not

| path | mechanism | production-006 status | class |
|---|---|---|---|
| parent → source owner | one `subprocess.Popen` (`golden_source_threads.py:848-855`), `CUDA_VISIBLE_DEVICES=""`, stdin/stdout pipes, JSON-line protocol | **EXECUTED, REQUIRED** — the owner is a separate address space and must be CUDA-sterile | CODE-PROVEN + DIRECTLY MEASURED (`child_pid=62`) |
| parent → owner readiness | 30 s readiness gate + geometry validation (`:857-878`) | **EXECUTED, REQUIRED** | CODE-PROVEN |
| parent → READY doorbells | one JSON line per READY extent on owner stdout (`:1695-1697`), read with `select` and a 250 ms slice (`:1087-1099`) | **EXECUTED, REQUIRED** — this is the cross-process notification | CODE-PROVEN |
| parent → shared arena | `SharedMemory` + `/dev/shm` raw attach, host-registered | **EXECUTED, REQUIRED** | CODE-PROVEN |
| owner → reader threads | shared Python objects, shared control buffer, shared plan, `Semaphore` wake | **EXECUTED, REQUIRED** — threads share the address space | CODE-PROVEN |
| reader thread → reader thread | none; coordination only via the control table and slot states | n/a | CODE-PROVEN |
| parent → **individual reader processes** | `mp.Process`, `multiprocessing.Pipe`, per-reader READY handshake, per-reader FD invalidation (`golden_model_transport.py:807-834`, `:956-970`) | **NOT EXECUTED** under `worker_kind="thread"` — reachable only from the non-C0 M2 process arm | CODE-PROVEN (unreachable in this config) |
| SIGCHLD / reader restart supervisor | none found on the thread path; `reader_pid` is telemetry, not control (`golden_io_process_v2.py:3139-3155`) | **NOT PRESENT** | CODE-PROVEN |
| per-reader health / restart state | none; fatal reader errors set shared stop+fatal state (`:1773-1793`) | **NOT PRESENT** as a supervisor | CODE-PROVEN |

## 2. Thread-era synchronisation leftovers

| mechanism | location | who uses it | cross-process semantics required? | verdict |
|---|---|---|---|---|
| `threading.Lock` in `GlobalSourcePacer` | `:294-302` | the 4 reader threads | no (in-process) | **REQUIRED** — it is the 4 ms global start gate |
| `_FileLock` (`threading.Lock` + `fcntl.flock`) | `:475-498`, created `:800-805` | parent↔owner protocol **and** owner↔reader slot table | **yes** — the parent is a different process | **REQUIRED** |
| control-buffer lock around claim/publish | `:718-724`, `:1748-1776`, `:1689-1690` | readers among themselves | no, but it is the same lock as the parent protocol | **REQUIRED** (one lock serves both) |
| `SharedSourcePacer` | `:402-475` | process topology only | n/a | **GENERIC MULTI-ARM** — dead under `worker_kind="thread"` |
| `mp.Lock` / `mp.Value` / `mp.Array` / `mp.Pipe` | `golden_model_transport.py:807-834` | non-C0 M2 process arm | n/a | **LEGACY PROCESS-READER BAGGAGE** — unreachable here |
| `multiprocessing.Manager` queues | none found | — | n/a | **NOT PRESENT** |
| per-op JSON between readers | none (owner JSON carries plan + doorbells only) | — | n/a | **NOT PRESENT** |

**No process-safe mechanism is used only between the reader threads.** The
`_FileLock` is genuinely cross-process because the *parent* participates, so it
is not a simplification candidate. This is an important negative result: the
thread migration did **not** leave behind a redundant process-safety layer
between readers.

## 3. Fresh-mmap leftovers (per-extent mapping machinery)

| item | location | executed under `whole`? | cost if executed | removable from production path? | still needed elsewhere? |
|---|---|---|---|---|---|
| per-extent `mmap()` | `:1654` | **NO** | the historical collapse: 6.2-6.4 GB/s → 0.145-1.597 GB/s | yes — hoistable into a generation-bound executor | yes, for the `fresh` diagnostic profile |
| page-align-down | `:1651` | **NO** | O(1) arithmetic, negligible | yes | same |
| exact-window length `source_offset-aligned+length` | `:1652` | **NO** | O(1) | yes | same |
| mapping delta `base + offset - aligned` | `:1658` | **NO** | O(1) | yes | same |
| per-extent `munmap()` | `:1675` | **NO** | the same per-extent re-fault cost | yes | same |
| `temporary_map` flag | `:1645`, `:1673` | **NO** (always false) | one branch per extent | yes | same |
| per-op map lifecycle telemetry fields | `OP_FIELDS` `map_start_ns`, `munmap_start_ns`, `munmap_end_ns` | fields written, always 0 | 3 × 8 B stores per extent | yes — but they are the *proof* that whole mode holds | diagnostic value |
| `retire_plan()` (munmap + close FD) | `:1618-1625` | **YES, once per generation** | required | **NO — required** | n/a |
| mapping registry / stale-map table | none found | n/a | n/a | n/a | **NOT PRESENT** |
| deferred-munmap state | none in this module (historical `du_runs` arm) | n/a | n/a | n/a | **NOT PRESENT** |

Per-extent cost of the whole fresh branch if it were live: **1 branch +
~5 arithmetic ops + 1 bool store per extent**, i.e. 304 evaluations across a
CLIP+UNET request. Python-level cost is on the order of microseconds total —
**structurally removable, wall-negligible**. Its removal value is code
clarity, not latency.

## 4. FD lifecycle

- **Who opens it:** the source owner, once per generation, in `build_plan()`
  when `open_source` is true (`:1591-1596`).
- **FDs per model:** 1. **FDs per reader:** 0 — threads never open or close an
  FD; they use the already-installed mapping (`:1627-1635`, `:1646-1650`).
- **Lifetime:** generation-scoped. Closed in `retire_plan()` (`:1621-1624`).
- **Does the mapping survive FD close?** The code retains `map_address` and
  `map_length` in the immutable plan (`:1610-1614`) and closes the FD only at
  retirement, so in this implementation the mapping is never used after its FD
  closes. Closing the FD immediately after `mmap` would be semantically valid on
  Linux and almost certainly under gVisor, **but that is UNSUPPORTED INFERENCE
  here** — it has not been tested, and gVisor's file-descriptor lifetime
  semantics for mappings are not something this audit will assume.
- **Retained solely for old readers?** No. The single owner FD is required by the
  mapping call itself.

## 5. Per-reader duplication

| work | multiplicity under production-006 | verdict |
|---|---|---|
| arena creation / attach | 1 owner + 1 parent | REQUIRED, not 4× |
| whole `mmap` | 1 per generation | REQUIRED, not 4× |
| FD open | 1 per generation | REQUIRED, not 4× |
| mapping validation | once per generation (plan validation) | REQUIRED |
| control-table init | once per generation | REQUIRED |
| source-plan reconstruction | one shared plan object; readers adopt the same reference | REQUIRED, no 4× parse |
| **destination pointer derivation** | **per extent per reader** — `ctypes.addressof` on the slot memoryview (`:1639-1660`) | REQUIRED (each extent has a different slot) |
| interpreter/IPC setup | 0 (thread arm) | legacy process arm only |

**There is no 4× redundancy in mapping, FD, or plan reconstruction.** The only
per-reader repeated work is the destination pointer, which is inherently
per-extent. This is a clean result: the thread migration already deduplicated
the expensive setup.

## 6. Per-extent hot-path compatibility branches

| branch | location | executions / CLIP | executions / UNET | outcome under production-006 | hoistable? |
|---|---|---|---|---|---|
| `whole` vs fresh mapping | `:1646` | 120 | 184 | always `whole` | yes — into a generation-bound callable |
| `if temporary_map:` munmap | `:1673` | 120 | 184 | always false | yes |
| `_paced_copy` pacer type dispatch (`isinstance(SharedSourcePacer)`) | `:1792-1797` | 120 | 184 | always `GlobalSourcePacer` | yes — select once at startup |
| `flags` composition incl. lifecycle bits | `:1777-1779` | 120 | 184 | computed every extent, only 2 bits are constant | partially |
| `claim_block` outcome branch (claimed / no_capacity / exhausted) | `:1861-1897` | 120 | 184 | claimed ~always; the other two are correctness paths | **NO — required** |
| stale-generation rejection | `:1748-1776` | 120 | 184 | required correctness | **NO** |
| `slot_generation_changed_during_fill` check | `:767-768` | 120 | 184 | required correctness | **NO** |

Total per request: 304 evaluations of purely historical branches. Combined
Python cost is **microseconds** — not a latency surface. These are clarity
candidates only.

## 7. Range / plan metadata rebuild

| item | classification | evidence |
|---|---|---|
| safetensors header + `data_start` + `data_bytes` | deployment-static per model, cached by `inspect()` keyed on path+file identity (`golden_model_transport.py:972-984`) | CODE-PROVEN |
| layout cache hit/miss | **measured**: CLIP `layout_cache_hit=False` (first touch of `qwen_3_4b`), UNET `True` on 10/10 | DIRECTLY MEASURED |
| `layout_resolve_ms` | **measured**: CLIP p50 **36.89 ms**, max **362.26 ms**; UNET p50 **0.67 ms**, max **1.20 ms** | DIRECTLY MEASURED |
| physical range list (120/184 × 64 MiB) | generation-specific, rebuilt per load | CODE-PROVEN |
| tensor-map metadata | generation-specific | CODE-PROVEN |

**Notable measured asymmetry:** the CLIP layout resolve costs ~37 ms median and
up to 362 ms, while UNET's costs 0.67 ms because it hits the cache. That is a
real, one-off, first-model cost that is *not* source I/O. It is a candidate for
snapshot precomputation, but it is small relative to a 1.5-4.9 s source wall.

## 8. CLIP vs UNET duplication

| work | classification |
|---|---|
| payload layout parse | necessarily model-specific |
| range construction (120 vs 184 extents) | necessarily model-specific |
| whole mapping install | generation-specific, REQUIRED |
| FD open/close | generation-specific, REQUIRED |
| slot/generation reset | generation-specific, REQUIRED |
| arena, `cudaHostRegister`, CUDA stream/events, dispatcher | **deployment-static, reused** — `host_registration_reused`/`cuda_stream_reused` are `True` for UNET on 10/10, `False` for CLIP (first use) |
| source-owner process + 4 threads | **deployment-static, persist across CLIP→UNET** — `transport_runtime_reused=True`, `reader_pool_reused=True`, `staging_reused=True` on 10/10 both roles |
| telemetry schema init | deployment-static |

Measured one-time costs paid only on the CLIP (first) load:
`register_ms = 495.94 ms` (`cudaHostRegister`), `child_startup_ms = 500.78 ms`
(overlapped spawn+register), `initialization_critical_path_ns = 513.6 ms`.

**The architecture already avoids the duplication.** Threads, arena, dispatcher
and registration are created once and reused; only the per-generation mapping,
FD, plan and slots are recreated. There is no "pure duplication" finding here.

## 9. Generation-transition cleanup (CLIP retirement → UNET start)

| operation | verdict | notes |
|---|---|---|
| retire whole mapping (munmap) | **REQUIRED** | `:1621-1622` |
| close generation FD | **REQUIRED** | `:1623-1624` |
| reset slot states / control table | **REQUIRED** | generation install resets scoped state |
| increment generation | **REQUIRED** | slot generations are never reset, by design |
| clear/rebuild READY state | **REQUIRED** | |
| completion-gated slot release | **REQUIRED** | the three production-006 correctness mechanisms |
| doorbell / pending-READY handling | **REQUIRED** | `_pending_ready` prevents losing announced work |
| plan + range metadata rebuild | **REQUIRED** | different model |
| layout cache | **kept** — UNET shows `layout_cache_hit=True` | not cleared on model change |
| CUDA events / dispatcher | **MUST PERSIST** — teardown here would be wrong | reused |
| reader threads | **MUST PERSIST** — no teardown/restart occurs | reused |
| fresh-era per-extent map cleanup | NOT EXECUTED | legacy |
| reader-local state reset | generation-scoped slot/generation state only | REQUIRED |

No unnecessary teardown was found. Measured `final_drain_wall_ms`: CLIP p50
0.42 ms / max 1.53 ms; UNET p50 1.83 ms / **max 143.45 ms** (the one
post-drain outlier).

## 10. Reachability map

| stage / branch | status |
|---|---|
| production profile → C0 streaming resolution | REACHABLE |
| `GoldenModelTransport._c0_enabled` | REACHABLE (`golden_model_transport.py:758-760`) |
| C0 arena + `cudaHostRegister` + source owner spawn | REACHABLE |
| one source-owner Popen | REACHABLE |
| four persistent reader threads | REACHABLE |
| whole generation plan + mapping | REACHABLE |
| slot claim / publish / READY table / doorbell / recovery | REACHABLE (required correctness) |
| parent C0 async H2D dispatcher | REACHABLE |
| per-extent fresh mmap/munmap | REACHABLE-ONLY-IN-OTHER-PROFILE |
| `SharedSourcePacer` | REACHABLE-ONLY-IN-OTHER-PROFILE |
| four reader-process topology | REACHABLE-ONLY-IN-OTHER-PROFILE |
| parent↔reader `mp.Process`/`Pipe`/FD-invalidation | UNREACHABLE-UNDER-production-006 |
| historical M2 staging / CUDA registration path | UNREACHABLE-UNDER-production-006 |
| M1 forensic gates | REACHABLE-ONLY-when-selected (off in production-006) |

## 11. Measured cost ledger

| component | location | exec/request | CLIP exec | UNET exec | median wall | max wall | hot path? | required? | legacy origin | removal confidence |
|---|---|---|---|---|---|---|---|---|---|---|
| `cudaHostRegister` (first load only) | `golden_io_process_v2.py:1160-1190` | 1 | 1 | 0 (reused) | 495.94 ms | 495.94 ms | no | **YES** | — | must not remove |
| source-owner spawn + startup | `golden_source_threads.py:848-878` | 1 | 1 | 0 (reused) | 500.78 ms (overlapped) | 513.64 ms critical path | no | **YES** | — | must not remove |
| CLIP layout resolve (cache miss) | `golden_model_transport.py:972-1008` | 1 | 1 | 0 (hit) | 36.89 ms | 362.26 ms | no | yes, but **snapshot-precomputable** | none (first-touch only) | MEDIUM |
| whole mmap install (per generation) | `golden_source_threads.py:1594-1606` | 2 | 1 | 1 | not separately timed | not separately timed | no | **YES** | — | must not remove |
| fresh per-extent mmap/munmap branch | `:1650-1659`, `:1673-1677` | 304 | 120 | 184 | **0 (not executed)** | 0 | yes (branch) | no | **FRESH ERA** | HIGH (dead code) |
| page-align-down + window arithmetic | `:1651-1652` | 304 | 120 | 184 | **0 (not executed)** | 0 | yes (branch) | no | **FRESH ERA** | HIGH (dead code) |
| `SharedSourcePacer` type dispatch | `:1792-1797` | 304 | 120 | 184 | ~0 (a few µs) | — | yes (branch) | no | **PROCESS ARM** | HIGH |
| per-op map lifecycle telemetry fields | `OP_FIELDS` | 304 | 120 | 184 | ~0 (3 stores) | — | yes | diagnostic only | FRESH ERA | MEDIUM (keep as proof) |
| READY publication | `:1678-1690` | 304 | 120 | 184 | **0.000 ms** | 0.010 ms | yes | **YES** | — | must not remove |
| pacer 4 ms floor | `:350-395` | ~all | 120 | 184 | 36.73 ms (1.77%) | 55.70 ms (2.32%) | yes | **YES** (deliberate) | — | must not remove |
| slot wait | claim path | few | 6 | 4 | 188.49 / 198.85 ms total | — | yes | symptom, not cause | — | n/a |
| `mp.Process`/`Pipe` reader arm | `golden_model_transport.py:807-834` | 0 | 0 | 0 | **0 (not executed)** | 0 | no | no | **PROCESS READERS** | HIGH (dead code) |

## 12. Fact block

```text
CURRENT SOURCE OWNER PROCESSES = 1
CURRENT READER PROCESSES       = 0
CURRENT READER THREADS         = 4

READER PROCESS MACHINERY STILL EXECUTED   = NO (mp.Process/Pipe/per-reader FD invalidation unreachable)
FRESH-MMAP MACHINERY STILL EXECUTED       = NO (mmap_map_count=0, mmap_unmap_count=0 on 10/10 runs, 1216/1216 extents)
PER-READER FD MACHINERY STILL EXECUTED    = NO (one owner FD per generation; readers never open an FD)
PER-READER MAPPING MACHINERY STILL EXEC.  = NO (one mapping per generation, shared by all 4 threads)
PROCESS-SAFE SYNC USED ONLY BY THREADS    = NONE FOUND (the _FileLock is genuinely cross-process via the parent)
HOT-PATH MULTI-ARM BRANCHES               = 4 branches x 304 executions/request (whole-vs-fresh, temporary_map,
                                            pacer-type dispatch, map-telemetry bit composition)

RESTORE WALL ATTRIBUTABLE TO LEGACY/REDUNDANT WORK = ~0 ms (no legacy machinery executes during restore)
CLIP LOAD WALL ATTRIBUTABLE TO LEGACY/REDUNDANT WORK = ~0 ms of the 1.5-4.9 s source wall; the only removable
                                            first-touch cost is layout_resolve_ms (p50 36.89, max 362.26)
UNET LOAD WALL ATTRIBUTABLE TO LEGACY/REDUNDANT WORK = ~0 ms (layout cache hit, p50 0.67 ms)

HIGH-CONFIDENCE FUTURE REMOVAL CANDIDATE #1 = per-extent fresh mmap/munmap + page-align/window arithmetic branch
MEASURED WALL = 0 ms (never executed; 304 dead branch evaluations per request)
CORRECTNESS DEPENDENCIES = the `fresh` diagnostic profile and the epoch/fresh A/B capability. Removing it from
                            the production path requires keeping a separate implementation, not deleting the feature.

HIGH-CONFIDENCE FUTURE REMOVAL CANDIDATE #2 = SharedSourcePacer isinstance() dispatch in _paced_copy
MEASURED WALL = ~0 ms (304 dispatches/request, microseconds total)
CORRECTNESS DEPENDENCIES = the worker_kind="process" diagnostic arm. Same caveat: specialise the production path,
                            do not delete the arm.

HIGH-CONFIDENCE FUTURE REMOVAL CANDIDATE #3 = CLIP first-touch layout resolve (precompute header/data_start in snapshot)
MEASURED WALL = p50 36.89 ms, max 362.26 ms (CLIP only; UNET already 0.67 ms via cache)
CORRECTNESS DEPENDENCIES = layout cache invalidation on model identity change (golden_model_transport.py:956-962)
                            and the exact-coverage assertion on tensor offsets (golden_model_transport.py:320-342).
                            A stale precomputed header would break the storage/coverage proof.

COMPONENTS THAT LOOK LEGACY BUT ARE STILL REQUIRED =
    parent<->source-owner JSON/Pipe IPC (CUDA isolation),
    _FileLock + fcntl.flock (the parent is a separate process),
    generation IDs, slot generations, READY authoritative table, _recover_ready_from_table,
    stale-generation rejection, H2D-completion-gated slot release, 30 s gates,
    cudaHostRegister (512 MiB must be pinned for async H2D),
    READY publication itself (0.000 ms, not a cost),
    the 4 ms pacer (enforced, 1.77-2.32% of source wall, deliberately purchased).

COMPONENTS UNRESOLVED =
    whether the whole mapping remains valid after immediate FD close under gVisor (not tested; not assumed),
    per-generation cost of the whole mmap install (not separately instrumented),
    UNET final_drain_wall_ms outlier of 143.45 ms (single occurrence, unexplained),
    NUMA/topology, cgroup throttling, CPU migration: not observable in this environment
      (see GVISOR_OBSERVABILITY_MATRIX.md).
```

## 13. Bottom line

The thread + whole migration was **structurally clean**. There is no legacy
process-reader or fresh-mmap machinery executing inside production-006, no
4× duplicated setup, no per-reader FD or mapping churn, and no redundant
generation-transition teardown. The dead code that remains is branch surface
whose cost is microseconds, not milliseconds.

The one genuinely measurable non-source cost found is the **CLIP first-touch
layout resolve (p50 36.89 ms, max 362.26 ms)**, which is a snapshot-precompute
candidate rather than a legacy-removal candidate.

Removing the fresh/process arms is therefore a **code-clarity** decision with a
capability cost, not a latency win. That trade-off should be made explicitly
rather than assumed.
