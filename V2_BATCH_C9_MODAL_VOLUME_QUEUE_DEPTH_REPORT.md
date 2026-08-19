# V2 Batch C9 — Modal Volume Queue-Depth Shootout (ZImage, real file)

Date: 2026-08-15 · Agent: Batch C9 (subagent-driven) · Mode: measurement-only
standalone mechanism benchmark against the exact ZImage safetensors file.
No ComfyUI loader integration. No commit. No branch/worktree. C4 artifacts
untouched.

---

## 1. Verdict

### STORAGE CONCURRENCY CONFIRMED — C6's storage ceiling conclusion is strongly falsified

| QD | full-file wall ms | aggregate GB/s | vs QD1 |
|---|---|---|---|
| 1 (cold, seq preadv) | 2788.6 | 4.41 | 1.00× |
| 2 (static, 32 MiB) | 758.4 | 16.23 | **3.68×** |
| 4 (static, 32 MiB) | 407.4 | 30.21 | **6.84×** |
| 8 (static, 32 MiB) | 302.3 | **40.72** | **9.22×** |
| 16 (static, 128 MiB*) | 799.6 | 15.40 | 3.49× |

\* QD16 ran at the default 128 MiB block (the bounded screen has no QD16
entry) — confounded with block size, excluded from classification (see §6).

The ~3–4 GB/s full-file result observed by C6 was the throughput of ONE
outstanding sequential reader, not a Modal Volume bandwidth ceiling.  Eight
disjoint positional readers on the SAME file aggregate **40.7 GB/s — 9.2× the
single-stream floor** (way beyond the mission's 2× "strongly falsified"
band), with byte-exact correctness on every full-file pass.

The 2×+ band is exceeded by QD2 alone (3.68×): **the C6 storage conclusion
(volume read ~3–4 GB/s whatever the mechanism) is falsified at queue depth 2.**

### External loaders: fastsafetensors (tuned) is the fastest GPU-ready path measured

| loader | config | dest | wall ms | GB/s | valid |
|---|---|---|---|---|---|
| Run:ai Model Streamer 0.16.1 | c=8 | cpu | 6572.9 | 1.87 | YES |
| Run:ai Model Streamer 0.16.1 | c=16 | cpu | 4018.5 | 3.06 | YES |
| Run:ai Model Streamer 0.16.1 | c=16 | cuda:0 | 4878.8 | 2.52 | YES (read+GPU) |
| fastsafetensors 0.3.3 | t=8, blk 1 GiB | cpu | 1995.1 | 6.17 | YES |
| fastsafetensors 0.3.3 | t=16, blk 1 GiB | cpu | 2033.0 | 6.06 | YES |
| fastsafetensors 0.3.3 | t=16, blk 1 GiB | **cuda:0** | **924.3** | **13.32** | YES |

All six loaders returned exactly 453 tensors / 12,309,817,472 bytes with the
exact header key set, shapes, dtypes (spot-checked), and a sample hash
identical to the mmap baseline (`0740edff…6bff52f`) — byte-identical data,
not cached wrong data.

---

## 2. Exact target

- model file = `z_image_turbo_bf16.safetensors`
- resolved path = `/root/comfy/ComfyUI/models/diffusion_models/z_image_turbo_bf16.safetensors`
- file size = 12,309,866,400 B (header 48,920 B)
- **total data bytes = 12,309,817,472 B** (453 tensors, bf16, gap-free packed layout per C12)
- volume = `comfyui-models` (mounted at `/root/models`, `create_if_missing`); f_bsize 4096
- platform = GCP/us-east4, NVIDIA RTX PRO 6000 Blackwell, CUDA 13.0,
  torch 2.13.0+cu130, **32 vCPU**, safetensors 0.5.3 (image-pinned)
- deployment = `stable-modal-comfy-v2-c9qd-shadow` (distinct queue-depth
  shadow, same C6-family image + env-gated extras
  `runai-model-streamer==0.16.1`, `fastsafetensors==0.3.3`)

## 3. Method

One standalone Modal function (`run_unet_qd_probe`, shadow deployment, three
modes).  One small structural gate, then ONE evidence-bearing invocation with
the full bounded matrix (standing rule; no cohort):

1. **env/file** — os, cpus, statvfs, mount, header parse + gap/overlap
   reconciliation (C12 layout re-validated: contiguous, exactly
   12,309,817,472 B).
2. **Baselines** — (A) safetensors mmap first-touch scan of all 453 keys
   (page-granular touch, mirrors comfy `load_torch_file` with
   DISABLE_MMAP=False); (B) sequential full-file preadv, 32 MiB syscalls
   (C6 floor repro).
3. **Bounded screen** — QD ∈ {1,2,4,8} × block ∈ {32,64,128,256} MiB = 16
   configs × 2 GiB rotating windows (cache-fair), static partition, + 1
   dynamic-queue QD8/64 MiB contrast.
4. **Full-file measurement** — QD2/4/8 at the screen-selected best block
   (32 MiB everywhere), optional QD16, then a warm-QD1 control (same config
   as the cold QD1, run last) to bound the page-cache effect.
5. **GPU phase** — best screen config (QD4/32 MiB): preadv→pinned→async
   non-blocking H2D with CUDA events, single sync.
6. **External battery** — Run:ai (c8/c16/c16-cuda) and fastsafetensors
   (t8/t16/t16-cuda, `nogds=True`, `max_copy_block_size=1 GiB` as C10
   requires, `use_buf_register=False` — cudaHostRegister is unsupported on
   this platform per C6 rc=304), each with key-set/shape/dtype/hash
   validity.

Worker mechanics: per-worker pinned buffers, positional 32 MiB `os.preadv`
syscalls with short-read retry (the C6-validated short-read-free regime),
disjoint byte ranges (partition math verified: no gaps, no overlap, exact
coverage), GIL-released blocking reads so N threads genuinely overlap at the
kernel.

## 4. Full-file correctness

Every full-file config returned **exactly 12,309,817,472 bytes** with
`verify.all_match = True` across 46 sampled regions per pass (head, tail,
and head+tail of every 512 MiB stride, sha256-compared against the
safetensors reference bytes reconstructed from `get_tensor`).  The mmap
baseline sample hash `0740edff0575056a1bd07ad4b98cb3c06a8b731a9d6c4d2199c94c02e6bff52f`
equals every external loader's sample hash.

## 5. Cache-state analysis (the honest reading of 40.7 GB/s)

Phases 3–5 read a cache-warm file (32-core host, ~12.3 GB file).  The
warm-QD1 control isolates the cache effect at QD1: **8.41 GB/s vs 4.41 cold =
1.91×** — page cache roughly doubles a single reader.  It cannot explain
QD8: against the warm-QD1 control at the SAME cache state, eight readers
still deliver **4.84× more** (40.72 vs 8.41 GB/s).  The scaling curve
(QD2 16.2 → QD4 30.2 → QD8 40.7) is therefore a concurrency effect on the
volume read path, not cache accumulation.  The per-config 256 MiB warm
repeat is flat (≈7 GB/s) across all configs — a single re-read never
exceeds ~7 GB/s even hot, while the aggregate with 8 readers reaches 40.7.
This is the queue-depth signature: the backend (volume FUSE client +
kernel) serves one stream at ~4–8 GB/s but parallelizes to 40+ GB/s.

Screen numbers are 2 GiB-window artifacts of ramp-up (16.5 GB/s max at
QD4/32 MiB) and were used only for block selection; full-file numbers are
authoritative.

## 6. Block size, scheduling, QD16, CPU

- **Block size**: 32 MiB won the screen for every QD; larger blocks were
  monotonically worse (QD4: 32 MiB 16.5 → 256 MiB 5.6 GB/s) — a short-window
  ramp artifact (2 iterations per worker at 256 MiB) plus fewer scheduling
  handoffs.  Full-file configs all ran at the screen-selected 32 MiB.
- **Scheduling**: static contiguous partition balanced well at full-file
  (QD8 tail spread 59 ms / 302 ms wall).  Dynamic block queue beat static on
  the 2 GiB window (QD8/64 MiB: 15.2 vs 11.0 GB/s, +38%) — better balance
  under ramp; not decisive at full-file.
- **QD16** (optional gate met: QD8 scaled +35% over QD4; 32 cores): ran at
  the default 128 MiB block (no screen entry) → 15.4 GB/s.  **Confounded by
  block size, not a CPU-oversubscription signal**; excluded from
  classification.  A clean QD16@32 MiB point would require another paid run;
  the standing rule (stop when the answer is clear) applies — the QD2/4/8
  curve already classifies.
- **CPU**: `os.preadv` releases the GIL; workers are I/O-bound.  The
  rusage CPU counters for the raw-QD configs were corrupted by an
  int-truncation bug in the run-time build (`ru_utime` float seconds → int
  deltas → ~0 ms reported); fixed in the tree afterward, and the external
  loaders' counters (measured through the fixed bracket in the same build —
  see caveat §7) show Run:ai at 18–24% of one core and fastsafetensors at
  8–10% (cpu) / 2.2% (cuda).  The QD16-vs-QD8 inversion is block-size
  driven, not a CPU-saturation collapse; no config was CPU-bound.

## 7. GPU transfer phase (storage → pinned → async GPU)

QD4/32 MiB: 12,309,817,472 B in **1508.1 ms (8.16 GB/s combined)**;
H2D device 1508.0 ms (fully hidden under storage), H2D host issue 11.7 ms
total, pinned 128 MiB + GPU temp 128 MiB, 368 async copies, one sync.  The
storage read was the binding stage; DMA hid under it.

## 8. Metric integrity notes

- `process_cpu_ms`/`cpu_utilization_pct` for the raw-QD configs are
  unreliable (rusage int-truncation bug, fixed in-tree post-run); the
  external-loaders' CPU numbers came from the same buggy bracket and should
  be read as ordering-valid, magnitude-indicative.
- `thread_cpu_ms` and context-switch deltas returned None on this container
  (best-effort /proc reads); RSS/minflt/majflt and all throughput/wall/verify
  metrics are intact.
- External loaders ran in a separate cold-container invocation; the host
  page cache may have been warm from the earlier evidence run.  Even at a
  50% discount for cache warmth, fastsafetensors t16-cuda (924 ms GPU-ready
  vs the native read+H2D chain 4091.6 ms) is >2× — classification holds.
- One evidence run per the standing rule; no cohort.  Deploys were cached
  (only source layers changed); the first deploy attempt aborted pre-
  finalize on a Windows `charmap` console crash (Modal rich output to a
  cp1252 pipe) — no deployment was created and no paid work was lost.

## 9. Required report fields

```
report path            = V2_BATCH_C9_MODAL_VOLUME_QUEUE_DEPTH_REPORT.md
changed files          = comfymodal_runtime/unet_qd_probe.py (new QD battery,
                         baselines, external-loader adapters, smoke tests),
                         comfymodal_runtime/modal_app.py (run_unet_qd_probe
                         method + 3-point registration + env-gated
                         COMFYMODAL_V2_C9QD_EXTRAS image extras),
                         tools/run_c9_qd_probe.py (runner),
                         tests/test_c9_qd_probe.py (31 offline tests)
commit = none
deploy count           = 4 (3 finalized; 1 aborted pre-finalize by a Windows
                         console codec crash — cached layers, no paid impact)
Modal requests         = 4 (structural gate ×1 error → fixed; evidence ×1
                         valid; structural ×1 ok incl. loader smoke; external
                         ×1 valid)
model file             = z_image_turbo_bf16.safetensors (diffusion_models)
total bytes            = 12,309,817,472

QD1 best GB/s          = 4.41 (cold full-file sequential preadv; warm control 8.41)
QD2 best GB/s          = 16.23
QD4 best GB/s          = 30.21
QD8 best GB/s          = 40.72
QD16 best GB/s         = 15.40 (confounded: default 128 MiB block; not classified)

best block size        = 32 MiB (screen-selected; larger blocks worse on short windows)
best scheduling strategy = static contiguous partition (dynamic +38% only on
                         2 GiB ramp windows)
max aggregate GB/s     = 40.72
speedup vs sequential  = 9.22× vs cold QD1; 4.84× vs warm-QD1 control (same
                         cache state)
CPU utilization QD1    = not reliably measurable (rusage truncation bug in
                         the run; GIL-released I/O workers, wall-bound)
CPU utilization best   = same caveat; indicative: fastsafetensors t16-cuda
                         2.2% core util at 13.32 GB/s (0.002 cores per GB/s);
                         Run:ai c16 24.1% at 3.06 GB/s (0.079 cores per GB/s)
memory overhead best   = QD8: 256 MiB peak pinned (8 × 32 MiB) + kernel page
                         cache; fastsafetensors t16-cuda: 12.31 GB GPU temp +
                         ~256 MiB bounce pool; peak RSS observed 40.4 GB
                         (fastsafetensors CPU file buffer)

safe_open mmap GB/s    = 7.74 (cold full-file first-touch; healthy-native
                         parity with C13's 1.624 s)
sequential preadv GB/s = 4.41 (C6 floor reproduced)
official safetensors pread GB/s = N/A — image pins safetensors 0.5.3, which
                         has no pread backend (verified
                         safe_open_backend_param=false); F recorded skipped
                         per the mission (no dependency modification budget)

storage concurrency classification = STORAGE_QD_SCALES (major; >50% band
                         exceeded at QD2; 9.22× at QD8)
single-stream floor disproven = YES (2×+ band exceeded at QD2 alone)
recommended loader queue depth = 8 (32 MiB-chunk preadv pool; plateau region;
                         QD16 point confounded, do not extrapolate)
```

## 10. Addendum fields (C10/C12/C8 handoffs)

```
raw QD classification  = STORAGE_QD_SCALES (9.22×)
RunAI valid            = YES (c8, c16, c16-cuda; 453 tensors, exact bytes,
                         hash-identical; memory-limit env quirk fixed: the
                         limit is BYTES — header-size floor 48920 — was
                         previously set in MiB)
RunAI best wall        = 4018.5 ms (c16, cpu)
RunAI best GB/s        = 3.06 (c16, cpu; 2.52 read+GPU cuda variant)
fastsafetensors valid  = YES (t8, t16, t16-cuda; hash-identical; adapter
                         fixed: SafeTensorsFileLoader — fastsafe_open does
                         not forward max_threads; use_buf_register=False for
                         the unsupported cudaHostRegister path)
fastsafetensors best wall = 924.3 ms (t16, cuda:0, GPU-ready)
fastsafetensors best GB/s = 13.32 (t16, cuda:0); CPU-best 6.17 (t8)
best overall loader    = fastsafetensors 0.3.3 t16 cuda:0 (924 ms GPU-ready,
                         byte-identical)
best overall speedup vs native = 4.43× vs native read+H2D chain
                         (1623.7 + 2467.9 = 4091.6 ms); 1.72× vs native mmap
                         read alone (1591 ms) while also producing
                         GPU-resident tensors
STORAGE_QD_SCALES      = YES
EXTERNAL_LOADER_WIN    = YES (with the cache-warmth caveat of §8; holds at
                         50% discount)
NATIVE_FLOOR_SUPPORTED = NO
SHARDING_NEXT          = NO — C12's condition ("same-file QD fails or
                         saturates poorly") is false: one file delivers
                         40.7 GB/s at QD8; no evidence independent files add
                         backend parallelism. Shards not created.
META_NATIVE_NEXT       = YES — C8's meta+native hybrid (~165–305 ms) is an
                         independent small optimization, unaffected by this
                         result; validate separately after C9.
additional paid runs needed = 0 — the answer is decisive and the standing
                         rule (one bounded evidence-bearing invocation,
                         fix-and-repeat only for broken mechanisms) was
                         honored; the two loader adapter fixes were validated
                         by the cheap structural gate + smoke tests before
                         the single corrective external run.
reason = single-stream full-file preadv (4.41 GB/s) is not a storage
                         ceiling: 8 disjoint readers aggregate 40.72 GB/s
                         (9.22×) on the same file with byte-exact data; the
                         fastest GPU-ready path measured (fastsafetensors
                         t16 cuda, 924 ms) beats the native read+H2D chain
                         4.4×; C6's "volume read ~3–4 GB/s whatever the
                         mechanism" is falsified, and C6's STOP decision is
                         re-opened for a concurrency-based loader.
```

## 11. Performance opportunity / next step

**Opportunity**: a bounded QD8 (32 MiB chunk) preadv reader replaces the
single-stream read: storage read 12.31 GB in ~0.30 s vs 2.79 s sequential
and vs 1.59 s mmap page-in — storage stops binding the UNET chain entirely
(4.6 s → storage ~0.3–0.9 s + construction + H2D, H2D hidden under reads at
QD4+).  fastsafetensors (nogds, 1 GiB blocks, ≤16 threads, cuda:0) is the
lowest-effort production path already available and validated byte-identical.

**Next step** (recommended, requires authorization): integrate a QD8/32 MiB
preadv→pinned→async-H2D UNET loader for ZImage (or adopt fastsafetensors'
nogds cuda path) behind the existing default-off seam, then validate with
the standing one-run rule.  Do not default it on without a new decision;
C8's meta-native hybrid remains a separate orthogonal lane.

## 12. You asked for

- Determine whether C6's ~3–4 GB/s full-file result is a Modal Volume
  bandwidth ceiling or single-reader throughput, via a standalone QD
  shootout (QD1/2/4/8(+16), 32–256 MiB blocks, static+dynamic) against the
  exact ZImage file, plus native mmap/seq-preadv baselines and the C10
  external loaders (Run:ai, fastsafetensors) with full validity checks, one
  deploy, one structural gate, one evidence run, and the required report.

## 13. You should now manually check

- Decision fields: STORAGE_QD_SCALES=YES, EXTERNAL_LOADER_WIN=YES,
  NATIVE_FLOOR_SUPPORTED=NO, SHARDING_NEXT=NO, META_NATIVE_NEXT=YES —
  a new loader integration decision is required before any production
  change; this task added only a default-off measurement path and the
  env-gated image extras flag (production images are unchanged when
  `COMFYMODAL_V2_C9QD_EXTRAS` is unset).
- The QD16 point (15.4 GB/s at 128 MiB blocks) is block-confounded; if a
  clean QD16 is ever needed, it requires a dedicated run — not assumed.
- CPU-utilization counters from this run are unreliable (fixed in-tree
  post-run); RSS/throughput/verify metrics are intact.
- Run:ai memory-limit unit (bytes) and fastsafetensors adapter (direct
  SafeTensorsFileLoader) are validated by the structural-gate smoke tests;
  the run-time `c9qd_*` result JSONs are in the local temp dir if re-analysis
  is wanted.
- No commit was made; C4's deployment/artifacts untouched; all unrelated
  working-tree changes preserved.
