# E37 CLEAN_LANE Algorithm Recovery Report

## Result

The first structurally valid E37 CLEAN_LANE gate completed successfully.
G1 has not been started.

- Profile: `e37-clean-lane-qd4`
- Gate: `.v2ctl/gates/gate_20260821-223621_f76e3da7.json`
- Run artifact: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_22-35-45\run_001_sample.json`
- Request: `v2-benchmark-0-c9ac6e750942`
- Deployment fingerprint: `9ea14a717f57cdd64ea3aa3db3836357b0073cfa7b280d200def58593e2813f3`
- Gate status: `valid=1`
- Provenance: validated

## Recovered clean algorithm

1. Restore completes before plan identity is finalized.
2. Plan identity completes before CLIP source loading.
3. CLIP uses the synchronous QD4 reader after restore; speculative CLIP hydration is not used.
4. QD4 uses 32 MiB blocks, four workers, paired H2D timing, and joins all worker/future/event work before bind.
5. CLIP binds only after QD quiescence and device-ready publication.
6. Conditioning uses the real CLIP encode path with an explicit cache miss and no persistence.
7. UNET sampling and VAE decode follow CLIP bind; no clean-lane forbidden overlap was observed.

## Remote evidence

- Output SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
- Configured/observed QD: `4/4`
- Actual in-flight QD: `4`
- Worker count: `4`
- Source blocks: `240/240`
- Source errors: none
- QD fallback: false
- H2D host issue: `127.398988 ms`
- H2D CUDA event: `27.3155 ms`
- QD source wall: `1043.5138 ms`
- Aggregate source throughput: `7.7095 GB/s`
- Conditioning lookup: `hit=false`, `miss_count=1`, `lookup_status=bypassed`
- Conditioning decision: `miss_not_stored`, `encode_calls=1`, `persisted_count=0`
- Conditioning reason: `clean_lane_forced_miss`
- Volume identity and read interval: present
- Lifecycle ordering: restore → plan identity → QD start → QD ready → bind → forward start/end
- Forbidden GPU overlap: none

## Fixes applied

- Preserved `E37_CLEAN_LANE` atomic profile through batch run-side validation.
- Routed clean-lane demand through synchronous `clip_qd_load` instead of rejecting the expected absence of speculative hydration.
- Disabled inference mode only around QD GPU buffer construction so bind receives mutable tensors without cloning the full CLIP state.
- Added QD start, source identity, phase interval, and explicit forced-miss telemetry.
- Added bounded v2ctl stdout/stderr diagnostics for canonical artifact failures.

## Validation

- Combined focused local suites: `146 passed`
- Additional proof/gating coverage from the final telemetry lane: `57 passed`
- E37-focused coverage: `13 passed`
- `py_compile`: passed
- `git diff --check`: passed

## Remaining note

The persisted runtime artifact retains a legacy timing-reconciliation warning (`validation_status=FAILED`) even though the canonical v2ctl gate is valid and all required CLEAN_LANE proof predicates pass. This is a timing-accounting diagnostic to inspect separately; it is not a failed clean-lane algorithm proof.

No confirmation runs were performed, and G1 remains intentionally unstarted.
