# Gates: Workflow domain and persistence

OWNS: studio_domain/store.py, studio_domain/services.py, studio_workflow_routes.py, tests/test_studio_workflow_manifest.py, tests/test_studio_workflow_run_plan_identity.py

Scope: Make the Workflow domain/API the durable authority for static graphs, bindings, values, layouts, filters, autosave, and bundle round-trip.

- [x] G1: Workflow manifest and run-identity contracts pass.
  CHECK: python -m pytest tests/test_studio_workflow_manifest.py tests/test_studio_workflow_run_plan_identity.py -q && echo WORKFLOW_DOMAIN_PASS
  EXPECT: WORKFLOW_DOMAIN_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=d9edee8b19cea794fa76a6ee633c5262a634d79ad1ad1f68152e1cf35d17fce9; exit=0; EXPECT=matched; output-sha256=dae92b1da341e51785978461f56c0591494933bc2e31313a4af45143f6e61976; output-bytes=1013; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G2: Durable bundle round-trip preserves the approved Workflow contract without outputs/history/experiment drafts.
  CHECK: python -m pytest tests/test_portability_roundtrip.py -q && echo WORKFLOW_BUNDLE_PASS
  EXPECT: WORKFLOW_BUNDLE_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=b8aad8dbe20a610e2293d459379d321ae319a8badc9393e17c522a4316e7a575; exit=0; EXPECT=matched; output-sha256=b422d24f37354c18550e76a48a6e4bec3ba275293661f4d689bd9fc09eda41b2; output-bytes=476; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G3: Manual review confirms one durable authority, autosave boundaries, and no legacy migration behavior.
  EVIDENCE: Reviewed studio_domain/store.py WorkflowDomainStore four JSON collections with atomic locked autosave, comment explicitly without second store or migration layer; studio_domain/services.py autosave_workflow boundaries plus exclusion list experiment_values/experiment_draft/run_history/generated_images, no migration code; routes preserve durable config only.
