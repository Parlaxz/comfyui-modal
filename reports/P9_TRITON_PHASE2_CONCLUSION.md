# Production 009 — Phase 2 Conclusion: Triton first-use compilation

**Verdict: NOT SUCCESSFUL.** No Triton treatment is committed. The request-path
target is real and now measured; the treatment that would remove it was not
built, because the one fact it depends on could not be established without
fabricating it.

Starting SHA `95e90b26`. Lane `.slim/worktrees/p8fix`.

## What Phase 2 asked

Remove Triton's two first-use costs from the CLIP forward request path:
the `cuda_utils` helper build (~709–987 ms) and the actual kernel JIT
(`JITFunction._do_compile`, ~315–441 ms).

## 2A. The installed stack (measured, not assumed)

Phase 2A required reading the installed Triton rather than trusting upstream
behaviour. Doing so invalidated parts of the brief.

| item | measured |
|---|---|
| Triton | **3.8.0** |
| PyTorch | **2.14.0+cu130** |
| CUDA | 13.0 |
| device / arch | H100 80GB HBM3, **sm90**, 132 SMs |
| cache root | `knobs.cache.dir` = `/tmp/triton_cache` (from `TRITON_CACHE_DIR`) |
| cache layout | `FileCacheManager(key)` → `<cache_dir>/<key>/<filename>` |
| helper key fn | `make_so_cache_key(version_hash, signature, constants, ids, **kw)` |
| kernel key fn | `get_cache_key(src, backend, backend_options, env_vars)` |

Three findings changed the plan:

1. **The kernel is PyTorch's, not ComfyUI's.** The chain
   `Llama2_.compute_freqs_cis` (llama.py:815) → `precompute_freqs_cis`
   (llama.py:445) → `torch.bmm` is served by a Torch **dispatch override**
   `aten::bmm` on the CUDA key in
   `torch/_native/ops/bmm_outer_product/`, which fires for exactly the rank-3
   `a[...,1] × b[...,1,:]` RoPE shape. It cannot be wrapped by this repo; only
   Triton's own disk cache can be seeded.
2. **Two APIs named in the brief do not exist on 3.8.0.**
   `triton.backends.nvidia.driver.CudaUtilsDriver` and
   `triton.runtime.cache.default_cache_dir` both raise `ImportError`. Anything
   written against them fails closed at import.
3. **`compile_module_from_file` is module-level**, not a `CudaUtils` method.

Triton 3.8.0 is published on neither PyPI (caps at 3.2.0) nor
`download.pytorch.org/whl/cu130`, so it can only be audited in-container. A
read-only probe (`run_triton_introspection_probe`) was added for that.

## 2B/2C. Both costs confirmed on the production-shaped path

The brief allows **at most one** verification exhaustive profile answering
exactly: is `compile_module_from_file` present, and is `JITFunction._do_compile`
present. One was run (deploy `40fe7255`, trace `582bb00c`, 1 141 875 calls):

```
compile_module_from_file   build.py:193      680.925 ms wall
JITFunction._do_compile    jit.py:877        286.347 ms wall
  compile                  compiler.py:226   285.242 ms
    make_llir              compiler.py:367    58.349 ms
    make_ptx               compiler.py:480    50.251 ms
    make_cubin             compiler.py:513    47.896 ms
```

Both are real, on the snapshot-enabled deployment, and the P9 figures reproduce.
So the premise of Phase 2 holds: there is ~967 ms of first-use compilation on
the CLIP request path.

## Why the treatment was not built

Seeding the kernel cache requires the **exact** specialization the request
compiles: `(B, M, N, dtype, BLOCK_M, BLOCK_N)`. That is what forms the Triton
key. Seeding a plausible-but-different shape produces a different key and a
cache miss, and calling it "warm" would be exactly the fake-warmup the brief
prohibits.

Three independent attempts failed to obtain it:

1. **Triton's own `jit_post_compile_hook`** — not invoked on this deployment;
   `triton_compile_events` was empty on every run.
2. **The exhaustive trace** — carries no per-call `args`, so the specialization
   cannot be read from it.
3. **A runtime shape observer** wrapping the real
   `bmm_outer_product` entry point — installed but did not fire on the trial
   run.

So the builder keeps failing closed. No synthetic shape is seeded anywhere.

## Two false readings this phase had to correct

Both were in our own telemetry, not in the platform, and both would have led to
a wrong decision:

- **`request_time_helper_build` is a false positive.** It was computed as
  `not (compatible and helper_files <= files)`, which is trivially true whenever
  no manifest exists. It reported `true` on a run where `cache_file_count` was
  `0` and the suffix list was empty — while the profile independently showed a
  ~681 ms helper build. It must be derived from observed artifacts.
- **`cache_file_count == 0` was misread as "Triton caches nothing".** The
  observation is a *before* snapshot by construction
  (`exact_kernel_cache_present_before_clip_forward`), so zero files before CLIP
  forward is expected. It says nothing about what happens after.

## Production defects found and fixed

Neither was in the original scope; both were caused by this work and are fixed
with regression tests.

1. **Snapshot poisoning crash loop** (`2e7b7b39`). Triton hydration and
   `install_compile_observer()` were placed in `startup()`, which runs with
   `snap=True` during snapshot capture. This repo deliberately blocks
   CUDA-touching imports during capture, so that poisoned every snapshot: the
   captured container reported `vram_mib=81559` with the H100 present, yet every
   restored container then failed with `No CUDA GPUs are available`, in a loop
   burning H100 time. Isolated by stash-and-redeploy: with the change stashed
   the probe succeeded immediately on the same account and profile. Fixed by
   gating the observer on the flag and moving hydration/observation to
   `restore()` (snap=False).
2. **Silent flag gating** (`975aec14`). A Golden flag must be declared in three
   places; the copy probe was in two. `_runtime_env()` is a hand-written
   allowlist, so the flag never reached the container and the diagnostic
   quietly collected nothing. `tests/test_golden_flag_reaches_container.py` now
   enforces all three, confirmed to fail when the passthrough is removed.

## State left behind

- `triton_cache.py`, `restore`-time hydration, identity validation and the
  Volume all exist and are **inert**: `COMFYMODAL_GOLDEN_TRITON_CACHE` defaults
  to `0` and is consumed at `restore`, never `module_import`. No counted or
  profiled profile enables it.
- The builder refuses to run without a measured specialization.
- Local suite: **614 passed**, only the two pre-existing
  `test_rx9p_h_identity_chain` failures (which also fail on a pristine
  `production-007` tree).

## What Phase 3 of this work would be

Two things unblock the treatment, in order:

1. Make the specialization observable. The most robust route is to read it at
   the one place it is unambiguous — inside the CLIP RoPE forward, from the real
   tensors — rather than relying on a Triton hook that does not fire on this
   build.
2. Only then run the cache-builder, verify both artifacts exist, and run the
   5-request gate.

Until (1) is done, Phase 2 must not be reported as successful and no treatment
may be committed.