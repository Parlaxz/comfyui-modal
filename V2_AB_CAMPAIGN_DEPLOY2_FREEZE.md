# Step-3 Accepted Campaign - Deployment 2 Freeze Record (restore-memory experiment)

generated_at: 2026-08-12 21:09:40
purpose: Deployment 2 = accepted architecture + COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1 (restore_memory/optimized arm)

git_head: e5483d5a7a5414fc9baae84d16e02c13bf270520
git_branch: TESTING2
git_status_porcelain_count: 134

canonical_custom_node_generation: 2a72642e34e66186c43d44eb871ef310
baked_manifest_generation: 2a72642e34e66186c43d44eb871ef310
manifest_matches_tree: True

deployment_1_baseline: snapshot im-8KexmbMytHCmXTxTMl6pl9|423ce11e7d2646c9b270e02955b04604 (D1 cohort COMPLETE: baseline N=5, UNET stopped, VAE winner N=5, PNG N=2, cache N=2)

this_tree_change_vs_d1:
  - comfymodal_runtime/modal_app.py: _runtime_env passthrough for COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN
    (framework wiring gap found before D2: the env was never forwarded to the container; without it the
    restore B arm would silently run baseline. D1 cohorts unaffected.)

architecture_preset: identical to Deployment 1 (snapshot_restore_only, inherit, CLIP/VAE=1, UNET=0, retain clip_vae,
  fast-disk, sampling_end, single-use, rtx-pro-6000, 12 CPU, 32768 MB, no pins, core pinned to f49bdb6) +
  COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1 + OPTIMIZATION_DIAGNOSTICS=1 + SNAPSHOT_CONSTRUCTION=1 (bat-forced)

constraints:
  NO SOURCE EDITS from now through restore collection completion
  NO commits (commit hash: none)
  no cloud pin / no region pin / no warm pool
