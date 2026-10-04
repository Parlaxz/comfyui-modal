# Production 009 — Source-Side 64 MiB Copy Isolation

## 0. Answer

**`SOURCE_SIDE`.**

Arms A and B — the two arms whose source is the whole-file `MAP_PRIVATE`
mapping of the Volume-backed UNET checkpoint — are pathological in the same way,
in the same regime, at the same magnitudes. Arms C and D, whose source is
resident anonymous RAM, are not merely healthy but **5.3x faster at the median**
and never produced a single copy over 100 ms across 5120 copies and 10
containers.

The pinned shared arena is exonerated. Arm C uses the *same* pinned
`cudaHostRegister`ed arena as production and is the fastest mapped-destination
arm in the set.

| arm | source | destination | p50 | p99 | max | >100 ms | >250 ms | >1 s | verdict |
|:--|:--|:--|--:|--:|--:|--:|--:|--:|:--|
| **A** | whole mmap | pinned shared arena | 43.59 | 497.22 | 5095.47 | 841 | 103 | 35 | pathological |
| **B** | whole mmap | anonymous RAM | 42.73 | 568.71 | 2543.02 | 52 | 34 | 2 | pathological |
| **C** | anonymous RAM | pinned shared arena | **8.31** | **25.97** | **32.35** | **0** | **0** | **0** | healthy |
| **D** | anonymous RAM | anonymous RAM | **6.53** | **15.25** | **34.49** | **0** | **0** | **0** | healthy |

This is the discrimination Phase-1 could not make. Its per-copy counters showed
zero `majflt`, zero `inblock` and zero context switches on every pathological
copy, and it correctly recorded that under gVisor those host-kernel counters are
NON-AUTHORITATIVE for ruling out backing-page work. It then recommended changing
nothing in the source path on the strength of those counters. That
recommendation was wrong, and this experiment is the evidence that it was.

## 1. Exact experiment base SHA

| item | value |
|:--|:--|
| base SHA | `211d204b06f1246bbd2b5b591473d7d08b629030` |
| base commit | `docs(golden-source): report the pathological source stall mechanism` |
| branch | `exp/source-copy-isolation` |
| worktree | `.slim/worktrees/source-copy-isolation` |
| experiment commit | `cc2f541c` |
| teardown fix commit | `f3ea682c` |
| source-probe fix commit | `18099c1e` |
| arm-identity fix commit | `504f330d` |

`211d204b` is the exact Phase-1 diagnostic conclusion. It is the direct parent
of the active optimisation lane's only commit, so the optimisation lane's tree
was neither read from nor modified. Its ancestry is exactly the documented
Phase-1 chain:

```
211d204b docs(golden-source): report the pathological source stall mechanism
975aec14 fix(golden-config): let the source copy probe reach the container
cfee2acf fix(golden-source): import the copy probe without a relative import
28506a03 chore(golden-diagnostic): add the isolated source-stall diagnostic profile
dce3c4ac feat(golden-source): classify pathological mapped-copy stalls
```

`git branch -a --contains 211d204b` returns nothing because the lane that holds
it, `.slim/worktrees/p8fix`, is a **detached HEAD** at `ac56539b` whose parent is
`211d204b`. The commit is therefore reachable but unreferenced, which is why it
had to be identified from the log rather than from a ref.

## 2. Branch and worktree

```
git worktree add -b exp/source-copy-isolation .slim/worktrees/source-copy-isolation 211d204b
```

The worktree was created at exactly `211d204b` and was clean at creation. The
active optimisation lane `.slim/worktrees/p8fix` was not entered, not read from
and not modified; `main`, the production tags, the workflow, the sampler,
Triton, the CLIP metadata cache, the VAE logic, Modal resource settings, the QD
transport, the reader count, the 64 MiB block size, the pacer and the H2D
dispatcher semantics are all untouched.

Nothing was promoted. No production-010 exists and no production tag moved. No
cherry-pick was made into any other lane.

## 3. Experimental app and deploy identity

Five isolated apps. Each arm owns its own app so that the arm is a *deploy-level*
identity, not a request-time override (see section 6.2 for why that is not a
stylistic choice).

| arm | profile | app | deploy fingerprint | image |
|:--|:--|:--|:--|:--|
| shared base | `golden_p1_parallel_p9_srccopy_iso_h100` | `batch-p9srccopy-h100` | `95221b5013b5882e6c3d2b214049086a2d6f93348c9b917994af30f05259276f` | `im-svj7AXMXey29gZy8au8ILo` |
| A | `golden_p1_parallel_p9_srccopy_iso_a_h100` | `batch-p9srccopy-a-h100` | `e152c5fd0adbfff0db55a85b8fc75229454e169d439a00d5fd0704c484ef990e` | `im-V3OJS7Heyzl55fDe3ndH8v` |
| B | `golden_p1_parallel_p9_srccopy_iso_b_h100` | `batch-p9srccopy-b-h100` | `7e936b992cdc38399d584212d0264c6d898200756b97fc3d8270a2f19895d391` | `im-iD7WQNWeVT1NLafxPimv0d` |
| C | `golden_p1_parallel_p9_srccopy_iso_c_h100` | `batch-p9srccopy-c-h100` | `b9f4b3f899b1e3e7ee6d9476e4cfc2780351b185ccbb2040d402d5b6b0d53c12` | `im-PN3O2Mp4Hqay8qpZDdlov6` |
| D | `golden_p1_parallel_p9_srccopy_iso_d_h100` | `batch-p9srccopy-d-h100` | `9d4cfae2d657202a7c7c84eeac5176840e995387feb6f1799379945f1e22497e` | `im-jEpdkyqD3Vf2J0AKZua1nQ` |

Every deployment: `H100!` / `CPU=12` requested / memory 24576 MB, class
`ModalRuntimeEntrypointV2`, method `run_golden_parallel_stream`, whole mmap
lifecycle, thread source owner, 64 MiB blocks, 16 x 64 MiB arena,
`conditioning_cache=forced_miss`, `fresh_required=true`, expected output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`,
`min_containers=0`, single-use containers.

`v2ctl doctor` returned `OK` for all five. `v2ctl source-probe` returned
`RESULT=PASS source_identity=MATCH` for all five, including the experiment's own
module:

```
comfymodal_runtime/source_copy_isolation.py: MATCH remote_sha=65f57aa7ca495c10 expected_sha=65f57aa7ca495c10
comfymodal_runtime/source_copy_probe.py:    MATCH remote_sha=08cea861f6733861 expected_sha=08cea861f6733861
comfymodal_runtime/source_stall_classification.py: MATCH
comfymodal_runtime/golden_parallel.py:      MATCH remote_sha=fb207bf63b996fdb expected_sha=fb207bf63b996fdb
```

In addition, every arm payload carries `identity.module_sha256`, the SHA-256 of
the experiment module's own bytes **as loaded inside the container that ran the
arm**, so each of the 40 usable requests independently proves which experiment
code produced its numbers.

## 4. The current production source-copy path, verified from source

Read from `comfymodal_runtime/golden_source_threads.py` at the base commit, not
inferred from Phase-1's prose.

| property | value | file:line |
|:--|:--|:--|
| arena geometry | 16 slots x 64 MiB = 1 GiB | `golden_source_threads.py:76-78` |
| reader count | 4 (`READER_COUNT`) | `golden_source_threads.py:79` |
| pacer | 4 ms global launch-spacing floor | `golden_source_threads.py:81` |
| mapping lifecycle | one whole-file `MAP_PRIVATE` mapping per generation, opened once | `golden_source_threads.py:1660-1669` |
| mapping call | `mmap(NULL, size, PROT_READ=1, MAP_PRIVATE=2, fd, 0)` | `golden_source_threads.py:1663-1665` |
| destination | 64 MiB window of the pinned shared arena at `slot_index * SLOT_BYTES` | `golden_source_threads.py:1702` |
| copy | `libc.memmove(dst, map_address + source_offset, length)` | `golden_source_threads.py:1736-1737` |
| probe | same `SourceCopyProbe` around the memmove and nothing else | `golden_source_threads.py:1735-1738` |
| pinned arena construction | POSIX `shared_memory.SharedMemory(create=True, 1 GiB)` then one `cudaHostRegister(addr, size, flags=0)`, no prefault | `golden_io_process_v2.py:4518`, `:4543`, `:4453` |

So the production path is exactly:

```
whole-file MAP_PRIVATE mapping of the checkpoint (once per generation)
    -> 4 source reader threads
        -> claim a 64 MiB slot from the 16-slot shared arena
        -> 4 ms pacer
        -> libc.memmove(source_addr + offset, arena_slot_addr, 64 MiB)
        -> publish READY, H2D consumes the slot, parent releases it
```

The experiment does **not** invent a persistent whole mapping as an arm. That
is already the architecture; it is arm A's control.

## 5. Four-arm design

`comfymodal_runtime/source_copy_isolation.py`, `ARM_LAYOUT`:

| arm | source | destination | variants | app |
|:--|:--|:--|:--|:--|
| A | whole-file `MAP_PRIVATE` mmap of `z_image_turbo_bf16.safetensors` (12 309 866 400 B, 184 x 64 MiB blocks) | pinned shared arena, `cudaHostRegister` flags 0, no prefault | `concurrent4` | `batch-p9srccopy-a-h100` |
| B | identical whole-file mmap, identical source offsets | ordinary anonymous RAM, same 1 GiB / 16 x 64 MiB geometry, no `cudaHostRegister` | `concurrent4` | `batch-p9srccopy-b-h100` |
| C | ordinary anonymous RAM, 4 GiB / 64 x 64 MiB, native `memset` pre-touch | identical pinned shared arena construction | `single`, `concurrent4` | `batch-p9srccopy-c-h100` |
| D | identical anonymous RAM | identical anonymous RAM | `single`, `concurrent4` | `batch-p9srccopy-d-h100` |

Fidelity properties, each enforced by a test:

* **The copy kernel is the production one.** The experiment drives
  `golden_source_threads._run_reader_loop`, which calls
  `golden_source_threads.execute_block`. The slot claim, the 4 ms pacer, the
  whole-file address arithmetic, the `libc.memmove` and the Phase-1 probe are all
  production code. Nothing is re-implemented with Python slicing.
* **The mapped arms use the production mapping.** The whole-file mapping is
  established by `golden_source_threads.build_plan(open_source=True)` — the same
  call production makes. Only the *range list* is extended, via
  `dataclasses.replace`, so 256 ranges exist for a 184-block file; the
  descriptor, mapping address and mapping length are production's.
* **The pinned destination is the production destination.** Same POSIX shared
  memory, same size, one `cudaHostRegister` with flags 0, no prefault memset —
  production explicitly rejected prefault because registration is the population
  step.
* **Anonymous memory is genuinely resident.** `memset` with a non-zero fill over
  the whole range, before timing. The fill is `0xA5` so the pre-touch is
  observable: a page that was never written would still read as zero.
* **Geometry is unchanged.** 64 MiB blocks, 16 slots, 1 GiB destination, 4 ms
  pacer. No toy 4 KiB or 1 MiB copies anywhere.

Where the arm runs, and why it cannot perturb what it measures: between
`await golden_request_setup(session)` and the first model byte read, in
`comfymodal_runtime/golden_parallel.py`. At that point the model paths are
resolved and ComfyUI `folder_paths` is initialised, but no checkpoint byte has
been read, no C0 arena exists, no H2D has been submitted and the CUDA context is
already live from the Dynamic VRAM activation. So the arm runs on an untouched
true-cold container, and it never competes with the real CLIP source load.

## 6. Two experiment defects found by running it

Both are recorded because both produced confidently wrong evidence before they
were fixed. Both are the same class of failure Phase-1 already hit twice
(`cfee2acf`, `975aec14`): a diagnostic that quietly does not do what it claims.

### 6.1 The pinned arena was never unregistered

The first arm-A request ran the arm perfectly — 256/256 timed copies, p50
55.5 ms, max 86.5 ms, both source and arena fully resident — and then broke the
Golden request that followed it:

```
AcceleratorError: CUDA error: resource already mapped
Search for `cudaErrorAlreadyMapped' in https://docs.nvidia.com/cuda/...
```

`PinnedSharedArena.close()` closed and unlinked the shared-memory segment while
it was still registered. A `cudaHostRegister` outlives the Python object: the
driver keeps the virtual address range registered, the next 1 GiB shared-memory
allocation is handed the same address by the kernel, and the production
`cudaHostRegister` in `SharedArenaRing.ensure` then fails. The arm payload was
fine and the request died in the real CLIP load, which would have read as "the
experiment perturbed the host".

Fixed in `f3ea682c`: `close()` mirrors `SharedArenaRing`'s own teardown order —
`cudaHostUnregister` first, then release the memoryview, then close and unlink —
and the outcome is published as `report["teardown"]` so a failed unregister is
visible in the evidence instead of surfacing later as a CUDA error in an
unrelated stage. The analysis tool treats a failed unregister as
not-usable rather than as data.

### 6.2 The run-only arm selector never reached the container

Fifteen requests requested as arms B, C and D **all executed arm A**.

`COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM` was registered
`change_requires = "run"`, so `v2ctl` accepted the `--set` override, changed the
run fingerprint and recorded the value in the run manifest as `flag_sources:
set`. The container never saw it, because the class environment that
`_runtime_env()` freezes at deploy time still carried the default `"A"`.

Every one of those fifteen runs was perfectly healthy by every available check:
exit 0, `source-probe` `RESULT=PASS source_identity=MATCH`, `doctor` `OK`, valid
true-cold restored request, exact output SHA, `restore_count=1`,
`request_count=1`. Nothing raised anywhere. The only way to see it was to read
`identity.env` out of the arm payload itself.

Had the cohort been analysed from the run manifests — which is where the arm
selector was correctly recorded — the conclusion would have been that arms B, C
and D ran and were healthy, i.e. exactly backwards.

Fixed in `504f330d`: the arm, copy count, model and anonymous working-set size
are `change_requires = "deploy"`, and each arm owns its own profile and app, so
the arm is provable from the deployed fingerprint alone.

## 7. Local tests

`tests/test_source_copy_isolation.py`, **50 contracts, all passing**:

* arm selection: default is the production control; explicit selection works;
  unknown arm and unknown model fail closed; an unparseable copy count cannot
  become 1 or 0; a copy count below 128 is refused;
* the 2x2 layout itself: only A and C use the pinned destination, only A and B
  use the mapped source, only C and D carry the single-thread baseline;
* pinned vs anonymous destinations really differ: the anonymous evidence path
  does not even import CUDA, reports `cuda_host_registered: false`, has the same
  1 GiB size as the pinned arena, and is allocated once and reused;
* anonymous buffers are pre-touched: a 4 MiB buffer is allocated, written and
  read back in full, and must equal `0xA5` everywhere — a page never written
  would read as zero;
* the pinned arena unregisters before it releases the mapping, and `run_arm`
  publishes the outcome (section 6.1);
* 64 MiB block size is the production constant; `file_block_ranges` covers the
  file exactly once with only the final block short; `repeated_plan_ranges` holds
  exactly the requested copy count with gap-free destination offsets and
  in-range source offsets, and reuses source offsets so identity correlation is
  possible at all;
* slot-index reporting: `slot_index` projects to `slot * 64 MiB`, slot 0 is
  offset 0, and an out-of-range slot reports `None` rather than inventing an
  address that does not exist;
* thread-CPU accounting is the before/after delta, not the absolute clock;
  unavailable thread CPU is `None` and never fabricated; wall stays measured
  even without thread CPU; a zero or backwards CPU delta yields no ratio;
  sentinel and real-zero fault deltas stay distinguishable;
* statistics: every required statistic, empty series is all-null, all four
  stall thresholds, slowest list capped at 20 and ordered worst-first;
* the experiment does not reimplement the production copy, redefines no
  production geometry constant, and re-exports no production symbol;
* the `golden_parallel` hook sits after `golden_request_setup` and before
  `golden_clip_load`;
* the experiment is inert unless explicitly enabled, and enables only on an
  explicit true value;
* runtime identity never invents a region; host facts declare NUMA
  `not_inferred`;
* an **end-to-end run of the real driver**: with the geometry shrunk to 1 MiB
  slots x 4, the test starts four real reader threads through the production
  reader loop, performs 8 real `libc.memmove` copies through the production
  control block and operation ring, releases every slot through the
  production `READY -> IN_FLIGHT -> FREE` transitions, and asserts
  8/8 published, 8/8 recorded, no timeout, no fatal, no failure, all slots
  quiescent, and the exact source offsets and slot indices it asked for.

Regression suites: `tests/test_c0_source_threads.py`,
`tests/test_source_copy_probe.py`, `tests/test_golden_flag_reaches_container.py`,
`tests/test_source_child_script_launch.py` — **153 passed, 6 skipped**.

`fast_unit`: **609 passed**, with only the two pre-existing
`test_rx9p_h_identity_chain` failures (`INCOMPLETE` vs `MISMATCH`) that
`211d204b` already documented and that reproduce on a pristine tree.

Note on `tools/test_perf.py --fast -- tests -m fast_unit`: its 15 s budget is
below this repository's collection cost on this host. Measured collection of the
same `fast_unit` set, twice, with and without the new test file:
10.29–10.68 s of pytest-reported collection time in all four runs, and the new
file adds none of it. The failure is at `COLLECTION` with `count=0`, i.e. a
pre-existing host property, not a test-time regression.

## 8. Per-arm run validity

41 requests, run strictly serially, never concurrently, one `golden run` per
request, five per arm on the four per-arm deployments.

| check | result |
|:--|:--|
| attempts | 41 |
| valid | 40/41 |
| DNF | 0 |
| true-cold | 41/41 |
| exact output SHA | 40/40 valid (the one invalid request produced no output) |
| arm status `ok` | 40/41 |
| variants complete | 40/41 |
| usable (valid **and** arm `ok` **and** all variants complete **and** teardown registered) | **40** |
| request-time `SNAPSHOT_CAPTURE` | none; `capture_guard` `state=idle`, `next_request_guarded=false` after every arm |
| excluded | 1 (the `cudaErrorAlreadyMapped` request of section 6.1) |

**No attempt was discarded.** The excluded request is listed with its failure
reasons in `artifacts/source_copy_isolation/summary_final.json`. Every one of the
40 usable requests is a valid true-cold restored request on the exact expected
output SHA, and each carries a complete arm payload with 256 (A, B) or 512 (C,
D) timed copies.

Arms are reported per deployment, never pooled across deployments:

| arm | deployment | containers | copies | image |
|:--|:--|--:|--:|:--|
| A | `batch-p9srccopy-a-h100` | 5 | 1280 | `im-V3OJS7Heyzl55fDe3ndH8v` |
| A | `batch-p9srccopy-h100` (earlier, section 6.2) | 20 | 5120 | `im-svj7AXMXey29gZy8au8ILo` |
| B | `batch-p9srccopy-b-h100` | 5 | 1280 | `im-iD7WQNWeVT1NLafxPimv0d` |
| C | `batch-p9srccopy-c-h100` | 5 | 2560 | `im-PN3O2Mp4Hqay8qpZDdlov6` |
| D | `batch-p9srccopy-d-h100` | 5 | 2560 | `im-jEpdkyqD3Vf2J0AKZua1nQ` |

The 20 extra arm-A containers are genuine arm-A observations on a different
deployment, so they are reported as a separate cohort and never mixed into the
arm-A per-deployment numbers. Both are pathological, independently.

## 9. Wall and thread-CPU statistics

Pooled over all usable containers of an arm. All values in milliseconds.

### Arm A — whole mmap -> pinned shared arena (25 containers, 6400 copies)

| series | min | p50 | p90 | p95 | p99 | max | mean | SD | CV |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| wall_ms | 4.87 | 43.59 | 117.42 | 136.23 | 497.22 | 5095.47 | 61.52 | 156.23 | 2.540 |
| thread_cpu_ms | 0.00 | 40.00 | 110.00 | 130.00 | 470.20 | 4940.00 | 58.20 | 151.66 | 2.606 |
| wall/cpu | 0.49 | 1.04 | 1.18 | 1.24 | 1.41 | 2.99 | 1.02 | 0.16 | 0.156 |

Arm A split by deployment, so that the two deployments are never pooled into
one homogeneous cohort:

| deployment | containers | copies | min | p50 | p90 | p95 | p99 | max | mean | SD | CV | >250 | >1 s |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `batch-p9srccopy-a-h100` | 5 | 1280 | 6.48 | 62.76 | 131.98 | 139.64 | 162.53 | 1094.31 | 69.97 | 59.25 | 0.847 | 3 | 1 |
| `batch-p9srccopy-h100` | 20 | 5120 | 4.87 | 40.72 | 84.68 | 131.35 | 668.26 | 5095.47 | 59.40 | 172.08 | 2.897 | 100 | 34 |

Both are pathological, independently and on their own deployments.

Per container, arm-A deployment only (`batch-p9srccopy-a-h100`):

| request | image | copies | p50 | p99 | max | cpu p50 | ratio p50 | >250 ms |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|
| `e4c672870e2a` | `im-V3OJS7Heyzl55fDe3ndH8v` | 256 | 106.18 | 183.44 | 209.28 | 90 | 1.042 | 0 |
| `b9a2044f9016` | same | 256 | 54.99 | 311.02 | **1094.31** | 50 | 1.043 | 3 |
| `0d8d24a7bb97` | same | 256 | 44.12 | 59.51 | 65.35 | 40 | 1.014 | 0 |
| `48731546f28e` | same | 256 | 97.56 | 165.55 | 195.37 | 90 | 1.043 | 0 |
| `0373746a5917` | same | 256 | 115.31 | 148.38 | 161.15 | 105 | 1.048 | 0 |

Per container, earlier arm-A deployment (`batch-p9srccopy-h100`):

| request | p50 | p99 | max | cpu p50 | ratio p50 | >250 ms |
|:--|--:|--:|--:|--:|--:|--:|
| `fc0545bc0db6` | 48.49 | 67.85 | 77.47 | 50 | 1.025 | 0 |
| `e3b5b4bf1f25` | 41.62 | 1085.57 | **1282.02** | 40 | 1.019 | 12 |
| `b2a34ebae7e6` | 34.00 | 194.55 | 416.97 | 30 | 1.031 | 1 |
| `e4b81e90dabe` | 30.49 | 994.54 | **2002.53** | 30 | 1.014 | 24 |
| `d2a4b9f58f3c` | 47.85 | 66.96 | 68.79 | 50 | 1.009 | 0 |
| `09b894536a24` | 41.34 | 55.32 | 60.44 | 40 | 1.033 | 0 |
| `d496f66f7570` | 74.43 | 360.38 | 501.88 | 70 | 1.072 | 11 |
| `b16714ec4df3` | 33.12 | 55.56 | 60.84 | 30 | 1.078 | 0 |
| `e691a128ab12` | 33.36 | 47.73 | 56.95 | 30 | 1.091 | 0 |
| `0caa4a130dcb` | 53.76 | 69.86 | 72.30 | 50 | 1.031 | 0 |
| `27ca099a6d47` | 115.23 | 172.97 | 192.49 | 100 | 1.048 | 0 |
| `f068a3d74bdd` | 31.49 | 40.92 | 47.24 | 30 | 1.054 | 0 |
| `d5fe3e39273c` | 38.45 | 2235.56 | **5095.47** | 40 | 1.020 | 7 |
| `299ae342db74` | 59.36 | 118.33 | 132.67 | 60 | 1.022 | 0 |
| `83b8ff355786` | 42.28 | 67.59 | 72.90 | 40 | 1.018 | 0 |
| `38051360bff6` | 65.78 | 239.82 | 317.04 | 60 | 1.056 | 3 |
| `aaf3f59db095` | 48.80 | 68.77 | 70.04 | 50 | 1.019 | 0 |
| `e3dabb1f7d5e` | 25.67 | 1980.53 | **2446.87** | 30 | 1.025 | 35 |
| `5ceb9e1c79d2` | 47.55 | 1049.60 | **3778.92** | 40 | 1.027 | 5 |
| `a38116be788d` | 42.81 | 227.08 | 511.92 | 40 | 1.022 | 2 |

### Arm B — whole mmap -> anonymous RAM (5 containers, 1280 copies)

| series | min | p50 | p90 | p95 | p99 | max | mean | SD | CV |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| wall_ms | 5.06 | 42.73 | 63.05 | 83.82 | 568.71 | **2543.02** | 52.25 | 113.90 | 2.180 |
| thread_cpu_ms | 0.00 | 40.00 | 60.00 | 80.00 | 534.20 | 2210.00 | 48.41 | 103.94 | 2.147 |
| wall/cpu | 0.10 | 1.02 | 1.20 | 1.26 | 1.52 | 6.31 | 1.03 | 0.29 | 0.284 |

| request | copies | p50 | p99 | max | cpu p50 | ratio p50 | >250 ms |
|:--|--:|--:|--:|--:|--:|--:|--:|
| `2643d014f364` | 256 | 45.03 | 88.04 | 100.85 | 40 | 1.010 | 0 |
| `db6ca6372194` | 256 | 44.14 | 60.39 | 66.10 | 40 | 1.024 | 0 |
| `92b0de68d70d` | 256 | 45.61 | 71.10 | 72.67 | 40 | 1.018 | 0 |
| `94d0e1c5aad8` | 256 | 30.37 | 815.03 | **1151.57** | 30 | 1.010 | 23 |
| `45b4ceae5e00` | 256 | 49.03 | 524.05 | **2543.02** | 50 | 1.050 | 11 |

### Arm C — anonymous RAM -> pinned shared arena (5 containers, 2560 copies)

| series | min | p50 | p90 | p95 | p99 | max | mean | SD | CV |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| wall_ms | 6.24 | **8.31** | 11.23 | 11.96 | **25.97** | **32.35** | 8.91 | 2.62 | 0.294 |
| thread_cpu_ms | 0.00 | 10.00 | 10.00 | 10.00 | 20.00 | 30.00 | 7.94 | 4.92 | 0.620 |
| wall/cpu | 0.54 | 0.84 | 1.13 | 1.19 | 1.30 | 1.76 | 0.89 | 0.16 | 0.179 |

| request | copies | p50 | p99 | max | cpu p50 | ratio p50 | >250 ms |
|:--|--:|--:|--:|--:|--:|--:|--:|
| `92fc8db906ed` | 512 | 8.31 | 14.05 | 32.29 | 10 | 0.839 | 0 |
| `8b25ce7975d0` | 512 | 8.81 | 27.40 | 29.24 | 10 | 0.901 | 0 |
| `2fbedc3278f6` | 512 | 8.12 | 12.96 | 32.03 | 10 | 0.818 | 0 |
| `83747e3059f6` | 512 | 9.43 | 12.38 | 32.35 | 10 | 0.959 | 0 |
| `5b1ef6055fcf` | 512 | 8.12 | 24.87 | 31.33 | 10 | 0.818 | 0 |

### Arm D — anonymous RAM -> anonymous RAM (5 containers, 2560 copies)

| series | min | p50 | p90 | p95 | p99 | max | mean | SD | CV |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| wall_ms | 4.69 | **6.53** | 8.77 | 11.48 | **15.25** | **34.49** | 6.91 | 2.58 | 0.374 |
| thread_cpu_ms | 0.00 | 10.00 | 10.00 | 10.00 | 20.00 | 30.00 | 6.09 | 5.39 | 0.884 |
| wall/cpu | 0.47 | 0.68 | 0.90 | 1.18 | 1.30 | 1.66 | 0.72 | 0.19 | 0.269 |

| request | copies | p50 | p99 | max | cpu p50 | ratio p50 | >250 ms |
|:--|--:|--:|--:|--:|--:|--:|--:|
| `323915c1c988` | 512 | 4.99 | 7.26 | 17.36 | 0 | 0.506 | 0 |
| `9d9ff5453c6f` | 512 | 6.89 | 15.29 | 34.49 | 10 | 0.691 | 0 |
| `e308f609081e` | 512 | 5.32 | 9.94 | 22.81 | 10 | 0.541 | 0 |
| `9e60c94896c4` | 512 | 8.46 | 14.35 | 31.97 | 10 | 0.847 | 0 |
| `abc24e5bd431` | 512 | 6.12 | 13.87 | 27.69 | 10 | 0.625 | 0 |

**Measurement caveat, stated rather than hidden.** `wall/cpu` below 1.0 in arms C
and D is an artefact of `CLOCK_THREAD_CPUTIME_ID` granularity, not evidence that
a copy finished before it started. `thread_cpu_ms` in those arms quantises to
0/10/20/30 ms while a 64 MiB copy takes 6–9 ms, so the ratio is dominated by
quantisation at both ends. The wall numbers are the usable measurement in C and
D; the ratio is only meaningful where a copy is long relative to the tick,
i.e. in arms A and B.

Per-copy effective bandwidth at the median, 64 MiB per copy:

| arm | p50 wall | p50 per-copy | 4-thread aggregate at p50 |
|:--|--:|--:|--:|
| A | 43.59 ms | 1.43 GiB/s | ~5.7 GiB/s |
| B | 42.73 ms | 1.46 GiB/s | ~5.9 GiB/s |
| C | 8.31 ms | **7.52 GiB/s** | ~30 GiB/s |
| D | 6.53 ms | **9.57 GiB/s** | ~38 GiB/s |

## 10. Stall-threshold counts

| arm | containers | copies | >100 ms | >250 ms | >500 ms | >1000 ms | worst |
|:--|--:|--:|--:|--:|--:|--:|--:|
| A (pooled, 2 deployments) | 25 | 6400 | 841 (13.1 %) | 103 | 64 | 35 | 5095.47 |
| A (arm-A app only) | 5 | 1280 | 435 (34.0 %) | 3 | 3 | 1 | 1094.31 |
| B | 5 | 1280 | 52 (4.1 %) | 34 | 17 | 2 | 2543.02 |
| C | 5 | 2560 | **0** | **0** | **0** | **0** | 32.35 |
| D | 5 | 2560 | **0** | **0** | **0** | **0** | 34.49 |

Arms C and D produced **zero** copies over 100 ms in 5120 copies across 10
containers. Arm A's worst copy, 5095.47 ms, is 158x arm C's worst.

## 11. Top slow copies

Arms A and B, with full evidence. Every single one has `majflt_delta = 0`,
`inblock_delta = 0`, `nvcsw_delta = 0` and `nivcsw_delta = 0`, and a wall/cpu
ratio between 1.02 and 1.19.

**Arm A — the ten slowest copies across 25 containers:**

| wall ms | cpu ms | ratio | slot | src offset MiB | reader | ordinal | majflt | inblk | nvcsw | nivcsw |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 5095.47 | 4940.0 | 1.032 | 3 | 192 | 3 | 3 | 0 | 0 | 0 | 0 |
| 4213.38 | 4090.0 | 1.030 | 1 | 1664 | 0 | 26 | 0 | 0 | 0 | 0 |
| 3778.92 | 3630.0 | 1.041 | 0 | 3712 | 3 | 58 | 0 | 0 | 0 | 0 |
| 2536.23 | 2460.0 | 1.031 | 4 | 1280 | 1 | 20 | 0 | 0 | 0 | 0 |
| 2446.87 | 2390.0 | 1.024 | 2 | 1792 | 0 | 28 | 0 | 0 | 0 | 0 |
| 2115.31 | 2060.0 | 1.027 | 2 | 3584 | 2 | 56 | 0 | 0 | 0 | 0 |
| 2057.82 | 2010.0 | 1.024 | 0 | 896 | 3 | 14 | 0 | 0 | 0 | 0 |
| 2002.53 | 1950.0 | 1.027 | 1 | 5312 | 2 | 83 | 0 | 0 | 0 | 0 |
| 1989.56 | 1940.0 | 1.026 | 2 | 2624 | 2 | 41 | 0 | 0 | 0 | 0 |
| 1917.29 | 1880.0 | 1.020 | 1 | 2048 | 1 | 32 | 0 | 0 | 0 | 0 |

**Arm B — the ten slowest copies across 5 containers:**

| wall ms | cpu ms | ratio | slot | src offset MiB | reader | ordinal | majflt | inblk | nvcsw | nivcsw |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 2543.02 | 2210.0 | 1.151 | 2 | 9408 | 1 | 147 | 0 | 0 | 0 | 0 |
| 1151.57 | 1110.0 | 1.037 | 3 | 10048 | 2 | 157 | 0 | 0 | 0 | 0 |
| 983.40 | 950.0 | 1.035 | 4 | 9792 | 0 | 153 | 0 | 0 | 0 | 0 |
| 903.88 | 780.0 | 1.159 | 4 | 9088 | 2 | 142 | 0 | 0 | 0 | 0 |
| 852.63 | 820.0 | 1.040 | 2 | 7104 | 3 | 111 | 0 | 0 | 0 | 0 |
| 784.26 | 760.0 | 1.032 | 1 | 5696 | 0 | 89 | 0 | 0 | 0 | 0 |
| 776.75 | 760.0 | 1.022 | 0 | 9024 | 1 | 141 | 0 | 0 | 0 | 0 |
| 744.55 | 730.0 | 1.020 | 4 | 8896 | 0 | 139 | 0 | 0 | 0 | 0 |
| 632.69 | 530.0 | 1.194 | 1 | 9344 | 0 | 146 | 0 | 0 | 0 | 0 |
| 623.59 | 610.0 | 1.022 | 3 | 9152 | 2 | 143 | 0 | 0 | 0 | 0 |

**Arm C — the ten slowest copies, for contrast:**

| wall ms | cpu ms | ratio | slot | src offset MiB | reader | ordinal |
|--:|--:|--:|--:|--:|--:|--:|
| 32.35 | 30.0 | 1.078 | 3 | 192 | 3 | 3 |
| 32.29 | 30.0 | 1.077 | 4 | 256 | 0 | 4 |
| 32.20 | 30.0 | 1.074 | 2 | 128 | 2 | 2 |
| 32.03 | 30.0 | 1.068 | 4 | 256 | 0 | 4 |
| 31.33 | 30.0 | 1.044 | 2 | 128 | 2 | 2 |

Arm D's worst is 34.49 ms. Arms C and D's slowest copies are all in the first
five ordinals of their variant — the first-touch tail Phase-1 saw at ordinal 0 —
and are bounded by 35 ms.

## 12. Source-offset correlation

| arm | distinct offsets | slow copies | slow copies at distinct offsets | offsets slow in >=2 containers | per-offset p50 spread | worst-offset mean |
|:--|--:|--:|--:|--:|--:|--:|
| A | 184 | 841 | 184 | 181 | 16.10 – 56.34 ms (3.5x) | 199.13 ms (offset 5312 MiB, n=25) |
| B | 184 | 52 | 46 | 0 | 17.74 – 70.51 ms (4.0x) | 538.77 ms (offset 9408 MiB, n=5) |
| C | 64 | 0 | 0 | 0 | 7.93 – 8.73 ms (1.1x) | 12.06 ms |
| D | 64 | 0 | 0 | 0 | 6.12 – 7.95 ms (1.3x) | 9.24 ms |

**There is no source-offset identity.** In arm A every one of the 184 distinct
file offsets produced at least one copy over 100 ms, and the slow copies in each
container span the whole file. Per container:

| container | slow copies | source offset range (MiB) | distinct offsets |
|:--|--:|:--|--:|
| `e4b81e90dabe` | 33 | 0 – 11200 | 33 |
| `27ca099a6d47` | 151 | 64 – 11584 | 151 |
| `d496f66f7570` | 66 | 0 – 11712 | 66 |
| `38051360bff6` | 53 | 0 – 11072 | 53 |
| `0373746a5917` | 156 | 0 – 11520 | 156 |
| `d5fe3e39273c` | 14 | 192 – 3136 | 14 |
| `299ae342db74` | 5 | 4032 – 4992 | 5 |

The "recurs across containers" counts in the table are an artefact of arm A's
13 % base rate: with 13 % of copies slow, every identity is eventually slow
somewhere. The informative number is the **per-offset p50 spread of 3.5x on a
43.6 ms median**, against **1.1x in arm C** on the identical driver with an
anonymous source. That is a source-property difference, not an
offset-identity difference.

What *is* strongly identity-like is the **container**, not the offset: arm A's
per-container p50 ranges from 25.67 ms to 115.31 ms and its per-container slow
fraction from 0/256 to 156/256. The slow regime is a property of the container
and the time window, not of a particular byte range of the checkpoint.

`REPEATING_SOURCE_OFFSET = no`.

## 13. Slot correlation

| arm | distinct slots used | slot mean spread | slow copies at distinct slots | reader mean spread |
|:--|--:|--:|--:|--:|
| A | 7 of 16 | 58.78 – 106.57 ms (1.81x) | 7 | 59.26 – 65.23 ms (1.10x) |
| B | 7 of 16 | 46.72 – 157.20 ms (3.36x) | 7 | 48.83 – 55.62 ms (1.14x) |
| C | 7 of 16 | 8.65 – 20.42 ms (2.36x) | 0 | 8.36 – 9.11 ms (1.09x) |
| D | 5 of 16 | 6.68 – 7.00 ms (1.05x) | 0 | 6.34 – 7.14 ms (1.13x) |

Slot identity is preserved exactly: every copy records the production
`slot_index` from the claim, and `dest_byte_offset` is derived from it. In arm A
the per-slot mean spread is 1.81x against a 5.2x per-offset spread and a
CV of 2.4, i.e. slot identity explains a small fraction of the variance, and
the arm's own destination is exonerated by arm C: **the same pinned arena, the
same slot geometry and the same 4-reader driver, with an anonymous source,
produced zero copies over 100 ms in 2560 copies.** Arm B's 3.36x slot spread is
one pathological container (5 containers, ~183 copies per slot) whose worst
single copy landed on slot 2; it is not a slot property.

Reader identity is flat everywhere (1.09x–1.14x), so no single reader is
implicated — consistent with Phase-1's rejection of "one dead reader".

`REPEATING_DEST_SLOT = no`.

## 14. Single-thread versus 4-thread

Arms C and D each ran 256 copies single-threaded and 256 copies across four
readers, in the same container, against the same source and destination.

| arm | variant | readers | copies | p50 | p90 | p99 | max | >100 ms | CV |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| C | single | 1 | 1280 | 8.40 | 11.69 | 14.37 | 30.59 | 0 | 0.267 |
| C | concurrent4 | 4 | 1280 | 8.20 | 9.75 | 27.59 | 32.35 | 0 | 0.319 |
| D | single | 1 | 1280 | 6.73 | 10.96 | 14.54 | 34.49 | 0 | 0.378 |
| D | concurrent4 | 4 | 1280 | 6.12 | 8.49 | 16.71 | 30.28 | 0 | 0.359 |

Four readers change nothing: p50 improves by 2 % in C and by 9 % in D, p99
worsens in C and improves marginally in D, and neither variant produces a single
copy over 100 ms. Arm A ran at production's 4 readers throughout.

This is what rules out `CONCURRENCY_SPECIFIC`: the single-thread control on the
*same* anonymous source and the *same* pinned arena as arm A is clean, so the
pathology in A and B is not a memory-bandwidth or contention effect that appears
only under concurrent traffic.

Caveat on exposure: the single-thread variants run for roughly 4x the wall of the
4-reader variants (256 sequential copies instead of 64 per reader), so they see a
longer window and therefore more opportunity to catch a rare stall. They saw
none.

## 15. Region, GPU and PCI evidence

Across all 40 usable attempts:

| field | value |
|:--|:--|
| GPU | `NVIDIA H100 80GB HBM3` in 40/40 |
| SM / memory clock | `1980 / 2619 MHz` in 40/40 |
| Performance state | `0` in 40/40 |
| PCIe link | `gen5x16` in 19, `gen4x16` in 21 |
| PCI bus id | 22 distinct BDFs, e.g. `00000000:2D:00.0`, `00000000:05:00.0`, `00000003:00:04.0` |
| Region | 9 distinct: `us-east` 4, `eu-south` 6, `ap-northeast` 2, `us-central` 5, `uk` 9, `us-west` 7, `eu-north` 2, `ap-south` 1, `ca` 4 |
| `sched_getaffinity` count | 28 in 40/40 (the profile requests `CPU=12`; the observed affinity mask is reported as measured and not reconciled) |
| NUMA | **not inferred** |
| Images | 5, one per deployment, each used by exactly the attempts from that deployment |

Two facts matter here. First, the cohort spans 9 regions and 22 distinct PCI
bus ids, and the pathology appears in some and not others, so it is not tied to
one host, one GPU or one region. Second, the split is **per container**: two
containers on the same image, in the same region, minutes apart, differ by 40x
in slow-copy count (e.g. `0d8d24a7bb97` with 0/256 and `0373746a5917` with
156/256 on `im-V3OJS7Heyzl55fDe3ndH8v`). The slow state is per container and
transient, not per host.

## 16. Classification

**`SOURCE_SIDE`**, from the decision structure:

> Evidence: A pathological, B pathological, while C healthy and D healthy.
> Conclusion: model mmap / Volume-backed source / mapped-page path is
> implicated.

| arm | verdict | basis |
|:--|:--|:--|
| A | pathological | 841/6400 over 100 ms, 35 over 1 s, max 5095 ms, 25 containers, 2 deployments |
| B | pathological | 52/1280 over 100 ms, 2 over 1 s, max 2543 ms, 5 containers |
| C | healthy | 0/2560 over 100 ms, max 32.35 ms |
| D | healthy | 0/2560 over 100 ms, max 34.49 ms |

Exactly the arms that share the whole-file `MAP_PRIVATE` mapping of the
Volume-backed checkpoint are pathological; exactly the arms that replace it with
resident anonymous RAM are not. The pinned `cudaHostRegister`ed arena is present
in one pathological arm (A) and one clean arm (C), and the arena is 5.2x faster
in C than in A, so the destination is not the variable.

`SOURCE_SIDE` is the only classification the evidence supports. The others are
excluded explicitly:

* `DESTINATION_SIDE` requires C pathological. C is the cleanest mapped-
  destination arm in the set.
* `INTERACTION_ONLY` requires A pathological with B **and** C healthy. B is
  pathological, so the pathology does not need the pinned destination at all.
* `HOST_MEMORY_GLOBAL` requires all four pathological. D never exceeded 34.49 ms
  in 2560 copies on the same class of H100 host, in the same regions, at the same
  time as arms A and B were producing 5-second copies. The host is not globally
  slow.
* `CONCURRENCY_SPECIFIC` requires single-thread controls healthy and 4-thread
  variants pathological. Both anonymous arms are clean at 1 and at 4 readers, and
  the pathological arms are pathological at the production 4 readers while the
  same driver at 1 reader on an anonymous source is clean.
* `MIXED` and `INCONCLUSIVE` do not apply: the arms discriminate cleanly, on
  absolute thresholds, on their own deployments, with 40 valid true-cold
  requests.

Pathological is judged on an absolute rule, not relative to another arm: at
least 1 % of copies over 100 ms **and** p99 at or above 100 ms, with at least two
containers. A relative rule would have been circular here, since the slowest arm
is itself a candidate for the mechanism.

## 17. Exact evidence supporting the classification

1. **Arms A and B share only their source.** A's destination is the pinned
   arena and B's is anonymous; both are pathological (p99 497 and 569 ms, max
   5095 and 2543 ms). One variable changed, the outcome did not.
2. **Arms C and D share only their source with each other, and it is the
   anonymous one.** C's destination is the pinned arena and D's is anonymous;
   both are clean, and they are the two fastest arms in the set (p50 8.31 and
   6.53 ms against 43.59 and 42.73 ms). One variable changed, the outcome did
   not.
3. **Arm A versus arm C is the same pinned arena on both sides.** Same
   `cudaHostRegister` flags 0, same 1 GiB / 16 x 64 MiB geometry, same 4 ms
   pacer, same 4-reader production loop, same probe, same container class. The
   only difference is the source. p50 43.59 ms vs 8.31 ms: **5.2x**.
4. **Arm C's maximum over 2560 copies is 32.35 ms, below arm A's median.** The
   pinned arena is not merely uninvolved, it is not the bottleneck at all.
5. **The per-copy signature is unchanged from Phase-1, which is what makes the
   source-side reading credible rather than a different failure.** Every
   pathological copy has wall/cpu 1.02–1.19, `majflt` 0, `inblock` 0, `nvcsw` 0,
   `nivcsw` 0. This experiment reproduced Phase-1's worst signature — 5095 ms
   wall against 4940 ms CPU — with no H2D, no CLIP construction, no sampler and
   no VAE running. The stall therefore does not require the rest of the request.
6. **The measurement is not an artefact of the driver's harness.** All four arms
   run the identical driver; the two mapped-source arms are slow and the two
   anonymous-source arms are not.
7. **The source really was resident-by-the-kernel and the copy really did burn
   CPU on it.** `mincore` reported `residency_first_block = 1.0` and
   `residency_arena_fraction = 1.0` on arm A. That is weak evidence, because
   Phase-1 already established that `mincore` semantics for a file-backed
   mapping on a mounted Volume under gVisor are unverified; it is recorded, and
   no conclusion in this report rests on it.

## 18. The next smallest experiment

The evidence supports the *category* of treatment, not a specific syscall. Phase-1
recommended changing nothing in the source path because the fault counters
ruled out page acquisition; this experiment shows those counters were not
authoritative, so that recommendation is withdrawn. What is now established is
that the mapped file source is the slow side. What is **not** established is
whether the mechanism is (a) backing pages not resident when the copy runs, or
(b) the per-page mapped-read path itself being slow under gVisor's Sentry.

The next experiment is two extra arms on the existing isolation harness, both
one-flag changes to the production source owner, keeping every other variable
fixed:

* **ARM A2 — `posix_fadvise(POSIX_FADV_WILLNEED)` on the source descriptor,
  once per generation, immediately after the existing `os.open`.** This asks
  whether telling the Volume to stage the file removes the stall. Note this is
  now a *diagnostic*, not a treatment: Phase-1 rejected it because the counters
  said the mechanism was not page acquisition, and the counters were wrong.
* **ARM A3 — the same whole-file mapping created with `MAP_POPULATE`.** This
  asks whether forcing population into the `mmap` syscall itself removes the
  per-copy stall. If it does, the stall was per-copy page acquisition and is
  payable once per generation. If it does not, the per-page read path is slow and
  prefetching is the wrong family of treatment.

The two arms together separate (a) from (b) with no architecture change and no
production behaviour change outside the two flags. Decision rule, stated before
the runs:

* A2 and A3 both clean -> the stall was unmaterialised backing pages. Next
  experiment is the cheapest durable form of population (probably `MAP_POPULATE`
  or `fadvise(WILLNEED)` on the generation's descriptor), measured on a counted
  cohort.
* A2 clean, A3 sick -> the `mmap` path itself is the problem. Next experiment is
  an arm that replaces the mapping with per-block positioned `preadv` into an
  anonymous buffer — which is exactly what arm C already measures at 8.31 ms,
  so the destination performance of that fallback is already known to be good.
* Both sick -> the per-page mapped read through the Sentry is intrinsically slow
  on this storage, and the source read primitive must change. Arm C is then the
  control that predicts the replacement's performance.

Chosen on the measured evidence rather than by preference: arm C is already a
working measurement of "anonymous resident source, any destination", so the
`preadv`-into-anonymous fallback is not a hypothetical performance claim.

## 19. What NOT to change yet

* **Do not change anything about the pinned shared arena.** It is exonerated by
  direct measurement: the same arena with an anonymous source produced a 32 ms
  maximum over 2560 copies. No arena alignment work, no `cudaHostAlloc` vs
  `cudaHostRegister` comparison, no arena page-layout change, no NUMA placement
  for the arena. All of that is now measured to be treating a symptom that was
  measured not to exist.
* **Do not change QD, the 64 MiB block size, the reader count, the 4 ms pacer or
  the H2D dispatcher semantics.** None is implicated. Arm C used the identical
  geometry and pacer and was 5.2x faster.
* **Do not change the mmap lifecycle.** Whole-file `MAP_PRIVATE` mapped once is
  the architecture and remains it; the experiment's finding is about *what that
  mapping costs under gVisor*, not that the mapping is the wrong abstraction.
* **Do not add NUMA binding or CPU affinity.** No NUMA evidence exists in this
  environment and none is inferred. The split here is per container, not per
  host, and both arms ran on the same hosts' siblings with and without the
  pathology.
* **Do not promote, cherry-pick or merge any of this.** No production-010, no
  production tag movement, no change to the active optimisation lane. The only
  artefact eligible for a later cherry-pick is a *final proven treatment*, which
  does not exist yet: the mechanism category is identified, the treatment is
  not.
* **Do not treat arm C or D's speed as available production performance.** They
  do not load the model. Their purpose is to locate the slow side, and a 5.2x
  median difference is a location result, not a proposed optimisation.
* **Do not treat `mincore` residency as evidence.** It reported 1.0 for a
  file-backed mapping on a mounted Volume under gVisor, whose semantics Phase-1
  already flagged as unverified, and it reported the same 1.0 for an arena whose
  pages were populated by registration rather than by any read.

## 20. Reproducing

```
python tools/v2ctl.py --profile golden_p1_parallel_p9_srccopy_iso_a_h100 golden deploy --app batch-p9srccopy-a-h100
python tools/v2ctl.py --profile golden_p1_parallel_p9_srccopy_iso_a_h100 --app batch-p9srccopy-a-h100 source-probe
python tools/v2ctl.py --profile golden_p1_parallel_p9_srccopy_iso_a_h100 --app batch-p9srccopy-a-h100 doctor
python tools/v2ctl.py --profile golden_p1_parallel_p9_srccopy_iso_a_h100 golden run --app batch-p9srccopy-a-h100
# ... five times, serially, then arms b, c, d on their own profiles/apps
python tools/source_copy_isolation_report.py --root . --out artifacts/source_copy_isolation/summary_final.json
```

No `--set` is used at run time. That is deliberate and load-bearing: a run-only
`--set` for the arm is accepted by the control plane, recorded in the run
manifest, and never reaches the container (section 6.2).

Raw evidence: every attempt, cohort manifest, run manifest and provenance
sibling under `artifacts/phase_p1_parallel_golden_v1/cohort_*/`, plus the
aggregated `artifacts/source_copy_isolation/summary_final.json`.
