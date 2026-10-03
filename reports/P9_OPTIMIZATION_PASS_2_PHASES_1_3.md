# Production 009 — Optimization Pass 2, Phases 1-3

Lane `.slim/worktrees/p8fix`, detached HEAD. Workspace `Testing 1`
(`ws_e677ab553606`). Profile `golden_p1_parallel_p9opt1_source_diag_h100`,
H100 80GB HBM3 (sm90), CPU 12. Output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` verified on
every run reported here.

| Phase | Subject | Verdict |
|---|---|---|
| 1 | Source-copy stall diagnosis | **Complete** — root cause identified |
| 2 | Triton first-use compilation | **Not successful** — cost confirmed, treatment not buildable |
| 3 | Persistent CLIP layout/meta cache | **Successful** — 31.16 ms -> 1.01 ms |

Phase 4 is out of scope for this pass.

---

## Phase 1 — source stall diagnosis: COMPLETE

10/10 valid true-cold runs. 3026 `CPU_MEMORY_STALL`, 14 `UNRESOLVED`, 0 page
I/O, 0 deschedule, 0 major faults, 0 block I/O, 0 context switches. The stall is
CPU/memory contention inside the container, not storage and not the scheduler.
Reported in `P9_SOURCE_STALL_ROOT_CAUSE.md`. This phase is what made the Phase 2
and Phase 3 numbers interpretable: it established that the same deterministic
Python work costs ~31 ms on a healthy host and ~1609 ms on a sick one.

## Phase 2 — Triton first-use compilation: NOT SUCCESSFUL

### The cost is real

One sanctioned verification exhaustive profile (deploy `40fe7255`, trace
`582bb00c`, 1 141 875 calls) on the production-shaped snapshot-enabled path:

```
compile_module_from_file   build.py:193      680.925 ms
JITFunction._do_compile    jit.py:877        286.347 ms
  make_llir / make_ptx / make_cubin    58.3 / 50.3 / 47.9 ms
```

~967 ms of first-use compilation per process, reproducing the P9 figures.

### Why no treatment was built

Seeding the Triton disk cache requires the **exact** specialization the request
compiles — `(B, M, N, dtype, BLOCK_M, BLOCK_N)` — because that tuple forms the
cache key. A plausible-but-different shape is a different key and a guaranteed
miss. All three observation routes failed:

1. `jit_post_compile_hook` never fires on Triton 3.8.0 in this deployment.
2. The exhaustive trace records no per-call arguments.
3. A runtime observer wrapped around the real `bmm_outer_product` entry did not
   fire on trial.

So the builder fails closed. Nothing synthetic is seeded and no treatment is
committed. Building it on a guessed specialization would have produced a cache
that never hits while looking complete.

### Measured, not assumed

Installed stack: Triton **3.8.0**, torch **2.14.0+cu130**, CUDA 13.0, sm90,
`TRITON_CACHE_DIR=/tmp/triton_cache`, `FileCacheManager` layout
`<cache_dir>/<key>/<file>`. Two APIs named in the brief do not exist on 3.8.0
(`CudaUtilsDriver`, `default_cache_dir`), and `compile_module_from_file` is
module-level rather than a `CudaUtils` method. The kernel is PyTorch's
`aten::bmm` dispatch override in `torch/_native/ops/bmm_outer_product/`, not
ComfyUI code, so it cannot be wrapped from this repo — only the disk cache can be
seeded.

### Production defects found and fixed

- **Snapshot-poisoning crash loop** (`2e7b7b39`, `f357e99`). Triton hydration and
  the compile observer ran in `startup()` under `snap=True`. This repo blocks
  CUDA-touching imports during capture, so every snapshot was poisoned: containers
  captured with `vram_mib=81559` and the H100 present, then every restore failed
  with `No CUDA GPUs are available`, in a loop. Isolated by stash-and-redeploy.
  Moved to `restore()` (`snap=False`) and gated on the flag.
- **Silent flag gating** (`975aec14`). A Golden flag needs declaring in three
  places; the copy probe was in two, and `_runtime_env()` is a hand-written
  allowlist, so the flag never reached the container and the diagnostic collected
  nothing. `tests/test_golden_flag_reaches_container.py` now enforces all three
  and fails when the passthrough is removed.

### Two of our own telemetry fields were wrong

- `request_time_helper_build` was computed as
  `not (compatible and helper_files <= files)`, trivially true whenever no
  manifest exists. It read `true` on a run with zero cache files.
- `cache_file_count` is a *before*-forward snapshot by construction, so `0` is
  expected and says nothing about what happens after.

## Phase 3 — persistent CLIP layout/meta cache: SUCCESSFUL

Committed `e1bdddc`. Deployment `8d889d24`, 5 serial true-cold runs, every run
`valid` + `true_cold` + exact SHA, `layout_cache_source='persistent'`,
`clip_meta_cache_hit=True`.

| metric | control | treatment | delta |
|---|---|---|---|
| `layout_resolve_ms` | 31.16 | **1.01** | **-97%** |
| `layout_lookup_ms` | — | **0.00** | free |
| `meta_sd_build_ms` | 36.31 | 33.11 | -3.20 ms |
| `metadata_cache_hydration_ms` | — | 5.50 - 7.83 | during `restore()` |
| `residual_meta_build_ms` | — | 0.98 - 2.97 | blueprint from RAM |

Hydration budget was 75 ms; measured 5.5-7.8 ms, and it is off the request path.

### Design

Identity is `(canonical relative path, st_size, st_mtime_ns)` with the header
digest as tiebreaker when the cheap identity disagrees. `st_dev`/`st_ino` are not
stable across containers and `models_generation` is never advanced on download,
so neither can key the cache. One normalized tensor table
`(name, dtype, shape, offset, length)` serves both `_parse_layout` and
`_clip_meta_state_dict_from_header`; tensor objects are never serialized.

Publication is owned by `ModalRuntimeEntrypoint.publish_model_metadata_cache`, a
sibling of the contractually read-only `source_identity_probe`, exposed as
`v2ctl publish-model-metadata-cache` and run in the Golden sequence right after
`source-probe`. It publishes the three static cohort models, commits the Volume
once, is idempotent, never raises, and never runs in the inference request path.
Hydration is warmed inside `restore()` immediately after
`reload_runtime_state()`. Absent, corrupt, wrong-schema, truncated, stale and
unknown all fall back to the canonical parse with the reason visible.

### Three defects that every existing check passed

1. **Wrong mount.** `CACHE_PATH` used the legacy `ComfyAPI` mount
   (`/root/comfymodal_runtime_state`) while the deployed V2 class mounts the
   *same* Volume at `/mnt/comfymodal_runtime_state`. The publisher created an
   ordinary directory, wrote the blob into it, and committed a Volume it had
   never written to. It reported `status: ok` with a real `file_bytes`.
2. **Memoized miss.** `hydrate()` cached its "not there yet" result, pinning
   `absent` for the container's lifetime so a blob published by another container
   could never be seen.
3. **Verification cost.** Identity checking re-read the header off the Volume on
   every lookup, making the cache *slower* (39.56 ms) than the parse it replaced
   (31.16 ms).

Each is pinned by a regression test that fails against the old code.

## Local verification

`python -m pytest tests -m fast_unit` → **631 passed, 2 failed, 7 skipped**. The
two failures are `tests/test_rx9p_h_identity_chain.py::test_success_path_exact`
and `::test_compact_nested_sage_observation_is_mismatch`, which also fail on a
pristine `production-007` tree and are unrelated to this work.

## Workspace note

Phase 2 and the first Phase 3 iterations ran on `Testing 9`
(`ws_ee7221847f7d`), which exhausted its credit. The lane moved to `Testing 1`
(`ws_e677ab553606`) via the config-owned destination
`config/v2/modal_target.toml`. Testing 1 already held all three cohort models, so
no reprovisioning was needed. That file is intentionally **not** committed —
it is local environment state, not a lane change.

## What is worth carrying forward

Every failure in this pass shared one shape: it was invisible to the checks that
were being run. The publisher reported success, runs stayed `valid`, output SHAs
matched, and the suite was green — while the feature did nothing, or did
something worse than nothing.

The questions that actually caught them were unglamorous: *is the writer writing
to the thing the reader reads?*, *can a blob published by another process ever
become visible?*, and *is this faster than the code it replaced?* None of those
were in the original checklist, and all three should be.

Phase 2's remaining prerequisite is narrow and concrete: make the Triton
specialization observable where it is unambiguous — the real tensors inside the
CLIP RoPE forward — rather than via a Triton hook that does not fire on 3.8.0.
Everything else for that treatment already exists and is committed.