# V2 Batch C6 — Pinned-Ring Implementation Report (ZImage, default-OFF)

Date: 2026-08-15
Flag: `COMFYMODAL_V2_UNET_PINNED_RING=1` (default OFF; invalid values fail closed with a named reason).
Scope: ZImage-only family allow-list. No ComfyUI core edits. No commit.

## Implementation map

| Component | Location | Responsibility |
|---|---|---|
| `_ring_flag_value` / `_ring_pipeline_enabled` | model_preload.py:1263/1273 | env gate; on/off/invalid fail-closed (invalid prints once, never enables) |
| `_RING_WAVE_TARGET_BYTES` / `_RING_MAX_WAVE_BYTES` / `_RING_DEPTH` | 1257-1259 | 64 MiB target / 128 MiB cap / fixed depth 2 (not tunable) |
| `_ring_derive_config` | 1285 | header-only ZImage config (prefix strip, allow_fp16 value probe, extended-fp16 insertion, set_inference_dtype); returns effective prefix ("" when the `"model."` heuristic matches nothing) |
| `_ring_resolve_unet_path` | 1374 | `folder_paths.get_full_path_or_raise` → `get_full_path` → lane-trace `resolved_path` fallback |
| `_ring_eligible` | ~1397 | conditions 1-10 pre-construction (HIGH_VRAM, torch future, quant/fp8/channels_last evidence, dtype conversion, pinned 1 MiB probe, CUDA) |
| `_ring_wave_build` | 1452 | byte-oriented packing, own-wave for >target tensors, cap, dtype-uniform, order-preserving |
| `_ring_run_waves` | 1541 | two flat typed pinned slots, per-wave event pairs, slot reuse-waits, incremental `param.data`/`buf.data` binding; `(None, "<stage>:<detail>")` failure contract |
| `_ring_try_pipeline` | ~1697 | S1-S10 orchestrator; every failure → named reason + cleanup + None (fresh `_invoke_original`) |
| `_load_unet` branch | ~13185 | flag → `_ring_try_pipeline`; `(patcher,)` flows through the byte-identical tail (normal_loader_ready, probe registration, future); else `_invoke_original` |
| `_runtime_env` passthrough | modal_app.py:3134 | `COMFYMODAL_V2_UNET_PINNED_RING` baked like other V2 flags |

## Eligibility behavior

All pre-construction gates must pass (flag on, ZImage family, header parse, value probe resolved, HIGH_VRAM, plain-patchable, no quant/fp8/channels_last, no torch future, default dtype request, uniform dtype, supported dtype, CUDA, pinned 1 MiB probe). Post-construction gates: config parity (family + derived fields), key-set ⊆ (params ∪ buffers) with `sd_unmapped_keys` recorded, transform INDEPENDENT (identity), uniform destination dtype. Any failure → `status=ineligible reason=...` → existing loader. Ineligibility is not an error (telemetry distinguishes ineligible vs fallback).

## Fallback behavior

ANY failure after pipeline start → `status=fallback reason=stage:<detail>` (e.g. `stage:ring_run:read:KeyError`, `stage:key_param_mismatch` with `sd_unmapped_keys`), cleanup (pinned/dests freed, empty_cache, model/patcher locals dropped), then `_invoke_original` FRESH exactly once. No partial pipeline object is ever published. Fallback count is visible in telemetry. Verified across all three diagnostic deploys (path_unresolved, key_param_mismatch, ring_run) — each fell back cleanly with byte-identical output.

## Ring state machine (as implemented and validated)

```
wave w (slot s = w % 2):
  if ev_pending[s]: ev_pending[s].synchronize()   # slot reuse wait (only this slot)
  read keys (get_tensor, keep refs)               # page-in lands here (views)
  ensure slot capacity (grow-to-largest, realloc replaces)
  stage: pin_slot[s][off:off+n].view(shape).copy_(t, non_blocking=False)
  ev_start.record()
  per key: dest = empty_like(cuda); dest.copy_(pin_view, non_blocking=True); param.data = dest
  ev_end.record(); ev_pending[s] = ev_end
after all waves: model.to(target)  (8.3 ms — no duplicate transfer; 0 sd-mapped cpu params)
exactly ONE torch.cuda.synchronize()
publish (normal_loader_ready → future → graph → sampler unchanged)
```

## Local test results

`tests/test_c6_read_h2d_probe.py`: **135 passed** (81 prior probe tests + 54 ring tests: flag semantics, eligibility ×16, derive/config, wave packing, ring mechanics with fake torch, prefix/submodule key-map, subset gate, failure injection ×12 stages, telemetry, integration). `python -m py_compile` OK. Regression set: **269 passed / 10 pre-existing failures** (9× TestBenchmarkPrefixInstrumentation + 1× png-level order-flake) — unchanged. Batch A/B/C acceptance, fast-disk, TWO-LANE/prefill, critical-path suites all green.

## Deploy/run inventory (implementation phase)

| # | deploy hash | run dir | outcome |
|---|---|---|---|
| 1 | 09c0c5c2 | v2_2026-08-15_01-56-21 | fallback `stage:path_unresolved` (wrong module name `comfy.folder_paths`) → fixed resolver |
| 2 | 58c0b894 | v2_2026-08-15_02-10-43 | fallback `stage:key_param_mismatch` (prefixed vs unprefixed keys) → fixed submodule key-map + strict=False subset gate |
| 3 | 18663165 | v2_2026-08-15_02-39-41 | fallback `stage:ring_run` (heuristic `"model."` prefix leaked into get_tensor keys) → fixed effective prefix + stage-detail contract |
| 4 | 31b84e0a | **v2_2026-08-15_02-59-51** | **VALID: status=ok, fallback_count=0, pipeline replaced fast-disk entirely** |

Each diagnostic run fell back cleanly with byte-identical output (SHA `20b10e1f...e5260`) — the fail-closed contract worked end-to-end before the pipeline ever succeeded. Standing rule honored: no cohort; the first correct validation run (02-59-51) is the data run.

## Valid-run pipeline telemetry (02-59-51)

| Metric | Value |
|---|---|
| eligibility / family | ok / ZImage |
| fallback_count | **0** |
| header_config_wall | 86.28 ms |
| value_probe_wall | 33.37 ms |
| get_model_wall | **2340.92 ms** (fast-disk reference on similar host: 348.7 ms) |
| param/tensor count | 453 / 453 |
| total bytes | 12,309,817,472 |
| waves | 205 (mean 60.0 MB, max 88.5 MB; target 64 MiB, cap 128 MiB) |
| pinned alloc | 216,289,792 B (~206 MiB) |
| read/page-in wall | 180.99 ms (get_tensor; page-in lands inside staging) |
| CPU staging wall | **3430.31 ms** (≈3.6 GB/s, page-in-bound) |
| H2D device wall | 940.45 ms |
| H2D host-issue wall | 728.38 ms (~3.6 ms/wave host enqueue) |
| reuse wait total / max | 29.90 ms / 2.80 ms |
| final model.to wall | 8.31 ms (no duplicate transfer) |
| final sync wall | 0.03 ms |
| **total pipeline wall** | **9027.31 ms** |
| serial-equivalent | 6901.02 ms |
| **hidden overlap** | **0.0 ms** |

## Output identity / correctness

- Output SHA: `sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` — identical to the probe-off baseline (5th consecutive byte-identical generation).
- Fresh YES, C1 identity healthy (deploy hash 31b84e0a, comfyui_core_match=1), B1 exact-match observed, local waterfall reconciliation −0.24 ms OK.
- Final GPU state: load/offload/first-parameter = cuda:0, dtype bfloat16.
- Exactly one UNET lifecycle; `unet_fast_disk_*` events absent (pipeline replaced the fast-disk path on the valid run).
- TWO-LANE / MutationLane semantics unchanged (pipeline in the UNET prep worker, same single-flight future, sampler gates untouched).

## Measured performance — decision-relevant

- **The ring produced zero net hidden overlap on the valid run** (`hidden_overlap_ms = 0.0`): the pipeline wall (9027 ms) EXCEEDS its own serial-equivalent decomposition (6901 ms) by ~2.1 s. The DMA (940 ms) trivially hid under staging, but the host-bound stages (get_model 2341 + staging 3430 + issue 728 + header/probe 120) dominate the wall.
- Compared with the fast-disk chain on a similar slow host (read ~2.2 s + get_model 349 + bind 348 + H2D 4731 ≈ 7.6 s): the pipeline (9.0 s) is **slower**.
- Cost drivers (all measured):
  1. **Construction-before-read** pays a fresh-memory/COW cost (~2.0-2.3 s get_model vs 0.35-0.58 s post-read in the fast-disk path) — the design assumed construction moves off the critical path, but on snapshot-restored containers the first large write-heavy allocation is expensive and now happens before page-in warms the allocator.
  2. **Per-wave host overhead**: 205 waves × ~3.6 ms issue + ~16.7 ms staging per wave = ~2 s of host bookkeeping the probe (12 chunks, resident pages) did not expose.
  3. **Staging is page-in-bound** (3.6 GB/s vs the ring probe's 50-100 GB/s on resident pages) — the production pipeline pays page-in inside the pinned copy, so it does not beat the old read rate while adding the copy.
- Host note: the valid run's scheduling was 67-117 s vs 26-33 s healthy (heavily contended host); absolute numbers are host-degraded, but the internal serial-equivalent comparison (9027 > 6901) is host-independent and already fails the threshold.

## Decision

### STOP — measured benefit below threshold

- **Correctness: PASS** — byte-identical output, zero fallbacks on the valid run, all gates held, fail-closed contract demonstrated across four deploys.
- **Performance: BELOW THRESHOLD** — valid-run conservative measured benefit is **negative** (pipeline wall 9027 ms > serial-equivalent 6901 ms > fast-disk reference chain ~7.6 s on a comparable host). This triggers the explicit stop condition "valid-run conservative measured benefit < 300 ms".
- The design's predicted 1.4-2.2 s saving is **not confirmed**; the ring's CPU-stage/H2D overlap did not materialize net of host costs.
- **Recommended production default: OFF** (as pre-decided; the evidence does not support enabling).
- No further runs under the standing rule (first correct validation = the data run; no cohort).
- Out of scope, not authorized: a bounded refactor to kill the per-wave host overhead (flat GPU wave buffer + bulk enqueue) and to address the construction-before-read fresh-memory cost would require a new decision and re-validation.

## Remaining compatibility limitations

- ZImage-only allow-list; Lumina2 requires its own parity validation before inclusion.
- The `"model."` heuristic prefix from `unet_prefix_from_state_dict` must be kept effective-prefix-aware (fixed; regression-tested).
- Production telemetry is lean (one event, no per-tensor series); probe-mode I-1/I-2/I-3 instrumentation remains behind `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE=probe`.
- The ring code paths are inert with the flag unset/invalid (verified by tests; no behavior change with both flags off).

---

## You asked for:
- Implement and remotely validate the default-OFF ZImage pinned-ring UNET loader (flag `COMFYMODAL_V2_UNET_PINNED_RING=1`), with local tests, one deploy + one true-cold validation, evidence, and a decision.

## You should now manually check:
- **Decision: STOP (performance)** — the pipeline is correct (byte-identical output, zero fallbacks) but its valid-run wall (9.0 s) exceeds both its own serial-equivalent (6.9 s) and the fast-disk reference on a comparable host (~7.6 s). Do not default the flag on; do not broaden scope without a new decision.
- If a bounded-refactor decision is ever made, the measured cost drivers to attack are: (1) construction-before-read fresh-memory/COW (~2 s), (2) ~2 s per-wave host overhead (205 waves), (3) page-in-bound staging (3.6 GB/s) — and the overlap must show `hidden_overlap_ms > 0` on a re-validation run.
- Confirm probe-off/flag-off byte-identity on production (no ring events, no pinned allocations, no header work with the flag unset — verified by tests + baseline runs).
- Output SHA `20b10e1f...e5260` identical across all five generations — the instrumentation and the pipeline never altered the authoritative model.
- Report file: `V2_BATCH_C6_PINNED_RING_IMPLEMENTATION_REPORT.md` (repo root). No commit was made.
