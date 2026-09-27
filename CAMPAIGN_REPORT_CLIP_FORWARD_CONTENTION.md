# CLIP-forward contention campaign — full data report

**Repo:** `ComfyUI/custom_nodes/comfyui-modal` · **Branch:** `TESTING2`
**HEAD:** `eebea831537e45204144ff9ec6078e84bea5217a` (`fix: apply Golden sampler GC suppression to parallel mode`)
**Prior HEAD at campaign start:** `80b2e5cfe86d826086740ccc59a93a66a29bb25f`
**Canonical output SHA (all runs):** `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`
**Platform:** Modal serverless · Testing 6 / `ws_175a616152c5` · RTX PRO 6000 Blackwell · 4 CPU / 16 GiB · CPU snapshot · `min_containers=0` · scaledown 4 · single-use · CUDA 13 · true-QD2 · baked Sage · LIGHT telemetry · deep profiler OFF
**Status:** all experiment code reverted; only the sampler-parity prerequisite commit remains. 59 `EXPERIMENT_EVIDENCE_*.md` retained at repo root.

Contents: 1) sampler prerequisite · 2) full-warm J1 · 3) bounded 2 GiB · 4) Phase 0 · 5) ladder harness + fixes · 6) ladder results · 7) cgroup findings · 8) verdict · 9) process notes · Appendix A artifact index · Appendix B per-run trace table.

---

## 1. Prerequisite: sampler GC-suppression parity (COMMITTED, kept)

**Bug:** request-scoped RES4LYF GC suppression gated on `session.golden_mode == "serial"`; Parallel requests (`golden_mode="parallel"`) skipped with `skip_reason="golden_mode_not_serial"`, sampling at the old ~5.445 s baseline while Serial held ~4.62–4.65 s.
**Fix (already in tree at `comfymodal_runtime/golden_serial.py:12844-12855`, diff empty):** `golden_mode in ("serial", "parallel")`, skip wording `golden_mode_unsupported`. Implementation untouched: module-local GC proxy (lines 572–584), overlap guard (605–615), `intercepted_collect_count` (674), mandatory `finally` restoration (659–683). No RES4LYF changes.
**Commit `eebea83` (test-only, 4+/2-):** parametrized `test_golden_sampling_wraps_only_the_direct_sampler_closure` over `["serial","parallel"]`, asserting `status=="applied"`, `intercepted_collect_count==1`, `restoration_state=="restored"`, original sampler-module GC binding restored (`active.gc is gc`).
**Validation:** `python tools/test_perf.py --fast -- tests/test_golden_res4lyf_gc_suppression.py tests/test_golden_parallel_foundation.py` → **22 passed**. Post-campaign rerun: **22 passed in 4.75 s**.
**Sampler behavior in every remote run of this campaign:** status=applied, count=1, restored; walls 4.5–4.9 s both arms (example remote record: `{"status":"applied","module_name":"/root/comfy/ComfyUI/custom_nodes/RES4LYF.beta.samplers","intercepted_collect_count":1,"suppression_wall_ms":4569.3249,"restoration_state":"restored","restoration_error":null}`).

---

## 2. Experiment 1 — full-file J1 page-cache warm (REJECTED, reverted)

**Design:** one daemon thread, 8 MiB reused `bytearray`, `open(path,'rb',buffering=0)+readinto`, discard, `POSIX_FADV_SEQUENTIAL`, stop-checked per chunk; no hash/tensors/pinned/CUDA; start after `golden_clip_load`, stop+join in `finally` around `golden_clip_forward`, then the unchanged `await golden_unet_load(session)` (`golden_parallel.py:81-85`). Headroom cap `min(file, cgroup_limit−RSS−2GiB−512MiB)`. Flag `COMFYMODAL_V2_GOLDEN_UNET_PAGECACHE_FORWARD_WARM` (default OFF), registered in `config_authority.py` + `modal_app.py` class-env + `flag_registry.toml`. LIGHT boundary telemetry only.
**Deploys:** `batch-j1-warm-control` fp `3523c545…f840b3` / `batch-j1-warm-candidate` fp `1f3231f7…493c05f7`; generations `154e8260…` / `899ef8b2…` (6025 files; differ only because the profile overlay is published content); both source-probe PASS/MATCH, `skip_exact` non-destructive; resolved-env diff over 146 keys = flag only.
**Cohort:** 3 interleaved pairs A1B1/B2A2/A3B3 + 2 smokes, all ELIGIBLE true-cold, zero captures, exact SHA, sampler applied/1/restored throughout. `--acknowledge-volume-drift` used (own two generations on shared Volume; receipts bound).

### 2.1 Per-run traces (from `artifacts/phase_p1_parallel_golden_v1/cohort_*_*/attempt_0.json`)

| run | req | restore | clip_load | clip_fwd | unet_load | sampler |
|---|---|---|---|---|---|---|
| A-smoke | `6a5cafef` | 197881.5* | 3010.5 | 1756.9 | 5003.4 | 4964.4 |
| B-smoke | `56e6aa0` | 2474.1 | 1583.2 | **5153.9** | **636.4** | 4765.8 |
| A1 | `f499053c` | 1969.4 | 1704.8 | 1415.7 | 1960.4 | 4628.9 |
| B1 | `836a7a1b` | 1963.8 | 1910.8 | **2823.8** | **664.1** | 4603.2 |
| B2 | `f70997fa` | 1651.2 | 1736.7 | **2729.9** | **594.7** | 4598.0 |
| A2 | `7986b994` | 1600.8 | 1572.2 | 1422.0 | 1699.7 | 4594.2 |
| A3 | `304a94c1` | 1600.8 | 1472.2 | 1487.4 | 2167.2 | 4666.6 |
| B3 | `2680f88e` | 1003.6 | 1427.0 | **5520.1** | **664.4** | 4612.2 |

\* A-smoke restore absorbed a one-time ~197 s snapshot path effect (smokes never count).
Pair ΔFRR (B−A): P1 **+260.0**, P2 **+356.9**, P3 **+2437.7** (mean +1018.2, median +356.9; no P90 from n=3). CLIP distributions fully separated (A 1416–1487 vs B 2730–5520). Reconciliation residuals ≤58 ms: `Δ ≈ (B_clip−A_clip) − (A_unet−B_unet)`.
**Representative warmer payload (B1, `golden_unet_pagecache_warm` event):** `thread_count=1, chunk=8MiB, bytes_read=12309866400/12309866400 (fraction 1.0, 1468 reads), read_wall=2567.0ms @ 4.795 GB/s, stop=completed, overlap=2823.8ms, join=0.023ms, rss 5088960512→5088960512, cgroup 3872661504→4197781504 (+325MB), cuda=0, h2d=0`. Full payloads §7.
**Gate:** (a) bytes PASS · (b) UNET −1.1–1.5 s PASS · (c) CLIP regression FAIL (+1.3–4.0 s) · (d) sampler PASS · (e) E2E FAIL (3/3 unfavorable) → **REJECT**. Cause: 12.3 GB concurrent warm throttles forward (+2.25 s mean) more than the UNET saving (−1.30 s mean); only 45–74% of warm wall converts. Reverted (no commit). Manifests `.v2ctl/runs/run_20260910-{181010,182020,183910,184947,185435,185739,190114,190448}_*.json`; raw `artifacts/.../cohort_2026-09-{10_23-*,11_00-01-54_41d8e9}/attempt_0.json`; requests `6a5cafef/56e6aa0/f499053c/836a7a1b/f70997fa/7986b994/304a94c1/2680f88e`.

---

## 3. Experiment 2 — bounded 2 GiB budget (STOPPED at 2 GiB, reverted)

**Added design:** byte budget `COMFYMODAL_V2_GOLDEN_UNET_PAGECACHE_WARM_BUDGET_MB` (2048/4096/6144, default 2048), `stop_reason=budget_reached`, prompt thread exit. **Demand-order recon** (`golden_serial.py:12463` → `read_file_qd_gpu` → QD arms; header `[0,8)`+`[8,8+hlen)` first, then contiguous forward blocks from `data_start`, QD-concurrent): sequential-from-zero covers header + earliest data → demand-aligned where practical. No footer reads exist.
**Deploys:** `batch-j1-budget-control` fp `47154623…` (gen `2b4ed66b`) / `batch-j1-budget-2gib` fp `5e0fad99…` (gen `1a0a4167`), both PASS/MATCH; resolved-env diff (147 keys) = warm flag only (budget key 2048→2048 inert when OFF).
**Cohort:** A1B1/B2A2/A3B3 + 2 smokes, 8/8 ELIGIBLE, zero captures/DNFs, exact SHA throughout.

### 3.1 Per-run traces

| run | req | restore | clip_load | clip_fwd | unet_load | sampler | warm wall/rate/stop |
|---|---|---|---|---|---|---|---|
| A-smoke | `629cb6e2` | 197881.5* | 3010.5 | 1756.9 | 5003.4 | 4964.4 | — (inert ✓) |
| B-smoke | `a7bfaad7` | 2474.1 | 1583.2 | 1894.1 | 1553.4 | 4765.8 | 472ms / 4.55 / budget_reached |
| A1 | `2315858c` | 1969.4 | 1519.8 | 1544.7 | 2180.1 | 4769.6 | — |
| B1 | `176243d1` | 1063.8 | 1483.7 | 1869.1 | 1568.2 | 4766.2 | 542ms / 3.96 / budget_reached |
| B2 | `8e01e287` | 958.5 | 1935.9 | 2001.5 | 1574.7 | 4694.0 | 703ms / 3.06 / budget_reached |
| A2† | `dc1355b1` | 1651.2 | **8336.3** | 1542.8 | **7100.8** | 4776.1 | — (control-side storage outlier, no warming) |
| A3 | `d78758e1` | 1600.8 | 1343.2 | 1282.5 | 1540.6 | 4623.1 | — |
| B3† | `40639b6c` | 1003.6 | **6700.4** | **3005.8** | 1439.3 | 4723.2 | 1621ms / 1.33 / budget_reached |

† retained valid outliers. Pair deltas (B−A): P1 Δclip +324.4, Δunet −611.9, net **+287.5**, ΔFRR −365.1 · P2 Δclip +458.7 (A2 outlier), net outlier-driven · P3 Δclip **+1723.3**, Δunet −101.4, net **−1621.9**, ΔFRR **+7160.0**. Median Δclip **+458.7** (B slower all 3 pairs). H2D bytes identical 12309817472, read-count 370 every run (loader unchanged); joins 6–8 ms before UNET start; 0 CUDA/H2D during forward.
**Representative payload (B1):** `bytes_read=2147483648 (fraction 0.174452, 256 reads), read_wall=541.996ms @ 3.962 GB/s, stop=budget_reached, overlap=546.271ms, join=0.024ms, rss 3948240896→4671885312 (+724MB), cgroup 3874734080→4454223872 (+579MB), cgroup_limit=MAX(2^63−1, fallback note), cuda=0, h2d=0`. Full payloads §7.
**Verdict: REGRESSED-leaning → STOP whole budget line** (2 GiB already materially slows CLIP: P3 net −1.6 s; median net +287 ms fragile single-clean-pair evidence). No 4/6 GiB. Reverted. Manifests `.v2ctl/runs/run_20260910-{201605,201744,201852,202013,202123,202501}_*.json`; cohorts `01-06-23_3cd678 … 01-21-59_9234f9`.

---

## 4. Phase 0 — retrospective mining (killer question UNANSWERABLE, verified)

**Question:** does a 2 GiB Volume read grow cgroup file memory ~2 GiB and push `current` toward the 16 GiB limit (RSS historically ~11–12 GiB)?
**Finding:** unanswerable from surviving artifacts. `.v2ctl/runs/*.json` and `artifacts/*/attempt_0.json` for the J1 cohorts are absent locally (gitignored, never committed); 55 evidence markdowns embed deployment identity + gate checklists only. Verified by 5 direct probes: needle search for `2147483648`/`budget_reached`/`rss_start`/`join_wall_ms` (zero hits); `golden_unet_pagecache_warm`×8/file = checklist mentions; sole `stop_reason` hit = unrelated `unet_prefetch_stop_reason`; `cgroup_current` hits = local restore-probe snapshots (~7.4 GiB), not remote readings.
**Salvaged dose-response (lane-reported, weak provenance):** 3.96 GB/s→+324 ms · 3.06→+459 · ~2.4→~+3500 · 1.33→+1723 (inverse rate-vs-tax, suggestive only).
**Partial retrospective answer (§7 data recovered later):** container cgroup grew only **+230 MB for 12.3 GB** and **+579 MB for 2 GiB** reads, with `cgroup_limit=MAX` (no visible limit; RSS 3.9–5.1 GiB at prewarm time, well below the historical 11–12 GiB full-request figure — different measurement points). Page cache is not visibly charged to the container cgroup view, or is reclaimed as fast as it fills.

---

## 5. Ladder harness (built, fixed 3×, then reverted)

**Module (reverted):** `comfymodal_runtime/golden_diag_traffic.py` (~1077 lines) + hook in `golden_parallel.py` (+19/−2; later `golden_serial.py` +19/−2) + 4 DIAG env keys (`ARM` OFF/N0/M1/M2/F1/V1/V2, `BUDGET_MB` 2048, `RATE_MBPS` 3072, `PRECONDITION` bool) registered in authority + class-env + flag registry. Tests reached 35 FAST_UNIT green.
**Arms:** N0 sleep-thread null · M1 small-ring (2×32 MiB) paced anon memcpy, 2 GiB aggregate @ ~3.072 GB/s nominal · M2 +2 GiB touched anon held through forward, zero traffic · F1 2 GiB container-local file, precondition-cached identically both sides · V1 full Volume pre-read (hot-confirmation rate) + reread · V2 cold Volume 2 GiB (reproducer). Bracket: start post-clip-load → stop+join pre-UNET-load, `try/finally`, guarded `recorder.event`. OFF → `maybe_bracket=None`, byte-identical executors (proven by order-preservation tests).
**Pairing matrix:** control `ARM=OFF+PRECONDITION=1` (F1/V1 preconditions, never M2 hold/traffic); M2 treatment `ARM=M2+PRECONDITION=1` (hold lives in precondition — deploying M2 with PRECONDITION=0 was caught pre-deploy and ruled out); V2 both sides `PRECONDITION=0` (cold).
**Fix chronology:** (i) bundles died in single-use containers → full payload via recorder events (`golden_diag_{traffic,cgroup,forensics,meta}`, ~3.5 KB total, no size cap on path, proven in `attempt_0.json → golden_telemetry.events[]`); (ii) harness only hooked parallel while a lane ran `golden_p1` serial → mirrored bracket into `golden_serial_execute` with inertness proof; (iii) V1/V2 `volume_path` unresolved (resolver missed `diffusion_models/`) → mirror restore's `folder_paths` resolution + candidates, record `resolved_by`; cgroup flat-path → v1-subdir fallback chain (`cgroup_path_style`); forensics → telemetry fallback (`forensics_source`) without touching executors.
**Serial-profile incident:** one N0 smoke ran `golden_p1`/serial (`diag:null`, clip_fwd 1610.3) — excluded from all contrasts.

---

## 6. Ladder results (attempt 3 + V1/V2/32GiB; all `golden_p1_parallel`, ELIGIBLE, exact SHA)

Pair medians (treatment−control), control noise ~300 ms: **N0 −137.8** (2 pairs) · **M1 +114.7** (3 pairs; achieved 3.214–3.220 GB/s vs 3.072 nominal; elapsed 0.667 s) · **M2 −66.9** (2; `release.bytes=2147483648` both runs) · **F1 −41.2** (2; reread 15.9–16.7 GB/s = resident both sides) · **V1 +131–190** (smoke +66.2, P1 +190.2, P2 +131.3; reread 9.1–10.7 GB/s) · **V2-16GiB +233.9 clean** (+477.4 region-confounded; cold 4.0–5.1 GB/s) · **V2-32GiB +443.6/+718.1 same-region** (median +581; cold 2.8–3.4 GB/s east1).
Apps (all PASS/MATCH): `batch-diag-{cold-idle,n0,m1,m2,f1ctl,f1,v1ctl,v1,v2}` 16 GiB + `batch-diag-{cold-idle-32g,v2-32g}` 32 GiB (`MEMORY_MB/REQUEST=32768` via temp profile overlay; placement caveat recorded; all V2-32 pairs same-region us-east1). Sampler 4547–4947 ms everywhere; joins confirmed; 0 CUDA/H2D in arms by construction.
**Cgroup/forensics legs:** all files `available:false` (v1 detected; usage/peak/stat/pressure unreadable container-side) → anon/file/fault/pressure deltas null everywhere; forensics `forensics_source=telemetry-fallback`, `gpu_elapsed=null` (never read as contention). Forward-window `memory.usage_in_bytes` delta ≈ +550–580 MB on both arms (CLIP H2D footprint, not traffic-driven).
**Step-up: none in N0→F1; lands at cold Volume read (V2). 32 GiB does not attenuate → against capacity/reclaim, toward per-cold-byte backend cost.**

---

## 7. Cgroup/memory evidence (only surviving quantitative leg)

- Full-warm B1: `rss 5088960512→5088960512` (flat), `cgroup 3872661504→4197781504` (**+325 MB for 12.31 GB read**), limit MAX, `cgroup_headroom_clamp`.
- Full-warm B-smoke: cgroup +230 MB for 12.31 GB @ 2.524 GB/s. B3: cgroup +~8.6 MB for 12.31 GB @ 6.085 GB/s.
- 2GiB B1: `rss 3948240896→4671885312` (**+724 MB**), `cgroup 3874734080→4454223872` (**+579 MB for 2.00 GB**), limit MAX (`9223372036854775807:rss_observed`).
- 2GiB B3 (slow storage): same +579 MB cgroup growth @ 1.325 GB/s.
- Reading: container cgroup view does not accumulate page cache 1:1 with bytes read (host-level charging or immediate reclaim); no limit pressure visible in-container. Does not exonerate or confirm eviction effects — stat/pressure stayed dark.

---

## 8. Verdict

**Contention source: cold bytes traversing the Volume backend during forward** — remote fetch + per-byte FUSE/userspace-filesystem host cost (daemon wakeups, copies, CPU/DRAM bandwidth taken from forward orchestration). Exonerated: thread scheduling (N0), host DRAM bandwidth (M1), resident capacity/reclaim (M2 + 32 GiB non-attenuation), hot page-cache reread (F1), GPU contention (no evidence), CPU saturation (prior metrics), QD2/H2D/sampler (held out). Competitive hypothesis killed: 2 GiB cap did not remove the tax (same shape as full-warm); hot reread costs only ~⅓–½ of cold. **Warming concurrent with forward is non-viable in this shape on 4 CPU / 16 GiB.** Untested: paced-trickle rates, idle-window warming outside forward, QD-integrated prefetch. Caveats: n=2–3 pairs/arm, ~300 ms control noise, one region-confounded V2 pair (flagged, same-sign), foreign-lane concurrency nearby (serial discipline kept).

---

## 9. Process notes

- Parallel-runs request declined (skill never-list; would confound paired deltas with backend load). Mid-flight parallel-deploys declined (shared-file overlay races; deploys ~10% of lane time).
- Two stopped-then-fixed lanes: bundle durability (fix: recorder events, proven) and serial-executor gap (fix: mirrored bracket + profile gate). One lane ran the wrong profile (`golden_p1`); its smoke excluded.
- Durability lesson now encoded: measurement lanes must persist run manifests to committable paths; Phase 0 failed on process grounds as much as telemetry grounds.
- Delegation: 16 specialist lanes (explorer/fixer); orchestrator acted directly only for verification reads and this report.

## Appendix A — artifact index

- Sampler commit: `eebea831537e45204144ff9ec6078e84bea5217a` (test-only).
- Full-warm manifests: `.v2ctl/runs/run_20260910-{181010,182020,183910,184947,185435,185739,190114,190448}_*.json`; deploys `.v2ctl/deployments/deploy_20260910-{174145_3523c545,175048_1f3231f7}.json`; raw `artifacts/phase_p1_parallel_golden_v1/cohort_2026-09-{10_23-*,11_00-01-54_41d8e9}/`.
- 2GiB manifests: `.v2ctl/runs/run_20260910-{201605,201744,201852,202013,202123,202501}_*.json`; cohorts `.../cohort_2026-09-11_01-{06-23_3cd678 … 01-21-59_9234f9}/`.
- Ladder cohorts: `.../cohort_2026-09-11_{02-23-01_48a92b,02-43-50_77233f(serial-excluded),03-07-55_1c3dd7 … 03-59-10_9a45b8,04-24-45_bba3e1 … 05-25-26_0824de}/` (60 cohort dirs local).
- Evidence: 59 `EXPERIMENT_EVIDENCE_*.md` at root (8 full-warm J1 + 8 budget + ~25 ladder + remainder prior).
- Request IDs: full-warm `6a5cafef/56e6aa0/f499053c/836a7a1b/f70997fa/7986b994/304a94c1/2680f88e`; 2GiB `629cb6e2/a7bfaad7/2315858c/176243d1/8e01e287/dc1355b1/d78758e1/40639b6c`; ladder §6 cohorts.
- Fingerprints: control `3523c545`/candidate `1f3231f7` (J1); `47154623`/`5e0fad99` (budget); diag `cd2313f6/ef330060/7dfdd11a/bfeeeef6/b34a61b7/f7cf3b6e/a9e95547/c5b1f551/b8badeb2` + 32g `e0271d48/93b72d32`; generations `154e8260/899ef8b2` (J1), `2b4ed66b/1a0a4167` (budget).

## Appendix B — per-run trace table (condensed from local `attempt_0.json`)

Format: cohort | req | mode | restore/clip_load/clip_fwd/unet/sampler ms | GC | arm payload.
Full-warm: `23-06-02` 6a5cafef A: 4.8/1684.8/1605.3/2079.3/4664.2 · `23-10-57` 56e6aa0 B: 3.5/2582.8/5153.9/636.4/4634.5 (12.31GB, 4876ms@2.524, completed, cgroup+230MB) · `23-37-36` f499053c A: 4.3/1704.8/1415.7/1960.4/4628.9 · `23-39-52` 836a7a1b B: 4.7/1910.8/2823.8/664.1/4603.2 (12.31GB, 2567ms@4.795, cgroup+325MB) · `23-50-27` f70997fa B: 4.4/1736.7/2729.9/594.7/4598.0 (12.31GB, 2466ms@4.991) · `23-55-15` 7986b994 A: 4.6/1572.2/1422.0/1699.7/4594.2 · `23-58-26` 304a94c1 A: 4.3/1472.2/1487.4/2167.2/4666.6 · `00-01-54` 2680f88e B: 4.4/1427.0/5520.1/664.4/4612.2 (12.31GB, 2023ms@6.085, cgroup+8.6MB). GC applied/1/restored all; `23-21-55_75ef88` = retained DNF dir (local poller timeout, no artifact).
2GiB: `01-06-23` 629cb6e2 A: 4.5/3010.5/1756.9/5003.4/4855.0 · `01-13-14` a7bfaad7 B: 4.9/1583.2/1894.1/1553.4/4652.9 (2GiB, 472ms@4.547, budget_reached, rss+724MB, cgroup+579MB) · `01-15-30` 2315858c A: 4.3/1519.8/1544.7/2180.1/4661.4 · `01-17-11` 176243d1 B: 4.8/1483.7/1869.1/1568.2/4657.0 (542ms@3.962) · `01-18-19` 8e01e287 B: 5.1/1935.9/2001.5/1574.7/4577.5 (703ms@3.055) · `01-19-27` dc1355b1 A: 4.6/8336.3/1542.8/7100.8/4667.0 · `01-20-47` d78758e1 A: 4.4/1343.2/1282.5/1540.6/4517.6 · `01-21-59` 40639b6c B: 4.4/6700.4/3005.8/1439.3/4613.5 (1621ms@1.325). GC applied/1/restored all.
Ladder N0 (`03-07-55` ea8d33c8 N0 smoke 4.3/2780.2/1552.5/3723.7/4603.6; `03-30-15` 43327f0d9a7e N0-A1 4.6/1757.9/1362.9/2021.2/4568.9; `03-31-26` 62cdbe6b3896 C-B1 4.7/1590.4/1613.9/1961.3/4640.1; `03-32-33` f3267348fcfa C-B2 5.1/1586.1/1402.3/2023.3/4712.0; `03-33-38` 835a5f190523 N0-A2 4.6/3029.1/1377.9/1692.4/4606.8) · M1 (`03-34-48` 2133eb862fa0 smoke 4.4/2557.4/1602.2/3317.8/4946.9, 2GiB@3.218GB/s; `03-36-12` 80d33a6b415e A1 6.3/1614.5/1422.7/1841.7/4665.8 @3.220; `03-37-18` 3c99e256acec C-B1 3.6/1623.6/1308.0/2028.9/4610.0; `03-38-23` 42baa9419579 C-B2 4.8/1577.0/1398.7/2066.5/4585.8; `03-39-28` 356af136aeca A2 3.8/1642.4/1358.2/1949.1/4547.2 @3.220; `03-40-34` d70692ef09da A3 4.5/1752.6/1500.1/2210.2/4618.1 @3.213; `03-41-40` 877b9876c36e C-B3 4.5/1652.2/1364.6/1855.8/4609.5) · M2 (`03-42-46` 4552c484d502 smoke 3.9/2593.6/1597.1/3174.6/4607.9 released 2GiB; `03-44-05` 676abc5103d3 A1 4.5/1598.0/1418.4/5527.4/4606.6; `03-45-15` 9227de4ee53c C-B1 4.4/1761.5/1487.4/1668.0/4621.7; `03-46-23` baadf1403306 C-B2 4.8/1795.0/1442.1/2189.4/4606.5; `03-47-33` e88b55aba1cf A2 5.0/1383.1/1377.3/2138.1/4634.0) · F1 (`03-49-34` 074324a49d63 smoke 4.3/1440.2/1557.4/2141.9/4601.8 @16.66GB/s; `03-50-41` 522943afe2eb A1 3.6/1561.5/1503.5/2129.4/4599.4; `03-51-51` f6d6b1 C-B1; `03-52-58` c46ad1 C-B2; `03-54-05` 1ecc37 A2; medians A 1459.7–1503.5 / C 1470.8–1574.8) · V1 (`03-55-22` 0bb001 smoke err/0B pre-fix; `04-24-45` bba3e1 ctl-smoke 1612.50; `04-27-01` 3c81e3 tx-smoke 1678.74 @10.7GB/s; `04-28-45` 8901ac A1 1410.87; `04-30-10` e8ab29 B1 1601.03; `04-31-54` 545aa7 B2 1554.10; `04-33-36` 6bf844 A2 1422.85) · V2-16 (`04-44-46` 068745 smoke 2121.35; `04-46-27` a65a0f A1 1493.17; `04-48-08` fab055 B1 1727.11 @4–5GB/s; `04-49-47` 1ff1bf B2 1856.29; `04-51-27` 774e72 A2 1378.91 west1) · V2-32 (`05-14-04` f099b6 smoke 3230.15 west1; `05-20-06` 893b11 A1 1502.61; `05-21-51` 89c9cd B1 1946.20; `05-23-28` b093c7 B2 2158.46; `05-25-26` 0824de A2 1440.39; all east1 except smoke; @2.8–3.4GB/s). GC applied/1/restored on all 60; SHA exact on all 60; diag 4-event sets on all armed runs; cgroup `available:false` throughout ladder (v1); forensics `telemetry-fallback`, `gpu_elapsed=null`.
Full per-cohort JSON: `artifacts/phase_p1_parallel_golden_v1/<cohort>/attempt_0.json` (+ serial `02-43-50_77233f` excluded). Full warmer payloads: §2.1/§3.1 exemplars + attempt files above.
