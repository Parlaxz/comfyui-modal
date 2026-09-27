# V2 Custom-Node Generation Parity Fix - Validation Deployment Freeze Record
generated_at: 2026-08-12 14:44:23
git_head: e5483d5a7a5414fc9baae84d16e02c13bf270520
purpose: ONE validation deployment + snapshot construction after root-cause repair. NO generation requests.
repair_files:
  - comfymodal_runtime/custom_node_parity.py (NEW: pure parity report/decision + stale-record rule)
  - comfymodal_runtime/modal_app.py (construction-gated reconciliation + [v2.custom_node_generation_parity] events)
  - tools/publish_custom_nodes_volume.py (NEW: deploy-time volume publication via V1 sync_custom_nodes_to_volume)
  - deploy_and_run_v2_single.bat (publish step before V2 deploy in both branches)
  - tests/test_custom_node_generation_parity.py (NEW: 20 tests, 16 mandated scenarios)
tree_generation: ec22f6de14b680fb439c55d93ac0d364 (matches baked manifest)
