# V2 Batch C6 — Read-Only Feasibility Audit: Pipelined UNET Read -> H2D

Date: 2026-08-14
Mode: READ-ONLY. No source modified, no tests created, nothing deployed, nothing committed.
Method: 3 explorer traces (front half, back half, prior-art/telemetry) + 1 oracle synthesis, all against `main` (current).

---

## Classification

**FEASIBLE WITH BOUNDED REFACTOR — but ONLY after a new explicit decision point.**

The exact seams exist and were verified line-by-line. The refactor is bounded to the custom-node loader
(`model_preload.py`); core ComfyUI stays byte-identical. However, prior research
(`V2_UNET_READ_H2D_OVERLAP_RESEARCH.md` §14, stop-condition 6) explicitly declared D10-style chunked
read->bind->H2D pipelining OUT OF SCOPE and defined any such proposal as a **stop signal requiring a new
decision before coding**. This audit is the decision request. Do not implement without an explicit go.

- Not FEASIBLE NOW: config inference iterates the full state dict before construction; with config-from-sd
  the overlap ceiling is exactly 0.
- Not REQUIRES MAJOR LOADER REWRITE: nothing in core ComfyUI (`comfy/utils.py`, `comfy/sd.py`,
  `comfy/model_patcher.py`, `comfy/model_management.py`) needs changing; the read loop stays identical.

---

## Required summary

| Field | Finding |
|---|---|
| classification | FEASIBLE WITH BOUNDED REFACTOR (gated by prior stop-condition 6 — decision required first) |
| current full-materialization barrier | `comfy/utils.py:139` — final `sd[k] = tensor` in the `safe_open` per-key `get_tensor` loop; the complete ~12.31 GB CPU state dict exists only when `load_torch_file` returns (`utils.py:167`). Before that, config inference (`calculate_parameters` sd.py:1961, `weight_dtype` sd.py:1962, `model_config_from_unet` sd.py:1965) and bind (`load_state_dict(assign=True)`, model_base.py:348) block any H2D. |
| first safe overlap seam | Per-tensor: `_SafeOpenProxy._proxy_get_tensor` (model_preload.py:2955) as read producer → per-key assign (params share read tensors under `assign=True`) → per-param `cast_to` (`r=empty_like; r.copy_(weight, non_blocking=True)`, comfy/model_management.py:1469-1474) on the default stream. Wired at the bulk `.to()` seam `_fast_disk_replay_to` (model_preload.py:4069). |
| files/functions | Custom-node only: `comfymodal_runtime/model_preload.py` — `_SafeOpenProxy` (:2939), `_fast_disk_replay_to` (:4069), `_fast_disk_handle_bind` (:4487), `_h2d_pre_cpu_refs` (:4205). Reuses existing `cast_to` + event timing (:4239-4298). Core unchanged. |
| TWO-LANE behavior preserved | Yes. Two lanes = per-model-file preparation lane vs early-UNET activation lane (resource_telemetry.py:538 `two_lane_activation`); the pipeline lives INSIDE the prep-lane worker. Lane count and partition unchanged. Fast-disk H2D already runs outside the MutationLane FIFO (it is not a `load_models_gpu` mutation), so no lane/lock interaction is introduced. |
| estimated overlap ceiling | ~1.0–1.7 s (full read hidden under H2D; H2D 2.0–3.9 s > read 1.0–1.7 s on healthy exact-hit runs). |
| estimated realistic saving | ~0.5–1.0 s on exact-hit runs (construction/first-assign head ~50–110 ms stays serial; header parse ~1–2 ms). ~1.3–1.7 s on bad-host runs (H2D 9.2 s). ~0 net on miss runs (load already overlaps prefill; only contention shifts). Exactly 0 if config stays sd-driven. |
| recommended next implementation | Flag-gated probe sequence in `model_preload.py` under `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE` (values `probe`/`1`, default off): (1) per-tensor materialize timing; (2) wave-split H2D replay probe (behavior-preserving); (3) header-vs-sd config parity gate (mandatory); (4) interleaved single-thread read→assign→copy loop. |

---

## Trace (verified locations)

Front half:
1. Plan receipt: `modal_app.py:16116` `ExecutionPlan.from_dict` → `:16128` `_maybe_schedule_execution_unet_at_plan_receipt` (`:7524`) → `bridge.schedule_execution_unet` (model_preload.py:10236) → `coordinator.schedule_execution_unet` (:8666) → `_submit` (:8802) → `ThreadPoolExecutor(max_workers=2, "comfymodal-restore")` (:8796).
2. Read: `_load_unet` (:10822) → `nodes.UNETLoader.load_unet` → `comfy.sd.load_diffusion_model` (sd.py:2022) → `comfy.utils.load_torch_file` (utils.py:122-167). **Streaming**: `safetensors.safe_open` + per-key `get_tensor`; NOT `load_file`. mmap `load_safetensors` only when `aimdo_enabled`.
3. Materialization: `sd[k] = tensor` loop, `utils.py:139`; full dict at return (`utils.py:167`). No intermediate representation on this path.
4. Construction: sd.py:1925 `load_diffusion_model_state_dict` — `calculate_parameters` (:1961), `weight_dtype` (:1962), `model_config_from_unet` (:1965) all iterate the FULL sd; `get_model` (:2011); `load_model_weights(assign=True)` (:2016) → `load_state_dict` (model_base.py:340-355). ModelPatcher ctor (sd.py:2012-2013) touches no tensors.
5. Bind: model_base.py:348; `assign=True` ⇒ model params ARE the read tensors (no copy at bind).
6. `normal_loader_ready` (model_preload.py:10877-10928): **diagnostic only**, not a gate. Real gates: future join (`_consume_model_impl` :11492), `graph_unet_join_or_adopt` (modal_app.py:13203), `_lane.acquire("sampler")` (:13233).

Back half:
7. TWO-LANE: two parallel lanes (per-model file identity), NOT a tensor partition of the UNET. Lane A = prep (read+materialize); Lane B = `_run_early_unet_activation` (:13757) overlapping CLIP prefill.
8. H2D path A: bulk `model.to(cuda)` in `_fast_disk_replay_to` (:4069) → `ModelPatcher.load` → `patch_weight_to_device` (model_patcher.py:845) → `cast_to` (model_management.py:1449-1475): per-param `empty_like` dest then `r.copy_(weight, non_blocking=True)` on the default stream; per-module `torch.cuda.synchronize()` (model_patcher.py:1023); final sync + CUDA-event timing (:4291-4298).
9. H2D path B (flag): `transfer_module_via_pinned_staging` (unet_pinned_staging.py:43) — dedicated stream, GPU dest first (:156), per-chunk pinned staging with per-chunk `_stream.synchronize()` (single reused buffer ⇒ serialization barrier).
10. Sampler: starts only after full H2D + sync; gated by future join + ownership claim + sampler lane acquire.
11. Telemetry: read = wall clock `read_start/end` (:2100); get_model/bind = fast-disk metadata; H2D = `to_wall_ms` (monotonic) + `to_device_ms` (CUDA events) (:4239-4298). No per-tensor time series exists. Invariant `to_wall ≈ to_device` (Δ ≤ 0.08 ms) proves pages resident before copy — read and H2D are naturally serial today.

---

## Questions A–J

**A. Full CPU representation available at:** `comfy/utils.py:167` (return of `load_torch_file`), after final `sd[k] = tensor` at `utils.py:139`. Per-tensor availability is sequential in safetensors header order.

**B. Complete sd required before first H2D?** Yes today, but the dependency is not data-semantic. All pre-bind consumers are metadata-only (`calculate_parameters` needs `nelement()`; `weight_dtype` needs dtype counts; `model_config_from_unet` is key-set membership + a few shape lookups; all header-derivable). Real data barriers are bind and H2D only. This is implementation order.

**C. Incremental enumerate/transfer without semantic change?** Mechanically yes. Risks: (1) partial module states — safe because ownership/join/sampler gates fire only post-H2D; final sync must stay before future publish; (2) dtype parity — must inherit the existing no-dtype-conversion guard verbatim; (3) config-from-sd fork (D); (4) `process_unet_state_dict` (model_base.py:347) must be applied per key identically.

**D. Construction the barrier?** No — implementation order with one bounded fork. ModelPatcher ctor touches no tensors; module construction needs shapes/dtypes only (header-derivable). The fast-disk path already knows `model_key` at plan receipt (D1, modal_app.py:16116-16131); `model_manifest.py` supports identity→config lookup. The fork: header-driven config, parity-validated against the sd-derived config before any reorder.

**E. H2D for materialized storages while later storages still read?** Yes. `cast_to` is per-param with late dest allocation; host can enqueue copy *k* then read *k+1* while DMA runs. Required changes: per-key incremental bind (or `param.data = tensor` loop over the key→param map), copy scheduling (single-thread interleave or consumer thread), key→param map wired at the `_SafeOpenProxy` seam.

**F. Fight with TWO-LANE?** No. Pipeline lives inside the prep lane; lane count/partition unchanged. Premise correction: fast-disk H2D already runs outside the MutationLane FIFO (not a `load_models_gpu` mutation) — no new lock or lane. Only discipline concern is bandwidth: ~0 added contention on exact hits (no concurrent GPU work); on miss runs the same DMA bytes shift ~1.0–1.7 s earlier into the encode window (contention already measured: CLIP +39–62%, H2D +18–23%).

**G. Lifetime constraints that would make it unsafe:**
1. CPU source must outlive the non_blocking DMA — per-tensor refs until final sync (extend `_h2d_pre_cpu_refs` pattern :4205).
2. mmap views vs copied buffers on the Modal volume — must verify storage-backedness (probe I-1); mapping must not be invalidated mid-read.
3. Pinned staging uses ONE reused buffer with per-chunk sync — serializes the interleave; pipeline must bypass staging or use a buffer ring.
4. `ModelPatcher.backup` is created post-H2D (model_patcher.py:852-853) — unaffected. `unet_backing.py` frees are probe locals — unaffected.
5. Partial-module visibility — safe under existing gates; must not be loosened.

**H. GPU dests before all CPU weights loaded?** No. `cast_to` allocates `empty_like` at copy time per parameter (model_management.py:1469/1473); pinned staging likewise allocates per tensor (:156). Late, per-tensor dest allocation in both paths.

**I. Smaller first experiment preserving final object identity (ranked by risk):**
1. Per-tensor materialize timing instrumentation in `_SafeOpenProxy` (zero behavior change; proves the read wave structure).
2. Wave-based H2D replay probe: replace the single `original_to` (:4290) with N sequential subset `.to()` calls — same order, same values, same patcher/param identity, one CUDA event pair per wave; all before the existing final sync.
3. Header-vs-sd config parity validation (zero behavior change; **mandatory gate** before any reorder).
4. Interleaved single-thread pipeline probe (first real behavior change, flag-gated).

**J. Telemetry proving real overlap (not phase shift):**
- Per-tensor series `(key, storage_ptr, materialize_end_ns, copy_start_ns, copy_end_ns)`; proof = ∃k: `copy_start_k < materialize_end_{k+1}` and `total(read_start→copy_end) < read_wall + copy_wall`.
- CUDA events per wave (device timeline, host-noise immune).
- `ru_minflt` delta during the copy window (page-in during copy = direct overlap evidence).
- nvidia-smi DtoH curve showing DMA starting while read is active.
- Today's `to_wall ≈ to_device` (Δ ≤ 0.08 ms) is the anti-overlap proof; post-change expectation: `to_device < to_wall` and shrinking `read_start→copy_end`.

---

## Smallest experimental implementation plan

- **Files:** `comfymodal_runtime/model_preload.py` only (staging module untouched).
- **Flag:** `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE` (default off; `probe` = measurement only, `1` = interleaved path). Existing `COMFYMODAL_V2_*` convention.
- **Steps:**
  1. Per-tensor timing in `_SafeOpenProxy` (:2939) + wave-split replay probe at `_fast_disk_replay_to` (:4069).
  2. Header-config parity (I-3) — hard gate; flag refuses to enable `1` on mismatch.
  3. Interleaved loop under the flag: per header key `get_tensor` → `process_unet_state_dict` per key → `param.data` assign → `empty_like` dest → `non_blocking` copy on the default stream; keep the existing `finally` sync + CUDA-event timing + guard/fallback/record structure; the single `.to()` replay is bypassed only under the flag.
- **Invariants:** final object identity (same patcher, same param objects — `.data` rebinding only, as the `.to()` path does); bit-exact output (inherit the no-dtype-conversion guard); mutation-lane compliance unchanged (H2D stays outside the FIFO, exactly as today); TWO-LANE unchanged (2 lanes, same partition); single-flight future + `_LOADER_MISS` semantics unchanged.
- **Expected failure modes:** (a) per-key vs whole-dict `process_unet_state_dict` divergence; (b) header/sd config mismatch (must hard-fail the flag, never silently mis-shape); (c) CPU source freed before non_blocking DMA completes (per-tensor refs to final sync); (d) `COMFYMODAL_V2_UNET_PINNED_STAGING` interaction (single-buffer staging negates overlap — bypass or ring); (e) error-path rollback must mirror `_fast_disk_handle_bind`'s legacy-replay fallback (:4523/:4556).

---

## Uncertainty (retained)

1. Whether `safe_open.get_tensor` on the Modal volume returns copied buffers or mapping-held views is inferred from the `to_wall ≈ to_device` invariant, not directly observed — verify in probe phase 1.
2. Savings figures are estimates from the verified timing structure, not measurements; the probe phases exist to replace them with data.
3. `--disable-mmap` state in the deployed Modal runtime determines whether the mmap-view hazard (G-2) is real in production — verify before relying on it.
4. The proposal triggers documented stop-condition 6 (D10 out-of-scope). Classification assumes a new decision point authorizes the probe phases before any reorder work.

---

*No source files were created or modified by this audit.*
