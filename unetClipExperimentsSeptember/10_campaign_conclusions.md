# Source to H2D Decoupling Campaign Conclusions

STATUS=PARTIAL_DATASET_STOPPED_BY_USER

## Evidence basis

- Pure-source raw evidence: `06_source_only_runs`; 123 eligible observations, with 3 or 4 observations in each observed cell and all interrupted/invalid attempts retained.
- Pure-source derived report: `06_source_block_qd_matrix_pure_source.json`, `.csv`, `.md`.
- Historical integrated comparison: `05_qd2_qd4_qd8_additional10.json` and `.md`, 10 eligible observations per model/QD for static-E27 QD2/QD4/QD8.
- The historical integrated cohort is not decoupled evidence.

## Answers

1. The observed 256 MiB QD4/QD8 regression belongs to the historical integrated static-E27 path, not the pure source path. Its source wall medians rose from QD2 to QD4 to QD8: CLIP 1001.319 -> 1247.263 -> 1341.708 ms; UNET 1553.951 -> 1971.510 -> 2153.934 ms. The pure-source observations instead improved at 256 MiB as QD increased: CLIP 10960.21 -> 6431.57 -> 6069.72 -> 5470.15 ms for QD1/2/4/8; UNET 15952.76 -> 67839.80 -> 11365.10 -> 10936.48 ms. This isolates the inversion to the integrated transport pipeline with the available evidence, while the UNET QD2 pure-source outlier remains visible and prevents claiming a clean monotonic source law.
2. Provisional best pure-source geometry: CLIP 256 MiB/QD8; UNET 256 MiB/QD8. The second observed candidates are CLIP 256 MiB/QD4 and UNET 128 MiB/QD8. These rankings are provisional because the user stopped before ten observations per cell.
3. Optimal source-to-CUDA geometry: NOT MEASURED. No decoupled integrated matrix observations were collected, so H2D extent/depth winners cannot be claimed.
4. Full-Golden improvement: NOT MEASURED. No decoupled Golden A/B was launched.
5. Remaining dominant bottleneck: on the historical integrated path, the source/H2D pipeline and its wait/stream behavior dominate the QD inversion; the decoupled implementation is specifically intended to separate those controls, but its remote integrated effect remains unmeasured.

## Identity

- Worktree: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal`
- Branch: `TESTING2`
- Remote workspace: Testing 7 / `main`
- Source-only app: `sept-unetclip-04-source-ceiling-oracle`
- Source-only deployment image: `im-T0i7a8ZwRw0DKHLGiwPJIy`
- Models Volume: `comfyui-models`, read-only `/root/models`
- No implementation commit was created.

The campaign state records Phase 2 as partial and Phase 3/4 as not run. No synthetic fixture was used for the remote conclusions.
