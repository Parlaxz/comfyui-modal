# U4 Final Remote-Readiness Repair

Scope: current `TESTING2` worktree at bundle authority `467eaa9`. Local-only
validation; no Modal contact.

## Repairs

- Production positioned source reads now pass a writable zero-copy byte view of
  CPU contiguous Torch `uint8` staging storage to `_read_at`/`os.preadv`.
  Dispatcher H2D submission still receives the original Torch tensor.
- Direct-read short retries advance both source and destination offsets; the
  exact `abcdefgh` regression proves two reads and exact final coverage.
- CLIP diagnostics retain broad conversion telemetry and add selected-Qwen
  parameter conversion counts, bytes, dtypes, per-forward values, storage
  alias classification, and fail-closed proof status. One observed forward is
  sufficient for this proof. Activation/output/device conversions remain
  outside the selected-parameter count.

The BF16 and FP32 remote result expectations were not claimed locally.

## Validation

Passed:

```text
U1 focused suite: 198 passed, 2 skipped
U2 focused suite: 118 passed
SW5 shield: 24 passed, 2 skipped
Affected transport/RA9C/RA9G/RA9H suite: 99 passed
Adjacent Golden contracts: 306 passed, 1 skipped, 1 unrelated S2 failure
py_compile + compileall: passed
git diff --check: passed
```

The isolated S2 failure is
`test_native_golden_deploy_publishes_before_backend`; it fails without U4
runtime changes because the mocked deploy manifest path is not materialized
before publication. No deployment or remote request was performed.

```text
U4_COMPLETE=YES

TORCH_DIRECT_READINTO_WORKS=YES
READ_VIEW_SHARES_STAGING_STORAGE=YES
DISPATCH_SOURCE_REMAINS_TORCH_TENSOR=YES
MODEL_BLOCK_PAGEABLE_COPY=NO

SHORT_READ_DESTINATION_ADVANCEMENT_CORRECT=YES
SHORT_READ_EXACT_CONTENT_PROVEN=YES

PARAMETER_CAST_SCOPE_PROVEN=YES
ALL_CASTS_SEPARATE_FROM_PARAMETER_CASTS=YES
SINGLE_FORWARD_PARAMETER_CAST_PROOF_SUPPORTED=YES

LEGACY_QD_SCHEDULING_CHANGED=NO
CAST_ONCE_OWNERSHIP_CHANGED=NO
DURABILITY_CHANGED=NO
SAMPLER_CHANGED=NO
MODAL_CONTACTED=NO

READY_FOR_SINGLE_SEQUENTIAL_REMOTE_CAMPAIGN=YES
```
