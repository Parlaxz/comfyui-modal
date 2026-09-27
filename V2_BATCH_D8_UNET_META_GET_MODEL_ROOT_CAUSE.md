# V2 Batch D8 — UNET Meta `get_model` Root-Cause (Explain the ~2.98 s Wall)

ZERO-SPEND investigation. No Modal deploy/request, no C4 execution, no paid
benchmark, no production-file edits, no commit.

| | |
|---|---|
| Evidence source | D6 remote sample: Worker-A wall ~2981 ms, `meta_get_model` ~2979 ms, worker thread CPU ~410 ms (effective cores ~0.14) |
| Local reproduction | `tools/v2_d8_get_model_forensics.py` (synthetic ZImage, header-faithful) |
| Data file | `V2_BATCH_D8_get_model_bench.json` (full per-row detail) |
| Tests | `tests/test_v2_d8_get_model_forensics.py` — 9/9 OK; adjacent `test_c8_meta_native.py` + `test_d4_forensics_reconciliation.py` 18 OK / 3 skips; py_compile OK |

---

## 1. Executive answer

**`get_model` is a ~20 ms intrinsic Python construction that is inflated to
~3 s by GIL starvation when Python-heavy threads run concurrently with
Worker-A — not by construction work, imports, allocation, native child
threads, or scheduler wait of the measured thread.**

Evidence chain:

1. **Intrinsic serial cost is tiny.** The exact production construction path
   (ZImage → `Lumina2` → `BaseModel.__init__` → `NextDiT`, 32 layers × 3840
   dim, in meta context) runs in **18–25 ms wall / ~16 ms thread CPU** on this
   host, serially, unloaded. This independently confirms the meta-direct
   pipeline header note ("meta get_model ~20 ms") — the "healthy" historical
   shape is the intrinsic shape.
2. **The D6 wall is reproducible locally as GIL starvation.** The same
   `get_model` call, run while a GIL-hungry Python worker runs concurrently,
   took **5.0–13.5 s wall** (median 11.3 s) while the construction thread's
   CPU stayed at **15–190 ms** — the exact D6 fingerprint (2981 ms wall /
   410 ms CPU). Process CPU ≈ wall × 1 core: one saturated core, the rest of
   the wall is the construction thread waiting for GIL slices.
3. **Span shape under contention is fully accounted and uniformly inflated**
   (100% accounted; every child span stretches by the same factor), i.e. the
   wall is *waiting inside each span*, not a hidden span.
4. **Every alternative factor is measured and rejected**: first-call imports
   (ratio 1.04), torch threadpool settings (no effect), gc/allocator pre-trim
   (no effect), config reuse (no effect), IO concurrency (no effect). Only
   GIL-hungry Python concurrency reproduces the ~3 s class of wall.
5. **No physical allocations**: 6.53B params / 13.05 GB logical / **0
   physical bytes**; RSS delta +1.8 MB; all params and buffers meta. The
   ~3 s is not allocator work.

**META_ROOT_CAUSE = concurrent GIL-hungry Python work (input_types_warm and
Worker-B Python phases) starving the meta-construction thread; intrinsic
construction is ~20 ms.**

Causality on the remote split: the D6 sample shows `input_types_warm`
overlapped Worker-A for 2974 of 2981 ms (scope=complete). That is concurrence
evidence, not D9's causal conclusion. What this batch proves is the
**mechanism**: a GIL-hungry peer inflates this exact call by 2–3 orders of
magnitude while thread CPU stays near-zero — and the serial call is ~20 ms.
The input_types_warm role is a **D8 supporting experiment**, not a D9 verdict.

## 2. Exact call graph

All statements source-derived (CONFIRMED). Custom-node paths relative to
`comfymodal_runtime/`; ComfyUI paths relative to the ComfyUI root.

### Scheduling → Worker-A entry

| Step | Location | Confirmed |
|---|---|---|
| `bridge.schedule_execution_unet(...)` (after prefill scheduling) | `modal_app.py:7869`, `:11978`, `:16642` | yes |
| `V2LoaderBridge.schedule_execution_unet` (docstring: overlaps UNET construction with CLIP prefill) | `model_preload.py:12749-12764` | yes |
| `_execution_unet` closure → `self._load_unet(_key)` | `model_preload.py:12815-12834` | yes |
| `_load_unet` branch table: ring / meta-direct / fastsafetensors / vanilla | `model_preload.py:13387/13407/13431/13447` | yes |
| **`_fs_try_pipeline`** (fastsafetensors gate `COMFYMODAL_V2_UNET_FASTSAFETENSORS`, default OFF) | `unet_fastsafetensors.py:798` | yes |
| Spawns Worker-A (`_worker_a`, meta construction) and Worker-B (`_worker_b`, file→CUDA) concurrently | `unet_fastsafetensors.py:932-1066` | yes |
| `_worker_a` → `_fs_meta_construct(_config, _meta_sd, _metrics, worker_ident)` | `unet_fastsafetensors.py:942` → `:401` | yes |
| Meta context: `torch.no_grad()` + `torch.device("meta")` | `unet_fastsafetensors.py:423` | yes |
| Forensics gate (default OFF): `torch.nn.Module.__init__` patch + gc callbacks | `unet_fastsafetensors.py:433-465` | yes |
| **`config.get_model(meta_sd, "")` — the timed call** | `unet_fastsafetensors.py:470` | yes |
| Post: param validation, sampling poison detect/repair, reconcile metrics | `unet_fastsafetensors.py:508-574` | yes |

### Inside `get_model` (ZImage family)

| Step | Location | Confirmed |
|---|---|---|
| `ZImage.get_model` (inherited `Lumina2.get_model` — **ignores state_dict/prefix entirely**) | `supported_models.py:1159-1161` | yes |
| `model_base.Lumina2(self, device=device)` | `model_base.py:1345-1348` | yes |
| `BaseModel.__init__`: `pick_operations(unet_config["dtype"], manual_cast, fp8, model_config)` | `model_base.py:158-161` → `ops.py:1464` | yes |
| `pick_operations` → `supports_fp8/nvfp4/mxfp8_compute` (GPU capability queries, cached) → returns `disable_weight_init` for bf16 ZImage | `ops.py:1464-1499` | yes |
| `self.diffusion_model = NextDiT(**unet_config, device=None, operations=ops)` | `model_base.py:164` → `ldm/lumina/model.py:423` | yes |
| NextDiT children: `x_embedder` Linear(16→3840); `noise_refiner` 2× `context_refiner` 2×; `layers` **32×** `JointTransformerBlock` (z_image modulation); `t_embedder` TimestepEmbedder(1024, out 256); `cap_embedder` RMSNorm+Linear(5120→3840); `final_layer` (LayerNorm affine=False + Linear(3840→16) + adaLN); `rope_embedder` EmbedND(θ=256, axes [32,48,48]) | `ldm/lumina/model.py:465-610` | yes |
| Per `JointTransformerBlock` (×36): `JointAttention` (qkv Linear 3840→11520, out Linear, q/k RMSNorm) + `FeedForward` (w1/w2/w3, hidden 10240) + 4 RMSNorm + `adaLN_modulation` Linear(256→15360) | `ldm/lumina/model.py:225-296`, `:73-215` | yes |
| `self.diffusion_model.eval()`; `force_channels_last` check; logging; `archive_model_dtypes` (module-tree dtype sweep) | `model_base.py:165-170` | yes |
| `self.model_sampling = model_sampling(model_config, FLOW)` → `ModelSamplingDiscreteFlow` — builds 1000-element sigma schedule **on meta** (the "poisoned" buffer repaired post-construction) | `model_base.py:173` → `:97-135` | yes |
| Tail: adm_channels, memory_usage_factor | `model_base.py:175-184` | yes |

Config resolution happens BEFORE Worker-A on the main thread (header-only,
no payload): `_c6_parse_safetensors_header` → `_c6_build_meta_sd` →
`unet_prefix_from_state_dict` → `state_dict_prefix_replace` →
`model_config_from_unet` (`detect_unet_config` ZImage branch
`model_detection.py:487-527`, incl. the single-tensor std<0.42 value probe)
→ `ZImage.__init__` → `set_inference_dtype` — `model_preload.py:1346-1441`.
Not part of the `get_model` wall; measured separately (`detect_ms 2.3 ms`,
`dtype_resolve_ms 0.5 ms`).

## 3. Disjoint timing accounting

Instrumented run, first construction (serial, unloaded). Spans are disjoint
by construction: each production function is wrapped at its boundary, called
exactly once per `get_model`.

```
get_model_total            wall 18.249 ms   cpu 15.625 ms   (outer window)
├── ops_selection                0.056 ms      0.0   (pick_operations)
├── diffusion_model_construct   13.479 ms      0.0   (NextDiT, all 36 blocks)
├── archive_dtypes               2.298 ms      —     (dtype sweep)
├── model_sampling_construct     1.228 ms      —     (sigma schedule)
└── residual                     1.188 ms      —     (BaseModel init tail, eval,
                                                       logging, module framework)
accounted (children sum)        17.06 ms  → 93.5 %
```

Nested attribution (informational only, never summed): 594 `nn.Module.__init__`
calls total **4.49 ms** — i.e. the framework-level module init is a small
fraction; the rest of `diffusion_model_construct` is parameter/tensor
creation, dict/modulelist bookkeeping, and C++ binding overhead. GC during
construction: 16 cycles / 1.7 ms.

Accounting constraints honored: children wall sums never exceed the parent;
`tree_disjoint_errors == []` in all runs; CPU-vs-wall is only asserted at a
2-quantum threshold because **Windows `time.thread_time()` has ~15.6 ms
granularity** — per-span CPU below ~16 ms is unreliable; total-call CPU is
the trustworthy number (and is the number D6 used, at 410 ms).

Under GIL contention the same tree stays disjoint and 100% accounted, with
every span inflated uniformly (see §5).

## 4. First-vs-steady-state behavior

Serial benchmark, fresh config per iteration (production shape), n=5:

| Metric | Value |
|---|---|
| First call wall | 21.3 ms |
| Steady median wall | 20.4 ms (min 14.5 / max 55.1 across arms) |
| First/steady ratio | **1.04 — no first-call effect** |
| Thread CPU (all rows) | ~15.6 ms (one Windows quantum) |

There is no meaningful first-call penalty once ComfyUI/torch are imported
(the harness measures imports separately; in production the CLIP prefill
lane precedes UNET scheduling, so torch is warm — `model_preload.py:12755`).

**The variance mechanism is GC churn, not cold-cache effects**: discarding
the previous iteration's 594-module model makes the next construction pay
GC: one serial row was 194 ms wall with **172 ms (88%) GC wall, 15 cycles**.
Production pays this at most once per request (one model built per request),
so it is a ~0.2 s occasional tax, not the 3 s problem.

## 5. CPU/thread attribution

| Sample | Wall | Thread CPU | Process CPU | Verdict |
|---|---|---|---|---|
| Serial construction | 18-25 ms | ~16 ms | ~16 ms | pure single-thread work; proc CPU ≈ thread CPU |
| **GIL worker concurrent** (median of 5) | **11 309 ms** | **31 ms** | ~10.2 s | proc CPU ≈ wall × 1 core: ONE core saturated by the peer; construction thread starved |
| IO worker concurrent | 17.2 ms | ~16 ms | ~16 ms | syscalls release the GIL — no inflation |
| torch threads 1 / default | 15.7 / 14.6 ms | ~16 ms | — | no threadpool effect on construction |
| D6 remote sample | 2981 ms | 410 ms | — | same fingerprint as the local GIL arm |

GIL-arm detail (one row): wall 5.04 s; process CPU 4.89 s; construction
thread CPU 187 ms; native threads flat at 30; RSS +1.8 MB. Span shape under
contention: `diffusion_model_construct` 4629 ms wall / 172 ms CPU,
`model_sampling_construct` 348 ms wall / 0 CPU — **every span stretches by
~340× while its own CPU stays unchanged**. That is waiting-for-GIL time
*inside each span*, not native child-thread work and not uncharged wall.

Interpretation per Part 6 rules:
- process CPU (≈ wall × 1 core) vs worker CPU (≈ 0.2% of wall): **not**
  parallel native construction — the saturated core is the *competitor*.
- Native thread count flat (30 before/during/after; +2 = sampler + worker).
- Conclusion: **native child-thread work: NOT supported. Blocking/descheduling
  of the measured thread behind a GIL-hungry peer: SUPPORTED.**

## 6. Allocator/meta tensor audit

| Quantity | Value |
|---|---|
| Modules | 594 |
| Parameters | 477 |
| Buffers | 1 (model_sampling sigmas, 1000 elems) |
| Tensor objects | 478 |
| Param numel | 6 526 554 688 (~6.5B) |
| Logical param bytes | 13 053 109 376 (~13.05 GB) |
| **Physical param bytes** | **0 — every param is `device=meta`** |
| RSS delta during construction | +1.8 MB (sampler, GIL arm) / +1.8 MB serial |
| Allocator/GC during construction | 16 GC cycles / 1.7 ms serial; up to 172 ms when discarding prior models |

Audit conclusions (all measured/source-supported):
- `device=meta` **does** propagate: `disable_weight_init.Linear` → `torch.nn.Linear`
  creates weights via `torch.empty` under the meta context; `reset_parameters`
  is overridden to a no-op (`ops.py:411-503`). No CPU materialization.
- No `zeros`/`empty` escapes on CPU; the only non-meta object ever present is
  the injected allow_fp16 probe tensor (a real checkpoint's value probe —
  production reads it from disk the same way).
- The single meta buffer (sigma schedule, 1000 elems) is the documented
  "poisoned" `model_sampling`; repair costs 0.2 ms (`sampling_fix_ms`).
- `param_validate` 0.67 ms; sampling poison detect 0.01 ms.
- Nothing allocator-heavy exists to optimize. 13 GB of *logical* meta space
  costs zero physical bytes.

## 7. Variance experiments

Local, behavior-preserving, each n=5 (median wall ms):

| Arm (factor) | Median | Min | Max | Effect |
|---|---|---|---|---|
| A baseline serial | 18.1 | 17.3 | 55.1 | reference |
| B **GIL-hungry Python worker** | **11 308.7** | 5039.8 | 13 488.5 | **+600× — reproduces D6 class of wall** |
| C disk-IO worker (96 MB chunked reads) | 17.2 | 16.4 | 18.5 | none |
| D torch intra-op threads 1 | 15.7 | 14.6 | 200.7 | none (construction is not parallel) |
| D' torch intra-op threads default (6) | 14.6 | 14.5 | 15.9 | none |
| E `gc.collect()` before construction | 16.0 | 15.4 | 17.1 | none |
| F allocator trim (gc + cuda empty_cache) | 16.9 | 15.6 | 53.9 | none |
| G config object reuse (vs rebuilt) | 19.1 | 17.7 | 58.7 | none |
| H cold→warm imports | ratio 1.04 | — | — | none |
| I **input_types_warm-style concurrent** (live `execution_warm.warm_classes_input_types`, 28 classes) | 30.7 | 20.0 | 72.0 | +70% locally (weak pressure locally: warm caches make the helper finish in ~10 ms; production's cold walk was 3593 ms) |

Notes:
- I is a **D8 supporting experiment only** — it reproduces the *shape* of the
  production concurrency, it does not make D9's causal conclusion.
- The faithful pressure proxy for the production warm thread is arm B
  (sustained GIL demand). Production's warm thread walked 31 classes for
  3.59 s (D6) — far heavier than the local 10 ms warm pass.

## 8. Root-cause classification

**Primary (measured, reproduced): GIL starvation of Worker-A by concurrent
Python-heavy threads.**

- Serial intrinsic cost: **~20 ms** (594 modules, 478 tensors, all meta).
- Local reproduction of the exact D6 fingerprint: same call, GIL-hungry peer
  → 5.0–13.5 s wall / ~31 ms thread CPU / proc CPU ≈ wall.
- D6 remote concurrence evidence: `input_types_warm` overlapped Worker-A
  for 2974/2981 ms (scope=complete) and Worker-B ran concurrently; the
  Python phases of both (INPUT_TYPES walks + dict construction loops) hold
  the GIL while their C++ phases (folder scans, CUDA copies) release it —
  matching the local mechanism.

**Secondary (measured, ~0.2 s class): GC churn from discarded model graphs**
— 88% GC in a spike row; occasional, per-request, not the 3 s driver.

**Rejected as contributors to the ~3 s (all measured):** imports/first-call
(ratio 1.04), torch threadpool settings, allocator behavior (0 physical
bytes), config/registry rebuilds (no effect), IO concurrency (no effect),
native child-thread construction (proc CPU ≈ wall×1, thread count flat),
CUDA calls inside get_model (ops selection is 0.06 ms; no CUDA work in
construction), checkpoint/state-dict work (ZImage `get_model` ignores the
payload entirely — `supported_models.py:1159-1161`).

Cross-host note (Part 8 constraint): historical healthy ~1.9–2.0 s vs D6
~2.98 s comparisons remain non-causal; this batch only shows the *internal
span* that must expand — here the answer is **none of the intrinsic spans
expand** (serial is ~20 ms); the whole ~3 s is external GIL starvation,
which also explains why meta-direct (unloaded main-thread construction)
measured ~20 ms in the past.

## 9. Generic optimization ranking

Ranked by expected saving × confidence ÷ risk. NOT implemented (this batch
is root-cause only).

| # | Fix | Expected saving | Confidence | Risk | Genericity |
|---|---|---|---|---|---|
| 1 | **Remove/schedule GIL-hungry work out of the Worker-A window**: run `input_types_warm` to completion BEFORE spawning A/B, or make the warm thread yield periodically (`threading`-level), or move warm to the main thread pre-scheduling | ~2.5–2.9 s exposed per request | High (mechanism reproduced; saving = the starvation window) | Low (advisory warm; ordering change only) | Any model, any loader |
| 2 | **Reduce Worker-B Python-phase GIL use** (dict/tensor instantiation loop `fastsafe_instantiate_wall_ms`), e.g. bulk-ops or defer instantiation until after Worker-A | ~0.3–1 s | Medium | Medium (touches fastsafe path) | Any model |
| 3 | **Absorb the GC tax**: `gc.collect()` at a quiet point (post-prefill, pre-workers) and/or retain the previous model graph until the next request is built (snapshot reuse) | ~0.2 s occasional | High | Low | Any model |
| 4 | **Construction template/snapshot of the immutable ZImage meta structure** (594 modules are shape-identical per checkpoint; cache the module graph + re-`Parameter` on demand) | ~15–20 ms | High | Medium (new mechanism) | ZImage family first, generic pattern |
| 5 | Preload imports/configs at boot (already effectively warm via prefill) | ~0 | High | None | — |

## 10. Expected critical-path savings (12 s budget)

Ordering (confirmed): prefill scheduling → CLIP prefill (~4.9 s sampling)
→ UNET scheduling → Worker-A (meta) ∥ Worker-B (load) ∥ input_types_warm.

- Serial meta construction ~20 ms + worst GC ~0.2 s is **fully hidden behind
  Worker-B's load window** in the normal case. Raw `get_model` wall is
  therefore NOT the critical-path concern; the **exposed** effect is the
  starvation it induces on the shared GIL and the join delay it adds when it
  finishes last.
- Fix #1 removes ~2.5–2.9 s of Worker-A wall and, because the warm thread is
  the dominant GIL consumer, also shortens Worker-B's wall and the join.
- Expected exposed critical-path effect after #1+#3: meta path ≈ 0.02–0.2 s
  (vs ~3 s), keeping the uncached-first-cold COMMAND→RESPONSE budget of 12 s
  comfortably within planning assumptions (1 + 3.5 + 4.9 + ~2.4 all-in).

## 11. Recommended next experiment

1. **Local ordering simulation** (next batch, no spend): reproduce the full
   Worker-A/B/warm triple concurrency with the harness, then A/B the three
   orderings — warm-first-then-spawn vs concurrent (current) vs warm-on-main
   — and measure the join + exposed-wall delta. This converts the mechanism
   into an ordering recommendation without touching D9's code.
2. **One remote run (later, when authorized)**: `COMFYMODAL_V2_INPUT_TYPES_WARM=0`
   with the D6-identical harness, to confirm the remote split — this is the
   D9/D6 causal test, explicitly NOT claimed here.
3. Optionally re-run the harness with `COMFYMODAL_V2_UNET_FORENSICS=1` on the
   remote host to capture `meta_gc_wall_ms` and per-class module attribution
   under real load (measurement only).

---

## Final response

```
GET_MODEL_TOTAL = 18.1 ms median serial (21.3 first / 20.4 steady); ~11 309 ms median under GIL-hungry concurrent worker (5.0-13.5 s range)
LARGEST_CHILD_SPAN = diffusion_model_construct: 13.5 ms serial (74%); 4629 ms under contention (wall-only; own CPU 172 ms unchanged)
ACCOUNTED_PERCENT = 93.5 % serial (children sum vs window; residual 1.19 ms); 100 % under contention
PROCESS_CPU_MS = ~16 ms serial; ~10 219 ms median under contention (≈ wall × 1 core — competitor's GIL use)
WORKER_THREAD_CPU_MS = ~15.6 ms serial; 31 ms median under contention (construction CPU essentially unchanged)
NATIVE_THREAD_WORK = NOT SUPPORTED (native thread count flat 30; proc CPU ≈ wall × 1; all construction CPU on the measured thread)
PHYSICAL_ALLOCATIONS = 0 bytes (477 params + 1 buffer all meta; 13.05 GB logical; RSS +1.8 MB)
FIRST_CALL_EFFECT = none beyond imports (first/steady ratio 1.04; imports warm via CLIP prefill lane)
STEADY_STATE = ~15-20 ms construction + occasional GC spikes ~0.2 s (88% GC) when prior model graphs are discarded
CONCURRENCY_EFFECT = DOMINANT: GIL-hungry Python peers inflate get_model wall 500-600x while thread CPU stays ~constant (D6 fingerprint reproduced: 2.98 s / 410 ms)
META_ROOT_CAUSE = GIL starvation of Worker-A by concurrent Python-heavy threads (input_types_warm 2974/2981 ms overlap + Worker-B Python phases); intrinsic meta construction is ~20 ms; allocation/imports/threadpool/GC/cold-cache all rejected by measurement
CONFIDENCE = HIGH for the mechanism (locally reproduced 500-600x inflation with identical CPU fingerprint; serial cost independently matches meta-direct's historical ~20 ms); remote input_types_warm split remains a D6/D9 causal question, NOT claimed here
BEST_GENERIC_FIX = schedule/remove GIL-hungry work (input_types_warm) out of the Worker-A window (run-to-completion before A/B spawn, or cooperative yielding); secondary: GC at a quiet point / retain prior model graph
EXPECTED_SAVING = ~2.5-2.9 s exposed per request on the meta path (Worker-A wall ~3 s → ~0.02-0.2 s); critical-path total stays within the 12 s budget
FILES_CREATED = tools/v2_d8_get_model_forensics.py, tests/test_v2_d8_get_model_forensics.py, V2_BATCH_D8_UNET_META_GET_MODEL_ROOT_CAUSE.md, V2_BATCH_D8_get_model_bench.json (benchmark data)
FILES_MODIFIED = none (production untouched; tool patches are process-local and restored)
TESTS = 9/9 new tests OK; adjacent test_c8_meta_native + test_d4_forensics_reconciliation 18 OK / 3 skips (real-checkpoint gated); py_compile OK
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
READY_FOR_PRODUCTION_META_FIX = YES (root cause + mechanism established; fixes are generic and ordering-only — next batch may implement #1/#3 without further investigation)
```
