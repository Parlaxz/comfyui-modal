# V2_BATCH_C13 — NATIVE FAST-DISK WINNER FORENSIC AUDIT

**Role:** Read-only independent reviewer lane (Batch-C concurrent work: untouched, `main` only)
**Date:** 2026-08-15
**Scope:** Explain every millisecond of the accepted native fast-disk UNET load chain (~4.605 s healthy), resolve the read/H2D page-fault ambiguity, audit for idle gaps ≥ 25 ms, evaluate safe (non-invasive) optimizations.
**Constraints honored:** No source modified. No implementation code. No deploy. No Modal run. No commit. Only artifact: this Markdown report.
**Evidence base:** 7 C6 reports + 10 earlier fast-disk/two-lane/timing reports + 2 telemetry skills (read in full by subagents), independent source trace of `comfymodal_runtime/model_preload.py` (20,701 lines), `comfymodal_runtime/modal_app.py`, `comfy/utils.py`, `comfy/sd.py`, `comfy/model_management.py`, `comfy/model_patcher.py` (ComfyUI v0.24.0), and `safetensors/torch.py` (0.8.0-rc.1). Key claims verified against source by the auditor.

---

## 1. Executive summary — the physical model

The accepted native fast-disk chain is **physically three serial segments**:

```
read 1.624 s ──► construction/bind barrier 0.514 s ──► H2D 2.468 s  =  4.605 s
```

(Reference: C6 I-1/I-2 probe run `v2_2026-08-14_22-24-46`; healthy host, exact hit, `serial_current` 4605.3 ms.)

**What each segment actually is (resolved):**

1. **Read (1.624 s)** — safetensors mmap `get_tensor` calls. `get_tensor` itself returns **zero-copy `torch.frombuffer` views** over the mmap (`safetensors/torch.py:468`; verified 453/453 `is_view=true`, `storage_offset=0`). Pure view creation for all 453 tensors costs only **~181 ms** (measured in the ring-implementation run). The remaining **~1.35 s of the read span is physical page-in: the 12.31 GB payload is faulted into the page cache inside this window**. This is CONFIRMED, not inference: (a) the H2D span shows zero host blocking (`to_wall ≈ to_device`, Δ ≤ 0.134 ms — Gate-2 proved a pageable `copy_` over missing pages blocks the host 19–29 ms per 78.6 MB, so missing pages at H2D time would be visible); (b) I-1 byte reconciliation is exact (12,309,817,472 B) and the per-tensor walls are bytes-proportional with a bursty head.
2. **Construction/bind barrier (0.514 s)** — `get_model` 383.4 ms + `ModelPatcher` ctor 2.2 ms + `load_model_weights(assign=True)` bind 109.6 ms + ~18.5 ms misc (incl. key-only config scans). The 383 ms `get_model` is **cold first-allocation / allocator warm-up** on a fresh container (measured: 2390 ms fresh-pre-read → 749 warm → 851 post-read; minflt Δ = 0, RSS Δ = 0 → NOT COW, NOT memory pressure — the "COW" label in prior V1 work was wrong). Warm-container `get_model` is 35–83 ms.
3. **H2D (2.468 s)** — pure device-bound DMA of **already-resident** pages: `to_wall ≈ to_device` (Δ 0.134 ms), Σ wave device 2406.5 ms, effective 4.99 GB/s, 62.5 ms inter-wave host gap (2.6%). **No page-fault servicing occurs inside H2D.**

**Key resolution of the mission's central ambiguity:** The native path is **READ + H2D** (two serial, physically distinct passes), *not* a fused "page-fault-during-DMA single pass". The read pass faults the full payload into RAM; the H2D pass DMA-copies resident pages. The salvage report's phrase "native single-pass page-fault-during-DMA" is a **contradicted gloss**: what is genuinely single-pass is the absence of any extra staging copy — but the page-in happens in the read span, before H2D starts (see §6, contradiction #1).

**Where the remaining money is:** the 1.6 s read is the largest serial segment but is already near volume bandwidth (~8 GB/s aggregate — *faster* than every custom reader ever measured: preadv 4.07 GB/s, pinned staging 3.6 GB/s). It cannot be overlapped with H2D (falsified, eff 0.02) and cannot be removed on a cold container. The **only loader-internal wins that survive C6 evidence** are (a) hiding `get_model`+config under the read via header-derived config + meta construction (~200–300 ms cold), and (b) H2D grouping/launch-gap cleanup (~50–150 ms). The largest realistic win (~0.5 s) is operational: page-cache warm reuse of containers.

---

## 2. The accepted native path — code map

Loader chain (verified in current source):

| Stage | Code |
|---|---|
| Lane entry (plan-receipt hoist) | `_maybe_schedule_execution_unet_at_plan_receipt` modal_app.py:7549 → `_execution_unet` model_preload.py:12719 |
| `_load_unet` entry, stamps | model_preload.py:13240–13286 |
| Accepted branch | `_invoke_original("UNETLoader")` model_preload.py:13322 (ring/meta-direct flags default OFF) |
| Original node method | `nodes.UNETLoader.load_unet` → `comfy.sd.load_diffusion_model` |
| **Read** | `comfy.utils.load_torch_file` (utils.py:122–167) → `safe_open(ckpt, framework="pt", device="cpu")` (mmap backend, `DISABLE_MMAP=False`) → per-key `get_tensor` (zero-copy view) → `sd[k] = tensor` |
| Config detection | `unet_prefix_from_state_dict` + `detect_unet_config` + `calculate_parameters` + `weight_dtype` + `model_config_from_unet` — **keys/shapes/dtype only, zero data touch** (model_detection.py:44–86, 1030–1050; utils.py:175–193) |
| Construction | `model_config.get_model(sd, prefix)` — module tree built on `inital_load_device` (GPU in HIGH_VRAM) |
| Patcher + deferral | `ModelPatcher(model, load_device, offload_device)`; flag-gated `model.to()` deferral `_fast_disk_maybe_defer_to` model_preload.py:6818 |
| Bind | `load_model_weights(sd, prefix, assign=True)` model_base.py:340–355; `_fast_disk_handle_bind` model_preload.py:6905; params become the mmap views (no data copy at bind) |
| **H2D** | single replayed `model.to(cuda)` / `ModelPatcher.load` → per-module transfer, per-module `torch.cuda.synchronize()` (model_patcher.py:1022–1023), final `torch.cuda.synchronize()` + CUDA-event timing model_preload.py:6594–6623 |
| Ready | `normal_loader_ready` state collection + probe registration model_preload.py:13356–13398 (diagnostic only, not a gate); graph join `wait_unet` ≈ 0 ms |
| Telemetry export | `_restore_timing` modal_app.py:16827 → `__init__.py` meta → `history[prompt_id]["meta"]["restore_timing"]` |

The flag `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` (model_preload.py:5615) is default OFF in code; the accepted production deployment runs it ON (assign=True + deferred single `to()` — the change that removed the legacy double H2D pass, UNETLoader wall 4550.28 → 3353.93 ms median, −26%). Verify deployment env at audit time.

---

## 3. Telemetry semantics (what each number means)

| Symbol | Bracket | Clock | Includes CUDA sync? |
|---|---|---|---|
| `read_start/read_end` (model_preload.py:3854/3872) | whole `load_torch_file`: open + header parse + 453 `get_tensor` | host monotonic, container side | no |
| I-1 per-tensor `get_tensor` walls (proxy :4697) | each `get_tensor` call | host monotonic | no (4 probe sample points add syncs — accepted perturbation) |
| `to_wall_ms` (:6519/6594) | H2D replay, host enqueue→return (includes per-module syncs) | host monotonic | yes (drain inside span) |
| `to_device_ms` (CUDA events :6535/6597) | device timeline of whole H2D | device | yes (events) |
| **`to_wall ≈ to_device` (Δ ≤ 0.134 ms)** | — | — | **anti-overlap invariant: no host stall ⇒ pages resident before H2D** |
| `h2d_enqueue_host_ms` / `h2d_sync_wait_host_ms` | enqueue loop / sync wait (healthy ≈ 1.175 ms) | host | — |
| `unet_fast_disk_complete` | one authoritative fast-disk load | both | carries to_wall/to_device |
| `normal_loader_ready` (:13368) | after load returns | host | diagnostic only |
| `restore_timing` | restore phase timers (NOT the loader) | container | legacy vs current profile differ — do not mix |

**minflt caveat (critical):** `getrusage` minflt/majflt are **genuinely 0 under gVisor** (sentry handles guest faults internally — V2_HOST_HARDWARE_AND_PRESSURE_TELEMETRY.md:225–248). The fast-disk report's "0/0 faults" cannot prove or disprove residency. The genuine residency proofs are the timing invariant + I-1 byte reconciliation. All C6 "minflt Δ = 0" observations are likewise non-informative for page-in location.

---

## 4. Exact native timeline (healthy exact-hit, reference run)

All times ms, host wall unless noted. Overlap column = overlap with any other stage in the CURRENT accepted path.

| # | Stage | Wall (ref) | CPU work | File I/O / page faults | CUDA | Sync | Overlap today |
|---|---|---|---|---|---|---|---|
| T0 | `_load_unet` entry (lane start) | 0 | stamps, flags, kwargs | — | — | — | lane runs off graph thread; concurrent with graph setup/prefill (already overlapped) |
| T1 | checkpoint open (`safe_open`, mmap) | ~9 | Rust mmap open, JSON header read (~8.9 KB) | header read | — | — | none (precedes all) |
| T2 | header parse (`list(f.keys())`) | ~79 | JSON parse 453 keys; config fields visible (Gate 1 proved full config derivable here + one 7,680 B probe) | — | — | — | none; **cacheable per file** |
| T3 | first tensor exposure (first `get_tensor`) | 0+ | view creation (µs) + first-fault batch | **page-in begins** | — | — | — |
| T4 | state_dict completion (`read_end`) | 1623.7 total (open+parse ~88.5 + materialize 1535.2) | 453 view creations (~181 ms worth) + **~1.35 s page-fault servicing** (I-1: bytes-proportional, bursty head — first 4 tensors ≈ 305 ms; 78 MB tensors 15–18 ms each ≈ 4.4 GB/s effective; small tensors pay 30–120 ms fixed costs — per-fault latency dominated) | **12.31 GB faulted into page cache (CONFIRMED)** | — | — | none (serial by dependency) |
| T5 | config detection | ~10–90 (in "misc" 18.5 in ref; separate in fast-disk runs) | 5–7 key-only dict passes (prefix, detect, params, dtype, matches) — trivial per-key CPU | none (shapes/dtype metadata only) | — | — | none; **fully header-derivable (Gate 1 PASSED, fail-closed)** |
| T6 | `get_model` | 383.4 (cold allocator; 35–83 warm) | module tree construction; **cold first-allocation** (2390 fresh-pre-read / 749 warm / 851 post-read measured; minflt=0, RSS=0 ⇒ allocator warm-up, not COW) | none | params allocated on GPU (HIGH_VRAM) | — | none; **overlap-able under read via meta construction (validated 19.5–199.9 ms)** |
| T7 | assign/bind | 109.6 (16–28 warm) | `load_model_weights(assign=True)`: prefix strip + pop (1 key pass), torch `load_state_dict` assign machinery; params = mmap views, **no data read** | none | none | — | none (needs complete sd) |
| T8 | fast-disk deferral | ~0 | decision recorded at get_model exit; original `to()` skipped, replay queued | — | — | — | — |
| T9 | H2D scheduled | 0 (replay immediately after bind — no post-bind gap) | — | — | enqueue begins | — | — |
| T10 | first CUDA copy | ~0.3 s into H2D | — | — | wave 1 (~330.6 device) | — | — |
| T11 | last CUDA copy | 2.406 (Σ wave device) | per-module `.to()` passes; per-module syncs (model_patcher.py:1023) | none (resident pages) | 8 waves: 330.6/281.6/258.6/**431.1 outlier**/265.9/306.2/275.2/257.5; 4.99 GB/s | per-module syncs | none; inter-wave host gap 62.5 ms (2.6%) |
| T12 | final sync | 2.468 (`to_wall`) | `torch.cuda.synchronize()` (:6598) | — | — | full-device | — |
| T13 | `normal_loader_ready` | +1.5–1.9 (fast-disk runs) | state collection, forward-probe registration, ModelPatcher bookkeeping | — | — | — | — |
| T14 | graph join → first forward | wait_unet 0.18–0.36; loader-return→first-forward 201.7–222.7 | graph join + sampling start + first-kernel warm-up | — | — | — | sampler/prefill window (C5/C6 territory, outside loader) |

**Serial chain (CONFIRMED):** T1–T4 (read) → T5–T8 (construction/bind) → T9–T12 (H2D) → T13. `to_wall ≈ to_device` proves T4 and T9–T12 do not overlap.

---

## 5. Key ambiguity — resolved

**Q1: Does the measured "read ~1.6 s" actually fault the 12.31 GB payload into RAM?**

**CONFIRMED: yes.** Chain of proof:
1. `get_tensor` is zero-copy view creation (safetensors torch.py:468 `torch.frombuffer(...).reshape(...)`; 453/453 `is_view=true`) — views alone cost ~181 ms (ring-run measurement).
2. Therefore ~1.35 s of the read span is page-in of the payload into page cache. I-1's per-tensor walls (bytes-proportional, 78 MB @ ~4.4 GB/s, bursty head, small-tensor fixed costs of 30–120 ms) are the direct observation of fault servicing.
3. The anti-overlap invariant (`to_wall ≈ to_device`, Δ ≤ 0.134 ms) proves no pages were missing at H2D time; combined with Gate-2 (missing-page pageable copy_ would block host 19–29 ms/78.6 MB), the faulting must have completed in the read span.

The "mostly metadata/view creation with faulting deferred to H2D" hypothesis is **FALSIFIED**.

**Residual measurement anomaly (flagged, not fully reconcilable from reports):** I-1 attributed the 1.54 s to per-`get_tensor` walls, while the ring-implementation run measured `get_tensor` at 181 ms total with page-in landing in its pinned staging (3.6 GB/s). Both runs claim fresh containers. Possible contributors (INFERENCE): probe bookkeeping, host/volume variance (read band 1.54–2.17 s), sentry fault-batch semantics. **Immaterial to the native path**: both agree the payload is resident before H2D in the native path, and the healthy native read (~8 GB/s aggregate) is the *fastest page-in rate ever measured* on this stack.

**Q2: Does H2D 2.47 s include substantial storage/page-fault servicing?**

**CONFIRMED: no.** `to_wall ≈ to_device` (Δ ≤ 0.134 ms) with a full-device sync inside the span; `h2d_sync_wait_host_ms` ≈ 1.175 ms healthy. H2D is pure DMA of resident pages at 4.99 GB/s effective. Note the bulk rate (4.99 GB/s) is far below isolated pageable-copy rates (7–26 GB/s, ring probe) and pinned rates (50–56 GB/s) — the bulk loss is copy-size/grouping/sync structure, not storage (see §7, gap 7).

**Physical model verdict:** the native path is **READ (fault-in) + H2D (DMA)** — two serial passes sharing the same 12.31 GB. The "fused page-fault-during-DMA single-pass" model is **wrong as mechanism** (page-in completes in the read pass); what is single-pass is the *staging* (no intermediate copy), which is why two-pass custom loaders (preadv→pinned) cannot win: they pay the read at equal-or-worse rates (4.07 / 3.6 GB/s vs native ~8 GB/s) *plus* an extra DMA pass.

---

## 6. Idle gap audit — healthy-path segments ≥ 25 ms

| # | Segment | Measured wall | Dependency | Can overlap? | Can cache? | Can snapshot? | Can eliminate? | Compatibility risk |
|---|---|---|---|---|---|---|---|---|
| 1 | **Read materialize (page-in)** | 1535.2 (band 1.06–1.71 s) | payload→RAM before device-bound H2D | NO (falsified: pageable interleave eff 0.02; pinned ring needed page-in ≥ 8 GB/s to win, custom readers achieve 3.6–4.07) | **YES — page cache on container reuse** (read band low end 1.06 s ≈ warm; 35 s-gap study shows reuse at 20 s) | NO by design (UNET excluded from snapshot) | NO on cold container (already fastest measured rate) | n/a |
| 2 | **Open + header parse** | 88.5 | file header | NO | YES — parse result per file/container | partially (config fields) | partially (parse is fixed format; ~79 ms is slow for 8.9 KB — sentry/volume JSON read) | LOW |
| 3 | **Config detection** | ~10–90 (in misc 18.5 ref) | sd keys only | NO today; YES with header-derived config (Gate 1 PASSED) | YES per file | YES | YES via header (37.8 + 1.8 ms probe measured) | LOW-MED (module-count artifact explained) |
| 4 | **`get_model` (cold allocator)** | 383.4 (35–83 warm; 2390 worst fresh) | config; complete-enough sd | **YES — meta-construct under read** (validated: meta get_model 19.5–199.9 ms, cold-immune, meta-poison fixed in salvage) | allocator warm-up is cache-like | n/a | overlap-able (hides ~383 cold) | MED (config parity, bind ordering I-11/I-12, fallback contract) |
| 5 | **Bind** | 109.6 (16–28 warm) | complete sd + module | NO | NO | NO | partially (torch load_state_dict overhead; assign=True already minimal) | LOW-MED |
| 6 | Post-bind → first CUDA issue | ~0 (replay contiguous with bind) | — | — | — | — | no gap exists | — |
| 7 | **H2D** | 2467.9 (Σ device 2406.5) | resident pages | NO with pageable source (eff 0.02); pinned staging would need page-in ≥ 8 GB/s (never achieved: 3.6–4.07) | NO | NO | partially: inter-wave gap 62.5 ms (2.6%); wave-3 outlier 431 ms (transient); per-param small-copy structure (~1.1 GB/s isolated) | MED (core-adjacent grouping) |
| 8 | H2D → ready bookkeeping | 1.5–1.9 | — | — | — | — | negligible | LOW |
| 9 | Loader-return → first forward | 201.7–222.7 | graph join + sampler + first kernel | already overlapped (lane; prefill hides 0.66–0.92 s) | n/a | n/a | scheduler/first-kernel territory (C5/C6), not loader | n/a |
| 10 | Python/GIL gaps | ~0.8 ms/chunk instrumentation-inclusive; native `to()` is a C++ loop | — | — | — | — | negligible in native path (the 3.6 ms/wave host issue in the ring was page-in blocking, not GIL) | — |

**Summary: exactly three meaningful healthy-path idle segments exist: read page-in (1.54 s, not removable on cold), construction barrier (0.51 s, partially overlap-able), H2D structural losses (≤ ~0.25 s, partially removable).** Everything else is noise (< 25 ms) or already overlapped.

---

## 7. Safe change investigation (nothing falsified by C6 is re-advocated)

1. **Meta construction while the current read happens** — SUPPORTED, bounded. Header-derived config (Gate 1 PASSED, fail-closed, one explained artifact: `expected_module_count`) + meta `get_model` (validated 19.5 ms probe / 199.9 ms container-cold; meta-poison fix 0.18 ms already exists) + real bind `assign=True` when sd completes + **native read and native H2D untouched**. Critically, meta construction is immune to the cold-allocator penalty that killed the ring's construction-before-read (real construction pre-read paid 2340 ms; meta construction pays ≤ 200 ms). Expected: hide ~383 ms cold / 35–83 ms warm + config (~10–90 ms). This is the *only* surviving route from the C6 sequence — the meta piece of META_DIRECT was CONFIRMED; only its preadv two-pass I/O was the failure.
2. **Config derivation from header** — Gate 1 CONFIRMED parity (config_class, dtypes, parameters 6,154,908,736, weight_dtype all match; 453/453 per-key INDEPENDENT transform, 0 FULL_DICT_REQUIRED). Standalone value 10–90 ms; enabling value for (1). Also makes config cacheable across requests on reused containers.
3. **Earlier `get_model`** — only safe in meta form (see 1). Real-construction-earlier is FALSIFIED (ring impl: 2340.92 ms).
4. **Allocator warm-up placement** — native order (read → construct) is already favorable (post-read 851 vs pre-read 2390). Do NOT reorder. Meta construction sidesteps the issue entirely.
5. **Pre-create ModelPatcher** — ctor is 2.2 ms. Not worth it. Reject.
6. **Reduce prefix/config scans** — 5–7 key-only passes over 453 keys ≈ 1–5 ms total. Not worth it. Reject (mission's "state-dict scan duplication" is a red herring at this scale).
7. **Bind with assign=True more directly** — already the accepted single-pass bind (109.6 cold / 16–28 warm). Further ~30–60 ms only via bypassing torch `load_state_dict` machinery with a direct param-level loop — LOW-MED value, MED risk. Conditional.
8. **Avoid redundant state_dict iteration** — see 6; negligible.
9. **Begin native H2D earlier without custom staging** — impossible: H2D depends on complete sd + bind (the 0.51 s barrier). The only "earlier" is hiding the barrier's construction part under the read (item 1). No change to H2D start is possible in the native ordering.
10. **Larger internal transfer grouping** — the I-2 wave probe (8 × 128 MiB) measured 4.99 GB/s device with 62.5 ms inter-wave gap. Grouping to fewer/larger waves or eliminating per-module syncs: ≤ ~150 ms realistic. Requires promoting probe machinery to production code — bounded, MED risk. The wave-3 outlier (431 ms) is transient bandwidth, not structure.
11. **Eliminate final bookkeeping** — 1.5–1.9 ms. Reject.
12. **Page-cache warm reuse (operational, not code)** — the read band (1.06–1.71 s) plus the 35 s-cooldown study (warm-container reuse resolved at 20 s gap) indicate warm containers serve the fast-disk read substantially faster. `COMFYMODAL_V2_PAGE_READINESS_MODE=willneed` + `pretouch` are currently off by design; `madvise(WILLNEED)` alone is advisory (falsified as architecture value) but becomes useful *given* container reuse. Largest single lever (~0.3–0.6 s), zero loader code, but a production-config/ops decision (isolation/cost trade-offs).

---

## 8. External loader concepts — comparison (evidence-gated)

| System | Mechanism | Relevance to this stack |
|---|---|---|
| **fastsafetensors** (foundation-model-stack; note: repo moved from gordicaleksa) | Explicitly anti-mmap; async parallel reads; lazy tensor instantiation directly in GPU memory via DLPack; GDS (cuFile) storage→HBM on Linux, DirectStorage on Windows; 4.8–7.5× vs safetensors, 26.4 GB/s NVMe | GDS dead on Modal Volume (no `/proc/driver/nvidia-fs`, C6-measured). The nogds async-read win assumes storage saturates with parallelism — contradicted here: native mmap read (~8 GB/s healthy) already beats every custom reader measured (preadv 4.07, staging 3.6). No applicability evidence. |
| **Run:ai Model Streamer** (run-ai/runai-model-streamer) | Multi-threaded concurrent storage reads into a CPU buffer; H2D of arrived tensors overlaps later reads; 3.3–6.2× vs HF on NVMe; 5.04 s for 13 GB from S3 | This is precisely the read∥H2D overlap architecture that Gate-2 FALSIFIED on pageable memory (eff 0.02; host blocks 19–29 ms/78.6 MB) and the pinned-ring production FALSIFIED end-to-end (page-in-bound 3.6 GB/s; wall 9027 > serial-equiv 6901). Their win comes from saturating local NVMe — not achievable at 3.6–8 GB/s volume page-in. |
| **InstantTensor** (scitix/InstantTensor; no confirmed AWS-branded product — closest AWS analogs: SageMaker Fast Model Loader, GDS on FSx for Lustre over EFA) | Direct I/O (AIO/io_uring) + tuned concurrency + pipelining + NCCL + optional GDS; 32.4× on Qwen3-30B-A3B single H200; avoids page cache | Direct I/O forfeits page-cache reuse (the one free win on reused containers); concurrency gains unproven vs native 8 GB/s read; NCCL irrelevant single-GPU. Note: "GPU page-fault-during-kernel" (CUDA managed memory style) is NOT what ComfyUI's mmap path does — ComfyUI's faults are CPU-side file→page-cache; the DMA is separate and synchronous. |
| **ServerlessLLM** (OSDI'24) | Custom binary format + O_DIRECT + pinned memory pool + 4–8 parallel I/O threads + tier (disk∥RAM∥GPU) pipelining; 6–10× vs safetensors; explicitly cites safetensors' "112K page faults for LLaMA-2-7B" as the cost | O_DIRECT + format conversion + pinned pool + C++ reader = new I/O architecture (heavy); the pinned-pool overlap was attempted (pinned ring) and failed on this storage (page-in 3.6 GB/s). Their page-fault finding independently corroborates that the native mmap read's cost IS page faults — matching our Q1 conclusion. |

**What native ComfyUI gets "for free" from mmap (CONFIRMED concepts, applicability inference):**
1. **No explicit read pass** — demand paging serves the payload at ~8 GB/s healthy, which beat every custom reader this project built (4.07 GB/s preadv, 3.6 GB/s staging). The OS readahead + bursty fault batching is empirically superior to hand-rolled I/O here.
2. **Zero-copy view creation** — 453 tensors in ~181 ms; bind with `assign=True` costs zero data movement.
3. **Config from metadata** — keys/shapes/dtype never touch payload bytes (free for Gate-1-style header derivation).
4. **Page-cache reuse across requests** — the only mechanism that can eliminate the read segment, and it requires container reuse (operational).

---

## 9. Optimization ranking

| # | Candidate | Native stage targeted | Healthy measured cost | Max possible saving | Realistic expected saving | New I/O arch? | Workflow/update risk | Recommended? |
|---|---|---|---|---|---|---|---|---|
| 1 | Container warm-reuse + page-cache retention (ops) | read (page-in) | 1535.2 | ~1200 | ~300–600 (band evidence: 1.06 s low end) | NO | LOW-MED (isolation, cost, teardown policy) | **YES — measure first (zero code)** |
| 2 | Header config + meta-construct under read, native bind+H2D | construction barrier (get_model 383.4 + config) | 514 (cold) | ~470 | **200–300 cold / 50–100 warm** | NO | MED (Gate-1 artifact, bind ordering invariants, fallback contract) | **YES — highest-confidence loader-internal** |
| 3 | H2D grouping / wave machinery promotion | H2D (62.5 ms gap + per-param structure) | 2467.9 | ~250 | 50–150 | NO | MED (core-adjacent; probe code exists) | YES (bounded, gateable) |
| 4 | Direct param-level bind loop (skip torch load_state_dict machinery) | bind | 109.6 | ~80 | 30–60 | NO | MED | MAYBE |
| 5 | Header-config standalone (no overlap) | config | ~10–90 | 90 | 30–90 | NO | LOW | MAYBE (only as enabler of #2) |
| 6 | Cache open+parse per container | open/parse | 88.5 | 80 | 30–60 (reused containers) | NO | LOW | MAYBE |
| 7 | Pre-create ModelPatcher / kill final bookkeeping | ctor + ready | ~5–20 | 20 | 5–15 | NO | LOW | NO |
| 8 | Pinned-ring staging pipeline (`COMFYMODAL_V2_UNET_PINNED_RING`) | read+H2D | 4105 | ~2000 (theory) | **0 (measured −2.9 s: 9027 vs 6901 serial-equiv)** | YES | HIGH | **NO — FALSIFIED (C6 measured)** |
| 9 | Meta + preadv two-pass (`COMFYMODAL_V2_UNET_META_DIRECT`) | read+H2D | 4105 | ~1200 (theory) | **0 (measured −0.24 s: 4839.9 vs 4605)** | YES | HIGH | **NO — FALSIFIED (C6 measured)** |
| 10 | Pageable read→H2D interleave | read+H2D | 4105 | ~1700 (theory) | 0–50 (eff 0.02) | NO | HIGH | **NO — FALSIFIED (C6 measured)** |
| 11 | GDS / cudaHostRegister / fadvise | — | — | — | — | — | — | NO — dead on Modal (rc=304; no nvidia-fs; advisory-only) |

**Total safe plausible savings (items 2+3+4+6, cold container):** ~0.35–0.6 s; with item 1 (reuse): ~0.7–1.2 s. None require new I/O architecture; all are bounded and gated by the existing fallback machinery.

---

## 10. Contradictions found in prior C6 interpretation (do not inherit)

1. **"Native H2D is page-fault-during-DMA single-pass" (salvage report) vs measured anti-overlap invariant.** The mechanism is wrong: page-in completes in the read span (Δ ≤ 0.134 ms proves no faulting during H2D; Gate-2 proves missing pages would block the host). The correct property: no staging copy (single pass over the data), which is precisely why two-pass loaders lose.
2. **"Full-file volume read converges to ~3–4 GB/s whatever the mechanism" (salvage) vs I-1 native read at ~8 GB/s aggregate** (1.54 s for 12.31 GB; healthy band 1.06–1.71 s). The "floor" was measured only via custom readers (preadv 4.07, staging 3.6); the native mmap read beats both by ~2×. Custom loaders failed on extra passes + overhead at equal-or-worse rates — not because of a bandwidth ceiling.
3. **I-1 `get_tensor` walls (1535 ms, page-in inside read) vs ring-run `get_tensor` walls (181 ms, page-in in staging @ 3.6 GB/s).** Same call, different attribution and rates. Unresolved measurement anomaly (probe bookkeeping / host variance / sentry fault batching). Both agree pages are resident before H2D in the native path.
4. **The 0.9–1.7 s saving estimate round-trip** (proposed → 0–0.05 s Gate-2 direct → "reinstated" 1.2–1.4 s via resident-page probe extrapolation → 1.4–2.2 s design prediction → measured hidden_overlap 0.0 and negative savings in both production pipelines). Every overlap estimate in reports 3/5/6 was simulation or extrapolation; the three measured pipelines (Gate-2, META_DIRECT, pinned ring) all showed ≤ 0 hidden overlap.
5. **minflt "0/0" as residency proof (fast-disk report).** getrusage faults are sentry-zero under gVisor; the fast-disk report's read-diagnostic fault counts are artifacts. Residency is proven by timing invariants and byte reconciliation, not fault counters.
6. **The "COW" label for slow `get_model` (V1-era) vs allocator warm-up (C6-measured: minflt=0, RSS=0).** Prior explanation corrected; the cold first-allocation cost is host/allocator-state dependent (35–2340 ms band).

---

## 11. Conclusions

1. The accepted native chain is a **serial READ→construct/bind→H2D** pipeline; all three measured segments are confirmed as: (a) full-payload page-in (~1.6 s, the fastest measured read on this stack), (b) cold-allocator construction + assign bind (~0.51 s, partially hideable), (c) device-bound DMA of resident pages (~2.47 s, no storage servicing).
2. Every invasive C6 loader failed for one physical reason: **they added a pass while failing to match the native page-in rate**. The read is not the bottleneck to attack with custom I/O; it is the fastest component already.
3. The safe, evidence-backed path forward is a **meta-native hybrid**: header-derived config (Gate 1 CONFIRMED) + meta construction under the read (CONFIRMED) + the existing native assign-bind and native H2D untouched, gated by the existing fallback contract. Expected 200–300 ms cold.
4. The largest single lever (0.3–0.6 s) is operational: page-cache retention via warm-container reuse — zero loader code, requires a production decision.
5. H2D structural cleanup (wave grouping, sync reduction) is worth a bounded experiment (~50–150 ms).

---

## 12. Required final fields (audit answer)

- **report path =** `V2_BATCH_C13_NATIVE_FAST_DISK_FORENSIC_AUDIT.md` (this file, repo root)
- **changed files =** report only
- **commit =** none
- **deploys =** 0
- **Modal runs =** 0
- **native path physical model =** READ (mmap demand-paging of the full 12.31 GB into page cache, ~1.6 s) → construction/bind barrier (~0.51 s cold) → H2D (device-bound DMA of resident pages, ~2.47 s); three strictly serial segments; no staging copy
- **read stage actually faults payload =** YES — CONFIRMED (view creation alone ≈ 181 ms; ~1.35 s of the read span is page-fault servicing; proven by `to_wall ≈ to_device` Δ ≤ 0.134 ms + I-1 byte-exact reconciliation + Gate-2 host-block counterfactual)
- **H2D includes page faults =** NO — CONFIRMED (Δ ≤ 0.134 ms; sync-wait ≈ 1.175 ms; H2D is pure DMA at 4.99 GB/s effective)
- **native read/H2D overlap =** ZERO today — CONFIRMED (`to_wall ≈ to_device`); pageable interleave impossible (eff 0.02 measured); pinned overlap falsified end-to-end (page-in-bound)
- **confirmed serial stages =** open/parse → per-tensor page-in → config (keys-only) → get_model → bind → H2D → ready; also CLIP/prefill overlap of the whole lane is already exploited (loader off critical path)
- **largest removable stage =** read page-in (1535 ms) — removable only via warm page cache (container reuse), not in-loader
- **second largest =** construction barrier get_model cold-allocator (383.4 ms) — hideable under read via meta+header (200–300 ms realistic)
- **third largest =** H2D structural losses (inter-wave gap 62.5 ms + per-param copy structure; ≤ ~150 ms realistic)
- **meta-native hybrid assessment =** SUPPORTED — the only surviving route from C6: header config (Gate 1 PASSED) + meta get_model (19.5–199.9 ms measured, cold-immune, meta-poison fixed) under the read; native assign-bind and native H2D unchanged; gate via existing fallback machinery; expected 200–300 ms cold / 50–100 ms warm
- **header-derived config opportunity =** CONFIRMED viable (parity with one bounded artifact: expected_module_count); standalone 10–90 ms, enabling value for construction overlap; also cacheable per file/container
- **state-dict scan duplication =** negligible (5–7 key-only passes over 453 keys ≈ 1–5 ms total); not a real cost
- **bind overhead opportunity =** small (109.6 cold / 16–28 warm; assign=True already minimal); ~30–60 ms only via direct param-level loop bypassing torch load_state_dict — MED risk
- **H2D launch-gap opportunity =** no post-bind gap exists (replay contiguous with bind); the pre-H2D barrier is the opportunity (see meta-native hybrid); inter-wave gap 62.5 ms removable via grouping
- **total safe plausible savings =** ~0.35–0.6 s cold container (items 2–6 of §9); ~0.7–1.2 s with warm-container page-cache reuse
- **highest-confidence next experiment =** meta-native hybrid: header-derived config + meta construction overlapped with the native read, native assign-bind + native H2D untouched, gated by existing fallback contract (expected 200–300 ms cold); measurement-only companion: fast-disk read on a warm-reused container to quantify the page-cache lever
- **contradictions found in prior C6 interpretation =** (1) "page-fault-during-DMA" gloss vs measured anti-overlap invariant; (2) "3–4 GB/s volume floor" vs native ~8 GB/s read (floor measured only via custom readers); (3) I-1 vs ring get_tensor wall/rate attribution anomaly; (4) the 0.9–1.7 s saving estimate round-trip, all simulation — three measured pipelines showed ≤ 0 hidden overlap; (5) minflt "0/0" as residency proof is a gVisor artifact; (6) "COW" label corrected to allocator warm-up
- **classification =** RESOLVED-WITH-ONE-MEASUREMENT-ANOMALY
- **reason =** The physical model (read faults payload; H2D is clean DMA; serial) is established by convergent direct evidence (timing invariant, byte reconciliation, Gate-2 host-block counterfactual, safetensors source). Only the internal attribution of the I-1 read wall (faults inside get_tensor calls vs surrounding probe path) differs between two runs and cannot be fully reconciled from reports; it does not affect any conclusion about the native path.
