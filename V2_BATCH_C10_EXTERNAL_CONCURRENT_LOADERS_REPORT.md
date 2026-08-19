# V2 Batch C10 — External Concurrent Loaders Report

**Lane:** Concurrent Batch-C. **Date:** 2026-08-15
**Branch:** main only. No branch/worktree. **Commit:** none. **Deploys:** 0. **Modal runs:** 0.
**C9 exclusively owns remote benchmarking.** All findings from primary sources (upstream repos/source, PyPI, wheels, release notes, maintainer issues) + isolated local import verification of fastsafetensors 0.3.3. Nothing wired into ComfyUI. No unrelated tree changes made.

---

## Stop-condition application

| Candidate | Rejected? | Reason |
|---|---|---|
| vLLM/SGLang runtimes | REJECT | requires replacing ComfyUI as inference runtime |
| GDS-only loaders | n/a | GDS absent on target (`/proc/driver/nvidia-fs` missing); no candidate requires it |
| PyTorch DCP | REJECT | requires checkpoint conversion before every use; can't read standalone .safetensors |
| safetensors 0.8.0 pread backend | REJECT as candidate | sequential one-thread per-tensor pread — same mechanism already tested; usable only as a control (its pinned-DMA CUDA path is a minor win) |
| Run:ai / fastsafetensors / InstantTensor | ACCEPT | all operate standalone, no GDS, no vLLM, plain safetensors in → plain state_dict of torch.Tensor out |

## Required fields

- **report path =** `V2_BATCH_C10_EXTERNAL_CONCURRENT_LOADERS_REPORT.md` (this file)
- **changed files =** `tools/c10_loader_api_probe.py` (new, benchmark adapter reference), `V2_BATCH_C10_EXTERNAL_LOADER_SURVEY.md` (new, full survey with sources), this report. No other files touched.
- **commit = none** · **deploys = 0** · **Modal runs = 0**

- **RunAI usable standalone =** YES — `pip install runai-model-streamer` (0.16.1, Apache-2.0, prebuilt C++ wheel, torch>=2.0,<3.0 only; Linux-only). `SafetensorsStreamer().stream_file(path, device=...)` + `get_tensors()` on a bare `.safetensors`; no Run:ai platform, no API key, no vLLM, no sidecar files.
- **RunAI no-GDS path =** THE DESIGN — GDS/cuFile does not exist anywhere in the codebase (no detection, no fallback, no symbols). C++ pool of `RUNAI_STREAMER_CONCURRENCY` (default 16) threads, each with its own fd, buffered `read()` in 2 MiB chunks into a host staging buffer; Python iterator hands completed tensors to the caller, `.to(device)` per tensor overlaps H2D with continued reads. No O_DIRECT/AIO/io_uring.
- **RunAI same-file concurrency =** YES, definitive — `Assigner` splits the single 12.31 GB file's byte range across 16 worker slices (~770 MB each) by bytes, not by tensor (assigner.cc:78-153; per-tensor atomic completion counter). Verified in 0.16.1 source.

- **fastsafetensors usable =** YES — `pip install fastsafetensors==0.3.3` (IBM Foundation Model Stack, Apache-2.0, dep: typer only, no safetensors dep; prebuilt manylinux + win_amd64 wheels; import verified locally on Windows). `fastsafe_open(filenames=[f], device="cuda:0", nogds=True)` → `get_tensor(k)` torch.Tensor (zero-copy DLPack view of device buffer); BF16, single file, single GPU. Direct-to-CUDA without GDS.
- **fastsafetensors no-GDS =** N concurrent `pread(2)` on ONE shared fd → per-thread pinned bounce slices (`cudaHostAlloc` pool, bbuf_size_kb × max_threads = 16 MB × 16 = 256 MB) → `cudaMemcpy` H2D per 16 MB chunk (ext.cpp `nogds_file_reader::_thread`). GDS auto-detect falls back with warning.
- **fastsafetensors expected advantage =** raises I/O queue depth to N threads on a single file — but ONLY if `max_copy_block_size` is lowered below file size (default 16 GiB ⇒ exactly ONE reader thread for 12.31 GB; verified signature locally). Tuned (1 GiB block, 16 threads): their no-GDS measurements 1.91–6.02 GB/s vs 1.01–1.28 GB/s mmap (2.6–4.7×); direct-to-CUDA avoids the final CPU→GPU pass. Caveats: whole-file 12.31 GB VRAM buffer (or bound via `max_batch_bytes`), open issue #94 (memory retention on unified memory), tensors are views (clone).

- **InstantTensor usable standalone =** YES — `pip install instanttensor` (0.1.9, scitix, Apache-2.0, dep: torch>=2.8.0 only; prebuilt manylinux wheels; Linux-only). Standalone is the primary documented usage; `safe_open(path, framework="pt", device=0, copy=True)` → `tensors()` yields CUDA torch.Tensor. ComfyUI usage exists independently (ComfyUI-InstantTensorLoaders). Alpha maturity (first release 2026-03).
- **InstantTensor non-GDS path =** io_uring O_DIRECT (default, kernel≥5.15) or libaio O_DIRECT fallback; deep async queue (io_depth default 512 × 8 MiB chunks ≈ 4 GiB VRAM + 4 GiB pinned host staging, tunable via INSTANTTENSOR_IO_DEPTH) with `cudaMemcpyAsync` H2D on private streams and event-based publish — read/DMA/compute overlap. GDS (CUFILE backend) strictly optional opt-in. Risk: `cudaHostRegister` unsupported on our target (rc=304) and O_DIRECT on the network volume is unproven; layout validation requires contiguous offsets + non-increasing element sizes (true for our file).

- **safetensors pread backend available =** YES since 0.8.0 (2026-06-09) — `safe_open/load_file(..., backend="pread")`, keyword-only; sequential per-tensor pread(2); pinned-CUDA async DMA path for `device="cuda"` regardless of backend; parallel_pread exists only for Apple-MPS. **No parallelism on Linux/CUDA** (open PR #822 unmerged). No O_DIRECT/io_uring ever shipped.
- **safetensors version requirement =** `safetensors>=0.8.0` for `backend="pread"` (local env is 0.5.3 — no backend param). Not a candidate; control only.

- **best candidate =** **Run:ai Model Streamer** (runai-model-streamer 0.16.1)
- **second-best candidate =** **fastsafetensors** 0.3.3

- **remote benchmark adapters ready =** YES — `tools/c10_loader_api_probe.py` implements the exact contract (`loader_name`, `setup()`, `load_exact_file_to_cpu_or_gpu()`, wall, bytes, `tensor_hash_check()`, `cleanup()`) for: `baseline_mmap` (mirrors comfy.utils.load_torch_file), `baseline_preadv` (in-tree single-thread floor), `runai`, `fastsafetensors`, `instanttensor`, `safetensors08_pread` (control). Per-run JSON `{loader, ok, wall_ms, decimal_GBps, bytes_read, tensor_count, tensor_hash, error, meta}`; validity = bytes == expected data size, 453 tensors, hash equality vs baseline; cold/warm semantics + optional root drop_caches; C9-style CLI (`--loader/--file/--device/--repeats/--out-json`).
- **exact packages/versions =** `runai-model-streamer==0.16.1` (Linux, torch>=2.0,<3.0); `fastsafetensors==0.3.3` (manylinux; runtime dep typer; torch lazy); `instanttensor==0.1.9` (Linux, torch>=2.8.0); `safetensors==0.8.0` (upgrade from 0.5.3, control only). Local env: Python 3.11.9 / torch 2.8.0+cu128 / safetensors 0.5.3.
- **estimated integration risk =** LOW for Run:ai (one context manager; plain state_dict out; zero-copy views require clone-on-bind); LOW-MEDIUM for fastsafetensors (tuning-sensitive `max_copy_block_size`, 12.31 GB VRAM file buffer, clone-before-close); MEDIUM-HIGH for InstantTensor (Alpha, staging budget vs ComfyUI VRAM, cudaHostRegister-unsupported target, O_DIRECT-on-volume unproven). All three feed `load_model_weights(assign=True)` with no ComfyUI core modification. Fundamental caveat: all are two-pass read→DMA designs vs the native single-pass mmap page-in-during-DMA; they win only if concurrent reads exceed ~5.3 GB/s cold (volume floor ~3–4 GB/s single-thread) AND read/H2D overlap — this is the empirical question the shootout answers.

- **classification =** 1. Run:ai Model Streamer — RECOMMENDED for shootout (highest non-GDS design maturity, same-file 16-way concurrency, read/H2D overlap, zero extra risk). 2. fastsafetensors — RECOMMENDED for shootout (tuned; direct-to-CUDA zero-copy). 3. InstantTensor — WATCHLIST (best raw I/O engine; block on maturity + O_DIRECT/staging probes). 4. safetensors 0.8.0 pread — control only. 5. PyTorch DCP — rejected (conversion required).
- **recommended remote shootout =** `runai` vs `fastsafetensors` (tuned) vs `baseline_mmap` vs `baseline_preadv`, on the exact 12.31 GB file, single GPU, cold (fresh container + drop_caches) × 3 and warm × 2, device cuda:0, hash-verified; Run:ai with `RUNAI_STREAMER_CONCURRENCY` 8/16/32 sweep, fastsafetensors with `--max-copy-block-size 512MiB/1GiB --max-threads 8/16`. Optional second round: InstantTensor with `INSTANTTENSOR_IO_DEPTH` 16/32/64 and backend URING vs AIO_BUFFERED. Pass = any loader whose total load wall < native mmap wall (~3350 ms node wall / ~2320 ms H2D) with identical tensor hashes, without touching ComfyUI core.
- **reason =** The in-tree single-thread preadv already lost to native (4.07 GB/s full-file vs mmap's page-in-during-DMA). The only loaders that can plausibly beat native on this stack are those raising intra-file I/O queue depth above ~5.3 GB/s cold and overlapping H2D with reads — Run:ai (16 same-file reader threads + completion-driven overlap, no GDS in design, Apache-2.0, active) and tuned fastsafetensors (N-pread → pinned bounce → direct CUDA, Apache-2.0, IBM-maintained) are the two production-grade, low-risk options; InstantTensor's deeper engine is real but its Alpha status and target-environment mismatches (cudaHostRegister unsupported, O_DIRECT on network volume, 4 GiB staging) put it on the watchlist rather than the primary shootout.
