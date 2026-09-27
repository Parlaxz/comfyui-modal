# V2 UNET-Backing A/B Evidence Report

**Question:** do slow 12.31 GB CPU→GPU UNET transfers come from safetensors/Volume-backed (mmap) pages, or from the general Modal host memory/PCIe path?

**Answer (evidence below):** neither. The snapshot UNET is **100 % anonymous RAM in both arms** (verified per-storage against `/proc/self/maps` at snapshot-build and at transfer time), a synthetic 2 GiB anonymous H2D probe is **fast and stable (~17–24 GB/s) on every run**, and forcing an anonymous-RAM clone (Arm B) changes **nothing** about the slow tail. The tail lives in the **snapshot/model page path** — the traversal of the restored 12.31 GB anonymous pages — not the Volume mmap, not the DMA path, not the parameter-copy structure. No production fix ships.

Experiment dirs (every attempt preserved):
- Full block: `comfymodal-data/benchmarks/runs/v2_2026-08-06_12-22-32/` (16 attempts: 2 discarded + 6 valid per arm)
- Second block: `comfymodal-data/benchmarks/runs/v2_2026-08-06_12-12-57/` (6 attempts: snapshot-build + discard + 1 valid per arm)
- First block (superseded parser instrumentation; transfer measurements valid, backing counts unreliable): `comfymodal-data/benchmarks/runs/v2_2026-08-06_11-55-04/`

Commit: `c22844b`-era instrumentation extended here; final commit SHA at the bottom.

## Protocol

1. Two shadow deployments, same image, same config (CPU 16 / mem 49152 MiB, TBASE/O0, single-use containers, minimal teardown, VAE snapshot, exact CLIP conditioning cache, UNET activation `late`, diagnostics off by default, variance + host diagnostics ON for this study):
   - **Arm A** `stable-modal-comfy-v2-backing-a-shadow`: current CPU-snapshot UNET (backing verified, not mutated).
   - **Arm B** `stable-modal-comfy-v2-backing-b-shadow`: anonymous-RAM snapshot (`COMFYMODAL_V2_ANON_UNET_SNAPSHOT=1` — every UNET parameter/buffer cloned into fresh anonymous CPU memory immediately before snapshot capture, old storages released, GC run, re-verified).
2. Strictly interleaved A,B,A,B,… (placement/scheduling noise shared), unpinned, 25 s gaps.
3. Per arm: the snapshot-build run and the run immediately after it discarded; **7 valid measured cold runs collected** (restore_count==1 && request_count==1 && fresh identity) — 1 from the second block + 6 from the full block.
4. Every attempt carries: `host_diagnostics` (provider/region/CPU/GPU UUID/task id), the per-run `synth_h2d_probe` (2 GiB touched anonymous contiguous float32 H2D, measured immediately before the real transfer, GPU tensor freed before the UNET loads), the real `synchronized_transfer_ms`/GB/s, restore, scheduling, sampler wait, and `/proc/self/maps` backing evidence.

## Backing verification (per-storage, `/proc/self/maps`)

Map lines are parsed by fixed-width columns (`start-end perms offset dev inode [pathname]`); a missing pathname is **anonymous** — an inode in the 5th column is never a pathname. The UNET has 454 unique storages / 12,309,821,472 bytes (6.15 B params × 2 bytes bf16).

| point | arm | tensors | anonymous | file-backed | unknown |
|---|---:|---:|---:|---:|---:|
| snapshot build (before capture) | A | 454 | **454** | 0 | 0 |
| snapshot build (before capture) | B | 454 | **454** | 0 | 0 |
| snapshot build (after Arm-B clone) | B | 454 | **454** | 0 | 0 |
| transfer time (per-run, all 14 measured runs) | A & B | 454 | **454** | 0 | 0 |

Sample maps lines (build-time, arm A): every storage resolves into `555ad74e9000-555b3e309000 rw-p 00000000 00:00 0  [heap]` (and equivalent heap regions) — plain anonymous private mappings. No storage address maps to a safetensors/Volume file in either arm, at either point.

Arm-B clone verification: `clone.cloned = 454`, `clone.bytes = 12,309,821,472`, `clone.error = ""` — every parameter and buffer was re-allocated into fresh anonymous memory with dtype/shape/strides preserved and parameter objects intact; post-clone re-verification is again 454/454 anonymous. The clone is backing-neutral: the source was already 100 % anonymous, so it cannot change page backing by construction.

## Per-run results (14 valid measured cold runs)

All runs: `CLOUD_PROVIDER_GCP` us-east4, CPU AMD family 191/model 2 (redacted name), RTX PRO 6000 Blackwell, PCIe5 ×16.

| arm | file | tfr (ms) | GB/s | class | synth (ms) | synth GB/s | restore (ms) | sched (ms) | sampler wait (ms) | GPU uuid |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| A | 12-12-57/attempt_0004 | 5856 | 2.10 | SLOW | 126 | 17.1 | 894 | 5 206 | 4 808 | f88ccf02 |
| A | 12-22-32/attempt_0004 | 5043 | 2.44 | SLOW | 109 | 19.8 | 2 491 | 3 272 | 4 107 | 881cd087 |
| A | 12-22-32/attempt_0006 | 7667 | 1.82 | SLOW | 114 | 18.8 | 3 010 | 6 696 | 0 | dd10262e |
| A | 12-22-32/attempt_0008 | 7424 | 1.87 | SLOW | 95 | 22.6 | 1 911 | 6 332 | 0 | 80ea8d48 |
| A | 12-22-32/attempt_0010 | **1671** | 7.39 | FAST | 93 | 23.1 | 652 | 10 186 | 856 | 176c31e2 |
| A | 12-22-32/attempt_0012 | 5932 | 2.08 | SLOW | 88 | 24.4 | 1 169 | 4 700 | 3 164 | a4a64489 |
| A | 12-22-32/attempt_0014 | 7360 | 1.90 | SLOW | 105 | 20.5 | 1 012 | 6 287 | 0 | 257c0ecb |
| B | 12-12-57/attempt_0005 | 8010 | 1.71 | SLOW | 97 | 22.1 | 7 868 | 13 415 | 0 | 176c31e2 |
| B | 12-22-32/attempt_0005 | 9152 | 1.47 | SLOW | 91 | 23.6 | 4 167 | 3 957 | 0 | dd10262e |
| B | 12-22-32/attempt_0007 | 7487 | 1.86 | SLOW | 91 | 23.6 | 463 | 11 088 | 0 | 80ea8d48 |
| B | 12-22-32/attempt_0009 | 7941 | 1.73 | SLOW | 111 | 19.3 | 1 646 | 8 209 | 0 | 0034f8a4 |
| B | 12-22-32/attempt_0011 | **1665** | 7.42 | FAST | 98 | 21.9 | 3 168 | 4 822 | 933 | a4a64489 |
| B | 12-22-32/attempt_0013 | **1670** | 7.40 | FAST | 90 | 23.8 | 2 635 | 6 372 | 866 | 65d7d42c |
| B | 12-22-32/attempt_0015 | 7247 | 1.92 | SLOW | 105 | 20.4 | 3 477 | 6 596 | 0 | 881cd087 |

Per arm: **A** — median 5 932 ms, 1 FAST / 0 MEDIUM / 6 SLOW; **B** — median 7 487 ms, 2 FAST / 0 MEDIUM / 5 SLOW. Synth probe: A median 105 ms (17.1–24.4 GB/s), B median 97 ms (19.3–23.8 GB/s) — every run, both arms, fast and slow.

(The first block at `11-55-04`, superseded instrumentation: same transfer measurements — A 6 400 ms SLOW, B 7 292 ms SLOW, synth 20–24 GB/s — but its backing counts were corrupted by a maps-parser bug, fixed before the second/full blocks.)

## Interpretation (framework mapping)

**"A and B variable, synthetic H2D stable: snapshot/model page backing is causal, but not specifically the original Volume mmap."**

- **A vs B:** no difference. A: 1F/0M/6S, B: 2F/0M/5S; medians 5.9 s vs 7.5 s (the anonymous arm is not faster — if anything noisier); FAST runs at 1.67 s exist in both. The clone provides no latency benefit.
- **Synthetic vs real:** the 2 GiB anonymous H2D is 88–126 ms @ 17–24 GB/s on **every** run — including the runs whose real 12.31 GB transfer takes 7–9 s @ 1.5–2 GB/s. The general host RAM/PCIe/DMA path is not degraded; the slow operation is specific to traversing the restored snapshot's 12.31 GB page set.
- **Volume mmap:** rejected by direct measurement — 454/454 storages are anonymous `[heap]` at snapshot build AND at transfer time in both arms. There is no safetensors/Volume file backing to eliminate (the loader already materializes into anonymous RAM under the snapshot build context).
- **Parameter-copy structure:** rejected as the mechanism — Arm B replaced every storage with a fresh anonymous copy (verified: cloned 454/454, 12.31 GB) and the tail is unchanged.

The remaining candidate consistent with ALL evidence is the **residency/hydration of the restored snapshot's anonymous pages**: the restored 12.31 GB page set is sometimes slow to traverse (page-in from the snapshot blob / host memory bandwidth at traversal time) while freshly-touched anonymous memory (the synth probe) and small DMA transfers are always fast. This is a transient, pool-level property: the same physical GPU UUIDs produced both FAST and SLOW runs minutes apart (e.g., GPU-176c31e2: A-FAST 1 671 ms and B-SLOW 8 010 ms; GPU-881cd087: B-SLOW 7 487 ms and A-SLOW 5 043 ms), and the FAST runs cluster at the end of the block — no stable host signature.

## Recommendation

**No production fix ships** — no result supports one:
- The mmap hypothesis is disproven (nothing is mmap-backed), the clone does not help, and the general DMA path is healthy. There is no code change that this experiment justifies.
- Production already overlaps the transfer behind graph/prefill work (`late` activation + early lane); the residual sampler-lane cost on slow draws (0–5.5 s here, 4.7–5.8 s in the earlier host study) is the natural tail of the pool, consistent with the host-stability report's conclusion that the tail is a transient pool property.
- If the tail must be bounded, the only evidence-backed lever remains explicit region pinning (us-east-2: never-slow but ~2.2 s median transfers; a latency-vs-tail tradeoff), unchanged by this experiment.
- Suggested follow-up to isolate the residual mechanism (diagnostic only, not shipped): correlate per-run mincore residency of the restored UNET (the existing `sample_storage_residency`/storage-registry machinery) with transfer speed, and/or re-run the quiesced-transfer A/B on slow draws.

## Files changed

- `comfymodal_runtime/unet_backing.py` — **new**: backing-diagnostics module (default off): per-storage `/proc/self/maps` classification (fixed-width column parser — a missing pathname is anonymous, never "file:inode"), anonymous-RAM clone of every UNET parameter/buffer preserving dtype/shape/strides/parameter objects + GC + re-verification, and the synthetic 2 GiB touched-anonymous H2D probe (measured, GPU tensor freed before the real transfer).
- `comfymodal_runtime/modal_app.py` — snapshot-build-time backing capture + Arm-B clone immediately before snapshot commit (`COMFYMODAL_V2_UNET_BACKING_VERIFY` / `COMFYMODAL_V2_ANON_UNET_SNAPSHOT`, both default off); evidence attached to every result; env passthrough in `_runtime_env`.
- `comfymodal_runtime/model_preload.py` — per-run `synth_h2d_probe` (default off) immediately before the real UNET transfer + per-run UNET backing classification at transfer time, emitted as a trace event.
- `tools/benchmark_v2_direct.py` — `--backing-ab` interleaved mode (A/B shadow apps, per-arm skip-first-2, 7 valid cold per arm, per-attempt app switching, artifact surfacing of `unet_backing_evidence`, `backing_ab_report.md`); `_run_one` app-identity check now env-based (per-attempt arm switching).
- `deploy_and_run_backing_ab.py` — **new**: deploy A + B shadow apps with the verified production config plus study gates; `--deploy-only`; runs `--backing-ab`.
- `V2_UNET_BACKING_AB_REPORT.md` — this report.

## Replication

```
python deploy_and_run_backing_ab.py 7 12
```

(deploys both shadow apps, then runs the interleaved study; `--deploy-only` to deploy without running. All diagnostic gates default OFF in production.)

Final commit SHA: instrumentation `73ad06b`; this report and its final
commit: see the head commit of `main` at the time of writing.
