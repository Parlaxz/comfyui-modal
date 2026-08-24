# R44G2 — CLIP/UNET Physical Throughput Forensics and Historical 40+ GB/s Reconciliation

Batch: R44G2 · Lane: READ-ONLY FORENSICS · Date: 2026-08-24
Worktree: `../comfyui-modal-r42` · Branch: `r42-golden-reconciliation`
Constraints honored: no runtime code changed, no deploy, no Modal run, no paid request, no remote model read.
Only file created by this lane: this report.

Companion lanes: R44F, R44G1 (concurrent). Note: `COMFYUI_MODAL_V2_PERFORMANCE_HISTORY_AND_RECOVERY_HANDOFF_2026-08-23.md` did not exist in either tree at analysis time; its content could not be consumed. All evidence below comes from artifacts present in the worktree.

---

## 0. Question

Why are current integrated physical model transfers (R44E: CLIP 4.159 GB/s, UNET 19.706 GB/s at the exact FastSafe `copy_files_to_device` boundary) much slower than historical ~40–50 GB/s-class source probes and adjacent measurements?

---

## 1. Measurement taxonomy (mandatory)

Classes:
A raw source/storage read · B source->host/pinned staging · C direct file->CUDA transport ·
D broad H2D/activation window · E integrated model-loader node · F page-cache-warmed transfer ·
G true first-touch/cold transfer · H sequential/warmed probe (battery position >= 2 over the same file)

"Comparable to R44E CLIP" = same boundary (`copy_files_to_device` wall), same file class, CLIP cold first-touch.
"Comparable to R44E UNET" = same boundary, UNET file, page-cache-warmed by full source prep.

| # | Label | Class | Bytes | Wall ms | GB/s | Cache state | Destination | Exact boundary | Source (file:line) | ~R44E CLIP? | ~R44E UNET? |
|---|---|---|---:|---:|---:|---|---|---|---|---|---|
| 1 | R44E CLIP FastSafe copy | C+G | 8,044,982,048 | 1,934.712 | 4.159 | true first-touch (descriptor_cache_hits=0; first payload access in cold request) | CUDA cuda:0 | perf_counter around `loader.copy_files_to_device(...)` only | RAW_LOG.txt:135; clip_fast_hydration_wiring.py:837-845 | — (baseline) | no (cold, not warm) |
| 2 | R44E CLIP file->GPU aggregate | C+G+E | 8,044,982,048 | 2,117.326 | 3.800 | cold | CUDA | setup+copy+get_keys+tensor loop (excl. bind 2670.5) | RAW_LOG.txt:123,134-137 | yes (broader) | no |
| 3 | R44E CLIP loader node | E | 8,044,982,048 | 4,825.536 | 1.667 | cold | CUDA+bind | t4_clip_load_start->end (incl. bind_mode=copy_cuda) | RAW_LOG.txt:260-261 | broader | no |
| 4 | R44E load_models_gpu(CLIP) | E | ~8.10 GB alloc delta | 2,283.612 | — | post-load | CUDA | second model-sized materialization inside ComfyUI | RAW_LOG.txt:218-219 | no (different seam) | no |
| 5 | R44E UNET FastSafe copy | C+F | 12,309,866,400 | 624.6765 | 19.706 | page-cache-warmed (full source prep completed before demand) | CUDA | perf_counter around `copy_files_to_device` only | RAW_LOG.txt:179,187; unet_fastsafetensors.py:902-908 | no (warm) | — (baseline) |
| 6 | R44E UNET loader node | E+F | 12,309,866,400 | 819.495 | 15.02 | warm | CUDA | t4b_unet_load_start->end | RAW_LOG.txt:264-265 | no | broader |
| 7 | R44E UNET source prep | B (host read only) | 12,309,866,400 | 4,827.1 (armed->joined) | 2.550 | cold->warms cache | host page cache | plain Python open(buffering=0)+readinto, 4 threads x 8 MiB chunks | RAW_LOG.txt:152-173,199-206; checkpoint_prewarm.py:205-212 | no | no (it is the warmer) |
| 8 | R44E "UNET H2D" GPU-lane span | D | 12,309,866,400 | 741.786 | 16.60 | warm | CUDA | trace span incl. adopt/setup around copy | RAW_LOG.txt:233-234 | no | yes (broader) |
| 9 | R44D cold gate CLIP node | E+G | 8,044,982,048 | 6,462 (window) | ~1.24 | true cold | CUDA | node window, telemetry not persisted per-event | R44D report:11-21,128-145 | consistent band | no |
| 10 | R44D broad UNET H2D | D | 12,309,866,400 | 2,719.655 | 4.53 | cold | CUDA | copy+instantiate+adoption (NOT pure H2D) | Inventory:80-90,124-132 | no | consistent band (cold) |
| 11 | E28 UNET FastSafe bbuf512 | C+F/H | 12,309,866,400 | 477 | 25.81 | warm-class (later cell in tuning battery; 2,014 ms -> 477 ms progression same session) | CUDA | fastsafe_file_gpu_wall_ms | E28 report:38-59 | no | yes (same class, faster) |
| 12 | E27 sequential cells CLIP ~490 / UNET ~700 | H (+C) | ~8.04 GB / ~12.31 GB | ~490 / ~700 | ~16.4 / ~17.6 | warm/sequential (cell 0 only was true first-touch) | CUDA | FastSafe copy-class cells in sequential battery | E27 report:277-287,359-403 | no (warm) | yes (class) |
| 13 | E27 UNET QD1 cold raw read | A+G | 12,309,817,472 | 1,866.0 | 6.60 | true cold (first cell, fresh container) | host buffers | custom preadv QD probe, 32 MiB blocks, NO CUDA | E27 report:255-262 | no (raw read) | no |
| 14 | E27 UNET QD1 warm control | A+F | 12,309,817,472 | 1,081.8 | 11.38 | page-cache-warmed | host buffers | same probe, second pass | E27 report:258 | no | no |
| 15 | E27 UNET QD2 | A+F/H | 12,309,817,472 | 534.2 | 23.04 | battery pos>=2 (cache state unproven; see 4.3) | host buffers | preadv, 2 streams | E27 report:259 | no | no |
| 16 | E27 UNET QD4 | A+F/H | 12,309,817,472 | 283.3 | 43.45 | battery pos>=3 (unproven cache; see 4.3) | host buffers | preadv, 4 streams, NO CUDA | E27 report:260 | no | no |
| 17 | E27 UNET QD8 | A+F/H | 12,309,817,472 | 248.1 | 49.61 | battery pos>=4 (unproven cache; see 4.3) | host buffers | preadv, 8 streams, NO CUDA | E27 report:261 | no | no |
| 18 | E27 UNET QD16/128MiB | A+F/H | 12,309,817,472 | 538.6 | 22.86 | battery pos>=5; CPU-bound (1,690 ms CPU) | host buffers | preadv, 16 streams | E27 report:262 | no | no |
| 19 | E27 CLIP QD1 cold raw read | A+G | 8,044,982,048 | 1,047.3 | 7.68 | true cold (first cell) | host buffers | preadv QD probe, NO CUDA | E27 report:366 | no | no |
| 20 | E27 CLIP QD1 warm control | A+F | 8,044,982,048 | 753.9 | 10.67 | warmed | host buffers | second pass | E27 report:367 | no | no |
| 21 | E27 CLIP QD4 | A+F/H | 8,044,982,048 | 191.4 | 42.03 | battery pos>=3 (unproven cache) | host buffers | preadv, 4 streams | E27 report:369 | no | no |
| 22 | E27 CLIP QD8/64MiB | A+F/H | 8,044,982,048 | 178.8 | 45.00 | battery pos>=4 (unproven cache) | host buffers | preadv, 8 streams | E27 report:370 | no | no |
| 23 | E27 CLIP native mmap baseline | A+G | 8,044,982,048 | 7,370.8 | 1.09 | cold | host (mmap) | Comfy load_torch_file path | E27 report:373-375 | no | no |
| 24 | E27 UNET QD4 storage->pinned->async H2D | D | 12,309,817,472 | 1,020.9 (device event 1,020.8) | 12.06 | battery-context | CUDA via pinned | combined pipeline incl. device copy | E27 report:268-270 | no | yes (H2D-class) |
| 25 | E27 CLIP QD2 storage->pinned->async H2D | D | 8,044,982,048 | 700.2 (event 703.2) | 11.49 | battery-context | CUDA via pinned | combined pipeline | E27 report:377-378 | yes (H2D-class) | no |
| 26 | E27 UNET FastSafe screen 8T | C+F/H | 12.31 GB | 740.0 (copy) | 16.63 | warm battery | CUDA | SafeTensorsFileLoader screen | _e27_fastsafe_unet_out.txt:528-537 | no | yes |
| 27 | E27 UNET FastSafe direct CUDA 16T/1GiB | C+F/H | 12.31 GB | ~592 | 20.78 | warm battery | CUDA | loader screen (then-production 1 GiB block) | E27 report:272-275 | no | yes |
| 28 | E27 CLIP FastSafe direct CUDA 16T/1GiB | C+F/H | 8.04 GB | ~496 | 16.22 | warm battery | CUDA | loader screen | E27 report:380-381 | yes (but warm) | no |
| 29 | C9 true-cold UNET FastSafe file->GPU | C+G | 12,309,817,472 | 2,172.92 | 5.67 | true cold (standalone battery, controls per C9 method) | CUDA | FastSafe copy boundary | C9 report:137-160,209-211 | no (UNET file) | no (cold twin of #5) |
| 30 | C9 cache-warm UNET result | C+F | 12.31 GB | 924 | 13.32 | explicitly classified cache-warm | CUDA | same boundary | C9 report:209-211 | no | yes (band) |
| 31 | E37 clean-lane CLIP QD4 raw source | A(+G) | 8,044,982,048 | 1,043.514 | 7.710 | clean-lane cold-class | host buffers | QD4/32 MiB, 4 workers, NO CUDA | E37 report:20-38 | no | no |
| 32 | E37 CLIP H2D host issue / CUDA event | D | partial (documented sub-stage) | 127.399 / 27.316 | — | — | CUDA | paired issue/event timings; byte scope not fully documented | E37 report:20-38 | partial | no |
| 33 | R42 Golden CLIP cold QD source | A+G+E | 8,044,982,048 | 4,491.6 | 1.79 | integrated cold, occupancy collapse 1.68% | host buffers | golden pipeline QD stage | R42 report:315-353 | consistent band | no |
| 34 | R42 Golden UNET prep | B+G | 12,309,866,400 | 5,409.7 | 2.276 | cold, fully hidden | host page cache | golden prep stage | R42 report:315-367 | no | no |
| 35 | R42 Golden UNET commit/H2D | D+F | 12.31 GB | 878.5 | 14.012 | explicitly cache-served | CUDA | golden commit stage | R42 report:315-367 | no | yes (band) |

Boundary-equivalence summary: NOTHING in the historical set measures 40+ GB/s at boundary C (direct file->CUDA). The 40–50 GB/s cluster lives entirely at boundary A (raw host-side reads, no CUDA). The only same-boundary twins are: #29 (cold twin of #5) and #11/#26/#27/#30/#35 (warm cohort of #5); #1 has no prior same-boundary CLIP cold twin at all.

---

## 2. CLIP 4.159 GB/s — what is inside 1,934.712 ms

### 2.1 Verified mechanics of the timed region

Timed region (`clip_fast_hydration_wiring.py:837-845`, t0/t1 perf_counter around the single library call):

- Library: fastsafetensors 0.3.3 (`foundation-model-stack/fastsafetensors`, tag `0.3.3`, commit daf6cc3).
- Constructor args actually passed: `pg=None`, dev=`cuda:0`, `max_threads=8`, `bbuf_size_kb=524288`, `nogds=True`, `disable_cache=True` (r44-request-fastsafe.toml:43-45; wiring :820-830).
- `copy_files_to_device(use_buf_register=False, max_copy_block_size=268435456)`.

What the library does inside (upstream source, tag 0.3.3):

1. `LazyTensorFactory` per file; header parse; tensor byte-range selection.
2. NOGDS copier: `nogds_file_reader(False, bbuf_size_kb=524288, max_threads=8, ..., device_id)`.
   - Constructor divides the pool: `_bbuf_size_kb = ceil(524288/8) = 65536 KB = 64 MiB per slot`; allocates ONE pinned host pool via `cudaHostAlloc(buf_len = 65536*1024*8 = 512 MiB)` (cpp/ext.cpp).
3. Python submit loop splits the file into <=256 MiB requests (`max_copy_block_size` caps REQUEST size only).
4. Each request runs on rotating `std::thread` slot `thread_id % 8`; a slot reuse JOINS the prior thread first (ext.cpp). Per request, the slot loops:
   - `pread(fd, pinned_slice, <=64 MiB, offset)`
   - `cudaMemcpy(dst_dev, pinned_slice, c, cudaMemcpyHostToDevice)` — SYNCHRONOUS, implicit null stream
   - repeat until request done. NO double buffering, NO intra-slot read/copy overlap.
5. `wait_io()` joins all slots. Return.

Therefore `fastsafe_copy_wall_ms=1934.712` contains: header/factory setup, all cold storage `pread`s, all pinned-staging activity, all (serialized) H2D memcpys, and all slot joins. It EXCLUDES: descriptor 27.547 ms, setup 11.272, get_keys 0.018, tensor loop 0.317, bind 2670.544 (bind_mode=copy_cuda — a SECOND materialization), and the explicit `torch.cuda.synchronize()` which sits after the timed region on the direct hydration path (clip_fast_hydration.py:645-652).

### 2.2 Hypothesis adjudication

| Hypothesis | Verdict | Evidence |
|---|---|---|
| H1 Cold Modal Volume/source delivery dominates | STRONGLY SUPPORTED | True first-touch: descriptor_cache_hits=0, first payload access of the cold request (RAW_LOG:111-150). Genuine-cold rates in this environment cluster at 1.79–7.71 GB/s: E27 QD1-cold raw 6.60/7.68 (#13,#19), C9 true-cold FastSafe 5.67 (#29), R42 golden integrated cold 1.79 (#33), R44D cold node ~1.24 (#9). 4.159 sits inside that band. NOT PROVEN to be the sole cause: no per-phase counter exists inside `copy_files_to_device`. |
| H2 FastSafe NOGDS read->copy serialization suppresses storage queue depth | PROVEN as mechanism; PLAUSIBLE as major quantified contributor | Upstream ext.cpp/nogds.py: each slot alternates blocking `pread` with synchronous `cudaMemcpy`; while a slot copies, it issues no storage reads; effective storage concurrency < 8. E27 showed thread/block regime sensitivity (8T 6.66 vs 16T 20.78 GB/s, #26/#27). |
| H3 Null-stream cudaMemcpy serialization caps warm ceiling (~20–26 GB/s) and adds structure to cold time | STRONGLY SUPPORTED | Synchronous `cudaMemcpy` on implicit default stream (upstream ext.cpp); legacy null stream serializes against prior work; warm measurements cluster 16.22–25.81 GB/s (#11,#26,#27,#30,#35) ~= single-copy pinned regime. For CLIP cold, serialized-copy floor ~= 8.04 GB / ~20 GB/s ~= 400 ms << 1935 ms, so copies alone do not explain CLIP. |
| H4 Host staging / bounce buffer misconfiguration | FALSIFIED | bbuf512 KiB-param = TOTAL pool -> 64 MiB pinned per slot (upstream constructor math). Healthy, not starved. `use_buf_register=False` is GDS-only (`cuFileBufRegister`) and inert in NOGDS (upstream gds.py). |
| H5 `disable_cache=True` slows reuse | FALSIFIED | It disables only the distributed shuffle/tensor cache (tensor_factory.py); zero effect on OS page cache or reads. |
| H6 Block size B256MiB bottleneck | FALSIFIED as primary | `max_copy_block_size` caps request size; internal chunking is per-slot bbuf (64 MiB) regardless. E27 2-GiB screen showed larger blocks monotonically worse on short windows; 256 MiB requests are not the binding constraint. |
| H7 PCIe / device link limit | UNKNOWN | No PCIe gen/width telemetry recorded anywhere in the worktree (searched). Cannot be assigned blame or cleared. |
| H8 CPU contention | PLAUSIBLE contributor | Heavy process CPU in adjacent phases (clip_raw_encode process_cpu 14,520 ms; QD16 CPU-bound precedent at 22.86 GB/s). During the copy window specifically, concurrent runtime work is not instrumented. |
| H9 Thread count T8 undersized for cold storage | PLAUSIBLE | E27 screens: UNET 8T 6.66 -> 16T 10.13 (CPU) and 16T direct 20.78 vs 8T-class much lower (#26/#27). Never tested true-cold at integrated boundary. |

Bottom line: 4.159 GB/s is the cold band for this environment at this boundary, shaped by (a) genuinely cold network-volume delivery, (b) a reader whose per-slot serial pread->memcpy alternation keeps effective storage queue depth below 8, plus (c) serialized null-stream copies. It is NOT a regression against any same-boundary cold predecessor: the only same-boundary cold UNET ancestor is C9 at 5.67 GB/s (#29), and CLIP cold has no same-boundary ancestor at all (E27's 16.22 #28 was a warm battery screen).

Arithmetic sanity: 8 slots x 64 MiB chunks; if per-slot cycle = cold pread(~119 ms) + memcpy(~3.2 ms), aggregate = 8 x 64 MiB / 122.5 ms ~= 4.2 GB/s — matches observed. The implied per-stream cold fetch rate (~0.54 GB/s effective including latency exposure) is far below the standalone QD1-cold probe (6.60 GB/s), which is the integrated-vs-probe gap independently corroborated by R42 golden (#33: 1.79 GB/s integrated cold QD with occupancy collapse). Residual uncertainty: the split between storage latency/duty-cycle loss and in-process contention cannot be decomposed without per-phase counters inside the library call.

---

## 3. UNET 19.706 GB/s — why warm page-cache->CUDA

Chain of custody, each step evidenced:

1. Source prep read the FULL file before demand: `targeted_bytes = touched_bytes = 12,309,866,400`, `read_count=1468`, `stop_reason="completed"`, `finished_before_demand=true`, `source_fence_valid=true` (RAW_LOG:152-173). Mechanism: plain Python `open(path,"rb",buffering=0)` + reusable bytearray + `readinto`, 4 threads x 8 MiB chunks, advisory `POSIX_FADV_SEQUENTIAL` (checkpoint_prewarm.py:205-212,392-400).
2. Ordinary `read()`/`pread()` populates the Linux page cache. The repo's own code disclaims residency proof (checkpoint_prewarm.py:215-229) — correctly: `source_fence_valid` guarantees only that the prep workers JOINED after touching every byte. It does not guarantee residency. But with a 48 GiB vehicle memory shape (repo taste.md env fact) and a 12.31 GB file read seconds earlier, eviction of the whole file is implausible; and the outcome matches residency precisely (see 4).
3. `disable_cache=True` does NOT bypass Linux page cache — upstream it gates only the shuffle-result dict (tensor_factory.py). Nothing in the stack evicts or avoids page cache.
4. Therefore FastSafe's `pread` calls in the copy hit page cache: each 64 MiB chunk is a RAM->pinned-RAM copy (~10+ GB/s per stream, cf. warm-QD1 controls 11.38/10.67 #14,#20) instead of a network fetch. The per-slot cycle becomes memcpy-dominated.
5. All 8 slots' `cudaMemcpy` calls execute on the implicit null stream and serialize in the driver; aggregate delivery converges to the single-copy pinned H2D regime.
6. Result: 12.31 GB / 624.6765 ms = 19.706 GB/s — squarely inside the environment's warm file->CUDA band: 16.22 (#28), 16.63 (#26), 20.78 (#27), 13.32 (#30), 14.01 (#35), 25.81 (#11).

Why 19.7 and not ~40–50: the 40–50 numbers are raw host-side reads with no CUDA in the boundary (Section 4); appending a device copy caps delivery at the H2D regime regardless of how fast bytes reach host.

Why 19.7 and not E28's 25.8: same boundary, same nominal UNET config (T8/256MiB/bbuf512), different session/day/region (E27 explicitly observed us-east1 vs us-east4 variance), different CPU contention, clock states. Both are warm-band samples; the 30% spread is not attributable to any identified config delta. UNKNOWN at finer grain.

Cold/warm delta quantified at the identical boundary and config: C9 true-cold 2,172.92 ms / 5.67 GB/s (#29) vs R44E warm 624.68 ms / 19.706 GB/s (#5) = 3.48x throughput, 1,548 ms saved on the copy boundary by cache warmth alone.

---

## 4. Reconciling the 40–50 GB/s numbers (honest, per-number)

Interrogation of each claim:

| Question | E27 UNET QD4 43.45 / QD8 49.61 | E27 CLIP QD4 42.03 / QD8 45.00 |
|---|---|---|
| True cold / first-touch? | Only QD1-cell-0 was provably first-touch. QD4/QD8 ran AFTER full-file reads in the same container/session; no cache eviction is documented between cells. | Same. |
| Page-cache served? | Unproven either way; strongly indicated (see below). | Same. |
| Raw read rather than GPU delivery? | YES — pure host preadv, destination host buffers, zero CUDA. | YES. |
| Later in a sequential battery? | YES — battery positions 3 and 4. | YES. |
| Includes CUDA copy? | NO. | NO. |
| Different reader? | YES — custom QD preadv probe with static contiguous per-worker segments, back-to-back reads, no interleaved device work. | YES. |
| Queue depth? | 4 / 8 concurrent streams. | 4 / 8. |
| Preallocated pinned buffers? | Host buffers; pinned only in the separate H2D-control probes. | Same. |
| Overlapped operations? | Read-only; nothing to overlap. | Same. |
| Logical vs physical completion? | Wall to last worker join; measures bytes landed in host buffers. | Same. |

The cache-state problem, stated precisely:

- The E27 report's own controls are: `minflt_delta=0` on every cell, and warm-QD1 (11.38) vs cold-QD1 (6.60). It concludes "QD scaling is a concurrency effect, not cache warmth" (E27 report:277-287,383-387).
- `minflt_delta=0` does NOT measure file page-cache residency. Minor faults count process user-space faults; `pread` from a cached kernel page performs no user-space fault. The inference "reads are cold-storage-bound, not page-in" is methodologically unsound.
- The warm control exists ONLY at QD1. "Warmth independence at QD4/QD8" was never tested — there is no warm-QD4 or warm-QD8 control anywhere in the evidence.
- Physics cross-check: 49.61 GB/s sustained from a networked Modal Volume is ~397 Gbps — not a credible storage delivery rate. The same arithmetic as 8-way page-cache memcpy (~6 GB/s per stream) is entirely credible on a 12-core host. The QD16 CPU-bound collapse (22.86 GB/s at 1,690 ms CPU) is exactly what cache-served memcpy saturation looks like.
- Counter-evidence acknowledged honestly: cold-QD1 6.60 << warm-QD8 49.61 shows concurrency matters; and steady-state columns (12.4 GB/s at QD4) suggest mixed provenance. The honest classification is: QD4/QD8 cells are battery-position measurements whose cache state is UNPROVEN; the cold-storage interpretation requires 40+ GB/s from network storage, which lacks any independent physical corroboration in the entire corpus; the cache-served interpretation requires nothing unusual.

Do the numbers prove a real capability FastSafe fails to use? PARTLY YES, and this matters:

- They prove the HOST-SIDE machinery (multi-stream preadv into buffers) can sustain 40–50 GB/s when provenance permits. That is a real, demonstrated host capability.
- FastSafe NOGDS structurally cannot exploit it: per-slot serial pread->cudaMemcpy with null-stream copy serialization (Section 5). E27 itself concluded this and recommended a QD4-8/32MiB preadv->pinned->async-H2D pipeline or fastsafe reconfiguration (E27 report:289-327).
- They do NOT prove 40–50 GB/s of cold storage delivery, and therefore do not constitute an available file->CUDA target.

E28 477 ms / 25.8 GB/s (#11): same FastSafe boundary as R44E UNET, warm-class (progression 2,014 -> 477 ms within one tuning session; later cells inherit warmth). Confirms the warm band; not comparable to CLIP cold.

E27 sequential cells CLIP ~490 / UNET ~700 ms (#12): explicitly sequential battery; only cell 0 was true first-touch; later cells warm. Classified H. Not independent cold samples — the user's framing is confirmed by the artifact structure (E27 report:277-287,383-387).

---

## 5. Pipeline mechanics: FastSafe NOGDS vs raw QD probe (verified code, not intuition)

Raw QD probe (E27 probe; per-worker static segments):

```
storage/Volume --[N concurrent workers, back-to-back preadv, 32 MiB]--> host buffers --> join
Queue depth:        N (4..8) sustained reads in flight, no device work interleaved
Buffer:             host (pageable) per-worker bytearrays
Sync:               one join at end of each worker segment
Serialization:      none between reads
Measured boundary:  bytes landed in host RAM
```

FastSafe NOGDS 0.3.3 (production; T8/B256MiB/bbuf512):

```
                    +-- slot0: pread 64M(pinned) -> cudaMemcpy 64M(sync,null stream) -> pread ... (x4 per 256M request)
storage/page cache -+-- slot1: same ...                                                        ...
 (cold: network)    +-- ...
                    +-- slot7: same
Queue depth:        <=8 requests in flight; EFFECTIVE storage depth < 8 (each slot idles storage during its memcpy)
Buffers:            ONE 512 MiB cudaHostAlloc pool; 64 MiB pinned slice per slot (pool/max_threads)
Copy:               synchronous cudaMemcpy, implicit NULL stream -> cross-slot H2D SERIALIZES in driver
Sync:               slot-reuse JOIN + final wait_io join; cudaDeviceSynchronize for chunks <=64 KiB
Overlap:            across slots only; NONE within a slot (no double buffering)
Measured boundary:  bytes landed in CUDA device memory (gbuf)
```

Where the gap comes from, mechanically:

1. Boundary: probe stops at host RAM; FastSafe continues to device memory through a serialized copy stage.
2. Concurrency quality: probe keeps N storage streams saturated continuously; FastSafe alternates each slot between storage and copy, halving effective storage pressure and exposing per-request latency.
3. Copy stage: null-stream synchronous memcpys serialize; warm ceiling ~= single-copy pinned bandwidth (observed band 13.3–25.8 GB/s).
4. Cache: probe cells >=2 and FastSafe-after-prep both benefit from page cache; cold FastSafe gets no such help.

This triangle (boundary, concurrency quality, copy serialization) fully accounts for the ordering: raw-QD-battery (40–50, host, warm-ish) > FastSafe warm (16–26, includes serialized H2D) > FastSafe/integrated cold (1.8–6.7, network-latency-exposed).

---

## 6. Physical limits (environment-grounded only)

- GPU: NVIDIA RTX PRO 6000 Blackwell (E27 report:252 fresh-container env echo; R44E report environment section). torch 2.13.0+cu130, GCP.
- PCIe generation/link width: NOT RECORDED in any examined artifact (searched R44*, E2x, R4x, logs, JSON). VERDICT: UNKNOWN. Generic Gen5 x16 theoretical numbers are NOT used as evidence anywhere in this report.
- Pinned-memory bandwidth: no standalone benchmark found. Derived empirical band from same-environment H2D-class measurements: 11.49–12.06 GB/s combined pipelines (#24,#25), 14.01 cache-served golden commit (#35), 13.32–25.81 FastSafe warm band (#11,#26,#27,#28,#30). Working ceiling estimate for this environment: ~20–26 GB/s sustained file->CUDA warm; treat as measured band, not a link spec.
- Host RAM: 48 GiB vehicle memory shape (repo taste.md environment fact; deployed spec 16 CPU / 49152 MiB). Fits CLIP 8.04 GB and UNET 12.31 GB simultaneously; page-cache retention of the prepped UNET file is unremarkable.
- Historical same-GPU-model values: all rows above are from this same GPU family/environment lineage (RTX PRO 6000 Blackwell on GCP since E19/E27).
- R41 already flags suspicion that some historical device timings exceed plausible PCIe bounds and require physical verification (R41 report:195-208) — consistent with this report's refusal to treat 40–50 GB/s as a delivery capability.

---

## 7. Cache-state asymmetry: CLIP cold vs UNET warm — PROVEN structurally

- CLIP: first model payload of the cold request. Descriptor pass touched only header bytes (27.547 ms; descriptor_cache_hits=0). No mechanism warmed the 8.04 GB payload beforehand. Classification: TRUE FIRST-TOUCH at payload granularity (backend cache state beyond page cache unknowable from artifacts — the honest ceiling per repo taste norms).
- UNET: full 12,309,866,400-byte read completed and joined before demand (RAW_LOG:161-173), 97.15% overlapped under CLIP forward (overlap 4,689.870 ms; tail at demand 137.665 ms; RAW_LOG:197-206). Classification: PAGE-CACHE-WARMED file->CUDA (residency itself inferred, not directly observed; see Section 3 step 2-3).
- Quantified asymmetry at identical boundary/config: 4.159 vs 19.706 GB/s = 4.74x; vs the cold twin C9 5.67 GB/s = 3.48x.
- Therefore R44E effectively measured: CLIP = cold source->CUDA; UNET = warmed page-cache->CUDA. YES.

Could a CLIP source-prep equivalent hide elsewhere WITHOUT moving contention onto the CLIP critical path? Analysis only (not implemented):

- Prep rate observed: 12.31 GB / 4.827 s = 2.55 GB/s (#7). An 8.04 GB CLIP prep at that rate ~= 3.16 s.
- Available in-container idle before CLIP demand: application_restore ~906 ms, VAE load ~324 ms, descriptor ~28 ms — total < 1.3 s. INSUFFICIENT.
- modal_scheduling (34.2 s) precedes container start; local_preparation (15.1 s) is client-side. Neither can touch container page cache.
- Conclusion: a CLIP prep equivalent has NO free hiding window in the current schedule; it would add ~3.2 s serial wall unless prep throughput itself improves (e.g., QD-style parallel prep at 6+ GB/s ~= 1.3 s, still exceeding current idle) or the copy is made cold-tolerant instead. The cheaper direction is improving the cold path, not replicating the prep trick for CLIP.

---

## 8. Is 40 GB/s a realistic target — per boundary

| Boundary | Realistic target (this environment) | Basis |
|---|---|---|
| Source-read capability (TRUE cold) | ~6.6–7.7 GB/s demonstrated single-stream; multi-stream true-cold UNKNOWN (never cleanly measured — battery contamination). 40+ GB/s cold: NOT DEMONSTRATED and physically implausible for networked Volume. | #13,#19,#23,#31,#33 |
| Page-cache read (host) | 40–50 GB/s achievable host-side (proven by battery cells under the cache interpretation); CPU-bound ~20 GB/s at QD16/128MiB. | #15–#18,#21,#22 |
| Host->CUDA (pinned) | ~20–26 GB/s sustained demonstrated (FastSafe warm band); link spec UNKNOWN. | #11,#26,#27,#30,#35 |
| Full FastSafe file->CUDA | Cold: ~4–6.7 GB/s today (C9, R44E). Warm: ~16–26 GB/s. 40 GB/s at this exact boundary: NEVER demonstrated by any artifact in the corpus. | #1,#5,#11,#26–#30 |
| Integrated model-ready | CLIP node 4,825.5 ms (dominated by copy 1,934.7 + bind 2,670.5 second materialization); UNET node 819.5 ms. Transport is no longer the largest CLIP term — bind is. | #3,#4,#6; RAW_LOG:120-150,218-219 |

If historical evidence had demonstrated 40 GB/s at the SAME boundary, this report would say so. It does not: no artifact measures 40+ GB/s past the host-RAM boundary, and the two same-boundary cold anchors (C9 5.67; R44E CLIP 4.16) agree with each other, not with 40.

---

## 9. Next most informative experiment (AFTER R44F; designed, NOT run)

Single decision: is the CLIP cold deficit caused by source coldness (cache-state hypothesis) or by the FastSafe transport itself?

Minimum experiment — CLIP_CACHE_STATE_AB (one deploy, three fresh-container cold requests, alternating arms, first-payload discipline: stat/open/header only before measurement):

- Arm A (control): exact R44E CLIP config (T8/B256MiB/bbuf512/nogds/disable_cache/use_buf_register=False), no prep. Expect ~1,900 ms reproduction.
- Arm B: identical, except a CLIP source-prep (checkpoint_prewarm mechanism retargeted to qwen_3_4b.safetensors, 4T/8MiB) completes and joins BEFORE the FastSafe copy; report prep wall and copy wall separately; accept that prep adds serial wall OUTSIDE the copy boundary.
- Arm C (optional third arm only if budget allows): T16, no prep — tests the storage-concurrency lever (E27 precedent: 16T screens roughly tripled 8T on cold-ish loads).

Decision rule:
- B copy ~= 600–900 ms (>= ~10 GB/s): cache-state causation PROVEN at the exact boundary; cold-path work should target warming/pipelining, not FastSafe knobs.
- B copy ~= 1,300–1,900 ms: cold-delivery/transport hypothesis survives; next probe becomes per-phase counters inside copy_files_to_device (read-bytes-time vs copy-time), not another A/B.
- C materially better than A: thread-count lever confirmed for cold; fold into any future config change.

Why this and not a matrix: it isolates the single variable with the largest explanatory power (4.74x observed asymmetry), reuses existing mechanisms (checkpoint_prewarm, r44 profile), costs one deploy, and each outcome redirects the following step decisively.

---

## 10. What evidence would falsify this report's conclusions

- Per-phase counters inside `copy_files_to_device` on a cold CLIP showing pread bytes-complete time << total copy wall (reads fast, copies slow): falsifies H1 primacy; promotes H3/null-stream and motivates async double-buffering.
- A warm-QD4/QD8 control measuring ~12 GB/s (not ~43–50): falsifies the cache-served interpretation of the 40–50 cluster and revives the raw-storage-capability interpretation; would demand re-derivation of Section 4.
- nvidia-smi / NVML telemetry showing PCIe Gen5 x16 with a measured pinned H2D microbenchmark > 40 GB/s in this container: invalidates the ~20–26 GB/s working ceiling; Sections 3, 5, 8 would need revision.
- C9 re-run on current build measuring UNET true-cold ~= 19 GB/s (not ~5.7): falsifies the cold/warm band model outright.
- Demonstration that prep'd pages were evicted before UNET demand (e.g., /proc/meminfo or minflt-based evidence of re-reads from storage) while copy stayed 624 ms: falsifies the page-cache mechanism despite circumstantial fit; would require a replacement explanation (e.g., volume read cache on the storage backend).
- Finding that `disable_cache` or `use_buf_register` alter NOGDS read behavior in 0.3.3 (contradicting upstream source cited here): falsifies the FALSIFIED verdicts H4/H5.

---

## 11. Configuration assessment: T8/B256MiB/bbuf512 — inherited, not derived

- Provenance: carried from the E28-era tuning (E28 report:54-59) into r44-request-fastsafe.toml:43-45. No R44-era derivation evidence exists.
- bbuf512/T8 => 64 MiB pinned per slot: sound for the warm regime; not starved (contra the natural misreading that 512 KiB-scale buffers are in play).
- B256MiB: near-neutral (caps request size only; internal chunking is per-slot).
- T8: adequate for warm (null-stream serialization makes extra threads inert); PLAUSIBLY undersized for cold (E27 16T screens beat 8T substantially; never tested true-cold at this boundary).
- Overall: MERELY INHERITED. Defensible for warm UNET; unproven and plausibly suboptimal for cold CLIP. The dominant lever remains cache state and transport structure, not these knobs — but Arm C above is the cheap test of the one knob with historical signal.

---

## 12. Flags

```
R44G2_40GBPS_NUMBERS_RECONCILED = YES
R44G2_CLIP_4GBPS_ROOT_CAUSE_PROVEN = NO          (STRONGLY SUPPORTED: cold-source-dominated with serialization structure; not PROVEN — no per-phase decomposition inside copy_files_to_device)
R44G2_UNET_20GBPS_ROOT_CAUSE_PROVEN = YES        (page-cache-warmed delivery capped by serialized null-stream H2D; structural chain fully evidenced)
R44G2_COLD_VS_WARM_BOUNDARIES_CLASSIFIED = YES
R44G2_FASTSAFE_VS_QD_MECHANICS_TRACED = YES
R44G2_NEXT_MINIMAL_EXPERIMENT_DEFINED = YES      (CLIP_CACHE_STATE_AB, arms A/B[/C])
R44G2_RUNTIME_CODE_CHANGED = NO
R44G2_REMOTE_RUN_PERFORMED = NO
```
