# V2 Batch C12 — Safetensors Layout & Sharding: Can File Structure Unlock More Modal Bandwidth?

Date: 2026-08-15 · Lane: C12 (concurrent Batch-C) · Agent: subagent-driven (librarian research + explorer codebase recon + local analysis)
Mode: analysis + tooling only. **NO model conversion, NO deploy, NO Modal runs, NO commit.**
C9 owns remote measurement; this lane is designed to combine with either C9 outcome.

---

## 1. Executive verdict

| axis | result |
|---|---|
| Physical layout understood | **YES** — real header fetched (range-request, no payload download) and fully characterized |
| Is layout limiting read bandwidth? | **NO** — data section is byte-packed with **zero gaps**; read pass is sequential in file order and bytes-proportional (C6: 50% bytes @ 54.7% wall) |
| Reordering opportunity | **LOW** — the file is already fully contiguous and read front-to-back; reordering cannot change total bytes, page count, or sequentiality. It only changes which tensors absorb page-fault attribution |
| Parallel-file (sharding) opportunity | **CONDITIONAL-HIGH** — Modal docs explicitly recommend concurrent multi-file reads to saturate volume bandwidth; observed in-project volume read varies 4–13 GB/s across runs. If C9 shows same-file QD does NOT scale, shards are the documented lever |
| ComfyUI native shard support | **NO** (deliberate non-goal; maintainer quote, Comfy-Org/ComfyUI#9354) — an adapter is required for any sharded experiment |
| Byte-identical shardability | **YES** — 453 tensors, whole-tensor cuts only, payload bytes preserved verbatim ⇒ identical state_dict ⇒ identical output SHA for the same loader semantics |

---

## 2. Evidence read (C6)

- `V2_BATCH_C6_UNET_READ_H2D_PROBE_REPORT.md` — I-1/I-2 probe: 453 tensors, 12,309,817,472 B, read wall 1535.2 ms (span 1623.7 ms incl. ~88.5 ms open/parse head), 25/50/75/100% bytes at 541.5/839.0/1184.2/1535.2 ms, read roughly bytes-proportional & slightly front-loaded; **bursty head**: first 4 tensors ≈ 305 ms with tiny tensors dominating materialization wall (cap_embedder.1.bias 7,680 B → 120.1 ms; context_refiner.0.attention.q_norm.weight 256 B → 91.0 ms); 453/453 `is_view=true` mmap-backed views; H2D 8 waves, 2467.9 ms @ 4.99 GB/s; serial chain 4605.3 ms.
- `V2_BATCH_C6_SALVAGE_V2_FEASIBILITY_AND_IMPLEMENTATION_REPORT.md` — meta-construction + preadv→pinned loader: full-file preadv **4.07 GB/s (3.02 s)** = volume-bandwidth floor; native single-pass mmap page-in-during-DMA at same floor (2.47 s); STOP decision (two-pass cannot beat one-pass on one file); cudaHostRegister unsupported; GDS absent. Header offsets used by the runtime wave builder are **data-section-relative** (data_start = 8 + header_len), matching this lane's analysis.

Also reconciled: `V2_SINGLE_PASS_FAST_DISK_LOADER_REPORT.md` (mmap page-in **~12 GB/s** in 3 runs: 962.9/938.7/1086.2 ms — faster than C6 salvage's cold preadv, i.e. volume read is variable), `FAST_DISK_SNAPSHOT_RESTORE_REPORT.md` (UNET deliberately evicted from memory snapshot; first read happens at graph-time UNETLoader **from the mounted volume** — the volume IS the fast disk).

**Observed volume-read variance band (same file, different runs): 4.07 GB/s (cold preadv) → ~8 GB/s (C6 probe read wall) → ~12 GB/s (fast-disk mmap runs).** This variance is exactly what C9's same-file QD measurement must characterize.

## 3. Model identity & file identity

- Production file: `/root/models/diffusion_models/z_image_turbo_bf16.safetensors` on Modal volume `comfyui-models` (comfymodal_runtime/modal_app.py:263,266; volume path captured in studio-api-after-failure.json).
- Source manifest entry (.model_manifest.json): `https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors` — the exact URL the deploy pipeline streams into the volume (comfyapp.py `download_model_to_volume`).
- **Identity validated**: the range-fetched HF header yields 453 tensors / payload **12,309,817,472 B** — the exact byte count C6 measured for the production file. File size = 48,928 B header + 12,309,817,472 B payload = 12,309,866,400 B. Production copy == HF artifact (same URL, same bytes).
- Family/config: **Z-Image Turbo, Lumina2/NextDiT family** — comfy detection: `cap_embedder.1.weight` + `noise_refiner.*` → Lumina-2, `dim == 3840` → ZImage branch (n_heads=30, rope_theta=256, z_image_modulation, ModelType.FLOW); `supported_models.ZImage(Lumina2)` → `model_base.Lumina2` → `comfy.ldm.lumina.model.NextDiT` (context_refiner ModuleList, t_embedder, cap_embedder, 29 transformer blocks, noise_refiner). Single dtype bf16, no fp8 — cleanly shardable.

## 4. Physical layout (real header, data-section-relative offsets)

- Header: 48,920 B JSON + 8 B prefix = **48,928 B**; data section [48,928, 12,309,866,400).
- **Contiguity: PACKED, zero gaps, zero overlaps** — validated tensor-by-tensor (first starts at 0; every next start == previous end; last end == payload total). This also independently confirms the runtime's `reconcile_header_bytes` wave check (137 waves, byte-exact).
- 453 tensors, sizes:
  - **70 tiny (<1 KiB)** — 18,048 B total (0.0% of payload)
  - **179 small (1 KiB–1 MiB)** — 4,104,704 B (0.0%)
  - **68 medium (1–64 MiB)** — 1,275,985,920 B (10.4%)
  - **136 huge (≥64 MiB)** — 11,029,708,800 B (**89.6%** of payload)
- Largest: `context_refiner.0.attention.qkv.weight` 88,473,600 B (84.4 MiB) @ 49,221,920. Smallest: `final_layer.linear.bias` 128 B.
- Alignment: **453/453 tensor starts page-unaligned** — data section begins at 48,928 B = 3,872 B past a 4 KiB boundary and every tensor start inherits the same 3,872 B residue (no intra-file padding). Each tensor's first page is shared with the previous tensor's tail; irrelevant for full-file sequential reads (all pages fault anyway), noted for completeness.
- **Physical order = lexicographic string sort of tensor names**, not numeric/module order: layer blocks appear `layers.1, layers.10..19, layers.2, layers.20..29, layers.3..9` then `noise_refiner.0/1, t_embedder, x_embedder, x_pad_token`; head is `cap_embedder.*, cap_pad_token, context_refiner.0/1`. 29 layer blocks × 13 tensors each.

## 5. Access order (read, H2D, module traversal)

| axis | order | vs physical |
|---|---|---|
| Read pass (`load_torch_file`, comfy/utils.py:135-139) | `safe_open(...)` then `for k in f.keys()` — **header order** | **identical** (mmap page-in is sequential front-to-back) |
| H2D waves (probe/meta-direct) | waves built greedily in header order from contiguous ranges | **identical** (each wave is a contiguous byte range) |
| Module traversal (`load_model_weights` / NextDiT) | numeric layer order (1,2,...,29) | **differs** — lexicographic file order vs numeric walk; but weights load by name lookup, so this mismatch costs nothing in the current pipeline |

**Layout mismatch = none in the I/O path.** Read and H2D both run in physical file order. The C6 "bursty head" (small tensors taking 50–120 ms) is cold page-in of the file head attributed to the first tensors (cap_embedder/context_refiner live at the head), plus tail faults at `noise_refiner` — page-fault attribution, not a layout defect.

## 6. Questions

**Q1. Would reordering tensors make native mmap access more sequential?** No. mmap page-in order is physical-offset order; the read pass already touches the file front-to-back. Reordering permutes which tensor pays which fault, but total bytes, page count, and sequentiality are unchanged. The only scenario where ordering matters is a future partial-consumption pipeline (I-3-style overlap) that wants specific tensors early — and even there the full file must eventually be resident (12.31 GB < 32 GB RAM), so ordering only shapes the availability CDF, not the total.

**Q2. Is safetensors already contiguous enough?** Yes — byte-packed, zero gaps, validated. Layout is not the problem for sequential bandwidth; the problem (if any) is the volume's per-read throughput and its variance (4–13 GB/s observed), which is a backend property, not a file property.

**Q3. Would 2/4/8 shards allow Modal to service independent backing objects in parallel?** Plausible and directly supported by Modal's guidance: cold-start docs explicitly say "load multiple large files concurrently… concurrent IO takes full advantage of the platform's high disk and network bandwidth" (modal.com/docs/guide/cold-start); volume read realistically 1–2 GB/s per docs, up to 2.5 GB/s advertised, but in-project runs have hit ~12 GB/s, suggesting caching layers already help single-file sequential reads. Whether independent files beat multiple ranges of one file is precisely C9's same-file QD question; the shard plans below make the file-side experiment ready for either answer.

**Q4. Compatibility impact on ComfyUI's standard UNETLoader?** Sharded files **will not load** with UNETLoader: `comfy.utils.load_torch_file` opens exactly one path (`safe_open`), `UNETLoader` (nodes.py:943-966) resolves one file via `folder_paths.get_full_path_or_raise("diffusion_models", ...)`; no `index.json`/`weight_map`/`-0000x-of-` handling exists anywhere in comfy/, comfy_extras/, or nodes.py. ComfyUI's stance is an explicit non-goal (maintainer: "I want people to stop shipping checkpoints in the annoying split format so I'm not going to support loading them", Comfy-Org/ComfyUI#9354; open issue #4256; unmerged PR #12717 merges HF shards for ComfyUI). Impact of shipping shards: **zero regression risk to the standard path** (single-file behavior untouched) — shards simply require the adapter below.

**Q5. Can a lightweight manifest/custom-node adapter reconstruct one logical state_dict without core edits?** **Yes, cleanly.** The runtime already has all primitives:
- `_c6_parse_safetensors_header` (model_preload.py:296-324) reads a header from any path — run it per shard.
- `_ring_derive_config` (model_preload.py:1314-1411) derives config from a merged logical header (merge = union of per-shard entries; no offset collisions because per-shard offsets are data-section-relative).
- `build_wave_ranges` (unet_salvage_probe.py:107-188) extends trivially from `(start, end)` to `(shard_id, start, end)`; the preadv ring (unet_meta_direct.py) opens one fd per shard.
- The existing `_install_graph_unet_loader_wrapper` fast-disk branch shows the exact integration seam (wrap `comfy.sd.load_diffusion_model`, default-off flag, fail-closed fallback to `_invoke_original`).
Adapter = a default-off loader branch + manifest (standard `index.json` or a 1-KB custom JSON mapping key→shard→offset); **no ComfyUI core edits, no production default change**. The reconstructed state_dict is a dict of mmap-backed views — exactly what `load_torch_file` produces today, so downstream (get_model, ModelPatcher, bind) is untouched.

## 7. Shard plans (BYTES, whole tensors, byte-identical)

Method (tools/c12_plan_safetensors_shards.py): partition the 453 tensors in header order at the cumulative boundary nearest each target (k·total/n), ≥1 tensor per shard, monotonic cuts. Each shard is a **contiguous byte range of the original data section** — a future splitter copies payload bytes verbatim and writes a fresh header per shard ⇒ every tensor byte-identical ⇒ SHA-identical generation for the same loader semantics. Header overhead per shard ≈ 49 KB (negligible).

| plan | shard sizes (MiB) | % of payload | balance max/min | max dev from target |
|---|---|---|---|---|
| **2** | 5872.05 / 5867.50 | 50.0 / 50.0 | **1.001** | +0.0% |
| **4** | 2961.58 / 2910.47 / 2955.53 / 2911.97 | 25.2 / 24.8 / 25.2 / 24.8 | **1.018** | +0.9% |
| **8** | 1506.33 / 1455.25 / 1455.24 / 1455.24 / 1500.28 / 1455.25 / 1455.24 / 1456.74 | 12.8 / 12.4 ×5 / 12.8 / 12.4 | **1.035** | +2.6% |

Boundary tensors (all cuts fall at tensor boundaries inside layer blocks — no tensor split anywhere):
- 2-shard cut: between `layers.21.feed_forward.w3.weight` and `layers.21.ffn_norm1.weight`
- 4-shard cuts: at `layers.14.feed_forward.w1/w2`, `layers.21.feed_forward.w3/ffn_norm1`, `layers.3.feed_forward.w1/w2`
- 8-shard cuts: `layers.10.qkv/attention_norm1`, `layers.14.feed_forward.w1/w2`, `layers.18.feed_forward.w2/w3`, `layers.21.feed_forward.w3/ffn_norm1`, `layers.26.qkv/attention_norm1`, `layers.3.feed_forward.w1/w2`, `layers.7.feed_forward.w2/w3`

Full weight_map (453 keys → shard → byte offset within shard) for all three plans is emitted by the tool (`--save-plans`, standard `index.json`-compatible shape: `metadata.total_size` + `weight_map`). Note the official sharding convention (huggingface_hub `model-00001-of-0000N.safetensors` + `model.safetensors.index.json`) uses the same shape; shard-size target is convention, not spec (HF/transformers stable default 5 GB; diffusers 10 GB; any target is valid).

## 8. Byte-identical split procedure (design only — NOT executed)

```
1. Read header (48,920 B JSON) — already done, cached in this lane.
2. For plan n, for each shard: create new file = [8-byte LE header len][JSON header
   with only this shard's tensors, data_offsets rewritten relative to 0][payload
   bytes copied verbatim from original range].
3. Copy payload with a single read+write pass (or zero-copy range copy on the
   volume host) — no tensor decode/re-encode anywhere.
4. Verify: per-tensor sha256 of payload ranges identical to source; total bytes
   per shard = plan; wave replay matches 137-wave C6 reference.
5. Deploy shards as N files on the volume (comfyui-models); production single
   file untouched.
```
Cost estimate (if ever executed remotely): one 12.31 GB read + write pass on the volume host (~2× 3–4 s at the measured floor, plus copy overhead) — cheap **relative to the experiment's value**, and never touches the production checkpoint (write to new paths).

## 9. Concurrency hypothesis & combination with C9

Decision table (C12 is file-side ready for either branch):

| C9 same-file QD result | Shard value | Recommended next experiment (C9/C13) |
|---|---|---|
| **Does NOT scale** (QD 1≈QD 4; single-file read caps ~4–8 GB/s cold) | **HIGH** — independent files are Modal's documented lever; shards = N independent backing objects, each read concurrently | A/B: 1 file vs 4 vs 8 shards, concurrent mmap/preadv reads, measure wall + GB/s (expect max-shard-time bound, ~12.31/n GB at equal bandwidth) |
| **Scales well** (QD 4 ≈ 2–3× single-stream; one file already saturates ~12 GB/s) | **LOW** — sharding adds adapter complexity without bandwidth gain | Keep single file; optionally pursue page-cache residency across requests (different axis, C6 salvage recommendation) |
| **Mixed/variance-bound** (4–13 GB/s swings dominate) | **MEDIUM** — sharding stabilizes by bounding per-object read size; worth one A/B | Single A/B run per plan, standing rule: stop at first valid run |

Existing measurement hooks make the experiment cheap: `unet_salvage_probe.py` already measures safe_open touch rates and preadv throughput; the wave-probe metadata (`unet_read_h2d_wave_probe`) already reconciles per-wave bytes; the only new remote code needed is the N-fd concurrent reader (~50 lines, default-off).

## 10. Optional layout optimization (grouping by module traversal)

**Assessed: no benefit, do not pursue.** The read pass faults pages in physical order; reordering to module order would make the mmap walk **non-sequential** (scattered faults across `layers.10` then `layers.2`...) while the model still consumes by name lookup. The current lexicographic order is already effectively "sequential" for the I/O path; module-order grouping would only hurt. The C6 measured read CDF (bytes-proportional, 50% @ 54.7% wall) shows no page-churn pathology to fix.

## 11. Tooling (delivered)

`tools/c12_plan_safetensors_shards.py` — stdlib only; no model conversion, never downloads payloads.
- Inputs: local `.safetensors` (header region only), local header `.json` (from `_c6_parse_safetensors_header`), or HTTPS URL (8-byte + header range fetch).
- Outputs: layout report (contiguity validation, size classes, alignment, first-25 order), shard plans for 2/4/8 (nearest-boundary whole-tensor packing), optional `--save-plans` JSON (index.json-compatible weight_map with per-shard offsets).
- Verified against the real production-identical header: 453 tensors, zero gaps, payload 12,309,817,472 B — reconciles with C6 wave replay (137 waves).
- Usage: `python tools/c12_plan_safetensors_shards.py --input <file|url|json> --shards 2,4,8 --save-plans plan.json`
- Missing remote input (documented): the header is not persisted anywhere in the repo (runtime parses it in-process each load). If the volume copy ever diverges from the HF artifact, capture the production header with the runtime's existing `_c6_parse_safetensors_header` (model_preload.py:296) or an equivalent 49 KB range read on the volume host and re-run the tool locally.

---

## Required artifacts / final field summary

```
report path            = V2_BATCH_C12_SAFETENSORS_LAYOUT_SHARDING_REPORT.md
changed files          = tools/c12_plan_safetensors_shards.py (new, ~300 lines, stdlib)
commit                 = none
deploys                = 0
Modal runs             = 0

current tensor count   = 453 (70 tiny <1 KiB, 179 small, 68 medium, 136 huge ≥64 MiB)
current physical order understood = YES (real header; lexicographic name order;
                          byte-packed, zero gaps; data section [48928, 12309866400))
current access order   = read: header order == physical order; H2D waves: contiguous
                          ranges in header order; module traversal: numeric (differs,
                          cost-free)
layout mismatch        = NONE in the I/O path (read/H2D sequential in file order);
                          lexicographic vs numeric only affects fault attribution

2-shard balance        = 50.0% / 50.0%  (max/min 1.001, dev +0.0%)
4-shard balance        = 25.2/24.8/25.2/24.8  (max/min 1.018, dev +0.9%)
8-shard balance        = 12.8/12.4×5/12.8/12.4  (max/min 1.035, dev +2.6%)

standard safetensors sharding usable = YES (index.json metadata.total_size +
                          weight_map; model-00001-of-N naming; each shard a valid
                          standalone safetensors file; HF/transformers read side
                          is weight_map-driven)
ComfyUI native shard support = NO (deliberate non-goal, Comfy-Org/ComfyUI#9354;
                          zero shard code in load_torch_file/UNETLoader/sd.py)
custom adapter required = YES — default-off runtime loader branch reusing existing
                          primitives (per-shard header parse, merged logical
                          header for config, (shard,start,end) waves, N-fd preadv);
                          no core edits

reordering opportunity  = LOW/none (file already contiguous + read sequentially;
                          reordering cannot reduce bytes or faults)
parallel-file opportunity = CONDITIONAL-HIGH (Modal cold-start docs: concurrent
                          multi-file reads saturate bandwidth; observed single-file
                          variance 4–13 GB/s; independent files are the documented
                          lever if same-file QD does not scale)

dependency on C9 result = STRONG for priority; plans + splitter design + adapter
                          seam are ready for either branch (decision table §9)
classification          = Layout: NOT a bottleneck (contiguous, sequential,
                          bytes-proportional). Sharding: ready, conditional value
                          pending C9 same-file QD measurement.
recommended experiment  = C9-first: same-file QD scaling (already C9's scope).
                          If QD does not scale: one bounded remote A/B of 1-file
                          vs 4-shard vs 8-shard concurrent reads (default-off
                          probe code, ~50 lines) using the byte-identical splitter
                          described in §8; stop at first valid run.
reason                  = The file's structure is already optimal for sequential
                          mmap (zero gaps, read in physical order, bytes-proportional
                          read CDF). The only remaining lever is backend parallelism,
                          which sharding targets directly and Modal documents as
                          the sanctioned mechanism; its value is gated on C9's
                          same-file QD result, which this lane's artifacts make
                          independently testable.
```

## Manual checks for the reader

1. C9 same-file QD result — the gate for whether the 2/4/8 plans become an experiment (decision table §9).
2. If the volume copy ever diverges from `Comfy-Org/z_image_turbo`'s `z_image_turbo_bf16.safetensors`, capture the production header (runtime `_c6_parse_safetensors_header`) and re-run the tool before trusting the plans.
3. The tool's URL mode requires network access to huggingface.co (range requests); the local `.json` mode works fully offline.
4. Shard plans preserve byte-identity by construction, but the first split (if authorized later) must verify per-tensor payload hashes + wave replay before any run.
5. No production change: single-file path, flags, and defaults are all untouched; only the new tool + this report were added.
