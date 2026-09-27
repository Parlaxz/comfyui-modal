# Testing 7 Stale-File Read Report

## Scope

- Workspace: Testing 7 / `main`
- Existing app: `sept-unetclip-04-source-ceiling-oracle`
- Existing Volume: `comfyui-models`
- Mount: `/root/models`, read-only
- Target: `/root/models/text_encoders/qwen_3_4b.safetensors`
- File size: `8,044,982,048` bytes
- Payload: `8,044,936,192` bytes
- Allocation: exactly 12 CPU, no GPU
- Reader: QD8, 4 MiB blocks
- No hash, warmup, model construction, H2D, or intentional preread

The existing source-only reader was reused. It uses static disjoint ranges, one shared file descriptor, positioned `preadv` reads, worker-join timing, and byte reconciliation. No new harness was created.

## Step-by-step

### 1. Existing implementation

Read-only discovery located the historical QD reader and the existing deployable Testing 7 source-only endpoint:

- `e04_source_ceiling_modal.py`
- `comfymodal_runtime/source_ceiling_oracle.py`

The clean Workspace 3 corpus reader was not used because it intentionally primes the file, violating the no-preread requirement.

### 2. Testing 7-only configuration fixes

Only the existing Testing 7 endpoint was changed:

- CPU allocation changed from 4 to 12.
- GPU explicitly disabled.
- CPU-only PyTorch dependency added because the reader requires Torch setup.
- 4 MiB added to the accepted block-size set.
- CPU-only pageable-buffer fallback added when pinned memory is unavailable without a GPU.

The QD/preadv/static-range read algorithm remained unchanged. The buffer fallback changes only the backing from pinned tensor to pageable host bytes, as required for a no-GPU run.

### 3. Deployment attempts

- The initial deploy hit a Windows `charmap` Unicode-output error; no reader call occurred.
- The same deploy succeeded after enabling UTF-8 output.
- The existing app was redeployed after each Testing 7-only compatibility fix.
- The final deployment succeeded with CPU12 and `gpu: null`.

### 4. Failed Testing 7 attempts

These artifacts are retained:

1. `first_access.json` — rejected the 4 MiB configuration; no payload read.
2. `first_access_retry.json` — missing `torch`; no payload measurement.
3. `first_access_cpu_torch.json` — CPU-only Torch had no pinned-memory allocator; no payload measurement.

### 5. Successful first-access read

Artifact:

```text
unetClipExperimentsSeptember/12_stale_file_first_reread/first_access_cpu_pageable.json
```

- Wall: `1,561.809034 ms`
- Throughput: `5.151037 GB/s`
- Exact returned bytes: `8,044,936,192`
- Expected/requested bytes: `8,044,936,192`
- Gaps: `0`
- Overlaps: `0`
- Syscalls: `1,920`
- Observed QD: `8`
- CPU: `12`
- GPU: `null`
- CUDA used: `false`
- H2D used: `false`
- Buffer: pageable host bytes
- Coverage: valid

Container region: GCP `europe-west8`.

### 6. Successful immediate reread

Artifact:

```text
unetClipExperimentsSeptember/12_stale_file_first_reread/immediate_reread_cpu_pageable.json
```

- Wall: `2,002.792039 ms`
- Throughput: `4.016860 GB/s`
- Exact returned bytes: `8,044,936,192`
- Expected/requested bytes: `8,044,936,192`
- Gaps: `0`
- Overlaps: `0`
- Syscalls: `1,920`
- Observed QD: `8`
- CPU: `12`
- GPU: `null`
- CUDA used: `false`
- H2D used: `false`
- Coverage: valid

Container region: GCP `europe-west1`.

## Conclusion

The stale Testing 7 CLIP file did not show the historical >40 GB/s behavior under this CPU-only QD8/4 MiB configuration:

- First access: `5.15 GB/s`
- Immediate reread: `4.02 GB/s`

Testing 6 was not touched: no Testing 6 deployment, function invocation, file access, or remote inspection occurred.
