# Final Observability + Restore Completion - Acceptance Deployment Freeze Record

generated_at: 2026-08-13 03:05:00
purpose: ONE fresh deployment/snapshot + ONE validation/discard generation to validate the
  restore frozen-VRAM arm + waterfall/reconciliation/logging completion set

git_head: e5483d5a7a5414fc9baae84d16e02c13bf270520
git_branch: TESTING2
git_status_porcelain_count: 140

canonical_custom_node_generation: 4beea0bbdb2a3e74517b90a3989b9de5
baked_manifest_generation: 4beea0bbdb2a3e74517b90a3989b9de5
manifest_matches_tree: True

this_tree_changes_vs_previous_campaign:
  - RESTORE ARM: comfymodal_runtime/restore_memory_arm.py frozen_capacity_path() now resolves in-container
    (modal_app _runtime_env forwards COMFYMODAL_V2_STATE_VOLUME_ROOT=RUNTIME_STATE_PATH); new diagnostics
    [restore_memory_arm] freeze status=ok / [v2.restore_memory_arm] requested=optimized ... frozen_capacity_used=1;
    fixed dead once-per-process status-log gate (split guard).
  - WATERFALL: comfymodal_runtime/v2_waterfall.py accounting_role model (top_level/child/overlap_diagnostic/
    reconciliation); Residual no longer a numbered stage (footer metadata only); REMOTE/PARTIAL strips all
    stage % and # bars (TOTAL WALL unknown); pre-Python interval classified footer line; UNET checkpoint-read
    H2D-fallback marked overlap_diagnostic; negative child detail -> UNAVAILABLE ('-') not INVALID; node rows
    filtered (>=25ms or strategic class); concise top-level table + Expanded diagnostics section;
    attach_waterfall(print_render=...) kwarg.
  - UNET READ: comfyapp.py _complete_active_model_read now carries start_wall_unix_ns/start_monotonic_ns/
    end_wall_unix_ns/end_monotonic_ns so the real disk-read span is distinct from H2D.
  - OUTPUT: modal_app.py deferred-commit emits deferred_commit_start/end trace events (child, excluded from
    TOTAL WALL); benchmark_v2_direct prints prefer host-reconciled waterfall_local (WATERFALL (host-reconciled)).
  - OBSERVABILITY: modal_app cgroup resolver lenient match + process-CPU fallback (source=process_cpu_fallback);
    unavailable cgroup line once-per-process compact; COMFYMODAL_V2_QUIET console gating (forwarded via
    _runtime_env); COMFYMODAL_V2_COMPACT_BREAKDOWN for 63-field breakdown lines; host fallback attach_waterfall
    calls pass print_render=False.
  - TESTS: tests/test_v2_final_observability.py (29 scenarios); updated pins in test_v2_waterfall.py,
    test_waterfall_attach_central.py.

architecture_preset: identical to accepted campaigns (snapshot_restore_only, inherit profile, CLIP/VAE=1,
  UNET=0, retain clip_vae, native fast-disk, conditioning cache, sampling_end, single-use, minimal teardown,
  rtx-pro-6000, 12 CPU, 32768 MB, no cloud/region pins, ComfyUI pinned f49bdb6) +
  COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1 + COMFYMODAL_V2_QUIET=1 + OPTIMIZATION_DIAGNOSTICS=1

constraints:
  NO SOURCE EDITS from now through validation/discard completion
  NO commits (commit hash: none)
  exactly ONE deploy and ONE generation request
  no baseline samples, no A/B arms, no run-health classifier
