# Bounded-Blocking Futex Canary — Does a Deliberately Bounded Futex Wake Late?

Diagnosis only. No Golden change, no geometry/QD/block-size/priming change, no hedging/retry, no tuning after campaign start, no follow-up campaign.

- Campaign: 11 fresh H100 containers (`fx-01..fx-11`) — goal met (3 large episodes + 7 clean), cap 25 not reached.
- Helper: `native_canary.c` → `/opt/native_canary.so` (gcc at image build).
- Engine: `comfymodal_runtime/source_race_oracle.py::run_sentinel_probe`
- App: `e04_source_race_modal.py::run_sentinel_h100` | Runner: `tools/run_sentinel_campaign.py`
- Analysis: `tools/analyze_futex.py` | Raw: `sentinel_runs/fx-*.json`, `sentinel_runs/{campaign_fx.log,fx_analysis.txt}`, smoke `sentinel_runs/fx-on-*.json`

---

## 1. Executive summary

**YES — a deliberately bounded futex wakes hundreds of milliseconds to seconds late, and only in the main PID. This is CASE 2.**

| run | worst source read | workers | Python hb | S_main lat | **B_MAIN excess wake** | S_child lat | **B_CHILD excess wake** |
|---|---|---|---|---|---|---|---|
| fx-03 | 277 ms | 0,1,3 | 276 ms | 7 ms | **135 ms** | 5 ms | **24 ms** |
| fx-05 | 1296 ms | 0,1,2,3 | 1103 ms | 1 ms | **1163 ms** | 1 ms | **2 ms** |
| fx-10 | 1980 ms | 0,3 | 1953 ms | 1 ms | **1952 ms** | 1 ms | **2 ms** |
| fx-11 | 629 ms | 0,1,2,3 | 403 ms | 7 ms | **470 ms** | 2 ms | **2 ms** |

Plus the smoke runs (which also carried the full topology): B_MAIN excess **3513 / 567 / 2418 ms** vs B_CHILD excess **2.7 / 3.4 / 1.9 ms** with identical timeout, identical syscall, identical cadence.

The decisive shape of a single worst tick (fx-05):

```
B_MAIN : enter t=2245ms   expected wake at +2.0 ms   actual exit t=3409ms   blocking=1165 ms
         retval=-1  errno=110 (ETIMEDOUT)            ticks in episode = 80
B_CHILD: enter t=2451ms   expected wake at +2.0 ms   actual exit t=2455ms   blocking=   4 ms
         retval=-1  errno=110 (ETIMEDOUT)            ticks in episode = 623
```

The futex **entered on schedule** (scheduling delay is 1–7 ms) and **parked normally**; the **timeout wake itself arrived late**. errno 110 confirms it was woken by the timeout — not by any storage completion, another Python thread, or any application wakeup. This isolates the failure to **park → timer fires → resume**.

**This refines the previous campaign's CASE C.** CASE C established that syscall *dispatch* is healthy (trivial `SYS_gettid` fine in both PIDs). This campaign shows that a *blocking* syscall is sick — and that the sickness is **scoped to the main PID/thread group**, not global. So the correct statement is not "gVisor's park/wakeup path is broken" but:

> **The main process's task park/wakeup state is pathological. An identical bounded blocking futex in a separate PID in the same container wakes on time.**

**Causality note (important):** late main-PID futex occurred in **clean source runs too** — fx-02 (293 ms excess) and fx-04 (340 ms excess) had no source episode ≥250 ms. Conversely, **no** large source episode occurred with a healthy main-PID futex. So the park/wakeup pathology is the broader, more sensitive signal, and the source `preadv` slowdown is a co-symptom rather than the cause. The causal direction is still not proven, but the asymmetry is informative.

**Perturbation caveat, stated plainly:** the futex canary adds a blocking syscall every ~2 ms *inside the main PID* — the very domain under investigation. The smoke produced 3/3 large episodes (vs arm A's 3/11), which is a possible worsening. The 11-run campaign itself produced 3 large / 7 clean, comparable to previous campaigns. I did **not** tune the timeout to compensate. Treat "the instrument may amplify the phenomenon" as an open concern, not a resolved one.

---

## 2. B_MAIN / B_CHILD implementation

Added to `native_canary.c` as a third canary kind, alongside U_* (pure userspace) and S_* (`SYS_gettid`):

- one native pthread per process, created before any source worker thread
- no Python C-API, no GIL, no callbacks, no logging, no `malloc`/`free`, no file I/O, no locks shared with Python
- records `(intended_ns, enter_ns, exit_ns, retval, errno, timeout_ns)` — 48 bytes — into a preallocated anonymous `mmap` (capacity 50 000 ≈ 100 s at 2 ms)
- cadence is established by the futex timeout itself (no sleep/nanosleep/Event used for pacing)
- B_MAIN and B_CHILD are identical in syscall number, timeout, clock, ring format and timestamp semantics; the only intended difference is PID/thread-group identity

Per-iteration metrics:
```
scheduling_delay    = enter  - intended
blocking_duration   = exit   - enter
excess_wakeup_delay = blocking_duration - configured_timeout     <-- KEY METRIC
```

Process-level state is isolated per slot (`g_user`, `g_sys`, `g_futex`), and each process runs its own two/three canaries on its own rings. Rings are created before `fork`, so the parent collects the child's after `waitpid`.

---

## 3. Futex syscall arguments and timeout semantics

```c
ts.tv_sec  = 0;
ts.tv_nsec = 2 * 1000000;                       /* 2 ms, fixed for the campaign */
syscall(SYS_futex, &g_futex_word,               /* private, preallocated, never modified */
        FUTEX_WAIT_PRIVATE,                     /* 128 = FUTEX_WAIT(0) | FUTEX_PRIVATE_FLAG */
        (int32_t)0,                             /* expected value at word */
        &ts,                                    /* relative timeout */
        (void *)0, (int32_t)0);
```

`g_futex_word` stays 0 forever and nothing ever calls `FUTEX_WAKE` on it, so the **only** possible wake is the timeout. Expected return is `-1` with `errno = ETIMEDOUT (110)` — observed in every worst tick above, confirming the timeout path was exercised rather than an external wake.

Because the wake depends on nothing but the timer, a late return cannot be attributed to storage completion, another Python thread, or any application-level wakeup. That is precisely why this is strong evidence about park/resume machinery.

Configured timeout was fixed at 2 ms for the smoke and the whole campaign and **not** adjusted after seeing outcomes.

---

## 4. PID / TID topology

| run | python pid | U_MAIN | S_MAIN | **B_MAIN** | worker TIDs | child pid | U_CHILD | S_CHILD | **B_CHILD** |
|---|---|---|---|---|---|---|---|---|---|
| fx-on-1 | 2 | pid 2 tid 8 | pid 2 tid 9 | **pid 2** | 18,19,20,21 | 7 | pid 7 tid 11 | pid 7 tid 13 | **pid 7** |
| fx-on-2 | 2 | pid 2 tid 8 | pid 2 tid 9 | **pid 2** | 18,19,20,21 | 7 | pid 7 tid 12 | pid 7 tid 14 | **pid 7** |
| fx-on-3 | 2 | pid 2 tid 8 | pid 2 tid 9 | **pid 2** | 18,19,20,21 | 7 | pid 7 tid 13 | pid 7 tid 14 | **pid 7** |

B_MAIN is in the Python PID (2) with all four source workers; B_CHILD is outside it (7). All canaries have distinct TIDs. No canary is a disguised subprocess.

Clock/syscall separation re-confirmed in these runs: `CLOCK_MONOTONIC` 37.0–51.7 ns/call vs `SYS_gettid` 4216–4965 ns/call (~85–115x), so the pacing clock is vDSO and the control syscall is real.

---

## 5. Perturbation validation

| arm | n | median gbps | median refill gap | max refill gap | sick >=500 | clean <250 | QD balanced |
|---|---|---|---|---|---|---|---|
| A (2×2 only) | 11 | 4.24 | 0.010 ms | 26.3 ms | 3 | 5 | True |
| B (2×2 + B_MAIN/B_CHILD) | 3 | 1.38 | 0.009 ms | 0.1 ms | 3 | 0 | True |

- **QD balanced** in every run (`{0:30, 1:30, 2:30, 3:30}`).
- **Refill gaps unchanged** (0.009 vs 0.010 ms median; max far better in arm B).
- **Source pathology remains observable** — indeed arm B was 3/3 large.
- **Futex timeout behaves normally in healthy runs**: clean-run B_MAIN excess is 50–94 ms in most runs (fx-01, fx-06..fx-09) and B_CHILD 1.3–15.1 ms; the 2 ms timeout returns in ~2–4 ms in the child essentially always (e.g. fx-05: 623 ticks, worst 4 ms).
- **Rate**: ~600 ticks per run in the child; fewer in the main PID when it is frozen (fx-05: 80, fx-10: 57) — itself a symptom, since a blocked waiter cannot reissue.

**Open concern:** arm B's 3/3 large rate in the smoke may indicate the main-PID futex canary amplifies the pathology, since it adds blocking syscalls in the affected domain. Not resolved; flagged rather than hidden.

---

## 6. Healthy baseline

| instrument | healthy behaviour |
|---|---|
| S_MAIN / S_CHILD `SYS_gettid` | 0.0–7 ms latency in-episode; sub-10 ms typical whole-run |
| **B_MAIN bounded futex** | 2 ms timeout returns in ~2 ms normally; clean-run maxima 50–94 ms (whole-run, includes startup) |
| **B_CHILD bounded futex** | ~2–4 ms essentially always; worst clean-run whole-run value 15.1 ms |
| U_MAIN / U_CHILD | 2.0–3.8 ms max gap in every run |

Baseline for the bounded futex is **≈2–4 ms** in the child and typically the same in the main PID, with occasional tens-of-ms excursions during container startup. The pathological values (135–3513 ms) are 30–1700x baseline.

---

## 7. Per-run table

| run | region | worst src | workers | py hb | S_main lat | **B_MAIN excess** | S_child lat | **B_CHILD excess** | classification |
|---|---|---|---|---|---|---|---|---|---|
| fx-01 | OCI/us-chicago-1 | 224 | – | – | – | (whole-run 95) | – | (whole-run 2) | CLEAN |
| fx-02 | GCP/us-east | 243 | – | – | – | (whole-run **293**) | – | (whole-run 4) | CLEAN **but late main futex** |
| fx-03 | GCP/northamerica-northeast2 | 277 | 0,1,3 | 276 | 7 | **135** | 5 | 24 | **CASE 2** |
| fx-04 | GCP/us-east4 | 219 | – | – | – | (whole-run **340**) | – | (whole-run 3) | CLEAN **but late main futex** |
| fx-05 | GCP/us-east | **1296** | 0,1,2,3 | 1103 | 1 | **1163** | 1 | **2** | **CASE 2** |
| fx-06 | UNSPECIFIED/london | 119 | – | – | – | (whole-run 53) | – | (whole-run 15) | CLEAN |
| fx-07 | OCI/us-chicago-1 | 152 | – | – | – | (whole-run 51) | – | (whole-run 1) | CLEAN |
| fx-08 | GCP/us-west | 160 | – | – | – | (whole-run 55) | – | (whole-run 2) | CLEAN |
| fx-09 | GCP/us-east4 | 150 | – | – | – | (whole-run 61) | – | (whole-run 1) | CLEAN |
| fx-10 | UNSPECIFIED/CANADA-2 | **1980** | 0,3 | 1953 | 1 | **1952** | 1 | **2** | **CASE 2** |
| fx-11 | GCP/asia-south2 | **629** | 0,1,2,3 | 403 | 7 | **470** | 2 | **2** | **CASE 2** |

CASE 1 (both PIDs late): **0 episodes.** CASE 3 (both healthy): **0 episodes.** CASE 2: **4 campaign episodes + 3 smoke episodes.**

---

## 8. Timelines for >=500 ms episodes

### fx-10 — 1980 ms source episode, workers 0 and 3

```
SOURCE (pid 2)
 w0,w3  |================ 1980 ms ================|

PYTHON HEARTBEAT (pid 2)          |........ 1953 ms GAP ........|

U_MAIN   (pid 2, no syscalls)     tick tick tick ... max gap 2.0 ms
S_MAIN   (pid 2, SYS_gettid)      latency 1 ms
B_MAIN   (pid 2, FUTEX_WAIT 2ms)
         enter t=5567   expected wake t=5569   |......... exits t=7522 .........|
         blocking = 1954 ms   errno=110 (ETIMEDOUT)   ticks in episode = 57

U_CHILD  (pid 7, no syscalls)     tick tick tick ... max gap 2.3 ms
S_CHILD  (pid 7, SYS_gettid)      latency 1 ms
B_CHILD  (pid 7, FUTEX_WAIT 2ms)
         enter t=6933   expected wake t=6935   exits t=6937
         blocking = 4 ms      errno=110 (ETIMEDOUT)   ticks in episode = 934
```

### fx-05 — 1296 ms source episode, all four workers

```
SOURCE (pid 2)                    |========== 1296 ms ==========|
PYTHON HEARTBEAT                  |........ 1103 ms GAP ........|
U_MAIN   max gap 2.0 ms           S_MAIN latency 1 ms
B_MAIN   enter t=2245  expected wake +2.0 ms  |...... exits t=3409 ......|
         blocking = 1165 ms  errno=110   ticks=80
U_CHILD  max gap 2.3 ms           S_CHILD latency 1 ms
B_CHILD  enter t=2451  expected wake +2.0 ms  exits t=2455  blocking = 4 ms
         errno=110   ticks=623
```

### fx-11 — 629 ms source episode, all four workers

```
SOURCE (pid 2)          |==== 629 ms ====|
PYTHON HEARTBEAT        |.. 403 ms GAP ..|
B_MAIN  blocking = 472 ms (expected 2 ms)   errno=110   ticks=88
B_CHILD blocking =   4 ms (expected 2 ms)   errno=110   ticks=319
U_MAIN / U_CHILD max gap 2.0 / 2.3 ms   S_MAIN / S_CHILD latency 7 / 2 ms
```

### fx-03 — 277 ms source episode, workers 0,1,3 (smallest case)

```
SOURCE                  |== 277 ms ==|
PYTHON HEARTBEAT        |  276 ms GAP |
B_MAIN  blocking = 135 ms (expected 2 ms)  errno=110
B_CHILD blocking =  24 ms (expected 2 ms)  errno=110
```

Note the tight coupling in every case: **B_MAIN excess ≈ Python heartbeat gap ≈ source worst read**, all within a few percent.

---

## 9. Pathology without source pathology, and vice versa

**Late main-PID futex WITHOUT source pathology (category C):**
- **fx-02** — 293 ms main-PID futex excess, source worst only 243 ms
- **fx-04** — 340 ms main-PID futex excess, source worst only 219 ms

**Large source pathology WITHOUT late futex:**
- **none.** Every ≥500 ms source episode had a late main-PID futex.

So in this sample the park/wakeup pathology is a **superset** of the source pathology: it can occur alone, but the source episode never occurred alone. That asymmetry is the strongest causal hint in the campaign — and it points away from "slow preadv causes the freeze".

**Futex pathology in the child PID:** essentially none. Worst B_CHILD excess across all runs is 24 ms (fx-03) against a 2 ms configured timeout; every other run is 1–4 ms.

---

## 10. Cross-PID temporal alignment

Comparing the worst ticks in the same episode:

| run | B_MAIN enter | B_MAIN actual exit | B_CHILD enter | B_CHILD actual exit | exit difference |
|---|---|---|---|---|---|
| fx-05 | t=2245 | t=3409 | t=2451 | t=2455 | 954 ms |
| fx-10 | t=5567 | t=7522 | t=6933 | t=6937 | 585 ms |
| fx-11 | t=4965 | t=5437 | t=5507 | t=5512 | −75 ms |

The two waiters have **different expected wake times** (they are independently scheduled, seconds apart) and their **actual exits are not aligned** — the child simply never enters the pathological state. There is no shared delayed-release event spanning both PIDs; the failure is confined to the main PID's waiter.

This is the key negative result for CASE 1: had a single Sentry-global wakeup mechanism been delayed, both waiters would have resumed together regardless of their independent timers. They did not.

---

## 11. Direct answers

**Does a bounded blocking futex wake late during the sickness?**
Yes, in the main PID — up to 1954 ms for a 2 ms timeout (fx-10), and 3513 ms in a smoke run. errno=110 confirms the timeout fired; only the *return* was late.

**Does it happen in the main PID?** Yes — 4/4 campaign episodes and 3/3 smoke episodes.

**Does it happen in the child PID?** No. Worst child excess across the whole campaign is 24 ms; typical 1–4 ms, i.e. at the configured timeout.

**Are late wakes temporally aligned across PIDs?**
No — the child never stalls, so there is no shared release instant. Expected wake times differ and actual exits differ by 75–954 ms. A shared Sentry-global delayed wake is excluded.

**Does `SYS_gettid` remain healthy simultaneously?**
Yes. S_main latency 1–7 ms and S_child 1–5 ms *during the same episodes* in which the main-PID futex was 135–1952 ms late. So within one process: **non-blocking syscall healthy, blocking syscall sick.**

**Is the pathology generic to task park/wakeup?**
No — not generic. It is **not** global to the container (the child PID is healthy) and **not** generic to syscall dispatch (both PIDs healthy). It is generic only *within the main process's blocking waiters*.

**Or is it narrower than that?**
Narrower in scope (main PID only) but broader in *class* within that process: the main PID's bounded futex and its `Event.wait` futex and its blocking `preadv` all stall together, while its non-blocking syscalls do not.

**Is source-read sickness always coupled to park/wakeup sickness?**
No — the coupling is one-directional in this sample. Park/wakeup sickness occurred alone (fx-02, fx-04); source sickness never occurred alone. So source-read sickness appears to be a *consequence or co-symptom* of the park/wakeup state, not its cause.

**What is the narrowest defensible owner/state domain now?**
**The main process's (thread group's) blocking task state in gVisor** — the park/wakeup bookkeeping for waiters belonging to that task set. Not the container, not syscall dispatch, not the filesystem, not the GIL, not the sandbox scheduler, and not the Sentry globally.

**What is the SINGLE best next diagnostic or audit?**
A **static gVisor source audit of the per-task-set blocking path**, comparing what is *per-thread-group* versus *global* in the park/wakeup machinery — specifically `Task.block()` / `BlockWithTimeout` / `BlockWithDeadline`, `blockingTimer` and its channel, `interruptChan`, `prepareSleep`/`completeSleep` (address-space deactivate/reactivate), the running-task counters (`incRunningTasks`/`decRunningTasks`), and where the Go runtime is entered/exited around them. The question to answer: **what in that path is keyed to the task set, such that one thread group's waiters resume late while another thread group's identical waiter resumes on time?**

No further campaign is needed to establish the scope; the scope is now the finding.

---

## 12. Evidence table

| Finding | Episodes | Confidence | Implication |
|---|---|---|---|
| Bounded futex wakes late in the MAIN PID | 4/4 campaign + 3/3 smoke | High | Park/wakeup pathology confirmed and reproducible |
| Identical futex healthy in the CHILD PID | 7/7 | High | CASE 1 excluded — not Sentry-global |
| `SYS_gettid` healthy in both PIDs simultaneously | 7/7 | High | Not syscall-dispatch; blocking-specific |
| Late wake with errno=110 (ETIMEDOUT) | all worst ticks | High | Entered and parked normally; only the timeout return was late |
| Scheduling delay small (1–7 ms) while excess wake is huge | 4/4 | High | Failure is in resume-after-timer, not in reaching the syscall |
| B_MAIN excess ≈ Python hb gap ≈ source worst read | 4/4 | High | One shared freeze event within the main process |
| Late main futex in clean source runs | fx-02, fx-04 | Medium | Park/wakeup sickness can precede/exist without source sickness |
| No large source episode with healthy main futex | 4/4 | Medium | Source sickness appears downstream of park/wakeup state |
| No cross-PID exit alignment | 3/3 compared | High | No shared delayed-release event |
| Futex canary may amplify pathology | smoke 3/3 vs arm A 3/11 | Low | Open perturbation concern, not resolved |
