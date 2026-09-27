# Gates: Studio Workflow Legacy Absorption

- [ ] G1: Every absorption leaf has been reverified from its exact ledger.
  CHECK: node C:\Users\parla\.config\opencode\skills\unlazy\scripts\gate-check.mjs --root . --cwd . --reverify --jobs 1 .unlazy/studio-workflow-legacy-absorption/gates/leaf-abs-1.md && node C:\Users\parla\.config\opencode\skills\unlazy\scripts\gate-check.mjs --root . --cwd . --timeout 600 --reverify --jobs 1 .unlazy/studio-workflow-legacy-absorption/gates/leaf-abs-2.md && node C:\Users\parla\.config\opencode\skills\unlazy\scripts\gate-check.mjs --root . --cwd . --timeout 600 --reverify --jobs 1 .unlazy/studio-workflow-legacy-absorption/gates/leaf-abs-3.md && echo ABSORPTION_LEAVES_REVERIFIED
  EXPECT: ABSORPTION_LEAVES_REVERIFIED
  CWD: .
  EVIDENCE: pending

- [ ] G2: The complete mocked import-to-run-to-matrix journey still passes after migration.
  CHECK: npx playwright test tests/browser/studio-workflows.spec.mjs tests/browser/studio-playground.spec.mjs tests/browser/studio-experiment.spec.mjs --project=mocked --retries=1 && echo ABSORPTION_E2E_PASS
  EXPECT: ABSORPTION_E2E_PASS
  CWD: .
  EVIDENCE: pending

- [ ] G3: Affected-area regression coverage passes after migration.
  CHECK: python -m pytest tests/test_studio_workflow_manifest.py tests/test_studio_workflow_run_plan_identity.py tests/test_portability_roundtrip.py tests/test_workflow_domain.py tests/test_legacy_preset_adapter_unit.py -q && echo ABSORPTION_REGRESSION_PASS
  EXPECT: ABSORPTION_REGRESSION_PASS
  CWD: .
  EVIDENCE: pending

- [ ] G4: Publication and deployment guards still pass with exclusions intact.
  CHECK: python -m pytest tests/test_runtime_deployment_spec.py tests/test_custom_node_publication_guard.py tests/test_custom_node_generation_parity.py -q && echo ABSORPTION_PUBLICATION_PASS
  EXPECT: ABSORPTION_PUBLICATION_PASS
  CWD: .
  EVIDENCE: pending

- [ ] G5: The absorption contract and artifacts are complete.
  EVIDENCE: pending
