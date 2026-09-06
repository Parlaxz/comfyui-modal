# Hot Scaling

Evidence policy: raw attempt artifacts are authoritative; no worker rates are summed.

- Valid observations: 16
- Median GB/s: 36.78997983552421
- Range GB/s: 11.880419093386829 .. 94.99813053843279

## Enclosing-wall curve

| backend | workers | median GB/s | speedup vs one worker |
|---|---:|---:|---:|
| processes | 1 | 14.169596 | 1.000000 |
| processes | 2 | 34.036797 | 2.402101 |
| processes | 4 | 38.450204 | 2.713571 |
| processes | 8 | 79.866652 | 5.636480 |
| threads | 1 | 13.697275 | 1.000000 |
| threads | 2 | 33.622383 | 2.454677 |
| threads | 4 | 50.562783 | 3.691448 |
| threads | 8 | 61.678639 | 4.502986 |

### hot_threads_scaling
- Classification: **POSSIBLE**
- Thread scaling is reported only from enclosing coordinated read walls.
- Valid: 8; failures: 0
- Unsupported/opaque: kernel page cache state, FUSE internal scheduling

### hot_process_scaling
- Classification: **POSSIBLE**
- Process scaling retains startup and full-process timing when returned by the remote reader.
- Valid: 8; failures: 0
- Unsupported/opaque: process creation outside the timed read, kernel page cache state

### hot_best_candidates
- Classification: **SUPPORTED**
- Best thread, best process, and the one-worker reference are selected only after an all-valid meaningful smoke curve.
- Valid: 16; failures: 0
- Unsupported/opaque: best-candidate selection is smoke-derived unless confirmation exists

### hot_speedups
- Classification: **POSSIBLE**
- Speedups use median aggregate bytes / coordinated wall relative to the one-worker reference.
- Valid: 16; failures: 0
- Unsupported/opaque: speedup is relative to retained observations, not worker-rate sums


## Raw artifacts

- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_processes_w8_r1_10004__writer__attempt0028_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_processes_w8_r2_10005__writer__attempt0029_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_processes_w8_r3_10006__writer__attempt0030_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_threads_w1_r1_10007__writer__attempt0031_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_threads_w1_r2_10008__writer__attempt0032_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_threads_w8_r1_10001__writer__attempt0025_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_threads_w8_r2_10002__writer__attempt0026_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_confirm_threads_w8_r3_10003__writer__attempt0027_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w1_0005__forensics_hot_reader__attempt0017_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w1_0005__writer__attempt0005_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w1_0005_cleanup__cleanup__attempt0018_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w2_0006__forensics_hot_reader__attempt0019_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w2_0006__writer__attempt0006_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w2_0006_cleanup__cleanup__attempt0020_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w4_0007__forensics_hot_reader__attempt0021_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w4_0007__writer__attempt0007_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w4_0007_cleanup__cleanup__attempt0022_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w8_0008__forensics_hot_reader__attempt0023_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w8_0008__writer__attempt0008_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_processes_w8_0008_cleanup__cleanup__attempt0024_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w1_0001__forensics_hot_reader__attempt0009_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w1_0001__writer__attempt0001_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w1_0001_cleanup__cleanup__attempt0010_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w2_0002__forensics_hot_reader__attempt0011_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w2_0002__writer__attempt0002_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w2_0002_cleanup__cleanup__attempt0012_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w4_0003__forensics_hot_reader__attempt0013_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w4_0003__writer__attempt0003_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w4_0003_cleanup__cleanup__attempt0014_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w8_0004__forensics_hot_reader__attempt0015_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w8_0004__writer__attempt0004_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/4560eec83e2b4758818c5c98e52334c2__hot_scaling__v1__hot_scaling_smoke_threads_w8_0004_cleanup__cleanup__attempt0016_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w1_0005__forensics_hot_reader__attempt0017_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w1_0005__writer__attempt0005_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w1_0005_cleanup__cleanup__attempt0018_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w2_0006__forensics_hot_reader__attempt0019_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w2_0006__writer__attempt0006_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w2_0006_cleanup__cleanup__attempt0020_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w4_0007__forensics_hot_reader__attempt0021_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w4_0007__writer__attempt0007_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w4_0007_cleanup__cleanup__attempt0022_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w8_0008__forensics_hot_reader__attempt0023_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w8_0008__writer__attempt0008_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_processes_w8_0008_cleanup__cleanup__attempt0024_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w1_0001__forensics_hot_reader__attempt0009_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w1_0001__writer__attempt0001_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w1_0001_cleanup__cleanup__attempt0010_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w2_0002__forensics_hot_reader__attempt0011_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w2_0002__writer__attempt0002_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w2_0002_cleanup__cleanup__attempt0012_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w4_0003__forensics_hot_reader__attempt0013_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w4_0003__writer__attempt0003_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w4_0003_cleanup__cleanup__attempt0014_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w8_0004__forensics_hot_reader__attempt0015_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w8_0004__writer__attempt0004_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/c500f548aad0494998ce74df0d4d37a4__hot_scaling__v1__hot_scaling_smoke_threads_w8_0004_cleanup__cleanup__attempt0016_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_processes_w8_r1_10004_recovery__cleanup__attempt0001_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_processes_w8_r2_10005_recovery__cleanup__attempt0002_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_processes_w8_r3_10006_recovery__cleanup__attempt0003_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_threads_w1_r1_10007_recovery__cleanup__attempt0004_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_threads_w1_r2_10008_recovery__cleanup__attempt0005_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_threads_w8_r1_10001_recovery__cleanup__attempt0006_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_threads_w8_r2_10002_recovery__cleanup__attempt0007_json`
- `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/modal-single-volume-parallelism/results_cold_parallelism_forensics/raw/d106b3059fcf40a295ff1d8f7f0d5640__hot_scaling__v1__hot_scaling_confirm_threads_w8_r3_10003_recovery__cleanup__attempt0008_json`

## Unsupported or opaque layers

- Remote kernel/FUSE internals are unsupported unless explicitly returned in raw diagnostics.
- A failed or unavailable mechanism remains a retained diagnostic outcome.
