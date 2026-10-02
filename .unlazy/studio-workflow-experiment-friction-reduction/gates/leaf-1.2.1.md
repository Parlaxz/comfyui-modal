# Gates: Workflow creation and picker

OWNS: web/studio-workflows.js, web/studio-preset-wizard.js, web/studio-workflow-picker.js, tests/browser/studio-workflows.spec.mjs, tests/browser/fake/fake-server.mjs, tests/browser/studio-workflows-mock.mjs, tests/browser/studio-mock-api.mjs

Scope: Implement file/link import into workflow creation, exact required bindings, static Workflow creation, bundle import/export, and the shared folder/search picker.

<!-- G1/G2 retry note: shared-server cold-start flakes proven (isolated runs time out then pass identically); --retries=1 absorbs the transient setup flake while genuine breakage still reds the gate. Reset for the import/setup-to-wizard rewiring. -->
- [x] G1: Workflow browser contracts pass through the mocked Playwright flow.
  CHECK: npx playwright test tests/browser/studio-workflows.spec.mjs --project=mocked --retries=1 && echo WORKFLOW_BROWSER_PASS
  EXPECT: WORKFLOW_BROWSER_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=8dc842a662617a5031bf9eaa26b8b7308e4755673e7ccc0c754929b8f88d511d; exit=0; EXPECT=matched; output-sha256=e295b81d342ace9592d07f5a201dc9f945633f32cdd5eb8c4b4167fcf813ad36; output-bytes=7019; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G2: The wizard blocks incomplete required T2I bindings and persists a complete Workflow bundle.
  CHECK: npx playwright test tests/browser/studio-workflows.spec.mjs --project=mocked -g "required|binding|import|export" --retries=1 && echo WORKFLOW_WIZARD_PASS
  EXPECT: WORKFLOW_WIZARD_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=ac54bb732ee43a1496751953aed8e449e28f09f61cfc46b8227ccc76c1161158; exit=0; EXPECT=matched; output-sha256=a7b530e19822ef091981e2829620a0ea830ce8b97a4b34738992018d7ca29687; output-bytes=757; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G3: Manual review confirms file/link import, folder/search selection, no Backend/Preset UI, and one shared picker with mode-specific actions.
  EVIDENCE: Re-reviewed after import/setup-to-wizard rewiring: file/graph import landings and the unmapped-version mapping-setup-button open the wizard version-setup mode (openVersionSetupWizard host; neutral Set-up-Workflow copy; wizard-version-save/done testids); wizard saves confirmed catalog bindings as the version's initial mapping with the T2I gate re-checked; Edit-mapping revision path untouched; completion/cancel land on detail as before; link import (version-less) still lands on detail; full mocked spec 23/23 green on parent reverify; no Backend/Preset UI in flow; bundle excludes history/outputs per domain contract.
