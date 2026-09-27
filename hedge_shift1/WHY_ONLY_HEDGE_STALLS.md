# Why does only the hedge worker stall? — correction and open question

## 1. Your objection holds, and it kills the resource-wide explanation

If the stall were a resource-level block (per-inode, per-volume, per-mount), **every** concurrent read on that resource would stall together. They don't:

- in a sick QD4 run, **one** read takes 6837 ms while the other three workers keep going at ~40 ms;
- within a worker, ~119 of 120 reads are ~40 ms and one is seconds.

So the stall is **local to a single in-flight read**, not a property of the shared resource. My earlier "same-path coupling" framing is therefore **not established**, and a hedge *should* be able to escape it.

## 2. Re-reading the alt-file evidence — it actually argues against coupling

The 7.3 s alt-file hedge **entered at 1371.10 ms while its own original had already exited at 1368.8 ms**. A hedge cannot be "riding" an original that finished before it started. **That 7.3 s was the hedge's own independent stall**, not coupling.

That was my error: I read "hedge slow" as "hedge coupled" without checking whether the original was still running.

## 3. The per-block hypothesis, and its test

Best remaining hypothesis: the stall is attached to a **specific block/offset** (a miss fetch), which would explain all of:
- only one worker stalls — that worker's block missed;
- others continue — their blocks are cached;
- a **same-block** hedge also stalls — it joins the same in-flight fetch;
- a different-file hedge is mostly fast (4 of 5 were 16–40 ms).

**Test run:** hedge shifted to a **different block of the same file** (`--hedge-shift-blocks 1`), 12 runs, 7 hedge events:

| original ms | trigger ms | receive→enter ms | hedge ms | winner |
|---:|---:|---:|---:|---|
| 171.1 | 125.8 | 83.13 | 45.46 | original |
| 157.5 | 132.4 | 112.76 | 24.43 | original |
| 147.9 | 125.2 | 107.66 | 94.75 | original |
| 133.3 | 128.2 | 3.26 | 94.60 | original |
| — | 125.4 | 0.17 | 55.20 | original |
| — | 125.3 | 2.26 | 45.92 | original |
| — | 125.9 | 0.34 | 53.11 | original |

**Shifted hedges: median 53.11 ms. Same-block hedges (fix2): median 17.86 ms.**

That is the **opposite** of the per-block prediction: reading a *different* block was *slower*, not faster. A plausible reading is that joining an already-in-flight fetch for the same block is *cheaper* than starting a fresh fetch for another block — which would make same-block duplication "coupled" in a benign sense (it completes with the fetch it joined) rather than blocked by a resource lock.

## 4. Why I am not calling this settled

The shift test is **confounded and under-powered**:

- **Mild originals only.** This batch's events had originals of 133–171 ms — no real stall. A genuine multi-second stall did not occur.
- **Serial hedge process.** `receive→enter` reached 83–113 ms, i.e. hedges queued behind each other. One slow hedge blocks the rest, so durations are not independent draws.
- **Two analyzer mis-keys.** Two events resolved to negative "original ms" (−2011.8, −2196.3) because my (worker, block) lookup matched the wrong physical record. Those rows are invalid.
- **n = 7**, one batch.

## 5. What is actually established

| claim | status |
|---|---|
| stall is resource-wide (per-inode/volume/mount) | **disproved** — other workers keep reading normally |
| coupling is a bug in our code | **disproved** — audit found no shared lock/pacer/FD/buffer/state |
| same-block hedge reliably loses | **established** — 0 wins across 12 clean events (fix2 + altfile) |
| the hedge rides the original | **not established** — the 7.3 s case started after its original ended |
| stall is per-block / cache-miss | **not established** — the shift test pointed the other way |

**The mechanism is genuinely unresolved.** What I have is a reproducible *behaviour* (same-block hedges don't win) without a proven *cause*.

## 6. The test that would settle it

One stall event, three hedge arms triggered off the **same** original read, all recorded on the same clock:

1. **same block, same file** (baseline — currently always loses)
2. **different block, same file** (per-block hypothesis)
3. **different file, same volume** (inode hypothesis)

Plus, to remove the confound: **a pool of hedge workers instead of one serial server**, so hedge durations are independent draws rather than queued ones. And the analyzer must key on `(worker, generation, block)`, not `(worker, block)`.

That is the experiment I'd run next — it is the only way to separate "per-block miss fetch" from "per-read luck" from "same-fetch join", and it needs a real multi-second stall to be meaningful.
