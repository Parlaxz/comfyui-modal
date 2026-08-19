# V2 Batch C10 — External Concurrent Loader Survey

**Lane:** Concurrent Batch-C (C9 owns remote benchmarking — no Modal runs performed here)
**Date:** 2026-08-15
**Scope:** Determine which production-grade external loaders can load the exact ZImage safetensors model without GDS and without adopting vLLM/SGLang as the inference runtime.
**Branch:** main (no branch/worktree). **No commit. No deploy. No Modal run.**
**Method:** primary sources only (upstream repos, source code, wheels, PyPI metadata, release notes, maintainer issues). Local isolated inspection where allowed.

---

## 0. Baseline facts (from in-repo evidence, V2_BATCH_C6_*, V2_SINGLE_PASS_FAST_DISK_LOADER_REPORT)

| Fact | Value |
|---|---|
| Exact file | `z_image_turbo_bf16.safetensors`, `/root/models/diffusion_models/` on Modal volume `comfyui-models` (GCP us-east4) |
| Size / tensors / dtype | 12,309,817,472 B (12.31 GB) / 453 / BF16, model_type Lumina2 (NextDiT) |
| Target | single GPU, RTX PRO 6000, CUDA 13.0 |
| Current production reader | ComfyUI `comfy.utils.load_torch_file` → `safetensors.safe_open(framework="pt")` + per-key `get_tensor` (mmap-backed views, `DISABLE_MMAP=False`), single-threaded, page-fault-driven; params bound via `load_model_weights(assign=True)` |
| Measured native baseline | read materialize ~962.9 ms median (~12 GB/s warm); full H2D pass 2320.9 ms ≈ 5.3 GB/s; UNETLoader node wall 3353.93 ms median |
| Single-thread preadv (in-tree, gated OFF) | 6.6–14.0 GB/s first ~1.5 GB but 4.07 GB/s full-file (3021.9 ms); serial pipeline 4839.9 ms vs native 4605 ms → FAIL |
| Volume cold full-file read floor | ~3–4 GB/s (network-attached volume) |
| GDS | **Absent**: `libcufile` present but `/proc/driver/nvidia-fs` absent → GDS_SUPPORTED_ON_MODAL_VOLUME=NO |
| cudaHostRegister | **Unsupported** (rc=304) on target |
| Local env (this machine) | Python 3.11.9, torch 2.8.0+cu128, safetensors 0.5.3, Windows |

Key architectural insight: the native path is **single-pass** — mmap page-in happens during the H2D DMA, so read and copy overlap implicitly. A two-pass loader (parallel read → host buffer → H2D) only wins if its concurrent reads exceed the ~5.3 GB/s H2D rate and the passes overlap. This is exactly what the three external candidates attempt.

---

## 1. Candidate: NVIDIA Run:ai Model Streamer

Repo: `github.com/run-ai/runai-model-streamer` (still under run-ai org; verified). PyPI: `runai-model-streamer` 0.16.1 (2026-07-13). Apache-2.0.

### Installation
- `pip install runai-model-streamer` — prebuilt C++ core `libstreamer.so` shipped in wheel; **no build step**. Torch `>=2.0,<3.0` + numpy + humanize only. **Linux-only** (manylinux2014 x86_64/aarch64; POSIX `fcntl`/`read`). No CUDA toolkit needed (streamer has no CUDA code). S3/GCS/Azure are optional extras (`[s3]` etc.).
- **GDS: does not exist anywhere in the codebase** — no cuFile, no GDS detection, no fallback. The non-GDS path IS the design. No vLLM/SGLang requirement; standalone; no Run:ai platform/API key.

### Input
- Standard `.safetensors` accepted directly (header parsed in-process via `struct.unpack` + JSON; validated). One-file model supported. Bare file, no sidecar/package format.
- **Same-file concurrency: YES, definitive.** `Assigner` (cpp/streamer/impl/assigner/assigner.cc:78-153) coalesces the file's contiguous tensor ranges into one transfer, then splits **by bytes** across `min(total/2MiB, concurrency)` worker slices. Default `RUNAI_STREAMER_CONCURRENCY=16` → a 12.31 GB file gets 16 workers × ~770 MB slices of the SAME file. Each worker batch opens its **own fd** (`::open(path, O_RDONLY)`), seeks once, reads sequentially in **2 MiB buffered `read()` chunks** (no O_DIRECT, no fadvise, no io_uring). Tensor granularity matters only for completion accounting (atomic per-tensor counter).
- Queue depth: thread pool = concurrency env var (16 FS / 8 S3 default). Block size: fixed 2 MiB (not configurable). Direct target device: `stream_file(path, device="cuda:0")` — each yielded tensor is `.to()`-copied H2D, overlapping with continued reads. No GDS path exists at all (comment in file_streamer.py: "for future GDS/CUDA support we will need to move the tensor to the device"). Pinned bounce: OS page-cache buffered host staging buffer (default `RUNAI_STREAMER_MEMORY_LIMIT` 40 GB).

### Output / integration
- `SafetensorsStreamer` context manager: `stream_file/stream_files(path, device=...)` then `get_tensors()` yields `(name, torch.Tensor)` **zero-copy views** of the staging buffer as each tensor completes (BF16 → `torch.bfloat16`). No state_dict return; `dict(iter)` builds one. Tensors are views → clone before buffer reuse/close.
- ModelPatcher path: `dict(get_tensors())` is a plain state_dict of CPU (or CUDA) tensors → `load_model_weights(assign=True)` binding works unchanged. **No ComfyUI core modification required.**

### Non-GDS usefulness
The entire product is a no-GDS loader: concurrent same-file reads (queue depth 16 via OS threads) + read/H2D overlap via completion iterator. Run:ai's own benchmarks (15 GB Llama): concurrency 1→16 gives 47.56→14.34 s on 1 GiB/s GP3 SSD and 43.71→7.53 s on IO2 SSD (≈3.3–5.8×). Note: at concurrency 1 it is not faster than a single-threaded loader, and it cannot beat a hand-tuned 16-thread pread by much — its advantages are the parsing/completion pipeline and zero-copy views, not a fundamentally different I/O mechanism.

### Maintenance
Active (last push 2026-08-10), 339 stars, ~monthly releases since 0.5.0 (2024-08). 35 open issues. Master (post-0.16.1) adds ring buffers + multiple in-flight submissions (not yet shipped). Known caveats: Linux-only; default memory limit 40 GB; clone tensors if buffer limited.

---

## 2. Candidate: fastsafetensors (IBM Foundation Model Stack)

Repo: `github.com/foundation-model-stack/fastsafetensors` (NOT agwa/ — that 404s). PyPI: `fastsafetensors` 0.3.3 (2026-07-07). **Apache-2.0** (not AGPL — verified from pyproject and every source header).

### Installation
- Runtime dep: `typer` only. **Does not depend on the safetensors package** (parses the header itself). Python 3.10–3.14. Torch not declared as a dependency (lazily imported; CI uses 2.11). Prebuilt wheels: manylinux x86_64/aarch64 + **win_amd64** (verified locally: `fastsafetensors 0.3.3` imports on Windows Python 3.11). No CUDA build (dlopens libcudart/libcufile at runtime). Linux/CUDA, ROCm, Windows (DirectStorage), 3FS, unified-memory supported.
- **GDS: optional.** `nogds=True` is a first-class path; `nogds=False` auto-falls back to nogds copier if libcufile missing or GDS unsupported (with warning). No vLLM/SGLang requirement — standalone library, vLLM/SGLang are merely consumers.

### Input
- Standard safetensors accepted directly; one-file model supported; BF16 in dtype table.
- **Same-file concurrency: yes, at block granularity.** No-GDS path (traced): `NoGdsFileCopier.submit_io` (copier/nogds.py) opens **one shared fd**, allocates a device buffer for the whole data section, splits into `max_copy_block_size` blocks, one `submit_read` (→ one C++ reader thread) per block. Reader thread (ext.cpp `nogds_file_reader::_thread`): `pread(fd, buffer, l, offset)` chunks into per-thread pinned bounce slices (`cudaHostAlloc` pool, `bbuf_size_kb × max_threads` = 16 MB × 16 = 256 MB), then `cudaMemcpy` H2D per chunk. In-flight concurrency capped at `max_threads` (slot pool with join-before-reuse).
- **CRITICAL TUNING CAVEAT (verified locally):** `fastsafe_open(..., max_copy_block_size=17179869184)` — default **16 GiB** block → a 12.31 GB file yields exactly **ONE** submit_read → **one reader thread**, i.e. the same one-thread pread mechanism already tested. Must pass `max_copy_block_size=1<<30` (or smaller) to get ~12 concurrent reader threads. Queue depth = min(blocks, max_threads); block size configurable via API (not via JSON config; ParallelLoader doesn't expose it).
- Direct target device: `device="cuda:0"` allocates the file buffer in VRAM; tensors are **zero-copy DLPack views** (torch.from_dlpack) — no final CPU→GPU copy. Pinned bounce path: yes (cudaHostAlloc pool; on CPU device uses std::memcpy, no GPU needed). GDS copier: cuFile with runtime downgrade.

### Output / integration
- `get_tensor(name)` → `torch.Tensor` (clone before close — views into buffer). No load_state_dict helper; `dict(iterate_weights())` / `as_dict()` builds a state_dict. Whole-file device buffer = 12.31 GB VRAM unless bounded via `max_batch_bytes`/`device_memory_budget` (0.3.x).
- ModelPatcher path: same as above — plain state_dict of CUDA tensors, bindable with `assign=True`. No ComfyUI core modification.

### Non-GDS usefulness
Precisely "N concurrent pread(2) on one fd → pinned bounce → H2D" — raises I/O queue depth to N. Their own no-GDS measurements: 1.91–6.02 GB/s vs 1.01–1.28 GB/s mmap (2.6–4.7×). With correct block-size tuning it can beat a single-thread loader; on a single NVMe the multi-pread win is modest; real gains come from overlapping read and H2D across threads.

### Maintenance
Very active: weekly commits (last 2026-08-14), monthly releases, 5 open issues. Watch: #94 (~2× file-size memory retained after `close()` on unified-memory/GB10 — less likely on discrete GPU), #95 (vLLM integration bug), yanked 0.1.11 (regressions on vLLM). Releases tagged `prerelease: true` on GitHub.

---

## 3. Candidate: InstantTensor

Repo: `github.com/scitix/InstantTensor` (NOT tobiasbrock/ — 404s). PyPI: `instanttensor` 0.1.9 (2026-05-27). **Apache-2.0**. Development Status: Alpha.

### Installation
- Runtime dep: **`torch>=2.8.0` only** (verified pyproject). Prebuilt manylinux wheels cp310–cp314 (x86_64 + aarch64). g++ C++17 extension, **no nvcc** — CUDA symbols resolved at runtime via dlopen of already-loaded libcudart. **Linux-only.** CUDA or ROCm at runtime.
- **GDS: strictly optional opt-in** (CUFILE backend; never tried unless requested; dlopens libcufile, falls back otherwise). **No vLLM requirement — standalone is the primary documented usage** (README quickstart + tests run standalone; vLLM is one consumer). Independent ComfyUI usage exists: `redstonewhite/ComfyUI-InstantTensorLoaders` builds directly on `instanttensor.safe_open`.

### Input
- Standard safetensors; own header parser; validates contiguous `data_offsets` and non-increasing element sizes (both true for standard writers incl. ComfyUI checkpoints; other layouts hard-rejected since 2026-08-13). Single file, BF16, single GPU (device must be CUDA; multi-GPU optional via NCCL process group).
- **Non-GDS path (traced):** default backend **io_uring with O_DIRECT** (kernel ≥ 5.15, runtime-checked) or **libaio O_DIRECT** fallback; BUFFERED variants; MMAP only for tmpfs. Pipeline: `cudaMalloc` device ring buffer + `aligned_alloc` + `cudaHostRegister` pinned host staging; one SQE per thread segment submitted to a ring sized `io_depth × num_threads`; CQEs consumed on a `cuda_thread` issuing `cudaMemcpyAsync` H2D → `cudaEventRecord` → wait_thread sync → publish. Deep async queue: default `io_depth = max(512 // world_size, 3)` = **512 chunks in flight** (8 MiB each) on a single submission thread; reads parallelize across worker threads and overlap with DMA.
- Queue depth / block size: configurable (`io_depth`, `chunk_size`, `concurrency` args or `INSTANTTENSOR_*` env vars). Direct-to-GPU: yes — outputs CUDA tensors.
- **Memory staging caveat (issue #17):** defaults stage ~4 GiB VRAM + ~4 GiB pinned host during load (512 × 8 MiB); tune `INSTANTTENSOR_IO_DEPTH` down for ComfyUI. Note `cudaHostRegister` is unsupported on our target (rc=304) — the pinned staging fallback behavior on that host must be probed remotely.

### Output / integration
- `safe_open(filename, framework="pt", device=0, copy=True, ...)` context manager; `tensors()` generator yields `(name, torch.Tensor)` CUDA tensors; `copy=True` (default) → owned clones. `dict(f.tensors())` builds a state_dict → ModelPatcher-compatible with `assign=True`. No ComfyUI core modification.
- Layout constraint note: element-size non-increasing ordering is required (standard for our single-dtype BF16 file — trivially satisfied).

### Maintenance
Young: first release 2026-03, 74 commits, active (2026-08-13), 69 stars, 5 open issues (#17 staging memory + latent use-after-free in opt-in cache path; #15 S3/GDS feature request unanswered). Alpha maturity — the strongest raw I/O engine of the three (O_DIRECT + deep async queue + DMA overlap) but the least battle-tested.

---

## 4. Candidate: Hugging Face safetensors built-in backends (mmap / pread / eager)

- **Current state:** latest 0.8.0 (2026-06-09). Local env has 0.5.3 — no pread backend there. 0.8.0 adds keyword-only `backend: str = "mmap" | "pread"` to `safe_open`, `load_file`, `load_model` (PR #760, motivated by unified-memory OOMs and NFS). **Version requirement for pread: ≥ 0.8.0.**
- mmap path: `torch.UntypedStorage.from_file` (MAP_PRIVATE since 0.5.1) — lazy page-fault reads, OS readahead, no read() at open. `load_file(device="cuda")` = mmap view → `torch.asarray(..., device=cuda)` internal bounce copy (≤0.5.3); ≥0.8.0 uses explicit pinned CPU buffer + async DMA for CUDA regardless of backend.
- **pread backend trace:** sequential per-tensor `pread(2)` into fresh host buffers (Rust `read_exact_at`); for CUDA routes into the pinned-DMA path. **NO parallelism on Linux/CUDA** — the only concurrent read in the codebase is Apple-MPS-specific `parallel_pread` (≤8 workers). Open PR #822 (CUDA batching/interleaving) not merged. No O_DIRECT/io_uring ever shipped (PRs #681/#690/#692 closed unmerged). No env var to disable mmap.
- **Stop-condition analysis: REJECT as candidate** — "effectively the same one-thread Python preadv mechanism already tested". Useful only as a control/baseline (0.8.0's pinned-DMA + offset-ordered iteration are small wins, not a concurrency mechanism). 0.6.0's offset-ordered `load_file` (PR #571) gave 4.7× on some files — already part of the mmap baseline if adopted.

## 5. Candidate: PyTorch distributed checkpoint (official loader)

- `torch.distributed.checkpoint` reads only its own format (`.distcp` shards + pickled `.metadata`, or DCP-written HF-style sharded safetensors *directories*). `format_utils.py` exposes only `dcp_to_torch_save` / `torch_save_to_dcp` / `BroadcastingTorchSaveReader` (torch.save format, needs a process group).
- **Stop-condition analysis: REJECT** — requires checkpoint conversion before every use; cannot return a plain state_dict from a standalone `.safetensors` file; multi-process oriented, not single-GPU ComfyUI.

---

## 6. Benchmark adapter contract (for C9 / remote orchestrator)

Reference implementation: `tools/c10_loader_api_probe.py`. Every adapter implements:

```
loader_name
setup()                                  # lazy import + one-time init
load_exact_file_to_cpu_or_gpu() -> tensors: dict[str, torch.Tensor], wall_ns
tensor_hash_check()                      # sha256 over sorted tensor bytes
cleanup()
```

Per-run JSON: `{loader, ok, wall_ms, decimal_GBps, bytes_read, tensor_count, tensor_hash, error, meta}`. Validity: `bytes_read == expected_data_bytes` AND `len(tensors) == 453` AND hash equality vs `baseline_mmap`. Cold = fresh container + `--drop-caches-if-root` (root only); warm = second repeat same process. `baseline_mmap` mirrors `comfy.utils.load_torch_file` exactly; `baseline_preadv` mirrors the in-tree single-thread preadv floor.

Adapters ready: `baseline_mmap`, `baseline_preadv`, `runai`, `fastsafetensors` (tuned `--max-copy-block-size 1GiB --max-threads 16`; default 16 GiB block = 1 thread — do not benchmark untuned), `instanttensor` (defaults; optionally `INSTANTTENSOR_IO_DEPTH=32` to bound staging), `safetensors08_pread` (control; requires pip upgrade to 0.8.0 on the benchmark image).

---

## 7. Ranking (1 = best)

| # | Candidate | P(beat native) | Integration complexity | Extra deps | Maint. risk | ComfyUI compat | Non-GDS value |
|---|---|---|---|---|---|---|---|
| 1 | **Run:ai Model Streamer** | High (16-way same-file reads + read/H2D overlap, no GDS needed at all) | Low (pip + 1 context manager; zero-copy views; clone per tensor) | torch only (already present); C++ wheel | Low-moderate (active, 35 open issues; ring buffers not yet shipped) | High (plain state_dict) | Highest — no-GDS IS the design |
| 2 | **fastsafetensors** | Medium-High (N-pread on one fd; direct-to-CUDA zero-copy) | Low-Medium (tuning-sensitive: max_copy_block_size must be < file size; 12.31 GB VRAM file buffer or max_batch_bytes) | typer only + wheel | Low (IBM, weekly commits; #94 memory retention watch) | High | High |
| 3 | **InstantTensor** | Medium (deepest I/O pipeline: io_uring/O_DIRECT + 512-deep async + DMA overlap) | Medium (staging budget 4 GiB VRAM + 4 GiB pinned; cudaHostRegister unsupported on target needs probe; layout validation) | torch only (≥2.8) | **High (Alpha**, 5 open issues incl. memory staging + uaf in opt-in path) | High | High (but O_DIRECT on network volume unproven; page-cache bypass may hurt) |
| 4 | safetensors 0.8.0 pread | None (sequential) | Low | upgrade to 0.8.0 | Low | High | Control only — stop condition reject |
| 5 | PyTorch DCP | n/a | n/a | n/a | n/a | None | Stop condition reject (conversion required) |

**Expected gain mechanics:** all three external candidates are two-pass (read→H2D) designs; native mmap is single-pass. They win only if concurrent reads push cold volume bandwidth above ~5.3 GB/s AND read/H2D overlap. That is exactly what the remote shootout must measure (Run:ai claims 3.3–5.8× from concurrency alone on SSD).

## 8. Sources

- Run:ai: github.com/run-ai/runai-model-streamer (README, docs/src/{usage,benchmarks,installation,env-vars}.md, cpp/streamer/impl/{assigner,batch,file,workload,config}/…, streamer.cc, wheel 0.16.1 METADATA/RECORD, PyPI, GitHub API). No GDS/cuFile symbols anywhere in tree; `file_streamer.py` comment "for future GDS/CUDA support…".
- fastsafetensors: github.com/foundation-model-stack/fastsafetensors @ main (4d14349) — pyproject.toml, setup.py, fastsafetensors/{loader,common,file_buffer,tensor_factory,parallel_loader,auto_loader,config}.py, copier/{nogds,gds,base,registry}.py, cpp/ext.cpp, frameworks/_torch.py, docs/{overview,configuration,amd-perf}.md, PyPI (wheels/versions/yanked), GitHub issues #94/#95/#99/#93, releases, CLOUD 2025 paper (arXiv:2505.23072). Local isolated import verified 0.3.3 signatures on Windows.
- InstantTensor: github.com/scitix/InstantTensor @ main — README, pyproject.toml, setup.py, instanttensor/{__init__,_impl}.py, csrc/{main,loader_common,loader_io_uring,loader_io_aio,loader_io_cufile,loader_io_inmem}.cpp, docs/loader-internals.md, CI workflow (no nvcc), tests, PyPI JSON, issues #15/#17, vLLM docs integration page, ComfyUI-InstantTensorLoaders.
- safetensors: github.com/safetensors/safetensors — bindings/python/src/lib.rs (mmap/pread/pinned-CUDA/MPS), py_src/safetensors/{__init__.pyi,torch.py} (main + v0.6.2), safetensors/src/tensor.rs, Cargo.toml, PyPI release history, PRs #760/#553/#571/#822/#681/#690/#692, issues #758/#759/#728. Local 0.5.3 introspection.
- PyTorch DCP: docs.pytorch.org distributed.checkpoint docs, torch/distributed/checkpoint/{filesystem,_hf_utils,format_utils}.py.
