# Step-3 Final Parity - Acceptance Deployment Freeze Record

generated_at: 2026-08-12 16:55:20
purpose: ONE fresh deployment/snapshot + ONE validation/discard generation to prove Step-3 production acceptance

git_head: e5483d5a7a5414fc9baae84d16e02c13bf270520
git_branch: TESTING2
git_status_porcelain_count: 108

canonical_custom_node_generation: 995727c9f0d1a496fb2de3af9d08c4b5
baked_manifest_generation: 995727c9f0d1a496fb2de3af9d08c4b5
manifest_matches_tree: True

this_tree_changes_vs_last_campaign:
  - Step-3 deployment identity: plan now carries persisted baked hash (container readback), host mirror diagnostic-only
  - Step-3 registry: workflow-relevant per-class registry proof (registry_proof.py), full fingerprint diagnostic-only
  - deploy_and_run_v2_single.bat: records baked identity post-deploy (record_deployment_identity.py)
  - tests: tests/test_step3_final_parity.py (+23), fixture updates

architecture_preset: identical to V2_AB_CAMPAIGN_FREEZE_RESUMED_D1.md (snapshot_restore_only, inherit, CLIP/VAE=1, UNET=0, retain clip_vae, fast-disk, sampling_end, single-use, rtx-pro-6000, 12 CPU, 32768 MB, no pins) + COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1 + COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1 (bat-forced)

constraints:
  NO SOURCE EDITS from now through validation/discard completion
  NO commits (commit hash: none)
  no cloud pin / no region pin / no warm pool
