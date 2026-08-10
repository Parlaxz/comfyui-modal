# RTX PRO 6000 — 12 CPU / 32 GiB — 6 True-Cold Runs

Date: 2026-08-10 (UTC). Baseline: `2909edb` + config commit `5b5b725`.
Deployed app: `stable-modal-comfy-v2-variance-shadow`, production profile, CPU=12, memory=32768 MiB, GPU=RTX-PRO-6000.

Method: `run_v2_single.bat` with `V2_BENCHMARK_MODE=variance_cold`, `V2_VARIANCE_RUN_COUNT=7`, 25 s gap, full teardown between requests.
Run_0 was the post-deploy snapshot-capture request (storage_unique_count=0, no CPU→GPU transfer evidence) and is not counted.
Runs 1–6 are the measured true-cold generations (cold_valid, restore_count=1, request_count=1, distinct restored instance each, 453 unique storage records — FULL snapshot path).

## Runs (ms)

| run | region | restore ms | UNET activation/load ms | sampler wait ms | sampling duration_ms | Python resume → durable result ms | scheduling ms | total wall ms | status |
|-----|--------|-----------|------------------------|-----------------|---------------------|-----------------------------------|---------------|---------------|--------|
| 1 | us-south1 (GCP) | 3470 | 1349 | 1202 | 3716 | 12649 | 28191 | 43829 | COLD ok |
| 2 | us-west1 (GCP) | 3564 | 6833 | 3347 | 3732 | 18750 | 47041 | 69634 | COLD ok |
| 3 | us-west1 (GCP) | 3916 | 1451 | 1010 | 3710 | 11317 | 50349 | 65077 | COLD ok |
| 4 | eu-west-2 (AWS) | 3064 | 17439 | 13597 | 3736 | 31719 | 53830 | 88064 | COLD ok |
| 5 | eu-west-2 (AWS) | 1308 | 2279 | 1895 | 3750 | 15082 | 33878 | 49772 | COLD ok |
| 6 | ap-northeast-1 (AWS) | 2503 | 2455 | 2203 | 3741 | 48884 | 91126 | 141989 | COLD ok |

Metric mapping (variance-cold normalized keys): restore = `metrics.restore.restore_total_ms`; UNET activation/load = `metrics.page_traversal.activation_total_ms`; sampler wait = `metrics.sampler.sampler_lane_wait_ms`; sampling = `metrics.sampler.sampling_ms`; Python resume→durable result = `remote_python_resume_to_restore_start_ms (0.0) + restore_to_method_entry_ms + first_remote_event_to_final_result_ms` (method_entry_to_first_remote_event_ms and output_commit_ms unavailable on all runs; output written via direct-output-sink registry); scheduling = `metrics.transfer.pre_python_modal_scheduling_ms`; total wall = `metrics.transfer.wall_ms`.

## Summary

RTX PRO 6000 — 12 CPU / 32 GiB

valid runs: 6

| metric | p50 ms | min / max ms |
|--------|--------|--------------|
| Python→result | 16916 | 11317 / 48884 |
| UNET load (CPU→GPU transfer) | 2324 | 1321 / 17362 |
| sampler wait | 2049 | 1010 / 13597 |
| sampling | 3734 | 3710 / 3750 |
| restore | 3267 | 1308 / 3916 |
| scheduling | 48695 | 28191 / 91126 |
| total wall | 67356 | 43829 / 141989 |

Notes:
- Client-observed command→response ranged 284.8 s (run 1) to 824.7 s (run 6); remote wall_ms above excludes local queue/download tails not attributable to the container.
- Cross-region spread dominates variance: run 4 (eu-west-2) CPU→GPU transfer 17.4 s @ 0.71 GB/s vs run 1 (us-south1) 1.3 s @ 9.32 GB/s; sampling is stable (3710–3750 ms).
- pretouch disabled (production default, pretouch_enabled=0, pretouch_valid=False by design). No variance failures, no identity failures on any measured run.

## Git records

- backup commit: `43c31aacaba40c88cde16f7f3c28209b8c5704cf`
- backup tag: `pre-2909edb-revert-20260809-200603`
- reverted baseline: `2909edb3f6baa2b5c405a7a18ceefaede58544fd`
- new config commit: `5b5b725`
- run artifacts: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-10_01-15-10\` (run_0..6.json, summary.json, variance_cold_report.md)
- run log: `v2_rtx6000_cold_runs.log` (repo root)
