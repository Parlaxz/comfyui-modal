# V2 Batch C6 — UNET Read/H2D Probe Report (I-1 + I-2)

Date: 2026-08-14
Mode: measurement-only. I-1 per-tensor materialization series + I-2 wave-split H2D replay probe.
Flag: `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE=probe` (default/unset = byte-for-byte production; value `1` reserved and explicitly rejected as unsupported).
No source-behavior change in production: probe-off path is byte-identical (verified by tests + the probe-off baseline run).

---

## Valid probe run

Run dir: `comfymodal-data/benchmarks/runs/v2_2026-08-14_22-24-46/` (run_0.json)
Request: `v2-benchmark-0-...` | Instance: `80582d1c9efd423591679ad68e779139` | Fresh: YES
Deployment: `stable-modal-comfy-v2-c6probe-shadow`, deployment_combined_hash `90407dcde8cb62d2`, comfyui_core_match=1
Platform: GCP/us-east4, RTX PRO 6000 Blackwell, CUDA 13.0, linux, `comfy.utils.DISABLE_MMAP=False`
Lifecycle: exactly one UNET read → bind → H2D lifecycle (`lifecycle_count=1`, one `normal_loader_ready`)

Probe events fired: `unet_read_h2d_pipeline_probe` (I-1) = 1, `unet_read_h2d_wave_probe` (I-2) = 1,
`unet_tensor_materialize_aggregated` = 1 (453 tensors / 12,309,817,472 B — reconciles).

## I-1 — Read (producer) measurements

| Metric | Value |
|---|---|
| tensors | 453 |
| total bytes | 12,309,817,472 |
| read wall (first→last tensor) | 1535.19 ms |
| read span (read_start→read_end, incl. open/parse head) | 1623.7 ms |
| 25% bytes at | 541.5 ms (35.3% of wall) |
| 50% bytes at | 839.0 ms (54.7% of wall) |
| 75% bytes at | 1184.2 ms (77.1% of wall) |
| 100% bytes at | 1535.2 ms |
| bytes-linearity | 50% bytes at 54.7% of time — read is roughly bytes-proportional, slightly front-loaded |
| storage behavior | 453/453 `is_view=true` (base non-None), `storage_offset=0` — safetensors returns mapping-backed views, not independent copies |
| mmap state | `comfy.utils.DISABLE_MMAP = False` (mmap-backed views active; no copy-out in load_torch_file) |

Largest 10 tensors by materialization wall (note: NOT byte-proportional — small tensors dominate):
1. `cap_embedder.1.bias` — 120.1 ms (7,680 B)
2. `context_refiner.0.attention.q_norm.weight` — 91.0 ms (256 B)
3. `noise_refiner.1.attention.q_norm.weight` — 50.2 ms (256 B)
4. `cap_embedder.1.weight` — 26.6 ms (19,660,800 B)
5. `layers.21.ffn_norm1.weight` — 19.0 ms (7,680 B)
6. `cap_embedder.0.weight` — 18.6 ms (5,120 B)
7. `layers.21.feed_forward.w1.weight` — 18.3 ms (78,643,200 B)
8. `layers.21.attention_norm1.weight` — 17.0 ms (7,680 B)
9. `layers.21.attention_norm2.weight` — 15.4 ms (7,680 B)
10. `layers.22.feed_forward.w2.weight` — 15.3 ms (78,643,200 B)

Read-wave conclusion: **bursty at the head** (first 4 tensors ≈ 305 ms of the 1535 ms wall, dominated by
norm/bias allocations and page-in), then roughly byte-proportional for the bulk. Largest byte tensors
(78 MB) materialize in ~15-18 ms each (~4.4 GB/s effective page-in rate); the read is not smooth at
tensor granularity — a few dozen small tensors carry disproportionate wall time.

## I-2 — H2D (consumer) measurements

| Metric | Value |
|---|---|
| waves | 8 (byte-bounded, greedy partition) |
| tensors | 454 (453 params + 1 buffer) |
| total bytes | 12,309,821,472 |
| to_wall | 2467.892 ms |
| to_device (CUDA events, synchronized) | 2467.758 ms |
| Σ wave device | 2406.493 ms |
| inter-wave host gap | 62.473 ms (GPU idle between waves; 2.6% overhead from wave splitting) |
| anti-overlap invariant | wall ≈ device (Δ 0.134 ms) — pages already resident before copy; no page-in during H2D |

Per wave (device_ms, cumulative device):
| wave | tensors | bytes | device ms | cum device |
|---|---|---|---|---|
| 0 | 60 | 1,541,205,504 | 330.594 | 330.6 |
| 1 | 56 | 1,555,417,600 | 281.551 | 612.1 |
| 2 | 53 | 1,525,925,888 | 258.551 | 870.7 |
| 3 | 58 | 1,533,820,928 | 431.090 | 1301.8 |
| 4 | 55 | 1,565,278,208 | 265.914 | 1567.7 |
| 5 | 55 | 1,525,926,400 | 306.161 | 1873.9 |
| 6 | 53 | 1,525,925,888 | 275.153 | 2149.1 |
| 7 | 64 | 1,536,321,056 | 257.479 | 2406.5 |

H2D cumulative: 25% @612.1 ms, 50% @1301.8 ms, 75% @1873.9 ms, 100% @2406.5 ms (device).
Effective rate: 12,309,821,472 B / 2467.8 ms ≈ **4.99 GB/s** device (waterfall row: "Synchronized H2D (4.9 GB/s)").
Wave behavior: uniform byte sizes (1.53-1.57 GB each), stable per-wave times (258-431 ms); the 431 ms
wave 3 outlier suggests one slow copy or transient bandwidth dip — otherwise the consumer is smooth.

## Serial timeline (measured, current order)

```
read_start ── 1623.7 ms ──► read_end ── 513.7 ms ──► to_start ── 2467.9 ms ──► to_end
```
- read_start→read_end: 1623.7 ms (materialize 1535.2 + open/parse head ~88.5 ms)
- read_end→to_start: 513.7 ms = get_model 383.4 + ctor 2.2 + bind 109.6 + ~18.5 misc — **the construction/bind barrier**
- to_start→to_end: 2467.9 ms
- **serial_current = 4605.3 ms** (read_start → H2D end)

## Future-overlap simulation (measured producer/consumer, NO overlap implemented)

Producer availability (read): 25% @541.5, 50% @839.0, 75% @1184.2, 100% @1535.2 ms.
Consumer (wave device cumulative): 12.5% @330.6, 25% @612.1, 37.5% @870.7, 50% @1301.8, 62.5% @1567.7,
75% @1873.9, 87.5% @2149.1, 100% @2406.5 ms.

Ideal pipeline (wave i starts at max(producer_avail(boundary_i), end_{i-1})):
- w0: s=270, e=600.6 | w1: s=600.6, e=882.2 | w2: s=882.2, e=1140.8 | w3: s=1140.8, e=1571.9
- w4: s=1571.9, e=1837.8 | w5: s=1837.8, e=2144.0 | w6: s=2144.0, e=2419.2 | w7: s=2419.2, e=2676.7

- **ideal_pipeline ≈ 2676.7 ms** (from read start)
- **theoretical perfect-overlap ceiling = 4605.3 − 2676.7 ≈ 1928.6 ms** (~42% of the read→H2D chain)
- **conservative realistic saving ≈ 0.9–1.7 s** (discounting per-tensor enqueue overhead, residual
  construction serialization ~150–250 ms, and the 62 ms measured wave-gap; audit-style 50% discount
  of the theoretical ceiling gives ~0.95 s)
- **floor: 0 ms** without the I-3 refactor — with config-from-sd the bind requires the complete state
  dict (measured: H2D waits 513.7 ms after read_end), so no overlap is possible in the current order.
  The measured producer/consumer timelines only become exploitable after the header-config fork.

## Anti-regression evidence (probe ON)

- Output SHA identical to probe-off baseline run: `sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` (both runs)
- Fresh: YES (identity + host_telemetry)
- Exactly one UNET lifecycle: `lifecycle_count=1`, one `normal_loader_ready`, one `unet_fast_disk_complete`
- Final GPU-ready semantics preserved: `normal_loader_ready` state patcher=ModelPatcher, load=cuda:0,
  offload=cuda:0, current=cuda:0, first_parameter_device=cuda:0, dtype=bfloat16
- Same model identity/param count/bytes: 454 wave items vs 453 read tensors (454 = 453 params + 1 buffer; 4,000 B delta reconciles to the buffer)
- No fallback introduced: `unet_fast_disk_complete decision=complete reason=ok`, wave probe used (8 waves), no `waves fallback=` line
- Anti-overlap invariant preserved: `to_wall 2467.892 ≈ to_device 2467.758` (Δ 0.134 ms); no copy began before read_end (to_start is 513.7 ms after read_end)
- Pinned staging production setting: **OFF** (`COMFYMODAL_V2_UNET_PINNED_STAGING` unset → `unet_pinned_staging_enabled()=False`); probe ran on the plain A path; the single-buffer staging arm was NOT active and did not influence these numbers
- Waterfall: local reconciliation OK (3.9 ms, console STATUS OK); host rebuild reconciliation FAILED
  (−781.9 ms) — **pre-existing for this run vehicle with diagnostics on** (the probe-off baseline run
  21-21 also fails at −675.4 ms; not probe-induced; host rebuild semantics documented in
  V2_BATCH_C3_WATERFALL_CONTRACT_REPORT.md)

## Hazards / observations for I-3 design

1. **Construction barrier is the real gate** (get_model 383.4 + bind 109.6 ms serial after read_end); the header-config fork is mandatory before any overlap is exploitable — unchanged from the feasibility audit.
2. **Read burstiness**: ~305 ms of the 1535 ms read wall is spent on the first 4 tensors (small norm/bias tensors); per-tensor scheduling must not assume smooth byte-proportional production.
3. **mmap-backed views confirmed**: 453/453 `is_view=true`, `storage_offset=0`, `DISABLE_MMAP=False` — a pipelined transfer must keep the mmap/file mapping alive until every copy completes (same exposure as today, but now per-tensor).
4. Wave-split measurement perturbation: 62.5 ms inter-wave host gap (2.6%) — bounded, documented, device-total reconciliation (2406.5 vs 2467.8) healthy.
5. `h2d_copy_count/h2d_total_bytes` decomposition fields read 0 on the wave path (params already on CUDA when the post-hoc decomposition scans pre-transfer refs) — the wave probe metadata is authoritative for the probe runs; baseline decomposition fields are unchanged when the flag is off.

## Decision gate

Measured read/H2D timelines show a **meaningful overlap opportunity** (theoretical ceiling ≈ 1.93 s,
conservative realistic ≈ 0.9–1.7 s — well above the ≥ 300 ms threshold) and **no architectural
contradiction** in the measured producer/consumer behavior (smooth consumer, hideable producer, stable
wave granularity, preserved identity/SHA). The only blocker is the known, bounded construction-barrier
refactor (header-config + incremental bind), which is exactly the I-3 scope.

### PROCEED TO I-3
- theoretical perfect-overlap ceiling ≈ 1.93 s (42% of the read→H2D chain; ~13% of total wall)
- conservative realistic saving ≈ 0.9–1.7 s (measured), vs the earlier audit estimate of 0.5–1.0 s — measurements are at the favorable end of the audit range
- I-3 must NOT be implemented in this task; this is the decision request only

## Uncertainty (retained)

- Savings are simulated from the measured producer/consumer timelines, not from an implemented overlap; the construction-barrier refactor cost is estimated (150–250 ms residual), not measured.
- The 431 ms wave-3 outlier may indicate transient bandwidth variance; a single-run probe cannot distinguish steady-state from noise.
- Host-rebuild waterfall reconciliation FAILED is pre-existing for this vehicle (baseline-identical), but it means the strict host-side waterfall contract check did not pass on any diagnostic run today; local reconciliation is the authoritative in-container accounting and is OK.
- Probe evidence comes from exactly one true-cold run (standing rule: stop after the first valid run).

---

## You asked for:
- Implement and validate measurement-only probes I-1 (per-tensor read series) and I-2 (wave-split H2D replay) behind `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE=probe`, one deploy + one cold run, then analyze and classify.

## You should now manually check:
- The decision gate (PROCEED TO I-3) — do not implement I-3 without a new explicit authorization; the stop-condition 6 from `V2_UNET_READ_H2D_OVERLAP_RESEARCH.md` still gates any interleaved pipeline work.
- The wave-3 H2D outlier (431 ms) — worth confirming on a second diagnostic run if I-3 is authorized (this probe run is complete; no cohort was collected).
- Probe-off byte-identity: with `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE` unset the runtime is byte-for-byte production (no probe events, no wave path) — verified by tests and the 21-21 baseline run.
