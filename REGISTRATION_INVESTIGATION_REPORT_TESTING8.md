# C0 Registration Investigation

## A. Identity

- Starting HEAD: `55c4d6a9a3a15e0c618f9d7edbb341c97b7c6ead` (`TESTING8`).
- Instrumentation commits: none. The worktree was already dirty; diagnostic changes were deployed from the dirty tree and unrelated user changes were preserved.
- Diagnostic selectors:
  - `COMFYMODAL_GOLDEN_C0_REGISTRATION_DIAG=1`
  - `COMFYMODAL_GOLDEN_C0_REGISTRATION_ORDER=overlap|register_first`
  - `COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT=0|1`
- Baseline profile: `golden_p1_parallel_m2clip_h100_registration_diag`.
- Candidate config: H100, CPU 12, QD4, four reader processes, 64 MiB windows, `mmap_fresh`, native libc memcpy, persistent FDs, `FIVE_SLOTS=1`, `READER_GATE=1`, `DMA_RING=0`, `HOST_REGISTER=1`, 5 x 64 MiB = 320 MiB POSIX SHM, direct registered-SHM H2D.
- Deployments: overlap `fceee3b1...`; register-first `2be3197b...`; effective context-preinit `b2783cf3...`; one-shot probe `1542ce8f...`.

## B. Historical Versus Current

| Ref | Mapping | Bytes | API / flags | Context | Ordering | Timing boundary |
|---|---|---:|---|---|---|---|
| TESTING8 | `multiprocessing.shared_memory.SharedMemory`, `/dev/shm` POSIX | 320 MiB | PyTorch `cudaHostRegister`, `0` | `cuCtxGetCurrent=0x0` before call; primary context appears during call | Child `Popen` before register in overlap arm | `register_start_ns` to `register_end_ns`, call only |
| production-005 tag `a186d4c` | POSIX `SharedMemory` | 512 MiB, 8 x 64 MiB | PyTorch `cudaHostRegister`, `0` | Runtime did not explicitly preinitialize it in the registration implementation | Register first, then child `Popen` | `register_ms` wraps only `register()`; arena setup was separately reported |
| C0 overlap change `533ce94` | POSIX `SharedMemory` | 512 MiB | PyTorch `cudaHostRegister`, `0` | Same unresolved runtime-context behavior | Child `Popen` before register | Same exact call-only boundary |
| standalone M2 `ef34e23` | `mp.RawArray`, anonymous inherited shared mapping | QD4 x 2 x 64 MiB = 512 MiB | raw `cuMemHostRegister_v2`, `0` | Explicit `cuInit` + fresh `cuCtxCreate`; context popped only after setup | Readers fork and become ready, then parent `on_ready` registers before release | `register_ms` wraps only `cuMemHostRegister`; `setup_ms` includes register plus GPU allocation/stream |
| optimized M2 `3f38b26` | anonymous `mmap(-1, ...)`, shared inherited mapping | 256 MiB in the reported optimized arm | raw `cuMemHostRegister_v2`, `0` | Explicit raw driver context initialized separately | Context init overlapped reader fork/prep; register remained before source release | Report separates `ctx_init_ms`, `register_ms`, and allocation |

The historical `~65 ms` number is not a single generic “CUDA setup” boundary. The M2 report explicitly separates raw context initialization from `cuMemHostRegister`; the optimized report describes `cuMemHostRegister` at roughly `40–65 ms` and context initialization separately. The current C0 `register_ms` is a call-only wall, but its call begins with no current CUDA context.

## C. Current Deep Trace

All three rows below are valid true-cold H100 runs from the same overlap deployment and exact five-slot candidate. `Rss`, `Locked`, and fault values are the relevant `/proc`/rusage observations; gVisor field reliability is limited.

| Run | Provider:region | Register wall | Process CPU delta | Thread CPU delta | User/system delta | Context switches | RSS before -> after | Locked | Context before -> after |
|---|---|---:|---:|---:|---|---|---|---|---|
| `23-23-38` | `CLOUD_PROVIDER_UNSPECIFIED:eu-north` | 503.318 ms | 820 ms | 550 ms | 390 / 420 ms | 0 voluntary/involuntary delta | 0 -> 327680 kB | 0 -> 0 kB | `0x0` -> nonzero |
| `23-24-41` | `CLOUD_PROVIDER_UNSPECIFIED:eu-north` | 414.664 ms | 870 ms | 560 ms | 500 / 370 ms | 0 voluntary/involuntary delta | 0 -> 327680 kB | 0 -> 0 kB | `0x0` -> nonzero |
| `23-26-24` | `CLOUD_PROVIDER_UNSPECIFIED:eu-north` | 642.760 ms | 1000 ms | 670 ms | 440 / 560 ms | 0 voluntary/involuntary delta | 0 -> 327680 kB | 0 -> 0 kB | `0x0` -> nonzero |

Common identity: NVIDIA H100 80GB HBM3, Torch `2.14.0+cu130`, CUDA runtime `13.0`, device 0, flags `0`, return code `0`, pointer page-aligned (`mod 4096 = 0`), 4 KiB kernel/MMU pages, POSIX SHM mapping `/dev/shm/psm_*`, `VmFlags=rd wr sh mr mw ms`, `AnonHugePages=0`, `numa_maps` unavailable. The relevant mapping was lazy before registration (`Rss=0`) and fully resident after it (`Rss=327680 kB`).

The child timeline proves overlap rather than hiding it: `popen_return` precedes `cuda_host_register_begin`; child attach, reader fork, and startup probes occur while the register span is active. Child startup was `684–933 ms` in these rows, but moving it after registration did not reduce the register wall materially.

## D. Child-Overlap A/B

| Arm | Register samples | Child startup |
|---|---:|---:|
| Current overlap | 503.3, 414.7, 642.8 ms | 684–933 ms, overlapping register |
| Register first | 489.2, 419.3 ms | 172–223 ms, outside register |

**Does concurrent child boot/fork inflate `cudaHostRegister`? NO, not materially.** The samples overlap broadly and the registration call still remains in the hundreds of milliseconds when child creation is completely removed from its interval. Child overlap affects the total establishment critical path, but it is not the explanation for the registration gap.

## E. Mapping Provenance A/B

One-shot containers, 320 MiB, flags `0`, current primary context explicitly made current, same H100 and Torch/CUDA runtime:

| Mapping | API | Register wall |
|---|---|---:|
| POSIX `SharedMemory` | PyTorch `cudaHostRegister` | 191.43 ms |
| anonymous `MAP_SHARED` | PyTorch `cudaHostRegister` | 66.00, 67.21 ms |
| anonymous `MAP_PRIVATE` control | PyTorch `cudaHostRegister` | 91.85 ms |
| historical M2 `RawArray` + fresh raw driver context | `cuMemHostRegister_v2` | 24.86, 45.91 ms |

**Does mapping provenance explain a material part of the gap? YES.** POSIX SHM is about 2.9x slower than anonymous shared mapping under the same current-context/API conditions. The exact historical-style primitive remains in the tens-of-milliseconds class on today’s H100 environment.

## F. Historical Primitive Replay

**YES, it still registers cheaply.** The replay used the historical `RawArray` anonymous shared allocation, a fresh raw driver context, `cuMemHostRegister_v2`, flags `0`, one registration, one unregister, and process exit. It measured `24.86 ms` and `45.91 ms` on current H100 infrastructure. It did not run source reads or H2D; this is intentionally a registration primitive replay, not a production-loader claim.

## G. Context Analysis

Current baseline deep traces show `cuCtxGetCurrent=0x0` before `torch.cuda.cudart().cudaHostRegister` and a nonzero context after it. A first preinit attempt using `torch.cuda.init()` was ineffective: it took `0.007 ms` and left the current handle at `0x0`.

The effective isolated arm used driver `cuDevicePrimaryCtxRetain` plus `cuCtxSetCurrent` before registration. It measured:

- context preinit: `288.389 ms`;
- current POSIX SHM registration after preinit: `172.647 ms`;
- nonzero current context before and after registration.

**Is CUDA-context choice a major contributor? YES.** The current call includes lazy primary-context setup. Explicit preinitialization removes roughly `~288 ms` from the register call, although the POSIX mapping still costs roughly `~173 ms`.

## H. Page Materialization

Baseline mapping state was `Rss=0 kB`, `Private_Dirty=0 kB`, and `Locked=0 kB` before registration; after registration it was `Rss=327680 kB` and `Private_Dirty=327680 kB`. rusage reported zero page-fault deltas in this gVisor environment and must not be treated as authoritative. The RSS transition is direct evidence that registration materializes/pins the lazy mapping here.

This agrees with the prior populate experiment: prepopulation can make the registration subspan faster but costs more in population plus registration end-to-end. No new evidence supports prepopulation as an optimization recommendation.

## I. Registration Cost Model

- Lazy primary-context setup inside current `cudaHostRegister`: approximately `288 ms` when explicitly separated.
- POSIX SHM mapping registration after context is current: approximately `173–191 ms` in the isolated probes.
- Anonymous shared mapping registration after the same current context/API setup: approximately `66–67 ms`.
- Historical raw driver context + anonymous RawArray primitive: approximately `25–46 ms`.
- Concurrent child penalty: not material; register-first did not collapse the distribution.
- Environment/host variance: at least tens to low hundreds of milliseconds across valid same-arm observations; this is residual variance, not an explanation for the structural provenance difference.
- Unexplained residual: the `~20–30 ms` spread between anonymous shared and historical raw-context replay is consistent with API/context implementation and host variance; it is not needed to explain the current gap.

## J. Final Answers

- **Why is current `cudaHostRegister` ~350–500 ms?** The call receives a lazy POSIX SHM mapping while no CUDA context is current. It performs both lazy PyTorch primary-context establishment and expensive registration/materialization of the `/dev/shm` mapping. The deep arm separates these into about `288 ms` context setup plus `173 ms` POSIX registration, with normal variation producing the observed `350–500+ ms` class.
- **Why was historical M2 much cheaper?** M2 used an anonymous inherited shared mapping, explicitly established a raw driver context before registration, and called the raw driver API directly. Replaying that primitive today gives `25–46 ms`; anonymous shared plus the current primary API gives `66–67 ms`.
- **Is current POSIX SHM itself responsible?** **YES, for a material part.** POSIX SHM is about `191 ms` versus `66 ms` for anonymous MAP_SHARED under matched current-context/API conditions.
- **Does overlapping child startup inflate registration?** **NO, not materially.**
- **Is lazy-page materialization a major contributor?** **PARTIALLY.** Registration changes RSS from zero to the full 320 MiB, but the prior end-to-end population result still does not justify prepopulation.
- **Is CUDA-context choice a major contributor?** **YES.** The current call begins with no current context; explicit driver primary-context setup removes roughly `288 ms` from the call boundary.
- **Is the current 350–500 ms cost fundamentally unavoidable?** **NO.** The current H100 reproduced `66 ms` with anonymous shared mapping/current context and `25–46 ms` with the historical raw primitive.
- **Best next registration experiment:** build a fork-inherited anonymous `MAP_SHARED` C0 diagnostic arm with the same five-slot geometry, source readers, direct H2D, and explicit primary-context preinitialization; compare it against current POSIX SHM without changing QD, gate, reader algorithm, or H2D topology. This report does not promote or implement that arm.

No source algorithm, QD, four-millisecond gate, DMA ring, restore architecture, `production-005`, or production tag was changed.
