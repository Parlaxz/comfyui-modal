# RA9H — Golden CLIP FP32 Cast-Once Integration

## Current authoritative status

RA9H is locally implemented in `comfymodal_runtime/golden_serial.py` and
covered by `tests/test_ra9h_golden_clip_residency.py`. The implementation is
request-local and default-off. No deploy, Modal request, remote run, paid
experiment, or performance claim was made.

The current worktree is substantially dirty from concurrent lanes. This lane
preserved those changes and did not reset, stash, clean, revert, or overwrite
unfamiliar files. The primary RA9H source change is `golden_serial.py`; the
RA9H test is a new file.

## Implemented path

1. `GoldenRequest` freezes `clip_residency` once at request construction.
   Omitted/false-like/invalid canonical V2 environment values select the safe
   BF16 control; explicit request values are normalized and invalid values
   fail closed.
2. The only Golden selector is
   `COMFYMODAL_V2_CLIP_FP32_CAST_ONCE`, already registered by the project
   configuration authority. No Golden-only environment alias remains.
3. `golden_clip_load` reads each checkpoint through the existing Golden QD
   transport once, retains each owner, and calls the real upstream
   `load_text_encoder_state_dicts` constructor once with shallow copies of the
   transported views.
4. The opt-in arm calls the RA9G transfer exactly once, then requires the
   actual post-loader destination map, `assign=True` bind receipt, storage
   proof, generic Golden adoption proof, source-reference removal, source-free
   proof, and owner retirement before publishing `READY`.
5. Transfer failure is observable and falls back only to the already
   transported BF16 source; no reread or second H2D is allowed. Later
   load/adoption failure remains a failed request and is not reported ready.
6. CLIP forward runs the real serial `CLIPTextEncode` closure. Optional stage
   diagnostics instrument the existing forward boundary and report conversion
   counts/bytes without adding synchronization to the normal path.
7. Telemetry is flat/scalar-or-metadata-only and includes requested/effective
   residency, fallback reason, source identity, source/resident/compute dtype,
   device, destination bytes, adoption proof, source cleanup, and load/
   transform/bind/proof/forward timings. Unavailable measurements remain
   `None` or `NOT RUN`, never zero.

## Local evidence

Focused RA9H/RA9G/RA9C validation:

```text
rtk pytest tests/test_ra9h_golden_clip_residency.py \
  tests/test_ra9g_clip_fp32_ownership_transfer.py \
  tests/test_ra9c_golden_qd_integration.py -q
45 passed
```

Adjacent Golden contract/observability validation:

```text
rtk pytest tests/test_p1_golden_serial.py \
  tests/test_p2_golden_core_contract.py \
  tests/test_p2_golden_observability.py \
  tests/test_ra3_clip_truth_telemetry.py \
  tests/test_e31_clip_forward_fp32.py -q
239 passed, 1 skipped
```

Additional checks:

```text
python -m compileall -q comfymodal_runtime tests     PASS
git diff --check                                      PASS
```

The RA9H tests exercise CPU tensors, protocol fakes, the actual transfer
state machine, the actual bind-receipt API, and the Golden loader seam. They
do not prove CUDA allocator behavior, production ComfyUI loader behavior on a
real model, Modal image freshness, remote latency, or end-to-end output
equivalence.

## Out-of-scope validation result

A mixed adapter/startup suite was also run:

```text
rtk pytest tests/test_golden_p1_wiring.py \
  tests/test_p2_golden_snapshot_adapter.py \
  tests/test_modal_app_identity.py -q
195 passed, 13 failed
```

The failures are in concurrent `modal_app.py`/CacheDiT startup and output-
durability/custom-node-generation changes, including missing local CacheDiT
dependencies and an unrelated `_output_durability_policy` `NameError`.
They do not execute the RA9H-only source path and were not modified by this
lane.

## Final status

```text
RA9H_LOCAL_IMPLEMENTATION=YES
RA9H_LOCAL_TESTS=PASS
DEFAULT_CLIP_RESIDENCY=BF16
CAST_ONCE_SELECTOR=COMFYMODAL_V2_CLIP_FP32_CAST_ONCE
CAST_ONCE_TRANSFORM_EXACTLY_ONCE=LOCALLY_PROVEN
ACTUAL_ASSIGN_BIND_RECEIPT_REQUIRED=YES
STORAGE_AND_SOURCE_FREE_PROOF_REQUIRED=YES
SOURCE_REFERENCES_DROPPED_BEFORE_OWNER_RETIREMENT=LOCALLY_PROVEN
BF16_FALLBACK=OBSERVABLE_AND_NO_REREAD
TELEMETRY_METADATA_ONLY=YES
QD_DISPATCHER_SOURCE_CHANGED=NO
RA7B_DURABILITY_SOURCE_CHANGED_BY_RA9H=NO
MODAL_CONTACTED=NO
REMOTE_VALIDATION=REQUIRED
PERFORMANCE_WIN=UNPROVEN
REPORT=RA9H_GOLDEN_CLIP_FP32_CAST_ONCE_INTEGRATION_REPORT.md
```
