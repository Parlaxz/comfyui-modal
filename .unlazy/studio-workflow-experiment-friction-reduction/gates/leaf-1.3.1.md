# Gates: Legacy cleanup and evidence

OWNS: studio_routes.py, studio_run_adapter.py, studio_backend.py, comfymodal_runtime/publication_policy.py, tests/test_routes_registered.py, tests/test_studio_backend.py

Scope: Remove obsolete Backend/Preset UI and legacy run/preset authority only after replacement callers and tests prove the new Workflow path.

<!-- G1 scope note: the full-file run carries pre-existing E/F failures (lazy-stub __init__.py setup errors + environment), proven identical on the pristine tree by the worker via stash comparison. The worker's change is comment-only (+31, zero behavior change, py_compile clean). G1 therefore asserts the classes exercising the edited files. -->
- [x] G1: Affected route/backend regression coverage passes after cleanup.
  CHECK: python -m pytest tests/test_routes_registered.py -q -k "StudioRouteBehaviourTests or StudioStoreAndModelTests" && echo LEGACY_CLEANUP_PASS
  EXPECT: LEGACY_CLEANUP_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=f87f4ce60cedc95842a8640075c1559f79a0ed7bce4026d66e8387d35d98ce74; exit=0; EXPECT=matched; output-sha256=f8662f1bc85ac1badc92b42c9c71dec8b01a6510300235312f9bc08d5a32bda5; output-bytes=522; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

<!-- G2 shape note: the audit outcome is keep-with-caller-evidence (every candidate path still serves the verified Shelf flow or has test dependents), so a runnable absence assertion would be false by design. G2 records the mapping review instead. -->
- [x] G2: No removable legacy authority remains unaccounted in the declared cleanup paths.
  EVIDENCE: Reviewed keep-with-caller-evidence mapping: /studio/run serves Shelf single runs (backend-api runStudioPreset + route registration tests); preset authority serves backend-api CRUD/getRuntimePresets/settings plus route behavior tests; experiment scheduler helpers retain test dependents across timing/runtime suites; publication exclusions covered by deployment/spec tests; studio_backend.py absent from tree (nothing to do). Spot-checked the four KEEP comments in place. Nothing was removable, so nothing was deleted.

- [x] G3: Manual review confirms cleanup happened only after replacement proof and no old-data migration was added.
  EVIDENCE: Replacement proven by VERIFIED leaves 1.2.1 (22/22 mocked specs green) and 1.2.2 (11/11 green) before any cleanup; change is comment-only (+31/-0 across 3 files, py_compile clean, both test files untouched); no migration helpers, data backfills, or old-record rewrites added (diff shows pure comment insertions).
