# Production 009 — Phase 2A: Installed Triton Audit

Read-only audit performed against the deployed `batch-p9opt1-diag-h100`
container (deploy fingerprint `eb22ff3626a63bfa3bf227b0fee23e37e24aa98f59b33f801c70b1a5accc9a43`,
commit `ac56539`) via the new no-generation
`run_triton_introspection_probe`. It compiled nothing, built nothing, imported
no model and touched no GPU state.

This audit exists because Phase 2A forbids assuming upstream-current Triton
behaviour. It did: **the installed version invalidates several of the names and
one of the architectural assumptions in the Phase 2 brief.**

## 1. Installed stack

| item | value |
|---|---|
| Triton | **3.8.0** (`/usr/local/lib/python3.11/site-packages/triton`) |
| PyTorch | **2.14.0+cu130** |
| CUDA | **13.0** |
| Python | 3.11.5 |
| device | NVIDIA H100 80GB HBM3 |
| compute capability | 9.0 |
| target arch | **sm90** |
| SM count / memory | 132 / 85 017 624 576 B |
| `TRITON_CACHE_DIR` | `/tmp/triton_cache` |
| `HOME` | `/root` |

Triton 3.8.0 with torch 2.14.0+cu130 is **not published on PyPI or the public
`download.pytorch.org/whl/cu130` index** (PyPI tops out at `triton` 3.2.0; that
index has no `triton` or `pytorch-triton` at all). It therefore cannot be
audited from a downloaded wheel and can only be read from the container. That is
why this probe exists.

## 2. The kernel is PyTorch's, not ComfyUI's

The Phase 2 brief describes the call chain as living in ComfyUI text-encoder
code. In this image it does not. The profiler call chain

```
Llama2_.compute_freqs_cis      llama.py:815
  -> precompute_freqs_cis      llama.py:445
    -> bmm_outer_product       triton_kernels.py:77
      -> _bmm_outer_product_impl  triton_impl.py:18
```

resolves to files shipped by **PyTorch itself**:

```
/usr/local/lib/python3.11/site-packages/torch/_native/ops/bmm_outer_product/
    triton_kernels.py
    triton_impl.py
```

`triton_impl.py` registers a **Torch dispatch override for `aten::bmm` on the
CUDA key**:

```python
def _bmm_outer_product_cond(a, b, *args, **kwargs) -> bool:
    if _is_acc_tensor(a) and a.device == b.device and _is_outer_product(a, b):
        return True
    return False

tu.register_op_override("aten", "bmm", "CUDA", cond=..., impl=_bmm_outer_product_impl, ...)
```

`_is_outer_product` is true for rank-3 tensors where `a.shape[2] == 1` and
`b.shape[1] == 1` — exactly the RoPE `bmm` shape. So the Triton compile is
reached through `torch.bmm` dispatch, inside PyTorch, for **any** such call.

**Consequence for Phase 2:** this is not an application-owned kernel that the
repo can wrap. It is a PyTorch-owned native op. The only legitimate lever is
Triton's own compiled-kernel disk cache, seeded before the request.

The kernel is `_bmm_outer_product_kernel`, specialised by
`(B, M, N, dtype, BLOCK_M, BLOCK_N)` per `_bmm_log_key`, with
`_pick_block_sizes(m, n)` choosing the block sizes. Seeding therefore requires
the **exact** `(B, M, N, dtype)` that CLIP's RoPE actually uses; a different
shape produces a different key and a cache miss.

## 3. Names in the Phase 2 brief that do not exist in Triton 3.8.0

Two imports named in the brief failed against the installed package:

| brief name | result on 3.8.0 |
|---|---|
| `triton.backends.nvidia.driver.CudaUtilsDriver` | `ImportError` — no such name |
| `triton.runtime.cache.default_cache_dir` | `ImportError` — no such name |

Both must be re-derived from the installed source before 2B/2C are written. Any
implementation written against the brief's names would fail closed at import on
this image.

## 4. The JIT compile path (read from installed source)

`triton/runtime/jit.py` still owns the compile, and both relevant entry points
are present:

- `JITFunction.run(...)` — computes
  `key = compute_cache_key(kernel_key_cache, specialization, options)`, looks up
  `kernel_cache`, and **only on a miss** calls
  `self._do_compile(key, signature, device, constexprs, options, attrs, warmup)`.
- `JITFunction._do_compile(...)` — resolves
  `kernel_cache, _, target, backend, _ = self.device_caches[device]`, computes
  `cache_key = get_cache_key(src, backend, options, env_vars)`, then
  `self.compile(src, target=target, options=options.__dict__)`, and stores the
  result in `kernel_cache[key]`.
- `JITFunction.warmup(*args, grid, **kwargs)` — Triton-sanctioned pre-compile:
  `return self.run(grid=grid, warmup=True, *map(MockTensor.wrap_dtype, args), **kwargs)`.

Two things follow:

1. `run()` gates on an **in-memory** `kernel_cache` per device, but `_do_compile`
   delegates to `self.compile(...)`, which is where the **on-disk** cache under
   `TRITON_CACHE_DIR` is consulted. A pre-seeded disk cache is therefore the
   supported way to make `run()` skip `_do_compile`, and it needs no monkeypatch.
2. `JITFunction.warmup()` is the correct, public API to force a compile without
   executing the kernel. It is not a monkeypatch and not a fake shape, provided
   it is called with the **real** arguments.

## 5. What is NOT yet established

- The `CudaUtils` helper that the profile attributes ~709–987 ms to
  (`CudaUtils.__init__`, `compile_module_from_file`) was **not** confirmed on
  3.8.0, because the probe imported `CudaUtilsDriver` and that name is absent.
  The class `CudaUtils` itself may well exist under a different driver symbol.
  Its built-object location and cache key must be read from
  `triton/backends/nvidia/driver.py` in the container before 2B can be written.
- Whether the disk cache is keyed such that a pre-seeded artifact is reused
  across processes on this image is **unverified**. It has not been observed
  either way, and no claim is made.

## 6. Revised Phase 2 plan implied by this audit

1. Re-derive the helper (`CudaUtils`) API from 3.8.0 source in-container; seed it
   at image build if it needs no GPU, otherwise in a pre-inference cache-builder
   lifecycle — never by moving the compile into measured restore.
2. Seed the **exact** `(B, M, N, dtype)` kernel specialization the CLIP RoPE
   `bmm` uses, via a one-time H100 cache-builder that lets Triton produce its
   genuine artifact, persisting `TRITON_CACHE_DIR` to durable storage and
   hydrating it before inference.
3. Prove with cache-file existence and key identity that the request path no
   longer calls `_do_compile`, and only then treat Phase 2 as successful.

The prohibited shortcuts remain prohibited: no hand-rolled PTX/cubin, no
`JITFunction` monkeypatch, no cross-GPU cache, and no assuming a non-sm90
artifact is valid for sm90.

**Phase 2 is NOT complete.** 2A is done; 2B, 2C, 2D, 2E, 2F, 2G and 2H are
outstanding, and nothing has been committed as a Phase 2 treatment.