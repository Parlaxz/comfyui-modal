# Gates: Runtime consumers and deletion

OWNS: web/studio-playground.js, web/studio-experiment-mode.js, web/studio-workflow-run.js, web/studio-settings.js, web/studio-shell.js, tests/browser/studio-playground.spec.mjs, tests/browser/studio-experiment.spec.mjs

Scope: Move Shelf/Experiment selectors and submissions to workflow APIs, delete dead Backend/Preset code only with caller proof, keep publication exclusions intact, preserve output placement.

- [ ] G1: Shelf and Experiment browser contracts pass through the mocked flow.
  CHECK: npx playwright test tests/browser/studio-playground.spec.mjs tests/browser/studio-experiment.spec.mjs --project=mocked --retries=1 && echo ABS3_RUNTIME_PASS
  EXPECT: ABS3_RUNTIME_PASS
  CWD: .
  EVIDENCE: pending

- [ ] G2: Every edited web file parses without runtime syntax errors.
  CHECK: node --check web/studio-playground.js && node --check web/studio-experiment-mode.js && node --check web/studio-workflow-run.js && node --check web/studio-settings.js && node --check web/studio-shell.js && echo ABS3_SYNTAX_PASS
  EXPECT: ABS3_SYNTAX_PASS
  CWD: .
  EVIDENCE: pending

- [ ] G3: Manual review confirms per-path deletion proof, intact publication exclusions, and preserved output placement.
  EVIDENCE: pending
