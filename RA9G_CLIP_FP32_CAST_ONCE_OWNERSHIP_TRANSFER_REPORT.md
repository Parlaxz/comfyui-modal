# RA9G — CLIP FP32 Cast-Once Ownership Transfer

## Scope and evidence boundary

RA9G implements and locally validates a request-local ownership-transfer
contract for optional CLIP BF16-to-FP32 cast-once hydration. No Golden deploy,
Modal request, remote A/B, QD transport change, or edit to the RA9C Golden
dispatcher was performed by this lane.

The current worktree contains unrelated concurrent changes, including a
pre-existing modification to `comfymodal_runtime/golden_serial.py`. RA9G did
not modify that file and does not claim ownership of its diff.

## Implemented contract

`comfymodal_runtime/clip_fp32_cast_once.py` now provides:

1. A stable source/manifest identity including checkpoint, manifest
   generation, selected tensor scope, model-patch identity, target device, and
   manifest facts.
2. An explicit state machine for transform, `assign=True` bind receipt,
   storage proof, source-reference removal, owner retirement, `READY`, and
   fail-closed cleanup.
3. Exact key, shape, dtype, device, storage, byte-count, and FP32 residency
   proofs. A plain arbitrary FP32 mapping is not accepted as provenance.
4. Metadata-only snapshots after transfer. Model-sized source and destination
   tensors are never placed in the snapshot metadata.
5. Retry-safe owner cleanup and explicit external-release receipts.

`clip_fast_hydration_wiring.py` integrates the transfer only in the optional
hydration path. The actual bind/adoption receipt is required before residency
proof and source-owner retirement. Unknown or failed predicates fall back to
ordinary BF16 behavior. `speculative_clip_hydration.py` keeps cancellation
cooperative and prevents a cancelled worker from publishing into a demand
lane.

## Validation

Command:

```text
pytest -q tests/test_ra9g_clip_fp32_ownership_transfer.py tests/test_e31_clip_forward_fp32.py tests/test_e28_critical_path.py tests/test_v2_clip_fast_hydration_production.py tests/test_e30_clip_qd_io.py
```

Result:

```text
168 passed, 0 failed, 1 skipped
```

Additional checks:

```text
python -m compileall -q comfymodal_runtime tests     PASS
git diff --check                                      PASS
```

The RA9G tests use CPU tensors and protocol fakes. CUDA allocator behavior,
production loader behavior, Golden equivalence, and remote latency remain
unproven by this local lane.

## Final status

```text
RA9G_COMPLETE=YES
CAST_ONCE_TRANSFORM_EXACTLY_ONCE=PROVEN
ACTUAL_ASSIGN_BIND_RECEIPT_REQUIRED=YES
STORAGE_RESIDENCY_PROOF_REQUIRED=YES
SOURCE_REFERENCES_DROPPED_BEFORE_OWNER_RETIREMENT=PROVEN
SNAPSHOT_MODE=METADATA_ONLY
MISSING_IDENTITY_FAILS_CLOSED=YES
ORDINARY_BF16_FALLBACK_ON_FAILURE=YES
SPECULATIVE_CANCEL_PUBLICATION_RACE_CLOSED=YES
GOLDEN_WIRING_CHANGED_BY_RA9G=NO
GOLDEN_SERIAL_MODIFIED_BY_RA9G=NO
MODAL_CONTACTED=NO
REMOTE_AB_REQUIRED=YES
REPORT=RA9G_CLIP_FP32_CAST_ONCE_OWNERSHIP_TRANSFER_REPORT.md
```
