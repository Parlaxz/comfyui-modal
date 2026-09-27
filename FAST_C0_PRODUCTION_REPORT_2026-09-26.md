# FAST C0 Production Report — 2026-09-26

Golden Parallel loader repair, `production-004` freeze, Modal-log Gantt,
source-throughput investigation (Stages A–E), and snapshot/restore minimization.

Branch: TESTING2. App: `batch-fastc0-sep26`. Profile:
`golden_p1_parallel_m2clip_h100`. Method: `run_golden_parallel_stream`.
CPU=12, GPU=H100, mem=24576 MiB. Expected output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`.

---

## 1. `production-004` freeze

### 1.1 What was repaired (and why)

The Sep-26 C0/M2 integrations had diverted the production path into a
standalone M2 execution arm: `GoldenModelTransport` ran pure M2 persistent
transport (`source_engine=m2_mmap_process_persistent`,
`execution_arm=m2_mmap_process`, fresh 256 MiB staging, forked readers, own
CUDA context/registration/stream), and the HEAD bundle deleted the C0 branch
(`_load_c0_sync`, `_c0_enabled`, C0-aware `initialize_cuda`) plus the 9 C0
selector lines from the 12-CPU parallel profile.

The repair restores the last-good C0 dispatch (state as of `16104b2`) with
corrected identity:

```text
GOOD C0 BODY (parallel orchestration, 512 MiB arena, workers, restore, Gantt)
+ FAST M2 SOURCE KERNEL (exact-window mmap inside C0 child workers)
+ C0 DISPATCHER ASYNC H2D (shared stream/events over the registered arena)
= FAST C0
```

### 1.2 Commit / tag record

```text
commit: 398e3de "production-004: FAST C0 M2-source transport baseline"
tag:    production-004 (annotated object b5775ac → 398e3de)
```

Tag message records: 15/15 valid true-cold H100 runs, CPU=12, C0 Parallel,
512 MiB shared arena, exact-window mmap source, dispatcher async H2D, exact
SHA, tens-of-ms load tracking, no fallback, overlap preserved.

**Remote push: DEFERRED by operator decision.** GitHub rejects every push on
this branch: Sep-2 bundle commits in history contain 761–1196 MB evidence
files (100 MB limit); remote TESTING2 is stuck at Aug-30 (`02f1845`). The
local tag is frozen and was never moved. Follow-up commits (below) sit on
top; none retag `production-004`.

### 1.3 Commits on top of `production-004` (no worktrees, no retag)

```text
f799ab2 restore Golden Parallel console Gantt with Modal log rendering
c862412 fix C0 child spawn via content-hashed file (argv limit crash at restore)
ade4360 source observability: A-D probes, geometry selector, window trace
835a1b6 forward C0 scheduling selectors across Modal class env
a0b0300 C0 qd4_128 treatment geometry, transport selector, CPU/sched attribution
d9e8a0d restore decomposition: arena-ensure timing plus external restore Gantt row
533ce94 overlap C0 child spawn with arena registration at restore
```

### 1.4 Replacement map (as built)

| C0 component | Keep/replace | Replacement |
|---|---|---|
| Golden Parallel orchestration | KEEP | C0 (`golden_parallel.py` untouched except Gantt hook) |
| C0 restore / snapshot state | KEEP | C0 (observation-only + external metadata) |
| C0 512 MiB arena | KEEP | C0 (`C0_ARENA_BYTES = 536870912`) |
| C0 worker lifecycle | KEEP | C0 (child + 4 reader procs + dispatcher producers) |
| C0 model ownership / adoption | KEEP | C0 (existing CLIP/UNET bind + proofs) |
| C0 Gantt | KEEP + render | C0 intervals, new console renderer |
| source read syscall/algorithm | REPLACE | M2 exact-window mmap kernel (in C0 child) |
| source range scheduling | REPLACE minimally | QD4/64MiB static regions via shared dispatcher |
| source→GPU submission | REPLACE | C0 dispatcher async H2D (same pattern as proven M2 tail) |
| H2D completion gating | KEEP | C0 ticket/event/quiescence (already correct) |

### 1.5 Static validation (35/35 PASS) + unit tests

- C0 dispatch reached; shared dispatcher executes; H2D quiescence gates.
- C0 path contains no harness symbols (`load_m2_safetensors`, `build_staging,
  persistent_reader_main`, `cuMemHostRegister`, `cuStreamCreate`, fork/process).
- Identity keys present; arena 512 MiB; profile CPU=12 + 9 C0 selectors;
  CLIP+UNET record propagation; parallel entrypoint intact.
- Focused suite: 46 passed. Full FAST_UNIT: 281 passed, 2 failed in
  `test_rx9p_h_identity_chain.py` — pre-existing, unrelated module
  (`tools/v2_control/experiment_evidence.py`), untouched by this work.

### 1.6 Telemetry identity (emitted per CLIP/UNET load)

```text
execution_architecture = c0_parallel
execution_arm          = c0_parallel   (never m2_mmap_process)
source_engine          = m2_exact_window
h2d_engine             = c0_dispatcher_async
c0_arena_bytes         = 536870912
```

Fail-closed guard: `STREAMING=1` without `mmap_fresh` raises
`golden_model_transport_c0_streaming_requires_mmap_fresh` instead of silently
running the M2 arm. Geometry mismatch raises `c0_transport_geometry_unsupported`.

---

## 2. Gantt (Part 2, observability-only)

`render_parallel_console_gantt()` (`golden_human_report.py`, pure, ASCII-only,
no clock reads, no synchronization) renders recorded stage intervals +
transport durations; hooked after `TEARDOWN_COMPLETE` in
`golden_parallel_execute` (print to stdout → Modal logs, plus a
`golden_parallel_gantt` artifact event). Verified live via
`modal app logs batch-fastc0-sep26 --search "[GOLDEN GANTT]"`:

```text
[GOLDEN GANTT] mode=parallel arch=c0_parallel/m2_exact_window arena=512MiB
t+  0.000s |restore       |       5.7ms [...] | observation-only
t+  0.006s |request_setup |       1.2ms [...]
t+  0.007s |CLIP load     |    6358.8ms [####...] | src=5618.2ms full=6332.7ms eng=m2_exact_window qwen_3_4b.safetensors
t+  6.368s |UNET load     |    8530.3ms [...####...] | src=7302.7ms full=7328.4ms eng=m2_exact_window z_image_turbo_bf16.safetensors
t+  6.368s |CLIP forward  |    4079.6ms [...]
t+ 14.899s |sampler_prepare|     234.6ms [...]
t+ 15.134s |sampling      |    4222.3ms [...]
t+ 15.135s |VAE load      |     212.2ms [...]
t+ 19.357s |sampler_tail  |       0.0ms [...]
t+ 19.358s |VAE decode    |     670.7ms [...]
t+ 20.028s |output        |     210.1ms [...]
t+ 20.249s |teardown      |       0.2ms [...]
OVERLAP: unet_load inside clip_forward 4079.6ms; vae_load inside sampling 212.2ms
```

An `external restore:` lead-in row was added but prints only when adapter
restore metadata is supplied in-method; the adapter currently does not supply
it (its fail-closed boundary validation would reject a partial handoff), so
external totals remain in the manifest + waterfall log. Left conditional
deliberately — no handoff surgery for observability.

Acceptance held: exact SHA unchanged, C0 identity unchanged, 512 MiB
unchanged, CPU=12, source/overlap behavior unchanged (1 VALID run on the
Gantt deployment before/after comparison showed identical structure).

---

## 3. 15-run acceptance evidence (deploy `a382e745`, production-004 code)

All 15: VALID, true-cold, exact SHA, c0_parallel, m2_exact_window,
512 MiB arena, CPU=12, restore_count=1, request_count=1, no fallback, no
snapshot captures, same deployment, no code changes mid-campaign.

Payloads: CLIP `qwen_3_4b.safetensors` = 8,044,982,048 B (8.045 GB);
UNET `z_image_turbo_bf16.safetensors` = 12,309,817,472 B (12.31 GB).
Throughput metric: `GB/s = payload bytes / source wall s / 1e9`.

### 3.1 Raw rows (ms; ovh = full − source)

```text
run region      dur   restore  CLIP src/full/ovh      UNET src/full/ovh
1   uk        20646   1907     1692/1748/56           2215/2237/22
2   uk        68841   1626     1676/1733/58           2050/2092/42
3   ca        53058   1596     1547/1602/55           1853/1891/38
4   us-west   65172   2085     1615/1798/184*         2121/2152/31
5   us-west   18455   1967     1959/2021/62           2556/2581/26
6   ca        53924   1728     1612/1672/60           2004/2031/27
7   uk        42552   1733     3712/3778/66           5620/5709/89
8   us-central 53883  1675     2350/2406/56           3188/3217/29
9   us-central 52568  1354     1523/1576/53           2560/2586/26
10  eu-south  21589   1797     1827/2023/196*         2144/2184/40
11  eu-south  20377   1736     2232/2290/58           3672/3698/26
12  ca        31503   1712     4595/4673/77          13562/13604/42
13  ca        16031   1420     1691/1741/50           2079/2118/38
14  ca        17470   1369     1824/1894/70           2340/2372/32
15  ca        16261   1281     1815/1882/67           2165/2196/31
* runs 4/10 overhead includes first-touch GPU destination growth (~115–190 ms).
```

### 3.2 Overall (n=15; p90 = linear interpolation)

```text
metric      mean     median   min      max      range    sd      cv      p90
duration    36822    31503    16031    68841    52811    19487   52.9%   60673
restore      1666     1712     1281     2085      804      233   14.0%    1943
snap_restore 1236     1252      834     1666      832      224   18.1%    1523
clip_src     2111     1815     1523     4595     3072      878   41.6%    3167
clip_full    2189     1882     1576     4673     3097      875   40.0%    3229
clip_ovh       78       60       50      196      146       46   59.3%     141
unet_src     3342     2215     1853    13562    11708     2986   89.4%    4841
unet_full    3378     2237     1891    13604    11713     2992   88.6%    4905
unet_ovh       36       31       22       89       67       16   44.8%      42
clip_fwd     3126     3066     2622     4882     2260      551   17.6%     3406
sampler      3815     3775     3664     4188      524      147    3.9%    4012
```

Throughput medians: CLIP 8.045/1.815 = **4.43 GB/s**; UNET 12.31/2.215 =
**5.56 GB/s**. Loader invariant holds throughout: even run 12's pathological
UNET source (13562 ms) tracks full load within 42 ms.

### 3.3 Per-region sub-tables (p90 n/a for n<10)

```text
ca (n=6): restore med 1508 | clip_src med 1753 (CV 54.5%) | clip_ovh med 64 (CV 15.9%)
          unet_src med 2122 (CV 117.2%) | unet_ovh med 35 (CV 15.9%)
eu-south (n=2): restore med 1766 | clip_src med 2030 | clip_ovh med 127
          unet_src med 2908 | unet_ovh med 33
uk (n=3): restore med 1733 | clip_src med 1692 (CV 49.6%) | clip_ovh med 58 (CV 8.6%)
          unet_src med 2215 (CV 61.2%) | unet_ovh med 42
us-central (n=2): restore med 1514 | clip_src med 1937 | clip_ovh med 54
          unet_src med 2874 | unet_ovh med 28
us-west (n=2): restore med 2026 | clip_src med 1787 | clip_ovh med 123
          unet_src med 2338 | unet_ovh med 28
```

Overhead stays tens of ms in every region (worst 196 ms incl. destination
growth). Source throughput varies by host, not by region identity.

### 3.4 First-in-region vs rest (hypothesis: first runs slower — NOT supported)

First-in-region runs: 1, 3, 4, 8, 10 (n=5). Rest: n=10.

```text
            clip_src med  unet_src med  clip_ovh med  unet_ovh med  dur med
FIRST (5)   1692         2144           56             31           53058
REST (10)   1820         2448           61             32           25940
```

Firsts are slightly *faster* on source. The three source outliers (runs 7,
8, 12) include only one first-run. Slow sources are sporadic per-host
storage stalls, not region warm-up.

---

## 4. M2 vs FAST C0 — 14-item forensic diff (all traced to code)

| # | Proven standalone M2 | Current FAST C0 | Exact match? | Consequence |
|---|---|---|---|---|
| 1 QD | 4 (fork 1 proc/lane, self-serve ownership array, slots=1/lane) | 4 (4 dispatcher producer threads, queue_depth=4, 8 slots) | nominal yes; enforcement differs | none observed |
| 2 producers | 4 forked reader PROCESSES, persistent | 4 reader PROCS + parent threads + child pool | yes, +per-fill pipe/JSON hops | ~2 ms/fill host tax |
| 3 lanes | sticky ranges + stealing (`affinity_breaks`) | static contiguous/producer; reader=producer%4 | steady-state equivalent | none; no stealing |
| 4 CPU | no affinity; NO concurrent compute (GPU untouched) | no affinity; UNET src overlaps CLIP forward | **CONFOUND** | UNET slower/more variable |
| 5 windows | 64 MiB exact, partial via min() | 64 MiB `BLOCK_BYTES`, same min() | exact | none |
| 6 floor | `_alloc_gate` 4 ms in-reader pre-mmap | `_mmap_launch_gate` 4 ms at dispatch | nominal same; placement differs | floor never binds (p50 ~1us) |
| 7 align | `off & ~(PAGE-1)` + delta | `(off//PAGE)*PAGE` + delta | identical math | none |
| 8 length | roundup(delta+len), no POPULATE | same, no POPULATE, len ≤ slot validated | exact | none |
| 9 memcpy | libc memcpy → anon staging | libc memcpy → registered SHM direct | C0 FEWER copies | dest-type candidate |
| 10 munmap | publish BEFORE munmap (overlaps H2D) | munmap BEFORE reply (on path) | DIFFERS ~1.5–3 ms/fill | ~5% structural tax |
| 11 FD | LRU per-path + identity check | persistent per-(path,prod), never closed | equivalent; 4 FDs/model | none observed |
| 12 order | sticky contiguous + steal | static contiguous | equivalent; no rebalancing | tail-imbalance absorbed by slots |
| 13 backpressure | slots=1/lane, tight H2D coupling | 8 slots/4 prod, decoupled | C0 more headroom | zero starvation measured |
| 14 H2D gate | 1 stream, fresh event/xfer, tail 1.9–4.6 ms | shared stream, per-slot events, quiescence | same pattern | tail unstamped (None) |

Key derived facts: per-lane memcpy throughput is IDENTICAL in both
(~1.6 GB/s at 64 MiB; M2 6.6 aggregate = near-perfect overlap). The C0 gap
is overlap efficiency (~83%) + host variance, not mechanism. M2's structural
edge is zero per-fill IPC (shared-memory coordination vs C0's pipe round
trip per 64 MiB fill).

---

## 5. Stages A–E (each completed; verdicts with data)

- **A (slot/H2D backpressure):** Zero starvation on qd4_64 —
  `backpressure_block 0`, `producer_capacity_block 0.0 ms`, `min_free_slots`
  reaching 0 with no waits >100us, drain ~2 ms, H2D 86% idle. No fix needed.
- **B (launch parity):** QD4 genuinely concurrent (`qd_depth_max=4`,
  246–374 transitions, even 30/31 producer splits). Schedule parity holds.
- **C (per-window):** Stalls are single-window memcpy blowups (worst 3394 ms
  vs 23 ms p50; map/munmap innocent). First-touch penalty quantified
  (754 ms first vs 176 ms reuse cold). `gpu_ready_tail` stays null by design;
  overhead-over-source is the tail proxy.
- **D (CPU):** 4 readers 70–77% busy, majflt=0, no affinity anywhere.
  UNET-vs-CLIP gap confounds file placement with forward contention; the
  decisive serial-schedule diagnostic was deferred (GPU budget vs value) —
  recorded as the open CPU question, not a conclusion.
- **E (geometry matrix):**
  - `qd4_64` (current): STANDS. Best median, zero starvation, robust.
    Medians: CLIP 4.43, UNET 5.56 GB/s; best singles CLIP 6.03, UNET 6.64.
  - `qd4_64_h2d128` (H2D aggregation): REJECTED. CLIP 6083 ms (cap 12.9 s),
    UNET 13035 ms (cap 24.4 s) — aggregation holds slots 2x longer with the
    same pool; starvation is structural. (An earlier void run measured the
    wrong geometry due to a stale container; re-run engaged and confirmed.)
  - `qd2_128` (control slots): REJECTED. Warm 3.77/4.53 GB/s — halved
    parallelism never compensates (~25% slower than QD4 typical).
  - `qd4_128` true form (new 4x128MiB treatment geometry, same 512 MiB
    arena): REJECTED on robustness. Warm CLIP 5.26 GB/s matches qd4_64, but
    `cap_block` 280–945 ms — 4 producers on 4 slots have zero headroom and
    lockstep fills collide. Fragile by construction.

**6.5 GB/s median verdict: NOT achieved** (final qd4_64 cohort medians:
CLIP 4.65, UNET 5.24, n=8). Remaining owner, precisely: per-stream volume
throughput (~1.6–2.3 GB/s) × QD4 at ~80–85% overlap efficiency, plus fleet
host variance. The only structural path (shared-memory fill completion,
removing ~100 ms/load IPC tax) is a redesign — explicitly out of scope.
`munmap`-deferral (~5%) was evaluated and declined: protocol risk for
single-digit percent.

---

## 6. Crash incident + env-forwarding fix (found during Stage E)

- Deploy `e0614e17` crash-looped at restore: `OSError: [Errno 36] File name
  too long: '/usr/local/bin/python'`. Root cause: the C0 child program
  (132,169 B) crossed the kernel single-argument limit (131,072 B);
  production-004 sat at 130,761 B — 311 bytes of headroom. Any future
  instrumentation would have detonated it.
- Fix (`c862412`): spawn from a content-hashed file
  (`write_c0_child_source_file`); argv indexing unchanged. Unit test
  compile-checks the materialized program. No crashes since (log-verified).
- Related discovery: new profile flags never reached containers because
  `modal_app._runtime_env()` is an explicit allowlist. Added the two
  scheduling selectors (`835a1b6`, unit-pinned). This also explained the
  void V2 run. Lesson now encoded in tests: any new deploy-baked flag needs
  profile + registry + `_runtime_env` entries.

## 7. Snapshot/restore (Part 4)

Waterfall (medians): platform `snapshot_restore` ~1250 (outside Python, out
of scope) + Python ~430 = restore_total ~1612–1712. Arena establishment
(measured via new `arena_ensure` telemetry): SHM ~4 ms + `cudaHostRegister`
~230–360 ms + child startup ~124–365 ms.

Change (`533ce94`): spawn the child BEFORE `cudaHostRegister` (it needs only
the SHM name), hiding fork/exec/startup behind registration with no
threading; register-failure path upgraded to full cleanup (kills the
early-spawned child). Result: restore median 1712 → 1612 ms (n=15 vs n=8;
within fleet noise — claimed as no-regression + ~120 ms arena-component
reduction, not a breakthrough).

Audit (A=image, B=snapshot, C=repair-after-restore, D=per-request,
E=unnecessary): snapshot-restore/platform=A-out-of-scope; SHM/register/
spawn/streams/events=C (kept); GPU pool, layout/FD caches=D-lazy already;
generation checks=D-minimal; backend boot 27 s=A (amortized, not
per-request); custom-node publication already manual; no model scans; **E:
none found in the hot restore path** (reloads are already ~0 ms no-ops).
Deliberately NOT touched: `cudaHostRegister` flags (WC mappings would need
fencing proof for DMA visibility) and upstream ComfyUI VRAM rebuild
(~524 ms) — both violate the do-no-harm rule at this stage.

## 8. Correctness (final 8-run cohort, deploy `5115d284`)

8/8 VALID, true-cold, exact SHA, c0_parallel, m2_exact_window, 512 MiB
arena, CPU=12, restore_count=1, request_count=1, no fallback, regions
ca/eu-south/us-east/us-central/eu-west/us-west/ca. Restore median 1611.5
(1341–2531). Overhead medians: CLIP 63 ms, UNET 45 ms. One overhead outlier
(eu-west, CLIP ovh 894 ms on a 1.87 GB/s cold load) flagged for follow-up;
loader tracking held everywhere else (worst otherwise 150 ms).

## 9. Diff scope (all on TESTING2; `production-004` frozen; unrelated = zero)

- Production freeze: `golden_model_transport.py`, `golden_serial.py`,
  `golden_p1_parallel_m2clip_h100.toml`, `flag_registry.toml` (descriptions),
  2 test files → `398e3de` + tag.
- Gantt/observability: `golden_human_report.py`, `golden_parallel.py`,
  `test_parallel_console_gantt.py` → `f799ab2`.
- Crash fix: `golden_io_process_v2.py`, `test_c0_child_spawn.py` → `c862412`.
- Source parity instrumentation: transport, io_process_v2, registry, tests
  → `ade4360`.
- Env forwarding: `modal_app.py`, `test_runtime_env_forwarding.py` → `835a1b6`.
- qd4_128 scaffolding + CPU attribution: io_process_v2, transport,
  registry, tests → `a0b0300`.
- Restore/Gantt-row: transport, human_report, parallel, tests → `d9e8a0d`.
- Spawn/register overlap: io_process_v2 → `533ce94`.

## 10. Open follow-ups (not blocking)

1. GitHub push needs Ahmed's history repair (LFS or surgery for Sep-2 blobs).
2. v2ctl `no canonical run artifact` lookup gap for parallel cohorts
   (manifests authoritative; fix only if small/isolated).
3. Serial-schedule diagnostic to separate UNET file-placement vs
   forward-contention effects.
4. `gpu_ready_tail_ms` remains null (needs dispatcher completion timestamps).
5. eu-west CLIP 894 ms overhead outlier undecomposed.

---

## 11. Production-004 hardening addendum

This addendum supersedes stale conclusions above where they say the external
restore boundary is unresolved, Gantt output is artifact-only,
`gpu_ready_tail_ms` is null, or GitHub publication is deferred.

### 11.1 Restore Boundary And Fix

Historical known-good Python evidence reports:

```text
remote_python_resume_mono_ns == restore_method_start_mono_ns
restore_method_entry_gap_ms = 0.0
minimal_restore_total_ms = 2.129
restore_total_ms = 2.129
```

The pre-Python Modal snapshot interval is not inside that Python restore field.
The separately supplied `2.703 ms` external and `4.340 ms` Gantt values are
different display boundaries and must not be added to the persisted minimal
restore value.

The production regression was twofold:

1. The parallel profile did not explicitly select minimal restore, so it took the legacy restore path. A fresh run measured `restore_total_ms=1901.329`, including `snapshot_restore_ms=1379.23` and legacy runtime/CUDA work.
2. `golden_restore()` itself initialized the C0 transport and queried CUDA after adapter restore, inflating the human restore stage.

Fixes:

- `83171f7`: explicitly select `COMFYMODAL_GOLDEN_MINIMAL_RESTORE=1` in the parallel profile.
- `84780f9`: keep `golden_restore()` observation-only; C0 transport/CUDA initialization remains lazy at model load.
- `a76206c`: reuse a matching shared runtime-state marker for unchanged manifest content.

Latest exact run: `cohort_2026-09-27_02-27-51_2bd68a`, with
`minimal_restore_total_ms=2.361`. The Python restore target is restored to
single-digit behavior.

### 11.2 Real Modal Gantt Proof

The caller emits one flushed Modal log record per line. Literal lines from the
latest `modal app logs batch-fastc0-sep26` stream include:

```text
[GOLDEN GANTT] external restore: 2.4ms (pre-method, observation-only)
[GOLDEN GANTT] t+  0.000s |restore       |       0.2ms [...] | observation-only
[GOLDEN GANTT] t+  0.002s |CLIP load     |    4536.7ms [...] | src=3141.4ms full=4506.6ms ready=4493.9ms tail=3.1ms eng=m2_exact_window qwen_3_4b.safetensors
[GOLDEN GANTT] t+  4.637s |UNET load     |    7553.6ms [...] | src=5037.5ms full=5131.7ms ready=5123.6ms tail=3.4ms eng=m2_exact_window z_image_turbo_bf16.safetensors
[GOLDEN GANTT] OVERLAP: unet_load inside clip_forward 6747.6ms; vae_load inside sampling 330.8ms
```

### 11.3 GitHub Clean Publication

The exact frozen production tree contains no file over 100 MB. GitHub issued
only a 63.24 MB recommendation warning for
`reports/golden_sickness_forensic_2026-09-17/per_request.json`.

```text
validated local commit: 398e3de0659fa453b908bc70d8d61696cb9939da
validated tree SHA:     49ce91ac7eb9c7bb32e21271607277ee79dfa1c0
clean commit:            37b041facaec16da4c34b68c8d1253ba93f63f17
clean tree SHA:          49ce91ac7eb9c7bb32e21271607277ee79dfa1c0
tree identical:         yes
remote tag:             production-004 -> 37b041facaec16da4c34b68c8d1253ba93f63f17
```

The clean commit omits poisoned historical parent ancestry only. Local
`production-004` still points to `398e3de`; `TESTING2` was not rewritten.

### 11.4 CLIP Tail Decomposition

The dispatcher now records final source-byte completion, final H2D submit,
final H2D completion observation, views-ready, adoption start/end, and load
exit without a global CUDA synchronize. Latest C0 CLIP evidence:

```text
source wall:                         3141.418 ms
source end -> final H2D submit:        -1.239 ms (overlap)
source end -> final H2D complete:       3.149 ms
H2D complete -> views ready:           12.226 ms
views ready -> adoption start:         11.921 ms
adoption start -> adoption end:        15.285 ms
adoption end -> CLIP load exit:         2.478 ms
full load - source:                  1395.297 ms
```

The apparent `894 ms` event was not an H2D tail. It was full-load-minus-source
residual dominated by pre-source layout/skeleton work. The measured
source-to-GPU tail is `3.149 ms` for this run; latest UNET tail is `2.778 ms`.
`gpu_ready_tail_ms` is no longer null.

### 11.5 Source Parity Status

The C0 source scheduler now matches the M2 sticky-lane/self-serve behavior at
the producer-pool level: each producer consumes its sticky lane first, then
steals unclaimed extents from exhausted lanes. The latest run persisted
`affinity_breaks=37` for CLIP and `affinity_breaks=70` for UNET.

The C0 implementation still differs from standalone M2 in two material ways:
per-fill child pipe/JSON control remains, and C0 publishes after synchronous
munmap rather than before it. Existing mmap instrumentation records memcpy wall
time, minor/major faults, process CPU time, and schedstat run/wait deltas. A
same-file paired M2-vs-C0 cohort and removal of per-fill control IPC remain open
source-engine work.

Latest one-run source evidence after scheduler parity:

```text
CLIP source: 3141.418 ms = 2.561 GB/s
UNET source: 4227.829 ms = 2.912 GB/s
```

The 6.5 GB/s median target is **not achieved**. The remaining owner is the
source-side host/storage path and C0 control/munmap coordination, not H2D
completion or adoption. No M2 throughput-parity claim is made yet.

### 11.6 Verification

- `test_parallel_console_gantt.py`: 4 passed.
- `test_runtime_state_reload_guard.py`: 33 passed.
- `test_golden_model_transport.py`: 26 passed.
- Changed modules pass `py_compile`.
- `test_golden_qd_transport.py` and P2 contract tests hit a Windows torch import access violation during collection before any test ran; this is an environment failure, not a test assertion failure.

### 11.7 Control-session stall containment

The first Linux run of the new C0 control session exposed a 15-minute stall:
the parent inherited the old `900 s` per-fill timeout while the child control
descriptor remained unresolved. This was a real operational defect.

Containment is now committed in `384e315` / `95bd664`:

- shared-session waits are hard-capped at 30 seconds;
- legacy C0 fill waits are also capped at 30 seconds;
- control-loop exceptions resolve active descriptors and stop the loop;
- the shared control session is disabled by default until its Linux child path
  is repaired and revalidated.

The subsequent production run completed normally in about one minute; no new
15-minute stall was observed. The shared session remains a development arm,
not a production claim, until the unresolved child descriptor cause is fixed.

The remaining live-session failure was then isolated: `write_request()` wrote
the new sequence into both `published` and `consumed`, so the child correctly
ignored the request because `published <= consumed`. `b301dbb` removes that
write. The next Linux run completed successfully with the shared session
active; source throughput was CLIP `5.47 GB/s` and UNET `6.01 GB/s`, with no
control timeout.

### 11.8 Canonical Gantt Format

The custom hash-bar renderer was removed in `384e315`. Production logs now use
the existing `modal_app` waterfall plus `gantt_telemetry`/`gantt_canonical`
renderers: boxed stage tables and square-block remote Gantt windows. The
`golden_parallel` path no longer emits a competing hash-bar chart.
