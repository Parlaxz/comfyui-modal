# V2 Batch E23 Critical-Path Forensics

## 1. Executive result

Full prefetch is not a settled KEEP. It improves source-side work in the clean
same-region comparison, but it also makes CLIP forward materially slower. The
graph-relative readiness result is variable across the three ON observations;
the two newest runs are faster than OFF, while ON #1 is slower. Recommendation:
**KEEP_CONCEPT_BUT_REDESIGN**. The source benefit must be retained without
starting a competing full-read operation on the CLIP critical path.

The apparent sampler improvement is an instrumentation-boundary issue, not a
proven 1.1 s diffusion optimization. `sampler_ms` is ~3.64-3.68 s, while the
same artifacts' `sampling` interval is 4.709-4.734 s. The latter is the older
sampler-visible boundary and includes 1.069-1.057 s between sampler-node
entry and actual sampling start.

## 2. Four-run E22 table

| Run | provider / region | CLIP hydration | CLIP forward | CLIP ready from graph | prefetch wall / bytes / fraction | Worker B wall / effective GB/s | fastsafe wall | file-to-GPU | UNET ready from graph | post-CLIP tail | joint graph readiness | sampling | VAE | PNG | command response | no-scheduling |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| OFF | GCP / us-east1 | 1613.168 | 2775.666 | 4672.437 | UNKNOWN / UNKNOWN / UNKNOWN | 5019.503 / UNKNOWN | 7035.198 | 2084.806 | 6815.863 | 2143.427 | 6815.863 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| ON #1 | GCP / us-east4 | UNKNOWN | 4650.688 | 6917.516 | 4105.848 / 12309866400 / 1.0 | 5596.885 / UNKNOWN | UNKNOWN | UNKNOWN | 7524.382 | 606.866 | 7524.382 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 22727.233 |
| ON #2 | GCP / us-east1 | UNKNOWN | 3313.016 | 4874.333 | 2819.289 / 12309866400 / 1.0 | 3859.791 / 3.188 | 5426.321 | 1515.418 | 5421.529 | 547.196 | 5421.529 | 3639.628 | 349.526 | 161.779 | 18987.999 | 16865.854 |
| ON #3 | GCP / us-east4 | UNKNOWN | 3677.093 | 5432.620 | 3271.600 / 12309866400 / 1.0 | 4209.416 / 2.924 | 6159.479 | UNKNOWN | 6025.693 | 593.073 | 6025.693 | 3677.480 | 362.350 | 177.529 | 21090.980 | 19804.394 |

Worker effective GB/s uses 12.3098664 GB divided by Worker B wall. ON #1,
hydration, OFF post-CLIP data, and unavailable end-to-end fields remain
UNKNOWN rather than being inferred.

## 3. Exact readiness-origin grounding

The exact sources are:

- `graph_execution_start`: JSON `full_trace.events[]`, event name
  `graph_execution_start`, `process=remote`, `monotonic_ns`; emitted by
  `modal_app.py:11587` via `trace.emit("graph_execution_start")`.
- `clip_forward_start_at` / `clip_forward_end_at`: JSON orchestration record;
  emitted by `fast_cold_orchestration.py:552-571` through
  `on_clip_forward_start/end`, with corresponding events
  `fast_cold_clip_forward_start/end`.
- `clip_ready_at`: same orchestration record, assigned in
  `fast_cold_orchestration.py:569` in `on_clip_forward_end`.
- `unet_ready_at`: same orchestration record, assigned in
  `fast_cold_orchestration.py:1080` by `record_unet_ready`.
- The exact readiness event is `unet_ready`; the gate event is
  `model_readiness_gate`.

ON #2 (`run_001_sample.json` in `02-37-17`): graph start monotonic
`1482304767614` ns; CLIP forward `1483.866085246` to `1487.179100971` s;
`clip_ready_at=1487.179100971`; `unet_ready_at=1487.726296990`.
Therefore CLIP-ready-from-graph = **4874.333 ms**, UNET-ready-from-graph =
**5421.529 ms**, joint = **5421.529 ms**, and post-CLIP tail = **547.196 ms**.

ON #3 (`02-38-27`): graph start monotonic `1553847028860` ns; CLIP forward
`1555.602555649` to `1559.279648951` s; `clip_ready_at=1559.279648951`;
`unet_ready_at=1559.872722302`. Therefore CLIP-ready-from-graph =
**5432.620 ms**, UNET-ready-from-graph = **6025.693 ms**, joint =
**6025.693 ms**, and post-CLIP tail = **593.073 ms**.

`MODEL_READINESS_GATE_MS` is **not equivalent** in these artifacts. Source
`fast_cold_orchestration.py:790-799` subtracts `origin = self._request_origin or
self.started_at`, not the graph event. Thus ON #2 gate 5426.350 ms and ON #3
gate 6159.495 ms are orchestration-origin spans. The raw graph-relative values
above are authoritative for this report.

## 4. Prefetch source benefit

Same-region OFF versus ON #2, measured but not host-quality causal proof:

- `CLIP_COST_MS = +537.350` (ON slower).
- `WORKER_B_VALUE_MS = +1159.712` (OFF minus ON; ON faster).
- `FASTSAFE_PIPELINE_VALUE_MS = +1608.876`.
- `UNET_READINESS_VALUE_MS = +1394.334`.
- `NET_PREFETCH_VALUE_MS = +1394.334`.
- `POST_CLIP_TAIL_VALUE_MS = +1596.231`.

ON #1 versus OFF is unfavorable for Worker B and readiness, while ON #2 and
ON #3 show lower Worker B and fastsafe walls than OFF. This is **variable**
source effect, with positive clean same-region evidence but only three ON
samples and different regions.

## 5. Prefetch CLIP cost

All three ON observations have longer CLIP forward than OFF: +1875.022 ms,
+537.350 ms, and +901.427 ms. `clip_forward` is the outer measured forward
span; inner `clip_substage_*` fields are null. Classification:
**PREFETCH_CLIP_EFFECT = HARMFUL**.

## 6. Prefetch net critical-path value

Graph-relative joint readiness deltas versus OFF are ON #1 **-708.519 ms**,
ON #2 **+1394.334 ms**, and ON #3 **+790.170 ms**. Classification:
**PREFETCH_NET_READINESS_EFFECT = VARIABLE**. Source effect is also
**VARIABLE**. Engineering decision: **KEEP_CONCEPT_BUT_REDESIGN**.

## 7. Sampling boundary audit

The reported `SAMPLING_MS`/`sampler_ms` is the `sampling_start` to
`sampling_end` interval. `sampling_start` is emitted by the sampler
instrumentation; `sampling_end` is emitted at the diffusion-call boundary.
ON #2: 3639.628 ms; ON #3: 3677.480 ms.

The artifact also contains a separate top-level `sampling` stage, from
`sampler_node_to_sampling` end to the sampling-end-side boundary: ON #2
4709.422 ms and ON #3 4734.354 ms. The sampler-node-to-sampling intervals are
124.170 ms and 112.532 ms. There is also a measured `sampling_end` event
duration of 4709.447/4734.403 ms. No per-step timings are present.

## 8. Sampling decomposition

| Stage | ON #2 | ON #3 |
|---|---:|---:|
| Sampler-node entry to actual sampling start | 124.170 ms | 112.532 ms |
| Actual diffusion boundary (`sampler_ms`) | 3639.628 ms | 3677.480 ms |
| Sampler-visible historical-style interval | 4709.422 ms | 4734.354 ms |
| Difference | 1069.794 ms | 1056.874 ms |
| Steps | 8 | 8 |
| First/median/last step | UNKNOWN | UNKNOWN |

The available inner stages identify lane wait (0.195/0.134 ms) and actual
sampling start, but not model-execution per-step spans, preview, or a separate
final synchronization. Actual diffusion work is therefore **SUPPORTED
INFERENCE** at approximately 3639.628/3677.480 ms; pre-overhead is
**CONFIRMED** at 124.170/112.532 ms for the recorded sampler-node-to-start
boundary; post-overhead is **UNKNOWN**. Removable sampler overhead is at most
the known 112-124 ms pre-boundary, not the 1.06 s boundary difference.

## 9. Historical 4.8 s reconciliation

Current sampling boundary: `sampling_start -> sampling_end`, represented by
`sampler_ms` and the requested 3.64-3.68 s values. Historical boundary:
sampler-visible `sampling`/`sampling_end_duration_ms`, represented here by
4.709-4.734 s. `SAME_BOUNDARY = NO`.

The quantified boundary difference is 1069.794 ms (ON #2) and 1056.874 ms
(ON #3), principally the sampler-node-to-actual-sampling preparation interval.
The repository's older reports contain 4.7-5.3 s `sampling` stages, confirming
that the old number was not proven to be pure diffusion kernel execution.
No 1.1 s optimization claim is justified.

## 10. CLIP forward decomposition availability

`CLIP_FORWARD_CURRENTLY_DECOMPOSABLE = PARTIAL`. Existing telemetry provides
tokenize (ON #2 14.11 ms in the broad trace, ON #3 33.44 ms), hydration GPU
(1611.27/1345.94 ms), GPU prepare (2.74/2.40 ms), raw encode
(5303.36/4671.13 ms), and outer fast-cold forward (3679.42/3316.56 ms).
The requested transformer/layer/attention/MLP/output-projection breakdown is
not present; `clip_substage_forward_inner_ms`, hydration, post-forward, and
tokenize fields in the orchestration record are null.

## 11. Current cold critical-path waterfall

For ON #2, the defensible no-scheduling path is **16865.854 ms**; ON #3 is
**19804.394 ms**. A non-double-counted critical-path representation is:

`restore/startup` (platform snapshot restore 1459.799/3139.221 ms plus
application restore 259.388/312.594 ms) -> graph execution -> overlapped CLIP
and UNET work -> joint readiness 5421.529/6025.693 ms -> sampler-node
pre-overhead 124.170/112.532 ms -> actual sampling 3639.628/3677.480 ms ->
post-sampling/VAE transition 838.839/854.364 ms -> VAE decode
349.526/362.350 ms -> PNG/output persistence 247.265/263.620 ms -> local
handoff and residual.`

CLIP and UNET are parallel inside the joint-readiness stage; their durations
must not be summed. The explicit artifact-level remaining critical-path
residual/handoff is not cleanly separable from graph setup and remote return;
use **UNKNOWN**, not an accumulated-work subtraction.

## 12. 13-second budget

Scenario A, conservative: restore 4000 ms + current clean CLIP floor 3313.016
ms + current sampling 3639.628 ms + VAE/PNG/output approximately 511 ms gives
an unavoidable-ish subtotal of **11463.6 ms**, before exposed UNET tail and
handoff. The remaining 1536.4 ms must cover exposed model-loading tail,
transition, and output residual. A 13 s result requires nearly all of the
same-region 1394 ms readiness gain plus approximately 140 ms elsewhere.

Scenario B, best repeatedly demonstrated current values: the best measured
no-scheduling value is **16865.854 ms** (ON #2); best repeated sampling is the
two-run mean **3658.554 ms**, best VAE is **349.526 ms**, and best PNG is
**161.779 ms**. The direct gap to 13 s is **3865.854 ms**. The exact serial
intervals containing that gap are exposed restore/startup, graph/model
readiness, pre-sampler wait, post-sampling transition, and remote return
residual; no single accumulated Worker-B number may be counted as savings.

## 13. Ranked next optimizations

1. **Prefetch/source preparation redesign**: exposed model-readiness interval
   5421.529-6025.693 ms; plausible target near the lower ON #2 result;
   expected critical-path saving 0-1394 ms; confidence medium. Preserve source
   benefit while preventing CLIP contention.
2. **Restore/startup reduction**: current exposed platform/application restore
   is 1719.187 ms ON #2 and 3451.815 ms ON #3; target 4000 ms total conservative
   startup is already demonstrated; expected saving 0-~1700 ms versus ON #3;
   confidence medium, region/host variable.
3. **Sampler boundary/wrapper**: known pre-boundary 112-124 ms; plausible target
   near zero; expected saving <=124 ms; confidence high for the boundary, low for
   pure diffusion optimization. Do not treat the 1.06 s boundary mismatch as a
   confirmed removable cost.
4. **VAE/output**: current VAE 349-362 ms, PNG 162-178 ms; plausible target
   300/150 ms; expected saving approximately 60-90 ms; confidence low-medium.

## 14. Post-CLIP tail causal attribution

The OFF report's 2143.427 ms tail and 2084.8063 ms file-to-GPU wall match
numerically at 97.261%. However, the OFF artifact does not contain raw
file-to-GPU start/end timestamps or a raw `unet_ready_at`/file interval pair;
only the graph-relative readiness timestamps and aggregate file-to-GPU field
are available. Therefore `POST_CLIP_TAIL_FILE_TO_GPU_OVERLAP_MS = UNKNOWN`,
`POST_CLIP_TAIL_EXPLAINED_BY_FILE_TO_GPU_PERCENT = UNKNOWN`, and the deferred
UNET transfer is **SUPPORTED INFERENCE, NOT CONFIRMED** as the temporally
aligned primary cause. The numerical match alone is insufficient.

## Final fields

```text
E23_CRITICAL_PATH_FORENSICS_COMPLETE
REMOTE_DEPLOYS = 0
PAID_REQUESTS = 0
COMMIT = none
ON2_GRAPH_EXECUTION_START_SOURCE = full_trace.events[] graph_execution_start, remote monotonic_ns 1482304767614, modal_app.py:11587
ON2_CLIP_READY_SOURCE = orchestration record clip_ready_at=1487.179100971, fast_cold_orchestration.py:569
ON2_UNET_READY_SOURCE = orchestration record unet_ready_at=1487.726296990, unet_ready event, fast_cold_orchestration.py:1080
ON2_MODEL_READINESS_FROM_GRAPH_START_MS = 5421.529
ON2_POST_CLIP_UNET_TAIL_MS = 547.196
ON3_GRAPH_EXECUTION_START_SOURCE = full_trace.events[] graph_execution_start, remote monotonic_ns 1553847028860, modal_app.py:11587
ON3_CLIP_READY_SOURCE = orchestration record clip_ready_at=1559.279648951, fast_cold_orchestration.py:569
ON3_UNET_READY_SOURCE = orchestration record unet_ready_at=1559.872722302, unet_ready event, fast_cold_orchestration.py:1080
ON3_MODEL_READINESS_FROM_GRAPH_START_MS = 6025.693
ON3_POST_CLIP_UNET_TAIL_MS = 593.073
MODEL_READINESS_GATE_SEMANTICS = max(clip_ready_at, unet_ready_at) - request_origin_at/started_at; not graph-relative in these artifacts
SAME_REGION_OFF_ON2_CLIP_COST_MS = 537.350
SAME_REGION_OFF_ON2_WORKER_B_VALUE_MS = 1159.712
SAME_REGION_OFF_ON2_NET_PREFETCH_VALUE_MS = 1394.334
PREFETCH_SOURCE_EFFECT = VARIABLE
PREFETCH_CLIP_EFFECT = HARMFUL
PREFETCH_NET_READINESS_EFFECT = VARIABLE
PREFETCH_ENGINEERING_RECOMMENDATION = KEEP_CONCEPT BUT REDESIGN
CURRENT_SAMPLING_BOUNDARY = sampling_start -> sampling_end / sampler_ms
HISTORICAL_SAMPLING_BOUNDARY = sampler-visible sampling / sampling_end_duration_ms
SAME_SAMPLING_BOUNDARY = NO
ON2_SAMPLER_TOTAL_MS = 3639.628
ON3_SAMPLER_TOTAL_MS = 3677.480
ACTUAL_DIFFUSION_WORK_MS = 3639.628 / 3677.480, SUPPORTED INFERENCE
SAMPLER_PRE_OVERHEAD_MS = 124.170 / 112.532, CONFIRMED
SAMPLER_POST_OVERHEAD_MS = UNKNOWN
REMOVABLE_SAMPLER_OVERHEAD_MS = <=124.170, LOW-MEDIUM CONFIDENCE
CLIP_FORWARD_CURRENTLY_DECOMPOSABLE = PARTIAL
OFF_POST_CLIP_TAIL_MS = 2143.427
OFF_FILE_TO_GPU_MS = 2084.8063
POST_CLIP_TAIL_FILE_TO_GPU_OVERLAP_MS = UNKNOWN
POST_CLIP_TAIL_EXPLAINED_BY_FILE_TO_GPU_PERCENT = UNKNOWN
POST_CLIP_TAIL_PRIMARY_CAUSE = SUPPORTED INFERENCE ONLY; temporal overlap unavailable
CURRENT_BEST_RESTORE_MS = 1719.187 measured remote restore components; 4000.000 conservative total
CURRENT_BEST_QWEN_FORWARD_MS = 3313.016
CURRENT_BEST_SAMPLING_MS = 3639.628
CURRENT_BEST_VAE_DECODE_MS = 349.526
CURRENT_BEST_PNG_ENCODE_MS = 161.779
CURRENT_CRITICAL_PATH_EXPLAINED_MS = 16865.854 no-scheduling ON #2
CURRENT_UNEXPLAINED_RESIDUAL_MS = UNKNOWN
TARGET_13S_GAP_MS = 3865.854 versus best no-scheduling artifact
TOP_OPTIMIZATION_1 = prefetch/source preparation redesign
EXPECTED_SAVING_1_MS = 0-1394
TOP_OPTIMIZATION_2 = restore/startup reduction
EXPECTED_SAVING_2_MS = 0-1700
TOP_OPTIMIZATION_3 = sampler-node boundary overhead
EXPECTED_SAVING_3_MS = <=124
EXPECTED_13S_PATH = restore 4000 + joint readiness near 5422 + sampling 3639.628 + VAE/PNG/output ~511 = ~13572 before residual; requires further ~572 ms
NEXT_IMPLEMENTATION_BATCH = redesign prefetch critical-path interaction, then measure graph-relative readiness; no runtime change in E23
```
