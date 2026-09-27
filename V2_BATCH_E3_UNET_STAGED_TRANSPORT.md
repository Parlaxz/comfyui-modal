# V2 Batch E3 - Generic UNET Staged Transport Adapter

Date: 2026-08-16

Scope: adapt the existing UNET fastsafetensors pipeline so eligible Worker B
loads can use a generic staged-safetensors plan/prepare/commit contract while
preserving Worker A meta construction and the existing direct fastsafe path.

## Implementation

- `comfymodal_runtime/unet_fastsafetensors.py`
  - Uses the staged helper's default-off `COMFYMODAL_V2_STAGED_SAFETENSORS`
    gate.
  - Keeps the existing ZImage-specific C9 eligibility and fixed manifest gates
    for the direct fastsafe path.
  - Adds a generic staged eligibility path with the same path, value-probe,
    dtype, configuration-safety, CUDA, and manifest validation requirements,
    without model-name assumptions.
  - Keeps Worker A unchanged: meta model construction and sampling repair
    remain concurrent with Worker B.
  - Exposes separate staged plan, prepare, and commit adapter calls.
  - Holds the existing D15 UNET GPU token before staged prepare and commit;
    the disk-to-pinned overlap flag is not enabled.
  - Reuses the unchanged `_fs_fastsafe_load` path exactly once when staged
    prepare or commit fails.
  - Retains assign-based state-dict binding, residual-meta sweep, final
    validation, and transport-owner lifetime through the patcher.
  - Emits `unet_staged_prepare_ms`, `unet_staged_commit_ms`,
    `unet_staged_h2d_ms`, `unet_staged_bind_ms`, and
    `unet_staged_fallback_reason`.

## Local Evidence

The staged helper is intentionally outside this change set. E3 tests inject a
contract-compatible fake helper and verify the adapter boundary without GPU or
Modal activity. The adapter also matches the helper's `plan`, `prepare`, and
`commit(..., device=...)` contract and its owner-backed `StageResult`.

```
READY_FOR_E_INTEGRATION
FILES_CHANGED = comfymodal_runtime/unet_fastsafetensors.py,
                tests/test_v2_e3_unet_staged_transport.py,
                V2_BATCH_E3_UNET_STAGED_TRANSPORT.md
TESTS = 6 E3 tests; 95 existing UNET/native/A-B/D15 focused tests; py_compile
D15_REGRESSION = PASS
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
```
