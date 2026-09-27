# Step-3 Last-Two-Blockers - Acceptance Deployment Freeze Record

generated_at: 2026-08-12 18:36:51
purpose: ONE fresh deployment/snapshot + ONE validation/discard generation to prove Step-3 production acceptance (path-independent identity + pinned core)

git_head: e5483d5a7a5414fc9baae84d16e02c13bf270520
git_branch: TESTING2
git_status_porcelain_count: 113

canonical_custom_node_generation: e54f0670730bad2c6c8ed5bfab7e39c3
baked_manifest_generation: e54f0670730bad2c6c8ed5bfab7e39c3
manifest_matches_tree: True

this_tree_changes_vs_last_campaign:
  - registry_proof.py: path-independent logical module identity (shortest relpath vs roots, abspath-not-realpath), LF-normalized file content hash, fail-closed on unresolvable roots
  - canonical_execution.py: host proof roots [comfyui_root, repo_root] (custom_nodes_dir deliberately excluded for root-set symmetry)
  - modal_app.py: _registry_manifest_roots() shared by proof freeze + readback; readback returns comfyui_commit + core_module_sha256s (diagnostic)
  - tools/record_deployment_identity.py: host/deployed comfyui identity + comfyui_core_match diagnostics; persisted in .deployed_state.json
  - comfyapp.py: _COMFYUI_PINNED_COMMIT=f49bdb655707b97952dcef40e12e5af1f08d2007 (upstream v0.24.0 tag) + git fetch/checkout/log pin step after comfy-cli install
  - tests: tests/test_step3_path_identity.py (15), tests/test_step3_final_parity.py updates, test_plan_validation_proof.py fixture isolation

authoritative_core_source: local ComfyUI checkout f49bdb655707b97952dcef40e12e5af1f08d2007 (upstream v0.24.0 tag, verified detached + clean)
image_core_pin: same commit (image now rebuilt with pin)

architecture_preset: identical to prior campaigns (snapshot_restore_only, inherit, CLIP/VAE=1, UNET=0, retain clip_vae, fast-disk, sampling_end, single-use, rtx-pro-6000, 12 CPU, 32768 MB, no pins) + OPTIMIZATION_DIAGNOSTICS=1 + SNAPSHOT_CONSTRUCTION=1 (bat-forced)

constraints:
  NO SOURCE EDITS from now through validation/discard completion
  NO commits (commit hash: none)
  no cloud pin / no region pin / no warm pool
