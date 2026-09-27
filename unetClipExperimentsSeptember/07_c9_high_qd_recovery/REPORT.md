# C9 High-QD Source Recovery

## Result

Directional campaign: **48 eligible observations**, 8 per cell, collected by
one strictly serial remote call at a time. The operator stopped before the
requested 10-per-cell cohort. All 48 are retained in the ledger and raw
artifacts. Two earlier 60-call lookup-failure attempts and one stopped
wrong-workspace attempt are retained but excluded from this result.

| metric | QD2 | QD4 | QD8 |
|---|---:|---:|---:|
| CLIP median source wall (ms) | 7051.068 | 5993.812 | 5889.848 |
| CLIP median decimal GB/s | 1.140997 | 1.343227 | 1.367233 |
| UNET median source wall (ms) | 12925.769 | 12206.610 | 11546.226 |
| UNET median decimal GB/s | 0.952347 | 1.009382 | 1.066134 |

The complete per-request values and statistics (mean, sample SD, CV) are in
`summary.json`; every raw response is under `runs/`.

**Verdict: `C9_HIGH_QD_PARTIALLY_RECOVERED`**

QD8 beats QD4 and QD2 for both models, restoring the direction
`QD8 > QD4 > QD2`, but the gain saturates early and is far below historical
C9 throughput. Median QD2→QD8 improvement is +19.8% for CLIP and +11.9% for
UNET; QD4→QD8 is only +1.8% and +5.6% respectively.

## Actual concurrency

Configured QD8 did not sustain eight active readers. Median maximum active
readers were 7 for both models; median time-weighted achieved QD was 2.681
(CLIP) and 2.463 (UNET). QD4 reached max 4 but only about 1.27/1.25
time-weighted QD. Thus the result is not evidence of a fully exercised QD8
backend; active-reader timing shows substantial gaps/serialization.

## Historical C9 authority

Authoritative source: `comfymodal_runtime/unet_qd_probe.py:1419-1629`.
Authoritative report: `V2_BATCH_C9_MODAL_VOLUME_QUEUE_DEPTH_REPORT.md:10-29,
52-96, 125-155, 195-229`.

Historical full-file UNET payload was 12,309,817,472 bytes and used positioned
`os.preadv`, one FD per worker, statically disjoint contiguous ranges, and
32 MiB physical requests. Historical anchors were QD2 **16.23 GB/s**, QD4
**30.21 GB/s**, and QD8 **40.72 GB/s**. The historical deployment was GCP
`us-east4`, 32 vCPU, RTX PRO 6000, and its native C9 arm used per-worker pinned
buffers; its report also notes corrupted raw CPU counters.

The current oracle used the same read primitive/topology/range geometry and
32 MiB bound, but CPU=4, memory=8192 MiB, no GPU, no CUDA/H2D, no model
construction, no pinned buffers, and the current source-only telemetry. The
current UNET payload is byte-size identical to the historical one. Current
observed provider/region varied by model: CLIP Azure/westus3 and UNET
AWS/us-east-1. The requested read-only mount was `/root/models` on
`comfyui-models`; `/proc/self/mountinfo` observed the underlying 9p mount as
rw, with no writes performed by the oracle.

## Provenance fix

Fix: `comfymodal_runtime/e27_source_mechanism.py:166-191`, with provenance
captured at syscall entry (`:237`) and retained at event close (`:272`). Same
marker calls are O(1); changed markers require `allow_change=True` and affect
future events only. Focused tests are in
`tests/test_e27_source_mechanism.py` and prove no traversal, marker history,
concurrency, byte proof, and caller compatibility.

Synthetic benchmark: `e27_provenance_tracker_microbenchmark.json`.
Legacy-to-fixed median wall ratios were approximately **11.3x (47 events),
37.2x (123), 58.0x (243), and 111.5x (370)**. The Windows process CPU clock
had 15.6 ms resolution and measured the fixed arm as zero for these short
cases; CPU ratios are therefore not claimed as precise, but the fixed CPU
cost is below that clock resolution while the old 370-event arm measured
171.875 ms median CPU.

## Implementation and evidence

- Dedicated Modal wrapper: `c9_recovery_modal.py`
- Serial runner: `tools/run_c9_recovery.py`
- Offline tests: `tests/test_c9_recovery.py` (4 tests) and E27 focused suite
  (33 tests)
- App/function: `sept-unetclip-c9-recovery-source-only` /
  `run_c9_recovery`
- Deployment receipt: `deploy.log`; image IDs
  `im-CXmqu77s2wROxKB78AS9KG`, `im-D52zqBkWn9Bg5hNCxcxCEI`
- Deployment manifest: `deployment_manifest.json`
- Ledger: `ledger.json`
- Raw artifacts: `runs/`
- Machine-readable summary: `summary.json`

## Answers

1. The fix removed the quadratic event-rewrite work: synthetic wall cost fell
   by 11x–112x over the requested event counts. Exact CPU savings are below
   the local timer resolution for the fixed arm.
2. Yes. Current QD8 beats QD4 and QD2 in both CLIP and UNET medians, but only
   modestly.
3. Current UNET medians are 0.95/1.01/1.07 GB/s versus historical
   16.23/30.21/40.72 GB/s for QD2/QD4/QD8. This is roughly 5.9%, 3.3%, and
   2.6% of the historical anchors. Known differences prevent calling this a
   pure Volume regression: CPU4 vs CPU32, provider/region, no pinned buffers,
   different telemetry, and low sustained achieved QD.
4. Because strong historical recovery was not established, no modern-transport
   regression ranking is asserted. The three most important differential
   isolates are CPU4 versus CPU32, pinned versus ordinary host buffers, and
   sustained reader overlap/FD scheduling.
5. Highest-value next differential: repeat this exact oracle at higher CPU
   allocation while holding block size, FD topology, provider/region, and
   telemetry constant, to separate CPU/scheduling starvation from backend
   capacity.
