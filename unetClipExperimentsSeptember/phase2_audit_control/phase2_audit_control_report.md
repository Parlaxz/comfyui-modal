# Phase 2 Source/H2D Causal Control Report

## Status

`COMPLETE — CAUSAL CONTROL GATE PASS`

- Fresh v4 control cohort: **24/24 eligible requests**.
- v4 used identical contiguous pinned CPU `torch.uint8` staging in both arms
  and the shared `golden_serial._read_at` physical reader.
- Existing Phase 2 artifacts and the earlier failed control attempts were preserved unchanged.
- Phase 3 remains stopped.
- No production Golden app was used.

## Purpose

Determine whether the large absolute slowdown in the earlier pure-source
Phase 2 table came from removing H2D or from a non-comparable source harness.

The control compared the same bounded `PreplannedExtentTransport` producer
path with and without H2D participation:

- CLIP, 256 MiB, QD2 and QD8
- UNET, 256 MiB, QD2 and QD8
- `source_only_same_path` versus `decoupled_integrated_control`
- Three eligible fresh-container requests per arm and geometry
- Serial execution

## Fixed Runtime Identity

- App: `comfy-modal-phase2-audit-control`
- Workspace: Testing 7
- GPU: RTX PRO 6000
- CPU: 4
- Memory: 8192 MiB
- Models Volume: `comfyui-models`
- Mount: `/root/models`, read-only
- Source worker path: `PreplannedExtentTransport`
- Source block: 256 MiB
- Source capacity: 8, independent of source QD
- Timing boundary: source-path entry through all source workers joined

## Results

Values are `SOURCE_WALL_MS`; each row contains three eligible observations.

| Model | QD | Arm | Values (ms) | Median (ms) | Achieved QD mean | Achieved QD max |
|---|---:|---|---|---:|---|---|
| CLIP | 2 | source-only | 1081.276, 1194.065, 1180.079 | 1180.079 | 1.960, 1.982, 1.945 | 2, 2, 2 |
| CLIP | 2 | source→H2D | 1070.545, 1067.013, 1106.162 | 1070.545 | 1.782, 1.832, 1.808 | 2, 2, 2 |
| CLIP | 8 | source-only | 1279.433, 1501.035, 1450.448 | 1450.448 | 6.108, 6.076, 6.155 | 8, 8, 8 |
| CLIP | 8 | source→H2D | 1398.104, 1780.963, 1550.390 | 1550.390 | 4.369, 4.789, 5.294 | 8, 8, 8 |
| UNET | 2 | source-only | 1717.706, 1700.386, 1703.805 | 1703.805 | 1.993, 1.995, 1.971 | 2, 2, 2 |
| UNET | 2 | source→H2D | 1611.583, 1739.110, 1604.817 | 1611.583 | 1.831, 1.821, 1.830 | 2, 2, 2 |
| UNET | 8 | source-only | 2812.785, 2756.357, 2346.421 | 2756.357 | 5.985, 6.487, 6.196 | 8, 8, 8 |
| UNET | 8 | source→H2D | 2538.344, 2168.194, 2113.584 | 2168.194 | 5.548, 5.233, 5.524 | 8, 8, 8 |

## Mechanism and Byte Checks

All 24 fresh-cohort artifacts passed:

- `classification=ELIGIBLE`
- strict control proof
- CPU allocation identity: requested/observed CPU 4
- exact source payload reconciliation
- physical requested/returned byte retention
- source worker join
- staging parity: one contiguous pinned CPU `torch.uint8` arena, identical
  geometry and allocation identity in both arms

H2D participation was distinct:

- Source-only: zero H2D events and no H2D dispatcher.
- Integrated: CLIP produced 30 H2D events per request; UNET produced 46.

The raw artifacts retain every physical read's requested and returned lengths,
offsets, producer ID, retry number, and timestamps. They also retain worker
timing, QD transitions, wait dimensions, filesystem identity, provider/region,
and H2D telemetry.

## Retained Evidence

- Fresh v4 raw artifacts: `runs_v4/`
- Fresh v4 ledger: `ledger_v4.json`
- v4 control artifacts: all 24 requests classified `ELIGIBLE`
- Superseded v2/v3 control artifacts remain retained unchanged.
- Earlier failed/import-timeout attempts: `runs/` and `ledger.json`
- Frozen 320-observation Phase 2 table: `../06_source_block_qd_matrix_pure_source.*`

The earlier control attempt contained one packaging failure and subsequent
one-second join-timeout failures. Those records remain retained and are not
included in the 24-request cohort.

## Comparability Finding

The v4 control substantially narrows the discrepancy: same-path source-only and
source→H2D source walls are comparable, unlike the earlier pure-source table's
roughly 4–8x slowdown versus historical integrated measurements. The v4 median
arm ratios (source-only / source→H2D) are 1.10x for CLIP QD2, 0.94x for CLIP
QD8, 1.06x for UNET QD2, and 1.27x for UNET QD8.

The causal-control methodology therefore passes: the remaining arm delta is
measurable under matched staging and reader provenance. This does **not** by
itself support the hypothesis that H2D transport coupling caused the original
QD inversion. Both arms still show higher source walls at QD8 than QD2, and
achieved QD8 is below configured QD in the integrated arm. The corrected full
source-only matrix is required before selecting Phase 3 configurations.

The earlier 320-observation pure-source table must remain descriptive only and
must not select Phase 3 configurations. Its invalid harness attempts and
missing historical provenance are not silently repaired or relabeled.

## Next Gate

Run the corrected full source-only matrix at 32/64/128/256 MiB × QD1/2/4/8,
three fresh serial observations per cell for both CLIP and UNET. Use only
eligible, provenance-complete observations for configuration selection.

The requested old-vs-new diagnostic cells and Phase 3's 160-observation
integrated matrix remain unexecuted. Phase 4 Golden A/B remains blocked until
an integrated configuration is established.
