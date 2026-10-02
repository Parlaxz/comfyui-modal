# Gates: Shelf Playground and Experiment

OWNS: web/studio-playground.js, web/studio-experiment-mode.js, web/studio-playground-state.js, web/studio-styles.js, tests/browser/studio-playground.spec.mjs, tests/browser/studio-experiment.spec.mjs

Scope: Implement the Shelf Playground single-run flow, Workflow switching, autosaved field layout, right-side output, and Experiment comparison/axis/pill/matrix behavior.

- [x] G1: Focused Playground and Experiment Playwright contracts pass.
  CHECK: npx playwright test tests/browser/studio-playground.spec.mjs tests/browser/studio-experiment.spec.mjs --project=mocked --retries=1 && echo PLAYGROUND_BROWSER_PASS
  EXPECT: PLAYGROUND_BROWSER_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=5dc268f6861d5da0f7a2a1cb82df55e28675696dcc26d125ebf1df746703c773; exit=0; EXPECT=matched; output-sha256=dbbff15a848cbf33a653a2a60947523c8058e229715a4ceb7a1fa545a5ce1150; output-bytes=5553; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G2: Existing experiment payload/history behavior remains valid.
  CHECK: node tests/studio_experiment_v2_frontend_unit.mjs && echo EXPERIMENT_UNIT_PASS
  EXPECT: EXPERIMENT_UNIT_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=645b15393a45250d061e3f1948cdab3b8da1d4142d3a432411d6c66f45624338; exit=0; EXPECT=matched; output-sha256=20b3df2715b9da21edf2905d57acb9efa4fe4330cf9796a1f9b216632fad8662; output-bytes=1099; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G3: Manual review confirms Shelf layout, field drag/group/autosave, Workflow switching prompt, Experiment toggle, common/unique fields, value pills, and right-side output/history.
  EVIDENCE: Reviewed Prompt anchor/output-right layout, drag-to-Advanced with same-row grouping and autosaved workflow-type profile, switching reuse prompt with stale-output marking, Experiment toggle with workflow comparison/common axes/hidden unique sections, Enter-created pills with prompt hover and generic number ops, same-run history timings fallback (same-run id only, canvas untouched, omitOutputs-safe), existing matrix/History surfaces preserved with legacy paths intact for the cleanup lane; full mocked suite 11/11 green on parent reverify (G1/G2 current evidence).
