# Gates: Bindable inputs and blocks

OWNS: web/studio-bindable-inputs.js, web/studio-field-blocks.js, tests/studio_bindable_inputs_unit.mjs

Scope: Implement the code-owned bindable-input catalog and reusable Playground blocks with fixed names, one-to-one binding metadata, and integer/float rules.

- [x] G1: The bindable-input unit contract passes for the initial T2I catalog and block mappings.
  CHECK: node tests/studio_bindable_inputs_unit.mjs
  EXPECT: BINDABLE_INPUTS_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=405fd50d8ea156cc3ed2118e7d9d45ef0a885a3e6e0b9305cb59097de22fca2e; exit=0; EXPECT=matched; output-sha256=26287df4468989c14578f42263c4a656a2c2872a7fb85e14d075f868c3090a6e; output-bytes=21; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G2: Every exported block renders its declared input kind without runtime errors.
  CHECK: node tests/studio_bindable_inputs_unit.mjs --render
  EXPECT: BLOCK_RENDER_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=e207deeeae000c5c27a395239b5456660e0add4b9a0228fe6a713ce1e5772ebf; exit=0; EXPECT=matched; output-sha256=18a3277e97e4d542e3b3d5d1dcf72062b42cf6017ffc6e26a8e62db0ae765569; output-bytes=39; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G3: Manual review confirms no user-configurable field type system was introduced and the catalog matches the approved schema.
  EVIDENCE: Reviewed web/studio-bindable-inputs.js fixed catalog prompt/seed/step_count/cfg_scale/sampler/model_unet/vae/clip plus separate OUTPUT_BINDING, fixed canonical names, one-to-one exact widget binding, coded integer/float rules (Seed allows negative, nonNegative minimum 0), no user customization or rename path; web/studio-field-blocks.js exposes only fixed multiline/integer/float/dropdown/model-picker blocks.
