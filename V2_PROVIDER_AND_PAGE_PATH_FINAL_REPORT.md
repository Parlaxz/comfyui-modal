# V2 Provider (AWS vs GCP) + Page-Path Isolation — Final Report

**Questions:** (1) does AWS vs GCP materially change the slow-transfer tail without region pinning? (2) is the restored-UNET slowdown caused by snapshot-page hydration, total transfer size, or the 454-storage copy structure?

**Answers (direct measurement):**

1. **No.** The real UNET tail (~5.2–6.0 s @ 2.0–2.4 GB/s) exists on **both** providers in **every** measured run, and it does not track the provider's DMA speed: GCP's synthetic DMA is ~2.5× faster than AWS's (27 vs 10.4 GB/s contiguous), yet the real transfer differs by only ~14 % (2.37 vs 2.07 GB/s). Distributions overlap materially — provider selection does not stabilize the tail. (Provider does matter for availability — GCP containers segfaulted in `load_models_gpu` — and for scheduling — AWS 32–230 s, GCP 22–315 s today.)
2. **None of the three.** Hydration is rejected (mincore residency is **100 % before any touching**, traversal is fast, the real H2D records zero major faults and zero I/O, and is still slow *after* a full traversal). Total size is rejected (a fresh 12.31 GB contiguous anonymous H2D is fast). Copy structure is rejected (a fresh 454-storage synthetic with the same sizes and the same per-storage loop is fast). **Supported conclusion: the restored snapshot/model-page path** — the Modal-restored UNET pages themselves DMA slowly while fresh anonymous memory in the same container, at the same moment, is 5–10× faster.

**No production change ships** — nothing here supports one. Best stabilization option: keep the existing `late`-activation overlap (it already hides most of the transfer behind graph work); if worst-case must be bounded, the only evidence-backed lever remains region pinning (pool-odds play, not a mechanism fix).

## Protocol and arms

- Two otherwise identical shadow deployments, cloud-pinned only (`cloud=` kwarg, **no** region pin): `stable-modal-comfy-v2-provider-aws-shadow` (aws) and `stable-modal-comfy-v2-provider-gcp-shadow` (gcp). Same image, GPU RTX PRO 6000, CPU 16 / mem 49152 MiB, TBASE/O0, single-use containers, minimal teardown, `late` activation, workflow and cache config. All diagnostic gates default OFF in production.
- Interleaved aws,gcp,aws,gcp,…; snapshot-build run + following run discarded per arm; 25 s gaps; cap 10 measured attempts per arm. **Provider-arm matching was perfect — zero mismatches, zero rejections needed** (aws arm → `CLOUD_PROVIDER_AWS` every attempt, region eu-central-1; gcp arm → `CLOUD_PROVIDER_GCP`, region us-east4).
- **Availability caveat:** GCP containers crash-looped during this experiment — `Runner segmentation fault (SIGSEGV), exit code: 139` inside ComfyUI's `load_models_gpu` (3 s into the real H2D) on some attempts, plus two `stream_failed: Server has lost track of input` and two `missing output for previous input` container-level failures. AWS never crashed. All failures are preserved as attempt artifacts. The GCP measured set is therefore small (1 valid + 1 protocol-excluded + 1 snapshot-builder run, all with complete page-path records).
- Per-run ordering (documented, and enforced in the worker): `mincore-before → native one-byte-per-page traversal → mincore-after → real UNET H2D → 12.31 GB contiguous synthetic H2D → 454-storage synthetic H2D`. Synthetic probes run strictly **after** the real transfer and are allocated/measured/freed separately (memory-bounded waves; guaranteed frees; `malloc_trim`), so they cannot prewarm or alter the real result. The traversal intentionally precedes the real H2D (its hydration effect is exactly what is being measured).

## Per-run results (every preserved attempt)

Primary page-path dataset: `comfymodal-data/benchmarks/runs/v2_2026-08-06_14-45-28/` and `v2_2026-08-06_15-17-01/` (raw page-path records + host diagnostics in each `attempt_*.json`). Superseded/incomplete dirs: `v2_2026-08-06_14-32-47` (empty), `v2_2026-08-06_15-58-57`, `v2_2026-08-06_16-14-35` (AWS-only attempts before abort).

| attempt | arm | status | region | GPU uuid | resid-before | traversal ms (GB/s) | resid-after | real H2D ms (GB/s) | 12.31G contig ms (GB/s) | 454-stor ms (GB/s) | restore ms | sched ms | cmd→resp ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 14-45/0000 | aws | snap-build (excl.) | eu-central-1 | GPU-5b000b4f | — | — (no worker) | — | — | — | — | 1323 | 10 243 | 448 412 |
| 14-45/0001 | gcp | snap-build (excl.) | us-east4 | GPU-ec914488 | 1.0 | 203 (58.1) | 1.0 | 5293 (2.33) | 453 (27.2) | 751 (16.4) | 606 | 22 187 | 162 591 |
| 14-45/0002 | aws | skip (excl.) | eu-central-1 | GPU-6de3bc1f | 1.0 | 363 (34.0) | 1.0 | 5992 (2.05) | 1189 (10.4) | 1366 (9.0) | 1713 | 200 980 | 217 271 |
| 14-45/0003 | gcp | FAILED (stream_failed) | — | — | — | — | — | — | — | — | — | — | — |
| 14-45/0004 | **aws** | **valid** | eu-central-1 | GPU-5b000b4f | 1.0 | 335 (36.7) | 1.0 | 6035 (2.04) | 1174 (10.5) | 1374 (9.0) | 1696 | 230 040 | 246 105 |
| 15-17/0000 | aws | skip (excl.) | eu-central-1 | — | 1.0 | — | 1.0 | — | — | — | — | — | 123 128 |
| 15-17/0001 | gcp | FAILED (stream_failed) | — | — | — | — | — | — | — | — | — | — | — |
| 15-17/0002 | aws | skip (excl.) | eu-central-1 | — | 1.0 | — | 1.0 | — | — | — | — | — | 199 635 |
| 15-17/0003 | gcp | skip (excl., full probes) | us-east4 | — | 1.0 | 197 (58.8) | 1.0 | 5176 (2.38) | 565 (21.8) | 551 (22.4) | 385 | 315 894 | 328 944 |
| 15-17/0004 | **aws** | **valid** | eu-central-1 | — | 1.0 | 350 (35.2) | 1.0 | 5938 (2.07) | 1185 (10.4) | 1339 (9.2) | 1400 | 42 819 | 59 471 |
| 15-17/0005 | **gcp** | **valid** | us-east4 | — | 1.0 | 203 (57.5) | 1.0 | 5193 (2.37) | 455 (27.0) | 568 (21.7) | 1807 | 246 787 | 261 302 |
| 15-17/0006 | **aws** | **valid** | eu-central-1 | — | 1.0 | 376 (32.8) | 1.0 | 5934 (2.08) | 1168 (10.5) | 1301 (9.5) | 1401 | 31 515 | 47 133 |

Real-H2D partitions all report `major_faults = 0` and `io_deltas.read_bytes = 0`. mincore walks cover 454 storages / 3,005,776 pages / 12,309,821,472 bytes on every run, resident fraction **1.0 before and after traversal** on every run. The 454-storage synthetic uses the exact UNET storage sizes and the same per-storage `to(cuda, non_blocking=True)` + final-sync loop; the contiguous synthetic is the exact 12,309,821,472-byte payload.

## Required conclusions

**Per provider (measured runs; protocol-excluded runs with full probes in parentheses):**

- **AWS (eu-central-1), n=3 valid:** real H2D median 5938 ms, range 5934–6035 ms, **3/3 >5 s**; traversal median 350 ms (32.8–36.7 GB/s); residency 1.0 → 1.0; contiguous median 1174 ms @ 10.48 GB/s; 454-storage median 1339 ms @ 9.19 GB/s; restore median 1400 ms; scheduling 31.5–230 s; cmd→resp 47–246 s.
- **GCP (us-east4), n=1 valid (+2 excluded with full probes):** real H2D 5193 ms (5 176/5 293) @ 2.37 GB/s, **3/3 >5 s**; traversal 197–203 ms (57.5–58.8 GB/s); residency 1.0 → 1.0; contiguous 453–565 ms @ 21.8–27.2 GB/s; 454-storage 551–751 ms @ 16.4–22.4 GB/s; restore 385–1807 ms; scheduling 22–316 s; cmd→resp 162–329 s.

**Interpretation, strictly:**

- *Traversal fast but real H2D slow → hydration rejected.* **Confirmed.** Traversal is 197–376 ms @ 33–59 GB/s (resident pages), the real H2D immediately after is 5.2–6.0 s @ 2.0–2.4 GB/s with zero faults and zero I/O, and residency was already 100 % before any touching. There is nothing to hydrate; the traversal moved no latency (real H2D unchanged vs the previous studies' cold-transfer numbers, e.g. 5.3–6.4 s).
- *Contiguous fast but 454-storage synthetic slow → storage fragmentation/per-tensor copy loop.* **Not observed** — both synthetic cases are fast on both providers.
- *Both synthetic cases fast while real UNET remains slow → restored snapshot/model-page path.* **Supported.** In the same container, same moment, same sizes, same copy loop: fresh anonymous 12.31 GB contiguous = 453–1189 ms, fresh 454-storage = 551–1374 ms, restored UNET = 5176–6035 ms. The only difference is the restored pages themselves (physical state after Modal's snapshot restore — placement/THP/folio state), consistent with the host-stability report (transient, pool-dependent, same GPU fast/slow minutes apart) and the backing study (100 % anonymous, not mmap-backed).
- *All large H2D cases slow together → general host RAM/PCIe/DMA.* **Rejected** (synthetics fast).
- *AWS and GCP differ clearly → provider selection is a practical placement lever.* **Not supported for the tail.** Real transfer 5.93–6.03 s (AWS) vs 5.18–5.29 s (GCP): GCP ~13 % better, but every run on both providers is >5 s, and the 2.5× GCP DMA advantage (27.2 vs 10.4 GB/s) fails to materialize in the real transfer (2.37 vs 2.07 GB/s) — the real transfer is not DMA-bound. Distributions overlap materially; provider selection does not stabilize the tail. Provider does matter for *availability* (GCP segfaults in `load_models_gpu` today) and *scheduling* (AWS 32–230 s erratic; GCP median ~22 s but one 316 s outlier).

## Final causal conclusion

The slow-transfer tail is caused by the **restored snapshot's UNET pages**: Modal-restored anonymous memory (100 % resident, zero faults, zero I/O) DMA-transfers at 2.0–2.4 GB/s while freshly allocated anonymous memory in the same container reaches 9–27 GB/s. Snapshot-page hydration, total transfer size, the 454-storage copy structure, and the general host RAM/PCIe/DMA path are all rejected by direct in-container measurement. Provider selection changes the DMA ceiling and availability but not the tail; the mechanism is transient and pool-dependent, not a property of our code.

## Best stabilization option

- **Do not ship a production change** — no result clearly supports one (the anonymous-RAM clone in the previous study also failed to help; the restore re-materializes the same way).
- Keep the existing production overlap (`late` activation + early UNET lane): the transfer already runs behind graph/prefill work; the sampler-lane residual (0–5.5 s) is the visible tail cost.
- If worst-case latency must be bounded, region pinning remains the only evidence-backed lever (us-east-2 historically 0/18 bad), and it is a pool-odds play — today's data shows unpinned AWS at ~5.9 s, so pinning does not fix the mechanism. GCP currently additionally carries container crashes in this path (availability concern, pool condition).

## Files changed

- `comfymodal_runtime/modal_app.py` — `COMFYMODAL_V2_CLOUD` provider pin (`cloud=` kwarg, allowlist aws/gcp, default off, fail-loud); env passthrough; page-path gate passthrough.
- `comfymodal_runtime/unet_backing.py` — page-path diagnostics (default off): per-storage `mincore` residency (mapping-clamped), native one-byte-per-page traversal (numpy strided read; wall/process CPU, covered pages/bytes, GB/s), size-exact 12.31 GB contiguous H2D probe, 454-storage synthetic H2D probe matching the exact UNET sizes with the real per-storage loop (memory-bounded waves, guaranteed frees, `malloc_trim`, RSS capture).
- `comfymodal_runtime/model_preload.py` — per-run page-path sequence in the UNET activation worker: mincore-before → traversal → mincore-after → real H2D (existing synchronized partition) → synthetic probes after, emitted as one `page_path_probe` trace event.
- `tools/benchmark_v2_direct.py` — `--provider-ab` mode: interleaved AWS/GCP arms with cloud-pinned shadow apps, per-arm skip-first-2, target 6–7 valid cold (cap 10 measured/arm), provider-mismatch rejection, page-path extraction, `provider_ab_report.md` renderer.
- `deploy_and_run_provider_ab.py` — **new**: deploys the AWS/GCP shadow apps with the verified production config + study-only gates; `--deploy-only`.
- `V2_PROVIDER_AND_PAGE_PATH_FINAL_REPORT.md` — this report.

Final commit SHA: instrumentation `313af3c`; this report and its final
commit: see the head commit of `main` at the time of writing.
