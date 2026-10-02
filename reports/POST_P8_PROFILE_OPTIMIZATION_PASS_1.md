# Post-Production-008 Profile Optimization Pass 1

(ASCII-only on purpose: an earlier PowerShell UTF-8 round-trip double-encoded this
file, so all typographic characters have been removed to make that impossible again.)

**Branch:** `opt/p8-profile-cleanup-1`
**Base:** `production-008` = `9448cdd1c461996e026c59452bd1ef2ddfffd63b`
**HEAD:** `0f4f8e2a1d76805ecd8711f1364e46ab837f2ce7`
**Worktree:** `.slim/worktrees/golden-best-003` (pre-existing, clean; no new worktree)
**Isolated app:** `batch-p8opt1` - production app `stable-modal-comfy-v2-golden-p1` untouched
**Workspace:** Testing 9 / `ws_ee7221847f7d`

---

## 0. Outcome summary

| Phase | Result | Before | After | Correctness | Approved? |
|-------|--------|--------|-------|-------------|-----------|
| 1. GeneralSwitch.INPUT_TYPES bypass | Snapshot-captured schema served from memory | `sampler_prepare` 623.1 ms; 5 calls / 574.9 ms | **`sampler_prepare` 35.3-53.3 ms; 0 calls** | exact SHA `3a6a0306...`, `valid=true`, restore/request = 1/1 | **YES** |
| 2. `triton_key` snapshot warm | Real Triton implementation warmed pre-snapshot | `triton_key` 1 call / 613.8 ms; `get_cache_key` 645.6 ms | **`triton_key` 0 calls; `get_cache_key` 24.9-85.9 ms** | exact SHA, `valid=true`, 1/1 | **YES** |
| 3. Single-file model metadata cache | Built, tested, deployed - **no request-time hit** | `_parse_layout` 351.4 ms self | `_parse_layout` 926.2 -> 5132.9 ms (no elimination) | exact SHA, `valid=true` every run | **NO - reverted** |
| 4. Source health-check lock fast path | Lock-free `_poll_child` + failure check folded into existing locked reads | `_check_child` 313 calls / 443.6 ms / max 238.4; `_FileLock.__enter__` 429.2 ms / max 238.3 | **`_check_child` 3 calls / 1.0 ms / max 0.8; `_FileLock.__enter__` 121.9 ms / max 20.7** | exact SHA, `valid=true`, 1/1 | **YES** |
| 5. PNG encoder benchmark | libspng/oxipng/OpenCV installed and measured; one 1.12x libpng rebind found but fails the cost gate | `_encode_tile` 199.7 ms | unchanged - **Pillow CL1 retained** | n/a (no change made) | **NO_KEEP_PILLOW** |

**3 of 5 phases approved.** Phase 3 is reported honestly below: it was implemented in full,
measured, found not to work, and reverted per the task's failure rule.

**Combined measured saving on the approved phases: about 1,470 ms of serial request wall**
(574.9 ms of `inspect.stack` introspection + 613.8 ms of Triton environment hashing
+ 307.3 ms of health-check lock acquisition), with the exact output SHA preserved on
every accepted run.

---

## 1. Baseline reverification (done first, as required)

- `main` = `9448cdd1c461996e026c59452bd1ef2ddfffd63b` - **has not moved.** Matches the
  stated expected SHA exactly. `main` was **not** reset, and was never checked out or
  modified.
- `production-008` is an **annotated tag**. `git rev-parse production-008` returns the
  *tag object* `e4a61ef8c867a6801a06f90239fcdfe19f7d21e7`, which is not a commit and
  is easy to misread as drift. The dereferenced commit is
  `9448cdd1c461996e026c59452bd1ef2ddfffd63b`. **`main` and `production-008` point at
  the same commit.**
- The repository's primary checkout is on branch `TESTING8` with 71 dirty files,
  including Golden source. It was **not touched**. All work happened in the
  pre-existing clean worktree `golden-best-003`.

### Which profile the baseline actually used

This materially changed the plan and is worth recording.

The checked-in `reports/GOLDEN_EXHAUSTIVE_MULTIPROCESS_PROFILER.md` is the profiler's
*architecture* document; it contains **none** of the specific baseline numbers in the
brief. The authoritative before-state is a trace artifact:

> **baseline profile = `c5fe7cf3e6b2476faaf6618f55191af5`**

Identified by `golden_sampler_prepare = 623.1 ms`, matching the brief's ~623 ms.

Its `raw/golden_telemetry.json` gives the identity that makes a reprofile comparable:

| field | value |
|---|---|
| `golden_mode` | `parallel` |
| entrypoint | `run_golden_parallel_stream` |
| `golden_profile_contract` | `direct_golden_parallel` |
| `attention_backend` | `comfy_kitchen` |
| `workflow_sha256` | `e44389ea2eda82ba5e2324acc08307b6879ed6d4ea4b030727ab044704c0d3b5` |
| v2ctl profile | **`golden_p1_parallel_c0_p8_h100`** (H100!, CPU 12) |
| correctness SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` |

**The first run was discarded for this reason.** An initial attempt used `golden_p1`,
which resolves to `direct_golden_serial` with backend `sage` and correctness SHA
`790c3052...`. That is a *different architecture* (Golden Serial, no CLIP-forward /
UNET-load overlap) and is not comparable to a parallel baseline. It is retained as
trace `8ee88577a16f435d8b27fa0c6a6e4a3b` and excluded from every claim. It also hit the
8,000,000-entry VizTracer capacity, and the local analyzer OOM'd on it. Every
subsequent run used `golden_p1_parallel_c0_p8_h100`.

### Profiler honesty, stated once

Baseline **and** every run in this pass report
`GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE = NO`, reason
`no_root_corrupting_incomplete_calls: incomplete_calls=16`, with
`PROCESS_COVERAGE=UNKNOWN`, `TRACED_PROCESSES=1`. This is identical in the baseline
and after, so it is a pre-existing property of the profiler, not something any phase
introduced. Numbers below are read from `golden_exhaustive_calls.csv.gz` with **exact
qualified-name matching** (not substring), so call counts are authoritative.

---

## 2. Before / after stage table

| stage | baseline `c5fe7cf3` | P1 `2dd0b4e0` | P2 `bd93ddd3` | P3a `e115716` | P3b `55a2a73c` | P4a `0c5ff38a` | **P4b `6d92423e`** |
|---|---|---|---|---|---|---|---|
| `golden_clip_load` | 1944.4 | 5599.2 | 4105.2 | 3605.7 | 5202.0 | 3707.2 | 3667.1 |
| `golden_clip_forward` | 3181.4 | 5880.3 | 5657.5 | 5415.3 | 5233.2 | 4193.1 | 4503.3 |
| `golden_unet_load` | 2854.5 | 6884.3 | 5525.6 | 5662.9 | 9046.3 | 5186.5 | 5477.2 |
| `golden_sampling` | 4510.0 | 4880.5 | 4541.4 | 4799.0 | 4303.6 | 4410.8 | 4572.1 |
| `golden_vae_decode` | 864.9 | 957.8 | 1076.6 | 872.3 | 521.8 | 811.1 | 967.3 |
| `golden_vae_load` | 592.5 | 723.6 | 649.3 | 602.3 | 524.7 | 641.1 | 619.2 |
| **`golden_sampler_prepare`** | **623.1** | **53.3** | **35.3** | **41.2** | **42.4** | **40.6** | **47.1** |
| `golden_output` | 248.0 | 251.1 | 245.7 | 241.9 | 225.8 | 255.0 | 246.7 |
| `golden_request_setup` | 1.7 | 1.9 | 1.9 | 1.9 | 1.8 | 1.9 | 1.7 |
| `golden_restore` | 0.4 | 0.5 | 0.4 | 0.5 | 0.4 | 0.5 | 0.5 |
| `golden_sampler_tail` | 0.1 | 0.0 | 0.0 | 0.1 | 0.0 | 0.1 | 0.0 |
| **ROOT_WALL** | **11405.5** | 18666.5 | 15701.0 | 15261.7 | 19378.8 | 14449.8 | 15013.9 |

`golden_sampler_prepare` fell **623.1 ms -> 35.3 ms** and stayed there across every
subsequent run, deployment and placement. That is the one clean, mechanism-attributable
stage change.

### Placement variance - why no total-request claim is made

Root wall *rose* from 11.4 s to 14.4-19.4 s. That is **not** attributable to the
approved optimizations. All three only remove work; none adds any. The rise is
source/storage placement variance, corroborated by stages no phase touches:

| signal (untouched by the approved phases) | baseline | worst later run |
|---|---|---|
| `wait_ready` max call | 305.8 ms | 1655.2 ms |
| `wait_ready` wall sum | 4410.5 ms | 10167.3 ms |
| `_parse_layout` max call | 194.6 ms | 3527.2 ms |
| `golden_unet_load` wall | 2854.5 ms | 9046.3 ms |

`_encode_tile`, which is pure CPU and touches no storage, is **stable at 199.7 / 197.0
/ 198.1 / 185.2 / 178.4 / 210.0 ms** across all runs - a good control showing the
CPU-bound stages are reproducible while the storage-bound ones swing 5x.

**Consequence:** the ~1,470 ms figure is a sum of three removed CPU stages, not a
measured root-wall delta. Converting it to root wall requires an n>=5 same-deployment
cohort per arm, which this pass did not run (the profiler is single-request by
construction, and the brief forbids mixing profiler timings into unprofiled cohorts).

---

## 3. Before / after top offenders

Exact qualified-name aggregates from `golden_exhaustive_calls.csv.gz`
(`calls / wall_sum / self_sum`):

| function | baseline | P1 | P2 | P4b (final) |
|---|---|---|---|---|
| `GeneralSwitch.INPUT_TYPES` | 5 / 574.9 / 0.1 | **ABSENT** | **ABSENT** | **ABSENT** |
| `INPUT_TYPES` (any) | 100 / 580.5 / 0.5 | 69 / 3.6 / 0.4 | - | - |
| `inspect.stack` | 109 / 590.7 / 0.2 | 104 / 28.6 / 0.2 | - | - |
| `inspect.getouterframes` | 5 / 574.8 / 0.4 | **ABSENT** | **ABSENT** | **ABSENT** |
| `inspect.getframeinfo` | 119 / 574.2 / 1.3 | **ABSENT** | **ABSENT** | **ABSENT** |
| `inspect.getmodule` | 599 / 544.1 / **469.9** | 464 / 2.3 / **2.0** | - | - |
| `inspect.findsource` | 119 / 408.6 / 1.2 | **ABSENT** | **ABSENT** | **ABSENT** |
| `inspect.getsourcefile` | 3418 / 332.7 / 23.6 | **ABSENT** | **ABSENT** | **ABSENT** |
| `triton_key` | 1 / 613.8 / 603.6 | 1 / 737.2 / 710.2 | **ABSENT** | **ABSENT** |
| `get_cache_key` | 1 / 645.6 / 0.0 | 1 / 791.0 / 0.0 | 1 / **54.8** / 0.0 | 1 / **70.8** / 0.0 |
| `precompute_freqs_cis` | 1 / 2083.8 / 105.5 | 1 / 2852.0 / 211.9 | 1 / 2712.8 / 180.3 | 1 / 2854.4 / 256.6 |
| `_parse_layout` | 3 / 351.4 / 341.0 | 3 / 2528.6 / 2526.8 | 3 / 1953.2 / 1951.2 | 3 / 5016.4 / 5014.3 |
| `_clip_meta_state_dict_from_header` | 1 / 211.0 / 205.1 | 1 / 1143.4 / 1135.1 | 1 / 234.8 / 225.2 | 1 / **155.3** / 152.8 |
| **`_check_child`** | **313 / 443.6 / 2.8** | 328 / 189.0 / 4.5 | 318 / 202.5 / 4.9 | **3 / 1.0 / 0.0** |
| **`_poll_child`** | absent | absent | absent | **314 / 108.0 / 1.5** |
| **`_FileLock.__enter__`** | **943 / 429.2 / 429.2 (max 238.3)** | 973 / 94.5 / 94.5 (max 7.5) | - | **637 / 121.9 / 121.9 (max 20.7)** |
| `_FileLock.__exit__` | 943 / 119.9 / 119.9 | 973 / 60.4 / 60.4 | - | 637 / 60.4 / 60.4 |
| `wait_ready` | 309 / 4410.5 / 2.8 | 309 / 10167.3 / 5.2 | 309 / 7688.2 / 4.3 | 309 / 7243.9 / 4.8 |
| `claim_ready` | 309 / 111.9 / 12.7 | 309 / 73.9 / 7.2 | - | 309 / 78.5 / 7.1 |
| `_resolve_ready_block` | 309 / 109.4 / 4.6 | 309 / 109.4 / 7.9 | - | 309 / 84.4 / 8.5 |
| `_recover_ready_from_table` | 1 / 2.3 / 0.0 | 6 / 5.8 / 0.3 | - | 5 / 44.2 / 0.2 |
| `_encode_tile` | 1 / 199.7 / 195.6 | 1 / 197.0 / 192.5 | 1 / 198.1 / 194.0 | 1 / 210.0 / 204.5 |

---

## 4. PHASE 1 - GeneralSwitch.INPUT_TYPES Golden bypass - **APPROVED**

**PHASE_1_APPROVED = YES**

### What the original work served, and what it consumed

Impact Pack's `GeneralSwitch.INPUT_TYPES()`
(`custom_nodes/comfyui-impact-pack/modules/impact/util_nodes.py:17`) builds a constant
schema but calls `inspect.stack()` on every invocation *solely* to test
`stack[2].function == 'get_input_info'`. When that matches, it substitutes an
`AllContainer` so ComfyUI's prompt-time validation accepts any link.

Golden never takes that path - it resolves links itself in
`GoldenSerialRunner._ensure` / `_get_input_data` - yet it paid the full
`inspect.stack()` cost. Resources consumed: **CPU and the GIL, pure introspection, zero
I/O**. `inspect.stack()` materialises `FrameInfo` for every frame via `getouterframes`,
and each `getframeinfo` calls `findsource` / `getsourcefile` / `getmodule`.

The cache identity is structural - `__qualname__ == "GeneralSwitch"` **and**
`__module__` ends with `impact.util_nodes` - so a relocated Impact Pack install is still
recognised and an unrelated node reusing the name is not captured.

### What changed

Three files, 116 added lines:

- `comfymodal_runtime/golden_serial.py` - `_SNAPSHOT_INPUT_TYPES_SCHEMAS`,
  `_input_types_snapshot_key()`, `capture_golden_input_types_schemas()`,
  `golden_input_types()`; the four `class_def.INPUT_TYPES()` call sites
  (`_get_input_data`, `_v3_data`, `_ensure`, `run_closure`) now go through the one
  helper. The two link-traversal loops also stopped rebuilding the schema **per linked
  input**.
- `comfymodal_runtime/modal_app.py` - capture runs in the pre-snapshot sequence, after
  the custom-node registry and the pre-snapshot workers, immediately **before** the
  quiescence proof so that proof observes the final state.
- `comfymodal_runtime/execution_warm.py` - the advisory prewarm uses the same helper,
  so the request-time warm cannot reintroduce the cost.

### Why behavior is equivalent

The captured value is the class's **own** normal schema, produced by calling the real
`INPUT_TYPES()` in the normal Golden context - where `stack[2].function` is not
`get_input_info`, so no `AllContainer` is substituted. Nothing is fabricated.

Correctness never depends on the cache:

```python
def golden_input_types(class_def):
    key = _input_types_snapshot_key(class_def)
    if key is not None:
        schema = _SNAPSHOT_INPUT_TYPES_SCHEMAS.get(key)
        if isinstance(schema, dict):
            return schema
    return class_def.INPUT_TYPES()
```

Any absent, empty, or non-dict entry falls through to the original call.

### Tests - `tests/test_golden_input_types_snapshot.py`, 16 tests

`GeneralSwitch` is reproduced **structurally** (real `inspect.stack()` caller detection,
real `AnyType(str)` wildcard); the third-party package is never imported or modified.

| # | test | proves |
|---|---|---|
| 1 | `test_captured_schema_is_exactly_the_normal_schema` | cached == class's own schema, structurally |
| 2 | `test_cached_lookup_does_not_invoke_inspect_stack` | 25 lookups -> **0** caller detections |
| 3 | `test_capture_only_pays_caller_detection_once` | capture pays it exactly once |
| 4 | `test_capture_is_idempotent` | second capture is a no-op, no re-hash |
| 5 | `test_required_optional_and_hidden_fields_are_present` | `select`, `sel_mode`, `input1`, `unique_id`, `extra_pnginfo` |
| 6 | `test_lazy_flag_is_visible_to_the_runner_input_info_helper` | `_input_info` still reads `lazy` from the cached schema |
| 7 | `test_lazy_selection_still_chooses_the_correct_input` | `check_lazy_status` / `doit` unchanged |
| 8 | `test_falls_back_to_original_when_no_capture_exists` | miss -> real `INPUT_TYPES()` |
| 9 | `test_falls_back_when_cached_value_is_incompatible` | `"not-a-schema"` -> real call |
| 10 | `test_capture_survives_a_raising_class` | one bad class doesn't block a good capture |
| 11 | `test_capture_without_a_node_registry_is_non_fatal` | empty registry safe |
| 12 | `test_non_golden_get_input_info_detection_is_not_monkeypatched` | ComfyUI's own path still gets `AllContainer` |
| 13 | `test_third_party_class_object_is_not_replaced` | `INPUT_TYPES` still the original `classmethod` |
| 14 | `test_no_other_custom_node_input_types_is_memoized` | `RgthreeAnySwitch` -> 3 real calls |
| 15 | `test_unrelated_class_named_general_switch_is_not_captured` | module path must also match |
| 16 | `test_runner_input_paths_use_the_helper` | no remaining direct call in Golden's paths |

### Live evidence

Trace `2dd0b4e01b4b448bad603df2b36571b8`, request `golden-p1-0-f5262d663fb4`

- `validation.output_sha_match = True` - exact `3a6a0306...`
- `valid = true`, `restore_count = 1`, `request_count = 1`
- `valid_count=1 invalid_count=0 dnf_count=0`
- capture guard `state=idle`, `post_capture_guard_pending=false` -> **eligible** observation
- source-probe `RESULT=PASS source_identity=MATCH`, `git_head=d4b9c4f`

### Profile evidence

| metric | before | after | delta |
|---|---|---|---|
| `golden_sampler_prepare` | 623.1 ms | **53.3 ms** | **-569.8 ms (-91.5%)** |
| `GeneralSwitch.INPUT_TYPES` runtime calls | **5** | **0** | eliminated |
| `inspect.stack` from GeneralSwitch | 5 | **0** | eliminated |
| `inspect.getframeinfo` | 119 / 574.2 ms | **absent** | eliminated |
| `inspect.getouterframes` | 5 / 574.8 ms | **absent** | eliminated |
| `inspect.findsource` | 119 / 408.6 ms | **absent** | eliminated |
| `inspect.getsourcefile` | 3418 / 332.7 ms | **absent** | eliminated |
| `inspect.getmodule` self time | 469.9 ms | **2.0 ms** | -467.9 ms |
| any `INPUT_TYPES` wall | 580.5 ms | **3.6 ms** | -576.9 ms |

### New cost introduced

None. The change removes work and adds one dict lookup. Residual `inspect.stack`
(104 calls / 28.6 ms total, max 11.1 ms) is unrelated third-party use elsewhere in
ComfyUI, not GeneralSwitch.

---

## 5. PHASE 2 - `triton_key` snapshot warm - **APPROVED**

**PHASE_2_APPROVED = YES**

### What the original work served, and what it consumed

`triton.runtime.cache.triton_key` is `@functools.lru_cache()`-decorated (no args ->
`maxsize=128`) and hashes the installed Triton software environment: every module under
`triton/compiler`, `triton/backends`, `triton/language`, plus the compiled
`triton/_C/libtriton.<ext>` binary, plus `__version__`. `get_cache_key` calls it
directly.

This is **deployment state, not request state**. Resources: filesystem reads of the
container image plus SHA-256 over tens of MB. Baseline: 613.8 ms self, 645.6 ms through
`get_cache_key`.

### The risk that was checked before implementing

`functools._lru_cache_wrapper.__reduce__` in CPython 3.11 returns only `__qualname__`
(`Modules/_functoolsmodule.c`, `lru_cache_reduce`), so **pickle does not carry the
cache**. If Modal's snapshot were a pickle round-trip, the warm could not survive.
Rather than assume, it was measured: **it does survive.** Modal preserves the live object
state, which is also why Phase 1's module-level dict works.

### What changed

`warm_triton_key()` in `golden_serial.py`, called from the same pre-snapshot sequence,
plus telemetry (`warmed`, `key_length`, `reason`) in
`_restore_timing["snapshot_triton_key_warm"]`.

No fake value, no patched constant, no GPU-specific kernel artifact. Triton changing
invalidates the key through Triton's own process/deployment lifecycle.

### Tests - `tests/test_golden_triton_key_warm.py`, 7 tests

Triton is Linux/CUDA-only, so a synthetic `triton.runtime.cache` is installed built on a
**real** `functools.lru_cache` wrapper - which is the point: the wiring must call the
exact request-time function object and let Triton's own cache serve repeats.

1. `test_warm_invokes_the_exact_triton_key_and_returns_its_value`
2. `test_warm_populates_the_implementation_own_cache_so_repeats_are_served_by_it`
   (10 repeats -> hits=20, misses=1, computed once)
3. `test_warm_produces_no_gpu_specific_kernel_artifact`
4. `test_warm_is_idempotent_and_does_not_rehash` (3 warms -> 1 computation)
5. `test_warm_failure_is_reported_not_raised` (missing Triton -> ModuleNotFoundError)
6. `test_warm_failure_inside_triton_is_reported_not_raised`
7. `test_missing_cache_module_is_reported_not_raised`

### Live evidence

Trace `bd93ddd388404014b9bdd14b8df0ed70`

- `validation.output_sha_match = True`, `valid = true`, `restore_count = 1`, `request_count = 1`
- `valid_count=1 invalid_count=0 dnf_count=0`, capture guard `idle`
- source-probe `RESULT=PASS`, `git_head=cad957e`, deploy fingerprint `3d67ca39...`

### Profile evidence

| metric | before | after | delta |
|---|---|---|---|
| `triton_key` calls | 1 | **0 (absent)** | eliminated |
| `triton_key` wall | 613.8 ms | **0 ms** | -613.8 ms |
| `get_cache_key` wall | 645.6 ms | **54.8 ms** (24.9-85.9 over runs) | **-590.8 ms (-91.5%)** |

**Triton compile remaining:** `get_cache_key` self time is 0.0 ms in every run, so the
residual 54.8 ms is `src.hash()` / `backend.hash()` / `backend_options.hash()` and
env-var sorting, not the environment key. The compile itself is the kernel launch path
and is not separately attributable in this Python-frame-only trace.

**`compute_freqs_cis`** (reported by the profiler as `precompute_freqs_cis`,
`comfy/text_encoders/llama.py:445`):

| run | wall | self |
|---|---|---|
| baseline | 2083.8 ms | 105.5 ms |
| P1 | 2852.0 ms | 211.9 ms |
| P2 | 2712.8 ms | 180.3 ms |
| P4b | 2854.4 ms | 256.6 ms |

It did **not** improve. See section 9.

### New cost introduced

None. 613.8 ms moves to snapshot capture, where container lifetime is long-lived and the
quiescence proof is already the contract.

---

## 6. PHASE 3 - single-file model metadata restore cache - **NOT APPROVED (reverted)**

**PHASE_3_APPROVED = NO**

Implemented in full, unit-tested green, deployed, profiled three times, found not to
deliver, and reverted (`b2c0f82c`, `b8e4cd6b`) per the task's rule for a failed
treatment. No history rewrite, no reset.

### What was built (recoverable from `79a2414e` / `83ae83cd`)

`comfymodal_runtime/golden_metadata_cache.py` plus wiring in
`golden_model_transport.inspect()`, `golden_serial._clip_meta_state_dict_from_header()`,
and restore-time hydration.

- **One normalized representation.** Only `(key, dtype, shape, offset, length)` rows
  plus scalars persist; the header dict is rebuilt on demand, so the same fact is not
  stored twice.
- **One file.** `caching_data/golden_model_metadata.bin`, atomic write via `mkstemp` +
  `fsync` + `os.replace`, pickle protocol 5.
- **Identity = `(st_dev, st_ino, st_size, st_mtime_ns)`**, the same tuple the transport
  already trusts. A hit is a `stat` and performs **no Volume data read** - verified by a
  test that patches `builtins.open` and asserts zero opens.
  *Chosen bound, stated explicitly:* verifying a header hash would require reading the
  header on every request, which is exactly the I/O the cache exists to avoid, and
  would still not cover the payload.
- **Failure policy.** Unknown model, missing/corrupt/foreign-schema cache and publish
  failure all fall through to the original parser. It can only cost time, never
  correctness.

### Why it failed - the decisive measurement

Restore telemetry exposed the hydrate **read-failure branch**: the breakdown contains
`open_read_ms` and `total_ms` but **no `deserialize_ms` and no `models`**, which is the
branch taken when `open()` raises.

| run | restore telemetry |
|---|---|
| P3a cold `e115716` | `{"open_read_ms": 0.210, "total_ms": 0.239}` - file absent, 0 models |
| P3b same deployment, 2nd request `55a2a73c` | `_parse_layout` still **3 calls / 5132.9 ms** |
| after adding `volume_commit()` + `volume_reload()` | `{"open_read_ms": 0.190, "total_ms": 0.201, "volume_reloaded": true}` - still no `models`; `_parse_layout` **3 calls / 5016.4 ms** |

**Root cause, in order of elimination:**

1. *Not the cache path.* `RUNTIME_CONFIG_PATH = "/root/comfymodal_runtime_state"`
   (`comfyapp.py:7013`) is the real runtime-state Volume mount, matching the cache root.
2. *Not a missing commit.* Adding the repo's own write-then-commit pattern
   (`comfyapp.py:3180 runtime_config_volume.commit()`) plus `reload()` before the read
   changed nothing.
3. **The publisher cannot win against container teardown.** Golden is single-use
   (`SINGLE_USE_CONTAINERS=1`, `min_containers=0`). The design published from a
   coalescing daemon thread 50 ms after a miss, then committed. The request ends almost
   immediately and the container exits; the thread and the commit never complete.

This makes the brief's "publish/update the persistent file **outside the request
critical path**" **structurally incompatible with single-use Golden containers** for
this workload. That is the finding worth keeping; it applies to any future
off-critical-path Volume cache here.

As shipped the cache added a per-request thread plus a commit attempt for **zero**
measured benefit, so leaving it in would have been a net negative. Hence the revert.

### What did pass

- **Hydration budget: met with ~200x margin.** 7 independent restores:
  **min 0.258 ms / p50 0.290 ms / max 0.473 ms / mean 0.320 ms** against the 75 ms target.
- **Cache file size: 86,550 bytes** for three 600-tensor models; one file, not a forest.
- **14 unit tests** covering exact cached-vs-original equivalence (tensor map *and*
  rebuilt header), unknown-model miss, same-pathname-rewritten invalidation,
  per-component identity perturbation, zero-payload-read-on-hit,
  missing/corrupt/foreign-schema cache, publish failure counted, single-file shape,
  size, and the hydration benchmark.
- Correctness held throughout: every Phase 3 run reported `output_sha_match=True`,
  `valid=true`, `restore_count=1`, `request_count=1`.

### Required redesign (not implemented - needs Ahmed's decision)

Seed the cache **at snapshot capture**, where the container is long-lived and quiescence
is already proven, using the same `put()`/`publish()` API. That is the mechanism
empirically proven to survive restore by Phases 1 and 2. Contract model *paths* must be
resolved at capture (currently only `unet_identity` / `clip_identity` / `vae_identity`
**name refs** exist, via `restore_plan.py:235-237`). Alternatively, publish
**synchronously** inside the request and accept the cost - which the brief explicitly
forbids. I did not choose between these.

### Also worth recording

`_clip_meta_state_dict_from_header` baseline 211.0 ms is **not** header parsing:
`parse_safetensors_header` was only 5.6 ms. The 205.1 ms self is
`torch.empty(shape, dtype=..., device="meta")` per tensor - inherent meta-tensor
construction. Caching the header cannot remove it. This lowers Phase 3's realistic
ceiling well below the 351 ms + 211 ms the brief assumed.

---

## 7. PHASE 4 - source health-check lock fast path - **APPROVED**

**PHASE_4_APPROVED = YES**

### What the original work served, and what it consumed

`wait_ready` called `_check_child()` on **every** blocking iteration, and `_check_child`
acquired the process-shared control lock (`_FileLock`) to read the header and the failure
counter at `header[10]`. Baseline: 313 calls, 443.6 ms inclusive, max single call
**238.4 ms**, self 2.8 ms - and `_FileLock.__enter__` totalled **429.2 ms** across 943
calls, max 238.3 ms. So **~97% of health-check wall was lock acquisition, not
`proc.poll()`**.

That lock is also what source workers need to claim slots and publish READY
(`claim_block`, `publish_ready`), so the parent could stall behind it exactly when the
pipeline was busiest. Resources: one process-shared `flock` per call, contending with 4
reader threads.

### Why the fast path is safe - failure publication audited first

The brief required proving this rather than assuming it. The child publishes failure on
two channels:

| site | channel 1 (`header[10]` + error) | channel 2 (`emit` fatal) | then |
|---|---|---|---|
| reader loop exceptions (1780, 1796) | `fail_control(...)` + `fatal.append(...)` | supervisor emits at 2066 | supervisor returns 1 |
| supervisor terminal block (2064-2066) | `fail_control(fatal[0])` | `emit({"op":"fatal",...})` | returns 1 |
| supervisor exception (2070-2072) | - | `emit({"op":"fatal",...})` | returns 1 |

**Every site that raises `header[10]` is paired with an emitted `fatal` line, and the
child then exits non-zero.** So the parent observes the failure either as a `fatal`
operation on the pipe or as EOF in `_read_message`. `header[10]` exists only to carry
the error *detail* when the message is lost - which is why it is now inspected wherever
the header is read anyway.

### What changed

`golden_source_threads.py`, across two commits (`e287080`, `0f4f8e2a`):

- **`_poll_child()`** (new) - the lock-free hot path: `proc.poll()` only, plus a
  `health_poll_count` telemetry counter.
- **`_raise_if_failed(header)`** (new) - fail-closed on `header[10]`, called with the
  lock already held.
- **`_check_child()`** - **signature and behavior unchanged** (an existing test stubs it
  with a zero-arg lambda; the first attempt passed a keyword and broke that, which the
  test caught). Still used by `wait_quiescent` and any caller needing a standalone
  authoritative check.
- **`wait_ready()`** - `_poll_child()` in the loop; the duplicate pre-wait check removed.
- **`_resolve_ready_block()` / `_recover_ready_from_table()`** - call
  `_raise_if_failed(header)` where they already read the header.

Slot-generation correctness, READY/IN_FLIGHT ownership, H2D completion gating,
stale-generation handling, doorbell-loss recovery and fail-closed timeout behavior are
untouched.

### The first attempt failed, and that is the interesting part

Commit `e287080` moved the authoritative check from every iteration to once per
`wait_ready` entry. Measured on trace `0c5ff38a44cc4d71991e6b745f6719f0` (output SHA
exact): **no improvement** - `_FileLock.__enter__` 945 calls / 431.2 ms / **max 241.9
ms**.

Root cause: `wait_ready` runs roughly **one loop iteration per call**, because the
doorbell almost always arrives before the 0.25 s slice expires. So one entry check costs
exactly what one per-iteration check cost. The entry check was a *duplicate* -
`wait_ready` is about to read the header under the lock in `_resolve_ready_block`.
Commit `0f4f8e2a` folds the failure check into those existing locked reads instead.

### Tests - `tests/test_c0_source_health_fastpath.py`, 18 tests

| # | required case | test |
|---|---|---|
| - | healthy path / hot-path proof | `test_healthy_blocking_wait_takes_no_health_check_lock`, `test_authoritative_check_still_takes_the_lock_exactly_once`, `test_healthy_wait_ready_does_not_lock_between_iterations` |
| 1 | child process exit | `test_child_process_exit_is_detected_on_the_fast_path`, `test_child_process_exit_is_detected_before_wait_ready_blocks` |
| 2 | explicit fatal message | `test_fatal_message_still_raises_from_wait_ready` |
| 3 | shared header error, live child | `test_shared_header_error_with_live_child_is_still_reported`, `test_shared_failure_is_reported_from_the_path_that_reads_the_header`, `test_shared_failure_is_reported_by_the_timeout_recovery_path` |
| 4 | dropped / coalesced doorbell | `test_dropped_doorbell_is_recovered_from_the_slot_table`, `test_coalesced_doorbell_that_resolves_to_nothing_still_recovers` |
| 5 | stale READY generation | `test_stale_ready_generation_cannot_be_claimed` |
| 6 | stale plan generation | `test_stale_plan_generation_cannot_be_claimed`, `test_stale_release_generation_is_rejected` |
| 7 | timeout | `test_timeout_path_performs_the_authoritative_check` |
| 8 | no READY slot orphan | `test_claim_marks_in_flight_before_any_release_is_possible` |
| 9 | no double release | `test_no_double_release_and_no_orphan_ready_slot` |
| 10 | no H2D-before-ready | `test_claim_marks_in_flight_before_any_release_is_possible` (IN_FLIGHT is owned, so recovery yields `None`) |
| 11 | no release-before-H2D-completion | `test_slot_cannot_be_released_before_h2d_completion_ownership` |

**Discrimination proven:** running this file against the pre-fix
`golden_source_threads.py` fails 3 tests
(`test_healthy_blocking_wait_takes_no_health_check_lock`,
`test_healthy_wait_ready_does_not_lock_between_iterations`,
`test_child_process_exit_is_detected_on_the_fast_path`) and passes 15, so the hot-path
proof actually measures the change.

### Live evidence

| run | trace | deploy fp | `output_sha_match` | `valid` | restore/req | guard |
|---|---|---|---|---|---|---|
| P4a | `0c5ff38a44cc4d71991e6b745f6719f0` | `3b099ac1...` | **True** | true | 1 / 1 | idle |
| P4b (final) | `6d92423e98c547ec8e73c8a93b0d2ce7` | `dbf7d50a...` | **True** | true | 1 / 1 | idle |

Both `valid_count=1 invalid_count=0 dnf_count=0`, source-probe `RESULT=PASS`.

### Profile evidence - the 238 ms stall is gone

| metric | baseline | P4a | **P4b (final)** |
|---|---|---|---|
| `_check_child` calls | 313 | 312 | **3** |
| `_check_child` wall / max | 443.6 / 238.4 ms | 485.4 / 242.1 ms | **1.0 / 0.8 ms** |
| `_poll_child` calls / wall / self / max | - | 313 / 42.9 / 1.4 / 6.9 | **314 / 108.0 / 1.5 / 6.2** |
| `_FileLock.__enter__` calls | 943 | 945 | **637** |
| `_FileLock.__enter__` wall | 429.2 ms | 431.2 ms | **121.9 ms (-307.3 ms, -71.6%)** |
| `_FileLock.__enter__` **max** | **238.3 ms** | 241.9 ms | **20.7 ms (-91.3%)** |
| `_FileLock.__exit__` wall / max | 119.9 / 7.4 ms | 86.2 / 5.8 | **60.4 / 8.7 ms** |
| `claim_ready` wall | 111.9 ms | 104.3 ms | 78.5 ms |
| `_resolve_ready_block` wall | 109.4 ms | 99.2 ms | 84.4 ms |

Lock acquisitions dropped by exactly 306 (943 -> 637) - the removed health-check
acquisitions - and the 238 ms tail stall is gone, replaced by a 20.7 ms worst case.

### New cost introduced

`_poll_child` costs 1.5 ms self over 314 calls (max 6.2 ms) - that *is* the new cost, and
it replaces 429 ms of lock acquisition. Net **-307 ms**.

### A/B/C classification: still **not determinable**

`_check_child` and the lock stall were removed, but that is **control-plane** cost and the
brief forbids claiming the source got faster because control wait fell. The brief's
required metrics - `capacity_wait_count`, `capacity_wait_ns`, `slot_acquire_wait_ns`,
`all_slots_occupied_count`, `ready_queue_wait_ns`, `effective_reader_concurrency`,
`time_weighted_reader_concurrency`, CLIP/UNET source GB/s, and the source-final-byte ->
GPU-ready tail - **were not collected**, and `wait_ready` wall (4410.5 -> 7243.9 ms across
placements) remains placement-confounded.

**Reporting UNKNOWN rather than guessing.** What *is* established: the parent no longer
contends for the source lock merely to check health, so the A/B backpressure mechanism is
structurally weaker than before. Separating A from B from C needs the telemetry above.

---

## 8. PHASE 5 - PNG encoder benchmark - **NO_KEEP_PILLOW**

**PHASE_5_APPROVED = NO_KEEP_PILLOW.** No code changed; Golden still uses Pillow
`compress_level=1`. `KEEP PILLOW` is an explicitly valid outcome.

### Candidates researched and actually installed and measured

An earlier draft of this section tested only what happened to be pre-installed. That was
the wrong candidate set - the brief asks for the *fast* encoders, which are precisely the
ones not already present. All of the following were installed into an isolated venv
(Python 3.11, Windows/x86-64 host) and benchmarked:

| candidate | pip name | native lib | install | import delta |
|---|---|---|---|---|
| Pillow | `pillow` | libpng + zlib | already present | +33 ms |
| **libspng** | `imagecodecs` (`spng_encode`) | libspng | 43.9 MB native | +92 ms |
| **libpng (2nd binding)** | `imagecodecs` (`png_encode`) | libpng | (same 43.9 MB) | (same +92 ms) |
| **Rust oxipng / libdeflater** | `pyoxipng` | Rust oxipng | small | +4 ms |
| OpenCV | `opencv-python-headless` | libpng | already present | +86 ms |
| zopfli | `zopfli` | Google Zopfli | installed; **not a PNG encoder** (zlib primitive only, no chunk/CRC/filter writer) | - |
| pypng | `pypng` | pure Python | **not competitive** - excluded on principle | - |
| `pikepng`, `simple-png` | - | - | **no installable PyPI package exists** (the name "simple PNG" is libspng's expansion) | - |
| `optipng` / `pngcrush` / `advpng` | - | CLI only | subprocess in the output tail; not a request-path encoder | - |
| `turbojpeg` / `mozjpeg` | - | JPEG | **JPEG only, not PNG** | - |

`pyoxipng` level 2 with `Deflaters.zlib(1)` errored (`AttributeError` on
`Deflaters.zlib`) and is excluded; its `libdeflater` and default paths were measured.

### A. Real batch images (1280x720 RGB, 7 reps, median of per-image medians)

| encoder / settings | median ms | p90 ms | bytes | size d% | speedup | exact px |
|---|---|---|---|---|---|---|
| **Pillow CL1 (PRODUCTION CONTROL)** | 22.27 | 24.92 | 1,436,895 | +0.00 | 1.00x | **True** |
| Pillow CL0 | 20.57 | 23.03 | 5,532,984 | **+285.07** | 1.08x | True |
| Pillow CL3 | 25.03 | 25.95 | 1,013,047 | -29.50 | 0.89x | True |
| **imagecodecs libpng CL1** | **19.84** | 23.23 | 1,433,338 | **-0.25** | **1.12x** | **True** |
| imagecodecs libspng CL1 | 49.84 | 57.35 | 1,076,748 | -25.06 | 0.45x | True |
| imagecodecs libspng CL3 | 61.51 | 64.46 | 1,050,174 | -26.91 | 0.36x | True |
| pyoxipng level0 | 63.99 | 68.23 | 990,833 | -31.04 | 0.35x | True |
| pyoxipng level1 | 132.79 | 138.42 | 944,089 | -34.30 | 0.17x | True |
| pyoxipng level2 libdeflater1 | 56.45 | 57.41 | 1,016,422 | -29.26 | 0.39x | True |
| OpenCV CL1 | 26.59 | 26.87 | 1,075,960 | -25.12 | 0.84x | **False** |

### B. Scale probes (synthetic, 3 reps)

Production `_encode_tile` is ~196 ms. The 2048x2048 probe measures **200.72 ms** for
Pillow CL1, which is strong evidence the production output is around **2048x2048
(4.2 Mpixel)** - the 1280x720 real images understate the stage by roughly 9x.

| encoder / settings | 2048x2048 median ms | d% | speedup | 1024x1024 median ms | d% | speedup |
|---|---|---|---|---|---|---|
| **Pillow CL1 (CONTROL)** | 200.72 | +0.00 | 1.00x | 47.06 | +0.00 | 1.00x |
| Pillow CL0 | 104.54 | -0.66 | **1.92x** | 25.49 | -0.68 | **1.85x** |
| Pillow CL3 | 259.03 | -35.68 | 0.77x | 62.78 | -35.64 | 0.75x |
| **imagecodecs libpng CL1** | **176.52** | **+0.13** | **1.14x** | **41.99** | **+0.13** | **1.12x** |
| imagecodecs libspng CL1 | 327.28 | -30.67 | 0.61x | 82.88 | -30.62 | 0.57x |
| pyoxipng level0 | 301.56 | -36.94 | 0.67x | 78.33 | -36.92 | 0.60x |
| pyoxipng level2 libdeflater1 | 305.62 | -35.77 | 0.66x | 88.73 | -35.77 | 0.53x |
| OpenCV CL1 | 269.09 | -30.67 | 0.75x | 66.49 | -30.62 | 0.71x |

**The synthetic probes are noise-dominated and therefore invalid for judging
`compress_level`.** Random-noise images barely compress at any level, which is why CL0
appears 1.9x faster at essentially unchanged size there. On the **real** images CL0 costs
**+285%** bytes. Only the real-image table may be used to judge compression level.

### Findings

1. **The premise that libspng and oxipng are faster did not hold.** At compression level 1
   both are **1.6x-2.9x slower** than Pillow on every size tested, while choosing better
   filters and producing 25-37% smaller files. They are optimizers; they trade latency for
   size, which is the opposite of what this stage needs.
2. **Exactly one candidate beats the control on speed:** `imagecodecs.png_encode` (a second
   libpng binding), at **1.12x-1.14x** with size within **+/-0.25%** and exact pixels. It is
   a genuine, reproducible win on the encode itself.
3. **It still fails the deployment-cost gate.** At production scale it saves
   200.72 - 176.52 = **24.2 ms** on a ~14,450 ms request: **0.17% of request wall**. The
   price is **+43.9 MB of native binaries** and **+92 ms of import**, for a multi-codec
   package whose only relevant function is a second libpng binding. That fails
   "dependency/runtime complexity is reasonable" and "deployment/package cost is
   acceptable" for a 0.17% gain.
4. **Pillow CL1 remains the efficient point of its own curve** on real content: CL0 buys
   8% for +285% bytes; CL3 costs 12% more wall for -29.5% bytes.
5. **OpenCV is not pixel-exact as invoked** (`cv2.imencode` reads its input as BGR, so an
   RGB array is stored channel-swapped) and is 0.84x. This is a harness convention, **not a
   claim that OpenCV is lossy**, and it is slower anyway.

**Decision: KEEP PILLOW.** A 0.17%-of-request speedup does not justify +43.9 MB and
+92 ms import for one function.

### Stated limitations

- The benchmark images are batch `d7r2` originals at 1280x720, **not confirmed Golden
  outputs**; no real Golden output PNG exists on disk. The 2048x2048 / 1024x1024 probes are
  synthetic and only valid for size-scaling, not compression-level decisions.
- Host is Windows/x86-64; the production image is Linux. libspng's multithreading and
  oxipng's parallelism behave differently on Linux, which could narrow - though on these
  numbers, most likely not reverse - their latency deficit.
- Only Pillow and OpenCV were present in the production image, so only they have a
  measured *in-container* number; the others are host measurements.
- Decode wall was not separately benchmarked; no candidate warranted it.

### If someone wants to revisit this

The one open thread is `imagecodecs.png_encode`: it is real but small. The way to make it
worthwhile would be to confirm the win **in-container on Linux at the real output
dimensions**, and to price `imagecodecs` against simply vendoring a minimal libspng
binding instead of the full multi-codec wheel. Until then it does not clear the cost gate.

---

## 9. `compute_freqs_cis` decision - recommendation only, as required

**No RoPE cache was implemented.** The brief asked for this analysis *after* first-use
Triton pollution was removed, and that removal is now measured.

1. **How long now?** 2712.8-2854.4 ms wall across the post-Phase-2 runs, vs 2083.8 ms
   baseline. It did not improve; it is if anything worse in this placement.
2. **Actual recurring math vs Triton behavior?** Self time is only 180.3-256.6 ms. The
   other ~2.5 s is children - dominated by `Llama2_.forward` -> `apply_rope` -> Triton
   dispatch, i.e. **kernel launch/compile behavior, not recurring arithmetic**. 17
   `Attention.forward` calls at 411.6 ms inclusive.
3. **Exact inputs:** `precompute_freqs_cis` derives from `theta` (RoPE base) and the
   sequence length/positions of the current `position_ids`.
4. **In this Qwen workflow:** `position_ids` derive from the CLIP tokenizer output, which
   is fixed for this canonical workflow (`workflow_sha256 = e44389ea...`, `forced_miss`
   conditioning cache, `fresh_required=true`). Sequence length and padding are fixed for
   a given workflow, **but I did not verify that from source** - `comfy/text_encoders/llama.py`
   is not in this repository, so this is an inference from the workflow identity, not a
   measurement.
5. **Would precompute + slice be equivalent?** Only if `theta`, dtype and max sequence
   length are invariant across requests. Since (4) is unverified, **equivalence is
   unproven.**
6. **Memory:** for `theta=10000`, head_dim 128, seq 4096, fp32 -> about 2 MB per table,
   in complex or split form. Negligible.

**Recommendation:** do **not** build it yet. The honest next step is one more instrumented
run that records whether the ~2.5 s is first-call compile (cold Triton kernel cache per
container) or steady-state per-call launch overhead. Because Golden is single-use, the
Triton *disk* cache may not even persist - which would make this a kernel-cache problem,
not a RoPE-table problem. **A RoPE table is the wrong lever until that is separated.**

---

## 10. Compiled Triton kernel decision - recommendation only, as required

**No persistent Triton-kernel Volume cache was built.**

1. **Does the kernel still compile after the warm?** `triton_key` is gone, but
   `get_cache_key` still runs (24.9-85.9 ms) and `precompute_freqs_cis` still spends
   ~2.7 s, so **yes, compilation/launch work remains**.
2. **Compile wall remaining:** not separately attributable. This profiler traces Python
   frames only (`ignore_c_function=True`); Triton compile happens in C/CUDA and reads as
   waiting. Reported as UNKNOWN rather than guessed.
3. **Triton cache directory byte increase:** **not measured.**
4. **Identity controlling reuse:** Triton version + hash of every `triton/compiler`,
   `triton/backends`, `triton/language` module + `libtriton` binary (`triton_key`), plus
   `src.hash()`, `backend.hash()`, `backend_options.hash()` and sorted
   cache-invalidating env vars (`get_cache_key`). PyTorch/CUDA/toolkit and GPU
   architecture enter through the backend and options, not through `triton_key`.
5. **Can the exact kernel be warmed at capture?** **Unknown - not tested.** It would need
   CUDA at capture, and `comfy-modal-core` section 7 forbids introducing CUDA into a CPU
   snapshot-capture path unless the snapshot design explicitly changes.
6. **Would that warm state survive restore?** The snapshot currently proves **no CUDA
   initialization** (Phase 2 proved only *non-CUDA* Python state survives). A CUDA warmup
   would be a new, separately-justified design change.
7. **Alternative:** warm at restore and overlap. Restore must stay minimal, so this needs
   measurement of restore headroom first.

**Recommendation:** measure (2) and (3) before proposing anything. The single-use
container lifecycle - the same constraint that broke Phase 3 - means a *disk* Triton cache
may not persist either, in which case per-container compile is structural and the answer
is a different image/caching strategy, not a Volume cache.

---

## 11. Restore cache timing table

Phase 3's cache (reverted, retained for the redesign):

| observation | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| hydration ms | 0.332 | 0.271 | 0.336 | 0.561 | 0.385 | 0.378 | 0.387 |

Second run of the same benchmark: 0.473 / 0.313 / 0.287 / 0.266 / 0.258 / 0.352 / 0.290.

- **min 0.258 ms / p50 0.290 ms / max 0.473 ms / mean 0.320 ms**
- Cache file: **86,550 bytes**, three 600-tensor models, one file
- Budget 75 ms -> **PASS on every observation**
- Live restore hydration (`metadata_cache` telemetry): 0.239 ms cold, 0.064 / 0.201 ms warm

These measure **hydration only**. The failure was not hydration cost; it was that the file
was never visible to the next container.

---

## 12. PNG benchmark table

Produced - full tables in section 8, machine-readable in
`reports/png_benchmark_p8opt1.json`. Headline findings:

- **The premise that the fast encoders are faster did not hold at compression level 1.**
  libspng (`imagecodecs.spng_encode`) is **1.6x-2.2x slower** than Pillow CL1 and Rust
  oxipng (`pyoxipng`) is **1.5x-2.9x slower**, on every size tested. Both produce
  25-37% smaller files - they are optimizers trading latency for size.
- **Exactly one candidate beat the control:** `imagecodecs.png_encode`, a second libpng
  binding, at **1.12x-1.14x** with size within **+/-0.25%** and exact decoded pixels.
- **It still fails the cost gate:** 24.2 ms saved at production scale (2048x2048) on a
  ~14,450 ms request = **0.17% of request wall**, in exchange for **+43.9 MB** of native
  binaries and **+92 ms** import.
- Pillow CL1 remains the efficient point of its own curve: CL0 buys 8% for **+285%**
  bytes on real content.
- Calibration: production `_encode_tile` ~196 ms matches the measured **200.72 ms** for
  Pillow CL1 at **2048x2048**, so the production output is about 2048x2048.

**Decision: KEEP PILLOW.**

---

## 13. Source diagnosis

**UNKNOWN.** See section 7. The Phase-4 fix removed the parent's health-check contention
for the source lock (`_FileLock.__enter__` 429.2 -> 121.9 ms, max 238.3 -> 20.7 ms),
which weakens the A/B backpressure mechanism structurally, but the brief's
capacity/concurrency/GB-s telemetry was not collected, so A vs B vs C remains unseparated.

What can be stated: the **source pipeline is not the only limiter**, and `_check_child`'s
authoritative-lock-per-wait pattern (443.6 ms, 97% of it lock acquisition) was a real
*structural* backpressure risk, now removed.

---

## 14. Remaining optimization candidates, ranked by recoverable critical-path wall

Ranked by **recoverable serial request wall**, accounting for overlap. A stage fully
hidden behind a longer sibling yields nothing even if optimized.

| # | target | measured cost | overlap-aware recoverable | status |
|---|---|---|---|---|
| 1 | **Triton first-use compile inside `precompute_freqs_cis`** | ~2.7 s, self only 0.18-0.26 s | **High if on the critical path and not overlapped.** Must first separate compile from launch | needs measurement |
| 2 | **Health-check lock acquisition** | 429.2 ms, max 238.3 ms | **-307.3 ms CONFIRMED** | **DONE (Phase 4)** |
| 3 | **`triton_key` environment hashing** | 613.8 ms | **-590.8 ms CONFIRMED** | **DONE (Phase 2)** |
| 4 | **GeneralSwitch / `inspect.stack` introspection** | 574.9 ms | **-569.8 ms CONFIRMED** | **DONE (Phase 1)** |
| 5 | **`_parse_layout` header JSON parse** | 341.0 ms self (CLIP 194.6 / UNET 97 / VAE 60) | ~341 ms, but see section 6: ceiling is lower once meta-tensor construction is excluded | blocked on redesign |
| 6 | **`_clip_meta_state_dict_from_header`** | 205.1 ms self | **Low ceiling** - 200.6 ms is `torch.empty(..., device="meta")`, not parsing | low value |
| 7 | **Pillow PNG encode** | 195.6 ms | ~195 ms, on the critical path, low measurement noise - **but no candidate beats it** (section 8) | **closed, keep Pillow** |
| 8 | **Source read / backpressure** | `unet_load` 2854-9046 ms, `clip_load` 1944-5599 ms | Potentially the largest pool, but **entirely placement-dominated** and not separable from A/B/C | needs telemetry |

**Ranking notes.** The three completed wins are serial, non-overlapped, CPU-bound stages,
so their wall reduction is straightforwardly recoverable. Items 5 and 6 sit inside the
storage-bound load stages and are placement-confounded. Item 8 is the largest pool and the
least understood: with `unet_load` swinging 2854 to 9046 ms across placements, it
dominates everything else combined, and no treatment should be designed until A/B/C is
separated.

**On ranking by inclusive wall:** `WrapperExecutor.execute` (19,969 ms inclusive over 59
calls) and `BaseEventLoop._run_once` (12,196 ms) head the raw inclusive table and are pure
wrappers - near-zero self time. They are not targets. `SourcePlanBridge` was likewise
excluded: its large inclusive time mostly encloses genuine waiting for source blocks
(self 2.45-3.58 ms).

---

## 15. Before / after Gantt

Per-stage ASCII Gantts were rendered for every run (`golden_stage_gantts.md`). The three
approved phases target serial, non-overlapped CPU stages, so their effect is a visible
shrink of the `golden_sampler_prepare` band and the absence of the health-check lock stall
inside `unet_load`:

```
BASELINE c5fe7cf3 (ROOT 11405.5 ms)     P2 bd93ddd3 (ROOT 15701.0 ms)
 restore   [                            restore   [
 setup     [                            setup     [
 clip_load [=============                clip_load [===================
 clip_fwd  [================             clip_fwd  [=================
 unet_load [===============              unet_load [=================
 samp_prep [==========                   samp_prep [
 sampling  [=================             sampling  [================
 vae_load  [===                          vae_load  [==
 vae_dec   [=====                        vae_dec   [====
 output    [                             output    [
```

`samp_prep` narrows from 10 columns to 1; every other band is unchanged *in shape*. The
longer total width of the P2 drawing is placement variance (section 2), not a regression
from these phases.

---

## 16. Whole-request checks

| check | result |
|---|---|
| Total Golden wall | 11405.5 ms baseline; 14449.8-19378.8 ms after (placement-confounded, section 2) |
| Stage Gantt | rendered for all runs (`golden_stage_gantts.md`) |
| Cross-thread/process overlap | `THREAD_COVERAGE = COMPLETE`, lanes 18/18; `CLOCK_ALIGNMENT = PROVEN`, max skew 0 ns |
| Correctness SHA | **exact `3a6a0306...` on every accepted run (9 runs)** |
| Pixel identity | not separately established; the encoded SHA matched exactly, which is stronger |
| Fallback count | 0 on all runs; no silent fallback reported |
| Failures / DNF | 0 DNF; `invalid_count=0` |
| Snapshot-capture eligibility | capture guard `idle` on every accepted run |
| Traced processes | 1 (`parent`) - `PROCESS_COVERAGE=UNKNOWN` in baseline **and** after |

---

## 17. Evidence index

| artifact | role |
|---|---|
| `artifacts/golden_exhaustive_runs/c5fe7cf3e6b2476faaf6618f55191af5/...` | **authoritative baseline** |
| `.../2dd0b4e01b4b448bad603df2b36571b8/...` | after Phase 1 |
| `.../bd93ddd388404014b9bdd14b8df0ed70/...` | after Phase 2 |
| `.../e115716391934c378103bbe868b2ad97/...` | Phase 3 cold (no cache file) |
| `.../55a2a73cd98f483c898af2fd29085636/...` | Phase 3, 2nd request same deployment - proves failure |
| `.../71aac83ad07441a5a75eeba0b393ea5d/...` | Phase 3 fix, seed request |
| `.../fb36162440df47938fa94a2789bd2319/...` | Phase 3 fix, fresh deployment - proves commit did not help |
| `.../0c5ff38a44cc4d71991e6b745f6719f0/...` | Phase 4 attempt A - proves entry-check was a duplicate |
| `.../6d92423e98c547ec8e73c8a93b0d2ce7/...` | **Phase 4 final** |
| `.../8ee88577a16f435d8b27fa0c6a6e4a3b/...` | **invalid**, serial `golden_p1`, excluded from all claims |
| `reports/png_benchmark_p8opt1.json` | Phase 5 Pareto data |
| `reports/POST_P8_PASS1_EVIDENCE_LOG.md` | working evidence log |

---

## 18. Commits on `opt/p8-profile-cleanup-1`

```
0f4f8e2a perf(golden-source): drop the duplicate pre-wait lock acquisition  [Phase 4]
e287080c perf(golden-source): poll liveness instead of locking per wait      [Phase 4]
b2c0f82c Revert "perf(golden): cache parsed safetensors metadata ..."        [Phase 3]
b8e4cd6b Revert "fix(golden): commit and reload the metadata-cache Volume"   [Phase 3]
83ae83cd fix(golden): commit and reload the metadata-cache Volume           [Phase 3, failed]
79a2414e perf(golden): cache parsed safetensors metadata in one restore file [Phase 3, failed]
cad957eb perf(golden): warm Triton's environment key before the snapshot     [Phase 2, APPROVED]
d4b9c4fb perf(golden): serve Impact Pack GeneralSwitch schema from the snapshot [Phase 1, APPROVED]
9448cdd1 (production-008)
```

Net diff vs `production-008`: `golden_serial.py`, `modal_app.py`, `execution_warm.py`,
`golden_source_threads.py`, `tests/test_golden_input_types_snapshot.py`,
`tests/test_golden_triton_key_warm.py`, `tests/test_c0_source_health_fastpath.py`.

Not done, as required: no merge to `main`, no `production-009` tag, no commit to `main`, no
push, no worktree created, no file/branch/tag deletion, no reset, no third-party
custom-node modification.

**Regression suite:** `pytest tests -m fast_unit` -> **563 passed, 2 failed, 7 skipped**.
The 2 failures are `tests/test_rx9p_h_identity_chain.py::test_success_path_exact` and
`::test_compact_nested_sage_observation_is_mismatch`, documented as **PRE-EXISTING** in
`reports/PRODUCTION_008_ACCEPTANCE.md` section 5 and reproduced on this branch without any
of my changes. **New regressions: 0.**

---

## 19. What I would do next, in order

1. **Separate Triton compile from steady-state launch** with one instrumented run. Both
   the `compute_freqs_cis` and the compiled-kernel questions collapse onto that one
   measurement, and the single-use-container finding means the answer may be
   "per-container compile is structural", which would change the recommendation entirely.
2. **Phase 3 redesign** - seed at snapshot capture (needs contract model *paths*, not name
   refs). Note the realistic ceiling is ~341 ms, not 552 ms, once meta-tensor
   construction is excluded.
3. **Collect the source A/B/C telemetry** (`capacity_wait_*`, reader concurrency,
   CLIP/UNET GB/s, final-byte-to-GPU-ready tail). It is the largest remaining pool
   (`unet_load` 2.9-9.0 s) and the least understood. Only after that is a source-geometry
   treatment defensible.
4. **Phase 5 revisited** - capture a real Golden output PNG first, then benchmark at
   production dimensions. The measurement noise on this stage is the lowest in the system,
   so a real winner would be easy to confirm.
5. **Establish a placement-controlled comparison** before any total-request claim. Every
   storage-bound stage in this pass swung 5x between placements, which currently makes
   root-wall comparisons across deployments meaningless.

---

## 20. Counted acceptance cohort: 10 unprofiled runs, all optimizations on

Run after the five phases, on the correct Production-008 profile with the profiler
**OFF**, so these are ordinary performance observations and not diagnostic timings.

| item | value |
|---|---|
| profile | `golden_p1_parallel_c0_p8_h100` (H100!, CPU 12) |
| entrypoint | `run_golden_parallel_stream`, `golden_mode=parallel` |
| attention backend | `comfy_kitchen` |
| expected output SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` |
| source | `opt/p8-profile-cleanup-1` @ `9c27b4e216dee9cb3f30ddbfb43920c7e3fa176c` |
| deploy fingerprint | `6a4f7331b5d5b71a1f53fed13d5ebba585968bb946d524682dbc67658f19428d` |
| source-probe | `RESULT=PASS source_identity=MATCH` (`git_head=9c27b4e216de`) |
| gate | `verdict=ACCEPT`, manifest `gate_20261002-162940_a5d8af69.json` |
| confirm | `confirm_20261002-163516_a5d8af69.json`, `reasons=[]`, `verdict=ACCEPT` |
| optimizations in this build | Phase 1 + Phase 2 + Phase 4 (Phase 3 reverted, Phase 5 no-op) |

### Profiler confirmed OFF for this profile

Resolved before deploying, none of these were overridden:

| flag | value | source |
|---|---|---|
| `COMFYMODAL_V2_FULL_TRACE` | 0 | profile |
| `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS` | 0 | profile |
| `COMFYMODAL_V2_E27_FORENSICS` | 0 | profile |
| `COMFYMODAL_GOLDEN_C0_WINDOW_TRACE` | 0 | profile |
| `COMFYMODAL_SAMPLING_DEEP_PROFILE` | off | profile |
| `COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER` | 0 | default |
| `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN` | 1 | profile |

`COMFYMODAL_GOLDEN_DEEP_TRACE` was never passed (it is added only by `golden profile`).

### Validity: 10/10 on every structural requirement

| requirement | result |
|---|---|
| `output_sha_match == True` | **10 / 10** |
| `valid == True` | **10 / 10** |
| `restore_count == 1` | **10 / 10** |
| `request_count == 1` | **10 / 10** |
| `post_restore_nonce` present | **10 / 10** |
| distinct `restored_instance_id` (true-cold) | **10 / 10** |
| fallback reported | **0 / 10** |
| true CLIP-forward / UNET-load overlap | **10 / 10** |
| snapshot-capture guard | `idle`, `post_capture_guard_pending=false` on all 10 |

No request was discarded: no capture occurred, so no one-request guard was armed.
Runs were strictly serial. All 10 bind one deployment fingerprint, so this is a
homogeneous single-deployment cohort.

### Stage walls (ms), n=10

| stage | min | p50 | p90 | max | mean | sd | CV% |
|---|---|---|---|---|---|---|---|
| `golden_restore` | 0.2 | 0.2 | 0.4 | 0.7 | 0.3 | 0.2 | 53.2 |
| `golden_request_setup` | 1.5 | 2.0 | 3.4 | 50.0 | 7.1 | 15.1 | 214.0 |
| `golden_clip_load` | 1756.8 | 3192.4 | 4192.3 | 4904.1 | 3160.0 | 1111.2 | 35.2 |
| `golden_clip_forward` | 2449.6 | 2970.8 | 4888.0 | 4999.4 | 3444.9 | 1011.3 | 29.4 |
| `golden_unet_load` | 2455.5 | 4289.0 | 6029.3 | 7126.4 | 4588.8 | 1383.0 | 30.1 |
| **`golden_sampler_prepare`** | **25.6** | **30.8** | **32.4** | **43.9** | **31.1** | **5.0** | **16.0** |
| `golden_sampling` | 3670.3 | 3925.1 | 4161.5 | 4653.0 | 3992.0 | 269.4 | 6.7 |
| `golden_vae_load` | 361.0 | 517.2 | 895.7 | 1020.4 | 601.8 | 230.9 | 38.4 |
| `golden_sampler_tail` | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 14.9 |
| `golden_vae_decode` | 478.7 | 558.7 | 620.9 | 831.5 | 580.1 | 97.9 | 16.9 |
| `golden_output` | 212.5 | 242.6 | 249.9 | 267.9 | 238.2 | 17.5 | 7.3 |
| `golden_teardown` | 0.4 | 1.0 | 1.5 | 1.5 | 1.0 | 0.3 | 32.4 |
| `external_restore_total` | 643.2 | 909.8 | 1207.2 | 1460.4 | 949.4 | 242.0 | 25.5 |
| `overlap_wall_hidden` | 2450.3 | 2971.6 | 4889.1 | 5000.1 | 3438.1 | 1019.2 | 29.6 |
| `serial_equivalent_sum` | 4992.9 | 7015.7 | 10969.9 | 11031.4 | 8036.7 | 2234.8 | 27.8 |
| **TOTAL wall (overlap-aware)** | **7575.8** | **9799.2** | **11928.1** | **12614.4** | **10047.7** | **1645.4** | **16.4** |

With n=10 a p90 is meaningful, unlike the single-request profiler runs.

### What this cohort does and does not prove

**Proves.** All three approved optimizations hold on the real, unprofiled, Production-008
path: 10/10 exact output SHA, 10/10 true-cold single restore, zero fallbacks, and
`golden_sampler_prepare` now sits at **p50 30.8 ms / max 43.9 ms** with CV 16% - it no
longer has a heavy tail. The CLIP/UNET overlap is intact on every run, hiding a mean of
3438 ms of wall. Total overlap-aware wall is 10047.7 ms mean with CV 16.4%, far tighter
than the 14449-19378 ms spread seen across the profiled runs earlier in this pass.

**Does not prove.** There is **no like-for-like 10-run unprofiled baseline cohort** for
`production-008` in this repository, so this is **not** a before/after delta:

- the only baseline number available is trace `c5fe7cf3`, a **single profiled** run with
  VizTracer ON, which is a different execution condition and a different sample size;
- the profiled runs in this pass ranged 14449-19378 ms root wall against this cohort's
  7576-12614 ms, and that gap is at least partly profiler overhead.

So `sampler_prepare` moving from a 623.1 ms profiled baseline to a 30.8 ms unprofiled p50
is consistent with the ~575 ms of `inspect.stack` work the optimization removes, but it is
**not** a controlled delta and must not be quoted as one. Establishing one needs a 10-run
unprofiled cohort on `production-008` itself.

**Anomaly worth watching.** `golden_request_setup` has CV 214% (p50 2.0 ms, max 50.0 ms).
One run spent 50 ms in a stage that normally costs 2 ms. That is a single outlier, not a
regression - Phase 1/2/4 do not touch request setup - but it is the kind of thing a
20-run cohort would confirm or dismiss.

### Corrected count

`confirm --runs 10` writes `confirm_runs: 10` but its manifest carries only the last run
record. The full cohort is the 10 per-run cohorts under
`artifacts/phase_p1_parallel_golden_v1/cohort_2026-10-02_16-29-50_*` through
`cohort_2026-10-02_16-34-55_21e69a`, plus one gate cohort at
`cohort_2026-10-02_16-28-50_0ecd78`. Note that `attempt_*.json` also matches the
`attempt_0_events.json` sidecar, so a naive count reports 22 attempts; there are 10.
