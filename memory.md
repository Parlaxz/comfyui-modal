# Working Memory

- Product priority: optimize **cold container behavior** for production with infrequent traffic and small early customer volume.
- Warm-container performance is not the optimization target unless it directly improves cold-container latency or cold-container stability.
- For round 1d and beyond, prioritize techniques that improve **cold start / restore-from-snapshot / first real request** behavior.
- Do **not** retry live loader seeding/priming approaches without explicit user approval:
  - no full warmup workflow execution during `startup(snap=True)`
  - no loader seeding during `startup(snap=True)`
  - no loader priming during `restore(snap=False)`
- Reason: all loader-seeding/priming branches either crashed, produced inference-tensor lifecycle errors, or regressed cold restore time too much.
- Current rule: only pursue optimizations that **do not increase snapshot restore time**.

## SIGSEGV-on-snapshot-restore — the fix that worked (June 2026)

**Problem.** Running the in-process ComfyUI backend during `@enter(snap=True)` and using
`enable_gpu_snapshot=True` produced a SIGSEGV (exit 139) at Modal's
`Restoring Function from memory snapshot` step. The previous workaround — force the
subprocess backend during snap=True and re-initialise the in-process backend in
`@enter(snap=False)` — worked but cost ~13s per restore (~5.7s Modal restore + 6.9s
in-process re-init).

**Root cause.** The SageAttention CUDA C extensions (`sageattn_qk_int8_pv_fp16_cuda`
for Blackwell SM 12.0, `sageattn_qk_int8_pv_fp8_cuda` for older GPUs) get imported
transitively when KJNodes is loaded by `nodes.init_extra_nodes()`. Their `PyInit_*`
functions call CUDA driver APIs **directly** (`cudaGetDeviceCount`, `cudaMalloc`,
kernel registration). They bypass the `torch.cuda.is_available()` / `current_device()`
monkey-patch and land GPU state in the snapshot. On restore the driver context is
fresh; the captured handles are dangling pointers → SIGSEGV.

**Fix that works** (in `comfyapp._force_cpu_during_snapshot`):
- Patch `torch.cuda.is_available` → False and `torch.cuda.current_device` → cpu
  (the original tolgaouz/modal-comfy-worker pattern — alone is **insufficient** for
  SageAttention).
- Additionally install a `sys.meta_path` finder that raises `ImportError` for any
  module matching `*_cuda` / `cuda_*` / `*_cuda_*`. This blocks the C extension
  `PyInit_*` from running during snap=True. SageAttention's `__init__.py` catches
  the `ImportError` and falls back to its Triton path. The blocker is removed in
  `finally`, so the real imports work normally on restore. `_import_sage_cuda()`
  re-imports the CUDA module with a fresh driver context after `_warmup_cuda()`.

**Restored performance.** Modal baseline restore drops from 5.7s → 2.3s; total
`restore sanity check` drops from 7.9s → 1.2s. End-to-end "Restoring Function…" →
"restore sanity check done" is ~3.5s (was 13s with the subprocess fallback).

**Key code location.** `comfyapp._force_cpu_during_snapshot` context manager —
combines the `torch.cuda` monkey-patch with the `sys.meta_path` C-extension blocker.

**Do not regress.** Any change to `_force_cpu_during_snapshot` must keep both
components. Removing the `sys.meta_path` blocker will re-introduce SIGSEGV as soon
as KJNodes (or any other custom node that loads a `*_cuda` extension) is registered.

## Current cold-start optimization decisions (June 2026)

- User explicitly rejected TeaCache / FBCache style workflow changes for this line of work.
  Do not propose or implement them unless the user reopens that decision.
- Current target is the second cold-start request after snapshot cache is warm, not the
  first post-deploy blob-cold restore.
- `ENABLE_WARMUP` is now intended to default to `1` so restore-time warmup can rebuild
  the in-process model cache from the last saved model stack / warmup workflow.
- `restore()` is allowed to do three focused things for the in-process backend:
  1. reattach GPU state and warm CUDA,
  2. select/apply SageAttention runtime policy,
  3. set `comfy.utils.DISABLE_MMAP = True` before restore-time warmup/model loading.
- Rationale for `DISABLE_MMAP=True`: force eager safetensors reads so volume I/O happens
  during model load rather than leaking into `clip_encode` / sampler compute as mmap
  page-fault overhead.
- CPU snapshot preload of 17+ GB model state dicts remains disabled. It made snapshot
  restore much slower (roughly 7.9s → 26.4s) and is still considered a bad trade-off
  for this branch.
