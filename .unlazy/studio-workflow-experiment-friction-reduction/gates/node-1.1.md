# Gates: Foundations integration

Scope: integrate children 1.1.1 and 1.1.2 into one verified schema and persistence foundation.

- [x] N1: every named direct child is reverified from its exact ledger.
  CHECK: node C:\Users\parla\.config\opencode\skills\unlazy\scripts\gate-check.mjs --root . --cwd . --reverify --jobs 1 .unlazy/studio-workflow-experiment-friction-reduction/gates/leaf-1.1.1.md .unlazy/studio-workflow-experiment-friction-reduction/gates/leaf-1.1.2.md
  EXPECT: ALL MET
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=1340b48d45ddf572dd5c8d2c5bc33bf2ce2fb5d6ba482ca2419422555028c0b4; exit=0; EXPECT=matched; output-sha256=e207a7801855d94ac2707b0519535068000484be689df20e0461655851353891; output-bytes=4859; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] N2: bindable-input schema and durable Workflow persistence agree at their boundary.
  CHECK: python -m pytest tests/test_studio_workflow_manifest.py -q && echo FOUNDATION_BOUNDARY_PASS
  EXPECT: FOUNDATION_BOUNDARY_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=3ae3b41260909bdffd26940568957d19b1dacffef6198981bd9455a699db7bd7; exit=0; EXPECT=matched; output-sha256=b92bb4a9ee86a89e46e78c9a0f05e5399bc565ef7e2a7b53d67777b723b20d88; output-bytes=498; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] N3: foundation interfaces work together without a second configuration authority.
  CHECK: python -m pytest tests/test_studio_workflow_manifest.py tests/test_studio_workflow_run_plan_identity.py -q && echo FOUNDATION_INTEGRATION_PASS
  EXPECT: FOUNDATION_INTEGRATION_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=e7736a12436ac0682cc11ea6cd6828cdd5efde5355132cf7150f0d0b06a2dc1b; exit=0; EXPECT=matched; output-sha256=4ef8648837074c1a014c2c988faaf85303d25ecbc902edc55e94ab8445bfe339; output-bytes=1020; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] N4: affected foundation behavior has not regressed.
  CHECK: python -m pytest tests/test_portability_roundtrip.py -q && echo FOUNDATION_REGRESSION_PASS
  EXPECT: FOUNDATION_REGRESSION_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=6b7ed56b983d3944486fcb2dc05e0c80284b5547299f4135b797879864118aca; exit=0; EXPECT=matched; output-sha256=cef6a4384413c4e8229bcd34601a1af6de72675361f5a72fe3a552186352e35d; output-bytes=482; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] N5: every direct leaf child's ownership lease was released after parent verification.
  EVIDENCE: Released leaf-1.1.1 and leaf-1.1.2 leases via gate-check --leaf ... --release after parent --reverify ALL MET; status.log contains leaf-1.1.1 verified/lease released and leaf-1.1.2 verified/lease released.

- [x] N6: consequential manual foundation outcomes were reviewed.
  EVIDENCE: Reviewed leaf-1.1.1 G3 fixed catalog/no user customization and leaf-1.1.2 G3 single WorkflowDomainStore authority/autosave boundaries/no migration; foundation boundary checks N2-N4 pass.
