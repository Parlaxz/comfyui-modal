# RX9P-B Golden Identity, Evidence Preservation, and Sage Production Default

## Implementation

- Golden discovery is invocation-bound: `v2ctl_invocation_id` is passed into
  the backend, the backend requires one stdout-identified cohort under
  `artifacts/phase_p1_serial_golden_v1`, and validates its `manifest.json`,
  attempt artifact, request ID, and `summary.json`. External or adjacent
  cohorts cannot satisfy the request. Missing artifacts are named explicitly.
- Resolved attention backend is frozen before dispatch and carried through the
  command/environment, experiment identity, profile/run fingerprints, backend
  result, run record, gate/confirmation manifests, and evidence index. Mixed
  backend evidence is rejected. `golden_p1` remains on its accepted PyTorch
  control backend.
- `tools/v2_control/experiment_evidence.py` creates an ignored raw bundle and
  a Git-visible `EXPERIMENT_EVIDENCE_<ID>_<date>.md`. It inventories every
  cohort, including incomplete/failed cohorts, preserves control-plane and
  referenced evidence, embeds textual evidence with source paths, and records
  byte sizes/SHA256 values. Large repeated attempt event streams retain raw
  copies plus path/cohort/size/SHA256/omission metadata.
- Gate, confirmation, and run completion paths invoke evidence finalization.
  Finalizer failure produces `EXPERIMENT_EVIDENCE_STATUS=FAILED`, forces an
  inconclusive result, and invalidates the persisted control manifest rather
  than leaving a valid verdict behind.
- Generic production now sets `COMFYMODAL_SAGE_RUNTIME_MODE = "baked_cuda"`
  in `config/v2/profiles/production.toml`. The existing working runtime path
  remains `comfyapp._preferred_sage_backend()` selecting the public
  `sageattention.sageattn`; explicit PyTorch selection remains supported.
  `golden_p1.toml` explicitly overrides `COMFYMODAL_SAGE_RUNTIME_MODE = "auto"`
  so Golden does not inherit production's `baked_cuda` default.  Golden's
  attention backend remains the separate accepted PyTorch control selector.

## Synthetic validation

`EXPERIMENT_EVIDENCE_SYNTHETIC_FIXTURE.md` documents clean exact, mismatch,
failed, incomplete, mixed-backend, adjacent/concurrent, large-event,
missing-receipt, and multi-arm cohorts. `tests/test_evidence.py` generates
these cases locally without Modal or paid execution.

## Verification

- Focused offline control-plane/evidence/config suite: **170 passed**.
- Python compilation for changed control-plane modules: **passed**.
- `git diff --check`: **passed**.
- The Sage policy suite imports the heavyweight runtime and exceeded the local
  timeout; no remote operation was attempted. Profile/config coverage passed
  in the focused suite.
- Concurrent RX9P-A/C worktree changes were preserved and are not included in
  RX9P-B staging.

GOLDEN_ARTIFACT_OWNERSHIP_FIXED=YES
ATTENTION_BACKEND_FROZEN=YES
PRODUCTION_SAGE_DEFAULT=YES
GOLDEN_CONTROL_BACKEND_CHANGED=NO
AUTO_RAW_EVIDENCE_BUNDLE=YES
AUTO_COMPACT_COHORT_INDEX=YES
AUTO_GIT_VISIBLE_COMBINED_MD=YES
EVIDENCE_REQUIRED_FOR_VERDICT=YES
REMOTE_CALLS=0
PAID_RUNS=0
READY_FOR_RX9=YES
