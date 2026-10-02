# Source-I/O experiment ledger

The no-repeat ledger. Statuses: CARRY · CANDIDATE · DIAGNOSTIC ONLY · REJECTED · SUPERSEDED · UNRESOLVED.

## Locked runtime facts (gVisor, `4.19.0-gvisor`)

| mechanism | observed | status |
|---|---|---|
| `mmap(PROT_READ, MAP_PRIVATE)` | rc 0, works | CARRY |
| `madvise(MADV_WILLNEED)` | rc 0 but **functionally inert** (cold first touch 24.7 ms vs 27.0 ms advised) | REJECTED as prefetch |
| `madvise(MADV_POPULATE_READ/WRITE)` | **EINVAL (22)** — unsupported | REJECTED |
| `readahead()` | **EINVAL (22)** — unsupported | REJECTED |
| `mmap(MAP_POPULATE)` | rc 0, **does not materialize** (64 MiB window mapped in 4.8 ms) | REJECTED as population |
| `mincore()` | callable, **meaningless** — reports all pages resident before any touch | REJECTED as evidence |
| gVisor page-fault counters | **0/0 always** | REJECTED as evidence |
| what actually materializes mmap pages | **only a real access** through the mapping | CARRY |

## Source mechanisms

| experiment | topology | speed | tail effect | conclusion | status | repeat? | caveat |
|---|---|---|---|---|---|---|---|
| preadv QD4 / 64 MiB / 4 ms | 4 procs, self-service, 64 MiB, 4 ms | counted median 5.487 GB/s (n=27) | 0 ops ≥250 ms in counted regions | current proven baseline | **CARRY** | no | region-sensitive |
| M0 persistent mmap + C memcpy | 4 procs, QD4, 64 MiB, one whole-file mapping per proc | counted median 5.419 GB/s (n=32) | 9 ops ≥250, 3 ≥500, 5/32 runs | not faster than preadv pooled | **CANDIDATE** | yes, only with region matching | tails all in us-east/us-east4 where preadv has no counted runs |
| M0 as RESCUE after preadv pathology | paired dormant rescuers | — | **0 meaningful escapes in 53 ≥1 s events**; median finish 1.4 ms from original | rescue does not escape | **REJECTED as rescue** | no | proves only inability to escape an *already* sick fetch — says nothing about M0-primary origin rate |
| M0 + toucher (T1 1-block / T2 2-block) | per-reader native toucher thread ahead in lane | 3.568 / 3.717 vs T0 5.295 GB/s | toucher itself sick (T2 max 1045.5 ms); READY_AHEAD = 0 | toucher adds contention, never got ahead | **REJECTED** | no | first attempt invalid (toucher never fired) |
| M0 zero-copy / direct-consume (D0/D1/D2) | no destination buffer, native consumer reads mapping | D2 4.686 vs M0 5.621 GB/s (−16.6%) | D2 3 ops ≥250 | **memcpy is removable but removing it is not a win** | **DIAGNOSTIC ONLY** | no | D1 faster only because it reads 1 byte/64 (not a full consumer) |
| M1 inert WILLNEED | M0 + WILLNEED | expected ≈ M0 | — | semantically inert | **REJECTED** | **do not rerun as prefetch** | M0+M1 x5 closure only if needed |
| M2 exact-window mmap (cross-time) | per-block window map (+ inert MAP_POPULATE), copy, unmap | counted median 5.856 GB/s (n=33) | 8 ops ≥250, 4 ≥500, 1 ≥1000 | cross-time comparison, not conclusive | SUPERSEDED by the interleaved test | no | operation cost = map_ms + preadv_ms |
| **P vs M2, same-time interleaved** | `[P,M2,M2,P,P,M2]`, both engines in the same window, 30 counted each | **M2 6.503 vs P 5.904 GB/s (+10.1%); mean +15.8%; p10 +29%; wall 1237 vs 1363 (−9.2%)** | M2 worse mid-tail: 9 ops ≥250, 6 ≥500 vs P 4 and 1; both 0 ≥1s | **M2 is genuinely faster, and the win survives same-time interleaving and per-region stratification (wins in all 4 overlapping regions)** | **CANDIDATE — best pure-CPU throughput, not yet the tail winner** | no further runs needed | M2 carries a heavier 250–1000 ms tail; block 90 (offset 6039797760) recurs in BOTH arms |
| RTX PRO 6000 Blackwell, M2 window | same M2 engine on `rtx-pro-6000`, 15 runs | pooled all-region median **6.513 GB/s** (mean 6.491, p10 5.808, best 7.632, worst 3.442); wall median 1235 ms | 9 ops ≥250, 5 ≥500, 2 ≥1000 | cross-GPU check only | **DIAGNOSTIC ONLY** | no | only 2 of 15 runs were US (us-east, median 7.072); the rest are non-US and excluded from counted stats |
| **A WHOLE (persistent whole-file)** | one whole-file map per reader, kept alive | counted n=8 med **5.657 GB/s**, wall 1423 | **0 ops ≥250 ms — cleanest tails**; CV 0.228, spread 3.07 | cleanest tails, poor consistency | **CANDIDATE** | no | mapping creation 1.26 ms (nearly free) |
| **B SEGMENTED-PERSISTENT** | one exact map per 64 MiB window, all created up front and kept alive | counted n=**7** med **4.469 GB/s**, wall 1755; matched us-central 4.145 (worst) | 1 op ≥250 ms; CV 0.234, spread 2.54 | **DOMINATED** — never best in any matched region, and carries a **~125 s per-run start-up penalty** | **REJECTED** | no | 120 live mappings; `prep_map` only 2.15 ms, so "avoiding map cost" is not the advantage — but the ~31 GB of VMA across 4 readers costs ~125 s at container start (reproduced on Testing 4 H100 **and** Testing 5 CPU-only; source wall and cleanup are normal, so it is outside the measured phases) |
| CPU-only placement class | same engines, no `gpu=` argument | pooled median **3.323 GB/s** vs 5.5–6.5 GB/s on H100 hosts | — | quota-compatible route for pure-CPU source work | **DIAGNOSTIC ONLY** | yes, when GPU quota is exhausted | absolute numbers are **not** comparable to H100 cohorts; internal A/B/C comparisons stay valid |
| **C FRESH-WINDOW (= current M2)** | map exact window, memcpy, munmap, repeat | counted n=8 med **5.535 GB/s**, wall 1453; **best in matched us-central (5.685)** | 4 ops ≥250, 1 ≥500; **CV 0.098, spread 1.35 — most consistent by far** | **CANDIDATE — best consistency, equal-or-better throughput** | yes, if a tie-break is wanted | heavier mid-tail than A; all its ≥250 ms ops were in GCP:us-east |
| MAP_POPULATE removal | A/B/C all run without it | same-window interleaved sanity: 7.265 vs 7.293 GB/s (0.4% apart) | — | inert, confirmed again | **REMOVED from all arms** | **do not re-add** | never call it population in this runtime |
| MAP_POPULATE behaviour | — | 64 MiB window mapped in 4.8 ms | — | accepted-but-inert | **REJECTED as population** | no | **never call this actual population** |
| fio pvsync | 4 independent jobs, non-overlapping quarters, bs=64m | us-east median 2.004 GB/s (n=5) | — | corroboration only | **DIAGNOSTIC ONLY** | no | sync engine; no iodepth QD claim |
| fio mmap | same | us-east median 2.967 GB/s (n=7) | — | agrees with harness direction | **DIAGNOSTIC ONLY** | no | same |
| source-wall profiler | preallocated shared-memory telemetry | identity error 0.000000 ms | residual 42.2 ms (2.6%): pacing 27.5, ramp 13.3, drain 32.9 | wall is explained by reads/concurrency | **CARRY instrumentation** | — | — |
| current region rule | US only; singleton US regions excluded | — | — | prevents composition confounds | **CARRY** | — | non-US and singleton runs retained separately |

## Previously established (unchanged by this work)

| experiment | topology | speed | tail effect | conclusion | status | repeat? | caveat |
|---|---|---|---|---|---|---|---|
| QD1→QD2→QD4 | raw concurrency | scaled dramatically | not a tail cure | concurrency matters | SUPERSEDED numbers | no | old 30–40 GB/s not comparable to cold loader |
| QD5 / QD6 / QD7 / QD8 sustained | — | −1% / −9% / −7% / worse | no trustworthy improvement; QD8 can go pathological | QD4 optimal | REJECTED | no | QD7 "clean tail" was region-confounded |
| block-size sweeps 32/64/128/256 MiB | — | boundary-dependent | changes tail shape | no universal winner | REJECTED | no | — |
| threads → 4 independent processes | — | +10–12% median | does not eliminate multi-second stalls | CARRY | — | no | — |
| 8 processes / 4 MiB old topology | — | −25–33% | no cure | REJECTED | no | — | — |
| persistent FDs | — | removes open churn | sickness remains | CARRY for cleanliness only | no | not a cure |
| eager workers | — | removed ~3.4 s first-start serialization | tail remained | CARRY | no | — |
| pinned vs pageable destination | — | ~1% | no cure | REJECTED as tail mechanism | no | — |
| persistent registered pinned arena | — | H2D cheap | does not cure source sickness | CARRY for transport | no | out of scope here |
| private buffer → SHM split | — | added copy | localized sickness inside preadv | DIAGNOSTIC ONLY | no | not a speed optimization |
| pretouch / page-fault theory | — | no useful gain | clustered sickness remained | REJECTED | no | distinct from the native toucher tested here |
| fresh anonymous/rehome copies | — | fast after data read | you still pay the slow source read | REJECTED | no | — |
| primers / leading reads | — | small cohorts looked cleaner | failed replication | REJECTED | no | — |
| persistent-FD + static region reader | — | good healthy baseline | tails survive | CARRY baseline | no | — |
| central manager greedy allocator | — | ~13% regression | no benefit | REJECTED | no | manager bubble measured at 1.429 ms/block |
| self-service allocator | — | bubble 0.1095 ms/block | retains flexibility | CARRY | no | within 0.06 ms of coordination-free loop |
| globally interleaved allocator | — | initially slower | no balancing benefit | SUPERSEDED | no | — |
| fixed ~2 GiB static ownership | — | fastest simple preadv control | cannot react to straggler | CARRY control | no | — |
| work-stealing study | — | little opportunity | pathological reads dominated | DIAGNOSTIC ONLY | no | — |
| same-range race-N duplicates | — | no gain | no cure | REJECTED | no | — |
| same-path hedge after fixes | — | functional | photo-finish <1 ms | REJECTED as cure | no | — |
| 2×64 / 4×32 split rescue of 128 MiB | — | — | subreads co-stalled with original | REJECTED | no | — |
| old 150 ms O_DIRECT hedge | — | rescue worked | endpoint worse via lifetime bug | REJECTED unchanged | no | do not resurrect slot_busy |
| prearmed O_DIRECT spare (single) | — | healthy path preserved | did not cap tail | UNRESOLVED | only as independently paired | — |
| ROTATE3/4 resource islands | — | real rescue wins | bank exhaustion remained | containment only | no | — |
| SHAM → SPLIT/fresh resource | — | tail incidence dropped | implicated reused lifecycle | DIAGNOSTIC ONLY | no | — |
| fresh slot CUDA completion events | — | little healthy cost | strongest CLIP→UNET reduction | CARRY (integrated CUDA) | no | out of scope here |
| fresh H2D stream only | — | — | weaker | REJECTED | no | out of scope |
| R41 source→ring→dispatcher→reaper | — | not proven as throughput win | prevents source workers waiting CUDA events | CARRY structural invariant | no | — |
| direct VolumeGetFile2 transport | — | ~0.092 GB/s | avoided preadv but unusable | REJECTED | no | — |
| Volume V1 vs V2 POSIX | — | similar | no stabilization | not a speed cure | no | — |
| physical/file sharding | — | unstable bandwidth | no durable cure | REJECTED | **do not revisit** | — |
| 4 ms pacing | — | counted median 5.487 GB/s | 0 ops ≥250 ms in counted regions | CURRENT WINNER | CARRY | no | — |
| 5 ms / 6 ms pacing | — | −5.9% / −4.6% median | tails only in unique regions; no matched-region gain | REJECTED | no | — |
| 7/8 ms pacing | not run | — | — | **DO NOT RUN** | no | — |
| **mmap window 32 MiB (fresh)** | fresh window, 2 ms spacing | counted n=6 med **6.879 GB/s**, wall 1171 | 0 ops ≥250 ms; **worst CV (0.222)**; worst÷own-median 4.18× | fastest median (+32.5% vs 64 MiB) but least consistent | **CANDIDATE (throughput)** | no | 32,801 ops/TiB — 8× the operations of 256 MiB |
| **mmap window 64 MiB (fresh)** | fresh window, 4 ms spacing | counted n=6 med 5.189 GB/s, wall 1551 | 0 ops ≥250 ms; CV 0.179 | mid-pack on both axes | **CANDIDATE (baseline)** | no | no distinguishing advantage in this cohort |
| **mmap window 128 MiB (fresh)** | fresh window, 8 ms spacing | counted n=6 med 5.351 GB/s, wall 1509 | 0 ops ≥250 ms; CV 0.193 | mid | **CANDIDATE** | no | — |
| **mmap window 256 MiB (fresh)** | fresh window, 16 ms spacing | counted n=6 med 5.581 GB/s, wall 1441 | 26 ops ≥250 ms (2/6 runs) but **best CV (0.177)** and **tightest worst÷own-median (1.97×)** | most consistent, fewest operations | **CANDIDATE (consistency)** | no | the ≥250 ms count is an **absolute-threshold artefact** applied to 8× larger ops; all 26 came from ONE run (im-29, OCI:us-central) and were contiguous, not offset-specific |
| size sweep spacing rule | 32→2 ms, 64→4 ms, 128→8 ms, 256→16 ms | achieved spacing matched nominal exactly (2.0051 / 4.0270 / 8.0296 / 16.0813) | — | geometry isolation only | **NOT a pacing optimum** | pacing optimised separately | `mmap` cost is negligible (0.04–0.07 ms); memcpy dominates; unmap scales with size |
| **full geometry matrix (12 cells, n=20 each)** | {32,64,128,256} MiB × QD{4,6,8}, fresh-window, H100, 20 balanced rounds seed 20261001 | medians 5.36–6.15 GB/s — **throughput is essentially flat (~15% spread)**; best 64/QD6 6.152, then 32/QD8 6.027 | **higher QD destroys tails for windows ≥128 MiB**: 256 MiB affected-run rate 30% (QD4) → 90% (QD6) → 100% (QD8); 128 MiB 5% → 40% → 60% | **throughput does not improve with QD; only tails do (worse)** | **CARRY as the geometry reference** | no | effective concurrency scales correctly (3.9/5.8/7.6) so QD is real — the path simply cannot convert concurrency into throughput |
| matrix — best-behaved cells | 64/QD4 · 256/QD6 · 32/QD8 · 128/QD4 | 64/QD4 best CV 0.157 & MAD 0.713 & worst-run 4.095; 256/QD6 best p10 5.075 & relative tail 2.20; 32/QD8 best median 6.027 & wall 1335; 128/QD4 lowest affected 5% | — | shortlist for pacing/final validation | **CANDIDATES** | pacing phase decides | tradeoff is throughput vs variance vs tail shape — NOT decided here |
| matrix — dominated cells | 64/QD8 · 256/QD8 · 128/QD6 · 128/QD8 | no axis favours them | 64/QD8 worst run 0.216 GB/s, severity 378×; 256/QD8 100% runs affected | **REJECTED** | no | — |
| counting-rule change (region ≥3 runs) | per ARM, keep regions with ≥3 runs; drop regions with <3; **no US-only filter** | raised counted yield from 3.3% (US+singleton) to ~55% of launches | — | makes a 12-arm matrix feasible | **CARRY as the matrix counting rule** | — | applied mid-experiment to filtering only; no runs wasted |
| CARRY re-audit (mmap harness) | readers eager/alive before request timing? FD persistent per reader? | **both PRESENT** — readers block on `go` after prep and the wall starts at first memcpy (`source_race_oracle.py:7810-7812`, `8069`, `8083`, `8129-8131`); `fd = os.open(...)` once per reader at `7770`, reused in every `mmap` (`7885`) | — | nothing had to be restored | **CARRY CONFIRMED** | — | code-audited, not re-benchmarked |
| **PHASE 1 pacing 0/2/4 ms** | 64 MiB / QD4 / fresh-window, 30 balanced rounds of 3 arms (seed 20261003), 15 counted/arm | median **P0 5.592 · P2 6.179 · P4 6.287**; CV **P0 0.2171 · P2 0.3772 · P4 0.1759**; worst-run P0 2.344 · P2 2.097 · **P4 3.649** | ops ≥250 ms: **P0 11 (13% runs affected) · P2 0 · P4 0**; P2 has heavier mid-tail (p90 126.2 vs P4 67.6) | 0 ms LOSES ~10–12% median vs 2/4 ms and carries the worst tail; 2 ms shows no advantage over 4 ms here | **P4 (4 ms) remains the best-behaved; NOT a decision for Ahmed** | pacing only | max QD = 4 in every arm; achieved spacing 0.008 / 2.010 / 4.010 ms matched the configured floor exactly |
| PHASE 1 tails — BOTH definitions | (1) pooled worst/pooled med vs (2) max per-run worst/own med | P0 **43.03 / 65.01** · P2 **5.49 / 3.76** · P4 **3.61 / 2.45** | — | the two are different quantities and are never mixed in one column | **CARRY as the tail reporting rule** | — | fixes the earlier mislabeled "worst op ÷ own median" |
| **PHASE 2 deferred munmap** | 64 MiB / QD4 / 4 ms, mmap→memcpy→enqueue retire→continue, bounded in-process reaper thread (max 2/reader) | source-ready **5.650** vs fully-drained **5.642 GB/s**; **drain penalty median 2.24 ms**; queue-full **0**, max depth **1**, avg 1.000; 2376/2400 munmaps during source; **0 leaks, 0 map/unmap errors** | matched-restricted vs P4: **P4 6.331 (n=20) vs DU 5.853 (n=25) = −7.5%**, per-region deltas **mixed (+6.4% … −9.4%)** | **no net source-ready gain**; munmap is only **5.3%** of the source-path op, so the ceiling was ~5% and reaper contention offsets it | **mechanically safe but no measured benefit — do NOT carry on perf grounds** | no | region-matched on all valid runs (uncapped); overlap sufficient (5 shared regions n≥3 both) so NO extra controls added |
| historical M2 cross-check | today's P4 sync vs the old pm2 `mmap_source` cohort | historical M2 **6.439** pooled / **6.498** matched-restricted (n=49); today's P4 matched-restricted **6.331** | — | **within 1.7% → NO code regression**; differences are provider:region / placement | **CARRY as the no-regression evidence** | — | historical M2 was us-west/us-east dominated; today's cohorts drew CANADA-2/ca/asia-northeast1/europe-west9 (+ heavy `uk` in DU) |
| **FINAL CHECK 1 — MAP_SHARED vs MAP_PRIVATE** | 64 MiB / QD4 / 4 ms fresh-window, 30 balanced rounds of 2 arms (seed 20261004), 15 counted/arm | A PRIVATE med **6.224** mean 6.208 p10 5.345 worst 4.128 CV 0.1520 MAD 0.6992; B SHARED med **5.506** mean 5.423 p10 3.072 worst 2.878 CV 0.2504 MAD 0.9586 | B op tail heavier (102 vs 8 ops ≥100 ms; normalized tail (2) 21.02 vs 13.76); matched (uncapped, n≥3 both) asia-northeast1 **−12.6%**, us-west −3.6%, matched-pooled **−12.1%** | MAP_SHARED is worse on EVERY axis | **REJECTED — keep MAP_PRIVATE** | — | consistent with "only a real access materializes pages": MAP_SHARED buys no sharing benefit, adds shared-mapping bookkeeping |
| **FINAL CHECK 2 — CPU vs wall around memcpy** | instrumented baseline (private), 15 counted, fail-closed CPU clock (thread_time_ns is stubbed in gVisor and must not be trusted blind) | clock used = **thread** (`CLOCK_THREAD_CPUTIME_ID`); 1800/1800 ops had CPU data; median wall **39.799 ms**, median CPU **40.000 ms**, **median CPU fraction 0.9449** (healthy 0.9451) | aggregate CPU/wall across 4 readers **median 3.504** (min 2.83, max 3.63) ≈ ~100% of elapsed CPU on 4 cores | **the ~40 ms memcpy wall is ~92–95% CPU work, NOT waiting/materializing**; no idle window | **CARRY as the mechanism answer** | — | corroborates the earlier 97.4%-explained wall profiler; SIMD/alignment/affinity NOT run (4 cores already saturated) |
| **mmap baseline status (frozen)** | 64 MiB / QD4 / 4 ms / fresh-window / MAP_PRIVATE / persistent FD / eager workers / self-service / native memcpy / sync munmap / no POPULATE | — | — | **CANONICAL CURRENT mmap BASELINE** | **CARRY** | — | 0 ms pacing REJECTED · 2 ms NOT PREFERRED over 4 ms · deferred munmap REJECTED · MAP_SHARED REJECTED · MAP_POPULATE removed/inert |
| CARRY audit of the current mmap path | all historical CARRY items checked against the fresh-window path | 4 processes · persistent FD · eager workers · self-service · 4 ms spacing · `mmap(PROT_READ, MAP_PRIVATE)` · access-materialized pages · native memcpy · wall instrumentation · region-matched analysis | — | **nothing missing — no restore needed** | **CARRY audit complete** | — | no new broad experiment started |
| **FINAL OPT 1 — CPU AFFINITY** | 64 MiB / QD4 / 4 ms fresh-window, 30 balanced rounds of 2 arms (seed 20261005), 15 counted/arm | `sched_getaffinity`/`sched_setaffinity` **SUPPORTED**; 28 allowed logical CPUs; readers pinned 0→CPU0, 1→CPU1, 2→CPU2, 3→CPU3 (`set_ok=True`, observed `after` confirms). Median A 5.550 vs B 5.534 (**−0.3%**); matched-restricted **−1.7%** | pooled CV 0.2837→0.1170 and p10 2.613→5.122 look better, **but matched region asia-northeast1 shows B WORSE on every tail**: ops ≥100 ms 5 (0.4%) vs 20 (1.2%), ≥150 ms 0 vs 5, ≥250 ms 0 vs 2, worst 107.6 vs 270.8 | no throughput gain; the pooled variance/tail win is **region composition** (A drew europe-west2 med 3.000; B drew ca med 6.848) | **NOT CARRIED — not a clean win** | no | topology NOT readable under gVisor (`available=False`) → distinct LOGICAL CPUs only; that limitation is real |
| **FINAL OPT 2 — FIXED-VA WINDOW REPLACEMENT** | 64 MiB / QD4 / 4 ms fresh-window, 30 balanced rounds of 2 arms (seed 20261006), 15 counted/arm; reader-owned 64 MiB PROT_NONE reservation + MAP_FIXED window replacement + one final munmap | **SAFE & VERIFIED**: 1800 replacements, **0 errors**, **0 address mismatches**, 60/60 slots page-aligned, peak live mappings 1, **0/60 slots leaked after cleanup (real `/proc/self/maps` check)**, 0 worker/barrier errors, coverage exact 120/120, amp 1.0 | **explicit munmap 2.2209 → 0.0000 ms/op BUT replacement mmap 0.0596 → 2.2367 ms/op** — the cost is **RELOCATED into MAP_FIXED, not removed**; net `op_wall` 46.9 → 46.3 ms (−1.3%, noise). B pays a 3.12 ms end-of-run drain instead of per-op munmaps | fresh-window semantics **PRESERVED** (fresh exact window per block, not persistent-segmented) but **no measurable gain** | **NOT CARRIED — cost-neutral** | no | pooled wall +5.1% matched is placement, not mechanism, because `op_wall` is unchanged |
| **mmap optimization program status** | both final optimizations tested (affinity, fixed-VA) | affinity: no throughput gain + worse matched tail · fixed-VA: munmap relocated not removed | — | **PROGRAM EFFECTIVELY EXHAUSTED — FREEZE THE BASELINE** | **CARRY: freeze** | — | 64 MiB / QD4 / 4 ms / fresh-window / MAP_PRIVATE is the frozen baseline |

## Explicit no-repeat rules

1. **DO NOT** rerun `MADV_WILLNEED` as if it were real prefetch — it is functionally inert here.
2. **DO NOT** call `MAP_POPULATE` actual population in this runtime.
3. **DO NOT** use `mincore` residency claims as evidence.
4. **DO NOT** use gVisor fault counters as meaningful evidence.
5. **DO NOT** claim the M0-rescue failure means mmap-primary is equally tail-prone — those are different questions.
6. **DO NOT** repeat large M1 cohorts.
7. **DO NOT** rerun the frozen preadv cohort unless comparability genuinely breaks.
8. **DO NOT** treat pooled mmap-vs-preadv tail differences as a mechanism effect without matched regions.
9. **DO NOT** count M2's operation cost as copy-only; it is `map_ms + preadv_ms`.
10. **DO NOT** use `MAP_SHARED` — final check: −12.1% matched throughput and worse tails; keep `MAP_PRIVATE`.
11. **DO NOT** trust `time.thread_time_ns()` / `time.process_time_ns()` blindly in gVisor — they can read as a permanent zero; require a clock that advances across real CPU work.
12. **DO NOT** start SIMD / custom-copy / alignment / CPU-affinity work on the memcpy: it is already ~92–95% CPU and the 4 readers saturate 4 cores (aggregate ≈100%).
13. **DO NOT** carry CPU affinity: median throughput is unchanged (−0.3% pooled, −1.7% matched) and on the one adequately-matched region the op tail is slightly WORSE; the pooled variance/tail gain was region composition.
14. **DO NOT** expect `MAP_FIXED` window replacement to remove the munmap cost — it **relocates** it: explicit munmap 2.2209→0.0000 ms but the replacement mmap 0.0596→2.2367 ms, so `op_wall` is unchanged.
15. **DO NOT** infer a mechanism effect from pooled wall/throughput in these A/Bs — always check the matched-region op tail and the per-op cost decomposition.
