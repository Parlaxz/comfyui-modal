# TESTING8 — Native GDS and H100 InstantTensor Investigation

Date: 2026-09-28  
Scope: one strict native cuFile probe, then targeted InstantTensor AIO/URING probes.  
Production impact: no Golden integration; `production-005` was not modified.

## A. Historical Evidence Acknowledged

Historical InstantTensor experiments ran on NVIDIA RTX PRO 6000 Blackwell Server Edition, using InstantTensor 0.1.9 when recoverable.

| Historical result | CLIP | UNET |
|---|---:|---:|
| Automatic AIO, `copy=True` | 1.626 GB/s | 1.894 GB/s |
| AIO, 64 MiB, depth 4, `copy=False` | **6.594 GB/s** | **6.221 GB/s** |
| Concurrent CLIP+UNET | Worse and variable | Worse and variable |

The historical deep-depth tests regressed: AIO depth 32/128/256 did not improve this storage path. The historical ownership finding was that `copy=False` exposed reusable ring views while `copy=True` produced owning tensors.

## B. Native GDS Capability

The probe used the real file `/root/models/text_encoders/qwen_3_4b.safetensors`, strict compatibility settings, and a tiny CUDA 13-compatible native helper.

| Field | Result |
|---|---|
| GPU | NVIDIA H100 80GB HBM3 |
| Provider / observed region | GCP / `ap-northeast` |
| Driver / CUDA runtime | 580.95.05 / CUDA 13.0.48 |
| Kernel / sandbox | Linux 4.19.0-gvisor |
| `libcufile` available | YES; `/usr/local/cuda/lib64/libcufile.so`, `libcufile.so.0` |
| `cufile.h` availability | `/usr/local/cuda/include/cufile.h` |
| `gdscheck` | NOT AVAILABLE |
| Model-volume filesystem | Modal Volume mounted as `9p`; `statfs`: `v9fs` |
| `nvidia-fs` visibility | `/proc/driver/nvidia-fs` absent; `nvidia-fs` module absent |
| Relevant device nodes | `/dev/nvidia-fs` and `/dev/cufile` absent |
| Compatibility mode disabled | YES; task-local config `allow_compat_mode=false`, `force_compat_mode=false`, `CUFILE_FORCE_COMPAT_MODE=false` |
| `cuFileDriverOpen` | **FAILED: cuFile error `err=5001`, `cu_err=0`** |
| File handle registered | NOT ATTEMPTED; driver open failed first |
| GPU buffer registered | NOT ATTEMPTED; driver open failed first |
| 64 MiB native read | NOT ATTEMPTED; driver open failed first |
| Correctness | NOT APPLICABLE; no native read occurred |

`NATIVE_GDS_ON_MODEL_VOLUME = NO`

The lowest-level failure is the cuFile driver open failure before file registration. The missing `nvidia-fs` interface and `9p`/`v9fs` mount independently establish that this is not a native GDS-ready model-volume path. The GDS branch was stopped after this one capability probe.

## C. Current InstantTensor Semantics

| Item | Current result |
|---|---|
| Version | `0.2.0` |
| `copy=False` | Reusable, non-owning views into an internal ring; consume before the next yield and do not retain past context exit |
| `copy=True` | Owning cloned CUDA tensors; verified usable after context exit |
| Caller-provided final-GPU-destination API | **NO**; current public surface is `safe_open`, `Backend`, and `BackendPolicy` |
| AIO implementation | Explicit `Backend.AIO`; native extension opened with the requested backend value |
| URING implementation | Explicit `Backend.URING`; backend selection rejects it on this kernel rather than falling back |

Current source inspection also exposed the root cause of the initial UNET stall: automatic ring sizing. The probe originally set 64 MiB chunks and depth 4 but left `buffer_size=None`, allowing InstantTensor to select a larger H100 ring based on tensor layout and available VRAM. The fixed probe explicitly bounds the ring to 256 MiB, then permits the library's required minimum for a large individual tensor. The fixed UNET run completed in 6.95 s instead of exceeding the 180 s watchdog.

## D. AIO Results

All runs used explicit `Backend.AIO`, 64 MiB chunks, depth 4, and a requested 256 MiB device ring. Provider/region was GCP/`ap-northeast` for this H100 deployment.

| Run | Model | Copy | Backend proof | Wall | Bytes | GB/s | Staging |
|---|---|---|---|---:|---:|---:|---|
| AIO-CLIP-1 | CLIP | false | observed `Backend.AIO` | 2349.6 ms | 8,044,936,192 | 3.424 | 256 MiB requested; library raised actual ring to 777,912,320 B for the largest tensor |
| AIO-CLIP-2 | CLIP | false | observed `Backend.AIO` | 2615.8 ms | 8,044,936,192 | 3.076 | same |
| AIO-CLIP-3 | CLIP | false | observed `Backend.AIO` | 2037.5 ms | 8,044,936,192 | 3.948 | same |
| AIO-UNET-1 | UNET | false | observed `Backend.AIO` | 6954.6 ms | 12,309,817,472 | 1.770 | 256 MiB requested |
| AIO-UNET-2 | UNET | false | observed `Backend.AIO` | 7259.3 ms | 12,309,817,472 | 1.696 | 256 MiB requested |
| AIO-UNET-3 | UNET | false | observed `Backend.AIO` | 9426.9 ms | 12,309,817,472 | 1.306 | 256 MiB requested |

Copy-false summaries:

| Model | Mean wall | Median wall | Mean GB/s | Full-data validation |
|---|---:|---:|---:|---|
| CLIP | 2334.3 ms | 2349.6 ms | 3.483 | PASS, SHA-256 `e48ed5be...ab101a1` |
| UNET | 7880.3 ms | 7259.3 ms | 1.591 | PASS, SHA-256 `f0660776...fd93d30` |

The copy-false probes matched expected tensor names/counts/bytes. CUDA allocation/reserved memory was zero after teardown; InstantTensor does not expose host staging bytes in this API.

## E. URING Results

| Run | Model | Result |
|---|---|---|
| URING-CLIP-1 | CLIP | **INVALID / BACKEND NOT ENGAGED** |

Exact error:

```text
RuntimeError: No available backend was found among candidates [URING].
io_uring requires Linux kernel 5.6 or newer; the detected kernel version is 4.19.0-gvisor.
```

No AIO fallback occurred. No UNET URING run was launched after the explicit backend failure.

## F. Ownership Tax

One owning-output observation was collected per model using the same fixed AIO geometry.

| Backend | Model | Copy=false wall / GB/s | Copy=true wall / GB/s | Added wall | Slowdown |
|---|---|---:|---:|---:|---:|
| AIO | CLIP | 2334.3 ms / 3.483 | 4349.4 ms / 1.850 | +2015.1 ms | +86.3% |
| AIO | UNET | 7880.3 ms / 1.591 | 11292.9 ms / 1.090 | +3412.6 ms | +43.3% |

Both copy-true probes passed the post-context owning-storage access check.

## G. Final Answers

**Does native GDS work on the actual Modal model Volume?**  
**NO** — `cuFileDriverOpen` fails with cuFile error `5001`; `nvidia-fs` is absent and the model path is `9p`/`v9fs`.

**Does InstantTensor AIO beat the current ~6.5 GB/s source target on H100?**  
**NO** — CLIP mean is 3.483 GB/s and UNET mean is 1.591 GB/s.

**Does InstantTensor URING genuinely engage under current gVisor?**  
**NO** — gVisor reports kernel 4.19.0, below the required 5.6.

**Does URING beat AIO?**  
**NOT TESTABLE** — URING is unsupported and did not engage.

**Is stock InstantTensor copy=False usable as final authoritative model storage?**  
**NO** — it is reusable ring storage and must be consumed inline.

**Is stock InstantTensor copy=True fast enough to justify integration?**  
**NO** — it is 1.850 GB/s for CLIP and 1.090 GB/s for UNET, with a measured ownership tax of 2.015 s and 3.413 s respectively.

**Does current InstantTensor expose a true caller-provided final-GPU-destination path?**  
**NO** — no such public API was found in version 0.2.0.

**Should we proceed to O_DIRECT/raw-AIO next?**  
**NO** — native AIO is already below target, URING is blocked by gVisor, GDS is unavailable, and another raw-AIO campaign would not address the measured ownership and filesystem limits.

## Evidence Files

- `TESTING8_GDS_PROBE_RESULT.json`
- `TESTING8_INSTANTTENSOR_INSPECTION.json`
- `TESTING8_AIO_CLIP_FIXED_1.json`
- `TESTING8_AIO_CLIP_FIXED_2.json`
- `TESTING8_AIO_CLIP_FIXED_3.json`
- `TESTING8_AIO_UNET_FALSE_FIXED.json`
- `TESTING8_AIO_UNET_FIXED_2.json`
- `TESTING8_AIO_UNET_FIXED_3.json`
- `TESTING8_AIO_UNET_VALIDATION.json`
- `TESTING8_AIO_CLIP_TRUE_FIXED.json`
- `TESTING8_AIO_UNET_TRUE_FIXED.json`
- `TESTING8_URING_CLIP_FIXED_1.json`
