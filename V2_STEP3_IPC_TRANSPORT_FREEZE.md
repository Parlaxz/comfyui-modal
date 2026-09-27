# Step-3 Persistent-IPC Transport Acceptance - Redeploy Freeze Record

generated_at: 2026-08-12 20:07:59
purpose: ONE fresh deployment/snapshot + ONE validation/discard generation to prove plan_validation_consumed=1

git_head: e5483d5a7a5414fc9baae84d16e02c13bf270520
git_branch: TESTING2
git_status_porcelain_count: 121

canonical_custom_node_generation: fbecafb8ae72728ebc36d581b8356e39
baked_manifest_generation: fbecafb8ae72728ebc36d581b8356e39
manifest_matches_tree: True

this_tree_changes_vs_last_campaign:
  - ROOT CAUSE FIX: comfymodal_runtime/registry_proof.py evaluate_workflow_registry_parity + _proof_stats now accept
    collections.abc.Mapping (frozen MappingProxyType) for plan_proof / snapshot_manifest / manifest_classes and
    tuple classes.  ExecutionPlan.__post_init__ freezes deployment_identity, so the nested registry_proof arrived
    at the container gate as a MappingProxyType and the strict isinstance(dict) gate rejected it
    (plan_registry_proof_unavailable -> consumed=0).  The transport (client -> owner -> Modal) was proven faithful
    end-to-end (3 independent local experiments + 12-scenario regression suite).
  - tests: tests/test_step3_frozen_registry_parity.py (9), tests/test_persistent_handle_transport.py (12)

environment_actions:
  - killed stale persistent local-handle owner (PID 22844, spawned 11:30) + cleared owner state file
    (fresh owner will spawn with current code)

architecture_preset: identical to prior campaigns (snapshot_restore_only, inherit, CLIP/VAE=1, UNET=0, retain clip_vae,
  fast-disk, sampling_end, single-use, rtx-pro-6000, 12 CPU, 32768 MB, no pins, core pinned to f49bdb6) +
  OPTIMIZATION_DIAGNOSTICS=1 + SNAPSHOT_CONSTRUCTION=1 (bat-forced)

constraints:
  NO SOURCE EDITS from now through validation/discard completion
  NO commits (commit hash: none)
  no cloud pin / no region pin / no warm pool
