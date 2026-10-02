# TESTING9 C0 Non-Source Decomposition

## Scope

This report is measurement-only. It does not choose an architecture, compare C0
with E37 as a recommendation, or modify `production-005`.

The current evidence is split into:

- Phase 1 H100/gVisor console evidence: `artifacts/testing9Phase1.txt`.
- Current C0/Fresh model-load evidence: 15 valid requests in
  `artifacts/phase_p1_parallel_golden_v1/` for app
  `testing9-c0-mmap-fresh`.
- Raw per-window flattening: `artifacts/testing9_c0_phase2/`.
- The historical mislabeled Whole/Epoch artifacts are retained but excluded
  from lifecycle conclusions because child evidence proves they executed Fresh.

The current experimental deployment used H100, CPU 12, QD4, 128 MiB logical
source operations, four source workers, 512 MiB C0 arena, persistent FDs,
native libc memcpy, and the existing C0 dispatcher/H2D path. Runtime evidence
reported `4.19.0-gvisor`. `production-005` was not modified or retagged.

## Phase 1

The supplied H100/gVisor log contains `300/300` balanced samples: 30 steady
8-copy samples for each arm and worker count. Throughput is decimal GB/s for
approximately 1 GiB per worker in the steady section.

| Arm | Workers | n | Median GB/s | Mean GB/s | p10/p50/p90/p95 GB/s | Min-Max GB/s | SD | CV |
|---|---:|---:|---:|---:|---|---|---:|---:|
| THREAD->PRIVATE | 1 | 30 | 12.11 | 11.32 | 8.76/12.11/14.28/14.69 | 6.54-14.40 | 2.58 | 22.8% |
| THREAD->PRIVATE | 4 | 30 | 9.14 | 9.22 | 8.29/9.14/10.71/10.71 | 7.75-10.83 | 0.89 | 9.6% |
| THREAD->SHARED | 1 | 30 | 11.57 | 11.35 | 9.32/11.57/14.08/14.00 | 6.50-15.09 | 2.41 | 21.2% |
| THREAD->SHARED | 4 | 30 | 8.85 | 8.78 | 7.28/8.85/10.65/10.65 | 7.30-11.16 | 1.36 | 15.5% |
| PROCESS->PRIVATE | 1 | 30 | 11.87 | 11.81 | 9.30/11.87/13.74/14.00 | 7.71-14.71 | 1.96 | 16.6% |
| PROCESS->PRIVATE | 4 | 30 | 8.68 | 8.67 | 6.39/8.68/10.66/10.66 | 5.50-10.94 | 1.62 | 18.7% |
| PROCESS->SHARED | 1 | 30 | 13.24 | 12.52 | 9.46/13.24/14.51/14.56 | 8.37-15.03 | 2.19 | 16.5% |
| PROCESS->SHARED | 4 | 30 | 8.95 | 8.80 | 7.87/8.95/10.28/10.31 | 5.72-11.01 | 1.15 | 13.1% |
| FRESH PROCESS/MAPPING->SHARED | 1 | 30 | 2.46 | 2.41 | 2.22/2.46/2.70/2.70 | 1.65-2.71 | 0.25 | 10.2% |
| FRESH PROCESS/MAPPING->SHARED | 4 | 30 | 0.82 | 0.82 | 0.74/0.82/0.85/0.85 | 0.74-0.95 | 0.04 | 5.5% |

The console artifact contains steady sample totals, not individual first/later
copy rows or fault counters. Those fields are therefore unavailable here. The
separate detailed thread-private JSON is preserved at
`artifacts/testing9_phase1_h100_thread_private.json`.

### Direct comparisons

- Persistent PROCESS->SHARED is not slower than THREAD->SHARED: it is 14.4%
  faster at one worker and 1.1% faster at four workers by median steady rate.
- PROCESS->SHARED is not slower than PROCESS->PRIVATE: it is 11.6% faster at
  one worker and 3.1% faster at four workers.
- THREAD->SHARED is within 4.4% of THREAD->PRIVATE at one worker and 3.2% at
  four workers.
- Fresh PROCESS/MAPPING->SHARED is 81% lower than persistent PROCESS->SHARED
  at one worker and 91% lower at four workers.
- Persistent arms show normal contention when moving from one to four workers;
  Fresh shows the clear scaling collapse.
- Persistent shared memcpy is approximately 9 GB/s at four workers and is
  above both the current 3.4-5.2 GB/s source range and the 6.5 GB/s target.

Phase 1 therefore rejects a material penalty from persistent cross-process
shared-arena access. The evidence supports a fresh process/mapping lifecycle
penalty, not a general process boundary or shared-arena memcpy penalty.

## Current C0 Boundaries

The current C0 path is implemented by `SharedArenaRing`,
`GoldenModelTransport._load_c0_sync`, `C0StageReader.readinto_lease`,
`GoldenQDTransport`, and the CUDA-sterile child source kernel.

For each model load the measured boundaries are:

- model-load entry: `load_setup_marks.load_enter`;
- first source start: minimum child `mmap_start_ns` in the raw window trace;
- last source completion: maximum child `copy_end_ns`;
- source span: child first-start to child last-copy completion;
- GPU-ready: `final_h2d_completion_observed_ns`;
- model return: `total_load_ms` from the model transport record.

The current headline `source_wall_ms` is the child source interval used by
`golden_model_transport.py`; it is not a raw filesystem-only timer. It includes
the child source-operation interval, while parent slot/control/H2D waits are
reported separately in the dispatcher/window evidence.

## Current Fresh C0 Decomposition

These are medians over 15 valid Fresh CLIP and 15 valid Fresh UNET loads. The
source span uses the raw trace minimum/maximum, not the ordinal-0 operation.
Per-run residuals are computed before taking medians; component medians do not
necessarily sum exactly to the median total.

| Model | Full load wall | Pre-source | Actual source span | Post-source residual | Source->GPU-ready tail |
|---|---:|---:|---:|---:|---:|
| CLIP | 4183.8 ms | 901.0 ms | 2382.9 ms | 16.6 ms | 5.1 ms |
| UNET | 3715.0 ms | 12.9 ms | 3624.3 ms | 27.1 ms | 8.9 ms |

The median per-run non-source wall, computed as `pre + post`, is approximately
915.7 ms for CLIP and 56.2 ms for UNET. This is the first-use asymmetry: CLIP
is the first model load and pays C0 establishment/setup; UNET reuses that state.

### Pre-source components

| Component | CLIP median | UNET median | Execution/overlap |
|---|---:|---:|---|
| C0 arena ensure critical span | 607.0 ms | 607.0 ms recorded snapshot, not re-executed | CLIP first-use only; UNET evidence repeats the arena snapshot, not its cost |
| `cudaHostRegister` call | 559.8 ms | 0 ms new call | One registration for the shared arena; reused by UNET |
| SHM backing creation | 6.8 ms typical | 0 ms new call | CLIP first-use; the cohort has occasional much larger outliers |
| child spawn/readiness | 569.8 ms | 0 ms new spawn | Overlaps registration; child is persistent afterward |
| transfer-resource creation | 19.3 ms | not present | C0 shared resources are reused after first setup |
| safetensors layout/header resolution | 3.2 ms | 0.7 ms | Per model |
| GPU owner acquire | 2.6 ms | 4.9 ms | Per model, storage-size dependent |
| backend/pool/dispatcher construction | about 0.2 ms combined | about 0.1 ms combined | Per model, not the CLIP overhead source |
| dispatcher execute to first mmap | 7.0 ms | 3.8 ms | Includes first lease/control handoff |

The CLIP arena `register_ms` value is current evidence from
`arena_ensure.registration_diagnostic`; it is not a historical M2 number.
The child source code reports no standalone M2 `cuInit`, `cuCtxCreate`, or raw
driver context construction in the current C0 path. Current C0 calls
`torch.cuda.current_device()` and creates/reuses the existing C0 transfer
resources; no separate M2 CUDA context is created.

### Post-source components

The available current evidence shows a small post-source tail:

- final H2D completion after the last source copy: CLIP 5.1 ms median, UNET
  8.9 ms median;
- H2D-ready to model-load return: CLIP 6.2 ms median, UNET 12.2 ms median;
- CLIP model proof/adoption events are present in the timing trace, including
  skeleton construction, bind/assign, owner handoff, storage adoption, and
  compute-ready proof. The representative CLIP event contains roughly 0.07 ms
  skeleton construction, 9.4 ms bind/assign, 16.8 ms storage adoption, and
  2.5 ms compute-ready proof. These are not the dominant CLIP non-source cost;
  the dominant cost is before the first source launch.

No current evidence shows reader shutdown, FD teardown, arena unregister, or
large JSON/Gantt serialization inside the model-load return path. Child readers
remain persistent; the model-load source path reports persistent FD reuse.

## Current FD/Reader Evidence

In the representative current Fresh CLIP load:

- 63 fills;
- 4 FD opens;
- 59 FD reuses;
- 0 FD closes during the load;
- four persistent reader processes;
- QD4 observed;
- source map/child memcpy/munmap/pipe phase records retained per window.

This confirms that current C0 is not paying a fresh `open()` per logical
window, and that the reader processes are already persistent.

## Historical Lifecycle Identity Audit

The old supposed Whole and Epoch cohorts are preserved as accidental controls,
not lifecycle data.

Raw child-level evidence shows:

- old Whole: lifecycle code `1` for every retained operation, per-window
  mapping IDs advancing per reader, nonzero munmap on every operation;
- old Epoch: lifecycle code `1` for every retained operation with the same
  Fresh pattern;
- corrected Whole smoke: lifecycle code `2`, two mapping IDs per worker across
  the two model loads, and zero per-operation munmap.

The raw audit is in `artifacts/testing9_c0_phase2/phase2_execution_identity_audit.json`.
The old Whole/Epoch performance values must not be used as lifecycle estimates.

## Measurement Limitations

- The supplied Phase 1 console log does not contain first-copy/later-copy rows
  or per-copy fault counters; those fields are explicitly unavailable here.
- The current C0 raw trace does not expose a separate filesystem-service timer.
  `mapped_access_plus_memcpy_ms` remains a combined access/fault/memcpy phase.
- `source_wall_ms` and parent source-fill totals have different boundaries and
  must not be added together.
- The current retained valid lifecycle data is Fresh plus one corrected Whole
  smoke. Epoch currently fails with `mmap_reader_eof` before producing a valid
  load, so no Epoch performance claim is made.

## Evidence Files

- `artifacts/testing9Phase1.txt`
- `artifacts/testing9_phase1/phase1_samples.json`
- `artifacts/testing9_phase1/phase1_samples.csv`
- `artifacts/testing9_phase1/phase1_summary.json`
- `artifacts/testing9_phase1_h100_thread_private.json`
- `artifacts/testing9_c0_phase2/phase2_runs.json`
- `artifacts/testing9_c0_phase2/phase2_operations.json`
- `artifacts/testing9_c0_phase2/phase2_operations.csv`
- `artifacts/testing9_c0_phase2/phase2_execution_identity_audit.json`
- `artifacts/phase_p1_parallel_golden_v1/`
