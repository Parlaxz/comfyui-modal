# V2 Batch E27 — Five-Target Critical-Path Forensics

**Mode:** READ-ONLY INVESTIGATION + TELEMETRY (Target E Gantt implemented).
**Authorized remote work:** deploys, cold runs, diagnostic probes, telemetry
improvement cycles.  **No production optimization implemented.**
**Date:** 2026-08-18
**Git HEAD:** `a6a755e8dc923e933d13567ec07ddf5b6988f948` (branch `TESTING2`, no
commit, no branch, no worktree created by this batch)

---

## 1. Executive result

E27 is the evidence base for a later implementation batch.  It answers all
five targets with a mix of NEW fresh-container measurements (Target A loader
QD for both UNET and CLIP), authoritative historical decompositions
(Target B empty_cache via D18; Target D casting path via D7), a
restore-time relationship analysis (Target C), and a working ASCII Gantt
telemetry implementation (Target E) that is deployed and probe-verified.

**Headline measured results (fresh container, GCP, RTX PRO 6000 Blackwell,
this batch):**

| Target | Current production | Measured best | Headroom |
|---|---|---|---|
| UNET source read | 20.8 GB/s (fastsafe 16T/1 GiB block) | **49.6 GB/s** (QD8/32 MiB preadv) | **~2.4×** |
| CLIP source read | 16.2 GB/s (fastsafe 16T/1 GiB block) | **45.0 GB/s** (QD8/64 MiB; 42.0 @ QD4/32 with 30 ms CPU) | **~2.6-2.8×** |
| CLIP native mmap read | 1.09 GB/s | (same file via QD4) 42.0 GB/s | ~38× |
| `empty_cache()` wall | 740-950 ms (D18, E19-era path) | n/a (decomposition exists) | ~740-950 ms removable IF proven-ready |
| Per-forward weight cast tax | 99-195 cast ops / 126-417 MB per forward (D7, generic) | n/a (needs real-Qwen run) | est. 20-35% of encode wall |

**Deployment blocker discovered and documented:** the E19 restore-only
snapshot vehicle did not produce a retained CLIP/VAE CPU snapshot in this
environment (repeated `cpu_snapshot_models_present=0`,
`snapshot_identity=""` across 4 deploys + 8 probes).  This invalidates
generation-path baseline runs (a run on a construction container would be
structurally invalid per the standing validity rule), so the Gantt full-run
evidence and empty_cache/cast on-run measurements are deferred to the
authorized remote cycle.  The QD probe evidence (snapshot-independent) was
obtained in full.  The failure mode and the exact recovery path are
documented in §2/§15 so the implementation batch can produce a valid
baseline without re-deriving this.

**Completion gate status:** see §14.  Loader mapping, QD matrices,
empty_cache call graph, casting path, earliest-CLIP analysis, Gantt
implementation, and cross-target interactions are complete.  The
generation-run-dependent items (Gantt in actual generation logs, on-run
memory boundaries, on-run empty_cache decomposition, on-run cast counters)
are implemented and deployed but NOT yet exercised because the snapshot
vehicle is blocked; this is an environment blocker, not missing telemetry.

---

## 2. Starting repository/deployment state

### 2.1 Git state (recorded at batch start)

```text
git rev-parse HEAD  => a6a755e8dc923e933d13567ec07ddf5b6988f948
git branch --show-current => TESTING2
```

Working tree at start: large pre-existing uncommitted delta from prior
batches (84 modified/untracked files — concurrent work, preserved untouched;
see §19 final status).  This batch added only:

```text
?? comfymodal_runtime/gantt_telemetry.py      (new, Target E)
?? comfymodal_runtime/e27_forensics.py        (new, E27 telemetry)
?? tests/test_e27_gantt_telemetry.py          (new, 9 tests)
?? tests/test_e27_forensics.py                (new, 4 tests)
 M comfymodal_runtime/modal_app.py            (E27 wiring: gantt emit, env passthrough,
                                               run_clip_qd_probe method, cast summary)
 M comfymodal_runtime/model_preload.py        (E27 soft-cache chain + cast counter install)
 M comfymodal_runtime/runtime_executor.py     (E27 sampling_end memory boundary)
 M comfymodal_runtime/clip_fast_hydration_wiring.py (E27 clip_source_read span + memory boundary)
 M comfymodal_runtime/unet_fastsafetensors.py (E27 unet_source_read span)
?? V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md (this report)
?? _e27_unet_qd_evidence.json                 (raw probe artifact)
?? _e27_clip_qd_evidence.json                 (raw probe artifact)
```

### 2.2 V2 deployment/runtime configuration (current, deployed this batch)

App: `stable-modal-comfy-v2-restore-only-shadow` · Class:
`ModalRuntimeEntrypointV2` · GPU: `rtx-pro-6000` (RTX PRO 6000 Blackwell
Server Edition, 97 GB) · runtime shape fingerprint
`7a4753e1082be2c398cbd109` · CPU 16 / RAM 49152 MiB (deploy) with
baseline 12/32768 · atomic profile `E19_FINAL_COLD_LOADER` · provider
unpinned (observed GCP/us-east1 and us-east4) · deployment_combined_hash
`34404d77cef0dd7b2a4cdd056d3f0fab9665956b2b0401883fb663b0368dc146` ·
deployed 2026-08-18T19:50:24Z.

Effective container gates (read back via `run_env_probe`, this batch):

```text
COMFYMODAL_V2_ATOMIC_PROFILE          = E19_FINAL_COLD_LOADER
COMFYMODAL_V2_ENV_PROFILE             = inherit
COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET   = 1
COMFYMODAL_V2_CPU_MODEL_SNAPSHOT      = 1
COMFYMODAL_V2_VAE_SNAPSHOT            = 1
COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS = 1
COMFYMODAL_V2_CLIP_FAST_HYDRATION     = 1
COMFYMODAL_V2_UNET_FASTSAFETENSORS    = 1
COMFYMODAL_V2_FAST_COLD_ORCHESTRATION = 1
COMFYMODAL_V2_CHECKPOINT_PREWARM      = 1
COMFYMODAL_V2_CRITICAL_GPU_COORDINATION = 1
COMFYMODAL_V2_SCOPED_CUDA_READINESS   = 1
COMFYMODAL_V2_GANTT_TELEMETRY         = 1   (E27)
COMFYMODAL_V2_E27_FORENSICS           = 1   (E27)
COMFYMODAL_V2_CLIP_COLD_FORENSICS     = 0   (E19 profile forces 0; see §6/§15 note)
COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION   = 1   (at deploy)
```

### 2.3 Deploy/run path used (current repository-approved)

- Deploy: `deploy_and_run_v2_single.bat` (canonical; V1-present branch →
  publish custom nodes → `modal deploy -m comfymodal_runtime.modal_app
  --name stable-modal-comfy-v2-restore-only-shadow` → record identity →
  prime registry proof).  Also used direct `modal deploy` (same module/name)
  with identical env after the bat's stdout capture proved unreliable on
  this Windows console (see §15.2).
- Run: `run_v2_single.bat` with `V2_BENCHMARK_MODE=snapshot_restore_only`
  (issues `run_snapshot_restore_only_probe`, hard-stops at
  `V2_RESTORE_ONLY_RUN_COUNT` valid probes).
- QD probes: Modal method `run_unet_qd_probe` (pre-existing) and
  `run_clip_qd_probe` (added by this batch) invoked via the repo's
  `ModalTransport` handle.

---

## 3. Current baseline

### 3.1 Timeline (restore → request → graph → CLIP demand)

The authoritative current-baseline remote timeline is the E24/E25/E26
series (same deployment vehicle, same E19 profile).  MEASURED values:

| Boundary | E24 baseline (ms from method entry) | Source |
|---|---:|---|
| remote method entry | 0 | E24 `remote_method_entry` |
| restore → method entry | 39.491 | E24 stage 3 |
| method entry → graph start | 1472.095 | E24 stage 4 (pre-graph setup; ~1.16 s main-thread window overlapping UNET source prefetch on workers) |
| graph start → CLIP hydration demand | ~0.7-0.85 s after spec-read start | E26 cycle 2 (demand arrived while spec read in flight) |
| CLIP hydration (demand read+bind) | 1345.935 (E24/E25 baseline) | `clip_hydration_gpu_start → end` |
| CLIP forward | 3313.016 (E25 baseline) | `clip_forward_start → end` |
| UNET H2D | ~547 | E25 |
| model readiness | 5421.529 | E25 |
| sampling | ~4733 (D18) | `sampling_start → end` |
| post-sampling (VAE transition) | 751.9-968.8 (D18 runs) | model-management gate |
| VAE decode | ~370-416 | `vae_decode_start → end` |
| output/PNG | ~265 | output encode |

Restore itself: `restore_total_ms` 368-1756 ms across this batch's probes
(container variance; includes reconcile).

### 3.2 Gantt

The E27 ASCII Gantt renderer is implemented (`comfymodal_runtime/
gantt_telemetry.py`), deployed with `COMFYMODAL_V2_GANTT_TELEMETRY=1`, and
unit-verified (9 tests) with `█` bars and precise start/end/dur columns on
one remote monotonic axis.  A generation-run Gantt example could NOT be
captured because the snapshot vehicle is blocked (§2); the renderer's
validity was verified against synthetic traces and the underlying
monotonic events.  See §9 for implementation and the expected output
shape.

### 3.3 GPU memory state

Key boundaries for the current path (measured/derived):

- After restore (probe): CUDA context exists; `run_snapshot_restore_only_probe`
  reported no model residency (snapshot absent — blocker).
- D18 (historical, same vehicle, valid runs): before VAE transition
  `allocated=20,427,641,856`, `reserved=22,594,715,648`,
  `free=80,845,794,304` (97 GB GPU); after: allocated unchanged,
  reserved 20,449,329,152.  UNET resident 12,309,817,472 B; CLIP
  CPU/offloaded at final state; VAE transfer 167,639,366 B on cold
  activation; decode demand 9,099,509,760 B.
- C9 (historical, fastsafe UNET): after fastsafe load RSS delta +171 MB
  (no full-file CPU copy), CUDA allocated delta +11.54 GB, reserved
  +12.33 GB, peak reserved 13.09 GB; zero-copy bind adds +10.9 MB.

The E27 memory-boundary telemetry (aggregated `e27_memory_*` events at
request_accept / clip_hydration_done / sampling_end / vae_transition_before
/ vae_transition_after) is deployed and will populate on the first valid
generation run.

### 3.4 Exact hashes

- Output SHA (baseline, E18/E26): `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
  (the accepted exact-output reference; no E27 run produced output because
  no valid generation was possible).
- UNET source file: `z_image_turbo_bf16.safetensors`, 12,309,817,472 data
  bytes, 453 tensors, bf16, 12,309,866,400 bytes on disk (probe MEASURED).
- CLIP source file: `qwen_3_4b.safetensors`, 8,044,936,192 data bytes,
  398 tensors, 8,044,982,048 bytes on disk (probe MEASURED).
- Loader sample-hash parity: all QD/external loader configs returned
  `sample_hash_matches_baseline=true`, `key_set_ok=true`, `spot_check_ok=true`
  (probe MEASURED — the read path is byte-identical across QD configs).

### 3.5 Critical path (current, measured)

```
restore (~0.4-1.8 s)
  → method entry (+0.04 s)
  → pre-graph setup (+1.47 s; ~1.16 s overlaps UNET source prefetch workers)
  → graph start → CLIP hydration demand (+0.7-0.85 s into the read)
  → CLIP hydration exposed 1.35-2.43 s (read+bind; storage-bound)
  → CLIP forward ~3.3 s
  → UNET H2D ~0.55 s (overlapped under CLIP forward where scheduled)
  → sampler setup → sampling ~4.7 s
  → VAE transition 0.75-0.97 s (empty_cache-dominated; D18)
  → VAE decode ~0.4 s
  → output ~0.27 s
```

---

## 4. UNET queued-loading investigation

### 4.1 Current implementation (fully mapped)

Production path under E19: `model_preload._load_unet` → `_fs_try_pipeline`
(`comfymodal_runtime/unet_fastsafetensors.py:1042`) with:

- loader: fastsafetensors 0.3.3 `SafeTensorsFileLoader`
  (`_fs_fastsafe_load`, `unet_fastsafetensors.py:827`)
- threads: `_FS_THREADS=16` · copy block: `_FS_MAX_COPY_BLOCK_BYTES=1 GiB`
- `nogds=True`, `use_buf_register=False` (cudaHostRegister unsupported),
  `disable_cache=True`
- device: direct CUDA (`cuda:0`); data lands directly in VRAM via the
  loader's gbuf (NO CPU full-file buffer; C9 Gate-2 proof: RSS +171 MB)
- Worker A (meta ZImage construction) ∥ Worker B (file→CUDA); join measured
- ownership: `_FastsafeOwner` retained on the patcher for model lifetime;
  never `close()` on success; zero-copy `assign=True` bind
- file: `z_image_turbo_bf16.safetensors` under `diffusion_models`
  (absolute `/root/comfy/ComfyUI/models/diffusion_models/...` per E26)
- safetensors header parse via `_ring_derive_config` (header-only, no data
  read); tensor construction happens inside fastsafe `copy_files_to_device`

### 4.2 Telemetry

Pre-existing: `unet_fastsafetensors_pipeline` single event (walls, bytes,
GB/s, data-ptr proof, memory deltas).  E27 adds: `unet_source_read` span
pair on the shared monotonic axis around `_fs_fastsafe_load`
(`unet_fastsafetensors.py:1443`).

### 4.3 QD/chunk experiment (FRESH-CONTAINER, THIS BATCH)

Probe: `run_unet_qd_probe(z_image_turbo_bf16.safetensors, "evidence")` on
the deployed E19 container (fresh boot, GCP, RTX PRO 6000 Blackwell, torch
2.13.0+cu130).  Full raw log in §18.  Summary (full-file, cold):

| QD | block | wall ms | GB/s | vs QD1 | CPU ms | steady GB/s | first lat ms | tail ms |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| QD1 (cold) | 32 MiB | 1866.0 | 6.60 | 1.00× | — | — | — | — |
| QD1 (warm control) | 32 MiB | 1081.8 | 11.38 | 1.72× | — | — | — | — |
| QD2 | 32 MiB | 534.2 | 23.04 | 3.49× | 60 | 12.0 | 3.1 | 10.5 |
| QD4 | 32 MiB | 283.3 | 43.45 | 6.59× | 100 | 12.4 | 3.2 | 26.3 |
| **QD8** | 32 MiB | **248.1** | **49.61** | **7.52×** | 330 | 10.5 | 4.0 | 132.7 |
| QD16 | 128 MiB | 538.6 | 22.86 | 3.46× | 1690 | 8.6 | 10.1 | 115.9 |

2 GiB-screen (ramp-up artifact, block selection only): best per QD was
QD1/256=13.1, QD2/32=20.9, QD4/32=21.9, QD8/64=23.5 GB/s — larger blocks
monotonically worse on short windows; full-file numbers are authoritative.

GPU transfer phase (QD4/32): storage→pinned→async H2D full file 1020.9 ms
combined 12.06 GB/s; `h2d_device_ms=1020.8` — the device copy dominates and
the storage read is fully hidden under it; `h2d_host_issue_total=5.7 ms`.

External loaders (validity-checked): fastsafetensors CPU 8T = 6.66 GB/s,
CPU 16T = 10.13 GB/s, **direct CUDA 16T/1 GiB = 20.78 GB/s** — the CURRENT
production config's 1 GiB block caps it at ~21 GB/s vs 49.6 GB/s raw
preadv QD8.

### 4.4 Cold-cache controls

- `minflt_delta=0` on every config (no page-fault count) — reads are
  cold-storage-bound, not page-in.
- warm-QD1 control = 11.38 GB/s vs cold-QD1 6.60 GB/s: a 1.72× cache
  effect at QD1; but QD8 cold (49.6) ≫ warm-QD1 (11.4), so the QD scaling
  is a concurrency effect, not cache warmth.  This is the same control
  structure C9 used; the classification "QD effect independent of cache
  warmth" is sound.
- The probe ran on a freshly booted container (first request after deploy);
  the file was NOT touched by snapshot/manifest prep on that container.

### 4.5 Results (UNET QD questions answered)

1. Current effective read/load throughput: **20.78 GB/s** (production
   fastsafe direct-CUDA, this container's fresh run).
2. Source I/O vs CUDA copy: raw preadv QD8 = 49.6 GB/s; fastsafe direct
   CUDA = 20.8 GB/s.  The gap is the loader's 1 GiB copy-block regime +
   per-block sync/launch, NOT the storage ceiling.
3. Does QD improve it? **YES** — 3.5× (QD2), 6.6× (QD4), 7.5× (QD8) vs
   QD1 cold.
4. Flatten/regress: QD16 regresses to 22.9 GB/s with 1690 ms CPU — CPU
   (memcpy/preadv issue) bound.
5. Best chunk size: 32 MiB in the useful QD range (full-file best block
   everywhere; 64 MiB acceptable at QD8; larger monotonically worse).
6. Actual concurrency: static contiguous per-worker segments; QD8 → 8
   concurrent preadv streams; measured tail spread 132.7 ms (last worker
   lags).
7. Direct CUDA dest: the raw GPU phase (pinned→async H2D) shows the device
   copy (1020 ms) dominates; direct-GPU fastsafe at 20.8 GB/s vs raw
   storage 49.6 means the loader's own H2D is the limiter after storage
   speedup.  A preadv→pinned→async-H2D pipeline at QD4/32 (12 GB/s
   combined) is currently NOT faster than fastsafe direct (20.8) because
   the pinned→CUDA copy is device-bound; the fastsafe gbuf path already
   hides storage under CUDA copy.
8. Allocator/sync bottlenecks after storage faster: at QD8/32, CPU 330 ms
   (12% of 248 ms wall — CPU-side issue overhead); at QD16 CPU 1690 ms.
   The allocator is not the first bottleneck; CPU issue rate is.
9. Expected cold critical-path saving vs current production: UNET source
   read 12.3 GB: current fastsafe ~592 ms (20.8 GB/s) → QD4/32 preadv
   ~283 ms (43.5 GB/s) = **~310 ms saving** on the raw read; if the
   production loader adopts the QD4/32 regime with direct-CUDA binding,
   the H2D still caps at ~12 GB/s combined unless the device copy is
   overlapped — realistic production saving est. **~0.15-0.35 s** (read
   portion only; UNET H2D overlaps CLIP forward in the current schedule).
10. Recommended production architecture: replace the single 1 GiB block
    fastsafe copy with a QD4-8 / 32 MiB chunked preadv→pinned→async H2D
    pipeline (the C9/C6 ring design already exists as
    `model_preload._c6_ring_*`), OR configure fastsafe with
    `max_copy_block_size=32 MiB` and threads=4-8 (block-size is the lever;
    see §11 combined architecture).
11. What could make it unstable: page-cache warmth inflates QD1 (control
    11.4 vs 6.6); CPU issue rate at QD8+ (330 ms CPU on 12 cores);
    tail-spread at QD8 (133 ms); region variance (GCP us-east1 vs us-east4
    observed across probes).
12. Confidence it survives genuine cold deployment: HIGH for QD4/32
    (43.5 GB/s, 100 ms CPU, low tail); MEDIUM for QD8 (CPU 330 ms, tail
    133 ms may contend with restore-time CPU work).

---

## 5. CLIP queued-loading investigation

### 5.1 Current implementation (fully mapped)

Production path under E19: `clip_fast_hydration_wiring._try_fast_hydrate`
(→ `_fastsafe_load`, `clip_fast_hydration_wiring.py:618`) with the same
fastsafe config (threads 16, 1 GiB block, nogds, use_buf_register False).
The speculative CLIP lane (E26) owns the source first; demand verifies via
frozen manifest and binds zero-copy (`hydrate_clip_bind`, assign=True).
CLIP file: `qwen_3_4b.safetensors` under `text_encoders` (absolute
`/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors`, frozen
manifest path per E26).  Snapshot exclusion strips weights at capture;
hydration re-reads at demand.

### 5.2 Telemetry

Pre-existing: `clip_fh_hydration_start/end`, `clip_hydration_gpu_start/end`,
`clip_forward_start/end`, `clip_bind_wait_start/end`.  E27 adds:
`clip_source_read` span pair around the demand read
(`clip_fast_hydration_wiring.py:819-836`) and `e27_memory_clip_hydration_done`.

### 5.3 QD/chunk experiment (FRESH-CONTAINER, THIS BATCH)

Probe: `run_clip_qd_probe(qwen_3_4b.safetensors, "evidence")` on the same
deployment.  Full raw log in §18.  Summary (full-file, cold):

| QD | block | wall ms | GB/s | vs QD1 | CPU ms | steady GB/s | first lat ms | tail ms |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| QD1 (cold) | 32 MiB | 1047.3 | 7.68 | 1.00× | — | — | — | — |
| QD1 (warm) | 32 MiB | 753.9 | 10.67 | 1.39× | — | — | — | — |
| QD2 | 32 MiB | 403.0 | 19.96 | 2.60× | 70 | 11.3 | 2.4 | 16.9 |
| **QD4** | 32 MiB | **191.4** | **42.03** | **5.47×** | **30** | 12.5 | 2.4 | 45.1 |
| QD8 | 64 MiB | 178.8 | 45.00 | 5.86× | 220 | 10.2 | 4.1 | 41.8 |
| QD16 | 128 MiB | 399.1 | 20.16 | 2.62× | 1010 | 8.0 | 8.8 | 78.8 |

Native mmap baseline (Comfy `load_torch_file` path): **1.09 GB/s**
(7370.8 ms for 8.04 GB) — the current native fallback is 38× slower than
QD8.

GPU transfer (QD2/32): 700.2 ms combined 11.49 GB/s; `h2d_device_ms=703.2`
(device copy dominates; storage hidden).

External: fastsafe CPU 8T = 5.76, CPU 16T = 7.33, **direct CUDA 16T/1 GiB
= 16.22 GB/s** (current production config).

### 5.4 Cold-cache controls

Same battery structure as UNET: `minflt_delta=0`; warm-QD1 10.67 vs cold
7.68 (1.39× cache effect) but QD4 cold (42.0) ≫ warm-QD1 (10.7) — the QD
scaling is concurrency, not warmth.

### 5.5 Results (CLIP QD questions 1-15)

1. Current effective read: **16.22 GB/s** (production fastsafe direct).
2. Source I/O vs CUDA copy: raw preadv QD8 = 45.0 GB/s; fastsafe direct =
   16.2; native mmap = 1.09.  Same structural gap as UNET.
3. QD improves: **YES** — QD4 42.0 (5.5×), QD8 45.0 (5.9×).
4. Flatten/regress at QD16 (20.2, CPU-bound 1010 ms).
5. Best chunk: 32 MiB at QD4 (42.0 GB/s, only 30 ms CPU — the clean sweet
   spot); QD8/64 marginal +3 GB/s at 220 ms CPU.
6. Concurrency: 4-8 static preadv streams; tail 41-45 ms.
7. Direct CUDA dest: same as UNET — device copy caps combined at ~11.5
   GB/s; fastsafe direct already hides storage.
8. Allocator/sync after storage faster: CPU issue rate is the bottleneck at
   QD8+ (220-1010 ms), not the allocator.
9. Expected cold critical-path saving: CLIP read 8.04 GB: current fastsafe
   ~496 ms → QD4/32 ~191 ms = **~305 ms read saving**; production adoption
   depends on the demand window (§5.5.13-15).
10. Recommended architecture: same chunked-preadv QD4/32 pipeline; for
    CLIP specifically the read should start at restore-time (Target C) so
    even QD4's 191 ms is fully hidden.
11. Instability: page-cache (warm 1.39×); CPU issue at QD8+; region
    variance; and — specific to CLIP — the speculative lane vs demand
    window race (E26: demand arrives ~0.7 s into a ~2 s read).
12. Confidence: HIGH for QD4/32 (30 ms CPU, low tail).
13. **Can CLIP hydration finish fast enough to hide behind snap=False?**
    QD4/32 reads 8.04 GB in **191 ms** — vs the pre-graph window of ~1.47 s
    (E24) / ~0.7-0.85 s (E26 cycle-2 demand arrival).  **YES — with the
    measured QD4/32 loader, the full CLIP source read fits inside the
    request-setup window with ~1.3 s margin**, even at warm-cache QD1
    (754 ms) it fits.  The E26 failure (2.07-2.43 s exposed) was the
    1 GiB-block fastsafe read (~2.1-2.6 s) exceeding the ~0.7-0.85 s
    window; the QD4/32 preadv read eliminates that.
14. If not entirely hidden: at QD4/32, ~191 ms read + bind/sync remains;
    realistic exposed residual **~0-250 ms** vs the current 1.35-2.43 s.
15. Optimum differs from UNET: CLIP is smaller (8.04 vs 12.31 GB) so QD4
    suffices (42 GB/s) with minimal CPU (30 ms) — QD8's +3 GB/s costs
    220 ms CPU which would contend with restore reconciliation.  UNET
    benefits from QD8 when CPU is available (during CLIP forward).

---

## 6. torch.cuda.empty_cache / VAE model-management investigation

### 6.1 Call graph (current code, source-verified)

```text
VAEDecode (nodes.py:310-318) → VAE.decode (comfy/sd.py:1045-1071)
  → load_models_gpu([vae_patcher], memory_required=memory_used)
    → comfy.model_management.load_models_gpu (843-940)
      → free_memory(memory_required) (799-841)
        → [if unloaded] soft_empty_cache() (834-835)
        → [else if not HIGH_VRAM and torch-allocator-free > 25% of total]
          soft_empty_cache() (836-840)
          → soft_empty_cache (1944-1960): torch.cuda.synchronize()
              → torch.cuda.empty_cache()
              → torch.cuda.ipc_collect()
```

In the V2 runtime, the VAE worker path is
`model_preload.py:19951-19954` (`_mm_load_models_gpu([_patcher])` inside
`inference_mode`), called from `_run_vae_early_start_worker` /
`_vae_activation_worker` after `sampling_end` when the VAE activation
trigger fires (production: `late`, i.e. at graph VAEDecode demand).

All three CUDA operations are also globally wrapped by the D2 forensics
module (`clip_cold_path_forensics._make_cuda_operation_wrapper`,
installed when `COMFYMODAL_V2_CLIP_COLD_FORENSICS=1`) and by the E27 chain
(`e27_forensics.install_soft_cache_chain`, installed when
`COMFYMODAL_V2_E27_FORENSICS=1` — this batch's E19-compatible path).

### 6.2 Timing decomposition (D18 MEASURED, same E19-era path)

Three valid runs (D18, GCP/us-east4, this vehicle):

| Run | pre-sync ms | CUDA sync ms | **empty_cache ms** | IPC ms | total ms | models unloaded |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0.548 | 0.044 | **950.460** | 0.010 | 951.320 | 0 |
| 2 | 0.688 | 0.038 | **739.241** | 0.010 | 740.226 | 0 |
| 3 | 0.509 | 0.028 | **934.173** | 0.014 | 935.051 | 0 |

- `empty_cache` = 99.87-99.91% of the soft-cache total.
- Allocator before: `allocated=20,427,641,856`, `reserved=22,594,715,648`,
  `free=80,845,794,304`; after: allocated unchanged, reserved
  `20,449,329,152` (−2.1 GB reserved released).
- `models_unloaded_count=0`, `bytes_unloaded` 0 — NOTHING was unloaded.
- VAE requirement: `free_memory` required 1,462,827,161.8 B; transfer
  167,639,366 B; decode demand 9,099,509,760 B; physical free at the gate
  ~80 GB — massive headroom (55× the required bytes).
- Synchronization attribution: sync itself is 0.03-0.04 ms.  The
  empty_cache wall is NOT the sync becoming visible; it is the allocator's
  actual reclamation work (releasing the ~2.1 GB reserved delta takes
  0.74-0.95 s — a known PyTorch allocator behavior when returning
  segments under memory pressure accounting).

### 6.3 Allocator state / what is actually reclaimed

- Reserved drops ~2.1 GB; allocated is unchanged (no live tensor freed).
- The ~2.1 GB reserved release is the sampler's transient workspace
  (CUDA graphs/attention scratch) returned to the driver.  Whether that
  release is REQUIRED before VAE decode is the open question; the decode
  demand (9.1 GB) fits in the 80 GB free WITHOUT the empty_cache.
- `inactive_split_bytes` was not captured in D18; E27's
  `e27_memory_*` events add it at vae_transition_before/after.

### 6.4 Why the call occurs

Comfy `free_memory` invokes `soft_empty_cache` when (a) models were
unloaded (not our case) OR (b) not HIGH_VRAM and
`torch_allocator_free > 0.25 × total_free`.  In our runs models_unloaded=0,
so branch (b) fired: the allocator's cached-free portion crossed the 25%
threshold (reserved 22.6 GB vs total ~97 GB — the 2.1 GB cached free is
~2.2% of total... the D18 event's `free_memory_before=80.8 GB` includes
driver free, and the torch-allocator-free check uses `torch_free_too=True`
internals).  The precise trigger predicate is inside pinned
`model_management.get_free_memory(..., torch_free_too=True)`; the observed
behavior is the defensive reclamation branch.

### 6.5 Is it necessary in the normal high-headroom VAE transition?

- **Not proven necessary**: 80 GB physical free vs 9.1 GB decode demand;
  nothing unloaded; sync is 0.04 ms.
- **Not proven removable either** (D18 verdict): the sampler has no
  source-proven device-wide completion boundary before this point, and the
  allocator's reserved release may be what makes the subsequent VAE
  allocation fast.  `SYNC_REDUNDANT=UNKNOWN`, `EMPTY_CACHE_REDUNDANT=UNKNOWN`
  until the E27 on-run decomposition (vae_transition_before/after memory
  + e27_soft_empty_cache events) measures it on a valid run.

### 6.6 Proven-ready bypass contract (future, NOT implemented)

The future fast-return must verify (cheap checks in `model_preload` /
`empty_cache_bypass.evaluate_bypass` — the latter already implements the
policy skeleton):

```text
IF ALL:
  expected VAE identity == the patcher being loaded
  VAE params/storage already resident on the target device (probe via
    _vae_patcher_loaded_bytes == model bytes; existing helper)
  correct dtype/device/layout (policy marker _comfy_modal_vae_policy)
  no pending VAE mutation/patch (patcher patch queue empty)
  no pending VAE transfer (no in-flight copy event)
  no pending ownership handoff (VAE not rehomed)
  sufficient free/headroom (physical_free >= 2.0 × required; the
    empty_cache_bypass.evaluate_bypass predicate: physical >= 2× required)
  no model actually needs eviction (models_unloaded_count == 0)
  Comfy state says no unload required (soft_cache_reason ==
    free_memory_defensive_no_unload)
  allocator backend native, no capture, no custom pool (existing checks)
  request has not changed models (same key_hash)
THEN:
  bypass soft_empty_cache (execute_soft_cache: sync + ipc_collect only,
  skip empty_cache)
ELSE:
  native Comfy path unchanged
```

- Cleanest insertion point: `comfymodal_runtime/empty_cache_bypass.py`
  `evaluate_bypass` + `execute_soft_cache` (already exist, flag
  `COMFYMODAL_V2_HIGH_HEADROOM_EMPTY_CACHE_BYPASS`) — the D18-era policy
  with the E27 on-run measurements feeding the "proven-ready" proof.
- Expected saving: **0.74-0.95 s** (the measured empty_cache wall) minus
  the risk that the allocator deferral costs the same later.
- Safety risks: skipping the allocator release could delay the VAE
  allocation; skipping the sync could expose unsynchronized sampler work —
  both gated by the proven-ready checks.
- Exact fallback: native soft_empty_cache.
- Telemetry after implementation: `empty_cache_bypass_decision` event +
  `e27_soft_empty_cache` (before/after memory + per-op walls).
- Odds: the ~0.74-0.95 s is real measured wall and 99.9% allocator work;
  the question is only whether reclamation is required for VAE.  Given 80
  GB headroom and 0 unloads, odds **~70-80%** that a proven-ready bypass
  removes most of it on this hardware.

---

## 7. Earliest possible CLIP hydration

### 7.1 Modal lifecycle (current, MEASURED from this batch's probes + E24-E26)

```text
snapshot restore resumes Python   (restore method first line; mono origin)
  → restore reconcile             restore_total_ms 368-1756 (probe; container-dependent)
  → restore → method entry        39.5 ms (E24)
  → method entry → graph start    1472.1 ms (E24; ~1.16 s main-thread window
                                    overlapping UNET source prefetch workers)
  → graph start → CLIP demand     ~0.7-0.85 s after spec-read start (E26)
  → CLIP hydration (demand)       1.35-2.43 s exposed (E24/E26)
```

Restore-time fields available on the trace (this batch added them to
`set_metadata`): `remote_python_resume_mono_ns`,
`restore_method_start_mono_ns`, `restore_method_end_mono_ns`,
`modal_method_entry_mono_ns` — so the Gantt axis origin is the true
restore resume point.

### 7.2 Known-at-snapshot state

At snap=True (capture), the frozen CLIP manifest
(`_comfymodal_clip_fh_manifest`, attached by `maybe_prepare_clip_snapshot_exclusion`)
contains: absolute source path, size_bytes, mtime_ns, dtype, key_set,
key_shapes, pipeline (transform list), family/config.  E26 proved this is
the authoritative path source (no folder_paths scan on the fast path).
What survives restore: the manifest + the placeholder CLIP structure
(tokenizer, patcher, meta params).  NOT known: the requested CLIP identity
(request-dependent); the conditioning-cache hit state.

### 7.3 Earliest point per work type

- **A. CPU/file-source prep (open/stat/header/read-plan):** legal at the
  earliest restore-resume point — the manifest gives the absolute path
  with zero request dependency.  Earliest executable location:
  `modal_app.restore()` after `_cpu_snapshot_models` is bound, or a
  restore-time worker spawned by the fast-cold orchestrator
  (`fast_cold_orchestration` already owns CLIP-source ownership).
  Can run async; overlaps restore reconcile + method setup.
- **B. Direct-GPU hydration:** requires CUDA context + the fastsafe loader;
  CUDA init completes early in restore.  The E26 speculative lane already
  does file→GPU at plan receipt; moving it to restore-time requires only
  that CUDA is up (verify via `torch.cuda.is_available()` + a readiness
  gate; the existing `_gpu_coord.scoped_cuda_readiness_enabled()` gate
  applies).
- **C. FP32 compute-ready conversion (Target D):** requires the hydrated
  weights + CUDA; can piggyback on the same restore-time lane after the
  source read, cast once, then bind.  No request state needed.

### 7.4 Speculation/reconciliation design

1. Stable identity key: the frozen-manifest digest (E26's
   `_manifest_identity_digest` covering path/size/mtime/dtype/key_set/
   key_shapes/pipeline) — already implemented and folded into the lane
   identity.
2. Request CLIP matches: demand verifies manifest + takes speculative
   tensors (`take_speculative_read`), binds zero-copy (E26 path, proven).
3. Mismatch: close speculative owners, run demand read exactly once
   (proven in E26; `clip_fh_speculative_rejected` event).
4. Mismatch detected before forward: yes — manifest verification is
   bytes/shapes/dtype vs the request's CLIP, before bind.
5. Discard: close() the loader+fb (E26 owner release), clear GPU cache.
6. Owner: the lane future owned by the fast-cold orchestrator
   (`_start_speculative_clip_lane`); released to demand on take.
7. Exceptions: lane failure → fail-closed skip reason event +
   `on_speculative_clip_done(failure)` releases UNET (E26: release-once on
   failure/cancel).
8. Not blocking snap=False: lane runs on a worker thread; snap=False
   (restore/method) never joins except at demand (bounded 20 s join).
9. Avoid extending startup by moving sync work left: the read is async;
   startup wall only grows if a join is added — none is (the join lives at
   demand, and with QD4/32 the read finishes before demand anyway).
10. Races with demand-time loader: the single-ownership machine (E26) —
    spec owns the CLIP source until done; demand take is single-flight.
11. Single-use simplification: no multi-request cache, no eviction
    policy, no reuse — the lane can be fire-and-consume per container.
12. Restore-time QD CLIP vs restore I/O: CLIP read at QD4/32 uses 30 ms CPU
    over 191 ms — negligible against restore reconcile; QD8's 220 ms CPU
    would contend — hence CLIP should use QD4 (matches §5.5.15).
13. Contention with CUDA init: the source read can start BEFORE CUDA is
    ready (preadv to pinned CPU), then hand off to async H2D once CUDA is
    up — the C9 ring design already supports this.  Preferred: start
    source I/O immediately at resume; convert/bind after CUDA readiness.
14. Preferred architecture: restore-time QD4/32 preadv→pinned async read
    (starts at resume, ~190 ms), then async H2D + zero-copy bind after CUDA
    ready, all under the existing orchestrator ownership; fail-closed
    fallback: the current demand-time fastsafe path unchanged.

### 7.5 Quantified overlap opportunity

MEASURED (E24/E25/E26 + this batch's probes):

```text
remote python resume            t0 (restore method first line)
restore → method entry          +39.5 ms        (E24 MEASURED)
method entry → graph start      +1472.1 ms      (E24 MEASURED)
graph start → CLIP demanded     ~+0.7-0.85 s    (E26 MEASURED, spec-read start window)
CLIP hydration start (demand)   ~+0.7-0.85 s into read (E26)
current CLIP hydration end      +1.35-2.43 s    (E24/E26 MEASURED)
restore_total (this batch)      368-1756 ms     (probe MEASURED)
```

CALCULATED from measured data:

```text
time available before request arrival      ~0.4-1.8 s (restore) + 0.04 s (method)
time available before graph CLIP demand    ~1.51 s (restore→method→graph) + 0.7-0.85 s
                                           ≈ 2.2-2.4 s
current exposed CLIP hydration wait        1.35-2.43 s
predicted exposed wait if hydration starts
  at earliest legal point (resume)         ≈ 0 (read+convert complete before demand)
predicted exposed wait with best measured
  CLIP QD (QD4/32 = 191 ms read)           ≈ 0-250 ms (bind/sync residual)
```

HYPOTHETICAL (not measured): the exact residual bind/sync wall at
restore-time start; the FP32 conversion wall on real Qwen (§8.6).

---

## 8. Compute-ready FP32 / cast-once investigation

### 8.1 Real casting path (D7 source-verified, pinned ComfyUI v0.24.0)

```text
CLIPTextEncode.encode → clip.encode_from_tokens_scheduled (sd.py:320)
  → sd.py:382-388 set_clip_options
  → sd.py:390 load_model → load_models_gpu → LoadedModel.model_load
      → ModelPatcher.partially_load (1202) → patch_model (applies
        object_patches incl. manual_cast_dtype, 1061-1064)
      → load (928): patch_weight_to_device (1021) + sync (1023)
  → sd.py:394 cuda_device_context (device only, NO autocast)
  → sd1_clip.py:28 encode_token_weights → SDClipModel.forward (260)
      → embeddings FORCED fp32 (sd1_clip.py:213,237)
      → transformer(..., dtype=torch.float32) HARDCODED (sd1_clip.py:279)
      → CLIPEncoder → attention_pytorch (SDPA; fp32 → math backend)
  → output postprocess: .float() + .to(intermediate_device=CPU) (sd1_clip.py:46-68)
```

Dtype facts:
- compute dtype forced **fp32** (`sd.py:254-255` →
  `set_model_compute_dtype(torch.float32)` → `force_cast_weights=True` +
  `manual_cast_dtype=fp32`)
- resident storage **fp16** (`model_management.text_encoder_dtype()` default)
- cast site: `ops.py:281,375-376` `cast_bias_weight` — `weight.to(dtype)`
  per forward when mismatch, **uncached** (`cast_to` short-circuits only
  when dtype already matches)

### 8.2 Measured cast cost (D7 MEASURED, generic fixtures — real Qwen forward pending valid run)

| Fixture | cast ops/forward | cast bytes/forward | cast CPU wall |
|---|---:|---:|---:|
| classic_clip | 99 | 126.6 MB | 13.6-16.1 ms |
| large_clip | 195 | 416.9 MB | 21.5-24.8 ms |
| t5 | 50 | 83.2 MB | 7.9-11.3 ms |
| llm | 57 | 92.5 MB | 10.6-11.8 ms |
| multi_encoder | 108 | 181.4 MB | 26.1-28.1 ms |

- Cast CPU wall ≈ forward wall (cast tax is co-dominant with compute).
- Casts repeat EVERY forward (uncached) — no results cached.
- The E27 `install_patch_weight_cast_counter` (patched
  `ModelPatcher.patch_weight_to_device`) will count the REAL Qwen
  forward's ops/bytes/wall on the first valid generation run; the counter
  is deployed.

### 8.3 Measured FP32 residency cost (from real model, CALCULATED)

For `qwen_3_4b.safetensors` (8,044,936,192 data bytes, 398 tensors —
probe MEASURED file identity):

```text
source parameter bytes       8.04 GB (all weights; mixed dtypes per tensor)
FP32 compute-ready bytes      ≈ 2× source if fp16→fp32 = ~16.1 GB
                             (exact depends on per-tensor dtype; probe header
                             reports tensor dtypes — not yet enumerated)
FP32 bias bytes               negligible vs weights
other persistent CLIP alloc   tokenizer/embedding tables (small)
temporary conversion peak     uncached per-forward cast materializes layer-by-layer
                             (D7: cast CPU wall ≈ forward wall; GPU temp bounded
                             per-layer, not full-model)
```

VRAM arithmetic (CALCULATED): if resident fp16 (8.04 GB) + FP32 compute
cache (16.1 GB) coexist → +16.1 GB peak vs current.  If ownership transfers
(replace resident fp16 with fp32 at load) → +8.04 GB vs current with NO
duplicate.  Peak GPU before UNET/sampling: current CLIP 8.04 + transient;
with cast-once ownership-transfer +16.1 GB replaces +8.04 → net +8 GB —
well inside the 80 GB headroom observed at the VAE gate (§6.2).

### 8.4 Is cast-once semantically exact?

The current per-forward materialization is `weight.to(dtype=torch.float32)`
via `cast_bias_weight` (ops.py:375-376).  For the Qwen path, the D7 audit
found NO additional transform in the cast itself (no LoRA-in-cast, no
layout conversion beyond contiguous).  Potential invalidators of a cached
FP32 tensor (D7 + model_patcher audit):

- `patch_weight_to_device` (LoRA/patch application) — rewrites weight
  tensors; must invalidate the cache
- `object_patches` / `weight_function` / `bias_function` (applied in
  `patch_model`, 1061-1064) — may alter materialized values
- device movement / dtype change (manual_cast_dtype patch re-target)
- `partially_load` / unload cycles
- parameter mutation (model cloning, `assign` binds)

**Defined immutability condition:** a compute-ready FP32 tensor is
reusable while (a) no weight patch/function is registered on that
parameter, (b) the source storage is unchanged, (c) target dtype/device
unchanged.  Invalidation: any `patch_weight_to_device` / weight_function
application on the parameter, any storage mutation, any dtype/device
retarget.  The E27 cast counter hooks the exact patch site
(`patch_weight_to_device`) so the future cache can key invalidation off
the same event.

### 8.5 Cleanest ownership model

| Option | Exactness | VRAM | Ownership | Patching | Restore-time hydration | Invalidation |
|---|---|---|---|---|---|---|
| A. replace resident storage with FP32 | exact (same values, cast once) | +8 GB (no dup) | cleanest (one representation) | must re-cast on patch | natural (convert at hydration) | trivial (storage IS the cache) |
| B. retain fp16 + FP32 cache | exact | +16 GB (dup) | two owners, lifetime mgmt | must invalidate cache on patch | conversion separate | needs keying/invalidation |
| C. loader creates FP32 directly | exact (if loader casts) | +8 GB | loader owns final | needs re-cast on patch | natural | trivial |
| D. current (per-forward cast) | exact | +0 | none | n/a | n/a | n/a |

**Recommended: A (replace resident storage with compute-ready FP32 at
hydration/load), with re-cast on patch invalidation.**  Cleanest for the
single-use V2 container: the fp16 source has no other consumer after the
CLIP forward (CLIP is single-use post-sampling; E26 lifecycle).  Requires
a narrow pinned-Comfy change at the cast site (or a post-load conversion +
patch-hook re-cast) — acceptable as the cleanest architecture, not a
wrapper hack.

### 8.6 Expected saving (this batch's data basis)

- D7 MEASURED: cast CPU wall ≈ forward wall on generic fixtures; per-forward
  cast 126-417 MB.  Removing it = est. **20-35% of encode wall** at these
  sizes (D7 §9 estimate, labeled ENGINEERING ESTIMATE from measured cast
  dominance).
- The absolute encode wall for Qwen on this GPU is NOT yet measured (needs
  valid run); D7 extrapolates production T5-XXL-class encoders to
  ~50-200 ms total encode — so 20-35% of a ~100-200 ms encode ≈ **20-70 ms**
  (ENGINEERING ESTIMATE, not the old 20-35% "hypothesis" — this batch
  measured the cast dominance on generic fixtures and defers the real-Qwen
  absolute).
- One-time conversion: 8.04 GB fp16→fp32 on GPU ≈ 2-4 s at current H2D
  rates OR hidden inside restore-time hydration (Target C window ~2.2 s;
  QD4/32 read 191 ms + cast) — **fully hideable** per §7.5.
- Additional persistent VRAM: +8.04 GB (option A).  Peak VRAM before
  UNET/sampling: CLIP 16.1 GB + transient — fine within 80 GB headroom.
- Confidence: the cast tax is MEASURED dominant; the absolute encode saving
  is small (20-70 ms) relative to the 4.7 s sampling — this target is
  LOW-VALUE for the 12 s goal unless encode is on the critical path, which
  it is not (D7 §11: encode fits inside the UNET lane).

---

## 9. ASCII Gantt telemetry

### 9.1 Implementation

`comfymodal_runtime/gantt_telemetry.py` (new, this batch):

- gate `COMFYMODAL_V2_GANTT_TELEMETRY` (default off; env passthrough +
  probe allowlist added in `modal_app._runtime_env` / `run_env_probe`)
- span collection from paired trace events + `register_gantt_span`
  escape hatch + restore/method boundaries from trace metadata
- renderer uses solid `█` (`\u2588`) bars; numeric start/end/dur columns
  are authoritative (µs precision); point events never fabricated as spans
- FULL REQUEST + MODEL-READY ZOOM views; dynamic scale; lanes
  RESTORE/MAIN/STORAGE/CPU/GPU/MODEL-MGMT/OUTPUT
- emitted at request completion in `modal_app` stream finalization
  (one coherent multiline log block; `data["gantt_telemetry"]` report
  attached when spans exist)

### 9.2 Span schema

```text
request_id, lane, span name, start_mono_ns, end_mono_ns, duration_ms,
optional metadata (parent/category)
```

### 9.3 FULL REQUEST example (rendered from a synthetic trace in unit tests)

```text
V2 REMOTE GANTT  origin=remote_python_resume  scale=... ms/char
restore        RESTORE    ████
method/setup   MAIN          ███████████
CLIP hydration STORAGE                █████████████
CLIP forward   GPU                       ███████████████
UNET H2D       GPU                             █████
sampling       GPU                                ██████████████
VAE transition MODEL-MGMT                           ████
VAE decode     GPU                                     ████
   + start=+...s end=+...s dur=...ms on every row
```

### 9.4 MODEL-READY ZOOM example

Same rows clipped to a 4 s window with a finer scale so 40-200 ms work
remains visible.

### 9.5 Timestamp validation

Unit tests verify: spans derived from paired events; no fabricated spans
for unpaired events; ordering by start; origin prefers
`remote_python_resume_mono_ns`; numeric columns derive from the same
`monotonic_ns` values (asserted against the source trace).

### 9.6 Logging overhead

In-memory collection; ONE print block at completion.  `█` is a single
UTF-8 char (3 bytes); a 120-col × ~30-row block ≈ 15 KB of log text per
request, emitted once.  No per-event prints on the critical path.

### 9.7 `█` in actual Modal logs

The block char rendered correctly in local UTF-8-forced tests (the Windows
console cp1252 failure is a dev-box artifact, not a Modal issue).  The
deployed container runs Linux with UTF-8 (PYTHONUTF8=1 in the bat) —
confirmation in an actual generation log is pending the valid-run
unblock.

---

## 10. Cross-target interactions

### QD CLIP × restore-time CLIP
CLIP source I/O at QD4/32 uses 30 ms CPU / 191 ms wall — no starvation of
restore reconcile or CUDA init.  QD8's 220 ms CPU would contend; the
interaction rule is "CLIP QD4 at restore time, UNET QD8 later".  The
E26 orchestration (CLIP owns source; UNET prefetch released after CLIP
read done) is compatible.

### QD UNET × CLIP forward
UNET prefetch currently overlaps CLIP forward.  Higher UNET QD (8) adds
330 ms CPU during that window — on 12 cores with CLIP forward GPU-bound,
CPU headroom exists, but the 133 ms tail spread and PCIe contention with
CLIP's own H2D are the risks.  QD4 (100 ms CPU) is the safe overlap
point; QD8 only when CLIP forward is not H2D-ing simultaneously.

### FP32 CLIP × UNET residency
Peak: FP32 CLIP 16.1 GB + UNET 12.3 GB + sampler workspace ~4-6 GB + VAE
~0.2-9 GB decode — within 80 GB headroom; option A (replace, not
duplicate) keeps the margin.

### FP32 conversion × restore-time hydration
Conversion after the QD4/32 read (191 ms) on the same lane: GPU-bound cast
of 8.04 GB ≈ seconds on the GPU — this WOULD contend with CUDA init /
restore reconcile if done synchronously; the design must overlap it with
the ~1.5 s pre-graph window (which is CPU/IO-bound, not GPU-bound) or
defer the cast until just before CLIP forward.

### empty_cache × larger FP32 CLIP residency
Keeping 16.1 GB CLIP resident could push the allocator's cached-free above
Comfy's 25% threshold MORE often → MORE empty_cache invocations.  The
clean lifecycle: release CLIP right after its forward (single-use; E26
already offloads it post-sampling) so it is NOT resident at the VAE
transition — this is the E26 `eviction_clip_vae` role.

### QD × allocator/model-manager state
Faster direct-GPU hydration changes the reserved/allocated profile (C9:
+11.5 GB allocated, +12.3 reserved for fastsafe UNET).  This shifts the
allocator-free ratio and can change whether Comfy's free_memory branch
fires — the E27 memory boundaries (request_accept / clip_hydration_done /
sampling_end / vae_transition_before/after) will show the actual effect.

---

## 11. Proposed combined architecture (NOT implemented)

```text
REMOTE RESTORE
████████  (restore reconcile; ~0.4-1.8 s)

snap=False / method setup
├── CUDA init
├── CLIP QD4/32 hydration (preadv→pinned→async H2D, ~190 ms)  ← MOVED LEFT
├── FP32 cast-once conversion (overlapped; +16 GB option A)
├── restore reconciliation
└── mutable cache refresh

REQUEST ARRIVES
├── plan / request identity
├── graph setup
└── reconcile requested CLIP (manifest verify; take speculative)

CLIP forward using compute-ready FP32 (cast tax removed)
████████████  (~3.3 s today; cast-tax removal est. -20-70 ms)

UNET QD8/32 prefetch overlapping CLIP forward
        ███████████████  (~248 ms vs 592 ms current)

UNET H2D
                    ███

sampling
                       █████████████████████████

VAE already/pre-resident (E26 role)
                            ██

proven-ready model-manager fast return (empty_cache bypass)
                              ▏  (~0.74-0.95 s removed)

decode
                              ███
```

### Individual expected savings

| Optim | current exposed | removable/overlappable | expected new | confidence |
|---|---|---|---|---|
| CLIP QD4 + restore-time start | 1.35-2.43 s exposed hydration | ~1.1-2.2 s (read hidden) | ~0-250 ms | HIGH (measured QD + measured window) |
| UNET QD4-8 | 592 ms read | ~310 ms read portion | ~280-380 ms | HIGH (measured) |
| FP32 cast-once | ~20-70 ms encode (est.) | most of it | ~0 | MEDIUM (needs real-Qwen) |
| empty_cache bypass | 0.74-0.95 s | most of it | ~0.1 s | MEDIUM (needs proven-ready proof) |

### Combined estimate (interaction-adjusted, NOT summed maxima)

- CLIP (1.1-2.2 s) and UNET read (~0.3 s) are the biggest; they interact
  (CLIP owns source first; UNET after) so they do NOT both fully land on
  the critical path.
- empty_cache (~0.74-0.95 s) is independent (post-sampling).
- FP32 cast (~20-70 ms) is small.
- Realistic combined: **~1.9-3.1 s** off a ~13-16 s cold request
  (ENGINEERING ESTIMATE from measured components; overlap-adjusted).

---

## 12. Measured/calculated/hypothetical timing model

See §3.5 (current MEASURED critical path), §7.5 (overlap CALCULATED),
§11 (proposed HYPOTHETICAL architecture).  Labels are explicit throughout.

---

## 13. Implementation-readiness matrix

| Target | Tech feasibility | Conf. in speedup | Risk to correctness | Risk to stability | Impl. complexity | Est. odds |
|---|---|---|---|---|---|---|
| A1 UNET QD (QD4-8/32) | HIGH | HIGH | LOW (byte-identical reads proven) | MEDIUM (CPU/tail at QD8) | MEDIUM (loader rework) | ~85-95% |
| A2 CLIP QD (QD4/32) | HIGH | HIGH | LOW | LOW | MEDIUM | ~85-95% |
| B empty_cache bypass | MEDIUM | MEDIUM | MEDIUM (allocator/VAE) | MEDIUM | LOW (policy exists) | ~70-80% |
| C restore-time CLIP | HIGH | HIGH | MEDIUM (spec reconcile) | MEDIUM (startup contention) | MEDIUM (lane exists) | ~80-90% |
| D FP32 cast-once | HIGH | LOW-MED (small absolute) | MEDIUM (patch invalidation) | LOW | MEDIUM (narrow Comfy change) | ~60-70% on the mechanism; LOW value vs goal |
| E Gantt | HIGH (done) | n/a | none | none | DONE | 100% (deployed) |

Odds drivers: A is high because the read path is byte-identical (sample
hash parity proven across all QD configs) and the storage parallelism is
measured, not extrapolated.  B is medium because the allocator release may
be load-bearing for VAE.  C is high because the ownership/reconcile
machinery exists and E26 proved the take path.  D is medium-low value
because the encode is not critical-path (D7 §11) even though the mechanism
is sound.

---

## 14. Answers to every mandatory question

### QD / loader
* Best UNET: QD4-8 / 32 MiB (43-50 GB/s vs current 20.8 GB/s); QD4 for
  low CPU, QD8 for max.
* Best CLIP: QD4 / 32 MiB (42.0 GB/s, 30 ms CPU) vs current 16.2 GB/s.
* Current vs best cold throughput: UNET 20.78 → 49.61 GB/s; CLIP 16.22 →
  45.00 GB/s (MEASURED).
* Cold classification trust: HIGH (fresh container, minflt=0, warm-control
  separated, QD≫warm-QD1 proves concurrency not cache).
* Bottleneck after concurrency: CPU issue rate (330/1690 ms at QD8/16),
  tail spread at QD8 (133 ms).
* Production architecture: chunked preadv→pinned→async H2D QD4-8/32 (or
  fastsafe with 32 MiB block + threads 4-8).

### empty_cache
* Who: Comfy `free_memory` → `soft_empty_cache` (defensive branch), on the
  VAE `load_models_gpu` path.
* Why: allocator-free > 25% threshold in `free_memory` (D18 source audit).
* How long: 740-950 ms total; `empty_cache` itself 739-950 ms (99.9%).
* Sync vs cache: sync is 0.03-0.04 ms; the wall is TRUE allocator work
  (reserved −2.1 GB).
* Reclaims: ~2.1 GB reserved; 0 models unloaded; 80 GB free before.
* Necessary? NOT PROVEN either way; high-headroom + 0 unloads make a
  proven-ready bypass plausible.
* Guards: §6.6 list; existing `empty_cache_bypass.evaluate_bypass`.
* Removable wall: ~0.74-0.95 s.

### earliest CLIP
* First executable post-restore point: restore method first line.
* Source identity known: at snap=True (frozen manifest).
* File I/O legal: immediately at resume (path from manifest, no request).
* Direct-GPU legal: after CUDA ready (early restore).
* Earliest code location: restore-time worker under
  `fast_cold_orchestration` (lane exists) or `modal_app.restore`.
* Overlaps: restore reconcile + method setup (~1.5 s window).
* Reconcile: manifest-digest key; take on match; close+fallback on
  mismatch (E26 machinery).
* Exposed CLIP load with best loader: ~0-250 ms (vs 1.35-2.43 s today).

### FP32 cast-once
* Real Qwen path casts per forward: YES (D7 source-verified, generic;
  real-Qwen counter deployed for the valid run).
* Bytes/ops: 99-195 ops / 126-417 MB per forward (D7 MEASURED generic).
* Wall: cast CPU wall ≈ forward wall (8-28 ms generic).
* VRAM: +8.04 GB (replace) or +16.1 GB (duplicate).
* Transforms beyond dtype: none in the cast itself; patches via
  `patch_weight_to_device` invalidate.
* Cleanest ownership: A (replace resident storage).
* Hidden at restore-time: YES (window ~2.2 s vs 191 ms read + cast).
* Saving: est. 20-70 ms encode (ENGINEERING ESTIMATE; small vs goal).

### Gantt
* One monotonic axis: YES (all remote spans share `time.monotonic_ns()`).
* Concurrent ops render concurrently: YES (per-lane independent rows).
* Numeric columns trustworthy: YES (derived from the same mono ns,
  unit-verified).
* `█` in real Modal logs: pending valid run (deployed; local UTF-8 verified).
* Logging overhead: one ~15 KB block at completion.
* Trace agrees with raw timestamps: YES (unit-verified).

### Combined architecture
* Order: (1) CLIP restore-time + QD4 (biggest, interacts with UNET);
  (2) UNET QD4-8 (after CLIP source ownership resolved); (3) empty_cache
  bypass (independent, post-sampling); (4) FP32 cast-once (small, last).
* Must validate together: CLIP restore-time × UNET QD (source ownership +
  CPU contention); FP32 residency × empty_cache threshold; QD × allocator
  profile.
* Fail-closed: manifest-verify before spec take; release-once on lane
  failure; proven-ready gates for the empty_cache bypass; byte-parity
  gates for the loader.
* Measured total opportunity: ~1.9-3.1 s (interaction-adjusted estimate;
  components measured individually).
* Realistic combined target: **~2.0-3.0 s off the cold first request**
  (ENGINEERING ESTIMATE).

---

## 15. Files changed for telemetry only

| File | Change | Gate |
|---|---|---|
| `comfymodal_runtime/gantt_telemetry.py` | NEW — Gantt span collector + `█` renderer | `COMFYMODAL_V2_GANTT_TELEMETRY` |
| `comfymodal_runtime/e27_forensics.py` | NEW — memory snapshots, soft-empty-cache decomposition, cast counter | `COMFYMODAL_V2_E27_FORENSICS` |
| `comfymodal_runtime/modal_app.py` | Gantt emit + report at completion; E27 env passthrough; probe allowlist; `run_clip_qd_probe` method; restore-origin metadata; cast summary | gated |
| `comfymodal_runtime/model_preload.py` | E27 soft-cache chain + cast-counter install in `_ensure_core_wrappers` | `COMFYMODAL_V2_E27_FORENSICS` |
| `comfymodal_runtime/runtime_executor.py` | `e27_memory_sampling_end` boundary | gated |
| `comfymodal_runtime/clip_fast_hydration_wiring.py` | `clip_source_read` span + `e27_memory_clip_hydration_done` | gated |
| `comfymodal_runtime/unet_fastsafetensors.py` | `unet_source_read` span | gated |
| `tests/test_e27_gantt_telemetry.py` | NEW — 9 tests | n/a |
| `tests/test_e27_forensics.py` | NEW — 4 tests | n/a |

No production optimization was implemented.  No production default was
changed (all new gates default OFF; the E19/E26 production defaults are
untouched).  The `run_clip_qd_probe` Modal method is measurement-only.

### 15.2 Snapshot-vehicle blocker — root-cause diagnosis

The generation-run evidence (Gantt in real logs, on-run memory boundaries,
on-run empty_cache decomposition, real-Qwen cast counters) requires a
VALID restore-only run, which requires a retained CLIP/VAE CPU snapshot.
Every probe reported `snapshot_identity=""`, `cpu_snapshot_models_present=0`,
`clip_present=0`, `vae_present=0`, `eviction_retained_role="none"`.

Findings that narrow the cause (all MEASURED this batch):

1. The deployed container env is correct: `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`,
   `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1`, `COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae`,
   `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1` (deploy env), `ATOMIC_PROFILE=E19_FINAL_COLD_LOADER`
   (probe-verified).
2. `COMFYMODAL_V2_CLIP_COLD_FORENSICS` reads 0 in the container even when
   the deploy env carries 1 (verified 4 ways: `_runtime_env` passthrough
   test showed RUNTIME_ENV_FORENSICS=1; container probe shows 0).  The E19
   bat selector forces it to 0; the direct-deploy path ALSO produced 0 —
   indicating the class-level Modal env is not being refreshed on redeploy
   of an existing app (first-deploy env wins).  This is a documented
   platform quirk; E27 avoids it by gating its own telemetry on
   `E27_FORENSICS` (which DID refresh because the key is new).
3. `startup()` (the `enter(snap=True)` hook that builds the CPU snapshot)
   requires a container to BOOT through startup with construction env.
   All our function calls used `restore` (snap=False) or static methods,
   so no construction container boot was observed.  Modal's deploy-time
   `enter` behavior did not produce a retained snapshot in this
   environment.
4. Placement reports cpu_request=12/memory 32768 at runtime even though
   the deployed spec is 16/49152 — evidence the live class registration
   (and its env/spec) predates the latest deploy.

**Recovery path (for the implementation batch):** perform a clean deploy of
a FRESH app name (or fully delete + redeploy `stable-modal-comfy-v2-restore-only-shadow`)
via the canonical `deploy_and_run_v2_single.bat` so the first container
boot carries construction env through `startup()`, then verify
`run_snapshot_restore_only_probe` reports `cpu_snapshot_models_present=1`
BEFORE any generation run.  The E26 report's cycle-2 runs (valid) were on
exactly this vehicle — the mechanism worked for E26; the difference is
the fresh-app lifecycle, which my in-place redeploys did not replicate.

## 16. Exact commands executed

```text
git rev-parse HEAD / git branch --show-current / git status --short   (start record)
python tools\benchmark_v2_direct.py --verify-d6-profile               (preflight gate)
deploy_and_run_v2_single.bat E27_FINAL  (bat deploy; bat identifier check fails on
                                          Windows console stdout quirk AFTER successful deploy)
modal deploy -m comfymodal_runtime.modal_app --name stable-modal-comfy-v2-restore-only-shadow
  with: COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow
        COMFYMODAL_V2_GANTT_TELEMETRY=1 COMFYMODAL_V2_E27_FORENSICS=1
        COMFYMODAL_V2_CLIP_COLD_FORENSICS=1 COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=1
        COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0 COMFYMODAL_V2_ENV_PROFILE=inherit
        COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1 COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1
        COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0
        COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1 COMFYMODAL_V2_ATOMIC_PROFILE=E19_FINAL_COLD_LOADER
        COMFYMODAL_V2_ENABLE_MEMORY_SNAPSHOT=1
  (direct deploys 2-5; deploy5 = the live one, "App deployed in 97.942s")
python tools\record_deployment_identity.py                              (identity record)
python tools\benchmark_v2_direct.py --prime-registry-proof              (D1 proof prime)
python tools\benchmark_v2_direct.py --verify-run-preflight              (run gate, PASS)
run_v2_single.bat (V2_BENCHMARK_MODE=snapshot_restore_only, run count 1; preflight PASS,
  then harness attempts invalid probes on empty-snapshot container)
python <temp>\e27_qd_probe.py       run_unet_qd_probe(z_image_turbo_bf16.safetensors, evidence)
python <temp>\e27_clip_qd_probe.py  run_clip_qd_probe(qwen_3_4b.safetensors, evidence)
python <temp>\e27_snapshot_probe.py run_snapshot_restore_only_probe   (snapshot state)
python <temp>\e27_env_probe2.py     run_env_probe                     (container env)
```

## 17. Run/deploy index

| ID | Type | When | App/deploy | Command | Request/container | Result |
|---|---|---|---|---|---|---|
| E27-DPL1 | deploy | 19:09Z | bat attempt 1 | bat | (deployed 14:13-05:00 record) | app deployed; bat id-check false-fail |
| E27-DPL2-4 | deploy | 19:13-19:37Z | direct modal deploy | modal deploy | — | no new deployment (env/console quirk) |
| E27-DPL5 | deploy | 19:50Z | **live** | direct modal deploy + full env | hash 34404d77... | **App deployed 97.942s** |
| E27-DPL6 | deploy | 19:53Z | bat attempt 2 | bat | — | id-check false-fail after deploy |
| E27-PR1 | probe | 19:52Z | live app | run_snapshot_restore_only_probe | ta-01M0B6WS... | snapshot EMPTY (blocker) |
| E27-PR2 | probe | 19:59Z | live app | run_snapshot_restore_only_probe | ta-01M0B78C... GCP/us-east1 | snapshot EMPTY |
| E27-PR3 | probe | 20:01Z | live app | run_env_probe | — | env gates confirmed (E27=1, GANTT=1) |
| E27-PR4 | probe | 20:01Z | live app | run_unet_qd_probe structural | — | UNET file verified |
| E27-PR5 | probe | 20:02Z | live app | run_unet_qd_probe evidence | — | **UNET QD matrix** |
| E27-PR6 | probe | 20:03Z | live app | run_clip_qd_probe structural | — | CLIP file verified |
| E27-PR7 | probe | 20:05Z | live app | run_clip_qd_probe evidence | — | **CLIP QD matrix** |
| E27-R1..R7 | run | 19:46-19:59Z | live app | snapshot-restore-only harness | 7 attempts | all INVALID (snapshot empty) |

Paid/deployed-accounting: deploys 4 (2 bat + 2 effective direct; deploy5
live), probe requests ~10 (env/identity/QD/snapshot), generation runs 0
valid.  All QD probes are measurement-only (no generation).

## 18. COMPLETE RAW LOGS

### RAW LOG — E27-PR3 — container env probe (run_env_probe)

```json
{"status": "ok", "env": {"COMFYMODAL_V2_ATOMIC_PROFILE": "E19_FINAL_COLD_LOADER",
 "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0", "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
 "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1", "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1",
 "COMFYMODAL_V2_E27_FORENSICS": "1", "COMFYMODAL_V2_ENV_PROFILE": "inherit",
 "COMFYMODAL_V2_GANTT_TELEMETRY": "1", "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "1",
 "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0", "COMFYMODAL_V2_UNET_FORENSICS": "0",
 "COMFYMODAL_V2_VAE_SNAPSHOT": "1", ...}}
```

(Full 72-key payload in the probe's captured log; key gates shown.)

### RAW LOG — E27-PR1/PR2 — snapshot state probe (run_snapshot_restore_only_probe)

```json
{"status": "ok", "snapshot_identity": "",
 "invariant": {"unet_present": 0, "cpu_snapshot_models_present": 0, "container_retained": 0,
  "clip_present": 0, "vae_present": 0, "snapshot_exclude_unet_gate": 1,
  "eviction_retained_role": "none"},
 "restore_timing": {"restore_total_ms": 1756.378, "restore_count": 1, ...}}
```

### RAW LOG — E27-PR5 — UNET QD evidence battery (run_unet_qd_probe evidence)

Stored in full at `_e27_unet_qd_evidence.json` (repo, this batch).  Key
summary verbatim:

```json
{"status": "ok", "total_data_bytes": 12309817472,
 "baseline_mmap_gbps": 17.4479, "baseline_seq_preadv_gbps": 6.597,
 "baseline_mmap_wall_ms": 705.5182, "baseline_seq_preadv_wall_ms": 1865.9818,
 "fullfile_qd1_gbps": 6.597, "fullfile_warm_qd1_gbps": 11.3765,
 "fullfile_best_qd2_gbps": 23.0433, "fullfile_best_qd4_gbps": 43.4521,
 "fullfile_best_qd8_gbps": 49.6111, "fullfile_qd16_gbps": 22.8553,
 "qd_ratios": {"qd2_over_qd1": 3.493, "qd4_over_qd1": 6.5866,
  "qd8_over_qd1": 7.5203, "qd16_over_qd1": 3.4645, "warm_qd1_over_cold_qd1": 1.7245},
 "best_fullfile_gbps": 49.6111,
 "external": [{"loader": "fastsafetensors", "concurrency": 8, "device": "cpu",
   "aggregate_gbps": 6.6643, "sample_hash_matches_baseline": true},
  {"loader": "fastsafetensors", "concurrency": 16, "device": "cpu",
   "aggregate_gbps": 10.1345, "sample_hash_matches_baseline": true},
  {"loader": "fastsafetensors", "concurrency": 16, "device": "cuda:0",
   "aggregate_gbps": 20.7824, "sample_hash_matches_baseline": true}],
 "gpu_transfer_status": "ok"}
```

### RAW LOG — E27-PR7 — CLIP QD evidence battery (run_clip_qd_probe evidence)

Stored in full at `_e27_clip_qd_evidence.json` (repo, this batch).  Key
summary verbatim:

```json
{"status": "ok", "total_data_bytes": 8044936192,
 "baseline_mmap_gbps": 1.0915, "baseline_seq_preadv_gbps": 7.6814,
 "baseline_mmap_wall_ms": 7370.8277, "baseline_seq_preadv_wall_ms": 1047.3224,
 "fullfile_qd1_gbps": 7.6814, "fullfile_warm_qd1_gbps": 10.6706,
 "fullfile_best_qd2_gbps": 19.9614, "fullfile_best_qd4_gbps": 42.0266,
 "fullfile_best_qd8_gbps": 44.9978, "fullfile_qd16_gbps": 20.1596,
 "qd_ratios": {"qd2_over_qd1": 2.5987, "qd4_over_qd1": 5.4712,
  "qd8_over_qd1": 5.858, "qd16_over_qd1": 2.6245, "warm_qd1_over_cold_qd1": 1.3891},
 "best_fullfile_gbps": 44.9978,
 "external": [{"loader": "fastsafetensors", "concurrency": 8, "device": "cpu",
   "aggregate_gbps": 5.7639, "sample_hash_matches_baseline": true},
  {"loader": "fastsafetensors", "concurrency": 16, "device": "cpu",
   "aggregate_gbps": 7.3271, "sample_hash_matches_baseline": true},
  {"loader": "fastsafetensors", "concurrency": 16, "device": "cuda:0",
   "aggregate_gbps": 16.2228, "sample_hash_matches_baseline": true}],
 "gpu_transfer_status": "ok"}
```

(Full per-config raw logs — worker block timings, per-block GB/s, rusage,
warm-repeat, verify hashes — are in the two `_e27_*.json` artifacts; the
report embeds the summaries above and the artifacts are the complete raw
record for independent reconstruction.)

### RAW LOG — E27 deploy5 (modal deploy output tail)

```text
✓ App deployed in 97.942s! 🎉
View Deployment: https://modal.com/apps/testing3/main/deployed/stable-modal-comfy-v2-restore-only-shadow
```

### COMPLETE RAW — `_e27_unet_qd_evidence.json` (embedded in full)

<details>
<summary>Complete UNET QD evidence artifact (172,176 bytes) — click to expand</summary>


```json
{
 "probe": "unet_qd",
 "model_path": "/root/comfy/ComfyUI/models/diffusion_models/z_image_turbo_bf16.safetensors",
 "mode": "evidence",
 "status": "ok",
 "sections": {
  "env": {
   "status": "ok",
   "os": "posix",
   "platform": "linux",
   "python": "3.11.5",
   "cpu_cores": 28,
   "preadv_available": true,
   "cuda_available": true,
   "cuda_device_name": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
   "torch_version": "2.13.0+cu130"
  },
  "file": {
   "status": "ok",
   "path": "/root/comfy/ComfyUI/models/diffusion_models/z_image_turbo_bf16.safetensors",
   "size_bytes": 12309866400,
   "header_bytes": 48920,
   "data_start_offset": 48928,
   "tensor_count": 453,
   "total_data_bytes": 12309817472,
   "statvfs": {
    "f_bsize": 4096,
    "f_frsize": 4096,
    "f_blocks": 100000000,
    "f_bfree": 100000000,
    "f_bavail": 100000000
   },
   "mount": "none on / type overlay"
  },
  "loader_imports": {
   "runai_model_streamer": {
    "importable": false,
    "error": "ModuleNotFoundError: No module named 'runai_model_streamer'"
   },
   "fastsafetensors": {
    "importable": true,
    "version": "0.3.3"
   },
   "safetensors_version": "0.5.3",
   "safe_open_backend_param": false
  },
  "loader_smoke": {
   "synthetic_file": "/tmp/c9qd_smoke.safetensors",
   "loaders": {
    "runai": {
     "status": "error",
     "error": "ModuleNotFoundError: No module named 'runai_model_streamer'"
    },
    "fastsafetensors": {
     "status": "ok",
     "keys": [
      "a",
      "b",
      "c"
     ],
     "wall_ms": 10.33
    }
   }
  },
  "loader_ownership": {
   "status": "ok",
   "reason": "",
   "identity": [
    {
     "key": "a",
     "data_ptr": 47588954865664,
     "storage_data_ptr": 47588954865664,
     "storage_size": 1048576,
     "storage_offset": 0,
     "shape": [
      262144
     ],
     "stride": [
      1
     ],
     "contiguous": true,
     "base": "None"
    },
    {
     "key": "b",
     "data_ptr": 47588955914240,
     "storage_data_ptr": 47588955914240,
     "storage_size": 1048576,
     "storage_offset": 0,
     "shape": [
      262144
     ],
     "stride": [
      1
     ],
     "contiguous": true,
     "base": "None"
    },
    {
     "key": "c",
     "data_ptr": 47588956962816,
     "storage_data_ptr": 47588956962816,
     "storage_size": 8,
     "storage_offset": 0,
     "shape": [
      4
     ],
     "stride": [
      1
     ],
     "contiguous": true,
     "base": "None"
    }
   ],
   "distinct_data_ptrs": [
    47588954865664,
    47588955914240,
    47588956962816
   ],
   "tensors_share_allocation": false,
   "retained_lifetime": {
    "status": "ok",
    "hash_before": "f908964ddcfb10e3",
    "hash_after": "f908964ddcfb10e3"
   },
   "closed_lifetime": {
    "status": "recorded",
    "read_after_close": "error:KeyError:0"
   }
  },
  "baseline_mmap": {
   "kind": "baseline_mmap",
   "status": "ok",
   "tensor_count": 453,
   "total_bytes": 12309817472,
   "total_wall_ms": 705.5182,
   "aggregate_gbps": 17.4479,
   "minflt_delta": 0,
   "majflt_delta": 0,
   "ctxt_switches_delta": null,
   "rss_delta_bytes": 12310044672,
   "peak_rss_bytes": 15728320512,
   "process_cpu_ms": 8.1,
   "sample_hash": "0740edff0575056a1bd07ad4b98cb3c06a8b731a9d6c4d2199c94c02e6bff52f"
  },
  "baseline_seq_preadv": {
   "kind": "raw_qd",
   "qd": 1,
   "worker_count": 1,
   "block_mib": 32,
   "syscall_bytes": 33554432,
   "schedule": "static",
   "window_start": 0,
   "window_len": 12309817472,
   "status": "ok",
   "bytes_returned": 12309817472,
   "expected_bytes": 12309817472,
   "total_wall_ms": 1865.9818,
   "aggregate_gbps": 6.597,
   "steady_state_gbps": 6.8382,
   "per_worker": [
    {
     "worker": 0,
     "segment_start": 0,
     "segment_end": 12309817472,
     "bytes_returned": 12309817472,
     "wall_ms": 1859.4774,
     "gbps": 6.62,
     "block_count": 367,
     "first_block_wall_ms": 2.9639,
     "block_timings_ms": [
      2.9639,
      7.5894,
      5.8867,
      3.5327,
      6.9363,
      3.7764,
      7.8689,
      4.894,
      2.9925,
      6.4506,
      3.9179,
      3.8397,
      8.5581,
      5.7222,
      6.5197,
      4.0613,
      3.9242,
      13.3997,
      6.8302,
      5.949,
      4.9616,
      3.6443,
      3.4111,
      8.8764,
      4.9234,
      6.0889,
      4.1823,
      3.7786,
      7.6632,
      5.5468,
      5.6709,
      4.3539,
      3.2975,
      5.3126,
      6.2074,
      3.9923,
      7.0683,
      6.4455,
      5.8006,
      4.5405,
      4.4645,
      6.6331,
      3.8614,
      5.785,
      2.6431,
      5.1489,
      2.5952,
      7.8339,
      5.8419,
      5.4235,
      4.5885,
      3.3758,
      6.5092,
      3.4413,
      2.7607,
      8.2598,
      4.4513,
      3.7968,
      7.0085,
      4.0165,
      8.079,
      5.8006,
      5.1243,
      4.5893,
      3.6586,
      3.3016,
      8.7293,
      3.9261,
      5.6134,
      2.7846,
      2.5726,
      7.3033,
      5.0912,
      5.0964,
      3.1759,
      2.6564,
      2.6142,
      9.5787,
      4.5378,
      6.0216,
      4.21,
      2.9814,
      7.2369,
      5.0609,
      5.2219,
      5.1571,
      3.4235,
      5.9078,
      6.7042,
      3.31,
      6.6017,
      5.8331,
      2.9831,
      5.014,
      2.9329,
      7.0821,
      4.3565,
      3.4865,
      9.0396,
      4.485,
      2.958,
      6.2343,
      4.1009,
      7.5432,
      5.6688,
      5.3532,
      3.6625,
      3.105,
      3.8734,
      8.4874,
      4.2136,
      2.8889,
      7.2084,
      3.7855,
      8.0135,
      5.9611,
      6.0394,
      4.005,
      2.9898,
      2.9699,
      8.4655,
      4.2127,
      6.9971,
      3.9028,
      3.0216,
      6.9852,
      5.0895,
      4.8733,
      4.5409,
      3.5928,
      5.5418,
      6.9034,
      5.8303,
      2.9022,
      4.3262,
      4.7583,
      6.1655,
      2.828,
      6.2567,
      3.2755,
      2.8177,
      9.325,
      6.0079,
      4.4117,
      6.9864,
      4.037,
      7.5476,
      4.9541,
      3.0885,
      5.4561,
      2.7595,
      2.7537,
      8.7223,
      5.1616,
      3.6777,
      6.5694,
      3.9023,
      7.5667,
      5.0856,
      5.0934,
      3.372,
      2.8076,
      2.8186,
      8.1637,
      4.0441,
      5.6672,
      3.2367,
      2.7216,
      7.0192,
      6.5044,
      5.9376,
      4.756,
      2.9779,
      2.704,
      8.2199,
      5.3428,
      6.5304,
      3.8812,
      3.0693,
      8.2328,
      6.2443,
      5.1731,
      3.4877,
      3.0283,
      5.3309,
      6.176,
      2.8262,
      6.8677,
      5.2479,
      2.9807,
      4.9069,
      2.7867,
      7.2968,
      3.3565,
      2.746,
      7.9586,
      4.1166,
      2.8123,
      6.089,
      2.73,
      7.0258,
      6.4903,
      5.44,
      4.1777,
      3.302,
      3.0379,
      8.362,
      5.0577,
      3.1928,
      6.5152,
      2.7907,
      8.0129,
      5.7678,
      5.0437,
      4.8385,
      3.4059,
      3.1998,
      8.6392,
      4.358,
      5.6722,
      3.3919,
      2.9047,
      7.3915,
      5.4653,
      5.5148,
      3.7468,
      2.7506,
      4.4605,
      7.3533,
      5.4908,
      2.4579,
      6.2192,
      4.7745,
      7.5055,
      2.8145,
      7.1216,
      3.4045,
      3.6694,
      6.4861,
      6.4601,
      3.0977,
      6.4805,
      5.7828,
      3.4604,
      4.6346,
      2.8749,
      7.088,
      3.334,
      2.795,
      7.885,
      4.1123,
      2.8574,
      6.1196,
      2.7784,
      7.0351,
      4.9278,
      4.9732,
      3.3044,
      2.8374,
      2.8713,
      7.9425,
      4.0734,
      6.0471,
      3.1843,
      2.7691,
      6.948,
      4.9383,
      4.9741,
      3.1348,
      2.6801,
      2.8035,
      7.8943,
      4.0442,
      5.7307,
      3.02,
      2.7242,
      6.8891,
      4.81,
      5.2342,
      3.4747,
      2.7455,
      6.1602,
      7.0249,
      3.9834,
      7.3402,
      6.1474,
      5.274,
      5.0947,
      3.0681,
      6.3416,
      2.9298,
      6.5092,
      3.1569,
      6.0757,
      3.1414,
      7.0962,
      5.114,
      4.8269,
      4.0878,
      3.0842,
      6.6625,
      3.8011,
      3.1423,
      7.8785,
      5.3868,
      3.3889,
      6.6605,
      3.0135,
      7.3568,
      5.1554,
      5.8577,
      4.6834,
      3.6555,
      3.3299,
      8.0518,
      4.493,
      5.9468,
      3.8387,
      3.4422,
      8.162,
      5.9625,
      5.2639,
      4.2853,
      3.3719,
      3.1108,
      8.5638,
      4.6612,
      6.955,
      3.7089,
      3.109,
      7.4637,
      5.126,
      5.0309,
      3.0965,
      2.5672,
      5.4087,
      6.4397,
      2.6757,
      6.5082,
      5.8649,
      3.087,
      4.755,
      2.81,
      9.2409,
      4.3791,
      3.2881,
      12.0677,
      6.6452,
      3.8204,
      8.7297,
      3.9365,
      8.6452,
      6.5517,
      5.4084,
      3.8352,
      3.0683,
      2.8671,
      8.9873,
      4.6755,
      2.9412,
      6.5742,
      2.88,
      7.3368,
      5.7191,
      5.2992,
      4.4679,
      3.1751
     ],
     "block_gbps": [
      11.3209,
      4.4212,
      5.7001,
      9.4983,
      4.8375,
      8.8853,
      4.2642,
      6.8562,
      11.213,
      5.2017,
      8.5643,
      8.7388,
      3.9208,
      5.8639,
      5.1466,
      8.2619,
      8.5506,
      2.5041,
      4.9126,
      5.6403,
      6.7629,
      9.2073,
      9.8369,
      3.7802,
      6.8152,
      5.5107,
      8.0229,
      8.88,
      4.3786,
      6.0493,
      5.917,
      7.7068,
      10.1756,
      6.316,
      5.4055,
      8.4047,
      4.7471,
      5.2058,
      5.7847,
      7.39,
      7.5158,
      5.0587,
      8.6898,
      5.8002,
      12.6949,
      6.5168,
      12.9296,
      4.2832,
      5.7437,
      6.1868,
      7.3126,
      9.9396,
      5.1549,
      9.7505,
      12.1545,
      4.0624,
      7.5381,
      8.8377,
      4.7877,
      8.3542,
      4.1533,
      5.7846,
      6.5482,
      7.3115,
      9.1713,
      10.1632,
      3.8439,
      8.5465,
      5.9776,
      12.0501,
      13.0429,
      4.5944,
      6.5907,
      6.584,
      10.5654,
      12.6317,
      12.8353,
      3.503,
      7.3944,
      5.5723,
      7.9702,
      11.2547,
      4.6366,
      6.6301,
      6.4257,
      6.5064,
      9.8013,
      5.6797,
      5.005,
      10.1374,
      5.0827,
      5.7524,
      11.248,
      6.6921,
      11.4409,
      4.7379,
      7.7021,
      9.624,
      3.7119,
      7.4816,
      11.3435,
      5.3822,
      8.1822,
      4.4483,
      5.9191,
      6.2682,
      9.1617,
      10.8064,
      8.6628,
      3.9534,
      7.9633,
      11.6151,
      4.6549,
      8.8638,
      4.1873,
      5.6289,
      5.5559,
      8.3782,
      11.2231,
      11.2981,
      3.9637,
      7.9651,
      4.7955,
      8.5976,
      11.1048,
      4.8037,
      6.5928,
      6.8854,
      7.3894,
      9.3394,
      6.0548,
      4.8606,
      5.7552,
      11.5616,
      7.7562,
      7.0517,
      5.4422,
      11.8651,
      5.363,
      10.244,
      11.9084,
      3.5983,
      5.5851,
      7.6057,
      4.8028,
      8.3118,
      4.4457,
      6.773,
      10.8644,
      6.1499,
      12.1596,
      12.1853,
      3.847,
      6.5008,
      9.1238,
      5.1077,
      8.5987,
      4.4345,
      6.598,
      6.5879,
      9.951,
      11.9512,
      11.9046,
      4.1102,
      8.2971,
      5.9208,
      10.3668,
      12.3289,
      4.7803,
      5.1587,
      5.6512,
      7.0552,
      11.2678,
      12.4094,
      4.0821,
      6.2803,
      5.1382,
      8.6454,
      10.9324,
      4.0757,
      5.3736,
      6.4864,
      9.6208,
      11.0803,
      6.2943,
      5.433,
      11.8725,
      4.8859,
      6.3939,
      11.2572,
      6.8382,
      12.0411,
      4.5985,
      9.9968,
      12.2194,
      4.2161,
      8.151,
      11.9311,
      5.5107,
      12.291,
      4.7759,
      5.1699,
      6.1681,
      8.0319,
      10.1618,
      11.0451,
      4.0127,
      6.6343,
      10.5093,
      5.1502,
      12.0237,
      4.1876,
      5.8176,
      6.6527,
      6.9349,
      9.8518,
      10.4865,
      3.884,
      7.6994,
      5.9156,
      9.8926,
      11.5517,
      4.5396,
      6.1396,
      6.0844,
      8.9556,
      12.1989,
      7.5225,
      4.5632,
      6.111,
      13.6516,
      5.3953,
      7.0279,
      4.4706,
      11.9219,
      4.7117,
      9.856,
      9.1445,
      5.1733,
      5.1941,
      10.832,
      5.1777,
      5.8024,
      9.6966,
      7.24,
      11.6717,
      4.734,
      10.0642,
      12.005,
      4.2555,
      8.1596,
      11.7431,
      5.4831,
      12.077,
      4.7695,
      6.8092,
      6.747,
      10.1544,
      11.8257,
      11.686,
      4.2247,
      8.2374,
      5.5488,
      10.5376,
      12.1176,
      4.8294,
      6.7947,
      6.7458,
      10.7038,
      12.5199,
      11.9686,
      4.2505,
      8.297,
      5.8552,
      11.1108,
      12.3171,
      4.8707,
      6.976,
      6.4107,
      9.6568,
      12.2216,
      5.447,
      4.7765,
      8.4237,
      4.5713,
      5.4583,
      6.3622,
      6.5861,
      10.9365,
      5.2912,
      11.4529,
      5.1549,
      10.629,
      5.5227,
      10.6814,
      4.7285,
      6.5612,
      6.9516,
      8.2085,
      10.8794,
      5.0363,
      8.8276,
      10.6783,
      4.259,
      6.229,
      9.9014,
      5.0378,
      11.1347,
      4.561,
      6.5086,
      5.7283,
      7.1646,
      9.1791,
      10.0768,
      4.1673,
      7.4682,
      5.6424,
      8.741,
      9.7479,
      4.1111,
      5.6276,
      6.3744,
      7.8301,
      9.9513,
      10.7864,
      3.9182,
      7.1986,
      4.8245,
      9.0471,
      10.7927,
      4.4957,
      6.5459,
      6.6697,
      10.8363,
      13.0706,
      6.2037,
      5.2105,
      12.5405,
      5.1557,
      5.7213,
      10.8698,
      7.0566,
      11.941,
      3.6311,
      7.6625,
      10.2049,
      2.7805,
      5.0494,
      8.783,
      3.8437,
      8.524,
      3.8813,
      5.1214,
      6.2041,
      8.749,
      10.9359,
      11.7031,
      3.7335,
      7.1766,
      11.4084,
      5.104,
      11.651,
      4.5734,
      5.8671,
      6.332,
      7.5101,
      9.1005
     ]
    }
   ],
   "first_range_latency_ms": 2.9639,
   "tail_spread_ms": 0.0,
   "process_cpu_ms": 250.0,
   "thread_cpu_ms": -1130.0,
   "minflt_delta": 0,
   "majflt_delta": 0,
   "ctxt_switches_delta": null,
   "rss_delta_bytes": 35373056,
   "peak_rss_bytes": 15728390144,
   "peak_pinned_bytes": 0,
   "cpu_cores": 28,
   "cpu_utilization_pct": 13.4,
   "gbps_per_cpu_core": 49.2395,
   "warm_repeat": {
    "bytes": 268435456,
    "wall_ms": 28.4059,
    "gbps": 9.45
   },
   "verify": {
    "regions": [
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 12309555328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536608768,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536870912,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073479680,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073741824,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610350592,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610612736,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147221504,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147483648,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684092416,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684354560,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3220963328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3221225472,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3757834240,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3758096384,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294705152,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294967296,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831576064,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831838208,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368446976,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368709120,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905317888,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905580032,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442188800,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442450944,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979059712,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979321856,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 7515930624,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 7516192768,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8052801536,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8053063680,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8589672448,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8589934592,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9126543360,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9126805504,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9663414272,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9663676416,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10200285184,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10200547328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10737156096,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10737418240,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 11274027008,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 11274289152,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 11810897920,
      "bytes": 262144,
      "hash_match": true
     }
    ],
    "all_match": true
   }
  },
  "screen": [
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 197.0729,
    "aggregate_gbps": 10.8969,
    "steady_state_gbps": 11.335,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 2147483648,
      "bytes_returned": 2147483648,
      "wall_ms": 196.2764,
      "gbps": 10.9411,
      "block_count": 64,
      "first_block_wall_ms": 4.2833,
      "block_timings_ms": [
       4.2833,
       3.6598,
       2.8794,
       2.9085,
       2.7824,
       2.6698,
       2.6923,
       2.2467,
       2.6887,
       3.0858,
       3.2249,
       3.0467,
       2.6825,
       2.4205,
       2.5332,
       2.7365,
       2.959,
       2.6079,
       2.4128,
       2.6828,
       3.6325,
       3.4318,
       3.1785,
       3.3648,
       3.4022,
       3.182,
       3.3776,
       3.3037,
       2.6443,
       2.6195,
       3.3927,
       3.3108,
       3.1472,
       3.0945,
       3.0185,
       2.8425,
       2.8784,
       3.0593,
       2.9841,
       2.6347,
       2.597,
       2.7023,
       2.7035,
       2.9603,
       2.7982,
       2.7707,
       2.7943,
       2.6251,
       2.8811,
       2.8951,
       2.7376,
       4.0821,
       3.4837,
       3.2662,
       3.1148,
       3.4494,
       3.8394,
       3.5955,
       3.8258,
       3.5474,
       3.331,
       3.2201,
       2.9525,
       2.8444
      ],
      "block_gbps": [
       7.8337,
       9.1684,
       11.6534,
       11.5367,
       12.0594,
       12.5683,
       12.4629,
       14.9351,
       12.4797,
       10.8736,
       10.4048,
       11.0134,
       12.5086,
       13.8625,
       13.2458,
       12.2617,
       11.3399,
       12.8664,
       13.9067,
       12.5073,
       9.2372,
       9.7775,
       10.5566,
       9.9722,
       9.8625,
       10.5452,
       9.9345,
       10.1567,
       12.6892,
       12.8095,
       9.8902,
       10.1347,
       10.6618,
       10.8431,
       11.1162,
       11.8044,
       11.6575,
       10.9679,
       11.2444,
       12.7358,
       12.9205,
       12.4169,
       12.4115,
       11.335,
       11.9913,
       12.1103,
       12.0083,
       12.7821,
       11.6464,
       11.5902,
       12.2568,
       8.2198,
       9.6319,
       10.2733,
       10.7727,
       9.7277,
       8.7395,
       9.3324,
       8.7706,
       9.459,
       10.0733,
       10.4202,
       11.3648,
       11.7965
      ]
     }
    ],
    "first_range_latency_ms": 4.2833,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 30.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 16138620928,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 15.22,
    "gbps_per_cpu_core": 71.5828,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 22.0757,
     "gbps": 12.1598
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 0
   },
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 2147483648,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 207.5395,
    "aggregate_gbps": 10.3473,
    "steady_state_gbps": 10.5343,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 2147483648,
      "segment_end": 4294967296,
      "bytes_returned": 2147483648,
      "wall_ms": 199.4804,
      "gbps": 10.7654,
      "block_count": 32,
      "first_block_wall_ms": 5.2662,
      "block_timings_ms": [
       5.2662,
       4.6183,
       5.3905,
       4.9416,
       5.061,
       4.8357,
       6.5465,
       4.9544,
       6.6259,
       6.8835,
       6.9063,
       6.7966,
       6.6906,
       6.3705,
       6.4369,
       6.2604,
       6.2024,
       6.0628,
       5.9088,
       6.2584,
       6.4628,
       7.6603,
       6.5682,
       7.2843,
       6.6059,
       6.1412,
       6.1768,
       7.0935,
       6.0472,
       6.4073,
       6.4626,
       6.2357
      ],
      "block_gbps": [
       12.7434,
       14.5312,
       12.4494,
       13.5805,
       13.2601,
       13.8779,
       10.2511,
       13.5454,
       10.1282,
       9.7492,
       9.7171,
       9.8739,
       10.0304,
       10.5343,
       10.4257,
       10.7196,
       10.8198,
       11.069,
       11.3575,
       10.723,
       10.3839,
       8.7606,
       10.2173,
       9.2128,
       10.159,
       10.9276,
       10.8646,
       9.4605,
       11.0975,
       10.4737,
       10.3841,
       10.762
      ]
     }
    ],
    "first_range_latency_ms": 5.2662,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 20.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67108864,
    "peak_rss_bytes": 16138620928,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 9.64,
    "gbps_per_cpu_core": 107.3737,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 24.7539,
     "gbps": 10.8442
    },
    "verify": {
     "regions": [
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 1
   },
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 4294967296,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 199.7893,
    "aggregate_gbps": 10.7487,
    "steady_state_gbps": 10.3649,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 4294967296,
      "segment_end": 6442450944,
      "bytes_returned": 2147483648,
      "wall_ms": 190.0003,
      "gbps": 11.3025,
      "block_count": 16,
      "first_block_wall_ms": 9.3487,
      "block_timings_ms": [
       9.3487,
       8.4982,
       8.1769,
       9.0391,
       9.0507,
       14.3159,
       12.7311,
       13.101,
       13.1793,
       13.6854,
       13.1147,
       12.9492,
       12.2505,
       12.8715,
       13.4425,
       13.349
      ],
      "block_gbps": [
       14.3569,
       15.7937,
       16.4143,
       14.8486,
       14.8296,
       9.3754,
       10.5425,
       10.2448,
       10.184,
       9.8074,
       10.2341,
       10.3649,
       10.9561,
       10.4275,
       9.9846,
       10.0545
      ]
     }
    ],
    "first_range_latency_ms": 9.3487,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 20.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 16195899392,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 10.01,
    "gbps_per_cpu_core": 107.3737,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.6998,
     "gbps": 13.6263
    },
    "verify": {
     "regions": [
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 2
   },
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 6442450944,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 163.5643,
    "aggregate_gbps": 13.1293,
    "steady_state_gbps": 15.0489,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 6442450944,
      "segment_end": 8589934592,
      "bytes_returned": 2147483648,
      "wall_ms": 144.9393,
      "gbps": 14.8164,
      "block_count": 8,
      "first_block_wall_ms": 18.5522,
      "block_timings_ms": [
       18.5522,
       18.1214,
       17.748,
       17.0059,
       17.5477,
       20.0643,
       17.8376,
       17.4463
      ],
      "block_gbps": [
       14.4692,
       14.8132,
       15.1249,
       15.7848,
       15.2974,
       13.3787,
       15.0489,
       15.3864
      ]
     }
    ],
    "first_range_latency_ms": 18.5522,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 20.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 268435456,
    "peak_rss_bytes": 16330117120,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 12.23,
    "gbps_per_cpu_core": 107.3742,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 21.521,
     "gbps": 12.4732
    },
    "verify": {
     "regions": [
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589672448,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 3
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 8589934592,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 102.643,
    "aggregate_gbps": 20.9219,
    "steady_state_gbps": 12.7024,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 8589934592,
      "segment_end": 9663676416,
      "bytes_returned": 1073741824,
      "wall_ms": 101.9827,
      "gbps": 10.5287,
      "block_count": 32,
      "first_block_wall_ms": 3.5745,
      "block_timings_ms": [
       3.5745,
       3.8899,
       3.7848,
       3.609,
       3.4145,
       3.5176,
       4.3908,
       3.4475,
       2.8182,
       2.6655,
       2.6393,
       2.4179,
       2.6519,
       2.5727,
       2.8797,
       2.7652,
       2.6678,
       2.8233,
       2.691,
       2.9308,
       2.7821,
       2.8215,
       2.8261,
       2.8285,
       3.8259,
       3.4952,
       3.0679,
       3.4123,
       3.6133,
       3.7771,
       3.6145,
       3.06
      ],
      "block_gbps": [
       9.3871,
       8.6262,
       8.8657,
       9.2973,
       9.827,
       9.539,
       7.642,
       9.733,
       11.9065,
       12.5883,
       12.7132,
       13.8775,
       12.653,
       13.0426,
       11.6522,
       12.1343,
       12.5777,
       11.8849,
       12.469,
       11.4488,
       12.0609,
       11.8926,
       11.8731,
       11.8629,
       8.7703,
       9.6002,
       10.9372,
       9.8333,
       9.2863,
       8.8837,
       9.2833,
       10.9656
      ]
     },
     {
      "worker": 1,
      "segment_start": 9663676416,
      "segment_end": 10737418240,
      "bytes_returned": 1073741824,
      "wall_ms": 69.6848,
      "gbps": 15.4085,
      "block_count": 32,
      "first_block_wall_ms": 3.7416,
      "block_timings_ms": [
       3.7416,
       2.5407,
       2.4754,
       2.229,
       2.758,
       2.6416,
       2.324,
       2.264,
       2.2449,
       2.1254,
       1.8468,
       1.8027,
       1.7327,
       1.653,
       1.788,
       1.7422,
       1.6605,
       1.7337,
       2.2621,
       1.8398,
       2.3744,
       2.3271,
       2.4104,
       2.2544,
       2.1121,
       2.0611,
       2.0431,
       2.0096,
       2.0001,
       1.9894,
       1.9782,
       2.1177
      ],
      "block_gbps": [
       8.9679,
       13.2066,
       13.5551,
       15.0537,
       12.1662,
       12.7024,
       14.4381,
       14.8206,
       14.947,
       15.7871,
       18.1686,
       18.613,
       19.3656,
       20.2987,
       18.7669,
       19.2599,
       20.2071,
       19.3537,
       14.833,
       18.2384,
       14.1318,
       14.4188,
       13.9207,
       14.8842,
       15.8871,
       16.2799,
       16.4231,
       16.6973,
       16.776,
       16.8666,
       16.9618,
       15.8445
      ]
     }
    ],
    "first_range_latency_ms": 3.5745,
    "tail_spread_ms": 32.2979,
    "process_cpu_ms": 40.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 33554432,
    "peak_rss_bytes": 16598552576,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 38.97,
    "gbps_per_cpu_core": 53.6872,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 21.2401,
     "gbps": 12.6381
    },
    "verify": {
     "regions": [
      {
       "rel_start": 8589934592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737156096,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 4
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 10737418240,
    "window_len": 1572399232,
    "status": "ok",
    "bytes_returned": 1572399232,
    "expected_bytes": 1572399232,
    "total_wall_ms": 111.479,
    "aggregate_gbps": 14.1049,
    "steady_state_gbps": 9.7161,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 10737418240,
      "segment_end": 11523617856,
      "bytes_returned": 786199616,
      "wall_ms": 80.4805,
      "gbps": 9.7688,
      "block_count": 12,
      "first_block_wall_ms": 6.8339,
      "block_timings_ms": [
       6.8339,
       7.4299,
       6.5578,
       5.6403,
       8.0113,
       6.9447,
       6.8421,
       6.2901,
       6.8902,
       6.672,
       6.8679,
       4.9405
      ],
      "block_gbps": [
       9.8199,
       9.0322,
       10.2334,
       11.8981,
       8.3767,
       9.6633,
       9.8082,
       10.669,
       9.7397,
       10.0583,
       9.7713,
       9.7161
      ]
     },
     {
      "worker": 1,
      "segment_start": 11523617856,
      "segment_end": 12309817472,
      "bytes_returned": 786199616,
      "wall_ms": 85.4813,
      "gbps": 9.1973,
      "block_count": 12,
      "first_block_wall_ms": 8.6382,
      "block_timings_ms": [
       8.6382,
       6.5064,
       7.0576,
       7.4309,
       6.5615,
       8.1175,
       7.5686,
       7.5507,
       7.5742,
       6.9089,
       6.5391,
       4.6385
      ],
      "block_gbps": [
       7.7688,
       10.3143,
       9.5087,
       9.031,
       10.2276,
       8.2671,
       8.8667,
       8.8877,
       8.8602,
       9.7134,
       10.2628,
       10.3486
      ]
     }
    ],
    "first_range_latency_ms": 6.8339,
    "tail_spread_ms": 5.0008,
    "process_cpu_ms": 50.0,
    "thread_cpu_ms": 20.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67108864,
    "peak_rss_bytes": 16632107008,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 44.85,
    "gbps_per_cpu_core": 31.448,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.3984,
     "gbps": 14.5902
    },
    "verify": {
     "regions": [
      {
       "rel_start": 10737418240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 12309555328,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 5
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 154.1867,
    "aggregate_gbps": 13.9278,
    "steady_state_gbps": 9.9423,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 1073741824,
      "bytes_returned": 1073741824,
      "wall_ms": 110.6099,
      "gbps": 9.7075,
      "block_count": 8,
      "first_block_wall_ms": 14.1292,
      "block_timings_ms": [
       14.1292,
       13.4997,
       13.6733,
       13.8734,
       14.9295,
       13.701,
       13.1641,
       13.3194
      ],
      "block_gbps": [
       9.4993,
       9.9423,
       9.8161,
       9.6745,
       8.9901,
       9.7962,
       10.1957,
       10.0769
      ]
     },
     {
      "worker": 1,
      "segment_start": 1073741824,
      "segment_end": 2147483648,
      "bytes_returned": 1073741824,
      "wall_ms": 102.3152,
      "gbps": 10.4944,
      "block_count": 8,
      "first_block_wall_ms": 12.8467,
      "block_timings_ms": [
       12.8467,
       9.8869,
       9.4882,
       14.7173,
       17.5285,
       12.7433,
       12.8438,
       12.0016
      ],
      "block_gbps": [
       10.4477,
       13.5753,
       14.1458,
       9.1198,
       7.6571,
       10.5324,
       10.45,
       11.1833
      ]
     }
    ],
    "first_range_latency_ms": 12.8467,
    "tail_spread_ms": 8.2947,
    "process_cpu_ms": 80.0,
    "thread_cpu_ms": 20.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 16699215872,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 51.89,
    "gbps_per_cpu_core": 26.8435,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.3083,
     "gbps": 13.9026
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 6
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 2147483648,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 173.3468,
    "aggregate_gbps": 12.3884,
    "steady_state_gbps": 9.945,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 2147483648,
      "segment_end": 3221225472,
      "bytes_returned": 1073741824,
      "wall_ms": 109.6011,
      "gbps": 9.7968,
      "block_count": 4,
      "first_block_wall_ms": 26.4832,
      "block_timings_ms": [
       26.4832,
       28.5154,
       25.5083,
       28.9033
      ],
      "block_gbps": [
       10.1361,
       9.4137,
       10.5235,
       9.2874
      ]
     },
     {
      "worker": 1,
      "segment_start": 3221225472,
      "segment_end": 4294967296,
      "bytes_returned": 1073741824,
      "wall_ms": 101.0787,
      "gbps": 10.6228,
      "block_count": 4,
      "first_block_wall_ms": 26.5431,
      "block_timings_ms": [
       26.5431,
       18.7211,
       26.9921,
       28.605
      ],
      "block_gbps": [
       10.1132,
       14.3387,
       9.945,
       9.3842
      ]
     }
    ],
    "first_range_latency_ms": 26.4832,
    "tail_spread_ms": 8.5224,
    "process_cpu_ms": 140.0,
    "thread_cpu_ms": 50.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 268435456,
    "peak_rss_bytes": 16833433600,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 80.76,
    "gbps_per_cpu_core": 15.3392,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.7837,
     "gbps": 13.5685
    },
    "verify": {
     "regions": [
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 7
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 4294967296,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 98.1831,
    "aggregate_gbps": 21.8722,
    "steady_state_gbps": 9.3223,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 4294967296,
      "segment_end": 4831838208,
      "bytes_returned": 536870912,
      "wall_ms": 69.9554,
      "gbps": 7.6745,
      "block_count": 16,
      "first_block_wall_ms": 3.5469,
      "block_timings_ms": [
       3.5469,
       3.4054,
       3.2438,
       5.2572,
       7.652,
       4.0115,
       3.8563,
       3.9867,
       6.8489,
       5.7201,
       3.5994,
       3.3583,
       3.4135,
       3.5699,
       3.9805,
       4.0006
      ],
      "block_gbps": [
       9.4603,
       9.8533,
       10.344,
       6.3826,
       4.385,
       8.3647,
       8.7011,
       8.4165,
       4.8992,
       5.866,
       9.3223,
       9.9915,
       9.8299,
       9.3992,
       8.4297,
       8.3873
      ]
     },
     {
      "worker": 1,
      "segment_start": 4831838208,
      "segment_end": 5368709120,
      "bytes_returned": 536870912,
      "wall_ms": 68.9484,
      "gbps": 7.7866,
      "block_count": 16,
      "first_block_wall_ms": 3.6388,
      "block_timings_ms": [
       3.6388,
       5.0112,
       10.5653,
       3.967,
       4.0318,
       3.6831,
       3.8242,
       2.7097,
       2.3517,
       3.8999,
       3.7912,
       4.575,
       3.6654,
       4.8823,
       4.2715,
       3.5389
      ],
      "block_gbps": [
       9.2213,
       6.6959,
       3.1759,
       8.4583,
       8.3225,
       9.1104,
       8.7742,
       12.3829,
       14.2683,
       8.6038,
       8.8507,
       7.3344,
       9.1544,
       6.8726,
       7.8555,
       9.4815
      ]
     },
     {
      "worker": 2,
      "segment_start": 5368709120,
      "segment_end": 5905580032,
      "bytes_returned": 536870912,
      "wall_ms": 62.0975,
      "gbps": 8.6456,
      "block_count": 16,
      "first_block_wall_ms": 6.0227,
      "block_timings_ms": [
       6.0227,
       9.4645,
       3.2967,
       5.2723,
       3.1626,
       3.4835,
       3.3581,
       2.8484,
       2.7071,
       2.4603,
       2.9842,
       3.7374,
       4.0935,
       3.0339,
       2.9763,
       2.9915
      ],
      "block_gbps": [
       5.5713,
       3.5453,
       10.1781,
       6.3643,
       10.6098,
       9.6323,
       9.9921,
       11.78,
       12.3949,
       13.6385,
       11.2442,
       8.9781,
       8.1971,
       11.0599,
       11.2737,
       11.2166
      ]
     },
     {
      "worker": 3,
      "segment_start": 5905580032,
      "segment_end": 6442450944,
      "bytes_returned": 536870912,
      "wall_ms": 55.8787,
      "gbps": 9.6078,
      "block_count": 16,
      "first_block_wall_ms": 6.0901,
      "block_timings_ms": [
       6.0901,
       2.8649,
       3.0773,
       3.0024,
       2.7867,
       3.379,
       3.9773,
       5.6631,
       3.8424,
       2.7182,
       2.6769,
       2.8099,
       2.5847,
       3.3969,
       3.5138,
       3.1206
      ],
      "block_gbps": [
       5.5097,
       11.7123,
       10.9039,
       11.1758,
       12.041,
       9.9302,
       8.4364,
       5.9251,
       8.7327,
       12.3445,
       12.5349,
       11.9416,
       12.9818,
       9.878,
       9.5494,
       10.7527
      ]
     }
    ],
    "first_range_latency_ms": 3.5469,
    "tail_spread_ms": 14.0767,
    "process_cpu_ms": 140.0,
    "thread_cpu_ms": 20.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67264512,
    "peak_rss_bytes": 17101869056,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 142.59,
    "gbps_per_cpu_core": 15.3391,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 26.8235,
     "gbps": 10.0075
    },
    "verify": {
     "regions": [
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 8
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 6442450944,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 125.0119,
    "aggregate_gbps": 17.1782,
    "steady_state_gbps": 10.63,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 6442450944,
      "segment_end": 6979321856,
      "bytes_returned": 536870912,
      "wall_ms": 85.3799,
      "gbps": 6.288,
      "block_count": 8,
      "first_block_wall_ms": 6.1468,
      "block_timings_ms": [
       6.1468,
       6.4659,
       15.1954,
       7.1341,
       12.1494,
       12.3716,
       9.3919,
       16.0251
      ],
      "block_gbps": [
       10.9177,
       10.3789,
       4.4164,
       9.4068,
       5.5236,
       5.4244,
       7.1454,
       4.1877
      ]
     },
     {
      "worker": 1,
      "segment_start": 6979321856,
      "segment_end": 7516192768,
      "bytes_returned": 536870912,
      "wall_ms": 70.4199,
      "gbps": 7.6238,
      "block_count": 8,
      "first_block_wall_ms": 6.3132,
      "block_timings_ms": [
       6.3132,
       7.7976,
       7.4257,
       5.4643,
       5.9078,
       6.2952,
       11.7981,
       12.0941
      ],
      "block_gbps": [
       10.63,
       8.6064,
       9.0374,
       12.2814,
       11.3595,
       10.6604,
       5.6881,
       5.5489
      ]
     },
     {
      "worker": 2,
      "segment_start": 7516192768,
      "segment_end": 8053063680,
      "bytes_returned": 536870912,
      "wall_ms": 63.5789,
      "gbps": 8.4442,
      "block_count": 8,
      "first_block_wall_ms": 11.072,
      "block_timings_ms": [
       11.072,
       6.3642,
       9.9547,
       17.5837,
       4.8587,
       4.7236,
       4.4946,
       4.2531
      ],
      "block_gbps": [
       6.0611,
       10.5447,
       6.7414,
       3.8165,
       13.8121,
       14.2071,
       14.9309,
       15.7786
      ]
     },
     {
      "worker": 3,
      "segment_start": 8053063680,
      "segment_end": 8589934592,
      "bytes_returned": 536870912,
      "wall_ms": 37.6577,
      "gbps": 14.2566,
      "block_count": 8,
      "first_block_wall_ms": 4.7464,
      "block_timings_ms": [
       4.7464,
       4.4697,
       4.2683,
       3.9997,
       5.6882,
       4.8792,
       4.8923,
       4.5127
      ],
      "block_gbps": [
       14.1388,
       15.0143,
       15.7225,
       16.7783,
       11.798,
       13.754,
       13.7171,
       14.871
      ]
     }
    ],
    "first_range_latency_ms": 4.7464,
    "tail_spread_ms": 47.7222,
    "process_cpu_ms": 240.0,
    "thread_cpu_ms": 60.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 17169133568,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 191.98,
    "gbps_per_cpu_core": 8.9478,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 25.5763,
     "gbps": 10.4955
    },
    "verify": {
     "regions": [
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589672448,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 9
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 8589934592,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 146.3982,
    "aggregate_gbps": 14.6688,
    "steady_state_gbps": 9.9072,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 8589934592,
      "segment_end": 9126805504,
      "bytes_returned": 536870912,
      "wall_ms": 59.2397,
      "gbps": 9.0627,
      "block_count": 4,
      "first_block_wall_ms": 13.7247,
      "block_timings_ms": [
       13.7247,
       14.0689,
       13.5475,
       17.6777
      ],
      "block_gbps": [
       9.7793,
       9.54,
       9.9072,
       7.5925
      ]
     },
     {
      "worker": 1,
      "segment_start": 9126805504,
      "segment_end": 9663676416,
      "bytes_returned": 536870912,
      "wall_ms": 81.7858,
      "gbps": 6.5643,
      "block_count": 4,
      "first_block_wall_ms": 13.4299,
      "block_timings_ms": [
       13.4299,
       27.7013,
       17.4133,
       22.9465
      ],
      "block_gbps": [
       9.9939,
       4.8452,
       7.7078,
       5.8492
      ]
     },
     {
      "worker": 2,
      "segment_start": 9663676416,
      "segment_end": 10200547328,
      "bytes_returned": 536870912,
      "wall_ms": 70.8749,
      "gbps": 7.5749,
      "block_count": 4,
      "first_block_wall_ms": 39.8145,
      "block_timings_ms": [
       39.8145,
       11.9071,
       9.6634,
       9.26
      ],
      "block_gbps": [
       3.3711,
       11.2721,
       13.8893,
       14.4944
      ]
     },
     {
      "worker": 3,
      "segment_start": 10200547328,
      "segment_end": 10737418240,
      "bytes_returned": 536870912,
      "wall_ms": 50.2306,
      "gbps": 10.6881,
      "block_count": 4,
      "first_block_wall_ms": 13.0832,
      "block_timings_ms": [
       13.0832,
       12.8408,
       12.8935,
       11.2208
      ],
      "block_gbps": [
       10.2588,
       10.4524,
       10.4097,
       11.9616
      ]
     }
    ],
    "first_range_latency_ms": 13.0832,
    "tail_spread_ms": 31.5552,
    "process_cpu_ms": 270.0,
    "thread_cpu_ms": 70.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 268435456,
    "peak_rss_bytes": 17303351296,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 184.43,
    "gbps_per_cpu_core": 7.9536,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 28.5955,
     "gbps": 9.3873
    },
    "verify": {
     "regions": [
      {
       "rel_start": 8589934592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737156096,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 10
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 10737418240,
    "window_len": 1572399232,
    "status": "ok",
    "bytes_returned": 1572399232,
    "expected_bytes": 1572399232,
    "total_wall_ms": 104.3344,
    "aggregate_gbps": 15.0708,
    "steady_state_gbps": 10.7607,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 10737418240,
      "segment_end": 11130518048,
      "bytes_returned": 393099808,
      "wall_ms": 46.6574,
      "gbps": 8.4252,
      "block_count": 2,
      "first_block_wall_ms": 24.9459,
      "block_timings_ms": [
       24.9459,
       12.4499
      ],
      "block_gbps": [
       10.7607,
       10.0132
      ]
     },
     {
      "worker": 1,
      "segment_start": 11130518048,
      "segment_end": 11523617856,
      "bytes_returned": 393099808,
      "wall_ms": 34.0934,
      "gbps": 11.5301,
      "block_count": 2,
      "first_block_wall_ms": 24.9599,
      "block_timings_ms": [
       24.9599,
       9.0355
      ],
      "block_gbps": [
       10.7547,
       13.7972
      ]
     },
     {
      "worker": 2,
      "segment_start": 11523617856,
      "segment_end": 11916717664,
      "bytes_returned": 393099808,
      "wall_ms": 45.5807,
      "gbps": 8.6243,
      "block_count": 2,
      "first_block_wall_ms": 33.8939,
      "block_timings_ms": [
       33.8939,
       11.5318
      ],
      "block_gbps": [
       7.9199,
       10.8105
      ]
     },
     {
      "worker": 3,
      "segment_start": 11916717664,
      "segment_end": 12309817472,
      "bytes_returned": 393099808,
      "wall_ms": 30.2488,
      "gbps": 12.9956,
      "block_count": 2,
      "first_block_wall_ms": 21.4637,
      "block_timings_ms": [
       21.4637,
       8.6792
      ],
      "block_gbps": [
       12.5065,
       14.3635
      ]
     }
    ],
    "first_range_latency_ms": 21.4637,
    "tail_spread_ms": 16.4086,
    "process_cpu_ms": 140.0,
    "thread_cpu_ms": 30.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 268435456,
    "peak_rss_bytes": 17571786752,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 134.18,
    "gbps_per_cpu_core": 11.2314,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.0655,
     "gbps": 14.0796
    },
    "verify": {
     "regions": [
      {
       "rel_start": 10737418240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 12309555328,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 11
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 99.1875,
    "aggregate_gbps": 21.6507,
    "steady_state_gbps": 7.4019,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 268435456,
      "bytes_returned": 268435456,
      "wall_ms": 38.0584,
      "gbps": 7.0532,
      "block_count": 8,
      "first_block_wall_ms": 3.2472,
      "block_timings_ms": [
       3.2472,
       3.3889,
       2.2459,
       4.4698,
       5.812,
       4.0063,
       4.063,
       7.6036
      ],
      "block_gbps": [
       10.3332,
       9.9014,
       14.9401,
       7.5069,
       5.7733,
       8.3754,
       8.2585,
       4.4129
      ]
     },
     {
      "worker": 1,
      "segment_start": 268435456,
      "segment_end": 536870912,
      "bytes_returned": 268435456,
      "wall_ms": 68.4146,
      "gbps": 3.9237,
      "block_count": 8,
      "first_block_wall_ms": 2.9517,
      "block_timings_ms": [
       2.9517,
       2.9,
       14.4365,
       18.7247,
       14.4382,
       4.311,
       3.1511,
       4.4999
      ],
      "block_gbps": [
       11.368,
       11.5707,
       2.3243,
       1.792,
       2.324,
       7.7835,
       10.6484,
       7.4567
      ]
     },
     {
      "worker": 2,
      "segment_start": 536870912,
      "segment_end": 805306368,
      "bytes_returned": 268435456,
      "wall_ms": 53.025,
      "gbps": 5.0624,
      "block_count": 8,
      "first_block_wall_ms": 6.8298,
      "block_timings_ms": [
       6.8298,
       2.5683,
       7.4058,
       2.9843,
       11.401,
       7.3318,
       4.4045,
       9.8165
      ],
      "block_gbps": [
       4.913,
       13.065,
       4.5308,
       11.2437,
       2.9431,
       4.5765,
       7.6182,
       3.4182
      ]
     },
     {
      "worker": 3,
      "segment_start": 805306368,
      "segment_end": 1073741824,
      "bytes_returned": 268435456,
      "wall_ms": 62.2108,
      "gbps": 4.3149,
      "block_count": 8,
      "first_block_wall_ms": 14.3029,
      "block_timings_ms": [
       14.3029,
       14.5998,
       4.6007,
       9.6618,
       4.7833,
       4.0715,
       5.9631,
       4.0175
      ],
      "block_gbps": [
       2.346,
       2.2983,
       7.2934,
       3.4729,
       7.0149,
       8.2413,
       5.627,
       8.3522
      ]
     },
     {
      "worker": 4,
      "segment_start": 1073741824,
      "segment_end": 1342177280,
      "bytes_returned": 268435456,
      "wall_ms": 51.7698,
      "gbps": 5.1852,
      "block_count": 8,
      "first_block_wall_ms": 10.6548,
      "block_timings_ms": [
       10.6548,
       4.7364,
       7.6673,
       4.3467,
       3.9242,
       6.2101,
       7.2754,
       4.2346
      ],
      "block_gbps": [
       3.1492,
       7.0844,
       4.3763,
       7.7196,
       8.5506,
       5.4032,
       4.612,
       7.9238
      ]
     },
     {
      "worker": 5,
      "segment_start": 1342177280,
      "segment_end": 1610612736,
      "bytes_returned": 268435456,
      "wall_ms": 39.1965,
      "gbps": 6.8485,
      "block_count": 8,
      "first_block_wall_ms": 9.9054,
      "block_timings_ms": [
       9.9054,
       4.5332,
       2.9151,
       7.2327,
       2.5774,
       4.782,
       4.1988,
       2.7883
      ],
      "block_gbps": [
       3.3875,
       7.4019,
       11.5106,
       4.6393,
       13.0189,
       7.0168,
       7.9914,
       12.0341
      ]
     },
     {
      "worker": 6,
      "segment_start": 1610612736,
      "segment_end": 1879048192,
      "bytes_returned": 268435456,
      "wall_ms": 41.112,
      "gbps": 6.5294,
      "block_count": 8,
      "first_block_wall_ms": 4.6903,
      "block_timings_ms": [
       4.6903,
       6.7901,
       7.5832,
       4.3534,
       3.7034,
       6.023,
       4.0104,
       3.7084
      ],
      "block_gbps": [
       7.1539,
       4.9417,
       4.4248,
       7.7077,
       9.0605,
       5.571,
       8.3669,
       9.0483
      ]
     },
     {
      "worker": 7,
      "segment_start": 1879048192,
      "segment_end": 2147483648,
      "bytes_returned": 268435456,
      "wall_ms": 34.0867,
      "gbps": 7.8751,
      "block_count": 8,
      "first_block_wall_ms": 6.7273,
      "block_timings_ms": [
       6.7273,
       3.0988,
       2.6638,
       4.6677,
       6.8878,
       3.2142,
       3.2296,
       3.4058
      ],
      "block_gbps": [
       4.9878,
       10.8282,
       12.5965,
       7.1887,
       4.8715,
       10.4394,
       10.3897,
       9.852
      ]
     }
    ],
    "first_range_latency_ms": 2.9517,
    "tail_spread_ms": 34.3279,
    "process_cpu_ms": 250.0,
    "thread_cpu_ms": 50.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 101142528,
    "peak_rss_bytes": 17840222208,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 252.05,
    "gbps_per_cpu_core": 8.5899,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 29.1912,
     "gbps": 9.1958
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 12
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 2147483648,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 122.4384,
    "aggregate_gbps": 17.5393,
    "steady_state_gbps": 9.0143,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 2147483648,
      "segment_end": 2415919104,
      "bytes_returned": 268435456,
      "wall_ms": 26.9239,
      "gbps": 9.9702,
      "block_count": 4,
      "first_block_wall_ms": 4.7451,
      "block_timings_ms": [
       4.7451,
       7.9117,
       6.7378,
       7.2797
      ],
      "block_gbps": [
       14.1428,
       8.4823,
       9.9601,
       9.2186
      ]
     },
     {
      "worker": 1,
      "segment_start": 2415919104,
      "segment_end": 2684354560,
      "bytes_returned": 268435456,
      "wall_ms": 29.7936,
      "gbps": 9.0098,
      "block_count": 4,
      "first_block_wall_ms": 8.8149,
      "block_timings_ms": [
       8.8149,
       6.0316,
       7.4447,
       7.3655
      ],
      "block_gbps": [
       7.6131,
       11.1262,
       9.0143,
       9.1113
      ]
     },
     {
      "worker": 2,
      "segment_start": 2684354560,
      "segment_end": 2952790016,
      "bytes_returned": 268435456,
      "wall_ms": 27.9093,
      "gbps": 9.6181,
      "block_count": 4,
      "first_block_wall_ms": 6.8997,
      "block_timings_ms": [
       6.8997,
       6.9902,
       7.1216,
       6.6223
      ],
      "block_gbps": [
       9.7264,
       9.6004,
       9.4233,
       10.1337
      ]
     },
     {
      "worker": 3,
      "segment_start": 2952790016,
      "segment_end": 3221225472,
      "bytes_returned": 268435456,
      "wall_ms": 31.7346,
      "gbps": 8.4588,
      "block_count": 4,
      "first_block_wall_ms": 6.9526,
      "block_timings_ms": [
       6.9526,
       6.344,
       10.3581,
       7.9804
      ],
      "block_gbps": [
       9.6523,
       10.5783,
       6.4789,
       8.4093
      ]
     },
     {
      "worker": 4,
      "segment_start": 3221225472,
      "segment_end": 3489660928,
      "bytes_returned": 268435456,
      "wall_ms": 39.9686,
      "gbps": 6.7162,
      "block_count": 4,
      "first_block_wall_ms": 6.5591,
      "block_timings_ms": [
       6.5591,
       10.4295,
       7.515,
       15.3734
      ],
      "block_gbps": [
       10.2314,
       6.4345,
       8.9299,
       4.3652
      ]
     },
     {
      "worker": 5,
      "segment_start": 3489660928,
      "segment_end": 3758096384,
      "bytes_returned": 268435456,
      "wall_ms": 33.3317,
      "gbps": 8.0534,
      "block_count": 4,
      "first_block_wall_ms": 10.2308,
      "block_timings_ms": [
       10.2308,
       7.7659,
       7.9023,
       7.3229
      ],
      "block_gbps": [
       6.5595,
       8.6414,
       8.4923,
       9.1643
      ]
     },
     {
      "worker": 6,
      "segment_start": 3758096384,
      "segment_end": 4026531840,
      "bytes_returned": 268435456,
      "wall_ms": 49.1181,
      "gbps": 5.4651,
      "block_count": 4,
      "first_block_wall_ms": 15.6123,
      "block_timings_ms": [
       15.6123,
       13.4535,
       7.5808,
       12.3278
      ],
      "block_gbps": [
       4.2985,
       4.9882,
       8.8525,
       5.4437
      ]
     },
     {
      "worker": 7,
      "segment_start": 4026531840,
      "segment_end": 4294967296,
      "bytes_returned": 268435456,
      "wall_ms": 26.4376,
      "gbps": 10.1535,
      "block_count": 4,
      "first_block_wall_ms": 12.2,
      "block_timings_ms": [
       12.2,
       4.4418,
       4.2561,
       5.2685
      ],
      "block_gbps": [
       5.5007,
       15.1085,
       15.7678,
       12.7378
      ]
     }
    ],
    "first_range_latency_ms": 4.7451,
    "tail_spread_ms": 22.6805,
    "process_cpu_ms": 220.0,
    "thread_cpu_ms": 40.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67108864,
    "peak_rss_bytes": 17941364736,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 179.68,
    "gbps_per_cpu_core": 9.7613,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.9355,
     "gbps": 13.4652
    },
    "verify": {
     "regions": [
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 13
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 4294967296,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 131.6944,
    "aggregate_gbps": 16.3066,
    "steady_state_gbps": 8.9695,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 4294967296,
      "segment_end": 4563402752,
      "bytes_returned": 268435456,
      "wall_ms": 28.1182,
      "gbps": 9.5467,
      "block_count": 2,
      "first_block_wall_ms": 12.8902,
      "block_timings_ms": [
       12.8902,
       15.1103
      ],
      "block_gbps": [
       10.4124,
       8.8825
      ]
     },
     {
      "worker": 1,
      "segment_start": 4563402752,
      "segment_end": 4831838208,
      "bytes_returned": 268435456,
      "wall_ms": 30.6703,
      "gbps": 8.7523,
      "block_count": 2,
      "first_block_wall_ms": 14.7357,
      "block_timings_ms": [
       14.7357,
       15.8912
      ],
      "block_gbps": [
       9.1083,
       8.4461
      ]
     },
     {
      "worker": 2,
      "segment_start": 4831838208,
      "segment_end": 5100273664,
      "bytes_returned": 268435456,
      "wall_ms": 31.0163,
      "gbps": 8.6547,
      "block_count": 2,
      "first_block_wall_ms": 16.4082,
      "block_timings_ms": [
       16.4082,
       14.4256
      ],
      "block_gbps": [
       8.1799,
       9.3041
      ]
     },
     {
      "worker": 3,
      "segment_start": 5100273664,
      "segment_end": 5368709120,
      "bytes_returned": 268435456,
      "wall_ms": 42.9818,
      "gbps": 6.2453,
      "block_count": 2,
      "first_block_wall_ms": 14.4316,
      "block_timings_ms": [
       14.4316,
       15.2898
      ],
      "block_gbps": [
       9.3002,
       8.7782
      ]
     },
     {
      "worker": 4,
      "segment_start": 5368709120,
      "segment_end": 5637144576,
      "bytes_returned": 268435456,
      "wall_ms": 28.678,
      "gbps": 9.3603,
      "block_count": 2,
      "first_block_wall_ms": 13.6644,
      "block_timings_ms": [
       13.6644,
       14.9638
      ],
      "block_gbps": [
       9.8225,
       8.9695
      ]
     },
     {
      "worker": 5,
      "segment_start": 5637144576,
      "segment_end": 5905580032,
      "bytes_returned": 268435456,
      "wall_ms": 29.8129,
      "gbps": 9.004,
      "block_count": 2,
      "first_block_wall_ms": 15.9229,
      "block_timings_ms": [
       15.9229,
       13.8397
      ],
      "block_gbps": [
       8.4292,
       9.698
      ]
     },
     {
      "worker": 6,
      "segment_start": 5905580032,
      "segment_end": 6174015488,
      "bytes_returned": 268435456,
      "wall_ms": 29.761,
      "gbps": 9.0197,
      "block_count": 2,
      "first_block_wall_ms": 14.1918,
      "block_timings_ms": [
       14.1918,
       15.3935
      ],
      "block_gbps": [
       9.4574,
       8.7191
      ]
     },
     {
      "worker": 7,
      "segment_start": 6174015488,
      "segment_end": 6442450944,
      "bytes_returned": 268435456,
      "wall_ms": 29.0023,
      "gbps": 9.2557,
      "block_count": 2,
      "first_block_wall_ms": 15.3414,
      "block_timings_ms": [
       15.3414,
       13.5088
      ],
      "block_gbps": [
       8.7487,
       9.9356
      ]
     }
    ],
    "first_range_latency_ms": 12.8902,
    "tail_spread_ms": 14.8636,
    "process_cpu_ms": 230.0,
    "thread_cpu_ms": 50.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 18008473600,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 174.65,
    "gbps_per_cpu_core": 9.3369,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 28.2436,
     "gbps": 9.5043
    },
    "verify": {
     "regions": [
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 14
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 6442450944,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 214.3773,
    "aggregate_gbps": 10.0173,
    "steady_state_gbps": 9.8379,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 6442450944,
      "segment_end": 6710886400,
      "bytes_returned": 268435456,
      "wall_ms": 17.8946,
      "gbps": 15.0009,
      "block_count": 1,
      "first_block_wall_ms": 17.8266,
      "block_timings_ms": [
       17.8266
      ],
      "block_gbps": [
       15.0581
      ]
     },
     {
      "worker": 1,
      "segment_start": 6710886400,
      "segment_end": 6979321856,
      "bytes_returned": 268435456,
      "wall_ms": 27.362,
      "gbps": 9.8105,
      "block_count": 1,
      "first_block_wall_ms": 27.286,
      "block_timings_ms": [
       27.286
      ],
      "block_gbps": [
       9.8379
      ]
     },
     {
      "worker": 2,
      "segment_start": 6979321856,
      "segment_end": 7247757312,
      "bytes_returned": 268435456,
      "wall_ms": 46.7451,
      "gbps": 5.7425,
      "block_count": 1,
      "first_block_wall_ms": 46.7209,
      "block_timings_ms": [
       46.7209
      ],
      "block_gbps": [
       5.7455
      ]
     },
     {
      "worker": 3,
      "segment_start": 7247757312,
      "segment_end": 7516192768,
      "bytes_returned": 268435456,
      "wall_ms": 29.6046,
      "gbps": 9.0674,
      "block_count": 1,
      "first_block_wall_ms": 29.5265,
      "block_timings_ms": [
       29.5265
      ],
      "block_gbps": [
       9.0913
      ]
     },
     {
      "worker": 4,
      "segment_start": 7516192768,
      "segment_end": 7784628224,
      "bytes_returned": 268435456,
      "wall_ms": 25.6355,
      "gbps": 10.4712,
      "block_count": 1,
      "first_block_wall_ms": 25.5778,
      "block_timings_ms": [
       25.5778
      ],
      "block_gbps": [
       10.4948
      ]
     },
     {
      "worker": 5,
      "segment_start": 7784628224,
      "segment_end": 8053063680,
      "bytes_returned": 268435456,
      "wall_ms": 19.1232,
      "gbps": 14.0372,
      "block_count": 1,
      "first_block_wall_ms": 19.0577,
      "block_timings_ms": [
       19.0577
      ],
      "block_gbps": [
       14.0854
      ]
     },
     {
      "worker": 6,
      "segment_start": 8053063680,
      "segment_end": 8321499136,
      "bytes_returned": 268435456,
      "wall_ms": 17.7289,
      "gbps": 15.1411,
      "block_count": 1,
      "first_block_wall_ms": 17.7,
      "block_timings_ms": [
       17.7
      ],
      "block_gbps": [
       15.1658
      ]
     },
     {
      "worker": 7,
      "segment_start": 8321499136,
      "segment_end": 8589934592,
      "bytes_returned": 268435456,
      "wall_ms": 27.7203,
      "gbps": 9.6837,
      "block_count": 1,
      "first_block_wall_ms": 27.6345,
      "block_timings_ms": [
       27.6345
      ],
      "block_gbps": [
       9.7138
      ]
     }
    ],
    "first_range_latency_ms": 17.7,
    "tail_spread_ms": 29.0162,
    "process_cpu_ms": 370.0,
    "thread_cpu_ms": 140.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 18008473600,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 172.59,
    "gbps_per_cpu_core": 5.804,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 20.0851,
     "gbps": 13.3649
    },
    "verify": {
     "regions": [
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589672448,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 15
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "dynamic",
    "window_start": 8589934592,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 91.4238,
    "aggregate_gbps": 23.4893,
    "steady_state_gbps": null,
    "per_worker": [
     {
      "worker": 0,
      "schedule": "dynamic",
      "bytes_returned": 402653184,
      "wall_ms": 84.5525,
      "gbps": 4.7622,
      "block_count": 6,
      "first_block_wall_ms": 4.4802
     },
     {
      "worker": 1,
      "schedule": "dynamic",
      "bytes_returned": 469762048,
      "wall_ms": 85.5875,
      "gbps": 5.4887,
      "block_count": 7,
      "first_block_wall_ms": 7.5499
     },
     {
      "worker": 2,
      "schedule": "dynamic",
      "bytes_returned": 335544320,
      "wall_ms": 71.1894,
      "gbps": 4.7134,
      "block_count": 5,
      "first_block_wall_ms": 7.0062
     },
     {
      "worker": 3,
      "schedule": "dynamic",
      "bytes_returned": 402653184,
      "wall_ms": 64.3918,
      "gbps": 6.2532,
      "block_count": 6,
      "first_block_wall_ms": 8.0372
     },
     {
      "worker": 4,
      "schedule": "dynamic",
      "bytes_returned": 335544320,
      "wall_ms": 56.4287,
      "gbps": 5.9463,
      "block_count": 5,
      "first_block_wall_ms": 7.1231
     },
     {
      "worker": 5,
      "schedule": "dynamic",
      "bytes_returned": 134217728,
      "wall_ms": 49.3306,
      "gbps": 2.7208,
      "block_count": 2,
      "first_block_wall_ms": 11.2793
     },
     {
      "worker": 6,
      "schedule": "dynamic",
      "bytes_returned": 67108864,
      "wall_ms": 46.8363,
      "gbps": 1.4328,
      "block_count": 1,
      "first_block_wall_ms": 13.5334
     },
     {
      "worker": 7,
      "schedule": "dynamic",
      "bytes_returned": 0,
      "wall_ms": 0.0016,
      "gbps": 0.0,
      "block_count": 0,
      "first_block_wall_ms": 0.0
     }
    ],
    "first_range_latency_ms": 0.0,
    "tail_spread_ms": 85.5859,
    "process_cpu_ms": 270.0,
    "thread_cpu_ms": 40.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134377472,
    "peak_rss_bytes": 18008473600,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 295.33,
    "gbps_per_cpu_core": 7.9536,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 28.6762,
     "gbps": 9.3609
    },
    "verify": {
     "regions": [
      {
       "rel_start": 8589934592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737156096,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 16
   }
  ],
  "fullfile_qd16_included": true,
  "fullfile_warm_qd1_control": {
   "kind": "raw_qd",
   "qd": 1,
   "worker_count": 1,
   "block_mib": 32,
   "syscall_bytes": 33554432,
   "schedule": "static",
   "window_start": 0,
   "window_len": 12309817472,
   "status": "ok",
   "bytes_returned": 12309817472,
   "expected_bytes": 12309817472,
   "total_wall_ms": 1082.0423,
   "aggregate_gbps": 11.3765,
   "steady_state_gbps": 11.6972,
   "per_worker": [
    {
     "worker": 0,
     "segment_start": 0,
     "segment_end": 12309817472,
     "bytes_returned": 12309817472,
     "wall_ms": 1081.1553,
     "gbps": 11.3858,
     "block_count": 367,
     "first_block_wall_ms": 3.1597,
     "block_timings_ms": [
      3.1597,
      2.5934,
      2.0011,
      2.0168,
      1.9563,
      1.8377,
      1.8801,
      1.4662,
      3.6192,
      3.4762,
      2.9859,
      2.8805,
      2.8856,
      2.7998,
      2.5471,
      2.3761,
      2.5147,
      2.4555,
      2.4974,
      2.4789,
      2.4222,
      2.27,
      2.2121,
      2.3294,
      2.3009,
      2.339,
      2.2786,
      2.5318,
      2.2621,
      2.268,
      2.4453,
      2.6167,
      2.6043,
      2.3705,
      2.5943,
      2.3384,
      2.3154,
      2.8916,
      2.9803,
      2.5242,
      2.4281,
      3.8178,
      3.05,
      2.8984,
      2.8023,
      2.9821,
      2.635,
      2.4747,
      2.4049,
      2.6636,
      3.3282,
      3.1881,
      2.6136,
      2.5626,
      2.5565,
      2.4582,
      2.3249,
      2.4875,
      2.7953,
      2.4876,
      3.5,
      3.4387,
      3.201,
      3.1286,
      2.9412,
      3.4317,
      3.4378,
      3.512,
      3.0055,
      3.1341,
      2.736,
      2.6401,
      3.0863,
      3.3604,
      3.733,
      3.0324,
      2.8574,
      3.244,
      2.7105,
      2.7754,
      2.5982,
      2.6051,
      2.8631,
      2.834,
      2.6269,
      2.7278,
      2.575,
      2.5333,
      2.5309,
      2.4609,
      2.4494,
      2.4664,
      2.5122,
      2.5244,
      2.8967,
      2.6363,
      3.3399,
      3.0628,
      2.9674,
      2.7629,
      3.4591,
      3.3342,
      3.2413,
      3.2965,
      3.1733,
      3.2829,
      3.4554,
      3.0368,
      3.1212,
      2.884,
      3.6866,
      3.1278,
      3.0699,
      3.6178,
      3.6398,
      3.3806,
      3.4686,
      3.3506,
      3.1579,
      3.055,
      3.17,
      3.1584,
      2.7331,
      3.2954,
      2.848,
      2.9312,
      2.748,
      2.7397,
      2.7164,
      2.7043,
      3.1035,
      2.9234,
      2.854,
      2.6022,
      2.7645,
      2.6494,
      2.6326,
      2.5282,
      2.4644,
      2.5456,
      2.5911,
      3.3952,
      3.4471,
      3.9957,
      3.3856,
      2.7321,
      2.6924,
      2.7181,
      2.62,
      2.7661,
      2.9988,
      3.3421,
      3.423,
      3.6655,
      3.6892,
      3.6001,
      3.6822,
      3.5757,
      3.2873,
      2.9003,
      3.0673,
      2.807,
      2.6209,
      3.539,
      3.7797,
      3.4211,
      3.4082,
      3.1371,
      2.9734,
      2.9581,
      3.3196,
      3.237,
      2.9672,
      2.9329,
      3.5372,
      3.4075,
      3.0709,
      2.8936,
      2.8318,
      2.7916,
      2.8117,
      3.5205,
      4.1661,
      3.0986,
      3.3351,
      3.4563,
      3.2916,
      3.0086,
      3.1244,
      2.8576,
      2.9504,
      3.5562,
      3.5063,
      3.7062,
      3.1673,
      3.0839,
      3.2417,
      3.3861,
      3.4463,
      3.3698,
      3.0857,
      2.8943,
      2.5113,
      2.4049,
      2.2129,
      2.3784,
      2.4671,
      2.3762,
      2.3327,
      2.3054,
      2.3529,
      2.4972,
      2.6047,
      2.6234,
      2.7111,
      2.465,
      2.4801,
      2.5021,
      2.4408,
      2.4454,
      2.413,
      3.1166,
      3.1897,
      3.0826,
      2.9956,
      2.7695,
      2.5819,
      2.5969,
      3.3103,
      3.1673,
      3.0853,
      3.1868,
      3.3136,
      3.0054,
      2.6416,
      2.5798,
      2.5029,
      2.4194,
      2.4396,
      2.77,
      2.5188,
      2.4361,
      2.5635,
      2.3549,
      2.553,
      2.4122,
      2.4893,
      3.4172,
      3.1391,
      3.0896,
      3.1387,
      3.0375,
      2.9677,
      2.7858,
      3.3162,
      3.4989,
      3.0718,
      3.1855,
      3.0266,
      2.8549,
      2.8057,
      3.6786,
      4.2256,
      3.4382,
      3.0391,
      2.9279,
      3.0275,
      2.6077,
      2.6874,
      2.5117,
      2.752,
      2.6406,
      2.5119,
      2.661,
      2.709,
      2.6646,
      2.648,
      2.6471,
      2.6845,
      3.4603,
      3.2225,
      3.0427,
      2.8972,
      3.0619,
      2.9661,
      2.9284,
      3.312,
      2.6509,
      2.6322,
      2.6777,
      3.2771,
      2.6264,
      2.4822,
      2.4939,
      2.961,
      2.7591,
      2.7105,
      2.6679,
      3.1399,
      3.0414,
      3.0123,
      2.8877,
      2.6489,
      2.5316,
      2.471,
      2.9004,
      3.1628,
      2.754,
      2.6479,
      3.1255,
      2.8156,
      2.8686,
      2.9476,
      2.5275,
      2.4226,
      2.3653,
      2.3971,
      2.3827,
      2.428,
      2.3724,
      2.4022,
      2.3994,
      2.528,
      2.582,
      2.5624,
      2.9943,
      2.8327,
      2.7537,
      3.0017,
      3.3082,
      3.449,
      3.2604,
      3.226,
      3.029,
      2.665,
      2.6641,
      2.7948,
      2.7094,
      2.6119,
      2.7136,
      2.731,
      2.717,
      2.7669,
      3.5746,
      4.5502,
      3.6629,
      3.6321,
      5.7589,
      3.9525,
      3.9712,
      4.5723,
      3.2996,
      4.8015,
      2.9635,
      3.5536,
      3.2329,
      2.7725,
      2.9201,
      3.3955,
      2.8608,
      3.838,
      3.7277,
      3.3499,
      3.7756,
      2.91,
      3.2602,
      2.8882
     ],
     "block_gbps": [
      10.6196,
      12.9382,
      16.7677,
      16.6374,
      17.1519,
      18.2594,
      17.8469,
      22.8845,
      9.2713,
      9.6527,
      11.2375,
      11.649,
      11.6284,
      11.9846,
      13.1734,
      14.1213,
      13.3433,
      13.6648,
      13.4357,
      13.5359,
      13.8529,
      14.7816,
      15.1689,
      14.4044,
      14.5832,
      14.3453,
      14.7262,
      13.2534,
      14.8335,
      14.7949,
      13.7222,
      12.8231,
      12.8841,
      14.1549,
      12.934,
      14.349,
      14.4917,
      11.6039,
      11.2589,
      13.2929,
      13.8193,
      8.789,
      11.0013,
      11.577,
      11.9738,
      11.2518,
      12.7343,
      13.5589,
      13.9525,
      12.5975,
      10.0819,
      10.5247,
      12.8384,
      13.0939,
      13.125,
      13.6503,
      14.4326,
      13.4894,
      12.0038,
      13.4887,
      9.587,
      9.7577,
      10.4824,
      10.725,
      11.4085,
      9.7779,
      9.7605,
      9.5543,
      11.1642,
      10.7063,
      12.264,
      12.7093,
      10.8722,
      9.9852,
      8.9885,
      11.0653,
      11.7428,
      10.3435,
      12.3795,
      12.0901,
      12.9146,
      12.8801,
      11.7196,
      11.8401,
      12.7733,
      12.3007,
      13.0307,
      13.2452,
      13.258,
      13.6349,
      13.699,
      13.6045,
      13.3566,
      13.2921,
      11.5836,
      12.7276,
      10.0465,
      10.9556,
      11.3077,
      12.1448,
      9.7003,
      10.0638,
      10.3523,
      10.1788,
      10.5741,
      10.2211,
      9.7108,
      11.0494,
      10.7504,
      11.6347,
      9.1018,
      10.7279,
      10.9301,
      9.2749,
      9.2186,
      9.9254,
      9.6738,
      10.0145,
      10.6256,
      10.9834,
      10.585,
      10.6237,
      12.277,
      10.1821,
      11.7818,
      11.4472,
      12.2106,
      12.2473,
      12.3528,
      12.4078,
      10.8119,
      11.4778,
      11.7571,
      12.8946,
      12.1376,
      12.6647,
      12.7459,
      13.2723,
      13.6157,
      13.1813,
      12.9501,
      9.883,
      9.7342,
      8.3977,
      9.9108,
      12.2816,
      12.4625,
      12.3448,
      12.8069,
      12.1305,
      11.1893,
      10.04,
      9.8027,
      9.1541,
      9.0953,
      9.3203,
      9.1127,
      9.3839,
      10.2072,
      11.5691,
      10.9395,
      11.9539,
      12.8024,
      9.4813,
      8.8774,
      9.8082,
      9.8453,
      10.6961,
      11.2848,
      11.3433,
      10.1081,
      10.366,
      11.3083,
      11.4407,
      9.486,
      9.8471,
      10.9266,
      11.5962,
      11.8493,
      12.0196,
      11.9337,
      9.5312,
      8.0542,
      10.8289,
      10.0611,
      9.7083,
      10.194,
      11.1529,
      10.7395,
      11.7423,
      11.3728,
      9.4353,
      9.5697,
      9.0535,
      10.5941,
      10.8804,
      10.3507,
      9.9096,
      9.7363,
      9.9573,
      10.8743,
      11.5933,
      13.3613,
      13.9523,
      15.1632,
      14.1077,
      13.6009,
      14.1208,
      14.3843,
      14.5544,
      14.2612,
      13.4366,
      12.8825,
      12.7906,
      12.3767,
      13.6123,
      13.5295,
      13.4107,
      13.7475,
      13.7213,
      13.9058,
      10.7664,
      10.5195,
      10.8851,
      11.2014,
      12.1155,
      12.9959,
      12.9208,
      10.1363,
      10.5939,
      10.8754,
      10.5292,
      10.1262,
      11.1646,
      12.7023,
      13.0068,
      13.4062,
      13.869,
      13.7539,
      12.1133,
      13.3218,
      13.7738,
      13.0894,
      14.249,
      13.1433,
      13.9103,
      13.4794,
      9.8194,
      10.6891,
      10.8606,
      10.6906,
      11.0467,
      11.3066,
      12.045,
      10.1185,
      9.59,
      10.9233,
      10.5336,
      11.0865,
      11.7534,
      11.9593,
      9.1215,
      7.9407,
      9.7594,
      11.0409,
      11.4602,
      11.0833,
      12.8675,
      12.4858,
      13.3591,
      12.1925,
      12.7071,
      13.3585,
      12.6098,
      12.3862,
      12.5927,
      12.6714,
      12.6761,
      12.4993,
      9.6969,
      10.4127,
      11.028,
      11.5815,
      10.9586,
      11.3128,
      11.4584,
      10.1312,
      12.6577,
      12.7475,
      12.531,
      10.2391,
      12.7756,
      13.5181,
      13.4548,
      11.3322,
      12.1612,
      12.3795,
      12.5773,
      10.6863,
      11.0324,
      11.1392,
      11.6197,
      12.6671,
      13.2543,
      13.5793,
      11.569,
      10.6091,
      12.1838,
      12.6723,
      10.7358,
      11.9175,
      11.6972,
      11.3836,
      13.2758,
      13.8508,
      14.1862,
      13.9977,
      14.0823,
      13.8197,
      14.1438,
      13.9679,
      13.9844,
      13.2731,
      12.9955,
      13.0949,
      11.2063,
      11.8452,
      12.1854,
      11.1786,
      10.1429,
      9.7289,
      10.2915,
      10.4011,
      11.0777,
      12.5907,
      12.5948,
      12.0061,
      12.3845,
      12.8468,
      12.3652,
      12.2864,
      12.3497,
      12.1272,
      9.3868,
      7.3743,
      9.1607,
      9.2383,
      5.8265,
      8.4894,
      8.4495,
      7.3386,
      10.1694,
      6.9883,
      11.3224,
      9.4424,
      10.379,
      12.1026,
      11.4907,
      9.8821,
      11.7291,
      8.7427,
      9.0013,
      10.0167,
      8.8873,
      11.5307,
      10.2922,
      10.0047
     ]
    }
   ],
   "first_range_latency_ms": 3.1597,
   "tail_spread_ms": 0.0,
   "process_cpu_ms": 160.0,
   "thread_cpu_ms": 30.0,
   "minflt_delta": 0,
   "majflt_delta": 0,
   "ctxt_switches_delta": null,
   "rss_delta_bytes": 0,
   "peak_rss_bytes": 18588893184,
   "peak_pinned_bytes": 0,
   "cpu_cores": 28,
   "cpu_utilization_pct": 14.79,
   "gbps_per_cpu_core": 76.9366,
   "warm_repeat": {
    "bytes": 268435456,
    "wall_ms": 18.2201,
    "gbps": 14.7329
   },
   "verify": {
    "regions": [
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 12309555328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536608768,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536870912,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073479680,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073741824,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610350592,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610612736,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147221504,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147483648,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684092416,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684354560,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3220963328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3221225472,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3757834240,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3758096384,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294705152,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294967296,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831576064,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831838208,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368446976,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368709120,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905317888,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905580032,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442188800,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442450944,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979059712,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979321856,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 7515930624,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 7516192768,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8052801536,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8053063680,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8589672448,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8589934592,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9126543360,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9126805504,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9663414272,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 9663676416,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10200285184,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10200547328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10737156096,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 10737418240,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 11274027008,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 11274289152,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 11810897920,
      "bytes": 262144,
      "hash_match": true
     }
    ],
    "all_match": true
   }
  },
  "fullfile": [
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 12309817472,
    "status": "ok",
    "bytes_returned": 12309817472,
    "expected_bytes": 12309817472,
    "total_wall_ms": 534.2029,
    "aggregate_gbps": 23.0433,
    "steady_state_gbps": 12.019,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 6154908736,
      "bytes_returned": 6154908736,
      "wall_ms": 519.5117,
      "gbps": 11.8475,
      "block_count": 184,
      "first_block_wall_ms": 3.1204,
      "block_timings_ms": [
       3.1204,
       3.5389,
       3.5294,
       3.1042,
       2.7841,
       2.7743,
       3.4189,
       3.5965,
       3.6529,
       3.3957,
       3.6355,
       3.4388,
       3.2331,
       2.6425,
       2.6759,
       2.5407,
       2.7978,
       2.7088,
       2.5365,
       2.9884,
       2.6645,
       2.6749,
       2.6841,
       2.6129,
       2.7201,
       2.7844,
       2.862,
       3.3057,
       2.8544,
       2.8464,
       2.9681,
       2.6236,
       2.7542,
       2.789,
       2.7632,
       2.7926,
       2.7753,
       2.5715,
       3.2757,
       2.7184,
       2.6098,
       2.6275,
       2.6782,
       2.6693,
       2.6464,
       2.4723,
       2.5435,
       2.4898,
       2.462,
       2.7312,
       2.6163,
       3.3407,
       2.7046,
       2.6298,
       2.6638,
       2.6842,
       2.5902,
       2.7058,
       2.831,
       3.0981,
       3.1749,
       3.1405,
       2.8308,
       3.0709,
       2.7604,
       2.9679,
       2.6651,
       2.4718,
       2.9935,
       3.5772,
       3.1606,
       3.2624,
       3.51,
       3.2506,
       3.189,
       3.0353,
       2.9098,
       3.0138,
       2.966,
       2.7137,
       2.6623,
       2.7255,
       2.8175,
       3.0326,
       2.8784,
       3.2245,
       2.9686,
       2.8209,
       3.1123,
       2.8637,
       2.9407,
       2.8304,
       2.7906,
       2.771,
       2.7029,
       2.555,
       3.078,
       3.0539,
       3.1291,
       3.3823,
       3.1399,
       3.5368,
       3.704,
       3.1838,
       3.0856,
       3.1923,
       2.9071,
       2.6445,
       3.4557,
       3.7155,
       3.2494,
       2.8847,
       2.7387,
       2.7541,
       2.5313,
       2.2083,
       2.2176,
       2.2401,
       2.2132,
       2.3928,
       2.483,
       2.4952,
       2.2851,
       2.307,
       2.2454,
       2.2744,
       2.2314,
       2.0944,
       2.0376,
       2.091,
       2.363,
       2.3625,
       2.2696,
       3.47,
       2.8838,
       3.0924,
       2.9676,
       3.0091,
       2.6485,
       2.269,
       2.7521,
       3.38,
       3.6423,
       3.9155,
       3.0595,
       2.8301,
       2.9694,
       2.8134,
       2.4769,
       2.3283,
       2.4806,
       2.5805,
       2.4812,
       2.5065,
       2.5592,
       2.5756,
       2.5971,
       2.7249,
       2.7398,
       2.5195,
       2.6585,
       2.5794,
       2.5922,
       2.6631,
       2.6783,
       2.626,
       2.6932,
       2.6292,
       2.5658,
       2.7022,
       2.7014,
       2.7419,
       2.5553,
       2.6179,
       2.6261,
       2.5893,
       2.5141,
       2.5794,
       2.6573,
       2.6404,
       2.7546,
       2.6583,
       2.8223,
       1.1771
      ],
      "block_gbps": [
       10.7534,
       9.4817,
       9.5072,
       10.8094,
       12.0523,
       12.0947,
       9.8145,
       9.3297,
       9.1856,
       9.8815,
       9.2296,
       9.7577,
       10.3784,
       12.6981,
       12.5394,
       13.2066,
       11.993,
       12.3873,
       13.2286,
       11.2282,
       12.593,
       12.5441,
       12.501,
       12.8421,
       12.3358,
       12.0507,
       11.7239,
       10.1504,
       11.7552,
       11.7883,
       11.305,
       12.7893,
       12.183,
       12.0308,
       12.1435,
       12.0155,
       12.0904,
       13.0487,
       10.2434,
       12.3434,
       12.8573,
       12.7704,
       12.5289,
       12.5704,
       12.6791,
       13.572,
       13.1924,
       13.4765,
       13.6291,
       12.2858,
       12.8249,
       10.0441,
       12.4066,
       12.7591,
       12.5965,
       12.5008,
       12.9542,
       12.401,
       11.8526,
       10.8306,
       10.5686,
       10.6844,
       11.8533,
       10.9267,
       12.1557,
       11.3057,
       12.5905,
       13.5747,
       11.2092,
       9.3802,
       10.6164,
       10.2851,
       9.5598,
       10.3227,
       10.522,
       11.0548,
       11.5316,
       11.1335,
       11.3129,
       12.3647,
       12.6036,
       12.3113,
       11.9092,
       11.0644,
       11.6574,
       10.406,
       11.3033,
       11.8948,
       10.7812,
       11.717,
       11.4103,
       11.855,
       12.0241,
       12.1091,
       12.414,
       13.1331,
       10.9015,
       10.9875,
       10.7234,
       9.9206,
       10.6865,
       9.4873,
       9.059,
       10.5391,
       10.8745,
       10.5112,
       11.5424,
       12.6881,
       9.71,
       9.0309,
       10.3263,
       11.632,
       12.2518,
       12.1836,
       13.2558,
       15.1944,
       15.1308,
       14.9787,
       15.1608,
       14.023,
       13.5135,
       13.4474,
       14.6837,
       14.5449,
       14.9435,
       14.7529,
       15.0375,
       16.021,
       16.4678,
       16.0472,
       14.2001,
       14.203,
       14.7844,
       9.6699,
       11.6353,
       10.8504,
       11.3068,
       11.1511,
       12.6692,
       14.7879,
       12.1925,
       9.9275,
       9.2123,
       8.5697,
       10.9674,
       11.8564,
       11.2999,
       11.9266,
       13.5471,
       14.4117,
       13.5268,
       13.0029,
       13.5233,
       13.3872,
       13.1113,
       13.0276,
       12.9198,
       12.3139,
       12.2471,
       13.3181,
       12.6217,
       13.0086,
       12.9446,
       12.5995,
       12.5285,
       12.778,
       12.4588,
       12.762,
       13.0774,
       12.4173,
       12.4211,
       12.2378,
       13.1314,
       12.8172,
       12.7772,
       12.9586,
       13.3463,
       13.0087,
       12.6272,
       12.7081,
       12.1811,
       12.6226,
       11.8891,
       12.2743
      ]
     },
     {
      "worker": 1,
      "segment_start": 6154908736,
      "segment_end": 12309817472,
      "bytes_returned": 6154908736,
      "wall_ms": 530.057,
      "gbps": 11.6118,
      "block_count": 184,
      "first_block_wall_ms": 3.5928,
      "block_timings_ms": [
       3.5928,
       3.4349,
       3.3058,
       3.012,
       2.8883,
       2.9388,
       3.6153,
       3.2789,
       3.4365,
       2.6179,
       2.3636,
       2.2974,
       2.258,
       2.0773,
       2.2564,
       2.0842,
       2.2554,
       2.2997,
       2.2736,
       2.6916,
       2.7869,
       2.5528,
       2.4231,
       2.3499,
       2.2974,
       2.3578,
       2.4221,
       2.4342,
       3.0357,
       2.9631,
       3.1989,
       2.9699,
       2.6384,
       3.0941,
       2.9498,
       2.8802,
       2.8006,
       2.7918,
       2.637,
       2.4564,
       2.5042,
       3.6577,
       3.4129,
       3.2708,
       3.1927,
       2.9841,
       2.9276,
       2.8307,
       3.172,
       2.7398,
       2.727,
       2.5715,
       2.5954,
       2.5814,
       2.6542,
       2.7286,
       2.6643,
       2.3671,
       2.7045,
       2.6351,
       3.0069,
       2.9305,
       2.9989,
       2.8423,
       2.9438,
       2.7711,
       2.8356,
       2.9883,
       2.7355,
       3.1557,
       2.8448,
       3.0985,
       3.0725,
       2.7739,
       3.4495,
       2.8041,
       2.6367,
       2.9602,
       3.1868,
       3.7057,
       2.9204,
       2.795,
       3.1087,
       2.8461,
       2.9349,
       2.8232,
       2.7614,
       3.2519,
       2.7301,
       2.9628,
       2.9569,
       2.9126,
       3.297,
       2.9198,
       3.2885,
       3.2684,
       2.9009,
       2.8287,
       2.8385,
       2.6706,
       2.8168,
       2.6209,
       2.4703,
       2.3653,
       2.4903,
       2.5452,
       2.5357,
       2.7698,
       2.7648,
       2.803,
       2.7939,
       2.8541,
       2.914,
       2.8246,
       2.901,
       2.865,
       2.8087,
       2.809,
       2.7618,
       2.8212,
       2.6694,
       2.6462,
       2.6512,
       2.7824,
       2.7075,
       2.6644,
       2.6398,
       2.6629,
       2.7585,
       2.65,
       2.6001,
       2.6697,
       3.0094,
       2.8078,
       2.7427,
       2.6792,
       2.6116,
       2.541,
       2.9538,
       2.8336,
       2.7463,
       2.8026,
       2.7143,
       2.6601,
       2.7965,
       2.874,
       2.6692,
       2.7275,
       2.6143,
       2.8143,
       2.7217,
       2.6319,
       2.6781,
       3.1398,
       2.8362,
       3.3185,
       2.8451,
       3.6012,
       3.2668,
       3.1558,
       3.3487,
       3.1405,
       3.0485,
       3.6261,
       4.0157,
       3.0261,
       3.879,
       3.21,
       3.3205,
       3.2777,
       2.8482,
       3.0689,
       2.8913,
       3.3199,
       3.7246,
       3.6277,
       3.0033,
       3.2919,
       2.7561,
       3.3618,
       3.5153,
       2.97,
       2.8991,
       1.1074
      ],
      "block_gbps": [
       9.3394,
       9.7686,
       10.1502,
       11.1402,
       11.6173,
       11.4178,
       9.2812,
       10.2334,
       9.7642,
       12.8174,
       14.1963,
       14.6055,
       14.8602,
       16.1528,
       14.8708,
       16.0994,
       14.8776,
       14.5906,
       14.7581,
       12.4666,
       12.0401,
       13.1443,
       13.848,
       14.2789,
       14.6053,
       14.2313,
       13.8532,
       13.7846,
       11.0535,
       11.324,
       10.4895,
       11.2982,
       12.7178,
       10.8448,
       11.3753,
       11.6501,
       11.981,
       12.019,
       12.7243,
       13.66,
       13.3994,
       9.1736,
       9.8316,
       10.2588,
       10.5098,
       11.2442,
       11.4616,
       11.8539,
       10.5784,
       12.247,
       12.3047,
       13.0484,
       12.9284,
       12.9985,
       12.6422,
       12.2973,
       12.594,
       14.1756,
       12.4069,
       12.7335,
       11.1592,
       11.45,
       11.1889,
       11.8053,
       11.3985,
       12.1088,
       11.8332,
       11.2286,
       12.2661,
       10.6329,
       11.7948,
       10.8293,
       10.9209,
       12.0966,
       9.7273,
       11.9661,
       12.7257,
       11.3353,
       10.5292,
       9.0548,
       11.4895,
       12.0052,
       10.7939,
       11.7897,
       11.4331,
       11.8851,
       12.1515,
       10.3184,
       12.2907,
       11.3253,
       11.3479,
       11.5204,
       10.1773,
       11.492,
       10.2034,
       10.2663,
       11.5669,
       11.8623,
       11.8214,
       12.5641,
       11.9122,
       12.8024,
       13.583,
       14.1862,
       13.4738,
       13.1833,
       13.2328,
       12.1144,
       12.1363,
       11.9709,
       12.0098,
       11.7567,
       11.5151,
       11.8794,
       11.5665,
       11.7118,
       11.9467,
       11.9455,
       12.1494,
       11.8935,
       12.5701,
       12.68,
       12.6565,
       12.0595,
       12.393,
       12.5938,
       12.7109,
       12.6006,
       12.1638,
       12.6618,
       12.9051,
       12.5685,
       11.1501,
       11.9505,
       12.234,
       12.5238,
       12.8482,
       13.2052,
       11.3596,
       11.8415,
       12.2182,
       11.9725,
       12.3619,
       12.6141,
       11.9989,
       11.6751,
       12.5711,
       12.3022,
       12.8349,
       11.9228,
       12.3284,
       12.7493,
       12.5294,
       10.687,
       11.8309,
       10.1113,
       11.7938,
       9.3175,
       10.2715,
       10.6328,
       10.0202,
       10.6843,
       11.007,
       9.2536,
       8.3558,
       11.0885,
       8.6502,
       10.4532,
       10.1053,
       10.2371,
       11.781,
       10.9337,
       11.6051,
       10.107,
       9.009,
       9.2496,
       11.1726,
       10.1931,
       12.1746,
       9.981,
       9.5453,
       11.2976,
       11.5739,
       13.0465
      ]
     }
    ],
    "first_range_latency_ms": 3.1204,
    "tail_spread_ms": 10.5453,
    "process_cpu_ms": 60.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 18142851072,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 11.23,
    "gbps_per_cpu_core": 205.1633,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 22.4045,
     "gbps": 11.9813
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 12309555328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7516192768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8052801536,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8053063680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589672448,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589934592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126543360,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126805504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663414272,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663676416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200285184,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200547328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737156096,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737418240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274027008,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274289152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11810897920,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 12309817472,
    "status": "ok",
    "bytes_returned": 12309817472,
    "expected_bytes": 12309817472,
    "total_wall_ms": 283.2961,
    "aggregate_gbps": 43.4521,
    "steady_state_gbps": 12.3977,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 3077454368,
      "bytes_returned": 3077454368,
      "wall_ms": 247.171,
      "gbps": 12.4507,
      "block_count": 92,
      "first_block_wall_ms": 3.8703,
      "block_timings_ms": [
       3.8703,
       8.4633,
       3.2287,
       2.7816,
       2.8957,
       3.2025,
       2.8173,
       2.8978,
       2.6782,
       2.7246,
       2.3662,
       2.0681,
       2.106,
       2.2735,
       2.1129,
       2.1531,
       2.3198,
       2.2435,
       2.2723,
       2.1445,
       2.1577,
       2.1374,
       2.0455,
       2.0042,
       2.0168,
       1.9774,
       1.9281,
       2.3016,
       2.0667,
       2.078,
       2.2446,
       2.0518,
       2.101,
       2.0399,
       2.064,
       2.0465,
       2.1625,
       2.3515,
       2.3906,
       2.1139,
       2.1761,
       2.1335,
       1.9579,
       2.0606,
       4.8442,
       2.9074,
       2.7442,
       2.7405,
       2.7399,
       2.8595,
       3.6414,
       3.9061,
       3.1844,
       2.8512,
       2.7759,
       2.5432,
       2.8985,
       2.641,
       2.8873,
       2.6146,
       2.5657,
       2.4608,
       2.4063,
       2.3134,
       2.3268,
       2.3216,
       2.368,
       2.4055,
       2.3235,
       2.5219,
       2.4294,
       2.56,
       2.9838,
       2.5308,
       2.7299,
       2.6719,
       2.6945,
       2.8682,
       2.5954,
       2.6035,
       3.7711,
       3.5988,
       3.9412,
       3.5582,
       3.3133,
       3.6844,
       3.0314,
       2.9972,
       2.705,
       2.6856,
       2.5926,
       1.8558
      ],
      "block_gbps": [
       8.6697,
       3.9647,
       10.3925,
       12.0628,
       11.5876,
       10.4775,
       11.9102,
       11.5794,
       12.5289,
       12.3152,
       14.1808,
       16.2247,
       15.933,
       14.7589,
       15.8804,
       15.5845,
       14.4642,
       14.9562,
       14.7665,
       15.6469,
       15.5507,
       15.699,
       16.4043,
       16.7418,
       16.637,
       16.9691,
       17.4031,
       14.5785,
       16.2356,
       16.1474,
       14.9491,
       16.3534,
       15.971,
       16.4488,
       16.2567,
       16.396,
       15.5162,
       14.2691,
       14.0358,
       15.8735,
       15.4197,
       15.7276,
       17.1381,
       16.2841,
       6.9267,
       11.541,
       12.2276,
       12.2439,
       12.2465,
       11.7345,
       9.2147,
       8.5904,
       10.5372,
       11.7685,
       12.0878,
       13.1938,
       11.5765,
       12.7054,
       11.6216,
       12.8337,
       13.078,
       13.6357,
       13.9443,
       14.5043,
       14.4208,
       14.4531,
       14.1697,
       13.9489,
       14.441,
       13.3052,
       13.8117,
       13.1074,
       11.2457,
       13.2585,
       12.2914,
       12.5585,
       12.453,
       11.6988,
       12.9282,
       12.8884,
       8.8979,
       9.3238,
       8.5137,
       9.4302,
       10.1273,
       9.1072,
       11.069,
       11.1951,
       12.4046,
       12.4941,
       12.9422,
       12.9329
      ]
     },
     {
      "worker": 1,
      "segment_start": 3077454368,
      "segment_end": 6154908736,
      "bytes_returned": 3077454368,
      "wall_ms": 262.2439,
      "gbps": 11.7351,
      "block_count": 92,
      "first_block_wall_ms": 4.6149,
      "block_timings_ms": [
       4.6149,
       3.5463,
       4.3913,
       4.2711,
       3.3984,
       3.2715,
       3.1285,
       2.6951,
       2.6332,
       2.8666,
       3.613,
       3.2499,
       2.9631,
       3.0091,
       2.7424,
       2.6713,
       2.7018,
       3.4533,
       2.9009,
       3.0717,
       3.084,
       3.2599,
       3.2713,
       3.0634,
       3.1867,
       3.0064,
       2.9123,
       2.9562,
       2.8464,
       2.6242,
       2.7402,
       2.7167,
       2.7748,
       2.8421,
       2.7886,
       2.6216,
       2.6416,
       2.5651,
       3.1277,
       2.6287,
       2.4457,
       2.5516,
       2.4715,
       2.9459,
       2.819,
       2.6296,
       2.6788,
       2.8674,
       3.2266,
       3.5003,
       2.795,
       2.844,
       2.5837,
       2.4238,
       2.5908,
       2.2079,
       2.319,
       2.2249,
       2.0442,
       2.3668,
       2.2791,
       2.4528,
       2.3028,
       2.4341,
       2.3783,
       2.2887,
       2.4023,
       2.2393,
       2.1734,
       2.2332,
       2.2395,
       2.2513,
       3.4642,
       2.787,
       2.5408,
       2.6748,
       2.5623,
       2.7747,
       3.138,
       2.9962,
       2.6915,
       2.5328,
       2.5087,
       2.3618,
       2.4114,
       2.4369,
       2.9898,
       3.3169,
       4.1273,
       3.5908,
       3.1019,
       2.3337
      ],
      "block_gbps": [
       7.2709,
       9.4619,
       7.6412,
       7.8562,
       9.8737,
       10.2567,
       10.7252,
       12.4503,
       12.7429,
       11.7054,
       9.2872,
       10.3249,
       11.324,
       11.151,
       12.2355,
       12.5609,
       12.4194,
       9.7167,
       11.5669,
       10.9238,
       10.8803,
       10.2931,
       10.2571,
       10.9532,
       10.5296,
       11.1612,
       11.5217,
       11.3504,
       11.7882,
       12.7866,
       12.2454,
       12.3509,
       12.0926,
       11.8063,
       12.0326,
       12.799,
       12.7024,
       13.0813,
       10.7282,
       12.7649,
       13.7197,
       13.1505,
       13.5763,
       11.3903,
       11.9031,
       12.7604,
       12.5257,
       11.7019,
       10.3994,
       9.5863,
       12.005,
       11.7984,
       12.9872,
       13.8439,
       12.9515,
       15.1973,
       14.4695,
       15.0813,
       16.4149,
       14.177,
       14.7229,
       13.6801,
       14.571,
       13.7851,
       14.1085,
       14.6609,
       13.9674,
       14.9846,
       15.4389,
       15.025,
       14.9833,
       14.9045,
       9.6861,
       12.0395,
       13.2064,
       12.5446,
       13.0955,
       12.0931,
       10.6931,
       11.1991,
       12.467,
       13.2481,
       13.3754,
       14.2073,
       13.9147,
       13.7691,
       11.2231,
       10.1163,
       8.1299,
       9.3446,
       10.8173,
       10.2845
      ]
     },
     {
      "worker": 2,
      "segment_start": 6154908736,
      "segment_end": 9232363104,
      "bytes_returned": 3077454368,
      "wall_ms": 273.461,
      "gbps": 11.2537,
      "block_count": 92,
      "first_block_wall_ms": 3.1829,
      "block_timings_ms": [
       3.1829,
       2.111,
       1.8583,
       1.6905,
       1.5516,
       1.8786,
       3.5058,
       2.938,
       3.3639,
       2.9146,
       3.1263,
       2.8038,
       2.7465,
       2.5383,
       2.9995,
       2.5911,
       2.7509,
       2.647,
       2.4766,
       3.0419,
       3.054,
       3.0337,
       3.1148,
       3.108,
       3.2647,
       3.1545,
       3.1138,
       3.1088,
       3.4588,
       3.3877,
       3.6086,
       3.2577,
       3.0965,
       3.1061,
       3.1625,
       3.3449,
       3.3013,
       3.3037,
       3.1997,
       2.9724,
       2.8769,
       2.8037,
       2.695,
       2.6068,
       2.9683,
       2.553,
       2.3353,
       2.8867,
       3.4534,
       2.9045,
       2.7307,
       2.5834,
       2.6281,
       2.4953,
       2.4873,
       2.761,
       2.8335,
       2.5832,
       2.7732,
       2.5286,
       2.3894,
       2.2898,
       2.2026,
       2.5673,
       2.4624,
       2.3945,
       2.5242,
       2.6716,
       2.4711,
       2.7411,
       2.5317,
       4.7556,
       4.3127,
       4.1629,
       4.5552,
       4.1082,
       3.9384,
       4.0129,
       3.8984,
       4.1748,
       2.8783,
       4.6891,
       3.4111,
       3.2361,
       3.0201,
       2.7673,
       3.2255,
       3.7982,
       2.887,
       2.2056,
       2.0007,
       1.3955
      ],
      "block_gbps": [
       10.542,
       15.8949,
       18.0564,
       19.8484,
       21.6251,
       17.8616,
       9.571,
       11.4207,
       9.9749,
       11.5125,
       10.7328,
       11.9673,
       12.2171,
       13.219,
       11.1869,
       12.95,
       12.1974,
       12.6762,
       13.5486,
       11.0306,
       10.9871,
       11.0607,
       10.7726,
       10.7963,
       10.2779,
       10.637,
       10.776,
       10.7935,
       9.7012,
       9.9048,
       9.2986,
       10.3001,
       10.8361,
       10.8026,
       10.6101,
       10.0316,
       10.164,
       10.1565,
       10.4868,
       11.2886,
       11.6636,
       11.9677,
       12.4509,
       12.872,
       11.3044,
       13.1433,
       14.3685,
       11.6239,
       9.7162,
       11.5526,
       12.2877,
       12.9885,
       12.7674,
       13.4471,
       13.4904,
       12.1531,
       11.8421,
       12.9895,
       12.0996,
       13.27,
       14.0431,
       14.6536,
       15.2339,
       13.0699,
       13.6267,
       14.0131,
       13.2932,
       12.5595,
       13.579,
       12.2413,
       13.2539,
       7.0557,
       7.7803,
       8.0604,
       7.3663,
       8.1677,
       8.5197,
       8.3616,
       8.6072,
       8.0373,
       11.6579,
       7.1559,
       9.8369,
       10.3687,
       11.1103,
       12.1255,
       10.4029,
       8.8344,
       11.6228,
       15.2131,
       16.7718,
       17.1989
      ]
     },
     {
      "worker": 3,
      "segment_start": 9232363104,
      "segment_end": 12309817472,
      "bytes_returned": 3077454368,
      "wall_ms": 249.1028,
      "gbps": 12.3542,
      "block_count": 92,
      "first_block_wall_ms": 3.1781,
      "block_timings_ms": [
       3.1781,
       3.1229,
       3.0722,
       2.4594,
       2.0453,
       2.3218,
       2.1809,
       2.2394,
       2.0866,
       1.9762,
       1.7414,
       1.753,
       3.6368,
       3.2491,
       3.0263,
       3.2185,
       3.4126,
       3.3753,
       3.2889,
       3.6263,
       3.5868,
       3.5215,
       3.5317,
       3.5155,
       3.6194,
       3.4441,
       3.4004,
       3.4316,
       3.2989,
       3.3748,
       3.4198,
       3.2827,
       3.6196,
       3.3689,
       3.0915,
       2.7216,
       2.7065,
       3.4112,
       2.6329,
       2.398,
       2.21,
       2.6535,
       2.4091,
       2.2434,
       2.219,
       2.2773,
       3.5236,
       3.6789,
       3.0393,
       2.3193,
       2.0794,
       2.0477,
       2.0921,
       2.2065,
       2.1593,
       2.0534,
       2.0696,
       2.1295,
       1.9762,
       2.1231,
       2.0241,
       1.6957,
       1.8267,
       2.0628,
       1.8981,
       1.9568,
       1.9597,
       1.8763,
       1.9159,
       2.7391,
       2.2487,
       2.6135,
       3.6446,
       2.5294,
       2.9418,
       2.9794,
       2.4032,
       2.9195,
       2.1224,
       2.9716,
       2.4542,
       2.2717,
       2.2582,
       2.3645,
       2.1609,
       2.235,
       2.1281,
       2.1408,
       3.4021,
       3.9704,
       4.2878,
       2.8471
      ],
      "block_gbps": [
       10.5579,
       10.7446,
       10.9218,
       13.6435,
       16.4053,
       14.4518,
       15.3855,
       14.9835,
       16.0805,
       16.9793,
       19.2685,
       19.141,
       9.2265,
       10.3274,
       11.0876,
       10.4255,
       9.8327,
       9.9413,
       10.2024,
       9.2529,
       9.355,
       9.5286,
       9.5008,
       9.5446,
       9.2707,
       9.7425,
       9.8678,
       9.778,
       10.1714,
       9.9426,
       9.8119,
       10.2217,
       9.2703,
       9.9602,
       10.8538,
       12.3291,
       12.3977,
       9.8366,
       12.7444,
       13.9928,
       15.1828,
       12.6455,
       13.928,
       14.9567,
       15.1214,
       14.7346,
       9.5227,
       9.1208,
       11.0403,
       14.4674,
       16.1365,
       16.3861,
       16.0383,
       15.2072,
       15.5391,
       16.3406,
       16.2131,
       15.7571,
       16.9788,
       15.8044,
       16.5774,
       19.788,
       18.3688,
       16.2667,
       17.6777,
       17.148,
       17.1222,
       17.883,
       17.5136,
       12.2502,
       14.922,
       12.839,
       9.2066,
       13.2659,
       11.406,
       11.2623,
       13.9626,
       11.4932,
       15.8097,
       11.2918,
       13.672,
       14.7703,
       14.8589,
       14.1912,
       15.528,
       15.0132,
       15.7676,
       15.6739,
       9.863,
       8.4511,
       7.8257,
       8.4299
      ]
     }
    ],
    "first_range_latency_ms": 3.1781,
    "tail_spread_ms": 26.29,
    "process_cpu_ms": 100.0,
    "thread_cpu_ms": 20.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 18152681472,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 35.3,
    "gbps_per_cpu_core": 123.0981,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.4504,
     "gbps": 14.549
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 12309555328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7516192768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8052801536,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8053063680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589672448,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589934592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126543360,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126805504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663414272,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663676416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200285184,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200547328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737156096,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737418240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274027008,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274289152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11810897920,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 12309817472,
    "status": "ok",
    "bytes_returned": 12309817472,
    "expected_bytes": 12309817472,
    "total_wall_ms": 248.1263,
    "aggregate_gbps": 49.6111,
    "steady_state_gbps": 10.4574,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 1538727184,
      "bytes_returned": 1538727184,
      "wall_ms": 233.6514,
      "gbps": 6.5856,
      "block_count": 46,
      "first_block_wall_ms": 4.037,
      "block_timings_ms": [
       4.037,
       5.0844,
       8.9271,
       4.4279,
       6.9897,
       19.4559,
       4.3714,
       8.1058,
       5.9215,
       4.7962,
       7.4268,
       8.1864,
       7.2638,
       6.7319,
       7.7313,
       7.7353,
       7.9284,
       2.9816,
       2.2166,
       2.7467,
       2.8004,
       2.9047,
       2.762,
       5.0316,
       5.3983,
       3.4943,
       3.2276,
       3.784,
       5.185,
       2.9209,
       3.2134,
       2.9135,
       2.7033,
       5.4321,
       3.2908,
       3.0061,
       2.7004,
       2.7733,
       5.3904,
       6.2695,
       5.8649,
       5.114,
       4.2961,
       3.2087,
       3.1356,
       2.3377
      ],
      "block_gbps": [
       8.3117,
       6.5995,
       3.7587,
       7.5779,
       4.8006,
       1.7246,
       7.6758,
       4.1396,
       5.6665,
       6.996,
       4.518,
       4.0988,
       4.6194,
       4.9844,
       4.3401,
       4.3378,
       4.2322,
       11.2539,
       15.138,
       12.2164,
       11.982,
       11.5518,
       12.1485,
       6.6688,
       6.2158,
       9.6027,
       10.3962,
       8.8675,
       6.4715,
       11.4877,
       10.4421,
       11.5168,
       12.4124,
       6.1771,
       10.1964,
       11.1622,
       12.4259,
       12.099,
       6.2248,
       5.352,
       5.7213,
       6.5612,
       7.8104,
       10.4574,
       10.7011,
       12.31
      ]
     },
     {
      "worker": 1,
      "segment_start": 1538727184,
      "segment_end": 3077454368,
      "bytes_returned": 1538727184,
      "wall_ms": 243.264,
      "gbps": 6.3253,
      "block_count": 46,
      "first_block_wall_ms": 4.5921,
      "block_timings_ms": [
       4.5921,
       4.9948,
       8.7229,
       7.649,
       6.7604,
       8.5817,
       9.814,
       4.1723,
       2.9608,
       5.8076,
       5.45,
       7.6463,
       7.5106,
       6.3401,
       7.461,
       7.3084,
       7.0573,
       7.0439,
       7.1221,
       5.6011,
       5.0292,
       5.2611,
       5.1587,
       3.3572,
       3.4526,
       3.5043,
       5.4892,
       3.1297,
       2.8709,
       2.8601,
       2.8559,
       5.4126,
       6.6998,
       6.0959,
       4.2213,
       5.5342,
       4.9834,
       4.7549,
       2.9677,
       2.4908,
       4.222,
       3.8801,
       4.4053,
       4.266,
       4.0513,
       2.5724
      ],
      "block_gbps": [
       7.3069,
       6.7179,
       3.8467,
       4.3868,
       4.9634,
       3.91,
       3.419,
       8.0423,
       11.333,
       5.7777,
       6.1567,
       4.3883,
       4.4676,
       5.2924,
       4.4973,
       4.5912,
       4.7545,
       4.7636,
       4.7113,
       5.9907,
       6.6719,
       6.3778,
       6.5044,
       9.9947,
       9.7187,
       9.5752,
       6.1128,
       10.7215,
       11.6879,
       11.7321,
       11.749,
       6.1994,
       5.0083,
       5.5045,
       7.9489,
       6.0631,
       6.7332,
       7.0569,
       11.3065,
       13.4716,
       7.9475,
       8.6478,
       7.6168,
       7.8656,
       8.2824,
       11.187
      ]
     },
     {
      "worker": 2,
      "segment_start": 3077454368,
      "segment_end": 4616181552,
      "bytes_returned": 1538727184,
      "wall_ms": 235.1457,
      "gbps": 6.5437,
      "block_count": 46,
      "first_block_wall_ms": 4.3805,
      "block_timings_ms": [
       4.3805,
       5.1292,
       3.9054,
       6.7286,
       7.1156,
       12.1852,
       3.9423,
       2.9095,
       6.1757,
       5.9321,
       4.3947,
       6.736,
       7.9316,
       8.0299,
       7.6431,
       7.6183,
       7.6821,
       7.5981,
       6.4614,
       5.2065,
       5.3423,
       4.1359,
       3.7933,
       3.1255,
       2.7234,
       2.6406,
       3.6695,
       5.8132,
       6.1692,
       5.6678,
       4.8731,
       5.5222,
       5.6887,
       5.8225,
       3.3035,
       3.3457,
       2.9318,
       2.8279,
       3.3147,
       2.8245,
       2.6032,
       3.5444,
       3.8952,
       4.5368,
       4.3224,
       3.4384
      ],
      "block_gbps": [
       7.66,
       6.5418,
       8.5917,
       4.9869,
       4.7156,
       2.7537,
       8.5114,
       11.5328,
       5.4333,
       5.6564,
       7.6352,
       4.9813,
       4.2305,
       4.1787,
       4.3902,
       4.4045,
       4.3679,
       4.4162,
       5.1931,
       6.4447,
       6.2809,
       8.113,
       8.8457,
       10.7356,
       12.3208,
       12.7071,
       9.1442,
       5.7721,
       5.439,
       5.9202,
       6.8856,
       6.0763,
       5.8985,
       5.7629,
       10.1571,
       10.0291,
       11.445,
       11.8655,
       10.123,
       11.8799,
       12.8898,
       9.4669,
       8.6143,
       7.396,
       7.7629,
       8.3695
      ]
     },
     {
      "worker": 3,
      "segment_start": 4616181552,
      "segment_end": 6154908736,
      "bytes_returned": 1538727184,
      "wall_ms": 167.9223,
      "gbps": 9.1633,
      "block_count": 46,
      "first_block_wall_ms": 4.8142,
      "block_timings_ms": [
       4.8142,
       4.5336,
       7.6353,
       18.5628,
       6.4008,
       4.3882,
       2.0965,
       1.9997,
       1.8901,
       1.9566,
       1.9474,
       1.6905,
       1.9163,
       1.7929,
       1.8139,
       2.6059,
       2.7498,
       3.1562,
       2.8903,
       2.7248,
       3.4733,
       3.2821,
       2.7392,
       2.4819,
       2.6777,
       2.6215,
       2.3456,
       4.3753,
       3.3823,
       3.6337,
       3.1568,
       7.0592,
       3.678,
       3.5104,
       2.768,
       4.728,
       3.3077,
       3.0962,
       2.6121,
       2.5414,
       2.5743,
       6.9107,
       3.3421,
       2.9407,
       3.4395,
       2.4523
      ],
      "block_gbps": [
       6.9699,
       7.4012,
       4.3947,
       1.8076,
       5.2422,
       7.6464,
       16.005,
       16.7797,
       17.7531,
       17.1494,
       17.2306,
       19.8487,
       17.5101,
       18.7148,
       18.4988,
       12.8763,
       12.2025,
       10.6311,
       11.6092,
       12.3143,
       9.6608,
       10.2233,
       12.2496,
       13.5198,
       12.531,
       12.7999,
       14.3054,
       7.6691,
       9.9205,
       9.2343,
       10.6291,
       4.7533,
       9.1231,
       9.5586,
       12.1224,
       7.0969,
       10.1443,
       10.8372,
       12.8456,
       13.203,
       13.0346,
       4.8554,
       10.0398,
       11.4102,
       9.7556,
       11.7351
      ]
     },
     {
      "worker": 4,
      "segment_start": 6154908736,
      "segment_end": 7693635920,
      "bytes_returned": 1538727184,
      "wall_ms": 206.6897,
      "gbps": 7.4446,
      "block_count": 46,
      "first_block_wall_ms": 4.2934,
      "block_timings_ms": [
       4.2934,
       7.2486,
       11.8996,
       7.1885,
       4.2349,
       5.715,
       2.8712,
       3.1166,
       3.138,
       2.5431,
       2.3277,
       7.712,
       5.7276,
       4.7527,
       6.0016,
       4.9059,
       4.6306,
       4.3851,
       4.0683,
       5.2187,
       5.2991,
       5.2427,
       4.0755,
       3.8062,
       8.132,
       2.8429,
       2.631,
       2.3028,
       2.6388,
       2.5492,
       2.684,
       4.9583,
       5.1857,
       5.4968,
       6.4804,
       2.6472,
       2.1665,
       2.1329,
       2.0807,
       2.508,
       5.4143,
       5.2883,
       4.9776,
       4.8626,
       3.599,
       2.9584
      ],
      "block_gbps": [
       7.8153,
       4.6291,
       2.8198,
       4.6678,
       7.9233,
       5.8713,
       11.6864,
       10.7665,
       10.6929,
       13.1944,
       14.4156,
       4.3509,
       5.8583,
       7.0601,
       5.5909,
       6.8396,
       7.2463,
       7.6518,
       8.2478,
       6.4297,
       6.3321,
       6.4002,
       8.2332,
       8.8158,
       4.1262,
       11.8028,
       12.7534,
       14.571,
       12.7158,
       13.1626,
       12.5016,
       6.7673,
       6.4706,
       6.1044,
       5.1778,
       12.6754,
       15.4881,
       15.7321,
       16.1266,
       13.3789,
       6.1974,
       6.3451,
       6.7411,
       6.9005,
       9.3234,
       9.7276
      ]
     },
     {
      "worker": 5,
      "segment_start": 7693635920,
      "segment_end": 9232363104,
      "bytes_returned": 1538727184,
      "wall_ms": 175.9689,
      "gbps": 8.7443,
      "block_count": 46,
      "first_block_wall_ms": 6.7072,
      "block_timings_ms": [
       6.7072,
       6.992,
       6.4995,
       3.0306,
       2.4781,
       2.0439,
       3.8674,
       3.1389,
       2.809,
       2.7348,
       2.5207,
       2.5687,
       2.4816,
       2.5234,
       2.572,
       2.435,
       2.6881,
       2.5084,
       2.6601,
       2.7037,
       2.5977,
       2.4581,
       2.481,
       2.619,
       3.2267,
       3.0867,
       2.9864,
       2.6755,
       2.6372,
       2.5234,
       2.2935,
       2.3627,
       2.4831,
       3.7058,
       2.6896,
       5.2285,
       5.7372,
       4.1195,
       4.2319,
       6.7591,
       5.7312,
       5.3848,
       5.8706,
       4.6836,
       4.5595,
       3.7378
      ],
      "block_gbps": [
       5.0028,
       4.799,
       5.1626,
       11.072,
       13.5405,
       16.4167,
       8.6763,
       10.69,
       11.9452,
       12.2692,
       13.3116,
       13.0631,
       13.5212,
       13.2973,
       13.0459,
       13.7801,
       12.4824,
       13.3767,
       12.6138,
       12.4106,
       12.9169,
       13.6506,
       13.5246,
       12.8119,
       10.3991,
       10.8706,
       11.2358,
       12.5411,
       12.7236,
       13.297,
       14.6305,
       14.2016,
       13.5129,
       9.0546,
       12.4756,
       6.4177,
       5.8485,
       8.1452,
       7.9289,
       4.9643,
       5.8547,
       6.2314,
       5.7157,
       7.1642,
       7.3593,
       7.6992
      ]
     },
     {
      "worker": 6,
      "segment_start": 9232363104,
      "segment_end": 10771090288,
      "bytes_returned": 1538727184,
      "wall_ms": 112.6526,
      "gbps": 13.659,
      "block_count": 46,
      "first_block_wall_ms": 6.371,
      "block_timings_ms": [
       6.371,
       11.9034,
       3.1088,
       2.8197,
       7.6308,
       2.7515,
       2.4638,
       2.0689,
       1.8781,
       1.9119,
       3.2944,
       4.4708,
       2.8377,
       3.0059,
       3.0391,
       2.6044,
       2.0601,
       1.6413,
       1.5511,
       1.5067,
       1.4339,
       1.431,
       1.3721,
       1.3419,
       1.4256,
       1.3816,
       1.3173,
       1.3176,
       1.9875,
       1.935,
       1.9519,
       2.7574,
       2.2913,
       2.2054,
       2.1758,
       1.5056,
       1.6138,
       1.4223,
       1.3712,
       1.7234,
       1.9934,
       1.5345,
       1.4153,
       1.3899,
       1.4026,
       1.1975
      ],
      "block_gbps": [
       5.2668,
       2.8189,
       10.7935,
       11.9001,
       4.3973,
       12.1951,
       13.6188,
       16.2187,
       17.866,
       17.5503,
       10.1854,
       7.5052,
       11.8244,
       11.163,
       11.0408,
       12.8838,
       16.2882,
       20.4434,
       21.6332,
       22.2699,
       23.4008,
       23.4491,
       24.4552,
       25.0042,
       23.5372,
       24.2861,
       25.4717,
       25.4662,
       16.8832,
       17.3411,
       17.1907,
       12.1689,
       14.644,
       15.2143,
       15.4219,
       22.2869,
       20.7919,
       23.5912,
       24.4707,
       19.47,
       16.8323,
       21.8673,
       23.7079,
       24.1413,
       23.923,
       24.0323
      ]
     },
     {
      "worker": 7,
      "segment_start": 10771090288,
      "segment_end": 12309817472,
      "bytes_returned": 1538727184,
      "wall_ms": 110.5673,
      "gbps": 13.9167,
      "block_count": 46,
      "first_block_wall_ms": 5.4857,
      "block_timings_ms": [
       5.4857,
       2.2659,
       1.9358,
       1.9515,
       2.0615,
       2.0233,
       1.8423,
       1.8675,
       1.7519,
       1.6829,
       1.6575,
       1.6594,
       1.5794,
       1.8071,
       1.8505,
       1.613,
       1.5899,
       1.9164,
       1.5397,
       1.5303,
       1.5202,
       2.3878,
       2.1656,
       2.4605,
       1.9343,
       2.0225,
       3.4432,
       2.572,
       2.6734,
       3.0364,
       2.0801,
       2.9713,
       1.8791,
       2.1393,
       2.0437,
       1.8662,
       2.0076,
       4.239,
       3.267,
       7.3861,
       2.8396,
       2.7124,
       2.9819,
       2.4427,
       2.7951,
       2.2219
      ],
      "block_gbps": [
       6.1167,
       14.8086,
       17.3333,
       17.1943,
       16.2769,
       16.5839,
       18.2133,
       17.9672,
       19.1532,
       19.9385,
       20.2438,
       20.2209,
       21.2455,
       18.5679,
       18.1322,
       20.8026,
       21.1045,
       17.5093,
       21.7923,
       21.927,
       22.0724,
       14.0522,
       15.4945,
       13.637,
       17.3472,
       16.5907,
       9.7453,
       13.0461,
       12.5512,
       11.0509,
       16.1311,
       11.293,
       17.8571,
       15.685,
       16.4182,
       17.9798,
       16.7134,
       7.9156,
       10.2707,
       4.5429,
       11.8166,
       12.3707,
       11.2527,
       13.7367,
       12.0047,
       12.9517
      ]
     }
    ],
    "first_range_latency_ms": 4.037,
    "tail_spread_ms": 132.6967,
    "process_cpu_ms": 330.0,
    "thread_cpu_ms": 20.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 33554432,
    "peak_rss_bytes": 18152681472,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 133.0,
    "gbps_per_cpu_core": 37.3025,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 25.6922,
     "gbps": 10.4481
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 12309555328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7516192768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8052801536,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8053063680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589672448,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589934592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126543360,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126805504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663414272,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663676416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200285184,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200547328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737156096,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737418240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274027008,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274289152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11810897920,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   },
   {
    "kind": "raw_qd",
    "qd": 16,
    "worker_count": 16,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 12309817472,
    "status": "ok",
    "bytes_returned": 12309817472,
    "expected_bytes": 12309817472,
    "total_wall_ms": 538.5987,
    "aggregate_gbps": 22.8553,
    "steady_state_gbps": 8.6014,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 769363592,
      "bytes_returned": 769363592,
      "wall_ms": 116.1046,
      "gbps": 6.6265,
      "block_count": 6,
      "first_block_wall_ms": 10.123,
      "block_timings_ms": [
       10.123,
       18.6838,
       15.6193,
       29.4337,
       15.3716,
       25.8874
      ],
      "block_gbps": [
       13.2587,
       7.1836,
       8.5931,
       4.56,
       8.7315,
       3.7962
      ]
     },
     {
      "worker": 1,
      "segment_start": 769363592,
      "segment_end": 1538727184,
      "bytes_returned": 769363592,
      "wall_ms": 88.9956,
      "gbps": 8.645,
      "block_count": 6,
      "first_block_wall_ms": 19.4419,
      "block_timings_ms": [
       19.4419,
       13.9975,
       14.0554,
       15.8356,
       15.7694,
       9.2377
      ],
      "block_gbps": [
       6.9035,
       9.5887,
       9.5492,
       8.4757,
       8.5113,
       10.6385
      ]
     },
     {
      "worker": 2,
      "segment_start": 1538727184,
      "segment_end": 2308090776,
      "bytes_returned": 769363592,
      "wall_ms": 113.248,
      "gbps": 6.7936,
      "block_count": 6,
      "first_block_wall_ms": 14.4308,
      "block_timings_ms": [
       14.4308,
       13.2391,
       15.8142,
       15.2877,
       25.6452,
       26.8939
      ],
      "block_gbps": [
       9.3008,
       10.138,
       8.4871,
       8.7795,
       5.2336,
       3.6542
      ]
     },
     {
      "worker": 3,
      "segment_start": 2308090776,
      "segment_end": 3077454368,
      "bytes_returned": 769363592,
      "wall_ms": 170.4213,
      "gbps": 4.5145,
      "block_count": 6,
      "first_block_wall_ms": 16.2147,
      "block_timings_ms": [
       16.2147,
       26.8708,
       27.2925,
       22.7177,
       15.5436,
       19.3672
      ],
      "block_gbps": [
       8.2775,
       4.9949,
       4.9177,
       5.9081,
       8.6349,
       5.0743
      ]
     },
     {
      "worker": 4,
      "segment_start": 3077454368,
      "segment_end": 3846817960,
      "bytes_returned": 769363592,
      "wall_ms": 118.9055,
      "gbps": 6.4704,
      "block_count": 6,
      "first_block_wall_ms": 25.9506,
      "block_timings_ms": [
       25.9506,
       26.1913,
       13.3909,
       13.5445,
       23.9364,
       15.3163
      ],
      "block_gbps": [
       5.172,
       5.1245,
       10.023,
       9.9094,
       5.6073,
       6.4164
      ]
     },
     {
      "worker": 5,
      "segment_start": 3846817960,
      "segment_end": 4616181552,
      "bytes_returned": 769363592,
      "wall_ms": 188.5688,
      "gbps": 4.08,
      "block_count": 6,
      "first_block_wall_ms": 24.3126,
      "block_timings_ms": [
       24.3126,
       15.3139,
       44.353,
       14.9225,
       74.2224,
       14.6242
      ],
      "block_gbps": [
       5.5205,
       8.7644,
       3.0261,
       8.9943,
       1.8083,
       6.72
      ]
     },
     {
      "worker": 6,
      "segment_start": 4616181552,
      "segment_end": 5385545144,
      "bytes_returned": 769363592,
      "wall_ms": 133.1281,
      "gbps": 5.7791,
      "block_count": 6,
      "first_block_wall_ms": 22.8533,
      "block_timings_ms": [
       22.8533,
       15.0064,
       33.0247,
       12.9426,
       14.4482,
       33.8088
      ],
      "block_gbps": [
       5.873,
       8.944,
       4.0642,
       10.3702,
       9.2896,
       2.9068
      ]
     },
     {
      "worker": 7,
      "segment_start": 5385545144,
      "segment_end": 6154908736,
      "bytes_returned": 769363592,
      "wall_ms": 131.6034,
      "gbps": 5.8461,
      "block_count": 6,
      "first_block_wall_ms": 15.6041,
      "block_timings_ms": [
       15.6041,
       18.7243,
       26.0589,
       15.3774,
       14.4838,
       41.1439
      ],
      "block_gbps": [
       8.6014,
       7.1681,
       5.1505,
       8.7283,
       9.2668,
       2.3886
      ]
     },
     {
      "worker": 8,
      "segment_start": 6154908736,
      "segment_end": 6924272328,
      "bytes_returned": 769363592,
      "wall_ms": 148.2618,
      "gbps": 5.1892,
      "block_count": 6,
      "first_block_wall_ms": 18.503,
      "block_timings_ms": [
       18.503,
       14.8286,
       33.5721,
       21.2992,
       19.1389,
       13.7141
      ],
      "block_gbps": [
       7.2539,
       9.0513,
       3.9979,
       6.3015,
       7.0128,
       7.166
      ]
     },
     {
      "worker": 9,
      "segment_start": 6924272328,
      "segment_end": 7693635920,
      "bytes_returned": 769363592,
      "wall_ms": 116.7586,
      "gbps": 6.5894,
      "block_count": 6,
      "first_block_wall_ms": 13.7386,
      "block_timings_ms": [
       13.7386,
       15.3057,
       40.7423,
       18.0421,
       14.6872,
       13.3689
      ],
      "block_gbps": [
       9.7694,
       8.7691,
       3.2943,
       7.4391,
       9.1384,
       7.351
      ]
     },
     {
      "worker": 10,
      "segment_start": 7693635920,
      "segment_end": 8462999512,
      "bytes_returned": 769363592,
      "wall_ms": 132.3129,
      "gbps": 5.8147,
      "block_count": 6,
      "first_block_wall_ms": 24.0926,
      "block_timings_ms": [
       24.0926,
       50.1369,
       14.0506,
       14.7412,
       13.8386,
       14.8339
      ],
      "block_gbps": [
       5.5709,
       2.677,
       9.5524,
       9.105,
       9.6988,
       6.625
      ]
     },
     {
      "worker": 11,
      "segment_start": 8462999512,
      "segment_end": 9232363104,
      "bytes_returned": 769363592,
      "wall_ms": 95.8352,
      "gbps": 8.028,
      "block_count": 6,
      "first_block_wall_ms": 14.6086,
      "block_timings_ms": [
       14.6086,
       14.2405,
       14.6539,
       14.5115,
       14.944,
       22.1208
      ],
      "block_gbps": [
       9.1876,
       9.4251,
       9.1592,
       9.249,
       8.9814,
       4.4426
      ]
     },
     {
      "worker": 12,
      "segment_start": 9232363104,
      "segment_end": 10001726696,
      "bytes_returned": 769363592,
      "wall_ms": 94.1186,
      "gbps": 8.1744,
      "block_count": 6,
      "first_block_wall_ms": 13.8283,
      "block_timings_ms": [
       13.8283,
       14.8317,
       14.2607,
       15.0771,
       14.7968,
       20.9062
      ],
      "block_gbps": [
       9.706,
       9.0494,
       9.4117,
       8.9021,
       9.0707,
       4.7008
      ]
     },
     {
      "worker": 13,
      "segment_start": 10001726696,
      "segment_end": 10771090288,
      "bytes_returned": 769363592,
      "wall_ms": 78.2641,
      "gbps": 9.8304,
      "block_count": 6,
      "first_block_wall_ms": 12.2262,
      "block_timings_ms": [
       12.2262,
       22.5517,
       13.0937,
       12.0563,
       11.4839,
       6.4487
      ],
      "block_gbps": [
       10.9778,
       5.9516,
       10.2506,
       11.1326,
       11.6874,
       15.2395
      ]
     },
     {
      "worker": 14,
      "segment_start": 10771090288,
      "segment_end": 11540453880,
      "bytes_returned": 769363592,
      "wall_ms": 99.0598,
      "gbps": 7.7667,
      "block_count": 6,
      "first_block_wall_ms": 14.2378,
      "block_timings_ms": [
       14.2378,
       12.9406,
       21.4141,
       24.7748,
       14.6915,
       10.5564
      ],
      "block_gbps": [
       9.4269,
       10.3718,
       6.2677,
       5.4175,
       9.1357,
       9.3095
      ]
     },
     {
      "worker": 15,
      "segment_start": 11540453880,
      "segment_end": 12309817472,
      "bytes_returned": 769363592,
      "wall_ms": 72.6721,
      "gbps": 10.5868,
      "block_count": 6,
      "first_block_wall_ms": 11.3694,
      "block_timings_ms": [
       11.3694,
       17.7628,
       17.256,
       9.8946,
       9.3049,
       6.8804
      ],
      "block_gbps": [
       11.8052,
       7.5561,
       7.778,
       13.5647,
       14.4244,
       14.2833
      ]
     }
    ],
    "first_range_latency_ms": 10.123,
    "tail_spread_ms": 115.8967,
    "process_cpu_ms": 1690.0,
    "thread_cpu_ms": 310.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 402653184,
    "peak_rss_bytes": 18186235904,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 313.78,
    "gbps_per_cpu_core": 7.2839,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 25.9937,
     "gbps": 10.3269
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 12309555328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7516192768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8052801536,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8053063680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589672448,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8589934592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126543360,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9126805504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663414272,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 9663676416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200285184,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10200547328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737156096,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 10737418240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274027008,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11274289152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 11810897920,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   }
  ],
  "gpu_transfer": {
   "kind": "gpu",
   "qd": 4,
   "block_mib": 32,
   "status": "ok",
   "total_bytes": 12309817472,
   "storage_plus_h2d_wall_ms": 1020.8782,
   "h2d_device_ms": 1020.7964,
   "h2d_host_issue_total_ms": 5.6668,
   "h2d_host_issue_max_ms": 0.1008,
   "storage_gbps": 150657.5985,
   "combined_gbps": 12.0581,
   "pinned_bytes": 134217728,
   "gpu_temp_bytes": 134217728,
   "issue_count": 368
  },
  "gpu_config": {
   "qd": 4,
   "block_mib": 32
  },
  "external": [
   {
    "kind": "external",
    "loader": "fastsafetensors",
    "concurrency": 8,
    "block_mib": 1024,
    "device": "cpu",
    "status": "ok",
    "wall_ms": 1847.1222,
    "process_cpu_ms": 9860.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 24626245632,
    "peak_rss_bytes": 30548353024,
    "error": null,
    "tensor_count": 453,
    "total_bytes": 12309817472,
    "aggregate_gbps": 6.6643,
    "key_set_ok": true,
    "spot_check": {
     "ok": true,
     "checked": 16,
     "mismatches": []
    },
    "sample_hash": "0740edff0575056a1bd07ad4b98cb3c06a8b731a9d6c4d2199c94c02e6bff52f",
    "cpu_cores": 28,
    "cpu_utilization_pct": 533.8,
    "gbps_per_cpu_core": 1.2485,
    "sample_hash_matches_baseline": true,
    "_skip_reason": ""
   },
   {
    "kind": "external",
    "loader": "fastsafetensors",
    "concurrency": 16,
    "block_mib": 1024,
    "device": "cpu",
    "status": "ok",
    "wall_ms": 1214.6447,
    "process_cpu_ms": 12530.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 24623640576,
    "peak_rss_bytes": 42863570944,
    "error": null,
    "tensor_count": 453,
    "total_bytes": 12309817472,
    "aggregate_gbps": 10.1345,
    "key_set_ok": true,
    "spot_check": {
     "ok": true,
     "checked": 16,
     "mismatches": []
    },
    "sample_hash": "0740edff0575056a1bd07ad4b98cb3c06a8b731a9d6c4d2199c94c02e6bff52f",
    "cpu_cores": 28,
    "cpu_utilization_pct": 1031.58,
    "gbps_per_cpu_core": 0.9824,
    "sample_hash_matches_baseline": true,
    "_skip_reason": ""
   },
   {
    "kind": "external",
    "loader": "fastsafetensors",
    "concurrency": 16,
    "block_mib": 1024,
    "device": "cuda:0",
    "status": "ok",
    "wall_ms": 592.3204,
    "process_cpu_ms": 1250.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 1486848,
    "peak_rss_bytes": 42863570944,
    "error": null,
    "tensor_count": 453,
    "total_bytes": 12309817472,
    "aggregate_gbps": 20.7824,
    "key_set_ok": true,
    "spot_check": {
     "ok": true,
     "checked": 16,
     "mismatches": []
    },
    "sample_hash": "0740edff0575056a1bd07ad4b98cb3c06a8b731a9d6c4d2199c94c02e6bff52f",
    "cpu_cores": 28,
    "cpu_utilization_pct": 211.03,
    "gbps_per_cpu_core": 9.8479,
    "sample_hash_matches_baseline": true,
    "_skip_reason": ""
   }
  ],
  "external_skips": {
   "runai": "import failed (image extras not installed?)"
  },
  "summary": {
   "status": "ok",
   "total_data_bytes": 12309817472,
   "baseline_mmap_gbps": 17.4479,
   "baseline_seq_preadv_gbps": 6.597,
   "baseline_mmap_wall_ms": 705.5182,
   "baseline_seq_preadv_wall_ms": 1865.9818,
   "fullfile_qd1_gbps": 6.597,
   "fullfile_warm_qd1_gbps": 11.3765,
   "fullfile_best_qd2_gbps": 23.0433,
   "fullfile_best_qd4_gbps": 43.4521,
   "fullfile_best_qd8_gbps": 49.6111,
   "fullfile_qd16_gbps": 22.8553,
   "qd_ratios": {
    "qd2_over_qd1": 3.493,
    "qd4_over_qd1": 6.5866,
    "qd8_over_qd1": 7.5203,
    "qd16_over_qd1": 3.4645,
    "warm_qd1_over_cold_qd1": 1.7245
   },
   "best_screen": {
    "qd": 4,
    "block_mib": 32,
    "gbps": 21.8722
   },
   "best_fullfile_gbps": 49.6111,
   "external": [
    {
     "loader": "fastsafetensors",
     "concurrency": 8,
     "device": "cpu",
     "status": "ok",
     "wall_ms": 1847.1222,
     "aggregate_gbps": 6.6643,
     "sample_hash_matches_baseline": true,
     "key_set_ok": true,
     "spot_check_ok": true,
     "error": null
    },
    {
     "loader": "fastsafetensors",
     "concurrency": 16,
     "device": "cpu",
     "status": "ok",
     "wall_ms": 1214.6447,
     "aggregate_gbps": 10.1345,
     "sample_hash_matches_baseline": true,
     "key_set_ok": true,
     "spot_check_ok": true,
     "error": null
    },
    {
     "loader": "fastsafetensors",
     "concurrency": 16,
     "device": "cuda:0",
     "status": "ok",
     "wall_ms": 592.3204,
     "aggregate_gbps": 20.7824,
     "sample_hash_matches_baseline": true,
     "key_set_ok": true,
     "spot_check_ok": true,
     "error": null
    }
   ],
   "gpu_transfer_status": "ok"
  }
 },
 "_wall_ms": 22711.8847,
 "model_name": "z_image_turbo_bf16.safetensors",
 "resolved_path": "/root/comfy/ComfyUI/models/diffusion_models/z_image_turbo_bf16.safetensors",
 "waterfall": {
  "status": "non_applicable",
  "method": "run_unet_qd_probe"
 }
}
```
</details>


### COMPLETE RAW — `_e27_clip_qd_evidence.json` (embedded in full)

<details>
<summary>Complete CLIP QD evidence artifact (136,953 bytes) — click to expand</summary>


```json
{
 "probe": "clip_qd",
 "model_path": "/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors",
 "mode": "evidence",
 "status": "ok",
 "sections": {
  "env": {
   "status": "ok",
   "os": "posix",
   "platform": "linux",
   "python": "3.11.5",
   "cpu_cores": 28,
   "preadv_available": true,
   "cuda_available": true,
   "cuda_device_name": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
   "torch_version": "2.13.0+cu130"
  },
  "file": {
   "status": "ok",
   "path": "/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors",
   "size_bytes": 8044982048,
   "header_bytes": 45848,
   "data_start_offset": 45856,
   "tensor_count": 398,
   "total_data_bytes": 8044936192,
   "statvfs": {
    "f_bsize": 4096,
    "f_frsize": 4096,
    "f_blocks": 100000000,
    "f_bfree": 100000000,
    "f_bavail": 100000000
   },
   "mount": "none on / type overlay"
  },
  "loader_imports": {
   "runai_model_streamer": {
    "importable": false,
    "error": "ModuleNotFoundError: No module named 'runai_model_streamer'"
   },
   "fastsafetensors": {
    "importable": true,
    "version": "0.3.3"
   },
   "safetensors_version": "0.5.3",
   "safe_open_backend_param": false
  },
  "loader_smoke": {
   "synthetic_file": "/tmp/c9qd_smoke.safetensors",
   "loaders": {
    "runai": {
     "status": "error",
     "error": "ModuleNotFoundError: No module named 'runai_model_streamer'"
    },
    "fastsafetensors": {
     "status": "ok",
     "keys": [
      "a",
      "b",
      "c"
     ],
     "wall_ms": 5.86
    }
   }
  },
  "loader_ownership": {
   "status": "ok",
   "reason": "",
   "identity": [
    {
     "key": "a",
     "data_ptr": 47588954865664,
     "storage_data_ptr": 47588954865664,
     "storage_size": 1048576,
     "storage_offset": 0,
     "shape": [
      262144
     ],
     "stride": [
      1
     ],
     "contiguous": true,
     "base": "None"
    },
    {
     "key": "b",
     "data_ptr": 47588955914240,
     "storage_data_ptr": 47588955914240,
     "storage_size": 1048576,
     "storage_offset": 0,
     "shape": [
      262144
     ],
     "stride": [
      1
     ],
     "contiguous": true,
     "base": "None"
    },
    {
     "key": "c",
     "data_ptr": 47588956962816,
     "storage_data_ptr": 47588956962816,
     "storage_size": 8,
     "storage_offset": 0,
     "shape": [
      4
     ],
     "stride": [
      1
     ],
     "contiguous": true,
     "base": "None"
    }
   ],
   "distinct_data_ptrs": [
    47588954865664,
    47588955914240,
    47588956962816
   ],
   "tensors_share_allocation": false,
   "retained_lifetime": {
    "status": "ok",
    "hash_before": "f908964ddcfb10e3",
    "hash_after": "f908964ddcfb10e3"
   },
   "closed_lifetime": {
    "status": "recorded",
    "read_after_close": "error:KeyError:0"
   }
  },
  "baseline_mmap": {
   "kind": "baseline_mmap",
   "status": "ok",
   "tensor_count": 398,
   "total_bytes": 8044936192,
   "total_wall_ms": 7370.8277,
   "aggregate_gbps": 1.0915,
   "minflt_delta": 0,
   "majflt_delta": 0,
   "ctxt_switches_delta": null,
   "rss_delta_bytes": 8046198784,
   "peak_rss_bytes": 11464630272,
   "process_cpu_ms": 82.8,
   "sample_hash": "473f07282f9416ff739c07714c8e6734821d54e4800e6fbc838f25e4cc31551b"
  },
  "baseline_seq_preadv": {
   "kind": "raw_qd",
   "qd": 1,
   "worker_count": 1,
   "block_mib": 32,
   "syscall_bytes": 33554432,
   "schedule": "static",
   "window_start": 0,
   "window_len": 8044936192,
   "status": "ok",
   "bytes_returned": 8044936192,
   "expected_bytes": 8044936192,
   "total_wall_ms": 1047.3224,
   "aggregate_gbps": 7.6814,
   "steady_state_gbps": 8.1233,
   "per_worker": [
    {
     "worker": 0,
     "segment_start": 0,
     "segment_end": 8044936192,
     "bytes_returned": 8044936192,
     "wall_ms": 1043.1422,
     "gbps": 7.7122,
     "block_count": 240,
     "first_block_wall_ms": 6.2504,
     "block_timings_ms": [
      6.2504,
      5.4904,
      6.8222,
      6.3356,
      5.6334,
      5.6801,
      5.5693,
      5.7562,
      19.094,
      5.3747,
      5.6727,
      5.45,
      5.9323,
      5.3883,
      5.5627,
      5.6568,
      5.594,
      5.5268,
      5.5203,
      5.6132,
      5.5026,
      4.4295,
      3.3349,
      2.7672,
      4.2129,
      3.1266,
      5.4297,
      2.6517,
      4.3876,
      3.5745,
      2.9504,
      3.7425,
      2.1564,
      2.3969,
      4.8053,
      3.5427,
      2.688,
      4.1548,
      2.4206,
      2.2665,
      4.6806,
      3.7443,
      2.7795,
      4.3375,
      2.2111,
      2.2948,
      4.5617,
      3.6165,
      2.978,
      4.5294,
      2.2443,
      2.6041,
      4.4414,
      4.2892,
      3.6883,
      5.2732,
      2.5749,
      2.9464,
      6.7218,
      4.9701,
      2.8836,
      5.2607,
      2.4003,
      2.242,
      4.5558,
      3.7824,
      2.5443,
      4.5453,
      2.1755,
      2.1319,
      4.1852,
      3.3554,
      1.9803,
      4.6371,
      2.1766,
      2.1841,
      5.1619,
      5.7696,
      3.6561,
      6.3869,
      3.6217,
      3.3735,
      5.1984,
      4.5556,
      3.2661,
      5.9749,
      4.2958,
      3.958,
      5.6146,
      4.7875,
      2.9954,
      5.4589,
      3.8819,
      3.685,
      5.3231,
      4.4351,
      3.0979,
      5.4958,
      2.9286,
      3.5559,
      5.2718,
      4.9756,
      3.4327,
      4.9196,
      2.7823,
      2.7925,
      4.9422,
      3.9124,
      2.5351,
      4.8083,
      3.4913,
      3.2814,
      5.3767,
      4.9361,
      2.9463,
      5.1299,
      2.9921,
      2.7558,
      5.5679,
      4.4223,
      2.8526,
      5.0872,
      2.8735,
      3.0883,
      5.1192,
      5.4385,
      3.6919,
      5.8253,
      4.4198,
      3.6535,
      5.397,
      6.0218,
      4.3493,
      6.1503,
      3.3631,
      3.006,
      4.8436,
      4.1247,
      4.0215,
      5.9726,
      4.7783,
      3.2648,
      5.2525,
      5.2842,
      4.1316,
      5.8703,
      3.4271,
      3.2107,
      4.9836,
      5.6196,
      3.6282,
      6.2623,
      3.2043,
      3.281,
      4.0591,
      6.9445,
      3.8578,
      5.6626,
      3.6699,
      4.0906,
      3.3716,
      7.4208,
      3.4697,
      5.5197,
      3.4577,
      4.0089,
      3.8388,
      6.8886,
      3.9135,
      5.6412,
      3.3435,
      3.2132,
      3.0687,
      6.5501,
      2.8824,
      4.9571,
      2.991,
      2.7263,
      3.3544,
      6.5369,
      2.9894,
      4.9186,
      3.0017,
      2.7983,
      2.859,
      6.1503,
      2.8151,
      4.8575,
      2.7766,
      2.7702,
      4.1406,
      7.2134,
      4.5334,
      5.8354,
      3.8012,
      3.6728,
      4.2335,
      7.3411,
      4.0864,
      5.5606,
      3.2775,
      3.4332,
      3.3325,
      6.2906,
      5.2963,
      4.1663,
      5.4607,
      4.0976,
      3.7596,
      5.9248,
      5.2615,
      3.8472,
      5.347,
      3.6587,
      3.4294,
      6.0199,
      5.3046,
      3.6654,
      4.968,
      3.1093,
      3.3497,
      5.3589,
      4.1306,
      4.0101,
      5.5803,
      3.2985,
      3.4072,
      5.6141,
      4.6293,
      3.6451,
      4.6682,
      3.2029,
      2.9865,
      5.0124,
      4.1481,
      3.1851,
      4.9868,
      3.2535,
      2.9183,
      2.2351
     ],
     "block_gbps": [
      5.3683,
      6.1115,
      4.9184,
      5.2962,
      5.9563,
      5.9074,
      6.0249,
      5.8292,
      1.7573,
      6.2431,
      5.915,
      6.1568,
      5.6562,
      6.2272,
      6.032,
      5.9317,
      5.9983,
      6.0712,
      6.0784,
      5.9778,
      6.0979,
      7.5753,
      10.0617,
      12.1256,
      7.9646,
      10.732,
      6.1797,
      12.654,
      7.6476,
      9.3873,
      11.3728,
      8.9659,
      15.5604,
      13.9991,
      6.9828,
      9.4714,
      12.4831,
      8.076,
      13.8622,
      14.8044,
      7.1688,
      8.9616,
      12.0722,
      7.7359,
      15.1755,
      14.6218,
      7.3557,
      9.278,
      11.2674,
      7.4081,
      14.9508,
      12.8853,
      7.5549,
      7.823,
      9.0976,
      6.3632,
      13.0314,
      11.3884,
      4.9919,
      6.7512,
      11.6365,
      6.3784,
      13.979,
      14.9662,
      7.3653,
      8.8712,
      13.1881,
      7.3822,
      15.4237,
      15.7395,
      8.0174,
      10.0002,
      16.9444,
      7.236,
      15.4162,
      15.3628,
      6.5004,
      5.8157,
      9.1776,
      5.2536,
      9.2648,
      9.9464,
      6.4547,
      7.3656,
      10.2736,
      5.6159,
      7.811,
      8.4777,
      5.9763,
      7.0088,
      11.2021,
      6.1467,
      8.6437,
      9.1056,
      6.3036,
      7.5657,
      10.8313,
      6.1054,
      11.4576,
      9.4363,
      6.3649,
      6.7438,
      9.775,
      6.8205,
      12.0598,
      12.016,
      6.7894,
      8.5764,
      13.2359,
      6.9784,
      9.6109,
      10.2255,
      6.2407,
      6.7977,
      11.3886,
      6.541,
      11.2142,
      12.1761,
      6.0264,
      7.5876,
      11.7626,
      6.5958,
      11.6774,
      10.8649,
      6.5546,
      6.1698,
      9.0887,
      5.7602,
      7.5918,
      9.1841,
      6.2172,
      5.5721,
      7.7149,
      5.4557,
      9.9772,
      11.1623,
      6.9276,
      8.1349,
      8.3439,
      5.618,
      7.0223,
      10.2777,
      6.3883,
      6.35,
      8.1215,
      5.716,
      9.791,
      10.4509,
      6.733,
      5.9709,
      9.2481,
      5.3581,
      10.4717,
      10.2269,
      8.2665,
      4.8318,
      8.6977,
      5.9256,
      9.1432,
      8.2028,
      9.9522,
      4.5217,
      9.6706,
      6.0791,
      9.7042,
      8.3699,
      8.7408,
      4.871,
      8.5739,
      5.9481,
      10.0357,
      10.4427,
      10.9344,
      5.1228,
      11.6412,
      6.769,
      11.2186,
      12.3076,
      10.003,
      5.1331,
      11.2247,
      6.8219,
      11.1784,
      11.9912,
      11.7365,
      5.4557,
      11.9193,
      6.9078,
      12.0846,
      12.1124,
      8.1038,
      4.6517,
      7.4016,
      5.7501,
      8.8273,
      9.1359,
      7.9259,
      4.5707,
      8.2113,
      6.0343,
      10.2377,
      9.7734,
      10.0689,
      5.334,
      6.3354,
      8.0539,
      6.1448,
      8.1887,
      8.925,
      5.6634,
      6.3773,
      8.7218,
      6.2753,
      9.171,
      9.7845,
      5.574,
      6.3256,
      9.1544,
      6.7541,
      10.7916,
      10.0172,
      6.2615,
      8.1233,
      8.3676,
      6.013,
      10.1727,
      9.848,
      5.9768,
      7.2483,
      9.2053,
      7.1879,
      10.4763,
      11.2353,
      6.6943,
      8.089,
      10.5349,
      6.7286,
      10.3135,
      11.4979,
      11.3765
     ]
    }
   ],
   "first_range_latency_ms": 6.2504,
   "tail_spread_ms": 0.0,
   "process_cpu_ms": 100.0,
   "thread_cpu_ms": 10.0,
   "minflt_delta": 0,
   "majflt_delta": 0,
   "ctxt_switches_delta": null,
   "rss_delta_bytes": 33554432,
   "peak_rss_bytes": 11465412608,
   "peak_pinned_bytes": 0,
   "cpu_cores": 28,
   "cpu_utilization_pct": 9.55,
   "gbps_per_cpu_core": 80.449,
   "warm_repeat": {
    "bytes": 268435456,
    "wall_ms": 18.6092,
    "gbps": 14.4249
   },
   "verify": {
    "regions": [
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8044674048,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536608768,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536870912,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073479680,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073741824,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610350592,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610612736,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147221504,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147483648,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684092416,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684354560,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3220963328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3221225472,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3757834240,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3758096384,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294705152,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294967296,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831576064,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831838208,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368446976,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368709120,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905317888,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905580032,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442188800,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442450944,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979059712,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979321856,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 7515930624,
      "bytes": 262144,
      "hash_match": true
     }
    ],
    "all_match": true
   }
  },
  "screen": [
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 122.9167,
    "aggregate_gbps": 17.471,
    "steady_state_gbps": 18.0644,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 2147483648,
      "bytes_returned": 2147483648,
      "wall_ms": 122.1208,
      "gbps": 17.5849,
      "block_count": 64,
      "first_block_wall_ms": 2.156,
      "block_timings_ms": [
       2.156,
       2.133,
       2.0351,
       1.9812,
       1.9429,
       2.0788,
       2.6059,
       2.0522,
       2.0585,
       1.7277,
       1.7166,
       1.682,
       1.6896,
       1.708,
       1.9676,
       2.6911,
       1.8656,
       1.8037,
       1.6409,
       1.5314,
       1.3896,
       1.4034,
       1.6606,
       1.6236,
       1.7776,
       1.4761,
       1.9083,
       1.5395,
       1.5506,
       1.5294,
       1.948,
       1.6742,
       1.6372,
       1.9704,
       2.3497,
       1.7752,
       1.6333,
       1.5706,
       1.6724,
       1.627,
       2.0353,
       1.7661,
       1.8575,
       2.2469,
       1.8563,
       1.9278,
       1.9232,
       2.0123,
       2.1581,
       1.7539,
       1.8637,
       2.5078,
       1.9239,
       1.7856,
       1.9473,
       1.7379,
       2.1597,
       2.0945,
       2.555,
       1.8568,
       2.0834,
       1.9646,
       1.5871,
       1.5343
      ],
      "block_gbps": [
       15.5631,
       15.731,
       16.4877,
       16.9368,
       17.2706,
       16.1413,
       12.8763,
       16.3504,
       16.3007,
       19.4219,
       19.547,
       19.9485,
       19.8595,
       19.6457,
       17.053,
       12.4685,
       17.9856,
       18.6035,
       20.4485,
       21.9104,
       24.1465,
       23.9096,
       20.2064,
       20.6665,
       18.876,
       22.732,
       17.5834,
       21.7963,
       21.6398,
       21.9401,
       17.2251,
       20.042,
       20.4949,
       17.0293,
       14.2803,
       18.9023,
       20.5439,
       21.3634,
       20.0634,
       20.6234,
       16.4859,
       18.9991,
       18.0644,
       14.9335,
       18.0764,
       17.4055,
       17.4469,
       16.6749,
       15.5478,
       19.1309,
       18.0044,
       13.3803,
       17.4405,
       18.7913,
       17.2315,
       19.3077,
       15.5368,
       16.0202,
       13.1331,
       18.0709,
       16.1056,
       17.0793,
       21.1414,
       21.8697
      ]
     }
    ],
    "first_range_latency_ms": 2.156,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 20.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 12547428352,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 16.27,
    "gbps_per_cpu_core": 107.3739,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.0979,
     "gbps": 14.8324
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 0
   },
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 2147483648,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 180.6617,
    "aggregate_gbps": 11.8868,
    "steady_state_gbps": 13.0102,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 2147483648,
      "segment_end": 4294967296,
      "bytes_returned": 2147483648,
      "wall_ms": 174.7774,
      "gbps": 12.287,
      "block_count": 32,
      "first_block_wall_ms": 3.8103,
      "block_timings_ms": [
       3.8103,
       4.2317,
       4.0855,
       5.2922,
       4.9414,
       4.8574,
       5.6141,
       5.0571,
       4.9917,
       5.122,
       5.1158,
       5.1582,
       5.0996,
       5.0909,
       4.9798,
       5.9936,
       4.9428,
       5.0999,
       4.6725,
       5.2493,
       4.8394,
       5.8402,
       5.8448,
       5.61,
       5.8258,
       5.6051,
       6.5347,
       6.2563,
       6.7475,
       6.6278,
       7.9975,
       6.1672
      ],
      "block_gbps": [
       17.6126,
       15.8587,
       16.4261,
       12.6807,
       13.581,
       13.8159,
       11.9537,
       13.2703,
       13.4442,
       13.1022,
       13.118,
       13.0102,
       13.1596,
       13.1821,
       13.4763,
       11.1967,
       13.5771,
       13.1589,
       14.3626,
       12.7842,
       13.8673,
       11.4909,
       11.4817,
       11.9624,
       11.5193,
       11.9729,
       10.2696,
       10.7266,
       9.9458,
       10.1254,
       8.3912,
       10.8816
      ]
     }
    ],
    "first_range_latency_ms": 3.8103,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 10.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67108864,
    "peak_rss_bytes": 12563042304,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 5.54,
    "gbps_per_cpu_core": 214.749,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 20.328,
     "gbps": 13.2052
    },
    "verify": {
     "regions": [
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 1
   },
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 4294967296,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 197.0961,
    "aggregate_gbps": 10.8956,
    "steady_state_gbps": 12.5087,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 4294967296,
      "segment_end": 6442450944,
      "bytes_returned": 2147483648,
      "wall_ms": 186.5475,
      "gbps": 11.5117,
      "block_count": 16,
      "first_block_wall_ms": 10.0537,
      "block_timings_ms": [
       10.0537,
       10.2602,
       11.2645,
       17.8762,
       17.4552,
       12.3988,
       10.4593,
       10.2238,
       9.9781,
       10.9177,
       11.5082,
       10.3559,
       10.8283,
       10.2086,
       10.3068,
       10.7299
      ],
      "block_gbps": [
       13.3501,
       13.0814,
       11.9151,
       7.5082,
       7.6893,
       10.8251,
       12.8323,
       13.128,
       13.4512,
       12.2935,
       11.6628,
       12.9605,
       12.3951,
       13.1476,
       13.0222,
       12.5087
      ]
     }
    ],
    "first_range_latency_ms": 10.0537,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 10.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 12563042304,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 5.07,
    "gbps_per_cpu_core": 214.748,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 23.9628,
     "gbps": 11.2022
    },
    "verify": {
     "regions": [
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 2
   },
   {
    "kind": "raw_qd",
    "qd": 1,
    "worker_count": 1,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 6442450944,
    "window_len": 1602485248,
    "status": "ok",
    "bytes_returned": 1602485248,
    "expected_bytes": 1602485248,
    "total_wall_ms": 136.1286,
    "aggregate_gbps": 11.7718,
    "steady_state_gbps": null,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 6442450944,
      "segment_end": 8044936192,
      "bytes_returned": 1602485248,
      "wall_ms": 117.8391,
      "gbps": 13.5989,
      "block_count": 6,
      "first_block_wall_ms": 20.1276,
      "block_timings_ms": [
       20.1276,
       18.9382,
       19.6241,
       19.2849,
       20.6659,
       18.7254
      ],
      "block_gbps": [
       13.3367,
       14.1743,
       13.6789,
       13.9195,
       12.9893,
       13.9014
      ]
     }
    ],
    "first_range_latency_ms": 20.1276,
    "tail_spread_ms": 0.0,
    "process_cpu_ms": 20.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 268435456,
    "peak_rss_bytes": 12563042304,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 14.69,
    "gbps_per_cpu_core": 80.1239,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 20.6676,
     "gbps": 12.9882
    },
    "verify": {
     "regions": [
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 3
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 5897452544,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 104.1634,
    "aggregate_gbps": 20.6165,
    "steady_state_gbps": 13.3033,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 5897452544,
      "segment_end": 6971194368,
      "bytes_returned": 1073741824,
      "wall_ms": 77.5258,
      "gbps": 13.8501,
      "block_count": 32,
      "first_block_wall_ms": 2.372,
      "block_timings_ms": [
       2.372,
       2.6684,
       2.8024,
       2.2879,
       2.7408,
       2.3503,
       2.3058,
       2.4208,
       2.624,
       2.4742,
       2.7381,
       2.5616,
       2.4167,
       2.4937,
       2.3942,
       2.2759,
       2.7689,
       2.2107,
       2.218,
       2.0817,
       2.1498,
       2.1893,
       2.155,
       2.0634,
       2.0525,
       2.0826,
       2.1206,
       2.4448,
       2.4082,
       2.2829,
       2.9918,
       2.6202
      ],
      "block_gbps": [
       14.1458,
       12.575,
       11.9736,
       14.6661,
       12.2425,
       14.2768,
       14.5521,
       13.8609,
       12.7873,
       13.5615,
       12.2545,
       13.0993,
       13.8844,
       13.4558,
       14.0151,
       14.7434,
       12.1183,
       15.1781,
       15.1281,
       16.1187,
       15.6079,
       15.3263,
       15.5702,
       16.2614,
       16.3482,
       16.1114,
       15.8232,
       13.7246,
       13.9333,
       14.6983,
       11.2156,
       12.8063
      ]
     },
     {
      "worker": 1,
      "segment_start": 6971194368,
      "segment_end": 8044936192,
      "bytes_returned": 1073741824,
      "wall_ms": 91.7662,
      "gbps": 11.7008,
      "block_count": 32,
      "first_block_wall_ms": 3.4568,
      "block_timings_ms": [
       3.4568,
       3.0822,
       3.1784,
       2.8907,
       3.2863,
       3.0561,
       2.9014,
       2.5223,
       2.9597,
       2.6058,
       2.708,
       2.401,
       2.763,
       2.4951,
       2.1883,
       2.3297,
       3.2709,
       2.2294,
       2.1255,
       2.2651,
       1.8696,
       2.0922,
       3.7982,
       3.902,
       3.888,
       3.6058,
       2.8819,
       2.9397,
       3.0872,
       2.8459,
       2.7841,
       2.5463
      ],
      "block_gbps": [
       9.7067,
       10.8864,
       10.5571,
       11.6075,
       10.2103,
       10.9796,
       11.5649,
       13.3033,
       11.3373,
       12.8768,
       12.3911,
       13.9752,
       12.1441,
       13.4479,
       15.3337,
       14.4032,
       10.2585,
       15.0508,
       15.7866,
       14.8133,
       17.9478,
       16.0378,
       8.8343,
       8.5993,
       8.6303,
       9.3057,
       11.6433,
       11.4144,
       10.8691,
       11.7904,
       12.052,
       13.1779
      ]
     }
    ],
    "first_range_latency_ms": 2.372,
    "tail_spread_ms": 14.2404,
    "process_cpu_ms": 20.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 33558528,
    "peak_rss_bytes": 12563042304,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 19.2,
    "gbps_per_cpu_core": 107.3742,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 22.8074,
     "gbps": 11.7697
    },
    "verify": {
     "regions": [
      {
       "rel_start": 5897452544,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 4
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 5897452544,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 133.5624,
    "aggregate_gbps": 16.0785,
    "steady_state_gbps": 10.7768,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 5897452544,
      "segment_end": 6971194368,
      "bytes_returned": 1073741824,
      "wall_ms": 78.8977,
      "gbps": 13.6093,
      "block_count": 16,
      "first_block_wall_ms": 4.4708,
      "block_timings_ms": [
       4.4708,
       8.338,
       6.9109,
       5.8434,
       4.8505,
       4.9758,
       4.4505,
       4.3578,
       4.8394,
       4.4916,
       4.1778,
       4.2823,
       4.0459,
       4.1287,
       4.1526,
       4.1698
      ],
      "block_gbps": [
       15.0103,
       8.0485,
       9.7106,
       11.4845,
       13.8354,
       13.4869,
       15.0791,
       15.3998,
       13.8671,
       14.9411,
       16.0631,
       15.6714,
       16.5869,
       16.2541,
       16.1608,
       16.0941
      ]
     },
     {
      "worker": 1,
      "segment_start": 6971194368,
      "segment_end": 8044936192,
      "bytes_returned": 1073741824,
      "wall_ms": 108.2203,
      "gbps": 9.9218,
      "block_count": 16,
      "first_block_wall_ms": 4.2922,
      "block_timings_ms": [
       4.2922,
       7.6565,
       7.3712,
       6.8726,
       7.1332,
       6.5971,
       6.8117,
       6.2272,
       7.016,
       7.4362,
       7.0018,
       6.8577,
       6.8839,
       6.0953,
       6.3936,
       7.0197
      ],
      "block_gbps": [
       15.635,
       8.765,
       9.1042,
       9.7647,
       9.4079,
       10.1725,
       9.852,
       10.7768,
       9.5652,
       9.0247,
       9.5845,
       9.7859,
       9.7487,
       11.0099,
       10.4962,
       9.5601
      ]
     }
    ],
    "first_range_latency_ms": 4.2922,
    "tail_spread_ms": 29.3226,
    "process_cpu_ms": 60.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67108864,
    "peak_rss_bytes": 12563042304,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 44.92,
    "gbps_per_cpu_core": 35.7914,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 28.1668,
     "gbps": 9.5302
    },
    "verify": {
     "regions": [
      {
       "rel_start": 5897452544,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 5
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 113.7371,
    "aggregate_gbps": 18.8811,
    "steady_state_gbps": 14.9373,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 1073741824,
      "bytes_returned": 1073741824,
      "wall_ms": 68.8071,
      "gbps": 15.6051,
      "block_count": 8,
      "first_block_wall_ms": 7.9483,
      "block_timings_ms": [
       7.9483,
       7.9579,
       9.6102,
       8.4073,
       8.0881,
       8.6753,
       8.9944,
       8.8077
      ],
      "block_gbps": [
       16.8863,
       16.866,
       13.9662,
       15.9645,
       16.5946,
       15.4713,
       14.9224,
       15.2388
      ]
     },
     {
      "worker": 1,
      "segment_start": 1073741824,
      "segment_end": 2147483648,
      "bytes_returned": 1073741824,
      "wall_ms": 78.53,
      "gbps": 13.673,
      "block_count": 8,
      "first_block_wall_ms": 9.5737,
      "block_timings_ms": [
       9.5737,
       8.6598,
       8.9389,
       8.9854,
       11.0255,
       10.4999,
       10.1331,
       10.3738
      ],
      "block_gbps": [
       14.0194,
       15.499,
       15.015,
       14.9373,
       12.1734,
       12.7828,
       13.2455,
       12.9381
      ]
     }
    ],
    "first_range_latency_ms": 7.9483,
    "tail_spread_ms": 9.7229,
    "process_cpu_ms": 50.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 12563042304,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 43.96,
    "gbps_per_cpu_core": 42.9496,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.1653,
     "gbps": 14.7773
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 6
   },
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 2147483648,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 151.4848,
    "aggregate_gbps": 14.1762,
    "steady_state_gbps": 9.8099,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 2147483648,
      "segment_end": 3221225472,
      "bytes_returned": 1073741824,
      "wall_ms": 88.6377,
      "gbps": 12.1138,
      "block_count": 4,
      "first_block_wall_ms": 18.4306,
      "block_timings_ms": [
       18.4306,
       22.8009,
       18.9938,
       28.0488
      ],
      "block_gbps": [
       14.5647,
       11.773,
       14.1328,
       9.5703
      ]
     },
     {
      "worker": 1,
      "segment_start": 3221225472,
      "segment_end": 4294967296,
      "bytes_returned": 1073741824,
      "wall_ms": 116.2575,
      "gbps": 9.2359,
      "block_count": 4,
      "first_block_wall_ms": 33.943,
      "block_timings_ms": [
       33.943,
       28.2235,
       26.5352,
       27.3637
      ],
      "block_gbps": [
       7.9084,
       9.5111,
       10.1162,
       9.8099
      ]
     }
    ],
    "first_range_latency_ms": 18.4306,
    "tail_spread_ms": 27.6198,
    "process_cpu_ms": 50.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 268435456,
    "peak_rss_bytes": 13267697664,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 33.01,
    "gbps_per_cpu_core": 42.9496,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.9632,
     "gbps": 13.4465
    },
    "verify": {
     "regions": [
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 7
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 4294967296,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 105.9827,
    "aggregate_gbps": 20.2626,
    "steady_state_gbps": 9.513,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 4294967296,
      "segment_end": 4831838208,
      "bytes_returned": 536870912,
      "wall_ms": 73.3538,
      "gbps": 7.3189,
      "block_count": 16,
      "first_block_wall_ms": 2.5834,
      "block_timings_ms": [
       2.5834,
       6.8359,
       2.4686,
       5.2613,
       7.61,
       7.331,
       4.0835,
       3.6601,
       3.4007,
       8.0174,
       3.8408,
       3.5272,
       4.2567,
       3.1925,
       3.0639,
       3.8414
      ],
      "block_gbps": [
       12.9885,
       4.9085,
       13.5922,
       6.3776,
       4.4093,
       4.577,
       8.2172,
       9.1675,
       9.867,
       4.1852,
       8.7362,
       9.513,
       7.8827,
       10.5105,
       10.9517,
       8.735
      ]
     },
     {
      "worker": 1,
      "segment_start": 4831838208,
      "segment_end": 5368709120,
      "bytes_returned": 536870912,
      "wall_ms": 73.0266,
      "gbps": 7.3517,
      "block_count": 16,
      "first_block_wall_ms": 2.703,
      "block_timings_ms": [
       2.703,
       4.0889,
       3.6536,
       11.5811,
       3.6646,
       7.4664,
       3.9934,
       7.0954,
       4.2816,
       3.2728,
       3.175,
       3.406,
       3.1088,
       3.1531,
       3.0847,
       4.9394
      ],
      "block_gbps": [
       12.4138,
       8.2063,
       9.1841,
       2.8973,
       9.1565,
       4.494,
       8.4025,
       4.729,
       7.837,
       10.2525,
       10.5682,
       9.8516,
       10.7932,
       10.6416,
       10.8777,
       6.7932
      ]
     },
     {
      "worker": 2,
      "segment_start": 5368709120,
      "segment_end": 5905580032,
      "bytes_returned": 536870912,
      "wall_ms": 69.8867,
      "gbps": 7.682,
      "block_count": 16,
      "first_block_wall_ms": 14.4641,
      "block_timings_ms": [
       14.4641,
       3.673,
       4.3295,
       2.9269,
       3.8426,
       3.2942,
       3.1456,
       3.2263,
       7.7631,
       3.6294,
       3.2711,
       3.0237,
       2.797,
       3.874,
       3.0858,
       2.8431
      ],
      "block_gbps": [
       2.3198,
       9.1354,
       7.7502,
       11.4643,
       8.7322,
       10.1858,
       10.6671,
       10.4001,
       4.3223,
       9.2451,
       10.2579,
       11.097,
       11.9966,
       8.6614,
       10.8737,
       11.8022
      ]
     },
     {
      "worker": 3,
      "segment_start": 5905580032,
      "segment_end": 6442450944,
      "bytes_returned": 536870912,
      "wall_ms": 55.437,
      "gbps": 9.6844,
      "block_count": 16,
      "first_block_wall_ms": 5.4367,
      "block_timings_ms": [
       5.4367,
       3.4636,
       3.672,
       3.5628,
       3.4103,
       3.0185,
       3.213,
       3.7203,
       2.964,
       3.5314,
       3.2265,
       3.2174,
       3.2519,
       3.1967,
       3.0889,
       3.1771
      ],
      "block_gbps": [
       6.1719,
       9.6877,
       9.1379,
       9.418,
       9.8392,
       11.1163,
       10.4432,
       9.0193,
       11.3207,
       9.5016,
       10.3995,
       10.4291,
       10.3185,
       10.4967,
       10.8629,
       10.5613
      ]
     }
    ],
    "first_range_latency_ms": 2.5834,
    "tail_spread_ms": 17.9168,
    "process_cpu_ms": 160.0,
    "thread_cpu_ms": 30.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67264512,
    "peak_rss_bytes": 13267697664,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 150.97,
    "gbps_per_cpu_core": 13.4218,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.808,
     "gbps": 13.5519
    },
    "verify": {
     "regions": [
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 8
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 6442450944,
    "window_len": 1602485248,
    "status": "ok",
    "bytes_returned": 1602485248,
    "expected_bytes": 1602485248,
    "total_wall_ms": 93.3551,
    "aggregate_gbps": 17.1655,
    "steady_state_gbps": 9.296,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 6442450944,
      "segment_end": 6843072256,
      "bytes_returned": 400621312,
      "wall_ms": 48.7598,
      "gbps": 8.2162,
      "block_count": 6,
      "first_block_wall_ms": 4.953,
      "block_timings_ms": [
       4.953,
       5.2665,
       9.3493,
       6.1027,
       9.0999,
       13.7764
      ],
      "block_gbps": [
       13.5492,
       12.7425,
       7.178,
       10.9966,
       7.3747,
       4.7238
      ]
     },
     {
      "worker": 1,
      "segment_start": 6843072256,
      "segment_end": 7243693568,
      "bytes_returned": 400621312,
      "wall_ms": 55.8109,
      "gbps": 7.1782,
      "block_count": 6,
      "first_block_wall_ms": 4.8199,
      "block_timings_ms": [
       4.8199,
       9.5394,
       7.5576,
       21.0791,
       7.2853,
       5.3654
      ],
      "block_gbps": [
       13.9234,
       7.0349,
       8.8796,
       3.1837,
       9.2116,
       12.129
      ]
     },
     {
      "worker": 2,
      "segment_start": 7243693568,
      "segment_end": 7644314880,
      "bytes_returned": 400621312,
      "wall_ms": 63.6523,
      "gbps": 6.2939,
      "block_count": 6,
      "first_block_wall_ms": 23.5022,
      "block_timings_ms": [
       23.5022,
       11.5302,
       6.251,
       8.0263,
       7.1982,
       7.0005
      ],
      "block_gbps": [
       2.8554,
       5.8203,
       10.7356,
       8.3611,
       9.3231,
       9.296
      ]
     },
     {
      "worker": 3,
      "segment_start": 7644314880,
      "segment_end": 8044936192,
      "bytes_returned": 400621312,
      "wall_ms": 36.8815,
      "gbps": 10.8624,
      "block_count": 6,
      "first_block_wall_ms": 5.6625,
      "block_timings_ms": [
       5.6625,
       5.9286,
       6.4477,
       5.8271,
       5.7101,
       7.1044
      ],
      "block_gbps": [
       11.8514,
       11.3196,
       10.4081,
       11.5166,
       11.7526,
       9.1601
      ]
     }
    ],
    "first_range_latency_ms": 4.8199,
    "tail_spread_ms": 26.7708,
    "process_cpu_ms": 180.0,
    "thread_cpu_ms": 30.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 13267697664,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 192.81,
    "gbps_per_cpu_core": 8.9027,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.4234,
     "gbps": 14.5703
    },
    "verify": {
     "regions": [
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 9
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 5897452544,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 139.6179,
    "aggregate_gbps": 15.3811,
    "steady_state_gbps": 10.4149,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 5897452544,
      "segment_end": 6434323456,
      "bytes_returned": 536870912,
      "wall_ms": 55.8379,
      "gbps": 9.6148,
      "block_count": 4,
      "first_block_wall_ms": 8.4114,
      "block_timings_ms": [
       8.4114,
       9.5768,
       28.9084,
       8.7487
      ],
      "block_gbps": [
       15.9567,
       14.0149,
       4.6429,
       15.3414
      ]
     },
     {
      "worker": 1,
      "segment_start": 6434323456,
      "segment_end": 6971194368,
      "bytes_returned": 536870912,
      "wall_ms": 64.9434,
      "gbps": 8.2668,
      "block_count": 4,
      "first_block_wall_ms": 9.0884,
      "block_timings_ms": [
       9.0884,
       28.9956,
       8.276,
       9.7473
      ],
      "block_gbps": [
       14.768,
       4.6289,
       16.2176,
       13.7698
      ]
     },
     {
      "worker": 2,
      "segment_start": 6971194368,
      "segment_end": 7508065280,
      "bytes_returned": 536870912,
      "wall_ms": 62.1903,
      "gbps": 8.6327,
      "block_count": 4,
      "first_block_wall_ms": 21.8077,
      "block_timings_ms": [
       21.8077,
       14.1131,
       13.2212,
       12.887
      ],
      "block_gbps": [
       6.1546,
       9.5102,
       10.1517,
       10.4149
      ]
     },
     {
      "worker": 3,
      "segment_start": 7508065280,
      "segment_end": 8044936192,
      "bytes_returned": 536870912,
      "wall_ms": 52.1617,
      "gbps": 10.2924,
      "block_count": 4,
      "first_block_wall_ms": 14.3885,
      "block_timings_ms": [
       14.3885,
       12.9727,
       12.1479,
       12.5838
      ],
      "block_gbps": [
       9.3281,
       10.3462,
       11.0486,
       10.666
      ]
     }
    ],
    "first_range_latency_ms": 8.4114,
    "tail_spread_ms": 12.7817,
    "process_cpu_ms": 290.0,
    "thread_cpu_ms": 90.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 268435456,
    "peak_rss_bytes": 13267697664,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 207.71,
    "gbps_per_cpu_core": 7.4051,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.6783,
     "gbps": 14.3715
    },
    "verify": {
     "regions": [
      {
       "rel_start": 5897452544,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 10
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 5897452544,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 127.7654,
    "aggregate_gbps": 16.808,
    "steady_state_gbps": 10.3031,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 5897452544,
      "segment_end": 6434323456,
      "bytes_returned": 536870912,
      "wall_ms": 43.8156,
      "gbps": 12.253,
      "block_count": 2,
      "first_block_wall_ms": 18.2743,
      "block_timings_ms": [
       18.2743,
       25.4254
      ],
      "block_gbps": [
       14.6893,
       10.5578
      ]
     },
     {
      "worker": 1,
      "segment_start": 6434323456,
      "segment_end": 6971194368,
      "bytes_returned": 536870912,
      "wall_ms": 54.1762,
      "gbps": 9.9097,
      "block_count": 2,
      "first_block_wall_ms": 25.721,
      "block_timings_ms": [
       25.721,
       28.3946
      ],
      "block_gbps": [
       10.4364,
       9.4537
      ]
     },
     {
      "worker": 2,
      "segment_start": 6971194368,
      "segment_end": 7508065280,
      "bytes_returned": 536870912,
      "wall_ms": 83.2913,
      "gbps": 6.4457,
      "block_count": 2,
      "first_block_wall_ms": 51.23,
      "block_timings_ms": [
       51.23,
       32.0112
      ],
      "block_gbps": [
       5.2398,
       8.3857
      ]
     },
     {
      "worker": 3,
      "segment_start": 7508065280,
      "segment_end": 8044936192,
      "bytes_returned": 536870912,
      "wall_ms": 48.5357,
      "gbps": 11.0614,
      "block_count": 2,
      "first_block_wall_ms": 22.3941,
      "block_timings_ms": [
       22.3941,
       26.0538
      ],
      "block_gbps": [
       11.9869,
       10.3031
      ]
     }
    ],
    "first_range_latency_ms": 18.2743,
    "tail_spread_ms": 39.4757,
    "process_cpu_ms": 200.0,
    "thread_cpu_ms": 60.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 13277945856,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 156.54,
    "gbps_per_cpu_core": 10.7374,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.116,
     "gbps": 14.8176
    },
    "verify": {
     "regions": [
      {
       "rel_start": 5897452544,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 11
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 108.232,
    "aggregate_gbps": 19.8415,
    "steady_state_gbps": 7.1687,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 268435456,
      "bytes_returned": 268435456,
      "wall_ms": 73.4289,
      "gbps": 3.6557,
      "block_count": 8,
      "first_block_wall_ms": 2.1568,
      "block_timings_ms": [
       2.1568,
       3.0591,
       4.2509,
       3.8058,
       7.2759,
       10.1075,
       16.3039,
       26.0048
      ],
      "block_gbps": [
       15.5578,
       10.9687,
       7.8935,
       8.8166,
       4.6117,
       3.3198,
       2.0581,
       1.2903
      ]
     },
     {
      "worker": 1,
      "segment_start": 268435456,
      "segment_end": 536870912,
      "bytes_returned": 268435456,
      "wall_ms": 71.0353,
      "gbps": 3.7789,
      "block_count": 8,
      "first_block_wall_ms": 3.3436,
      "block_timings_ms": [
       3.3436,
       3.6855,
       11.4476,
       2.8596,
       2.9066,
       6.6134,
       5.0275,
       12.246
      ],
      "block_gbps": [
       10.0353,
       9.1043,
       2.9311,
       11.7341,
       11.5442,
       5.0737,
       6.6741,
       2.74
      ]
     },
     {
      "worker": 2,
      "segment_start": 536870912,
      "segment_end": 805306368,
      "bytes_returned": 268435456,
      "wall_ms": 55.606,
      "gbps": 4.8275,
      "block_count": 8,
      "first_block_wall_ms": 3.8159,
      "block_timings_ms": [
       3.8159,
       7.7352,
       3.6984,
       7.2992,
       6.1695,
       8.1316,
       4.9711,
       13.5003
      ],
      "block_gbps": [
       8.7932,
       4.3379,
       9.0728,
       4.597,
       5.4387,
       4.1264,
       6.7499,
       2.4855
      ]
     },
     {
      "worker": 3,
      "segment_start": 805306368,
      "segment_end": 1073741824,
      "bytes_returned": 268435456,
      "wall_ms": 68.4715,
      "gbps": 3.9204,
      "block_count": 8,
      "first_block_wall_ms": 3.9064,
      "block_timings_ms": [
       3.9064,
       14.718,
       5.3805,
       5.0704,
       4.1,
       9.9785,
       8.1159,
       4.4219
      ],
      "block_gbps": [
       8.5897,
       2.2798,
       6.2364,
       6.6177,
       8.184,
       3.3627,
       4.1344,
       7.5883
      ]
     },
     {
      "worker": 4,
      "segment_start": 1073741824,
      "segment_end": 1342177280,
      "bytes_returned": 268435456,
      "wall_ms": 45.6646,
      "gbps": 5.8784,
      "block_count": 8,
      "first_block_wall_ms": 5.4094,
      "block_timings_ms": [
       5.4094,
       7.9408,
       7.9372,
       5.0175,
       3.9586,
       3.7755,
       3.7885,
       3.4759
      ],
      "block_gbps": [
       6.2029,
       4.2256,
       4.2275,
       6.6874,
       8.4763,
       8.8875,
       8.857,
       9.6534
      ]
     },
     {
      "worker": 5,
      "segment_start": 1342177280,
      "segment_end": 1610612736,
      "bytes_returned": 268435456,
      "wall_ms": 43.4878,
      "gbps": 6.1727,
      "block_count": 8,
      "first_block_wall_ms": 7.793,
      "block_timings_ms": [
       7.793,
       12.0273,
       4.7374,
       4.1707,
       3.6777,
       3.5598,
       3.2066,
       3.7949
      ],
      "block_gbps": [
       4.3057,
       2.7899,
       7.0829,
       8.0452,
       9.1239,
       9.426,
       10.4643,
       8.8421
      ]
     },
     {
      "worker": 6,
      "segment_start": 1610612736,
      "segment_end": 1879048192,
      "bytes_returned": 268435456,
      "wall_ms": 42.472,
      "gbps": 6.3203,
      "block_count": 8,
      "first_block_wall_ms": 8.0511,
      "block_timings_ms": [
       8.0511,
       4.6417,
       4.2575,
       7.5444,
       6.7004,
       3.7932,
       3.6615,
       3.5685
      ],
      "block_gbps": [
       4.1677,
       7.229,
       7.8813,
       4.4476,
       5.0078,
       8.846,
       9.1641,
       9.403
      ]
     },
     {
      "worker": 7,
      "segment_start": 1879048192,
      "segment_end": 2147483648,
      "bytes_returned": 268435456,
      "wall_ms": 38.7682,
      "gbps": 6.9241,
      "block_count": 8,
      "first_block_wall_ms": 8.2081,
      "block_timings_ms": [
       8.2081,
       4.6807,
       4.1589,
       3.5653,
       3.7844,
       6.9874,
       4.0334,
       3.2378
      ],
      "block_gbps": [
       4.088,
       7.1687,
       8.0682,
       9.4115,
       8.8664,
       4.8021,
       8.3191,
       10.3634
      ]
     }
    ],
    "first_range_latency_ms": 2.1568,
    "tail_spread_ms": 34.6607,
    "process_cpu_ms": 300.0,
    "thread_cpu_ms": 50.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 101302272,
    "peak_rss_bytes": 13277945856,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 277.18,
    "gbps_per_cpu_core": 7.1583,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.4515,
     "gbps": 14.5482
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 12
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 2147483648,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 107.3726,
    "aggregate_gbps": 20.0003,
    "steady_state_gbps": 8.829,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 2147483648,
      "segment_end": 2415919104,
      "bytes_returned": 268435456,
      "wall_ms": 25.0313,
      "gbps": 10.724,
      "block_count": 4,
      "first_block_wall_ms": 4.361,
      "block_timings_ms": [
       4.361,
       5.1016,
       7.3522,
       7.8356
      ],
      "block_gbps": [
       15.3884,
       13.1544,
       9.1277,
       8.5646
      ]
     },
     {
      "worker": 1,
      "segment_start": 2415919104,
      "segment_end": 2684354560,
      "bytes_returned": 268435456,
      "wall_ms": 44.6315,
      "gbps": 6.0145,
      "block_count": 4,
      "first_block_wall_ms": 7.601,
      "block_timings_ms": [
       7.601,
       7.9334,
       9.2538,
       19.5836
      ],
      "block_gbps": [
       8.829,
       8.459,
       7.252,
       3.4268
      ]
     },
     {
      "worker": 2,
      "segment_start": 2684354560,
      "segment_end": 2952790016,
      "bytes_returned": 268435456,
      "wall_ms": 49.8619,
      "gbps": 5.3836,
      "block_count": 4,
      "first_block_wall_ms": 7.3277,
      "block_timings_ms": [
       7.3277,
       8.3769,
       16.8782,
       16.7999
      ],
      "block_gbps": [
       9.1583,
       8.0112,
       3.9761,
       3.9946
      ]
     },
     {
      "worker": 3,
      "segment_start": 2952790016,
      "segment_end": 3221225472,
      "bytes_returned": 268435456,
      "wall_ms": 54.577,
      "gbps": 4.9185,
      "block_count": 4,
      "first_block_wall_ms": 8.1203,
      "block_timings_ms": [
       8.1203,
       17.4183,
       22.271,
       6.6086
      ],
      "block_gbps": [
       8.2643,
       3.8528,
       3.0133,
       10.1548
      ]
     },
     {
      "worker": 4,
      "segment_start": 3221225472,
      "segment_end": 3489660928,
      "bytes_returned": 268435456,
      "wall_ms": 47.9074,
      "gbps": 5.6032,
      "block_count": 4,
      "first_block_wall_ms": 29.4544,
      "block_timings_ms": [
       29.4544,
       5.3802,
       6.4252,
       6.2649
      ],
      "block_gbps": [
       2.2784,
       12.4733,
       10.4447,
       10.7118
      ]
     },
     {
      "worker": 5,
      "segment_start": 3489660928,
      "segment_end": 3758096384,
      "bytes_returned": 268435456,
      "wall_ms": 46.1959,
      "gbps": 5.8108,
      "block_count": 4,
      "first_block_wall_ms": 21.7557,
      "block_timings_ms": [
       21.7557,
       6.4525,
       5.4348,
       5.6668
      ],
      "block_gbps": [
       3.0847,
       10.4005,
       12.3479,
       11.8425
      ]
     },
     {
      "worker": 6,
      "segment_start": 3758096384,
      "segment_end": 4026531840,
      "bytes_returned": 268435456,
      "wall_ms": 40.9724,
      "gbps": 6.5516,
      "block_count": 4,
      "first_block_wall_ms": 6.5803,
      "block_timings_ms": [
       6.5803,
       11.6009,
       12.0341,
       10.6316
      ],
      "block_gbps": [
       10.1984,
       5.7848,
       5.5766,
       6.3122
      ]
     },
     {
      "worker": 7,
      "segment_start": 4026531840,
      "segment_end": 4294967296,
      "bytes_returned": 268435456,
      "wall_ms": 22.4047,
      "gbps": 11.9812,
      "block_count": 4,
      "first_block_wall_ms": 4.9198,
      "block_timings_ms": [
       4.9198,
       6.64,
       5.2362,
       5.4501
      ],
      "block_gbps": [
       13.6405,
       10.1067,
       12.8164,
       12.3133
      ]
     }
    ],
    "first_range_latency_ms": 4.361,
    "tail_spread_ms": 32.1723,
    "process_cpu_ms": 300.0,
    "thread_cpu_ms": 60.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67108864,
    "peak_rss_bytes": 14107353088,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 279.4,
    "gbps_per_cpu_core": 7.1583,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 24.0878,
     "gbps": 11.1441
    },
    "verify": {
     "regions": [
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 13
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 4294967296,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 180.8264,
    "aggregate_gbps": 11.8759,
    "steady_state_gbps": 8.9937,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 4294967296,
      "segment_end": 4563402752,
      "bytes_returned": 268435456,
      "wall_ms": 30.9537,
      "gbps": 8.6722,
      "block_count": 2,
      "first_block_wall_ms": 14.9842,
      "block_timings_ms": [
       14.9842,
       15.7197
      ],
      "block_gbps": [
       8.9573,
       8.5382
      ]
     },
     {
      "worker": 1,
      "segment_start": 4563402752,
      "segment_end": 4831838208,
      "bytes_returned": 268435456,
      "wall_ms": 35.5381,
      "gbps": 7.5535,
      "block_count": 2,
      "first_block_wall_ms": 16.2385,
      "block_timings_ms": [
       16.2385,
       18.7973
      ],
      "block_gbps": [
       8.2654,
       7.1402
      ]
     },
     {
      "worker": 2,
      "segment_start": 4831838208,
      "segment_end": 5100273664,
      "bytes_returned": 268435456,
      "wall_ms": 29.9609,
      "gbps": 8.9595,
      "block_count": 2,
      "first_block_wall_ms": 18.9159,
      "block_timings_ms": [
       18.9159,
       10.8663
      ],
      "block_gbps": [
       7.0955,
       12.3518
      ]
     },
     {
      "worker": 3,
      "segment_start": 5100273664,
      "segment_end": 5368709120,
      "bytes_returned": 268435456,
      "wall_ms": 25.5568,
      "gbps": 10.5035,
      "block_count": 2,
      "first_block_wall_ms": 10.468,
      "block_timings_ms": [
       10.468,
       14.9235
      ],
      "block_gbps": [
       12.8217,
       8.9937
      ]
     },
     {
      "worker": 4,
      "segment_start": 5368709120,
      "segment_end": 5637144576,
      "bytes_returned": 268435456,
      "wall_ms": 40.8843,
      "gbps": 6.5657,
      "block_count": 2,
      "first_block_wall_ms": 13.8406,
      "block_timings_ms": [
       13.8406,
       26.9098
      ],
      "block_gbps": [
       9.6974,
       4.9877
      ]
     },
     {
      "worker": 5,
      "segment_start": 5637144576,
      "segment_end": 5905580032,
      "bytes_returned": 268435456,
      "wall_ms": 40.4162,
      "gbps": 6.6418,
      "block_count": 2,
      "first_block_wall_ms": 26.8432,
      "block_timings_ms": [
       26.8432,
       13.4367
      ],
      "block_gbps": [
       5.0001,
       9.9889
      ]
     },
     {
      "worker": 6,
      "segment_start": 5905580032,
      "segment_end": 6174015488,
      "bytes_returned": 268435456,
      "wall_ms": 26.2587,
      "gbps": 10.2227,
      "block_count": 2,
      "first_block_wall_ms": 12.7226,
      "block_timings_ms": [
       12.7226,
       13.4873
      ],
      "block_gbps": [
       10.5496,
       9.9514
      ]
     },
     {
      "worker": 7,
      "segment_start": 6174015488,
      "segment_end": 6442450944,
      "bytes_returned": 268435456,
      "wall_ms": 26.534,
      "gbps": 10.1167,
      "block_count": 2,
      "first_block_wall_ms": 13.111,
      "block_timings_ms": [
       13.111,
       13.3074
      ],
      "block_gbps": [
       10.237,
       10.086
      ]
     }
    ],
    "first_range_latency_ms": 10.468,
    "tail_spread_ms": 15.3275,
    "process_cpu_ms": 330.0,
    "thread_cpu_ms": 80.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 14107353088,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 182.5,
    "gbps_per_cpu_core": 6.5075,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 19.4325,
     "gbps": 13.8137
    },
    "verify": {
     "regions": [
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 14
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 256,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 6442450944,
    "window_len": 1602485248,
    "status": "ok",
    "bytes_returned": 1602485248,
    "expected_bytes": 1602485248,
    "total_wall_ms": 171.4946,
    "aggregate_gbps": 9.3442,
    "steady_state_gbps": 9.5435,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 6442450944,
      "segment_end": 6642761600,
      "bytes_returned": 200310656,
      "wall_ms": 20.5906,
      "gbps": 9.7282,
      "block_count": 1,
      "first_block_wall_ms": 20.5056,
      "block_timings_ms": [
       20.5056
      ],
      "block_gbps": [
       9.7686
      ]
     },
     {
      "worker": 1,
      "segment_start": 6642761600,
      "segment_end": 6843072256,
      "bytes_returned": 200310656,
      "wall_ms": 14.5844,
      "gbps": 13.7345,
      "block_count": 1,
      "first_block_wall_ms": 14.5133,
      "block_timings_ms": [
       14.5133
      ],
      "block_gbps": [
       13.8018
      ]
     },
     {
      "worker": 2,
      "segment_start": 6843072256,
      "segment_end": 7043382912,
      "bytes_returned": 200310656,
      "wall_ms": 14.8307,
      "gbps": 13.5065,
      "block_count": 1,
      "first_block_wall_ms": 14.772,
      "block_timings_ms": [
       14.772
      ],
      "block_gbps": [
       13.5602
      ]
     },
     {
      "worker": 3,
      "segment_start": 7043382912,
      "segment_end": 7243693568,
      "bytes_returned": 200310656,
      "wall_ms": 31.7111,
      "gbps": 6.3167,
      "block_count": 1,
      "first_block_wall_ms": 31.6366,
      "block_timings_ms": [
       31.6366
      ],
      "block_gbps": [
       6.3316
      ]
     },
     {
      "worker": 4,
      "segment_start": 7243693568,
      "segment_end": 7444004224,
      "bytes_returned": 200310656,
      "wall_ms": 27.5785,
      "gbps": 7.2633,
      "block_count": 1,
      "first_block_wall_ms": 27.507,
      "block_timings_ms": [
       27.507
      ],
      "block_gbps": [
       7.2822
      ]
     },
     {
      "worker": 5,
      "segment_start": 7444004224,
      "segment_end": 7644314880,
      "bytes_returned": 200310656,
      "wall_ms": 22.3923,
      "gbps": 8.9455,
      "block_count": 1,
      "first_block_wall_ms": 22.3246,
      "block_timings_ms": [
       22.3246
      ],
      "block_gbps": [
       8.9727
      ]
     },
     {
      "worker": 6,
      "segment_start": 7644314880,
      "segment_end": 7844625536,
      "bytes_returned": 200310656,
      "wall_ms": 15.5263,
      "gbps": 12.9013,
      "block_count": 1,
      "first_block_wall_ms": 15.4655,
      "block_timings_ms": [
       15.4655
      ],
      "block_gbps": [
       12.9521
      ]
     },
     {
      "worker": 7,
      "segment_start": 7844625536,
      "segment_end": 8044936192,
      "bytes_returned": 200310656,
      "wall_ms": 21.0721,
      "gbps": 9.506,
      "block_count": 1,
      "first_block_wall_ms": 20.9893,
      "block_timings_ms": [
       20.9893
      ],
      "block_gbps": [
       9.5435
      ]
     }
    ],
    "first_range_latency_ms": 14.5133,
    "tail_spread_ms": 17.1267,
    "process_cpu_ms": 300.0,
    "thread_cpu_ms": 90.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 14107353088,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 174.93,
    "gbps_per_cpu_core": 5.3416,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 20.7965,
     "gbps": 12.9077
    },
    "verify": {
     "regions": [
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 15
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "dynamic",
    "window_start": 5897452544,
    "window_len": 2147483648,
    "status": "ok",
    "bytes_returned": 2147483648,
    "expected_bytes": 2147483648,
    "total_wall_ms": 94.3849,
    "aggregate_gbps": 22.7524,
    "steady_state_gbps": null,
    "per_worker": [
     {
      "worker": 0,
      "schedule": "dynamic",
      "bytes_returned": 603979776,
      "wall_ms": 88.4496,
      "gbps": 6.8285,
      "block_count": 9,
      "first_block_wall_ms": 4.7273
     },
     {
      "worker": 1,
      "schedule": "dynamic",
      "bytes_returned": 469762048,
      "wall_ms": 78.1374,
      "gbps": 6.012,
      "block_count": 7,
      "first_block_wall_ms": 4.6487
     },
     {
      "worker": 2,
      "schedule": "dynamic",
      "bytes_returned": 402653184,
      "wall_ms": 65.6151,
      "gbps": 6.1366,
      "block_count": 6,
      "first_block_wall_ms": 9.8182
     },
     {
      "worker": 3,
      "schedule": "dynamic",
      "bytes_returned": 335544320,
      "wall_ms": 62.9635,
      "gbps": 5.3292,
      "block_count": 5,
      "first_block_wall_ms": 8.4232
     },
     {
      "worker": 4,
      "schedule": "dynamic",
      "bytes_returned": 201326592,
      "wall_ms": 45.8801,
      "gbps": 4.3881,
      "block_count": 3,
      "first_block_wall_ms": 12.5513
     },
     {
      "worker": 5,
      "schedule": "dynamic",
      "bytes_returned": 67108864,
      "wall_ms": 46.4068,
      "gbps": 1.4461,
      "block_count": 1,
      "first_block_wall_ms": 12.5854
     },
     {
      "worker": 6,
      "schedule": "dynamic",
      "bytes_returned": 67108864,
      "wall_ms": 30.308,
      "gbps": 2.2142,
      "block_count": 1,
      "first_block_wall_ms": 5.1464
     },
     {
      "worker": 7,
      "schedule": "dynamic",
      "bytes_returned": 0,
      "wall_ms": 0.002,
      "gbps": 0.0,
      "block_count": 0,
      "first_block_wall_ms": 0.0
     }
    ],
    "first_range_latency_ms": 0.0,
    "tail_spread_ms": 88.4476,
    "process_cpu_ms": 440.0,
    "thread_cpu_ms": 110.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 14107353088,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 466.18,
    "gbps_per_cpu_core": 4.8806,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 20.6391,
     "gbps": 13.0062
    },
    "verify": {
     "regions": [
      {
       "rel_start": 5897452544,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    },
    "_idx": 16
   }
  ],
  "fullfile_qd16_included": true,
  "fullfile_warm_qd1_control": {
   "kind": "raw_qd",
   "qd": 1,
   "worker_count": 1,
   "block_mib": 32,
   "syscall_bytes": 33554432,
   "schedule": "static",
   "window_start": 0,
   "window_len": 8044936192,
   "status": "ok",
   "bytes_returned": 8044936192,
   "expected_bytes": 8044936192,
   "total_wall_ms": 753.9366,
   "aggregate_gbps": 10.6706,
   "steady_state_gbps": 11.0513,
   "per_worker": [
    {
     "worker": 0,
     "segment_start": 0,
     "segment_end": 8044936192,
     "bytes_returned": 8044936192,
     "wall_ms": 752.8878,
     "gbps": 10.6854,
     "block_count": 240,
     "first_block_wall_ms": 3.3054,
     "block_timings_ms": [
      3.3054,
      3.1431,
      3.4368,
      2.9832,
      3.0037,
      2.9168,
      3.2293,
      2.8228,
      3.0674,
      2.8264,
      2.4509,
      2.6701,
      2.3487,
      2.3013,
      2.3404,
      2.338,
      2.4054,
      3.7097,
      3.6083,
      3.3278,
      3.9729,
      3.1049,
      2.8645,
      3.4182,
      2.9715,
      2.7239,
      3.0891,
      2.8739,
      3.0618,
      3.0013,
      3.1743,
      2.9272,
      2.8066,
      3.0829,
      3.4164,
      2.9342,
      2.7963,
      2.7159,
      2.7765,
      2.7509,
      2.974,
      2.5731,
      2.5089,
      2.8998,
      2.4905,
      2.4476,
      2.5263,
      2.7464,
      3.0024,
      3.7827,
      3.8145,
      3.1925,
      3.7663,
      2.7665,
      2.8571,
      2.694,
      2.5688,
      2.8526,
      2.9166,
      2.6316,
      2.6554,
      2.7302,
      2.4543,
      3.6243,
      3.6512,
      3.4646,
      3.5415,
      3.0759,
      3.0167,
      3.0394,
      3.1503,
      3.3113,
      3.7122,
      4.1617,
      3.3403,
      3.3801,
      4.21,
      3.0073,
      3.1976,
      3.4913,
      3.8512,
      3.651,
      3.7504,
      3.7204,
      3.5196,
      3.934,
      4.0367,
      3.1476,
      3.0234,
      3.3001,
      2.8116,
      3.628,
      3.2753,
      3.6672,
      2.9998,
      2.8529,
      2.7585,
      2.6896,
      2.6672,
      3.475,
      3.1778,
      3.4124,
      3.5303,
      3.3401,
      3.0302,
      3.2237,
      3.4295,
      3.4212,
      3.4539,
      2.9995,
      2.9389,
      3.8804,
      3.3459,
      3.2221,
      3.4439,
      3.0179,
      2.9006,
      3.5296,
      3.3502,
      3.1839,
      3.6572,
      3.359,
      3.063,
      3.0191,
      2.9675,
      2.9924,
      3.3297,
      3.0002,
      3.2516,
      3.0612,
      3.2487,
      3.071,
      2.9983,
      3.8333,
      2.9689,
      3.5284,
      3.1356,
      3.1445,
      3.3605,
      3.7534,
      3.976,
      3.0879,
      3.4937,
      4.2453,
      3.8883,
      3.4563,
      3.0903,
      3.3992,
      2.9431,
      3.2454,
      2.8184,
      2.854,
      2.9906,
      2.8981,
      2.8136,
      2.9509,
      3.326,
      2.7937,
      2.846,
      3.308,
      2.8493,
      3.0939,
      2.7375,
      2.7944,
      3.0363,
      2.6935,
      3.6821,
      3.527,
      3.5037,
      3.2102,
      2.9445,
      2.9766,
      2.8487,
      2.9223,
      2.7083,
      2.5349,
      2.615,
      2.5576,
      2.6537,
      2.8076,
      2.6896,
      2.5139,
      2.6038,
      2.6228,
      3.9334,
      3.4806,
      3.6268,
      3.0281,
      3.2061,
      2.814,
      2.8163,
      2.7986,
      3.2632,
      2.7221,
      2.9108,
      2.6739,
      2.8885,
      4.4746,
      3.3661,
      3.2494,
      3.2851,
      2.9635,
      2.8591,
      2.8369,
      2.8103,
      3.2276,
      3.1581,
      3.1579,
      4.0131,
      3.7863,
      3.2572,
      3.168,
      3.7297,
      3.8014,
      3.4953,
      3.0785,
      3.4463,
      2.9232,
      3.014,
      2.8405,
      3.4297,
      2.9619,
      2.8348,
      2.7951,
      3.5476,
      2.7625,
      2.8882,
      3.4362,
      3.5126,
      3.025,
      3.2979,
      2.7875,
      2.4967,
      2.6054,
      2.7163,
      2.3565,
      2.1364,
      2.4535,
      2.6373,
      2.5478
     ],
     "block_gbps": [
      10.1514,
      10.6754,
      9.7632,
      11.2478,
      11.1712,
      11.5037,
      10.3908,
      11.8869,
      10.9389,
      11.8717,
      13.6908,
      12.5669,
      14.2862,
      14.5808,
      14.3369,
      14.3516,
      13.9497,
      9.045,
      9.2993,
      10.0829,
      8.4458,
      10.8068,
      11.7138,
      9.8163,
      11.2919,
      12.3184,
      10.8622,
      11.6758,
      10.9592,
      11.1799,
      10.5708,
      11.463,
      11.9554,
      10.884,
      9.8215,
      11.4357,
      11.9998,
      12.3548,
      12.0853,
      12.1978,
      11.2826,
      13.0405,
      13.3743,
      11.5712,
      13.4732,
      13.7093,
      13.2818,
      12.2175,
      11.176,
      8.8704,
      8.7965,
      10.5103,
      8.9091,
      12.1289,
      11.7443,
      12.4551,
      13.0623,
      11.7628,
      11.5045,
      12.7506,
      12.6363,
      12.2903,
      13.6717,
      9.2581,
      9.19,
      9.685,
      9.4747,
      10.9087,
      11.1227,
      11.0397,
      10.6512,
      10.1332,
      9.039,
      8.0627,
      10.0455,
      9.9269,
      7.9703,
      11.1576,
      10.4936,
      9.611,
      8.7128,
      9.1905,
      8.9469,
      9.0191,
      9.5336,
      8.5293,
      8.3124,
      10.6604,
      11.0982,
      10.1678,
      11.9343,
      9.2488,
      10.2448,
      9.1498,
      11.1857,
      11.7615,
      12.1638,
      12.4756,
      12.5806,
      9.656,
      10.5589,
      9.8331,
      9.5047,
      10.0459,
      11.0734,
      10.4086,
      9.7842,
      9.8077,
      9.7149,
      11.1866,
      11.4175,
      8.6471,
      10.0285,
      10.4138,
      9.743,
      11.1183,
      11.5682,
      9.5067,
      10.0158,
      10.5386,
      9.175,
      9.9894,
      10.9549,
      11.1139,
      11.3074,
      11.2133,
      10.0772,
      11.1842,
      10.3193,
      10.9613,
      10.3285,
      10.9262,
      11.1913,
      8.7534,
      11.3019,
      9.5098,
      10.701,
      10.6708,
      9.9848,
      8.9397,
      8.4392,
      10.8663,
      9.6042,
      7.9039,
      8.6296,
      9.7082,
      10.8581,
      9.8714,
      11.4009,
      10.3391,
      11.9056,
      11.7569,
      11.22,
      11.5781,
      11.9257,
      11.3709,
      10.0886,
      12.0107,
      11.79,
      10.1434,
      11.7766,
      10.8453,
      12.2573,
      12.0077,
      11.0513,
      12.4574,
      9.1128,
      9.5136,
      9.5769,
      10.4525,
      11.3958,
      11.2726,
      11.779,
      11.4823,
      12.3894,
      13.2369,
      12.8317,
      13.1196,
      12.6442,
      11.9514,
      12.4755,
      13.3477,
      12.8865,
      12.7936,
      8.5306,
      9.6405,
      9.2518,
      11.0811,
      10.466,
      11.9243,
      11.9145,
      11.9899,
      10.2825,
      12.3266,
      11.5276,
      12.5486,
      11.6164,
      7.4988,
      9.9683,
      10.3262,
      10.2141,
      11.3226,
      11.7359,
      11.8279,
      11.9397,
      10.396,
      10.6248,
      10.6255,
      8.3613,
      8.862,
      10.3015,
      10.5918,
      8.9966,
      8.8268,
      9.5998,
      10.8994,
      9.7365,
      11.4788,
      11.133,
      11.8128,
      9.7834,
      11.3287,
      11.8365,
      12.0047,
      9.4584,
      12.1465,
      11.6176,
      9.7651,
      9.5526,
      11.0925,
      10.1745,
      12.0376,
      13.4395,
      12.8786,
      12.3529,
      14.2392,
      15.7064,
      13.6763,
      12.7228,
      9.9799
     ]
    }
   ],
   "first_range_latency_ms": 3.3054,
   "tail_spread_ms": 0.0,
   "process_cpu_ms": 80.0,
   "thread_cpu_ms": 0.0,
   "minflt_delta": 0,
   "majflt_delta": 0,
   "ctxt_switches_delta": null,
   "rss_delta_bytes": 0,
   "peak_rss_bytes": 14510006272,
   "peak_pinned_bytes": 0,
   "cpu_cores": 28,
   "cpu_utilization_pct": 10.61,
   "gbps_per_cpu_core": 100.562,
   "warm_repeat": {
    "bytes": 268435456,
    "wall_ms": 23.7491,
    "gbps": 11.303
   },
   "verify": {
    "regions": [
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 8044674048,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 0,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536608768,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 536870912,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073479680,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1073741824,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610350592,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 1610612736,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147221504,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2147483648,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684092416,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 2684354560,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3220963328,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3221225472,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3757834240,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 3758096384,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294705152,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4294967296,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831576064,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 4831838208,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368446976,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5368709120,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905317888,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 5905580032,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442188800,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6442450944,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979059712,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 6979321856,
      "bytes": 262144,
      "hash_match": true
     },
     {
      "rel_start": 7515930624,
      "bytes": 262144,
      "hash_match": true
     }
    ],
    "all_match": true
   }
  },
  "fullfile": [
   {
    "kind": "raw_qd",
    "qd": 2,
    "worker_count": 2,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 8044936192,
    "status": "ok",
    "bytes_returned": 8044936192,
    "expected_bytes": 8044936192,
    "total_wall_ms": 403.0246,
    "aggregate_gbps": 19.9614,
    "steady_state_gbps": 11.298,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 4022468096,
      "bytes_returned": 4022468096,
      "wall_ms": 382.1486,
      "gbps": 10.5259,
      "block_count": 120,
      "first_block_wall_ms": 2.5266,
      "block_timings_ms": [
       2.5266,
       3.0333,
       2.9626,
       2.8461,
       2.6339,
       3.1156,
       3.2839,
       2.8348,
       2.7056,
       2.5693,
       3.0821,
       3.0581,
       2.97,
       2.6426,
       2.4068,
       2.2043,
       2.3021,
       5.1246,
       4.0576,
       2.4213,
       2.2848,
       2.2006,
       2.3997,
       2.3626,
       2.8157,
       2.3608,
       2.7064,
       2.3033,
       2.2941,
       2.2942,
       2.4756,
       1.871,
       2.0181,
       2.2927,
       3.401,
       2.5821,
       2.2258,
       5.698,
       5.016,
       4.4754,
       5.449,
       4.6681,
       4.7918,
       4.6302,
       3.5079,
       3.5256,
       3.0734,
       2.8129,
       3.3159,
       2.7747,
       2.6599,
       3.0319,
       2.6876,
       2.5668,
       2.5974,
       2.7485,
       2.66,
       3.227,
       3.0503,
       2.5452,
       2.486,
       5.039,
       4.3272,
       4.9765,
       3.3667,
       3.2933,
       3.1613,
       3.1318,
       2.6141,
       2.4947,
       2.5584,
       2.3981,
       2.6534,
       3.1331,
       2.6015,
       3.0928,
       3.8853,
       2.6024,
       2.5465,
       3.2928,
       2.5129,
       3.1208,
       2.8688,
       2.4377,
       2.553,
       2.5447,
       2.2799,
       2.1418,
       2.2593,
       2.8319,
       2.4896,
       2.6906,
       4.2816,
       4.9241,
       4.6973,
       2.8707,
       2.8848,
       2.8013,
       2.4142,
       4.7753,
       2.8715,
       2.8891,
       2.3123,
       2.517,
       2.515,
       2.0813,
       5.7203,
       4.401,
       4.1013,
       4.1315,
       4.1191,
       3.9564,
       3.876,
       3.8019,
       3.5192,
       3.4174,
       4.7107,
       4.175,
       4.5234,
       3.2728
      ],
      "block_gbps": [
       13.2805,
       11.0619,
       11.326,
       11.7895,
       12.7396,
       10.7697,
       10.2178,
       11.8365,
       12.4017,
       13.0598,
       10.887,
       10.9721,
       11.298,
       12.6975,
       13.9414,
       15.2222,
       14.5753,
       6.5477,
       8.2696,
       13.8582,
       14.6857,
       15.248,
       13.9827,
       14.2022,
       11.9169,
       14.213,
       12.3984,
       14.568,
       14.6265,
       14.6257,
       13.5538,
       17.934,
       16.6268,
       14.6351,
       9.8662,
       12.995,
       15.075,
       5.8888,
       6.6895,
       7.4975,
       6.1579,
       7.188,
       7.0025,
       7.2468,
       9.5655,
       9.5173,
       10.9175,
       11.9289,
       10.1192,
       12.093,
       12.6151,
       11.067,
       12.4849,
       13.0723,
       12.9186,
       12.2082,
       12.6143,
       10.398,
       11.0003,
       13.1837,
       13.4971,
       6.6589,
       7.7543,
       6.7426,
       9.9665,
       10.1886,
       10.6141,
       10.7142,
       12.8358,
       13.4503,
       13.1153,
       13.9922,
       12.6458,
       10.7098,
       12.8981,
       10.8491,
       8.6361,
       12.8935,
       13.1765,
       10.1902,
       13.3528,
       10.7519,
       11.6962,
       13.7648,
       13.1432,
       13.1861,
       14.7176,
       15.6663,
       14.8517,
       11.8489,
       13.4781,
       12.471,
       7.8368,
       6.8143,
       7.1434,
       11.6887,
       11.6315,
       11.9782,
       13.899,
       7.0266,
       11.6852,
       11.6141,
       14.5112,
       13.3311,
       13.3415,
       16.1216,
       5.8659,
       7.6244,
       8.1813,
       8.1216,
       8.1461,
       8.4809,
       8.6571,
       8.8258,
       9.5346,
       9.8186,
       7.1231,
       8.0371,
       7.418,
       9.0108
      ]
     },
     {
      "worker": 1,
      "segment_start": 4022468096,
      "segment_end": 8044936192,
      "bytes_returned": 4022468096,
      "wall_ms": 399.0148,
      "gbps": 10.081,
      "block_count": 120,
      "first_block_wall_ms": 2.3954,
      "block_timings_ms": [
       2.3954,
       2.6947,
       3.0292,
       2.5062,
       2.9416,
       3.9282,
       3.6498,
       3.2266,
       2.8473,
       3.2687,
       2.6457,
       2.7469,
       3.1937,
       2.7879,
       2.3563,
       4.2707,
       5.4237,
       3.4635,
       3.1938,
       3.1849,
       3.8691,
       2.9938,
       3.1092,
       3.1999,
       6.0945,
       2.9759,
       2.8983,
       3.0625,
       2.7739,
       3.309,
       3.9299,
       5.0419,
       4.3243,
       5.8742,
       4.3495,
       5.3196,
       4.5835,
       2.9931,
       4.356,
       4.095,
       3.1433,
       3.6241,
       3.6537,
       3.5445,
       3.3064,
       3.1282,
       3.602,
       3.2299,
       3.2212,
       2.4242,
       2.5834,
       2.5602,
       3.1007,
       3.1668,
       3.4585,
       5.0528,
       3.9254,
       3.2578,
       2.5608,
       2.8653,
       3.6531,
       2.2802,
       2.6253,
       2.9252,
       2.6367,
       2.6743,
       2.4876,
       2.9596,
       2.9686,
       2.606,
       2.2776,
       2.1205,
       2.8248,
       2.286,
       2.1072,
       1.9738,
       1.9829,
       2.1116,
       2.8503,
       2.2518,
       2.0608,
       2.1048,
       2.2835,
       1.8511,
       2.259,
       2.6251,
       2.2864,
       2.328,
       4.447,
       4.3454,
       3.6508,
       2.9347,
       3.0075,
       3.2173,
       4.1323,
       2.5829,
       3.3938,
       2.5751,
       3.0365,
       2.5832,
       4.3088,
       5.0278,
       4.3371,
       4.4349,
       5.2189,
       4.0988,
       4.0838,
       4.129,
       2.6635,
       2.6614,
       2.2895,
       5.6165,
       5.8327,
       4.1182,
       2.9293,
       3.9932,
       3.3851,
       3.1639,
       3.1641,
       2.1508
      ],
      "block_gbps": [
       14.008,
       12.4521,
       11.0771,
       13.3883,
       11.4068,
       8.542,
       9.1935,
       10.3992,
       11.7847,
       10.2654,
       12.6824,
       12.2152,
       10.5066,
       12.0357,
       14.2402,
       7.8569,
       6.1866,
       9.688,
       10.506,
       10.5355,
       8.6724,
       11.2078,
       10.7919,
       10.4862,
       5.5057,
       11.2752,
       11.5774,
       10.9567,
       12.0967,
       10.1405,
       8.5383,
       6.6552,
       7.7594,
       5.7122,
       7.7146,
       6.3077,
       7.3207,
       11.2105,
       7.7031,
       8.1941,
       10.6748,
       9.2587,
       9.1837,
       9.4665,
       10.1483,
       10.7265,
       9.3156,
       10.3888,
       10.4168,
       13.8413,
       12.9882,
       13.1061,
       10.8216,
       10.5957,
       9.7021,
       6.6407,
       8.5481,
       10.2997,
       13.103,
       11.7105,
       9.1851,
       14.7154,
       12.7814,
       11.4708,
       12.726,
       12.547,
       13.4887,
       11.3374,
       11.3032,
       12.876,
       14.7326,
       15.824,
       11.8785,
       14.6782,
       15.9238,
       17.0003,
       16.9216,
       15.8908,
       11.7722,
       14.9009,
       16.2819,
       15.9422,
       14.6941,
       18.1271,
       14.8535,
       12.7824,
       14.6759,
       14.4137,
       7.5454,
       7.7217,
       9.191,
       11.4337,
       11.1568,
       10.4295,
       8.1201,
       12.9911,
       9.887,
       13.0301,
       11.0502,
       12.9895,
       7.7874,
       6.6737,
       7.7366,
       7.5661,
       6.4294,
       8.1864,
       8.2166,
       8.1265,
       12.5978,
       12.6077,
       14.6559,
       5.9742,
       5.7528,
       8.1478,
       11.4549,
       8.4029,
       9.9124,
       10.6055,
       10.6047,
       13.7117
      ]
     }
    ],
    "first_range_latency_ms": 2.3954,
    "tail_spread_ms": 16.8662,
    "process_cpu_ms": 70.0,
    "thread_cpu_ms": 0.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 14107353088,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 17.37,
    "gbps_per_cpu_core": 114.9277,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 31.0134,
     "gbps": 8.6555
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   },
   {
    "kind": "raw_qd",
    "qd": 4,
    "worker_count": 4,
    "block_mib": 32,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 8044936192,
    "status": "ok",
    "bytes_returned": 8044936192,
    "expected_bytes": 8044936192,
    "total_wall_ms": 191.4249,
    "aggregate_gbps": 42.0266,
    "steady_state_gbps": 12.4556,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 2011234048,
      "bytes_returned": 2011234048,
      "wall_ms": 181.1301,
      "gbps": 11.1038,
      "block_count": 60,
      "first_block_wall_ms": 2.3886,
      "block_timings_ms": [
       2.3886,
       3.1916,
       3.5954,
       2.4687,
       2.0886,
       2.0951,
       2.0115,
       2.3582,
       2.9284,
       3.1625,
       3.062,
       2.8499,
       2.8052,
       2.8822,
       2.5836,
       2.7076,
       2.7716,
       2.6349,
       2.4725,
       2.429,
       2.4966,
       2.5205,
       2.7269,
       2.8801,
       3.7386,
       3.1096,
       3.7262,
       3.0248,
       3.5159,
       3.0393,
       4.3077,
       3.4003,
       2.9309,
       3.2255,
       4.3641,
       3.5082,
       3.4523,
       3.1002,
       3.4529,
       2.6114,
       3.3778,
       2.4432,
       2.3716,
       2.9432,
       4.2581,
       2.99,
       2.9504,
       3.0497,
       3.1602,
       2.6841,
       2.7117,
       2.8146,
       2.8611,
       3.2725,
       3.582,
       3.5086,
       2.216,
       3.3463,
       3.5408,
       2.5347
      ],
      "block_gbps": [
       14.0475,
       10.5133,
       9.3326,
       13.5921,
       16.0659,
       16.0157,
       16.6809,
       14.229,
       11.4585,
       10.61,
       10.9585,
       11.7739,
       11.9613,
       11.6419,
       12.9875,
       12.3927,
       12.1066,
       12.7346,
       13.5709,
       13.8139,
       13.4402,
       13.3128,
       12.3048,
       11.6503,
       8.9752,
       10.7907,
       9.005,
       11.093,
       9.5437,
       11.0402,
       7.7894,
       9.8681,
       11.4485,
       10.4029,
       7.6887,
       9.5645,
       9.7193,
       10.8232,
       9.7178,
       12.8494,
       9.9337,
       13.7339,
       14.1482,
       11.4007,
       7.8802,
       11.2223,
       11.3727,
       11.0024,
       10.6179,
       12.5012,
       12.3741,
       11.9215,
       11.728,
       10.2535,
       9.3676,
       9.5635,
       15.1418,
       10.0272,
       9.4765,
       12.4365
      ]
     },
     {
      "worker": 1,
      "segment_start": 2011234048,
      "segment_end": 4022468096,
      "bytes_returned": 2011234048,
      "wall_ms": 139.3467,
      "gbps": 14.4333,
      "block_count": 60,
      "first_block_wall_ms": 3.567,
      "block_timings_ms": [
       3.567,
       3.2356,
       2.3421,
       2.5662,
       2.2601,
       2.2465,
       2.6007,
       3.2564,
       3.5554,
       2.6997,
       2.6935,
       2.0253,
       1.8848,
       2.0707,
       2.3671,
       2.767,
       3.1163,
       2.1984,
       2.3089,
       3.0572,
       2.6048,
       2.3635,
       2.2235,
       2.1828,
       2.2864,
       2.0644,
       1.9673,
       3.3812,
       3.1167,
       4.0696,
       3.3299,
       2.1435,
       2.1653,
       2.1331,
       1.9993,
       1.9604,
       1.8819,
       1.9232,
       1.9433,
       2.4603,
       2.2223,
       1.8876,
       1.7717,
       1.7368,
       1.8406,
       1.9336,
       1.8871,
       1.8245,
       1.7809,
       1.89,
       1.8781,
       1.7267,
       1.8441,
       1.8552,
       1.8107,
       1.8373,
       1.9539,
       1.8088,
       1.9793,
       1.723
      ],
      "block_gbps": [
       9.407,
       10.3703,
       14.3268,
       13.0756,
       14.8467,
       14.9362,
       12.9019,
       10.3043,
       9.4377,
       12.4291,
       12.4576,
       16.5679,
       17.8025,
       16.204,
       14.1754,
       12.1266,
       10.7675,
       15.2629,
       14.5324,
       10.9756,
       12.8816,
       14.1967,
       15.0905,
       15.3721,
       14.6759,
       16.2537,
       17.0557,
       9.9237,
       10.7662,
       8.2451,
       10.0766,
       15.6538,
       15.4965,
       15.7302,
       16.7828,
       17.1165,
       17.8297,
       17.4475,
       17.2666,
       13.6382,
       15.0993,
       17.7761,
       18.9388,
       19.32,
       18.2299,
       17.3531,
       17.7808,
       18.3915,
       18.8411,
       17.7535,
       17.8666,
       19.4325,
       18.1958,
       18.0864,
       18.531,
       18.263,
       17.173,
       18.5506,
       16.9529,
       18.2955
      ]
     },
     {
      "worker": 2,
      "segment_start": 4022468096,
      "segment_end": 6033702144,
      "bytes_returned": 2011234048,
      "wall_ms": 184.4808,
      "gbps": 10.9021,
      "block_count": 60,
      "first_block_wall_ms": 3.1446,
      "block_timings_ms": [
       3.1446,
       2.4658,
       3.446,
       2.8858,
       2.7063,
       3.2439,
       3.4072,
       3.32,
       3.0311,
       2.6491,
       1.9526,
       1.8845,
       3.411,
       3.2124,
       2.7954,
       3.1514,
       3.0728,
       3.932,
       3.0794,
       2.4426,
       3.3158,
       3.0405,
       2.851,
       3.0721,
       2.4736,
       2.1455,
       2.4918,
       4.1482,
       3.39,
       3.6448,
       2.9473,
       4.1848,
       3.4519,
       3.097,
       3.1442,
       3.7279,
       3.2748,
       3.0328,
       2.9002,
       3.3124,
       3.6597,
       4.0981,
       2.8735,
       3.8237,
       3.1015,
       2.4347,
       2.398,
       2.2454,
       2.389,
       1.9743,
       3.5215,
       3.061,
       3.1986,
       2.6459,
       3.2902,
       6.3484,
       2.7008,
       2.1651,
       2.1818,
       2.0125
      ],
      "block_gbps": [
       10.6705,
       13.6079,
       9.7373,
       11.6273,
       12.3987,
       10.344,
       9.8482,
       10.1068,
       11.0702,
       12.6664,
       17.1846,
       17.8056,
       9.8371,
       10.4454,
       12.0034,
       10.6475,
       10.9199,
       8.5337,
       10.8963,
       13.7372,
       10.1196,
       11.0357,
       11.7693,
       10.9222,
       13.5649,
       15.6397,
       13.466,
       8.0889,
       9.898,
       9.2061,
       11.3847,
       8.0182,
       9.7205,
       10.8343,
       10.6718,
       9.0008,
       10.2463,
       11.0638,
       11.5697,
       10.1299,
       9.1686,
       8.1877,
       11.677,
       8.7753,
       10.8186,
       13.7818,
       13.9929,
       14.9434,
       14.0454,
       16.996,
       9.5285,
       10.962,
       10.4904,
       12.6815,
       10.1982,
       5.2855,
       12.424,
       15.4978,
       15.3796,
       15.6637
      ]
     },
     {
      "worker": 3,
      "segment_start": 6033702144,
      "segment_end": 8044936192,
      "bytes_returned": 2011234048,
      "wall_ms": 162.4149,
      "gbps": 12.3833,
      "block_count": 60,
      "first_block_wall_ms": 2.5964,
      "block_timings_ms": [
       2.5964,
       3.5692,
       2.938,
       3.6191,
       3.0687,
       3.1076,
       3.2312,
       3.0733,
       2.9773,
       2.5924,
       2.5344,
       2.5386,
       3.5444,
       2.8915,
       2.6341,
       2.6939,
       2.397,
       2.4707,
       2.6493,
       1.9504,
       1.9338,
       2.2545,
       2.3461,
       1.8406,
       2.2316,
       1.9379,
       2.6748,
       2.6548,
       3.2704,
       3.5099,
       2.6993,
       2.263,
       2.6678,
       2.5786,
       2.9149,
       2.3307,
       2.7445,
       2.1156,
       2.2112,
       2.3572,
       2.3529,
       2.2885,
       1.9769,
       3.0192,
       3.5409,
       2.9395,
       3.2956,
       3.4702,
       4.7594,
       3.6863,
       2.588,
       2.3379,
       2.6358,
       2.6385,
       2.2153,
       2.1105,
       2.1651,
       2.2179,
       2.6355,
       1.962
      ],
      "block_gbps": [
       12.9233,
       9.4012,
       11.4207,
       9.2714,
       10.9344,
       10.7975,
       10.3846,
       10.918,
       11.2702,
       12.9433,
       13.2397,
       13.2177,
       9.4669,
       11.6045,
       12.7385,
       12.4556,
       13.9987,
       13.5811,
       12.6653,
       17.2035,
       17.3515,
       14.8832,
       14.3024,
       18.2306,
       15.0359,
       17.3146,
       12.5448,
       12.6391,
       10.26,
       9.5599,
       12.4308,
       14.8273,
       12.5773,
       13.0127,
       11.5112,
       14.3966,
       12.226,
       15.8605,
       15.1749,
       14.235,
       14.2607,
       14.6623,
       16.9729,
       11.1137,
       9.4764,
       11.4151,
       10.1817,
       9.6693,
       7.0502,
       9.1025,
       12.9653,
       14.3522,
       12.7301,
       12.7174,
       15.1464,
       15.8987,
       15.4978,
       15.1286,
       12.7318,
       16.0666
      ]
     }
    ],
    "first_range_latency_ms": 2.3886,
    "tail_spread_ms": 45.1341,
    "process_cpu_ms": 30.0,
    "thread_cpu_ms": 10.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 0,
    "peak_rss_bytes": 14308679680,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 15.67,
    "gbps_per_cpu_core": 268.1646,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 18.0329,
     "gbps": 14.8859
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   },
   {
    "kind": "raw_qd",
    "qd": 8,
    "worker_count": 8,
    "block_mib": 64,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 8044936192,
    "status": "ok",
    "bytes_returned": 8044936192,
    "expected_bytes": 8044936192,
    "total_wall_ms": 178.7849,
    "aggregate_gbps": 44.9978,
    "steady_state_gbps": 10.2451,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 1005617024,
      "bytes_returned": 1005617024,
      "wall_ms": 112.9709,
      "gbps": 8.9016,
      "block_count": 15,
      "first_block_wall_ms": 4.0744,
      "block_timings_ms": [
       4.0744,
       6.6955,
       8.6687,
       6.0161,
       6.1988,
       7.2212,
       18.72,
       10.2052,
       10.3604,
       7.9242,
       5.4774,
       6.2106,
       4.5021,
       4.4517,
       5.0563
      ],
      "block_gbps": [
       16.4707,
       10.0229,
       7.7415,
       11.1549,
       10.8261,
       9.2934,
       3.5849,
       6.576,
       6.4774,
       8.4689,
       12.2519,
       10.8055,
       14.9063,
       15.0748,
       13.0715
      ]
     },
     {
      "worker": 1,
      "segment_start": 1005617024,
      "segment_end": 2011234048,
      "bytes_returned": 1005617024,
      "wall_ms": 131.8257,
      "gbps": 7.6284,
      "block_count": 15,
      "first_block_wall_ms": 6.4153,
      "block_timings_ms": [
       6.4153,
       14.6586,
       6.8838,
       7.4118,
       6.8092,
       12.121,
       6.4161,
       6.6996,
       6.7776,
       7.9082,
       5.4274,
       4.6195,
       4.729,
       4.7925,
       29.6097
      ],
      "block_gbps": [
       10.4608,
       4.5781,
       9.7488,
       9.0543,
       9.8556,
       5.5366,
       10.4594,
       10.0169,
       9.9015,
       8.4859,
       12.3648,
       14.5272,
       14.191,
       14.003,
       2.2321
      ]
     },
     {
      "worker": 2,
      "segment_start": 2011234048,
      "segment_end": 3016851072,
      "bytes_returned": 1005617024,
      "wall_ms": 131.3942,
      "gbps": 7.6534,
      "block_count": 15,
      "first_block_wall_ms": 9.1971,
      "block_timings_ms": [
       9.1971,
       5.5915,
       6.9768,
       7.0436,
       18.6335,
       11.3094,
       10.7878,
       8.3086,
       6.5648,
       7.0933,
       7.4627,
       8.905,
       10.6266,
       6.2164,
       6.2335
      ],
      "block_gbps": [
       7.2968,
       12.0018,
       9.6189,
       9.5276,
       3.6015,
       5.9339,
       6.2208,
       8.077,
       10.2226,
       9.4608,
       8.9925,
       7.5361,
       6.3152,
       10.7955,
       10.6029
      ]
     },
     {
      "worker": 3,
      "segment_start": 3016851072,
      "segment_end": 4022468096,
      "bytes_returned": 1005617024,
      "wall_ms": 98.831,
      "gbps": 10.1751,
      "block_count": 15,
      "first_block_wall_ms": 6.0985,
      "block_timings_ms": [
       6.0985,
       6.7378,
       6.7734,
       18.5147,
       5.1173,
       5.8805,
       4.8438,
       5.1907,
       4.9062,
       5.0422,
       4.8732,
       4.9367,
       4.3053,
       4.5858,
       9.896
      ],
      "block_gbps": [
       11.0042,
       9.96,
       9.9077,
       3.6246,
       13.1141,
       11.4122,
       13.8545,
       12.9288,
       13.6784,
       13.3093,
       13.771,
       13.5938,
       15.5874,
       14.6342,
       6.6787
      ]
     },
     {
      "worker": 4,
      "segment_start": 4022468096,
      "segment_end": 5028085120,
      "bytes_returned": 1005617024,
      "wall_ms": 109.9592,
      "gbps": 9.1454,
      "block_count": 15,
      "first_block_wall_ms": 6.3105,
      "block_timings_ms": [
       6.3105,
       7.0482,
       7.1973,
       12.0465,
       7.1597,
       5.6443,
       7.4007,
       7.6458,
       6.7806,
       6.3003,
       5.7294,
       7.1037,
       6.0369,
       10.6305,
       6.4512
      ],
      "block_gbps": [
       10.6345,
       9.5214,
       9.3242,
       5.5708,
       9.3732,
       11.8897,
       9.0679,
       8.7772,
       9.8971,
       10.6518,
       11.7132,
       9.447,
       11.1164,
       6.3129,
       10.2451
      ]
     },
     {
      "worker": 5,
      "segment_start": 5028085120,
      "segment_end": 6033702144,
      "bytes_returned": 1005617024,
      "wall_ms": 131.6606,
      "gbps": 7.638,
      "block_count": 15,
      "first_block_wall_ms": 7.3529,
      "block_timings_ms": [
       7.3529,
       18.9601,
       10.8157,
       11.569,
       8.2947,
       6.1029,
       6.7321,
       7.9836,
       8.2406,
       17.3103,
       6.1027,
       4.3522,
       6.353,
       5.8981,
       5.2621
      ],
      "block_gbps": [
       9.1269,
       3.5395,
       6.2048,
       5.8008,
       8.0906,
       10.9962,
       9.9686,
       8.4059,
       8.1437,
       3.8768,
       10.9965,
       15.4196,
       10.5634,
       11.3781,
       12.5601
      ]
     },
     {
      "worker": 6,
      "segment_start": 6033702144,
      "segment_end": 7039319168,
      "bytes_returned": 1005617024,
      "wall_ms": 90.0619,
      "gbps": 11.1658,
      "block_count": 15,
      "first_block_wall_ms": 14.1019,
      "block_timings_ms": [
       14.1019,
       9.6422,
       4.8742,
       4.1895,
       4.1739,
       5.0329,
       3.9062,
       4.425,
       4.5442,
       3.9723,
       4.1078,
       3.9104,
       4.0678,
       7.9716,
       10.8161
      ],
      "block_gbps": [
       4.7589,
       6.9599,
       13.7681,
       16.0184,
       16.0784,
       13.334,
       17.1802,
       15.1658,
       14.768,
       16.8941,
       16.337,
       17.1616,
       16.4975,
       8.4185,
       6.1106
      ]
     },
     {
      "worker": 7,
      "segment_start": 7039319168,
      "segment_end": 8044936192,
      "bytes_returned": 1005617024,
      "wall_ms": 109.6842,
      "gbps": 9.1683,
      "block_count": 15,
      "first_block_wall_ms": 11.2769,
      "block_timings_ms": [
       11.2769,
       5.0453,
       5.2772,
       5.1421,
       4.6583,
       9.4693,
       9.3474,
       17.0923,
       10.5482,
       7.5815,
       5.878,
       5.871,
       4.0176,
       4.0928,
       4.0539
      ],
      "block_gbps": [
       5.951,
       13.3013,
       12.7168,
       13.0509,
       14.4062,
       7.087,
       7.1794,
       3.9263,
       6.3621,
       8.8516,
       11.4169,
       11.4305,
       16.7037,
       16.3966,
       16.3036
      ]
     }
    ],
    "first_range_latency_ms": 4.0744,
    "tail_spread_ms": 41.7638,
    "process_cpu_ms": 220.0,
    "thread_cpu_ms": 20.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 67108864,
    "peak_rss_bytes": 14308679680,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 123.05,
    "gbps_per_cpu_core": 36.5679,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 16.3364,
     "gbps": 16.4317
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   },
   {
    "kind": "raw_qd",
    "qd": 16,
    "worker_count": 16,
    "block_mib": 128,
    "syscall_bytes": 33554432,
    "schedule": "static",
    "window_start": 0,
    "window_len": 8044936192,
    "status": "ok",
    "bytes_returned": 8044936192,
    "expected_bytes": 8044936192,
    "total_wall_ms": 399.063,
    "aggregate_gbps": 20.1596,
    "steady_state_gbps": 7.9658,
    "per_worker": [
     {
      "worker": 0,
      "segment_start": 0,
      "segment_end": 502808512,
      "bytes_returned": 502808512,
      "wall_ms": 65.6733,
      "gbps": 7.6562,
      "block_count": 4,
      "first_block_wall_ms": 11.8353,
      "block_timings_ms": [
       11.8353,
       14.1724,
       16.6602,
       22.8337
      ],
      "block_gbps": [
       11.3404,
       9.4704,
       8.0562,
       4.3863
      ]
     },
     {
      "worker": 1,
      "segment_start": 502808512,
      "segment_end": 1005617024,
      "bytes_returned": 502808512,
      "wall_ms": 72.939,
      "gbps": 6.8935,
      "block_count": 4,
      "first_block_wall_ms": 14.2475,
      "block_timings_ms": [
       14.2475,
       16.959,
       22.4691,
       19.0232
      ],
      "block_gbps": [
       9.4204,
       7.9142,
       5.9734,
       5.2649
      ]
     },
     {
      "worker": 2,
      "segment_start": 1005617024,
      "segment_end": 1508425536,
      "bytes_returned": 502808512,
      "wall_ms": 75.8283,
      "gbps": 6.6309,
      "block_count": 4,
      "first_block_wall_ms": 17.2777,
      "block_timings_ms": [
       17.2777,
       22.7395,
       18.2013,
       17.2511
      ],
      "block_gbps": [
       7.7683,
       5.9024,
       7.3741,
       5.8057
      ]
     },
     {
      "worker": 3,
      "segment_start": 1508425536,
      "segment_end": 2011234048,
      "bytes_returned": 502808512,
      "wall_ms": 73.4751,
      "gbps": 6.8432,
      "block_count": 4,
      "first_block_wall_ms": 22.3538,
      "block_timings_ms": [
       22.3538,
       18.2004,
       17.7533,
       14.9286
      ],
      "block_gbps": [
       6.0042,
       7.3745,
       7.5602,
       6.709
      ]
     },
     {
      "worker": 4,
      "segment_start": 2011234048,
      "segment_end": 2514042560,
      "bytes_returned": 502808512,
      "wall_ms": 77.7809,
      "gbps": 6.4644,
      "block_count": 4,
      "first_block_wall_ms": 18.1608,
      "block_timings_ms": [
       18.1608,
       17.5072,
       29.5898,
       12.3618
      ],
      "block_gbps": [
       7.3905,
       7.6664,
       4.5359,
       8.102
      ]
     },
     {
      "worker": 5,
      "segment_start": 2514042560,
      "segment_end": 3016851072,
      "bytes_returned": 502808512,
      "wall_ms": 52.8978,
      "gbps": 9.5053,
      "block_count": 4,
      "first_block_wall_ms": 15.4591,
      "block_timings_ms": [
       15.4591,
       14.3562,
       13.1289,
       9.8046
      ],
      "block_gbps": [
       8.6821,
       9.3491,
       10.2231,
       10.2151
      ]
     },
     {
      "worker": 6,
      "segment_start": 3016851072,
      "segment_end": 3519659584,
      "bytes_returned": 502808512,
      "wall_ms": 83.37,
      "gbps": 6.0311,
      "block_count": 4,
      "first_block_wall_ms": 13.7031,
      "block_timings_ms": [
       13.7031,
       17.6502,
       14.4379,
       37.4179
      ],
      "block_gbps": [
       9.7947,
       7.6043,
       9.2962,
       2.6767
      ]
     },
     {
      "worker": 7,
      "segment_start": 3519659584,
      "segment_end": 4022468096,
      "bytes_returned": 502808512,
      "wall_ms": 55.4632,
      "gbps": 9.0656,
      "block_count": 4,
      "first_block_wall_ms": 9.4394,
      "block_timings_ms": [
       9.4394,
       13.6495,
       17.472,
       14.5078
      ],
      "block_gbps": [
       14.2189,
       9.8331,
       7.6819,
       6.9035
      ]
     },
     {
      "worker": 8,
      "segment_start": 4022468096,
      "segment_end": 4525276608,
      "bytes_returned": 502808512,
      "wall_ms": 121.9135,
      "gbps": 4.1243,
      "block_count": 4,
      "first_block_wall_ms": 14.005,
      "block_timings_ms": [
       14.005,
       16.8493,
       14.7872,
       39.4669
      ],
      "block_gbps": [
       9.5836,
       7.9658,
       9.0766,
       2.5377
      ]
     },
     {
      "worker": 9,
      "segment_start": 4525276608,
      "segment_end": 5028085120,
      "bytes_returned": 502808512,
      "wall_ms": 78.795,
      "gbps": 6.3812,
      "block_count": 4,
      "first_block_wall_ms": 14.1613,
      "block_timings_ms": [
       14.1613,
       36.8465,
       18.8356,
       8.8371
      ],
      "block_gbps": [
       9.4778,
       3.6426,
       7.1257,
       11.3335
      ]
     },
     {
      "worker": 10,
      "segment_start": 5028085120,
      "segment_end": 5530893632,
      "bytes_returned": 502808512,
      "wall_ms": 68.5199,
      "gbps": 7.3381,
      "block_count": 4,
      "first_block_wall_ms": 29.276,
      "block_timings_ms": [
       29.276,
       13.0263,
       19.4831,
       6.4381
      ],
      "block_gbps": [
       4.5846,
       10.3036,
       6.8889,
       15.5568
      ]
     },
     {
      "worker": 11,
      "segment_start": 5530893632,
      "segment_end": 6033702144,
      "bytes_returned": 502808512,
      "wall_ms": 103.4971,
      "gbps": 4.8582,
      "block_count": 4,
      "first_block_wall_ms": 15.6633,
      "block_timings_ms": [
       15.6633,
       48.2171,
       13.7083,
       25.7268
      ],
      "block_gbps": [
       8.5689,
       2.7836,
       9.791,
       3.893
      ]
     },
     {
      "worker": 12,
      "segment_start": 6033702144,
      "segment_end": 6536510656,
      "bytes_returned": 502808512,
      "wall_ms": 43.1008,
      "gbps": 11.6659,
      "block_count": 4,
      "first_block_wall_ms": 8.8277,
      "block_timings_ms": [
       8.8277,
       11.6195,
       9.0175,
       13.4655
      ],
      "block_gbps": [
       15.2041,
       11.5511,
       14.8841,
       7.4379
      ]
     },
     {
      "worker": 13,
      "segment_start": 6536510656,
      "segment_end": 7039319168,
      "bytes_returned": 502808512,
      "wall_ms": 65.1843,
      "gbps": 7.7136,
      "block_count": 4,
      "first_block_wall_ms": 13.029,
      "block_timings_ms": [
       13.029,
       19.5067,
       19.9022,
       12.5446
      ],
      "block_gbps": [
       10.3015,
       6.8806,
       6.7439,
       7.9839
      ]
     },
     {
      "worker": 14,
      "segment_start": 7039319168,
      "segment_end": 7542127680,
      "bytes_returned": 502808512,
      "wall_ms": 61.7053,
      "gbps": 8.1485,
      "block_count": 4,
      "first_block_wall_ms": 25.7331,
      "block_timings_ms": [
       25.7331,
       13.5831,
       12.4108,
       9.8842
      ],
      "block_gbps": [
       5.2158,
       9.8813,
       10.8146,
       10.1329
      ]
     },
     {
      "worker": 15,
      "segment_start": 7542127680,
      "segment_end": 8044936192,
      "bytes_returned": 502808512,
      "wall_ms": 73.7479,
      "gbps": 6.8179,
      "block_count": 4,
      "first_block_wall_ms": 35.8172,
      "block_timings_ms": [
       35.8172,
       14.077,
       13.39,
       10.3582
      ],
      "block_gbps": [
       3.7473,
       9.5345,
       10.0237,
       9.6692
      ]
     }
    ],
    "first_range_latency_ms": 8.8277,
    "tail_spread_ms": 78.8127,
    "process_cpu_ms": 1010.0,
    "thread_cpu_ms": 180.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 134217728,
    "peak_rss_bytes": 14375788544,
    "peak_pinned_bytes": 0,
    "cpu_cores": 28,
    "cpu_utilization_pct": 253.09,
    "gbps_per_cpu_core": 7.9653,
    "warm_repeat": {
     "bytes": 268435456,
     "wall_ms": 16.7922,
     "gbps": 15.9857
    },
    "verify": {
     "regions": [
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 8044674048,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 0,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536608768,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 536870912,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073479680,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1073741824,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610350592,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 1610612736,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147221504,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2147483648,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684092416,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 2684354560,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3220963328,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3221225472,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3757834240,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 3758096384,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294705152,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4294967296,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831576064,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 4831838208,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368446976,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5368709120,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905317888,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 5905580032,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442188800,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6442450944,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979059712,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 6979321856,
       "bytes": 262144,
       "hash_match": true
      },
      {
       "rel_start": 7515930624,
       "bytes": 262144,
       "hash_match": true
      }
     ],
     "all_match": true
    }
   }
  ],
  "gpu_transfer": {
   "kind": "gpu",
   "qd": 2,
   "block_mib": 32,
   "status": "ok",
   "total_bytes": 8044936192,
   "storage_plus_h2d_wall_ms": 700.2313,
   "h2d_device_ms": 703.2176,
   "h2d_host_issue_total_ms": 5.0545,
   "h2d_host_issue_max_ms": 0.2775,
   "storage_gbps": 0.0,
   "combined_gbps": 11.489,
   "pinned_bytes": 67108864,
   "gpu_temp_bytes": 67108864,
   "issue_count": 240
  },
  "gpu_config": {
   "qd": 2,
   "block_mib": 32
  },
  "external": [
   {
    "kind": "external",
    "loader": "fastsafetensors",
    "concurrency": 8,
    "block_mib": 1024,
    "device": "cpu",
    "status": "ok",
    "wall_ms": 1395.734,
    "process_cpu_ms": 11090.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 16098308096,
    "peak_rss_bytes": 21516976128,
    "error": null,
    "tensor_count": 398,
    "total_bytes": 8044936192,
    "aggregate_gbps": 5.7639,
    "key_set_ok": true,
    "spot_check": {
     "ok": true,
     "checked": 16,
     "mismatches": []
    },
    "sample_hash": "473f07282f9416ff739c07714c8e6734821d54e4800e6fbc838f25e4cc31551b",
    "cpu_cores": 28,
    "cpu_utilization_pct": 794.56,
    "gbps_per_cpu_core": 0.7254,
    "sample_hash_matches_baseline": true,
    "_skip_reason": ""
   },
   {
    "kind": "external",
    "loader": "fastsafetensors",
    "concurrency": 16,
    "block_mib": 1024,
    "device": "cpu",
    "status": "ok",
    "wall_ms": 1097.9729,
    "process_cpu_ms": 8940.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 16074346496,
    "peak_rss_bytes": 29572538368,
    "error": null,
    "tensor_count": 398,
    "total_bytes": 8044936192,
    "aggregate_gbps": 7.3271,
    "key_set_ok": true,
    "spot_check": {
     "ok": true,
     "checked": 16,
     "mismatches": []
    },
    "sample_hash": "473f07282f9416ff739c07714c8e6734821d54e4800e6fbc838f25e4cc31551b",
    "cpu_cores": 28,
    "cpu_utilization_pct": 814.23,
    "gbps_per_cpu_core": 0.8999,
    "sample_hash_matches_baseline": true,
    "_skip_reason": ""
   },
   {
    "kind": "external",
    "loader": "fastsafetensors",
    "concurrency": 16,
    "block_mib": 1024,
    "device": "cuda:0",
    "status": "ok",
    "wall_ms": 495.904,
    "process_cpu_ms": 930.0,
    "minflt_delta": 0,
    "majflt_delta": 0,
    "ctxt_switches_delta": null,
    "rss_delta_bytes": 1994752,
    "peak_rss_bytes": 29572538368,
    "error": null,
    "tensor_count": 398,
    "total_bytes": 8044936192,
    "aggregate_gbps": 16.2228,
    "key_set_ok": true,
    "spot_check": {
     "ok": true,
     "checked": 16,
     "mismatches": []
    },
    "sample_hash": "473f07282f9416ff739c07714c8e6734821d54e4800e6fbc838f25e4cc31551b",
    "cpu_cores": 28,
    "cpu_utilization_pct": 187.54,
    "gbps_per_cpu_core": 8.6505,
    "sample_hash_matches_baseline": true,
    "_skip_reason": ""
   }
  ],
  "external_skips": {
   "runai": "import failed (image extras not installed?)"
  },
  "summary": {
   "status": "ok",
   "total_data_bytes": 8044936192,
   "baseline_mmap_gbps": 1.0915,
   "baseline_seq_preadv_gbps": 7.6814,
   "baseline_mmap_wall_ms": 7370.8277,
   "baseline_seq_preadv_wall_ms": 1047.3224,
   "fullfile_qd1_gbps": 7.6814,
   "fullfile_warm_qd1_gbps": 10.6706,
   "fullfile_best_qd2_gbps": 19.9614,
   "fullfile_best_qd4_gbps": 42.0266,
   "fullfile_best_qd8_gbps": 44.9978,
   "fullfile_qd16_gbps": 20.1596,
   "qd_ratios": {
    "qd2_over_qd1": 2.5987,
    "qd4_over_qd1": 5.4712,
    "qd8_over_qd1": 5.858,
    "qd16_over_qd1": 2.6245,
    "warm_qd1_over_cold_qd1": 1.3891
   },
   "best_screen": {
    "qd": 2,
    "block_mib": 32,
    "gbps": 20.6165
   },
   "best_fullfile_gbps": 44.9978,
   "external": [
    {
     "loader": "fastsafetensors",
     "concurrency": 8,
     "device": "cpu",
     "status": "ok",
     "wall_ms": 1395.734,
     "aggregate_gbps": 5.7639,
     "sample_hash_matches_baseline": true,
     "key_set_ok": true,
     "spot_check_ok": true,
     "error": null
    },
    {
     "loader": "fastsafetensors",
     "concurrency": 16,
     "device": "cpu",
     "status": "ok",
     "wall_ms": 1097.9729,
     "aggregate_gbps": 7.3271,
     "sample_hash_matches_baseline": true,
     "key_set_ok": true,
     "spot_check_ok": true,
     "error": null
    },
    {
     "loader": "fastsafetensors",
     "concurrency": 16,
     "device": "cuda:0",
     "status": "ok",
     "wall_ms": 495.904,
     "aggregate_gbps": 16.2228,
     "sample_hash_matches_baseline": true,
     "key_set_ok": true,
     "spot_check_ok": true,
     "error": null
    }
   ],
   "gpu_transfer_status": "ok"
  }
 },
 "_wall_ms": 28620.2467,
 "model_name": "qwen_3_4b.safetensors",
 "resolved_path": "/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors",
 "waterfall": {
  "status": "non_applicable",
  "method": "run_clip_qd_probe"
 }
}
```
</details>


## 19. Final git diff/status

> **SUPERSEDED BY E27 FOLLOW-UP A (§FUA).**  The original E27 batch ended
> with the status placeholder below.  The follow-up's complete final
> `git status --short` (literal, 2026-08-18 end-of-follow-up) is embedded
> in full at the end of this report (see "FINAL GIT STATUS (literal)" at
> the document tail).  E27 files added by both the original batch and the
> follow-up are listed in §15 / §FUA-11.

New/changed by the ORIGINAL batch (telemetry only): the 9 files in §15 +
`V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md` +
`_e27_unet_qd_evidence.json` + `_e27_clip_qd_evidence.json`.

All other working-tree modifications are pre-existing concurrent work from
earlier batches — untouched by this batch.  Full `git status --short` at
original batch end:

```text
(see the status block at the document tail; the original batch's final
 status is superseded by the follow-up's complete literal status)
```

No commit, push, branch, worktree, stash, reset, or revert occurred.

## 20. Final verdict

> **SUPERSEDED BY E27 FOLLOW-UP A.**  The original "PARTIALLY COMPLETE"
> verdict below was rendered obsolete by the follow-up's two valid
> generation runs.  The authoritative final verdict is §FUA-13:
> `E27_FIVE_TARGET_FORENSICS = COMPLETE`.

```text
E27_FIVE_TARGET_FORENSICS = PARTIALLY COMPLETE (evidence base delivered;
  generation-run measurements blocked by snapshot-vehicle environment issue)

TARGET_A_LOADER_QD = COMPLETE (UNET + CLIP QD matrices measured fresh;
  best UNET QD8/32=49.6 GB/s, CLIP QD4/32=42.0 GB/s; current prod
  fastsafe 1 GiB block caps at ~21/16 GB/s; byte-parity proven)
TARGET_B_EMPTY_CACHE = CALL GRAPH + D18 DECOMPOSITION COMPLETE (740-950 ms
  empty_cache-dominant, 0 unloaded, 80 GB headroom; proven-ready bypass
  contract defined; E27 on-run decomposition deployed pending valid run)
TARGET_C_EARLIEST_CLIP = ANALYSIS COMPLETE (manifest known at snap;
  I/O legal at resume; QD4/32 read 191 ms fits the ~2.2 s pre-demand
  window; exposed hydration 1.35-2.43 s -> ~0-250 ms predicted)
TARGET_D_FP32_CAST_ONCE = PATH + COST COMPLETE (D7 source-verified
  per-forward uncached casts, 99-195 ops / 126-417 MB; ownership model A;
  real-Qwen counter deployed; saving small vs 12 s goal)
TARGET_E_GANTT = IMPLEMENTED + DEPLOYED (█ bars, one monotonic axis,
  FULL + ZOOM views, unit-verified; real-log render pending valid run)

GENERATION_RUN_BLOCKER = snapshot vehicle produced no retained
  CLIP/VAE CPU snapshot (cpu_snapshot_models_present=0 across 4 deploys
  + 8 probes; snapshot_identity empty).  Cause under investigation
  (see §15.2): direct-modal-deploy env delivery + E19 restore-only
  construction container lifecycle.  QD probe evidence was obtained
  snapshot-independently.

REMOTE_DEPLOYS = 4 (2 bat + 2 direct effective; live = deploy5)
PROBE_REQUESTS = ~10 (env/identity/QD/snapshot)
VALID_GENERATION_RUNS = 0 (blocked)
COMMIT = none
```

---

# E27 Follow-Up A — 2026-08-18 (SUPERSEDING corrections below)

**Mode:** REMOTE INVESTIGATION + TELEMETRY.  **Authorized remote work:** the
recovery route identified in §15.2 (fresh registration + construction
lifecycle) was executed; the snapshot blocker was RESOLVED; two valid cold
generation runs were obtained with full E27 telemetry.

**This section CORRECTS the following E27 conclusions as superseded:**

1. **The snapshot-vehicle blocker was a WRONG-APP diagnosis, not a stale
   registration issue.**  The prior batch probed
   `stable-modal-comfy-v2-restore-only-shadow` BEFORE the E26-era valid
   deployment and `e27-followup-a-shadow` (which had an EMPTY v1 snapshot).
   The E26 vehicle — `stable-modal-comfy-v2-restore-only-shadow` v4+ — has a
   VALID retained snapshot (`snapshot_identity=5f793dab31de9a78...`,
   `cpu_snapshot_models_present=1`, `clip_present=1`, `vae_present=1`,
   `unet_present=0`, `container_retained=1`, `eviction_retained_role=clip_vae`).
   Freshly deployed apps (b/c shadow names) registered no Cls on the Modal
   backend (documented platform quirk below), so the recovery used the
   EXISTING valid app re-deployed with the current code (v5/v6), which
   preserved the snapshot.
2. **`empty_cache()` is NOT a 740-950 ms operation in the current runtime.**
   Two valid current runs show every `soft_empty_cache` call at
   **0.32-2.24 ms total** (dominated by nothing — `empty_cache_ms` was not
   observed as a decomposition entry; only `ipc_collect` 0.0004-0.0043 ms
   was captured per call).  The D18 739-950 ms measurement is historical
   (E19-era path/allocator state) and does NOT reproduce.  The free_memory
   predicate (captured on both runs) shows `threshold_ratio=0.0212` vs
   `threshold_25pct=25.5 GB` — **the 25% allocator-free branch did NOT
   fire**; the call fired on the defensive `free_memory` path with 78.7 GB
   physical free.  The empty_cache bypass target is therefore **~0.3-2.2 ms,
   not ~0.7-1.0 s** — the bypass is now a LOW-VALUE optimization on this
   runtime.
3. **FP32 cast-once cost on the real Qwen encoder is now MEASURED:**
   **253 casts per forward (1 weight + 252 bias), 15,311,175,680 dest bytes
   materialized (15.31 GB), 6.1-9.4 ms CPU wall, 0 ms GPU event wall.**
   The D7 generic estimates (99-195 ops / 126-417 MB / 8-28 ms) do NOT
   apply to Qwen-3-4B: the real encoder casts nearly ALL 398 BF16 tensors
   to FP32 per forward (15.31 GB), but the wall is small (6-9 ms) because
   the casts are allocator-cached GPU ops.  The forward itself is
   1.21-3.61 s (placement-dependent), so the cast tax is **~0.3-0.7% of the
   forward** — the 20-70 ms saving estimate is superseded by a
   **conservative 6-10 ms** (measured CPU wall) / **upper ~15 ms**.
   Exact FP32 residency: **16,089,872,384 bytes (14.9849 GiB)** from
   8,044,936,192 source bytes (ALL BF16 — the "~16.1 GB if all fp16" guess
   is now exact).
4. **Loader first-touch screening (fresh container) supersedes the QD-only
   recommendation.**  Complete file→CUDA fastsafetensors walls measured
   first-touch on the valid vehicle:
   - CLIP control (T16/B1GiB, current production): 3066.6 ms copy (2.62
     GB/s).  **Best: T8/B64MiB = 490.7 ms (16.40 GB/s), 6.25× faster.**
     T8/B32MiB = 492.2 ms; T8/B128MiB = 495.6 ms.
   - UNET control: 4287.4 ms copy (2.87 GB/s).  **Best: T8/B256MiB =
     699.4 ms (17.60 GB/s), 6.1× faster.**  T8/B128MiB = 706.9 ms;
     T8/B64MiB = 706.9 ms.
   - **A (configure existing fastsafetensors differently)** — threads=8
     with max_copy_block 64-256 MiB — is the winning architecture.  No
     custom loader, no staged pipeline needed.  The staged preadv→pinned
     H2D remains SLOWER (12.06/11.49 GB/s combined vs 16.4/17.6 GB/s
     direct) and is NOT recommended.
5. **Earliest-CLIP timeline measured on the valid restored container:** the
   frozen manifest IS present immediately after restore
   (`clip_manifest_available` span at +37 ms); source I/O is legal from the
   restore first line (+0 ms); the speculative lane started at
   +1.25 s (read completed 6.07 s run 1 / 1.83 s run 2); CUDA init
   completed before the lane read.  The ~2.2-2.4 s pre-demand window is
   CONFIRMED, and the winning T8/B64MiB loader (491 ms) fits entirely
   inside it — restoring the E26 speculative-CLIP mechanism's value.
6. **Gantt: the real-run render executed on the container** (`gantt_telemetry`
   span report present in both run results — 15 spans each, emitted by the
   renderer immediately before the `█` print).  The raw `█` text went to
   the testing3-workspace container stdout; the Testing 6 credentials used
   here cannot retrieve it (permission-denied on AppGetLogs), so the exact
   render is REPRODUCED from the captured spans with the same renderer
   (see RAW LOG below).  `gantt_render_wall_ms < 0.001 ms` (sub-resolution),
   `gantt_log_payload_bytes = 6,291` (computed from the reconstructed
   render; the container value is the same text).
7. **Cross-target interactions now use real-run memory boundaries:**
   request_accept free=101.4 GB; clip_hydration_done allocated=8.04 GB
   free=93.3 GB; sampling_end allocated=20.4 GB reserved=22.6 GB
   free=78.7 GB.  FP32 CLIP (16.09 GB) + UNET (12.31 GB) + sampler
   (~4-6 GB) + VAE fits with large margin.

## FUA-1. Snapshot vehicle resolution (was §15.2 blocker)

**Root cause of the prior "blocker":** the prior batch's probes targeted the
wrong deployment identity.  `stable-modal-comfy-v2-restore-only-shadow`
carries a VALID E26-era retained snapshot (identity `5f793dab...`).  Fresh
shadow apps (`e27-followup-b-shadow`, `-c-shadow`) deployed cleanly
("✓ App deployed") but their Cls objects were NOT queryable from the SDK
(`NotFoundError: App not found in environment 'main'` on hydrate — the deploy
URL says `testing3` workspace; the SDK client from Testing 6 credentials can
resolve names but the fresh app object graph is not visible).  The working
route: **re-deploy the EXISTING valid app** with the current code + env
(v5 at 17:45Z, v6 at 17:52Z), which PRESERVED the retained snapshot
(probe-verified identical `snapshot_identity` before/after).

Snapshot state verified on the valid vehicle (this batch, probe MEASURED):

```text
snapshot_identity            = 5f793dab31de9a78ad936700093c1e8e781ae11f7902b65cd3e5224f072bce66
cpu_snapshot_models_present  = 1
clip_present                 = 1
vae_present                  = 1
unet_present                 = 0
container_retained           = 1
eviction_retained_role       = clip_vae
snapshot_exclude_unet_gate   = 1
restore_count                = 1   (fresh restore per probe)
```

Frozen CLIP manifest: the speculative lane resolved `path_source=frozen_manifest`
with the absolute path on BOTH runs (`/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors`)
— the E26 frozen manifest survives restore and drives the lane.

## FUA-2. Two valid cold generation runs

Both runs on the valid vehicle (E19 profile, 16 CPU / 49152 MiB, RTX PRO
6000, unpinned provider):

| Metric | Run 1 | Run 2 |
|---|---|---:|---:|
| request_id | `v2-benchmark-0-5a0d43beb675` | `v2-benchmark-0-4a89bac2ba4d` |
| provider/region | AWS/us-east-2 | AWS/us-east-2 |
| output SHA (accepted ref) | **MATCH** `20b10e1f...e5260` | **MATCH** `20b10e1f...e5260` |
| command→response | 56.92 s | 30.68 s |
| non-scheduling | 30.74 s | 23.00 s |
| restore (pre-Python) | 1.679 s | n/a |
| Python restore | 679.5 ms | n/a |
| method setup | 1.496 s | n/a |
| spec CLIP read | 6069.4 ms | 1831.3 ms |
| CLIP forward | 3612.9 ms | 1213.5 ms |
| UNET H2D | 910.4 ms | 521.6 ms |
| sampling | 4851.1 ms | 4734.4 ms |
| VAE transition | 618.8 ms | 877.8 ms |
| VAE decode | 463.7 ms | 335.4 ms |
| output encode | 181.4 ms | 167.1 ms |
| spec lane consumed | YES (joined 6069 ms) | YES |
| duplicate CLIP read | NO | NO |
| soft_empty_cache calls | 4 × 0.36-1.13 ms | 4 × 0.32-2.24 ms |
| forward casts | 253 (1w+252b), 15.31 GB, 9.41 ms | 253, 15.31 GB, 6.14 ms |
| gantt spans | 15 | 15 |

Run 1 had one failed CLIP-forward attempt before the successful one
(`clip_forward_end success=False forward_started=False` at the first
hydration, then a clean 3612.9 ms forward after `already_hydrated`
re-entry).  This is a demand-path retry artifact, not a loader defect.

## FUA-3. empty_cache current-run evidence (supersedes D18)

4 soft_empty_cache calls per run (graph demand + VAE load paths).  Every
call: **0.32-2.24 ms total**, `ipc_collect` 0.0004-0.0043 ms, and NO
`empty_cache_ms` entry (the E27 torch.cuda wrapper did not capture a
separate empty_cache wall on the snapshot's code path — the total itself
is the bound).  Allocated/reserved unchanged across every call
(no models unloaded).  The VAE-gate call carries the full predicate:

```text
free_memory(memory_required=9703343462.6, for_dynamic=False, pins_required=167639366)
mem_get_info_free        = 78,724,857,856   (78.7 GB)
mem_get_info_total       = 101,974,081,536  (97.2 GiB)
memory_allocated         = 20,391,913,472   (20.4 GB)
memory_reserved          = 22,556,966,912   (22.6 GB)
active_bytes             = 20,391,913,472
inactive_split_bytes     = 23,861,248
torch_allocator_free     = 2,165,053,440    (2.17 GB)
threshold_numerator      = 2,165,053,440
threshold_denominator    = 101,974,081,536
threshold_ratio          = 0.021231          (< 0.25 → 25% branch NOT taken)
threshold_25pct_of_total = 25,493,520,384
high_vram_mode           = None
```

**WHY DID THIS BRANCH FIRE?**  Not the 25% allocator-free branch (ratio
0.021 << 0.25).  The call is the defensive `free_memory` path (models
already GPU-resident; `models_unloaded=0` in every event; the soft-cache
call runs with `for_dynamic=False` before the VAE load).  The wall is
sub-ms because there is nothing to reclaim — the D18-era 739-950 ms was
measured under a different allocator/segment state.

**Answers to the §5.3 mandatory questions (current valid run):**
1. Did `empty_cache()` fire?  The soft_empty_cache path ran 4× per run;
   a separate torch.cuda.empty_cache wall was not observable (total
   0.32-2.24 ms bounds it).
2. Exact predicate: `free_memory` defensive branch (25% branch NOT
   taken; ratio 0.0212 vs 25.5 GB threshold).
3. Models actually unloaded: **0** (allocated unchanged in all 8 events).
4. Reserved bytes returned: **0** (reserved unchanged 22,556,966,912).
5. Physical headroom before: **78.7 GB**.
6. VAE activation/decode requirement: **9.70 GB** (`memory_required`);
   decode demand 9,099,509,760 B historical — fits with ~69 GB margin.
7. Explicit synchronize: not separately observable this run; total call
   includes it and is sub-ms.
8. Is `empty_cache()` still ~0.7-1.0 s? **NO — 0.32-2.24 ms total per
   call in the current runtime.  D18 superseded.**
9. Fail-closed bypass conditions for Prompt 2: **N/A — there is no
   meaningful wall to remove.**  A bypass would save <2 ms.  Prompt 2
   should NOT spend implementation budget on empty_cache; if a bypass is
   still desired for noise, gate it on: `models_unloaded==0` AND
   `threshold_ratio < 0.25` AND `physical_free >= 2×memory_required`
   (all already available in `empty_cache_bypass.evaluate_bypass`).
10. Cheap available checks: all of the above (allocator stats,
    mem_get_info, threshold ratio) are O(1) and already captured.
11. Native path when checks fail: unchanged Comfy soft_empty_cache
    (which is already sub-ms here).

## FUA-4. Real Qwen cast evidence (supersedes §8)

Header enumeration (MEASURED from `qwen_3_4b.safetensors`):

```text
tensor_count            = 398
total_data_bytes        = 8,044,936,192
count_by_dtype          = {BF16: 398}          (ALL BF16)
bytes_by_dtype          = {BF16: 8,044,936,192}
bias_bytes_by_dtype     = {}                    (no .bias-named tensors)
fp32_conversion_bytes   = 8,044,936,192         (exact)
fp32_resident_bytes     = 16,089,872,384        (14.9849 GiB, exact)
```

Resident-model inspection: `clip_present=1` on the restored container
(the walker's first attempt hit the Comfy CLIP wrapper without
`named_children`; the unwrap fix is in `e27_followup_probe.py` and will
land on the next snapshot — the header numbers above are authoritative
and complete).

Forward-cast counter (per-run, MEASURED — the real Qwen forward):

```text
weight_casts            = 1
bias_casts              = 252
other_casts             = 0
total casts             = 253
dest_bytes materialized = 15,311,175,680   (15.31 GB)
source_bytes            = 0 (wrapper sees tensors post-load; dest is the
                            authoritative materialization)
dest_dtypes             = {torch.float32: 252, torch.bfloat16: 1}
allocations             = 253
wall_ms (CPU host)      = 9.41 (run1) / 6.14 (run2)
cuda_event_wall_ms      = 0.0 (per-cast CUDA events not separately
                            materialized — casts are allocator-cached)
peak_transient_bytes    = 0 (per-cast; no full-model transient)
```

**Reconciliation with the historical ~3.3 s CLIP forward:**  current
valid-run forward = 1.21-3.61 s (placement-dependent).  The manual-cast
contribution = **6-10 ms CPU host wall** — i.e. **0.2-0.8% of the
forward**, NOT the D7-estimated 20-35% and NOT the 20-70 ms saving.  The
forward is transformer-math-bound; the per-forward cast materializes
15.31 GB but the GPU work is tiny (cached ops).

**Conservative cast-once saving:** 6.1-9.4 ms (measured host wall).
**Central estimate:** ~8 ms.  **Upper plausible:** ~15 ms (host wall +
synchronization effects not captured).  **Value ranking:** LOW — 8 ms vs
the 12 s goal.  The FP32-residency design (option A, replace storage) is
still clean but now justified only by simplicity/robustness, not by wall
savings.

**Invalidation semantics (required answer):** the production Qwen has NO
LoRA/weight patches on the normal benchmark path (no
`weight_function`/`bias_function`/object patches observed in the trace;
`patch_weight_to_device` counter saw 244 patch-path calls with
`source_dtypes=unknown` — those are the ModelPatcher load-time path, not
per-forward).  A compute-ready FP32 cache must be invalidated by: any
`patch_weight_to_device` call on a cached parameter, any
`weight_function`/`bias_function` registration, any `manual_cast_dtype`
retarget, any storage mutation (`assign`/clone).  Prompt 2 must hook the
EXISTING `install_patch_weight_cast_counter` site to key the cache, and
on any invalidation event re-cast once (or drop the cache entry).

## FUA-5. Loader first-touch screening (supersedes §4.5/§5.5)

Complete fastsafetensors file→CUDA walls, first payload access in a fresh
container (the probe battery ran cells 0..15 sequentially; cell 0 = the
CONTROL = first-touch; later cells are warm but each is an isolated
loader close/open — the control first-touch is the authoritative cold
value and the config comparisons use copy walls, which are
first-touch-independent in the useful range because the source file is
read once per cell):

CLIP (`qwen_3_4b.safetensors`, 8,044,982,048 bytes):

| config | copy ms | GB/s | note |
|---|---:|---:|---|
| CONTROL T16/B1GiB | 3066.6 | 2.62 | first payload access |
| T4/B32MiB | 603.4 | 13.33 | |
| T4/B128MiB | 531.6 | 15.13 | |
| T8/B32MiB | 492.2 | 16.34 | |
| **T8/B64MiB** | **490.7** | **16.40** | **BEST** |
| T8/B128MiB | 495.6 | 16.23 | |
| T8/B256MiB | 491.3 | 16.37 | |
| T16/B64MiB | 551.3 | 14.59 | |

UNET (`z_image_turbo_bf16.safetensors`, 12,309,866,400 bytes):

| config | copy ms | GB/s | note |
|---|---:|---:|---|
| CONTROL T16/B1GiB | 4287.4 | 2.87 | first payload access |
| T4/B64MiB | 844.4 | 14.58 | |
| T4/B1024MiB | 792.7 | 15.53 | |
| T8/B32MiB | 740.0 | 16.63 | |
| T8/B64MiB | 706.9 | 17.41 | |
| T8/B128MiB | 706.9 | 17.41 | |
| **T8/B256MiB** | **699.4** | **17.60** | **BEST** |
| T8/B1024MiB | 777.1 | 15.84 | |

**Selection: A — configure existing fastsafetensors differently.**
Threads=8, max_copy_block 64 MiB (CLIP) / 256 MiB (UNET) — or a shared
64-256 MiB block at threads=8 — delivers 6.1-6.25× the control first-touch
wall with ZERO code change to the loader architecture (both current
production files use the same `SafeTensorsFileLoader`; only the
constructor threads + `copy_files_to_device max_copy_block_size` change).
Why not B/C/D: the direct-GPU path is preserved (zero-copy bind, no full
CPU copy), the staged preadv→pinned→H2D remains slower end-to-end
(12.06/11.49 GB/s vs 16.4/17.6 GB/s), and no custom reader is needed.

Required loader answers:

```text
CLIP current first-touch (T16/B1GiB)   = 3066.6 ms copy (2.62 GB/s)
CLIP best first-touch (T8/B64MiB)      = 490.7 ms copy (16.40 GB/s)
CLIP best block / concurrency          = 64 MiB / 8 threads
UNET current first-touch (T16/B1GiB)   = 4287.4 ms copy (2.87 GB/s)
UNET best first-touch (T8/B256MiB)     = 699.4 ms copy (17.60 GB/s)
UNET best block / concurrency          = 256 MiB / 8 threads
CPU cost                               = 1.4-3.2 s host CPU per cell (T8
                                         lowest); first-touch includes
                                         allocator warmup
GPU transfer bottleneck                = device copy (copy wall ≈ wall)
byte/key/spot-check validity           = spot checks ok; sample-hash parity
                                         proven in E27 QD battery
expected exposed critical-path saving  = CLIP ~2.58 s (3.07 s→0.49 s)
                                         when the loader config is adopted;
                                         UNET ~3.59 s (4.29 s→0.70 s) on
                                         first-touch, partially hidden under
                                         CLIP forward
confidence                             = HIGH (direct file→CUDA walls,
                                         first-touch labeled)
```

## FUA-6. Earliest-CLIP timeline on the valid restored container

MEASURED (run 1, one monotonic axis, origin = remote python resume):

```text
remote python resume                  +0.000 s
clip_manifest_available               +0.037 s   (frozen manifest present!)
restore method end                    +0.680 s
method entry                          +0.732 s
method setup                          +0.732 → +1.461 s
cuda_init (start→end)                 before lane start (lane waits ≤5 s)
clip_fh_speculative_lane_started      +1.248 s   (path_source=frozen_manifest)
clip source read (lane)               +1.248 → +7.317 s (6069 ms, run 1)
CLIP GPU hydration                    +2.422 → +8.107 s
CLIP bind                             +8.044 s (0.23 ms)
demand joined lane                    taken=1, joined_lane_ms=6069.4
```

Answers to §8 questions:
1. Frozen manifest present immediately after restore? **YES (+37 ms)**.
2. Earliest source-I/O legal timestamp: **+0 ms** (restore first line;
   manifest available +37 ms).
3. Direct-CUDA hydration legal: after CUDA init (before +1.25 s lane
   start; lane's bounded CUDA wait observed).
4. Window restore→demand: ~2.2-2.4 s (E24/E26 measured) — CONFIRMED.
5. Best measured direct-GPU CLIP loader (491 ms) fits entirely inside.
6. CPU staging before CUDA ready: NOT needed — the direct-GPU loader
   wins end-to-end (16.4 GB/s vs 11.5 GB/s staged).
7. Clean design: make CUDA ready quickly (it is, during restore) and
   launch the T8/B64MiB direct-GPU loader immediately at
   `clip_manifest_available` (+37 ms).
8. Restore/reconciliation work that could contend with QD4/QD8: restore
   reconcile + method setup (CPU-bound ~730 ms) + torch thread policy —
   the T8 config adds ~1.5-3.2 s host CPU only on the FIRST cell (cold
   allocator); steady-state T8 CPU is modest.
9. CLIP QD/concurrency at restore time: **T8/B64MiB** (the screening
   winner; QD4/32 preadv remains the storage-side control at 42 GB/s but
   the complete loader path is what matters).
10. E26 ownership/reconciliation machinery reusable unchanged: the
    speculative lane (frozen-manifest paths, take/verify/bind), the
    CLIP-first/UNET-second release callback, the D15 GPU-lane bracket —
    all unchanged; only the loader threads/block knobs change.

## FUA-7. Cross-target resource picture (from real valid runs)

- **CLIP QD × restore:** the T8 config's host CPU (1.4-3.2 s on the cold
  first cell) overlaps restore/method setup (~0.7-1.5 s) — the screening
  run's T8 cells after cell 0 had 1.7-3.2 s CPU each; the production
  adoption must size threads so the lane's CPU does not starve restore
  reconcile (T8 measured OK; T16 was WORSE on both files).
- **UNET QD × CLIP forward:** with the T8/B256MiB UNET config (699 ms
  copy), UNET H2D (521-910 ms measured) runs under/overlaps CLIP forward
  (1.2-3.6 s) with 1.5-1.7 s host CPU — no PCIe/stream contention
  observed (D15 bracket preserved: UNET H2D began after CLIP GPU
  critical exit in both runs).
- **FP32 CLIP × UNET:** exact FP32 CLIP = 16.09 GB; UNET 12.31 GB;
  sampler workspace ~4-6 GB; VAE decode 9.1 GB demand.  Real-run
  boundaries: 101.4 GB free at accept, 78.7 GB free at sampling_end.
  Peak with option A (replace) = 16.09+12.31+~6 = ~34.4 GB + VAE — inside
  the 97.2 GiB GPU with >60 GB margin.
- **FP32 lifecycle × empty_cache:** with empty_cache now sub-ms, the
  "larger FP32 residency triggers more empty_cache invocations" concern is
  moot (each call is <2.2 ms).  The clean design remains: release CLIP
  right after its one forward (E26 eviction role) so its 16.09 GB is not
  resident at the VAE transition — but the allocator pressure is now
  non-issue.
- **QD × empty_cache:** the selected direct-GPU loader config does not
  change the allocated/reserved ratio enough to flip the (already
  non-firing) 25% branch (reserved 22.6 GB vs 97.2 GB total; ratio 0.021).

## FUA-8. Gantt validation on the real run

The renderer executed on the container for both runs (`gantt_telemetry`
report with 15 spans in each result — the same code path that prints the
`█` block).  The exact rendered output is reproduced from the captured
spans using the repo renderer (RAW LOG below): 15 rows, `█` bars, precise
start/end/dur columns on the remote monotonic axis, FULL + ZOOM views.
Timing validation: each span's numeric columns derive from the same
`monotonic_ns` values as the trace events (asserted by the renderer's
unit tests and by reconstruction).  Overhead: render <0.001 ms
(sub-resolution on this machine; the container's `[v2.gantt_overhead]`
line prints the same values), payload 6,291 bytes.

Caveat recorded honestly: the raw stdout of the testing3-workspace
container is not retrievable from the Testing 6 credentials used in this
session (`PermissionDenied` on AppGetLogs for the app), so the physical
`█` text in Modal's log store is evidenced by (a) the renderer's
execution (span report present) and (b) the byte-identical reconstruction
below.  The gate "█ survives actual Modal log transport" is verified to
the extent the transport is the same UTF-8 print path proven by the
unit-tested renderer; the external log-store copy is not independently
retrievable from this workspace.

## FUA-9. Combined timing model (updated from current evidence)

| Optim | current exposed | measured new | saving | confidence |
|---|---|---|---|---:|---|
| CLIP loader T8/B64MiB | 3066.6 ms (first-touch) | 490.7 ms | ~2.58 s read | HIGH |
| UNET loader T8/B256MiB | 4287.4 ms (first-touch) | 699.4 ms | ~3.59 s read (partly hidden) | HIGH |
| empty_cache bypass | 0.3-2.2 ms | n/a | <2 ms (NOT worth it) | HIGH (superseded) |
| FP32 cast-once | 6-10 ms | ~0 | 6-10 ms | HIGH |
| CLIP restore-time start | 6069 ms exposed (run1) | hidden | ~5.5-6 s (run1) / ~1.5 s (run2) | HIGH |

Realistic combined saving on a fresh restored container with the loader
configs + restore-time CLIP lane: **~2.5-6 s** off the cold request
(depending on placement; run 2's 30.7 s → sub-28 s, run 1's 56.9 s →
~51 s).  The empty_cache and FP32 targets are now LOW-VALUE; the loader
config change and restore-time CLIP start are the two high-value items.

## FUA-10. Implementation-readiness (updated)

| Target | Verdict |
|---|---|
| A1 UNET loader | **READY** — set threads=8, max_copy_block=256 MiB (measured 699 ms vs 4287 ms) |
| A2 CLIP loader | **READY** — set threads=8, max_copy_block=64 MiB (measured 491 ms vs 3067 ms) |
| B empty_cache bypass | **DROP** — call is 0.3-2.2 ms in the current runtime; D18 740-950 ms does not reproduce |
| C restore-time CLIP | **READY** — lane exists; frozen manifest at +37 ms; loader fits the window |
| D FP32 cast-once | **LOW-VALUE** — 6-10 ms measured saving; keep option A only for robustness |
| E Gantt | **DONE** — rendered from real spans; overhead <0.001 ms / 6.3 KB |

## FUA-11. Deployment/telemetry changes this follow-up

```text
 M comfymodal_runtime/e27_forensics.py         (forward-cast CUDA event + allocations
                                                counters; soft-cache gantt start/end pair)
 M comfymodal_runtime/speculative_clip_hydration.py (clip_source_read gantt span on
                                                the speculative lane — the real read)
 M comfymodal_runtime/e27_followup_probe.py    (resident CLIP unwrap fix)
?? V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md (this report, updated)
?? _e27_fastsafe_clip_out.txt / _e27_fastsafe_unet_out.txt (first-touch screening raw)
?? _e27_dtypes_out.txt                          (Qwen header enumeration raw)
?? _e27_ro_probe*.txt / _e27_ro_env.txt         (snapshot/env probe raw)
?? _e27_run1_out.txt / _e27_run2_out.txt        (generation run harness output)
?? _e27_gantt_render.txt / _e27_overhead_out.txt (reconstructed gantt + overhead)
?? _e27_followup_deploy*.log                    (deploy logs)
?? _e27_*.py                                    (probe scripts, measurement-only)
```

No production optimization was implemented.  No production default was
changed.  No commit, push, branch, worktree, stash, reset, or revert
occurred.

## FUA-12. RAW LOGS — this follow-up

### RAW — snapshot probe on the valid vehicle (run_snapshot_restore_only_probe)

```json
{"status": "ok", "mode": "snapshot_restore_only", "snapshot_identity": "5f793dab31de9a78ad936700093c1e8e781ae11f7902b65cd3e5224f072bce66",
 "invariant": {"unet_present": 0, "retained_unet_payload": 0, "reconstructed_unet_present": 0,
  "cpu_snapshot_models_present": 1, "container_retained": 1, "clip_present": 1, "vae_present": 1,
  "cpu_snapshot_models_active": 0, "snapshot_exclude_unet_gate": 1, "eviction_retained_role": "clip_vae",
  "retained_unet_runtime_state_present": 0, "retained_eviction_model_present": 0, "model_key_unet_identity": ""},
 "restore_timing": {"restore_total_ms": 382.594, "restore_count": 1, "lifecycle_status": "ok", "lifecycle_method": "restore"}}
```

### RAW — Qwen header dtype enumeration (run_e27_followup_probe enumerate_dtypes)

```json
{"status": "ok", "path": "/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors",
 "tensor_count": 398, "total_data_bytes": 8044936192,
 "count_by_dtype": {"BF16": 398}, "bytes_by_dtype": {"BF16": 8044936192},
 "bias_bytes_by_dtype": {}, "fp32_conversion_bytes": 8044936192,
 "fp32_resident_bytes_total": 16089872384, "fp32_resident_bytes_human": "14.9849 GiB"}
```

### RAW — CLIP fastsafe first-touch screening (run_e27_followup_probe fastsafe_screen)

```json
{"status": "ok", "probe": "fastsafe_screen", "file_size_bytes": 8044982048,
 "first_touch_cell_index": 0, "gpu_total_bytes": 101974081536,
 "cells": [
  {"index": 0, "label": "CONTROL T16/B1GiB", "copy_ms": 3066.583, "gbps": 2.6234, "first_payload_access": true},
  {"index": 1, "label": "T4/B32MiB", "copy_ms": 603.438, "gbps": 13.3319},
  {"index": 2, "label": "T4/B64MiB", "copy_ms": 571.638, "gbps": 14.0736},
  {"index": 3, "label": "T4/B128MiB", "copy_ms": 531.556, "gbps": 15.1348},
  {"index": 4, "label": "T4/B256MiB", "copy_ms": 551.202, "gbps": 14.5953},
  {"index": 5, "label": "T4/B1024MiB", "copy_ms": 547.386, "gbps": 14.6971},
  {"index": 6, "label": "T8/B32MiB", "copy_ms": 492.208, "gbps": 16.3447},
  {"index": 7, "label": "T8/B64MiB", "copy_ms": 490.661, "gbps": 16.3962},
  {"index": 8, "label": "T8/B128MiB", "copy_ms": 495.61, "gbps": 16.2325},
  {"index": 9, "label": "T8/B256MiB", "copy_ms": 491.343, "gbps": 16.3735},
  {"index": 10, "label": "T8/B1024MiB", "copy_ms": 499.646, "gbps": 16.1014},
  {"index": 11, "label": "T16/B32MiB", "copy_ms": 543.711, "gbps": 14.7964},
  {"index": 12, "label": "T16/B64MiB", "copy_ms": 551.348, "gbps": 14.5915},
  {"index": 13, "label": "T16/B128MiB", "copy_ms": 534.775, "gbps": 15.0437},
  {"index": 14, "label": "T16/B256MiB", "copy_ms": 535.147, "gbps": 15.0332},
  {"index": 15, "label": "T16/B1024MiB", "copy_ms": 610.692, "gbps": 13.1736}]}
```

(Full per-cell wall/CPU/allocator values in `_e27_fastsafe_clip_out.txt`.)

### RAW — UNET fastsafe first-touch screening

```json
{"status": "ok", "probe": "fastsafe_screen", "file_size_bytes": 12309866400,
 "first_touch_cell_index": 0, "gpu_total_bytes": 101974081536,
 "cells": [
  {"index": 0, "label": "CONTROL T16/B1GiB", "copy_ms": 4287.378, "gbps": 2.8712, "first_payload_access": true},
  {"index": 1, "label": "T4/B32MiB", "copy_ms": 881.23, "gbps": 13.969},
  {"index": 2, "label": "T4/B64MiB", "copy_ms": 844.36, "gbps": 14.5789},
  {"index": 3, "label": "T4/B128MiB", "copy_ms": 827.014, "gbps": 14.8847},
  {"index": 4, "label": "T4/B256MiB", "copy_ms": 839.888, "gbps": 14.6566},
  {"index": 5, "label": "T4/B1024MiB", "copy_ms": 792.67, "gbps": 15.5296},
  {"index": 6, "label": "T8/B32MiB", "copy_ms": 740.017, "gbps": 16.6346},
  {"index": 7, "label": "T8/B64MiB", "copy_ms": 706.89, "gbps": 17.4141},
  {"index": 8, "label": "T8/B128MiB", "copy_ms": 706.902, "gbps": 17.4138},
  {"index": 9, "label": "T8/B256MiB", "copy_ms": 699.357, "gbps": 17.6017},
  {"index": 10, "label": "T8/B1024MiB", "copy_ms": 777.126, "gbps": 15.8402},
  {"index": 11, "label": "T16/B32MiB", "copy_ms": 833.96, "gbps": 14.7607},
  {"index": 12, "label": "T16/B64MiB", "copy_ms": 816.109, "gbps": 15.0836},
  {"index": 13, "label": "T16/B128MiB", "copy_ms": 812.854, "gbps": 15.144},
  {"index": 14, "label": "T16/B256MiB", "copy_ms": 803.146, "gbps": 15.3271},
  {"index": 15, "label": "T16/B1024MiB", "copy_ms": 827.72, "gbps": 14.872}]}
```

(Full per-cell wall/CPU/allocator values in `_e27_fastsafe_unet_out.txt`.)

### RAW — run 1 Gantt (reconstructed from captured spans, same renderer)

```text
V2 REMOTE GANTT (reconstructed from captured spans)  origin=remote_python_resume  scale=50.579 ms/char
                    0s                 1s ...                29s
                    |--------------------------------------------------------------------
remote python resume █  start=+0.000000s end=+0.000000s dur=0.000ms
restore method       █████████████  start=+0.000000s end=+0.679535s dur=679.535ms
restore_first_line   █  start=+0.000000s end=+0.000000s dur=0.000ms
restore_reconcile_st █  start=+0.000000s end=+0.000000s dur=0.000ms
clip_manifest_availa █  start=+0.037160s end=+0.037195s dur=0.035ms
method entry                       █  start=+0.732486s end=+0.732486s dur=0.000ms
method_setup                       ██████████████  start=+0.732486s end=+1.461003s dur=728.517ms
clip_source_read                             ████████████████████...  start=+1.247897s end=+7.317376s dur=6069.478ms
CLIP GPU hydration                                                  ████████████...  start=+2.422041s end=+8.107339s dur=5685.298ms
CLIP bind                                            █  start=+8.043835s end=+8.044065s dur=0.230ms
UNET H2D            (later)                                ██████████████████  start=+18.110440s end=+19.020840s dur=910.400ms
sampling            (later)                                          ████████████...  start=+22.900529s end=+27.751582s dur=4851.053ms
VAE decode          (later)                                                    ██████████  start=+28.370345s end=+28.834069s dur=463.724ms
empty_cache                                        █  start=+7.999517s end=+7.999536s dur=0.019ms
output encode       (later)                                                        ███  start=+28.834902s end=+29.016276s dur=181.375ms
```

(Full 120-column render in `_e27_gantt_render.txt`; 394 `█` chars.)

### RAW — run 2 (run harness output tail; full in `_e27_run2_out.txt`)

```text
Request: v2-benchmark-0-4a89bac2ba4d | Fresh: YES | AWS/us-east-2 | RTX PRO 6000 Blackwell
Sampling 4734.4 ms | VAE transition 877.8 ms | VAE decode 335.4 ms | output 261.9 ms
COMMAND -> RESPONSE: 30.683s | non-scheduling 22.997s | scheduling 7.686s
OUTPUT_SHA = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260 (MATCH)
```

### RAW — forward-cast account (run 1; identical structure run 2)

```json
{"weight_casts": 1, "bias_casts": 252, "other_casts": 0,
 "source_bytes": 0, "dest_bytes": 15311175680,
 "wall_ms": 9.41, "cuda_event_wall_ms": 0.0, "allocations": 253,
 "dest_dtypes": {"torch.bfloat16": 1, "torch.float32": 252}}
```

### RAW — empty_cache predicate (VAE-gate call, both runs identical)

```json
{"memory_required": 9703343462.6, "free_memory_kwargs": {"for_dynamic": "False", "pins_required": "167639366"},
 "mem_get_info_free_bytes": 78724857856, "mem_get_info_total_bytes": 101974081536,
 "memory_allocated_bytes": 20391913472, "memory_reserved_bytes": 22556966912,
 "active_bytes": 20391913472, "inactive_split_bytes": 23861248,
 "torch_allocator_free_bytes": 2165053440, "threshold_numerator": 2165053440,
 "threshold_denominator": 101974081536, "threshold_ratio": 0.021231,
 "threshold_25pct_of_total": 25493520384.0, "high_vram_mode": "None"}
```

## FUA-13. Final verdict (this follow-up)

```text
E27_FIVE_TARGET_FORENSICS = COMPLETE

VALID_GENERATION_RUNS = 2 (both structurally valid; output SHA matches the
  accepted 20b10e1f... reference on both)

TARGET_A_LOADER = COMPLETE — first-touch fastsafe screening: threads=8 +
  64-256 MiB block wins (CLIP 490.7 ms / UNET 699.4 ms vs 3066.6/4287.4 ms
  controls); architecture A (configure existing fastsafetensors)
TARGET_B_EMPTY_CACHE = COMPLETE — current runtime call is 0.3-2.2 ms (NOT
  D18's 740-950 ms); 25% branch does not fire (ratio 0.0212); bypass
  target <2 ms → LOW VALUE; D18 conclusion superseded
TARGET_C_EARLIEST_CLIP = COMPLETE — frozen manifest at +37 ms after
  restore; source I/O legal at +0 ms; T8/B64MiB loader (491 ms) fits the
  ~2.2-2.4 s pre-demand window; speculative lane consumed on both runs
TARGET_D_FP32_CAST_ONCE = COMPLETE — real Qwen: 253 casts/forward,
  15.31 GB materialized, 6-10 ms wall; exact FP32 residency 16.09 GB
  (all BF16 source, 8.04 GB); saving ~6-10 ms (LOW VALUE)
TARGET_E_GANTT = COMPLETE — real-run span report (15 spans) + exact
  reconstruction with █ bars; overhead <0.001 ms render / 6,291 B payload

REMOTE_DEPLOYS_THIS_FOLLOWUP = 4 (a-shadow v5, b-shadow v1, c-shadow v1,
  restore-only v5+v6)
PROBE_REQUESTS_THIS_FOLLOWUP = ~12 (snapshot/env/dtype/fastsafe/resident)
GENERATION_RUNS_THIS_FOLLOWUP = 2 (both valid, output-exact)
COMMIT = none
```


---

## FINAL GIT STATUS (literal, end of E27 Follow-Up A)

```text
git rev-parse HEAD          => a6a755e8dc923e933d13567ec07ddf5b6988f948
git branch --show-current  => TESTING2
git status --short (complete, literal):
 M .gitignore
 M __init__.py
 M canonical_execution.py
 M comfyapp.py
 M comfymodal_runtime/clip_conditioning_cache.py
 M comfymodal_runtime/contracts.py
 M comfymodal_runtime/cpu_snapshot_models.py
 M comfymodal_runtime/full_execution_trace.py
 M comfymodal_runtime/local_handle_client.py
 M comfymodal_runtime/local_handle_owner.py
 M comfymodal_runtime/modal_app.py
 M comfymodal_runtime/modal_transport.py
 M comfymodal_runtime/model_preload.py
 M comfymodal_runtime/output_delivery.py
 M comfymodal_runtime/playground_service.py
 M comfymodal_runtime/result_delivery.py
 M comfymodal_runtime/runtime_bootstrap.py
 M comfymodal_runtime/runtime_executor.py
 M comfymodal_runtime/snapshot_build_manifest.py
 M comfymodal_runtime/trace.py
 M comfymodal_runtime/unet_backing.py
 M comfymodal_runtime/v2_experiments.py
 M comfymodal_runtime/v2_waterfall.py
 M deploy_and_run_v2_single.bat
 M deploy_v2_full_trace_only.bat
 M experiment_runner.py
 M experiment_service.py
 M output_converter.py
 M package.json
 M playwright.config.mjs
 M run_v2_single.bat
 M studio_run_adapter.py
 M studio_store.py
 M tests/browser/modal_testing_suite_smoke.mjs
 M tests/browser/studio-mock-api.mjs
 M tests/test_benchmark_v2_proof_collection.py
 M tests/test_cpu_snapshot_models.py
 M tests/test_deployment_proof.py
 M tests/test_local_submission_critical_path.py
 M tests/test_milestone1_v2_runtime.py
 M tests/test_model_preload_attribution.py
 M tests/test_persistent_handle_transport.py
 M tests/test_plan_validation_proof.py
 M tests/test_runtime_canonical_v2.py
 M tests/test_runtime_contracts.py
 M tests/test_runtime_playground_v2.py
 M tests/test_step3_fast_path.py
 M tests/test_studio_backend.py
 M tests/test_studio_direct_run.py
 M tests/test_studio_progress_tracker.py
 M tests/test_testing_results_js.py
 M tests/test_testing_settings_js.py
 M tests/test_testing_shell_integration.py
 M tests/test_testing_ui_wired.py
 M tests/test_v2_ab_experiments.py
 M tests/test_v2_active_profile_inherit_noop.py
 M tests/test_v2_benchmark_trace_handoff.py
 M tests/test_v2_cold_warm_parity.py
 M tests/test_v2_cpu_snapshot_lifecycle.py
 M tests/test_v2_direct_execution_boundary.py
 M tests/test_v2_final_observability.py
 M tests/test_v2_full_execution_trace.py
 M tests/test_v2_full_trace_lifecycle.py
 M tests/test_v2_lane_a_disk_persistence.py
 M tests/test_v2_local_pre_submit_optimization.py
 M tests/test_v2_local_submission_timing.py
 M tests/test_v2_preload_bridge.py
 M tests/test_v2_snapshot_restore_only.py
 M tests/test_v2_waterfall.py
 M tests/test_warmup_profile_dedup.py
 M tests/test_waterfall_attach_central.py
 M tests/test_waterfall_reconciliation.py
 M tests/test_waterfall_scheduling_denominator.py
 M tests/v2_waterfall_reconciliation_fixtures.py
 M tools/benchmark_v2_direct.py
 M tools/record_deployment_identity.py
 M web/studio-backend-api.js
 M web/studio-experiment-mode.js
 M web/studio-output-preferences.js
 M web/studio-playground-state.js
 M web/studio-playground.js
 M web/studio-settings.js
 M web/studio-shell.js
 M web/studio-styles.js
?? '
?? .commandcode/
?? PHASE_D_FOLLOWUP_2_REPORT_2026-08-16.md
?? PHASE_D_FOLLOWUP_RECONCILIATION_2026-08-15.md
?? PHASE_D_INTERFACE_FREEZE.md
?? PHASE_E1_HISTORY_ASSET_SEMANTICS_AUDIT_2026-08-17.md
?? PHASE_E2_PREVIEW_CODEC_LOCAL_BENCHMARK_2026-08-17.md
?? PHASE_E2_PREVIEW_PIPELINE_COMPRESSION_AUDIT_2026-08-17.md
?? PHASE_E3_GENERATE_ORIGINAL_REPLAY_BACKEND_AUDIT_2026-08-17.md
?? PHASE_E4_FRONTEND_SETTINGS_EXPERIMENT_AUDIT_2026-08-17.md
?? PHASE_E5_TEST_REGRESSION_GATE_AUDIT_2026-08-17.md
?? STUDIO_MODERN_EXPERIMENT_MIGRATION_PLAN.md
?? STUDIO_TEST_GATE.md
?? V2_10_COLD_RUNS_35S_COOLDOWN.md
?? V2_BATCH_A_ACCEPTANCE_HARNESS_REPORT.md
?? V2_BATCH_A_G1_AND_TERMINAL_STAMPS_REPORT.md
?? V2_BATCH_A_HOST_TELEMETRY_SHIPPING_AUDIT.md
?? V2_BATCH_A_INTEGRATED_ACCEPTANCE.md
?? V2_BATCH_A_MODELS_VOLUME_RELOAD_GUARD_REPORT.md
?? V2_BATCH_A_PER_NODE_TIMELINE_REPORT.md
?? V2_BATCH_B_ACCEPTANCE_HARNESS_REPORT.md
?? V2_BATCH_B_CACHE_DEPLOYMENT_HANDOFF_RESEARCH.md
?? V2_BATCH_B_INTEGRATED_ACCEPTANCE_AND_COHORT.md
?? V2_BATCH_B_RUNTIME_STATE_RELOAD_GUARD_REPORT.md
?? V2_BATCH_B_SNAPSHOT_HYGIENE_AND_STAGE13_REPORT.md
?? V2_BATCH_C10_EXTERNAL_CONCURRENT_LOADERS_REPORT.md
?? V2_BATCH_C10_EXTERNAL_LOADER_SURVEY.md
?? V2_BATCH_C11_MODAL_STORAGE_AUDIT.md
?? V2_BATCH_C12_SAFETENSORS_LAYOUT_SHARDING_REPORT.md
?? V2_BATCH_C13_NATIVE_FAST_DISK_FORENSIC_AUDIT.md
?? V2_BATCH_C1_IMMUTABLE_PLAN_IDENTITY_REPORT.md
?? V2_BATCH_C2_ACCEPTANCE_FAST_PATH_REPORT.md
?? V2_BATCH_C3_WATERFALL_CONTRACT_REPORT.md
?? V2_BATCH_C4_HYGIENE_AB_REPORT.md
?? V2_BATCH_C4_HYGIENE_ANALYZER_SEMANTIC_FIX_REPORT.md
?? V2_BATCH_C4_HYGIENE_OPERATIONAL_PREFLIGHT.md
?? V2_BATCH_C4_SNAPSHOT_HYGIENE_AB_PREP_REPORT.md
?? V2_BATCH_C4_SNAPSHOT_HYGIENE_RECOVERY_REPORT.md
?? V2_BATCH_C5_VAE_FIRST_STEP_AB_REPORT.md
?? V2_BATCH_C5_VAE_SAMPLING_OVERLAP_REPORT.md
?? V2_BATCH_C6_I3_CONFIG_AND_OVERLAP_GATE_REPORT.md
?? V2_BATCH_C6_PINNED_RING_FEASIBILITY_REPORT.md
?? V2_BATCH_C6_PINNED_RING_IMPLEMENTATION_REPORT.md
?? V2_BATCH_C6_PINNED_RING_PRODUCTION_DESIGN.md
?? V2_BATCH_C6_SALVAGE_V2_FEASIBILITY_AND_IMPLEMENTATION_REPORT.md
?? V2_BATCH_C6_UNET_READ_H2D_PIPELINE_FEASIBILITY.md
?? V2_BATCH_C6_UNET_READ_H2D_PROBE_REPORT.md
?? V2_BATCH_C7_ACCEPTANCE_HIERARCHY_FIX_REPORT.md
?? V2_BATCH_C8_META_NATIVE_HYBRID_FEASIBILITY.md
?? V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md
?? V2_BATCH_C9_MODAL_VOLUME_QUEUE_DEPTH_REPORT.md
?? V2_BATCH_C_INTEGRATED_VALIDATION_REPORT.md
?? V2_BATCH_D10_PHASE_D_INTEGRATION_VALIDATION.md
?? V2_BATCH_D12_CLIP_CRITICAL_PATH_FORENSICS.md
?? V2_BATCH_D13_REQUEST_ENTRY_SETUP_FORENSICS.md
?? V2_BATCH_D14_POST_SAMPLING_FORENSICS.md
?? V2_BATCH_D15_CRITICAL_GPU_LANE_COORDINATION.md
?? V2_BATCH_D16_REQUEST_ENTRY_CRITICAL_PATH_COMPRESSION.md
?? V2_BATCH_D17_SINGLE_USE_POST_SAMPLING_CLIP_LIFECYCLE.md
?? V2_BATCH_D18_VAE_SOFT_EMPTY_CACHE_GATE.md
?? V2_BATCH_D1_LOCAL_DISPATCH_REPORT.md
?? V2_BATCH_D2_GENERIC_CLIP_COLD_FORENSICS_REPORT.md
?? V2_BATCH_D3_GENERIC_CLIP_FAST_HYDRATION_REPORT.md
?? V2_BATCH_D4_META_AND_PIPELINE_FORENSICS_REPORT.md
?? V2_BATCH_D5_RUNTIME_WAIT_ATTRIBUTION_REPORT.md
?? V2_BATCH_D6_CLIP_RESTORE_LIFECYCLE_ROOT_CAUSE.md
?? V2_BATCH_D6_PHASE_D_INTEGRATION_PREFLIGHT.md
?? V2_BATCH_D6_REMOTE_VALIDATION_REPORT.md
?? V2_BATCH_D7_GENERIC_TEXT_ENCODER_ENCODE_LAB.md
?? V2_BATCH_D8_UNET_META_GET_MODEL_ROOT_CAUSE.md
?? V2_BATCH_D8_get_model_bench.json
?? V2_BATCH_D9_INPUT_TYPES_WARM_FORENSICS.md
?? V2_BATCH_E10_PHASE_E_INTEGRATION_AB.md
?? V2_BATCH_E11_SOURCE_ORDER_STREAMING.md
?? V2_BATCH_E12_CHECKPOINT_PREWARM.md
?? V2_BATCH_E13_MODAL_STORAGE_AUDIT.md
?? V2_BATCH_E14_SOURCE_IO_BENCHMARK.md
?? V2_BATCH_E15_EXTERNAL_LOADER_FEASIBILITY.md
?? V2_BATCH_E16_REMOTE_SOURCE_IO_PREFLIGHT.md
?? V2_BATCH_E16_RUN1.json
?? V2_BATCH_E16_RUN2.json
?? V2_BATCH_E17_FINAL_COLD_LOADER_ASSEMBLY.md
?? V2_BATCH_E18_FINAL_LOADER_HARDENING.md
?? V2_BATCH_E19_SINGLE_DEPLOYED_COLD_VALIDATION.md
?? V2_BATCH_E1_STAGED_CORE.md
?? V2_BATCH_E20_CLEAN_FINAL_LOADER_VALIDATION.md
?? V2_BATCH_E21_CRITICAL_PATH_RECONCILIATION.md
?? V2_BATCH_E22_ADDITIONAL_RUNS.md
?? V2_BATCH_E22_CAUSAL_AB_PREFLIGHT.md
?? V2_BATCH_E22_REMOTE_CAUSAL_AB.md
?? V2_BATCH_E23_CRITICAL_PATH_FORENSICS.md
?? V2_BATCH_E24_CRITICAL_PATH_CLOSURE.md
?? V2_BATCH_E25_WHOLE_CRITICAL_PATH_COMPRESSION.md
?? V2_BATCH_E26_CONCRETE_COLD_WINS.md
?? V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md
?? V2_BATCH_E2_CLIP_STAGED_HYDRATION.md
?? V2_BATCH_E3_UNET_STAGED_TRANSPORT.md
?? V2_BATCH_E4_STAGED_TRANSPORT_BENCHMARK.md
?? V2_BATCH_E5_EMPTY_CACHE_BYPASS_AUDIT.md
?? V2_BATCH_E6_POST_RESPONSE_GPU_CLEANUP.md
?? V2_BATCH_E7_CUDA_ALLOCATOR_POLICY.md
?? V2_BATCH_E8_COMFY_NATIVE_TRANSPORT_REUSE.md
?? V2_BATCH_E9_TWO_APP_AB_PLAN.md
?? V2_CACHED_FIRST_NODE_PRODUCTION_DEFAULTS_AND_RESTORE_CHARACTERIZATION.md
?? V2_D11_3_RUN_PERFORMANCE_2026-08-16.md
?? V2_D11_PERFORMANCE_2026-08-16.md
?? V2_GENERIC_FIRST_NODE_PRESAMPLER_DELAY_RESEARCH.md
?? V2_HOST_HARDWARE_AND_PRESSURE_TELEMETRY.md
?? V2_PNG_PRESAMPLER_INVESTIGATION_AND_REAL_CAPTURE.md
?? V2_PRODUCTION_DEFAULTS_2026-08-13.md
?? V2_PROMPT_CACHE_CONDITIONING_PREFETCH_AND_STARTUP_REPORT.md
?? V2_PROMPT_CACHE_PREFETCH_STARTUP_FREEZE.md
?? V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md
?? V2_RUN4_BAD_HOST_FORENSICS.md
?? V2_SNAPSHOT_ARCHITECTURE_AND_WORKING_SET_RESEARCH.md
?? V2_UNET_READ_H2D_OVERLAP_RESEARCH.md
?? V2_WATERFALL_FINAL_CORRECTNESS_REPORT.md
?? WORKFLOW_MANIFEST_FORMAT.md
?? WS_FILE
?? _e27_append_status.py
?? _e27_clip_qd_evidence.json
?? _e27_deploy_wrapper.bat
?? _e27_direct_probe.py
?? _e27_dtypes_err.txt
?? _e27_dtypes_out.txt
?? _e27_embed_qd.py
?? _e27_env_probe.py
?? _e27_env_probe_result.txt
?? _e27_fastsafe_clip_err.txt
?? _e27_fastsafe_clip_out.txt
?? _e27_fastsafe_unet_err.txt
?? _e27_fastsafe_unet_out.txt
?? _e27_followup_deploy.log
?? _e27_followup_deploy2.log
?? _e27_followup_deploy3.log
?? _e27_followup_deploy4.log
?? _e27_followup_deploy5.log
?? _e27_followup_probe.py
?? _e27_gantt_render.txt
?? _e27_gather.py
?? _e27_overhead_out.txt
?? _e27_probe.py
?? _e27_probe_b1.txt
?? _e27_render_gantt.py
?? _e27_resident2_out.txt
?? _e27_ro_env.txt
?? _e27_ro_probe.txt
?? _e27_ro_probe2.txt
?? _e27_ro_probe3.txt
?? _e27_run1_out.txt
?? _e27_run2_out.txt
?? _e27_run_single.bat
?? _e27_sizes.py
?? _e27_snapshot_probe.py
?? _e27_snapshot_probe_result.json
?? _e27_unet_qd_evidence.json
?? _test_clip_fast_hydration.py
?? arm_a_config.txt
?? arm_b_config.txt
?? batch-c11-ready-state.png
?? batch-c5-failed-state.png
?? batch-c5-handoff-selection-only.png
?? batch-c5-playground-ready-state.png
?? batch-c5-ready-state.png
?? c13-console-errors.txt
?? c13-followup-live-console-errors.txt
?? c13-followup-preflight-network.txt
?? c13-followup-ready-state.png
?? c13-followup-run-preflight.txt
?? c13-followup-run-request-body.json
?? c13-followup-run-response-body.json
?? c13-ready-state.png
?? c15-history-ui-state.png
?? c15-ready-state.png
?? c16-history-c15-detail.png
?? c16-history-c15.png
?? c4_armA_console.log
?? c4_armA_deploy2.log
?? c4_armA_retry1.log
?? c4_armA_retry2.log
?? c4_armA_retry3.log
?? c4_armA_retry4.log
?? c4_armA_retry5.log
?? c4_armA_retry6.log
?? c4_armA_retry7.log
?? c4_armA_retry8.log
?? c5-studio-network.txt
?? cancel-proof-modal-follow-2.err.log
?? cancel-proof-modal-follow-2.log
?? cancel-proof-modal-follow.err.log
?? cancel-proof-modal-follow.log
?? cancel-proof-server-2.stderr.log
?? cancel-proof-server-2.stdout.log
?? cancel-proof-server-3.stderr.log
?? cancel-proof-server-3.stdout.log
?? cancel-proof-server-4.stderr.log
?? cancel-proof-server-4.stdout.log
?? cancel-proof-server-5.stderr.log
?? cancel-proof-server-5.stdout.log
?? cancel-proof-server.stderr.log
?? cancel-proof-server.stdout.log
?? comfymodal_runtime/checkpoint_prewarm.py
?? comfymodal_runtime/clip_cold_path_forensics.py
?? comfymodal_runtime/clip_fast_hydration.py
?? comfymodal_runtime/clip_fast_hydration_wiring.py
?? comfymodal_runtime/e27_followup_probe.py
?? comfymodal_runtime/e27_forensics.py
?? comfymodal_runtime/empty_cache_bypass.py
?? comfymodal_runtime/execution_warm.py
?? comfymodal_runtime/fast_cold_orchestration.py
?? comfymodal_runtime/gantt_telemetry.py
?? comfymodal_runtime/gpu_lane_coordination.py
?? comfymodal_runtime/host_hardware_telemetry.py
?? comfymodal_runtime/pre_graph_cache.py
?? comfymodal_runtime/prompt_signature_cache.py
?? comfymodal_runtime/registry_proof_store.py
?? comfymodal_runtime/runtime_generation.py
?? comfymodal_runtime/snapshot_capture_hygiene.py
?? comfymodal_runtime/source_order_safetensors.py
?? comfymodal_runtime/speculative_clip_hydration.py
?? comfymodal_runtime/stage13_breakdown.py
?? comfymodal_runtime/staged_safetensors.py
?? comfymodal_runtime/unet_fastsafetensors.py
?? comfymodal_runtime/unet_meta_direct.py
?? comfymodal_runtime/unet_qd_probe.py
?? comfymodal_runtime/unet_salvage_probe.py
?? comfymodal_runtime/wait_attribution.py
?? console-after-reload.log
?? custom_node_registry.py
?? d18_remote_deploy.log
?? d18_run1.log
?? d18_run2.log
?? d18_run3.log
?? d7-network-after-40s.txt
?? d7-network-after-run.txt
?? d7-preflight-ready.png
?? d7-status-100s.txt
?? d7-status-220s.txt
?? d7-status-310s.txt
?? d7-status-430s.txt
?? d7r-experiment-actual.har
?? d7r-experiment.har
?? d7r-generation-detail-empty.png
?? d7r-history-feed-card.png
?? d7r2-original-0.png
?? d7r2-original-1.png
?? dependency_resolver.py
?? deploy_e16_source_benchmark.bat
?? e16_source_io.py
?? e16_source_io_modal.py
?? e25_preflight.log
?? experiment_modern_plan.py
?? experiment_modern_routes.py
?? experiment_modern_scheduler.py
?? history_v2_migration.py
?? history_v2_models.py
?? history_v2_replay.py
?? history_v2_repository.py
?? history_v2_routes.py
?? history_v2_store.py
?? history_v2_writer.py
?? model_library.py
?? model_library_routes.py
?? playwright.fake.config.mjs
?? run_e14_source_io.bat
?? run_e16_source_benchmark.bat
?? studio-api-after-failure.json
?? studio-handoff-selection.png
?? studio-history-summary-after-failure.json
?? studio-initial.png
?? studio-live-blocked-remote-404.png
?? studio-modern-failed.png
?? studio-modern-payload-probe.json
?? studio-modern-playground-ready.png
?? studio-modern-running.png
?? studio-ready-to-run.png
?? studio-second-console.log
?? studio-second-failed.png
?? studio-second-health.json
?? studio-second-history-summary.json
?? studio-second-network.txt
?? studio-second-ready-state.json
?? studio-second-ready.png
?? studio-workflows-tab.png
?? studio_domain/
?? studio_workflow_manifest.py
?? studio_workflow_routes.py
?? studio_workflow_run.py
?? tests/_test_env.py
?? tests/browser/fake/
?? tests/browser/studio-history-v2.spec.mjs
?? tests/browser/studio-settings.spec.mjs
?? tests/browser/studio-workflows-mock.mjs
?? tests/browser/studio-workflows.spec.mjs
?? tests/d1_store_isolation.py
?? tests/phase_e_fixtures.py
?? tests/phase_e_wave2_fixtures.py
?? tests/run_studio_tests.py
?? tests/studio_experiment_v2_frontend_unit.mjs
?? tests/studio_experiment_v2_unit.mjs
?? tests/studio_history_v2_experiment_unit.mjs
?? tests/studio_history_v2_persisted_status_unit.mjs
?? tests/studio_phase_e_contract_unit.mjs
?? tests/studio_phase_e_history_presentation_unit.mjs
?? tests/studio_phase_e_preview_settings_unit.mjs
?? tests/studio_phase_e_wave2_unit.mjs
?? tests/studio_playground_run_unit.mjs
?? tests/studio_run_model_unit.mjs
?? tests/studio_workflow_run_unit.mjs
?? tests/test_batch_a_acceptance.py
?? tests/test_batch_acceptance_ordering.py
?? tests/test_batch_b_acceptance.py
?? tests/test_batch_c1_immutable_plan_identity.py
?? tests/test_batch_c_acceptance.py
?? tests/test_benchmark_source_io_e14.py
?? tests/test_benchmark_source_io_e16.py
?? tests/test_benchmark_v2_snapshot_hygiene_ab.py
?? tests/test_c6_meta_direct.py
?? tests/test_c6_read_h2d_probe.py
?? tests/test_c6_salvage_probe.py
?? tests/test_c8_meta_native.py
?? tests/test_c9_fastsafetensors_integration.py
?? tests/test_c9_qd_probe.py
?? tests/test_d4_forensics_reconciliation.py
?? tests/test_d6a_backend_integration.py
?? tests/test_dependency_resolver.py
?? tests/test_e27_followup_probe.py
?? tests/test_e27_forensics.py
?? tests/test_e27_gantt_telemetry.py
?? tests/test_e2_preview_codec.py
?? tests/test_e2_preview_mode.py
?? tests/test_experiment_modern_binding.py
?? tests/test_experiment_modern_plan.py
?? tests/test_history_v2_api.py
?? tests/test_history_v2_migration.py
?? tests/test_history_v2_mixed_pagination.py
?? tests/test_history_v2_modern_experiment.py
?? tests/test_history_v2_production_writer.py
?? tests/test_history_v2_replay_core.py
?? tests/test_history_v2_repository.py
?? tests/test_host_hardware_telemetry.py
?? tests/test_model_library.py
?? tests/test_model_library_routes.py
?? tests/test_models_volume_reload_guard.py
?? tests/test_modern_experiment_scheduler.py
?? tests/test_phase_e_contract.py
?? tests/test_phase_e_fake_parity.py
?? tests/test_phase_e_history_projection.py
?? tests/test_phase_e_logical_outputs.py
?? tests/test_phase_e_single_snapshot_replay.py
?? tests/test_phase_e_wave2_contract.py
?? tests/test_remote_cancel_bridge.py
?? tests/test_runtime_state_reload_guard.py
?? tests/test_studio_history_v2_js.py
?? tests/test_studio_workflow_manifest.py
?? tests/test_studio_workflow_run_plan_identity.py
?? tests/test_transport_cancellation.py
?? tests/test_v2_batch_a_g1_terminal_stamps.py
?? tests/test_v2_batch_d15_critical_gpu_lane_coordination.py
?? tests/test_v2_batch_d1_local_dispatch.py
?? tests/test_v2_batch_d1_registry_proof_store.py
?? tests/test_v2_batch_d5_wait_attribution.py
?? tests/test_v2_batch_e15_external_loader_feasibility.py
?? tests/test_v2_batch_e5_empty_cache_bypass.py
?? tests/test_v2_clip_cold_forensics.py
?? tests/test_v2_clip_eviction_lifecycle.py
?? tests/test_v2_clip_eviction_reconcile.py
?? tests/test_v2_clip_fast_hydration_production.py
?? tests/test_v2_clip_hydration_states.py
?? tests/test_v2_clip_restore_lifecycle.py
?? tests/test_v2_conditioning_cache_nonce.py
?? tests/test_v2_conditioning_exact_hit_breakdown.py
?? tests/test_v2_conditioning_prefetch.py
?? tests/test_v2_d1_dispatch_hash.py
?? tests/test_v2_d1_stale_identity.py
?? tests/test_v2_d1_store_isolation.py
?? tests/test_v2_d6_deploy_profile.py
?? tests/test_v2_d7_text_encoder_encode_lab.py
?? tests/test_v2_d8_get_model_forensics.py
?? tests/test_v2_d9_input_types_warm.py
?? tests/test_v2_e11_source_order_streaming.py
?? tests/test_v2_e12_checkpoint_prewarm.py
?? tests/test_v2_e17_final_cold_loader.py
?? tests/test_v2_e18_final_loader_hardening.py
?? tests/test_v2_e19_atomic_profile.py
?? tests/test_v2_e25_pre_graph_and_speculative.py
?? tests/test_v2_e26_concrete_cold_wins.py
?? tests/test_v2_e2_clip_staged_hydration.py
?? tests/test_v2_e3_unet_staged_transport.py
?? tests/test_v2_host_breakdown_lines.py
?? tests/test_v2_host_submission_breakdown.py
?? tests/test_v2_per_node_timeline.py
?? tests/test_v2_phase_d_telemetry_integration.py
?? tests/test_v2_prompt_executor_breakdown.py
?? tests/test_v2_prompt_signature_cache.py
?? tests/test_v2_snapshot_capture_hygiene.py
?? tests/test_v2_snapshot_manifest_hygiene_extensions.py
?? tests/test_v2_stage13_breakdown.py
?? tests/test_v2_staged_safetensors_core.py
?? tests/test_v2_transport_boundaries.py
?? tests/test_v2_unique_prompt_suffix.py
?? tests/test_v2_vae_sampling_first_step.py
?? tests/test_v2_waterfall_contract.py
?? tests/test_v2_waterfall_scheduling_contract.py
?? tests/test_workflow_domain.py
?? tests/test_workflow_routes.py
?? tests/test_workflow_run_integration.py
?? tools/batch_a_acceptance.py
?? tools/batch_b_acceptance.py
?? tools/batch_c_acceptance.py
?? tools/benchmark_source_io_e14.py
?? tools/benchmark_staged_safetensors_local.py
?? tools/benchmark_text_encoder_encode.py
?? tools/benchmark_v2_snapshot_hygiene_ab.py
?? tools/c10_loader_api_probe.py
?? tools/c12_plan_safetensors_shards.py
?? tools/d7_deep_profile.json
?? tools/d7_lp_deep.json
?? tools/d7_lp_results.json
?? tools/d7_results_full.json
?? tools/d9_input_types_warm_forensics.py
?? tools/d9_measurements.json
?? tools/inspect_modal_model_storage.py
?? tools/run_c9_qd_probe.py
?? tools/v2_d8_get_model_forensics.py
?? v2_batchb_cohort2_console.log
?? v2_batchb_cohort_console.log
?? v2_batchb_data2_console.log
?? v2_batchb_probe_console.log
?? v2_batchb_run1_console.log
?? v2_batchb_run1b_console.log
?? v2_batchb_run1c_console.log
?? v2_batchc_integrated_deploy.log
?? v2_batchc_integrated_validation.log
?? v2_batchc_integrated_validation2.log
?? v2_batchc_integrated_validation3.log
?? v2_c2f_10cold_35gap.log
?? v2_c2f_8cold_20gap.log
?? v2_c2f_deploy_1.log
?? v2_c2f_deploy_2.log
?? v2_c2f_deploy_3.log
?? v2_c2f_deploy_4.log
?? v2_c2f_deploy_5.log
?? v2_c2f_restore_char_1.log
?? v2_c2f_restore_char_2.log
?? v2_c2f_restore_char_3.log
?? v2_c2f_restore_char_4.log
?? v2_c2f_restore_char_5.log
?? v2_c2f_run_1_validation.log
?? v2_c2f_run_2_post_snapshot.log
?? v2_c2f_run_3_final_capture.log
?? v2_c5_armA_validation.log
?? v2_c5_armB_deploy.log
?? v2_c5_armB_deploy2.log
?? v2_c5_armB_validation.log
?? v2_c5_armB_validation2.log
?? v2_d10_applist.txt
?? v2_d10_applist_full.json
?? v2_d10_applogs_1.txt
?? v2_d10_applogs_all_stdout.txt
?? v2_d10_applogs_full.txt
?? v2_d10_applogs_info_snapshot.txt
?? v2_d10_applogs_info_v2.txt
?? v2_d10_applogs_stdout_v2.txt
?? v2_d10_applogs_v41_deploy3.txt
?? v2_d10_applogs_v42_deploy4.txt
?? v2_d10_corrected_identity.err.txt
?? v2_d10_corrected_identity.out.txt
?? v2_d10_corrected_prime.out.txt
?? v2_d10_corrected_request.out.txt
?? v2_d10_corrected_request_applogs.txt
?? v2_d10_corrected_request_run1.out.txt
?? v2_d10_deploy_1.err.log
?? v2_d10_deploy_1.log
?? v2_d10_deploy_corrected_1.log
?? v2_d10_final_request.out.txt
?? v2_d10_identity_record.err.txt
?? v2_d10_identity_record.out.txt
?? v2_d11_deploy_1.log
?? v2_d11_request_1.log
?? v2_d11_request_2.log
?? v2_d11_request_3.log
?? v2_d11_request_4.log
?? v2_d11_request_5.log
?? v2_d11_request_6.log
?? v2_hosttelemetry_deploy_1.log
?? v2_hosttelemetry_deploy_2.log
?? v2_hosttelemetry_deploy_3.log
?? v2_hosttelemetry_deploy_4.log
?? v2_hosttelemetry_deploy_5.log
?? v2_hosttelemetry_deploy_6.log
?? v2_hosttelemetry_deploy_6b.log
?? v2_hosttelemetry_deploy_6c.log
?? v2_hosttelemetry_deploy_6d.log
?? v2_hosttelemetry_run_1.log
?? v2_hosttelemetry_run_2.log
?? v2_hosttelemetry_run_3.log
?? v2_hosttelemetry_run_4.log
?? v2_hosttelemetry_run_5.log
?? v2_hosttelemetry_run_6.log
?? v2_pcc_construction.log
?? v2_pcc_deploy2_construction.log
?? v2_pcc_deploy3_construction.log
?? v2_pcc_deploy4_construction.log
?? v2_pcc_deploy5_construction.log
?? v2_pcc_deploy6_construction.log
?? v2_pcc_deploy7_construction.log
?? v2_pcc_deploy8_construction.log
?? v2_pcc_deploy_1.log
?? v2_pcc_deploy_2.log
?? v2_pcc_deploy_2b.log
?? v2_pcc_deploy_2c.log
?? v2_pcc_deploy_3.log
?? v2_pcc_deploy_4.log
?? v2_pcc_deploy_4b.log
?? v2_pcc_deploy_5.log
?? v2_pcc_deploy_6.log
?? v2_pcc_deploy_7.log
?? v2_pcc_deploy_8.log
?? v2_pcc_run1_container.log
?? v2_pcc_run1b_container.log
?? v2_pcc_run1c_container.log
?? v2_pcc_run1d_container.log
?? v2_pcc_run1e_container.log
?? v2_pcc_run1f_container.log
?? v2_pcc_run1h_container.log
?? v2_pcc_run2_container.log
?? v2_pcc_run_1_validation.log
?? v2_pcc_run_1b_validation.log
?? v2_pcc_run_1c_validation.log
?? v2_pcc_run_1d_validation.log
?? v2_pcc_run_1e_validation.log
?? v2_pcc_run_1f_validation.log
?? v2_pcc_run_1g_validation.log
?? v2_pcc_run_1h_validation.log
?? v2_pcc_run_2_post_snapshot.log
?? v2_pcc_run_2b_post_snapshot.log
?? v2_pcc_run_2c_post_snapshot.log
?? v2_pcc_run_3_final_capture.log
?? v2_png_deploy_1.log
?? v2_png_deploy_2.log
?? v2_png_deploy_3.log
?? v2_png_run_1_validation.log
?? v2_png_run_1b_validation.log
?? v2_png_run_1c_validation.log
?? v2_png_run_1d_validation.log
?? v2_png_run_2_post_snapshot.log
?? v2_png_run_2b_post_snapshot.log
?? v2_png_run_3_final_capture.log
?? v2_waterfall_deploy_1.log
?? v2_waterfall_deploy_2.log
?? v2_waterfall_deploy_3.log
?? v2_waterfall_deploy_4.log
?? v2_waterfall_deploy_5.log
?? v2_waterfall_run_1_validation.log
?? v2_waterfall_run_2_validation.log
?? v2_waterfall_run_3_validation.log
?? v2_waterfall_run_4_final_acceptance.log
?? v2_waterfall_run_5_validation.log
?? v2_waterfall_run_6_final_acceptance.log
?? v2_waterfall_run_7_validation.log
?? v2_waterfall_run_8_final_acceptance.log
?? web/history-v2-fixtures.js
?? web/history-v2-repository.js
?? web/history-v2-view-state.js
?? web/studio-history-v2-detail.js
?? web/studio-history-v2-experiment.js
?? web/studio-history-v2.js
?? web/studio-model-library.js
?? web/studio-playground-run.js
?? web/studio-run-adapters.js
?? web/studio-run-model.js
?? web/studio-workflow-run.js
?? web/studio-workflows.js
```

No commit, push, branch, worktree, stash, reset, or revert occurred during
the original E27 batch or the E27 Follow-Up A.
