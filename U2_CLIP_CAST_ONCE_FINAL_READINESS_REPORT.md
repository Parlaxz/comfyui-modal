# U2 CLIP cast-once final readiness

Date: 2026-08-31  
Scope: current checkout, local/offline evidence only. No Modal deployment or
remote request was performed by this lane.

## Final keys

| Key | YES/NO | Evidence / boundary |
|---|---|---|
| `U2_COMPLETE` | NO | Remote A/B execution and paired remote evidence are still outstanding. |
| `BF16_RESIDENT_DTYPE_TRUTHFUL` | YES | Golden reports the dtype from the adopted selected-scope storage snapshot; RA9H loader coverage verifies BF16/FP32 resident values. |
| `BF16_COMPUTE_DTYPE_TRUTHFUL` | YES | `compute_dtype` is populated only from observed selected Qwen-forward input/output and cast-destination evidence; otherwise it remains unavailable. |
| `DEFAULT_CONTROL_PARITY_PROVEN` | NO | The default-off path is a no-op in focused tests and profile wiring, but a real paired end-to-end transport-counter run was not performed locally. |
| `CAST_ONCE_SINGLE_TRANSFORM` | YES | RA9G/RA9H ownership tests cover exact-once widening; Golden uses one already-transported source and one actual constructor/bind path. |
| `ASSIGN_STORAGE_PROOF_REQUIRED` | YES | Actual-bind receipt, pointer/storage proof, shape/dtype/device checks, and fail-closed tests are required before READY. |
| `SOURCE_OWNER_RETIREMENT_PROVEN` | YES | Lifecycle tests prove source stays live through proof, references are dropped, then the owner is retired; failed release remains retryable. |
| `NO_SECOND_MODEL_SIZED_COPY` | YES | Local ownership proof derives the FP32 representation count and duplicate bytes from transformed/adopted storage signatures; the focused alias test observes one representation and zero duplicate bytes. |
| `FORWARD_CAST_DIAGNOSTICS_READY` | YES | Diagnostics now expose real forward count, per-forward conversion counts/bytes, repeated conversion counts/bytes, and `UNPROVEN`/`NOT RUN` states without fabricated zeros. |
| `QD_TRANSPORT_CHANGED` | NO | No QD transport/read file was changed by this lane. |
| `MODAL_CONTACTED` | NO | No deployment, Modal call, or remote validation was performed. |
| `READY_FOR_REMOTE_CAST_ONCE_TEST` | YES | Local implementation and focused contract tests are ready for the orchestrator-owned remote A/B test; this is not remote proof. |

## Local validation

Command:

```text
pytest -q tests/test_ra9g_clip_fp32_ownership_transfer.py tests/test_ra9h_golden_clip_residency.py
```

Result: **40 passed**.

Also passed `py_compile` for the changed runtime modules and focused RA9G/RA9H
test modules. The focused suite includes real `torch.nn.Module.load_state_dict`
`assign=True` adoption, mixed-output and truncated-forward fail-closed checks,
phase-based failure classification, and pre/post owner-retirement source-free
proof checks.

Adjacent regression check:

```text
pytest -q tests/test_ra9g_clip_fp32_ownership_transfer.py tests/test_ra9h_golden_clip_residency.py tests/test_e31_clip_forward_fp32.py tests/test_e31_profiles.py
```

Result: **110 passed**.

## Remaining limitations

The local suite does not establish Modal/remote GPU behavior, paired QD read or
H2D counters, two real remote CLIP forwards, remote allocator checkpoints, or
remote numerical parity. The orchestrator must treat those as pending and must
not convert local readiness into a remote success claim.
