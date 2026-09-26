# M2 vs E37 — minimal-overhead forensic audit

Read-only audit. No runtime source modified. M2 source engine untouched.
Evidence: historical commit `36b895d`, raw E37 artifact
`comfymodal-data/benchmarks/runs/v2_2026-08-21_22-35-45/run_001_sample.json`
(request `v2-benchmark-0-c9ac6e750942`), current commit `3f38b26` plus
`timing_runs/`, `opt_runs/`, `opt2_runs/`, `opt4_runs/`.

---

## 1. Executive answer

E37 added only ~101–106 ms above its source wall because almost everything we
pay per load was **already paid or structurally unnecessary**:

- E37 used **threads** (`_static_gpu_worker`) sharing the parent address space, so
  its staging was ordinary `torch.empty(..., pin_memory=True)` — no shared
  mapping, no `cuMemHostRegister`, no fork, no pipes, no process join.
- E37's **CUDA context already existed before hydration**: it was created during
  `restore` (`restore_gpu_state` = 212.7 ms, `cuda_init` = 3.43 ms), i.e. paid
  outside the hydration timer, at request setup. Its snapshot is CPU-only
  (`gpu_snapshot_enabled=False`, `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`).
- E37's reader module is ~1.9k lines imported at demand, and torch/Comfy were
  already imported; our current wrapper imports an 11k-line experiment module
  (~160 ms) inside the measured function.

Current M2 adds ~776 ms above source on the measured good host
(`opt4-02`: function 2141 ms, source 1365 ms). The gap is **not** the M2 source
engine and **not** the H2D. It decomposes into:

| bucket | ~ms | nature |
|---|---:|---|
| CUDA context init | 326 | harness artifact (E37 paid it at restore) |
| import of experiment oracle | 160 | harness artifact |
| fork 4 readers | 94 | process topology |
| reader teardown / pipe payload | 91 | mostly telemetry, some process join |
| `cuMemHostRegister` | 65 | process topology (E37 used torch pinned allocator) |
| staging mmap alloc | 8 | process topology (snapshot-able) |
| consumer join (final H2D drain) | 17 | CUDA/H2D |
| ready/pre-fork/collect/result | ~12 | unavoidable/trivial |

The **single biggest difference** is that E37's CUDA context and module import
were outside its hydration span while ours are inside the measured function; the
**second** is threads-vs-processes forcing shared staging + registration + fork.

`source + ~100–200 ms` is plausible for M2+processes **only if** context, arena,
registration and worker creation are hoisted once per container (and telemetry is
dropped). It is not plausible with per-load fork + per-load registration +
in-function context creation.

---

## 2. Exact E37 timing boundaries

Ledger events (`canonical_ledger.events`), ms relative to `clip_loader_start`
(mono_ns 217540276720):

| ms | event |
|---:|---|
| 0.000 | `clip_loader_start` (hydration start) |
| 16.935 | `clip_qd_source_submit_start` |
| 39.331 | `clip_qd_copy_to_device_start` |
| 1092.311 | `clip_qd_source_first_completion` |
| 1092.334 | `clip_qd_source_last_completion` |
| 1092.354 | `clip_qd_source_submit_end` |
| 1095.567 | `clip_qd_copy_to_device_end` |
| 1097.340 | `clip_qd_device_ready` (GPU-ready) |
| 1098.277 | `clip_qd_spec_record_publish` |
| 1098.308 | `clip_qd_bind` (source-side ledger) |
| 1099.144 | `clip_qd_owner_retained` |
| 1144.903 | `clip_device_ready` (hydration end) |

Reported figures: source wall `total_source_wall_ms` = **1043.514**;
submit→GPU-ready = 1097.340−16.935 = **1080.405** (report says 1080.424);
hydration ≈ **1144.9–1149.95** depending on end boundary.

Boundaries that matter:
- E37 "source wall" = thread `t_wall0` → `join` (the whole pread loop), 1043.514 ms.
- E37 "GPU-ready" = after final per-slot H2D event waits + validation, before
  tensor views. 1080.4 ms from submit.
- E37 "hydration end" = `clip_device_ready`, after take/bind ledger + pipeline
  transform + verify + real bind. 1144.9 ms.

Source engine is **pread (positioned read) with threads**, 32 MiB blocks, QD4,
240 blocks, 7.7095 GB/s — *not* M2. This audit keeps M2 and only compares the
surrounding machinery.

---

## 3. What existed before E37 hydration began

| item | state | label | evidence |
|---|---|---|---|
| Python modules (torch, Comfy, comfyapp) | present | SNAPSHOT-RESIDENT (CPU) | `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`; backend started under `_force_cpu_during_snapshot` |
| `torch` import | present | SNAPSHOT-RESIDENT | full_trace `cuda_version=13.0`; no torch import in span |
| CUDA driver init / context | **present** | CREATED BEFORE HYDRATION (at restore) | `restore_gpu_state=212.7 ms`, `cuda_init=3.43 ms`; `_restore_in_process_gpu_state` calls `torch.cuda.mem_get_info` |
| PyTorch CUDA active | present | CREATED BEFORE HYDRATION | `_initialize_cuda_context` = `torch.cuda.current_device()` + `synchronize` (3.43 ms) |
| CUDA allocator state | present | CREATED BEFORE HYDRATION | restore flips `vram_state=HIGH_VRAM` |
| pinned-memory allocator | ready (torch) | DEPLOYMENT/IMPORT STATE | first `pin_memory=True` in span; cheap |
| source workers | threads, created in span | CREATED INSIDE HYDRATION | `_static_gpu_worker`, `threading.Thread` |
| pinned host slots | created in span | CREATED INSIDE HYDRATION | 8 × 32 MiB `torch.empty(pin_memory=True)` |
| GPU destination | created in span | CREATED INSIDE HYDRATION | `torch.empty(total)` |
| safetensors metadata/layout | parsed in span | CREATED INSIDE HYDRATION | `parse_safetensors_header`, `build_header_tensor_map` |
| Comfy model object / CLIP wrapper | present (CPU) | SNAPSHOT-RESIDENT | hydration is a *load_sd* bind, not model construction |
| `QdGpuOwner` support objects | created in span | CREATED INSIDE HYDRATION | `QdGpuOwner(gpu_buf, slots, dev)` |

**CUDA context is created at restore, not snapshotted** (`gpu_snapshot_enabled=False`).
That is the decisive "absent from the timer" cost.

---

## 4. E37 ~106 ms overhead waterfall

Above source wall (1043.514 → 1144.903 = **101.4 ms**; report's 106.4 uses a
slightly later end):

| ms | segment | content |
|---:|---|---|
| 16.935 | loader_start → submit_start | speculative-take attempt, `import clip_qd_reader`, `qd_config`, `os.path.exists`, `clip_qd_load` entry, `parse_safetensors_header`, `build_header_tensor_map`, region plan, coverage, stats, `os.stat`, `mark_qd_start` |
| 22.396 | submit_start → copy_start | `torch.empty(8 GB GPU)`, 8 × 32 MiB `pin_memory=True` slots (256 MiB), 8 CUDA event pairs, `_StaticReaderState`, telemetry, 4 × `os.open`, 4 thread objects |
| ~9.5 | last source read → last_completion | post-source record validation |
| 3.233 | last_completion → copy_end | final per-slot H2D event waits (exposed tail) |
| ~2.1 | copy_end → owner_created | stats finalize, gpu validation, coverage, sync metrics, zero-copy tensor views, `QdGpuOwner` |
| ~1.8 | publish/take/bind/owner_retained | ledger events (source-side) |
| ~45.8 | owner_retained → clip_device_ready | `_apply_pipeline` transform, `_verify_file_against_manifest`, real Comfy bind, endpoint emit |

H2D totals (overlapped, not exposed): `h2d_host_issue_total_ms=127.399`,
`h2d_device_ms=27.3155` across 240 blocks. Only ~3.2 ms tail is above source.

---

## 5. Exact current M2 overhead waterfall

`opt4-02` (mode=h2d, good host): function 2141 ms, source 1365 ms, overhead **776 ms**.
Measured by `gpu_timing` + engine `timing`:

| ms | segment | source |
|---:|---|---|
| 159.7 | import (`source_race_oracle` + `source_race_gpu`) | `gpu_timing.import_ms` |
| 8.5 | staging mmap alloc | `gpu_timing.staging_alloc_ms` |
| 0.4 | consumer thread start | `consumer_start_ms` |
| 3.8 | pre-fork (stat/lanes/ctx arrays) | engine `pre_fork_ms` |
| 93.8 | fork 4 reader processes | engine `fork_ms` |
| 3.8 | reader-ready barrier | engine `ready_ms` |
| 326.5 | wait for CUDA context-init thread | `ctx_overlap_join_ms` |
| 65.2 | `cuMemHostRegister` + `cuMemAlloc` + stream | `cuda_setup_ms` |
| 1364.7 | **source wall** (M2 mmap window) | `full_file_wall_ms` |
| 91.3 | reader join + pipe payload + result build | `join_ms − source_wall` |
| 1.0 | payload collect | engine `collect_ms` |
| 16.9 | H2D consumer join (final drain) | `consumer_join_ms` |

Accounting closes to 2141 ms. The 776 ms above source is the sum of the
non-source rows.

---

## 6. E37 vs M2 mechanism table

| mechanism | E37 | M2 (3f38b26) | E37 ms | M2 ms | why | req mmap? | req proc? | req CUDA? | harness-only? | remove? | cheaper? | overlap? | snapshot CPU? |
|---|---|---|---:|---:|---|---|---|---|---|---|---|---|---|
| workers | threads | 4 processes | ~1 | 94 | shared addr vs isolated | no | yes | no | no | no | amortize/container | no | no (live procs unsafe) |
| staging | torch pinned tensors (parent-private) | anon shared mmap | incl. 22.4 | 8.5 | procs can't write parent-private | no | yes | no | no | no | snapshot arena | yes | **yes** |
| pinning | torch `pin_memory` allocator | `cuMemHostRegister` | 0 | 65 | process-shared mmap needs pinning | no | yes | yes | no | no | register once/container | no | no (CUDA) |
| CUDA ctx | at restore (212.7) | in-function | 0 (outside) | 326 | CUDA-sterile probe vs torch-live process | no | no | yes | **yes** | use existing ctx | primary ctx | yes | no |
| import | 1.9k-line reader, torch present | 11k-line oracle | ~small (in 16.9) | 160 | experiment module | no | no | no | **yes** | slim module | snapshot pre-import | n/a | **yes** |
| H2D | torch `copy_` non_blocking, per-thread stream | `cuMemcpyHtoDAsync`, one parent stream | 127.4 host / 27.3 dev (hidden) | ~150–295 active (hidden) | parent owns CUDA | no | yes | yes | no | no | more streams (not needed) | already | no |
| events | per-slot reuse | fresh per transfer | small | small | task design | no | no | yes | no | reuse per-slot | — | yes | no |
| slots | 2/worker (8 × 32 MiB) | 1/lane (4 × 64 MiB) | 256 MiB | 256 MiB | geometry | no | no | no | no | no | — | — | yes (mapping) |
| GPU dest | `torch.empty` | `cuMemAlloc` | incl. 22.4 | ~2 | raw driver vs torch | no | no | yes | no | no | torch allocator | — | no |
| owner/views | `QdGpuOwner` + zero-copy views | none | ~2 (+45 bind) | 0 (missing) | needed for Comfy use | no | no | no | no | **add (minimal)** | reuse E37 concept | — | no |
| worker completion | thread join (in source wall) | process join + pipe | in 1043 | 91 | processes | no | yes | no | partly telemetry | drop telemetry | shared counter | no | no |
| telemetry | stats/ledger (in span) | `physical_attempts_log`, `logical_reads` | included | part of 91 | benchmark | no | no | no | **yes** | drop in prod | — | — | n/a |
| result collect | in-process dict | pipe recv + serialize | ~0 | ~1–91 | processes | no | yes | no | partly | slim | — | — | n/a |

---

## 7. Minimum overhead forced specifically by processes

Keeping 4 mmap reader processes (required), the genuinely forced extras vs
threads are:

1. **Shared host mapping** — children cannot write parent-private pinned memory.
   Forced. Cost ~8 ms (mmap) and it is snapshot-able as CPU state.
2. **Pinning the shared mapping** — `cuMemHostRegister` (40–65 ms) is required
   because the staging is not from a pinned allocator. Forced *given post-fork
   CUDA init*. Amortizable once per container.
3. **Fork** — 78–170 ms (typ. 94) per creation. Forced per worker set; amortizable
   once per container across CLIP and UNET loads.
4. **Parent-side CUDA consumer** — children must not own CUDA; the parent must
   submit H2D and gate slot reuse. Forced. ~17 ms drain + ~1 ms/transfer.
5. **Process join / payload** — to know the source is complete. Minimum is a
   shared completion counter; the pipe + `physical_attempts_log` are **not**
   forced (telemetry only).

Not forced, currently paid: per-load registration, per-load fork, in-function
context creation, 11k-line import, full telemetry payload.

`cuMemHostRegister` is not avoidable by "allocate pinned in parent before fork"
without initializing CUDA before fork; forking a CUDA-initialized process is the
hazard the current design avoids. So accept 40–65 ms, once per container.

---

## 8. Pinned-memory architecture comparison

- **E37**: `torch.empty(block_bytes, dtype=uint8, pin_memory=True)` — PyTorch
  caching host allocator (`cudaHostAlloc`/registration internally). Threads write
  directly into it; `gpu_buf[...].copy_(slot, non_blocking=True)` on the current
  stream; per-slot `torch.cuda.Event` for reuse. No raw registration in user code.
- **M2**: anonymous `MAP_SHARED` mmap (fork-inherited) + `cuMemHostRegister`,
  then `cuMemcpyHtoDAsync`. Registration is required only because the producer is
  a process-shared mapping that CUDA does not already know as pinned.
- **Feasibility of inheriting a pinned allocation across fork**: NOT recommended.
  It requires a CUDA context before fork (the child then inherits CUDA state),
  pinned mappings are not guaranteed valid/shared post-fork, and gVisor/Modal
  fork-after-CUDA is the exact hazard the current seam avoids. Do not trade
  correctness for 50 ms.

---

## 9. CUDA context comparison

- E37: context created at **restore** via `_restore_in_process_gpu_state`
  (`torch.cuda.mem_get_info`) = 212.7 ms, then `_initialize_cuda_context`
  (device + `synchronize`) = 3.43 ms. **Outside** the hydration span.
- M2: `e04` is deliberately CUDA-sterile; the function calls `cuInit` +
  `cuCtxCreate` after fork = 208–854 ms (typ. 326). It does **not** use PyTorch's
  primary context, because the probe process never imports torch.
- Production reality: the loader runs in the Comfy process, which already has a
  CUDA context (Comfy `model_management`/torch). The correct M2 production path
  is to make the **existing/primary context current** and register — no
  `cuCtxCreate`. That makes the context cost ~0 per load, matching E37.
- The current 326 ms is a **harness artifact of a CUDA-sterile probe**, not an
  M2 mechanic.

---

## 10. Import / dependency comparison

- E37: `from .clip_qd_reader import clip_qd_load, qd_config` at demand (inside
  the 16.9 ms pre-submit bucket); `clip_qd_reader.py` = 1935 lines; torch/Comfy
  already imported (snapshot-resident).
- M2: `from comfymodal_runtime.source_race_oracle import run_mmap_source_probe`
  = 11,367 lines parsed per call = ~160 ms; `source_race_gpu` is small.
- The 160 ms is experiment-only code. Minimum production module = the M2 window
  engine (`_mm2_child` + `run_mmap_source_probe` plumbing) + `source_race_gpu`
  seam, extracted into a small `m2_source_core`-style module, used by both the
  oracle and production. Pure-Python and snapshot-safe (pre-import at capture),
  but the correct framing is *smaller module*, not *moved import*.

---

## 11. Worker completion / teardown comparison

- E37: `for t in threads: t.join()` — thread join inside the source wall;
  post-source work is validation (~9.5 ms) + final event waits (3.2 ms).
- M2: `proc.join(timeout=…)` per process, then `conn.recv()` per process carrying
  `physical_attempts_log` (120 records × ~15 fields) + `logical_reads`, then
  result construction. Measured post-source = 91 ms.
- Minimum correctness after last source block + last H2D complete + exact GPU
  destination: know every reader has stopped and every block was published. A
  shared `completed` counter already exists and is sufficient; the pipe payload
  and per-op telemetry are benchmark-only. Process join can be replaced by
  waiting on the shared counter, with `terminate()` only on error.

---

## 12. E37 GPU-owner / tensor-view / bind path

E37 turned flat GPU bytes into Comfy weights with:

1. `tensor_map = build_header_tensor_map(header)` (safetensors header → per-key
   `(key, dtype, shape, rel_start, length)`).
2. Zero-copy views: `sd[key] = gpu_buf[rel:rel+length].view(dt).view(shape)`
   (rare misalignment falls back to a copy).
3. `QdGpuOwner(gpu_buf, slots, device)` — owns the buffer + pinned slots; tensors
   are views valid while the owner lives; `close()` idempotent.
4. Caller `_apply_pipeline` + `_verify_file_against_manifest` + real Comfy bind
   (`assign=True` mutable tensors; QD built under `torch.inference_mode(False)`).
5. `clip_device_ready`.

Cost ≈ 2 ms views/owner + ~45.8 ms transform/verify/bind in-span. No Golden
proof/adoption framework was needed — this is a light concept we can reuse
directly around an M2-produced contiguous GPU allocation.

---

## 13. Snapshot-safe setup opportunities

Container is restored from a **CPU** memory snapshot.

| candidate | label | evidence |
|---|---|---|
| slim loader module imported | **SAFE SNAPSHOT STATE** | pure Python; E37 backend snapshot-resident |
| parsed Python modules / code | **SAFE** | CPU snapshot |
| pure CPU config / qd_config / static metadata | **SAFE** | CPU |
| static safetensors header/layout | **SAFE if model generation identity permits** | CPU parse |
| anonymous shared mmap staging mapping | **SAFE** | CPU mapping; lazy pages ~0 resident |
| mp control structures (Value/Array) | **SAFE** | CPU shared memory |
| CUDA context | **UNSAFE / CURRENT CONTRACT FORBIDS** | `gpu_snapshot_enabled=False`; CPU snapshot forces CPU; CUDA created at restore |
| CUDA stream / event | **UNSAFE** | as above |
| registered pinned pages | **UNSAFE** | CUDA driver object; not snapshotted |
| GPU allocation | **UNSAFE** | no GPU snapshot |
| live worker process | **UNSAFE** | fork must be post-restore |
| live checkpoint FD | **CURRENT CONTRACT FORBIDS** (readers not retained) | restore contract |

So: pre-import, arena mapping, config and static metadata are legitimately
snapshot-resident (removed from the per-load critical path). CUDA objects are not;
they are paid once per container after restore (as E37 did at restore).

---

## 14. Current overhead classification (~776 ms, `opt4-02`)

| ms | bucket | class |
|---:|---|---|
| 326.5 | CUDA context init | **REPLACE WITH CHEAPER** (use existing/primary context in production) |
| 159.7 | import experiment oracle | **REMOVE ENTIRELY** (slim module) / **SNAPSHOT** (pre-import) |
| 93.8 | fork 4 readers | **REQUIRED BY PROCESS TOPOLOGY** / **OVERLAP**/amortize per container |
| 91.3 | reader join + pipe payload + result | **REMOVE ENTIRELY** (telemetry) + minimal process join |
| 65.2 | `cuMemHostRegister` + alloc | **REQUIRED BY PROCESS+CUDA** / amortize once per container |
| 16.9 | H2D consumer join | **REQUIRED BY CUDA/H2D** |
| 8.5 | staging mmap alloc | **SNAPSHOT AS PURE CPU STATE** |
| 3.8 | pre-fork | required/trivial |
| 3.8 | ready barrier | required/trivial |
| 1.0 | collect | required/trivial |
| ~2 | result build/return | trivial |

No unexplained residual; categories close to 776 ms.

---

## 15. Minimal M2 production wrapper

Derived sequence (justify each step):

1. **Loader + config already resident** — pre-imported at snapshot capture (CPU);
   E37 equivalent: backend/torch snapshot-resident. Removes ~160 ms.
2. **Staging mapping already resident** — anonymous shared mmap created at
   capture; lazy pages. E37 equivalent: none needed (threads) but cost is ~0.
   Removes ~8 ms.
3. **Use the process's existing CUDA context** (make primary context current);
   no `cuCtxCreate`. E37 equivalent: context at restore. Removes ~326 ms.
4. **Register the arena once per container** and reuse for CLIP and UNET;
   `cuMemAlloc` the GPU destination once per load (or resize). E37 equivalent:
   pinned allocator + `torch.empty`. Amortizes ~65 ms.
5. **Fork four M2 readers once per container**, re-target to each file; or fork
   per load if isolation is required. E37 equivalent: threads (no fork). Cost is
   the process tax.
6. **GO → source/H2D pipeline unchanged** (M2 mmap, QD4, 64 MiB, 4 ms pacing;
   parent `cuMemcpyHtoDAsync` with per-transfer fresh events, slot reuse gated on
   completion). E37 equivalent: thread pread + `copy_`.
7. **Minimal completion** — wait on the shared `completed` counter for all
   readers; wait the final H2D event; no per-op payload. E37 equivalent: thread
   join + final event waits. Removes most of ~91 ms.
8. **Minimal usable-GPU adapter** — reuse the E37 concept: safetensors header →
   `gpu_buf[rel:rel+len].view(dt).view(shape)` zero-copy views + a minimal owner;
   hand to Comfy bind. ~2 ms views + existing bind.
9. **Return.** No Golden proof framework.

Nothing else is required. Step 3 is the largest single change; steps 1–2 are
snapshot; steps 4–5 are per-container hoists; step 7 is a correctness-minimal
replacement for telemetry.

---

## 16. Estimated achievable cold restored-container wall

- **A. Current M2 floor** (existing architecture, landed fixes): source + ~500–800 ms
  (measured 776 on the example host; ~500 on faster hosts).
- **B. Minimal M2+processes floor** (only safe/removable changes; M2 mechanics
  unchanged): per-load ≈ source + ~80–150 ms, plus per-container fork+register
  (~160 ms) amortized across CLIP+UNET → ≈ source + ~160–230 ms per load.
- **C. E37-like target**: `source + ~100–200 ms` is technically plausible for
  M2+processes **if** context is the process's existing context, arena+register+
  fork are hoisted per container, telemetry is dropped, and the E37-style
  view/owner/bind is reused. It is **not** plausible with per-load fork, per-load
  registration, in-function context creation, or the full telemetry payload.

Process-specific unavoidable tax (quantified): fork ~94 ms + shared staging
~8 ms + register ~65 ms + parent consumer/drain ~17 ms + minimal process join
~10–30 ms ≈ **~194 ms per container**, ≈ ~97 ms per load amortized over the two
model loads. That is the honest floor difference vs threads.

---

## 17. Exact minimum changes, ordered by payoff/risk

1. **Use the existing/primary CUDA context instead of `cuCtxCreate`** (~326 ms;
   low risk, largest payoff). In the harness this means importing torch or
   retaining the primary context; in production it is free.
2. **Drop per-op telemetry from the publication path** (~80 ms of the 91 ms;
   low risk). Wait on the shared `completed` counter; keep `physical_attempts_log`
   only when a benchmark flag is set.
3. **Hoist arena + registration + workers to once per container** (~65 ms + ~94 ms
   per load; medium risk — needs clean re-target between CLIP and UNET).
4. **Slim/extract the M2 engine into a small module (or pre-import at snapshot)**
   (~160 ms; medium risk — must preserve byte-identical M2 behavior).
5. **Pre-create the shared mmap arena at snapshot capture** (~8 ms; low risk).
6. **Add the E37-style minimal view/owner/bind adapter** (needed for Comfy-usable
   output; adds ~2 ms views + bind, but is the missing production step).

Do not change: M2 mmap algorithm, MAP_PRIVATE window behavior, QD4, 64 MiB,
4 ms pacing, four-process topology, source allocator, source scheduling.

---

    E37 SOURCE WALL:
    1043.514 ms (pread threads, 32 MiB, QD4, 240 blocks, 7.7095 GB/s)

    E37 TOTAL HYDRATION:
    ~1144.9–1149.95 ms (clip_loader_start -> clip_device_ready)

    E37 ABOVE-SOURCE OVERHEAD:
    ~101.4 ms (106.4 by report boundary)

    E37 COSTS PAID BEFORE HYDRATION:
    CUDA context init ~212.7 ms at restore (restore_gpu_state), cuda_init 3.43 ms,
    torch/Comfy imports snapshot-resident, CPU-only snapshot (gpu_snapshot_enabled=False)

    CURRENT M2 SOURCE WALL:
    ~1365 ms typical (mmap window, 64 MiB, QD4, 4 ms pacing, ~6 GB/s)

    CURRENT M2 ABOVE-SOURCE OVERHEAD:
    ~776 ms measured (opt4-02: function 2141 - source 1365)

    PROCESS-SPECIFIC UNAVOIDABLE TAX:
    ~194 ms per container (fork ~94 + staging ~8 + register ~65 + parent CUDA
    consumer/drain ~17 + minimal join ~10-30); ~97 ms/load amortized over CLIP+UNET

    CURRENT OVERHEAD THAT IS PURELY REMOVABLE:
    ~160 ms import + ~80 ms telemetry payload + ~326 ms in-function context init
    (context is removable in production by using the existing context) = ~566 ms

    CURRENT OVERHEAD WITH CHEAPER E37-LIKE ALTERNATIVE:
    fork/register/staging hoisted per container (E37 paid these at restore /
    never); E37-style views/owner/bind replaces nothing today because M2 has none

    CURRENT OVERHEAD SAFE TO SNAPSHOT:
    slim loader module (pre-import), anonymous shared mmap arena, pure CPU config,
    static safetensors metadata (generation-permitting), mp control structures
    (~170 ms)

    MINIMUM REQUIRED CHANGES TO M2:
    1. Use the process's existing/primary CUDA context; no cuCtxCreate.
    2. Wait on the shared completion counter; drop per-op telemetry from publication.
    3. Hoist arena + registration + workers to once per container (reuse for CLIP+UNET).
    4. Extract/pre-import a small M2 source module; add the minimal E37-style view/owner/bind.

    EXPECTED M2+PROCESSES OVERHEAD AFTER MINIMAL CHANGES:
    ~80-150 ms per load + ~160 ms per-container (amortized ~97/load) = ~160-230 ms/load

    IS SOURCE + ~100-200 MS PLAUSIBLE:
    YES (conditionally)
    Evidence: E37's own above-source was 101 ms because context+import were outside
    its timer and threads needed no shared mapping/registration/fork. With the
    process's existing context, snapshot-resident import+arena, per-container
    fork/register, and telemetry removed, M2's remaining above-source is final H2D
    tail (~3 ms) + E37-style views/owner/bind (~2-45 ms) + minimal join. If fork and
    registration stay per-load, the floor is ~250-350 ms and 100-200 ms is not reachable.

    SINGLE BIGGEST DIFFERENCE BETWEEN E37 AND M2 WRAPPER:
    E37 created its CUDA context and imported its loader OUTSIDE the measured span
    (context at restore; torch/Comfy snapshot-resident), and used threads so no
    shared-mapping registration or fork existed. Our wrapper creates a raw CUDA
    context and imports an 11k-line module INSIDE the function, and processes force
    shared staging + cuMemHostRegister + fork — ~486 ms of the 776 ms is
    harness/lifecycle, not M2 source or H2D.
