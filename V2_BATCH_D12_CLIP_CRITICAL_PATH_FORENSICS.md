# V2 Batch D12 — CLIP Critical-Path Forensics (Explain the 6.1–7.5 s Cold CLIP Encode)

ZERO-SPEND investigation. No Modal deploy/request, no benchmark execution, no
production-file edits, no commit. Source: the three D11 batch run JSONs with
embedded remote event traces (543–545 events each), host logs, and the
hydrator source in `comfymodal_runtime/`.

| | |
|---|---|
| Evidence source | `comfymodal-data/benchmarks/runs/v2_2026-08-16_18-26-58/run_0.json` (Run 2, GCP us-east4), `...v2_2026-08-16_18-29-25/...` (Run 5, GCP us-east4), `...v2_2026-08-16_18-30-19/...` (Run 6, AWS us-east-1) — remote `events` arrays |
| Host logs | `v2_d11_request_2.log`, `v2_d11_request_5.log`, `v2_d11_request_6.log` (aggregate numbers only) |
| Code | `comfymodal_runtime/clip_fast_hydration_wiring.py` (telemetry + `_try_fast_hydrate` L640), `comfymodal_runtime/clip_fast_hydration.py` (hydrate/bind/owner helpers) |
| Prior context | `V2_BATCH_D8_UNET_META_GET_MODEL_ROOT_CAUSE.md`, `V2_BATCH_D9_INPUT_TYPES_WARM_FORENSICS.md`, `V2_D11_3_RUN_PERFORMANCE_2026-08-16.md` |
| Times | ms relative to run-local t0 = min event `wall_unix_ns`; cross-process wall-clock precision, `clock_scope=cross_process` |

---

## 1. Executive answer

**The ~6.1–7.5 s cold CLIP encode is a per-request hydration re-read plus a
transformer forward, with the two lanes trading wait time exactly where the
D8-known UNET meta/H2D lane overlaps them.** Every meaningful millisecond of
the encode window is accounted; `OTHER` is 30–147 ms (≤2%).

1. **Hydration path executed: A (direct-GPU fast hydration) — CONFIRMED.**
   `clip_fh_hydration_decision` `@decision` = `{"decision":"fast_path",
   "reason":"fast_hydration_allowed","state_before":"EXCLUDED_PLACEHOLDER"}`
   (399 params, 8,044,936,196 bytes, all meta); `clip_fh_hydration_end` =
   `{"ok":true,"mode":"fastsafetensors_direct_gpu","fallback_count":0,
   "zero_copy":"398/398 keys share storage",...}`. Paths B/C/D/E are ruled out
   by mode, state, and `fallback_count` (B/C would be `mode=native`, D would
   not see `EXCLUDED_PLACEHOLDER`, E would not run).
2. **The "missing" `clip_fh_hydration_start/end` markers are a telemetry
   artifact, not a missing execution — CONFIRMED.** Both events are emitted
   back-to-back at *completion* (wiring L710–715), 40–80 µs apart at the same
   timestamp; they never delimit a window in console logs, and the host
   `v2_d11_request_*.log` pages do not surface the embedded event stream. The
   real hydration window is `decision` (entry) → `start/end` (exit): 4.36 s /
   1.53 s / 1.95 s.
3. **The single biggest confirmed cost differs per run because a concurrent
   lane moves across it:**
   - Run 2: **bind + device-sync wait = 2,889.7 ms** (hydration-total 4,358.7).
     CONFIRMED as *wait*, not work: the same bind code runs in 94–121 ms when
     uncontended (Runs 5/6), the encode thread's total CPU budget (1,790 ms
     incl. the 1,200 ms forward) cannot contain 2.9 s of work, and
     `cuda_delta_bytes = 20,355,218,432` proves the UNET fastsafetensors H2D
     (its own 12.3 GB) was allocating on the same context *inside* the bind
     window. The bind includes `torch.cuda.synchronize()` (wiring L684);
     unet lane overlapped the bind window 2,850 of 2,890 ms.
   - Runs 5/6: **forward = 4,578.6 / 5,333.9 ms** (the UNET lane starts
     *after* hydration ended and overlaps the forward instead). Clean-forward
     baseline (Run 2, no lane overlap) = 1,729.5 ms. Run 5 delay ≈ 2,849 =
     overlap −130 ms (SUPPORTED INFERENCE, within 4% of the 2,980 ms lane
     overlap); Run 6 delay ≈ 3,604 vs 2,863–2,950 ms overlap, leaving a
     ~700 ms AWS-specific residual (SUPPORTED INFERENCE with UNKNOWN
     residual).
4. **Aggregate over the batch: FORWARD = 11.64 s (59%), HYDRATION = 7.85 s
   (40%), OTHER = 0.23 s (1%).** The forward's own work is ~1.73 s per run;
   ~6.45 s of the batch forward wall is GPU-lane wait caused by the UNET
   meta/H2D lane (D8 root-cause: 2.78–3.02 s GIL-starved `get_model` + H2D
   copy) running concurrently by design in the prefill window.
5. **`input_types_warm` is NOT proven causal** (D9 verdict stands): its
   windows overlap the lane but effective cores are 0.16–0.19 and CPU is
   0.88–0.95 s spread over 4.88–5.56 s; in Run 2 it overlapped hydration
   (not forward), in Runs 5/6 its forward overlap (2.86–2.98 s) ≈ the UNET
   lane's, so it cannot be separately identified as cause.
6. **CONTENTION_SUPPORTED = YES** (Run 2 bind wait: CONFIRMED mechanism —
   sync semantics + CPU-budget + cuda_delta fingerprint; Run 5 forward
   delay: SUPPORTED INFERENCE, magnitude-matched; Run 6: SUPPORTED with
   ~700 ms UNKNOWN AWS residual).
7. **UNET_CAUSAL for the CLIP inflate = PROVEN for Run 2 (mechanism-level),
   SUPPORTED for Runs 5/6.**

---

## 2. Per-run critical path (remote event times, ms)

### Run 2 — GCP us-east4 — CLIP encode 6,127.1 ms scheduled

| t_start | t_end | span | ms | classification |
|---|---|---|---|---|
| 653,816.1 | 653,830.2 | tokenize | 14.1 | CONFIRMED |
| 653,830.2 | 653,831.6 | schedule→raw encode | 1.4 | CONFIRMED |
| 653,831.6 | 653,837.5 | loader-invoke entry → demand wrapper | 5.9 | CONFIRMED |
| 653,837.5 | 658,199.7 | **hydration (decision→end)** | **4,362.2** | CONFIRMED |
| 653,837.5+ | 655,306.0 | fastsafetensors file→GPU, 8.045 GiB | 1,468.5 @ 5.10 GB/s | CONFIRMED |
| 655,309.5 | 658,199.2 | **bind (zero-copy 398/398) + `torch.cuda.synchronize()`** | **2,889.7** | CONFIRMED (wall) / wait-dominated |
| — | — | unet meta lane (th=91) 655,379.6→658,159.5; pipeline H2D event @658,227.9 | 2,779.9 / 2,692.0 | CONFIRMED, overlaps bind 2,850/2,890 ms |
| 658,226.4 | 659,955.9 | **forward** | **1,729.5** (thread CPU 1,200) | CONFIRMED — clean (no lane overlap; warm ended 658,201.4, 25 ms before) |
| 659,955.9 | 659,957.3 | post-forward | 1.4 | CONFIRMED |
| | | OTHER = 6,127.1 − 4,362.2 − 1,729.5 = | **35.4** | prepare/eps/wrappers |

### Run 5 — GCP us-east4 — CLIP encode 6,142.5 ms scheduled

| t_start | t_end | span | ms | classification |
|---|---|---|---|---|
| 800,686.8 | 800,707.7 | tokenize | 20.9 | CONFIRMED |
| 800,707.8 | 800,708.6 | schedule→raw encode | 0.9 | CONFIRMED |
| 800,718.1 | 802,251.6 | **hydration** | **1,533.5** | CONFIRMED |
| | | file→GPU | 1,401.9 @ 5.34 GB/s | CONFIRMED |
| | | bind + sync | 120.8 (uncontended) | CONFIRMED |
| 802,270.5 | 806,849.0 | **forward** | **4,578.6** (thread CPU 1,500) | CONFIRMED (wall) |
| | | unet meta 802,264.6→805,280.5 (3,015.9); pipeline event @805,329.5 — overlaps forward 2,980–3,059 ms | | CONFIRMED coexistence |
| | | forward delay vs clean 1,729.5 = 2,849.1 ≈ overlap −130 | | SUPPORTED INFERENCE |
| | | OTHER = 6,142.5 − 1,533.5 − 4,578.6 = | **30.4** | |

### Run 6 — AWS us-east-1 — CLIP encode 7,434.1 ms scheduled

| t_start | t_end | span | ms | classification |
|---|---|---|---|---|
| 159,748.4 | 159,762.5 | tokenize | 14.1 | CONFIRMED |
| 159,774.0 | 161,726.9 | **hydration** | **1,952.9** | CONFIRMED |
| | | file→GPU | 1,850.5 @ 4.05 GB/s (AWS volume slower) | CONFIRMED |
| | | bind + sync | 93.8 | CONFIRMED |
| 161,860.9 | 167,194.8 | **forward** | **5,333.9** (thread CPU 2,040) | CONFIRMED (wall) |
| | | unet meta 161,733.2→164,753.8 (3,020.7); pipeline event @164,810.7 — overlaps forward 2,893–2,950 ms | | CONFIRMED coexistence |
| | | forward delay vs clean 1,729.5 = 3,604.4; overshoot vs overlap ≈ +711 ms | | SUPPORTED INFERENCE + UNKNOWN AWS residual |
| | | OTHER = 7,434.1 − 1,952.9 − 5,333.9 = | **147.2** | prepare 18.3 + wait + AWS scheduling, UNKNOWN split |

---

## 3. Reconciliation (required fields)

`CLIP_ENCODE_TOTAL_MS ≈ HYDRATION_MS + FORWARD_MS + OTHER_MS` (scheduled
span, remote events):

| run | CLIP_TOTAL | HYDRATION | FORWARD | OTHER | residual |
|---|---|---|---|---|---|
| Run 2 | 6,127.1 | 4,362.2 (71%) | 1,729.5 (28%) | 35.4 (0.6%) | 0.0 |
| Run 5 | 6,142.5 | 1,533.5 (25%) | 4,578.6 (75%) | 30.4 (0.5%) | 0.0 |
| Run 6 | 7,434.1 | 1,952.9 (26%) | 5,333.9 (72%) | 147.2 (2.0%) | 0.0 |
| **batch** | **19,703.7** | **7,848.6 (39.8%)** | **11,642.0 (59.1%)** | **213.0 (1.1%)** | |

Host-reported CLIP encode (6.151 / 6.173 / 7.465 s) tracks the remote
scheduled span within ~0.2–1.4% (node-wrapper delta, `loader_invoke`
≈ scheduled + 17–31 ms). Input counts: 8,044,986,048 checkpoint bytes
(7.49 GiB), 399 params all-meta, hydration re-reads the full file per
request; RSS delta 21–41 MB; `zero_copy_evidence` = 398/398 keys share
storage.

---

## 4. Telemetry defect (why "the markers are missing")

`_try_fast_hydrate` (wiring L640–716) emits `clip_fh_hydration_start`
**and** `clip_fh_hydration_end` in the same breath at the *end* of the
function (L710–715), 40–80 µs apart, with the decision emitted at entry.
Consequence:
- In the run-JSON event stream both markers share the completion timestamp
  (e.g. Run 2: start @658,199.70, end @658,199.74) — they cannot delimit a
  window by inspection.
- Console/host log pages (`v2_d11_request_*.log`) print aggregates only;
  the per-event stream stays embedded in `run_0.json`.
- Actionable corollary: hydration timing is *inferred* from
  `decision → end`; the internal file/bind split comes from metadata
  (`file_to_gpu_wall_ms`, `bind_wall_ms`, `gbps`, `cuda_delta_bytes`), which
  are correct.

Classification: CONFIRMED (both statements; source L640–716 + observed
timestamps).

---

## 5. Why bind*sync walked with the UNET lane (Run 2)

Bind = 398 `can_assign_sd`-forced `load_sd` assignments (CPU-side, ~µs each)
+ `_zero_copy_evidence_clip` (398 leaf checks) + `torch.cuda.synchronize()`
(L673–685). Uncontended total: 94–121 ms (Runs 5/6). Run 2's 2,889.7 ms
cannot be CPU (encode-thread CPU budget ≈1,790 ms incl. the 1,200 ms
forward → ≤~580 ms plausible for hydration-side Python), so it is device
wait. The only outstanding device work: the UNET fastsafetensors H2D lane
(meta 655.38→658.16, file→GPU 2,692 ms, pipeline event @658,227.9) plus
its caching-allocator churn — `cuda_delta_bytes = 20,355,218,432` (18.96
GiB ≈ CLIP 8.04 GiB + UNET ~12.3 GiB allocated *within the hydration
window*; Runs 5/6 show only 8.04 GiB). CONFIRMED: sync waits for the
concurrent copy; overlap 2,850/2,890 ms ≈ extra 2,790 ms (98% match).

## 6. Why forward walked with the UNET lane (Runs 5/6)

UNET meta starts 6–7 ms after hydration *ends* (802,264.6 / 161,733.2 vs
802,251.6 / 161,726.9), so hydration stays uncontended; the lane instead
overlaps the forward 2,980–3,059 / 2,863–2,950 ms (meta + H2D + pipeline
event). Forward wall 4,578.6 / 5,333.9 vs clean 1,729.5 (Run 2) → delay
2,849 / 3,604 ms. Run 5 delay matches overlap within 4%. Run 6 overshoots
~711 ms (AWS volume/H2D slower — file already 4.05 vs 5.10–5.34 GB/s — plus
allocator churn; `thread_cpu 2,040` vs 1,200 shows the forward thread also
spun more). The ~3 s lane itself is D8's root cause (GIL-starvation of the
meta `get_model`); its physical H2D additionally competes for the GPU.

## 7. Verdict sheet

| field | verdict | classification |
|---|---|---|
| DIRECT_GPU_HYDRATION_ACTUALLY_EXECUTED | YES — path A, `fastsafetensors_direct_gpu`, zero-copy 398/398, `fallback_count=0`, EXCLUDED_PLACEHOLDER pre-state | CONFIRMED |
| Telemetry "missing markers" | present in run-JSON events but co-emitted at completion (wiring L710–715); absent from host console pages | CONFIRMED |
| BIGGEST_CONFIRMED_CLIP_COST | batch: FORWARD 11.64 s (clean ~1.73 s/run + ~6.45 s lane-wait); per-run max: Run 2 bind+sync 2,889.7 (CONFIRMED wait), Run 5 4,578.6, Run 6 5,333.9 | CONFIRMED wall; delay attribution SUPPORTED INFERENCE |
| CONTENTION_SUPPORTED | YES — UNET lane overlaps the CLIP lane in all 3 runs; Run 2 wait ≈ overlap (98%), Run 5 delay ≈ overlap (96%) | CONFIRMED (Run 2) / SUPPORTED (Run 5) / SUPPORTED+UNKNOWN ~711 ms (Run 6) |
| INPUT_TYPES_WARM_CAUSAL | NOT PROVEN (D9 verdict; advisory daemon, 0.16–0.19 eff. cores; overlap windows coincide with, not cause of, lane waits) | SUPPORTED INFERENCE (non-causal) |
| UNET_CAUSAL | YES for Run 2 bind inflate (mechanism-level); YES-directionally for Run 5/6 forward inflate | PROVEN (Run 2) / SUPPORTED (Run 5/6) |
| OTHER_MS | 30–147 ms/run (tokenize 14–21, gpu-prepare/wait 9.5–18.3, node wrapper, scheduling; Run 6 split UNKNOWN) | CONFIRMED components; Run 6 tail UNKNOWN |

---

## 8. Generic CLIP-text-encoder-layer fix observations (report-only, no implementation)

Ranked by expected value at the generic ComfyUI layer; every idea is
HYPOTHESIS-level (not validated here), and none touches Qwen/Z-Image/GQA/
QKV specifics:

1. **De-collide the UNET H2D lane from the CLIP lane.** The D8 lane
   (3.0 s meta + 2.7–2.9 s file→GPU) is scheduled concurrently with the
   prefill encode; sequencing the UNET file copy after the prefill CLIP
   encode (or gating the warm daemon/folder-walk during the encode window)
   removes the 2.8–3.6 s CLIP-side wait with no CLIP change. Expected
   saving: 2.8–3.6 s on Runs 5/6; Run 2 bind wait (2.89 s) on GCP.
2. **Scope the bind sync per-stream.** `torch.cuda.synchronize()` (L684)
   waits device-wide; a stream-scoped sync after the assign-then-CUDA work
   would not absorb unrelated copy engines (saves the Run 2-class wait).
3. **Persist hydration across requests.** The 1.4–1.9 s file→GPU is a
   per-request re-read of 7.49 GiB by design (EXCLUDED placeholder).
   Holding the GPU-resident weights (warm/retain path) removes the re-read;
   the zero-copy design's currency is the retry-safe re-read, so this is a
   lifecycle change needing validation.
4. Per-run ceiling check after 1: forward ≈1.73 s (GCP) / ~2.4 s (AWS) +
   tokenize + ~35 ms → ~1.9 s / ~2.5 s cold CLIP encode.

## Final response

ZERO-SPEND. No commit. No deploy. No benchmark. Report-only; no code
changed. `V2_BATCH_D12_CLIP_CRITICAL_PATH_FORENSICS.md` written.