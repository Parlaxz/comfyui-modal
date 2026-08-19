# V2 Batch E2: Generic CLIP Staged Hydration

## Scope

This batch adds an optional, generic staged-safetensors adapter for excluded
CLIP placeholders. The adapter is default-off and uses the Phase-E
`plan -> prepare -> commit -> result` contract when the staged core is
available. Binding remains delegated to the existing generic
`hydrate_clip_bind` contract; the existing fastsafetensors path is the exact
fallback and is invoked at most once.

The staged backend does not alter CLIP numerical policy, D15 coordination,
conditioning-cache semantics, snapshot exclusion policy, or native fallback
behavior. No `staged_safetensors.py` changes were made.

## Local Evidence

- Cold excluded placeholder: staged core phases run once and bind through the
  existing shared-storage proof.
- Cache hit: no staged phase is entered and no hydration occurs.
- Staged failure: existing fastsafetensors hydration is called once, with the
  staged failure reason preserved in telemetry.
- Owner lifetime: staged storage is retained on the CLIP patcher and released
  by the existing owner teardown surface.
- Telemetry fields: `clip_staged_prepare_ms`, `clip_staged_commit_ms`,
  `clip_staged_h2d_ms`, `clip_staged_bind_ms`, and
  `clip_staged_fallback_reason`.

## Result

READY_FOR_E_INTEGRATION

FILES_CHANGED=
comfymodal_runtime/clip_fast_hydration.py
comfymodal_runtime/clip_fast_hydration_wiring.py
tests/test_v2_e2_clip_staged_hydration.py
V2_BATCH_E2_CLIP_STAGED_HYDRATION.md

TESTS=python -m pytest -q tests/test_v2_e2_clip_staged_hydration.py tests/test_v2_clip_fast_hydration_production.py tests/test_v2_clip_hydration_states.py (61 passed, 1 skipped); python -m py_compile comfymodal_runtime/clip_fast_hydration.py comfymodal_runtime/clip_fast_hydration_wiring.py tests/test_v2_e2_clip_staged_hydration.py
MODAL_DEPLOYS=0
MODAL_REQUESTS=0
COMMIT=none
STOP.
