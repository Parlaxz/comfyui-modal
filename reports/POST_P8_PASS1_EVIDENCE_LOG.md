# Working evidence log - POST-P8 optimization pass 1

Branch: `opt/p8-profile-cleanup-1` (from `production-008` = commit `9448cdd1c461996e026c59452bd1ef2ddfffd63b`)
Worktree: `.slim/worktrees/golden-best-003`
App: `batch-p8opt1` (isolated; production app untouched)
Workspace: Testing 9 / `ws_ee7221847f7d`

## Baseline identity (reverified)

- `main` = `9448cdd1c461996e026c59452bd1ef2ddfffd63b` -- **has NOT moved**. Matches the stated expected SHA.
- `production-008` is an *annotated* tag; `git rev-parse production-008` returns the tag object
  `e4a61ef8...`. The dereferenced commit is `9448cdd1c461996e026c59452bd1ef2ddfffd63b`. main == that commit.
- The root checkout (branch `TESTING8`, 71 dirty files) was NOT touched; all work is in the clean worktree.

### Authoritative baseline profile

`c5fe7cf3e6b2476faaf6618f55191af5` (identified by `golden_sampler_prepare = 623.1 ms`, matching the brief).
Local path: `artifacts/golden_exhaustive_runs/c5fe7cf3.../c5fe7cf3.../session/derived/`

Baseline identity (from `raw/golden_telemetry.json`):
- `golden_mode = parallel`, `method = run_golden_parallel_stream`
- `attention_backend = comfy_kitchen`
- `workflow_sha256 = e44389ea2eda82ba5e2324acc08307b6879ed6d4ea4b030727ab044704c0d3b5`
- `golden_profile_contract = direct_golden_parallel`
- profile used for reprofile: **`golden_p1_parallel_c0_p8_h100`** (app `batch-c0-p8-h100`, H100!)
- correctness SHA for that profile: `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`

### Invalid attempt retained (do not use for comparison)

`8ee88577a16f435d8b27fa0c6a6e4a3b` -- ran `golden_p1` (SERIAL, expected SHA `790c3052...`, backend sage).
`golden_profile_contract = direct_golden_serial`. **Not comparable** to the parallel baseline.
It also hit the 8,000,000-entry VizTracer capacity and the local analyzer OOM'd (MemoryError) on it.
Retained as evidence; excluded from all before/after claims.

---

## Baseline numbers (from the `golden_exhaustive_calls.csv.gz` of c5fe7cf3, exact match on qualified name)

| target | calls | wall_sum ms | self_sum ms | max ms |
|---|---|---|---|---|
| `GeneralSwitch.INPUT_TYPES` | 5 | 574.9 | 0.1 | 187.5 |
| `INPUT_TYPES` (any) | 100 | 580.5 | 0.5 | 187.5 |
| `inspect.stack` | 109 | 590.7 | 0.2 | 187.5 |
| `inspect.getouterframes` | 5 | 574.8 | 0.4 | 187.5 |
| `inspect.getframeinfo` | 119 | 574.2 | 1.3 | 89.8 |
| `inspect.getmodule` | 599 | 544.1 | 469.9 | 84.9 |
| `inspect.findsource` | 119 | 408.6 | 1.2 | 89.7 |
| `inspect.getsourcefile` | 3418 | 332.7 | 23.6 | 19.4 |
| `_parse_layout` | 3 (exact) | 351.4 | 341.0 | 194.6 |
| `_clip_meta_state_dict_from_header` | 1 | 211.0 | 205.1 | 211.0 |
| `triton_key` | 1 | 613.8 | 603.6 | 613.8 |
| `get_cache_key` | 1 | 645.6 | 0.0 | 645.6 |
| `precompute_freqs_cis` (llama.py:445) | 1 | 2083.8 | 105.5 | 2083.8 |
| `_check_child` | 313 | 443.6 | 2.8 | 238.4 |
| `_FileLock.__enter__` | 943 | 429.2 | 429.2 | 238.3 |
| `_encode_tile` (PIL) | 1 | 199.7 | 195.6 | 199.7 |
| `golden_output` | 2 | 495.9 | 262.9 | 248.0 |
| `wait_ready` | 309 | 4410.5 | 2.8 | 305.8 |

Baseline stage walls: sampling 4510.0, clip_forward 3181.4, unet_load 2854.5, clip_load 1944.4,
vae_decode 864.9, **sampler_prepare 623.1**, vae_load 592.5, output 248.0, request_setup 1.7,
restore 0.4, sampler_tail 0.1. ROOT_WALL = 11405.5 ms.

Baseline profiler health: `GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE=NO`
(reason: `no_root_corrupting_incomplete_calls: incomplete_calls=16`), PROCESS_COVERAGE=UNKNOWN,
TRACED_PROCESSES=1, TRACE_TRUNCATED=NO, CLOCK_ALIGNMENT=PROVEN.
**The baseline is itself incomplete on the same 16 incomplete calls** -- this is a pre-existing
profiler characteristic, not something any phase introduced.

---

## PHASE 1 - GeneralSwitch.INPUT_TYPES Golden bypass

Commit: `d4b9c4fb2640ca294828c899186f9b77840e3504`
Evidence run: trace `2dd0b4e01b4b448bad603df2b36571b8`, request `golden-p1-0-f5262d663fb4`

### Purpose / resource / change
- Purpose: `GeneralSwitch.INPUT_TYPES()` builds a constant schema but calls `inspect.stack()` only to
  detect upstream ComfyUI `get_input_info()` and substitute an accept-anything container.
  Golden never takes that path.
- Resource: CPU + GIL, pure introspection, zero I/O.
- Change: capture the normal schema once pre-snapshot
  (`capture_golden_input_types_schemas()`), serve via one helper `golden_input_types()`;
  also hoisted the per-linked-input rebuild out of the two link-traversal loops.

### Correctness (all pass)
- `validation.output_sha_match = True` (exact `3a6a0306...`), `valid = True`
- `restore_count = 1`, `request_count = 1`, true-cold restored identity present
- `valid_count=1 invalid_count=0 dnf_count=0`
- capture guard `state=idle`, `post_capture_guard_pending=false` -> ELIGIBLE observation
- source-probe `RESULT=PASS source_identity=MATCH`, git_head `d4b9c4f`
- 16/16 new unit tests; full `fast_unit` 538 passed / 2 failed / 7 skipped
  (baseline on this branch without the new file: 522 passed / 2 failed / 7 skipped ->
  the 2 failures are the documented PRE-EXISTING `test_rx9p_h_identity_chain.py` ones.)

### Profile evidence (before -> after)
| metric | baseline c5fe7cf3 | after-P1 2dd0b4e0 | delta |
|---|---|---|---|
| `golden_sampler_prepare` | 623.1 ms | **53.254 ms** | **-569.8 ms (-91.5%)** |
| `GeneralSwitch.INPUT_TYPES` | 5 calls / 574.9 ms | **0 / absent** | eliminated |
| `inspect.getframeinfo` | 119 / 574.2 ms | **absent** | eliminated |
| `inspect.getouterframes` | 5 / 574.8 ms | **absent** | eliminated |
| `inspect.findsource` | 119 / 408.6 ms | **absent** | eliminated |
| `inspect.getsourcefile` | 3418 / 332.7 ms | **absent** | eliminated |
| `inspect.getmodule` self | 469.9 ms | **2.0 ms** | -467.9 ms |
| any `INPUT_TYPES` wall | 580.5 ms | **3.6 ms** | -576.9 ms |

`PHASE_1_APPROVED = YES`

### Honest caveat - placement variance
Same-deployment single request, but the after-run landed on much slower storage/placement:

| stage | baseline | after-P1 |
|---|---|---|
| golden_clip_load | 1944.4 | 5599.2 |
| golden_unet_load | 2854.5 | 6884.3 |
| golden_clip_forward | 3181.4 | 5880.3 |
| golden_sampling | 4510.0 | 4880.5 |
| golden_vae_load | 592.5 | 723.6 |
| golden_vae_decode | 864.9 | 957.8 |
| golden_output | 248.0 | 251.1 |
| ROOT_WALL | 11405.5 | 18666.5 |

Corroborating storage slowness in the same run: `wait_ready` max 305.8 -> 1655.2 ms,
`_parse_layout` max 194.6 -> 1225.9 ms, `_clip_meta_state_dict_from_header` 211.0 -> 1143.5 ms.
None of these are touched by Phase 1. **Phase 1's win is claimed only for the sampler_prepare
stage, which is serial CPU work with no storage dependency.** No total-request claim is made
from this pair.