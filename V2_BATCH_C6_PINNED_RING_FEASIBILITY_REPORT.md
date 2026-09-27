# V2 Batch C6 — Multi-Buffer Pinned-Staging Ring Feasibility Microprobe

Date: 2026-08-15
Mode: measurement-only (probe mode `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE=probe`; default path byte-identical).
No production pipeline implemented; no pinned staging introduced into the production path; no mmap/DISABLE_MMAP changes; no commit.

## Valid probe run

Run dir: `comfymodal-data/benchmarks/runs/v2_2026-08-15_00-33-37/` (run_0.json)
Deployment: `stable-modal-comfy-v2-c6probe-shadow`, deployment_combined_hash `852fe14165055efa`, comfyui_core_match=1
Fresh: YES | B1 exact-match: observed | Local waterfall reconciliation 6.2 ms OK (host rebuild FAILED — pre-existing vehicle property, baseline-identical)
Output SHA: `sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` — **identical to the probe-off baseline** (4th consecutive byte-identical run)
Lifecycle: exactly one authoritative UNET load (one `unet_fast_disk_complete decision=complete`, one `normal_loader_ready`); final state load=cuda:0, offload=cuda:0, first_parameter_device=cuda:0, dtype=bfloat16 — GPU-ready; no fallback/error.
Probe event: `unet_i3_pinned_ring_probe` = 1 (verdict COMPLETE, 12 representative chunks).

## What was measured

12 real mmap-backed UNET tensors (78,643,200 B and similar, real shapes 10240×3840 / 3840×10240 / 11520×3840), collected during the authoritative read, run post-load through four configs with TEMPORARY pinned CPU buffers + CUDA dests/events only. The authoritative load proceeded unchanged.

| Config | ring wall ms | total CPU stage ms | total H2D ms | serial-equiv ms | overlap eff |
|---|---|---|---|---|---|
| A pageable (mmap→GPU) | 174.75 | 0 | 172.50 | 172.50 | n/a |
| B pinned 1-buffer | 47.00 | 17.03 | 19.72 | 36.75 | 0.0 |
| C pinned 2-buffer | 30.01 | 15.43 | 18.64 | 34.08 | **0.264** |
| D pinned 3-buffer | 41.60 | 17.77 | 18.37 | 36.14 | 0.0 |

Per-chunk (78.6 MB) steady-state values:

| Metric | pageable | pinned1 | pinned2 | pinned3 |
|---|---|---|---|---|
| H2D host issue ms | 2.96–4.04 | 0.005–0.64 | 0.005–0.08 | 0.009–0.08 |
| CPU stage ms | — | 0.78–1.50 | 0.93–1.59 | 0.96–1.83 |
| H2D CUDA ms | 3.0–10.7* | 1.41–1.67 | 1.45–1.70 | 1.41–1.73 |
| DMA GB/s | ~20–26 | ~52–56 | ~50–55 | ~50–55 |
| reuse wait ms | — | ~1.4 (serialized) | 0.007–0.54 | 0.005–0.016 |

\* first chunk 127 ms (cold-stream artifact); steady state ~3–10 ms.

## The critical hypothesis — CONFIRMED

**Pinned H2D host issue is effectively asynchronous.** `copy_(non_blocking=True)` from pinned memory returns in **0.005–0.08 ms per chunk (median 0.0149 ms)** — a ~200–800× reduction vs pageable (2.96–4.04 ms per chunk in this run; 19–29 ms for the larger 78.6 MB sample in Gate-2). The host-side pageable staging barrier identified in Gate 2 is removed by pinning.

**Real CPU-stage/H2D overlap demonstrated:** the 2-buffer ring wall (30.0 ms) is below its serial-equivalent (34.1 ms) — overlap efficiency 0.264; and 83% below the pageable wall (174.7 ms). The 1-buffer config serializes as designed (eff 0.0). The 3-buffer config regressed (41.6 ms, eff 0.0) — more buffers are not better; the classifier selected **best_buffers = 2** (pinned2 wall ≤ 1.05×pinned3 AND eff2 ≥ 0.5 fails; pinned3 not materially better; lowest wall wins → 2).

**Contention:** CPU staging runs at ~50–100 GB/s (0.8–1.8 ms per 78.6 MB) and pinned DMA at ~50–55 GB/s concurrently without collapse (per-chunk rates stable across all configs; minflt Δ = 0; thread CPU 30–60 ms per 12-chunk config). The CPU staging thread is the busy resource; the DMA hides under it in the 2-buffer ring.

## Full-model extrapolation (12.31 GB, 453 tensors)

Measured inputs: I-1 read wall (page-in + materialize) 2174.5 ms this run / 1535–1624 ms healthy; bulk H2D 2315.5 ms this run / 2467.9 ms healthy; head (get_model 474.9 + bind 413.3 = 888 ms this run; 513.7 ms healthy); pinned CPU copy ~60 GB/s; pinned DMA ~52 GB/s; probe-measured per-chunk python overhead ~0.8 ms.

| Basis | serial chain | CPU total (page-in+copy+overhead) | predicted ring wall (+head) | saving |
|---|---|---|---|---|
| this run | 5378 ms | 2742 ms | 3630 ms | **1748 ms** |
| healthy | 4605 ms | 2616 ms | 2617 ms | **1989 ms** |

DMA (237 ms total) is fully hideable under the CPU-bound pipeline (2742 ms) — the ring pipeline is CPU-bound on page-in + staging, which the async DMA overlaps. Conservative estimate (30% discount for production per-chunk overheads and partial page-in concurrency): **~1200–1400 ms expected saving on healthy hosts** — the prior ~0.9–1.7 s estimate is REINSTATED and supported by direct measurement, unlike the Gate-2 direct-path estimate (0–0.05 s), which remains dead.

## Anti-regression evidence

- Output SHA identical to probe-off baseline; Fresh YES; one lifecycle; GPU-ready; B1 exact-match observed; no fallback/error.
- Temporary pinned buffers + CUDA dests never bound into the ModelPatcher (post-probe freed; `empty_cache`); probe disabled → zero probe code paths, byte-identical production.
- Diagnostics path: two earlier deploys in this gate failed cleanly (first: swallowed RuntimeError → added error_msg/fail_step capture; second: shape-mismatch on slot buffer reuse → per-slot shape/dtype tracking). Both diagnosed from artifact evidence and fixed before the valid run.

## Known probe limitations

- `cpu_gbps` field in records is GB/ms (unit off by 1000 vs the label); the stage_ms raw values are authoritative — CPU staging ~50–100 GB/s. Cosmetic; does not affect the decision; not worth a redeploy.
- Ring probe ran post-read on resident pages (page-in already happened during the authoritative read); the page-in cost is included in the extrapolation via the I-1 read wall, but the probe itself measured copy-of-resident pages.
- 12-chunk steady state only; per-chunk python overhead (0.8 ms) is instrumentation-inclusive and may shrink in a lean production implementation.

## Decision

### PROCEED TO PINNED-RING DESIGN

All five thresholds met:
1. pinned H2D host issue effectively asynchronous — YES (0.015 ms median vs pageable 3–29 ms);
2. real CPU-stage/H2D overlap demonstrated — YES (eff2 0.264; 2-buffer wall 30.0 < serial 34.1; 83% below pageable);
3. ring wall materially below serial-equivalent — YES (2-buffer ring);
4. conservative extrapolated healthy-run saving ≥ ~300 ms — YES (~1.2–1.4 s);
5. memory/CPU contention acceptable — YES (no rate collapse; CPU-bound, DMA hidden).

Design constraints for the production pinned-ring loader (NOT implemented here): prefer a 2-buffer ring (3 regressed); keep pinned buffer count bounded (≤2 × ~78.6 MB); per-chunk python overhead must be minimized (the 0.8 ms/chunk instrumentation overhead would add ~360 ms across 453 tensors in production); keep the single-tensor allow_fp16 value probe + header-config derivation (Gate-1 result) as the pre-read config source; per-key identity transform keeps bind fully incremental; final synchronize before future publication (TWO-LANE and mutation-lane semantics unchanged).

## Uncertainty (retained)

- The extrapolation assumes page-in rate and per-chunk overhead scale linearly to 453 tensors; small tensors (norm/bias) have higher per-tensor overhead and lower page-in efficiency (measured in I-1: ~305 ms on the first 4 tensors alone).
- Overlap efficiency 0.264 is modest; a production ring may do better (leaner per-chunk loop) or worse (real page-in concurrency). The conservative 30% discount covers this band.
- Single valid run per the standing rule; no cohort. Host variance between runs (read 1535–2174 ms) affects the absolute numbers, not the relative ring-vs-pageable result.

---

## You asked for:
- Measurement-only multi-buffer pinned-staging-ring feasibility microprobe: pageable vs 1/2/3-buffer pinned configs on real mmap-backed tensors, per-stage timing, contention evidence, full-model extrapolation, decision gate, and report.

## You should now manually check:
- **Decision: PROCEED TO PINNED-RING DESIGN** — the production ring loader is NOT implemented in this task; design work + a new decision are required before coding it (prefer 2 buffers; minimize per-chunk overhead; keep Gate-1 config derivation + identity transform; final sync before publication).
- The `cpu_gbps` record-field unit quirk (GB/ms vs GB/s) — harmless to the decision, but fix it if the ring probe is reused in the design phase.
- The 3-buffer regression (41.6 ms vs 30.0 ms for 2 buffers) — verify in the design phase whether it is a measurement artifact or a real effect before choosing a ring depth.
- Probe-off byte-identity: with the flag unset, none of the ring code paths fire (verified by tests + baseline runs); pinned staging remains OFF in production.
- Output SHA `20b10e1f...e5260` identical across all four probe generations — the instrumentation never altered the authoritative model.
