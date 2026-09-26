# Same-PID Native Pthread Canary — GIL vs Thread-Group Scheduling

Diagnosis only. No Golden change, no QD/block-size/priming change, no retries/hedging, no follow-up experiment run.

- Campaign: 11 fresh H100 containers (`ncr-01..ncr-11`), stopped at 3 large episodes + 5 clean runs (cap 25).
- Native helper: `native_canary.c` → `/opt/native_canary.so` (compiled at image build with gcc).
- Engine: `comfymodal_runtime/source_race_oracle.py::run_sentinel_probe` (`native_canary=True`)
- App: `e04_source_race_modal.py::run_sentinel_h100`
- Runner: `tools/run_sentinel_campaign.py`
- Analysis: `tools/analyze_sentinel.py`, `tools/analyze_gil_vs_syscall.py`
- Raw: `sentinel_runs/ncr-*.json`, `sentinel_runs/{campaign_nc.log,nc_analysis.txt,gil_vs_syscall.txt}`, smoke `sentinel_runs/nc-on-*.json`

---

## 1. Executive summary

**The binary question is answered: native code in the SAME PID keeps executing while Python freezes. The main PID is NOT being descheduled.**

Across all 6 Python-freeze episodes the same-PID native pthread never exceeded a **6.70 ms** gap while the Python heartbeat stalled **111–508 ms**:

| run | worst source read | Python heartbeat | **same-PID native pthread** | separate-PID canary |
|---|---|---|---|---|
| ncr-01 | 596 ms | 502 ms | **2.00 ms** | 2.01 ms |
| ncr-02 | 285 ms | 111 ms | **2.00 ms** | 2.01 ms |
| ncr-08 | 297 ms | 217 ms | **2.00 ms** | 2.77 ms |
| ncr-09 | 336 ms | 334 ms | **2.00 ms** | 2.46 ms |
| ncr-10 | 718 ms | 508 ms | **6.70 ms** | 2.10 ms |
| ncr-11 | 534 ms | 350 ms | **2.65 ms** | 2.21 ms |

By the stated decision tree this is **CASE 1**. Thread-group/PID-wide scheduling suspension is excluded (CASE 2), and an all-three freeze is excluded (CASE 3).

**However, the evidence does NOT support the GIL explanation for CASE 1, and this is the most important finding of the campaign.**

Two independent results from the same runs:

1. **The GIL was free throughout the freeze.** A worker that had just spent **596 ms inside `os.preadv`** re-entered its next `os.preadv` **0.012 ms** later, having executed its Python loop bookkeeping (list/dict writes, lock acquire, two clock reads) in that interval. Across the three large episodes the refill gap immediately after a sick read was **0.005–0.026 ms**. A thread holding the GIL for 500 ms would have made that impossible.

2. **`os.preadv` demonstrably releases the GIL.** In ncr-01, **four distinct Python threads were simultaneously inside `os.preadv` for a 502.2 ms overlap window** (all four entered within 0.1 ms and exited at ~502 ms). With the GIL held across the call this is impossible — CPython would serialize them.

So the correct statement is narrower than "CPython/GIL-domain freeze":

> **The main PID is schedulable and native execution continues. Every thread that stalled was inside a gVisor syscall; every thread that stayed healthy makes no syscalls in steady state.**

- workers stalled **inside `os.preadv`** (refill gaps ~0.01 ms prove they were not blocked between syscalls)
- Python heartbeat and all three sentinels stalled in `threading.Event.wait()` — a **futex** syscall returning late
- same-PID native pthread: pure userspace, **zero syscalls** → unaffected
- separate-PID canary: pure userspace, **zero syscalls** → unaffected

The common factor is not Python and not the GIL — it is **syscall participation**. The narrowest defensible domain is therefore **the gVisor syscall path**, not CPython/GIL.

**Important limitation:** both healthy canaries are syscall-free *by construction*, so this experiment cannot tell whether a syscall issued from a *different* process would also stall. Every syscall-making thread we instrumented lives in the main process.

---

## 2. Native canary implementation

`native_canary.c` — one pthread created inside the calling process:

- **No Python C-API**, no `PyGILState_Ensure`, no callbacks, no logging.
- **No I/O, no `malloc`/`free`, no locks, no condition variables** in the steady-state loop.
- Ring allocated by the caller (Python `mmap.mmap(-1, ...)`, anonymous) and handed in at `nc_start()`; Python touches it only before start and after stop.
- Timing primitive: **`clock_gettime(CLOCK_MONOTONIC)`** — no blocking syscall per tick.
- Pacing: **busy-spin** (never blocks, so a wall gap can only mean "not scheduled").
- Records `(monotonic ns, sequence)` every ~2 ms; capacity 200 000 records (~400 s) so the run cannot overflow; `overflow` flag recorded regardless.

Layout: 128-byte header (`stop`, `count`, `overflow`, `capacity`, `tid`, `pid`, `cadence_ns`, `started`) then int64 `[ts, seq]` pairs.

Exported API: `nc_start(base, capacity, cadence_ns)`, `nc_stop()`, `nc_count/overflow/tid/pid/self_pid/self_tid`, `nc_calibrate_monotonic_ns(iters)`, `nc_calibrate_syscall_ns(iters)`.

Build (image, `debian_slim` python 3.11):
```
apt_install("gcc", "libc6-dev")
add_local_file("native_canary.c", "/root/native_canary.c")
run_commands("gcc -O2 -fPIC -shared -o /opt/native_canary.so /root/native_canary.c -lpthread",
             "test -f /opt/native_canary.so")
```
Loaded via `ctypes.CDLL("/opt/native_canary.so")`. `ctypes.CDLL` releases the GIL for the duration of each foreign call, and the pthread never re-enters Python.

**One CPU is busy-spun for the duration of each run** (12 declared CPUs). This is stated explicitly, not hidden.

Ordering (nothing is created in response to sickness): identities → tmpfs file → sentinel FDs + buffers → mmap + separate-PID `fork` canary → **native pthread canary** → heartbeat + sentinel threads → worker buffers + FDs → worker threads, `settle_ms=0`.

---

## 3. Clock validation

Measured in-container, native C (`nc_calibrate_*`, 20 000 iterations):

| run | `clock_gettime(CLOCK_MONOTONIC)` | `getpid()` (indisputable syscall) | ratio |
|---|---|---|---|
| nc-on-1 | 18.6 ns/call | 2444.9 ns/call | 131x |
| nc-on-2 | 37.3 ns/call | 2411.1 ns/call | 65x |
| nc-on-3 | 36.9 ns/call | 2096.7 ns/call | 57x |

The native clock path is **57–131x faster than a known syscall → consistent with vDSO / userspace-fast**, not a syscall. The canary therefore does not depend on a blocking syscall for each tick. Python-side calibration from the previous campaign agrees (`perf_counter_ns` 60.1 ns/op vs `getpid` 1224.8 ns/op).

`process_time_ns` was not used anywhere in this campaign's reasoning, per the previous result that it is unusable here.

---

## 4. PID/TID topology proof

The same-PID canary is genuinely a pthread of the source process, not a subprocess:

| run | native pid | Python pid | native TID | worker TIDs | main TID |
|---|---|---|---|---|---|
| nc-on-1 | **2** | **2** | 7 | 12, 13, 14, 15 | 6 |
| nc-on-2 | **2** | **2** | 7 | 12, 13, 14, 15 | 6 |
| nc-on-3 | **2** | **2** | 7 | 12, 13, 14, 15 | 6 |

`native_pid == python_pid` in every run, with a distinct TID (7) from all four worker threads (12–15) and the main thread (6). The separate-PID canary is a distinct `fork()`ed PID. Confirmed: same PID/thread group, distinct thread.

---

## 5. Perturbation validation

Arm A = the 11 already-captured runs from the previous campaign (same topology, native canary absent). Arm B = 3 runs with the native pthread added.

| arm | n | median gbps | median refill gap | max refill gap | sick >=500 ms | clean <250 ms | QD balanced |
|---|---|---|---|---|---|---|---|
| A native OFF | 11 | 4.24 | 0.010 ms | 26.3 ms | 3 | 5 | True |
| B native ON | 3 | 3.48 | 0.010 ms | 0.0 ms | 1 | 0 | True |

- **QD remains correct**: per-worker reads exactly `{0:30, 1:30, 2:30, 3:30}`, balanced in all runs.
- **Refill gaps effectively unchanged**: identical median (0.010 ms), and arm B's max (0.0 ms) is better than arm A's single 26.3 ms outlier.
- **Throughput not obviously destroyed**: arm B's median is lower only because its 3 runs contain 1 sick run and 0 clean runs — the same pathology-confound as before. Nothing suggests the native thread costs throughput.
- **Pathology still observable**: yes — the smoke's third run was already a 507 ms episode, and the campaign captured 3 large + 3 intermediate + 5 clean.

**Does adding the native pthread suppress the phenomenon?** No evidence of suppression. Rate comparison is weak (3 vs 11 runs), so this is reported as "no suppression observed", not proven equivalence. The native thread busy-spins one CPU; that is the one uncontrolled cost.

---

## 6. Per-run table

In-episode values (restricted to the worst source episode).

| run | region | worst src read | affected workers | Python hb in-ep | **same-PID native in-ep** | sep-PID in-ep | A sched/lat | B sched/lat | C sched/lat | classification |
|---|---|---|---|---|---|---|---|---|---|---|
| ncr-01 | GCP/us-east4 | **596** | 0,1,2,3 | 502 | **2.00** | 2.01 | 499/19.8 | 499/309.4 | 499/20.1 | CASE 1 |
| ncr-02 | GCP/us-east4 | 285 | 2 | 111 | **2.00** | 2.01 | 162/19.9 | 182/21.1 | 163/41.0 | CASE 1 |
| ncr-03 | GCP/us-east | 208 | – | – | – | – | – | – | – | CLEAN |
| ncr-04 | GCP/us-west | 208 | – | – | – | – | – | – | – | CLEAN |
| ncr-05 | GCP/us-east4 | 245 | – | – | – | – | – | – | – | CLEAN |
| ncr-06 | GCP/us-east5 | 212 | – | – | – | – | – | – | – | CLEAN |
| ncr-07 | GCP/europe-west2 | 177 | – | – | – | – | – | – | – | CLEAN |
| ncr-08 | GCP/us-east | 297 | 2 | 217 | **2.00** | 2.77 | 210/21.8 | 209/21.9 | 215/24.1 | CASE 1 |
| ncr-09 | GCP/us-west | 336 | 0,1,2,3 | 334 | **2.00** | 2.46 | 324/18.4 | 334/18.4 | 313/17.3 | CASE 1 |
| ncr-10 | GCP/us-west | **718** | 0,1,2,3 | 508 | **6.70** | 2.10 | 484/0.7 | 508/0.4 | 483/0.6 | CASE 1 |
| ncr-11 | GCP/us-west | **534** | 0,1,2,3 | 350 | **2.65** | 2.21 | 433/126.3 | 402/457.6 | 395/126.2 | CASE 1 |

`sched/lat` = sentinel scheduling delay / syscall latency, ms.

---

## 7. Timelines for the >=500 ms episodes

### ncr-01 — 596 ms, all four workers, 502.2 ms of true 4-thread preadv overlap

```
SOURCE (Python, same PID)
 w3 |================== 502.7 ms ==================|
 w2 |================== 502.4 ms ==================|
 w0 |================== 502.2 ms ==================|
 w1 |======================= 595.7 ms =======================|
    enter 0.0-0.1 ms, exit 502-596 ms

PYTHON HEARTBEAT (needs GIL + futex)
    |............. 501.7 ms GAP .............|

SAME-PID NATIVE PTHREAD (no GIL, no syscalls)
    tick tick tick tick tick tick tick tick tick        max gap 2.00 ms

SEPARATE-PID CANARY (no GIL of this process, no syscalls)
    tick tick tick tick tick tick tick tick tick        max gap 2.01 ms

SENTINELS (need GIL + futex, then preadv)
 A model file        sched 499.3 ms | read 19.8 ms
 B other Volume file sched 499.1 ms | read 309.4 ms
 C tmpfs             sched 498.9 ms | read 20.1 ms

AFTER THE WORST READ: next preadv entered 0.012 ms later  <- GIL was free
```

### ncr-10 — 718 ms, all four workers, 523.4 ms overlap

```
SOURCE
 w3 gen4 |================ 717.5 ms ================|
 w2 gen7        |============ 555.6 ms ============|
 w0 gen7          |=========== 546.9 ms ==========|
 w1 gen7            |========== 524.0 ms =========|
    all four inside preadv simultaneously for 523.4 ms

PYTHON HEARTBEAT    |........ 508.1 ms GAP ........|
SAME-PID NATIVE     tick tick tick ... max gap 6.70 ms
SEPARATE-PID        tick tick tick ... max gap 2.10 ms
 A 484.3/0.7   B 508.3/0.4   C 483.4/0.6   (sched/lat ms)
AFTER THE WORST READ: next preadv entered 0.026 ms later
```

### ncr-11 — 534 ms, all four workers, 406.7 ms overlap

```
SOURCE
 w3 gen0 |============ 406.9 ms ============|
 w2 gen0 |================ 533.0 ms ================|
 w0 gen0 |============== 467.7 ms ==============|
 w1 gen0 |================ 533.6 ms ================|

PYTHON HEARTBEAT    |...... 349.6 ms GAP ......|
SAME-PID NATIVE     tick tick tick ... max gap 2.65 ms
SEPARATE-PID        tick tick tick ... max gap 2.21 ms
 A 433.5/126.3   B 402.4/457.6   C 395.0/126.2
AFTER THE WORST READ: next preadv entered 0.005 ms later
```

---

## 8. Clean-run baseline

| mechanism | clean-run max gap |
|---|---|
| Python heartbeat | 149.2 / 151.3 / 178.9 / 350.2 / 471.4 ms (ncr-03..07) |
| same-PID native pthread | 2.00–2.76 ms (campaign), 2.03–2.76 ms (smoke) |
| separate-PID canary | 2.09–8.05 ms |
| sentinel A/B/C median scheduling delay | 0.29–0.64 ms (previous campaign baseline) |
| sentinel A/B/C median syscall latency | 0.12–0.18 ms |

The native pthread and separate-PID canary hold a ~2 ms cadence in **every** run, clean or sick. The Python heartbeat is the only mechanism that ever stalls — and note ncr-04 shows a 471.4 ms heartbeat gap in a run with **no source episode at all**, i.e. the freeze can occur without a large source stall.

---

## 9. Cross-episode consistency

| observation | across episodes |
|---|---|
| native pthread in-episode gap | 2.00, 2.00, 2.00, 2.00, 6.70, 2.65 ms (6/6) |
| separate-PID in-episode gap | 2.01, 2.01, 2.77, 2.46, 2.10, 2.21 ms (6/6) |
| Python heartbeat in-episode gap | 111, 217, 334, 350, 502, 508 ms (6/6) |
| native gap / Python gap ratio | 0.004 – 0.020 |
| all three sentinels freeze together | 6/6 |
| tmpfs freezes with the model file | 6/6 |
| refill gap after a sick read | 0.005 / 0.012 / 0.026 ms |
| 4 threads simultaneously inside preadv | 3/3 large episodes (502.2 / 523.4 / 406.7 ms) |
| native pthread whole-run max gap | 2.00–6.70 ms in all 14 native-enabled runs |

The native pthread never showed a gap larger than 6.70 ms in any of the 14 native-enabled runs (3 smoke + 11 campaign).

---

## 10. Evidence table

| Finding | Episodes | Confidence | Implication |
|---|---|---|---|
| Same-PID native pthread keeps running while Python freezes | 6/6 Python-freeze episodes (2.00–6.70 ms vs 111–508 ms) | High | The main PID is schedulable. CASE 2 and CASE 3 excluded. |
| Native pthread is in the same PID as the workers | 14/14 native runs (`native_pid == python_pid`, distinct TID) | High | The discriminator is valid; not a disguised subprocess. |
| Native clock is vDSO-fast (18.6–37.3 ns/call vs getpid 2097–2445 ns/call) | 3/3 calibrated runs | High | Canary does not depend on a syscall per tick. |
| **The GIL was free during the freeze** (refill gap 0.005–0.026 ms after a 500+ ms read) | 3/3 large episodes | High | A GIL-hold explanation is **contradicted**, not supported. |
| **`os.preadv` releases the GIL** (4 threads simultaneously inside it for 406–523 ms) | 3/3 large episodes | High | Runtime proof, independent of source reading. |
| All stalled threads were inside syscalls; all healthy threads make none | 6/6 | High | The common factor is syscall participation, not Python. |
| Sentinels stall in `Event.wait()` (futex), workers stall in `preadv` | 6/6 | Medium-High | Two different syscalls stall together — consistent with a shared syscall path. |
| Freeze can occur with no large source episode | ncr-04 (471 ms heartbeat gap, no episode) | Medium | The freeze is not caused by the source stall; they are correlated symptoms. |
| Adding the native pthread does not suppress pathology | arm A vs B | Low-Medium (3 vs 11 runs) | No suppression observed; not proven equivalent. |

---

## 11. Direct answers

**Does native code in the SAME PID continue executing while Python freezes?**
Yes, unambiguously. 2.00–6.70 ms max gap versus 111–508 ms of Python freeze, in 6/6 episodes and in all 14 native-enabled runs.

**Is the main PID actually being descheduled?**
No. A pthread of that very PID held a 2 ms cadence throughout. Thread-group/PID-wide suspension is excluded.

**Is the freeze specifically Python/CPython execution?**
Not in the sense of the GIL. Every Python thread that stalled was **inside a syscall** (`preadv` for workers, futex for heartbeat/sentinels), and the GIL was demonstrably free. "Python execution" and "syscall participation" are confounded in this process because the Python threads are exactly the syscall-issuing threads.

**Does the separate PID still reproduce as healthy?**
Yes — 2.01–2.77 ms in-episode gaps, consistent with the previous campaign.

**Which classification fits?**
**CASE 1** by the stated decision tree (native continues, Python freezes, separate PID healthy). CASE 2 and CASE 3 are excluded.

**Is a GIL-domain explanation strengthened or weakened?**
**Weakened — substantially.** The GIL being free (0.005–0.026 ms refill gaps) and four threads coexisting inside `os.preadv` both contradict a GIL hold. The data supports a syscall-path stall instead.

**If strengthened, what native/Python code paths could plausibly hold the GIL?**
Not applicable — the GIL was free. For completeness, the reachable code in this process is small: the app imports only `modal`, `os`, `platform`, `subprocess`, `pathlib`, `typing`; the engine imports only stdlib (`ctypes`, `mmap`, `struct`, `threading`, `time`, …). **No torch, no CUDA, no numpy, no cffi, no logging, no `gc`/finalizer/`atexit`/`signal` use in the engine.** So the candidate list for a GIL holder is essentially empty, which is consistent with the GIL being free.

**Does CPython's `os.preadv()` release the GIL in our Python version?**
**Yes.** Verified two ways:
- *Runtime proof (this campaign):* four distinct Python threads were simultaneously inside `os.preadv` for 502.2 / 523.4 / 406.7 ms. Holding the GIL across the call would serialize them.
- *Source pattern:* CPython wraps blocking syscalls in `Py_BEGIN_ALLOW_THREADS`/`Py_END_ALLOW_THREADS` (confirmed for `os_open_impl`, `os_read_impl`, `os_write_impl` in `Modules/posixmodule.c`). I could not retrieve `os_preadv_impl` verbatim — the raw `posixmodule.c` and the annotated mirror both truncated before it — so I am **not** claiming a source quote for `preadv` specifically. The runtime proof above is the stronger evidence and does not depend on it.

**What is the narrowest defensible owner/state domain now?**
**The gVisor syscall path.** Precisely: *in-flight syscalls issued by the main process's threads stall for 100–500+ ms, while userspace-only execution in the same PID and in a separate PID continues normally.*

**What is the SINGLE best next diagnostic?**
A **syscall-making sentinel in a separate process** — a forked child that issues one trivial, non-filesystem syscall on a low cadence (e.g. `getpid`, or a tiny read on tmpfs) and records the same intended/enter/exit triple.

This is the one gap this campaign could not close: both healthy canaries are syscall-free by construction, so we cannot tell whether the stall is *container-wide syscall path* (gVisor Sentry) or *specific to the main process's syscall issuance*.
- If the separate-process syscall sentinel **also** stalls → the gVisor syscall path is container-wide; the domain is the Sentry, and the main process is simply the only place we issue syscalls from.
- If it **does not** stall → the syscall stall is specific to the main process/thread group, which would revive a thread-group-level explanation at the syscall layer rather than the scheduler layer.

Everything needed already exists: the fork canary harness, the intended/enter/exit sentinel design, and the ring layout. It is a small extension, not a new architecture.
