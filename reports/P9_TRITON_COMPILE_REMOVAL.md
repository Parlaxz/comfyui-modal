# Production 009 — Phase 2 Triton first-use compile: completion report

**Verdict: `COMPILE_REMOVED_ROOT_NEUTRAL`.**

The compile is genuinely and deterministically removed from the measured CLIP
forward. The Golden root wall does **not** improve, because hydrating the exact
artifacts off a Modal Volume costs more than the compilation it eliminates. Do
not integrate on the micro-timing.

Lane `.slim/worktrees/p8fix`, detached HEAD.

```
START_SHA = b2bd23d585e259eb32d67473b5f18ca2d9280620
HEAD      = c724069
```

Workspace `Testing 1` (`ws_e677ab553606`), app `batch-p9opt1-diag-h100`, class
`ModalRuntimeEntrypointV2`, H100 80GB HBM3 (sm90), CPU 12. Output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` verified on
all 20 paired runs.

---

## 1. Runtime call chain (observed, not assumed)

```
Llama2_.compute_freqs_cis            (llama.py:815)
  -> precompute_freqs_cis            (llama.py:445)
  -> torch.bmm
  -> aten::bmm dispatch override (CUDA key)
       torch/_native/ops/bmm_outer_product/triton_kernels.py
  -> triton_kernels.bmm_outer_product
  -> JITFunction.run                  (caches by its own key)
  -> JITFunction._do_compile          <-- observed boundary
  -> make_llir / make_ptx / make_cubin
```

The kernel is PyTorch's, not ComfyUI's, so it cannot be wrapped from this repo.
Only Triton's own disk cache can be pre-seeded.

## 2. Exact observed specialization

Captured at `JITFunction._do_compile`, from the real tensors, on the real request:

| field | value |
|---|---|
| kernel | `_bmm_outer_product_kernel` |
| source sha256 | `c9e95e8b1eff8b052837b8d2f5e7a12d4d0626b7908f8f926751041ad5fd29c6` |
| `B_dim` | `constexpr 1` |
| `M` | `i32` = **64** |
| `N` | `i32` = **283** |
| `A_ptr` / `B_ptr` / `OUT_ptr` | `*fp32`, each `tt.divisibility 16` |
| `stride_am` / `stride_bn` / `stride_on` | `constexpr 1` |
| `BLOCK_M` / `BLOCK_N` | `constexpr 32` / `constexpr 128` |
| `num_warps` | **4** |

Cross-checked independently by the shape observer on the same run:
`B=1, M=64, N=283, torch.float32, BLOCK_M=32, BLOCK_N=128`,
`a_shape=[1,64,1]`, `b_shape=[1,1,283]`.

The specialization is **not** only `(B,M,N,dtype,BLOCK_M,BLOCK_N)`. It also
partitions on pointer divisibility-by-16 and on three `constexpr` strides. This
is why the builder drives real `torch.bmm` with the observed dimensions instead
of re-deriving a key formula.

## 3. Specialization stability

Depends on batch, and on the CLIP RoPE feature/sequence dimensions of the
resolved model. It does **not** depend on prompt text: the tensors are the
positional-frequency tensors, fixed by the model, so M/N are prompt-invariant
for a given model. It is invariant across the Golden cohort (5/5 runs produced
exactly one specialization) and **model-specific**, not universal. Nothing is
hard-coded: `build-triton-cache` refuses to run without `--specialization`, and
the runtime treats a mismatched artifact as a plain Triton cache miss.

## 4. Cache artifact identity

Triton names each artifact directory after its own cache key, so the observed
directory names *are* the cache identity — no key formula was re-derived.

| key directory | contents |
|---|---|
| `G3MEI3MRFEH6CP3FYG7BIMHG3QXLHLF7QRALHOAB75W4F35QZFBA` | `cuda_utils.cpython-311-x86_64-linux-gnu.so` (56,152 B) |
| `WV5BZZCW6JQ526LENDPXPBAY6U3X5QOP22RIKBLWO6NJ7VN35BZQ` | `.cubin` 20,968 · `.ptx` 22,013 · `.llir` 28,125 · `.ttir` 9,913 · `.ttgir` 11,991 · `.source` 20,253 · 2×`.json` |

~180 KB total. The builder independently produced **byte-identical key directory
names and artifact sizes** from the observed specialization, which is the proof
that the specialization was captured rather than guessed.

## 5. Before / after compile evidence

Paired A/B, same deployment, same instrumentation, alternating cold-Volume
control and hydrated treatment, 5 pairs per arm. Triton 3.8 routes a disk-cache
**hit** through the same `_do_compile` boundary, so the call count cannot
distinguish the two; the elapsed time can.

Overlapped-hydration cohort (deployment `7c161574`):

| arm | n | `_do_compile` ms | range |
|---|---|---|---|
| control (cold Volume) | 5 | median **242.2**, mean 244.6 | 213.2 – 278.4 |
| treatment (hydrated) | 5 | median **24.0**, mean 25.6 | 21.8 – 32.6 |

**Ranges do not overlap.** Delta −218.2 ms median / −219.0 ms mean. The
sick-host tail visible earlier (one control run at 1,315.6 ms) is eliminated;
the worst treatment run is 32.6 ms.

Earlier serial-hydration cohort (`8b2642d7`) agreed: 315.5 → 29.1 ms median,
control range 291.9–341.5 vs treatment 26.7–83.7.

## 6. CLIP forward and root wall

Overlapped-hydration cohort, medians:

| metric | CTRL | TREAT | delta |
|---|---|---|---|
| `clip_forward_total_ms` | 2190.7 | 1554.5 | **−636.1** |
| `restore_total_ms` | 906.7 | 1175.3 | **+268.5** |
| `total_entry_to_return_wall_ms` (root) | 1320.2 | 1396.2 | **+76.0** |

Serial-hydration cohort: root 1539.4 → 1404.9 (−134.6 median, +48.4 mean).

CLIP forward improves because the ~240 ms compile leaves it, but **restore pays
for it**: reading ~180 KB off a Modal Volume costs ~270–400 ms of first-touch
I/O, which exceeds the compile it removes. Overlapping the hydration with restore
work reduced that penalty from +401 ms to +269 ms, and it did not go to zero
because the Volume fetch is latency-bound, not size-bound.

Net root wall across both cohorts is within noise of zero and the sign is not
stable (−135, +76 median; +48, +528 mean). The previously estimated 0.5–0.65 s
ceiling assumed the compile could be removed for free; it cannot, because the
artifact has to be fetched.

## 7. Correctness

- Exact output SHA `3a6a0306…` on **20/20** paired runs.
- `valid=True` and `true_cold=True` on 20/20.
- No fallback or behavioural regression: Triton still owns the cache lookup, and
  a specialization mismatch is an ordinary miss, never a wrong result.
- Local suite **639 passed** (baseline 614; +25). Only the two pre-existing
  `tests/test_rx9p_h_identity_chain.py` failures remain, which also fail on a
  pristine `production-007` tree.
- Unknown specialization → canonical first-use compile plus a visible miss
  reason. New and dynamic models are unaffected.

## 8. Snapshot safety

`SNAPSHOT_CUDA_TOUCH = no`.

- All Triton work is in `restore()` (`snap=False`) or in an explicitly invoked
  remote method. Nothing Triton-related runs in `startup()`.
- Hydration runs on a daemon thread started inside `restore()` and is joined in a
  `finally` clause, so it cannot outlive a failed restore or write into a
  torn-down container.
- The observer imports Triton but compiles nothing; it only wraps `_do_compile`.
- The earlier snapshot-poisoning crash loop (`2e7b7b39`, `f357e99`) remains fixed
  and this work does not reintroduce it: no CUDA work at import, no work during
  capture.

## 9. Measurement defects found and fixed

Three silent failures, all of which had previously produced confident wrong
readings.

1. **The observation was taken before the event.** The pre-forward call site is
   the last boundary before CLIP can begin, so an empty event list there cannot
   distinguish "no compile happened" from "the compile had not happened yet".
   Phase 2 read that silence as "zero compiles". A post-forward observation was
   added; the compile was there all along.
2. **`JITFunction` instances have no `__name__`.** The observer filtered on
   `self.__name__`, which returns `''` on an instance, so the filter could never
   match — an observer that installs cleanly and records nothing. Identity now
   comes from `self.fn.__name__` or the kernel source, and the install result is
   reported in telemetry.
3. **A method on the base class is not reachable on the decorated V2 class.**
   `ModalRuntimeEntrypointV2` is built by `type()` and only methods wrapped with
   `_modal.method()` are exposed. `clear_triton_cache` raised
   `NotFoundError` until it was attached, which invalidated the first control
   attempt.

Also: `install_bmm_shape_observer` was *not* broken. It had recorded a real
specialization all along; it reported `observed_calls` captured at install time,
which is always `0`.

## 10. Treatment classification

`COMPILE_REMOVED_ROOT_NEUTRAL`.

| criterion | result |
|---|---|
| `REAL_SPECIALIZATION_OBSERVED` | **yes** |
| `EXACT_CACHE_OR_WARM_MATCH` | **yes** — byte-identical cache keys |
| `FIRST_USE_COMPILE_IN_CLIP_FORWARD` | **removed** — 242 → 24 ms, non-overlapping ranges |
| `SNAPSHOT_CUDA_TOUCH` | **no** |
| `EXACT_SHA` | **yes** — 20/20 |
| `ROOT_WALL_IMPROVEMENT` | **no** — within noise, sign not stable |

## 11. Integration recommendation

**Do not integrate.** The mechanism is correct and the compile removal is real,
but it buys nothing at the root wall and costs ~270–400 ms of restore plus a
persistent Volume, a manifest, and a build step.

If this is revisited, the only route that can pay is removing the Volume fetch,
not removing the compile:

1. **Bake the artifacts into the memory snapshot.** Populate
   `/tmp/triton_cache` during snapshot capture so restore needs no fetch at all.
   This is the only variant where the ~240 ms saving survives. It requires
   proving that writing these specific files during capture does not poison the
   snapshot — the failure mode that already bit this lane once.
2. Only if (1) is unsafe, leave the Triton cache alone. The ~240 ms is small
   against a 1.3–1.8 s root wall and well inside the host-sickness variance
   Phase 1 quantified.

## Commits

| SHA | content |
|---|---|
| `0bfc666` | observe the real compile request at `_do_compile` |
| `a496e1d` | compile duration + `--clear-only` cold-Volume control |
| `e81828e` | attach `clear_triton_cache` on the decorated V2 class |
| `8cf19f1` | drop the duplicate `build_triton_cache` attach |
| `c724069` | overlap hydration with restore work |

Not merged, not promoted, no tags moved.