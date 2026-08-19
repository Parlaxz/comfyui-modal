# V2 Batch D14 — Post-Sampling Tail Forensics

**Date:** 2026-08-16
**Scope:** Quantify the post-sampling output tail (~1.5-1.8 s) on Batch D11 deployment `2305b0b3bbdf3fbe…` (`fingerprint f504e296c398bdcb2c4c07e2`) and determine whether VAE activation can safely start earlier than the `sampling_end` boundary without changing image bytes, VAE dtype, decode, PNG settings, or workflow semantics.
**Mode:** Read-only forensics (NORMAL agent). No code changes, no deploy, no Modal requests, no commit.
**Ground truth:** `full_trace.events` (remote process, monotonic ns) from the three valid D11 samples:
- Run 2: `comfymodal-data\benchmarks\runs\v2_2026-08-16_18-26-58\run_001_sample.json` (`v2-benchmark-0-8ce2b1d3ce62`, GCP us-east4)
- Run 5: `comfymodal-data\benchmarks\runs\v2_2026-08-16_18-29-25\run_001_sample.json` (`v2-benchmark-0-f397baff019f`, GCP us-east4)
- Run 6: `comfymodal-data\benchmarks\runs\v2_2026-08-16_18-30-19\run_001_sample.json` (`v2-benchmark-0-54a4ff16625d`, AWS us-east-1)

---

## 1. Headline numbers (times are ms, measured from `sampling_end` unless noted)

| Metric | Run 2 | Run 5 | Run 6 | Mean |
|---|---|---|---|---|
| Sampling duration (`sampling_start→sampling_end`, reconciliation) | 4758.0 | 4703.9 | 4937.0 | 4800.0 |
| **Post-sampling tail** (`sampling_end → remote_result_emit`) | **1546.3** | **1542.8** | **1804.1** | **1631.0** |
| VAE activation schedule cost (sampling_end → scheduled) | 0.30 | 0.33 | 0.40 | 0.34 |
| VAE pre-copy start (scheduled → `vae_early_activation_load_start`) | 3.4 | 2.1 | 3.7 | 3.1 |
| VAE load wall (`load_start → terminal`, reconciliation `load_wall_ms`) | 936.8 / 937.3 | 950.5 / 950.5 | 1113.5 / 1113.5 | 1000.3 |
| **VAE exposed** (join wait: decode dispatch → VAE ready, reconciliation `join_wait_ms`) | **28.4** | **31.1** | **66.1** | **41.9** |
| Decode node dispatch (`vae_decode_start` #1, +Δ from sampling_end) | 912.1 | 922.0 | 1051.6 | 961.9 |
| Decode wall (`vae_decode_start` #2 → `vae_decode_end`) | 335.8 | 340.0 | 373.5 | 349.8 |
| Output encode (`output_encode_start → end`; PNG-dominated) | 176.5 | 156.7 | 188.0 | 173.7 |
| Output chain + persist + collect (`collect_start → collect_end`) | 8.0 | 7.0 | 9.4 | 8.1 |
| Executor return + close workers (`graph_execution_end → close_workers_end`) | 0.2 | 0.2 | 0.2 | 0.2 |
| **Remote result handoff** (`close_workers_end → remote_result_emit`) | 85.1 | 85.9 | 115.5 | 95.5 |
| Sum of parts (Run 2) | | | | ≈1554 (measured tail 1546) ✓ |

Run 2 PNG line cross-check: `png_encode_ms=176.453` matches the output-encode window (176.5 ms) exactly; bytes/sha identical across the batch (no byte drift).

---

## 2. The anatomy of the tail — three windows

### 2a. `sampling_end → VAE ready` (~940-1118 ms): NOT a VAE-load stall — a CUDA memory-settle + CLIP cold reload gate

Every run shows the identical sequence at `sampling_end`:

```
+0.0   sampling_end
+0.1..0.4   sampler_lane_released / vae_early_activation_scheduled / preload_submitted
+0.7..0.9   vae_prepare_start / preload_worker_started
+2.4..4.1   vae_early_activation_load_start          <- VAE pre-copy begins (side path)
+3.8..7.5   clip_cold_load_models_gpu_start          <- deliberate CLIP cold reload also starts here
+4.4..8.3   gpu_lane_wait / gpu_commit_start
[~885-1034 ms of silence]                            <- CUDA context settle
+890..1040 clip_cold_soft_empty_cache (x2), clip_cold_free_memory,
           clip_cold_patcher_partial_load, clip_state_checkpoint
+912..1052 vae_decode_start #1 (executor dispatches VAEDecode)   <- gate ends
+940..1118 vae_early_activation_terminal / consumed  <- VAE ready (AFTER the gate!)
```

Key findings:

1. **The decode gate is the settle, not the VAE.** The executor's dispatch of VAEDecode (+912 / +922 / +1052) lands immediately after the CLIP-cold `soft_empty_cache/free_memory/patcher/state_checkpoint` tail, and is gated by a ~885-1034 ms silent window that begins right after `gpu_commit_start`. The VAE terminal (+940 / +953 / +1118) finishes *after* the gate in all three runs.
2. **VAE load is already almost fully overlapped.** `load_wall_ms` (937/950/1113) runs parallel to the settle window; the only VAE latency actually seen by the critical path is the reconciliation `join_wait_ms` (28.4 / 31.1 / 66.1) — the join in `VAEDecode._consume_vae_decode` (model_preload.py `_make_wrapper`, VAEDecode branch) after dispatch.
3. **CLIP cold reload is scheduled deliberately at `sampling_end`** (deferred to keep VRAM free for the sampler), and its commit contends with the arena released by the sampler. The two `clip_cold_soft_empty_cache` calls bracket 1.8-4.1 ms, so the ~885-1034 ms silence is the *settle before reclamation/patching* (fragmented-arena drain / allocator-commit blocking), not the cache call itself.

**Implication:** the waterfall label "post_sampling_transition / VAE load ~870-916 ms" misattributes the gate to VAE loading. VAE loading is *not* the binding constraint — the arena settle + CLIP cold reload is, and it is ~2/3 of the whole tail.

### 2b. `VAE ready → decode done` (~336-374 ms): pure decode wall

`vae_decode_start #2 → vae_decode_end`: 335.8 / 340.0 / 373.5 (mean 349.8). No stall inside (layout re-check + contiguous decode of 1088x1920 bf16 latents). Irreducible with current dtype/resolution.

### 2c. `decode done → result emit` (~262-303 ms): encode + descriptor + handoff

| Piece | Run 2 | Run 5 | Run 6 | Mean |
|---|---|---|---|---|
| Output encode (PNG compress_level=1 + chain) | 178.2 | 158.4 | 190.0 | 175.5 |
| Output collect / descriptor (`output_persist_*`, `output_chain_*`) | 8.0 | 7.0 | 9.4 | 8.1 |
| Executor return + `remote_result_emit` body (close_workers_end → emit) | 85.1 | 85.9 | 115.5 | 95.5 |

`remote_result_emit` (85-116 ms) is the serialization + Modal result-API handoff after `close_workers_end`; the executor-return sliver is ≈0.2 ms.

---

## 3. Can VAE activation start earlier? (candidate triggers)

| Trigger candidate | Feasibility today | Safety profile | Expected saving |
|---|---|---|---|
| `sampling_end` (current, mode `sampling_end`) | implemented | lane-bound; worker mutates only after sampler releases lane | — (baseline) |
| `sampling_first_step` (first completed step) | **already implemented** at model_preload.py:20426 (`schedule_vae_early_activation_at_first_step`), experimental | bounded transfer-only pre-copy on side stream (no lane, no mutation during sampling); narrow lane-bound `.data` rebind only after `sampling_end`; idempotent; falls back to graph loader on failure | removes `join_wait_ms` ≈ **42 ms mean**; decouples VAE load from the settle |
| Last sampler step (step N) | hook would reuse the existing step-callback machinery (same one-shot watchdog callback family); no hook today | identical safety class to first-step (transfer-only, rebind after lane release); trigger ≈ one step (~235 ms) before `sampling_end` | ≈42 ms (same as first-step; no additional gate is opened) |
| Last UNET forward completion | new hook needed inside sampler wrapper | same class; trigger ≈ tens of ms before `sampling_end` | ≈42 ms minus nothing measurable |
| Sufficiently late sampling progress (e.g., 95%) | new hook | same class | ≈42 ms |

**Bottom line on triggers:** every earlier trigger collapses to the *same* saving — the 42 ms mean join — because decode dispatch is gated by the arena settle + CLIP cold reload, which is independent of VAE readiness. **Starting VAE earlier does NOT open the decode gate.** The decisive lever is the settle itself (2a).

---

## 4. What it takes to reach ≤1.0 s

Post-sampling budget today (mean 1631 ms):
- settle + CLIP cold reload gate: **~962 ms** (912-1052 to decode dispatch) ← the attack surface
- decode: ~350 ms (irreducible at current dtype/resolution)
- encode + chain + persist + collect: ~184 ms
- emit body: ~96 ms
- join: ~42 ms (removable via `sampling_first_step`)

Path to ≤1.0 s requires (in order of expected value):
1. **Overlap the CLIP cold GPU reload + arena settle with late sampling** (or pre-commit CLIP+VAE working set before sampling / empty_cache discipline). This is the only move that can buy ~400-900 ms; it has a VRAM-vs-sampler tradeoff and is a *strategy change*, not a trigger change (out of D14 scope — needs its own measurement plan).
2. `sampling_first_step` VAE activation (code exists) — removes the join (~42 ms) at low risk.
3. Emit-body overlap (serialize result during executor return) — ~30-60 ms, mechanical.

If (1) fully hides the settle and (2)+(3) land: ~350+184+96-60+~50 ≈ **0.62-0.75 s** post-sampling. If settle only halves: ~1.1-1.2 s.

---

## 5. Metric lines

```
CURRENT_POST_SAMPLING_MS = 1631.0 (1542.8 / 1546.3 / 1804.1, sampling_end -> remote_result_emit)
VAE_LOAD_MS = 1000.3 (936.8 / 950.5 / 1113.5, load_start -> terminal; reconciles with load_wall_ms)
VAE_EXPOSED_MS = 41.9 (28.4 / 31.1 / 66.1, join_wait_ms at VAEDecode demand join)
DECODE_MS = 349.8 (335.8 / 340.0 / 373.5, vae_decode_start #2 -> vae_decode_end)
PNG_MS = 173.7 (176.5 / 156.7 / 188.0, output_encode window; run2 log png_encode_ms=176.453 cross-checked)
HANDOFF_MS = 95.5 (85.1 / 85.9 / 115.5, close_workers_end -> remote_result_emit)
SAFE_EARLIEST_VAE_TRIGGER = sampling_first_step (implemented, experimental; transfer-only side-stream pre-copy,
  lane-bound .data rebind strictly after sampler lane release; idempotent; graph-loader fallback)
  -- last-step / last-UNET-forward trivially safe but add nothing beyond first-step
POTENTIALLY_HIDEABLE_VAE_MS = 42 (join_wait_ms only; VAE load is already overlapped with the arena-settle gate;
  VAE load itself is NOT the decode gate -- the CLIP-cold/arena settle is, ~962 ms mean)
IRREDUCIBLE_POST_SAMPLING_MS = ~962 (settle+CLIP-cold gate, current architecture) + decode 350 + encode 184 + emit 96
  minus overlap opportunities -> ~1.59 s at current architecture; ~0.62-0.75 s only after settle overlap (strategy change)
BEST_NEXT_FIX = overlap CLIP-cold GPU reload + arena settle with late sampling (pre-commit CLIP+VAE working set /
  empty_cache discipline) -- the only lever that reaches <=1.0 s; secondary: enable sampling_first_step (join -42 ms),
  overlap emit body with executor return (-30-60 ms)
EXPECTED_SAVING_MS = ~42 (trigger change alone) ; ~490-1000 (trigger + settle overlap + emit overlap, best case)
CONFIDENCE = high on event-level numbers (triple run, reconciliation cross-checked); medium on the settle-gate
  mechanism attribution (main-thread stall vs allocator contention indistinguishable from trace; needs one
  instrumented run) and on settle-overlap feasibility (untested VRAM tradeoff)
FILES_CHANGED = report only (V2_BATCH_D14_POST_SAMPLING_FORENSICS.md)
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
STOP.
```