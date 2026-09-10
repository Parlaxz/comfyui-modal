# Gates: Management UI migration

OWNS: web/studio-backend-api.js, web/studio-backend.js, web/studio-backend-presets.js, web/studio-preset-wizard.js, web/studio-workflows.js, tests/browser/studio-workflows.spec.mjs, tests/browser/fake/fake-server.mjs, tests/browser/studio-workflows-mock.mjs, tests/browser/studio-mock-api.mjs

Scope: Move Backend/preset management UI (CRUD, counts, cache keys, wizard mappings, Backend Presets page) onto workflow routes and the abs-1 adapter surface; no Backend/Preset concepts in user flow at end.

- [ ] G1: Workflow management browser contracts pass through the mocked flow.
  CHECK: npx playwright test tests/browser/studio-workflows.spec.mjs --project=mocked --retries=1 && echo ABS2_MGMT_PASS
  EXPECT: ABS2_MGMT_PASS
  CWD: .
  EVIDENCE: pending

- [ ] G2: Every edited web file parses without runtime syntax errors.
  CHECK: node --check web/studio-backend-api.js && node --check web/studio-backend.js && node --check web/studio-backend-presets.js && node --check web/studio-preset-wizard.js && node --check web/studio-workflows.js && echo ABS2_SYNTAX_PASS
  EXPECT: ABS2_SYNTAX_PASS
  CWD: .
  EVIDENCE: pending

- [ ] G3: Manual review confirms no Backend/Preset UI in user flow with workflow-scoped counts and cache.
  EVIDENCE: pending
