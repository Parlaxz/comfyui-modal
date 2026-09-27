# V2 Batch C6 — I-3 Config Parity + Actual mmap/H2D Overlap Gate Report

Date: 2026-08-14
Mode: measurement-only (probe mode `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE=probe`; default path byte-identical).
No interleaved pipeline implemented; no pinned staging introduced; no mmap/DISABLE_MMAP changes; no commit.

## Valid probe run

Run dir: `comfymodal-data/benchmarks/runs/v2_2026-08-14_23-26-59/` (run_0.json)
Deployment: `stable-modal-comfy-v2-c6probe-shadow`, deployment_combined_hash `d99aaa7fc0dd2e75`, comfyui_core_match=1
Fresh: YES | B1 exact-match skip: observed | Local waterfall reconciliation 3.2 ms (host rebuild FAILED — pre-existing vehicle property, baseline-identical)
Output SHA: `sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` — **identical to the probe-off baseline**
Lifecycle: exactly one authoritative UNET load (one `unet_fast_disk_complete`, one `normal_loader_ready`); final state load=cuda:0, offload=cuda:0, first_parameter_device=cuda:0, dtype=bfloat16 — GPU-ready; no fallback/error.
Events fired: `unet_i3_config_parity`=1, `unet_i3_transform_classification`=1, `unet_i3_micro_overlap`=1 (+ I-1/I-2 probes intact).

---

# GATE 1 — I-3 header-vs-state-dict config parity

## Dependency trace (what must exist before `get_model`)

| Input | Consumer | Metadata-derivable? |
|---|---|---|
| parameter count | `calculate_parameters` (utils.py:175, nelement) | YES — shape product |
| weight dtype | `weight_dtype` (utils.py:183, numel per dtype) | YES — header dtype |
| key set / shapes / dtype switches | `unet_prefix_from_state_dict`, `state_dict_prefix_replace`, `model_config_from_unet` → `detect_unet_config` (model_detection.py:44) | YES — key names/shapes |
| **allow_fp16 (ZImage dim==3840)** | `detect_unet_config` line 519: `torch.std(layers.{n-2}.ffn_norm1.weight).item() < 0.42` → `ZImage.__init__` inserts float16 into `supported_inference_dtypes` | **NO — VALUE-DEPENDENT** (one small tensor, 7,680 B) |
| supported inference dtypes | `model_config.supported_inference_dtypes` | YES after value probe |
| unet_dtype / manual_cast | `unet_dtype`/`unet_manual_cast` (device + params + dtypes) | YES (same live process) |
| metadata | `load_torch_file` return | YES — header `__metadata__` |

The only payload-dependent input for this model is **`allow_fp16`** — a single small norm tensor (7,680 B), readable via the header's `data_offsets` as a bounded value probe (`_c6_value_probe_allow_fp16`). Not full-dict.

## Parity comparison (authoritative capture vs meta-header derivation)

| Field | Auth | Cand | Match |
|---|---|---|---|
| config_class | ZImage | ZImage | **MATCH** |
| unet_config (topology) | image_model=lumina2, patch_size=2, in_channels=16, dim=3840, cap_feat_dim=2560, n_layers=30, qk_norm, ... | same | value_dependent_gap (allow_fp16) — **gap resolved by value probe** |
| supported_inference_dtypes | [bf16, f16, f32] | [bf16, f16, f32] (fp16 inserted after value probe + extended_fp16_support) | **MATCH** |
| parameters | 6,154,908,736 | 6,154,908,736 | **MATCH** |
| weight_dtype | torch.bfloat16 | torch.bfloat16 | **MATCH** |
| unet_dtype | torch.bfloat16 | torch.bfloat16 | **MATCH** |
| manual_cast_dtype | null | null | **MATCH** |
| expected_param_count | 6,154,908,736 | 6,154,908,736 | **MATCH** |
| expected_module_count | 562 | null (candidate does not construct) | **MISMATCH — explained artifact** (module count is a construction outcome, not a header-derivable input; the probe never builds a candidate model by design) |

Verdict: **MISMATCH (fail-closed)** with exactly two flagged fields:
1. `unet_config` — value_dependent_gap, **resolved** (supported dtypes MATCH after the bounded 7,680 B value probe).
2. `expected_module_count` — candidate side null by design (no candidate construction in probe mode); **explained**, not a config defect.

Every correctness-relevant field that can be derived without construction matches exactly. The config can be known before full tensor materialization **with the addition of the single-tensor allow_fp16 value probe**.

## Incremental state transform feasibility (`process_unet_state_dict`)

For Lumina2/ZImage the transform is the BASE identity (`supported_models_base.py:94`). Empirically verified on the real run:

- `transform_is_identity = True`, output_keys = 453
- **INDEPENDENT: 453 | SMALL_GROUP: 0 | FULL_DICT_REQUIRED: 0** (runs=0 — identity short-circuit)

The read→transform→bind→transfer pipeline is fully decomposable per-key for this model; no whole-dict transform remains.

## Gate 1 conclusion

Header/manifest metadata plus a bounded single-tensor value probe reproduces every correctness-relevant config input. The state-dict transform is per-key independent. **Gate 1 PASSES with one bounded, explained comparison artifact (module count not constructible without building).**

---

# GATE 2 — actual mmap/pageable H2D overlap micro-probe

Bounded micro-probe inside `_SafeOpenProxy` during the real read: at 4 sample ordinals (head, ~25%, ~50%, ~75%), materialize tensor k via the proxy, issue `dest.copy_(tensor, non_blocking=True)` to a TEMPORARY CUDA destination (never bound into the ModelPatcher), materialize tensor k+1 while the transfer is in flight, synchronize, release the temporary destination. The authoritative load then proceeds unchanged (output SHA identical).

| Sample | key | bytes | copy_issue host ms | h2d CUDA ms | next mat ms | combined ms | direct overlap | complete overlap | minflt Δ |
|---|---|---|---|---|---|---|---|---|---|
| ord 2 (head) | cap_embedder.1.weight | 19,660,800 | 4.18 | 5.62 | 7.80 | 12.97 | TRUE (marginal, ~0.45 ms) | FALSE | 0 |
| ord 116 (~25%) | layers.14.ffn.w1.weight | 78,643,200 | 29.41 | 73.79 | 8.20 | 83.70 | FALSE | FALSE | 0 |
| ord 222 (~50%) | layers.21.ffn.w3.weight | 78,643,200 | 21.98 | 23.41 | 1.72 | 25.21 | FALSE | FALSE | 0 |
| ord 337 (~75%) | layers.3.ffn.w1.weight | 78,643,200 | 19.67 | 19.91 | 0.10 | 20.95 | FALSE | FALSE | 0 |

**Classifier: EFFECTIVELY_SERIAL** — mean efficiency 0.0199, direct overlap 1/4, complete overlap 0/4.

## Pageable staging behavior (the decisive finding)

- `copy_issue_host_ms` (19–29 ms for a 78.6 MB tensor) shows the host **blocks inside `copy_(non_blocking=True)`** — the pageable→device path performs synchronous host-side staging; the call does not return while the copy is staged.
- At 3 of 4 samples the next materialize **starts only after the CUDA copy has fully completed** (`overlap_direct=False`) — no concurrency at all.
- The single "direct" sample is marginal (0.45 ms of a 5.6 ms transfer) and contributes efficiency 0.08.
- `minflt_delta = 0` everywhere (pages already resident; the serialization is the pageable-copy staging, not page-in).
- The isolated single-copy rate is also poor (78.6 MB / 73.8 ms ≈ 1.1 GB/s vs the aggregate 4.9 GB/s of the pipelined bulk replay) — the async copy chain is what makes the bulk transfer fast, and it is exactly that chain that the proposed interleaved design cannot use (host is busy staging each copy, not reading).

The I-1/I-2 wave simulation assumed the host could read while the GPU copies. The micro-probe proves the opposite on this Modal environment for the **currently proposed mmap/pageable path**: the host is occupied by synchronous staging during each copy, so subsequent materialization cannot overlap.

## Gate 2 conclusion

**EFFECTIVELY_SERIAL.** The direct mmap/pageable interleaved pipeline loses its theoretical benefit. Per the task rule, this is a STOP condition for the real pipeline as currently proposed.

---

# Savings model update

| Item | Value |
|---|---|
| previous ideal simulation ceiling | ~1.93 s (theoretical producer/consumer overlap) |
| measured actual concurrency efficiency | **0.02 (EFFECTIVELY_SERIAL)** |
| construction/config serial head that remains | get_model 365.0 ms + bind 216.5 ms ≈ 581.5 ms |
| pageable staging cost (per 78.6 MB copy) | 19–29 ms host-staged, synchronous |
| predicted real pipeline wall | ≈ 4.55–4.6 s (current serial 4.605 s; overlap ≈ 0) |
| conservative expected saving | **≈ 0–0.05 s (noise) — NOT the prior 0.9–1.7 s estimate** |

The prior 0.9–1.7 s estimate is **contradicted** by direct measurement: it rested on the theoretical wave simulation, which assumed host-read concurrency that the pageable copy path does not provide on this environment.

---

# Decision

**STOP** — the direct mmap/pageable interleaved loader is not viable as proposed.

- Gate 1: passes (metadata parity exact for every correctness-relevant derivable field; allow_fp16 resolved by a bounded single-tensor value probe; transform fully INDEPENDENT).
- Gate 2: **fails** — pageable/mmap H2D is effectively serial (efficiency 0.02, complete overlap 0/4); actual realistic overlap ≈ 0 < 300 ms.

The ~1.9 s opportunity is real in the temporal structure (Gate 1 + wave timing) but is **not reachable through the proposed direct mmap/pageable path**. The only bounded mechanism that could capture it is multi-buffer **pinned staging** (a staging ring so the host never blocks on pageable staging and can read while DMA runs) — explicitly out of scope for this task ("Do not introduce pinned staging") and therefore recorded here as the required bounded design change, NOT authorized.

Do not implement the real read→assign→H2D pipeline.

## Uncertainty (retained)

- Micro-probe samples 4 points (bounded by design); the classifier thresholds (≥0.6 TRUE, 0.2–0.6 PARTIAL) are documented but arbitrary.
- The single marginal direct-overlap sample (head, ord 2) hints the very first copy after a long idle gap may partially overlap; irrelevant at scale.
- Pinned-staging (the out-of-scope design change) was NOT measured; its overlap potential remains unquantified. The 62.5 ms I-2 wave gap and the ~4.9 GB/s aggregate chain suggest a staging ring would recover most of the ~1.9 s ceiling, but this is a hypothesis, not evidence.
- Host-rebuild waterfall reconciliation FAILED is pre-existing for this vehicle (baseline-identical); local reconciliation OK (3.2 ms).

---

## You asked for:
- Gate 1: header/metadata config parity vs the authoritative state-dict-derived config (fail closed) + incremental transform classification; Gate 2: actual mmap/pageable H2D/read overlap micro-probe; both measurement-only, one deploy + one cold run, decision and updated savings model.

## You should now manually check:
- **Decision: STOP.** Do not implement the interleaved loader on the mmap/pageable path. If the ~1.9 s opportunity is still desired, it requires a NEW decision + a bounded pinned-staging-ring design (out of scope here, unmeasured).
- The `expected_module_count` parity artifact (candidate null by design): if a future design needs pre-construction module-count validation, it must construct a candidate model or predict module count from the config — add to the design work.
- The pageable copy staging cost (19–29 ms per 78.6 MB) is the physical blocker; confirm on any future staging-ring experiment that pinned sources remove the host-side block (measure `copy_issue_host_ms` ≈ 0.1 ms).
- Probe-off byte-identity remains intact (no probe events, no I-3 code paths when the flag is unset; verified by tests + baseline runs).
- Output SHA `20b10e1f...e5260` identical across probe-off baseline, I-1/I-2 probe run, and this I-3 run — probe instrumentation never altered the authoritative model.
