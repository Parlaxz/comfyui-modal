# C8 Runtime-Shape Benchmark Handoff

## Executive result

Use **TBASE/O0** as the current winner when the deciding metric is application wall time excluding platform variance.

The trimmed comparison below removes the first valid run from each seven-run experiment and averages runs 2–7.

| Rank | Experiment | Total wall ms | Platform scheduling ms | App wall excl. platform ms | Command-to-response ms |
|---:|---|---:|---:|---:|---:|
| 1 | **TBASE/O0** | **15,365.6** | 4,569.6 | **9,147.0** | 15,771.0 |
| 2 | Memory-40960 | 20,807.3 | 9,562.6 | 9,493.2 | 21,205.2 |
| 3 | T1/O0 | 21,813.1 | 7,778.0 | 10,709.9 | 22,213.7 |
| 4 | TBASE/O3 | 17,204.8 | 4,335.7 | 10,733.1 | 17,602.0 |
| 5 | CPU-8 | 19,693.0 | 6,114.9 | 10,945.8 | 20,118.6 |
| 6 | TBASE/O2 | 23,436.9 | 8,725.4 | 12,038.9 | 23,829.2 |
| 7 | T3/O0 | 26,037.5 | 11,549.1 | 12,147.8 | 26,432.5 |
| 8 | TBASE/O1 | 20,072.2 | 5,054.5 | 12,844.3 | 20,496.4 |
| 9 | T2/O0 | 31,039.2 | 13,063.6 | 15,628.9 | 31,426.8 |

`App wall excl. platform` is the recorded `t3b_to_t8_ms`. `Platform scheduling` is the waterfall `modal_scheduling` stage.

## Selected production shape (cost-balanced)

TBASE/O0 is the current winner (CPU 16, memory 49152 MiB). For production the selected
cost-balanced shape is **TBASE/O0 / CPU 16 / memory 40960 MiB**: it requests 8 GiB less memory
(49152 − 40960 = 8192 MiB = 8 GiB lower request) at a measured ~346 ms slower application wall
time excluding platform variance (app wall 9,493.2 ms for Memory-40960 vs 9,147.0 ms for the
49152 MiB baseline). **40960 MiB is the production default**; 49152 MiB remains available as an
explicit environment override and the benchmark-only baseline used to reproduce the documented
latency winner. It is not selected on total wall time — the platform-scheduling variance is excluded
when comparing the cost-balanced choice.

## Benchmark context

- Runtime-shape worktree: `C:\Users\parla\.config\superpowers\worktrees\comfyui-modal\runtime-snapshot-shape`
- Artifact root: `C:\Users\parla\.config\superpowers\worktrees\comfymodal-data\benchmarks\runs`
- Required wrappers:
  - `deploy_and_run_v2_single.bat`
  - `run_v2_single.bat`
- Custom-node source:
  `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes`
- Baseline: TBASE/O0, CPU 16, memory 49152 MiB.
- GPU: RTX PRO 6000.

## Validity protocol

Every selected experiment contains seven valid runs. The first valid run was removed for the trimmed comparison above, leaving six runs per experiment.

For every invocation:

```powershell
$env:V2_BENCHMARK_RUNS='1'
$env:V2_BENCHMARK_GAP_SECONDS='0'
& '.\run_v2_single.bat'
Start-Sleep -Seconds 25
```

Deployment used `deploy_and_run_v2_single.bat`, also followed by the manual 25-second sleep.

Excluded records:

- Snapshot records: `snapshot_callback_to_command_start_ms == null`.
- Immediate post-snapshot records.
- Any record with zero or missing restore time.
- Earlier bulk or single-run artifacts created without the required manual delay.

## Selected artifact sets

All paths below are relative to the artifact root and use the `v2_2026-08-05_` prefix.

| Experiment | Seven selected artifact suffixes |
|---|---|
| TBASE/O0 | `10-09-00`, `10-09-53`, `10-10-41`, `10-53-31`, `10-54-25`, `10-57-26`, `10-58-23` |
| T1/O0 | `10-20-06`, `10-21-12`, `10-22-16`, `11-04-18`, `11-05-31`, `11-09-10`, `11-10-11` |
| T2/O0 | `10-26-34`, `10-27-34`, `10-28-56`, `11-17-18`, `11-18-17`, `11-19-54`, `11-20-51` |
| T3/O0 | `10-39-22`, `10-40-22`, `10-41-20`, `10-42-44`, `10-43-39`, `10-45-05`, `10-46-35` |
| TBASE/O1 | `11-27-28`, `11-28-35`, `11-31-47`, `11-32-44`, `11-33-38`, `11-34-35`, `11-35-48` |
| TBASE/O2 | `11-41-04`, `11-42-21`, `11-43-17`, `11-44-16`, `11-45-14`, `11-46-38`, `11-47-32` |
| TBASE/O3 | `11-53-15`, `11-54-23`, `11-55-17`, `11-56-11`, `11-57-17`, `11-58-11`, `11-59-07` |
| CPU-8 | `12-05-23`, `12-06-33`, `12-07-34`, `12-08-29`, `12-09-28`, `12-10-25`, `12-11-22` |
| Memory-40960 | `12-19-55`, `12-21-04`, `12-22-01`, `12-23-13`, `12-24-09`, `12-25-32`, `12-27-01` |

`12-28-00` was an extra valid Memory-40960 observation and is intentionally not part of the required seven-run set.

## Interpretation

1. **TBASE/O0 wins** on both trimmed total wall time and application wall excluding platform variance.
2. O3 has lower platform scheduling than O0, but its application wall is materially slower; do not select it based on platform time alone.
3. T1, T2, and T3 are slower than TBASE under the trimmed application metric.
4. CPU-8 and Memory-40960 do not improve total wall time over the 16-CPU/49152-MiB baseline.
5. Platform scheduling variance is substantial. Preserve both platform and application metrics in future comparisons.

## Agent instructions

- Use only the selected artifact sets above for conclusions.
- Do not mix the old gap-zero artifacts into the result set.
- Treat a new snapshot recapture as a reset: discard the snapshot and its immediate post-snapshot run before counting valid runs.
- Keep the manual 25-second Windows sleep between every invocation.
- If rerunning, preserve the seven-valid-run standard and report platform scheduling separately from application wall.
