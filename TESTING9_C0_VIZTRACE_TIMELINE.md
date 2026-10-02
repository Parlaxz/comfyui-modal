# TESTING9 C0 Diagnostic Timeline

## Request Identity

- App: `testing9-c0-mmap-intertwined`
- Deployment fingerprint: `2ae546bdd6d37ac5ce42dee13fb98db55de36e1232238ad0d21323a520c7c430`
- GPU: H100
- Provider/region: `CLOUD_PROVIDER_GCP`, `us-west`
- Runtime: current C0, Fresh lifecycle, QD4, four persistent readers, 512 MiB
  arena, native libc memcpy, existing dispatcher/H2D path
- Request: one true-cold Golden Parallel request
- Request ID: `golden-p1-0-bda0727bfb1a`
- Container session: `bd56fba4762b476c`

Raw request evidence:

`artifacts/phase_p1_parallel_golden_v1/cohort_2026-09-29_07-17-52_681449/attempt_0_events.json`

Derived machine-readable summary:

`artifacts/testing9_viztrace/viztrace_parent_child_summary.json`

## Trace Availability

Parent request tracing was enabled with `COMFYMODAL_V2_FULL_TRACE=1` and the
request deep-trace selector. The request reported `viztracer_status=ok` and a
full-trace bundle descriptor. The descriptor points to:

`v2-full-trace/2026-09-29/bd945dac427040a094feefcf48dcb237/bundle.tar.gz`

The bundle was not present at that remote Volume path when downloaded. The raw
parent event stream and C0 per-window traces are available and were analyzed;
the merged VizTracer JSON itself is unavailable. The child-only VizTracer
bundle was not present in the retained request artifact. This is an evidence
limitation, not a claim that tracing executed no code.

## Model Boundaries

The raw trace/event evidence provides these current request boundaries:

| Model | Source span | Full model load | GPU-ready tail |
|---|---:|---:|---:|
| CLIP | 1659.9 ms | 2359.2 ms | 5.8 ms |
| UNET | 2331.2 ms | 2431.6 ms | 5.3 ms |

CLIP source begins after a 684.7 ms pre-source interval in this request. UNET
source begins about 10.0 ms before its mapped source span. The parent event
timeline shows CLIP forward from approximately `46.596 s` to `50.084 s` in the
request clock. UNET source/model load overlaps that forward interval.

The event-level overlap proof reports:

- CLIP forward wall: `3488.2 ms`
- UNET load wall: `2507.0 ms`
- overlap intersection: `2507.0 ms`
- overlap outcome: `success`, `true_overlap=true`

## Per-Window Distributions

### CLIP

63 logical source operations were captured.

| Phase | Median | P90 | P95 | P99 | Max | >50 ms | >100 ms | >250 ms | >500 ms | >1000 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mmap | 0.043 ms | 0.085 | 0.201 | 0.313 | 0.338 | 0 | 0 | 0 | 0 | 0 |
| mapped access + memcpy | 81.3 ms | 135.5 | 144.4 | 146.9 | 147.3 | 58 | 24 | 0 | 0 | 0 |
| munmap | 2.75 ms | 4.76 | 5.70 | 5.96 | 5.99 | 0 | 0 | 0 | 0 | 0 |
| pipe round trip | 84.7 ms | 142.3 | 147.5 | 151.0 | 153.2 | 58 | 27 | 0 | 0 | 0 |
| lease wait | 6.57 ms | 11.3 | 13.1 | 16.4 | 17.8 | 0 | 0 | 0 | 0 | 0 |
| H2D/slot return | 6.59 ms | 9.39 | 10.4 | 11.2 | 14.6 | 0 | 0 | 0 | 0 | 0 |

### UNET

95 logical source operations were captured.

| Phase | Median | P90 | P95 | P99 | Max | >50 ms | >100 ms | >250 ms | >500 ms | >1000 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mmap | 0.042 ms | 0.067 | 0.070 | 0.094 | 0.489 | 0 | 0 | 0 | 0 | 0 |
| mapped access + memcpy | 80.5 ms | 111.2 | 122.7 | 137.7 | 150.7 | 90 | 13 | 0 | 0 | 0 |
| munmap | 2.57 ms | 2.78 | 2.80 | 2.96 | 3.04 | 0 | 0 | 0 | 0 | 0 |
| pipe round trip | 84.2 ms | 114.8 | 126.1 | 141.1 | 153.8 | 91 | 13 | 0 | 0 | 0 |
| lease wait | 6.57 ms | 12.4 | 15.7 | 37.6 | 40.7 | 0 | 0 | 0 | 0 | 0 |
| H2D/slot return | 6.48 ms | 10.9 | 14.0 | 28.1 | 30.9 | 0 | 0 | 0 | 0 | 0 |

## Reader Concurrency

Time-weighted active mapped-access/memcpy concurrency:

| Model | 0 readers | 1 reader | 2 readers | 3 readers | 4 readers | Effective concurrency |
|---|---:|---:|---:|---:|---:|---:|
| CLIP | 0.22% | 3.23% | 11.63% | 20.74% | **64.18%** | **3.45** |
| UNET | 0.00% | 0.00% | 0.00% | 0.00% | **100.00%** | **3.37** |

The UNET source interval in this request kept all four readers active for the
entire mapped-access/memcpy union window. The CLIP interval had short bubbles
and spent 64.2% of its mapped-access window at all four readers active.

Per-reader busy time was approximately balanced:

- CLIP: readers 0-3 = `1407`, `1416`, `1435`, `1465` ms
- UNET: readers 0-3 = `1907`, `1971`, `1982`, `1977` ms

## CLIP Pre-Source Waterfall

The current request's CLIP pre-source interval is `684.7 ms` from model-load
entry to the first child mmap start. Existing setup marks show the following
critical-path components:

| Component | Measured evidence | Relationship |
|---|---:|---|
| C0 arena backing creation | 5.3 ms | first-use setup |
| C0 host registration | current arena evidence; not a new UNET operation | overlaps child setup |
| reader spawn/readiness | four child PIDs and readiness milestones | overlaps registration |
| transfer resources | request setup marks | before dispatcher execute |
| layout/owner/dispatcher setup | request setup marks | serial setup before first command |
| first control/lease handoff | first window trace | final gap before mmap |

The parent C0 trace records four reader PIDs and four startup-ready milestones.
The current parent event evidence does not expose a separate VizTracer row for
every internal Python call, so the exact remaining pre-source gap cannot be
split further without the missing raw VizTracer bundle. It is not silently
assigned to source service.

## CLIP Forward and UNET Scheduling

The parent event timeline proves UNET load overlaps CLIP forward for the full
`2507.0 ms` UNET-load interval. In this request:

- UNET source had effective mapped-copy concurrency `3.37`.
- All four UNET readers were active across the measured mapped-access union.
- UNET lease wait median was `6.57 ms`; maximum `40.7 ms`.
- H2D/slot-return median was `6.48 ms`; maximum `30.9 ms`.

This request does not show a material reader-concurrency collapse while CLIP
forward was active. The available event evidence is high-level; the missing
VizTracer bundle prevents a finer CPU runnable-versus-running attribution.

## Current Interpretation

The retained diagnostic request shows:

- mmap syscall and munmap are small relative to mapped access + memcpy;
- CLIP has a large first-use pre-source interval;
- UNET has a small pre-source interval after CLIP setup;
- mapped access + memcpy is the dominant per-window source phase;
- control/pipe round trips track the mapped-copy duration but do not create
  250+ ms waits in this request;
- lease/H2D waits are single-digit median milliseconds;
- reader concurrency remains high during the overlapping UNET load.

The trace is diagnostic only and was not used as a production throughput
measurement. No architecture or production change was made from this result.

## E31 One-Shot Torch Profiler Pass

A second Fresh diagnostic request enabled the existing E31 one-shot profiler
with `COMFYMODAL_V2_E31_FORWARD_PROFILE=1` and left the broader profiler off.
This request was diagnostic-only on the same experimental app/code path.

Forward timing from that request:

- host wall: `4124.984 ms`;
- CUDA event elapsed: `4114.868 ms`;
- host-only residual: `10.116 ms`;
- weight/bias/other casts: `0`;
- real conversion bytes: `0`;
- new cast allocations: `0`.

Backend evidence:

- Comfy Kitchen INT8 attention calls: `340`;
- masked Comfy Kitchen calls: `0`;
- PyTorch attention calls: `0`;
- Sage specialized calls: `0`;
- fallback attention calls: `0`.

The one-shot profiler captured the first public attention call:

| Profiler item | Value |
|---|---:|
| Public call | `comfy_kitchen_int8_attention` |
| Count | 1 |
| Self CPU time | 34.121 ms |
| Total CPU time | 42.450 ms |
| Device time | 0.0269 ms |

This profiler pass did not capture all 340 attention calls as individual
profiler rows. Therefore the `4114.868 ms` CUDA forward interval cannot be
legitimately partitioned into an exact per-attention-kernel sum from this
artifact. The evidence does establish that the forward is Comfy Kitchen INT8,
not a cast/conversion path, and that the first profiled public attention call is
not representative of the full forward wall by itself.
