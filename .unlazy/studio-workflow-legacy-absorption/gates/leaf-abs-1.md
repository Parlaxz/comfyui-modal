# Gates: Domain adapters

OWNS: studio_domain/store.py, studio_domain/services.py, studio_workflow_routes.py, studio_workflow_run.py, studio_run_adapter.py, studio_domain/legacy_adapters.py, tests/test_workflow_domain.py, tests/test_legacy_preset_adapter_unit.py

Scope: Build legacy-preset to workflow adapters and establish the single run contract; WorkflowDomainStore/API stays the sole durable authority; no old-data migration.

- [x] G1: Adapter and domain contracts pass, including the new adapter unit tests.
  CHECK: python -m pytest tests/test_studio_workflow_manifest.py tests/test_studio_workflow_run_plan_identity.py tests/test_portability_roundtrip.py tests/test_workflow_domain.py tests/test_legacy_preset_adapter_unit.py -q && echo ABS1_DOMAIN_PASS
  EXPECT: ABS1_DOMAIN_PASS
  CWD: .
  EVIDENCE: automatic-evidence=v1; definition-sha256=cb36484cf6a49275f3c7c3e00c3bf92a08a514661af836b253e324a40d86e964; exit=0; EXPECT=matched; output-sha256=9564049927246fb4289de12dfe5d8d1d6d2bb1e4d6a3abf5269233575961be1f; output-bytes=1071; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal; path=eccbf075e8d4/76 entries

- [x] G2: Manual review confirms one durable authority, adapter boundaries, and no migration behavior.
  EVIDENCE: Reviewed: WorkflowDomainStore remains the sole durable authority (no second store); legacy_adapters.py is pure translation (no I/O, store access, or migration); bridges delegate to verified create_preset/merge_workflow_controls; alleged deletions verified as in-file relocations (validation, duplicate guards, insert returns all still present); legacy dispatch path untouched; 90-test green current.
