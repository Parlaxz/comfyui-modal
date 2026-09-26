# Triggered Cross-Source Probe — Localization Campaign

Scope: diagnosis only. No Golden changes, no geometry/QD/priming changes, no mitigation.
Campaign: 15 fresh H100 containers (hard cap 25). Stopped when >=3 pathological episodes and >=3 clean runs existed.

Raw data: `cross_source_runs/cs-r01.json` .. `cs-r15.json`, `campaign.log`, `analysis.txt`
Engine: `comfymodal_runtime/source_race_oracle.py::run_cross_source_probe`
App: `e04_source_race_modal.py::run_cross_source_h100` (deployed to Testing 4)
Runner: `tools/run_cross_source_campaign.py` | Analysis: `tools/analyze_cross_source.py`

---

## 1. Executive summary

The campaign captured 12 pathological episodes and 3 clean runs, but **the diagnostic probes never
executed during the episode that triggered them.** In all 12 episodes the triggering requests cleared
before the earliest probe reached its syscall (clears at +34..+1217 ms after trigger; earliest probe
syscall entry at +428..+1825 ms after trigger). The reason is the phenomenon under study: under the
stall, spawning a thread and reaching `os.open()`/`preadv` costs 0.4–1.8 s.

Consequence: **CASE 1/2/3/4/6 cannot be discriminated from this campaign.** Probes A/B/C/D measured the
post-stall recovery window, not the stall.

What *did* work is probe E, the heartbeat — the only probe that is continuously in flight and therefore
cannot be defeated by startup latency. It shows a container-wide execution stall:

- heartbeat max inter-sample gap 910 / 987 / 922 / 1591 / 1940 / 2074 ms in the six large episodes
- vs 76 / 105 / 141 ms in the three clean runs (median gap 5.4 ms in every run)
- heartbeat max gap tracks episode magnitude almost exactly

One probe did land inside a later stall: **cs-r13 `A_same_file_fresh_fd` entered t=4105 ms, exited
t=4957 ms, latency 852 ms, overlapping a co-terminous 4-worker stall of worst 852 ms.** A brand-new FD
on the same file was exactly as trapped as the four existing workers.

Narrowest supported domain: **whole sandbox/container (CASE 5)**, with cohort/file/Volume/filesystem not
excluded.

---

## 2. Diagnostic implementation

Normal workers unchanged: 4 persistent threads, persistent FDs, 64 MiB reads, QD4, 120 blocks, no primer,
reusable buffers, same enter/exit telemetry. Diagnostic bytes excluded from measured throughput.

Trigger: monitor thread polls every 10 ms; fires exactly ONE probe set when any outstanding normal
`preadv` has elapsed >= 250 ms; re-arms only after `outstanding` is empty (episode clearly ended).

Probes (each own thread, own FD, own buffer, own enter/exit timestamps, 4 MiB):
- A `A_same_file_fresh_fd` — new FD, same model file, range = last 4 MiB of file (non-overlapping)
- B `B_same_range_fresh_fd` — new FD, same file, same offset+length as a currently blocked request
- C `C_other_volume_file` — new FD, `/root/models/diffusion_models/z_image_turbo_bf16.safetensors`, offset 0
- D `D_local_file` — new FD, `/tmp/c0_local_probe.bin` (tmpfs, 16 MiB, written before the run), offset 0
- E heartbeat — thread appending `(perf_counter_ns, counter)` every 5 ms, no I/O

Clean-run reference: same A/C/D set fired once at ~500 ms on the first 3 runs.

Implementation notes / deviations from spec:
- `enter` is recorded after `os.open()` and buffer allocation, so "probe enter" includes FD open and
  4 MiB allocation, not only the `preadv`. This is why startup delay is visible at all.
- B was not included in clean-reference sets (no blocked range existed) — healthy B baseline is missing.
- D always reads offset 0 (not rotating).
- E records only `perf_counter_ns`; `process_time_ns` was not captured, so "not scheduled" vs
  "clock read delayed" cannot be separated from this data alone.

---

## 3. Static source identities (identical in every run)

| item | value |
|---|---|
| target model file | `/root/models/text_encoders/qwen_3_4b.safetensors` — size 8044982048, `st_dev=31`, `st_ino=4`, `st_mtime_ns=1781316088009883330` |
| alternate same-Volume file | `/root/models/diffusion_models/z_image_turbo_bf16.safetensors` — size 12309866400, `st_dev=31`, `st_ino=6` |
| local diagnostic file | `/tmp/c0_local_probe.bin` — size 16777216, `st_dev=18`, `st_ino=268`, tmpdir `/tmp` |
| guest kernel | `4.19.0-gvisor` |
| syscall impl | `os.preadv` (`preadv_available=true`) |
| image | `im-uYqts8YnS01B1QygCc1utS` |

`st_dev` 31 for both Volume files; 18 for tmpfs. Both Volume files share the same device, so probe C
genuinely tests "different file, same mounted source".

---

## 4. Per-run table

"workers >=250 ms at trigger" = normal workers with elapsed >= 250 ms at the trigger instant.
Diagnostic latencies are ms; **none of A/B/C/D overlapped the triggering episode** except where noted.

| run | region | sick/clean | worst normal preadv | workers >=250 ms at trigger | A same-file | B same-range | C other-Volume | D local | heartbeat healthy? | originals exited after trigger | classification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cs-r01 | GCP/us-east4 | SICK | 339 | 1 (w1 256) | 72 | 80 | 60 | 78 | yes (179 ms) | +84 | inconclusive (probe after episode) |
| cs-r02 | GCP/us-east | SICK | 1080 | 4 (all 913) | 130 | 228 | 168 | 58 | NO (910 ms) | +167 | inconclusive |
| cs-r03 | GCP/asia-south2 | SICK | 297 | 1 (w2 255) | 138 | 52 | 70 | 1 | yes (211 ms) | +43 | inconclusive |
| cs-r04 | GCP/us-east4 | SICK | 991 | 4 (all 810) | 126 | 186 | 84 | 3 | NO (987 ms) | +180 | inconclusive |
| cs-r05 | GCP/us-east4 | SICK | 318 | 1 (w2 254) | 226 | 48 | 111 | 55 | yes (181 ms) | +64 | inconclusive |
| cs-r06 | OCI/us-chicago-1 | SICK | 290 | 1 (w2 256) | 97 | 90 | 88 | 74 | yes (215 ms) | +34 | inconclusive |
| cs-r07 | UNSPECIFIED/CANADA-2 | SICK | 298 | 1 (w2 252) | 183 | 101 | 279 | 70 | marginal (271 ms) | +46 | inconclusive |
| cs-r08 | GCP/us-east | SICK | 853 | 4 (all 361) | 199 | 72 | 57 | 97 | NO (922 ms) | +285 | inconclusive |
| cs-r09 | UNSPECIFIED/odin | clean | 199 | – | – | – | – | – | yes (76 ms) | – | – |
| cs-r10 | OCI/us-chicago-1 | SICK | 315 | 1 (w1 254) | 149 | 136 | 83 | 75 | yes (213 ms) | +61 | inconclusive |
| cs-r11 | AWS/us-east | clean | 239 | – | – | – | – | – | yes (105 ms) | – | – |
| cs-r12 | GCP/us-east | SICK | 2161 | 2 (w1 1465, w2 1466) | 259 | 94 | 111 | 1 | NO (1591 ms) | +128..+697 | inconclusive |
| cs-r13 | UNSPECIFIED/CANADA-2 | SICK | 3497 | 1 (w2 2280) | **852 (overlapped later stall)** | 94 | 57 | 57 | NO (1940 ms) | +1217 | **CASE 2/3 lean (fresh same-file equally trapped)** |
| cs-r14 | UNSPECIFIED/eu-north | SICK | 2567 | 1 (w0 2506) | 58 | 116 | 47 | 1 | NO (2074 ms) | +61 | inconclusive |
| cs-r15 | GCP/us-east | clean | 222 | – | – | – | – | – | yes (141 ms) | – | – |

Heartbeat verdict uses a 300 ms threshold on max gap. Note cs-r07 at 271 ms is borderline; clean runs top
out at 141 ms, so 271 ms is already anomalous.

---

## 5. Episode timelines

### cs-r01 — trigger fires on time, probes miss anyway (single-worker, 339 ms)

```
t=0     w1 gen0 normal preadv ---------------------------| exit 339 ms (339 ms)   [only sick worker]
        w0 gen0 (16 ms at trigger) | w2 (20) | w3 (22)

t=256   TRIGGER  (w1 elapsed 256 ms)

t=340   all blocked requests cleared                          (+84 ms after trigger)
t=738   A same-file fresh FD enter  -> exit 810   (lat 72)    (+482 ms after trigger)
t=992   B same-range fresh FD enter -> exit 1071  (lat 80)    (+736 ms)
t=1112  C other-Volume file enter   -> exit 1172  (lat 60)
t=1173  D local tmpfs enter         -> exit 1251  (lat 78)

verdict: every probe ran in the post-stall recovery window, 398-917 ms after the stall cleared.
```

### cs-r13 — the one probe that landed inside a stall (852 ms, 4 workers)

```
t=0     w0 gen0 ----------------------| exit 2241 (2241 ms)
        w1 gen0 ----------------------| exit 2280 (2280 ms)
        w3 gen0 ----------------------| exit 2280 (2280 ms)
        w2 gen0 --------------------------------------| exit 3497 (3497 ms)
        w0 gen1 (enter 2241) -------------------| exit 3497 (1256 ms)
        w1 gen1 (enter 2280) -------------------| exit 3497 (1218 ms)
        w3 gen1 (enter 2280) -------------------| exit 3497 (1217 ms)

t=2280  TRIGGER (w2 elapsed 2280 ms)
t=3497  triggering cohort cleared                             (+1217 ms after trigger)
t=3667  w3 gen5 alone, 304 ms
t=4105  w0/w1/w2/w3 all enter gen (co-terminous stall #2)
t=4105  A same-file fresh FD enter ---------------------| exit 4957  (852 ms)  <-- INSIDE stall #2
t=4957  stall #2 ends; all four workers exit together
t=5172  B same-range fresh FD enter -> exit 5266 (94 ms)      [no stall active]
t=5267  C other-Volume file enter   -> exit 5324 (57 ms)
t=5267  D local tmpfs enter         -> exit 5324 (57 ms)

verdict: during a co-terminous 4-worker stall of 852 ms, a brand-new FD on the same file took
852 ms for 4 MiB (healthy baseline 1.5-4.2 ms). No escape.
```

### cs-r14 — 2.5 s stall, heartbeat confirms whole-container freeze

```
t=1     w0 gen0 ---------------------------------------| exit 2567 (2567 ms)
        w1 gen0 ---------------------------| exit 2153 (2152 ms)
        w2 gen0 -------------------------------| exit 2233 (2232 ms)
        w3 gen0 -----------------------| exit 2078 (2078 ms)
t=2507  TRIGGER (w0 elapsed 2506 ms)   <- monitor loop itself stalled ~2.25 s
t=2568  all cleared                                            (+61 ms)
t=3112  A same-file enter -> exit 3170 (58 ms)
t=3349  B same-range enter -> exit 3465 (116 ms)
t=3605  D local tmpfs enter -> exit 3607 (1 ms)

heartbeat max gap = 2074 ms, coincident with the stall.
```

---

## 6. Healthy baseline probe latencies

From clean-reference sets at ~500 ms on cs-r01/r02/r03:

| probe | cs-r01 | cs-r02 | cs-r03 |
|---|---|---|---|
| A same-file fresh FD | 1.5 | 4.2 | 2.1 |
| C other-Volume file | 3.4 | 3.4 | 3.7 |
| D local tmpfs | 1.4 | 3.3 | 1.9 |
| B same-range | not fired (no blocked range) | – | – |

Baseline for 4 MiB is **1.4–4.2 ms**. Post-stall recovery values were 47–852 ms, i.e. **15–200x
baseline**, so the recovery tail is long and affects tmpfs (D, 55–97 ms in 7 of 12 episodes) as well as
the model Volume.

---

## 7. Cross-episode consistency

| observation | value across episodes |
|---|---|
| probes overlapping the triggering episode | 0 of 12 |
| probes overlapping any later stall | 1 of 48 (cs-r13 A) |
| trigger->clear (blocked cohort) | 34, 34, 43, 46, 61, 61, 64, 84, 128..697, 167, 180, 1217 ms |
| trigger->earliest probe syscall entry | 428, 482, 605, 607, 672, 698, 776, 842, 947, 992, 1081, 1462, 1539, 1602, 1825 ms |
| monitor loop lateness in large episodes | r12 ~1215 ms, r13 ~2029 ms, r14 ~2256 ms (should fire at ~251 ms) |
| heartbeat max gap vs clean | large episodes 910–2074 ms; clean 76–141 ms |
| heartbeat median gap | 5.4 ms in every single run |
| co-terminous multi-worker stalls | cs-r02 (1080), cs-r04 (990–991), cs-r08 (646–647), cs-r12 (2163), cs-r13 (3497), cs-r14 (2078–2568) |
| single-worker stalls | cs-r01, cs-r03, cs-r05, cs-r06, cs-r07, cs-r10 (290–339 ms) |

Two clean episode shapes exist: a short single-worker spike (~300 ms) and a long co-terminous
all-worker freeze (650–3500 ms). The long shape is the one that destroys throughput (1.33–2.38 GB/s vs
4.26–6.26 GB/s clean).

---

## 8. Evidence table

| Finding | Episodes supporting | Confidence | Implication |
|---|---|---|---|
| Triggered probes cannot observe the episode that triggers them | 12/12 | High (direct timestamps) | The triggered-probe design is defeated by the stall's own startup latency. Any re-run must use already-in-flight probes. |
| Thread start + open + alloc under stall costs 428–1825 ms | 12/12 | High | The stall delays *new work*, not only in-flight I/O. |
| Monitor's own 10 ms poll loop stalls 1.2–2.3 s | r12, r13, r14 | High | A pure-scheduling userspace loop freezes — not an I/O-path-only effect. |
| Heartbeat (no I/O) stalls 910–2074 ms, tracking episode size | r02, r04, r08, r12, r13, r14 | High | Userspace scheduling does **not** remain healthy. Supports CASE 5. |
| Heartbeat median gap 5.4 ms in all runs, timeline spans full run | 15/15 | High | Rules out "heartbeat thread never ran"; the gap is a mid-run freeze. |
| Co-terminous multi-worker exits | r02, r04, r08, r12, r13, r14 | High | Shared release instant — a shared blocking domain, not independent per-request luck. |
| Fresh same-file FD equally trapped (852 vs 852 ms) | r13 (n=1) | Low-Medium | Points away from CASE 1/6 toward CASE 2/3, but single observation. |
| Post-stall recovery tail hits tmpfs too (55–97 ms) | 7/12 | Medium | Recovery slowness is not disk-queue-only. |
| Probes did not release the episode | 12/12 | High | Every clear preceded probe syscall entry, so probes cannot have caused the clears. |
| Clean runs still spike (199–239 ms reads, 76–141 ms heartbeat gaps) | r09, r11, r15 | High | The phenomenon is a continuum, not binary; "clean" still contains ~100 ms freezes. |

---

## 9. Final answers

**Can fresh same-file requests escape while old requests are stuck?**
Not answered for the triggering episode — no probe ever ran during one. The single later-stall
observation (cs-r13) says **no**: a fresh FD took 852 ms for 4 MiB while four existing workers took
852 ms.

**Can a different file on the same Volume escape?**
Not answered. Probe C never overlapped a stall. Post-stall values 47–279 ms.

**Does local filesystem I/O remain healthy?**
Not answered during a stall. Post-stall tmpfs values 1–97 ms, i.e. elevated 15–60x over the 1.4–3.3 ms
baseline in 7 of 12 episodes.

**Does userspace scheduling/heartbeat remain healthy?**
**No.** Heartbeat max gap 910–2074 ms in the six large episodes vs 76–141 ms clean, with median 5.4 ms
throughout. The monitor loop and new-thread startup freeze on the same schedule.

**Is sickness scoped to request cohort, file, Volume, filesystem, or whole sandbox?**
Evidence supports **whole sandbox/container (CASE 5)**. The narrower cases are not excluded, because the
only probe class that was continuously in flight (E) is not source-specific.

**Does a same-range fresh request bypass an older blocked request?**
Not answered. Probe B never overlapped a stall.

**Do diagnostic probes appear to change/unblock the pathological episode?**
No. In all 12 episodes the cohort cleared 34–1217 ms after trigger while the earliest probe syscall entry
was 428–1825 ms after trigger — every clear preceded probe entry. The co-terminous exits are the stall
ending, not a probe effect.

**Does the natural-escape behavior from historical experiments reproduce?**
Not tested by this campaign; it cannot speak to it.

**What is the narrowest current owner/state domain?**
Whole sandbox/container execution (gVisor), with file/Volume/filesystem/cohort unresolved.

**What exact next subsystem should we investigate?**
Not another source sweep — the measurement instrument. Two concrete defects to fix:
1. Probes must be **already in flight** (pre-opened FDs, always-on low-rate readers) rather than spawned
   on trigger, because spawning costs 0.4–1.8 s under the stall.
2. The heartbeat must record `process_time_ns` alongside `perf_counter_ns` so "thread not scheduled" can
   be separated from "clock read delayed under gVisor". A forked CPU-only spin process (separate PID, no
   shared GIL) would discriminate host/sandbox CPU starvation from a Sentry syscall-path stall.

Then re-ask the original localization question, which this campaign could not answer.
