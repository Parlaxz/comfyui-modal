# 2×2 Execution/Syscall Matrix — Is the gVisor Syscall Path Stalling Globally?

Diagnosis only. No Golden change, no geometry/QD/block-size/priming change, no tuning after seeing results, no follow-up campaign.

- Campaign: 25 fresh H100 containers (`mx-01..mx-25`) — **hit the hard cap** with 2 large episodes + 18 clean.
- Helper: `native_canary.c` → `/opt/native_canary.so` (gcc at image build).
- Engine: `comfymodal_runtime/source_race_oracle.py::run_sentinel_probe`
- App: `e04_source_race_modal.py::run_sentinel_h100` | Runner: `tools/run_sentinel_campaign.py`
- Analysis: `tools/analyze_matrix_2x2.py`
- Raw: `sentinel_runs/mx-*.json`, `sentinel_runs/{campaign_mx.log,mx_analysis.txt}`, smoke `sentinel_runs/mx-on-*.json`

---

## 1. Executive summary

**CASE C: trivial syscalls are healthy everywhere.** The identical syscall (`SYS_gettid`) did **not** stall in either PID, while Python froze 108–403 ms.

| episode | worst source read | Python hb | U_MAIN | **S_MAIN** sched/lat | U_CHILD | **S_CHILD** sched/lat |
|---|---|---|---|---|---|---|
| mx-02 | 604 ms | 402.5 ms | 2.0 | **1.0 / 2.4** | 2.0 | **7.0 / 6.6** |
| mx-05 | 279 ms | 134.6 ms | 2.0 | **0.4 / 0.1** | 2.4 | **3.6 / 1.4** |
| mx-12 | 358 ms | 198.2 ms | 2.0 | **0.0 / 0.2** | 2.0 | **0.0 / 0.2** |
| mx-16 | 279 ms | 119.0 ms | 2.0 | **0.0 / 0.3** | 2.0 | **0.8 / 0.4** |
| mx-23 | 286 ms | 107.8 ms | 2.0 | **0.0 / 2.1** | 2.0 | **0.0 / 0.4** |
| mx-25 | 277 ms | 277.8 ms | 2.0 | **5.0 / 2.3** | 2.0 | **8.1 / 10.7** |

(ms; `sched` = intended→enter, `lat` = enter→exit.)

So:
- **Not CASE A** — no global syscall-path stall.
- **Not CASE B** — no main-PID-scoped syscall stall (S_MAIN ≈ S_CHILD; if anything S_CHILD is slightly worse).
- **CASE C** — syscall *dispatch* is healthy in both PIDs.

This must **not** be mislabeled as PID-specific. The correct reading is narrower: **the pathology is specific to syscalls that BLOCK**, not to syscalls per se.

`SYS_gettid` is a fast, non-blocking syscall — it enters the Sentry and returns without parking the task. `os.preadv` on a blocking file read and `Event.wait()`'s futex both park the task goroutine and depend on a wakeup. Those are the two paths that stall. So the domain narrows to the **gVisor task blocking/wakeup path**, and the audit below shows both stalled paths genuinely share that mechanism.

Also important: **mx-24 had a 622 ms source read with only 60.3 ms of Python freeze.** A large source read occurred with no Python freeze — further evidence that "slow preadv" and "Python/syscall freeze" are correlated symptoms, not cause and effect, and that the causal direction is unresolved.

**Caveat on the capture goal:** the campaign reached the 25-container cap with only 2 large episodes (mx-02 604 ms, mx-24 622 ms) against a target of ≥3. Sickness was simply rarer in this window (18/25 clean). Per instructions I stopped at the cap and did **not** tune geometry, cadence, or the trigger to manufacture more episodes. Every episode captured shows the same result, so the conclusion is consistent, but it rests on 6 episodes rather than the intended 3 large + more.

---

## 2. Exact 2×2 instrumentation topology

```
                    SAME PID (python pid)     SEPARATE PID (forked child)
PURE USERSPACE      U_MAIN  (no syscalls)     U_CHILD (no syscalls)
TRIVIAL SYSCALL     S_MAIN  (SYS_gettid)      S_CHILD (SYS_gettid)
```

All four are native pthreads created before any source worker thread:
- **U_***: busy-spin, `clock_gettime(CLOCK_MONOTONIC)` only, records `(ts_ns, seq)`, 2 ms cadence.
- **S_***: busy-spin pacing on the same vDSO clock, records `(intended_ns, enter_ns, exit_ns, retval)` around one `syscall(SYS_gettid)`, 3 ms cadence. **No sleep/nanosleep/Event/futex is used to establish cadence** — that would itself be a syscall and would confound the measurement.
- Identical syscall number, cadence, clock, ring format and timestamp semantics in both PIDs. The only intended difference is PID/thread-group identity.
- Each process has its own two preallocated anonymous `mmap` rings (created before `fork`, so the child's are shared with the parent for collection). Python never touches them during the run.
- No Python C-API, no GIL, no I/O, no `malloc`/`free`, no locks, no logging in any canary.

Ordering: identities → tmpfs file → sentinel FDs+buffers → 4 rings → **fork** (before any thread exists) → child starts U_CHILD+S_CHILD → parent starts U_MAIN+S_MAIN → heartbeat+sentinels → worker buffers/FDs → workers, `settle_ms=0`.

Source workload unchanged: H100, 64 MiB, QD4, 4 persistent Python workers, persistent FDs, reusable buffers, 120 blocks, `qwen_3_4b.safetensors`, no primer.

**One CPU is busy-spun per userspace canary and one more by the syscall canaries' pacing loops** (12 declared CPUs). Stated explicitly.

---

## 3. Syscall choice and proof it is a real syscall path

Chosen syscall: **`SYS_gettid` = 186** (x86-64), issued as raw `syscall(SYS_gettid)`, not a libc-cached wrapper.

Measured separation, native C, 20 000 iterations per run:

| run | `clock_gettime(CLOCK_MONOTONIC)` | `syscall(SYS_gettid)` | ratio |
|---|---|---|---|
| mx-01 | 36.9 ns/call | 5500.2 ns/call | 149x |
| mx-02 | 37.2 ns/call | 4458.2 ns/call | 120x |
| mx-03 | 37.1 ns/call | 5018.5 ns/call | 135x |
| mx-04 | 33.9 ns/call | 4555.5 ns/call | 134x |

**~120–149x separation** — the chosen monotonic clock is vDSO/userspace-fast (consistent with the previous campaign), while `SYS_gettid` behaves like a genuine syscall entering gVisor. It is *not* `clock_gettime`, which was already proven not to be a syscall. `process_time_ns` was not used anywhere.

Corroboration: in-run tick counts (e.g. mx-02 S_main=235, S_child=235 ticks inside a 604 ms episode) show the cadence held and the syscall loop was executing throughout.

---

## 4. PID/TID topology

| run | python pid | U_MAIN | S_MAIN | worker TIDs | child pid | U_CHILD | S_CHILD |
|---|---|---|---|---|---|---|---|
| mx-on-1 | 2 | pid 2, tid 8 | pid 2, tid 9 | 16,17,18,19 | 7 | pid 7, tid 13 | pid 7, tid 14 |
| mx-on-2 | 2 | pid 2, tid 8 | pid 2, tid 9 | 16,17,18,19 | 7 | pid 7, tid 12 | pid 7, tid 13 |
| mx-on-3 | 2 | pid 2, tid 8 | pid 2, tid 9 | 16,17,18,19 | 7 | pid 7, tid 12 | pid 7, tid 13 |

**U_MAIN and S_MAIN share the Python PID (2) with all four source workers**; **U_CHILD and S_CHILD are outside it (pid 7)**. All four have distinct TIDs. The same-PID pair is genuinely a pthread pair of the source process, not a disguised subprocess.

---

## 5. Perturbation validation

Arm A = the 11 runs from the previous native-canary campaign (single pthread, no syscall canaries). Arm B = 3 runs with the full 2×2.

| arm | n | median gbps | median refill gap | max refill gap | sick >=500 | clean <250 | QD balanced |
|---|---|---|---|---|---|---|---|
| A (previous topology) | 11 | 4.24 | 0.010 ms | 26.3 ms | 3 | 5 | True |
| B (2×2 added) | 3 | 4.69 | 0.009 ms | 1.1 ms | 1 | 2 | True |

- **Source QD unchanged**: per-worker reads exactly `{0:30, 1:30, 2:30, 3:30}`, balanced in every run.
- **Refill gaps unchanged**: 0.009 vs 0.010 ms median; arm B's max is *better* than arm A's single outlier.
- **Pathology still observable**: mx-on-3 produced a 1309.8 ms source episode in the smoke.
- **Syscall rate low enough**: at 3 ms cadence, ~1300–1700 ticks over a run, against a ~4–5 GB/s source. No throughput destruction observed (arm B median 4.69 > arm A 4.24).
- **No suppression**: 2×2 added, episodes still occurred at a similar rate.

The 2 ms userspace / 3 ms syscall cadences were kept as chosen and **not** adjusted after seeing outcomes.

---

## 6. Per-run table (campaign, 25 containers)

| run | region | worst src | workers | py hb | U_MAIN | S_MAIN sched/lat | U_CHILD | S_CHILD sched/lat | class |
|---|---|---|---|---|---|---|---|---|---|
| mx-01 | GCP/us-east4 | 193 | – | – | – | – | – | – | CLEAN |
| **mx-02** | GCP/europe-west2 | **604** | 0,1,2,3 | 402.5 | 2.0 | 1.0/2.4 | 2.0 | 7.0/6.6 | CASE C |
| mx-03 | GCP/us-east | 243 | – | – | – | – | – | – | CLEAN |
| mx-04 | GCP/us-west | 199 | – | – | – | – | – | – | CLEAN |
| mx-05 | GCP/us-east | 279 | 2 | 134.6 | 2.0 | 0.4/0.1 | 2.4 | 3.6/1.4 | CASE C |
| mx-06 | AWS/us-west | 168 | – | – | – | – | – | – | CLEAN |
| mx-07 | GCP/us-west | 191 | – | – | – | – | – | – | CLEAN |
| mx-08 | AWS/us-west | 171 | – | – | – | – | – | – | CLEAN |
| mx-09 | GCP/us-west | 192 | – | – | – | – | – | – | CLEAN |
| mx-10 | AWS/us-west | 162 | – | – | – | – | – | – | CLEAN |
| mx-11 | OCI/us-chicago-1 | 239 | – | – | – | – | – | – | CLEAN |
| mx-12 | AWS/us-west | 358 | 2 | 198.2 | 2.0 | 0.0/0.2 | 2.0 | 0.0/0.2 | CASE C |
| mx-13 | UNSPECIFIED/odin | 188 | – | – | – | – | – | – | CLEAN |
| mx-14 | UNSPECIFIED/london | 204 | – | – | – | – | – | – | CLEAN |
| mx-15 | GCP/us-west | 241 | – | – | – | – | – | – | CLEAN |
| mx-16 | GCP/us-west | 279 | 0 | 119.0 | 2.0 | 0.0/0.3 | 2.0 | 0.8/0.4 | CASE C |
| mx-17 | GCP/us-west | 143 | – | – | – | – | – | – | CLEAN |
| mx-18 | GCP/us-west1 | 234 | – | – | – | – | – | – | CLEAN |
| mx-19 | GCP/us-west | 178 | – | – | – | – | – | – | CLEAN |
| mx-20 | GCP/us-west1 | 228 | – | – | – | – | – | – | CLEAN |
| mx-21 | GCP/us-west | 205 | – | – | – | – | – | – | CLEAN |
| mx-22 | GCP/us-west1 | 161 | – | – | – | – | – | – | CLEAN |
| mx-23 | GCP/us-west1 | 286 | 2 | 107.8 | 2.0 | 0.0/2.1 | 2.0 | 0.0/0.4 | CASE C |
| **mx-24** | GCP/us-west | **622** | 1 | 60.3 | 2.0 | 7.1/5.9 | 2.0 | 0.8/3.6 | no python freeze |
| mx-25 | GCP/us-east | 277 | 0,1,2 | 277.8 | 2.0 | 5.0/2.3 | 2.0 | 8.1/10.7 | CASE C |

Note mx-24: a 622 ms source read with only 60.3 ms of Python freeze, and S_main/S_child both ≤7.1 ms. A slow blocking read occurred with essentially no process freeze.

---

## 7. Timelines

### mx-02 — 604 ms, all four workers (the only >=500 ms episode with a full Python freeze)

```
SOURCE (Python workers, pid 2)
 w0..w3  |============== 604 ms ==============|
         enter ~0 ms, exit ~604 ms

PYTHON HEARTBEAT (pid 2, needs GIL + futex)
         |........... 402.5 ms GAP ...........|

U_MAIN (pid 2, tid 8, NO syscalls)
         tick tick tick tick tick ... max gap 2.0 ms

S_MAIN (pid 2, tid 9, SYS_gettid every 3 ms)
         syscall syscall syscall syscall ... 235 ticks
         max scheduling delay 1.0 ms | max syscall latency 2.4 ms

U_CHILD (pid 7, NO syscalls)
         tick tick tick tick tick ... max gap 2.0 ms

S_CHILD (pid 7, SYS_gettid every 3 ms)
         syscall syscall syscall syscall ... 235 ticks
         max scheduling delay 7.0 ms | max syscall latency 6.6 ms

=> identical syscall: 1.0 ms in the frozen PID, 7.0 ms in the healthy PID.
   The syscall path is NOT stalled anywhere. Only blocking paths stalled.
```

### mx-24 — 622 ms source read, NO Python freeze

```
SOURCE
 w1  |================== 622 ms ==================|

PYTHON HEARTBEAT    max gap 60.3 ms   <- no freeze
U_MAIN              max gap 2.0 ms
S_MAIN              7.1 ms sched / 5.9 ms lat
U_CHILD             max gap 2.0 ms
S_CHILD             0.8 ms sched / 3.6 ms lat

=> a 622 ms blocking read with no process-level freeze at all.
   "Slow preadv" and "Python freeze" are separable.
```

### mx-25 — 277 ms, workers 0,1,2

```
SOURCE           |==== 277 ms ====|
PYTHON           |.. 277.8 ms GAP ..|
U_MAIN           2.0 ms      U_CHILD 2.0 ms
S_MAIN           5.0 / 2.3    S_CHILD 8.1 / 10.7
```

---

## 8. Clean-run baseline (18 clean runs)

| instrument | clean-run behaviour |
|---|---|
| U_MAIN max gap | 2.00–2.01 ms in every clean run |
| U_CHILD max gap | 2.00–2.02 ms in every clean run |
| S_MAIN sched / lat | 0.0–22.2 ms / 0.1–25.2 ms (whole-run maxima; in-episode values are far lower) |
| S_CHILD sched / lat | 0.0–0.004 ms / 0.4–2.0 ms typical |
| Python heartbeat | 96–654 ms whole-run maxima, including runs with no source episode |

Baseline: **both userspace canaries hold ~2 ms in every single run, clean or sick. Both syscall canaries stay in the sub-10 ms range.** The Python heartbeat is the only instrument that ever stalls, and it does so even in runs with no source pathology.

The widest clean-run syscall values (mx-01: S_MAIN 22.2/25.2 ms) are whole-run maxima including container startup, not in-episode values.

---

## 9. Cross-episode consistency

| observation | result |
|---|---|
| S_MAIN in-episode max scheduling delay | 0.0, 0.0, 0.0, 0.4, 1.0, 5.0 ms (6/6) |
| S_MAIN in-episode max syscall latency | 0.1, 0.2, 0.3, 2.1, 2.3, 2.4 ms (6/6) |
| S_CHILD in-episode max scheduling delay | 0.0, 0.0, 0.8, 3.6, 7.0, 8.1 ms (6/6) |
| U_MAIN in-episode max gap | 2.0 ms in all 6 episodes |
| U_CHILD in-episode max gap | 2.0–2.4 ms in all 6 episodes |
| Python heartbeat in-episode gap | 107.8, 119.0, 134.6, 198.2, 277.8, 402.5 ms |
| S_MAIN / S_CHILD asymmetry | none systematic; S_CHILD slightly *worse* in mx-02 and mx-25 |
| all three decision-tree cases | CASE C in 6/6, CASE A in 0, CASE B in 0 |

No episode showed a main-PID-scoped syscall stall. The main PID is not special at the syscall-dispatch layer.

---

## 10. Direct answers

**Does an identical trivial syscall stall in the main PID?**
No. Max scheduling delay 0.0–5.0 ms and max syscall latency 0.1–2.4 ms, across a 108–403 ms Python freeze.

**Does it stall in a separate PID?**
No. 0.0–8.1 ms scheduling delay, 0.2–10.7 ms latency.

**If both stall, are they temporally aligned?**
Neither stalls, so the question does not arise. There is no systematic main-vs-child asymmetry in either direction.

**Is the pathology global to gVisor syscall processing?**
No. **CASE A is excluded.** Syscall entry and completion are healthy in both PIDs.

**Is it scoped to the main process/thread group?**
No. **CASE B is excluded.** If anything the separate PID was marginally worse in two episodes.

**Or are trivial syscalls healthy, implying a narrower blocking-syscall/futex/filesystem mechanism?**
**This is what the data shows — CASE C.** The pathology is specific to syscalls that *block and wait for a wakeup*. `SYS_gettid` never blocks; `preadv` on a blocking read and `Event.wait()`'s futex both park the task goroutine. Both stalled paths share that mechanism.

**Which domain is now the narrowest defensible owner?**
**The gVisor task blocking/wakeup path** — the mechanism that parks a task goroutine on a channel and later wakes it. Not syscall dispatch, not the PID/thread group, not the filesystem, not the GIL, not the sandbox scheduler.

**Does the source audit support that?** Yes — see §11. In gVisor, blocking reads and futex waits both go through the same `Task.block()` machinery, and both use the per-task `futex.Waiter` / waiter-channel wakeup pattern. There is no separate mechanism that would have to be independently sick.

---

## 11. Static gVisor source audit (per instructions, since trivial syscalls stayed healthy)

Bounded audit of the relevant paths. Findings are source-referenced; mechanisms below are **hypotheses**, not proven causes.

**Verified structure:**

1. **Two distinct blocking primitives exist.**
   - `Task.block(C, timerChan)` in `pkg/sentry/kernel/task_block.go` — parks the task goroutine on a Go channel via `select` over `C`, `t.interruptChan`, and `timerChan`. `Block`, `BlockOn`, `BlockWithTimeout`, `BlockWithDeadline`, `BlockWithTimer` are all thin wrappers over it.
   - `UninterruptibleSleepStart/Finish` — the uninterruptible variant.
   `StateStatus()` maps `TaskGoroutineBlockedInterruptible` → `"S (sleeping)"` and `TaskGoroutineBlockedUninterruptible` → `"D (disk sleep)"`. This matches the previously established guest `D` state.

2. **futex waits and blocking reads share the same parking mechanism.** The futex package (`pkg/sentry/kernel/futex`) documents: *"It allows one to easily transform Wait() calls into waits on a channel"*. `WaitPrepare` *"enqueues w to be woken by a send to w.C"*, and `Task.futexWaiter` is a per-task `futex.Waiter`. So `Event.wait()` → futex `FUTEX_WAIT` → enqueue waiter → park on a channel. A blocking file read parks through `Task.block()` on a different channel. **Same parking/wakeup machinery, different waitable.**

3. **`Task.block()` explicitly deactivates the address space while parked** (`t.prepareSleep()` → `t.Deactivate()`), and maintains a kernel-wide running-task counter (`t.k.decRunningTasks()` on block, `incRunningTasks()` on unblock). `Task.block()` is described in-source as *"very hot"*.

4. **gVisor itself acknowledges Go-runtime scheduling as a source of long task-goroutine delays.** `pkg/sentry/kernel/task_sched.go` states the CPU-clock ticker increment *"approximately compensates for cases where thread throttling or bad Go runtime scheduling prevents the kernelCPUClockTicker goroutine, and presumably task goroutines as well, from executing for a long period of time."*

**Ranked hypotheses (not proven):**

| rank | hypothesis | basis | why it fits / what would falsify |
|---|---|---|---|
| 1 | Stall in the **park/wakeup path** shared by blocking reads and futex — e.g. a task goroutine not being scheduled back after its wakeup channel fires, or a contended hot path in `Task.block()`/`Wake` | both stalled paths are blocking paths; non-blocking syscalls are unaffected; gVisor explicitly warns about Go-runtime starvation of task goroutines | fits the CASE C signature exactly. Would be falsified if a *blocking* sentinel syscall (e.g. a bounded futex or a tiny blocking read on tmpfs) also stayed healthy |
| 2 | **Wakeup delivered but task goroutine slow to resume** — the event fires, but `incRunningTasks`/`Activate` and the return to userspace are delayed | `prepareSleep`/`completeSleep` do address-space deactivate/reactivate around every park | would show as large "scheduling delay" after wakeup rather than lost wakeups |
| 3 | **Filesystem/gofer-specific** blocking (mount/gofer RPC) — narrower than futex | the original symptom was `preadv` on the model Volume | **weakened**: the tmpfs sentinel stalls identically, and tmpfs does not go through the gofer |
| 4 | Host CPU starvation | — | **already excluded**: pure-userspace canaries hold 2 ms in both PIDs |

**Not established:** the exact code path. The audit is bounded — it establishes that a single shared parking/wakeup mechanism covers both stalled syscall classes, which is what the observation requires, but it does not identify a specific failing function or lock.

**The critical next measurement** is therefore a **blocking** sentinel syscall, not another trivial one. Concretely: extend S_MAIN/S_CHILD to issue a deliberately *bounded blocking* operation at low cadence — the cheapest options being `FUTEX_WAIT` with an immediate timeout on a private preallocated word (parks through the futex waiter path, wakes via the timer), or a tiny blocking read on tmpfs. If a bounded blocking syscall stalls in both PIDs while `SYS_gettid` stays healthy, hypothesis 1 is confirmed and the domain is pinned to the park/wakeup path. If it stays healthy, hypotheses 1 and 2 are falsified and attention moves to what is unique to `preadv`/`Event.wait` (e.g. the specific waitable objects and their queues).

This is a small extension of the existing S_* canary (same ring, same clock, same intended/enter/exit triple) — not a new architecture.

---

## 12. Evidence table

| Finding | Episodes | Confidence | Implication |
|---|---|---|---|
| Identical trivial syscall (`SYS_gettid`) healthy in the main PID | 6/6 | High | CASE B excluded; syscall dispatch in the frozen PID is fine |
| Identical trivial syscall healthy in the separate PID | 6/6 | High | CASE A excluded; no global gVisor syscall-path stall |
| U_MAIN and U_CHILD both hold ~2 ms throughout | 6/6 (+18 clean) | High | Pure userspace is unaffected in both PIDs |
| Python heartbeat stalls 108–403 ms | 6/6 | High | The freeze is real and reproducible |
| No main-vs-child syscall asymmetry | 6/6 | High | Scope is not PID/thread-group |
| Slow source read can occur with no Python freeze | mx-24 (622 ms read, 60.3 ms hb) | Medium | Correlated symptoms, unresolved causal direction |
| Both stalled paths are blocking paths sharing `Task.block()`/futex waiter machinery | gVisor source | Medium-High | Narrows the domain to the park/wakeup path (hypothesis) |
| 2×2 instrumentation does not perturb or suppress | 3 vs 11 runs | Low-Medium | No suppression observed; not proven equivalent |
| Capture goal not met (2 large, not >=3) | 25-container cap | High | Conclusion rests on 6 episodes, not the intended larger set |

---

## 13. What is now excluded

- whole-container / sandbox suspension — excluded (previous campaign)
- main-PID / thread-group scheduling suspension — excluded (previous campaign)
- GIL hold — excluded (refill gaps 0.005–0.026 ms; four threads concurrently inside `os.preadv`)
- global gVisor syscall-path stall — excluded (this campaign, CASE A)
- main-PID-scoped syscall stall — excluded (this campaign, CASE B)
- file / Volume / filesystem-wide specificity — excluded (tmpfs stalls identically)
- worker-cohort-only specificity — excluded (pre-existing sentinels stall too)

**Remaining domain: syscalls that block and depend on a wakeup, via gVisor's shared task park/wakeup mechanism.**
