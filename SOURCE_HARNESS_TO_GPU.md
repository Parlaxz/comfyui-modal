# Source harness → GPU — final report

Working source harness: the frozen **M2 window** mmap engine
(`run_mmap_source_probe`, `mmap_mode="window"`), commit `b9196ac`. GPU/H2D work
is additive and lives in `comfymodal_runtime/source_race_gpu.py` plus an
`on_ready` seam in `source_race_oracle.py`; the CPU path is unchanged when
staging is disabled (`mode="private"`).

All runs: Testing5 (`ws_c1487d319820`), app `sept-clip-source-race-oracle`,
`h100!`, no provider/region pinning. Every run reports source wall, function
(execution) wall and the Modal call id.

## Baseline (M2, 10 fresh H100 runs)

- tag `working-source-harness-m2`, record `WORKING_SOURCE_HARNESS_M2.md`.
- source GB/s: median **6.720**, mean 6.649, p10 5.137, p90 7.671, min 4.823, max 8.555.
- source wall median 1215 ms; function wall median 1582 ms; end-to-end ≈ 5.08 GB/s.
- coverage exact 120/120 on all; max in-flight 4.

## Destination change (Phase 1, M2)

`mode="shared"`: readers memcpy into a POSIX shared-memory staging region
(`mp.RawArray`, `/dev/shm`, fork-inherited), `slots=2` per lane, publish-after-copy,
one parent release consumer.

- 6 private vs 6 shared interleaved: shared **0 staging waits**, 720/720 blocks
  published, coverage exact, max in-flight 4.
- source GB/s: private median 4.571, shared median 5.921 (placement-dominated);
  matched region gcp:ca private 3.469 vs shared 5.50.
- conclusion: **shareable destination adds no source-side slowdown.**

## Registration change (Phase 2, M2)

`mode="registered"`: staging pinned with `cuMemHostRegister` in a new
`on_ready` hook that runs **after the reader fork, before readers are released**.

- First attempt (registration inside the source window) stalled each reader once
  (~400–700 ms), ~22% throughput loss → rejected.
- Pre-source hook: 6 shared vs 6 registered interleaved — registered **0 staging
  waits**, 720/720 published, coverage exact; `cuMemHostRegister` 73–188 ms,
  device H100 80GB HBM3. Registered median 5.884 vs shared 5.346 (placement);
  matched regions equal. **PASS.**

## H2D change (Phase 3, M2)

`mode="h2d"`: one 8 GB GPU destination (`cuMemAlloc`), one non-blocking stream,
`cuMemcpyHtoDAsync` per produced block, a fresh start+completion event per
transfer, slot released only after its completion event.

Correctness run (`phase3_verify/v-01.json`): 120 transfers, 8,044,982,048 bytes
= exact file size, coverage offsets 120 exact (no dup/miss/reorder),
**GPU SHA256 == file SHA256** (`6c6714…`), 0 staging waits, `cuMemHostRegister`
78 ms, GPU alloc 1.9 ms.

Performance (5 registered vs 5 h2d interleaved, no verify):

| arm | source GB/s median | source wall med | function wall med | waits | H2D active |
|---|---:|---:|---:|---:|---:|
| registered | 5.376 | 1496 ms | 3044 ms | 0 | — |
| h2d | 6.003 | 1340 ms | 2703 ms | 0 | ~150 ms total |

Per-run H2D: total device-active 149–295 ms for 8 GB; max single transfer
1.36–2.5 ms; **exposed H2D tail 1.88–4.55 ms**; GPU-ready wall ≈ source wall +
2–5 ms. H2D runs underneath source production.

## Optimization pass (post-Phase 3)

Applied, with source and H2D unchanged:

- **Lazy shared `mmap` staging instead of `mp.RawArray`.** No eager zero-fill;
  `slots=1` per lane (4 × 64 MiB = 256 MiB). Measured `staging_alloc` dropped
  from **589–1002 ms → 8–10 ms**.
- **`nvidia-smi` removed from the hot path** (`observe_gpu=False`, production
  default). Measured 57–154 ms → **0**.
- **No prefault for CUDA modes** — `cuMemHostRegister` pins/faults the pages, so
  the separate prefault was double-work. Measured `prefault_join` **219–386 ms → 0**.
- **CUDA context init overlapped** with reader fork/prep via an `on_post_fork`
  hook (independent work; readers parked). `cuInit+cuCtxCreate` is the real CUDA
  cost (**208–854 ms**), vs `cuMemHostRegister` **40–65 ms** and `cuMemAlloc` ~2 ms.
  ~100 ms of context init is now hidden under fork/ready.

Good-host h2d after optimization (`opt4-02`): function wall 2141 ms, source wall
1365 ms, overhead 776 ms. Of that, **import (~160 ms) and CUDA context init
(~336 ms) are harness artifacts** — a production adapter on a warm container with
an existing CUDA context does not pay them. Remaining real per-request overhead
≈ fork 94 + register 65 + reader teardown 91 + staging 8 + consumer join 17
≈ **0.28 s**, and register/staging amortize with a persistent arena.

Import slimming is a production refactor (extract the M2 engine + GPU seam into a
small loader module so importing the loader is cheap); it is not treated here as
a speedup by relocating the import.

## Required verdict

- **WORKING SOURCE HARNESS:** M2 window engine, source median 6.72 GB/s (10 runs), tag `working-source-harness-m2`.
- **SHAREABLE DESTINATION EFFECT:** none on source; 0 staging waits, exact coverage.
- **HOST REGISTRATION EFFECT:** none on source once done pre-source (0 waits); registration 73–188 ms.
- **H2D EFFECT ON SOURCE:** none; h2d median 6.003 vs registered 5.376 (placement); 0 waits; H2D hidden.
- **FINAL SOURCE WALL:** ~1.2–1.5 s typical (host-dependent; 16 s on one pathological eu-south host).
- **FINAL GPU-READY WALL:** source wall + 1.9–4.6 ms exposed tail.
- **EXPOSED H2D TAIL:** 1.9–4.6 ms (147–295 ms total device-active for 8 GB).
- **READY TO BUILD PRODUCTION ADAPTER:** YES for the loader seam (source and H2D are clean); NO for an end-to-end claim until fixed per-invocation overhead (import, 512 MiB staging alloc, CUDA setup) is removed or amortized — function wall is ~2.7–3.0 s vs source wall ~1.3–1.5 s.

## Commits / tags

- `3db1033` docs: freeze working source harness (Phase 0, fresh) + tag `working-source-harness`.
- `ca285b1` shared-destination seam (Phase 1, fresh engine).
- `74dbaf0` pre-source on_ready registration (Phase 2, fresh engine).
- M2 seam + instrumentation + docs (this commit) + tag `working-source-harness-m2`.

## Caveats

- Placement dominates absolute GB/s (3.0–8.6 across hosts). All A/Bs are
  same-window interleaved; no region pinning (pinning queued and was abandoned).
- One known M2-seam bug was found and fixed during Phase 1: `build_staging`
  initialised `alive=0`, which exited the release consumer immediately and
  deadlocked readers; now `alive=1`.
- Fresh-engine numbers (Phase 0–2, commits above) remain valid for that engine
  but are superseded by M2 for this program.
