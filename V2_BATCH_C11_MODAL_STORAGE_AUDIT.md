# V2_BATCH_C11_MODAL_STORAGE_AUDIT

**Batch:** C (Concurrent Batch-C lane) — **Lane:** C11
**Date:** 2026-08-15
**Constraint class:** read-only audit. No mutations, no commits, no deploys, no Modal runs. C9 exclusively owns current remote execution.

---

## 1. Executive summary

- Model weights live on a **Modal Volume named `comfyui-models`**, mounted at **`/root/models`**, and are read by the unchanged ComfyUI core loader (`comfy.utils.load_torch_file`) via **mmap-backed `safetensors.safe_open`** (the "fast-disk" loader is a defer/bind wrapper around that core read; it opens no files itself).
- The volume's **generation (v1/v2) cannot be determined from code or local metadata**. All `Volume.from_name(...)` calls omit the `version=` argument (default = v1); v2 is an opt-in Beta backend. A read-only generation probe is specified below; it must be run by C9.
- **Volume v2 is not relevant to this workload's read path.** Its documented advantages are writes/commits/reloads/concurrency/metadata — not single-large-file read throughput (no read numbers are published; tree traversal is documented *slower* in v2). It is also Beta ("cannot yet guarantee that no data will be lost").
- **Image-baked weights are documented as "similar" performance to Volumes** by Modal's own model-weights guide — not faster. Bucket mounts are documented as *sequential*-read-optimized, a poor fit for an mmap range-read loader, with no published cost model.
- **The only documented faster-than-Volume disk is the container's ephemeral local SSD**, which is per-container and would require a boot-time copy of the file (the copy itself is volume-bound).
- **Repo evidence already indicates storage is not the bottleneck:** the U-Net backing A/B showed 100% anonymous RAM after load and a 5–9 s tail that is *restored-page traversal, not volume mmap/DMA*; the mmap page-in itself measured ~963 ms. Modal docs additionally state that memory snapshots do not speed up storage-bound weight loading.
- **Conclusion:** no first-party storage placement gives a plausible throughput advantage for the exact safetensors file with the loader unchanged. Storage-only experiments have bounded upside; the cheapest doc-backed one is an ephemeral-SSD copy A/B. Volume v2 migration is not justified by evidence; BucketMount is contraindicated.

---

## 2. Method

Two parallel read-only lanes (no Modal API access, no runs):

1. **Repo trace (@explorer)** — Volume creation/handles, mount points, downloader/preload code, build-time image handling, snapshot config, commit/reload logic, weight duplication check, fast-disk loader read path, existing storage evidence, benchmark harness, local Modal metadata.
2. **Docs research (@librarian)** — Official Modal docs (modal.com/docs/guide/volumes, model-weights, cloud-bucket-mounts, memory-snapshots, cold-start, scale, resources; SDK/CLI reference; official engineering blogs; official modal-client source where docs are silent). All claims below cite doc sections; the only claims sourced from client source code are labeled.

Plus a read-only helper created per mission allowance: `tools/inspect_modal_model_storage.py` (stdlib-only; default mode has zero network; `--probe` is opt-in, read-only, and flagged for C9). Verified run: clean exit, no network, mutated nothing.

---

## 3. Current storage architecture (repo ground truth)

### 3.1 Volumes

| Role | Volume name | Mount path | Referenced by |
|---|---|---|---|
| **models (weights)** | **`comfyui-models`** | **`/root/models`** | comfyapp.py:6538/7828; comfymodal_runtime/modal_app.py:263/266 |
| custom-nodes | `comfyui-custom-nodes` | `/root/custom_nodes_vol` | comfyapp.py:6541/7829; modal_app.py:264/267 |
| runtime-state | `comfymodal-runtime-config` | V1 `/root/comfymodal_runtime_state`; V2 `/mnt/comfymodal_runtime_state` | comfyapp.py:6539/6540; modal_app.py:265/268 |
| profiles (V2) | `comfymodal-v2-profiles` | `/mnt/comfymodal_profiles` | modal_app.py:277/278 |
| prompt-cache | `comfymodal-prompt-encoding-cache` | `/root/prompt_cache_vol` | comfyapp.py:6547/6548; modal_app.py:283/284 |

- All handles are `modal.Volume.from_name(...)` with `create_if_missing=True`; mounts wired through `volumes={...}` on `@app.cls` (comfyapp.py:24281-24296; modal_app.py:17446-17464) and downloader `@app.function` (comfyapp.py:8372, 8431). **No `NetworkFileSystem` / `SharedVolume` anywhere** (legacy NFS is a separate deprecated product, not the v1/v2 story).
- Weights inventory (`.model_manifest.json`, fresh count): **19 entries** — diffusion_models 7 (incl. the 12.31 GB U-Net), text_encoders 4, vae 4, clip 1, loras 1, controlnet 1, model_patches 1. Manifest-driven downloaders (`download_model_to_volume` comfyapp.py:8322, `download_model_stream` :8374, `batch_download_models` :8433) stream to the volume, `.part` → `os.replace`, then `vol.commit()`.
- **No weight duplication into Images:** nothing bakes `.safetensors`/model dirs into the image (`_image_base` comfyapp.py:7862-7927 has no model copies; only source files are baked). Weights exist only on the `comfyui-models` volume.

### 3.2 The "fast-disk" loader read path (unchanged in any proposed experiment)

- Opt-in wrapper: `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` (model_preload.py:5591-5615) — defers one eligible UNet `model.to(cuda)`, rewrites weight binding to `assign=True` (no copy), then one real `model.to(cuda)` (:6806, :6855, :6939-6940).
- The actual file read is ComfyUI core `comfy.utils.load_torch_file` (parent repo `ComfyUI/comfy/utils.py:122-167`): `safetensors.safe_open(ckpt, framework="pt", device="cpu")` — **mmap-backed lazy `get_tensor`** — or `torch.load(..., mmap=True)` for `.ckpt`; `DISABLE_MMAP` escape hatch exists (utils.py:137) and is used at snapshot capture time.
- Source path: `/root/models/diffusion_models/<file>` (volume mount). Measured: `load_torch_file` 962.9 ms; mmap page-in ~963 ms (~12 GB/s apparent); UNETLoader node wall 4550 → 3354 ms (−26%) with the fast-disk loader (V2_SINGLE_PASS_FAST_DISK_LOADER_REPORT.md).

### 3.3 Snapshot / cache configuration

- **CPU memory snapshot: GA, enabled** — `enable_memory_snapshot=True` (comfyapp.py:24291; V2 modal_app.py:17476 via `COMFYMODAL_V2_ENABLE_MEMORY_SNAPSHOT`).
- **GPU memory snapshot: Alpha, gated off by default** — `COMFYMODAL_ENABLE_GPU_SNAPSHOT` default False (comfyapp.py:450); `experimental_options={"enable_gpu_snapshot": True}` only when enabled (comfyapp.py:24295; modal_app.py:17489).
- Startup `vol.reload()` (comfyapp.py:8614-8615); commits after every download/write path (55 refs incl. async `vol.commit.aio()` modal_app.py:1546).
- Local Modal metadata: no `~/.modal` directory; `~/.modal.toml` token exists (never printed). **Nothing locally records volume IDs or generations** — `.deployed_state.json` holds app/identity hashes only; the runtime `model_volume_generation` field exists in `ModelRestoreKey` but is **never populated** (modal_app.py:1021-1023, 1052-1053).

---

## 4. Volume v1 vs v2 — determination and relevance

### 4.1 What the docs say (official, Aug 2026)

- v1 and v2 are **two different filesystem backends**, not a rename: "Because the file system implementation is completely different, there will be some significant performance characteristics that can differ from version 1 Volumes." (docs/guide/volumes)
- **v2 is Beta**: "We cannot yet guarantee that no data will be lost, so we don't recommend using Volumes v2 for mission-critical data at this time." Docs explicitly deem v2 fine for rebuildable data ("model weights, caches, and more").
- Creation syntax: CLI `modal volume create --version=2 NAME`; SDK `modal.Volume.objects.create(name, version=2)` / `from_name(name, create_if_missing=True, version=2)` / `Volume.ephemeral(version=2)`; `version` param marked "(Experimental)".
- **Migration is manual only**: "Currently, there is no automated tool for upgrading v1 Volumes to v2" — create a v2 volume and `cp -rp` or `rsync -a` (then `sync`). Reusing a deleted v1 name is dangerous (volumes are identified by opaque unique IDs).
- v1 limits: hard 500,000 inodes per Volume; "recommend keeping the count to 50,000 or less"; "latency to attach or modify a Volume scales linearly with the number of files". v2: no file-count limit; per-directory cap 262,144 files; files < 1 TiB; concurrent writers from hundreds of containers (v1 recommends ≤ 5 writers); faster commits and reloads; hard links; random-access writes no longer rewrite the whole file.
- Throughput: the only published figure is "Volumes are designed to provide up to 2.5 GB/s of bandwidth" (not version-split). **No published read MB/s or IOPS for v1 vs v2.** The only read-specific v2 note is that filesystem *tree traversal* can be slower (demand loading).
- Caching: "Volumes have caching and chunking optimizations built-in to maximize throughput" — no documented local-disk/page-cache/eviction semantics.

### 4.2 Can the current volume be identified from code/metadata? — **No**

- No volume IDs or generations persist anywhere in the repo; `model_volume_generation` is a never-populated schema field (modal_app.py:1021-1023, 1052-1053).
- **Presumption (not proof): v1** — every `Volume.from_name(...)` call omits `version=` (default UNSPECIFIED → v1 normalization), and v2 is opt-in Beta via `--version=2`; nothing in the repo or deploy pipeline passes `version=2`.
- **Exact safe read-only checks** (contact the Modal API read-only; C9-owned window only; neither mutates):
  1. `modal volume list` — but verified in official client source: output columns are Name / Created at / Created by only; **no version column even with `--json`**. `modal volume ls` lists files, not generation.
  2. SDK version-pin probe (authoritative, no creation):
     ```python
     vol = modal.Volume.from_name("comfyui-models", create_if_missing=False, version=1)
     vol.hydrate()
     # InvalidError containing "exists but has version v2" ⇒ v2; success ⇒ v1.
     # Private fallback after hydration: vol._metadata.version (VolumeFsVersion enum)
     ```
     This performs a `VolumeGetOrCreate` with creation type UNSPECIFIED (a get, not a create).
  3. `tools/inspect_modal_model_storage.py --probe` wraps check 2 for all five volumes (opt-in; prints warning; never calls mutating methods). Not run in this audit.

### 4.3 Relevance verdict for this exact workload

| v2 feature | Impact here |
|---|---|
| Faster commits/reloads | ~None — commits happen at download time only; reads dominate |
| Concurrent writers (hundreds) | ~None — effectively 1–2 writer containers (batch downloaders) |
| No file-count limit | ~None — 19 weight files; v1's 50k recommendation is far away |
| Random-access writes without rewrite | ~None — weights are written once (full-file replace) |
| **Read throughput** | **Unproven — no published numbers; v2 tree traversal documented slower** |
| Beta data-loss caveat | Risk — weights are manifest-rebuildable, so contained, but no read benefit to justify it |

**Volume v2 relevant: No (for the read path). Expected advantage: none documented. Migration complexity: manual copy of the weight set to a new volume + `from_name(version=2)` + snapshot/restore re-verification; medium effort, medium risk.**

---

## 5. Image vs Volume (model-weight storage)

- Official model-weights guide: "**We recommend storing model weights in a Modal Volume. … Performance is similar for the two methods.** Volumes are more flexible. Images are rebuilt when their definition changes … leads to unnecessary extra downloads in most cases."
- Mechanics: image layers are served by a FUSE lazy-loading file server; every file read incurs some overhead; a worker-memory cache serves popular files "usually 3–5x faster than when downloading files without a cache" (official engineering blog, Jan 2025). That cache is for **popular** (i.e., cross-user) files — a private 12 GB U-Net layer is unlikely to be a hot worker-cache entry.
- Cold-start guide: for tens-of-GB models, concurrent multi-file loading is recommended — "Concurrent IO takes full advantage of our platform's high disk and network bandwidth" (our loader design already does this).
- **Image storage advantage: none documented; parity per official guide.** Baking would additionally couple weights to image rebuild cycles (re-download per definition change) and inflate the image. Not recommended as a storage migration target.

---

## 6. Other first-party storage candidates

| Candidate | Status | Fit for this workload |
|---|---|---|
| `modal.CloudBucketMount` (S3/R2/GCS) | GA; built on mountpoint-s3, "inherits its limitations" | **Poor.** Docs: "optimized for reading large files sequentially"; arbitrary-offset (`seek`+write) unsupported; range-read performance unverified; per-request cloud costs with no published cost model; cold containers mount at start. Our loader issues mmap-driven range reads — mismatch. |
| Legacy `NetworkFileSystem` | Deprecated, "will be removed" | Not a candidate (distinct backend from Volume; `modal nfs` prefix). |
| **Ephemeral local SSD** (`ephemeral_disk=`, up to 3.0 TiB; default quota 512 GiB) | GA, first-party | **Only documented faster-than-Volume disk**: "IO latency is lower against local SSD"; dataset-ingestion guide says raw data should be staged at `/tmp` first. But it is **per-container ephemeral** — requires a boot-time copy of the file, and the copy itself is volume-read-bound. |
| /dev/shm / tmpfs tuning | — | No documented first-party guidance. |

**Other Modal storage candidate: ephemeral local SSD via `ephemeral_disk=` + boot-time staging — the only one with a documented read-path advantage, and only as an A/B arm (see §8).**

---

## 7. Cache persistence across cold containers

- **CPU memory snapshots: GA and already enabled** in this app (`enable_memory_snapshot=True`). They capture the full Linux container state (gVisor checkpoint/restore, pages preloaded into page cache on restore) and are officially positioned as the way to keep scale-to-zero cold starts fast.
- **GPU memory snapshots: Alpha** (`experimental_options.enable_gpu_snapshot`), off by default here. They capture VRAM contents *including loaded model weights* — but the docs are explicit: **"GPU Memory Snapshots do not speed up model loading from storage … if the majority of your initialization latency is spent loading weights, GPU Memory Snapshots will generally not improve your cold start times — and may even worsen them, by adding overhead."** Snapshot restore also *depends on* the volume's files still existing (deleted files ⇒ restore failures); redeploys invalidate old snapshots.
- **Page/file cache for Volume data surviving a snapshot restore: not documented** (UNKNOWN). Given the explicit "snapshots don't help storage-bound loads" warning, restored containers should be treated as doing normal volume reads.
- Repo evidence agrees (FAST_DISK_SNAPSHOT_RESTORE_REPORT.md): restore retains CLIP/VAE and anonymous state (restored RSS ≈ 12.8 GiB), **U-Net is deliberately evicted pre-capture** (`unet_present=0`); no material pre-Python restore improvement was measured. V2_UNET_BACKING_AB_REPORT.md: post-load storages are 100% anonymous `[heap]`; the 5–9 s tail is **restored-page traversal, not volume mmap/DMA**.
- **Cold-cache persistence available: partial.** Snapshots preserve non-storage init state (imports, JIT, CLIP/VAE tensors) — that is real and already in use. They do **not** preserve the U-Net read (evicted by design) and are not documented to preserve volume page cache. No warm-process strategy applies (`min_containers=0`, cold/single-use containers) — and none is needed: the storage read itself is not the dominant cost.

---

## 8. Critical question: would moving the exact safetensors file make the loader faster?

**Answer: no plausible advantage, and repo evidence says the storage read is not the dominant cost.**

1. Measured page-in ≈ 963 ms for the 12.31 GB U-Net; the 5–9 s post-load tail is restored-page traversal (anonymous memory), which is **independent of where the file lives** (V2_UNET_BACKING_AB_REPORT.md).
2. Modal publishes no placement with proven faster single-file reads: v2 (no read numbers, Beta), Image ("similar"), BucketMount (sequential-optimized; range reads unverified).
3. The only documented faster disk is ephemeral local SSD, and exploiting it requires a boot-time copy whose cost is bounded by volume read bandwidth (docs claim ≤ 2.5 GB/s ⇒ ≥ ~5 s for 12 GB — likely a wash or a loss for one-shot containers).

### Storage-migration experiments ranked by effort/risk (storage-only, loader unchanged)

| # | Experiment | Effort | Risk | Expected read gain |
|---|---|---|---|---|
| E1 | **Ephemeral SSD staging A/B**: at boot, copy the exact UNet `.safetensors` to `/tmp` (ephemeral_disk), point ComfyUI's model folder at the copy via config only (no loader code change) | Low–med (boot hook + folder config) | Low (no backend change) | Small/bounded — copy cost likely offsets SSD gain; measurable only on fully cold (non-snapshot) containers |
| E2 | **Volume v2 migration** of `comfyui-models`: create `--version=2`, copy ~19 weights, `from_name(version=2)`, re-verify snapshot/restore parity | Med (manual copy + repoint) | Med (Beta, no data-loss guarantee; weights manifest-rebuildable) | None documented for reads |
| E3 | **Bake U-Net into Image layer** | Med (image def + rebuild) | Low | None documented ("similar") |
| E4 | **CloudBucketMount** for weights | Med–high (bucket + creds + mounts) | High (sequential-optimized vs range reads; cost model unpublished) | Negative-risk |

---

## 9. Required benchmark plan (designed; NOT executed)

**Smallest valid A/B — storage placement only, UNCHANGED native fast-disk loader.**

- **Arm A (control):** current storage. U-Net at `/root/models/diffusion_models/<file>` on `comfyui-models` volume; `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1`.
- **Arm B (best alternative):** E1. Same file, same loader binary, same image build; a boot-time staging step copies the file to `/tmp/models/diffusion_models/` (container ephemeral SSD via `ephemeral_disk=`), and ComfyUI's model discovery is pointed at the `/tmp` copy **by folder-path config only** (no loader/fast-disk code changes). File deletion after run (ephemeral disk hygiene).
- **Optional follow-on arms (only if A vs B shows headroom and C9 releases the lane):** E2 (v2 volume), E3 (image-baked path). E4 excluded.
- **Identity/freshness requirements (per arm):**
  - Same app name + deployment identity recorded (`record_deployment_identity.py`); same image build hash; re-deploy per `deploy_and_run_v2_single.bat` conventions.
  - **sha256 of the UNet safetensors verified identical** on both arms before runs.
  - **Volume generation probed read-only** (`tools/inspect_modal_model_storage.py --probe`) and recorded per arm; snapshot generation recorded; snapshot/restore parity must hold (files present at capture).
  - Bit-exact output comparison across arms (existing harness assertion).
- **Harness/protocol (existing, pinned):** `deploy_and_run_v2_single.bat` (rtx-pro-6000, 12 CPU / 32768 MiB, TBASE/O0, `native_fast_disk_unet=1`, `release_gpu_after_request`) then `tools/benchmark_v2_direct.py`; `V2_BENCHMARK_RUNS=10`, `V2_BENCHMARK_GAP_SECONDS=35` cooldown; timing via `restore_timing` keys in `/history` meta (`restore_total_ms`, `remote_python_resume_wall_unix_ns`, `snapshot_callback_age_at_restore_ms`) per restore-timing-workflow skill.
- **Metrics:** command-to-response wall; `restore_total_ms`; UNETLoader node wall; `load_torch_file`/page-in time; `/proc/self/maps` anonymous-vs-file-backed classification; RSS at load.
- **Gate:** all remote execution (deploys + runs + read-only probe) is owned by C9. This plan is not scheduled.

---

## 10. Final fields

- **current model volume name:** `comfyui-models`
- **current mount path:** `/root/models`
- **current volume generation:** unknown from repo/local metadata (nothing persists IDs/generations; `model_volume_generation` runtime field is never populated)
- **current volume v1/v2 status:** presumed **v1** (all `from_name` calls omit `version=`; v2 is opt-in Beta) — **unconfirmed**; exact safe read-only probe in §4.2 (SDK version-pin probe / `modal volume list`), C9-owned
- **Volume v2 relevant:** No for the read path; advantages (commits, concurrent writers, file counts, random writes) do not apply
- **expected advantage:** none documented for single-large-file reads; Beta data-loss caveat; migration manual only
- **migration complexity:** medium (manual `--version=2` create + copy of weight set + repoint + snapshot/restore re-verification)
- **Image storage advantage:** none — official docs: "Performance is similar for the two methods"; image rebuilds re-download
- **other Modal storage candidate:** ephemeral local SSD (`ephemeral_disk=`, boot-time staging) — only documented faster disk, per-container, copy-cost-bound; CloudBucketMount contraindicated (sequential-optimized, range-read unverified, no cost model)
- **cold-cache persistence available:** partial — CPU memory snapshots GA and enabled (preserve imports/JIT/CLIP/VAE state); GPU memory snapshots Alpha and off; neither documented to preserve volume page cache; docs explicitly say snapshots don't speed storage-bound weight loading
- **snapshot can preserve useful cache state:** yes for non-storage init state (already exploited: restore retains CLIP/VAE, ~12.8 GiB RSS), no for the U-Net read (evicted pre-capture by design)
- **best storage-only experiment:** E1 — ephemeral-SSD copy A/B (A: volume read vs B: `/tmp` staging, loader unchanged), smallest valid pair, n=10, identity+sha256+generation gated
- **native loader unchanged:** yes — all arms use the current native fast-disk loader; only file location/folder config varies
- **classification:** storage placement is **not** the load-path bottleneck (prior A/B: tail is restored-page traversal, not volume I/O; page-in ≈ 963 ms); no storage change is justified by docs or repo evidence
- **remote A/B recommended:** deferred — optional, only with C9 capacity and release of the lane; E1 only; expected bounded upside (copy cost offsets SSD gain); E2/E3/E4 not justified by current evidence

---

## 11. Artifacts

- `tools/inspect_modal_model_storage.py` — new read-only helper (storage map, manifest summary, loader read-path confirmation, local metadata, generation probe wrapper; `--probe` opt-in and C9-flagged; verified run mutates nothing, no network in default mode).
- This report.
- **Commit:** none. **Deploys:** 0. **Modal runs:** 0.
